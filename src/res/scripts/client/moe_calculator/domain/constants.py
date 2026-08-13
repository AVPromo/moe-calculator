# -*- coding: utf-8 -*-
"""Shared constants used across the domain, adapter, and view.

Centralizing them means a typo is a NameError instead of a silently mismatched value.
The mark milestone percents are the wire contract with the widget JS -- keep them in
lockstep with the MARK_PERCENTS array in the .js. 2/3-compatible, engine-free.
"""


# The three Marks of Excellence milestones, as percentiles of the vehicle's player
# population combined-damage distribution. 1 mark = 65th percentile, 2 = 85th, 3 = 95th.
# Index 0..2 <-> mark count 1..3. These positions are FIXED (the bar axis is the
# percentile 0..100), so the ticks always sit at the same spots regardless of vehicle.
MARK_PERCENTS = (65, 85, 95)

# Mark counts, parallel to MARK_PERCENTS.
MARK_COUNTS = (1, 2, 3)

# Threshold key 100 is the bar's right-edge "goalpost" -- the combined damage at the 100th
# percentile. The WG API returns it directly (percentile=100), so the normal path carries it
# as-is. GOALPOST_PERCENTILE is used ONLY by the offline estimator fallback (moe_estimate),
# which fires when a WG-API request errors: the true 100th percentile is +infinity under a
# continuous distribution, so the estimator reads the goalpost off a high-but-finite percentile.
# (Literally only there now -- the in-battle interpolator used to borrow it for its top stop;
# since it went piecewise-linear over WG's own anchors it uses the real 100 key value.)
GOALPOST_PERCENTILE = 99

# The full percentile axis the bar spans.
AXIS_MIN = 0
AXIS_MAX = 100

# The four EQUAL visual quarters the damage-efficiency bar's five damage stops
# [0, r65, r85, r95, r100] are mapped onto (see battle_builder.efficiency_bar_x). Equal quarters
# spread the crowded high requirements evenly instead of bunching them at the tail -- the same
# trick, and the same numbers, as the garage bar's percentile axis (BAR_STOPS in
# MoECalculator.js:312) and the phase-1 tuner's BAR_STOPS (tools/dev/eff_bar_tuner.html).
# THE SINGLE PLACE TO CHANGE: the requirement ticks are pinned to these positions in
# MoEEfficiency.css, so the CSS and this tuple are a wire contract.
EFFICIENCY_BAR_STOPS = (0, 25, 50, 75, 100)

# --- fetch-list working set --------------------------------------------------
# The persistent list of owned tank ids we maintain thresholds for is capped at this size
# (also the WG API's tank_id-per-request cap, so the whole list fits one batch fetch).
FETCH_LIST_CAP = 100

# A tank drops out of the fetch list if it hasn't been played within this window (the
# session-open purge). Measured against the vehicle's last-battle timestamp; a freshly bought
# tank is stamped with the purchase time so it survives ~7 days even if never played.
STALE_WINDOW_SECONDS = 7 * 24 * 3600

# Threshold data is served without refetching while now < OUR LAST FETCH TIME + this (the
# cache-freshness throttle). Single source shared by moe_wgapi.fresh_table (cache-adopt gate) and
# fetch_list.needs_refetch (the "don't refetch every session" throttle). WG refreshes the MoE
# distribution DAILY (officially confirmed) but publishes it with a ~1-2 day lag, so anchoring the
# window to WG's own `updated_at` would leave the data >24h old on arrival and refetch on every
# garage entry. We therefore anchor to when WE fetched: at 12h we re-check up to twice a day, so a
# session started in the evening still picks up WG's new daily distribution without a day-long
# lag. A fetch that reveals a changed WG `updated_at` still forces a full refetch sooner
# (fetch_list.data_changed + moe_wgapi._poll).
REVALIDATE_SECONDS = 12 * 3600

# In-battle projected-rating (EWMA) coefficient. WG's Marks rating is a moving average
# over "~50-100 battles"; we model it as an EWMA newAvg = prevAvg + k*(CD - prevAvg) with
# k = 2/(N+1), N=100 (k ~= 0.0198). N/k are community-reverse-engineered, NOT WG-confirmed
# -- treat as an assumption to validate against real replays (see TASKS/in-battle-moe-panel.md).
EWMA_N = 100
EWMA_K = 2.0 / (EWMA_N + 1)

# Variant A: the Moving-Average bar's axis floor and remaining-battles readout. The mark axis is
# hundreds-to-thousands of combined damage wide while one battle moves the EWMA by single/double
# digits, so the bar read as dead -- the floor is rescaled to where the battle actually STARTED
# (battle_builder.progress_axis_lo) and the delta caption carries a battles-remaining count
# (battle_builder.battles_to_axis_hi). Values as prototyped in tools/dev/progress_bar_variant_a.html.
PROGRESS_AXIS_MIN_WINDOW = 200.0   # combined damage; keeps the axis from collapsing
PROGRESS_ETA_CAP = 99              # readout ceiling (2 digits, see the clipping budget)

# In-battle overlay window anchor, in FIXED logical-GUI-space px. WG's efficiency panel is
# laid out in logical units (physical px / interfaceScale), so its screen corner sits at the
# SAME logical coordinate at every interface scale -- a fixed logical offset tracks it with
# NO per-scale multiplication (confirmed in-client at 1x AND 2x; the old fraction-of-space
# anchor wrongly doubled X to ~529 at 1x). X is measured from the LEFT edge, Y from the
# BOTTOM edge (0 = bottom-flush). Calibrated empirically to WG's efficiency panel corner
# (WG panels are Flash -- no runtime position API). Phase 2 adds a separate raised anchor
# (BATTLE_ANCHOR_*_RAISED) used when the damage-log summary block collapses.
BATTLE_ANCHOR_X = 266
BATTLE_ANCHOR_Y = 0

# Phase 2: the RAISED anchor used when the "Summarized damage" group is fully unticked (all four
# DAMAGE_LOG summary flags off -> WG collapses the summary block and the damage-log events shift
# up, so the overlay moves to keep tracking them). Its OWN X + Y (independent of the default
# above, which stays signed-off) -- both fixed logical-px offsets, scale-invariant. Calibrated
# empirically against the collapsed layout (the summary block is Flash-side, no runtime px API).
BATTLE_ANCHOR_X_RAISED = 215
BATTLE_ANCHOR_Y_RAISED = 33

# Extra rightward offset (fixed logical px, added to whichever X anchor is in play) applied
# when WG's efficiency panel goes FIVE digits: a "Summarized damage" total that is ENABLED and
# exceeds EFFICIENCY_WIDE_THRESHOLD makes WG's panel grow one character wider, which would
# collide with our overlay. Shifting right by this much clears the widened panel. Calibrated in
# the overlay tuner (tools/dev/gen_overlay_tuner.ps1) -- WG panels are Flash, no runtime width
# API, so the offset is empirical like the anchors above. To be confirmed in-client.
BATTLE_ANCHOR_X_SHIFT = 5

# The "5-digit" cutoff: a value STRICTLY greater than this (i.e. >= 10000) prints a fifth
# digit and widens WG's panel. Compared against getTotalEfficiency() totals.
EFFICIENCY_WIDE_THRESHOLD = 9999

# Centre-screen progress-bar window anchor. Unlike the corner overlay's FIXED logical offsets
# above (which track a Flash panel laid out in logical units), this one is genuinely
# PROPORTIONAL: the bar must clear WG's fly-up ribbon feed, whose baseline measures 75.1vh, so
# it is placed as a FRACTION of the window's movable vertical extent. 0.865 is the tuner's
# settled stage placement (tools/dev/gen_bar_tuner.ps1, "top 86.5vh"). X is centred by the
# far-sentinel identity in positioning.anchor_centred; the offset is the tuner's 0rem.
PROGRESS_ANCHOR_Y_FRAC = 0.865
PROGRESS_ANCHOR_X_OFFSET = 0

# COMPENSATION for the bar's placement -- a WIRE CONTRACT with the JS, and ONE PURE TERM:
# -SHIFT_Y_REM (== -44). MoEProgress.js shifts the whole composition into POSITIVE document
# coordinates (nothing may sit at a negative x/y or the engine clips it there, whatever the
# surface size), by SHIFT_X_REM / SHIFT_Y_REM. That pushes the bar SHIFT_Y_REM down inside its
# own surface, so the window moves UP by exactly that much and the bar stays put on screen. Keep
# in lockstep with MoEProgress.js SHIFT_Y_REM (1rem == 1 logical px): if SHIFT_Y_REM changes,
# THIS constant must change with it.
# WAS A TWO-TERM COMPOSITE, retired by the Alignment wiring: PROGRESS_ANCHOR_Y_OFFSET == 36 ==
# (-44) + 80, where term 2 was +round(PROGRESS_ANCHOR_Y_FRAC * VIEW_H_REM) == round(0.865 * 92)
# == +80, a UNIT CONVERSION that existed ONLY because anchor_centred applied the fraction to the
# MOVABLE EXTENT (space_h - surface_h) rather than to the viewport. positioning
# .anchor_centred_reduced applies it to space_h DIRECTLY, which cancels that term algebraically at
# every resolution (see its docstring), so nothing bakes it any more -- and no future alignment
# has to bake its own. What is left is the pure intra-surface shift, which is NEGATIVE (the
# window moves UP), a plain mirror of -SHIFT_Y_REM again. PROGRESS_ANCHOR_Y_FRAC above still
# genuinely reads as "fraction of viewport height".
# X gets NO compensation on purpose: `max_x // 2` centres whatever surface width the view asks
# for and the composition is symmetric about its own centre, so the horizontal centring
# self-calibrates (and needs no unit conversion either). Do not fight it.
PROGRESS_ANCHOR_Y_SHIFT = -44

# ...and the LARGE size mode's twin (mod_settings.progress_bar_size == 1) -- NOT a pure scale-up
# of the 1x constant. `PROGRESS_ANCHOR_Y_SHIFT_LARGE = SHIFT_Y_REM * SIZE_F` (== -55) is an
# ALGEBRAIC IDENTITY that leaves `int(space_y * frac) + shift` -- the window's own pre-shift
# coordinate, roughly mid-composition -- at the SAME screen row at every size. That pins neither
# the composition's top ink nor its bottom ink (a stale comment here once claimed the former; it
# was wrong -- do not re-derive from it). Rule 5 (TASKS/in-battle-bar-layout-auto-set-redesign.md,
# DECISION 3) instead requires the BOTTOM ink -- the lowest ink pixel below the window's top-left --
# to land on the SAME screen row at Default and Large, so the bar visibly grows UP off a fixed
# bottom, not up-and-down off a fixed middle.
#
# `.mp-backdrop` IS the ink extreme on every side (its text-/box-shadow bleed reaches the box edge
# exactly, MoEProgress.js:65-70), and the backdrop sits with a symmetric PAD_REM slack to the
# surface edge, so the BOTTOM ink, measured from the window's top-left, is
#   bottom_ink_default == VIEW_H_REM - PAD_REM == 92 - 10 == 82.
# Both `frac` and `space_y` in anchor_centred_reduced's `y = int(space_y*frac) + shift` are
# size-independent, so `shift` is the ONLY size-dependent term, and every rem length (both the
# surface and the ink inside it) scales by the SAME SIZE_F == 1.25 via the root font:
#   bottom_ink_large == bottom_ink_default * SIZE_F
# Pinning bottom_ink means `shift_large + bottom_ink_large == shift_default + bottom_ink_default`,
# i.e.
#   shift_large == shift_default - bottom_ink_default * (SIZE_F - 1)
#              == shift_default - 0.25 * bottom_ink_default
#              == -44 - 0.25*82 == -64.5 -> -65 (half-away rounding, i.e. away from zero: the
#              shift is negative, so it rounds DOWN to -65, moving the window UP by 1 more px than
#              the naive -55 did -- see TASKS/in-battle-bar-layout-auto-set-redesign.md Trap 3
#              Fix A / DECISION 3 for the re-derivation and its arithmetic).
PROGRESS_ANCHOR_Y_SHIFT_LARGE = -65

# The damage-efficiency bar's window anchor -- its OWN three constants, not the progress bar's.
# Only one of the two centre-screen bars is ever open (they are radio alternatives), but the
# Y compensation term below is a function of the bar's own surface height, so sharing the
# progress bar's would silently mis-place whichever composition changed second.
# Y_FRAC is the phase-1 tuner's settled stage placement (eff_bar_tuner.html `offY` = 86.5vh --
# the same ribbon-clearing height the Moving Average bar was tuned to); X_OFFSET is its `offX` 0,
# and anchor_centred's `max_x // 2` centres whatever surface width the JS asks for.
# Y_SHIFT is the same ONE PURE TERM PROGRESS_ANCHOR_Y_SHIFT documents at length above, measured
# against the REAL MoEEfficiency.js:
#   -SHIFT_Y_REM == -50. MoEEfficiency.js shifts the whole composition into POSITIVE document
#   coordinates by PAD_REM - BOX_TOP_REM == 10 - (-40) == 50, so the window moves UP by exactly
#   that much and the bar stays put on screen. BOX_TOP_REM is .mp-backdrop's top in
#   MoEEfficiency.css (-40rem) -- the composition's topmost edge.
# WAS EFFICIENCY_ANCHOR_Y_OFFSET == 50 == (-50) + 100, term 2 being
# +round(EFFICIENCY_ANCHOR_Y_FRAC * VIEW_H_REM) == round(0.865 * 116) == +100 (VIEW_H_REM ==
# BOX_H_REM + 2*PAD_REM == 96 + 20 == 116, .mp-backdrop's height plus the JS's four-sided slack) --
# the extent-to-viewport conversion retired by anchor_centred_reduced. The old composite happening
# to equal SHIFT_Y_REM was a coincidence of round(0.865*116) == 2*50; THIS value is the shift
# itself, so the coincidence is gone with the term.
EFFICIENCY_ANCHOR_Y_FRAC = 0.865
EFFICIENCY_ANCHOR_X_OFFSET = 0
EFFICIENCY_ANCHOR_Y_SHIFT = -50

# ...and its LARGE-mode twin, re-derived exactly as PROGRESS_ANCHOR_Y_SHIFT_LARGE documents at
# length (read that first) to pin the composition's BOTTOM ink instead of the naive
# `-(SHIFT_Y_REM * SIZE_F)` identity's pre-shift coordinate (rule 5, DECISION 3):
#   bottom_ink_default == VIEW_H_REM - PAD_REM == 116 - 10 == 106
#   shift_large == shift_default - 0.25 * bottom_ink_default == -50 - 0.25*106
#              == -76.5 -> -77 (half-away rounding, away from zero).
# WAS EFFICIENCY_ANCHOR_Y_OFFSET_LARGE == 62 == (-63) + 125 under the RETIRED naive derivation
# (-63); that two-term composite's own retirement (the extent-to-viewport conversion cancelled by
# anchor_centred_reduced) is unaffected by this further correction -- only the ONE remaining pure
# term changes, from -63 to -77.
EFFICIENCY_ANCHOR_Y_SHIFT_LARGE = -77

# --- Phase 2 (in-battle vertical bar): minimap-anchored placement geometry -------------------
# Feeds domain.positioning.anchor_minimap, which places a vertical bar to the LEFT of the
# minimap instead of proportionally down the screen -- see
# TASKS/in-battle-vertical-bar-PLAN.md "Phase 2 -- Python placement".

# Measured logical-px minimap size per settingsCore GAME.MINIMAP_SIZE index (0-5), INVARIANT
# across resolution AND interface scale, the minimap flush to the screen's bottom-right corner
# with ZERO inset -- see tools/dev/measure_minimap.py's module docstring (the measurement
# source; corner-scan + connected-component cross-check, [228,279,329,409,510,628] +/-1px JPEG
# noise, confirmed at 3840x2160 scale 1/2 and 2560x1440 scale 1). The settingsCore read does NOT
# clamp its own range -- callers must clamp the index into [0, 5] before indexing this tuple.
MINIMAP_SIZES = (228, 279, 329, 409, 510, 628)

# Bar -> minimap logical-px clearances -- the vertical tuners' DEFAULTS. Fixed logical-px design
# values, NOT rem lengths: unlike MM_TICK_OVERHANG below they do not scale with the Large size mode.
# BOTH ARE MEASURED TO THE VISIBLE TRACK BOX, never to the window surface -- the tuners' own
# barRightPx() / barBottomPx() (gen_bar_tuner_vertical.ps1:377-378) and the efficiency tuner's
# placement() (eff_bar_tuner_vertical.html) place the TRACK on the stage, which is why
# anchor_minimap needs the *_MM_TRACK_X / MM_TRACK_Y terms below to convert into surface coordinates.
# MM_GAP == 8 in BOTH tuners. THE BOTTOM GAP DOES NOT MATCH, AND IS NOW SPLIT PER BAR: the Moving
# Average tuner's `mmGapBottom` default is 30 (gen_bar_tuner_vertical.ps1:451) and the Damage
# Efficiency tuner's `bottomGap` default is 28 (eff_bar_tuner_vertical.html:470).
# IT USED TO BE ONE SHARED 30, deliberately, because the difference was UNOBSERVABLE: the engine
# clamps a window into [0, space - surface] in compiled C++ (memory
# `engine-clamps-every-wulf-window-to-screen-and-the-mod-depends-on-it`), so every value below the
# surface's own below-the-track slack -- then a shared surface_h - MM_TRACK_Y == 380 - 290 == 90 --
# placed BOTH bars identically, flush to the screen's bottom, and neither tuned number was reachable.
# THE FRONT-END CHANGE THAT FREES THE SLACK HAS LANDED, which is the exact condition the shared
# value's own note named for splitting this: each vertical composition's surface now stops at its own
# tuned gap below the track instead of below the backdrop's lower bleed (MoEProgress.js /
# MoEEfficiency.js V_CLIP_B_REM, 60 and 62 rem of clipped bleed respectively), so the slack is 30 and
# 28 -- both tuned gaps are reachable and a 2px difference between them is now visible on screen. So
# each bar carries its own, threaded through BarHost exactly as *_MM_TRACK_X is (bar_window's
# `mm_gap_bottom` argument).
# STILL FIXED LOGICAL PX, with NO Large twin, and that is not an omission: under the Large size mode
# the clip scales with the composition (it rides applySize's `* f`), so the slack becomes 37 / 35 and
# a fixed 30 / 28 is once again UNREACHABLE -- the engine flushes to the bottom and the track lands at
# the tuned gap * SIZE_F, i.e. the same look 1.25x, which is what a scaled composition wants. Adding a
# *_LARGE twin here would compute the identical placement with more code. See MoEProgress.js's
# V_CLIP_B_REM note for why the clip must stay inside that factor.
MM_GAP = 8

# THE ACTUAL PLACEMENT GAP, PER BAR *AND PER SIZE* -- deliberately NOT MM_GAP above (kept at 8,
# the tuners' own shared reference/backdrop-fit constant -- both vertical CSS files' derivation
# comments still cite it, and it stays what a stock BarHost defaults to). The maintainer chose to
# spend part of the surface's own minimap clearance to pull both vertical bars closer to the
# minimap -- see anchor_minimap's `x = space_x - mm_size - gap - overhang - edge_x`: shrinking
# `gap` alone moves the ink AND the surface right by the same amount, so the ceiling is whichever
# size's surface has less clearance to spend
# (test_the_surface_clears_the_minimap_at_every_size_index pins the real number for each).
# margin(gap) = gap + overhang + edge_x - view -- overhang/edge_x/view are each their OWN
# Default/Large pair (MM_TICK_OVERHANG(_LARGE), *_MM_TRACK_X(_LARGE), the surface width at that
# size), so margin is a DIFFERENT affine function of `gap` at each size, and margin is
# INDEPENDENT of the minimap's own size index by construction (see the same test). A FIRST PASS
# solved one shared gap per bar (the largest reduction with BOTH sizes' margins >= 1), which
# left the SLACKER size of a pair paying for the tighter one: the Moving Average bar's Large size
# is always 1px tighter than Default at this anchor (its right-side pad was trimmed to the tick's
# own overhang plus a 2px margin -- see MoEProgress.js's own five-point note), so a single shared
# gap of 6 left Default sitting at a 2px margin it did not need to keep. SOLVED PER SIZE NOW,
# because the maintainer plays at Default and asked for THAT size's gap closed as far as it goes
# without also being bound by Large's tighter pad:
#   Moving Average: margin_default == gap - 4, margin_large == gap_large - 5
#                   -> gap == 5 (margin 1), gap_large == 6 (margin 1) -- Default improves from the
#                   shared pass's 6 to 5; Large is UNCHANGED, it was already the binding size.
#   Damage Efficiency: margin_default == gap - 2, margin_large == gap_large - 2 (the SAME affine
#                   function at both sizes for this bar, unlike the sibling) -> gap == gap_large
#                   == 3 (margin 1) at both -- UNCHANGED from the shared pass: splitting a knob
#                   that already wanted the identical value at both sizes buys nothing.
# None of the four can be pushed one further without landing a size mode at 0 (flush) or negative
# (an actual overlap, the click-blocking bug this module's own header calls out as critical) --
# see test_the_surface_clears_the_minimap_at_every_size_index for the pinned margins this derives.
# RESTORED to the shared 8 (2026-08-10, in-client review): the earlier per-size shrink (5/6, 3/3)
# moved the visible TRACK+numerals toward the minimap by 3-5px off the maintainer-approved position
# (track on-screen clearance == gap + overhang; edge_x/MM_TRACK_X cancels). The surface still reaches
# the minimap (1px floor) INDEPENDENTLY via each bar's grown V_PAD_XR(_LARGE) -- see MoEProgress.js /
# MoEEfficiency.js -- so restoring the gap did NOT reopen the backdrop-to-minimap gap.
PROGRESS_MM_GAP = 8
PROGRESS_MM_GAP_LARGE = 8
EFFICIENCY_MM_GAP = 8
EFFICIENCY_MM_GAP_LARGE = 8

PROGRESS_MM_GAP_BOTTOM = 30
EFFICIENCY_MM_GAP_BOTTOM = 28

# Half the tick's cross-axis overhang past the track's own edge (ticks are wider than the
# track), mirrored from the vertical tuner's live formula (gen_bar_tuner_vertical.ps1:371
# halfOverhang(): max(tickWEnd, tickWPre, tickWProj) - trackW, halved -- "if more than one tick
# cross-length exists, use the widest"). The shipped vertical CSS's defaults are all three tick
# cross-lengths == 9rem and trackW == 3rem (gen_bar_tuner_vertical.ps1:429-432), so
# overhang == (9 - 3) / 2 == 3 logical px at 1x (1rem == 1 logical px at the default root font).
# LARGE mode: trackW/tickW are CROSS-AXIS ("x") lengths, so under the Large size mode's total
# x-length factor of SIZE_F * SIZE_XF == 1.25 * 4/3 == 5/3 (memory
# `mp-lg-x-lengths-are-pure-sizexf-not-sizef`; the same reasoning PROGRESS_ANCHOR_Y_SHIFT_LARGE's
# header explains for the two-term composites above), the overhang -- being a difference of two
# x-lengths -- scales by that SAME 5/3: 3 * 5/3 == 5 exactly, no rounding ambiguity.
MM_TICK_OVERHANG = 3
MM_TICK_OVERHANG_LARGE = 5

# The vertical bar's ENTIRE intra-surface shift compensation -- positioning.anchor_centred_reduced's
# `y_shift` argument when orientation == vertical -- and, under the space_y-based reduction (see
# anchor_centred_reduced's own docstring), the WHOLE constant, not a two-term sum: term 2 (the
# extent-to-viewport fraction conversion) is cancelled algebraically once the caller passes
# space_y directly, so no alignment or orientation ever needs to bake it separately.
# IDENTICAL for both bars, unlike their horizontal siblings' -44-vs--50 split: both vertical
# compositions share the same backdrop geometry (`top: -80rem`, `height: 360rem`), so with the
# shared PAD_REM == 10 both shipped JS files use (mirroring how EFFICIENCY's SHIFT_Y_REM derives
# from PAD_REM - BOX_TOP_REM above):
#   SHIFT_Y_REM == PAD_REM - BOX_TOP_REM == 10 - (-80) == 90.
#   1x:    -SHIFT_Y_REM == -90.
# Do NOT re-add a term 2 here -- see anchor_centred_reduced's docstring for why none is needed.
# The horizontal composites are collapsed the same way now (PROGRESS_/EFFICIENCY_ANCHOR_Y_SHIFT
# (_LARGE) above), so every orientation carries exactly one shift per size and nothing else.
#
# THE LARGE TWIN IS RE-DERIVED FOR RULE 5 (TASKS/in-battle-bar-layout-auto-set-redesign.md,
# DECISION 3), exactly as PROGRESS_ANCHOR_Y_SHIFT_LARGE's header explains at length: the naive
# `-(SHIFT_Y_REM * SIZE_F) == -112.5 -> -113` is an algebraic identity that pins the pre-shift
# coordinate origin (mid-composition), not the BOTTOM ink -- read that constant's comment first,
# this one only carries the vertical numbers. This constant is used ONLY by the vertical +
# Damage Log placement (bar_window._resolve's `elif vertical:` branch, anchor_centred_reduced) --
# the Minimap alignment (both bars' natural home under rules 2/3) never reads it; see
# anchor_minimap's own MM_TRACK_Y(_LARGE), already bottom-right-invariant by construction.
#
# UNLIKE the horizontal pair, the two vertical surfaces this bar's SHARED shift feeds are NOT
# identical any more (320 rem clipped on the Moving Average bar, 318 on Damage Efficiency -- see
# the *_MM_GAP_BOTTOM split above and each JS's V_CLIP_B_REM), so treating the CLIPPED surface
# height itself as "the bottom ink" (the surface was deliberately clipped down to just past the
# caption ink plus a few rem of tuned slack, unlike the horizontal bars' full untouched PAD_REM)
# gives two slightly different bottom_ink_default readings that must land on the SAME shared
# constant -- and they do, up to the same +/-1 int-floor discretization anchor_centred_reduced's
# own docstring already accepts (do not chase a fix for it):
#   Moving Average (320):    -90 - 0.25*320 == -90 - 80   == -170.0 -> -170
#   Damage Efficiency (318): -90 - 0.25*318 == -90 - 79.5 == -169.5 -> -170 (half-away rounding)
# Both round to the SAME -170, which is why one shared constant still works -- but a future retune
# of either bar's OWN clipped height could round to -169 or -171 instead, so any test pinning this
# constant against ONE bar's derivation must assert a BOUND (+/-1), never equality against both.
VERTICAL_ANCHOR_Y_SHIFT = -90
VERTICAL_ANCHOR_Y_SHIFT_LARGE = -170

# DELETED (v23, the Fixed-alignment redesign): PROGRESS_ANCHOR_X_SHIFT_LARGE /
# EFFICIENCY_ANCHOR_X_SHIFT_LARGE, rule 5's vertical + Damage Log right-pin term, wired through
# domain.positioning.anchor_centred_reduced's `x_shift` argument and bar_window.BarHost's
# `x_shift_large` constructor argument. It existed to hold the composition's right edge still on a
# Default<->Large size flip for a VERTICAL bar resolving to the Damage Log anchor -- a combination
# that was already unreachable through the UI (a vertical bar's natural Alignment was Minimap) but
# stayed storable pre-v23. As of v23 the Alignment radio only ever stores Fixed or Free
# (clamp_variant's ceiling is PROGRESS_ALIGN_FREE == 1) and Fixed always resolves to Minimap when
# vertical (bar_window._resolve) -- there is no stored value or UI path left that can select
# Damage Log while vertical, so the term is genuinely dead rather than merely unreachable. See
# mod_settings.py's SETTINGS_VERSION 22->23 comment.

# WHERE THE VERTICAL COMPOSITION'S TRACK SITS INSIDE ITS OWN SURFACE -- positioning.anchor_minimap's
# `edge_x` / `edge_y`, i.e. the offset from the surface's top-LEFT corner to the two edges the
# minimap gaps are measured against. The shipped minimap placement had NO such term (it passed the
# surface's own width/height), which aligned the SURFACE's far edges instead of the track's and put
# the bar 45-63 logical px too far LEFT and 90 too HIGH -- the same surface-vs-composition frame
# mismatch VERTICAL_ANCHOR_Y_SHIFT above cancels for the centred anchor. Derived from the SAME five
# numbers those shifts are (the JS's V_BOX_* + PAD_REM) plus the track's own two CSS lengths, so
# nothing here is measured or tuned:
#
#   the track box IS #moe-bar-root -- `width: 3rem` (trackW, the cross axis) by `height: 200rem`
#   (barLen, the axis) in MoEProgressVertical.css:43-44 / MoEEfficiencyVertical.css:47-48 -- and
#   MoEBarTransient's mount writes it to (SHIFT_X_REM, SHIFT_Y_REM) inside the surface, so:
#
#     edge_x == SHIFT_X_REM + trackW == (padX - V_BOX_LEFT_REM) + 3
#     edge_y == SHIFT_Y_REM + barLen == (PAD_REM - V_BOX_TOP_REM)  + 200
#
# `padX` IS THE SURFACE'S X SLACK AND IS NOT PAD_REM ON EITHER BAR NOW. Both vertical surfaces
# reach further sideways than their backdrops do, because both bars' right-anchored captions grow
# leftward past them and PAD_REM alone CLIPPED them (MoEProgress.js's V_PAD_X_REM == 63; the
# Damage Efficiency bar's own per-mark caption pass later ate its PAD_REM margin too, so it now
# carries the SAME fix, V_PAD_X_REM == 14 -- MoEEfficiency.js's own note carries that derivation).
# Both apply their pad to BOTH sides even though only the left needs it: the centred alignment
# centres the SURFACE, so an asymmetric one moves the bar.
# GROWING THAT SLACK MOVES THE TRACK INSIDE THE SURFACE, so this constant has to grow with it or the
# whole bar slides left by the difference -- the surface widened on the left alone, the composition
# did not move within it, and nothing on screen may change.
#
# X IS PER BAR because the two vertical surfaces differ in their left clearance
# (V_BOX_LEFT_REM -34 vs -40, and now the pad on top), and it is a CROSS-AXIS length, so LARGE
# carries SIZE_XF == 4/3 on every x-length AND SIZE_F == 1.25 through the root font (memory
# `mp-lg-x-lengths-are-pure-sizexf-not-sizef`; the pad is NOT an x-length -- see
# MoEBarTransient.applySize, which re-derives shiftX as `padX - boxLeft * xf`):
#   Moving Average:    (70 + 34) + 3 == 107
#     LARGE:           (70 + 34*4/3 + 3*4/3) * 1.25 == 119.333 * 1.25 == 149.167 -> 149
#   Damage Efficiency: (52 + 40) + 3 == 95
#     LARGE:           (52 + 40*4/3 + 3*4/3) * 1.25 == 109.333 * 1.25 == 136.667 -> 137
# BOTH PADS GREW TWICE, in the SAME two passes, for the SAME reason each time -- a caption's own
# translateX moved further left (more overflow) and the surface pad had to grow with it or clip:
#   Moving Average V_PAD_X_REM: 63 -> 70. The maintainer's "move the bottom block (current damage
#     + delta) left 7px" nudge shrank .mpv-capC's translateX from 16 to 9, and .mpv-capC was
#     ALREADY this file's extreme row (MoEProgress.js's own derivation) -- the pad grew by the
#     identical +7 to restore the SAME ~4.5rem margin it had before the nudge.
#   Damage Efficiency V_PAD_X_REM: 10 (plain PAD_REM) -> 14 -> 52, in two corrections to the SAME
#     bug. First, the per-mark caption pass (icon_gap_tuner.html) pushed r1/r2/r3's mark_2/mark_3
#     far enough left that PAD_REM's flat 10rem started clipping them, so this bar picked up the
#     same widened-pad fix the Moving Average bar already had (10 -> 14) -- but that first pass
#     ONLY checked the mark rows and used the wrong icon width for them (13rem, the shared base
#     `.mev-ico` box, instead of the 16rem `.mev-ico.mk` override the mark icons actually render
#     at), and it never checked `.mev-cap.bt` (the current-damage + delta row) at all -- the same
#     "a gate that only watches one caption" mistake the Moving Average bar's OWN capC-is-the-
#     extreme lesson already existed to prevent. Re-deriving every row (including .bt, whose
#     16rem font + bare signed delta make IT this bar's true extreme, exactly as capC is for the
#     Moving Average bar) needs 52, not 14 -- and the maintainer's OWN "move the top/bottom block
#     left 4px/7px" nudges (MoEEfficiency.js's own V_PAD_X_REM note carries the exact reach) are
#     folded into that same 52, not a THIRD separate growth.
# EITHER GROWTH MOVES THE TRACK INSIDE ITS SURFACE, so the matching *_MM_TRACK_X(_LARGE) below had
# to grow with it -- else the surface would have widened on the left, the track would have sat
# further right INSIDE it, and the visible bar would have slid right into the minimap by the same
# device-px count the pad grew (times SIZE_F under Large).
#
# A maintainer Ctrl+drag of this bar once landed 2 logical px off this derivation, and a second,
# independent Ctrl+drag of the Moving Average bar landed 2px off ITS OWN pure derivation the OTHER
# way -- at the time read as hand-drag scatter at this maintainer's 4K x2 screen (1 logical px ==
# 2 device px), since the two straddled the derived values symmetrically.
#
# THAT READING HAS SINCE BEEN OVERTURNED FOR THE MOVING AVERAGE BAR ONLY, by a THIRD, independent
# Ctrl+drag on a freshly-deployed build, in a DIFFERENT surface geometry from either earlier one
# (a different shiftX, i.e. a different composition width) -- and it landed on the SAME track-left
# the second drag did, not a fresh scatter point:
#
#   MA drag #1, OLD geometry (shiftX 44):  pos_x 1354 -> track-left 1354 + 44 == 1398
#   MA drag #2, NEW geometry (shiftX 97):  pos_x 1301 -> track-left 1301 + 97 == 1398
#   pure derivation (edge_x 100):  1920 - 510 - 8 - 3 - 100 == 1299, + shiftX 97 == 1396
#
# Two independent drags landing on the IDENTICAL value across two different geometries is a
# repeatable 2px-right miss, not scatter (scatter would not repeat exactly). So PROGRESS_MM_TRACK_X
# below carries that -2 as a MEASURED HAND-PLACEMENT CORRECTION, specific to THIS bar: decreasing
# edge_x moves anchor_minimap's `x = space_x - mm_size - gap - overhang - edge_x` RIGHT by the same
# amount, landing the derived surface x at 1301 (+ shiftX 97 == 1398, matching both drags).
# _LARGE gets the SAME FLAT -2, not a scaled one -- matching how every other fixed logical-px
# clearance in this file is treated (MM_GAP, *_MM_GAP_BOTTOM have no Large twin because a clearance
# is a fixed logical-px design value, invariant to the size mode; this correction is the same kind
# of fixed hand-measured offset, not a composition length that scales with SIZE_F/SIZE_XF).
#
# THE DAMAGE EFFICIENCY BAR IS DELIBERATELY NOT GIVEN THIS CORRECTION. EFFICIENCY_MM_TRACK_X below
# stays the pure derivation (95 / 137, off the widened padX -- see above) -- its own single
# hand-drag (the FIRST one above) is still just one data point, never confirmed by a second
# independent drag the way the Moving Average bar's now is, and it has since been inspected in-game
# and accepted as correct as derived. The two bars' compositions differ (different surfaces,
# different shiftX), so nothing here licenses copying a Moving-Average-specific measurement onto
# its sibling. That hand-drag predates BOTH the per-mark caption pass AND the top/bottom-block
# nudges and their padX widenings, so it checked a MUCH narrower surface (edge_x 53) than the one
# shipping now (95) -- a fresh in-game confirmation of the new position is owed more than ever.
# THE MOVING AVERAGE BAR'S OWN -2 CORRECTION IS ALSO UNRE-CONFIRMED AT THE NEW 70 PAD. It is kept
# here on the working assumption that it is a fixed engine-side miss independent of composition
# width (its own history section above never varied with shiftX either) -- but every one of the
# THREE drags that established it happened at a narrower V_PAD_X_REM than 70, so this too is a
# should-hold, not a re-measured fact.
# THE Y AXIS WAS DELIBERATELY LEFT ALONE by that same re-placement. The stored drag pair's y was 820,
# i.e. 58 px BELOW the auto-placed 762, which would mean a bottom gap of -30 -- unreachable: the
# engine clamps every window into [0, space - surface] in compiled C++ (memory
# `engine-clamps-every-wulf-window-to-screen-and-the-mod-depends-on-it`) and the surface's own
# below-the-track slack (V_VIEW_H_REM - MM_TRACK_Y == 318 - 290 == 28 == EFFICIENCY_MM_GAP_BOTTOM) is
# a HARD FLOOR. The bar on screen was therefore already sitting at exactly the shipped Y, which is
# why EFFICIENCY_MM_GAP_BOTTOM is unchanged. Lowering it further needs a SURFACE change
# (MoEEfficiency.js V_CLIP_B_REM), never a constant nudge here.
# Y IS SHARED, exactly as VERTICAL_ANCHOR_Y_SHIFT is and for the same reason (both vertical
# backdrops have the identical `top: -80rem` / `height: 360rem`), and it is a Y length, so LARGE
# carries SIZE_F alone -- no SIZE_XF anywhere on this axis:
#   (10 + 80) + 200 == 290
#     LARGE:  290 * 1.25 == 362.5 -> 363 (half-away rounding, the convention
#             VERTICAL_ANCHOR_Y_SHIFT_LARGE's -112.5 -> -113 already uses)
#
# NO HORIZONTAL TWIN EXISTS ON PURPOSE. Neither horizontal tuner has any minimap placement at all
# (only the two VERTICAL ones do), so a horizontal bar beside the minimap has no tuned reference to
# reproduce -- bar_window._resolve keeps passing the surface's own edges there, which is what it
# always did. Do not invent the four numbers; tune them first if that alignment ever matters.
PROGRESS_MM_TRACK_X = 105              # pure derivation 107, -2 measured hand-placement correction
PROGRESS_MM_TRACK_X_LARGE = 147         # pure derivation 149, same flat -2 (see the comment above)
EFFICIENCY_MM_TRACK_X = 95              # pure derivation, no correction (see the comment above)
EFFICIENCY_MM_TRACK_X_LARGE = 137
MM_TRACK_Y = 290
MM_TRACK_Y_LARGE = 363
