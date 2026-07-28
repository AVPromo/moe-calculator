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
