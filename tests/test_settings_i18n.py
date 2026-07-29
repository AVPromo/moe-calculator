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
    assert de[u"garageWidget"][u"label"] != en[u"garageWidget"][u"label"]
    assert de[u"garageWidget"][u"label"] == u"Garage-Widget"
    assert en[u"garageWidget"][u"label"] == u"In-Garage Widget"


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
    # The Alt child is the SECOND column-1 control -- between the master and counted assist.
    assert S.COL1_KEYS[1] == u"battleAltKey"
    en = S.resolve(u"en")
    assert en[u"battleAltKey"][u"label"] == u"Show on Alt Key"
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
    assert uk[u"battleAltKey"][u"label"] == u"Показувати по клавіші Alt"
    assert uk[u"battleAltKey"][u"label"] != en[u"battleAltKey"][u"label"]


# --- countedAssist (the "Enable Counted Assistance" third-row setting) --------

def test_counted_assist_present_in_master_and_col1():
    assert u"countedAssist" in S._PANEL[u"en"]
    # THIRD control in column 1 -- the second child under the In-Battle master in
    # mod_settings._template() ([battle master, alt child, counted child, progress bar]). It is
    # the last of the GROUP, not of the column; the length is pinned by the template<->COL1_KEYS
    # pairing test in test_mod_settings, not restated here.
    assert u"countedAssist" in S.COL1_KEYS
    assert S.COL1_KEYS[2] == u"countedAssist"
    en = S.resolve(u"en")
    assert en[u"countedAssist"][u"label"] == u"Counted Assistance"
    assert u"ttHeader" in en[u"countedAssist"] and u"ttBody" in en[u"countedAssist"]


def test_counted_assist_ukrainian_translated():
    uk = S.resolve(u"uk")
    en = S.resolve(u"en")
    assert uk[u"countedAssist"][u"label"] == u"Зарахована допомога"
    assert uk[u"countedAssist"][u"label"] != en[u"countedAssist"][u"label"]


# --- progressBar + progressVariant (the Progress Bar group, last in column 1) --

def test_progress_bar_group_is_the_tail_of_col1():
    # The progress-bar control briefly had a column 3 of its own; that column never rendered
    # in-client, so it is back in column 1 -- now as a MASTER followed by its variant radio, so
    # the radio's key is the LAST column-1 key. The TABLE KEY `progressBar` never changed through
    # any of those moves, so no translation was ever orphaned.
    assert u"progressBar" in S._PANEL[u"en"]
    assert S.COL1_KEYS[-2:] == (u"progressBar", u"progressVariant")
    assert S.VARIANT_KEY == u"progressVariant"
    # ...and the radio is the ONE control with no _PANEL row in any language (build() synthesises
    # it, see below), so it must NOT be in the English master either -- a re-added row would
    # silently make _KEYS/_SHIPPED demand a translation for a control that renders no text.
    assert S.VARIANT_KEY not in S._PANEL[u"en"]
    # The column-3 key tuple is gone with the column -- a leftover would silently re-add a
    # phantom column to mod_settings._sync_template_text's walk.
    assert not hasattr(S, u"COL3_KEYS")
    en = S.resolve(u"en")
    # Retitled "Progress Log" -> "Progress Bar" (the master of the two variants); text-only, so
    # it reaches an existing install through _sync_template_text with no version bump.
    assert en[u"progressBar"][u"label"] == u"Progress Bar"
    assert u"ttHeader" in en[u"progressBar"] and u"ttBody" in en[u"progressBar"]
    # The radio's own "Bar Type" label row is GONE -- an empty label so the panel draws no header
    # above the options and they read as direct children of the master checkbox. The KEY survives
    # (COL1_KEYS is positional) but it is no longer a _PANEL row at all: build() SYNTHESISES the
    # blank entry, and with no visible row there is nothing to hang a tooltip on, so it emits no
    # "tooltip" key at all.
    variant = S.build(u"en")[S.VARIANT_KEY]
    assert variant[u"text"] == u""
    assert u"tooltip" not in variant
    # The variant prose was MOVED, not dropped: it now lives on the master's tooltip body, the one
    # surface the group still has.
    assert u"Moving Average" in en[u"progressBar"][u"ttBody"]
    assert u"Damage Efficiency" in en[u"progressBar"][u"ttBody"]


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
    reads it, off build()'s synthesised entry (the `variant_options()` helper was inlined into
    build(), so there is no other public seam left)."""
    return S.build(code)[S.VARIANT_KEY][u"options"]


def test_progress_variant_row_is_deliberately_blank_in_every_language():
    # The radio's label row is GONE by design, in EVERY language -- and now it is not a _PANEL row
    # at all: build() SYNTHESISES a blank `text` with no tooltip key. This is the flip side of the
    # leak guard above -- an empty string here must not be read as "untranslated" (build() never
    # marks the synthesised entry, since there is nothing to fall back FROM), and equally a
    # re-added "Bar Type" row would fail here instead of quietly coming back.
    key = S.VARIANT_KEY
    for code in S._PANEL:
        assert key not in S._PANEL[code], u"%s re-grew a %s row" % (code, key)
        rendered = S.build(code)[key]
        assert rendered[u"text"] == u""
        assert u"tooltip" not in rendered


def test_the_synthesised_variant_row_is_never_marked_untranslated(monkeypatch):
    # It has NO _PANEL row in any language, so the naive `k in tbl` test build() uses for every
    # real key would mark it as an English fallback in EVERY language -- an "_" prefix on a row
    # that renders no text at all, and worse, on the option labels beside it. Only the OPTIONS
    # fall back, and only for an unknown code (next test).
    monkeypatch.setattr(i18n, u"MARK_UNTRANSLATED", True)
    for code in S._PANEL:
        rendered = S.build(code)[S.VARIANT_KEY]
        assert rendered[u"text"] == u"", u"%s marked the blank variant row" % code
        assert not any(o.startswith(u"_") for o in rendered[u"options"]), \
            u"%s marked its own translated options" % code


def test_variant_options_translated_in_every_shipped_language():
    # The radio's option labels live in their OWN table (they are structural to MSA, not text --
    # only a settingsVersion bump carries them to an existing install), so they need the same
    # no-English-leak guard: two options per language, in index order, none of them English.
    assert set(S._VARIANT_OPTIONS) == set(S._PANEL), (
        u"a language block has no variant option tuple (or vice versa)")
    en_opts = _options(u"en")
    assert en_opts == (u"Moving Average", u"Damage Efficiency")
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


def test_build_attaches_options_only_to_the_variant_control():
    # mod_settings._radio reads the option labels off the rendered entry, so build() must attach
    # them there -- and NOWHERE else, or a checkbox would grow a phantom options key.
    b = S.build(u"de")
    assert b[S.VARIANT_KEY][u"options"] == S._VARIANT_OPTIONS[u"de"]
    for key, entry in b.items():
        if key != S.VARIANT_KEY:
            assert u"options" not in entry, u"%s grew an options key" % key


def test_progress_bar_ukrainian_translated():
    uk = S.resolve(u"uk")
    assert uk[u"progressBar"][u"label"] != S.resolve(u"en")[u"progressBar"][u"label"]
    # No progressVariant label comparison: it is blank in every language by design (see
    # test_progress_variant_row_is_deliberately_blank_in_every_language) -- only the OPTION labels
    # under it carry Ukrainian text now.
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
    assert t[u"garageWidget"][u"text"] == u"Garage-Widget"
