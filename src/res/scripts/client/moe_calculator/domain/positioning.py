# -*- coding: utf-8 -*-
"""Pure, engine-free placement math for the in-battle overlay window.

The overlay is a fixed-size Wulf surface positioned in the engine's LOGICAL GUI space
(physical px / interfaceScale). WG's own efficiency panel is anchored at a FIXED LOGICAL
offset from the screen edge -- confirmed in-client at 1x and 2x: the panel corner sits at
the same logical coordinate regardless of interface scale. So we place our window at a fixed
logical offset too (see constants.BATTLE_ANCHOR_X/Y) -- NO per-scale multiplication -- and
just clamp it to the window's movable extent (space - surface), which the caller recovers
with a far-sentinel calibration.

Anchoring convention: x is measured from the LEFT edge, y from the BOTTOM edge (so a larger
y_from_bottom RAISES the panel -- that's the hook the Phase-2 damage-log-aware anchor uses).
2/3-compatible, engine-free, unit-testable with the client closed.
"""


def damage_log_summary_hidden(total, blocked, assist, assist_stun):
    """True when ALL FOUR "Summarized damage" DAMAGE_LOG flags are unticked.

    When every summary total (damage / blocked / assist-damage / assist-stun) is off, WG
    collapses the summary block and the damage-log events shift UP -- so the overlay must
    move to the raised anchor (constants.BATTLE_ANCHOR_Y_RAISED). Any one flag ticked keeps
    the block present -> default anchor. Each flag is bool()-coerced so getSetting's 0/1/None
    read correctly, and the fail-soft "treat an unreadable flag as ticked" default (see
    battle_adapter) lands on the DEFAULT anchor rather than wrongly raising the panel."""
    return not (bool(total) or bool(blocked) or bool(assist) or bool(assist_stun))


def efficiency_panel_wide(flags, values, threshold):
    """True when any ENABLED "Summarized damage" total exceeds `threshold` (goes 5-digit).

    A five-digit total widens WG's efficiency panel by one character, colliding with the
    overlay -- so the caller shifts the overlay right (constants.BATTLE_ANCHOR_X_SHIFT). Only
    ENABLED totals count: a huge value whose summary flag is unticked isn't drawn, so it can't
    widen the panel. `flags` and `values` are aligned tuples (total, blocked, assist, stun):
    `flags` from battle_adapter.read_damage_log_summary_flags(), `values` from
    read_efficiency_totals(). Each flag is bool()-coerced (getSetting's 0/1/None) and each
    value guarded against None. The fail-soft reads default flags to ticked / values to 0, so a
    bad read never wrongly triggers the shift on a disabled/zero total.

    Length is reconciled explicitly rather than `zip`-truncated: a short `values` tuple (from a
    fail-soft adapter read) would otherwise silently drop a column, so a 5-digit total in the
    dropped column would be missed and the overlay could collide with WG's widened panel. Missing
    flags default to ticked (the same fail-soft default as an unreadable flag); missing values to 0."""
    flags = tuple(flags or ())
    values = tuple(values or ())
    for i in range(max(len(flags), len(values))):
        enabled = bool(flags[i]) if i < len(flags) else True
        value = values[i] if i < len(values) else 0
        if enabled and (value or 0) > threshold:
            return True
    return False


def anchor_top_left(max_x, max_y, x_from_left, y_from_bottom):
    """Top-left (x, y) in logical GUI space for the overlay window.

    `max_x, max_y` is the movable extent (= logical space - surface size) recovered by the
    caller's far-sentinel clamp. `x_from_left` / `y_from_bottom` are fixed logical offsets
    from the left/bottom screen edges. The result is clamped on-screen: x into [0, max_x],
    y into [0, max_y] (y = max_y - y_from_bottom, so y_from_bottom=0 is bottom-flush)."""
    x = min(max(0, x_from_left), max_x)
    y = min(max(0, max_y - y_from_bottom), max_y)
    return x, y


def anchor_centred(max_x, max_y, y_frac, x_offset=0, y_offset=0):
    """Top-left (x, y) in logical GUI space for a HORIZONTALLY CENTRED window.

    Used by the centre-screen progress bar, where -- unlike the corner overlay above -- the
    vertical placement is genuinely PROPORTIONAL (it must clear WG's fly-up ribbon feed,
    whose baseline sits at ~75.1vh) rather than a fixed logical offset tracking a Flash panel.

    `max_x, max_y` is the movable extent (= logical space - surface size) recovered by the
    caller's far-sentinel clamp. That is the whole trick on X: max_x == space_w - surface_w,
    so `max_x // 2` centres the surface EXACTLY without this function knowing either width.
    `y_frac` places the top edge that fraction down the vertical extent (0.0 = top,
    1.0 = bottom); `x_offset` / `y_offset` are signed logical-px nudges off centre / off the
    proportional Y. Both axes are clamped on-screen. Fail-soft: an unusable (non-numeric /
    NaN) y_frac or either offset degrades to 0 -- top edge / dead centre -- so a bad value can
    never raise into the placement path.

    `y_offset` exists to CANCEL an intra-surface offset: the bar's front end rigidly
    translates its whole composition into positive document coordinates so nothing is clipped
    at the document origin (MoEProgress.js SHIFT_X_REM / SHIFT_Y_REM), which pushes the bar
    that far DOWN inside its own surface. Moving the window UP by the same amount (a NEGATIVE
    y_offset, constants.PROGRESS_ANCHOR_Y_OFFSET) leaves the bar exactly where it was on
    screen. X needs no such term: `max_x // 2` centres whatever surface width the view asks
    for, and the composition is symmetric about its own centre, so the centring self-adapts."""
    max_x = _int(max_x)
    max_y = _int(max_y)
    frac = _float(y_frac)
    x = min(max(0, max_x // 2 + _int(x_offset)), max_x)
    y = min(max(0, int(max_y * frac) + _int(y_offset)), max_y)
    return x, y


def anchor_pinned(max_x, max_y, pos_x, pos_y, y_frac, x_offset=0, y_offset=0):
    """Top-left (x, y) for a centre-screen bar the user may have Ctrl+DRAGGED somewhere.

    `pos_x` / `pos_y` are the stored drag position (mod_settings.bar_pos_x / bar_pos_y) in the
    SAME LOGICAL GUI SPACE the window is moved in -- deliberately NOT pinned to a viewport like
    the garage widget's posW/posH pair, because that space is already interface-scale invariant
    (see the module header), so there is nothing to rescale.

    0/0 MEANS AUTO, and ONLY the exact pair: an untouched install falls straight through to
    anchor_centred, so the shipped *_ANCHOR_* placement stays byte-identical for every user who
    never drags. Anything else -- including a lone axis, a negative coordinate and a coordinate
    past the movable extent -- is an explicit pin, honoured VERBATIM.

    NOT CLAMPED ON SCREEN, deliberately: the user is allowed to park a bar half (or wholly) off
    any edge, so there is no "safezone" here and none in the writer either (cursor_top_left
    below). A corrupt / non-numeric store still degrades to 0 via _int, i.e. to auto.

    `max_x` / `max_y` are unused by the pinned branch and kept only for anchor_centred's
    fallback -- the far-sentinel extent measurement is still what centres an unpinned bar."""
    x = _int(pos_x)
    y = _int(pos_y)
    if x == 0 and y == 0:
        return anchor_centred(max_x, max_y, y_frac, x_offset, y_offset)
    return x, y


def cursor_logical(cursor, screen, space_x, space_y):
    """The mouse cursor's position IN THE WINDOW'S LOGICAL GUI SPACE, or None if unreadable.

    `cursor` is the raw engine read (GUI.mcursor().position or a mouse event's .cursorPosition -- a
    Vector2, but a plain pair reads identically) and `screen` the raw GUI.screenResolution() pair.
    `space_x, space_y` is the FULL logical space the window is moved in, which the caller recovers as
    extent + surface size (see bridge/bar_window._space) -- NOT the movable extent, see the gain note
    on cursor_top_left.

    THE UNITS ARE DECIDED AT RUNTIME, not assumed: the decompiled call sites DISAGREE (armor/utils
    .getCollisionsAtCursor feeds the same read to a clip-space ray cast, i.e. [-1, 1]; radial_menu
    pairs a cursor pair with GUI.screenResolution(), i.e. device px). So a read whose components are
    both within [-1, 1] is taken as clip space -- x left..right, y BOTTOM..TOP, because BigWorld's
    clip y is UP -- and anything larger is normalised against `screen`, whose y runs DOWN from the
    top. The only ambiguity is the 2px corner at the screen origin, which reads as near-centre.

    UNCLAMPED AND FLOAT, on purpose: this is what the drag's grab offset is measured from, and a
    cursor beyond the movable extent (which is SMALLER than the space by the surface size, so the
    bottom-right corner of the screen always is) would otherwise bake the clamp's own error into the
    offset for the rest of the gesture. Returns None -- "leave the window exactly where it is" -- for
    any unusable cursor, or for a pixel-space cursor with no usable resolution to normalise it
    against."""
    point = _xy(cursor)
    if point is None:
        return None
    cx, cy = point
    if -1.0 <= cx <= 1.0 and -1.0 <= cy <= 1.0:
        fx = (cx + 1.0) / 2.0
        fy = (1.0 - cy) / 2.0            # clip y is UP; a window top-left is measured from the TOP
    else:
        res = _xy(screen)
        if res is None or res[0] <= 0 or res[1] <= 0:
            return None
        fx = cx / res[0]
        fy = cy / res[1]
    return fx * _int(space_x), fy * _int(space_y)


def cursor_top_left(cursor, screen, space_x, space_y, grab_x=0, grab_y=0):
    """Top-left (x, y) for a bar being Ctrl+DRAGGED, mapped ABSOLUTELY from the mouse cursor.

    THE WHOLE POINT IS THAT NOTHING HERE IS A DELTA. The superseded protocol had the bar's own JS
    report a mouse delta for Python to add: that needed a device-px -> logical-px gain factor
    (guessed wrong twice), and it could only see mouse events while the cursor stayed inside the
    bar-sized surface rect -- so any gain error or round-trip lag let the cursor escape the rect,
    events stopped and resumed, and the bar lurched. An absolute mapping has no factor to get wrong
    and no dependence on any hit rect.

    THE GAIN IS EXACTLY 1, AND THAT IS WHY `space_*` IS THE ARGUMENT. The window's position IS the
    cursor's position in logical space, less the offset it was grabbed by:

        window_pos = cursor_logical(...) + grab            (grab = window_pos - cursor, at start)

    so N logical units of cursor travel move the window N logical units. Mapping the cursor's SCREEN
    FRACTION onto the MOVABLE EXTENT instead (space - surface, which is all a far-sentinel clamp can
    recover) silently bakes in a gain of (space - surface) / space: measured ~0.74 on x, i.e. "the
    bar moves slower than the cursor", which is the exact live symptom this whole absolute mapping
    replaces. Hence `space_*`, never the extent.

    `grab_x` / `grab_y` is the offset recorded between the window's top-left and cursor_logical at
    gesture START, carried for the whole gesture so the bar keeps the point it was grabbed by
    instead of teleporting its corner under the cursor on the first event.

    NOT CLAMPED AT ALL -- there is no on-screen safezone. The user may drag a bar past any edge,
    including off the left/top into negative coordinates, and anchor_pinned honours whatever lands
    here verbatim. The ONE forbidden result is the exact pair (0, 0), which is anchor_pinned's AUTO
    sentinel: a drag that happens to land there is nudged one px on x so it can never be misread as
    "never dragged". Returns None whenever cursor_logical does."""
    point = cursor_logical(cursor, screen, space_x, space_y)
    if point is None:
        return None
    x = int(point[0] + _float(grab_x))
    y = int(point[1] + _float(grab_y))
    if x == 0 and y == 0:
        x = 1
    return x, y


def cursor_in_rect(point, top_left, size):
    """True when `point` lies inside the rect at `top_left` of `size` (all three in the SAME
    logical GUI space -- see cursor_logical).

    THE DRAG'S OWNERSHIP GATE. Ctrl+left-button is sampled globally off WG's input dispatchers, so
    without this every open bar claimed every gesture anywhere on screen -- dragging another mod's
    UI dragged ours too. A host claims a gesture only when it STARTED inside that host's own window
    rect; once claimed it keeps the gesture wherever the cursor goes (so re-testing on a move would
    drop the bar mid-drag -- see bar_window.BarHost.drag).

    Bounds are INCLUSIVE on both edges: the rect is the window's surface, and its far edge is a
    legitimate place to grab. Fail-soft to FALSE -- an unreadable point / position / size means "do
    not claim", which loses the gesture rather than stealing one."""
    p = _xy(point)
    tl = _xy(top_left)
    wh = _xy(size)
    if p is None or tl is None or wh is None:
        return False
    return (tl[0] <= p[0] <= tl[0] + wh[0]) and (tl[1] <= p[1] <= tl[1] + wh[1])


def _xy(value):
    """(x, y) as floats from a Vector2-like OR a plain pair, or None for anything unusable.

    Both shapes are real: the decompiled client reads `.x`/`.y` off GUI.mcursor().position in one
    place and tuple-unpacks it in another, and GUI.screenResolution() is a plain pair. A NaN
    component is unusable (it would poison every comparison downstream)."""
    try:
        x = float(value.x)
        y = float(value.y)
    except (AttributeError, TypeError, ValueError):
        try:
            x, y = value
            x = float(x)
            y = float(y)
        except (AttributeError, TypeError, ValueError):
            return None
    return None if (x != x or y != y) else (x, y)


def _int(value):
    """int(value), or 0 for anything unusable (None / non-numeric / NaN)."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0
    return 0 if value != value else int(value)


def _float(value):
    """float(value), or 0.0 for anything unusable (None / non-numeric / NaN)."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if value != value else value
