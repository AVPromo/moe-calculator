# -*- coding: utf-8 -*-
"""Bake the six MSA settings-panel preview PNGs from real in-game 4K screenshots.

One-off generator (Python 3 + Pillow). The MSA panel is Scaleform/AS3 and cannot render the
mod's real Gameface DOM, so we ship static PNG crops of real battle screenshots and swap them
live via g_modsSettingsApi.updateImage (see bridge/mod_settings.py:update_preview_images).

SOURCE screenshots (3840x2160, NOT in the repo -- these live in the maintainer's game folder):
    D:/Games/World_of_Tanks_EU/screenshots/shot_002.jpg   calculator 3 rows + Efficiency vertical
    D:/Games/World_of_Tanks_EU/screenshots/shot_003.jpg   Moving Average vertical
    D:/Games/World_of_Tanks_EU/screenshots/shot_005.jpg   calculator 2 rows + Efficiency horizontal
    D:/Games/World_of_Tanks_EU/screenshots/shot_006.jpg   Moving Average horizontal

Crop boxes are original-pixel (left, upper, right, lower). ONE uniform SCALE applies to the whole
set so the six images keep their relative sizes -- tune SCALE, never a per-image size.

Reproducible if the sources exist; a clean no-op (with a message) if they don't, so a checkout
without the screenshots can still run it without error.
"""
import os

# The single tunable knob. 0.5 halves every crop; relative sizes across the six survive.
SCALE = 0.5

_SRC_DIR = u"D:/Games/World_of_Tanks_EU/screenshots"
_OUT_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__),
    u"../../src/res/gui/maps/icons/moe_calculator/previews"))

# (output name, source file, crop box (left, upper, right, lower))
_JOBS = (
    (u"calc_assist_on",     u"shot_002.jpg", (462, 1688, 905, 1852)),
    (u"calc_assist_off",    u"shot_005.jpg", (462, 1688, 905, 1798)),
    (u"bar_eff_vertical",   u"shot_002.jpg", (2658, 1600, 2812, 2150)),
    (u"bar_ma_vertical",    u"shot_003.jpg", (2698, 1585, 2848, 1975)),
    (u"bar_eff_horizontal", u"shot_005.jpg", (1580, 1760, 2210, 1990)),
    (u"bar_ma_horizontal",  u"shot_006.jpg", (1640, 1790, 2220, 1990)),
)


def main():
    from PIL import Image

    missing = [j[1] for j in _JOBS if not os.path.isfile(os.path.join(_SRC_DIR, j[1]))]
    if missing:
        print("source screenshots not found in %s (%s) -- nothing to do."
              % (_SRC_DIR, ", ".join(sorted(set(missing)))))
        return

    if not os.path.isdir(_OUT_DIR):
        os.makedirs(_OUT_DIR)

    for name, src, box in _JOBS:
        im = Image.open(os.path.join(_SRC_DIR, src)).crop(box)
        w, h = im.size
        scaled = (max(1, int(round(w * SCALE))), max(1, int(round(h * SCALE))))
        im = im.resize(scaled, Image.LANCZOS)
        out = os.path.join(_OUT_DIR, name + u".png")
        im.save(out, "PNG")
        print("%-20s %4dx%-4d -> %s" % (name, scaled[0], scaled[1], out))


if __name__ == "__main__":
    main()
