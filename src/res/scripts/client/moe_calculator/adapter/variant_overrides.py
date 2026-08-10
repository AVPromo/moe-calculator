"""Per-vehicle override of the in-battle progress-bar mode (variant).

Engine-free: all disk access goes through moe_wgapi (its `helpers` import is lazy),
so this module imports and unit-tests with the game closed. The store is one JSON
file, a dict {str(int_cd): variant_int}, variant in {0, 1}.
"""
import os

OVERRIDES_FILE = "progress_variant_overrides.json"
_VALID = (0, 1)


def _path():
    from moe_calculator.adapter.moe_wgapi import data_dir
    return os.path.join(data_dir(), OVERRIDES_FILE)


def load():
    """The override map as {int(int_cd): variant_int}. A missing, corrupt or non-dict
    file reads as EMPTY; junk keys/values are dropped, never raised."""
    blob = None
    try:
        from moe_calculator.adapter.moe_wgapi import read_json
        blob = read_json(_path())
    except Exception:
        pass
    if not isinstance(blob, dict):
        return {}
    out = {}
    for k, v in blob.items():
        if isinstance(v, bool):
            continue
        try:
            key = int(k)
            val = int(v)
        except (TypeError, ValueError):
            continue
        if val in _VALID:
            out[key] = val
    return out


def save(overrides):
    from moe_calculator.adapter.moe_wgapi import write_json
    blob = dict((str(int(k)), int(v)) for k, v in overrides.items())
    write_json(_path(), blob)


def effective(int_cd, default_variant):
    """The stored override for this vehicle, or `default_variant` when none."""
    if int_cd is None:
        return default_variant
    return load().get(int(int_cd), default_variant)


def toggle(int_cd, default_variant):
    """Flip this vehicle's effective variant, persist, and return the new value.
    When the new value equals `default_variant`, DROP the entry (space rule)."""
    overrides = load()
    current = overrides.get(int(int_cd), default_variant)
    new = 1 - current
    if new == default_variant:
        overrides.pop(int(int_cd), None)
    else:
        overrides[int(int_cd)] = new
    save(overrides)
    return new
