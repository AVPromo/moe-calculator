/* check_eff_vertical.js -- headless runner for eff_bar_tuner_vertical.html's own selfCheck(),
 * plus independent assertions on its emitted CSS (placement math + bottom-anchoring), PLUS the
 * artifact-twin's publish-readiness (no document skeleton, size, zero external refs, zero local-
 * path leaks). Same idiom as tools/dev/emit_eff_css.js: the tuner's <script> body is read as
 * text, truncated at its "// ---- panel wiring" marker (everything past that is DOM event wiring
 * the emit never reads), and evaluated by `new Function` against a single self-returning stub
 * node -- nothing in the tuner file is edited, it runs at its checked-in SCHEMA defaults.
 *
 * Unlike emit_eff_css.js, this does NOT write MoEEfficiency.css (or any shipped file) -- the
 * vertical variant is tuner-only, Phase 1, nothing in src/ exists for it yet. This script is the
 * verification the task asked for: run it, read the output, that's the whole job.
 *
 * THE ARTIFACT TWIN IS GENERATED, NOT HAND-MAINTAINED (see make_eff_vertical_artifact.js's own
 * header for why): this check re-runs that exact same build() and asserts the checked-in
 * eff_bar_tuner_vertical.artifact.html is byte-identical to it, so a stale twin (someone edited
 * the tuner and forgot to regenerate) fails loudly here instead of drifting silently.
 *
 *   node tools/dev/check_eff_vertical.js
 */
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");
const makeArtifact = require("./make_eff_vertical_artifact.js");

const TUNER = path.join(__dirname, "eff_bar_tuner_vertical.html");
const CUT = "// ---- panel wiring";

function stubNode() {
    const n = {
        style: {}, textContent: "", className: "", innerHTML: "", offsetWidth: 0, offsetHeight: 0,
        classList: { add() {}, remove() {}, contains: () => false, toggle: () => false },
        appendChild(c) { return c; }, addEventListener() {}, removeEventListener() {},
        querySelectorAll: () => [],
    };
    n.querySelector = () => n;
    return n;
}
const node = stubNode();
const document = {
    head: node, body: node,
    getElementById: () => node,
    createElement: () => stubNode(),
    querySelector: () => node,
    querySelectorAll: () => [],
};

const html = fs.readFileSync(TUNER, "utf8");
const open = html.indexOf("<script>");
const close = html.lastIndexOf("</script>");
assert.ok(open >= 0 && close > open, "eff_bar_tuner_vertical.html: no <script> block found");
const full = html.slice(open + "<script>".length, close);
const cut = full.indexOf(CUT);
assert.ok(cut > 0, "eff_bar_tuner_vertical.html: the '" + CUT + "' marker is gone -- re-check the cut point");

// ================================================================================================
// THE STAGE STYLESHEET, scanned as SOURCE TEXT -- not the emit. This whole file is a rename-clone
// (.mp-* -> .mev-*, #moe-bar-root -> #mev-bar-root) of eff_bar_tuner.html, so a selector the
// rename missed is the single most likely defect class here, and cssOut()-only scanning (the
// check this replaces) cannot see it: the stage <style> block is hand-authored preview CSS, wholly
// separate from what cssOut() builds.
// ================================================================================================
const styleOpen = html.indexOf("<style>");
const styleClose = html.indexOf("</style>");
assert.ok(styleOpen >= 0 && styleClose > styleOpen, "eff_bar_tuner_vertical.html: no <style> block found");
const stageCss = html.slice(styleOpen + "<style>".length, styleClose);
const stageDecl = stageCss.replace(/\/\*[\s\S]*?\*\//g, ""); // decl(): strip comments before scanning

const staleNamespace = stageDecl.match(/\.mp-[A-Za-z0-9-]+|#moe-bar-root/g) || [];
assert.strictEqual(staleNamespace.length, 0,
    "STAGE STYLESHEET carries a surviving .mp-*/#moe-bar-root selector -- the rename missed it: " +
    JSON.stringify(staleNamespace));

// Stronger than the namespace grep: every glyph-carrying class combo actually used in the
// markup must have a MATCHING stage-CSS rule that sets background-image, so a rename miss (or
// any other selector/markup mismatch) that leaves a glyph unwired is caught regardless of which
// prefix it lands on. Cheap because it's a pure subset test over already-parsed class tokens --
// no real DOM/cascade needed for a stylesheet this flat (no nesting, no specificity fights among
// the rules that set background-image).
const markup = html.slice(styleClose + "</style>".length, open);
const iconTags = markup.match(/<i class="[^"]+">/g) || [];
assert.ok(iconTags.length > 0, "no <i class=\"...\"> icon tags found in the markup to check");

function rulesOf(cssText) {
    const rules = [];
    const re = /([^{}]+)\{([^{}]*)\}/g;
    let m;
    while ((m = re.exec(cssText)) !== null) {
        const classes = (m[1].match(/\.[A-Za-z0-9-]+/g) || []).map((c) => c.slice(1));
        rules.push({ classes, decl: m[2] });
    }
    return rules;
}
const stageRules = rulesOf(stageDecl);

iconTags.forEach((tag) => {
    const classes = tag.match(/class="([^"]+)"/)[1].split(/\s+/);
    const wired = stageRules.some((r) =>
        r.decl.indexOf("background-image") >= 0 &&
        r.classes.length > 0 &&
        r.classes.every((c) => classes.indexOf(c) >= 0));
    assert.ok(wired, "icon tag " + tag + " has NO matching stage-CSS rule with background-image " +
        "(classes " + JSON.stringify(classes) + ") -- a rename miss or dead selector");
});
console.log("stage stylesheet: 0 stale .mp-*/#moe-bar-root selectors, all " + iconTags.length +
    " icon tags have a wired background-image rule");

const EFF = new Function("document", "window", "navigator",
    full.slice(0, cut) +
    "\nreturn {st:st,cssOut:cssOut,check:selfCheck,SCHEMA:SCHEMA,BANDS:BANDS,placement:placement};")(
    document, { EFF: null }, {});

// Defaults only, same guard as emit_eff_css.js: nothing above may have moved a knob.
EFF.SCHEMA.forEach((sec) => sec[1].forEach((c) => assert.strictEqual(
    EFF.st[c.id], c.val, "knob '" + c.id + "' is not at its SCHEMA default")));

// --- the tuner's own self-check, headless ----------------------------------------------------
const green = EFF.check();
const report = node.textContent;
assert.ok(green, "the tuner's own selfCheck FAILED:\n" + report);
console.log("tuner selfCheck: " + report.split("\n")[0]);

// --- the emit --------------------------------------------------------------------------------
const css = EFF.cssOut();
assert.ok(!/__[A-Z0-9_]+__/.test(css), "leftover __TOKEN__ placeholder in the emit");
assert.ok(!/\bundefined\b|\bNaN\b/.test(css), "the emit contains undefined/NaN");
assert.ok(!/\bmp-|#moe-bar-root/.test(css.replace(/\/\*[\s\S]*?\*\//g, "")),
    "the emit leaked the shared .mp-*/#moe-bar-root namespace outside a comment");

// --- independent placement-math assertions (not just re-running the tuner's own selfCheck) ---
// mmGap defaults to 8 (unchanged); bottomGap is the maintainer's tuned 28 (was 8) -- a real
// tuning-session value, preserved here, not re-derived.
const mmGapKnob = EFF.SCHEMA[0][1].find((c) => c.id === "mmGap");
const bottomGapKnob = EFF.SCHEMA[0][1].find((c) => c.id === "bottomGap");
assert.strictEqual(mmGapKnob.val, 8, "mmGap SCHEMA default must be 8");
assert.strictEqual(bottomGapKnob.val, 28, "bottomGap SCHEMA default must be 28 (the tuned value)");
// TUNED, post-fix: capxReq (r1-r3, small tick-clearance trim) and capxR4/capxCur (r4/current,
// their OWN larger constants -- no tick to clear above/below the track's end) are all FIXED
// constants, independent of the numeral's own width; that independence is what makes an anchor
// correct, not whether the default happens to be 0. See the file header's own note.
const capxReqKnob = EFF.SCHEMA[0][1].find((c) => c.id === "capxReq");
const capxR4Knob = EFF.SCHEMA[0][1].find((c) => c.id === "capxR4");
const capxCurKnob = EFF.SCHEMA[0][1].find((c) => c.id === "capxCur");
const dYKnob = EFF.SCHEMA[1][1].find((c) => c.id === "dY");
assert.strictEqual(capxReqKnob.val, -2, "capxReq (r1-r3) SCHEMA default must be -2");
assert.strictEqual(capxR4Knob.val, 11, "capxR4 (r4) SCHEMA default must be 11");
assert.strictEqual(capxCurKnob.val, 13, "capxCur (current) SCHEMA default must be 13");
assert.strictEqual(dYKnob.val, 2.5, "dY SCHEMA default must be 2.5");

// crossPad(): half the OVERHANG of the wider tick past the track -- re-derived here from the
// SCHEMA defaults, not trusted from the tuner's own crossPad().
const crossPad = () => (Math.max(EFF.st.tickH, EFF.st.tickHC) - EFF.st.trackH) / 2;
const pad = crossPad();

// --- ISOLATION PROBE for the split knob: capxReq (r1-r3) and capxR4 (r4) used to be ONE shared
// knob -- mutate each independently and assert the re-emit changes EXACTLY the one line that
// knob owns, same idiom as the icoyReq/icoyBm/icoyCur probe below.
{
    const linesBase = css.split("\n");
    const wasReq = EFF.st.capxReq, wasR4 = EFF.st.capxR4;
    EFF.st.capxReq = -17.5;
    const cssReq = EFF.cssOut();
    const movedReq = cssReq.split("\n").filter((l, i) => l !== linesBase[i]);
    EFF.st.capxReq = wasReq;
    EFF.st.capxR4 = 23.5;
    const cssR4 = EFF.cssOut();
    const movedR4 = cssR4.split("\n").filter((l, i) => l !== linesBase[i]);
    EFF.st.capxR4 = wasR4;
    // Exactly one emitted LINE moves per knob (the property line -- the selector line above it,
    // ".mev-cap.lf {" / ".mev-cap.tp {", is unaffected, which line-diffing alone cannot show, so
    // this ALSO greps the full string for the owning selector immediately preceding the changed
    // literal, the same idiom the tuner's own selfCheck uses for this exact pair).
    // TWO lines now, not one: the knob owns its base rule AND its `.mev-lg` size-mode twin (whose
    // literal is the SAME base scaled by SIZE_XF, so it is a different string and the
    // exactly-once greps below still hold on the base literal).
    assert.strictEqual(movedReq.length, 2,
        "mutating capxReq must change EXACTLY two emitted lines (its base rule + its .mev-lg twin)");
    assert.ok(movedReq[1].indexOf(".mev-lg .mev-cap.lf") >= 0 &&
        movedReq[1].indexOf("translateX(" + +(-17.5 * 4 / 3).toFixed(3) + "rem)") >= 0,
        "capxReq's SECOND changed line must be its .mev-lg twin at base*SIZE_XF: " + movedReq[1]);
    assert.ok(movedReq[0].indexOf("-17.5rem") >= 0,
        "capxReq's changed line must carry its new literal: " + movedReq[0]);
    assert.ok(cssReq.indexOf(".mev-cap.lf {\n  transform: translateY(50%) translateX(" +
        (-pad) + "rem) translateX(-17.5rem);") >= 0,
        "the -17.5rem literal must land in .mev-cap.lf's OWN transform, not .mev-cap.tp's");
    assert.ok(cssReq.indexOf(".mev-cap.tp {\n  bottom: 100%; padding-bottom: ") >= 0 &&
        cssReq.indexOf("-17.5rem") === cssReq.lastIndexOf("-17.5rem"),
        "the -17.5rem literal must appear EXACTLY ONCE (not also in .mev-cap.tp)");

    assert.strictEqual(movedR4.length, 2,
        "mutating capxR4 must change EXACTLY two emitted lines (its base rule + its .mev-lg twin)");
    assert.ok(movedR4[1].indexOf(".mev-lg .mev-cap.tp") >= 0 &&
        movedR4[1].indexOf("translateX(" + +(23.5 * 4 / 3).toFixed(3) + "rem)") >= 0,
        "capxR4's SECOND changed line must be its .mev-lg twin at base*SIZE_XF: " + movedR4[1]);
    assert.ok(movedR4[0].indexOf("23.5rem") >= 0,
        "capxR4's changed line must carry its new literal: " + movedR4[0]);
    assert.ok(cssR4.indexOf(".mev-cap.tp {\n  bottom: 100%; padding-bottom: " + EFF.st.gapBot +
        "rem;\n  transform: translateX(" + (-pad) + "rem) translateX(23.5rem);") >= 0,
        "the 23.5rem literal must land in .mev-cap.tp's OWN transform, not .mev-cap.lf's");
    assert.strictEqual((cssR4.match(/23\.5rem/g) || []).length, 1,
        "the 23.5rem literal must appear EXACTLY ONCE (not also in .mev-cap.lf)");
}

const MM_SIZES = [228, 279, 329, 409, 510, 628];
[0, 2, 5].forEach((idx) => {
    const was = EFF.st.mmIdx;
    EFF.st.mmIdx = idx;
    const p = EFF.placement();
    const expectSize = MM_SIZES[idx];
    assert.strictEqual(p.mmSize, expectSize, "mmIdx=" + idx + ": mmSize");
    assert.strictEqual(p.barRight, EFF.st.stageW - expectSize - EFF.st.mmGap,
        "mmIdx=" + idx + ": barRight (the TICK'S outer edge) must equal stageW - mmSize - gap, " +
        "independent of crossPad");
    assert.strictEqual(p.rightInset, expectSize + EFF.st.mmGap + pad,
        "mmIdx=" + idx + ": rightInset (what the CSS `right:` uses) must equal mmSize + gap + " +
        "(K-T)/2");
    EFF.st.mmIdx = was;
});
assert.strictEqual(EFF.placement().barBottom, EFF.st.stageH - EFF.st.bottomGap,
    "barBottom must equal stageH - bottomGap");

// --- bottom-anchoring, read straight off the emitted CSS, independent of the tuner's own check.
const decl = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "");
assert.ok(/\.mev-fill \{\n {2}position: absolute;\n {2}left: 0;\n {2}bottom: 0;/.test(css),
    "the fill rule must be bottom-anchored");
assert.ok(css.indexOf("height: 0;") >= 0 && decl(css).indexOf(".mev-fill { width: 0") < 0,
    "the fill's animated axis must be height, not width");
["r1", "r2", "r3", "r4"].forEach((r, i) => {
    const pct = [25, 50, 75, 100][i];
    assert.ok(css.indexOf(".mev-tick." + r + " { bottom: " + pct + "%; }") >= 0,
        ".mev-tick." + r + " must be bottom-anchored at " + pct + "%");
});
assert.ok(css.indexOf("transition: bottom ") >= 0, "the current tick's transition must be on bottom");
assert.ok(decl(css).indexOf(".mev-mark") < 0,
    "there must be NO .mev-mark selector left in the emit -- the moving marker element is gone");
assert.ok(css.indexOf("bottom: " + EFF.st.bottomGap + "px;") >= 0,
    "#mev-bar-root's `bottom:` inset must carry the bottomGap knob");

// --- item 1: r1/r2/r3 LEFT of the track on their own tick (25/50/75%, translateY(50%)); r4 a
// static cap at the TOP end (bottom:100%); current value + delta static at the BOTTOM end
// (top:100%), with the delta LEFT of the numeral.
["r1", "r2", "r3"].forEach((r, i) => {
    const pct = [25, 50, 75][i];
    assert.ok(css.indexOf(".mev-cap." + r + " { bottom: " + pct + "%; }") >= 0,
        ".mev-cap." + r + " must sit at bottom: " + pct + "%, beside its own tick");
});
assert.ok(/\.mev-cap \{\n {2}position: absolute; display: flex;[^}]*right: 100%;/.test(css),
    "the SHARED .mev-cap base rule must anchor every caption via right: 100%");
assert.ok(/\.mev-cap\.lf \{\n {2}transform: translateY\(50%\)/.test(css),
    ".mev-cap.lf must add translateY(50%) centring on top of the shared anchor");
assert.ok(/\.mev-cap\.tp \{\n {2}bottom: 100%;/.test(css),
    ".mev-cap.tp (r4) must be a static cap at bottom:100% (the track's top end)");
assert.ok(/\.mev-cap\.bt \{\n {2}top: 100%;/.test(css),
    ".mev-cap.bt (current value) must be a static cap at top:100% (the track's bottom end)");
assert.ok(/\.mev-cap\.bt \.mev-d \{\n {2}position: absolute;\n {2}right: 100%;/.test(css),
    "the delta must anchor via right:100% -- LEFT of the numeral, not right of it");
assert.ok(decl(css).indexOf(".mev-cap.bt .mev-d {\n  position: absolute;\n  left: 100%;") < 0,
    "the delta must NOT anchor via left:100% (that would put it right of the numeral)");

// --- THE BUG FIX ITSELF, as a STRUCTURAL invariant (no real layout engine here, so this is the
// closest a headless check gets to "caption alignment is invariant across digit counts"): no
// caption may centre itself via a self-referencing left:50% + translate(-50%) (a box's OWN size
// feeding its OWN position IS the bug -- see the task's root-cause diagnosis), and exactly ONE
// bare `.mev-cap`/`.mev-cap.X` rule may declare `right: 100%` -- the single shared anchor line
// every caption (lf/tp/bt) rides on, not one apiece.
assert.ok(!/\.mev-cap[.\w]*\s*\{[^}]*left:\s*50%[^}]*\}/.test(decl(css)),
    "NO caption rule may declare left: 50% (the digit-count centring bug)");
assert.ok(!/\.mev-cap[.\w]*\s*\{[^}]*translate[XY]?\(\s*-50%[^}]*\}/.test(decl(css)),
    "NO caption rule may declare a self-referencing translate(-50%...) (the digit-count centring bug)");
const sharedAnchorRules = decl(css).match(/^\.mev-cap(\.[a-z]+)? \{[^}]*right:\s*100%/gm) || [];
assert.strictEqual(sharedAnchorRules.length, 1,
    "exactly ONE bare .mev-cap/.mev-cap.X rule may declare right: 100% (the shared anchor line), " +
    "found " + sharedAnchorRules.length + " -- lf/tp/bt must not each redeclare their own");

// --- item 3: the icon is now an IN-FLOW flex child (margin-left gap), not an out-of-flow
// absolute+transform edge-hang -- that self-referencing edge-hang was the OTHER half of the bug
// (both the icon AND the delta hung off a box whose width depended on its own numeral).
assert.ok(decl(css).indexOf(".mev-ico { position: relative; display: block; flex: none;") >= 0,
    "the base .mev-ico rule must be an IN-FLOW flex child (position: relative, not absolute)");
assert.ok(css.indexOf(".mev-cap .mev-ico { margin-left: ") >= 0,
    "the icon's gap must be an ordinary in-flow margin-left, not an out-of-flow transform");
assert.ok(!/\.mev-ico[^{]*\{\n[^}]*(left|right):\s*100%/.test(decl(css)),
    "no .mev-ico rule may anchor via left:100%/right:100% (that is the out-of-flow edge-hang bug)");
assert.ok(/\.mev-cap \{[^}]*display:\s*flex/.test(decl(css)),
    "the shared .mev-cap base rule must be display: flex (the shipped .mp-cap / .mpv-cap idiom)");

// --- item 4: the (K-T)/2 term already proven above via rightInset; prove it ALSO reaches the
// left caption's own clearance transform (--lfclear / translateX literal).
assert.ok(css.indexOf("translateX(" + (-pad) + "rem)") >= 0 ||
    css.indexOf("translateX(-" + pad + "rem)") >= 0,
    "the left caption's clearance transform must carry -crossPad() (" + (-pad) + "rem)");

// --- item 3/7: the three icon Y-nudge knobs stay independent (re-derived here, not just
// trusting the tuner's own probe) -- moving one must not move the OTHER two knobs' literals.
const wasReq = EFF.st.icoyReq, wasBm = EFF.st.icoyBm, wasCur = EFF.st.icoyCur;
EFF.st.icoyReq = 4; EFF.st.icoyBm = -4; EFF.st.icoyCur = 4;
const cssMoved = EFF.cssOut();
EFF.st.icoyReq = wasReq; EFF.st.icoyBm = wasBm; EFF.st.icoyCur = wasCur;
assert.ok(cssMoved.indexOf("translateY(4rem)") >= 0, "icoyReq/icoyCur (both probed to 4) must reach the emit");
assert.ok(cssMoved.indexOf("translateY(-4rem)") >= 0, "icoyBm (probed to -4) must reach the emit");
const onlyReq = (() => {
    const wasB = EFF.st.icoyBm, wasC = EFF.st.icoyCur;
    EFF.st.icoyReq = 4; EFF.st.icoyBm = wasBm; EFF.st.icoyCur = wasCur;
    const out = EFF.cssOut();
    EFF.st.icoyReq = wasReq; EFF.st.icoyBm = wasB; EFF.st.icoyCur = wasC;
    return out;
})();
assert.strictEqual(
    (onlyReq.match(/translateY\(0\.25rem\)/g) || []).length, 0,
    "moving icoyReq off its default must remove ITS OWN old literal");
assert.ok(onlyReq.indexOf("translateY(-0.25rem)") >= 0, "icoyBm must stay at its own default while icoyReq moves");
assert.ok(onlyReq.indexOf("translateY(0.5rem)") >= 0, "icoyCur must stay at its own default while icoyReq moves");

// ================================================================================================
// THE RE-TRIGGER TWIN + THE "LARGE" SIZE-MODE BLOCK, asserted as EMITTED VALUES. Comments are
// STRIPPED FIRST and every assertion is SCOPED TO ITS OWNING RULE -- a bare value grep passes just
// as happily after the value was reverted in the rule that owns it and left behind somewhere else
// (unscoped-substring-assertion-is-not-an-assertion).
// ================================================================================================
{
    const emit = decl(css);
    // ruleOf(sel): the declaration body of the ONE rule whose selector is exactly `sel`.
    const ruleOf = (sel) => {
        const m = emit.match(new RegExp("(?:^|\\})\\s*" +
            sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\s*\\{([^{}]*)\\}"));
        return m ? m[1].replace(/\s+/g, " ").trim() : null;
    };
    const kf = (name) => {
        const m = emit.match(new RegExp("@keyframes\\s+" + name + "\\{([\\s\\S]*?\\}\\})"));
        return m ? m[1] : null;
    };

    // --- 1/2/3. The twin exists, is BYTE-IDENTICAL apart from the name, and each half is bound to
    // its OWN run class at the same duration. `\b` alone cannot tell mev-life from mev-life-b ("-"
    // is a non-word char), so the lookahead below is load-bearing.
    const life = kf("mev-life"), lifeB = kf("mev-life-b");
    assert.ok(life, "@keyframes mev-life is missing from the emit");
    assert.ok(lifeB, "@keyframes mev-life-b (the re-trigger twin) is missing from the emit");
    assert.strictEqual(life, lifeB,
        "the twin's keyframe body must be BYTE-IDENTICAL to mev-life's, name aside");
    assert.strictEqual((emit.match(/@keyframes\s+mev-life(?!-)/g) || []).length, 1,
        "exactly one @keyframes mev-life (the base) may be emitted");
    assert.strictEqual((emit.match(/@keyframes\s+mev-life-b\b/g) || []).length, 1,
        "exactly one @keyframes mev-life-b (the twin) may be emitted");
    const totalMs = EFF.st.fadeIn + EFF.st.hold + EFF.st.fadeOut;
    assert.strictEqual(ruleOf("#mev-bar-root.mev-run"), "animation:mev-life " + totalMs + "ms both",
        "#mev-bar-root.mev-run must animate mev-life for totalMs with `both` fill");
    assert.strictEqual(ruleOf("#mev-bar-root.mev-run-b"), "animation:mev-life-b " + totalMs + "ms both",
        "#mev-bar-root.mev-run-b must animate mev-life-b for the SAME duration with `both` fill");
    assert.notStrictEqual(ruleOf("#mev-bar-root.mev-run"), ruleOf("#mev-bar-root.mev-run-b"),
        "the twin must carry a DIFFERENT animation-name than .mev-run -- that IS the mechanism");

    // --- 4. The Large block's actual x-lengths. `x` is re-derived HERE (base knob * SIZE_XF, 3dp,
    // trailing zeros trimmed), not trusted from the tuner's own X43 -- and SIZE_XF is asserted to be
    // 4/3 and NOT 5/3: the root font already carries SIZE_F, so an x-length taking both would come
    // out 25% long (mp-lg-x-lengths-are-pure-sizexf-not-sizef).
    const SIZE_XF = 4 / 3, SIZE_F = 1.25;
    const x = (v) => +(v * SIZE_XF).toFixed(3);
    const s = EFF.st, clr = "translateX(" + x(-pad) + "rem)";
    assert.strictEqual(ruleOf(".mev-lg #mev-bar-root"), "width: " + x(s.trackH) + "rem;",
        "the track thickness must be base*SIZE_XF (" + x(s.trackH) + "rem), NOT base*SIZE_F*SIZE_XF (" +
        +(s.trackH * SIZE_F * SIZE_XF).toFixed(3) + "rem)");
    assert.strictEqual(ruleOf(".mev-lg .mev-track"), "width: " + x(s.trackH) + "rem;",
        ".mev-track carries its OWN explicit width and owes the same twin as the root");
    assert.strictEqual(ruleOf(".mev-lg .mev-backdrop"),
        "left: " + x(s.bdTop) + "rem; width: " + x(s.bdH) + "rem;",
        ".mev-lg .mev-backdrop must restate BOTH x-lengths, preserving the base overhangs");
    // THE DASH GRID TAKES NO .mev-lg RULE, and that ABSENCE is asserted: a 0deg grid's period is a
    // y-length the root font already scales, so a reintroduced twin would DOUBLE-APPLY SIZE_F --
    // and without an absence assertion it would sail through silently.
    assert.strictEqual(ruleOf(".mev-lg .mev-track::after"), null,
        "the .mev-lg block must declare NO dash-grid rule: the 0deg grid's period is a y-length " +
        "the root font already scales (unlike the horizontal .mp-lg block's 90deg twin)");
    assert.ok(!/\.mev-lg [^{}]*mev-track::after/.test(emit),
        "no .mev-lg selector may reach the dash grid at all");
    assert.strictEqual(ruleOf(".mev-lg .mev-tick.mev-req"), "width: " + x(s.tickH) + "rem; " +
        "transform: translate(-50%, 50%) translateX(" + x(s.tickyReq) + "rem);",
        "the req tick's cross-span + X nudge scale, and the WHOLE transform is restated");
    assert.strictEqual(ruleOf(".mev-lg .mev-tick.mev-cur"), "width: " + x(s.tickHC) + "rem; " +
        "transform: translate(-50%, 50%) translateX(" + x(s.tickyCur) + "rem);",
        "the cur tick's own cross-span + X nudge scale independently of the req tick's");
    assert.strictEqual(ruleOf(".mev-lg .mev-cap.lf"),
        "transform: translateY(50%) " + clr + " translateX(" + x(s.capxReq) + "rem);",
        "r1-r3 keep their translateY(50%) centring term and scale BOTH x terms (clearance + trim)");
    assert.strictEqual(ruleOf(".mev-lg .mev-cap.tp"),
        "transform: " + clr + " translateX(" + x(s.capxR4) + "rem);",
        "r4 scales both x terms and gains no y term");
    assert.strictEqual(ruleOf(".mev-lg .mev-cap.bt"),
        "transform: " + clr + " translateX(" + x(s.capxCur) + "rem);",
        "the current caption scales both x terms and gains no y term");
    assert.strictEqual(ruleOf(".mev-lg .mev-cap .mev-ico"), "margin-left: " + x(s.icoGap) + "rem;",
        "the icon gap is an x-length");
    // The Large twins of the per-icon ink-gap-parity overrides, pinned as LITERALS (not re-derived
    // from x()/icoGap): they are their own hand-calibrated correction, same as the horizontal
    // sibling's .mp-lg .mp-cap.dn .mp-ico.bm/.mk twins.
    assert.strictEqual(ruleOf(".mev-lg .mev-cap .mev-ico.bm"), "margin-left: 1.671rem;",
        "the bm ink-gap-parity Large twin must be the literal 1.671rem");
    assert.strictEqual(ruleOf(".mev-lg .mev-cap .mev-ico.mk"), "margin-left: -1.333rem;",
        "the mk ink-gap-parity Large twin must be the literal -1.333rem");
    // The delta's transform mixes an x gap with a y nudge: the x scales, the y is restated VERBATIM
    // (the root font already has it). Same shape as the shipped MoEEfficiency.css:459 twin, whose
    // x term is this very 4.2 -> 5.6.
    assert.strictEqual(ruleOf(".mev-lg .mev-cap.bt .mev-d"),
        "transform: translate(" + x(-Math.round(s.dGap * s.dFS * 100) / 100) + "rem, " + s.dY + "rem);",
        "the delta's x gap scales while its y nudge is restated verbatim");

    // --- 5. NOTHING y/uniform may appear under .mev-lg -- the root font already scales it, so a
    // rule here would DOUBLE-APPLY SIZE_F.
    const lgRules = emit.match(/\.mev-lg [^{}]*\{[^{}]*\}/g) || [];
    // Exactly 20, and pinned: root, track, backdrop, the per-row STRIP flush override (.mev-bd,
    // an x-length left/width -- the visible dither's minimap-facing edge), the two ticks, the three
    // captions, the icon gap, its two per-icon ink-gap-parity twins (bm/mk), the delta gap -- PLUS
    // the six the icon_gap_tuner.html per-mark pass added: three per-row block-gap overrides
    // (.mev-cap.lf.r1/.r2/.r3) and three per-mark lever overrides (.mev-cap .mev-ico.mk1/.mk2/.mk3)
    // -- PLUS the one 2026-08-12 backdrop-widen pass added: .mev-bd-5's own Large left/width
    // override (current-damage +50%, right-edge-pinned -- see the static rule's own comment).
    // .mev-bd-1's own +25% Large override was REVERTED (2026-08-12 fine-tuning round, an overshoot)
    // back to the shared .mev-lg .mev-bd rule, dropping the count from 21 to 20. The 2026-08-12
    // mark-requirement NARROWING pass briefly added three more (.mev-bd-2/3/4's own Large
    // left/width overrides, 2/3 width, right-edge-pinned, bringing the count to 23), but that
    // narrowing left their right edge ~11.87rem short of the shared 17.067rem AND left the
    // box-relative WIDE checker-dither mask too little room to taper to a point -- a crop, not a
    // fix. The 2026-08-17 crop fix REVERTED all three back to the shared .mev-lg .mev-bd rule
    // (same move as bd-1's own revert above), dropping the count back to 20. A rule appearing or
    // vanishing beyond that must be deliberate.
    assert.strictEqual(lgRules.length, 20,
        "the .mev-lg block must declare exactly 20 rules, found " + lgRules.length);
    const lgDecls = lgRules.join("");
    assert.ok(!/(font-size|line-height|height:|padding|margin-top|margin-bottom|animation|background|translateY\(-?[0-9.]+rem\))/
        .test(lgDecls),
        "no y/uniform length may be restated inside the .mev-lg block: " + lgDecls);
    assert.ok(!/@keyframes[^{]*mev-lg|\.mev-lg[^{}]*\{[^{}]*\}\s*@keyframes/.test(emit),
        "no @keyframes may live inside the .mev-lg block (the slide is a y length)");
}
// --- THE DASH GRID'S DIRECTION, PERIOD AND TILE SIZE, scoped to .mev-track::after with comments
// stripped. The grid was inherited at the HORIZONTAL bar's 90deg + `background-size: 3rem 100%`,
// where the period runs ACROSS a 3rem-wide track -- narrower than one 3rem period, so it rendered
// as a single stripe rather than a mask. 0deg ("to top") puts the first stop at the track's BOTTOM
// edge and runs the period ALONG the axis, matching the sibling vertical PROGRESS tuner. The
// TRANSPOSED `background-size: 100% <period>rem` tiles the pattern from a <period>rem TILE instead
// of rasterizing the gradient across the whole element -- dropping `background-size` altogether (the
// prior fix) left the sampler smearing each dash's ink over ~4 device px instead of a crisp 2. Re-
// derived here from the knobs, not read back out of the emit, and asserted as the WHOLE declaration
// body of the owning rule.
{
    const emit = decl(css), s = EFF.st;
    const hexA = (hex, a) => { const n = parseInt(hex.slice(1), 16);
        return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + a + ")"; };
    const c = hexA(s.dashCol, s.dashA), g = s.gapA > 0 ? hexA(s.gapCol, s.gapA) : "transparent";
    const grad = "repeating-linear-gradient(0deg," + c + " 0rem," + c + " " + s.dashW + "rem," +
        g + " " + s.dashW + "rem," + g + " " + (s.dashW + s.dashGap) + "rem)";
    const period = s.dashW + s.dashGap;
    const bdr = "0 0 0 " + s.bdrW + "rem " + hexA(s.bdrCol, s.bdrA);
    const grid = (emit.match(/(?:^|\})\s*\.mev-track::after\s*\{([^{}]*)\}/) || [])[1];
    assert.ok(grid, ".mev-track::after is missing from the emit");
    assert.strictEqual(grid.replace(/\s+/g, " ").trim(),
        'content: ""; position: absolute; left: 0; top: 0; width: 100%; height: 100%; z-index: 1; ' +
        "background-image: " + grad + "; background-size: 100% " + period + "rem; " +
        "box-shadow: " + bdr + ";",
        ".mev-track::after must spell the 0deg grid with its period in the gradient's own rem " +
        "stops AND a transposed `background-size: 100% " + period + "rem` tile");
    assert.ok(!/90deg/.test(emit), "no 90deg gradient may survive anywhere in the emit");
    assert.ok(!new RegExp(period + "rem 100%").test(emit),
        "the HORIZONTAL form `" + period + "rem 100%` must NOT appear anywhere -- a silent " +
        "transposition back to the x-period tiling would be invisible to a bare presence check");
    // The gap stripe's alpha is NOT in scope and must stay exactly as tuned (opaque here; the
    // sibling progress tuner's 0.5 is its own tuned default).
    assert.strictEqual(s.gapA, 1, "the dash GAP alpha must stay 1 -- out of scope, do not retune");
}

console.log("check_eff_vertical: tuner assertions passed (" +
    css.split("\n").length + " lines emitted, mmGap default " + mmGapKnob.val +
    "px, bottomGap default " + bottomGapKnob.val + "px, crossPad " + pad + "rem)");

// ================================================================================================
// THE ARTIFACT TWIN. Regenerate it in-memory (same build() the checked-in file was written by)
// and diff against what's on disk -- a stale twin (tuner edited, artifact not regenerated) fails
// here instead of drifting silently.
// ================================================================================================
const freshArtifact = makeArtifact.build();
const diskArtifact = fs.readFileSync(makeArtifact.OUT, "utf8");
assert.strictEqual(diskArtifact, freshArtifact,
    "eff_bar_tuner_vertical.artifact.html is STALE -- re-run " +
    "`node tools/dev/make_eff_vertical_artifact.js` after editing the tuner");

// 1) no document-skeleton tags at all, and exactly one <title> with the required text.
const skeletonTags = ["<!doctype", "<html", "<head", "<body", "</html>", "</head>", "</body>"];
skeletonTags.forEach((tag) => {
    assert.ok(diskArtifact.toLowerCase().indexOf(tag) < 0,
        "artifact twin must carry NO document-skeleton tag: found " + tag);
});
const titleMatches = diskArtifact.match(/<title>[\s\S]*?<\/title>/g) || [];
assert.strictEqual(titleMatches.length, 1, "artifact twin must carry exactly one <title>");
assert.strictEqual(titleMatches[0], "<title>" + makeArtifact.ARTIFACT_TITLE + "</title>",
    "artifact twin's <title> must be exactly '" + makeArtifact.ARTIFACT_TITLE + "'");

// 2) under 16 MB.
const artifactBytes = Buffer.byteLength(diskArtifact);
assert.ok(artifactBytes < 16 * 1024 * 1024,
    "artifact twin must be under 16 MB, is " + artifactBytes + " bytes");

// 3) zero external refs. Base64 payloads are stripped FIRST (any run of 80+ base64-alphabet
// chars) so payload bytes can never produce a false-positive match -- the payloads are font/PNG/
// JPEG data: URIs and cannot legitimately contain "http://" etc. as a real substring anyway, but
// this is the belt-and-suspenders the task asked for.
const scrubbed = diskArtifact.replace(/[A-Za-z0-9+/=]{80,}/g, "<PAYLOAD>");
const extPatterns = [
    ["http://", /http:\/\//g],
    ["https://", /https:\/\//g],
    ["protocol-relative // in src/href/url", /(src|href|url)\s*[=(]\s*["']?\/\//g],
    ["fetch(", /\bfetch\s*\(/g],
    ["XMLHttpRequest", /XMLHttpRequest/g],
    ["WebSocket", /WebSocket/g],
    ["@import", /@import/g],
];
extPatterns.forEach(([name, re]) => {
    const n = (scrubbed.match(re) || []).length;
    assert.strictEqual(n, 0, "artifact twin must have ZERO '" + name + "' refs, found " + n);
});

// 4) zero local-path leaks.
const leakPatterns = ["Dmytro", "C:\\Users", "D:/Games", "World_of_Tanks"];
leakPatterns.forEach((needle) => {
    const n = scrubbed.split(needle).length - 1;
    assert.strictEqual(n, 0, "artifact twin must have ZERO '" + needle + "' leaks, found " + n);
});
// Generic absolute-path scan: a drive letter is always STANDALONE (\b before it), which is what
// tells a real "C:\" apart from the tail of an ordinary word ("...side:\n", "img://") -- neither
// of those has a word boundary immediately before its single letter, so no scheme/prose
// allowlist is needed at all.
const realLeaks = scrubbed.match(/\b[A-Za-z]:[\\/]/g) || [];
assert.strictEqual(realLeaks.length, 0,
    "artifact twin must have ZERO local absolute-path leaks, found: " + JSON.stringify(realLeaks));

console.log("check_eff_vertical: artifact twin OK -- " + artifactBytes + " bytes (< 16 MB), " +
    "no skeleton tags, title correct, 0 external refs, 0 local-path leaks");
