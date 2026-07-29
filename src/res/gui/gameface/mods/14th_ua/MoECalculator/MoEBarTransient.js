// 14th_ua's MoE Calculator -- the SHARED transient machinery behind both centre-screen in-battle
// bars (MoEProgress.js = Moving Average, MoEEfficiency.js = Damage Efficiency). Everything in here
// was byte-identical in the two files; only the values each bar animates were ever different.
//
// The two bars are radio ALTERNATIVES -- Python opens exactly one -- but they are SEPARATE Gameface
// DOCUMENTS, so this module is instantiated twice with no cross-talk: every piece of state below is
// a closure local of createTransient(), never a module-level variable. (Both documents already
// import ../../libs/model.js, so module resolution across this directory is proven.)
//
// EVERY BEHAVIOUR HERE COST A CLIENT RELAUNCH TO FIND. Do not "simplify" any of them:
//   * the negative-`animation-delay` debounce (armRun's seek) -- mp-life bakes fade-in, hold and
//     fade-out into ONE both-filled keyframe, so its hold CANNOT be extended in place;
//   * holding a peek open by pausing `animationPlayState` and, on release, seeking -3600ms;
//   * deriving the peek phase from ELAPSED TIME (plateauAt + HOLD_MS), never from a `showing` flag
//     -- `showing` stays true through the whole fade-out, so a flag-based branch pins the bar at
//     partial opacity;
//   * the mp-run <-> mp-run-b identity alternation, so consecutive runs never share an
//     animation-name for the engine to coalesce a restart with;
//   * the fallback end timer, without which one missing animationend wedges `showing` true forever
//     and the bar shows once and never again;
//   * the POST-DEADLINE surface re-assert -- the engine's default-view-size fallback runs LAST and
//     WINS, so only a late re-assert puts the surface right (see SURFACE_REASSERT_MS).
// The rewind before a COLD show, and the value commit after one, are the two things that DO differ
// between the bars: they are the onRewind / onCommit hooks, not flattened away.
//
// The battle windows have NO hot-reload (they pin their resources at client launch), so every tweak
// here costs a full client relaunch: tune in the browser, not in the client.

// --- the transient's timings, from the bars' CSS trailing JSON `meta` blocks -------------------
// Kept as constants rather than read from the CSS: Gameface gives no reliable way to read a
// keyframe's stops, and these numbers ARE the contract with BOTH stylesheets (whose mp-life is
// identically tuned). If a timing changes in a tuner, change it here too.
// Declared as bare `const` and re-exported below so a plain `^const NAME = <int>;` scrape still
// finds them (the mirror tests and the dev harnesses read these out of the source text).
const FADE_IN_MS = 600;              // meta.fadeInMs == the 9.68% keyframe stop of mp-life
const HOLD_MS = 5000;                // meta.holdMs
const FADE_OUT_MS = 600;             // meta.fadeOutMs (== fadeInMs in both tuned JSONs)
const TOTAL_MS = FADE_IN_MS + HOLD_MS + FADE_OUT_MS;   // meta.totalMs == mp-life's own 6200ms

// How far to seek INTO mp-life, in ms, when arming a run (armRun turns these into a NEGATIVE
// animation-delay, which starts the animation already that far along without replaying its entry).
// Verified against the emitted keyframes (@keyframes mp-life): the stops are 0 / 9.68 / 90.32 / 100
// of a 6200ms animation, i.e. 0 / 600.16 / 5599.8 / 6200 ms.
//   600  == the 9.68% stop (within 0.2ms): opacity 1 and translateY(0rem) both COMPLETE, so the bar
//           sits exactly at the hold plateau and does not re-flash or re-slide.
//   5600 == the 90.32% stop: the instant the fade-out begins.
const SEEK_NONE = 0;
const SEEK_PLATEAU = FADE_IN_MS;
const SEEK_FADE_OUT = FADE_IN_MS + HOLD_MS;

// --- THE RE-ASSERT: LOAD-BEARING, DO NOT DELETE ---------------------------------------------
// Live-measured: the engine's size-calculation deadline expired ~2.2s after the view loaded
// (resizeViewRem at 04.8s; the `Size calculation timeout` + its "Set the default view size" action
// at 06.2s, clobbering the pushed size back to the 256x256 default -- THE FALLBACK RUNS LAST AND
// WINS, which is why pushing the size earlier can never help). A static in-flow #moe-bar-box does
// NOT satisfy the engine's measurement; that premise was tested and DISPROVEN. So this re-assert is
// the ONLY thing that puts the surface right, and it is permanent. 4000ms is comfortably past the
// observed ~2.2s.
// It is load-bearing TWICE: `settled` flips off the back of it, because the re-assert IS the event
// that makes the surface correct. Before it the surface is the 256x256 fallback -- which CLIPS the
// composition and, since Python's anchor_centred bakes a term for the real surface height
// (domain/constants.*_ANCHOR_Y_OFFSET), places the bar far too high. Delete either half and the bug
// comes back.
const SURFACE_REASSERT_MS = 4000;
// Slack between the re-assert and letting the bar show. The resize round-trips through C++
// (Window._cResized -> onSizeChanged -> bridge/bar_window._place re-reads the movable extent), so
// the surface is only correct -- and the window only re-placed -- a beat AFTER the push. 250ms is
// far more than an engine callback needs and is not user-visible: it lands ~4.25s into a battle,
// inside a window where nothing shows anyway.
const SURFACE_SETTLE_MS = 250;

// Margin on the fallback end timer so it always LOSES to a working animationend (which fires at
// exactly the run's remaining duration). Not a tuned CSS value -- pure slack.
const END_MARGIN_MS = 250;

// THE SURFACE RECT IS THE MOUSE HIT RECT -- exactly why WindowFlags.WINDOW_FULLSCREEN was rejected
// for these windows (bridge/battle_view.py). A ~480rem-wide surface across screen centre would be an
// input-stealing strip, and these bars are purely decorative and must never take input. So collapse
// the input rect with an EQUAL padding on all four sides. Confirmed against WG's own JS wrapper
// (gui-part3.pkg battle/battle_notifier/BattleNotifierView/BattleNotifierView.js): the order is
// (top, right, bottom, left, 15) -- but our four values are equal anyway, so the order is moot. Do
// NOT "clean this up" into asymmetric per-side values. Negative values are rejected, so a padding
// can only shrink the rect inward; half the LARGER dimension therefore collapses both axes to
// nothing. HIT_MAGIC mirrors WG's constant; its meaning is unknown, so the call is retried without
// it if the 5-argument form is rejected.
const HIT_MAGIC = 15;

// Two interchangeable arming classes, each bound to its OWN identically-tuned @keyframes (the
// second is each stylesheet's marked HAND-ADDED mp-life-b block), so consecutive runs never share
// an animation-name and the engine has nothing to coalesce a restart with.
const RUN_CLASSES = ["mp-run", "mp-run-b"];
const RUN_NAMES = ["mp-life", "mp-life-b"];

// Group an integer with thousands separators: 2910 -> "2,910". The tuners' fmt() at their tuned
// `comma` separator (MoEBattle.ttf carries "," and space, so both were shippable).
function fmt(n) {
    n = Math.round(Number(n) || 0);
    const sign = n < 0 ? "-" : "";
    return sign + String(Math.abs(n)).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Build one bar's transient controller.
//
//   root                          the bar's #moe-bar-root element (mp-life animates ITS transform)
//   boxLeft/boxTop/boxW/boxH      the composition's bounding box in document rem (== .mp-backdrop)
//   pad                           slack for the shadow/glow bleed, on all four sides
//   onRewind(atCurrent)           OPTIONAL. Called inside a cold show, BEFORE the run is armed, to
//                                 write the values the entry opens with (transitions suppressed).
//                                 `atCurrent` true == the Alt entry: open ALREADY committed.
//   onCommit(cold)                OPTIONAL. Called after a DAMAGE-driven cold show and after every
//                                 warm re-trigger, to retarget the animated values. `cold` says
//                                 which -- NOT cosmetic: after a cold show the run class was just
//                                 added and onRewind wrote a resting value, so the new target must
//                                 land in a LATER frame (requestAnimationFrame); a warm re-trigger
//                                 rewound nothing and sets it synchronously.
//   onEnd()                       OPTIONAL. endRun's force-settle tail.
//   onIdle()                      OPTIONAL. reset's tail (the resting/hidden state).
//
// Returns { mount, settled, show, peek, reset, disarm }.
export function createTransient(cfg) {
    const root = cfg.root;
    const nop = function () {};
    const onRewind = cfg.onRewind || nop;
    const onCommit = cfg.onCommit || nop;
    const onEnd = cfg.onEnd || nop;
    const onIdle = cfg.onIdle || nop;

    // --- the surface, and the rigid shift into it ------------------------------------------
    // A Gameface view PUSHES its own size to C++ through the `viewEnv` global
    // (viewEnv.resizeViewRem(w, h), rem == logical px); a view that never calls it gets the
    // engine's default-size fallback (see SURFACE_REASSERT_MS). There is NO Python-side and NO
    // res_map lever for this (bridge/bar_window.py). The surface is the composition's box plus
    // `pad` on all four sides, and the whole composition is rigidly translated by that much so
    // NOTHING sits at a negative coordinate -- an origin overflow is clipped at ANY surface size.
    const viewW = cfg.boxW + 2 * cfg.pad;
    const viewH = cfg.boxH + 2 * cfg.pad;
    const shiftX = cfg.pad - cfg.boxLeft;
    const shiftY = cfg.pad - cfg.boxTop;      // MIRRORED (negated, plus the fraction-unit term) in
                                              // Python as domain/constants.*_ANCHOR_Y_OFFSET
    const hitPad = Math.ceil(Math.max(viewW, viewH) / 2);

    // Animation state. `showing` = the bar is visibly up (running or peek-held). `peeking` = Alt is
    // held, so the bar is pinned at the hold plateau with no fade-out. `plateauAt` = the wall-clock
    // ms at which the running animation reaches (or reached) that plateau -- the ONLY thing the
    // peek needs to know about the animation's progress, since Gameface exposes no readable
    // playback position. `dmgPlateauAt` = the same instant for the most recent DAMAGE-driven show
    // (0 == none in flight). It is a RECORD, NOT A SECOND CLOCK: `plateauAt` stays the only run
    // clock, and this only says where the damage hold that a peek interrupted would have been, so
    // peekOff can RESUME it instead of truncating it. Only ever nonzero while `showing` is true --
    // both places that clear `showing` (endRun, reset) clear it too, or a release could resurrect a
    // show that already ended.
    // `settled` = the surface has been re-asserted and is the size we asked for, so the composition
    // is neither clipped nor mis-placed. Until then the bar must NOT be shown by ANY trigger.
    let settled = false;
    let peekT = null;
    let showing = false;
    let peeking = false;
    let plateauAt = 0;
    let dmgPlateauAt = 0;

    // The live run's id, and the last id already ended. endRun is idempotent on this pair:
    // whichever of animationend / the fallback timer arrives first wins and the other becomes a
    // no-op, and a timer left over from a superseded run can never end a newer one.
    // armIdx starts at 1 -> the first armRun flips to 0, i.e. run #1 uses the emitted
    // .mp-run / mp-life pair.
    let armIdx = 1;
    let runId = 0;
    let endedId = 0;
    let endT = null;

    function disarm() {
        root.classList.remove(RUN_CLASSES[0]);
        root.classList.remove(RUN_CLASSES[1]);
    }

    // Start (or restart) mp-life, seeking `seekMs` into it. THE single arming point -- coldShow,
    // warmShow, peekOn and peekOff all funnel through here, so the restart idiom exists in exactly
    // one place. Every run gets a FRESH animation identity (alternating .mp-run / .mp-run-b) rather
    // than trusting remove -> reflow -> re-add to restart the SAME animation, an idiom never proven
    // in Coherent; the engine has nothing to coalesce the new run with. The reflow is kept anyway:
    // it costs nothing where it works. The fallback timer is armed for this run's own remaining
    // duration and calls the SAME endRun.
    function armRun(seekMs) {
        armIdx = 1 - armIdx;
        runId += 1;
        const id = runId;
        disarm();
        root.style.animationPlayState = "";
        root.style.animationDelay = seekMs ? "-" + seekMs + "ms" : "0ms";
        void root.offsetWidth;
        root.classList.add(RUN_CLASSES[armIdx]);
        clearTimeout(endT);
        endT = setTimeout(function () { endRun(id); }, TOTAL_MS - seekMs + END_MARGIN_MS);
        // THE run clock, maintained in ONE place so every arming path agrees: the seek makes the
        // run start `seekMs` in, so it reaches the plateau FADE_IN_MS - seekMs from now (in the past
        // for a seek past it). Gameface exposes no readable playback position, so this is how the
        // peek knows where the run is -- see peekOn. Only meaningful while the run is NOT paused
        // (wall-clock keeps running, the animation does not).
        plateauAt = Date.now() + FADE_IN_MS - seekMs;
    }

    // COLD SHOW: the bar is not up -> play the whole mp-life transient. `fromDamage` distinguishes
    // the data-driven entry (which owns a hold an Alt peek may interrupt and must later resume)
    // from peekOn's own entry, which IS the peek -- and it also picks which VALUES the run opens
    // with, via onRewind. The MOTION is identical either way (armRun(SEEK_NONE), the tuned fade +
    // slide).
    function coldShow(fromDamage) {
        clearTimeout(peekT);
        onRewind(!fromDamage);
        armRun(SEEK_NONE);                   // a cold show plays the entry in full (plateauAt too)
        if (fromDamage) dmgPlateauAt = plateauAt;
        showing = true;
        if (fromDamage) onCommit(true);      // cold: the target must land in a LATER frame
    }

    // WARM RE-TRIGGER (the debounce): a change arrived while the bar is ALREADY up. Do NOT replay
    // the appearance -- re-measure the DISAPPEARANCE from this event instead. mp-life bakes
    // fade-in, hold and fade-out into ONE both-filled keyframe, so its hold cannot be extended in
    // place; instead restart the animation but SEEK PAST the entry with a negative delay
    // (SEEK_PLATEAU, the 9.68% stop, where both the opacity fade and the slide have completed). The
    // bar stays visibly put and gets a fresh hold + fade-out.
    function warmShow() {
        if (!peeking) {
            armRun(SEEK_PLATEAU);        // the seek lands us AT the plateau (armRun sets plateauAt)
        }
        // THIS event's hold, remembered so an Alt release resumes it instead of discarding it
        // (peekOff). The peeking branch is the whole reason this is not just read off `plateauAt`:
        // while Alt is held we deliberately do NOT armRun (the pause must survive), so an event
        // landing mid-peek would otherwise get no hold at all and be wiped 600ms after the release.
        // Record the plateau the run WOULD have had -- SEEK_PLATEAU cancels FADE_IN_MS, so armRun's
        // clock makes that exactly now, which is also why the non-peek branch can read the
        // freshly-set plateauAt.
        dmgPlateauAt = peeking ? Date.now() : plateauAt;
        onCommit(false);                     // warm: nothing was rewound, so set the target NOW
    }

    // ALT PEEK (an ADDITIVE second show-trigger, not a gate -- the transient still fires on its own
    // when Alt is untouched). While Alt is held the bar must be pulled up and HELD with no
    // fade-out. Mechanism: play (or keep) mp-life and PAUSE it at the hold plateau, so the entry is
    // the real fade+slide and the hold simply never ends.
    function peekOn() {
        clearTimeout(peekT);
        if (!showing) {
            coldShow(false);            // full entry, then pause below once it lands
        } else if (!peeking && Date.now() >= plateauAt + HOLD_MS) {
            // ALT PRESSED DURING THE FADE-OUT -- `showing` stays true all the way through it (only
            // endRun clears it), so pausing here would pin the bar at partial opacity.
            // plateauAt + HOLD_MS is the 90.32% stop (== elapsed SEEK_FADE_OUT, see armRun's run
            // clock), so at/past it the run is already fading out and must be RE-ARMED, not paused.
            // SEEK_PLATEAU, not a cold entry: mp-life's 0% stop is opacity 0, so replaying the
            // entry from a partially-visible bar would visibly DIP it to nothing and fade up again
            // (reads as a flicker). Seeking to the plateau snaps it back to full opacity -- "caught
            // it". armRun also re-establishes the run identity, the runId guard and the endT
            // fallback, so the superseded run's animationend/timer cannot end this one.
            armRun(SEEK_PLATEAU);
        }
        peeking = true;
        // Pause once the entry has completed -- pausing mid-fade-in would freeze the bar at partial
        // opacity. If the bar was already PAST the entry the wait is 0 and it pauses on this tick.
        peekT = setTimeout(function () {
            root.style.animationPlayState = "paused";
            // A paused hold NEVER ends, so the fallback timer must not end it either. peekOff
            // re-arms a fresh run (and a fresh timer) for the fade-out -- and it does so whether or
            // not this pause ever landed, so a release that beats it is still hold-to-show.
            clearTimeout(endT);
        }, Math.max(0, plateauAt - Date.now()));
    }

    // Alt released -> fade out NOW rather than serving the rest of the hold: unpause and seek
    // straight to the 90.32% stop, so only the fade-out plays. THE PEEK IS STRICTLY HOLD-TO-SHOW,
    // so this must be true for EVERY release, including one that beats the pause -- hence the
    // MIRROR: `inLeft` is how much of the entry was still owed, and starting that far BEFORE the
    // 90.32% stop lands the run at the same opacity it was already at. A peek that did pause is
    // past the plateau, so inLeft == 0 and the seek is exactly SEEK_FADE_OUT. (An earlier build
    // bailed on `animationPlayState !== "paused"` instead, which re-armed nothing, so a
    // sub-FADE_IN_MS tap served the whole transient and read as a toggle-on with a 5s auto-hide.)
    // COSMETIC, DELIBERATELY NOT FIXED: the mirror is linear while both fade halves are ease-in, so
    // a release mid-fade-in can step opacity by up to ~0.2. Only reachable on a sub-600ms tap,
    // where the bar is barely visible at all.
    //
    // EXCEPT when the peek interrupted a DATA-driven show that still has hold left: players hold
    // Alt near-constantly (extended markers), so fading out there would truncate an event's 5s to
    // whatever was left of the peek. RESUME that hold instead, at its true elapsed position:
    // seeking (now - dmgPlateauAt) PAST the plateau makes armRun's clock re-derive
    // plateauAt == dmgPlateauAt, so the resumed run's fade-out starts at exactly the instant the
    // original hold would have -- not later. The pause is simply not credited back: the hold is
    // wall-clock, as it was before any Alt.
    function peekOff() {
        clearTimeout(peekT);
        if (!peeking) return;
        peeking = false;
        if (dmgPlateauAt + HOLD_MS > Date.now()) {
            armRun(SEEK_PLATEAU + (Date.now() - dmgPlateauAt));
            return;
        }
        const inLeft = Math.min(FADE_IN_MS, Math.max(0, plateauAt - Date.now()));
        armRun(SEEK_FADE_OUT + inLeft);
    }

    // FORCE-SETTLE, and the ONE place the "run is over" state is cleared. mp-life is both-filled so
    // the root rests at its 100% stop (opacity 0) with no help from JS; onEnd drops whatever else
    // a hold longer than the transient would have left showing.
    // `id` is the run being ended: an id that is not the live run (a timer from a superseded run) or
    // one already ended (the loser of the animationend/timer race) is ignored.
    function endRun(id) {
        if (id !== runId || id === endedId) return;
        endedId = id;
        clearTimeout(endT);
        clearTimeout(peekT);
        disarm();
        showing = false;
        peeking = false;
        dmgPlateauAt = 0;                // the hold is over -- a later release must never resume it
        root.style.animationPlayState = "";
        onEnd();
    }

    // Only the CURRENTLY armed animation's end counts. Because armRun alternates the identity, the
    // cancel/end noise of the run it just superseded reports the OTHER name and is dropped here for
    // free. A pulse on an inner element (.mp-track) never reaches this listener.
    root.addEventListener("animationend", function (e) {
        if (e.animationName !== RUN_NAMES[armIdx]) return;
        endRun(runId);
    });

    // Reset to the resting/hidden state, so a later re-show starts COLD. The caller additionally
    // drops its own change-detect baseline, so the next push becomes a fresh silent one (a
    // scoreboard opening and closing must not replay the bar).
    function reset() {
        clearTimeout(peekT);
        clearTimeout(endT);
        endedId = runId;                 // no live run left for a late animationend to end
        disarm();
        root.style.animationPlayState = "";
        root.style.animationDelay = "0ms";
        showing = false;
        peeking = false;
        dmgPlateauAt = 0;                // ditto endRun: no hold survives a hide / a new battle
        onIdle();
    }

    // Push the surface size and collapse the input rect. Feature-detected and fail-soft, like every
    // engine read in this codebase -- OpenWG's own libs/common.js touches the `viewEnv` global
    // directly and offers no resize wrapper, so this does too. Idempotent: called at mount and once
    // more after SURFACE_REASSERT_MS.
    function pushSurfaceSize() {
        if (typeof viewEnv === "undefined" || !viewEnv) return;
        try {
            // WG's own views freeze the texture across a resize (flicker, not sizing) -- e.g.
            // BattleNotifierView.js. Optional, so feature-detected like the rest.
            if (viewEnv.freezeTextureBeforeResize) viewEnv.freezeTextureBeforeResize();
        } catch (e) { /* fail-soft */ }
        try {
            if (viewEnv.resizeViewRem) viewEnv.resizeViewRem(viewW, viewH);
        } catch (e) { /* fail-soft: a clipped bar beats a dead one */ }
        if (!viewEnv.setHitAreaPaddingsRem) return;
        try {
            viewEnv.setHitAreaPaddingsRem(hitPad, hitPad, hitPad, hitPad, HIT_MAGIC);
        } catch (e) {
            // The 5th argument's meaning is unknown -- if the binding rejects the 5-arg form, the
            // 4-arg one still collapses the rect.
            try {
                viewEnv.setHitAreaPaddingsRem(hitPad, hitPad, hitPad, hitPad);
            } catch (e2) { /* fail-soft */ }
        }
    }

    // Wire the bar up, ONCE, on engine ready. Three parts, in this order:
    //
    //  (1) THE RIGID TRANSLATION (unconditional -- an origin overflow is clipped at ANY surface
    //      size, so this must happen even without viewEnv). #moe-bar-root is
    //      position:absolute;left:0;top:0 in the CSS, and moving its origin carries the in-flow
    //      .mp-track AND the abspos .mp-backdrop with it -- relative geometry stays bit-for-bit
    //      identical and NO tuned value is touched. It has to be left/top and NOT a transform:
    //      mp-life animates the root's OWN transform and would clobber one. Python cancels the
    //      shift (*_ANCHOR_Y_OFFSET) so the bar does not move on screen.
    //  (2) THE SURFACE + INPUT RECT, pushed now and RE-ASSERTED after the engine's default-size
    //      deadline. The `settled` flip is NESTED in that callback on purpose: it is the re-assert
    //      that makes the surface correct, so the dependency is structural rather than a second
    //      timer that could outlive it. It then re-renders the model we already hold, so a
    //      STILL-HELD Alt takes effect immediately -- during PREBATTLE there may be no efficiency
    //      tick to re-push it, and the player is mid-peek.
    //  (3) the model subscription and the first render.
    function mount(observer, render) {
        engine.whenReady.then(() => {
            root.style.left = shiftX + "rem";
            root.style.top = shiftY + "rem";
            pushSurfaceSize();
            setTimeout(function () {
                pushSurfaceSize();
                setTimeout(function () {
                    settled = true;
                    render(observer.model);
                }, SURFACE_SETTLE_MS);
            }, SURFACE_REASSERT_MS);
            observer.onUpdate(render);
            observer.subscribe();
            render(observer.model);
        });
    }

    return {
        mount: mount,
        // THE SHOW TRIGGERS ARE GATED ON `settled`; a caller's SILENT BASELINE must not be. Before
        // the re-assert the surface is the engine's 256x256 fallback: the bar would come up cropped
        // and badly mis-placed. A baseline shows nothing, so it costs nothing to let it run -- and
        // it MUST run, or the change-detect never gets its first value.
        settled: function () { return settled; },
        show: function () {
            if (showing) warmShow();
            else coldShow(true);
        },
        // Alt is an ADDITIVE trigger, never a gate. Re-peeking while already peeking is a no-op, so
        // a re-push that merely carries altHeld again cannot restart the hold.
        peek: function (held) {
            if (held) {
                if (!peeking && settled) peekOn();
            } else {
                peekOff();
            }
        },
        reset: reset,
        disarm: disarm,
    };
}

export {
    fmt,
    FADE_IN_MS, HOLD_MS, FADE_OUT_MS, TOTAL_MS,
    SEEK_NONE, SEEK_PLATEAU, SEEK_FADE_OUT,
    SURFACE_REASSERT_MS, SURFACE_SETTLE_MS, END_MARGIN_MS, HIT_MAGIC,
    RUN_CLASSES, RUN_NAMES,
};
