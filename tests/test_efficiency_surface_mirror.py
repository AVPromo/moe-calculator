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
  * domain/constants.EFFICIENCY_ANCHOR_Y_SHIFT is now the PURE intra-surface shift term alone
    (just -SHIFT_Y_REM) -- asserted as its DERIVATION off the shipped JS, never as a literal, so a
    deliberate re-tune of the pad or the box still passes while genuine drift fails. The
    extent-to-viewport UNIT CONVERSION the retired two-term EFFICIENCY_ANCHOR_Y_OFFSET composite
    also carried is gone: positioning.anchor_centred_reduced computes it algebraically by applying
    the fraction to space_y directly (see its docstring), so this constant needs no surface-height
    term at all.
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
    EFFICIENCY_ANCHOR_X_OFFSET, EFFICIENCY_ANCHOR_Y_FRAC, EFFICIENCY_ANCHOR_Y_SHIFT,
    EFFICIENCY_ANCHOR_Y_SHIFT_LARGE, EFFICIENCY_BAR_STOPS, VERTICAL_ANCHOR_Y_SHIFT,
    VERTICAL_ANCHOR_Y_SHIFT_LARGE)
from moe_calculator.domain.positioning import anchor_centred_reduced, anchor_offset
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
    # ALL FIVE are now `let`, so the DERIVATION is what is pinned, not the keyword --
    # `(?:const|let)`. FOUR became `let` for the LARGE size mode (applySize re-derives whatever
    # carries a factor). shiftY joined them in Phase 1 for a DIFFERENT reason, not a size-mode one:
    # goVertical() (the vertical orientation's ONE-TIME mount-time DOM/geometry switch) genuinely
    # swaps the whole composition box -- the vertical box is TALLER than it is wide where the
    # horizontal one is the reverse -- so shiftY = cfg.pad - cfg.boxTop is recomputed there too. Do
    # not "fix" this back to `const`: that would break the vertical bar's surface shift, not
    # restore an invariant.
    #
    # THE X PAIR IS NOW SPELLED `padX`, NOT `pad`, and that is a generalisation rather than a
    # change: `padX` is normalised to `pad` at the top of createTransient, so `2 * padX` and
    # `padX - boxLeft` are byte-identical to what THIS bar always computed. Only the vertical
    # Moving Average composition supplies its own (MoEProgress.js's V_PAD_X_REM -- its
    # right-anchored captions grow LEFTWARD past the backdrop and PAD_REM clipped them).
    src = _transient()
    for line in ("viewW = cfg.boxW + 2 * cfg.padX;",
                 "viewH = cfg.boxH + 2 * cfg.pad - cfg.clipB;",
                 "shiftX = cfg.padX - cfg.boxLeft;",
                 "shiftY = cfg.pad - cfg.boxTop;",
                 "hitPad = Math.ceil(Math.max(viewW, viewH) / 2);"):
        assert re.search(r"(?m)^\s*(?:const|let) " + re.escape(line), src), \
            "MoEBarTransient.js: lost the derivation `%s`" % line


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
    # (`showEvents` -- the "Events" visibility switch -- sits between the two; the settle gate is
    # still the last term, and it is the one this test owns.)
    assert re.search(r"if \(gained && model\.showEvents !== false && T\.settled\(\)\)", _js()), \
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


def _eff_tuner():
    """tools/dev/eff_bar_tuner.html -- the SINGLE source of truth for every number in this bar's
    base cascade: MoEEfficiency.css's non-`.mp-lg` half IS this tuner's emit, byte-for-byte
    (tools/dev/emit_eff_css.js re-assembles it and check_eff_css.js gates the drift). Read RAW:
    SCHEMA is JS, not CSS, so the CSS comment strippers above do not apply -- and every assertion
    on it below is scoped to the ONE `{id:"..."}` entry that owns the value."""
    with open(os.path.join(os.path.dirname(__file__), "..", "tools", "dev",
                           "eff_bar_tuner.html")) as handle:
        return handle.read()


def _knob(name):
    """One SCHEMA knob's default `val`, scoped to its own entry, as a Decimal.

    Scoped and not a bare search on purpose: the tuner's prose and its selfCheck() PROBE VALUES
    quote these very numbers (selfCheck deliberately re-emits at -1.75 / -2.25 / -1.25), so a
    file-wide grep for a value here would be satisfied by a probe that has nothing to do with the
    shipped default."""
    match = re.search(r'\{id:"%s",[^}]*\bval:(-?[\d.]+)\}' % re.escape(name), _eff_tuner())
    assert match, "eff_bar_tuner.html: no SCHEMA entry for knob '%s'" % name
    return Decimal(match.group(1))


def _css_num(value):
    """A Decimal as the tuner's emit spells it (no trailing zeros, never exponent form)."""
    return format(value.normalize(), "f")


def test_the_current_rows_delta_and_icon_sit_at_their_tuned_y():
    """The current-damage row's delta and icon Ys, PINNED AS VALUES and against their knobs.

    Neither had independent signal before this test: the only thing asserting them was the
    base<->`.mp-lg` twin lockstep below, so a coherent 3rem shift -- the tuner default, the shipped
    base rule, the shipped twin and emit_eff_css.js's copy of the twin, all four together -- left the
    suite fully green (that shift was attempted, and reverted, precisely because nothing caught it).
    Two claims per value, because they fail differently:

      LOCKSTEP  the shipped rule is what the knob emits. This stylesheet's base half is the
                tuner's emit byte-for-byte, so a stylesheet-only pin lets the next
                `node tools/dev/emit_eff_css.js` revert it silently (the repo lesson
                `emitcss-is-not-the-whole-shipped-stylesheet`, and how this bar's sibling lost its
                delta size once already).
      THE VALUE the literal the live pass settled on. A pure knob has no derivation to check it
                against, so the literal IS the pin -- and it is what refuses a coherent shift.

    THE DELTA'S X IS TREATED THE OTHER WAY ROUND: 4.2rem is not a knob, it is dGap * dFS at the
    tuner's own 2dp (`dTf`, eff_bar_tuner.html:706), so it is RE-DERIVED from those two knobs
    rather than restated -- a genuine retune of the gap or the delta's size moves both and still
    passes, while drift in one alone fails. The Y half must NOT pick up that derivation, which is
    the whole reason they share one translate(): only the FIRST argument is horizontal.
    """
    css = _css()
    # X: derived. Y: pinned. Asserted as ONE whole declaration so a dropped argument fails too --
    # a `translate(4.2rem)` renders no Y at all and would satisfy two separate half-assertions.
    gap_x = (_knob("dGap") * _knob("dFS")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert _decl(css, ".mp-cap .mp-d", "transform") == \
        "translate(%srem, %srem)" % (_css_num(gap_x), _css_num(_knob("dY"))), \
        "the delta's translate is not `dGap*dFS` in x and the dY knob in y"
    assert _knob("dY") == Decimal("2.5"), \
        "eff_bar_tuner.html's dY default is %s -- the live pass settled the delta at 2.5rem" % (
            _knob("dY"),)
    # The icon keeps its gap in the SAME transform (Coherent drops margin on the `right:100%`
    # side), so only the chained translateY() is this row's Y nudge.
    assert Decimal(str(_translate_y(css, ".mp-cap.up .mp-ico"))) == _knob("icoyCur"), \
        "the current row's icon Y is not the icoyCur knob -- a re-emit would move the glyph"
    assert _knob("icoyCur") == Decimal("0.5"), \
        "eff_bar_tuner.html's icoyCur default is %s -- the live pass settled the glyph at " \
        "0.5rem" % (_knob("icoyCur"),)


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
    #
    # Phase 1 (vertical port) added a SECOND link, MoEEfficiencyVertical.css, scoped under
    # `#moe-bar-root.mev` so it stays disjoint from the horizontal `.mp-*`/`.me-*` rules while both
    # sheets are loaded together. ORDER IS LOAD-BEARING, not incidental: with both sheets present,
    # source order is the cascade tiebreak for any rule of equal specificity that appears in both
    # (see memory `equal-specificity-before-rules-resolved-by-source-order`), so the horizontal
    # sheet must stay first and the vertical sheet second -- reversing them would silently let the
    # vertical rules win the tiebreak against the horizontal ones instead of the other way round.
    html = _read("MoEEfficiencyView.html")
    assert re.findall(r'<link rel="stylesheet" href="([^"]+)"', html) == \
        ["MoEEfficiency.css", "MoEEfficiencyVertical.css"]


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

def test_python_y_shift_cancels_the_js_intra_surface_shift():
    # EFFICIENCY_ANCHOR_Y_SHIFT is now the PURE term -- just -SHIFT_Y_REM, cancelling the
    # composition's intra-surface downward shift so the bar stays put on screen when the window
    # moves. Asserted as the DERIVATION so a deliberate re-tune of the pad or the box propagates.
    # The extent-to-viewport UNIT CONVERSION the retired two-term EFFICIENCY_ANCHOR_Y_OFFSET
    # composite also carried (round(0.865 * 116), which happened to equal 2 * SHIFT_Y_REM by
    # coincidence) is gone -- anchor_centred_reduced computes it algebraically now.
    js = _js()
    assert EFFICIENCY_ANCHOR_Y_SHIFT == -_shift_y(js)


def test_python_large_y_shift_is_the_same_pure_term_scaled_by_size_f():
    # The LARGE twin (mod_settings.progress_bar_size == 1), derived the SAME way from the SAME
    # shipped JS -- only in logical px now, so it carries SIZE_F and NOT SIZE_XF (this is the Y
    # axis). No literal here: a retune of the pad or the box propagates, and so does SIZE_F itself.
    js = _js()
    assert EFFICIENCY_ANCHOR_Y_SHIFT_LARGE == -_large_shift_y(js)


def _v_surface_wh(js):
    """The vertical surface this bar's JS pushes to the engine -- V_BOX_W_REM + 2*PAD_REM on the
    width, V_BOX_H_REM + 2*PAD_REM - V_CLIP_B_REM on the height (MoEBarTransient.js's
    `viewH = cfg.boxH + 2 * cfg.pad - cfg.clipB;`), the same derivation as _surface_wh above but
    off the `V_` (vertical) box consts and this bar's own clip."""
    pad = _js_const(js, "PAD_REM")
    return (_js_const(js, "V_BOX_W_REM") + 2 * pad,
            _js_const(js, "V_BOX_H_REM") + 2 * pad - _js_const(js, "V_CLIP_B_REM"))


def _v_shift_y(js):
    """MoEEfficiency.js's vertical SHIFT_Y_REM (goVertical's `cfg.pad - cfg.boxTop`, fed from
    V_BOX_TOP_REM) -- mirrored (negated) in Python as VERTICAL_ANCHOR_Y_SHIFT."""
    return _js_const(js, "PAD_REM") - _js_const(js, "V_BOX_TOP_REM")


def test_the_vertical_box_consts_quote_the_backdrop_rule():
    # V_BOX_* is .mev-backdrop -- the vertical composition's own bounding box, axis-swapped from
    # .mp-backdrop/BOX_* above. Mirrors test_the_js_box_consts_quote_the_backdrop_rule's contract
    # under the vertical prefix -- comment-stripped like the rest of this file.
    css, js = _no_css_comments(_read("MoEEfficiencyVertical.css")), _js()
    assert (_js_const(js, "V_BOX_LEFT_REM"), _js_const(js, "V_BOX_TOP_REM"),
            _js_const(js, "V_BOX_W_REM"), _js_const(js, "V_BOX_H_REM")) == \
        (_rem(css, ".mev-backdrop", "left"), _rem(css, ".mev-backdrop", "top"),
         _rem(css, ".mev-backdrop", "width"), _rem(css, ".mev-backdrop", "height"))
    assert (_js_const(js, "V_BOX_LEFT_REM"), _js_const(js, "V_BOX_TOP_REM"),
            _js_const(js, "V_BOX_W_REM"), _js_const(js, "V_BOX_H_REM")) == (-40, -80, 96, 360)


def test_the_vertical_clip_is_fed_from_its_own_constant():
    # `viewH`'s `- cfg.clipB` term (MoEBarTransient.js) is only meaningful if the vertical config
    # actually hands it V_CLIP_B_REM by name -- a literal or a copy of the progress bar's constant
    # would still satisfy every OTHER derivation test while the clip silently drifted.
    js = _js()
    assert re.search(r"clipB:\s*V_CLIP_B_REM\s*[,}]", js), \
        "MoEEfficiency.js: vert config's clipB is not fed from V_CLIP_B_REM"
    assert _js_const(js, "V_CLIP_B_REM") == 62


def test_the_vertical_css_sizing_box_matches_the_js_surface():
    # body.mev #moe-bar-box mirrors V_BOX_W_REM + 2*PAD_REM on width, V_BOX_H_REM + 2*PAD_REM -
    # V_CLIP_B_REM on height, exactly as the horizontal #moe-bar-box mirrors BOX_W/H_REM + 2*PAD_REM
    # in test_the_js_box_consts_quote_the_backdrop_rule's sibling coverage for this bar's OWN
    # surface push.
    css = _no_css_comments(_read("MoEEfficiencyVertical.css"))
    match = re.search(r"body\.mev #moe-bar-box\s*\{\s*width:\s*(\d+)rem;\s*height:\s*(\d+)rem;\s*\}",
                       css)
    assert match, "MoEEfficiencyVertical.css: body.mev #moe-bar-box rule not found"
    box = (int(match.group(1)), int(match.group(2)))
    assert box == _v_surface_wh(_js()) == (116, 318)


def test_the_vertical_shift_matches_progresss_and_is_pinned():
    # VERTICAL_ANCHOR_Y_SHIFT is ONE constant for BOTH bars (unlike the horizontal 44-vs-50
    # split): both vertical compositions share the same backdrop geometry (top: -80rem,
    # height: 360rem) and the same PAD_REM == 10, so THIS bar's independent derivation must land
    # on the exact same shared value the progress mirror file derives off ITS OWN JS.
    js = _js()
    assert VERTICAL_ANCHOR_Y_SHIFT == -_v_shift_y(js) == -90


def test_the_vertical_large_shift_is_the_same_pure_term_scaled_by_size_f():
    # The LARGE twin -- half-away rounding, the same convention every other *_SHIFT_LARGE uses
    # (-112.5 -> -113).
    js = _js()
    assert VERTICAL_ANCHOR_Y_SHIFT_LARGE == \
        -iround_half_away(Decimal(_v_shift_y(js)) * _size_factor("SIZE_F")) == -113


def test_the_vertical_large_box_reproduces_the_pinned_logical_surface():
    # body.mev.mp-lg #moe-bar-box restates ONLY the width, in rem, at V_BOX_W_REM*SIZE_XF +
    # 2*PAD_REM (the root font's SIZE_F is layered on top of every rem for free, including this
    # one and the unrestated height) -- so the LOGICAL PX surface under Large is this rem value
    # times SIZE_F for width, and the default height times SIZE_F alone. Pinned per the plan:
    # efficiency vertical Large -> 185 x 398.
    css, js = _no_css_comments(_read("MoEEfficiencyVertical.css")), _js()
    match = re.search(r"body\.mev\.mp-lg #moe-bar-box\s*\{\s*width:\s*(\d+)rem;\s*\}", css)
    assert match, "MoEEfficiencyVertical.css: body.mev.mp-lg #moe-bar-box rule not found"
    large_w_rem = int(match.group(1))
    xf, f = _size_factor("SIZE_XF"), _size_factor("SIZE_F")
    pad = _js_const(js, "PAD_REM")
    assert large_w_rem == _js_const(js, "V_BOX_W_REM") * xf + 2 * pad
    _, default_h = _v_surface_wh(js)
    assert (iround_half_away(Decimal(large_w_rem) * f),
            iround_half_away(Decimal(default_h) * f)) == (185, 398)


def test_the_reachable_minimap_gap_equals_surface_h_minus_track_y():
    # THE INVARIANT the two placement fixes exist to satisfy, pinned from BOTH sides rather than
    # just the tuned constant: the engine clamps every window into [0, space - surface] (memory
    # `engine-clamps-every-wulf-window-to-screen-and-the-mod-depends-on-it`), so whenever
    # gap_bottom is smaller than the surface's own below-the-track slack (surface_h - edge_y) the
    # closest reachable bottom gap IS that slack, not the tuned constant -- and it only equals the
    # tuned constant because the front-end clip (V_CLIP_B_REM) was sized to make it so. A surface
    # retune that forgets to also retune the clip would silently detach this bar from its tuned
    # gap; this test is the tripwire for that.
    from moe_calculator.domain.constants import (
        EFFICIENCY_MM_GAP_BOTTOM, MM_TRACK_Y, MM_TRACK_Y_LARGE)

    js = _js()
    _, surface_h = _v_surface_wh(js)
    assert surface_h - MM_TRACK_Y == EFFICIENCY_MM_GAP_BOTTOM

    # LARGE is a +/-1 JITTER, not bit-exact (see the sibling progress mirror's copy of this test):
    # for THIS bar the two independent half-away roundings happen to cancel exactly (398 - 363 ==
    # 35, round(28 * 1.25) == 35), unlike the progress bar's measured 1-off jitter -- still asserted
    # as a bounded +/-1 rather than a bit-exact 0 so a future retune of either bar cannot silently
    # tighten this into a coincidence the code doesn't actually guarantee.
    f = _size_factor("SIZE_F")
    surface_h_large = iround_half_away(Decimal(surface_h) * f)
    tuned_large = iround_half_away(Decimal(EFFICIENCY_MM_GAP_BOTTOM) * f)
    delta = (surface_h_large - MM_TRACK_Y_LARGE) - tuned_large
    assert abs(delta) <= 1, (
        "the Large reachable gap drifted by %d from round(gap * SIZE_F), which must be a bounded "
        "+/-1 jitter, never more" % delta)


def test_the_vertical_dash_grids_gap_stripe_stays_fully_opaque():
    # This bar's vertical tuner already emitted opaque -- see "Dash-gap alpha -- CLOSED": no
    # hand-rewrite was owed here (unlike the vertical PROGRESS bar, whose own tuner default was
    # 0.5 and needed one). SCOPED to .mev-track::after's OWN gradient -- a bare value search for
    # "1" or "0.5" would either miss this rule entirely or false-hit the box-shadow ring in the
    # SAME rule, which is legitimately rgba(13,14,16,0.5) (it sits OUTSIDE the fill and is not
    # what this instruction touches).
    body = _rule(_no_css_comments(_read("MoEEfficiencyVertical.css")), ".mev-track::after")
    match = re.search(r"background-image:\s*repeating-linear-gradient\(([^;]*)\);", body)
    assert match, "MoEEfficiencyVertical.css: .mev-track::after has no repeating-linear-gradient"
    stops = re.findall(r"rgba?\(([^)]*)\)", match.group(1))
    assert len(stops) == 4, "expected one dash + one gap stop pair, got %r" % (stops,)
    for gap in stops[2:]:
        parts = [p.strip() for p in gap.split(",")]
        assert len(parts) == 3 or float(parts[3]) == 1.0, \
            "the vertical dash grid's GAP stripe must be fully opaque, not %r" % (gap,)
    box_shadow = re.search(r"box-shadow:\s*([^;]+);", body)
    assert box_shadow and box_shadow.group(1).strip() == "0 0 0 1rem rgba(13,14,16,0.5)"


def test_the_large_size_block_never_re_adds_the_deleted_vertical_dash_grid_rule():
    # Phase 0's "second defect found" fix DELETED (not rescaled) the vertical EFFICIENCY bar's
    # Large dash-grid rule -- a 0deg grid's period is a y-length the root font already scales, so
    # a reintroduced twin would double-apply SIZE_F (this file's own HAND-EDIT 4/5 comment, in so
    # many words). Asserted as a SELECTOR search on COMMENT-STRIPPED source, not a substring:
    # ".mev-lg" and ".mev-track" BOTH appear legitimately, more than once, in the HAND-EDIT prose
    # documenting this very deletion -- a bare `grep -c` trips on its own documentation (this is
    # the exact mistake recorded against this task; probed below by reintroducing the rule, not
    # by editing one).
    css = _no_css_comments(_read("MoEEfficiencyVertical.css"))
    assert not re.search(r"\.mp-lg\s+\.mev-track::after\s*\{", css), \
        "MoEEfficiencyVertical.css: the deleted Large dash-grid rule for .mev-track::after is back"
    assert not re.search(r"(?m)^\.mev-lg\b", css), \
        "MoEEfficiencyVertical.css: a .mev-lg selector survived the tuner-class rewrite to .mp-lg"


@pytest.mark.parametrize("space_h", [1080, 1440])
def test_the_composed_placement_puts_the_track_at_the_tuned_viewport_fraction(space_h):
    # THE invariant the pure shift term exists for: the track's top edge lands at
    # EFFICIENCY_ANCHOR_Y_FRAC of the VIEWPORT height, resolution-invariantly -- hence both
    # heights. Composed exactly as bar_window.BarHost._resolve does it now: the far-sentinel clamp
    # hands anchor_centred_reduced the movable extent AND the full space_y (the fraction applies to
    # space_y directly -- no extent-to-viewport conversion needed, see anchor_centred_reduced's
    # docstring), then the stored X/Y stepper offset (0 here) composes on top via anchor_offset,
    # and the track sits SHIFT_Y_REM below the window's top edge. Slack is 1.5px for the int()
    # floor.
    #
    # ...AND THE SAME UNDER THE LARGE SIZE MODE, which is that mode's whole point: it is a pure
    # scale-up, so the bar must not MOVE. Every length on the large side is bigger -- the surface,
    # the intra-surface shift, hence the Y compensation -- and the track's top edge still has to
    # come out at the SAME fraction of the same viewport, asserted both against the fraction and
    # directly against the 1x placement.
    js = _js()
    surface_w, surface_h = _surface_wh(js)
    max_x, max_y = 1920 - surface_w, space_h - surface_h
    base = anchor_centred_reduced(max_x, max_y, space_h, EFFICIENCY_ANCHOR_Y_FRAC,
                                  EFFICIENCY_ANCHOR_Y_SHIFT)
    _x, y = anchor_offset(base, EFFICIENCY_ANCHOR_X_OFFSET, 0)
    top = y + _shift_y(js)
    assert abs(top - EFFICIENCY_ANCHOR_Y_FRAC * space_h) <= 1.5
    lw, lh = _large_surface_wh(js)
    lmax_x, lmax_y = 1920 - lw, space_h - lh
    lbase = anchor_centred_reduced(lmax_x, lmax_y, space_h, EFFICIENCY_ANCHOR_Y_FRAC,
                                   EFFICIENCY_ANCHOR_Y_SHIFT_LARGE)
    _lx, ly = anchor_offset(lbase, EFFICIENCY_ANCHOR_X_OFFSET, 0)
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


def test_the_vertical_twin_keyframe_blocks_stay_identical_modulo_the_name():
    # mev-life-b is the SAME re-trigger twin for the VERTICAL composition (Phase 0's "built from
    # ONE builder called TWICE so they are byte-identical by construction rather than by hand" --
    # MoEBarTransient.js's RUN_CLASSES_V/RUN_NAMES_V alternate .mev-run / .mev-run-b the same way
    # the horizontal pair above alternates .mp-run/.mp-run-b). Comment-stripped and brace-balanced
    # so it survives the compact, unspaced emit this stylesheet actually ships
    # (`@keyframes mev-life{...}}`, no space before the brace).
    css = _no_css_comments(_read("MoEEfficiencyVertical.css"))
    assert _keyframes(css, "mev-life") == _keyframes(css, "mev-life-b")


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
    """`text` with every rem AND em length multiplied by SIZE_XF, at the stylesheet's own 3dp.

    The UNIT IS PRESERVED, and `em` is in here for the reason the sibling
    tests/test_progress_surface_mirror.py spells out: an `em` x-length is a horizontal length like
    any other and still owes SIZE_XF on top of the root font, and a rem-only matcher is blind to it
    -- which is how THAT stylesheet shipped its delta gap 25% short under the size mode. This bar
    happens to spell that same gap in rem (the x half of `.mp-cap .mp-d`'s translate), so today the
    `em` branch is latent here; it is kept in lockstep anyway, because the next `em` x-length added
    to this file must not be invisible too."""
    xf = _size_factor("SIZE_XF")

    def _one(match):
        scaled = (Decimal(match.group(1)) * xf).quantize(Decimal("0.001"),
                                                         rounding=ROUND_HALF_UP)
        return format(scaled.normalize(), "f") + match.group(2)

    return re.sub(r"(-?[\d.]+)(r?em)", _one, text)


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
        # `.mp-s1` / `.mp-s1.mp-lg` are HAND-ADDED BLOCK 4's INTERFACE-SCALE correction and are
        # dropped here: they are conditional overrides of the base cascade, not x-length twins of it,
        # and the pair already IS its own size-mode twin (the compound selector, at (0,5,0), is what
        # keeps the Large x). tests/test_caption_anchor_quantisation.py pins their exact values.
        # ANCHORED WITH A DIGIT on purpose: an earlier `.mp-c` form of this exclusion also swallowed
        # every `.mp-cap` BASE rule and silently emptied the walk of the declarations it exists to
        # check.
        if re.match(r"\.mp-s\d\b", selector):
            continue
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
      * a left/right margin or padding, and `left`/`right` itself, are always x -- in rem OR em
        (`r?em`), for the reason _x4_3 above gives: reading this as rem-only is exactly how the
        sibling stylesheet's `margin-left: 0.35em` went twinless;
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
            hit = re.search(r"-?[\d.]+r?em", value)
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
    # COMPLETE, both directions, and per DECLARATION rather than per selector -- the sibling file's
    # _lg_completeness spells out why: a rule that ALREADY has a twin hides the next x-length added
    # to it, which is the same species of miss as the untwinned gap that shipped. A base x-length
    # with no twin renders half-scaled horizontally under the large mode; a twin with no base
    # x-length is a rule scaling something the root font already handled (or a selector typo that
    # silently styles nothing).
    base, large = _cascade()
    want = {(s, p) for s, body in base.items() for p in _x_props(body)}
    got = {(s[len(_LG):], p) for s, body in large.items() for p, _v in _decls(body)}
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
    # Scoped to BLOCK 3's own markers: BLOCK 4 (the temporary diagnostic) follows it in the file.
    # Scoped to BLOCK 3's own markers: BLOCK 4 (the temporary probe) follows it in the file.
    block = _read("MoEEfficiency.css").split('HAND-ADDED BLOCK 3 OF 4')[-1] \
                                      .split('END HAND-ADDED BLOCK 3')[0]
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
