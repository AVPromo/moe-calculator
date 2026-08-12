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
const RE = /\n\/\* ===== HAND-ADDED BLOCK (\d) OF 4[\s\S]*?\/\* ===== END HAND-ADDED BLOCK \1 ===== \*\/\n/g;
const found = shipped.match(RE) || [];
assert.strictEqual(found.length, 4, "expected exactly 4 marked HAND-ADDED regions, got " + found.length);
const stripped = shipped.replace(RE, "");
assert.strictEqual(stripped, emit,
    "the shipped CSS is NOT the emit plus only the two marked blocks -- silent drift");

// --- HAND-ADDED BLOCK 4 (the interface-scale QUANT correction) is stripped whole above and
// otherwise gets NO content check -- an approved-value retune (the 0.7rem/5.6rem delta nudge)
// could silently drift back and every assertion above would still pass. Pin the four rules verbatim.
const block4 = found.find((b) => /HAND-ADDED BLOCK 4 OF 4/.test(b));
assert.ok(block4, "no HAND-ADDED BLOCK 4 (QUANT) found");
[
    ".mp-s1 .mp-cap.up .mp-ico       { transform: translate(-1rem, -50%) translateY(0rem); }",
    ".mp-s1.mp-lg .mp-cap.up .mp-ico { transform: translate(-1.333rem, -50%) translateY(0.7rem); }",
    ".mp-s1 .mp-cap .mp-d            { transform: translate(4.2rem, 1.5rem); }",
    ".mp-s1.mp-lg .mp-cap .mp-d      { transform: translate(5.6rem, 0.7rem); }",
].forEach((line) => assert.ok(block4.includes(line),
    "HAND-ADDED BLOCK 4 missing/drifted rule: " + line));

// --- HAND-ADDED BLOCK 3 (the .mp-lg LARGE size-mode x-lengths) is stripped whole above and
// otherwise gets NO content check -- an approved x-length retune could silently drift back and every
// assertion above would still pass. Pin every rule verbatim, SCOPED to its own selector (comments
// stripped first): these values (2.667rem, 5.6rem, -1.333rem, ...) also appear inside OTHER rules'
// declarations, so a bare substring grep would pass even after the owning rule was reverted.
const block3 = found.find((b) => /HAND-ADDED BLOCK 3 OF 4/.test(b));
assert.ok(block3, "no HAND-ADDED BLOCK 3 (.mp-lg) found");
const block3Decl = block3.replace(/\/\*[\s\S]*?\*\//g, "");
const ruleIn = (text, sel) => {
    const esc = sel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const m = new RegExp(esc + "\\s*\\{([^}]*)\\}").exec(text);
    assert.ok(m, "no rule for " + sel + " in HAND-ADDED BLOCK 3");
    return m[1].replace(/\s+/g, " ").trim();
};
[
    [".mp-lg #moe-bar-box", "width: 613.333rem;"],
    [".mp-lg #moe-bar-root", "width: 400rem;"],
    [".mp-lg .mp-backdrop", "left: -106.667rem; width: 613.333rem;"],
    [".mp-lg .mp-track::after",
     "background-image: repeating-linear-gradient(90deg,rgba(236,230,218,0.16) 0rem,rgba(236,230,218,0.16) 2.667rem,rgba(13,14,16,1) 2.667rem,rgba(13,14,16,1) 4rem); background-size: 4rem 100%;"],
    [".mp-lg .mp-tick", "width: 2.667rem;"],
    [".mp-lg .mp-tick.mp-cur", "width: 2.667rem;"],
    [".mp-lg .mp-cap .mp-d", "transform: translate(5.6rem, 2.5rem);"],
    [".mp-lg .mp-ico", "transform: translate(-1.333rem, -50%);"],
    [".mp-lg .mp-cap.dn .mp-ico", "transform: translate(-1.333rem, -50%) translateY(0.25rem);"],
    [".mp-lg .mp-cap.up .mp-ico", "transform: translate(-1.333rem, -50%) translateY(0.9rem);"],
    [".mp-lg .mp-cap.dn .mp-ico.bm", "transform: translate(-1.671rem, -50%) translateY(0.4rem);"],
    [".mp-lg .mp-cap.dn .mp-ico.mk", "transform: translate(1.333rem, -50%) translateY(0.25rem);"],
].forEach(([sel, expected]) => assert.strictEqual(ruleIn(block3Decl, sel), expected,
    "HAND-ADDED BLOCK 3 rule drifted: " + sel));

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

console.log("MoEEfficiency.css OK: emit (" + Buffer.byteLength(emit) + " B) + 4 marked blocks = " +
            Buffer.byteLength(shipped) + " B; twin matches; backdrop 460x96 @ (-80,-40); bar 300rem");
