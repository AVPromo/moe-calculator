# -*- coding: utf-8 -*-
"""Engine-free tests for adapter/battle_input -- the ONE battle input listener.

That module owns two monkey-patches on WG's central battle input dispatchers and, between them,
THREE consumers: the corner overlay's Alt peek, the bars' Ctrl hold, and the bars' Ctrl+left-button
REPOSITION GESTURE. The single-callback-slot hazard is the whole reason it is one module: installing
a second listener for a second consumer silently REPLACES the first, which is exactly how the Alt
peek was killed once before -- so the Alt regression below is not decoration.

Everything the module touches (BigWorld.isKeyDown, Keys, AvatarInputHandler) is lazy-imported
INSIDE its functions, which is what lets this file stub them as plain modules and drive the real
code with the game closed."""
import sys
import types

import pytest


def _stub(name, **attrs):
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        p = ".".join(parts[:i])
        if p not in sys.modules:
            sys.modules[p] = types.ModuleType(p)
    mod = sys.modules[name]
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


# The engine's key codes, real values from the client's Keys.py.
KEY_LALT, KEY_RALT = 56, 184
KEY_LCONTROL, KEY_RCONTROL = 29, 157
KEY_LEFTMOUSE = 256
KEY_I = 23

_DOWN = set()          # the keys the fake engine currently reports as held

_stub("Keys", KEY_LALT=KEY_LALT, KEY_RALT=KEY_RALT, KEY_LCONTROL=KEY_LCONTROL,
      KEY_RCONTROL=KEY_RCONTROL, KEY_LEFTMOUSE=KEY_LEFTMOUSE, KEY_I=KEY_I)
_stub("BigWorld", isKeyDown=lambda k: k in _DOWN)
# WG's own non-monkey-patch mouse registry: a plain set() that game.handleMouseEvent iterates.
_stub("gui", g_mouseEventHandlers=set())


class _MouseEvent(object):
    """A stand-in for the BigWorld mouse event game.handleMouseEvent passes each registry member.
    `cursorPosition` is the only field we read (game.py's convertMouseEvent reads it too)."""

    def __init__(self, cursor=(0.25, -0.5)):
        self.cursorPosition = cursor


class _AvatarInputHandler(object):
    """A stand-in for WG's central battle input dispatcher, with the two methods the module wraps.
    Each records that it ran, so a wrapper that fails to call through is visible."""

    def __init__(self):
        self.keys = []
        self.moves = []

    def handleKeyEvent(self, isDown, key, mods, event=None):
        self.keys.append((isDown, key))
        return "wg-key-result"

    def handleMouseEvent(self, dx, dy, dz):
        self.moves.append((dx, dy, dz))
        return "wg-mouse-result"


from moe_calculator.adapter import battle_input          # noqa: E402


@pytest.fixture
def wired():
    """A freshly-installed listener over a fresh fake AvatarInputHandler, plus the recorded
    callbacks. Resets every module global, because the install guard is deliberately one-shot
    per process."""
    _DOWN.clear()
    handler_module = _stub("AvatarInputHandler")
    handler_module.AvatarInputHandler = _AvatarInputHandler
    sys.modules["gui"].g_mouseEventHandlers = set()
    battle_input._installed = False
    battle_input._mouse_installed = False
    battle_input._gui_mouse_installed = False
    battle_input._alt_held = False
    battle_input._ctrl_held = False
    battle_input._drag_active = False
    battle_input._hotkey_keys = []
    battle_input._on_hotkey = None
    battle_input._hotkey_down = False
    changes = []
    drags = []
    # `drags` records PHASES only; the cursor the gesture carries has its own test, which installs
    # its own recording callback (a repeat install just refreshes the slot).
    assert battle_input.install_alt_key_listener(lambda a, c: changes.append((a, c)),
                                                lambda phase, _cursor=None: drags.append(phase))
    yield _AvatarInputHandler(), changes, drags
    battle_input._installed = False
    battle_input._mouse_installed = False
    battle_input._gui_mouse_installed = False
    battle_input._on_change = None
    battle_input._on_drag = None
    _DOWN.clear()


def _key(inst, key=KEY_LCONTROL, is_down=True):
    """Fire one key event through the PATCHED class method, as the engine would."""
    return _AvatarInputHandler.handleKeyEvent(inst, is_down, key, 0, None)


def _move(inst, dx=1, dy=0):
    return _AvatarInputHandler.handleMouseEvent(inst, dx, dy, 0)


# --- THE ALT PEEK REGRESSION -------------------------------------------------------------------

def test_alt_transitions_still_reach_the_callback(wired):
    # THE CALLBACK SLOT THAT GETS CLOBBERED. The corner overlay's "Battle Widget on Alt Key" mode
    # is driven by exactly this, and the reposition gesture had to be folded into the SAME listener
    # rather than installing a second one.
    inst, changes, _drags = wired
    _DOWN.add(KEY_LALT)
    _key(inst)
    assert changes == [(True, False)]
    _DOWN.discard(KEY_LALT)
    _key(inst)
    assert changes == [(True, False), (False, False)]


def test_ctrl_transitions_are_reported_alongside_alt(wired):
    inst, changes, _drags = wired
    _DOWN.add(KEY_LCONTROL)
    _key(inst)
    assert changes == [(False, True)]


def test_a_repeat_state_fires_nothing(wired):
    inst, changes, _drags = wired
    _DOWN.add(KEY_RALT)
    _key(inst)
    _key(inst)
    _key(inst)
    assert changes == [(True, False)]


def test_the_left_button_alone_never_fires_the_alt_ctrl_callback(wired):
    # The button is sampled for the GESTURE only. Firing _on_change on it would cost a full battle
    # re-push on every click in a battle, for a state nothing reads.
    inst, changes, _drags = wired
    _DOWN.add(KEY_LEFTMOUSE)
    _key(inst, KEY_LEFTMOUSE)
    assert changes == []


# --- THE GESTURE: Ctrl HELD *AND* THE LEFT BUTTON DOWN -----------------------------------------

def test_ctrl_plus_button_starts_the_gesture(wired):
    inst, _changes, drags = wired
    _DOWN.add(KEY_LCONTROL)
    _key(inst)
    assert drags == [], "Ctrl alone is not a gesture -- it only raises the cursor"
    _DOWN.add(KEY_LEFTMOUSE)
    _key(inst, KEY_LEFTMOUSE)
    assert drags == ["start"]


def test_the_button_alone_never_starts_the_gesture(wired):
    inst, _changes, drags = wired
    _DOWN.add(KEY_LEFTMOUSE)
    _key(inst, KEY_LEFTMOUSE)
    _move(inst)
    assert drags == []


def test_releasing_the_button_ends_the_gesture(wired):
    inst, _changes, drags = wired
    _DOWN.update((KEY_LCONTROL, KEY_LEFTMOUSE))
    _key(inst, KEY_LEFTMOUSE)
    _DOWN.discard(KEY_LEFTMOUSE)
    _key(inst, KEY_LEFTMOUSE, False)
    assert drags == ["start", "end"]


def test_releasing_ctrl_mid_gesture_ends_it_too(wired):
    # Ctrl is WG's own free-cursor key: letting go of it puts the cursor away, so the gesture is
    # over whatever the button is doing. Otherwise the drag would stay armed invisibly.
    inst, _changes, drags = wired
    _DOWN.update((KEY_LCONTROL, KEY_LEFTMOUSE))
    _key(inst, KEY_LEFTMOUSE)
    _DOWN.discard(KEY_LCONTROL)
    _key(inst, KEY_LCONTROL, False)
    assert drags == ["start", "end"]


def test_a_mouse_move_during_the_gesture_reports_a_move(wired):
    inst, _changes, drags = wired
    _DOWN.update((KEY_LCONTROL, KEY_LEFTMOUSE))
    _key(inst, KEY_LEFTMOUSE)
    _move(inst)
    _move(inst)
    assert drags == ["start", "move", "move"]


def test_a_mouse_move_outside_the_gesture_reports_nothing(wired):
    inst, _changes, drags = wired
    _move(inst)
    _DOWN.add(KEY_LCONTROL)
    _key(inst)
    _move(inst)
    assert drags == []


def test_the_mouse_wrap_can_start_the_gesture_on_its_own(wired):
    # THE BUTTON PRESS MAY NEVER ARRIVE AS A KEY EVENT: with the cursor raised over the HUD the GUI
    # can consume it before WG's key dispatcher runs (game.handleMouseEvent / handleKeyEvent both
    # early-return on GUI.handleMouseEvent). Sampling the SAME combined state inside the mouse wrap
    # costs one extra isKeyDown per move and makes the gesture start on the first movement instead.
    inst, _changes, drags = wired
    _DOWN.update((KEY_LCONTROL, KEY_LEFTMOUSE))
    _move(inst)
    assert drags == ["start", "move"]


# --- THE NON-MONKEY-PATCH MOUSE HOOK: gui.g_mouseEventHandlers ---------------------------------
# A plain set() the engine iterates in game.handleMouseEvent, so joining it is set.add -- no patch,
# no ownership marker, no unrestored wrap -- and the event it hands us carries the cursor position
# the engine itself measured. It is an ADDITION to the AvatarInputHandler wrap, not a replacement,
# because the set is iterated LAST in game.handleMouseEvent: after the early return on
# GUI.handleMouseEvent(event) AND after the one on inputHandler.handleMouseEvent(dx, dy, dz).


def _gui_members():
    return sys.modules["gui"].g_mouseEventHandlers


def _gui_mouse(cursor=(0.25, -0.5)):
    """Fire one mouse event through every registry member, as game.handleMouseEvent does."""
    return [member(_MouseEvent(cursor)) for member in list(_gui_members())]


def test_the_install_joins_wgs_mouse_registry(wired):
    assert battle_input._handle_gui_mouse_event in _gui_members()


def test_a_repeat_install_does_not_add_a_second_registry_member(wired):
    # A set only dedupes a STABLE object, which is why the member is a module-level function rather
    # than a closure over the callbacks -- a closure would stack one member per install.
    before = len(_gui_members())
    assert battle_input.install_alt_key_listener(lambda a, c: None, lambda p, c=None: None)
    assert len(_gui_members()) == before


def test_the_registry_hook_reports_the_gesture_with_the_events_own_cursor(wired):
    _inst, _changes, _drags = wired
    seen = []
    assert battle_input.install_alt_key_listener(lambda a, c: None,
                                                lambda phase, cursor=None: seen.append((phase,
                                                                                        cursor)))
    _DOWN.update((KEY_LCONTROL, KEY_LEFTMOUSE))
    _gui_mouse((0.25, -0.5))
    assert seen == [("start", (0.25, -0.5)), ("move", (0.25, -0.5))]
    _gui_mouse((0.75, 0.5))
    assert seen[-1] == ("move", (0.75, 0.5))


def test_the_avatar_input_wrap_reports_no_cursor_and_the_consumer_falls_back(wired):
    # WG converts the event to dx/dy/dz before the inputHandler ever sees it, so this path has no
    # cursorPosition to forward -- it passes None and the host reads GUI.mcursor() itself.
    inst, _changes, _drags = wired
    seen = []
    assert battle_input.install_alt_key_listener(lambda a, c: None,
                                                lambda phase, cursor=None: seen.append((phase,
                                                                                        cursor)))
    _DOWN.update((KEY_LCONTROL, KEY_LEFTMOUSE))
    _move(inst)
    assert seen == [("start", None), ("move", None)]


def test_the_registry_hook_never_consumes_the_event(wired):
    # A truthy return marks the event consumed and early-returns out of game.handleMouseEvent, eating
    # every mouse move for the rest of the client's chain. WG's own member returns None for this.
    _DOWN.update((KEY_LCONTROL, KEY_LEFTMOUSE))
    assert _gui_mouse() == [False]
    _DOWN.clear()
    assert _gui_mouse() == [False]


def test_the_registry_hook_reports_nothing_outside_the_gesture(wired):
    _inst, _changes, drags = wired
    _gui_mouse()
    _DOWN.add(KEY_LCONTROL)
    _gui_mouse()
    assert drags == []


def test_a_raising_consumer_never_escapes_the_registry_hook(wired):
    def _boom(*_a, **_k):
        raise RuntimeError("boom")

    assert battle_input.install_alt_key_listener(_boom, _boom)
    _DOWN.update((KEY_LCONTROL, KEY_LEFTMOUSE))
    assert _gui_mouse() == [False]


def test_a_cursorless_event_degrades_to_none(wired):
    # Defensive: an event shape without cursorPosition must pass None (the GUI.mcursor() fallback),
    # never raise into the engine's input chain.
    _inst, _changes, _drags = wired
    seen = []
    assert battle_input.install_alt_key_listener(lambda a, c: None,
                                                lambda phase, cursor=None: seen.append(cursor))
    _DOWN.update((KEY_LCONTROL, KEY_LEFTMOUSE))
    assert battle_input._handle_gui_mouse_event(object()) is False
    assert seen == [None, None]


# --- OWNERSHIP: ONE LISTENER, WG's HANDLER ALWAYS RUNS FIRST ------------------------------------

def test_both_wrappers_call_through_and_return_wgs_own_result(wired):
    # The wrappers only OBSERVE input: WG's handler runs first and its return value (was the event
    # consumed?) is preserved untouched.
    inst, _changes, _drags = wired
    assert _key(inst) == "wg-key-result"
    assert _move(inst) == "wg-mouse-result"
    assert inst.keys and inst.moves


def test_a_repeat_install_refreshes_the_callbacks_without_double_wrapping(wired):
    inst, _changes, _drags = wired
    key_wrapper = _AvatarInputHandler.handleKeyEvent
    mouse_wrapper = _AvatarInputHandler.handleMouseEvent
    changes2, drags2 = [], []
    assert battle_input.install_alt_key_listener(lambda a, c: changes2.append((a, c)),
                                                drags2.append)
    assert _AvatarInputHandler.handleKeyEvent is key_wrapper, "the key patch was re-applied"
    assert _AvatarInputHandler.handleMouseEvent is mouse_wrapper, "the mouse patch was re-applied"
    _DOWN.add(KEY_LALT)
    _key(inst)
    assert changes2 == [(True, False)], "a repeat install must refresh the callback slot"


def test_each_patch_stashes_wgs_original_as_its_ownership_marker(wired):
    # The double-wrap guard across a dev reload: a prior wrapper carries the REAL original, so a
    # re-install can never stack a wrapper on a wrapper.
    assert getattr(_AvatarInputHandler.handleKeyEvent, "_moe_alt_original", None) is not None
    assert getattr(_AvatarInputHandler.handleMouseEvent, "_moe_drag_original", None) is not None


def test_a_raising_callback_never_escapes_into_the_engine(wired):
    # Fail-soft, both wraps: an input observer must never turn a consumer's bug into a battle crash.
    inst, _changes, _drags = wired

    def _boom(*_a):
        raise RuntimeError("boom")

    assert battle_input.install_alt_key_listener(_boom, _boom)
    _DOWN.update((KEY_LCONTROL, KEY_LEFTMOUSE))
    assert _key(inst, KEY_LEFTMOUSE) == "wg-key-result"
    assert _move(inst) == "wg-mouse-result"


# --- THE HOTKEY SLOT: EDGE-TRIGGERED, ARBITRARY CHORD -------------------------------------------

def test_hotkey_fires_once_per_press(wired):
    inst, _changes, _drags = wired
    fires = []
    battle_input.set_hotkey([KEY_I], lambda: fires.append(1))
    _DOWN.add(KEY_I)
    _key(inst)          # not-down -> down: fire
    _key(inst)          # still down: no fire
    assert fires == [1]
    _DOWN.discard(KEY_I)
    _key(inst)          # released
    _DOWN.add(KEY_I)
    _key(inst)          # down again: fire
    assert fires == [1, 1]


def test_hotkey_chord_needs_all_keys(wired):
    inst, _c, _d = wired
    fires = []
    battle_input.set_hotkey([KEY_LCONTROL, KEY_I], lambda: fires.append(1))
    _DOWN.add(KEY_I)
    _key(inst)
    assert fires == []
    _DOWN.add(KEY_LCONTROL)
    _key(inst)
    assert fires == [1]


def test_empty_hotkey_never_fires(wired):
    inst, _c, _d = wired
    fires = []
    battle_input.set_hotkey([], lambda: fires.append(1))
    _DOWN.add(KEY_I)
    _key(inst)
    assert fires == []
