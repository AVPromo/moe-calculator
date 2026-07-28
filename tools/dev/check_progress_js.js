/* check_progress_js.js -- headless behavioural self-check for MoEProgress.js (the in-battle
 * centre-screen progress bar's front-end). Plain Node, zero dependencies, zero framework.
 *
 *   node tools/dev/check_progress_js.js
 *   node tools/dev/check_progress_js.js --mutate=<key>     (anti-vacuity check, see MUTATIONS)
 *   node tools/dev/check_progress_js.js --list-mutations
 *
 * WHY THIS EXISTS. The bar lives in a res_map-registered Gameface WINDOW, which pins its
 * resources at client launch: there is NO hot-reload, so every JS timing hypothesis costs a full
 * client relaunch to test. MoEProgress.js is a wall-clock state machine (a 6200ms keyframe seeked
 * with negative animation-delay, a fallback end timer, an Alt peek that pauses the animation), and
 * that is exactly the kind of logic a virtual clock can prove on the desk.
 *
 * IT ASSERTS EMITTED VALUES, not "the file parsed". Per the repo lesson recorded as
 * `bar-tuner-selfcheck-is-not-a-gate` (gen_bar_tuner.ps1's -SelfCheck once passed
 * `"holdMs": true` because it only checked for leftover tokens), every check below reads a value
 * the module actually WROTE -- the viewEnv resize args, the animation-delay string, the run class,
 * animationPlayState, the fill width percentage, the caption text -- and compares it to an
 * expected literal.
 *
 * HOW IT LOADS THE MODULE. MoEProgress.js is an ES module whose only import is OpenWG's
 * ../../libs/model.js, which is NOT in this repo. Rather than stub a file tree and fight a loader,
 * the source is read as text, the import line is stripped, and the body is evaluated by
 * `new Function` with every engine global injected as a parameter: document, viewEnv, engine,
 * setTimeout/clearTimeout/Date (the virtual clock), requestAnimationFrame and ModelObserver. The
 * module is otherwise UNMODIFIED -- the real file is what runs.
 *
 * WHAT IS AND IS NOT COVERED. This exercises the module's LOGIC. It has no layout, no CSS, no
 * compositor: it cannot tell you the bar looks right, whether Coherent honours
 * animation-play-state (it does -- live-confirmed), or whether the engine's size-calculation
 * fallback still clobbers the surface. Those stay live-verification items. The static
 * HTML/CSS/Python mirror of the surface size is guarded separately by
 * tests/test_progress_surface_mirror.py.
 */
"use strict";

const fs = require("fs");
const path = require("path");

const WIDGET = path.join(__dirname, "..", "..", "src", "res", "gui", "gameface", "mods",
                         "14th_ua", "MoECalculator");

// Source mutations for the anti-vacuity check: each one breaks ONE real behaviour, and a run with
// it applied MUST fail. Keys are the -- keep them tiny and surgical.
const MUTATIONS = {
    // The bug this pass fixed: drop the fade-out re-arm, so Alt during the fade-out pauses the
    // animation part-way through it (the bar freezes at partial opacity).
    "no-fadeout-rearm": [
        "} else if (!peeking && Date.now() >= plateauAt + HOLD_MS) {",
        "} else if (false) {"],
    // The H2 guard: without the fallback timer a missing animationend wedges `showing` forever.
    "no-end-timer": [
        "endT = setTimeout(function () { endRun(id); }, TOTAL_MS - seekMs + END_MARGIN_MS);",
        "endT = null;"],
    // The Change-2 guard: no re-assert of the surface size after the engine's fallback deadline.
    // Drops ONLY the second push, leaving the surfaceSettled flip below it intact.
    "no-surface-reassert": [
        "        pushSurfaceSize();\n        setTimeout(function () {",
        "        setTimeout(function () {"],
    // The show triggers must WAIT for the re-assert: before it the surface is the engine's 256x256
    // fallback, which crops the composition (it spans document x 10..370) and -- because Python's
    // anchor conversion bakes in a 92-tall surface -- places the bar ~142px too high. Two halves,
    // two mutations, because only an Alt peek at battle start can reach the second one.
    "no-change-gate": ["} else if (changed && surfaceSettled) {", "} else if (changed) {"],
    "no-settle-gate": [
        "if (!peeking && surfaceSettled) peekOn();", "if (!peeking) peekOn();"],
    // ...and the flip must RE-RENDER the model already held, or an Alt held across the settle only
    // appears on the next Python push -- and during PREBATTLE there may not be one.
    "no-settle-rerender": ["            render(observer.model);", ""],
    // The warm re-trigger must NOT replay the entry from opacity 0.
    "warm-replays-entry": ["armRun(SEEK_PLATEAU);            // the seek", "armRun(SEEK_NONE); //"],
    // The hold-to-show guard: put back the bail this pass DELETED (peekOff returned unless the
    // plateau pause had already landed), so a sub-FADE_IN_MS tap serves the whole transient again --
    // the toggle-like behaviour that was the bug.
    "tap-runs-out": [
        "    const inLeft = Math.min(",
        '    if (root.style.animationPlayState !== "paused") return;\n    const inLeft = Math.min('],
    // A superseded run's animationend must not end the live run.
    "no-identity-guard": ['if (e.animationName !== RUN_NAMES[armIdx]) return;', ""],
    // The entry window must CARRY the previous committed sign: put a clear back into the !sw path
    // and a bar that was green blinks neutral for 600ms before re-committing.
    "entry-clears-sign": [
        "if (!sw) return;",
        'if (!sw) { [capV(capC), capDN, fill, tProj].forEach(function (e) {' +
        ' e.classList.remove("mp-up"); e.classList.remove("mp-down"); }); return; }'],
    // The glow must key off the delta AS ROUNDED, or a +0.4 shows a green "(+0)".
    "raw-sign-gate": ["const glows = Math.round(Math.abs(d)) !== 0;", "const glows = d !== 0;"],
    // THE DAMAGE-HOLD RESUME (dmgPlateauAt). Four surgical halves, because each one resurrects or
    // truncates a different show and only its own assertion can see it.
    // Drop the resume itself -> every release fades out, truncating any damage hold it interrupted.
    "no-resume-on-release": ["    if (dmgPlateauAt + HOLD_MS > Date.now()) {", "    if (false) {"],
    // The mid-peek refresh: warmShow does NOT armRun while peeking, so reading the (stale) peek
    // plateau instead of `now` gives the damage event a hold that started before it did.
    "peek-dmg-uses-stale-plateau": [
        "dmgPlateauAt = peeking ? Date.now() : plateauAt;", "dmgPlateauAt = plateauAt;"],
    // The record must die WITH `showing`, or a release resumes a show that is already off screen.
    // Two clears, two mutations: the animationend/timer end, and the hide/new-battle reset.
    "endrun-keeps-dmg-plateau": [
        "    dmgPlateauAt = 0;                // the hold is over",
        "    // dmgPlateauAt = 0;  // the hold is over"],
    "reset-keeps-dmg-plateau": [
        "    dmgPlateauAt = 0;                // ditto endRun",
        "    // dmgPlateauAt = 0;  // ditto endRun"],
};

// --- assertions -----------------------------------------------------------------------------
let passed = 0;
const failures = [];
let group = "";

function section(name) { group = name; }

function eq(what, actual, expected) {
    const a = JSON.stringify(actual), b = JSON.stringify(expected);
    if (a === b) { passed += 1; return; }
    failures.push(group + " / " + what + ": got " + a + ", want " + b);
}

function ok(what, cond) { eq(what, !!cond, true); }

// --- the minimal DOM ------------------------------------------------------------------------
// Only what MoEProgress.js touches: classList (incl. toggle's 2-arg force form), className, style
// as a plain bag, textContent, innerHTML (parsed so querySelector works), appendChild,
// getElementById, offsetWidth (the reflow read) and addEventListener("animationend").
class El {
    constructor(tag) {
        this.tag = tag;
        this.id = "";
        this.children = [];
        this.style = {};
        this.textContent = "";
        this._cls = [];
        this._handlers = {};
        const self = this;
        this.classList = {
            add(c) { if (self._cls.indexOf(c) < 0) self._cls.push(c); },
            remove(c) { self._cls = self._cls.filter((x) => x !== c); },
            contains(c) { return self._cls.indexOf(c) >= 0; },
            toggle(c, force) {
                const on = arguments.length > 1 ? !!force : !self.classList.contains(c);
                if (on) self.classList.add(c); else self.classList.remove(c);
                return on;
            },
        };
    }
    get className() { return this._cls.join(" "); }
    set className(v) { this._cls = String(v).split(/\s+/).filter(Boolean); }
    get offsetWidth() { return 0; }               // the forced-reflow read
    set innerHTML(html) { this.children = []; parseHTML(html, this); }
    appendChild(el) { this.children.push(el); return el; }
    querySelector(sel) {                          // only ".class" is ever used
        const want = sel.replace(/^\./, "");
        for (const child of this.children) {
            if (child.classList.contains(want)) return child;
            const hit = child.querySelector(sel);
            if (hit) return hit;
        }
        return null;
    }
    byId(id) {
        for (const child of this.children) {
            if (child.id === id) return child;
            const hit = child.byId(id);
            if (hit) return hit;
        }
        return null;
    }
    addEventListener(type, fn) { (this._handlers[type] = this._handlers[type] || []).push(fn); }
    dispatch(type, event) { (this._handlers[type] || []).forEach((fn) => fn(event)); }
}

// Tag-stack parser -- enough for the module's innerHTML and the view's own body markup. Text nodes
// are dropped: the only literal text in either is the "(" / ")" pair, which nothing queries.
function parseHTML(html, parent) {
    const re = /<\/?([a-z]+[a-z0-9]*)((?:"[^"]*"|[^>])*)>/gi;
    const stack = [parent];
    let m;
    while ((m = re.exec(html)) !== null) {
        if (m[0][1] === "/") { if (stack.length > 1) stack.pop(); continue; }
        if (/^(meta|link|br|img|input)$/i.test(m[1])) continue;   // void tags, never queried
        const el = new El(m[1].toLowerCase());
        const cls = /class="([^"]*)"/.exec(m[2]);
        const id = /id="([^"]*)"/.exec(m[2]);
        if (cls) el.className = cls[1];
        if (id) el.id = id[1];
        stack[stack.length - 1].appendChild(el);
        if (!/\/>$/.test(m[0])) stack.push(el);
    }
}

// --- the virtual clock ----------------------------------------------------------------------
// setTimeout / clearTimeout / Date.now / requestAnimationFrame, all driven by advance(ms). Frame
// callbacks flush on every advance, so a rAF-deferred write lands in a LATER turn than the class
// change that preceded it -- which is the whole point of the module's rAF.
function makeClock(start) {
    let now = start, seq = 0;
    const timers = new Map();
    let frames = [];
    const clock = {
        now: () => now,
        setTimeout(fn, ms) { seq += 1; timers.set(seq, { at: now + (Number(ms) || 0), fn }); return seq; },
        clearTimeout(id) { timers.delete(id); },
        raf(fn) { frames.push(fn); seq += 1; return seq; },
        flushFrames() { const due = frames; frames = []; due.forEach((fn) => fn()); },
        advance(ms) {
            const target = now + ms;
            for (;;) {
                clock.flushFrames();
                let pick = null;
                for (const [id, t] of timers) {
                    if (t.at > target) continue;
                    if (pick === null || t.at < timers.get(pick).at) pick = id;
                }
                if (pick === null) break;
                const t = timers.get(pick);
                timers.delete(pick);
                now = Math.max(now, t.at);
                t.fn();
            }
            now = target;
            clock.flushFrames();
        },
        pending() { return timers.size; },
    };
    return clock;
}

// --- mounting the real module ---------------------------------------------------------------
const SRC = fs.readFileSync(path.join(WIDGET, "MoEProgress.js"), "utf8");
const VIEW_HTML = fs.readFileSync(path.join(WIDGET, "MoEProgressView.html"), "utf8");

// --- the module's own constants, SCRAPED (never written down here) ---------------------------
// The surface size, the input-rect padding and the composition shift are derived below exactly as
// MoEProgress.js derives them. They used to be literals (480x92 / 240 / "90rem"), and the moment
// the track narrowed 300rem -> 200rem (BOX_W_REM 460 -> 360) three of them went stale and this
// shim went red -- while tests/test_progress_surface_mirror.py, which scrapes the same constants,
// stayed green through the same change. Same regex and same formulas as that test's _js_const /
// _surface_wh, so the two cannot disagree, and what is asserted is the RELATIONSHIP: a resize
// moves both sides together and only a broken derivation fails.
// SCRAPED FROM THE UNMUTATED SOURCE on purpose -- no mutation touches a constant.
function jsConst(name) {
    const m = new RegExp("^const " + name + " = (-?\\d+);", "m").exec(SRC);
    if (!m) throw new Error("MoEProgress.js: const " + name + " not found");
    return Number(m[1]);
}
const PAD = jsConst("PAD_REM");
const SURFACE = [jsConst("BOX_W_REM") + 2 * PAD, jsConst("BOX_H_REM") + 2 * PAD];
const HIT_PAD = Math.ceil(Math.max(SURFACE[0], SURFACE[1]) / 2);
const SHIFT = [PAD - jsConst("BOX_LEFT_REM") + "rem", PAD - jsConst("BOX_TOP_REM") + "rem"];
// The show gate's two timings, scraped for the same reason: they are TUNED numbers (the re-assert
// only has to land after the engine's observed ~2.2s clobber, the slack only after the resize's C++
// round-trip), so a retune must move this shim with them and not redden it.
const REASSERT = jsConst("SURFACE_REASSERT_MS");
const SETTLE = REASSERT + jsConst("SURFACE_SETTLE_MS");

// `unsettled` leaves the clock at mount time, i.e. BEFORE the re-assert flips surfaceSettled -- the
// state the surface section and the show gate below examine. Every other section wants a bar that is
// allowed to show, so by default the clock is run straight past the flip.
function mount(mutation, unsettled) {
    let src = SRC;
    if (mutation) {
        const [from, to] = MUTATIONS[mutation];
        if (src.indexOf(from) < 0) {
            failures.push("mutation '" + mutation + "' did not apply -- its anchor text is gone");
        }
        src = src.replace(from, to);
    }
    src = src.replace(/^import[^\n]*\n/m, "");            // OpenWG's libs/model.js is not in-repo

    // A REALISTIC EPOCH MAGNITUDE, not a small number: the module's `dmgPlateauAt == 0` means "no
    // damage hold in flight", which only reads as "long ago" while Date.now() > HOLD_MS. That is
    // unconditionally true in the client (epoch ms) but was only true here by 250ms of luck -- a
    // clock starting at 1000 sat BELOW HOLD_MS until the SETTLE advance, so trimming
    // SURFACE_REASSERT_MS would have reddened the peek sections for a reason the client cannot have.
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

    new Function("document", "viewEnv", "engine", "ModelObserver", "setTimeout", "clearTimeout",
                 "Date", "requestAnimationFrame", src)(
        document, viewEnv, engine, () => observer, clock.setTimeout, clock.clearTimeout,
        { now: clock.now }, clock.raf);

    const root = document.getElementById("moe-bar-root");
    const q = (sel) => root.querySelector(sel);
    if (!unsettled) clock.advance(SETTLE);
    return {
        clock, calls, root, document, body, observer,
        // A real ModelObserver updates .model and THEN notifies, and the surface-settle re-render
        // reads .model back -- so pushing has to do both, or that path sees a stale/empty model.
        push: (m) => { observer.model = m; render(m); },
        animEnd: (name) => root.dispatch("animationend", { animationName: name }),
        fill: q(".mp-fill"), capC: q(".mp-capC"), capL: q(".mp-capL"), capR: q(".mp-capR"),
        capP: q(".mp-capP"), proj: q(".mp-proj"),
        capCV: q(".mp-capC").querySelector(".mp-v"),
        capD: q(".mp-capC").querySelector(".mp-d"),
        capDN: q(".mp-capC").querySelector(".mp-d-num"),
        run: () => (root.classList.contains("mp-run") ? "mp-run"
                    : root.classList.contains("mp-run-b") ? "mp-run-b" : null),
    };
}

// A model with round axis arithmetic: lo 2450, hi 3050 -> width 600, so preAvg 2700 = 41.667% and
// projAvg 2750 = 50.000%. delta +50.
const BASE = { visible: true, hasData: true, marks: 1, axisLo: 2450, axisHi: 3050,
               preAvg: 2700, projAvg: 2750, altHeld: false };
const M = (extra) => Object.assign({}, BASE, extra);

// mp-life's stops, in ms into the run (0 / 9.68 / 90.32 / 100), SCRAPED for the same reason as the
// surface constants above: they are TUNED numbers owned by the tuner's timings JSON, so a retune
// must move this shim with them and not redden it. Only the two literals are scraped -- TOTAL and
// the fade-out seek are DERIVED here exactly as the module derives TOTAL_MS / SEEK_FADE_OUT from
// the same pair (FADE_OUT_MS == FADE_IN_MS), so a broken derivation is what fails.
const FADE_IN = jsConst("FADE_IN_MS"), HOLD = jsConst("HOLD_MS");
const TOTAL = FADE_IN + HOLD + FADE_IN, SEEK_FADE_OUT = FADE_IN + HOLD;
const SEEK_PLATEAU = FADE_IN;                       // == the module's own SEEK_PLATEAU
const MARGIN = jsConst("END_MARGIN_MS");

function run(mutation) {
    // --- the surface push, and the re-assert guard -----------------------------------------
    section("surface");
    let s = mount(mutation, true);              // stay before the re-assert: it is what is asserted
    eq("resizeViewRem called once at mount with the surface size", s.calls.resize, [SURFACE]);
    eq("hit rect collapsed by half the larger dimension + WG's magic 5th arg",
       s.calls.hit, [[HIT_PAD, HIT_PAD, HIT_PAD, HIT_PAD, 15]]);
    eq("texture frozen before the resize (WG's pattern)", s.calls.freeze, 1);
    eq("the composition is shifted into positive document coords",
       [s.root.style.left, s.root.style.top], SHIFT);
    ok("the static sizing box from the HTML is present", s.document.getElementById("moe-bar-box"));
    ok("the JS built its own root and did NOT adopt the sizing box",
       s.document.getElementById("moe-bar-box") !== s.root);
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
    s = mount(mutation, true);                  // still pre-re-assert
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
       "mp-run");
    eq("...as a peek entry already committed at proj_avg (not a pre->proj climb)",
       [s.fill.style.width, s.capCV.textContent], ["75.000%", "2,900"]);
    s.clock.advance(FADE_IN);
    eq("...and it pauses at the plateau like any other peek", s.root.style.animationPlayState,
       "paused");
    s = mount(mutation);                        // the default mount is already past the flip
    s.push(M());
    s.push(M({ altHeld: true }));
    eq("after the settle an Alt peek shows normally", s.run(), "mp-run");

    // --- the first push is a SILENT baseline ------------------------------------------------
    section("first push");
    s = mount(mutation);
    s.push(M());
    eq("shown", s.root.style.display, "");
    eq("no run armed -- the bar must not appear at battle start", s.run(), null);
    eq("settled straight at projAvg", s.fill.style.width, "50.000%");
    eq("the static pre_avg tick + caption are painted", s.capP.style.left, "41.667%");
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
    eq("run #1 uses the original identity", s.run(), "mp-run");
    eq("the entry plays from the top (no seek)", s.root.style.animationDelay, "0ms");
    eq("the numeral still reads pre_avg until the swap", s.capCV.textContent, "2,700");
    eq("the delta is faded out until the swap", s.capD.style.opacity, "0");
    // THE REWIND IDIOM: a cold show snaps the fill back to pre_avg with transitions off, then aims
    // it at the target in a LATER frame (rAF) so the transition actually runs.
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
    eq("re-armed on the ALTERNATE identity", s.run(), "mp-run-b");
    eq("seeked PAST the entry to the plateau -- no re-flash, no re-slide",
       s.root.style.animationDelay, "-" + FADE_IN + "ms");
    eq("the fill was NOT rewound: it moves from where it is to the new target",
       s.fill.style.width, "100.000%");
    ok("the axis-full class is set at the goalpost", s.root.classList.contains("mp-full"));

    // --- a STALE animationend from the superseded identity ---------------------------------
    section("stale animationend");
    s.animEnd("mp-life");
    eq("the superseded run's animationend is ignored", s.run(), "mp-run-b");
    s.animEnd("mp-life-b");
    eq("the LIVE run's animationend ends it", s.run(), null);
    eq("force-settled on proj_avg", s.capCV.textContent, "3,050");
    s.push(M({ projAvg: 2750 }));
    eq("a change after the run ended is a fresh COLD show", s.root.style.animationDelay, "0ms");

    // --- the H2 fallback: animationend never arrives ---------------------------------------
    section("end-timer fallback");
    s = mount(mutation);
    s.push(M());
    s.push(M({ projAvg: 2900 }));
    s.clock.advance(TOTAL + MARGIN);
    eq("the run ends on the fallback timer with no animationend at all", s.run(), null);
    s.push(M({ projAvg: 2960 }));
    eq("so the NEXT change still gets a cold show (not wedged 'showing')",
       s.root.style.animationDelay, "0ms");

    // --- ALT PEEK: hold ---------------------------------------------------------------------
    section("peek hold");
    s = mount(mutation);
    s.push(M());
    s.push(M({ altHeld: true }));
    eq("the peek cold-shows the bar (full entry)", s.root.style.animationDelay, "0ms");
    eq("not paused mid-fade-in", s.root.style.animationPlayState, "");
    s.clock.advance(FADE_IN);
    eq("paused once the entry completes", s.root.style.animationPlayState, "paused");
    s.clock.advance(60000);
    eq("a held peek NEVER ends -- the fallback timer must not end it either",
       [s.root.style.animationPlayState, s.run()], ["paused", "mp-run"]);
    eq("still visible", s.root.style.display, "");

    // --- ALT PEEK: release ------------------------------------------------------------------
    section("peek release");
    s.push(M({ altHeld: false }));
    eq("released -> unpaused", s.root.style.animationPlayState, "");
    eq("...and seeked straight to the fade-out stop", s.root.style.animationDelay,
       "-" + (FADE_IN + HOLD) + "ms");
    s.clock.advance(FADE_IN + MARGIN);
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
    s = mount(mutation);
    s.push(M());
    s.push(M({ altHeld: true }));
    s.clock.advance(TAP);                       // still mid-fade-in
    eq("precondition: the tap never reached the plateau pause",
       s.root.style.animationPlayState, "");
    s.push(M({ altHeld: false }));
    eq("the release is MIRRORED into the fade-out, not left to run out",
       s.root.style.animationDelay, "-" + TAP_SEEK + "ms");
    eq("...which means peekOff re-armed, so the identity flipped", s.run(), "mp-run-b");
    eq("...unpaused, with the stale pause timer dropped alongside it",
       s.root.style.animationPlayState, "");
    s.clock.advance(TOTAL - TAP_SEEK);          // the shortened remainder: only the mirrored fade-out
    eq("still armed and still unpaused through that remainder",
       [s.run(), s.root.style.animationPlayState], ["mp-run-b", ""]);
    s.clock.advance(MARGIN);
    eq("and it ended on the SHORT run's own timer -- gone " + (TOTAL - TAP_SEEK + MARGIN) +
       "ms after the release, not " + (TOTAL + MARGIN) + "ms after the press", s.run(), null);

    // --- THE NEW CASE: Alt pressed DURING the fade-out --------------------------------------
    // Symptom: the bar froze mid-transition at partial opacity instead of reappearing.
    section("alt during fade-out");
    s = mount(mutation);
    s.push(M());
    s.push(M({ projAvg: 2900 }));               // cold show
    s.clock.advance(FADE_IN + HOLD + 100);      // 5700ms in: 100ms INTO the fade-out
    eq("precondition: the run is still armed and unpaused (fading out)",
       [s.run(), s.root.style.animationPlayState], ["mp-run", ""]);
    s.push(M({ projAvg: 2900, altHeld: true }));
    eq("re-armed at the PLATEAU, not paused in place, and not a cold entry from opacity 0",
       s.root.style.animationDelay, "-" + FADE_IN + "ms");
    eq("on a fresh identity", s.run(), "mp-run-b");
    eq("unpaused by the re-arm", s.root.style.animationPlayState, "");
    s.clock.advance(0);                         // the pause callback is due immediately
    eq("pinned at full opacity", s.root.style.animationPlayState, "paused");
    s.clock.advance(60000);
    eq("and held indefinitely -- the superseded run's timer cannot end it",
       [s.root.style.animationPlayState, s.run()], ["paused", "mp-run-b"]);
    eq("the numeral is still the committed proj_avg", s.capCV.textContent, "2,900");
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("release still fades out exactly once", s.root.style.animationDelay,
       "-" + (FADE_IN + HOLD) + "ms");
    s.clock.advance(FADE_IN + MARGIN);
    eq("...and ends", s.run(), null);

    // --- re-show after a hide ---------------------------------------------------------------
    section("hide resets");
    s.push(M({ visible: false }));
    eq("hidden", s.root.style.display, "none");
    s.push(M({ projAvg: 3000 }));
    eq("the first push after a re-show is a silent baseline again", s.run(), null);

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
    // The pre-existing "peek release" section holds Alt for 60s, which is past any hold and so cannot
    // see that; hold just past the plateau instead, where a stale record would still be live.
    s = mount(mutation);
    s.push(M());
    s.push(M({ altHeld: true }));               // peek only -- no damage event anywhere in this case
    s.clock.advance(FADE_IN);
    eq("precondition: the peek reached its plateau pause", s.root.style.animationPlayState,
       "paused");
    s.clock.advance(HELD);
    s.push(M({ altHeld: false }));
    eq("a peek that interrupted no damage show still fades out plainly (inLeft == 0)",
       s.root.style.animationDelay, "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_IN + MARGIN);
    eq("...and is gone a fade-out after the release", s.run(), null);

    // (b) THE FIX ITSELF: Alt pressed mid-hold, released with hold still owed.
    s = mount(mutation);
    s.push(M());
    s.push(M({ projAvg: 2900 }));               // the damage-driven cold show
    const T0 = s.clock.now();
    const DMG_END = T0 + TOTAL + MARGIN;        // its own end: armRun(SEEK_NONE)'s endT, untouched
    s.clock.advance(PRESS);
    s.push(M({ projAvg: 2900, altHeld: true }));
    eq("precondition: a press mid-hold neither re-arms nor moves the run",
       [s.run(), s.root.style.animationDelay], ["mp-run", "0ms"]);
    s.clock.advance(0);                         // the pause is due immediately (already past FADE_IN)
    eq("precondition: pinned at the plateau", s.root.style.animationPlayState, "paused");
    s.clock.advance(HELD);
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("the release RESUMES the damage hold, seeked to its true elapsed position",
       s.root.style.animationDelay, "-" + (PRESS + HELD) + "ms");
    eq("...on a fresh identity, unpaused",
       [s.run(), s.root.style.animationPlayState], ["mp-run-b", ""]);
    at(s, T0 + PRESS + HELD + FADE_IN + MARGIN);
    eq("a plain fade-out's worth of time after the release it is STILL up -- that truncation was the "
       + "whole bug", s.run(), "mp-run-b");
    at(s, DMG_END - 1);
    eq("still up right up to the instant the untouched damage run would have ended", s.run(),
       "mp-run-b");
    at(s, DMG_END);
    eq("and it ends exactly THERE: neither truncated to the release nor handed a fresh hold",
       s.run(), null);

    // (c) A DAMAGE EVENT THAT ARRIVES *DURING* A PEEK. warmShow deliberately does NOT armRun while
    // peeking (the pause has to survive), so the event gets no run clock of its own -- without the
    // record being refreshed there it would be wiped a fade-out after the release. It must instead
    // last exactly as long as the warm re-trigger it could not arm. Note the peek sits PAST its own
    // plateau before the event, so "the event's instant" and "the peek's plateau" are distinguishable.
    s = mount(mutation);
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
       [s.run(), s.root.style.animationPlayState], ["mp-run", "paused"]);
    s.clock.advance(HELD);
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("the release resumes THAT event's hold, elapsed from the event and not from the peek",
       s.root.style.animationDelay, "-" + (SEEK_PLATEAU + HELD) + "ms");
    s.clock.advance(FADE_IN + MARGIN);
    eq("so the mid-peek event is not wiped a fade-out after the release", s.run(), "mp-run-b");
    at(s, WARM_END - 1);
    eq("it lasts exactly as long as the warm re-trigger it could not arm", s.run(), "mp-run-b");
    at(s, WARM_END);
    eq("...and ends there", s.run(), null);

    // (d) NO RESURRECTION. Three ways a damage hold dies -- it runs out, its animationend lands, or a
    // hide resets the widget -- and after any of them a release must take the PLAIN fade-out. The
    // record is the only state this pass added that could outlive the show it describes.
    // (d1) it simply ran out before the press. Guarded by arithmetic alone (a run's endT is always
    // FADE_OUT + END_MARGIN past its own hold expiry), so this half needs no clear -- assert it
    // anyway, because it is the case a player hits constantly.
    s = mount(mutation);
    s.push(M());
    s.push(M({ projAvg: 2900 }));
    s.clock.advance(TOTAL + MARGIN);
    eq("precondition: the damage run is over", s.run(), null);
    s.push(M({ projAvg: 2900, altHeld: true }));
    s.clock.advance(FADE_IN);
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("a release after the damage hold expired takes the plain fade-out",
       s.root.style.animationDelay, "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_IN + MARGIN);
    eq("...and stays gone", s.run(), null);

    // (d2) A HIDE (the scoreboard, or the arena ending) mid-hold, then a re-show and a peek -- with
    // the clock advancing only through the peek's own entry, so the record is still nominally LIVE and
    // its arithmetic cannot save us. reset() clearing it is the only thing that can, which is why this
    // is asserted rather than assumed.
    s = mount(mutation);
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
    s.clock.advance(FADE_IN + MARGIN);
    eq("...and gone", s.run(), null);

    // (d3) the run's animationend lands (the AUTHORITATIVE end -- the timer is only the H2 fallback),
    // so `showing` clears while the nominal hold still has wall-clock time on it. endRun has to clear
    // the record with it, or the next release resumes a show that is already off screen.
    s = mount(mutation);
    s.push(M());
    s.push(M({ projAvg: 2900 }));
    s.clock.advance(PRESS);
    s.animEnd("mp-life");                       // run #1's own identity
    eq("precondition: the run ended on its animationend, mid-hold", s.run(), null);
    s.push(M({ projAvg: 2900, altHeld: true }));
    s.clock.advance(FADE_IN);
    s.push(M({ projAvg: 2900, altHeld: false }));
    eq("an ended run's hold is not resumed either -- plain fade-out",
       s.root.style.animationDelay, "-" + SEEK_FADE_OUT + "ms");
    s.clock.advance(FADE_IN + MARGIN);
    eq("...and gone", s.run(), null);

    // (e) is the pre-existing "short tap" section above, unchanged and deliberately NOT duplicated
    // here: a sub-FADE_IN tap with no damage in flight must still take the mirrored seek
    // (SEEK_FADE_OUT + inLeft). It guards this pass for free -- a record that tracked the peek's own
    // arm would send that release down the resume branch and emit "-" + TAP + "ms" instead.

    // --- ROUNDED-ZERO CLASSIFICATION --------------------------------------------------------
    // The glow keys off the delta AS THE TEXT ROUNDS IT, so a sub-precision change can never
    // display "(+0)" in green. Untestable from tests/: it is a classList side effect on four DOM
    // nodes, reached only through the virtual clock's swap. Both signs, because the gate is
    // Math.round(Math.abs(d)) and NOT Math.round(d) -- the latter is -0 at d == -0.5 while the
    // text already reads "(-1)", so a naive round disagrees with the glyph at exactly one value.
    section("rounded-zero classification");
    s = mount(mutation);
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
    s = mount(mutation);
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
}

// --- main -----------------------------------------------------------------------------------
const arg = process.argv.slice(2).join(" ");
if (/--list-mutations/.test(arg)) {
    console.log(Object.keys(MUTATIONS).join("\n"));
    process.exit(0);
}
const mutation = (/--mutate=([\w-]+)/.exec(arg) || [])[1] || null;
if (mutation && !MUTATIONS[mutation]) {
    console.error("unknown mutation '" + mutation + "'; --list-mutations to see them");
    process.exit(2);
}

run(mutation);

const label = mutation ? "MUTATED (" + mutation + ")" : "MoEProgress.js";
if (failures.length) {
    console.log(failures.map((f) => "  FAIL  " + f).join("\n"));
    console.log("\n" + label + ": " + failures.length + " failed, " + passed + " passed");
    // A mutated run is SUPPOSED to fail -- exit 0 so it can be scripted, but say so loudly.
    process.exit(mutation ? 0 : 1);
}
console.log(label + ": " + passed + " assertions passed");
if (mutation) {
    console.log("!! VACUOUS: the mutation broke nothing. Add a check that catches it.");
    process.exit(1);
}
