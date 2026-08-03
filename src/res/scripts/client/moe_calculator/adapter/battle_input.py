# -*- coding: utf-8 -*-
"""In-battle input detection: the "Battle Widget on Alt Key" peek mode, the bars' Ctrl hold, and
the centre-screen bars' Ctrl+left-button REPOSITION GESTURE (which Python owns end to end).

Event-driven ON PURPOSE. A self-rescheduling ``BigWorld.callback`` poll STALLS ~2s into a
battle (see ``TASKS/shipped/mod-positioning-handoff.md``), so we do NOT poll. Instead we wrap
WG's own central battle dispatchers and sample the live key state at each event via
``BigWorld.isKeyDown``. ``isKeyDown`` read AT an input event (not on a timer) avoids the stall
entirely. TWO dispatchers, one per axis of the problem:

  * ``AvatarInputHandler.handleKeyEvent`` -- fires on every key down/up transition, and the engine
    reports MOUSE BUTTONS as key events too (``Keys.KEY_LEFTMOUSE``). Alt, Ctrl and the left
    button are all sampled here.
  * ``AvatarInputHandler.handleMouseEvent(dx, dy, dz)`` -- fires per mouse MOVE. That is the whole
    reason the reposition gesture needs no JS and no delta protocol: every movement event is an
    opportunity to re-place the window ABSOLUTELY from the live cursor position.

...plus a THIRD, non-monkey-patch mouse sampling point:

  * ``gui.g_mouseEventHandlers`` -- a plain ``set()`` the engine iterates in
    ``game.handleMouseEvent`` (WG's own consumers: hangarspace, armor_sub_presenter). ``set.add`` /
    ``set.discard`` instead of a patch, so no ownership marker and no unrestored wrap, and the event
    it hands us carries ``event.cursorPosition`` -- the position the engine itself measured, which
    makes ``GUI.mcursor()`` a fallback rather than the primary read.

IT IS AN ADDITION, NOT A REPLACEMENT, and the reason is WHERE the engine iterates the set. In
``game.handleMouseEvent`` (game.py:359-382) it comes LAST -- after an early return on
``GUI.handleMouseEvent(event)`` AND after one on ``inputHandler.handleMouseEvent(dx, dy, dz)``. So:

  * a move the raised Gameface/Flash cursor consumes never reaches the set at all (the wrap, which
    sits INSIDE the ``inputHandler`` call, is equally starved -- but only one of the two can be
    starved by the OTHER gate, so sampling both is strictly more coverage than either alone);
  * the set IS reached during our gesture, because holding Ctrl is what detaches the input handler
    (gui/Scaleform/managers/battle_input.py:85-88 -> ``avatar_getter.setForcedGuiControlMode`` ->
    ``AvatarInputHandler.__isDetached``), and a detached ``handleMouseEvent`` returns False before
    touching the control mode (AvatarInputHandler/__init__.py:377) instead of the True that
    ArcadeControlMode returns.

That same detach is also why ``GUI.mcursor().position`` is trustworthy while Ctrl is down: an
ATTACHED ArcadeControlMode.handleMouseEvent overwrites it with ``self._aimOffset`` on every single
move (control_modes.py:527), and only the detached short-circuit keeps it a real free cursor.

ONE LISTENER PER DISPATCHER, ONE CALLBACK SLOT EACH. ``_on_change`` and ``_on_drag`` are single
slots: installing a second listener for a second consumer would silently REPLACE the first (which
is how the overlay's Alt peek got killed once), so a new consumer EXTENDS this module rather than
adding an install of its own.

THE GESTURE IS SAMPLED IN EVERY HOOK, not just the key one. With the cursor raised over the HUD the
GUI can consume a mouse-button event before WG's key dispatcher ever sees it (``game.handleKeyEvent``
/ ``game.handleMouseEvent`` both early-return on the GUI), so a gesture that only ever started off a
key event could silently never start. Re-sampling the same combined state on every mouse event costs
one extra ``isKeyDown`` per move and makes the FIRST MOVEMENT start it instead. A move reported twice
(both hooks firing for one engine event) is harmless: the placement is ABSOLUTE, so the second report
recomputes the identical position.

Both wrappers ALWAYS run WG's original handler first and return its result, and the
g_mouseEventHandlers member always returns False -- they only OBSERVE input, never consume or alter
it. Ownership: each wrap stashes its own original on itself; the set membership needs none.

Game symbols (``BigWorld``, ``Keys``, ``AvatarInputHandler``) are lazy-imported inside the
functions so this module still imports under the Python 3 test interpreter with the game closed.
"""
from moe_calculator._compat import LOG_CURRENT_EXCEPTION, LOG_DEBUG

# One-time install guards (one per hook), the last-seen combined Alt / Ctrl state, and the two
# callback slots. `_drag_active` is the gesture's own latch -- Ctrl AND the left button.
_installed = False
_mouse_installed = False
_gui_mouse_installed = False
_alt_held = False
_ctrl_held = False
_drag_active = False
_on_change = None
_on_drag = None


def _alt_down_now():
    """True iff either the left or right Alt key is currently down (engine read)."""
    import BigWorld
    from Keys import KEY_LALT, KEY_RALT
    return bool(BigWorld.isKeyDown(KEY_LALT) or BigWorld.isKeyDown(KEY_RALT))


def _ctrl_down_now():
    """True iff either Control key is currently down (engine read). Ctrl is ALSO WG's own
    free-cursor key, which is exactly why the bars' drag gesture hangs off it: the mouse pointer
    is already up and hit-testable whenever this is true."""
    import BigWorld
    from Keys import KEY_LCONTROL, KEY_RCONTROL
    return bool(BigWorld.isKeyDown(KEY_LCONTROL) or BigWorld.isKeyDown(KEY_RCONTROL))


def _lmb_down_now():
    """True iff the LEFT MOUSE BUTTON is currently down (engine read). BigWorld reports mouse
    buttons as key codes, so this is the same ``isKeyDown`` read as the modifiers above."""
    import BigWorld
    from Keys import KEY_LEFTMOUSE
    return bool(BigWorld.isKeyDown(KEY_LEFTMOUSE))


def _update_alt_state():
    """Sample both modifiers and fire the callback only when EITHER combined state flips.

    The left button is deliberately NOT part of this callback: it is sampled for the GESTURE only
    (``_update_drag_state`` below), because firing the Alt/Ctrl consumers -- which re-push the whole
    battle model -- on every click in a battle would cost a refresh per shot for a state nothing
    reads."""
    global _alt_held, _ctrl_held
    alt = _alt_down_now()
    ctrl = _ctrl_down_now()
    if alt != _alt_held or ctrl != _ctrl_held:
        _alt_held = alt
        _ctrl_held = ctrl
        LOG_DEBUG("[moe-battle] Alt %s Ctrl %s" % ("down" if alt else "up",
                                                   "down" if ctrl else "up"))
        if _on_change is not None:
            _on_change(alt, ctrl)


def _update_drag_state(cursor=None):
    """Sample the GESTURE (Ctrl held AND the left button down) and report its transitions.

    ``_on_drag("start")`` / ``("end")`` fire on the latch's flips only, so a consumer can record the
    grab offset once and persist once. Both keys are read LIVE rather than off ``_ctrl_held``,
    because this also runs from the mouse hooks (see the module header) where the key wrap may never
    have run. `cursor` is the reporting event's own ``cursorPosition`` when there is one, else None
    (the consumer then reads GUI.mcursor() itself). Returns whether the gesture is live, so a mouse
    hook can decide to report a move."""
    global _drag_active
    active = _ctrl_down_now() and _lmb_down_now()
    if active != _drag_active:
        _drag_active = active
        LOG_DEBUG("[moe-battle] reposition gesture %s" % ("start" if active else "end"))
        if _on_drag is not None:
            _on_drag("start" if active else "end", cursor)
    return active


def _handle_gui_mouse_event(event):
    """The ``gui.g_mouseEventHandlers`` member: one mouse event, observed, never consumed.

    A MODULE-LEVEL FUNCTION ON PURPOSE -- the registry is a ``set``, so only a stable object makes
    ``add`` idempotent and ``discard`` possible; a closure would stack a new member per install.

    ALWAYS RETURNS FALSE: a truthy return marks the event consumed and early-returns out of
    ``game.handleMouseEvent``, which would eat every mouse move for the rest of the client's chain
    (WG's own member in armor_sub_presenter returns None for the same reason)."""
    try:
        if _update_drag_state(getattr(event, "cursorPosition", None)) and _on_drag is not None:
            _on_drag("move", getattr(event, "cursorPosition", None))
    except Exception:
        LOG_CURRENT_EXCEPTION()
    return False


def install_alt_key_listener(on_change, on_drag=None):
    """Wire both callback slots, join WG's ``g_mouseEventHandlers`` registry, and monkey-patch its
    two battle input dispatchers (once each).

    ``on_change(alt_held, ctrl_held)`` is invoked (guarded) only when one of the two combined
    states changes; BOTH are passed every time, so a consumer never has to remember the other.
    ``on_drag(phase, cursor)`` reports the Ctrl+left-button reposition gesture as ``"start"`` /
    ``"move"`` / ``"end"`` -- ``"move"`` once per mouse movement while it is live -- with the
    reporting event's own ``cursorPosition``, or None when the reporting hook had no event.

    Idempotent and self-healing: a repeat call just refreshes the callbacks; each hook is installed a
    single time. Returns True once the AvatarInputHandler hooks are in place, False if the class isn't
    importable yet (a later call retries). The g_mouseEventHandlers registry is joined FIRST and
    independently, so its own (import-safe, always-available) hook is never gated on that retry."""
    global _installed, _mouse_installed, _gui_mouse_installed, _on_change, _on_drag
    _on_change = on_change
    _on_drag = on_drag
    if not _gui_mouse_installed:
        try:
            from gui import g_mouseEventHandlers
            g_mouseEventHandlers.add(_handle_gui_mouse_event)   # a plain set() -- no patch to own
            _gui_mouse_installed = True
            LOG_DEBUG("[moe-battle] drag listener joined gui.g_mouseEventHandlers")
        except Exception:
            LOG_CURRENT_EXCEPTION()
    if _installed and _mouse_installed:
        return True
    try:
        from AvatarInputHandler import AvatarInputHandler
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return False

    if not _installed:
        original = AvatarInputHandler.handleKeyEvent
        # Never double-wrap (e.g. across a dev reload): a prior wrapper carries the real original.
        original = getattr(original, "_moe_alt_original", original)

        def _patched(self, *args, **kwargs):
            # Run WG's handler first and preserve its return (was-the-event-consumed?) value.
            result = original(self, *args, **kwargs)
            try:
                _update_alt_state()
                _update_drag_state()
            except Exception:
                LOG_CURRENT_EXCEPTION()
            return result

        _patched._moe_alt_original = original  # ownership marker
        AvatarInputHandler.handleKeyEvent = _patched
        _installed = True
        LOG_DEBUG("[moe-battle] Alt/Ctrl listener installed on AvatarInputHandler.handleKeyEvent")

    if not _mouse_installed:
        mouse_original = AvatarInputHandler.handleMouseEvent
        mouse_original = getattr(mouse_original, "_moe_drag_original", mouse_original)

        def _patched_mouse(self, *args, **kwargs):
            result = mouse_original(self, *args, **kwargs)
            try:
                # The gesture's own dx/dy are DELIBERATELY IGNORED: the consumer re-places the
                # window ABSOLUTELY from the live cursor position, so this is a tick, not a delta.
                # No event here either (WG converts it to dx/dy/dz first), hence no cursor to pass.
                if _update_drag_state() and _on_drag is not None:
                    _on_drag("move", None)
            except Exception:
                LOG_CURRENT_EXCEPTION()
            return result

        _patched_mouse._moe_drag_original = mouse_original  # ownership marker
        AvatarInputHandler.handleMouseEvent = _patched_mouse
        _mouse_installed = True
        LOG_DEBUG("[moe-battle] drag listener installed on AvatarInputHandler.handleMouseEvent")
    return True
