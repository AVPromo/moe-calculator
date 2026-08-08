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
// TWO ORIENTATIONS, ONE DOCUMENT, and that is NOT a contradiction of the line above: this document
// DOES <link> a second stylesheet, MoEEfficiencyVertical.css, whose prefix (.mev-*) is disjoint from
// .mp-* by construction -- so the only selectors that can collide are `body`, `#moe-bar-box` and
// `#moe-bar-root`, and those three are the only ones the vertical sheet scopes under its `body.mev`
// class. Which composition draws comes from mod_settings' progress_bar_orientation, pushed as the
// VM's `vertical`, as a MOUNT-TIME branch (goVertical) -- NOT a second res_map layout, because a new
// itemID would cost every user a one-time client restart. The PLACEMENT half is Python's and already
// orientation-aware (bridge/bar_window._resolve).
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
import { createTransient, fmt, SIZE_F, SIZE_XF } from "./MoEBarTransient.js";

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

// The pushed LARGE size mode (VM `barSize`), mirrored here because capClampPct needs it -- it is the
// one place on either bar that mixes a MEASURED px width with rem literals, so the 1rem == 1 logical
// px identity it rests on breaks under the large mode's 1.25x root font. The transient owns everything
// else about the flag (see its SIZE_F / SIZE_XF).
let large = false;

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
// SHIFT_Y_REM is MIRRORED (negated) in Python as
// domain/constants.EFFICIENCY_ANCHOR_Y_SHIFT, so changing BOX_TOP_REM or PAD_REM moves the bar on
// screen until that constant follows. The hit padding and the re-assert timing live in the shared
// module (its HIT_MAGIC / SURFACE_REASSERT_MS -- both LOAD-BEARING, read its header).
const BOX_LEFT_REM = -80;                            // .mp-backdrop's left  == leftmost edge
const BOX_TOP_REM = -40;                             // .mp-backdrop's top   == topmost edge
const BOX_W_REM = 460;                               // .mp-backdrop's width  (== meta.boxWRem)
const BOX_H_REM = 96;                                // .mp-backdrop's height
const PAD_REM = 10;                                  // slack for the shadow/glow bleed

// --- THE VERTICAL ORIENTATION (mod_settings.progress_bar_orientation, pushed as the VM's
// `vertical`) ------------------------------------------------------------------------------------
// A SECOND COMPOSITION IN THE SAME DOCUMENT, not a restyle of this one: its own stylesheet
// (MoEEfficiencyVertical.css, <link>ed alongside MoEEfficiency.css from MoEEfficiencyView.html),
// its own namespace-disjoint prefix (.mev-*), its own DOM order (numeral BEFORE icon, delta LEFT of
// the numeral) and its own surface. NO second res_map entry: orientation is a MOUNT-TIME branch,
// and a new itemID would cost every user a one-time client restart.
//
// V_BOX_* IS .mev-backdrop, exactly as BOX_* above is .mp-backdrop. Note it is NOT a transpose of
// these four -- the vertical tuner's own tuned lengths -- but its TOP and HEIGHT are IDENTICAL to
// the vertical Moving Average bar's (-80 / 360), which is why the two share ONE Python shift
// constant where their horizontal siblings need -50 and -44 apiece:
//   V_VIEW_W_REM = V_BOX_W_REM + 2 * PAD_REM == 116   V_SHIFT_X_REM = PAD_REM - V_BOX_LEFT_REM == 50
//   V_VIEW_H_REM = V_BOX_H_REM + 2 * PAD_REM
//                               - V_CLIP_B_REM == 318 V_SHIFT_Y_REM = PAD_REM - V_BOX_TOP_REM  == 90
// V_SHIFT_Y_REM is MIRRORED (negated) in Python as domain/constants.VERTICAL_ANCHOR_Y_SHIFT (-90,
// -113 for Large == -round(90 * SIZE_F)). #moe-bar-box in MoEEfficiencyVertical.css is sized to the
// derived surface -- and unlike the horizontal file's box (left at the tuner's own emitted 460x55,
// deliberately not a surface copy) that one IS a third copy: keep it in lockstep.
//
// THE SURFACE IS THE ONLY SIDE THAT IS NOT box + PAD_REM, AND THAT IS THE WHOLE POINT (V_CLIP_B_REM).
// Read the sibling MoEProgress.js's own V_CLIP_B_REM note first -- the mechanism, the engine clamp it
// works around and the Large-mode reasoning are IDENTICAL and are written out once, there. Only the
// two numbers differ, because the two vertical tuners' bottom gaps differ:
//   V_CLIP_B_REM == (V_BOX_H_REM + 2*PAD_REM) - (V_SHIFT_Y_REM + barLen + bottomGap)
//                == 380 - (90 + 200 + 28) == 62
// `bottomGap` 28 is THIS bar's tuned value (tools/dev/eff_bar_tuner_vertical.html:470), against the
// Moving Average tuner's 30 -- a difference that used to be UNOBSERVABLE (both were below the shared
// 90 of slack, so the clamp flushed either to the same place) and is observable now, which is exactly
// why domain/constants' single MM_GAP_BOTTOM is split per bar in the same change.
// The surface's below-the-track slack becomes 318 - 290 == 28 == the tuned gap exactly (290 is
// V_SHIFT_Y_REM + barLen == domain/constants.MM_TRACK_Y, which this does NOT move). Under Large the
// pushed surface is round(318 * SIZE_F) == 398 against MM_TRACK_Y_LARGE 363, i.e. 35 of slack ==
// 28 * SIZE_F exactly -- so the fixed 28 is unreachable there and the engine's flush delivers the
// scaled gap, which is the sibling's 30 -> 37 case with this bar's own two numbers.
// WHAT IT COSTS, DERIVED FROM THE SHIPPED CSS, is 3.5rem of clearance on the bottom caption's ink and
// nothing else. .mev-cap.bt (MoEEfficiencyVertical.css) is `top: 100%` + `margin-top: 3rem` off the
// track's bottom end and its flex row is `line-height: 20.5rem` tall (the numeral's line box beats its
// 16rem .dmg icon; the delta is position:absolute and contributes no height at all), so its box ends
// 3 + 20.5 == 23.5rem below the track; the numeral's 1rem dark-drop text-shadow radius reaches 24.5,
// the icon's translateY(0.5rem) + its ::before 106% glow (3% of 16rem) reaches 22.2, and the delta --
// `top: 0` + translate(_, 1.5rem), 15.5rem tall, + 1rem of drop -- reaches 21.0. So the deepest ink is
// 24.5 against 28 of slack. The ONLY thing past the edge is the band glow's soft tail (the 6rem blur
// on .mev-cap.bt .mev-v under every #moe-bar-root.mev-b-* band, reaching ~29.5), which the tuner clips
// at its own stage bottom at the same 28.
// THE 256x256 SIZE-TIMEOUT FALLBACK STILL RUNS LAST AND STILL WINS here, and the vertical surface is
// pushed and RE-ASSERTED after the deadline by the same shared machinery (MoEBarTransient's
// SURFACE_REASSERT_MS); each push round-trips back as onSizeChanged -> bar_window._place, which is
// what makes the placement agree with the surface.
const V_BOX_LEFT_REM = -40;                          // .mev-backdrop's left
const V_BOX_TOP_REM = -80;                           // .mev-backdrop's top
const V_BOX_W_REM = 96;                              // .mev-backdrop's width
const V_BOX_H_REM = 360;                             // .mev-backdrop's height
const V_CLIP_B_REM = 62;                             // backdrop bleed the SURFACE clips off the bottom

// THE LIVE ORIENTATION PROFILE -- see the sibling MoEProgress.js for the same three-value shape.
//   PFX      the class prefix every selector and toggled class here is written in. The source spells
//            everything "mp-..." and ns() rewrites it, so the literals stay greppable.
//   AX       the property a marker's position is written to: `left` / `bottom` (0% at the BOTTOM).
//   GROW     the property the fill grows along: `width` / `height`.
//   CAP_C_AX the axis the CURRENT caption tracks, or null if it does not move. It is null on the
//            vertical composition, where the current value + delta are a STATIC readout below the
//            track's bottom end and only the current TICK follows the fill -- which also retires
//            capClampPct entirely there (a static caption cannot overflow the corridor).
let PFX = "mp";
let AX = "left";
let GROW = "width";
let CAP_C_AX = "left";

function ns(s) { return PFX === "mp" ? s : s.replace(/\bmp-/g, PFX + "-"); }

// THE HORIZONTAL COMPOSITION'S MARKUP (the vertical one is V_MARKUP below; ensureRoot builds this
// one and goVertical replaces it). Markup shape is the tuner's stage verbatim
// (eff_bar_tuner.html:333-351): backdrop, then the track carrying the fill, the four FIXED
// requirement ticks, the one moving current tick, the four requirement captions (three marksOnGun
// glyphs + the barrel_mark at 100 %) and the current caption with its BARE signed delta -- no
// parens on this bar, unlike the Moving Average one. The .mp-d / .mp-d-num split stays anyway: the
// wrapper carries the gap, size and fade, the inner numeral is what JS writes the digits into (see
// the CSS). NO word labels anywhere: MoEBattle.ttf is a 19-glyph numeric subset
// (digits % ( ) + - , . / space) and a letter renders BLANK.
const MARKUP =
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

// ...and THE VERTICAL COMPOSITION'S markup, tools/dev/eff_bar_tuner_vertical.html's stage verbatim.
// FOUR structural differences from the horizontal template above, all of them the tuner's tuned
// layout and none free to "tidy":
//   * NUMERAL BEFORE ICON in every caption (the icon trails, away from the track), and the DELTA
//     FIRST on the current caption. That ordering is what makes the shared right:100% anchor
//     digit-count invariant: the icon is the LAST in-flow child, flush against a FIXED edge, so only
//     the numeral grows and it grows leftward. Reversing it re-introduces the exact defect that
//     shipped once on the horizontal Moving Average bar.
//   * the four requirement captions split by ROLE, not one `dn` class: r1-r3 are `lf` (each beside
//     its own 25/50/75% tick) and r4 is `tp` (a static cap above the track's TOP end), because a
//     vertical axis has no single "below the track" side to share.
//   * the current caption is `bt mev-capC` -- a static cap below the BOTTOM end. It keeps mev-capC
//     purely so the ref lookup below is one selector for both orientations.
//   * every caption is a SIBLING of .mev-track rather than a child, exactly as the tuner has them
//     (root and track are the same 3x200rem box, so every percentage resolves identically; this
//     only keeps the diff against the tuner readable).
const V_MARKUP =
        '<div class="mev-backdrop"></div>' +
        '<div class="mev-track">' +
        '  <div class="mev-fill"></div>' +
        '  <div class="mev-tick mev-req r1"></div>' +
        '  <div class="mev-tick mev-req r2"></div>' +
        '  <div class="mev-tick mev-req r3"></div>' +
        '  <div class="mev-tick mev-req r4"></div>' +
        '  <div class="mev-tick mev-cur"></div>' +
        '</div>' +
        '<div class="mev-cap lf r1"><span class="mev-v"></span><i class="mev-ico mk mk1"></i></div>' +
        '<div class="mev-cap lf r2"><span class="mev-v"></span><i class="mev-ico mk mk2"></i></div>' +
        '<div class="mev-cap lf r3"><span class="mev-v"></span><i class="mev-ico mk mk3"></i></div>' +
        '<div class="mev-cap tp r4"><span class="mev-v"></span><i class="mev-ico bm"></i></div>' +
        '<div class="mev-cap bt mev-capC"><span class="mev-d"><span class="mev-d-num"></span></span>' +
        '<span class="mev-v"></span><i class="mev-ico dmg"></i></div>';

function ensureRoot() {
    let root = document.getElementById("moe-bar-root");
    if (root) return root;
    root = document.createElement("div");
    root.id = "moe-bar-root";
    root.innerHTML = MARKUP;
    document.body.appendChild(root);
    return root;
}

const root = ensureRoot();
// `let`, not `const`, because goVertical() rebuilds the root's contents under the .mev- prefix and
// every ref has to be re-queried against the new nodes. Under a single orientation nothing rewrites
// them. `.mp-capC` (not the old `.mp-cap.up`) is the current caption's lookup on BOTH orientations:
// the vertical composition's equivalent role class is `bt`, not `up`, so the shared marker class is
// what makes one ns()-rewritten selector serve both.
let fill = root.querySelector(".mp-fill");
let tCur = root.querySelector(".mp-tick.mp-cur");
let reqTicks = [1, 2, 3, 4].map(function (i) { return root.querySelector(".mp-tick.r" + i); });
let reqCaps = [1, 2, 3, 4].map(function (i) { return root.querySelector(".mp-cap.r" + i); });
let capC = root.querySelector(".mp-capC");
let capD = capC.querySelector(".mp-d");
let capDN = capC.querySelector(".mp-d-num");

// ADOPT THE VERTICAL COMPOSITION -- the bar's half of MoEBarTransient's onVertical hook (the shared
// module owns the surface, the rigid shift, the run-identity pair and the body scope class). Called
// ONCE, inside engine.whenReady, BEFORE the surface push and before the first render, so nothing
// downstream ever sees the horizontal DOM. A mid-battle Orientation change re-mounts this document
// (Python closes and reopens the window -- battle_bridge.apply_settings) and comes straight back
// through here; there is deliberately no live re-composition path.
function goVertical() {
    PFX = "mev";
    AX = "bottom";
    GROW = "height";
    CAP_C_AX = null;                 // a STATIC bottom cap here -- see the profile note
    root.innerHTML = V_MARKUP;
    fill = root.querySelector(".mev-fill");
    tCur = root.querySelector(".mev-tick.mev-cur");
    reqTicks = [1, 2, 3, 4].map(function (i) { return root.querySelector(".mev-tick.r" + i); });
    reqCaps = [1, 2, 3, 4].map(function (i) { return root.querySelector(".mev-cap.r" + i); });
    capC = root.querySelector(".mev-capC");
    capD = capC.querySelector(".mev-d");
    capDN = capC.querySelector(".mev-d-num");
}

function capV(c) { return c.querySelector(ns(".mp-v")); }

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
// of the two overhangs is added back, the icon's with its transform gap. A zero measured width
// (nothing laid out yet) simply degrades to no clamp.
//
// THE TWO SIZE FACTORS BOTH LAND HERE, and this is the ONE function on either bar where the
// 1rem == 1 logical px identity is load-bearing rather than incidental:
//   * every rem CONSTANT above is an x-length (the bar's width, the corridor's two bounds, the icon's
//     transform gap), so each takes SIZE_XF -- the corridor bounds included, since they are the
//     backdrop inset by an equal x-length each side and so scale with it;
//   * offsetWidth is MEASURED PX, and under the large mode's root font 1rem is SIZE_F px, so
//     every measurement is divided back into document rem. A caption's width in rem is unchanged by
//     the root font (its font-size is a rem too), which is exactly why this cannot be normalised
//     away: the corridor scales by SIZE_XF while the caption inside it does not.
function capClampPct(p) {
    const xf = large ? SIZE_XF : 1;
    const px = large ? SIZE_F : 1;
    const w = function (q) {
        const n = capC.querySelector(q);
        return ((n && n.offsetWidth) || 0) / px;
    };
    const half = (capC.offsetWidth || 0) / 2 / px +
                 Math.max(w(".mp-ico") + ICO_GAP_REM * xf, w(".mp-d"));
    const lo = CLAMP_L_REM * xf + half;
    const hi = CLAMP_R_REM * xf - half;
    let x = p / 100 * BAR_W_REM * xf;
    if (lo <= hi) x = Math.max(lo, Math.min(hi, x));
    return x / (BAR_W_REM * xf) * 100;
}

// Position the fill, the moving tick and its caption from the PUSHED barX (never recomputed here).
// No rewind/snap variant and no transition suppression, unlike MoEProgress.setPos: this bar has a
// single set of values, so the CSS's 400ms fill/left transitions may always run -- exactly what the
// tuner's own hit() does. On a cold entry they run under the 600ms fade-in and are invisible.
// THE AXIS IS A PAIR OF PROPERTY NAMES, not two code paths: GROW is the fill's growth property
// (`width` horizontally, `height` vertically -- 0% at the BOTTOM) and AX the current tick's position
// property (`left` / `bottom`). CAP_C_AX is null on the vertical composition, where the current
// caption is a static readout below the track's bottom end -- so capClampPct, whose whole job is
// keeping a MOVING caption inside a horizontal corridor, is not reached there at all.
function setPos(x) {
    const p = x.toFixed(3) + "%";
    fill.style[GROW] = p;
    tCur.style[AX] = p;
    if (CAP_C_AX) capC.style[CAP_C_AX] = capClampPct(x).toFixed(3) + "%";
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
    BAND_CLASSES.forEach(function (c, i) { root.classList.toggle(ns(c), i === cur.band); });
    // The pulse rule is #moe-bar-root.mp-b-au.mp-pulse .mp-track, so this class is inert off gold
    // anyway -- gate it on the band regardless, so the DOM says what it means.
    root.classList.toggle(ns("mp-pulse"), cur.band === 4);
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
    // THE VERTICAL COMPOSITION. `cls` is the body scope class MoEEfficiencyVertical.css hangs off AND
    // the key to that stylesheet's own re-trigger keyframe twin (MoEBarTransient's RUN_CLASSES_V);
    // `box` replaces the four box* arguments above. Adopted at mount iff the model's `vertical` is
    // true, which then calls goVertical above for the DOM half.
    vert: { cls: "mev", box: [V_BOX_LEFT_REM, V_BOX_TOP_REM, V_BOX_W_REM, V_BOX_H_REM],
            clipB: V_CLIP_B_REM },
    onVertical: goVertical,
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
    // The pushed size mode (mod_settings.progress_bar_size), BEFORE setPos: capClampPct reads it. The
    // transient owns the rest of the flag (the root-font write, the .mp-lg body class, the re-derived
    // surface) and is idempotent, so this is just "keep it in sync".
    large = Number(model.barSize) === 1;
    T.size(large);
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
    //
    // ALSO GATED ON `showEvents` (mod_settings.progress_show_events, with "Always" already folded in
    // Python). `!== false`, NOT `!!`: a model without the field (a pre-push frame, a harness
    // fixture) must degrade to the SHIPPED behaviour, which is "a hit raises the bar". The delta
    // caption rides the same gate -- with the bar staying down there is nothing to flash. "Alt
    // Press" and "Always" need no branch here: both arrive folded into `altHeld` below.
    if (gained && model.showEvents !== false && T.settled()) {
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
