# -*- coding: utf-8 -*-
"""Tests for the engine-free in-battle domain layer. Like test_builder.py these run on
Python 3 (no game engine) because domain/battle_builder imports zero game symbols -- the
in-battle MoE math is pure and unit-testable with the client closed."""
import pytest

from moe_calculator.domain import battle_types as bt
from moe_calculator.domain.battle_builder import (
    combined_damage, counted_assistance, ewma_project,
    build_battle_model, battle_bar_visible, _fit_from_thresholds, _smooth_percent)
from moe_calculator.domain.constants import EWMA_K, MARK_PERCENTS


# A clean threshold set (round numbers) so interpolation asserts stay exact. Keyed by
# PERCENTILE -- 65/85/95 are the 1/2/3-mark requirements, 100 the goalpost.
_THR = {65: 1000, 85: 2000, 95: 3000, 100: 4000}

# The four REQUIRED anchors every table carries, as (percentile key, percentile). The fit must
# reproduce each of them exactly -- the percentile IS the key now, no remap and no goalpost
# substitution (WG returns a real 100th-percentile damage, so there is no Phi^-1(1) infinity).
_STOPS = tuple((p, float(p)) for p in MARK_PERCENTS + (100,))

# Real per-tank EU tables, lifted verbatim from a live mods_data/14th_ua_moe/
# moe_wgapi_cache.json (keys are the vehicle int_cds). HARDCODED on purpose -- the test must
# never read that file or depend on this machine. WG's real distribution is NOT normal at all,
# which is why the superseded piecewise-NORMAL fit missed by up to 11.9pp below the lowest
# stop; these shapes are the regression fixtures for that bug.
_REAL_7281 = {65: 2807, 85: 3898, 95: 4749, 100: 5426}
_REAL_51537 = {65: 1721, 85: 2392, 95: 2914, 100: 3319}
_REAL_17217 = {65: 2521, 85: 3770, 95: 4793, 100: 5654}
_REAL_26705 = {65: 3312, 85: 4491, 95: 5405, 100: 6133}

# A real EU EIGHT-anchor row (int_cd 54657) -- the shape the current fetch returns, and the
# table the 118-battle back-test's low-percentile pins below were computed on.
_REAL_8_54657 = {20: 528, 40: 1163, 55: 1549, 65: 1799,
                 75: 2104, 85: 2494, 95: 3042, 100: 3482}

_ALL_REAL = (_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705, _REAL_8_54657)


def _with(thr, overrides):
    """`thr` plus int-keyed overrides. (`dict(thr, **{20: 1})` is a TypeError -- keywords must
    be strings -- and these keys are ints.)"""
    out = dict(thr)
    out.update(overrides)
    return out


def _bsnap(**kw):
    base = dict(vehicle_int_cd=1073, nation="germany", damage=2000, assist=500,
                stun=300, team_damage=0, pre_avg_damage=1800, pre_percentile=70.0,
                thresholds=dict(_THR))
    base.update(kw)
    return bt.BattleSnapshot(**base)


# --- counted_assistance ------------------------------------------------------

def test_counted_assistance_picks_highest_stream():
    assert counted_assistance(700, 400, 300) == (700, "track")   # tracking leads
    assert counted_assistance(400, 700, 300) == (700, "spot")    # spotting leads
    assert counted_assistance(400, 300, 900) == (900, "stun")    # stun leads


def test_counted_assistance_tie_breaks():
    # track vs spot tie -> spotting wins.
    assert counted_assistance(500, 500, 0) == (500, "spot")
    # stun only wins when STRICTLY greater, so a tie keeps the assist stream.
    assert counted_assistance(0, 600, 600) == (600, "spot")
    assert counted_assistance(600, 0, 600) == (600, "track")


def test_counted_assistance_zero_is_generic():
    # Total 0 -> value 0 + generic kind (the row hides in this case).
    assert counted_assistance(0, 0, 0) == (0, "assist")


def test_counted_assistance_merged_fallback_before_split():
    # Split not delivered yet (track/spot 0) but merged assist known -> credit merged as the
    # assist component with the generic 'assist' kind, so combined damage never under-counts.
    assert counted_assistance(0, 0, 0, 800) == (800, "assist")
    # stun still wins when strictly greater than the merged assist.
    assert counted_assistance(0, 0, 900, 800) == (900, "stun")
    # once the real split arrives it takes over from the merged fallback.
    assert counted_assistance(700, 100, 0, 800) == (700, "track")


def test_counted_assistance_handles_none():
    assert counted_assistance(None, None, None) == (0, "assist")


# --- combined_damage ---------------------------------------------------------

def test_combined_damage_takes_max_not_sum():
    # tracking 500 dominates spotting 300 and stun 0 -> +500, NOT +800 (WG #15060: max).
    assert combined_damage(2000, 500, 300, 0, 0) == 2500
    # stun dominates the assist streams
    assert combined_damage(2000, 100, 200, 700, 0) == 2700


def test_combined_damage_subtracts_team_damage():
    assert combined_damage(2000, 500, 0, 0, 300) == 2200


def test_combined_damage_clamps_non_negative():
    assert combined_damage(0, 0, 0, 0, 500) == 0
    assert combined_damage(100, 0, 0, 0, 999) == 0


def test_combined_damage_handles_none():
    assert combined_damage(None, None, None, None, None) == 0


def test_combined_damage_merged_fallback():
    # track/spot 0 but the merged live assist is known -> counted as the assist component.
    assert combined_damage(2000, 0, 0, 0, 0, merged_assist=500) == 2500


# --- the damage -> percent map (_fit_from_thresholds + _smooth_percent) ------
# WG's damageRating IS piecewise-LINEAR interpolation of average combined damage over the
# percentile anchors WG stores, PLUS an implicit (0 damage, 0 percent) origin stop. Confirmed by
# back-test over 118 logged real battles (percentiles 1.7-86): level error mean +0.047pp, stdev
# 0.088, max 0.238. The superseded piecewise-NORMAL 4-stop fit peaked at 11.9pp of error,
# concentrated below the lowest stop. So the "fit" IS the anchor list -- nothing is solved, no
# z-space, no probit -- and the tests below are exactness/shape assertions, not fit-quality ones.


def _reference_percent(damage, thresholds):
    """An INDEPENDENTLY-WRITTEN reference for the mapping -- the oracle.

    Deliberately NOT imported from tools/dev/analyze_battle_samples.lin_percent (a dev tool that
    may change) and deliberately not sharing a line of code with the shipped implementation: it
    is ten lines, and its independence is the entire point. This is the function that was
    validated against the 118 real battles."""
    pts = [(0.0, 0.0)]
    for p in sorted(int(k) for k in thresholds):
        d = float(thresholds[p])
        if d > pts[-1][0]:
            pts.append((d, float(p)))
    d = float(damage)
    if d <= 0.0:
        return 0.0
    for (d0, p0), (d1, p1) in zip(pts, pts[1:]):
        if d <= d1:
            return p0 + (p1 - p0) * (d - d0) / (d1 - d0)
    return pts[-1][1]


def _damage_at_percent(thr, percent):
    """The combined damage whose curve percent is `percent` -- the INVERSE of the piecewise-linear
    map, derived straight from the table's anchor pair that brackets `percent` (with the (0, 0)
    origin as the bottom anchor).

    Used only to ENGINEER an input move of a known size; every assertion below then checks the
    REPORTED number against a literal (1.0 / 20.0 / 65.0 ...), never against a re-derivation
    of the curve, so the oracle stays the threshold table itself."""
    pts = [(0.0, 0.0)] + [(float(thr[p]), float(p)) for p in sorted(thr)]
    (d_lo, p_lo), (d_hi, p_hi) = next(
        (q for q in zip(pts, pts[1:]) if percent <= q[1][1]), (pts[-2], pts[-1]))
    return d_lo + (d_hi - d_lo) * (percent - p_lo) / (p_hi - p_lo)


def test_stop_percentiles_are_the_expected_contract():
    # Pin the anchor contract the whole section's oracle rests on: the threshold dict's KEY IS
    # the percentile -- 65/85/95 for the marks and a REAL 100 (WG returns a finite 100th-
    # percentile damage, so the estimator's 99 goalpost substitution is not used here).
    assert _STOPS == ((65, 65.0), (85, 85.0), (95, 95.0), (100, 100.0))


# --- #1 THE ORACLE-EQUIVALENCE TEST (the highest-value assertion here) -------
# The shipped map must agree with the independent reference EVERYWHERE, not just at the anchors:
# swept over the edges, every anchor, and dense off-anchor points, on both an 8-anchor table and
# a legacy-four-only one. This is what pins the confirmed finding into the suite.

def _sweep(thr):
    """Every damage worth probing on `thr`: 0/negatives, each anchor and its +-1 neighbours,
    dense interior samples, and well past the top anchor."""
    top = max(thr.values())
    points = [-1000, -1, 0, 1]
    for d in thr.values():
        points += [d - 1, d, d + 1]
    points += [int(top * i / 97.0) for i in range(98)]          # dense, prime-ish stride
    points += [top + 1, top + 500, top * 2, top * 10, 999999]
    return sorted(set(points))


@pytest.mark.parametrize("thr", [
    _REAL_8_54657,                                       # all 8 anchors (the current fetch)
    _REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705,   # legacy-four-only live EU shapes
    {65: 300, 85: 420, 95: 500, 100: 560},               # tiny damages (low tier)
    {65: 4000, 85: 4100, 95: 4150, 100: 4180},           # very flat / compressed spread
    {65: 1000, 85: 4000, 95: 7000, 100: 9000},           # very steep spread
    _THR,                                                # the round-number fixture
], ids=["eight_54657", "real_7281", "real_51537", "real_17217", "real_26705",
        "tiny", "flat", "steep", "round"])
def test_shipped_map_agrees_with_the_independent_reference(thr):
    fit = _fit_from_thresholds(thr)
    assert fit is not None
    for d in _sweep(thr):
        assert _smooth_percent(d, fit) == pytest.approx(_reference_percent(d, thr), abs=1e-9), \
            "shipped map diverged from the validated reference at d=%d" % d


def test_the_reference_is_not_a_restatement_of_the_shipped_map():
    # Guard the oracle itself: the reference must be able to DISAGREE. Feed the shipped map a fit
    # built from a DIFFERENT table and the two must part company -- otherwise the test above
    # would pass against any implementation.
    fit = _fit_from_thresholds(_REAL_7281)
    assert _smooth_percent(3000, fit) != pytest.approx(
        _reference_percent(3000, _REAL_51537), abs=1e-6)


def test_the_enrichment_anchors_actually_change_the_low_end():
    # The 20/40/55/75 anchors are not decoration: below the 65th they are the ONLY thing between
    # a straight chord from the origin and WG's real curve. Pin that dropping them MOVES the
    # answer materially, so an accidental "legacy four only" regression cannot pass silently.
    legacy = dict((p, _REAL_8_54657[p]) for p in (65, 85, 95, 100))
    enriched = _smooth_percent(1000, _fit_from_thresholds(_REAL_8_54657))
    chord = _smooth_percent(1000, _fit_from_thresholds(legacy))
    assert enriched == pytest.approx(_reference_percent(1000, _REAL_8_54657), abs=1e-9)
    assert abs(enriched - chord) > 1.0


# --- #2 EXACTNESS AT EVERY ANCHOR + the fixed spans between them -------------

@pytest.mark.parametrize("thr", [
    _REAL_8_54657, _REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705, _THR,
    {65: 300, 85: 420, 95: 500, 100: 560},
    {65: 4000, 85: 4100, 95: 4150, 100: 4180},
    {65: 1000, 85: 4000, 95: 7000, 100: 9000},
], ids=["eight_54657", "real_7281", "real_51537", "real_17217", "real_26705", "round",
        "tiny", "flat", "steep"])
def test_curve_is_exact_at_every_anchor(thr):
    # THE acceptance criterion: the map passes through EVERY anchor WG gave us, all 8 when 8 are
    # present. The percentile IS the key, so this is a fixed-point property with no tolerance
    # story -- 1e-9, i.e. float noise only.
    fit = _fit_from_thresholds(thr)
    assert fit is not None
    for percent in sorted(thr):
        assert _smooth_percent(thr[percent], fit) == pytest.approx(float(percent), abs=1e-9), \
            "anchor D%s must map to %s exactly" % (percent, percent)


@pytest.mark.parametrize("thr", [_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705],
                         ids=["7281", "51537", "17217", "26705"])
def test_anchor_to_anchor_span_is_exact(thr):
    # The span BETWEEN two anchors is fixed by the percentile keys alone (65->85 is 20 points,
    # whatever the tank), so it is a fully table-independent oracle for the map's SLOPE -- the
    # half of the old bug the pre_percentile anchor could not cancel.
    fit = _fit_from_thresholds(thr)
    assert _smooth_percent(thr[85], fit) - _smooth_percent(thr[65], fit) \
        == pytest.approx(20.0, abs=1e-9)
    assert _smooth_percent(thr[95], fit) - _smooth_percent(thr[85], fit) \
        == pytest.approx(10.0, abs=1e-9)
    assert _smooth_percent(thr[100], fit) - _smooth_percent(thr[95], fit) \
        == pytest.approx(5.0, abs=1e-9)


def test_the_origin_stop_is_prepended_to_the_fit():
    # The (0 damage, 0 percent) origin is IMPLICIT in WG's table and EXPLICIT in the fit -- it is
    # what makes the sub-lowest-anchor region a real interpolation instead of an extrapolation
    # (where the old normal fit lost up to 11.9pp).
    fit = _fit_from_thresholds(_REAL_8_54657)
    assert fit[0] == (0.0, 0.0)
    assert fit == [(0.0, 0.0)] + [(float(_REAL_8_54657[p]), float(p))
                                  for p in sorted(_REAL_8_54657)]


# --- #3 REAL-WORLD REGRESSION PINS (the confirmed back-test numbers) ---------
# Straight from the 118-battle back-test against WG's own logged damageRating. A future retune
# that breaks the finding breaks THESE. pytest.approx, never exact float equality -- the map is
# float arithmetic on ints (0.35*12 == 4.199999999999999 is why).

@pytest.mark.parametrize("thr,avg,expected,wg_logged", [
    # int_cd 54657, the live EU 8-anchor table. Both averages sit BELOW the lowest anchor (D20),
    # i.e. on the origin segment -- exactly the region the old normal fit got worst.
    (_REAL_8_54657, 30, 1.136, 1.14),
    (_REAL_8_54657, 70, 2.65, 2.64),
    # int_cd 69153, between its 75th and 85th anchors. Only the bracketing pair can affect the
    # answer, so the two anchors below/above are omitted rather than invented.
    ({65: 2561, 75: 3043, 85: 3661}, 3192, 77.41, 77.37),
    ({65: 2561, 75: 3043, 85: 3661}, 3179, 77.20, None),
], ids=["54657_avg30", "54657_avg70", "69153_avg3192", "69153_avg3179"])
def test_backtested_percentiles_match_wgs_own_damage_rating(thr, avg, expected, wg_logged):
    got = _smooth_percent(avg, _fit_from_thresholds(thr))
    assert got == pytest.approx(expected, abs=0.005)
    if wg_logged is not None:
        # ...and within the back-test's measured error envelope of WG's OWN logged number
        # (mean +0.047pp, stdev 0.088, max 0.238 over 118 battles).
        assert got == pytest.approx(wg_logged, abs=0.24)


# --- #4 monotonicity + continuity across the segment boundaries --------------

@pytest.mark.parametrize("thr", _ALL_REAL + (_THR,),
                         ids=["7281", "51537", "17217", "26705", "eight_54657", "round"])
def test_curve_is_monotone_and_continuous_across_segment_boundaries(thr):
    # The piecewise map has a slope KINK at every anchor, so prove the VALUE has no discontinuity
    # there: it must never decrease as damage rises, including stepping across an anchor by 1.
    fit = _fit_from_thresholds(thr)
    prev = -1.0
    for d in range(1, int(thr[100]) + 400):
        cur = _smooth_percent(d, fit)
        assert cur >= prev, "curve decreased at d=%d" % d
        prev = cur
    # Continuity AT each interior anchor: the two sides of the kink meet on the anchor's own
    # percentile, so a +-1 damage step around it is a tiny step, never a jump.
    for percent in sorted(thr)[:-1]:
        d = int(thr[percent])
        assert _smooth_percent(d, fit) == pytest.approx(float(percent), abs=1e-9)
        assert _smooth_percent(d + 1, fit) - percent < 0.1
        assert percent - _smooth_percent(d - 1, fit) < 0.1


# --- #5 the two ends (the origin segment, and flat above the top anchor) -----

@pytest.mark.parametrize("thr", _ALL_REAL,
                         ids=["7281", "51537", "17217", "26705", "eight_54657"])
def test_no_damage_is_exactly_zero_percent(thr):
    # The origin stop makes 0 damage exactly 0 percent -- and anything at or below it too.
    fit = _fit_from_thresholds(thr)
    assert _smooth_percent(0, fit) == 0.0
    assert _smooth_percent(-1, fit) == 0.0
    assert _smooth_percent(-99999, fit) == 0.0
    assert _smooth_percent(None, fit) == 0.0


@pytest.mark.parametrize("thr", _ALL_REAL,
                         ids=["7281", "51537", "17217", "26705", "eight_54657"])
def test_nan_damage_reads_as_zero_percent(thr):
    # LOAD-BEARING: NaN compares False against every segment test, so an unguarded map would fall
    # through and report the TOP percentile. _clamp maps it to the low bound instead.
    fit = _fit_from_thresholds(thr)
    assert _smooth_percent(float("nan"), fit) == 0.0


@pytest.mark.parametrize("thr", _ALL_REAL,
                         ids=["7281", "51537", "17217", "26705", "eight_54657"])
def test_below_the_lowest_anchor_interpolates_from_the_origin(thr):
    # Not a clamp and not an extrapolation: a strictly increasing straight line from (0, 0) to
    # the lowest anchor, staying inside [0, that anchor's percentile).
    fit = _fit_from_thresholds(thr)
    lowest = min(thr)
    prev = -1.0
    for d in range(0, int(thr[lowest]), 25):
        cur = _smooth_percent(d, fit)
        assert 0.0 <= cur < float(lowest)
        assert cur > prev or d == 0
        prev = cur
    # Half-way to the lowest anchor is half its percentile -- the segment is a straight chord.
    assert _smooth_percent(thr[lowest] / 2.0, fit) == pytest.approx(lowest / 2.0, abs=1e-9)


@pytest.mark.parametrize("thr", _ALL_REAL,
                         ids=["7281", "51537", "17217", "26705", "eight_54657"])
def test_above_the_top_anchor_is_flat(thr):
    # WG's table ENDS at the 100th percentile, so there is nothing left to extrapolate into: the
    # map pins at the top anchor's percentile and stays there. (The superseded normal fit kept
    # climbing an asymptote here.)
    fit = _fit_from_thresholds(thr)
    d100 = int(thr[100])
    assert _smooth_percent(d100, fit) == pytest.approx(100.0, abs=1e-9)
    for d in (d100 + 1, d100 + 25, d100 + 1200, d100 * 3, 999999):
        assert _smooth_percent(d, fit) == 100.0, "top anchor must be flat, not climbing, at %d" % d


def test_a_table_topping_out_below_100_is_flat_at_its_own_top_percentile():
    # Missing the 100 anchor: flat at 95, NOT extended to 100 -- the map never invents percentile
    # WG did not give it.
    thr = dict((p, _REAL_8_54657[p]) for p in (20, 40, 55, 65, 75, 85, 95))
    fit = _fit_from_thresholds(thr)
    assert _smooth_percent(thr[95], fit) == pytest.approx(95.0, abs=1e-9)
    assert _smooth_percent(thr[95] * 4, fit) == 95.0


# --- #6 degenerate threshold tables -> None -> has_data False ----------------
# The rule is now per-STOP, not per-table: an offending anchor (`d <= 0`, or `d <=` the last kept
# damage) is dropped on its own and the rest survive. None only when NO real anchor survives, so
# this list is much shorter than the piecewise-normal fit's was -- a single usable anchor is a
# fit now (origin + that anchor = one segment), where the old code needed two real stops.

@pytest.mark.parametrize("thr", [
    {},                                                  # empty
    None,                                                # missing entirely
    [],                                                  # non-dict, empty
    [1000, 2000, 3000],                                  # non-dict, list
    (1000, 2000),                                        # non-dict, tuple
    "2807",                                              # non-dict, string
    42,                                                  # non-dict, scalar
    {65: "abc", 85: 2000, 95: 3000, 100: 4000},          # non-numeric value
    {65: [1], 85: 2000, 95: 3000, 100: 4000},            # non-coercible value
    {65: float("nan"), 85: 2000, 95: 3000, 100: 4000},   # NaN value
    {65: None, 85: None, 95: None, 100: None},           # all None
    {65: 0, 85: 0, 95: 0, 100: 0},                       # all zero
    {65: 0, 85: -5, 95: -10, 100: -20},                  # zero / negative damages
], ids=["empty", "none", "list_empty", "list", "tuple", "string", "scalar", "value_str",
        "value_list", "value_nan", "values_none", "all_zero", "negative"])
def test_fit_from_thresholds_none_when_no_anchor_survives(thr):
    assert _fit_from_thresholds(thr) is None


@pytest.mark.parametrize("thr", [
    {},
    None,
    [1000, 2000, 3000],
    {65: "abc", 85: 2000, 95: 3000, 100: 4000},
    {65: 0, 85: -5, 95: -10, 100: -20},
], ids=["empty", "none", "list", "value_str", "negative"])
def test_unusable_table_degrades_to_no_percent(thr):
    # Every unusable table must land on the has_data False path -- no percent, no crash -- while
    # the raw live damage metrics stay meaningful.
    m = build_battle_model(_bsnap(thresholds=thr))
    assert m.has_data is False
    assert m.cur_percent == 0.0
    assert m.pct_delta == 0.0
    assert m.combined_damage == 2500


@pytest.mark.parametrize("thr,kept", [
    ({65: 2807, 85: 0, 95: 0, 100: 0}, (65,)),           # ONE usable anchor -> still a fit
    ({65: 2000, 85: 2000, 95: 2000, 100: 2000}, (65,)),  # all equal -> only the first survives
    ({65: 3000, 85: 2000, 95: 1000, 100: 500}, (65,)),   # fully descending -> only the first
    ({65: 2807, 85: 3898, 95: 0, 100: 0}, (65, 85)),     # the two lower mark anchors
    ({65: 0, 85: 3898, 95: 0, 100: 5426}, (85, 100)),    # D85 + the goalpost
    ({65: 2807, 85: 0, 95: 0, 100: 5426}, (65, 100)),    # D65 + the goalpost, widest segment
    ({65: 0, 85: 0, 95: 4749, 100: 5426}, (95, 100)),    # top pair only
], ids=["one_anchor", "all_equal", "descending", "marks_65_85", "d85_goalpost",
        "d65_goalpost", "top_pair"])
def test_a_single_surviving_anchor_still_fits_and_stays_exact(thr, kept):
    # ONE strictly-positive anchor is the minimum: origin + it = one usable segment. The fit must
    # succeed (not degrade) and stay exact at every survivor.
    fit = _fit_from_thresholds(thr)
    assert fit is not None
    assert [int(d) for d, _p in fit] == [0] + [int(thr[p]) for p in kept]
    for percent in kept:
        assert _smooth_percent(thr[percent], fit) == pytest.approx(float(percent), abs=1e-9)
    assert build_battle_model(_bsnap(thresholds=thr)).has_data is True


@pytest.mark.parametrize("thr,kept,dropped", [
    ({65: 2807, 85: 3898, 95: 3000, 100: 5426}, (65, 85, 100), 95),   # D95 below D85
    ({65: 2807, 85: 3898, 95: 3898, 100: 5426}, (65, 85, 100), 95),   # D95 EQUAL to D85
    ({65: 2807, 85: 1000, 95: 4749, 100: 5426}, (65, 95, 100), 85),   # D85 dips mid-table
    ({65: 2807, 85: 3898, 95: 4749, 100: 3000}, (65, 85, 95), 100),   # goalpost below D95
    # An enrichment anchor is dropped the same way -- it costs low-end resolution, nothing more.
    (_with(_REAL_8_54657, {40: 400}), (20, 55, 65, 75, 85, 95, 100), 40),
], ids=["d95_below_d85", "d95_equals_d85", "d85_dips", "goalpost_below_d95", "enrich_40_dips"])
def test_one_non_monotone_anchor_is_dropped_individually(thr, kept, dropped):
    # A single garbage anchor must be DROPPED ALONE, not poison the table: the fit keeps the
    # strictly-increasing survivors (so has_data stays True) and is still EXACT at each of them.
    # The dropped anchor's damage must NOT read as its nominal percentile -- it was rejected, so
    # the curve owes it nothing.
    fit = _fit_from_thresholds(thr)
    assert fit is not None
    assert [int(d) for d, _p in fit] == [0] + [int(thr[p]) for p in kept]
    for percent in kept:
        assert _smooth_percent(thr[percent], fit) == pytest.approx(float(percent), abs=1e-9)
    assert _smooth_percent(thr[dropped], fit) != pytest.approx(float(dropped), abs=1e-6)
    assert build_battle_model(_bsnap(thresholds=thr)).has_data is True


def test_fit_from_thresholds_robust_to_missing_goalpost():
    # A table missing the D100 goalpost still fits from the three mark anchors -- and stays exact
    # at each of them.
    thr = dict((p, _THR[p]) for p in (65, 85, 95))
    fit = _fit_from_thresholds(thr)
    assert fit is not None and len(fit) == 4        # origin + three anchors
    for percent in (65, 85, 95):
        assert _smooth_percent(thr[percent], fit) == pytest.approx(float(percent), abs=1e-9)


def test_a_mark_count_keyed_table_is_not_silently_reinterpreted():
    # THE hazard of the percentile re-key: a stale v3 cache row keyed by MARK COUNT reads as
    # percentiles 1/2/3, i.e. D65 would map to the 1st percentile. moe_wgapi's _STORE_VERSION
    # bump is what prevents such a row from ever reaching here (tests/test_moe_wgapi.py); pin the
    # consequence so nobody "fixes" the domain by re-admitting mark keys.
    fit = _fit_from_thresholds({1: 2807, 2: 3898, 3: 4749, 100: 5426})
    assert _smooth_percent(2807, fit) == pytest.approx(1.0, abs=1e-9)   # NOT 65.0 -- garbage in
    assert _smooth_percent(2807, _fit_from_thresholds(_REAL_7281)) == pytest.approx(65.0, abs=1e-9)


# --- ewma_project ------------------------------------------------------------

def test_ewma_project_folds_cd_toward_average():
    # prev + k*(cd-prev); k = 2/101. Above-average battle nudges the average up.
    assert ewma_project(2000, 3000) == int(round(2000 + EWMA_K * 1000))   # 2020
    # Below-average battle nudges it down.
    assert ewma_project(2000, 1000) == int(round(2000 + EWMA_K * -1000))  # 1980


def test_ewma_project_honors_explicit_k():
    # An explicit k overrides the community default: prev + k*(cd-prev) with k=0.04.
    assert ewma_project(2000, 3000, 0.04) == int(round(2000 + 0.04 * 1000))   # 2040


def test_ewma_project_new_tank_zero_baseline():
    assert ewma_project(0, 3000) == int(round(EWMA_K * 3000))             # 59


def test_ewma_project_zero_cd_folds_below_baseline():
    # A 0-damage battle-so-far IS folded: proj = prev*(1-k), the honest 'if it ended now'
    # projection that opens just below career and climbs as damage accrues.
    assert ewma_project(1800, 0) == int(round(1800 * (1 - EWMA_K)))       # 1764
    assert ewma_project(2000, 0) == int(round(2000 * (1 - EWMA_K)))       # 1960
    assert ewma_project(0, 0) == 0


# --- build_battle_model ------------------------------------------------------

def test_build_battle_model_four_metrics():
    m = build_battle_model(_bsnap())
    # 1) live combined damage: 2000 + max(500,300) - 0
    assert m.combined_damage == 2500
    # 2) projected average: 1800 + k*(2500-1800)
    assert m.proj_avg_damage == int(round(1800 + EWMA_K * 700))           # 1814
    # 3) current percent is UN-ANCHORED: f(proj) directly, no pre_percentile stamp involved
    # (see build_battle_model's comment for why the anchor was dropped).
    fit = _fit_from_thresholds(_THR)
    f_proj = _smooth_percent(m.proj_avg_damage, fit)
    f_pre_avg = _smooth_percent(1800, fit)
    assert f_proj > f_pre_avg                                             # above-avg battle
    assert m.cur_percent == pytest.approx(f_proj, abs=1e-9)
    assert m.cur_percent > f_pre_avg
    # 4) delta measures gain from WG's stamped career standing pre_percentile (70.0 here), NOT
    # from our reconstruction f(pre_avg) -- see build_battle_model's comment on why the anchor
    # moved off the reconstruction.
    assert m.pct_delta == pytest.approx(f_proj - 70.0, abs=1e-9)
    assert m.has_data is True


# --- REPORTED-DELTA FIDELITY (the user-facing symptom) -----------------------
# A move that is genuinely +1.0 percentile points on the tank's curve must be REPORTED as +1.0,
# not inflated. The superseded piecewise-normal fit displayed the same move as +1.27 just above 1
# mark (~+27% overstated) and shrank it to +0.65 near the goalpost, because the pre_percentile
# anchor cancels a fit's LEVEL bias but not its SLOPE bias.
#
# The move is ENGINEERED from the threshold table (via _damage_at_percent) and the assertion is
# against the literal 1.0. Tolerance 0.03: build_battle_model rounds the EWMA projection to a
# whole damage value, and up to 0.5 damage of rounding is worth ~0.02 percentile points on the
# steepest (lowest) segment of these tables.

@pytest.mark.parametrize("thr", [_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705],
                         ids=["7281", "51537", "17217", "26705"])
@pytest.mark.parametrize("band", [65.5, 66.0, 70.0, 80.0, 88.0, 96.0])
def test_reported_delta_matches_a_true_one_point_move(thr, band):
    # Career sits at `band`; engineer this battle's combined damage so the EWMA projection lands
    # exactly one percentile point higher on the curve.
    d0 = int(round(_damage_at_percent(thr, band)))
    d1 = _damage_at_percent(thr, band + 1.0)
    cd = int(round(d0 + (d1 - d0) / EWMA_K))        # invert the EWMA fold: proj -> required CD
    m = build_battle_model(_bsnap(damage=cd, assist=0, stun=0, team_damage=0,
                                  pre_avg_damage=d0, pre_percentile=band, thresholds=thr))
    assert m.proj_avg_damage == pytest.approx(d1, abs=1.0)      # the move landed as engineered
    assert m.pct_delta == pytest.approx(1.0, abs=0.03)
    # ...and the anchored readout is the career standing plus exactly that move.
    assert m.cur_percent == pytest.approx(band + 1.0, abs=0.03)


@pytest.mark.parametrize("thr", [_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705],
                         ids=["7281", "51537", "17217", "26705"])
def test_reported_delta_for_a_one_mark_to_two_mark_move(thr):
    # The largest table-fixed move there is: career sitting exactly ON the 1-mark anchor,
    # projecting exactly ONTO the 2-mark anchor, must report the span the percentile keys define
    # -- 85-65 = 20.0 points. The superseded normal fit reported ~24.8 here.
    d0, d1 = int(thr[65]), int(thr[85])
    cd = int(round(d0 + (d1 - d0) / EWMA_K))
    m = build_battle_model(_bsnap(damage=cd, assist=0, stun=0, team_damage=0,
                                  pre_avg_damage=d0, pre_percentile=65.0, thresholds=thr))
    assert m.proj_avg_damage == pytest.approx(d1, abs=1.0)
    assert m.pct_delta == pytest.approx(20.0, abs=0.03)


@pytest.mark.parametrize("thr", [_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705],
                         ids=["7281", "51537", "17217", "26705"])
def test_reported_delta_is_symmetric_for_a_losing_move(thr):
    # The same fidelity in the other direction: a projection engineered exactly 0.5 points BELOW
    # career must report -0.5, so a bad battle is not overstated either.
    #
    # 0.5, not 1.0: a single battle's downward reach is CAPPED at proj = prev*(1-k) (combined
    # damage clamps at 0), i.e. k*prev damage ~= 0.9 percentile points on these tables -- a
    # 1.0-point losing move is physically unreachable in one battle, so engineering one would
    # silently clip against `max(cd, 0)` and test nothing. The cap itself is pinned below.
    band = 70.0
    d0 = int(round(_damage_at_percent(thr, band)))
    d1 = _damage_at_percent(thr, band - 0.5)
    cd = int(round(d0 + (d1 - d0) / EWMA_K))
    assert cd > 0, "the engineered move must be reachable, not clipped at zero damage"
    m = build_battle_model(_bsnap(damage=cd, assist=0, stun=0, team_damage=0,
                                  pre_avg_damage=d0, pre_percentile=band, thresholds=thr))
    assert m.pct_delta == pytest.approx(-0.5, abs=0.03)
    assert m.cur_percent == pytest.approx(band - 0.5, abs=0.03)


@pytest.mark.parametrize("thr", [_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705],
                         ids=["7281", "51537", "17217", "26705"])
def test_the_worst_possible_battle_is_capped_by_one_ewma_step(thr):
    # The floor on a single battle's damage: combined damage clamps at 0, so proj can fall no
    # further than prev*(1-k) -- about one and a bit percentile points at the 70th on these
    # tables, never an alarming plunge. Checked against the INDEPENDENT reference, so this pins
    # the value rather than restating the implementation. The floor is measured from the
    # WG-stamped `band` (pre_percentile) now, not from the reconstruction f(d0).
    band = 70.0
    d0 = int(round(_damage_at_percent(thr, band)))
    m = build_battle_model(_bsnap(damage=0, assist=0, stun=0, team_damage=0,
                                  pre_avg_damage=d0, pre_percentile=band, thresholds=thr))
    floor = _reference_percent(int(round(d0 * (1 - EWMA_K))), thr) - band
    assert m.pct_delta == pytest.approx(floor, abs=1e-9)
    assert -2.0 < m.pct_delta < 0.0
    # ...and nothing can beat that floor: an even "worse" battle cannot exist (cd is clamped).
    assert build_battle_model(_bsnap(damage=0, assist=0, stun=0, team_damage=9999,
                                     pre_avg_damage=d0, pre_percentile=band,
                                     thresholds=thr)).pct_delta == pytest.approx(floor, abs=1e-9)


# --- THE UN-ANCHORING CONTRACT (see build_battle_model's comment) -----------
# cur_percent is f(proj) directly, UN-ANCHORED (unchanged). pct_delta now measures gain from
# WG's REAL stamped career standing pre_percentile, not from our reconstruction f(pre_avg) --
# measuring from f(pre_avg) folded in the reconstruction offset f(pre_avg) - pre_percentile,
# which flips sign per tank and disagreed with lebwa. The consequence: cur_percent - pct_delta
# == pre_percentile (WG's own stamp), NOT f(pre_avg) any more -- these tests pin exactly that,
# and go RED against the superseded `f(proj) - f(pre_avg)` delta.

def test_build_battle_model_cur_percent_minus_delta_equals_pre_percentile():
    # THE core consistency invariant of the new contract: subtracting pct_delta back out of
    # cur_percent must land on WG's stamped pre_percentile (70.0) -- NOT on our reconstruction
    # f(pre_avg) (_THR maps 1800 damage to 81.0, deliberately different from 70.0 so this bites).
    # Against the superseded `f(proj) - f(pre_avg)` delta this reduces to f(pre_avg) (81.0) and
    # fails.
    m = build_battle_model(_bsnap())
    fit = _fit_from_thresholds(_THR)
    f_pre_avg = _smooth_percent(1800, fit)
    assert f_pre_avg != pytest.approx(70.0, abs=0.5)   # sanity: reconstruction really disagrees
    assert m.cur_percent - m.pct_delta == pytest.approx(70.0, abs=1e-9)


def test_build_battle_model_cur_percent_matches_reconstruction_at_proj():
    # The end-of-battle number IS f(proj) -- exactly, not approximately, since both sides are the
    # SAME computation with no anchor arithmetic in between.
    m = build_battle_model(_bsnap())
    fit = _fit_from_thresholds(_THR)
    assert m.cur_percent == _smooth_percent(m.proj_avg_damage, fit)


def test_build_battle_model_pct_delta_is_the_gain_from_pre_percentile():
    # The delta measures gain from WG's REAL stamped career standing pre_percentile
    # (getDamageRating) -- NOT from our reconstruction f(pre_avg), which flips sign per tank and
    # disagreed with lebwa (see build_battle_model's comment).
    m = build_battle_model(_bsnap())
    fit = _fit_from_thresholds(_THR)
    expected = _smooth_percent(m.proj_avg_damage, fit) - 70.0
    assert m.pct_delta == pytest.approx(expected, abs=1e-9)


def test_build_battle_model_projects_with_baked_k():
    # The projection uses the baked community EWMA_K default.
    m = build_battle_model(_bsnap())
    assert m.proj_avg_damage == int(round(1800 + EWMA_K * (2500 - 1800)))      # 1814


def test_build_battle_model_cur_percent_equals_fit_when_proj_equals_pre_avg():
    # If this battle's combined damage equals the career average, the EWMA fold is a no-op
    # (proj == pre_avg), and, UN-ANCHORED, cur_percent sits on OUR reconstruction curve at
    # pre_avg (f(pre_avg)), NOT on WG's stamped pre_percentile (73.5 here is deliberately NOT
    # what the fit would say for 1800 damage, pinning that the stamp no longer drives cur_percent
    # at all). pct_delta, however, is NOT 0 here -- it still measures gain from WG's real stamp,
    # so at this no-op battle it is exactly the reconstruction offset f(pre_avg) - pre_percentile.
    fit = _fit_from_thresholds(_THR)
    f_pre_avg = _smooth_percent(1800, fit)
    assert f_pre_avg != pytest.approx(73.5, abs=0.5)   # sanity: the stamp really disagrees
    m = build_battle_model(_bsnap(damage=1800, assist=0, stun=0, team_damage=0,
                                  pre_avg_damage=1800, pre_percentile=73.5))
    assert m.combined_damage == 1800
    assert m.proj_avg_damage == 1800
    assert m.cur_percent == pytest.approx(f_pre_avg, abs=1e-9)
    assert m.pct_delta == pytest.approx(f_pre_avg - 73.5, abs=1e-9)


def test_build_battle_model_counted_assist_from_split():
    # The split feeds both the counted-assist row and combined damage: max(track, spot, stun),
    # NOT the merged spot+track sum. Here track 900 leads.
    m = build_battle_model(_bsnap(track_assist=900, spot_assist=400, stun=300, assist=1300))
    assert m.counted_assist == 900
    assert m.assist_kind == "track"
    assert m.combined_damage == 2000 + 900       # split max, not the merged 1300


def test_build_battle_model_counted_assist_stun_leads():
    m = build_battle_model(_bsnap(track_assist=100, spot_assist=200, stun=800, assist=300))
    assert m.counted_assist == 800
    assert m.assist_kind == "stun"


def test_build_battle_model_counted_assist_merged_fallback():
    # Split not delivered yet -> value falls back to the merged live assist + generic kind.
    m = build_battle_model(_bsnap(track_assist=0, spot_assist=0, stun=0, assist=600))
    assert m.counted_assist == 600
    assert m.assist_kind == "assist"
    assert m.combined_damage == 2000 + 600


def test_build_battle_model_zero_damage_drags_below_career():
    # No damage yet (cd=0) -> proj = prev*(1-k) < pre_avg -> f(proj) sits just below f(pre_avg)
    # (honest 'if it ended now'). cur_percent is f(proj) directly (UN-ANCHORED, unchanged); the
    # delta measures gain from WG's stamped pre_percentile (84.7, deliberately not on the curve),
    # i.e. f(proj) - 84.7, not f(proj) - f(pre_avg).
    m = build_battle_model(_bsnap(damage=0, assist=0, stun=0,
                                  pre_avg_damage=1800, pre_percentile=84.7))
    assert m.proj_avg_damage == int(round(1800 * (1 - EWMA_K)))           # 1764
    fit = _fit_from_thresholds(_THR)
    f_proj = _smooth_percent(m.proj_avg_damage, fit)
    f_pre_avg = _smooth_percent(1800, fit)
    assert f_proj < f_pre_avg                                             # 0-damage drags down
    assert m.cur_percent == pytest.approx(f_proj, abs=1e-9)
    assert m.cur_percent < f_pre_avg
    assert m.pct_delta == pytest.approx(f_proj - 84.7, abs=1e-9)


def test_build_battle_model_clamps_cur_percent_to_100():
    # UN-ANCHORED: the clamp no longer sees pre_percentile + increment -- it must clamp f(proj)
    # ITSELF. Engineer a monster battle whose projection lands past the top anchor (D100=4000 on
    # _THR), where f is flat at 100 anyway, so this also proves the clamp is not just riding the
    # fit's own flat top.
    m = build_battle_model(_bsnap(damage=200000, assist=0, stun=0,
                                  pre_avg_damage=1800, pre_percentile=1.0))
    assert m.proj_avg_damage > 4000                 # past the top anchor, unclamped input to f
    assert m.cur_percent == 100.0


def test_build_battle_model_nan_pre_percentile_clamps():
    # A NaN pre_percentile must be clamped to the low bound, not passed through: NaN compares
    # False against the clamp bounds, so the naive clamp would leak NaN into cur_percent.
    m = build_battle_model(_bsnap(pre_percentile=float("nan")))
    assert m.cur_percent == m.cur_percent  # not NaN
    assert 0.0 <= m.cur_percent <= 100.0


def test_build_battle_model_has_baseline_true_with_career_standing():
    # Normal garage->battle flow: a real baseline is present -> the projected metrics are valid.
    assert build_battle_model(_bsnap()).has_baseline is True
    # Either half of the baseline alone is enough.
    assert build_battle_model(_bsnap(pre_avg_damage=1800, pre_percentile=0.0)).has_baseline is True
    assert build_battle_model(_bsnap(pre_avg_damage=0, pre_percentile=70.0)).has_baseline is True


def test_build_battle_model_no_baseline_flags_empty_replay():
    # BUG B: replay / relogin straight into battle -> the garage dossier was never read, so
    # the baseline comes back empty AND the tank was never marked seen (baseline_known False).
    # The model must FLAG this (has_baseline False) so the overlay dashes out the collapsed
    # proj/percent/delta instead of showing garbage. The live combined damage stays meaningful.
    m = build_battle_model(_bsnap(pre_avg_damage=0, pre_percentile=0.0, baseline_known=False,
                                  damage=2000, assist=0, stun=0))
    assert m.has_baseline is False
    assert m.combined_damage == 2000            # live CD still correct + shown
    assert m.has_data is True                   # thresholds are fine; only the baseline is missing


def test_build_battle_model_has_baseline_when_first_battle_zero_career():
    # First-ever battle in a freshly-bought tank: pre_avg/pre_percentile are a GENUINE 0
    # (the garage read the tank this session -> baseline_known True). 0 is the true baseline,
    # so the projection is well-defined and must NOT dash: has_baseline True, and the live
    # percent climbs from ~0 as damage accrues.
    m = build_battle_model(_bsnap(pre_avg_damage=0, pre_percentile=0.0, baseline_known=True,
                                  damage=2000, assist=0, stun=0))
    assert m.has_baseline is True
    assert m.has_data is True
    # proj = ewma_project(0, cd) = k*cd > 0; cur_percent anchors on 0 and climbs.
    assert m.proj_avg_damage > 0
    assert m.cur_percent > 0.0
    assert m.pct_delta > 0.0


def test_build_battle_model_baseline_known_alone_is_enough():
    # Even with no live damage yet, a known-genuine-0 baseline still counts as a baseline
    # (the overlay shows a real 0.x% opening, not a dash).
    m = build_battle_model(_bsnap(pre_avg_damage=0, pre_percentile=0.0, baseline_known=True,
                                  damage=0, assist=0, stun=0))
    assert m.has_baseline is True


def test_build_battle_model_negative_delta():
    # a weak battle projects below standing -> negative increment -> cur_percent dips below
    # the anchored pre_percentile
    m = build_battle_model(_bsnap(damage=100, assist=0, stun=0, pre_percentile=90.0))
    assert m.pct_delta < 0
    assert m.cur_percent < 90.0


# --- battle_bar_visible ------------------------------------------------------

def test_battle_bar_visible_gates():
    assert battle_bar_visible(True, True) is True
    assert battle_bar_visible(False, True) is False    # not in combat yet
    assert battle_bar_visible(True, False) is False     # no player vehicle


def test_battle_bar_visible_hidden_while_spectating():
    # After death, spectating a teammate: identity/thresholds follow the observed vehicle
    # while the damage stats stay ours -> a nonsense readout. Hide it.
    assert battle_bar_visible(True, True, is_spectating=True) is False
    # Alive (controlling own vehicle) -> visible.
    assert battle_bar_visible(True, True, is_spectating=False) is True
    # Default arg preserves prior behavior (never wrongly hides when the flag is absent).
    assert battle_bar_visible(True, True) is True


def test_battle_bar_visible_hidden_while_scoreboard_open():
    # Any full-stats scoreboard overlay (Tab / personal missions / reserves) is open ->
    # hide the readout so it doesn't clutter the full-screen scoreboard. Hard override:
    # hides even an otherwise-visible, alive, in-combat readout.
    assert battle_bar_visible(True, True, overlay_open=True) is False
    # Closed (default) preserves prior behavior.
    assert battle_bar_visible(True, True, overlay_open=False) is True
    assert battle_bar_visible(True, True) is True


def test_battle_bar_visible_overlay_never_reveals_hidden_case():
    # A closed scoreboard must not flip an already-hidden case visible: no vehicle / not in
    # combat / spectating all stay hidden regardless of the overlay flag.
    assert battle_bar_visible(True, False, overlay_open=False) is False   # no vehicle
    assert battle_bar_visible(False, True, overlay_open=False) is False   # not in combat
    assert battle_bar_visible(True, True, is_spectating=True, overlay_open=False) is False


def test_battle_bar_visible_disabled_setting_hides():
    # "Battle Widget Enabled" off is a hard override: hides an otherwise-visible overlay.
    assert battle_bar_visible(True, True, enabled=False) is False
    # Default (enabled) preserves prior behavior.
    assert battle_bar_visible(True, True, enabled=True) is True
    assert battle_bar_visible(True, True) is True


# --- Alt-key visibility semantics (INVERTED) ---------------------------------
# New rule (base guards vehicle/combat/spectating/scoreboard held satisfied):
#   active == enabled and (alt_held if alt_mode else True)
#   - master off              -> never visible.
#   - master on, alt_mode on  -> visible ONLY while Alt held.
#   - master on, alt_mode off -> ALWAYS visible.
# The "Show on Alt Key" child no longer overrides the master; it now GATES an
# already-enabled overlay down to the Alt-held window.

@pytest.mark.parametrize("enabled,alt_mode,alt_held,expected", [
    # master off -> never visible, regardless of alt_mode / alt_held.
    (False, False, False, False),
    (False, False, True,  False),
    (False, True,  False, False),
    (False, True,  True,  False),
    # master on, alt_mode off -> ALWAYS visible (Alt irrelevant).
    (True,  False, False, True),
    (True,  False, True,  True),
    # master on, alt_mode on -> visible ONLY while Alt held.
    (True,  True,  False, False),
    (True,  True,  True,  True),
])
def test_battle_bar_visible_truth_table(enabled, alt_mode, alt_held, expected):
    # Base guards satisfied (in combat, own vehicle, not spectating, no scoreboard).
    assert battle_bar_visible(True, True, enabled=enabled, alt_mode=alt_mode,
                              alt_held=alt_held) is expected


def test_battle_bar_visible_alt_mode_follows_held():
    # Master on + Alt-peek on: the overlay tracks whether Alt is held (INVERTED semantics --
    # the Alt child now GATES the enabled overlay rather than overriding a disabled one).
    assert battle_bar_visible(True, True, enabled=True, alt_mode=True, alt_held=True) is True
    assert battle_bar_visible(True, True, enabled=True, alt_mode=True, alt_held=False) is False


def test_battle_bar_visible_master_off_never_shows_even_on_alt():
    # Master off is the hard gate: neither alt_mode nor a held Alt can reveal the overlay.
    assert battle_bar_visible(True, True, enabled=False, alt_mode=True, alt_held=True) is False
    assert battle_bar_visible(True, True, enabled=False, alt_mode=False, alt_held=True) is False


def test_battle_bar_visible_alt_mode_off_shows_at_all_times():
    # Master on + Alt-peek OFF -> shown at all times; a held Alt makes no difference.
    assert battle_bar_visible(True, True, enabled=True, alt_mode=False, alt_held=False) is True
    assert battle_bar_visible(True, True, enabled=True, alt_mode=False, alt_held=True) is True


def test_battle_bar_visible_alt_mode_still_respects_base_guards():
    # The base guards (vehicle/combat/spectating/scoreboard) override the Alt-held window too:
    # even with the overlay enabled + Alt held, a failing base guard keeps it hidden.
    assert battle_bar_visible(True, False, enabled=True, alt_mode=True, alt_held=True) is False
    assert battle_bar_visible(False, True, enabled=True, alt_mode=True, alt_held=True) is False
    assert battle_bar_visible(True, True, is_spectating=True,
                              enabled=True, alt_mode=True, alt_held=True) is False
    assert battle_bar_visible(True, True, overlay_open=True,
                              enabled=True, alt_mode=True, alt_held=True) is False
