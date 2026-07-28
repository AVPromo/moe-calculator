# -*- coding: utf-8 -*-
"""Per-battle prediction<->outcome recorder (diagnostics collection only).

The in-battle live percent over-predicts, and tuning the damage->percent mapping needs ground
truth rather than anecdotes: what the overlay PREDICTED at the end of a battle, paired with what
WG's own dossier reported for that tank afterwards. This module records those pairs. It feeds
NOTHING back into the widget or the math -- it only appends to two files under the client's
writable prefs dir (see moe_wgapi.data_dir):

    mods_data/14th_ua_moe/battle_pending.json   {int_cd: prediction}   transient
    mods_data/14th_ua_moe/battle_samples.jsonl  one complete sample per line, append-only

Flow:
  * PREDICTED -- bridge/battle_bridge remembers the last non-spectating push of the battle and
    flushes it here via stash() on avatar teardown (once per battle).
  * ACTUAL    -- adapter/engine_adapter calls resolve() from its dossier read, which is the
    ground truth and already runs on the post-battle items-cache onSyncCompleted path.

The pairing needs no battle id: a prediction waits in the pending file until a dossier read for
that same intCD reports values DIFFERENT from the pre-battle ones it was predicted against.

ALWAYS ON, deliberately not DEBUG-gated -- the data has to come from normal play. Fail-soft
everywhere: every disk touch and every field read is guarded, and a missing/corrupt pending file
reads as empty rather than raising, so a recorder failure can never break a battle or the widget.

Engine-free apart from reusing moe_wgapi's prefs-dir + atomic-write helpers (whose engine import
is lazy), so this module imports and unit-tests with the game closed.

# ponytail: two real ceilings, both accepted for a diagnostics recorder --
#   (a) battle_samples.jsonl grows unbounded (a few hundred bytes per battle); add rotation
#       (or just delete the file) if the size ever matters.
#   (b) pairing is keyed by int_cd + the "post values changed" heuristic, so a dossier resync
#       that does not move movingAvgDamage/damageRating leaves a pending row unresolved. That is
#       harmless -- it resolves on the next read that does move -- and post_battles (dossier
#       battlesCount) is recorded so a stale pairing is detectable after the fact.
"""
import os
import json
import time
from collections import OrderedDict

from moe_calculator._compat import LOG_CURRENT_EXCEPTION, LOG_DEBUG

ROW_VERSION = 1
PENDING_FILE = "battle_pending.json"
SAMPLES_FILE = "battle_samples.jsonl"

# The prediction fields the caller supplies, in row order (see the module docstring for the
# full schema). Read with .get, so a caller that omits one logs a null instead of raising.
_PRED_KEYS = ("int_cd", "ewma_k", "thresholds", "pre_percentile", "pre_avg_damage",
              "baseline_known", "damage", "track_assist", "spot_assist", "stun", "team_damage",
              "combined_damage", "counted_assist", "assist_kind", "proj_avg_damage",
              "predicted_percent", "pct_delta", "has_data", "has_baseline")

# Optional trailing columns, appended AFTER post_battles so the pinned order above is untouched.
# They exist to answer the post-mortem-credit question from the data instead of a live-client
# session: the prediction of record is the last NON-spectating push, i.e. our state at death,
# while WG keeps crediting the player afterwards (burn damage from our fires, stun still ticking
# from a landed shell) and the dossier ground truth includes that credit. These carry the
# battle's very LAST push, spectating included -- equal to the prediction means post-mortem
# credit is a non-issue, divergent means the death path under-predicts by exactly that much.
# Each is omitted when the bridge couldn't supply it (no trailing push, or a different tank).
_FINAL_KEYS = ("final_combined_damage", "final_percent")

_version = None  # cached mod version string ("" = unresolvable -> the key is omitted)


def stash(prediction):
    """Record (overwriting) the pending prediction for one battle, keyed by its int_cd, so the
    next post-battle dossier read for that tank can resolve it. The file holds a DICT of pending
    records rather than one, so playing several tanks before reaching a resolvable hangar state
    still pairs each up. Returns True iff it was stored. Guarded.

    The mod version is stamped HERE, not when the row is resolved: pending records outlive the
    client session, so a mod update between sessions would otherwise credit the resolving build
    for a prediction the previous build made -- misattributing exactly the samples that straddle
    a mapping change."""
    try:
        cd = int(prediction.get("int_cd") or 0)
        if not cd:
            return False
        version = _mod_version()
        if version:
            prediction = dict(prediction, mod_version=version)
        pending = _load_pending()
        pending[str(cd)] = prediction
        _write_pending(pending)
        LOG_DEBUG("[moe-sample] stashed prediction for %d (pending=%d)" % (cd, len(pending)))
        return True
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return False


def resolve(int_cd, post_percentile, post_avg_damage, post_battles=None):
    """Ground truth arrived for a tank. If a pending prediction exists for it AND the dossier has
    MOVED off the pre-battle values it was predicted against, append the completed sample line and
    drop the pending entry. Returns True iff a sample was written.

    The "has moved" test is what pairs a prediction with its battle: the same dossier read fires
    repeatedly (every items-cache resync, every garage re-entry), and only the one carrying the
    post-battle numbers may be credited. Unchanged values simply leave the prediction pending.

    The append happens BEFORE the pending entry is dropped, so a failed write leaves the record
    pending for the next read instead of losing the sample. Guarded."""
    try:
        cd = int(int_cd or 0)
        if not cd:
            return False
        pending = _load_pending()
        rec = pending.get(str(cd))
        if not rec:
            return False
        post_p = float(post_percentile or 0.0)
        post_a = int(post_avg_damage or 0)
        if (post_p == float(rec.get("pre_percentile") or 0.0)
                and post_a == int(rec.get("pre_avg_damage") or 0)):
            return False  # dossier hasn't caught up yet -> keep waiting
        _append_row(_row(rec, post_p, post_a, post_battles))
        del pending[str(cd)]
        _write_pending(pending)
        LOG_DEBUG("[moe-sample] resolved %d: predicted=%.2f actual=%.2f"
                  % (cd, float(rec.get("predicted_percent") or 0.0), post_p))
        return True
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return False


# --- row assembly ------------------------------------------------------------

def _row(rec, post_percentile, post_avg_damage, post_battles):
    """The completed sample as an ordered dict (the JSONL column order). Ordered so the file is
    readable/diffable by hand -- a plain dict would serialize in hash order."""
    row = OrderedDict()
    row["v"] = ROW_VERSION
    version = rec.get("mod_version")  # stamped by stash(), i.e. the build that PREDICTED
    if version:
        row["mod_version"] = version
    row["ts"] = int(time.time())
    for key in _PRED_KEYS:
        row[key] = rec.get(key)
    row["post_percentile"] = post_percentile
    row["post_avg_damage"] = post_avg_damage
    row["residual"] = post_percentile - float(rec.get("predicted_percent") or 0.0)
    if post_battles is not None:
        row["post_battles"] = post_battles
    for key in _FINAL_KEYS:
        if rec.get(key) is not None:
            row[key] = rec[key]
    return row


def _mod_version():
    """The mod's own version constant, or "" when it can't be resolved (the entry-point module
    is not importable outside the client) -- the record then OMITS the key rather than inventing
    a literal that would drift. Resolved once; in-client the module is already in sys.modules, so
    the import is a lookup, not a re-execution."""
    global _version
    if _version is None:
        try:
            from gui.mods.mod_moe_calculator import MOD_VERSION
            _version = str(MOD_VERSION)
        except Exception:
            _version = ""
    return _version


# --- files -------------------------------------------------------------------

def _path(name):
    """<prefs>/mods_data/14th_ua_moe/<name>. moe_wgapi owns the prefs-dir lookup (its `helpers`
    import is lazy), so this module keeps no engine dependency of its own."""
    from moe_calculator.adapter.moe_wgapi import data_dir
    return os.path.join(data_dir(), name)


def _load_pending():
    """The pending records as {str(int_cd): prediction}. A missing, corrupt or non-dict file
    reads as EMPTY -- never a raise, and never a partial record."""
    blob = None
    try:
        from moe_calculator.adapter.moe_wgapi import read_json
        blob = read_json(_path(PENDING_FILE))
    except Exception:
        LOG_CURRENT_EXCEPTION()
    if not isinstance(blob, dict):
        return {}
    return dict((k, v) for k, v in blob.items() if isinstance(v, dict))


def _write_pending(pending):
    """Persist the pending map atomically (shared moe_wgapi.write_json, itself guarded)."""
    from moe_calculator.adapter.moe_wgapi import write_json
    write_json(_path(PENDING_FILE), pending)


def _append_row(row):
    """Append one JSON line to the samples file, creating it (and its directory) on first write.
    Deliberately NOT guarded here -- resolve() must see a failed write so it keeps the record
    pending instead of dropping the sample."""
    path = _path(SAMPLES_FILE)
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "ab") as fh:
        fh.write((json.dumps(row) + "\n").encode("utf-8"))
