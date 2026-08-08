# -*- coding: utf-8 -*-
"""Host a centre-screen transient bar as its OWN OpenWG-registered Gameface WINDOW over the
battle HUD. ONE implementation, instantiated once per bar (bridge/progress_view.py,
bridge/efficiency_view.py).

The two bars -- Moving Average and Damage Efficiency -- are radio ALTERNATIVES: battle_bridge opens
exactly one of them, which is the only reason both stylesheets can own #moe-bar-root and the .mp-*
prefix. They differ in FOUR things and nothing else: the res_map itemID, the ViewModel, the anchor
constants and the log tag. So each is a BarHost(...) rather than a hand-clone; what is emphatically
NOT shared is the per-bar state, because two hosts must be able to be open at once (a live radio
switch mid-battle opens one before the other closes):

  * ONE ``_active`` PER HOST, not per module. A module-level singleton is exactly what forced the
    clone this replaces -- apply_position / _place / active_view all hard-referenced it, so one
    module could not host two windows. Here it is instance state.
  * ONE ``ModDynAccessor`` PER HOST. Reusing another view's resId resolves the WRONG layout and
    opens a second copy of THAT view. It is passed to ViewSettings per instance, which is safe
    because gen_utils.DynAccessor is a plain ``__slots__`` callable -- ``__call__`` and no
    ``__get__`` -- so it was never a descriptor and its old class-level home was incidental.
  * ONE res_map JSON PER LAYOUT. Do NOT merge them: OpenWG assigns the numeric resId POSITIONALLY
    when it rebuilds res_map.json, so two entries sharing an itemID collide and one layout becomes
    unreachable. Adding an entry costs a one-time client restart.

Everything WHY-shaped about the hosting model lives in battle_view.py's docstrings (why a
registered window and not a garage-style inject; why WindowLayer.WINDOW and not OVERLAY; why NOT
WINDOW_FULLSCREEN -- a full-screen Coherent surface steals the whole-screen mouse hit-test whenever
the cursor is raised, and pointer-events:none does NOT make the window rectangle click-through).
Read that first. The difference here is placement: a bar is placed off whichever ANCHOR the
Alignment setting selects -- centred horizontally and proportionally down the screen (Damage Log,
the shipped default), to the left of the minimap (Minimap), or at the screen origin (Free, i.e. the
stored pair read as an absolute top-left) -- with the stored X/Y stepper pair composed on top of it
in every case (domain.anchor_offset). A Ctrl+DRAG writes that same pair and flips Alignment to
Free, which is why the drag has no special placement path of its own: offset (0, 0) under Damage
Log IS the shipped placement byte-for-byte, so there is no "auto" sentinel any more (see the
deleted domain.anchor_pinned).

THE DRAG IS ENTIRELY PYTHON'S NOW, AND ABSOLUTE. adapter/battle_input samples Ctrl + the left mouse
button off WG's own input dispatchers plus its g_mouseEventHandlers registry, and reports the gesture
here as drag("start"/"move"/"end", cursor); each movement re-places the window from the LIVE CURSOR
POSITION (domain.cursor_top_left), ONE handler and ONE stored pair for both bars. It replaces a JS
delta protocol that failed structurally three times over: the reported delta was device px while
window.move takes logical px (a gain factor we kept getting wrong), and -- because each bar is its OWN
window whose surface rect IS the mouse hit rect -- any gain error or round-trip lag let the cursor
leave that bar-sized rect, at which point the events stopped, resumed, and the bar lurched. An
absolute mapping has no factor and needs no mouse input in the document at all, so the hit rect now
stays permanently collapsed (see MoEBarTransient.js) and the HUD-input-stealing hazard is retired
with it. Its GAIN IS EXACTLY 1, which takes one more term than a far-sentinel clamp can see -- the
window's own size; see _space, and do NOT scale a cursor fraction onto _extent's result.

THE SURFACE IS SIZED FROM THE JS, NOT FROM HERE. There is no Python-side size setter anywhere
(native PyObjectWindow has no resize / no autoSize; ``windowSize`` writes land silently in
``__dict__`` and do nothing), and no res_map field for size -- Layout.parameters accepts only
extension / entrance / impl. What actually sizes a Gameface view is the view PUSHING its own size
to C++ via the ``viewEnv`` global: ``viewEnv.resizeViewRem(w, h)`` (rem == logical px). A view that
never calls it gets the engine's "default view size" fallback after a ``Size calculation timeout``
-- a flat 256x256 logical px, which is what clipped these bars.
PUSHING THE SIZE IS NOT SUFFICIENT ON ITS OWN, because the timeout's fallback runs LAST and WINS:
live-measured, the resize landed at 04.8s and the deadline's "Set the default view size" action at
06.2s put the surface back to 256x256. Static in-flow content does NOT satisfy the engine's
measurement either -- that premise was tested and disproven -- so the JS re-asserts the size once
after the deadline (SURFACE_REASSERT_MS in MoEBarTransient.js). Each resize round-trips back here as
Window._cResized -> onSizeChanged, which is exactly why _onReady SUBSCRIBES to it rather than
placing once: the placement has to be re-read against the REAL extent.

PC-only (needs the live client); not imported under pytest without stubs. Python 2.7 runtime.
"""
from moe_calculator._compat import LOG_CURRENT_EXCEPTION, LOG_DEBUG

from frameworks.wulf import ViewSettings, ViewFlags, WindowFlags, WindowLayer, PositionAnchor
from gui.impl.pub import ViewImpl, WindowImpl
from openwg_gameface import ModDynAccessor

from moe_calculator.bridge import mod_settings
from moe_calculator.domain.constants import (MINIMAP_SIZES, MM_GAP,
                                             MM_TICK_OVERHANG, MM_TICK_OVERHANG_LARGE,
                                             MM_TRACK_Y, MM_TRACK_Y_LARGE,
                                             VERTICAL_ANCHOR_Y_SHIFT,
                                             VERTICAL_ANCHOR_Y_SHIFT_LARGE)
from moe_calculator.domain.positioning import (anchor_centred_reduced, anchor_minimap,
                                               anchor_offset, cursor_in_rect, cursor_logical,
                                               cursor_top_left)

# A large sentinel offset used to clamp the window to the far corner (LEFT/TOP anchor) so we can
# read back the movable extent (= logical space - windowSize) and place proportionally.
_FAR = 1 << 20


def _cursor_position():
    """The mouse cursor's live position as the engine reports it, or None.

    THE FALLBACK, not the primary read: a mouse move reported through gui.g_mouseEventHandlers
    carries its own ``event.cursorPosition``, which drag() prefers. This is what the key /
    AvatarInputHandler sampling points -- which have no event to read -- fall back to.

    ``GUI.mcursor().position`` is battle-usable (precedent: gui/Scaleform/daapi/view/battle/shared/
    radial_menu.py's _showInternal) and is a Vector2. ITS UNITS ARE NOT SETTLED in the decompiled
    client -- one call site feeds it to a clip-space ray cast, another pairs a cursor pair with
    GUI.screenResolution() -- which is why the mapping that consumes it (domain.cursor_top_left)
    decides the convention at runtime instead of assuming one.

    Lazily imported and fail-soft to None ("leave the bar where it is"), so this module still
    imports under pytest with the game closed."""
    try:
        import GUI
        return GUI.mcursor().position
    except Exception:
        return None


def _minimap_size_index():
    """The player's minimap size as an index into constants.MINIMAP_SIZES, already clamped.

    Lazily imported and fail-soft for the same reason _cursor_position is: adapter/battle_adapter
    imports BigWorld at module scope, and this module has to stay importable with the game closed.
    The engine read, its clamp and its own fail-soft default all live in the adapter (that is the
    layer allowed to touch settingsCore) -- this wrapper only keeps the import off the module top,
    and falls back to the SAME largest-index default when even the import fails (see the adapter
    for why the largest, not the middle)."""
    try:
        from moe_calculator.adapter import battle_adapter
        return battle_adapter.read_minimap_size_index()
    except Exception:
        return len(MINIMAP_SIZES) - 1


def _screen_resolution():
    """(width, height) in device px, or None. Only needed for the PIXEL-space cursor convention --
    a clip-space read normalises itself."""
    try:
        import GUI
        return GUI.screenResolution()
    except Exception:
        return None


class _BarView(ViewImpl):
    """The registered Gameface view; its root ViewModel IS the bar's own model (the JS reads it
    with a bare ModelObserver(), no nested submodel and no unwrap).

    layoutID and the model arrive per INSTANCE, so one class serves every bar -- see the module
    docstring on why a per-instance ModDynAccessor is safe."""

    def __init__(self, layout_id, view_model):
        super(_BarView, self).__init__(ViewSettings(layout_id, ViewFlags.VIEW, view_model))

    @property
    def viewModel(self):
        return super(_BarView, self).getViewModel()

    def _onLoading(self, *args, **kwargs):
        super(_BarView, self)._onLoading(*args, **kwargs)
        # Push once the view (and its bound VM) is live so the bar has real values in hand for its
        # first transient. Lazy import avoids a bar_window <-> battle_bridge cycle.
        try:
            from moe_calculator.bridge import battle_bridge
            battle_bridge.refresh()
        except Exception:
            LOG_CURRENT_EXCEPTION()


class _BarWindow(WindowImpl):
    """Content-sized, input-transparent window hosting a _BarView over the HUD. Same flags and
    layer as MoEBattleWindow, for the same reasons (read its docstring): WindowFlags.WINDOW (NOT
    full-screen -- the Ctrl+click hit-test steal), layer WINDOW (7) so the modal in-battle menu at
    TOP_WINDOW (10) keeps its input, shown without focus."""

    def __init__(self, content, place):
        super(_BarWindow, self).__init__(
            WindowFlags.WINDOW, content=content, layer=WindowLayer.WINDOW)
        self._place = place

    def _onReady(self):
        self.show(focus=False)
        # RE-ARM EVERY MOUNT (dropped again in close_window -> detach): _place reads the movable
        # extent by far-sentinel clamp, and at _onReady the surface is still the engine's 256x256
        # default-size fallback -- the JS pushes the real size a moment later. Wulf fires
        # onSizeChanged per resize, so re-place off that rather than trusting this one shot. Plain
        # `+=` is the WG idiom for a Wulf window Event (see Window.__attachToDecorator).
        self.onSizeChanged += self._on_size_changed
        self._place(self)

    def _on_size_changed(self, _unique_id, _width, _height):
        """The JS resized our surface -> the movable extent changed -> re-place."""
        self._place(self)

    def detach(self):
        """Drop the onSizeChanged subscription. Called from close_window BEFORE destroy so the
        listener never outlives a battle. Fail-soft -- teardown must not raise."""
        try:
            self.onSizeChanged -= self._on_size_changed
        except Exception:
            LOG_CURRENT_EXCEPTION()


class BarHost(object):
    """One centre-screen bar window: its layout, its ViewModel and its own open/closed singleton.

    ``item_id`` is the itemID registered in mods/configs/res_map/<item_id>.json -- keep in lockstep,
    and keep it DISTINCT from every other entry's (the positional resId collision above).
    ``vm_factory`` is called per open to build a fresh root ViewModel. ``y_frac`` / ``x_off`` /
    ``y_shift`` are the bar's HORIZONTAL-orientation anchor constants (domain/constants), and
    ``tag`` prefixes its log lines. ``y_shift_large`` is the same intra-surface compensation for the
    LARGE size mode -- a bigger surface shifts its composition further down inside itself (see the
    constants' derivations) -- and BOTH shifts are only ONE of the values _resolve picks LATE rather
    than freezing here: the size, orientation and alignment settings are all read per placement,
    because these arguments are bound at MODULE IMPORT and a setting changed after that (or between
    battles) would otherwise keep using whichever value was current at first load, forever.
    ``mm_track_x`` / ``mm_track_x_large`` are the MINIMAP alignment's own per-bar term -- where this
    bar's VERTICAL track sits inside its own surface on the cross axis (constants
    .*_MM_TRACK_X(_LARGE)) -- per bar for the same reason the two shifts are, and read just as late.
    Its Y counterpart is SHARED by both bars (MM_TRACK_Y) and so needs no argument.
    ``mm_gap_bottom`` is that alignment's OTHER per-bar term: the clearance this bar's VERTICAL track
    keeps off the screen's bottom edge (constants.*_MM_GAP_BOTTOM, 30 vs 28 -- each tuner's own tuned
    value). It was a single shared constant while both bars' surfaces buried the tuned gaps under 90
    logical px of unreachable slack; the front-end change that shortened both vertical surfaces to
    their own tuned gap is what made the two numbers differ ON SCREEN and so worth threading. It has
    no Large twin, on purpose -- see the constants' note.
    """

    def __init__(self, item_id, vm_factory, y_frac, x_off, y_shift, y_shift_large,
                 mm_track_x, mm_track_x_large, mm_gap_bottom, tag):
        self.item_id = item_id
        self._vm_factory = vm_factory
        self._y_frac = y_frac
        self._x_off = x_off
        self._y_shift = y_shift
        self._y_shift_large = y_shift_large
        self._mm_track_x = mm_track_x
        self._mm_track_x_large = mm_track_x_large
        self._mm_gap_bottom = mm_gap_bottom
        self._tag = tag
        self._layout_id = ModDynAccessor(item_id)   # deferred; -1 until OpenWG validates it
        self._active = None                         # (window, view) while open
        self._extent_cache = None                   # memoized movable extent; see _extent
        # THE LIVE GESTURE's only two pieces of state (both None while none is in flight):
        # `_grab` is the offset between the window's top-left and the cursor's mapped position at
        # gesture start, carried for the whole gesture so the bar keeps the point it was grabbed by;
        # `_drag_pos` is the last position actually applied, i.e. what the mouse-up persists -- and
        # None means the gesture NEVER MOVED, which must persist nothing (see drag).
        # `_declined` latches a gesture this host does NOT own (it began outside our window rect),
        # so a foreign drag that later sweeps the cursor across us cannot be claimed mid-flight.
        self._grab = None
        self._drag_pos = None
        self._declined = False

    def _resolve(self, max_x, max_y, space_x, space_y):
        """This bar's top-left in logical GUI space: the base anchor the ALIGNMENT setting selects,
        with the stored X/Y stepper pair composed on top (domain.anchor_offset -- positive =
        right/down, uniformly, whichever alignment produced the base).

        `max_x, max_y` is the movable extent (space - surface) and `space_x, space_y` the FULL
        logical space; the surface size is their per-axis difference, which is why placing a bar
        needs no engine call the caller has not already made (see _space, and the drag's ownership
        gate, which recovers the surface the same way).

        THREE BRANCHES, and offset (0, 0) needs no fourth: under Damage Log alignment the base IS
        the shipped placement byte-for-byte, and under Free it now falls through to the
        orientation's own default anchor (see the Free bullet), so no branch has to special-case it.
          * Damage Log -- centred horizontally, PROPORTIONALLY down the viewport
            (anchor_centred_reduced). Its `y_shift` cancels the composition's intra-surface top
            offset (the JS shifts the whole bar into positive document coordinates); the fraction's
            extent-to-viewport conversion is computed by passing `space_y`, not baked into the
            constant -- see the constants' derivations and anchor_centred_reduced's docstring.
          * Minimap -- to the LEFT of the minimap, whose measured logical width comes from the live
            settingsCore size INDEX (_minimap_size_index). The tick overhang term applies only to a
            VERTICAL bar: it is a CROSS-axis length, and only a vertical bar's cross axis is the x
            axis the minimap gap is measured on (a horizontal bar's ticks overhang in y instead).
            WHAT THE TWO GAPS ARE MEASURED TO IS ALSO ORIENTATION-SPLIT, and getting it wrong was
            the shipped bug (the bar landed 45-63px too far left and 90 too high). Both tuners
            measure them to the visible TRACK box, so a VERTICAL bar passes where its track sits
            inside its surface (*_MM_TRACK_X / MM_TRACK_Y) as anchor_minimap's `edge_x` / `edge_y`.
            A HORIZONTAL bar keeps passing the SURFACE's own edges (space - extent, the shipped
            behaviour): neither horizontal tuner has a minimap placement at all, so there is no
            tuned reference to convert into and nothing to reproduce -- see the constants' note.
          * Free -- the stored pair as an ABSOLUTE top-left, i.e. composed onto the origin, which is
            exactly what a Ctrl+drag produces (the drag end also flips Alignment to Free) -- EXCEPT
            at the pair (0, 0), which under Free means AUTO and defers to whichever anchor this
            ORIENTATION defaults to (Horizontal -> Damage Log, Vertical -> Minimap, the same mapping
            _on_changed's re-anchor uses). That is what makes an explicit Orientation change safe:
            it zeroes the stored pair (mod_settings._on_changed) rather than carrying coordinates
            tuned for the other orientation's surface across, and it must do so WITHOUT touching
            the Alignment value, because Free is sticky. The stored alignment stays Free; only the
            resolved base moves. The one capability lost is placing a bar at exactly logical
            (0, 0) -- accepted.

        EVERY SETTING IS READ HERE, PER PLACEMENT, none in __init__ (which binds at module import):
        size, orientation and alignment can all change after load. Size in particular has to be
        read here because the JS pushes the LARGE surface on its post-deadline re-assert, which
        round-trips back as onSizeChanged -> _place -- this read is what makes the two agree."""
        large = mod_settings.progress_bar_size() == mod_settings.PROGRESS_SIZE_LARGE
        vertical = (mod_settings.progress_bar_orientation()
                    == mod_settings.PROGRESS_ORIENT_VERTICAL)
        alignment = mod_settings.progress_bar_alignment()
        off_x, off_y = mod_settings.bar_pos_x(), mod_settings.bar_pos_y()
        if alignment == mod_settings.PROGRESS_ALIGN_FREE and (off_x, off_y) == (0, 0):
            alignment = (mod_settings.PROGRESS_ALIGN_MINIMAP if vertical
                         else mod_settings.PROGRESS_ALIGN_DAMAGE_LOG)
        if alignment == mod_settings.PROGRESS_ALIGN_FREE:
            base = (0, 0)
        elif alignment == mod_settings.PROGRESS_ALIGN_MINIMAP:
            if vertical:
                overhang = MM_TICK_OVERHANG_LARGE if large else MM_TICK_OVERHANG
                edge_x = self._mm_track_x_large if large else self._mm_track_x
                edge_y = MM_TRACK_Y_LARGE if large else MM_TRACK_Y
            else:
                overhang = 0
                edge_x, edge_y = space_x - max_x, space_y - max_y
            base = anchor_minimap(space_x, space_y, edge_x, edge_y,
                                  MINIMAP_SIZES[_minimap_size_index()], MM_GAP,
                                  self._mm_gap_bottom, overhang)
        elif vertical:
            base = anchor_centred_reduced(
                max_x, max_y, space_y, self._y_frac,
                VERTICAL_ANCHOR_Y_SHIFT_LARGE if large else VERTICAL_ANCHOR_Y_SHIFT)
        else:
            base = anchor_centred_reduced(max_x, max_y, space_y, self._y_frac,
                                          self._y_shift_large if large else self._y_shift)
        return anchor_offset(base, off_x + self._x_off, off_y)

    def _extent(self, window):
        """The window's movable extent (= logical space - surface), read by clamping it to the far
        corner with a LEFT/TOP anchor -- the self-calibration battle_view._place uses, and the whole
        reason neither this module nor the domain has to know the surface size.

        MEMOIZED, because the measurement is a WINDOW MOVE: a Ctrl+drag calls drag() per mouse
        movement and an un-cached read cost a second native move() -- to (1<<20, 1<<20) -- per
        pointer event, which is what made the bar visibly jump around the cursor. The extent is a pure function of
        the surface size and the logical space, so it cannot change mid-gesture; _place invalidates
        it for the three things that DO change it (first placement, onSizeChanged, interface
        scale)."""
        if self._extent_cache is None:
            window.move(_FAR, _FAR, xAnchor=PositionAnchor.LEFT, yAnchor=PositionAnchor.TOP)
            self._extent_cache = window.position
        return self._extent_cache

    def _space(self, window):
        """The FULL logical GUI space (width, height) the window is moved in = extent + surface size.

        THE DRAG'S GAIN IS EXACTLY 1 BECAUSE OF THIS, and only because of this. _extent recovers
        space - surface (all a far-sentinel clamp can see), so mapping the cursor's screen fraction
        onto it scales every movement by (space - surface) / space -- measured ~0.74 on x, i.e. "the
        bar moves slower than the cursor". The missing term is the window's OWN size, and Wulf hands
        it over directly: ``Window.size`` is ``self.proxy.windowSize``, the sibling of the
        ``windowPosition`` that ``.position`` reads, so it is in the SAME logical units as
        ``.position`` and ``move()`` by construction -- WG's own tooltip_positioner.py subtracts a
        ``window.size`` width straight from a coordinate it then feeds to ``window.move()``. No rem
        conversion, no interface-scale factor, nothing guessed.

        Read live rather than memoized: unlike _extent this is a plain property read, not a window
        move, so it costs nothing per pointer event. Fail-soft to the extent alone (Wulf itself
        returns (0.0, 0.0) for a window with no proxy, which cannot be moved either)."""
        max_x, max_y = self._extent(window)
        try:
            width, height = window.size
            return max_x + int(width), max_y + int(height)
        except Exception:
            return max_x, max_y

    def _place(self, window):
        """Place the window off whichever anchor the Alignment setting selects (see _resolve).
        Fail-soft: a positioning error must never blank the bar.

        THE CACHE INVALIDATION POINT for _extent, and the only one needed: every reason the extent
        can move -- the first placement, the JS's resize (onSizeChanged, i.e. a Default<->Large
        flip), an interface-scale change and a minimap resize (both apply_position) -- already
        routes through here. _space's own extent read is free, having been warmed one line above."""
        try:
            self._extent_cache = None
            max_x, max_y = self._extent(window)
            space_x, space_y = self._space(window)
            x, y = self._resolve(max_x, max_y, space_x, space_y)
            window.move(x, y, xAnchor=PositionAnchor.LEFT, yAnchor=PositionAnchor.TOP)
        except Exception:
            LOG_CURRENT_EXCEPTION()

    def drag(self, phase, cursor=None):
        """The Ctrl+left-button reposition gesture. `phase` is "start", "move" or "end", reported by
        adapter/battle_input off WG's own input dispatchers -- no JS, no delta, no wire protocol.
        `cursor` is the position the reporting mouse EVENT carried (gui.g_mouseEventHandlers hands us
        ``event.cursorPosition``), or None from the key/AvatarInputHandler paths that have no event --
        in which case we read GUI.mcursor() ourselves. Both go through the same unit-agnostic mapping.

        EVERY MOVE IS AN ABSOLUTE PLACEMENT. The live cursor is mapped into this window's logical GUI
        space (domain.cursor_top_left, which is UNCLAMPED -- a bar may be parked past any screen
        edge -- and owns the unit-agnostic
        read), then offset by the grab recorded at "start" so the bar keeps the point it was grabbed
        by instead of teleporting its corner under the cursor. Nothing accumulates, so nothing can
        drift, no gain factor exists to get wrong, and the gain is exactly 1 (see _space).

        A "move" ARRIVING FIRST IS TREATED AS THE START. battle_input's mouse wrap can latch the
        gesture on the first movement (with the cursor raised, the button press may never reach the
        key dispatcher), so the grab is recorded by whichever event gets here first.

        THE GESTURE IS OWNED PER HOST, decided ONCE. Ctrl+left-button is sampled globally off WG's
        input dispatchers and battle_bridge hands the event to BOTH bars unconditionally, so without
        a spatial gate a Ctrl+drag anywhere on screen dragged whichever bar was open -- including
        while the user was dragging another mod's UI. This host claims the gesture only if it BEGAN
        inside its own window rect (domain.cursor_in_rect against window.position + the surface size,
        which _space already recovers as space - extent -- no extra engine call). The decision is
        latched: a claimed gesture is never re-tested (that would drop the bar the moment the cursor
        left the rect) and a DECLINED one is never reconsidered (`_declined`, cleared on the next
        "start"/"end"), so a foreign drag sweeping the cursor over us cannot hijack the bar halfway.

        ONLY THE END PERSISTS, and only if the gesture actually MOVED. A live move writes the
        in-memory value alone -- that is all _resolve reads -- because a settings write per movement
        would mean an MSA updateModSettings + saveState at pointer rate. And a gesture that never
        moved writes nothing at all: `_drag_pos` stays None, so no set_bar_position runs -- which
        matters MORE now than under the retired 0/0 sentinel, because that call also flips Alignment
        to Free. A stray Ctrl+click on the bar must not silently opt the user out of the anchored
        alignment (and of every future change to that anchor) without moving anything.

        Fail-soft throughout: an unreadable cursor leaves the window exactly where it is, and nothing
        raises into the engine's input path."""
        if self._active is None:
            return
        try:
            if phase == "end":
                pos = self._drag_pos
                self._grab = None
                self._drag_pos = None
                self._declined = False
                if pos is not None:
                    mod_settings.set_bar_position(pos[0], pos[1], persist=True)
                return
            if phase == "start":
                self._declined = False
            elif self._declined:
                return                          # not our gesture; decided at its start
            window = self._active[0]
            # READ BEFORE _extent: a cold extent cache measures by MOVING the window to the far
            # sentinel, which would make this read the sentinel corner instead of where the bar is.
            origin = window.position
            # ONE extent measurement PER GESTURE: _extent's read is a real window MOVE (the far
            # sentinel), so an un-memoized read here would teleport the window per pointer event --
            # which is what made the bar visibly jump around the cursor. Only _place invalidates it.
            max_x, max_y = self._extent(window)
            space_x, space_y = self._space(window)
            if cursor is None:
                cursor = _cursor_position()
            screen = _screen_resolution()
            if phase == "start" or self._grab is None:
                # The grab is measured off the UNCLAMPED mapping: the cursor can legitimately sit
                # beyond the movable extent (the screen's bottom-right corner always does, by the
                # surface size), and clamping the measurement would bake that error into the offset
                # for the whole gesture.
                spot = cursor_logical(cursor, screen, space_x, space_y)
                if spot is None:
                    return                      # unreadable cursor -> no grab, no move
                # OWNERSHIP GATE (start only -- see the docstring): the surface size is
                # space - extent, so the rect needs nothing this handler has not already read.
                if not cursor_in_rect(spot, origin, (space_x - max_x, space_y - max_y)):
                    self._declined = True
                    return                      # the gesture began on somebody else's box
                bx, by = self._resolve(max_x, max_y, space_x, space_y)
                self._grab = (bx - spot[0], by - spot[1])
                self._drag_pos = None
                return                          # the bar is already where it was grabbed
            pos = cursor_top_left(cursor, screen, space_x, space_y,
                                  self._grab[0], self._grab[1])
            if pos is None:
                return
            window.move(pos[0], pos[1], xAnchor=PositionAnchor.LEFT, yAnchor=PositionAnchor.TOP)
            self._drag_pos = pos
            mod_settings.set_bar_position(pos[0], pos[1], persist=False)
        except Exception:
            LOG_CURRENT_EXCEPTION()

    def apply_position(self):
        """Re-place this bar's window if open. Called from battle_bridge on an interface-scale
        change (the proportional anchor must follow the resized logical space) and on a MINIMAP
        RESIZE (the minimap alignment's base anchor moves with the minimap's width -- the size
        index is re-read here, per placement, so no state has to be invalidated). No-op when
        closed."""
        if self._active is None:
            return
        self._place(self._active[0])

    def open_window(self):
        """Idempotently open this bar's window. Returns its _BarView (read ``.viewModel`` to push
        into), or None on failure / res_map not yet registered."""
        if self._active is not None:
            return self._active[1]
        try:
            layout = self._layout_id()
            if layout is None or layout < 0:
                LOG_DEBUG("%s res_map layout '%s' unresolved -- a one-time client restart is "
                          "needed for OpenWG to register it." % (self._tag, self.item_id))
                return None
            view = _BarView(layout, self._vm_factory())
            window = _BarWindow(view, self._place)
            # Publish the singleton BEFORE load() so the view's _onLoading initial push (which calls
            # back through battle_bridge.refresh() -> active_view()) sees us.
            self._active = (window, view)
            window.load()
            LOG_DEBUG("%s window opened (layoutID=%s, layer=WINDOW, content-sized)"
                      % (self._tag, layout))
            return view
        except Exception:
            LOG_CURRENT_EXCEPTION()
            self._active = None
            return None

    def close_window(self):
        """Destroy this bar's window if open. MUST be called on battle teardown alongside the other
        windows' close_window()s or the window leaks across battles."""
        if self._active is None:
            return
        window = self._active[0]
        self._active = None
        try:
            window.detach()          # unhook onSizeChanged before the window goes away
            window.destroy()
            LOG_DEBUG("%s window destroyed" % self._tag)
        except Exception:
            LOG_CURRENT_EXCEPTION()

    def active_view(self):
        """The currently-open _BarView, or None."""
        return None if self._active is None else self._active[1]
