# -*- coding: utf-8 -*-
"""Engine-free tests for battle_bridge._on_settings_changed -- the ONE settingsCore listener that
routes TWO unrelated keys: the "Summarized damage" DAMAGE_LOG group (re-places the overlay) and
GAME.MINIMAP_SIZE (re-places the two bars). Both keys ride the SAME onSettingsChanged(diff) event,
so the routing itself -- not just each individual re-place -- is what a mutation could silently
break: an over-broad filter would re-place everything on every settings change, and an
under-broad one would miss a genuine minimap resize or damage-log toggle.

conftest.py stubs account_helpers.settings_core.settings_constants (DAMAGE_LOG / GAME) so this
drives the REAL routing branches, not the function's own except-branch fail-open fallback. Mirrors
test_battle_bridge_prediction.py's fake-game-symbol technique for importing battle_bridge under
pytest.
"""
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


_stub("frameworks.wulf", ViewModel=_Permissive, Array=_Permissive, ViewSettings=_Permissive,
      ViewFlags=object(), WindowFlags=object(), WindowLayer=object(), PositionAnchor=object())
_stub("gui.impl.pub", ViewImpl=_Permissive, WindowImpl=_Permissive)
_stub("openwg_gameface", ModDynAccessor=lambda *a, **k: (lambda: -1),
      gf_mod_inject=lambda *a, **k: None)

from moe_calculator.bridge import battle_bridge          # noqa: E402
from account_helpers.settings_core.settings_constants import DAMAGE_LOG, GAME  # noqa: E402


def _calls(monkeypatch):
    """Spy on all three windows' apply_position(), returning the set of labels that fired."""
    fired = set()
    monkeypatch.setattr(battle_bridge.battle_view, "apply_position",
                        lambda: fired.add("overlay"))
    monkeypatch.setattr(battle_bridge.progress_view, "apply_position",
                        lambda: fired.add("progress"))
    monkeypatch.setattr(battle_bridge.efficiency_view, "apply_position",
                        lambda: fired.add("efficiency"))
    return fired


def test_a_damage_log_diff_reroutes_only_the_overlay(monkeypatch):
    fired = _calls(monkeypatch)
    battle_bridge._on_settings_changed({DAMAGE_LOG.TOTAL_DAMAGE: True})
    assert fired == {"overlay"}


def test_each_of_the_four_damage_log_keys_reroutes_the_overlay(monkeypatch):
    for key in (DAMAGE_LOG.TOTAL_DAMAGE, DAMAGE_LOG.BLOCKED_DAMAGE, DAMAGE_LOG.ASSIST_DAMAGE,
                DAMAGE_LOG.ASSIST_STUN):
        fired = _calls(monkeypatch)
        battle_bridge._on_settings_changed({key: False})
        assert fired == {"overlay"}, "key %s did not reroute the overlay" % key


def test_a_minimap_size_diff_reroutes_only_the_two_bars(monkeypatch):
    fired = _calls(monkeypatch)
    battle_bridge._on_settings_changed({GAME.MINIMAP_SIZE: 3})
    assert fired == {"progress", "efficiency"}


def test_a_damage_log_only_diff_does_not_reroute_the_bars(monkeypatch):
    # THE NEGATIVE CASE: catches an over-broad filter that would re-place the bars on every
    # unrelated settings change (the routing lives on ONE shared event; a too-loose key check would
    # never be seen by anything except a diff-content assertion like this one).
    fired = _calls(monkeypatch)
    battle_bridge._on_settings_changed({DAMAGE_LOG.TOTAL_DAMAGE: True})
    assert "progress" not in fired and "efficiency" not in fired


def test_a_minimap_size_only_diff_does_not_reroute_the_overlay(monkeypatch):
    # The mirror negative case: a minimap resize must not needlessly re-place the corner overlay.
    fired = _calls(monkeypatch)
    battle_bridge._on_settings_changed({GAME.MINIMAP_SIZE: 3})
    assert "overlay" not in fired


def test_an_unrelated_key_reroutes_nothing(monkeypatch):
    fired = _calls(monkeypatch)
    battle_bridge._on_settings_changed({"someOtherModsSetting": True})
    assert fired == set()


def test_both_keys_present_reroute_everything(monkeypatch):
    fired = _calls(monkeypatch)
    battle_bridge._on_settings_changed({DAMAGE_LOG.TOTAL_DAMAGE: True, GAME.MINIMAP_SIZE: 2})
    assert fired == {"overlay", "progress", "efficiency"}


def test_a_none_diff_fails_open_and_reroutes_everything(monkeypatch):
    # diff=None is the "can't tell what changed" case (e.g. a full settings reload) -- fail OPEN
    # (re-place everything) rather than miss a real change; a spurious re-place is harmless.
    fired = _calls(monkeypatch)
    battle_bridge._on_settings_changed(None)
    assert fired == {"overlay", "progress", "efficiency"}


def test_a_broken_constants_import_fails_open_and_reroutes_everything(monkeypatch):
    # If account_helpers.settings_core.settings_constants itself becomes unreadable (or its
    # attributes change shape), the whole routed branch raises into the outer except, which
    # re-places every window rather than silently going dark.
    fired = _calls(monkeypatch)
    monkeypatch.delitem(sys.modules, "account_helpers.settings_core.settings_constants")
    battle_bridge._on_settings_changed({"anything": True})
    assert fired == {"overlay", "progress", "efficiency"}
