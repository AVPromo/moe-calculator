# -*- coding: utf-8 -*-
"""Turn a BattleSnapshot into a BattleMoEModel. Pure and engine-free.

The four in-battle readouts (see TASKS/in-battle-moe-panel.md):
  1. live combined damage  C = damage + max(track, spot, stun) - team_damage   (WG #15060: MAX)
  2. projected moving-average combined damage  avgWithCD = prevAvg + k*(C - prevAvg)  (EWMA)
  3. current percent  = f(avgWithCD): our reconstruction of WG's damageRating evaluated DIRECTLY
     at the projected moving average, where f maps combined damage to percentile by piecewise-LINEAR
     interpolation over the tank's percentile anchors plus a (0, 0) origin -- EXACTLY how WG
     computes damageRating itself (see _fit_from_thresholds). NOT anchored on WG's stamped
     pre_percentile any more (see build_battle_model for why the anchor was dropped).
  4. percent delta    = current percent - pre_percentile   (signed gain from WG's stamped
     career standing getDamageRating; so current percent - delta == pre_percentile, the WG stamp)

Metrics 2-4 ride on the EWMA coefficient k (community-reverse-engineered, not WG-confirmed).
The assist component of combined damage is the HIGHER of tracking / spotting / stun (see
counted_assistance) -- WG credits the greatest stream, not the sum; the server battle-events
summary supplies the track/spot split (adapter/battle_adapter._read_assist_split).
"""
import bisect
import math

from moe_calculator.domain import battle_types as bt
from moe_calculator.domain.constants import (
    EFFICIENCY_BAR_STOPS, EWMA_K, MARK_PERCENTS,
    PROGRESS_AXIS_MIN_WINDOW, PROGRESS_ETA_CAP)
from moe_calculator.domain.rounding import iround_half_away


def _clamp(value, lo, hi):
    # NaN compares False against everything, so the bare comparisons below would pass it
    # through unclamped and propagate NaN to the widget. Treat NaN as the low bound.
    if value != value:
        return lo
    return lo if value < lo else hi if value > hi else value


def counted_assistance(track, spot, stun, merged_assist=0):
    """The single assist stream that counts toward MoE this battle, and which one it is.

    MoE credits the HIGHER of assisted damage vs stun (not their sum) -- and within assisted
    damage, the higher of tracking vs spotting (not their sum). So the counted value is
    max(track, spot, stun); `kind` is whichever wins, and selects the overlay row's icon.

    `merged_assist` is the personal-efficiency controller's spot+track MERGED total, used only
    as a fallback: before the server split summary is delivered (battle start), track and spot
    are both 0 while merged_assist may already be > 0. In that window we credit merged_assist as
    the assist component (kind 'assist', generic icon) so combined damage never under-counts.

    Returns (value, kind), kind in {'track', 'spot', 'stun', 'assist'}. kind is 'assist' when
    value is 0 (the row hides then). Tie-breaks: stun wins only when strictly greatest; between
    tracking and spotting, spotting wins a tie."""
    t = int(track or 0)
    s = int(spot or 0)
    st = int(stun or 0)
    m = int(merged_assist or 0)
    if t == 0 and s == 0 and m > 0:
        assist_val, assist_kind = m, "assist"
    else:
        assist_val = t if t > s else s
        assist_kind = "track" if t > s else "spot"
    if st > assist_val:
        return st, "stun"
    if assist_val <= 0:
        return 0, "assist"
    return assist_val, assist_kind


def combined_damage(damage, track, spot, stun, team_damage, merged_assist=0):
    """Live combined damage: direct + counted assistance - team damage, clamped >= 0.

    Counted assistance = max(track, spot, stun) -- WG credits the HIGHER assist stream, not the
    sum (support #15060) -- with `merged_assist` as the pre-split fallback (see
    counted_assistance)."""
    counted, _kind = counted_assistance(track, spot, stun, merged_assist)
    c = int(damage or 0) + int(counted or 0) - int(team_damage or 0)
    return c if c > 0 else 0


def _fit_from_thresholds(thresholds):
    """Build the damage->percent fit from the per-tank threshold points -- WG's OWN curve.

    `thresholds` is keyed by PERCENTILE (adapter/moe_wgapi): the four legacy anchors 65/85/95/100
    always, plus 20/40/55/75 whenever WG returned them. Each entry is a known point on the tank's
    combined-damage -> percentile curve, and WG's damageRating is EXACTLY piecewise-LINEAR
    interpolation over those anchors plus an implicit (0 damage, 0 percent) origin -- confirmed by
    back-test over 118 logged battles (level error mean +0.05pp, stdev 0.09, max 0.24; the
    superseded piecewise-normal fit was mean +1.85, stdev 3.16, max 11.9, nearly all of it below
    the lowest fitted stop). See tools/dev/analyze_battle_samples.py --backtest. So the fit IS the
    anchor list -- nothing is solved, no z-space, no probit.

    Returns [(damage, percent), ...] ascending with the origin first, or None when NO real anchor
    survived (missing / unusable table -> the caller's has_data False path). WG's API can return
    missing, zero, equal or non-monotone anchors: keep only the strictly increasing-in-damage ones,
    which drops garbage and guarantees d_hi > d_lo on every segment (no zero divide)."""
    if not thresholds:
        return None
    try:
        anchors = sorted((int(pct), float(int(dmg or 0))) for pct, dmg in thresholds.items())
    except (TypeError, ValueError, AttributeError):
        return None
    stops = [(0.0, 0.0)]
    for percent, d in anchors:
        if d > stops[-1][0]:
            stops.append((d, float(percent)))
    if len(stops) < 2:
        return None
    return stops


def _smooth_percent(damage, fit):
    """Combined `damage` -> percent (0..100) by plain linear interpolation over `fit`'s anchors,
    i.e. WG's own damageRating (see _fit_from_thresholds). 0 at no damage (the origin stop), and
    FLAT at the top anchor's percentile above it -- WG's table ends at the 100th percentile, so
    there is nothing left to extrapolate into."""
    # _clamp, not a bare float: it maps NaN to the low bound (a NaN would otherwise fall through
    # every segment test and report the TOP percentile) and pins anything past the last anchor.
    d = _clamp(float(damage or 0.0), 0.0, fit[-1][0])
    percent = fit[-1][1]
    for (d_lo, p_lo), (d_hi, p_hi) in zip(fit, fit[1:]):
        if d <= d_hi:
            percent = p_lo + (p_hi - p_lo) * (d - d_lo) / (d_hi - d_lo)
            break
    return _clamp(percent, 0.0, 100.0)


def ewma_project_raw(prev_avg, cd, k=EWMA_K):
    """`ewma_project` WITHOUT the final rounding -- the same fold as a float.

    Exists because the rounding destroys the signal for any consumer that watches proj for
    CHANGE rather than displaying it: k ~= 0.02, so a whole battle's damage moves proj by only a
    couple of damage points and an integer proj quantises nearly every update away. The
    centre-screen progress bar's change-detect (MoEProgress.js) needs the raw float; the corner
    overlay, which only ever prints proj as a whole number, keeps the rounded `ewma_project`."""
    prev = float(prev_avg or 0.0)
    return prev + k * (float(cd or 0) - prev)


def ewma_project(prev_avg, cd, k=EWMA_K):
    """Fold this battle's combined damage `cd` into the moving average `prev_avg` one EWMA
    step: prev + k*(cd - prev). Rounded to an integer damage value.

    A 0-damage battle-so-far IS folded (proj = prev*(1-k)): the overlay honestly projects
    'where you'd stand if the battle ended now', opening ~1-2 pts below career and climbing
    as real damage accrues. `combined_damage()` clamps cd to >= 0 upstream, so the fold
    never drags below prev*(1-k)."""
    return iround_half_away(ewma_project_raw(prev_avg, cd, k))


def build_battle_model(snapshot):
    """Compose the four in-battle readouts from the snapshot. Always returns a model;
    visibility is decided separately by battle_bar_visible()."""
    thresholds = snapshot.thresholds or {}
    merged_assist = getattr(snapshot, "assist", 0)
    counted, assist_kind = counted_assistance(
        getattr(snapshot, "track_assist", 0), getattr(snapshot, "spot_assist", 0),
        snapshot.stun, merged_assist)
    cd = combined_damage(snapshot.damage, getattr(snapshot, "track_assist", 0),
                         getattr(snapshot, "spot_assist", 0), snapshot.stun,
                         snapshot.team_damage, merged_assist=merged_assist)
    proj = ewma_project(snapshot.pre_avg_damage, cd)
    # RAW (un-rounded) projection for the percentile lookup only. Rounding proj to a whole
    # damage value before f() shifts the interpolated percent enough to flip the 2-decimal
    # display by 0.01 (e.g. 682 -> 18.4574 vs 681.84 -> 18.4531); the rounded `proj` above
    # stays the DISPLAYED integer damage, `proj_raw` feeds only cur_percent below.
    proj_raw = ewma_project_raw(snapshot.pre_avg_damage, cd)

    # Whether we have a CAREER baseline to project from. A >0 pre_avg/pre_percentile is an
    # obvious yes; a GENUINE 0 baseline also counts when the garage read the tank this session
    # (snapshot.baseline_known) -- e.g. the first-ever battle in a freshly-bought tank, where 0
    # is the true career and the projection (proj = k*cd, cur_percent = interp(proj)) is well
    # defined. Only a FALSE 0 -- replay / relogin straight into battle, the garage dossier never
    # read (baseline_known False; see baseline_cache + BUG B) -- collapses the EWMA fold and
    # anchors cur_percent on a bogus 0, so the overlay dashes proj/percent/delta out there.
    has_baseline = ((snapshot.pre_percentile or 0) > 0
                    or (snapshot.pre_avg_damage or 0) > 0
                    or bool(getattr(snapshot, "baseline_known", False)))

    # The live percent is our reconstruction evaluated DIRECTLY at the projection: cur = f(proj).
    # At battle start proj == prev*(1-k), so f(proj) opens just BELOW f(pre_avg): the honest
    # projection of an uncommitted (0-damage) battle, climbing as damage accrues.
    #
    # UN-ANCHORED cur_percent, deliberately (was: pre_percentile + f(proj) - f(pre_avg)). WG's
    # getDamageRating is a server-STAMPED stored value; our f reconstructs the same curve from the
    # public anchors, and now reproduces WG's damageRating faithfully, so f(proj) at end matches the
    # garage to within reconstruction error; displaying it directly removes the old offset.
    #
    # The delta, however, measures gain from WG's REAL stamped career standing pre_percentile
    # (getDamageRating), NOT from our reconstruction f(pre_avg). Measuring from f(pre_avg) folded in
    # the reconstruction offset f(pre_avg) - pre_percentile, which flips sign per tank and made the
    # delta disagree with lebwa (e.g. Strv 107-12: cur 18.24, pre_percentile 19.03 -> real delta
    # -0.79, but cur - f(pre_avg) gave -0.37). So pct_delta = cur - pre_percentile, and the invariant
    # is cur - delta == pre_percentile (WG's stamp), matching lebwa.
    #
    # A table with no usable anchor at all degrades to 'no percent' (has_data False), never a crash.
    fit = _fit_from_thresholds(thresholds)
    has_data = fit is not None
    if has_data:
        cur_percent = _clamp(_smooth_percent(proj_raw, fit), 0.0, 100.0)
        pct_delta = cur_percent - float(snapshot.pre_percentile or 0.0)
    else:
        cur_percent = 0.0
        pct_delta = 0.0

    return bt.BattleMoEModel(
        combined_damage=cd,
        counted_assist=counted,
        assist_kind=assist_kind,
        proj_avg_damage=proj,
        cur_percent=cur_percent,
        pct_delta=pct_delta,
        has_data=has_data,
        has_baseline=has_baseline)


# --- centre-screen progress bar: the mark axis --------------------------------
# The bar spans the COMBINED-DAMAGE gap between the requirement for the mark you HOLD and the
# requirement for the next one, so it needs a mark count -- which BattleSnapshot does not carry
# (the dossier is unreadable in battle; see battle_types).

def marks_from_percentile(pre_percentile):
    """Mark count 0..3 implied by the career damage-rating percentile (MARK_PERCENTS).

    ponytail: derived, not read. Right AT a boundary this can disagree with the mark the game
    actually shows -- WG awards on its own rounding of a rating that keeps moving, so a career
    standing of 64.999 or 65.001 is a coin toss and the bar would pick the neighbouring axis
    segment for one battle. Upgrade path when that matters: stash the GARAGE's real
    MARK_ON_GUN_RECORD.getValue() in adapter/baseline_cache (which already carries
    pre_percentile / pre_avg from the garage into battle) and prefer it here, keeping this
    derivation as the replay / relogin fallback."""
    p = float(pre_percentile or 0.0)
    marks = 0
    for percent in MARK_PERCENTS:
        if p >= percent:
            marks += 1
    return marks


def mark_axis(thresholds, marks):
    """The (lo, hi) combined-damage axis ends for the progress bar, as floats.

    `thresholds` is keyed by PERCENTILE, so a mark count indexes MARK_PERCENTS: lo = the
    requirement for the mark HELD -- thresholds[MARK_PERCENTS[marks - 1]] -- with 0 as the left
    end at 0 marks (nothing held yet, so the axis starts at no damage). hi = the requirement for
    the mark being CHASED -- thresholds[MARK_PERCENTS[marks]] -- with the 100th-percentile
    goalpost (thresholds[100]) as the right end at 3 marks, where there is no higher mark.
    Mirrors the tuner's own axis (`nx = marks >= 3 ? 100 : marks + 1`).

    Returns (0.0, 0.0) when the table is missing or the resolved ends are not a usable
    ascending pair -- the caller's "no data" path (the bar hides rather than dividing by a
    zero-width axis)."""
    thresholds = thresholds or {}
    marks = min(max(0, int(marks or 0)), 3)
    try:
        lo = float(thresholds.get(MARK_PERCENTS[marks - 1], 0) or 0) if marks > 0 else 0.0
        hi = float(thresholds.get(100 if marks >= 3 else MARK_PERCENTS[marks], 0) or 0)
    except (TypeError, ValueError, AttributeError):
        return 0.0, 0.0
    if hi <= lo:
        return 0.0, 0.0
    return lo, hi


def progress_axis_lo(axis_hi, pre_avg, k=EWMA_K, min_window=PROGRESS_AXIS_MIN_WINDOW):
    """The bar's display floor: where the projection lands after a zero-damage battle.

    Replaces the held-mark requirement as the axis's left end, so one battle's
    movement is a visible fraction of the track instead of a rounding error.

    THE FLOOR IS A CALL TO ewma_project_raw, NEVER AN INLINED pre * (1 - k): it is the SAME fold
    the fill's own proj_avg uses, evaluated at the smallest cd can ever be (combined_damage clamps
    cd >= 0 upstream), so the floor is provably the fill's minimum and the two can never drift
    apart. min_window only binds once pre_avg sits within a few tens of damage of axis_hi (the
    window is already >= k * pre_avg without it) and keeps the axis from collapsing to zero width.

    mark_axis stays the no-data verdict: this is a DISPLAY floor, computed only once the caller has
    already decided the mark axis is usable."""
    floor = ewma_project_raw(pre_avg, 0, k)
    return max(0.0, min(floor, float(axis_hi or 0.0) - min_window))


def battles_to_axis_hi(proj_avg, cd, axis_hi, k=EWMA_K, cap=PROGRESS_ETA_CAP):
    """Repeats of THIS battle needed for the average to reach axis_hi.

    Models the future as "every future battle repeats this battle's combined damage `cd`". The
    EWMA folding `cd` each step converges geometrically on `cd` itself
    (avg_n - cd = (1 - k)^n * (proj_avg - cd)); setting avg_n = axis_hi and solving:
        n = ln((axis_hi - cd) / (proj_avg - cd)) / ln(1 - k)
    The count is MONOTONE NON-INCREASING in `cd` for cd > axis_hi -- a bigger overshoot converges
    FASTER, so a worse (smaller) cd yields a LARGER count -- and then BLANKS (returns -1) once
    cd <= axis_hi, rather than climbing toward `cap`.

    Sign check, so the log is asserted rather than trusted: branch 2 ruled out proj_avg >= axis_hi
    and branch 4's guard is cd > axis_hi, so proj_avg < axis_hi < cd. Both (axis_hi - cd) and
    (proj_avg - cd) are negative with |axis_hi - cd| < |proj_avg - cd|, i.e. the ratio sits in
    (0, 1), its ln is negative, and dividing by the also-negative ln(1 - k) gives a positive n.

    Returns:
      -1 when axis_hi <= 0 (no-data sentinel; the caller's hasData already gates rendering).
      0 when proj_avg >= axis_hi (the mark is already made).
      -1 when cd <= axis_hi (UNREACHABLE by design: repeating this battle converges the average on
        cd, which is at or below the goal, so the mark never comes -- render BLANK via the same JS
        no-data gate, not a pinned cap).
      otherwise a positive int capped at `cap`. Runs per damage event in battle, so any non-finite
      or degenerate input degrades to `cap` rather than raising."""
    if float(axis_hi or 0.0) <= 0.0:
        return -1
    hi = float(axis_hi)
    proj = float(proj_avg or 0.0)
    if proj >= hi:
        return 0
    dmg = float(cd or 0.0)
    if dmg <= hi:
        return -1
    try:
        n = math.log((hi - dmg) / (proj - dmg)) / math.log(1.0 - k)
        return min(cap, max(1, int(math.ceil(n))))
    except (ValueError, ZeroDivisionError, OverflowError):
        return cap


# --- damage-efficiency bar: the five-stop damage axis -------------------------
# The ALTERNATIVE centre-screen bar (a radio option against the mark-axis bar above) plots THIS
# BATTLE's combined damage against all four of the tank's requirements at once: the five damage
# stops [0, r65, r85, r95, r100] mapped onto four visually EQUAL quarters
# (constants.EFFICIENCY_BAR_STOPS), piecewise-linear and clamped at both ends. That is exactly
# barX's algorithm in MoECalculator.js:302-322 -- but barX maps a PERCENTILE, so the damage-keyed
# form below is the only mirror of it and had no Python home before.
# Unlike mark_axis this needs NO mark count and NO career baseline: the axis is the tank's
# requirement table and the plotted value is this battle's damage.

def efficiency_stops(thresholds):
    """The five damage stops (0.0, r65, r85, r95, r100) as floats, or None when unusable.

    `thresholds` is snap.thresholds, keyed by PERCENTILE, so these are keys 65/85/95/100 (it may
    also carry the 20/40/55/75 enrichment anchors -- this bar's axis deliberately ignores them,
    its four visual quarters ARE the four requirements). Upstream those four are ALL-OR-NOTHING
    (adapter/moe_wgapi drops a whole tank row unless all four parse, and returns {} on a miss), so
    there is no partial-axis path to write here: either all four requirements are present and
    strictly ascending, or this returns None and the caller's has_data gate hides the bar.
    Non-monotone / zero stops are rejected the same way -- a zero-width segment would divide by
    zero in efficiency_bar_x."""
    thresholds = thresholds or {}
    stops = [0.0]
    try:
        for key in MARK_PERCENTS + (100,):
            d = float(int(thresholds.get(key, 0) or 0))
            if d <= stops[-1]:
                return None
            stops.append(d)
    except (TypeError, ValueError, AttributeError):
        return None
    return tuple(stops)


def efficiency_bar_x(damage, stops):
    """Combined `damage` -> its position along the bar, 0..100 %, over the equal quarters.

    Clamped at both ends (damage past r100 pins at 100 %, negative at 0 %). Returns 0.0 on an
    unusable axis (`stops` None) -- the bar is hidden there anyway."""
    if not stops:
        return 0.0
    d = _clamp(float(damage or 0.0), stops[0], stops[-1])
    # bisect_left == "first stop >= d", i.e. the segment the clamped d falls in; max(1, ...) folds
    # the d == stops[0] case (which bisects to 0) into the first segment. `stops` is all floats
    # (efficiency_stops), so the interpolation is a true float divide with no __future__ import.
    i = max(1, bisect.bisect_left(stops, d))
    t = (d - stops[i - 1]) / (stops[i] - stops[i - 1])
    lo = EFFICIENCY_BAR_STOPS[i - 1]
    return lo + t * (EFFICIENCY_BAR_STOPS[i] - lo)


def efficiency_band(damage, stops):
    """The colour band index 0..4: the HIGHEST requirement `damage` has passed, `>=` INCLUSIVE
    -- damage landing exactly on r65 is already band 1. 0 = none passed yet.

    Deliberately Python, not JS: the band drives the fill, the numerals and both glows, so the
    inclusive rule gets exactly ONE home and is tested by the same fixtures as the axis. It is
    pushed as a single int VM prop; the front-end must never re-derive it."""
    if not stops:
        return 0
    # bisect_RIGHT is what makes the rule `>=`-inclusive: it inserts AFTER an equal stop, so
    # damage exactly on r65 counts as passed (bisect_left would read it as band 0).
    # _clamp IS LOAD-BEARING, not tidiness: bisect drives its search off `x < a[mid]`, which is
    # False for NaN at every step, so a NaN total would walk all the way right and report the TOP
    # band (the old highest-passed-stop loop reported 0, since NaN >= x is also False). _clamp maps
    # NaN to the low bound, restoring that -- and pins a negative/huge total to the axis ends.
    d = _clamp(float(damage or 0.0), stops[0], stops[-1])
    return max(0, bisect.bisect_right(stops, d) - 1)


def battle_bar_visible(in_battle, has_vehicle, is_spectating=False, overlay_open=False,
                       enabled=True, alt_mode=False, alt_held=False):
    """Whether the in-battle overlay should render. Pure/engine-free so it unit-tests on
    plain inputs: a player vehicle must be readable and combat must be active, and we must
    NOT be spectating another player. While spectating (postmortem free-look), the tank
    identity/thresholds follow the observed vehicle but the damage stats stay ours, so the
    percent/delta is meaningless -- hide it. `overlay_open` is a hard override: while WG's
    full-stats scoreboard family (Tab / personal missions / reserves) is up, hide the
    readout so it does not clutter the full-screen scoreboard.

    Two settings decide whether the overlay is "active" at all:
    - `enabled` is the "In-Battle Widget" master setting. When off, the overlay is NEVER
      shown -- it is the hard gate.
    - `alt_mode` is the "Show on Alt Key" child setting. While the master is on it decides HOW
      the overlay shows: with `alt_mode` on the overlay appears only while `alt_held` (Alt
      currently down); with `alt_mode` off it is shown at all times.
    i.e. active == enabled and (alt_held if alt_mode else True). The child is inert while the
    master is off. Defaults keep prior callers unchanged."""
    base = (bool(has_vehicle) and bool(in_battle)
            and not bool(is_spectating) and not bool(overlay_open))
    active = bool(enabled) and (bool(alt_held) if bool(alt_mode) else True)
    return base and active
