# -*- coding: utf-8 -*-
"""Every in-battle bar caption PINS its line box, and the pin is the FACTOR-2 value.

THE BUG. `line-height: normal` makes a line box the font's ascent+descent+gap SNAPPED UP TO WHOLE
DEVICE PIXELS. In rem that is NOT a constant: it shrinks as the rem->px factor grows. Measured live
(the six rows in `_MEASURED_BOX_PX` below):

      factor   .mp-cap 16rem font -> box            .mp-cap .mp-d 12rem font -> box
        1      16px -> 21px == 21.000rem            12px -> 16px == 16.000rem
        2      32px -> 41px == 20.500rem            24px -> 31px == 15.500rem
       24     384px -> 483px == 20.125rem          288px -> 362px == 15.083rem

Both bars place a glyph off that box -- MoEProgress's `.mp-ico` is a flex item under
`align-items: center`, MoEEfficiency's is `top: 50%` of the caption's padding box -- so HALF the
variation goes straight into the icon's Y. Reported at 3440x1440 (factor 1) as the current-damage
icon and delta sitting low; the maintainer's own render is factor 2 and is correct.

THE FIX is to pin each caption's line-height to a rem LENGTH, which makes the box linear in the
factor. THE PIN VALUE IS THE FACTOR-2 BOX, not the font's true unsnapped ratio: factor 2 is the
render the composition was approved on and must not move by even one device pixel (a `1.2565em`
line-height computes to 40.2px there, 0.75px off).

WHAT THIS FILE ASSERTS, and why each part exists separately:
  THE RATIO      `ceil(font_px * R)` reproduces all six MEASUREMENTS, with R read OUT OF THE TUNERS
                 rather than restated here -- so the generators' constant is the one under test.
  THE PINS       every pinned value is RE-DERIVED from the element's own declared font-size. A
                 derived emitted value with no independent copy is untested: `#moe-bar-box`'s height
                 drifted 51 -> 55 with this suite green (the repo lesson
                 `derived-emitted-value-with-no-meta-copy-is-untested`).
  THE NO-OP      pin_rem * 2 == the MEASURED factor-2 box in px, for every element whose font-size
                 was actually measured. This is the maintainer's hard constraint, and it is checked
                 against the measurement table, not against the formula that produced the pin.
  COMPLETENESS   every rule in either stylesheet that declares a rem font-size ALSO declares a pin,
                 and no rule pins without owning a font-size. Mechanical, so a caption added later
                 cannot ship unpinned.
  NO TWIN        no `.mp-lg` rule declares a line-height in either stylesheet. line-height is a
                 uniform (vertical) length: the root font (SIZE_F) already scales it, and a
                 size-mode twin would DOUBLE-apply it.
  LOCKSTEP       both halves of both generators. Each stylesheet's base cascade IS its tuner's emit
                 (byte-for-byte for MoEEfficiency.css, hand-spliced for MoEProgress.css), so a pin
                 that lives only in the stylesheet is one `-EmitCss` / `emit_eff_css.js` away from
                 being reverted -- and the live-preview half is the surface the look gets approved
                 on, so a preview without the pin sends the next tuning session back to the bug.

Decimal everywhere, never float: these are exact-equality comparisons of CSS lengths, and IEEE754
has already produced a false "these differ" on byte-identical declarations in this repo
(`css-em-arithmetic-needs-decimal-not-float-equality`).
"""
import os
import re
from decimal import Decimal, ROUND_CEILING
from fractions import Fraction

import pytest

_WIDGET = os.path.join(os.path.dirname(__file__), "..", "src", "res", "gui", "gameface", "mods",
                       "14th_ua", "MoECalculator")
_DEV = os.path.join(os.path.dirname(__file__), "..", "tools", "dev")

# The two in-battle bars, each with the generator whose emit its base cascade is.
_BARS = (("MoEProgress.css", "gen_bar_tuner.ps1"), ("MoEEfficiency.css", "eff_bar_tuner.html"))

# THE MEASUREMENT, and the only independent oracle in this file: {(font px, factor): line box px},
# taken live off the running client at three rem->px factors for the two caption font sizes that
# exist at 1x. Everything else here is derived; these six numbers are not.
_MEASURED_BOX_PX = {
    (16, 1): 21, (32, 2): 41, (384, 24): 483,      # a 16rem caption
    (12, 1): 16, (24, 2): 31, (288, 24): 362,      # the 12rem delta
}
# The corridor the brief quotes for R. NOT used as the test's bound -- `_corridor()` derives the
# exact one from the six measurements and this pair is checked to be a safe INWARD rounding of it.
_QUOTED_CORRIDOR = (Decimal("1.25521"), Decimal("1.25694"))


def _corridor():
    """The EXACT (open, closed] interval the six measurements confine R to, as Fractions.

    `ceil(f * R) == b` is `(b - 1) / f < R <= b / f`, so the corridor is the tightest such pair over
    every measured row. Fractions, not Decimals: 482/384 has no finite decimal form, and this
    interval is what the boundary probe below steps across."""
    lo = max(Fraction(box - 1, font) for (font, _f), box in _MEASURED_BOX_PX.items())
    hi = min(Fraction(box, font) for (font, _f), box in _MEASURED_BOX_PX.items())
    assert lo < hi, "the measurements are mutually inconsistent -- no single ratio fits them"
    return lo, hi


def _read(directory, name):
    with open(os.path.join(directory, name)) as handle:
        return handle.read()


def _ratio(generator):
    """The line ratio R out of one generator's `lh()` helper -- the pin's ONLY constant.

    Read rather than restated so that a drift in either generator fails the measurement check
    below instead of being silently blessed by a second copy living in this file."""
    src = _read(_DEV, generator)
    match = re.search(r"function lh\(fs\)\{return Math\.ceil\(fs\*2\*([\d.]+)\)/2;\}", src)
    assert match, "%s: no `function lh(fs){return Math.ceil(fs*2*<R>)/2;}` helper" % generator
    return Decimal(match.group(1))


def _pin(font_rem, ratio):
    """The pinned line-height for a font-size, in rem: ceil(font_rem * 2 * R) / 2.

    i.e. the box the font would snap to at rem->px factor 2, expressed back in rem. Halves are
    exact in rem, so this is always spellable as a plain decimal."""
    doubled = (font_rem * 2 * ratio).to_integral_value(rounding=ROUND_CEILING)
    return doubled / 2


def _rules(css):
    """[(selector, {property: value})] for every flat rule, COMMENTS STRIPPED.

    Both stylesheets' prose quotes the very numbers asserted here (one of them now spells out the
    whole measurement table), so an unstripped search is satisfied by a comment -- the repo lesson
    `unscoped-substring-assertion-is-not-an-assertion`. `[^{}@;]` keeps @font-face / @keyframes
    headers out and the percentage filter drops keyframe stops."""
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out = []
    for match in re.finditer(r"([^{}@;]+?)\s*\{([^{}]*)\}", bare):
        selector = " ".join(match.group(1).split())
        if re.match(r"^[\d.]+%$", selector):
            continue
        decls = {}
        for chunk in match.group(2).split(";"):
            prop, sep, value = chunk.partition(":")
            if sep:
                decls[prop.strip()] = " ".join(value.split())
        out.append((selector, decls))
    return out


def _rem(value):
    match = re.match(r"^(-?[\d.]+)rem$", value or "")
    return Decimal(match.group(1)) if match else None


def _pinned(name):
    """{selector: (font-size rem, line-height rem or None)} for the rules that own a rem font-size.

    THE ENUMERATION IS MECHANICAL, off the stylesheet itself, and that is the point: a hand-kept
    list of caption selectors is how the next caption ships unpinned. In both files this comes out
    as the caption variants (.up / .dn / .side, hence the .rN threshold stops and the two centre
    captions that qualify them) plus `.mp-cap .mp-d`; nothing else in either bar sets a font-size."""
    return {selector: (_rem(decls["font-size"]), _rem(decls.get("line-height")))
            for selector, decls in _rules(_read(_WIDGET, name))
            if _rem(decls.get("font-size")) is not None}


def test_the_line_ratio_reproduces_every_measured_line_box():
    # R is the whole fix's one empirical constant, and it is read out of the generators. All six
    # measured boxes must come back exactly, at every factor -- a ratio that fits only the factor-2
    # rows would pin the same values while being wrong about WHY, and the next font change would
    # then move the approved render.
    lo, hi = _corridor()
    for _css_name, generator in _BARS:
        ratio = _ratio(generator)
        assert lo < Fraction(ratio) <= hi, \
            "%s's line ratio %s is outside the corridor the measurements allow (%s, %s]" % (
                generator, ratio, float(lo), float(hi))
        for (font_px, factor), box_px in sorted(_MEASURED_BOX_PX.items()):
            got = (Decimal(font_px) * ratio).to_integral_value(rounding=ROUND_CEILING)
            assert got == box_px, \
                "%s: ceil(%dpx * %s) == %s, but the live box at factor %d measured %dpx" % (
                    generator, font_px, ratio, got, factor, box_px)


def test_the_corridor_is_tight_and_the_quoted_one_is_a_safe_rounding():
    # HALF A BOUNDARY PROBE, and the thing that makes the corridor an assertion rather than prose:
    # a ratio one step OUTSIDE the derived interval must fail some measurement, at BOTH ends. The
    # low end is the 384px row and the high end the 288px row -- if either stopped binding, the
    # corridor would be wider than claimed and the ratio less determined than the fix assumes.
    lo, hi = _corridor()
    eps = Fraction(1, 10 ** 9)
    for edge in (lo, hi + eps):
        broken = [row for row, box in _MEASURED_BOX_PX.items()
                  if -((-row[0] * edge) // 1) != box]      # ceil(font * edge), exactly
        assert broken, "a ratio of %s outside the corridor still reproduces every measurement" % (
            float(edge),)
    # ...and the corridor the brief quotes is INSIDE the derived one, i.e. rounded the safe way. A
    # quoted bound that fell outside would advertise a ratio the measurements actually refuse.
    quoted_lo, quoted_hi = _QUOTED_CORRIDOR
    assert lo < Fraction(quoted_lo) and Fraction(quoted_hi) <= hi, \
        "the quoted corridor (%s, %s] is not inside the derived (%s, %s]" % (
            quoted_lo, quoted_hi, float(lo), float(hi))


def test_both_generators_agree_on_the_ratio():
    # Two tuners, one physical font (MoEBattle.ttf is shared). A per-file constant is how the two
    # bars' captions would end up pinned to different boxes for the same font-size.
    ratios = {generator: _ratio(generator) for _css, generator in _BARS}
    assert len(set(ratios.values())) == 1, "the tuners disagree on the line ratio: %s" % ratios


@pytest.mark.parametrize("css_name,generator", _BARS)
def test_every_caption_pins_its_line_box_at_the_derived_value(css_name, generator):
    # THE PINS, re-derived from each rule's OWN declared font-size (read out of the rule that owns
    # it, comments stripped). A genuine size retune moves the font and the pin together and still
    # passes; drift in either alone fails.
    ratio = _ratio(generator)
    pinned = _pinned(css_name)
    assert pinned, "%s: no rule declares a rem font-size -- the enumeration has broken" % css_name
    for selector, (font_rem, line_rem) in sorted(pinned.items()):
        assert line_rem is not None, (
            "%s { %s } sets font-size: %srem with no line-height -- `normal` makes its box shrink "
            "as the rem->px factor grows and half of that lands in the icon's Y" % (
                css_name, selector, font_rem))
        assert line_rem == _pin(font_rem, ratio), (
            "%s { %s } pins line-height: %srem, but ceil(%s * 2 * %s) / 2 == %s" % (
                css_name, selector, line_rem, font_rem, ratio, _pin(font_rem, ratio)))


@pytest.mark.parametrize("css_name,generator", _BARS)
def test_the_pins_are_a_no_op_at_factor_two(css_name, generator):
    # THE MAINTAINER'S HARD CONSTRAINT, checked against the MEASUREMENT and not against the formula:
    # at rem->px factor 2 the pinned box must be the exact px count `normal` already produced, so
    # the approved render cannot move by a single device pixel. 1rem == 1 logical px, so the pin's
    # px value at factor 2 is simply pin_rem * 2.
    measured = {font_px // 2: box_px for (font_px, factor), box_px in _MEASURED_BOX_PX.items()
                if factor == 2}
    checked = 0
    for selector, (font_rem, line_rem) in sorted(_pinned(css_name).items()):
        if font_rem not in map(Decimal, measured):
            continue
        want = measured[int(font_rem)]
        assert line_rem * 2 == want, (
            "%s { %s }: the pin renders %spx at factor 2, but `normal` measured %dpx there -- this "
            "MOVES the render the maintainer approved" % (css_name, selector, line_rem * 2, want))
        checked += 1
    assert checked, "%s: no pinned caption has a MEASURED font-size" % css_name


def test_the_only_unmeasured_pins_are_the_two_14rem_progress_captions():
    # HONESTY GATE, and the residual-risk register. Only the 16rem and 12rem boxes were measured
    # live; every other pin rests on the formula alone. Naming the exact set here means a new
    # unmeasured font-size cannot slip in unlisted -- the test fails and says which one to measure.
    unmeasured = {(css_name, selector, font)
                  for css_name, _gen in _BARS
                  for selector, (font, _lh) in _pinned(css_name).items()
                  if int(font) not in {16, 12}}
    assert unmeasured == {("MoEProgress.css", ".mp-cap.up", Decimal("14")),
                          ("MoEProgress.css", ".mp-cap.side", Decimal("14"))}, \
        "the set of pins with NO live measurement changed: %s" % sorted(unmeasured)


@pytest.mark.parametrize("css_name,generator", _BARS)
def test_no_rule_pins_a_line_box_it_does_not_own(css_name, generator):
    # line-height inherits as a computed LENGTH, so a pin on a rule that sets no font-size lands on
    # descendants at whatever size they happen to be -- exactly the coupling the pin exists to
    # remove. (.mp-v / .mp-d-num correctly carry NO pin of their own: they inherit their caption's.)
    for selector, decls in _rules(_read(_WIDGET, css_name)):
        if "line-height" in decls:
            assert _rem(decls.get("font-size")) is not None, \
                "%s { %s } pins a line box without declaring the font-size it belongs to" % (
                    css_name, selector)


@pytest.mark.parametrize("css_name,generator", _BARS)
def test_the_size_mode_declares_no_line_height_twin(css_name, generator):
    # line-height is a UNIFORM length: the LARGE mode is delivered by the root font (SIZE_F), which
    # scales it for free. A `.mp-lg` twin would double-apply that and break Large mode -- and it
    # would be invisible at 1x. Asserted here as well as by each bar's large-mode cascade walk,
    # because those walks classify by property and this is the one property whose absence matters.
    for selector, decls in _rules(_read(_WIDGET, css_name)):
        if selector.startswith(".mp-lg"):
            assert "line-height" not in decls, \
                "%s { %s } twins a line-height -- the root font already scales it" % (css_name,
                                                                                     selector)


def test_the_progress_tuner_carries_the_pins_in_both_halves():
    # MoEProgress.css is a `-EmitCss` output spliced by hand, so a stylesheet-only pin is one
    # re-emit from being reverted; and the live-preview <style> is the surface the look is approved
    # on. Both halves must DERIVE from the same font-size knob the emitted font-size comes from --
    # a literal in either would leave the box behind the next size retune, which IS this bug.
    tuner = _read(_DEV, "gen_bar_tuner.ps1")
    for knob, var in (("reqFS", "--reqlh"), ("curFS", "--curlh"), ("endFS", "--endlh")):
        assert tuner.count('line-height: "+lh(st.%s)+"rem' % knob) == 1, \
            "gen_bar_tuner.ps1 -EmitCss no longer derives the %s caption's pin from st.%s" % (knob,
                                                                                              knob)
        assert tuner.count('S.setProperty("%s",rem(lh(st.%s)))' % (var, knob)) == 1, \
            "the tuner's live preview no longer writes %s from lh(st.%s)" % (var, knob)
        assert tuner.count("line-height:var(%s)" % var) == 1, \
            "the tuner's live preview no longer previews %s's pinned box" % knob
    # The delta's font-size is a LITERAL in both halves (no knob owns it), so its pin is one too --
    # built here from the shipped stylesheet's own declared size rather than transcribed.
    font, line = _pinned("MoEProgress.css")[".mp-cap .mp-d"]
    assert line == _pin(font, _ratio("gen_bar_tuner.ps1"))
    spelled = format(line.normalize(), "f")
    assert tuner.count("line-height: %srem;\\n" % spelled) == 1, \
        "gen_bar_tuner.ps1 -EmitCss no longer emits the delta's pinned box -- a re-emit reverts it"
    assert tuner.count("line-height:%srem;" % spelled) == 1, \
        "the tuner's LIVE PREVIEW no longer previews the delta's pinned box"


def test_the_efficiency_tuner_carries_the_pins_in_both_halves():
    # Same contract on the sibling. This stylesheet's base half is the tuner's emit BYTE-FOR-BYTE
    # (emit_eff_css.js re-assembles it, check_eff_css.js gates the drift), so the emit half is the
    # only place the value can live -- and all three of this bar's sizes are knobs.
    tuner = _read(_DEV, "eff_bar_tuner.html")
    for knob, var in (("reqFS", "--reqlh"), ("curFS", "--curlh"), ("dFS", "--dlh")):
        assert tuner.count('line-height: "+lh(st.%s)+"rem' % knob) == 1, \
            "eff_bar_tuner.html's cssOut() no longer derives the %s pin from st.%s" % (knob, knob)
        assert tuner.count('S.setProperty("%s",rem(lh(st.%s)))' % (var, knob)) == 1, \
            "the tuner's live preview no longer writes %s from lh(st.%s)" % (var, knob)
        assert tuner.count("line-height:var(%s)" % var) == 1, \
            "the tuner's live preview no longer previews %s's pinned box" % knob
