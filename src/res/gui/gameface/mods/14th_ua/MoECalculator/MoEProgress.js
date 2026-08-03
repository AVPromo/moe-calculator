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
// The transient machinery -- arming, the negative-delay debounce, the Alt peek's pause/seek, the end
// race and the surface re-assert -- is SHARED with MoEEfficiency.js. Every behaviour in there cost a
// client relaunch to find; read its header before changing anything that touches timing. Separate
// documents, so this module is instantiated twice with no cross-talk.
import { createTransient, fmt, FADE_IN_MS } from "./MoEBarTransient.js";

// No feature name -> observe this view's OWN root model (window.model == ProgressVM).
const observer = ModelObserver();

// This bar's ONE timing of its own: when the bottom numeral commits to proj_avg. It tracks
// tickDelayMs by construction, which is the shared FADE_IN_MS.
const VALUE_SWAP_MS = FADE_IN_MS;

// --- the surface, and the rigid shift into it ----------------------------------------------
// A Gameface view PUSHES its own size to C++ through the `viewEnv` global
// (viewEnv.resizeViewRem(w, h), rem == logical px); a view that never calls it gets the engine's
// "default view size" fallback after a `Size calculation timeout` -- a flat 256x256 logical px,
// which is what clipped this bar. WG precedent for the same window shape: DogTagMarkerView.js
// calls resize(500, 300, "rem") once on mount, and ~85 WG views do the same. There is NO
// Python-side and NO res_map lever for this (see bridge/bar_window.py).
//
// BUT THE ENGINE ALSO TRIES TO MEASURE THE DOCUMENT, AND ITS FALLBACK RUNS LAST AND WINS. Pushing
// the size is not sufficient on its own: our resize landed at 04.8s, the size-calculation deadline
// expired at 06.2s and its action ("Set the default view size") overwrote our pushed size with the
// 256x256 default. The static, in-flow #moe-bar-box (MoEProgressView.html, sized in
// MoEProgress.css to exactly the derived surface -- keep it in lockstep with the BOX_*/PAD_REM
// below) was meant to make the document measurable and stop the timeout. RE-MEASURED LIVE: IT DOES
// NOT. The box is there, in-flow and correctly sized, and the timeout fires anyway. So the shared
// module's SURFACE_REASSERT_MS is not a belt-and-braces guard -- it is the ONLY fix, and the window
// before it is the one T.settled() hides the bar through.
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
// BOX_W_REM by exactly the same amount and every per-side margin is preserved.
// WHICH CAPTION IS THE EXTREME HAS NOW MOVED THREE TIMES, so all three extremes are RE-DERIVED here
// from the shipped CSS and MoEBattle.ttf's own advances (digit 0.4932em, comma 0.2471, paren 0.3008,
// plus 0.4932; 1rem == 1 logical px; every figure re-checked against the ttf's hmtx). The two moves
// in THIS revision: the .mp-capL axis-floor caption is GONE outright, and the REMAINING-BATTLES
// COUNT moved OFF the delta and ONTO .mp-capR with a glyph of its own.
//   RIGHT -- .mp-capR, and it is now the extreme by a wide margin. ONE flex row, FOUR items --
//   plus a FIFTH term now, the ETA GAP (.mp-ico.battles's own margin-left, DOM order after the
//   requirement numeral and before the battles glyph -- it widens the row, not a box of its own):
//     3.00 (.mp-cap.side.mp-capR's margin-left off the track end)
//     + 17.00 (.mp-ico.mk / .mp-ico.moe) + 1.00 (.mp-cap .mp-ico's shared gap)
//     + 31.08 ("3,050", a 4-digit requirement, at the .side 14rem: 4*6.9048 + 3.4594)
//     + 4.00 (.mp-ico.battles's margin-left -- the ETA GAP, added to breathe the requirement
//       numeral apart from the remaining-battles count that follows it)
//     + 13.00 (.mp-ico.battles -- it takes .mp-ico's BASE box, the only glyph in the file that does)
//     + 1.00 (that same shared gap) + 13.81 ("99", the PROGRESS_ETA_CAP ceiling, 2*6.9048 at 14rem)
//     == 83.89rem of BOXES, + 1.00 for the numerals' dark-drop text-shadow radius == 84.89rem.
//     SO IT OVERHANGS THE 80rem BACKDROP CLEARANCE BY 4.89rem (UP FROM 0.89rem BEFORE THE GAP) --
//     and unlike before, that overhang is NO LONGER pure shadow halo. The final "99" numeral's own
//     box now spans 70.08 -> 83.89rem, i.e. 3.89rem of ITS BOX (not just its shadow) sits PAST the
//     80rem backdrop edge, on bare HUD. At the .side 14rem size one digit is 6.9048rem wide, so
//     3.89rem is a bit over half a digit -- WORST CASE IS ROUGHLY THE OUTER HALF OF THE LAST DIGIT
//     LOSING ITS DARK BACKING, and it only reaches that worst case when a 4-digit requirement
//     ("3,050"-shaped) and a 2-digit ETA ("99") land together. THIS IS A KNOWN, ACCEPTED TRADEOFF
//     OF THE 4rem GAP, not a bug to chase: do NOT fix it by moving the backdrop, changing
//     PROGRESS_ANCHOR_X_OFFSET, shrinking this gap, or re-deriving it away -- that is the
//     maintainer's call, not this file's.
//     DISTINGUISH OVERHANG FROM CLIPPING before reaching for the geometry -- the surface is a
//     further PAD_REM out at 90rem, so CLIPPING STARTS AT 90 and there is still 5.11rem of
//     clearance before that (90 - 84.89): nothing here is clipped, only unbacked.
//     REBALANCING THE BACKDROP IS NOT FREE AND WAS DELIBERATELY NOT DONE. Taking clearance off the
//     now-empty left side (80/80 -> e.g. 52/108, keeping BOX_W_REM and so the surface AND the mouse
//     hit rect) breaks the symmetry that lets positioning.anchor_centred's `max_x // 2` centre the
//     bar with NO X term in Python: constants.PROGRESS_ANCHOR_X_OFFSET is 0, and
//     tests/test_progress_surface_mirror.py::test_the_large_backdrop_stays_symmetric_about_the_track
//     pins exactly that. Any asymmetry slides the bar half the error sideways at every resolution
//     until that constant -- plus a Large twin for it, since it is logical px and the block's
//     x-lengths carry SIZE_XF -- follows. That is a positioning change, not a CSS one.
//   CENTRE (.mp-capC) RIGHT -- back down, now that the "/NN" suffix is off the delta:
//     17.76 (half of "3,050" at the .dn 16rem == 35.52) + 4.20 (.mp-d's 0.35em gap of its OWN 12rem
//     font) + 30.89 ("(+297)" at 12rem) + 6.00 (.mp-d-num's sign-glow text-shadow radius)
//     == 58.85rem, i.e. 21.15rem SPARE. That reproduces the pre-count figure exactly, as it must.
//     A 4-digit delta ("(+2,970)" == 39.78) still only reaches 67.74rem, and needs cd ~ 150,000.
//   LEFT -- .mp-capC at 0% is the ONLY candidate left, and its ICON path beats its numeral's glow:
//     17.76 (the same half-numeral) + 17.00 (.mp-capC .mp-ico's negative-margin overhang)
//     + 0.48 (that icon's ::before glow, 3% of its 16rem box) == 35.24rem, against the numeral's
//     own 17.76 + 6.00 == 23.76. So 35.24rem and 44.76rem SPARE: ~45rem of dead space out there.
//     (An earlier revision of this note SUMMED those two paths into 41.24rem. They are
//     ALTERNATIVES, not terms -- the 6rem is the numeral's own text-shadow and stops at -23.76.)
//   The .mp-full case is UNCHANGED and now provably so: battles_to_axis_hi returns 0 exactly when
//   proj_avg >= axis_hi, which is the same test .mp-full toggles on, so the count is suppressed on
//   every gold frame and needs no `#moe-bar-root.mp-full .mp-eta` rule of its own.
//   Large is NOT size-mode-agnostic (it needs its own sum, the x-length terms scale by SIZE_XF while
//   the boxes/numerals scale via the root font alone) but is still strictly slacker: the clearance
//   grows 80 -> 106.667rem, and the ETA GAP's own Large twin (.mp-ico.battles's margin-left, an
//   x-length like the shared gaps: 4 * 4/3 == 5.333) is the only new term --
//   capR' == 4 + 17 + 1.333 + 31.08 + 5.333 + 13 + 1.333 + 13.81 + 1 == 87.89rem, 18.78rem spare
//   (down from 24.1rem before the gap, since the gap only widens the reach and the backdrop grows
//   for a different reason). Still comfortably unclipped, so the Default size keeps binding on
//   every side.
// Keep the 80rem, and re-derive ALL THREE extremes again before ever moving it -- "which one is the
// extreme" has now moved three times, and each move invalidated the previous revision's spare.
// These five ARE this bar's surface contract and stay HERE, per bar. MoEBarTransient derives the
// rest from them (its box*/pad arguments), exactly as this file used to:
//   VIEW_W_REM = BOX_W_REM + 2 * PAD_REM == 380     SHIFT_X_REM = PAD_REM - BOX_LEFT_REM == 90
//   VIEW_H_REM = BOX_H_REM + 2 * PAD_REM == 92      SHIFT_Y_REM = PAD_REM - BOX_TOP_REM  == 44
// SHIFT_Y_REM is MIRRORED (negated, plus the fraction-unit term) in Python as
// domain/constants.PROGRESS_ANCHOR_Y_OFFSET, so changing BOX_TOP_REM or PAD_REM moves the bar on
// screen until that constant follows -- and #moe-bar-box in MoEProgress.css is sized to the derived
// surface, a THIRD copy: keep all three in lockstep. The hit padding and the re-assert timing live
// in the shared module (its HIT_MAGIC / SURFACE_REASSERT_MS -- both LOAD-BEARING, read its header).
const BOX_LEFT_REM = -80;                            // .mp-backdrop's left  == leftmost edge
const BOX_TOP_REM = -34;                             // .mp-backdrop's top   == topmost edge
const BOX_W_REM = 360;                               // .mp-backdrop's width
const BOX_H_REM = 72;                                // .mp-backdrop's height
const PAD_REM = 10;

// Build the root once and cache it. Markup shape is the tuner's stage: backdrop, the track with its
// four ticks, then THREE captions -- the tuner's fourth, .mp-capL, carried the axis FLOOR numeral
// and is gone (axisLo is the battle's starting projection, not a requirement, and the label said
// nothing the moving caption does not). Each caption is ONE flex row -- icon, value, and on capC the
// delta, whose PARENS are static text on the wrapper so they never glow (see the .mp-d / .mp-d-num
// split in the CSS). NO word labels anywhere: MoEBattle.ttf is a 19-glyph numeric subset
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
        '  <div class="mp-tick mp-end mp-left"></div>' +
        '  <div class="mp-tick mp-pre"></div>' +
        '  <div class="mp-tick mp-proj"></div>' +
        '  <div class="mp-tick mp-end mp-right"></div>' +
        '  <div class="mp-cap up mp-capP"><i class="mp-ico dmgp"></i>' +
        '<span class="mp-v"></span></div>' +
        '  <div class="mp-cap dn mp-capC"><i class="mp-ico dmgc"></i><span class="mp-v"></span>' +
        '<span class="mp-d">(<span class="mp-d-num"></span>)</span></div>' +
        // THE MARK PAIR MUST COME FIRST IN THIS ROW, and two helpers silently depend on it: setIco()
        // and capV() both do a querySelector for the FIRST .mp-ico / .mp-v, so reordering these four
        // nodes repoints the mark-glyph writer at the battles glyph and the requirement writer at the
        // count -- with no error and no test in this file to catch it. The requirement's glyph is the
        // only one setIco ever rewrites; the battles glyph's class is STATIC (paintStatic only
        // toggles `none` on it), which is why it can safely share the .mp-ico family here.
        '  <div class="mp-cap side mp-capR"><i class="mp-ico none"></i>' +
        '<span class="mp-v"></span><i class="mp-ico battles"></i>' +
        '<span class="mp-eta"></span></div>' +
        '</div>';
    document.body.appendChild(root);
    return root;
}

const root = ensureRoot();
const fill = root.querySelector(".mp-fill");
const tPre = root.querySelector(".mp-pre");
const tProj = root.querySelector(".mp-proj");
const capP = root.querySelector(".mp-capP");
const capC = root.querySelector(".mp-capC");
const capR = root.querySelector(".mp-capR");
const capD = capC.querySelector(".mp-d");
const capDN = capC.querySelector(".mp-d-num");
// The remaining-battles pair on capR. Its own classes, NOT a second .mp-v / an .mp-ico index: see the
// mark-pair-comes-first note on the template above.
const capEtaIco = capR.querySelector(".mp-ico.battles");
const capEta = capR.querySelector(".mp-eta");

function capV(c) { return c.querySelector(".mp-v"); }

// The mark glyph for the NEXT-MARK caption: k in 1..3 -> mk<k>; k=4 (3 marks held, no higher mark
// to chase) -> the general MoE glyph; k=0 -> no icon at all (.none is display:none).
// FIRST .mp-ico ONLY, and .mp-capR now holds two: the mark pair is first in the template precisely so
// this keeps addressing it (see the note there). The k=0 arm is unreached from paintStatic today --
// its only caller passes marks+1 or 4 -- but it stays, because without it a stray 0 would write the
// nonexistent class "mk mk0" and blank the glyph silently instead of hiding it.
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
let cur = { marks: 0, axisLo: 0, axisHi: 0, preAvg: 0, projAvg: 0, eta: -1 };
let last = null;

// This bar's OWN animation state, all of it about VALUES rather than the run: `swapped` = the bottom
// numeral currently shows proj_avg (not pre_avg); `swapT` is the pending swap timer -- ALWAYS
// cleared before starting anything, or an aborted run's swap fires into the new one. The run state
// itself (showing / peeking / the plateau clock / the surface settle) lives in the shared transient.
let swapped = true;
let swapT = null;

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
    // SIGN + MAGNITUDE ONLY. The remaining-battles count used to be appended here as "/NN"; it now
    // lives on .mp-capR beside the requirement it is a countdown to, with a glyph of its own (see
    // paintStatic). Do not re-append it: it was the single term that pushed capC's reach to 74rem.
    capDN.textContent = (d > 0 ? "+" : d < 0 ? "-" : "") + fmt(Math.abs(d));
    if (!sw) return;         // the entry window keeps the PREVIOUS committed sign -- see above
    // THE CLASSES KEY OFF THE ROUNDED VALUE, PRECISELY SO GLYPH AND GLOW CAN NEVER DISAGREE. `d`
    // is a raw float but the text above is rounded by fmt(), so an unrounded test glowed GREEN on
    // a displayed "(+0)" (any 0 < d < 0.5 -- routine at EWMA_K, and the "(-0)"-shows-red twin
    // equally so). The CSS says the intent outright: "a sub-precision change never reads as a
    // win". Tested on the MAGNITUDE, exactly as fmt() rounds it (half away from zero) -- NOT
    // Math.round(d), which is -0 for d == -0.5 while the text already reads "(-1)".
    const glows = Math.round(Math.abs(d)) !== 0;
    // capEta rides the SAME test as the delta -- no inversion. d > 0 is a better-than-average
    // battle, which LOWERS battles_to_axis_hi (fewer repeats still needed), so "d > 0 -> green"
    // already reads correctly on the countdown too. The intuitive-but-wrong instinct is "more
    // battles remaining is worse, so invert" -- resist it; there is no separate battles-count
    // delta to test against, only this one d.
    [capV(capC), capDN, fill, tProj, capEta].forEach(function (e) {
        e.classList.toggle("mp-up", glows && d > 0);
        e.classList.toggle("mp-down", glows && d < 0);
    });
}

// Everything that does NOT animate: the axis-end captions + their mark glyphs, the static pre_avg
// tick and caption, and the met-requirement gold. Safe to re-run on every push.
function paintStatic() {
    capV(capR).textContent = fmt(cur.axisHi);
    setIco(capR, cur.marks >= 3 ? 4 : cur.marks + 1);   // 3 marks -> the general MoE glyph
    // THE REMAINING-BATTLES COUNT, second pair of the same row -- moved here off the delta because it
    // is a countdown to THIS requirement, and because on the delta it cost 15.18rem of the clipping
    // budget (see the header's re-derivation).
    // SUPPRESSION COLLAPSES THE BOX, IT DOES NOT JUST BLANK THE ART: `.mp-ico.none` is
    // `display: none` (MoEProgress.css), so a suppressed glyph takes NO width and NOT the shared
    // 1rem gap either -- verified in the stylesheet before reusing the variant, because a
    // background-only blank would have left a 14rem hole mid-row. The class is toggled, never
    // rewritten: setIco() reassigns className wholesale and would drop `battles`, which is why the
    // family class is static in the template. The TEXT has to be cleared too -- a live count beside a
    // collapsed glyph is exactly the state this suppression exists to avoid.
    // WHEN: >= 1 only. 0 means the requirement is already met (.mp-full's gold says so, and
    // battles_to_axis_hi returns 0 on precisely the same proj_avg >= axis_hi test), -1 is the no-data
    // sentinel, and `>= 1` on a Number() of a possibly-ABSENT field is NaN-false -- so a pre-push
    // frame or an older harness fixture renders no count rather than a bogus one.
    const showEta = cur.eta >= 1;
    capEtaIco.classList.toggle("none", !showEta);
    capEta.textContent = showEta ? fmt(cur.eta) : "";
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
// This is the transient's onRewind hook: it runs INSIDE a cold show, before the run is armed.
// `atCurrent` is the shared coldShow's `!fromDamage`, i.e. true exactly for peekOn's Alt entry.
function coldRewind(atCurrent) {
    clearTimeout(swapT);
    capD.style.transition = "none";
    swapped = !!atCurrent;
    showVal(swapped);
    T.disarm();
    void root.offsetWidth;
    setPos(swapped ? cur.projAvg : cur.preAvg, false);
    void root.offsetWidth;
    capD.style.transition = "";
}

// ...and this is its onCommit hook: the pre->current climb, run after the transient arms a DAMAGE
// cold show and after every warm re-trigger.
//
// WARM RE-TRIGGER: a change arrived while the bar is ALREADY up, so the transient re-measures the
// DISAPPEARANCE rather than replaying the appearance (see its warmShow). NOTE the one place the
// phase-1 plan does NOT apply: we deliberately do NOT rewind the fill/tick to their resting values
// there. They stay where they are so the bar animates from its CURRENT position to the new target --
// the rewind above is for cold shows only. For the same reason the bottom numeral is left showing
// the PREVIOUS proj_avg until the scheduled swap, so number and bar still commit together.
//
// THE rAF IS COLD-ONLY AND THAT ASYMMETRY IS DELIBERATE: after a cold entry the run class was just
// added and coldRewind wrote a resting value, so the class change and the new target must land in
// DIFFERENT frames (the tuner does the same). A warm re-trigger rewound nothing and rearmed at the
// plateau, so it sets the target synchronously -- as this bar always has.
function commitClimb(cold) {
    if (cold) {
        requestAnimationFrame(function () { setPos(cur.projAvg, true); });
    } else {
        setPos(cur.projAvg, true);
    }
    scheduleSwap();
}

// The transient's onEnd hook -- the value half of its FORCE-SETTLE. mp-life is both-filled so the
// root rests at its 100% stop (opacity 0) with no help from JS, but a swap timer longer than the
// transient would otherwise leave the resting bar showing pre_avg forever, and a cancelled delta
// fade could strand part-way. showVal(true) sets both outright. Ported from
// gen_bar_tuner.ps1:931-940.
function settleValues() {
    clearTimeout(swapT);
    setPos(cur.projAvg, false);
    swapped = true;
    showVal(true);
}

// ...and its onIdle hook: the resting/hidden state. No showVal here -- the bar is invisible, and the
// next entry rewinds the values itself (coldRewind).
function idleValues() {
    clearTimeout(swapT);
    swapped = true;
}

// THE TRANSIENT. Everything shared with MoEEfficiency.js -- arming and its negative-delay debounce,
// the run clock, the ALT PEEK (play or keep mp-life and PAUSE it at the hold plateau, so the entry is
// the real fade+slide and the hold simply never ends; on release, mirror into the fade-out or RESUME
// an interrupted damage hold), the animationend-vs-timer end race, and the surface push +
// post-deadline re-assert. Read its header before touching any of it.
// This bar uses ALL FOUR hooks, because unlike the Damage Efficiency bar its cold entry has values to
// rewind and a pre->current climb to commit. Note peekOn's entry arrives as onRewind(atCurrent=true):
// the Alt entry opens on the CURRENT values, never the pre-battle rewind -- Python pushes a fresh
// compute in the same transaction as setAltHeld (battle_bridge._set_alt_held), so the VM is already
// current and the outdated first frames were purely that rewind.
const T = createTransient({
    root: root,
    boxLeft: BOX_LEFT_REM,
    boxTop: BOX_TOP_REM,
    boxW: BOX_W_REM,
    boxH: BOX_H_REM,
    pad: PAD_REM,
    onRewind: coldRewind,
    onCommit: commitClimb,
    onEnd: settleValues,
    onIdle: idleValues,
});

function render(model) {
    // Truthy guards, not `=== false`: a root VM whose flags are still undefined before Python's
    // first push must stay hidden, not paint a zero-width bar over the HUD. hasData false means
    // the per-tank threshold table gave no usable mark axis -- there is nothing to plot.
    if (!model || !model.visible || !model.hasData) {
        root.style.display = "none";
        T.reset();
        // Drop the change-detect baseline too, so a later re-show starts COLD and the next push
        // becomes a fresh silent one (a scoreboard opening and closing must not replay the bar).
        last = null;
        return;
    }
    root.style.display = "";
    // The pushed size mode (mod_settings.progress_bar_size). Idempotent in the transient, so this is
    // just "keep it in sync"; it owns the root-font write, the .mp-lg body class and the re-derived
    // surface. Nothing in THIS file measures px, so there is nothing else to scale here (contrast
    // MoEEfficiency.js's capClampPct, which mixes offsetWidth with rem literals).
    T.size(Number(model.barSize) === 1);
    // The pushed TRANSITION switches (mod_settings.progress_transitions_events / _manual, with the
    // Transitions master already ANDed in Python -- there is no master field to read here). The
    // transient only records them; the arming path decides per run. Passed RAW, deliberately: the
    // transient reads an ABSENT field as animated (see applyAnim), which is the fail-soft direction --
    // a `!!` here would turn a missing prop into "instant" instead.
    T.anim(model.transEvents, model.transManual);
    // The pushed HOLD DURATION (mod_settings.progress_hold_seconds * 1000). Passed RAW for the same
    // reason as the two switches: the transient reads an absent / non-positive field as the baked
    // 5000ms (see applyHold), which is the fail-soft direction -- a `|| 0` here would mean no hold.
    T.hold(model.holdMs);
    // The pushed CTRL key state (battle_bridge._ctrl_held): the drag-to-reposition gesture, which
    // opens the input hit rect and holds the bar up for as long as the key is down. Passed RAW like
    // the three above -- the transient tests it with `=== true`, so an absent field reads as NOT
    // held, which is the fail-soft direction HERE (an open hit rect would steal HUD input). Ahead
    // of T.peek() below, which ORs this state in.
    T.ctrl(model.ctrlHeld);

    cur = {
        marks: Number(model.marks) || 0,
        axisLo: Number(model.axisLo) || 0,
        axisHi: Number(model.axisHi) || 0,
        preAvg: Number(model.preAvg) || 0,
        projAvg: Number(model.projAvg) || 0,
        // NO `|| 0` here, deliberately: 0 is a MEANINGFUL value (requirement met) and an absent
        // field must not collapse into it. Number(undefined) is NaN, which paintStatic's `>= 1` reads
        // as "render no count" -- the fail-soft direction for a brand-new VM field.
        eta: Number(model.etaBattles),
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

    // THE SHOW TRIGGER IS GATED ON T.settled(); THE SILENT BASELINE BELOW IS NOT. Before the
    // re-assert the surface is the engine's 256x256 fallback: the bar would come up cropped and
    // ~142px too high (see the shared module's SURFACE_REASSERT_MS). The baseline shows nothing, so
    // it costs nothing to let it run -- and it MUST run, or `last` never gets recorded and the first
    // real change plays a bogus pre->proj climb. T.show() picks warm-vs-cold off its own `showing`.
    //
    // THE SHOW TRIGGER IS ALSO GATED ON `showEvents` (mod_settings.progress_show_events, with
    // "Always" already folded in Python -- there is no master field to read here). `!== false`, NOT
    // `!!`: a model that does not carry the field at all (a pre-push frame, a harness fixture) must
    // degrade to the SHIPPED behaviour, which is "an event raises the bar". The other two visibility
    // switches need no branch -- "Alt Press" and "Always" both arrive folded into `altHeld` below.
    if (first) {
        // Silent baseline: settle the bar at its resting values without showing anything.
        setPos(cur.projAvg, false);
        swapped = true;
        showVal(true);
    } else if (changed && model.showEvents !== false && T.settled()) {
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
