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
extents. On top of the -1rem: the ICON goes 1 device pixel DOWN, the DELTA 1 device pixel UP (was 2,
retuned 1px down). One device pixel is 1/SIZE_F rem there, because Large IS the root font
(baseFont * SIZE_F == 1 * 1.25), i.e. 0.8rem exactly. The two land on DIFFERENT values (0.3 / 0.7) --
they are independent, move independently, and must never be factored into one constant (at the
earlier SIZE_F == 1.5 they happened to coincide on 0.167rem, which is exactly the coincidence this
independence claim warns against banking on).
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

THE MOVING AVERAGE BAR (MoEProgress.css) TAKES TWO PIECES, FOUR RULES -- the same two the efficiency
bar corrects, and for the same reason. Its captions are flex rows under `align-items: center`, so an
IN-FLOW piece's anchor is (line box - own box) / 2 + the tuned nudge, in rem; the out-of-flow delta
takes the static position (see below) and its anchor is the nudge alone:

    .mp-capC .mp-ico   (20.5 - 16  )/2 + 1    == 3.25   <- 0.25 off the device grid at factor 1,
                                                           0.50 off at factor 2: it CAN drift
    .mp-capP .mp-ico   (18   - 14  )/2 + 0    == 2.00   <- whole rem: whole device pixels at EVERY
    .mp-capR .mp-ico   (18   - 17  )/2 + 0.5  == 1.00      factor, so it cannot resolve differently
    .mp-capR .mp-ico   (18   - 13  )/2 + 0.5  == 3.00      at the two scales and takes no rule
      ^ the SAME nudge rule, the battles glyph's smaller box -- see .mp-ico.battles
    .mp-cap  .mp-d      0           + 2.5     == 2.50   <- 0.5 off the grid at factor 1, whole at
                                                           factor 2: it CAN drift, and does
`.mp-cap.side .mp-v` is not in the table on purpose: its own box IS the line box, so the centring
term is identically 0 at every factor and its -0.5rem is a font-metrics constant, not a residual.
`test_only_the_ma_pieces_off_a_whole_rem_carry_a_correction` re-derives all six rows (both axis-end
glyph families) from the stylesheet, so a future retune that pushes another piece off the grid fails
here instead of shipping uncorrected.

THE DELTA ROW IS A CORRECTED WRONG PREDICTION, KEPT BECAUSE THE WRONG INPUT IS THE PLAUSIBLE ONE.
An earlier revision of this file worked that row as (20.5 - 15.5)/2 + 2.5 == 5.00rem -- a whole rem,
hence whole device pixels at every factor, hence "structurally incapable of drifting" -- and on that
basis DELIBERATELY did not mirror the efficiency bar's delta rule, recording the difference as a real
divergence between the two bars. The maintainer then checked the icon and the delta separately on
screen at interface scale 1 and reported the delta out by the same one device pixel as the icon.
    THE BAD INPUT: "the delta is out of flow with no `top`, so it takes the CENTRED static position it
    would have as the sole flex item." That is CSS Flexbox's rule (an abspos child's static position
    is aligned by align-items / justify-content) and THIS ENGINE DOES NOT IMPLEMENT IT. It places the
    child at the CSS2.1 static position -- the containing block's content-box origin -- so the used
    `top` is 0, there is no centring term, and the tuned translateY is the whole anchor.
    THE PROOF IS THE APPROVED RENDER, NOT A SPEC READING. MoEProgress.css's 2.5rem is the efficiency
    bar's delta Y carried over verbatim, and THERE it is measured from an explicit `top: 0` and is
    exactly the value that centres a 15.5rem delta box on a 20.5rem numeral box. Had this engine
    centred by static position, that same 2.5rem would sit this bar's delta a FURTHER 2.5rem (5 device
    px at factor 2) below its numeral's centre, hanging off the bottom of the caption -- and factor 2
    is the render the composition was approved on. So the two deltas are the SAME shape, land on the
    same 2.50rem anchor, and the mirror was owed all along.
    WHAT WAS CHECKED AND IS *NOT* THE CAUSE: the `.up` / `.dn` padding-vs-margin asymmetry. `.mp-cap.up`
    puts its 6rem gap in padding-bottom and `.mp-cap.dn` in margin-top, and an out-of-flow child's
    PERCENTAGE `top` does resolve against the padding box -- but the delta is on `.dn`, which has no
    padding, and declares no `top`. Nor does Gameface's drop of `margin` on a bottom/right-anchored
    side reach it: the delta's own anchors are `left: 100%` + margin-left, the pairing Coherent honours.

THE MA MAGNITUDE IS EMPIRICAL ON BOTH PIECES -- a weaker footing than the efficiency pair above, and
flagged rather than hidden. No screenshot pair has been taken of this bar; what is known is (a) the
arithmetic above, which says a residual exists and predicts no size (and on the delta predicted no
residual at all until its static-position input was fixed), and (b) the maintainer's live report --
made separately for the glyph and for the delta -- that this bar drifts the same way and by the same
amount as the efficiency bar, whose two corrections were a measured ONE DEVICE PIXEL up-screen. So one
device pixel up-screen is what ships, on each. ONE DEVICE PIXEL IS NOT ONE REM AT BOTH SIZES: Large IS
the root font (baseFont * SIZE_F == 1 * 1.5), so at interface scale 1 the factor is 1 at the Default
size and 1.5 under Large, i.e. 1rem and 1/SIZE_F == 0.667rem. Hence two rules per piece with DIFFERENT
Y, and hence the compound `.mp-s1.mp-lg` -- a lone `.mp-s1` rule would match under Large too and,
later in the file, win with the Default size's pixel.

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
# THE TWO NUDGES ARE INDEPENDENT. They landed on the SAME 0.167rem at the old SIZE_F == 1.5 (a
# coincidence of two opposite nudges one rem apart) and no longer agree at SIZE_F == 1.25 (0.3 vs
# 0.7) -- proof they were never one constant. The delta's own pixel count also moved with the 1px-
# down retune (2 device px UP -> 1 device px UP); the icon's is untouched by that retune.
_CORRECTED = ((".mp-s1 .mp-cap.up .mp-ico", ".mp-cap.up .mp-ico", 0),
              (".mp-s1.mp-lg .mp-cap.up .mp-ico", ".mp-lg .mp-cap.up .mp-ico", +1),
              (".mp-s1 .mp-cap .mp-d", ".mp-cap .mp-d", 0),
              (".mp-s1.mp-lg .mp-cap .mp-d", ".mp-lg .mp-cap .mp-d", -1))

# --- THE MOVING AVERAGE BAR (MoEProgress.css): TWO pieces, FOUR rules -----------------------------
# Everything below is re-derived FROM MoEProgress.css; nothing is transcribed, so a retune of any
# caption's font-size, its line-box pin, a glyph's box or a per-role nudge lands in this file rather
# than silently stranding (or inventing) a correction.
# (corrected selector, the BASE rule it overrides, is it the Large twin). Each pair overrides ONE base
# rule, which is where this bar differs from the sibling: NEITHER size-mode twin
# (`.mp-lg .mp-capC .mp-ico`, `.mp-lg .mp-cap .mp-d`) declares a transform -- both are margin-left --
# so the Large render's Y comes from the base rule too.
# THE DELTA IS BACK: the base rule's anchor is 1.5rem (translateY(2.5rem) -> translateY(1rem) ->
# translateY(1.5rem)), which is fractional again, so it resolves differently at the two factors and
# takes the same one-device-pixel correction as the icon -- see
# test_only_the_ma_pieces_off_a_whole_rem_carry_a_correction, which still derives that from the
# arithmetic rather than assuming it.
_MA_CORRECTED = ((".mp-s1 .mp-capC .mp-ico", ".mp-capC .mp-ico", False),
                 (".mp-s1.mp-lg .mp-capC .mp-ico", ".mp-capC .mp-ico", True),
                 (".mp-s1 .mp-cap .mp-d", ".mp-cap .mp-d", False),
                 (".mp-s1.mp-lg .mp-cap .mp-d", ".mp-cap .mp-d", True),
                 # NEW: the maintainer's "lower the top-row icon 0.5 device px" nudge pushed
                 # .mp-capP .mp-ico off a whole rem too (2.00 -> 2.50) -- same uniform -1-device-px
                 # correction, no Large-specific override on the base (rides SIZE_F, like capC's).
                 (".mp-s1 .mp-capP .mp-ico", ".mp-capP .mp-ico", False),
                 (".mp-s1.mp-lg .mp-capP .mp-ico", ".mp-capP .mp-ico", True))
# EVERY piece this bar hangs off a caption's line box, as
# (nudge rule, caption rule, own-box rule, own-box property, IS IT IN FLOW?). SIX rows for five
# pieces: the right-hand axis caption swaps glyph FAMILIES at 3 marks (.mk -> .moe), and both boxes
# have to land whole for that caption to be correctly ruleless.
# THE LAST FLAG IS THE INPUT THAT WAS WRONG ONCE (see the docstring). The four icons are flex items,
# so align-items:center contributes (line box - own box)/2; the delta is OUT OF FLOW and this engine
# gives it the CSS2.1 static position -- the content-box origin -- so it contributes NOTHING and the
# tuned nudge is the whole anchor. Its line box and the caption's are still read on that row, so a
# retune of either still has to keep them declared and parseable, and so the two numbers the failed
# model used stay visible next to the model that replaced it.
_MA_PIECES = ((".mp-capC .mp-ico", ".mp-cap.dn", ".mp-ico.dmgc", "height", True),
              (".mp-capP .mp-ico", ".mp-cap.up", ".mp-ico.dmgp", "height", True),
              (".mp-capR .mp-ico", ".mp-cap.side", ".mp-ico.mk", "height", True),
              (".mp-capR .mp-ico", ".mp-cap.side", ".mp-ico.moe", "height", True),
              (".mp-capR .mp-ico", ".mp-cap.side", ".mp-ico", "height", True),
              (".mp-cap .mp-d", ".mp-cap.dn", ".mp-cap .mp-d", "line-height", False))


def _bare(css):
    """A stylesheet with every comment stripped. Both files DISCUSS their own selectors and their
    own rejected forms in prose (`NEVER .mp-s1 .mp-lg`), so any structural search that skips this
    is answered by the warning that documents the rule."""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _decl(css, selector, prop, name="MoEEfficiency.css"):
    """One rule's value for one property, whitespace-normalized.

    COMMENTS ARE STRIPPED FIRST and the selector is anchored at the start of a LINE: both
    stylesheets discuss their own selectors in prose (this correction's block quotes
    `.mp-lg .mp-capC .mp-ico` verbatim), and an unscoped search would happily read a sentence as a
    rule -- the repo lesson `unscoped-substring-assertion-is-not-an-assertion`. The rule may be
    single- or multi-line (the delta's base is a full declaration block), so the brace body is read
    whole and the property picked out of it."""
    # `(?<!,\n)` refuses a GROUPED rule's continuation line: MoEProgress.css declares
    # `.mp-cap .mp-v,\n.mp-cap .mp-d { color... }` before the delta's own block, and without this the
    # search reads that shared rule and reports the delta as declaring no line-height.
    match = re.search(r"(?m)^(?<!,\n)" + re.escape(selector) + r"\s*\{([^{}]*)\}", _bare(css))
    assert match, "%s: no rule for `%s`" % (name, selector)
    # (?<![-\w]) not \b: `\bheight:` also matches inside `line-height:`, which would silently read
    # the pinned line box as a glyph's box height in the anchor arithmetic below.
    decl = re.search(r"(?<![-\w])" + re.escape(prop) + r":\s*([^;}]+)[;}]?", match.group(1) + "}")
    assert decl, "%s: `%s` declares no %s" % (name, selector, prop)
    return " ".join(decl.group(1).split())


def _transform(css, selector, name="MoEEfficiency.css"):
    return _decl(css, selector, "transform", name)


def _y_term(transform):
    """The rem Y of a transform, as (match, Decimal). Two shapes: a `translateY(<n>rem)` chained
    onto a centring translate, or the second argument of a single `translate(<x>, <y>)`."""
    match = (re.search(r"translateY\((-?[\d.]+)rem\)", transform) or
             re.search(r"translate\([^,]+,\s*(-?[\d.]+)rem\)", transform))
    assert match, "the rule carries no rem Y term: %s" % transform
    return match, Decimal(match.group(1))


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
    match, base_y = _y_term(transform)
    rem_per_px = 1 / _size_factor() if large else Decimal(1)
    y = (base_y - 1 + nudge_px * rem_per_px).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
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
    # probe (mp-f*). ONE FAMILY survives, `.mp-s1`, and it is now in BOTH stylesheets -- the Moving
    # Average bar's single corrected piece is pinned by the two tests below. Everything else must be
    # gone from both. Matched as RULES / statements, never as prose -- this module's docstring names
    # every one.
    assert not re.search(r"(?m)^\.mp-(?:q\d|p[ab]|c\d|f\d)", _read(_WIDGET, "MoEProgress.css")), \
        "MoEProgress.css still carries a quantisation or probe rule"
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


def _ma_anchor(css, nudge_sel, cap_sel, box_sel, box_prop, in_flow):
    """One MA piece's vertical anchor in rem.

    IN FLOW: (line box - own box) / 2 + the tuned nudge. The caption is a flex row under
    `align-items: center`, so the flex line's cross size is the numeral's line box -- i.e. the PIN
    (tests/test_caption_line_box_pins.py), which is exactly what makes this a constant and therefore
    quantisable at all.
    OUT OF FLOW (the delta): the nudge ALONE. This engine resolves an omitted `top` to the CSS2.1
    static position -- the containing block's content-box origin -- and does NOT apply flexbox's
    align-items centring to an out-of-flow child, so there is no centring term. Asserting the
    centred form here is the bad input this file records; see the docstring. The two boxes are still
    read on that row so a retune cannot quietly remove them.
    Decimal end to end: these are exact-equality comparisons of CSS lengths and IEEE754 has already
    produced a false verdict on byte-identical declarations in this repo
    (`css-em-arithmetic-needs-decimal-not-float-equality`)."""
    line = Decimal(_decl(css, cap_sel, "line-height", "MoEProgress.css")[:-len("rem")])
    own = Decimal(_decl(css, box_sel, box_prop, "MoEProgress.css")[:-len("rem")])
    _match, nudge = _y_term(_transform(css, nudge_sel, "MoEProgress.css"))
    return ((line - own) / 2 if in_flow else Decimal(0)) + nudge


def test_only_the_ma_pieces_off_a_whole_rem_carry_a_correction():
    """WHICH pieces are corrected, derived rather than decided.

    A WHOLE-REM anchor is a whole number of device pixels at EVERY factor, so it resolves the same
    at interface scale 1 and 2 and cannot be what drifted; a fractional one can. On this bar TWO of
    the six rows are fractional -- `.mp-capC .mp-ico` at 3.25rem and `.mp-cap .mp-d` at 2.50rem --
    and both are corrected. The delta row is the one this file got wrong once, by crediting it with a
    flex centring term it does not get and landing it on a whole 5.00rem (docstring); the assertion
    below is now what refuses the REVERSE mistake as well, since dropping the mirror again would
    leave a fractional anchor uncorrected. It equally catches a future retune that pushes another
    caption off a whole rem."""
    css = _read(_WIDGET, "MoEProgress.css")
    by_selector = {}
    for row in _MA_PIECES:
        by_selector.setdefault(row[0], []).append(_ma_anchor(css, *row))
    # THE "MUST AGREE" CHECK IS SCOPED TO FRACTIONAL PIECES ONLY. `.mp-capR .mp-ico` now covers
    # THREE icons sharing one nudge rule: the interchangeable mark family (mk/moe, both a 17rem
    # box, anchor 1.00) and the unrelated battles glyph (a 13rem box, anchor 3.00) -- two GENUINELY
    # different whole-rem anchors that both need no correction, so requiring them to match
    # NUMERICALLY would fail on a distinction that carries no consequence. What actually matters is
    # that only ONE correction rule exists per selector: if any sharing piece is fractional, every
    # piece sharing that selector must land on the exact SAME fractional anchor, or a single shared
    # `.mp-s1` rule cannot correct all of them at once.
    for sel, values in by_selector.items():
        if any(v != v.to_integral_value() for v in values):
            assert len(set(values)) == 1, \
                "%s anchors differently per glyph family -- one of them needs its own rule" % sel
    anchors = {sel: values[-1] for sel, values in by_selector.items()}
    drifting = {sel for sel, a in anchors.items() if a != a.to_integral_value()}
    assert drifting == {base for _sel, base, _large in _MA_CORRECTED}, \
        "the set of MA pieces off a whole rem changed: %s (anchors: %s)" % (
            sorted(drifting), {k: str(v) for k, v in sorted(anchors.items())})
    # ...and the shipped rules cover exactly that set. Anchored at the start of a LINE so the block's
    # own prose -- which names every selector it does NOT correct -- cannot satisfy it.
    ruled = set(re.findall(r"(?m)^\.mp-s1(?:\.mp-lg)? (\.\S+ \.\S+)\s*\{", _bare(css)))
    assert ruled == drifting, \
        "MoEProgress.css corrects %s but the arithmetic says %s" % (sorted(ruled), sorted(drifting))


def test_the_battles_glyph_has_no_box_of_its_own_and_lands_on_a_whole_rem():
    """.mp-ico.battles deliberately takes .mp-ico's BASE 13rem box (MoEProgress.css's own comment:
    "13 is one of only two boxes (13 and 17) that land this .side caption's anchor on a WHOLE rem").
    14/15/16rem would each owe a `.mp-s1`/`.mp-s1.mp-lg` correction pair of their own -- so a future
    "let's make it 14rem" must fail HERE, at test time, rather than as a half-pixel drift in-client.

    Two independent guards: the glyph must declare NO width/height override (or the anchor below is
    computed against the wrong box), and the anchor it actually resolves to -- re-derived from the
    shipped nudge/caption/box rules, never a transcribed literal -- must land on a whole rem."""
    css = _read(_WIDGET, "MoEProgress.css")
    assert not re.search(r"(?m)^\.mp-ico\.battles\s*\{[^}]*\b(?:width|height)\s*:", _bare(css)), \
        "MoEProgress.css: .mp-ico.battles now declares its own box -- re-derive its anchor"
    anchor = _ma_anchor(css, ".mp-capR .mp-ico", ".mp-cap.side", ".mp-ico", "height", True)
    assert anchor == anchor.to_integral_value(), \
        ".mp-ico.battles's box no longer lands the .side caption's icon anchor on a whole rem: " \
        "%s" % anchor


def test_the_battles_glyphs_background_size_is_the_derived_framing_recipe():
    # 331.0% is DERIVED (100/bb*0.75 fed the alpha>32 bbox: (50,48)-(77,77) on a 128px canvas -> bb
    # 0.226563 -> 331.03 -> 331.0), not a literal picked by eye -- see the rule's own comment.
    # SCOPED TO THE OWNING RULE, never a bare substring: the repo lesson
    # `unscoped-substring-assertion-is-not-an-assertion` -- an unscoped grep for "331.0%" would be
    # satisfied by the derivation comment ABOVE the rule (which spells the number in prose) even
    # after the declared value itself were reverted. `_decl` strips comments first and anchors on
    # the selector at the start of a line, so it can only read the rule that actually ships it.
    css = _read(_WIDGET, "MoEProgress.css")
    got = _decl(css, ".mp-ico.battles::after", "background-size", "MoEProgress.css")
    assert got == "331.0%", ".mp-ico.battles::after's background-size is not 331.0%%: %s" % got


def test_the_ma_correction_is_the_base_rule_exactly_one_device_pixel_higher():
    """All four MA rules re-derived from the base rule each overrides.

    ONE DEVICE PIXEL IS NOT ONE REM AT BOTH SIZES: Large IS the root font (baseFont * SIZE_F), so at
    interface scale 1 the rem->px factor is 1 at the Default size and SIZE_F under Large -- 1rem and
    1/SIZE_F == 0.667rem, with SIZE_F scraped out of the shipped JS so the conversion cannot drift
    from the factor the bar applies. That is the entire reason each piece has a Large twin.
    Only the NUMBER is spliced, so the x term (where the base has one) and the unit have to survive
    verbatim for the equality to hold -- which makes this also the "still the base's whole
    declaration" check. A transform declaration REPLACES its base outright: swapping the icon's
    `translate(x, y)` for a bare translateY() would drop the x AND the stacking context scoping its
    ::before glow's z-index:-1, and turning the delta's bare translateY() into a translate() pair
    would silently re-anchor its x."""
    css = _read(_WIDGET, "MoEProgress.css")
    for corrected, base_sel, large in _MA_CORRECTED:
        base = _transform(css, base_sel, "MoEProgress.css")
        match, base_y = _y_term(base)
        rem_per_px = 1 / _size_factor() if large else Decimal(1)
        y = (base_y - rem_per_px).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        want = base[:match.start(1)] + format(y.normalize(), "f") + base[match.end(1):]
        got = _transform(css, corrected, "MoEProgress.css")
        assert got == want, "%s is not `%s` one device pixel higher: %s != %s" % (
            corrected, base_sel, got, want)
        assert got.split("(")[0] == base.split("(")[0], \
            "%s is not `%s`'s own transform function: %s vs %s" % (corrected, base_sel, got, base)


def test_the_ma_large_twin_is_a_compound_and_keeps_the_base_x_verbatim():
    # SPECIFICITY: both classes land on document.body, so a lone `.mp-s1` rule would match under
    # Large as well and -- later in the file, equal specificity -- would win, shipping the Default
    # size's 1rem pixel at 1.5x. `.mp-s1.mp-lg` (0,4,0), no descendant combinator, out-specifies it.
    # NOTHING OUTSIDE THE Y NUMBER MAY DIFFER FROM THE BASE, on either rule of either pair: the icon's
    # x is 0rem (invariant under any factor, which is why its size twin carries no transform at all)
    # and the delta's base declaration is a bare translateY() whose gap rides margin-left. Comparing
    # the prefix and suffix around the spliced number covers both shapes without asserting an x term
    # that one of them legitimately does not have.
    css = _bare(_read(_WIDGET, "MoEProgress.css"))
    assert not re.search(r"(?m)^\.mp-s1 \.mp-lg", css), \
        "the MA Large correction is a DESCENDANT selector -- it cannot out-specify the size mode"
    for plain_row, large_row in ((_MA_CORRECTED[0], _MA_CORRECTED[1]),):
        base = _transform(css, plain_row[1], "MoEProgress.css")
        base_match, _base_y = _y_term(base)
        skeleton = (base[:base_match.start(1)], base[base_match.end(1):])
        plain = _transform(css, plain_row[0], "MoEProgress.css")
        large = _transform(css, large_row[0], "MoEProgress.css")
        assert plain != large, \
            "%s and %s are identical -- one of them is not its own size's device pixel" % (
                plain_row[0], large_row[0])
        for sel, got in ((plain_row[0], plain), (large_row[0], large)):
            got_match, _got_y = _y_term(got)
            assert (got[:got_match.start(1)], got[got_match.end(1):]) == skeleton, \
                "%s did not restate `%s` verbatim outside its Y (%s vs %s)" % (
                    sel, plain_row[1], got, base)
