# -*- coding: utf-8 -*-
"""Engine-free tests for domain/trend.py -- the weekly garage-tooltip MoE trend chart's pure
windowing (VIEWED TANK ONLY: rows are already scoped to one int_cd by adapter/trend_log
before they reach this module -- see the module docstring)."""
from moe_calculator.domain import trend

NOW = 1_700_000_000
DAY = 24 * 3600


def _row(ts, pct):
    return {"ts": ts, "pct": pct}


def test_empty_rows_yield_no_points():
    assert trend.points_for([], NOW) == []
    assert trend.points_for(None, NOW) == []


def test_points_within_the_window_survive():
    rows = [_row(NOW - 1 * DAY, 70.0), _row(NOW - 6 * DAY, 65.0), _row(NOW, 75.0)]
    assert trend.points_for(rows, NOW) == [[NOW - 6 * DAY, 65.0], [NOW - 1 * DAY, 70.0], [NOW, 75.0]]


def test_points_older_than_7_days_are_dropped():
    rows = [_row(NOW - 8 * DAY, 60.0), _row(NOW - 6 * DAY, 65.0)]
    assert trend.points_for(rows, NOW) == [[NOW - 6 * DAY, 65.0]]


def test_exactly_7_days_old_is_still_in_window():
    rows = [_row(NOW - 7 * DAY, 65.0)]
    assert trend.points_for(rows, NOW) == [[NOW - 7 * DAY, 65.0]]


def test_a_future_timestamp_is_dropped():
    # A clock-skew / hand-edited row from "the future" relative to `now` must not appear.
    rows = [_row(NOW + DAY, 90.0), _row(NOW - DAY, 70.0)]
    assert trend.points_for(rows, NOW) == [[NOW - DAY, 70.0]]


def test_output_is_chronological_regardless_of_input_order():
    rows = [_row(NOW, 80.0), _row(NOW - 5 * DAY, 60.0), _row(NOW - 2 * DAY, 70.0)]
    assert trend.points_for(rows, NOW) == [
        [NOW - 5 * DAY, 60.0], [NOW - 2 * DAY, 70.0], [NOW, 80.0]]


def test_a_corrupt_row_is_skipped_not_raised():
    rows = [_row(NOW, 80.0), {"ts": "nope", "pct": "also nope"}, {}]
    assert trend.points_for(rows, NOW) == [[NOW, 80.0]]


def test_points_are_plain_lists_not_tuples():
    # The JS-side wire contract is a JSON array of [ts, pct] pairs -- json.dumps(tuple) also
    # serializes as an array, but pin the list shape so a future refactor can't accidentally
    # emit e.g. a dict per point instead.
    out = trend.points_for([_row(NOW, 80.0)], NOW)
    assert out == [[NOW, 80.0]]
    assert isinstance(out[0], list)


def _day_row(ts, avg):
    return {"ts": ts, "avg": avg}


def _bucket_day(ts):
    # Deterministic day key -- no real tz/clock dependence.
    return ts // DAY


def test_days_for_empty_or_none_rows_yields_no_days():
    assert trend.days_for([], NOW, day_of=_bucket_day) == []
    assert trend.days_for(None, NOW, day_of=_bucket_day) == []


def test_days_for_groups_rows_spanning_a_day_boundary():
    day0 = NOW - 2 * DAY
    day1 = NOW - 1 * DAY
    rows = [
        _day_row(day0, 1000),
        _day_row(day0 + 100, 1100),
        _day_row(day1, 1200),
    ]
    assert trend.days_for(rows, NOW, day_of=_bucket_day) == [
        {"count": 2, "dmg": 1100},
        {"count": 1, "dmg": 1200},
    ]


def test_days_for_single_day_returns_one_entry():
    rows = [_day_row(NOW - 100, 900), _day_row(NOW - 50, 950), _day_row(NOW, 1000)]
    assert trend.days_for(rows, NOW, day_of=_bucket_day) == [{"count": 3, "dmg": 1000}]


def test_days_for_excludes_rows_older_than_the_window_like_points_for():
    rows = [_day_row(NOW - 8 * DAY, 500), _day_row(NOW - 6 * DAY, 600)]
    assert trend.days_for(rows, NOW, day_of=_bucket_day) == [{"count": 1, "dmg": 600}]


def test_days_for_exactly_7_days_old_is_still_in_window():
    rows = [_day_row(NOW - 7 * DAY, 700)]
    assert trend.days_for(rows, NOW, day_of=_bucket_day) == [{"count": 1, "dmg": 700}]


def test_days_for_coerces_a_fractional_avg_to_a_whole_number():
    # domain/trend.py reads "avg" via int(round(...)) -- true rounding, not truncation.
    # 1234.9 must round UP to 1235; truncation (int(1234.9) == 1234) would fail this.
    rows = [_day_row(NOW, 1234.9)]
    assert trend.days_for(rows, NOW, day_of=_bucket_day) == [{"count": 1, "dmg": 1235}]
