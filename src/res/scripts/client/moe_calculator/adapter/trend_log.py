# -*- coding: utf-8 -*-
"""Weekly MoE trend recorder -- one point per int_cd, per changed dossier read.

Feeds the garage tooltip's weekly trend chart (VIEWED TANK ONLY -- see domain/trend.py;
this file never aggregates across vehicles). Captured at the SAME event
adapter/sample_log.resolve() already rides: adapter/engine_adapter.build_snapshot()'s
post-battle dossier read, which fires on every items-cache resync (garage re-entry, tab
switch, ...), not just once per battle.

    mods_data/14th_ua_moe/moe_trend.json   a JSON list of points, rewritten in full on write

A plain JSON list (via moe_wgapi.read_json/write_json), not line-delimited: capture() prunes
then rewrites the WHOLE file on every write, so a JSONL append gains nothing here while still
costing a second hand-rolled atomic writer -- unlike sample_log.py's battle_samples.jsonl,
which is genuinely append-only and never rewritten.

Dedup ("one entry per int_cd change"): the same dossier read fires repeatedly for an
UNCHANGED career standing, so capture() compares against the LAST logged row for this
int_cd (read back from the file itself -- no separate last-seen cache/file needed) and
is a no-op when both percentile and avg_damage are unchanged.

Prune-on-write, unlike sample_log.py's deliberately-unbounded diagnostics log: this file
drives a live UI trend, not an accumulating record, so every write drops rows older than
the 7-day window (domain/trend.py re-derives the window against "now" at read time too,
since a row can cross the boundary between writes) plus a MAX_ROWS safety cap.

Engine-free apart from reusing moe_wgapi's prefs-dir + atomic-write helpers (lazy import),
so this module imports and unit-tests with the game closed. Fail-soft: every disk touch is
guarded, so a missing/corrupt file reads as empty and a write failure never raises into the
bridge.
"""
import os
import time

from moe_calculator._compat import LOG_CURRENT_EXCEPTION, LOG_DEBUG
from moe_calculator.domain.trend import WINDOW_SECONDS

TREND_FILE = "moe_trend.json"
# Safety cap independent of the time window (a pathological capture rate should still be
# bounded) -- generously above a typical week's row count (low hundreds per the research note).
MAX_ROWS = 2000


def capture(int_cd, percentile, avg_damage):
    """Append one {ts, int_cd, pct} point for this vehicle iff (percentile, avg_damage)
    changed since the last logged row for this int_cd. Returns True iff a row was written.
    Fail-soft: never raises."""
    try:
        cd = int(int_cd or 0)
        if not cd:
            return False
        pct = float(percentile or 0.0)
        avg = int(avg_damage or 0)
        rows = _load_rows()
        last = _last_row(rows, cd)
        if (last is not None and float(last.get("pct") or 0.0) == pct
                and int(last.get("avg") or 0) == avg):
            return False  # unchanged since last logged -> not a new battle
        rows.append({"ts": int(time.time()), "int_cd": cd, "pct": pct, "avg": avg})
        rows = _prune(rows, _now_epoch())
        _write_rows(rows)
        LOG_DEBUG("[moe-trend] logged %d: pct=%.2f avg=%d (rows=%d)" % (cd, pct, avg, len(rows)))
        return True
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return False


def rows_for(int_cd):
    """Every still-on-disk row for one int_cd, in file order (oldest first) -- what
    domain/trend.points_for windows into the tooltip's plotted list. Fail-soft: a missing/
    corrupt file (or a bad int_cd) reads as []."""
    try:
        cd = int(int_cd or 0)
        if not cd:
            return []
        return [row for row in _load_rows() if int(row.get("int_cd") or 0) == cd]
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return []


def _last_row(rows, cd):
    for row in reversed(rows):
        if int(row.get("int_cd") or 0) == cd:
            return row
    return None


def _prune(rows, now):
    """Drop rows older than the 7-day window, then cap to MAX_ROWS (oldest dropped first)."""
    cutoff = now - WINDOW_SECONDS
    kept = [row for row in rows if _row_ts(row) >= cutoff]
    if len(kept) > MAX_ROWS:
        kept = kept[-MAX_ROWS:]
    return kept


def _row_ts(row):
    try:
        return int(row.get("ts") or 0)
    except (TypeError, ValueError, AttributeError):
        return 0


def _now_epoch():
    return time.time()


# --- files -------------------------------------------------------------------

def _path():
    """<prefs>/mods_data/14th_ua_moe/moe_trend.json. moe_wgapi owns the prefs-dir lookup
    (its `helpers` import is lazy), so this module keeps no engine dependency of its own."""
    from moe_calculator.adapter.moe_wgapi import data_dir
    return os.path.join(data_dir(), TREND_FILE)


def _load_rows():
    """Every row as a list of dicts, file order. A missing/corrupt file, or a non-list
    envelope, reads as []; a non-dict entry is dropped rather than raising."""
    from moe_calculator.adapter.moe_wgapi import read_json
    blob = read_json(_path())
    if not isinstance(blob, list):
        return []
    return [row for row in blob if isinstance(row, dict)]


def _write_rows(rows):
    """Persist `rows` atomically (moe_wgapi.write_json's shared tmp+rename recipe)."""
    from moe_calculator.adapter.moe_wgapi import write_json
    write_json(_path(), rows)
