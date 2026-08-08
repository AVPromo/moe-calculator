# -*- coding: utf-8 -*-
"""Static guards on the progress bar's DUPLICATED values (surface size, twin keyframes).

The window has no hot-reload, so a drift between two copies of the same value costs a full client
relaunch to notice. Everything here is a text-level assertion on the shipped files; the module's
BEHAVIOUR is checked by tools/dev/check_progress_js.js instead.

THE SURFACE SIZE is written down THREE times.

MoEProgress.js's VIEW_W_REM / VIEW_H_REM (derived from the composition's measured box + PAD_REM)
are the source of truth. They are also spelled out as literals in MoEProgress.css's #moe-bar-box
(the static sizing shim that makes the document measurable, so the engine's 256x256 default-size
fallback never fires -- see MoEProgressView.html), and BOX_H_REM feeds
domain/constants.PROGRESS_ANCHOR_Y_SHIFT: it cancels the JS's SHIFT_Y_REM, which is the composition's
whole intra-surface shift and now the WHOLE constant -- the extent-to-viewport fraction conversion
the old two-term PROGRESS_ANCHOR_Y_OFFSET composite also carried is computed by
positioning.anchor_centred_reduced instead (see its docstring), so no surface-height term is baked
here at all any more.

The battle window has no hot-reload, so a drift between the three costs a client relaunch to
notice: assert the actual EMITTED VALUES here rather than trusting the comments.
"""
import os
import re
from decimal import Decimal, ROUND_HALF_UP

import pytest

from moe_calculator.domain.constants import (
    PROGRESS_ANCHOR_X_OFFSET, PROGRESS_ANCHOR_Y_FRAC, PROGRESS_ANCHOR_Y_SHIFT,
    PROGRESS_ANCHOR_Y_SHIFT_LARGE, VERTICAL_ANCHOR_Y_SHIFT, VERTICAL_ANCHOR_Y_SHIFT_LARGE)
from moe_calculator.domain.positioning import anchor_centred_reduced, anchor_offset
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


def _css_rect(src, selector):
    """left/top/width/height (all whole rem) out of ONE CSS rule -- the vertical composition's
    own bounding box, .mpv-backdrop, mirroring what .mp-backdrop is for the horizontal one."""
    body = _css_rule(src, selector)
    def _prop(name):
        match = re.search(r"%s:\s*(-?\d+)rem;" % name, body)
        assert match, "MoEProgressVertical.css: %s has no %s" % (selector, name)
        return int(match.group(1))
    return _prop("left"), _prop("top"), _prop("width"), _prop("height")


def _v_surface_wh(js):
    """The vertical surface the JS pushes to the engine -- V_BOX_W_REM + 2*V_PAD_X_REM on the
    width (MoEBarTransient's `viewW = cfg.boxW + 2 * cfg.padX;`), V_BOX_H_REM + 2*PAD_REM -
    V_CLIP_B_REM on the height (`viewH = cfg.boxH + 2 * cfg.pad - cfg.clipB;`). NEITHER axis is the
    uniform PAD_REM, and each departure is its own deliberate thing: the height CLIPS the backdrop's
    own bottom bleed (V_CLIP_B_REM) and the width reaches far PAST the backdrop on both sides to
    cover the right-anchored captions' leftward ink (V_PAD_X_REM). Both carry their derivation in
    the JS's own notes."""
    pad = _js_const(js, "PAD_REM")
    return (_js_const(js, "V_BOX_W_REM") + 2 * _js_const(js, "V_PAD_X_REM"),
            _js_const(js, "V_BOX_H_REM") + 2 * pad - _js_const(js, "V_CLIP_B_REM"))


def _v_shift_x(js):
    """MoEProgress.js's vertical SHIFT_X_REM (goVertical's `cfg.padX - cfg.boxLeft`) -- how far
    RIGHT the composition sits inside its own surface, i.e. how much room the captions have to grow
    leftward into before the surface clips them."""
    return _js_const(js, "V_PAD_X_REM") - _js_const(js, "V_BOX_LEFT_REM")


def _v_shift_y(js):
    """MoEProgress.js's vertical SHIFT_Y_REM (goVertical's `cfg.pad - cfg.boxTop`, fed from
    V_BOX_TOP_REM) -- mirrored (negated) in Python as VERTICAL_ANCHOR_Y_SHIFT."""
    return _js_const(js, "PAD_REM") - _js_const(js, "V_BOX_TOP_REM")


def test_the_vertical_box_consts_quote_the_backdrop_rule():
    # V_BOX_* is .mpv-backdrop -- the vertical composition's own bounding box, axis-swapped from
    # .mp-backdrop/BOX_* above (memory `emitted-css-gate-needs-absence-assertions`'s sibling
    # concern: a JS-side literal with no CSS-side cross-check can drift silently). Mirrors
    # test_css_sizing_box_matches_the_js_surface's contract under the vertical prefix.
    css, js = _read("MoEProgressVertical.css"), _read("MoEProgress.js")
    assert (_js_const(js, "V_BOX_LEFT_REM"), _js_const(js, "V_BOX_TOP_REM"),
            _js_const(js, "V_BOX_W_REM"), _js_const(js, "V_BOX_H_REM")) == \
        _css_rect(css, ".mpv-backdrop")
    assert (_js_const(js, "V_BOX_LEFT_REM"), _js_const(js, "V_BOX_TOP_REM"),
            _js_const(js, "V_BOX_W_REM"), _js_const(js, "V_BOX_H_REM")) == (-34, -80, 72, 360)


def test_the_vertical_clip_is_fed_from_its_own_constant():
    # `viewH`'s `- cfg.clipB` term (MoEBarTransient.js) is only meaningful if the vertical config
    # actually hands it V_CLIP_B_REM by name -- a literal or a copy of the wrong bar's constant
    # would still satisfy every OTHER derivation test while the clip silently drifted.
    js = _read("MoEProgress.js")
    assert re.search(r"clipB:\s*V_CLIP_B_REM\s*[,}]", js), \
        "MoEProgress.js: vert config's clipB is not fed from V_CLIP_B_REM"
    assert _js_const(js, "V_CLIP_B_REM") == 60


def test_the_vertical_css_sizing_box_matches_the_js_surface():
    # body.mpv #moe-bar-box mirrors the surface _v_surface_wh derives, exactly as the horizontal
    # #moe-bar-box mirrors BOX_W/H_REM + 2*PAD_REM in test_css_sizing_box_matches_the_js_surface.
    # The width is NOT box + 2*PAD_REM any more: V_PAD_X_REM widens BOTH sides so the surface covers
    # the right-anchored captions' leftward ink (the backdrop deliberately does not -- see
    # test_the_vertical_captions_fit_inside_the_surface, the gate on the value itself) while staying
    # concentric with the track (test_the_wider_vertical_surface_does_not_move_the_centred_track).
    css = _read("MoEProgressVertical.css")
    match = re.search(r"body\.mpv #moe-bar-box\s*\{\s*width:\s*(\d+)rem;\s*height:\s*(\d+)rem;\s*\}",
                       css)
    assert match, "MoEProgressVertical.css: body.mpv #moe-bar-box rule not found"
    box = (int(match.group(1)), int(match.group(2)))
    assert box == _v_surface_wh(_read("MoEProgress.js")) == (198, 320)


def test_the_vertical_shift_is_the_pure_intra_surface_term_and_shared_by_both_bars():
    # VERTICAL_ANCHOR_Y_SHIFT is ONE constant for BOTH bars (unlike the horizontal 44-vs-50
    # split): both vertical compositions share the same backdrop geometry (top: -80rem,
    # height: 360rem) and the same PAD_REM == 10, so this bar's own derivation already pins the
    # shared value -- the efficiency mirror file re-derives it independently off ITS OWN JS, and
    # the two must agree (see that file's copy of this test).
    js = _read("MoEProgress.js")
    assert VERTICAL_ANCHOR_Y_SHIFT == -_v_shift_y(js) == -90


def test_the_vertical_large_shift_is_the_same_pure_term_scaled_by_size_f():
    # The LARGE twin -- half-away rounding, the same convention every other *_SHIFT_LARGE uses
    # (-112.5 -> -113).
    js = _read("MoEProgress.js")
    assert VERTICAL_ANCHOR_Y_SHIFT_LARGE == \
        -iround_half_away(Decimal(_v_shift_y(js)) * _size_factor("SIZE_F")) == -113


def test_the_vertical_large_box_reproduces_the_pinned_logical_surface():
    # body.mpv.mp-lg #moe-bar-box restates ONLY the width, in DOCUMENT REM, at V_BOX_W_REM*SIZE_XF +
    # 2*V_PAD_X_REM (the root font's SIZE_F is layered on top of every rem for free, including this
    # one and the unrestated height) -- so the LOGICAL PX surface under Large is this rem value times
    # SIZE_F for width, and the default height times SIZE_F alone. DO NOT write the logical-px number
    # into the shim: 222 * 1.25 == 277.5 -> 278, and a 278rem shim would push a 347px surface.
    # ONLY THE BACKDROP HALF TAKES SIZE_XF. The pad is rem-space slack for rem-sized ink (the caption
    # glyphs and the shadow bleed), which the root font already grows by SIZE_F -- giving it the x
    # factor too would over-pad by 25%, the same rule PAD_REM has always followed.
    # Pinned: progress vertical Large -> 278 x 400.
    css, js = _read("MoEProgressVertical.css"), _read("MoEProgress.js")
    match = re.search(r"body\.mpv\.mp-lg #moe-bar-box\s*\{\s*width:\s*(\d+)rem;\s*\}", css)
    assert match, "MoEProgressVertical.css: body.mpv.mp-lg #moe-bar-box rule not found"
    large_w_rem = int(match.group(1))
    xf, f = _size_factor("SIZE_XF"), _size_factor("SIZE_F")
    pad = _js_const(js, "PAD_REM")
    assert large_w_rem == (_js_const(js, "V_BOX_W_REM") * xf
                           + 2 * _js_const(js, "V_PAD_X_REM"))
    _, default_h = _v_surface_wh(js)
    assert (iround_half_away(Decimal(large_w_rem) * f),
            iround_half_away(Decimal(default_h) * f)) == (278, 400)


def _advances(js):
    """MoEBattle.ttf's per-glyph advances in em, scraped from MoEProgress.js's OWN hmtx note.

    Scraped, not transcribed, so the file that DERIVES its horizontal extremes from these four and
    the test that derives the vertical ones can never disagree about the font. Anchored on the
    horizontal header's `plus` spelling, which occurs exactly once."""
    match = re.search(r"digit ([\d.]+)em, comma ([\d.]+), paren ([\d.]+),\s*\n?//\s*plus ([\d.]+)",
                      js)
    assert match, "MoEProgress.js: the MoEBattle.ttf advance note is gone or reworded"
    return dict(zip(("digit", "comma", "paren", "sign"),
                    (Decimal(g) for g in match.groups())))


def _ink(adv, size, digits=0, commas=0, parens=0, signs=0):
    """One numeral's rendered width in rem, at `size` rem and letter-spacing 0."""
    return size * (digits * adv["digit"] + commas * adv["comma"]
                   + parens * adv["paren"] + signs * adv["sign"])


def test_the_vertical_captions_fit_inside_the_surface():
    """Every vertical caption row's worst-case LEFTWARD ink must fit inside V_SHIFT_X_REM.

    THE GAP THIS CLOSES, and the reason the bug shipped: there was NO X-axis fit check on either
    vertical bar. The tuner's own checkCaptionInvariance() proves the caption ANCHOR does not move
    when the digit count changes -- it says nothing about whether the ink FITS -- and every other
    surface assertion in this file compares one copy of a number against another copy of the same
    number, so all of them stayed green while the surface cut two of the three rows in half.

    WHY A STATIC WORST CASE IS SOUND HERE. The three captions are RIGHT-anchored (`right: 100%;
    left: auto`, the track's own left edge) with the icon as the LAST in-flow child, so the anchor
    is digit-count invariant BY CONSTRUCTION and content grows strictly leftward from a fixed edge
    -- widest content == furthest reach, with no layout feedback. See the stylesheet's anchor note.

    RE-DERIVED, NEVER TRANSCRIBED: every length is read out of the rule that owns it and every glyph
    advance out of MoEProgress.js's own hmtx note, so a retune of a gap, a font-size or an icon box
    moves BOTH sides of the comparison together and only a real overflow fails.

    THE BUDGET IS THE 4-DIGIT DELTA (maintainer's call), not the 3-digit one: "(+2,970)" needs a
    combined damage around 150,000 but costs nothing to cover, and the margin left over is small.
    """
    css, js = _read("MoEProgressVertical.css"), _read("MoEProgress.js")
    adv = _advances(js)
    what = "MoEProgressVertical.css"

    def decls(sel):
        return _sole_rule_decls(css, sel, what)

    def rem(sel, prop):
        return _rem(decls(sel), prop, what)

    def tx(sel):
        """The rule's OWN translateX term -- the residual rightward nudge off the shared anchor."""
        match = re.search(r"translateX\((-?[\d.]+)rem\)", decls(sel))
        assert match, "%s: %s has no translateX" % (what, sel)
        return Decimal(match.group(1))

    def shadow(sel):
        """The widest text-shadow BLUR radius one rule declares -- the ink's halo past its box."""
        blurs = re.findall(r"-?[\d.]+rem\s+-?[\d.]+rem\s+([\d.]+)rem", decls(sel))
        assert blurs, "%s: %s declares no text-shadow" % (what, sel)
        return max(Decimal(b) for b in blurs)

    ico_gap = rem(".mpv-cap .mpv-ico", "margin-left")
    # capR's two numeral+icon groups are swapped (eta+battles leads, requirement+mark trails; see
    # MoEProgress.js's V_MARKUP), so the inter-group gap now sits on `.mpv-v`, not `.mpv-eta` -- same
    # 4rem value, just moved to the new leading child of the group it precedes.
    eta_gap = rem(".mpv-capR .mpv-v", "margin-left")
    drop = shadow(".mpv-cap .mpv-v,\n.mpv-cap .mpv-eta,\n.mpv-cap .mpv-d")   # the base dark drop
    glow = shadow(".mpv-v.mpv-up,\n.mpv-d-num.mpv-up,\n.mpv-eta.mpv-up")     # the sign colour glow
    d_size = rem(".mpv-cap .mpv-d", "font-size")
    d_gap_em = re.search(r"margin-right:\s*([\d.]+)em;", decls(".mpv-cap .mpv-d"))
    assert d_gap_em, "%s: the delta's gap is no longer an em" % what
    d_gap = d_size * Decimal(d_gap_em.group(1))

    # Per row: [font-size, the row's own in-flow terms, the halo on its LEFTMOST child, x-gaps].
    # A combined-damage numeral is worst-cased at "3,050" -- 4 digits and a comma -- exactly as the
    # horizontal composition's own extremes in MoEProgress.js are.
    def numeral(size):
        return _ink(adv, size, digits=4, commas=1)

    r_size, c_size, p_size = (rem(s, "font-size") for s in (".mpv-capR", ".mpv-capC", ".mpv-capP"))
    rows = {
        # [eta numeral][battles glyph][requirement numeral][mark glyph] -- the sum is order-
        # independent, but this list is kept in the shipped DOM order for readability.
        ".mpv-capR": (r_size,
                      [_ink(adv, r_size, digits=2),      # "99", the PROGRESS_ETA_CAP
                       ico_gap, rem(".mpv-ico", "width"),         # battles takes the BASE box
                       eta_gap, numeral(r_size), ico_gap, rem(".mpv-ico.mk", "width")],
                      drop, ico_gap + eta_gap + ico_gap),
        # [delta][proj numeral][damage glyph] -- the delta is the leftmost child, so its SIGN GLOW
        # (the widest shadow in the file) is what the surface has to clear, not the base drop.
        ".mpv-capC": (c_size,
                      [_ink(adv, d_size, digits=4, commas=1, parens=2, signs=1), d_gap,
                       numeral(c_size), ico_gap, rem(".mpv-ico.dmgc", "width")],
                      glow, ico_gap + d_gap),
        # [pre numeral][damage-projection glyph]
        ".mpv-capP": (p_size,
                      [numeral(p_size), ico_gap, rem(".mpv-ico.dmgp", "width")],
                      drop, ico_gap),
    }

    allowance = Decimal(_v_shift_x(js))
    worst, gaps = Decimal(0), Decimal(0)
    for sel, (_size, terms, halo, row_gaps) in rows.items():
        # The anchor is the track's own left edge (x == 0 in composition coordinates); the row's
        # content right edge sits at -padding-right + translateX off it, and grows leftward.
        reach = sum(terms) + halo + rem(sel, "padding-right") - tx(sel)
        assert reach <= allowance, (
            "%s's worst-case ink reaches %srem left of the track while the surface only allows "
            "%srem (V_PAD_X_REM - V_BOX_LEFT_REM) -- the caption is CLIPPED" % (sel, reach,
                                                                                allowance))
        worst, gaps = max(worst, reach), max(gaps, row_gaps)
    # ...and the margin is real, not a hairline: a retune that eats it should be a decision, not a
    # surprise. 4.5rem was the maintainer's chosen slack over the 4-digit-delta worst case.
    assert allowance - worst >= 4, \
        "only %srem of caption clearance is left -- budget the surface deliberately" % (
            allowance - worst)

    # LARGE NEEDS NO TWIN, and this is why rather than an assumption: the allowance grows by the
    # backdrop's left bleed picking up SIZE_XF (an x-length), while the ink only grows on its x-GAPS
    # (neither pad, nor any font-size, box or halo, takes the x factor -- the root font's SIZE_F
    # already carries all of those, on both sides of the comparison). So Default keeps binding.
    xf = _size_factor("SIZE_XF")
    extra_allowance = -Decimal(_js_const(js, "V_BOX_LEFT_REM")) * (xf - 1)
    assert extra_allowance > gaps * (xf - 1), (
        "the Large allowance grows by %srem but a row's x-gaps grow by up to %srem -- Default no "
        "longer binds and this test owes a Large twin" % (extra_allowance, gaps * (xf - 1)))


# The vertical MA surface as it shipped BEFORE V_PAD_X_REM existed: (width, shiftX) == box + 2*10
# and 10 - (-34). Frozen here on purpose -- these two ARE the reference the widening promised not to
# move, and the test below is the promise. They are the ONLY historical literals in this file and
# they must never be "updated to match": updating them is exactly the regression.
_PRE_PAD_X_SURFACE = (92, 44)


@pytest.mark.parametrize("space_w", [1920, 2560, 3440])
def test_the_wider_vertical_surface_does_not_move_the_centred_track(space_w):
    """The Damage Log (centred) alignment must land the vertical track EXACTLY where the
    pre-V_PAD_X_REM surface did, at every viewport width.

    WHY THIS IS THE LOAD-BEARING TEST OF THE WHOLE CHANGE. `anchor_centred_reduced` puts the window
    at `max_x // 2` with NO x compensation term anywhere in Python (PROGRESS_ANCHOR_X_OFFSET is 0),
    so it centres the SURFACE and only centres the BAR while the surface brackets the track evenly
    -- the same invariant test_the_large_backdrop_stays_symmetric_about_the_track guards for the
    horizontal composition. Widening the surface on the LEFT ALONE (the obvious way to stop the
    caption clip) silently slides this alignment right by half the asymmetry: 26 logical px at
    Default, 33 at Large, at every resolution, with every other assertion in this file still green.
    Applying V_PAD_X_REM to BOTH sides is what buys the exact equality below, and paying ~53rem of
    surface on a side nobody looks at is free (the rect is never drawn and the hit rect is collapsed
    unconditionally -- see the hitPad assertion at the end).

    COMPOSED THROUGH THE REAL FUNCTIONS, not re-derived arithmetic: the same
    anchor_centred_reduced -> anchor_offset chain bar_window.BarHost._resolve runs, so the `// 2`
    floor and its parity are exercised rather than modelled.
    """
    js = _read("MoEProgress.js")
    surface_w, _surface_h = _v_surface_wh(js)
    shift_x = _v_shift_x(js)
    old_w, old_shift = _PRE_PAD_X_SURFACE

    def track_x(width, shift):
        # Only x matters here; the y arguments are _resolve's real ones and do not affect it.
        base = anchor_centred_reduced(space_w - width, 1080 - 320, 1080,
                                      PROGRESS_ANCHOR_Y_FRAC, VERTICAL_ANCHOR_Y_SHIFT)
        x, _y = anchor_offset(base, PROGRESS_ANCHOR_X_OFFSET, 0)
        return x + shift

    assert track_x(surface_w, shift_x) == track_x(old_w, old_shift), (
        "the centred vertical track moved from %s to %s at %spx wide -- the surface is no longer "
        "concentric with the track" % (track_x(old_w, old_shift), track_x(surface_w, shift_x),
                                       space_w))

    # ...AND THE LARGE TWIN, which can only be bounded, not equal. Both the old and the new Large
    # surface are half-away rounded off a fractional intermediate and `max_x // 2` floors a result
    # whose parity differs between them, so the two land up to a pixel apart by construction -- the
    # same species of jitter memory `anchor-y-reduction-is-not-bit-exact` names on the Y axis.
    # Measured at exactly 0.25px here; a whole pixel is the ceiling worth failing on.
    f, xf = _size_factor("SIZE_F"), _size_factor("SIZE_XF")
    box_w, pad_x = _js_const(js, "V_BOX_W_REM"), _js_const(js, "V_PAD_X_REM")
    box_left, pad = _js_const(js, "V_BOX_LEFT_REM"), _js_const(js, "PAD_REM")
    large_w = iround_half_away((Decimal(box_w) * xf + 2 * pad_x) * f)
    large_shift = (pad_x - Decimal(box_left) * xf) * f
    old_large_w = iround_half_away((Decimal(box_w) * xf + 2 * pad) * f)
    old_large_shift = (pad - Decimal(box_left) * xf) * f
    drift = track_x(large_w, large_shift) - track_x(old_large_w, old_large_shift)
    assert abs(drift) < 1, (
        "the centred vertical track moved %s logical px under Large -- that is a real move, not "
        "the sub-pixel `// 2` parity jitter" % drift)

    # THE INPUT RECT IS UNMOVED TOO, and that is why the extra surface is free rather than a
    # trade-off: hitPad is ceil(max(w, h) / 2) and the vertical composition is height-dominated at
    # BOTH sizes, so widening the surface does not change it by a single rem. (It would not matter
    # even if it did -- pushHitArea collapses the rect unconditionally -- but a grown hit rect would
    # still be worth knowing about, and this is the cheapest place to notice.)
    _, surface_h = _v_surface_wh(js)
    assert max(surface_w, surface_h) == max(old_w, surface_h), \
        "the vertical surface is no longer height-dominated -- hitPad now tracks its WIDTH"


def test_the_reachable_minimap_gap_equals_surface_h_minus_track_y():
    # THE INVARIANT the two placement fixes exist to satisfy, pinned from BOTH sides rather than
    # just the tuned constant: the engine clamps every window into [0, space - surface] (memory
    # `engine-clamps-every-wulf-window-to-screen-and-the-mod-depends-on-it`), so whenever
    # gap_bottom is smaller than the surface's own below-the-track slack (surface_h - edge_y) the
    # closest reachable bottom gap IS that slack, not the tuned constant -- and it only equals the
    # tuned constant because the front-end clip (V_CLIP_B_REM) was sized to make it so. A surface
    # retune that forgets to also retune the clip would silently detach this bar from its tuned
    # gap; this test is the tripwire for that.
    from moe_calculator.domain.constants import PROGRESS_MM_GAP_BOTTOM, MM_TRACK_Y, MM_TRACK_Y_LARGE

    js = _read("MoEProgress.js")
    _, surface_h = _v_surface_wh(js)
    assert surface_h - MM_TRACK_Y == PROGRESS_MM_GAP_BOTTOM

    # LARGE is a +/-1 JITTER, not bit-exact (the sibling concern memory
    # `anchor-y-reduction-is-not-bit-exact` names for the horizontal anchor): MM_TRACK_Y_LARGE and
    # the surface height are each independently half-away rounded off a fractional intermediate, so
    # their difference and round(gap * SIZE_F) can land 1 apart -- measured here as exactly 1 for
    # this bar (400 - 363 == 37, round(30 * 1.25) == 38).
    f = _size_factor("SIZE_F")
    surface_h_large = iround_half_away(Decimal(surface_h) * f)
    tuned_large = iround_half_away(Decimal(PROGRESS_MM_GAP_BOTTOM) * f)
    delta = (surface_h_large - MM_TRACK_Y_LARGE) - tuned_large
    assert abs(delta) <= 1, (
        "the Large reachable gap drifted by %d from round(gap * SIZE_F), which must be a bounded "
        "+/-1 jitter, never more" % delta)


def test_the_vertical_dash_grids_gap_stripe_stays_fully_opaque():
    # Phase 1 porting instruction ("Dash-gap alpha -- CLOSED"): unlike the vertical PROGRESS
    # TUNER's gapA default of 0.5 (inherited from the horizontal progress tuner's own tuned
    # default), the SHIPPED vertical progress stylesheet hand-rewrites the gap to opaque
    # (rgba(13,14,16,1)), exactly like the horizontal bar already does. SCOPED to
    # .mpv-track::after's OWN gradient -- a bare value search for "0.5" would either miss this
    # rule or false-hit the box-shadow ring in the SAME rule, which is legitimately
    # rgba(13,14,16,0.5) (it sits OUTSIDE the fill and was never part of this porting
    # instruction).
    body = _css_rule(_read("MoEProgressVertical.css"), ".mpv-track::after")
    match = re.search(r"background-image:\s*repeating-linear-gradient\(([^;]*)\);", body)
    assert match, "MoEProgressVertical.css: .mpv-track::after has no repeating-linear-gradient"
    stops = re.findall(r"rgba?\(([^)]*)\)", match.group(1))
    assert len(stops) == 4, "expected one dash + one gap stop pair, got %r" % (stops,)
    for gap in stops[2:]:
        parts = [p.strip() for p in gap.split(",")]
        assert len(parts) == 3 or float(parts[3]) == 1.0, \
            "the vertical dash grid's GAP stripe must be fully opaque, not %r" % (gap,)
    # ...while the outset ring stays at the garage bar's 0.5 -- it sits OUTSIDE the fill, and is
    # NOT the value this porting instruction touches.
    box_shadow = re.search(r"box-shadow:\s*([^;]+);", body)
    assert box_shadow and box_shadow.group(1).strip() == "0 0 0 1rem rgba(13,14,16,0.5)"


def test_both_bars_read_the_new_show_events_flag_as_not_false():
    # `showEvents` is a NEW VM bool, and a model that does not carry it (a pre-push frame, an old
    # harness fixture, a marshal that dropped it) must degrade to the SHIPPED behaviour -- "an
    # event raises the bar". `!!undefined` is false, so a `!!` read would silently ship the
    # UNSHIPPED behaviour instead: a bar that never comes up. Both bars, one test, because they are
    # separate render() functions that trivially drift apart.
    #
    # SCOPED TO THE OWNING CONDITIONAL, and over COMMENT-STRIPPED source. A bare
    # `"model.showEvents !== false" in src` is not an assertion: both files carry that exact spelling
    # in the comment ABOVE the gate explaining why it is `!==` and not `!!`, so deleting the gate
    # outright left the substring behind and the check went vacuously green (mutation-probed).
    # The show trigger's OTHER two terms are what pin it to the real branch -- the event term
    # (`changed` / `gained`) and the settle gate -- so assert the whole expression.
    for name, event_term in (("MoEProgress.js", "changed"), ("MoEEfficiency.js", "gained")):
        src = re.sub(r"^[ \t]*//.*$", "", _read(name), flags=re.M)
        assert re.search(r"\(%s && model\.showEvents !== false && T\.settled\(\)\)" % event_term,
                         src), \
            "%s: the show trigger is no longer gated on showEvents (or the gate moved)" % name
        assert "!!model.showEvents" not in src, \
            "%s: showEvents must be read as `!== false`, never `!!` (absent means ON)" % name


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


def test_the_vertical_twin_keyframe_blocks_stay_identical_modulo_the_name():
    # mpv-life-b is the SAME re-trigger twin, for the VERTICAL composition (Phase 0: "built from
    # ONE builder called TWICE so they are byte-identical by construction rather than by hand" --
    # MoEBarTransient.js's RUN_CLASSES_V/RUN_NAMES_V alternate .mpv-run / .mpv-run-b the same way
    # the horizontal pair above alternates .mp-run/.mp-run-b).
    css = _read("MoEProgressVertical.css")
    assert _keyframes(css, "mpv-life") == _keyframes(css, "mpv-life-b")


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


def test_the_delta_carries_the_efficiency_bars_size_but_not_its_nudge_anymore():
    # A live pass once settled the recent-delta's look on the Damage Efficiency bar and the maintainer
    # asked for the SAME size AND nudge here -- but the "MA delta mirrors the Efficiency bar's delta
    # nudge" invariant is now RETIRED (maintainer decision): the two bars' deltas are independent. Only
    # the SIZE half of the mirror still holds -- font-size 12rem, MoEEfficiency.css's own value -- so
    # only that is asserted against the sibling. The Y is this bar's OWN tuned value
    # (translateY(1.5rem), scoped-pinned below) and must NOT be compared to the Efficiency bar's
    # 2.5rem.
    # The tuner is asserted alongside because MoEProgress.css is a -EmitCss output: pinning only the
    # stylesheet lets the next re-emit revert this silently, which is how it was lost once already.
    decls = _sole_rule_decls(_read("MoEProgress.css"), ".mp-cap .mp-d", "MoEProgress.css")
    assert re.search(r"\bfont-size:\s*12rem\s*;", decls), "delta font-size is not 12rem"
    # THE OWN NUDGE, PINNED HERE (not a bare substring grep -- scoped to the rule that owns it via
    # _sole_rule_decls above): the base anchor is 1.5rem, fractional again, which is why this bar's
    # four interface-scale correction rules for the delta are BACK (see
    # test_caption_anchor_quantisation.py's _MA_CORRECTED) -- a whole-rem anchor would have resolved
    # to the same device pixel at every factor and needed no correction, but 1.5rem does not.
    assert re.search(r"\btransform:\s*translateY\(1\.5rem\)\s*;", decls), \
        "delta Y nudge is not 1.5rem"
    tuner = _read_tuner()
    assert tuner.count("font-size: 12rem;\\n") == 1 and \
        tuner.count("transform: translateY(1.5rem);\\n") == 1, \
        "gen_bar_tuner.ps1 -EmitCss no longer emits the delta size/nudge -- a re-emit would revert it"
    # ...AND THE TUNER'S OTHER HALF. Its live-preview <style> carries its OWN hardcoded copy of both
    # (no knob: see the -EmitCss comment), and that preview is the surface the look is APPROVED on
    # -- so a drift there sends the next live pass back to re-tuning a value that already shipped.
    # Anchored on the rule's OWN opening, not on a bare `translateY(1.5rem)`: the stylesheet and both
    # tuner halves each carry a translateY of their own for the SIDE captions' numerals (the numY
    # knob), so an unanchored search is satisfied the moment those two happen to agree -- which is a
    # single retune away. The assertion above is scoped by _sole_rule_decls for the same reason; this
    # file's whole anti-vacuity rule is that a value only counts when read out of the rule that owns
    # it.
    assert tuner.count(".mp-cap .mp-d{position:absolute;left:100%;margin-left:.35em;"
                       "font-size:12rem;transform:translateY(1.5rem);") == 1, \
        "the tuner's LIVE PREVIEW no longer previews the delta's tuned size/nudge"


def _rem(decls, prop, what):
    """The rem value of `prop` within one rule's declarations, as a Decimal."""
    match = re.search(r"\b%s:\s*(-?[\d.]+)rem\s*;" % re.escape(prop), decls)
    assert match, "%s: no %s in `%s`" % (what, prop, decls.strip())
    return Decimal(match.group(1))


def test_the_eta_gap_separates_the_requirement_numeral_from_the_battles_glyph():
    """The 4rem gap between the next-mark numeral and the remaining-battles glyph (etaGap),
    pinned in BOTH stylesheet rules it feeds and BOTH tuner halves that derive them.

    SCOPED, not a bare `4rem` / `margin-left` substring -- both strings recur elsewhere in this
    file (e.g. `.mp-lg .mp-cap.side.mp-capR { margin-left: 4rem; }`, `.mp-capR .mp-ico` transforms),
    so `_sole_rule_decls` is what refuses a match against the wrong rule.

    PLACEMENT is no longer the adjacency of the gap rule to `::after` -- a `.mp-ico.battles::before`
    glow rule now sits between them (the gold-glow addition), so that adjacency check is retired.
    What placement now actually decides is a CASCADE RACE: `.mp-capR .mp-ico::before` (the side
    caption's dark drop) and `.mp-ico.battles::before` (this glyph's own gold override) are EQUAL
    SPECIFICITY -- both two classes plus a pseudo-element, (0,2,1) -- so the cascade has no
    specificity tiebreaker and falls through to SOURCE ORDER alone. Pin that the gold rule comes
    AFTER the dark-drop rule: reorder them and the battles glyph silently reverts to the dark drop
    with no error anywhere, while every value-equality grep in this file still passes.
    """
    css = _read("MoEProgress.css")
    decls = _sole_rule_decls(css, ".mp-ico.battles", "MoEProgress.css")
    assert _rem(decls, "margin-left", "MoEProgress.css") == 4, \
        "the requirement<->battles-glyph gap is not 4rem"
    bare = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    dark_drop = ".mp-capR .mp-ico::before"
    gold = ".mp-ico.battles::before"
    assert bare.count(dark_drop) == 1 and bare.count(gold) == 1, \
        "expected exactly one %s rule and one %s rule" % (dark_drop, gold)
    assert bare.index(dark_drop) < bare.index(gold), \
        "%s must come AFTER %s in source order -- both are (0,2,1) specificity, so the cascade " \
        "decides by source order alone, and reordering them silently reverts the battles glyph " \
        "to the dark drop" % (gold, dark_drop)
    # THE .mp-lg TWIN -- the hand-authored x-length pair this rule feeds. Pinned here too (not
    # only via the derived-count assertion in test_every_large_declaration_is_its_base_counterpart_
    # times_four_thirds): that test is satisfied by ANY correct 4/3 relationship between the base
    # and the twin, so a mutation that moves BOTH together in lockstep would still pass it. This
    # anchors the BASE side of that relationship to the literal spec value.
    large_decls = _sole_rule_decls(css, ".mp-lg .mp-ico.battles", "MoEProgress.css")
    assert _rem(large_decls, "margin-left", "MoEProgress.css") == Decimal("5.333"), \
        "the .mp-lg twin of the eta gap is not 4 * 4/3 == 5.333rem"
    # THE TUNER, all four places that would silently revert this on the next -EmitCss / a re-tune:
    # the SCHEMA default (what -EmitCss derives from), the emit builder (must read st.etaGap, never
    # a literal "4"), and the live preview's custom-property wiring + consuming rule.
    tuner = _read_tuner()
    default = re.search(r'\{id:"etaGap",[^}]*\bval:([\d.]+)\}', tuner)
    assert default and Decimal(default.group(1)) == 4, \
        "gen_bar_tuner.ps1's etaGap default is %s, not 4 -- the next -EmitCss would revert the gap" \
        % (default and default.group(1))
    assert tuner.count('".mp-ico.battles { margin-left: "+st.etaGap+"rem; }\\n"+') == 1, \
        "gen_bar_tuner.ps1 -EmitCss no longer emits the eta gap from st.etaGap"
    assert tuner.count(".mp-ico.battles{margin-left:var(--etagap)}") == 1, \
        "the tuner's live preview no longer takes the eta gap from --etagap"
    assert tuner.count('S.setProperty("--etagap",rem(st.etaGap))') == 1, \
        "the tuner's live preview no longer writes --etagap from the st.etaGap knob"


def test_the_eta_numeral_glows_on_the_deltas_own_sign_knobs():
    """.mp-eta.mp-up / .mp-eta.mp-down carry no dedicated knobs of their own -- they are added to the
    EXISTING .mp-v/.mp-d-num sign-glow rules, riding upCol/dnCol and the same triple text-shadow. Two
    independent gates, both required: the CSS rule here is inert without the JS's `capEta` in the
    d>0/d<0 toggle array (pinned separately, in check_progress_js.js).

    SCOPED to each rule via `_sole_rule_decls`, not a bare colour grep: rgba(123,236,55,0.9) /
    rgba(211,68,63,0.9) both already appear in the SAME two rules for `.mp-v`/`.mp-d-num`, so an
    unscoped substring search would pass even if `.mp-eta` were never added to the selector list.
    """
    css = re.sub(r"/\*.*?\*/", "", _read("MoEProgress.css"), flags=re.S)
    up = _sole_rule_decls(css, ".mp-v.mp-up,\n.mp-d-num.mp-up,\n.mp-eta.mp-up", "MoEProgress.css")
    down = _sole_rule_decls(css, ".mp-v.mp-down,\n.mp-d-num.mp-down,\n.mp-eta.mp-down",
                            "MoEProgress.css")
    for decls, colour, what in ((up, "123,236,55", "up"), (down, "211,68,63", "down")):
        shadows = re.findall(r"0rem 0rem (\d+)rem rgba\((\d+,\d+,\d+),(0\.\d+)\)", decls)
        assert shadows == [("1", "0,0,0", "0.5"), ("6", colour, "0.9"), ("1", colour, "0.9")], \
            "the .mp-eta.mp-%s rule's triple shadow does not match the delta's dark drop + wide " \
            "pass + tight core -- .mp-eta must share upCol/dnCol, never carry its own literal" % what


def test_the_two_centre_captions_icons_sit_at_their_tuned_y():
    """The Y of each centre caption's icon, PINNED AS A VALUE in both halves.

    The centring test below walks these same two rules but only asserts the transform's SHAPE
    (`translate(0rem, <signed rem>)`) -- what it owns is the negative margin, and it keeps that
    shape check only to prove the per-role Y still rides a transform rather than a margin. That
    left the Y ITSELF with no signal at all: a live pass moved the bottom row's glyph 3rem and
    reverting it -- in the stylesheet OR in the tuner's SCHEMA default -- kept the whole suite green.
    So pin the literal, the way the delta's nudge above is pinned.

    ONE tuner assertion per caption covers BOTH tuner halves, because both DERIVE from the knob
    rather than restating it: -EmitCss interpolates `st.icoYC` (asserted in the centring test) and
    the live preview writes it into the --icoyc custom property (asserted here). Those two
    derivation pins are what make the SCHEMA default the single source -- and hence what makes
    pinning that default enough. THE TOP caption is in here too even though that pass only moved
    the bottom one: its Y sits behind exactly the same shape-only check, so it carried the same
    hole, and 0 is the value where a DROPPED translateY would look identical.
    """
    css, tuner = _read("MoEProgress.css"), _read_tuner()
    for cap, knob, prop, want in ((".mp-capP", "icoYP", "--icoyp", "0"),
                                  (".mp-capC", "icoYC", "--icoyc", "1")):
        decls = _sole_rule_decls(css, cap + " .mp-ico", "MoEProgress.css")
        got = re.search(r"\btransform:\s*translate\(0rem,\s*(-?[\d.]+)rem\)\s*;", decls)
        assert got and Decimal(got.group(1)) == Decimal(want), \
            "%s's icon Y is %s, not %srem" % (cap, got and got.group(1) + "rem", want)
        # THE TUNER'S SCHEMA DEFAULT, scoped to the ONE knob entry that owns it -- a 128KB file of
        # prose, sliders and two CSS templates, where a bare search for `1` is satisfied by
        # anything from a slider `min` to a comment.
        default = re.search(r'\{id:"%s",[^}]*\bval:(-?[\d.]+)\}' % knob, tuner)
        assert default and Decimal(default.group(1)) == Decimal(want), \
            "gen_bar_tuner.ps1's %s default is %s, not %s -- the next -EmitCss would revert the " \
            "stylesheet" % (knob, default and default.group(1), want)
        assert tuner.count("%s .mp-ico{transform:translate(0,var(%s))" % (cap, prop)) == 1, \
            "the tuner's live preview no longer takes %s's icon Y from %s" % (cap, prop)
        assert tuner.count('S.setProperty("%s",rem(st.%s))' % (prop, knob)) == 1, \
            "the tuner's live preview no longer writes %s from the st.%s knob" % (prop, knob)


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
        # ...and the per-role Y is still on the SAME rule's transform, not traded for a margin. Shape
        # only, as the docstring says -- the quantisation term chained after it is matched loosely
        # here on purpose (the test above pins it per caption).
        assert re.search(r"\btransform:\s*translate\(0rem,\s*-?[\d.]+rem\)[^;]*;", decls), \
            "%s's icon lost the transform that scopes its glow's z-index" % cap
    for cap in (".mp-capR",):
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


def test_python_y_shift_cancels_the_js_intra_surface_shift():
    # PROGRESS_ANCHOR_Y_SHIFT is now the PURE term -- just -SHIFT_Y_REM, cancelling the
    # composition's intra-surface downward shift so the bar stays put on screen. THIS is the
    # lockstep the test has always guarded: change SHIFT_Y_REM in the JS without changing the
    # Python and the bar moves. The extent-to-viewport UNIT CONVERSION the retired two-term
    # PROGRESS_ANCHOR_Y_OFFSET composite also carried is gone -- anchor_centred_reduced computes
    # it algebraically by applying the fraction to space_y directly (see its docstring), so no
    # surface-height term is baked into this constant any more.
    js = _read("MoEProgress.js")
    assert PROGRESS_ANCHOR_Y_SHIFT == -_shift_y(js)


def test_python_large_y_shift_is_the_same_pure_term_scaled_by_size_f():
    # The LARGE twin, derived the SAME way from the SAME shipped JS -- only in logical px now, so
    # it carries SIZE_F and NOT SIZE_XF (this is the Y axis). No literal here: a retune of the pad
    # or the box propagates, and so does a change to SIZE_F itself.
    js = _read("MoEProgress.js")
    assert PROGRESS_ANCHOR_Y_SHIFT_LARGE == -_large_shift_y(js)


@pytest.mark.parametrize("space_h", [1080, 1440])
def test_the_composed_placement_puts_the_track_at_the_tuned_viewport_fraction(space_h):
    # THE invariant the pure shift term exists for: the track's top edge must land at
    # PROGRESS_ANCHOR_Y_FRAC of the VIEWPORT height -- resolution-invariant by construction, hence
    # both heights. Composed exactly as bar_window.BarHost._resolve does it now: the far-sentinel
    # clamp hands anchor_centred_reduced the movable extent AND the full space_y (the fraction is
    # applied to space_y directly, no extent-to-viewport conversion needed any more -- see
    # anchor_centred_reduced's docstring), then the stored X/Y stepper offset (0 here) composes on
    # top via anchor_offset, and the track sits SHIFT_Y_REM below the window's top edge. 1px of
    # slack for the int() floor. Before the original fix, 0.85 of the extent alone put the track at
    # 77.7vh.
    #
    # ...AND THE SAME FOR THE LARGE SIZE MODE, which is the whole point of that mode: it is a pure
    # scale-up, so the bar must not MOVE. Everything on the large side is bigger -- the surface, the
    # intra-surface shift, hence the Y compensation -- and the track's top edge has to come out at
    # the SAME fraction of the same viewport, asserted both against the fraction and directly
    # against the 1x placement. Slack is 1.5px on the large side.
    js = _read("MoEProgress.js")
    surface_w, surface_h = _surface_wh(js)
    max_x, max_y = 1920 - surface_w, space_h - surface_h
    base = anchor_centred_reduced(max_x, max_y, space_h, PROGRESS_ANCHOR_Y_FRAC,
                                  PROGRESS_ANCHOR_Y_SHIFT)
    _x, y = anchor_offset(base, PROGRESS_ANCHOR_X_OFFSET, 0)
    top = y + _shift_y(js)
    assert abs(top - PROGRESS_ANCHOR_Y_FRAC * space_h) <= 1
    lw, lh = _large_surface_wh(js)
    lmax_x, lmax_y = 1920 - lw, space_h - lh
    lbase = anchor_centred_reduced(lmax_x, lmax_y, space_h, PROGRESS_ANCHOR_Y_FRAC,
                                   PROGRESS_ANCHOR_Y_SHIFT_LARGE)
    _lx, ly = anchor_offset(lbase, PROGRESS_ANCHOR_X_OFFSET, 0)
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
    """`text` with every rem AND em length multiplied by SIZE_XF, at the stylesheet's own 3dp.

    The UNIT IS PRESERVED, and `em` is in here because leaving it out is how the delta's gap shipped
    25% short under the size mode: `.mp-cap .mp-d`'s `margin-left: 0.35em` is a horizontal length
    like any other, and 0.35em of a font-size the root font already grew by SIZE_F carries SIZE_F
    but not SIZE_XF. Everything else a value can hold -- a %, `contain`, a colour, `90deg`, a
    background-size y-ratio -- still passes through untouched, which is what the CLEAN claim rests
    on."""
    xf = _size_factor("SIZE_XF")

    def _one(match):
        scaled = (Decimal(match.group(1)) * xf).quantize(Decimal("0.001"),
                                                         rounding=ROUND_HALF_UP)
        return format(scaled.normalize(), "f") + match.group(2)

    return re.sub(r"(-?[\d.]+)(r?em)", _one, text)


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
      * a left/right margin or padding, and `left`/`right` itself, are always x -- in rem OR em
        (`r?em`): an em x-length still owes SIZE_XF on top of the root font, and reading this as
        rem-only is exactly how the delta's `margin-left: 0.35em` went twinless and rendered its
        gap 25% short under the size mode;
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


def _lg_completeness(name):
    """({(base selector, x-property)}, {(twin selector, property)}) for one stylesheet.

    PER DECLARATION, not per selector -- and that distinction is itself a hole this section once
    had, of exactly the species it exists to catch. `.mp-cap .mp-d` already carried a `.mp-lg` twin
    for its transform, so the day its `margin-left` gap was added the SELECTOR was already in both
    sets and the new x-length's missing twin was invisible. Confirmed by mutation probe: adding an
    untwinned em x-length to a rule that already has a twin left the whole suite green."""
    base, large = _cascade(name)
    return ({(s, p) for s, body in base.items() for p in _x_props(body)},
            {(s[len(_LG):], p) for s, body in large.items() for p, _v in _decls(body)})


def test_the_large_block_twins_exactly_the_base_cascades_x_lengths():
    # COMPLETE, both directions and per DECLARATION. A base x-length with no twin renders
    # half-scaled horizontally under the large mode; a twin with no base x-length is a rule scaling
    # something the root font already handled (or a selector typo that silently styles nothing).
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
    # RE-DERIVED, not transcribed: the twinned x-lengths (`want`, proven COMPLETE by
    # test_the_large_block_twins_exactly_the_base_cascades_x_lengths above) minus the three
    # RE_DERIVED exceptions this loop `continue`s past without incrementing `checked`. A blind
    # literal bump here is exactly how a mutated twin count would go unnoticed -- this fails if
    # either set drifts, not just if a twin is missing.
    want, _got = _lg_completeness("MoEProgress.css")
    expected = len(want) - len(_RE_DERIVED & want)
    assert checked == expected, (
        "expected %d straight x4/3 declarations (%d twinned x-lengths minus %d re-derived "
        "exceptions), checked %d" % (expected, len(want), len(_RE_DERIVED & want), checked))


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
    # TWO marked regions carry `.mp-lg` now: the size mode itself, and the appended interface-scale
    # correction whose Large twin is a COMPOUND `.mp-s1.mp-lg` (a lone `.mp-s1` rule would match under
    # Large too and, later in the file, win). Both are equally invisible to a re-emit, so the guard
    # counts the union rather than one block -- otherwise adding the second region would have made
    # the `outside == 0` claim fail for a rule that IS protected.
    marked = (('/* ===== APPENDED HAND-ADDED BLOCK -- THE "LARGE" SIZE MODE',
               "/* ===== END APPENDED HAND-ADDED BLOCK ===== */"),
              ("/* ===== APPENDED HAND-ADDED BLOCK -- THE INTERFACE-SCALE CAPTION CORRECTION",
               "/* ===== END APPENDED INTERFACE-SCALE BLOCK ===== */"))
    inside_count = 0
    for head, tail in marked:
        assert css.count(head) == 1 and css.count(tail) == 1, \
            "a hand-added block lost its markers: %s" % head
        inside_count += css[css.index(head):css.index(tail)].count(_LG)
    assert css.count(_LG) == inside_count > 0, \
        "a .mp-lg rule sits OUTSIDE the marked blocks -- a re-emit would drop it silently"
    # A RULE, not a mention: the emitted caption-pin comment names `.mp-lg` when it points readers at
    # the sibling hand-added blocks, and a bare substring search is satisfied by that prose (the repo
    # lesson `unscoped-substring-assertion-is-not-an-assertion`, in the direction that FAILS a green
    # file). A selector followed by a declaration brace is the thing that would actually be emitted.
    assert not re.search(r"\.mp-lg [^\n\"]*\{", _read_tuner()), \
        "gen_bar_tuner.ps1 now emits the size mode -- move this guard onto its emit, the way the " \
        "delta size/nudge pins are asserted in BOTH the tuner and the stylesheet"
