---
name: moe-settings
description: Use when editing the 14th_ua MoE Calculator's SETTINGS subsystem — the ModsSettingsAPI (MSA) panel, its three category headers, Empty spacers, the three column-1 grouped masters (In-Battle Widget, Progress Bar + its three visibility children, Transitions) and the two standalone inline int-valued radios, the column-2 garage widget + layout group, the flag getters the feature bridges read (including the master-folded transition getters and the "Always"-folded visibility getters), MSA registration / soft-dep / self-heal, MSA 1.6.4's real conditional gating and its zero descriptor validation, when a change owes a SETTINGS_VERSION bump, or why a foreign mod's settings change must not touch our flags. For the reusable MSA panel MECHANICS (probe, register/migrate lifecycle, descriptor shapes, guards, bump rules) see the harness skill wotmod-msa-settings; for the panel prose translation see wotmod-i18n-settings; for feature internals see moe-garage / moe-battle.
---

# MoE Calculator — settings panel (feature)

The mod's user toggles, surfaced as ModsSettingsAPI (MSA) controls in the in-game mod-settings
menu. Shared mechanics live in the harness: **the api probe, the register/migrate lifecycle,
descriptor shapes + gating keys, the replace-not-merge rule and `saveState`, the linkage /
`enabled` guards, and the `settingsVersion` bump rules** → `wotmod-msa-settings`;
**panel-prose localization, `_sync_template_text`, `getClientLanguage` + the `uk`-not-`ua`
quirk** → `wotmod-i18n-settings`.
This skill is only the mod's concretes. All paths under `src/res/scripts/client/moe_calculator/`.

Owner module: `bridge/mod_settings.py` (flag state + MSA registration). Prose: `adapter/settings_i18n.py`.

## The controls (two-column panel, three categories, three grouped masters + two standalone radios in column 1)

`SETTINGS_VERSION = 14`. Each `varName` == the `DEFAULTS` key, so the dict MSA returns maps
straight through `merge_settings`. Bump `SETTINGS_VERSION` **only** when the control layout /
varName set changes (the host wipes saved values back to defaults on a bump, and `register()`'s
migration branch carries the user's values across) — localizing plain label/tooltip text is
text-only and does NOT bump it. The full bump history is the comment block above the constant;
read it there rather than restating it. **The bump is always FORWARD, even to revert a layout** —
the host acts only on `new > stored`.

⚠️ Don't be misled by `wotmod-msa-settings`' (correct) general rule that a pure layout move is
NOT structural to MSA's `_settingsStructure`. That is about MSA; **this repo's `register()` takes
the saved-truthy path on an existing install and never calls `setModTemplate` at all**, so a
forward bump is the only thing that can re-lay-out a store we've already written — structural or
not. Same for *deleting* a text key, which `_sync_template_text` can never do.

The panel is **two columns** (a third does not render in Aslain's panel at all — tried, reverted),
so a **CATEGORY is not a column** but a bare `Label` header row (`_label()`, no `varName`)
followed by that feature's controls, with an **`Empty` spacer row** (`_empty()`) between
categories. Because the header names the feature, each master's own label is just **"Enabled"**
(was "Show" before v14).
Built in `_template()`:

- **column1 = two categories, two groups and two standalone radios spliced together.** Each group
  is its own `_grouped_column1()` call (→ `templates.createControlsGroup(master, children,
  indent=True)`, with a feature-detect fallback that sets `masterVarName` by hand for older MSA /
  izeberg):
  1. `Label` **"Battle Calculator"**, then the `battle_widget_enabled` master + two indented
     children ("Alt Press", "Counted Assistance Row");
  2. `_empty()`, `Label` **"Battle Progress"**, then the `progress_bar_enabled` master + its three
     **VISIBILITY** children ("Events", "Alt Press", "Always") — the first two then **trade** the
     group binding for an **AND gate** via `_gate_and()` (see below);
  3. the two **standalone `inline` radios** ("Mode", "Scale") — deliberately ungated;
  4. …and, in the SAME category (no header of its own), the `progress_transitions_enabled`
     master + two **label-only** children ("Events", "Alt Press").
- **column2 = `Label` "Garage Widget", the standalone `garage_widget_enabled` master, an
  `_empty()`, then the "Layout" group** — a `Label` header, the posX / posY `NumericStepper`s, and
  the "Follow Carousel Mode" checkbox.

**The two near-identical child pairs are DIFFERENT AXES and the resemblance is deliberate:** the
visibility trio decides **WHEN** the bar comes up, the Transitions pair only **HOW** it moves once
it does. Don't conflate them.

| Control (EN label) | key / `varName` | column | default | getter | consumed by |
|---|---|---|---|---|---|
| *Garage Widget* (header, **bold**) | — | column2 `Label` | — | — | — |
| Enabled | `garage_widget_enabled` | column2 (standalone) | ON | `garage_enabled()` | `bridge/gameface_bridge.py` (garage widget presence) |
| *Battle Calculator* (header, **bold**) | — | column1 `Label` | — | — | — |
| Enabled | `battle_widget_enabled` | column1 group-1 master | ON | `battle_enabled()` | `bridge/battle_bridge.py` (overlay hard gate) |
| Alt Press | `battle_widget_alt_key` | column1 group-1 child | OFF | `battle_alt_key_enabled()` | `bridge/battle_bridge.py` peek modifier |
| Counted Assistance Row | `counted_assistance_enabled` | column1 group-1 child | **ON** (flipped in v13) | `counted_assistance_enabled()` | `battle_bridge` → `BattleMoEVM.assistVisible` → JS row 3 |
| *Battle Progress* (header, **bold**) | — | column1 `Label` | — | — | — |
| Enabled | `progress_bar_enabled` | column1 group-2 master | OFF | `progress_bar_enabled()` | `battle_bridge` (centre-screen transient, hard gate) |
| ↳ Events | `progress_show_events` | column1 group-2 child (**AND-gated**) | ON | `progress_show_events()` | `battle_bridge` — whether a damage/efficiency tick raises the bar |
| ↳ Alt Press | `progress_show_alt_key` | column1 group-2 child (**AND-gated**) | ON | *(none — folded into `progress_alt_held()`)* | — |
| ↳ Always | `progress_show_always` | column1 group-2 child | OFF | *(none — folded into BOTH getters)* | — |
| Mode — Damage Efficiency / Moving Average | `progress_bar_variant` | column1 **standalone**, `inline` (**RadioButtonGroup**, **int**) | `0` = Damage Efficiency | `progress_bar_variant()` | `battle_bridge` — picks which centre-screen window opens |
| Scale — Default / Large | `progress_bar_size` | column1 **standalone**, `inline` (**RadioButtonGroup**, **int**) | `0` | `progress_bar_size()` | both bars' `barSize` → `MoEBarTransient.applySize` (root-font 1.5× + `.mp-lg`) |
| Transitions | `progress_transitions_enabled` | column1 group-3 **master** | ON | *(none — folded in below)* | never pushed to JS |
| ↳ Events | `progress_transitions_events` | column1 group-3 child | ON | `progress_transitions_events()` | `ProgressVM.transEvents` / `EfficiencyVM.transEvents` → `applyAnim` |
| ↳ Alt Press | `progress_transitions_manual` | column1 group-3 child | ON | `progress_transitions_manual()` | `…VM.transManual` → `applyAnim` (the Alt peek) |
| *Layout* (header, **bold**) | — | column2 `Label` | — | — | — |
| Follow Carousel Mode | `followCarousel` | column2 (sits ABOVE the steppers as of v14) | ON | `follow_carousel()` | garage widget carousel nudge |
| *Position* (sub-label, **not bold** — deliberately excluded from `HEADER_KEYS`) | — | column2 `Label` | — | — | — |
| Horizontal (left X) / Vertical (top Y) | `posX`, `posY` (+ non-user `posW`, `posH`) | column2 | 0 = auto | `pos_x()` … `pos_h()` | garage widget placement / rescale |

```python
COL1_KEYS = (u"catBattleCalc", u"battleWidget", u"battleAltKey", u"countedAssist",
             None,                                    # Empty spacer
             u"catBattleProgress", u"progressBar",
             u"progressShowEvents", u"progressShowAlt", u"progressShowAlways",
             VARIANT_KEY, u"progressSize",
             u"progressTransitions", u"progressTransEvents", u"progressTransManual")  # 15 slots
COL2_KEYS = (u"catGarage", u"garageWidget", None, u"positioning", u"followCarousel",
             u"positionSub", u"posX", u"posY")                                          # 8 slots (v14)
```

**v14 grew `COL2_KEYS` 7 → 8**: Follow Carousel moved to sit right under the (now bold) "Layout"
header, and a new varName-less `"positionSub"` (**"Position"**) sub-label was inserted ahead of the
two steppers — deliberately **excluded** from `HEADER_KEYS` (below) so its lighter weight reads as a
sub-level under "Layout" rather than a third header.

### `HEADER_KEYS` — the bold category/group headers, and the double-wrap self-revert bug (v14, RESOLVED)

`settings_i18n.HEADER_KEYS = frozenset((u"catBattleCalc", u"catBattleProgress", u"catGarage",
u"positioning"))` — the four header rows that render **bold**; `"positionSub"` is deliberately
excluded (the non-bold sub-label under "Layout").

**The wrap lives in exactly ONE place: `settings_i18n.build()`**, applied to each `HEADER_KEYS`
entry **after** the untranslated-fallback mark (so a marked English leak stays visible inside the
bold, not stranded outside it):

```python
for k in HEADER_KEYS:
    out[k][u"text"] = u"<b>%s</b>" % out[k][u"text"]
```

`mod_settings._label(key, rendered)` then does nothing but read `key in settings_i18n.HEADER_KEYS`
to add the matching `useHTML: True`, and passes `rendered["text"]` through **verbatim** — it never
wraps anything itself.

**Why this has to be one site, not two:** `_sync_template_text()` runs on **every** `register()`
call, including the one that just built the freshly-bolded template. It compares the stored
`comp["text"]` against a **freshly re-rendered** `panel_text()[key]["text"]`. If `_label()` had
wrapped the markup itself while `panel_text()` returned it unwrapped, that comparison would see
`"<b>Battle Calculator</b>"` disagree with `"Battle Calculator"` on the very first `register()`,
overwrite the bold back out, and `saveState()` — silently, on every launch, with `useHTML` left
dangling `True` on now-plain text. **This is exactly the bug that shipped before the v14 fix**, and
the on-disk tell is `aslainmenu.dat` showing `{'text': 'Battle Calculator', 'useHTML': True}` with no
`<b>` in sight — the enabling key survived, the markup didn't. Whenever a `_label`/`_checkbox`/etc.
decoration is added, it MUST be applied inside `settings_i18n.build()`, never inside `_template()`.

**The regression test has to be a build-then-sync round trip**, not a one-shot "does `_label` emit
bold" assertion — the latter passes against the broken code because it only exercises `_label` in
isolation with already-wrapped input. `tests/test_mod_settings.py`'s
`test_sync_template_text_walks_built_template_in_lockstep` (and its neighbours around it) build the
template exactly as `register()` does, run `_sync_template_text()` against it, and assert the `<b>`
+ `useHTML` survive.

This bump (13 → 14) also carries the three masters' own label going "Show" → "Enabled" and the
position steppers regaining their axis-hint wording — both text-only changes that would otherwise
have ridden `_sync_template_text` for free, but travel with this bump regardless since it was already
forced by the header bold + column-2 regroup.

These are the wire order MSA and `_sync_template_text` walk in lockstep, and the pairing is
**positional** — `zip(tmpl[col], keys)`, so a reorder or an omission does not error, it retitles
the **wrong control** on every existing install. Every bare **category `Label`** earns a slot even
though it has no `varName`. **A row with no TEXT at all — an `Empty` spacer — takes a `None`
SENTINEL slot**, never a skip: `panel_text().get(None)` is falsy, so the sync walk's existing
`if not rendered: continue` handles it for free, whereas skipping a component by type would
consume the component *without* consuming its key and desync every control after it.
**Appending** to the end shifts nothing and is the safe move; inserting is not.

### Gating: two grouped masters, one AND gate, two ungated radios

`createControlsGroup` sets exactly **one** `masterVarName` per child, so a master-under-a-master is
not expressible **through it**. But **MSA 1.6.4 has real conditional gating** (capability section
below), so three shapes are available:

1. **`_grouped_column1(master, children)`** — the default. One `masterVarName` per child.
2. **`_gate_and(control, ((var, value), …))`** — MSA's multi-condition form (`conditions` +
   `conditionsLogic: "AND"` + `masterIndent`), emitted by hand as plain keys. ⚠️ **`conditions`
   does NOT set `masterVarName`, so it REPLACES the group parenting** — `_gate_and` therefore
   `pop`s the now-dead `masterVarName` and the caller must include the group master as one of the
   conditions. `show_events` / `show_alt` are grouped under `PROGRESS_BAR_KEY` and then re-gated on
   `(PROGRESS_BAR_KEY == True) AND (PROGRESS_SHOW_ALWAYS_KEY == False)`, because they are also
   meaningless while "Always" is on.
3. **standalone** — no master, no condition. Both radios: Mode and Scale describe the bar itself
   rather than when it shows, they cost one row each because they are `inline`, and leaving them
   ungated keeps them readable while the feature is off (the same call already made for the
   column-2 steppers).

"Transitions under Progress Bar" is still a **third `_grouped_column1(...)` splice inside the same
category** — visually part of the Battle Progress block, with the accepted cost that **the
Transitions master is NOT greyed out while Progress Bar is off**. Harmless at runtime: the
`progress_bar_enabled()` gate means the flags have nothing to affect until the bar is on. (A
`_gate_and` on that master would grey it too, at the cost of the indent the group gives its
children — not attempted.)

### "Always" costs NO new code path — it is a permanently-held Alt

`MoEBarTransient.peekOn()` already pauses the run at its hold plateau **and** `clearTimeout(endT)`,
so a hold **never ends** while `altHeld` is true. `progress_alt_held(alt_held)` therefore just
reports `True` forever when "Always" is on — no fourth branch, no new CSS, no new VM field. It is
also why three new settings cost exactly **one** extra pushed bool: two collapse into the existing
`altHeld` push and the third folds into `progress_show_events()`.

### The visibility getters FOLD "ALWAYS" IN

MSA **still stores and still pushes a greyed control's value**, so a control being disabled in the
panel guarantees nothing at runtime. Every fold has to happen in Python:

```python
def progress_show_events():        # "Always" ON => the events flag must READ as on regardless
    return (bool(_settings.get(PROGRESS_SHOW_ALWAYS_KEY, False))
            or bool(_settings.get(PROGRESS_SHOW_EVENTS_KEY, True)))

def progress_alt_held(alt_held):   # ONE place, so the two bar variants can never disagree
    if bool(_settings.get(PROGRESS_SHOW_ALWAYS_KEY, False)):
        return True
    return bool(alt_held) and bool(_settings.get(PROGRESS_SHOW_ALT_KEY, True))
```

Keeping `progress_show_events()` true while pinned is also what keeps the bar's **numbers** live:
the JS commits new values on the same trigger it shows on.

### The two transition getters FOLD THE MASTER IN

`progress_transitions_enabled` has **no getter of its own and is never pushed to the widget**.
Both children's getters AND it together:

```python
return (bool(_settings.get(PROGRESS_TRANSITIONS_KEY, True))
        and bool(_settings.get(PROGRESS_TRANS_EVENTS_KEY, True)))   # …_MANUAL_KEY for the other
```

One place ANDs the group, so the JS can never honour a child while the master is off. The JS half
of the same discipline reads the pushed bools as `!== false` (absent ⇒ animated, the shipped
behaviour) — see `wotmod-gameface-widget` and the memory note on new VM bools.

### `_checkbox` / `_radio` / `_label` all omit a FALSY tooltip

All three descriptor helpers end with `tooltip = rendered.get("tooltip"); if tooltip: …`.
`_checkbox` used to hard-index `rendered["tooltip"]` and raised **`KeyError` inside `_template()`**
— i.e. inside `register()`'s guarded `try`, so the live symptom was **a client with no settings
panel at all** plus one logged traceback. The trigger is the **first label-only control of a given
TYPE**, which the Transitions children are. Emitting `u""` is not a fix: `_sync_template_text` only
overwrites, never deletes. The tripwire is the exact `tipless == 10` counter in
`tests/test_mod_settings.py::test_sync_template_text_walks_built_template_in_lockstep` (three
category headers + both radios + the three visibility children + the two Transitions children),
alongside `spacers == 2` for the two `None`-sentinel `Empty` rows.

The getters import NOTHING from the sibling bridges, so `gameface_bridge` / `battle_bridge` read
them without a cycle. Live state seeds from MSA in `register()`; defaults until then / if MSA absent.

## The two non-bool settings: both radios

`progress_bar_variant` and `progress_bar_size` are the mod's **only** settings that are not
bools. MSA's `RadioButtonGroup` stores its `value` as a **0-based option INDEX**:

- `PROGRESS_VARIANT_EFFICIENCY = 0` (the default), `PROGRESS_VARIANT_MOVING_AVERAGE = 1`.
  ⚠️ **The order FLIPPED in v13** and the stored raw int rides across **unchanged**, so an existing
  user's chosen bar swaps exactly once, silently — accepted deliberately, with no migration (one
  keyed on the old order would be indistinguishable from a fresh `0`);
- `PROGRESS_SIZE_DEFAULT = 0` (the shipped size), `PROGRESS_SIZE_LARGE = 1`.

`clamp_variant(v, max_index=PROGRESS_VARIANT_MOVING_AVERAGE)` is **shared** by both; the size radio
passes its own ceiling. `_coerce(key, value)` is therefore a **four-way branch**, and the order
matters:

```python
if key in _POS_KEYS:            return clamp_pos(value)                        # px ints
if key == PROGRESS_VARIANT_KEY: return clamp_variant(value)                    # radio index
if key == PROGRESS_SIZE_KEY:    return clamp_variant(value, PROGRESS_SIZE_LARGE)
return bool(value)                                                             # everything else
```

Falling through to `bool()` would turn index `1` into `True`, round-trip that bool back into MSA
and destroy the setting. **`clamp_variant` must test `isinstance(v, bool)` FIRST** — `bool` is an
`int` subclass, so a plain `int()` silently passes `True` through as a legal `1`. Anything
non-numeric / negative / out-of-range / boolean falls back to `0` — the safe choice for both
radios, since index 0 is in each case the behaviour the bar always had. Both getters
(`progress_bar_variant()`, `progress_bar_size()`) **re-clamp on read** (like the position getters),
so a corrupt store can never leak a bool or a stray index into the window picker or the widget.

`_radio()` (used for **both** radios) builds the MSA descriptor dict **by hand** — the same shape
`templates.createRadioButtonGroup` emits (`type` / `text` / `varName` / `value` / `inline` /
`options`, plus `tooltip` only when there is one), verified against the decompiled vendored
`templates.pyc`. Two reasons, both load-bearing:

- `_template()` stays a pure, unit-testable dict with **no `gui.aslainMenu` import**;
- **`inline: True` is emitted as a plain KEY, never through the helper's `inline` KWARG.** The
  kwarg raises `TypeError` on MSA < 1.6.1; an unknown *key* just rides through, because MSA does
  no descriptor validation at all. So the repo gets the one-horizontal-row layout — which is what
  lets two standalone two-option radios cost one row each instead of four stacked rows — with the
  version floor structurally impossible.

An API that doesn't know `RadioButtonGroup` (the izeberg fallback) simply skips the control; the
`progress_bar_enabled` master above it is a plain `CheckBox` and keeps working, with
`progress_bar_variant()` reporting its `0` default.

### Why `progress_bar_enabled` is its OWN master (and the radios now sit outside)

A grouped child inherits **that group's master** as its `masterVarName`, so passing the progress
controls as children of the In-Battle group would grey the progress bar out whenever the
*unrelated* In-Battle Widget is off. That hazard is exactly why `progress_bar_enabled` used to sit
**outside** the group with no `masterVarName` at all. Giving it its **own** master — a **second
`_grouped_column1(...)` call whose flat list is spliced onto the first** — keeps the property: its
children grey out with `PROGRESS_BAR_KEY` and nothing else, and `PROGRESS_BAR_KEY` itself stays a
group MASTER, so it still carries no `masterVarName`. Keep the reasoning in `_template()`'s
comment. The **Transitions** master is the same move a third time.

**v13 moved the two radios OUT of that group** and made them standalone `inline` controls — see
the gating section above for why (they describe the bar, not when it shows).

### The option labels are structural (the blank-label episode, now resolved)

- **Option labels live in `settings_i18n._VARIANT_OPTIONS` / `_SIZE_OPTIONS`**, two
  `{lang: (opt0, opt1)}` tables that must stay **BESIDE `_PANEL`, never inside it** — `_PANEL`'s
  keys are partitioned **positionally** by `COL1_KEYS` / `COL2_KEYS`, and an option tuple is not a
  label/tooltip row. `build()` attaches each tuple onto the rendered `VARIANT_KEY` /
  `progressSize` entry, where `_radio()` reads it. Fallback is **whole-tuple, not per-option** (the
  set's meaning is positional, so half-English is worse than all-English).
- Those labels are **STRUCTURAL to MSA**: Aslain folds the option tuple into `_settingsStructure`,
  and `_sync_template_text` rewrites only `text` / `tooltip` — **never `options[].label`**. So
  adding, removing, or merely re-wording/re-localizing an option reaches an existing install
  **only** through a `SETTINGS_VERSION` bump. Unlike every other string in `settings_i18n`.
- **RESOLVED — both radios are now normal `_PANEL` rows again** with real labels ("Mode",
  "Scale"). v10 had blanked the variant radio's label (`_row(u"")`) so its options read as direct
  children of the Progress Bar checkbox; v13 made them standalone `inline` controls, so each needs
  its own name back. `build()` no longer synthesises a blank entry for `VARIANT_KEY` — it only
  bolts the option tuple onto the rendered row. Both rows are still **tipless** (their option
  labels say it all), which is why they count toward `tipless == 10`.
- **Blanking that label cost the 9 → 10 bump, and un-blanking it rode the 12 → 13 one.** Text is
  *not* part of Aslain's `_settingsStructure` (and varName-less rows aren't collected at all), so
  strictly the empty label would have travelled text-only — but `_sync_template_text` can only
  **OVERWRITE** a key, never **DELETE** one, so a v9 install would have kept the stale "Bar Type"
  tooltip forever on a now-invisible row. Only `setModTemplate` replaces the stored control
  wholesale, and only a forward bump reaches it.

## Registration — soft dep, idempotent, self-healing

MSA (bundled `installer/vendor/aslain.modssettingsapi_1.6.4.wotmod`, import surface
`gui.aslainMenu`; izeberg's `gui.modsSettingsApi` is only a legacy fallback) is a **SOFT
dependency**: `register()` imports it guarded and, if absent, logs-and-returns with defaults
intact (both widgets on) and no panel — never a crash. There is no config file of ours; MSA
owns persistence.

### What MSA 1.6.4 offers → `wotmod-msa-settings`

The vendor capability survey (real conditional gating beyond a group master, the pure
key-setter nature of `enableWhen*` / `conditions`, `createControlsGroup`'s single effect, the
14 component types, zero descriptor validation, varName-less rows excluded from
`_settingsStructure`, and the two-columns reality) is the **harness** rule — read
`wotmod-msa-settings`. The installed copy here is byte-identical to
`installer/vendor/aslain.modssettingsapi_1.6.4.wotmod` and keeps its docstrings, so decompile
it (`wotmod-debug-repl`'s `uncompyle6` recipe) rather than guessing when a detail is missing.

Mod-relevant consequence: a boolean master's children grey out when it's off, but the disabled
state is **derived from a `masterVarName` / `conditions` binding**, not a per-control `disabled`
field — and a greyed control's value is **still stored and still pushed**, which is why every
"ignored while X is on" rule is folded Python-side below.

`register()` is **idempotent + self-healing** (`_registered` latch): MSA may not be loaded at
our import time (our reverse-domain id `com.14th_ua.moe_calculator` sorts early), so a first
failed attempt leaves the latch False and is retried on the first hangar mount
(`gameface_bridge.attach()` calls `register()` again). The entry point also subscribes the two
feature bridges' `apply_settings` as change listeners.

`_candidate_apis()` / `_primary_api()` are the harness probe verbatim (`wotmod-msa-settings` →
the probe): `gui.aslainMenu` first, the legacy `gui.modsSettingsApi` second and de-duped,
`register()` driving the primary while reset-hooks + template-text sync run on every candidate.

## The linkage-scoped, present-keys-only `_apply` rule (load-bearing)

MSA fires `onSettingsChanged` (and `onResetMod`) **GLOBALLY** — the callback runs for EVERY mod's
change, not just ours. Two defenses, both required:

- `_on_changed` / `_on_reset` are **linkage-scoped**: they early-return unless `linkage == LINKAGE`.
- `_apply(saved)` overlays **only the PRESENT known keys** onto the live cache in place; a key
  absent from `saved` keeps its current value. A naive replace-onto-`DEFAULTS` reintroduced a real
  bug: a foreign mod's global change handed us a payload with none of our keys, snapping every flag
  back to default — silently re-enabling the always-on battle overlay so it ignored
  "Battle Widget Enabled = off" + "Alt = on". A foreign payload now no-ops.

(`_seed` — the whole-state replace-filling-defaults — is used ONLY for the authoritative
registration/reset payload, never for the live-change path.)

## Master gate + Alt-peek modifier (the child model)

`battle_widget_enabled` is the **hard gate**; `battle_widget_alt_key` is a **peek modifier ON
an already-enabled overlay** (NOT mutually exclusive — that was the old, now-inverted rule). The
truth lives in `domain/battle_builder.battle_bar_visible` (pure, engine-free):

```
active == enabled and (alt_held if alt_mode else True)
```

- master **off** → overlay **never shown** (hard gate; `battle_bridge` doesn't even open the
  window — `_on_mount_refresh` early-returns, and the window-open gate keys on `battle_enabled()`
  alone).
- master **on** + Alt-child **off** → overlay **always shown**.
- master **on** + Alt-child **on** → overlay shown **only while Alt is held** (event-driven via
  `battle_input`, tracked in `_alt_held`).

The child greys out in the panel while the master is off (see `createControlsGroup` /
`masterVarName` above), and it's also inert at runtime — when `enabled` is false the `alt_mode`
term is never reached.

## Panel prose (defer to `wotmod-i18n-settings`)

Every visible label/tooltip comes from `adapter/settings_i18n.panel_text()` at the client's active
language (English master + per-key fallback; `COL1_KEYS` / `COL2_KEYS` are the wire order MSA and
`_sync_template_text` walk in lockstep — **15** and **8** slots (v14), two of which are `None`
sentinels for the `Empty` spacers). 11 language blocks. The four `HEADER_KEYS` entries come out of
`build()` pre-wrapped in `<b>...</b>` — see the `HEADER_KEYS` section above for why that wrap must
live nowhere else.
`modDisplayName` stays the literal English brand. THE gotcha — MSA caches a COPY of the template
text at registration, so on an EXISTING install a client-language change never shows unless
`_sync_template_text` rewrites the stored template text in place (text-only, NO `settingsVersion`
bump) — is the harness rule; see `wotmod-i18n-settings` for the full mechanism and the
`uk`-not-`ua` EU quirk.

**Two mod-specific exceptions to "text is free":** both radios' **option labels** are
structural (bump-only — see above), and **deleting** a text key (blanking a label) needs a bump too
because `_sync_template_text` overwrites but never removes. Renaming a **`varName`** is never free
either: `merge_settings` / `_apply` iterate `DEFAULTS` keys only with no rename/alias map, so a
rename silently resets every existing user's value. Rename the label, keep the key forever —
`progress_bar_enabled` is the shipped precedent (label went "Next Mark Progress Bar" → "Progress
Log" → "Progress Bar" → "Show"; the key never moved).

## Tests that guard this subsystem

Engine-free pytest (Python 3.13) — run the suite per `moe-build-release`:

- `tests/test_mod_settings.py` — `_coerce` / `clamp_variant` / `merge_settings` / `_apply`, the
  built template's per-column type + `varName` order, the label-only-tooltip regressions, and the
  `tipless == 10` / `spacers == 2` lockstep walk (the spacer branch also asserts the `None`-sentinel
  rows were left untouched).
- `tests/test_settings_i18n.py` — the `COL1_KEYS` / `COL2_KEYS` ↔ `_PANEL` partition and the
  untranslated-leak diagnostic.
- **`tests/test_view_models.py`** — the VMs' hand-numbered slot bookkeeping: `_add*Property` count
  vs each `__init__(properties=N)` default, and every `_set*` / `_getArray` index inside range.
  **Nothing else checks the declared count** (the recording fake VM ignores it), so a flag added to
  a VM without raising `properties` is otherwise green in pytest and broken only in the client.
- **`tests/test_progress_bridge.py`** (+ its sibling `tests/test_efficiency_bridge.py`) — the push
  marshalling for each bar's VM, including `test_push_writes_the_two_transition_flags_master_folded`,
  which is where the master-folding contract is actually pinned.

A layout/varName change also owes a look at `SETTINGS_VERSION` (see above) and, when it adds a
label-only row, at the exact `tipless` count.
