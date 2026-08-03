# -*- coding: utf-8 -*-
"""Engine-free tests for bridge.bar_window.BarHost's Ctrl+drag gesture: `drag(phase)`, which is the
WHOLE reposition channel -- adapter/battle_input reports "start" / "move" / "end" and each move
re-places the window ABSOLUTELY from the live cursor. The window/view hosting itself
(open_window/_place/apply_position) needs the live client and is out of scope -- only the pure-ish
placement math is covered here.

Technique is test_progress_bridge's: stub the game-only imports bar_window pulls in at module
top so it imports under pytest, then drive it against a fake window that records .move() calls
and reports back a `.position` reflecting them (mirroring the real far-sentinel self-calibration:
moving to the FAR corner reveals the movable extent)."""
import sys
import types


def _stub(name, **attrs):
    parts = name.split(".")
    for i in range(1, len(parts) + 1):
        p = ".".join(parts[:i])
        if p not in sys.modules:
            sys.modules[p] = types.ModuleType(p)
    mod = sys.modules[name]
    for key, value in attrs.items():
        if not hasattr(mod, key):
            setattr(mod, key, value)
    return mod


class _Permissive(object):
    def __init__(self, *a, **k):
        pass


class _PositionAnchor(object):
    LEFT = "LEFT"
    TOP = "TOP"


_stub("frameworks.wulf", ViewSettings=_Permissive, ViewFlags=object(), WindowFlags=object(),
      WindowLayer=object(), PositionAnchor=_PositionAnchor)
_stub("gui.impl.pub", ViewImpl=_Permissive, WindowImpl=_Permissive)
_stub("openwg_gameface", ModDynAccessor=lambda *a, **k: (lambda: -1))

import pytest                                             # noqa: E402

from moe_calculator.bridge import bar_window              # noqa: E402
from moe_calculator.bridge import mod_settings            # noqa: E402


class _FakeWindow(object):
    """Records every .move(); reports .position back as whatever the last move requested, so a
    far-sentinel clamp (bar_window._FAR, _FAR) reads back the fixture's chosen movable extent --
    exactly the self-calibration trick _extent uses on the real Wulf window.

    `.size` mirrors Wulf's own read-only Window.size (= self.proxy.windowSize, the sibling of the
    windowPosition that .position reads, in the SAME logical units). It is what lets _space recover
    the FULL logical space as extent + surface -- the term that makes the drag's gain exactly 1
    instead of (space - surface) / space. Default 256x256 = the engine's size-timeout fallback
    surface, so extent 1664x824 pairs with a real 1920x1080 logical space."""

    def __init__(self, max_x, max_y, size=(256, 256)):
        self._max = (max_x, max_y)
        self.size = size
        self.position = (0, 0)
        self.moves = []

    def move(self, x, y, xAnchor=None, yAnchor=None):
        self.moves.append((x, y))
        if (x, y) == (bar_window._FAR, bar_window._FAR):
            self.position = self._max
        else:
            self.position = (x, y)


@pytest.fixture(autouse=True)
def _reset_settings():
    mod_settings._seed(dict(mod_settings.DEFAULTS))
    yield
    mod_settings._seed(dict(mod_settings.DEFAULTS))


def _host(max_x, max_y, y_frac=0.865, x_off=0, y_off=36):
    host = bar_window.BarHost("test.item", lambda: object(), y_frac, x_off, y_off, y_off,
                              "[test]")
    window = _FakeWindow(max_x, max_y)
    host._active = (window, object())
    return host, window


# --- THE Ctrl+DRAG GESTURE, driven entirely from Python --------------------------------------
# `drag(phase)` is the whole reverse channel now: adapter/battle_input samples Ctrl + the left
# button and reports "start" / "move" / "end", and each MOVE re-places the window ABSOLUTELY from
# the live cursor (domain.positioning.cursor_top_left). No delta arrives from anywhere, so there is
# no gain factor and no dependence on the surface's mouse hit rect -- the three structural failures
# of the superseded JS delta protocol.


def _at(monkeypatch, cursor, screen=(1920, 1080)):
    """Point bar_window's two engine reads at a fixed cursor / resolution."""
    monkeypatch.setattr(bar_window, "_cursor_position", lambda: cursor)
    monkeypatch.setattr(bar_window, "_screen_resolution", lambda: screen)


def _centred(max_x, max_y, y_frac=0.865, x_off=0, y_off=36):
    from moe_calculator.domain.positioning import anchor_centred
    return anchor_centred(max_x, max_y, y_frac, x_off, y_off)


def test_drag_start_moves_nothing_and_records_the_grab_offset(monkeypatch):
    # THE DIFFERENCE BETWEEN "picks up where you grabbed it" AND "snaps": the gesture's first event
    # must leave the bar exactly where it was, however far the cursor is from its top-left corner.
    host, window = _host(1664, 824)
    _at(monkeypatch, (0.0, 0.0))
    host.drag("start")
    assert window.moves == [(bar_window._FAR, bar_window._FAR)], "start must not re-place the bar"
    assert host._grab is not None


def test_a_move_at_the_grab_point_keeps_the_bar_put(monkeypatch):
    # The grab offset, proven end to end: mapping the SAME cursor again must reproduce the
    # placement the bar was grabbed at, NOT put its corner under the cursor.
    host, window = _host(1664, 824)
    _at(monkeypatch, (0.0, 0.0))
    host.drag("start")
    host.drag("move")
    assert window.moves[-1] == _centred(1664, 824)


def test_a_move_repositions_absolutely_and_preserves_the_grab_offset(monkeypatch):
    host, window = _host(1664, 824)
    _at(monkeypatch, (0.0, 0.0))                       # grabbed dead centre
    host.drag("start")
    base = _centred(1664, 824)
    _at(monkeypatch, (0.5, 0.0))                       # cursor moved a quarter-screen right
    host.drag("move")
    # A quarter of the LOGICAL SPACE (1664 extent + 256 surface = 1920) to the right of where it was
    # grabbed -- offset intact on both axes, and the gain is 1, not 1664/1920.
    assert window.moves[-1] == (base[0] + 1920 // 4, base[1])


def test_a_move_with_no_start_records_the_grab_instead_of_snapping(monkeypatch):
    # Defensive, and reachable: battle_input's MOUSE wrap can latch the gesture on the first
    # movement (with the cursor raised, the button press may never reach the key dispatcher), so a
    # "move" is allowed to be the first event this host sees. It must behave like a start.
    host, window = _host(1664, 824)
    _at(monkeypatch, (0.9, -0.9))
    host.drag("move")
    assert window.moves == [(bar_window._FAR, bar_window._FAR)]
    host.drag("move")
    assert window.moves[-1] == _centred(1664, 824)


def test_a_live_move_updates_the_position_without_persisting(monkeypatch):
    host, _window = _host(1664, 824)
    calls = []
    monkeypatch.setattr(mod_settings, "set_bar_position",
                        lambda x, y, persist: calls.append((x, y, persist)))
    _at(monkeypatch, (0.0, 0.0))
    host.drag("start")
    _at(monkeypatch, (0.4, 0.2))
    host.drag("move")
    assert len(calls) == 1 and calls[0][2] is False


def test_the_gesture_end_persists_the_last_applied_position(monkeypatch):
    host, window = _host(1664, 824)
    calls = []
    monkeypatch.setattr(mod_settings, "set_bar_position",
                        lambda x, y, persist: calls.append((x, y, persist)))
    _at(monkeypatch, (0.0, 0.0))
    host.drag("start")
    _at(monkeypatch, (0.4, 0.2))
    host.drag("move")
    host.drag("end")
    assert calls[-1] == (window.moves[-1][0], window.moves[-1][1], True)


def test_a_gesture_that_never_moved_persists_nothing(monkeypatch):
    # A stray Ctrl+click must not convert the AUTO anchor (0/0) into an explicit pin at whatever
    # the bar is currently placed at -- that would be a silent opt-out of every future anchor
    # change (a Large-mode retune, a new default) and is invisible on the day it happens.
    host, _window = _host(1664, 824)
    calls = []
    monkeypatch.setattr(mod_settings, "set_bar_position",
                        lambda x, y, persist: calls.append((x, y, persist)))
    _at(monkeypatch, (0.0, 0.0))
    host.drag("start")
    host.drag("end")
    assert calls == []


def test_the_gesture_state_does_not_leak_into_the_next_one(monkeypatch):
    # The end must drop BOTH the grab offset and the "we moved" record, or the next gesture would
    # pick up the previous one's offset (and a click-only gesture would persist its position).
    host, _window = _host(1664, 824)
    _at(monkeypatch, (0.0, 0.0))
    host.drag("start")
    host.drag("move")
    host.drag("end")
    assert host._grab is None and host._drag_pos is None


def test_drag_clamps_to_one_at_the_top_left_edge(monkeypatch):
    # CLAMPED TO [1, max], not [0, max]: 0 is anchor_pinned's "auto" sentinel, so a drag that
    # reaches the screen edge must never store 0 (which would silently un-pin the bar).
    # Grabbed at the bottom-right corner so the carried offset is NEGATIVE on both axes -- i.e. the
    # clamp is what stops the result going to 0, not the mapping's own floor.
    host, window = _host(1664, 824)
    _at(monkeypatch, (1.0, -1.0))
    host.drag("start")
    _at(monkeypatch, (-1.0, 1.0))
    host.drag("move")
    assert window.moves[-1] == (1, 1)


def test_drag_clamps_to_max_at_the_bottom_right_edge(monkeypatch):
    host, window = _host(1664, 824)
    _at(monkeypatch, (0.0, 0.0))
    host.drag("start")
    _at(monkeypatch, (1.0, -1.0))
    host.drag("move")
    assert window.moves[-1] == (1664, 824)


def test_drag_handles_a_pixel_space_cursor_too(monkeypatch):
    # The units of GUI.mcursor().position are not settled in the decompiled client, so the mapping
    # is unit-agnostic -- and this is the OTHER convention, end to end through the host.
    host, window = _host(1664, 824)
    _at(monkeypatch, (960, 540))
    host.drag("start")
    _at(monkeypatch, (1440, 540))                      # a quarter-screen right, in device px
    host.drag("move")
    base = _centred(1664, 824)
    assert window.moves[-1] == (base[0] + 1920 // 4, base[1])


def test_the_drag_gain_is_exactly_one_through_the_host(monkeypatch):
    # THE ACCEPTANCE CRITERION, at the seam that supplies the missing term: N logical units of cursor
    # travel == N logical units of window travel. The window's OWN size (Wulf's read-only
    # Window.size, = self.proxy.windowSize) is what turns _extent's `space - surface` back into
    # `space`; without it the mapping scales by (space - surface) / space -- 1664/1920 = 0.867 here,
    # ~0.74 with the real Large surface -- and the bar visibly trails the cursor.
    host, window = _host(1664, 824)
    _at(monkeypatch, (800, 400))
    host.drag("start")
    host.drag("move")
    first = window.moves[-1]
    _at(monkeypatch, (1300, 200))                      # +500 logical px on x, -200 on y
    host.drag("move")
    assert (window.moves[-1][0] - first[0], window.moves[-1][1] - first[1]) == (500, -200)


def test_the_drag_falls_back_to_the_extent_when_the_surface_size_is_unreadable(monkeypatch):
    # FAIL SOFT, not a raise: Wulf itself hands back (0.0, 0.0) for a window with no proxy (which
    # cannot be moved either), so a bad size read degrades to the old extent-scaled gain rather than
    # freezing the gesture. Nothing must escape into the engine's input path.
    host, window = _host(1664, 824)
    window.size = None                                 # unpacking this raises inside _space
    assert host._space(window) == (1664, 824)
    _at(monkeypatch, (0.0, 0.0))
    host.drag("start")
    host.drag("move")
    assert window.moves[-1] == _centred(1664, 824)


def test_the_reporting_events_own_cursor_position_is_preferred(monkeypatch):
    # gui.g_mouseEventHandlers hands the drag `event.cursorPosition` -- the position the engine
    # itself measured -- which makes GUI.mcursor() a FALLBACK. Proven by pointing the fallback
    # somewhere else entirely: the passed cursor is what places the bar.
    host, window = _host(1664, 824)
    _at(monkeypatch, (-1.0, 1.0))                      # the fallback read says "top-left corner"
    host.drag("start", (0.0, 0.0))
    host.drag("move", (0.0, 0.0))
    assert window.moves[-1] == _centred(1664, 824)     # ...but the event's centre cursor won


def test_drag_is_a_noop_when_no_window_is_open(monkeypatch):
    host = bar_window.BarHost("test.item", lambda: object(), 0.865, 0, 36, 36, "[test]")
    _at(monkeypatch, (0.0, 0.0))
    assert host._active is None
    host.drag("start")
    host.drag("move")
    host.drag("end")


def test_drag_leaves_the_bar_alone_when_the_cursor_cannot_be_read(monkeypatch):
    # FAIL SOFT: an unreadable cursor (or resolution) must leave the window exactly where it is,
    # never move it to a guessed position and never raise into the engine's input path.
    host, window = _host(1664, 824)
    _at(monkeypatch, None)
    host.drag("start")
    host.drag("move")
    assert [m for m in window.moves if m != (bar_window._FAR, bar_window._FAR)] == []
    assert host._grab is None


def test_drag_never_raises_on_a_broken_engine_read(monkeypatch):
    host, _window = _host(1664, 824)

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(bar_window, "_cursor_position", _boom)
    monkeypatch.setattr(bar_window, "_screen_resolution", _boom)
    host.drag("start")
    host.drag("move")
    host.drag("end")


def _far_measurements(window):
    """How many times the window was teleported to the far sentinel (= extent measurements)."""
    return [m for m in window.moves if m == (bar_window._FAR, bar_window._FAR)]


def test_a_drag_measures_the_movable_extent_only_once(monkeypatch):
    # THE JUMPING BUG: _extent teleports the window to (1<<20, 1<<20) to read the engine's clamp.
    # That is a one-shot calibration -- doing it per movement event costs a second native move()
    # per pointer event and made the bar visibly jump around the cursor. The extent is a function
    # of the surface size and the screen, neither of which changes mid-drag, so N events = 1 measure.
    host, window = _host(1664, 824)
    _at(monkeypatch, (0.0, 0.0))
    host.drag("start")
    for i in range(8):
        _at(monkeypatch, (0.1 * i, 0.0))
        host.drag("move")
    host.drag("end")
    far = _far_measurements(window)
    assert len(far) == 1, "far-sentinel measured %d times in an 8-move drag" % len(far)


def test_a_size_change_re_measures_the_movable_extent(monkeypatch):
    # The one way the memoization can regress: a Default<->Large flip resizes the surface, so the
    # movable extent SHRINKS. _place is what onSizeChanged runs, and it must invalidate -- a stale
    # extent would clamp the bar to the old, too-large bounds.
    host, window = _host(1664, 824)
    _at(monkeypatch, (-1.0, 1.0))                         # grab at the top-left...
    host.drag("start")
    _at(monkeypatch, (1.0, -1.0))                         # ...drag hard into the bottom-right
    host.drag("move")
    assert window.moves[-1] == (1664, 824)

    window._max = (1600, 760)                             # Large surface -> smaller extent
    host._place(window)
    _at(monkeypatch, (-1.0, 1.0))
    host.drag("start")
    _at(monkeypatch, (1.0, -1.0))
    host.drag("move")
    assert window.moves[-1] == (1600, 760)                # clamped to the NEW extent, not the old
    assert len(_far_measurements(window)) == 2            # re-measured, and only once


def test_the_engine_reads_fail_soft_to_none():
    # The two reads themselves: with no GUI module importable (pytest, game closed) each must hand
    # back None rather than raise, which is what makes the whole gesture a no-op off-client.
    assert bar_window._cursor_position() is None
    assert bar_window._screen_resolution() is None
