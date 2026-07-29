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
const { section, eq, ok, El, parseHTML, makeClock, jsConst, jsArray } = S;

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
        "        if (e.animationName !== RUN_NAMES[armIdx]) return;\n", ""],
    "no-end-timer": ["T",
        "        endT = setTimeout(function () { endRun(id); }, TOTAL_MS - seekMs + END_MARGIN_MS);",
        "        endT = null;"],
    "reset-does-not-disarm": ["T",
        "        endedId = runId;                 // no live run left for a late animationend " +
        "to end\n        disarm();",
        "        endedId = runId;"],
    // fmt() moved with the transient; every numeral on this bar is a readout of it.
    "no-thousands-sep": ["T", '.replace(/\\B(?=(\\d{3})+(?!\\d))/g, ",")', ""],

    // ===== the SHARED transient: the Alt peek ==================================================
    "peek-no-pause": ["T",
        '            root.style.animationPlayState = "paused";',
        '            root.style.animationPlayState = "";'],
    "peek-ends-while-held": ["T",
        "            clearTimeout(endT);\n        }, Math.max(0, plateauAt - Date.now()));",
        "        }, Math.max(0, plateauAt - Date.now()));"],
    "release-no-fadeout-seek": ["T", "        armRun(SEEK_FADE_OUT + inLeft);", ""],
    // THE RESUME-VS-FADE SPLIT, peekOn's half. `showing` stays true all the way THROUGH the
    // fade-out, so branching on it freezes the widget at partial opacity -- the phase has to come
    // from elapsed time. Two mutations: drop the re-arm entirely, and the tempting `showing` form.
    "no-fadeout-rearm": ["T",
        "        } else if (!peeking && Date.now() >= plateauAt + HOLD_MS) {",
        "        } else if (false) {"],
    "peek-phase-from-showing": ["T",
        "        } else if (!peeking && Date.now() >= plateauAt + HOLD_MS) {",
        "        } else if (!peeking && !showing) {"],
    // ...and peekOff's half: a release mid-damage-hold RESUMES it (players hold Alt near-constantly),
    // but a hold that already died must NOT be resurrected.
    "no-dmg-hold-resume": ["T",
        "        if (dmgPlateauAt + HOLD_MS > Date.now()) {", "        if (false) {"],
    "endrun-keeps-dmg-plateau": ["T",
        "        dmgPlateauAt = 0;                // the hold is over",
        "        // dmgPlateauAt = 0;  // the hold is over"],
    "reset-keeps-dmg-plateau": ["T",
        "        dmgPlateauAt = 0;                // ditto endRun",
        "        // dmgPlateauAt = 0;  // ditto endRun"],
    // THE SOURCE-TEXT RULE, transient half: the shared module must be as free of a damage
    // comparison as this bar is. Smuggle one in and the text scan has to see it.
    "damage-comparison-smuggled-into-the-transient": ["T",
        "        if (fromDamage) dmgPlateauAt = plateauAt;",
        "        if (fromDamage) dmgPlateauAt = plateauAt;\n        if (cfg.damage > 0) void 0;"],

    // ===== THIS BAR: the show gate, and the silent baseline that must NOT be gated =============
    "no-hit-gate": ["B", "if (gained && T.settled()) {", "if (gained) {"],
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
        "BAND_CLASSES.forEach(function (c, i) { root.classList.toggle(c, i === cur.band); });",
        "BAND_CLASSES.forEach(function (c) { root.classList.toggle(c, true); });"],
    "met-off-by-one": ["B",
        'reqTicks[i].classList.toggle("met", i + 1 <= cur.band);',
        'reqTicks[i].classList.toggle("met", i <= cur.band);'],
    // THE RULE THIS BAR EXISTS TO KEEP IN PYTHON: `.met` may not come off a damage comparison.
    // Caught twice over -- behaviourally (a deliberately inconsistent model) and in the source text.
    "met-from-damage": ["B",
        'reqTicks[i].classList.toggle("met", i + 1 <= cur.band);',
        'reqTicks[i].classList.toggle("met", cur.damage >= cur.r[i]);'],
    "no-pulse-gate": ["B",
        'root.classList.toggle("mp-pulse", cur.band === 4);',
        'root.classList.toggle("mp-pulse", false);'],
    // ...and neither may barX be re-derived here: the axis arithmetic is domain/battle_builder's.
    "barx-recomputed": ["B",
        "        barX: Number(model.barX) || 0,",
        "        barX: Number(model.damage) / Number(model.r100) * 100 || 0,"],
    // setPos moves three things off the ONE pushed barX; each had an assertion and no probe.
    "no-fill-width": ["B", "    fill.style.width = p;", "    void 0;"],
    "no-cur-tick-move": ["B", "    tCur.style.left = p;", "    void 0;"],

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
    "clamp-left-bound": ["B", "    const lo = CLAMP_L_REM + half;", "    const lo = 0 + half;"],
    "clamp-right-bound": ["B",
        "    const hi = CLAMP_R_REM - half;", "    const hi = BAR_W_REM - half;"],
    "no-ico-gap": ["B",
                 'Math.max(w(".mp-ico") + ICO_GAP_REM, w(".mp-d"));',
                 'Math.max(w(".mp-ico"), w(".mp-d"));'],
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
const SURFACE = [jsConst(B_SRC, "BOX_W_REM", "MoEEfficiency.js") + 2 * PAD,
                 jsConst(B_SRC, "BOX_H_REM", "MoEEfficiency.js") + 2 * PAD];
const HIT_PAD = Math.ceil(Math.max(SURFACE[0], SURFACE[1]) / 2);
const SHIFT = [PAD - jsConst(B_SRC, "BOX_LEFT_REM", "MoEEfficiency.js") + "rem",
               PAD - jsConst(B_SRC, "BOX_TOP_REM", "MoEEfficiency.js") + "rem"];
const HIT_MAGIC = jsConst(T_SRC, "HIT_MAGIC", "MoEBarTransient.js");
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
function mount(srcs, unsettled) {
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
    const document = {
        body,
        createElement: (tag) => new El(tag),
        getElementById: (id) => body.byId(id),
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
    const engine = { whenReady: { then: (fn) => fn() } };

    // requestAnimationFrame is injected for parity with the progress harness even though neither
    // this bar nor the transient ever calls it (the cold-only rAF is MoEProgress.js's alone -- see
    // its commitClimb). An unused global costs nothing and keeps the two mounts comparable.
    new Function("document", "viewEnv", "engine", "ModelObserver", "setTimeout", "clearTimeout",
                 "Date", "requestAnimationFrame", src)(
        document, viewEnv, engine, () => observer, clock.setTimeout, clock.clearTimeout,
        { now: clock.now }, clock.raf);

    const root = document.getElementById("moe-bar-root");
    const q = (sel) => root.querySelector(sel);
    const capC = q(".mp-cap.up");
    if (!unsettled) clock.advance(SETTLE);
    return {
        clock, calls, root, document, body, observer,
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
    eq("hit rect collapsed by half the larger dimension + WG's magic 5th arg",
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
}

S.main("MoEEfficiency.js + MoEBarTransient.js", MUTATIONS, run);
