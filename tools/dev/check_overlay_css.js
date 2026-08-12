/* check_overlay_css.js -- the drift gate on the calculator-overlay preview tuner
 * (TASKS/refs/in-battle-overlay-tuner.html, built by tools/dev/gen_overlay_tuner.ps1).
 *
 *   node tools/dev/check_overlay_css.js        # exits non-zero on any drift
 *
 * Unlike the bar tuners, the calculator overlay has no tunable knobs to "emit" -- the tuner
 * just needs to embed the shipped MoEBattle.css VERBATIM (modulo swapping the two asset-URL
 * schemes that don't resolve from a standalone file: the @font-face src and the six img://
 * icon urls, for data: URIs). So this gate re-derives the SAME two substitutions from the live
 * shipped CSS and asserts the tuner's embedded <style> block is byte-identical to the result --
 * if MoEBattle.css changes and nobody regenerates the tuner, this fails loud.
 * It also asserts the frozen DOM still contains the row-3/countedAssist markup (the old tuner
 * had none) and does NOT contain the old, already-fixed per-row backdrop architecture
 * (.mb-row::before / negative margin-bottom pitch) that MoEBattle.css moved away from.
 */
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

const REPO = path.join(__dirname, "..", "..");
const TUNER = path.join(REPO, "TASKS", "refs", "in-battle-overlay-tuner.html");
const SHIPPED = path.join(REPO, "src", "res", "gui", "gameface", "mods", "14th_ua",
                          "MoECalculator", "MoEBattle.css");

if (!fs.existsSync(TUNER)) {
    console.error("no tuner at " + TUNER + "\nrun `pwsh tools/dev/gen_overlay_tuner.ps1` first");
    process.exit(2);
}
const tuner = fs.readFileSync(TUNER, "utf8");
let shipped = fs.readFileSync(SHIPPED, "utf8");

// --- extract the tuner's embedded <style> block -----------------------------------------------
const styleMatch = /<style>\n([\s\S]*?)\n<\/style>/.exec(tuner);
assert.ok(styleMatch, "no <style> block found in the tuner");
const embedded = styleMatch[1];

// --- re-derive substitution 1 (the @font-face src) from the live CSS, exactly as the
// generator does, and assert the tuner's font src is the SAME re-derivation -- not just "some"
// data: URI (a stale base64 blob from an older MoEBattle.ttf would otherwise pass silently).
const fontRe = /src:\s*url\(MoEBattle\.ttf\)\s*format\("truetype"\),\s*\r?\n\s*url\("coui:\/\/[^"]*"\)\s*format\("truetype"\);/;
assert.ok(fontRe.test(shipped), "shipped MoEBattle.css's @font-face src pattern not found -- drifted");
const ttfPath = path.join(REPO, "src", "res", "gui", "gameface", "mods", "14th_ua",
                          "MoECalculator", "MoEBattle.ttf");
const fontB64 = fs.readFileSync(ttfPath).toString("base64");
shipped = shipped.replace(fontRe, 'src: url(data:font/ttf;base64,' + fontB64 + ') format("truetype");');

// --- re-derive substitution 2 (the six icon img:// urls) the same way.
const ICONS = [
    "icon_battle_condition_barrel_mark.png",
    "icon_battle_condition_improve.png",
    "icon_battle_condition_assist.png",
    "icon_battle_condition_assist_track.png",
    "icon_battle_condition_assist_radio.png",
    "icon_battle_condition_assist_stun.png",
];
for (const name of ICONS) {
    const find = "img://gui/maps/icons/personal_missions_30/quest_type/128x128/" + name;
    assert.ok(shipped.includes(find), "shipped MoEBattle.css missing icon url -- " + find);
    const iconPath = path.join(REPO, "TASKS", "refs", "icons",
        "personal_missions_30__quest_type__128x128__" + name);
    assert.ok(fs.existsSync(iconPath),
        "missing local icon asset -- " + iconPath + " (run gen_overlay_tuner.ps1 -ExtractIcons)");
    const b64 = fs.readFileSync(iconPath).toString("base64");
    shipped = shipped.replace(find, "data:image/png;base64," + b64);
}

assert.strictEqual(embedded, shipped,
    "the tuner's embedded CSS is NOT the shipped MoEBattle.css plus only the two asset-url " +
    "substitutions -- silent drift. Regenerate with `pwsh tools/dev/gen_overlay_tuner.ps1`.");

// --- DOM assertions: the frozen markup must carry the row-3/countedAssist structure ------------
const dom = tuner;
["mb-backdrop mb-bd-1", "mb-backdrop mb-bd-2", "mb-backdrop mb-bd-3",
 "mb-row-assist", "mb-ico ast spot", "mb-value mb-ast"].forEach((needle) =>
    assert.ok(dom.includes(needle), "frozen DOM missing expected markup: " + needle));

// --- absence assertions: the OLD architecture this tuner replaced must not have crept back in.
// Comments stripped first (the repo lesson `unscoped-substring-assertion-is-not-an-assertion`) --
// the shipped CSS's own prose EXPLAINS the old negative-margin bug it fixed, so a raw substring
// check on "margin-bottom" would false-positive on that comment forever.
const domNoComments = dom.replace(/\/\*[\s\S]*?\*\//g, "");
["mb-row::before", "margin-bottom", "flex-direction:column", "flex-direction: column"].forEach(
    (needle) => assert.ok(!domNoComments.includes(needle),
        "tuner has reverted to the OLD per-row backdrop architecture -- found: " + needle));

console.log("MoEBattle.css overlay tuner OK: embedded CSS matches shipped + 2 asset-url " +
            "substitutions byte-for-byte; row-3/countedAssist markup present; no stale " +
            "per-row-backdrop architecture (" + Buffer.byteLength(tuner) + " B tuner).");
