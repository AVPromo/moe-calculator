#!/usr/bin/env python3
"""DEV: diagnose the in-battle percent prediction's error from the mod's own sample log.

`adapter/sample_log.py` appends one JSON line per battle to
`%APPDATA%\\Wargaming.net\\WorldOfTanks\\mods_data\\14th_ua_moe\\battle_samples.jsonl`,
pairing what the overlay PREDICTED with what WG's dossier reported afterwards
(`residual = post_percentile - predicted_percent`, so NEGATIVE = the mod over-predicted).
This reads that file and prints the diagnosis. Read-only, host-side Python 3, stdlib only.

    python tools/dev/analyze_battle_samples.py                  # default prefs path
    python tools/dev/analyze_battle_samples.py <path.jsonl>      # explicit file
    python tools/dev/analyze_battle_samples.py --min-delta 0.5   # ignore near-zero gains
    python tools/dev/analyze_battle_samples.py --self-check      # assert-based self-test

WHY the regression, not just the mean: the live percent is ANCHORED
(`cur_percent = pre_percentile + inc`), so a constant offset in the damage->percent
mapping CANCELS and is invisible. Only the mapping's DERIVATIVE is observable, and it
shows up as residual growing with the predicted gain -- hence OLS of `residual ~ pct_delta`.
A flat slope with a nonzero mean is a level/baseline problem instead (bad thresholds,
stale dossier), not a slope one. Read the verdict line, not the mean alone.

# ponytail: OLS + a t-ratio on the slope, no weighting/robust fit. A handful of outlier
# battles (arty assist, a 100%-mark tank) can tilt the line -- cross-read the buckets and
# the worst-offenders list before believing a slope. Upgrade to a median/Theil-Sen fit only
# if the buckets and the OLS line ever disagree.
"""
import argparse
import json
import os
import statistics as st
from datetime import datetime

DEFAULT_PATH = os.path.join(os.environ.get("APPDATA", ""), "Wargaming.net", "WorldOfTanks",
                            "mods_data", "14th_ua_moe", "battle_samples.jsonl")

BUCKETS = ((0.0, 1.0), (1.0, 2.0), (2.0, 4.0), (4.0, 8.0), (8.0, float("inf")))


# --- loading -----------------------------------------------------------------

def load(path, min_delta=0.0):
    """Usable rows + an ordered {reason: count} skip tally. A bad line is skipped, never fatal."""
    rows, skipped = [], {}

    def skip(why):
        skipped[why] = skipped.get(why, 0) + 1

    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                skip("unparseable JSON")
                continue
            if not isinstance(row, dict):
                skip("unparseable JSON")
                continue
            if not row.get("has_data"):
                skip("has_data false")
                continue
            if row.get("residual") is None:
                skip("residual missing")
                continue
            if abs(_f(row, "pct_delta")) < min_delta:
                skip("pct_delta below --min-delta")
                continue
            rows.append(row)
    return rows, skipped


def _f(row, key):
    """A float field, tolerating null/absent/garbage -> 0.0 (optional keys may be missing)."""
    try:
        return float(row.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


# --- stats -------------------------------------------------------------------

def fit(xs, ys):
    """(slope, intercept, r, se_slope) or None when there's no spread to fit.

    `statistics` already owns the OLS and Pearson r (3.10+); only the slope's standard
    error needs arithmetic: se = sd_y/sd_x * sqrt((1-r^2)/(n-2))."""
    n = len(xs)
    if n < 3 or len(set(xs)) < 2 or len(set(ys)) < 2:
        return None
    slope, intercept = st.linear_regression(xs, ys)
    r = st.correlation(xs, ys)
    se = (st.stdev(ys) / st.stdev(xs)) * (max(0.0, 1.0 - r * r) / (n - 2)) ** 0.5
    return slope, intercept, r, se


def describe(vals):
    """n / mean / median / stdev / min / max as one line."""
    if not vals:
        return "n=0"
    sd = st.stdev(vals) if len(vals) > 1 else 0.0
    return ("n=%d  mean=%+.3f  median=%+.3f  stdev=%.3f  min=%+.3f  max=%+.3f"
            % (len(vals), st.fmean(vals), st.median(vals), sd, min(vals), max(vals)))


# --- report ------------------------------------------------------------------

def report(rows):
    res = [_f(r, "residual") for r in rows]
    deltas = [_f(r, "pct_delta") for r in rows]
    dmg = [_f(r, "combined_damage") for r in rows]
    stamps = [int(r.get("ts") or 0) for r in rows if r.get("ts")]
    tanks = sorted({r.get("int_cd") for r in rows if r.get("int_cd")})
    ks = sorted({_f(r, "ewma_k") for r in rows})
    versions = sorted({str(r.get("mod_version")) for r in rows if r.get("mod_version")})

    print("samples=%d  tanks=%d  ewma_k=%s%s" % (
        len(rows), len(tanks), ", ".join("%g" % k for k in ks) or "-",
        "  mod=" + ",".join(versions) if versions else ""))
    if stamps:
        span = "%s .. %s" % (datetime.fromtimestamp(min(stamps)).strftime("%Y-%m-%d %H:%M"),
                             datetime.fromtimestamp(max(stamps)).strftime("%Y-%m-%d %H:%M"))
    else:
        span = "(no ts)"
    print("dates: " + span)

    print("\n== overall residual (post - predicted; negative = OVER-predicted) ==")
    print("  " + describe(res))

    print("\n== level vs slope ==")
    verdict = "inconclusive"
    for label, xs in (("pct_delta", deltas), ("combined_damage", dmg)):
        f = fit(xs, res)
        if f is None:
            print("  residual ~ %-16s no spread to fit" % label)
            continue
        slope, intercept, r, se = f
        t = slope / se if se else float("inf")
        print("  residual ~ %-16s slope=%+.4f (se %.4f, t=%+.1f)  intercept=%+.3f  r=%+.3f"
              % (label, slope, se, t, intercept, r))
        if label == "pct_delta":
            mean = st.fmean(res)
            sem = (st.stdev(res) / len(res) ** 0.5) if len(res) > 1 else 0.0
            if abs(t) > 2.0:
                verdict = ("SLOPE error: residual moves %+.3f pp per 1 pp of predicted gain "
                           "-> the damage->percent mapping's derivative is %s"
                           % (slope, "too steep" if slope < 0 else "too shallow"))
            elif sem and abs(mean) > 2.0 * sem:
                verdict = ("LEVEL offset: slope is flat (t=%+.1f) but mean residual is %+.3f "
                           "(+-%.3f) -> baseline/threshold problem, not the mapping"
                           % (t, mean, sem))
            else:
                verdict = ("neither is significant yet (slope t=%+.1f, mean %+.3f +-%.3f) "
                           "-> collect more battles" % (t, mean, sem))
    print("  VERDICT: " + verdict)

    print("\n== residual by predicted gain (pct_delta) ==")
    print("  %-12s %4s  %8s  %8s" % ("bucket", "n", "mean", "median"))
    for lo, hi in BUCKETS:
        vals = [_f(r, "residual") for r in rows if lo <= abs(_f(r, "pct_delta")) < hi]
        name = "%g-%g" % (lo, hi) if hi != float("inf") else "%g+" % lo
        if vals:
            print("  %-12s %4d  %+8.3f  %+8.3f" % (name, len(vals), st.fmean(vals), st.median(vals)))
        else:
            print("  %-12s %4d         -         -" % (name, 0))

    print("\n== worst offenders (largest |residual|) ==")
    print("  %-10s %8s %8s %9s %8s %9s" % ("int_cd", "dmg", "delta", "predict", "actual", "residual"))
    for r in sorted(rows, key=lambda r: -abs(_f(r, "residual")))[:10]:
        print("  %-10s %8.0f %8.2f %9.2f %8.2f %+9.2f"
              % (r.get("int_cd"), _f(r, "combined_damage"), _f(r, "pct_delta"),
                 _f(r, "predicted_percent"), _f(r, "post_percentile"), _f(r, "residual")))

    per_tank = {}
    for r in rows:
        per_tank.setdefault(r.get("int_cd"), []).append(_f(r, "residual"))
    shown = [(cd, v) for cd, v in per_tank.items() if len(v) >= 3]
    print("\n== per-tank (>= 3 samples) ==")
    if not shown:
        print("  none yet (%d tanks, all under 3 samples)" % len(per_tank))
    else:
        print("  %-10s %4s  %8s" % ("int_cd", "n", "mean"))
        for cd, vals in sorted(shown, key=lambda kv: st.fmean(kv[1])):
            print("  %-10s %4d  %+8.3f" % (cd, len(vals), st.fmean(vals)))
        print("  (a single tank far off the others = ITS thresholds; all shifted alike = the mapping)")


# --- self-check --------------------------------------------------------------

def self_check():
    """Inject a known slope + offset into synthetic rows and confirm OLS recovers them,
    then round-trip load() to confirm the skip tally, then render the report."""
    rows = [{"has_data": True, "int_cd": 100 + i % 3, "ts": 1750000000 + i * 3600,
             "ewma_k": 0.12, "pct_delta": 0.25 * i, "combined_damage": 300 + 90 * i,
             "predicted_percent": 50.0 + 0.25 * i,
             "post_percentile": 50.0 + 0.25 * i + (1.0 - 0.4 * (0.25 * i)),
             "residual": 1.0 - 0.4 * (0.25 * i)} for i in range(1, 41)]
    slope, intercept, r, se = fit([r["pct_delta"] for r in rows], [r["residual"] for r in rows])
    assert abs(slope - -0.4) < 1e-9, slope
    assert abs(intercept - 1.0) < 1e-9, intercept
    assert abs(r - -1.0) < 1e-9, r
    assert se < 1e-9, se  # perfect fit -> zero residual variance

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "battle_samples.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
            fh.write('{"has_data": false, "residual": 1.0, "pct_delta": 3.0}\n')
            fh.write('{"has_data": true, "pct_delta": 3.0}\n')  # residual missing
            fh.write("not json\n\n")
        loaded, skipped = load(path)
        assert len(loaded) == len(rows), len(loaded)
        assert skipped == {"has_data false": 1, "residual missing": 1, "unparseable JSON": 1}, skipped
        loaded, skipped = load(path, min_delta=5.0)
        assert len(loaded) == len([r for r in rows if r["pct_delta"] >= 5.0]) == 21, len(loaded)
        assert skipped["pct_delta below --min-delta"] == 19, skipped

    print("self-check OK (recovered slope %.4f, intercept %.4f, r %.4f)\n" % (slope, intercept, r))
    report(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", nargs="?", default=DEFAULT_PATH, help="battle_samples.jsonl (default: prefs dir)")
    ap.add_argument("--min-delta", type=float, default=0.0,
                    help="skip rows whose |pct_delta| is below this (default 0)")
    ap.add_argument("--self-check", action="store_true", help="run the assert-based self-test and exit")
    args = ap.parse_args()

    if args.self_check:
        self_check()
        return 0

    if not os.path.isfile(args.path):
        print("no sample log at %s" % args.path)
        print("Play a few battles with the mod installed (the recorder is always on), or pass a path.")
        return 1

    rows, skipped = load(args.path, args.min_delta)
    print("file: %s" % args.path)
    if skipped:
        print("skipped: " + ", ".join("%d %s" % (n, why) for why, n in sorted(skipped.items())))
    if not rows:
        print("no usable samples yet (0 rows with has_data and a residual).")
        return 1
    report(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
