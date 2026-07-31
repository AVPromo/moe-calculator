/* check_progress_js.js -- headless behavioural self-check for MoEProgress.js (the in-battle
 * centre-screen MOVING AVERAGE progress bar's front-end) AND the shared MoEBarTransient.js it now
 * drives. Plain Node, zero dependencies, zero framework. Sibling of check_efficiency_js.js, which
 * does the same job for the Damage Efficiency bar; the DOM shim, the virtual clock, the assertion
 * helpers, the constant scraper and the mutation applier are shared in tools/dev/lib/gf_check_shim.js.
 *
 *   node tools/dev/check_progress_js.js
 *   node tools/dev/check_progress_js.js --mutate=<key>     (anti-vacuity check, see MUTATIONS)
 *   node tools/dev/check_progress_js.js --probe-all        (every mutation, as a table)
 *   node tools/dev/check_progress_js.js --list-mutations
 *
 * WHY THIS EXISTS. The bar lives in a res_map-registered Gameface WINDOW, which pins its
 * resources at client launch: there is NO hot-reload, so every JS timing hypothesis costs a full
 * client relaunch to test. The transient is a wall-clock state machine (a 6200ms keyframe seeked
 * with negative animation-delay, a fallback end timer, an Alt peek that pauses the animation), and
 * that is exactly the kind of logic a virtual clock can prove on the desk.
 *
 * IT ASSERTS EMITTED VALUES, not "the file parsed". Per the repo lesson recorded as
 * `bar-tuner-selfcheck-is-not-a-gate` (gen_bar_tuner.ps1's -SelfCheck once passed
 * `"holdMs": true` because it only checked for leftover tokens), every check below reads a value
 * one of the two modules actually WROTE -- the viewEnv resize args, the animation-delay string, the
 * run class, animationPlayState, the fill width percentage, the caption text -- and compares it to
 * an expected literal.
 *
 * TWO FILES, ONE SCOPE. MoEProgress.js is now a thin caller of MoEBarTransient.js, so the shim
 * concatenates the two (transient FIRST) and evaluates them as one `new Function` body -- see the
 * shim's concatModules. Which file a mutation belongs to is spelled out in the table below: "T" is
 * the shared transient, "B" is this bar.
 *
 * WHAT IS AND IS NOT COVERED. This exercises module LOGIC only -- no layout, no CSS, no compositor.
 * The static HTML/CSS/Python mirror of the surface size is guarded separately by
 * tests/test_progress_surface_mirror.py.
 */
"use strict";

const S = require("./lib/gf_check_shim.js");
const { section, eq, ok, El, parseHTML, makeClock, makeRootFont, jsConst, jsArray, jsFactor } = S;

const T_SRC = S.read("MoEBarTransient.js");         // the shared transient  -> "T"
const B_SRC = S.read("MoEProgress.js");             // this bar              -> "B"
const VIEW_HTML = S.read("MoEProgressView.html");

// Source mutations for the anti-vacuity check: each breaks ONE real behaviour, and a run with it
// applied MUST fail. Keep them tiny and surgical. [WHICH, from, to] -- WHICH is "T" or "B", and
// naming it is the point of this table: the 187 lines that moved into MoEBarTransient.js took most
// of these anchors with them.
const MUTATIONS = {
    // ===== the SHARED transient ==============================================================
    // Every behaviour in here cost a client relaunch to find; see the module's own header.
    "no-surface-push": ["T",
        "            if (viewEnv.resizeViewRem) viewEnv.resizeViewRem(viewW, viewH);",
        "            if (viewEnv.resizeViewRem) viewEnv.resizeViewRem(256, 256);"],
    "no-hit-collapse": ["T",
        "        if (!viewEnv.setHitAreaPaddingsRem) return;", "        return;"],
    "hit-rect-not-collapsed": ["T",
        "            viewEnv.setHitAreaPaddingsRem(hitPad, hitPad, hitPad, hitPad, HIT_MAGIC);",
        "            viewEnv.setHitAreaPaddingsRem(0, 0, 0, 0, HIT_MAGIC);"],
    "no-texture-freeze": ["T",
        "            if (viewEnv.freezeTextureBeforeResize) viewEnv.freezeTextureBeforeResize();",
        "            void 0;"],
    "no-rigid-shift": ["T",
        '            root.style.left = shiftX + "rem";', '            root.style.left = "0rem";'],
    // The Change-2 guard: no re-assert of the surface size after the engine's fallback deadline.
    // Drops ONLY the inner (second) push, leaving the `settled` flip nested below it intact.
    "no-surface-reassert": ["T",
        "                pushSurfaceSize();\n                setTimeout(function () {",
        "                setTimeout(function () {"],
    // The show triggers must WAIT for the re-assert: before it the surface is the engine's 256x256
    // fallback, which crops the composition and -- because Python's anchor conversion bakes in a
    // 92-tall surface -- places the bar ~142px too high. Two halves, two mutations, because only an
    // Alt peek at battle start can reach the transient's own half.
    "no-settle-gate": ["T",
        "                if (!peeking && settled) peekOn();",
        "                if (!peeking) peekOn();"],
    // ...and the flip must RE-RENDER the model already held, or an Alt held across the settle only
    // appears on the next Python push -- and during PREBATTLE there may not be one.
    "no-settle-rerender": ["T", "                    render(observer.model);", ""],
    // The mp-run <-> mp-run-b alternation: consecutive runs must never share an animation-name for
    // the engine to coalesce a restart with.
    "no-identity-alternation": ["T", "        armIdx = 1 - armIdx;", "        armIdx = 0;"],
    // THE DEBOUNCE ITSELF: a negative animation-delay is the only way to seek into a both-filled
    // keyframe whose hold cannot be extended in place.
    "no-negative-delay-debounce": ["T",
        '        root.style.animationDelay = seekMs ? "-" + seekMs + "ms" : "0ms";',
        '        root.style.animationDelay = "0ms";'],
    // ...and the warm re-trigger must not replay the entry from opacity 0.
    "warm-replays-entry": ["T",
        "            armRun(SEEK_PLATEAU);        // the seek lands us AT the plateau",
        "            armRun(SEEK_NONE); //"],
    // A superseded run's animationend must not end the live run.
    "no-identity-guard": ["T",
        "        if (e.animationName !== RUN_NAMES[armIdx]) return;\n", ""],
    // The H2 guard: without the fallback timer a missing animationend wedges `showing` forever.
    "no-end-timer": ["T",
        "        endT = setTimeout(function () { endRun(id); }, TOTAL_MS - seekMs + END_MARGIN_MS);",
        "        endT = null;"],
    // The peek is held open by PAUSING the animation at the plateau...
    "peek-no-pause": ["T",
        '            root.style.animationPlayState = "paused";', "            void 0;"],
    // ...and a paused hold never ends, so the fallback timer must be cancelled with it.
    "peek-ends-while-held": ["T",
        "            clearTimeout(endT);\n        }, Math.max(0, plateauAt - Date.now()));",
        "        }, Math.max(0, plateauAt - Date.now()));"],
    // THE ELAPSED-NOT-A-FLAG RULE. Drop the fade-out re-arm, so Alt during the fade-out pauses the
    // animation part-way through it (the bar freezes at partial opacity)...
    "no-fadeout-rearm": ["T",
        "        } else if (!peeking && Date.now() >= plateauAt + HOLD_MS) {",
        "        } else if (false) {"],
    // ...and the tempting `showing` form, which stays true THROUGH the fade-out and so never fires.
    "peek-phase-from-a-showing-flag": ["T",
        "        } else if (!peeking && Date.now() >= plateauAt + HOLD_MS) {",
        "        } else if (!peeking && !showing) {"],
    "release-no-fadeout-seek": ["T", "        armRun(SEEK_FADE_OUT + inLeft);", ""],
    // The hold-to-show guard: put back the bail this bar's history DELETED (peekOff returned unless
    // the plateau pause had already landed), so a sub-FADE_IN_MS tap serves the whole transient
    // again -- the toggle-like behaviour that was the bug.
    "tap-runs-out": ["T",
        "        const inLeft = Math.min(",
        '        if (root.style.animationPlayState !== "paused") return;\n' +
        "        const inLeft = Math.min("],
    // THE DAMAGE-HOLD RESUME (dmgPlateauAt). Four surgical halves, because each one resurrects or
    // truncates a different show and only its own assertion can see it.
    "no-resume-on-release": ["T",
        "        if (dmgPlateauAt + HOLD_MS > Date.now()) {", "        if (false) {"],
    "peek-dmg-uses-stale-plateau": ["T",
        "        dmgPlateauAt = peeking ? Date.now() : plateauAt;",
        "        dmgPlateauAt = plateauAt;"],
    "endrun-keeps-dmg-plateau": ["T",
        "        dmgPlateauAt = 0;                // the hold is over",
        "        // dmgPlateauAt = 0;  // the hold is over"],
    "reset-keeps-dmg-plateau": ["T",
        "        dmgPlateauAt = 0;                // ditto endRun",
        "        // dmgPlateauAt = 0;  // ditto endRun"],
    "reset-does-not-disarm": ["T",
        "        endedId = runId;                 // no live run left for a late animationend " +
        "to end\n        disarm();",
        "        endedId = runId;"],
    // fmt() moved with the transient; the numerals are this bar's only readout of it.
    "no-thousands-sep": ["T", '.replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",")', ""],

    // ===== THIS BAR ==========================================================================
    "no-change-gate": ["B", "} else if (changed && T.settled()) {", "} else if (changed) {"],
    // THE COLD REWIND: a cold show must snap the fill back to pre_avg before the run.
    "no-cold-rewind": ["B",
        "    setPos(swapped ? cur.projAvg : cur.preAvg, false);", "    void 0;"],
    // THE rAF ASYMMETRY, both directions -- it is the ONE thing that must not be flattened into the
    // shared onCommit hook. Cold: the class change and the new target must land in DIFFERENT frames.
    // Warm: nothing was rewound, so the target is set SYNCHRONOUSLY.
    "cold-commit-loses-its-raf": ["B",
        "        requestAnimationFrame(function () { setPos(cur.projAvg, true); });",
        "        setPos(cur.projAvg, true);"],
    "warm-commit-gains-a-raf": ["B",
        "        setPos(cur.projAvg, true);\n    }\n    scheduleSwap();",
        "        requestAnimationFrame(function () { setPos(cur.projAvg, true); });\n" +
        "    }\n    scheduleSwap();"],
    // endRun's onEnd hook must FORCE-SETTLE the values, or a swap timer longer than the transient
    // leaves the resting bar showing pre_avg forever. TWO halves, because they are separately
    // invisible: the numeral commit, and the fill SNAP. The snap only shows on a run that ends before
    // BOTH its swap and its cold rAF have landed -- deleting it failed NOTHING until the
    // "force-settle" section below was written to that shape (this file's own vacuous assertion).
    "endrun-does-not-force-settle": ["B",
        "    clearTimeout(swapT);\n    setPos(cur.projAvg, false);\n    swapped = true;\n" +
        "    showVal(true);\n}",
        "    clearTimeout(swapT);\n}"],
    "endrun-does-not-snap-the-fill": ["B",
        "    clearTimeout(swapT);\n    setPos(cur.projAvg, false);\n    swapped = true;",
        "    clearTimeout(swapT);\n    swapped = true;"],
    // The remaining paintStatic writes, each of which had an assertion and no probe.
    "no-mp-full-class": ["B",
        'root.classList.toggle("mp-full", cur.projAvg >= cur.axisHi);',
        'root.classList.toggle("mp-full", false);'],
    "wrong-next-mark-glyph": ["B",
        "setIco(capR, cur.marks >= 3 ? 4 : cur.marks + 1);", "setIco(capR, cur.marks);"],
    "pre-tick-not-painted": ["B", "    tPre.style.left = pre;", "    void 0;"],
    "pre-caption-not-painted": ["B", "    capP.style.left = pre;", "    void 0;"],
    // ...and setPos's third write, which had no assertion at all until the captions were re-centred
    // on their NUMERAL (MoEProgress.css .mp-capP/.mp-capC .mp-ico + .mp-cap .mp-d): the bottom
    // caption is the one that rides proj_avg, so its painted X is the whole point of that centring.
    "cur-caption-not-painted": ["B", "    capC.style.left = p;", "    void 0;"],
    // The entry window must CARRY the previous committed sign: put a clear back into the !sw path
    // and a bar that was green blinks neutral for 600ms before re-committing.
    "entry-clears-sign": ["B",
        "if (!sw) return;",
        'if (!sw) { [capV(capC), capDN, fill, tProj].forEach(function (e) {' +
        ' e.classList.remove("mp-up"); e.classList.remove("mp-down"); }); return; }'],
    // The glow must key off the delta AS ROUNDED, or a +0.4 shows a green "(+0)".
    "raw-sign-gate": ["B",
        "const glows = Math.round(Math.abs(d)) !== 0;", "const glows = d !== 0;"],

    // ===== THE LARGE SIZE MODE (VM `barSize` == 1) ===========================================
    // Each half is separately invisible in-client (the CSS half is guarded by
    // tests/test_progress_surface_mirror.py, the Python anchor by its constants), so each gets its
    // own anchor.
    "size-no-root-font": ["T",
        'document.documentElement.style.fontSize = large ? (baseFont * SIZE_F) + "px" : "";',
        "void 0;"],
    // ...and the base must be the PRE-EXISTING root font, not the factor itself.
    "size-root-font-ignores-the-base": ["T",
        '(baseFont * SIZE_F) + "px"', 'SIZE_F + "px"'],
    // The class MUST land on the BODY: #moe-bar-box is a body-level SIBLING of the JS-created root,
    // so a class on the root could never reach the sizing shim.
    "size-no-body-class": ["T", 'document.body.classList.toggle("mp-lg", large);', "void 0;"],
    // The x-lengths carry SIZE_XF on top of the root font's SIZE_F; drop it and the surface is
    // 1.5x wide instead of 2x, cropping the composition.
    "size-surface-loses-the-x-factor": ["T",
        "viewW = Math.round((cfg.boxW * xf + 2 * cfg.pad) * f);",
        "viewW = Math.round((cfg.boxW + 2 * cfg.pad) * f);"],
    // PAD_REM is slack on BOTH axes and must not take the x factor.
    "size-pad-wrongly-takes-the-x-factor": ["T",
        "viewW = Math.round((cfg.boxW * xf + 2 * cfg.pad) * f);",
        "viewW = Math.round((cfg.boxW + 2 * cfg.pad) * xf * f);"],
    // The y/uniform half must NOT take the x factor (that is what keeps the bar's height right).
    "size-height-wrongly-takes-the-x-factor": ["T",
        "viewH = Math.round((cfg.boxH + 2 * cfg.pad) * f);",
        "viewH = Math.round((cfg.boxH * xf + 2 * cfg.pad) * f);"],
    "size-shift-not-re-derived": ["T",
        "shiftX = Math.round((cfg.pad - cfg.boxLeft * xf) * 1000) / 1000;", "void 0;"],
    // The CSS side and the surface must be re-pushed together: the engine round-trips the resize
    // back into Python's _place, which is what makes the two agree on where the bar sits.
    "size-no-surface-repush": ["T",
        '        root.style.left = shiftX + "rem";\n        pushSurfaceSize();\n    }',
        '        root.style.left = shiftX + "rem";\n    }'],
    // Idempotent, because both bars call T.size() on EVERY render: without the guard every push
    // re-pushes the surface to the engine.
    "size-not-idempotent": ["T", "        if (flag === large) return;", "        if (false) return;"],
    // WG re-writes the root font off this event; if it ever reaches a registered view we must take
    // the pushed scale as the new base rather than keep compounding the mount-time capture.
    "size-ignores-a-scale-update": ["T",
        "                    baseFont = parseFloat(scale) || baseFont || 1;", "                    void 0;"],
    // ...and it must stay scoped to the large mode: the shipped size never touches the root font.
    "size-scale-update-not-gated": ["T",
        "                    if (!large) return;", "                    if (false) return;"],
    // THIS BAR's one line: the pushed flag has to reach the transient at all.
    "size-flag-never-pushed": ["B", "    T.size(Number(model.barSize) === 1);", "    void 0;"],
};

// --- the modules' own constants, SCRAPED (never written down here) ---------------------------
// The surface size, the input-rect padding and the composition shift are derived below exactly as
// the two modules derive them. They used to be literals (480x92 / 240 / "90rem"), and the moment
// the track narrowed 300rem -> 200rem (BOX_W_REM 460 -> 360) three of them went stale and this
// shim went red -- while tests/test_progress_surface_mirror.py, which scrapes the same constants,
// stayed green through the same change. Same regex and same formulas as that test's _js_const /
// _surface_wh, so the two cannot disagree, and what is asserted is the RELATIONSHIP: a resize
// moves both sides together and only a broken derivation fails.
// SCRAPED FROM THE UNMUTATED SOURCES on purpose -- no mutation touches a constant.
//
// WHICH FILE OWNS WHICH. The five BOX_*/PAD_REM values are this bar's own surface contract and
// stayed in MoEProgress.js; every TIMING, the re-assert pair, END_MARGIN_MS, HIT_MAGIC and the
// run class/name pairs moved into MoEBarTransient.js with the machinery that uses them.
const PAD = jsConst(B_SRC, "PAD_REM", "MoEProgress.js");
const BOX_W = jsConst(B_SRC, "BOX_W_REM", "MoEProgress.js");
const BOX_H = jsConst(B_SRC, "BOX_H_REM", "MoEProgress.js");
const BOX_LEFT = jsConst(B_SRC, "BOX_LEFT_REM", "MoEProgress.js");
const SURFACE = [BOX_W + 2 * PAD, BOX_H + 2 * PAD];
const HIT_PAD = Math.ceil(Math.max(SURFACE[0], SURFACE[1]) / 2);
const SHIFT = [PAD - BOX_LEFT + "rem",
               PAD - jsConst(B_SRC, "BOX_TOP_REM", "MoEProgress.js") + "rem"];
const HIT_MAGIC = jsConst(T_SRC, "HIT_MAGIC", "MoEBarTransient.js");
// THE LARGE SIZE MODE (VM `barSize` == 1). Both factors are scraped, and every large expectation is
// DERIVED here exactly as MoEBarTransient.applySize derives it -- x-lengths take BOTH factors, the
// y/uniform half only SIZE_F, and each surface arg is Math.round()ed because 4/3 is not
// representable. `ROOT_FONT_PX` is the harness's own pretend base root font, deliberately not 1.
const SIZE_F = jsFactor(T_SRC, "SIZE_F", "MoEBarTransient.js");
const SIZE_XF = jsFactor(T_SRC, "SIZE_XF", "MoEBarTransient.js");
const ROOT_FONT_PX = 2;
const LG_SURFACE = [Math.round((BOX_W * SIZE_XF + 2 * PAD) * SIZE_F),
                    Math.round((BOX_H + 2 * PAD) * SIZE_F)];
const LG_HIT_PAD = Math.ceil(Math.max(LG_SURFACE[0], LG_SURFACE[1]) / 2);
const LG_SHIFT_X = Math.round((PAD - BOX_LEFT * SIZE_XF) * 1000) / 1000 + "rem";
// The show gate's two timings, scraped for the same reason: they are TUNED numbers (the re-assert
// only has to land after the engine's observed ~2.2s clobber, the slack only after the resize's C++
// round-trip), so a retune must move this shim with them and not redden it.
const REASSERT = jsConst(T_SRC, "SURFACE_REASSERT_MS", "MoEBarTransient.js");
const SETTLE = REASSERT + jsConst(T_SRC, "SURFACE_SETTLE_MS", "MoEBarTransient.js");
// mp-life's stops, in ms into the run (0 / 9.68 / 90.32 / 100), SCRAPED for the same reason as the
// surface constants above: they are TUNED numbers owned by the tuner's timings JSON, so a retune
// must move this shim with them and not redden it. Only the three literals are scraped -- TOTAL and
// the two seeks are DERIVED here exactly as the transient derives TOTAL_MS / SEEK_PLATEAU /
// SEEK_FADE_OUT from the same trio, so a broken derivation is what fails.
const FADE_IN = jsConst(T_SRC, "FADE_IN_MS", "MoEBarTransient.js");
const HOLD = jsConst(T_SRC, "HOLD_MS", "MoEBarTransient.js");
const FADE_OUT = jsConst(T_SRC, "FADE_OUT_MS", "MoEBarTransient.js");
const TOTAL = FADE_IN + HOLD + FADE_OUT;
const SEEK_PLATEAU = FADE_IN, SEEK_FADE_OUT = FADE_IN + HOLD;
const MARGIN = jsConst(T_SRC, "END_MARGIN_MS", "MoEBarTransient.js");
const RUN_CLASSES = jsArray(T_SRC, "RUN_CLASSES", "MoEBarTransient.js");
const RUN_NAMES = jsArray(T_SRC, "RUN_NAMES", "MoEBarTransient.js");

// `unsettled` leaves the clock at mount time, i.e. BEFORE the re-assert flips the transient's
// `settled` -- the state the surface section and the show gate below examine. Every other section
// wants a bar that is allowed to show, so by default the clock is run straight past the flip.
function mount(srcs, unsettled) {
    // The transient FIRST: this bar's `const VALUE_SWAP_MS = FADE_IN_MS` and its
    // `const T = createTransient(...)` both run at load and would hit the transient's const TDZ the
    // other way round.
    const body = S.concatModules([srcs.T, srcs.B]);

    // A REALISTIC EPOCH MAGNITUDE, not a small number: the transient's `dmgPlateauAt == 0` means "no
    // damage hold in flight", which only reads as "long ago" while Date.now() > HOLD_MS. That is
    // unconditionally true in the client (epoch ms) but was only true here by 250ms of luck -- a
    // clock starting at 1000 sat BELOW HOLD_MS until the SETTLE advance, so trimming
    // SURFACE_REASSERT_MS would have reddened the peek sections for a reason the client cannot have.
    const clock = makeClock(1e12);
    const bodyEl = new El("body");
    parseHTML(VIEW_HTML.replace(/<!--[\s\S]*?-->/g, ""), bodyEl);  // the view's own static markup
    // documentElement + getComputedStyle exist ONLY for the large size mode's root-font write.
    const { documentElement, getComputedStyle } = makeRootFont(ROOT_FONT_PX);
    const document = {
        body: bodyEl,
        documentElement,
        createElement: (tag) => new El(tag),
        getElementById: (id) => bodyEl.byId(id),
    };
    const calls = { resize: [], hit: [], freeze: 0 };
    const viewEnv = {
        resizeViewRem(w, h) { calls.resize.push([w, h]); },
        setHitAreaPaddingsRem(...a) { calls.hit.push(a); },
        freezeTextureBeforeResize() { calls.freeze += 1; },
    };
    let render = null;
    const observer = {
        model: {},
        onUpdate(fn) { render = fn; },
        subscribe() { observer.subscribed = true; },
    };
    // engine.on carries WG's own `self.onScaleUpdated`, which the transient re-reads the base root
    // font from (the one thing about the size mode that is not knowable from source).
    const engineHandlers = {};
    const engine = {
        whenReady: { then: (fn) => fn() },
        on(name, fn) { engineHandlers[name] = fn; },
    };

    new Function("document", "viewEnv", "engine", "ModelObserver", "setTimeout", "clearTimeout",
                 "Date", "requestAnimationFrame", "getComputedStyle", body)(
        document, viewEnv, engine, () => observer, clock.setTimeout, clock.clearTimeout,
        { now: clock.now }, clock.raf, getComputedStyle);

    const root = document.getElementById("moe-bar-root");
    const q = (sel) => root.querySelector(sel);
    if (!unsettled) clock.advance(SETTLE);
    return {
        clock, calls, root, document, body: bodyEl, observer, documentElement,
        scaleUpdate: (v) => engineHandlers["self.onScaleUpdated"](v),
        // A real ModelObserver updates .model and THEN notifies, and the surface-settle re-render
        // reads .model back -- so pushing has to do both, or that path sees a stale/empty model.
        push: (m) => { observer.model = m; render(m); },
        animEnd: (name) => root.dispatch("animationend", { animationName: name }),
        fill: q(".mp-fill"), capC: q(".mp-capC"), capL: q(".mp-capL"), capR: q(".mp-capR"),
        capP: q(".mp-capP"), proj: q(".mp-proj"), pre: q(".mp-pre"),
        capCV: q(".mp-capC").querySelector(".mp-v"),
        capD: q(".mp-capC").querySelector(".mp-d"),
        capDN: q(".mp-capC").querySelector(".mp-d-num"),
        run: () => (root.classList.contains(RUN_CLASSES[0]) ? RUN_CLASSES[0]
                    : root.classList.contains(RUN_CLASSES[1]) ? RUN_CLASSES[1] : null),
    };
}

// A model with round axis arithmetic: lo 2450, hi 3050 -> width 600, so preAvg 2700 = 41.667% and
// projAvg 2750 = 50.000%. delta +50.
const BASE = { visible: true, hasData: true, marks: 1, axisLo: 2450, axisHi: 3050,
               preAvg: 2700, projAvg: 2750, altHeld: false };
const M = (extra) => Object.assign({}, BASE, extra);

function run(mutation) {
    const srcs = S.applyMutation({ T: T_SRC, B: B_SRC }, mutation, MUTATIONS);

    // --- the surface push, and the re-assert guard -----------------------------------------
    section("surface");
    let s = mount(srcs, true);                  // stay before the re-assert: it is what is asserted
    eq("resizeViewRem called once at mount with the surface size", s.calls.resize, [SURFACE]);
    eq("hit rect collapsed by half the larger dimension + WG's magic 5th arg",
       s.calls.hit, [[HIT_PAD, HIT_PAD, HIT_PAD, HIT_PAD, HIT_MAGIC]]);
    eq("texture frozen before the resize (WG's pattern)", s.calls.freeze, 1);
    eq("the composition is shifted into positive document coords",
       [s.root.style.left, s.root.style.top], SHIFT);
    ok("the static sizing box from the HTML is present", s.document.getElementById("moe-bar-box"));
    ok("the JS built its own root and did NOT adopt the sizing box",
       s.document.getElementById("moe-bar-box") !== s.root);
    eq("the arming classes are the pair the stylesheet's hand-added twin provides",
       [RUN_CLASSES, RUN_NAMES], [["mp-run", "mp-run-b"], ["mp-life", "mp-life-b"]]);
    s.clock.advance(REASSERT);
    eq("the size is re-asserted once after the fallback deadline",
       s.calls.resize, [SURFACE, SURFACE]);
    eq("...and the input rect with it", s.calls.hit.length, 2);

    // --- hidden until the model says otherwise ---------------------------------------------
    section("gating");
    eq("an empty model hides the bar", s.root.style.display, "none");
    s.push(M({ hasData: false }));
    eq("hasData false hides the bar", s.root.style.display, "none");

    // --- THE SHOW GATE: nothing may appear before the surface is re-asserted -----------------
    // Between view creation and the re-assert the surface is the engine's 256x256 fallback, so a bar
    // shown in that window is CROPPED (the composition spans document x 10..370) and ~142px too high
    // (Python's anchor conversion bakes in a 92-tall surface). The only way to reach it in play is an
    // Alt peek at battle start -- the damage-driven entry needs a value to have moved, and nothing
    // has yet -- so it is exactly the case a virtual clock is for.
    section("show gate");
    s = mount(srcs, true);                      // still pre-re-assert
    s.push(M());
    eq("the suppressed window still runs the silent baseline: the fill settles", s.fill.style.width,
       "50.000%");
    eq("...and the numeral commits, so the baseline is captured", s.capCV.textContent, "2,750");
    eq("...while showing nothing", s.run(), null);
    s.push(M({ projAvg: 2900 }));
    eq("a real value change before the re-assert must NOT show", s.run(), null);
    s.push(M({ projAvg: 2900, altHeld: true }));
    eq("an Alt peek before the re-assert must NOT show either", s.run(), null);
    eq("...and nothing was paused mid-nothing", s.root.style.animationPlayState, "");
    // NO further push: the settle's own render(observer.model) is the only thing that runs here.
    s.clock.advance(SETTLE);
    eq("a STILL-HELD Alt shows the instant the flag flips, with no fresh model push", s.run(),
       RUN_CLASSES[0]);
    eq("...as a peek entry already committed at proj_avg (not a pre->proj climb)",
       [s.fill.style.width, s.capCV.textContent], ["75.000%", "2,900"]);
    s.clock.advance(FADE_IN);
    eq("...and it pauses at the plateau like any other peek", s.root.style.animationPlayState,
       "paused");
    s = mount(srcs);                            // the default mount is already past the flip
    s.push(M());
    s.push(M({ altHeld: true }));
    eq("after the settle an Alt peek shows normally", s.run(), RUN_CLASSES[0]);

    // --- the first push is a SILENT baseline ------------------------------------------------
    section("first push");
    s = mount(srcs);
    s.push(M());
    eq("shown", s.root.style.display, "");
    eq("no run armed -- the bar must not appear at battle start", s.run(), null);
    eq("settled straight at projAvg", s.fill.style.width, "50.000%");
    eq("the static pre_avg tick is painted", s.pre.style.left, "41.667%");
    eq("...and its caption with it", s.capP.style.left, "41.667%");
    // setPos writes THREE lefts and only two were ever asserted. The bottom caption's is the one
    // the numeral-centring in the CSS is about (.mp-capP/.mp-capC .mp-ico cancel the icon's width
    // and .mp-cap .mp-d hangs the delta out of flow, so translateX(-50%) halves the DIGITS' box):
    // the percentage below is the tick the digits must sit on.
    eq("the moving caption rides proj_avg, like the fill and the tick", s.capC.style.left,
       "50.000%");
    eq("the bottom numeral already shows projAvg", s.capCV.textContent, "2,750");
    eq("axis-end captions carry the requirement values",
       [s.capL.querySelector(".mp-v").textContent, s.capR.querySelector(".mp-v").textContent],
       ["2,450", "3,050"]);
    eq("the mark glyphs are held / next", [s.capL.querySelector(".mp-ico").className,
                                          s.capR.querySelector(".mp-ico").className],
       ["mp-ico mk mk1", "mp-ico mk mk2"]);

    // --- COLD SHOW --------------------------------------------------------------------------
    section("cold show");
    s.push(M({ projAvg: 2900 }));
    eq("run #1 uses the original identity", s.run(), RUN_CLASSES[0]);
    eq("the entry plays from the top (no seek)", s.root.style.animationDelay, "0ms");
    eq("the numeral still reads pre_avg until the swap", s.capCV.textContent, "2,700");
    eq("the delta is faded out until the swap", s.capD.style.opacity, "0");
    // THE REWIND IDIOM (this bar's onRewind hook): a cold show snaps the fill back to pre_avg with
    // transitions off, then aims it at the target in a LATER frame (the cold-only rAF in onCommit)
    // so the transition actually runs. The baseline above rests at projAvg 2750 == 50%, NOT at
    // preAvg -- otherwise a missing rewind would be invisible.
    eq("the fill was rewound to pre_avg...", [s.fill.style.width, s.fill.style.transition],
       ["41.667%", "none"]);
    s.clock.flushFrames();
    eq("...and re-aimed at the target in the next frame, with the transition handed back",
       [s.fill.style.width, s.fill.style.transition], ["75.000%", ""]);
    s.clock.advance(FADE_IN);
    eq("at the swap the numeral commits to proj_avg", s.capCV.textContent, "2,900");
    eq("...the delta appears", [s.capD.style.opacity, s.capDN.textContent], ["1", "+200"]);
    ok("...and the sign glow lands on the fill + numerals",
       s.fill.classList.contains("mp-up") && s.capCV.classList.contains("mp-up"));
    ok("no down-glow", !s.fill.classList.contains("mp-down"));

    // --- WARM RE-TRIGGER --------------------------------------------------------------------
    section("warm re-trigger");
    s.push(M({ projAvg: 3050 }));
    eq("re-armed on the ALTERNATE identity", s.run(), RUN_CLASSES[1]);
    eq("seeked PAST the entry to the plateau -- no re-flash, no re-slide",
       s.root.style.animationDelay, "-" + SEEK_PLATEAU + "ms");
    // THE ASYMMETRY THAT MUST NOT BE FLATTENED: the warm commit sets the target SYNCHRONOUSLY (no
    // rAF), because nothing was rewound. Read with no flushFrames, so a rAF here would still show
    // the previous target.
    eq("the fill was NOT rewound, and the target is set SYNCHRONOUSLY (no rAF wait)",
       s.fill.style.width, "100.000%");
    eq("...while the numeral holds the PREVIOUS proj_avg until the swap", s.capCV.textContent,
       "2,900");
    ok("the axis-full class is set at the goalpost", s.root.classList.contains("mp-full"));
    s.clock.advance(FADE_IN);
    eq("...then commits with the swap", s.capCV.textContent, "3,050");

    // --- a STALE animationend from the superseded identity ---------------------------------
    section("stale animationend");
    s.push(M({ projAvg: 2900 }));               // a fresh warm run, so a swap is still pending
    s.animEnd(RUN_NAMES[1]);
    eq("the superseded run's animationend is ignored", s.run(), RUN_CLASSES[0]);
    eq("...and did NOT force-settle the numeral", s.capCV.textContent, "3,050");
    s.animEnd(RUN_NAMES[0]);
    eq("the LIVE run's animationend ends it", s.run(), null);
    eq("force-settled on proj_avg (the onEnd hook, before its own swap could fire)",
       s.capCV.textContent, "2,900");
    s.push(M({ projAvg: 2750 }));
    eq("a change after the run ended is a fresh COLD show", s.root.style.animationDelay, "0ms");

    // --- THE FORCE-SETTLE, on a run that ends before BOTH its swap and its rAF ----------------
    // onEnd's setPos is a SNAP, and it is invisible on any run whose commit already landed: the warm
    // path above sets the fill target synchronously, so deleting settleValues' setPos outright failed
    // NOTHING there -- this file shipped that vacuous assertion until it was probed. A COLD entry
    // whose rAF has not been flushed leaves the fill at the REWIND, so the snap is the only thing
    // that can move it. (Same trap as `unscoped-substring-assertion-is-not-an-assertion`, one layer
    // down: an assertion coincidentally satisfied by a value someone else already wrote.)
    section("force-settle");
    s = mount(srcs);
    s.push(M());                                // baseline rests at projAvg 2750 == 50%
    s.push(M({ projAvg: 2900 }));               // cold entry -- rAF deliberately NOT flushed
    eq("precondition: mid-entry the numeral still reads pre_avg", s.capCV.textContent, "2,700");
    eq("precondition: ...and the fill is still at the rewind, not the target",
       s.fill.style.width, "41.667%");
    s.animEnd(RUN_NAMES[0]);                    // ends at ~0ms, well before VALUE_SWAP_MS
    eq("endRun force-settles the numeral to proj_avg", s.capCV.textContent, "2,900");
    eq("...and SNAPS the fill there, with the transition suppressed",
       [s.fill.style.width, s.fill.style.transition], ["75.000%", "none"]);

    // --- the H2 fallback: animationend never arrives ---------------------------------------
    section("end-timer fallback");
    s = mount(srcs);
    s.push(M());
    s.push(M({ projAvg: 2900 }));
    s.clock.advance(TOTAL + MARGIN);
    eq("the run ends on the fallback timer with no animationend at all", s.run(), null);
    s.push(M({ projAvg: 2960 }));
    eq("so the NEXT change still gets a cold show (not wedged 'showing')",
       s.root.style.animationDelay, "0ms");

    // --- ALT PEEK: hold ---------------------------------------------------------------------
    section("peek hold");
    s = mount(srcs);
    s.push(M());
    s.push(M({ altHeld: true }));
    eq("the peek cold-shows the bar (full entry)", s.root.style.animationDelay, "0ms");
    eq("not paused mid-fade-in", s.root.style.animationPlayState, "");
    s.clock.advance(FADE_IN);
    eq("paused once the entry completes", s.root.style.animationPlayState, "paused");
    s.clock.advance(60000);
    eq("a held peek NEVER ends -- the fallback timer must not end it either",
       [s.root.style.animationPlayState, s.run()], ["paused", RUN_CLASSES[0]]);
    eq("still visible", s.root.style.display, "");

    // --- ALT PEEK: release ------------------------------------------------------------------
    section("peek release");
    s.push(M({ altHeld: false }));
    eq("released -> unpaused", s.root.style.animationPlayState, "");
    eq("...and seeked straight to the fade-out stop", s.root.style.animationDelay,
       "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("only the fade-out played, then the run ended", s.run(), null);

    // --- the SHORT TAP (released before the plateau) -- STRICTLY HOLD-TO-SHOW ----------------
    // peekOff used to BAIL when the plateau pause had not landed (`animationPlayState !== "paused"`),
    // which re-armed nothing: the full TOTAL-ms transient played on, so a 300ms Alt tap read as a
    // toggle-on with a 5s auto-hide. It now MIRRORS the release into the fade-out -- the un-owed part
    // of the entry (`inLeft`) is subtracted from the fade-out stop, so the run resumes at the opacity
    // it was already at and the bar is gone a fade-out after the RELEASE, not TOTAL after the press.
    section("short tap");
    const TAP = 300;                                     // < FADE_IN, so the pause never lands
    const TAP_SEEK = SEEK_FADE_OUT + (FADE_IN - TAP);     // the mirrored stop, derived independently
    s = mount(srcs);
    s.push(M());
    s.push(M({ altHeld: true }));
    s.clock.advance(TAP);                       // still mid-fade-in
    eq("precondition: the tap never reached the plateau pause",
       s.root.style.animationPlayState, "");
    s.push(M({ altHeld: false }));
    eq("the release is MIRRORED into the fade-out, not left to run out",
       s.root.style.animationDelay, "-" + TAP_SEEK + "ms");
    eq("...which means peekOff re-armed, so the identity flipped", s.run(), RUN_CLASSES[1]);
    eq("...unpaused, with the stale pause timer dropped alongside it",
       s.root.style.animationPlayState, "");
    s.clock.advance(TOTAL - TAP_SEEK);          // the shortened remainder: only the mirrored fade-out
    eq("still armed and still unpaused through that remainder",
       [s.run(), s.root.style.animationPlayState], [RUN_CLASSES[1], ""]);
    s.clock.advance(MARGIN);
    eq("and it ended on the SHORT run's own timer -- gone " + (TOTAL - TAP_SEEK + MARGIN) +
       "ms after the release, not " + (TOTAL + MARGIN) + "ms after the press", s.run(), null);

    // --- ALT PRESSED DURING THE FADE-OUT (the elapsed-not-a-flag rule) ----------------------
    // Symptom: the bar froze mid-transition at partial opacity instead of reappearing. `showing`
    // stays true all the way THROUGH the fade-out (only endRun clears it), so the phase has to come
    // from ELAPSED TIME: Date.now() vs plateauAt + HOLD_MS.
    section("alt during fade-out");
    s = mount(srcs);
    s.push(M());
    s.push(M({ projAvg: 2900 }));               // cold show
    s.clock.advance(FADE_IN + HOLD + 100);      // 5700ms in: 100ms INTO the fade-out
    eq("precondition: the run is still armed and unpaused (fading out)",
       [s.run(), s.root.style.animationPlayState], [RUN_CLASSES[0], ""]);
    s.push(M({ projAvg: 2900, altHeld: true }));
    eq("re-armed at the PLATEAU, not paused in place, and not a cold entry from opacity 0",
       s.root.style.animationDelay, "-" + SEEK_PLATEAU + "ms");
    eq("on a fresh identity", s.run(), RUN_CLASSES[1]);
    eq("unpaused by the re-arm", s.root.style.animationPlayState, "");
    s.clock.advance(0);                         // the pause callback is due immediately
    eq("pinned at full opacity", s.root.style.animationPlayState, "paused");
    s.clock.advance(60000);
    eq("and held indefinitely -- the superseded run's timer cannot end it",
       [s.root.style.animationPlayState, s.run()], ["paused", RUN_CLASSES[1]]);
    eq("the numeral is still the committed proj_avg", s.capCV.textContent, "2,900");
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("release still fades out exactly once", s.root.style.animationDelay,
       "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("...and ends", s.run(), null);

    // --- re-show after a hide ---------------------------------------------------------------
    section("hide resets");
    s.push(M({ visible: false }));
    eq("hidden", s.root.style.display, "none");
    eq("...and the animation delay cleared", s.root.style.animationDelay, "0ms");
    s.push(M({ projAvg: 3000 }));
    eq("the first push after a re-show is a silent baseline again", s.run(), null);
    s.push(M({ projAvg: 3010 }));
    // A cold entry, on a FRESH identity: the alternation deliberately continues across a reset, so
    // consecutive runs still never share a name.
    eq("...and the next change shows COLD, on a fresh identity",
       [s.run(), s.root.style.animationDelay], [RUN_CLASSES[1], "0ms"]);

    // --- ALT ACROSS A DAMAGE-DRIVEN HOLD (dmgPlateauAt) --------------------------------------
    // Players hold Alt near-constantly (extended vehicle markers), and a release used to TRUNCATE
    // whatever it had interrupted: peekOff seeked to the fade-out stop unconditionally, so an Alt tap
    // during a damage event's 5s hold cut it to ~600ms. `dmgPlateauAt` remembers the most recent
    // NON-PEEK arm's plateau so a release can RESUME that hold at its true elapsed position.
    // WHAT MATTERS IS *WHEN IT ENDS*, not that it is still armed: the resumed run must expire exactly
    // when the untouched damage run would have -- earlier is the truncation bug, later is a free hold
    // extension on every Alt tap, and both look identical to a "still showing" check. Every instant
    // below is therefore an absolute one, derived from the scraped timings, and the two scenario
    // durations are FRACTIONS of HOLD so a retune cannot silently slide the press into the fade-out
    // and leave these cases quietly exercising a different branch of peekOn.
    section("alt across a damage hold");
    const PRESS = Math.round(HOLD * 0.4);       // into the damage run: mid-hold, before the fade-out
    const HELD = Math.round(HOLD * 0.2);        // ...and released with hold still left to serve
    // Absolute-instant seek. An end-timing assertion is "at exactly THIS instant", and stepping to it
    // from a captured origin cannot drift the way a chain of relative advances does.
    const at = (st, t) => st.clock.advance(t - st.clock.now());

    // (a) REGRESSION GUARD -- a peek that interrupted NOTHING still fades out plainly. The peek's own
    // entry arms a run too, so a record that tracked EVERY arm instead of only the damage ones would
    // make a peek resume ITSELF: the release would seek to the press instead of the fade-out stop.
    // The "peek release" section above holds Alt for 60s, which is past any hold and so cannot see
    // that; hold just past the plateau instead, where a stale record would still be live.
    s = mount(srcs);
    s.push(M());
    s.push(M({ altHeld: true }));               // peek only -- no damage event anywhere in this case
    s.clock.advance(FADE_IN);
    eq("precondition: the peek reached its plateau pause", s.root.style.animationPlayState,
       "paused");
    s.clock.advance(HELD);
    s.push(M({ altHeld: false }));
    eq("a peek that interrupted no damage show still fades out plainly (inLeft == 0)",
       s.root.style.animationDelay, "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("...and is gone a fade-out after the release", s.run(), null);

    // (b) THE FIX ITSELF: Alt pressed mid-hold, released with hold still owed.
    s = mount(srcs);
    s.push(M());
    s.push(M({ projAvg: 2900 }));               // the damage-driven cold show
    const T0 = s.clock.now();
    const DMG_END = T0 + TOTAL + MARGIN;        // its own end: armRun(SEEK_NONE)'s endT, untouched
    s.clock.advance(PRESS);
    s.push(M({ projAvg: 2900, altHeld: true }));
    eq("precondition: a press mid-hold neither re-arms nor moves the run",
       [s.run(), s.root.style.animationDelay], [RUN_CLASSES[0], "0ms"]);
    s.clock.advance(0);                         // the pause is due immediately (already past FADE_IN)
    eq("precondition: pinned at the plateau", s.root.style.animationPlayState, "paused");
    s.clock.advance(HELD);
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("the release RESUMES the damage hold, seeked to its true elapsed position",
       s.root.style.animationDelay, "-" + (PRESS + HELD) + "ms");
    eq("...on a fresh identity, unpaused",
       [s.run(), s.root.style.animationPlayState], [RUN_CLASSES[1], ""]);
    at(s, T0 + PRESS + HELD + FADE_OUT + MARGIN);
    eq("a plain fade-out's worth of time after the release it is STILL up -- that truncation was the "
       + "whole bug", s.run(), RUN_CLASSES[1]);
    at(s, DMG_END - 1);
    eq("still up right up to the instant the untouched damage run would have ended", s.run(),
       RUN_CLASSES[1]);
    at(s, DMG_END);
    eq("and it ends exactly THERE: neither truncated to the release nor handed a fresh hold",
       s.run(), null);

    // (c) A DAMAGE EVENT THAT ARRIVES *DURING* A PEEK. warmShow deliberately does NOT armRun while
    // peeking (the pause has to survive), so the event gets no run clock of its own -- without the
    // record being refreshed there it would be wiped a fade-out after the release. It must instead
    // last exactly as long as the warm re-trigger it could not arm. Note the peek sits PAST its own
    // plateau before the event, so "the event's instant" and "the peek's plateau" are distinguishable.
    s = mount(srcs);
    s.push(M());
    s.push(M({ altHeld: true }));               // peek first, no damage yet
    s.clock.advance(FADE_IN);
    s.clock.advance(HELD);
    eq("precondition: paused, and past the peek's own plateau",
       s.root.style.animationPlayState, "paused");
    s.push(M({ projAvg: 2900, altHeld: true }));    // the damage event, mid-peek
    const T1 = s.clock.now();
    const WARM_END = T1 + TOTAL - SEEK_PLATEAU + MARGIN;   // what a warm re-trigger here would arm
    eq("precondition: it did NOT re-arm -- the peek's pause survives it",
       [s.run(), s.root.style.animationPlayState], [RUN_CLASSES[0], "paused"]);
    s.clock.advance(HELD);
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("the release resumes THAT event's hold, elapsed from the event and not from the peek",
       s.root.style.animationDelay, "-" + (SEEK_PLATEAU + HELD) + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("so the mid-peek event is not wiped a fade-out after the release", s.run(), RUN_CLASSES[1]);
    at(s, WARM_END - 1);
    eq("it lasts exactly as long as the warm re-trigger it could not arm", s.run(), RUN_CLASSES[1]);
    at(s, WARM_END);
    eq("...and ends there", s.run(), null);

    // (d) NO RESURRECTION. Three ways a damage hold dies -- it runs out, its animationend lands, or a
    // hide resets the widget -- and after any of them a release must take the PLAIN fade-out. The
    // record is the one piece of state that could outlive the show it describes.
    // (d1) it simply ran out before the press. Guarded by arithmetic alone (a run's endT is always
    // FADE_OUT + END_MARGIN past its own hold expiry), so this half needs no clear -- assert it
    // anyway, because it is the case a player hits constantly.
    s = mount(srcs);
    s.push(M());
    s.push(M({ projAvg: 2900 }));
    s.clock.advance(TOTAL + MARGIN);
    eq("precondition: the damage run is over", s.run(), null);
    s.push(M({ projAvg: 2900, altHeld: true }));
    s.clock.advance(FADE_IN);
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("a release after the damage hold expired takes the plain fade-out",
       s.root.style.animationDelay, "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("...and stays gone", s.run(), null);

    // (d2) A HIDE (the scoreboard, or the arena ending) mid-hold, then a re-show and a peek -- with
    // the clock advancing only through the peek's own entry, so the record is still nominally LIVE and
    // its arithmetic cannot save us. reset() clearing it is the only thing that can, which is why this
    // is asserted rather than assumed.
    s = mount(srcs);
    s.push(M());
    s.push(M({ projAvg: 2900 }));               // a damage hold in flight...
    s.clock.advance(PRESS);
    s.push(M({ visible: false }));              // ...killed by a hide, mid-hold
    eq("precondition: hidden, and the run disarmed", [s.root.style.display, s.run()],
       ["none", null]);
    s.push(M({ projAvg: 2900 }));               // re-shown -> a fresh silent baseline
    s.push(M({ projAvg: 2900, altHeld: true }));
    s.clock.advance(FADE_IN);
    eq("precondition: the peek is up and paused", s.root.style.animationPlayState, "paused");
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("the killed hold is NOT resumed across the reset -- plain fade-out",
       s.root.style.animationDelay, "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("...and gone", s.run(), null);

    // (d3) the run's animationend lands (the AUTHORITATIVE end -- the timer is only the H2 fallback),
    // so `showing` clears while the nominal hold still has wall-clock time on it. endRun has to clear
    // the record with it, or the next release resumes a show that is already off screen.
    s = mount(srcs);
    s.push(M());
    s.push(M({ projAvg: 2900 }));
    s.clock.advance(PRESS);
    s.animEnd(RUN_NAMES[0]);                    // run #1's own identity
    eq("precondition: the run ended on its animationend, mid-hold", s.run(), null);
    s.push(M({ projAvg: 2900, altHeld: true }));
    s.clock.advance(FADE_IN);
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("an ended run's hold is not resumed either -- plain fade-out",
       s.root.style.animationDelay, "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("...and gone", s.run(), null);

    // (e) is the "short tap" section above, unchanged and deliberately NOT duplicated here: a
    // sub-FADE_IN tap with no damage in flight must still take the mirrored seek
    // (SEEK_FADE_OUT + inLeft). It guards this behaviour for free -- a record that tracked the peek's
    // own arm would send that release down the resume branch and emit "-" + TAP + "ms" instead.

    // --- ROUNDED-ZERO CLASSIFICATION --------------------------------------------------------
    // The glow keys off the delta AS THE TEXT ROUNDS IT, so a sub-precision change can never
    // display "(+0)" in green. Untestable from tests/: it is a classList side effect on four DOM
    // nodes, reached only through the virtual clock's swap. Both signs, because the gate is
    // Math.round(Math.abs(d)) and NOT Math.round(d) -- the latter is -0 at d == -0.5 while the
    // text already reads "(-1)", so a naive round disagrees with the glyph at exactly one value.
    section("rounded-zero classification");
    s = mount(srcs);
    s.push(M());                                  // baseline: delta +50, commits an up-glow
    s.push(M({ projAvg: 2700.4 }));               // cold show, delta +0.4
    s.clock.advance(FADE_IN);
    eq("a +0.4 delta displays as the rounded '+0'", s.capDN.textContent, "+0");
    eq("...and glows on NOTHING -- not the numeral, the delta, the fill or the tick",
       [s.capCV, s.capDN, s.fill, s.proj].map(
           (e) => e.classList.contains("mp-up") || e.classList.contains("mp-down")),
       [false, false, false, false]);
    s.push(M({ projAvg: 2699.6 }));               // warm re-trigger, delta -0.4
    s.clock.advance(FADE_IN);
    eq("the -0.4 twin displays as '-0'", s.capDN.textContent, "-0");
    eq("...and is equally neutral (the warm path classifies the same as the cold one)",
       [s.capCV, s.capDN, s.fill, s.proj].map(
           (e) => e.classList.contains("mp-up") || e.classList.contains("mp-down")),
       [false, false, false, false]);

    // --- PREVIOUS-SIGN CARRY ------------------------------------------------------------------
    // The cold-entry window (0..VALUE_SWAP_MS) has no new sign yet, so it must keep painting the
    // LAST COMMITTED one rather than flashing neutral: a bar that was red and stays red never
    // blinks. showVal(false) therefore returns WITHOUT removing a class, and the swap is the only
    // path that ever clears. Both halves are asserted here -- the carry, and that a rounded-zero
    // commit still wipes the carried colour (or a stale red survives into a neutral state).
    section("previous-sign carry");
    s = mount(srcs);
    s.push(M());                                  // baseline: delta +50 -> up-glow committed
    ok("the baseline committed an up-glow", s.fill.classList.contains("mp-up"));
    s.push(M({ projAvg: 2900 }));                 // cold show, still positive
    s.clock.advance(TOTAL + MARGIN);
    eq("precondition: that run is over", s.run(), null);
    ok("the committed up-glow outlives the run", s.fill.classList.contains("mp-up"));
    s.push(M({ preAvg: 3000, projAvg: 3000.4 }));  // a FRESH cold show whose delta rounds to zero
    eq("precondition: a cold entry from the top", s.root.style.animationDelay, "0ms");
    eq("the PREVIOUS committed sign is still painted through the entry window",
       [s.capCV, s.capDN, s.fill, s.proj].map((e) => e.classList.contains("mp-up")),
       [true, true, true, true]);
    s.clock.advance(FADE_IN);
    eq("...and only the swap clears it, because this delta rounds to zero",
       [s.capCV, s.capDN, s.fill, s.proj].map((e) => e.classList.contains("mp-up")),
       [false, false, false, false]);

    // --- THE LARGE SIZE MODE (mod_settings.progress_bar_size, pushed as `barSize`) -----------
    // Everything the flag DOES lives in MoEBarTransient.applySize, and none of it is visible to the
    // static mirror test: the root-font write (the whole SIZE_F half -- one line that re-lays the
    // composition 1.5x), the .mp-lg body class the stylesheet's appended block hangs off, and the
    // re-derived surface / hit rect / rigid shift. Every expectation is DERIVED from the scraped
    // factors (LG_* above), never written down, so a retune of either factor moves this section
    // with the module.
    section("large size mode");
    s = mount(srcs);
    s.push(M());
    eq("at the shipped size the root font is NEVER written (not even to an empty string)",
       s.documentElement.style.fontSize, undefined);
    eq("...and the body carries no size class", s.body.classList.contains("mp-lg"), false);
    const resizes = s.calls.resize.length, hits = s.calls.hit.length;

    s.push(M({ barSize: 1 }));
    eq("barSize 1 writes the ROOT FONT as base * SIZE_F -- the whole 1.5x half of the mode",
       s.documentElement.style.fontSize, (ROOT_FONT_PX * SIZE_F) + "px");
    ok("...and puts mp-lg on the BODY, where #moe-bar-box (a sibling of our root) can see it",
       s.body.classList.contains("mp-lg"));
    eq("...and re-pushes the surface with BOTH factors on x and only SIZE_F on y",
       s.calls.resize.slice(resizes), [LG_SURFACE]);
    eq("...and re-collapses the hit rect off the new larger dimension",
       s.calls.hit.slice(hits), [[LG_HIT_PAD, LG_HIT_PAD, LG_HIT_PAD, LG_HIT_PAD, HIT_MAGIC]]);
    eq("...and re-derives the rigid shift in document rem (3dp, matching the .mp-lg block)",
       s.root.style.left, LG_SHIFT_X);
    eq("...while the vertical shift is untouched -- it is a rem the root font already scaled",
       s.root.style.top, SHIFT[1]);

    const settled = s.calls.resize.length;
    s.push(M({ barSize: 1, projAvg: 2900 }));
    eq("a second render at the same size is a NO-OP: the surface is not re-pushed every push",
       s.calls.resize.length, settled);

    s.scaleUpdate(ROOT_FONT_PX * 4);
    eq("self.onScaleUpdated takes the PUSHED scale as the new base and re-applies the factor",
       s.documentElement.style.fontSize, (ROOT_FONT_PX * 4 * SIZE_F) + "px");

    s.push(M({ barSize: 0 }));
    eq("flipping BACK clears the inline root font entirely (not a 1x px value)",
       s.documentElement.style.fontSize, "");
    eq("...drops the body class", s.body.classList.contains("mp-lg"), false);
    eq("...restores the shipped surface", s.calls.resize.slice(-1), [SURFACE]);
    eq("...and the shipped rigid shift", s.root.style.left, SHIFT[0]);
    s.scaleUpdate(ROOT_FONT_PX * 8);
    eq("...and at the shipped size a scale update leaves the root font alone",
       s.documentElement.style.fontSize, "");
    // ...and it must not even RECORD that scale: the handler's `if (!large) return;` is what keeps
    // the shipped size from touching the root font at all. Without the gate the ignored 8x above
    // would silently become the base, so the next flip to large would apply 8x * SIZE_F -- which is
    // invisible until the flip, hence this last push.
    s.push(M({ barSize: 1 }));
    eq("a scale update seen at the shipped size is not remembered as the base",
       s.documentElement.style.fontSize, (ROOT_FONT_PX * 4 * SIZE_F) + "px");
}

S.main("MoEProgress.js + MoEBarTransient.js", MUTATIONS, run);
