# Dev tools (WoT 2.3.1.1)

In-game introspection + the real dev loop for this mod. **Not shipped** with the mod.
See the harness skills `wotmod-build-deploy` and `wotmod-debug-repl` for the generic
pattern behind these scripts.

## Environment (this PC)
- WoT install: `D:/Games/World_of_Tanks_EU`, version **2.3.1.1**. OpenWG Gameface installed.
- **Python 2.7.18** at `C:\Python27\python.exe` — packaging only (compiles `.pyc`; bytecode is 2.7-locked).
- **Python 3.13** at `%LOCALAPPDATA%\Programs\Python\Python313\python.exe` — runs pytest + the REPL client.
- Git at `C:\Program Files\Git\cmd\git.exe`, `core.longpaths=true` (needed for decompiled clones).

## The dev loop (WoT 2.x loads ONLY `.wotmod`)
Loose `res_mods\<version>\scripts` does **not** load in 2.x, and `res_mods` outranks `.wotmod`
(a stale loose copy SHADOWS the package → client ignores the mod). So always:

```
# 1) close the WoT client (file locks); then build+deploy the real mod:
& "C:\Python27\python.exe" build\deploy_wotmod.py "D:/Games/World_of_Tanks_EU" 2.3.1.1
# 2) relaunch the client. (OpenWG may auto-restart once when res_map changes.)
```
`deploy_wotmod.py` auto-cleans old `com.14th_ua.moe_calculator_[0-9]*.wotmod` and loose leftovers.

### Hot-reload loop for JS/CSS-only changes (NO relaunch)
`coui://gui/...` resolves through a merged FS where `res_mods/<version>/` outranks
the `.wotmod`, and the hangar sub-view re-fetches our assets each time its document
is rebuilt. So for **visual-only** (MoECalculator.js/.css) iteration:
```
# client may stay running:
& "<py3>" tools\dev\sync_gameface.py "D:/Games/World_of_Tanks_EU" 2.3.1.1
# then in-game: switch to another screen (e.g. Tech Tree) and back to the Garage.
```
This is ONLY for front-end assets. Python (mount/data) changes still need
build+deploy+relaunch. **Caveats:** after every `deploy_wotmod.py`, re-run
`sync_gameface.py` (else the stale overlay shadows the fresh package); and **remove
the overlay** (`res_mods\2.3.1.1\gui\gameface\mods\14th_ua\`) before a
clean ship-verification so you're testing the packaged assets.

Unit tests (engine-free domain layer, Python 3):
```
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m pytest -q   # expect green
```

## Debug REPL (live introspection)
`com.14th_ua.moe_calculator_debug.wotmod` runs a TCP REPL on **127.0.0.1:2224** in the client
(the sibling Garage Progress Bar's debug REPL owns **2223**, so both can run at once).
- Build/deploy it (client closed):
  `& "C:\Python27\python.exe" tools\dev\build_debug_wotmod.py "D:/Games/World_of_Tanks_EU" 2.3.1.1`
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
& "<py3>" tools\dev\analyze_battle_samples.py --backtest       # shipped-model back-test (fetches WG once)
```
The percent is anchored (`cur = pre_percentile + inc`), so a constant offset cancels —
read the OLS `residual ~ pct_delta` verdict + the buckets, not the mean alone.

**Two row classes are NOT samples** and the loader drops both (they are counted in the
`skipped:` line): `has_baseline false` (the overlay dashed the percent out, so nothing was
ever shown — the two in this log carry residuals of +79/+70) and a repeat of
`(int_cd, post_battles)` (the same battle re-logged from a replay watch, carrying a stale
pre-baseline — the one in this log reads `pre_percentile 50.0` against a real `34.79`). With
all three present the OLS slope reads t=-0.6 instead of its true t=+4.5, i.e. the poisoned
rows can invert the verdict.

**The default report is HISTORICAL, `--backtest` is current.** `residual` is a stored field —
whatever the mod believed *at the time it logged the row* — so every pre-1.6.x row carries the
superseded normal fit's error and the default mode still verdicts `t=+4.5` until enough battles
are logged by the shipped linear model. `--backtest` re-derives the error from the shipped code
and is the only mode that reflects HEAD.

The log **spans the threshold re-key**, so it carries two `thresholds` shapes: pre-1.6.x rows
keyed by MARK COUNT (`{1,2,3,100}` = D65/D85/D95/D100) and later rows keyed by PERCENTILE
(`{20,40,55,65,75,85,95,100}`). The loader normalises legacy `1/2/3 → 65/85/95` on read (the
key sets are disjoint apart from `100`) and the `thresholds:` header line counts each shape —
left unmapped, a legacy row feeds the shipped fit D65 as the **1st** percentile and looks like
garbage the fit accepts silently.

`--backtest` answers one question: **does the SHIPPED damage→percent model still reproduce WG's
own percentile?** The model is imported from `domain/battle_builder` (never re-implemented) and
fed the EIGHT anchors WG stores, exactly as the shipped adapter now fetches them. The strongest
test needs no prediction at all: `post_avg_damage` and `post_percentile` are BOTH read off the
dossier, so `f(post_avg) - post_percentile` measures the mapping directly. The 8 anchors need
one live WG call (batched, `.env` app_id, region eu, max 10 percentiles × 100 tank_ids);
`--cache8` caches them to JSON so re-runs are offline.

The finding this back-test banked, now shipped: WG's `damageRating` **IS** piecewise-linear
interpolation over those 8 anchors plus a `(0 damage, 0 percent)` origin stop. Confirmed over
118 logged rows — level error mean **+0.047**, stdev **0.088**, max **0.238**, and
`residual ~ inc` slope **+0.004 (t=+0.27)** where the superseded piecewise-normal fit gave
`+0.19 (t=+4.5)`. Those are the numbers a re-run must still print; a drift is a **shipped-code**
regression, not a tool one. The normal-fit comparison arm is **gone** (it cannot be reproduced
from shipped code any more, and its job is done); `lin_percent()` stays only as the independent
oracle that `--self-check` sweeps against the shipped model.

## The shared harness shim (`lib/gf_check_shim.js`)
Both in-battle bars are thin callers of ONE shared module,
`src\...\MoECalculator\MoEBarTransient.js`, and both JS behaviour checks below share
`tools\dev\lib\gf_check_shim.js`: the assertion helpers, the minimal DOM (`El` + a tag-stack
`parseHTML`), the **virtual clock** (`setTimeout`/`Date.now`/`requestAnimationFrame` driven by
`advance(ms)`), the `jsConst`/`jsArray` source scraper, `stripComments`, the module-syntax strip +
concat, and the mutation applier / `main` report block. The two harnesses used to carry a
byte-identical copy of all of that (~245 lines each); two copies of a harness drift, and a drifted
harness silently stops asserting (`bar-tuner-selfcheck-is-not-a-gate`).
Two shim details were once deliberate per-harness differences; both were **strict generalisations**
in the efficiency copy and both are now shared:
- `El.querySelector` matches **compound** class selectors (`.mp-tick.r3`, `.mp-cap.up`) — the
  efficiency bar disambiguates five ticks and five captions that way, and single-class matching would
  hand back the WRONG node instead of failing loudly.
- `offsetWidth` is **writable** (default 0), not a constant-0 getter — at a hard 0 the efficiency
  bar's `capClamp` corridor never binds, so the whole clamp section would be vacuous.

**How the two files are loaded.** Each bar imports OpenWG's `../../libs/model.js` (not in-repo) *and*
`./MoEBarTransient.js` (in-repo). The shim strips the ES module syntax, concatenates the sources
**transient FIRST** and evaluates the pair as ONE `new Function` body with every engine global
injected. Transient first is load-bearing: each bar's top-level `createTransient(...)` call (and
`MoEProgress.js`'s `const VALUE_SWAP_MS = FADE_IN_MS`) runs at load and would hit the transient's
`const` TDZ the other way round. The import strip needs the **`g` flag** — each bar now has TWO
import lines, and a non-global regex left the second one in the evaluated body, which is what broke
both harnesses when the transient was extracted.
Every `MUTATIONS` entry is `[WHICH, from, to]`, `WHICH` naming the file that owns the behaviour
(`"T"` = `MoEBarTransient.js`, `"B"` = the bar). Naming it is deliberate rather than "whichever
source contains the anchor": a mutation whose anchor has gone stale reports **ANCHOR NOT FOUND** and
counts as SURVIVED, so a refactor that moves code cannot quietly leave a probe unapplied.

## Progress-bar JS behaviour check (offline, no client, no browser)
`MoEProgress.js` + `MoEBarTransient.js` are a wall-clock state machine (a 6200ms keyframe seeked with
a negative `animation-delay`, an `animationend`-or-timer end race, an Alt peek that PAUSES the
animation), and the window has **no hot-reload** — every timing hypothesis otherwise costs a full
client relaunch. `check_progress_js.js` runs the real files headlessly in plain Node (zero deps) via
the shim above, then drives them and asserts **emitted VALUES** — the `resizeViewRem` args, the
`animation-delay` string, the armed run class, `animationPlayState`, the fill's width `%`, the
caption text. (Per `bar-tuner-selfcheck-is-not-a-gate`: a self-check that only looks for leftover
tokens proves nothing.)
```
node tools\dev\check_progress_js.js                      # the gate: exits 1 on any failure
node tools\dev\check_progress_js.js --probe-all          # every mutation, as a table
node tools\dev\check_progress_js.js --list-mutations
node tools\dev\check_progress_js.js --mutate=<key>       # anti-vacuity: MUST report failures
```
**164 assertions, 59 mutations, all probed and all firing.**
Covers: the surface push + the post-deadline re-assert, the visible/hasData gate, the
**`settled` show gate** (no trigger may show while the surface is still the engine's 256×256
fallback — cropped and ~142px too high — yet the silent baseline must still run, and a still-held Alt
must appear the instant the flag flips off the settle's own `render(observer.model)`), the silent
first baseline, cold show (incl. the rewind→rAF re-aim), warm re-trigger, a stale `animationend` from
a superseded identity, **the force-settle**, the fallback end timer with no `animationend` at all,
peek hold / release, the
**short Alt tap** (strictly hold-to-show: a release that beats the plateau pause is *mirrored* into
the fade-out — seek `SEEK_FADE_OUT + inLeft`, identity flips, gone ~550ms after the release instead
of serving the whole 6200ms transient), **Alt pressed during the fade-out**, the hide→re-show
reset, and **Alt across a damage-driven hold** (`dmgPlateauAt`): a release mid-hold *resumes* that
hold at its true elapsed position and ends **exactly when the untouched damage run would have** —
neither truncated to the release nor handed a fresh hold — a damage event arriving *during* a peek
gets the hold the warm re-trigger it could not arm would have had, and a peek that interrupted
nothing (or whose damage hold ran out / ended on `animationend` / was killed by a hide) still takes
the plain fade-out. Those cases assert **absolute end instants**, not "still armed": both failure
modes look identical to a visibility check. It also pins the **rAF asymmetry** that must never be
flattened into the shared `onCommit` hook — cold wraps `setPos` in `requestAnimationFrame`, warm sets
it synchronously — with a probe in *both* directions (`cold-commit-loses-its-raf` /
`warm-commit-gains-a-raf`). Each `MUTATIONS` entry breaks one real behaviour; every one of them must
make the run fail, or the check is vacuous.
> **A probe found a vacuous assertion in this very file.** "…and snapped the fill there" sat on the
> WARM path, where the commit had already set the fill to the target, so deleting `onEnd`'s `setPos`
> outright failed *nothing*. The force-settle is now probed on a run that ends before **both** its
> swap and its cold rAF have landed, where the snap is the only thing that can move the fill. Same
> trap as `unscoped-substring-assertion-is-not-an-assertion`, one layer down: an assertion
> coincidentally satisfied by a value someone else already wrote. `--probe-all` is what found it.

**THE TRANSITION SWITCHES** (`transEvents` / `transManual`) are asserted in BOTH harnesses, because
they live in the shared transient: one flag per trigger AREA, and the live run's copy decided **at arm
time**, so the exit follows the same switch as the entry. An un-animated run arms at `SEEK_PLATEAU`
instead of `SEEK_NONE`, its end timer stops being a *fallback* and becomes the **real** end at
`HOLD_MS` (no fade-out, no `END_MARGIN_MS`), and an Alt release ends it outright instead of arming a
fade-out. The end instants are absolute — "still armed" cannot tell `TOTAL_MS + END_MARGIN_MS` from
`HOLD_MS`, so both directions of the timer ternary are probed
(`unanimated-end-timer-still-fades-out` / `animated-end-timer-loses-its-fade-out`). The progress
harness additionally owns the VALUE half (the snap through `onRewind(atCurrent=true)` and the SKIPPED
`onCommit`, whose absence shows as the fill keeping its `transition:none` across a `flushFrames`);
the efficiency bar passes neither hook, so it cannot see that. And the **fail-soft direction is pinned
explicitly**: both flags are read `!== false`, so an absent field degrades to ANIMATED — which is why
every other fixture in either file, none of which carries either field, still asserts the shipped
behaviour (`absent-flag-degrades-to-instant`).

It never writes a timing literal — and since the extraction the constants live in **two** files, so
each scrape names its owner: `FADE_IN_MS`, `HOLD_MS`, `FADE_OUT_MS`, `END_MARGIN_MS`,
`SURFACE_REASSERT_MS`, `SURFACE_SETTLE_MS`, `HIT_MAGIC`, `RUN_CLASSES`/`RUN_NAMES` from
`MoEBarTransient.js`; the five `BOX_*`/`PAD_REM` surface values (and the hit-pad geometry derived from
them) from `MoEProgress.js`. `TOTAL` / `SEEK_PLATEAU` / `SEEK_FADE_OUT` are derived from the scraped
stops exactly as the transient derives them, so a retune moves the shim with it (the same `jsConst`
idiom as `tests/test_progress_surface_mirror.py`). Its virtual clock starts at a
**realistic epoch magnitude**
(`1e12`), not `0`-ish: `dmgPlateauAt == 0` means "no damage hold in flight", which only reads as
*long ago* while `Date.now() > HOLD_MS`.
It has no layout, no CSS and no compositor — looks, and whether Coherent honours a given property,
stay live-verification items. The surface size's HTML/CSS/Python mirror is guarded separately by
`tests/test_progress_surface_mirror.py`.

## Damage Efficiency bar: the tuner and its headless emit (no client, no browser)
`eff_bar_tuner.html` is the hand-written, self-contained tuner for the **Damage Efficiency**
in-battle bar variant (phase 1 of `TASKS/moe-efficiency-phase2.md`; 136 knobs, its own 70-assertion
`selfCheck()` — it reports `70 passed of 70`). It is the **single source of truth** for every number in that bar — do not copy
values out of the task note or out of `MoEProgress.css`.
```
node tools\dev\emit_eff_css.js [outPath]   # candidate (default TASKS\refs\MoEEfficiency.candidate.css)
                                          #   AND, in the same pass, candidate + the 2 hand-added
                                          #   blocks -> src\...\MoEEfficiency.css
node tools\dev\check_eff_css.js            # the drift gate: shipped == candidate + only those 2 blocks
```
The two run in that order. The candidate lands in **`TASKS/refs/`** — the repo's standing home for
emitted-CSS candidates (wholly gitignored; `gen_bar_tuner.ps1 -EmitCss` writes `MoEProgress.css`
there too), so there is no second generated directory to ignore. `check_eff_css.js` reads it from
there and exits 2 with a "run emit_eff_css.js first" hint if it is missing.
**The emit OVERWRITES the shipped stylesheet** — that is the point (nothing else may write it), and
the run names both files it wrote. Re-running it blind is safe: the SCHEMA-default assertion below
makes the output a pure function of the tuner plus the script, never of panel state.
`emit_eff_css.js` presses the tuner's **Copy CSS** button headlessly: it reads the `<script>` body
as text, truncates it at its `// ---- panel wiring` marker (everything past that is DOM wiring and
the `apply()` render pass — the emit path itself is pure in `st`, harvested from `SCHEMA`'s `val`
defaults), evaluates it with a one-node stub DOM, and calls `cssOut()`. It also runs the tuner's own
`selfCheck()` headlessly (pure apart from writing its readout to one element) and asserts every knob
is still at its `SCHEMA` default, so the emit is reproducible rather than "whatever the panel was
dialled to".
The emit ends in a JSON `meta` block — the **wire contract** the JS half needs and CSS cannot
express (axis, `barStops`, band colours, all timings, the `capClamp` corridor in rem, `boxWRem`, the
glyph ink bboxes). Per `bar-tuner-selfcheck-is-not-a-gate`, that block is `JSON.parse`d and
**every field type- and shape-checked**: exact key set, numbers that are actually numbers (`"holdMs":
true` fails by name), `totalMs == fadeIn + hold + fadeOut`, the clamp corridor non-degenerate and
inside `boxWRem`, glyph bboxes strictly in 0..1. All checks are `assert`-based and mutation-probed.
**The emit is NOT the whole stylesheet** (same trap as `-EmitCss` for `MoEProgress.css`): it carries
a `#moe-bar-box { width/height }` rule but **no `@font-face`** and no `mp-life-b` twin. Unlike
`MoEProgress.css`, though, **nobody hand-copies those in** — the same emit pass splices them, and
`check_eff_css.js` proves it:
- the splice makes the emit half byte-identical **by construction** (it is the in-memory `css`, not a
  re-read). It adds exactly two regions, each fenced by a `HAND-ADDED BLOCK n OF 2` /
  `END HAND-ADDED BLOCK n` marker pair: the
  `@font-face` (bare sibling `url(MoEBattle.ttf)` FIRST, as `MoEProgress.css` does — Coherent
  resolves an `@font-face` src against the DOCUMENT directory only), and the `mp-life-b` /
  `.mp-run-b` twin, which it **derives** from the emitted `mp-life` / `.mp-run` pair by rename so the
  twin can never drift from the tuner's timings.
- `check_eff_css.js` is the independent gate (it does not reuse the generator): it strips those two
  marked regions back out and asserts the remainder is the candidate **byte-for-byte**, that the twin
  still matches modulo the rename, and that there is exactly ONE `#moe-bar-box` rule and ONE
  `@font-face` **declaration** — counted with comments stripped, because a raw `@font-face` grep
  false-positives on the emit's own header prose
  (`unscoped-substring-assertion-is-not-an-assertion`). It also pins the four `.mp-backdrop` edges
  and the `#moe-bar-root` width, i.e. the numbers `MoEEfficiency.js`'s `BOX_*` / `BAR_W_REM` mirror.

The tuner's header comment says to hand-add the `#moe-bar-box` shim; that half is stale for the CSS
rule (the emit carries it), but the static in-flow `<div id="moe-bar-box">` still has to be cloned
into the view's `.html` — `MoEEfficiencyView.html:40` does.

## Damage Efficiency bar: the JS behaviour check (offline, no client, no browser)
`check_efficiency_js.js` is `check_progress_js.js`'s sibling for `MoEEfficiency.js` +
`MoEBarTransient.js` — **the same shim** (`lib/gf_check_shim.js`, above), same idiom, same
anti-vacuity rule, and the same reason for existing: the bar lives in a res_map-registered Gameface
**window**, which has NO hot-reload, so every timing hypothesis otherwise costs a full client
relaunch.
```
node tools\dev\check_efficiency_js.js                      # the gate: exits 1 on any failure
node tools\dev\check_efficiency_js.js --probe-all          # every mutation, as a table
node tools\dev\check_efficiency_js.js --list-mutations
node tools\dev\check_efficiency_js.js --mutate=<key>       # anti-vacuity: MUST report failures
```
**184 assertions, 76 mutations, all probed and all firing.**

**IT OWNS THE DELTA LATCH.** `battle_bridge`'s `_eff_last_damage` / `_eff_delta` and
`EfficiencyVM.damageDelta` were deleted and the latch now lives in `MoEEfficiency.js`, so the pytest
cases that covered those invariants were retired and **this file is the only gate on them**. `peak` is
the battle's HIGH-WATER mark, not the previous push (combined damage SUBTRACTS team damage, so the
total can move DOWN). Asserted: zero before any damage lands; the first increment of a battle is the
whole damage; a rise latches only the increment; a flat push keeps showing the previous increment; a
decrease never yields a negative delta *and* the next rise measures from the PEAK, not the dip; and
the latch **survives a `hasData` gap**, because a mid-battle re-show does not restart the total. Plus
the ONE intended behaviour change from the Python latch, pinned deliberately: a first push that
already carries damage **seeds** the mark, so `mount → 800 → 600` showed `+800` before and shows `0`
now.

**THE BATTLE BOUNDARY IS THE PUSHED `battleEpoch`, not an inference.** Python bumps a monotonic
counter once per battle mount and pushes it on every tick, and a change in it *is* the boundary — the
`if (total < peak) delta = 0` guess it replaced was wrong in exactly the case a player notices, so
that case is asserted **positively**: a boundary whose first total reads **HIGHER** than the previous
battle's peak (500 → 600) still resets, and re-seeds the mark at *that* total. Probed by
`epoch-reset-only-when-the-total-dropped` (the deleted inference restored as a guard — the ONLY
assertion that catches it) and `epoch-never-advances`. The counter lives in module state and
deliberately **not** in `last`, because the hide branch drops that baseline mid-battle and an epoch
that died with it would read the re-show as a new battle — probed by `epoch-stored-in-last`. And the
user-visible symptom has its own case: an **Alt peek right after a boundary** brings the bar up
reading `0`, never the dead battle's number.

**A DIP OR A FLAT PUSH MUST NOT POP THE BAR.** The show/flash trigger is the latch's `gained`, which
only a new high-water mark sets: "the value changed" and "the player gained damage" are different
events, since combined damage SUBTRACTS team damage. Asserted on the branch where the previous run
has already ended on its own `animationend`, so `T.show()` is the only thing that could arm anything —
and **both halves** are asserted, quiet (no run armed, no re-flash, the increment still standing) *and
still repainting* (the dipped total, `barX`, the tick, the band, `.met`, the pulse), because a
quiet-only check would pass just as well on a bar that is simply broken. Probed by
`dip-pops-the-bar`.

Covers: the surface push
(`resizeViewRem` / `setHitAreaPaddingsRem` / the rigid shift) **and the post-deadline re-assert** —
the engine's 256×256 default-size fallback runs LAST, so the mount push alone proves nothing; the
silent baseline (which must run *un*gated) versus **pre-settle suppression** (which must gate every
show trigger, damage and Alt alike, plus the settle's own `render(observer.model)` so a still-held Alt
lands the instant the flag flips); `band` → exactly ONE `mp-b-*` class with `.met` on tick *i* iff
*i* ≤ band and `mp-pulse` iff band 4; the delta's display window (`DELTA_HOLD_MS`, on a hit only —
never on a peek); the **warm re-trigger** (`-600ms` plateau seek **with the identity alternating
`mp-run` ↔ `mp-run-b`**, which is what the stylesheet's hand-added twin is *for* — a coalesced
restart on a `both`-filled `opacity:0` root is the "shows once, never again" bug the Moving Average
bar shipped with); the stale-`animationend` identity guard; the fallback end timer and a later hit
still showing after it; the Alt peek (pause, never ends while held, `-5600ms` release seek) and
**both halves of the resume-vs-fade split** — `peekOn`'s phase must come from ELAPSED TIME
(`Date.now()` vs `plateauAt + HOLD_MS`), never from `showing` (which stays true *through* the
fade-out, so branching on it freezes the bar at partial opacity), and `peekOff` must RESUME an
interrupted damage hold to its original absolute end instant while never resurrecting one that
already died; the `capClamp` corridor's two rem bounds, the icon-gap add-back and the
degenerate-corridor bail; and that **`barX` / `band` are consumed VERBATIM** — asserted twice over,
behaviourally (a model whose pushed values are deliberately inconsistent with anything derivable from
damage and the `r*` stops) and in the SOURCE TEXT with comments stripped and scoped per line (both
modules' prose is full of the words `damage`, `>=` and `INCLUSIVE`, so a raw grep would pass on the
commentary alone). The `>=`-inclusive rule is Python's, in `domain/battle_builder`, and unit-tested
there.
**The source-text rule is asserted on BOTH files** — `MoEEfficiency.js` *and*
`MoEBarTransient.js`: no comparison operator may share a line with `damage` or an `r*` stop, because
the shared transient is as much "the front end" as the bar is. It is also why the delta latch reads
the total into a `total` local first (it is damage-vs-damage and touches no requirement). Probed from
both sides — `met-from-damage` in the bar and
`damage-comparison-smuggled-into-the-transient` in the shared module. A companion assertion pins that
**nothing reads a `damageDelta` back off the model**, since the VM no longer carries one.
Like its sibling it writes down **no timing literal**, and each scrape names its owner now that the
constants live in two files: `FADE_IN_MS`, `HOLD_MS`, `FADE_OUT_MS`, `END_MARGIN_MS`,
`SURFACE_REASSERT_MS`, `SURFACE_SETTLE_MS`, `HIT_MAGIC`, `RUN_CLASSES`/`RUN_NAMES` from
`MoEBarTransient.js`; `DELTA_HOLD_MS`, the five `BOX_*`/`PAD_REM`, `BAR_W_REM`,
`CLAMP_L_REM`/`CLAMP_R_REM`, `ICO_GAP_REM` and `BAND_CLASSES` from `MoEEfficiency.js`. The seeks and
`TOTAL` are derived exactly as the transient derives them, so a retune moves the shim instead of
reddening it. The clock starts at a realistic epoch magnitude (`1e12`) for the same reason as its
sibling: `dmgPlateauAt == 0` must read as "long ago".
It has no layout, no CSS and no compositor, and **nothing in this bar has been confirmed in-game
yet** — looks, and whether Coherent honours a given property, stay live-verification items.

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

## The two VERTICAL bar tuners
Vertical variants of both in-battle bars, sitting **beside the minimap** rather than centre-screen
(the Orientation radio in the settings panel; see `TASKS/in-battle-vertical-bar-PLAN.md`). Phase 1
landed both stylesheets and their JS DOM/surface branch into `src/…/MoECalculator/` —
`MoEProgressVertical.css` / `MoEEfficiencyVertical.css`, `<link>`ed alongside the horizontal
sheets from the same `MoEProgressView.html` / `MoEEfficiencyView.html`, with `goVertical()` in
`MoEProgress.js` / `MoEEfficiency.js` doing the DOM half and `MoEBarTransient.js` doing the shared
surface/shift/run-identity half — but the **tuners themselves stay dev-only** (no res_map entry,
no shipped HTML): they are still where every proportion, timing and Large-mode value was settled
and where a future re-tune happens, exactly like the horizontal tuners for the horizontal sheets.
Every proportion is an exact **axis-swap** of the shipped `MoEProgress.css` / `MoEEfficiency.css`; a
rotation preserves stroke weights, only the axes trade places. Axis convention on both: **0% at the
BOTTOM, 100% at the TOP**, fill grows via `height` from `bottom: 0`, and every marker centres with
**`translateY(+50%)`** — the `+`, not the horizontal bars' `-50%`: a `bottom`-anchored box shifts
back DOWN by half its own length.
```
pwsh tools\dev\gen_bar_tuner_vertical.ps1 [-Out TASKS/refs/in-battle-bar-tuner-vertical.html]
                     [-Backdrop <any image>] [-GameDir <dir>] [-ExtractIcons] [-SelfCheck]
                     [-EmitCss [-CssOut TASKS/refs/MoEProgressVertical.css]]
                     [-Artifact [-ArtifactOut TASKS/refs/in-battle-bar-tuner-vertical.artifact.html]]
node tools\dev\check_bar_vertical.js          # the progress tuner's gate (~150 assertions)
node tools\dev\make_eff_vertical_artifact.js  # regenerate the efficiency tuner's artifact twin
node tools\dev\check_eff_vertical.js          # the efficiency tuner's gate + its own selfCheck()
```
- `gen_bar_tuner_vertical.ps1` — the vertical **MoE progress bar**. Class prefix **`.mpv-*`**, root
  **`#moe-bar-root`** (the prefix, never `.mp-`, is what keeps the emitted CSS from colliding with
  the shipped horizontal bar). Sibling of `gen_bar_tuner.ps1`, **not a flag on it** — same reason
  `gen_overlay_tuner.ps1` / `eff_bar_tuner.html` are separate files. **`-EmitCss` writes a real
  file** (`TASKS/refs/MoEProgressVertical.css`, gitignored) by running the generated `<script>` in a
  headless DOM shim and clicking the real **Copy CSS** handler, exactly as the horizontal tuner
  does, so the bytes are the button's bytes. `-Artifact` writes a skeleton-free twin (no
  `<!DOCTYPE>/<html>/<head>/<body>`) for publishing as a Claude Artifact, **derived from the same
  `$tpl`** so the two cannot drift. Adds a mock **minimap** to the stage (bottom-right, zero inset,
  sizes from `measure_minimap.py`'s measured table) plus `stageW`/`stageH`/`mmIdx`/`mmGap`/
  `mmGapBottom`: that placement math is **preview-only and never reaches the emitted CSS** — in-game
  the window is positioned from Python via `window.move()`, same as the horizontal bar's `offX/offY`.
- `eff_bar_tuner_vertical.html` — the vertical **Damage Efficiency bar**, hand-authored (a rename
  clone of `eff_bar_tuner.html`). Class prefix **`.mev-*`**, root **`#mev-bar-root`**. It has **no
  `-EmitCss` equivalent and no emit script**: CSS comes out of its in-page **Copy CSS** button only,
  clipboard-only by design. **Do NOT point `tools/dev/emit_eff_css.js` at it** — that script targets
  the HORIZONTAL tuner **by literal filename** and writes the shipped `src/…/MoEEfficiency.css`,
  so aiming it here would overwrite the shipped horizontal stylesheet with vertical CSS.
  `make_eff_vertical_artifact.js` regenerates the publishable twin
  (`eff_bar_tuner_vertical.artifact.html`) — **run it after every tuner edit**, since
  `check_eff_vertical.js` rebuilds it in memory and fails loudly on a stale one.
- Both gates assert **emitted values** in a headless DOM shim, not file size (`-SelfCheck` still
  only checks size + leftover `__TOKEN__`s, per `bar-tuner-selfcheck-is-not-a-gate`).
  `check_bar_vertical.js` additionally pins `cssOut()` at the SCHEMA defaults **byte-for-byte**
  against the checked-in `TASKS/refs/MoEProgressVertical.css`, so **re-run `-EmitCss` after any
  generator edit** or the gate fails on the stale artifact.
- **The re-trigger twin is EMITTED, not hand-added.** Both tuners emit a second, byte-identical
  keyframe (`mpv-life-b` / `mev-life-b`) plus its own run class (`.mpv-run-b` / `.mev-run-b`) from
  **one builder called twice**, so the pair cannot drift — unlike the shipped `MoEProgress.css`,
  whose `mp-life` / `mp-life-b` pair is kept identical by hand. The JS alternates the two names
  (`MoEBarTransient.js` `RUN_CLASSES`/`RUN_NAMES`) because a baked fade/hold/fade keyframe **cannot
  be re-triggered in place**; without the pair the bar cannot re-raise for a second battle event.
- **The `.mpv-lg` / `.mev-lg` Large-size blocks are emitted too**, mirroring the shipped `.mp-lg`
  blocks. The size mode is delivered by the **root font size** (`SIZE_F` 1.25), so only a
  **cross-axis (screen-x)** length owes the extra `SIZE_XF` = **4/3** — pure `SIZE_XF`, never
  `SIZE_F` (verified against all nine shipped `.mp-lg` values). Because the axes are swapped, "x
  length" now names the *cross* axis: track thickness, tick cross-spans, backdrop `left`/`width`,
  caption `padding-right`/`translateX`, the icon and delta gaps. The bar **length**, tick
  thicknesses, fonts, vertical gaps and the **dash grid** take **no rule**: restating one would
  double-apply `SIZE_F`. Neither block is compound; the pair that must be compound is the
  interface-scale one (`.mp-s1.mp-lg`), and neither tuner emits an `.mpv-s1`/`.mev-s1` rule at all.
- **Both dash grids are `0deg`** ("to top"), so the first stop sits at the track's BOTTOM edge and
  the period runs ALONG the bar's length — a dashed mask across the axis. The efficiency tuner
  originally inherited the horizontal bar's **`90deg`** + `background-size: <period>rem 100%`, where
  the period ran ACROSS a 3rem-wide track — narrower than one 3rem period, i.e. a single stripe, not
  a grid; rotated, and its `.mev-lg` twin **deleted** rather than rescaled, because a `0deg` grid's
  period is a **y**-length the root font already scales. The gate asserts that **absence**, not just
  the presence of the base rule. Both tuners now carry the period in the gradient's own rem stops
  with **no `background-size`**.
  The one remaining difference is deliberate: the dash-**gap alpha** is `gapA` **0.5** in the
  progress tuner (the horizontal tuner's own tuned default, which shipping hand-rewrites to opaque)
  and an opaque **1** in the efficiency tuner. Not a tuner concern — leave both alone.
- The in-browser **digit-count invariance** check (`checkCaptionInvariance()` in the progress tuner;
  the equivalent inside the efficiency tuner's `selfCheck()`) needs a real layout engine and
  **SKIPs** under both headless shims — visibly, and the gates assert the skip **fires**, not that
  the check passes. Open the published artifact and press **Self-check** to actually run it.
  The caption anchoring it guards is a hard contract: **one shared fixed `right: 100%`** on the base
  `.mpv-cap` / `.mev-cap` rule with the icon and delta as **in-flow flex children**. A nudge
  computed off a caption box's own content width is the bug this replaces.

### The shipped vertical CSS is "emit + exactly 5 hand-edits" — `check_vertical_css_handedits.js`
Both shipped stylesheets are their tuner's emit **plus exactly five documented hand-edits** (each
marked `HAND-EDIT n/5` at its site in the CSS's own header/comments): the root rule's scoping +
absolute positioning, a `#moe-bar-box` sizing shim the tuner never emits, the dash-gap stripe
forced to opaque `rgba(...,1)`, `.mpv-lg`/`.mev-lg` renamed to the shared `.mp-lg` (the body class
`MoEBarTransient.applySize` actually writes), and the two Large-mode root/box rules re-scoped to
`body.mpv.mp-lg` / `body.mev.mp-lg`. Until this gate existed those five were enforced by comment
only — a careless re-emit-and-paste (the exact mistake `emitcss-is-not-the-whole-shipped-
stylesheet` records for the horizontal sheets) silently reverts any of them with no signal.
```
node tools\dev\check_vertical_css_handedits.js                 # exits 1 on any drift
node tools\dev\check_vertical_css_handedits.js --probe-all      # every mutation, as a table
node tools\dev\check_vertical_css_handedits.js --list-mutations
node tools\dev\check_vertical_css_handedits.js --mutate=<key>   # anti-vacuity: MUST report failures
```
It regenerates a **fresh emit** for each bar — `gen_bar_tuner_vertical.ps1 -EmitCss` (a real,
non-selfcheck CSS file) for the progress bar; for the efficiency bar, which has **no `-EmitCss`
switch**, the same headless `cssOut()`-evaluation technique `check_eff_vertical.js` already uses
(read the tuner as text, cut at its `// ---- panel wiring` marker, evaluate with `new Function`
against a stub DOM) — then applies each hand-edit as a **pinned, ordered text edit** (the emit's
exact "before" text is asserted present, not just assumed) and diffs the fully-edited result
against the shipped file, comments and blank lines stripped. Any drift beyond the five edits fails
the same comparison. Two traps it is built to avoid: the gap-alpha edit is scoped to
**`.mpv-track::after`'s gradient stops only** — the same rule's `box-shadow` ring is legitimately
`rgba(13,14,16,0.5)` and must never move; and the `.mpv-lg`/`.mev-lg` **absence** check strips
comments first, since both names legitimately appear inside the very comments that document their
own rename.
**What it deliberately does not check**: the hand-edit *values* against any other source of truth
(those are cross-checked by `check_bar_vertical.js` / `check_eff_vertical.js` / the Python
positioning tests) — only that the shipped file equals "emit + exactly these edits, nothing else."
It does not touch the horizontal sheets' own hand-edit sets.

### The vertical DOM/surface/run-identity path — `check_bar_orientation_js.js`
`check_progress_js.js` / `check_efficiency_js.js`'s hundreds of assertions read `.mp-*` literals
that `ns()` rewrites into the live prefix at runtime, so they stayed green through the whole
vertical port and verify **nothing** about the vertical branch. `check_bar_orientation_js.js`
covers that gap, sharing the same `lib/gf_check_shim.js` idiom:
```
node tools\dev\check_bar_orientation_js.js
node tools\dev\check_bar_orientation_js.js --probe-all
node tools\dev\check_bar_orientation_js.js --list-mutations
node tools\dev\check_bar_orientation_js.js --mutate=<key>
```
Both bars, both drive the same assertions: `goVertical()` / `V_MARKUP` actually building the
vertical DOM (and a horizontal mount staying unaffected), the `V_BOX_*` → `resizeViewRem` surface
push **and its post-deadline re-assert** (pushing once is not enough — the engine's 256×256
size-timeout fallback runs last and wins), the orientation profile (`AX`/`GROW`/`CAP_C_AX`
resolving to `bottom`/`height`/`null` vertically), the `mpv-run`/`mev-run` identity pair (never
`mp-run`), the twin `-b` alternation restarting a second run, and the `animationend` name filter
following the orientation. The harness's one addition over the two horizontal gates: `window.model`
starts **empty** and is only populated the instant `engine.whenReady` resolves — mirroring the real
client's timing — so a hypothetical regression that hoists the `vertical` read to module scope
(instead of inside `whenReady`, per the port's own rule) would see `{}` and mount horizontal
regardless, which the DOM-build assertions then catch.

## Minimap rect measurement (offline, no client during analysis)
The in-battle minimap's size-index -> pixel mapping is compiled AS3 with no Python
accessor, so its on-screen rect (esp. the bottom-left corner) is recovered by diffing
screenshots, not by reading a symbol:
```
python tools\dev\measure_minimap.py --hidden baseline.png --shots s0.png s1.png s2.png s3.png s4.png s5.png [--scale 1.5] [--json out.json]
python tools\dev\measure_minimap.py --selfcheck    # assert-based self-test, no screenshots needed
```
Capture procedure (module docstring has the full version): pause a replay with Space,
toggle the minimap off and screenshot (`--hidden`), toggle it on and cycle its size
hotkeys through all 6 indices, screenshotting each (`--shots`, ascending index) — all 7
at the SAME paused frame, camera untouched. WoT writes to the install dir's
`screenshots/` folder. Device px is the durable output (`inset_x`/`inset_y` from the
image's bottom-left edge); `--scale` (interface scale) adds a separate logical-px
column. Reports a changed-pixel mask (not just a bbox) with `fill_ratio` and flags any
secondary cluster (noise / unpaused frame) LOUDLY instead of unioning it into the bbox,
and warns on a non-monotonic size sequence, a near-whole-image bbox (wrong frame pair),
or a bbox outside the bottom-left quadrant.

## Decompiled source (re-clone as needed; not in repo)
Match the client's branch/region — use the branch matching your client's major
version (e.g. the `2.3.1.1` major line):
```
& $git clone --depth 1 --branch <major> --single-branch https://github.com/StranikS-Scan/WorldOfTanks-Decompiled.git wot-eu
```
(The repo's default branch is a different regional client — cross-check against
the live `res/packages/scripts.pkg` by listing module filenames.)
