# -*- coding: utf-8 -*-
"""Unit tests for the settings-panel translation resolver (engine-free).

settings_i18n is pure except client_language(); it imports cleanly under pytest
because _compat guards the game's debug_utils. The single engine read is exercised
by faking a `helpers` module in sys.modules. Mirrors the sibling Garage Progress Bar
mod's test_settings_i18n."""
import sys
import types

from moe_calculator.adapter import settings_i18n as S
from moe_calculator.adapter import i18n

# The full key set every language block must cover (== the English master's keys).
_KEYS = set(S._PANEL[u"en"].keys())
# Every non-English language we ship a block for.
_SHIPPED = [c for c in S._PANEL if c != u"en"]


def _col1_slice(*keys):
    """The COL1_KEYS indices of `keys`, in the order given.

    Every positional pin below goes through this instead of an index literal: COL*_KEYS' pairing
    with the built template is POSITIONAL (mod_settings._sync_template_text zips them), so a
    reorder does not error -- it retitles the WRONG control on every existing install. Naming the
    key makes the next reorder report itself; an absent key raises here rather than reading as
    "index moved"."""
    for key in keys:
        assert key in S.COL1_KEYS, u"%s left COL1_KEYS entirely" % key
    return tuple(S.COL1_KEYS.index(key) for key in keys)


def test_the_text_less_spacer_rows_take_a_none_sentinel_slot():
    # An Empty spacer has no text in ANY language, so it gets a `None` slot rather than a key --
    # and the slot is MANDATORY: the zip in _sync_template_text is positional, so a spacer with no
    # slot would shift every later control's text by one. `None` specifically, because
    # `panel_text().get(None)` is falsy and the sync walk's existing `if not rendered: continue`
    # then skips it with no new branch (the template-side pairing is pinned in test_mod_settings).
    # FIVE in column 1, TWO in column 2: column 1 has one heading "Battle Progress", one heading
    # "Mode", one heading "Transitions", one (v19) heading the hold Slider and one (v18) heading
    # "Bar Position"; column 2 has one heading "Layout" and one heading "Position".
    assert S.COL1_KEYS.count(None) == 5
    assert S.COL2_KEYS.count(None) == 2
    # A sentinel must never collide with a real row, in any language.
    for code in S._PANEL:
        assert None not in S.build(code)


# --- resolve ---------------------------------------------------------------

def test_resolve_en_has_all_keys_shaped():
    r = S.resolve(u"en")
    assert set(r.keys()) == _KEYS
    for entry in r.values():
        assert u"label" in entry
    # Both current rows carry a header+body tooltip.
    assert u"ttHeader" in r[u"garageWidget"] and u"ttBody" in r[u"garageWidget"]
    assert u"ttHeader" in r[u"battleWidget"] and u"ttBody" in r[u"battleWidget"]


def test_resolve_de_differs_from_english():
    en = S.resolve(u"en")
    de = S.resolve(u"de")
    assert set(de.keys()) == _KEYS
    # The masters' own labels all became the bare "Enabled" (the CATEGORY header above names the
    # feature), so the garage master is no longer a useful English-vs-German comparison -- "Enabled"
    # / "Aktiviert" still differ, but the interesting per-language string moved to the header row.
    # Assert on the CATEGORY, which is where the feature name lives now, AND keep the master pair.
    assert de[u"catGarage"][u"label"] != en[u"catGarage"][u"label"]
    assert de[u"catGarage"][u"label"] == u"Garage-Widget"
    assert en[u"catGarage"][u"label"] == u"Garage Widget"
    assert de[u"garageWidget"][u"label"] == u"Aktiviert"
    assert en[u"garageWidget"][u"label"] == u"Enabled"


def test_resolve_unknown_is_full_english():
    assert S.resolve(u"xx") == S.resolve(u"en")
    assert S.resolve(u"") == S.resolve(u"en")
    assert S.resolve(None) == S.resolve(u"en")


def test_resolve_per_key_fallback(monkeypatch):
    # A synthetic language that translated ONLY one key falls back to English for the
    # rest -- proving fallback is per key, not per language.
    partial = {u"garageWidget": S._row(u"ZZ", u"ZZ", u"zz")}
    monkeypatch.setitem(S._PANEL, u"zz", partial)
    r = S.resolve(u"zz")
    assert r[u"garageWidget"][u"label"] == u"ZZ"
    assert r[u"battleWidget"] == S._PANEL[u"en"][u"battleWidget"]  # English fallback


def test_every_shipped_language_covers_all_keys():
    for code in _SHIPPED:
        assert set(S._PANEL[code].keys()) == _KEYS, (
            u"language %s is missing keys: %s" % (code, _KEYS - set(S._PANEL[code])))


# --- battleAltKey (the "show only while Alt held" peek setting) --------------

def test_battle_alt_key_present_in_master_and_col1():
    assert u"battleAltKey" in S._PANEL[u"en"]
    assert u"battleAltKey" in S.COL1_KEYS
    # POSITION, named rather than an index literal: the Alt child sits between the In-Battle master
    # and counted assist, and the whole group now follows the catBattleCalc header row. Naming the
    # neighbours means the next reorder reports which key moved instead of retitling a control.
    assert _col1_slice(u"catBattleCalc", u"battleWidget", u"battleAltKey") == (0, 1, 2)
    en = S.resolve(u"en")
    assert en[u"battleAltKey"][u"label"] == u"Alt Press"
    assert u"ttHeader" in en[u"battleAltKey"] and u"ttBody" in en[u"battleAltKey"]
    # New INVERTED meaning: peek while held; when off, shown at all times.
    assert u"only while the Alt key is held" in en[u"battleAltKey"][u"ttBody"]
    assert u"shown at all times" in en[u"battleAltKey"][u"ttBody"]


def test_battle_alt_key_keeps_alt_literal_in_every_language():
    # "Alt" is a keyboard key -- it must NOT be translated in any shipped language. Assert the
    # literal token appears in the label, header and body of every block.
    for code in S._PANEL:
        entry = S._PANEL[code][u"battleAltKey"]
        assert u"Alt" in entry[u"label"], u"%s label lost 'Alt'" % code
        assert u"Alt" in entry[u"ttHeader"], u"%s header lost 'Alt'" % code
        assert u"Alt" in entry[u"ttBody"], u"%s body lost 'Alt'" % code


def test_battle_alt_key_ukrainian_translated():
    uk = S.resolve(u"uk")
    en = S.resolve(u"en")
    assert uk[u"battleAltKey"][u"label"] == u"Натискання Alt"
    assert uk[u"battleAltKey"][u"label"] != en[u"battleAltKey"][u"label"]


# --- countedAssist (the "Enable Counted Assistance" third-row setting) --------

def test_counted_assist_present_in_master_and_col1():
    assert u"countedAssist" in S._PANEL[u"en"]
    # The SECOND child under the In-Battle master, i.e. the LAST key of the Battle Calculator
    # category -- the next slot is the spacer's `None` sentinel, and the one after it starts the
    # Battle Progress category. It is the last of the GROUP, not of the column; the column length
    # is pinned by the template<->COL1_KEYS pairing test in test_mod_settings, not restated here.
    alt, counted, next_cat = _col1_slice(u"battleAltKey", u"countedAssist", u"catBattleProgress")
    assert counted == alt + 1
    assert S.COL1_KEYS[counted + 1] is None      # the Empty spacer between the categories
    assert next_cat == counted + 2
    en = S.resolve(u"en")
    assert en[u"countedAssist"][u"label"] == u"Counted Assistance Row"
    assert u"ttHeader" in en[u"countedAssist"] and u"ttBody" in en[u"countedAssist"]


def test_counted_assist_ukrainian_translated():
    uk = S.resolve(u"uk")
    en = S.resolve(u"en")
    assert uk[u"countedAssist"][u"label"] == u"Рядок зарахованої допомоги"
    assert uk[u"countedAssist"][u"label"] != en[u"countedAssist"][u"label"]


# --- progressBar + progressVariant (the Progress Bar group, last in column 1) --

def test_progress_bar_group_is_the_tail_of_col1():
    # The progress-bar control briefly had a column 3 of its own; that column never rendered
    # in-client, so it is back in column 1 -- as the "Battle Progress" CATEGORY: a bare header row,
    # the Progress Bar master with its three VISIBILITY children, an Empty spacer (ahead of "Mode")
    # and the standalone Mode and Scale radios. A SECOND Empty spacer then closes it and the
    # "Transitions" CATEGORY takes the tail: its own bare header, the Transitions master, its two
    # switches and (v17) the hold-duration slider. The TABLE KEY `progressBar` never changed
    # through any of those moves, so no translation was ever orphaned.
    #
    # Pinned as a literal FIFTEEN-slot RUN (twelve real keys + the three `None` sentinels that sit
    # inside it -- v19 added a fifth Empty spacer ahead of "progressHoldSeconds"), rather than
    # filtering the sentinels out and asserting contiguity on what remains -- that would silently
    # accept a spacer landing anywhere in the run instead of exactly where it belongs. It was the
    # column TAIL until v18 appended a fourth category ("Bar Position"), so the run is now anchored
    # to where "Battle Progress" starts; the four slots after it are pinned separately below.
    assert u"progressBar" in S._PANEL[u"en"]
    start = S.COL1_KEYS.index(u"catBattleProgress")
    tail = S.COL1_KEYS[start:start + 15]
    assert tail == (u"catBattleProgress", u"progressBar",
                    u"progressShowEvents", u"progressShowAlt", u"progressShowAlways",
                    None, S.VARIANT_KEY, u"progressSize",
                    None, u"catTransitions",
                    u"progressTransitions", u"progressTransEvents", u"progressTransManual",
                    None, u"progressHoldSeconds"), (
        u"the Battle Progress + Transitions categories (incl. all three spacers) are no longer one "
        u"run in COL1_KEYS: %r" % (S.COL1_KEYS,))
    # ...and the "Bar Position" category IS the tail, spacer included.
    assert S.COL1_KEYS[start + 15:] == (None, u"catBarPosition", u"barPosX", u"barPosY"), (
        u"the Bar Position category is no longer the tail of COL1_KEYS: %r" % (S.COL1_KEYS,))
    assert S.VARIANT_KEY == u"progressVariant"
    # The column-3 key tuple is gone with the column -- a leftover would silently re-add a
    # phantom column to mod_settings._sync_template_text's walk.
    assert not hasattr(S, u"COL3_KEYS")
    en = S.resolve(u"en")
    # The master's LABEL went "Next Mark Progress Bar" -> "Progress Log" -> "Progress Bar" -> the
    # bare "Show" -> "Enabled", because the "Battle Progress" category header above it now carries
    # the feature name. All of those are text-only, so each reached an existing install through
    # _sync_template_text with no version bump; the varName never moved (there is no rename map --
    # a renamed varName silently resets every user's value).
    assert en[u"catBattleProgress"][u"label"] == u"Battle Progress"
    assert en[u"progressBar"][u"label"] == u"Enabled"
    assert u"ttHeader" in en[u"progressBar"] and u"ttBody" in en[u"progressBar"]
    # The variant radio is a NORMAL _PANEL row again (it carries a "Mode" label), so build() only
    # bolts its options on -- it no longer synthesises a blank entry. It also now carries its own
    # tooltip (maintainer override, v15 -- see test_both_radios_now_carry_a_tooltip_in_every_language).
    assert S.VARIANT_KEY in S._PANEL[u"en"]
    variant = S.build(u"en")[S.VARIANT_KEY]
    assert variant[u"text"] == u"Mode"
    assert variant[u"tooltip"]
    # The per-variant prose lives on the master's tooltip body.
    assert u"Moving Average" in en[u"progressBar"][u"ttBody"]
    assert u"Damage Efficiency" in en[u"progressBar"][u"ttBody"]
    # The three visibility switches now carry their OWN tooltips (test_..._children_..._below), so
    # the master no longer spells them out -- that sentence was dropped as redundant.
    for word in (u"Events brings it up", u"Alt Press while", u"Always keeps it"):
        assert word not in en[u"progressBar"][u"ttBody"], \
            u"the master's tooltip still explains the %r switch -- redundant now that " \
            u"the child rows carry their own tooltips" % word


def test_progress_bar_master_translated_in_every_shipped_language():
    # The Progress Bar MASTER must be present AND actually translated in all 11 shipped blocks --
    # a dropped or copy-pasted-English row would leak English for that one language only (marked
    # at runtime, but invisible here without this check). It now carries the variant prose too
    # (moved off the label-less radio), so the leak surface got BIGGER, not smaller.
    assert len(S._PANEL) == 11
    en = S._PANEL[u"en"]
    key = u"progressBar"
    for code in S._PANEL:
        entry = S._PANEL[code][key]
        assert entry[u"label"], u"%s has an empty %s label" % (code, key)
        assert entry[u"ttHeader"] and entry[u"ttBody"], (
            u"%s %s lost its tooltip" % (code, key))
        # The moved-in variant prose must be translated too, not left as the English sentences:
        # assert on the OPTION NAMES this language uses, which is the one token guaranteed to
        # appear in a faithful translation of that prose.
        for opt in S._VARIANT_OPTIONS[code]:
            assert opt.split(u" ")[0] in entry[u"ttBody"], (
                u"%s progressBar body does not mention its own '%s' option -- was the "
                u"variant prose left in English (or dropped)?" % (code, opt))
        if code == u"en":
            continue
        for part in (u"label", u"ttHeader", u"ttBody"):
            assert entry[part] != en[key][part], (
                u"%s/%s/%s is still the English string" % (code, key, part))


def _options(code):
    """The variant radio's rendered option tuple for `code` -- read where mod_settings._radio
    reads it, off build()'s rendered entry (the `variant_options()` helper was inlined into
    build(), so there is no other public seam left)."""
    return S.build(code)[S.VARIANT_KEY][u"options"]


def test_the_three_visibility_children_each_carry_their_own_tooltip_in_every_language():
    # WHEN the bar shows, as three switches under the Progress Bar master. Unlike the Transitions
    # pair (still label-only -- their master's tooltip spells them out), each of these three now
    # carries its OWN header+body tooltip: the master's tooltip used to explain all three inline,
    # but that sentence was redundant once these rows had their own prose, so it was dropped.
    #
    # Their labels still DELIBERATELY collide with the Transitions pair's ("Events" / "Alt Press")
    # -- two different axes, same words, and the category layout is what tells them apart.
    # Asserting the collision keeps a well-meaning "disambiguate these" edit from landing without
    # a settingsVersion decision.
    keys = (u"progressShowEvents", u"progressShowAlt", u"progressShowAlways")
    en = S._PANEL[u"en"]
    for code in S._PANEL:
        for key in keys:
            entry = S._PANEL[code][key]
            assert entry[u"label"], u"%s has an empty %s label" % (code, key)
            assert entry[u"ttHeader"] and entry[u"ttBody"], (
                u"%s/%s lost its tooltip" % (code, key))
            assert S.build(code)[key][u"tooltip"]
            if code != u"en":
                for part in (u"ttHeader", u"ttBody"):
                    assert entry[part] != en[key][part], (
                        u"%s/%s/%s is still the English string" % (code, key, part))
        assert (S._PANEL[code][u"progressShowEvents"][u"label"]
                == S._PANEL[code][u"progressTransEvents"][u"label"])
        assert (S._PANEL[code][u"progressShowAlt"][u"label"]
                == S._PANEL[code][u"progressTransManual"][u"label"])
    r = S.resolve(u"en")
    assert [r[k][u"label"] for k in keys] == [u"Events", u"Alt Press", u"Always"]
    # SCOPED content checks (not a bare substring grep against the whole file): each tooltip must
    # actually describe its own switch, and the "Ignored while Always is on" carve-out belongs to
    # the two switches Always overrides, not to Always itself.
    assert u"Ignored while Always is on" in r[u"progressShowEvents"][u"ttBody"]
    assert u"Ignored while Always is on" in r[u"progressShowAlt"][u"ttBody"]
    assert u"Ignored" not in r[u"progressShowAlways"][u"ttBody"]
    assert u"Overrides" in r[u"progressShowAlways"][u"ttBody"]


def test_every_alt_labelled_row_keeps_the_alt_literal_in_every_language():
    # Three separate controls now read "Alt Press" in English -- the overlay's peek, the bar's
    # peek and the bar's Alt transition. "Alt" is a KEYBOARD KEY and must survive translation in
    # all of them, not just the one battleAltKey test already guards.
    for key in (u"battleAltKey", u"progressShowAlt", u"progressTransManual"):
        for code in S._PANEL:
            assert u"Alt" in S._PANEL[code][key][u"label"], \
                u"%s/%s label lost the 'Alt' key name" % (code, key)


def test_both_radios_now_carry_a_tooltip_in_every_language():
    # MAINTAINER OVERRIDE (v15): the "options say it all" invariant this test used to protect is
    # deliberately WAIVED. Each radio still carries its LABEL ("Mode" / "Scale") but now ALSO a
    # real header+body tooltip that adds INFO the option labels alone don't -- Mode covers WHEN a
    # mode switch takes effect, Scale explains what the option words mean (it has no explanation
    # anywhere else in the panel). Assembled in the same {HEADER}/{BODY} shape _render() builds for
    # every other tooltipped row, and translated (not just present) in every shipped language.
    en = S._PANEL[u"en"]
    for key in (S.VARIANT_KEY, u"progressSize"):
        for code in S._PANEL:
            entry = S._PANEL[code][key]
            assert entry[u"label"], u"%s has an empty %s label" % (code, key)
            assert entry.get(u"ttHeader") and entry.get(u"ttBody"), (
                u"%s/%s lost its tooltip -- the maintainer override that waived the "
                u"label-only rule expects one" % (code, key))
            rendered = S.build(code)[key]
            assert rendered[u"text"] == entry[u"label"]
            assert rendered[u"tooltip"] == u"{HEADER}%s{/HEADER}{BODY}%s{/BODY}" % (
                entry[u"ttHeader"], entry[u"ttBody"])
            if code != u"en":
                for part in (u"ttHeader", u"ttBody"):
                    assert entry[part] != en[key][part], (
                        u"%s/%s/%s is still the English string" % (code, key, part))


def test_a_translated_radio_row_is_never_marked_untranslated(monkeypatch):
    # Both radios have a real row in every block, so neither the label nor the options beside it
    # may pick up the "_" English-fallback marker. Only the OPTIONS fall back, and only for an
    # unknown code (next test).
    monkeypatch.setattr(i18n, u"MARK_UNTRANSLATED", True)
    for key in (S.VARIANT_KEY, u"progressSize"):
        for code in S._PANEL:
            rendered = S.build(code)[key]
            assert not rendered[u"text"].startswith(u"_"), \
                u"%s marked its own translated %s label" % (code, key)
            assert not any(o.startswith(u"_") for o in rendered[u"options"]), \
                u"%s marked its own translated %s options" % (code, key)


def test_variant_options_translated_in_every_shipped_language():
    # The radio's option labels live in their OWN table (they are structural to MSA, not text --
    # only a settingsVersion bump carries them to an existing install), so they need the same
    # no-English-leak guard: two options per language, in index order, none of them English.
    assert set(S._VARIANT_OPTIONS) == set(S._PANEL), (
        u"a language block has no variant option tuple (or vice versa)")
    en_opts = _options(u"en")
    # THE v13 ORDER, pinned here as well as in mod_settings: the option TUPLE is the wire order the
    # stored raw int indexes, so this tuple and PROGRESS_VARIANT_* must never drift apart -- and
    # flipping it back would silently swap every user's bar a second time.
    assert en_opts == (u"Damage Efficiency", u"Moving Average")
    for code in S._VARIANT_OPTIONS:
        opts = _options(code)
        assert len(opts) == 2, u"%s does not have exactly two options" % code
        assert all(opts), u"%s has an empty option label" % code
        # build() must serve each language its OWN tuple, not just something two long.
        assert opts == S._VARIANT_OPTIONS[code]
        if code == u"en":
            continue
        for i, opt in enumerate(opts):
            assert opt != en_opts[i], u"%s option %d is still English" % (code, i)


def test_variant_options_unknown_language_falls_back_to_english_marked(monkeypatch):
    assert _options(u"xx") == _options(u"en")
    monkeypatch.setattr(i18n, u"MARK_UNTRANSLATED", True)
    assert all(o.startswith(u"_") for o in _options(u"xx"))
    # A real language is never marked.
    assert not any(o.startswith(u"_") for o in _options(u"de"))


def test_build_attaches_options_to_exactly_the_two_radio_controls():
    # mod_settings._radio reads the option labels off the rendered entry, so build() must attach
    # them there -- and NOWHERE else, or a checkbox would grow a phantom options key. There are TWO
    # option-bearing controls now, and they are named: the label-less variant radio (which has no
    # _PANEL row at all -- build() synthesises it) and the "Size" radio (a normal _PANEL row that
    # only needs its options bolted on). Naming them both is the point: a third options key
    # appearing anywhere, or one of these two losing its own, fails here.
    b = S.build(u"de")
    assert {k for k, entry in b.items() if u"options" in entry} == {S.VARIANT_KEY, u"progressSize"}
    assert b[S.VARIANT_KEY][u"options"] == S._VARIANT_OPTIONS[u"de"]
    assert b[u"progressSize"][u"options"] == S._SIZE_OPTIONS[u"de"]
    # ...and the size radio keeps its own translated LABEL beside them (the variant's is blank).
    assert b[u"progressSize"][u"text"] == S._PANEL[u"de"][u"progressSize"][u"label"]


def test_size_options_translated_in_every_shipped_language():
    # The size radio's option labels get the same guard as the variant's: they live in their OWN
    # table (structural to MSA -- only a settingsVersion bump carries them to an existing install),
    # so a dropped or copy-pasted-English tuple would leak English for that one language only.
    assert set(S._SIZE_OPTIONS) == set(S._PANEL), (
        u"a language block has no size option tuple (or vice versa)")
    en_opts = S.build(u"en")[u"progressSize"][u"options"]
    assert en_opts == (u"Default", u"Large")
    for code in S._SIZE_OPTIONS:
        opts = S.build(code)[u"progressSize"][u"options"]
        assert len(opts) == 2 and all(opts), u"%s does not have two non-empty size options" % code
        assert opts == S._SIZE_OPTIONS[code]     # its OWN tuple, not just something two long
        if code == u"en":
            continue
        for i, opt in enumerate(opts):
            assert opt != en_opts[i], u"%s size option %d is still English" % (code, i)


def test_size_options_unknown_language_falls_back_to_english_marked(monkeypatch):
    # The WHOLE-TUPLE fallback the shared _options() helper implements, on the second table: the
    # options are one ordered set whose meaning is positional, so half-English is worse than all of
    # it. Same contract as the variant radio's -- proven separately because a per-table regression
    # in one is invisible from the other.
    assert S.build(u"xx")[u"progressSize"][u"options"] == \
        S.build(u"en")[u"progressSize"][u"options"]
    monkeypatch.setattr(i18n, u"MARK_UNTRANSLATED", True)
    assert all(o.startswith(u"_") for o in S.build(u"xx")[u"progressSize"][u"options"])
    assert not any(o.startswith(u"_") for o in S.build(u"de")[u"progressSize"][u"options"])


def test_the_transitions_group_is_one_tooltip_on_the_master_and_two_label_only_children():
    # The group's prose lives ENTIRELY on the master: "Events" / "Manual" are one-word switches the
    # master's tooltip already explains, so they are LABEL-ONLY rows and _render must emit no
    # "tooltip" key for them (mod_settings._checkbox then omits it -- the hard-indexed
    # rendered["tooltip"] that used to sit there raised KeyError on exactly these two rows).
    #
    # Existence of the three keys in all 11 blocks is NOT re-asserted here:
    # test_every_shipped_language_covers_all_keys already derives _KEYS from the English master and
    # demands every block match it exactly, so a missing row fails there.
    master, children = u"progressTransitions", (u"progressTransEvents", u"progressTransManual")
    en = S._PANEL[u"en"]
    for code in S._PANEL:
        entry = S._PANEL[code][master]
        assert entry[u"label"], u"%s has an empty %s label" % (code, master)
        assert entry[u"ttHeader"] and entry[u"ttBody"], (
            u"%s/%s lost the tooltip that is the whole group's only prose" % (code, master))
        assert S.build(code)[master][u"tooltip"]
        if code != u"en":
            # The LABEL is deliberately not guarded against English: "Transitions" is genuinely
            # French and "Manual" genuinely Spanish. The long prose is where a copy-pasted English
            # block would actually show, so guard THAT.
            for part in (u"ttHeader", u"ttBody"):
                assert entry[part] != en[master][part], (
                    u"%s/%s/%s is still the English string" % (code, master, part))
        for key in children:
            child = S._PANEL[code][key]
            assert child[u"label"], u"%s has an empty %s label" % (code, key)
            assert u"ttHeader" not in child and u"ttBody" not in child, (
                u"%s/%s grew a tooltip -- it is a one-word switch the master's prose already "
                u"explains, and a tooltip written into a stored template can never be REMOVED "
                u"again (_sync_template_text only overwrites)" % (code, key))
            assert u"tooltip" not in S.build(code)[key]


def test_the_three_category_headers_are_label_only_in_every_language():
    # A category header is TEXT ONLY -- no varName and NO tooltip (a bare feature name has nothing
    # to explain, and mod_settings._label() omits the key rather than emitting u""). It must also be
    # really translated in all 11 blocks, since it is now the row that CARRIES the feature name:
    # the masters below it all read the bare "Enabled" (was "Show").
    cats = (u"catGarage", u"catBattleCalc", u"catBattleProgress")
    en = S._PANEL[u"en"]
    for key in cats:
        assert key in S.COL1_KEYS or key in S.COL2_KEYS, u"%s is in no column tuple" % key
        for code in S._PANEL:
            entry = S._PANEL[code][key]
            assert entry[u"label"], u"%s has an empty %s label" % (code, key)
            assert u"ttHeader" not in entry and u"ttBody" not in entry, (
                u"%s/%s grew a tooltip -- a bare category header has nothing to hover, and a "
                u"tooltip written into a stored template can never be REMOVED again "
                u"(_sync_template_text only overwrites)" % (code, key))
            assert u"tooltip" not in S.build(code)[key]
            if code != u"en":
                assert entry[u"label"] != en[key][u"label"], (
                    u"%s/%s is still the English string" % (code, key))


def test_position_sub_label_now_carries_a_tooltip_in_every_language():
    # The column-2 sub-label heading the two steppers (mod_settings SETTINGS_VERSION 14) shipped
    # tipless -- deliberately NOT bold (unlike "Layout" above it), the weight difference alone
    # marking it as a sub-level. MAINTAINER OVERRIDE (v15) waives that: it now carries a real
    # header+body tooltip explaining NEW info (that both steppers apply immediately, without
    # dragging the widget) -- not a repeat of "positioning"'s drag instructions or posX/posY's
    # per-axis tooltips. Still not bold; only the tipless status changed.
    assert u"positionSub" in S.COL2_KEYS
    en = S._PANEL[u"en"]
    for code in S._PANEL:
        entry = S._PANEL[code][u"positionSub"]
        assert entry[u"label"], u"%s has an empty positionSub label" % code
        assert entry.get(u"ttHeader") and entry.get(u"ttBody"), (
            u"%s/positionSub lost its tooltip -- the maintainer override that waived the "
            u"tipless rule expects one" % code)
        rendered = S.build(code)[u"positionSub"]
        assert rendered[u"tooltip"] == u"{HEADER}%s{/HEADER}{BODY}%s{/BODY}" % (
            entry[u"ttHeader"], entry[u"ttBody"])
        if code != u"en":
            for part in (u"ttHeader", u"ttBody"):
                assert entry[part] != en[u"positionSub"][part], (
                    u"%s/positionSub/%s is still the English string" % (code, part))


def test_posx_posy_labels_restore_the_axis_and_corner_hint_in_every_language():
    # Restores the axis + reference-corner hint ("Horizontal (left X)" / "Vertical (top Y)") that
    # was shortened to the bare axis word -- back in the LABEL (where it lived before), in every
    # shipped language; the tooltips are untouched. "X"/"Y" are the coordinate letters and must
    # survive translation, like the "Alt" key literal elsewhere in this module.
    for code in S._PANEL:
        x_label = S._PANEL[code][u"posX"][u"label"]
        y_label = S._PANEL[code][u"posY"][u"label"]
        assert u"X" in x_label and u"(" in x_label, u"%s/posX lost its axis hint" % code
        assert u"Y" in y_label and u"(" in y_label, u"%s/posY lost its axis hint" % code
    en = S.resolve(u"en")
    assert en[u"posX"][u"label"] == u"Horizontal (left X)"
    assert en[u"posY"][u"label"] == u"Vertical (top Y)"


# The bare "Enabled" word each master reads, per language -- was "Show". Pinned as an exact map
# (not derived from the garage master's own label) so the test below can never be satisfied by a
# stale leftover "Show"/"Anzeigen"/etc. surviving in one block while the others moved on.
_ENABLED_WORD = {
    u"en": u"Enabled",
    u"de": u"Aktiviert",
    u"fr": u"Activé",
    u"es": u"Activado",
    u"it": u"Abilitato",
    u"pl": u"Włączone",
    u"cs": u"Povoleno",
    u"ru": u"Включено",
    u"uk": u"Увімкнено",
    u"hu": u"Engedélyezve",
    u"tr": u"Etkin",
}


def test_every_masters_label_is_the_bare_enabled_in_every_language():
    # The three feature masters read just "Enabled" (was "Show") because the category header above
    # each one names the feature. That is a set: if one of them keeps a feature name the panel reads
    # "Garage Widget / Garage Widget". Asserted per language against an EXACT pinned word, not a
    # substring and not derived from one of the three rows itself -- a bare `in` check (or deriving
    # the expectation from the garage master) would have passed with the OLD word still present as
    # a stray leftover in an untouched language block.
    assert set(_ENABLED_WORD) == set(S._PANEL)
    for code in S._PANEL:
        expected = _ENABLED_WORD[code]
        for key in (u"garageWidget", u"battleWidget", u"progressBar"):
            assert S._PANEL[code][key][u"label"] == expected, (
                u"%s/%s reads %r, not the pinned %r -- the category header already names the "
                u"feature" % (code, key, S._PANEL[code][key][u"label"], expected))
        # ...and the tooltips were deliberately LEFT ALONE, so each master still explains itself.
        for key in (u"garageWidget", u"battleWidget", u"progressBar"):
            assert S._PANEL[code][key][u"ttHeader"] and S._PANEL[code][key][u"ttBody"], (
                u"%s/%s lost the tooltip that is now its only prose" % (code, key))


def test_progress_bar_ukrainian_translated():
    uk = S.resolve(u"uk")
    assert uk[u"progressBar"][u"label"] != S.resolve(u"en")[u"progressBar"][u"label"]
    # No progressVariant label/tooltip comparison here -- it is a normal, fully-translated row
    # (see test_both_radios_now_carry_a_tooltip_in_every_language); this test only needs the OPTION
    # labels under it to carry Ukrainian text too.
    assert _options(u"uk") != _options(u"en")


# --- _norm -----------------------------------------------------------------

def test_norm_cases():
    assert S._norm(u"en") == u"en"
    assert S._norm(u"EN") == u"en"
    assert S._norm(u"en-US") == u"en"       # region suffix -> primary subtag
    assert S._norm(u"pt_BR") == u"pt"       # unknown full -> primary subtag
    assert S._norm(u"ua") == u"uk"          # alias
    assert S._norm(u"UA") == u"uk"          # alias, case-insensitive
    assert S._norm(None) == u""
    assert S._norm(u"") == u""


# --- markup + rendering ----------------------------------------------------

def test_render_assembles_tooltip_markup():
    out = S._render({u"label": u"L", u"ttHeader": u"H", u"ttBody": u"B"})
    assert out[u"text"] == u"L"
    assert out[u"tooltip"] == u"{HEADER}H{/HEADER}{BODY}B{/BODY}"


def test_render_label_only_has_no_tooltip():
    out = S._render({u"label": u"L"})
    assert out == {u"text": u"L"}
    assert u"tooltip" not in out


# --- marking ---------------------------------------------------------------

def test_build_marks_only_fallback_keys(monkeypatch):
    partial = {u"garageWidget": S._row(u"ZZ", u"ZZ", u"zz")}
    monkeypatch.setitem(S._PANEL, u"zz", partial)
    monkeypatch.setattr(i18n, u"MARK_UNTRANSLATED", True)
    b = S.build(u"zz")
    # Translated key: no underscore marker.
    assert not b[u"garageWidget"][u"text"].startswith(u"_")
    # Fallback key: underscore-marked text and tooltip.
    assert b[u"battleWidget"][u"text"].startswith(u"_")
    assert b[u"battleWidget"][u"tooltip"].startswith(u"_")


def test_build_en_client_never_marks(monkeypatch):
    monkeypatch.setattr(i18n, u"MARK_UNTRANSLATED", True)
    b = S.build(u"en")
    for entry in b.values():
        assert not entry[u"text"].startswith(u"_")


# --- client_language guard -------------------------------------------------

def test_client_language_reads_helpers(monkeypatch):
    fake = types.ModuleType(u"helpers")
    fake.getClientLanguage = lambda: u"de"
    monkeypatch.setitem(sys.modules, u"helpers", fake)
    assert S.client_language() == u"de"


def test_client_language_normalizes_alias(monkeypatch):
    fake = types.ModuleType(u"helpers")
    fake.getClientLanguage = lambda: u"ua"
    monkeypatch.setitem(sys.modules, u"helpers", fake)
    assert S.client_language() == u"uk"


def test_client_language_falls_back_to_english_on_error(monkeypatch):
    fake = types.ModuleType(u"helpers")

    def _boom():
        raise RuntimeError(u"no client")

    fake.getClientLanguage = _boom
    monkeypatch.setitem(sys.modules, u"helpers", fake)
    assert S.client_language() == u"en"


def test_panel_text_uses_client_language(monkeypatch):
    fake = types.ModuleType(u"helpers")
    fake.getClientLanguage = lambda: u"de"
    monkeypatch.setitem(sys.modules, u"helpers", fake)
    t = S.panel_text()
    # Read the CATEGORY header, not the master: every master's label is now the bare "Enabled",
    # whose German is "Aktiviert" -- still language-dependent, but the header is where the feature
    # NAME lives, so it is the stronger witness that the whole panel followed the client language.
    # catGarage is a HEADER_KEYS row, so build() wraps it in <b>...</b> -- the wrap itself is
    # language-independent, but the localized German text must still be inside it.
    assert t[u"catGarage"][u"text"] == u"<b>Garage-Widget</b>"
    assert t[u"garageWidget"][u"text"] == u"Aktiviert"
