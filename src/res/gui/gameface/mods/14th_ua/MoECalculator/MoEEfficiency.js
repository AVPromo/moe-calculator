// 14th_ua's MoE Calculator -- in-battle centre-screen DAMAGE EFFICIENCY bar. Front-end of a
// STANDALONE OpenWG-registered Gameface view (MoEEfficiencyView.html, registered via
// mods/configs/res_map/MoEEfficiencyView.json) that bridge/efficiency_view.py opens as a
// CONTENT-SIZED (NOT full-screen), input-transparent window centred over the battle HUD. Do NOT
// re-add full-screen sizing / width:100% -- see bridge/battle_view.py for the Ctrl+click/hover
// input-steal that cost us.
//
// THIS IS THE RADIO ALTERNATIVE to the Moving Average bar (MoEProgress.js): Python opens exactly
// ONE of the two, which is the only reason both stylesheets can own #moe-bar-root and the .mp-*
// prefix. Never <link> both in one document.
//
// Because this is a registered view, OUR data model (EfficiencyVM) IS the view's own root
// ViewModel: a bare ModelObserver() with NO feature name, fields read DIRECTLY off the root
// (model.damage, ...). No nested submodel and NO unwrap dance -- that is only the garage's
// nested-model path.
//
// WHAT THE BAR SHOWS: THIS battle's combined damage plotted against all FOUR of the tank's mark
// requirements at once -- five damage stops [0, r65, r85, r95, r100] mapped onto four visually
// EQUAL quarters. The four requirement ticks/captions are pinned at 25/50/75/100 % in the CSS;
// only the fill, the current tick and its caption are positioned from here.
//
// AND THE AXIS ARITHMETIC IS NOT DONE HERE. Unlike MoEProgress.js (which derives its position from
// the pushed axis ends), Python pushes `barX` (0..100 % of the bar) and `band` (0..4, the highest
// requirement PASSED, `>=` INCLUSIVE) as finished values -- domain/battle_builder.efficiency_bar_x
// and efficiency_band. Do NOT recompute either here: the inclusive-boundary rule must live in
// exactly one place, and it is unit-tested there. The four r* props are for the CAPTION NUMERALS
// only. `.met` on a requirement tick likewise comes off `band` (stop i is met iff i <= band), not
// off a damage comparison.
//
// THE LOOK IS THE TUNER'S AND NOT NEGOTIABLE: MoEEfficiency.css is tools/dev/eff_bar_tuner.html's
// emit verbatim (reproducible with `node tools/dev/emit_eff_css.js`) plus two marked hand-added
// blocks, and this file is a port of that tuner's own preview pass (apply / showDelta / replay)
// crossed with MoEProgress.js's proven transient machinery. Every number below is mirrored from
// that stylesheet's trailing JSON `meta` block. The battle window has NO hot-reload (it pins its
// resources at client launch), so every tweak here costs a full client relaunch: tune in the
// browser, not in the client.
//
// pointer-events:none throughout (in the CSS) -- pure HUD info, never an input target.
import { ModelObserver } from "../../libs/model.js";
// The transient machinery -- arming, the negative-delay debounce, the Alt peek's pause/seek, the
// end race and the surface re-assert -- is SHARED with MoEProgress.js. Every behaviour in there cost
// a client relaunch to find; read its header before changing anything that touches timing.
// Separate documents, so this module is instantiated twice with no cross-talk.
import { createTransient, fmt } from "./MoEBarTransient.js";

// No feature name -> observe this view's OWN root model (window.model == EfficiencyVM).
const observer = ModelObserver();

// meta.deltaHoldMs -- the delta's OWN, SHORTER window, this bar's only timing of its own. It is not
// tied to the transient at all (that is the tuned intent: the increment is a flash, the bar is a 5s
// readout), so it fades on .mp-d's own 500ms opacity transition well before the bar leaves.
const DELTA_HOLD_MS = 1600;

// --- the axis / clamp contract, also from `meta` ----------------------------------------------
// The bar's own width (#moe-bar-root), which every percentage resolves against and which the cap
// clamp works in. meta.capClamp is the corridor the current caption may not leave, in the SAME
// document-rem coordinates: the box is the 300rem track plus 80rem of pad each side, minus the
// tuned 4rem end inset, i.e. [-76, 376].
const BAR_W_REM = 300;
const CLAMP_L_REM = -76;             // meta.capClamp.leftRem
const CLAMP_R_REM = 376;             // meta.capClamp.rightRem
// The icon's gap to the numeral, which rides in .mp-ico's transform (translate(-1rem, -50%)) and
// so is NOT part of its offsetWidth -- the clamp has to add it back, exactly as the tuner does.
const ICO_GAP_REM = 1;
// band -> the ONE class that goes on #moe-bar-root, in meta.bands order (white/green/teal/violet/
// gold). Python's `band` indexes straight into this.
const BAND_CLASSES = ["mp-b-w", "mp-b-g", "mp-b-t", "mp-b-v", "mp-b-au"];

// --- the surface, and the rigid shift into it ----------------------------------------------
// A Gameface view PUSHES its own size to C++ through the `viewEnv` global
// (viewEnv.resizeViewRem(w, h), rem == logical px); a view that never calls it gets the engine's
// "default view size" fallback after a `Size calculation timeout` -- a flat 256x256 logical px.
// There is NO Python-side and NO res_map lever for this (see bridge/efficiency_view.py), and
// pushing the size is not sufficient on its own: the engine ALSO tries to measure the document and
// ITS FALLBACK RUNS LAST AND WINS. See SURFACE_REASSERT_MS.
//
// The composition's bounding box, document origin at (0,0) and 1rem == 1 logical px, IS
// .mp-backdrop -- left -80rem / top -40rem / 460 wide / 96 tall (MoEEfficiency.css; the emitted
// value, asserted by tools/dev/check_eff_css.js). Everything else fits inside it with
// room to spare, measured against the emit rather than guessed:
//   * TOP: the .mp-cap.up numeral's box bottom sits at -11rem (bottom:100% of the 3rem track, then
//     translateY(-11rem)), so at a 16rem font its top is ~-30 and its 6rem band glow reaches ~-36.
//     Its out-of-flow glyph and the current tick's 6rem glow are shallower still.
//   * BOTTOM: .mp-cap.dn tops out at 12rem (top:100% + margin-top:9rem) and is 12rem tall -> ~26.
//   * SIDES: .mp-cap.r4 sits at 100 % (x == 300) and the current caption's delta hangs off its
//     right edge, reaching ~375 at four digits -- which is precisely why meta.capClamp's right
//     bound is 376. The clamp below keeps it there whatever the digits do.
// So the surface is that box plus PAD_REM of slack on all four sides, and the whole composition is
// rigidly translated by that much so NOTHING sits at a negative coordinate -- an origin overflow
// is clipped no matter how big the surface is.
//
// NOT A THIRD COPY: MoEProgressView.html's sizing shim is sized to that bar's surface, but THIS
// document's #moe-bar-box is 460x51rem straight out of the tuner's emit (the bar plus its two
// caption rows). Leave it emitted -- the box provably does not stop the size timeout anyway, so
// its exact value buys nothing, and hand-editing it would be silent drift from the emit.
// These five ARE this bar's surface contract and stay HERE, per bar. MoEBarTransient derives the
// rest from them (its box*/pad arguments), exactly as this file used to:
//   VIEW_W_REM = BOX_W_REM + 2 * PAD_REM == 480     SHIFT_X_REM = PAD_REM - BOX_LEFT_REM == 90
//   VIEW_H_REM = BOX_H_REM + 2 * PAD_REM == 116     SHIFT_Y_REM = PAD_REM - BOX_TOP_REM  == 50
// SHIFT_Y_REM is MIRRORED (negated, plus the fraction-unit term) in Python as
// domain/constants.EFFICIENCY_ANCHOR_Y_OFFSET, so changing BOX_TOP_REM or PAD_REM moves the bar on
// screen until that constant follows. The hit padding and the re-assert timing live in the shared
// module (its HIT_MAGIC / SURFACE_REASSERT_MS -- both LOAD-BEARING, read its header).
const BOX_LEFT_REM = -80;                            // .mp-backdrop's left  == leftmost edge
const BOX_TOP_REM = -40;                             // .mp-backdrop's top   == topmost edge
const BOX_W_REM = 460;                               // .mp-backdrop's width  (== meta.boxWRem)
const BOX_H_REM = 96;                                // .mp-backdrop's height
const PAD_REM = 10;                                  // slack for the shadow/glow bleed

// Build the root once and cache it. Markup shape is the tuner's stage verbatim
// (eff_bar_tuner.html:333-351): backdrop, then the track carrying the fill, the four FIXED
// requirement ticks, the one moving current tick, the four requirement captions (three marksOnGun
// glyphs + the barrel_mark at 100 %) and the current caption with its BARE signed delta -- no
// parens on this bar, unlike the Moving Average one. The .mp-d / .mp-d-num split stays anyway: the
// wrapper carries the gap, size and fade, the inner numeral is what JS writes the digits into (see
// the CSS). NO word labels anywhere: MoEBattle.ttf is a 19-glyph numeric subset
// (digits % ( ) + - , . / space) and a letter renders BLANK.
function ensureRoot() {
    let root = document.getElementById("moe-bar-root");
    if (root) return root;
    root = document.createElement("div");
    root.id = "moe-bar-root";
    root.innerHTML =
        '<div class="mp-backdrop"></div>' +
        '<div class="mp-track">' +
        '  <div class="mp-fill"></div>' +
        '  <div class="mp-tick mp-req r1"></div>' +
        '  <div class="mp-tick mp-req r2"></div>' +
        '  <div class="mp-tick mp-req r3"></div>' +
        '  <div class="mp-tick mp-req r4"></div>' +
        '  <div class="mp-tick mp-cur"></div>' +
        '  <div class="mp-cap dn r1"><i class="mp-ico mk mk1"></i>' +
        '<span class="mp-v"></span></div>' +
        '  <div class="mp-cap dn r2"><i class="mp-ico mk mk2"></i>' +
        '<span class="mp-v"></span></div>' +
        '  <div class="mp-cap dn r3"><i class="mp-ico mk mk3"></i>' +
        '<span class="mp-v"></span></div>' +
        '  <div class="mp-cap dn r4"><i class="mp-ico bm"></i>' +
        '<span class="mp-v"></span></div>' +
        '  <div class="mp-cap up mp-capC"><i class="mp-ico dmg"></i><span class="mp-v"></span>' +
        '<span class="mp-d"><span class="mp-d-num"></span></span></div>' +
        '</div>';
    document.body.appendChild(root);
    return root;
}

const root = ensureRoot();
const fill = root.querySelector(".mp-fill");
const tCur = root.querySelector(".mp-tick.mp-cur");
const reqTicks = [1, 2, 3, 4].map(function (i) { return root.querySelector(".mp-tick.r" + i); });
const reqCaps = [1, 2, 3, 4].map(function (i) { return root.querySelector(".mp-cap.r" + i); });
const capC = root.querySelector(".mp-cap.up");
const capD = capC.querySelector(".mp-d");
const capDN = capC.querySelector(".mp-d-num");

function capV(c) { return c.querySelector(".mp-v"); }

// --- the pushed state ---------------------------------------------------------------------
// `cur` is the latest push; `last` is the previous one. `last === null` means "no baseline yet":
// the FIRST push after mount (and after any re-show) seeds the latch silently, so the bar does not
// appear at battle start. (There is deliberately no `rev` counter on EfficiencyVM -- the battle
// window is a private, always-compositing view and has never needed the garage's cold-mount signal.)
let cur = { damage: 0, barX: 0, band: 0, r: [0, 0, 0, 0], battleEpoch: 0 };
let last = null;

// --- THE DELTA LATCH (derived HERE; EfficiencyVM carries no damageDelta) --------------------
// `peak` is the HIGH-WATER mark of this battle's combined damage, deliberately NOT the previous
// push's value: combined damage SUBTRACTS team damage, so the total can move DOWN, and the latch
// must measure only the rise above the highest total already seen -- a friendly-fire dip followed
// by a hit reports the gain over the old peak, never the dip plus the hit. `delta` then PERSISTS
// until superseded, because an efficiency tick that moved nothing (a spot, a dip, an arena period
// change, an Alt press) must keep showing the increment the player is reading; 0 == none yet.
//
// A NEW HIGH-WATER MARK IS ALSO THE ONLY THING THAT MAY POP THE BAR OPEN (see `gained` in render).
// "The value changed" and "the player gained damage" are NOT the same event: team damage
// subtracting from the combined total changes the value, and re-showing the bar for it would
// re-flash an increment the player has already read, carrying no new information.
//
// `epoch` is the battleEpoch `peak`/`delta` belong to. Python bumps a monotonic counter once per
// battle mount (bridge/battle_bridge._battle_epoch) and pushes it on every efficiency tick, so a
// change in it IS the battle boundary -- there is no longer any inference from the total having
// restarted low (battle N+1's first tick can read higher than battle N's peak, and then an Alt peek
// early in N+1 rendered N's stale increment). It deliberately does NOT live in `last`: a hide drops
// that baseline mid-battle, while the latch has to survive one. 0 == the counter's value before the
// first battle, so the first push of the first battle resets an already-empty latch for free.
//
// NO COMPARISON MAY NAME `damage` ON ITS OWN LINE. tools/dev/check_efficiency_js.js scans the
// comment-stripped source for a comparison operator sharing a line with `damage` or an r* stop,
// because the rule it guards is that the `>=`-INCLUSIVE damage-vs-REQUIREMENT test lives in Python
// (domain.efficiency_band) and nothing here may re-derive it. This latch is damage-vs-damage and
// touches no requirement, so it reads the total into `total` first and compares THAT.
let peak = 0;
let delta = 0;
let epoch = 0;

// The delta's own fade-out timer -- this bar's ONLY animation state of its own. Everything else
// (arming, the run clock, the peek pause/seek, the end race, the surface settle) lives in the shared
// transient below.
let deltaT = null;

// The current caption may not leave the box: it is centred on its tick, but its glyph hangs off the
// left and its delta off the right, so at 100 % the delta would overflow. Reproduces the tuner's
// capLeft() (eff_bar_tuner.html:716-729) in meta.capClamp's rem corridor -- and .mp-cap's
// offsetWidth is the NUMERAL only (the icon and the delta are out of flow), which is why the larger
// of the two overhangs is added back, the icon's with its transform gap. 1rem == 1 logical px in
// Gameface, so offsetWidth needs no scale division. A zero measured width (nothing laid out yet)
// simply degrades to no clamp.
function capClampPct(p) {
    const w = function (q) { const n = capC.querySelector(q); return (n && n.offsetWidth) || 0; };
    const half = (capC.offsetWidth || 0) / 2 +
                 Math.max(w(".mp-ico") + ICO_GAP_REM, w(".mp-d"));
    const lo = CLAMP_L_REM + half;
    const hi = CLAMP_R_REM - half;
    let x = p / 100 * BAR_W_REM;
    if (lo <= hi) x = Math.max(lo, Math.min(hi, x));
    return x / BAR_W_REM * 100;
}

// Position the fill, the moving tick and its caption from the PUSHED barX (never recomputed here).
// No rewind/snap variant and no transition suppression, unlike MoEProgress.setPos: this bar has a
// single set of values, so the CSS's 400ms fill/left transitions may always run -- exactly what the
// tuner's own hit() does. On a cold entry they run under the 600ms fade-in and are invisible.
function setPos(x) {
    const p = x.toFixed(3) + "%";
    fill.style.width = p;
    tCur.style.left = p;
    capC.style.left = capClampPct(x).toFixed(3) + "%";
}

// Everything that does NOT animate: the four requirement numerals, which of them are met, the band
// class and the 100 % pulse, and the current numerals. Safe to re-run on every push.
// `.met` AND the band come off the PUSHED `band` index -- stop i (1-based) is met iff i <= band.
// That is not a shortcut: it is how the `>=`-inclusive rule stays in Python only.
function paintStatic() {
    for (let i = 0; i < 4; i++) {
        capV(reqCaps[i]).textContent = fmt(cur.r[i]);
        reqTicks[i].classList.toggle("met", i + 1 <= cur.band);
    }
    BAND_CLASSES.forEach(function (c, i) { root.classList.toggle(c, i === cur.band); });
    // The pulse rule is #moe-bar-root.mp-b-au.mp-pulse .mp-track, so this class is inert off gold
    // anyway -- gate it on the band regardless, so the DOM says what it means.
    root.classList.toggle("mp-pulse", cur.band === 4);
    capV(capC).textContent = fmt(cur.damage);
    capDN.textContent = (delta > 0 ? "+" : "") + fmt(delta);
}

// The delta SNAPS in on a hit, holds for its own DELTA_HOLD_MS, then fades out on .mp-d's 500ms
// opacity transition. The snap is the shipped cancel idiom (transition:none -> set -> force a
// reflow -> hand the transition back) so the appearance is instant AND a half-finished fade from
// the previous hit can never bleed into this one. Ported from the tuner's showDelta()
// (eff_bar_tuner.html:736-741). Only a GAIN (a new high-water mark) calls this -- an Alt peek, a
// flat tick and a team-damage dip all show the latched numerals without re-flashing an increment
// that already had its moment.
function showDelta() {
    clearTimeout(deltaT);
    capD.style.transition = "none";
    capD.classList.add("on");
    void root.offsetWidth;
    capD.style.transition = "";
    deltaT = setTimeout(function () { capD.classList.remove("on"); }, DELTA_HOLD_MS);
}

// THE TRANSIENT. Everything shared with MoEProgress.js -- arming and its negative-delay debounce,
// the run clock, the Alt peek's pause/plateau-seek/resume, the animationend-vs-timer end race, the
// surface push + re-assert. This bar needs only ONE of the hooks: a tail on endRun/reset to drop the
// delta, so a hold longer than the transient cannot leave it showing on the next entry.
// NO onRewind and NO onCommit: unlike the Moving Average bar this one has a single set of values, so
// there is nothing to rewind before a cold entry and nothing to commit after it -- the CSS's 400ms
// fill/left transitions may always run, exactly as the tuner's own hit() does (see setPos).
const T = createTransient({
    root: root,
    boxLeft: BOX_LEFT_REM,
    boxTop: BOX_TOP_REM,
    boxW: BOX_W_REM,
    boxH: BOX_H_REM,
    pad: PAD_REM,
    onEnd: dropDelta,
    onIdle: dropDelta,
});

function dropDelta() {
    clearTimeout(deltaT);
    capD.classList.remove("on");
}

function render(model) {
    // Truthy guards, not `=== false`: a root VM whose flags are still undefined before Python's
    // first push must stay hidden, not paint a zero-width bar over the HUD. hasData false means the
    // per-tank threshold table gave no usable five-stop axis -- there is nothing to plot. (Note the
    // documented asymmetry: the battle path has no offline estimator fallback, so on a tank whose
    // WG fetch failed this stays blank while the garage bar still draws. Not a bug here.)
    if (!model || !model.visible || !model.hasData) {
        root.style.display = "none";
        T.reset();
        // Drop the change-detect baseline too, so a later re-show starts COLD and the next push
        // becomes a fresh silent one (a scoreboard opening and closing must not replay the bar).
        // `peak` / `delta` deliberately SURVIVE -- render()'s first-push branch re-seeds them.
        last = null;
        return;
    }
    root.style.display = "";

    cur = {
        damage: Number(model.damage) || 0,
        barX: Number(model.barX) || 0,
        // Clamped defensively to the classes that exist -- an out-of-range index would otherwise
        // leave the root with NO band class and an unstyled (invisible) fill.
        band: Math.max(0, Math.min(BAND_CLASSES.length - 1, Number(model.band) || 0)),
        r: [Number(model.r65) || 0, Number(model.r85) || 0,
            Number(model.r95) || 0, Number(model.r100) || 0],
        battleEpoch: Number(model.battleEpoch) || 0,
    };

    const first = last === null;
    last = cur;

    // The latch (see `peak`), run BEFORE paintStatic because that is what writes the numeral. The
    // two reset cases are told apart by the PUSHED epoch, not inferred from the total:
    //   * a re-show MID-BATTLE (a scoreboard closing, hasData arriving) -- same epoch, so the mark
    //     is re-seeded off the current total (nothing is claimed for damage dealt while this
    //     document was not watching) and the latched increment survives, exactly as the Python
    //     latch survived a hide;
    //   * a NEW BATTLE -- a different epoch, so the previous battle's increment is dropped, which is
    //     what _on_mount_refresh used to do. Deliberately 0 and not "the whole accumulated total as
    //     one increment": the first tick of a battle is not a hit.
    // `gained` is the SHOW/FLASH trigger and only a new high-water mark sets it -- a flat push or a
    // dip repaints below (paintStatic/setPos always run) but must not pop the bar or re-flash.
    const total = cur.damage;
    const newBattle = cur.battleEpoch !== epoch;
    epoch = cur.battleEpoch;
    let gained = false;
    if (newBattle) delta = 0;
    if (first || newBattle) {
        peak = total;
    } else if (total > peak) {
        delta = total - peak;
        peak = total;
        gained = true;
    }

    paintStatic();
    setPos(cur.barX);

    // THE SHOW TRIGGER IS GATED ON T.settled(); the silent baseline above is NOT. Before the
    // re-assert the surface is the engine's 256x256 fallback: the bar would come up cropped and
    // badly mis-placed (see the shared module's SURFACE_REASSERT_MS). The baseline shows nothing, so
    // it costs nothing to let it run -- and it MUST run, or `last` never gets recorded and the first
    // real hit is missed. T.show() picks warm-vs-cold off its own `showing`.
    if (gained && T.settled()) {
        showDelta();
        T.show();
    }

    // Alt is handled AFTER the value change so a push that carries both (Python re-pushes on every
    // Alt transition) gets the new target AND the peek hold. An Alt held BEFORE the surface settled
    // is not lost: the settle re-renders the current model, which arrives here with altHeld still
    // true and peeks then.
    T.peek(!!model.altHeld);
}

// The rigid translation into the surface, the surface push + its post-deadline re-assert, then the
// model subscription and the first render -- all in T.mount (see the shared module).
T.mount(observer, render);
