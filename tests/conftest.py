import os
import sys
import types

# Make the in-game package importable in tests without the game engine.
_CLIENT = os.path.join(os.path.dirname(__file__), "..", "src", "res", "scripts", "client")
sys.path.insert(0, os.path.abspath(_CLIENT))


def _stub_module(name, **attrs):
    """Install a bare stub module into sys.modules (once) so an adapter that imports a game
    symbol AT MODULE TOP can be imported under pytest. These only satisfy the import; every
    test drives real behavior by monkeypatching the adapter's own functions, never these.
    Mirrors the fake-game-symbol technique in test_i18n.py, hoisted here so the adapter
    modules import regardless of test collection order."""
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    for key, value in attrs.items():
        if not hasattr(mod, key):
            setattr(mod, key, value)
    return mod


# engine_adapter: `from CurrentVehicle import g_currentVehicle`
_stub_module("CurrentVehicle", g_currentVehicle=object())
# battle_adapter: `import BigWorld` (callback/player are only touched via monkeypatched paths)
_stub_module("BigWorld", callback=lambda *a, **k: None, player=lambda: None)


class _DamageLog(object):
    """The four "Summarized damage" DAMAGE_LOG keys battle_adapter/battle_bridge read/route on."""
    TOTAL_DAMAGE = "damageLog/totalDamage"
    BLOCKED_DAMAGE = "damageLog/blockedDamage"
    ASSIST_DAMAGE = "damageLog/assistDamage"
    ASSIST_STUN = "damageLog/assistStun"


class _Game(object):
    """The settingsCore key battle_adapter.read_minimap_size_index / battle_bridge route on."""
    MINIMAP_SIZE = "minimapSize"


# battle_adapter.read_minimap_size_index / battle_bridge._on_settings_changed both do
# `from account_helpers.settings_core.settings_constants import DAMAGE_LOG, GAME` lazily, inside a
# try/except -- so under pytest (module absent) that import silently fails and each function falls
# back to its own "can't tell, be safe" default, which would make every DAMAGE_LOG/MINIMAP_SIZE
# ROUTING test vacuously exercise only the except branch. Stub the module so those tests can drive
# the REAL branch instead; the fallback path itself is covered separately, deliberately, by forcing
# the underlying read to raise (see test_battle_adapter.py / test_bar_window.py).
_stub_module("account_helpers.settings_core.settings_constants", DAMAGE_LOG=_DamageLog, GAME=_Game)
