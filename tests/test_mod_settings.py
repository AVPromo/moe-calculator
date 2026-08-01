# -*- coding: utf-8 -*-
"""Tests for the settings module's pure merge logic. merge_settings is the only piece that
must be correct without the game: it turns whatever ModsSettingsAPI hands back (or nothing)
into the booleans the bridges read. The MSA registration/glue is not unit-tested (it needs
the client)."""
import re
import sys
import types

import pytest

from moe_calculator.bridge import mod_settings
from moe_calculator.bridge.mod_settings import (
    merge_settings, DEFAULTS, GARAGE_KEY, BATTLE_KEY, BATTLE_ALT_KEY,
    COUNTED_ASSIST_KEY, PROGRESS_BAR_KEY, LINKAGE, SETTINGS_VERSION,
    PROGRESS_VARIANT_KEY, PROGRESS_VARIANT_MOVING_AVERAGE, PROGRESS_VARIANT_EFFICIENCY,
    PROGRESS_SIZE_KEY, PROGRESS_SIZE_DEFAULT, PROGRESS_SIZE_LARGE,
    PROGRESS_TRANSITIONS_KEY, PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY,
    PROGRESS_SHOW_EVENTS_KEY, PROGRESS_SHOW_ALT_KEY, PROGRESS_SHOW_ALWAYS_KEY,
    battle_alt_key_enabled, battle_enabled, counted_assistance_enabled,
    progress_bar_enabled, progress_bar_variant, progress_bar_size, clamp_variant,
    progress_transitions_events, progress_transitions_manual,
    progress_show_events, progress_alt_held,
    POS_X_KEY, POS_Y_KEY, POS_W_KEY, POS_H_KEY, FOLLOW_CAROUSEL_KEY, POS_MAX,
    clamp_pos, pos_x, pos_y, pos_w, pos_h, follow_carousel, set_position)
from moe_calculator.adapter import settings_i18n


def _defaults_with(over):
    """A fresh copy of the full DEFAULTS with `over` (a dict) applied -- keeps the
    exact-equality merge assertions readable now that DEFAULTS carries the position group.
    Takes a dict (not **kwargs) because the keys are runtime varName strings, not identifiers."""
    out = dict(DEFAULTS)
    out.update(over)
    return out


@pytest.fixture(autouse=True)
def _restore_settings():
    """Each test that mutates the module-global cache restores it afterwards."""
    saved = dict(mod_settings._settings)
    yield
    mod_settings._seed(saved)


def test_defaults_when_empty_or_none():
    # No saved store (fresh install / MSA absent) -> both widgets and the counted-assistance row
    # on, the Alt-peek mode and the Progress Bar off (opt-in), the Progress Bar variant on Damage
    # Efficiency (0, the v13 order), both of its VISIBILITY triggers on with "Always" off, all
    # three TRANSITION switches on (the animated bar is what shipped), the drag position at auto
    # (0/0/0/0) and Follow Carousel on.
    assert merge_settings(None) == DEFAULTS
    assert merge_settings({}) == DEFAULTS
    assert DEFAULTS == {GARAGE_KEY: True, BATTLE_KEY: True, BATTLE_ALT_KEY: False,
                        COUNTED_ASSIST_KEY: True, PROGRESS_BAR_KEY: False,
                        PROGRESS_VARIANT_KEY: 0, PROGRESS_SIZE_KEY: 0,
                        PROGRESS_SHOW_EVENTS_KEY: True, PROGRESS_SHOW_ALT_KEY: True,
                        PROGRESS_SHOW_ALWAYS_KEY: False,
                        PROGRESS_TRANSITIONS_KEY: True, PROGRESS_TRANS_EVENTS_KEY: True,
                        PROGRESS_TRANS_MANUAL_KEY: True,
                        POS_X_KEY: 0, POS_Y_KEY: 0, POS_W_KEY: 0, POS_H_KEY: 0,
                        FOLLOW_CAROUSEL_KEY: True}
    # The three transitions flags are real BOOLS, not the radios' int indices: they must default
    # True (== "animate", what shipped) so an existing install's bar does not go instant on update.
    for key in (PROGRESS_TRANSITIONS_KEY, PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY):
        assert DEFAULTS[key] is True
    # ...and so are the three VISIBILITY flags, whose defaults reproduce EXACTLY the pre-v13
    # behaviour: an event raised the bar and Alt peeked it, unconditionally, and there was no
    # always-on mode.
    assert DEFAULTS[PROGRESS_SHOW_EVENTS_KEY] is True
    assert DEFAULTS[PROGRESS_SHOW_ALT_KEY] is True
    assert DEFAULTS[PROGRESS_SHOW_ALWAYS_KEY] is False
    # BOTH radio defaults must be the INT 0, not False -- the variant lands on Damage Efficiency
    # (the v13 index 0) at the shipped size, and a bool here would poison every _coerce round-trip.
    assert DEFAULTS[PROGRESS_VARIANT_KEY] is PROGRESS_VARIANT_EFFICIENCY
    assert DEFAULTS[PROGRESS_SIZE_KEY] is PROGRESS_SIZE_DEFAULT
    for key in (PROGRESS_VARIANT_KEY, PROGRESS_SIZE_KEY):
        assert not isinstance(DEFAULTS[key], bool)
    # THE v13 OPTION FLIP, pinned where it is decided. The two indices swapped and the stored raw
    # int rides across the bump unchanged, so this pair IS the one-time silent swap the maintainer
    # accepted -- a later "tidy-up" that flips them back would silently swap every user a second
    # time. settings_i18n._VARIANT_OPTIONS must stay in the same order (see its own test).
    assert (PROGRESS_VARIANT_EFFICIENCY, PROGRESS_VARIANT_MOVING_AVERAGE) == (0, 1)


def test_overlays_known_keys():
    out = merge_settings({GARAGE_KEY: False, BATTLE_KEY: True, BATTLE_ALT_KEY: True,
                          COUNTED_ASSIST_KEY: True})
    # Only the four bool flags were supplied -> the position group keeps its auto defaults.
    assert out == _defaults_with({GARAGE_KEY: False, BATTLE_KEY: True, BATTLE_ALT_KEY: True,
                                  COUNTED_ASSIST_KEY: True})
    out2 = merge_settings({GARAGE_KEY: True, BATTLE_KEY: False, BATTLE_ALT_KEY: False,
                           COUNTED_ASSIST_KEY: False,
                           POS_X_KEY: 640, POS_Y_KEY: 360, POS_W_KEY: 1920, POS_H_KEY: 1080,
                           FOLLOW_CAROUSEL_KEY: False})
    # A full store overlays every key, position coords coerced to clamped ints. The three
    # progress-bar keys, the three VISIBILITY keys and the three transitions keys are absent from
    # the input, so they keep their defaults.
    assert out2 == {GARAGE_KEY: True, BATTLE_KEY: False, BATTLE_ALT_KEY: False,
                    COUNTED_ASSIST_KEY: False, PROGRESS_BAR_KEY: False,
                    PROGRESS_VARIANT_KEY: 0, PROGRESS_SIZE_KEY: 0,
                    PROGRESS_SHOW_EVENTS_KEY: True, PROGRESS_SHOW_ALT_KEY: True,
                    PROGRESS_SHOW_ALWAYS_KEY: False,
                    PROGRESS_TRANSITIONS_KEY: True, PROGRESS_TRANS_EVENTS_KEY: True,
                    PROGRESS_TRANS_MANUAL_KEY: True,
                    POS_X_KEY: 640, POS_Y_KEY: 360, POS_W_KEY: 1920, POS_H_KEY: 1080,
                    FOLLOW_CAROUSEL_KEY: False}


def test_partial_dict_fills_missing_with_defaults():
    # Only one key present -> the others fall back to their defaults.
    out = merge_settings({GARAGE_KEY: False})
    assert out == _defaults_with({GARAGE_KEY: False})


def test_unknown_keys_ignored():
    out = merge_settings({GARAGE_KEY: False, "bogus": 123, "settingsVersion": 9})
    assert out == _defaults_with({GARAGE_KEY: False})
    assert "bogus" not in out


def test_values_coerced_to_bool():
    out = merge_settings({GARAGE_KEY: 0, BATTLE_KEY: 1, BATTLE_ALT_KEY: 1,
                          COUNTED_ASSIST_KEY: 1})
    assert out[GARAGE_KEY] is False
    assert out[BATTLE_KEY] is True
    assert out[BATTLE_ALT_KEY] is True
    assert out[COUNTED_ASSIST_KEY] is True


def test_non_dict_input_degrades_to_defaults():
    assert merge_settings("nonsense") == DEFAULTS
    assert merge_settings(42) == DEFAULTS
    assert merge_settings([GARAGE_KEY]) == DEFAULTS


def test_returns_fresh_dict_not_defaults_alias():
    # Must not hand back a reference to DEFAULTS (a caller mutating it would corrupt the base).
    out = merge_settings({})
    out[GARAGE_KEY] = False
    assert DEFAULTS[GARAGE_KEY] is True


def test_battle_alt_key_default_off_and_getter():
    # Getter reads the live cache. _seed replaces it wholesale; _apply overlays.
    mod_settings._seed(DEFAULTS)
    assert battle_alt_key_enabled() is False
    mod_settings._apply({BATTLE_ALT_KEY: True})
    assert battle_alt_key_enabled() is True
    mod_settings._apply({BATTLE_ALT_KEY: 0})
    assert battle_alt_key_enabled() is False


def test_counted_assistance_default_on_and_getter():
    # The counted-assistance row ships ON since v13 (MoE counts the assist, so the row is part of
    # the readout) and the getter tracks live changes. The DEFAULT and the getter's own fallback
    # must agree -- an absent key has to read the same as a fresh install, or a partially-written
    # store flips the row.
    mod_settings._seed(DEFAULTS)
    assert counted_assistance_enabled() is True
    mod_settings._apply({COUNTED_ASSIST_KEY: False})
    assert counted_assistance_enabled() is False
    mod_settings._apply({COUNTED_ASSIST_KEY: 1})
    assert counted_assistance_enabled() is True
    del mod_settings._settings[COUNTED_ASSIST_KEY]
    assert counted_assistance_enabled() is DEFAULTS[COUNTED_ASSIST_KEY] is True


def test_progress_bar_default_off_and_getter():
    # The centre-screen Progress Log bar ships OFF (a transient overlay is intrusive, so
    # existing users must opt in) and the getter tracks live changes. The NAME
    # `progress_bar_enabled` is a contract the progress-bar bridge calls -- don't rename it.
    mod_settings._seed(DEFAULTS)
    assert progress_bar_enabled() is False
    mod_settings._apply({PROGRESS_BAR_KEY: True})
    assert progress_bar_enabled() is True
    mod_settings._apply({PROGRESS_BAR_KEY: 0})
    assert progress_bar_enabled() is False


# --- the Progress Bar variant radio: the mod's ONE non-bool setting --------------------------

def test_clamp_variant_rejects_bools_and_out_of_range():
    # THE trust boundary. MSA stores a RadioButtonGroup's value as a 0-based INT index, and
    # _coerce's default branch bools everything it doesn't recognize -- so a missing/incorrect
    # variant branch would silently turn index 1 into True and round-trip that back into MSA.
    # Legal indices pass through unchanged, as ints.
    assert clamp_variant(0) == PROGRESS_VARIANT_EFFICIENCY
    assert clamp_variant(1) == PROGRESS_VARIANT_MOVING_AVERAGE
    for good in (0, 1):
        assert not isinstance(clamp_variant(good), bool)
    # Numeric strings / floats coerce through int(), like clamp_pos.
    assert clamp_variant("1") == 1
    assert clamp_variant("0") == 0
    assert clamp_variant(1.9) == 1
    # Hostile / corrupt stores all collapse to 0 (the template default), never a crash and never a
    # bool. bool is an int SUBCLASS, so True would otherwise sneak through a bare int() as index
    # 1 -- a bool is never a legal index, so it is corrupt.
    for bad in (True, False, 2, PROGRESS_VARIANT_MOVING_AVERAGE + 1, -1, 10 ** 9,
                None, "abc", "", [1], {}, object()):
        got = clamp_variant(bad)
        assert got == PROGRESS_VARIANT_EFFICIENCY, "%r leaked %r" % (bad, got)
        assert not isinstance(got, bool), "%r leaked a bool" % (bad,)


def test_coerce_variant_key_is_not_booled():
    # The branch is wired to the right key (a regression here is invisible until a user's radio
    # choice silently becomes True/False in the MSA store).
    assert mod_settings._coerce(PROGRESS_VARIANT_KEY, 1) == 1
    assert mod_settings._coerce(PROGRESS_VARIANT_KEY, 1) is not True
    assert mod_settings._coerce(PROGRESS_VARIANT_KEY, True) == 0
    assert mod_settings._coerce(PROGRESS_VARIANT_KEY, 99) == 0
    assert mod_settings._coerce(PROGRESS_VARIANT_KEY, None) == 0
    # ...while merge_settings, which routes through _coerce, keeps the index intact end to end.
    assert merge_settings({PROGRESS_VARIANT_KEY: 1})[PROGRESS_VARIANT_KEY] == 1
    assert merge_settings({PROGRESS_VARIANT_KEY: "1"})[PROGRESS_VARIANT_KEY] == 1
    assert merge_settings({PROGRESS_VARIANT_KEY: 7})[PROGRESS_VARIANT_KEY] == 0


def test_progress_bar_variant_default_and_getter():
    # Ships on Damage Efficiency (index 0 since the v13 option flip) and the getter tracks live
    # changes. The NAME `progress_bar_variant` is the contract the progress-bar bridges read --
    # don't rename it.
    mod_settings._seed(DEFAULTS)
    assert progress_bar_variant() == PROGRESS_VARIANT_EFFICIENCY
    mod_settings._apply({PROGRESS_VARIANT_KEY: PROGRESS_VARIANT_MOVING_AVERAGE})
    assert progress_bar_variant() == PROGRESS_VARIANT_MOVING_AVERAGE
    mod_settings._apply({PROGRESS_VARIANT_KEY: 0})
    assert progress_bar_variant() == PROGRESS_VARIANT_EFFICIENCY


def test_progress_bar_variant_getter_reclamps_a_corrupt_store():
    # Like the position getters, the getter re-clamps whatever is cached, so a store corrupted
    # outside _coerce (a hand-edited .dat, a foreign write) can never leak a bad index or a bool
    # to the bridge that picks a window off it.
    mod_settings._seed(dict(DEFAULTS))
    for junk in (True, 5, -2, None, "x"):
        mod_settings._settings[PROGRESS_VARIANT_KEY] = junk
        assert progress_bar_variant() == PROGRESS_VARIANT_EFFICIENCY
        assert not isinstance(progress_bar_variant(), bool)
    # An absent key falls back to the 0 default rather than raising.
    del mod_settings._settings[PROGRESS_VARIANT_KEY]
    assert progress_bar_variant() == PROGRESS_VARIANT_EFFICIENCY


# --- the Progress Bar SIZE radio: the mod's SECOND non-bool setting ---------------------------

def test_coerce_size_key_is_not_booled():
    # THE reason clamp_variant grew a max_index instead of the size key falling through to bool():
    # index 1 (LARGE) would become True, round-trip back into MSA as a bool, and destroy the
    # setting -- the exact failure the variant branch already guards, on a second key that a
    # `key == PROGRESS_VARIANT_KEY`-only branch silently misses.
    assert mod_settings._coerce(PROGRESS_SIZE_KEY, 1) == PROGRESS_SIZE_LARGE
    assert mod_settings._coerce(PROGRESS_SIZE_KEY, 1) is not True
    assert mod_settings._coerce(PROGRESS_SIZE_KEY, 0) is not False
    assert not isinstance(mod_settings._coerce(PROGRESS_SIZE_KEY, 1), bool)
    # ...and its own ceiling is honoured: this radio has exactly two options, so anything above
    # LARGE is corrupt, and a bool is never a legal index (bool is an int SUBCLASS).
    for bad in (True, False, PROGRESS_SIZE_LARGE + 1, -1, None, "abc", [1]):
        assert mod_settings._coerce(PROGRESS_SIZE_KEY, bad) == PROGRESS_SIZE_DEFAULT, \
            "%r leaked through the size branch" % (bad,)
    # ...end to end through merge_settings, which is the path MSA's payload actually takes.
    assert merge_settings({PROGRESS_SIZE_KEY: 1})[PROGRESS_SIZE_KEY] == PROGRESS_SIZE_LARGE
    assert merge_settings({PROGRESS_SIZE_KEY: "1"})[PROGRESS_SIZE_KEY] == PROGRESS_SIZE_LARGE
    assert merge_settings({PROGRESS_SIZE_KEY: True})[PROGRESS_SIZE_KEY] == PROGRESS_SIZE_DEFAULT


def test_progress_bar_size_getter_defaults_tracks_and_reclamps():
    # Mirrors the variant getter's two tests: ships on 0 (the shipped size, so an existing user's
    # bar does not suddenly grow), tracks live changes, and RE-CLAMPS on read so a store corrupted
    # outside _coerce (a hand-edited .dat, a foreign write) can never leak a bool or a stray index
    # into the JS's barSize / BarHost's y offset. The NAME is the contract battle_bridge and
    # bar_window call -- don't rename it.
    mod_settings._seed(DEFAULTS)
    assert progress_bar_size() == PROGRESS_SIZE_DEFAULT
    mod_settings._apply({PROGRESS_SIZE_KEY: PROGRESS_SIZE_LARGE})
    assert progress_bar_size() == PROGRESS_SIZE_LARGE
    mod_settings._apply({PROGRESS_SIZE_KEY: 0})
    assert progress_bar_size() == PROGRESS_SIZE_DEFAULT
    for junk in (True, 5, -2, None, "x"):
        mod_settings._settings[PROGRESS_SIZE_KEY] = junk
        assert progress_bar_size() == PROGRESS_SIZE_DEFAULT, "%r leaked on read" % (junk,)
        assert not isinstance(progress_bar_size(), bool)
    del mod_settings._settings[PROGRESS_SIZE_KEY]
    assert progress_bar_size() == PROGRESS_SIZE_DEFAULT


# --- the Transitions group: a master folded into its two children's getters -------------------

_TRANS_KEYS = (PROGRESS_TRANSITIONS_KEY, PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY)


def _trans(master, events, manual):
    """Seed the three transitions flags and return (events_getter, manual_getter) results."""
    mod_settings._seed(_defaults_with({PROGRESS_TRANSITIONS_KEY: master,
                                       PROGRESS_TRANS_EVENTS_KEY: events,
                                       PROGRESS_TRANS_MANUAL_KEY: manual}))
    return progress_transitions_events(), progress_transitions_manual()


def test_transitions_master_off_forces_both_children_false():
    # THE reason the fold lives in Python: the JS is handed only the two EFFECTIVE flags, so there
    # is one AND in the codebase and no chance of the widget honouring a child while the master
    # is off. With the master off, EVERY child combination must read False.
    for events in (True, False):
        for manual in (True, False):
            assert _trans(False, events, manual) == (False, False), \
                "master off leaked events=%r manual=%r" % (events, manual)


def test_transitions_master_on_passes_each_child_through_independently():
    # With the master on, each getter is exactly its OWN child -- no cross-talk (a single shared
    # flag, or the two getters reading the same key, would pass three of these four and fail the
    # mixed pair).
    assert _trans(True, True, True) == (True, True)
    assert _trans(True, False, True) == (False, True)
    assert _trans(True, True, False) == (True, False)
    assert _trans(True, False, False) == (False, False)


def test_transitions_getters_return_real_bools_and_default_animated():
    # Both getters return a genuine bool (the JS field is a _addBoolProperty), and an absent key
    # falls back to True -- "animated", which is what shipped -- not a raise and not "instant".
    assert _trans(True, True, True) == (True, True)
    for got in _trans(True, 1, 1):
        assert got is True                  # a truthy non-bool store still yields a bool
    mod_settings._seed(dict(DEFAULTS))
    for key in _TRANS_KEYS:
        del mod_settings._settings[key]
    assert progress_transitions_events() is True
    assert progress_transitions_manual() is True


def test_transitions_keys_round_trip_and_coerce_to_bool():
    # The three keys are plain bools, so they take _coerce's DEFAULT branch -- unlike the two
    # radios, which own dedicated branches. A stray non-bool payload (a hand-edited MSA store, a
    # foreign write)
    # must not leak an int/string through to a _setBool: mirror how the other bool keys are tested.
    for key in _TRANS_KEYS:
        assert mod_settings._coerce(key, 0) is False
        assert mod_settings._coerce(key, 1) is True
        assert mod_settings._coerce(key, "yes") is True
        assert mod_settings._coerce(key, "") is False
        assert mod_settings._coerce(key, None) is False
        assert isinstance(mod_settings._coerce(key, 7), bool)
    # ...end to end through merge_settings (the path MSA's payload actually takes) and through
    # _apply (the live-change path).
    out = merge_settings(dict((key, 0) for key in _TRANS_KEYS))
    assert out == _defaults_with(dict((key, False) for key in _TRANS_KEYS))
    for key in _TRANS_KEYS:
        assert out[key] is False
    out = merge_settings(dict((key, 1) for key in _TRANS_KEYS))
    for key in _TRANS_KEYS:
        assert out[key] is True
    mod_settings._seed(dict(DEFAULTS))
    mod_settings._apply(dict((key, 0) for key in _TRANS_KEYS))
    for key in _TRANS_KEYS:
        assert mod_settings._settings[key] is False, "%s leaked a non-bool through _apply" % key
    # A foreign broadcast carrying none of them leaves the user's choice alone (the _apply rule).
    mod_settings._apply({"someForeignKey": True})
    for key in _TRANS_KEYS:
        assert mod_settings._settings[key] is False


# --- the VISIBILITY trio: when the bar comes up (a different axis from Transitions) -----------

_SHOW_KEYS = (PROGRESS_SHOW_EVENTS_KEY, PROGRESS_SHOW_ALT_KEY, PROGRESS_SHOW_ALWAYS_KEY)


def _show(events, alt_key, always):
    """Seed the three visibility flags and return (show_events, alt_held_up, alt_held_down)."""
    mod_settings._seed(_defaults_with({PROGRESS_SHOW_EVENTS_KEY: events,
                                       PROGRESS_SHOW_ALT_KEY: alt_key,
                                       PROGRESS_SHOW_ALWAYS_KEY: always}))
    return progress_show_events(), progress_alt_held(True), progress_alt_held(False)


def test_show_defaults_reproduce_the_pre_v13_always_on_triggers():
    # Fresh defaults must behave EXACTLY like the build before these switches existed: an event
    # raises the bar and a held Alt peeks it, with nothing pinned.
    assert _show(True, True, False) == (True, True, False)


def test_show_always_overrides_both_other_triggers():
    # "Always" pins the bar (progress_alt_held True regardless of the real Alt state -- a
    # permanently-held Alt IS the always-on mode) and forces `showEvents` on so the pinned bar's
    # NUMBERS keep updating. MSA still stores + pushes a greyed control's value, so every
    # combination of the two greyed switches must land identically.
    for events in (True, False):
        for alt_key in (True, False):
            assert _show(events, alt_key, True) == (True, True, True), \
                "always leaked events=%r alt_key=%r" % (events, alt_key)


def test_show_events_and_alt_key_gate_independently_when_always_is_off():
    # No cross-talk: each switch owns exactly its own trigger (a single shared flag, or both
    # getters reading one key, would pass three of these four and fail the mixed pair).
    assert _show(True, True, False) == (True, True, False)
    assert _show(False, True, False) == (False, True, False)
    assert _show(True, False, False) == (True, False, False)
    # Both off => the bar has no way up at all while its master is on.
    assert _show(False, False, False) == (False, False, False)


def test_show_getters_return_real_bools_and_default_to_the_shipped_triggers():
    # Both feed _addBoolProperty fields, so a truthy non-bool store must still yield a bool -- and
    # an ABSENT key must fall back to the SHIPPED behaviour (trigger on), never to "never shows".
    for got in _show(1, 1, 0):
        assert isinstance(got, bool)
    mod_settings._seed(dict(DEFAULTS))
    for key in _SHOW_KEYS:
        del mod_settings._settings[key]
    assert progress_show_events() is True
    assert progress_alt_held(True) is True
    assert progress_alt_held(False) is False


def test_show_keys_coerce_to_bool_end_to_end():
    # Plain bools, so they take _coerce's DEFAULT branch (unlike the two radios). A stray non-bool
    # payload must not reach a _setBool.
    for key in _SHOW_KEYS:
        assert mod_settings._coerce(key, 0) is False
        assert mod_settings._coerce(key, 1) is True
        assert isinstance(mod_settings._coerce(key, "yes"), bool)
    out = merge_settings(dict((key, 0) for key in _SHOW_KEYS))
    assert out == _defaults_with(dict((key, False) for key in _SHOW_KEYS))
    # ...and a foreign broadcast carrying none of them leaves the user's choice alone.
    mod_settings._seed(_defaults_with({PROGRESS_SHOW_ALWAYS_KEY: True}))
    mod_settings._apply({"someForeignKey": True})
    assert progress_alt_held(False) is True


def test_progress_alt_held_coerces_a_junk_alt_argument():
    # The argument is battle_bridge._alt_held, which is engine-fed; the getter must return a real
    # bool for the _setBool either way.
    mod_settings._seed(dict(DEFAULTS))
    for junk in (None, 0, 1, "", "x", []):
        assert isinstance(progress_alt_held(junk), bool)
    assert progress_alt_held(None) is False
    assert progress_alt_held("x") is True


def test_clamp_variant_max_index_is_per_radio():
    # The generalisation itself: one clamp serves BOTH radios, so its ceiling must come from the
    # ARGUMENT, not from the variant's constant. Today the two ceilings are equal, which is exactly
    # how a hardcoded PROGRESS_VARIANT_EFFICIENCY would pass unnoticed until one radio grows a
    # third option -- so pin the parameter's behaviour directly.
    assert clamp_variant(2, max_index=2) == 2
    assert clamp_variant(2) == 0                    # the default ceiling still rejects it
    assert clamp_variant(3, max_index=2) == 0
    assert clamp_variant(True, max_index=2) == 0    # a bool is illegal at ANY ceiling


# --- the foreign-broadcast bug: a payload with none of our keys must NOT reset us ----------

def test_apply_preserves_current_for_absent_keys():
    # Reproduces the bug: MSA fires our onSettingsChanged for OTHER mods' changes, handing a
    # payload with none of our keys. That must NOT snap our flags back to defaults.
    mod_settings._seed({GARAGE_KEY: True, BATTLE_KEY: False, BATTLE_ALT_KEY: True})
    mod_settings._apply({"showElite": True, "posX": 1920})  # a foreign mod's settings dict
    assert battle_enabled() is False           # preserved, NOT reset to default True
    assert battle_alt_key_enabled() is True     # preserved, NOT reset to default False


def test_apply_overlays_only_present_keys():
    mod_settings._seed({GARAGE_KEY: True, BATTLE_KEY: True, BATTLE_ALT_KEY: False})
    mod_settings._apply({BATTLE_KEY: False})   # only one of our keys present
    assert battle_enabled() is False           # applied
    assert mod_settings.garage_enabled() is True   # untouched
    assert battle_alt_key_enabled() is False       # untouched


def test_apply_ignores_non_dict():
    mod_settings._seed({GARAGE_KEY: True, BATTLE_KEY: False, BATTLE_ALT_KEY: True})
    for junk in (None, "x", 42, [BATTLE_KEY]):
        mod_settings._apply(junk)
        assert battle_enabled() is False and battle_alt_key_enabled() is True


def test_on_changed_ignores_foreign_linkage():
    mod_settings._seed({GARAGE_KEY: True, BATTLE_KEY: False, BATTLE_ALT_KEY: True})
    # A foreign linkage carrying our-looking keys must be ignored entirely.
    mod_settings._on_changed("com.someone.othermod",
                             {BATTLE_KEY: True, BATTLE_ALT_KEY: False})
    assert battle_enabled() is False and battle_alt_key_enabled() is True
    # Our own linkage applies.
    mod_settings._on_changed(LINKAGE, {BATTLE_KEY: True})
    assert battle_enabled() is True


# --- _template() structure (two columns) ---------------------------------------------------
# _template() is buildable game-closed: settings_i18n.panel_text() falls back to English (no
# `helpers`), and _grouped_column1 hits its FALLBACK branch (gui.aslainMenu absent) which is
# exactly the manual masterVarName binding we assert below.

def _varnames(controls):
    return [c["varName"] for c in controls]


def _column_pairs(tmpl):
    """Every ("columnN", settings_i18n.COLN_KEYS) pair the built template actually DECLARES.

    Derived, not restated: a hand-written ("column1", "column2") list is exactly how the
    zip-drift guard below silently stopped covering a third column when the (since reverted)
    one-column-per-feature relayout landed. Deriving it means the next column is covered the
    moment _template() grows it -- and a column added WITHOUT a matching COL*_KEYS tuple fails
    here rather than mis-titling a control at runtime. Deliberately does NOT pin a column
    COUNT: the count is the layout's business, the pairing is ours."""
    cols = sorted(k for k in tmpl if re.match(r"^column\d+$", k))
    assert cols, "the template declares no columns at all"
    out = []
    for col in cols:
        keys = getattr(settings_i18n, "COL%s_KEYS" % col[len("column"):], None)
        assert keys is not None, "%s has no settings_i18n.COL*_KEYS counterpart" % col
        out.append((col, keys))
    return out


def test_template_settings_version_pins_the_current_layout():
    # A STRUCTURAL change must bump this (MSA reuses the stored template until it does), and a
    # bump wipes saved values -- so the exact number is pinned as a tripwire: bumping it is a
    # deliberate act that must come with the migration below, never a drive-by edit. The name
    # deliberately carries no version, only the assertion does.
    # Bumped 7 -> 8 to REVERT the one-column-per-feature relayout: column 3 never rendered
    # in-client and mangled the surrounding layout, so the progress-bar checkbox is back at the
    # end of column 1. Going back to 6 would NOT reach a v7 install (a bump needs new > stored),
    # hence 8. The "Progress Log" rename rides along and stays.
    # Bumped 8 -> 9 for the Progress Bar variant restructure: the checkbox is re-parented as the
    # master of its own group and gains a RadioButtonGroup child (new varName, new control, new
    # nesting). The radio's OPTION LABELS are structural too -- _sync_template_text never
    # rewrites options[].label -- so this bump is the only way they reach an existing install.
    # Bumped 9 -> 10 to drop the variant radio's own "Bar Type" label row (empty text, tooltip
    # removed) so its options read as direct children of the Progress Bar checkbox. Text is NOT in
    # Aslain's _settingsStructure, so the blank label alone would have travelled text-only -- but
    # _sync_template_text can only OVERWRITE text/tooltip, never DELETE the tooltip key (proven
    # below), so a v9 install would keep a stale "Bar Type" tooltip on an invisible row. Only
    # setModTemplate replaces the control wholesale, and only new > stored reaches it: 10, never a
    # revert to 8.
    # Bumped 10 -> 11 for the three-CATEGORY relayout plus a new control, either of which alone
    # would owe it: three bare Label header rows ("Battle Calculator", "Battle Progress", "Garage
    # Widget") shift every following control's POSITION, and the Progress Bar group gains a second
    # RadioButtonGroup child (progress_bar_size -- a new varName, and option labels, which Aslain
    # folds into _settingsStructure). The masters' own labels all became "Show", which is text-only
    # and would have travelled on its own; the rows and the control cannot.
    # Bumped 11 -> 12 for the "Transitions" group: a THIRD grouped master in the Battle Progress
    # category (progress_transitions_enabled) with two label-only children
    # (progress_transitions_events / progress_transitions_manual). THREE new varNames and three new
    # rows at the end of column 1 -- structural twice over, so neither the keys nor the rows can
    # reach an existing install without this forward bump (register()'s saved-truthy path never
    # calls setModTemplate). The migration below carries every saved value across it.
    # Bumped 12 -> 13 for the visibility relayout: three new varNames (the progress_show_* trio),
    # two Empty spacer rows, both radios re-parented out of the Progress Bar group into standalone
    # inline controls, and the variant radio's OPTION ORDER FLIPPED -- option labels are folded
    # into Aslain's _settingsStructure and _sync_template_text never rewrites options[].label, so
    # only a bump carries them. The flip deliberately has NO value migration: the stored raw int
    # rides across unchanged and swaps the user's chosen bar exactly once (accepted).
    # Bumped 13 -> 14 for the category-header bold + column-2 regroup: the four category/group
    # headers now render <b>...</b> with an explicit `useHTML` key, and _sync_template_text only
    # ever rewrites `text`/`tooltip` -- never `useHTML` -- so an existing v13 install would keep
    # rendering them plain forever without this bump. Column 2 also reorders (Follow Carousel moves
    # up under "Layout") and gains a new varName-less "Position" sub-label (COL2_KEYS 7 -> 8). No
    # varName was added/removed/renamed, so the migration branch carries every saved value across.
    assert SETTINGS_VERSION == 14
    assert mod_settings._template()["settingsVersion"] == SETTINGS_VERSION


def test_template_column1_is_two_categories_each_a_label_then_its_group():
    tmpl = mod_settings._template()
    col1 = tmpl["column1"]
    # FIFTEEN controls = TWO CATEGORIES separated by an Empty spacer, each a bare Label header
    # followed by that feature's controls: "Battle Calculator" + [In-Battle master, Alt child,
    # counted-assist child], spacer, then "Battle Progress" + [Progress Bar master + its three
    # VISIBILITY children] + [the two standalone radios] + [Transitions master, Events child, Alt
    # Press child]. The Transitions group is a SECOND group under the SAME category header, so it
    # adds three rows but NO Label -- there are still exactly two headers. The header names the
    # feature, which is why both masters read just "Enabled" (was "Show").
    assert [c["type"] for c in col1] == [
        "Label", "CheckBox", "CheckBox", "CheckBox",
        "Empty",
        "Label", "CheckBox", "CheckBox", "CheckBox", "CheckBox",
        "RadioButtonGroup", "RadioButtonGroup",
        "CheckBox", "CheckBox", "CheckBox"]
    # The varName-bearing controls, in order (a Label header / an Empty spacer has no stored value).
    assert [c["varName"] for c in col1 if "varName" in c] == [
        BATTLE_KEY, BATTLE_ALT_KEY, COUNTED_ASSIST_KEY,
        PROGRESS_BAR_KEY,
        PROGRESS_SHOW_EVENTS_KEY, PROGRESS_SHOW_ALT_KEY, PROGRESS_SHOW_ALWAYS_KEY,
        PROGRESS_VARIANT_KEY, PROGRESS_SIZE_KEY,
        PROGRESS_TRANSITIONS_KEY, PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY]
    # ...and the two category headers carry no varName at all -- and they are the ONLY two, so the
    # Transitions group cannot quietly grow a third header row (it belongs to Battle Progress).
    assert "varName" not in col1[0] and "varName" not in col1[5]
    assert [i for i, c in enumerate(col1) if c["type"] == "Label"] == [0, 5]
    # Both category headers are BOLD: <b>...</b> wrapped text and an explicit useHTML key (MSA's
    # own HTML default is unverified from our side, so we emit it ourselves rather than rely on it).
    assert col1[0]["text"] == u"<b>Battle Calculator</b>" and col1[0]["useHTML"] is True
    assert col1[5]["text"] == u"<b>Battle Progress</b>" and col1[5]["useHTML"] is True
    # The Empty spacer is a bare type and NOTHING else: no varName, and above all no text/tooltip,
    # which is what lets settings_i18n give it a `None` sentinel slot instead of a key.
    assert col1[4] == {"type": "Empty"}
    # ...and still only TWO columns: a third column does not render in the panel at all.
    assert sorted(k for k in tmpl if re.match(r"^column\d+$", k)) == ["column1", "column2"]


def _at(controls, key):
    """The control bearing `key` as its varName, plus its INDEX in the column.

    Named lookups on purpose: the previous pins were `col1[-1]` / `col1[-2]` index literals, and
    appending the size radio silently re-pointed them at the wrong control. A reorder now names
    itself in the failure message instead of retitling a neighbour's assertion."""
    for i, control in enumerate(controls):
        if control.get("varName") == key:
            return control, i
    raise AssertionError("no control with varName %r in %r" % (key, _varnames_loose(controls)))


def _varnames_loose(controls):
    return [c.get("varName", "(label)") for c in controls]


def test_template_variant_radio_shape(monkeypatch):
    # The descriptor must match what Aslain's templates.createRadioButtonGroup emits (we build it
    # by hand to keep _template() import-free): a 0-based INT index in `value` and an `options`
    # list of {"label": ...} dicts in index order, localized via settings_i18n.
    col1 = mod_settings._template()["column1"]
    radio, index = _at(col1, PROGRESS_VARIANT_KEY)
    # POSITION, named rather than an index literal buried in a longer assertion: the Mode radio
    # follows the LAST visibility child and the Scale radio follows it, so the pair's order is what
    # _sync_template_text's positional zip walks.
    assert index == _at(col1, PROGRESS_SHOW_ALWAYS_KEY)[1] + 1
    assert index + 1 == _at(col1, PROGRESS_SIZE_KEY)[1]
    assert radio["type"] == "RadioButtonGroup"
    assert radio["varName"] == PROGRESS_VARIANT_KEY
    assert radio["value"] == DEFAULTS[PROGRESS_VARIANT_KEY] == 0
    assert not isinstance(radio["value"], bool)
    # THE v13 OPTION ORDER: index 0 is Damage Efficiency, and the wire order must match
    # mod_settings' own constants or the panel and the window picker disagree.
    assert [o["label"] for o in radio["options"]] == ["Damage Efficiency", "Moving Average"]
    assert radio["options"][PROGRESS_VARIANT_EFFICIENCY]["label"] == "Damage Efficiency"
    assert radio["options"][PROGRESS_VARIANT_MOVING_AVERAGE]["label"] == "Moving Average"
    # `inline` is emitted as a plain KEY (one horizontal row), never through
    # createRadioButtonGroup's kwarg of the same name -- that kwarg raises TypeError on
    # MSA < 1.6.1, an unknown key just rides through (MSA validates no descriptor).
    assert radio["inline"] is True
    # It DOES carry a label now ("Mode"), unlike the label-less row it used to be.
    assert radio["text"] == u"Mode"
    # ...and no tooltip: the two option labels say it all, and _radio omits the key rather than
    # emitting u"" (an empty tooltip is still a tooltip to the panel, and one written into a
    # stored template can never be removed again).
    assert "tooltip" not in radio
    master = _at(col1, PROGRESS_BAR_KEY)[0]
    assert u"Moving Average" in master["tooltip"]
    assert u"Damage Efficiency" in master["tooltip"]
    # LOCALIZED, not hardcoded here. The old `== list(settings_i18n.variant_options(u"en"))` line
    # was dropped rather than re-pointed at build(): comparing against build()'s own output can
    # never fail where the English literal above passes (they move together, and a hardcoded list
    # in _radio would MATCH build's English), so it was strictly weaker than the literal it sat
    # beside. This is the claim it was reaching for and the one that mutation-probes: swap the
    # source tuple and the descriptor must follow.
    monkeypatch.setitem(settings_i18n._VARIANT_OPTIONS, u"en", (u"AAA", u"BBB"))
    fresh = _at(mod_settings._template()["column1"], PROGRESS_VARIANT_KEY)[0]
    assert [o["label"] for o in fresh["options"]] == [u"AAA", u"BBB"], \
        "the radio's options are not read from settings_i18n"


def test_template_size_radio_shape(monkeypatch):
    # The SECOND options-bearing control, and the second non-bool value. Same hand-built
    # RadioButtonGroup shape as the variant's, and the same three traps -- an INT index in `value`
    # (never a bool), `inline` emitted as a KEY and never as createRadioButtonGroup's kwarg
    # (TypeError on MSA < 1.6.1), and LOCALIZED options read off settings_i18n rather than
    # hardcoded in _radio.
    col1 = mod_settings._template()["column1"]
    radio, index = _at(col1, PROGRESS_SIZE_KEY)
    # POSITION, anchored to NAMED neighbours rather than to a length: the Scale radio is the last
    # control before the Transitions master, and the Transitions group is the contiguous THREE-row
    # tail of the column. So an insertion anywhere in between (which shifts every later control's
    # text -- COL1_KEYS' zip is positional) still fails here, while a legitimate append does not.
    assert index + 1 == _at(col1, PROGRESS_TRANSITIONS_KEY)[1], \
        "a control was inserted between the Scale radio and the Transitions master"
    assert [c.get("varName") for c in col1[-3:]] == [
        PROGRESS_TRANSITIONS_KEY, PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY], \
        "the Transitions group is no longer the column-1 tail (COL1_KEYS' zip is positional)"
    assert radio["type"] == "RadioButtonGroup"
    assert radio["value"] == DEFAULTS[PROGRESS_SIZE_KEY] == 0
    assert not isinstance(radio["value"], bool)
    assert [o["label"] for o in radio["options"]] == ["Default", "Large"]
    assert radio["inline"] is True
    # A label ("Scale") but still no tooltip: the two option labels say it all, and _radio omits
    # the key rather than emitting u"" (an empty tooltip is still a tooltip to the panel).
    assert radio["text"] == u"Scale"
    assert "tooltip" not in radio
    monkeypatch.setitem(settings_i18n._SIZE_OPTIONS, u"en", (u"AAA", u"BBB"))
    fresh = _at(mod_settings._template()["column1"], PROGRESS_SIZE_KEY)[0]
    assert [o["label"] for o in fresh["options"]] == [u"AAA", u"BBB"], \
        "the size radio's options are not read from settings_i18n"


def test_checkbox_tolerates_a_label_only_row_and_omits_the_tooltip_key():
    # REGRESSION. _checkbox hard-indexed rendered["tooltip"] and raised KeyError on the first
    # label-only CheckBox -- which the Transitions group's "Events" / "Manual" children are
    # (one-word
    # switches whose meaning the master's tooltip spells out). It blew up inside _template(), i.e.
    # register()'s guarded try, so the live failure mode was a client with NO settings panel at all
    # and a single logged traceback. Drive the helper directly with a tipless rendered row, the
    # exact
    # shape settings_i18n._render() returns for a `_row(u"Events")`.
    control = mod_settings._checkbox(PROGRESS_TRANS_EVENTS_KEY, {"text": u"Events"})
    assert control["text"] == u"Events"
    assert control["varName"] == PROGRESS_TRANS_EVENTS_KEY
    assert control["value"] == DEFAULTS[PROGRESS_TRANS_EVENTS_KEY]
    # OMITTED, not emitted empty -- same shape as _radio / _label. An empty tooltip is still a
    # tooltip to the panel, and a tooltip written into a stored template can never be removed again
    # (_sync_template_text only overwrites), so u"" would cost a later settingsVersion bump.
    assert "tooltip" not in control
    assert "tooltip" not in mod_settings._checkbox(PROGRESS_TRANS_MANUAL_KEY,
                                                  {"text": u"Manual", "tooltip": u""})
    # ...and a row that HAS one still carries it.
    assert mod_settings._checkbox(GARAGE_KEY, {"text": u"L", "tooltip": u"T"})["tooltip"] == u"T"
    # _stepper is the FIFTH descriptor helper and the last one that still hard-indexed
    # rendered["tooltip"]. Both steppers carry a tooltip today, so no built-template assertion can
    # reach the branch -- drive the helper directly, or the hard index comes back unnoticed and the
    # first tipless position row kills the whole panel again (mutation-probed: reverting _stepper to
    # the hard index left the entire suite green).
    assert "tooltip" not in mod_settings._stepper(POS_X_KEY, {"text": u"X"})
    assert mod_settings._stepper(POS_Y_KEY, {"text": u"Y", "tooltip": u"T"})["tooltip"] == u"T"
    # End to end: the two real children in the built template are tipless, the master is not.
    col1 = mod_settings._template()["column1"]
    for child_key in (PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY):
        assert "tooltip" not in _at(col1, child_key)[0], \
            "%s grew a tooltip -- it is a label-only row" % child_key
    assert _at(col1, PROGRESS_TRANSITIONS_KEY)[0]["tooltip"], \
        "the Transitions master lost the tooltip that is the group's only prose"


def test_label_emits_usehtml_by_key_and_never_touches_the_text():
    # _label no longer wraps text itself -- settings_i18n.build() does that wrap, ONCE, for every
    # key in HEADER_KEYS (see that function's docstring for why: a second wrap here would make
    # _template() and _sync_template_text() disagree on every register() call, including the one
    # that just built the freshly-bolded template, and the sync would strip the bold back out).
    # _label only decides useHTML off the KEY and passes rendered["text"] straight through -- drive
    # it directly (not just through the built template) so a regression here cannot hide behind a
    # template-level assertion that only checks ONE of the two headers.
    plain = mod_settings._label("positionSub", {"text": u"Layout", "tooltip": u"T"})
    assert plain["text"] == u"Layout"
    assert "useHTML" not in plain
    # A HEADER_KEYS key gets useHTML regardless of what its text looks like -- _label does not
    # inspect or wrap the text, it only reads the key.
    bold = mod_settings._label("catGarage", {"text": u"<b>Layout</b>", "tooltip": u"T"})
    assert bold["text"] == u"<b>Layout</b>"
    assert bold["useHTML"] is True
    assert bold["tooltip"] == u"T"
    # A tipless header row still omits the tooltip key (same shape as the plain path).
    tipless_bold = mod_settings._label("positioning", {"text": u"<b>Position</b>"})
    assert "tooltip" not in tipless_bold
    assert tipless_bold["text"] == u"<b>Position</b>" and tipless_bold["useHTML"] is True


def test_template_column2_is_the_garage_category_then_the_layout_group():
    # Column 2 = the "Garage Widget" category header, the garage master ("Enabled"), an Empty
    # spacer, then the "Layout" group: its BOLD Label header (no varName), Follow Carousel, a
    # non-bold "Position" sub-label, then the X/Y numeric steppers.
    col2 = mod_settings._template()["column2"]
    assert [c["type"] for c in col2] == [
        "Label", "CheckBox", "Empty", "Label", "CheckBox", "Label",
        "NumericStepper", "NumericStepper"]
    # The varName-bearing controls, in order (a Label header / Empty spacer has no stored value).
    assert [c["varName"] for c in col2 if "varName" in c] == [
        GARAGE_KEY, FOLLOW_CAROUSEL_KEY, POS_X_KEY, POS_Y_KEY]
    # THREE Label rows carry no varName. The CATEGORY header and the "Layout" header are both BOLD
    # (<b> wrap + explicit useHTML) and the category header stays TIPLESS (a bare feature name has
    # nothing to explain) while "Layout" keeps its tooltip; "Position" is neither bold nor
    # tooltipped -- the weight difference alone marks it as a sub-level under "Layout". _label()
    # emits the tooltip key only when there IS one and the useHTML key only when bold -- see the
    # tipless counter in test_sync_template_text_walks_built_template_in_lockstep.
    assert "varName" not in col2[0] and "tooltip" not in col2[0]
    assert col2[0]["text"] == u"<b>Garage Widget</b>"
    assert col2[0]["useHTML"] is True
    assert col2[2] == {"type": "Empty"}
    assert "varName" not in col2[3] and col2[3]["tooltip"]
    assert col2[3]["text"] == u"<b>Layout</b>"
    assert col2[3]["useHTML"] is True
    assert "varName" not in col2[5] and "tooltip" not in col2[5]
    assert col2[5]["text"] == u"Position"
    assert "useHTML" not in col2[5]


def test_template_steppers_are_bounded_manual_entry():
    # Each position stepper spans [0, POS_MAX], allows manual input and steps by 1 px so a
    # typed 0 returns the widget to auto and a nudge isn't rounded away.
    col2 = mod_settings._template()["column2"]
    steppers = [c for c in col2 if c["type"] == "NumericStepper"]
    assert [c["varName"] for c in steppers] == [POS_X_KEY, POS_Y_KEY]
    for s in steppers:
        assert s["minimum"] == 0
        assert s["maximum"] == POS_MAX
        assert s["canManualInput"] is True
        assert s["snapInterval"] == 1


def test_template_children_bind_to_their_own_master_only():
    # Each group's children carry masterVarName == THEIR master's varName so MSA groups + greys
    # them out under it. Proven via the manual-binding fallback branch (no gui.aslainMenu under
    # pytest -- see _grouped_column1).
    col1 = mod_settings._template()["column1"]
    master = _at(col1, BATTLE_KEY)[0]
    alt_child = _at(col1, BATTLE_ALT_KEY)[0]
    counted_child = _at(col1, COUNTED_ASSIST_KEY)[0]
    progress = _at(col1, PROGRESS_BAR_KEY)[0]
    variant = _at(col1, PROGRESS_VARIANT_KEY)[0]
    size = _at(col1, PROGRESS_SIZE_KEY)[0]
    assert alt_child["masterVarName"] == BATTLE_KEY
    assert counted_child["masterVarName"] == BATTLE_KEY
    # Neither master is bound to anything: the Progress Bar is an independent feature and must
    # stay togglable while the In-Battle master is OFF. That is why it gets its OWN
    # _grouped_column1 call instead of being passed into the In-Battle group as a third child --
    # a grouped child inherits THAT master's varName and MSA greys it out with it, which would
    # tie the progress bar to the unrelated In-Battle Widget.
    assert "masterVarName" not in master
    assert progress["varName"] == PROGRESS_BAR_KEY
    assert "masterVarName" not in progress
    # ...and BOTH radios are deliberately STANDALONE since v13: Mode and Scale describe the bar
    # itself, not when it shows, so they carry no master and no condition at all -- the same call
    # already made for the column-2 steppers. (A child of the FIRST group would have inherited
    # BATTLE_KEY and greyed out with the unrelated In-Battle Widget; that hazard is why this is
    # asserted rather than assumed.)
    for radio in (variant, size):
        assert "masterVarName" not in radio and "conditions" not in radio, \
            "%s gained a gate -- both radios are deliberately standalone" % radio["varName"]
    # The THREE VISIBILITY children. "Always" is a plain child of the Progress Bar master...
    always = _at(col1, PROGRESS_SHOW_ALWAYS_KEY)[0]
    assert always["masterVarName"] == PROGRESS_BAR_KEY
    assert "conditions" not in always
    # ...while "Events" and "Alt Press" are dead in TWO ways -- with the bar off and with "Always"
    # on -- so they carry MSA's multi-condition AND form instead. That form does NOT set
    # masterVarName, so it REPLACES the group parenting: the master has to ride along as one of the
    # conditions, and the stale key must be gone or the panel reads a parent the gate ignores.
    for key in (PROGRESS_SHOW_EVENTS_KEY, PROGRESS_SHOW_ALT_KEY):
        child = _at(col1, key)[0]
        assert "masterVarName" not in child, \
            "%s kept a masterVarName the `conditions` form supersedes" % key
        assert child["conditionsLogic"] == "AND"
        assert child["masterIndent"] is True
        assert child["conditions"] == [
            {"masterVarName": PROGRESS_BAR_KEY, "condition": "==", "masterValue": True},
            {"masterVarName": PROGRESS_SHOW_ALWAYS_KEY, "condition": "==",
             "masterValue": False}], \
            "%s lost the group master from its AND gate (or the peer/values drifted)" % key
    # ...and the THIRD group, Transitions, is bound the same way: its own master carries NO
    # masterVarName (it is a master, and it must stay togglable while the Progress Bar checkbox is
    # off) and both children point at IT, never at PROGRESS_BAR_KEY. This is the exact thing that
    # breaks silently if someone re-parents the splice -- passing these two as children of the
    # PROGRESS BAR group would grey them out with the bar, and the panel would look plausible while
    # the binding was wrong.
    trans = _at(col1, PROGRESS_TRANSITIONS_KEY)[0]
    assert "masterVarName" not in trans, \
        "the Transitions master was re-parented -- it is a group MASTER, not a child"
    for child_key in (PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY):
        child = _at(col1, child_key)[0]
        assert child["masterVarName"] == PROGRESS_TRANSITIONS_KEY, \
            "%s is gated by %r, not by the Transitions master" % (
                child_key, child.get("masterVarName"))
        assert child["masterVarName"] != PROGRESS_BAR_KEY
        assert child["masterVarName"] != BATTLE_KEY
    # The position steppers and Follow Carousel stay STANDALONE: they must keep working, and stay
    # ungreyed, while the garage widget is off (that is a deliberate decision, not an oversight).
    # `conditions` is checked too -- it is the OTHER way a control can acquire a gate now.
    for control in mod_settings._template()["column2"]:
        assert "masterVarName" not in control and "conditions" not in control, \
            "%s gained a master -- column 2 is deliberately flat" % control.get("varName")


def test_template_control_defaults_match_defaults_dict():
    # Each value-bearing control's initial `value` mirrors its DEFAULTS entry (varName ==
    # DEFAULTS key). Label headers and Empty spacers carry no varName/value and are skipped.
    # Covers the checkboxes, both radios and the numeric steppers (steppers default to 0 = auto),
    # across EVERY column.
    tmpl = mod_settings._template()
    for col, _keys in _column_pairs(tmpl):
        for c in tmpl[col]:
            if "varName" not in c:            # a Label header / an Empty spacer
                assert c["type"] in ("Label", "Empty")
                continue
            assert c["type"] in ("CheckBox", "NumericStepper", "RadioButtonGroup")
            assert c["value"] == DEFAULTS[c["varName"]]


def test_grouped_column1_uses_aslain_helper_when_present(monkeypatch):
    # When Aslain's templates.createControlsGroup exists, _grouped_column1 delegates to it
    # (master, children, indent=True) instead of the manual fallback.
    calls = {}

    def _fake_group(master, children, indent=False):
        calls["args"] = (master, list(children), indent)
        return ["GROUPED", master] + list(children)

    fake_templates = types.ModuleType("gui.aslainMenu.templates")
    fake_templates.createControlsGroup = _fake_group
    fake_aslain = types.ModuleType("gui.aslainMenu")
    fake_aslain.templates = fake_templates
    fake_gui = types.ModuleType("gui")
    fake_gui.aslainMenu = fake_aslain
    monkeypatch.setitem(sys.modules, "gui", fake_gui)
    monkeypatch.setitem(sys.modules, "gui.aslainMenu", fake_aslain)
    monkeypatch.setitem(sys.modules, "gui.aslainMenu.templates", fake_templates)

    master = {"varName": BATTLE_KEY}
    children = [{"varName": BATTLE_ALT_KEY}, {"varName": COUNTED_ASSIST_KEY}]
    out = mod_settings._grouped_column1(master, children)
    assert out[0] == "GROUPED"                      # the helper's return is used verbatim
    assert calls["args"] == (master, children, True)  # called with indent=True
    # The helper owns the binding, so we did NOT set masterVarName by hand here.
    assert "masterVarName" not in children[0]


# --- COL*_KEYS stay in lockstep with the built template order (so _sync_template_text walks
# the stored template correctly) -----------------------------------------------------------

def test_col_keys_lockstep_with_template_order():
    # _sync_template_text zips tmpl[col] with settings_i18n.COL*_KEYS and writes panel_text()[key]
    # onto each control. That only lands text on the right control if the built template's column
    # order matches the key tuples. Prove it: each control's rendered text == panel_text()[key]
    # VERBATIM -- a HEADER_KEYS control's text already arrives <b>...</b>-wrapped from
    # settings_i18n.build() (see HEADER_KEYS), and _label() passes it straight through rather than
    # wrapping it again, so _template() and panel_text() must agree byte-for-byte with NO extra
    # wrap applied here (a second wrap is exactly the double-wrap bug -- see
    # test_build_then_sync_preserves_header_bold).
    tmpl = mod_settings._template()
    text = settings_i18n.panel_text()
    sentinels = 0
    for col, keys in _column_pairs(tmpl):
        controls = tmpl[col]
        assert len(controls) == len(keys), (
            "%s length drifted from COL keys" % col)
        for control, key in zip(controls, keys):
            if key is None:
                # The text-less sentinel slot -- and it must line up with a control that genuinely
                # HAS no text, or the sentinel is hiding a real control from the sync walk.
                assert control["type"] == "Empty"
                assert "text" not in control and "tooltip" not in control
                sentinels += 1
                continue
            assert control["text"] == text[key]["text"]
            assert control.get("tooltip") == text[key].get("tooltip")
    # ...and every Empty in the template is covered by one: a spacer added without a sentinel would
    # shift the whole tail of the zip and silently retitle every control after it.
    assert sentinels == sum(1 for col, _k in _column_pairs(tmpl)
                            for c in tmpl[col] if c["type"] == "Empty") == 2


def test_sync_template_text_walks_built_template_in_lockstep():
    # End-to-end for the sync path: build a stored template exactly as register() would, drift
    # EVERY column's control text, then _sync_template_text must restore each to panel_text()[key]
    # -- proving the COL*_KEYS walk lands the right string on the right control.
    #
    # Drifting EVERY column _template() declares (not a hand-listed subset) is what proves
    # _sync_template_text's OWN pair list covers them all: that pair list is the only thing that
    # carries a text change -- e.g. the "Next Mark Progress Bar" -> "Progress Log" rename, or a
    # client-language switch -- to an EXISTING install, because MSA renders from the template
    # COPY it cached at registration. Miss a column there and an upgrader keeps reading the old
    # label forever (it went stale once already, when a third column was added and then dropped).
    tmpl = mod_settings._template()
    columns = _column_pairs(tmpl)
    for col, _keys in columns:
        for c in tmpl[col]:
            c["text"] = u"STALE"
            c["tooltip"] = u"STALE"
    saved = {"called": False}

    class _FakeApi(object):
        state = {"templates": {LINKAGE: tmpl}}

        def saveState(self):
            saved["called"] = True

    mod_settings._sync_template_text(_FakeApi())
    text = settings_i18n.panel_text()
    tipless = 0
    spacers = 0
    for col, keys in columns:
        for control, key in zip(tmpl[col], keys):
            if key is None:
                # An Empty spacer's sentinel slot. The sync walk must leave it ALONE -- it has no
                # text to refresh, and writing one would put a stray label in the panel. No code
                # branch does this: `t.get(None)` is falsy, so the existing `if not rendered`
                # guard already skips it, which is exactly why the sentinel was chosen over a
                # type-sniffing skip.
                assert control["text"] == u"STALE" and control["tooltip"] == u"STALE"
                spacers += 1
                continue
            assert control["text"] == text[key]["text"], (
                "%s/%s kept its STALE text -- is the column missing from "
                "_sync_template_text's pair list?" % (col, key))
            tip = text[key].get("tooltip")
            if tip is not None:
                assert control["tooltip"] == tip
            else:
                # A control with NO tooltip keeps whatever the stored template held: the sync path
                # only ever OVERWRITES text/tooltip, it never deletes a key. That gap is precisely
                # why removing the variant radio's "Bar Type" label needed a settingsVersion bump
                # (setModTemplate replaces the control wholesale) rather than riding the text-only
                # path -- and it is the reason _label() now OMITS the tooltip key on a tipless row
                # instead of emitting u"": an empty tooltip written into a stored template could
                # never be removed again.
                assert control["tooltip"] == u"STALE"
                tipless += 1
    # EIGHT tipless controls: the three bare CATEGORY headers (Battle Calculator / Battle Progress /
    # Garage Widget -- a feature name has nothing to explain and nothing to hover), BOTH radios
    # (Mode / Scale -- their option labels say it all), the Transitions group's two children
    # (Events / Alt Press) -- one-word switches whose meaning the Transitions master's tooltip
    # spells out -- and the new "Position" sub-label (heads the two steppers; the weight
    # difference from "Layout" above it is its only distinguishing mark, so it carries no tooltip
    # either). The Progress Bar group's three VISIBILITY children (Events / Alt Press / Always)
    # used to be label-only too (bringing the count to TEN), but each now carries its own tooltip,
    # so they dropped OUT of this count -- see settings_i18n's progressShowEvents/Alt/Always. The
    # counter is the tripwire that surfaced the _label tooltip hole in the first place, and it is
    # what caught the SAME hole in _checkbox: the Transitions children were the first tipless
    # CHECKBOXES, and _checkbox hard-indexed rendered["tooltip"], so building the template raised
    # KeyError before this walk was even reached. Keep it exact rather than a `>= 1`, because a NEW
    # tipless row is exactly the change that owes a bump.
    assert tipless == 8, "expected 8 tooltip-less controls, got %d" % tipless
    # ...and both Empty spacers were walked and left untouched (see the sentinel branch above).
    assert spacers == 2, "expected 2 text-less spacer rows, got %d" % spacers
    assert saved["called"] is True   # something changed -> state persisted


def test_build_then_sync_preserves_header_bold():
    # REGRESSION for the double-wrap bug: settings_i18n.build() and mod_settings._label() used to
    # BOTH wrap a header's text in <b>...</b> -- _label wrapped it into the built template, but
    # panel_text() (== build()) returned the PLAIN string, so _sync_template_text -- which runs on
    # EVERY register() call, including the one that just built the freshly-bolded template -- saw
    # comp["text"] ("<b>Battle Calculator</b>") disagree with panel_text()[key]["text"]
    # ("Battle Calculator"), overwrote the bold back out, and saved. useHTML was never touched, so
    # it dangled True on now-plain text.
    #
    # The lockstep test above does NOT catch this: it STALES every control's text before syncing,
    # which always converges on panel_text() regardless of whether _template()'s own build and
    # panel_text() agree with EACH OTHER. This test skips the staling step and instead runs the
    # sync immediately against a template built the way register() actually builds one -- a
    # control whose OWN build disagrees with panel_text() fails here even though the built
    # template already "looks bold".
    tmpl = mod_settings._template()
    text = settings_i18n.panel_text()

    class _FakeApi(object):
        state = {"templates": {LINKAGE: tmpl}}

        def saveState(self):
            pass

    mod_settings._sync_template_text(_FakeApi())

    for col, keys in _column_pairs(tmpl):
        for control, key in zip(tmpl[col], keys):
            if key not in settings_i18n.HEADER_KEYS:
                continue
            assert control["text"] == text[key]["text"], (
                "%s/%s's synced text no longer matches panel_text()" % (col, key))
            assert control["text"].startswith(u"<b>") and control["text"].endswith(u"</b>"), (
                "%s/%s lost its bold across a build-then-sync round trip" % (col, key))
            assert control.get("useHTML") is True


# --- drag-to-reposition: clamp_pos, accessors, set_position, follow_carousel, reset --------

def test_clamp_pos_bounds():
    # 0 = auto/unseeded; negatives and non-numeric collapse to 0; over-ceiling clamps down.
    assert clamp_pos(0) == 0
    assert clamp_pos(-1) == 0
    assert clamp_pos(-9999) == 0
    assert clamp_pos(123) == 123
    assert clamp_pos(POS_MAX) == POS_MAX
    assert clamp_pos(POS_MAX + 1) == POS_MAX
    assert clamp_pos(10 ** 9) == POS_MAX
    # Non-numeric / None -> 0 (a bad measurement never pins).
    assert clamp_pos(None) == 0
    assert clamp_pos("abc") == 0
    assert clamp_pos([1, 2]) == 0
    # Numeric strings / floats coerce through int().
    assert clamp_pos("640") == 640
    assert clamp_pos(360.9) == 360


def test_position_accessors_round_trip():
    mod_settings._seed(dict(DEFAULTS))
    # Auto default: every coordinate 0.
    assert (pos_x(), pos_y(), pos_w(), pos_h()) == (0, 0, 0, 0)
    mod_settings._apply({POS_X_KEY: 640, POS_Y_KEY: 360, POS_W_KEY: 2560, POS_H_KEY: 1440})
    assert pos_x() == 640
    assert pos_y() == 360
    assert pos_w() == 2560
    assert pos_h() == 1440


def test_position_accessors_clamp_a_bad_stored_value():
    # A getter re-clamps whatever is cached, so a corrupt store never leaks a bad px out.
    mod_settings._seed(dict(DEFAULTS))
    mod_settings._settings[POS_X_KEY] = -50
    mod_settings._settings[POS_Y_KEY] = POS_MAX + 500
    assert pos_x() == 0
    assert pos_y() == POS_MAX


def test_follow_carousel_default_true_and_getter():
    mod_settings._seed(dict(DEFAULTS))
    assert follow_carousel() is True
    mod_settings._apply({FOLLOW_CAROUSEL_KEY: False})
    assert follow_carousel() is False
    mod_settings._apply({FOLLOW_CAROUSEL_KEY: 1})   # coerced to bool
    assert follow_carousel() is True


class _FakeMsa(object):
    """A stand-in ModsSettingsAPI sink: returns a stored dict from getModSettings and records
    the full dict written by updateModSettings + whether saveState flushed it."""
    def __init__(self, current):
        self._current = current
        self.written = None
        self.saved = False

    def getModSettings(self, linkage, template):
        return dict(self._current)

    def updateModSettings(self, linkage, data):
        self.written = data

    def saveState(self):
        self.saved = True


def test_set_position_writes_full_dict_preserving_enabled(monkeypatch):
    # set_position must write the WHOLE settings dict (MSA replace-not-merge) and preserve the
    # host-managed 'enabled' toggle + any foreign host keys, then flush with saveState().
    mod_settings._seed(dict(DEFAULTS))
    fake = _FakeMsa({"enabled": False, "someHostKey": 7})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)

    set_position(100, 200, 1920, 1080)

    assert fake.saved is True                 # persisted to disk
    data = fake.written
    assert data is not None
    # host keys preserved (not clobbered by our partial write)
    assert data["enabled"] is False
    assert data["someHostKey"] == 7
    # our position coords written
    assert data[POS_X_KEY] == 100
    assert data[POS_Y_KEY] == 200
    assert data[POS_W_KEY] == 1920
    assert data[POS_H_KEY] == 1080
    # the FULL flag set is present too (replace-not-merge -> nothing of ours dropped)
    for key in DEFAULTS:
        assert key in data
    # live cache + accessors reflect the new pin
    assert (pos_x(), pos_y(), pos_w(), pos_h()) == (100, 200, 1920, 1080)


def test_set_position_adds_enabled_when_host_omits_it(monkeypatch):
    # If the stored dict lacks 'enabled', the write must still guarantee it (a missing
    # 'enabled' blanks Aslain's whole panel).
    mod_settings._seed(dict(DEFAULTS))
    fake = _FakeMsa({})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)
    set_position(10, 20)
    assert fake.written["enabled"] is True


def test_set_position_clamps_and_survives_absent_msa(monkeypatch):
    # No MSA present -> the position still applies this session (cache + accessors), just not
    # persisted; negative/oversized inputs are clamped on the way in.
    mod_settings._seed(dict(DEFAULTS))
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: None)
    set_position(-5, POS_MAX + 100, w=1920, h=1080)
    assert pos_x() == 0                 # clamped
    assert pos_y() == POS_MAX           # clamped
    assert pos_w() == 1920
    assert pos_h() == 1080


def test_on_reset_forces_auto_position_and_follow_on():
    # The per-mod Reset must snap the position back to auto (0/0/0/0) and Follow Carousel Mode
    # back ON, overriding any stale pin the host reset snapshot may still carry.
    mod_settings._seed({GARAGE_KEY: True, BATTLE_KEY: True,
                        POS_X_KEY: 500, POS_Y_KEY: 300, POS_W_KEY: 1920, POS_H_KEY: 1080,
                        FOLLOW_CAROUSEL_KEY: False})
    mod_settings._on_reset(LINKAGE, {POS_X_KEY: 999, POS_Y_KEY: 888,
                                     FOLLOW_CAROUSEL_KEY: False})
    assert (pos_x(), pos_y(), pos_w(), pos_h()) == (0, 0, 0, 0)
    assert follow_carousel() is True


def test_on_reset_ignores_foreign_linkage():
    # onResetMod fires globally; a foreign mod's reset must not wipe our pin / follow flag.
    mod_settings._seed({GARAGE_KEY: True, BATTLE_KEY: True,
                        POS_X_KEY: 500, POS_Y_KEY: 300,
                        FOLLOW_CAROUSEL_KEY: False})
    mod_settings._on_reset("com.someone.othermod", {})
    assert pos_x() == 500
    assert pos_y() == 300
    assert follow_carousel() is False


def test_coerce_types_per_key():
    # Position keys coerce to clamped ints, the progress-bar variant AND size to clamped radio
    # indices (see test_coerce_variant_key_is_not_booled / test_coerce_size_key_is_not_booled),
    # every other key to bool. Both radios are named here so a key that loses its branch fails on
    # THIS test too, not only on its own.
    assert mod_settings._coerce(POS_X_KEY, "640") == 640
    assert mod_settings._coerce(POS_Y_KEY, -3) == 0
    assert mod_settings._coerce(GARAGE_KEY, 0) is False
    assert mod_settings._coerce(FOLLOW_CAROUSEL_KEY, 1) is True
    assert mod_settings._coerce(PROGRESS_VARIANT_KEY, 1) is not True
    assert mod_settings._coerce(PROGRESS_SIZE_KEY, 1) is not True


# --- settingsVersion-bump migration: preserve saved values across a register() bump ---------

class _FakeMsaApi(object):
    """Models Aslain MSA's settingsVersion-bump behavior for the migration path.

    getModSettings returns None while the template's settingsVersion exceeds the stored one
    (the wipe path register()'s else-branch reacts to); once setModTemplate records the new
    version it returns the current stored dict. setModTemplate resets the stored dict to the
    template's varName defaults (preserving the host-owned 'enabled' toggle) and returns them.
    The raw previously-stored values live at .state['settings'][LINKAGE] until setModTemplate
    overwrites them."""

    def __init__(self, stored=None, stored_version=0):
        settings = {LINKAGE: dict(stored)} if stored is not None else {}
        self.state = {"settings": settings, "templates": {}}
        self._stored_version = stored_version
        self.saved = 0
        self.updated = 0
        self.registered_cb = None
        self.template_cb = None

    # The host walks a FIXED column1..column4 (Aslain MSA _constants.py:33), NOT just the columns
    # this mod happens to use -- so the fake walks all four too. Do NOT trim this to the two we
    # currently ship: restating our own column list is how the fake would quietly stop collecting
    # a control's default the moment the layout moves it to another column, making the migration
    # test below vacuous (exactly what a hand-listed pair did during the column-3 detour).
    _COLUMNS = ("column1", "column2", "column3", "column4")

    @classmethod
    def _defaults_from_template(cls, template):
        d = {}
        for col in cls._COLUMNS:
            for c in template.get(col, []):
                if "varName" in c:
                    d[c["varName"]] = c.get("value")
        d["enabled"] = template.get("enabled", True)
        return d

    def getModSettings(self, linkage, template=None):
        cur = (self.state.get("settings") or {}).get(linkage)
        if cur is None:
            return None
        if template is not None and template.get("settingsVersion", 0) > self._stored_version:
            return None
        return cur

    def setModTemplate(self, linkage, template, callback):
        self.template_cb = callback
        defaults = self._defaults_from_template(template)
        prev = (self.state.get("settings") or {}).get(linkage) or {}
        if "enabled" in prev:
            defaults["enabled"] = prev["enabled"]
        self.state.setdefault("settings", {})[linkage] = defaults
        self._stored_version = template.get("settingsVersion", 0)
        return defaults

    def registerCallback(self, linkage, callback):
        self.registered_cb = callback

    def updateModSettings(self, linkage, data):
        self.updated += 1
        self.state.setdefault("settings", {})[linkage] = dict(data)

    def saveState(self):
        self.saved += 1


@pytest.fixture
def _run_register(monkeypatch):
    """Run register() against a fake api: patch _primary_api to it, neutralize the
    reset/text-sync loops (out of scope for migration), reset the one-shot _registered guard,
    and restore it after."""
    saved_registered = mod_settings._registered

    def _run(api):
        monkeypatch.setattr(mod_settings, "_primary_api", lambda: api)
        monkeypatch.setattr(mod_settings, "_candidate_apis", lambda: [])
        mod_settings._registered = False
        mod_settings.register()

    yield _run
    mod_settings._registered = saved_registered


def test_migration_preserves_user_values_drops_removed_key_and_seeds_new_default(_run_register):
    # Old v4 dict with non-default checkbox choices, a legacy key removed from the template,
    # and none of the v5 position keys -> migration must keep the survivors, drop the legacy
    # key, and leave the new position/followCarousel keys at their fresh defaults.
    old = {
        "enabled": True,
        GARAGE_KEY: False,
        BATTLE_KEY: False,
        BATTLE_ALT_KEY: True,
        COUNTED_ASSIST_KEY: True,
        "legacyGoneVarName": 7,
    }
    api = _FakeMsaApi(stored=old, stored_version=4)
    _run_register(api)

    assert mod_settings.garage_enabled() is False
    assert mod_settings.battle_enabled() is False
    assert mod_settings.battle_alt_key_enabled() is True
    assert mod_settings.counted_assistance_enabled() is True
    # New-to-v5 keys were absent from the old dict -> fresh defaults.
    assert mod_settings.pos_x() == 0 and mod_settings.pos_y() == 0
    assert mod_settings.follow_carousel() is True
    # ...and so is the new-to-v6 progress-bar key (opt-in stays off across the bump) and the
    # variant index, which lands on the v13 index-0 default (Damage Efficiency).
    assert mod_settings.progress_bar_enabled() is False
    assert mod_settings.progress_bar_variant() == PROGRESS_VARIANT_EFFICIENCY
    # ...and the new-to-v11 size index (the shipped size, so nobody's bar grows on update).
    assert mod_settings.progress_bar_size() == PROGRESS_SIZE_DEFAULT
    # ...and the three new-to-v12 transitions keys (True = animated, which is what shipped, so an
    # existing user's bar keeps moving exactly as it did).
    assert progress_transitions_events() is True
    assert progress_transitions_manual() is True
    # ...and the three new-to-v13 VISIBILITY keys, whose fresh defaults reproduce the pre-v13
    # unconditional triggers: an event raises the bar, Alt peeks it, nothing is pinned.
    assert progress_show_events() is True
    assert progress_alt_held(True) is True
    assert progress_alt_held(False) is False
    # The removed legacy key never leaks into our cache.
    assert "legacyGoneVarName" not in mod_settings._settings
    # Persisted exactly once (reset + overlay coalesce into one debounced write).
    assert api.updated == 1
    assert api.saved == 1
    written = api.state["settings"][LINKAGE]
    assert written[GARAGE_KEY] is False
    assert written[BATTLE_ALT_KEY] is True
    assert "enabled" in written and written["enabled"] is True
    assert "legacyGoneVarName" not in written


def test_migration_across_a_layout_bump_keeps_every_saved_value(_run_register):
    # THE data-loss guard for a LAYOUT-ONLY settingsVersion bump -- currently the revert bump that
    # put the progress-bar checkbox back at the end of column 1. Nothing about the stored VALUES
    # changed (no varName added, removed or renamed), only where a control is drawn, so a user must
    # come out the other side with all TEN persisted varNames exactly as they left them. MSA has no
    # value migration of its own: setModTemplate resets the stored dict to the template defaults on
    # any bump, so without register()'s snapshot -> setModTemplate -> _apply(old_raw) ->
    # updateModSettings + saveState path this bump is a silent settings wipe on every update.
    #
    # The stored version is derived (SETTINGS_VERSION - 1), not a literal: this test guards the
    # BEHAVIOUR "a version bump never wipes stored values", so it must keep guarding the NEXT bump
    # without an edit -- pinning the number here would just re-rot on every relayout.
    #
    # Every value below is the NON-default, so a wipe cannot masquerade as a pass: each flag is
    # flipped from its DEFAULTS entry and each coordinate is a real pin.
    old = {
        "enabled": True,
        GARAGE_KEY: False,              # default True
        BATTLE_KEY: False,              # default True
        BATTLE_ALT_KEY: True,           # default False
        COUNTED_ASSIST_KEY: False,      # default True since v13
        PROGRESS_BAR_KEY: True,         # default False -- the control the relayout moved
        PROGRESS_VARIANT_KEY: PROGRESS_VARIANT_MOVING_AVERAGE,   # default 0 (Damage Efficiency)
        PROGRESS_SIZE_KEY: PROGRESS_SIZE_LARGE,              # default 0 (the shipped size)
        PROGRESS_SHOW_EVENTS_KEY: False,    # default True
        PROGRESS_SHOW_ALT_KEY: False,       # default True
        PROGRESS_SHOW_ALWAYS_KEY: True,     # default False
        PROGRESS_TRANSITIONS_KEY: False,    # default True (animated -- what shipped)
        PROGRESS_TRANS_EVENTS_KEY: False,   # default True
        PROGRESS_TRANS_MANUAL_KEY: False,   # default True
        POS_X_KEY: 700, POS_Y_KEY: 300, # default 0 (auto)
        POS_W_KEY: 1920, POS_H_KEY: 1080,
        FOLLOW_CAROUSEL_KEY: False,     # default True
    }
    for key in DEFAULTS:
        assert old[key] != DEFAULTS[key], "%s must differ from its default to prove anything" % key
    api = _FakeMsaApi(stored=old, stored_version=SETTINGS_VERSION - 1)
    _run_register(api)

    # The live cache: every getter reports the user's choice, not the fresh default.
    assert mod_settings.garage_enabled() is False
    assert mod_settings.battle_enabled() is False
    assert mod_settings.battle_alt_key_enabled() is True
    assert mod_settings.counted_assistance_enabled() is False
    assert mod_settings.progress_bar_enabled() is True
    # The two non-bool values: each must come out the bump as the INT index the user chose, not
    # booled into True by _coerce's default branch. This store already carries PROGRESS_SHOW_EVENTS_KEY
    # (a v13-introduced key), so it is a >= v13 store -- _migrate_pre_v13_variant must leave the
    # variant raw int untouched (only a PRE-v13 store gets flipped; see the dedicated test below).
    assert mod_settings._settings[PROGRESS_VARIANT_KEY] == 1
    assert mod_settings.progress_bar_variant() == PROGRESS_VARIANT_MOVING_AVERAGE
    assert mod_settings.progress_bar_size() == PROGRESS_SIZE_LARGE
    # The three visibility flags: a user who pinned the bar (or muted a trigger) must not have it
    # reset by the bump.
    assert progress_show_events() is True        # "Always" folds in
    assert progress_alt_held(False) is True      # ...and pins the bar
    for key in (PROGRESS_VARIANT_KEY, PROGRESS_SIZE_KEY):
        assert not isinstance(mod_settings._settings[key], bool)
    # The three transitions flags: a user who turned the motion OFF must not have it switched back
    # on by the bump (the fresh default is True, so a wipe here is silently "your bar animates
    # again").
    assert progress_transitions_events() is False
    assert progress_transitions_manual() is False
    assert (mod_settings.pos_x(), mod_settings.pos_y()) == (700, 300)
    assert (mod_settings.pos_w(), mod_settings.pos_h()) == (1920, 1080)
    assert mod_settings.follow_carousel() is False

    # ...and the same survived to DISK, in one coalesced write (the transient reset never lands).
    written = api.state["settings"][LINKAGE]
    for key, value in old.items():
        assert written[key] == value, "%s was wiped by the settingsVersion bump" % key
    assert api.updated == 1
    assert api.saved == 1


def test_migrate_pre_v13_variant_flips_only_when_the_v13_marker_key_is_absent():
    # Pure unit test of the fixup: a store with no PROGRESS_SHOW_EVENTS_KEY (the v13-introduced
    # marker) is PRE-v13 and gets its raw variant int flipped 0<->1 in place; a store that already
    # carries the marker is >= v13 and is left untouched.
    pre_v13 = {PROGRESS_VARIANT_KEY: 0}   # OLD order: 0 = Moving Average
    mod_settings._migrate_pre_v13_variant(pre_v13)
    assert pre_v13[PROGRESS_VARIANT_KEY] == 1   # CURRENT order's Moving Average index

    pre_v13_other = {PROGRESS_VARIANT_KEY: 1}   # OLD order: 1 = Damage Efficiency
    mod_settings._migrate_pre_v13_variant(pre_v13_other)
    assert pre_v13_other[PROGRESS_VARIANT_KEY] == 0   # CURRENT order's Damage Efficiency index

    at_v13 = {PROGRESS_SHOW_EVENTS_KEY: True, PROGRESS_VARIANT_KEY: 0}
    mod_settings._migrate_pre_v13_variant(at_v13)
    assert at_v13[PROGRESS_VARIANT_KEY] == 0   # untouched -- marker key present means already v13+


def test_migrate_pre_v13_variant_is_fail_soft():
    # A missing key, a non-int, a bool (an int subclass -- must not be treated as a legal 0/1) and
    # an out-of-range value must never raise, and are left exactly as-is (clamp_variant is what
    # falls back to a safe default when one of these is later read).
    no_key = {}
    mod_settings._migrate_pre_v13_variant(no_key)
    assert PROGRESS_VARIANT_KEY not in no_key

    non_int = {PROGRESS_VARIANT_KEY: "nonsense"}
    mod_settings._migrate_pre_v13_variant(non_int)
    assert non_int[PROGRESS_VARIANT_KEY] == "nonsense"

    booly = {PROGRESS_VARIANT_KEY: True}
    mod_settings._migrate_pre_v13_variant(booly)
    assert booly[PROGRESS_VARIANT_KEY] is True

    out_of_range = {PROGRESS_VARIANT_KEY: 7}
    mod_settings._migrate_pre_v13_variant(out_of_range)
    assert out_of_range[PROGRESS_VARIANT_KEY] == 7


def test_migration_flips_progress_bar_variant_for_a_pre_v13_store(_run_register):
    # An upgrading pre-v13 (e.g. the published v1.6.0, settingsVersion 10) user who chose "Moving
    # Average" under the OLD option order (raw stored int 0) must land back on "Moving Average"
    # under the CURRENT order (index 1) -- the raw int must FLIP, not ride across unchanged.
    old = {"enabled": True, PROGRESS_BAR_KEY: True, PROGRESS_VARIANT_KEY: 0}
    api = _FakeMsaApi(stored=old, stored_version=10)
    _run_register(api)
    assert mod_settings._settings[PROGRESS_VARIANT_KEY] == 1
    assert mod_settings.progress_bar_variant() == PROGRESS_VARIANT_MOVING_AVERAGE
    written = api.state["settings"][LINKAGE]
    assert written[PROGRESS_VARIANT_KEY] == 1
    assert api.updated == 1
    assert api.saved == 1


def test_migration_preserves_host_enabled_false(_run_register):
    # A user who disabled the mod via the host 'enabled' toggle must stay disabled across
    # migration (the host key survives the template reset and the re-write).
    old = {"enabled": False, GARAGE_KEY: False}
    api = _FakeMsaApi(stored=old, stored_version=4)
    _run_register(api)
    assert api.state["settings"][LINKAGE]["enabled"] is False


def test_fresh_install_yields_defaults_without_spurious_persist(_run_register):
    # No stored settings -> old_raw empty -> migration overlay skipped: defaults everywhere and
    # NO updateModSettings / saveState.
    api = _FakeMsaApi(stored=None, stored_version=0)
    _run_register(api)
    assert mod_settings.garage_enabled() is DEFAULTS[GARAGE_KEY]
    assert mod_settings.pos_x() == 0 and mod_settings.pos_y() == 0
    assert api.updated == 0
    assert api.saved == 0
    # Fresh-install path registered the template and wired its callback.
    assert api.template_cb is mod_settings._on_changed


def test_same_version_load_does_not_migrate(_run_register):
    # getModSettings returns the stored dict (version matches) -> saved-truthy branch runs
    # (_seed + registerCallback), and the migration/setModTemplate else-branch is never entered.
    stored = {"enabled": True, GARAGE_KEY: False, BATTLE_ALT_KEY: True,
              POS_X_KEY: 700, POS_Y_KEY: 300}
    api = _FakeMsaApi(stored=stored, stored_version=SETTINGS_VERSION)
    _run_register(api)
    assert mod_settings.garage_enabled() is False
    assert mod_settings.battle_alt_key_enabled() is True
    assert mod_settings.pos_x() == 700 and mod_settings.pos_y() == 300
    assert api.registered_cb is mod_settings._on_changed
    assert api.template_cb is None
    assert api.updated == 0
    assert api.saved == 0
