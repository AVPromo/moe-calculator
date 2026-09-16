# -*- coding: utf-8 -*-
"""Tests for adapter/trend_log -- the weekly garage-tooltip trend recorder.

Mirrors test_sample_log.py's tmp_path seam: moe_wgapi.data_dir is monkeypatched so the
whole capture -> rows_for flow runs on Python 3 with the game closed, using the REAL
read_json/write_json code (the trend store is a plain JSON list, rewritten in full on
every write -- see the module docstring)."""
import json
import time

from moe_calculator.adapter import moe_wgapi
from moe_calculator.adapter import trend_log


def _use_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(moe_wgapi, "data_dir", lambda: str(tmp_path))


def _rows(tmp_path):
    path = tmp_path / trend_log.TREND_FILE
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


# --- capture: append + dedup ---------------------------------------------------

def test_first_capture_for_a_tank_writes_a_row(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert trend_log.capture(1073, 73.67, 1850) is True
    rows = _rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["int_cd"] == 1073
    assert rows[0]["pct"] == 73.67
    assert isinstance(rows[0]["ts"], int)


def test_unchanged_repeat_capture_is_a_noop(monkeypatch, tmp_path):
    # The same dossier read fires on every items-cache resync, not just once per battle.
    _use_tmp(monkeypatch, tmp_path)
    trend_log.capture(1073, 73.67, 1850)
    assert trend_log.capture(1073, 73.67, 1850) is False
    assert len(_rows(tmp_path)) == 1


def test_a_changed_percentile_logs_a_new_row(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    trend_log.capture(1073, 73.67, 1850)
    assert trend_log.capture(1073, 74.10, 1866) is True
    assert len(_rows(tmp_path)) == 2


def test_a_changed_avg_damage_only_logs_a_new_row(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    trend_log.capture(1073, 73.67, 1850)
    assert trend_log.capture(1073, 73.67, 1851) is True
    assert len(_rows(tmp_path)) == 2


def test_dedup_is_keyed_per_int_cd(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    trend_log.capture(1073, 73.67, 1850)
    assert trend_log.capture(2049, 73.67, 1850) is True   # same values, different tank
    assert len(_rows(tmp_path)) == 2


def test_capture_rejects_a_falsy_int_cd(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert trend_log.capture(0, 73.67, 1850) is False
    assert trend_log.capture(None, 73.67, 1850) is False
    assert _rows(tmp_path) == []


# --- rows_for -------------------------------------------------------------------

def test_rows_for_filters_by_int_cd(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    trend_log.capture(1073, 73.67, 1850)
    trend_log.capture(2049, 50.0, 900)
    trend_log.capture(1073, 74.10, 1866)
    rows = trend_log.rows_for(1073)
    assert [r["pct"] for r in rows] == [73.67, 74.10]


def test_rows_for_missing_file_reads_as_empty(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert trend_log.rows_for(1073) == []


def test_rows_for_rejects_a_falsy_int_cd(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    trend_log.capture(1073, 73.67, 1850)
    assert trend_log.rows_for(0) == []


# --- pruning: 7-day window + MAX_ROWS safety cap --------------------------------

def test_prune_drops_rows_older_than_7_days(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    now = time.time()
    old_row = {"ts": int(now - 8 * 24 * 3600), "int_cd": 1073, "pct": 60.0, "avg": 1000}
    (tmp_path / trend_log.TREND_FILE).write_text(json.dumps([old_row]), encoding="utf-8")
    monkeypatch.setattr(trend_log, "_now_epoch", lambda: now)
    assert trend_log.capture(1073, 73.67, 1850) is True
    rows = _rows(tmp_path)
    # the stale row was pruned on this write, only the fresh capture remains
    assert len(rows) == 1 and rows[0]["pct"] == 73.67


def test_prune_caps_at_max_rows(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(trend_log, "MAX_ROWS", 3)
    for pct in (60.0, 61.0, 62.0, 63.0):
        # distinct (pct, avg) each time so the dedup gate never suppresses a write
        trend_log.capture(1073, pct, int(pct * 10))
    rows = _rows(tmp_path)
    assert len(rows) == 3
    assert [r["pct"] for r in rows] == [61.0, 62.0, 63.0]   # oldest dropped first


# --- fail-soft: corrupt / unreadable file ---------------------------------------

def test_corrupt_file_reads_as_empty(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    (tmp_path / trend_log.TREND_FILE).write_bytes(b'{"not": "a list", "trunc')
    assert trend_log._load_rows() == []
    assert trend_log.rows_for(1073) == []
    # capture still succeeds -- the corrupt file is simply replaced with the new content.
    assert trend_log.capture(1073, 73.67, 1850) is True


def test_non_list_envelope_reads_as_empty(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    (tmp_path / trend_log.TREND_FILE).write_text(json.dumps({"int_cd": 1073}), encoding="utf-8")
    assert trend_log._load_rows() == []


def test_non_dict_entries_are_dropped(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    (tmp_path / trend_log.TREND_FILE).write_text(
        json.dumps(["nope", {"int_cd": 2049, "ts": 1, "pct": 50.0}]), encoding="utf-8")
    assert trend_log._load_rows() == [{"int_cd": 2049, "ts": 1, "pct": 50.0}]


def test_capture_is_falsey_when_data_dir_raises(monkeypatch):
    def boom():
        raise RuntimeError("no prefs dir")

    monkeypatch.setattr(moe_wgapi, "data_dir", boom)
    assert trend_log.capture(1073, 73.67, 1850) is False


def test_rows_for_is_empty_when_data_dir_raises(monkeypatch):
    def boom():
        raise RuntimeError("no prefs dir")

    monkeypatch.setattr(moe_wgapi, "data_dir", boom)
    assert trend_log.rows_for(1073) == []
