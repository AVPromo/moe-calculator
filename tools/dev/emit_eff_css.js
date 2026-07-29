/* emit_eff_css.js -- press the eff_bar_tuner's "Copy CSS" button from the command line, AND
 * assemble the SHIPPED MoEEfficiency.css from what comes out.
 *
 *   node tools/dev/emit_eff_css.js [outPath]   (default TASKS/refs/MoEEfficiency.candidate.css)
 *   node tools/dev/check_eff_css.js            # then: the independent drift gate
 *
 * TWO files are written every run, and both are named in the output because the second is an
 * OVERWRITE of a shipped source file:
 *   1. the candidate at [outPath] -- the repo's standing home for emitted-CSS candidates
 *      (TASKS/refs/, wholly gitignored; same place gen_bar_tuner.ps1 -EmitCss writes
 *      MoEProgress.css). check_eff_css.js reads it from there.
 *   2. src/.../MoECalculator/MoEEfficiency.css -- that candidate byte-for-byte, plus exactly two
 *      explicitly-marked HAND-ADDED regions (FONT and TWIN below), so the emit half is identical
 *      BY CONSTRUCTION rather than by careful copying (the repo lesson
 *      `emitcss-is-not-the-whole-shipped-stylesheet`: a naive hand-copy silently drops the
 *      hand-added blocks, and each one has already cost a client relaunch).
 * The overwrite is safe to re-run blind because of the SCHEMA-default assertion below: the output is
 * a pure function of two checked-in files (the tuner + this script), never of panel state.
 *
 * WHY. tools/dev/eff_bar_tuner.html is the single source of truth for every number in the
 * Damage Efficiency in-battle bar (TASKS/moe-efficiency-phase2.md), and the only documented way
 * to get its `MoEEfficiency.css` candidate is a browser button. An implementer working headless
 * cannot press it, and hand-copying numbers out of the note is exactly what that note forbids.
 *
 * HOW. The tuner's whole emit path -- cssOut() and every builder it calls -- is PURE in `st`,
 * and `st` is harvested generically from SCHEMA's `val` defaults (eff_bar_tuner.html:653-657).
 * So the <script> body is read as text, TRUNCATED at its "panel wiring" marker (everything past
 * that point is DOM event wiring plus the apply()/replay() render pass, none of which the emit
 * reads), and evaluated by `new Function` against the stub DOM below. Nothing is edited: the
 * tuner file is what runs, at its checked-in defaults.
 *
 * The stub is a SINGLE self-returning node, not a DOM: the truncated body only needs
 * getElementById / querySelector / querySelectorAll / createElement / head.appendChild /
 * addEventListener to not throw while capturing element handles it never uses here. (Contrast
 * check_progress_js.js, which shims a real tree because MoEProgress.js's behaviour IS the DOM
 * writes. Here the DOM is incidental.)
 *
 * IT ASSERTS EMITTED VALUES. Per the repo lesson `bar-tuner-selfcheck-is-not-a-gate`
 * (gen_bar_tuner.ps1's -SelfCheck once passed `"holdMs": true` because it only checked size and
 * leftover tokens): the trailing `meta` block is JSON.parse'd and every field is type- and
 * shape-checked -- exact key set, numbers that are actually numbers (a boolean fails `typeof`),
 * array lengths, the totalMs == fadeIn+hold+fadeOut identity, the clamp corridor's ordering. The
 * tuner's OWN selfCheck() (the axis, the band boundaries, the emitted strings) is run headless
 * here too, since it is pure apart from writing its readout into one element.
 *
 * NOT COVERED: this proves the emit reproduces, not that the bar looks right. The emit omits
 * exactly TWO things, both spliced in by FONT / TWIN below: @font-face (the tuner inlines the ttf
 * as a data: URI) and the mp-life-b/mp-run-b keyframe twin. The #moe-bar-box sizing rule IS
 * emitted -- see the emitted header comment.
 */
"use strict";

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const TUNER = path.join(__dirname, "eff_bar_tuner.html");
const OUT = process.argv[2] ||
    path.join(__dirname, "..", "..", "TASKS", "refs", "MoEEfficiency.candidate.css");
const SHIPPED = path.join(__dirname, "..", "..", "src", "res", "gui", "gameface", "mods",
                          "14th_ua", "MoECalculator", "MoEEfficiency.css");
const CUT = "// ---- panel wiring";

// --- the stub DOM: one node that answers every query with itself ----------------------------
function stubNode() {
    const n = {
        style: {}, textContent: "", className: "", innerHTML: "", offsetWidth: 0,
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

// --- load the tuner's emit path -------------------------------------------------------------
const html = fs.readFileSync(TUNER, "utf8");
const open = html.indexOf("<script>");
const close = html.lastIndexOf("</script>");
assert.ok(open >= 0 && close > open, "eff_bar_tuner.html: no <script> block found");
const full = html.slice(open + "<script>".length, close);
const cut = full.indexOf(CUT);
assert.ok(cut > 0, "eff_bar_tuner.html: the '" + CUT + "' marker is gone -- re-check the cut point");

const EFF = new Function("document", "window", "navigator",
    full.slice(0, cut) +
    "\nreturn {st:st,cssOut:cssOut,check:selfCheck,SCHEMA:SCHEMA,BANDS:BANDS};")(
    document, { EFF: null }, {});

// Defaults only: nothing above may have moved a knob (a preset button is past the cut anyway).
EFF.SCHEMA.forEach((sec) => sec[1].forEach((c) => assert.strictEqual(
    EFF.st[c.id], c.val, "knob '" + c.id + "' is not at its SCHEMA default")));

// --- the tuner's own self-check, headless ----------------------------------------------------
const green = EFF.check();
const report = node.textContent;
assert.ok(green, "the tuner's own selfCheck FAILED:\n" + report);

// --- the emit --------------------------------------------------------------------------------
const css = EFF.cssOut();
assert.ok(!/__[A-Z0-9_]+__/.test(css), "leftover __TOKEN__ placeholder in the emit");
assert.ok(!/\bundefined\b|\bNaN\b/.test(css), "the emit contains undefined/NaN");

// --- the wire contract: parse the trailing meta block and check every field -------------------
const m = /\/\* Axis \+ timings[^\n]*\n([\s\S]*?)\n\*\/\s*$/.exec(css);
assert.ok(m, "the emit does not end in the '/* Axis + timings ... */' meta block");
const meta = JSON.parse(m[1]);

const num = (v, what) => {
    assert.strictEqual(typeof v, "number", what + ": expected a number, got " + JSON.stringify(v));
    assert.ok(Number.isFinite(v), what + ": not finite (" + v + ")");
    return v;
};
const str = (v, what) => {
    assert.strictEqual(typeof v, "string", what + ": expected a string, got " + JSON.stringify(v));
    assert.ok(v.length > 0, what + ": empty string");
    return v;
};

// Exact key set: a renamed or dropped field must fail here, not silently reach the JS half.
assert.deepStrictEqual(Object.keys(meta).sort(), [
    "axis", "bands", "barStops", "boxWRem", "capClamp", "deltaFadeEasing", "deltaFadeMs",
    "deltaHoldMs", "dmgStopsSource", "fadeInMs", "fadeOutMs", "fillDurationMs", "fillEasing",
    "glyphBbox", "holdMs", "pulseMs", "slideEasingIn", "slideEasingOut", "slideRem", "totalMs",
].sort(), "meta's key set changed");

["axis", "dmgStopsSource", "slideEasingIn", "slideEasingOut", "fillEasing", "deltaFadeEasing"]
    .forEach((k) => str(meta[k], "meta." + k));

// The axis: four visually EQUAL quarters, and they are numbers.
assert.deepStrictEqual(meta.barStops, [0, 25, 50, 75, 100], "meta.barStops");
meta.barStops.forEach((v, i) => num(v, "meta.barStops[" + i + "]"));

// Timings. The identity is the point: a boolean or a string in any of the three breaks it.
["fadeInMs", "holdMs", "fadeOutMs", "totalMs", "fillDurationMs", "deltaHoldMs", "deltaFadeMs",
 "pulseMs"].forEach((k) => assert.ok(num(meta[k], "meta." + k) > 0, "meta." + k + " must be > 0"));
assert.strictEqual(meta.totalMs, meta.fadeInMs + meta.holdMs + meta.fadeOutMs,
                   "meta.totalMs is not fadeIn + hold + fadeOut");
num(meta.slideRem, "meta.slideRem");

// Bands: one per .mp-b-* class, in axis order, each with a resolved colour VALUE (Gameface drops
// a declaration whose var() cannot resolve, so a bare custom-property name here is a bug).
assert.strictEqual(meta.bands.length, EFF.BANDS.length, "meta.bands length");
meta.bands.forEach((b, i) => {
    assert.deepStrictEqual(Object.keys(b).sort(), ["cls", "colour", "name"], "meta.bands[" + i + "] keys");
    str(b.name, "meta.bands[" + i + "].name");
    assert.strictEqual(b.cls, "mp-b-" + EFF.BANDS[i].k, "meta.bands[" + i + "].cls");
    assert.ok(/^(#[0-9a-f]{6}|rgba?\([\d.,\s]+\))$/i.test(b.colour),
              "meta.bands[" + i + "].colour is not a literal colour: " + b.colour);
});

// The clamp corridor: `enabled` is the ONE field that is legitimately a boolean; both bounds are
// rem numbers and the corridor must be non-degenerate.
assert.deepStrictEqual(Object.keys(meta.capClamp).sort(), ["enabled", "leftRem", "rightRem"],
                       "meta.capClamp keys");
assert.strictEqual(typeof meta.capClamp.enabled, "boolean", "meta.capClamp.enabled");
num(meta.capClamp.leftRem, "meta.capClamp.leftRem");
num(meta.capClamp.rightRem, "meta.capClamp.rightRem");
assert.ok(meta.capClamp.rightRem > meta.capClamp.leftRem, "meta.capClamp corridor is inverted");

// The surface width the JS half pushes, and that the corridor sits inside it.
assert.ok(num(meta.boxWRem, "meta.boxWRem") > 0, "meta.boxWRem must be > 0");
assert.ok(meta.capClamp.rightRem - meta.capClamp.leftRem <= meta.boxWRem,
          "the clamp corridor is wider than boxWRem");

// Glyph bboxes: ink FRACTIONS of the 128px canvas, measured at alpha > 32, so strictly 0..1.
assert.deepStrictEqual(Object.keys(meta.glyphBbox).sort(), ["barrel_mark", "damage", "note"],
                       "meta.glyphBbox keys");
str(meta.glyphBbox.note, "meta.glyphBbox.note");
["barrel_mark", "damage"].forEach((k) => {
    const v = num(meta.glyphBbox[k], "meta.glyphBbox." + k);
    assert.ok(v > 0 && v < 1, "meta.glyphBbox." + k + " is not a 0..1 ink fraction: " + v);
});

// --- write the candidate ----------------------------------------------------------------------
fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, css);
const selectors = (css.replace(/\/\*[\s\S]*?\*\//g, "").match(/^[^@\s}][^{}]*(?=\{)/gm) || [])
    .map((s) => s.trim());
console.log("wrote " + OUT + " (" + Buffer.byteLength(css) + " bytes)");
console.log("tuner selfCheck: " + report.split("\n")[0]);
console.log("meta: " + Object.keys(meta).length + " fields checked, " + meta.bands.length +
            " bands; " + selectors.length + " rules emitted");

// --- the two hand-added blocks, and the shipped file ------------------------------------------
// The @font-face goes where MoEProgress.css keeps it: after the emit's own header comment,
// before `body { margin: 0; }`. The emit's header ends at the first "*/\n".
const cutHdr = css.indexOf("*/\n") + "*/\n".length;

const FONT = `
/* ===== HAND-ADDED BLOCK 1 OF 2 (everything else in this file is the tuner's emit, VERBATIM --
   tools/dev/emit_eff_css.js reproduces it byte-for-byte). #moe-bar-root asks for font-family
   "MoEBattle" but the tuner ran in a browser and inlined the ttf as a data: URI, so the emit
   carries no face for it; and this document does NOT <link> MoEBattle.css or MoEProgress.css
   (both would collide on the shared #moe-bar-root / .mp-* namespace). So the declaration is
   copied verbatim from MoEProgress.css:18-24 -- same family name, same single weight-600 cut,
   same bare-sibling url FIRST: Coherent resolves an @font-face src against the DOCUMENT
   directory only, so a subdir-relative path silently falls back to Arial Narrow. That is also
   why this file must sit right beside MoEBattle.ttf and checker.png (both already shipped
   siblings -- nothing new to copy). ===== */
@font-face {
    font-family: "MoEBattle";
    font-weight: 600;
    font-style: normal;
    src: url(MoEBattle.ttf) format("truetype"),
         url("coui://gui/gameface/mods/14th_ua/MoECalculator/MoEBattle.ttf") format("truetype");
}
/* ===== END HAND-ADDED BLOCK 1 ===== */
`;

const TWIN = `
/* ===== HAND-ADDED BLOCK 2 OF 2 -- a byte-identical copy of @keyframes mp-life / #moe-bar-root.mp-run
   above, renamed. NOT tuned, and no tuned value touched.
   WHY: JS restarts the transient (a hit landing while the bar is already up re-measures the
   fade-out from that event) with the classic remove-class -> force-reflow -> re-add-class idiom,
   which is UNPROVEN in Coherent/Gameface. If the engine coalesces the re-add with the run it just
   cancelled, the restart is a NO-OP -- and because #moe-bar-root rests at opacity 0 under \`both\`
   fill, that leaves the bar permanently INVISIBLE after its first appearance. That is not a
   hypothesis: it is the exact reported symptom the Moving Average bar shipped with, and
   MoEProgress.css:512-529 carries this same pair for the same reason. So MoEEfficiency.js
   ALTERNATES between .mp-run and .mp-run-b (armRun): consecutive runs carry DIFFERENT
   animation-names, which the engine cannot coalesce.
   Keep the two blocks identical: any tuner change to mp-life must be mirrored here verbatim.
   Once a launch proves the plain restart works in Coherent, delete this pair and drop armRun's
   alternation. ===== */
`;

// Lift the emitted mp-life / .mp-run pair and re-emit it under the -b names, so the twin can
// never drift from the tuner's timings by hand-editing.
const life = /@keyframes mp-life\{[\s\S]*?\}\}\n#moe-bar-root\.mp-run\{animation:mp-life \d+ms both\}\n/
    .exec(css);
assert.ok(life, "the emit's mp-life / .mp-run pair no longer matches -- re-check");
const twinRules = life[0].replace(/mp-life/g, "mp-life-b").replace(/mp-run/g, "mp-run-b");

const shipped = css.slice(0, cutHdr) + FONT + css.slice(cutHdr) + TWIN + twinRules +
                "/* ===== END HAND-ADDED BLOCK 2 ===== */\n";
fs.writeFileSync(SHIPPED, shipped);
console.log("OVERWROTE " + SHIPPED + " (" + Buffer.byteLength(shipped) +
            " bytes = the emit + the 2 marked hand-added blocks)");
