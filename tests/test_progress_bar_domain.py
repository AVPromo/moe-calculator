# -*- coding: utf-8 -*-
"""Engine-free tests for the centre-screen progress bar's three new domain pieces:
the mark-count derivation, the mark-axis end selection, and the centred window anchor.
All pure -- no client, no game symbols.
"""
import pytest

from moe_calculator.domain.battle_builder import (
    battles_to_axis_hi, ewma_project_raw, mark_axis, marks_from_percentile, progress_axis_lo)
from moe_calculator.domain.constants import (
    EWMA_K, PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_FRAC, PROGRESS_ANCHOR_Y_OFFSET,
    PROGRESS_ETA_CAP, PROGRESS_ETA_MARGIN)
from moe_calculator.domain.positioning import anchor_centred

# The shape battle_adapter fills from moe_wgapi.get_thresholds(): D65 / D85 / D95 / D100, keyed
# by PERCENTILE (mark_axis indexes MARK_PERCENTS into it, not MARK_COUNTS).
THR = {65: 2450, 85: 3050, 95: 3620, 100: 4400}


# --- marks_from_percentile ----------------------------------------------------

@pytest.mark.parametrize("percentile,expected", [
    (0.0, 0), (12.5, 0), (64.99, 0),
    (65.0, 1), (65.01, 1), (84.99, 1),
    (85.0, 2), (94.99, 2),
    (95.0, 3), (99.9, 3), (100.0, 3),
])
def test_mark_count_from_the_career_percentile(percentile, expected):
    assert marks_from_percentile(percentile) == expected


def test_mark_count_reads_a_boundary_as_earned():
    # MARK_PERCENTS are the >= thresholds, so a percentile exactly ON a stop counts the mark.
    # (This is the boundary the ponytail note in marks_from_percentile flags as fragile.)
    assert marks_from_percentile(85) == 2


def test_mark_count_fails_soft_on_an_unreadable_percentile():
    assert marks_from_percentile(None) == 0


# --- mark_axis ----------------------------------------------------------------

def test_axis_at_zero_marks_runs_from_zero_to_the_first_requirement():
    assert mark_axis(THR, 0) == (0.0, 2450.0)


@pytest.mark.parametrize("marks,expected", [
    (1, (2450.0, 3050.0)),
    (2, (3050.0, 3620.0)),
])
def test_axis_between_marks_is_held_to_chased(marks, expected):
    assert mark_axis(THR, marks) == expected


def test_axis_at_three_marks_chases_the_hundredth_percentile_goalpost():
    # No higher mark exists, so the 100 stop is the right end.
    assert mark_axis(THR, 3) == (3620.0, 4400.0)


def test_axis_is_unusable_without_a_threshold_table():
    assert mark_axis({}, 1) == (0.0, 0.0)
    assert mark_axis(None, 1) == (0.0, 0.0)


def test_axis_is_unusable_when_the_chased_end_is_missing():
    # A partial WG table: the mark held is known but the next requirement is not.
    assert mark_axis({65: 2450}, 1) == (0.0, 0.0)


def test_axis_is_unusable_when_the_ends_are_not_ascending():
    # WG can return non-monotone stops; a zero-or-negative-width axis must degrade, not divide.
    assert mark_axis({65: 3050, 85: 3050, 100: 4400}, 1) == (0.0, 0.0)
    assert mark_axis({65: 3100, 85: 3050, 100: 4400}, 1) == (0.0, 0.0)


def test_axis_reads_percentile_keys_not_mark_counts():
    # REGRESSION for the percentile re-key: a stale mark-count-keyed table ({1,2,3,100}) must
    # degrade to no axis, never resolve D65/D85 as the 1st/2nd-percentile requirements.
    assert mark_axis({1: 2450, 2: 3050, 3: 3620, 100: 4400}, 1) == (0.0, 0.0)


def test_axis_ignores_the_enrichment_anchors():
    # The 20/40/55/75 anchors ride in the same dict; the mark axis's ends are 65/85/95/100 only.
    enriched = dict(THR)
    enriched.update({20: 528, 40: 1163, 55: 1549, 75: 2104})
    assert mark_axis(enriched, 1) == (2450.0, 3050.0)
    assert mark_axis(enriched, 0) == (0.0, 2450.0)


def test_axis_clamps_a_nonsense_mark_count():
    assert mark_axis(THR, 9) == (3620.0, 4400.0)     # clamped to 3 -> the goalpost
    assert mark_axis(THR, -1) == (0.0, 2450.0)       # clamped to 0 -> from zero


# --- anchor_centred -----------------------------------------------------------

def test_centred_anchor_halves_the_movable_extent():
    # THE identity: the far-sentinel clamp yields max_x == space_w - surface_w, so max_x // 2
    # centres the surface exactly -- neither width is needed here. 1920 space, 256 surface:
    space_w, surface_w = 1920, 256
    max_x = space_w - surface_w
    x, _y = anchor_centred(max_x, 800, 0.85)
    assert x == 832
    assert x + surface_w // 2 == space_w // 2


def test_centred_anchor_places_y_proportionally_down_the_extent():
    assert anchor_centred(1664, 800, 0.85)[1] == 680
    assert anchor_centred(1664, 800, 0.0)[1] == 0
    assert anchor_centred(1664, 800, 1.0)[1] == 800


def test_centred_anchor_applies_a_signed_x_offset():
    assert anchor_centred(1664, 800, 0.5, 40)[0] == 872
    assert anchor_centred(1664, 800, 0.5, -40)[0] == 792


def test_centred_anchor_applies_a_signed_y_offset():
    # The compensation term: the JS shifts the whole composition down inside its own surface
    # (MoEProgress.js SHIFT_Y_REM), so the window moves UP by the same amount.
    assert anchor_centred(1664, 800, 0.85, 0, -44)[1] == 636      # 680 - 44
    assert anchor_centred(1664, 800, 0.85, 0, 44)[1] == 724


def test_centred_anchor_y_offset_cancels_the_intra_surface_shift():
    # THE INVARIANT the compensation exists for: shifting the bar +N inside the surface and the
    # window -N leaves the bar's ON-SCREEN y exactly where it was. Same extent both sides, so
    # this isolates the translation from the surface-height change that also moves max_y.
    shift = -PROGRESS_ANCHOR_Y_OFFSET
    plain = anchor_centred(1664, 800, PROGRESS_ANCHOR_Y_FRAC)[1]
    compensated = anchor_centred(1664, 800, PROGRESS_ANCHOR_Y_FRAC,
                                 PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_OFFSET)[1]
    assert compensated + shift == plain


def test_centred_anchor_needs_no_x_compensation():
    # X self-calibrates: max_x == space_w - surface_w, so max_x // 2 centres ANY surface width,
    # and the composition is symmetric about its own centre -> the bar's centre lands on the
    # screen's centre at both the old 256 fallback width and the new one. Hence X_OFFSET == 0.
    space_w = 1920
    assert PROGRESS_ANCHOR_X_OFFSET == 0
    for surface_w in (256, 480):
        x = anchor_centred(space_w - surface_w, 800, 0.85, PROGRESS_ANCHOR_X_OFFSET)[0]
        assert x + surface_w // 2 == space_w // 2


def test_centred_anchor_clamps_both_axes_on_screen():
    assert anchor_centred(1664, 800, 2.5) == (832, 800)        # y past the bottom
    assert anchor_centred(1664, 800, -1.0) == (832, 0)         # y above the top
    assert anchor_centred(1664, 800, 0.5, 9999)[0] == 1664     # offset past the right edge
    assert anchor_centred(1664, 800, 0.5, -9999)[0] == 0       # ...and past the left


def test_centred_anchor_survives_a_zero_extent():
    # A surface as large as the logical space leaves nothing movable -> the origin.
    assert anchor_centred(0, 0, 0.85) == (0, 0)


@pytest.mark.parametrize("bad", [None, "", "x", float("nan")])
def test_centred_anchor_fails_soft_on_an_unusable_y_frac(bad):
    # Degrades to the top edge rather than raising into the placement path.
    assert anchor_centred(1664, 800, bad) == (832, 0)


@pytest.mark.parametrize("bad", [None, "", "x", float("nan")])
def test_centred_anchor_fails_soft_on_an_unusable_offset(bad):
    assert anchor_centred(1664, 800, 0.5, bad)[0] == 832


def test_centred_anchor_fails_soft_on_an_unusable_extent():
    assert anchor_centred(None, None, 0.85) == (0, 0)


# --- progress_axis_lo ----------------------------------------------------------

def test_axis_lo_is_exactly_the_zero_damage_ewma_projection():
    # NOT a recomputed pre * (1 - k) literal -- a call to the SAME fold the fill uses, so the
    # floor and the fill can never drift apart. This must fail if someone inlines the arithmetic.
    axis_hi, pre_avg = 4400.0, 1850.0
    assert progress_axis_lo(axis_hi, pre_avg) == ewma_project_raw(pre_avg, 0, EWMA_K)


def test_axis_lo_sits_strictly_below_the_pre_battle_average():
    # "started the battle, did nothing" -- the zero-damage fold always pulls the average down.
    assert progress_axis_lo(4400.0, 1850.0) < 1850.0


def test_axis_lo_binds_to_the_min_window_near_the_top_of_the_axis():
    # pre_avg sits within a few tens of damage of axis_hi -- the unclamped floor would leave a
    # near-zero-width axis, so min_window forces the floor down to axis_hi - min_window.
    assert progress_axis_lo(2950.0, 2900.0) == 2750.0


def test_axis_lo_floors_at_zero_and_never_goes_negative():
    # axis_hi below min_window collapses the clamp's upper bound below zero.
    assert progress_axis_lo(100.0, 5000.0) == 0.0
    # pre_avg 0 / None with a normal axis_hi -- the fold is 0, well inside [0, axis_hi - window].
    assert progress_axis_lo(4400.0, 0) == 0.0
    assert progress_axis_lo(4400.0, None) == 0.0


# --- battles_to_axis_hi ---------------------------------------------------------

def test_eta_is_monotone_non_increasing_as_the_battle_gets_worse():
    # THE property the whole model exists to satisfy: a worse battle (lower proj_avg) must never
    # read as FEWER remaining battles. A signed linear extrapolation was tried and rejected
    # precisely because it fails this; this sweep is the guard against it coming back.
    axis_hi = 4400.0
    steps = [axis_hi * i / 500.0 for i in range(500)]  # 0 .. just under axis_hi
    values = [battles_to_axis_hi(p, axis_hi) for p in steps]
    for prev, cur in zip(values, values[1:]):
        assert cur <= prev


def test_eta_sentinels():
    assert battles_to_axis_hi(1000.0, 0.0) == -1
    assert battles_to_axis_hi(1000.0, -5.0) == -1
    assert battles_to_axis_hi(4400.0, 4400.0) == 0
    assert battles_to_axis_hi(5000.0, 4400.0) == 0


def test_eta_never_raises_across_the_full_sweep():
    axis_hi = 4400.0
    for i in range(-100, 600):
        battles_to_axis_hi(axis_hi * i / 500.0, axis_hi)


@pytest.mark.parametrize("bad_axis_hi,bad_proj", [
    (float("nan"), 1000.0),
    (4400.0, float("nan")),
])
def test_eta_degenerates_to_the_cap_rather_than_raising(bad_axis_hi, bad_proj):
    assert battles_to_axis_hi(bad_proj, bad_axis_hi) == PROGRESS_ETA_CAP


def test_eta_degenerates_to_the_cap_on_a_k_that_never_converges():
    # k == 1.0 makes ln(1 - k) == ln(0), which raises inside the fold -- the caller must still
    # get a number back.
    assert battles_to_axis_hi(1000.0, 4400.0, k=1.0) == PROGRESS_ETA_CAP


def test_eta_clamps_at_the_cap_and_returns_at_least_one_short_of_the_goal():
    assert battles_to_axis_hi(0.0, 4400.0) <= PROGRESS_ETA_CAP
    for proj in (0.0, 100.0, 2000.0, 4399.0):
        assert battles_to_axis_hi(proj, 4400.0) >= 1


def test_eta_reads_its_defaults_from_the_constants_module():
    # Pin against the CONSTANTS, not a hardcoded 99 / 0.10, so a knob change can't leave a
    # stale-but-green test: an explicit-args call must match the bare-defaults call exactly.
    proj_avg, axis_hi = 1200.0, 4400.0
    assert (battles_to_axis_hi(proj_avg, axis_hi)
            == battles_to_axis_hi(proj_avg, axis_hi, EWMA_K, PROGRESS_ETA_MARGIN, PROGRESS_ETA_CAP))
    # And the cap is genuinely reachable at the constant's value, not some other number.
    assert battles_to_axis_hi(4399.999999, 4400.0) <= PROGRESS_ETA_CAP
