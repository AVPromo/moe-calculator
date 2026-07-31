# -*- coding: utf-8 -*-
"""Static guards on the DAMAGE EFFICIENCY bar's DUPLICATED values (surface, anchor, timings).

Sibling of tests/test_progress_surface_mirror.py, and for the same reason: a registered battle
window has NO hot-reload, so a drift between two copies of the same number is invisible until a
full client relaunch. Everything here is a text-level assertion on the shipped files; the
module's BEHAVIOUR is checked by tools/dev/check_efficiency_js.js instead.

WHAT IS MIRRORED WHERE -- and the ONE place this differs from the Moving Average bar:

  * THE SURFACE BOUNDING BOX IS `.mp-backdrop`, NOT `#moe-bar-box`. On the progress bar those
    two happen to be the same rectangle, so its mirror test reads the sizing shim. Here they are
    DELIBERATELY different: `#moe-bar-box` is the tuner's own emit -- its width a tuned knob and
    its HEIGHT a five-term derivation over the bar plus its two caption rows -- and
    MoEEfficiencyView.html says in so many words not to "fix" it to the surface. So every surface
    assertion below reads the `.mp-backdrop` rule -- the composition's true bounding box -- and
    MoEEfficiency.js's BOX_* consts quote it by name.
  * PAD_REM turns that box into the surface size pushed to the engine and into the rigid translate
    into positive document coordinates -- but those FIVE derivations now live ONE FILE OVER, in
    the shared MoEBarTransient.js, parameterised over its cfg (viewW/viewH/shiftX/shiftY/hitPad
    off cfg.box*/cfg.pad). So the mirror chain has an extra link: MoEEfficiency.js must actually
    HAND its BOX_*/PAD_REM to createTransient (asserted), and the shared module must derive from
    them (asserted there). Which file owns which scrape is spelled out per test below; the BOX_*
    and PAD_REM consts stay per-bar and stay in the `^const NAME = <int>;` shape both mirror
    tests and both dev harnesses read.
  * domain/constants.EFFICIENCY_ANCHOR_Y_OFFSET is a function of BOTH -- and is asserted as its
    DERIVATION, never as the literal 50, so a deliberate re-tune of the fraction or the box still
    passes while genuine drift fails. NOTE THE TRAP: 50 coincidentally equals SHIFT_Y_REM because
    round(0.865 * 116) == 2 * 50. It is NOT a mirror of it.
  * The transient's timings live in THREE places -- MoEBarTransient.js's constants (SHARED with
    the Moving Average bar, whose mp-life is identically tuned), the CSS's @keyframes/animation,
    and the tuner's trailing JSON `meta` block (the round-trip contract for the next tuner
    session). The shared module says outright "these numbers ARE the contract with BOTH
    stylesheets ... change it here too"; this is what makes that true.

ANTI-VACUITY: every assertion below runs against COMMENT-STRIPPED source and is scoped to the
rule / declaration that owns the value -- both files are heavily commented with the very numbers
being checked, so a bare file-wide substring search would be satisfied by prose. The only
deliberate exception is the tuner's `meta` block, which IS a comment by design and is parsed as
JSON out of the raw text.
"""
import json
import os
import re
from decimal import Decimal, ROUND_HALF_UP

import pytest

from moe_calculator.domain.constants import (
    EFFICIENCY_ANCHOR_X_OFFSET, EFFICIENCY_ANCHOR_Y_FRAC, EFFICIENCY_ANCHOR_Y_OFFSET,
    EFFICIENCY_ANCHOR_Y_OFFSET_LARGE, EFFICIENCY_BAR_STOPS)
from moe_calculator.domain.positioning import anchor_centred
from moe_calculator.domain.rounding import iround_half_away

_WIDGET = os.path.join(os.path.dirname(__file__), "..", "src", "res", "gui", "gameface", "mods",
                       "14th_ua", "MoECalculator")


def _read(name):
    with open(os.path.join(_WIDGET, name)) as handle:
        return handle.read()


# --- comment stripping: no assertion here may be satisfiable by prose ---------

def _no_css_comments(src):
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def _no_js_comments(src):
    # Blocks first (they can contain //), then //-to-EOL. The negative lookbehind keeps a future
    # `coui://` / `img://` URL from being mistaken for a comment.
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)(?<![:/])//.*$", "", src)


def _css():
    return _no_css_comments(_read("MoEEfficiency.css"))


def _js():
    return _no_js_comments(_read("MoEEfficiency.js"))


def _transient():
    """The SHARED transient module -- MoEBarTransient.js. It now owns the surface derivations, the
    engine pushes, the hit-rect collapse and every timing constant; this bar keeps only its own
    BOX_*/PAD_REM (which it hands over) and DELTA_HOLD_MS. Comment-stripped like the rest: that
    file's prose quotes 4000 / 250 / 15 / 600 / 5000 and every derivation by name."""
    return _no_js_comments(_read("MoEBarTransient.js"))


# --- scoped extraction helpers ------------------------------------------------

def _braced(src, pattern, what):
    """The body of the first brace-balanced block whose header matches `pattern`."""
    match = re.search(pattern, src)
    assert match, "MoEEfficiency: no %s" % what
    start = src.index("{", match.start())
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start + 1:i]
    raise AssertionError("MoEEfficiency: unbalanced braces in %s" % what)


def _rule(css, selector):
    """The declarations of one CSS rule, anchored at line start so `.mp-backdrop` cannot be
    satisfied by `.mp-backdrop::before` (nor `#moe-bar-root` by `#moe-bar-root.mp-run`)."""
    return _braced(css, r"(?m)^" + re.escape(selector) + r"\s*\{", "rule %s" % selector)


def _keyframes(css, name):
    return _braced(css, r"@keyframes\s+" + re.escape(name) + r"\s*\{", "@keyframes %s" % name)


def _decl(css, selector, prop):
    """One declaration's value, read out of its OWN rule."""
    body = _rule(css, selector)
    match = re.search(re.escape(prop) + r"\s*:\s*([^;}]+)", body)
    assert match, "MoEEfficiency.css: %s has no %s" % (selector, prop)
    return match.group(1).strip()


def _rem(css, selector, prop):
    value = _decl(css, selector, prop)
    match = re.match(r"^(-?\d+)rem$", value)
    assert match, "MoEEfficiency.css: %s { %s: %s } is not a whole rem" % (selector, prop, value)
    return int(match.group(1))


def _js_const(js, name, what="MoEEfficiency.js"):
    # The `^const NAME = <int>;` shape is DELIBERATE and load-bearing in both bars AND in the
    # shared module (which declares its timings as bare consts and re-exports them at the bottom
    # for exactly this reason): the mirror tests and both tools/dev/check_*_js.js harnesses read
    # these out of the source text.
    match = re.search(r"(?m)^const %s = (-?\d+);" % name, js)
    assert match, "%s: const %s not found (as an integer literal)" % (what, name)
    return int(match.group(1))


def _tconst(name):
    """One integer const out of the SHARED module."""
    return _js_const(_transient(), name, "MoEBarTransient.js")


def _size_factor(name):
    """One of the LARGE size mode's two factors, out of the SHARED MoEBarTransient.js.

    They are FRACTIONAL (1.5 and 4 / 3), so they cannot ride `_js_const`'s integer shape -- and
    SIZE_XF is not even a literal, it is the expression `4 / 3`. Read as a Decimal on purpose: `4/3`
    is not representable, the implementer hit `949.9999999999999` deriving THIS bar's large surface
    from it in float, and everything below compares CSS lengths for exact equality."""
    match = re.search(r"(?m)^const %s = (\d+(?:\.\d+)?)(?:\s*/\s*(\d+))?;" % name, _transient())
    assert match, "MoEBarTransient.js: const %s not found" % name
    value = Decimal(match.group(1))
    return value / Decimal(match.group(2)) if match.group(2) else value


def _derivation(src, line, what):
    """One whole derivation line, anywhere in `src` (the shared module's are indented inside
    createTransient, so this is NOT anchored at column 0 -- only at a line start)."""
    assert re.search(r"(?m)^\s*" + re.escape(line) + r"\s*$", src), \
        "%s: lost the derivation `%s`" % (what, line)


def _meta():
    """The tuner's trailing JSON round-trip block. Deliberately read from the RAW css: it IS a
    comment, and it is the contract the next tuner session re-imports."""
    raw = _read("MoEEfficiency.css")
    chunk = [c for c in raw.split("/*") if '"barStops"' in c]
    assert len(chunk) == 1, "MoEEfficiency.css: expected exactly one tuner meta block"
    body = chunk[0]
    return json.loads(body[body.index("{"):body.rindex("}") + 1])


# --- the surface: .mp-backdrop <-> MoEEfficiency.js's BOX_* -------------------

def test_the_js_box_consts_quote_the_backdrop_rule():
    # THE core mirror. .mp-backdrop is the composition's bounding box; the JS names each of its
    # four values as a const and derives the surface, the shift and the hit rect from them.
    css, js = _css(), _js()
    assert (_js_const(js, "BOX_LEFT_REM"), _js_const(js, "BOX_TOP_REM"),
            _js_const(js, "BOX_W_REM"), _js_const(js, "BOX_H_REM")) == \
        (_rem(css, ".mp-backdrop", "left"), _rem(css, ".mp-backdrop", "top"),
         _rem(css, ".mp-backdrop", "width"), _rem(css, ".mp-backdrop", "height"))


def test_the_backdrop_brackets_the_track_symmetrically():
    # The backdrop is the track plus EQUAL side clearance, which is what lets anchor_centred's
    # `max_x // 2` centre the composition for free (no X compensation term exists). Read the
    # track's own width from its rule and the JS's copy of it.
    css, js = _css(), _js()
    assert _js_const(js, "BAR_W_REM") == _rem(css, "#moe-bar-root", "width")
    assert _js_const(js, "BOX_W_REM") == \
        _js_const(js, "BAR_W_REM") - 2 * _js_const(js, "BOX_LEFT_REM")


def test_this_bar_hands_its_own_box_and_pad_to_the_shared_transient():
    # THE LINK THE REFACTOR ADDED, and the one that keeps every derivation below relevant to THIS
    # bar: the five surface literals stay here, per bar, but the arithmetic moved into
    # MoEBarTransient.js's cfg. If this call ever passed a literal (or the progress bar's numbers)
    # the derivations would still all pass while the surface silently stopped matching
    # .mp-backdrop -- and both _surface_wh() below and EFFICIENCY_ANCHOR_Y_OFFSET read the consts.
    body = _braced(_js(), r"createTransient\(\{", "createTransient call")
    for key, const in (("boxLeft", "BOX_LEFT_REM"), ("boxTop", "BOX_TOP_REM"),
                       ("boxW", "BOX_W_REM"), ("boxH", "BOX_H_REM"), ("pad", "PAD_REM")):
        assert re.search(r"(?m)^\s*%s:\s*%s,\s*$" % (key, const), body), \
            "MoEEfficiency.js: createTransient's `%s` is not this bar's %s" % (key, const)


def test_the_surface_and_shift_are_derived_from_the_box_plus_the_pad():
    # Pin the FORMULAS, not just the numbers: this bar's five literals plus these five lines are
    # the whole surface contract, so a re-tune of the box or the pad propagates instead of drifting.
    # They live in the SHARED module now, keyed to its cfg (which the test above proves is fed from
    # this bar's consts); the old VIEW_*/SHIFT_*/HIT_PAD_REM consts are those same five expressions.
    #
    # FOUR of the five became `let` for the LARGE size mode (applySize re-derives whatever carries a
    # factor), so the DERIVATION is what is pinned, not the keyword -- `(?:const|let)`. shiftY is the
    # exception and stays pinned as a `const`: it is a pure y/uniform rem length that the 1.5x root
    # font scales for free, so a size mode that starts rewriting it is rewriting the wrong axis.
    src = _transient()
    for line in ("viewW = cfg.boxW + 2 * cfg.pad;",
                 "viewH = cfg.boxH + 2 * cfg.pad;",
                 "shiftX = cfg.pad - cfg.boxLeft;",
                 "hitPad = Math.ceil(Math.max(viewW, viewH) / 2);"):
        assert re.search(r"(?m)^\s*(?:const|let) " + re.escape(line), src), \
            "MoEBarTransient.js: lost the derivation `%s`" % line
    assert re.search(r"(?m)^\s*const shiftY = cfg\.pad - cfg\.boxTop;", src), \
        "MoEBarTransient.js: shiftY must stay a pure-y const -- the root font scales it"


def _surface_wh(js):
    pad = _js_const(js, "PAD_REM")
    return _js_const(js, "BOX_W_REM") + 2 * pad, _js_const(js, "BOX_H_REM") + 2 * pad


def _shift_y(js):
    return _js_const(js, "PAD_REM") - _js_const(js, "BOX_TOP_REM")


def _large_surface_wh(js):
    """The surface pushed in the LARGE size mode, derived exactly as MoEBarTransient.applySize
    does it: the x half takes BOTH factors, the y half only SIZE_F, and each is ROUNDED because
    4/3 is not representable (Math.round, so half-AWAY, not py3's banker's rule -- and on THIS
    bar the x term really does land on 949.9999999999999 in float). PAD_REM is slack on both axes
    and takes no x factor."""
    f, xf = _size_factor("SIZE_F"), _size_factor("SIZE_XF")
    pad = _js_const(js, "PAD_REM")
    return (iround_half_away((Decimal(_js_const(js, "BOX_W_REM")) * xf + 2 * pad) * f),
            iround_half_away((Decimal(_js_const(js, "BOX_H_REM")) + 2 * pad) * f))


def _large_shift_y(js):
    """SHIFT_Y_REM in LOGICAL PX under the large mode. The JS never rewrites it -- it is a pure
    y/uniform rem length in `root.style.top`, so the 1.5x root font scales it for free; this
    conversion is what the Python constant has to carry (it is logical px, not rem)."""
    return iround_half_away(Decimal(_shift_y(js)) * _size_factor("SIZE_F"))


def test_the_js_pushes_that_surface_to_the_engine():
    # The size is a JS PUSH, not a ceiling: a view that never calls resizeViewRem gets the
    # engine's 256x256 default-size fallback. Now in the shared module. Scoped to the call, and
    # comment-stripped -- the prose around it names resizeViewRem four times.
    assert re.search(r"viewEnv\.resizeViewRem\(viewW,\s*viewH\)", _transient()), \
        "MoEBarTransient.js: resizeViewRem is not called with viewW, viewH"


def test_the_composition_is_translated_into_the_surface_by_the_shift():
    src = _transient()
    assert re.search(r'root\.style\.left = shiftX \+ "rem";', src)
    assert re.search(r'root\.style\.top = shiftY \+ "rem";', src)


def test_the_hit_rect_is_collapsed_on_all_four_sides():
    # THE SURFACE RECT IS THE MOUSE HIT RECT: a 480rem-wide strip across screen centre would
    # steal HUD input. WG's wrapper passes (top, right, bottom, left, 15); ours are all equal.
    # The call and HIT_MAGIC moved to the shared module; the surface it collapses is still THIS
    # bar's (BOX_* + PAD_REM), which is what makes the arithmetic below this bar's own.
    src = _transient()
    assert re.search(r"viewEnv\.setHitAreaPaddingsRem\("
                     r"hitPad,\s*hitPad,\s*hitPad,\s*hitPad,\s*HIT_MAGIC\)",
                     src), "MoEBarTransient.js: the 5-arg equal-padding hit-area call is gone"
    assert _tconst("HIT_MAGIC") == 15
    surface_w, surface_h = _surface_wh(_js())
    pad = -(-max(surface_w, surface_h) // 2)          # the JS's Math.ceil(max/2)
    assert 2 * pad >= surface_w and 2 * pad >= surface_h, \
        "half the LARGER dimension must collapse BOTH axes to nothing"


def test_the_surface_reassert_outlasts_the_engines_size_deadline():
    # Load-bearing: the engine's `Size calculation timeout` fallback runs LAST and wins, ~2.2s
    # after the view loads (live-measured on the Moving Average bar). Only a POST-deadline
    # re-assert puts the surface right -- and the settled flag, which gates every show trigger,
    # flips off the back of it. All three live in the shared module now (the flag is its closure
    # local `settled`, exposed as T.settled(), not the old module-level `surfaceSettled`).
    assert _tconst("SURFACE_REASSERT_MS") >= 3000, \
        "the re-assert must land comfortably after the observed ~2.2s deadline"
    assert _tconst("SURFACE_SETTLE_MS") > 0, \
        "the surface is only correct a beat AFTER the push round-trips through C++"
    src = _transient()
    assert re.search(r"(?m)^\s*settled = true;\s*$", src), \
        "MoEBarTransient.js: nothing flips the settle flag"
    # ...and it must flip INSIDE the re-assert's callback, not off an independent timer that could
    # outlive it: the re-assert IS the event that makes the surface correct, so the dependency has
    # to be structural. In mount()'s body that means the assignment sits between the timer's
    # opening and its `}, SURFACE_REASSERT_MS);` close.
    mount = _braced(src, r"function mount\(", "mount()")
    assert mount.index("setTimeout(") < mount.index("settled = true;") \
        < mount.index("}, SURFACE_REASSERT_MS);"), \
        "MoEBarTransient.js: the settle flip is no longer nested in the re-assert callback"
    # This bar's show trigger is gated on it (the silent baseline deliberately is not).
    assert re.search(r"if \(gained && T\.settled\(\)\)", _js()), \
        "MoEEfficiency.js: the show trigger is no longer gated on the settle flag"


# --- the sizing shim: emitted, and NOT a third copy of the surface ------------

def test_the_sizing_box_is_static_markup_and_in_flow():
    # It MUST be in the HTML (JS-created content misses the first layout pass) and must not be
    # taken out of flow (an abspos box contributes no content size).
    assert '<div id="moe-bar-box"></div>' in _read("MoEEfficiencyView.html")
    css = _css()
    assert re.search(r"(?m)^body\s*\{\s*margin:\s*0;\s*\}", css), "body margin:0 inflates the box"
    assert "position" not in _rule(css, "#moe-bar-box")


def test_the_sizing_box_stays_the_tuners_emit_and_is_not_the_surface():
    # THE ONE PLACE THIS BAR DIFFERS FROM THE MOVING AVERAGE BAR. The shim is the emit's own
    # rectangle (the bar plus its two caption rows). It provably does not stop the size timeout,
    # so its exact value buys nothing, and "fixing" it to the surface would be silent drift from
    # the tuner -- MoEEfficiencyView.html says so explicitly. Pin the WIDTH to the emit's
    # boxWRem (the HEIGHT is derived -- next test), and assert it is NOT the surface so the
    # tempting edit fails loudly.
    css, js = _css(), _js()
    box_w = _rem(css, "#moe-bar-box", "width")
    box_h = _rem(css, "#moe-bar-box", "height")
    assert box_w == _meta()["boxWRem"] == _js_const(js, "BOX_W_REM")
    assert (box_w, box_h) != _surface_wh(js), \
        "#moe-bar-box is the tuner's emit, not the surface -- see MoEEfficiencyView.html"


def _translate_y(css, selector):
    """The translateY() term of one rule's `transform`, in rem. Read from its OWN rule."""
    value = _decl(css, selector, "transform")
    match = re.search(r"translateY\((-?[\d.]+)rem\)", value)
    assert match, "MoEEfficiency.css: %s { transform } carries no translateY(<n>rem)" % selector
    return float(match.group(1))


def test_the_sizing_boxs_height_is_the_emits_own_five_term_derivation():
    # THE HEIGHT IS DERIVED, AND meta CARRIES NO COPY OF IT (only boxWRem), so before this test it
    # was the one emitted number with ZERO test signal -- it went 51 -> 55 on a re-tune of tickH /
    # tickHC and the whole suite stayed green. The tuner computes it as
    #   round(trackH + (tickH + gapBot) + reqFS + (tickHC + gapTop) + curFS)
    # (eff_bar_tuner.html:944, gaps via gapBot()/gapTop() at :712-713) and every one of those five
    # terms is ALSO emitted into a rule of its own, so re-derive it from the stylesheet rather than
    # hardcoding 55: a DELIBERATE re-tune moves the terms and the box together and still passes,
    # while genuine drift -- a hand-edited box, or a half-copied emit that took the new caption
    # rules and left the old box -- fails. Each term is read from the rule that owns it (the file's
    # prose quotes these very numbers, so a file-wide search would be satisfied by a comment), and
    # the two tick-inclusive gaps are the caption offsets the emit derives them into: .mp-cap.dn's
    # margin-top on the `top:100%` side, and the NEGATED translateY on the `bottom:100%` side,
    # where Coherent drops margin outright. Summed with the repo's half-away rounding so the
    # tie-break matches the emitting JS's Math.round rather than py3's banker's rule.
    from moe_calculator.domain.rounding import iround_half_away
    css = _css()
    track_h = _rem(css, ".mp-track", "height")
    gap_bot = _rem(css, ".mp-cap.dn", "margin-top")
    req_fs = _rem(css, ".mp-cap.dn", "font-size")
    gap_top = -_translate_y(css, ".mp-cap.up")
    cur_fs = _rem(css, ".mp-cap.up", "font-size")
    assert gap_top > 0, \
        "the current caption's translateY must LIFT it off the track (a negative rem), not push " \
        "it down -- got translateY(%grem)" % -gap_top
    assert _rem(css, "#moe-bar-box", "height") == \
        iround_half_away(track_h + gap_bot + req_fs + gap_top + cur_fs), \
        "#moe-bar-box's height is no longer the emit's derivation over .mp-track / .mp-cap.dn / " \
        ".mp-cap.up -- re-copy the WHOLE tuner emit, do not hand-edit the box"


def test_the_document_loads_only_its_own_stylesheet():
    # MoEEfficiency.css reuses #moe-bar-root and the whole .mp-* prefix, IDENTICAL to
    # MoEProgress.css. That is harmless only because each registered view is its own document;
    # loading a second one here would collide every selector.
    html = _read("MoEEfficiencyView.html")
    assert re.findall(r'<link rel="stylesheet" href="([^"]+)"', html) == ["MoEEfficiency.css"]


def test_the_hand_added_font_face_survives_a_tuner_re_emit():
    # HAND-ADDED BLOCK 1: the tuner inlined the ttf as a data: URI, so the emit carries no face
    # for the family #moe-bar-root asks for, and this document links no other stylesheet. The
    # BARE SIBLING url must come FIRST -- Coherent resolves an @font-face src against the
    # DOCUMENT directory only, so a subdir-relative path silently falls back to Arial Narrow.
    face = _braced(_css(), r"@font-face\s*\{", "@font-face block")
    assert re.search(r'font-family:\s*"MoEBattle"', face)
    assert re.search(r"src:\s*url\(MoEBattle\.ttf\)", face), \
        "the bare-sibling url must be the FIRST src entry"
    assert os.path.exists(os.path.join(_WIDGET, "MoEBattle.ttf"))


# --- the Python anchor: derived from the JS, not copied from it ---------------

def test_python_y_offset_cancels_the_js_shift_and_converts_frac_to_viewport():
    # EFFICIENCY_ANCHOR_Y_OFFSET is TWO summed terms, both owned by the JS:
    #   -SHIFT_Y_REM        cancels the composition's intra-surface downward shift, so the bar
    #                       stays put on screen when the window moves.
    #   +frac * VIEW_H_REM  UNIT CONVERSION. anchor_centred applies the fraction to the MOVABLE
    #                       EXTENT (space_h - surface_h), so adding frac*surface_h back turns it
    #                       into a fraction of the VIEWPORT, which is how the constant is tuned.
    # Asserted as the DERIVATION so a deliberate re-tune of the fraction, the pad or the box
    # propagates -- and NOT as the literal 50, which only coincidentally equals SHIFT_Y_REM
    # (round(0.865 * 116) happens to be 2 * 50). Every term is read from the shipped JS.
    js = _js()
    surface_h = _surface_wh(js)[1]
    assert EFFICIENCY_ANCHOR_Y_OFFSET == \
        -_shift_y(js) + int(round(EFFICIENCY_ANCHOR_Y_FRAC * surface_h))


def test_python_large_y_offset_is_the_same_two_terms_scaled_by_size_f():
    # The LARGE twin (mod_settings.progress_bar_size == 1), derived the SAME two ways from the SAME
    # shipped JS -- only every length is in logical px now, so both terms carry SIZE_F and NEITHER
    # carries SIZE_XF (this is the Y axis). No literal 76 here. Unlike the 1x pair there is not even
    # a coincidence to trip over: -(50*1.5) == -75 and round(0.865*116*1.5) == 151 share nothing.
    js = _js()
    surface_h = Decimal(_surface_wh(js)[1])
    assert EFFICIENCY_ANCHOR_Y_OFFSET_LARGE == \
        -_large_shift_y(js) + iround_half_away(Decimal(str(EFFICIENCY_ANCHOR_Y_FRAC))
                                               * surface_h * _size_factor("SIZE_F"))


@pytest.mark.parametrize("space_h", [1080, 1440])
def test_the_composed_placement_puts_the_track_at_the_tuned_viewport_fraction(space_h):
    # THE invariant the offset's second term exists for: the track's top edge lands at
    # EFFICIENCY_ANCHOR_Y_FRAC of the VIEWPORT height, resolution-invariantly -- hence both
    # heights. Composed exactly as efficiency_view._place does it: the far-sentinel clamp hands
    # anchor_centred the movable extent, and the track then sits SHIFT_Y_REM below the window's
    # top edge. Slack is 1.5px: anchor_centred's int() floor loses up to 1, and the offset's own
    # round() up to 0.5.
    #
    # ...AND THE SAME UNDER THE LARGE SIZE MODE, which is that mode's whole point: it is a pure
    # scale-up, so the bar must not MOVE. Every length on the large side is bigger -- the surface,
    # the intra-surface shift, hence the Y compensation -- and the track's top edge still has to
    # come out at the SAME fraction of the same viewport, asserted both against the fraction and
    # directly against the 1x placement.
    js = _js()
    surface_w, surface_h = _surface_wh(js)
    _x, y = anchor_centred(1920 - surface_w, space_h - surface_h, EFFICIENCY_ANCHOR_Y_FRAC,
                           EFFICIENCY_ANCHOR_X_OFFSET, EFFICIENCY_ANCHOR_Y_OFFSET)
    top = y + _shift_y(js)
    assert abs(top - EFFICIENCY_ANCHOR_Y_FRAC * space_h) <= 1.5
    lw, lh = _large_surface_wh(js)
    _lx, ly = anchor_centred(1920 - lw, space_h - lh, EFFICIENCY_ANCHOR_Y_FRAC,
                             EFFICIENCY_ANCHOR_X_OFFSET, EFFICIENCY_ANCHOR_Y_OFFSET_LARGE)
    large_top = ly + _large_shift_y(js)
    assert abs(large_top - EFFICIENCY_ANCHOR_Y_FRAC * space_h) <= 1.5, \
        "the LARGE bar's track lands at %s of the viewport, not %s" % (
            large_top / float(space_h), EFFICIENCY_ANCHOR_Y_FRAC)
    assert abs(large_top - top) <= 2, \
        "the size mode MOVED the bar: 1x track top %s vs large %s" % (top, large_top)


# --- the tuner's meta block: the third leg of every timing -------------------

def test_the_visual_stops_are_the_same_five_the_tuner_emitted():
    # domain/constants.EFFICIENCY_BAR_STOPS is the axis the CSS pins its four requirement ticks
    # to. The tuner's meta is where those percentages came from.
    assert list(EFFICIENCY_BAR_STOPS) == _meta()["barStops"]
    # ...and the four nonzero stops are where the stylesheet ACTUALLY pins the ticks + captions.
    # This half replaces a `== (0, 25, 50, 75, 100)` self-literal that was deleted from
    # tests/test_efficiency_axis.py: the constant became load-bearing when efficiency_bar_x started
    # keying its OUTPUT to it (it interpolates between EFFICIENCY_BAR_STOPS[i-1] and [i]), and meta
    # is a comment while these rules are the emit. Each value is read from the rule that owns the
    # tick/caption pair, comment-stripped -- the file's prose quotes 25 / 50 / 75 / 100 in words.
    css = _css()
    for i, stop in enumerate(EFFICIENCY_BAR_STOPS[1:], start=1):
        rule = re.search(r"(?m)^\.mp-tick\.r%d,\s*\.mp-cap\.r%d\s*\{\s*left:\s*([\d.]+)%%;" % (i, i),
                         css)
        assert rule, "MoEEfficiency.css: no `.mp-tick.r%d, .mp-cap.r%d { left }` rule" % (i, i)
        assert float(rule.group(1)) == float(stop), \
            "stop %d is %s%% in the CSS but %s in EFFICIENCY_BAR_STOPS" % (i, rule.group(1), stop)


def test_the_js_timings_match_the_meta_block():
    # The three transient timings and the two seeks are SHARED with the Moving Average bar now, so
    # they are read out of MoEBarTransient.js -- which is legitimate precisely because both
    # stylesheets' mp-life is identically tuned (this bar's meta is the one asserted here; the
    # progress bar's own mirror test pins its keyframes against its own meta). DELTA_HOLD_MS is
    # NOT shared: it is this bar's only timing of its own and stays in MoEEfficiency.js.
    meta, src = _meta(), _transient()
    assert _tconst("FADE_IN_MS") == meta["fadeInMs"]
    assert _tconst("HOLD_MS") == meta["holdMs"]
    assert _tconst("FADE_OUT_MS") == meta["fadeOutMs"]
    assert _js_const(_js(), "DELTA_HOLD_MS") == meta["deltaHoldMs"]
    assert meta["totalMs"] == meta["fadeInMs"] + meta["holdMs"] + meta["fadeOutMs"]
    for line in ("const TOTAL_MS = FADE_IN_MS + HOLD_MS + FADE_OUT_MS;",
                 "const SEEK_PLATEAU = FADE_IN_MS;",
                 "const SEEK_FADE_OUT = FADE_IN_MS + HOLD_MS;"):
        _derivation(src, line, "MoEBarTransient.js")


def test_the_css_transient_runs_for_exactly_the_js_total():
    # The JS seeks INTO this animation with a negative animation-delay in MILLISECONDS, so its
    # own total and the stylesheet's duration must agree or every seek lands in the wrong phase.
    css, meta = _css(), _meta()
    for selector, name in (("#moe-bar-root.mp-run", "mp-life"),
                           ("#moe-bar-root.mp-run-b", "mp-life-b")):
        anim = _decl(css, selector, "animation")
        assert anim == "%s %dms both" % (name, meta["totalMs"]), \
            "%s: expected `%s %dms both`, got `%s`" % (selector, name, meta["totalMs"], anim)


def test_the_keyframe_stops_are_where_the_js_seeks():
    # SEEK_PLATEAU / SEEK_FADE_OUT are ms into mp-life; the stylesheet expresses the same two
    # instants as PERCENTAGES of the total. Drift here silently re-flashes or re-slides the bar
    # on a re-trigger. 1ms of slack for the 2-decimal percentage.
    meta = _meta()
    total = float(meta["totalMs"])
    stops = [float(s) for s in re.findall(r"(?m)^\s*([\d.]+)%\{", _keyframes(_css(), "mp-life"))]
    assert stops[0] == 0.0 and stops[-1] == 100.0 and len(stops) == 4
    assert abs(stops[1] / 100.0 * total - meta["fadeInMs"]) <= 1.0
    assert abs((100.0 - stops[2]) / 100.0 * total - meta["fadeOutMs"]) <= 1.0


def test_the_twin_keyframe_blocks_stay_identical_modulo_the_name():
    # mp-life-b (HAND-ADDED BLOCK 2) exists ONLY so consecutive runs carry different animation
    # identities -- MoEEfficiency.js's armRun alternates .mp-run / .mp-run-b, because a plain
    # remove/reflow/re-add restart is unproven in Coherent and a coalesced re-add would leave the
    # bar permanently at opacity 0 (the exact bug the Moving Average bar shipped with). So the two
    # must animate IDENTICALLY; a tuner re-emission of mp-life alone is what breaks it.
    css = _css()
    assert _keyframes(css, "mp-life") == _keyframes(css, "mp-life-b")


def test_the_slide_distance_matches_the_tuner_meta():
    # 1rem == 1 LOGICAL PX in Gameface, and WG's own keyframe-translate floor is 3rem -- refuse
    # to regress below it. translateY() must be on ALL FOUR stops (Gameface will not interpolate
    # a transform across mismatched function lists): the two outer stops carry the slide, the two
    # held stops sit at 0.
    css, meta = _css(), _meta()
    rem = meta["slideRem"]
    assert rem >= 3, "a %drem slide is imperceptible at 1rem == 1 logical px" % rem
    for name in ("mp-life", "mp-life-b"):
        assert re.findall(r"translateY\((-?[\d.]+)rem\)", _keyframes(css, name)) == \
            [str(rem), "0", "0", str(rem)], "%s: unexpected slide stops" % name


def test_the_band_classes_are_the_metas_in_order():
    # Python pushes `band` as an INDEX into this list (domain.efficiency_band), so a reorder or a
    # rename silently paints the wrong colour for every band. Each class must also exist in the
    # stylesheet.
    js, css = _js(), _css()
    match = re.search(r"(?m)^const BAND_CLASSES = \[([^\]]*)\];", js)
    assert match, "MoEEfficiency.js: const BAND_CLASSES not found"
    classes = re.findall(r'"([^"]+)"', match.group(1))
    assert classes == [band["cls"] for band in _meta()["bands"]]
    for cls in classes:
        assert re.search(r"\.%s\b" % re.escape(cls), css), \
            "MoEEfficiency.css: band class .%s is never styled" % cls


def test_the_dash_grids_gap_stripe_stays_fully_OPAQUE():
    # MoEProgress.css needed a HAND REWRITE of this same rule; MoEEfficiency.css ships the eff
    # tuner's emit verbatim, and the emit ALREADY carries the corrected form -- the two rules are
    # declaration-for-declaration identical bar `rgb(13,14,16)` vs the equivalent
    # `rgba(13,14,16,1)`. What made it correct is that THE GAP IS ALPHA 1: the grid masks the
    # solid fill (the garage bar's .moe-fill has no background-colour at all and shows the dark
    # track backing through its gaps). At a lower gap alpha the fill floods through and a gap LEFT
    # of the fill edge reads lighter than one to its right -- the "irregular intervals" bug this
    # bar's sibling shipped with. A re-emit at a tuned-down gap alpha is exactly how it comes back.
    gradient = _decl(_css(), ".mp-track::after", "background-image")
    stops = re.findall(r"rgba?\(([^)]*)\)", gradient)
    assert len(stops) == 4, "expected one 2rem dash + 1rem gap period, got %r" % (stops,)
    for gap in stops[2:]:
        parts = [p.strip() for p in gap.split(",")]
        assert len(parts) == 3 or float(parts[3]) == 1.0, \
            "the dash grid's GAP stripe must be fully opaque, not %r" % (gap,)
    # ...while the outset ring stays at the garage bar's 0.5 -- it sits OUTSIDE the fill.
    assert _decl(_css(), ".mp-track::after", "box-shadow") == "0 0 0 1rem rgba(13,14,16,0.5)"


# --- THE "LARGE" SIZE MODE: HAND-ADDED BLOCK 3's .mp-lg rules ---------------------------------
# mod_settings.progress_bar_size == 1. The mode is delivered by the ROOT FONT SIZE (SIZE_F == 1.5,
# which IS the rem->px factor in Gameface), so it needs NO CSS at all for anything uniform -- height,
# fonts, icon boxes, glow radii, the caption offsets and mp-life's slide all follow the root font.
# What is left is the HORIZONTAL x2: an x-length carries an extra SIZE_XF == 4/3 on top of that 1.5,
# and the appended block re-declares X-LENGTHS AND NOTHING ELSE.
#
# The sibling tests/test_progress_surface_mirror.py runs the identical three claims over
# MoEProgress.css -- COMPLETE (every base x-length has a twin, and nothing else does), CORRECT (each
# twin is its base counterpart times 4/3, re-derived here rather than transcribed) and CLEAN (no
# non-x property and no non-rem value was scaled, since scaling any of those DOUBLE-applies SIZE_F).
# The helpers are duplicated per bar exactly like _read / _js_const / _surface_wh above: these two
# mirror files have never shared a module, and each bar's guards belong where its reader looks.
#
# ONE difference from that file: this stylesheet has NO re-derived exception. Its #moe-bar-box is the
# tuner's own emit and coincides with .mp-backdrop's width, so the plain x4/3 holds for every single
# declaration -- which is itself asserted (the box gets its own independent re-derivation below).
#
# Decimal throughout, never float: the repo lesson
# `css-em-arithmetic-needs-decimal-not-float-equality`.
_LG = ".mp-lg "


def _x4_3(text):
    """`text` with every rem length multiplied by SIZE_XF, at the stylesheet's own 3dp."""
    xf = _size_factor("SIZE_XF")

    def _one(match):
        scaled = (Decimal(match.group(1)) * xf).quantize(Decimal("0.001"),
                                                         rounding=ROUND_HALF_UP)
        return format(scaled.normalize(), "f") + "rem"

    return re.sub(r"(-?[\d.]+)rem", _one, text)


# WHICH PROPERTIES CARRY THE X FACTOR, and how much of their value is horizontal. Doubling as the
# CLEAN check: a `.mp-lg` rule declaring anything NOT in here fails, which is what refuses a
# font-size / height / line-height / vertical margin sneaking in.
_X_SCALE = {
    "width": _x4_3, "left": _x4_3, "right": _x4_3,
    "margin-left": _x4_3, "margin-right": _x4_3,
    "padding-left": _x4_3, "padding-right": _x4_3,
    # ONLY the first translate() argument is horizontal. This bar leans on that hard: `.mp-cap
    # .mp-d`'s translate carries the caption gap in x AND the delta's Y nudge in y, and each
    # `.mp-ico` transform chains a per-role translateY -- scaling either would move a glyph
    # vertically, which the root font has already done.
    "transform": lambda v: re.sub(r"(translate\(\s*)(-?[\d.]+rem)",
                                  lambda m: m.group(1) + _x4_3(m.group(2)), v),
    # `<x> <y>`: only the x term tiles horizontally; the y term is `100%` and must stay untouched.
    "background-size": lambda v: " ".join([_x4_3(v.split()[0])] + v.split()[1:]),
    # A 90deg repeating gradient -- every stop is a horizontal offset. The colours carry no rem, so
    # _x4_3 leaves them (and the `90deg`) alone, which is itself part of the CLEAN claim.
    "background-image": _x4_3,
}


def _rules(css):
    """[(selector, declarations)] for every flat rule in already-comment-stripped `css`.

    Deliberately NOT anchored on the preceding `}`: consuming it makes the regex skip every OTHER
    rule. `[^{}@;]` keeps `@font-face` / `@keyframes` headers out, and a keyframe STOP
    (`9.68%{...}`) is dropped by the percentage filter."""
    out = []
    for match in re.finditer(r"([^{}@;]+?)\s*\{([^{}]*)\}", css):
        selector = " ".join(match.group(1).split())
        if not re.match(r"^[\d.]+%$", selector):
            out.append((selector, match.group(2)))
    return out


def _decls(body):
    """[(property, value)] of one rule's declaration block, whitespace-normalized."""
    out = []
    for chunk in body.split(";"):
        prop, sep, value = chunk.partition(":")
        if sep:
            out.append((prop.strip(), " ".join(value.split())))
    return out


def _cascade():
    """({base selector: decls}, {.mp-lg selector: decls}) for MoEEfficiency.css."""
    base, large = {}, {}
    for selector, body in _rules(_css()):
        (large if selector.startswith(_LG) else base)[selector] = body
    return base, large


def _rem_d(body, prop):
    """One rem declaration of an already-extracted rule body, as a Decimal (the file's `_rem`
    reads whole rem only, and every large value is fractional)."""
    match = re.search(r"\b%s:\s*(-?[\d.]+)rem\s*;" % re.escape(prop), body)
    assert match, "MoEEfficiency.css: no %s in `%s`" % (prop, body.strip())
    return Decimal(match.group(1))


def _x_props(body):
    """The properties of one BASE rule that declare a HORIZONTAL rem length.

    Mechanical, not a hand-kept list -- a hand-kept list is how the next x-length gets added with
    no twin and nothing notices:
      * a left/right margin or padding, and `left`/`right` itself, are always x;
      * a `width` in rem is x UNLESS the same rule gives `height` the same value -- that is a
        SQUARE icon box, a uniform length the root font already scales (this bar has four of them:
        .mp-ico, .mp-ico.mk, .mp-ico.bm, .mp-ico.dmg);
      * a translate()'s FIRST argument, when it is a NONZERO rem (0 is invariant under any factor,
        which is what keeps .mp-tick.mp-req's `translateY(0rem)` chain out of this);
      * a background-size / background-image carrying rem (the dash grid's period and stops).
    """
    values = dict(_decls(body))
    out = []
    for prop, value in _decls(body):
        if prop in ("margin-left", "margin-right", "padding-left", "padding-right",
                    "left", "right"):
            hit = re.search(r"-?[\d.]+rem", value)
        elif prop == "width":
            hit = (re.match(r"^-?[\d.]+rem$", value) and values.get("height") != value)
        elif prop == "transform":
            hit = re.search(r"\btranslate\(\s*-?[\d.]*[1-9][\d.]*rem", value)
        elif prop in ("background-size", "background-image"):
            hit = re.search(r"[\d.]+rem", value)
        else:
            hit = None
        if hit:
            out.append(prop)
    return out


def test_the_large_block_twins_exactly_the_base_cascades_x_lengths():
    # COMPLETE, both directions. A base x-length with no twin renders half-scaled horizontally under
    # the large mode; a twin with no base x-length is a rule scaling something the root font already
    # handled (or a selector typo that silently styles nothing).
    base, large = _cascade()
    want = {s for s, body in base.items() if _x_props(body)}
    got = {s[len(_LG):] for s in large}
    assert got == want, "missing .mp-lg twins: %s; twins with no base x-length: %s" % (
        sorted(want - got), sorted(got - want))


def test_every_large_declaration_is_its_base_counterpart_times_four_thirds():
    # CORRECT + CLEAN, in one pass: for every twin declaration, re-derive the expected value from
    # the BASE rule (the independent source) and compare. Because the derivation only ever rewrites
    # rem numbers, this equally asserts that no %, em, `contain`, colour, `90deg` or background-size
    # y-ratio was scaled, and the _X_SCALE lookup refuses any property that is not an x-length.
    # NO exception list, unlike the Moving Average bar's: on this stylesheet the plain x4/3 holds
    # for every declaration, and the count is pinned so a twin cannot go missing here either.
    base, large = _cascade()
    checked = 0
    for selector, body in large.items():
        bare = selector[len(_LG):]
        assert bare in base, "%s overrides a rule that does not exist" % selector
        base_decls = dict(_decls(base[bare]))
        for prop, value in _decls(body):
            assert prop in _X_SCALE, \
                "%s { %s } is not an x-length -- the root font already scales it, so a .mp-lg " \
                "rule DOUBLE-applies SIZE_F" % (selector, prop)
            assert prop in base_decls, "%s { %s } has no base counterpart" % (selector, prop)
            assert value == _X_SCALE[prop](base_decls[prop]), \
                "%s { %s: %s } is not the base `%s` times 4/3" % (selector, prop, value,
                                                                  base_decls[prop])
            checked += 1
    assert checked == 13, "expected 13 x4/3 declarations, checked %d" % checked


def test_the_large_block_carries_no_keyframe_and_no_vertical_length():
    # The CLEAN claim's other half, on the raw text: _X_SCALE above refuses a vertical PROPERTY, but
    # a `@keyframes` (mp-life's slide is a y length, and its identity is what the twin blocks exist
    # for) would not be a rule at all and would slip past the walk entirely. Read from the RAW file
    # so the block's own markers are visible.
    block = _read("MoEEfficiency.css").split('HAND-ADDED BLOCK 3 OF 3')[-1]
    assert "@keyframes" not in block and "%{" not in block, \
        "the .mp-lg block grew a keyframe -- the root font already scales mp-life's slide"


def test_the_large_sizing_box_still_tracks_the_backdrop_not_the_surface():
    # The 1x pin (test_the_sizing_box_stays_the_tuners_emit_and_is_not_the_surface) is that
    # #moe-bar-box's width IS BOX_W_REM -- .mp-backdrop's width, the emit's own rectangle -- and
    # deliberately NOT the surface. Re-derive the large twin the same way, off the large BACKDROP
    # rather than off the base box, so the two stay the same rectangle under the mode; and refuse a
    # restated height, which 92/116rem at a 1.5x root font already delivers.
    _base, large = _cascade()
    assert _rem_d(large[_LG + "#moe-bar-box"], "width") == \
        _rem_d(large[_LG + ".mp-backdrop"], "width")
    assert (_rem_d(large[_LG + "#moe-bar-box"], "width"),
            _rem_d(large[_LG + ".mp-backdrop"], "width")) != _large_surface_wh(_js()), \
        "#moe-bar-box is the tuner's emit, not the surface -- see MoEEfficiencyView.html"
    assert "height" not in dict(_decls(large[_LG + "#moe-bar-box"])), \
        "the large sizing box must not restate a height -- the root font scales the base 55rem"


def test_the_large_block_matches_the_generators_own_copy_of_it():
    # THE OTHER DIRECTION of the splice. check_eff_css.js proves the shipped file is the tuner's emit
    # plus exactly three MARKED regions -- but it STRIPS those regions, so it never looks inside
    # them: a hand-edit to the shipped .mp-lg rules passes it, and then the next
    # `node tools/dev/emit_eff_css.js` silently reverts the edit from the generator's own `LARGE`
    # literal. Pin the rules on BOTH sides, the same shape as the Moving Average bar's tuner pins.
    # Rules only, not the prose: the two comment blocks are allowed to drift in wording.
    _base, large = _cascade()
    generator = _no_css_comments(
        open(os.path.join(os.path.dirname(__file__), "..", "tools", "dev",
                          "emit_eff_css.js")).read())
    for selector, body in large.items():
        for prop, value in _decls(body):
            assert re.search(r"(?m)^" + re.escape(selector) + r"\s*\{[^}]*" +
                             re.escape("%s: %s" % (prop, value)), generator), (
                "tools/dev/emit_eff_css.js does not emit `%s { %s: %s }` -- a re-emit would "
                "revert it" % (selector, prop, value))


def test_the_large_backdrop_stays_symmetric_about_the_track():
    # LOAD-BEARING, and silent when it breaks: there is NO X compensation term in Python, so
    # anchor_centred's `max_x // 2` only centres the bar because the backdrop brackets the track
    # with EQUAL bleed each side (the 1x half of this is
    # test_the_backdrop_brackets_the_track_symmetrically). Break the symmetry under the large mode
    # and X drifts by half the error at every resolution, with every other assertion still green.
    # Tolerance is 0.002rem, not exact: each of the three values is independently rounded to the
    # stylesheet's 3dp (the bleed twice over), so the sum cannot close exactly. It is ~4 orders of
    # magnitude below the smallest real error (a dropped x factor moves the bleed by 26.667rem).
    _base, large = _cascade()
    bleed = -_rem_d(large[_LG + ".mp-backdrop"], "left")
    width = _rem_d(large[_LG + ".mp-backdrop"], "width")
    track = _rem_d(large[_LG + "#moe-bar-root"], "width")
    assert bleed > 0, "the backdrop must start LEFT of the track, not inside it"
    assert abs(width - (track + 2 * bleed)) <= Decimal("0.002"), (
        "the large backdrop is %srem around a %srem track with %srem of left bleed -- "
        "asymmetric, so `max_x // 2` no longer centres the bar" % (width, track, bleed))


def test_the_cap_clamp_corridor_sits_inside_the_backdrop():
    # The current caption may not leave meta.capClamp, expressed in the SAME document rem the
    # backdrop is: the corridor is the backdrop inset by an EQUAL amount each side. Asserted as
    # that relationship rather than as -76 / 376, so a re-tune of the box moves both bounds.
    js, meta = _js(), _meta()
    left = _js_const(js, "CLAMP_L_REM")
    right = _js_const(js, "CLAMP_R_REM")
    assert (left, right) == (meta["capClamp"]["leftRem"], meta["capClamp"]["rightRem"])
    box_left = _js_const(js, "BOX_LEFT_REM")
    box_right = box_left + _js_const(js, "BOX_W_REM")
    assert box_left <= left < right <= box_right, "the corridor must stay inside the backdrop"
    assert left - box_left == box_right - right, "the end inset must be symmetric"
