/* check_eff_css.js -- the drift gate on the shipped MoEEfficiency.css.
 *
 *   node tools/dev/check_eff_css.js        # exits non-zero on any drift
 *
 * INDEPENDENT of the generator (it does not reuse emit_eff_css.js): strip the three
 * explicitly-marked HAND-ADDED regions out of the shipped stylesheet and assert what remains is the
 * tuner's emit BYTE-FOR-BYTE. Also asserts the mp-life-b twin's stops are identical to mp-life's
 * modulo the rename, and that the shipped file contains exactly ONE BASE #moe-bar-box rule and ONE
 * @font-face DECLARATION -- grepping the raw file for "@font-face" false-positives on the emit's own
 * header prose, so the count is taken with comments stripped (the repo lesson
 * `unscoped-substring-assertion-is-not-an-assertion`).
 */
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const REPO = path.join(__dirname, "..", "..");
const EMIT = path.join(REPO, "TASKS", "refs", "MoEEfficiency.candidate.css");
const SHIPPED = path.join(REPO, "src", "res", "gui", "gameface", "mods", "14th_ua",
                          "MoECalculator", "MoEEfficiency.css");

if (!fs.existsSync(EMIT)) {
    console.error("no emit at " + EMIT + "\nrun `node tools/dev/emit_eff_css.js` first");
    process.exit(2);
}
const emit = fs.readFileSync(EMIT, "utf8");
const shipped = fs.readFileSync(SHIPPED, "utf8");

// --- strip the marked hand-added regions ----------------------------------------------------
const RE = /\n\/\* ===== HAND-ADDED BLOCK (\d) OF 3[\s\S]*?\/\* ===== END HAND-ADDED BLOCK \1 ===== \*\/\n/g;
const found = shipped.match(RE) || [];
assert.strictEqual(found.length, 3, "expected exactly 3 marked HAND-ADDED regions, got " + found.length);
const stripped = shipped.replace(RE, "");
assert.strictEqual(stripped, emit,
    "the shipped CSS is NOT the emit plus only the two marked blocks -- silent drift");

// --- the twin is the emitted pair, renamed ---------------------------------------------------
const pair = (css, suf) => {
    const m = new RegExp("@keyframes mp-life" + suf + "\\{[\\s\\S]*?\\}\\}\\n#moe-bar-root\\.mp-run" +
                         suf + "\\{animation:mp-life" + suf + " (\\d+)ms both\\}").exec(css);
    assert.ok(m, "no mp-life" + suf + " / .mp-run" + suf + " pair found");
    return m;
};
const a = pair(shipped, ""), b = pair(shipped, "-b");
assert.strictEqual(b[0].replace(/mp-life-b/g, "mp-life").replace(/mp-run-b/g, "mp-run"), a[0],
    "the mp-life-b twin has DRIFTED from mp-life");

// --- no duplicated shim / face, and the face is a bare sibling url ---------------------------
const decl = shipped.replace(/\/\*[\s\S]*?\*\//g, "");
// ANCHORED at line start on purpose: the BASE rule may exist only once (a hand-added second copy is
// the drift this guards), while the size mode's `.mp-lg #moe-bar-box` override is a scoped twin whose
// line starts with the ancestor class, not with the id.
assert.strictEqual((decl.match(/^#moe-bar-box\s*\{/gm) || []).length, 1,
    "#moe-bar-box declared twice");
assert.strictEqual((decl.match(/@font-face/g) || []).length, 1, "@font-face count");
assert.ok(/src:\s*url\(MoEBattle\.ttf\)\s*format\("truetype"\)/.test(decl),
    "the @font-face src does not lead with the BARE sibling url(MoEBattle.ttf)");
assert.ok(/font-family:\s*"MoEBattle"/.test(decl), "the face is not named MoEBattle");

// --- the JS/CSS wire contract the surface depends on ------------------------------------------
const rule = (sel) => {
    const m = new RegExp("\\" + sel + " \\{([^}]*)\\}").exec(decl);
    assert.ok(m, "no rule for " + sel);
    return m[1];
};
const bd = rule(".mp-backdrop");
[["left", "-80rem"], ["top", "-40rem"], ["width", "460rem"], ["height", "96rem"]].forEach((p) =>
    assert.ok(new RegExp(p[0] + ":\\s*" + p[1].replace(".", "\\.") + ";").test(bd),
              ".mp-backdrop " + p[0] + " is not " + p[1] + " -- MoEEfficiency.js's BOX_* are stale"));
assert.ok(/width:\s*300rem;/.test(rule("#moe-bar-root")), "#moe-bar-root width is not 300rem (BAR_W_REM)");

console.log("MoEEfficiency.css OK: emit (" + Buffer.byteLength(emit) + " B) + 3 marked blocks = " +
            Buffer.byteLength(shipped) + " B; twin matches; backdrop 460x96 @ (-80,-40); bar 300rem");
