# -*- coding: utf-8 -*-
"""Engine-shim + best-effort guard helpers shared across the adapter/bridge layers.

`debug_utils` is a game symbol: it exists in the running client but not under the
Python 3 test interpreter. Rather than copy-paste the guarded fallback import in
every module, they import `LOG_CURRENT_EXCEPTION` / `LOG_DEBUG` / `LOG_PROD` from here --
one place that resolves the real thing in-client and degrades to a no-op out of client (so
the engine-free helper modules still import under pytest). `LOG_DEBUG` additionally gates
all verbose diagnostics behind the `DEBUG` release switch so a shipped build stays silent;
`LOG_PROD` is the always-on low-volume counterpart. `LOG_CURRENT_EXCEPTION` is re-implemented
here (not re-exported from `debug_utils`) so every logged traceback is path-scrubbed before it
reaches a player's python.log.

`_safe` / `_safe_int` are the read-side guard idiom (run a getter, log + fall back to a
default on any failure) lifted here so more than one module can share them.

Adapter/bridge only -- the engine-free `domain/` layer must NOT import this. 2/3-compatible.
"""
import re
import traceback

# RELEASE SWITCH. Verbose diagnostics (lifecycle, placement, data payloads) go through
# LOG_DEBUG, which writes to WoT's python.log ONLY when this is True. A shipped build MUST
# leave it False so the release stays quiet -- unconditional notes have no place in a player's
# log. Flip to True ONLY for local dev and NEVER commit it True (tests/test_logging_gate.py
# fails the build if you do). Genuine errors are reported separately through the always-on,
# path-safe LOG_CURRENT_EXCEPTION; low-volume once-per-lifecycle markers go through the
# always-on LOG_PROD instead.
DEBUG = False

try:
    from debug_utils import LOG_NOTE, LOG_ERROR
except Exception:
    def LOG_NOTE(*args, **kwargs):
        pass

    def LOG_ERROR(*args, **kwargs):
        pass


def LOG_DEBUG(*args, **kwargs):
    """Gated verbose note: forwards to LOG_NOTE only when DEBUG is True, else a no-op.

    Use this for ANYTHING informational or internal (payloads, lists, lifecycle, placement) so
    the release build stays silent. Reserve LOG_CURRENT_EXCEPTION for real failures. Read DEBUG
    off the module at call time (not captured) so tests can toggle it via monkeypatch."""
    if DEBUG:
        LOG_NOTE(*args, **kwargs)


def LOG_PROD(*args, **kwargs):
    """Always-on, low-volume production diagnostic -- unlike LOG_DEBUG, this fires in a
    shipped build regardless of DEBUG. Reserve for genuine once-per-lifecycle-event markers
    (mod version/install, a listener re-arm, a sub-view placement decision, a settings
    migrate/register) -- never a per-refresh or per-selection line. Must stay free of
    filesystem paths, usernames, and install dirs since it ships in every build. No-op when
    debug_utils is unavailable (dev/test)."""
    LOG_NOTE(*args, **kwargs)


# Anchor each `File "..."` frame on its scripts/client/ segment (case-insensitive, \- or
# /-separated) and keep only the mod-relative tail (+ the line/func info outside the quotes,
# untouched) -- this drops the drive letter, the player's `Users\<name>`, and the .wotmod
# install path ahead of it.
_SCRIPTS_CLIENT_RE = re.compile(
    r'File "[^"]*?[\\/]scripts[\\/]client[\\/]([^"]+)"',
    re.IGNORECASE,
)

# Fallbacks for a frame with NO scripts/client anchor (e.g. a WG-shipped module under
# res/scripts/common/, or a path mentioned in the exception message itself): strip any
# remaining absolute path down to its basename. Each requires its own prefix (a drive
# letter, a UNC host, a leading slash) so it can never re-match the separator-less tail the
# pass above already produced.
_WIN_ABS_PATH_RE = re.compile(r'[A-Za-z]:[\\/][^"\r\n]*')
_UNC_ABS_PATH_RE = re.compile(r'\\\\[^"\r\n]*')
_POSIX_ABS_PATH_RE = re.compile(r'(?<![\w:])/[^"\r\n]*')


def _basename(match):
    return match.group(0).replace('\\', '/').rsplit('/', 1)[-1]


def _scrub_paths(text):
    """Scrub filesystem paths out of `text` (a formatted traceback, typically) before it's
    logged. Pure stdlib re, no game imports -- unit-tests with the game closed. Stance:
    over-scrub rather than risk a leak. Non-path text (exception type, message) passes
    through unchanged."""
    text = _SCRIPTS_CLIENT_RE.sub(lambda m: 'File "%s"' % m.group(1), text)
    text = _WIN_ABS_PATH_RE.sub(_basename, text)
    text = _UNC_ABS_PATH_RE.sub(_basename, text)
    text = _POSIX_ABS_PATH_RE.sub(_basename, text)
    return text


def LOG_CURRENT_EXCEPTION():
    """Path-safe drop-in for `debug_utils.LOG_CURRENT_EXCEPTION` -- same zero-arg signature
    (every bare `except:` call site across the mod calls this, unchanged), but the formatted
    traceback is scrubbed of the player's absolute install path/username before it reaches
    python.log. Never raises out of an except block: a scrub/log failure is swallowed."""
    try:
        LOG_ERROR(_scrub_paths(traceback.format_exc()))
    except Exception:
        pass


def _safe(fn, default):
    """Call `fn`; return its value, or `default` on None / any exception (logged)."""
    try:
        value = fn()
        return default if value is None else value
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return default


def _safe_int(fn, default):
    """Call `fn` and coerce to int; return `default` on None / any exception (logged).
    The int() runs INSIDE the guard, so a non-coercible return (a string, an object)
    falls back to `default` rather than raising through this fail-soft helper."""
    return _safe(lambda: int(fn()), default)
