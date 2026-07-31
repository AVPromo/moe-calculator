/* gf_check_shim.js -- the shared headless harness behind the two in-battle bars' JS self-checks:
 * tools/dev/check_progress_js.js (MoEProgress.js) and tools/dev/check_efficiency_js.js
 * (MoEEfficiency.js). Plain Node, zero dependencies, zero framework.
 *
 * WHY IT EXISTS. Both bars are now thin callers of ONE shared module,
 * src/res/gui/gameface/mods/14th_ua/MoECalculator/MoEBarTransient.js, and the two harnesses were
 * carrying a byte-identical copy of everything in this file (the assertion helpers, the DOM shim,
 * the virtual clock, the constant scraper, the mutation applier and the main/report block). Two
 * copies of a harness DRIFT, and a harness that has drifted silently stops asserting -- which is
 * exactly the failure `bar-tuner-selfcheck-is-not-a-gate` records.
 *
 * WHAT THE TWO COPIES DISAGREED ON, AND WHICH ONE WON. Both differences were in the efficiency
 * copy and both are STRICT GENERALISATIONS, so both are adopted here:
 *   * querySelector matches COMPOUND class selectors (".mp-tick.mp-cur", ".mp-cap.r1"). The
 *     progress copy matched one class only, which on the efficiency bar's five ticks and five
 *     captions would silently hand back the WRONG node instead of failing loudly.
 *   * offsetWidth is a WRITABLE field defaulting to 0, not a constant-0 getter. The efficiency
 *     bar's capClampPct() measures three elements, and at a hard 0 the clamp corridor is never
 *     binding -- a constant-0 getter would leave that entire section VACUOUS. Both bars' only
 *     other use of offsetWidth is the `void root.offsetWidth` forced reflow, which does not care.
 *
 * WHAT IS AND IS NOT COVERED (both harnesses). This exercises module LOGIC. There is no layout, no
 * CSS and no compositor: it cannot tell you a bar LOOKS right, whether Coherent honours
 * animation-play-state (it does -- live-confirmed), or whether the engine's size-calculation
 * fallback still clobbers the surface. Those stay live-verification items.
 */
"use strict";

const fs = require("fs");
const path = require("path");

// The widget directory, resolved from THIS file (tools/dev/lib/ -> repo root -> src/...).
const WIDGET = path.join(__dirname, "..", "..", "..", "src", "res", "gui", "gameface", "mods",
                         "14th_ua", "MoECalculator");

function read(file) { return fs.readFileSync(path.join(WIDGET, file), "utf8"); }

// --- assertions -----------------------------------------------------------------------------
// `counts` is exported as an OBJECT so the caller reads live values (a plain exported number would
// be a copy taken at require time).
const counts = { passed: 0, failures: [] };
let group = "";

function section(name) { group = name; }

function eq(what, actual, expected) {
    const a = JSON.stringify(actual), b = JSON.stringify(expected);
    if (a === b) { counts.passed += 1; return; }
    counts.failures.push(group + " / " + what + ": got " + a + ", want " + b);
}

function ok(what, cond) { eq(what, !!cond, true); }

function fail(message) { counts.failures.push(message); }

// --- the minimal DOM ------------------------------------------------------------------------
// Only what the two bars and the shared transient touch: classList (incl. toggle's 2-arg force
// form), className, style as a plain bag, textContent, innerHTML (parsed so querySelector works),
// appendChild, getElementById, offsetWidth (writable -- see the header) and
// addEventListener("animationend").
class El {
    constructor(tag) {
        this.tag = tag;
        this.id = "";
        this.children = [];
        this.style = {};
        this.textContent = "";
        this.offsetWidth = 0;
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
    set innerHTML(html) { this.children = []; parseHTML(html, this); }
    appendChild(el) { this.children.push(el); return el; }
    // Class selectors only, but COMPOUND ones (".mp-tick.mp-cur", ".mp-cap.r1") -- see the header.
    querySelector(sel) {
        const want = sel.split(".").filter(Boolean);
        for (const child of this.children) {
            if (want.every((c) => child.classList.contains(c))) return child;
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

// Tag-stack parser -- enough for the modules' innerHTML and the views' own body markup. Text nodes
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
// change that preceded it -- which is the whole point of MoEProgress.js's cold-only rAF. (The
// efficiency bar never calls rAF; its frame queue simply stays empty.)
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

// --- scraping the modules' own constants (never written down in a harness) --------------------
// Both harnesses derive the surface, the shift, the hit padding, every timing and the clamp
// corridor exactly as the modules derive them, so a RETUNE moves the harness with the module
// instead of reddening it. `src` is explicit because the constants now live in TWO files: the
// timings, the re-assert and HIT_MAGIC in MoEBarTransient.js, the per-bar BOX_*/PAD_REM (and the
// efficiency bar's clamp corridor) in the bar itself.
function jsConst(src, name, where) {
    const m = new RegExp("^const " + name + " = (-?[\\d.]+);", "m").exec(src);
    if (!m) throw new Error((where || "source") + ": const " + name + " not found");
    return Number(m[1]);
}

function jsArray(src, name, where) {
    const m = new RegExp("^const " + name + " = (\\[[^\\]]*\\]);", "m").exec(src);
    if (!m) throw new Error((where || "source") + ": const " + name + " not found");
    return JSON.parse(m[1]);
}

// `const NAME = <a>;` OR `const NAME = <a> / <b>;`. The LARGE size mode's SIZE_XF is written as the
// EXPRESSION `4 / 3` (deliberately -- it is "the rest of x2 after the root font's 1.5"), which
// jsConst's single-literal shape cannot read; and hardcoding 1.3333 in a harness is exactly the
// transcription this scraper section exists to avoid.
function jsFactor(src, name, where) {
    const m = new RegExp("^const " + name + " = (-?[\\d.]+)(?:\\s*/\\s*(-?[\\d.]+))?;", "m")
        .exec(src);
    if (!m) throw new Error((where || "source") + ": const " + name + " not found");
    return m[2] === undefined ? Number(m[1]) : Number(m[1]) / Number(m[2]);
}

// --- the document ROOT element + getComputedStyle -------------------------------------------
// The LARGE size mode's whole SIZE_F half is ONE write: MoEBarTransient.setRootFont() puts
// `base * SIZE_F` on documentElement.style.fontSize, having read `base` back ONCE through
// getComputedStyle. Neither global existed here, so that write was unobservable (and the function's
// fail-soft try/catch meant a missing documentElement looked exactly like a working shipped size).
// `base` is deliberately NOT 1: at 1 the expected value would equal SIZE_F itself, so a module that
// wrote the bare factor instead of base*factor would pass.
function makeRootFont(base) {
    const documentElement = new El("html");
    const getComputedStyle = (el) => ({ fontSize: (el === documentElement ? base : 0) + "px" });
    return { documentElement, getComputedStyle };
}

// Comments OUT before any source-text assertion. This repo has had a check satisfied by a COMMENT
// naming the trap (`unscoped-substring-assertion-is-not-an-assertion`), and both bars' prose is
// full of the very words the text rules forbid in code.
function stripComments(src) {
    return src.replace(/\/\*[\s\S]*?\*\//g, "")           // block comments
              .replace(/(^|\s)\/\/[^\n]*/g, "$1");        // line + trailing comments
}

// --- loading the real modules ---------------------------------------------------------------
// The two bars are ES modules that import OpenWG's ../../libs/model.js (NOT in this repo) and, as
// of the transient extraction, ./MoEBarTransient.js (which IS). Rather than stub a file tree and
// fight a loader, the sources are read as text, their ES module syntax is stripped, the SHARED
// TRANSIENT IS CONCATENATED FIRST (the bar's top-level `const T = createTransient(...)` and, on the
// progress bar, `const VALUE_SWAP_MS = FADE_IN_MS` both run at load and would hit the transient's
// const TDZ the other way round) and the pair is evaluated as ONE `new Function` body with every
// engine global injected as a parameter. The modules are otherwise UNMODIFIED -- the real files run.
//
// The import strip needs the `g` FLAG: each bar now has TWO import lines, and a non-global regex
// removed only the first -- leaving `import { createTransient, fmt } from "./MoEBarTransient.js";`
// in the evaluated body, where it is a syntax error. That is precisely what broke both harnesses.
function stripModuleSyntax(src) {
    return src
        .replace(/^import[^\n]*\n/gm, "")                  // OpenWG's model.js + the sibling module
        .replace(/^export\s*\{[\s\S]*?\};?[ \t]*\n/gm, "")  // the transient's re-export block
        .replace(/^export\s+/gm, "");                      // `export function createTransient`
}

function concatModules(srcs) {
    return srcs.map(stripModuleSyntax).join("\n");
}

// --- mutations ------------------------------------------------------------------------------
// Anti-vacuity: each entry breaks ONE real behaviour, and a run with it applied MUST fail. Because
// the behaviours now live in two files, an entry is [WHICH, from, to] -- WHICH keying into the
// harness's source map ("T" = MoEBarTransient.js, "B" = the bar). Naming the file is deliberate
// rather than "whichever source contains the anchor": re-homing every anchor to the file that now
// owns it is half the point of this pass, and a silent fallback would hide a mis-homed one.
function applyMutation(srcs, key, table) {
    const out = Object.assign({}, srcs);
    if (!key) return out;
    const [which, from, to] = table[key];
    if (out[which] === undefined) {
        fail("mutation '" + key + "': ANCHOR NOT FOUND -- no source keyed '" + which + "'");
        return out;
    }
    if (out[which].indexOf(from) < 0) {
        fail("mutation '" + key + "': ANCHOR NOT FOUND in source '" + which +
             "' -- re-home it to the file that owns the behaviour now");
        return out;
    }
    out[which] = out[which].replace(from, to);
    return out;
}

// --- the main / report block ------------------------------------------------------------------
//   node tools/dev/check_*_js.js
//   node tools/dev/check_*_js.js --mutate=<key>       one anti-vacuity probe
//   node tools/dev/check_*_js.js --probe-all          every probe, as a table
//   node tools/dev/check_*_js.js --list-mutations
function main(label, MUTATIONS, run) {
    const arg = process.argv.slice(2).join(" ");
    if (/--list-mutations/.test(arg)) {
        console.log(Object.keys(MUTATIONS).join("\n"));
        process.exit(0);
    }
    if (/--probe-all/.test(arg)) { probeAll(label, MUTATIONS); return; }

    const key = (/--mutate=([\w-]+)/.exec(arg) || [])[1] || null;
    if (key && !MUTATIONS[key]) {
        console.error("unknown mutation '" + key + "'; --list-mutations to see them");
        process.exit(2);
    }

    run(key);

    const tag = key ? "MUTATED (" + key + ")" : label;
    if (counts.failures.length) {
        console.log(counts.failures.map((f) => "  FAIL  " + f).join("\n"));
        console.log("\n" + tag + ": " + counts.failures.length + " failed, " +
                    counts.passed + " passed");
        // A mutated run is SUPPOSED to fail -- exit 0 so it can be scripted, but say so loudly.
        process.exit(key ? 0 : 1);
    }
    console.log(tag + ": " + counts.passed + " assertions passed");
    if (key) {
        console.log("!! VACUOUS: the mutation broke nothing. Add a check that catches it.");
        process.exit(1);
    }
}

// Run every mutation in a CHILD process (the sources are read at module load, so one process can
// only ever apply one) and print the probe table. A mutation whose anchor no longer matches counts
// as SURVIVED, not caught: an un-applied mutation proves nothing, and that is the failure mode a
// refactor introduces.
function probeAll(label, MUTATIONS) {
    const { execFileSync } = require("child_process");
    const keys = Object.keys(MUTATIONS);
    const survived = [];
    let caught = 0;
    for (const key of keys) {
        let out = "", code = 0;
        try {
            out = execFileSync(process.execPath, [process.argv[1], "--mutate=" + key],
                               { encoding: "utf8" });
        } catch (e) {
            out = String(e.stdout || "") + String(e.stderr || "");
            code = e.status;
        }
        const stale = /ANCHOR NOT FOUND/.test(out);
        if (stale) { survived.push(key + "  (anchor stale -- never applied)"); }
        else if (code === 1 || /VACUOUS/.test(out)) { survived.push(key); }
        else { caught += 1; }
        console.log("  " + (stale ? "STALE     " : survived.indexOf(key) >= 0 ? "SURVIVED  "
                                                                             : "caught    ") + key);
    }
    console.log("\n" + label + " probes: " + keys.length + " | caught: " + caught +
                " | survived: " + survived.length);
    if (survived.length) {
        console.log("VACUOUS -- these mutations broke nothing:");
        survived.forEach((s) => console.log("   - " + s));
    }
    process.exit(survived.length ? 1 : 0);
}

module.exports = {
    WIDGET, read,
    counts, section, eq, ok, fail,
    El, parseHTML, makeClock, makeRootFont,
    jsConst, jsArray, jsFactor, stripComments,
    stripModuleSyntax, concatModules, applyMutation,
    main,
};
