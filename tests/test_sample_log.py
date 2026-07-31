# -*- coding: utf-8 -*-
"""Tests for adapter/sample_log -- the per-battle prediction<->outcome recorder.

The module is engine-free apart from reusing moe_wgapi's prefs-dir helper, so the whole
stash -> resolve flow runs on Python 3 with the game closed: we point `moe_wgapi.data_dir`
at pytest's tmp_path (the module resolves it lazily inside _path, so a plain monkeypatch of
the module attribute is the injection seam) and let the REAL read_json/write_json do the
disk work. Mirrors the monkeypatched-seam idiom in test_engine_adapter / test_moe_wgapi.
"""
import json
import time
from collections import OrderedDict

from moe_calculator.adapter import moe_wgapi
from moe_calculator.adapter import sample_log

# The JSONL column order, pinned as a wire contract (the file is meant to be read by hand and
# by an offline fitting script). mod_version rides between "v" and "ts" only when the stashing
# build could resolve it; post_battles is appended only when supplied.
_EXPECTED_KEYS = [
    "v", "ts",
    "int_cd", "ewma_k", "thresholds", "pre_percentile", "pre_avg_damage", "baseline_known",
    "damage", "track_assist", "spot_assist", "stun", "team_damage",
    "combined_damage", "counted_assist", "assist_kind", "proj_avg_damage",
    "predicted_percent", "pct_delta", "has_data", "has_baseline",
    "post_percentile", "post_avg_damage", "residual", "post_battles",
]

# The post-mortem-credit instrumentation columns append AFTER post_battles, so adding them left
# the pinned order above untouched.
_EXPECTED_KEYS_WITH_FINAL = _EXPECTED_KEYS + ["final_combined_damage", "final_percent"]


def _use_tmp(monkeypatch, tmp_path):
    """Point the recorder's data dir at tmp_path and forget any cached mod version."""
    monkeypatch.setattr(moe_wgapi, "data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(sample_log, "_version", None)


def _pred(int_cd=1073, **over):
    """A plausible end-of-battle prediction, as bridge/battle_bridge._flush_prediction emits it."""
    pred = {
        "int_cd": int_cd, "ewma_k": 0.02,
        "thresholds": {65: 2544, 85: 3634, 95: 4512, 100: 5229},
        "pre_percentile": 73.67, "pre_avg_damage": 1850, "baseline_known": True,
        "damage": 2400, "track_assist": 300, "spot_assist": 100, "stun": 0, "team_damage": 0,
        "combined_damage": 2700, "counted_assist": 300, "assist_kind": "track",
        "proj_avg_damage": 1867, "predicted_percent": 74.30, "pct_delta": 0.63,
        "has_data": True, "has_baseline": True,
    }
    pred.update(over)
    return pred


def _samples(tmp_path):
    """Every complete sample row written so far, in file order."""
    path = tmp_path / sample_log.SAMPLES_FILE
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _pending(tmp_path):
    path = tmp_path / sample_log.PENDING_FILE
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# --- happy path: stash -> resolve --------------------------------------------

def test_stash_then_resolve_writes_exactly_one_sample(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert sample_log.stash(_pred()) is True
    assert sample_log.resolve(1073, 74.10, 1866, 1240) is True
    rows = _samples(tmp_path)
    assert len(rows) == 1
    assert rows[0]["int_cd"] == 1073
    assert rows[0]["post_percentile"] == 74.10
    assert rows[0]["post_avg_damage"] == 1866
    assert rows[0]["post_battles"] == 1240


def test_resolved_row_key_order_is_the_wire_contract(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    sample_log.resolve(1073, 74.10, 1866, 1240)
    assert list(_samples(tmp_path)[0].keys()) == _EXPECTED_KEYS


def test_row_is_an_ordered_dict(monkeypatch, tmp_path):
    # The order above is only GUARANTEED in-game (Python 2.7, where a plain dict serializes in
    # hash order) by the OrderedDict -- a py3 test can't observe the difference, so pin the type.
    _use_tmp(monkeypatch, tmp_path)
    row = sample_log._row(_pred(), 74.10, 1866, 1240)
    assert isinstance(row, OrderedDict)
    assert list(row.keys()) == _EXPECTED_KEYS


def test_row_carries_the_version_and_a_timestamp(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    sample_log.resolve(1073, 74.10, 1866)
    row = _samples(tmp_path)[0]
    assert row["v"] == sample_log.ROW_VERSION
    assert isinstance(row["ts"], int)
    assert abs(row["ts"] - int(time.time())) < 60


def test_residual_is_actual_minus_predicted(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred(predicted_percent=74.30))
    sample_log.resolve(1073, 74.10, 1866)
    row = _samples(tmp_path)[0]
    # The whole point of the recorder: how far the overlay over/under-predicted.
    assert row["residual"] == row["post_percentile"] - row["predicted_percent"]
    assert abs(row["residual"] - (-0.20)) < 1e-9


def test_resolve_empties_the_pending_file(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    assert list(_pending(tmp_path)) == ["1073"]
    sample_log.resolve(1073, 74.10, 1866)
    assert _pending(tmp_path) == {}


def test_post_battles_omitted_when_not_supplied(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    sample_log.resolve(1073, 74.10, 1866)
    assert "post_battles" not in _samples(tmp_path)[0]


# --- the "post values changed" gate ------------------------------------------
# The same dossier read fires repeatedly (every items-cache resync, every garage re-entry);
# only the read that actually carries the post-battle numbers may be credited.

def test_unchanged_post_values_leave_the_row_pending(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    assert sample_log.resolve(1073, 73.67, 1850) is False   # dossier hasn't caught up
    assert _samples(tmp_path) == []
    assert list(_pending(tmp_path)) == ["1073"]


def test_a_later_changed_read_resolves_the_waiting_row_once(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    sample_log.resolve(1073, 73.67, 1850)                   # still pre values -> waits
    sample_log.resolve(1073, 73.67, 1850)                   # and again -> still waits
    assert sample_log.resolve(1073, 74.10, 1866) is True    # dossier moved -> credited
    assert len(_samples(tmp_path)) == 1
    assert _pending(tmp_path) == {}


def test_second_resolve_for_the_same_tank_is_a_noop(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    sample_log.resolve(1073, 74.10, 1866)
    assert sample_log.resolve(1073, 74.10, 1866) is False   # nothing pending any more
    assert len(_samples(tmp_path)) == 1                     # no duplicate line


def test_percentile_only_move_resolves(monkeypatch, tmp_path):
    # The gate is "not BOTH unchanged": a rating that moved while movingAvgDamage rounded to the
    # same integer is still a post-battle read.
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    assert sample_log.resolve(1073, 73.71, 1850) is True


def test_avg_damage_only_move_resolves(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    assert sample_log.resolve(1073, 73.67, 1851) is True


def test_resolve_without_a_pending_row_is_false(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert sample_log.resolve(1073, 74.10, 1866) is False
    assert _samples(tmp_path) == []


# --- multi-tank pairing ------------------------------------------------------

def test_pending_is_keyed_by_int_cd_and_resolves_independently(monkeypatch, tmp_path):
    # Several tanks played before reaching a resolvable hangar state: each pairs up on its own.
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred(1073, predicted_percent=74.30))
    sample_log.stash(_pred(2049, predicted_percent=51.00, pre_percentile=50.0,
                           pre_avg_damage=900))
    assert sorted(_pending(tmp_path)) == ["1073", "2049"]

    assert sample_log.resolve(1073, 74.10, 1866) is True
    rows = _samples(tmp_path)
    assert len(rows) == 1 and rows[0]["int_cd"] == 1073
    assert list(_pending(tmp_path)) == ["2049"]             # tank B still waiting

    assert sample_log.resolve(2049, 51.40, 915) is True
    assert [r["int_cd"] for r in _samples(tmp_path)] == [1073, 2049]
    assert _pending(tmp_path) == {}


def test_stash_overwrites_the_same_tanks_pending_row(monkeypatch, tmp_path):
    # Two battles in a row in the same tank with no resolvable read between: the LATEST
    # prediction is the one that gets graded (documented overwrite, not an append).
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred(predicted_percent=74.30))
    sample_log.stash(_pred(predicted_percent=75.90))
    assert list(_pending(tmp_path)) == ["1073"]
    sample_log.resolve(1073, 76.00, 1900)
    assert _samples(tmp_path)[0]["predicted_percent"] == 75.90


def test_stash_rejects_a_falsy_int_cd(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert sample_log.stash(_pred(0)) is False
    assert sample_log.stash(_pred(None)) is False
    assert _pending(tmp_path) == {}


def test_resolve_rejects_a_falsy_int_cd(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    assert sample_log.resolve(0, 74.10, 1866) is False
    assert _samples(tmp_path) == []


# --- unreadable pending file -------------------------------------------------

def test_missing_pending_file_reads_as_empty(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    assert sample_log._load_pending() == {}


def test_corrupt_pending_file_reads_as_empty(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    (tmp_path / sample_log.PENDING_FILE).write_bytes(b'{"1073": {"int_cd": 10')  # truncated
    assert sample_log._load_pending() == {}
    assert sample_log.resolve(1073, 74.10, 1866) is False   # never raises
    # A stash still succeeds -- the corrupt file is simply replaced.
    assert sample_log.stash(_pred()) is True
    assert list(_pending(tmp_path)) == ["1073"]


def test_non_dict_pending_file_reads_as_empty(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    (tmp_path / sample_log.PENDING_FILE).write_text('[1, 2, 3]', encoding="utf-8")
    assert sample_log._load_pending() == {}


def test_non_dict_pending_values_are_dropped(monkeypatch, tmp_path):
    # A hand-edited file with a junk row must not become a half-read record.
    _use_tmp(monkeypatch, tmp_path)
    (tmp_path / sample_log.PENDING_FILE).write_text(
        '{"1073": "nope", "2049": {"int_cd": 2049}}', encoding="utf-8")
    assert sample_log._load_pending() == {"2049": {"int_cd": 2049}}


def test_unreadable_pending_path_reads_as_empty(monkeypatch, tmp_path):
    # The pending path is a DIRECTORY (or otherwise unopenable) -> reads as absent, no raise.
    _use_tmp(monkeypatch, tmp_path)
    (tmp_path / sample_log.PENDING_FILE).mkdir()
    assert sample_log._load_pending() == {}
    assert sample_log.resolve(1073, 74.10, 1866) is False


# --- fail-soft: the prefs dir itself is unavailable --------------------------

def _broken_data_dir(monkeypatch):
    def boom():
        raise RuntimeError("no prefs dir")

    monkeypatch.setattr(moe_wgapi, "data_dir", boom)
    monkeypatch.setattr(sample_log, "_version", None)


def test_stash_is_falsey_when_data_dir_raises(monkeypatch):
    _broken_data_dir(monkeypatch)
    assert not sample_log.stash(_pred())


def test_resolve_is_falsey_when_data_dir_raises(monkeypatch):
    _broken_data_dir(monkeypatch)
    assert not sample_log.resolve(1073, 74.10, 1866, 1240)


# --- field fidelity ----------------------------------------------------------

def test_thresholds_round_trip_as_string_keys(monkeypatch, tmp_path):
    # JSON has no int keys: the anchors come back as "65"/"85"/"95"/"100" -- the PERCENTILE keys,
    # stringified. Pinned so the offline analysis script can rely on it (and so a future "keep
    # ints" change is a deliberate one).
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    sample_log.resolve(1073, 74.10, 1866)
    assert _samples(tmp_path)[0]["thresholds"] == {"65": 2544, "85": 3634, "95": 4512,
                                                   "100": 5229}


def test_missing_prediction_field_logs_null_rather_than_raising(monkeypatch, tmp_path):
    # Every prediction key is read with .get, so a caller that omits one still produces a row.
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash({"int_cd": 1073, "pre_percentile": 73.67, "pre_avg_damage": 1850})
    assert sample_log.resolve(1073, 74.10, 1866) is True
    row = _samples(tmp_path)[0]
    assert row["damage"] is None and row["assist_kind"] is None
    assert row["residual"] == 74.10                          # predicted defaults to 0.0


def test_mod_version_omitted_when_the_entry_point_is_not_importable(monkeypatch, tmp_path):
    # Outside the client `gui.mods.mod_moe_calculator` doesn't exist -> the key is dropped
    # rather than a drifting literal being invented.
    _use_tmp(monkeypatch, tmp_path)
    assert sample_log._mod_version() == ""
    sample_log.stash(_pred())
    assert "mod_version" not in _pending(tmp_path)["1073"]
    sample_log.resolve(1073, 74.10, 1866)
    assert "mod_version" not in _samples(tmp_path)[0]


def test_mod_version_recorded_when_resolvable(monkeypatch, tmp_path):
    # In-client the entry point IS in sys.modules; the version then rides right after "v".
    _use_tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(sample_log, "_version", "1.6.0")
    sample_log.stash(_pred())
    sample_log.resolve(1073, 74.10, 1866)
    row = _samples(tmp_path)[0]
    assert list(row)[:3] == ["v", "mod_version", "ts"]
    assert row["mod_version"] == "1.6.0"


def test_mod_version_is_stamped_at_stash_time_not_at_resolve_time(monkeypatch, tmp_path):
    # Pending rows persist on disk across client restarts, so a mod update between the prediction
    # and its dossier read must credit the build that PREDICTED -- otherwise exactly the samples
    # that straddle a mapping change get misattributed to the new mapping.
    _use_tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(sample_log, "_version", "1.6.0")
    sample_log.stash(_pred())
    assert _pending(tmp_path)["1073"]["mod_version"] == "1.6.0"
    monkeypatch.setattr(sample_log, "_version", "1.7.0")   # relaunched on an updated build
    sample_log.resolve(1073, 74.10, 1866)
    assert _samples(tmp_path)[0]["mod_version"] == "1.6.0"


def test_a_pending_row_stashed_without_a_version_still_resolves(monkeypatch, tmp_path):
    # Rows left pending by a build that predated the stash-time stamp carry no version -> the
    # column is simply omitted rather than borrowing the resolving build's number.
    _use_tmp(monkeypatch, tmp_path)
    (tmp_path / sample_log.PENDING_FILE).write_text(json.dumps({"1073": _pred()}),
                                                    encoding="utf-8")
    monkeypatch.setattr(sample_log, "_version", "1.6.0")
    assert sample_log.resolve(1073, 74.10, 1866) is True
    assert "mod_version" not in _samples(tmp_path)[0]


def test_stash_does_not_mutate_the_callers_prediction(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    monkeypatch.setattr(sample_log, "_version", "1.6.0")
    pred = _pred()
    sample_log.stash(pred)
    assert "mod_version" not in pred


# --- the post-mortem-credit instrumentation columns --------------------------
# The prediction of record is the last NON-spectating push (our state at death), while WG keeps
# crediting us afterwards and the dossier includes that credit. The bridge therefore also supplies
# the battle's trailing push; these columns let the samples answer whether it diverges.

def test_final_columns_are_appended_after_post_battles(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred(final_combined_damage=2900, final_percent=74.55))
    sample_log.resolve(1073, 74.10, 1866, 1240)
    row = _samples(tmp_path)[0]
    assert list(row.keys()) == _EXPECTED_KEYS_WITH_FINAL
    assert row["final_combined_damage"] == 2900
    assert row["final_percent"] == 74.55


def test_final_columns_are_omitted_when_the_bridge_supplied_none(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    sample_log.stash(_pred())
    sample_log.resolve(1073, 74.10, 1866, 1240)
    row = _samples(tmp_path)[0]
    assert list(row.keys()) == _EXPECTED_KEYS
    assert "final_combined_damage" not in row and "final_percent" not in row


def test_final_columns_survive_a_missing_post_battles(monkeypatch, tmp_path):
    # post_battles is itself optional, so the final pair must still land last, not leave a hole.
    _use_tmp(monkeypatch, tmp_path)
    row = sample_log._row(_pred(final_combined_damage=2900, final_percent=74.55),
                          74.10, 1866, None)
    assert list(row.keys())[-3:] == ["residual", "final_combined_damage", "final_percent"]


def test_a_zero_final_value_is_still_recorded(monkeypatch, tmp_path):
    # 0 damage / 0.0 percent are real readings (a scout that died spotting), not "absent".
    _use_tmp(monkeypatch, tmp_path)
    row = sample_log._row(_pred(final_combined_damage=0, final_percent=0.0), 74.10, 1866, 1240)
    assert row["final_combined_damage"] == 0 and row["final_percent"] == 0.0


def test_samples_file_is_append_only_across_battles(monkeypatch, tmp_path):
    _use_tmp(monkeypatch, tmp_path)
    for pct, avg in ((74.10, 1866), (74.55, 1880), (74.90, 1895)):
        sample_log.stash(_pred(pre_percentile=pct - 0.4, pre_avg_damage=avg - 14))
        assert sample_log.resolve(1073, pct, avg) is True
    assert [r["post_percentile"] for r in _samples(tmp_path)] == [74.10, 74.55, 74.90]
