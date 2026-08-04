# -*- coding: utf-8 -*-
"""Tests for the engine-free overlay-placement math. Runs on Python 3 (no game engine):
domain.positioning imports zero game symbols. The extents below are the REAL far-sentinel
readouts measured in-client at 4K (probe_scale.py): 1x -> space 3840x2160, 2x -> 1920x1080,
surface fixed 256x256, so movable extent = space - 256."""
from moe_calculator.domain.positioning import (
    anchor_centred, anchor_pinned, anchor_top_left, cursor_in_rect, cursor_logical,
    cursor_top_left, damage_log_summary_hidden, efficiency_panel_wide)
from moe_calculator.domain.constants import (
    BATTLE_ANCHOR_X, BATTLE_ANCHOR_Y, BATTLE_ANCHOR_X_RAISED, BATTLE_ANCHOR_Y_RAISED,
    BATTLE_ANCHOR_X_SHIFT, EFFICIENCY_WIDE_THRESHOLD)


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


# --- the in-battle bars' Ctrl+drag position ---------------------------------
# anchor_pinned wraps anchor_centred: a stored drag position (logical GUI px) takes over, and
# 0 means AUTO -- which is the whole compatibility story, since every existing install stores
# 0/0 and must land on the shipped anchor byte-for-byte.
_FRAC, _XOFF, _YOFF = 0.865, 0, 36      # the Moving Average bar's shipped anchor constants


def test_pinned_zero_is_auto_and_falls_back_to_the_shipped_anchor():
    # 0/0 == "never dragged", and it is the ONLY auto pair. The result must be anchor_centred's,
    # IDENTICALLY -- not merely close: this is the path every user who never touches the feature takes.
    auto = anchor_centred(3584, 1904, _FRAC, _XOFF, _YOFF)
    assert anchor_pinned(3584, 1904, 0, 0, _FRAC, _XOFF, _YOFF) == auto
    # A lone axis IS a pin now: a bar parked flush against the top or left edge legitimately stores
    # 0 on one axis, so only the exact (0, 0) pair may fall back.
    assert anchor_pinned(3584, 1904, 900, 0, _FRAC, _XOFF, _YOFF) == (900, 0)
    assert anchor_pinned(3584, 1904, 0, 900, _FRAC, _XOFF, _YOFF) == (0, 900)
    # A corrupt store still degrades to auto, because _int maps anything unusable to 0 on BOTH axes.
    assert anchor_pinned(3584, 1904, None, None, _FRAC, _XOFF, _YOFF) == auto
    assert anchor_pinned(3584, 1904, "x", "y", _FRAC, _XOFF, _YOFF) == auto


def test_a_stored_position_overrides_the_anchor_on_both_axes():
    assert anchor_pinned(3584, 1904, 900, 640, _FRAC, _XOFF, _YOFF) == (900, 640)
    # The anchor constants are then IGNORED -- a pin is absolute, not an offset from them.
    assert anchor_pinned(3584, 1904, 900, 640, 0.1, 999, -999) == (900, 640)


def test_a_stored_position_is_never_clamped_on_screen():
    # THERE IS NO SAFEZONE. The user may park a bar past any screen edge, so a pin is honoured
    # verbatim -- beyond the movable extent...
    assert anchor_pinned(1664, 824, 3000, 1800, _FRAC, _XOFF, _YOFF) == (3000, 1800)
    # ...and NEGATIVE, off the left/top edge, which the old [0, max] clamp used to teleport back.
    assert anchor_pinned(1664, 824, -400, -120, _FRAC, _XOFF, _YOFF) == (-400, -120)
    # A pin exactly AT the extent stays put too (nothing here reads max_x/max_y for a pin at all).
    assert anchor_pinned(1664, 824, 1664, 824, _FRAC, _XOFF, _YOFF) == (1664, 824)


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
    # The top-left lands on the forbidden (0, 0) AUTO sentinel, so x -- and only x -- is nudged to 1.
    assert cursor_top_left((-1.0, 1.0), _SPACE, *_ARGS) == (1, 0)          # top-left, nudged off 0/0
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


def test_cursor_never_emits_the_auto_sentinel_pair():
    # (0, 0) is anchor_pinned's "never dragged" sentinel, so a drag that lands exactly there must be
    # nudged off it -- otherwise releasing the mouse at the screen's top-left silently un-pins the bar
    # and the next placement jumps back to the shipped anchor. One px on x is the whole fix.
    assert cursor_top_left((-1.0, 1.0), _SPACE, *_ARGS) == (1, 0)
    # ...and it must be the ONLY nudge: either coordinate alone at 0 is a legal pin, untouched.
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
