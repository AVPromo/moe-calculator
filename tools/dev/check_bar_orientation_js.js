/* check_bar_orientation_js.js -- headless behavioural self-check for the VERTICAL orientation path
 * shared by MoEProgress.js and MoEEfficiency.js (mod_settings.progress_bar_orientation, pushed as
 * the VM's `vertical`), plus its two-thirds in the shared MoEBarTransient.js.
 *
 * WHY THIS EXISTS SEPARATELY FROM check_progress_js.js / check_efficiency_js.js. Both of those
 * gates' 400+ assertions read literals spelled ".mp-*" -- the horizontal path's own class prefix.
 * The vertical port added a one-line ns() rewriter that turns those same literals into the LIVE
 * prefix at runtime, so every existing assertion in the two horizontal gates stayed green through
 * the whole port and verified NOTHING about the vertical branch: goVertical(), the V_MARKUP DOM,
 * the vertical surface push, the orientation profile (PFX/AX/GROW/CAP_C_AX) and the mpv-run/mev-run
 * identity pair. This file is that missing coverage, sharing the same zero-dependency Node harness
 * (tools/dev/lib/gf_check_shim.js) the two horizontal gates use.
 *
 *   node tools/dev/check_bar_orientation_js.js
 *   node tools/dev/check_bar_orientation_js.js --mutate=<key>
 *   node tools/dev/check_bar_orientation_js.js --probe-all
 *   node tools/dev/check_bar_orientation_js.js --list-mutations
 *
 * THE ONE HARNESS TWIST THIS FILE ADDS: `window.model` (observer.model) starts EMPTY and is only
 * populated the instant engine.whenReady resolves -- mirroring the real client, where the module's
 * top-level code runs before the engine has populated the view's model. This is what makes "the
 * vertical flag is read INSIDE engine.whenReady, not at module scope"
 * (memory `model-vertical-must-be-read-inside-whenready`) a real, catchable regression here rather
 * than an unverifiable code-review-only claim: a hypothetical hoist of the read to module scope
 * would see the pre-populated {} and always mount horizontal, which the "vertical DOM build"
 * sections below would then catch.
 *
 * WHAT IS AND IS NOT COVERED. Module LOGIC only, exactly like the two horizontal gates -- no
 * layout, no CSS, no compositor, no live client. See their own headers for that boundary; it holds
 * here unchanged.
 */
"use strict";

const S = require("./lib/gf_check_shim.js");
const { section, eq, ok, fail, El, parseHTML, makeClock, makeRootFont,
        jsConst, jsArray, jsFactor, applyMutation, main } = S;

// A mutation that guts goVertical()'s markup swap makes the SOURCE's own follow-on querySelector
// chain throw (a null .mpv-capC has no .querySelector) -- a real crash, not a wrong value, and a
// perfectly valid way for a mutation to be caught. Recording it as a FAILED ASSERTION (rather than
// letting the exception escape and kill the whole run) is what makes --probe-all's exit-code-based
// classification see it as "caught" instead of misreading the crash as vacuous.
function safely(what, fn) {
    try { return fn(); } catch (e) { fail(what + ": THREW -- " + e.message); return null; }
}

const T_SRC = S.read("MoEBarTransient.js");
const P_SRC = S.read("MoEProgress.js");
const E_SRC = S.read("MoEEfficiency.js");
const P_VIEW = S.read("MoEProgressView.html");
const E_VIEW = S.read("MoEEfficiencyView.html");

// [WHICH, from, to] -- WHICH is "T" (shared transient), "P" (MoEProgress.js) or "E"
// (MoEEfficiency.js). Every anchor below is unique within its own file (applyMutation replaces the
// FIRST match only), so each is quoted with enough surrounding context to not collide with the
// file's own non-vertical declarations of the same identifier.
const MUTATIONS = {
    // ===== the SHARED transient's orientation switch ==========================================
    "vertical-never-adopted": ["T",
        "if (cfg.vert && observer.model && observer.model.vertical === true) goVertical();",
        "if (false) goVertical();"],
    // THE FAIL-SOFT DIRECTION: an absent/undefined `vertical` (a pre-push frame, an old fixture)
    // must stay horizontal -- `!== false` would flip a model that never carries the field at all.
    "vertical-fail-soft-wrong-direction": ["T",
        "observer.model.vertical === true", "observer.model.vertical !== false"],
    "vertical-box-not-adopted": ["T",
        "cfg.boxW = cfg.vert.box[2];", "cfg.boxW = cfg.boxW;"],
    // The vertical composition's own X slack. Only the Moving Average bar supplies one, and
    // without it its right-anchored captions are CLIPPED by the surface (they grow leftward past
    // .mpv-backdrop by design). Falling back to `pad` here is the shipped bug, not a fail-soft.
    "vertical-padx-not-adopted": ["T",
        "cfg.padX = cfg.vert.padX || cfg.pad;", "cfg.padX = cfg.pad;"],
    "vertical-run-class-not-switched": ["T",
        "runCls = RUN_CLASSES_V[cfg.vert.cls] || RUN_CLASSES;", "runCls = RUN_CLASSES;"],
    "vertical-run-name-not-switched": ["T",
        "runNames = RUN_NAMES_V[cfg.vert.cls] || RUN_NAMES;", "runNames = RUN_NAMES;"],
    "vertical-scope-class-not-added": ["T",
        "document.body.classList.add(cfg.vert.cls);", "void 0;"],

    // ===== MoEProgress.js's own goVertical() half ==============================================
    "p-markup-not-swapped": ["P", "root.innerHTML = V_MARKUP;\n    fill = root.querySelector(\".mpv-fill\");",
        "fill = root.querySelector(\".mpv-fill\");"],
    "p-axis-not-flipped": ["P", 'AX = "bottom";\n    GROW = "height";', 'AX = "left";\n    GROW = "height";'],
    "p-grow-not-flipped": ["P", 'AX = "bottom";\n    GROW = "height";', 'AX = "bottom";\n    GROW = "width";'],
    "p-capc-ax-not-nulled": ["P", "CAP_C_AX = null;", 'CAP_C_AX = "left";'],
    // Kills the stacked-row layout outright: re-merges the eta group back into ONE row with the
    // requirement group (the pre-split shape), so the DOM-order assertions above must catch it --
    // proving they are the real gate on the split, not a stale check of a shape no longer built.
    // The anchor is the RAW SOURCE of V_MARKUP's two adjacent string-literal lines (quote + ` +` +
    // newline + indent between them), not their evaluated/concatenated runtime value.
    "p-eta-row-not-split": ["P",
        '\'<div class="mpv-cap mpv-capEta"><span class="mpv-eta"></span><i class="mpv-ico battles"></i></div>\' +\n' +
        '        \'<div class="mpv-cap mpv-capR"><span class="mpv-v"></span><i class="mpv-ico none"></i></div>\' +',
        '\'<div class="mpv-cap mpv-capR"><span class="mpv-eta"></span><i class="mpv-ico battles"></i>\' +\n' +
        '        \'<span class="mpv-v"></span><i class="mpv-ico none"></i></div>\' +'],

    // ===== MoEEfficiency.js's own goVertical() half =============================================
    "e-markup-not-swapped": ["E", "root.innerHTML = V_MARKUP;\n    fill = root.querySelector(\".mev-fill\");",
        "fill = root.querySelector(\".mev-fill\");"],
    "e-axis-not-flipped": ["E", 'AX = "bottom";\n    GROW = "height";', 'AX = "left";\n    GROW = "height";'],
    "e-grow-not-flipped": ["E", 'AX = "bottom";\n    GROW = "height";', 'AX = "bottom";\n    GROW = "width";'],
    "e-capc-ax-not-nulled": ["E", "CAP_C_AX = null;", 'CAP_C_AX = "left";'],
};

// --- scraped constants (never written down as literals here -- see the two horizontal gates) ----
const SIZE_F = jsFactor(T_SRC, "SIZE_F", "MoEBarTransient.js");
const SIZE_XF = jsFactor(T_SRC, "SIZE_XF", "MoEBarTransient.js");
const REASSERT = jsConst(T_SRC, "SURFACE_REASSERT_MS", "MoEBarTransient.js");
const SETTLE = REASSERT + jsConst(T_SRC, "SURFACE_SETTLE_MS", "MoEBarTransient.js");
const FADE_IN = jsConst(T_SRC, "FADE_IN_MS", "MoEBarTransient.js");
const RUN_CLASSES_V = { mpv: ["mpv-run", "mpv-run-b"], mev: ["mev-run", "mev-run-b"] };
const RUN_NAMES_V = { mpv: ["mpv-life", "mpv-life-b"], mev: ["mev-life", "mev-life-b"] };
const RUN_NAMES_H = jsArray(T_SRC, "RUN_NAMES", "MoEBarTransient.js");

function vBox(src, where) {
    const PAD = jsConst(src, "PAD_REM", where);
    const left = jsConst(src, "V_BOX_LEFT_REM", where);
    const top = jsConst(src, "V_BOX_TOP_REM", where);
    const w = jsConst(src, "V_BOX_W_REM", where);
    const h = jsConst(src, "V_BOX_H_REM", where);
    const clipB = jsConst(src, "V_CLIP_B_REM", where);
    // THE X SLACK IS PER COMPOSITION and only ONE of the two vertical bars declares its own:
    // the Moving Average captions are right-anchored and grow LEFTWARD past .mpv-backdrop, so its
    // surface needs V_PAD_X_REM to stop clipping them, while the Damage Efficiency composition
    // stays four-sided-uniform. Absent -> PAD, which is exactly MoEBarTransient's own fallback, so
    // the efficiency expectations below are byte-identical to what they were. ONE value for both
    // sides, so the surface stays concentric with the track -- see V_PAD_X_REM's own note.
    const padX = /^const V_PAD_X_REM = /m.test(src) ? jsConst(src, "V_PAD_X_REM", where) : PAD;
    // THE RIGHT (minimap-facing) PAD is its OWN, separate knob now -- both vertical bars declare
    // one, so they clip the backdrop's decorative bleed short of the invisible surface's minimap-
    // facing edge instead of padding it symmetrically (see each bar's own V_PAD_XR_REM note).
    // Absent -> padX, MoEBarTransient's own fallback (a composition that never supplies one stays
    // symmetric, byte-identical to the old `2 * padX` formula).
    const padXR = /^const V_PAD_XR_REM = /m.test(src) ? jsConst(src, "V_PAD_XR_REM", where) : padX;
    const padXRLarge = /^const V_PAD_XR_REM_LARGE = /m.test(src)
        ? jsConst(src, "V_PAD_XR_REM_LARGE", where) : padXR;
    return {
        surface: [w + padX + padXR, h + 2 * PAD - clipB],
        shiftX: padX - left + "rem", shiftY: PAD - top + "rem",
        lgSurface: [Math.round((w * SIZE_XF + padX + padXRLarge) * SIZE_F),
                    Math.round((h + 2 * PAD - clipB) * SIZE_F)],
    };
}
const P_V = vBox(P_SRC, "MoEProgress.js");
const E_V = vBox(E_SRC, "MoEEfficiency.js");

// --- the harness ------------------------------------------------------------------------------
// `bar` is "P" or "E". `model` is the FULL model the view should see once engine.whenReady resolves
// -- see the header's note on why observer.model starts empty and is only populated there.
function mount(bar, srcs, model, unsettled) {
    const body = S.concatModules([srcs.T, bar === "P" ? srcs.P : srcs.E]);
    const VIEW_HTML = bar === "P" ? P_VIEW : E_VIEW;
    const clock = makeClock(1e12);
    const bodyEl = new El("body");
    parseHTML(VIEW_HTML.replace(/<!--[\s\S]*?-->/g, ""), bodyEl);
    const { documentElement, getComputedStyle, win } = makeRootFont(2, false);
    const document = Object.assign({
        body: bodyEl, documentElement,
        createElement: (tag) => new El(tag),
        getElementById: (id) => bodyEl.byId(id),
    }, S.makeDocumentEvents ? S.makeDocumentEvents() : {});
    const calls = { resize: [] };
    const viewEnv = {
        resizeViewRem(w, h) { calls.resize.push([w, h]); },
        setHitAreaPaddingsRem() {},
        freezeTextureBeforeResize() {},
    };
    let render = null;
    // See the file header: model starts empty, and is only swapped in the instant whenReady fires.
    const observer = { model: {}, onUpdate(fn) { render = fn; }, subscribe() {} };
    const engine = { whenReady: { then(fn) { observer.model = model; fn(); } }, on() {} };

    new Function("document", "viewEnv", "engine", "ModelObserver", "setTimeout", "clearTimeout",
                 "Date", "requestAnimationFrame", "getComputedStyle", "window", body)(
        document, viewEnv, engine, () => observer, clock.setTimeout, clock.clearTimeout,
        { now: clock.now }, clock.raf, getComputedStyle, win);

    const root = document.getElementById("moe-bar-root");
    if (!unsettled) clock.advance(SETTLE);
    return {
        clock, calls, root, document, observer,
        push: (m) => { observer.model = m; render(m); },
        animEnd: (name) => root.dispatch("animationend", { animationName: name }),
        run: (cls) => (root.classList.contains(cls[0]) ? cls[0] : root.classList.contains(cls[1]) ? cls[1] : null),
    };
}

const BASE_P = { visible: true, hasData: true, marks: 1, axisLo: 100, axisHi: 200,
                 preAvg: 120, projAvg: 150, etaBattles: 5, altHeld: false };
const BASE_E = { visible: true, hasData: true, damage: 1500, barX: 37.5, band: 1,
                 r65: 1000, r85: 2000, r95: 3000, r100: 4000, altHeld: false, battleEpoch: 1 };

function run(mutation) {
    const srcs = applyMutation({ T: T_SRC, P: P_SRC, E: E_SRC }, mutation, MUTATIONS);

    for (const [bar, base, V, mpfx] of [["P", BASE_P, P_V, "mpv"], ["E", BASE_E, E_V, "mev"]]) {
      safely(bar + " (uncaught exception during this bar's section)", () => {
        const model = Object.assign({}, base, { vertical: true });

        section(bar + ": vertical DOM build");
        let s = mount(bar, srcs, model);
        ok(bar + ": the vertical root exists", s.root);
        ok(bar + ": the vertical fill exists", s.root?.querySelector("." + mpfx + "-fill"));
        eq(bar + ": the horizontal fill is GONE -- V_MARKUP replaced MARKUP, not appended",
           s.root?.querySelector(".mp-fill") || null, null);
        ok(bar + ": the vertical scope class landed on the body", s.document.body.classList.contains(mpfx));

        // P's capR is now TWO STACKED ROWS, not one (maintainer's call: "move the ETA on top of
        // the next mark requirement" -- ported here only; the horizontal .mp-capR and the E bar's
        // own .mev-capR are untouched). Nothing else in this file or check_progress_js.js pins
        // V_MARKUP's capR/capEta shape, so a re-merge or a reorder here is otherwise invisible.
        // FAMILY only (not the exact className -- this mount already pushed BASE_P, so the mark
        // icon and eta numeral carry live variant/sign classes, not their markup-literal ones).
        if (bar === "P") {
            const capR = s.root.querySelector(".mpv-capR");
            const capEta = s.root.querySelector(".mpv-capEta");
            const family = (c) => c.classList.contains("mpv-eta") ? "eta"
                : c.classList.contains("battles") ? "battles-icon"
                : c.classList.contains("mpv-v") ? "v"
                : c.classList.contains("mpv-ico") ? "other-icon" : "?";
            eq(bar + ": .mpv-capEta's DOM order is [eta][battles icon], stacked above capR",
               capEta && capEta.children.map(family).join("|"), "eta|battles-icon");
            eq(bar + ": .mpv-capR's DOM order is [requirement][mark icon], with NO eta group left",
               capR && capR.children.map(family).join("|"), "v|other-icon");
        }

        section(bar + ": horizontal DOM build is unaffected (regression guard)");
        let h = mount(bar, srcs, Object.assign({}, base));  // no `vertical` field at all
        ok(bar + ": the horizontal fill exists", h.root.querySelector(".mp-fill"));
        eq(bar + ": no vertical scope class leaks onto a horizontal mount",
           h.document.body.classList.contains(mpfx), false);

        section(bar + ": vertical surface push + post-deadline re-assert");
        s = mount(bar, srcs, model, true);   // stay BEFORE the re-assert -- that is what is asserted
        eq(bar + ": the mount-time push already uses the VERTICAL surface, not 256x256/horizontal",
           s.calls.resize[0], V.surface);
        eq(bar + ": the rigid shift matches the vertical composition",
           [s.root.style.left, s.root.style.top], [V.shiftX, V.shiftY]);
        s.clock.advance(REASSERT);
        eq(bar + ": THE RE-ASSERT pushes the VERTICAL surface again, not the engine's 256x256 default",
           s.calls.resize[s.calls.resize.length - 1], V.surface);

        section(bar + ": vertical surface push, Large size mode");
        s = mount(bar, srcs, Object.assign({}, model, { barSize: 1 }));
        eq(bar + ": Large vertical surface carries both SIZE_F and SIZE_XF, on the vertical box",
           s.calls.resize[s.calls.resize.length - 1], V.lgSurface);

        section(bar + ": orientation profile (PFX/AX/GROW/CAP_C_AX)");
        s = mount(bar, srcs, model);
        const fill = s.root.querySelector("." + mpfx + "-fill");
        const capC = s.root.querySelector("." + mpfx + "-capC");
        // AX's own readout: the moving TICK (proj for the progress bar, cur for efficiency) --
        // fill/capC alone cannot tell "AX" (a marker's position property) apart from "GROW" (the
        // fill's growth property), since a capC-null / fill-height check is silent on AX specifically.
        const tick = bar === "P" ? s.root.querySelector(".mpv-proj")
                                  : s.root.querySelector(".mev-tick.mev-cur");
        ok(bar + ": (precondition) the vertical fill/capC/tick exist", fill && capC && tick);
        s.push(Object.assign({}, model, bar === "P" ? { projAvg: 180 } : { damage: 2500 }));
        ok(bar + ": the fill grows on height, not width", fill?.style.height && !fill?.style.width);
        ok(bar + ": the moving tick rides `bottom`, not `left` (AX)", tick?.style.bottom && !tick?.style.left);
        eq(bar + ": the bottom-centre caption is NOT positioned (a static cap, CAP_C_AX == null)",
           [capC?.style.bottom, capC?.style.left], [undefined, undefined]);

        section(bar + ": run identity follows the orientation");
        s = mount(bar, srcs, model, true);
        s.clock.advance(SETTLE);                              // let the settle re-render land
        s.push(Object.assign({}, model, bar === "P" ? { projAvg: 190 } : { damage: 2600 }));
        eq(bar + ": a vertical show arms the VERTICAL run class, never the horizontal mp-run",
           s.run(RUN_CLASSES_V[mpfx]), RUN_CLASSES_V[mpfx][0]);
        eq(bar + ": ...and never mp-run either", s.run(["mp-run", "mp-run-b"]), null);
        // The twin -b alternation must still restart a run under the vertical identity pair too: a
        // second, later change while the first run is still up must flip to the OTHER of the two.
        s.clock.advance(FADE_IN);
        s.push(Object.assign({}, model, bar === "P" ? { projAvg: 199 } : { damage: 2700 }));
        eq(bar + ": a second change re-arms on the OTHER vertical identity (the debounce twin)",
           s.run(RUN_CLASSES_V[mpfx]), RUN_CLASSES_V[mpfx][1]);

        section(bar + ": the animationend name filter follows the orientation");
        s = mount(bar, srcs, model, true);
        s.clock.advance(SETTLE);
        s.push(Object.assign({}, model, bar === "P" ? { projAvg: 190 } : { damage: 2600 }));
        s.animEnd(RUN_NAMES_H[0]);   // the HORIZONTAL keyframe's name -- must be a stale no-op here
        eq(bar + ": a stale horizontal animationend name is ignored on a vertical run",
           s.run(RUN_CLASSES_V[mpfx]), RUN_CLASSES_V[mpfx][0]);
        s.animEnd(RUN_NAMES_V[mpfx][0]);   // the matching VERTICAL keyframe's own name
        eq(bar + ": the matching vertical animationend name ends the run",
           s.run(RUN_CLASSES_V[mpfx]), null);
      });
    }
}

main("orientation (vertical path, both bars)", MUTATIONS, run);
