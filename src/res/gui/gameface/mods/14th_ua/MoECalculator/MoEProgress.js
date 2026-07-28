// 14th_ua's MoE Calculator -- in-battle centre-screen MoE progress bar (the TRANSIENT one; the
// always-on corner readout is MoEBattle.js). Front-end of a STANDALONE OpenWG-registered Gameface
// view (MoEProgressView.html, registered via mods/configs/res_map/MoEProgressView.json) that
// bridge/progress_view.py opens as a CONTENT-SIZED (NOT full-screen), input-transparent window
// centred over the battle HUD. Do NOT re-add full-screen sizing / width:100% -- see
// bridge/battle_view.py for the Ctrl+click/hover input-steal that cost us.
//
// Because this is a registered view, OUR data model (ProgressVM) IS the view's own root
// ViewModel: a bare ModelObserver() with NO feature name, fields read DIRECTLY off the root
// (model.projAvg, ...). No nested submodel and NO unwrap dance -- that is only the garage's
// nested-model path.
//
// WHAT THE BAR SHOWS: where the career moving-average combined damage sits between the
// requirement for the mark you HOLD and the requirement for the next one, and the nudge THIS
// battle contributes. Everything derived here is derived in COMBINED DAMAGE, not percentiles:
// Python pushes the two axis ends plus pre_avg / proj_avg and this file does the arithmetic.
//
// THE LOOK IS FINISHED AND NOT NEGOTIABLE: MoEProgress.css was settled in a browser tuner
// (tools/dev/gen_bar_tuner.ps1) and copied verbatim, and this file is a port of that tuner's own
// preview script (setPos / showVal / replay / the animationend force-settle) -- not an
// invention. Its comments explain every value; read them before changing a number. The battle
// window has NO hot-reload (it pins its resources at client launch), so every tweak here costs a
// full client relaunch: tune in the browser, not in the client.
//
// pointer-events:none throughout (in the CSS) -- pure HUD info, never an input target.
import { ModelObserver } from "../../libs/model.js";

// No feature name -> observe this view's OWN root model (window.model == ProgressVM).
const observer = ModelObserver();

// --- the transient's timings, from MoEProgress.css's trailing JSON block -------------------
// Kept as constants rather than read from the CSS: Gameface gives no reliable way to read a
// keyframe's stops, and these three numbers ARE the contract with the stylesheet. If a timing
// changes in the tuner, change it in BOTH places.
const FADE_IN_MS = 600;      // == the 9.68% keyframe stop of mp-life (600/6200)
const HOLD_MS = 5000;
const FADE_OUT_MS = FADE_IN_MS;    // fadeOutMs == fadeInMs in the tuned JSON
const TOTAL_MS = FADE_IN_MS + HOLD_MS + FADE_OUT_MS;   // == mp-life's own 6200ms duration
const VALUE_SWAP_MS = FADE_IN_MS;  // valueSwapMs tracks tickDelayMs by construction

// How far to seek INTO mp-life, in ms, when arming a run (armRun turns these into a NEGATIVE
// animation-delay, which starts the animation already that far along without replaying its
// entry). Verified against the emitted keyframes (MoEProgress.css @keyframes mp-life): the stops
// are 0 / 9.68 / 90.32 / 100 of a 6200ms animation, i.e. 0 / 600.16 / 5599.8 / 6200 ms.
//   600  == the 9.68% stop (within 0.2ms): opacity 1 and translateY(0rem) both COMPLETE, so the
//           bar sits exactly at the hold plateau and does not re-flash or re-slide.
//   5600 == the 90.32% stop: the instant the fade-out begins.
const SEEK_NONE = 0;
const SEEK_PLATEAU = FADE_IN_MS;
const SEEK_FADE_OUT = FADE_IN_MS + HOLD_MS;

// --- the surface, and the rigid shift into it ----------------------------------------------
// A Gameface view PUSHES its own size to C++ through the `viewEnv` global
// (viewEnv.resizeViewRem(w, h), rem == logical px); a view that never calls it gets the engine's
// "default view size" fallback after a `Size calculation timeout` -- a flat 256x256 logical px,
// which is what clipped this bar. WG precedent for the same window shape: DogTagMarkerView.js
// calls resize(500, 300, "rem") once on mount, and ~85 WG views do the same. There is NO
// Python-side and NO res_map lever for this (see bridge/progress_view.py).
//
// BUT THE ENGINE ALSO TRIES TO MEASURE THE DOCUMENT, AND ITS FALLBACK RUNS LAST AND WINS. Pushing
// the size is not sufficient on its own: our resize landed at 04.8s, the size-calculation deadline
// expired at 06.2s and its action ("Set the default view size") overwrote our pushed size with the
// 256x256 default. The static, in-flow #moe-bar-box (MoEProgressView.html, sized in
// MoEProgress.css to exactly VIEW_W_REM x VIEW_H_REM -- a THIRD copy of these two numbers, keep all
// three in lockstep) was meant to make the document measurable and stop the timeout. RE-MEASURED
// LIVE: IT DOES NOT. The box is there, in-flow and correctly sized, and the timeout fires anyway.
// So SURFACE_REASSERT_MS below is not a belt-and-braces guard -- it is the ONLY fix, and the window
// before it is the one surfaceSettled hides the bar through.
//
// The composition's MEASURED bounding box, document origin at (0,0) and 1rem == 1 logical px, is
// 360 x 72 -- .mp-backdrop IS the extremes (left -80rem / top -34rem / 360 wide / 72 tall,
// MoEProgress.css) and every caption, tick and glow sits inside it. So the surface is that box
// plus PAD_REM of slack on all four sides (the text-/box-shadow bleed reaches the box edge
// exactly), and the whole composition is rigidly translated by that much so NOTHING sits at a
// negative coordinate -- an origin overflow is clipped no matter how big the surface is.
//
// THE SIDE CLEARANCE IS 80rem AND IT IS NOT WIDTH-DERIVED: the box is the 200rem track (see
// #moe-bar-root's width note in the CSS) plus BOX_LEFT_REM on each side, so a track resize moves
// BOX_W_REM by exactly the same amount and every per-side margin is preserved. The widest thing
// outside the track is a .side caption, and it is bounded: 6rem gap + a 17rem .mk glyph + its 1rem
// margin + the numerals, whose digits advance 0.4932em == 6.90rem at the .side 14rem font-size
// (MoEBattle.ttf hmtx, comma 3.46rem), i.e. ~55rem for a 4-digit requirement and ~62rem even at 5
// digits. The glows are smaller still (8rem .mp-full, 16rem .mp-pulse, 1rem ring). So the BACKDROP
// is the extreme on both sides with ~18rem to spare -- keep the 80rem, do not trim it to the
// caption.
const BOX_LEFT_REM = -80;                            // .mp-backdrop's left  == leftmost edge
const BOX_TOP_REM = -34;                             // .mp-backdrop's top   == topmost edge
const BOX_W_REM = 360;                               // .mp-backdrop's width
const BOX_H_REM = 72;                                // .mp-backdrop's height
const PAD_REM = 10;
const VIEW_W_REM = BOX_W_REM + 2 * PAD_REM;          // 380
const VIEW_H_REM = BOX_H_REM + 2 * PAD_REM;          // 92
const SHIFT_X_REM = PAD_REM - BOX_LEFT_REM;          // 90
const SHIFT_Y_REM = PAD_REM - BOX_TOP_REM;           // 44 -- MIRRORED (negated) in Python as
                                                     // domain/constants.PROGRESS_ANCHOR_Y_OFFSET

// THE SURFACE RECT IS THE MOUSE HIT RECT -- exactly why WindowFlags.WINDOW_FULLSCREEN was
// rejected for this window (bridge/battle_view.py). A 380rem-wide surface across screen centre
// would be a 380rem input-stealing strip, and this bar is purely decorative and must never take
// input. So collapse the input rect with an EQUAL padding on all four sides: the C++ validator
// names the sides left/top/right/bottom while WG's own JS wrapper passes them in a DIFFERENT
// order plus a magic 5th argument (its setInputPaddingsRem(e) is literally
// setHitAreaPaddingsRem(e, e, e, e, 15)), so the argument ORDER IS NOT CONFIRMED. Equal values
// make the order irrelevant -- do NOT "clean this up" into asymmetric per-side values. Negative
// values are rejected, so a padding can only shrink the rect inward; half the LARGER dimension
// therefore collapses both axes to nothing. HIT_MAGIC mirrors WG's constant; its meaning is
// unknown, so the call is retried without it if the 5-argument form is rejected.
const HIT_PAD_REM = Math.ceil(Math.max(VIEW_W_REM, VIEW_H_REM) / 2);
// Confirmed against WG's own wrapper (gui-part3.pkg,
// battle/battle_notifier/BattleNotifierView/BattleNotifierView.js): the order is
// (top, right, bottom, left, 15). Our four values are equal anyway, so the order is moot.
const HIT_MAGIC = 15;

// --- THE RE-ASSERT: LOAD-BEARING, DO NOT DELETE ---------------------------------------------
// The engine's size-calculation deadline expired ~2.2s after this view loaded (live-measured: our
// resizeViewRem ran at 04.8s, the `Size calculation timeout` + its "Set the default view size"
// action landed at 06.2s and clobbered our push back to the 256x256 default -- the FALLBACK RUNS
// LAST AND WINS, which is why pushing the size earlier can never help).
// THIS WAS ONCE COMMENTED AS "delete once a clean launch proves #moe-bar-box works". THAT PREMISE
// IS DISPROVEN: #moe-bar-box is present, in-flow and exactly VIEW_W_REM x VIEW_H_REM, and the
// timeout STILL fires -- static in-flow content does not satisfy the engine's measurement. This
// re-assert is the ONLY thing that puts the surface right, so it is permanent. 4000ms is
// comfortably past the observed ~2.2s clobber.
// It is now load-bearing TWICE: surfaceSettled (below) flips off the back of it, because the
// re-assert IS the event that makes the surface correct. Between view creation and it, the surface
// is the 256x256 fallback -- which CLIPS the composition (it spans document x 10..370) and, since
// Python's anchor_centred converts extent-fraction to viewport-fraction with a term baked for a
// 92-tall surface (domain/constants.PROGRESS_ANCHOR_Y_OFFSET), places the bar ~142 logical px too
// high. That is exactly the "cropped bar, too high, before the countdown" an Alt peek used to
// reveal. Delete either half and the bug comes back.
const SURFACE_REASSERT_MS = 4000;
// Slack between the re-assert and letting the bar show. The resize round-trips through C++
// (Window._cResized -> onSizeChanged -> bridge/progress_view._place re-reads the movable extent),
// so the surface is only correct -- and the window only re-placed -- a beat AFTER the push. 250ms
// is far more than an engine callback needs and is not user-visible: it lands ~4.25s into a battle,
// inside a window where nothing shows anyway (the damage-driven entry needs the countdown first).
const SURFACE_SETTLE_MS = 250;

// Group an integer with thousands separators: 2910 -> "2,910". Same as the tuner's fmt().
function fmt(n) {
    n = Math.round(Number(n) || 0);
    const sign = n < 0 ? "-" : "";
    return sign + String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Build the root once and cache it. Markup shape is the tuner's stage verbatim: backdrop, the
// track with its four ticks, then the four captions. Each caption is ONE flex row -- icon, value,
// and on capC only the delta, whose PARENS are static text on the wrapper so they never glow
// (see the .mp-d / .mp-d-num split in the CSS). NO word labels anywhere: MoEBattle.ttf is a
// 19-glyph numeric subset (digits % ( ) + - , . / space) and a letter renders BLANK.
function ensureRoot() {
    let root = document.getElementById("moe-bar-root");
    if (root) return root;
    root = document.createElement("div");
    root.id = "moe-bar-root";
    root.innerHTML =
        '<div class="mp-backdrop"></div>' +
        '<div class="mp-track">' +
        '  <div class="mp-fill"></div>' +
        '  <div class="mp-tick mp-end mp-left"></div>' +
        '  <div class="mp-tick mp-pre"></div>' +
        '  <div class="mp-tick mp-proj"></div>' +
        '  <div class="mp-tick mp-end mp-right"></div>' +
        '  <div class="mp-cap side mp-capL"><i class="mp-ico none"></i>' +
        '<span class="mp-v"></span></div>' +
        '  <div class="mp-cap up mp-capP"><i class="mp-ico dmgp"></i>' +
        '<span class="mp-v"></span></div>' +
        '  <div class="mp-cap dn mp-capC"><i class="mp-ico dmgc"></i><span class="mp-v"></span>' +
        '<span class="mp-d">(<span class="mp-d-num"></span>)</span></div>' +
        '  <div class="mp-cap side mp-capR"><i class="mp-ico none"></i>' +
        '<span class="mp-v"></span></div>' +
        '</div>';
    document.body.appendChild(root);
    return root;
}

const root = ensureRoot();
const fill = root.querySelector(".mp-fill");
const tPre = root.querySelector(".mp-pre");
const tProj = root.querySelector(".mp-proj");
const capL = root.querySelector(".mp-capL");
const capP = root.querySelector(".mp-capP");
const capC = root.querySelector(".mp-capC");
const capR = root.querySelector(".mp-capR");
const capD = capC.querySelector(".mp-d");
const capDN = capC.querySelector(".mp-d-num");

function capV(c) { return c.querySelector(".mp-v"); }

// The mark glyph for an axis-end caption: k in 1..3 -> mk<k>; k=4 (3 marks held, no higher mark
// to chase) -> the general MoE glyph; k=0 (nothing held) -> no icon at all (.none is display:none).
function setIco(c, k) {
    c.querySelector(".mp-ico").className =
        "mp-ico" + (k === 0 ? " none" : k === 4 ? " moe" : " mk mk" + k);
}

// --- the pushed state ---------------------------------------------------------------------
// `cur` is the latest push; `last` is the previous one, and comparing the two IS the
// change-detect (there is deliberately no `rev` counter on ProgressVM -- the battle window is a
// private, always-compositing view and has never needed the garage's cold-mount signal).
// `last === null` means "no baseline yet": the FIRST push after mount (and after any re-show) is
// recorded silently so the bar does not appear at battle start.
let cur = { marks: 0, axisLo: 0, axisHi: 0, preAvg: 0, projAvg: 0 };
let last = null;

// Animation state. `swapped` = the bottom numeral currently shows proj_avg (not pre_avg);
// `swapT` is the pending swap timer -- ALWAYS cleared before starting anything, or an aborted
// run's swap fires into the new one. `showing` = the bar is visibly up (running or peek-held).
// `peeking` = Alt is held, so the bar is pinned at the hold plateau with no fade-out.
// `plateauAt` = the wall-clock ms at which the running animation reaches (or reached) that
// plateau -- the ONLY thing the peek needs to know about the animation's progress, since Gameface
// exposes no readable playback position.
// `dmgPlateauAt` = the same instant for the most recent DAMAGE-driven show (0 == none in flight).
// It is a RECORD, NOT A SECOND CLOCK: `plateauAt` stays the only run clock, and this only says
// where the damage hold that a peek interrupted would have been, so peekOff can resume it instead
// of truncating it. Only ever nonzero while `showing` is true -- both places that clear `showing`
// (endRun, reset) clear it too, or a release could resurrect a show that already ended.
// `surfaceSettled` = the surface has been re-asserted (see SURFACE_REASSERT_MS) and is the size we
// asked for, so the composition is neither clipped nor mis-placed. Until then the bar must NOT be
// shown by ANY trigger: the engine's 256x256 fallback crops it and Python places it ~142px too
// high. Nothing legitimately wants to show in that window anyway.
let surfaceSettled = false;
let swapped = true;
let swapT = null;
let peekT = null;
let showing = false;
let peeking = false;
let plateauAt = 0;
let dmgPlateauAt = 0;

// --- run arming (see armRun / endRun) -----------------------------------------------------
// Two interchangeable arming classes, each bound to its OWN identically-tuned @keyframes, so
// consecutive runs never share an animation-name. armIdx starts at 1 -> the first armRun flips to
// 0, i.e. run #1 uses the original .mp-run / mp-life pair.
const RUN_CLASSES = ["mp-run", "mp-run-b"];
const RUN_NAMES = ["mp-life", "mp-life-b"];
let armIdx = 1;
// The live run's id, and the last id already ended. endRun is idempotent on this pair: whichever
// of animationend / the fallback timer arrives first wins and the other becomes a no-op, and a
// timer left over from a superseded run can never end a newer one.
let runId = 0;
let endedId = 0;
let endT = null;
// Margin on the fallback timer so it always LOSES to a working animationend (which fires at
// exactly the run's remaining duration). Not a tuned CSS value -- pure slack.
const END_MARGIN_MS = 250;

function disarm() {
    root.classList.remove(RUN_CLASSES[0]);
    root.classList.remove(RUN_CLASSES[1]);
}

// Start (or restart) mp-life, seeking `seekMs` into it. THE single arming point -- coldShow,
// warmShow and peekOff all funnel through here, so the restart idiom exists in exactly one place.
//
// DEFEATS H3 (the restart being a no-op): rather than trusting remove -> reflow -> re-add to
// restart the SAME animation -- an idiom never proven in Coherent, where mp-life is the client's
// only @keyframes -- every run is armed with a FRESH animation identity (alternating
// .mp-run / .mp-run-b, see the appended keyframes in MoEProgress.css). The engine has nothing to
// coalesce the new run with. The reflow is kept anyway: it costs nothing where it works.
//
// DEFEATS H2 (animationend never firing): arms a fallback timer for this run's own remaining
// duration, which calls the SAME endRun. Without it, a missing animationend wedges `showing`
// true forever, and from then on every Alt press takes peekOn's already-showing branch and every
// data change takes warmShow() -- the bar shows once and never again (the reported symptom).
function armRun(seekMs) {
    armIdx = 1 - armIdx;
    runId += 1;
    const id = runId;
    disarm();
    root.style.animationPlayState = "";
    root.style.animationDelay = seekMs ? "-" + seekMs + "ms" : "0ms";
    void root.offsetWidth;
    root.classList.add(RUN_CLASSES[armIdx]);
    clearTimeout(endT);
    endT = setTimeout(function () { endRun(id); }, TOTAL_MS - seekMs + END_MARGIN_MS);
    // THE run clock, maintained in ONE place so every arming path agrees: the seek makes the run
    // start `seekMs` in, so it reaches the plateau FADE_IN_MS - seekMs from now (in the past for a
    // seek past it). Gameface exposes no readable playback position, so this is how the peek knows
    // where the run is -- see peekOn. Only meaningful while the run is NOT paused (wall-clock keeps
    // running, the animation does not).
    plateauAt = Date.now() + FADE_IN_MS - seekMs;
}

function axisPct(v) {
    const w = cur.axisHi - cur.axisLo;
    if (w <= 0) return 0;
    return Math.max(0, Math.min(1, (v - cur.axisLo) / w)) * 100;
}

// Position the fill, the moving tick and its caption. anim=false SNAPS (transition:none) -- used
// to rewind to the resting value before a cold show. The 600ms transition DELAY lives in the CSS
// (.mp-fill, .mp-proj, .mp-capC), so JS sets the target once and lets CSS time it.
function setPos(v, anim) {
    const p = axisPct(v).toFixed(3) + "%";
    const t = anim ? "" : "none";
    fill.style.transition = t;
    tProj.style.transition = t;
    capC.style.transition = t;
    fill.style.width = p;
    tProj.style.left = p;
    capC.style.left = p;
}

// The bottom-centre numeral shows pre_avg while the bar fades + slides IN, then swaps to proj_avg
// at VALUE_SWAP_MS -- the same instant the fill/tick begin moving -- so the number never claims a
// gain the bar has not shown yet. The delta arrives WITH that swap.
//
// THE SIGN COLOUR DURING THE ENTRY IS THE *PREVIOUS COMMITTED* ONE -- AN EXPLICIT MAINTAINER
// DECISION, NOT DRIFT, verbatim: "Before the sign class lands, applied color must resemble previous
// state. E.g., when the bar was red and dealt damage moves it into green, it must appear red and
// then turn green after recalculation lands. If it was and will remain red, it must always show
// red." So the sw==false path (the cold damage entry) writes the numeral back to pre_avg and hides
// the delta but DELIBERATELY DOES NOT TOUCH .mp-up/.mp-down: whatever the last showVal(true)
// committed stays applied for the whole 600ms entry, and a NEW sign is only claimed once it lands at
// the swap. The was-red-stays-red case therefore shows NO colour change whatever -- which is the
// whole point; an earlier build stripped both classes here and flashed the neutral fill on every
// single cold entry. Holding a class across coldShow's suppress -> reflow -> armRun sequence
// interpolates nothing: .mp-fill transitions width only, .mp-proj / .mp-capC left only, and no
// .mp-up/.mp-down rule declares a transition at all (see the CSS).
//
// sw==true is the ONLY path that ever REMOVES a class, and it has to stay that way -- it is what
// clears the sign when a transition lands on a rounded-zero delta. So the neutral colour is
// reserved for exactly two states: nothing committed yet (the first show of a battle) and a
// rounded-zero delta. Only this bottom caption (plus the fill and the tick it rides) ever takes
// .mp-up/.mp-down; the two requirement captions and the top-centre pre_avg caption stay plain
// white (see the CSS's "WHO GLOWS" note).
function showVal(sw) {
    const d = cur.projAvg - cur.preAvg;
    capV(capC).textContent = fmt(sw ? cur.projAvg : cur.preAvg);
    capD.style.opacity = sw ? "1" : "0";
    capDN.textContent = (d > 0 ? "+" : d < 0 ? "-" : "") + fmt(Math.abs(d));
    if (!sw) return;         // the entry window keeps the PREVIOUS committed sign -- see above
    // THE CLASSES KEY OFF THE ROUNDED VALUE, PRECISELY SO GLYPH AND GLOW CAN NEVER DISAGREE. `d`
    // is a raw float but the text above is rounded by fmt(), so an unrounded test glowed GREEN on
    // a displayed "(+0)" (any 0 < d < 0.5 -- routine at EWMA_K, and the "(-0)"-shows-red twin
    // equally so). The CSS says the intent outright: "a sub-precision change never reads as a
    // win". Tested on the MAGNITUDE, exactly as fmt() rounds it (half away from zero) -- NOT
    // Math.round(d), which is -0 for d == -0.5 while the text already reads "(-1)".
    const glows = Math.round(Math.abs(d)) !== 0;
    [capV(capC), capDN, fill, tProj].forEach(function (e) {
        e.classList.toggle("mp-up", glows && d > 0);
        e.classList.toggle("mp-down", glows && d < 0);
    });
}

// Everything that does NOT animate: the axis-end captions + their mark glyphs, the static pre_avg
// tick and caption, and the met-requirement gold. Safe to re-run on every push.
function paintStatic() {
    capV(capL).textContent = fmt(cur.axisLo);
    capV(capR).textContent = fmt(cur.axisHi);
    setIco(capL, cur.marks);                            // 0 marks -> no icon at all
    setIco(capR, cur.marks >= 3 ? 4 : cur.marks + 1);   // 3 marks -> the general MoE glyph
    capV(capP).textContent = fmt(cur.preAvg);
    const pre = axisPct(cur.preAvg).toFixed(3) + "%";
    tPre.style.left = pre;
    capP.style.left = pre;
    root.classList.toggle("mp-full", cur.projAvg >= cur.axisHi);
}

// Schedule the numeral/delta/sign commit for VALUE_SWAP_MS from now -- the same delay the
// fill/tick transitions carry, so number and bar commit together.
function scheduleSwap() {
    clearTimeout(swapT);
    swapT = setTimeout(function () { swapped = true; showVal(true); }, VALUE_SWAP_MS);
}

// COLD SHOW: the bar is not up -> play the whole mp-life transient.
// The REWIND idiom (transition:none -> write the resting value -> force a reflow -> hand the
// transition back) is what lets a run start from pre_avg even if a previous run was aborted
// part-way; the same treatment cancels a half-finished delta fade. Clearing the pending swap
// FIRST is not optional. Ported from the tuner's replay() (gen_bar_tuner.ps1:921-930).
//
// `atCurrent` (falsy by default -- the DAMAGE-EVENT entry, unchanged) picks which VALUES the run
// opens with; the MOTION is identical either way (armRun(SEEK_NONE), the tuned 600ms fade + 20rem
// slide). Falsy = the rewind above: open on pre_avg with the delta hidden, then climb to proj_avg
// on the 600ms-delayed transitions and swap the numeral at VALUE_SWAP_MS. That pre->current climb
// IS the widget when a damage event pulls the bar up, so it must stay.
// TRUE (only peekOn's Alt entry): open ALREADY committed -- fill/tick/caption snapped to proj_avg,
// numeral + delta + sign already showing -- because Alt is a "show me the state now" request and
// the 0-600ms pre-battle frames read as stale info. No scheduleSwap: there is nothing left to
// commit. The transitions still have to be suppressed and flushed (void root.offsetWidth) BEFORE
// armRun re-adds the run class, or the 600ms-delayed width/left transitions animate anyway and the
// stale flip comes back through the back door; likewise capD's transition is off while opacity
// goes to 1, or the delta fades in over 600ms instead of being simply present.
function coldShow(atCurrent) {
    clearTimeout(swapT);
    clearTimeout(peekT);
    capD.style.transition = "none";
    swapped = !!atCurrent;
    showVal(swapped);
    disarm();
    void root.offsetWidth;
    setPos(swapped ? cur.projAvg : cur.preAvg, false);
    void root.offsetWidth;
    capD.style.transition = "";
    armRun(SEEK_NONE);                       // a cold show plays the entry in full (plateauAt too)
    // Only a DAMAGE entry owns a hold a peek may interrupt; peekOn's atCurrent entry IS the peek.
    if (!atCurrent) dmgPlateauAt = plateauAt;
    showing = true;
    if (swapped) return;
    // rAF so the class change and the target land in DIFFERENT frames (the tuner does the same).
    requestAnimationFrame(function () { setPos(cur.projAvg, true); });
    scheduleSwap();
}

// WARM RE-TRIGGER (the debounce): a change arrived while the bar is ALREADY up. Do NOT replay the
// appearance -- re-measure the DISAPPEARANCE from this event instead. mp-life bakes fade-in, hold
// and fade-out into ONE both-filled 6200ms keyframe, so its hold cannot be extended in place;
// instead restart the animation but SEEK PAST the entry with a negative delay (SEEK_PLATEAU, the
// 9.68% stop, where both the opacity fade and the 20rem slide have completed). The bar stays
// visibly put and gets a fresh hold + fade-out.
// NOTE the one place the phase-1 plan does NOT apply: we deliberately do NOT rewind the fill/tick
// to their resting values here. They stay where they are so the bar animates from its CURRENT
// position to the new target -- the rewind idiom is for cold shows only. For the same reason the
// bottom numeral is left showing the PREVIOUS proj_avg until the scheduled swap, so number and
// bar still commit together.
function warmShow() {
    if (!peeking) {
        armRun(SEEK_PLATEAU);            // the seek lands us AT the plateau (armRun sets plateauAt)
    }
    // THIS event's hold, remembered so an Alt release resumes it instead of discarding it (peekOff).
    // The peeking branch is the whole reason this is not just read off `plateauAt`: while Alt is held
    // we deliberately do NOT armRun (the pause must survive), so a damage event landing mid-peek
    // would otherwise get no hold at all and be wiped 600ms after the release. Record the plateau
    // the run WOULD have had -- SEEK_PLATEAU cancels FADE_IN_MS, so armRun's clock makes that
    // exactly now, which is also why the non-peek branch can read the freshly-set plateauAt.
    dmgPlateauAt = peeking ? Date.now() : plateauAt;
    setPos(cur.projAvg, true);
    scheduleSwap();
}

// ALT PEEK (an ADDITIVE second show-trigger, not a gate -- the transient still fires on its own
// when Alt is untouched). While Alt is held the bar must be pulled up and HELD with no fade-out.
// Mechanism: play (or keep) mp-life and PAUSE it at the hold plateau, so the entry is the real
// fade+slide and the hold simply never ends. No new CSS rule -- the stylesheet's `.mp-hold` was a
// tuner-stage-only class and the emitted file has no rule for it.
function peekOn() {
    clearTimeout(peekT);
    if (!showing) {
        // atCurrent: the Alt entry opens on the CURRENT values, never the pre-battle rewind.
        // Python pushes a fresh compute in the same transaction as setAltHeld
        // (battle_bridge._set_alt_held), so the VM is already current -- the outdated first frames
        // were purely this rewind. Same entry animation, different starting values.
        coldShow(true);             // full entry, then pause below once it lands
    } else if (!peeking && Date.now() >= plateauAt + HOLD_MS) {
        // ALT PRESSED DURING THE FADE-OUT -- the bar froze mid-transition at partial opacity
        // instead of coming back. `showing` stays true all the way through the fade-out (only
        // endRun clears it), so the pause branch below used to pause the animation part-way
        // through the fade and pin it there. plateauAt + HOLD_MS is the 90.32% stop (== elapsed
        // SEEK_FADE_OUT, see armRun's run clock), so at/past it the run is already fading out and
        // must be RE-ARMED, not paused in place.
        // SEEK_PLATEAU, not a cold entry: mp-life's 0% stop is opacity 0, so replaying the entry
        // from a partially-visible bar would visibly DIP it to nothing and fade up again (reads as
        // a flicker). Seeking to the plateau snaps it back to full opacity -- "caught it".
        // armRun re-establishes the run identity, the runId guard and the endT fallback, so the
        // superseded run's animationend/timer cannot end this one; the pause below then clears
        // endT for the held plateau exactly as it does for a cold show.
        armRun(SEEK_PLATEAU);
    }
    peeking = true;
    // Pause once the entry has completed -- pausing mid-fade-in would freeze the bar at partial
    // opacity. If the bar was already PAST the entry (mid-hold, or a warm re-trigger that seeked
    // straight to the plateau) the wait is 0 and it pauses on this tick.
    peekT = setTimeout(function () {
        root.style.animationPlayState = "paused";
        // A paused hold NEVER ends, so the H2 fallback timer must not end it either. peekOff
        // re-arms a fresh run (and a fresh timer) for the fade-out -- and it does so whether or not
        // this pause ever landed, so a release that beats it is still hold-to-show.
        clearTimeout(endT);
    }, Math.max(0, plateauAt - Date.now()));
}

// Alt released -> fade out NOW rather than serving the rest of the hold: unpause and seek
// straight to the 90.32% stop, so only the 600ms fade-out plays. THE PEEK IS STRICTLY
// HOLD-TO-SHOW, so this must be true for EVERY release, including one that beats the pause.
// It used to bail on `animationPlayState !== "paused"` -- the proxy for "the entry never
// finished, so seeking to the fade-out stop would flash the bar to full opacity first" -- but
// bailing re-arms nothing, so a sub-FADE_IN_MS tap served the whole 6200ms transient and read as
// a toggle-on with a 5s auto-hide. Instead MIRROR the release into the fade-out: `inLeft` is how
// much of the entry was still owed, and starting that far BEFORE the 90.32% stop lands the run at
// the same opacity it was already at. A peek that did pause is past the plateau, so inLeft == 0
// and the seek is exactly the old SEEK_FADE_OUT -- behaviour for any hold >= FADE_IN_MS is
// unchanged. armRun unpauses, flips the run identity and re-arms endT for the shorter remainder,
// so the paused/unpaused branch is gone entirely.
// COSMETIC, DELIBERATELY NOT FIXED: the mirror is linear while both fade halves are ease-in
// (MoEProgress.css), so a release mid-fade-in can step opacity by up to ~0.2. Only reachable on a
// sub-600ms tap, where the bar is barely visible at all -- not a bug, not worth a keyframe.
//
// EXCEPT when the peek interrupted a DAMAGE-driven show that still has hold left: players hold Alt
// near-constantly (extended markers), so fading out there would truncate an event's 5s to whatever
// was left of the peek. RESUME that hold instead, at its true elapsed position: seeking
// (now - dmgPlateauAt) PAST the plateau makes armRun's clock re-derive plateauAt == dmgPlateauAt
// (plateauAt = now + FADE_IN_MS - seek), so the resumed run's fade-out starts at exactly the instant
// the original hold would have -- not later -- and armRun's endT covers only the shorter remainder.
// The pause is simply not credited back: the hold is wall-clock, as it was before any Alt.
function peekOff() {
    clearTimeout(peekT);
    if (!peeking) return;
    peeking = false;
    if (dmgPlateauAt + HOLD_MS > Date.now()) {
        armRun(SEEK_PLATEAU + (Date.now() - dmgPlateauAt));
        return;
    }
    const inLeft = Math.min(FADE_IN_MS, Math.max(0, plateauAt - Date.now()));
    armRun(SEEK_FADE_OUT + inLeft);
}

// FORCE-SETTLE, and the ONE place the "run is over" state is cleared. mp-life is both-filled so
// the root rests at its 100% stop (opacity 0) with no help from JS -- but a swap timer longer than
// the transient would otherwise leave the resting bar showing pre_avg forever, and a cancelled
// delta fade could strand part-way. showVal(true) sets both outright. Ported from
// gen_bar_tuner.ps1:931-940.
// `id` is the run being ended: an id that is not the live run (a timer from a superseded run) or
// one already ended (the loser of the animationend/timer race) is ignored.
function endRun(id) {
    if (id !== runId || id === endedId) return;
    endedId = id;
    clearTimeout(endT);
    clearTimeout(peekT);
    clearTimeout(swapT);
    disarm();
    showing = false;
    peeking = false;
    dmgPlateauAt = 0;                // the hold is over -- a later release must never resume it
    root.style.animationPlayState = "";
    setPos(cur.projAvg, false);
    swapped = true;
    showVal(true);
}

// Only the CURRENTLY armed animation's end counts. Because armRun alternates the identity, the
// cancel/end noise of the run it just superseded reports the OTHER name and is dropped here for
// free -- which is why the H3 fix does not need a separate guard against a cancel arriving as an
// animationend.
root.addEventListener("animationend", function (e) {
    if (e.animationName !== RUN_NAMES[armIdx]) return;
    endRun(runId);
});

// Reset to the resting/hidden state, so a later re-show starts COLD and the next push after it
// becomes a fresh silent baseline (a scoreboard opening and closing must not replay the bar).
function reset() {
    clearTimeout(swapT);
    clearTimeout(peekT);
    clearTimeout(endT);
    endedId = runId;                 // no live run left for a late animationend to end
    disarm();
    root.style.animationPlayState = "";
    root.style.animationDelay = "0ms";
    showing = false;
    peeking = false;
    dmgPlateauAt = 0;                // ditto endRun: no hold survives a hide / a new battle
    swapped = true;
    last = null;
}

function render(model) {
    // Truthy guards, not `=== false`: a root VM whose flags are still undefined before Python's
    // first push must stay hidden, not paint a zero-width bar over the HUD. hasData false means
    // the per-tank threshold table gave no usable mark axis -- there is nothing to plot.
    if (!model || !model.visible || !model.hasData) {
        root.style.display = "none";
        reset();
        return;
    }
    root.style.display = "";

    cur = {
        marks: Number(model.marks) || 0,
        axisLo: Number(model.axisLo) || 0,
        axisHi: Number(model.axisHi) || 0,
        preAvg: Number(model.preAvg) || 0,
        projAvg: Number(model.projAvg) || 0,
    };
    paintStatic();

    // CHANGE-DETECT, JS-side: replay only when a pushed value actually MOVED. Python re-pushes on
    // every efficiency tick with no dirty check, so without this the bar would replay constantly.
    const changed = last !== null && (
        cur.projAvg !== last.projAvg || cur.preAvg !== last.preAvg ||
        cur.axisLo !== last.axisLo || cur.axisHi !== last.axisHi ||
        cur.marks !== last.marks);
    const first = last === null;
    last = cur;

    // THE TWO SHOW TRIGGERS ARE GATED ON surfaceSettled; THE SILENT BASELINE BELOW IS NOT. Before
    // the re-assert the surface is the engine's 256x256 fallback: the bar would come up cropped and
    // ~142px too high (see SURFACE_REASSERT_MS). The baseline shows nothing, so it costs nothing to
    // let it run -- and it MUST run, or `last` never gets recorded and the first real change plays
    // a bogus pre->proj climb.
    if (first) {
        // Silent baseline: settle the bar at its resting values without showing anything.
        setPos(cur.projAvg, false);
        swapped = true;
        showVal(true);
    } else if (changed && surfaceSettled) {
        if (showing) warmShow();
        else coldShow();
    }

    // Alt is handled AFTER the value change so a push that carries both (Python re-pushes on every
    // Alt transition) gets the new target AND the peek hold. An Alt held BEFORE the surface settled
    // is not lost: the settle re-renders the current model, which arrives here with altHeld still
    // true and peeks then.
    if (model.altHeld) {
        if (!peeking && surfaceSettled) peekOn();
    } else {
        peekOff();
    }
}

// Run ONCE on mount, before the first render. Two independent halves:
//
//  (1) THE RIGID TRANSLATION (unconditional -- an origin overflow is clipped at ANY surface
//      size, so this must happen even without viewEnv). #moe-bar-root is
//      position:absolute;left:0;top:0 in the CSS, and moving its origin carries the in-flow
//      .mp-track AND the abspos .mp-backdrop with it -- relative geometry stays bit-for-bit
//      identical and NO tuned value is touched. It has to be left/top and NOT a transform:
//      mp-life animates the root's OWN transform and would clobber one. Python cancels the shift
//      (PROGRESS_ANCHOR_Y_OFFSET) so the bar does not move on screen.
//  (2) THE SURFACE + INPUT RECT (feature-detected, fail-soft, like every engine read in this
//      codebase). OpenWG's own libs/common.js touches the `viewEnv` global directly and offers no
//      resize wrapper, so this does too. WG views resize repeatedly; we push twice (see
//      SURFACE_REASSERT_MS).
function mountSurface() {
    root.style.left = SHIFT_X_REM + "rem";
    root.style.top = SHIFT_Y_REM + "rem";
    pushSurfaceSize();
    // Re-assert once after the engine's default-size fallback deadline, so a clobber cannot be the
    // last word -- and only THEN let the bar be shown at all. The flip is NESTED in this callback
    // on purpose: it is the re-assert that makes the surface correct, so the dependency is
    // structural rather than a second timer that could outlive it (see SURFACE_REASSERT_MS).
    setTimeout(function () {
        pushSurfaceSize();
        setTimeout(function () {
            surfaceSettled = true;
            // Re-render the model we already hold so a STILL-HELD Alt takes effect immediately:
            // during PREBATTLE there may be no efficiency tick to re-push it
            // (bridge/battle_bridge._on_efficiency_updated), and the player is mid-peek.
            render(observer.model);
        }, SURFACE_SETTLE_MS);
    }, SURFACE_REASSERT_MS);
}

// Push the surface size and collapse the input rect. Idempotent -- called at mount and once more
// after SURFACE_REASSERT_MS.
function pushSurfaceSize() {
    if (typeof viewEnv === "undefined" || !viewEnv) return;
    try {
        // WG's own views freeze the texture across a resize (flicker, not sizing) -- e.g.
        // BattleNotifierView.js. Optional, so feature-detected like the rest.
        if (viewEnv.freezeTextureBeforeResize) viewEnv.freezeTextureBeforeResize();
    } catch (e) { /* fail-soft */ }
    try {
        if (viewEnv.resizeViewRem) viewEnv.resizeViewRem(VIEW_W_REM, VIEW_H_REM);
    } catch (e) { /* fail-soft: a clipped bar beats a dead one */ }
    if (!viewEnv.setHitAreaPaddingsRem) return;
    try {
        viewEnv.setHitAreaPaddingsRem(HIT_PAD_REM, HIT_PAD_REM, HIT_PAD_REM, HIT_PAD_REM,
                                      HIT_MAGIC);
    } catch (e) {
        // The 5th argument's meaning is unknown -- if the binding rejects the 5-arg form, the
        // 4-arg one still collapses the rect.
        try {
            viewEnv.setHitAreaPaddingsRem(HIT_PAD_REM, HIT_PAD_REM, HIT_PAD_REM, HIT_PAD_REM);
        } catch (e2) { /* fail-soft */ }
    }
}

engine.whenReady.then(() => {
    mountSurface();
    observer.onUpdate(render);
    observer.subscribe();
    render(observer.model);
});
