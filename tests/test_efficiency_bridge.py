# -*- coding: utf-8 -*-
"""Engine-free tests for the DAMAGE EFFICIENCY bar's bridge-level invariants.

Two families, neither reachable from the domain tests:

1. `push_efficiency`'s MARSHALLING: it is EfficiencyVM's only producer, and it WRITES no module
   state -- the delta latch that used to live here (`_eff_last_damage` / `_eff_delta`, plus
   `damageDelta` on the VM) now lives in MoEEfficiency.js off successive `damage` pushes, so
   those behaviours belong to tools/dev/check_efficiency_js.js and NOT to pytest. What the push
   does still READ is the one module global `_battle_epoch` -- the per-battle counter that hands
   that JS latch its battle boundary, which it cannot infer. Its bump lives in `_on_mount_refresh`,
   so the epoch tests at the bottom of this file drive the MOUNT, not just the push.

2. "EXACTLY ONE CENTRE-SCREEN BAR AT A TIME". The two bars are radio ALTERNATIVES under the
   single `progress_bar_enabled` master, and `_window_gates()` is the one place that decides it,
   shared by the battle mount and the live settings apply so the rule cannot drift between them.
   It reads `mod_settings.progress_bar_variant()` DIRECTLY (the `_progress_variant()` wrapper is
   gone), so these tests monkeypatch that getter on mod_settings itself.

Technique mirrors tests/test_battle_bridge_prediction.py: install bare stub modules for the game
imports battle_bridge pulls in transitively, then drive the functions directly. The real
EfficiencyVM needs Wulf, so the push writes into a recording fake -- whose accepted setter names
are cross-checked against the real EfficiencyVM class, so a typo'd setter cannot pass silently.
The window WIRING (does the engine actually open it) needs the live client and is out of scope.
"""
import io
import os
import sys
import tokenize
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


_stub("frameworks.wulf", ViewModel=_Permissive, Array=_Permissive, ViewSettings=_Permissive,
      ViewFlags=object(), WindowFlags=object(), WindowLayer=object(), PositionAnchor=object())
_stub("gui.impl.pub", ViewImpl=_Permissive, WindowImpl=_Permissive)
_stub("openwg_gameface", ModDynAccessor=lambda *a, **k: (lambda: -1),
      gf_mod_inject=lambda *a, **k: None)

import pytest                                              # noqa: E402

from moe_calculator.bridge import battle_bridge            # noqa: E402
from moe_calculator.bridge import mod_settings             # noqa: E402
from moe_calculator.bridge.view_models import EfficiencyVM  # noqa: E402
from moe_calculator.domain import battle_types as bt       # noqa: E402

THR = {65: 2450, 85: 3050, 95: 3620, 100: 4400}   # keyed by PERCENTILE, not by mark count

# The property names EfficiencyVM actually declares, derived from its OWN setters -- so this
# fake can never accept a set*() the shipped model does not have (nor miss one it does).
_VM_PROPS = frozenset(name[3].lower() + name[4:]
                      for name in dir(EfficiencyVM) if name.startswith("set"))


class _FakeVM(object):
    """Records what a push writes. Stands in for the Wulf-backed EfficiencyVM."""

    def __init__(self):
        self.props = {}

    def transaction(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        if not name.startswith("set"):
            raise AttributeError(name)
        key = name[3].lower() + name[4:]
        assert key in _VM_PROPS, "EfficiencyVM has no set%s" % name[3:]
        return lambda v: self.props.__setitem__(key, v)


def _snap(**over):
    kwargs = dict(vehicle_int_cd=1073, thresholds=dict(THR),
                  has_vehicle=True, in_battle=True, is_spectating=False, baseline_known=True,
                  pre_avg_damage=1850, pre_percentile=73.67)
    kwargs.update(over)
    return bt.BattleSnapshot(**kwargs)


def _model(combined_damage=0, **over):
    kwargs = dict(combined_damage=combined_damage, proj_avg_damage=1867, cur_percent=74.3,
                  pct_delta=0.63, has_data=True, has_baseline=True,
                  counted_assist=0, assist_kind="")
    kwargs.update(over)
    return bt.BattleMoEModel(**kwargs)


@pytest.fixture(autouse=True)
def _fresh_battle(monkeypatch):
    """A fresh battle with the Damage Efficiency bar selected: no scoreboard up, and the settings
    reading through the real gate functions (monkeypatched per test)."""
    monkeypatch.setattr(battle_bridge, "_open_overlays", set())
    monkeypatch.setattr(mod_settings, "progress_bar_enabled", lambda: True)
    monkeypatch.setattr(mod_settings, "progress_bar_variant",
                        lambda: mod_settings.PROGRESS_VARIANT_EFFICIENCY)
    monkeypatch.setattr(mod_settings, "battle_enabled", lambda: False)


@pytest.fixture
def epoch(monkeypatch):
    """Park `_battle_epoch` at a KNOWN value so every assertion below can name a LITERAL.

    Deliberately not a comparison against `battle_bridge._battle_epoch`: that reads the same
    global the push reads, so it moves with the source and would pass whatever the epoch did
    (including never bumping). monkeypatch restores the real counter, keeping these tests
    order-independent from the rest of the suite."""
    def _set(value=0):
        monkeypatch.setattr(battle_bridge, "_battle_epoch", value)
    _set()
    return _set


def _push(damage, **snap_over):
    vm = _FakeVM()
    battle_bridge.push_efficiency(vm, _snap(**snap_over), _model(combined_damage=damage))
    return vm.props


# --- the marshalling ----------------------------------------------------------

def test_push_writes_exactly_the_view_models_twelve_properties():
    # The bridge is this model's only producer: a prop added on one side without the other would
    # silently leave the JS reading a default forever. TWELVE: the ten that survived `damageDelta`'s
    # removal (which RENUMBERED every property after it), then `battleEpoch` and now `barSize`, both
    # APPENDED after altHeld for exactly that reason -- an append renumbers nothing.
    assert set(_push(2000)) == _VM_PROPS
    assert len(_VM_PROPS) == 12


def test_the_push_keeps_no_state_between_calls(epoch):
    # THE flip side of retiring the latch. push_efficiency is NOT a pure function of its three
    # arguments -- it reads ONE module global, `_battle_epoch` (the JS latch's battle-boundary
    # signal, bumped only by _on_mount_refresh). That read is the whole allowance: the push writes
    # NO module state, so at a fixed epoch a repeated identical push must be byte-identical, a
    # DECREASE must not be remembered anywhere, and the push must not bump the epoch itself.
    # (The "keep showing the last increment" behaviour it replaced is now MoEEfficiency.js's
    # `peak`/`delta` -- see tools/dev/check_efficiency_js.js.)
    epoch(4)
    assert _push(800) == _push(800)
    assert _push(600) == _push(600)
    assert _push(800) == _push(800)              # the interleaved 600 left nothing behind
    assert battle_bridge._battle_epoch == 4      # ...and four pushes did not advance the epoch
    assert not [n for n in dir(battle_bridge) if n.startswith("_eff_")], \
        "push_efficiency grew module state again -- the delta latch lives in the JS now"


# --- the hasData false path ---------------------------------------------------

def test_an_unusable_axis_pushes_zero_for_every_stop():
    # snap.thresholds is all-or-nothing upstream, so this is the ONLY data gate. The four Real
    # stops must go out as 0.0 rather than stale or garbage values.
    props = _push(2000, thresholds={})
    assert props["hasData"] is False
    assert (props["r65"], props["r85"], props["r95"], props["r100"]) == (0.0, 0.0, 0.0, 0.0)
    assert props["barX"] == 0.0 and props["band"] == 0
    assert props["damage"] == 2000       # the damage itself is still real


def test_a_usable_axis_pushes_the_four_requirements_and_the_band():
    props = _push(3050)
    assert props["hasData"] is True
    assert (props["r65"], props["r85"], props["r95"], props["r100"]) == (2450.0, 3050.0,
                                                                        3620.0, 4400.0)
    assert props["barX"] == 50.0 and props["band"] == 2


def test_a_partial_threshold_table_is_an_unusable_axis():
    props = _push(2000, thresholds={65: 2450, 85: 3050, 95: 3620})
    assert props["hasData"] is False


def test_a_mark_count_keyed_table_is_an_unusable_axis():
    # A stale v3 cache row ({1,2,3,100}) must read as NO axis, never as D65 mis-labelled as the
    # 1st-percentile requirement. moe_wgapi's _STORE_VERSION bump is the primary guard; this is
    # the domain-side backstop.
    assert _push(2000, thresholds={1: 2450, 2: 3050, 3: 3620, 100: 4400})["hasData"] is False


# --- push_efficiency's own visibility gate ------------------------------------

def test_the_bar_is_hidden_while_the_other_variant_is_selected(monkeypatch):
    monkeypatch.setattr(mod_settings, "progress_bar_variant",
                        lambda: mod_settings.PROGRESS_VARIANT_MOVING_AVERAGE)
    assert _push(2000)["visible"] is False


def test_the_bar_is_hidden_while_the_master_is_off(monkeypatch):
    monkeypatch.setattr(mod_settings, "progress_bar_enabled", lambda: False)
    assert _push(2000)["visible"] is False


def test_the_bar_is_visible_with_the_master_on_and_the_variant_selected():
    assert _push(2000)["visible"] is True


def test_the_bar_needs_no_career_baseline():
    # Unlike push_progress: the axis is the tank's requirement table and the plotted value is
    # this battle's own damage, so a replay / relogin (BUG B) costs this bar nothing.
    assert _push(2000, baseline_known=False)["visible"] is True


def test_a_missing_view_model_is_a_noop(monkeypatch):
    # A CLEAN early return, not a swallowed crash: without the `rvm is None` guard the very next
    # line (rvm.transaction()) would raise into the blanket except, which LOGS and then also
    # returns None -- so "it didn't raise" alone is vacuous here. Count the exception log instead,
    # and prove no work was started either.
    logged = []
    monkeypatch.setattr(battle_bridge, "LOG_CURRENT_EXCEPTION", lambda *a: logged.append(1))
    monkeypatch.setattr(battle_bridge, "efficiency_stops", lambda *a: pytest.fail(
        "push_efficiency did work on a missing view model"))
    assert battle_bridge.push_efficiency(None, _snap(), _model(combined_damage=500)) is None
    assert logged == []


def test_push_never_raises_into_the_refresh():
    vm = _FakeVM()
    battle_bridge.push_efficiency(vm, object(), None)   # no snapshot / model attributes at all
    assert vm.props == {}


# --- BarHost reads the SIZE setting LATE ---------------------------------------
# Not specific to this bar -- BarHost is shared with the Moving Average one -- but this is the
# module that already carries the stub modules bar_window needs (it imports battle_bridge, which
# pulls efficiency_view -> bar_window), so the test lives beside them rather than in a second
# stub tree.

class _FakeBarWindow(object):
    """Just enough window for BarHost._place: it clamps to the far corner, reads `position` back
    as the movable extent, then moves for real. The extent is FIXED here, so the only thing that
    can move the second `move` is the y offset _place chose."""

    def __init__(self, extent):
        self._extent = extent
        self.moves = []

    def move(self, x, y, xAnchor=None, yAnchor=None):
        self.moves.append((x, y))

    @property
    def position(self):
        return self._extent


def test_bar_host_reads_the_size_setting_inside_place_not_at_import(monkeypatch):
    # THE REGRESSION TEST FOR THE BUG THAT SHIPPED IN THE FIRST DRAFT. BarHost's arguments are bound
    # where progress_view / efficiency_view construct it -- i.e. AT MODULE IMPORT, once per client
    # process. Choosing the y offset there would freeze it at whatever the size setting happened to
    # be at first load, so a user flipping "Size" (or the JS's post-deadline LARGE surface
    # round-tripping back as onSizeChanged -> _place) would keep placing against the other size's
    # compensation, forever. So the read has to happen INSIDE _place: flip the getter between two
    # _place calls on the SAME host and the placement must follow.
    from moe_calculator.bridge import bar_window

    # PositionAnchor is stubbed as a bare object() at the top of this file (it only has to satisfy
    # the import), and _place's blanket except would SWALLOW the resulting AttributeError into a
    # silent no-op -- so give it the two members and assert both moves actually landed.
    anchor = types.SimpleNamespace(LEFT=0, TOP=1)
    monkeypatch.setattr(bar_window, "PositionAnchor", anchor)
    monkeypatch.setattr(bar_window, "LOG_CURRENT_EXCEPTION",
                        lambda *a: pytest.fail("_place swallowed an exception"))

    small, large = 36, 53                       # two DISTINCT offsets; the values are irrelevant
    host = bar_window.BarHost("ItemId", object, 0.865, 0, small, large, "[test]")
    window = _FakeBarWindow((970, 906))

    monkeypatch.setattr(mod_settings, "progress_bar_size",
                        lambda: mod_settings.PROGRESS_SIZE_DEFAULT)
    host._place(window)
    monkeypatch.setattr(mod_settings, "progress_bar_size",
                        lambda: mod_settings.PROGRESS_SIZE_LARGE)
    host._place(window)

    assert len(window.moves) == 4, "each _place is a far-corner clamp plus the real move"
    default_y, large_y = window.moves[1][1], window.moves[3][1]
    assert large_y - default_y == large - small, (
        "the size flag was not re-read: the same host placed at y=%d then y=%d, a delta of %d "
        "instead of %d" % (default_y, large_y, large_y - default_y, large - small))
    # ...and X is untouched by the size, which is what lets `max_x // 2` centre either surface.
    assert window.moves[1][0] == window.moves[3][0]


# --- exactly one centre-screen bar at a time ----------------------------------

def _gate(module):
    return dict((mod, enabled) for enabled, mod in battle_bridge._window_gates())[module]


@pytest.mark.parametrize("bar_on", [True, False])
@pytest.mark.parametrize("variant", [0, 1, 2, -1, 99])
def test_never_more_than_one_centre_screen_bar_is_gated_on(monkeypatch, bar_on, variant):
    monkeypatch.setattr(mod_settings, "progress_bar_enabled", lambda: bar_on)
    monkeypatch.setattr(mod_settings, "progress_bar_variant", lambda: variant)
    on = [mod for enabled, mod in battle_bridge._window_gates()
          if mod in (battle_bridge.progress_view, battle_bridge.efficiency_view) and enabled]
    assert len(on) <= 1
    # The MASTER dominates: off means NEITHER bar, at every variant (folded in from a separate
    # master-off test this parametrisation already covered, variants -1/2/99 included).
    if not bar_on:
        assert on == []
    # Fail-CLOSED on an index mod_settings.clamp_variant would never emit: each bar tests for
    # its OWN variant, so an unknown one lights up NEITHER rather than falling through to the
    # last `else`. That must hold in _window_gates itself, not merely downstream of the clamp.
    if variant not in (mod_settings.PROGRESS_VARIANT_MOVING_AVERAGE,
                       mod_settings.PROGRESS_VARIANT_EFFICIENCY):
        assert on == []


def test_each_variant_gates_its_own_bar_on(monkeypatch):
    monkeypatch.setattr(mod_settings, "progress_bar_variant",
                        lambda: mod_settings.PROGRESS_VARIANT_MOVING_AVERAGE)
    assert _gate(battle_bridge.progress_view) and not _gate(battle_bridge.efficiency_view)
    monkeypatch.setattr(mod_settings, "progress_bar_variant",
                        lambda: mod_settings.PROGRESS_VARIANT_EFFICIENCY)
    assert _gate(battle_bridge.efficiency_view) and not _gate(battle_bridge.progress_view)


def test_the_gates_name_all_three_windows_in_open_order():
    # refresh()/apply_settings/_on_mount_refresh all iterate this, and _on_teardown mirrors it by
    # hand: a fourth window added here without the teardown line would leak across battles.
    assert [mod for _enabled, mod in battle_bridge._window_gates()] == \
        [battle_bridge.battle_view, battle_bridge.progress_view, battle_bridge.efficiency_view]


def test_the_corner_overlay_has_its_own_master(monkeypatch):
    # The two bars' master must not reach the corner overlay, and vice versa.
    monkeypatch.setattr(mod_settings, "battle_enabled", lambda: True)
    monkeypatch.setattr(mod_settings, "progress_bar_enabled", lambda: False)
    assert _gate(battle_bridge.battle_view)


# --- apply_settings: a live variant flip swaps the two bars in one pass -------

class _FakeWindow(object):
    """One of the three window modules: an open/close singleton with a call log."""

    def __init__(self, is_open=False):
        self._view = object() if is_open else None
        self.log = []

    def open_window(self):
        self.log.append("open")
        self._view = object()

    def close_window(self):
        self.log.append("close")
        self._view = None

    def active_view(self):
        return self._view


@pytest.fixture
def windows(monkeypatch):
    """The three window modules replaced by fakes, mid-battle, with the engine calls stubbed.
    Starts with the Moving Average bar up -- the state a live radio flip has to leave behind."""
    fakes = {"battle": _FakeWindow(), "progress": _FakeWindow(is_open=True),
             "efficiency": _FakeWindow()}
    monkeypatch.setattr(battle_bridge, "battle_view", fakes["battle"])
    monkeypatch.setattr(battle_bridge, "progress_view", fakes["progress"])
    monkeypatch.setattr(battle_bridge, "efficiency_view", fakes["efficiency"])
    monkeypatch.setattr(battle_bridge, "_in_battle", True)
    monkeypatch.setattr(battle_bridge, "install_all_listeners", lambda: None)
    monkeypatch.setattr(battle_bridge.moe_wgapi, "start", lambda: None)
    monkeypatch.setattr(battle_bridge, "refresh", lambda: False)
    monkeypatch.setattr(mod_settings, "progress_bar_variant",
                        lambda: mod_settings.PROGRESS_VARIANT_MOVING_AVERAGE)
    return fakes


def test_a_live_variant_flip_closes_one_bar_and_opens_the_other(monkeypatch, windows):
    monkeypatch.setattr(mod_settings, "progress_bar_variant",
                        lambda: mod_settings.PROGRESS_VARIANT_EFFICIENCY)
    battle_bridge.apply_settings()
    assert windows["progress"].log == ["close"] and windows["progress"].active_view() is None
    assert windows["efficiency"].log == ["open"]
    assert windows["efficiency"].active_view() is not None


def test_a_live_variant_flip_back_swaps_them_again(monkeypatch, windows):
    monkeypatch.setattr(mod_settings, "progress_bar_variant",
                        lambda: mod_settings.PROGRESS_VARIANT_EFFICIENCY)
    battle_bridge.apply_settings()
    monkeypatch.setattr(mod_settings, "progress_bar_variant",
                        lambda: mod_settings.PROGRESS_VARIANT_MOVING_AVERAGE)
    battle_bridge.apply_settings()
    assert windows["progress"].active_view() is not None
    assert windows["efficiency"].active_view() is None


def test_apply_settings_never_leaves_both_bars_open(monkeypatch, windows):
    # The invariant itself, across every reachable settings state -- including the corner
    # overlay's own master, which must not influence either bar.
    for overlay in (False, True):
        for bar_on in (False, True):
            for variant in (mod_settings.PROGRESS_VARIANT_MOVING_AVERAGE,
                            mod_settings.PROGRESS_VARIANT_EFFICIENCY):
                monkeypatch.setattr(mod_settings, "battle_enabled", lambda v=overlay: v)
                monkeypatch.setattr(mod_settings, "progress_bar_enabled", lambda v=bar_on: v)
                monkeypatch.setattr(mod_settings, "progress_bar_variant", lambda v=variant: v)
                battle_bridge.apply_settings()
                up = [k for k in ("progress", "efficiency") if windows[k].active_view()]
                assert len(up) <= 1, (overlay, bar_on, variant, up)
                assert bool(up) == bar_on
                assert bool(windows["battle"].active_view()) == overlay


def test_turning_the_master_off_live_closes_the_open_bar(monkeypatch, windows):
    monkeypatch.setattr(mod_settings, "progress_bar_enabled", lambda: False)
    battle_bridge.apply_settings()
    assert windows["progress"].active_view() is None
    assert windows["efficiency"].log == []          # never opened, never needlessly closed


def test_nothing_opens_outside_a_battle(monkeypatch, windows):
    # The gate can go on in the garage; the window may only appear once a battle is up.
    monkeypatch.setattr(battle_bridge, "_in_battle", False)
    monkeypatch.setattr(mod_settings, "progress_bar_variant",
                        lambda: mod_settings.PROGRESS_VARIANT_EFFICIENCY)
    battle_bridge.apply_settings()
    assert windows["efficiency"].active_view() is None
    assert windows["progress"].active_view() is None    # the deselected one still closes


# --- battleEpoch: the JS delta latch's battle-boundary signal -----------------
# The bar's damage-delta latch lives in MoEEfficiency.js and has to drop the previous battle's
# increment. It used to INFER the boundary from a total arriving below its high-water mark -- wrong
# whenever the new battle's first tick already read HIGHER, so an Alt peek early in the next battle
# rendered the last battle's number. Python now pushes the boundary explicitly. This is the ONLY
# coverage of that Python half; the JS half is tools/dev/check_efficiency_js.js.

def test_the_push_carries_the_epoch_and_two_pushes_in_one_battle_share_it(epoch):
    # Within a battle the counter never moves, so consecutive ticks must carry the SAME value --
    # the JS resets on `!==`, so a per-push epoch would wipe the increment on every tick.
    assert _push(0)["battleEpoch"] == 0
    epoch(7)
    assert _push(500)["battleEpoch"] == 7
    assert _push(900)["battleEpoch"] == 7


def test_a_battle_mount_bumps_the_epoch_exactly_once(epoch, windows):
    battle_bridge._on_mount_refresh()
    assert _push(0)["battleEpoch"] == 1          # once per mount, not twice, not zero times
    battle_bridge._on_mount_refresh()
    assert _push(0)["battleEpoch"] == 2


def test_the_battles_first_push_already_carries_the_new_epoch(epoch, windows, monkeypatch):
    # THE ordering that matters. The bump has to land BEFORE _on_mount_refresh's own refresh(), or
    # the battle's OPENING push still carries the previous battle's epoch and the JS latch keeps
    # showing last battle's increment until the second efficiency tick -- exactly the bug the
    # explicit signal replaced. "It changed eventually" cannot see that, so drive the real push
    # from inside refresh() and read what the very first one of each battle actually emitted.
    seen = []
    monkeypatch.setattr(battle_bridge, "refresh",
                        lambda: seen.append(_push(0)["battleEpoch"]))
    battle_bridge._on_mount_refresh()
    battle_bridge._on_mount_refresh()
    assert seen == [1, 2]


def test_the_epoch_strictly_increases_across_successive_mounts(epoch, windows):
    # A literal expected sequence, not "it differs from the last one": the JS only needs
    # consecutive battles to DIFFER, but a counter that wrapped, reset, or repeated a value would
    # silently re-suppress a reset, and only pinning the sequence catches that.
    assert [_mount_then_epoch() for _ in range(5)] == [1, 2, 3, 4, 5]


def _mount_then_epoch():
    battle_bridge._on_mount_refresh()
    return _push(0)["battleEpoch"]


def test_the_epoch_is_a_counter_and_never_an_arena_identity():
    # Wulf's _setNumber int-casts (view_models.EfficiencyVM), so pushing a 64-bit arenaUniqueID
    # would arrive silently mangled -- and nothing here needs identity, only that consecutive
    # battles differ. Pin it at the source so a future "let's just use arenaUniqueID" edit trips
    # here rather than in-game.
    #
    # COMMENTS ARE STRIPPED FIRST and that strip is load-bearing: battle_bridge's own prose names
    # the trap, so a raw whole-file grep is satisfied by the warning ABOUT the bug and asserts
    # nothing (this repo has been bitten by exactly that shape).
    code = _battle_bridge_code()
    offenders = [n for n in ("arenaUniqueID", "arena_unique_id", "arenaUniqueId") if n in code]
    assert offenders == [], (
        "battle_bridge reads an arena id (%s) -- battleEpoch must stay a small monotonic counter; "
        "_setNumber int-casts and would mangle a 64-bit arena id" % ", ".join(offenders))


def _battle_bridge_code():
    """battle_bridge.py's source with every COMMENT token removed (docstrings kept -- they are
    real code objects and would ship an arena id just as loudly)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "res", "scripts",
                        "client", "moe_calculator", "bridge", "battle_bridge.py")
    with io.open(path, encoding="utf-8") as fh:
        src = fh.read()
    return " ".join(tok.string for tok in tokenize.generate_tokens(io.StringIO(src).readline)
                    if tok.type != tokenize.COMMENT)
