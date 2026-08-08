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
    y_offset, constants.PROGRESS_ANCHOR_Y_SHIFT) leaves the bar exactly where it was on
    screen. X needs no such term: `max_x // 2` centres whatever surface width the view asks
    for, and the composition is symmetric about its own centre, so the centring self-adapts.

    SUPERSEDED AND NO LONGER CALLED BY THE MOD -- anchor_centred_reduced below is what
    bridge/bar_window.py._resolve places with. This is kept as the pre-reduction REFERENCE the
    test suite compares that form against (the +/-1 int-floor bound), and for no other reason: the
    `y_offset` it takes was a TWO-TERM composite (the retired constants.PROGRESS_ANCHOR_Y_OFFSET
    (_LARGE) / EFFICIENCY_ANCHOR_Y_OFFSET(_LARGE)) baking both the intra-surface cancellation above
    AND an extent-to-viewport fraction conversion, while the shipped constants are now the PURE
    shift term alone. Do NOT add a third variant, and do not place with this one."""
    max_x = _int(max_x)
    max_y = _int(max_y)
    frac = _float(y_frac)
    x = min(max(0, max_x // 2 + _int(x_offset)), max_x)
    y = min(max(0, int(max_y * frac) + _int(y_offset)), max_y)
    return x, y


def anchor_centred_reduced(max_x, max_y, space_y, y_frac, y_shift, x_shift=0):
    """Top-left (x, y) in logical GUI space for a HORIZONTALLY CENTRED window -- the COMPUTED
    successor to anchor_centred above, and what bridge/bar_window.py._resolve now places the
    Damage-Log-aligned bar with (see TASKS/in-battle-vertical-bar-PLAN.md "Phase 2 approach: the
    anchor-Y term is COMPUTED, not baked"). Same job, reduced math: takes the FULL logical space
    `space_y` in place of the
    movable extent `max_y` for the Y fraction, and a single PURE shift term (`y_shift`) in place
    of a baked two-term composite.

    `x_shift` (DEFAULT 0, i.e. pure `max_x // 2` centring, byte-identical to every call site that
    predates it) is rule 5's vertical + Damage Log right-pin (TASKS/in-battle-bar-layout-auto-set-
    redesign.md Trap 3 Fix A / DECISION 3): a horizontal bar's composition is symmetric about its
    own centre, so `max_x // 2` alone already keeps the bottom-CENTRE's x fixed across a size
    change and must stay a no-op there. A VERTICAL bar's natural anchor is bottom-RIGHT instead,
    and centring is not a right-pin -- a size-up widens the surface and `max_x // 2` moves BOTH
    edges outward by half the width delta, so the caller passes a per-size, per-bar NEGATIVE
    `x_shift` (constants.PROGRESS_/EFFICIENCY_ANCHOR_X_SHIFT_LARGE, 0 at Default) that cancels
    exactly that outward drift and holds the right edge -- see those constants' derivation. This
    moves the WINDOW's top-left only; the composition inside the surface is untouched, so the
    vertical bar's surface stays concentric with its own track (memory `vertical-bar-surface-
    must-stay-concentric-with-track` is about anchor_minimap, not this anchor, but the same
    window-vs-composition distinction applies here).

    WHY THE REDUCTION IS VALID. anchor_centred's `y_offset` sums two terms: -shift (cancelling
    the composition's intra-surface offset) and +round(y_frac * surface_h) (converting the
    fraction from "of the movable extent" to "of the viewport", needed only because
    anchor_centred multiplies the fraction by max_y == space_y - surface_h). Substituting:

        y = int(max_y * frac) + (-shift + round(frac * surface_h))
          = int((space_y - surface_h) * frac) + round(frac * surface_h) - shift
         ~= int(space_y * frac) - shift

    i.e. once the fraction is applied to `space_y` directly, the extent-to-viewport conversion
    term is exactly cancelled and never needs computing (or baking per orientation/alignment) at
    all -- `y_shift` is the WHOLE remaining constant, always negative-or-zero, one value per
    (bar, size), shared by every alignment that uses this anchor at all.

    THREE ARGUMENTS, not two, because of what each is for: `max_x` centres X the same way
    anchor_centred does (`max_x // 2` -- still the movable EXTENT, not `space_x`: it centres the
    surface exactly without this function knowing the surface width, and that trick only works on
    the extent, never on the full space). `max_y` still bounds the Y CLAMP (a fraction near 1.0
    plus a small negative shift must not push the bar below the movable extent, and a huge
    positive shift must not push it above the extent's top) -- the clamp target does not change
    just because the multiplication no longer uses it. `space_y` is what the fraction itself is
    now applied to.

    ACCEPTED, MEASURED RISK: int(space_y * frac) is int-of-sum where the old form is
    sum-of-rounded-parts, so this can differ from anchor_centred's result by +/-1 logical px
    depending on the exact space_y -- confirmed by direct computation across a wide span of
    resolutions (not assumed to be 0; see the implementer's report). Do not chase a "fix" for
    this -- there is no baked constant left to nudge, and the two forms are only equivalent up to
    that 1px int-floor discretization by construction, at every resolution.

    Fail-soft, matching anchor_centred: an unusable (non-numeric / NaN) max_x/max_y/space_y,
    y_frac or y_shift degrades to 0 via _int/_float."""
    max_x = _int(max_x)
    max_y = _int(max_y)
    space_y = _int(space_y)
    frac = _float(y_frac)
    shift = _int(y_shift)
    xshift = _int(x_shift)
    x = min(max(0, max_x // 2 + xshift), max_x)
    y = min(max(0, int(space_y * frac) + shift), max_y)
    return x, y


def anchor_minimap(space_x, space_y, edge_x, edge_y, mm_size, gap, gap_bottom, overhang):
    """Top-left (x, y) in logical GUI space for a bar anchored to the LEFT of the minimap.

    The minimap sits flush to the screen's bottom-right corner with ZERO inset at every
    resolution and interface scale (memory `minimap-onscreen-geometry-measured-table`), so both
    axes are plain subtraction from the FULL logical space `space_x, space_y` -- unlike
    anchor_centred_reduced / anchor_top_left there is no movable-extent term here at all, because
    this anchor does not track a Ctrl+drag extent, it tracks the minimap's own edge:

        x = space_x - mm_size - gap - overhang - edge_x
        y = space_y - gap_bottom - edge_y

    `mm_size` is the measured minimap size for the current settingsCore GAME.MINIMAP_SIZE index
    (constants.MINIMAP_SIZES, already clamped [0, 5] by the caller -- WG's own getter does not
    clamp). `gap` / `gap_bottom` are the fixed logical-px clearances (constants.MM_GAP, shared by both
    bars, and constants.*_MM_GAP_BOTTOM, one PER BAR -- each vertical tuner tuned its own: 30 and 28).
    `overhang` is half the bar's tick cross-axis overhang past its own track edge
    (constants.MM_TICK_OVERHANG(_LARGE)) -- the track's right edge sits `gap + overhang` clear of
    the minimap, but the TICK's outer edge (which is what visually reads as "the bar") sits only
    `gap` clear, mirroring the vertical tuner's `halfOverhang()`.

    `edge_x` / `edge_y` ARE WHAT MAKE THE TWO GAPS MEAN WHAT THE TUNER MEANT, and passing the wrong
    thing for them WAS the shipped bug. They are the ALIGNED EDGE's own offset from the surface's
    top-LEFT corner: `edge_x` from the surface's left edge out to the edge that has to clear the
    minimap, `edge_y` from the surface's top edge down to the edge that has to clear the screen
    bottom. The shipped call passed the bar's own SURFACE WIDTH/HEIGHT, which aligns the SURFACE's
    far edges -- and that is not the frame `gap` / `gap_bottom` were tuned in:
    tools/dev/gen_bar_tuner_vertical.ps1's barRightPx() / barBottomPx() (and the efficiency
    tuner's placement()) place the visible TRACK box on the stage, while the vertical compositions
    leave a wide margin of caption space, backdrop bleed and shadow pad between the track and the
    surface (constants.*_MM_TRACK_X / MM_TRACK_Y: 45-63 logical px of it on x, 90 on y -- which is
    exactly how far the bar landed off). This is the same surface-vs-composition frame mismatch the
    *_ANCHOR_Y_SHIFT constants cancel for the centred anchor, and it is the CALLER that supplies the
    per-bar, per-size term -- see bar_window._resolve, which still passes the surface's own edges
    for a HORIZONTAL bar because no tuner ever placed that composition beside the minimap.

    THE Y RESULT IS NOT ALWAYS REACHABLE, and this function deliberately does not pretend otherwise
    by clamping. The engine clamps EVERY window into [0, space - surface] in compiled C++
    (movePyWindow -- memory `engine-clamps-every-wulf-window-to-screen-and-the-mod-depends-on-it`;
    bar_window._extent's far-sentinel calibration DEPENDS on that clamp existing), so a
    `gap_bottom` SMALLER than the surface's own below-the-track slack (surface_h - edge_y) cannot be
    honoured at all: the surface would have to hang past the screen's bottom edge, and it may not.
    The engine flushes the surface to the bottom instead, which is still the closest reachable
    placement to the tuner's. X has no such ceiling -- the surface overhangs the MINIMAP, not the
    screen.
    WHICH IS WHY THE SLACK IS A FRONT-END NUMBER, and it has since been shrunk to exactly each
    vertical bar's tuned gap: the surface used to be sized to contain the whole backdrop (380 rem
    tall against edge_y 290, i.e. 90 of slack, so both tuned gaps -- 30 and 28 -- were unreachable
    and both bars flushed to the same spot ~60px high). It is now sized to contain the bottom
    caption's INK and to CLIP the backdrop's lower bleed, exactly as each tuner's stage clips it
    (MoEProgress.js / MoEEfficiency.js V_CLIP_B_REM), so at the Default size both gaps are reachable
    and land on their tuned value. Under the LARGE size mode the clip scales with the composition
    while `gap_bottom` stays fixed logical px, so this ceiling engages again -- deliberately, since
    flushing then delivers the tuned gap * SIZE_F, which is the same look scaled (constants
    .*_MM_GAP_BOTTOM). Do NOT clamp here to paper over either case.

    UNCLAMPED, deliberately, matching the module's no-safezone rule (cursor_top_left below): a
    small enough space or wide enough bar can legitimately push x/y negative,
    and there is nothing to clamp against here anyway -- unlike anchor_centred_reduced there is no
    movable-extent argument on hand to clamp into.

    Fail-soft: every argument degrades via _int, so an unreadable minimap-size read or a bad
    surface measurement lands the bar at a wrong-but-numeric spot rather than raising."""
    space_x = _int(space_x)
    space_y = _int(space_y)
    edge_x = _int(edge_x)
    edge_y = _int(edge_y)
    mm_size = _int(mm_size)
    gap = _int(gap)
    gap_bottom = _int(gap_bottom)
    overhang = _int(overhang)
    x = space_x - mm_size - gap - overhang - edge_x
    y = space_y - gap_bottom - edge_y
    return x, y


def anchor_offset(anchor, off_x=0, off_y=0):
    """Top-left (x, y) for `anchor` nudged by a stored stepper offset -- POSITIVE = right/down,
    UNIFORMLY regardless of which alignment produced `anchor`:

        x, y = anchor(alignment, orientation) + (off_x, off_y)

    This is what RETIRED the old anchor_pinned's 0/0-means-auto sentinel (deleted with the wiring
    step): under Damage Log alignment, offset (0, 0) already IS the shipped placement (the base
    anchor returned verbatim, no sentinel to fall through), so every alignment composes the same
    way, always -- THIS function has no "auto" case and no branch of any kind. The caller does:
    bar_window._resolve picks the BASE anchor, and a (0, 0) pair under FREE alignment makes it pick
    the orientation's default anchor instead of the origin -- NOT because Free is sticky (that
    rule is SUPERSEDED, see mod_settings._derive_layout) but because (0, 0) is Free's own "not yet
    materialised" marker (see bar_window.BarHost._materialise) and the accepted, deliberately lost
    capability of pinning a bar at literal logical (0, 0) via the steppers. A NON-zero Free pair
    skips this function entirely -- see free_top_left below, which converts the stored ANCHOR
    POINT into a top-left using the live surface size instead of composing an offset onto a base.
    That choice is the caller's alone -- do not reintroduce a sentinel here.

    UNCLAMPED, matching the module's no-safezone rule (cursor_top_left below): the base
    anchor may already be clamped (anchor_centred_reduced) or not (anchor_minimap), and a
    user-configurable nudge on top of either is allowed to push the bar past any edge -- that is
    the whole point of an offset control.

    Fail-soft: an unusable `anchor` (wrong shape / non-numeric / NaN) degrades to (0, 0) before
    the offset is added (via the same `_xy` the cursor helpers below use); an unusable `off_x` /
    `off_y` degrades to 0 via `_int`."""
    point = _xy(anchor)
    ax, ay = (0, 0) if point is None else point
    return _int(ax) + _int(off_x), _int(ay) + _int(off_y)


def free_top_left(pair, surface, vertical):
    """Top-left (x, y) for a bar under Alignment = Free, given the stored pair as an ANCHOR
    POINT (TASKS/in-battle-bar-layout-auto-set-redesign.md Trap 3 Fix B / DECISION 2) rather than
    a top-left:

        horizontal: top_left = (pair_x - surface_w // 2, pair_y - surface_h)   # bottom-centre
        vertical:   top_left = (pair_x - surface_w,      pair_y - surface_h)   # bottom-right

    WHY AN ANCHOR POINT, NOT A TOP-LEFT. Rule 5 (a size change must not move the bar's anchor)
    needs the anchor re-derived from the CURRENT surface size at every placement -- a
    Default<->Large flip changes `surface`, and re-deriving from a fixed anchor point keeps that
    point fixed while the surface grows/shrinks around it, with zero stored-coordinate math.
    Converting the STORED pair itself at the moment of the size change is impossible: the size
    radio lives in the garage settings panel, where no bar surface exists to convert against (the
    same wall bar_window.BarHost._materialise hits when Free is first picked) -- so the
    conversion has to live HERE, at placement, applied fresh every call.

    UNCLAMPED, matching every other placement function in this module (no on-screen safezone): the
    engine's own clamp (compiled C++, no opt-out) still applies downstream, and clamping here too
    would bake a crossed-edge clamp into a value nothing ever re-reads -- see the caller
    (bar_window._resolve) for why this conversion is PLACEMENT-ONLY and never written back to the
    store.

    Fail-soft: an unusable `pair` or `surface` degrades to (0, 0) via the same `_xy` the cursor
    helpers below use."""
    point = _xy(pair)
    px, py = (0, 0) if point is None else point
    surf = _xy(surface)
    sw, sh = (0, 0) if surf is None else surf
    sw = _int(sw)
    sh = _int(sh)
    if vertical:
        return _int(px) - sw, _int(py) - sh
    return _int(px) - sw // 2, _int(py) - sh


def free_anchor_point(top_left, surface, vertical):
    """The exact inverse of free_top_left: the ANCHOR POINT a bar currently sitting at
    `top_left` (given `surface`) would be stored as under the Fix B frame.

    Used ONLY to MATERIALISE Free's stored pair -- bar_window.BarHost._materialise, the first
    time a real battle surface exists after (1) picking Free with no coordinates computed yet
    (DECISION 1) or (2) upgrading past a pre-v22 store whose pair was still a literal top-left
    (DECISION 2's deferred conversion, option (a)). Every ordinary placement goes through
    free_top_left instead; this direction is the one-shot write path.

    Exact, not approximate: addition undoes free_top_left's subtraction of the SAME
    surface-derived term, so free_anchor_point(free_top_left(pair, surface, vertical), surface,
    vertical) == pair for any integer pair and surface -- no rounding is introduced beyond
    whatever the caller's own inputs already carry.

    Fail-soft: an unusable `top_left` or `surface` degrades to (0, 0) via the same `_xy` the
    cursor helpers below use."""
    point = _xy(top_left)
    tx, ty = (0, 0) if point is None else point
    surf = _xy(surface)
    sw, sh = (0, 0) if surf is None else surf
    sw = _int(sw)
    sh = _int(sh)
    if vertical:
        return _int(tx) + sw, _int(ty) + sh
    return _int(tx) + sw // 2, _int(ty) + sh


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

    NOT CLAMPED AT ALL, AND NO RESULT IS FORBIDDEN -- there is no on-screen safezone. The user may
    drag a bar past any edge, including off the left/top into negative coordinates, and the stored
    pair is honoured verbatim (a drag end sets Alignment := Free, so the pair IS the top-left).
    The exact pair (0, 0) used to be nudged one px on x because it was the deleted anchor_pinned's
    AUTO sentinel, and it is once again a value the placement path reads as AUTO (bar_window
    ._resolve: a (0, 0) pair under Free defers to the orientation's default anchor, which is what
    lets an Orientation change reset the coordinates without un-sticking Free). The nudge has NOT
    come back with it: dragging a bar's top-left onto exactly logical (0, 0) and having it snap to
    the default anchor is the accepted, explicitly-agreed cost of that reset, and re-adding a
    silent 1px lie here would just move the surprise somewhere harder to find. Returns None
    whenever cursor_logical does."""
    point = cursor_logical(cursor, screen, space_x, space_y)
    if point is None:
        return None
    return int(point[0] + _float(grab_x)), int(point[1] + _float(grab_y))


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
