# -*- coding: utf-8 -*-
"""The user settings, laid out as two columns of NAMED CATEGORIES in the MSA panel. A category is
a BOLD label header row followed by that feature's controls, with an "Empty" spacer row between
categories (MSA renders only two columns here, so a category cannot be a column of its own -- see
_template()). Column 1 holds "Battle Calculator" (the In-Battle Widget master, labelled "Enabled",
grouped with its "Alt Press" + "Counted Assistance Row" children) then "Battle Progress" (the
Progress Bar master, also "Enabled", with its three VISIBILITY children "Events" / "Alt Press" /
"Always", then the standalone inline "Mode" and "Scale" radios, then the "Transitions" master with
its "Events" + "Alt Press" children). Column 2 holds "Garage Widget" -- the garage master plus the
"Layout" group (also BOLD): Follow Carousel, then a non-bold "Position" sub-label heading the X/Y
steppers.

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
# progress_bar_variant key takes its fresh 0 (= Moving Average) default, so an existing user
# lands exactly on the bar they already had.
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
SETTINGS_VERSION = 16

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

# The Progress Bar's ENTER/EXIT TRANSITIONS (its fade + slide), as a THIRD grouped master in the
# "Battle Progress" category with one child per trigger AREA. Plain bools, all defaulting True --
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
# Follow Carousel Mode (default ON): keep nudging a pinned widget vertically as the carousel
# state changes (1<->2 rows, small<->tall), so a dragged widget never overlaps the carousel.
# The nudge is live-measured JS-side -- no extra persisted coordinate.
FOLLOW_CAROUSEL_KEY = "followCarousel"

# Sanity ceiling for a stored pixel coordinate (well past any real screen size); a
# typed / echoed value is clamped into [0, POS_MAX], with 0 meaning "auto / unseeded".
POS_MAX = 20000

_POS_KEYS = (POS_X_KEY, POS_Y_KEY, POS_W_KEY, POS_H_KEY)

# The two widgets and the counted-assistance row ship ON; the Alt-peek mode and the progress bar
# ship OFF (opt-in), with the progress-bar VARIANT on Damage Efficiency (0, the v13 order) and both
# of its VISIBILITY triggers on but "Always" off, and all three TRANSITION switches ON (the animated
# bar is what shipped). The drag position ships at auto (0/0/0/0) and Follow Carousel ships ON.
# merge_settings only ever overlays these known keys, so an MSA store from a newer/older template
# can never introduce or drop a flag we act on.
DEFAULTS = {GARAGE_KEY: True, BATTLE_KEY: True, BATTLE_ALT_KEY: False,
            COUNTED_ASSIST_KEY: True, PROGRESS_BAR_KEY: False,
            PROGRESS_VARIANT_KEY: PROGRESS_VARIANT_EFFICIENCY,
            PROGRESS_SIZE_KEY: PROGRESS_SIZE_DEFAULT,
            PROGRESS_SHOW_EVENTS_KEY: True, PROGRESS_SHOW_ALT_KEY: True,
            PROGRESS_SHOW_ALWAYS_KEY: False,
            PROGRESS_TRANSITIONS_KEY: True, PROGRESS_TRANS_EVENTS_KEY: True,
            PROGRESS_TRANS_MANUAL_KEY: True,
            POS_X_KEY: 0, POS_Y_KEY: 0, POS_W_KEY: 0, POS_H_KEY: 0,
            FOLLOW_CAROUSEL_KEY: True}


def clamp_pos(v):
    """Coerce a position coordinate to an int in [0, POS_MAX]. 0 = auto/unseeded.
    Pure + engine-free (unit-tested); non-numeric / negative -> 0."""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return 0
    if v < 0:
        return 0
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

# Live flag state (seeded from MSA in register(); defaults until then / if MSA is absent).
_settings = dict(DEFAULTS)

# apply_settings callbacks the entry point subscribes (one per feature bridge).
_listeners = []

# True once we've registered with MSA. Kept so register() is idempotent AND self-healing:
# a failed attempt (MSA not loaded yet at our import time -- our id sorts before izeberg's)
# leaves this False, so a later register() (first hangar mount) retries until it sticks.
_registered = False


def _coerce(key, value):
    """Coerce a saved value to the type this key stores: the position coords are clamped ints,
    the progress-bar variant and size are clamped radio INDEXes, everything else is a bool.
    Pure + engine-free.

    The two radio branches are load-bearing: falling through to bool() would turn a radio's
    index 1 into True and index 0 into False, which then round-trips back to MSA as a bool
    and destroys the setting."""
    if key in _POS_KEYS:
        return clamp_pos(value)
    if key == PROGRESS_VARIANT_KEY:
        return clamp_variant(value)
    if key == PROGRESS_SIZE_KEY:
        return clamp_variant(value, PROGRESS_SIZE_LARGE)
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
    [0, POS_MAX] with manual entry allowed. Shows 0 (auto) until a drag / edit pins a value.

    The tooltip is OMITTED rather than hard-indexed when the rendered row has none, matching
    _checkbox / _radio / _label. Both steppers do carry one today, so this never fires -- it is
    here because the hard index is what killed the WHOLE settings panel once (a KeyError inside
    _template(), i.e. inside register()'s guarded try, so the only symptom was no panel at all)."""
    control = {
        "type": "NumericStepper",
        "text": rendered["text"],
        "value": DEFAULTS[key],
        "minimum": 0,
        "maximum": POS_MAX,
        "snapInterval": 1,
        "canManualInput": True,
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

    `rendered["text"]` arrives ALREADY wrapped in <b>...</b> for the four HEADER_KEYS --
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
    "Transitions" masters -- and splices the flat lists together (see _template()).

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
    VISIBILITY children, an Empty spacer, the standalone Mode and Scale radios, a SECOND Empty
    spacer, then the Transitions master + its Events and Alt Press children). Column 2: "Garage
    Widget" (the garage master), then the "Layout" group -- a header, Follow Carousel, an Empty
    spacer, a "Position" sub-label, then the X/Y numeric steppers. Because the header names the
    feature, each master's
    own label is just "Enabled".
    Every visible label/tooltip comes from settings_i18n at the client's language (English
    fallback). The four category/group headers render BOLD (see _label); "Position" does not."""
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
    trans_master = _checkbox(PROGRESS_TRANSITIONS_KEY, t["progressTransitions"])
    trans_events = _checkbox(PROGRESS_TRANS_EVENTS_KEY, t["progressTransEvents"])
    trans_manual = _checkbox(PROGRESS_TRANS_MANUAL_KEY, t["progressTransManual"])
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
        # column1: TWO categories separated by an Empty spacer, each a bare Label header followed
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
        # the Progress Bar one is its own group: its two children must grey out with IT and with
        # nothing else. Same "Battle Progress" category, so it gets NO header row of its own --
        # only an Empty spacer ahead of it, breathing room after the two radios (same purely
        # visual role as the spacer ahead of "Battle Progress" itself).
        #
        # Both category headers render BOLD -- settings_i18n.build() already wrapped their text
        # (see _label); this only adds the matching useHTML key.
        "column1": ([_label("catBattleCalc", t["catBattleCalc"])]
                    + _grouped_column1(battle_master, [battle_alt, counted])
                    + [_empty(), _label("catBattleProgress", t["catBattleProgress"])]
                    + progress_group
                    + [_empty(), progress_variant, progress_size, _empty()]
                    + _grouped_column1(trans_master, [trans_events, trans_manual])),
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


def _on_changed(linkage, new_settings):
    """MSA onSettingsChanged callback: overlay our keys and fan out to the feature bridges so a
    checkbox change applies live.

    Linkage-scoped: MSA broadcasts this callback GLOBALLY (it fires for every mod's change, not
    just ours), so ignore events for other mods -- mirrors _on_reset. Even without the guard the
    _apply overlay would no-op a foreign payload, but skipping early also avoids a spurious
    _notify()/re-push and any chance of a foreign key colliding with one of ours."""
    try:
        if linkage != LINKAGE:
            return
        _apply(new_settings)
        LOG_DEBUG("[moe] settings changed -> %r" % (_settings,))
        _notify()
    except Exception:
        LOG_CURRENT_EXCEPTION()


def _on_reset(linkage, defaults):
    """Panel 'reset to defaults' button. The host fires onResetMod (NOT onSettingsChanged),
    globally across every mod, so this is linkage-scoped. Restore our defaults, then force the
    position back to AUTO (0/0/0/0) and Follow Carousel Mode back ON regardless of any seeded
    value the host snapshot may still carry, and fan out."""
    try:
        if linkage != LINKAGE:
            return
        _seed(defaults if defaults else DEFAULTS)
        _settings[POS_X_KEY] = 0
        _settings[POS_Y_KEY] = 0
        _settings[POS_W_KEY] = 0
        _settings[POS_H_KEY] = 0
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
    data.update(_settings)             # our varNames (flags + posX/posY/posW/posH + followCarousel)
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
