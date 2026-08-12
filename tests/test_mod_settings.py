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
    PROGRESS_HOLD_SECONDS_KEY, PROGRESS_HOLD_DEFAULT, PROGRESS_HOLD_MIN, PROGRESS_HOLD_MAX,
    battle_alt_key_enabled, battle_enabled, counted_assistance_enabled,
    progress_bar_enabled, progress_bar_variant, progress_bar_size, clamp_variant,
    progress_transitions_events, progress_transitions_manual,
    progress_show_events, progress_alt_held, clamp_hold_seconds, progress_hold_seconds,
    POS_X_KEY, POS_Y_KEY, POS_W_KEY, POS_H_KEY, FOLLOW_CAROUSEL_KEY, POS_MAX,
    BAR_POS_X_KEY, BAR_POS_Y_KEY,
    clamp_pos, pos_x, pos_y, pos_w, pos_h, follow_carousel, set_position,
    bar_pos_x, bar_pos_y, set_bar_position,
    PROGRESS_ORIENTATION_KEY, PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ORIENT_VERTICAL,
    PROGRESS_ALIGNMENT_KEY, PROGRESS_ALIGN_FIXED, PROGRESS_ALIGN_FREE,
    PROGRESS_ALIGN_DAMAGE_LOG, PROGRESS_ALIGN_MINIMAP,
    progress_bar_orientation, progress_bar_alignment,
    PROGRESS_VARIANT_HOTKEY_KEY, progress_variant_hotkey)
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
    # three TRANSITION switches on (the animated bar is what shipped), BOTH drag positions at auto
    # (the garage widget's 0/0/0/0 and the in-battle bar's 0/0 -- the v18 pair, which is what keeps
    # every existing user's bar on the shipped anchor), Orientation Horizontal and Alignment Damage
    # Log (v21 -- also byte-identical to what shipped) and Follow Carousel on. The hold duration
    # defaults to 5 SECONDS -- the JS transient's own baked HOLD_MS / 1000, so an existing bar's
    # length does not change on update.
    assert merge_settings(None) == DEFAULTS
    assert merge_settings({}) == DEFAULTS
    assert DEFAULTS == {GARAGE_KEY: True, BATTLE_KEY: True, BATTLE_ALT_KEY: False,
                        COUNTED_ASSIST_KEY: True, PROGRESS_BAR_KEY: False,
                        PROGRESS_VARIANT_KEY: 0, PROGRESS_SIZE_KEY: 0,
                        PROGRESS_SHOW_EVENTS_KEY: True, PROGRESS_SHOW_ALT_KEY: True,
                        PROGRESS_SHOW_ALWAYS_KEY: False,
                        PROGRESS_TRANSITIONS_KEY: True, PROGRESS_TRANS_EVENTS_KEY: True,
                        PROGRESS_TRANS_MANUAL_KEY: True,
                        PROGRESS_HOLD_SECONDS_KEY: 5,
                        POS_X_KEY: 0, POS_Y_KEY: 0, POS_W_KEY: 0, POS_H_KEY: 0,
                        mod_settings.BAR_POS_X_KEY: 0, mod_settings.BAR_POS_Y_KEY: 0,
                        mod_settings.PROGRESS_POS_FRAME_KEY: mod_settings.POS_FRAME_ANCHOR,
                        PROGRESS_ORIENTATION_KEY: 0, PROGRESS_ALIGNMENT_KEY: 0,
                        FOLLOW_CAROUSEL_KEY: True,
                        PROGRESS_VARIANT_HOTKEY_KEY: [37]}
    # v22: fresh installs start straight in the ANCHOR frame -- there is no legacy pair to carry.
    assert DEFAULTS[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_ANCHOR
    # THE ORIENTATION/ALIGNMENT RADIOS: an int 0 each (Horizontal / Fixed), never a bool -- the
    # same trap as the two variant/size radios. Alignment is Fixed/Free only (v23) -- the old
    # 3-option Damage Log/Minimap/Free domain is retired; PROGRESS_ALIGN_DAMAGE_LOG /
    # PROGRESS_ALIGN_MINIMAP survive only as bar_window's INTERNAL anchor selectors, never a
    # stored value.
    assert DEFAULTS[PROGRESS_ORIENTATION_KEY] is PROGRESS_ORIENT_HORIZONTAL
    assert DEFAULTS[PROGRESS_ALIGNMENT_KEY] is PROGRESS_ALIGN_FIXED
    for key in (PROGRESS_ORIENTATION_KEY, PROGRESS_ALIGNMENT_KEY):
        assert not isinstance(DEFAULTS[key], bool)
    assert (PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ORIENT_VERTICAL) == (0, 1)
    assert (PROGRESS_ALIGN_FIXED, PROGRESS_ALIGN_FREE) == (0, 1)
    # The internal anchor selectors keep their OLD numeric values (0/1) on purpose -- see
    # mod_settings.py -- but they are a DIFFERENT vocabulary from the stored Fixed/Free pair and
    # must never be compared against it (PROGRESS_ALIGN_MINIMAP == PROGRESS_ALIGN_FREE == 1).
    assert (PROGRESS_ALIGN_DAMAGE_LOG, PROGRESS_ALIGN_MINIMAP) == (0, 1)
    # An INT, never a bool -- the same trap as the two radios: a bool here would poison every
    # _coerce round-trip and the panel would store True instead of a second count.
    assert DEFAULTS[PROGRESS_HOLD_SECONDS_KEY] is PROGRESS_HOLD_DEFAULT
    assert isinstance(DEFAULTS[PROGRESS_HOLD_SECONDS_KEY], int)
    assert not isinstance(DEFAULTS[PROGRESS_HOLD_SECONDS_KEY], bool)
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
                    PROGRESS_HOLD_SECONDS_KEY: PROGRESS_HOLD_DEFAULT,
                    POS_X_KEY: 640, POS_Y_KEY: 360, POS_W_KEY: 1920, POS_H_KEY: 1080,
                    mod_settings.BAR_POS_X_KEY: 0, mod_settings.BAR_POS_Y_KEY: 0,
                    mod_settings.PROGRESS_POS_FRAME_KEY: mod_settings.POS_FRAME_ANCHOR,
                    PROGRESS_ORIENTATION_KEY: 0, PROGRESS_ALIGNMENT_KEY: 0,
                    FOLLOW_CAROUSEL_KEY: False,
                    PROGRESS_VARIANT_HOTKEY_KEY: [37]}


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


def test_progress_variant_hotkey_default_and_getter():
    mod_settings._seed(DEFAULTS)
    assert progress_variant_hotkey() == [37]
    mod_settings._apply({PROGRESS_VARIANT_HOTKEY_KEY: [38]})
    assert progress_variant_hotkey() == [38]
    mod_settings._apply({PROGRESS_VARIANT_HOTKEY_KEY: []})
    assert progress_variant_hotkey() == []


def test_progress_variant_hotkey_guards_bad_store():
    mod_settings._seed(DEFAULTS)
    mod_settings._apply({PROGRESS_VARIANT_HOTKEY_KEY: "K"})
    assert progress_variant_hotkey() == [37]


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


# --- v21: the Orientation radio (the mod's THIRD non-bool setting) -----------------------------

def test_coerce_orientation_key_is_not_booled():
    # Same trap as the variant/size radios: index 1 (Vertical) must not fall through to bool() and
    # become True.
    assert mod_settings._coerce(PROGRESS_ORIENTATION_KEY, 1) == PROGRESS_ORIENT_VERTICAL
    assert mod_settings._coerce(PROGRESS_ORIENTATION_KEY, 1) is not True
    assert mod_settings._coerce(PROGRESS_ORIENTATION_KEY, 0) is not False
    assert not isinstance(mod_settings._coerce(PROGRESS_ORIENTATION_KEY, 1), bool)
    # THE BOOL TRAP, named: True is an int subclass equal to 1, so a naive int() cast would pass
    # it through as the legal index 1 (Vertical) instead of being rejected as corrupt.
    assert mod_settings._coerce(PROGRESS_ORIENTATION_KEY, True) == PROGRESS_ORIENT_HORIZONTAL
    assert mod_settings._coerce(PROGRESS_ORIENTATION_KEY, True) is not True
    # Only two options exist -- anything past Vertical is corrupt.
    for bad in (True, False, PROGRESS_ORIENT_VERTICAL + 1, -1, None, "abc", [1]):
        assert mod_settings._coerce(PROGRESS_ORIENTATION_KEY, bad) == PROGRESS_ORIENT_HORIZONTAL, \
            "%r leaked through the orientation branch" % (bad,)
    assert merge_settings({PROGRESS_ORIENTATION_KEY: 1})[PROGRESS_ORIENTATION_KEY] == \
        PROGRESS_ORIENT_VERTICAL
    assert merge_settings({PROGRESS_ORIENTATION_KEY: True})[PROGRESS_ORIENTATION_KEY] == \
        PROGRESS_ORIENT_HORIZONTAL


def test_progress_bar_orientation_getter_reclamps_a_corrupt_store():
    mod_settings._seed(dict(DEFAULTS))
    assert progress_bar_orientation() == PROGRESS_ORIENT_HORIZONTAL
    mod_settings._apply({PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL})
    assert progress_bar_orientation() == PROGRESS_ORIENT_VERTICAL
    for junk in (True, 5, -2, None, "x"):
        mod_settings._settings[PROGRESS_ORIENTATION_KEY] = junk
        assert progress_bar_orientation() == PROGRESS_ORIENT_HORIZONTAL, \
            "%r leaked on read" % (junk,)
        assert not isinstance(progress_bar_orientation(), bool)
    del mod_settings._settings[PROGRESS_ORIENTATION_KEY]
    assert progress_bar_orientation() == PROGRESS_ORIENT_HORIZONTAL


# --- v21: the Alignment radio (the mod's FOURTH non-bool setting, max_index=2) ------------------

def test_coerce_alignment_key_is_not_booled():
    # v23: TWO options now (Fixed / Free) -- the old Damage Log/Minimap/Free 3-option domain is
    # retired.
    assert mod_settings._coerce(PROGRESS_ALIGNMENT_KEY, 1) == PROGRESS_ALIGN_FREE
    assert mod_settings._coerce(PROGRESS_ALIGNMENT_KEY, 1) is not True
    for good in (0, 1):
        assert not isinstance(mod_settings._coerce(PROGRESS_ALIGNMENT_KEY, good), bool)
    # THE BOOL TRAP again: True must not pass through as the legal index 1 (Free).
    assert mod_settings._coerce(PROGRESS_ALIGNMENT_KEY, True) == PROGRESS_ALIGN_FIXED
    assert mod_settings._coerce(PROGRESS_ALIGNMENT_KEY, True) is not True
    # Anything past Free (including the OLD raw index 2, the pre-v23 Free) is corrupt to a bare
    # _coerce/merge_settings call -- only the dedicated migration (_migrate_pre_v23_alignment, run
    # once at register()) may still interpret 2 as Free.
    for bad in (True, False, 2, PROGRESS_ALIGN_FREE + 1, -1, None, "abc", [1]):
        assert mod_settings._coerce(PROGRESS_ALIGNMENT_KEY, bad) == PROGRESS_ALIGN_FIXED, \
            "%r leaked through the alignment branch" % (bad,)
    assert merge_settings({PROGRESS_ALIGNMENT_KEY: 1})[PROGRESS_ALIGNMENT_KEY] == \
        PROGRESS_ALIGN_FREE
    assert merge_settings({PROGRESS_ALIGNMENT_KEY: True})[PROGRESS_ALIGNMENT_KEY] == \
        PROGRESS_ALIGN_FIXED


def test_progress_bar_alignment_getter_reclamps_a_corrupt_store():
    mod_settings._seed(dict(DEFAULTS))
    assert progress_bar_alignment() == PROGRESS_ALIGN_FIXED
    mod_settings._apply({PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FREE})
    assert progress_bar_alignment() == PROGRESS_ALIGN_FREE
    for junk in (True, 5, -2, None, "x"):
        mod_settings._settings[PROGRESS_ALIGNMENT_KEY] = junk
        assert progress_bar_alignment() == PROGRESS_ALIGN_FIXED, \
            "%r leaked on read" % (junk,)
        assert not isinstance(progress_bar_alignment(), bool)
    del mod_settings._settings[PROGRESS_ALIGNMENT_KEY]
    assert progress_bar_alignment() == PROGRESS_ALIGN_FIXED


# --- DELETED (this dispatch): set_bar_position() no longer touches Alignment at all -------------
# It used to force Alignment := Free unconditionally (v21). That write is now provably a no-op on
# every call: both callers (BarHost.drag's persist, BarHost._materialise's own conversion write)
# already refuse to reach set_bar_position unless Alignment is ALREADY Free -- see
# test_set_bar_position_leaves_alignment_untouched below, which pins the deletion directly.

def test_set_bar_position_leaves_alignment_untouched():
    # The regression this dispatch's deletion owes: set_bar_position must NOT resurrect the
    # retired "-> Free" write, even called directly (bypassing the callers' own gates) as a test
    # would. Position still writes; Alignment (started Fixed here) must not move.
    mod_settings._seed(_defaults_with({PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FIXED}))
    set_bar_position(120, 240, persist=False)
    assert (bar_pos_x(), bar_pos_y()) == (120, 240)
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FIXED


# --- v23: the Orientation<->Alignment mutual auto-set is RETIRED --------------------------------
# _derive_layout keeps exactly ONE rule now (this dispatch deleted the second): an explicit
# Orientation flip still zeroes the stored X/Y pair (the two orientations use different surface
# geometries); the "a position change forces Alignment := Free" rule (v21) is GONE, because a
# position can now only ever change while Alignment is ALREADY Free (the steppers are gated on it
# and BarHost.drag() refuses the gesture otherwise -- see mod_settings.py's SETTINGS_VERSION 23
# same-bump-follow-on comment and _derive_layout's own docstring).

def _seed_live(orientation, alignment, x=0, y=0):
    mod_settings._seed(_defaults_with({
        PROGRESS_ORIENTATION_KEY: orientation, PROGRESS_ALIGNMENT_KEY: alignment,
        BAR_POS_X_KEY: x, BAR_POS_Y_KEY: y}))


def test_on_changed_orientation_switch_leaves_alignment_untouched():
    # DELETED-RULE REGRESSION: an Orientation flip must NOT re-anchor Alignment any more, in
    # either direction, and regardless of whether Alignment started Fixed or Free.
    for start_o, other_o in ((PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ORIENT_VERTICAL),
                             (PROGRESS_ORIENT_VERTICAL, PROGRESS_ORIENT_HORIZONTAL)):
        for alignment in (PROGRESS_ALIGN_FIXED, PROGRESS_ALIGN_FREE):
            _seed_live(start_o, alignment)
            mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: other_o})
            assert mod_settings.progress_bar_alignment() == alignment, \
                "an Orientation flip touched Alignment (%r -> %r, started %r)" % (
                    start_o, other_o, alignment)


def test_on_changed_orientation_switch_zeroes_the_stored_position_pair():
    # KEPT: the two orientations use different surface geometries, so a real pair must not carry
    # across an Orientation flip -- regardless of Alignment (Fixed or Free).
    for alignment in (PROGRESS_ALIGN_FIXED, PROGRESS_ALIGN_FREE):
        _seed_live(PROGRESS_ORIENT_HORIZONTAL, alignment, x=900, y=500)
        mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL,
                                           BAR_POS_X_KEY: 900, BAR_POS_Y_KEY: 500})
        assert (bar_pos_x(), bar_pos_y()) == (0, 0)

        _seed_live(PROGRESS_ORIENT_VERTICAL, alignment, x=-120, y=640)
        mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_HORIZONTAL,
                                           BAR_POS_X_KEY: -120, BAR_POS_Y_KEY: 640})
        assert (bar_pos_x(), bar_pos_y()) == (0, 0)


def test_on_changed_alignment_switch_does_not_touch_orientation_or_position():
    # DELETED-RULE REGRESSION: Alignment no longer derives Orientation in either direction, and
    # switching it alone must not zero the stored pair either -- both were rows the OLD design
    # forced (Damage Log -> Horizontal, Minimap -> Vertical); v23 has no such rows left.
    _seed_live(PROGRESS_ORIENT_VERTICAL, PROGRESS_ALIGN_FIXED, x=42, y=13)
    mod_settings._on_changed(LINKAGE, {PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FREE})
    assert mod_settings.progress_bar_orientation() == PROGRESS_ORIENT_VERTICAL
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FREE
    assert (bar_pos_x(), bar_pos_y()) == (42, 13)

    _seed_live(PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_FREE, x=7, y=8)
    mod_settings._on_changed(LINKAGE, {PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FIXED})
    assert mod_settings.progress_bar_orientation() == PROGRESS_ORIENT_HORIZONTAL
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FIXED
    assert (bar_pos_x(), bar_pos_y()) == (7, 8)


def test_on_changed_no_orientation_or_position_change_leaves_alignment_alone():
    # Neither axis changed (some OTHER key in the payload changed, e.g. a checkbox) -> nothing
    # must fire at all.
    _seed_live(PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_FREE, x=0, y=0)
    mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_HORIZONTAL,
                                       BAR_POS_X_KEY: 0, BAR_POS_Y_KEY: 0,
                                       BATTLE_KEY: False})
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FREE


def test_on_changed_orientation_switch_persists_the_zeroed_pair_through_msa(monkeypatch):
    # The zeroing is the ONLY derived write left on an Orientation flip: ONE
    # updateModSettings/saveState pass, and Alignment rides through UNCHANGED (no re-anchor).
    _seed_live(PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_FREE, x=900, y=500)
    fake = _FakeMsa({"enabled": True})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)
    mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL,
                                       BAR_POS_X_KEY: 900, BAR_POS_Y_KEY: 500})
    assert fake.write_count == 1
    assert fake.save_count == 1
    assert fake.written[BAR_POS_X_KEY] == 0 and fake.written[BAR_POS_Y_KEY] == 0
    assert fake.written[PROGRESS_ALIGNMENT_KEY] == PROGRESS_ALIGN_FREE   # untouched


def test_on_changed_stepper_edit_does_not_zero_the_pair():
    # A typed coordinate with an UNCHANGED orientation must be honoured verbatim -- zeroing it
    # would make the two steppers impossible to use at all.
    _seed_live(PROGRESS_ORIENT_VERTICAL, PROGRESS_ALIGN_FREE, x=0, y=0)
    mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL,
                                       BAR_POS_X_KEY: 250, BAR_POS_Y_KEY: 700})
    assert (bar_pos_x(), bar_pos_y()) == (250, 700)


def test_on_changed_orientation_change_zeroes_the_pair_even_with_a_typed_value_in_the_same_payload():
    # DELETED-RULE REGRESSION, inverted: the old "position wins outright" precedence (v21) used to
    # keep a typed pair when it rode in the SAME payload as an Orientation flip. That rule is gone
    # -- an Orientation change zeroes the stored pair UNCONDITIONALLY now, even when the payload
    # also carries a brand-new coordinate, because the two orientations use different surface
    # geometries regardless of what value a stepper edit happened to arrive with.
    _seed_live(PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_FIXED, x=0, y=0)
    mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL,
                                       BAR_POS_X_KEY: 250, BAR_POS_Y_KEY: 700})
    assert (bar_pos_x(), bar_pos_y()) == (0, 0)


def test_on_changed_alignment_and_position_set_together_in_one_payload():
    # NOT a derivation any more (the old "position forces Alignment" rule is deleted) -- this is
    # plain _apply overlay behaviour: both keys are explicitly present in the payload (as a real
    # stepper edit under Free would send them), Orientation is unchanged so _derive_layout does not
    # fire, and both values simply land as given.
    _seed_live(PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_FIXED, x=0, y=0)
    mod_settings._on_changed(LINKAGE, {PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FREE,
                                       BAR_POS_X_KEY: 250, BAR_POS_Y_KEY: 700})
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FREE
    assert (bar_pos_x(), bar_pos_y()) == (250, 700)


def test_on_changed_unrelated_key_change_does_not_zero_the_pair(monkeypatch):
    # A foreign-shaped payload for one of OUR keys (a checkbox) leaves the orientation equal, so
    # the reset must not fire -- and nothing must be written back at all. The call count is what
    # proves the guard held: the resulting pair is (900, 500) either way if the write were a
    # no-op mutation, so only the write count separates "did not fire" from "fired harmlessly".
    _seed_live(PROGRESS_ORIENT_VERTICAL, PROGRESS_ALIGN_FREE, x=900, y=500)
    fake = _FakeMsa({"enabled": True})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)
    mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL,
                                       BAR_POS_X_KEY: 900, BAR_POS_Y_KEY: 500,
                                       BATTLE_KEY: False})
    assert (bar_pos_x(), bar_pos_y()) == (900, 500)
    assert fake.write_count == 0


def test_a_foreign_mods_change_never_zeroes_the_pair(monkeypatch):
    # MSA broadcasts onSettingsChanged GLOBALLY. A foreign linkage must not even reach the
    # comparison -- otherwise every other mod's orientation-shaped key could wipe our coordinates.
    _seed_live(PROGRESS_ORIENT_VERTICAL, PROGRESS_ALIGN_FREE, x=900, y=500)
    fake = _FakeMsa({"enabled": True})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)
    mod_settings._on_changed("com.someone_else.other_mod",
                             {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_HORIZONTAL})
    assert (bar_pos_x(), bar_pos_y()) == (900, 500)
    assert fake.write_count == 0


def test_on_changed_loop_guard_does_not_refire_on_the_echoed_pass(monkeypatch):
    # THE LOOP GUARD: the zeroing write-back fires another onSettingsChanged of its own (MSA
    # echoes the write), so a second _on_changed pass with the SAME already-updated values must
    # NOT write through MSA again. A value-only assertion is blind here (the pair reads (0, 0)
    # after either one or two writes), so this is a CALL COUNT test by necessity (memory
    # a-noop-mutation-and-a-fail-soft-branch-can-look-identical).
    _seed_live(PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_FIXED, x=900, y=500)
    fake = _FakeMsa({"enabled": True})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)

    # FIRST pass: orientation actually changed -> the pair zeroes -> ONE write. Alignment is
    # NOT part of the derived write any more (the retired rule used to land it on Minimap here).
    mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL,
                                       BAR_POS_X_KEY: 900, BAR_POS_Y_KEY: 500})
    assert (bar_pos_x(), bar_pos_y()) == (0, 0)
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FIXED
    assert fake.write_count == 1
    assert fake.save_count == 1

    # SECOND pass: MSA's echo of that write -- orientation already Vertical, pair already zeroed
    # -> nothing to do.
    mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL,
                                       BAR_POS_X_KEY: 0, BAR_POS_Y_KEY: 0})
    assert (bar_pos_x(), bar_pos_y()) == (0, 0)
    assert fake.write_count == 1, "the echoed pass re-fired updateModSettings"
    assert fake.save_count == 1, "the echoed pass re-fired saveState"


# --- _derive_layout: the pure state machine (this dispatch: ONE rule, not two) -------------------
# The former "position change forces Alignment := Free" rule (v21) is DELETED along with every
# table row that exercised it -- see mod_settings.py's SETTINGS_VERSION 23 same-bump-follow-on
# comment. _derive_layout's signature dropped Alignment entirely (it never derives from anything
# here any more), so the table below is (orientation, position) pairs, not three-tuples. What
# remains: an Orientation change zeroes the position; everything else settles on `post` unchanged.

_DERIVE_LAYOUT_TABLE = (
    # (id, pre, post, expected)
    ("orientation-change-zeroes-a-real-pair",
     (PROGRESS_ORIENT_HORIZONTAL, (12, 34)),
     (PROGRESS_ORIENT_VERTICAL, (12, 34)),
     (PROGRESS_ORIENT_VERTICAL, (0, 0))),
    ("orientation-change-on-an-already-zero-pair-is-a-no-op",
     (PROGRESS_ORIENT_VERTICAL, (0, 0)),
     (PROGRESS_ORIENT_HORIZONTAL, (0, 0)),
     (PROGRESS_ORIENT_HORIZONTAL, (0, 0))),
    ("unrelated-key-is-a-no-op",
     (PROGRESS_ORIENT_HORIZONTAL, (3, 4)),
     (PROGRESS_ORIENT_HORIZONTAL, (3, 4)),
     (PROGRESS_ORIENT_HORIZONTAL, (3, 4))),
    ("echo-of-our-own-write-back-is-a-no-op",
     (PROGRESS_ORIENT_VERTICAL, (0, 0)),
     (PROGRESS_ORIENT_VERTICAL, (0, 0)),
     (PROGRESS_ORIENT_VERTICAL, (0, 0))),
)


@pytest.mark.parametrize("pre,post,expected",
                         [row[1:] for row in _DERIVE_LAYOUT_TABLE],
                         ids=[row[0] for row in _DERIVE_LAYOUT_TABLE])
def test_derive_layout_table(pre, post, expected):
    assert mod_settings._derive_layout(pre, post) == expected


_RESTING_STATES = (
    (PROGRESS_ORIENT_HORIZONTAL, (0, 0)),
    (PROGRESS_ORIENT_VERTICAL, (0, 0)),
    (PROGRESS_ORIENT_HORIZONTAL, (321, 654)),
    (PROGRESS_ORIENT_VERTICAL, (-15, 200)),
)


@pytest.mark.parametrize("state", _RESTING_STATES,
                         ids=["horizontal-zero", "vertical-zero", "horizontal-pinned",
                              "vertical-pinned"])
def test_derive_layout_resting_states_are_fixed_points(state):
    # THE TERMINATION PROOF: every resting state must derive to itself, or the write-back's own
    # echo would ping-pong forever. Trivially true now for ANY state (pre == post means
    # `orientation_changed` cannot fire, so the function returns `post` verbatim) -- these four are
    # kept as a representative, named regression set rather than asserting the property is vacuous.
    assert mod_settings._derive_layout(state, state) == state


# --- single-pass settle: one user action, exactly one write, self-terminating echo --------------

def test_on_changed_settles_in_a_single_pass_and_the_echo_writes_nothing(monkeypatch):
    # Seeded with a REAL pre-existing pin (not 0/0): the orientation flip needs a non-zero pair
    # already stored for its own derived write (the zeroing) to actually be dirty.
    _seed_live(PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_FIXED, x=900, y=500)
    fake = _FakeMsa({"enabled": True})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)

    mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL})
    assert (bar_pos_x(), bar_pos_y()) == (0, 0)
    assert fake.write_count == 1
    assert fake.save_count == 1

    # MSA's echo carries exactly the dict we just wrote -> a second pass must write NOTHING.
    echoed = dict(fake.written)
    mod_settings._on_changed(LINKAGE, echoed)
    assert fake.write_count == 1, "the echo of our own write-back re-fired updateModSettings"
    assert fake.save_count == 1, "the echo of our own write-back re-fired saveState"


def test_on_changed_alignment_only_change_writes_nothing(monkeypatch):
    # v23: an Alignment change ALONE (no position, no orientation change in the same payload) no
    # longer derives anything -- it settles on `post` unchanged, so the pass must not be dirty.
    _seed_live(PROGRESS_ORIENT_VERTICAL, PROGRESS_ALIGN_FIXED, x=0, y=0)
    fake = _FakeMsa({"enabled": True})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)

    mod_settings._on_changed(LINKAGE, {PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FREE})
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FREE
    assert fake.write_count == 0
    assert fake.save_count == 0


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


# --- the hold-duration Slider: a whole-seconds int, and NOT master-folded --------------------

def test_clamp_hold_seconds_bounds_and_bool_trap():
    # A THIRD trust boundary alongside clamp_pos / clamp_variant, and the same bool trap: bool is
    # an int SUBCLASS, so isinstance must be tested BEFORE int() or True/False would pass through
    # as legal 1/0-second holds. Legal in-range ints pass through unchanged.
    assert clamp_hold_seconds(PROGRESS_HOLD_MIN) == PROGRESS_HOLD_MIN
    assert clamp_hold_seconds(PROGRESS_HOLD_MAX) == PROGRESS_HOLD_MAX
    assert clamp_hold_seconds(12) == 12
    assert not isinstance(clamp_hold_seconds(12), bool)
    # Numeric strings / floats coerce through int(), like clamp_pos / clamp_variant.
    assert clamp_hold_seconds("12") == 12
    assert clamp_hold_seconds(12.9) == 12
    # A bool ALWAYS falls back to the DEFAULT (not to MIN, and never treated as a legal 0/1 s).
    assert clamp_hold_seconds(True) == PROGRESS_HOLD_DEFAULT
    assert clamp_hold_seconds(False) == PROGRESS_HOLD_DEFAULT
    for bad in (True, False):
        assert not isinstance(clamp_hold_seconds(bad), bool) or clamp_hold_seconds(bad) != bad
    # Garbage (None, a non-numeric string, a list, an object) also falls back to the DEFAULT --
    # NOT to MIN, which would silently shorten a corrupt store's hold to the floor instead of the
    # shipped 5 s.
    for bad in (None, "x", [], {}, object()):
        got = clamp_hold_seconds(bad)
        assert got == PROGRESS_HOLD_DEFAULT, "%r leaked %r" % (bad, got)
        assert not isinstance(got, bool)
    # Merely OUT-OF-RANGE (a real int, just outside [MIN, MAX]) clamps to the nearest bound --
    # unlike garbage, this does NOT fall back to the default: "as long as possible" is a real ask.
    assert clamp_hold_seconds(PROGRESS_HOLD_MIN - 1) == PROGRESS_HOLD_MIN
    assert clamp_hold_seconds(0) == PROGRESS_HOLD_MIN
    assert clamp_hold_seconds(-100) == PROGRESS_HOLD_MIN
    assert clamp_hold_seconds(PROGRESS_HOLD_MAX + 1) == PROGRESS_HOLD_MAX
    assert clamp_hold_seconds(10 ** 6) == PROGRESS_HOLD_MAX


def test_coerce_hold_seconds_key_is_not_booled():
    # The branch is wired to the right key: a stored 12 must survive as 12 (never booled to True by
    # the default branch), and a stored 0 must clamp to MIN rather than becoming False.
    assert mod_settings._coerce(PROGRESS_HOLD_SECONDS_KEY, 12) == 12
    assert mod_settings._coerce(PROGRESS_HOLD_SECONDS_KEY, 12) is not True
    assert mod_settings._coerce(PROGRESS_HOLD_SECONDS_KEY, 0) == PROGRESS_HOLD_MIN
    assert mod_settings._coerce(PROGRESS_HOLD_SECONDS_KEY, 0) is not False
    assert mod_settings._coerce(PROGRESS_HOLD_SECONDS_KEY, True) == PROGRESS_HOLD_DEFAULT
    assert mod_settings._coerce(PROGRESS_HOLD_SECONDS_KEY, None) == PROGRESS_HOLD_DEFAULT
    # ...and end to end through merge_settings, the path MSA's payload actually takes.
    assert merge_settings({PROGRESS_HOLD_SECONDS_KEY: 12})[PROGRESS_HOLD_SECONDS_KEY] == 12
    assert merge_settings({PROGRESS_HOLD_SECONDS_KEY: "12"})[PROGRESS_HOLD_SECONDS_KEY] == 12
    assert merge_settings({PROGRESS_HOLD_SECONDS_KEY: 0})[PROGRESS_HOLD_SECONDS_KEY] == \
        PROGRESS_HOLD_MIN
    assert merge_settings({PROGRESS_HOLD_SECONDS_KEY: True})[PROGRESS_HOLD_SECONDS_KEY] == \
        PROGRESS_HOLD_DEFAULT


def test_progress_hold_seconds_getter_defaults_tracks_and_reclamps():
    # Ships on the JS transient's own baked default (5 s) and the getter tracks live changes, RE-
    # CLAMPING on read like the position/radio getters -- a store corrupted outside _coerce must
    # never leak a bool or an out-of-range duration to the widget.
    mod_settings._seed(dict(DEFAULTS))
    assert progress_hold_seconds() == PROGRESS_HOLD_DEFAULT
    mod_settings._apply({PROGRESS_HOLD_SECONDS_KEY: 20})
    assert progress_hold_seconds() == 20
    mod_settings._apply({PROGRESS_HOLD_SECONDS_KEY: PROGRESS_HOLD_DEFAULT})
    assert progress_hold_seconds() == PROGRESS_HOLD_DEFAULT
    for junk in (True, False, 999, -5, None, "x"):
        mod_settings._settings[PROGRESS_HOLD_SECONDS_KEY] = junk
        got = progress_hold_seconds()
        assert not isinstance(got, bool)
        assert PROGRESS_HOLD_MIN <= got <= PROGRESS_HOLD_MAX
    del mod_settings._settings[PROGRESS_HOLD_SECONDS_KEY]
    assert progress_hold_seconds() == PROGRESS_HOLD_DEFAULT


def test_progress_hold_seconds_is_not_master_folded_by_the_transitions_switch():
    # THE invariant a later "tidy-up" is most likely to break: the hold is a DURATION, not a switch,
    # so it must NOT be ANDed with progress_transitions_enabled the way progress_transitions_events /
    # _manual are. With the Transitions master OFF (and even with every switch off), the configured
    # hold must still come back as the user's stored seconds -- never 0, never False.
    mod_settings._seed(_defaults_with({
        mod_settings.PROGRESS_TRANSITIONS_KEY: False,
        mod_settings.PROGRESS_TRANS_EVENTS_KEY: False,
        mod_settings.PROGRESS_TRANS_MANUAL_KEY: False,
        PROGRESS_HOLD_SECONDS_KEY: 17,
    }))
    assert progress_hold_seconds() == 17
    assert progress_hold_seconds() is not False
    assert progress_transitions_events() is False       # the master fold still holds for its OWN pair
    assert progress_transitions_manual() is False


def test_slider_descriptor_shape_and_tipless_omission():
    # The Slider descriptor's shape mirrors _stepper's (a plain dict, no gui.aslainMenu import): a
    # `minimum`/`maximum`/`snapInterval` triple Aslain folds into its _settingsStructure signature,
    # `format` as MSA's own "{{value}} s" substitution token, and the tooltip key OMITTED (not
    # emitted empty) when the rendered row has none -- the same hard-index trap that once killed the
    # WHOLE panel from inside _checkbox / _stepper (a KeyError inside _template(), i.e. inside
    # register()'s guarded try).
    control = mod_settings._slider(PROGRESS_HOLD_SECONDS_KEY, {"text": u"Hold Duration"})
    assert control["type"] == "Slider"
    assert control["text"] == u"Hold Duration"
    assert control["varName"] == PROGRESS_HOLD_SECONDS_KEY
    assert control["value"] == DEFAULTS[PROGRESS_HOLD_SECONDS_KEY]
    assert control["minimum"] == PROGRESS_HOLD_MIN
    assert control["maximum"] == PROGRESS_HOLD_MAX
    assert control["snapInterval"] == 1
    assert control["format"] == "{{value}} s"
    assert "tooltip" not in control
    # THE HELPER ITSELF NEVER EMITS A masterVarName -- only _grouped_column1 writes that key, and
    # this descriptor is never passed to it (see below). Asserted on the raw helper too, so a
    # "helpful" default added here is caught even if _template() stopped grouping anything.
    assert "masterVarName" not in control
    # ...and a row that HAS one still carries it.
    tipped = mod_settings._slider(PROGRESS_HOLD_SECONDS_KEY, {"text": u"H", "tooltip": u"T"})
    assert tipped["tooltip"] == u"T"
    # End to end in the built template: the Slider hangs off the "Transitions" HEADER, NOT off the
    # "Enabled" master -- a plain top-level UNGROUPED row spliced on after the group. It must carry
    # NO masterVarName AT ALL: MSA reads the key's PRESENCE, so a None would still bind it to a
    # master named None, and any real value would grey it out (PROGRESS_TRANSITIONS_KEY would claim
    # the duration stops applying when the motion is off -- see progress_hold_seconds(), which is
    # deliberately NOT master-folded; PROGRESS_BAR_KEY would be the wrong feature entirely).
    # It does carry a real tooltip: the Transitions prose lives on the master and its label-only
    # children, but the Slider is a real value control, not a label-only switch.
    col2 = mod_settings._template()["column2"]
    slider = _at(col2, PROGRESS_HOLD_SECONDS_KEY)[0]
    assert slider["type"] == "Slider"
    assert "masterVarName" not in slider, \
        "the hold slider was re-parented into a group -- it must hang off the header (see " \
        "progress_hold_seconds: a duration is not master-folded, so it must not grey out)"
    # ...and it is not gated the OTHER way either (the _gate_and form REPLACES group parenting, so
    # an absent masterVarName alone would not notice a conditions-based gate).
    assert "conditions" not in slider and "masterIndent" not in slider
    assert slider["minimum"] == PROGRESS_HOLD_MIN
    assert slider["maximum"] == PROGRESS_HOLD_MAX
    assert slider["snapInterval"] == 1
    assert slider["format"] == "{{value}} s"
    assert slider["value"] == PROGRESS_HOLD_DEFAULT
    # ...while its two SIBLING switches DO stay grouped under the master -- the reparent moved one
    # control, not the group. Pinning both halves is what makes this a boundary rather than a
    # blanket "nothing in this category is grouped".
    assert [_at(col2, k)[0]["masterVarName"] for k in
            (PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY)] == \
        [PROGRESS_TRANSITIONS_KEY, PROGRESS_TRANSITIONS_KEY]


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
    # Bumped 14 -> 15 to add two more "Empty" spacer rows -- one heading "Transitions" in column 1,
    # one heading "Position" in column 2 -- purely visual, but the two new None-sentinel slots shift
    # every later control's positional pairing in _sync_template_text, so it is structural even
    # though no varName changed. The migration branch carries every saved value across unchanged.
    # Bumped 15 -> 16 for a THIRD "Empty" spacer, immediately ahead of the "Mode" radio in column 1
    # -- again purely visual (no tooltip moved, no varName touched), but the new None-sentinel slot
    # (COL1_KEYS 16 -> 17) shifts every later control's positional pairing, so it is structural
    # regardless. The migration branch carries every saved value across unchanged.
    # Bumped 16 -> 17 for the Transitions restructure plus a new varName, either of which alone
    # would owe it: "Transitions" is promoted to a CATEGORY of its own (a new bold Label header row
    # ahead of the master, shifting every later control's positional pairing), and the group gains a
    # FOURTH control -- progress_hold_seconds, a new varName AND a new component type (Slider), whose
    # minimum/maximum/snapInterval Aslain folds into _settingsStructure. COL1_KEYS 17 -> 19. The
    # master's label goes "Transitions" -> "Enabled" but its varName is deliberately UNCHANGED, so
    # the migration branch carries every saved value across and only the new key takes a default.
    # Bumped 17 -> 18 for the in-battle bar's Ctrl+drag POSITION controls: a FOURTH column-1
    # category ("Bar Position" -- an Empty spacer plus its own bold Label header) and the two
    # progress_bar_pos_x / progress_bar_pos_y NumericSteppers, i.e. two new varNames AND four new
    # rows (COL1_KEYS 19 -> 23). Structural twice over. The two new keys take their fresh 0 (=
    # auto) default, which is what leaves every existing user's bar on the shipped anchor.
    # Bumped 18 -> 19 for a FIFTH Empty spacer in column 1, immediately ahead of the hold-duration
    # Slider (COL1_KEYS 23 -> 24) -- no varName touched, but the new None-sentinel slot still
    # shifts the Slider's and every later control's positional pairing.
    # Bumped 19 -> 20 for the position steppers' `minimum: 0` -> `minimum: -POS_MAX` (both pairs).
    # The on-screen clamp is gone -- a bar may be dragged off any edge, storing a NEGATIVE
    # coordinate -- and MSA echoes a stepper's value back on change, so a stored descriptor still
    # bounded at 0 would snap that position to 0 the moment the panel was OPENED. No varName or row
    # moved, but a descriptor edit reaches an existing install ONLY through a forward bump
    # (register()'s saved-truthy path never calls setModTemplate), and Aslain folds
    # minimum/maximum/snapInterval into its _settingsStructure signature besides.
    # Bumped 20 -> 21 for the vertical-bar Orientation/Alignment radios: two new varNames, two new
    # standalone RadioButtonGroup rows spliced ABOVE the X/Y steppers in the fourth column-1
    # category (COL1_KEYS 24 -> 26), and that category's header TEXT changing "Bar Position" ->
    # "Layout" (the i18n key stays catBarPosition). The radios' OPTION LABELS are structural to
    # MSA too, so only this forward bump reaches an existing install; the migration branch
    # (_migrate_pre_v21_layout) is a LOOKUP keyed on the ABSENCE of progress_bar_orientation, not
    # arithmetic -- see that function.
    # Bumped 21 -> 22 for Free's stored frame (Trap 3 Fix B / DECISION 2): a new varName
    # (progress_bar_pos_frame) marking whether the CURRENT progress_bar_pos_x/_y pair is a
    # pre-v22 literal top-left ("legacy") or the new anchor point ("anchor"). No template
    # control/row/option changed shape -- the bump exists ONLY to reach the new key via
    # register()'s migration hook (a new varName is structural on its own). The migration
    # (_migrate_pre_v22_pos_frame) is a LOOKUP, not a conversion: it seeds the marker but defers
    # the actual pair conversion to bar_window.BarHost._materialise, the same materialise-on-mount
    # path Free's initial pin (DECISION 1) already owes.
    # Bumped 22 -> 23 for the Fixed-alignment redesign: the Alignment radio COLLAPSES from three
    # options (Damage Log / Minimap / Free) to two (Fixed / Free) -- an option reorder/removal is
    # structural to Aslain's _settingsStructure, so only a forward bump reaches an existing
    # install. The stored value is a 0-based INT INDEX, so this is ALSO a silent value migration:
    # raw 1 meant Minimap pre-bump and means Free post-bump. _migrate_pre_v23_alignment maps it
    # explicitly (old 0/1 -> Fixed, old 2 -> Free), running LAST in the chain, after
    # _migrate_pre_v21_layout / _migrate_pre_v22_pos_frame (both of which still speak the OLD
    # encoding). No varName was added, removed or renamed. This bump also retires the mutual
    # Orientation<->Alignment auto-set (_derive_layout): neither setting derives the other any
    # more, though an Orientation flip still zeroes the stored pair -- not part of the template.
    #
    # SAME-BUMP FOLLOW-ON (still v23 -- template-only / behaviour-only, no varName/control/option
    # changed shape): the two position steppers (barPosX/barPosY) now carry an enableWhen-shaped
    # gate on Alignment == Free (greyed under Fixed, not hidden -- a stepper that vanishes and
    # reappears reflows the column), and BarHost.drag() refuses the whole Ctrl+drag gesture under
    # Fixed. This ALSO retires the "position change forces Alignment := Free" rule (v21) from BOTH
    # _derive_layout and set_bar_position: with the gate + the drag block in place, a stored
    # position can only ever change while Alignment is ALREADY Free, so the rule has nothing left
    # to fire on.
    # Bumped 23 -> 24 for a pure COLUMN SWAP: column 1 now holds the In-Battle Calculator group
    # plus EVERY garage-related group ("Garage Widget" + its "Layout"/positioning group), and
    # column 2 now holds the WHOLE Progress Bar feature ("Battle Progress", the Mode/Scale radios,
    # "Transitions", the hold Slider, and the Progress Bar's own "Layout"/catBarPosition group) in
    # its previous internal order. No varName/control/option changed shape, but register()'s
    # saved-truthy path never calls setModTemplate on an existing install, so the new column
    # assignment (and the COL1_KEYS/COL2_KEYS positional pairing) reaches nobody without this
    # forward bump. The migration branch carries every saved value across unchanged.
    # Bumped 24 -> 25 to add two live preview Images (calcPreview in column 1's calculator group,
    # barPreview at the tail of column 2's Layout category -- see mod_settings's _image/_template).
    # A new template ROW is structural, and neither varName is a stored setting (both absent from
    # DEFAULTS -- updateImage addressing handles only), so no user loses a value across the bump.
    # Bumped 25 -> 26 for the in-battle mode-override HotKey control (progress_variant_hotkey),
    # spliced into column 2 right after the Mode radio -- a new varName AND a new component type,
    # either structural on its own. See mod_settings's own SETTINGS_VERSION comment.
    assert SETTINGS_VERSION == 26
    assert mod_settings._template()["settingsVersion"] == SETTINGS_VERSION


def test_template_column1_is_the_calculator_and_garage_groups():
    # RENAMED + REWRITTEN for the SETTINGS_VERSION 23->24 column swap: column 1 now holds the
    # In-Battle Calculator group (unchanged) plus EVERY garage-related group (moved here from
    # the old column 2). What used to be column 1's four Progress Bar categories now lives in
    # column 2 -- see test_template_column2_is_four_categories_each_a_label_then_its_group.
    tmpl = mod_settings._template()
    col1 = tmpl["column1"]
    # FIFTEEN controls: "Battle Calculator" + [In-Battle master, Alt child, counted-assist
    # child], the calcPreview Image (24->25 -- closes the calculator group), an Empty spacer, then
    # "Garage Widget" + [the standalone garage master -- no children of its own], a SECOND Empty
    # spacer, then the garage's "Layout" group -- its own bold header, Follow Carousel, a THIRD
    # Empty spacer, the non-bold "Position" sub-label, then the X/Y numeric steppers.
    assert [c["type"] for c in col1] == [
        "Label", "CheckBox", "CheckBox", "CheckBox",
        "Image",
        "Empty",
        "Label", "CheckBox",
        "Empty",
        "Label", "CheckBox",
        "Empty",
        "Label", "NumericStepper", "NumericStepper"]
    # The varName-bearing controls, in order (a Label header / an Empty spacer has no varName).
    # The calcPreview Image DOES carry a varName -- it is an updateImage addressing handle, not a
    # stored value (absent from DEFAULTS; see mod_settings.CALC_PREVIEW_KEY) -- so it sits in this
    # list right after countedAssist, closing the calculator group.
    assert [c["varName"] for c in col1 if "varName" in c] == [
        BATTLE_KEY, BATTLE_ALT_KEY, COUNTED_ASSIST_KEY,
        mod_settings.CALC_PREVIEW_KEY,
        GARAGE_KEY,
        FOLLOW_CAROUSEL_KEY,
        POS_X_KEY, POS_Y_KEY]
    # ...and the four Label rows carry no varName at all -- and they are the ONLY four, so no
    # group can quietly grow a header row of its own.
    assert ("varName" not in col1[0] and "varName" not in col1[6]
            and "varName" not in col1[9] and "varName" not in col1[12])
    assert [i for i, c in enumerate(col1) if c["type"] == "Label"] == [0, 6, 9, 12]
    # Three of the four headers are BOLD: <b>...</b> wrapped text and an explicit useHTML key.
    # "Position" (index 12) is deliberately NOT bold -- the weight difference marks it as a
    # sub-level under "Layout" rather than a fourth header.
    assert col1[0]["text"] == u"<b>Battle Calculator</b>" and col1[0]["useHTML"] is True
    assert col1[6]["text"] == u"<b>Garage Widget</b>" and col1[6]["useHTML"] is True
    assert col1[9]["text"] == u"<b>Layout</b>" and col1[9]["useHTML"] is True
    assert col1[12]["text"] == u"Position" and "useHTML" not in col1[12]
    # The calcPreview Image sits at index 4 (after the calculator group's three checkboxes), with
    # its source path, addressing-handle varName and a reserved container so a swap never reflows.
    assert col1[4]["type"] == "Image" and col1[4]["varName"] == mod_settings.CALC_PREVIEW_KEY
    assert col1[4]["source"].startswith(u"gui/maps/icons/") and col1[4]["source"].endswith(u".png")
    assert col1[4]["containerWidth"] and col1[4]["containerHeight"]
    # All THREE Empty spacers are a bare type and NOTHING else: no varName, and above all no
    # text/tooltip, which is what lets settings_i18n give each a `None` sentinel slot instead of a
    # key. The first heads "Garage Widget"; the second heads "Layout"; the third heads "Position".
    assert col1[5] == {"type": "Empty"}
    assert col1[8] == {"type": "Empty"}
    assert col1[11] == {"type": "Empty"}
    assert [i for i, c in enumerate(col1) if c["type"] == "Empty"] == [5, 8, 11]
    # The garage master carries no group at all -- it has no children of its own.
    assert "masterVarName" not in _at(col1, GARAGE_KEY)[0]
    # The steppers and Follow Carousel stay STANDALONE -- see
    # test_template_children_bind_to_their_own_master_only for the full gating assertions.
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
    col2 = mod_settings._template()["column2"]
    radio, index = _at(col2, PROGRESS_VARIANT_KEY)
    # POSITION, named rather than an index literal buried in a longer assertion: an Empty spacer
    # (new in this bump) now sits between the last visibility child and the Mode radio, and the
    # Scale radio still directly follows Mode, so the pair's order is what _sync_template_text's
    # positional zip walks.
    assert col2[_at(col2, PROGRESS_SHOW_ALWAYS_KEY)[1] + 1] == {"type": "Empty"}, \
        "a control was inserted between the last visibility child and the Mode radio's spacer"
    assert index == _at(col2, PROGRESS_SHOW_ALWAYS_KEY)[1] + 2
    # v26: the HotKey mode-override control now sits directly between Mode and Scale.
    assert index + 1 == _at(col2, PROGRESS_VARIANT_HOTKEY_KEY)[1]
    assert index + 2 == _at(col2, PROGRESS_SIZE_KEY)[1]
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
    # It DOES carry a label now ("Mode").
    assert radio["text"] == u"Mode"
    # ...and it now ALSO carries a tooltip -- a maintainer OVERRIDE (v15) of the "options say it
    # all" invariant this test used to protect: Mode's tooltip covers WHEN a mode switch takes
    # effect, which the option labels alone don't say. Assembled in the same {HEADER}/{BODY} shape
    # settings_i18n._render() builds for every other tooltipped row.
    assert radio["tooltip"] == u"{HEADER}%s{/HEADER}{BODY}%s{/BODY}" % (
        settings_i18n._PANEL[u"en"][settings_i18n.VARIANT_KEY][u"ttHeader"],
        settings_i18n._PANEL[u"en"][settings_i18n.VARIANT_KEY][u"ttBody"])
    master = _at(col2, PROGRESS_BAR_KEY)[0]
    assert u"Moving Average" in master["tooltip"]
    assert u"Damage Efficiency" in master["tooltip"]
    # LOCALIZED, not hardcoded here. The old `== list(settings_i18n.variant_options(u"en"))` line
    # was dropped rather than re-pointed at build(): comparing against build()'s own output can
    # never fail where the English literal above passes (they move together, and a hardcoded list
    # in _radio would MATCH build's English), so it was strictly weaker than the literal it sat
    # beside. This is the claim it was reaching for and the one that mutation-probes: swap the
    # source tuple and the descriptor must follow.
    monkeypatch.setitem(settings_i18n._VARIANT_OPTIONS, u"en", (u"AAA", u"BBB"))
    fresh = _at(mod_settings._template()["column2"], PROGRESS_VARIANT_KEY)[0]
    assert [o["label"] for o in fresh["options"]] == [u"AAA", u"BBB"], \
        "the radio's options are not read from settings_i18n"


def test_template_size_radio_shape(monkeypatch):
    # The SECOND options-bearing control, and the second non-bool value. Same hand-built
    # RadioButtonGroup shape as the variant's, and the same three traps -- an INT index in `value`
    # (never a bool), `inline` emitted as a KEY and never as createRadioButtonGroup's kwarg
    # (TypeError on MSA < 1.6.1), and LOCALIZED options read off settings_i18n rather than
    # hardcoded in _radio.
    col2 = mod_settings._template()["column2"]
    radio, index = _at(col2, PROGRESS_SIZE_KEY)
    # POSITION, anchored to NAMED neighbours rather than to a length: an Empty spacer and the
    # "Transitions" category header now sit between the Scale radio and the Transitions master, and
    # that master plus its two switches plus the ungrouped hold Slider are still a contiguous
    # FOUR-row run. So an insertion anywhere else (which shifts every later control's text --
    # COL2_KEYS' zip is positional) still fails here, while a legitimate append does not.
    assert col2[index + 1] == {"type": "Empty"}, \
        "a control was inserted between the Scale radio and its spacer"
    assert col2[index + 2]["type"] == "Label", \
        "the Transitions category header moved or disappeared"
    master_at = _at(col2, PROGRESS_TRANSITIONS_KEY)[1]
    assert index + 3 == master_at, \
        "the spacer + header ahead of the Transitions master moved or disappeared"
    # The group's THREE varName-bearing controls (master + two switches) are still a contiguous
    # run; the hold Slider is one further slot out, with a FIFTH Empty spacer (v19) between it and
    # "Alt Press" -- so the run is 5 rows wide, not 4, once that spacer joined.
    assert [c.get("varName") for c in col2[master_at:master_at + 3]] == [
        PROGRESS_TRANSITIONS_KEY, PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY], \
        "the Transitions group is no longer contiguous (COL2_KEYS' zip is positional)"
    assert col2[master_at + 3] == {"type": "Empty"}, \
        "the spacer ahead of the hold Slider moved or disappeared"
    assert col2[master_at + 4].get("varName") == PROGRESS_HOLD_SECONDS_KEY, \
        "the hold Slider moved (COL2_KEYS' zip is positional)"
    assert radio["type"] == "RadioButtonGroup"
    assert radio["value"] == DEFAULTS[PROGRESS_SIZE_KEY] == 0
    assert not isinstance(radio["value"], bool)
    assert [o["label"] for o in radio["options"]] == ["Default", "Large"]
    assert radio["inline"] is True
    # A label ("Scale") AND now a tooltip too -- the same maintainer override as the Mode radio
    # (v15): Scale has no explanation anywhere else in the panel, so its tooltip spells out what
    # the option words mean, in the same {HEADER}/{BODY} shape.
    assert radio["text"] == u"Scale"
    assert radio["tooltip"] == u"{HEADER}%s{/HEADER}{BODY}%s{/BODY}" % (
        settings_i18n._PANEL[u"en"]["progressSize"][u"ttHeader"],
        settings_i18n._PANEL[u"en"]["progressSize"][u"ttBody"])
    monkeypatch.setitem(settings_i18n._SIZE_OPTIONS, u"en", (u"AAA", u"BBB"))
    fresh = _at(mod_settings._template()["column2"], PROGRESS_SIZE_KEY)[0]
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
    col2 = mod_settings._template()["column2"]
    for child_key in (PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY):
        assert "tooltip" not in _at(col2, child_key)[0], \
            "%s grew a tooltip -- it is a label-only row" % child_key
    assert _at(col2, PROGRESS_TRANSITIONS_KEY)[0]["tooltip"], \
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


def test_template_column2_is_four_categories_each_a_label_then_its_group():
    # RENAMED + MOVED for the SETTINGS_VERSION 23->24 column swap: this is the WHOLE Progress Bar
    # feature -- what used to be column 1's tail (see the SETTINGS_VERSION 20->21 comment for its
    # own history) now lives in column 2, unchanged internally, alongside column 1's new
    # garage-related groups (test_template_column1_is_the_calculator_and_garage_groups).
    tmpl = mod_settings._template()
    col2 = tmpl["column2"]
    # TWENTY-THREE controls = FOUR CATEGORIES separated by Empty spacers, each a bare Label header
    # followed by that feature's controls: "Battle Progress" + [Progress Bar master + its three
    # VISIBILITY children] + a SECOND Empty spacer (ahead of "Mode") + [the Mode radio, its HotKey
    # mode-override sibling (v26), and the Scale radio -- all three standalone], then a THIRD Empty
    # spacer and "Transitions" -- its OWN header since the hold-duration Slider arrived -- +
    # [Transitions master, Events child, Alt Press child] + a FOURTH Empty spacer (ahead of the
    # Slider) + the UNGROUPED hold Slider, which hangs off that header rather than the master (its
    # masterVarName absence is pinned in test_slider_descriptor_shape_and_tipless_omission), and
    # finally a FIFTH Empty spacer and "Layout" (header text; i18n key stays catBarPosition) +
    # [the standalone Orientation/Alignment radios, ABOVE the two standalone position steppers],
    # then the barPreview Image APPENDED at the tail (24->25). The header names the feature, which
    # is why every master reads just "Enabled".
    assert [c["type"] for c in col2] == [
        "Label", "CheckBox", "CheckBox", "CheckBox", "CheckBox",
        "Empty",
        "RadioButtonGroup", "HotKey", "RadioButtonGroup",
        "Empty",
        "Label", "CheckBox", "CheckBox", "CheckBox",
        "Empty",
        "Slider",
        "Empty",
        "Label", "RadioButtonGroup", "RadioButtonGroup", "NumericStepper", "NumericStepper",
        "Image"]
    # The varName-bearing controls, in order (a Label header / an Empty spacer has no varName). The
    # barPreview Image DOES carry a varName -- an updateImage addressing handle, not a stored value
    # (absent from DEFAULTS; see mod_settings.BAR_PREVIEW_KEY) -- so it closes this list.
    assert [c["varName"] for c in col2 if "varName" in c] == [
        PROGRESS_BAR_KEY,
        PROGRESS_SHOW_EVENTS_KEY, PROGRESS_SHOW_ALT_KEY, PROGRESS_SHOW_ALWAYS_KEY,
        PROGRESS_VARIANT_KEY, PROGRESS_VARIANT_HOTKEY_KEY, PROGRESS_SIZE_KEY,
        PROGRESS_TRANSITIONS_KEY, PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY,
        PROGRESS_HOLD_SECONDS_KEY,
        PROGRESS_ORIENTATION_KEY, PROGRESS_ALIGNMENT_KEY,
        mod_settings.BAR_POS_X_KEY, mod_settings.BAR_POS_Y_KEY,
        mod_settings.BAR_PREVIEW_KEY]
    # ...and the two category headers carry no varName at all -- and they are the ONLY two here.
    assert "varName" not in col2[0] and "varName" not in col2[10] and "varName" not in col2[17]
    assert [i for i, c in enumerate(col2) if c["type"] == "Label"] == [0, 10, 17]
    # Every category header is BOLD: <b>...</b> wrapped text and an explicit useHTML key (MSA's
    # own HTML default is unverified from our side, so we emit it ourselves rather than rely on it).
    assert col2[0]["text"] == u"<b>Battle Progress</b>" and col2[0]["useHTML"] is True
    assert col2[10]["text"] == u"<b>Transitions</b>" and col2[10]["useHTML"] is True
    assert col2[17]["text"] == u"<b>Layout</b>" and col2[17]["useHTML"] is True
    # All FOUR Empty spacers are a bare type and NOTHING else: no varName, and above all no
    # text/tooltip, which is what lets settings_i18n give each a `None` sentinel slot instead of a
    # key. The first heads "Mode"; the second heads "Transitions"; the third heads the hold Slider;
    # the fourth heads "Layout".
    assert col2[5] == {"type": "Empty"}
    assert col2[9] == {"type": "Empty"}
    assert col2[14] == {"type": "Empty"}
    assert col2[16] == {"type": "Empty"}
    assert [i for i, c in enumerate(col2) if c["type"] == "Empty"] == [5, 9, 14, 16]
    # The Mode/HotKey/Scale trio are STANDALONE -- no masterVarName, no conditions -- so they stay
    # readable and editable while the Progress Bar master is off, exactly like column 1's steppers
    # used to be before they were gated.
    for control in col2[6:9]:
        assert "masterVarName" not in control and "conditions" not in control
    assert col2[6]["varName"] == PROGRESS_VARIANT_KEY
    assert col2[7]["type"] == "HotKey" and col2[7]["varName"] == PROGRESS_VARIANT_HOTKEY_KEY
    assert col2[8]["varName"] == PROGRESS_SIZE_KEY
    # The two Orientation/Alignment radios are ALSO STANDALONE -- see above. The two position
    # steppers ARE gated: see test_template_position_steppers_are_gated_on_alignment_free below.
    for control in col2[18:20]:
        assert "masterVarName" not in control and "conditions" not in control
    # The two radios sit directly between the "Layout" header and the two steppers.
    assert col2[18]["varName"] == PROGRESS_ORIENTATION_KEY
    assert col2[19]["varName"] == PROGRESS_ALIGNMENT_KEY
    assert col2[20]["varName"] == mod_settings.BAR_POS_X_KEY
    assert col2[21]["varName"] == mod_settings.BAR_POS_Y_KEY
    # The barPreview Image closes the column (index 22): source path, addressing-handle varName and
    # a reserved container sized for the widest/tallest bar so a swap never reflows the panel.
    assert col2[22]["type"] == "Image" and col2[22]["varName"] == mod_settings.BAR_PREVIEW_KEY
    assert col2[22]["source"].startswith(u"gui/maps/icons/") and col2[22]["source"].endswith(u".png")
    assert col2[22]["containerWidth"] and col2[22]["containerHeight"]
    # ...and still only TWO columns: a third column does not render in the panel at all.
    assert sorted(k for k in tmpl if re.match(r"^column\d+$", k)) == ["column1", "column2"]


def _find_desc(tmpl, key):
    """The descriptor bearing `key` as its varName, searched across every column the built
    template declares (column-agnostic -- mirrors _at, which only looks at one column list)."""
    for col, _keys in _column_pairs(tmpl):
        for c in tmpl[col]:
            if c.get("varName") == key:
                return c
    raise AssertionError("no control with varName %r in any column" % (key,))


def test_settings_version_bumped_for_hotkey_control():
    assert mod_settings.SETTINGS_VERSION == 26


def test_template_includes_hotkey_descriptor():
    tmpl = mod_settings._template()
    names = [c["varName"] for col, _keys in _column_pairs(tmpl)
             for c in tmpl[col] if "varName" in c]
    assert PROGRESS_VARIANT_HOTKEY_KEY in names
    desc = _find_desc(tmpl, PROGRESS_VARIANT_HOTKEY_KEY)
    assert desc["type"] == "HotKey"
    assert desc["value"] == [37]


def test_preview_source_names_map_every_driving_combo():
    # The pure preview-source picker: countedAssist toggles the calc PNG (3-row vs 2-row), and
    # (variant, orientation) picks one of the four bar PNGs. Confirmed against settings_i18n's
    # option order: variant 0 = Damage Efficiency / 1 = Moving Average, orientation 0 = Horizontal
    # / 1 = Vertical. All four bar combos + both calc states, so a swapped mapping fails loudly.
    E, MA = PROGRESS_VARIANT_EFFICIENCY, PROGRESS_VARIANT_MOVING_AVERAGE
    H, V = PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ORIENT_VERTICAL
    assert mod_settings.preview_source_names(True, E, H) == ("calc_assist_on", "bar_eff_horizontal")
    assert mod_settings.preview_source_names(False, E, V) == ("calc_assist_off", "bar_eff_vertical")
    assert mod_settings.preview_source_names(True, MA, H)[1] == "bar_ma_horizontal"
    assert mod_settings.preview_source_names(True, MA, V)[1] == "bar_ma_vertical"
    assert mod_settings.preview_source_names(True, E, V)[1] == "bar_eff_vertical"
    assert mod_settings.preview_source_names(False, E, H)[0] == "calc_assist_off"


def test_preview_sources_are_bare_relative_scaleform_paths():
    # preview_sources() reads the live getters and returns BARE-RELATIVE Scaleform resource paths
    # (NOT the Gameface img:// scheme -- MSA's Image feeds a Flash UILoaderAlt that can't resolve
    # img://; it needs a plain path like MSA's own gui/maps/icons/aslainMenu/icon.png).
    mod_settings._seed(dict(DEFAULTS))
    calc_src, calc_w, calc_h, bar_src, bar_w, bar_h = mod_settings.preview_sources()
    for src in (calc_src, bar_src):
        assert src.startswith(u"gui/maps/icons/moe_calculator/previews/")
        assert not src.startswith(u"img://")
        assert src.endswith(u".png")
    # Defaults: countedAssist on -> 3-row calc, variant Efficiency + Horizontal -> eff_horizontal.
    assert calc_src.endswith(u"calc_assist_on.png")
    assert bar_src.endswith(u"bar_eff_horizontal.png")
    # The dims must match _PREVIEW_DISPLAY for the default state (calc 125x73, bar 392x88 --
    # the bar's soft backdrop is now revealed at a wider/taller extent).
    assert (calc_w, calc_h) == mod_settings._PREVIEW_DISPLAY["calc_assist_on"] == (125, 73)
    assert (bar_w, bar_h) == mod_settings._PREVIEW_DISPLAY["bar_eff_horizontal"] == (392, 88)


def test_template_preview_images_carry_display_width_and_height():
    # The _image descriptors for both preview keys must carry explicit width/height so MSA
    # downscales the 4x-supersampled source -- a bare `source` with no dims was the pre-preview
    # shape and would leave the panel showing the PNG at its raw 4x size.
    mod_settings._seed(dict(DEFAULTS))
    tmpl = mod_settings._template()
    calc_img = _at(tmpl["column1"], mod_settings.CALC_PREVIEW_KEY)[0]
    bar_img = _at(tmpl["column2"], mod_settings.BAR_PREVIEW_KEY)[0]
    # width/height are the CURRENT source's display dims; containerWidth/Height reserve the
    # max slot across every swappable image, so a taller/wider swap never reflows the panel.
    assert (calc_img["width"], calc_img["height"]) == (125, 73)
    assert (bar_img["width"], bar_img["height"]) == (392, 88)
    assert (calc_img["containerWidth"], calc_img["containerHeight"]) == (
        mod_settings._CALC_PREVIEW_W, mod_settings._CALC_PREVIEW_H)
    assert (bar_img["containerWidth"], bar_img["containerHeight"]) == (
        mod_settings._BAR_PREVIEW_W, mod_settings._BAR_PREVIEW_H)


def test_update_preview_images_passes_the_display_dims_through(monkeypatch):
    # update_preview_images() must forward the SAME (w, h) preview_sources() computed, not just
    # the source path -- a regression here would silently drop back to an unscaled swap.
    mod_settings._seed(dict(DEFAULTS))
    calls = []

    class _FakeImageMsa(object):
        def updateImage(self, linkage, var_name, source, width, height):
            calls.append((linkage, var_name, source, width, height))

    fake = _FakeImageMsa()
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)
    mod_settings.update_preview_images()
    assert len(calls) == 2
    for linkage, var_name, source, width, height in calls:
        assert linkage == mod_settings.LINKAGE
        assert isinstance(width, int) and isinstance(height, int)
    calc_call = [c for c in calls if c[1] == mod_settings.CALC_PREVIEW_KEY][0]
    bar_call = [c for c in calls if c[1] == mod_settings.BAR_PREVIEW_KEY][0]
    assert (calc_call[3], calc_call[4]) == (125, 73)
    assert (bar_call[3], bar_call[4]) == (392, 88)


def test_template_steppers_are_bounded_manual_entry():
    # Each position stepper spans [-POS_MAX, POS_MAX], allows manual input and steps by 1 px so a
    # typed 0/0 returns the widget to auto and a nudge isn't rounded away.
    #
    # THE MINIMUM MUST BE NEGATIVE, on BOTH pairs: there is no on-screen safezone any more, so a bar
    # dragged off the left/top edge stores a negative coordinate -- and MSA echoes a stepper's value
    # back through onSettingsChanged, so a `minimum: 0` would snap that position to 0 as soon as the
    # user merely OPENED the panel. This is what the 19 -> 20 SETTINGS_VERSION bump exists to deliver.
    tmpl = mod_settings._template()
    steppers = [c for c in tmpl["column1"] if c["type"] == "NumericStepper"]
    assert [c["varName"] for c in steppers] == [POS_X_KEY, POS_Y_KEY]
    steppers += [c for c in tmpl["column2"] if c["type"] == "NumericStepper"]
    for s in steppers:
        assert s["minimum"] == -POS_MAX
        assert s["maximum"] == POS_MAX
        assert s["canManualInput"] is True
        assert s["snapInterval"] == 1


def test_template_position_steppers_are_gated_on_alignment_free():
    # The lock this dispatch adds: since MSA has no way to assign a peer control's value (no
    # "position change sets Alignment to Free" is expressible through the panel), the steppers
    # are greyed out unless Alignment is ALREADY Free -- an enableWhen-shaped binding
    # (masterVarName / masterValue / masterIndent / condition), keyed on the REAL Free value
    # rather than a hardcoded 1, so a future renumbering of the radio can't silently desync the
    # gate from the option it means to test.
    col2 = mod_settings._template()["column2"]
    x_stepper = _at(col2, mod_settings.BAR_POS_X_KEY)[0]
    y_stepper = _at(col2, mod_settings.BAR_POS_Y_KEY)[0]
    for stepper in (x_stepper, y_stepper):
        assert stepper["masterVarName"] == PROGRESS_ALIGNMENT_KEY
        assert stepper["masterValue"] == PROGRESS_ALIGN_FREE
        assert stepper.get("condition", "==") == "=="
        # NOT indented -- these are siblings, not sub-options of a createControlsGroup master.
        assert stepper["masterIndent"] is False
        # And NOT the multi-condition `conditions` form -- that shape would REPLACE this key
        # (see _gate_and), so its presence here would mean the single-master binding never took.
        assert "conditions" not in stepper


def test_template_children_bind_to_their_own_master_only():
    # Each group's children carry masterVarName == THEIR master's varName so MSA groups + greys
    # them out under it. Proven via the manual-binding fallback branch (no gui.aslainMenu under
    # pytest -- see _grouped_column1). The In-Battle Calculator group is column 1; the Progress
    # Bar / Transitions groups are column 2 (SETTINGS_VERSION 23->24 moved them).
    col1 = mod_settings._template()["column1"]
    col2 = mod_settings._template()["column2"]
    master = _at(col1, BATTLE_KEY)[0]
    alt_child = _at(col1, BATTLE_ALT_KEY)[0]
    counted_child = _at(col1, COUNTED_ASSIST_KEY)[0]
    progress = _at(col2, PROGRESS_BAR_KEY)[0]
    variant = _at(col2, PROGRESS_VARIANT_KEY)[0]
    size = _at(col2, PROGRESS_SIZE_KEY)[0]
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
    # already made for column 1's steppers. (A child of the FIRST group would have inherited
    # BATTLE_KEY and greyed out with the unrelated In-Battle Widget; that hazard is why this is
    # asserted rather than assumed.)
    for radio in (variant, size):
        assert "masterVarName" not in radio and "conditions" not in radio, \
            "%s gained a gate -- both radios are deliberately standalone" % radio["varName"]
    # The THREE VISIBILITY children. "Always" is a plain child of the Progress Bar master...
    always = _at(col2, PROGRESS_SHOW_ALWAYS_KEY)[0]
    assert always["masterVarName"] == PROGRESS_BAR_KEY
    assert "conditions" not in always
    # ...while "Events" and "Alt Press" are dead in TWO ways -- with the bar off and with "Always"
    # on -- so they carry MSA's multi-condition AND form instead. That form does NOT set
    # masterVarName, so it REPLACES the group parenting: the master has to ride along as one of the
    # conditions, and the stale key must be gone or the panel reads a parent the gate ignores.
    for key in (PROGRESS_SHOW_EVENTS_KEY, PROGRESS_SHOW_ALT_KEY):
        child = _at(col2, key)[0]
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
    trans = _at(col2, PROGRESS_TRANSITIONS_KEY)[0]
    assert "masterVarName" not in trans, \
        "the Transitions master was re-parented -- it is a group MASTER, not a child"
    for child_key in (PROGRESS_TRANS_EVENTS_KEY, PROGRESS_TRANS_MANUAL_KEY):
        child = _at(col2, child_key)[0]
        assert child["masterVarName"] == PROGRESS_TRANSITIONS_KEY, \
            "%s is gated by %r, not by the Transitions master" % (
                child_key, child.get("masterVarName"))
        assert child["masterVarName"] != PROGRESS_BAR_KEY
        assert child["masterVarName"] != BATTLE_KEY
    # The position steppers and Follow Carousel (column 1) and the standalone Orientation/
    # Alignment radios (column 2) stay STANDALONE: the garage steppers/Follow Carousel must keep
    # working, and stay ungreyed, while the garage widget is off (a deliberate decision, not an
    # oversight). `conditions` is checked too -- it is the OTHER way a control can acquire a gate.
    for control in (_at(col1, POS_X_KEY)[0], _at(col1, POS_Y_KEY)[0],
                    _at(col1, FOLLOW_CAROUSEL_KEY)[0]):
        assert "masterVarName" not in control and "conditions" not in control, \
            "%s gained a master -- these garage controls are deliberately standalone" % (
                control.get("varName"),)


def test_template_control_defaults_match_defaults_dict():
    # Each value-bearing control's initial `value` mirrors its DEFAULTS entry (varName ==
    # DEFAULTS key). Label headers and Empty spacers carry no varName/value and are skipped.
    # Covers the checkboxes, both radios, the hold Slider and the numeric steppers (steppers
    # default to 0 = auto), across EVERY column.
    tmpl = mod_settings._template()
    for col, _keys in _column_pairs(tmpl):
        for c in tmpl[col]:
            if c["type"] == "Image":          # a preview: has a varName but no stored `value`
                assert c["varName"] not in DEFAULTS and "value" not in c
                continue
            if "varName" not in c:            # a Label header / an Empty spacer
                assert c["type"] in ("Label", "Empty")
                continue
            assert c["type"] in ("CheckBox", "NumericStepper", "RadioButtonGroup", "Slider",
                                 "HotKey")
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
                # The text-less sentinel slot -- an Empty spacer OR a preview Image (an updateImage
                # addressing handle with no i18n text). Either way it must genuinely have no text,
                # or the sentinel is hiding a real control from the sync walk.
                assert control["type"] in ("Empty", "Image")
                assert "text" not in control and "tooltip" not in control
                sentinels += 1
                continue
            assert control["text"] == text[key]["text"]
            assert control.get("tooltip") == text[key].get("tooltip")
    # ...and every text-less row in the template is covered by one: a spacer/Image added without a
    # sentinel would shift the whole tail of the zip and silently retitle every control after it.
    # NINE now: SEVEN Empty spacers plus the TWO preview Images (calcPreview / barPreview, 24->25).
    assert sentinels == sum(1 for col, _k in _column_pairs(tmpl)
                            for c in tmpl[col] if c["type"] in ("Empty", "Image")) == 9


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
    # SIX tipless controls: the FOUR bare CATEGORY headers (Battle Calculator / Battle Progress /
    # Transitions / Garage Widget -- a feature name has nothing to explain and nothing to hover), and the
    # Transitions group's two children (Events / Alt Press) -- one-word switches whose meaning the
    # Transitions master's tooltip spells out. BOTH radios (Mode / Scale) and the "Position"
    # sub-label used to be tipless too (bringing the count to EIGHT), but a maintainer OVERRIDE
    # (v15) gave all three their own tooltip -- Mode/Scale describe the bar and its size beyond
    # what the option labels alone say, and "Position" explains that both steppers apply
    # immediately -- so they dropped OUT of this count. See settings_i18n's progressVariant /
    # progressSize / positionSub. The Progress Bar group's three VISIBILITY children (Events / Alt
    # Press / Always) dropped out earlier, in v14, the same way. The counter is the tripwire that
    # surfaced the _label tooltip hole in the first place, and it is what caught the SAME hole in
    # _checkbox: the Transitions children were the first tipless CHECKBOXES, and _checkbox
    # hard-indexed rendered["tooltip"], so building the template raised KeyError before this walk
    # was even reached. Keep it exact rather than a `>= 1`, because a NEW tipless row is exactly
    # the change that owes a bump (and a control LOSING its tipless status is the change this
    # bump made). v16 added a THIRD Empty spacer (ahead of "Mode") but moved no tooltip, so that
    # bump left this count alone -- a pure-layout bump can grow the spacer count without touching
    # this one, and pinning both separately is what proves that. v17 took it 5 -> 6: "Transitions"
    # became a CATEGORY, so it gained a fourth bare header row (the new hold-duration Slider does
    # carry a tooltip, and the master kept the one it always had). v18 took it 6 -> 8: the "Bar
    # Position" category's two NumericSteppers are label-only rows -- their axis hint says it all
    # and the header above them carries the Ctrl+drag prose, exactly as the Transitions children
    # sit under theirs. That header is NOT in this count: it is the one category header that DOES
    # carry a tooltip (the column-2 "Layout" header is its precedent).
    assert tipless == 8, "expected 8 tooltip-less controls, got %d" % tipless
    # v19 added a FIFTH column-1 Empty spacer (ahead of the hold Slider) but moved no tooltip, so
    # it grew the spacer count alone -- same as v16's spacer-only bump.
    # NINE None-keyed rows now: the SEVEN Empty spacers plus the TWO preview Images (24->25), all
    # walked and left untouched (see the sentinel branch above -- an Image is text-less too).
    assert spacers == 9, "expected 9 text-less None-keyed rows, got %d" % spacers
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


# --- _sync_template_text also rewrites options[].label (the four standalone radios' option
# words), not just text/tooltip -- REGRESSION for a real bug: an existing install kept its
# stored radio options in English forever after a client-language change, because nothing
# had ever rewritten options[] before this fix. ------------------------------------------

def _find_by_varname(tmpl, var_key):
    """The one control across every column carrying this varName -- scoping helper so each
    assertion below targets the SPECIFIC radio under test, not a shared/leaked value."""
    for col in tmpl:
        if not re.match(r"^column\d+$", col):
            continue
        for c in tmpl[col]:
            if isinstance(c, dict) and c.get("varName") == var_key:
                return c
    raise AssertionError("%s not found in the built template" % var_key)


_RADIO_KEYS = ((PROGRESS_VARIANT_KEY, settings_i18n.VARIANT_KEY),
               (PROGRESS_SIZE_KEY, u"progressSize"),
               (PROGRESS_ORIENTATION_KEY, u"progressOrientation"),
               (PROGRESS_ALIGNMENT_KEY, u"progressAlignment"))


def test_sync_template_text_rewrites_option_labels_on_language_change(monkeypatch):
    # A stored template built at English, re-synced while the client resolves to German, must
    # end with the GERMAN option labels on all four radios (Mode/Scale/Orientation/Alignment)
    # -- this is the exact upgrade-path fix: MSA never rewrote options[] on its own.
    tmpl = mod_settings._template()  # built at the default (English) language
    monkeypatch.setattr(settings_i18n, "client_language", lambda: u"de")
    de_text = settings_i18n.build(u"de")

    class _FakeApi(object):
        state = {"templates": {LINKAGE: tmpl}}

        def __init__(self):
            self.calls = 0

        def saveState(self):
            self.calls += 1

    api = _FakeApi()
    mod_settings._sync_template_text(api)

    for var_key, text_key in _RADIO_KEYS:
        comp = _find_by_varname(tmpl, var_key)
        expected = list(de_text[text_key]["options"])
        assert [o["label"] for o in comp["options"]] == expected, (
            "%s options were not rewritten to the German labels" % var_key)
        # item 4: the stored value/index itself must never move -- only the label text changes.
        assert comp["value"] == DEFAULTS[var_key]
    assert api.calls == 1, "a real change must call saveState()"


def test_sync_template_text_options_no_op_on_second_sync(monkeypatch):
    # A second sync with nothing left to change must rewrite nothing and must NOT call
    # saveState() again -- assert the CALL COUNT, not just the value, since a no-op mutation
    # and a fail-soft branch look identical from the value alone.
    tmpl = mod_settings._template()
    monkeypatch.setattr(settings_i18n, "client_language", lambda: u"de")

    class _FakeApi(object):
        state = {"templates": {LINKAGE: tmpl}}

        def __init__(self):
            self.calls = 0

        def saveState(self):
            self.calls += 1

    api = _FakeApi()
    mod_settings._sync_template_text(api)          # first pass: real rewrite, one save
    assert api.calls == 1
    snapshot = {var_key: [dict(o) for o in _find_by_varname(tmpl, var_key)["options"]]
                for var_key, _tk in _RADIO_KEYS}

    mod_settings._sync_template_text(api)          # second pass: already in sync

    assert api.calls == 1, "a no-op sync must not call saveState() a second time"
    for var_key, _tk in _RADIO_KEYS:
        assert _find_by_varname(tmpl, var_key)["options"] == snapshot[var_key]


def test_sync_template_text_skips_options_on_count_mismatch(monkeypatch):
    # THE safety guard: a stored options list whose length disagrees with the freshly rendered
    # tuple (a structural drift that only a SETTINGS_VERSION bump may fix -- a stored index
    # would otherwise suddenly name a different option) must be left BYTE-FOR-BYTE untouched,
    # not partially patched.
    tmpl = mod_settings._template()
    monkeypatch.setattr(settings_i18n, "client_language", lambda: u"de")

    drifted = _find_by_varname(tmpl, PROGRESS_ALIGNMENT_KEY)
    drifted["options"].append({"label": u"EXTRA"})   # simulate a stale, mismatched store
    before_options = [dict(o) for o in drifted["options"]]
    before_value = drifted["value"]

    other = _find_by_varname(tmpl, PROGRESS_ORIENTATION_KEY)
    before_other_options = [dict(o) for o in other["options"]]

    class _FakeApi(object):
        state = {"templates": {LINKAGE: tmpl}}

        def saveState(self):
            pass

    mod_settings._sync_template_text(_FakeApi())

    assert drifted["options"] == before_options, (
        "a count mismatch must leave that component's options untouched")
    assert drifted["value"] == before_value        # item 4: value never touched either
    # the mismatch must be scoped to the ONE drifted component -- a sibling radio with a
    # matching count still gets rewritten normally.
    de_text = settings_i18n.build(u"de")
    assert [o["label"] for o in other["options"]] == list(
        de_text[u"progressOrientation"]["options"])
    assert other["options"] != before_other_options


def test_sync_template_text_options_fail_soft(monkeypatch):
    # A missing/None `options` key, a non-dict option entry, and a rendered row with no
    # options of its own must never raise -- the count-match guard alone isn't enough if the
    # shapes themselves are unexpected.
    monkeypatch.setattr(settings_i18n, "client_language", lambda: u"de")
    variant_opts = settings_i18n.build(u"de")[settings_i18n.VARIANT_KEY]["options"]

    tmpl = {
        "column1": [
            {"type": "RadioButtonGroup", "varName": PROGRESS_VARIANT_KEY,
             "text": u"stale", "value": 0},                        # no "options" key at all
            {"type": "RadioButtonGroup", "varName": PROGRESS_SIZE_KEY,
             "text": u"stale", "value": 0, "options": None},        # options explicitly None
            {"type": "RadioButtonGroup", "varName": PROGRESS_ORIENTATION_KEY,
             "text": u"stale", "value": 0,
             "options": ["not-a-dict"] * len(variant_opts)},        # non-dict option entries
            {"type": "Label", "text": u"stale",                     # a rendered row with no
             "options": [{"label": u"leftover"}]},                  # options of its own
        ],
        "column2": [],
    }
    keys = (settings_i18n.VARIANT_KEY, u"progressSize", u"progressOrientation",
            u"catBattleCalc")
    monkeypatch.setattr(settings_i18n, "COL1_KEYS", keys)
    monkeypatch.setattr(settings_i18n, "COL2_KEYS", ())

    class _FakeApi(object):
        state = {"templates": {LINKAGE: tmpl}}

        def saveState(self):
            pass

    mod_settings._sync_template_text(_FakeApi())   # must not raise

    assert "options" not in tmpl["column1"][0]                       # never invented
    assert tmpl["column1"][1]["options"] is None                     # left exactly as-is
    assert tmpl["column1"][2]["options"] == ["not-a-dict"] * len(variant_opts)
    assert tmpl["column1"][3]["options"] == [{"label": u"leftover"}]


# --- drag-to-reposition: clamp_pos, accessors, set_position, follow_carousel, reset --------

def test_clamp_pos_bounds():
    # 0/0 = auto/unseeded; non-numeric collapses to 0; either MAGNITUDE bound clamps.
    assert clamp_pos(0) == 0
    assert clamp_pos(123) == 123
    assert clamp_pos(POS_MAX) == POS_MAX
    assert clamp_pos(POS_MAX + 1) == POS_MAX
    assert clamp_pos(10 ** 9) == POS_MAX
    # A NEGATIVE IS A REAL POSITION, not garbage: a bar dragged off the left/top edge stores one, and
    # collapsing it to 0 would both teleport the bar and (at 0/0) silently un-pin it.
    assert clamp_pos(-1) == -1
    assert clamp_pos(-9999) == -9999
    assert clamp_pos(-POS_MAX) == -POS_MAX
    assert clamp_pos(-POS_MAX - 1) == -POS_MAX
    assert clamp_pos(-10 ** 9) == -POS_MAX
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
    # A getter re-clamps whatever is cached, so a corrupt store never leaks a bad px out -- but only
    # the MAGNITUDE is corrupt-able now: a negative is a legal off-screen position.
    mod_settings._seed(dict(DEFAULTS))
    mod_settings._settings[POS_X_KEY] = -50
    mod_settings._settings[POS_Y_KEY] = POS_MAX + 500
    assert pos_x() == -50
    assert pos_y() == POS_MAX
    mod_settings._settings[POS_X_KEY] = -POS_MAX - 500
    mod_settings._settings[POS_Y_KEY] = "nope"
    assert pos_x() == -POS_MAX
    assert pos_y() == 0


def test_follow_carousel_default_true_and_getter():
    mod_settings._seed(dict(DEFAULTS))
    assert follow_carousel() is True
    mod_settings._apply({FOLLOW_CAROUSEL_KEY: False})
    assert follow_carousel() is False
    mod_settings._apply({FOLLOW_CAROUSEL_KEY: 1})   # coerced to bool
    assert follow_carousel() is True


class _FakeMsa(object):
    """A stand-in ModsSettingsAPI sink: returns a stored dict from getModSettings and records
    the full dict written by updateModSettings + whether saveState flushed it.

    write_count/save_count exist ALONGSIDE written/saved (not a replacement) so a loop-guard test
    can assert the CALL COUNT: the resulting VALUE is identical whether a handler wrote once or
    fired a second redundant write, so only the count can see the difference."""
    def __init__(self, current):
        self._current = current
        self.written = None
        self.saved = False
        self.write_count = 0
        self.save_count = 0

    def getModSettings(self, linkage, template):
        return dict(self._current)

    def updateModSettings(self, linkage, data):
        self.written = data
        self.write_count += 1

    def saveState(self):
        self.saved = True
        self.save_count += 1


class _ReentrantFakeMsa(_FakeMsa):
    """Like _FakeMsa, but updateModSettings synchronously re-fires onSettingsChanged with a
    STALE (pre-derivation) snapshot before returning -- the hostile case Trap 1(c)'s _deriving
    latch defends against (including a buggy/hostile host firing the callback from inside its
    own write call)."""
    def __init__(self, current, stale_payload):
        _FakeMsa.__init__(self, current)
        self._stale_payload = stale_payload
        self._fired_reentrant = False

    def updateModSettings(self, linkage, data):
        _FakeMsa.updateModSettings(self, linkage, data)
        if not self._fired_reentrant:
            self._fired_reentrant = True
            mod_settings._on_changed(LINKAGE, self._stale_payload)


def test_on_changed_deriving_latch_survives_a_synchronous_reentrant_stale_echo(monkeypatch):
    # A SYNCHRONOUS re-entrant onSettingsChanged fired from inside updateModSettings, carrying
    # the user's STALE pre-derivation values, must not trigger a second derivation/write -- the
    # _deriving latch must still settle on the user's actual intent (Vertical, position zeroed,
    # Alignment UNTOUCHED -- v23 retired the Orientation-forces-Alignment rule), and the call
    # count -- not just the value -- proves the guard held.
    _seed_live(PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_FIXED, x=900, y=500)
    stale_payload = {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_HORIZONTAL,
                     PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FREE,
                     BAR_POS_X_KEY: 777, BAR_POS_Y_KEY: 888}
    fake = _ReentrantFakeMsa({"enabled": True}, stale_payload)
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)

    mod_settings._on_changed(LINKAGE, {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL})

    assert fake.write_count == 1, "the reentrant echo must not trigger a second write"
    assert fake.written[PROGRESS_ORIENTATION_KEY] == PROGRESS_ORIENT_VERTICAL
    assert fake.written[PROGRESS_ALIGNMENT_KEY] == PROGRESS_ALIGN_FIXED
    assert (fake.written[BAR_POS_X_KEY], fake.written[BAR_POS_Y_KEY]) == (0, 0)
    assert mod_settings._deriving is False, "the latch must be released after the write-back"


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
    assert pos_x() == -5                # a negative is a legal off-screen position, not garbage
    assert pos_y() == POS_MAX           # clamped (magnitude ceiling)
    assert pos_w() == 1920
    assert pos_h() == 1080


def test_on_reset_forces_auto_position_and_follow_on():
    # The per-mod Reset must snap the position back to auto (0/0/0/0) and Follow Carousel Mode
    # back ON, overriding any stale pin the host reset snapshot may still carry. It must also
    # force the in-battle bar's position to auto (0/0) and Orientation/Alignment back to
    # Horizontal/Damage Log -- 0/0 IS the Damage Log anchor, so a reset panel is internally
    # consistent -- regardless of any seeded value the host snapshot still carries.
    mod_settings._seed({GARAGE_KEY: True, BATTLE_KEY: True,
                        POS_X_KEY: 500, POS_Y_KEY: 300, POS_W_KEY: 1920, POS_H_KEY: 1080,
                        BAR_POS_X_KEY: 810, BAR_POS_Y_KEY: 640,
                        PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL,
                        PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_MINIMAP,
                        FOLLOW_CAROUSEL_KEY: False})
    mod_settings._on_reset(LINKAGE, {POS_X_KEY: 999, POS_Y_KEY: 888,
                                     BAR_POS_X_KEY: 777, BAR_POS_Y_KEY: 666,
                                     PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL,
                                     PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FREE,
                                     FOLLOW_CAROUSEL_KEY: False})
    assert (pos_x(), pos_y(), pos_w(), pos_h()) == (0, 0, 0, 0)
    assert (bar_pos_x(), bar_pos_y()) == (0, 0)
    assert mod_settings.progress_bar_orientation() == PROGRESS_ORIENT_HORIZONTAL
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_DAMAGE_LOG
    assert follow_carousel() is True


def test_on_reset_ignores_foreign_linkage():
    # onResetMod fires globally; a foreign mod's reset must not wipe our pin / follow flag.
    mod_settings._seed({GARAGE_KEY: True, BATTLE_KEY: True,
                        POS_X_KEY: 500, POS_Y_KEY: 300,
                        FOLLOW_CAROUSEL_KEY: False})
    mod_settings._on_reset("com.someone.othermod", {})
    assert pos_x() == 500
    assert pos_y() == 300


def test_bar_position_accessors_round_trip_and_clamp():
    mod_settings._seed(dict(DEFAULTS))
    assert (bar_pos_x(), bar_pos_y()) == (0, 0)
    mod_settings._apply({BAR_POS_X_KEY: 810, BAR_POS_Y_KEY: 640})
    assert bar_pos_x() == 810
    assert bar_pos_y() == 640
    # A getter re-clamps whatever is cached, same as pos_x/pos_y -- and a NEGATIVE survives, because
    # a bar dragged off the left/top edge stores one (there is no on-screen safezone).
    mod_settings._settings[BAR_POS_X_KEY] = -50
    mod_settings._settings[BAR_POS_Y_KEY] = POS_MAX + 500
    assert bar_pos_x() == -50
    assert bar_pos_y() == POS_MAX


def test_set_bar_position_live_drag_does_not_persist(monkeypatch):
    # persist=False (every mouse move during a drag): the in-memory value updates so _resolve
    # sees it immediately, but MSA is never touched -- no updateModSettings, no saveState.
    mod_settings._seed(dict(DEFAULTS))
    fake = _FakeMsa({"enabled": True})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)

    set_bar_position(120, 240, persist=False)

    assert (bar_pos_x(), bar_pos_y()) == (120, 240)
    assert fake.written is None
    assert fake.saved is False


def test_set_bar_position_mouseup_persists(monkeypatch):
    # persist=True (the mouse-up): the full settings dict is written through MSA and flushed,
    # same replace-not-merge contract as set_position.
    mod_settings._seed(dict(DEFAULTS))
    fake = _FakeMsa({"enabled": True, "someHostKey": 7})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)

    set_bar_position(120, 240, persist=True)

    assert (bar_pos_x(), bar_pos_y()) == (120, 240)
    assert fake.saved is True
    data = fake.written
    assert data is not None
    assert data[BAR_POS_X_KEY] == 120
    assert data[BAR_POS_Y_KEY] == 240
    assert data["someHostKey"] == 7   # preserved, not clobbered


def test_set_bar_position_clamps_and_survives_absent_msa(monkeypatch):
    mod_settings._seed(dict(DEFAULTS))
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: None)
    set_bar_position(-5, POS_MAX + 100, persist=True)
    assert bar_pos_x() == -5             # off the left edge: kept, not snapped back on screen
    assert bar_pos_y() == POS_MAX        # clamped (magnitude ceiling)


def test_set_bar_position_always_marks_the_pair_as_the_anchor_frame():
    # v22 (Trap 3 Fix B): EVERY caller of set_bar_position -- a drag end, a live drag move, or
    # BarHost._materialise's own conversion write -- hands it a value that IS already in the new
    # anchor-point frame, so the frame marker flips unconditionally, even starting from "legacy"
    # (this is also what flips a pre-v22 legacy pin the first time _materialise converts it).
    mod_settings._seed(_defaults_with({
        mod_settings.PROGRESS_POS_FRAME_KEY: mod_settings.POS_FRAME_LEGACY}))
    assert mod_settings.progress_bar_pos_frame() == mod_settings.POS_FRAME_LEGACY
    set_bar_position(120, 240, persist=False)
    assert mod_settings.progress_bar_pos_frame() == mod_settings.POS_FRAME_ANCHOR


def test_set_bar_positions_echo_writes_nothing_through_on_changed(monkeypatch):
    # THE STEP 5 CONFIRMATION, done for real rather than assumed: whatever writes the anchor pair
    # back (a drag end, or BarHost._materialise's own conversion) is, from _on_changed's point of
    # view, indistinguishable from any other position write -- MSA's echo carries exactly what was
    # just written, Orientation is UNCHANGED, so _derive_layout returns `post` verbatim and nothing
    # is dirty; the echoed pass writes NOTHING. Alignment stays Free throughout -- set_bar_position
    # no longer sets it at all (this dispatch); both its callers already gate on Alignment being
    # Free before they ever get here.
    _seed_live(PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_FREE, x=0, y=0)
    fake = _FakeMsa({"enabled": True})
    monkeypatch.setattr(mod_settings, "_primary_api", lambda: fake)

    set_bar_position(239, 314, persist=True)   # e.g. BarHost._materialise's own conversion write
    assert fake.write_count == 1
    assert fake.save_count == 1

    echoed = dict(fake.written)
    mod_settings._on_changed(LINKAGE, echoed)
    assert fake.write_count == 1, "the materialise write's echo re-fired updateModSettings"
    assert fake.save_count == 1, "the materialise write's echo re-fired saveState"
    assert (mod_settings.bar_pos_x(), mod_settings.bar_pos_y()) == (239, 314)
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FREE


def test_coerce_types_per_key():
    # Position keys coerce to clamped ints, the progress-bar variant AND size to clamped radio
    # indices (see test_coerce_variant_key_is_not_booled / test_coerce_size_key_is_not_booled),
    # every other key to bool. Both radios are named here so a key that loses its branch fails on
    # THIS test too, not only on its own.
    assert mod_settings._coerce(POS_X_KEY, "640") == 640
    assert mod_settings._coerce(POS_Y_KEY, -3) == -3          # negatives are legal positions now
    assert mod_settings._coerce(POS_Y_KEY, "nope") == 0
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
        PROGRESS_HOLD_SECONDS_KEY: 12,      # default 5 s
        POS_X_KEY: 700, POS_Y_KEY: 300, # default 0 (auto)
        POS_W_KEY: 1920, POS_H_KEY: 1080,
        mod_settings.BAR_POS_X_KEY: 810,    # default 0 (auto -- the shipped bar anchor)
        mod_settings.BAR_POS_Y_KEY: 640,
        FOLLOW_CAROUSEL_KEY: False,     # default True
    }
    # progress_bar_orientation / progress_bar_alignment / progress_bar_pos_frame are DELIBERATELY
    # ABSENT from `old`: this store is pre-v21 (the whole point of the fixture), and none of these
    # three keys existed before v21/v22 -- their value is DERIVED by _migrate_pre_v21_layout /
    # _migrate_pre_v22_pos_frame, not carried across like every other key here, so they are
    # checked separately below instead of by this "must differ" loop. PROGRESS_VARIANT_HOTKEY_KEY
    # is likewise absent -- it postdates this store and has no migration wiring yet (a later task).
    for key in DEFAULTS:
        if key in (PROGRESS_ORIENTATION_KEY, PROGRESS_ALIGNMENT_KEY,
                   mod_settings.PROGRESS_POS_FRAME_KEY, PROGRESS_VARIANT_HOTKEY_KEY):
            continue
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
    # ...and the hold DURATION, the third non-bool value: an int seconds count out the other side,
    # never booled into True by _coerce's default branch, and NOT master-folded to 0 by the
    # Transitions master being off above (a duration is not a switch).
    assert mod_settings.progress_hold_seconds() == 12
    assert not isinstance(mod_settings._settings[PROGRESS_HOLD_SECONDS_KEY], bool)
    assert (mod_settings.pos_x(), mod_settings.pos_y()) == (700, 300)
    assert (mod_settings.pos_w(), mod_settings.pos_h()) == (1920, 1080)
    assert mod_settings.follow_carousel() is False
    # ...and the two v21 keys, which this store never had: _migrate_pre_v21_layout DERIVES them
    # rather than carrying a stored value across. Orientation always seeds Horizontal (the only
    # axis that existed pre-v21); Alignment seeds Free because the stored bar position (810, 640)
    # is non-zero -- exactly what Alignment=Free means -- and the coordinates themselves carry
    # across verbatim via the normal DEFAULTS overlay above (bar_pos_x()/bar_pos_y() == 810/640,
    # not asserted again here since BAR_POS_X_KEY/BAR_POS_Y_KEY aren't exposed by name in this
    # test's imports; see the dedicated test below for both migration branches in isolation).
    assert mod_settings.progress_bar_orientation() == PROGRESS_ORIENT_HORIZONTAL
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FREE
    assert not isinstance(mod_settings._settings[PROGRESS_ORIENTATION_KEY], bool)
    assert not isinstance(mod_settings._settings[PROGRESS_ALIGNMENT_KEY], bool)
    # ...and the v22 key: this pre-v21 (hence pre-v22) store has just been migrated to
    # Alignment=Free with a non-(0, 0) pair (810, 640) -- exactly the shape _migrate_pre_v22_
    # pos_frame marks "legacy" (the pair is still a literal top-left, pending BarHost._materialise
    # converting it at this bar's next battle mount).
    assert mod_settings.progress_bar_pos_frame() == mod_settings.POS_FRAME_LEGACY

    # ...and the same survived to DISK, in one coalesced write (the transient reset never lands).
    written = api.state["settings"][LINKAGE]
    for key, value in old.items():
        assert written[key] == value, "%s was wiped by the settingsVersion bump" % key
    # ...and the DERIVED keys reached disk too, at exactly the values just asserted live.
    assert written[PROGRESS_ORIENTATION_KEY] == PROGRESS_ORIENT_HORIZONTAL
    assert written[PROGRESS_ALIGNMENT_KEY] == PROGRESS_ALIGN_FREE
    assert written[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_LEGACY
    assert api.updated == 1
    assert api.saved == 1


def test_migrate_pre_v21_layout_non_zero_position_means_free_alignment():
    # ONE branch of the fixup: a pre-v21 store's non-zero (progress_bar_pos_x, progress_bar_pos_y)
    # was an ABSOLUTE top-left, exactly what Alignment=Free means -- so it seeds Free and the
    # coordinates are left untouched (the caller's normal DEFAULTS overlay carries them across, not
    # this function). Orientation always seeds Horizontal (the only axis that existed pre-v21).
    #
    # ASSERTS THE OLD (PRE-v23) ENCODING -- literal 2, not the symbolic PROGRESS_ALIGN_FREE (now
    # 1): this fixup runs BEFORE _migrate_pre_v23_alignment in register()'s chain and still writes
    # the 3-option encoding that was live when it was written (see its own docstring).
    old = {BAR_POS_X_KEY: 810, BAR_POS_Y_KEY: 640}
    mod_settings._migrate_pre_v21_layout(old)
    assert old[PROGRESS_ORIENTATION_KEY] == PROGRESS_ORIENT_HORIZONTAL
    assert old[PROGRESS_ALIGNMENT_KEY] == 2   # the pre-v23 Free index
    assert (old[BAR_POS_X_KEY], old[BAR_POS_Y_KEY]) == (810, 640)   # untouched, not re-derived


def test_migrate_pre_v21_layout_zero_position_means_damage_log_alignment():
    # THE OTHER branch: a zero (or absent) pair means the bar was on the shipped anchor, so it
    # seeds Damage Log -- still 0/0, the byte-identical shipped placement. Nobody's bar moves.
    old = {BAR_POS_X_KEY: 0, BAR_POS_Y_KEY: 0}
    mod_settings._migrate_pre_v21_layout(old)
    assert old[PROGRESS_ORIENTATION_KEY] == PROGRESS_ORIENT_HORIZONTAL
    assert old[PROGRESS_ALIGNMENT_KEY] == PROGRESS_ALIGN_DAMAGE_LOG

    # Absent keys behave exactly like a stored zero (clamp_pos's own 0 fallback).
    absent = {}
    mod_settings._migrate_pre_v21_layout(absent)
    assert absent[PROGRESS_ORIENTATION_KEY] == PROGRESS_ORIENT_HORIZONTAL
    assert absent[PROGRESS_ALIGNMENT_KEY] == PROGRESS_ALIGN_DAMAGE_LOG


def test_migrate_pre_v21_layout_leaves_a_v21plus_store_untouched():
    # A store that ALREADY carries progress_bar_orientation is >= v21 and must be left exactly as
    # the user set it -- even a corrupt/out-of-range value, which is `_coerce`'s job to clamp on
    # read, not this fixup's.
    at_v21 = {PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL, BAR_POS_X_KEY: 0, BAR_POS_Y_KEY: 0}
    mod_settings._migrate_pre_v21_layout(at_v21)
    assert at_v21[PROGRESS_ORIENTATION_KEY] == PROGRESS_ORIENT_VERTICAL   # untouched
    assert PROGRESS_ALIGNMENT_KEY not in at_v21   # never added -- the whole function short-circuits


def test_migrate_pre_v22_pos_frame_marks_legacy_only_for_a_nonzero_free_pin():
    # ONLY a store that is ALREADY Alignment=Free with a non-(0, 0) pair has a legacy top-left to
    # convert -- everything else (any other alignment, or Free still at the (0, 0) "not yet
    # materialised" marker) has no legacy pair at all, so it seeds straight to "anchor".
    #
    # ASSERTS THE OLD (PRE-v23) ENCODING -- literal 2 for Free, not the symbolic
    # PROGRESS_ALIGN_FREE (now 1): this fixup runs BEFORE _migrate_pre_v23_alignment and still
    # reads the 3-option encoding that was live when it was written (see its own docstring).
    free_pinned = {PROGRESS_ALIGNMENT_KEY: 2,   # the pre-v23 Free index
                  BAR_POS_X_KEY: 810, BAR_POS_Y_KEY: 640}
    mod_settings._migrate_pre_v22_pos_frame(free_pinned)
    assert free_pinned[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_LEGACY

    free_unmaterialised = {PROGRESS_ALIGNMENT_KEY: 2,   # the pre-v23 Free index
                           BAR_POS_X_KEY: 0, BAR_POS_Y_KEY: 0}
    mod_settings._migrate_pre_v22_pos_frame(free_unmaterialised)
    assert free_unmaterialised[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_ANCHOR

    damage_log = {PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_DAMAGE_LOG,
                 BAR_POS_X_KEY: 810, BAR_POS_Y_KEY: 640}
    mod_settings._migrate_pre_v22_pos_frame(damage_log)
    assert damage_log[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_ANCHOR

    minimap = {PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_MINIMAP}
    mod_settings._migrate_pre_v22_pos_frame(minimap)
    assert minimap[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_ANCHOR

    # Absent alignment behaves like Damage Log (clamp_variant's own fallback).
    absent = {}
    mod_settings._migrate_pre_v22_pos_frame(absent)
    assert absent[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_ANCHOR


def test_migrate_pre_v22_pos_frame_leaves_a_v22plus_store_untouched():
    # A store that ALREADY carries progress_bar_pos_frame is >= v22 and must be left exactly as
    # it is -- even if it would otherwise look "legacy" by position/alignment alone.
    at_v22 = {mod_settings.PROGRESS_POS_FRAME_KEY: mod_settings.POS_FRAME_ANCHOR,
             PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FREE,
             BAR_POS_X_KEY: 810, BAR_POS_Y_KEY: 640}
    mod_settings._migrate_pre_v22_pos_frame(at_v22)
    assert at_v22[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_ANCHOR   # untouched


def test_migrate_pre_v22_pos_frame_is_fail_soft():
    # A non-numeric / boolean / out-of-range stored alignment or position must never raise, and
    # falls back to the safe "anchor" reading (clamp_variant/clamp_pos's own fallback is what
    # matters when these are later READ; this fixup only needs to not blow up on garbage).
    non_int_alignment = {PROGRESS_ALIGNMENT_KEY: "nonsense",
                         BAR_POS_X_KEY: 810, BAR_POS_Y_KEY: 640}
    mod_settings._migrate_pre_v22_pos_frame(non_int_alignment)
    assert non_int_alignment[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_ANCHOR

    booly_alignment = {PROGRESS_ALIGNMENT_KEY: True,
                       BAR_POS_X_KEY: 810, BAR_POS_Y_KEY: 640}
    mod_settings._migrate_pre_v22_pos_frame(booly_alignment)
    assert booly_alignment[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_ANCHOR

    non_numeric_pos = {PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FREE,
                       BAR_POS_X_KEY: "nonsense", BAR_POS_Y_KEY: "nonsense"}
    mod_settings._migrate_pre_v22_pos_frame(non_numeric_pos)
    assert non_numeric_pos[mod_settings.PROGRESS_POS_FRAME_KEY] == mod_settings.POS_FRAME_ANCHOR


def test_migrate_pre_v22_pos_frame_carries_every_default_key_when_driven_from_defaults():
    # ENUMERATED FROM DEFAULTS, not hand-listed (the task's own instruction): a pre-v22 store that
    # otherwise carries every DEFAULTS key verbatim (flipped from its default, so a wipe cannot
    # masquerade as a pass) must survive migration with every one of THOSE OTHER keys untouched --
    # only the new marker key is added. This is the generic half of the v22 migration story; the
    # legacy/anchor semantics themselves are covered by the two tests above.
    old = {}
    for key, default in DEFAULTS.items():
        if key == mod_settings.PROGRESS_POS_FRAME_KEY:
            continue   # the one key genuinely absent from a pre-v22 store
        if isinstance(default, bool):
            old[key] = not default
        elif key in (PROGRESS_ORIENTATION_KEY, PROGRESS_ALIGNMENT_KEY):
            old[key] = default   # left at the shipped default; not this fixup's concern
        elif isinstance(default, int):
            old[key] = default + 1 if key not in (PROGRESS_VARIANT_KEY, PROGRESS_SIZE_KEY) else default
        else:
            old[key] = default
    before = dict(old)
    mod_settings._migrate_pre_v22_pos_frame(old)
    for key, value in before.items():
        assert old[key] == value, "%s was touched by the pos-frame migration" % key
    assert mod_settings.PROGRESS_POS_FRAME_KEY in old


# --- v23: _migrate_pre_v23_alignment -- the option-collapse value migration ----------------------

def test_migrate_pre_v23_alignment_maps_all_three_old_values_explicitly():
    # THE explicit map the task calls for: old 0 (Damage Log) -> 0 (Fixed); old 1 (Minimap) ->
    # 0 (Fixed); old 2 (Free) -> 1 (Free). Driven off the LITERAL pre-v23 ints, not the (now
    # renumbered) symbolic constants -- see the function's own docstring for why.
    damage_log = {PROGRESS_ALIGNMENT_KEY: 0}
    mod_settings._migrate_pre_v23_alignment(damage_log)
    assert damage_log[PROGRESS_ALIGNMENT_KEY] == PROGRESS_ALIGN_FIXED

    minimap = {PROGRESS_ALIGNMENT_KEY: 1}
    mod_settings._migrate_pre_v23_alignment(minimap)
    assert minimap[PROGRESS_ALIGNMENT_KEY] == PROGRESS_ALIGN_FIXED

    free = {PROGRESS_ALIGNMENT_KEY: 2}
    mod_settings._migrate_pre_v23_alignment(free)
    assert free[PROGRESS_ALIGNMENT_KEY] == PROGRESS_ALIGN_FREE


def test_migrate_pre_v23_alignment_is_fail_soft():
    # A missing / non-int / boolean / out-of-range value is left alone -- clamp_variant re-clamps
    # it into the new domain when later read; this fixup only needs to not blow up on garbage.
    no_key = {}
    mod_settings._migrate_pre_v23_alignment(no_key)
    assert PROGRESS_ALIGNMENT_KEY not in no_key

    non_int = {PROGRESS_ALIGNMENT_KEY: "nonsense"}
    mod_settings._migrate_pre_v23_alignment(non_int)
    assert non_int[PROGRESS_ALIGNMENT_KEY] == "nonsense"

    booly = {PROGRESS_ALIGNMENT_KEY: True}
    mod_settings._migrate_pre_v23_alignment(booly)
    assert booly[PROGRESS_ALIGNMENT_KEY] is True

    out_of_range = {PROGRESS_ALIGNMENT_KEY: 7}
    mod_settings._migrate_pre_v23_alignment(out_of_range)
    assert out_of_range[PROGRESS_ALIGNMENT_KEY] == 7


def test_migrate_pre_v23_alignment_carries_every_default_key_when_driven_from_defaults():
    # ENUMERATED FROM DEFAULTS, not hand-listed (the task's own instruction): every OTHER key must
    # survive this migration untouched -- only PROGRESS_ALIGNMENT_KEY's raw value is remapped.
    old = {}
    for key, default in DEFAULTS.items():
        if key == PROGRESS_ALIGNMENT_KEY:
            old[key] = 1   # the pre-v23 "Minimap" index -- must become Fixed (0), not stay 1
            continue
        if isinstance(default, bool):
            old[key] = not default
        elif isinstance(default, int) and key not in (
                PROGRESS_VARIANT_KEY, PROGRESS_SIZE_KEY, PROGRESS_ORIENTATION_KEY):
            old[key] = default + 1
        else:
            old[key] = default
    before = dict(old)
    mod_settings._migrate_pre_v23_alignment(old)
    for key, value in before.items():
        if key == PROGRESS_ALIGNMENT_KEY:
            continue
        assert old[key] == value, "%s was touched by the alignment migration" % key
    assert old[PROGRESS_ALIGNMENT_KEY] == PROGRESS_ALIGN_FIXED


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


def test_migration_collapses_pre_v23_alignment_across_every_default_key(_run_register):
    # THE v23 index migration, end to end: a pre-v23 store with the OLD raw "Minimap" index (1)
    # must land on Fixed (0), and every OTHER DEFAULTS key must survive the bump untouched --
    # enumerated from DEFAULTS, not hand-listed, so this test cannot rot as new keys are added.
    old = {"enabled": True}
    for key, default in DEFAULTS.items():
        if key == PROGRESS_ALIGNMENT_KEY:
            old[key] = 1   # the pre-v23 "Minimap" index
        elif key == mod_settings.PROGRESS_POS_FRAME_KEY:
            continue   # genuinely absent pre-v22 too; seeded by its own migration
        elif isinstance(default, bool):
            old[key] = not default
        elif isinstance(default, int):
            old[key] = default + 1   # every radio's ceiling is 1, so default+1 is a legal index
        else:
            old[key] = default
    api = _FakeMsaApi(stored=old, stored_version=SETTINGS_VERSION - 1)
    _run_register(api)

    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FIXED
    for key, value in old.items():
        if key in (PROGRESS_ALIGNMENT_KEY, "enabled"):
            continue
        assert mod_settings._settings[key] == value, "%s was wiped by the v23 bump" % key
    written = api.state["settings"][LINKAGE]
    assert written[PROGRESS_ALIGNMENT_KEY] == PROGRESS_ALIGN_FIXED
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


def test_a_mount_never_zeroes_the_stored_bar_position(_run_register):
    # A MOUNT is the other thing that must never trigger the orientation-change coordinate reset:
    # register() on an existing install runs the saved-truthy _seed path and never calls
    # _on_changed at all, so a Vertical install's stored pair must come back verbatim on every
    # launch. (Were the reset ever moved into a seed/apply path instead, this goes red.)
    stored = {"enabled": True,
              PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_VERTICAL,
              PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_FREE,
              BAR_POS_X_KEY: 900, BAR_POS_Y_KEY: 500}
    api = _FakeMsaApi(stored=stored, stored_version=SETTINGS_VERSION)
    _run_register(api)
    assert (bar_pos_x(), bar_pos_y()) == (900, 500)
    assert mod_settings.progress_bar_alignment() == PROGRESS_ALIGN_FREE
    assert api.updated == 0
