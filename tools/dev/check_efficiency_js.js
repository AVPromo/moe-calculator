/* check_efficiency_js.js -- headless behavioural self-check for MoEEfficiency.js (the in-battle
 * centre-screen DAMAGE EFFICIENCY bar's front-end) AND the shared MoEBarTransient.js it now drives.
 * Plain Node, zero dependencies, zero framework. Sibling of check_progress_js.js, which does the
 * same job for the Moving Average bar; the DOM shim, the virtual clock, the assertion helpers, the
 * constant scraper and the mutation applier are shared in tools/dev/lib/gf_check_shim.js.
 *
 *   node tools/dev/check_efficiency_js.js
 *   node tools/dev/check_efficiency_js.js --mutate=<key>     (anti-vacuity check, see MUTATIONS)
 *   node tools/dev/check_efficiency_js.js --probe-all        (every mutation, as a table)
 *   node tools/dev/check_efficiency_js.js --list-mutations
 *
 * WHY THIS EXISTS. The bar lives in a res_map-registered Gameface WINDOW, which pins its resources
 * at client launch: there is NO hot-reload, so every JS timing hypothesis costs a full client
 * relaunch to test. The transient is a wall-clock state machine (a 6200ms keyframe seeked with a
 * negative animation-delay, a fallback end timer, an Alt peek that pauses the animation), and that
 * is exactly the kind of logic a virtual clock can prove on the desk.
 *
 * IT ASSERTS EMITTED VALUES, not "the file parsed". Per the repo lesson
 * `bar-tuner-selfcheck-is-not-a-gate`, every check below reads a value one of the two modules
 * actually WROTE -- the viewEnv resize args, the animation-delay string, the armed run class,
 * animationPlayState, the fill's width %, the band class, the `.met` flags, the caption text -- and
 * compares it to an expected literal. The SOURCE-TEXT checks (the last section) are taken with
 * comments stripped and scoped to the owning line, per
 * `unscoped-substring-assertion-is-not-an-assertion`.
 *
 * TWO FILES, ONE SCOPE. MoEEfficiency.js is now a thin caller of MoEBarTransient.js, so the shim
 * concatenates the two (transient FIRST) and evaluates them as one `new Function` body -- see the
 * shim's concatModules. Which file a mutation belongs to is spelled out in the table below: "T" is
 * the shared transient, "B" is this bar.
 *
 * THIS FILE OWNS THE DELTA LATCH. The Python-side latch (battle_bridge's _eff_last_damage /
 * _eff_delta, pushed as EfficiencyVM.damageDelta) was DELETED and the latch now lives in
 * MoEEfficiency.js, so the pytest cases that covered those invariants were retired in favour of the
 * "delta latch" section below. Every one of them is a JS-side behaviour now; there is no other gate.
 *
 * WHAT IS AND IS NOT COVERED. This exercises module LOGIC only -- no layout, no CSS, no compositor.
 * NOTHING in this bar has been confirmed in-game. The stylesheet's own emit/hand-added-block
 * contract is guarded by check_eff_css.js.
 */
"use strict";

const S = require("./lib/gf_check_shim.js");
const { section, eq, ok, El, parseHTML, makeClock, makeRootFont, makeDocumentEvents,
        jsConst, jsArray, jsFactor } = S;

const T_SRC = S.read("MoEBarTransient.js");         // the shared transient  -> "T"
const B_SRC = S.read("MoEEfficiency.js");           // this bar              -> "B"
const VIEW_HTML = S.read("MoEEfficiencyView.html");

// Source mutations for the anti-vacuity check: each breaks ONE real behaviour, and a run with it
// applied MUST fail. Keep them tiny and surgical. [WHICH, from, to] -- WHICH is "T" or "B", and
// naming it is the point of this table: the 187 lines that moved into MoEBarTransient.js took most
// of these anchors with them.
const MUTATIONS = {
    // ===== the SHARED transient: the surface ==================================================
    "no-surface-push": ["T",
        "            if (viewEnv.resizeViewRem) viewEnv.resizeViewRem(viewW, viewH);",
        "            if (viewEnv.resizeViewRem) viewEnv.resizeViewRem(256, 256);"],
    "no-hit-collapse": ["T",
        "        if (!viewEnv.setHitAreaPaddingsRem) return;", "        return;"],
    "hit-rect-not-collapsed": ["T",
        "            viewEnv.setHitAreaPaddingsRem(hitPad, hitPad, hitPad, hitPad, HIT_MAGIC);",
        "            viewEnv.setHitAreaPaddingsRem(0, 0, 0, 0, HIT_MAGIC);"],
    // The per-axis regression: WG's own confirmed wrapper usage (gui-part3.pkg) passes FOUR EQUAL
    // values, always, and an oversized pad is accepted, not rejected -- so ONE shared value off
    // `Math.max(viewW, viewH)` is the recorded design, immune to argument order and to which
    // axis's size the pad happens to be derived from.
    "hit-pad-split-per-axis": ["T",
        "    let hitPad = Math.ceil(Math.max(viewW, viewH) / 2);",
        "    let hitPadX = Math.ceil(viewW / 2), hitPadY = Math.ceil(viewH / 2);"],
    "no-shift": ["T",
        '            root.style.left = shiftX + "rem";', '            root.style.left = "0rem";'],
    "no-texture-freeze": ["T",
        "            if (viewEnv.freezeTextureBeforeResize) viewEnv.freezeTextureBeforeResize();",
        "            void 0;"],
    // THE RE-ASSERT. The engine's 256x256 default-size fallback runs LAST and wins, so a single
    // mount-time push proves nothing. Drops ONLY the inner (second) push, leaving the `settled` flip
    // nested below it intact.
    "no-surface-reassert": ["T",
        "                pushSurfaceSize();\n                setTimeout(function () {",
        "                setTimeout(function () {"],

    // ===== the SHARED transient: the pre-settle show gate ======================================
    "no-peek-gate": ["T",
        "                if (!peeking && settled) peekOn();",
        "                if (!peeking) peekOn();"],
    "no-settle-rerender": ["T", "                    render(observer.model);", ""],

    // ===== the SHARED transient: arming, the debounce, the identity alternation ================
    "warm-replays-entry": ["T",
        "            armRun(SEEK_PLATEAU);        // the seek lands us AT the plateau",
        "            armRun(SEEK_NONE); //"],
    // The twin's whole reason: a coalesced restart on a `both`-filled opacity:0 root is the
    // "shows once, never again" bug the Moving Average bar shipped with.
    "no-identity-alternation": ["T", "        armIdx = 1 - armIdx;", "        armIdx = 0;"],
    "no-negative-delay-debounce": ["T",
        '        root.style.animationDelay = seekMs ? "-" + seekMs + "ms" : "0ms";',
        '        root.style.animationDelay = "0ms";'],
    "no-animationend-identity-guard": ["T",
        "        if (e.animationName !== runNames[armIdx]) return;\n", ""],
    // RE-HOMED when the timer grew its un-animated branch: the statement is three lines now, and the
    // old one-line anchor silently stopped applying (which probeAll reports as STALE, not caught).
    "no-end-timer": ["T",
        "        endT = setTimeout(function () { endRun(id); },\n" +
        "                          animated ? TOTAL_MS - seekMs + END_MARGIN_MS\n" +
        "                                   : Math.max(0, SEEK_FADE_OUT - seekMs));",
        "        endT = null;"],
    "reset-does-not-disarm": ["T",
        "        endedId = runId;                 // no live run left for a late animationend " +
        "to end\n        disarm();",
        "        endedId = runId;"],
    // fmt() moved with the transient; every numeral on this bar is a readout of it.
    "no-thousands-sep": ["T", '.replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",")', ""],

    // ===== the SHARED transient: the configurable hold duration (VM `holdMs`) =================
    // The fail-soft direction: an absent/non-positive push must degrade to the BAKED HOLD_MS, never
    // to "no hold at all". Anchored on BOTH bars -- see check_progress_js.js's twin.
    "hold-fail-soft-broken": ["T", "        holdMs = v > 0 ? v : HOLD_MS;", "        holdMs = v;"],
    // THIS BAR's one line: the pushed duration has to reach the transient at all.
    "hold-flag-never-pushed": ["B", "    T.hold(model.holdMs);", "    void 0;"],
    // Drop the one line that makes Alt own the hold: without it a pending correction -- including the
    // one the peek's OWN cold entry just armed, which is why this clear has to sit AFTER that branch
    // and not before it -- releases the bar mid-peek on any hold shorter than the baked one.
    "peek-does-not-own-the-hold": ["T",
        "        clearTimeout(holdT);\n        peeking = true;", "        peeking = true;"],

    // ===== the SHARED transient: the Alt peek ==================================================
    // ANCHORED ON peekT's setTimeout, not on the bare pause line: holdFrom's LONGER-hold branch
    // pauses at exactly the same indentation and is defined FIRST, and applyMutation replaces only
    // the FIRST match -- so the bare line silently re-homed this probe onto the wrong pause.
    "peek-no-pause": ["T",
        "        peekT = setTimeout(function () {\n" +
        '            root.style.animationPlayState = "paused";',
        '        peekT = setTimeout(function () {\n            root.style.animationPlayState = "";'],
    // ...and the OTHER pause: a hold LONGER than the baked one is served by parking the run at its
    // plateau, so without this the keyframe fades out at HOLD_MS and the extra time shows nothing.
    "long-hold-does-not-park-the-run": ["T",
        "            if (id !== runId) return;\n" +
        '            root.style.animationPlayState = "paused";',
        "            if (id !== runId) return;"],
    "peek-ends-while-held": ["T",
        "            clearTimeout(endT);\n        }, Math.max(0, plateauAt - Date.now()));",
        "        }, Math.max(0, plateauAt - Date.now()));"],
    "release-no-fadeout-seek": ["T", "        armRun(SEEK_FADE_OUT + inLeft);", ""],
    // THE RESUME-VS-FADE SPLIT, peekOn's half. `showing` stays true all the way THROUGH the
    // fade-out, so branching on it freezes the widget at partial opacity -- the phase has to come
    // from elapsed time. Two mutations: drop the re-arm entirely, and the tempting `showing` form.
    "no-fadeout-rearm": ["T",
        '        } else if (!peeking && root.style.animationPlayState !== "paused"\n' +
        "                   && Date.now() >= plateauAt + HOLD_MS) {",
        "        } else if (false) {"],
    "peek-phase-from-showing": ["T",
        '        } else if (!peeking && root.style.animationPlayState !== "paused"\n' +
        "                   && Date.now() >= plateauAt + HOLD_MS) {",
        "        } else if (!peeking && !showing) {"],
    // ...and peekOff's half: a release mid-damage-hold RESUMES it (players hold Alt near-constantly),
    // but a hold that already died must NOT be resurrected.
    "no-dmg-hold-resume": ["T",
        "        if (dmgPlateauAt + holdMs > Date.now()) {", "        if (false) {"],
    "endrun-keeps-dmg-plateau": ["T",
        "        dmgPlateauAt = 0;                // the hold is over",
        "        // dmgPlateauAt = 0;  // the hold is over"],
    "reset-keeps-dmg-plateau": ["T",
        "        dmgPlateauAt = 0;                // ditto endRun",
        "        // dmgPlateauAt = 0;  // ditto endRun"],
    // ===== the SHARED transient: THE TRANSITION SWITCHES (VM transEvents / transManual) ========
    // Two pushed bools, one per trigger AREA, and the LIVE RUN's copy is decided AT ARM TIME. The
    // rewind/commit halves of the change are NOT anchored here -- this bar passes neither hook, so
    // they are invisible to it and are probed in check_progress_js.js instead.
    "cold-entry-ignores-the-trigger-area": ["T",
        "        animated = fromDamage ? animEvents : animManual;",
        "        animated = animEvents;"],
    // An un-animated entry arms AT the plateau -- opacity 1 and translateY(0) both complete, so there
    // is nothing left to play. Arm at SEEK_NONE and the "instant" bar fades and slides in anyway.
    "unanimated-entry-replays-the-fade": ["T",
        "        armRun(animated ? SEEK_NONE : SEEK_PLATEAU);", "        armRun(SEEK_NONE);"],
    // ...and its end timer stops being a FALLBACK: it is the REAL end, at the end of the hold, so it
    // carries no margin and the fade-out never plays. Both directions, so neither "ends at HOLD_MS"
    // nor "still armed through the fade-out" can be a vacuous line.
    "unanimated-end-timer-still-fades-out": ["T",
        "                          animated ? TOTAL_MS - seekMs + END_MARGIN_MS\n" +
        "                                   : Math.max(0, SEEK_FADE_OUT - seekMs));",
        "                          TOTAL_MS - seekMs + END_MARGIN_MS);"],
    "animated-end-timer-loses-its-fade-out": ["T",
        "                          animated ? TOTAL_MS - seekMs + END_MARGIN_MS\n" +
        "                                   : Math.max(0, SEEK_FADE_OUT - seekMs));",
        "                          Math.max(0, SEEK_FADE_OUT - seekMs));"],
    // An Alt release on an un-animated run ENDS it outright rather than arming a fade-out.
    "unanimated-release-arms-a-fade-out": ["T",
        "        if (!animated) {\n            endRun(runId);\n            return;\n        }\n", ""],
    // FAIL-SOFT DIRECTION: an ABSENT field must degrade to ANIMATED (the shipped bar), which is why
    // both reads are `!== false` and not `!!`. Every fixture in this file that carries neither field
    // depends on it.
    "absent-flag-degrades-to-instant": ["T",
        "        animEvents = events !== false;\n        animManual = manual !== false;",
        "        animEvents = !!events;\n        animManual = !!manual;"],

    // THE SOURCE-TEXT RULE, transient half: the shared module must be as free of a damage
    // comparison as this bar is. Smuggle one in and the text scan has to see it.
    "damage-comparison-smuggled-into-the-transient": ["T",
        "        if (fromDamage) dmgPlateauAt = plateauAt;",
        "        if (fromDamage) dmgPlateauAt = plateauAt;\n        if (cfg.damage > 0) void 0;"],

    // ===== THIS BAR: the show gate, and the silent baseline that must NOT be gated =============
    "no-hit-gate": ["B",
        "if (gained && model.showEvents !== false && T.settled()) {",
        "if (gained && model.showEvents !== false) {"],
    // ...but the BASELINE must still run before the settle, or `last` is never recorded and the
    // first real hit is missed entirely.
    "baseline-gated-too": ["B",
        "    if (!model || !model.visible || !model.hasData) {",
        "    if (!model || !model.visible || !model.hasData || !T.settled()) {"],

    // ===== THIS BAR: gating / reset ============================================================
    "no-hide": ["B",
        '        root.style.display = "none";\n        T.reset();', "        T.reset();"],
    "hide-no-reset": ["B", "        T.reset();\n", ""],
    // The show trigger is the LATCH's `gained`, so "the first push shows" is now spelled as the
    // silent seed claiming a gain.
    "first-push-shows": ["B",
        "    if (first || newBattle) {\n        peak = total;",
        "    if (first || newBattle) {\n        peak = total; gained = true;"],

    // ===== THIS BAR: band / met / pulse, all off the PUSHED index ==============================
    "no-band-class": ["B",
        "BAND_CLASSES.forEach(function (c, i) { root.classList.toggle(ns(c), i === cur.band); });",
        "BAND_CLASSES.forEach(function (c) { root.classList.toggle(ns(c), true); });"],
    "met-off-by-one": ["B",
        'reqTicks[i].classList.toggle("met", i + 1 <= cur.band);',
        'reqTicks[i].classList.toggle("met", i <= cur.band);'],
    // THE RULE THIS BAR EXISTS TO KEEP IN PYTHON: `.met` may not come off a damage comparison.
    // Caught twice over -- behaviourally (a deliberately inconsistent model) and in the source text.
    "met-from-damage": ["B",
        'reqTicks[i].classList.toggle("met", i + 1 <= cur.band);',
        'reqTicks[i].classList.toggle("met", cur.damage >= cur.r[i]);'],
    "no-pulse-gate": ["B",
        'root.classList.toggle(ns("mp-pulse"), cur.band === 4);',
        'root.classList.toggle(ns("mp-pulse"), false);'],
    // ...and neither may barX be re-derived here: the axis arithmetic is domain/battle_builder's.
    "barx-recomputed": ["B",
        "        barX: Number(model.barX) || 0,",
        "        barX: Number(model.damage) / Number(model.r100) * 100 || 0,"],
    // setPos moves three things off the ONE pushed barX; each had an assertion and no probe.
    "no-fill-width": ["B", "    fill.style[GROW] = p;", "    void 0;"],
    "no-cur-tick-move": ["B", "    tCur.style[AX] = p;", "    void 0;"],

    // ===== THIS BAR: THE DELTA LATCH (moved out of Python this pass) ===========================
    // `peak` is the battle's HIGH-WATER mark, not the previous push: combined damage SUBTRACTS team
    // damage, so the total can move DOWN. Off the previous push a dip yields a NEGATIVE delta and
    // the following hit measures from the dip instead of the peak.
    "latch-off-the-previous-push-not-the-peak": ["B",
        "    } else if (total > peak) {", "    } else {"],
    // The increment must PERSIST until superseded: a tick that moved nothing (a spot, an arena
    // period change) still has to show the number the player is reading.
    "latch-does-not-persist": ["B",
        "    const total = cur.damage;\n",
        "    const total = cur.damage;\n    delta = 0;\n"],
    // THE SHOW/FLASH TRIGGER IS `gained`, and ONLY a new high-water mark may set it. Widening the
    // branch to "the value changed at all" IS the deleted `hit` gate restored: a team-damage dip then
    // pops the bar open and re-flashes an increment the player has already read.
    "dip-pops-the-bar": ["B",
        "    } else if (total > peak) {", "    } else if (total !== peak) {"],
    // A NEW BATTLE (a different pushed battleEpoch) must DROP the stale increment -- that is what
    // Python's _on_mount_refresh used to do, and the epoch is the signal that replaced the
    // "the total restarted below the mark" inference.
    "battle-epoch-keeps-a-dead-battles-increment": ["B",
        "    if (newBattle) delta = 0;", "    void 0;"],
    // THE DELETED INFERENCE, restored as a guard on the epoch reset. `total < peak` agrees with the
    // epoch on every boundary EXCEPT the one that matters -- a new battle whose FIRST tick already
    // reads higher than the last battle's peak -- so only the positive case below catches this.
    "epoch-reset-only-when-the-total-dropped": ["B",
        "    if (newBattle) delta = 0;", "    if (newBattle && total < peak) delta = 0;"],
    // ...and the counter must ADVANCE, or every push reads as a boundary and no increment survives.
    "epoch-never-advances": ["B", "    epoch = cur.battleEpoch;", "    void 0;"],
    // `epoch` is module state ON PURPOSE and deliberately NOT part of `last`: the hide branch drops
    // that baseline mid-battle, and an epoch that died with it would read the re-show as a new battle
    // and bin the increment. This is what "moving it into `last`" costs.
    "epoch-stored-in-last": ["B",
        "    const newBattle = cur.battleEpoch !== epoch;",
        "    if (first) epoch = 0;\n    const newBattle = cur.battleEpoch !== epoch;"],
    // ...and the boundary/re-show must RE-SEED the mark, or the first hit measures against the
    // previous battle's peak (or a stale mid-battle one) and reports nothing at all.
    "first-push-does-not-reseed-the-mark": ["B",
        "    if (first || newBattle) {\n        peak = total;", "    if (false) {\n        peak = total;"],
    // The VM no longer carries damageDelta at all: reading one back is dead code that would mask
    // the latch on the next Python change.
    "delta-read-back-off-the-model": ["B",
        "        damage: Number(model.damage) || 0,",
        "        damage: Number(model.damage) || 0,\n" +
        "        damageDelta: Number(model.damageDelta) || 0,"],

    // ===== THIS BAR: the delta's display window ================================================
    "no-delta-on-hit": ["B", "        showDelta();\n        T.show();", "        T.show();"],
    "no-delta-window": ["B",
        'deltaT = setTimeout(function () { capD.classList.remove("on"); }, DELTA_HOLD_MS);',
        "deltaT = null;"],
    // ...shown on a HIT only: an Alt peek shows the latched numerals, never re-flashes an increment
    // that already had its moment.
    "delta-flashes-on-peek": ["B",
        "    T.peek(!!model.altHeld);",
        "    if (model.altHeld) showDelta();\n    T.peek(!!model.altHeld);"],

    // ===== THIS BAR: the caption's clamp corridor =============================================
    "no-clamp": ["B", "    if (lo <= hi) x = Math.max(lo, Math.min(hi, x));", ""],
    "clamp-degenerate-clamps": ["B",
        "    if (lo <= hi) x = Math.max(lo, Math.min(hi, x));",
        "    x = Math.max(lo, Math.min(hi, x));"],
    // The `* xf` on each rem literal is the LARGE size mode (MoEBarTransient's SIZE_XF): every
    // constant in the corridor is an x-length, and at the shipped size xf == 1, so these anchors are
    // the same behaviour they always guarded.
    "clamp-left-bound": ["B",
        "    const lo = CLAMP_L_REM * xf + half;", "    const lo = 0 + half;"],
    "clamp-right-bound": ["B",
        "    const hi = CLAMP_R_REM * xf - half;", "    const hi = BAR_W_REM - half;"],
    "no-ico-gap": ["B",
                 'Math.max(w(".mp-ico") + ICO_GAP_REM * xf, w(".mp-d"));',
                 'Math.max(w(".mp-ico"), w(".mp-d"));'],

    // ===== THE LARGE SIZE MODE (VM `barSize` == 1) ===========================================
    // The shared halves are anchored identically in check_progress_js.js; this bar adds the ONE
    // place on either bar that mixes a MEASURED px width with rem literals, so it needs the px<->rem
    // division too.
    "size-no-root-font": ["T",
        'document.documentElement.style.fontSize = large ? (baseFont * SIZE_F) + "px" : "";',
        "void 0;"],
    "size-root-font-ignores-the-base": ["T",
        '(baseFont * SIZE_F) + "px"', 'SIZE_F + "px"'],
    "size-no-body-class": ["T", 'document.body.classList.toggle("mp-lg", large);', "void 0;"],
    "size-surface-loses-the-x-factor": ["T",
        "viewW = Math.round((cfg.boxW * xf + cfg.padX + (large ? cfg.padXRLarge : cfg.padXR)) * f);",
        "viewW = Math.round((cfg.boxW + cfg.padX + (large ? cfg.padXRLarge : cfg.padXR)) * f);"],
    // THE 4/3 REPRESENTABILITY TRAP, on the bar that actually hits it: (460*4/3 + 20)*1.5 evaluates
    // to 949.9999999999999, so a floor hands the engine a 1px-narrow surface.
    "size-surface-floored-not-rounded": ["T",
        "viewW = Math.round((cfg.boxW * xf + cfg.padX + (large ? cfg.padXRLarge : cfg.padXR)) * f);",
        "viewW = Math.floor((cfg.boxW * xf + cfg.padX + (large ? cfg.padXRLarge : cfg.padXR)) * f);"],
    "size-shift-not-re-derived": ["T",
        "shiftX = Math.round((cfg.padX - cfg.boxLeft * xf) * 1000) / 1000;", "void 0;"],
    "size-no-surface-repush": ["T",
        '        root.style.left = shiftX + "rem";\n        pushSurfaceSize();\n    }',
        '        root.style.left = shiftX + "rem";\n    }'],
    "size-not-idempotent": ["T", "        if (flag === large) return;", "        if (false) return;"],
    "size-ignores-a-scale-update": ["T",
        "                    baseFont = parseFloat(scale) || baseFont || 1;", "                    void 0;"],
    "size-scale-update-not-gated": ["T",
        "                    if (!large) return;", "                    if (false) return;"],
    // THIS BAR's two lines: the flag has to reach the transient, and capClampPct's own mirror of it
    // has to be kept in sync (the clamp is the one thing the transient does NOT own).
    "size-flag-never-pushed": ["B", "    T.size(large);", "    void 0;"],
    // ...and, on the same footing, the two TRANSITION flags have to reach the transient at all.
    "trans-flags-never-pushed": ["B",
        "    T.anim(model.transEvents, model.transManual);", "    void 0;"],
    "size-flag-not-mirrored-for-the-clamp": ["B",
        "    large = Number(model.barSize) === 1;", "    large = false;"],
    // ...and the px<->rem division on every MEASURED width: under the 1.5x root font 1rem is
    // SIZE_F px, while the caption's width IN REM is unchanged (its font-size is a rem too), so the
    // corridor scales by SIZE_XF and the caption inside it does not. Two halves -- the querySelector
    // helper's measurement and .mp-cap's own offsetWidth -- because either alone mis-centres.
    "clamp-measured-icon-not-normalised": ["B",
        "        return ((n && n.offsetWidth) || 0) / px;", "        return (n && n.offsetWidth) || 0;"],
    "clamp-measured-numeral-not-normalised": ["B",
        "    const half = (capC.offsetWidth || 0) / 2 / px +",
        "    const half = (capC.offsetWidth || 0) / 2 +"],
    // The axis the clamped x is expressed against must take the x factor too, or the returned
    // PERCENTAGE is off by 4/3.
    "clamp-axis-not-scaled": ["B",
        "    let x = p / 100 * BAR_W_REM * xf;", "    let x = p / 100 * BAR_W_REM;"],
    "clamp-return-axis-not-scaled": ["B",
        "    return x / (BAR_W_REM * xf) * 100;", "    return x / BAR_W_REM * 100;"],
    // THE INTERFACE-SCALE GATE (.mp-s1). Three ways to lose it, each of which SHIPS SILENTLY: a
    // missing class renders as the bug and an extra one moves the render the maintainer approved.
    // (1) latched to the Default branch, which is how the shipped build made the correction a
    // function of how Large was reached; (2) the trust gate dropped, so an unsized view's 0 reads as
    // "scale 1" and the correction lands at scale 2 as well; (3) not re-evaluated on a size flip,
    // where an engine-pushed scale (self.onScaleUpdated, large-only) reaches it for the first time.
    "quant-gate-latched-to-the-default-path": ["T",
        "                if (large) setRootFont();\n                setQuantClass();",
        "                if (large) setRootFont(); else setQuantClass();"],
    "quant-gate-trusts-an-untrusted-read": ["T",
        'document.body.classList.toggle("mp-s1", px > 0 && px < 1.5);',
        'document.body.classList.toggle("mp-s1", px < 1.5);'],
    "quant-gate-not-re-evaluated-on-a-size-flip": ["T", "\n        setQuantClass();", ""],

    // ===== CTRL HOLDS THE BAR UP (VM `ctrlHeld`) ==============================================
    // See check_progress_js.js's own twin block (this bar drives the SAME shared transient). The five
    // drag mutations that used to live here are DELETED with the code they probed: the reposition
    // gesture is Python's now (adapter/battle_input + bridge/bar_window), so this document has no
    // mousedown/mousemove/mouseup listener and no `setPosition` report. Their Python-side
    // replacements are in tests/test_battle_input.py and tests/test_bar_window.py.
    //
    // THE FAIL-SOFT DIRECTION: `=== true` (not `!== false`) is deliberately the OPPOSITE of
    // applyAnim/applyHold -- the shipped bar is NOT pinned up, so an absent/undefined ctrlHeld must
    // read as NOT held. `!== false` peeks forever.
    "ctrl-absent-reads-as-held": ["T",
        "        ctrlHeld = held === true;", "        ctrlHeld = held !== false;"],
    "ctrl-flag-never-pushed": ["B", "    T.ctrl(model.ctrlHeld);", "    void 0;"],
};

// --- the modules' own constants, SCRAPED (never written down here) ---------------------------
// The surface size, the input-rect padding, the composition shift, every timing and the clamp
// corridor are all derived below exactly as the two modules derive them, so a retune moves this
// shim with them instead of reddening it (the same jsConst idiom as check_progress_js.js and
// tests/test_progress_surface_mirror.py). SCRAPED FROM THE UNMUTATED SOURCES on purpose -- no
// mutation touches a constant.
//
// WHICH FILE OWNS WHICH. The five BOX_*/PAD_REM values, DELTA_HOLD_MS, the clamp corridor and the
// band classes are this bar's own contract and stayed in MoEEfficiency.js; every TIMING, the
// re-assert pair, END_MARGIN_MS, HIT_MAGIC and the run class/name pairs moved into
// MoEBarTransient.js with the machinery that uses them.
const PAD = jsConst(B_SRC, "PAD_REM", "MoEEfficiency.js");
const BOX_W = jsConst(B_SRC, "BOX_W_REM", "MoEEfficiency.js");
const BOX_H = jsConst(B_SRC, "BOX_H_REM", "MoEEfficiency.js");
const BOX_LEFT = jsConst(B_SRC, "BOX_LEFT_REM", "MoEEfficiency.js");
const SURFACE = [BOX_W + 2 * PAD, BOX_H + 2 * PAD];
// ONE SHARED VALUE (see MoEBarTransient.js's header note): half the LARGER of the two surface
// dimensions, on all four sides -- WG's own confirmed usage (four equal args, an oversized pad
// accepted not rejected), not a per-axis pair.
const HIT_PAD = Math.ceil(Math.max(SURFACE[0], SURFACE[1]) / 2);
const SHIFT = [PAD - BOX_LEFT + "rem",
               PAD - jsConst(B_SRC, "BOX_TOP_REM", "MoEEfficiency.js") + "rem"];
const HIT_MAGIC = jsConst(T_SRC, "HIT_MAGIC", "MoEBarTransient.js");
// THE LARGE SIZE MODE (VM `barSize` == 1). Both factors are scraped, and every large expectation is
// DERIVED here exactly as MoEBarTransient.applySize derives it -- x-lengths take BOTH factors, the
// y/uniform half only SIZE_F, and each surface arg is Math.round()ed because 4/3 is not
// representable (on THIS bar the x term really does land on 949.9999999999999). `ROOT_FONT_PX` is
// the harness's own pretend base root font, deliberately not 1 so `base * SIZE_F` cannot be
// satisfied by writing the bare factor.
const SIZE_F = jsFactor(T_SRC, "SIZE_F", "MoEBarTransient.js");
const SIZE_XF = jsFactor(T_SRC, "SIZE_XF", "MoEBarTransient.js");
const ROOT_FONT_PX = 2;
// The UA default root font -- what getComputedStyle reports BEFORE the engine has written its own,
// i.e. for the first frames of every mount. Not scraped: it is a browser constant, and deliberately
// different from ROOT_FONT_PX so the two are distinguishable in an assertion.
const UA_FONT_PX = 16;
const LG_SURFACE = [Math.round((BOX_W * SIZE_XF + 2 * PAD) * SIZE_F),
                    Math.round((BOX_H + 2 * PAD) * SIZE_F)];
const LG_HIT_PAD = Math.ceil(Math.max(LG_SURFACE[0], LG_SURFACE[1]) / 2);
const LG_SHIFT_X = Math.round((PAD - BOX_LEFT * SIZE_XF) * 1000) / 1000 + "rem";
const REASSERT = jsConst(T_SRC, "SURFACE_REASSERT_MS", "MoEBarTransient.js");
const SETTLE = REASSERT + jsConst(T_SRC, "SURFACE_SETTLE_MS", "MoEBarTransient.js");
// mp-life's shape. Only the three tuned stops are scraped -- TOTAL and the two seeks are DERIVED
// here exactly as the transient derives TOTAL_MS / SEEK_PLATEAU / SEEK_FADE_OUT, so a broken
// derivation is what fails.
const FADE_IN = jsConst(T_SRC, "FADE_IN_MS", "MoEBarTransient.js");
const HOLD = jsConst(T_SRC, "HOLD_MS", "MoEBarTransient.js");
const FADE_OUT = jsConst(T_SRC, "FADE_OUT_MS", "MoEBarTransient.js");
const TOTAL = FADE_IN + HOLD + FADE_OUT;
const SEEK_PLATEAU = FADE_IN, SEEK_FADE_OUT = FADE_IN + HOLD;
const MARGIN = jsConst(T_SRC, "END_MARGIN_MS", "MoEBarTransient.js");
const RUN_CLASSES = jsArray(T_SRC, "RUN_CLASSES", "MoEBarTransient.js");
const RUN_NAMES = jsArray(T_SRC, "RUN_NAMES", "MoEBarTransient.js");
// This bar's own: the delta window, the axis / clamp contract (mirrored from the stylesheet's `meta`
// block, whose CSS side check_eff_css.js guards) and the band classes.
const DELTA_HOLD = jsConst(B_SRC, "DELTA_HOLD_MS", "MoEEfficiency.js");
const BAR_W = jsConst(B_SRC, "BAR_W_REM", "MoEEfficiency.js");
const CLAMP_L = jsConst(B_SRC, "CLAMP_L_REM", "MoEEfficiency.js");
const CLAMP_R = jsConst(B_SRC, "CLAMP_R_REM", "MoEEfficiency.js");
const ICO_GAP = jsConst(B_SRC, "ICO_GAP_REM", "MoEEfficiency.js");
const BANDS = jsArray(B_SRC, "BAND_CLASSES", "MoEEfficiency.js");

// `unsettled` leaves the clock at mount time, i.e. BEFORE the re-assert flips the transient's
// `settled` -- the state the surface section and the show gate below examine. Every other section
// wants a bar that is allowed to show, so by default the clock is run straight past the flip.
// `unsized` additionally starts the VIEW at 0x0 reporting the UA-default root font, i.e. the state a
// mount is really in before the engine has sized the view and written its own -- the state the
// caption-anchor section below replays, since that write shares the same trust gate.
function mount(srcs, unsettled, unsized) {
    // The transient FIRST: this bar's top-level `const T = createTransient(...)` runs at load and
    // would hit the transient's const TDZ the other way round.
    const src = S.concatModules([srcs.T, srcs.B]);

    // A REALISTIC EPOCH MAGNITUDE, not a small number: the transient's `dmgPlateauAt == 0` means "no
    // damage hold in flight", which only reads as "long ago" while Date.now() > HOLD_MS. That is
    // unconditionally true in the client (epoch ms); a clock starting near 0 would send every plain
    // peek release down the resume branch for a reason the client cannot have.
    const clock = makeClock(1e12);
    const body = new El("body");
    parseHTML(VIEW_HTML.replace(/<!--[\s\S]*?-->/g, ""), body);   // the view's own static markup
    // documentElement + getComputedStyle exist ONLY for the large size mode's root-font write, and
    // `win` with them: setRootFont only trusts the computed base once the view has a size. The
    // regression that gate exists for is asserted in check_progress_js.js's own large-size section.
    const { documentElement, getComputedStyle, font, win } =
        makeRootFont(unsized ? UA_FONT_PX : ROOT_FONT_PX, unsized);
    const document = Object.assign({
        body,
        documentElement,
        createElement: (tag) => new El(tag),
        getElementById: (id) => body.byId(id),
    }, makeDocumentEvents());
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

    // requestAnimationFrame is injected for parity with the progress harness even though neither
    // this bar nor the transient ever calls it (the cold-only rAF is MoEProgress.js's alone -- see
    // its commitClimb). An unused global costs nothing and keeps the two mounts comparable.
    new Function("document", "viewEnv", "engine", "ModelObserver", "setTimeout", "clearTimeout",
                 "Date", "requestAnimationFrame", "getComputedStyle", "window", src)(
        document, viewEnv, engine, () => observer, clock.setTimeout, clock.clearTimeout,
        { now: clock.now }, clock.raf, getComputedStyle, win);

    const root = document.getElementById("moe-bar-root");
    const q = (sel) => root.querySelector(sel);
    const capC = q(".mp-cap.up");
    if (!unsettled) clock.advance(SETTLE);
    return {
        clock, calls, root, document, body, observer, documentElement, font, win,
        scaleUpdate: (v) => engineHandlers["self.onScaleUpdated"](v),
        // A real ModelObserver updates .model and THEN notifies, and the surface-settle re-render
        // reads .model back -- so pushing has to do both, or that path sees a stale/empty model.
        push: (m) => { observer.model = m; render(m); },
        animEnd: (name) => root.dispatch("animationend", { animationName: name }),
        fill: q(".mp-fill"), tCur: q(".mp-tick.mp-cur"), capC,
        capCV: capC.querySelector(".mp-v"),
        capD: capC.querySelector(".mp-d"),
        capDN: capC.querySelector(".mp-d-num"),
        capIco: capC.querySelector(".mp-ico"),
        reqTick: (i) => q(".mp-tick.r" + i),
        reqCapV: (i) => q(".mp-cap.r" + i).querySelector(".mp-v"),
        // Which band class is on the root -- ALL of them, so "exactly one" is assertable.
        bands: () => BANDS.filter((c) => root.classList.contains(c)),
        met: () => [1, 2, 3, 4].map((i) => q(".mp-tick.r" + i).classList.contains("met")),
        deltaOn: () => capC.querySelector(".mp-d").classList.contains("on"),
        run: () => (root.classList.contains(RUN_CLASSES[0]) ? RUN_CLASSES[0]
                    : root.classList.contains(RUN_CLASSES[1]) ? RUN_CLASSES[1] : null),
    };
}

// The pushed model. barX / band are FINISHED VALUES from domain/battle_builder -- deliberately not
// consistent with any arithmetic over damage and the r* stops, which is what makes the "consumed
// verbatim" section below able to tell the difference. NOTE there is deliberately no `damageDelta`:
// the VM stopped carrying one when the latch moved into the JS. `battleEpoch` is 1 because Python's
// counter is bumped on the FIRST battle mount (0 is its pre-battle value); a second battle is 2.
const BASE = { visible: true, hasData: true, damage: 1500, barX: 37.5, band: 1,
               r65: 1000, r85: 2000, r95: 3000, r100: 4000, altHeld: false, battleEpoch: 1 };
const M = (extra) => Object.assign({}, BASE, extra);

function run(mutation) {
    const srcs = S.applyMutation({ T: T_SRC, B: B_SRC }, mutation, MUTATIONS);

    // --- the surface push, and THE RE-ASSERT ------------------------------------------------
    // The engine's "default view size" fallback (a flat 256x256) runs AFTER the mount-time push and
    // wins, so the mount push alone proves nothing -- the post-deadline re-assert is the load-bearing
    // half. Both are asserted, and the count is what separates them.
    section("surface");
    let s = mount(srcs, true);                  // stay before the re-assert: it is what is asserted
    eq("resizeViewRem called once at mount with the surface size", s.calls.resize, [SURFACE]);
    eq("hit rect collapsed per axis (top/bottom = half height, left/right = half width) + WG's "
       + "magic 5th arg",
       s.calls.hit, [[HIT_PAD, HIT_PAD, HIT_PAD, HIT_PAD, HIT_MAGIC]]);
    eq("texture frozen before the resize (WG's pattern)", s.calls.freeze, 1);
    eq("the composition is shifted into positive document coords",
       [s.root.style.left, s.root.style.top], SHIFT);
    ok("the static sizing box from the HTML is present", s.document.getElementById("moe-bar-box"));
    ok("the JS built its own root and did NOT adopt the sizing box",
       s.document.getElementById("moe-bar-box") !== s.root);
    s.clock.advance(REASSERT);
    eq("THE RE-ASSERT: the size is pushed again after the fallback deadline",
       s.calls.resize, [SURFACE, SURFACE]);
    eq("...and the input rect with it", s.calls.hit.length, 2);
    eq("the arming classes are the pair the stylesheet's hand-added twin provides",
       [RUN_CLASSES, RUN_NAMES], [["mp-run", "mp-run-b"], ["mp-life", "mp-life-b"]]);

    // --- hidden until the model says otherwise ---------------------------------------------
    section("gating");
    eq("an empty model hides the bar", s.root.style.display, "none");
    s.push(M({ hasData: false }));
    eq("hasData false hides the bar", s.root.style.display, "none");
    s.push(M({ visible: false }));
    eq("visible false hides the bar", s.root.style.display, "none");

    // --- THE SILENT BASELINE, and the PRE-SETTLE SUPPRESSION ---------------------------------
    // Before the re-assert the surface is the engine's 256x256 fallback: the composition spans
    // document x 10..470, so the bar would be CROPPED, and Python's anchor conversion bakes in a
    // 116-tall surface, so it would also sit far too high. Nothing may SHOW in that window -- but the
    // baseline MUST still run, or `last` is never recorded and the first real hit is missed.
    section("silent baseline + pre-settle suppression");
    s = mount(srcs, true);                      // still pre-re-assert
    s.push(M());
    eq("shown", s.root.style.display, "");
    eq("the suppressed window still runs the silent baseline: the fill settles",
       s.fill.style.width, "37.500%");
    eq("...the numeral commits, so the baseline is captured", s.capCV.textContent, "1,500");
    eq("...while showing nothing", s.run(), null);
    s.push(M({ damage: 1900, barX: 45 }));
    eq("a real damage change before the re-assert must NOT show", s.run(), null);
    eq("...and must not flash the delta either", s.deltaOn(), false);
    eq("...though the values still repaint", s.fill.style.width, "45.000%");
    s.push(M({ damage: 1900, barX: 45, altHeld: true }));
    eq("an Alt peek before the re-assert must NOT show either", s.run(), null);
    eq("...and nothing was paused mid-nothing", s.root.style.animationPlayState, "");
    // NO further push: the settle's own render(observer.model) is the only thing that runs here.
    s.clock.advance(SETTLE);
    eq("a STILL-HELD Alt shows the instant the flag flips, with no fresh model push", s.run(),
       RUN_CLASSES[0]);
    s.clock.advance(FADE_IN);
    eq("...and it pauses at the plateau like any other peek", s.root.style.animationPlayState,
       "paused");

    // --- the first push is a SILENT baseline -----------------------------------------------
    section("first push");
    s = mount(srcs);                            // the default mount is already past the flip
    s.push(M());
    eq("no run armed -- the bar must not appear at battle start", s.run(), null);
    eq("settled straight at the pushed barX", s.fill.style.width, "37.500%");
    eq("...the moving tick with it", s.tCur.style.left, "37.500%");
    eq("the current numeral shows the combined damage, thousands-separated",
       s.capCV.textContent, "1,500");
    eq("the four requirement numerals are painted",
       [1, 2, 3, 4].map((i) => s.reqCapV(i).textContent), ["1,000", "2,000", "3,000", "4,000"]);
    eq("no delta showing", s.deltaOn(), false);
    // A push that moves ONLY barX/band (a late-arriving threshold table) must repaint SILENTLY.
    s.push(M({ barX: 60, band: 2 }));
    eq("a barX/band change with no damage change repaints without showing",
       [s.fill.style.width, s.run()], ["60.000%", null]);

    // --- band -> exactly ONE class; .met and the pulse off the SAME pushed index ---------------
    section("band / met / pulse");
    for (let b = 0; b <= 4; b++) {
        s.push(M({ band: b }));
        eq("band " + b + " puts exactly one band class on the root", s.bands(), [BANDS[b]]);
        eq("band " + b + " -> .met on tick i iff i <= band", s.met(),
           [1, 2, 3, 4].map((i) => i <= b));
        eq("band " + b + " -> mp-pulse iff band is the top one",
           s.root.classList.contains("mp-pulse"), b === 4);
    }

    // --- THE DELTA LATCH --------------------------------------------------------------------
    // IT LIVES HERE NOW. battle_bridge's _eff_last_damage / _eff_delta and EfficiencyVM.damageDelta
    // were deleted, so the invariants the retired pytest cases covered are asserted below and
    // NOWHERE ELSE. `peak` is the battle's HIGH-WATER mark, deliberately NOT the previous push:
    // combined damage SUBTRACTS team damage, so the total can move DOWN, and a friendly-fire dip
    // followed by a hit must report the gain over the OLD peak -- never a negative, and never the
    // dip plus the hit. `delta` then PERSISTS until superseded, because a tick that moved nothing
    // (a spot, an arena period change, an Alt press) must keep showing the number being read.
    section("delta latch");
    s = mount(srcs);
    const dn = () => s.capDN.textContent;
    const P = (damage, extra) => s.push(M(Object.assign({ damage: damage }, extra || {})));

    P(0);
    eq("the delta is 0 BEFORE ANY DAMAGE LANDS", dn(), "0");
    eq("...and nothing flashed", s.deltaOn(), false);
    P(500);
    eq("THE FIRST INCREMENT of a battle is the whole damage", dn(), "+500");
    ok("...and it flashes", s.deltaOn());
    P(800);
    eq("a rise latches ONLY THE INCREMENT", dn(), "+300");
    P(800);
    eq("A FLAT PUSH keeps showing the previous increment", dn(), "+300");
    P(800);
    eq("...however many flat pushes arrive", dn(), "+300");
    P(600);
    eq("A DECREASE never yields a negative delta -- the latched increment stands", dn(), "+300");
    P(900);
    eq("...and the next rise measures from the PEAK, not from the dip", dn(), "+100");

    // A hasData GAP drops the change-detect baseline (`last = null`) but must NOT drop the latch:
    // the total has not restarted, so the mark and the increment both survive the re-show, exactly
    // as the Python latch survived a hide.
    P(900, { hasData: false });
    P(950);                                     // the re-show: a fresh mid-battle tick
    eq("the re-show really did repaint (so the delta below is a written value, not a stale one)",
       s.capCV.textContent, "950");
    eq("THE LATCH SURVIVES A hasData GAP -- the re-seed keeps the increment", dn(), "+100");
    P(1000);
    eq("...and the next rise measures from the RE-SEEDED mark, not from 0", dn(), "+50");

    // A BATTLE BOUNDARY: a fresh pushed `battleEpoch` (bridge/battle_bridge._battle_epoch, bumped on
    // each battle mount), so the previous battle's increment must go. This is an EXPLICIT signal, not
    // the "the total restarted below the mark" inference it replaced -- that was false whenever the
    // new battle's first tick already read higher than the old peak, and an Alt peek then rendered
    // the dead battle's number.
    P(1000, { visible: false });
    P(0, { battleEpoch: 2 });
    eq("A BATTLE BOUNDARY (a fresh pushed battleEpoch) RESETS the latch", dn(), "0");
    P(450, { battleEpoch: 2 });
    eq("...and the first hit of the new battle is the whole total again", dn(), "+450");

    // ...AND THE BOUNDARY IS THE EPOCH, POSITIVELY: battle N+1's first tick can read HIGHER than
    // battle N's peak (a fast opening hit, a bigger tank), which is EXACTLY where the deleted
    // "the total restarted below the mark" inference was wrong -- it kept the dead battle's increment
    // in the one case a player would notice. The reset must not depend on the total having dropped.
    P(600, { battleEpoch: 3 });
    eq("A BOUNDARY WHOSE FIRST TOTAL IS HIGHER than the last battle's peak still resets", dn(), "0");
    P(650, { battleEpoch: 3 });
    eq("...and the mark was re-seeded at THAT total, not left at the old peak", dn(), "+50");

    // THE ONE INTENDED BEHAVIOUR CHANGE from the Python latch. A first push that ALREADY carries
    // damage SEEDS the mark with it, so nothing is claimed for damage dealt before this document was
    // watching. `mount -> 800 -> 600` showed "+800" under the Python latch (whose previous-damage
    // started at 0, so the dip was measured against nothing) and shows "0" now. Pinned deliberately.
    s = mount(srcs);
    s.push(M({ damage: 800 }));
    eq("a first push that already carries damage claims NOTHING", dn(), "0");
    s.push(M({ damage: 600 }));
    eq("...and a dip below that seed still claims nothing (the Python latch showed '+800' here)",
       dn(), "0");
    s.push(M({ damage: 900 }));
    eq("...only a rise above the seeded mark claims anything", dn(), "+100");

    // --- AN ALT PEEK RIGHT AFTER A BATTLE BOUNDARY -------------------------------------------
    // THE USER-VISIBLE SYMPTOM the epoch fixed, and the one path that RENDERS a stale increment
    // rather than merely holding one: a peek shows the LATCHED numerals without re-flashing, so
    // before the epoch the player pressed Alt early in a new battle and read the previous battle's
    // number as this battle's. The clock is run past the whole of battle 1's run first, so the peek
    // is the only thing that can be showing the bar here.
    section("alt peek after a battle boundary");
    s = mount(srcs);
    P(0);
    P(500);                                     // battle 1 lands a hit: +500, latched and flashed
    eq("precondition: battle 1's increment is up and flashing", [dn(), s.deltaOn()], ["+500", true]);
    s.clock.advance(TOTAL + MARGIN);
    eq("precondition: that run, and its delta window, are over",
       [s.run(), s.deltaOn()], [null, false]);
    P(0, { battleEpoch: 2 });
    eq("the new battle's first tick shows nothing (it is a silent re-seed)", s.run(), null);
    P(0, { battleEpoch: 2, altHeld: true });
    // ONE assertion, both halves: that the peek really did bring the bar UP is what stops the readout
    // half passing on a bar that simply never appeared. (No mutation in the table breaks a cold peek
    // on its own, so a separate `run() !== null` line would be an unprobed assertion -- exactly the
    // vacuity this file exists to refuse.)
    eq("an Alt peek right after the boundary brings the bar up reading 0 -- NOT the dead battle's "
       + "number", [s.run() !== null, dn()], [true, "0"]);
    eq("...with no flash -- a peek never re-shows an increment", s.deltaOn(), false);

    // --- COLD SHOW, and the delta display window --------------------------------------------
    section("cold show + delta window");
    s = mount(srcs);
    s.push(M());
    s.push(M({ damage: 1900, barX: 45, band: 1 }));
    eq("run #1 uses the original identity", s.run(), RUN_CLASSES[0]);
    eq("the entry plays from the top (no seek)", s.root.style.animationDelay, "0ms");
    eq("the delta is shown on the hit", s.deltaOn(), true);
    eq("...signed, and thousands-separated", s.capDN.textContent, "+400");
    // BARE -- this bar renders no parens (the Moving Average bar still does). Asserted on the
    // SOURCE markup because the shim drops text nodes, so capD.textContent can never see them.
    ok("...and bare: the wrapper adds no parens around .mp-d-num",
       /<span class="mp-d"><span class="mp-d-num"><\/span><\/span>/.test(B_SRC));
    eq("the fill moved to the pushed barX", s.fill.style.width, "45.000%");
    s.clock.advance(DELTA_HOLD - 1);
    eq("the delta is still up one tick short of its own window", s.deltaOn(), true);
    s.clock.advance(1);
    eq("...and drops at DELTA_HOLD_MS", s.deltaOn(), false);
    ok("while the bar itself is still up (the delta window is the SHORTER one)", s.run() !== null);

    // --- WARM RE-TRIGGER: the debounce, on the ALTERNATE identity ----------------------------
    // A coalesced restart on a `both`-filled opacity:0 root is the "shows once, never again" bug the
    // Moving Average bar shipped with, which is the entire reason the stylesheet carries the
    // mp-life-b twin. So the identity MUST flip, and the seek must skip the entry.
    section("warm re-trigger");
    s.push(M({ damage: 2200, barX: 55, band: 2 }));
    eq("re-armed on the ALTERNATE identity", s.run(), RUN_CLASSES[1]);
    eq("seeked PAST the entry to the plateau -- no re-flash, no re-slide",
       s.root.style.animationDelay, "-" + SEEK_PLATEAU + "ms");
    eq("the delta flashed again, latching only this increment",
       [s.deltaOn(), s.capDN.textContent], [true, "+300"]);
    s.push(M({ damage: 2500, barX: 65, band: 2 }));
    eq("...and back again on the next hit -- the alternation goes both ways", s.run(),
       RUN_CLASSES[0]);

    // --- a STALE animationend from the superseded identity ----------------------------------
    section("stale animationend");
    s.animEnd(RUN_NAMES[1]);
    eq("the superseded run's animationend is ignored", s.run(), RUN_CLASSES[0]);
    s.animEnd(RUN_NAMES[0]);
    eq("the LIVE run's animationend ends it", s.run(), null);
    eq("...and drops the delta with it (the onEnd hook)", s.deltaOn(), false);

    // --- A DIP MUST NOT POP THE BAR ----------------------------------------------------------
    // The show trigger is `gained`, which ONLY a new high-water mark sets -- "the value changed" and
    // "the player gained damage" are different events, and combined damage SUBTRACTS team damage, so
    // the total moves DOWN with no new information in it. This runs on the branch above, where the
    // previous run has ENDED on its own animationend: T.show() is then the only thing that could arm
    // anything, so `run() === null` has exactly one possible author. BOTH HALVES MATTER -- the bar
    // must be QUIET *and* still repainting, or this would pass just as well on a bar that is broken.
    section("a dip must not pop the bar");
    s.push(M({ damage: 2300, barX: 30, band: 1 }));
    eq("a dip after the run ended arms NOTHING", s.run(), null);
    eq("...and does not re-flash the increment either", s.deltaOn(), false);
    eq("...while the dipped total and barX still repaint",
       [s.capCV.textContent, s.fill.style.width, s.tCur.style.left], ["2,300", "30.000%", "30.000%"]);
    eq("...and so do the band, .met and the pulse",
       [s.bands(), s.met(), s.root.classList.contains("mp-pulse")],
       [[BANDS[1]], [true, false, false, false], false]);
    eq("...and the latched increment STANDS, neither reset nor gone negative", dn(), "+300");

    // --- the fallback end timer: animationend never arrives ---------------------------------
    section("end-timer fallback");
    s = mount(srcs);
    s.push(M());
    s.push(M({ damage: 1900, barX: 45 }));
    s.clock.advance(TOTAL + MARGIN);
    eq("the run ends on the fallback timer with no animationend at all", s.run(), null);
    s.push(M({ damage: 2000, barX: 50 }));
    // The identity is NOT asserted here: armRun alternates unconditionally, so which of the pair
    // run #2 lands on is a function of how many runs came before it, not of this behaviour.
    eq("so a LATER hit still shows -- a cold one (not wedged 'showing')",
       [s.run() !== null, s.root.style.animationDelay], [true, "0ms"]);

    // --- ALT PEEK: hold, then release --------------------------------------------------------
    section("peek hold + release");
    s = mount(srcs);
    s.push(M());
    s.push(M({ altHeld: true }));
    eq("the peek cold-shows the bar (full entry)", s.root.style.animationDelay, "0ms");
    eq("not paused mid-fade-in", s.root.style.animationPlayState, "");
    eq("a peek does NOT flash the delta -- that increment already had its moment",
       s.deltaOn(), false);
    s.clock.advance(FADE_IN);
    eq("paused once the entry completes", s.root.style.animationPlayState, "paused");
    s.clock.advance(60000);
    eq("a held peek NEVER ends -- the fallback timer must not end it either",
       [s.root.style.animationPlayState, s.run()], ["paused", RUN_CLASSES[0]]);
    s.push(M({ altHeld: false }));
    eq("released -> unpaused", s.root.style.animationPlayState, "");
    eq("...and seeked straight to the fade-out stop", s.root.style.animationDelay,
       "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("only the fade-out played, then the run ended", s.run(), null);

    // --- THE RESUME-VS-FADE SPLIT (peekOn): Alt pressed DURING the fade-out -------------------
    // `showing` stays true all the way THROUGH the fade-out (only endRun clears it), so branching
    // the pause-vs-re-arm decision on it freezes the widget at partial opacity. The phase has to come
    // from ELAPSED TIME: Date.now() vs plateauAt + HOLD_MS.
    section("alt during fade-out");
    s = mount(srcs);
    s.push(M());
    s.push(M({ damage: 1900, barX: 45 }));       // cold show
    s.clock.advance(FADE_IN + HOLD + 100);      // 100ms INTO the fade-out
    eq("precondition: still armed and unpaused (fading out)",
       [s.run(), s.root.style.animationPlayState], [RUN_CLASSES[0], ""]);
    s.push(M({ damage: 1900, barX: 45, altHeld: true }));
    eq("re-armed at the PLATEAU, not paused in place, and not a cold entry from opacity 0",
       s.root.style.animationDelay, "-" + SEEK_PLATEAU + "ms");
    eq("...on a fresh identity, unpaused",
       [s.run(), s.root.style.animationPlayState], [RUN_CLASSES[1], ""]);
    s.clock.advance(0);                         // the pause callback is due immediately
    eq("pinned at FULL opacity, not part-way through the fade-out",
       s.root.style.animationPlayState, "paused");
    s.clock.advance(60000);
    eq("and held indefinitely -- the superseded run's timer cannot end it",
       [s.root.style.animationPlayState, s.run()], ["paused", RUN_CLASSES[1]]);
    s.push(M({ damage: 1900, barX: 45, altHeld: false }));
    eq("the release still fades out exactly once (the damage hold is long dead)",
       s.root.style.animationDelay, "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("...and ends", s.run(), null);

    // --- THE RESUME-VS-FADE SPLIT (peekOff): a release mid-damage-hold RESUMES it --------------
    // Players hold Alt near-constantly (extended vehicle markers), so fading out on release would
    // truncate a hit's 5s hold to whatever was left of the peek. WHAT MATTERS IS *WHEN IT ENDS*:
    // the resumed run must expire exactly when the untouched damage run would have -- earlier is the
    // truncation bug, later is a free hold extension on every Alt tap, and both look identical to a
    // "still showing" check. The instants are absolute, stepped to rather than chained.
    section("alt across a damage hold");
    const at = (st, t) => st.clock.advance(t - st.clock.now());
    const PRESS = Math.round(HOLD * 0.4), HELD = Math.round(HOLD * 0.2);
    s = mount(srcs);
    s.push(M());
    s.push(M({ damage: 1900, barX: 45 }));
    const T0 = s.clock.now();
    const DMG_END = T0 + TOTAL + MARGIN;        // armRun(SEEK_NONE)'s own endT, untouched
    s.clock.advance(PRESS);
    s.push(M({ damage: 1900, barX: 45, altHeld: true }));
    eq("precondition: a press mid-hold neither re-arms nor moves the run",
       [s.run(), s.root.style.animationDelay], [RUN_CLASSES[0], "0ms"]);
    s.clock.advance(0);
    eq("precondition: pinned at the plateau", s.root.style.animationPlayState, "paused");
    s.clock.advance(HELD);
    s.push(M({ damage: 1900, barX: 45, altHeld: false }));
    eq("the release RESUMES the damage hold, seeked to its true elapsed position",
       s.root.style.animationDelay, "-" + (PRESS + HELD) + "ms");
    at(s, T0 + PRESS + HELD + FADE_OUT + MARGIN);
    eq("a plain fade-out's worth of time after the release it is STILL up -- that truncation was the "
       + "whole bug", s.run(), RUN_CLASSES[1]);
    at(s, DMG_END - 1);
    eq("still up right up to the instant the untouched damage run would have ended",
       s.run(), RUN_CLASSES[1]);
    at(s, DMG_END);
    eq("and it ends exactly THERE: neither truncated to the release nor handed a fresh hold",
       s.run(), null);

    // ...but a hold that already DIED must never be resurrected by a later release. Two ways it
    // dies, two clears (endRun and reset), so two cases -- and the clock only ever advances through
    // the peek's own entry, so the record is still nominally live and arithmetic cannot save us.
    s = mount(srcs);
    s.push(M());
    s.push(M({ damage: 1900, barX: 45 }));
    s.clock.advance(PRESS);
    s.animEnd(RUN_NAMES[0]);                    // the AUTHORITATIVE end, mid-hold
    eq("precondition: the run ended on its animationend, mid-hold", s.run(), null);
    s.push(M({ damage: 1900, barX: 45, altHeld: true }));
    s.clock.advance(FADE_IN);
    s.push(M({ damage: 1900, barX: 45, altHeld: false }));
    eq("an ENDED run's hold is not resumed -- plain fade-out", s.root.style.animationDelay,
       "-" + SEEK_FADE_OUT + "ms");
    s = mount(srcs);
    s.push(M());
    s.push(M({ damage: 1900, barX: 45 }));
    s.clock.advance(PRESS);
    s.push(M({ visible: false }));              // a hide (scoreboard / arena end), mid-hold
    eq("precondition: hidden, and the run disarmed",
       [s.root.style.display, s.run()], ["none", null]);
    s.push(M({ damage: 1900, barX: 45 }));
    eq("the first push after a re-show is a silent baseline again", s.run(), null);
    s.push(M({ damage: 1900, barX: 45, altHeld: true }));
    s.clock.advance(FADE_IN);
    s.push(M({ damage: 1900, barX: 45, altHeld: false }));
    eq("a hold killed by a hide is not resumed across the reset -- plain fade-out",
       s.root.style.animationDelay, "-" + SEEK_FADE_OUT + "ms");

    // --- THE CLAMP CORRIDOR ------------------------------------------------------------------
    // The current caption is centred on its tick, but its glyph hangs off the left and its delta off
    // the right, so at 100 % the delta would overflow the surface. meta.capClamp's corridor is in
    // document rem: [-76, 376] against a 300rem bar. .mp-cap's own offsetWidth is the NUMERAL only
    // (icon and delta are out of flow), so the larger overhang is added back -- the icon's with its
    // transform gap, which is NOT in its offsetWidth. (The shim's offsetWidth is WRITABLE precisely
    // so this section is not vacuous -- at a constant 0 the corridor never binds.)
    section("cap clamp corridor");
    s = mount(srcs);
    s.capC.offsetWidth = 100;                   // half the numeral == 50
    s.capIco.offsetWidth = 60;                  // + ICO_GAP_REM == 61 -> half == 111
    s.capD.offsetWidth = 0;
    const HALF = 100 / 2 + 60 + ICO_GAP;
    const LO = ((CLAMP_L + HALF) / BAR_W * 100).toFixed(3) + "%";
    const HI = ((CLAMP_R - HALF) / BAR_W * 100).toFixed(3) + "%";
    s.push(M({ barX: 0 }));
    eq("at barX 0 the caption is held off the LEFT bound (meta.capClamp.leftRem)",
       s.capC.style.left, LO);
    eq("...while the fill and tick are NOT clamped -- only the caption is",
       [s.fill.style.width, s.tCur.style.left], ["0.000%", "0.000%"]);
    s.push(M({ barX: 100 }));
    eq("at barX 100 it is held off the RIGHT bound (meta.capClamp.rightRem)",
       s.capC.style.left, HI);
    s.push(M({ barX: 50 }));
    eq("mid-axis it rides its tick untouched", s.capC.style.left, "50.000%");
    // The delta can be the wider overhang, and then IT sets the margin (no icon gap involved).
    s.capIco.offsetWidth = 10;
    s.capD.offsetWidth = 60;
    s.push(M({ barX: 0 }));
    eq("the WIDER of the two overhangs wins -- here the delta's",
       s.capC.style.left, ((CLAMP_L + 50 + 60) / BAR_W * 100).toFixed(3) + "%");
    // A corridor narrower than the caption is DEGENERATE: bail, do not invert the bounds.
    s.capC.offsetWidth = 1000;
    s.push(M({ barX: 100 }));
    eq("a degenerate corridor bails out of the clamp entirely", s.capC.style.left, "100.000%");
    s.push(M({ barX: 0 }));
    eq("...at both ends", s.capC.style.left, "0.000%");

    // --- barX AND band ARE CONSUMED VERBATIM -------------------------------------------------
    // domain/battle_builder owns efficiency_bar_x / efficiency_band, and the `>=`-INCLUSIVE
    // boundary rule is unit-tested THERE. So this file must do no axis arithmetic and no
    // damage-vs-requirement comparison. Proved two ways: behaviourally, with a model whose pushed
    // values are deliberately INCONSISTENT with anything derivable from damage and the r* stops
    // (huge damage, tiny requirements, yet band 0 and barX 7) -- any recomputation lands elsewhere.
    section("barX / band consumed verbatim");
    s = mount(srcs);
    s.push(M({ damage: 999999, barX: 7, band: 0,
               r65: 100, r85: 200, r95: 300, r100: 400 }));
    eq("the fill sits at the PUSHED barX, not at anything derived from damage",
       s.fill.style.width, "7.000%");
    eq("...and so does the moving tick", s.tCur.style.left, "7.000%");
    eq("NO requirement reads as met, though the damage dwarfs all four", s.met(),
       [false, false, false, false]);
    eq("...no pulse either", s.root.classList.contains("mp-pulse"), false);
    eq("the band class is the PUSHED index", s.bands(), [BANDS[0]]);
    eq("the r* props reached the caption NUMERALS and nothing else",
       [1, 2, 3, 4].map((i) => s.reqCapV(i).textContent), ["100", "200", "300", "400"]);

    // ...and in the SOURCE TEXT, with comments stripped (both modules' prose is full of the words
    // `damage`, `>=` and `INCLUSIVE`, so a raw grep would pass on the commentary alone -- the repo
    // lesson `unscoped-substring-assertion-is-not-an-assertion`) and scoped to the owning line.
    //
    // ON BOTH FILES. The rule is that the `>=`-inclusive damage-vs-REQUIREMENT test lives in Python
    // (domain.efficiency_band) and nothing on the front end may re-derive it -- and the shared
    // transient is as much "the front end" as this bar is. The delta latch is damage-vs-damage and
    // touches no requirement, which is exactly why it reads the total into a `total` local first:
    // no comparison may share a line with `damage`.
    section("no axis math in the source");
    const lines = (src) => S.stripComments(src).split("\n");
    const CMP = /(?:>=|<=|(?<![=!<>])<(?!=)|(?<![=!<>-])>(?!=))/;
    const AXIS = /\bdamage\b|\bcur\.r\b|\.r\[|\br(?:65|85|95|100)\b/;
    for (const [name, src] of [["MoEEfficiency.js", srcs.B], ["MoEBarTransient.js", srcs.T]]) {
        eq("no comparison operator touches damage or a requirement stop in " + name,
           lines(src).filter((l) => CMP.test(l) && AXIS.test(l)), []);
    }
    const code = lines(srcs.B);
    eq("`cur.r` is read on exactly ONE line -- the caption numerals",
       code.filter((l) => /\bcur\.r\b|cur\.r\[/.test(l)).map((l) => l.trim()),
       ["capV(reqCaps[i]).textContent = fmt(cur.r[i]);"]);
    eq("...and the r* model props only on the two lines of the array build",
       code.filter((l) => /model\.r(?:65|85|95|100)\b/.test(l)).length, 2);
    // THE LATCH IS JS-SIDE NOW: EfficiencyVM stopped carrying damageDelta, so nothing may read one
    // back off the model -- a stale read would silently shadow the latch.
    eq("nothing reads a damageDelta off the model (the latch replaced it)",
       code.filter((l) => /damageDelta/.test(l)), []);

    // --- THE CONFIGURABLE HOLD DURATION (mod_settings.progress_hold_seconds, pushed as `holdMs`) --
    // The shared half is identical to check_progress_js.js's twin: applyHold's fail-soft cast and
    // T.hold(model.holdMs) both live where BOTH bars call them, so both harnesses assert it, on this
    // bar's own hit-driven cold show.
    //
    // holdFrom CORRECTS the deadline mp-life already bakes rather than replacing it, so the two
    // directions are observably different:
    //   AT THE BAKED HOLD (default, unpushed, or a hostile value failing soft to it) it does NOTHING
    //     -- animationDelay stays "0ms", the identity never flips, and the keyframe's own fade-out
    //     plus animationend end the run. Asserted, not assumed: the obvious "always pause and
    //     re-arm" implementation satisfies every duration below while costing EVERY ordinary
    //     auto-hide an extra identity flip mid-run (a live flicker risk).
    //   AWAY FROM IT the exit is re-targeted through releaseHold, which seeks the replacement run to
    //     the fade-out stop (see "peek hold + release"), so animationDelay says WHEN.
    section("configurable hold duration");
    s = mount(srcs);
    s.push(M());                                   // no holdMs field at all
    s.push(M({ damage: 1900, barX: 45, band: 1 })); // cold show -- the plain shipped entry
    const unpushedRun = s.run();
    s.clock.advance(FADE_IN + HOLD - 1);
    eq("an unpushed hold has not released just before the BAKED HOLD_MS elapses",
       s.root.style.animationDelay, "0ms");
    s.clock.advance(1);
    eq("...and AT the baked deadline it still has not touched the run: no re-arm, no seek, no "
       + "identity flip -- the keyframe's own fade-out is what plays",
       [s.root.style.animationDelay, s.run()], ["0ms", unpushedRun]);
    s.clock.advance(FADE_OUT);
    s.animEnd(RUN_NAMES[0]);
    eq("...and its OWN animationend ends it, one fade-out after the baked deadline", s.run(), null);

    s = mount(srcs);
    s.push(M({ holdMs: 10000 }));                  // a configured hold, longer than the baked one
    s.push(M({ damage: 1900, barX: 45, band: 1, holdMs: 10000 }));  // T.hold() reads EVERY render
    s.clock.advance(FADE_IN);
    eq("a LONGER hold parks the run AT its plateau -- without the pause the keyframe would fade out "
       + "at the baked HOLD_MS and the extra seconds would show nothing",
       s.root.style.animationPlayState, "paused");
    s.clock.advance(HOLD + 1);                     // past where the BAKED hold would have released
    eq("a configured hold outlives the BAKED HOLD_MS", s.root.style.animationDelay, "0ms");
    eq("...and is still parked there", s.root.style.animationPlayState, "paused");
    s.clock.advance((FADE_IN + 10000) - (FADE_IN + HOLD + 1) - 1);
    eq("...still running right up to its OWN configured deadline", s.root.style.animationDelay,
       "0ms");
    s.clock.advance(2);
    eq("...and releases exactly at the configured duration", s.root.style.animationDelay,
       "-" + SEEK_FADE_OUT + "ms");
    eq("...unpaused, so the fade-out actually plays", s.root.style.animationPlayState, "");

    s = mount(srcs);
    s.push(M({ holdMs: 0 }));                      // a hostile push must fail SOFT, not release now
    s.push(M({ damage: 1900, barX: 45, band: 1, holdMs: 0 }));
    const softRun = s.run();
    s.clock.advance(FADE_IN + HOLD - 1);
    eq("a zero holdMs has not released just before the BAKED HOLD_MS",
       s.root.style.animationDelay, "0ms");
    s.clock.advance(2);
    eq("...it degrades to the baked HOLD_MS -- which means the correction is INERT, exactly as for "
       + "an unpushed field, so the run is still the untouched shipped one",
       [s.root.style.animationDelay, s.run()], ["0ms", softRun]);
    s.clock.advance(FADE_OUT + MARGIN);
    eq("...and ends no later than its own fallback timer, never immediately", s.run(), null);

    // THE HOLD CORRECTION MUST NEVER OUTLIVE AN ALT PRESS -- a REGRESSION, found by probe and fixed
    // in peekOn. A peek's own cold entry runs through coldShow, which arms a correction of its own,
    // so peekOn has to drop it AFTER that branch rather than before: clearing first left a hold
    // SHORTER than the baked one free to release the bar out from under a still-held key (measured:
    // a 2s hold ended the peek 3.2s in and ignored Alt entirely). "Always" is a permanently-held
    // Alt, so this is also what stops a short hold from un-pinning the always-on mode.
    s = mount(srcs);
    s.push(M({ holdMs: 2000 }));
    s.push(M({ holdMs: 2000, altHeld: true }));    // Alt cold-shows the bar
    s.clock.advance(FADE_IN + 2000 + FADE_OUT + MARGIN);   // well past the CONFIGURED hold
    ok("a hold shorter than the baked one does not release a HELD Alt", s.run() !== null);
    eq("...and the bar is still parked at its plateau", s.root.style.animationPlayState, "paused");
    s.push(M({ holdMs: 2000, altHeld: false }));   // ...only the release ends it
    eq("the RELEASE is what fades it out", s.root.style.animationDelay,
       "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("...and it is gone one fade-out later", s.run(), null);

    // --- THE LARGE SIZE MODE (mod_settings.progress_bar_size, pushed as `barSize`) -----------
    // The shared half (root font, body class, re-derived surface / hit rect / shift, idempotence,
    // the scale-update re-apply) is identical to check_progress_js.js's -- it lives in the shared
    // transient, so BOTH harnesses assert it, on their OWN surface constants. Every expectation is
    // DERIVED from the scraped factors (LG_* above), never written down.
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
    eq("...and re-pushes the surface with BOTH factors on x and only SIZE_F on y (ROUNDED: the " +
       "x term is 949.9999999999999 in float)", s.calls.resize.slice(resizes), [LG_SURFACE]);
    eq("...and re-collapses the hit rect per axis off the new (larger) surface",
       s.calls.hit.slice(hits),
       [[LG_HIT_PAD, LG_HIT_PAD, LG_HIT_PAD, LG_HIT_PAD, HIT_MAGIC]]);
    eq("...and re-derives the rigid shift in document rem (3dp, matching the .mp-lg block)",
       s.root.style.left, LG_SHIFT_X);
    eq("...while the vertical shift is untouched -- it is a rem the root font already scaled",
       s.root.style.top, SHIFT[1]);

    const settled = s.calls.resize.length;
    s.push(M({ barSize: 1, damage: 1600 }));
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
    s.push(M({ barSize: 1 }));
    eq("a scale update seen at the shipped size is not remembered as the base",
       s.documentElement.style.fontSize, (ROOT_FONT_PX * 4 * SIZE_F) + "px");


    // --- THE INTERFACE-SCALE GATE (.mp-s1) ----------------------------------------------------
    // The body class MoEEfficiency.css's HAND-ADDED BLOCK 4 hangs its caption-icon correction off.
    // It lives in the shared transient, but only THIS bar's stylesheet carries a rule for it, so it
    // is asserted here alone. Threshold, on the root-font capture, on BOTH size paths.
    // ROOT_FONT_PX is 2 -- the maintainer's approved render -- so the default settled mount is the
    // "must not move" case and 1 is the scale-1 case.
    section("the interface-scale gate");
    s = mount(srcs, true, true);              // unsized == the first frames of a mount
    s.push(M());
    s.clock.advance(SETTLE);                  // the re-assert runs the gate on a STILL-unsized view
    eq("an UNSIZED view's root font is not trusted, so NO class is added -- the base cascade IS the "
       + "approved render, and every failure mode must land on it", s.body.classList.contains("mp-s1"),
       false);

    s = mount(srcs, true, true);
    s.push(M());
    s.font.px = 1;                            // the engine arrives at interface scale 1...
    s.win.innerWidth = 1920;
    s.win.innerHeight = 1080;
    s.clock.advance(SETTLE);
    ok("a base font BELOW the threshold (interface scale 1) turns the correction on",
       s.body.classList.contains("mp-s1"));

    s = mount(srcs, true, true);
    s.push(M());
    s.font.px = ROOT_FONT_PX;                 // ...and at interface scale 2 (the approved render)
    s.win.innerWidth = 1920;
    s.win.innerHeight = 1080;
    s.clock.advance(SETTLE);
    eq("at/above the threshold there is no class at all, so no .mp-s1 selector can match and the "
       + "approved render is structurally unreachable", s.body.classList.contains("mp-s1"), false);

    s = mount(srcs, true, true);
    s.push(M({ barSize: 1 }));                // Large enabled BEFORE launch: the re-assert takes the
    s.font.px = 1;                            // large branch, and the gate must STILL run
    s.win.innerWidth = 1920;
    s.win.innerHeight = 1080;
    s.clock.advance(SETTLE);
    ok("a launch STRAIGHT INTO Large gets the gate too (the shipped build ran it in the `else` "
       + "alone, so the correction depended on HOW the user reached Large)",
       s.body.classList.contains("mp-s1"));
    ok("...alongside mp-lg, which is what the compound .mp-s1.mp-lg rule is for",
       s.body.classList.contains("mp-lg"));

    // ...and the flip RE-EVALUATES it, which is the one path an engine-pushed scale can reach it by:
    // self.onScaleUpdated only updates the base while large, so flipping back is where that base is
    // first re-read. A scale of 2 pushed under Large must switch the correction OFF on the way out.
    s.scaleUpdate(ROOT_FONT_PX);
    s.push(M({ barSize: 0 }));
    eq("a size flip re-evaluates the gate off the base self.onScaleUpdated pushed, and toggle() "
       + "REMOVES the class rather than latching it", s.body.classList.contains("mp-s1"), false);


    // --- THE CLAMP CORRIDOR UNDER THE LARGE MODE ---------------------------------------------
    // capClampPct is the ONE function on either bar that mixes a MEASURED px width with rem
    // literals, so it is the one place the "1rem == 1 logical px" identity is load-bearing rather
    // than incidental -- and the large mode breaks it: 1rem is SIZE_F px now. Two independent
    // corrections, and they pull in OPPOSITE directions, which is why neither can be normalised
    // away: every rem CONSTANT is an x-length and takes SIZE_XF, while every MEASUREMENT is divided
    // back into document rem by SIZE_F. The same three measured widths as the 1x section above, each
    // scaled by SIZE_F so the caption is the SAME size in rem -- so the only thing moving the result
    // is the corridor's own x factor.
    section("cap clamp corridor under the large size mode");
    s = mount(srcs);
    s.push(M({ barSize: 1 }));
    s.capC.offsetWidth = 100 * SIZE_F;          // 100 document rem -> half is 50
    s.capIco.offsetWidth = 60 * SIZE_F;         // 60 document rem
    s.capD.offsetWidth = 0;
    const LG_HALF = 100 / 2 + 60 + ICO_GAP * SIZE_XF;
    const LG_LO = ((CLAMP_L * SIZE_XF + LG_HALF) / (BAR_W * SIZE_XF) * 100).toFixed(3) + "%";
    const LG_HI = ((CLAMP_R * SIZE_XF - LG_HALF) / (BAR_W * SIZE_XF) * 100).toFixed(3) + "%";
    s.push(M({ barSize: 1, barX: 0 }));
    eq("at barX 0 the caption is held off the LEFT bound, scaled by SIZE_XF",
       s.capC.style.left, LG_LO);
    ok("...and that is NOT the 1x answer -- the corridor really did scale",
       s.capC.style.left !== ((CLAMP_L + 100 / 2 + 60 + ICO_GAP) / BAR_W * 100).toFixed(3) + "%");
    eq("...while the fill and tick are still NOT clamped -- only the caption is",
       [s.fill.style.width, s.tCur.style.left], ["0.000%", "0.000%"]);
    s.push(M({ barSize: 1, barX: 100 }));
    eq("at barX 100 it is held off the RIGHT bound", s.capC.style.left, LG_HI);
    s.push(M({ barSize: 1, barX: 50 }));
    eq("mid-axis it rides its tick untouched, at ANY size", s.capC.style.left, "50.000%");
    // A caption WIDER than the corridor still bails instead of inverting the bounds.
    s.capC.offsetWidth = 1000 * SIZE_F;
    s.push(M({ barSize: 1, barX: 100 }));
    eq("a degenerate corridor bails out of the clamp entirely, at ANY size",
       s.capC.style.left, "100.000%");

    // --- THE TRANSITION SWITCHES (mod_settings.progress_transitions_events / _manual, pushed as
    // --- the VM's transEvents / transManual) --------------------------------------------------
    // TWO pushed bools, one per trigger AREA (a hit takes the events flag, an Alt peek the manual
    // one), and the LIVE RUN's copy is decided AT ARM TIME so the EXIT follows the same switch as the
    // entry. Un-animated is NOT a second code path: the entry arms at SEEK_PLATEAU (opacity 1 and
    // translateY(0) both already complete, so there is nothing left to play) and the end timer stops
    // being a FALLBACK -- it becomes the REAL end at the end of the hold, with no fade-out and no
    // margin. (The VALUE half of the change -- the snap through onRewind and the skipped onCommit --
    // cannot be seen from here: this bar passes NEITHER hook. check_progress_js.js owns it.)
    // WHAT MATTERS IS *WHEN IT ENDS*, so every end instant is absolute (stepped to with `at`) and
    // DERIVED from the scraped timings -- "still armed" alone cannot tell TOTAL_MS + END_MARGIN_MS
    // from HOLD_MS.
    const F = (flags, extra) => M(Object.assign({}, flags, extra));
    const EV_ON = { transEvents: true, transManual: true };
    const EV_OFF = { transEvents: false };
    const MAN_OFF = { transManual: false };
    const MAN_ON = { transManual: true };
    const MIX = { transEvents: false, transManual: true };   // events instant, Alt animated
    let armAt = 0;

    section("transitions: events ON");
    s = mount(srcs);
    s.push(F(EV_ON));                                 // the silent baseline seeds the mark
    armAt = s.clock.now();
    s.push(F(EV_ON, { damage: 1900, barX: 45 }));
    eq("an explicit events:true hit still plays the entry from the top",
       s.root.style.animationDelay, "0ms");
    at(s, armAt + TOTAL);
    eq("...and it is still armed all the way through the fade-out", s.run(), RUN_CLASSES[0]);
    at(s, armAt + TOTAL + MARGIN - 1);
    eq("...right up to its own FALLBACK end timer", s.run(), RUN_CLASSES[0]);
    at(s, armAt + TOTAL + MARGIN);
    eq("...which sits TOTAL_MS + END_MARGIN_MS after the arm", s.run(), null);

    section("transitions: events OFF");
    s = mount(srcs);
    s.push(F(EV_OFF));
    armAt = s.clock.now();
    s.push(F(EV_OFF, { damage: 1900, barX: 45 }));
    eq("an un-animated hit arms AT the plateau instead of playing the entry",
       s.root.style.animationDelay, "-" + SEEK_PLATEAU + "ms");
    eq("...while the values and the increment flash exactly as they always do",
       [s.fill.style.width, s.capCV.textContent, s.capDN.textContent, s.deltaOn()],
       ["45.000%", "1,900", "+400", true]);
    at(s, armAt + HOLD - 1);
    eq("still armed one tick short of the hold's own end", s.run(), RUN_CLASSES[0]);
    at(s, armAt + HOLD);
    eq("...and DISARMED exactly at HOLD_MS: the end timer is the REAL end now, so it carries neither "
       + "a fade-out nor END_MARGIN_MS", s.run(), null);

    section("transitions: manual OFF");
    s = mount(srcs);
    s.push(F(MAN_OFF));
    s.push(F(MAN_OFF, { altHeld: true }));
    eq("an un-animated Alt entry arms AT the plateau too", s.root.style.animationDelay,
       "-" + SEEK_PLATEAU + "ms");
    eq("...and still does not flash the delta", s.deltaOn(), false);
    s.push(F(MAN_OFF, { altHeld: false }));
    eq("the release ENDS the run in the SAME TICK -- no fade-out is armed", s.run(), null);
    // 1, not 0: mount()'s settle callback ran against the harness's still-empty pre-push model
    // (not yet `visible`), so it left ONE self-rescheduling cold-mount poll timer pending
    // (MoEBarTransient.js's COLD_POLL_MS retry) -- and nothing in this section ever advances the
    // clock far enough for that retry to fire. It is not a leftover run/hold/peek timer: those
    // are all what the release below actually clears.
    eq("...unpaused, with nothing but the cold-mount poll left pending on the clock",
       [s.root.style.animationPlayState, s.clock.pending()], ["", 1]);
    s.push(F(MAN_OFF, { damage: 1900, barX: 45 }));
    eq("...and it went through endRun (onEnd and all), not a bare disarm: `showing` was cleared, so "
       + "the next hit is a fresh COLD show and not a warm re-trigger",
       s.root.style.animationDelay, "0ms");

    // REGRESSION GUARD: an explicit manual:true must still take the shipped mirrored fade-out. The
    // sections above this block carry NEITHER field, so without this one nothing pins the peek's exit
    // against a `true` that is actually read.
    section("transitions: manual ON");
    s = mount(srcs);
    s.push(F(MAN_ON));
    s.push(F(MAN_ON, { altHeld: true }));
    s.clock.advance(FADE_IN);
    eq("precondition: an animated peek reached its plateau pause",
       s.root.style.animationPlayState, "paused");
    s.push(F(MAN_ON, { altHeld: false }));
    eq("the release still seeks straight to the fade-out stop", s.root.style.animationDelay,
       "-" + SEEK_FADE_OUT + "ms");
    eq("...and the bar is still up, on a fresh identity, unpaused",
       [s.run(), s.root.style.animationPlayState], [RUN_CLASSES[1], ""]);
    s.clock.advance(FADE_OUT + MARGIN);
    eq("...gone only a fade-out later", s.run(), null);

    // THE MIXED CASE: the two flags are independent, so an ANIMATED Alt peek can interrupt an
    // UN-ANIMATED hit's hold. The run's `animated` is the ARMING AREA's, kept for the whole run, so
    // the resumed hold still exits the HIT's way -- instantly, at the instant the untouched
    // un-animated hold would have ended.
    section("transitions: an animated peek across an un-animated hit's hold");
    s = mount(srcs);
    s.push(F(MIX));
    armAt = s.clock.now();
    s.push(F(MIX, { damage: 1900, barX: 45 }));
    eq("precondition: the hit's hold armed at the plateau", s.root.style.animationDelay,
       "-" + SEEK_PLATEAU + "ms");
    s.clock.advance(PRESS);
    s.push(F(MIX, { damage: 1900, barX: 45, altHeld: true }));
    s.clock.advance(0);                         // the pause is due immediately (already at plateau)
    eq("precondition: the peek pinned it at the plateau", s.root.style.animationPlayState, "paused");
    s.clock.advance(HELD);
    s.push(F(MIX, { damage: 1900, barX: 45, altHeld: false }));
    eq("the release RESUMES the hit's hold at its true elapsed position",
       s.root.style.animationDelay, "-" + (SEEK_PLATEAU + PRESS + HELD) + "ms");
    at(s, armAt + HOLD - 1);
    eq("...for exactly the REMAINING hold, not a fresh one", s.run(), RUN_CLASSES[1]);
    at(s, armAt + HOLD);
    eq("...and the exit is INSTANT at the original hold's end -- the peek did not buy the hit a "
       + "fade-out it had switched off", s.run(), null);

    // THE FAIL-SOFT DIRECTION, pinned explicitly. `!== false` is why a model that does not carry the
    // fields (a pre-push frame, a marshal that dropped them, every fixture above) degrades to the
    // SHIPPED animated bar; `!!undefined` would silently degrade to instant instead.
    section("transitions: an absent flag degrades to ANIMATED");
    s = mount(srcs);
    const NONE = { transEvents: undefined, transManual: undefined };
    s.push(F(NONE));
    s.push(F(NONE, { damage: 1900, barX: 45 }));
    eq("T.anim(undefined, undefined) leaves the EVENT half animated: a full entry from the top",
       s.root.style.animationDelay, "0ms");
    s.clock.advance(TOTAL + MARGIN);
    eq("precondition: that run is over (so the peek below is a cold entry)", s.run(), null);
    s.push(F(NONE, { damage: 1900, barX: 45, altHeld: true }));
    s.clock.advance(FADE_IN);
    eq("...and the MANUAL half animated too: the Alt entry played and paused at the plateau",
       s.root.style.animationPlayState, "paused");
    s.push(F(NONE, { damage: 1900, barX: 45, altHeld: false }));
    eq("...so its release still MIRRORS into the fade-out instead of ending outright",
       [s.root.style.animationDelay, s.run() !== null], ["-" + SEEK_FADE_OUT + "ms", true]);

    // --- CTRL: HOLD THE BAR UP, AND NOTHING ELSE (VM `ctrlHeld`) ------------------------------
    // THE DRAG IS GONE FROM THIS DOCUMENT. The Ctrl+left-button reposition gesture is Python's end
    // to end (adapter/battle_input samples the keys off WG's dispatchers; bridge/bar_window re-places
    // the window ABSOLUTELY from GUI.mcursor().position), so there is no document mousedown/
    // mousemove/mouseup listener, no `setPosition` reverse command, and no delta protocol left to
    // test. See check_progress_js.js's own twin section, which drives the SAME shared transient --
    // this bar only differs in its own value fixture (damage/barX) -- and MoEBarTransient's
    // "NOT IN THIS FILE ANY MORE" block for the three structural failures that killed the delta
    // design. Two things replace ~150 lines of harness:
    //
    //   (1) THE HIT RECT IS NOW PERMANENTLY COLLAPSED. It used to be OPENED (padding 0 == the whole
    //       surface rect live) while Ctrl was held, so this document could receive the drag's mouse
    //       events -- and the rect IS the mouse hit rect, so an open one steals HUD input across the
    //       bar's footprint. With no mouse input needed at all it never opens again.
    //   (2) CTRL RIDES THE SAME PEEK AS ALT, which is the bar's whole remaining part in the gesture
    //       (you cannot grab a bar that has faded out).
    section("ctrl");
    const lastHit = (st) => st.calls.hit[st.calls.hit.length - 1] || [];
    const setPos = [];
    // The VM the bars are pushed: a `setPosition` command is offered DELIBERATELY, so a reintroduced
    // reverse-channel report would be recorded here rather than silently swallowed.
    const VM = (extra) => Object.assign({ setPosition: (arg) => setPos.push(arg) }, extra);

    // (a) the rect is collapsed at mount, and STAYS collapsed with Ctrl held.
    s = mount(srcs);
    s.push(M(VM()));
    eq("the input rect is collapsed at mount", lastHit(s),
       [HIT_PAD, HIT_PAD, HIT_PAD, HIT_PAD, HIT_MAGIC]);
    s.push(M(VM({ ctrlHeld: true })));
    eq("a held Ctrl no longer opens the input rect -- the HUD-input-steal hazard is retired",
       lastHit(s), [HIT_PAD, HIT_PAD, HIT_PAD, HIT_PAD, HIT_MAGIC]);
    s.push(M(VM({ ctrlHeld: false })));
    eq("...and releasing it changes nothing either", lastHit(s),
       [HIT_PAD, HIT_PAD, HIT_PAD, HIT_PAD, HIT_MAGIC]);

    // (b) CTRL RIDES THE PEEK: held -> the bar comes up and pauses at the hold plateau; released ->
    // it leaves. This is the one behaviour the flag still drives, and it is what `T.ctrl(...)` being
    // pushed at all buys.
    s = mount(srcs);
    s.push(M(VM()));
    s.push(M(VM({ ctrlHeld: true })));
    s.clock.advance(FADE_IN);
    eq("a held Ctrl pins the bar at the hold plateau, exactly like a held Alt",
       [s.run() !== null, s.root.style.animationPlayState], [true, "paused"]);
    s.push(M(VM({ ctrlHeld: false })));
    eq("...and releasing it seeks straight to the fade-out",
       s.root.style.animationDelay, "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_OUT + MARGIN);
    eq("...which then ends the run", s.run(), null);

    // (c) THE FAIL-SOFT DIRECTION: `=== true`, not `!== false` -- the OPPOSITE of applyAnim /
    // applyHold, because the shipped bar is NOT pinned up. A model that never carries the field (a
    // pre-push frame, an old fixture, a marshal that dropped it) must read as NOT held; `!== false`
    // would peek forever and the bar would never come down.
    s = mount(srcs);
    s.push(M(VM()));
    s.push(M(VM()));
    s.clock.advance(FADE_IN);
    eq("a model that never carries ctrlHeld never peeks", s.run(), null);

    // (d) NO MOUSE LISTENER EXISTS. A Ctrl+mousedown over a showing bar is neither claimed nor
    // stopped -- a foreign listener sees it untouched -- and nothing is ever reported back through
    // the reverse channel. This pins the deletion: any reintroduced document drag fails here.
    s = mount(srcs);
    s.push(M(VM()));
    s.push(M(VM({ damage: 1900, barX: 45, ctrlHeld: true })));   // cold show, Ctrl already down
    let foreign = 0;
    s.document.addEventListener("mousedown", () => { foreign += 1; }, true);
    setPos.length = 0;
    const ev = s.document.dispatch("mousedown", { ctrlKey: true, buttons: 1, screenX: 100,
                                                  screenY: 50, clientX: 100, clientY: 50,
                                                  target: s.body });
    s.document.dispatch("mousemove", { buttons: 1, screenX: 160, screenY: 90,
                                       clientX: 160, clientY: 90 });
    s.document.dispatch("mouseup", { screenX: 160, screenY: 90, clientX: 160, clientY: 90 });
    eq("a Ctrl+mousedown over a showing bar is NOT claimed -- this document takes no mouse input",
       ev.defaultPrevented, false);
    eq("...and is not stopped: a foreign listener still sees it", foreign, 1);
    eq("...and a whole down/move/up gesture reports nothing on the reverse channel",
       setPos.length, 0);
}

S.main("MoEEfficiency.js + MoEBarTransient.js", MUTATIONS, run);
