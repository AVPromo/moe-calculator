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
from decimal import Decimal

import pytest

from moe_calculator.domain.constants import (
    PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_FRAC, PROGRESS_ANCHOR_Y_OFFSET)
from moe_calculator.domain.positioning import anchor_centred

_WIDGET = os.path.join(os.path.dirname(__file__), "..", "src", "res", "gui", "gameface", "mods",
                       "14th_ua", "MoECalculator")


def _read(name):
    with open(os.path.join(_WIDGET, name)) as handle:
        return handle.read()


def _js_const(src, name):
    match = re.search(r"^const %s = (-?\d+);" % name, src, re.M)
    assert match, "MoEProgress.js: const %s not found" % name
    return int(match.group(1))


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


@pytest.mark.parametrize("space_h", [1080, 1440])
def test_the_composed_placement_puts_the_track_at_the_tuned_viewport_fraction(space_h):
    # THE invariant the offset's second term exists for, and the one nothing caught: the track's
    # top edge must land at PROGRESS_ANCHOR_Y_FRAC of the VIEWPORT height -- resolution-invariant
    # by construction, hence both heights. Composed exactly as progress_view._place does it: the
    # far-sentinel clamp hands anchor_centred the movable extent (logical space - surface), and the
    # track then sits SHIFT_Y_REM below the window's top edge. 1px of slack for anchor_centred's
    # int() floor. Before the fix, 0.85 of the extent alone put the track at 77.7vh.
    js = _read("MoEProgress.js")
    surface_w, surface_h = _surface_wh(js)
    _x, y = anchor_centred(1920 - surface_w, space_h - surface_h, PROGRESS_ANCHOR_Y_FRAC,
                           PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_OFFSET)
    assert abs((y + _shift_y(js)) - PROGRESS_ANCHOR_Y_FRAC * space_h) <= 1
