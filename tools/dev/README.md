# Dev tools (WoT 2.3.1.0)

In-game introspection + the real dev loop for this mod. **Not shipped** with the mod.
See the harness skills `wotmod-build-deploy` and `wotmod-debug-repl` for the generic
pattern behind these scripts.

## Environment (this PC)
- WoT install: `D:/Games/World_of_Tanks_EU`, version **2.3.1.0**. OpenWG Gameface installed.
- **Python 2.7.18** at `C:\Python27\python.exe` — packaging only (compiles `.pyc`; bytecode is 2.7-locked).
- **Python 3.13** at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe` — runs pytest + the REPL client.
- Git at `C:\Program Files\Git\cmd\git.exe`, `core.longpaths=true` (needed for decompiled clones).

## The dev loop (WoT 2.x loads ONLY `.wotmod`)
Loose `res_mods\<version>\scripts` does **not** load in 2.x, and `res_mods` outranks `.wotmod`
(a stale loose copy SHADOWS the package → client ignores the mod). So always:

```
# 1) close the WoT client (file locks); then build+deploy the real mod:
& "C:\Python27\python.exe" build\deploy_wotmod.py "D:/Games/World_of_Tanks_EU" 2.3.1.0
# 2) relaunch the client. (OpenWG may auto-restart once when res_map changes.)
```
`deploy_wotmod.py` auto-cleans old `com.14th_ua.moe_calculator_[0-9]*.wotmod` and loose leftovers.

### Hot-reload loop for JS/CSS-only changes (NO relaunch)
`coui://gui/...` resolves through a merged FS where `res_mods/<version>/` outranks
the `.wotmod`, and the hangar sub-view re-fetches our assets each time its document
is rebuilt. So for **visual-only** (MoECalculator.js/.css) iteration:
```
# client may stay running:
& "<py3>" tools\dev\sync_gameface.py "D:/Games/World_of_Tanks_EU" 2.3.1.0
# then in-game: switch to another screen (e.g. Tech Tree) and back to the Garage.
```
This is ONLY for front-end assets. Python (mount/data) changes still need
build+deploy+relaunch. **Caveats:** after every `deploy_wotmod.py`, re-run
`sync_gameface.py` (else the stale overlay shadows the fresh package); and **remove
the overlay** (`res_mods\2.3.1.0\gui\gameface\mods\14th_ua\`) before a
clean ship-verification so you're testing the packaged assets.

Unit tests (engine-free domain layer, Python 3):
```
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m pytest -q   # expect green
```

## Debug REPL (live introspection)
`com.14th_ua.moe_calculator_debug.wotmod` runs a TCP REPL on **127.0.0.1:2224** in the client
(the sibling Garage Progress Bar's debug REPL owns **2223**, so both can run at once).
- Build/deploy it (client closed):
  `& "C:\Python27\python.exe" tools\dev\build_debug_wotmod.py "D:/Games/World_of_Tanks_EU" 2.3.1.0`
- Drive it from the host (client running, in Garage):
  `& "<py3>" tools\dev\repl_client.py "<expr>"` or `--file cmds.txt`
- One command per line; state shared only within one run → put interdependent
  commands in one `--file`. For multi-line code: write a `.py` and send
  `execfile(r'<abs path>')` as one command.
- Keep the debug package SLIM (only `mod_moe_calculator_debug.pyc`). If it also ships
  `moe_calculator`, it conflicts with the real mod and WoT ignores it.

### Handy REPL snippets
```python
# current vehicle -> snapshot -> model
from CurrentVehicle import g_currentVehicle
from moe_calculator.adapter import engine_adapter
from moe_calculator.domain.builder import build_model
m = build_model(engine_adapter.build_snapshot())
(m.mode, m.scale_min, m.scale_max, m.fill_vehicle, m.fill_free, len(m.ticks))

# force a refresh of the mounted widget
from moe_calculator.bridge import gameface_bridge as B
B.refresh()
```

## Prediction-error analysis (offline, no client)
`adapter/sample_log.py` appends one prediction↔outcome row per battle to
`%APPDATA%\Wargaming.net\WorldOfTanks\mods_data\14th_ua_moe\battle_samples.jsonl`.
`analyze_battle_samples.py` reads it and prints whether the live percent's error is a
**slope** (mapping derivative) or a **level** (thresholds/baseline) problem:
```
& "<py3>" tools\dev\analyze_battle_samples.py                  # default prefs path
& "<py3>" tools\dev\analyze_battle_samples.py <file.jsonl> --min-delta 0.5
& "<py3>" tools\dev\analyze_battle_samples.py --self-check     # assert-based self-test
```
The percent is anchored (`cur = pre_percentile + inc`), so a constant offset cancels —
read the OLS `residual ~ pct_delta` verdict + the buckets, not the mean alone.

## Progress-bar JS behaviour check (offline, no client, no browser)
`MoEProgress.js` is a wall-clock state machine (a 6200ms keyframe seeked with a negative
`animation-delay`, an `animationend`-or-timer end race, an Alt peek that PAUSES the animation), and
its window has **no hot-reload** — every timing hypothesis otherwise costs a full client relaunch.
`check_progress_js.js` runs the real file headlessly in plain Node (zero deps): it strips the one
OpenWG `import`, evaluates the source with `document` / `viewEnv` / `engine` / `ModelObserver` and a
**virtual clock** injected as parameters, then drives it and asserts **emitted VALUES** — the
`resizeViewRem` args, the `animation-delay` string, the armed run class, `animationPlayState`, the
fill's width `%`, the caption text. (Per `bar-tuner-selfcheck-is-not-a-gate`: a self-check that only
looks for leftover tokens proves nothing.)
```
node tools\dev\check_progress_js.js                      # the gate: exits 1 on any failure
node tools\dev\check_progress_js.js --list-mutations
node tools\dev\check_progress_js.js --mutate=<key>       # anti-vacuity: MUST report failures
```
Covers: the surface push + the post-deadline re-assert, the visible/hasData gate, the
**`surfaceSettled` show gate** (no trigger may show while the surface is still the engine's 256×256
fallback — cropped and ~142px too high — yet the silent baseline must still run, and a still-held Alt
must appear the instant the flag flips off the settle's own `render(observer.model)`), the silent
first baseline, cold show (incl. the rewind→rAF re-aim), warm re-trigger, a stale `animationend` from
a superseded identity, the fallback end timer with no `animationend` at all, peek hold / release, the
**short Alt tap** (strictly hold-to-show: a release that beats the plateau pause is *mirrored* into
the fade-out — seek `SEEK_FADE_OUT + inLeft`, identity flips, gone ~550ms after the release instead
of serving the whole 6200ms transient), **Alt pressed during the fade-out**, the hide→re-show
reset, and **Alt across a damage-driven hold** (`dmgPlateauAt`): a release mid-hold *resumes* that
hold at its true elapsed position and ends **exactly when the untouched damage run would have** —
neither truncated to the release nor handed a fresh hold — a damage event arriving *during* a peek
gets the hold the warm re-trigger it could not arm would have had, and a peek that interrupted
nothing (or whose damage hold ran out / ended on `animationend` / was killed by a hide) still takes
the plain fade-out. Those cases assert **absolute end instants**, not "still armed": both failure
modes look identical to a visibility check. Each `MUTATIONS` entry breaks one real behaviour; every
one of them must make the run fail, or the check is vacuous.
It never writes a timing literal: `SURFACE_REASSERT_MS`, `SURFACE_SETTLE_MS`, `FADE_IN_MS`,
`HOLD_MS`, `END_MARGIN_MS` and the surface/hit-pad geometry are all **scraped** out of the module
(and `TOTAL` / `SEEK_FADE_OUT` derived from the scraped pair exactly as the module derives them), so
a retune moves the shim with it (the same `jsConst` idiom as
`tests/test_progress_surface_mirror.py`). Its virtual clock starts at a **realistic epoch magnitude**
(`1e12`), not `0`-ish: `dmgPlateauAt == 0` means "no damage hold in flight", which only reads as
*long ago* while `Date.now() > HOLD_MS`.
It has no layout, no CSS and no compositor — looks, and whether Coherent honours a given property,
stay live-verification items. The surface size's HTML/CSS/Python mirror is guarded separately by
`tests/test_progress_surface_mirror.py`.

## Browser tuners / pickers (PowerShell generators, no client)
The in-battle Gameface **window** has no hot-reload (every CSS tweak = a full relaunch), so its
look is settled in a browser first. Each script emits ONE self-contained HTML (assets
base64-inlined) with slider panels and a "Copy CSS" button whose output is pasted verbatim
into the mod's CSS. Output lands in `TASKS/refs/` (gitignored).
```
pwsh tools\dev\gen_bar_tuner.ps1 [-Out TASKS/refs/in-battle-bar-tuner.html]
                                 [-Backdrop <any image>] [-ExtractIcons] [-SelfCheck]
                                 [-EmitCss [-CssOut TASKS/refs/MoEProgress.css]]
```
- `gen_bar_tuner.ps1` — the NEW centre-screen in-battle **MoE progress bar** (`.mp-*` →
  future `MoEProgress.css`): axis modes, mock `BattleSnapshot` data, **four labelled ticks**
  (axis ends = prev/next MoE requirement with the held / chased mark glyph, labelled **beside**
  the bar — `.mp-cap.side`, vertically centred on the track and hanging off each end by its own
  independent gap (`gapEndL` **8** → `padding-right`, `gapEndR` **3** → `margin-left`; the property
  differs because Gameface renders `margin` on the `right:100%` anchored side as a **0** gap),
  with their own `endFS` size, plus **`numY`** (default **-0.5**) which nudges just those two
  captions' NUMERALS — emitted as `.mp-cap.side .mp-v { transform: translateY(<numY>rem) }` — because
  `MoEBattle.ttf`'s metrics (asc 2088 / desc 486 @ upem 2048 = a **1.2568em** line box, 17.60rem at
  `endFS` 14) put the digit ink's centre **0.0381em = 0.53rem below** the line box's centre, and it
  is the box that `translateY(-50%)` centres on the midline; `min-height` cannot fix that (the box is
  already 17.60rem, so `markBox`'s 17 is a no-op) and `.up`/`.dn` must not inherit it. The tuner
  inlines the real ttf, so this reproduces the exact line box and is dialled **in the browser**
  instead of one relaunch per guess; the two CENTRE captions keep the load-bearing split, `pre_avg`
  above the track and `proj_avg` below it — each caption is ONE row, **icon left of the
  numerals**), the slide+fade-in → tick-move → hold → slide+fade-out sequence (the exit slides
  back **DOWN**, the way it came in)
  with a **preset dropdown of real WG timings** (`BattleNotifierView` transient/show,
  `vehicle_/player_messages_panel`), mock fly-up ribbons, backdrop-screenshot drag-and-drop.
  Schema defaults are the **maintainer's tuned values** (600/**5000**/600 ms = **6200** total, keyframe
  stops **9.68/90.32**; `barW` **200** (was 300) — the ONE knob behind the emitted
  `#moe-bar-root { width: 200rem }`, and the only tuned length anything else is derived from:
  `.mp-backdrop` follows it (`width: barW + 2*bdBleedX` = **360rem**) and so, outside this file, does
  `MoEProgress.js`'s mirrored `BOX_W_REM` → `VIEW_W_REM` → the hand-appended `#moe-bar-box` width
  (`SHIFT_X_REM` is `PAD_REM - BOX_LEFT_REM` and does **not** move with `barW`). 200 = 3×66 + 2, so
  the 3rem dash period still ends on a **whole 2rem mark flush with the right edge** — nothing to
  compensate. Everything the bar animates is **`%`-based** (`.mp-fill` width, the `.mp-pre`/`.mp-proj`
  `left`, `.mp-capC` `left`, the `.mp-left`/`.mp-right` end ticks), so the axis is width-agnostic;
  what is NOT is the horizontal head-room for the two moving centre captions, which are a fixed
  **rem** width centred on their tick: at `barW` 200 the bottom caption is collision-free only over
  **17.5 %–82.5 %** of the axis (it was 11.7 %–88.3 % at 300), the top one over 8.5 %–91.5 %, and the
  `pre`/`proj` tick edges close from 2rem to **0.67rem** at the default mock move. The two `.side`
  captions hang off the ends by a width-INDEPENDENT `gapEndL`/`gapEndR` + row width, so `bdBleedX` 80 still
  covers them with ~25rem to spare exactly as at 300;
  `offY` **86.5**vh, `trackH` 3, `tickH` 9, `slide` **20rem, range ±85, step 0.1 —
  a float** (it was 1 until `slideStops()` was fixed to route through the `pxrem` calibration like
  every other length: it had emitted a literal `rem`, and with no root font-size the browser's 16px
  default showed **19.2×** the travel the slider claimed, so the approved look was ~19.2rem, not 1);
  icons `icoFill` **0.75** → 228.7% (top-centre `barrel_mark`, bb 0.328) / 342.5% (bottom-centre
  `damage`, bb 0.219) / **274.7%** (the 3-marks right cap `icon_battle_condition_top`, bb **0.273**
  — its own glyph, since `barrel_mark` is the top-centre default now), `icoBox` 13 is the base
  `.mp-ico` fallback only (every caption overrides it), `dmgPBox`/`dmgCBox` 14/16, `markBox` 17
  driving **both** `.mp-ico.mk` **and** `.mp-ico.moe` (one knob — `.moe` replaces the right mark, so
  they are never on screen together; without the `.moe` rule it fell back to 13rem and shrank),
  `icoGap` 1, per-role
  icon Y 0.5/**0**/1/0.5 (L/P/C/R — the TOP caption's nudge is 0 now, the bottom one is still 1), `numY` **-0.5**; fill **cream `#ede6d9` @ 0.8** — `fillA` drives all three fill backgrounds —
  ticks `endA` **0.8** / `preA` **0.75** / `projA` **1** (the CURRENT tick reads solid); backdrop `bdBleedX` **80** → `left: -80rem` / `width: 360rem`, dither mask
  `56% 110%` fading out by **67%**, radial underlay **76% 57%**), so the "transient"
  preset no longer matches them. **`fillCol` must stay off `upCol`/`dnCol`:** it *was* the same
  green as `upCol`, which made every cold damage event flash **green** through the entry animation
  (the sign class only lands at the numeral swap) even while the delta was negative. The cream
  `#ede6d9` is now the **first-show** neutral only — nothing committed yet — because the entry
  window otherwise inherits the previous committed sign colour (see the classification note below),
  so it is not a per-event flash. Expect to re-dial it by eye — a cream fill makes the cream dash marks
  (`dashCol` @ `dashA` 0.16) near-invisible over the reached half, leaving the opaque `gapCol`
  stripe to carry the grid; that is a **slider**, so it costs zero relaunches to retune.
  The track carries **the garage widget's own treatment**, cloned from `#moe-root .moe-track`
  (`MoECalculator.css:284-297`): the hangar bar paints WG's `bg_pattern_small.png` at
  `background-size: 99rem 2rem` (1 art px == 1rem → **2rem dash / 1rem gap**, cream
  `rgb(236,230,218)` @ **41/255 = 0.16**) plus `box-shadow: 0 0 0 1rem rgba(13,14,16,0.5)`. Same
  numbers here as **sliders** (`dashW`/`dashGap`/`dashCol`/`dashA` + `gapCol`/`gapA`,
  `bdrW`/`bdrCol`/`bdrA`) with a
  **track dashes** / **track border** checkbox each (both ON, emitting `none` when off) — the art is
  re-drawn as a 4-stop `repeating-linear-gradient` because `img://` is dead in a browser and a PNG
  cannot follow a slider. **The GAP stripe is a real dark colour, not `transparent`**
  (`gapCol` `#0d0e10` @ `gapA` **0.5** by default — the maintainer's tuned half-strength mask;
  `gapA` 1 is the full garage read): the garage's own `.moe-fill`
  (`MoECalculator.css:304-326`) has **no `background-color` at all** — it paints
  `filled_pattern_small.png` only, at the same `99rem 2rem` / `left center` as the track — so the
  hangar grid is a **mask** and the fill exists only inside the dash marks while the gaps show the
  dark backing. Our fill is a solid colour, so an opaque gap stripe (`gapA` 1) is what reproduces
  that read exactly and the tuned **0.5** dials it back halfway;
  `gapA` 0 gives back the earlier look where the fill floods the gaps and the bar reads as sitting
  *on top of* the grid. (The `bg_pattern_small.png` fallback noted in the emitted CSS is therefore
  only equivalent at `gapA` 0 — that PNG's gaps are transparent.) The gradient is on the **track's**
  pseudo, so its origin is the track's left edge and the dashes stay in phase across the reached and
  unreached halves at any fill width — the mask-on-`.mp-fill` alternative was rejected (a `mask` on
  a `width`-transitioning element is an unverified Coherent risk; the only emitted `mask` is still
  the backdrop dither). Both live on ONE `.mp-track::after` with the explicit
  `left/top/width/height` box Coherent needs: `z-index: 1` puts the dashes **above** the auto-`z`
  fill and below the `z-index: 2` ticks (so the moving `.mp-proj` tick still reads at `gapA` 1),
  and the garage's "border" is an **outset** shadow, never a
  `border` — zero box-model impact, so the track's height stays exactly `trackH` and the tick /
  `bdTop` centring cannot shift (no `box-sizing` needed anywhere). The pseudo also survives
  `.mp-full` / `.mp-pulse`, which overwrite the track's own `box-shadow`.
  **`.mp-tick.mp-proj`** (the tick riding `proj_avg`) gets its own two-pass glow —
  `projGlowCol`/`projGlowA`/`projGlowB`/`projGlowB2`, default white @ 0.5, 6rem + 2rem core — the
  same wide+core shape as the gold ring and the text glow. `#moe-bar-root.mp-full .mp-tick` is
  id+2-class (specificity 1,2,0) and **out-specifies** it, so met-requirement gold deliberately
  takes the tick over; there is no knob to fight that. **That tick also takes the SIGN**, from the
  emitted `.mp-tick.mp-proj.mp-up` / `.mp-tick.mp-proj.mp-down` (and the stage's `.mp-proj.mp-up` /
  `.mp-proj.mp-down` twins, so the preview shows it): the `upCol`/`dnCol` sliders at the fixed 0.9
  delta-glow alpha with the **tick's own** `projGlowB`/`projGlowB2` radii — no new knobs, so
  re-dialling a sign colour moves the numerals' glow and the tick's together, which is the whole
  point of "same colours as the text". `projGlowCol`/`projGlowA` are the **neutral** only (no rule
  needed for it — the base rule *is* the neutral). Two things not to "tidy": these stay at
  specificity **(0,3,0)** so the (1,2,0) `.mp-full` rule still wins, and they emit
  **declaration-only** — restating `transition` would re-arm the base `left` transition. The bottom caption's
  `(+N)` is a separate `.mp-d` element carrying the shipped sign convention — for **text** a
  green/red **glow, never a fill** (`#7BEC37` / `#D3443F` @ 0.9, wide + tight pass); zero delta
  gets neither class. **The preview classifies on the ROUNDED delta**, mirroring the shipped
  `showVal` — `Math.round(Math.abs(d)) !== 0`, tested on the magnitude exactly as `fmt()` rounds it
  (`Math.round(d)` is `-0` at `d == -0.5` while the text already reads `(-1)`). The displayed glyphs
  are untouched, so a `d` of `+0.4` still renders `(+0)` but now glows **nothing**; unrounded, it
  glowed green on a displayed `(+0)`.
  **The cold-entry window CARRIES the previous committed sign, it does not reset to neutral**:
  `showVal(false)` returns *before* the toggles and so removes nothing, leaving whatever the last
  `showVal(true)` applied on all four elements (fill, main numeral, delta number, `.mp-proj` tick).
  A bar that was red and then earns damage reads **red through the entry and turns green at the
  swap**; a bar that was and stays red never blinks. Only `showVal(true)` ever clears — and it
  **must**, because a rounded-zero commit has to wipe the carried colour or a stale red survives
  into the neutral `(+0)` state. Only the very first show has nothing committed, and that is the
  one place the cream `fillCol` neutral shows. This is a **sequence** behaviour, so a single-call
  check cannot see it — assert it as an ordered call sequence in the node DOM shim.
  **`.mp-fill` is the one exception**: the bar takes the same up/down colour
  as a real `background` (no glyph to keep legible), neutral at zero delta, with `transition`
  still naming only `width`. The bottom numeral shows `pre_avg` during the entry and **swaps to
  `proj_avg` on `tickDelay`** — delta, sign glow and fill colour all arrive with it
  (`valueSwapMs` in the emitted timings JSON tracks `tickDelayMs`).
  **The `(+N)` delta FADES in** at that swap rather than snapping: `opacity` 0 → 1 with
  `transition: opacity <dFadeMs>ms <dFadeEase>` on `.mp-d` (defaults **600ms / `cubic-bezier(.2,.8,.2,1)`**
  = the tick move's own duration and curve, so the delta finishes appearing exactly when the fill and
  tick finish moving; both are in the timings JSON as `deltaFadeMs` / `deltaFadeEasing`). `opacity`,
  **not `visibility`** (which cannot interpolate) and **not `display`** (which would drop the box out
  of the flex row and re-centre the `translateX(-50%)` caption mid-animation — `opacity` keeps the box
  laid out exactly as `visibility` did). No `visibility` alongside it: the widget is
  `pointer-events: none`, so a 0-alpha box has nothing to hit-test. Exactly **one** `transition` on
  `.mp-d`, naming only `opacity`, with explicit ms + easing (a `transition` on a property whose value
  comes from an unresolvable `var()` gets dropped by Gameface). Replay cancels it the same way the
  fill/tick rewind does — `transition: none`, `opacity: 0`, reflow, restore — so a half-finished fade
  never runs into the next cycle, and the `animationend` settle lands it at 1.
  **When the requirement is met the fill's COLOUR turns gold too**, not just its glow:
  `#moe-bar-root.mp-full .mp-fill` gets `background: <glowCol> @ fullFillA` (**0.8** by default —
  the glow's own 0.5 is far too faint for a solid bar, and 0.8 == `fillA`, so the bar's density does
  not change when it turns gold, only its hue). One gold, one picker: it reuses `glowCol` and only
  the alpha is its own. It needs a rule of its **own** — the grouped `.mp-track, .mp-fill, .mp-tick`
  rule above it is the `box-shadow`, and a `background` there would paint the track and ticks too.
  Specificity **verified in the emitted CSS**: `#moe-bar-root.mp-full .mp-fill` is (1,2,0) vs
  `.mp-fill.mp-up` / `.mp-fill.mp-down` at (0,2,0) and `.mp-fill` at (0,1,0), so the gold wins with no
  `!important` and JS keeps toggling the sign classes untouched. `transition` is **not** restated
  there — `width` stays the only animated property; the background flips.
  **Two independent icon glows.** `icoGlowCol`/`icoGlowA` now govern the **two centre damage icons
  only**; the **MoE requirement icons** — the mark glyphs on the two axis-end `.side` captions,
  including the general-MoE glyph that replaces the right one at 3 marks — have their own
  `reqGlowCol`/`reqGlowA`, emitted as a `.mp-capL .mp-ico::before, .mp-capR .mp-ico::before` rule.
  **The two groups are tuned APART now:** the centre damage pair keeps the gold halo
  (`icoGlowCol` `#ffcd5a` @ `icoGlowA` **0.5**) while the side mark glyphs are a **dark drop** —
  `reqGlowCol` **`#1a1a1a`** @ `reqGlowA` **0.5** → `rgba(26,26,26,0.5)` — a shadow lifting them off
  the map, not a halo.
  Deliberate; don't "restore" them to the gold. (The `.mp-full` ring / `mp-pulse` / met-state fill
  golds are untouched, so near-black @ 0.5 is the file's one intentionally dark glow.)
  That override sets **`background` only** and targets `::before`, never `.mp-ico` — `.mp-ico`'s own
  `transform` carries the per-role Y (`icoYL`…`icoYR`) *and* is the stacking context that scopes the
  `::before` glow's `z-index: -1`, and the base `.mp-ico::before` rule (bare selector) keeps
  supplying that `z-index`, the 106% glow box and its own `translate(-50%,-50%)` for both groups.
  `-Backdrop` bakes in ANY image (a raw 3840x2160 screenshot needs no manual resize) —
  auto-resized to the stage's 1600x900, centre-cropped if it is not 16:9. The default is
  `TASKS/refs/tuner-backdrop-ribbon.jpg`, which has a **real WG fly-up ribbon** in frame at
  75.1vh (`tuner-backdrop.jpg` is the older no-ribbon shot).
  **`-ExtractIcons` (run once per clone)** pulls the 6 tick PNGs out of the client's
  `gui-part{1..4}.pkg` into `TASKS/refs/icons/` (they are scattered across all four packages) —
  the tuner runs in a browser where `img://` is dead, so icons must be base64-inlined; a missing
  one aborts by path. `-SelfCheck` asserts the emitted file exists, is > 100 KB, and has no
  leftover `__TOKEN__` — it **cannot** catch a wrong value or a key collision, so verify a change
  by running the emitted `<script>` in a headless DOM shim and asserting `cssOut()`'s values.
  **`-EmitCss`** writes the settled stylesheet to a **real file** (`-CssOut`, default
  `TASKS/refs/MoEProgress.css` — gitignored, a handoff artifact; phase 2 copies it to
  `src/res/gui/gameface/mods/14th_ua/MoECalculator/MoEProgress.css`) instead of leaving it in the
  browser's clipboard. It runs the just-generated HTML's own `<script>` in that same headless DOM
  shim **under node** and clicks the real **Copy CSS** handler, so the bytes are the button's bytes
  (the driver asserts clipboard == `cssOut()` == the panel preview and rejects any
  `NaN`/`undefined`/unresolved `var()`); `cssOut()` is never re-implemented in PowerShell, which
  would drift on the next slider. Needs `node` on PATH. At the settled defaults: **25,394 bytes /
  439 lines**, LF, no BOM (this figure moves on every emit change — the two signed
  `.mp-tick.mp-proj` rules and their comment are the latest bump).
  It then **WARNS about the hand-edited blocks it does not emit** — **four** of them now. The
  shipped `MoEProgress.css` is the emit *plus* the `@font-face`, the `body`/`#moe-bar-box` sizing
  shim and the `mp-life-b` twin (all **appended**), *and* a **rewritten** `.mp-track::after`: the
  shipped dash grid uses WG's own tiling idiom — `background-image` with exactly ONE 3rem period +
  `background-size: 3rem 100%` + `background-repeat: repeat`, and an **opaque** `rgb(13,14,16)`
  gap — whereas the emit still writes a single track-wide `background:` gradient at `gapA` **0.5**.
  A naive copy therefore reverts the tiling *and* floods the gaps (the fill stops reading as
  masked). Each of the four has already cost a client relaunch. Advisory only: it warns per missing
  marker and never fails the emit. Another block = one line in the script's `$APPENDED` table.
- `gen_overlay_tuner.ps1` — the **shipped in-battle overlay** (`.mb-*` → `MoEBattle.css`): row
  pitch, backdrops, icon glow, 5-digit `BATTLE_ANCHOR_X_SHIFT` guide. Its `$out` is a dead
  hard-coded scratchpad path — edit it before running (see `gen_bar_tuner.ps1` for the fix).
- `gen_icon_picker.ps1` — browsable grid of the game's quest-type / mark PNGs with their
  `img://` URLs, for choosing an overlay glyph. Same dead-path caveat.

## Decompiled source (re-clone as needed; not in repo)
Match the client's branch/region — use the branch matching your client's major
version (e.g. the `2.3.1.0` major line):
```
& $git clone --depth 1 --branch <major> --single-branch https://github.com/StranikS-Scan/WorldOfTanks-Decompiled.git wot-eu
```
(The repo's default branch is a different regional client — cross-check against
the live `res/packages/scripts.pkg` by listing module filenames.)
