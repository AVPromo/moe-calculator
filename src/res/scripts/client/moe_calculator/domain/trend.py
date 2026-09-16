# -*- coding: utf-8 -*-
"""Pure windowing for the garage-tooltip weekly MoE trend chart. Engine-free.

Scope: VIEWED TANK ONLY -- the tooltip plots the currently-viewed vehicle's own trend, not
an account-wide aggregate (percentiles have no common scale across different tanks).

adapter/trend_log.capture() appends one point per int_cd whenever the resolved dossier
percentile/avg_damage changes (adapter/engine_adapter.build_snapshot, same event as
sample_log.resolve). adapter/trend_log.rows_for(int_cd) hands back that vehicle's rows;
this module turns them into the chronological [[ts, pct], ...] point list the tooltip
plots as one div bar per point, re-windowed to "now - 7 days" so a row that crossed the
boundary since the last write (storage only prunes ON WRITE) never shows as stale.
"""
import time
from itertools import groupby

WINDOW_SECONDS = 7 * 24 * 3600


def _windowed(rows, now, field, cast):
    """Shared scaffolding for points_for/_windowed_avg_points: window `rows` (one int_cd's
    dossier-trend records, each carrying "ts"/`field`) to [now - WINDOW_SECONDS, now], parse
    + coerce `field` via `cast`, sort chronologically. Returns [(ts, value), ...] oldest
    first. Pure, fail-soft: a corrupt/hand-edited row is skipped, never raised."""
    cutoff = now - WINDOW_SECONDS
    pts = []
    for row in (rows or []):
        try:
            ts = int(row.get("ts") or 0)
            if ts < cutoff or ts > now:
                continue
            value = cast(row.get(field) or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        pts.append((ts, value))
    pts.sort(key=lambda p: p[0])
    return pts


def points_for(rows, now):
    """rows: dossier-trend records already scoped to ONE int_cd (adapter/trend_log.rows_for)
    -- {"ts": <epoch>, "pct": <float>, ...} dicts, order-agnostic and possibly carrying a
    corrupt/hand-edited entry (skipped, never raises). Returns [[ts, pct], ...] within
    [now - WINDOW_SECONDS, now], oldest first. Pure."""
    return [[ts, pct] for ts, pct in _windowed(rows, now, "pct", float)]


def _default_day_of(ts):
    """Local-calendar-day bucket key for an epoch timestamp: (year, month, day) via the
    system tz. The real-clock/tz-dependent seam -- tests inject their own `day_of` instead
    of relying on this."""
    return time.localtime(ts)[:3]


def _windowed_avg_points(rows, now):
    """Shared scaffolding for days_for: window `rows` (one int_cd's dossier-trend
    records, each carrying "ts"/"avg") to [now - WINDOW_SECONDS, now], parse + coerce "avg"
    to a whole int, sort chronologically. Returns [(ts, avg), ...] oldest first. Pure,
    fail-soft: a corrupt/hand-edited row is skipped, never raised."""
    return _windowed(rows, now, "avg", lambda v: int(round(float(v))))


def days_for(rows, now, day_of=None):
    """Group `rows` (same shape/scope as points_for -- one int_cd's dossier-trend records,
    each carrying "ts"/"avg") into per-LOCAL-CALENDAR-DAY buckets, re-windowed to
    [now - WINDOW_SECONDS, now] exactly like points_for. Returns
    [{"count": <int points that day>, "dmg": <int end-of-day avg damage>}, ...] in
    chronological (oldest day first) order; `dmg` is the LAST point's "avg" field for that
    day (end-of-day career avg damage), rounded to a whole number.

    `day_of(ts)` buckets a timestamp to a calendar-day key; defaults to `_default_day_of`
    (system-local tz). Injectable so this stays pure/deterministic under test -- never
    depends on the real clock or timezone directly. Fail-soft: empty/None `rows` -> []."""
    if day_of is None:
        day_of = _default_day_of
    pts = _windowed_avg_points(rows, now)

    # pts is already sorted by ts, so same-day points are contiguous -- groupby's adjacent-run
    # grouping is exactly the per-day bucketing this needs.
    days = []
    for _, group in groupby(pts, key=lambda p: day_of(p[0])):
        day_pts = list(group)
        days.append({"count": len(day_pts), "dmg": day_pts[-1][1]})  # last point of the day wins
    return days
