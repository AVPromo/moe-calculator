/* check_vertical_css_handedits.js -- the emit-vs-shipped DIFFER for the two vertical stylesheets
 * (MoEProgressVertical.css, MoEEfficiencyVertical.css). Each shipped file is its tuner's emit PLUS
 * exactly its own marked hand-edits (see each file's own header, "HAND-EDIT n/N" -- MoEProgressVertical.css
 * carries SIX, MoEEfficiencyVertical.css FIVE); until now those were enforced only by a comment, so
 * a careless re-emit-and-paste silently reverts them with no signal. This makes them a real gate: it
 * re-derives EACH hand-edit from a FRESH emit via a pinned, ordered text edit (the same
 * anchor-and-replace idiom the two check_*_js.js gates use for their MUTATIONS tables), then asserts
 * the fully-edited result is byte-identical (comments and blank lines aside) to the shipped file.
 * Any OTHER drift -- anything not one of the documented edits -- fails this same final comparison.
 *
 *   node tools/dev/check_vertical_css_handedits.js
 *   node tools/dev/check_vertical_css_handedits.js --mutate=<key>   (anti-vacuity check)
 *   node tools/dev/check_vertical_css_handedits.js --probe-all
 *   node tools/dev/check_vertical_css_handedits.js --list-mutations
 *
 * WHAT THIS ENFORCES. That the shipped MoEProgressVertical.css / MoEEfficiencyVertical.css equal
 * "a fresh tuner emit, with exactly the five documented hand-edits applied and nothing else."
 *
 * WHAT THIS DELIBERATELY DOES NOT ENFORCE.
 *   - It does not re-derive the five edits' VALUES from any other source of truth (the shim sizes,
 *     the SIZE_F/SIZE_XF factors, MM_GAP...) -- those are cross-checked elsewhere
 *     (check_bar_vertical.js / check_eff_vertical.js / the Python-side positioning tests). This gate
 *     only proves the shipped file is "emit + exactly these edits", not that the edit VALUES are
 *     themselves correct in isolation.
 *   - It does not touch the horizontal siblings (MoEProgress.css / MoEEfficiency.css) or their own
 *     hand-edit sets -- out of scope for this task; a future pass could extend it.
 *   - It does not validate the PROSE of either file's header/comments -- comments are stripped
 *     before the final comparison specifically so a header rewrite (this file's own diff shows one)
 *     never fails the gate.
 *
 * TWO TRAPS THIS GATE IS BUILT AROUND (both hit once verifying this by hand):
 *   - `.mpv-track::after` / `.mev-track::after`'s opaque gap alpha lives in the rule's GRADIENT stops
 *     only; the box-shadow RING in the same rule is legitimately rgba(...,0.5) and must not move --
 *     the edit below is scoped to the gradient stops text alone.
 *   - `.mpv-lg` / `.mev-lg` legitimately appear inside the HAND-EDIT comments that document the
 *     rename, so the final "no live .mpv-lg/.mev-lg selector remains" check strips comments FIRST.
 */
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

const REPO = path.join(__dirname, "..", "..");
const WIDGET = path.join(REPO, "src", "res", "gui", "gameface", "mods", "14th_ua", "MoECalculator");

const counts = { passed: 0, failures: [] };
function eq(what, a, b) {
    if (a === b) { counts.passed += 1; return; }
    counts.failures.push(what + ":\n    got:  " + JSON.stringify(a) + "\n    want: " + JSON.stringify(b));
}
function ok(what, cond) { eq(what, !!cond, true); }

function stripComments(css) { return css.replace(/\/\*[\s\S]*?\*\//g, ""); }
function normalize(css) {
    return stripComments(css).split("\n").map((l) => l.trim()).filter(Boolean).join("\n");
}

// The same anchor-and-replace idiom as check_progress_js.js's applyMutation: PIN the exact input
// text (so a tuner change that alters this rule's shape is caught, not silently skipped) before
// producing the edited output.
function edit(text, from, to, label) {
    if (text.indexOf(from) < 0) {
        counts.failures.push("EDIT ANCHOR NOT FOUND (" + label +
            ") -- the fresh emit no longer matches this hand-edit's documented input shape");
        return text;
    }
    return text.replace(from, to);
}

// --- fresh emits ------------------------------------------------------------------------------
function freshProgressCss() {
    const tmp = path.join(os.tmpdir(), "check_vcss_p." + process.pid + ".css");
    execFileSync("pwsh", ["-NoProfile", "-File", path.join(__dirname, "gen_bar_tuner_vertical.ps1"),
                          "-EmitCss", "-CssOut", tmp], { cwd: REPO, encoding: "utf8" });
    const css = fs.readFileSync(tmp, "utf8");
    fs.unlinkSync(tmp);
    return css;
}

// Mirrors check_eff_vertical.js's OWN technique exactly (this tuner has no -EmitCss switch): read
// the tuner as text, cut at its "// ---- panel wiring" marker, and evaluate cssOut() against a
// self-returning stub DOM via `new Function`.
function freshEfficiencyCss() {
    const html = fs.readFileSync(path.join(__dirname, "eff_bar_tuner_vertical.html"), "utf8");
    const open = html.indexOf("<script>"), close = html.lastIndexOf("</script>");
    const full = html.slice(open + "<script>".length, close);
    const cut = full.indexOf("// ---- panel wiring");
    if (cut < 0) throw new Error("eff_bar_tuner_vertical.html: panel-wiring marker not found");
    function stubNode() {
        const n = { style: {}, textContent: "", className: "", innerHTML: "", offsetWidth: 0, offsetHeight: 0,
                    classList: { add() {}, remove() {}, contains: () => false, toggle: () => false },
                    appendChild: (c) => c, addEventListener() {}, removeEventListener() {},
                    querySelectorAll: () => [] };
        n.querySelector = () => n;
        return n;
    }
    const node = stubNode();
    const document = { head: node, body: node, getElementById: () => node, createElement: stubNode,
                       querySelector: () => node, querySelectorAll: () => [] };
    const EFF = new Function("document", "window", "navigator",
        full.slice(0, cut) + "\nreturn { cssOut: cssOut };")(document, {}, {});
    return EFF.cssOut();
}

// --- MoEProgressVertical.css's SIX hand-edits, as ORDERED [from, to, label] text edits ---------
// Applying all of a file's edits, in order, to a FRESH emit must reproduce the shipped file
// (comments/blank-lines aside). Each edit's `from` is the PINNED fresh-emit input.
const PROGRESS_EDITS = [
    // HAND-EDIT 1/6: the root rule, scoped under body.mpv and given the shipped absolute
    // positioning + z-index + pointer-events the tuner's own bare stage rule never carries.
    ['#moe-bar-root {\n  position: relative;\n  width: 3rem;\n  height: 200rem;\n' +
     '  font-family: "MoEBattle", "Arial Narrow", sans-serif;\n  text-align: center;\n  opacity: 0;\n}',
     'body.mpv #moe-bar-root {\n  position: absolute;\n  left: 0;\n  top: 0;\n  width: 3rem;\n' +
     '  height: 200rem;\n  z-index: 9000;\n  pointer-events: none;\n' +
     '  font-family: "MoEBattle", "Arial Narrow", sans-serif;\n  text-align: center;\n  opacity: 0;\n}',
     '1/6 root rule'],
    // HAND-EDIT 2/6: the sizing shim -- the tuner has no surface, so this rule does not exist in
    // the emit at all; inserted right before the backdrop rule that follows the root in both files.
    // The width is a SPLIT pad now: 46 + 70 + -4 == 112 (V_BOX_W_REM(46) + V_PAD_X_REM(70) on the
    // LEFT, where the right-anchored captions' ink lives, + V_PAD_XR_REM(-4) on the RIGHT, which
    // CLIPS the (already trimmed) backdrop's own decorative bleed a little further, down to just
    // past the track's tick overhang plus a 2px margin -- see MoEProgress.js's own note).
    ['\n.mpv-backdrop {', '\nbody.mpv #moe-bar-box { width: 112rem; height: 320rem; }\n.mpv-backdrop {',
     '2/6 sizing shim'],
    // HAND-EDIT 3/5: the dash grid's gap stripe goes OPAQUE -- SCOPED to the gradient's own stops,
    // never the box-shadow ring in the same rule (which stays 0.5, a separate knob).
    ['rgba(13,14,16,0.5) 2rem,rgba(13,14,16,0.5) 3rem)',
     'rgba(13,14,16,1) 2rem,rgba(13,14,16,1) 3rem)', '3/6 gap alpha'],
    // HAND-EDIT 4/6 + 5/6: `.mpv-lg` -> `.mp-lg` (the body class MoEBarTransient.applySize actually
    // writes, shared by both orientations) plus the box-shim's own Large twin, which -- like 2/6 --
    // the tuner never emits at all.
    ['.mpv-lg #moe-bar-root { width: 4rem; }\n' +
     // 61.333, not 90 -- V_BOX_W_REM's own knob (bdW) is trimmed 72->46 to stop the backdrop
     // covering the minimap (live-measurement-confirmed correct, keep it), so the tuner's own
     // X43(46) twin moved with it. HAND-EDIT 6i/6 below overrides this raw emit outright with a
     // LITERAL 90 (not this *4/3 figure) -- see the "to" side and MoEProgress.js's own note.
     '.mpv-lg .mpv-backdrop { left: -45.333rem; width: 61.333rem; }\n' +
     '.mpv-lg .mpv-tick.mpv-end { width: 12rem;\n  transform: translate(-50%, 50%) translateX(0rem); }\n' +
     '.mpv-lg .mpv-tick.mpv-pre { width: 12rem;\n  transform: translate(-50%, 50%) translateX(0rem); }\n' +
     '.mpv-lg .mpv-tick.mpv-proj { width: 12rem;\n  transform: translate(-50%, 50%) translateX(0rem); }\n' +
     '.mpv-lg .mpv-capR { padding-right: 8rem; transform: translateX(18.667rem); }\n' +
     '.mpv-lg .mpv-capC { padding-right: 8rem; transform: translateX(21.333rem); }\n' +
     '.mpv-lg .mpv-capP { padding-right: 8rem;\n  transform: translateY(50%) translateX(0rem); }\n' +
     '.mpv-lg .mpv-cap .mpv-ico { margin-left: 1.333rem; }\n' +
     '.mpv-lg .mpv-cap .mpv-d { margin-right: 0.467em; }\n' +
     '.mpv-lg .mpv-capR .mpv-eta { margin-left: 5.333rem; }',
     'body.mpv.mp-lg #moe-bar-root { width: 4rem; }\n' +
     // 125.333, the PRE-SIZE_F box-shim quantity (round((boxW*xf + padX + padXRLarge) * f) == 157
     // is what actually gets pushed via resizeViewRem -- see MoEProgress.js's own V_PAD_XR_REM
     // note; this shim renders in DOCUMENT rem, so the root font supplies SIZE_F a second time).
     'body.mpv.mp-lg #moe-bar-box { width: 125.333rem; }\n' +
     // HAND-EDIT 6i/6: LITERAL 90, not the tuner's own X43(46)==61.333 -- the naive *4/3 twin lands
     // the backdrop's right edge SHORT of the Large track edge by 15.667rem (see MoEProgress.js's
     // own fact-3 note); 90 lands it exactly on the minimap's edge instead.
     '.mp-lg .mpv-backdrop { left: -45.333rem; width: 90rem; }\n' +
     '.mp-lg .mpv-tick.mpv-end { width: 12rem;\n  transform: translate(-50%, 50%) translateX(0rem); }\n' +
     '.mp-lg .mpv-tick.mpv-pre { width: 12rem;\n  transform: translate(-50%, 50%) translateX(0rem); }\n' +
     '.mp-lg .mpv-tick.mpv-proj { width: 12rem;\n  transform: translate(-50%, 50%) translateX(0rem); }\n' +
     // 17rem, not 18.667 (== 14rem's old *4/3): the icon_gap_tuner.html per-mark pass reports the
     // Large block-gap LITERALLY, not normalised back to Default scale -- see 6f/6g below.
     '.mp-lg .mpv-capR { padding-right: 8rem; transform: translateX(17rem); }\n' +
     // 15.733rem, not the tuner's own X43(16)==21.333 -- HAND-EDIT 6h/6's Large-only nudge (the
     // maintainer's "move the bottom block left" request, un-halved after the 2026-08-10 correction
     // that briefly halved it on a since-disproven interface-scale theory -- see
     // MoEProgressVertical.css's own note) is a hand-tuned literal, not the *4/3 formula. Default
     // carries no nudge at all (see 6h/6's own note above, now empty of an edit).
     '.mp-lg .mpv-capC { padding-right: 8rem; transform: translateX(15.733rem); }\n' +
     '.mp-lg .mpv-capP { padding-right: 8rem;\n  transform: translateY(50%) translateX(0rem); }\n' +
     '.mp-lg .mpv-cap .mpv-ico { margin-left: 1.333rem; }\n' +
     '.mp-lg .mpv-cap .mpv-d { margin-right: 0.467em; }\n' +
     '.mp-lg .mpv-capR .mpv-eta { margin-left: 5.333rem; }',
     '4/6+5/6 Large block'],
    // HAND-EDIT 6/6: the ETA row split (Job 1: "move the ETA on top of the next mark
    // requirement") plus the marks/battles icon box-and-gap parity pass (Job 2). Replaces the OLD
    // 6/6 eta-gap retarget outright -- the tuner's own capR markup keeps both numeral+icon groups
    // on ONE row, untouched, so this whole change is shipped-only, ported here by hand.
    //
    // 6a: insert the NEW `.mpv-capEta` row right after capR, stacked above it via
    // `bottom: 100%; padding-bottom: 30rem` (== capR's own 24rem box + a 6rem visual gap), same
    // right-anchor mechanism copied verbatim from capR.
    // 15rem, not the tuner's own 14 -- the icon_gap_tuner.html block<->bar-gap pass (6f/6g below
    // is the per-mark LEVER; this is the single shared block-gap MA_V uses, so no per-mark
    // selector is needed here, just a value change on the one shared rule capEta always mirrors).
    ['.mpv-capR { bottom: 100%; padding-bottom: 6rem; padding-right: 6rem;\n' +
     '            transform: translateX(14rem); font-size: 14rem; line-height: 18rem; }',
     '.mpv-capR { bottom: 100%; padding-bottom: 6rem; padding-right: 6rem;\n' +
     '            transform: translateX(15rem); font-size: 14rem; line-height: 18rem; }\n' +
     // translateY(3rem) is the maintainer's OWN "lower the ETA row 3 device px" nudge -- a WHOLE
     // -ROW move (numeral+icon together), additive to the row's existing right-anchor translateX.
     '.mpv-capEta { bottom: 100%; padding-bottom: 30rem; padding-right: 6rem;\n' +
     '              transform: translateX(15rem) translateY(3rem); font-size: 14rem; line-height: 18rem; }',
     '6a/6 capEta row inserted'],
    // 6b: split the old combined capR-scoped Y-nudge rules into per-row copies (same values,
    // capEta's copy governs the battles icon + eta numeral it now owns).
    ['.mpv-capR .mpv-ico { transform: translate(0rem, 0.5rem); }\n' +
     '.mpv-capR .mpv-v,\n.mpv-capR .mpv-eta { transform: translateY(-0.5rem); }',
     '.mpv-capR .mpv-ico { transform: translate(0rem, 0.5rem); }\n' +
     '.mpv-capR .mpv-v { transform: translateY(-0.5rem); }\n' +
     '.mpv-capEta .mpv-ico { transform: translate(0rem, 0.5rem); }\n' +
     '.mpv-capEta .mpv-eta { transform: translateY(-0.5rem); }',
     '6b/6 per-row Y-nudge split'],
    // 6c: NO box lever any more (2026-08-08 correction: the maintainer reverted Job 2's box resize
    // outright, "icon sizes must stay the same, adjust paddings individually") -- dmgp/moe/mk are
    // back at the tuner's own 14/17/17rem, so nothing needs editing at their box declarations at
    // all; they pass through the fresh emit untouched. The old etaGap rule/comment (the tuner's own
    // capR still emits it, unaffected -- its capR markup is untouched) is instead retargeted into
    // FOUR per-icon margin corrections (margin lever only): dmgp/moe/mk/battles each get their own
    // override, re-measured against the RESTORED boxes off the real PNGs' alpha>32 bbox (see the
    // shipped file's own note above `.mpv-cap .mpv-ico.dmgp` for the full derivation).
    ['.mpv-capR .mpv-eta { margin-left: 4rem; }',
     '.mpv-cap .mpv-ico.dmgp { margin-left: 1.253rem; }\n' +
     '.mpv-cap .mpv-ico.moe { margin-left: 0.885rem; }\n' +
     '.mpv-cap .mpv-ico.mk { margin-left: -1.25rem; }\n' +
     // 6f: the mark icon's OWN per-mark levers, hand-tuned in icon_gap_tuner.html -- replace the
     // single-residual .mk value above with three, same (0,3,0)-tie-by-source-order convention as
     // MoEProgress.css's identical split.
     '.mpv-cap .mpv-ico.mk1 { margin-left: 0.500rem; }\n' +
     '.mpv-cap .mpv-ico.mk2 { margin-left: 2.000rem; }\n' +
     '.mpv-cap .mpv-ico.mk3 { margin-left: 4.000rem; }\n' +
     '.mpv-cap .mpv-ico.battles { margin-left: 1.038rem; }',
     '6c/6+6f/6 four-icon margin corrections + per-mark levers (Default)'],
    // 6d: the new capEta row's own Large positioning (byte-identical to capR's).
    // NOTE: anchors on `.mp-lg`, not `.mpv-lg` -- edit 4/6+5/6 above (the rename) has ALREADY run
    // on this same text by the time this applies, INCLUDING that edit's own 18.667->17 change.
    ['.mp-lg .mpv-capR { padding-right: 8rem; transform: translateX(17rem); }',
     '.mp-lg .mpv-capR { padding-right: 8rem; transform: translateX(17rem); }\n' +
     // 2.4rem == 3 / SIZE_F(1.25) -- the SAME 3-device-px nudge as the Default rule above,
     // re-expressed so it renders as 3px (not 3.75) once the Large root font multiplies it.
     '.mp-lg .mpv-capEta { padding-right: 8rem; transform: translateX(17rem) translateY(2.4rem); }',
     '6d/6 capEta Large twin'],
    // 6e: the four margin corrections' own Large twins (SIZE_XF == 4/3, replacing the OLD eta-gap
    // retarget's Large twin outright).
    ['.mp-lg .mpv-capR .mpv-eta { margin-left: 5.333rem; }',
     '.mp-lg .mpv-cap .mpv-ico.dmgp { margin-left: 1.671rem; }\n' +
     '.mp-lg .mpv-cap .mpv-ico.moe { margin-left: 1.180rem; }\n' +
     '.mp-lg .mpv-cap .mpv-ico.mk { margin-left: -1.667rem; }\n' +
     // 6g: Large's own per-mark levers -- LITERAL, not this row's *4/3 (see the 4/6+5/6 note above
     // on the literal-vs-normalised reading), so 0.5/2/4 does NOT become 0.667/2.667/5.333 here.
     '.mp-lg .mpv-cap .mpv-ico.mk1 { margin-left: -1.000rem; }\n' +
     '.mp-lg .mpv-cap .mpv-ico.mk2 { margin-left: 1.000rem; }\n' +
     '.mp-lg .mpv-cap .mpv-ico.mk3 { margin-left: 3.000rem; }\n' +
     '.mp-lg .mpv-cap .mpv-ico.battles { margin-left: 1.384rem; }',
     '6e/6+6g/6 four-icon margin corrections + per-mark levers (Large)'],
    // 6h: the bottom block (current damage + delta)'s own residual X nudge -- Large ONLY
    // (2026-08-10, twice-corrected): the nudge was never meant to touch Default at all, so Default
    // is UNEDITED (matches the tuner's own capxC=16 default exactly, no entry needed here any
    // more). Its Large twin is handled inside 4/6+5/6 above, since that edit already owns the whole
    // Large block and .mpv-capC's Large line lives inside it -- see that edit's own comment for the
    // restored, un-halved value.
];

const EFFICIENCY_EDITS = [
    // HAND-EDIT 1/5 + 2/5: the root rule's id normalised to the shipped #moe-bar-root, scoped under
    // body.mev, and its minimap-placement PREVIEW (right/bottom) dropped for the shipped left:0;top:0
    // origin (positioning is Python's, never CSS's).
    ['#mev-bar-root {\n  position: absolute;\n  right: 639px;\n  bottom: 28px;\n  width: 3rem;',
     'body.mev #moe-bar-root {\n  position: absolute;\n  left: 0;\n  top: 0;\n  width: 3rem;',
     '1/5+2/5 root rule'],
    // ...and every OTHER #mev-bar-root occurrence (the run/band/pulse rules, the Large block) is
    // normalised to the same shipped id -- "THROUGHOUT", per the file's own header.
    ['#mev-bar-root', '#moe-bar-root', '1/5 id rename (remaining occurrences)', "all"],
    // HAND-EDIT 3/5: the sizing shim, inserted right before the backdrop rule -- the tuner has no
    // surface, so this does not exist in the emit at all.
    // Width is a SPLIT pad now: 54 + 52 + -6 == 100 (V_BOX_W_REM(54) + V_PAD_X_REM(52) on the LEFT,
    // this bar's true extreme (.mev-cap.bt, current damage + delta) needs its ink, + V_PAD_XR_REM
    // (-6) on the RIGHT, which CLIPS the (already trimmed) backdrop's own bleed a little further,
    // down to just past the track's tick overhang plus a 2px margin -- see MoEEfficiency.js's own
    // note).
    ['\n.mev-backdrop {', '\nbody.mev #moe-bar-box { width: 100rem; height: 318rem; }\n.mev-backdrop {',
     '3/5 sizing shim'],
    // HAND-EDIT 4/5 + 5/5: `.mev-lg` -> `.mp-lg`, plus the box-shim's own Large twin the tuner never
    // emits -- the PRE-SIZE_F quantity (72 + 52 + -8.667 == 115.333; round(115.333 * SIZE_F) == 144
    // is what actually gets pushed via resizeViewRem -- see MoEEfficiency.js's own V_PAD_XR_REM
    // note).
    ['.mev-lg #moe-bar-root { width: 4rem; }',
     'body.mev.mp-lg #moe-bar-root { width: 4rem; }\nbody.mev.mp-lg #moe-bar-box { width: 115.333rem; }',
     '4/5+5/5 Large block (root/box)'],
    ['.mev-lg ', '.mp-lg ', '4/5 remaining Large-block rename', "all"],
    // 5i: the backdrop's OWN Large width, overridden with a LITERAL 98, not the tuner's own
    // X43(54)==72 (already renamed to .mp-lg by the edit above; V_BOX_W_REM's trim to 54 is
    // live-measurement-confirmed correct -- see MoEEfficiency.js's fact 3, keep it). The naive *4/3
    // twin lands the backdrop's right edge SHORT of the Large track edge by 13rem (see
    // MoEEfficiency.js's own note); 98 lands it exactly on the minimap's edge instead.
    ['.mp-lg .mev-backdrop { left: -53.333rem; width: 72rem; }',
     '.mp-lg .mev-backdrop { left: -53.333rem; width: 98rem; }',
     '5i/5 backdrop Large width'],
    // 5h: the top block (r4/.tp, the 100% requirement) and bottom block (.bt, current damage +
    // delta)'s own residual X nudge -- CANCELLED (2026-08-10, third correction): the maintainer's
    // follow-up ("4px / 7px RIGHT on Large") is the exact opposite of the un-halved LEFT nudge this
    // table carried a moment ago, and verified-by-Decimal cancels it exactly (11.467+3.2==14.667,
    // 11.733+5.6==17.333 -- see MoEEfficiencyVertical.css's own note). Large now matches the tuner's
    // own capxR4=11 / capxCur=13 defaults (X43'd) exactly too, so no entry is needed here at all any
    // more -- neither Default nor Large diverges from the fresh emit for this pair of rules.
];

function applyEdits(css, edits) {
    for (const [from, to, label, mode] of edits) {
        if (mode === "all") {
            if (css.indexOf(from) < 0) {
                counts.failures.push("EDIT ANCHOR NOT FOUND (" + label + ")");
                continue;
            }
            css = css.split(from).join(to);
        } else {
            css = edit(css, from, to, label);
        }
    }
    return css;
}

function run(mutation) {
    // CRLF-normalised on read: the shipped files are CRLF on disk (this repo's checkout), the fresh
    // emits are LF-only, and both the mutation table's string anchors below and the final
    // normalize() compare need ONE line-ending convention to agree on.
    let progressShipped = fs.readFileSync(path.join(WIDGET, "MoEProgressVertical.css"), "utf8")
        .replace(/\r\n/g, "\n");
    let efficiencyShipped = fs.readFileSync(path.join(WIDGET, "MoEEfficiencyVertical.css"), "utf8")
        .replace(/\r\n/g, "\n");
    // Anti-vacuity: apply ONE surgical mutation to the SHIPPED text in memory before comparing,
    // mirroring the two check_*_js.js gates' own --mutate mechanism (there is no "source" to
    // fixture here beyond the shipped files themselves).
    if (mutation) {
        const table = {
            "p-gap-alpha-reverted": [() => { progressShipped = progressShipped.replace(
                "rgba(13,14,16,1) 2rem,rgba(13,14,16,1) 3rem)", "rgba(13,14,16,0.5) 2rem,rgba(13,14,16,0.5) 3rem)"); }],
            "p-lg-class-restored": [() => { progressShipped = progressShipped.replace(
                "body.mpv.mp-lg #moe-bar-root", ".mpv-lg #moe-bar-root"); }],
            "p-box-shim-dropped": [() => { progressShipped = progressShipped.replace(
                "body.mpv #moe-bar-box { width: 112rem; height: 320rem; }\n", ""); }],
            "e-root-scope-dropped": [() => { efficiencyShipped = efficiencyShipped.replace(
                "body.mev #moe-bar-root {", "#moe-bar-root {"); }],
            "e-lg-box-twin-dropped": [() => { efficiencyShipped = efficiencyShipped.replace(
                "body.mev.mp-lg #moe-bar-box { width: 115.333rem; }\n", ""); }],
            "e-lg-class-not-renamed": [() => { efficiencyShipped = efficiencyShipped.replace(
                ".mp-lg .mev-track { width: 4rem; }", ".mev-lg .mev-track { width: 4rem; }"); }],
        };
        if (!table[mutation]) {
            console.error("unknown mutation '" + mutation + "'; --list-mutations to see them");
            process.exit(2);
        }
        table[mutation][0]();
    }

    const freshP = freshProgressCss();
    // The efficiency tuner's cssOut() leads with `body { margin: 0; }` -- its OWN stage-preview
    // convenience (the tuner's document needs the reset; the real MoEEfficiencyView.html document
    // does not, and never carried it). This is a PORT-TIME drop, not one of the five documented
    // hand-edits, so it is peeled off here rather than added to the edit table.
    const freshE = freshEfficiencyCss().replace("body { margin: 0; }\n", "");

    const editedP = applyEdits(freshP, PROGRESS_EDITS);
    const editedE = applyEdits(freshE, EFFICIENCY_EDITS);

    eq("MoEProgressVertical.css == fresh emit + exactly its 6 hand-edits",
        normalize(editedP), normalize(progressShipped));
    eq("MoEEfficiencyVertical.css == fresh emit + exactly its 5 hand-edits",
        normalize(editedE), normalize(efficiencyShipped));

    // Named absence checks, comments stripped first (.mpv-lg/.mev-lg are legitimately named INSIDE
    // the HAND-EDIT comments that document the rename).
    ok("no live .mpv-lg selector remains in the shipped progress sheet",
        !/\.mpv-lg\b/.test(stripComments(progressShipped)));
    ok("no live .mev-lg selector remains in the shipped efficiency sheet",
        !/\.mev-lg\b/.test(stripComments(efficiencyShipped)));
    ok("no live #mev-bar-root id remains in the shipped efficiency sheet",
        !/#mev-bar-root\b/.test(stripComments(efficiencyShipped)));

    // Axis pin for the progress sheet's dash grid -- mirrors check_eff_vertical.js's own pair
    // exactly. A silent transposition back to the horizontal bar's `<period>rem 100%` x-tiling form
    // would still smear the dash ink (the original bug) and is invisible to a bare presence check,
    // so this asserts BOTH the correct Y-tiling form is present AND the horizontal form is absent.
    const progressNoComments = stripComments(progressShipped);
    const trackAfterDecl = (progressNoComments.match(/\.mpv-track::after\s*\{([^{}]*)\}/) || [])[1] || "";
    ok(".mpv-track::after declares the Y-tiling background-size: 100% 3rem",
        /background-size:\s*100% 3rem\s*;/.test(trackAfterDecl));
    ok("the horizontal x-tiling form `3rem 100%` never appears anywhere in the progress vertical sheet",
        !/3rem 100%/.test(progressNoComments));
    ok(".mp-lg declares no background-size (the dash period is a Y-length the root font already scales)",
        !/\.mp-lg[^{}]*\{[^{}]*background-size/.test(progressNoComments));
}

// --- main / report (same shape as the two check_*_js.js gates) --------------------------------
const arg = process.argv.slice(2).join(" ");
const MUTATION_KEYS = ["p-gap-alpha-reverted", "p-lg-class-restored", "p-box-shim-dropped",
                       "e-root-scope-dropped", "e-lg-box-twin-dropped", "e-lg-class-not-renamed"];
if (/--list-mutations/.test(arg)) { console.log(MUTATION_KEYS.join("\n")); process.exit(0); }

if (/--probe-all/.test(arg)) {
    const { execFileSync: exec } = require("child_process");
    let survived = 0;
    for (const key of MUTATION_KEYS) {
        let out = "", code = 0;
        try {
            out = exec(process.execPath, [process.argv[1], "--mutate=" + key], { encoding: "utf8" });
        } catch (e) { out = String(e.stdout || "") + String(e.stderr || ""); code = e.status; }
        const caught = code === 0 && /failed/.test(out);
        console.log("  " + (caught ? "caught    " : "SURVIVED  ") + key);
        if (!caught) survived += 1;
    }
    console.log("\nvertical CSS hand-edit differ probes: " + MUTATION_KEYS.length +
               " | caught: " + (MUTATION_KEYS.length - survived) + " | survived: " + survived);
    process.exit(survived ? 1 : 0);
}

const key = (/--mutate=([\w-]+)/.exec(arg) || [])[1] || null;
run(key);
if (counts.failures.length) {
    console.log(counts.failures.map((f) => "  FAIL  " + f).join("\n"));
    console.log("\n" + (key ? "MUTATED (" + key + ")" : "vertical CSS hand-edit differ") +
               ": " + counts.failures.length + " failed, " + counts.passed + " passed");
    process.exit(key ? 0 : 1);
}
console.log((key ? "MUTATED (" + key + ")" : "vertical CSS hand-edit differ") +
           ": " + counts.passed + " assertions passed");
if (key) { console.log("!! VACUOUS: the mutation broke nothing."); process.exit(1); }
