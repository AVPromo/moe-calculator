# -*- coding: utf-8 -*-
"""Render the six MSA settings-panel preview PNGs from the dev tuners, as TRANSPARENT crops of
the real widget (not screenshot crops of a battle backdrop -- see the previous version's
docstring in git history for that approach).

Python 3 + Pillow + Playwright. Playwright drives a real Chromium so the tuner's actual CSS/JS
lays the widget out exactly as it does in a browser; Pillow then finds the widget's own painted
region (by alpha, NOT a hardcoded crop box) and applies ONE uniform scale to the whole set.

DEPENDENCIES (dev-only, never shipped):
    py -m pip install playwright
No browser download needed -- EDGE_PATH below points at the WebView2-runtime's own Chromium
binary, which Windows ships even without a user-facing Edge/Chrome install. If neither Playwright
nor that binary is present this prints a clear message and exits without touching any file (a
checkout without them can still run the rest of the dev tooling).

Run from the repo root:
    py tools/dev/gen_settings_previews.py

Each tuner's OWN default on-load state is used for the four bar images (do not touch -- these
are the SAME state their check_*.js drift gates already verify); only the calculator tuner is
driven (via its window.setAssist toggle) to get both the ON/OFF row states out of one file.
"""
import glob
import os

_REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_OUT_DIR = os.path.join(_REPO, "src", "res", "gui", "maps", "icons", "moe_calculator", "previews")

# SUPERSAMPLE, not a cosmetic shrink: Playwright's `device_scale_factor` renders the page at
# this many device px per CSS px (real Chromium supersampling, not a post-hoc PIL upscale), so
# every icon/glyph/gradient is rasterised at full detail before any crop happens -- the fix for
# the user's anti-pixelation ask. The shipped PNG is saved at this FULL supersampled resolution
# (no shrink-back-down applied here): MSA's own `width`/`height` (the DISPLAY size this script
# also reports -- the widget's native 1x logical bbox) does the downscale at render time, which
# reads crisp from a 4x source.
SUPERSAMPLE = 4

# A generous viewport that comfortably contains every tuner's fixed 1600x900 `.stage` (bar
# tuners) or the calculator's fixed 340x152 document -- alpha-bbox cropping trims the rest, so
# oversizing this costs nothing but a slightly bigger raw screenshot.
_BAR_VIEWPORT = {"width": 1650, "height": 950}
_CALC_VIEWPORT = {"width": 340, "height": 152}

# (output name, tuner file, viewport, setup JS to run before the shot -- None for "use the
# tuner's own default, gate-verified state, untouched").
# The calculator tuner's own body is already `background:transparent` (MoEBattle.css) -- no
# override needed. The bar tuners paint an opaque photo `.stage` + a control `.panel`/mock
# `#ribbons`/`#mmMock` scene around the widget for interactive tuning; NONE of that is the
# widget, so it is stripped for the render (not part of the mirrored widget CSS -- this is
# scene dressing the tuner adds on top, same override proven in the render-capability smoke
# test: TASKS/settings-preview-images.md).
#   #ribbons/#mmMock -- mock damage-ribbon / minimap scene dressing.
#   #loupe            -- the MA-horizontal tuner's own "dither magnifier" debug panel.
# The shipped in-battle bars KEEP their backdrop (dark radial + checker-dither strips) -- this
# is a PREVIEW-ONLY omission, so the settings-panel image shows just the track/ticks/numbers/
# icons on full transparency. `.mp-backdrop` (horizontals) paints its own dither/glow directly
# via ::before/::after; `.mev-bd`/`.mpv-bd` (efficiency/progress verticals) are the per-row strip
# elements that carry it (`.mev-backdrop`/`.mpv-backdrop` themselves paint nothing -- see each
# tuner's own header comment). Hiding the host element also suppresses its ::before/::after.
_STRIP_SCENE_CSS = (
    "html,body{background:transparent!important}"
    ".stage{background:none!important;box-shadow:none!important;outline:none!important}"
    ".panel,#ribbons,#mmMock,#loupe{display:none!important}"
    ".mp-backdrop,.mev-bd,.mpv-bd{display:none!important}"
)

# Alpha threshold, PER JOB -- used as an OUTPUT FLOOR, not just a bbox cutoff: every pixel with
# alpha <= T is forced to EXACT 0 (not just excluded from the crop box). The calculator tuner's
# page has no haze (its body is genuinely transparent outside the widget -- corners measure exact
# alpha 0 with no floor needed; T=10 here is just a small safety margin). The four bar tuners,
# once the scene dressing above is stripped, still carry a low-level (~0-40) alpha HAZE across
# nearly the whole 1600x900 stage EVEN AT PIXELS WHERE `elementsFromPoint` shows only fully-
# transparent, mask-free, opacity:1 ancestors -- i.e. no CSS on the page paints it. Ruled out as a
# GPU-compositor effect: identical under `--disable-gpu`, `--disable-gpu-compositing` and
# `--use-gl=swiftshader` (all tried; none changed a single alpha value). It is a real artifact of
# Chromium's `omit_background` screenshot capture on a page with enough masked/gradient layers
# elsewhere, not of any particular render backend -- so it is scrubbed at the OUTPUT instead: the
# floor below zeroes it outright rather than merely excluding it from the crop rectangle (a bbox
# cutoff alone still leaves haze pixels INSIDE the box, visible as a veil once composited onto a
# dark panel). This unavoidably also floors the last, faintest few percent of the widget's own
# designed glow tail, which sits in the same alpha range and is not separable by value alone -- a
# disclosed tradeoff (a hairline glow loss), not an oversight; a visible veil is the worse defect.
# See TASKS/settings-preview-images.md.
_CALC_ALPHA_THRESHOLD = 10
_BAR_ALPHA_THRESHOLD = 45
_BBOX_PAD = 4

# The backdrop-protected-floor machinery this comment used to describe is GONE (2026-08-12):
# previews now hide the backdrop entirely (see _STRIP_SCENE_CSS above), so there is no more
# low-opacity backdrop paint to protect from the flat haze floor below -- a plain _floor_alpha
# is correct again. See git history for the prior per-job protected-rect approach if a preview
# ever needs its backdrop back.


def _floor_alpha(im, threshold):
    """Return a copy of `im` with every alpha <= threshold forced to exactly 0."""
    from PIL import Image
    r, g, b, a = im.split()
    a = a.point(lambda p: 0 if p <= threshold else p)
    return Image.merge("RGBA", (r, g, b, a))

# (output name, tuner file, viewport, extra style CSS to strip scene dressing (None = not
# needed), setup JS to run before the shot (None = use the tuner's own default, gate-verified
# state, untouched), alpha threshold, ms to wait before the shot (the bar tuners hold-fade in on
# load -- a short wait catches them mid-animation and under-renders every alpha value)).
_JOBS = (
    ("calc_assist_on", "TASKS/refs/in-battle-overlay-tuner.html", _CALC_VIEWPORT, None,
     "document.documentElement.style.fontSize='1px'", _CALC_ALPHA_THRESHOLD, 200),
    ("calc_assist_off", "TASKS/refs/in-battle-overlay-tuner.html", _CALC_VIEWPORT, None,
     "document.documentElement.style.fontSize='1px';setAssist(false)", _CALC_ALPHA_THRESHOLD, 200),
    ("bar_eff_horizontal", "tools/dev/eff_bar_tuner.html", _BAR_VIEWPORT,
     _STRIP_SCENE_CSS, None, _BAR_ALPHA_THRESHOLD, 2000),
    ("bar_eff_vertical", "tools/dev/eff_bar_tuner_vertical.html", _BAR_VIEWPORT,
     _STRIP_SCENE_CSS, None, _BAR_ALPHA_THRESHOLD, 2000),
    ("bar_ma_horizontal", "TASKS/refs/in-battle-bar-tuner.html", _BAR_VIEWPORT,
     _STRIP_SCENE_CSS, None, _BAR_ALPHA_THRESHOLD, 2000),
    ("bar_ma_vertical", "TASKS/refs/in-battle-bar-tuner-vertical.html", _BAR_VIEWPORT,
     _STRIP_SCENE_CSS, None, _BAR_ALPHA_THRESHOLD, 2000),
)

# All four bar previews fill their whole preview box with N copies of themselves, one per COLOUR
# RANGE the shipped widget has (DE Damage Efficiency: 5 -- `.mev-b-w/g/t/v/au` (vertical) /
# `.mp-b-w/g/t/v/au` (horizontal), white/green/teal/violet/gold, `MoEEfficiency.js`'s
# BAND_CLASSES; MA Moving Average: 3 -- plain up/down (green/red, `.mpv-fill.mpv-up`/`.mpv-down`,
# `.mp-fill.mp-up`/`.mp-down` horizontal) plus the gold "mark met" `.mpv-full`/`.mp-full`
# override) instead of one bar in mostly-empty space. The verticals tile the copies SIDE BY SIDE
# (`hconcat`); the horizontals -- already wide -- STACK them as rows (`vconcat`). Both DE tuners
# (horizontal/vertical) and both MA tuners share identical slider ids/defaults (`dmg`/`r65`../
# `preAvg`/`projAvg`/`marks`), so one state list drives all 4 previews. Each state string is JS
# run via `page.evaluate` against the tuner's own top-level `set(id, v)` + `apply()` (both plain
# global functions -- these tuners have no wrapping IIFE, confirmed live). `setPos(st.projAvg,
# false)` is forced on the MA states because `apply()` only calls it itself when the root ISN'T
# mid the initial load replay's hold animation (`if (!root.classList.contains("mp(v)-run"))
# setPos(...)`) -- relying on that timing is fragile (the hold can outlast this file's wait_ms),
# so the fill/proj tick position is set directly and unconditionally instead. DE's own apply()
# has no such gate -- it always writes fill.style.height itself, so no equivalent call is needed.
#
# DE fill levels sit in the MIDDLE of each band's own range (stops [0, 2450, 3050, 3620, 4400]),
# so the current-damage cursor reads as centred in its colour segment rather than pinned to the
# band's own edge -- deliberately off the exact boundaries, since `band(d, stops)` in the tuner
# assigns a value EXACTLY AT a requirement to the band ABOVE it (`if (d >= stops[i]) n = i`).
# Gold is the one exception: it has no ceiling, so it stays at its own prior value (4800, well
# clear of r100=4400) -- reads as unambiguously maxed/fully filled, which mid-banding would undo.
_DE_BAND_STATES = (
    ("white", "set('dmg',1225);apply();"),   # mid [0, 2450)
    ("green", "set('dmg',2750);apply();"),   # mid [2450, 3050)
    ("teal",  "set('dmg',3335);apply();"),   # mid [3050, 3620)
    ("violet","set('dmg',4010);apply();"),   # mid [3620, 4400)
    ("gold",  "set('dmg',4800);apply();"),   # unchanged -- well above r100, fully filled
)
# MA has FOUR states, not three -- the base `.mp(v)-fill` (NEITHER up/down/full class) is a real,
# documented shipped state, not a gap: MoEProgress.css's own header comment on `.mp-fill` spells
# it out -- "Zero delta -> NEITHER class -> the neutral background above... THE NEUTRAL IS CREAM
# (rgba(237,230,217,0.8)), reserved for the only two states with nothing committed to show: the
# FIRST show of a battle... and a ROUNDED-ZERO DELTA." `showVal()`'s own gate is
# `glows = Math.round(Math.abs(d)) !== 0` -- up/down are toggled only if glows, so preAvg ===
# projAvg (delta exactly 0) reaches it deterministically, no ambiguity. Order requested:
# red (down) -> white (neutral) -> green (up) -> gold (full).
# `preAvg` is HELD FIXED at 2905 across down/white/up so only `projAvg` moves below/at/above it
# -- a shared anchor makes the red->white->green sequence read as one progression around a
# single mark, instead of "same damage, three colours" (varying preAvg per state was
# counterintuitive here).
_MA_BAND_STATES = (
    ("down",  "set('preAvg',2905);set('projAvg',2850);apply();setPos(st.projAvg,false);"),
    ("white", "set('preAvg',2905);set('projAvg',2905);apply();setPos(st.projAvg,false);"),
    ("up",    "set('preAvg',2905);set('projAvg',2960);apply();setPos(st.projAvg,false);"),
    ("full",  "set('marks',1);set('preAvg',2905);set('projAvg',3100);apply();"
              "setPos(st.projAvg,false);"),
)
_MULTI_BAND_JOBS = {
    "bar_eff_vertical": (_DE_BAND_STATES, "h"),
    "bar_ma_vertical": (_MA_BAND_STATES, "h"),
    "bar_eff_horizontal": (_DE_BAND_STATES, "v"),
    "bar_ma_horizontal": (_MA_BAND_STATES, "v"),
}
_MULTI_BAND_GAP_PX = 8 * SUPERSAMPLE  # 8 display px between copies

# MA-VERTICAL-only, PREVIEW-ONLY: hides `.mpv-tick.mpv-bottom`, the shipped axisLo end-tick
# (always present in the real widget, pinned at the track's own 0% floor by `bottom:0` --
# confirmed in MoEProgressVertical.css and MoEProgress.js's V_MARKUP; NOT a bug, never toggled by
# any JS condition). Flagged as visual clutter in the vertical 3-up composite and hidden here
# only -- do not copy this rule into shipped CSS, it would remove a real, intentional axis
# marker. Not applied to the horizontal MA stack -- not asked for there, and each row already
# reads cleanly without it (the horizontal end tick sits inline with the axis, not stacked under
# the fill the way the vertical one visually does).
_MA_HIDE_BOTTOM_TICK_CSS = ".mpv-tick.mpv-bottom{display:none!important}"

# WebView2 runtime's own Chromium -- present on any Windows 11 box even with no user-facing
# Edge/Chrome install. Globbed (not hardcoded) because the version folder rolls with Windows
# Update; the highest installed version is used.
def _find_edge():
    cands = sorted(glob.glob(
        r"C:\Program Files (x86)\Microsoft\EdgeCore\*\msedge.exe"))
    return cands[-1] if cands else None


def _alpha_bbox(im):
    return im.split()[3].getbbox()


def main():
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed (`py -m pip install pillow`) -- nothing to do.")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed (`py -m pip install playwright`, no browser download "
              "needed -- see this file's docstring) -- nothing to do.")
        return
    edge = _find_edge()
    if not edge:
        print("no WebView2-runtime Chromium found under Microsoft\\EdgeCore -- nothing to do.")
        return

    missing = [j for j in _JOBS if not os.path.isfile(os.path.join(_REPO, j[1]))]
    if missing:
        print("missing tuner(s): %s -- nothing to do." %
              ", ".join(sorted({j[1] for j in missing})))
        return

    if not os.path.isdir(_OUT_DIR):
        os.makedirs(_OUT_DIR)

    from io import BytesIO

    def shoot(browser, tuner_rel, viewport, strip_css, setup_js, threshold, wait_ms,
              extra_css=None):
        """One screenshot -> floored, tight alpha-bbox crop (or None if fully transparent)."""
        page = browser.new_page(viewport=viewport, device_scale_factor=SUPERSAMPLE)
        page.goto("file:///" + os.path.join(_REPO, tuner_rel).replace("\\", "/"))
        if strip_css:
            page.add_style_tag(content=strip_css)
        if extra_css:
            page.add_style_tag(content=extra_css)
        page.wait_for_timeout(wait_ms)
        if setup_js:
            page.evaluate(setup_js)
            # Root cause of the gold-band "not fully filled" bug: `.mev-fill`/`.mp-fill` height
            # is CSS-transitioned (`--filldur`, shipped default 400ms), so a big jump in `dmg`
            # (band-composite states jump straight from the tuner's own default state) was still
            # mid-animation at 150ms, screenshotting a few px short of its target height even
            # though `fill.style.height` was already the correct final value. 600ms clears the
            # shipped 400ms transition with margin (confirmed via direct getBoundingClientRect()
            # measurement: gapPx was 0 once settled).
            page.wait_for_timeout(600)
        raw = page.screenshot(omit_background=True)
        page.close()

        im = Image.open(BytesIO(raw)).convert("RGBA")
        # Floor FIRST (zeroes the capture haze at the pixel level), THEN find the bbox and crop
        # the FLOORED image -- a bbox cutoff alone still leaves haze pixels inside the box (see
        # the threshold comment above).
        im = _floor_alpha(im, threshold)
        bbox = _alpha_bbox(im)
        if not bbox:
            return None
        pad = _BBOX_PAD * SUPERSAMPLE
        l, t, r, b = bbox
        l, t = max(0, l - pad), max(0, t - pad)
        r, b = min(im.width, r + pad), min(im.height, b + pad)
        return im.crop((l, t, r, b))

    def hconcat(crops_list):
        """Side-by-side, top-aligned, transparent gap between -- same height expected (same
        tuner/layout across states, only fill/colour differs)."""
        w = sum(c.width for c in crops_list) + _MULTI_BAND_GAP_PX * (len(crops_list) - 1)
        h = max(c.height for c in crops_list)
        combo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        x = 0
        for c in crops_list:
            combo.paste(c, (x, 0), c)
            x += c.width + _MULTI_BAND_GAP_PX
        return combo

    def vconcat(crops_list):
        """Stacked rows, left-aligned, transparent gap between -- for the wide horizontal bars
        (tiling those side by side would run off the settings column)."""
        w = max(c.width for c in crops_list)
        h = sum(c.height for c in crops_list) + _MULTI_BAND_GAP_PX * (len(crops_list) - 1)
        combo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        y = 0
        for c in crops_list:
            combo.paste(c, (0, y), c)
            y += c.height + _MULTI_BAND_GAP_PX
        return combo

    crops = {}  # name -> Image -- saved after the loop so calc_assist_off can be padded to
                # calc_assist_on's canvas size first (see below).
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=edge, headless=True)
        try:
            for name, tuner_rel, viewport, strip_css, setup_js, threshold, wait_ms in _JOBS:
                if name in _MULTI_BAND_JOBS:
                    states, direction = _MULTI_BAND_JOBS[name]
                    extra_css = (_MA_HIDE_BOTTOM_TICK_CSS if name == "bar_ma_vertical" else None)
                    subs = []
                    for _label, state_js in states:
                        sub = shoot(browser, tuner_rel, viewport, strip_css, state_js,
                                    threshold, wait_ms, extra_css)
                        if sub is not None:
                            subs.append(sub)
                    if not subs:
                        print("%-20s NOTHING rendered (fully transparent) -- skipped." % name)
                        continue
                    crops[name] = hconcat(subs) if direction == "h" else vconcat(subs)
                    continue
                crop = shoot(browser, tuner_rel, viewport, strip_css, setup_js, threshold,
                             wait_ms)
                if crop is None:
                    print("%-20s NOTHING rendered (fully transparent) -- skipped." % name)
                    continue
                crops[name] = crop
        finally:
            browser.close()

    # calc_assist_off must NOT change the preview's outer size when the panel swaps it in for
    # calc_assist_on (MSA has no crossfade -- a size change reads as a visible resize). The 3-row
    # (on) state is strictly taller. TOP-ALIGN the pad: rows 1/2 are shared between both states
    # and must land at the exact same Y in both images, or toggling the 3rd row on/off visibly
    # shifts rows 1/2 -- that shift is the actual bug this pads against. Product decision: no
    # shift on toggle wins over the standalone centered look (leftover height goes to the bottom
    # as transparent padding, where the missing 3rd row would sit).
    if "calc_assist_on" in crops and "calc_assist_off" in crops:
        on_size = crops["calc_assist_on"].size
        off = crops["calc_assist_off"]
        if off.size != on_size:
            padded = Image.new("RGBA", on_size, (0, 0, 0, 0))
            padded.paste(off, (0, 0))
            crops["calc_assist_off"] = padded

    # NOTE: a prior left-pad-to-400 step for the two vertical bars (right-aligning them in the
    # MSA column) was REVERTED -- MSA's Image control clips at the column's left-anchored width,
    # so a wider-than-natural canvas got its right (content) side cropped. Right-alignment is
    # handled by MSA's own `align='right'` param instead (implementer side); these ship at their
    # natural tight bbox again.

    for name, _tuner_rel, _viewport, _strip_css, _setup_js, _threshold, _wait_ms in _JOBS:
        crop = crops.get(name)
        if crop is None:
            print("%-20s NOTHING rendered (fully transparent) -- skipped." % name)
            continue
        w, h = crop.size
        # SHIP THE FULL SUPERSAMPLED CROP -- no shrink-back-down here (that was the old
        # cosmetic SCALE knob; it fought the supersample). Display size (what MSA's own
        # width/height should be set to, so it downscales this crisply) is the same crop
        # at 1x -- i.e. this size divided back by SUPERSAMPLE.
        out = os.path.join(_OUT_DIR, name + ".png")
        crop.save(out, "PNG")
        disp_w, disp_h = w / SUPERSAMPLE, h / SUPERSAMPLE
        print("%-20s supersampled %4dx%-4d  (%dx)  -> display %6.1fx%-6.1f -> %s" %
              (name, w, h, SUPERSAMPLE, disp_w, disp_h, out))


if __name__ == "__main__":
    main()
