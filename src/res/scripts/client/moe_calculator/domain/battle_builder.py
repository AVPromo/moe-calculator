# -*- coding: utf-8 -*-
"""Turn a BattleSnapshot into a BattleMoEModel. Pure and engine-free.

The four in-battle readouts (see TASKS/in-battle-moe-panel.md):
  1. live combined damage  C = damage + max(track, spot, stun) - team_damage   (WG #15060: MAX)
  2. projected moving-average combined damage  avgWithCD = prevAvg + k*(C - prevAvg)  (EWMA)
  3. current percent  = WG's real career standing (pre_percentile) + this battle's increment
     f(avgWithCD) - f(prevAvg), where f maps combined damage to percentile by piecewise-LINEAR
     interpolation over the tank's percentile anchors plus a (0, 0) origin -- which is EXACTLY
     how WG computes damageRating itself (see _fit_from_thresholds).
  4. percent delta    = current percent - pre-battle standing percentile   (signed)

Metrics 2-4 ride on the EWMA coefficient k (community-reverse-engineered, not WG-confirmed).
The assist component of combined damage is the HIGHER of tracking / spotting / stun (see
counted_assistance) -- WG credits the greatest stream, not the sum; the server battle-events
summary supplies the track/spot split (adapter/battle_adapter._read_assist_split).
"""
import bisect

from moe_calculator.domain import battle_types as bt
from moe_calculator.domain.constants import EFFICIENCY_BAR_STOPS, EWMA_K, MARK_PERCENTS
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

    # The live percent is ALWAYS anchored to WG's REAL career standing (pre_percentile, from
    # the dossier's getDamageRating) plus ONLY this battle's increment f(proj) - f(pre_avg). At
    # battle start proj == prev*(1-k), so the increment is slightly negative and we open just
    # BELOW WG's number: the honest projection of an uncommitted (0-damage) battle, climbing as
    # damage accrues.
    #
    # KEEP THE ANCHORED FORM. f now reproduces WG's damageRating rather than approximating it, so
    # the anchor's job is no longer accuracy -- it is UI CONTINUITY: WG's anchor table drifts
    # DAILY, so f(pre_avg) computed off today's table differs slightly from the pre_percentile the
    # dossier recorded under an older one. Anchoring guarantees the overlay opens on exactly the
    # number the garage just showed, and the drift cancels in the increment. Do not "simplify" it
    # into a bare f(proj).
    #
    # A table with no usable anchor at all degrades to 'no percent' (has_data False), never a crash.
    fit = _fit_from_thresholds(thresholds)
    has_data = fit is not None
    if has_data:
        inc = (_smooth_percent(proj, fit)
               - _smooth_percent(snapshot.pre_avg_damage, fit))
        cur_percent = _clamp(float(snapshot.pre_percentile or 0.0) + inc, 0.0, 100.0)
        pct_delta = inc
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
