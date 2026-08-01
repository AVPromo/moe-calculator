# -*- coding: utf-8 -*-
"""The current-damage caption's drift at interface scale 1 -- measured, corrected, and SHIPPED.

TWO elements of `.mp-cap.up` on the Damage Efficiency bar sit ONE device pixel low at factor 1 and
are both correct at factor 2: the damage ICON (`.mp-ico`) and the DELTA (`.mp-cap .mp-d`).

MEASURE AGAINST THE DIGIT BASELINE, NEVER THE DIGIT TOP -- THE TRAP THAT HID THE DELTA FOR A WHOLE
SESSION. The ink TOP is glyph-dependent: it moves with which digits are on screen, so a top-relative
reading made the delta look scale-invariant while the icon looked wrong. Compare WITHIN the row,
baseline-relative, on shots whose UP row is the same shape (both plain 3-digit, no comma):

                                    factor 1 (shot_050)   factor 2 (shot_049, confirmed by _045)
    digits                          1839..1850            1811..1833
    delta                           1841..1849            1813..1829
    delta bottom - digit baseline   -1.00rem              -2.00rem   <- the delta is 1rem LOW
    icon bottom  - digit baseline   -1.00rem              -0.50rem   <- residual 0.5rem, SUB-PIXEL at
                                                                        factor 1: on the grid, and
                                                                        NOT to be touched
    icon ink top - digit top        +1.00rem @thr205      0.00rem @thr205 AND @thr175   <- the icon's
                                    +2.00rem @thr175                                       own fix,
                                                                                           verified

ANCHOR FOR THE TABLE, so the numbers can be trusted: the track top is 1866 at factor 1 and 1860 at
factor 2 in every shot, and the caption row sits at a different REM offset from the track at the two
scales (line-box rounding). That is exactly why only within-row, baseline-relative comparisons mean
anything here. BOTH corrections are verified live at the Default size: the icon's ink top 1841 ->
1840 at factor 1, the delta's baseline offset -1.00rem -> -2.00rem matching factor 2, and factor 2
itself pixel-identical to the approved render (shot_052 against shot_049).

THE LARGE MODE AT FACTOR 1 TAKES TWO MORE TERMS, EYEBALLED AND NOT MEASURED -- a calibration of the
composition by the maintainer's eye, distinct in kind from the -1rem above, which came off ink
extents. On top of the -1rem: the ICON goes 1 device pixel DOWN, the DELTA 2 device pixels UP. One
device pixel is 1/SIZE_F rem there, because Large IS the root font (baseFont * SIZE_F == 1 * 1.5),
i.e. 0.667rem. Both values land on 0.167rem, which is a COINCIDENCE of two opposite nudges one rem
apart -- they are independent, will move independently, and must never be factored into one constant.
The Default-size pair takes NO nudge (verified above), and Large at factor 2 carries no class at all,
so it renders the untouched base.

WHY. With the line box pinned (tests/test_caption_line_box_pins.py) the icon's anchor is a constant:
line/2 - own box/2 + nudge == 20.5/2 - 16/2 + 0.5 == 2.75rem. That is a whole number of DEVICE pixels
only where the rem->px factor is a multiple of 4: a whole half pixel at factor 2 (the approved
render), 0.75 of one at factor 1, where the engine resolves the remainder DOWN-SCREEN. That says WHY
a residual exists at one factor and not the other; it does NOT predict the size of any correction.
Every -1rem here is a SCREENSHOT, and each element is corrected on ITS OWN measurement -- which is
why the icon's remaining -0.50rem residual is left alone (sub-pixel at factor 1) while the delta,
a full -1.00rem out, takes the same -1rem the icon's ink measurement produced.

THE GATE. `MoEBarTransient.setQuantClass()` puts `.mp-s1` on document.body when the root-font capture
reads below 1.5. That capture IS a valid interface-scale signal on the DEFAULT path: a four-bit
screenshot probe (four candidate quantities, four distinct elements, one fresh-launch shot per scale)
read it below 1.5 at scale 1 and at/above 1.5 at scale 2. THE OTHER THREE CANDIDATES ARE NOT SIGNALS
AND DO NOT NEED RE-MEASURING: `window.devicePixelRatio` and `window.innerWidth / viewW` both read a
constant 1 at either scale, and `window.innerHeight / viewH` a constant ratio.

THE ONE MEASUREMENT TRAP, and the reason a scale-2 build once read as "regressed": A MID-SESSION
INTERFACE-SCALE CHANGE LEAVES THE CLASS STALE. The gate is evaluated on the post-deadline re-assert
and on every size flip; nothing carries a live scale change into the bar's document (Python sees one
-- settingsCore.interfaceScale.onScaleChanged -> battle_bridge._on_scale_changed -- but there is no
VM field for it, and `baseFont` is captured once). So a shot taken after changing the scale in the
running client is NOT a measurement of the gate. Relaunch between scales, every time. (This replaces
an earlier post-mortem in this file which concluded from two shots that shared a client session that
the base font "reads ~1 regardless of interface scale". That is DISPROVEN -- the confound was exactly
this staleness.)

A SECOND DEFECT FROM THE SAME BRANCH STRUCTURE, and why the gate is not latched: the shipped build
called setQuantClass() only from the `else` of the `if (large) setRootFont();` re-assert, so `.mp-s1`
and `.mp-lg` could coexist by exactly one route -- launch at Default, then enable Large mid-session
-- and the correction applied or not depending on HOW the user reached Large. It now runs
unconditionally there AND on every applySize flip, in both directions (toggle(cls, force) removes).

WHAT DID NOT WORK, so a later build does not repeat it:
  1. A custom property (`--mp-qy-*`). WRONG BY CONSTRUCTION: Gameface DROPS THE WHOLE DECLARATION on
     an unresolved var(), which here costs the icon its gap to the numeral AND the stacking context
     scoping its glow. `test_no_stylesheet_leaks_a_custom_property` is the rail that stops a repeat.
  2. A class + per-factor rules on `document.documentElement`. Never matched -- it must be the BODY.
  3. An EXACT-STRING bucket key (`px === 1`) -- an exact match on an engine-reported number fails
     silently. Hence a threshold, never a key.
  4. A single `.mp-s1` rule per element, for both size modes. Later in the file and at equal or
     higher specificity, it also beats the `.mp-lg` twin and replaces its x-length. Hence the
     compound `.mp-s1.mp-lg`.
  5. A quantiser that snapped the anchor to the device grid: provably an IDENTITY
     (`corrected * f` IS `floor(ideal * f)`). Deleted, not parked.
  6. Reading the drift off the digit TOP. Glyph-dependent, and it hid the delta for a whole session
     (see the table above). Baseline-relative, within-row, same-shape shots -- always.
"""
import os
import re
from decimal import Decimal, ROUND_HALF_UP

from test_caption_line_box_pins import _read, _WIDGET

# The four shipped rules: (corrected selector, the BASE rule it overrides, the DEVICE-PIXEL nudge).
# The current-damage caption's ICON and its DELTA, each with its `.mp-lg` twin. Re-derived from the
# base rather than transcribed, so a future retune of either Y moves its correction with it (the repo
# lesson `derived-emitted-value-with-no-meta-copy-is-untested`).
#
# TWO KINDS OF TERM, DELIBERATELY NOT MERGED. Every value is `base - 1rem`, the MEASURED correction
# (ink extents / the digit baseline). The two LARGE rules then carry a second term: a nudge EYEBALLED
# against the Large render at interface scale 1, in whole DEVICE PIXELS, positive = down-screen. It is
# a calibration of the composition, not a derivation, so it is spelled as the pixel count the
# maintainer actually judged and converted here -- retuning a shipped value by hand without moving its
# pixel count fails this file.
# THE TWO NUDGES ARE INDEPENDENT. They currently produce the SAME 0.167rem, which is a coincidence of
# two opposite nudges one rem apart; they will move independently and must never become one constant.
_CORRECTED = ((".mp-s1 .mp-cap.up .mp-ico", ".mp-cap.up .mp-ico", 0),
              (".mp-s1.mp-lg .mp-cap.up .mp-ico", ".mp-lg .mp-cap.up .mp-ico", +1),
              (".mp-s1 .mp-cap .mp-d", ".mp-cap .mp-d", 0),
              (".mp-s1.mp-lg .mp-cap .mp-d", ".mp-lg .mp-cap .mp-d", -2))


def _transform(css, selector):
    """One rule's whole `transform` value. The rule may be single- or multi-line (the delta's base
    is a full declaration block), so the brace body is read and the property picked out of it."""
    match = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^{}]*)\}", css)
    assert match, "MoEEfficiency.css: no rule for `%s`" % selector
    decl = re.search(r"\btransform:\s*([^;]+);", match.group(1))
    assert decl, "MoEEfficiency.css: `%s` declares no transform" % selector
    return " ".join(decl.group(1).split())


def _size_factor():
    """SIZE_F, the Large mode's root-font factor, READ OUT OF THE SHIPPED JS.

    Large IS the root font (`baseFont * SIZE_F`), so 1 device pixel at interface scale 1 + Large is
    1/SIZE_F rem. Scraped rather than restated, so the px->rem conversion below can never drift from
    the factor the bar actually applies."""
    match = re.search(r"(?m)^const SIZE_F = ([\d.]+);", _read(_WIDGET, "MoEBarTransient.js"))
    assert match, "MoEBarTransient.js no longer declares `const SIZE_F = <n>;`"
    return Decimal(match.group(1))


def _corrected(transform, nudge_px, large):
    """`transform` with its Y term moved by `-1rem + nudge_px device pixels`, everything else kept.

    Two shapes, because the two corrected elements spell their Y differently: the icon chains a
    `translateY(<n>rem)` onto its centring translate, the delta carries Y as the second argument of a
    single `translate(<x>, <y>)`. Only the NUMBER is spliced, so the x term, the -50% centring and the
    unit all have to survive verbatim for the comparison to hold -- which is what makes this one
    assertion also the "the full compound transform is still there" check.

    A device pixel is 1/SIZE_F rem under Large and 1rem at the shipped size (where every nudge is 0
    anyway, so the branch only documents the intent). Quantised to the stylesheet's own 3dp.

    Decimal, never float: this is an exact-equality comparison of a CSS length, and IEEE754 has
    already produced a false "these differ" on byte-identical declarations in this repo
    (`css-em-arithmetic-needs-decimal-not-float-equality`) -- and here 1/1.5 is precisely the kind of
    value that would."""
    match = (re.search(r"translateY\((-?[\d.]+)rem\)", transform) or
             re.search(r"translate\([^,]+,\s*(-?[\d.]+)rem\)", transform))
    assert match, "the base rule carries no rem Y term to correct: %s" % transform
    rem_per_px = 1 / _size_factor() if large else Decimal(1)
    y = (Decimal(match.group(1)) - 1 + nudge_px * rem_per_px).quantize(Decimal("0.001"),
                                                                      rounding=ROUND_HALF_UP)
    return transform[:match.start(1)] + format(y.normalize(), "f") + transform[match.end(1):]


def test_no_stylesheet_leaks_a_custom_property():
    # THE ONE RAIL ATTEMPT 1 ABOVE IS WHY: GAMEFACE DROPS THE WHOLE DECLARATION ON AN UNRESOLVED
    # var(). On a `transform` that costs the element its entire positioning, not merely the term that
    # could not resolve. A rail around EVERY shipped stylesheet, not just the two bars, because the
    # trap is the engine's and not this feature's -- both generators enforce the same thing on their
    # own emit (`-EmitCss`'s driver and eff_bar_tuner's selfCheck); this is what catches a hand-edit.
    #
    # COMMENTS STRIPPED FIRST, across the whole file rather than per line: two stylesheet headers NAME
    # the trap in prose (`NO var(--color-*)`), so an unstripped search is FAILED by the warning that
    # documents the rule -- `unscoped-substring-assertion-is-not-an-assertion` in reverse.
    leaks = []
    for name in sorted(os.listdir(_WIDGET)):
        if not name.endswith(".css"):
            continue
        bare = re.sub(r"/\*.*?\*/", "", _read(_WIDGET, name), flags=re.S)
        leaks += ["%s: %s" % (name, line.strip()) for line in bare.splitlines() if "var(--" in line]
    assert not leaks, "a shipped stylesheet uses a custom property:\n  " + "\n  ".join(leaks)


def test_nothing_from_the_abandoned_attempts_is_still_shipped():
    # THE CLEAN-UP GATE. Every attempt in the docstring left rules or JS in the tree at some point:
    # quantisation buckets (mp-q*), per-element probe classes (mp-p*, mp-c*) and the four-bit carrier
    # probe (mp-f*). ONE thing survives, in ONE stylesheet -- `.mp-s1` in MoEEfficiency.css. The
    # Moving Average bar is out of scope and must carry NO scale rule at all: its own caption geometry
    # was never measured at factor 1, and a rule there would move a render nobody has checked.
    # Matched as RULES / statements, never as prose -- this module's docstring names every one.
    assert not re.search(r"(?m)^\.mp-(?:q\d|p[ab]|c\d|f\d|s\d)", _read(_WIDGET, "MoEProgress.css")), \
        "MoEProgress.css carries a quantisation, probe or correction rule -- that bar is out of scope"
    assert not re.search(r"(?m)^\.mp-(?:q\d|p[ab]|c\d|f\d)", _read(_WIDGET, "MoEEfficiency.css")), \
        "MoEEfficiency.css still carries a quantisation or probe rule"
    code = re.sub(r"(?m)^\s*//.*$", "",
                  re.sub(r"/\*[\s\S]*?\*/", "", _read(_WIDGET, "MoEBarTransient.js")))
    for gone in ("QUANT_CLASSES", "quantY", "probeFactor", 'classList.add("mp-'):
        assert gone not in code, "MoEBarTransient.js still carries `%s`" % gone


def test_the_correction_is_the_base_rule_one_rem_higher_plus_its_named_pixel_nudge():
    """THE FOUR SHIPPED RULES, re-derived from the base cascade they override.

    -1rem is the MEASURED correction (the icon's ink top 1841 -> 1840 at interface scale 1; the
    delta's bottom -1.00rem from the digit baseline against -2.00rem at scale 2) and NOT the output
    of any box arithmetic -- the anchor sum in the docstring says why a residual exists, not how big
    it is. The two Large rules then add a nudge EYEBALLED against the Large render at scale 1, in
    whole device pixels over SIZE_F (scraped from the JS).
    Pinning each as `base - 1rem + <pixel count>` rather than as a literal is what keeps a future
    retune of a caption's Y from silently leaving its correction behind, AND what refuses a hand
    retune of a shipped value that does not move the pixel count with it."""
    css = _read(_WIDGET, "MoEEfficiency.css")
    for corrected, base, nudge_px in _CORRECTED:
        got = _transform(css, corrected)
        want = _corrected(_transform(css, base), nudge_px, corrected.startswith(".mp-s1.mp-lg"))
        assert got == want, "%s is not `%s` one rem higher %+d device px: %s != %s" % (
            corrected, base, nudge_px, got, want)
        # ALWAYS THE FULL COMPOUND TRANSFORM: a bare translateY() REPLACES the whole declaration and
        # silently drops the icon's -50% centring (and with it the stacking context that scopes the
        # ::before glow's z-index:-1) or the delta's whole x gap. _corrected splices only the NUMBER,
        # so the equality above already carries this -- restated here as an explicit rail because the
        # failure is invisible in a screenshot at the scale that has no class.
        assert got.startswith("translate("), "%s is not a full compound transform: %s" % (corrected,
                                                                                          got)
        if "-50%" in _transform(css, base):
            assert ", -50%)" in got, "%s dropped the -50%% centring: %s" % (corrected, got)


def test_every_large_twin_is_a_compound_selector_so_it_out_specifies_the_size_mode():
    # SPECIFICITY, and the reason each element takes TWO rules instead of one. Both classes land on
    # document.body, so a lone `.mp-s1 ...` rule -- later in the file and at equal or higher
    # specificity -- would also beat the `.mp-lg` twin and replace its x-length (the icon's -1.333rem
    # with -1rem, the delta's 5.6rem with 4.2rem), shoving the element sideways at scale 1 + Large.
    # `.mp-s1.mp-lg` (both classes on the SAME element, no descendant combinator) out-specifies the
    # twin outright, so only Y moves.
    css = _read(_WIDGET, "MoEEfficiency.css")
    compounds = [row[0] for row in _CORRECTED if row[0].startswith(".mp-s1.mp-lg")]
    assert len(compounds) == 2 and ".mp-s1 .mp-lg" not in css, \
        "a Large correction is not a COMPOUND selector -- it would swallow the size mode's x"
    # ...and the pairs really do carry DIFFERENT x terms, which is the whole point of the compound:
    # if they matched, one of the two is not the size mode's own x.
    for plain_sel, large_sel in ((_CORRECTED[0][0], _CORRECTED[1][0]),
                                 (_CORRECTED[2][0], _CORRECTED[3][0])):
        plain, large = _transform(css, plain_sel), _transform(css, large_sel)
        assert plain.split(",")[0] != large.split(",")[0], \
            "%s and %s share an x term -- one of them is not the size mode's" % (plain_sel, large_sel)


def test_the_class_is_gated_on_a_threshold_and_re_evaluated():
    # THE CSS ABOVE IS INERT WITHOUT THIS, and every failure mode must land on the base cascade (the
    # render the maintainer approved at interface scale 2). A THRESHOLD, never an exact key; a
    # POSITIVE lower bound, so the untrusted read captureBaseFont() returns before the view has a size
    # leaves the class OFF; and never a consultation of `large`. Behaviour is asserted in
    # tools/dev/check_efficiency_js.js (which mutation-probes all three); this is the source pin that
    # runs in the always-on suite.
    js = _read(_WIDGET, "MoEBarTransient.js")
    assert js.count('document.body.classList.toggle("mp-s1", px > 0 && px < 1.5);') == 1, \
        "MoEBarTransient.js no longer gates .mp-s1 on the threshold + trust bound"
    assert js.count("\n        setQuantClass();") == 1, "applySize no longer re-evaluates the gate"
    assert js.count("\n                setQuantClass();") == 1, \
        "the post-deadline re-assert no longer evaluates the gate on BOTH size paths"
    assert "else setQuantClass" not in js, \
        "the gate is latched to one branch again -- that is the defect this file records"
