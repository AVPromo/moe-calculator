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
Read that first. The difference here is placement: a bar is CENTRED horizontally and placed
PROPORTIONALLY down the screen (domain.positioning.anchor_centred), not at a fixed logical corner
-- unless the user Ctrl+DRAGGED it somewhere, which stores a top-left in that same logical space
and takes over (anchor_pinned; 0/0 == auto, so an untouched install is byte-identical).

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
from moe_calculator.domain.positioning import (anchor_pinned, cursor_in_rect, cursor_logical,
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
    ``y_off`` are the bar's anchor constants (domain/constants), and ``tag`` prefixes its log lines.
    ``y_off_large`` is the same compensation for the LARGE size mode -- a bigger surface needs a
    different Y term (see the constants' derivations), and it is read LATE, inside _place, NOT frozen
    here: these arguments are bound at MODULE IMPORT, so a size chosen after that (or changed between
    battles) would otherwise keep using whichever value was current at first load, forever.
    """

    def __init__(self, item_id, vm_factory, y_frac, x_off, y_off, y_off_large, tag):
        self.item_id = item_id
        self._vm_factory = vm_factory
        self._y_frac = y_frac
        self._x_off = x_off
        self._y_off = y_off
        self._y_off_large = y_off_large
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

    def _resolve(self, max_x, max_y):
        """This bar's top-left in logical GUI space, given the movable extent: the user's
        Ctrl+DRAGGED position when one is stored, else the shipped proportional anchor
        (domain.anchor_pinned -- 0/0 means auto, so an untouched install is unchanged).

        The y offset cancels the composition's intra-surface top offset (the JS shifts the whole
        bar into positive document coordinates) and converts the fraction from "of the movable
        extent" to "of the viewport" -- see the constant's own comment. It is picked HERE, per
        placement, off the live size setting: the JS pushes the LARGE surface on its post-deadline
        re-assert, which round-trips back as onSizeChanged -> _place, so this read is what makes
        the two agree."""
        large = mod_settings.progress_bar_size() == mod_settings.PROGRESS_SIZE_LARGE
        y_off = self._y_off_large if large else self._y_off
        return anchor_pinned(max_x, max_y, mod_settings.bar_pos_x(), mod_settings.bar_pos_y(),
                             self._y_frac, self._x_off, y_off)

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
        """Place the window: centred horizontally and PROPORTIONALLY down the screen, or wherever
        the user dragged it. Fail-soft: a positioning error must never blank the bar.

        THE CACHE INVALIDATION POINT for _extent, and the only one needed: every reason the extent
        can move -- the first placement, the JS's resize (onSizeChanged, i.e. a Default<->Large
        flip) and an interface-scale change (apply_position) -- already routes through here."""
        try:
            self._extent_cache = None
            max_x, max_y = self._extent(window)
            x, y = self._resolve(max_x, max_y)
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
        edge -- and also owns the (0, 0) auto-sentinel nudge and the unit-agnostic
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
        moved writes nothing at all: `_drag_pos` stays None, so a stray Ctrl+click cannot convert the
        0/0 AUTO sentinel into an explicit pin at the anchor the bar is already on (which would be a
        silent opt-out of every future anchor change).

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
                bx, by = self._resolve(max_x, max_y)
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
        """Re-place this bar's window if open. Called on interface-scale change (battle_bridge) so
        the proportional anchor -- or a stored drag position -- follows the resized logical space.
        No-op when closed."""
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
