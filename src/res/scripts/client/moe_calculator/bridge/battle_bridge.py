# -*- coding: utf-8 -*-
"""Bridge: drive the in-battle MoE overlay -- open/close its window, arm the engine
listeners, and push the recomputed model into the window view's ViewModel.

The overlay is a standalone OpenWG-registered Gameface WINDOW opened over the battle HUD
(see bridge/battle_view.py for WHY a window and not a garage-style sub-view inject). This
module owns the lifecycle: on battle start (avatar ready) it opens the window and arms the
efficiency listener; on battle end (avatar becomes non-player) it destroys the window. A
burst of onTotalEfficiencyUpdated collapses to one deferred push.

    All symbols VERIFIED (decompile + live replay, 2.3.0.1): the PlayerEvents arena hooks
    and personalEfficiencyCtrl.onTotalEfficiencyUpdated. Re-arm every battle: the arena
    teardown rebuilds the controllers/event lists each match.
"""
import BigWorld

from moe_calculator._compat import LOG_CURRENT_EXCEPTION, LOG_DEBUG
from moe_calculator.adapter import battle_adapter
from moe_calculator.adapter import battle_input
from moe_calculator.adapter import moe_wgapi
from moe_calculator.adapter import sample_log
from moe_calculator.domain.battle_builder import (
    build_battle_model, battle_bar_visible, ewma_project_raw, mark_axis, marks_from_percentile)
from moe_calculator.domain.constants import EFFICIENCY_WIDE_THRESHOLD, EWMA_K
from moe_calculator.domain.positioning import efficiency_panel_wide
from moe_calculator.bridge import battle_view
from moe_calculator.bridge import mod_settings
from moe_calculator.bridge import progress_view

# Set while a coalesced refresh is queued, so a burst of onTotalEfficiencyUpdated fires
# collapses to a single deferred refresh().
_refresh_pending = False

# Whether we've registered our one-time listener on the async MoE-table loader (so the
# overlay re-pushes and reveals once the per-tank thresholds finish loading).
_data_listener_armed = False

# Whether we've promoted the played tank into the permanent fetch list this battle. Reset on
# each battle mount; set once we can read the player's OWN vehicle (see push). Recording here
# -- off the persistent PlayerEvents lifecycle, where the played vehicle is known -- is far more
# reliable than the garage-side onResultPosted, whose subscription is torn down with the hangar
# during the battle and re-armed only after the result has already posted.
_battle_recorded = False

# The battle's PREDICTION of record for the prediction<->outcome recorder: the (snapshot, model)
# of the last non-spectating push, i.e. the overlay's final state this battle. Flushed to
# adapter/sample_log once on teardown (and reset there), mirroring the once-per-battle
# _battle_recorded idiom above. Diagnostics only -- nothing reads it back into the model.
_last_prediction = None

# The battle's very LAST push with a readable vehicle, SPECTATING INCLUDED -- so the recorder can
# carry the post-death state alongside the prediction of record (see sample_log._FINAL_KEYS for
# why: WG keeps crediting the player after death and the dossier ground truth includes it).
# Diagnostics only; it never becomes the prediction of record.
_last_final_push = None

# The full-stats scoreboard views currently open, keyed by their g_eventBus eventType. While
# any is open the overlay hides (it would otherwise clutter the full-screen scoreboard). All
# four are dispatched on g_eventBus at EVENT_BUS_SCOPE.BATTLE with ctx['isDown'] (True open /
# False close) -- this mirrors WG's own damage_log_panel gating (see battle.shared.page).
# Deliberately EXCLUDED: Ctrl free-look (SHOW_CURSOR), F1 help and the ESC menu all keep the
# readout visible.
_open_overlays = set()

# Whether the g_eventBus scoreboard listeners are armed. Unlike the arena controllers (rebuilt
# every battle), g_eventBus is a persistent singleton whose BATTLE-scope listeners survive
# arena teardown -- so we arm ONCE and never re-add (a second add would only warn + no-op).
_overlay_listeners_armed = False

# Last-applied "efficiency panel is 5-digit wide" state (see domain.efficiency_panel_wide).
# The overlay opens at damage 0 (condition False), so the right-shift can only engage LATER,
# when a total crosses the threshold mid-battle. We re-place the window when this flips (not on
# every efficiency tick -- window.move is comparatively costly). None = not yet evaluated this
# battle; reset on each mount.
_last_wide = None


# True between avatar-ready and avatar-non-player, i.e. while we're in a battle. Tracked even
# when the overlay is disabled so a live enable (apply_settings) knows to open the window now.
_in_battle = False


# Whether Alt is currently held, as reported by the event-driven battle_input hook. TWO readers:
#  - the corner overlay's "Show on Alt Key" mode -- while the In-Battle Widget master is on AND
#    that mode is on, the overlay's visible flag follows this (decided in battle_bar_visible);
#  - the centre-screen progress bar, which gets it pushed as `altHeld` and treats it as an
#    ADDITIVE show trigger (pull the bar up and hold it), never a gate.
# Read this module global -- do NOT call battle_input.install_alt_key_listener again for a second
# consumer: its `_on_change` is a SINGLE callback slot, so a second install would silently
# replace the overlay's handler and kill its Alt peek.
_alt_held = False


# --- engine event subscriptions ---------------------------------------------
# Handlers are module-level (stable identity) so the membership-checked _arm is idempotent.

def _on_mount_refresh(*args, **kwargs):
    # Avatar ready -> we're in a battle: open the overlay window, (re)arm the efficiency
    # listener, kick the thresholds loader, and push the initial model. Reset the played-tank
    # record so this battle promotes its vehicle exactly once (see push).
    global _battle_recorded, _last_wide, _in_battle
    try:
        _in_battle = True
        _battle_recorded = False
        # Re-evaluate the 5-digit shift from scratch this battle (totals reset to 0).
        _last_wide = None
        # Clear any scoreboard flag left over from a prior battle / relogin / replay teardown,
        # so a stale key can never keep the fresh battle's overlay hidden.
        _open_overlays.clear()
        # The two windows are independently settings-gated. The In-Battle Widget master being
        # off means the corner overlay is never shown, so don't open ITS window this battle (the
        # "Show on Alt Key" child is inert while the master is off) -- but the centre-screen
        # progress bar has its own checkbox and may still want to open. A live enable of either
        # opens it mid-battle (see apply_settings); _in_battle stays True so that path fires.
        if not (mod_settings.battle_enabled() or mod_settings.progress_bar_enabled()):
            return
        if mod_settings.battle_enabled():
            battle_view.open_window()
        if mod_settings.progress_bar_enabled():
            progress_view.open_window()
        install_all_listeners()
        moe_wgapi.start()  # idempotent; the garage path may already have kicked it
        refresh()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_arena_period_changed(*args, **kwargs):
    # Arena period changed (PREBATTLE -> BATTLE ...) -> re-push so the overlay reveals/hides.
    try:
        refresh()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_efficiency_updated(*args, **kwargs):
    # personalEfficiencyCtrl.onTotalEfficiencyUpdated(totals): live cumulative stats changed.
    # Coalesce onto the next tick so a burst collapses to one push.
    try:
        _schedule_refresh()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_summary_feedback(*args, **kwargs):
    # feedback.onPlayerSummaryFeedbackReceived(event): the server pushed a fresh battle-events
    # summary -- the source of the track/spot assist split (counted-assistance row). Coalesce a
    # push so the row updates promptly. (push() re-reads the cached summary either way; this just
    # makes it timely rather than waiting for the next efficiency tick.)
    try:
        _schedule_refresh()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_observed_vehicle_changed(*args, **kwargs):
    # vehicleState.onVehicleControlling / onPostMortemSwitched: the observed vehicle changed
    # (died into postmortem, or cycled to another spectated ally). Re-push so the overlay
    # hides while spectating someone else and reveals again if control returns to us.
    # Efficiency events may not fire while spectating, so this is the signal we need.
    try:
        refresh()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_teardown(*args, **kwargs):
    # Avatar became non-player (battle exit) -> tear down BOTH windows; the next battle mount
    # re-opens whichever is enabled. The event lists are rebuilt by the arena teardown regardless.
    # The progress bar needs its OWN close here or its window leaks across battles.
    global _in_battle
    try:
        _in_battle = False
        _flush_prediction()
        battle_view.close_window()
        progress_view.close_window()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_scale_changed(*args, **kwargs):
    # Interface scale changed mid-battle (settingsCore.interfaceScale.onScaleChanged) -> the
    # logical GUI space resized, so re-place the overlay to keep it tracking WG's efficiency
    # panel (the fixed logical anchor is scale-invariant, but the window must be re-applied
    # because the movable extent changed). The bar's anchor is a FRACTION of that extent, so it
    # needs re-placing for the same reason.
    try:
        battle_view.apply_position()
        progress_view.apply_position()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_settings_changed(diff):
    # settingsCore.onSettingsChanged(diff): the "Summarized damage" DAMAGE_LOG group drives
    # our anchor (all four unticked -> summary block collapses -> events shift up -> raised
    # anchor). Re-place only when one of those four flags changed. Fail-open (re-place anyway
    # if the constants can't be resolved) -- a spurious re-place is harmless (idempotent).
    try:
        from account_helpers.settings_core.settings_constants import DAMAGE_LOG
        flags = (DAMAGE_LOG.TOTAL_DAMAGE, DAMAGE_LOG.BLOCKED_DAMAGE,
                 DAMAGE_LOG.ASSIST_DAMAGE, DAMAGE_LOG.ASSIST_STUN)
        if diff is None or any(f in diff for f in flags):
            battle_view.apply_position()
    except Exception:
        LOG_CURRENT_EXCEPTION()
        try:
            battle_view.apply_position()
        except Exception:
            LOG_CURRENT_EXCEPTION()


def _on_moe_data_ready():
    # The MoE-data source signalled ready (a WG-API fetch round completed on the main-thread poll).
    # Re-push so the overlay (hidden while hasData is false) reveals with numbers.
    try:
        LOG_DEBUG("[moe-battle] table ready -> refresh")
        refresh()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_scoreboard_toggled(event):
    # A full-stats scoreboard view (Tab / personal missions / reserves / event stats) opened
    # or closed -> track which are down and re-push so the overlay hides while any is open and
    # reveals when the last closes. Read fail-soft: a missing/odd ctx can only DROP the key
    # (reveal the overlay), never wedge it hidden.
    try:
        ctx = getattr(event, "ctx", None) or {}
        key = getattr(event, "eventType", None)
        if ctx.get("isDown"):
            _open_overlays.add(key)
        else:
            _open_overlays.discard(key)
        _schedule_refresh()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _set_alt_held(down):
    # battle_input's transition callback: Alt was pressed / released. Store it and re-push so
    # the overlay reveals/hides live under the "Battle Widget on Alt Key" peek mode. refresh()
    # is cheap and no-ops when no window is open (always-on off + peek off), so it's safe to
    # fire on every Alt transition regardless of which mode is active.
    global _alt_held
    try:
        _alt_held = bool(down)
        refresh()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _player_events_holder():
    from PlayerEvents import g_playerEvents
    return g_playerEvents


def _efficiency_holder():
    return battle_adapter._efficiency_ctrl()  # None until the controller exists -> skipped


def _feedback_holder():
    # sessionProvider.shared.feedback -- the BattleFeedbackAdaptor whose battle-events summary
    # carries the track/spot assist split. None until the arena spins it up -> _arm retries.
    return battle_adapter._feedback_ctrl()


def _vehicle_state_holder():
    # sessionProvider.shared.vehicleState -- the OBSERVED_VEHICLE_STATE controller. None until
    # the arena spins it up -> _arm skips and retries next mount.
    sp = battle_adapter._session_provider()
    return sp.shared.vehicleState if (sp and sp.shared) else None


def _interface_scale_holder():
    # settingsCore.interfaceScale -- exposes onScaleChanged (Event.Event). None if the core is
    # unavailable -> _arm skips. Unlike the arena controllers this persists across battles, so
    # re-arming is idempotent (the membership check keeps it a single subscription).
    sc = battle_adapter._settings_core()
    return sc.interfaceScale if sc is not None else None


def _settings_core_holder():
    # settingsCore itself -- exposes onSettingsChanged (fired with a {name: value} diff). Used
    # to re-place the overlay when the "Summarized damage" DAMAGE_LOG group toggles. Persists
    # across battles like interfaceScale, so re-arming is idempotent (membership-checked).
    return battle_adapter._settings_core()


# (label, holder-getter, event-attribute, handler)
_LISTENERS = (
    ("avatar ready", _player_events_holder, "onAvatarReady", _on_mount_refresh),
    ("avatar teardown", _player_events_holder, "onAvatarBecomeNonPlayer", _on_teardown),
    ("arena period", _player_events_holder, "onArenaPeriodChange", _on_arena_period_changed),
    ("efficiency", _efficiency_holder, "onTotalEfficiencyUpdated", _on_efficiency_updated),
    # Server battle-events summary -> the track/spot assist split (counted-assistance row).
    ("summary feedback", _feedback_holder, "onPlayerSummaryFeedbackReceived",
     _on_summary_feedback),
    # Observed-vehicle changes drive the spectate hide/reveal (postmortem free-look).
    ("observed vehicle", _vehicle_state_holder, "onVehicleControlling",
     _on_observed_vehicle_changed),
    ("postmortem", _vehicle_state_holder, "onPostMortemSwitched",
     _on_observed_vehicle_changed),
    # Interface-scale changes re-place the overlay so it keeps tracking WG's efficiency panel.
    ("interface scale", _interface_scale_holder, "onScaleChanged", _on_scale_changed),
    # "Summarized damage" DAMAGE_LOG group toggles re-place the overlay (raised vs default).
    ("settings", _settings_core_holder, "onSettingsChanged", _on_settings_changed),
)


def _arm(label, get_holder, attr, handler):
    """Subscribe `handler` to holder.<attr> iff not already present, storing the augmented
    Event back onto the attribute (WoT's += does not reliably mutate in place). Self-healing
    + idempotent; a not-yet-ready holder just skips (retried next mount)."""
    try:
        holder = get_holder()
        if holder is None:
            return
        event = getattr(holder, attr, None)
        if event is not None and handler not in event:
            event += handler
            setattr(holder, attr, event)
            LOG_DEBUG("[moe-battle] %s listener (re)armed" % label)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def install_all_listeners():
    """(Re)arm every battle listener + the one-time MoE-data ready hook. Safe to call on
    every battle mount -- the arena teardown drops the delegates and rebuilds the
    controllers, and this restores them."""
    global _data_listener_armed
    for entry in _LISTENERS:
        _arm(*entry)
    if not _data_listener_armed:
        try:
            moe_wgapi.add_ready_listener(_on_moe_data_ready)
            _data_listener_armed = True
        except Exception:
            LOG_CURRENT_EXCEPTION()
    _arm_overlay_listeners()
    # Event-driven Alt-key hook for the "Battle Widget on Alt Key" peek mode. Installed once
    # (idempotent + self-healing: AvatarInputHandler may not be importable until a battle
    # exists, so a failed attempt retries on the next mount).
    battle_input.install_alt_key_listener(_set_alt_held)


def _arm_overlay_listeners():
    """Subscribe the scoreboard hide/reveal handler to the full-stats g_eventBus events, ONCE.
    These sit on the persistent g_eventBus (not the per-battle arena controllers), so re-arming
    each mount is unnecessary and would only warn. Fail-soft: an unavailable event bus just
    leaves the overlay always-visible (its prior behaviour)."""
    global _overlay_listeners_armed
    if _overlay_listeners_armed:
        return
    try:
        from gui.shared import g_eventBus, EVENT_BUS_SCOPE
        from gui.shared.events import GameEvent
        events = (GameEvent.FULL_STATS, GameEvent.FULL_STATS_QUEST_PROGRESS,
                  GameEvent.FULL_STATS_PERSONAL_RESERVES, GameEvent.EVENT_STATS)
        for ev in events:
            g_eventBus.addListener(ev, _on_scoreboard_toggled, scope=EVENT_BUS_SCOPE.BATTLE)
        _overlay_listeners_armed = True
        LOG_DEBUG("[moe-battle] scoreboard hide listeners armed")
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _schedule_refresh():
    """Coalesce a refresh onto the next tick (main thread -> transaction is safe)."""
    global _refresh_pending
    if _refresh_pending:
        return
    _refresh_pending = True
    try:
        BigWorld.callback(0.0, _do_scheduled_refresh)
    except Exception:
        _refresh_pending = False
        LOG_CURRENT_EXCEPTION()
        try:
            refresh()
        except Exception:
            LOG_CURRENT_EXCEPTION()


def _do_scheduled_refresh():
    global _refresh_pending
    _refresh_pending = False
    try:
        refresh()
    except Exception:
        LOG_CURRENT_EXCEPTION()
    _maybe_replace_for_width()


def _maybe_replace_for_width():
    """Re-place the overlay when the "efficiency panel is 5-digit wide" state flips (a total
    crossed the threshold), so the right-shift engages/disengages live. Coalesced onto the
    efficiency refresh; a no-op when the state is unchanged (avoids a window.move every tick).
    Fail-soft: a bad read leaves the position untouched."""
    global _last_wide
    try:
        wide = efficiency_panel_wide(battle_adapter.read_damage_log_summary_flags(),
                                     battle_adapter.read_efficiency_totals(),
                                     EFFICIENCY_WIDE_THRESHOLD)
        if wide != _last_wide:
            _last_wide = wide
            battle_view.apply_position()
    except Exception:
        LOG_CURRENT_EXCEPTION()


# --- fetch-list promotion ----------------------------------------------------

def _record_played_tank(snap):
    """Promote the tank this battle is being fought in from the fetch list's temp set to the
    permanent list -- once per battle, as soon as we can read the player's OWN vehicle. Skips
    while spectating (a dead player observing a teammate: getControllingVehicleID would be the
    ally's tank, not ours). Guarded -- a promotion failure must never break the overlay push."""
    global _battle_recorded
    if _battle_recorded:
        return
    try:
        if snap.has_vehicle and not snap.is_spectating and snap.vehicle_int_cd:
            moe_wgapi.on_battle_played(snap.vehicle_int_cd)
            _battle_recorded = True
    except Exception:
        LOG_CURRENT_EXCEPTION()


# --- prediction<->outcome recorder (diagnostics) ------------------------------

def _note_prediction(snap, model):
    """Remember this push as the battle's prediction of record, so the teardown can hand it to
    adapter/sample_log for the post-battle dossier read to grade. Skipped while spectating or
    with no readable vehicle (the readout isn't ours then), so the LAST push that was genuinely
    ours wins. The trailing push is ALSO kept separately, spectating included, for the
    final_* diagnostic columns. Guarded -- the recorder must never break a push."""
    global _last_prediction, _last_final_push
    try:
        if snap.has_vehicle and snap.vehicle_int_cd:
            # Every push, spectating included -- the trailing one instruments post-mortem credit.
            _last_final_push = (snap, model)
            if not snap.is_spectating:
                _last_prediction = (snap, model)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _flush_prediction():
    """Stash the battle's final prediction for the post-battle dossier read to resolve, then
    clear it so the next battle starts fresh. Once per battle, on teardown. Every field is
    coerced to a plain JSON scalar/dict here (no game objects reach the log) and the whole body
    is guarded -- a recorder failure must never break the teardown."""
    global _last_prediction, _last_final_push
    pair = _last_prediction
    final = _last_final_push
    _last_prediction = None
    _last_final_push = None
    if pair is None:
        return
    snap, model = pair
    try:
        pred = {
            "int_cd": int(snap.vehicle_int_cd or 0),
            "ewma_k": float(EWMA_K),
            "thresholds": dict(snap.thresholds or {}),
            "pre_percentile": float(snap.pre_percentile or 0.0),
            "pre_avg_damage": int(snap.pre_avg_damage or 0),
            "baseline_known": bool(getattr(snap, "baseline_known", False)),
            "damage": int(snap.damage or 0),
            "track_assist": int(getattr(snap, "track_assist", 0) or 0),
            "spot_assist": int(getattr(snap, "spot_assist", 0) or 0),
            "stun": int(snap.stun or 0),
            "team_damage": int(snap.team_damage or 0),
            "combined_damage": int(model.combined_damage or 0),
            "counted_assist": int(model.counted_assist or 0),
            "assist_kind": str(model.assist_kind or ""),
            "proj_avg_damage": int(model.proj_avg_damage or 0),
            "predicted_percent": float(model.cur_percent or 0.0),
            "pct_delta": float(model.pct_delta or 0.0),
            "has_data": bool(model.has_data),
            "has_baseline": bool(model.has_baseline),
        }
        # The battle's trailing push, spectating included and guarded to the SAME tank. These two
        # columns exist so the data answers the post-mortem-credit question without a live-client
        # session: dying mid-battle makes our state AT DEATH the prediction of record, while WG
        # keeps crediting us afterwards (burn damage from our fires, stun from a landed shell) and
        # the dossier ground truth includes that credit. Equal to the prediction => a non-issue;
        # divergent => the death path systematically under-predicts by that much.
        if final is not None and int(final[0].vehicle_int_cd or 0) == pred["int_cd"]:
            pred["final_combined_damage"] = int(final[1].combined_damage or 0)
            pred["final_percent"] = float(final[1].cur_percent or 0.0)
        sample_log.stash(pred)
    except Exception:
        LOG_CURRENT_EXCEPTION()


# --- push --------------------------------------------------------------------

def refresh():
    """Re-push the current battle model into whichever of our two battle windows are open.

    ONE snapshot read + ONE model build per call, shared by both pushes: the coalesced
    efficiency tick must cost a single recompute, not one per window."""
    view = battle_view.active_view()
    bar = progress_view.active_view()
    if view is None and bar is None:
        return False
    try:
        snap = battle_adapter.build_battle_snapshot()
        _record_played_tank(snap)
        model = build_battle_model(snap)
        _note_prediction(snap, model)
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return False
    if view is not None:
        push(view.viewModel, snap, model)
    if bar is not None:
        push_progress(bar.viewModel, snap, model)
    return True


def push(rvm, snap, model):
    """Write the recomputed in-battle overlay model into rvm."""
    if rvm is None:
        return
    try:
        overlay_open = bool(_open_overlays)
        visible = battle_bar_visible(snap.in_battle, snap.has_vehicle, snap.is_spectating,
                                     overlay_open=overlay_open,
                                     enabled=mod_settings.battle_enabled(),
                                     alt_mode=mod_settings.battle_alt_key_enabled(),
                                     alt_held=_alt_held)
        assist_visible = mod_settings.counted_assistance_enabled()
        LOG_DEBUG("[moe-battle] push visible=%s spectating=%s scoreboard=%s alt=%s cd=%d pct=%.1f delta=%.2f data=%s baseline=%s assist=%d/%s(on=%s)" % (
            visible, snap.is_spectating, overlay_open, _alt_held, model.combined_damage,
            model.cur_percent, model.pct_delta, model.has_data, model.has_baseline,
            model.counted_assist, model.assist_kind, assist_visible))
        with rvm.transaction() as tx:
            tx.setVisible(visible)
            tx.setCombinedDamage(model.combined_damage)
            tx.setProjAvgDamage(model.proj_avg_damage)
            tx.setCurPercent(model.cur_percent)
            tx.setPctDelta(model.pct_delta)
            tx.setHasData(model.has_data)
            tx.setHasBaseline(model.has_baseline)
            tx.setCountedAssist(model.counted_assist)
            tx.setAssistKind(model.assist_kind)
            tx.setAssistVisible(assist_visible)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def push_progress(rvm, snap, model):
    """Write the centre-screen progress bar's model into rvm (a ProgressVM).

    The bar works in COMBINED DAMAGE along the mark axis, so it takes the axis ends plus the two
    averages and derives everything else (position, delta, requirement-met) in JS. Its `visible`
    reuses battle_bar_visible's base gating (in battle, own vehicle, not spectating, no full-stats
    scoreboard) with its OWN checkbox as the master and alt_mode off -- Alt is an ADDITIVE show
    trigger for this widget (pushed as altHeld), not a gate. Without a career baseline
    (replay / relogin, BUG B) pre_avg is a false 0 and the axis position would be nonsense, so the
    bar stays hidden entirely rather than dashing values out like the overlay does.

    projAvg is pushed UNROUNDED (ewma_project_raw + a Real VM property), unlike the overlay's
    integer `projAvgDamage`: the bar's only show-trigger is the JS change-detect comparing
    successive pushes, and at k ~= 0.02 an integer proj moves ~2 steps across a whole battle, so
    rounding it anywhere on this path is what kept the bar from ever appearing. MoEProgress.js's
    fmt() rounds for display."""
    if rvm is None:
        return
    try:
        marks = marks_from_percentile(snap.pre_percentile)
        axis_lo, axis_hi = mark_axis(snap.thresholds, marks)
        visible = (battle_bar_visible(snap.in_battle, snap.has_vehicle, snap.is_spectating,
                                      overlay_open=bool(_open_overlays),
                                      enabled=mod_settings.progress_bar_enabled())
                   and model.has_baseline)
        pre_avg = snap.pre_avg_damage or 0
        proj_avg = ewma_project_raw(pre_avg, model.combined_damage)
        has_data = axis_hi > axis_lo
        LOG_DEBUG("[moe-battle] push_progress visible=%s data=%s marks=%d axis=%.1f..%.1f pre=%d proj=%.3f alt=%s" % (
            visible, has_data, marks, axis_lo, axis_hi, pre_avg, proj_avg, _alt_held))
        with rvm.transaction() as tx:
            tx.setVisible(visible)
            tx.setMarks(marks)
            tx.setAxisLo(axis_lo)
            tx.setAxisHi(axis_hi)
            tx.setPreAvg(pre_avg)
            tx.setProjAvg(proj_avg)
            tx.setHasData(has_data)
            tx.setAltHeld(_alt_held)
    except Exception:
        LOG_CURRENT_EXCEPTION()


def apply_settings():
    """Apply the battle settings live (the mod_settings change callback).

    Each of the two windows must exist whenever its own master checkbox is on -- the corner
    overlay's "In-Battle Widget" (the "Show on Alt Key" child is inert while that master is off,
    so it never opens the window on its own) and the bar's "Next Mark Progress Bar". Master off
    -> close that window if open. Master on while in a battle -> open it now (arm + kick data +
    push) so the toggle takes effect without waiting for the next battle. (Under the Alt-key mode
    the overlay window opens but stays hidden until Alt is held -- push/battle_bar_visible decides
    visible.) A trailing re-push makes a live MODE switch, which opens nothing, take effect too."""
    try:
        opened = False
        for enabled, module in ((mod_settings.battle_enabled(), battle_view),
                                (mod_settings.progress_bar_enabled(), progress_view)):
            if not enabled:
                if module.active_view() is not None:
                    module.close_window()
            elif _in_battle and module.active_view() is None:
                module.open_window()
                opened = True
        if opened:
            install_all_listeners()
            moe_wgapi.start()
        refresh()
    except Exception:
        LOG_CURRENT_EXCEPTION()
