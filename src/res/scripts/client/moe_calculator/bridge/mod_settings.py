# -*- coding: utf-8 -*-
"""The user settings, laid out as two columns of NAMED CATEGORIES in the MSA panel. A category is
a BOLD label header row followed by that feature's controls, with an "Empty" spacer row between
categories (MSA renders only two columns here, so a category cannot be a column of its own -- see
_template()). Column 1 holds "Battle Calculator" (the In-Battle Widget master, labelled "Enabled",
grouped with its "Alt Press" + "Counted Assistance Row" children) then "Battle Progress" (the
Progress Bar master, also "Enabled", with its three VISIBILITY children "Events" / "Alt Press" /
"Always", then the standalone inline "Mode" and "Scale" radios) then "Transitions" (that master,
also "Enabled", with its "Events" + "Alt Press" switches and the "Hold Duration (s)" slider that
says how long the bar stays up) then "Layout" (column 1's header text; the i18n KEY stays
"catBarPosition" -- see SETTINGS_VERSION 20->21) with the standalone inline "Orientation" and
"Alignment" radios ABOVE the X/Y steppers that mirror the bar's Ctrl+drag. Column 2 holds "Garage
Widget" -- the garage master plus the
"Layout" group (also BOLD): Follow Carousel, then a non-bold "Position" sub-label heading the X/Y
steppers. (Column 1's "Layout" and column 2's "Layout" are two DIFFERENT categories that happen to
share a display name -- distinct i18n keys, distinct controls.)

The two near-identical child pairs are DELIBERATE and are different axes: the visibility trio
decides WHEN the bar comes up, the Transitions pair only HOW it moves once it does.

Surfaced as ModsSettingsAPI (MSA) checkboxes in the game's in-game mod-settings menu. MSA
(Aslain's gui.aslainMenu preferred, izeberg.modssettingsapi as a legacy fallback) is a SOFT
dependency: we import it guarded, and if it is absent the mod simply uses the defaults (both
widgets enabled) with no settings panel -- never a crash. MSA owns persistence, so there is
no config file of ours.

This module owns the flag state and fans a change out to per-feature ``apply_settings``
callbacks (registered by the entry point). It imports NOTHING from the sibling bridges, so
``gameface_bridge`` / ``battle_bridge`` can import it for the flag getters without a cycle.

Panel prose is localized: every visible label/tooltip is pulled from
``settings_i18n.panel_text()`` at the client's active language (English fallback per key --
see that module). The control STRUCTURE (types, varNames, values, settingsVersion) is
language-independent; only the text follows the language. ``modDisplayName`` stays the
literal English brand.

``merge_settings`` is pure so it unit-tests without the game (defaults, partial dict, unknown
keys, reset, version drift).
"""
from moe_calculator._compat import LOG_CURRENT_EXCEPTION, LOG_DEBUG
from moe_calculator.adapter import settings_i18n

# MSA store key for this mod (reverse-domain id). Stable across versions so saved checkbox
# state survives upgrades.
LINKAGE = "com.14th_ua.moe_calculator"
MOD_DISPLAY_NAME = "14th_ua's MoE Calculator"

# Bump ONLY when the control layout / varName set changes (the host wipes saved values to
# defaults on a bump). Localizing text is text-only -- it does NOT bump this (the stored
# template text is refreshed in place by _sync_template_text instead).
# Bumped 4 -> 5 when the drag-to-reposition controls landed: the posX/posY numeric steppers,
# the Follow Carousel Mode checkbox, and a positioning Label (new varNames + a new column-2
# layout), so the bump is mandatory to reach an existing install.
# Bumped 5 -> 6 when the Next Mark Progress Bar checkbox landed (a new varName + a fourth
# column-1 control), which is structural. register()'s migration branch carries the user's
# existing values across the bump; the new key just takes its fresh default.
# Bumped 6 -> 7 for a one-column-per-feature relayout that moved the progress-bar checkbox into
# its own column 3. Bumped 7 -> 8 to REVERT that: column 3 never rendered in-client and the
# surrounding layout came out mangled, so the checkbox is back at the end of column 1. Column
# membership is non-structural to MSA (_settingsStructure records only varName/type/domain) and
# register() never re-runs setModTemplate on an existing install, so ONLY a bump re-lays-out a
# v7 install -- 6 would not do (a bump needs new > stored). The "Next Mark Progress Bar" ->
# "Progress Log" rename rides along and is KEPT; on its own it would have been text-only
# (_sync_template_text) and needed no bump.
# Bumped 8 -> 9 for the Progress Bar variant restructure: the "Progress Log" checkbox is
# RE-PARENTED into its own createControlsGroup as the "Progress Bar" master and gains a
# RadioButtonGroup child (Moving Average / Damage Efficiency), which is a new varName, a new
# control and a new nesting -- all structural. The radio's OPTION LABELS are structural too
# (Aslain folds them into _settingsStructure and _sync_template_text only ever rewrites
# text/tooltip, never options[].label), so they can reach an existing install ONLY via this
# bump. register()'s migration branch carries every saved value across it; the new
# progress_bar_variant key takes its fresh 0 (= Moving Average, the option order AS SHIPPED AT
# THIS BUMP -- bump 12->13 below flips it, so 0 means Damage Efficiency from v13 onward; see
# PROGRESS_VARIANT_KEY) default, so an existing user lands exactly on the bar they already had.
# Bumped 9 -> 10 to DROP the variant radio's own "Bar Type" label row, so its two options read as
# direct children of the Progress Bar checkbox: the radio's text is now empty and its tooltip is
# gone (folded into the master's, the only surface left to hover). Version 9 shipped to nobody but
# the maintainer's own install, and 10 exists purely to re-lay-out THAT install. Strictly, text is
# NOT part of Aslain's _settingsStructure (only type/varName/options are), so the empty label
# alone would have travelled text-only via _sync_template_text -- but that helper can only
# OVERWRITE text/tooltip, never DELETE a key, so a v9 install would keep the stale "Bar Type"
# tooltip on an invisible row forever. Only setModTemplate replaces the stored control wholesale,
# and only a bump (new > stored) reaches it. Never go backwards: 10, not a revert to 8.
# Bumped 10 -> 11 for the three-category relayout PLUS a new key, either of which alone would
# already require it: the panel gains three bare Label header rows ("Battle Calculator", "Battle
# Progress", "Garage Widget") that shift every following control's position, and the Progress Bar
# group gains a second RadioButtonGroup child (progress_bar_size, with its own option labels --
# structural to Aslain's _settingsStructure). register()'s saved-truthy path never calls
# setModTemplate, so neither the new rows nor the new control can reach an existing install without
# this forward bump; the migration branch carries every saved value across the bump and
# progress_bar_size takes its fresh 0 (= Default) default.
# Bumped 11 -> 12 for the "Transitions" group: a THIRD grouped master in the "Battle Progress"
# category (progress_transitions_enabled) with two children (progress_transitions_events,
# progress_transitions_manual) -- three new varNames and three new rows at the end of column 1, all
# structural. As always register()'s saved-truthy path never calls setModTemplate, so only a forward
# bump reaches an existing install; the migration branch carries every saved value across and the
# three new keys take their fresh True (= animated, what shipped) defaults.
# Bumped 12 -> 13 for the visibility relayout: THREE new varNames (progress_show_events,
# progress_show_alt_key, progress_show_always -- the WHEN the bar comes up, distinct from the
# Transitions group's HOW it moves), two "Empty" spacer rows, both radios re-parented OUT of the
# Progress Bar group into standalone inline controls, and the variant radio's OPTION ORDER FLIPPED
# (Damage Efficiency is now index 0 and the default). The option labels are structural to Aslain
# (_settingsStructure folds them in) and _sync_template_text never rewrites options[].label, so only
# a forward bump reaches an existing install. NOTE (later corrected -- see _migrate_pre_v13_variant):
# this originally carried the stored raw int across UNCHANGED, silently swapping an existing user's
# chosen bar; register()'s migration branch now flips a pre-v13 store's raw int so the user's choice
# survives, keyed on the ABSENCE of a key introduced in this same bump (there is no stored version
# int to compare against directly). The three new keys take their fresh defaults (events on, Alt
# Press on, Always off), and
# counted_assistance_enabled's DEFAULT flipped False -> True, which reaches only fresh installs (the
# migration branch preserves a saved value, as it must).
# Bumped 13 -> 14 for the category-header bold + column-2 regroup: the four category/group headers
# (Battle Calculator, Battle Progress, Garage Widget, Layout) now render <b>...</b> with an explicit
# `useHTML` key -- _sync_template_text only ever rewrites a stored control's `text`/`tooltip`, never
# `useHTML`, so an existing v13 install would keep rendering those headers plain forever without this
# bump. Column 2 also reorders (Follow Carousel moves up to be the first row under "Layout") and
# gains a new varName-less "Position" sub-label heading the two steppers -- COL2_KEYS grows 7 -> 8.
# Because register()'s saved-truthy path never calls setModTemplate on an existing install, only a
# forward bump reaches it (structural-to-Aslain or not -- see the moe-settings skill). No varName
# was added, removed or renamed, so the migration branch carries every saved value across unchanged.
# The three masters' own label also went "Show" -> "Enabled" and the position steppers' labels
# regained their axis hints ("Horizontal (left X)" / "Vertical (top Y)") -- both text-only and would
# have travelled via _sync_template_text on their own, but ride along with this bump regardless.
# Bumped 14 -> 15 to add two more "Empty" spacer rows: one heading the "Transitions" group (column
# 1, right after the Scale radio) and one heading the "Position" sub-label (column 2, right after
# Follow Carousel) -- purely visual breathing room, matching the existing category-separator
# spacers. Two new None-sentinel slots in COL1_KEYS/COL2_KEYS shift every following control's
# positional pairing in _sync_template_text, so this is structural even though no varName changed;
# register()'s saved-truthy path never calls setModTemplate on an existing install, so only a
# forward bump reaches it. No varName was added, removed or renamed, so the migration branch
# carries every saved value across unchanged.
# Bumped 15 -> 16 for a THIRD "Empty" spacer row in column 1: one now heads the standalone Mode /
# Scale radios too (right after the Progress Bar group's three visibility children), the same
# purely visual role as the other two. One more None-sentinel slot in COL1_KEYS (16 -> 17) shifts
# every later control's positional pairing in _sync_template_text, so -- same reasoning as the
# 14 -> 15 bump -- this is structural even though no varName changed; only a forward bump reaches
# an existing install. No varName was added, removed or renamed, so the migration branch carries
# every saved value across unchanged.
# Bumped 16 -> 17 for the Transitions restructure plus a new varName, either of which alone would
# already require it: "Transitions" is promoted from a bare third group inside the "Battle Progress"
# category to a CATEGORY OF ITS OWN (a new bold Label header row ahead of the master, which shifts
# every following control's positional pairing in _sync_template_text), and the category gains a
# new control -- the progress_hold_seconds SLIDER, a brand-new varName AND a brand-new component
# type, whose minimum/maximum/snapInterval Aslain folds into its _settingsStructure signature.
# COL1_KEYS grows 17 -> 19. The slider hangs off the "Transitions" HEADER, NOT off the master: it is
# a plain top-level un-indented row spliced on after the group, so the group keeps exactly its two
# switch children and the slider carries no masterVarName. That is deliberate and matches
# progress_hold_seconds(), the one member of the category that is not master-folded -- a duration
# applies whether or not the enter/exit animate, so greying it under "Enabled" would have claimed
# otherwise. The master's own label goes "Transitions" -> "Enabled" (the header now
# names the feature, exactly as for the other three masters) but its varName is DELIBERATELY
# unchanged -- merge_settings/_apply iterate DEFAULTS keys only with no rename/alias map, so a
# rename would silently reset every existing user's value. register()'s saved-truthy path never
# calls setModTemplate on an existing install, so only a forward bump reaches it; the migration
# branch carries every saved value across and progress_hold_seconds takes its fresh 5 s default
# (== the JS transient's baked HOLD_MS, so nobody's bar changes length without asking).
# Bumped 17 -> 18 for the in-battle bar's Ctrl+drag POSITION controls: a FOURTH column-1 category
# ("Bar Position" -- an Empty spacer plus its own bold Label header) and the two
# progress_bar_pos_x / progress_bar_pos_y NumericSteppers, i.e. two brand-new varNames and four new
# rows appended to column 1 (COL1_KEYS 19 -> 23). Structural twice over, and as always register()'s
# saved-truthy path never calls setModTemplate on an existing install, so only a forward bump
# reaches one. The migration branch carries every saved value across and the two new keys take
# their fresh 0 (= auto) default, so every existing user's bar stays exactly where it has always
# been -- 0/0 composes onto the default Damage Log alignment's base and reproduces the shipped
# placement byte-for-byte (domain.anchor_offset; the alignment wiring came later and retired the
# old anchor_pinned sentinel this comment used to name).
# Bumped 18 -> 19 for a FIFTH "Empty" spacer row in column 1, immediately ahead of the
# hold-duration Slider (still inside the "Transitions" category, right after the group's "Alt
# Press" child) -- purely visual breathing room, the same role every other spacer plays. No
# varName was added, removed or renamed, but the new None-sentinel slot (COL1_KEYS 23 -> 24)
# shifts the Slider's and every later control's positional pairing in _sync_template_text, so it
# is structural regardless; register()'s saved-truthy path never calls setModTemplate on an
# existing install, so only a forward bump reaches it. The migration branch carries every saved
# value across unchanged.
# Bumped 19 -> 20 because BOTH position stepper pairs (the in-battle barPosX/barPosY and the garage
# posX/posY) drop their `minimum: 0` for `minimum: -POS_MAX`. The on-screen clamp is gone -- a bar
# may now be dragged past any edge, storing a NEGATIVE coordinate (see clamp_pos and
# domain/positioning) -- and MSA echoes a stepper's value back through onSettingsChanged, so a
# stored descriptor still bounded at 0 would snap a negative dragged position back to 0 as soon as
# the user merely OPENED the panel. No varName was added, removed or renamed and no row moved, but a
# descriptor edit alone reaches nobody: register()'s saved-truthy path never calls setModTemplate on
# an existing install (Aslain also folds minimum/maximum/snapInterval into its _settingsStructure
# signature), so only a forward bump replaces the stored control. The migration branch carries every
# saved value across unchanged -- and _apply/_coerce now clamp through the widened clamp_pos, so a
# negative position captured before the bump survives it.
# Bumped 20 -> 21 for the vertical-bar Orientation/Alignment radios: TWO new varNames
# (progress_bar_orientation, progress_bar_alignment), TWO new standalone inline RadioButtonGroup
# rows spliced ABOVE the existing X/Y steppers in the fourth column-1 category (COL1_KEYS grows
# 24 -> 26), and that category's header TEXT changes "Bar Position" -> "Layout" (the i18n KEY
# stays catBarPosition -- a rename buys nothing, see moe-settings skill). All three are structural
# on their own; together they make three independent reasons for the bump. The radios' OPTION
# LABELS are structural to MSA too (Aslain folds them into _settingsStructure;
# _sync_template_text never rewrites options[].label), so get the order right: Orientation is
# Horizontal (0, default) / Vertical (1); Alignment is Damage Log (0, default) / Minimap (1) /
# Free (2). register()'s saved-truthy path never calls setModTemplate on an existing install, so
# only this forward bump reaches one. The migration branch below (_migrate_pre_v21_layout) is a
# LOOKUP, not arithmetic: keyed on the ABSENCE of progress_bar_orientation (no stored version int
# to compare against directly, same trick as _migrate_pre_v13_variant), a pre-v21 store's
# progress_bar_pos_x/_y was an ABSOLUTE top-left, which is exactly what Alignment=Free means --
# so a non-zero pair maps to Free (coordinates carried verbatim) and a zero pair to Damage Log
# (still 0/0, the shipped placement). Nobody's bar moves. Every OTHER saved value carries across
# unchanged and the two new keys take their fresh Horizontal/Damage Log defaults where the
# migration doesn't apply (a fresh install).
# Bumped 21 -> 22 for Free's stored frame (TASKS/in-battle-bar-layout-auto-set-redesign.md Trap 3
# Fix B / DECISION 2): under Free, the stepper pair is now read as an ANCHOR POINT
# (bottom-centre horizontal / bottom-right vertical -- domain.positioning.free_top_left), not a
# top-left, so a size change re-anchors the bar instead of growing it off to one side. That is a
# BEHAVIOUR change, not a template one -- no varName/control/option changed shape -- but the
# maintainer chose to migrate it with a NEW varName rather than accept the one-time visible shift
# of every existing Free pin, and a new varName is structural on its own (a bump is the only hook
# register() gives to migrate a stored VALUE, and the absence-of-a-key trick below needs a key to
# key on). progress_bar_pos_frame ("legacy" | "anchor") marks which frame the CURRENT
# progress_bar_pos_x/_y pair is in; fresh installs default straight to "anchor" (there is no
# legacy pair to carry). CONVERSION ROUTE TAKEN: option (a) from the decision, NOT (b) -- the
# surface size needed to convert a legacy top-left into an anchor point does not exist at
# migration time either (the same wall Free's initial materialisation hits, see
# bar_window.BarHost._materialise), so _migrate_pre_v22_pos_frame only SEEDS the marker
# ("legacy" for a pre-v22 store with Alignment=Free and a non-(0, 0) pair, "anchor" for every
# other case -- there is no legacy pair to convert). The actual conversion is deferred onto the
# SAME materialise-on-mount path DECISION 1 already owes: the first _place with a real,
# post-onSizeChanged surface converts whichever pair is currently stored (as a literal top-left,
# per _resolve's legacy branch) into the anchor-point frame and flips the marker, reusing
# free_anchor_point / set_bar_position -- no surface constant baked into Python, and the two
# DECISION-1/DECISION-2 triggers collapse into ONE _materialise call because both end in the exact
# same action ("re-express the just-resolved top-left as an anchor point and persist it").
# progress_bar_pos_x/_y are NOT renamed (there is no rename/alias map -- see
# mod-settings-has-no-key-rename-map) and stay readable forever; only their FREE-alignment
# interpretation changes, gated by the new key. register()'s saved-truthy path never calls
# setModTemplate on an existing install, so only this forward bump reaches one; the migration
# branch carries every saved value across (enumerated from DEFAULTS, not hand-listed) and the new
# key takes its fresh "anchor" default where the migration doesn't apply (a fresh install).
SETTINGS_VERSION = 22

GARAGE_KEY = "garage_widget_enabled"
BATTLE_KEY = "battle_widget_enabled"
# The in-battle overlay's Alt-key mode, a CHILD of BATTLE_KEY (grouped under it via
# createControlsGroup): show the overlay only while Alt is held; when off the overlay is shown
# at all times. It has effect ONLY while BATTLE_KEY is on -- with the master off the overlay is
# never shown, so the child is inert (and MSA greys it out under the group). See
# battle_bar_visible: active == battle_enabled and (alt_held if alt_mode else True).
BATTLE_ALT_KEY = "battle_widget_alt_key"
# Optional third in-battle row: "counted assistance" = the higher of tracking / spotting / stun
# assist this battle (the assist that MoE credits). Default ON since v13 -- MoE counts the assist,
# so the row is part of the readout, not an extra. A saved OFF survives the bump (the migration
# branch preserves it); only a fresh install sees the new default.
COUNTED_ASSIST_KEY = "counted_assistance_enabled"

# Master enable for the transient centre-screen progress bar ("Progress Bar"), shown when the
# career moving average updates. Its OWN feature, NOT a child of BATTLE_KEY (it renders
# independently of the In-Battle Widget overlay), so it is the master of its OWN column-1 group
# and never carries a masterVarName -- see the comment in _template().
# Opt-in (default OFF) -- a centre-screen transient is intrusive, so existing users must ask for it.
# The varName is DELIBERATELY unchanged despite the label going "Progress Log" -> "Progress Bar":
# merge_settings/_apply iterate DEFAULTS keys only, with no rename/alias map, so renaming a
# varName would silently reset EVERY existing user's value. The key lives forever.
PROGRESS_BAR_KEY = "progress_bar_enabled"

# Which bar the Progress Bar master draws -- a STANDALONE inline radio (v13 pulled it out of the
# Progress Bar group; see _template()), and one of two settings of ours that are NOT bools: MSA's
# RadioButtonGroup stores its value as a 0-BASED OPTION INDEX (see
# templates.createRadioButtonGroup, ":type value: int"). _coerce has a dedicated branch for it,
# because the default bool() branch would turn index 1 into True.
#
# THE ORDER FLIPPED IN v13. register()'s migration branch now flips a PRE-v13 store's raw int
# in place (see _migrate_pre_v13_variant) so an upgrading user keeps the bar they actually
# chose; a store already at v13+ passes through untouched. Damage Efficiency is index 0 and
# therefore the default.
PROGRESS_VARIANT_KEY = "progress_bar_variant"
PROGRESS_VARIANT_EFFICIENCY = 0       # the damage-vs-requirements "Damage Efficiency" bar
PROGRESS_VARIANT_MOVING_AVERAGE = 1   # the original next-mark moving-average bar
# ... and MOVING_AVERAGE is the highest legal index: a stored value outside [0, MOVING_AVERAGE] is
# corrupt (clamp_variant).

# How large the Progress Bar draws -- the SECOND child radio of PROGRESS_BAR_KEY and the mod's
# second non-bool setting, so _coerce needs its own branch here too (falling through to bool()
# would turn index 1 into True and destroy the setting, exactly as for the variant).
PROGRESS_SIZE_KEY = "progress_bar_size"
PROGRESS_SIZE_DEFAULT = 0             # the shipped size -- every existing user keeps it
PROGRESS_SIZE_LARGE = 1               # ... and the highest legal index (see clamp_variant)

# WHEN the Progress Bar comes up -- three children of PROGRESS_BAR_KEY, and a DIFFERENT axis from
# the Transitions group below, which only decides HOW it moves once it is coming up. Do not
# conflate them; the near-identical labels are deliberate.
#   events    a battle event (a damage / efficiency tick) raises the bar
#   alt_key   holding Alt peeks it up
#   always    the bar is permanently on screen -- and then the other two are IGNORED, which is
#             folded in by the two consumers below (MSA still stores and still pushes a greyed
#             control's value, so the fold has to happen here, exactly like the Transitions master)
# ALWAYS IS IMPLEMENTED AS A PERMANENTLY-HELD ALT, not a fourth code path: the JS transient already
# pins the bar at its hold plateau for as long as altHeld is true (MoEBarTransient.peekOn pauses
# the animation there and never ends the run), so progress_alt_held() simply reports True and the
# shared machine does the rest -- no new CSS, no new state.
PROGRESS_SHOW_EVENTS_KEY = "progress_show_events"
PROGRESS_SHOW_ALT_KEY = "progress_show_alt_key"
PROGRESS_SHOW_ALWAYS_KEY = "progress_show_always"

# The Progress Bar's ENTER/EXIT TRANSITIONS (its fade + slide), as the master of its OWN
# "Transitions" category with one child per trigger AREA. Plain bools, all defaulting True --
# the animated bar is what shipped. Turning a child OFF makes that area's appearance AND
# disappearance INSTANT: the bar still shows and still hides, only the motion is skipped. That
# mimics the game's own HUD, which does not animate its elements on Alt.
#   events  the bar reacting to what happens in battle (a damage / efficiency tick)
#   manual  the Alt-key peek
# The MASTER is folded in by the getters below and is deliberately NEVER pushed to the JS -- the
# widget only ever sees the two effective flags.
PROGRESS_TRANSITIONS_KEY = "progress_transitions_enabled"
PROGRESS_TRANS_EVENTS_KEY = "progress_transitions_events"
PROGRESS_TRANS_MANUAL_KEY = "progress_transitions_manual"

# How long the Progress Bar STAYS UP once it is up, in whole SECONDS -- the fourth control of the
# Transitions group and an MSA "Slider" (its only one). Pushed to both bars as `holdMs`
# (seconds * 1000), where MoEBarTransient drives the hold with its own wall-clock timer rather than
# the baked mp-life keyframe, whose 5000ms hold cannot be stretched in place.
# WHOLE SECONDS ONLY: a fractional slider value's runtime type is a live-client unknown, and int
# seconds are all a 1..30s range needs. NOT a bool, so _coerce needs its own branch (falling
# through to bool() would turn 5 into True and destroy the setting -- exactly the radios' trap).
# The default is the JS transient's OWN baked HOLD_MS / 1000, so an existing user's bar is
# unchanged until they touch the slider.
PROGRESS_HOLD_SECONDS_KEY = "progress_hold_seconds"
PROGRESS_HOLD_MIN = 1
PROGRESS_HOLD_MAX = 30
PROGRESS_HOLD_DEFAULT = 5

# Draggable garage-widget position, stored as two on-screen PIXEL coordinates (the widget's
# top-LEFT anchor): posX (left px) + posY (top px). Both default to 0, meaning "auto" -- the
# widget keeps its CSS bottom-right default (resolution-relative), so it re-derives correctly at
# every resolution. posX/posY stay 0 until the user drags the widget (or edits a stepper); a
# real pin sets the chosen px. posW/posH record the viewport px the pin was captured at, so the
# widget can rescale it proportionally after a resolution / UI-scale change (not user-facing --
# written only via set_position). See the sibling Garage Progress Bar mod for the same scheme.
POS_X_KEY = "posX"
POS_Y_KEY = "posY"
POS_W_KEY = "posW"
POS_H_KEY = "posH"

# Draggable IN-BATTLE BAR position -- stored the same way (a px pair, 0/0 default) as the garage
# pair above, but composed differently: this pair is an OFFSET onto whichever anchor the
# Alignment setting selects (domain.anchor_offset), not a standalone "auto" sentinel, and
# nothing else in common with the garage pair:
#   * ONE PAIR FOR BOTH BARS. Moving Average and Damage Efficiency are radio ALTERNATIVES (only
#     one is ever open), so a second pair would be two more settings rows describing the same
#     spot on screen.
#   * NO posW/posH TWIN. The garage pair is on-screen PIXELS and must be rescaled when the
#     resolution changes, which is what those record. These two are the window's top-left in the
#     engine's LOGICAL GUI SPACE -- already interface-scale invariant (see domain/positioning's
#     header) -- so there is nothing to pin them to and nothing to rescale.
# 0/0 is just the default offset: under the default Damage Log alignment it reproduces the
# shipped placement byte-for-byte, which is where every existing user is.
# The varNames are FROZEN (there is no rename/alias map -- a rename silently resets every user).
BAR_POS_X_KEY = "progress_bar_pos_x"
BAR_POS_Y_KEY = "progress_bar_pos_y"

# Which FRAME the BAR_POS pair is currently expressed in under Alignment=Free -- v22 (see
# SETTINGS_VERSION 21->22). NOT a UI control -- no varName-to-row mapping is needed for MSA to
# persist it, same precedent as POS_W_KEY/POS_H_KEY above. Two values only:
#   "anchor"  the pair is the ANCHOR POINT Fix B stores (bottom-centre horizontal / bottom-right
#             vertical -- domain.positioning.free_top_left) -- fresh installs start here, since
#             there is no legacy pair to carry.
#   "legacy"  the pair is still a PRE-v22 literal top-left, pending conversion at this bar's next
#             battle mount (bar_window.BarHost._materialise) -- only a pre-v22 store with
#             Alignment=Free and a non-(0, 0) pair is seeded here (_migrate_pre_v22_pos_frame).
# set_bar_position() always writes "anchor" (every path that calls it -- a drag end, or
# _materialise's own conversion write -- produces a pair that IS already in the new frame), so
# "legacy" can only be read, never re-written by anything other than the migration.
PROGRESS_POS_FRAME_KEY = "progress_bar_pos_frame"
POS_FRAME_ANCHOR = "anchor"
POS_FRAME_LEGACY = "legacy"

# Which axis the bar draws on -- a STANDALONE inline radio (v21), shared by BOTH bars like the
# position pair above it (Moving Average / Damage Efficiency are alternatives, not simultaneous).
# One of the mod's non-bool settings, so _coerce needs its own clamp_variant branch (falling
# through to bool() would turn index 1 into True and destroy the setting, exactly like the
# variant/size radios above).
PROGRESS_ORIENTATION_KEY = "progress_bar_orientation"
PROGRESS_ORIENT_HORIZONTAL = 0   # the shipped axis -- every existing user keeps it
PROGRESS_ORIENT_VERTICAL = 1     # ... and the highest legal index (see clamp_variant)

# Which anchor the position steppers offset FROM (v21) -- also standalone/inline, also non-bool.
# Damage Log is the shipped centred anchor (offset 0/0 reproduces today's placement byte-for-byte);
# Minimap is the new minimap-relative anchor; Free is the pair read as an ANCHOR POINT as of v22
# (domain.positioning.free_top_left -- PROGRESS_POS_FRAME_KEY marks whether a pre-v22 pair still
# needs converting into that frame). ALL THREE OPTIONS STAY ALWAYS-SELECTABLE regardless of
# orientation -- MSA gates whole controls (masterVarName/conditions), not individual radio
# options, so a per-orientation restriction would cost a second stored key for no behavioural
# gain.
PROGRESS_ALIGNMENT_KEY = "progress_bar_alignment"
PROGRESS_ALIGN_DAMAGE_LOG = 0   # the shipped centred anchor -- every existing user keeps it
PROGRESS_ALIGN_MINIMAP = 1
PROGRESS_ALIGN_FREE = 2         # ... and the highest legal index (see clamp_variant)

# Follow Carousel Mode (default ON): keep nudging a pinned widget vertically as the carousel
# state changes (1<->2 rows, small<->tall), so a dragged widget never overlaps the carousel.
# The nudge is live-measured JS-side -- no extra persisted coordinate.
FOLLOW_CAROUSEL_KEY = "followCarousel"

# Sanity MAGNITUDE limit for a stored pixel coordinate (well past any real screen size); a
# typed / echoed value is clamped into [-POS_MAX, POS_MAX], with 0/0 meaning "auto / unseeded".
# NEGATIVES ARE LEGAL: an in-battle bar may be Ctrl+dragged past the left/top screen edge (there is
# no on-screen safezone -- see domain/positioning), so this is a corruption guard, not a viewport.
POS_MAX = 20000

_POS_KEYS = (POS_X_KEY, POS_Y_KEY, POS_W_KEY, POS_H_KEY, BAR_POS_X_KEY, BAR_POS_Y_KEY)

# The two widgets and the counted-assistance row ship ON; the Alt-peek mode and the progress bar
# ship OFF (opt-in), with the progress-bar VARIANT on Damage Efficiency (0, the v13 order) and both
# of its VISIBILITY triggers on but "Always" off, all three TRANSITION switches ON (the animated
# bar is what shipped) and the hold at 5s (the JS transient's baked HOLD_MS, so the default bar is
# byte-identical to what shipped). The drag position ships at auto (0/0/0/0), orientation
# Horizontal and alignment Damage Log (v21 -- also byte-identical to what shipped), Follow
# Carousel ON. merge_settings only ever overlays these known keys, so an MSA store from a
# newer/older template can never introduce or drop a flag we act on.
DEFAULTS = {GARAGE_KEY: True, BATTLE_KEY: True, BATTLE_ALT_KEY: False,
            COUNTED_ASSIST_KEY: True, PROGRESS_BAR_KEY: False,
            PROGRESS_VARIANT_KEY: PROGRESS_VARIANT_EFFICIENCY,
            PROGRESS_SIZE_KEY: PROGRESS_SIZE_DEFAULT,
            PROGRESS_SHOW_EVENTS_KEY: True, PROGRESS_SHOW_ALT_KEY: True,
            PROGRESS_SHOW_ALWAYS_KEY: False,
            PROGRESS_TRANSITIONS_KEY: True, PROGRESS_TRANS_EVENTS_KEY: True,
            PROGRESS_TRANS_MANUAL_KEY: True,
            PROGRESS_HOLD_SECONDS_KEY: PROGRESS_HOLD_DEFAULT,
            POS_X_KEY: 0, POS_Y_KEY: 0, POS_W_KEY: 0, POS_H_KEY: 0,
            BAR_POS_X_KEY: 0, BAR_POS_Y_KEY: 0,
            PROGRESS_POS_FRAME_KEY: POS_FRAME_ANCHOR,
            PROGRESS_ORIENTATION_KEY: PROGRESS_ORIENT_HORIZONTAL,
            PROGRESS_ALIGNMENT_KEY: PROGRESS_ALIGN_DAMAGE_LOG,
            FOLLOW_CAROUSEL_KEY: True}


def clamp_pos(v):
    """Coerce a position coordinate to an int in [-POS_MAX, POS_MAX]. 0/0 = auto/unseeded.
    Pure + engine-free (unit-tested); non-numeric -> 0.

    A NEGATIVE COORDINATE IS A REAL POSITION, not garbage: a bar dragged off the left/top edge
    stores one, and clamping it to 0 would both teleport the bar and (at 0/0) silently un-pin it.
    Only the magnitude is guarded, symmetrically."""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 0
    if v < -POS_MAX:
        return -POS_MAX
    if v > POS_MAX:
        return POS_MAX
    return v


def clamp_variant(v, max_index=PROGRESS_VARIANT_MOVING_AVERAGE):
    """Coerce a stored RadioButtonGroup value to a legal 0-based option index in
    [0, max_index]. Pure + engine-free (unit-tested).

    Shared by BOTH radios -- `max_index` defaults to the variant radio's ceiling, and the size
    radio passes PROGRESS_SIZE_LARGE. These are the mod's only non-bool settings, so this is
    also the one trust boundary where a hostile store could leak the wrong TYPE into the bridge:
    a bool is never a legal index (bool is an int subclass, so a plain int() would silently pass
    True through as 1), and neither is a non-numeric, negative or out-of-range value. All of them
    fall back to 0 -- the template DEFAULT for either radio (Damage Efficiency / the shipped
    size), which is the only sane landing spot for a value we cannot trust."""
    if isinstance(v, bool):
        return 0
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 0
    if 0 <= v <= max_index:
        return v
    return 0


def clamp_hold_seconds(v):
    """Coerce the stored hold duration to a whole number of seconds in
    [PROGRESS_HOLD_MIN, PROGRESS_HOLD_MAX]. Pure + engine-free (unit-tested).

    Third trust boundary alongside clamp_pos / clamp_variant, and the same bool trap: bool is an
    int subclass, so isinstance must be tested FIRST or True would pass through as a legal 1
    second. Garbage (a bool, a non-numeric) falls back to the template DEFAULT; a merely
    OUT-OF-RANGE number is clamped to the nearest bound, like clamp_pos -- the user asked for
    "as long as possible", not for 5."""
    if isinstance(v, bool):
        return PROGRESS_HOLD_DEFAULT
    try:
        v = int(v)
    except (TypeError, ValueError):
        return PROGRESS_HOLD_DEFAULT
    if v < PROGRESS_HOLD_MIN:
        return PROGRESS_HOLD_MIN
    if v > PROGRESS_HOLD_MAX:
        return PROGRESS_HOLD_MAX
    return v

# Live flag state (seeded from MSA in register(); defaults until then / if MSA is absent).
_settings = dict(DEFAULTS)

# apply_settings callbacks the entry point subscribes (one per feature bridge).
_listeners = []

# True once we've registered with MSA. Kept so register() is idempotent AND self-healing:
# a failed attempt (MSA not loaded yet at our import time -- our id sorts before izeberg's)
# leaves this False, so a later register() (first hangar mount) retries until it sticks.
_registered = False

# True only WHILE _on_changed's write-back (updateModSettings/saveState) is in flight. Guards
# against a re-entrant onSettingsChanged -- including a SYNCHRONOUS one fired from inside
# updateModSettings itself -- landing on a stale pre-derivation snapshot and deriving against it.
# While set, _on_changed still _apply()s + _notify()s (so the fan-out isn't lost) but skips
# _derive_layout entirely. See TASKS/in-battle-bar-layout-auto-set-redesign.md Trap 1(c).
_deriving = False


def _coerce(key, value):
    """Coerce a saved value to the type this key stores: the position coords are clamped ints,
    the progress-bar variant/size/orientation/alignment are clamped radio INDEXes, the hold
    duration a clamped second count, the pos-frame marker one of two known strings, everything
    else is a bool. Pure + engine-free.

    Every non-bool branch is load-bearing: falling through to bool() would turn a radio's
    index 1 into True and index 0 into False (and the hold's 5 into True, or a "legacy" string
    into True too), which then round-trips back to MSA as a bool and destroys the setting."""
    if key in _POS_KEYS:
        return clamp_pos(value)
    if key == PROGRESS_VARIANT_KEY:
        return clamp_variant(value)
    if key == PROGRESS_SIZE_KEY:
        return clamp_variant(value, PROGRESS_SIZE_LARGE)
    if key == PROGRESS_ORIENTATION_KEY:
        return clamp_variant(value, PROGRESS_ORIENT_VERTICAL)
    if key == PROGRESS_ALIGNMENT_KEY:
        return clamp_variant(value, PROGRESS_ALIGN_FREE)
    if key == PROGRESS_HOLD_SECONDS_KEY:
        return clamp_hold_seconds(value)
    if key == PROGRESS_POS_FRAME_KEY:
        return value if value == POS_FRAME_LEGACY else POS_FRAME_ANCHOR
    return bool(value)


def merge_settings(saved):
    """Overlay only the known keys from `saved` onto DEFAULTS, coercing each to its type
    (position coords -> clamped int, the rest -> bool). Pure.

    Tolerates None / non-dict / partial dicts / unknown extra keys (MSA replaces the whole
    dict, so a stale or foreign store must degrade to safe defaults, never raise)."""
    out = dict(DEFAULTS)
    if isinstance(saved, dict):
        for key in DEFAULTS:
            if key in saved:
                out[key] = _coerce(key, saved[key])
    return out


def garage_enabled():
    """Whether the hangar percentile-bar widget is enabled (default True)."""
    return bool(_settings.get(GARAGE_KEY, True))


def battle_enabled():
    """Whether the in-battle overlay is enabled (default True)."""
    return bool(_settings.get(BATTLE_KEY, True))


def battle_alt_key_enabled():
    """Whether the "show only while Alt held" peek mode is enabled (default False).

    Independent of battle_enabled(): the consumer (battle_bar_visible) applies the soft-gate
    so this is ignored while battle_enabled() is on."""
    return bool(_settings.get(BATTLE_ALT_KEY, False))


def counted_assistance_enabled():
    """Whether the in-battle "counted assistance" row is enabled (default True since v13)."""
    return bool(_settings.get(COUNTED_ASSIST_KEY, True))


def progress_bar_enabled():
    """Whether the transient centre-screen next-mark progress bar is enabled (default False).

    Independent of battle_enabled(): the progress bar is its own feature, not part of the
    In-Battle Widget overlay."""
    return bool(_settings.get(PROGRESS_BAR_KEY, False))


def progress_show_events():
    """Whether a battle event may raise (and re-target) the progress bar (default True).

    FOLDS "ALWAYS" IN, like the Transitions master below: with the bar permanently up the other
    two triggers are ignored, and MSA keeps storing + pushing a greyed control's value, so the
    fold has to live here. It is also what keeps the bar's NUMBERS live while it is pinned -- the
    JS commits new values on the same trigger it shows on."""
    return (bool(_settings.get(PROGRESS_SHOW_ALWAYS_KEY, False))
            or bool(_settings.get(PROGRESS_SHOW_EVENTS_KEY, True)))


def progress_alt_held(alt_held):
    """The `altHeld` the two centre-screen bars are pushed, given the raw Alt state.

    ONE place, so "Always" and "Alt Press" can never disagree between the two bars:
      * "Always" on  -> True forever. The JS transient pins the bar at its hold plateau for as
        long as this is true and never ends the run, so a permanently-held Alt IS the Always
        mode -- no fourth code path, no new CSS.
      * otherwise    -> the real Alt state, but only while "Alt Press" is on."""
    if bool(_settings.get(PROGRESS_SHOW_ALWAYS_KEY, False)):
        return True
    return bool(alt_held) and bool(_settings.get(PROGRESS_SHOW_ALT_KEY, True))


def progress_bar_variant():
    """Which progress bar the master draws, as the radio's 0-based option INDEX:
    PROGRESS_VARIANT_EFFICIENCY (0, the default) or PROGRESS_VARIANT_MOVING_AVERAGE (1).

    An int, NOT a bool -- callers pick a window off it, so re-clamp on read (like the
    position getters) and never let a corrupt store leak a bool or an out-of-range index.
    Meaningless while progress_bar_enabled() is off: the master gates the whole feature."""
    return clamp_variant(_settings.get(PROGRESS_VARIANT_KEY,
                                       PROGRESS_VARIANT_EFFICIENCY))


def progress_bar_size():
    """How large the progress bar draws, as the radio's 0-based option INDEX:
    PROGRESS_SIZE_DEFAULT (0, the default) or PROGRESS_SIZE_LARGE (1).

    An int, NOT a bool -- so re-clamp on read (mirroring progress_bar_variant) and never let a
    corrupt store leak a bool or an out-of-range index to the widget. Meaningless while
    progress_bar_enabled() is off: the master gates the whole feature."""
    return clamp_variant(_settings.get(PROGRESS_SIZE_KEY, PROGRESS_SIZE_DEFAULT),
                         PROGRESS_SIZE_LARGE)


def progress_transitions_events():
    """Whether the progress bar ANIMATES (fade + slide) when a battle event pulls it up and lets
    it go again (default True). False -> both are instant; the bar still shows and still hides.

    FOLDS THE MASTER IN, which is the whole point of these two getters: the JS never sees
    PROGRESS_TRANSITIONS_KEY at all, so there is exactly one place that ANDs the group together and
    no chance of the widget honouring a child while the master is off."""
    return (bool(_settings.get(PROGRESS_TRANSITIONS_KEY, True))
            and bool(_settings.get(PROGRESS_TRANS_EVENTS_KEY, True)))


def progress_transitions_manual():
    """Whether the progress bar ANIMATES when the Alt-key peek brings it up and releases it
    (default True). False -> both are instant, matching the game's own HUD, which does not animate
    on Alt. Folds the master in -- see progress_transitions_events()."""
    return (bool(_settings.get(PROGRESS_TRANSITIONS_KEY, True))
            and bool(_settings.get(PROGRESS_TRANS_MANUAL_KEY, True)))


def progress_hold_seconds():
    """How long the progress bar stays up once it is up, in whole seconds (default 5).

    An int, NOT a bool -- so re-clamp on read (mirroring the two radio getters) and never let a
    corrupt store leak a bool or an absurd duration to the widget.

    DELIBERATELY NOT master-folded, unlike its two group siblings above: this is a DURATION, not a
    switch, so ANDing the Transitions master in would report 0/False whenever transitions are off
    -- a bar with no hold at all, which is not what that checkbox means. The master only decides
    whether the enter/exit MOVE; the hold is how long the bar stays, animated or not (an un-animated
    run ends AT the hold rather than fading out of it), and the JS gates showing on
    transEvents/transManual instead.

    ...and BECAUSE of that, its MSA control is deliberately UNGROUPED too -- a plain top-level row
    under the "Transitions" header rather than a child of the "Enabled" master (see _template()).
    Do not re-parent it into the group: greying the slider out while "Enabled" is off would tell the
    user this value stops applying, which is exactly the claim this getter refuses to make."""
    return clamp_hold_seconds(_settings.get(PROGRESS_HOLD_SECONDS_KEY, PROGRESS_HOLD_DEFAULT))


def pos_x():
    """The pinned widget top-left x (px), or 0 for auto (CSS bottom-right default)."""
    return clamp_pos(_settings.get(POS_X_KEY, 0))


def pos_y():
    """The pinned widget top-left y (px), or 0 for auto (CSS bottom-right default)."""
    return clamp_pos(_settings.get(POS_Y_KEY, 0))


def pos_w():
    """The viewport width (px) a pinned position was captured at (0 = unknown)."""
    return clamp_pos(_settings.get(POS_W_KEY, 0))


def pos_h():
    """The viewport height (px) a pinned position was captured at (0 = unknown)."""
    return clamp_pos(_settings.get(POS_H_KEY, 0))


def bar_pos_x():
    """The in-battle bar's stored X in LOGICAL GUI px: an anchor-relative OFFSET under Damage
    Log/Minimap, or (as of v22, see PROGRESS_POS_FRAME_KEY) the ANCHOR POINT under Free. 0 means
    auto (the shipped centre anchor / "not yet materialised", see bar_window's AUTO branch).
    Shared by both bars -- see BAR_POS_X_KEY."""
    return clamp_pos(_settings.get(BAR_POS_X_KEY, 0))


def bar_pos_y():
    """The in-battle bar's stored Y -- see bar_pos_x()."""
    return clamp_pos(_settings.get(BAR_POS_Y_KEY, 0))


def progress_bar_pos_frame():
    """Which frame bar_pos_x()/bar_pos_y() are currently expressed in under Alignment=Free:
    POS_FRAME_ANCHOR (the default -- the pair IS the anchor point, domain.positioning.
    free_top_left) or POS_FRAME_LEGACY (a pre-v22 pair that is still a literal top-left, pending
    conversion at this bar's next battle mount -- see bar_window.BarHost._materialise and the
    SETTINGS_VERSION 21->22 comment). Meaningless under any other alignment.

    Re-coerced on read, like the radio getters -- a corrupt store falls back to POS_FRAME_ANCHOR,
    the safe choice (treating a legacy pair as an anchor point misplaces the bar once; treating an
    anchor point as legacy would misplace it on EVERY size change, which is the whole bug this
    frame exists to prevent)."""
    return _coerce(PROGRESS_POS_FRAME_KEY,
                   _settings.get(PROGRESS_POS_FRAME_KEY, POS_FRAME_ANCHOR))


def progress_bar_orientation():
    """Which axis the progress/efficiency bars draw on, as the radio's 0-based option INDEX:
    PROGRESS_ORIENT_HORIZONTAL (0, the default) or PROGRESS_ORIENT_VERTICAL (1). Shared by both
    bars, like the position pair above.

    An int, NOT a bool -- re-clamp on read (like progress_bar_variant / progress_bar_size) and
    never let a corrupt store leak a bool or an out-of-range index."""
    return clamp_variant(_settings.get(PROGRESS_ORIENTATION_KEY, PROGRESS_ORIENT_HORIZONTAL),
                         PROGRESS_ORIENT_VERTICAL)


def progress_bar_alignment():
    """Which anchor the position steppers offset FROM, as the radio's 0-based option INDEX:
    PROGRESS_ALIGN_DAMAGE_LOG (0, the default), PROGRESS_ALIGN_MINIMAP (1) or
    PROGRESS_ALIGN_FREE (2).

    An int, NOT a bool -- re-clamp on read (like the other radio getters). Kept in sync by
    set_bar_position() (-> Free, the drag-end seam) and _on_changed's _derive_layout auto-set
    rules: Orientation and Alignment are two views of ONE choice, fully mutually derived (an
    Orientation switch re-anchors Alignment EVEN FROM FREE -- Free is no longer sticky -- and an
    Alignment switch re-anchors Orientation the same way); a position edit (stepper or drag) beats
    both and forces Free. See _derive_layout's table for the state machine."""
    return clamp_variant(_settings.get(PROGRESS_ALIGNMENT_KEY, PROGRESS_ALIGN_DAMAGE_LOG),
                         PROGRESS_ALIGN_FREE)


def follow_carousel():
    """Whether a pinned widget keeps riding the carousel's vertical shifts (default True)."""
    return bool(_settings.get(FOLLOW_CAROUSEL_KEY, True))


def add_change_listener(fn):
    """Register a zero-arg callback invoked (guarded) after the flags change."""
    if fn not in _listeners:
        _listeners.append(fn)


def _notify():
    for fn in list(_listeners):
        try:
            fn()
        except Exception:
            LOG_CURRENT_EXCEPTION()


def _seed(saved):
    """Replace the WHOLE flag state from an AUTHORITATIVE store (registration only), filling
    defaults for any key it omits. Used where `saved` fully defines our state."""
    global _settings
    _settings = merge_settings(saved)


def _apply(saved):
    """Overlay only the PRESENT known keys from `saved` onto the live cache IN PLACE; a key
    ABSENT from `saved` keeps its current value.

    This is the live-change path, and preserving current values is load-bearing: MSA fires the
    onSettingsChanged callback GLOBALLY, so `_on_changed` also runs for OTHER mods' changes,
    handed a payload that contains none of OUR keys. Merging that onto DEFAULTS (as a naive
    replace would) snapped every flag back to its default -- the bug where a foreign mod's
    settings sync silently re-enabled the always-on battle overlay, so it ignored
    "Battle Widget Enabled = off" + "on Alt Key = on". A foreign payload now no-ops here."""
    if not isinstance(saved, dict):
        return
    for key in DEFAULTS:
        if key in saved:
            _settings[key] = _coerce(key, saved[key])


def _checkbox(key, rendered):
    """One MSA CheckBox descriptor. `varName` matches a DEFAULTS key so the dict MSA returns
    maps straight through merge_settings; text/tooltip come from settings_i18n (English
    fallback per key).

    The tooltip key is OMITTED rather than emitted empty when the rendered row has none (same shape
    as _radio / _label): the Transitions group's "Events" / "Manual" children are LABEL-ONLY rows --
    one-word switches the master's tooltip already explains -- and handing the panel an empty tooltip
    to render is not the same as having none. _sync_template_text tolerates it (its `tip is not None`
    guard skips a tipless rendered entry, so it never writes the key back on)."""
    control = {
        "type": "CheckBox",
        "text": rendered["text"],
        "value": DEFAULTS[key],
        "varName": key,
    }
    tooltip = rendered.get("tooltip")
    if tooltip:
        control["tooltip"] = tooltip
    return control


def _stepper(key, rendered):
    """One MSA NumericStepper descriptor for a position coordinate (px). `varName` matches a
    DEFAULTS key so the returned int maps straight through merge_settings; the range is
    [-POS_MAX, POS_MAX] with manual entry allowed. Shows 0 (auto) until a drag / edit pins a value.

    THE MINIMUM IS NEGATIVE, and it has to be: a bar dragged off the left/top screen edge stores a
    negative coordinate (there is no on-screen safezone -- see domain/positioning), and MSA echoes a
    stepper's value back through onSettingsChanged, so a `minimum: 0` would snap that position back
    to 0 the moment the user merely OPENED the panel. The stored descriptor is what the panel
    renders, and register()'s saved-truthy path never calls setModTemplate, so this bound only
    reaches an existing install through a forward SETTINGS_VERSION bump (18 -> 19 -> 20).

    The tooltip is OMITTED rather than hard-indexed when the rendered row has none, matching
    _checkbox / _radio / _label. Both steppers do carry one today, so this never fires -- it is
    here because the hard index is what killed the WHOLE settings panel once (a KeyError inside
    _template(), i.e. inside register()'s guarded try, so the only symptom was no panel at all)."""
    control = {
        "type": "NumericStepper",
        "text": rendered["text"],
        "value": DEFAULTS[key],
        "minimum": -POS_MAX,
        "maximum": POS_MAX,
        "snapInterval": 1,
        "canManualInput": True,
        "varName": key,
    }
    tooltip = rendered.get("tooltip")
    if tooltip:
        control["tooltip"] = tooltip
    return control


def _slider(key, rendered):
    """One MSA Slider descriptor -- the hold duration, in whole SECONDS. `varName` matches a
    DEFAULTS key so the returned int maps straight through merge_settings, and `snapInterval: 1`
    keeps the value an int (see clamp_hold_seconds for why a fraction is not wanted).

    Built as a plain dict rather than through Aslain's templates.createSlider, for the same reason
    every other helper here is (see _radio): it keeps _template() a pure, unit-testable dict with
    no gui.aslainMenu import, and MSA does no descriptor validation at all, so the dict IS what
    that helper emits -- createSlider is createStepper(SLIDER, ...) plus a `format` key, i.e.
    exactly _stepper's shape minus canManualInput. An API that does not know the Slider type at all
    just skips the row (the AS3 panel logs "Unexpected type of component:"), leaving the three
    Transitions checkboxes above it working and progress_hold_seconds() on its 5 s default.

    NO `masterVarName`, and never one: this control is deliberately NOT a child of the Transitions
    master (see _template() and progress_hold_seconds()), so it is emitted top-level and un-indented.
    Nothing here sets the key -- only _grouped_column1 does, and this descriptor is never passed to
    it -- so the key is genuinely ABSENT rather than present-and-None (MSA reads the key's presence,
    so a None would still bind it to a master named None).

    `{{value}}` is MSA's own substitution token, so the panel renders "5 s" rather than a bare
    number. `tooltip` is OMITTED, never emitted empty, exactly like _checkbox / _radio / _label --
    a hard index there is what killed the WHOLE settings panel once (a KeyError inside _template(),
    i.e. inside register()'s guarded try, so the only symptom was no panel at all)."""
    control = {
        "type": "Slider",
        "text": rendered["text"],
        "value": DEFAULTS[key],
        "minimum": PROGRESS_HOLD_MIN,
        "maximum": PROGRESS_HOLD_MAX,
        "snapInterval": 1,
        "format": "{{value}} s",
        "varName": key,
    }
    tooltip = rendered.get("tooltip")
    if tooltip:
        control["tooltip"] = tooltip
    return control


def _radio(key, rendered):
    """One MSA RadioButtonGroup descriptor for a mutually-exclusive choice. `varName` matches a
    DEFAULTS key and `value` is the 0-BASED OPTION INDEX (never a label); `options` is the
    localized label tuple settings_i18n attached to the rendered entry, in index order.

    Built as a plain dict rather than through Aslain's templates.createRadioButtonGroup -- the
    same shape that helper emits (type/text/varName/value/tooltip/options/inline) -- because it
    keeps _template() a pure, unit-testable dict with no gui.aslainMenu import. An API that does
    not know RadioButtonGroup at all (the izeberg fallback) simply skips the control -- the
    PROGRESS_BAR_KEY checkbox above it is a plain CheckBox and keeps working, and
    progress_bar_variant() then reports its 0 default.

    `inline: True` renders the options as ONE HORIZONTAL ROW, which is what makes two standalone
    two-option radios fit beside each other instead of costing four stacked rows. It is emitted as
    a plain KEY, never through the helper's `inline` KWARG -- that kwarg raises TypeError on
    MSA < 1.6.1, while an unknown key just rides through (MSA does no descriptor validation).

    `tooltip` is OMITTED, not empty, when the row has none: createBase adds the key only when the
    tooltip is not None, so a control with nothing to explain simply has no key. Emitting "" would
    hand the panel an empty tooltip to render -- and a tooltip written into a stored template can
    never be removed again (_sync_template_text only overwrites)."""
    control = {
        "type": "RadioButtonGroup",
        "text": rendered["text"],
        "value": DEFAULTS[key],
        "varName": key,
        "inline": True,
        "options": [{"label": label} for label in rendered["options"]],
    }
    tooltip = rendered.get("tooltip")
    if tooltip:
        control["tooltip"] = tooltip
    return control


def _label(key, rendered):
    """A plain MSA Label header (no varName -- not a stored value). Carries text, and a tooltip
    only when there IS one, so _sync_template_text can refresh it in lockstep with the column's
    other controls.

    `rendered["text"]` arrives ALREADY wrapped in <b>...</b> for the five HEADER_KEYS --
    settings_i18n.build() does that wrap, once, so this template and _sync_template_text see
    the IDENTICAL string (see that docstring for why: wrapping here too would make every
    register() call -- including the one that just built the freshly-bolded template -- see a
    mismatch, strip the bold back out, and fire a pointless saveState()). This function only
    adds `useHTML: True` for those rows -- MSA labels render as HTML by default
    (createBase(..., useHTML=True)), but _label hand-builds this dict and never emitted that
    key, so the default was unverified from our side; emitting it ourselves removes the doubt.
    The "Position" sub-label above the steppers is deliberately NOT in HEADER_KEYS, so the
    weight difference is what makes the hierarchy read.

    The tooltip key is OMITTED rather than emitted empty (same shape as _radio): a bare header is
    text-only, and handing the panel an empty tooltip to render is not the same as having none.
    _sync_template_text already tolerates it -- its `tip is not None` guard skips a rendered entry
    with no tooltip, so it never writes a key back onto a tipless row. NOTE _sync_template_text
    only ever rewrites `text`/`tooltip`, never `useHTML` -- so moving a key into/out of
    HEADER_KEYS needs a SETTINGS_VERSION bump to reach an existing install (see that constant)."""
    control = {"type": "Label", "text": rendered["text"]}
    if key in settings_i18n.HEADER_KEYS:
        control["useHTML"] = True
    tooltip = rendered.get("tooltip")
    if tooltip:
        control["tooltip"] = tooltip
    return control


def _empty():
    """A blank spacer row -- MSA's own "Empty" control type (optional int `height`, default 20px).
    Carries NO text at all, which is why settings_i18n's positional key tuples give it a `None`
    sentinel slot: _sync_template_text's `if not rendered: continue` then skips it for free while
    the zip stays aligned with every later control."""
    return {"type": "Empty"}


def _gate_and(control, conditions):
    """Gate `control` on SEVERAL peers at once (MSA's multi-condition form, ANDed).

    `conditions` is a ((varName, value), ...) tuple; the emitted `condition` is always "==".
    NOTE this REPLACES any createControlsGroup parenting: MSA's `conditions` form does not set
    masterVarName, so a control gated this way must carry its group master as one of the
    conditions (and the now-dead masterVarName is dropped, so nothing reads a stale parent)."""
    control.pop("masterVarName", None)
    control["conditions"] = [{"masterVarName": var, "condition": "==", "masterValue": value}
                             for var, value in conditions]
    control["conditionsLogic"] = "AND"
    control["masterIndent"] = True
    return control


def _grouped_column1(master, children):
    """ONE column-1 master with its indented children, greyed out while the master is off.
    Column 1 calls this THREE times -- for the "In-Battle Widget", "Progress Bar" and
    "Transitions" masters -- and splices the flat lists together (see _template()). The children
    are type-agnostic (createControlsGroup only writes a masterVarName), but the Transitions
    category's hold-duration Slider is still NOT passed as one -- it is spliced on after the group
    as a top-level row, which is the only reason it carries no masterVarName (see _slider()).

    Prefer Aslain's templates.createControlsGroup(master, children, indent=True) -- it returns
    the flat [master, child1, child2] list and binds each child to the master (a masterVarName
    key = master's varName; the panel disables + indents the children while the master is off).
    FEATURE-DETECT + degrade: if that helper is absent (older MSA / izeberg fallback) we set
    masterVarName by hand -- which is exactly what the helper does -- so the children still list
    under the master and older builds that ignore the key simply show them as plain checkboxes."""
    try:
        from gui.aslainMenu import templates
        return templates.createControlsGroup(master, children, indent=True)
    except Exception:
        for child in children:
            child["masterVarName"] = master["varName"]
        return [master] + list(children)


def _template():
    """The MSA panel descriptor, grouped into three NAMED CATEGORIES. Two columns ONLY -- a third
    column does not render in the panel at all (that was tried and reverted; see the
    SETTINGS_VERSION history), so a category is not a column but a bare Label header row followed
    by that feature's controls, and categories are separated by an "Empty" spacer row.
    Column 1: "Battle Calculator" (the In-Battle Widget master + its "Alt Press" and "Counted
    Assistance Row" children), then "Battle Progress" (the Progress Bar master + its three
    VISIBILITY children, an Empty spacer, the standalone Mode and Scale radios), then a SECOND
    Empty spacer and "Transitions" (its own header + the Transitions master with its Events, Alt
    Press children, a spacer, then the UNGROUPED Hold Duration slider), then a THIRD Empty spacer
    and "Layout" (header text; i18n key stays catBarPosition -- its own header + the standalone
    Orientation and Alignment radios ABOVE the two standalone X/Y steppers). Column 2: "Garage
    Widget" (the garage master), then the "Layout" group -- a header, Follow Carousel, an Empty
    spacer, a "Position" sub-label, then the X/Y numeric steppers. Because the header names the
    feature, each master's
    own label is just "Enabled".
    Every visible label/tooltip comes from settings_i18n at the client's language (English
    fallback). The six category/group headers render BOLD (see _label); "Position" does not."""
    t = settings_i18n.panel_text()
    battle_master = _checkbox(BATTLE_KEY, t["battleWidget"])
    battle_alt = _checkbox(BATTLE_ALT_KEY, t["battleAltKey"])
    counted = _checkbox(COUNTED_ASSIST_KEY, t["countedAssist"])
    progress_master = _checkbox(PROGRESS_BAR_KEY, t["progressBar"])
    show_events = _checkbox(PROGRESS_SHOW_EVENTS_KEY, t["progressShowEvents"])
    show_alt = _checkbox(PROGRESS_SHOW_ALT_KEY, t["progressShowAlt"])
    show_always = _checkbox(PROGRESS_SHOW_ALWAYS_KEY, t["progressShowAlways"])
    progress_variant = _radio(PROGRESS_VARIANT_KEY, t[settings_i18n.VARIANT_KEY])
    progress_size = _radio(PROGRESS_SIZE_KEY, t["progressSize"])
    progress_orientation = _radio(PROGRESS_ORIENTATION_KEY, t["progressOrientation"])
    progress_alignment = _radio(PROGRESS_ALIGNMENT_KEY, t["progressAlignment"])
    trans_master = _checkbox(PROGRESS_TRANSITIONS_KEY, t["progressTransitions"])
    trans_events = _checkbox(PROGRESS_TRANS_EVENTS_KEY, t["progressTransEvents"])
    trans_manual = _checkbox(PROGRESS_TRANS_MANUAL_KEY, t["progressTransManual"])
    trans_hold = _slider(PROGRESS_HOLD_SECONDS_KEY, t["progressHoldSeconds"])
    garage = _checkbox(GARAGE_KEY, t["garageWidget"])
    # The Progress Bar master with its three VISIBILITY children. _grouped_column1 binds all three
    # to PROGRESS_BAR_KEY; the first two then TRADE that binding for an AND gate, because they are
    # also meaningless while "Always" is on (MSA still stores and still pushes their value while
    # greyed, which is why progress_show_events / progress_alt_held fold "Always" in as well).
    progress_group = _grouped_column1(progress_master, [show_events, show_alt, show_always])
    for child in (show_events, show_alt):
        _gate_and(child, ((PROGRESS_BAR_KEY, True), (PROGRESS_SHOW_ALWAYS_KEY, False)))
    return {
        "modDisplayName": MOD_DISPLAY_NAME,
        "enabled": True,
        "settingsVersion": SETTINGS_VERSION,
        # column1: THREE categories separated by Empty spacers, each a bare Label header followed
        # by that feature's controls. The header rows carry no varName and no tooltip.
        #
        # The Progress Bar controls are deliberately NOT passed as children of the In-Battle
        # group: a grouped child inherits THAT master's varName, so MSA would grey the progress
        # bar out whenever the unrelated In-Battle Widget is off. That hazard is exactly why the
        # Progress Log checkbox used to sit outside the group with no masterVarName at all, and
        # it still holds for BATTLE_KEY. Giving the progress bar its OWN master (a second
        # _grouped_column1 call) is a deliberate re-parent that keeps the property: its children
        # grey out with PROGRESS_BAR_KEY and with nothing else, and PROGRESS_BAR_KEY itself
        # stays a group MASTER, so it never carries a masterVarName either.
        #
        # The two RADIOS are deliberately STANDALONE (no master, no condition): Mode and Scale
        # describe the bar itself rather than when it shows, they are `inline` so they cost one row
        # each, and leaving them ungated keeps them readable while the feature is off -- the same
        # call already made for the column-2 steppers. An Empty spacer heads them, same purely
        # visual role as every other spacer in this column.
        #
        # Wire order MUST stay in lockstep with settings_i18n.COL1_KEYS (see
        # _sync_template_text) -- its zip is positional, so a reorder retitles the wrong control.
        #
        # The Transitions master is a THIRD _grouped_column1 call spliced on, for the same reason
        # the Progress Bar one is its own group: its TWO switch children must grey out with IT and
        # with nothing else. It is a CATEGORY of its own -- an Empty spacer and its own bold Label
        # header -- which is what lets its master read just "Enabled" like the other three.
        #
        # THE HOLD SLIDER IS DELIBERATELY *NOT* A CHILD OF THAT MASTER: it hangs off the
        # "Transitions" HEADER instead, as a plain top-level un-indented row spliced on AFTER the
        # group, with an Empty spacer immediately ahead of it (same purely visual role as every
        # other spacer in this column). The panel order is unchanged (header, Enabled, Events, Alt
        # Press, spacer, Hold Duration) -- it just neither indents nor greys out with "Enabled".
        # That matches the getter: progress_hold_seconds() is the one member of this group that is
        # NOT master-folded, because a DURATION is not a switch -- the bar stays up for that long
        # whether or not the enter/exit animate (an un-animated run ends AT the hold rather than
        # fading out of it). Greying it under "Enabled" claimed the opposite. See
        # progress_hold_seconds().
        #
        # All three category headers render BOLD -- settings_i18n.build() already wrapped their
        # text (see _label); this only adds the matching useHTML key.
        #
        # ...and a FOURTH category closes the column: "Layout" (header text; i18n key stays
        # catBarPosition -- see SETTINGS_VERSION 20->21), the standalone Orientation and Alignment
        # radios ABOVE the two steppers that mirror the Ctrl+drag. All four are STANDALONE like the
        # column-2 pair (no master, no condition) for the same reason: a bar's shape/anchor and a
        # coordinate all stay readable and editable while the feature is off. They are APPENDED at
        # the very end, so no earlier control's positional pairing moves.
        "column1": ([_label("catBattleCalc", t["catBattleCalc"])]
                    + _grouped_column1(battle_master, [battle_alt, counted])
                    + [_empty(), _label("catBattleProgress", t["catBattleProgress"])]
                    + progress_group
                    + [_empty(), progress_variant, progress_size,
                       _empty(), _label("catTransitions", t["catTransitions"])]
                    + _grouped_column1(trans_master, [trans_events, trans_manual])
                    + [_empty(), trans_hold,
                       _empty(), _label("catBarPosition", t["catBarPosition"]),
                       progress_orientation, progress_alignment,
                       _stepper(BAR_POS_X_KEY, t["barPosX"]),
                       _stepper(BAR_POS_Y_KEY, t["barPosY"])]),
        # column2: the BOLD category header, the garage master, an Empty spacer, then the "Layout"
        # group -- its own BOLD header, Follow Carousel, a SECOND Empty spacer, a non-bold
        # "Position" sub-label, then the X/Y steppers. Follow Carousel sits ABOVE the steppers
        # (moved up so the whole group reads top-to-bottom as "Layout" -> toggle -> spacer ->
        # position), and "Position" heads just the two steppers -- deliberately NOT bold, so the
        # weight difference marks it as a sub-level under "Layout" rather than a THIRD header.
        # Column 2 stays FLAT: the steppers and Follow Carousel
        # are all STANDALONE (no masterVarName), so they keep working -- and stay ungreyed -- while
        # the garage widget is off. Steppers show 0 (auto) until a drag / edit pins a px; Follow
        # Carousel ships ON. The wire order here MUST stay in lockstep with settings_i18n.COL2_KEYS
        # (see _sync_template_text) -- its zip is positional, so a reorder retitles the wrong
        # control.
        "column2": [
            _label("catGarage", t["catGarage"]),
            garage,
            _empty(),
            _label("positioning", t["positioning"]),
            _checkbox(FOLLOW_CAROUSEL_KEY, t["followCarousel"]),
            _empty(),
            _label("positionSub", t["positionSub"]),
            _stepper(POS_X_KEY, t["posX"]),
            _stepper(POS_Y_KEY, t["posY"]),
        ],
    }


def _candidate_apis():
    """The settings-api instance(s) this client exposes, in PREFERENCE order. Aslain's
    gui.aslainMenu is probed FIRST (that is where the user's data now lives) with izeberg's
    gui.modsSettingsApi as the legacy fallback -- so a lingering izeberg install can never win
    over Aslain. With both present there are TWO separate objects; on a plain install just one.
    Return whichever import(s) succeed, de-duped, primary first."""
    apis = []
    try:
        from gui.aslainMenu import g_modsSettingsApi as a
        apis.append(a)
    except Exception:
        pass
    try:
        from gui.modsSettingsApi import g_modsSettingsApi as b
        if b not in apis:
            apis.append(b)
    except Exception:
        pass
    return apis


def _primary_api():
    """The preferred settings-api instance (Aslain first, else izeberg), or None if MSA is
    absent. This is the object register() drives getModSettings/setModTemplate/registerCallback
    through."""
    apis = _candidate_apis()
    return apis[0] if apis else None


def _sync_template_text(api):
    """Refresh a stored template's label/tooltip text to the client's active language.

    MSA stores a COPY of the template text at registration and renders from it; on an
    EXISTING install register() takes the saved-truthy branch and never re-applies the
    template text, so a language change would otherwise never show. This walks the stored
    template in lockstep with settings_i18n's column key order and overwrites each entry's
    text/tooltip from panel_text(), saving only if something changed. Idempotent: a no-op on
    a fresh install (text already matches). Guarded; text-only, no settingsVersion bump."""
    try:
        tmpl = (getattr(api, "state", None) or {}).get("templates", {}).get(LINKAGE)
        if not isinstance(tmpl, dict):
            return
        t = settings_i18n.panel_text()
        changed = False
        for col, keys in (("column1", settings_i18n.COL1_KEYS),
                          ("column2", settings_i18n.COL2_KEYS)):
            for comp, key in zip(tmpl.get(col) or [], keys):
                rendered = t.get(key) if isinstance(comp, dict) else None
                if not rendered:
                    continue
                if comp.get("text") != rendered["text"]:
                    comp["text"] = rendered["text"]
                    changed = True
                tip = rendered.get("tooltip")
                if tip is not None and comp.get("tooltip") != tip:
                    comp["tooltip"] = tip
                    changed = True
        if changed and hasattr(api, "saveState"):
            api.saveState()
            LOG_DEBUG("[moe] synced settings template text to client language")
    except Exception:
        LOG_CURRENT_EXCEPTION()


# Object ids of api instances we've already hooked onResetMod on, so retries never stack
# duplicate handlers.
_reset_hooked = set()


def _subscribe_reset(api):
    """Subscribe _on_reset to an api's onResetMod event (the panel 'reset to defaults'
    button, which fires onResetMod -- NOT onSettingsChanged), de-duped by object id. No-op if
    the api lacks onResetMod (pure izeberg) or is already hooked."""
    try:
        if api is None or not hasattr(api, "onResetMod"):
            return
        if id(api) in _reset_hooked:
            return
        api.onResetMod += _on_reset
        _reset_hooked.add(id(api))
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _migrate_pre_v13_variant(old_raw):
    """Flip a PRE-v13 progress_bar_variant raw int in place, so an upgrading user keeps the
    bar they actually chose across the v13 option-order flip (see PROGRESS_VARIANT_KEY /
    the SETTINGS_VERSION 12->13 comment). A store already at v13+ is left untouched.

    There is no stored settingsVersion int to compare against directly (old_raw is just the
    flat varName->value dict), so "pre-v13" is inferred from the ABSENCE of a key introduced
    in that SAME bump (PROGRESS_SHOW_EVENTS_KEY) -- a v13+ store always carries it, since
    setModTemplate/register() seed every varName current at the time it was written.

    Fail-soft, and local to this one key: a missing / non-int / out-of-range value is left
    alone (clamp_variant falls back to the safe default when it's read); this is a single
    targeted fixup, not a general per-key migration framework."""
    if PROGRESS_SHOW_EVENTS_KEY in old_raw:
        return
    v = old_raw.get(PROGRESS_VARIANT_KEY)
    if isinstance(v, bool) or not isinstance(v, int):
        return
    if v == PROGRESS_VARIANT_EFFICIENCY:
        old_raw[PROGRESS_VARIANT_KEY] = PROGRESS_VARIANT_MOVING_AVERAGE
    elif v == PROGRESS_VARIANT_MOVING_AVERAGE:
        old_raw[PROGRESS_VARIANT_KEY] = PROGRESS_VARIANT_EFFICIENCY


def _migrate_pre_v21_layout(old_raw):
    """Seed PRE-v21 Orientation/Alignment in place, so an upgrading user's bar stays exactly
    where it has always been (see the SETTINGS_VERSION 20->21 comment). A store already at v21+
    is left untouched.

    A LOOKUP, not arithmetic: there is no stored settingsVersion int to compare against directly,
    so "pre-v21" is inferred from the ABSENCE of a key introduced in that SAME bump
    (PROGRESS_ORIENTATION_KEY), same trick as _migrate_pre_v13_variant. Orientation always seeds
    Horizontal (the only axis that existed pre-v21). Alignment depends on the stored position:
    a pre-v21 non-zero (progress_bar_pos_x, progress_bar_pos_y) was an ABSOLUTE top-left, which is
    exactly what Alignment=Free means, so it seeds Free and the coordinates carry across verbatim
    (via the normal DEFAULTS overlay, untouched here); a zero pair seeds Damage Log, still 0/0 --
    the shipped placement. Nobody's bar moves.

    Fail-soft, and local to these two keys: a non-numeric / out-of-range stored position is
    treated as zero for this decision (clamp_pos re-clamps it properly when read elsewhere)."""
    if PROGRESS_ORIENTATION_KEY in old_raw:
        return
    old_raw[PROGRESS_ORIENTATION_KEY] = PROGRESS_ORIENT_HORIZONTAL
    x = clamp_pos(old_raw.get(BAR_POS_X_KEY, 0))
    y = clamp_pos(old_raw.get(BAR_POS_Y_KEY, 0))
    old_raw[PROGRESS_ALIGNMENT_KEY] = (PROGRESS_ALIGN_FREE if (x, y) != (0, 0)
                                       else PROGRESS_ALIGN_DAMAGE_LOG)


def _migrate_pre_v22_pos_frame(old_raw):
    """Seed PRE-v22 stores with the new BAR_POS frame marker in place (see the SETTINGS_VERSION
    21->22 comment / DECISION 2). A store already at v22+ is left untouched.

    A LOOKUP, not a conversion -- there is no stored settingsVersion int to compare against
    directly, so "pre-v22" is inferred from the ABSENCE of PROGRESS_POS_FRAME_KEY, same trick as
    _migrate_pre_v13_variant / _migrate_pre_v21_layout. ONLY a pre-v22 store that is ALREADY
    Alignment=Free with a non-(0, 0) pair has anything to convert -- its pair is a LITERAL
    top-left under the old semantics, so it is marked "legacy"; every other case (any other
    alignment, or a Free pair still at the (0, 0) "not yet materialised" marker) has no legacy
    pair at all, so it is marked "anchor" straight away. THE ACTUAL CONVERSION IS NOT DONE HERE --
    no surface size exists at migration time either (the same wall Free's own materialisation
    hits), so this only seeds the marker; bar_window.BarHost._materialise performs the real
    conversion the first time this bar next mounts with a real surface (option (a) of the
    decision).

    Fail-soft, and local to this one key: a non-numeric / out-of-range stored position is treated
    as zero for this decision (clamp_pos re-clamps it properly when read elsewhere), and the
    alignment falls back to Damage Log the same way clamp_variant would."""
    if PROGRESS_POS_FRAME_KEY in old_raw:
        return
    alignment = old_raw.get(PROGRESS_ALIGNMENT_KEY, PROGRESS_ALIGN_DAMAGE_LOG)
    if isinstance(alignment, bool) or not isinstance(alignment, int):
        alignment = PROGRESS_ALIGN_DAMAGE_LOG
    x = clamp_pos(old_raw.get(BAR_POS_X_KEY, 0))
    y = clamp_pos(old_raw.get(BAR_POS_Y_KEY, 0))
    if alignment == PROGRESS_ALIGN_FREE and (x, y) != (0, 0):
        old_raw[PROGRESS_POS_FRAME_KEY] = POS_FRAME_LEGACY
    else:
        old_raw[PROGRESS_POS_FRAME_KEY] = POS_FRAME_ANCHOR


def register():
    """Register (or re-load) the settings panel with MSA and seed the flag state.

    Soft + idempotent + self-healing: a no-op once registered; if MSA is absent it
    logs-and-returns with defaults intact; MSA may load after us at startup, so a first
    failed attempt is retried on the first hangar mount. Guarded so it never raises into the
    mount path."""
    global _registered
    if _registered:
        return
    g_modsSettingsApi = _primary_api()
    if g_modsSettingsApi is None:
        LOG_DEBUG("[moe] ModsSettingsAPI absent -> both widgets default enabled")
        return
    try:
        template = _template()
        saved = g_modsSettingsApi.getModSettings(LINKAGE, template)
        if saved:
            _seed(saved)
            g_modsSettingsApi.registerCallback(LINKAGE, _on_changed)
        else:
            # Fresh-install OR settingsVersion-bump path: getModSettings returned None. On a
            # bump Aslain's setModTemplate resets every stored value to the template defaults,
            # which would silently wipe the user's saved checkboxes. Migrate: capture the raw
            # stored dict from THIS api BEFORE setModTemplate runs -- getModSettings reports None
            # on the bump, but the old values are still readable at api.state['settings'][LINKAGE]
            # (reading state does not mutate/persist; only setModTemplate wipes). izeberg's state
            # layout differs; only Aslain is supported -- an unrecognized shape falls back cleanly
            # to a plain fresh install.
            old_raw = {}
            try:
                _state = getattr(g_modsSettingsApi, "state", None)
                if isinstance(_state, dict):
                    old_raw = dict((_state.get("settings") or {}).get(LINKAGE) or {})
            except Exception:
                old_raw = {}
            # Register the new template. On a bump this resets the stored dict to fresh v-current
            # defaults; _settings is DEFAULTS here, so _seed just re-affirms them.
            _seed(g_modsSettingsApi.setModTemplate(LINKAGE, template, _on_changed))
            # MIGRATE: a non-empty old_raw means this is an UPDATE (settingsVersion bump), not a
            # fresh install. Overlay the surviving user values onto the fresh defaults and
            # persist, so the transient reset never lands on disk (MSA debounces saveState to the
            # next tick, so the reset + this overlay coalesce into one write). _apply drops keys
            # removed from DEFAULTS and clamps the rest; keys NEW to this template keep their
            # fresh default (old_raw lacks them). Fail-soft: any error leaves the mod on fresh
            # defaults and registration still completes below.
            if old_raw:
                try:
                    _migrate_pre_v13_variant(old_raw)
                    _migrate_pre_v21_layout(old_raw)
                    _migrate_pre_v22_pos_frame(old_raw)
                    _apply(old_raw)
                    g_modsSettingsApi.updateModSettings(
                        LINKAGE, _full_settings_for_write(g_modsSettingsApi))
                    try:
                        g_modsSettingsApi.saveState()
                    except Exception:
                        LOG_CURRENT_EXCEPTION()
                    LOG_DEBUG("[moe] migrated saved settings across a settingsVersion bump")
                except Exception:
                    LOG_CURRENT_EXCEPTION()
        # Wire the panel's "reset to defaults" button on whichever api(s) store our settings
        # (Aslain keeps a SEPARATE api object from izeberg's; subscribe on both, de-duped).
        for api in _candidate_apis():
            _subscribe_reset(api)
        # Refresh the stored template text to the client's active language (required for an
        # existing install whose stored template is a stale language). No-op on a fresh one.
        for api in _candidate_apis():
            _sync_template_text(api)
        _registered = True
        LOG_DEBUG("[moe] settings registered -> %r" % (_settings,))
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _derive_layout(pre, post):
    """(orientation, alignment, (x, y)) the layout settles at, from a (pre, post) diff of the
    three stored layout values. Pure, engine-free, TOTAL -- one call, no recursion, no reads of
    module state (`pre`/`post` carry everything it needs). See
    TASKS/in-battle-bar-layout-auto-set-redesign.md for the full transition table (rows 1-13)
    this implements; the summary:

      * a position change (stepper edit or Ctrl+drag) wins outright -> Alignment := Free,
        Orientation untouched (rows 6-7; precedence 1);
      * else an alignment change to Damage Log / Minimap forces the matching Orientation and
        zeroes the position, because the two orientations have different surface geometries and
        carrying one's absolute pair across lands the bar somewhere it was never tuned for (rows
        3-4; precedence 2 -- alignment beats orientation, DECISION 4);
      * else an alignment change to Free leaves Orientation and the position untouched -- the
        real coordinates are only computable once a bar surface exists, so materialising them is
        a separate, later concern (row 5; the `(0, 0)` case is exactly Free's own
        "not yet materialised" marker, see bar_window._resolve);
      * else an orientation change forces the matching Alignment and zeroes the position -- FIRES
        EVEN FROM FREE, "Free is sticky" is SUPERSEDED (rows 1-2);
      * else (no relevant diff -- a foreign key, an unrelated flag, Size/Variant, or the echo of
        our own write-back) settles on `post` unchanged (rows 8-11, 13).

    Every settled output is a FIXED POINT: _derive_layout(s, s) == s for each of the four resting
    states (H, DL), (V, MM), (H, FREE) and (V, FREE) -- that termination proof is why `_on_changed`
    below needs no recursion and only ever writes back once per user action."""
    pre_o, pre_a, pre_p = pre
    post_o, post_a, post_p = post
    orientation_changed = post_o != pre_o
    alignment_changed = post_a != pre_a
    position_changed = post_p != pre_p

    if position_changed:
        return post_o, PROGRESS_ALIGN_FREE, post_p

    if alignment_changed:
        if post_a == PROGRESS_ALIGN_DAMAGE_LOG:
            return PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_DAMAGE_LOG, (0, 0)
        if post_a == PROGRESS_ALIGN_MINIMAP:
            return PROGRESS_ORIENT_VERTICAL, PROGRESS_ALIGN_MINIMAP, (0, 0)
        return post_o, PROGRESS_ALIGN_FREE, post_p   # -> Free: orientation/position untouched

    if orientation_changed:
        if post_o == PROGRESS_ORIENT_HORIZONTAL:
            return PROGRESS_ORIENT_HORIZONTAL, PROGRESS_ALIGN_DAMAGE_LOG, (0, 0)
        return PROGRESS_ORIENT_VERTICAL, PROGRESS_ALIGN_MINIMAP, (0, 0)

    return post_o, post_a, post_p


def _on_changed(linkage, new_settings):
    """MSA onSettingsChanged callback: overlay our keys, settle Orientation/Alignment/Position
    via _derive_layout, and fan out to the feature bridges so a checkbox change applies live.

    Linkage-scoped: MSA broadcasts this callback GLOBALLY (it fires for every mod's change, not
    just ours), so ignore events for other mods -- mirrors _on_reset. Even without the guard the
    _apply overlay would no-op a foreign payload, but skipping early also avoids a spurious
    _notify()/re-push and any chance of a foreign key colliding with one of ours.

    THE DERIVATION: snapshot the three stored layout values BEFORE the overlay (the only way to
    tell "the user flipped Orientation" apart from "the user typed a coordinate", since MSA hands
    us the FULL settings snapshot every time, never a diff), overlay, then hand (pre, post) to
    _derive_layout ONCE. Whatever differs from `post` gets written into the live cache and the
    pass is marked dirty; nothing derived is ever re-fed back into _derive_layout in the same
    pass -- see _derive_layout's docstring for why that single call always reaches a fixed point.

    RE-ENTRANCY LATCH (_deriving): guards the belt-and-braces case where MSA's write-back
    (below) triggers a SYNCHRONOUS re-entrant onSettingsChanged carrying a stale (pre-derivation)
    snapshot. While `_deriving` is set, skip derivation entirely -- still _apply + _notify, so the
    fan-out isn't lost -- rather than deriving against stale data and undoing the settle in
    progress.

    LOOP GUARD (the normal, non-re-entrant case): the write-back below fires another
    onSettingsChanged of its own. No extra flag is needed for THAT pass -- the echo carries
    exactly what we just wrote, `_derive_layout` on a fixed point returns its input unchanged, so
    the echoed pass finds nothing dirty and no-ops."""
    global _deriving
    try:
        if linkage != LINKAGE:
            return
        if _deriving:
            _apply(new_settings)
            LOG_DEBUG("[moe] settings changed (re-entrant, no derivation) -> %r" % (_settings,))
            _notify()
            return
        pre = (_settings.get(PROGRESS_ORIENTATION_KEY, PROGRESS_ORIENT_HORIZONTAL),
               _settings.get(PROGRESS_ALIGNMENT_KEY, PROGRESS_ALIGN_DAMAGE_LOG),
               (_settings.get(BAR_POS_X_KEY, 0), _settings.get(BAR_POS_Y_KEY, 0)))
        _apply(new_settings)
        post = (_settings.get(PROGRESS_ORIENTATION_KEY, PROGRESS_ORIENT_HORIZONTAL),
                _settings.get(PROGRESS_ALIGNMENT_KEY, PROGRESS_ALIGN_DAMAGE_LOG),
                (_settings.get(BAR_POS_X_KEY, 0), _settings.get(BAR_POS_Y_KEY, 0)))
        settled_o, settled_a, settled_p = _derive_layout(pre, post)
        dirty = False
        if settled_o != post[0]:
            _settings[PROGRESS_ORIENTATION_KEY] = settled_o
            dirty = True
        if settled_a != post[1]:
            _settings[PROGRESS_ALIGNMENT_KEY] = settled_a
            dirty = True
        if settled_p != post[2]:
            _settings[BAR_POS_X_KEY], _settings[BAR_POS_Y_KEY] = settled_p
            dirty = True
        if dirty:
            g = _primary_api()
            if g is not None:
                _deriving = True
                try:
                    g.updateModSettings(LINKAGE, _full_settings_for_write(g))
                    try:
                        g.saveState()
                    except Exception:
                        LOG_CURRENT_EXCEPTION()
                except Exception:
                    LOG_CURRENT_EXCEPTION()
                finally:
                    _deriving = False
        LOG_DEBUG("[moe] settings changed -> %r" % (_settings,))
        _notify()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_reset(linkage, defaults):
    """Panel 'reset to defaults' button. The host fires onResetMod (NOT onSettingsChanged),
    globally across every mod, so this is linkage-scoped. Restore our defaults, then force BOTH
    positions back to AUTO (the garage widget's 0/0/0/0 and the in-battle bar's 0/0), Orientation
    back to Horizontal and Alignment back to Damage Log (so a reset panel is internally
    consistent -- 0/0 IS the Damage Log anchor), and Follow Carousel Mode back ON, regardless of
    any seeded value the host snapshot may still carry, and fan out."""
    try:
        if linkage != LINKAGE:
            return
        _seed(defaults if defaults else DEFAULTS)
        _settings[POS_X_KEY] = 0
        _settings[POS_Y_KEY] = 0
        _settings[POS_W_KEY] = 0
        _settings[POS_H_KEY] = 0
        _settings[BAR_POS_X_KEY] = 0
        _settings[BAR_POS_Y_KEY] = 0
        _settings[PROGRESS_POS_FRAME_KEY] = POS_FRAME_ANCHOR
        _settings[PROGRESS_ORIENTATION_KEY] = PROGRESS_ORIENT_HORIZONTAL
        _settings[PROGRESS_ALIGNMENT_KEY] = PROGRESS_ALIGN_DAMAGE_LOG
        _settings[FOLLOW_CAROUSEL_KEY] = True
        LOG_DEBUG("[moe] settings reset -> %r" % (_settings,))
        _notify()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _full_settings_for_write(api):
    """Build the COMPLETE settings dict to hand to updateModSettings.

    updateModSettings *replaces* the whole stored per-linkage dict (MSA replace-not-merge), so a
    partial dict silently drops keys the settings host owns -- notably Aslain's per-mod 'enabled'
    toggle, whose renderer indexes settings['enabled'] (a missing key blanks the ENTIRE panel).
    So start from the currently-stored settings (preserving 'enabled' + any host keys), guarantee
    'enabled' exists, then overlay our own varNames."""
    data = {}
    try:
        current = api.getModSettings(LINKAGE, _template())
        if current:
            data = dict(current)
    except Exception:
        LOG_CURRENT_EXCEPTION()
    data.setdefault("enabled", True)   # host-managed per-mod toggle; never drop it
    data.update(_settings)             # our varNames -- every DEFAULTS key, e.g. flags +
                                        # posX/posY/posW/posH + followCarousel + the bar-pos pair
                                        # and its frame marker
    return data


def set_position(x, y, w=0, h=0):
    """Persist a new widget position (px) and re-push it to the widget. Called from the JS
    `setPosition` reverse command -- a Ctrl+drag / stepper edit / rescale echo that pins the
    top-left px. (An auto default -- posX/posY == 0 -- is never sent from the widget; it keeps
    the resolution-relative CSS default, so px only ever arrive from a real pin.)

    `w`/`h` are the Gameface viewport size the px were captured at; we store them (posW/posH) so
    the widget can rescale the pinned position proportionally after a resolution / UI-scale change
    (see applyPosition in MoECalculator.js).

    Writes the FULL settings through MSA so the panel's numeric fields track the position; guarded
    so a missing / broken MSA never breaks the widget. updateModSettings only mutates in-memory
    state, so saveState() flushes it to disk. Then fans out (re-push) so the echoed position
    reaches the widget immediately, even without MSA."""
    _settings[POS_X_KEY] = clamp_pos(x)
    _settings[POS_Y_KEY] = clamp_pos(y)
    _settings[POS_W_KEY] = clamp_pos(w)
    _settings[POS_H_KEY] = clamp_pos(h)
    g = _primary_api()
    if g is not None:
        try:
            g.updateModSettings(LINKAGE, _full_settings_for_write(g))
            try:
                g.saveState()
            except Exception:
                LOG_CURRENT_EXCEPTION()
        except Exception:
            LOG_CURRENT_EXCEPTION()
    # else MSA absent -> position still applies this session, just not persisted.
    _notify()


def set_bar_position(x, y, persist=True):
    """Store the in-battle bar's Free ANCHOR POINT (LOGICAL GUI px; 0/0 == "not yet
    materialised", see bar_window's AUTO branch) -- domain.positioning.free_top_left, NOT a
    top-left. Called from the bars' Ctrl+drag gesture (bar_window.BarHost.drag, which converts
    its own top-left grab into this frame before calling here) and from BarHost._materialise (the
    deferred conversion for a freshly-picked Free or a pre-v22 legacy pin).

    `persist` FALSE is the live drag: the in-memory value is all a re-place reads, so every mouse
    movement updates that and nothing else. TRUE (the gesture end, or a materialisation) additionally
    writes it through MSA so the panel's steppers track it and the position survives the session.

    ALSO sets Alignment to Free and the frame marker to POS_FRAME_ANCHOR -- every caller hands
    this an ANCHOR POINT (never a legacy top-left), so the frame marker is unconditionally
    "anchor" the instant this runs; this is also what flips a pre-v22 "legacy" store the first
    time _materialise converts it. Setting Alignment here (rather than inferring it in
    _on_changed from the position change alone) is what lets _on_changed's pre/post comparison
    recognise "this echo is our own write" for free -- by the time MSA echoes this write back, the
    live cache already holds these exact values, so that handler sees no change and no-ops (see
    its LOOP GUARD note).

    NO _notify(), unlike set_position: the bar's own host re-places the window directly in the same
    handler, so a fan-out would only cost every OTHER feature a needless apply_settings + re-push
    -- at pointer rate during a drag. Guarded so a missing / broken MSA never breaks the gesture."""
    _settings[BAR_POS_X_KEY] = clamp_pos(x)
    _settings[BAR_POS_Y_KEY] = clamp_pos(y)
    _settings[PROGRESS_ALIGNMENT_KEY] = PROGRESS_ALIGN_FREE
    _settings[PROGRESS_POS_FRAME_KEY] = POS_FRAME_ANCHOR
    if not persist:
        return
    g = _primary_api()
    if g is None:
        return   # MSA absent -> the position still applies this session, just not persisted.
    try:
        g.updateModSettings(LINKAGE, _full_settings_for_write(g))
        try:
            g.saveState()
        except Exception:
            LOG_CURRENT_EXCEPTION()
    except Exception:
        LOG_CURRENT_EXCEPTION()
