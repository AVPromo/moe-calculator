# -*- coding: utf-8 -*-
"""The user settings, laid out as two columns of NAMED CATEGORIES in the MSA panel. A category is
a bare label header row followed by that feature's controls (MSA renders only two columns here, so
a category cannot be a column of its own -- see _template()). Column 1 holds "Battle Calculator"
(the In-Battle Widget master, labelled "Show", grouped with its "Show on Alt Key" + "Counted
Assistance" children) then "Battle Progress" (the Progress Bar master, also "Show", with its
label-less variant radio and its "Size" radio as children, followed by the "Transitions" master
with its "Events" + "Manual" children). Column 2 holds "Garage Widget" -- the garage master plus
the standalone drag-position group.

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
# this forward bump; the migration branch carries every saved value across it and progress_bar_size
# takes its fresh 0 (= Default) default.
# Bumped 11 -> 12 for the "Transitions" group: a THIRD grouped master in the "Battle Progress"
# category (progress_transitions_enabled) with two children (progress_transitions_events,
# progress_transitions_manual) -- three new varNames and three new rows at the end of column 1, all
# structural. As always register()'s saved-truthy path never calls setModTemplate, so only a forward
# bump reaches an existing install; the migration branch carries every saved value across and the
# three new keys take their fresh True (= animated, what shipped) defaults.
SETTINGS_VERSION = 12

GARAGE_KEY = "garage_widget_enabled"
BATTLE_KEY = "battle_widget_enabled"
# The in-battle overlay's Alt-key mode, a CHILD of BATTLE_KEY (grouped under it via
# createControlsGroup): show the overlay only while Alt is held; when off the overlay is shown
# at all times. It has effect ONLY while BATTLE_KEY is on -- with the master off the overlay is
# never shown, so the child is inert (and MSA greys it out under the group). See
# battle_bar_visible: active == battle_enabled and (alt_held if alt_mode else True).
BATTLE_ALT_KEY = "battle_widget_alt_key"
# Optional third in-battle row: "counted assistance" = the higher of tracking / spotting / stun
# assist this battle (the assist that MoE credits). Opt-in (default OFF).
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

# Which bar the Progress Bar master draws -- a CHILD of PROGRESS_BAR_KEY (grouped under it), and
# the one setting of ours that is NOT a bool: MSA's RadioButtonGroup stores its value as a
# 0-BASED OPTION INDEX (see templates.createRadioButtonGroup, ":type value: int"). _coerce has a
# dedicated branch for it, because the default bool() branch would turn index 1 into True.
# Defaults to Moving Average so every existing user keeps exactly the bar they already had.
PROGRESS_VARIANT_KEY = "progress_bar_variant"
PROGRESS_VARIANT_MOVING_AVERAGE = 0   # the original next-mark moving-average bar
PROGRESS_VARIANT_EFFICIENCY = 1       # the damage-vs-requirements "Damage Efficiency" bar
# ... and the highest legal index: a stored value outside [0, EFFICIENCY] is corrupt (clamp_variant).

# How large the Progress Bar draws -- the SECOND child radio of PROGRESS_BAR_KEY and the mod's
# second non-bool setting, so _coerce needs its own branch here too (falling through to bool()
# would turn index 1 into True and destroy the setting, exactly as for the variant).
PROGRESS_SIZE_KEY = "progress_bar_size"
PROGRESS_SIZE_DEFAULT = 0             # the shipped size -- every existing user keeps it
PROGRESS_SIZE_LARGE = 1               # ... and the highest legal index (see clamp_variant)

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

# The two widgets ship ON; the Alt-peek mode, the counted-assistance row and the progress bar
# ship OFF (opt-in), with the progress-bar VARIANT on Moving Average (0) so a user who enables
# the bar gets the behaviour it always had, and all three TRANSITION switches ON (the animated bar
# is what shipped). The drag position ships at auto (0/0/0/0) and Follow Carousel Mode ships ON.
# merge_settings only ever overlays these known keys, so an MSA store from a newer/older template
# can never introduce or drop a flag we act on.
DEFAULTS = {GARAGE_KEY: True, BATTLE_KEY: True, BATTLE_ALT_KEY: False,
            COUNTED_ASSIST_KEY: False, PROGRESS_BAR_KEY: False,
            PROGRESS_VARIANT_KEY: PROGRESS_VARIANT_MOVING_AVERAGE,
            PROGRESS_SIZE_KEY: PROGRESS_SIZE_DEFAULT,
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


def clamp_variant(v, max_index=PROGRESS_VARIANT_EFFICIENCY):
    """Coerce a stored RadioButtonGroup value to a legal 0-based option index in
    [0, max_index]. Pure + engine-free (unit-tested).

    Shared by BOTH radios -- `max_index` defaults to the variant radio's ceiling, and the size
    radio passes PROGRESS_SIZE_LARGE. These are the mod's only non-bool settings, so this is
    also the one trust boundary where a hostile store could leak the wrong TYPE into the bridge:
    a bool is never a legal index (bool is an int subclass, so a plain int() would silently pass
    True through as 1), and neither is a non-numeric, negative or out-of-range value. All of them
    fall back to 0 -- the safe choice for either radio, since index 0 is in both cases the
    behaviour the bar always had (Moving Average / the shipped size)."""
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
    """Whether the optional in-battle "counted assistance" row is enabled (default False)."""
    return bool(_settings.get(COUNTED_ASSIST_KEY, False))


def progress_bar_enabled():
    """Whether the transient centre-screen next-mark progress bar is enabled (default False).

    Independent of battle_enabled(): the progress bar is its own feature, not part of the
    In-Battle Widget overlay."""
    return bool(_settings.get(PROGRESS_BAR_KEY, False))


def progress_bar_variant():
    """Which progress bar the master draws, as the radio's 0-based option INDEX:
    PROGRESS_VARIANT_MOVING_AVERAGE (0, the default) or PROGRESS_VARIANT_EFFICIENCY (1).

    An int, NOT a bool -- callers pick a window off it, so re-clamp on read (like the
    position getters) and never let a corrupt store leak a bool or an out-of-range index.
    Meaningless while progress_bar_enabled() is off: the master gates the whole feature."""
    return clamp_variant(_settings.get(PROGRESS_VARIANT_KEY,
                                       PROGRESS_VARIANT_MOVING_AVERAGE))


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
    [0, POS_MAX] with manual entry allowed. Shows 0 (auto) until a drag / edit pins a value."""
    return {
        "type": "NumericStepper",
        "text": rendered["text"],
        "value": DEFAULTS[key],
        "minimum": 0,
        "maximum": POS_MAX,
        "snapInterval": 1,
        "canManualInput": True,
        "tooltip": rendered["tooltip"],
        "varName": key,
    }


def _radio(key, rendered):
    """One MSA RadioButtonGroup descriptor for a mutually-exclusive choice. `varName` matches a
    DEFAULTS key and `value` is the 0-BASED OPTION INDEX (never a label); `options` is the
    localized label tuple settings_i18n attached to the rendered entry, in index order.

    Built as a plain dict rather than through Aslain's templates.createRadioButtonGroup -- the
    same shape that helper emits (type/text/varName/value/tooltip/options) -- for two reasons:
    it keeps _template() a pure, unit-testable dict with no gui.aslainMenu import, and it means
    the helper's `inline` kwarg (one horizontal row) is never passed at all, so the TypeError it
    raises on MSA < 1.6.1 is structurally impossible. The options stay in MSA's default vertical
    stack, which every build renders. An API that does not know RadioButtonGroup at all (the
    izeberg fallback) simply skips the control -- the PROGRESS_BAR_KEY master beside it is a
    plain CheckBox and keeps working, and progress_bar_variant() then reports its 0 default.

    `text` is EMPTY by design (settings_i18n renders the variant row blank in every language) so
    the panel draws no header row above the options and they read as direct children of the
    Progress Bar checkbox. `tooltip` is therefore OMITTED, not empty: createBase adds the key only
    when the tooltip is not None, so a control with nothing to explain simply has no key -- and a
    label-less row has nothing to hover anyway (the variant prose moved onto the master's
    tooltip). Emitting "" would hand the panel an empty tooltip to render."""
    control = {
        "type": "RadioButtonGroup",
        "text": rendered["text"],
        "value": DEFAULTS[key],
        "varName": key,
        "options": [{"label": label} for label in rendered["options"]],
    }
    tooltip = rendered.get("tooltip")
    if tooltip:
        control["tooltip"] = tooltip
    return control


def _label(rendered):
    """A plain MSA Label header (no varName -- not a stored value). Carries text, and a tooltip
    only when there IS one, so _sync_template_text can refresh it in lockstep with the column's
    other controls.

    The tooltip key is OMITTED rather than emitted empty (same shape as _radio): the three
    CATEGORY headers are text-only, and handing the panel an empty tooltip to render is not the
    same as having none. _sync_template_text already tolerates it -- its `tip is not None` guard
    skips a rendered entry with no tooltip, so it never writes a key back onto a tipless row."""
    control = {"type": "Label", "text": rendered["text"]}
    tooltip = rendered.get("tooltip")
    if tooltip:
        control["tooltip"] = tooltip
    return control


def _grouped_column1(master, children):
    """ONE column-1 master with its indented children, greyed out while the master is off.
    Column 1 calls this TWICE -- once for the "In-Battle Widget" master and once for the
    "Progress Bar" master -- and splices the two flat lists together (see _template()). The
    Progress Bar's single child is the label-less variant radio, so this grouping is the ONLY
    thing that visually files its two options under the master.

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
    by that feature's controls. Column 1: "Battle Calculator" (the In-Battle Widget master + its
    "Show on Alt Key" and "Counted Assistance" children), then "Battle Progress" (the Progress Bar
    master + its label-less variant radio and its Size radio, then the Transitions master + its
    Events and Manual children). Column 2: "Garage Widget" (the
    garage master), then the drag-position group -- a positioning Label header, the X/Y numeric
    steppers, and the Follow Carousel Mode checkbox. Because the header names the feature, each
    master's own label is just "Show". Every visible label/tooltip comes from settings_i18n at the
    client's language (English fallback)."""
    t = settings_i18n.panel_text()
    battle_master = _checkbox(BATTLE_KEY, t["battleWidget"])
    battle_alt = _checkbox(BATTLE_ALT_KEY, t["battleAltKey"])
    counted = _checkbox(COUNTED_ASSIST_KEY, t["countedAssist"])
    progress_master = _checkbox(PROGRESS_BAR_KEY, t["progressBar"])
    progress_variant = _radio(PROGRESS_VARIANT_KEY, t[settings_i18n.VARIANT_KEY])
    progress_size = _radio(PROGRESS_SIZE_KEY, t["progressSize"])
    trans_master = _checkbox(PROGRESS_TRANSITIONS_KEY, t["progressTransitions"])
    trans_events = _checkbox(PROGRESS_TRANS_EVENTS_KEY, t["progressTransEvents"])
    trans_manual = _checkbox(PROGRESS_TRANS_MANUAL_KEY, t["progressTransManual"])
    garage = _checkbox(GARAGE_KEY, t["garageWidget"])
    return {
        "modDisplayName": MOD_DISPLAY_NAME,
        "enabled": True,
        "settingsVersion": SETTINGS_VERSION,
        # column1: TWO categories, each a bare Label header followed by that feature's group --
        # the In-Battle master with its two children, then the Progress Bar master with its
        # variant + size radios. The header rows carry no varName and no tooltip.
        #
        # The Progress Bar controls are deliberately NOT passed as children of the In-Battle
        # group: a grouped child inherits THAT master's varName, so MSA would grey the progress
        # bar out whenever the unrelated In-Battle Widget is off. That hazard is exactly why the
        # Progress Log checkbox used to sit outside the group with no masterVarName at all, and
        # it still holds for BATTLE_KEY. Giving the progress bar its OWN master (a second
        # _grouped_column1 call) is a deliberate re-parent that keeps the property: the radio
        # greys out with PROGRESS_BAR_KEY and with nothing else, and PROGRESS_BAR_KEY itself
        # stays a group MASTER, so it never carries a masterVarName either.
        #
        # Wire order MUST stay in lockstep with settings_i18n.COL1_KEYS (see
        # _sync_template_text) -- its zip is positional, so a reorder retitles the wrong control.
        #
        # The Transitions master is a THIRD _grouped_column1 call spliced on, for the same reason
        # the Progress Bar one is its own group: its two children must grey out with IT and with
        # nothing else. Same "Battle Progress" category, so it gets NO header row of its own.
        "column1": ([_label(t["catBattleCalc"])]
                    + _grouped_column1(battle_master, [battle_alt, counted])
                    + [_label(t["catBattleProgress"])]
                    + _grouped_column1(progress_master, [progress_variant, progress_size])
                    + _grouped_column1(trans_master, [trans_events, trans_manual])),
        # column2: the category header, the garage master, then the drag-position group. The
        # steppers stay STANDALONE (no masterVarName), so they keep working -- and stay ungreyed --
        # while the garage widget is off. They show 0 (auto) until a drag / edit pins a px; Follow
        # Carousel Mode ships ON. The wire order here MUST stay in lockstep with
        # settings_i18n.COL2_KEYS (see _sync_template_text).
        "column2": [
            _label(t["catGarage"]),
            garage,
            _label(t["positioning"]),
            _stepper(POS_X_KEY, t["posX"]),
            _stepper(POS_Y_KEY, t["posY"]),
            _checkbox(FOLLOW_CAROUSEL_KEY, t["followCarousel"]),
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
