# -*- coding: utf-8 -*-
"""Assert the mod version is consistent everywhere.

  python build/check_version.py

`src/meta.xml` <version> is the source of truth. This scans the repo for every
version reference that must track it and fails (exit 1) on any mismatch, printing
each offending file:line. It exists because the version is hand-edited in several
places at release time (see the wotmod-release skill) and drift slips through.

To avoid false positives on the *other* version numbers in the repo (the target
client 2.3.0.1, bundled OpenWG GameFace 1.1.6, etc.) this matches only patterns
that unambiguously carry THIS mod's version:

  * com.14th_ua.moe_calculator_<v>.wotmod          (the packaged filename)
  * MoECalculator-Setup-<v>.exe   (the installer filename)
  * MOD_VERSION = "<v>"            (mod_moe_calculator.py)
  * #define ModVersion "<v>"       (the .iss installer script)
  * version <v>                    (prose header, e.g. dist/INSTALL.txt)

The last (prose) pattern has a negative lookahead so it matches THIS mod's 3-part
version only, never the 4-part client version ("version 2.3.0.1").

New references written in any of these forms are picked up automatically. On top of
that, a small REQUIRED list names files that must carry at least one reference, so a
file silently LOSING its version reference also fails the check.

The hand-bumped consumer readme (dist/INSTALL.txt) lives under gitignored dist/,
which is otherwise skipped; it is scanned explicitly when present.

`.claude/skills/**/*.md` + `CLAUDE.md` are prose nothing else greps, so they
silently rot after a release or client upgrade -- both dirs are in _SKIP_DIRS
above so the core pass never scans them for old-version drift either. On top
of that, this file ALSO prints a fix-list (file:line + what's stale) for three
narrower signals: an old bundled vendor .wotmod name (compares against
installer/vendor/*.wotmod, id-only so a version-only bump isn't a false
positive -- catches a modssettingsapi->modmenu-style swap), an old
settingsVersion/SETTINGS_VERSION value (compares against the mod's own
source), and old atlas WxH dimensions (compares against the mod's own atlas
PNG, read via IHDR, only on lines mentioning "atlas"). Every one of these is
fail-soft: a mod without a vendor dep / settings panel / atlas just emits no
rows for that category, never an error.

Run `python check_version.py --selfcheck` to also exercise the stale-doc scan
logic against fixtures (no repo state needed).

Runs on Python 2.7 or 3.x (release tooling is 2.7; CI is 3.13).
"""
from __future__ import print_function

import os
import re
import sys

import meta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Directories not worth scanning (build output, VCS, vendored binaries, editor cfg).
# Also skip internal, non-shipped docs: `.claude` skill definitions carry illustrative
# version examples, and `TASKS` holds frozen historical planning notes that legitimately
# reference the version they shipped under -- gating either would force us to falsify history
# or churn example values every release. The gate covers SHIPPED references only (src/,
# installer/, INSTALL.md, README.md, dist/INSTALL.txt).
_SKIP_DIRS = {".git", "dist", "__pycache__", "node_modules", ".idea", ".vscode",
              "vendor", "assets", ".claude", "TASKS"}
# Only these extensions hold version references.
_SCAN_EXT = (".md", ".py", ".xml", ".iss", ".ps1", ".txt")

# Under a _SKIP_DIRS folder but scanned anyway (hand-bumped, drift-prone). Relative
# to ROOT; skipped silently when absent (dist/ is gitignored build output).
_EXTRA_FILES = ("dist/INSTALL.txt",)

# Each pattern captures a semver in group 1 that must equal the meta version. The mod id is
# matched via re.escape so any dots in it stay literal. These forms UNAMBIGUOUSLY carry THIS
# mod's version (a packaged/installer filename, a MOD_VERSION/ModVersion assignment), so they are
# scanned in every file.
# Version group allows an optional semver pre-release suffix (e.g. "-beta.0", "-rc.1")
# so a pre-release cut doesn't spuriously fail this gate.
_VER = r"(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)"

_PATTERNS = [
    re.compile(re.escape("com.14th_ua.moe_calculator") + r"_" + _VER + r"\.wotmod"),
    re.compile(re.escape("MoECalculator") + r"-Setup-" + _VER + r"\.exe"),
    re.compile(r'MOD_VERSION\s*=\s*"' + _VER + r'"'),
    re.compile(r'#define\s+ModVersion\s+"' + _VER + r'"'),
]

# The free-prose "version <v>" form is inherently ambiguous -- it also matches a DEPENDENCY
# version written the same way (e.g. "OpenWG version 1.1.6"), which would spuriously fail the
# gate, and it can't tell this mod's 3-part version from an unrelated one. So it is applied ONLY
# to the consumer-facing install docs, where "version <v>" means THIS mod's version by convention
# -- not to source, research notes, or other prose scattered across the repo. The (?<!\d\.) /
# (?!\.\d) guards keep it from matching a fragment of the 4-part client version ("2.3.0.1").
_PROSE_PATTERN = re.compile(r"(?<!\d\.)version\s+" + _VER + r"(?!\.\d)")
# Root-relative, forward-slashed. dist/INSTALL.txt is gitignored build output (scanned when present
# via _EXTRA_FILES); README.md / INSTALL.md are the shipped consumer docs.
_PROSE_FILES = frozenset(("README.md", "INSTALL.md", "dist/INSTALL.txt"))

# Files that MUST carry at least one version reference. Catches a file silently
# LOSING its reference (which would otherwise pass). Paths are ROOT-relative,
# forward-slashed. Entries under dist/ are checked only when the file exists
# (gitignored build output). Add your own consumer docs (INSTALL.md, etc.) here
# once they exist and carry a version reference.
_REQUIRED = (
    "src/res/scripts/client/gui/mods/mod_moe_calculator.py",
    "installer/moe_calculator-setup.iss",
    "installer/build_installer.ps1",
    "dist/INSTALL.txt",
)


def _iter_files():
    for dirpath, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for name in files:
            if name.endswith(_SCAN_EXT):
                yield os.path.join(dirpath, name)
    # Files under an otherwise-skipped dir that we still want checked.
    for rel in _EXTRA_FILES:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        if os.path.isfile(path):
            yield path


# --- stale-doc scan: .claude/skills/**/*.md + CLAUDE.md ---------------------
# Project skills and CLAUDE.md go stale after every release/client-upgrade because
# _iter_files() above skips `.claude` (see _SKIP_DIRS), so nothing else greps them
# for drift. This walks them separately with three narrow, unambiguous signals and
# prints a fix-list (not enforced per-file like _REQUIRED -- advisory, prose not code).

_VENDOR_WOTMOD_RE = re.compile(r"\b([A-Za-z0-9_.]+?)_(\d+(?:\.\d+)*)\.wotmod\b")
_SETTINGS_VERSION_DOC_RE = re.compile(r"(?:SETTINGS_VERSION|settingsVersion)\D{0,10}?(\d+)")
_ATLAS_DIMS_DOC_RE = re.compile(r"\b(\d{2,5})\s*[xX]\s*(\d{2,5})\b")
_OWN_WOTMOD_RE = re.compile(re.escape("com.14th_ua.moe_calculator") + r"_\d+\.\d+\.\d+\.wotmod")
_SETTINGS_VERSION_SRC_RE = re.compile(r"(?:SETTINGS_VERSION|settingsVersion)\s*[:=]\s*(\d+)")
# "current state" version/client pointers (e.g. "canonical value ... currently 4.0.1",
# "**Client:** WoT **EU 2.3.1.2**") -- deliberately keyed on these narrow, unambiguous
# markers so a legitimate historical changelog line ("bumped mod to WoT client EU 2.3.1.3
# (up from 2.3.1.2)") is never mistaken for a live pointer.
_CURRENT_MOD_VER_RE = re.compile(
    r"currently\s+\**(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)\**")
_CLIENT_HEADER_RE = re.compile(
    r"\*\*Client:?\*\*\s*WoT\s*\**EU\s*(\d+\.\d+\.\d+\.\d+)\**")


def _read_text(path):
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", "replace")
    except (IOError, OSError):
        return None


def _iter_doc_files():
    claude_md = os.path.join(ROOT, "CLAUDE.md")
    if os.path.isfile(claude_md):
        yield claude_md
    skills_dir = os.path.join(ROOT, ".claude", "skills")
    for dirpath, _dirs, files in os.walk(skills_dir):
        for name in files:
            if name.endswith(".md"):
                yield os.path.join(dirpath, name)


def _shipped_vendor_ids():
    """Vendor package ids actually bundled (installer/vendor/*.wotmod), keyed
    without their version so a plain version bump isn't mistaken for a package
    swap. Fail-soft: empty set if the mod bundles no vendor .wotmods."""
    vendor_dir = os.path.join(ROOT, "installer", "vendor")
    ids = set()
    if os.path.isdir(vendor_dir):
        for name in os.listdir(vendor_dir):
            m = _VENDOR_WOTMOD_RE.match(name)
            if m:
                ids.add(m.group(1))
    return ids


def _current_client_version():
    """Deploy-target client version from deploy.local.json's "version" key
    (the mod's own source-of-truth for "what the client actually is" -- see
    CLAUDE.md). Fail-soft: None if the file is absent/unparseable."""
    path = os.path.join(ROOT, "deploy.local.json")
    text = _read_text(path)
    if text is None:
        return None
    try:
        import json
        return json.loads(text).get("version")
    except ValueError:
        return None


def _current_settings_version():
    """SETTINGS_VERSION / settingsVersion currently defined in the mod's own
    source. Fail-soft: None if the mod has no MSA settings panel."""
    src_dir = os.path.join(ROOT, "src")
    if not os.path.isdir(src_dir):
        return None
    for dirpath, _dirs, files in os.walk(src_dir):
        for name in files:
            if not name.endswith(".py"):
                continue
            text = _read_text(os.path.join(dirpath, name))
            m = text and _SETTINGS_VERSION_SRC_RE.search(text)
            if m:
                return int(m.group(1))
    return None


def _current_atlas_dims():
    """(width, height) of the mod's own atlas PNG, read off the IHDR chunk
    directly (no Pillow dependency). Fail-soft: None if the mod has no atlas."""
    src_dir = os.path.join(ROOT, "src")
    if not os.path.isdir(src_dir):
        return None
    for dirpath, _dirs, files in os.walk(src_dir):
        for name in files:
            if "atlas" in name.lower() and name.lower().endswith(".png"):
                try:
                    with open(os.path.join(dirpath, name), "rb") as fh:
                        header = fh.read(24)
                except (IOError, OSError):
                    continue
                if len(header) == 24 and header[12:16] == b"IHDR":
                    import struct
                    return struct.unpack(">II", header[16:24])
    return None


def _scan_line(line, vendor_ids, settings_version, atlas_dims,
                mod_version=None, client_version=None):
    """Pure per-line check: returns a list of human-readable "what's stale"
    strings for one prose line. No disk I/O -- kept separate so _selfcheck can
    exercise it with a fixture string.

    NOTE: old-version detection is NOT duplicated here -- main()'s existing
    _iter_files()/_PATTERNS pass already covers old-version drift in shipped
    files; this scan only reaches the docs _iter_files() skips (.claude, and
    CLAUDE.md is scanned there too but the drift-specific bits below still add
    value on top)."""
    findings = []
    if vendor_ids:
        for m in _VENDOR_WOTMOD_RE.finditer(line):
            if _OWN_WOTMOD_RE.search(line):
                continue
            if m.group(1) not in vendor_ids:
                findings.append(
                    "unrecognized vendor wotmod '%s' (shipped: %s)"
                    % (m.group(0), ", ".join(sorted(vendor_ids))))
    if settings_version is not None:
        m = _SETTINGS_VERSION_DOC_RE.search(line)
        if m and int(m.group(1)) != settings_version:
            findings.append("settingsVersion %s (current %s)" % (m.group(1), settings_version))
    if atlas_dims is not None and "atlas" in line.lower():
        for m in _ATLAS_DIMS_DOC_RE.finditer(line):
            dims = (int(m.group(1)), int(m.group(2)))
            if dims != atlas_dims:
                findings.append("atlas dims %dx%d (current %dx%d)"
                                 % (dims[0], dims[1], atlas_dims[0], atlas_dims[1]))
    if mod_version is not None:
        m = _CURRENT_MOD_VER_RE.search(line)
        if m and m.group(1) != mod_version:
            findings.append("mod version %s (current %s)" % (m.group(1), mod_version))
    if client_version is not None:
        m = _CLIENT_HEADER_RE.search(line)
        if m and m.group(1) != client_version:
            findings.append("client version %s (current %s)" % (m.group(1), client_version))
    return findings


def _scan_stale_docs():
    """Fix-list rows (file, line, what) for every stale reference found in
    .claude/skills/**/*.md + CLAUDE.md. `.claude` is in _SKIP_DIRS above (by
    design -- see its comment), so the core _PATTERNS/mismatches pass never
    reaches these files; this is the only place a stale "currently X.Y.Z" /
    "**Client:** WoT **EU x.x.x.x**" pointer in them gets caught."""
    vendor_ids = _shipped_vendor_ids()
    settings_version = _current_settings_version()
    atlas_dims = _current_atlas_dims()
    mod_version = meta.read_version()
    client_version = _current_client_version()
    rows = []
    for path in _iter_doc_files():
        text = _read_text(path)
        if text is None:
            continue
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        for lineno, line in enumerate(text.splitlines(), 1):
            for what in _scan_line(line, vendor_ids, settings_version, atlas_dims,
                                    mod_version, client_version):
                rows.append((rel, lineno, what))
    return rows


def main():
    expected = meta.read_version()
    mismatches = []
    counts = {}  # rel path -> number of version references found
    found_any = False
    for path in _iter_files():
        try:
            with open(path, "rb") as fh:
                text = fh.read().decode("utf-8", "replace")
        except (IOError, OSError):
            continue
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        # Unambiguous patterns everywhere; the ambiguous prose form only in the consumer docs.
        pats = _PATTERNS + [_PROSE_PATTERN] if rel in _PROSE_FILES else _PATTERNS
        for lineno, line in enumerate(text.splitlines(), 1):
            for pat in pats:
                for m in pat.finditer(line):
                    found_any = True
                    counts[rel] = counts.get(rel, 0) + 1
                    if m.group(1) != expected:
                        mismatches.append((rel, lineno, m.group(1), line.strip()))

    # A required file that carries NO reference (e.g. an edit dropped it silently).
    # dist/INSTALL.txt is only required when it exists (gitignored build output).
    missing = [rel for rel in _REQUIRED
               if not counts.get(rel)
               and (not rel.startswith("dist/")
                    or os.path.isfile(os.path.join(ROOT, rel.replace("/", os.sep))))]

    if mismatches:
        print("Version mismatch (src/meta.xml says %s):" % expected)
        for rel, lineno, got, line in mismatches:
            print("  %s:%d  found %s  ->  %s" % (rel, lineno, got, line))
        return 1
    if missing:
        print("Missing version reference (src/meta.xml says %s) in required files:"
              % expected)
        for rel in missing:
            print("  %s  (expected at least one %s reference)" % (rel, expected))
        return 1
    if not found_any:
        print("WARNING: no version references matched any pattern -- "
              "check_version.py may be stale.")
        return 1

    stale_docs = _scan_stale_docs()
    if stale_docs:
        print("Stale docs -- review these:")
        for rel, lineno, what in stale_docs:
            print("  %s:%d  %s" % (rel, lineno, what))
        return 1

    print("OK: all version references match src/meta.xml (%s)." % expected)
    return 0


def _selfcheck():
    """Assert every pattern captures a pre-release suffix in full, and still
    captures a plain X.Y.Z with no regression. Not part of the exit-code gate.

    Sample lines are built via %-formatting (not written as literals) so this
    file's own source doesn't itself look like a version reference to scan().
    """
    pre = "3.1.4" + "-beta.0"
    samples = [
        (_PATTERNS[0], "com.14th_ua.moe_calculator_%s.wotmod" % pre),
        (_PATTERNS[1], "MoECalculator-Setup-%s.exe" % pre),
        (_PATTERNS[2], 'MOD_VERSION = "%s"' % pre),
        (_PATTERNS[3], '#define ModVersion "%s"' % pre),
        (_PROSE_PATTERN, "version %s" % pre),
    ]
    for pat, line in samples:
        m = pat.search(line)
        assert m and m.group(1) == pre, (pat.pattern, line, m)
    # No-suffix case still parses, and the prose guard still rejects a 4-part version.
    plain = "3.1.3"
    assert _PATTERNS[0].search(
        "com.14th_ua.moe_calculator_%s.wotmod" % plain).group(1) == plain
    assert _PROSE_PATTERN.search("version %s" % plain) is not None
    assert _PROSE_PATTERN.search("version 2.3.0.1") is None
    print("selfcheck OK: pre-release suffix and no-suffix forms both parse.")

    # Stale-doc scan (_scan_line): a known-old vendor wotmod name and a known-old
    # settingsVersion/atlas dims each show up in the fix-list; a clean line
    # (matching current values) produces nothing; missing category data never flags.
    stale_vendor_line = "Depends on " + "aslain.modssettingsapi_1.7.1" + ".wotmod for settings."
    settings_line = "SETTINGS_VERSION" + " 23 is what ships today."
    atlas_line = "The atlas is " + "4096x5152" + " at build time."
    clean_line = "See MOD_VERSION" + " = \"2.0.0\" in the mod entry point."

    found = _scan_line(stale_vendor_line, {"aslain.modmenu"}, None, None)
    assert any("aslain.modssettingsapi_1.7.1.wotmod" in f for f in found), found

    found = _scan_line(settings_line, set(), 24, None)
    assert any("23" in f for f in found), found

    found = _scan_line(atlas_line, set(), None, (4096, 5076))
    assert any("4096x5152" in f for f in found), found

    assert _scan_line(clean_line, set(), None, None) == []
    assert _scan_line(stale_vendor_line, set(), None, None) == []
    assert _scan_line(settings_line, set(), None, None) == []
    assert _scan_line(atlas_line, set(), None, None) == []

    stale_mod_line = "the live canonical value is (" + "currently 4.0.1" + ", client target EU 2.3.1.3)."
    stale_client_line = "**Client:** WoT **EU " + "2.3.1.2" + "**."
    changelog_line = "bumped mod to WoT client EU " + "2.3.1.3" + " (up from 2.3.1.2)"

    found = _scan_line(stale_mod_line, set(), None, None, mod_version="5.0.0")
    assert any("mod version 4.0.1" in f for f in found), found

    found = _scan_line(stale_client_line, set(), None, None, client_version="2.4.0.0")
    assert any("client version 2.3.1.2" in f for f in found), found

    # A historical changelog mention (no "currently"/"**Client:**" marker) never flags --
    # that's the whole point of keying on those narrow markers.
    assert _scan_line(changelog_line, set(), None, None, mod_version="5.0.0",
                       client_version="2.4.0.0") == []

    print("selfcheck OK: stale-doc scan flags known-old values, "
          "skips categories the mod doesn't have.")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
        sys.exit(0)
    sys.exit(main())
