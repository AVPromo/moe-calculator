# -*- coding: utf-8 -*-
"""Static guards on the progress bar's DUPLICATED values (surface size, twin keyframes).

The window has no hot-reload, so a drift between two copies of the same value costs a full client
relaunch to notice. Everything here is a text-level assertion on the shipped files; the module's
BEHAVIOUR is checked by tools/dev/check_progress_js.js instead.

THE SURFACE SIZE is written down THREE times.

MoEProgress.js's VIEW_W_REM / VIEW_H_REM (derived from the composition's measured box + PAD_REM)
are the source of truth. They are also spelled out as literals in MoEProgress.css's #moe-bar-box
(the static sizing shim that makes the document measurable, so the engine's 256x256 default-size
fallback never fires -- see MoEProgressView.html), and BOTH of them feed
domain/constants.PROGRESS_ANCHOR_Y_OFFSET: it cancels the JS's SHIFT_Y_REM and converts the
placement fraction from the movable extent to the viewport using the surface height.

The battle window has no hot-reload, so a drift between the three costs a client relaunch to
notice: assert the actual EMITTED VALUES here rather than trusting the comments.
"""
import os
import re
from decimal import Decimal, ROUND_HALF_UP

import pytest

from moe_calculator.domain.constants import (
    PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_FRAC, PROGRESS_ANCHOR_Y_OFFSET,
    PROGRESS_ANCHOR_Y_OFFSET_LARGE)
from moe_calculator.domain.positioning import anchor_centred
from moe_calculator.domain.rounding import iround_half_away

_WIDGET = os.path.join(os.path.dirname(__file__), "..", "src", "res", "gui", "gameface", "mods",
                       "14th_ua", "MoECalculator")


def _read(name):
    with open(os.path.join(_WIDGET, name)) as handle:
        return handle.read()


def _js_const(src, name):
    match = re.search(r"^const %s = (-?\d+);" % name, src, re.M)
    assert match, "MoEProgress.js: const %s not found" % name
    return int(match.group(1))


def _size_factor(name):
    """One of the LARGE size mode's two factors, out of the SHARED MoEBarTransient.js.

    They are FRACTIONAL (1.5 and 4 / 3), so they cannot ride `_js_const`'s integer shape -- and
    SIZE_XF is not even a literal, it is the expression `4 / 3`. Read as a Decimal on purpose: `4/3`
    is not representable, the implementer already hit `949.9999999999999` deriving the surface from
    it in float, and this file compares CSS lengths for exact equality."""
    src = _read("MoEBarTransient.js")
    match = re.search(r"^const %s = (\d+(?:\.\d+)?)(?:\s*/\s*(\d+))?;" % name, src, re.M)
    assert match, "MoEBarTransient.js: const %s not found" % name
    value = Decimal(match.group(1))
    return value / Decimal(match.group(2)) if match.group(2) else value


def _css_box(src):
    match = re.search(r"#moe-bar-box\s*{\s*width:\s*(\d+)rem;\s*height:\s*(\d+)rem;\s*}", src)
    assert match, "MoEProgress.css: #moe-bar-box width/height rule not found"
    return int(match.group(1)), int(match.group(2))


def _surface_wh(js):
    """The surface size the JS pushes to the engine -- its VIEW_W_REM / VIEW_H_REM."""
    pad = _js_const(js, "PAD_REM")
    return _js_const(js, "BOX_W_REM") + 2 * pad, _js_const(js, "BOX_H_REM") + 2 * pad


def _shift_y(js):
    """MoEProgress.js SHIFT_Y_REM -- how far DOWN the composition sits inside its own surface."""
    return _js_const(js, "PAD_REM") - _js_const(js, "BOX_TOP_REM")


def _large_surface_wh(js):
    """The surface the JS pushes in the LARGE size mode, derived exactly as
    MoEBarTransient.applySize does it: the x half takes BOTH factors, the y half only SIZE_F,
    and each is ROUNDED because 4/3 is not representable (Math.round, hence half-AWAY, not py3's
    banker's rule). PAD_REM is slack on both axes and takes no x factor."""
    f, xf = _size_factor("SIZE_F"), _size_factor("SIZE_XF")
    pad = _js_const(js, "PAD_REM")
    return (iround_half_away((Decimal(_js_const(js, "BOX_W_REM")) * xf + 2 * pad) * f),
            iround_half_away((Decimal(_js_const(js, "BOX_H_REM")) + 2 * pad) * f))


def _large_shift_y(js):
    """SHIFT_Y_REM in LOGICAL PX under the large mode. The JS never rewrites it -- it is a pure
    y/uniform rem length in `root.style.top`, so the 1.5x root font scales it for free; this
    conversion is what the Python constant has to carry (it is logical px, not rem)."""
    return iround_half_away(Decimal(_shift_y(js)) * _size_factor("SIZE_F"))


def test_css_sizing_box_matches_the_js_surface():
    assert _css_box(_read("MoEProgress.css")) == _surface_wh(_read("MoEProgress.js"))


def test_the_sizing_box_is_static_markup_and_in_flow():
    # It MUST be in the HTML (JS-created content misses the first layout pass) and must not be
    # taken out of flow (an abspos box contributes no content size -- the original bug).
    assert '<div id="moe-bar-box"></div>' in _read("MoEProgressView.html")
    css = _read("MoEProgress.css")
    assert re.search(r"^body\s*{\s*margin:\s*0;\s*}", css, re.M), "body margin:0 inflates the box"
    assert "#moe-bar-box" in css and "position" not in _css_rule(css, "#moe-bar-box")


def _css_rule(src, selector):
    match = re.search(re.escape(selector) + r"\s*{([^}]*)}", src)
    assert match, "MoEProgress.css: no rule for %s" % selector
    return match.group(1)


def _keyframes(css, name):
    match = re.search(r"@keyframes %s \{(.*?)\n\}" % re.escape(name), css, re.S)
    assert match, "MoEProgress.css: no @keyframes %s block" % name
    return match.group(1)


def test_the_twin_keyframe_blocks_stay_identical_modulo_the_name():
    # mp-life-b exists ONLY so consecutive runs carry different animation identities (MoEProgress.js
    # armRun alternates between them), so the two must animate IDENTICALLY -- an edit to one that
    # misses the other silently gives every second run a different look. Currently protected by a
    # comment; a tuner re-emission or a hand-tuned stop is exactly what breaks it.
    css = _read("MoEProgress.css")
    assert _keyframes(css, "mp-life") == _keyframes(css, "mp-life-b")


def test_the_slide_distance_matches_the_tuner_json():
    # The trailing JSON block is the tuner's round-trip contract: it must state the distance the
    # keyframes actually animate, or the next tuner session re-emits the wrong slide. 1rem == 1
    # LOGICAL PX in Gameface -- the original 1 was invisible in-game, so also refuse to regress to
    # anything below WG's own 3rem keyframe-translate floor.
    css = _read("MoEProgress.css")
    slide = re.search(r'"slideRem":\s*(\d+)', css)
    assert slide, "MoEProgress.css: the trailing JSON has no slideRem"
    rem = int(slide.group(1))
    assert rem >= 3, "a %drem slide is imperceptible at 1rem == 1 logical px" % rem
    for name in ("mp-life", "mp-life-b"):
        block = _keyframes(css, name)
        # translateY() on ALL FOUR stops (Gameface needs matching function lists): the two outer
        # stops carry the slide, the two held stops sit at 0rem.
        assert re.findall(r"translateY\((-?[\d.]+)rem\)", block) == \
            [str(rem), "0", "0", str(rem)], "%s: unexpected slide stops" % name


def _sole_rule_decls(css, selector, what):
    """Declarations of the rule whose ENTIRE selector list is `selector`, comments stripped.

    Both halves matter and both have already drawn blood. COMMENTS: a value assertion was once
    satisfied by a comment merely NAMING the trap -- and the comment above this file's delta rule
    now spells out `font-size 12rem` and `2.5rem` in prose, so an unstripped search passes with the
    rule reverted. SCOPING: MoEProgress.css carries a SECOND rule that lists `.mp-cap .mp-d` as the
    tail of `.mp-cap .mp-v, .mp-cap .mp-d`, so a bare selector search finds THAT one first (in the
    sibling MoEEfficiency.css it was worse still -- .mp-cap.dn emits the identical
    `font-size: 12rem` string, and a bare grep for it passed after the delta's size was reverted).
    Anchoring on `}` (or the file start) is what refuses a selector that is only part of a list,
    and the count assertion refuses a silent second definition.
    """
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    hits = re.findall(r"(?:^|\})\s*%s\s*\{([^}]*)\}" % re.escape(selector), bare, re.S)
    assert len(hits) == 1, "%s: expected exactly one `%s` rule, found %d" % (what, selector,
                                                                            len(hits))
    return hits[0]


def test_the_delta_carries_the_efficiency_bars_size_and_nudge():
    # A live pass settled the recent-delta's look on the Damage Efficiency bar; the maintainer asked
    # for the SAME size and nudge here. The values are MoEEfficiency.css's `.mp-cap .mp-d` --
    # font-size 12rem and the Y half of its translate(4.2rem, 2.5rem). Only the Y half: the X gap is
    # already margin-left: 0.35em == the same 4.2rem at 12rem (see the centring test below, which
    # pins that gap and the anchor it hangs off). Adding an X term here would DOUBLE the gap.
    # The tuner is asserted alongside because MoEProgress.css is a -EmitCss output: pinning only the
    # stylesheet lets the next re-emit revert this silently, which is how it was lost once already.
    decls = _sole_rule_decls(_read("MoEProgress.css"), ".mp-cap .mp-d", "MoEProgress.css")
    assert re.search(r"\bfont-size:\s*12rem\s*;", decls), "delta font-size is not 12rem"
    assert re.search(r"\btransform:\s*translateY\(2\.5rem\)\s*;", decls), "delta Y nudge is not 2.5rem"
    tuner = _read_tuner()
    assert tuner.count("font-size: 12rem;\\n") == 1 and \
        tuner.count("transform: translateY(2.5rem);\\n") == 1, \
        "gen_bar_tuner.ps1 -EmitCss no longer emits the delta size/nudge -- a re-emit would revert it"


def _rem(decls, prop, what):
    """The rem value of `prop` within one rule's declarations, as a Decimal."""
    match = re.search(r"\b%s:\s*(-?[\d.]+)rem\s*;" % re.escape(prop), decls)
    assert match, "%s: no %s in `%s`" % (what, prop, decls.strip())
    return Decimal(match.group(1))


def test_the_two_centre_captions_are_centred_on_the_numeral_not_the_row():
    """.mp-cap's translateX(-50%) must halve the DIGITS' box, not icon+numeral(+delta).

    Both siblings therefore have to leave that box, and each needs its own mechanism:

    THE ICON stays in flow and cancels its own outer width with margin-left == -(its box + the
    gap), so -box-gap + box + gap == 0 and the numeral starts at the caption's origin. In flow
    because it must keep .mp-capP/.mp-capC's per-role translateY -- which is also the stacking
    context scoping the ::before glow's z-index:-1 -- and because an abspos icon would need a
    top:50% that, on .up, resolves against a PADDING box carrying the 6rem gap and drops the glyph
    half of it. RE-DERIVED here from the box + gap the emit computes the margin from (dmgPBox /
    dmgCBox / icoGap), never from the emitted literal: a genuine retune moves all of them together
    and still passes, while drift in one alone fails. Decimal, not float -- the gap slider steps in
    0.5 and IEEE754 makes such sums compare unequal.

    THE DELTA cannot use a margin: its text width changes, so any fixed negative would leave the
    centring drifting with the digits. It goes out of flow off the numeral's right edge instead,
    and `left: 100%` + margin-left is the pairing Coherent honours (it is the `right:100%` and
    `bottom:100%` anchors that render a margin as 0).

    The .side captions must NOT be cancelled: they are not centred on anything, they hang off the
    axis ends by their own gap, so a negative margin there would slide the whole label inwards.
    """
    css = _read("MoEProgress.css")
    gap = _rem(_sole_rule_decls(css, ".mp-cap .mp-ico", "MoEProgress.css"), "margin-right",
               "MoEProgress.css")
    for cap, glyph in ((".mp-capP", ".mp-ico.dmgp"), (".mp-capC", ".mp-ico.dmgc")):
        box = _rem(_sole_rule_decls(css, glyph, "MoEProgress.css"), "width", "MoEProgress.css")
        decls = _sole_rule_decls(css, cap + " .mp-ico", "MoEProgress.css")
        assert _rem(decls, "margin-left", "MoEProgress.css") == -(box + gap), \
            "%s's icon does not cancel its own %srem box + the %srem gap" % (cap, box, gap)
        # ...and the per-role Y is still on the SAME rule's transform, not traded for a margin.
        assert re.search(r"\btransform:\s*translate\(0rem,\s*-?[\d.]+rem\)\s*;", decls), \
            "%s's icon lost the transform that scopes its glow's z-index" % cap
    for cap in (".mp-capL", ".mp-capR"):
        assert "margin-left" not in _sole_rule_decls(css, cap + " .mp-ico", "MoEProgress.css"), \
            "%s is a .side caption -- cancelling its icon slides the label over the track" % cap
    delta = _sole_rule_decls(css, ".mp-cap .mp-d", "MoEProgress.css")
    assert re.search(r"\bposition:\s*absolute\s*;", delta), "the delta is still in the flex row"
    assert re.search(r"\bleft:\s*100%\s*;", delta), "the delta is not anchored off the numeral"
    assert re.search(r"\bmargin-left:\s*0\.35em\s*;", delta), \
        "the delta's gap must ride margin-left -- the left:100% anchor is the side Coherent honours"
    assert "right:" not in delta and "margin-right:" not in delta, \
        "margin is DROPPED on a right:100% anchor -- 0/515 in WG's corpus"
    # THE TUNER, BOTH HALVES. MoEProgress.css is a -EmitCss output, so pinning only the stylesheet
    # lets the next re-emit revert the centring silently -- exactly how the delta's size was lost
    # once. And the tuner's own live-preview <style> is the surface the look is approved on, so a
    # preview that still centres the whole row would send the next session back to the old bug.
    tuner = _read_tuner()
    assert tuner.count('".mp-capP .mp-ico { transform: translate(0rem, "+st.icoYP+"rem); '
                       'margin-left: "+') == 1, \
        "gen_bar_tuner.ps1 -EmitCss no longer cancels the TOP caption's icon width"
    assert tuner.count('".mp-capC .mp-ico { transform: translate(0rem, "+st.icoYC+"rem); '
                       'margin-left: "+') == 1, \
        "gen_bar_tuner.ps1 -EmitCss no longer cancels the BOTTOM caption's icon width"
    # TWICE each, once per half: the preview's --dmgpml / --dmgcml custom property and the emitted
    # literal. Both must DERIVE the margin from the same sliders -- a literal in either half means a
    # retune of the icon box or the gap silently de-centres that caption.
    assert tuner.count("(-(st.dmgPBox+st.icoGap))") == 2 and \
        tuner.count("(-(st.dmgCBox+st.icoGap))") == 2, \
        "the negative margins must stay DERIVED from the box + gap sliders in BOTH tuner halves"
    assert tuner.count("margin-left:var(--dmgpml)") == 1 and \
        tuner.count("margin-left:var(--dmgcml)") == 1, \
        "the tuner's live preview no longer cancels the centre captions' icon width"
    assert tuner.count('".mp-cap .mp-d {\\n  position: absolute;\\n  left: 100%;\\n'
                       '  margin-left: 0.35em;\\n"') == 1, \
        "gen_bar_tuner.ps1 -EmitCss no longer hangs the delta out of flow"
    assert tuner.count(".mp-cap .mp-d{position:absolute;left:100%;margin-left:.35em;") == 1, \
        "the tuner's live preview still lays the delta out in the flex row"


def _read_tuner():
    with open(os.path.join(os.path.dirname(__file__), "..", "tools", "dev",
                           "gen_bar_tuner.ps1")) as handle:
        return handle.read()


def test_python_y_offset_cancels_the_js_shift_and_converts_frac_to_viewport():
    # PROGRESS_ANCHOR_Y_OFFSET is TWO summed terms, both owned by the JS:
    #   -SHIFT_Y_REM      cancels the composition's intra-surface downward shift, so the bar stays
    #                     put on screen. THIS is the lockstep the test has always guarded: change
    #                     SHIFT_Y_REM in the JS without changing the Python and the bar moves.
    #   +frac * VIEW_H_REM  UNIT CONVERSION. anchor_centred applies the fraction to the MOVABLE
    #                     EXTENT (space_h - surface_h), so adding frac*surface_h back turns it into
    #                     a fraction of the VIEWPORT, which is how PROGRESS_ANCHOR_Y_FRAC is tuned:
    #                     frac*(H - surface_h) + frac*surface_h == frac*H, at every resolution.
    # Every term is read from the shipped JS -- no literal 34 here -- so a JS-only edit to the
    # shift, the pad, or the measured box still fails this.
    js = _read("MoEProgress.js")
    surface_h = _surface_wh(js)[1]
    assert PROGRESS_ANCHOR_Y_OFFSET == \
        -_shift_y(js) + int(round(PROGRESS_ANCHOR_Y_FRAC * surface_h))


def test_python_large_y_offset_is_the_same_two_terms_scaled_by_size_f():
    # The LARGE twin, derived the SAME two ways from the SAME shipped JS -- only every length is in
    # logical px now, so both terms carry SIZE_F and NEITHER carries SIZE_XF (this is the Y axis).
    # No literal 53 here: a retune of the pad, the box or the fraction propagates, and so does a
    # change to SIZE_F itself. NOT a mirror of the 1x value, and not a mirror of SHIFT_Y_REM either.
    js = _read("MoEProgress.js")
    f = _size_factor("SIZE_F")
    surface_h = Decimal(_surface_wh(js)[1])
    assert PROGRESS_ANCHOR_Y_OFFSET_LARGE == \
        -_large_shift_y(js) + iround_half_away(Decimal(str(PROGRESS_ANCHOR_Y_FRAC))
                                               * surface_h * f)


@pytest.mark.parametrize("space_h", [1080, 1440])
def test_the_composed_placement_puts_the_track_at_the_tuned_viewport_fraction(space_h):
    # THE invariant the offset's second term exists for, and the one nothing caught: the track's
    # top edge must land at PROGRESS_ANCHOR_Y_FRAC of the VIEWPORT height -- resolution-invariant
    # by construction, hence both heights. Composed exactly as progress_view._place does it: the
    # far-sentinel clamp hands anchor_centred the movable extent (logical space - surface), and the
    # track then sits SHIFT_Y_REM below the window's top edge. 1px of slack for anchor_centred's
    # int() floor. Before the fix, 0.85 of the extent alone put the track at 77.7vh.
    #
    # ...AND THE SAME FOR THE LARGE SIZE MODE, which is the whole point of that mode: it is a pure
    # scale-up, so the bar must not MOVE. Everything on the large side is bigger -- the surface, the
    # intra-surface shift, hence the Y compensation -- and the track's top edge has to come out at
    # the SAME fraction of the same viewport, which is asserted directly (`same` below) as well as
    # against the fraction. Slack is 1.5px on the large side: anchor_centred's int() floor loses up
    # to 1 and the offset's own round() up to 0.5 (at 1x those happen to cancel to <= 1).
    js = _read("MoEProgress.js")
    surface_w, surface_h = _surface_wh(js)
    _x, y = anchor_centred(1920 - surface_w, space_h - surface_h, PROGRESS_ANCHOR_Y_FRAC,
                           PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_OFFSET)
    top = y + _shift_y(js)
    assert abs(top - PROGRESS_ANCHOR_Y_FRAC * space_h) <= 1
    lw, lh = _large_surface_wh(js)
    _lx, ly = anchor_centred(1920 - lw, space_h - lh, PROGRESS_ANCHOR_Y_FRAC,
                             PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_OFFSET_LARGE)
    large_top = ly + _large_shift_y(js)
    assert abs(large_top - PROGRESS_ANCHOR_Y_FRAC * space_h) <= 1.5, \
        "the LARGE bar's track lands at %s of the viewport, not %s" % (
            large_top / float(space_h), PROGRESS_ANCHOR_Y_FRAC)
    assert abs(large_top - top) <= 2, \
        "the size mode MOVED the bar: 1x track top %s vs large %s" % (top, large_top)


# --- THE "LARGE" SIZE MODE: the stylesheet's one appended .mp-lg block --------------------------
# mod_settings.progress_bar_size == 1. The mode is delivered by the ROOT FONT SIZE (SIZE_F == 1.5,
# which IS the rem->px factor in Gameface), so it needs NO CSS at all for anything uniform -- height,
# fonts, icon boxes, glow radii, vertical gaps and mp-life's slide all follow the root font. What is
# left is the HORIZONTAL x2: an x-length carries an extra SIZE_XF == 4/3 on top of the root font's
# 1.5, and the appended `.mp-lg` block re-declares X-LENGTHS AND NOTHING ELSE.
#
# THREE separate claims are asserted below, because each fails differently:
#   COMPLETE   every x-length the BASE cascade declares has a `.mp-lg` twin -- and no twin exists
#              for anything else. A missing twin is a bar that renders half-scaled horizontally.
#   CORRECT    each twin's value is its base counterpart times 4/3, re-derived here rather than
#              transcribed -- with the three documented exceptions re-derived their OWN way.
#   CLEAN      no non-x property (a font-size, a height, a keyframe) and no non-rem value (a %, an
#              em, `contain`, a gradient colour) was scaled: scaling any of those DOUBLE-applies
#              SIZE_F, since the root font already covers them.
# Decimal throughout, never float: `4 / 3` is not representable (the implementer hit
# `949.9999999999999` deriving the surface from it) and these are exact-equality comparisons of CSS
# lengths -- the repo lesson `css-em-arithmetic-needs-decimal-not-float-equality`.
_LG = ".mp-lg "


def _x4_3(text):
    """`text` with every rem length multiplied by SIZE_XF, at the stylesheet's own 3dp."""
    xf = _size_factor("SIZE_XF")

    def _one(match):
        scaled = (Decimal(match.group(1)) * xf).quantize(Decimal("0.001"),
                                                         rounding=ROUND_HALF_UP)
        return format(scaled.normalize(), "f") + "rem"

    return re.sub(r"(-?[\d.]+)rem", _one, text)


def _xnum(value):
    """One number times SIZE_XF, as the 3dp Decimal the stylesheet would spell. Goes through
    _x4_3 so the test can never round differently from the values it is checking (and so a
    28-digit Decimal 4/3 cannot leak a `479.99999...` into an equality)."""
    return Decimal(_x4_3("%srem" % value)[:-len("rem")])


# WHICH PROPERTIES CARRY THE X FACTOR, and how much of their value is horizontal. Doubling as the
# CLEAN check: a `.mp-lg` rule declaring anything NOT in here fails, which is what refuses a
# font-size / height / line-height / vertical margin sneaking in.
_X_SCALE = {
    "width": _x4_3, "left": _x4_3, "right": _x4_3,
    "margin-left": _x4_3, "margin-right": _x4_3,
    "padding-left": _x4_3, "padding-right": _x4_3,
    # ONLY the first translate() argument is horizontal -- translateY and the 2nd arg are not, and
    # scaling either would move the glyph vertically (the root font already did that).
    "transform": lambda v: re.sub(r"(translate\(\s*)(-?[\d.]+rem)",
                                  lambda m: m.group(1) + _x4_3(m.group(2)), v),
    # `<x> <y>`: only the x term tiles horizontally; the y term is `100%` and must stay untouched.
    "background-size": lambda v: " ".join([_x4_3(v.split()[0])] + v.split()[1:]),
    # A 90deg repeating gradient -- every stop is a horizontal offset. The colours carry no rem, so
    # _x4_3 leaves them (and the `90deg`) alone, which is itself part of the CLEAN claim.
    "background-image": _x4_3,
}


def _rules(css):
    """[(selector, declarations)] for every flat rule, comments stripped.

    Deliberately NOT anchored on the preceding `}`: consuming it makes the regex skip every OTHER
    rule (it did, first try). `[^{}@;]` keeps `@font-face` / `@keyframes` headers out, and a
    keyframe STOP (`9.68%{...}`) is dropped by the percentage filter."""
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for match in re.finditer(r"([^{}@;]+?)\s*\{([^{}]*)\}", bare):
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


def _cascade(name):
    """({base selector: decls}, {.mp-lg selector: decls}) for one stylesheet."""
    base, large = {}, {}
    for selector, body in _rules(_read(name)):
        (large if selector.startswith(_LG) else base)[selector] = body
    return base, large


def _x_props(body):
    """The properties of one BASE rule that declare a HORIZONTAL rem length.

    The classification is mechanical, not a hand-kept list -- a hand-kept list is how the next
    x-length gets added with no twin and nothing notices:
      * a left/right margin or padding, and `left`/`right` itself, are always x;
      * a `width` in rem is x UNLESS the same rule gives `height` the same value -- that is a
        SQUARE icon box, a uniform length the root font already scales (scaling it would stretch
        the glyph);
      * a translate()'s FIRST argument, when it is a NONZERO rem (0 is invariant under any factor);
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


def _lg_completeness(name):
    """(base selectors that declare an x-length, `.mp-lg` selectors) for one stylesheet."""
    base, large = _cascade(name)
    return ({s for s, body in base.items() if _x_props(body)},
            {s[len(_LG):] for s in large})


def test_the_large_block_twins_exactly_the_base_cascades_x_lengths():
    # COMPLETE, both directions. A base x-length with no twin renders half-scaled horizontally
    # under the large mode; a twin with no base x-length is a rule scaling something the root font
    # already handled (or a selector typo that silently styles nothing).
    want, got = _lg_completeness("MoEProgress.css")
    assert got == want, "missing .mp-lg twins: %s; twins with no base x-length: %s" % (
        sorted(want - got), sorted(got - want))


# The three declarations that are NOT the base times 4/3 -- each mixes in a term that does NOT take
# the x factor, and each is re-derived on its own below.
_RE_DERIVED = {("#moe-bar-box", "width"),
               (".mp-capP .mp-ico", "margin-left"),
               (".mp-capC .mp-ico", "margin-left")}


def test_every_large_declaration_is_its_base_counterpart_times_four_thirds():
    # CORRECT + CLEAN, in one pass: for every twin declaration, re-derive the expected value from
    # the BASE rule (the independent source) and compare. Because the derivation only ever rewrites
    # rem numbers, this equally asserts that no %, em, `contain`, colour, `90deg` or
    # background-size y-ratio was scaled, and the _X_SCALE lookup refuses any property that is not
    # an x-length at all.
    base, large = _cascade("MoEProgress.css")
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
            if (bare, prop) in _RE_DERIVED:
                continue
            assert value == _X_SCALE[prop](base_decls[prop]), \
                "%s { %s: %s } is not the base `%s` times 4/3" % (selector, prop, value,
                                                                  base_decls[prop])
            checked += 1
    assert checked == 9, "expected 9 straight x4/3 declarations, checked %d" % checked


def test_the_large_block_carries_no_keyframe_and_no_vertical_length():
    # The CLEAN claim's other half, on the raw text: _X_SCALE above refuses a vertical PROPERTY, but
    # a `@keyframes` (mp-life's 20rem slide is a y length, and its identity is what the twin blocks
    # exist for) would not be a rule at all and would slip past the walk entirely.
    block = _read("MoEProgress.css").split('THE "LARGE" SIZE MODE')[-1]
    assert "@keyframes" not in block and "%{" not in block, \
        "the .mp-lg block grew a keyframe -- the root font already scales mp-life's slide"


def test_the_large_sizing_box_is_the_scaled_surface_not_the_scaled_box():
    # RE-DERIVED EXCEPTION 1. #moe-bar-box is the static sizing shim and it mirrors the SURFACE
    # (BOX_W_REM + 2*PAD_REM at 1x -- the test at the top of this file pins that). PAD_REM is slack
    # on both axes and does NOT take the x factor, so the large twin is BOX_W_REM*4/3 + 2*PAD_REM
    # (500), never the base width times 4/3 (506.667). Height is deliberately absent from the twin:
    # 92rem at a 1.5x root font already IS the 138 logical px the JS pushes.
    js = _read("MoEProgress.js")
    _base, large = _cascade("MoEProgress.css")
    want = _xnum(_js_const(js, "BOX_W_REM")) + 2 * _js_const(js, "PAD_REM")
    assert _rem(large[_LG + "#moe-bar-box"], "width", "MoEProgress.css") == want
    assert "height" not in dict(_decls(large[_LG + "#moe-bar-box"])), \
        "the large sizing box must not restate a height -- the root font scales the base 92rem"


def test_the_large_centre_caption_icon_cancels_scale_only_their_gap():
    # RE-DERIVED EXCEPTION 2 + 3, and the sharpest thing in this section. The centre captions'
    # negative margin cancels -(this caption's own icon BOX + the gap) so translateX(-50%) halves
    # the digits, not icon+numeral (see the 1x centring test above). The icon box is a SQUARE,
    # uniform length the root font scales on its own -- only the GAP is an x-length. So the large
    # margins are -(14 + 1.333) and -(16 + 1.333), NOT -15*4/3 / -17*4/3; multiply them and the
    # numeral stops sitting on its tick. Re-derived from the same three base rules the 1x test uses,
    # so a genuine retune of the box or the gap moves all of them together and still passes.
    css = _read("MoEProgress.css")
    _base, large = _cascade("MoEProgress.css")
    gap = _rem(_sole_rule_decls(css, ".mp-cap .mp-ico", "MoEProgress.css"), "margin-right",
               "MoEProgress.css")
    large_gap = _xnum(gap)
    for cap, glyph in ((".mp-capP", ".mp-ico.dmgp"), (".mp-capC", ".mp-ico.dmgc")):
        box = _rem(_sole_rule_decls(css, glyph, "MoEProgress.css"), "width", "MoEProgress.css")
        got = _rem(large[_LG + cap + " .mp-ico"], "margin-left", "MoEProgress.css")
        assert got == -(box + large_gap), (
            "%s's large icon margin is %s -- it must cancel its UNSCALED %srem box plus the "
            "SCALED %srem gap" % (cap, got, box, large_gap))


def test_the_large_backdrop_stays_symmetric_about_the_track():
    # LOAD-BEARING, and silent when it breaks: there is NO X compensation term in Python, so
    # anchor_centred's `max_x // 2` only centres the bar because the backdrop brackets the track
    # with EQUAL bleed each side. Break the symmetry under the large mode and X drifts by half the
    # error at every resolution, with every other assertion still green.
    # Tolerance is 0.002rem, not exact: each of the three values is independently rounded to the
    # stylesheet's 3dp (bleed twice over), so the sum cannot close exactly. It is ~5 orders of
    # magnitude below the smallest real error (a dropped x factor moves the bleed by 26.667rem).
    _base, large = _cascade("MoEProgress.css")
    bleed = -_rem(large[_LG + ".mp-backdrop"], "left", "MoEProgress.css")
    width = _rem(large[_LG + ".mp-backdrop"], "width", "MoEProgress.css")
    track = _rem(large[_LG + "#moe-bar-root"], "width", "MoEProgress.css")
    assert bleed > 0, "the backdrop must start LEFT of the track, not inside it"
    assert abs(width - (track + 2 * bleed)) <= Decimal("0.002"), (
        "the large backdrop is %srem around a %srem track with %srem of left bleed -- "
        "asymmetric, so `max_x // 2` no longer centres the bar" % (width, track, bleed))


def test_the_large_size_block_cannot_be_silently_lost_to_a_tuner_re_emit():
    # MoEProgress.css is a `gen_bar_tuner.ps1 -EmitCss` output, and a re-emit OVERWRITES THE WHOLE
    # FILE -- the repo lesson `emitcss-is-not-the-whole-shipped-stylesheet` (this file already
    # carries two other hand-added regions lost that way, each worth a client relaunch). The sibling
    # MoEEfficiency.css re-splices its three blocks BY CONSTRUCTION (tools/dev/emit_eff_css.js);
    # the tuner has no such path, so this is the guard that stands in for it, in both halves:
    #   * the block is present, MARKED at both ends, and every .mp-lg rule lives inside those
    #     markers (a twin outside them is a twin the next re-emit takes with it);
    #   * the tuner still does NOT emit `.mp-lg` -- pinning the KNOWN GAP, so the day someone
    #     teaches -EmitCss the size mode this fails and says to move the guard there.
    css = _read("MoEProgress.css")
    head = '/* ===== APPENDED HAND-ADDED BLOCK -- THE "LARGE" SIZE MODE'
    tail = "/* ===== END APPENDED HAND-ADDED BLOCK ===== */"
    assert css.count(head) == 1 and css.count(tail) == 1, "the .mp-lg block lost its markers"
    inside = css[css.index(head):css.index(tail)]
    assert css.count(_LG) == inside.count(_LG) > 0, \
        "a .mp-lg rule sits OUTSIDE the marked block -- a re-emit would drop it silently"
    assert ".mp-lg" not in _read_tuner(), \
        "gen_bar_tuner.ps1 now emits the size mode -- move this guard onto its emit, the way the " \
        "delta size/nudge pins are asserted in BOTH the tuner and the stylesheet"
