# -*- coding: utf-8 -*-
"""Tests for the engine-free in-battle domain layer. Like test_builder.py these run on
Python 3 (no game engine) because domain/battle_builder imports zero game symbols -- the
in-battle MoE math is pure and unit-testable with the client closed."""
import pytest

from moe_calculator.domain import battle_types as bt
from moe_calculator.domain.battle_builder import (
    combined_damage, counted_assistance, ewma_project,
    build_battle_model, battle_bar_visible, _fit_from_thresholds, _smooth_percent)
from moe_calculator.domain.constants import EWMA_K, MARK_PERCENTS, GOALPOST_PERCENTILE
from moe_calculator.domain import moe_estimate as me


# A clean threshold set (round numbers) so interpolation asserts stay exact.
_THR = {1: 1000, 2: 2000, 3: 3000, 100: 4000}

# The four KNOWN points on every tank's combined-damage -> percentile curve, as
# (threshold key, percentile). This is the wire contract the fit must reproduce exactly.
_STOPS = tuple(zip((1, 2, 3, 100), [float(p) for p in MARK_PERCENTS + (GOALPOST_PERCENTILE,)]))

# Real per-tank EU tables, lifted verbatim from a live mods_data/14th_ua_moe/
# moe_wgapi_cache.json (keys are the vehicle int_cds). HARDCODED on purpose -- the test must
# never read that file or depend on this machine. WG's real distribution is NOT exactly
# normal, which is exactly why a single global OLS (mu, sigma) could not pass through all
# four stops (residuals D1 -3.1, D2 +1.6, D3 +0.9, D100 -0.25 points); these shapes are the
# regression fixtures for that bug -- a synthetic normal table is nearly collinear in z, so the
# broken OLS fit missed its stops by only ~0.02 points (verified), 150x too subtle to rely on.
_REAL_7281 = {1: 2807, 2: 3898, 3: 4749, 100: 5426}
_REAL_51537 = {1: 1721, 2: 2392, 3: 2914, 100: 3319}
_REAL_17217 = {1: 2521, 2: 3770, 3: 4793, 100: 5654}
_REAL_26705 = {1: 3312, 2: 4491, 3: 5405, 100: 6133}


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


# --- smooth curve (_fit_from_thresholds + _smooth_percent) -------------------

def _thr_from_normal(mu, sigma):
    """Build a {1,2,3,100} threshold table whose stops lie exactly on a normal(mu, sigma):
    D1@65th, D2@85th, D3@95th, D100@99th (the goalpost percentile the fit uses)."""
    return dict((key, int(round(mu + sigma * me.inv_norm_cdf(p / 100.0))))
                for key, p in _STOPS)


def _damage_at_percent(thr, percent):
    """The combined damage whose curve percent is `percent` -- the INVERSE of the piecewise
    curve, derived straight from the table's stop pair that brackets `percent`.

    Used only to ENGINEER an input move of a known size; every assertion below then checks the
    REPORTED number against a literal (1.0 / 20.0 / 65.0 ...), never against a re-derivation
    of the curve, so the oracle stays the threshold table itself."""
    pairs = [(thr[1], 65.0, thr[2], 85.0), (thr[2], 85.0, thr[3], 95.0),
             (thr[3], 95.0, thr[100], 99.0)]
    d_lo, p_lo, d_hi, p_hi = next((q for q in pairs if percent < q[3]), pairs[-1])
    z_lo, z_hi = me.inv_norm_cdf(p_lo / 100.0), me.inv_norm_cdf(p_hi / 100.0)
    sigma = (d_hi - d_lo) / (z_hi - z_lo)
    return (d_lo - sigma * z_lo) + sigma * me.inv_norm_cdf(percent / 100.0)


def test_stop_percentiles_are_the_expected_contract():
    # Pin the stop percentiles the whole section's oracle rests on: 1/2/3 marks at 65/85/95
    # and the goalpost at 99 (NOT 100 -- Phi^-1(1) is +infinity).
    assert _STOPS == ((1, 65.0), (2, 85.0), (3, 95.0), (100, 99.0))


# --- #1 EXACTNESS AT EVERY STOP (the regression guard) -----------------------
# THE acceptance criterion for the overstated-progress bug: the curve must pass through all
# four known stops. The old global 2-parameter OLS fit could not (4 stops, 2 free
# parameters), leaving a sign-identical residual pattern on every live tank -- the 1-mark stop
# read ~61.9% instead of 65% and the slope just above a mark was ~26% too steep, which the
# pre_percentile anchor cancels only in LEVEL, not in SLOPE.
#
# Tolerance note: 1e-6 percentile points, not 1e-9. The floor here is NOT the fit (which is
# algebraically exact) but the inv_norm_cdf (Acklam rational approx) -> norm_cdf (erfc)
# round trip, whose residual is ~3e-8 points. That is still ~1e8x tighter than the bug's
# ~3-point bias, so this catches any regression of it instantly.

@pytest.mark.parametrize("thr", [
    _REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705,   # live EU shapes (non-normal)
    _thr_from_normal(1500.0, 800.0),                     # synthetic normal
    _thr_from_normal(3000.0, 2400.0),                    # wide (high-tier heavy-ish)
    {1: 300, 2: 420, 3: 500, 100: 560},                  # tiny damages (low tier)
    {1: 4000, 2: 4100, 3: 4150, 100: 4180},              # very flat / compressed spread
    {1: 1000, 2: 4000, 3: 7000, 100: 9000},              # very steep spread
    _THR,                                                # the round-number fixture
], ids=["real_7281", "real_51537", "real_17217", "real_26705", "normal_1500_800",
        "normal_3000_2400", "tiny", "flat", "steep", "round"])
def test_curve_is_exact_at_every_stop(thr):
    fit = _fit_from_thresholds(thr)
    assert fit is not None
    for key, percent in _STOPS:
        assert _smooth_percent(thr[key], fit) == pytest.approx(percent, abs=1e-6), \
            "stop D%s must map to %.1f exactly" % (key, percent)


@pytest.mark.parametrize("thr", [_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705],
                         ids=["7281", "51537", "17217", "26705"])
def test_stop_to_stop_span_is_exact(thr):
    # The span BETWEEN two stops is fixed by the table alone (65->85 is 20 points, whatever the
    # tank), so it is a fully table-independent oracle for the curve's SLOPE -- the half of the
    # bug the anchor could not cancel. The old OLS fit reported the 1->2 mark span as ~24.8
    # points instead of 20.0 (a ~24% overstatement, the user-visible symptom).
    fit = _fit_from_thresholds(thr)
    assert _smooth_percent(thr[2], fit) - _smooth_percent(thr[1], fit) \
        == pytest.approx(20.0, abs=1e-6)
    assert _smooth_percent(thr[3], fit) - _smooth_percent(thr[2], fit) \
        == pytest.approx(10.0, abs=1e-6)
    assert _smooth_percent(thr[100], fit) - _smooth_percent(thr[3], fit) \
        == pytest.approx(4.0, abs=1e-6)


def test_smooth_curve_tracks_true_percentile_off_mark():
    # At an off-mark damage the fitted normal curve recovers the true percentile closely
    # (the smooth fit is the sole percent path).
    mu, sigma = 1500.0, 800.0
    thr = _thr_from_normal(mu, sigma)
    d75 = int(round(mu + sigma * me.inv_norm_cdf(0.75)))    # true 75th percentile damage
    assert _smooth_percent(d75, _fit_from_thresholds(thr)) == pytest.approx(75.0, abs=1.0)


def test_synthetic_normal_table_recovers_the_whole_curve():
    # A table generated FROM a normal has collinear-in-z stops, so every segment's exact solve
    # recovers the SAME (mu, sigma) -- the piecewise curve degenerates to the single true
    # normal everywhere, not just at the stops. (Also documents why this shape alone cannot
    # detect the OLS bug: OLS is exact on collinear points too.)
    mu, sigma = 1500.0, 800.0
    fit = _fit_from_thresholds(_thr_from_normal(mu, sigma))
    for p in (0.30, 0.50, 0.70, 0.90, 0.97):
        d = mu + sigma * me.inv_norm_cdf(p)
        assert _smooth_percent(d, fit) == pytest.approx(100.0 * p, abs=0.05)


# --- #5 monotonicity + continuity across the segment boundaries --------------

@pytest.mark.parametrize("thr", [_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705, _THR],
                         ids=["7281", "51537", "17217", "26705", "round"])
def test_curve_is_monotone_and_continuous_across_segment_boundaries(thr):
    # The piecewise mapping has a slope KINK at each interior stop (each segment solves its own
    # sigma), so prove the VALUE has no discontinuity there: the curve must never decrease as
    # damage rises, including stepping across a stop by 1 damage.
    fit = _fit_from_thresholds(thr)
    prev = -1.0
    for d in range(1, int(thr[100]) + 400):
        cur = _smooth_percent(d, fit)
        assert cur >= prev, "curve decreased at d=%d" % d
        prev = cur
    # Continuity AT each interior boundary: the two sides of the kink meet on the stop's own
    # percentile, so a +-1 damage step around it is a tiny step, never a jump.
    for key, percent in _STOPS[:-1]:
        d = int(thr[key])
        assert _smooth_percent(d, fit) == pytest.approx(percent, abs=1e-6)
        assert _smooth_percent(d + 1, fit) - percent < 0.1
        assert percent - _smooth_percent(d - 1, fit) < 0.1


# --- #3 tails (below the lowest stop, above the highest) ---------------------

@pytest.mark.parametrize("thr", [_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705],
                         ids=["7281", "51537", "17217", "26705"])
def test_low_tail_is_monotone_and_in_range(thr):
    # Below D1 the lowest segment's curve is EXTENDED (no truncation, no special case): still a
    # real, strictly increasing percentile in [0, 65), never clamped flat to 0.
    fit = _fit_from_thresholds(thr)
    prev = -1.0
    for d in range(0, int(thr[1]), 25):
        cur = _smooth_percent(d, fit)
        assert 0.0 <= cur < 65.0
        assert cur > prev
        prev = cur
    assert _smooth_percent(0, fit) > 0.0          # a real low percentile, not a clamp artifact


@pytest.mark.parametrize("thr", [_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705],
                         ids=["7281", "51537", "17217", "26705"])
def test_high_tail_asymptotes_to_100_without_truncating_or_overshooting(thr):
    # Above the D100 goalpost the top segment is extended, so the curve keeps CLIMBING toward
    # 100 (not truncated at the 99 goalpost) and never exceeds it.
    fit = _fit_from_thresholds(thr)
    d100 = int(thr[100])
    assert _smooth_percent(d100, fit) == pytest.approx(99.0, abs=1e-6)
    prev = 99.0
    for d in range(d100 + 25, d100 + 1200, 25):
        cur = _smooth_percent(d, fit)
        assert cur > prev, "high tail must keep climbing at d=%d" % d   # not truncated at 99
        assert cur <= 100.0, "high tail overshot 100 at d=%d" % d
        prev = cur
    # Far out it saturates AT 100 and stays there -- never above, never wrapping back down.
    assert _smooth_percent(d100 * 3, fit) == pytest.approx(100.0, abs=1e-6)
    assert _smooth_percent(999999, fit) == 100.0


# --- #4 degenerate threshold tables -> None -> has_data False ----------------

@pytest.mark.parametrize("thr", [
    {},                                             # empty
    None,                                           # missing entirely
    [],                                             # non-dict, empty
    [1000, 2000, 3000],                             # non-dict, list
    (1000, 2000),                                   # non-dict, tuple
    "2807",                                         # non-dict, string
    42,                                             # non-dict, scalar
    {1: "abc", 2: 2000, 3: 3000, 100: 4000},        # non-numeric value
    {1: [1], 2: 2000, 3: 3000, 100: 4000},          # non-coercible value
    {1: float("nan"), 2: 2000, 3: 3000, 100: 4000},  # NaN value
    {1: None, 2: None, 3: None, 100: None},         # all None
    {1: 0, 2: 0, 3: 0, 100: 0},                     # all zero
    {1: 0, 2: -5, 3: -10, 100: -20},                # zero / negative damages
    {1: 2000, 2: 2000, 3: 2000, 100: 2000},         # all equal (no spread -> 1 usable stop)
    {1: 3000, 2: 2000, 3: 1000, 100: 500},          # non-monotone (descending)
    {1: 2807, 2: 0, 3: 0, 100: 0},                  # only ONE usable stop
], ids=["empty", "none", "list_empty", "list", "tuple", "string", "scalar", "value_str",
        "value_list", "value_nan", "values_none", "all_zero", "negative", "all_equal",
        "descending", "one_stop"])
def test_fit_from_thresholds_none_for_unusable_tables(thr):
    assert _fit_from_thresholds(thr) is None


@pytest.mark.parametrize("thr", [
    {},
    None,
    [1000, 2000, 3000],
    {1: "abc", 2: 2000, 3: 3000, 100: 4000},
    {1: 0, 2: -5, 3: -10, 100: -20},
    {1: 2000, 2: 2000, 3: 2000, 100: 2000},
    {1: 3000, 2: 2000, 3: 1000, 100: 500},
    {1: 2807, 2: 0, 3: 0, 100: 0},
], ids=["empty", "none", "list", "value_str", "negative", "all_equal", "descending",
        "one_stop"])
def test_unusable_table_degrades_to_no_percent(thr):
    # Every unusable table must land on the has_data False path -- no percent, no crash -- while
    # the raw live damage metrics stay meaningful.
    m = build_battle_model(_bsnap(thresholds=thr))
    assert m.has_data is False
    assert m.cur_percent == 0.0
    assert m.pct_delta == 0.0
    assert m.combined_damage == 2500


@pytest.mark.parametrize("thr,keys", [
    ({1: 2807, 2: 3898, 3: 0, 100: 0}, (1, 2)),        # only the two mark stops
    ({1: 0, 2: 3898, 3: 0, 100: 5426}, (2, 100)),      # D2 + the goalpost
    ({1: 2807, 2: 0, 3: 0, 100: 5426}, (1, 100)),      # D1 + the goalpost, widest segment
    ({1: 0, 2: 0, 3: 4749, 100: 5426}, (3, 100)),      # top pair only
], ids=["marks_1_2", "d2_goalpost", "d1_goalpost", "top_pair"])
def test_two_usable_stops_still_fit_and_stay_exact(thr, keys):
    # Two strictly-increasing stops are the MINIMUM the fit needs: it must succeed (not degrade)
    # and still reproduce both of them exactly -- a single segment extended in both directions.
    fit = _fit_from_thresholds(thr)
    assert fit is not None and len(fit) == 2
    percents = dict(_STOPS)
    for key in keys:
        assert _smooth_percent(thr[key], fit) == pytest.approx(percents[key], abs=1e-6)
    assert build_battle_model(_bsnap(thresholds=thr)).has_data is True


@pytest.mark.parametrize("thr,kept,dropped", [
    ({1: 2807, 2: 3898, 3: 3000, 100: 5426}, (1, 2, 100), 3),   # D3 below D2
    ({1: 2807, 2: 3898, 3: 3898, 100: 5426}, (1, 2, 100), 3),   # D3 EQUAL to D2 (no spread)
    ({1: 2807, 2: 1000, 3: 4749, 100: 5426}, (1, 3, 100), 2),   # D2 dips mid-table
    ({1: 2807, 2: 3898, 3: 4749, 100: 3000}, (1, 2, 3), 100),   # goalpost below D3
], ids=["d3_below_d2", "d3_equals_d2", "d2_dips", "goalpost_below_d3"])
def test_one_non_monotone_stop_is_dropped_not_the_whole_table(thr, kept, dropped):
    # A single garbage stop must be DROPPED, not poison the table: the fit keeps the strictly
    # increasing survivors (>= 2, so has_data stays True) and is still EXACT at each of them.
    # The dropped stop's damage must NOT read as its nominal percentile -- it was rejected, so
    # the curve owes it nothing.
    fit = _fit_from_thresholds(thr)
    assert fit is not None and len(fit) == len(kept)
    assert [int(d) for d, _z in fit] == [int(thr[k]) for k in kept]
    percents = dict(_STOPS)
    for key in kept:
        assert _smooth_percent(thr[key], fit) == pytest.approx(percents[key], abs=1e-6)
    assert _smooth_percent(thr[dropped], fit) != pytest.approx(percents[dropped], abs=1e-6)
    assert build_battle_model(_bsnap(thresholds=thr)).has_data is True


def test_fit_from_thresholds_robust_to_missing_goalpost():
    # A table missing the D100 goalpost (0) still fits from the 3 mark points -- and stays exact
    # at each of them.
    thr = _thr_from_normal(1500.0, 800.0)
    del thr[100]
    fit = _fit_from_thresholds(thr)
    assert fit is not None and len(fit) == 3
    for key, percent in _STOPS[:-1]:
        assert _smooth_percent(thr[key], fit) == pytest.approx(percent, abs=1e-6)


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
    # 3) current percent is ANCHORED: pre_percentile + this battle's SMOOTH-curve increment
    # (the primary path for a usable table; see _fit_from_thresholds).
    fit = _fit_from_thresholds(_THR)
    inc = _smooth_percent(m.proj_avg_damage, fit) - _smooth_percent(1800, fit)
    assert inc > 0                                                        # above-avg battle
    assert round(m.cur_percent, 2) == round(70.0 + inc, 2)
    assert m.cur_percent > 70.0
    # 4) delta IS the increment (self-consistent curve scale, not mixed vs WG rating)
    assert round(m.pct_delta, 2) == round(inc, 2)
    assert m.has_data is True


# --- #2 REPORTED-DELTA FIDELITY (the user-facing symptom) --------------------
# THE test that would have caught the bug: a move that is genuinely +1.0 percentile points on
# the tank's curve must be REPORTED as +1.0, not inflated. With the old global OLS fit the same
# move displayed as +1.27 just above 1 mark (~+27% overstated -- the reported "+1.0 shown as
# +1.265") and shrank to +0.65 near the goalpost, because the anchor cancels the fit's LEVEL
# bias but not its SLOPE bias.
#
# The move is ENGINEERED from the threshold table (via _damage_at_percent) and the assertion is
# against the literal 1.0. Tolerance 0.03: build_battle_model rounds the EWMA projection to a
# whole damage value, and up to 0.5 damage of rounding is worth ~0.01-0.02 percentile points.

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
    # The largest table-fixed move there is: career sitting exactly ON the 1-mark stop, projecting
    # exactly ONTO the 2-mark stop, must report the span the table itself defines -- 85-65 = 20.0
    # points. The old OLS fit reported ~24.8 here.
    d0, d1 = int(thr[1]), int(thr[2])
    cd = int(round(d0 + (d1 - d0) / EWMA_K))
    m = build_battle_model(_bsnap(damage=cd, assist=0, stun=0, team_damage=0,
                                  pre_avg_damage=d0, pre_percentile=65.0, thresholds=thr))
    assert m.proj_avg_damage == pytest.approx(d1, abs=1.0)
    assert m.pct_delta == pytest.approx(20.0, abs=0.03)


@pytest.mark.parametrize("thr", [_REAL_7281, _REAL_51537, _REAL_17217, _REAL_26705],
                         ids=["7281", "51537", "17217", "26705"])
def test_reported_delta_is_symmetric_for_a_losing_move(thr):
    # The same fidelity in the other direction: a projection engineered exactly 1.0 point BELOW
    # career must report -1.0, so a bad battle is not overstated either.
    band = 70.0
    d0 = int(round(_damage_at_percent(thr, band)))
    d1 = _damage_at_percent(thr, band - 1.0)
    cd = int(round(d0 + (d1 - d0) / EWMA_K))
    m = build_battle_model(_bsnap(damage=max(cd, 0), assist=0, stun=0, team_damage=0,
                                  pre_avg_damage=d0, pre_percentile=band, thresholds=thr))
    assert m.pct_delta == pytest.approx(-1.0, abs=0.03)
    assert m.cur_percent == pytest.approx(band - 1.0, abs=0.03)


def test_build_battle_model_projects_with_baked_k():
    # The projection uses the baked community EWMA_K default.
    m = build_battle_model(_bsnap())
    assert m.proj_avg_damage == int(round(1800 + EWMA_K * (2500 - 1800)))      # 1814


def test_build_battle_model_anchor_holds_when_proj_equals_pre_avg():
    # If this battle's combined damage equals the career average, the EWMA fold is a no-op
    # (proj == pre_avg), so the increment is exactly 0 and cur_percent sits ON WG's real
    # standing -- the anchor guarantee, independent of the curve's absolute value.
    m = build_battle_model(_bsnap(damage=1800, assist=0, stun=0, team_damage=0,
                                  pre_avg_damage=1800, pre_percentile=73.5))
    assert m.combined_damage == 1800
    assert m.proj_avg_damage == 1800
    assert m.pct_delta == pytest.approx(0.0, abs=1e-9)
    assert m.cur_percent == pytest.approx(73.5, abs=1e-9)


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
    # No damage yet (cd=0) -> proj = prev*(1-k) < pre_avg -> the folded 0-damage battle
    # drags the anchored percent just below WG's real number (honest 'if it ended now').
    m = build_battle_model(_bsnap(damage=0, assist=0, stun=0,
                                  pre_avg_damage=1800, pre_percentile=84.7))
    assert m.proj_avg_damage == int(round(1800 * (1 - EWMA_K)))           # 1764
    fit = _fit_from_thresholds(_THR)
    inc = _smooth_percent(m.proj_avg_damage, fit) - _smooth_percent(1800, fit)
    assert inc < 0                                                        # 0-damage drags down
    assert round(m.cur_percent, 2) == round(84.7 + inc, 2)
    assert m.cur_percent < 84.7
    assert round(m.pct_delta, 2) == round(inc, 2)


def test_build_battle_model_clamps_cur_percent_to_100():
    # High standing + a monster battle would push pre_percentile + increment over 100.
    m = build_battle_model(_bsnap(damage=99999, assist=0, stun=0,
                                  pre_avg_damage=1800, pre_percentile=99.0))
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
