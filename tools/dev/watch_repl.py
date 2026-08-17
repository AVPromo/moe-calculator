#!/usr/bin/env python3
"""DEV: continuously poll the live REPL and log every change with a timestamp.

For time-sensitive captures (e.g. a ~30s battle countdown) where a human-timed
before/after poll would miss the window: start this BEFORE the action, then just
play and act — it retries the socket until the client answers, polls on a short
interval, and logs the exact tick where the reply changes.

Reuses repl_client.py's transport (one command per fresh connection) — does not
reimplement the socket protocol.

    python tools/dev/watch_repl.py "<python-expr-or-statements>" [--port 2224] [--interval 0.5] [--out logfile]
    python tools/dev/watch_repl.py --selftest

Example (bar-hide investigation): probe open_overlays/windowStatus/showingStatus/
has_placed/_last_good/vm_visible; setup lines exec silently, the FINAL line must be a
bare expression (not print(...)) so its repr is what gets echoed back each tick —

    python tools/dev/watch_repl.py "import moe_calculator.bridge.battle_bridge as bb
from moe_calculator.bridge import progress_view, efficiency_view
host = progress_view._host if progress_view.active_view() else efficiency_view._host
active = host.active_view()
w = host._active[0] if host._active else None
\"open=%r ws=%r ss=%r placed=%r last_good=%r vis=%r\" % (bb._open_overlays, (w.windowStatus if w else None), (w.showingStatus if w else None), host.has_placed(), host._last_good, (active.viewModel._getBool(0) if active else None))"

Ctrl-C to stop; the log is flushed/closed cleanly.
"""
import argparse
import time
from datetime import datetime

import repl_client


def poll_once(snippet):
    """Send `snippet` the way `repl_client.py --file` does: one line per command over ONE
    connection (shared local_vars), and return the LAST line's echoed reply. Setup lines
    (imports/assignments) exec silently with no echo; only a final bare expression's repr
    comes back non-empty."""
    commands = repl_client.commands_from_lines(snippet.splitlines())
    return repl_client.run(commands)[-1][1]


def detect_change(prev, reply):
    """Pure change-detection: True if `reply` differs from `prev` (None prev = baseline, no change)."""
    return prev is not None and reply != prev


def watch(snippet, port, interval, out_path):
    repl_client.PORT = port
    prev = None
    log = open(out_path, "a", encoding="utf-8")
    try:
        last_wait_print = 0
        while True:
            try:
                reply = poll_once(snippet)
            except (ConnectionRefusedError, OSError):
                now = time.time()
                if now - last_wait_print > 3:
                    print("waiting for client on 127.0.0.1:%d ..." % port)
                    last_wait_print = now
                time.sleep(interval)
                continue

            ts = datetime.now().isoformat(timespec="milliseconds")
            lines = []
            if detect_change(prev, reply):
                lines.append(">>> CHANGED")
            lines.append("%s | %s" % (ts, reply))
            text = "\n".join(lines)
            print(text)
            log.write(text + "\n")
            log.flush()
            prev = reply
            time.sleep(interval)
    finally:
        log.close()


def _selftest():
    assert detect_change(None, "a=1") is False, "first reply is baseline, not a change"
    assert detect_change("a=1", "a=1") is False, "identical reply is not a change"
    assert detect_change("a=1", "a=2") is True, "differing reply must be flagged changed"
    print("selftest OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("snippet", nargs="?", help="python expr/statements to run each tick (must print one line)")
    ap.add_argument("--port", type=int, default=2224)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--out", default="watch_repl.log")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        _selftest()
        return
    if not args.snippet:
        ap.error("snippet is required unless --selftest")

    try:
        watch(args.snippet, args.port, args.interval, args.out)
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
