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
PROPORTIONALLY down the screen (domain.positioning.anchor_centred), not at a fixed logical corner.

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
from moe_calculator.domain.positioning import anchor_centred

# A large sentinel offset used to clamp the window to the far corner (LEFT/TOP anchor) so we can
# read back the movable extent (= logical space - windowSize) and place proportionally.
_FAR = 1 << 20


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

    def _place(self, window):
        """Centre the window horizontally and place its top edge PROPORTIONALLY down the screen.
        Self-calibrates exactly like battle_view._place: clamp to the far corner to read the movable
        extent (= logical space - surface), then hand it to domain.anchor_centred -- whose
        max_x // 2 centres whatever surface width the JS asked for, without needing to know it here.
        The y offset cancels the composition's intra-surface top offset (the JS shifts the whole bar
        into positive document coordinates) and converts the fraction from "of the movable extent"
        to "of the viewport" -- see the constant's own comment. It is picked HERE, per placement, off
        the live size setting: the JS pushes the LARGE surface on its post-deadline re-assert, which
        round-trips back as onSizeChanged -> _place, so this read is what makes the two agree.
        Fail-soft: a positioning error must never blank the bar."""
        try:
            large = mod_settings.progress_bar_size() == mod_settings.PROGRESS_SIZE_LARGE
            y_off = self._y_off_large if large else self._y_off
            window.move(_FAR, _FAR, xAnchor=PositionAnchor.LEFT, yAnchor=PositionAnchor.TOP)
            max_x, max_y = window.position
            x, y = anchor_centred(max_x, max_y, self._y_frac, self._x_off, y_off)
            window.move(x, y, xAnchor=PositionAnchor.LEFT, yAnchor=PositionAnchor.TOP)
        except Exception:
            LOG_CURRENT_EXCEPTION()

    def apply_position(self):
        """Re-place this bar's window if open. Called on interface-scale change (battle_bridge) so
        the proportional anchor follows the resized logical space. No-op when closed."""
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
