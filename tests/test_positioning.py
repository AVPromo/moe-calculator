# -*- coding: utf-8 -*-
"""Tests for the engine-free overlay-placement math. Runs on Python 3 (no game engine):
domain.positioning imports zero game symbols. The extents below are the REAL far-sentinel
readouts measured in-client at 4K (probe_scale.py): 1x -> space 3840x2160, 2x -> 1920x1080,
surface fixed 256x256, so movable extent = space - 256."""
from moe_calculator.domain.positioning import (
    anchor_centred, anchor_centred_reduced, anchor_minimap, anchor_offset,
    anchor_top_left, battle_y_anchor, cursor_in_rect, cursor_logical,
    cursor_top_left, damage_log_summary_hidden, efficiency_panel_wide,
    free_anchor_point, free_top_left)
from moe_calculator.domain.constants import (
    BATTLE_ANCHOR_X, BATTLE_ANCHOR_Y, BATTLE_ANCHOR_X_RAISED, BATTLE_ANCHOR_Y_RAISED,
    BATTLE_ANCHOR_X_SHIFT, BATTLE_ANCHOR_Y_EPIC, EFFICIENCY_WIDE_THRESHOLD,
    MINIMAP_SIZES, MM_GAP, PROGRESS_MM_GAP_BOTTOM, EFFICIENCY_MM_GAP_BOTTOM,
    MM_TICK_OVERHANG, MM_TICK_OVERHANG_LARGE,
    VERTICAL_ANCHOR_Y_SHIFT, VERTICAL_ANCHOR_Y_SHIFT_LARGE)


# Measured movable extents (space - 256 surface) at 4K.
_EXTENT_1X = (3584, 1904)   # logical space 3840x2160
_EXTENT_2X = (1664, 824)    # logical space 1920x1080


def test_fixed_offset_is_scale_invariant():
    # The whole point of Phase 1: the SAME logical offset (266 from left, bottom-flush) at
    # BOTH scales -- reproducing the 2x-aligned placement at 1x (where the old fraction anchor
    # wrongly landed at x=529). X is identical; Y is bottom-flush (= each scale's max_y).
    x1, y1 = anchor_top_left(_EXTENT_1X[0], _EXTENT_1X[1], BATTLE_ANCHOR_X, BATTLE_ANCHOR_Y)
    x2, y2 = anchor_top_left(_EXTENT_2X[0], _EXTENT_2X[1], BATTLE_ANCHOR_X, BATTLE_ANCHOR_Y)
    assert (x1, y1) == (266, 1904)
    assert (x2, y2) == (266, 824)
    assert x1 == x2 == 266  # X does not change with scale


def test_y_from_bottom_raises_the_panel():
    # A positive y_from_bottom moves the top-left UP (smaller y) -- the Phase-2 raised anchor.
    _, y0 = anchor_top_left(3584, 1904, 264, 0)
    _, y200 = anchor_top_left(3584, 1904, 264, 200)
    assert y0 == 1904
    assert y200 == 1704
    assert y200 < y0


def test_clamps_x_into_movable_extent():
    # An offset past the right edge clamps to max_x (never off-screen).
    x, _ = anchor_top_left(1664, 824, 99999, 0)
    assert x == 1664


def test_clamps_y_non_negative():
    # A y_from_bottom larger than the whole extent clamps the top-left to 0 (top edge), not
    # a negative off-screen coordinate.
    _, y = anchor_top_left(3584, 1904, 264, 99999)
    assert y == 0


def test_zero_offsets_sit_at_bottom_left_corner():
    x, y = anchor_top_left(3584, 1904, 0, 0)
    assert (x, y) == (0, 1904)


# --- Phase 2: damage-log-summary-aware anchor -------------------------------
# The "Summarized damage" group is four flags. When ALL four are unticked, the summary
# block disappears and the damage-log events shift UP, so the overlay must use the raised
# anchor. Any one flag ticked -> the block is present -> default anchor.


def test_summary_hidden_only_when_all_four_unticked():
    assert damage_log_summary_hidden(False, False, False, False) is True


def test_summary_visible_when_any_single_flag_ticked():
    # Each of the four flags on its own keeps the summary block present (default anchor).
    assert damage_log_summary_hidden(True, False, False, False) is False
    assert damage_log_summary_hidden(False, True, False, False) is False
    assert damage_log_summary_hidden(False, False, True, False) is False
    assert damage_log_summary_hidden(False, False, False, True) is False


def test_summary_visible_when_all_ticked():
    assert damage_log_summary_hidden(True, True, True, True) is False


def test_summary_hidden_coerces_truthy_falsey():
    # getSetting returns the stored value (may be 0/1 or None); bool()-coercion means
    # 0/None read as unticked and any truthy value reads as ticked.
    assert damage_log_summary_hidden(0, 0, 0, 0) is True
    assert damage_log_summary_hidden(None, None, None, None) is True
    assert damage_log_summary_hidden(0, 1, 0, 0) is False


def test_raised_anchor_is_higher_than_default():
    # The raised anchor must sit ABOVE the default (larger y_from_bottom -> smaller top y).
    # Guards against someone leaving the two constants equal (Phase 2 would then be a no-op).
    assert BATTLE_ANCHOR_Y_RAISED > BATTLE_ANCHOR_Y


def test_raised_anchor_has_its_own_x():
    # Phase 2's raised anchor carries its own X (calibrated left of the default here), which
    # must be a valid on-screen offset and independent of the signed-off default X.
    assert BATTLE_ANCHOR_X_RAISED >= 0
    assert BATTLE_ANCHOR_X == 266  # default X (Phase 1 264 + 2rem right nudge)


def test_raised_anchor_places_left_and_up_of_default():
    # With the calibrated raised anchor, the window sits left of and above the default
    # placement (same movable extent). Concrete regression check on the shipped values.
    xd, yd = anchor_top_left(3584, 1904, BATTLE_ANCHOR_X, BATTLE_ANCHOR_Y)
    xr, yr = anchor_top_left(3584, 1904, BATTLE_ANCHOR_X_RAISED, BATTLE_ANCHOR_Y_RAISED)
    assert xr < xd   # raised X (215) < default X (266)
    assert yr < yd   # raised (33 from bottom) -> smaller top y than bottom-flush


# --- Frontlines/Epic extra raise (ADDITIVE on top of default OR raised) ----
# battle_view._place calls domain.positioning.battle_y_anchor(raised, is_epic) for
# y_from_bottom -- it is not a third, standalone anchor. `raised` comes from
# damage_log_summary_hidden; `is_epic` from battle_adapter.read_is_epic_battle (engine-coupled,
# reads BigWorld.player().arena.bonusType) -- exercise battle_y_anchor itself directly so
# dropping the epic term in the bridge cannot leave this test green.


def test_battle_y_anchor_all_four_combinations():
    assert battle_y_anchor(False, False) == BATTLE_ANCHOR_Y
    assert battle_y_anchor(False, True) == BATTLE_ANCHOR_Y + BATTLE_ANCHOR_Y_EPIC
    assert battle_y_anchor(True, False) == BATTLE_ANCHOR_Y_RAISED
    assert battle_y_anchor(True, True) == BATTLE_ANCHOR_Y_RAISED + BATTLE_ANCHOR_Y_EPIC


# --- 5-digit efficiency-panel right-shift -----------------------------------
# When an ENABLED "Summarized damage" total goes 5-digit (> EFFICIENCY_WIDE_THRESHOLD), WG's
# panel widens and the overlay shifts right by BATTLE_ANCHOR_X_SHIFT. flags/values are aligned
# (total, blocked, assist, stun): flags = which totals are drawn, values = their amounts.
_ALL_ON = (True, True, True, True)
_ALL_OFF = (False, False, False, False)
_T = EFFICIENCY_WIDE_THRESHOLD


def test_wide_when_an_enabled_total_exceeds_threshold():
    assert efficiency_panel_wide(_ALL_ON, (10000, 0, 0, 0), _T) is True


def test_not_wide_when_high_total_is_disabled():
    # A 5-digit total whose summary flag is unticked isn't drawn -> can't widen the panel.
    assert efficiency_panel_wide((False, True, True, True), (10000, 0, 0, 0), _T) is False


def test_not_wide_when_enabled_totals_below_threshold():
    assert efficiency_panel_wide(_ALL_ON, (9999, 9999, 9999, 9999), _T) is False


def test_threshold_is_strict_boundary():
    # Exactly 9999 (4 digits) does NOT widen; 10000 (5 digits) does.
    assert efficiency_panel_wide(_ALL_ON, (9999, 0, 0, 0), _T) is False
    assert efficiency_panel_wide(_ALL_ON, (10000, 0, 0, 0), _T) is True


def test_not_wide_all_zero():
    assert efficiency_panel_wide(_ALL_ON, (0, 0, 0, 0), _T) is False


def test_wide_checks_each_enabled_column():
    # Any single enabled 5-digit total (blocked / assist / stun) triggers the shift.
    assert efficiency_panel_wide(_ALL_ON, (0, 12000, 0, 0), _T) is True
    assert efficiency_panel_wide(_ALL_ON, (0, 0, 12000, 0), _T) is True
    assert efficiency_panel_wide(_ALL_ON, (0, 0, 0, 12000), _T) is True


def test_not_wide_when_all_flags_off():
    # No totals drawn at all (raised-anchor case) -> never widened, whatever the values.
    assert efficiency_panel_wide(_ALL_OFF, (50000, 50000, 50000, 50000), _T) is False


def test_wide_coerces_flag_and_guards_none_value():
    # getSetting flags may be 0/1/None; a value may read None on a bad fetch -> treated as 0.
    assert efficiency_panel_wide((1, 0, 0, 0), (10000, None, None, None), _T) is True
    assert efficiency_panel_wide((0, 0, 0, 0), (10000, 0, 0, 0), _T) is False
    assert efficiency_panel_wide((1, 0, 0, 0), (None, 0, 0, 0), _T) is False


def test_shift_constant_is_positive():
    # A positive addend shifts the window RIGHT (x measured from the left edge). Guards against
    # the constant being left at 0 (the feature would then be a silent no-op).
    assert BATTLE_ANCHOR_X_SHIFT > 0


def test_shift_composes_with_default_anchor():
    # The shift adds to the DEFAULT anchor's X; the shifted placement sits right of the unshifted
    # one (same movable extent).
    xd, _ = anchor_top_left(3584, 1904, BATTLE_ANCHOR_X, BATTLE_ANCHOR_Y)
    xd_s, _ = anchor_top_left(3584, 1904, BATTLE_ANCHOR_X + BATTLE_ANCHOR_X_SHIFT, BATTLE_ANCHOR_Y)
    assert xd_s > xd


def test_shift_never_applies_in_the_raised_state():
    # The raised anchor means the summary block is COLLAPSED (all four flags off) -- WG doesn't
    # draw the totals, so nothing can widen and the shift must not fire. efficiency_panel_wide is
    # the gate _place uses; with every flag off it is False regardless of how huge the values are.
    assert efficiency_panel_wide(_ALL_OFF, (99999, 99999, 99999, 99999), _T) is False


def test_wide_does_not_truncate_on_short_values_tuple():
    # A fail-soft adapter read that returns FEWER values than flags must not silently drop the
    # trailing column via zip-truncation: a 5-digit total there would be missed and the overlay
    # would collide with the widened panel. The missing value defaults to 0 (no false shift)...
    assert efficiency_panel_wide(_ALL_ON, (0, 0, 0), _T) is False
    # ...and a short FLAGS tuple with a wide value present still fires (missing flag = ticked).
    assert efficiency_panel_wide((True,), (0, 0, 0, 12000), _T) is True


# --- THE ABSOLUTE Ctrl+drag MAPPING (cursor -> window top-left) ---------------------------------
# The drag is ABSOLUTE, not incremental: no reported delta, so no gain factor to get wrong and no
# dependence on the surface's own mouse hit rect (a delta protocol had both, and the cursor kept
# escaping the bar-sized rect). `cursor_logical` + `cursor_top_left` are the whole mapping, and they
# are UNIT-AGNOSTIC by construction because the two decompiled call sites of GUI.mcursor().position
# disagree about the units (armor/utils.py's ray cast is clip space [-1, 1]; radial_menu.py pairs a
# cursor pair with GUI.screenResolution()).
#
# THE MAPPING TAKES THE LOGICAL SPACE, NEVER THE MOVABLE EXTENT: the cursor fraction scales onto the
# space (1920x1080 below). Scaling onto the extent instead (space - surface, all a far-sentinel clamp
# can recover on its own) bakes in a gain of (space - surface) / space, measured ~0.74 on x. The
# extent used to be the CLAMP argument; there is no clamp any more (no on-screen safezone), so the
# mapping does not see it at all.
_SPACE = (1920, 1080)
_ARGS = _SPACE                      # (space_x, space_y)


def test_the_cursor_mapping_gain_is_exactly_one_in_pixel_space():
    # THE ACCEPTANCE CRITERION, and it is arithmetic: a cursor traversal of N logical units must move
    # the window N logical units. Anything less is "the bar moves slower than the cursor" -- the live
    # symptom the whole absolute mapping exists to kill.
    a = cursor_top_left((400, 200), _SPACE, *_ARGS)
    b = cursor_top_left((900, 500), _SPACE, *_ARGS)
    assert (b[0] - a[0], b[1] - a[1]) == (500, 300)


def test_the_cursor_mapping_gain_is_exactly_one_in_clip_space():
    # ...and at the OTHER unit convention, where the same 500x300 logical traversal is a clip-space
    # delta of 2*500/1920 on x and -2*300/1080 on y (clip y is UP).
    a = cursor_top_left((-1.0 + 2 * 400 / 1920.0, 1.0 - 2 * 200 / 1080.0), None, *_ARGS)
    b = cursor_top_left((-1.0 + 2 * 900 / 1920.0, 1.0 - 2 * 500 / 1080.0), None, *_ARGS)
    assert (b[0] - a[0], b[1] - a[1]) == (500, 300)


def test_the_cursor_maps_to_its_own_logical_position_not_a_share_of_the_extent():
    # The gain of 1 stated as a single point rather than a difference: the window's corner goes to the
    # cursor's LOGICAL coordinate. Dead centre of a 1920x1080 space is 960/540 -- NOT the extent's
    # midpoint (832/412), which is what the superseded extent-scaled mapping produced.
    assert cursor_top_left((0.0, 0.0), _SPACE, *_ARGS) == (960, 540)
    assert cursor_top_left((960, 540), _SPACE, *_ARGS) == (960, 540)


def test_cursor_maps_clip_space_corners_to_the_space_corners_unclamped():
    # The screen corners map to the SPACE corners, not to the movable extent: nothing clamps.
    # (0, 0) used to be nudged off the retired anchor_pinned AUTO sentinel; under Free alignment
    # it is just the screen origin now, an ordinary position like any other, so the top-left maps
    # to it VERBATIM -- no nudge.
    assert cursor_top_left((-1.0, 1.0), _SPACE, *_ARGS) == (0, 0)          # top-left, verbatim
    assert cursor_top_left((1.0, -1.0), _SPACE, *_ARGS) == (1920, 1080)    # bottom-right, un-clamped


def test_cursor_maps_pixel_space_against_the_screen_resolution():
    # The OTHER convention: components larger than 1 are device px and normalise against
    # GUI.screenResolution(). Screen y is DOWN from the top, so no flip here.
    assert cursor_top_left((1920, 1080), _SPACE, *_ARGS) == (1920, 1080)


def test_cursor_reads_a_vector2_as_well_as_a_plain_pair():
    # GUI.mcursor().position is a Vector2 (armor/utils.py reads .x/.y; radial_menu.py unpacks it),
    # so BOTH shapes must map identically -- a plain pair is what the tests and any fail-soft
    # fallback hand in.
    class _V(object):
        x = 0.0
        y = 0.0

    assert cursor_top_left(_V(), _SPACE, *_ARGS) == (960, 540)


def test_cursor_preserves_the_grab_offset():
    # THE DIFFERENCE BETWEEN "picks up where you grabbed it" AND "snaps": the offset recorded
    # between the window's top-left and the cursor at gesture start is carried for the whole
    # gesture, so the first movement event does not teleport the corner under the cursor.
    spot = cursor_logical((0.0, 0.0), _SPACE, *_SPACE)
    grab = (200 - spot[0], 100 - spot[1])            # the bar was grabbed while sitting at 200/100
    # Re-mapping the SAME cursor with that offset must reproduce the untouched position exactly.
    assert cursor_top_left((0.0, 0.0), _SPACE, *(_ARGS + grab)) == (200, 100)


def test_the_grab_offset_is_measured_UNCLAMPED():
    # cursor_logical must NOT clamp: the screen's bottom-right corner sits BEYOND the movable extent
    # by the surface size, so grabbing a bar there and clamping the measurement would bake a
    # 256-logical-px error into the offset for the rest of the gesture.
    assert cursor_logical((1.0, -1.0), _SPACE, *_SPACE) == (1920.0, 1080.0)
    # Proven end to end: grab at the far corner, then a 300px-left traversal moves the bar 300 left.
    spot = cursor_logical((1.0, -1.0), _SPACE, *_SPACE)
    grab = (1400 - spot[0], 700 - spot[1])           # the bar was sitting at 1400/700
    assert cursor_top_left((1620, 1080), _SPACE, *(_ARGS + grab)) == (1100, 700)


def test_cursor_drags_past_the_top_left_edge_into_negative_coordinates():
    # NO SAFEZONE: dragging off the left/top edge is allowed, so the grab offset carries the result
    # straight into negative logical px instead of being clamped back on screen.
    assert cursor_top_left((-1.0, 1.0), _SPACE, *(_ARGS + (-500, -500))) == (-500, -500)


def test_cursor_drags_past_the_bottom_right_edge():
    assert cursor_top_left((1.0, -1.0), _SPACE, *(_ARGS + (500, 500))) == (2420, 1580)


def test_cursor_lands_on_the_origin_pair_verbatim_no_nudge():
    # The retired anchor_pinned used (0, 0) as its "never dragged" AUTO sentinel, so a drag landing
    # exactly there once had to be nudged one px off it. That sentinel is gone (offset (0, 0) under
    # Damage Log alignment IS the shipped placement now, byte-for-byte -- there is nothing left to
    # distinguish an "auto" case from), so cursor_top_left must return the exact origin, untouched.
    assert cursor_top_left((-1.0, 1.0), _SPACE, *_ARGS) == (0, 0)
    assert cursor_top_left((-1.0, 1.0), _SPACE, *(_ARGS + (0, 300))) == (0, 300)
    assert cursor_top_left((-1.0, 1.0), _SPACE, *(_ARGS + (300, 0))) == (300, 0)


# --- THE DRAG'S OWNERSHIP GATE (which host owns the gesture) ------------------------------------
# Ctrl+left-button is sampled GLOBALLY off WG's input dispatchers and handed to every open bar, so
# without a rect test a Ctrl+drag anywhere on screen dragged whichever bar was open -- including while
# the user was dragging another mod's window. A host claims a gesture only if it began on its own box.
_BAR = (832, 748)                   # a centred 256x256 bar's top-left, from anchor_centred above
_SIZE = (256, 256)


def test_cursor_in_rect_claims_only_inside_the_hosts_own_box():
    assert cursor_in_rect((900, 800), _BAR, _SIZE) is True
    # Both EDGES are inside: the rect is the window's surface and its far edge is a real place to grab.
    assert cursor_in_rect(_BAR, _BAR, _SIZE) is True
    assert cursor_in_rect((1088, 1004), _BAR, _SIZE) is True
    # One axis outside is outside -- the screen centre sits ABOVE this bar, which is exactly the
    # "grabbed some other mod's UI" case.
    assert cursor_in_rect((960, 540), _BAR, _SIZE) is False
    assert cursor_in_rect((100, 800), _BAR, _SIZE) is False
    assert cursor_in_rect((1089, 800), _BAR, _SIZE) is False
    assert cursor_in_rect((900, 1005), _BAR, _SIZE) is False


def test_cursor_in_rect_reads_a_vector2_and_fails_soft_to_not_claiming():
    class _V(object):
        x = 900.0
        y = 800.0

    assert cursor_in_rect(_V(), _BAR, _SIZE) is True
    # FAIL SOFT TO FALSE: an unreadable point / origin / size means "do not claim", which loses a
    # gesture rather than stealing one.
    assert cursor_in_rect(None, _BAR, _SIZE) is False
    assert cursor_in_rect((900, 800), None, _SIZE) is False
    assert cursor_in_rect((900, 800), _BAR, None) is False
    assert cursor_in_rect((float("nan"), 800), _BAR, _SIZE) is False


def test_cursor_fails_soft_on_an_unreadable_cursor():
    # None means "leave the window exactly where it is" -- a bad engine read must never move the
    # bar and must never raise into the input path.
    assert cursor_top_left(None, _SPACE, *_ARGS) is None
    assert cursor_top_left("nope", _SPACE, *_ARGS) is None
    assert cursor_top_left((0.0,), _SPACE, *_ARGS) is None
    assert cursor_top_left((float("nan"), 0.0), _SPACE, *_ARGS) is None
    assert cursor_logical(None, _SPACE, *_SPACE) is None


def test_cursor_fails_soft_when_a_pixel_read_has_no_usable_resolution():
    # A pixel-space cursor is meaningless without the resolution to normalise it against, so an
    # unreadable / zero / non-numeric resolution is also "leave it alone" -- never a divide by zero.
    assert cursor_top_left((960, 540), None, *_ARGS) is None
    assert cursor_top_left((960, 540), (0, 0), *_ARGS) is None
    assert cursor_top_left((960, 540), ("a", "b"), *_ARGS) is None
    # ...but a CLIP-space read needs no resolution at all, so it still maps.
    assert cursor_top_left((0.0, 0.0), None, *_ARGS) == (960, 540)


# --- Phase 2 (in-battle vertical bar): anchor_minimap ----------------------------------------
# `x = space_x - mm_size - gap - overhang - edge_x`, `y = space_y - gap_bottom - edge_y`.
# `edge_x`/`edge_y` are the ALIGNED EDGE's own offset from the surface's top-left corner (the
# track's position inside the surface), NOT the surface's own width/height -- passing the
# surface size (the shipped bug) aligns the wrong frame. UNCLAMPED -- there is no
# movable-extent argument here at all, matching the module's no-safezone rule for
# anchor_pinned / cursor_top_left.

def test_minimap_anchor_formula():
    x, y = anchor_minimap(space_x=1920, space_y=1080, edge_x=60, edge_y=200,
                          mm_size=228, gap=8, gap_bottom=30, overhang=3)
    assert x == 1920 - 228 - 8 - 3 - 60
    assert y == 1080 - 30 - 200
    assert (x, y) == (1621, 850)


def test_minimap_anchor_changes_with_each_argument_independently():
    # A regression against the formula silently degenerating to a subset of its terms: nudge one
    # argument at a time and confirm ONLY the axis it belongs to moves, by exactly that amount.
    base = anchor_minimap(1920, 1080, 60, 200, 228, 8, 30, 3)
    assert anchor_minimap(1921, 1080, 60, 200, 228, 8, 30, 3) == (base[0] + 1, base[1])
    assert anchor_minimap(1920, 1081, 60, 200, 228, 8, 30, 3) == (base[0], base[1] + 1)
    assert anchor_minimap(1920, 1080, 61, 200, 228, 8, 30, 3) == (base[0] - 1, base[1])
    assert anchor_minimap(1920, 1080, 60, 201, 228, 8, 30, 3) == (base[0], base[1] - 1)
    assert anchor_minimap(1920, 1080, 60, 200, 229, 8, 30, 3) == (base[0] - 1, base[1])
    assert anchor_minimap(1920, 1080, 60, 200, 228, 9, 30, 3) == (base[0] - 1, base[1])
    assert anchor_minimap(1920, 1080, 60, 200, 228, 8, 31, 3) == (base[0], base[1] - 1)
    assert anchor_minimap(1920, 1080, 60, 200, 228, 8, 30, 4) == (base[0] - 1, base[1])


def test_minimap_anchor_is_unclamped_and_can_go_negative():
    # A small enough space or wide enough bar legitimately pushes x/y negative -- there is nothing
    # to clamp against here (no movable-extent argument on hand), matching anchor_pinned's rule.
    x, y = anchor_minimap(space_x=100, space_y=100, edge_x=200, edge_y=200,
                          mm_size=228, gap=8, gap_bottom=30, overhang=3)
    assert x < 0 and y < 0


def test_minimap_anchor_degrades_fail_soft_on_every_unusable_arg():
    # Every argument goes through _int(): None / non-numeric / NaN degrades to 0 rather than
    # raising, so an unreadable minimap-size or surface measurement lands the bar at a
    # wrong-but-numeric spot instead of crashing the placement path.
    assert anchor_minimap(None, None, None, None, None, None, None, None) == (0, 0)
    assert anchor_minimap("x", "y", "w", "h", "mm", "g", "gb", "o") == (0, 0)
    # A single NaN argument degrades to 0 rather than poisoning the whole sum with a NaN result.
    x_clean, y_clean = anchor_minimap(1920, 1080, 60, 200, 228, 8, 30, 3)
    x_nan, y_nan = anchor_minimap(1920, 1080, 60, 200, 228, 8, 30, float("nan"))
    assert (x_nan, y_nan) == (x_clean + 3, y_clean), \
        "a NaN overhang must degrade to 0 (dropping the -3), not poison the whole sum"


# --- Phase 2: anchor_offset --------------------------------------------------------------------
# `x, y = anchor(alignment, orientation) + (off_x, off_y)` -- adds a stored stepper offset to
# whichever base anchor the alignment selected, uniformly and unclamped.

def test_offset_adds_to_the_base_anchor_on_both_axes():
    assert anchor_offset((100, 200), off_x=10, off_y=-5) == (110, 195)
    assert anchor_offset((0, 0), off_x=0, off_y=0) == (0, 0)


def test_offset_reads_a_vector2_style_anchor_too():
    class _V(object):
        x = 50.0
        y = 60.0

    assert anchor_offset(_V(), off_x=1, off_y=2) == (51, 62)


def test_offset_has_no_side_effect_on_the_base_anchors_own_inputs():
    # Composing an offset on top of a base anchor must not mutate whatever produced that anchor --
    # anchor_offset only ever reads its `anchor` argument.
    base = (100, 200)
    anchor_offset(base, off_x=999, off_y=999)
    assert base == (100, 200)


def test_offset_is_unclamped():
    # Matches the module's no-safezone rule: a user-configurable nudge may push the bar past any
    # edge, whether the base anchor was itself clamped (anchor_centred_reduced) or not
    # (anchor_minimap).
    assert anchor_offset((0, 0), off_x=-99999, off_y=99999) == (-99999, 99999)


def test_offset_degrades_unusable_anchor_to_origin_before_adding():
    assert anchor_offset(None, off_x=5, off_y=7) == (5, 7)
    assert anchor_offset("nonsense", off_x=5, off_y=7) == (5, 7)
    assert anchor_offset((float("nan"), 0), off_x=5, off_y=7) == (5, 7)


def test_offset_degrades_unusable_offsets_to_zero():
    assert anchor_offset((10, 20), off_x=None, off_y="bad") == (10, 20)


# --- Trap 3 Fix B: free_top_left / free_anchor_point --------------------------------------------
# The stored Free pair as an ANCHOR POINT (bottom-centre horizontal / bottom-right vertical),
# converted into a top-left using the LIVE surface size (free_top_left) or the reverse
# (free_anchor_point, used only to materialise/convert a pair -- see bar_window.BarHost).
# Default AND Large sizes below stand in for "both sizes" (Rule 5): the whole point of the anchor
# frame is that neither of these two functions needs to know which size it is -- only the surface.

_SURFACE_DEFAULT = (256, 92)     # a real Moving Average default surface
_SURFACE_LARGE = (356, 132)      # its Large-mode stand-in (arbitrary but bigger on both axes)


def test_free_top_left_horizontal_is_bottom_centre():
    # pair (100, 500), surface 256x92: bottom-centre means (pair_x - surface_w // 2, pair_y - surface_h).
    assert free_top_left((100, 500), _SURFACE_DEFAULT, False) == (100 - 128, 500 - 92)


def test_free_top_left_vertical_is_bottom_right():
    assert free_top_left((100, 500), _SURFACE_DEFAULT, True) == (100 - 256, 500 - 92)


def test_free_top_left_reanchors_across_both_sizes_without_moving_the_anchor():
    # RULE 5, stated directly: the SAME anchor point, converted at two different surface sizes,
    # must keep the anchor's own point fixed -- i.e. the bottom-centre (horizontal) / bottom-right
    # (vertical) corner of the two resulting rects must be identical, even though the top-lefts
    # differ because the surfaces differ.
    pair = (700, 900)
    for vertical in (False, True):
        tl_default = free_top_left(pair, _SURFACE_DEFAULT, vertical)
        tl_large = free_top_left(pair, _SURFACE_LARGE, vertical)
        if vertical:
            anchor_default = (tl_default[0] + _SURFACE_DEFAULT[0], tl_default[1] + _SURFACE_DEFAULT[1])
            anchor_large = (tl_large[0] + _SURFACE_LARGE[0], tl_large[1] + _SURFACE_LARGE[1])
        else:
            anchor_default = (tl_default[0] + _SURFACE_DEFAULT[0] // 2, tl_default[1] + _SURFACE_DEFAULT[1])
            anchor_large = (tl_large[0] + _SURFACE_LARGE[0] // 2, tl_large[1] + _SURFACE_LARGE[1])
        assert anchor_default == anchor_large == pair, \
            "vertical=%r: the anchor point moved across a size change" % vertical


def test_free_top_left_degrades_unusable_pair_or_surface_to_origin():
    assert free_top_left(None, _SURFACE_DEFAULT, False) == (-128, -92)
    assert free_top_left((100, 500), None, False) == (100, 500)
    assert free_top_left((float("nan"), 0), _SURFACE_DEFAULT, False) == (-128, -92)


def test_free_anchor_point_is_the_exact_inverse_of_free_top_left():
    # Exact, not approximate: both directions are plain int arithmetic on the SAME surface-derived
    # term, so the round trip must be bit-exact -- no bound needed here (contrast
    # anchor_centred_reduced vs anchor_centred, which DO admit a +/-1px int-floor divergence).
    for surface in (_SURFACE_DEFAULT, _SURFACE_LARGE):
        for vertical in (False, True):
            for pair in ((0, 0), (100, 500), (-40, 900), (12345, -6789)):
                top_left = free_top_left(pair, surface, vertical)
                assert free_anchor_point(top_left, surface, vertical) == pair


def test_free_anchor_point_horizontal_and_vertical():
    assert free_anchor_point((-28, 408), _SURFACE_DEFAULT, False) == (-28 + 128, 408 + 92)
    assert free_anchor_point((-156, 408), _SURFACE_DEFAULT, True) == (-156 + 256, 408 + 92)


def test_free_anchor_point_degrades_unusable_top_left_or_surface_to_origin():
    assert free_anchor_point(None, _SURFACE_DEFAULT, False) == (128, 92)
    assert free_anchor_point((100, 500), None, False) == (100, 500)


# --- Phase 2: anchor_centred_reduced -----------------------------------------------------------
# The computed successor to anchor_centred: same X (`max_x // 2`, ignoring space_* entirely) and
# the same [0, max_y] Y clamp, but Y is `int(space_y * y_frac) + y_shift` instead of
# `int(max_y * y_frac) + y_offset` -- see TASKS/in-battle-vertical-bar-PLAN.md "Phase 2 approach".

def test_reduced_x_uses_the_extent_and_ignores_space_entirely():
    # X must match `max_x // 2` in BOTH functions, and must not move when space_x changes -- the
    # reduction never even takes a space_x argument, which is the invariant this pins.
    for space_y in (720, 1080, 1440, 2160):
        x_old, _ = anchor_centred(3584, 1904, 0.5, 0, 0)
        x_new, _ = anchor_centred_reduced(3584, 1904, space_y, 0.5, 0)
        assert x_old == x_new == 3584 // 2


def test_reduced_y_clamps_into_zero_and_max_y_both_directions():
    # A huge POSITIVE shift clamps to max_y (never past the bottom of the movable extent)...
    _, y_hi = anchor_centred_reduced(100, 500, 1080, 0.5, 999999)
    assert y_hi == 500
    # ...and a huge NEGATIVE shift clamps to 0 (never off the top), matching anchor_centred's own
    # existing [0, max_y] clamp exactly.
    _, y_lo = anchor_centred_reduced(100, 500, 1080, 0.5, -999999)
    assert y_lo == 0


def test_reduced_matches_the_shipped_horizontal_placement_within_one_px():
    # THE MEASURED, NOT ASSUMED claim: int(space_y * frac) is int-of-sum where anchor_centred's
    # form is sum-of-rounded-parts, so the two can differ by +/-1 logical px depending on the
    # exact space_y -- NEVER a fixed delta (memory `anchor-y-reduction-is-not-bit-exact`). Each
    # (bar, size) pair's PURE shift term (SHIFT_Y_REM * SIZE_F, un-rounded-summed with the
    # fraction term) is derived here from the shipped TWO-term composites so this test moves with
    # them rather than hand-duplicating a second copy of the constants:
    #   progress default: composite 36 == -44 + round(0.865*92)   -> pure shift -44, surface_h 92
    #   progress large:    composite 44 == -55 + round(0.865*115) -> pure shift -55, surface_h 115
    #   efficiency default:composite 50 == -50 + round(0.865*116) -> pure shift -50, surface_h 116
    #   efficiency large:  composite 62 == -63 + round(0.865*145) -> pure shift -63, surface_h 145
    cases = (
        ("progress default", 92, 36, -44),
        ("progress large", 115, 44, -55),
        ("efficiency default", 116, 50, -50),
        ("efficiency large", 145, 62, -63),
    )
    frac = 0.865
    max_x = 3584
    # A wide RESOLUTION SWEEP -- wide enough to actually exercise the jitter (a narrow sweep could
    # land on all-0 or all-+1 by accident and hide the -1 branch).
    seen_deltas = set()
    for space_y in range(600, 4000, 7):
        for name, surface_h, offset, shift in cases:
            max_y = space_y - surface_h
            x_old, y_old = anchor_centred(max_x, max_y, frac, 0, offset)
            x_new, y_new = anchor_centred_reduced(max_x, max_y, space_y, frac, shift)
            assert x_old == x_new
            delta = y_new - y_old
            assert abs(delta) <= 1, (
                "%s at space_y=%d drifted by %d (must be a bounded jitter, never more)" %
                (name, space_y, delta))
            seen_deltas.add(delta)
    # The jitter must actually JITTER across the sweep -- a test that only ever saw 0 would not
    # have caught a regression that widened the bound to +/-2 only at some other resolution, and
    # a fixed-delta pin (rejected by the plan) would have looked identical to this at one point.
    assert seen_deltas == {-1, 0, 1}, (
        "the sweep did not exercise the full -1/0/+1 jitter: %r" % (seen_deltas,))
    # ...and the concrete measured deltas at 1080p, pinned as the maintainer's own report records
    # them (not re-derived): progress default 0, progress Large +1, efficiency default +1,
    # efficiency Large +1.
    expected_at_1080 = {"progress default": 0, "progress large": 1,
                        "efficiency default": 1, "efficiency large": 1}
    for name, surface_h, offset, shift in cases:
        max_y = 1080 - surface_h
        _, y_old = anchor_centred(max_x, max_y, frac, 0, offset)
        _, y_new = anchor_centred_reduced(max_x, max_y, 1080, frac, shift)
        assert y_new - y_old == expected_at_1080[name]


# DELETED (v23, the Fixed-alignment redesign): test_reduced_x_shift_defaults_to_zero_and_is_pure_
# centring / test_reduced_x_shift_moves_x_left_and_clamps_into_the_extent. anchor_centred_reduced's
# `x_shift` parameter is gone -- it existed only for a VERTICAL bar resolving to the Damage Log
# anchor under Large (rule 5's right-pin), a combination that is no longer reachable through the
# UI or a stored value at all (Alignment only ever stores Fixed or Free; Fixed always resolves to
# Minimap when vertical -- see bar_window._resolve and mod_settings.py's SETTINGS_VERSION 22->23
# comment). Every remaining call site is horizontal, where pure `max_x // 2` centring was always
# already size-invariant with no shift term at all.

# --- Phase 2: new constants mirror the vertical CSS tuner's live defaults -----------------------

def test_minimap_size_table_matches_the_measured_geometry():
    assert MINIMAP_SIZES == (228, 279, 329, 409, 510, 628)
    assert len(MINIMAP_SIZES) == 6   # settingsCore's index range is [0, 5]


def test_minimap_clearance_constants_match_the_tuner_defaults():
    assert MM_GAP == 8
    assert PROGRESS_MM_GAP_BOTTOM == 30
    assert EFFICIENCY_MM_GAP_BOTTOM == 28


def test_minimap_gap_bottom_constants_are_genuinely_per_bar():
    # A regression against re-merging the two tuners' clearances back into one shared constant --
    # they differ ON SCREEN now that the front-end change freed the slack (see constants.py).
    assert PROGRESS_MM_GAP_BOTTOM != EFFICIENCY_MM_GAP_BOTTOM


def test_minimap_tick_overhang_scales_by_the_large_x_length_factor():
    # trackW=3, tickW*=9 -> overhang == (9-3)/2 == 3 at 1x; LARGE scales by SIZE_F*SIZE_XF ==
    # 1.25*4/3 == 5/3 exactly, so 3 * 5/3 == 5 with no rounding ambiguity.
    assert MM_TICK_OVERHANG == 3
    assert MM_TICK_OVERHANG_LARGE == 5
    assert MM_TICK_OVERHANG_LARGE == MM_TICK_OVERHANG * 5 // 3


def test_the_vertical_track_x_terms_are_pure_composition_derivations():
    # *_MM_TRACK_X is "where the track sits inside the surface", derived from the JS's V_BOX_LEFT_REM
    # + that bar's own LEFT surface slack + trackW -- and NOTHING else, PLUS one MEASURED correction
    # on the Moving Average bar only: two independent Ctrl+drags, in two different surface
    # geometries, both landed its track 2 logical px to the right of the pure derivation (see
    # constants.py) -- a repeatable miss, not the scatter an earlier single drag looked like. The
    # Damage Efficiency bar's own single drag has since been inspected in-game and accepted as
    # correct AS DERIVED, so it gets no correction.
    #
    # THE X SLACK IS NOT PAD_REM ON EITHER BAR ANY MORE, and it has grown TWICE on each, both times
    # for the same reason: a caption's own translateX moved further left (more overflow) and the
    # pad had to grow with it or clip (see constants.py's own derivation history). The Moving
    # Average bar's vertical surface now reaches 70rem past its backdrop on EACH side
    # (MoEProgress.js's V_PAD_X_REM, up from 63 after the maintainer's "move the bottom block left
    # 7px" nudge); the Damage Efficiency bar's is 52rem (MoEEfficiency.js's V_PAD_X_REM, up from a
    # plain PAD_REM of 10, via an intermediate 14 that only checked the mark rows). This term is
    # what keeps the widened surface from sliding the bar right into the minimap on screen -- the
    # surface grew, the track did not move inside it.
    from moe_calculator.domain.constants import (
        PROGRESS_MM_TRACK_X, PROGRESS_MM_TRACK_X_LARGE,
        EFFICIENCY_MM_TRACK_X, EFFICIENCY_MM_TRACK_X_LARGE)

    # (70 + 34) + 3 == 107 and (70 + 34*4/3 + 3*4/3) * 1.25 == 119.333 * 1.25 == 149.167 -> 149 is
    # the PURE derivation; the shipped constant is that MINUS the flat -2 hand-placement correction
    # (105 / 147).
    assert (PROGRESS_MM_TRACK_X, PROGRESS_MM_TRACK_X_LARGE) == (105, 147)
    # (52 + 40) + 3 == 95 and (52 + 40*4/3 + 3*4/3) * 1.25 == 109.333 * 1.25 == 136.667 -> 137 --
    # no correction on top.
    assert (EFFICIENCY_MM_TRACK_X, EFFICIENCY_MM_TRACK_X_LARGE) == (95, 137)


def test_vertical_anchor_shift_is_identical_for_both_bars():
    # Unlike the horizontal siblings' 44-vs-50 split, both vertical compositions share the same
    # backdrop geometry, so ONE constant covers both bars.
    assert VERTICAL_ANCHOR_Y_SHIFT == -90
    # LARGE pins the composition's BOTTOM ink (rule 5, DECISION 3), not a naive SIZE_F scale-up of
    # the 1x shift (that pins the pre-shift coordinate instead -- see
    # domain/constants.PROGRESS_ANCHOR_Y_SHIFT_LARGE's header for the full derivation this mirrors):
    #   shift_large == shift_default - 0.25 * bottom_ink_default
    # The two vertical bars' own clipped surface heights differ (320 Moving Average / 318 Damage
    # Efficiency), so treating EITHER as bottom_ink_default gives a slightly different exact value
    # (-170.0 / -169.5) that both happen to round to the SAME shared -170 today. ASSERT A BOUND, NOT
    # EQUALITY against one bar's derivation alone -- a future retune of either bar's clipped height
    # must not silently pass here (memory `anchor-y-reduction-is-not-bit-exact`).
    for bottom_ink_default in (320, 318):
        computed = VERTICAL_ANCHOR_Y_SHIFT - 0.25 * bottom_ink_default
        assert abs(VERTICAL_ANCHOR_Y_SHIFT_LARGE - computed) <= 1
    assert VERTICAL_ANCHOR_Y_SHIFT_LARGE == -170
