"""Recover the in-battle minimap's on-screen size by diffing screenshots.

The minimap's index -> pixel mapping lives in compiled AS3 with no Python
accessor, so pixel measurement (not a symbol read) is the only route to the
maintainer's own resolution + interface scale.

MINIMAP POSITION: the minimap is flush to the screen's BOTTOM-RIGHT corner,
with ~zero inset, at every interface scale -- confirmed on real 3840x2160
captures at scale 1 and scale 2. Its own "inner" corner (the one facing the
HUD) is therefore its BOTTOM-LEFT corner, at (image_width - size, image_height).

CAPTURE CAVEAT: two same-paused-frame screenshots are NOT pixel-identical
outside the minimap -- foliage/TAA keeps jittering, and HUD strips can change
between shots. A plain diff + connected-component bounding box is therefore
NOT robust: a noise blob adjacent to the minimap's edge merges into its
component and drags the bbox out. The PRIMARY estimator here is instead a
corner scan: walk left along a row near the bottom-right corner, counting the
contiguous (gap-tolerant) changed run -- immune to noise anywhere else in the
frame. The connected-component bbox is kept only as a CROSS-CHECK (its height
axis sits in quiet sky and is rarely contaminated).

GAP TOLERANCE BRIDGES A NOISE SLIVER IF THE THRESHOLD IS TOO TIGHT: at
`--threshold 10`, a real 1440p capture had a single borderline JPEG-noise
pixel (diff ~11-14) flip to "changed" right next to the minimap's true edge,
narrowing what should be a clean 3px unchanged gap down to 2px -- which
`--gap 2` then correctly bridges (2 <= gap IS meant to be tolerated), running
the scan on into unrelated HUD noise far to the left. This is a THRESHOLD
problem, not a gap-arithmetic one: raising `--threshold` to 15 removed that
borderline pixel and made the same shot read the true size stably at every
gap 0/1/2/4 (matched against an independently-implemented reference `run()`
byte-for-byte). `DEFAULT_THRESHOLD` was bumped 10 -> 15 for this reason.
Because gap sensitivity is silent otherwise, `measure()` still recomputes the
corner-scan size at gaps 0/1/2/4 as a diagnostic and WARNs if they disagree
by more than a few px -- that disagreement is the tell for exactly this
threshold-too-tight failure mode, so treat it as "raise --threshold", not
"lower --gap".

A column-density estimator (scanning a vertical band for changed-pixel
density) was tried as a second cross-check axis and REJECTED: it is only
valid when the sampling band is comfortably taller than the minimap, so on a
1440p capture at the largest size index it fell under its density cutoff and
returned garbage. Do not add it back as a general estimator.

The measured LOGICAL size (device px / --scale) is invariant across BOTH
interface scale AND screen resolution -- verified against 3840x2160 (scale 1
and scale 2) and 2560x1440 (scale 1) captures, all agreeing on
[228, 279, 329, 409, 510, 628] logical px (+/-1, JPEG threshold noise).
Expected use elsewhere: `size = SIZES[index]`, `corner = (logical_w - size,
logical_h)`, `device_size = logical_size * interface_scale`.

CAPTURE PROCEDURE (do this exactly, all 7 shots at the SAME paused frame):
  1. Launch a replay. Pause it with Space (frame is now static).
  2. Toggle the minimap OFF (its visibility hotkey / CMD_MINIMAP_VISIBLE) and
     take a screenshot -> this is the BASELINE (--hidden).
  3. Toggle the minimap back ON. Cycle its size with the minimap size hotkeys
     through all 6 size indices (0..5), taking one screenshot at each size
     (--shots, in ascending index order).
  4. Do NOT unpause, and do NOT move/rotate the camera between any of the 7
     shots -- any camera or animation drift breaks the diff (see check #5
     below: "almost the whole image changed" means two different frames).
  5. WoT writes screenshots into the game install dir's screenshots/ folder
     (default hotkey, or the client's screenshot binding). Copy the 7 files
     out and pass their paths to this script.

Usage:
    python tools/dev/measure_minimap.py --hidden baseline.png \\
        --shots s0.png s1.png s2.png s3.png s4.png s5.png \\
        --scale 1.5 --json out.json

Self-check (no screenshots needed, synthesizes images with PIL):
    python tools/dev/measure_minimap.py --selfcheck
"""
import argparse
import json
import sys

from PIL import Image, ImageChops

DEFAULT_THRESHOLD = 15
DEFAULT_GAP = 2
DEFAULT_EDGE_MARGIN = 2
CROSS_CHECK_TOLERANCE = 3
GAP_STABILITY_PROBES = (0, 1, 2, 4)


def _load(path):
    im = Image.open(path).convert("RGB")
    return im


def _diff_mask(baseline, shot, threshold):
    """Per-pixel boolean mask where baseline and shot differ by > threshold on any channel."""
    diff = ImageChops.difference(baseline, shot)
    w, h = diff.size
    px = diff.load()
    mask = [[False] * w for _ in range(h)]
    any_changed = False
    for y in range(h):
        row = mask[y]
        for x in range(w):
            r, g, b = px[x, y]
            if r > threshold or g > threshold or b > threshold:
                row[x] = True
                any_changed = True
    return mask, any_changed


def _components(mask, w, h):
    """4-connected components of True cells. Returns list of (bbox, count), largest first."""
    seen = [[False] * w for _ in range(h)]
    comps = []
    for sy in range(h):
        for sx in range(w):
            if not mask[sy][sx] or seen[sy][sx]:
                continue
            stack = [(sx, sy)]
            seen[sy][sx] = True
            minx = maxx = sx
            miny = maxy = sy
            count = 0
            while stack:
                x, y = stack.pop()
                count += 1
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            comps.append(((minx, miny, maxx + 1, maxy + 1), count))
    comps.sort(key=lambda c: c[1], reverse=True)
    return comps


def _corner_scan_size(mask, w, h, gap=DEFAULT_GAP, edge_margin=DEFAULT_EDGE_MARGIN):
    """Walk left along a row `edge_margin` px above the bottom edge, starting `edge_margin`
    px in from the right edge (skips JPEG ringing right at the screen border), counting the
    contiguous changed run. Tolerates up to `gap` consecutive unchanged px inside the run
    (foliage/TAA jitter) but stops at a longer gap. The minimap is assumed flush to the
    bottom-right corner, so size = image_width - (leftmost changed column found)."""
    y = h - 1 - edge_margin
    if not (0 <= y < h):
        return None
    x = w - 1 - edge_margin
    last_true = None
    misses = 0
    while x >= 0:
        if mask[y][x]:
            last_true = x
            misses = 0
        else:
            misses += 1
            if misses > gap:
                break
        x -= 1
    if last_true is None:
        return None
    return w - last_true


def measure(baseline, shot, threshold=DEFAULT_THRESHOLD, gap=DEFAULT_GAP,
            edge_margin=DEFAULT_EDGE_MARGIN, verbose_clusters=False):
    """Diff `shot` against `baseline`; return a result dict (see module docstring for fields)."""
    if baseline.size != shot.size:
        raise ValueError("size mismatch: baseline %r vs shot %r" % (baseline.size, shot.size))
    w, h = baseline.size
    mask, any_changed = _diff_mask(baseline, shot, threshold)

    result = {
        "image_size": [w, h],
        "warnings": [],
    }
    if not any_changed:
        result["warnings"].append("no pixels changed at all -- wrong shot, or minimap "
                                   "already at this state in the baseline")
        result["bbox"] = None
        result["scan_size"] = None
        result["corner"] = None
        return result

    comps = _components(mask, w, h)
    (left, top, right, bottom), changed_px = comps[0]
    bbox_w = right - left
    bbox_h = bottom - top
    bbox_area = bbox_w * bbox_h
    fill_ratio = changed_px / float(bbox_area) if bbox_area else 0.0

    result["bbox"] = {"left": left, "top": top, "right": right, "bottom": bottom,
                       "width": bbox_w, "height": bbox_h}
    result["changed_px"] = changed_px
    result["fill_ratio"] = fill_ratio

    scan_size = _corner_scan_size(mask, w, h, gap=gap, edge_margin=edge_margin)
    result["scan_size"] = scan_size

    # gap-stability diagnostic: a bridged sliver just past the minimap's true edge is
    # invisible unless you compare several gap tolerances against each other -- a real
    # 1440p capture over-read by ~89% at gap=4 while gaps 0-2 agreed.
    gap_probe = {g: _corner_scan_size(mask, w, h, gap=g, edge_margin=edge_margin)
                 for g in GAP_STABILITY_PROBES}
    result["gap_probe"] = gap_probe
    probed = [v for v in gap_probe.values() if v is not None]
    if probed and (max(probed) - min(probed)) > CROSS_CHECK_TOLERANCE:
        result["warnings"].append(
            "GAP-SENSITIVE corner scan: sizes at gap=0/1/2/4 are %r -- a larger gap is "
            "likely bridging a noise sliver just outside the minimap's true edge; the "
            "smallest gap(s) that agree with each other are the trustworthy reading, "
            "NOT necessarily the --gap default" % gap_probe)

    if scan_size is None:
        result["warnings"].append(
            "corner scan found no changed run at the bottom-right corner -- "
            "--gap/--edge-margin may need tuning, or the minimap isn't there")
        result["corner"] = None
    else:
        # flush-to-corner assumption: report the minimap's own bottom-left corner
        # (the one facing the HUD) directly off the image dimensions, not the
        # (possibly noise-contaminated) bbox.
        result["corner"] = {
            "left": w - scan_size,
            "bottom": h,
            "size": scan_size,
            "right_inset": w - right,
            "bottom_inset": h - bottom,
        }
        # cross-check: the bbox's OWN axes should each match the scan size (the
        # minimap is square); a mismatch is exactly the contamination signal that
        # caught a noise blob merged into the bbox in real captures.
        diff_w = abs(scan_size - bbox_w)
        diff_h = abs(scan_size - bbox_h)
        result["cross_check"] = {"scan_size": scan_size, "bbox_width": bbox_w,
                                  "bbox_height": bbox_h, "diff_width": diff_w, "diff_height": diff_h}
        if diff_w > CROSS_CHECK_TOLERANCE or diff_h > CROSS_CHECK_TOLERANCE:
            result["warnings"].append(
                "CROSS-CHECK MISMATCH: corner-scan size %d disagrees with bbox width %d "
                "(diff %d) / bbox height %d (diff %d) by more than %d px -- the bbox is "
                "likely contaminated by noise merged in from outside the minimap"
                % (scan_size, bbox_w, diff_w, bbox_h, diff_h, CROSS_CHECK_TOLERANCE))

    # secondary clusters: anything else more than a few px from the main bbox
    secondary = []
    for (l2, t2, r2, b2), count in comps[1:]:
        gap_dist = max(0, l2 - right, left - r2, t2 - bottom, top - b2)
        if gap_dist > 5:
            secondary.append({"bbox": [l2, t2, r2, b2], "changed_px": count})
    if secondary:
        secondary.sort(key=lambda c: c["changed_px"], reverse=True)
        result["secondary_clusters_count"] = len(secondary)
        shown = secondary if verbose_clusters else secondary[:3]
        result["secondary_clusters"] = shown
        result["warnings"].append(
            "%d SECONDARY CLUSTER(S) outside the main bbox -- likely noise (moving HUD "
            "element / unpaused frame / tank marker), NOT unioned into the bbox; "
            "largest %d shown: %r"
            % (len(secondary), len(shown), shown))

    if fill_ratio < 0.85:
        result["warnings"].append(
            "low fill_ratio %.2f -- the changed pixels are scattered, not a dense "
            "rectangle; the bbox is likely meaningless (frame wasn't paused / camera moved)"
            % fill_ratio)

    if bbox_area >= 0.9 * w * h:
        result["warnings"].append(
            "bbox spans nearly the whole image -- baseline and shot are probably "
            "two different frames entirely, not a minimap toggle")

    cx, cy = left + bbox_w / 2.0, top + bbox_h / 2.0
    if not (cx > w / 2.0 and cy > h / 2.0):
        result["warnings"].append(
            "bbox center (%.0f, %.0f) is NOT in the bottom-RIGHT quadrant of a %dx%d "
            "image -- unexpected minimap position" % (cx, cy, w, h))

    if bbox_h:
        aspect = bbox_w / float(bbox_h)
        if abs(aspect - 1.0) > 0.15:
            result["warnings"].append(
                "aspect ratio %.2f deviates >15%% from square" % aspect)

    return result


def _fmt_table(rows, scale):
    header = ["idx", "size", "right_inset", "bottom_inset", "bbox_w", "bbox_h"]
    if scale:
        header += ["size(log)"]
    header += ["fill", "changed_px", "warnings"]
    lines = ["\t".join(header)]
    for label, r in rows:
        if r["bbox"] is None:
            lines.append("%s\t(no diff)" % label)
            continue
        b = r["bbox"]
        c = r["corner"]
        row = [str(label), c["size"] if c else "?", c["right_inset"] if c else "?",
               c["bottom_inset"] if c else "?", b["width"], b["height"]]
        if scale:
            row += ["%.1f" % (c["size"] / scale) if c else "?"]
        row += ["%.2f" % r["fill_ratio"], r["changed_px"], len(r["warnings"])]
        lines.append("\t".join(str(cell) for cell in row))
    return "\n".join(lines)


def _build_parser():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hidden", help="baseline screenshot, minimap hidden")
    ap.add_argument("--shots", nargs="+", help="screenshots, ascending size index 0..N unless --labels")
    ap.add_argument("--scale", type=float, default=None, help="interface scale at capture time (optional)")
    ap.add_argument("--labels", help="comma-separated labels for --shots, default 0,1,2,...")
    ap.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD,
                     help="per-channel diff threshold 0-255 (default %d)" % DEFAULT_THRESHOLD)
    ap.add_argument("--gap", type=int, default=DEFAULT_GAP,
                     help="max consecutive unchanged px tolerated inside the corner-scan run "
                          "(default %d)" % DEFAULT_GAP)
    ap.add_argument("--edge-margin", type=int, default=DEFAULT_EDGE_MARGIN,
                     help="px skipped at the screen's outer edge before the corner scan starts "
                          "(default %d)" % DEFAULT_EDGE_MARGIN)
    ap.add_argument("--verbose-clusters", action="store_true",
                     help="dump every secondary cluster instead of just the largest 3")
    ap.add_argument("--json", dest="json_out", help="write machine-readable results here")
    ap.add_argument("--selfcheck", action="store_true", help="run the built-in synthetic self-check and exit")
    return ap


def main(argv=None):
    ap = _build_parser()
    args = ap.parse_args(argv)

    if args.selfcheck:
        _selfcheck()
        return

    if not args.hidden or not args.shots:
        ap.error("--hidden and --shots are required (or use --selfcheck)")

    baseline = _load(args.hidden)
    labels = args.labels.split(",") if args.labels else [str(i) for i in range(len(args.shots))]
    if len(labels) != len(args.shots):
        ap.error("--labels count must match --shots count")

    results = []
    for label, path in zip(labels, args.shots):
        shot = _load(path)
        if shot.size != baseline.size:
            ap.error("resolution mismatch: %s is %r, baseline is %r -- a mid-pass "
                      "resolution change invalidates the whole set" % (path, shot.size, baseline.size))
        r = measure(baseline, shot, threshold=args.threshold, gap=args.gap,
                    edge_margin=args.edge_margin, verbose_clusters=args.verbose_clusters)
        r["label"] = label
        r["path"] = path
        results.append((label, r))

    # monotonic sizes across ascending index (primary corner-scan size)
    sizes = [r["scan_size"] for _, r in results if r["scan_size"] is not None]
    deltas = [sizes[i + 1] - sizes[i] for i in range(len(sizes) - 1)]
    monotonic = all(d >= 0 for d in deltas)

    print(_fmt_table(results, args.scale))
    if not args.scale:
        print("\n(no --scale given: logical-px column skipped)")
    print("\nsize (px, corner scan) deltas across index: %r" % deltas)
    if not monotonic:
        print("WARNING: size sequence is NOT monotonically ascending -- shots may be "
              "mislabeled or out of order")
    for label, r in results:
        for w in r["warnings"]:
            print("WARNING [%s]: %s" % (label, w))

    if args.json_out:
        payload = {
            "image_size": baseline.size,
            "scale": args.scale,
            "threshold": args.threshold,
            "gap": args.gap,
            "edge_margin": args.edge_margin,
            "monotonic": monotonic,
            "size_deltas": deltas,
            "shots": [
                {k: v for k, v in r.items() if k != "path"}
                for _, r in results
            ],
        }
        with open(args.json_out, "w") as f:
            json.dump(payload, f, indent=2)
        print("\nwrote %s" % args.json_out)


def _selfcheck():
    """Synthesize a baseline + a shot with a known bottom-right-flush square, assert the
    corner scan recovers its size exactly -- including in the presence of noise that would
    fool a plain connected-component bbox."""
    W, H = 200, 150
    baseline = Image.new("RGB", (W, H), (20, 20, 20))

    # known minimap: 50x50, flush to the bottom-right corner (left=150, top=100,
    # right=200, bottom=150)
    rect = (150, 100, 200, 150)
    shot = baseline.copy()
    px = shot.load()
    for y in range(rect[1], rect[3]):
        for x in range(rect[0], rect[2]):
            px[x, y] = (200, 200, 200)

    r = measure(baseline, shot, threshold=10)
    assert r["bbox"] == {"left": 150, "top": 100, "right": 200, "bottom": 150, "width": 50, "height": 50}, r
    assert r["scan_size"] == 50, r["scan_size"]
    assert r["corner"]["left"] == 150 and r["corner"]["bottom"] == 150
    assert r["corner"]["right_inset"] == 0 and r["corner"]["bottom_inset"] == 0
    assert r["fill_ratio"] == 1.0
    assert r["changed_px"] == 50 * 50
    assert not r.get("secondary_clusters")
    # bbox center (175, 125) in a 200x150 image -> x>100, y>75 -> bottom-right quadrant: no warning
    assert not any("quadrant" in w for w in r["warnings"])
    assert not any("aspect ratio" in w for w in r["warnings"])
    assert not any("CROSS-CHECK" in w for w in r["warnings"])

    # (a) contamination case: an adjacent noise blob touching the square's LEFT edge,
    # confined to a y-range inside the square's own height (so bbox height stays clean,
    # only bbox width gets dragged out) -- this is what real foliage/TAA jitter did.
    noisy = baseline.copy()
    pxn = noisy.load()
    for y in range(rect[1], rect[3]):
        for x in range(rect[0], rect[2]):
            pxn[x, y] = (200, 200, 200)
    for y in range(120, 131):        # inside [100, 150)
        for x in range(130, 150):    # touches the square's left edge at x=150
            pxn[x, y] = (200, 200, 200)
    r_noisy = measure(baseline, noisy, threshold=10)
    assert r_noisy["bbox"]["width"] == 70, \
        "a plain bbox must over-read (contaminated): %r" % r_noisy["bbox"]
    assert r_noisy["bbox"]["height"] == 50, r_noisy["bbox"]
    assert r_noisy["scan_size"] == 50, \
        "the corner scan must return the TRUE size despite the contaminated bbox: %r" % r_noisy["scan_size"]
    assert any("CROSS-CHECK MISMATCH" in w for w in r_noisy["warnings"]), \
        "the scan-vs-bbox-width disagreement must be flagged: %r" % r_noisy["warnings"]

    # (b) gap tolerance: a <=--gap unchanged gap inside the run is bridged; a longer
    # gap stops the scan early.
    gappy = baseline.copy()
    pxg = gappy.load()
    for y in range(rect[1], rect[3]):
        for x in range(rect[0], rect[2]):
            pxg[x, y] = (200, 200, 200)
    scan_row = H - 1 - DEFAULT_EDGE_MARGIN  # 147, inside [100, 150)
    for x in range(170, 172):    # 2px gap (<= default gap=2): must be bridged
        pxg[x, scan_row] = (20, 20, 20)
    r_small_gap = measure(baseline, gappy, threshold=10)
    assert r_small_gap["scan_size"] == 50, \
        "a <=--gap unchanged gap must be tolerated: %r" % r_small_gap["scan_size"]

    gappier = baseline.copy()
    pxg2 = gappier.load()
    for y in range(rect[1], rect[3]):
        for x in range(rect[0], rect[2]):
            pxg2[x, y] = (200, 200, 200)
    for x in range(160, 168):    # 8px gap (> default gap=2): must stop the scan
        pxg2[x, scan_row] = (20, 20, 20)
    r_big_gap = measure(baseline, gappier, threshold=10)
    assert r_big_gap["scan_size"] < 50, \
        "a gap longer than --gap must NOT be bridged: %r" % r_big_gap["scan_size"]

    # complementary boundary check: a gap of EXACTLY gap+1 unchanged px must stop the run
    # (the "<=gap tolerated" test above alone doesn't pin the other side of the boundary).
    exact_stop = baseline.copy()
    pxe = exact_stop.load()
    for y in range(rect[1], rect[3]):
        for x in range(rect[0], rect[2]):
            pxe[x, y] = (200, 200, 200)
    for x in range(170, 173):    # exactly 3px gap == default gap(2) + 1: must stop
        pxe[x, scan_row] = (20, 20, 20)
    r_exact_stop = measure(baseline, exact_stop, threshold=10, gap=2)
    assert r_exact_stop["scan_size"] < 50, \
        "a gap of exactly gap+1 px must STOP the run, not bridge it: %r" % r_exact_stop["scan_size"]

    # real-world structure: a flush bottom-right square, then a clean 3px unchanged gap
    # right at its true edge, then ragged noise further left (unrelated HUD/foliage
    # content). gap=2 must read the true size; gap=4 bridges the 3px gap and over-reads.
    ragged = baseline.copy()
    pxr = ragged.load()
    for y in range(rect[1], rect[3]):
        for x in range(rect[0], rect[2]):
            pxr[x, y] = (200, 200, 200)
    for x, val in [(146, True), (145, False), (144, True), (143, True), (142, False),
                   (141, True), (140, True), (139, True), (138, False), (137, True)]:
        pxr[x, scan_row] = (200, 200, 200) if val else (20, 20, 20)
    # rect's left edge is at 150; a clean 3px gap sits at 147-149 (unset above, still baseline)
    r_ragged_gap2 = measure(baseline, ragged, threshold=10, gap=2)
    assert r_ragged_gap2["scan_size"] == 50, \
        "gap=2 must read the TRUE size through the 3px edge gap: %r" % r_ragged_gap2["scan_size"]
    r_ragged_gap4 = measure(baseline, ragged, threshold=10, gap=4)
    assert r_ragged_gap4["scan_size"] > 50, \
        "gap=4 must bridge the 3px edge gap into the ragged noise and over-read: %r" % r_ragged_gap4["scan_size"]

    # gap-stability guard: a 3px unchanged sliver just outside the minimap's true left
    # edge, with more changed pixels further left still (mimicking a real capture where
    # a noise sliver sits just past the edge and unrelated changed pixels lie beyond it).
    # gap=2 must return the true size; a gap that bridges the sliver (e.g. 8) must
    # over-read; the instability must be flagged regardless of which --gap was requested.
    sliver = baseline.copy()
    pxs = sliver.load()
    for y in range(rect[1], rect[3]):
        for x in range(rect[0], rect[2]):
            pxs[x, y] = (200, 200, 200)
    for x in range(120, 150):    # more "changed" pixels further left, beyond the sliver
        pxs[x, scan_row] = (200, 200, 200)
    for x in range(147, 150):    # 3px unchanged sliver just outside the true edge
        pxs[x, scan_row] = (20, 20, 20)
    r_sliver = measure(baseline, sliver, threshold=10, gap=2)
    assert r_sliver["scan_size"] == 50, \
        "gap=2 must not bridge the 3px sliver: %r" % r_sliver["scan_size"]
    r_sliver_bridged = measure(baseline, sliver, threshold=10, gap=8)
    assert r_sliver_bridged["scan_size"] > 50, \
        "gap=8 must bridge the sliver and over-read: %r" % r_sliver_bridged["scan_size"]
    assert any("GAP-SENSITIVE" in w for w in r_sliver["warnings"]), \
        "the gap-stability probe must flag this regardless of the requested --gap: %r" % r_sliver["warnings"]

    # threshold guard: a faint 5/255 halo must not register at threshold=10
    faint = baseline.copy()
    px3 = faint.load()
    for y in range(rect[1], rect[3]):
        for x in range(rect[0], rect[2]):
            r0, g0, b0 = px3[x, y]
            px3[x, y] = (r0 + 5, g0 + 5, b0 + 5)
    r3 = measure(baseline, faint, threshold=10)
    assert r3["bbox"] is None, "a 5/255 diff must be below the default threshold=10"

    # no-diff case
    r4 = measure(baseline, baseline.copy(), threshold=10)
    assert r4["bbox"] is None
    assert "no pixels changed" in r4["warnings"][0]

    # default-threshold guards: call measure() with NO explicit threshold, so a drifted
    # DEFAULT_THRESHOLD (in either direction) is actually exercised, not shadowed by every
    # other call site passing threshold=10 explicitly.
    r5 = measure(baseline, faint)
    assert r5["bbox"] is None, "the DEFAULT threshold must still reject a 5/255 faint halo"
    r6 = measure(baseline, shot)
    assert r6["scan_size"] == 50, \
        "the DEFAULT threshold must still recover a clean known size exactly: %r" % r6["scan_size"]

    # the DEFAULT_* copies (measure()'s signature + the real argparse defaults)
    # must not drift apart
    defaults = _build_parser().parse_args([])
    assert defaults.threshold == DEFAULT_THRESHOLD
    assert defaults.gap == DEFAULT_GAP
    assert defaults.edge_margin == DEFAULT_EDGE_MARGIN

    print("selfcheck: all assertions passed")


if __name__ == "__main__":
    main()
