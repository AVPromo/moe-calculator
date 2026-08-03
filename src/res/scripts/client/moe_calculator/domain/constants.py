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
# garage entry. We therefore anchor to when WE fetched: check at most once per day, which still
# picks up WG's new daily distribution within ~24h. A fetch that reveals a changed WG `updated_at`
# still forces a full refetch sooner (fetch_list.data_changed + moe_wgapi._poll).
REVALIDATE_SECONDS = 24 * 3600

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
PROGRESS_ETA_MARGIN = 0.10         # reference level sits this far above the requirement
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

# COMPENSATION for the bar's placement -- a WIRE CONTRACT with the JS. TWO terms, summed:
#   1. -SHIFT_Y_REM (== -44). MoEProgress.js shifts the whole composition into POSITIVE
#      document coordinates (nothing may sit at a negative x/y or the engine clips it there,
#      whatever the surface size), by SHIFT_X_REM / SHIFT_Y_REM. That pushes the bar
#      SHIFT_Y_REM down inside its own surface, so the window moves UP by exactly that much
#      and the bar stays put on screen. Keep in lockstep with MoEProgress.js SHIFT_Y_REM
#      (1rem == 1 logical px): if SHIFT_Y_REM changes, THIS constant must change with it.
#   2. +round(PROGRESS_ANCHOR_Y_FRAC * 92) (== +80). UNIT CONVERSION. anchor_centred applies
#      the fraction to the MOVABLE EXTENT (space_h - surface_h, surface_h == 92 == the JS's
#      VIEW_H_REM), not to the viewport, so a bare 0.865 landed the track at
#      int(988*0.865) + 44 - 44 = 854 of 1080 == 79.1vh, not the tuned 86.5vh. Adding
#      frac*surface_h back cancels the -frac*surface_h the extent form subtracts, at EVERY
#      resolution: 0.865*(H-92) + 0.865*92 == 0.865*H. At 1080 the track top is now
#      854 + 44 + 36 = 934 (== 0.865*1080 within the extent term's 1px int() floor).
# CONSEQUENCE: this is NO LONGER a plain mirror of -SHIFT_Y_REM -- the two are related but not
# equal, and PROGRESS_ANCHOR_Y_FRAC above now genuinely reads as "fraction of viewport height".
# X gets NO compensation on purpose: anchor_centred's `max_x // 2` centres whatever surface
# width the view asks for and the composition is symmetric about its own centre, so the
# horizontal centring self-calibrates (and needs no unit conversion either). Do not fight it.
PROGRESS_ANCHOR_Y_OFFSET = 36

# ...and the SAME two-term compensation for the LARGE size mode (mod_settings.progress_bar_size == 1),
# which is a pure scale-up of the composition and must NOT move the bar on screen. The mode's two
# factors live in MoEBarTransient.js -- SIZE_F = 1.25 (delivered by the ROOT FONT SIZE, so every rem
# length renders 1.25x with no CSS edit) and SIZE_XF = 4/3 (the EXTRA factor an x-length carries in the
# stylesheets' .mp-lg block, to reach 5/3 total). Neither term below takes SIZE_XF: this is the Y axis.
#   1. -(SHIFT_Y_REM * SIZE_F) == -(44 * 1.25) == -55. SHIFT_Y_REM is UNCHANGED at 44 -- it is a rem
#      length in the CSS (root.style.top), so the root font scales it for free -- but THIS constant is
#      logical px, which is what the extra * 1.25 converts.
#   2. +round(PROGRESS_ANCHOR_Y_FRAC * VIEW_H_REM * SIZE_F) == round(0.865 * 92 * 1.25)
#      == round(0.865 * 115) == +99. Same unit conversion as above; VIEW_H_REM is still 92 (a
#      y/uniform rem length), and 115 is the logical-px height the JS actually pushes to
#      resizeViewRem -- an ENGINE API, whose rem is C++'s and is NOT affected by our root font.
#   sum: -55 + 99 = 44. At 1080 the track top lands at int((1080-115)*0.865) + 44 + 55 = 933,
#   i.e. 0.865*1080 within the extent term's 1px int() floor -- exactly where the 1x bar sits.
# X still gets NO compensation, and only because the .mp-lg block keeps the backdrop SYMMETRIC about
# the track (left == -bleed', width == track' + 2*bleed'), so `max_x // 2` centres it for free.
PROGRESS_ANCHOR_Y_OFFSET_LARGE = 44

# The damage-efficiency bar's window anchor -- its OWN three constants, not the progress bar's.
# Only one of the two centre-screen bars is ever open (they are radio alternatives), but the
# Y compensation term below is a function of the bar's own surface height, so sharing the
# progress bar's would silently mis-place whichever composition changed second.
# Y_FRAC is the phase-1 tuner's settled stage placement (eff_bar_tuner.html `offY` = 86.5vh --
# the same ribbon-clearing height the Moving Average bar was tuned to); X_OFFSET is its `offX` 0,
# and anchor_centred's `max_x // 2` centres whatever surface width the JS asks for.
# Y_OFFSET is the same TWO-term compensation PROGRESS_ANCHOR_Y_OFFSET documents at length above,
# recomputed against the REAL MoEEfficiency.js (it was seeded provisionally from the progress bar
# while that file did not exist):
#   1. -SHIFT_Y_REM == -50. MoEEfficiency.js shifts the whole composition into POSITIVE document
#      coordinates by PAD_REM - BOX_TOP_REM == 10 - (-40) == 50, so the window moves UP by exactly
#      that much and the bar stays put on screen. BOX_TOP_REM is .mp-backdrop's top in
#      MoEEfficiency.css (-40rem) -- the composition's topmost edge.
#   2. +round(EFFICIENCY_ANCHOR_Y_FRAC * VIEW_H_REM) == +round(0.865 * 116) == +100. UNIT
#      CONVERSION: anchor_centred applies the fraction to the MOVABLE EXTENT (space_h - surface_h),
#      not to the viewport, and adding frac*surface_h back cancels the -frac*surface_h the extent
#      form subtracts, at EVERY resolution. VIEW_H_REM == BOX_H_REM + 2*PAD_REM == 96 + 20 == 116
#      (.mp-backdrop's height plus the JS's four-sided slack).
#   sum: -50 + 100 = 50. At 1080 the track top lands at int((1080-116)*0.865) + 50 + 50 = 933,
#   i.e. 0.865*1080 within the extent term's 1px int() floor -- same as the other bar.
# COINCIDENCE, NOT A MIRROR: this happens to equal SHIFT_Y_REM (50) because round(0.865*116) is
# 100 == 2*50. The two terms are independent -- any JS pad/box/frac change moves this value.
EFFICIENCY_ANCHOR_Y_FRAC = 0.865
EFFICIENCY_ANCHOR_X_OFFSET = 0
EFFICIENCY_ANCHOR_Y_OFFSET = 50

# ...and its LARGE-mode twin, derived exactly as PROGRESS_ANCHOR_Y_OFFSET_LARGE documents at length
# (read that first -- it explains why only SIZE_F appears here and never SIZE_XF):
#   1. -(SHIFT_Y_REM * SIZE_F) == -(50 * 1.25) == -63 (50*1.25 == 62.5, half-away rounds up).
#   2. +round(EFFICIENCY_ANCHOR_Y_FRAC * VIEW_H_REM * SIZE_F) == round(0.865 * 116 * 1.25)
#      == round(0.865 * 145) == +125. 145 is the logical-px height MoEEfficiency's transient pushes.
#   sum: -63 + 125 = 62. At 1080 the track top lands at int((1080-145)*0.865) + 62 + 63 = 933, i.e.
#   0.865*1080 within the int() floor -- the same place the 1x bar sits.
# NOT a mirror of anything: unlike the 1x pair (where round(0.865*116) happened to be 2*50), the two
# terms here share no coincidence at all. Any JS pad/box/frac change moves this value.
EFFICIENCY_ANCHOR_Y_OFFSET_LARGE = 62
