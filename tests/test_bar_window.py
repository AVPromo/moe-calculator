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
    """An open, ALREADY-PLACED host: _place is what _onReady runs, so a live window always has a
    real .position by the time a drag can reach it. Placing here matters because the drag's
    ownership gate tests the cursor against that .position -- an unplaced fake window sitting at
    (0, 0) would decline every gesture.

    The placement's own moves are then cleared so each test still reads its own from index 0. The
    extent memo is left WARM, as it is live: _place always repopulates it, which is what keeps the
    far-sentinel measurement out of the drag path (and why drag() reads .position BEFORE _extent --
    a cold read would teleport the window to the sentinel and the ownership rect would be there)."""
    host = bar_window.BarHost("test.item", lambda: object(), y_frac, x_off, y_off, y_off,
                              "[test]")
    window = _FakeWindow(max_x, max_y)
    host._active = (window, object())
    host._place(window)
    del window.moves[:]
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


# A cursor ON THE BAR, which every gesture now has to start from: the drag is claimed per host only
# if it began inside that host's own window rect (the fix for "Ctrl+drag anywhere dragged whichever
# bar was open, including while dragging another mod's UI"). In clip space (0.0, -0.4) maps to
# (960, 756) of a 1920x1080 logical space -- inside the centred 256x256 bar at (832, 748). The screen
# CENTRE, which these tests used to grab from, sits above the bar and is now correctly refused.
_GRAB = (0.0, -0.4)
_GRAB_PX = (960, 756)               # ...the same point in the OTHER (device-px) cursor convention


def test_drag_start_moves_nothing_and_records_the_grab_offset(monkeypatch):
    # THE DIFFERENCE BETWEEN "picks up where you grabbed it" AND "snaps": the gesture's first event
    # must leave the bar exactly where it was, however far the cursor is from its top-left corner.
    host, window = _host(1664, 824)
    _at(monkeypatch, _GRAB)
    host.drag("start")
    assert window.moves == [], "start must not re-place the bar"
    assert host._grab is not None


def test_a_move_at_the_grab_point_keeps_the_bar_put(monkeypatch):
    # The grab offset, proven end to end: mapping the SAME cursor again must reproduce the
    # placement the bar was grabbed at, NOT put its corner under the cursor.
    host, window = _host(1664, 824)
    _at(monkeypatch, _GRAB)
    host.drag("start")
    host.drag("move")
    assert window.moves[-1] == _centred(1664, 824)


def test_a_move_repositions_absolutely_and_preserves_the_grab_offset(monkeypatch):
    host, window = _host(1664, 824)
    _at(monkeypatch, _GRAB)                            # grabbed on the bar
    host.drag("start")
    base = _centred(1664, 824)
    _at(monkeypatch, (0.5, -0.4))                      # cursor moved a quarter-screen right
    host.drag("move")
    # A quarter of the LOGICAL SPACE (1664 extent + 256 surface = 1920) to the right of where it was
    # grabbed -- offset intact on both axes, and the gain is 1, not 1664/1920.
    assert window.moves[-1] == (base[0] + 1920 // 4, base[1])


def test_a_move_with_no_start_records_the_grab_instead_of_snapping(monkeypatch):
    # Defensive, and reachable: battle_input's MOUSE wrap can latch the gesture on the first
    # movement (with the cursor raised, the button press may never reach the key dispatcher), so a
    # "move" is allowed to be the first event this host sees. It must behave like a start.
    host, window = _host(1664, 824)
    _at(monkeypatch, _GRAB)
    host.drag("move")
    assert window.moves == []                          # ...i.e. it recorded the grab and moved nothing
    host.drag("move")
    assert window.moves[-1] == _centred(1664, 824)


def test_a_live_move_updates_the_position_without_persisting(monkeypatch):
    host, _window = _host(1664, 824)
    calls = []
    monkeypatch.setattr(mod_settings, "set_bar_position",
                        lambda x, y, persist: calls.append((x, y, persist)))
    _at(monkeypatch, _GRAB)
    host.drag("start")
    _at(monkeypatch, (0.4, -0.4))
    host.drag("move")
    assert len(calls) == 1 and calls[0][2] is False


def test_the_gesture_end_persists_the_last_applied_position(monkeypatch):
    host, window = _host(1664, 824)
    calls = []
    monkeypatch.setattr(mod_settings, "set_bar_position",
                        lambda x, y, persist: calls.append((x, y, persist)))
    _at(monkeypatch, _GRAB)
    host.drag("start")
    _at(monkeypatch, (0.4, -0.4))
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
    _at(monkeypatch, _GRAB)
    host.drag("start")
    host.drag("end")
    assert calls == []


def test_the_gesture_state_does_not_leak_into_the_next_one(monkeypatch):
    # The end must drop BOTH the grab offset and the "we moved" record, or the next gesture would
    # pick up the previous one's offset (and a click-only gesture would persist its position).
    host, _window = _host(1664, 824)
    _at(monkeypatch, _GRAB)
    host.drag("start")
    host.drag("move")
    host.drag("end")
    assert host._grab is None and host._drag_pos is None


def test_drag_past_the_top_left_edge_goes_negative_and_is_not_clamped(monkeypatch):
    # THERE IS NO SAFEZONE: a bar dragged off the left/top edge keeps going into negative logical
    # coordinates. The old [1, max] clamp stopped the corner at the screen edge, which made the last
    # part of the drag silently ignore the cursor.
    host, window = _host(1664, 824)
    _at(monkeypatch, _GRAB)
    host.drag("start")
    _at(monkeypatch, (-1.0, 1.0))                      # cursor to the screen's top-left corner
    host.drag("move")
    # The grab offset (the bar's corner relative to the cursor that grabbed it) is carried, so the
    # corner lands that far PAST the origin.
    base = _centred(1664, 824)
    assert window.moves[-1] == (base[0] - _GRAB_PX[0], base[1] - _GRAB_PX[1])
    assert window.moves[-1][0] < 0 and window.moves[-1][1] < 0


def test_drag_past_the_bottom_right_edge_is_not_clamped_to_the_extent(monkeypatch):
    host, window = _host(1664, 824)
    _at(monkeypatch, _GRAB)
    host.drag("start")
    _at(monkeypatch, (1.0, -1.0))                      # cursor to the screen's bottom-right corner
    host.drag("move")
    base = _centred(1664, 824)
    # Cursor travel from _GRAB_PX to (1920, 1080), gain 1, and NOTHING clamps it back to the movable
    # extent (1664x824) -- the bar is allowed to hang off the edge.
    assert window.moves[-1] == (base[0] + 1920 - _GRAB_PX[0], base[1] + 1080 - _GRAB_PX[1])
    assert window.moves[-1][0] > 1664 and window.moves[-1][1] > 824


def test_drag_handles_a_pixel_space_cursor_too(monkeypatch):
    # The units of GUI.mcursor().position are not settled in the decompiled client, so the mapping
    # is unit-agnostic -- and this is the OTHER convention, end to end through the host.
    host, window = _host(1664, 824)
    _at(monkeypatch, _GRAB_PX)
    host.drag("start")
    _at(monkeypatch, (_GRAB_PX[0] + 480, _GRAB_PX[1]))  # a quarter-screen right, in device px
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
    _at(monkeypatch, _GRAB_PX)
    host.drag("start")
    host.drag("move")
    first = window.moves[-1]
    _at(monkeypatch, (_GRAB_PX[0] + 500, _GRAB_PX[1] - 200))   # +500 logical px on x, -200 on y
    host.drag("move")
    assert (window.moves[-1][0] - first[0], window.moves[-1][1] - first[1]) == (500, -200)


def test_an_unreadable_surface_size_fails_soft_and_declines_the_gesture(monkeypatch):
    # FAIL SOFT, not a raise: Wulf itself hands back (0.0, 0.0) for a window with no proxy (which
    # cannot be moved either), so _space degrades to the extent alone...
    host, window = _host(1664, 824)
    window.size = None                                 # unpacking this raises inside _space
    assert host._space(window) == (1664, 824)
    # ...and with no surface size the OWNERSHIP RECT collapses to a point, so this host simply does
    # not claim the gesture: nothing moves, and nothing escapes into the engine's input path. A
    # proxy-less window could not have been moved anyway.
    _at(monkeypatch, _GRAB)
    host.drag("start")
    host.drag("move")
    assert [m for m in window.moves if m != (bar_window._FAR, bar_window._FAR)] == []


def test_the_reporting_events_own_cursor_position_is_preferred(monkeypatch):
    # gui.g_mouseEventHandlers hands the drag `event.cursorPosition` -- the position the engine
    # itself measured -- which makes GUI.mcursor() a FALLBACK. Proven by pointing the fallback
    # somewhere else entirely: the passed cursor is what places the bar.
    host, window = _host(1664, 824)
    _at(monkeypatch, (-1.0, 1.0))                      # the fallback read says "top-left corner"
    host.drag("start", _GRAB)
    host.drag("move", _GRAB)
    assert window.moves[-1] == _centred(1664, 824)     # ...but the event's on-bar cursor won


def test_a_gesture_that_began_off_the_bar_is_not_claimed(monkeypatch):
    # THE OWNERSHIP GATE. battle_bridge hands every drag event to BOTH bars unconditionally and
    # battle_input samples Ctrl+LMB globally, so before this a Ctrl+drag ANYWHERE grabbed whichever
    # bar was open -- dragging another mod's UI dragged ours with it.
    host, window = _host(1664, 824)
    _at(monkeypatch, (0.0, 0.0))                          # the screen centre: ABOVE the bar's box
    host.drag("start")
    host.drag("move")
    assert host._grab is None
    assert [m for m in window.moves if m != (bar_window._FAR, bar_window._FAR)] == []


def test_the_ownership_rect_is_read_against_the_real_position_not_a_cold_far_sentinel(monkeypatch):
    # LOAD-BEARING READ ORDER: window.position must be read BEFORE _extent() is called, because a
    # COLD extent cache measures by teleporting the window to the far sentinel (bar_window._FAR) --
    # reading .position AFTER that would test the ownership rect against the sentinel corner instead
    # of wherever the bar actually is. Reachable in practice: open_window() publishes `_active` BEFORE
    # window.load() resolves, so a drag can arrive before _onReady's first _place() has ever warmed
    # the memo -- i.e. exactly the cold-cache case, with the window still sitting at its untouched
    # native position.
    host = bar_window.BarHost("test.item", lambda: object(), 0.865, 0, 36, 36, "[test]")
    window = _FakeWindow(1664, 824)             # UNPLACED: position stays (0, 0), cache cold
    host._active = (window, object())
    _at(monkeypatch, (-1.0, 1.0))               # clip-space top-left -> logical (0, 0), on the window
    host.drag("start")
    assert host._grab is not None and host._declined is False, (
        "declined a gesture that started on the window's real (unplaced) position")


def test_a_declined_gesture_is_never_reconsidered_mid_flight(monkeypatch):
    # ...and the refusal LATCHES for the whole gesture: a foreign drag that happens to sweep the
    # cursor across our bar must not hijack it halfway (which would snap the bar to the cursor).
    host, window = _host(1664, 824)
    _at(monkeypatch, (0.0, 0.0))
    host.drag("start")
    _at(monkeypatch, _GRAB)                               # ...the cursor now passes over the bar
    host.drag("move")
    host.drag("move")
    assert host._grab is None
    assert [m for m in window.moves if m != (bar_window._FAR, bar_window._FAR)] == []
    # The latch is per gesture, not permanent: the next drag that DOES start on the bar works.
    host.drag("end")
    _at(monkeypatch, _GRAB)
    host.drag("start")
    host.drag("move")
    assert window.moves[-1] == _centred(1664, 824)


def test_a_claimed_gesture_keeps_the_bar_once_the_cursor_leaves_the_box(monkeypatch):
    # The mirror image, and why only the START tests the rect: a bar is 256px wide and the cursor
    # leaves it within the first few px of any real drag. Re-testing per move would drop the bar.
    host, window = _host(1664, 824)
    _at(monkeypatch, _GRAB)
    host.drag("start")
    _at(monkeypatch, (100, 100))                          # far outside the bar's own box
    host.drag("move")
    base = _centred(1664, 824)
    assert window.moves[-1] == (base[0] + 100 - _GRAB_PX[0], base[1] + 100 - _GRAB_PX[1])


def test_drag_is_a_noop_when_no_window_is_open(monkeypatch):
    host = bar_window.BarHost("test.item", lambda: object(), 0.865, 0, 36, 36, "[test]")
    _at(monkeypatch, _GRAB)
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
    _at(monkeypatch, _GRAB)
    host.drag("start")
    for i in range(8):
        _at(monkeypatch, (0.1 * i, 0.0))
        host.drag("move")
    host.drag("end")
    # ZERO here, because _place already warmed the memo when the window opened (see _host); an
    # un-memoized _extent would measure once per drag() call -- 9 times in this gesture.
    far = _far_measurements(window)
    assert len(far) == 0, "far-sentinel measured %d times in an 8-move drag" % len(far)


def test_a_size_change_re_measures_the_movable_extent(monkeypatch):
    # The one way the memoization can regress: a Default<->Large flip resizes the surface, so the
    # movable extent SHRINKS. _place is what onSizeChanged runs, and it must invalidate the memo.
    # Nothing CLAMPS to the extent any more (no safezone), so what a stale extent would corrupt now is
    # the AUTO placement and the logical space the cursor maps onto (extent + surface).
    host, window = _host(1664, 824)
    _at(monkeypatch, _GRAB)
    host.drag("start")
    host.drag("move")
    assert window.moves[-1] == _centred(1664, 824)

    window._max = (1600, 760)                             # Large surface -> smaller extent
    # That live move PINNED the position, and a pin is now honoured verbatim rather than clamped into
    # the extent -- so reset to auto (0/0), which is the placement the extent still decides.
    mod_settings.set_bar_position(0, 0, persist=False)
    host._place(window)
    _at(monkeypatch, _GRAB)
    host.drag("start")
    host.drag("move")
    assert window.moves[-1] == _centred(1600, 760)        # re-centred in the NEW extent, not the old
    assert len(_far_measurements(window)) == 1            # re-measured by _place, and only once


def test_the_engine_reads_fail_soft_to_none():
    # The two reads themselves: with no GUI module importable (pytest, game closed) each must hand
    # back None rather than raise, which is what makes the whole gesture a no-op off-client.
    assert bar_window._cursor_position() is None
    assert bar_window._screen_resolution() is None
