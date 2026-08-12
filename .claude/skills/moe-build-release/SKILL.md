---
name: moe-build-release
description: Use when packaging, deploying, testing, hot-reloading, versioning, or releasing the 14th_ua MoE Calculator — which files carry the version, what each build/ script and installer file does, the garage-vs-battle hot-reload split, the debug REPL wiring, and the dev-tools inventory. For feature internals see moe-garage / moe-battle.
---

# MoE Calculator — build, deploy, version & dev loop

Reusable mechanics live in `wotmod-build-deploy`, `wotmod-release`, and `wotmod-debug-repl`;
this skill is the concrete file list and command set. **Two Pythons:** package with
`C:\Python27\python.exe` (bytecode is version-locked), test/dev-tool with Python 3.13.

## Version files (bump together; `src/meta.xml` is canonical)

`build/check_version.py` enforces consistency (`<py> build/check_version.py`, exit 1 on drift):

| File | Reference |
|---|---|
| `src/meta.xml` | `<version>X.Y.Z</version>` — **source of truth** |
| `src/res/scripts/client/gui/mods/mod_moe_calculator.py` | `MOD_VERSION = "X.Y.Z"` |
| `installer/moe_calculator-setup.iss` | `#define ModVersion "X.Y.Z"` + `#define ModWotmod "…_X.Y.Z.wotmod"` |
| `installer/build_installer.ps1` | `$ModWotmod = …com.14th_ua.moe_calculator_X.Y.Z.wotmod` |
| `INSTALL.md` | `MoECalculator-Setup-X.Y.Z.exe`, `…_X.Y.Z.wotmod` |
| `dist/INSTALL.txt` | prose `version X.Y.Z` (gitignored build output; checked when present) |

_`X.Y.Z` is illustrative — the live canonical value is in `src/meta.xml` (currently 2.0.0)._

- `README.md` uses `<version>` placeholders (no hard-coded number). `adapter/moe_wgapi.py`'s
  `_AGENT` string carries the project URL (no version number — nothing cosmetic to bump there).
- The **client** version `2.3.1.1` is deliberately excluded from the check (a `(?!\.\d)` lookahead skips the 4-part client version).

## Release must stay silent (no unconditional logging)

A shipped build must write **nothing** to WoT's `python.log` in normal operation — those logs
are world-readable on every player's machine. Never call `debug_utils.LOG_NOTE` (or `LOG_NOTE`
re-exported from `_compat`) directly for informational output. Route every chatty/internal note
(lifecycle, placement, data payloads, fetch lists) through **`_compat.LOG_DEBUG`**, which is
gated on **`_compat.DEBUG`** (ships **`False`**; flip `True` only for local dev, never commit it
`True`). Genuine failures go through the always-on, path-safe `LOG_CURRENT_EXCEPTION`.

`tests/test_logging_gate.py` enforces this: it fails the build if `DEBUG` is committed `True` or
if any module outside `_compat.py` grows a raw `LOG_NOTE(` call site. **Run the full pytest suite
before every release** (it is part of the gate, alongside `check_version.py`), and eyeball
`python.log` after an in-game smoke test — it should stay clean.

## build/ scripts

- **`build_wotmod.py`** — **Python 2.7 only** (asserts). Reads `meta.xml`, compiles `.py`→`.pyc`
  (drops `.py`, skips `__pycache__`), zips `meta.xml` + `res/` as **`ZIP_STORED`** →
  `dist/com.14th_ua.moe_calculator_<version>.wotmod`. Non-`.py` files (fonts/PNG/JSON) are copied verbatim.
  **Self-enforces `-OO`** (`_ensure_optimized`, since 1cd8c27): if `sys.flags.optimize < 2` it
  re-execs *this script* (not `sys.argv`, so `deploy_wotmod.py`'s in-process `main()` isn't
  restarted) in an `-OO` subprocess, so a plain `python build/build_wotmod.py` ships
  docstring-stripped `.pyc` **by default** — the harness "Ship docstring-stripped bytecode"
  standard. (`-OO` also drops `assert`, so keep asserts to tests/dev tools, never load-bearing
  in shipped src.)
  **Single build, no arguments** — MoE thresholds come from the official WG API at runtime
  (`adapter/moe_wgapi.py`), so GitHub and WGMods ship the identical `.wotmod`.
- **`deploy_wotmod.py`** — Python 2.7. Cleans old `…_[0-9]*.wotmod` from `mods/<ver>/` + loose
  `res_mods` leftovers, calls `build_wotmod.main()`, copies in. Reads `deploy.local.json` if no args.
  `--clean-overlay` removes the hot-reload overlay. **Needs `WorldOfTanks.exe` closed** (`wgc` ok).
- **`build_moe_zip.py`** — any Python. Builds `dist/MoECalculator_<version>.zip` = bilingual
  `readme.txt` (from `installer/readme.moe.txt`, `{VERSION}` substituted, CRLF) + the mod `.wotmod`
  + all `installer/vendor/*.wotmod` under `mods/2.3.1.2/`. Manual upload to wgmods.net. Holds `CLIENT_VERSION="2.3.1.2"`.
  Packages whatever `.wotmod` is in `dist/` — the same single build the GitHub installer uses.
- **`check_version.py`** — the version gate above. **`clean_dist.py`** — prunes non-current release artifacts from `dist/` (`--dry-run`).

## installer/

- **`moe_calculator-setup.iss`** — Inno Setup 6. Detects WoT root, resolves client version, installs
  to `mods\<version>\`, bundles OpenWG from `installer/vendor/` **only if absent**
  (`NeedOpenWg`, `uninsneveruninstall`), cleans old builds, WoT-running guard, GitHub
  Atom-feed self-update. Repo `drizzer14/moe-calculator`, base name `MoECalculator-Setup`.
- **`build_installer.ps1`** — preflights the built `.wotmod` + vendor dep, finds `ISCC.exe`, compiles → `dist/MoECalculator-Setup-<version>.exe`.
- **`readme.moe.txt`** — bilingual EN/UA readme for the wgmods zip (the only readme template; the old `readme.wgmods.txt` stub was deleted). **`installer/vendor/`** — `net.openwg.gameface_1.1.6.wotmod` + `aslain.modssettingsapi_1.6.4.wotmod` + `me.poliroid.modslistapi_1.7.8.wotmod`.

## Hot-reload (the split that bites)

- **Garage widget hot-reloads:** `<py3> tools\dev\sync_gameface.py "D:/Games/World_of_Tanks_EU" 2.3.1.2`
  copies only the Gameface JS/CSS/assets into `res_mods`, then toggle Tech-Tree↔Garage to re-inject. No relaunch.
- **The in-battle registered WINDOW does NOT hot-reload** — its resources pin at client launch;
  reopen and `Window.reload()` both serve the launch-time cached document. **Every CSS/JS tweak to
  `MoEBattle.*` needs a full client relaunch.** Gate the commit on the in-game sign-off (deploy → verify live → commit).
- Clean the `res_mods` overlay before any ship-verification — a stale overlay shadows a fresh packaged build.

## Dev loop / REPL

- Live introspection: build the slim debug package (`tools/dev/build_debug_wotmod.py` →
  `com.14th_ua.moe_calculator_debug.wotmod`, TCP **:2224**), then `<py3> tools\dev\repl_client.py "<expr>"`.
  Multiline needs `execfile(r'<abs path>')`. See `wotmod-debug-repl`.
- Decompiled client source for symbol hunting: `C:\Users\Dmytro Vasylkivskyi\wot-eu\source\res\scripts\client\`.
- **`tools/dev/` inventory:** `sync_gameface.py` (hot-reload), `gen_checker.py` (battle dither PNG),
  `swf_font_to_ttf.py` / `swf_probe.py` (extract `MoEBattle.ttf` from `fontlib.swf`),
  `gen_overlay_tuner.ps1` / `gen_icon_picker.ps1` (browser calibration artifacts → `TASKS/refs/`),
  `mod_moe_calculator_debug.py` (Py2-only REPL server), and the `probe_*` live-discovery scripts.

## Release state

**v0.1.0 through v1.8.0 are published** on `github.com/drizzer14/moe-calculator` (`origin/main`);
**v1.8.0 (2026-08-03) was the prior Latest**, carrying the in-battle progress bar's Ctrl+drag
reposition + Bar Position X/Y fields, a configurable Hold Duration, the Moving Average bar's
ETA-in-battles readout, the relabelled Transitions master, and the shrunk Large mode.

**2.0.0 is a game-upgrade release (staged, not yet published)**: retargets the mod to WoT
client **EU 2.3.1.1** (#910, up from 2.3.1.0 #903) — major bump per convention, **zero
divergences found and no functional/code changes**. The `upgrade-analyzer` pass resolved all
198 gathered seams (monkey-patch targets, subscribed Events, Wulf ViewModel API, `img://` art
paths) present and unchanged in the new client's packed `.pyc`; vendor deps (OpenWG GameFace
1.1.6, Aslain ModsSettingsAPI 1.6.4, Mods List API 1.7.8) kept unchanged, pending a live
CONFIRM before publishing that none terminates the client at init on 2.3.1.1. The **1.0.0**
release retargeted the mod to WoT client **2.3.1.0** (major bump) and added the Alt-key peek
mode + Counted Assistance row; **1.1.0**
is a patch-level polish of the in-battle overlay row/backdrop alignment (shipped as a minor bump by
choice); **1.2.0** is a minor bump carrying the in-battle MoE-projection accuracy work (smooth
probit curve + self-calibrating EWMA `k`) plus the R3 row-backdrop fix — all committed after the
v1.1.0 tag but unreleased until then; **1.3.0** is a minor bump carrying the settings-surface
overhaul — migrated to Aslain **ModsSettingsAPI** + bundled **Mods List API** (settings now surface
in WoT's in-game "Modification list" window), a redesigned **two-column MSA settings panel**, and
resolution-correct **high-DPI/4K garage widget** size + position (plus an enlarged MoE award tooltip);
**1.3.1 (2026-07-19)** is a patch; **1.4.0 (2026-07-20)** is a minor bump carrying **garage widget
drag-to-reposition** (Ctrl+drag + numeric X/Y position steppers + a "Follow Carousel" toggle + a
reset command — moves only, no resizing) and **MSA settings-value migration** so a `SETTINGS_VERSION` bump (now **v5**) no longer
wipes users' saved settings (migrates the persisted Aslain ModsSettingsAPI values across the bump,
fail-soft to a fresh install); **1.5.0 (2026-07-25)** is a minor bump carrying in-battle
MoE-projection accuracy work — the damage→percent mapping moved from a single global
least-squares normal `(mu, sigma)` over the four threshold stops to an **exact-at-stops piecewise**
normal fit. Least squares passed through *none* of the stops (live-EU residuals sign-identical on
every tank: D1 −3.1, D2 +1.6, D3 +0.9, D100 −0.25 percentile points), so the 1-mark stop read
~61.9% instead of 65% and the slope just above a mark ran ~50% too steep — a **slope** bias the
`pre_percentile` anchor cannot cancel (it cancels only a level bias), so the readout started right
and drifted as damage accrued. `_fit_from_thresholds` now returns the usable stops as ascending
`[(damage, z), …]` and `_smooth_percent` solves the bracketing segment's `(mu, sigma)` exactly
through both stops, so `f(D_i) == 100*p_i` at every stop while the curve still rides WG's normal
shape between them; the end segments extend for both tails (no truncation above D100). Unusable WG
stops are dropped **individually** (`d <= 0`, or `d <=` the last kept `d`), so a bad interior stop
costs resolution, not `has_data`; **1.6.0 (2026-07-29)** is a minor bump carrying **two new
mutually exclusive centre-screen in-battle progress bars**, both **off by default** behind a new
independent `progress_bar_enabled` MSA master ("Progress Bar", its own column-1 group, never a
child of the In-Battle Widget) with an int-valued `progress_bar_variant` RadioButtonGroup child
(`0 = Moving Average`, the default, so an existing user lands on the original bar; `1 = Damage
Efficiency`). **Moving Average** (`MoEProgress.js/.css` + `MoEProgressView.html`,
`bridge/progress_view.py`, `res_map/MoEProgressView.json`) plots the career projected average
between the held mark and the next mark's requirement, plus this battle's signed delta; it is gated
on `model.has_baseline`, so it stays hidden in replays and after a relogin until a Garage visit
populates the baseline. **Damage Efficiency** (`MoEEfficiency.js/.css` + `MoEEfficiencyView.html`,
`bridge/efficiency_view.py`, `res_map/MoEEfficiencyView.json`) plots this battle's damage against
all four mark requirements on four equal quarters (`EFFICIENCY_BAR_STOPS = (0, 25, 50, 75, 100)`)
and auto-shows only on a new high-water damage mark; it has **no** baseline gate, only `hasData`.
`battle_bridge._window_gates()` is the single place that decides who may be up and opens **at most
one** centre bar — the only reason both stylesheets can own `#moe-bar-root` / `.mp-*` without
colliding. Shared transient behaviour (the fade/hold/fade life cycle, `HOLD_MS = 5000`) lives in
`MoEBarTransient.js`, instantiated once per document; **Alt is an ADDITIVE show trigger** for both
bars and is deliberately NOT gated by the overlay's "Show on Alt Key", and the bars' centre-screen
position is fixed, not configurable. `SETTINGS_VERSION` went **5 → 10** across the feature's
iterations (6 = the checkbox, 7 = a column-3 relayout, 8 = its revert plus the "Next Mark Progress
Bar" label rename, 9 = the re-parent into its own group + the variant radio, 10 = dropping the
radio's own "Bar Type" label row) — 6–9 shipped to nobody but the maintainer's install. Saved
values migrate across every step and no `varName` was renamed. Cosmetics: the Damage Efficiency
delta renders **without parentheses** (Moving Average and the corner overlay keep theirs) and
caption centring was fixed to sit on the numeral, not the row. Player docs were **resynced** this
release (`README.md` / `INSTALL.md` / `installer/readme.moe.txt`, both language halves), and
`installer/readme.wgmods.txt` was **DELETED** as a superseded stub — `readme.moe.txt` is now the
single portal-readme template, and `build/build_moe_zip.py` was already its only consumer.
**1.7.0 (2026-08-01)** is a minor bump carrying in-battle MoE-projection accuracy work plus a
full MSA panel restructure. The damage→percent mapping moved **off** 1.5.0's exact-at-stops
piecewise normal fit onto **WG's own LINEAR interpolation over the 8 published anchors plus a
(0,0) origin** — no z-space, no probit; the old normal fit's 11.9pp error was localised below the
lowest stop. Both centre bars gained a **Large** size mode (the `progressSize` radio, labelled
"Scale", options Default/Large). The progress bar's enter/exit fade+slide can now be switched off
per trigger area (`progress_transitions_enabled`/`_events`/`_manual`). The interface-scale-1
caption-drift fix landed on the efficiency bar then was mirrored onto the moving-average bar. A
died/survived flag was added to the battle-sample log to split the credit shortfall
(dev/sample-corpus only, not user-facing). The MSA panel itself was restructured into three
column-1 categories (Battle Calculator / Battle Progress / Transitions) with bold `<b>` headers and
`Empty` spacers; column 2 split into Garage Widget + Layout; every master now reads "Enabled"; new
progress-visibility flags `progress_show_events` / `_alt_key` / `_always` were added, with "Always"
greying the other two via an MSA multi-condition AND gate; both radios went standalone and inline;
the Mode radio was reordered so Damage Efficiency is index 0 and the new default; and
`counted_assistance_enabled` now defaults **True**. `SETTINGS_VERSION` went **12 → 14** (v1.6.0
shipped 10). A follow-up fix (`_migrate_pre_v13_variant` in `bridge/mod_settings.py`) flips a
pre-v13 store's `progress_bar_variant` raw int 0↔1 during `register()`'s migration branch, keyed
on the absence of the v13-introduced `progress_show_events` key (no stored version int to compare
against directly), so an upgrading v1.6.0 user keeps the bar they actually chose across the
reorder — no `SETTINGS_VERSION` bump of its own. Player docs (`README.md`, `INSTALL.md`,
`installer/readme.moe.txt`) were reconciled against the v14 panel in both EN and UA halves.
Both channels now ship the **same single build** (WG-API threshold source): the GitHub release
carries `MoECalculator-Setup-<ver>.exe` + the bare `.wotmod`, and `MoECalculator_<ver>.zip`
(same `.wotmod` + vendor deps) is uploaded manually to
[wgmods.net/7745](https://wgmods.net/7745/). Since **v0.3.0** the installer and the zip also
bundle **ModsSettingsAPI** (`installer/vendor/aslain.modssettingsapi_1.6.4.wotmod` — migrated
from izeberg 1.7.0 in v1.3.0) alongside OpenWG GameFace, plus **Mods List API**
(`installer/vendor/me.poliroid.modslistapi_1.7.8.wotmod`, added in v1.3.0) which surfaces the
settings in the in-game "Modification list" window. The installer self-update reads the GitHub Atom
feed, so keep the `vX.Y.Z` tag + `MoECalculator-Setup-<ver>.exe` asset-name convention. Follow
`wotmod-release` for the bump→tag→build→publish flow.

**Every release cut MUST reconcile the player docs** — `README.md`, `INSTALL.md` and
`installer/readme.moe.txt` — against the user-facing surface shipped since the last tag: new or
renamed settings controls, changed defaults, new widgets. Walk `git log <lasttag>..HEAD` for those
three, and apply **every** edit to **BOTH language halves** of the bilingual files (EN + UA). This
is required, same as bumping the version files: player docs have silently missed two feature
releases (1.4.0's garage drag-to-reposition, 1.6.0's two centre-screen bars) precisely because no
step checked them.

**Every release cut MUST refresh this "Release state" prose** to the newly published version —
promote it to "current Latest", add the prior version to the history line, and correct the
canonical `src/meta.xml` value noted above. Treat this edit as a required, non-optional step of
the release, same as bumping the version files. **Do NOT** end the post-release summary with a
reminder to manually upload the zip to wgmods — the maintainer already knows the zip is a manual
upload and has asked not to be reminded.

**GitHub release title = `vX.Y.Z` (v-prefixed), strictly.** Both the tag AND the release title
are `vX.Y.Z` (e.g. `v1.3.0`) — never the bare `X.Y.Z`. Every prior release (v0.1.0 … v1.3.0)
follows this. Create with `gh release create vX.Y.Z --title "vX.Y.Z" …`, then verify
`gh release view vX.Y.Z --json name --jq '.name'` prints `vX.Y.Z`; fix drift with
`gh release edit vX.Y.Z --title "vX.Y.Z"`.
