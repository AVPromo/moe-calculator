---
name: moe-settings
description: Use when editing the 14th_ua MoE Calculator's SETTINGS subsystem — the ModsSettingsAPI (MSA) panel, its two column-1 grouped masters (In-Battle Widget, Progress Bar) with the Progress Bar's int-valued variant radio, the column-2 garage widget + drag-position group, the flag getters the feature bridges read, MSA registration / soft-dep / self-heal, when a change owes a SETTINGS_VERSION bump, or why a foreign mod's settings change must not touch our flags. For the panel prose translation see the harness skill wotmod-i18n-settings; for feature internals see moe-garage / moe-battle.
---

# MoE Calculator — settings panel (feature)

The mod's user toggles, surfaced as ModsSettingsAPI (MSA) controls in the in-game mod-settings
menu. Shared mechanics live in the harness: **MSA structure, the replace-not-merge
rule, and `saveState`** → `wotmod-architecture` (ModsSettingsAPI); **panel-prose localization,
`_sync_template_text`, `getClientLanguage` + the `uk`-not-`ua` quirk** → `wotmod-i18n-settings`.
This skill is only the mod's concretes. All paths under `src/res/scripts/client/moe_calculator/`.

Owner module: `bridge/mod_settings.py` (flag state + MSA registration). Prose: `adapter/settings_i18n.py`.

## The controls (two-column panel, two grouped masters in column 1)

`SETTINGS_VERSION = 10`. Each `varName` == the `DEFAULTS` key, so the dict MSA returns maps
straight through `merge_settings`. Bump `SETTINGS_VERSION` **only** when the control layout /
varName set changes (the host wipes saved values back to defaults on a bump, and `register()`'s
migration branch carries the user's values across) — localizing plain label/tooltip text is
text-only and does NOT bump it. The full bump history is the comment block above the constant;
read it there rather than restating it. **The bump is always FORWARD, even to revert a layout** —
the host acts only on `new > stored`.

The panel is **two columns** (a third does not render in Aslain's panel at all — tried, reverted),
built in `_template()`:

- **column1 = TWO independent groups spliced together**, each via its own `_grouped_column1()`
  call (→ `templates.createControlsGroup(master, children, indent=True)`, with a feature-detect
  fallback that sets `masterVarName` by hand for older MSA / izeberg):
  1. the `battle_widget_enabled` master + two indented children ("Show on Alt Key",
     "Counted Assistance");
  2. the `progress_bar_enabled` master + one child, the **label-less variant radio**.
- **column2 = the standalone `garage_widget_enabled` master, then the drag-position group** — a
  positioning `Label` header, the posX / posY `NumericStepper`s, and the "Follow Carousel Mode"
  checkbox.

| Control (EN label) | key / `varName` | column | default | getter | consumed by |
|---|---|---|---|---|---|
| In-Garage Widget | `garage_widget_enabled` | column2 (standalone) | ON | `garage_enabled()` | `bridge/gameface_bridge.py` (garage widget presence) |
| In-Battle Widget | `battle_widget_enabled` | column1 group-1 master | ON | `battle_enabled()` | `bridge/battle_bridge.py` (overlay hard gate) |
| Show on Alt Key | `battle_widget_alt_key` | column1 group-1 child | OFF | `battle_alt_key_enabled()` | `bridge/battle_bridge.py` peek modifier |
| Counted Assistance | `counted_assistance_enabled` | column1 group-1 child | OFF | `counted_assistance_enabled()` | `battle_bridge` → `BattleMoEVM.assistVisible` → JS row 3 |
| Progress Bar | `progress_bar_enabled` | column1 group-2 master | OFF | `progress_bar_enabled()` | `battle_bridge` (centre-screen transient, hard gate) |
| *(no label)* Moving Average / Damage Efficiency | `progress_bar_variant` | column1 group-2 child (**RadioButtonGroup**, **int**) | `0` | `progress_bar_variant()` | `battle_bridge` — picks which centre-screen window opens |
| Widget position (px) / Horizontal / Vertical | `posX`, `posY` (+ non-user `posW`, `posH`) | column2 | 0 = auto | `pos_x()` … `pos_h()` | garage widget placement / rescale |
| Follow Carousel Mode | `followCarousel` | column2 | ON | `follow_carousel()` | garage widget carousel nudge |

```
COL1_KEYS = (u"battleWidget", u"battleAltKey", u"countedAssist",
             u"progressBar", u"progressVariant")          # 5 — wire order
COL2_KEYS = (u"garageWidget", u"positioning", u"posX", u"posY", u"followCarousel")
```

These are the wire order MSA and `_sync_template_text` walk in lockstep, and the pairing is
**positional** — `zip(tmpl[col], keys)`, so a reorder or an omission does not error, it retitles
the **wrong control** on every existing install. `progressVariant` earns a slot even though it
renders no label: it is still a control in the template. **Appending** to the end (what the
progress-bar work did, twice) shifts nothing and is the safe move; inserting is not.

The getters import NOTHING from the sibling bridges, so `gameface_bridge` / `battle_bridge` read
them without a cycle. Live state seeds from MSA in `register()`; defaults until then / if MSA absent.

## The one non-bool setting: the variant radio

`PROGRESS_VARIANT_KEY = "progress_bar_variant"` is the mod's **only** setting that is not a
bool. MSA's `RadioButtonGroup` stores its `value` as a **0-based option INDEX**:
`PROGRESS_VARIANT_MOVING_AVERAGE = 0` (the default — an existing user keeps the bar they had),
`PROGRESS_VARIANT_EFFICIENCY = 1`, ceiling `PROGRESS_VARIANT_MAX`.

`_coerce(key, value)` is therefore a **three-way branch**, and the order matters:

```python
if key in _POS_KEYS:            return clamp_pos(value)      # px ints
if key == PROGRESS_VARIANT_KEY: return clamp_variant(value)   # radio index
return bool(value)                                            # everything else
```

Falling through to `bool()` would turn index `1` into `True`, round-trip that bool back into MSA
and destroy the setting. **`clamp_variant` must test `isinstance(v, bool)` FIRST** — `bool` is an
`int` subclass, so a plain `int()` silently passes `True` through as a legal `1`. Anything
non-numeric / negative / out-of-range / boolean falls back to `0`. The getter
`progress_bar_variant()` **re-clamps on read** (like the position getters), so a corrupt store can
never leak a bool or a stray index into the window picker.

`_radio()` builds the MSA descriptor dict **by hand** — the same shape
`templates.createRadioButtonGroup` emits (`type` / `text` / `varName` / `value` / `options`, plus
`tooltip` only when there is one), verified against the disassembled vendored `templates.pyc`.
Two reasons, both load-bearing:

- `_template()` stays a pure, unit-testable dict with **no `gui.aslainMenu` import**;
- the helper's **`inline` kwarg is never passed at all**, so the `TypeError` it raises on
  MSA < 1.6.1 is structurally impossible. The options render in MSA's default vertical stack,
  which every build draws.

An API that doesn't know `RadioButtonGroup` (the izeberg fallback) simply skips the control; the
`progress_bar_enabled` master beside it is a plain `CheckBox` and keeps working, with
`progress_bar_variant()` reporting its `0` default.

### Why the radio is a group-2 child and not appended flat

A grouped child inherits **that group's master** as its `masterVarName`, so passing the progress
controls as children of the In-Battle group would grey the progress bar out whenever the
*unrelated* In-Battle Widget is off. That hazard is exactly why `progress_bar_enabled` used to sit
**outside** the group with no `masterVarName` at all. Giving it its **own** master — a **second
`_grouped_column1(...)` call whose flat list is spliced onto the first** — is the shape that
re-parents the radio under the Progress Bar checkbox **without** inheriting `BATTLE_KEY`: the radio
greys out with `PROGRESS_BAR_KEY` and nothing else, and `PROGRESS_BAR_KEY` itself stays a group
MASTER, so it still carries no `masterVarName`. Keep the reasoning in `_template()`'s comment.

### The option labels are structural; the label row is not (but still needed a bump)

- **Option labels live in `settings_i18n._VARIANT_OPTIONS`**, a `{lang: (opt0, opt1)}` table that
  must stay **BESIDE `_PANEL`, never inside it** — `_PANEL`'s keys are partitioned **positionally**
  by `COL1_KEYS` / `COL2_KEYS`, and an option tuple is not a label/tooltip row. `build()` attaches
  the tuple onto the rendered `VARIANT_KEY` entry, where `_radio()` reads it. Fallback is
  **whole-tuple, not per-option** (the set's meaning is positional, so half-English is worse than
  all-English).
- Those labels are **STRUCTURAL to MSA**: Aslain folds the option tuple into `_settingsStructure`,
  and `_sync_template_text` rewrites only `text` / `tooltip` — **never `options[].label`**. So
  adding, removing, or merely re-wording/re-localizing an option reaches an existing install
  **only** through a `SETTINGS_VERSION` bump. Unlike every other string in `settings_i18n`.
- **The radio's own label row is deliberately blank** (`_row(u"")` in every language block) so its
  two options read as direct children of the Progress Bar checkbox with no header row between.
  `_radio()` therefore **omits** the `tooltip` key rather than emitting `u""`; the per-variant
  prose moved onto the **master's** tooltip, the only hoverable surface the group has left. The
  empty row is present per language on purpose — an empty label is not an untranslated one, and the
  per-language entry stops `build()` marking it as an English fallback.
- **Blanking that label still cost the 9 → 10 bump.** Text is *not* part of Aslain's
  `_settingsStructure`, so strictly the empty label would have travelled text-only — but
  `_sync_template_text` can only **OVERWRITE** a key, never **DELETE** one, so a v9 install would
  keep the stale "Bar Type" tooltip forever on a now-invisible row. Only `setModTemplate` replaces
  the stored control wholesale, and only a forward bump reaches it.

**OPEN — not answerable from the Python.** Whether Aslain's panel still reserves a blank
line-height band where an empty-`text` row used to be. The layout is AS3 inside
`res/gui/flash/aslainMenu.swf` and no decompiler is available; the identifiers `labelH`,
`findRowLabelCenterY` and `textHeight` make a residual gap plausible. Needs an eyeball in-client.
Fallback if a gap shows: pass `inline: True` on the radio (accepting the MSA >= 1.6.1 floor) plus a
forward bump to **11**.

## Registration — soft dep, idempotent, self-healing

MSA (bundled `installer/vendor/aslain.modssettingsapi_1.6.4.wotmod`, import surface
`gui.aslainMenu`; izeberg's `gui.modsSettingsApi` is only a legacy fallback) is a **SOFT
dependency**: `register()` imports it guarded and, if absent, logs-and-returns with defaults
intact (both widgets on) and no panel — never a crash. There is no config file of ours; MSA
owns persistence.

The bundled **Aslain fork 1.6.4 DOES support child gating / grouping** (this is why the panel
can grey out the In-Battle children under their master, and the variant radio under the Progress
Bar master): `createControlsGroup(master,
children, indent=True)`, `enableWhen` / `visibleWhen` (with condition operators
`== != > >= < <=`), `enableWhenAll` / `enableWhenAny`, `visibleWhenAll` / `visibleWhenAny`, up
to **4 columns** (`column1..column4`), and 14 component types. A boolean master's children grey
out when it's off — but the disabled state is **derived from a `masterVarName` binding**, not a
literal per-control `disabled` field (this corrects an earlier note that claimed MSA had no
per-control disable at all).

`register()` is **idempotent + self-healing** (`_registered` latch): MSA may not be loaded at
our import time (our reverse-domain id `com.14th_ua.moe_calculator` sorts early), so a first
failed attempt leaves the latch False and is retried on the first hangar mount
(`gameface_bridge.attach()` calls `register()` again). The entry point also subscribes the two
feature bridges' `apply_settings` as change listeners.

With Aslain installed the mod's data lives in Aslain's own `gui.aslainMenu` object, a SEPARATE
instance from izeberg's `gui.modsSettingsApi`. `_candidate_apis()` probes `gui.aslainMenu`
FIRST and falls back to `gui.modsSettingsApi`, returning whichever import(s) succeed (de-duped,
preferred first) — so `_primary_api()` (which `register()` drives through) never lets a lingering
izeberg install win over Aslain, and reset-hooks + template-text sync still run on both when both
are present.

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
`_sync_template_text` walk in lockstep — **both are populated**, 5 keys each). 11 language blocks.
`modDisplayName` stays the literal English brand. THE gotcha — MSA caches a COPY of the template
text at registration, so on an EXISTING install a client-language change never shows unless
`_sync_template_text` rewrites the stored template text in place (text-only, NO `settingsVersion`
bump) — is the harness rule; see `wotmod-i18n-settings` for the full mechanism and the
`uk`-not-`ua` EU quirk.

**Two mod-specific exceptions to "text is free":** the variant radio's **option labels** are
structural (bump-only — see above), and **deleting** a text key (blanking a label) needs a bump too
because `_sync_template_text` overwrites but never removes. Renaming a **`varName`** is never free
either: `merge_settings` / `_apply` iterate `DEFAULTS` keys only with no rename/alias map, so a
rename silently resets every existing user's value. Rename the label, keep the key forever —
`progress_bar_enabled` is the shipped precedent (label went "Next Mark Progress Bar" → "Progress
Log" → "Progress Bar"; the key never moved).
