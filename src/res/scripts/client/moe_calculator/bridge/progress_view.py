# -*- coding: utf-8 -*-
"""Host the centre-screen transient MoE progress bar as its OWN OpenWG-registered Gameface
WINDOW over the battle HUD.

A near-clone of bridge/battle_view.py -- deliberately a CLONE and not a parameterization of it:
that module's `_active` is a module-level singleton and apply_position / _place / active_view all
hard-reference it, so one module cannot host two windows. Each therefore owns its own singleton
and, critically, its OWN ModDynAccessor: reusing MoEBattleView._layoutID here would resolve the
wrong layout and open a second copy of the corner overlay.

Everything WHY-shaped about the hosting model lives in battle_view.py's docstrings (why a
registered window and not a garage-style inject; why WindowLayer.WINDOW and not OVERLAY; why NOT
WINDOW_FULLSCREEN; the one-time client restart the res_map entry costs). Read that first. The one
difference here is placement: the bar is CENTRED horizontally and placed PROPORTIONALLY down the
screen (domain.positioning.anchor_centred) rather than at a fixed logical corner offset.

PC-only (needs the live client); not imported under pytest without stubs. Python 2.7 runtime.
"""
from moe_calculator._compat import LOG_CURRENT_EXCEPTION, LOG_DEBUG

from frameworks.wulf import ViewSettings, ViewFlags, WindowFlags, WindowLayer, PositionAnchor
from gui.impl.pub import ViewImpl, WindowImpl
from openwg_gameface import ModDynAccessor

from moe_calculator.bridge.view_models import ProgressVM
from moe_calculator.domain.constants import (
    PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_FRAC, PROGRESS_ANCHOR_Y_OFFSET)
from moe_calculator.domain.positioning import anchor_centred

# itemID registered in mods/configs/res_map/MoEProgressView.json -- keep in lockstep. It MUST
# differ from MoEBattleView's: OpenWG assigns the numeric resId positionally when it rebuilds
# res_map.json, so two entries sharing an itemID collide and one layout becomes unreachable.
RES_MAP_ITEM_ID = "MoEProgressView"


class MoEProgressView(ViewImpl):
    """The registered Gameface view; its root ViewModel is our ProgressVM."""

    # Its OWN deferred resId accessor -- see the module docstring on why this is not shared.
    _layoutID = ModDynAccessor(RES_MAP_ITEM_ID)

    def __init__(self):
        settings = ViewSettings(self._layoutID(), ViewFlags.VIEW, ProgressVM())
        super(MoEProgressView, self).__init__(settings)

    @property
    def viewModel(self):
        return super(MoEProgressView, self).getViewModel()

    def _onLoading(self, *args, **kwargs):
        super(MoEProgressView, self)._onLoading(*args, **kwargs)
        # Push once the view (and its bound VM) is live so the bar has real values in hand for
        # its first transient. Lazy import avoids a progress_view <-> battle_bridge cycle.
        try:
            from moe_calculator.bridge import battle_bridge
            battle_bridge.refresh()
        except Exception:
            LOG_CURRENT_EXCEPTION()


# A large sentinel offset used to clamp the window to the far corner (LEFT/TOP anchor) so we can
# read back the movable extent (= logical space - windowSize) and place proportionally.
_FAR = 1 << 20

# THE SURFACE IS SIZED FROM THE JS, NOT FROM HERE. There is no Python-side size setter anywhere
# (native PyObjectWindow has no resize / no autoSize; `windowSize` writes land silently in
# __dict__ and do nothing), and no res_map field for size -- Layout.parameters accepts only
# extension / entrance / impl. What actually sizes a Gameface view is the view PUSHING its own
# size to C++ via the `viewEnv` global: viewEnv.resizeViewRem(w, h) (rem == logical px). A view
# that never calls it gets the engine's "default view size" fallback after a
# `Size calculation timeout` -- a flat 256x256 logical px, which is what clipped this bar.
# WG precedent for the same window shape (WindowFlags.WINDOW, content view, in battle):
# DogTagMarkerView.js calls resize(500, 300, "rem") once on mount; ~85 WG views do this and none
# of them ever hits the timeout. So MoEProgress.js sizes the surface itself (its VIEW_W_REM /
# VIEW_H_REM) and each resize round-trips back here as Window._cResized -> onSizeChanged, which
# _onReady subscribes to so the placement is re-read against the REAL extent.
# PUSHING THE SIZE IS NOT SUFFICIENT ON ITS OWN, because the timeout's fallback runs LAST and
# WINS: live-measured, our resize landed at 04.8s and the deadline's "Set the default view size"
# action at 06.2s put the surface back to 256x256. The timeout fired because the document had no
# in-flow content to measure (the bar root is position:absolute), so the real fix is the static
# #moe-bar-box in MoEProgressView.html + MoEProgress.css. MoEProgress.js also re-asserts the size
# once after that deadline (SURFACE_REASSERT_MS) as a revertable guard -- each re-assert is another
# onSizeChanged -> _place, which is exactly why _onReady subscribes rather than placing once.
# WindowFlags.WINDOW_FULLSCREEN stays REJECTED regardless: a full-screen Coherent surface steals
# the whole-screen mouse hit-test whenever the cursor is raised (Ctrl) and pointer-events:none
# does NOT make the window rectangle click-through (battle_view.py:98-107). The surface rect IS
# the mouse hit rect, which is also why the JS collapses the input rect with
# viewEnv.setHitAreaPaddingsRem after resizing -- a ~480rem-wide surface across screen centre
# would otherwise be an input-stealing strip. See MoEProgress.js.


class MoEProgressWindow(WindowImpl):
    """Content-sized, input-transparent window hosting MoEProgressView over the HUD. Same flags
    and layer as MoEBattleWindow, for the same reasons (read its docstring): WindowFlags.WINDOW
    (NOT full-screen -- the Ctrl+click hit-test steal), layer WINDOW (7) so the modal in-battle
    menu at TOP_WINDOW (10) keeps its input, shown without focus."""

    def __init__(self, content):
        super(MoEProgressWindow, self).__init__(
            WindowFlags.WINDOW, content=content, layer=WindowLayer.WINDOW)

    def _onReady(self):
        self.show(focus=False)
        # RE-ARM EVERY MOUNT (dropped again in close_window -> detach): _place below reads the
        # movable extent by far-sentinel clamp, and at _onReady the surface is still the engine's
        # 256x256 default-size fallback -- MoEProgress.js pushes the real size a moment later.
        # Wulf fires onSizeChanged per resize, so re-place off that rather than trusting this one
        # shot. Plain `+=` is the WG idiom for a Wulf window Event (see Window.__attachToDecorator).
        self.onSizeChanged += self._on_size_changed
        _place(self)

    def _on_size_changed(self, _unique_id, _width, _height):
        """The JS resized our surface -> the movable extent changed -> re-place."""
        _place(self)

    def detach(self):
        """Drop the onSizeChanged subscription. Called from close_window BEFORE destroy so the
        listener never outlives a battle. Fail-soft -- teardown must not raise."""
        try:
            self.onSizeChanged -= self._on_size_changed
        except Exception:
            LOG_CURRENT_EXCEPTION()


def _place(window):
    """Centre the window horizontally and place its top edge PROPORTIONALLY down the screen.
    Self-calibrates exactly like battle_view._place: clamp to the far corner to read the movable
    extent (= logical space - surface), then hand it to domain.anchor_centred -- whose max_x // 2
    centres whatever surface width the JS asked for, without needing to know it here.
    PROGRESS_ANCHOR_Y_OFFSET cancels the composition's intra-surface top offset (the JS shifts the
    whole bar into positive document coordinates), so the bar does not move on screen.
    Fail-soft: a positioning error must never blank the bar."""
    try:
        window.move(_FAR, _FAR, xAnchor=PositionAnchor.LEFT, yAnchor=PositionAnchor.TOP)
        max_x, max_y = window.position
        x, y = anchor_centred(max_x, max_y, PROGRESS_ANCHOR_Y_FRAC, PROGRESS_ANCHOR_X_OFFSET,
                              PROGRESS_ANCHOR_Y_OFFSET)
        window.move(x, y, xAnchor=PositionAnchor.LEFT, yAnchor=PositionAnchor.TOP)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def apply_position():
    """Re-place the currently-open bar window. Called on interface-scale change (battle_bridge)
    so the proportional anchor follows the resized logical space. No-op when closed."""
    if _active is None:
        return
    _place(_active[0])


# Singleton (window, view) for the currently-open bar (None when closed).
_active = None


def open_window():
    """Idempotently open the progress-bar window. Returns its MoEProgressView (read
    `.viewModel` to push into), or None on failure / res_map not yet registered."""
    global _active
    if _active is not None:
        return _active[1]
    try:
        layout = MoEProgressView._layoutID()
        if layout is None or layout < 0:
            LOG_DEBUG("[moe-bar] res_map layout '%s' unresolved -- a one-time client "
                      "restart is needed for OpenWG to register it." % RES_MAP_ITEM_ID)
            return None
        view = MoEProgressView()
        window = MoEProgressWindow(view)
        # Publish the singleton BEFORE load() so the view's _onLoading initial push (which calls
        # back through battle_bridge.refresh() -> active_view()) sees us.
        _active = (window, view)
        window.load()
        LOG_DEBUG("[moe-bar] progress window opened (layoutID=%s, layer=WINDOW, content-sized)"
                  % layout)
        return view
    except Exception:
        LOG_CURRENT_EXCEPTION()
        _active = None
        return None


def close_window():
    """Destroy the progress-bar window if open. MUST be called on battle teardown alongside
    battle_view.close_window() or the window leaks across battles."""
    global _active
    if _active is None:
        return
    window = _active[0]
    _active = None
    try:
        window.detach()          # unhook onSizeChanged before the window goes away
        window.destroy()
        LOG_DEBUG("[moe-bar] progress window destroyed")
    except Exception:
        LOG_CURRENT_EXCEPTION()


def active_view():
    """The currently-open MoEProgressView, or None."""
    return None if _active is None else _active[1]
