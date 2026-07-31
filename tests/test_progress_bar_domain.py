# -*- coding: utf-8 -*-
"""Engine-free tests for the centre-screen progress bar's three new domain pieces:
the mark-count derivation, the mark-axis end selection, and the centred window anchor.
All pure -- no client, no game symbols.
"""
import pytest

from moe_calculator.domain.battle_builder import mark_axis, marks_from_percentile
from moe_calculator.domain.constants import (
    PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_FRAC, PROGRESS_ANCHOR_Y_OFFSET)
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
