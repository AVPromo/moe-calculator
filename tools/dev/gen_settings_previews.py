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
# reads crisp from a 4x source. Getting this wrong is silent: every pixel rect this script reads
# via `getBoundingClientRect()` is in CSS px, so it must be scaled by this factor before use as a
# device-px coordinate against the (4x-sized) screenshot -- see `_device_rect()` below.
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
_STRIP_SCENE_CSS = (
    "html,body{background:transparent!important}"
    ".stage{background:none!important;box-shadow:none!important;outline:none!important}"
    ".panel,#ribbons,#mmMock,#loupe{display:none!important}"
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

# The flat _BAR_ALPHA_THRESHOLD above clips more than the haze: a widget's own BACKDROP is a
# large, deliberately low-opacity radial/dither shape (checker dither ~alpha 25 at its own
# opacity:0.1, dark radial underlay fading from ~alpha 89 at centre to 0 at its edge) -- most of
# its OWN painted area sits at or below the same 45-alpha ceiling as the haze, so a flat floor
# silently shrinks the backdrop's true CSS-drawn extent (confirmed on bar_ma_horizontal: alpha>1
# bbox is 303px wide, matching `.mp-backdrop`'s own 360rem*pxrem; alpha>45 bbox is only 238px).
# Fix: read each backdrop element's OWN getBoundingClientRect() and floor at a much lower
# threshold ONLY inside that rect (haze there is negligible next to real backdrop opacity, so a
# low threshold is safe), keeping the normal floor everywhere else. Selectors per job below.
_BACKDROP_LOW_THRESHOLD = 3
# bar_ma_horizontal's review-confirmed defect (backdrop ~50% too small) traced to THIS floor
# clipping a real, low-opacity backdrop -- see TASKS/settings-preview-images.md's 2026-08-12
# backdrop-review note. EXTENDED to bar_eff_horizontal (2026-08-12 fine-tuning round): both bars
# render the EXACT SAME `.mp-backdrop` selector off byte-identical CSS (checker opacity 0.1, same
# mask/gradient stops -- MoEEfficiency.css vs MoEProgress.css, verified), so eff_h's backdrop
# reading visibly more "solid" than ma_h's is this SAME flat-floor clip, not a CSS difference --
# an unprotected job at the shared T=45 ceiling floors most of the backdrop's own low-opacity
# paint. bar_eff_vertical's and bar_ma_vertical's own review findings were POSITION mismatches
# between a caption and its backdrop STRIP (a seed/shipped-value issue) -- not a floor-clipping-
# the-size issue, so they get no entry here.
_BACKDROP_SELECTORS = {
    "bar_ma_horizontal": [".mp-backdrop"],
    "bar_eff_horizontal": [".mp-backdrop"],
}


def _floor_alpha(im, threshold):
    """Return a copy of `im` with every alpha <= threshold forced to exactly 0."""
    from PIL import Image
    r, g, b, a = im.split()
    a = a.point(lambda p: 0 if p <= threshold else p)
    return Image.merge("RGBA", (r, g, b, a))


def _floor_alpha_protected(im, threshold, low_threshold, protect_rects):
    """Like _floor_alpha, but pixels inside `protect_rects` ((l,t,r,b) tuples) use
    `low_threshold` instead -- so a widget's own real, low-opacity backdrop paint survives
    even where it sits below the haze-killing floor everywhere else."""
    from PIL import Image, ImageDraw
    high = _floor_alpha(im, threshold)
    if not protect_rects:
        return high
    low = _floor_alpha(im, low_threshold)
    mask = Image.new("L", im.size, 0)
    draw = ImageDraw.Draw(mask)
    for l, t, r, b in protect_rects:
        draw.rectangle([l, t, r, b], fill=255)
    return Image.composite(low, high, mask)

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

# WebView2 runtime's own Chromium -- present on any Windows 11 box even with no user-facing
# Edge/Chrome install. Globbed (not hardcoded) because the version folder rolls with Windows
# Update; the highest installed version is used.
def _find_edge():
    cands = sorted(glob.glob(
        r"C:\Program Files (x86)\Microsoft\EdgeCore\*\msedge.exe"))
    return cands[-1] if cands else None


def _alpha_bbox(im):
    return im.split()[3].getbbox()


def _device_rect(css_rect, dsf):
    """A getBoundingClientRect() tuple is in CSS px; the screenshot is `dsf`x that -- scale."""
    return tuple(v * dsf for v in css_rect)


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

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=edge, headless=True)
        try:
            for name, tuner_rel, viewport, strip_css, setup_js, threshold, wait_ms in _JOBS:
                page = browser.new_page(viewport=viewport, device_scale_factor=SUPERSAMPLE)
                page.goto("file:///" + os.path.join(_REPO, tuner_rel).replace("\\", "/"))
                if strip_css:
                    page.add_style_tag(content=strip_css)
                if setup_js:
                    page.evaluate(setup_js)
                page.wait_for_timeout(wait_ms)
                protect_rects = []
                for sel in _BACKDROP_SELECTORS.get(name, ()):
                    r = page.evaluate(
                        "(sel) => { const el = document.querySelector(sel); "
                        "if (!el) return null; const r = el.getBoundingClientRect(); "
                        "return [r.left, r.top, r.right, r.bottom]; }", sel)
                    if r:
                        protect_rects.append(_device_rect(r, SUPERSAMPLE))
                raw = page.screenshot(omit_background=True)
                page.close()

                from io import BytesIO
                im = Image.open(BytesIO(raw)).convert("RGBA")
                # Floor FIRST (zeroes the capture haze at the pixel level), THEN find the bbox
                # and crop the FLOORED image -- a bbox cutoff alone still leaves haze pixels
                # inside the box (see the threshold comment above). Each backdrop element's own
                # rect gets a much lower floor so its real, low-opacity paint survives.
                im = _floor_alpha_protected(im, threshold, _BACKDROP_LOW_THRESHOLD, protect_rects)
                bbox = _alpha_bbox(im)
                if not bbox:
                    print("%-20s NOTHING rendered (fully transparent) -- skipped." % name)
                    continue
                pad = _BBOX_PAD * SUPERSAMPLE
                l, t, r, b = bbox
                l, t = max(0, l - pad), max(0, t - pad)
                r, b = min(im.width, r + pad), min(im.height, b + pad)
                crop = im.crop((l, t, r, b))
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
        finally:
            browser.close()


if __name__ == "__main__":
    main()
