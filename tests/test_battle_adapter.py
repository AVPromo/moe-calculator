# -*- coding: utf-8 -*-
"""Branch-logic tests for adapter/battle_adapter.build_battle_snapshot -- the baseline
fallback that is the heart of BUG B, plus the gating-flag passthrough. battle_adapter
imports BigWorld at top (stubbed in conftest); each test monkeypatches the adapter's own
read seams so the snapshot-assembly logic is exercisable with the client closed."""
from moe_calculator.adapter import battle_adapter as ba
from moe_calculator.adapter import baseline_cache


def teardown_function(_):
    baseline_cache.clear()


def _patch_reads(monkeypatch, cd=1073, eff=(2000, 500, 0), thr=None,
                 in_battle=True, spectating=False, nation="germany"):
    monkeypatch.setattr(ba, "_player_vehicle_descr", lambda: object())
    monkeypatch.setattr(ba, "_player_vehicle_int_cd", lambda d: cd)
    monkeypatch.setattr(ba, "_read_efficiency", lambda: eff)
    monkeypatch.setattr(ba, "_player_nation", lambda d: nation)
    monkeypatch.setattr(ba, "_in_battle", lambda: in_battle)
    monkeypatch.setattr(ba, "_is_spectating", lambda: spectating)
    # `thresholds` is keyed by PERCENTILE (65/85/95 + the 100 goalpost), not by mark count.
    monkeypatch.setattr(ba.moe_wgapi, "get_thresholds",
                        lambda c: dict(thr if thr is not None else {65: 1, 85: 2, 95: 3, 100: 4}))
    monkeypatch.setattr(ba.moe_wgapi, "needs_estimate", lambda c: False)
    # In battle the lobby dossier is None -> engine_adapter._read_moe returns zeros; the
    # baseline must come from the garage cache instead.
    monkeypatch.setattr(ba.engine_adapter, "_read_moe", lambda c: (0, 0.0, 0))


def test_snapshot_falls_back_to_garage_baseline(monkeypatch):
    _patch_reads(monkeypatch)
    baseline_cache.remember(1073, 73.7, 1800)
    snap = ba.build_battle_snapshot()
    assert snap.has_vehicle is True
    assert snap.pre_percentile == 73.7
    assert snap.pre_avg_damage == 1800
    assert snap.damage == 2000 and snap.assist == 500


def test_snapshot_no_baseline_when_never_garaged(monkeypatch):
    # BUG B: replay / relogin straight into battle, tank never seen in the garage this
    # session -> the cache is empty -> the baseline reads empty. build_battle_model then
    # flags has_baseline=False (see test_battle_builder) and the overlay dashes the metrics.
    _patch_reads(monkeypatch)
    snap = ba.build_battle_snapshot()
    assert snap.pre_percentile == 0.0
    assert snap.pre_avg_damage == 0
    assert snap.baseline_known is False


def test_snapshot_baseline_known_first_battle_zero_career(monkeypatch):
    # First-ever battle in a freshly-bought tank: the garage DID read it this session
    # (marking it seen with an all-zero career), so the baseline is genuinely 0 -- NOT the
    # untrusted 0 of a replay. baseline_known must be True so the overlay projects from 0
    # instead of dashing.
    _patch_reads(monkeypatch)
    baseline_cache.remember(1073, 0.0, 0)   # garage read of a 0-career tank
    snap = ba.build_battle_snapshot()
    assert snap.pre_percentile == 0.0       # genuine zero baseline
    assert snap.pre_avg_damage == 0
    assert snap.baseline_known is True


def test_snapshot_baseline_known_with_cached_value(monkeypatch):
    # Normal flow: a real >0 baseline is cached -> both value and seen-marker present.
    _patch_reads(monkeypatch)
    baseline_cache.remember(1073, 73.7, 1800)
    snap = ba.build_battle_snapshot()
    assert snap.baseline_known is True


def test_snapshot_no_vehicle_hides(monkeypatch):
    _patch_reads(monkeypatch, cd=0)
    snap = ba.build_battle_snapshot()
    assert snap.has_vehicle is False


def test_snapshot_carries_gating_flags(monkeypatch):
    _patch_reads(monkeypatch, spectating=True, in_battle=True)
    snap = ba.build_battle_snapshot()
    assert snap.is_spectating is True
    assert snap.in_battle is True


def test_snapshot_carries_assist_split(monkeypatch):
    # The server battle-events summary split (track, spot) rides into the snapshot.
    _patch_reads(monkeypatch)
    monkeypatch.setattr(ba, "_read_assist_split", lambda: (900, 400))
    snap = ba.build_battle_snapshot()
    assert snap.track_assist == 900 and snap.spot_assist == 400


def test_snapshot_indexes_the_four_field_moe_read(monkeypatch):
    # REGRESSION: _read_moe grew a trailing battlesCount (the sample log's pairing aid). This
    # adapter reads it BY INDEX, so the extra field must not shift the baseline it picks up --
    # a real >0 in-battle read still trusts itself over the garage cache.
    _patch_reads(monkeypatch)
    monkeypatch.setattr(ba.engine_adapter, "_read_moe", lambda c: (2, 73.7, 1800, 1240))
    baseline_cache.remember(1073, 10.0, 100)      # must NOT win over the live read
    snap = ba.build_battle_snapshot()
    assert snap.pre_percentile == 73.7
    assert snap.pre_avg_damage == 1800
    assert snap.baseline_known is True


def test_snapshot_assist_split_defaults_zero(monkeypatch):
    # With the client closed _read_assist_split fails soft to (0, 0) -> snapshot carries 0/0
    # (the merged live `assist` covers combined damage until the split arrives).
    _patch_reads(monkeypatch)
    snap = ba.build_battle_snapshot()
    assert snap.track_assist == 0 and snap.spot_assist == 0


# --- the offline-estimator fallback (parity with engine_adapter.build_snapshot) ---
# THE bug this closes: engine_adapter fell back to the offline estimator when a tank's WG request
# completed with no data, and battle_adapter did NOT. So on such a tank the GARAGE rendered real
# numbers while every in-battle widget sat on an empty table and showed nothing at all.

def test_snapshot_estimates_when_the_wg_request_errored(monkeypatch):
    _patch_reads(monkeypatch, thr={})
    monkeypatch.setattr(ba.moe_wgapi, "needs_estimate", lambda c: True)
    calls = []
    monkeypatch.setattr(ba.engine_adapter, "_estimate_thresholds",
                        lambda pct, dmg: calls.append((pct, dmg)) or {65: 11, 85: 22,
                                                                      95: 33, 100: 44})
    baseline_cache.remember(1073, 60.0, 1500)
    snap = ba.build_battle_snapshot()
    assert snap.thresholds == {65: 11, 85: 22, 95: 33, 100: 44}
    # ...fed the SAME career point the garage path feeds it (the cached baseline).
    assert calls == [(60.0, 1500)]


def test_snapshot_waits_when_the_fetch_is_still_pending(monkeypatch):
    # needs_estimate False means the fetch has not answered yet -> do NOT estimate; the ready
    # listener re-pushes when it lands. Estimating here would flash extrapolated numbers first.
    _patch_reads(monkeypatch, thr={})
    monkeypatch.setattr(ba.moe_wgapi, "needs_estimate", lambda c: False)
    called = []
    monkeypatch.setattr(ba.engine_adapter, "_estimate_thresholds",
                        lambda pct, dmg: called.append(1) or {65: 11})
    baseline_cache.remember(1073, 60.0, 1500)
    assert ba.build_battle_snapshot().thresholds == {}
    assert called == []


def test_snapshot_never_estimates_over_a_real_wg_table(monkeypatch):
    # A present WG table always wins -- the estimator is the fallback, not an override.
    _patch_reads(monkeypatch)
    monkeypatch.setattr(ba.moe_wgapi, "needs_estimate", lambda c: True)
    monkeypatch.setattr(ba.engine_adapter, "_estimate_thresholds",
                        lambda pct, dmg: {65: 11, 85: 22, 95: 33, 100: 44})
    baseline_cache.remember(1073, 60.0, 1500)
    assert ba.build_battle_snapshot().thresholds == {65: 1, 85: 2, 95: 3, 100: 4}


def test_the_estimated_table_actually_drives_the_battle_readouts(monkeypatch):
    # The point of the fallback: end-to-end, an estimated table must make the battle model report
    # a percent (has_data True) where before it had an empty table and reported nothing.
    from moe_calculator.domain.battle_builder import build_battle_model
    _patch_reads(monkeypatch, thr={})
    monkeypatch.setattr(ba.moe_wgapi, "needs_estimate", lambda c: True)
    baseline_cache.remember(1073, 60.0, 1500)
    snap = ba.build_battle_snapshot()          # the REAL estimator, not a stub
    assert set(snap.thresholds) == {65, 85, 95, 100}
    assert build_battle_model(snap).has_data is True


