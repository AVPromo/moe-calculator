/* check_bar_vertical.js -- the drift gate on gen_bar_tuner_vertical.ps1's own JS logic.
 *
 *   node tools/dev/check_bar_vertical.js
 *
 * -SelfCheck on the generator only asserts file size + no leftover __TOKEN__s (plus, since this
 * variant, the .mpv- prefix / minimap table / mmGap+mmGapBottom defaults) -- none of that proves
 * the EMITTED VALUES are right (bar-tuner-selfcheck-is-not-a-gate). So this regenerates a real
 * (non-selfcheck) tuner HTML into a scratch file, evaluates its <script> block the same way the
 * generator's own -EmitCss driver does (vm + a minimal DOM shim, in the idiom of
 * tools/dev/lib/gf_check_shim.js), and asserts against the REAL top-level functions/state the
 * script defines:
 *   - the minimap placement math (barRightPx/barBottomPx) at two mmIdx values, including the
 *     (tickW-trackW)/2 outer-edge-overhang term on the right inset and mmGapBottom on the bottom
 *   - the fill/ticks are bottom-anchored (CSS text, not just "the file is big")
 *   - the caption reassignment: capC (bottom) carries projAvg + the delta LEFT of the numeral,
 *     capP (left) tracks the PRE tick (not proj) and shows preAvg
 *   - numeral-before-icon DOM order in every caption
 *   - .mpv-capP's clamp holds at both axis extremes (pct 0 and pct 100)
 *
 * It also scans the tuner's own <style> block (a rename-miss class can leave a selector matching
 * nothing while every emit-only assertion above stays green -- see the sibling efficiency
 * tuner's shipped bug) and regenerates the -Artifact variant to assert it is actually
 * publishable: no <!DOCTYPE>/<html>/<head>/<body> skeleton tags, under 16 MB, zero real
 * external-host references (http(s)://, fetch(, XMLHttpRequest, @import, protocol-relative //)
 * once the base64 asset payloads are stripped out of the scan, and no local machine/path leakage.
 */
"use strict";
const fs = require("fs");
const path = require("path");
const os = require("os");
const vm = require("vm");
const { execFileSync } = require("child_process");
const assert = require("assert");

const REPO = path.join(__dirname, "..", "..");
const GEN = path.join(__dirname, "gen_bar_tuner_vertical.ps1");
// PID-qualified: two concurrent runs on a FIXED name unlink each other's file mid-run (ENOENT on
// the unlink below, or worse a half-written read).
const tmpHtml = path.join(os.tmpdir(), "check_bar_vertical_tuner." + process.pid + ".html");

// Regenerate a fresh, real (non-selfcheck) tuner HTML -- self-sufficient, no ordering dependency
// on a prior manual run.
execFileSync("pwsh", ["-NoProfile", "-File", GEN, "-Out", tmpHtml], { cwd: REPO, encoding: "utf8" });
const html = fs.readFileSync(tmpHtml, "utf8");

// --- minimal DOM shim (same idiom as the generator's own -EmitCss driver / gf_check_shim.js) ----
const El = () => {
    const sm = {};
    const e = {
        children: [], _sel: {}, className: "", textContent: "", innerHTML: "", value: "", dataset: {},
        offsetWidth: 60, checked: false, files: [],
        style: new Proxy({ setProperty: (k, v) => { sm[k] = v; } }, {
            set(t, k, v) { sm[k] = v; return true; },
            get(t, k) { return k in t ? t[k] : sm[k]; },
        }),
        classList: {
            _s: new Set(),
            add(...c) { c.forEach((x) => this._s.add(x)); },
            remove(...c) { c.forEach((x) => this._s.delete(x)); },
            toggle(c, f) { (f === undefined ? !this._s.has(c) : f) ? this._s.add(c) : this._s.delete(c); },
            contains(c) { return this._s.has(c); },
        },
        addEventListener(t, f) { (e._ev = e._ev || {})[t] = f; },
        appendChild(c) { e.children.push(c); return c; },
        querySelector(s) { return e._sel[s] || (e._sel[s] = El()); },
        querySelectorAll() { return []; },
    };
    return e;
};
const byId = {};
const ctx = {
    document: {
        head: El(), body: El(), documentElement: El(), createElement: El,
        querySelectorAll: () => [], getElementById: (id) => byId[id] || (byId[id] = El()),
    },
    navigator: { clipboard: { writeText: () => {} } },
    requestAnimationFrame: (f) => f(), setTimeout: () => 0, clearTimeout: () => {},
    FileReader: function () { this.readAsDataURL = () => {}; },
    console, JSON, Math, Object, String, Number, parseFloat, parseInt, isNaN, Array,
};
ctx.window = ctx;

const m = html.match(/<script>([\s\S]*)<\/script>/);
assert.ok(m, "no <script> block in the generated tuner HTML");
vm.runInContext(m[1], vm.createContext(ctx), { filename: "tuner_vertical.js" });

let failed = 0, passed = 0;
function check(what, cond) {
    if (cond) { passed += 1; return; }
    failed += 1;
    console.log("  FAIL  " + what);
}

// --- schema defaults, captured BEFORE any test mutates st (else the check is trivial) ---------
check("mmGap default is 8", ctx.st.mmGap === 8);
check("mmGapBottom default is 30 (maintainer-tuned)", ctx.st.mmGapBottom === 30);
check("trackW default is 3 (== shipped horizontal cross-axis thickness)", ctx.st.trackW === 3);
["tickWEnd", "tickWPre", "tickWProj"].forEach((k) =>
    check(k + " default is 9 (== shipped horizontal tick cross-length)", ctx.st[k] === 9));
["tickHEnd", "tickHPre", "tickHProj"].forEach((k) =>
    check(k + " default is 2 (== shipped horizontal tick along-axis thickness)", ctx.st[k] === 2));
["tickXEnd", "tickXPre", "tickXProj"].forEach((k) =>
    check(k + " default is 0 (residual nudge, no compensation needed at defaults)", ctx.st[k] === 0));
// capxR/capxC are maintainer-tuned, non-zero PER-GROUP GEOMETRY (mirrors the efficiency sibling's
// own r4/current outcome: captions anchored ABOVE/BELOW the track need a constant rightward push
// off the shared left-of-track line, while the tick-adjacent caption sits near 0) -- a non-zero
// residual is not itself evidence of a broken anchor; capxP (beside the pre tick) stays 0.
check("capxR default is 14 (maintainer-tuned, per-group geometry)", ctx.st.capxR === 14);
check("capxC default is 16 (maintainer-tuned, per-group geometry)", ctx.st.capxC === 16);
check("capxP default is 0 (tick-adjacent caption needs no push)", ctx.st.capxP === 0);

// --- THE TELL FOR A BROKEN ANCHOR is not whether a residual is non-zero, but whether its value
// is a FUNCTION of the caption's own content width. Read the generator's SOURCE directly (the
// strongest possible proof -- not just "behaviour looks isolated") and confirm capxR/capxC/capxP
// are composed as plain scalar concatenations (st.capxR+"rem" etc.), with no offsetWidth /
// getBoundingClientRect / box-width read anywhere near the term.
{
    const genSrc = fs.readFileSync(GEN, "utf8");
    ["capxR", "capxC", "capxP"].forEach((k) => {
        const needle = "st." + k + '+"rem'; // the JS template's "rem" string often continues (e.g. "rem);...") rather than closing right after "rem"
        const hits = genSrc.split(needle).length - 1;
        check(k + " is composed as a plain constant (" + needle + ") in the source, found " +
            hits + " occurrence(s)", hits >= 1);
    });
    check("no offsetWidth/getBoundingClientRect read anywhere near a capx* term (source-level)",
        !/capx[RCP][^\n]*(offsetWidth|getBoundingClientRect)|(offsetWidth|getBoundingClientRect)[^\n]*capx[RCP]/
            .test(genSrc));
}
check("barH default is 200 (== shipped horizontal along-axis length)", ctx.st.barH === 200);

// --- placement math: barRight = stageW - mmSize - gap - (tickW-trackW)/2, at two mmIdx values --
// The clearance origin is the tick's OUTER edge (it overhangs the track), not the track's own
// edge -- see the .mpv-anchor comment in the generator. tickWEnd/Pre/Proj are all 9 by default,
// so halfOverhang()'s max-of-three collapses to the same single value the old shared knob gave.
const MM_SIZES = [228, 279, 329, 409, 510, 628];
ctx.st.tickWEnd = 9; ctx.st.tickWPre = 9; ctx.st.tickWProj = 9;
ctx.st.trackW = 3;
const overhang = (9 - 3) / 2;
[0, 5].forEach((idx) => {
    ctx.st.mmIdx = idx;
    ctx.st.stageW = 1920;
    ctx.st.mmGap = 8;
    const expected = 1920 - MM_SIZES[idx] - 8 - overhang;
    check("barRightPx() at mmIdx=" + idx + " includes the tick-overhang term", ctx.barRightPx() === expected);
});
ctx.st.stageH = 1080;
ctx.st.mmGapBottom = 8;
check("barBottomPx() == stageH - mmGapBottom", ctx.barBottomPx() === 1080 - 8);

// --- fill/ticks are bottom-anchored (CSS text, not just file size) ---------------------------
const cssBlock = (m2 => { assert.ok(m2, "no <style> block"); return m2[1]; })(html.match(/<style>([\s\S]*)<\/style>/));
check(".mpv-fill is bottom-anchored (bottom:0)", /\.mpv-fill\{[^}]*bottom:0\b/.test(cssBlock));
check(".mpv-fill has no left/width-only positioning left over from the horizontal bar",
    /\.mpv-fill\{[^}]*height:0\b/.test(cssBlock));
check(".mpv-end.mpv-bottom sits at bottom:0", /\.mpv-bottom\{bottom:0\}/.test(cssBlock));
check(".mpv-end.mpv-top sits at bottom:100%", /\.mpv-top\{bottom:100%\}/.test(cssBlock));
// Per-tick-type geometry: width/height/transform moved off the shared .mpv-tick base rule onto
// each of .mpv-end/.mpv-pre/.mpv-proj, so each carries its OWN translate(-50%,50%) centring.
["mpv-end", "mpv-pre", "mpv-proj"].forEach((cls) => {
    check("." + cls + " centres via translate(-50%,50%) off a `bottom` position (own knobs)",
        new RegExp("\\." + cls + "\\{[^}]*transform:translate\\(-50%,50%\\)").test(cssBlock));
});

// --- caption reassignment: capC (bottom) = projAvg + delta LEFT of the numeral; capP (left)
// tracks the PRE tick and never gets an animated `bottom` transition ------------------------
check("capC no longer carries a bottom-transition (it is fully static)",
    !/\.mpv-capC\{[^}]*transition:bottom/.test(cssBlock));
check("capP no longer carries a bottom-transition (it tracks the static pre tick)",
    !/\.mpv-capP\{[^}]*transition:bottom/.test(cssBlock));
// --- THE DIGIT-COUNT ANCHOR FIX (bar-tuner-digit-count-anchor-fix): NO caption may be a
// self-referencing shrink-wrapped box centred via left:50%+translateX(-50%) -- that construction
// can never give any child a truly fixed screen position, because BOTH its edges move as content
// width changes. All three captions must share ONE fixed right edge instead, and the delta must
// be an IN-FLOW flex child (an ordinary margin-right gap), not an out-of-flow box hanging off a
// content-dependent edge (right:100%/left:100%) -- that percentage-off-a-dynamic-box IS the exact
// mechanism of the sibling's shipped bug. Encoded as an INVARIANT, not today's literal values.
check("NO caption centres on a self-referencing left:50% + translateX(-50%) (the bug class)",
    !/\.mpv-cap[.\w]*\{[^}]*left:50%[^}]*\}/.test(cssBlock) &&
    !/\.mpv-cap[.\w]*\{[^}]*translateX\(-50%\)/.test(cssBlock));
check("capR/capC/capP share ONE right-alignment line: exactly one `right:100%` for the caption family",
    (cssBlock.match(/\.mpv-cap\b[^{]*\{[^}]*right:100%/g) || []).length === 1);
check("the delta (.mpv-d) is an IN-FLOW child -- no position:absolute left over",
    !/\.mpv-cap \.mpv-d\{[^}]*position:absolute/.test(cssBlock));
check("the delta's gap is an ordinary margin-right (in-flow), not right:100%/left:100%",
    /\.mpv-cap \.mpv-d\{margin-right:/.test(cssBlock) &&
    !/\.mpv-cap \.mpv-d\{[^}]*(right|left):100%/.test(cssBlock));
check(".mpv-ico is an IN-FLOW child with an ordinary margin-left gap, no out-of-flow left/right:100% hang",
    /\.mpv-cap \.mpv-ico\{margin-left:/.test(cssBlock) &&
    !/\.mpv-ico\{[^}]*(left|right):100%/.test(cssBlock));

ctx.showVal(true);
check("capV(capC) textContent == fmt(projAvg)", ctx.capV(ctx.capC).textContent === ctx.fmt(ctx.st.projAvg));
check("capV(capP) textContent == fmt(preAvg)", ctx.capV(ctx.capP).textContent === ctx.fmt(ctx.st.preAvg));
check("capP never gets the up/down glow (only capC/fill/tProj do)",
    !ctx.capV(ctx.capP).classList.contains("mpv-up") && !ctx.capV(ctx.capP).classList.contains("mpv-down"));

// --- capP tracks the PRE tick's position, not the proj tick's -------------------------------
// preAvg/projAvg are picked so their axis percentages land clear of the clearance clamp (5-95%)
// AND are clearly distinct (8.33% vs 75%) -- values that both fall into the clamped ceiling would
// mask a capP-tracks-the-wrong-tick bug behind an identical clamped result either way.
ctx.st.marks = 1; ctx.st.thrPrev = 2450; ctx.st.thrNext = 3050;
ctx.st.preAvg = 2500; ctx.st.projAvg = 2900;
ctx.apply();
check("capP.bottom tracks the pre tick's position (clamped pct(preAvg)), not proj's",
    ctx.capP.style.bottom === ctx.clampCapPPct(ctx.pct(ctx.st.preAvg)).toFixed(3) + "%");
check("tPre.bottom == pct(preAvg)", ctx.tPre.style.bottom === ctx.pct(ctx.st.preAvg).toFixed(3) + "%");

// --- the tuner's own in-browser regression guard must exist and skip CLEANLY + VISIBLY here
// (this vm shim has no real layout engine -- offsetWidth is a flat literal, getBoundingClientRect
// does not exist at all) -- a check nobody can see ran is indistinguishable from no check at all.
{
    const logged = [];
    const origLog = console.log;
    console.log = (m) => logged.push(m);
    const inv = ctx.checkCaptionInvariance();
    console.log = origLog;
    check("checkCaptionInvariance() exists and returns a result", !!inv);
    check("checkCaptionInvariance() skips CLEANLY under this headless shim (no real layout)", inv.skipped === true);
    check("the skip is VISIBLE (logged), not silent", logged.some((m) => /^SKIP\s+caption digit-count invariance/.test(m)));
}

// --- numeral-before-icon DOM order in every caption ------------------------------------------
const markup = html.match(/<div class="mpv-cap mpv-capP">([\s\S]*?)<\/div>/);
assert.ok(markup, "no .mpv-capP markup found");
check("capP: numeral (.mpv-v) precedes its icon (.mpv-ico) in the DOM",
    /class="mpv-v"[\s\S]*?class="mpv-ico/.test(markup[1]));
const capCMarkup = html.match(/<div class="mpv-cap mpv-capC">([\s\S]*?)<\/div>/)[1];
check("capC: numeral precedes its icon in the DOM", /class="mpv-v"[\s\S]*?class="mpv-ico/.test(capCMarkup));
const capRMarkup = html.match(/<div class="mpv-cap mpv-capR">([\s\S]*?)<\/div>/)[1];
check("capR: mark numeral precedes the mark icon, and eta numeral precedes the battles icon",
    /class="mpv-v"[\s\S]*?class="mpv-ico mk[\s\S]*?class="mpv-eta"[\s\S]*?class="mpv-ico battles/.test(capRMarkup));

// --- .mpv-capP's clamp holds at both axis extremes --------------------------------------------
ctx.st.barH = 200;
ctx.st.capPClear = 10;
const clr = (10 / 200) * 100; // 5%
const lo = ctx.clampCapPPct(0), hi = ctx.clampCapPPct(100);
check("clampCapPPct(0) is clamped up to the clearance floor", Math.abs(lo - clr) < 1e-9);
check("clampCapPPct(100) is clamped down to 100-clearance", Math.abs(hi - (100 - clr)) < 1e-9);
check("clampCapPPct never returns exactly 0 or 100 at the extremes", lo > 0 && hi < 100);
// mid-axis value must pass through unclamped
check("clampCapPPct(50) passes through unclamped", ctx.clampCapPPct(50) === 50);

// --- ISOLATION PROBES for every new per-type/per-caption knob (same idiom as the efficiency
// tuner's per-band glow knobs): mutate ONE knob, re-emit cssOut(), diff RULE-BY-RULE (selector ->
// declaration body, so a rule spanning many text lines is one unit, not fooled by line-splitting)
// against the baseline, and assert the ONLY rule whose declarations changed is the one that knob
// owns. A knob that silently moves a SECOND element is the failure mode this hunts for.
{
    function rulesOf(css) {
        const rules = [];
        const re = /([^{}]+)\{([^{}]*)\}/g;
        let m;
        while ((m = re.exec(css)) !== null) rules.push({ sel: m[1].trim(), decl: m[2] });
        return rules;
    }
    function isolated(knobId, probeVal, ownTag) {
        const baseRules = rulesOf(ctx.cssOut());
        const was = ctx.st[knobId];
        ctx.st[knobId] = probeVal;
        const mutRules = rulesOf(ctx.cssOut());
        ctx.st[knobId] = was;
        check(knobId + " isolation: rule count unchanged", mutRules.length === baseRules.length);
        let ownChanged = false;
        const leaked = [];
        for (let i = 0; i < baseRules.length && i < mutRules.length; i++) {
            if (baseRules[i].decl !== mutRules[i].decl) {
                if (baseRules[i].sel.indexOf(ownTag) >= 0) ownChanged = true;
                else leaked.push(baseRules[i].sel.replace(/\s+/g, " ").trim());
            }
        }
        check(knobId + " changes its OWN rule (" + ownTag + ")", ownChanged);
        check(knobId + " touches NO other rule (leaked into: " + (leaked.join(", ") || "none") + ")",
            leaked.length === 0);
    }
    // Tick geometry/nudges -- probe cross-lengths BELOW the current shared max (9) so the probe
    // itself can never trip halfOverhang()'s cross-cutting max-of-three into a second, LEGITIMATE
    // cascade into the captions' padding-right (that would be a false failure of this isolation
    // probe, not a real leak -- see halfOverhang()'s own comment).
    isolated("tickWEnd", 5, ".mpv-tick.mpv-end");
    isolated("tickWPre", 5, ".mpv-tick.mpv-pre");
    isolated("tickWProj", 5, ".mpv-tick.mpv-proj");
    isolated("tickHEnd", 4, ".mpv-tick.mpv-end");
    isolated("tickHPre", 4, ".mpv-tick.mpv-pre");
    isolated("tickHProj", 4, ".mpv-tick.mpv-proj");
    isolated("tickXEnd", 3, ".mpv-tick.mpv-end");
    isolated("tickXPre", 3, ".mpv-tick.mpv-pre");
    isolated("tickXProj", 3, ".mpv-tick.mpv-proj");
    // Caption residual X nudges.
    isolated("capxR", 3, ".mpv-capR");
    isolated("capxC", 3, ".mpv-capC");
    isolated("capxP", 3, ".mpv-capP");
    // Delta label knobs -- dFS legitimately touches both its font-size AND its derived
    // line-height (lh(dFS)), both within the one .mpv-cap .mpv-d rule.
    isolated("dFS", 20, ".mpv-cap .mpv-d");
    isolated("dGap", 0.8, ".mpv-cap .mpv-d");
    isolated("dY", -3, ".mpv-cap .mpv-d");
    // Per-caption numeral Y nudges -- never merged.
    isolated("numYR", 2, ".mpv-capR .mpv-v");
    isolated("numYC", 2, ".mpv-capC .mpv-v");
    isolated("numYP", 2, ".mpv-capP .mpv-v");
}

// --- byte-identical-at-defaults: re-running cssOut() with every SCHEMA default restored must
// reproduce the checked-in TASKS/refs/MoEProgressVertical.css byte-for-byte -- proves task 2's
// new knobs introduced no default-value drift (every new custom property/knob renders the SAME
// computed CSS the pre-task-2 file already emitted, just via a knob instead of a literal).
{
    const shippedCss = fs.readFileSync(path.join(REPO, "TASKS", "refs", "MoEProgressVertical.css"), "utf8");
    const freshCss = ctx.cssOut();
    check("cssOut() at SCHEMA defaults reproduces the checked-in MoEProgressVertical.css byte-for-byte",
        freshCss === shippedCss);
}

// --- THE RE-TRIGGER TWIN + THE "LARGE" SIZE-MODE BLOCK, asserted as EMITTED VALUES ------------
// Both are read off cssOut() with comments STRIPPED FIRST and every assertion SCOPED TO ITS
// OWNING RULE: a bare value grep passes just as happily after the value was reverted in the rule
// that owns it and left behind somewhere else (unscoped-substring-assertion-is-not-an-assertion).
{
    const emit = ctx.cssOut().replace(/\/\*[\s\S]*?\*\//g, "");
    // decl(sel): the declaration body of the ONE rule whose selector is exactly `sel`, or null.
    function decl(sel) {
        const re = new RegExp("(?:^|\\})\\s*" + sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{([^{}]*)\\}");
        const m2 = emit.match(re);
        return m2 ? m2[1].replace(/\s+/g, " ").trim() : null;
    }
    const kf = (name) => {
        const m2 = emit.match(new RegExp("@keyframes\\s+" + name + "\\s*\\{([\\s\\S]*?\\n\\})"));
        return m2 ? m2[1] : null;
    };

    // 1. THE TWIN EXISTS, and there are EXACTLY two life keyframes -- no more, no fewer.
    const life = kf("mpv-life"), lifeB = kf("mpv-life-b");
    check("@keyframes mpv-life exists in the emit", !!life);
    check("@keyframes mpv-life-b (the re-trigger twin) exists in the emit", !!lifeB);
    // `\b` alone is NOT enough to tell mpv-life from mpv-life-b -- "-" is a non-word char, so
    // /mpv-life\b/ happily matches the twin's name too. The lookahead is load-bearing.
    check("exactly two mpv-life* keyframes are emitted (one base, one twin)",
        (emit.match(/@keyframes\s+mpv-life(?!-)/g) || []).length === 1 &&
        (emit.match(/@keyframes\s+mpv-life-b\b/g) || []).length === 1 &&
        (emit.match(/@keyframes\s+mpv-life/g) || []).length === 2);
    // 2. BYTE-IDENTICAL APART FROM THE NAME. The bodies carry no name at all, so they must match
    // exactly -- this is the assertion the shipped MoEProgress.css pair can only make by hand.
    check("the twin's keyframe body is BYTE-IDENTICAL to mpv-life's", !!life && life === lifeB);
    // 3. EACH IS REFERENCED BY ITS OWN RUN CLASS, at the same duration, scoped to that rule.
    const total = ctx.st.fadeIn + ctx.st.hold + ctx.st.fadeOut;
    check("#moe-bar-root.mpv-run animates mpv-life for totalMs (" + total + "ms), `both` fill",
        decl("#moe-bar-root.mpv-run") === "animation: mpv-life " + total + "ms both;");
    check("#moe-bar-root.mpv-run-b animates mpv-life-b for the SAME " + total + "ms, `both` fill",
        decl("#moe-bar-root.mpv-run-b") === "animation: mpv-life-b " + total + "ms both;");
    check("the twin is bound to a DIFFERENT animation-name than .mpv-run (that IS the mechanism)",
        decl("#moe-bar-root.mpv-run") !== decl("#moe-bar-root.mpv-run-b"));

    // 4. THE LARGE BLOCK's actual x/y lengths. `x` is re-derived HERE (base knob * SIZE_XF, 3dp,
    // trailing zeros trimmed) rather than trusted from the tuner's own X43() -- and SIZE_XF is
    // asserted to be 4/3 and NOT 5/3: the root font already carries SIZE_F, so an x-length that
    // took both would come out 25% long (mp-lg-x-lengths-are-pure-sizexf-not-sizef).
    const SIZE_XF = 4 / 3, SIZE_F = 1.25;
    const x = (v) => +(v * SIZE_XF).toFixed(3);
    const s = ctx.st, pr = x(s.gapP + ctx.halfOverhang()) + "rem";
    check("SIZE_XF is 4/3 and the block does NOT also apply SIZE_F (" +
        x(s.trackW) + "rem, not " + +(s.trackW * SIZE_XF * SIZE_F).toFixed(3) + "rem)",
        decl(".mpv-lg #moe-bar-root") === "width: " + x(s.trackW) + "rem;");
    check(".mpv-lg .mpv-backdrop restates BOTH x-lengths (left/width), preserving the base overhangs",
        decl(".mpv-lg .mpv-backdrop") ===
        "left: " + x(s.bdLeft) + "rem; width: " + x(s.bdW) + "rem;");
    [["end", "tickWEnd", "tickXEnd"], ["pre", "tickWPre", "tickXPre"], ["proj", "tickWProj", "tickXProj"]]
        .forEach(([cls, wk, xk]) => {
            check(".mpv-lg .mpv-tick.mpv-" + cls + " scales its OWN cross-span + X nudge, and " +
                "RESTATES the whole transform (a transform declaration replaces its base outright)",
                decl(".mpv-lg .mpv-tick.mpv-" + cls) === "width: " + x(s[wk]) + "rem; transform: " +
                "translate(-50%, 50%) translateX(" + x(s[xk]) + "rem);");
        });
    check(".mpv-lg .mpv-capR carries its own padding-right + translateX",
        decl(".mpv-lg .mpv-capR") === "padding-right: " + pr + "; transform: translateX(" + x(s.capxR) + "rem);");
    check(".mpv-lg .mpv-capC carries its own padding-right + translateX",
        decl(".mpv-lg .mpv-capC") === "padding-right: " + pr + "; transform: translateX(" + x(s.capxC) + "rem);");
    check(".mpv-lg .mpv-capP keeps its translateY(50%) centring term in the restated transform",
        decl(".mpv-lg .mpv-capP") === "padding-right: " + pr +
        "; transform: translateY(50%) translateX(" + x(s.capxP) + "rem);");
    check(".mpv-lg .mpv-cap .mpv-ico scales the icon gap", decl(".mpv-lg .mpv-cap .mpv-ico") ===
        "margin-left: " + x(s.icoGap) + "rem;");
    check(".mpv-lg .mpv-cap .mpv-d scales the delta gap and stays in `em` (it tracks its own font-size)",
        decl(".mpv-lg .mpv-cap .mpv-d") === "margin-right: " + x(s.dGap) + "em;");
    check(".mpv-lg .mpv-capR .mpv-eta scales the eta gap", decl(".mpv-lg .mpv-capR .mpv-eta") ===
        "margin-left: " + x(s.etaGap) + "rem;");

    // 5. NOTHING Y/UNIFORM MAY APPEAR UNDER .mpv-lg -- the root font already scales it, so a rule
    // here would DOUBLE-APPLY SIZE_F. Scoped to the .mpv-lg rules only, comments already stripped.
    const lgDecls = (emit.match(/\.mpv-lg [^{}]*\{[^{}]*\}/g) || []).join("");
    check(".mpv-lg block declares " + (emit.match(/\.mpv-lg /g) || []).length + " rules, and NONE of " +
        "them is a y/uniform length (no font-size/line-height/height/padding-bottom/margin-top/animation)",
        lgDecls.length > 0 &&
        !/(font-size|line-height|height:|padding-bottom|padding-top|margin-top|margin-bottom|animation)/.test(lgDecls));
    check("no @keyframes is declared inside the .mpv-lg block (the slide is a y length)",
        !/\.mpv-lg[^{}]*\{[^{}]*\}\s*@keyframes/.test(emit) && !/@keyframes[^{]*mpv-lg/.test(emit));
    // The dash grid is a y-PERIOD on this bar (0deg == "to top"), unlike the horizontal bar's
    // 90deg twin, so unlike .mp-lg it must take NO rule here at all.
    check("the dash grid takes no .mpv-lg rule (0deg == a y-period here, not the horizontal 90deg)",
        !/\.mpv-lg [^{}]*mpv-track/.test(emit) &&
        /\.mpv-track::after \{[^}]*repeating-linear-gradient\(0deg/.test(emit));
}

// --- stage-stylesheet check: a rename-miss can leave a selector matching NOTHING while every
// emit-only assertion above stays green -- the sibling efficiency tuner shipped exactly this bug
// (three selectors left under the old prefix, glyphs rendered blank, every emit assertion still
// passed). Strip CSS comments first, then verify every glyph class actually used in the markup
// has a background-image rule, and no ".mp*" selector token survives outside ".mpv-".
const cssNoComments = cssBlock.replace(/\/\*[\s\S]*?\*\//g, "");
["dmgp", "dmgc", "moe", "mk1", "mk2", "mk3", "battles"].forEach((cls) => {
    // "used" = the class token appears somewhere in the document (static markup for dmgp/dmgc/
    // battles/mk-in-general, or the JS's setIco()/glyph-select string literals for moe/mk1/mk3,
    // which only ever land in the DOM at runtime for a 0/3-mark snapshot the static HTML doesn't
    // capture) -- proof the glyph is really part of the widget, not proof it rendered THIS run.
    const used = html.includes(cls);
    const hasRule = new RegExp('\\.mpv-ico\\.' + cls + '(::after)?\\{[^}]*background-image').test(cssNoComments);
    check("glyph ." + cls + " is used by the widget and has a background-image rule", used && hasRule);
});
const badMpSelectors = [];
cssNoComments.replace(/([^{}]+)\{/g, (_, sel) => {
    sel.split(",").forEach((s) => {
        (s.match(/\.mp[A-Za-z0-9_-]*/g) || []).forEach((t) => {
            if (!t.startsWith(".mpv-")) badMpSelectors.push(t);
        });
    });
    return "";
});
check("no bare .mp- selector token survives in the <style> block (found: " +
    (badMpSelectors.length ? badMpSelectors.join(", ") : "none") + ")", badMpSelectors.length === 0);

fs.unlinkSync(tmpHtml);

// --- the -Artifact variant: no document skeleton, zero external hosts, under 16 MB -----------
// -SelfCheck asserts the skeleton tags are gone too, but cheaply (regex on the in-memory
// string); this is the thorough pass -- a REAL generated file, and the external-reference scan
// strips base64 payloads first so a coincidental byte run inside an asset can't false-positive.
const tmpArtifact = path.join(os.tmpdir(), "check_bar_vertical_artifact." + process.pid + ".html");
execFileSync("pwsh", ["-NoProfile", "-File", GEN, "-Artifact", "-ArtifactOut", tmpArtifact],
    { cwd: REPO, encoding: "utf8" });
const artifactBuf = fs.readFileSync(tmpArtifact);
const artifact = artifactBuf.toString("utf8");
fs.unlinkSync(tmpArtifact);

["<!DOCTYPE", "<html", "<head", "<body"].forEach((tag) => {
    check("artifact variant has no " + tag + " tag", !new RegExp(tag, "i").test(artifact));
});
check("artifact variant keeps a <title>", /<title>/.test(artifact));
check("artifact variant is under 16 MB", artifactBuf.length < 16 * 1024 * 1024);
console.log("  artifact size: " + artifactBuf.length + " bytes");

const noPayloads = artifact.replace(/base64,[A-Za-z0-9+/=]+/g, "base64,STRIPPED");
const EXTERNAL = {
    "http(s):// reference": /https?:\/\//,
    "fetch(": /fetch\(/,
    "XMLHttpRequest": /XMLHttpRequest/,
    "@import": /@import/,
    "protocol-relative // src/href/url": /(?:src|href|url)\(?\s*=?\s*["']?\/\//,
};
Object.entries(EXTERNAL).forEach(([label, re]) => {
    const n = (noPayloads.match(new RegExp(re, "g")) || []).length;
    check("zero " + label + " outside base64 payloads (found " + n + ")", n === 0);
});

// --- no local machine/path leakage (username, game install dir, -GameDir default) -------------
["Dmytro", "D:/Games", "World_of_Tanks_EU", "GameDir", "C:\\Users"].forEach((needle) => {
    check("no local-path leak: " + JSON.stringify(needle), !artifact.includes(needle));
});

console.log("");
if (failed) {
    console.log("check_bar_vertical: " + failed + " failed, " + passed + " passed");
    process.exit(1);
}
console.log("check_bar_vertical: " + passed + " assertions passed");
