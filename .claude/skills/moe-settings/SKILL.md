---
name: moe-settings
description: Use when editing the 14th_ua MoE Calculator's SETTINGS subsystem — the ModsSettingsAPI (MSA) panel, its six bold category/group headers, Empty spacers, the four column-1 grouped/standalone categories (In-Battle Widget, Progress Bar + its three visibility children, Transitions + its Events/Alt Press/Hold Duration slider children, "Layout" (i18n key catBarPosition) + its Orientation/Alignment radios and its two shared X/Y steppers for the Ctrl+drag reposition) and the four standalone inline int-valued radios (Mode, Scale, Orientation, Alignment), the column-2 garage widget + layout group, the flag getters the feature bridges read (including the master-folded transition getters, the "Always"-folded visibility getters, and the position getters/setter), MSA registration / soft-dep / self-heal, MSA 1.6.4's real conditional gating and its zero descriptor validation, when a change owes a SETTINGS_VERSION bump, or why a foreign mod's settings change must not touch our flags. For the reusable MSA panel MECHANICS (probe, register/migrate lifecycle, descriptor shapes, guards, bump rules) see the harness skill wotmod-msa-settings; for the panel prose translation see wotmod-i18n-settings; for feature internals see moe-garage / moe-battle.
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

## The controls (two-column panel, four categories, three grouped masters + four standalone radios + one standalone stepper pair in column 1)

`SETTINGS_VERSION = 21`. Each `varName` == the `DEFAULTS` key, so the dict MSA returns maps
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

- **column1 = two categories, two groups and four standalone radios spliced together.** Each group
  is its own `_grouped_column1()` call (→ `templates.createControlsGroup(master, children,
  indent=True)`, with a feature-detect fallback that sets `masterVarName` by hand for older MSA /
  izeberg):
  1. `Label` **"Battle Calculator"**, then the `battle_widget_enabled` master + two indented
     children ("Alt Press", "Counted Assistance Row");
  2. `_empty()`, `Label` **"Battle Progress"**, then the `progress_bar_enabled` master + its three
     **VISIBILITY** children ("Events", "Alt Press", "Always") — the first two then **trade** the
     group binding for an **AND gate** via `_gate_and()` (see below);
  3. the two **standalone `inline` radios** ("Mode", "Scale") — deliberately ungated;
  4. `_empty()`, `Label` **"Transitions"**, then the `progress_transitions_enabled` master + THREE
     children: two label-only checkboxes ("Events", "Alt Press") and, as of v17, a `Slider`
     ("Hold Duration (s)") — `progress_hold_seconds`, 1-30s, `snapInterval: 1`, `format:
     "{{value}} s"`, default 5. Its master's own label reads **"Enabled"** now, same as the
     other three masters (was "Transitions" before v17), but the `varName` is deliberately
     unchanged;
  5. `_empty()`, `Label` **"Layout"** (i18n key `catBarPosition`, header text renamed from "Bar
     Position" at v21 — the key is unchanged, a rename buys nothing since it's positional in
     `COL1_KEYS`), then two more **standalone `inline` radios** — "Orientation"
     (`progress_bar_orientation`: Horizontal `0` default / Vertical `1`) and "Alignment"
     (`progress_bar_alignment`: Damage Log `0` default / Minimap `1` / Free `2`) — followed by the
     two **standalone** `NumericStepper`s, `progress_bar_pos_x` / `progress_bar_pos_y`, mirroring
     the in-battle bar's Ctrl+drag reposition (see `moe-battle`). All four are standalone like the
     Mode/Scale radios above (no master, no condition): a bar's shape/anchor and a coordinate
     should all stay readable/editable while the feature is off. **One shared radio pair and one
     shared stepper pair serve BOTH bar variants** (they're mutually exclusive at runtime); the
     steppers store LOGICAL GUI px (interface-scale invariant, no `posW`/`posH` viewport pinning
     like the garage pair below). **As of v21 the steppers are anchor-relative OFFSETS, not an
     absolute top-left. The old *universal* `0/0 == auto` sentinel is gone, but Free keeps its own:
     under Alignment = Free the exact pair `(0, 0)` still resolves to the orientation's default
     anchor** (`bar_window.py:295-297`) — see `anchor_offset()` /
     `progress_bar_alignment()` below. Both this pair's steppers and the garage `posX`/`posY` pair
     below run **`-POS_MAX .. POS_MAX`** (was `0 .. POS_MAX` before v20) — the on-screen edge
     clamp was removed so a bar may be dragged past any screen edge; see the memory
     `[[unclamping-drag-is-constrained-by-the-auto-placement-sentinel]]`. All three Alignment
     options stay always-selectable regardless of Orientation (MSA gates whole controls, not
     individual radio options) — a per-orientation restriction was rejected as a second stored key
     for no behavioural gain.
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
| Enabled (Transitions master) | `progress_transitions_enabled` | column1 group-3 **master** | ON | *(none — folded in below)* | never pushed to JS |
| ↳ Events | `progress_transitions_events` | column1 group-3 child | ON | `progress_transitions_events()` | `ProgressVM.transEvents` / `EfficiencyVM.transEvents` → `applyAnim` |
| ↳ Alt Press | `progress_transitions_manual` | column1 group-3 child | ON | `progress_transitions_manual()` | `…VM.transManual` → `applyAnim` (the Alt peek) |
| ↳ Hold Duration (s) | `progress_hold_seconds` | column1 group-3 child, `Slider` (1-30, int) | `5` | `progress_hold_seconds()` — **NOT** master-folded (a duration, not a flag) | both bars' `MoEBarTransient` hold timer |
| *Layout* (header, **bold**, v18, header text renamed from "Bar Position" at v21, key `catBarPosition` unchanged) | — | column1 `Label` | — | — | — |
| Orientation — Horizontal / Vertical | `progress_bar_orientation` | column1 **standalone**, `inline` (**RadioButtonGroup**, **int**, v21) | `0` = Horizontal | `progress_bar_orientation()` | `bar_window.BarHost._resolve` (orientation branch), front-end DOM build branch |
| Alignment — Damage Log / Minimap / Free | `progress_bar_alignment` | column1 **standalone**, `inline` (**RadioButtonGroup**, **int**, v21) | `0` = Damage Log | `progress_bar_alignment()` | `bar_window.BarHost._resolve` (alignment branch picks `anchor_centred_reduced` / `anchor_minimap` / origin) |
| Horizontal (left X) / Vertical (top Y) | `progress_bar_pos_x`, `progress_bar_pos_y` | column1 **standalone** `NumericStepper`s, range `-POS_MAX..POS_MAX` (v20) | 0 = anchor-relative offset under Damage Log / Minimap; under **Free**, the exact pair 0/0 means AUTO (the orientation's default anchor) | `bar_pos_x()` / `bar_pos_y()` | `bar_window.BarHost.apply_position` (both bars, via `battle_bridge.apply_settings` → `progress_view`/`efficiency_view.apply_position()`) |
| *Layout* (header, **bold**) | — | column2 `Label` | — | — | — |
| Follow Carousel Mode | `followCarousel` | column2 (sits ABOVE the steppers as of v14) | ON | `follow_carousel()` | garage widget carousel nudge |
| *Position* (sub-label, **not bold** — deliberately excluded from `HEADER_KEYS`) | — | column2 `Label` | — | — | — |
| Horizontal (left X) / Vertical (top Y) | `posX`, `posY` (+ non-user `posW`, `posH`) | column2, range `-POS_MAX..POS_MAX` (v20) | 0 = auto | `pos_x()` … `pos_h()` | garage widget placement / rescale |

```python
COL1_KEYS = (u"catBattleCalc", u"battleWidget", u"battleAltKey", u"countedAssist",
             None,                                    # Empty spacer
             u"catBattleProgress", u"progressBar",
             u"progressShowEvents", u"progressShowAlt", u"progressShowAlways",
             None,                                    # Empty spacer
             VARIANT_KEY, u"progressSize",
             None,                                    # Empty spacer
             u"catTransitions", u"progressTransitions",
             u"progressTransEvents", u"progressTransManual",
             None,                                    # Empty spacer (v20)
             u"progressHoldSeconds",
             None,                                    # Empty spacer
             u"catBarPosition", u"progressOrientation", u"progressAlignment",
             u"barPosX", u"barPosY")               # 26 slots (v21, grew from 24 at v20)
COL2_KEYS = (u"catGarage", u"garageWidget", None, u"positioning", u"followCarousel",
             None, u"positionSub", u"posX", u"posY")                                    # 9 slots
```

**v14 grew `COL2_KEYS` 7 → 8**: Follow Carousel moved to sit right under the (now bold) "Layout"
header, and a new varName-less `"positionSub"` (**"Position"**) sub-label was inserted ahead of the
two steppers — deliberately **excluded** from `HEADER_KEYS` (below) so its lighter weight reads as a
sub-level under "Layout" rather than a third header. **`COL2_KEYS` has since grown 8 → 9** (a second
`Empty` spacer now heads "Position" the same way the first one heads "Battle Progress").

**v17 added a `catTransitions` `Label` header** ahead of the Transitions master (previously the
group rode inside the "Battle Progress" category with no header of its own) plus the
`progress_hold_seconds` `Slider` as a fourth Transitions child — growing `COL1_KEYS` 17 → 19
(two more `None` spacers plus `catTransitions` and `progressHoldSeconds`) and `HEADER_KEYS`
four entries → five.

**v18 added a FOURTH column-1 category, `catBarPosition`** (header text "Bar Position" at the
time, renamed "Layout" at v21 — see below) — an `Empty` spacer + its own bold `Label` header,
then the two standalone `progress_bar_pos_x` / `progress_bar_pos_y` `NumericStepper`s (`barPosX`
/ `barPosY`) mirroring the in-battle bar's Ctrl+drag reposition. Appended at the very end (safe:
shifts nothing before it) — `COL1_KEYS` grows 19 → 23 and `HEADER_KEYS` five entries → six.

**v20** (the `-POS_MAX..POS_MAX` unclamp) also split the Transitions group's two switch children
from the ungrouped `progressHoldSeconds` slider with its own `None` spacer — `COL1_KEYS` grows
23 → 24, no `HEADER_KEYS` change.

**v21 (Orientation + Alignment) renamed the "Bar Position" header text to "Layout"** — the i18n
KEY stays `catBarPosition` (it's positional in `COL1_KEYS`/`HEADER_KEYS`; a key rename buys
nothing) — and spliced two new standalone `inline` radios, `progressOrientation` /
`progressAlignment`, in **AFTER** `catBarPosition` and **BEFORE** `barPosX`/`barPosY`, matching
`mod_settings._template()`'s wire order exactly. Inserting mid-column rather than appending is
safe **only** because a `SETTINGS_VERSION` bump (20 → 21) accompanies it. `COL1_KEYS` grows
24 → 26, `HEADER_KEYS` is unchanged at six (the new radios are ordinary rows, not headers).

### `HEADER_KEYS` — the bold category/group headers, and the double-wrap self-revert bug (v14, RESOLVED)

`settings_i18n.HEADER_KEYS = frozenset((u"catBattleCalc", u"catBattleProgress", u"catTransitions",
u"catBarPosition", u"catGarage", u"positioning"))` — the **six** header rows that render **bold**
(as of v18); `"positionSub"` is deliberately excluded (the non-bold sub-label under "Layout").

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

### Gating: two grouped masters, one AND gate, four ungated radios

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
3. **standalone** — no master, no condition. All four radios — Mode, Scale, and the v21
   Orientation / Alignment pair — describe the bar itself rather than when it shows, they cost
   one row each because they are `inline`, and leaving them ungated keeps them readable while the
   feature is off (the same call already made for the column-2 steppers). All three Alignment
   options stay always-selectable regardless of Orientation — MSA gates whole controls, not
   individual radio options, so a per-orientation restriction would need a second stored key for
   no behavioural gain, and was rejected. The v18 "Layout" (`catBarPosition`) `barPosX` /
   `barPosY` steppers are standalone for the identical reason — a saved coordinate should stay
   readable/editable even with the bar off.

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

### `bar_pos_x()` / `bar_pos_y()` and `set_bar_position()` — the Ctrl+drag position pair

`progress_bar_pos_x` / `progress_bar_pos_y` (`BAR_POS_X_KEY` / `BAR_POS_Y_KEY`, both frozen
`varName`s forever) store the in-battle bar's dragged top-left in **logical GUI px**, shared by
**both** bar variants — they're mutually exclusive at runtime, so one pair is one fewer settings
row rather than a duplicated pair per variant. `bar_pos_x()` / `bar_pos_y()` re-clamp on read
(`clamp_pos`, same `_POS_KEYS` branch of `_coerce` as the garage `posX`/`posY`).

**Placement model as of v21 (Orientation + Alignment) — `anchor_pinned` and its blanket
`0/0 == auto` sentinel are GONE.** Placement is now `anchor_offset(base, off_x, off_y)`, where
`base` is whichever of three alignment branches `progress_bar_alignment()` selects —
`anchor_centred_reduced` (Damage Log), `anchor_minimap` (Minimap), or the screen origin (Free) —
and `off_x`/`off_y` are these same two steppers, now **anchor-relative offsets** rather than an
absolute top-left. **CORRECTED 2026-08-08: Free still has a sentinel of its own.** Before the Free
branch runs, `_resolve` (`bar_window.py:295-297`) rewrites the exact pair `(0, 0)` under Free to
this orientation's default alignment (Horizontal → Damage Log, Vertical → Minimap), so Free+0/0 is
AUTO, **not** the screen corner. This is load-bearing: it is what lets an Orientation flip zero the
stored pair without carrying the other orientation's coordinates across. (Earlier revisions of this
file and of `[[unclamping-drag-is-constrained-by-the-auto-placement-sentinel]]` claimed the
opposite; the claim has flipped several times — read `_resolve`.) `anchor_centred` itself is
retained byte-for-byte in `domain/positioning.py`
as the pre-reduction oracle `anchor_centred_reduced`'s `abs(delta) <= 1` bound is tested against,
though nothing in `src/` calls it anymore.

**`_migrate_pre_v21_layout` and the sticky-Free auto-set rule** run in `mod_settings`, both keyed
on the same `_on_changed` machinery: a pre-v21 store is migrated by **lookup, not arithmetic** —
keyed on the absence of `progress_bar_orientation` (same trick `_flip_pre_v13_variant` already
uses) — a non-zero pre-bump `(pos_x, pos_y)` implies the old absolute placement, so it becomes
Alignment = Free with the coordinates carried verbatim; a zero pair implies the shipped centred
placement, so it becomes Alignment = Damage Log, still `(0, 0)`. Nobody's bar moves on upgrade.
At runtime, `_on_changed` compares the live cache before vs. after every settings-panel change to
auto-set Alignment: an Orientation flip re-anchors Alignment to (Horizontal → Damage Log, Vertical
→ Minimap) **unless Alignment is already Free**; a `set_bar_position()` call (drag end) or a
stepper edit sets Alignment to Free unconditionally. **Free is sticky — an Orientation switch must
never overwrite it** (`mod_settings.py:1293`'s `!= PROGRESS_ALIGN_FREE` gate). **The maintainer
REVERSED this on 2026-08-08** — the rule still describes the shipped code, but it is scheduled for
deletion; see `TASKS/in-battle-bar-layout-auto-set-redesign.md` before relying on it. The write-back inside
`_on_changed` fires one more `onSettingsChanged` of its own; it terminates because the second pass
finds the values already equal, the same self-terminating pattern the pre-v13 migration already
relies on — no re-entrancy flag needed (see the memory
`[[a-noop-mutation-and-a-fail-soft-branch-can-look-identical]]` for why a test of this guard must
assert the **call count**, not just the resulting value).

`set_bar_position(x, y, persist=True)` is the write path, called from `bar_window.BarHost.drag`
on gesture end (`phase == "end"`). **The gesture itself has no JS and no wire protocol at
all** — Python owns it end to end: `adapter/battle_input.py` samples Ctrl + the left mouse
button off WG's own input dispatchers and `gui.g_mouseEventHandlers`, and `BarHost.drag` places
the window ABSOLUTELY from the live cursor position (`domain/positioning.cursor_top_left`) plus
a grab offset recorded at gesture start — never a delta. The previous design (a JS `setPosition`
command reporting a mouse delta for Python to add) is gone: both bar VMs are `commands=0`
again. See `moe-battle`'s Ctrl+drag notes and the memory
`[[absolute-cursor-placement-replaces-js-delta-drag-protocol]]` for why the delta protocol
could not work structurally. `set_bar_position` deliberately does **NOT** call `_notify()`,
unlike `set_position` (the garage twin): the bar host re-places its own window directly in the
same handler, so a fan-out would only cost every *other* feature a needless `apply_settings` +
re-push, at pointer rate during a live drag. `persist=False` (every mousemove) only updates the
in-memory value; `persist=True` (mouseup) additionally writes it through MSA so the panel
steppers track the drag and it survives the session.

Because a stepper edit or a panel Reset changes the stored value **without** going through
`set_bar_position`, `battle_bridge.apply_settings()` calls `progress_view.apply_position()` /
`efficiency_view.apply_position()` (thin aliases for `bar_window.BarHost.apply_position`) on
every settings change, so either path — drag or panel — moves the live bar.

### `_checkbox` / `_radio` / `_label` all omit a FALSY tooltip

All three descriptor helpers end with `tooltip = rendered.get("tooltip"); if tooltip: …`.
`_checkbox` used to hard-index `rendered["tooltip"]` and raised **`KeyError` inside `_template()`**
— i.e. inside `register()`'s guarded `try`, so the live symptom was **a client with no settings
panel at all** plus one logged traceback. The trigger is the **first label-only control of a given
TYPE**, which the Transitions children are, and (as of v18) the "Layout" (`catBarPosition`)
steppers are the first tipless `NumericStepper`s. Emitting `u""` is not a fix: `_sync_template_text`
only overwrites, never deletes. The tripwire is the exact `tipless == 8` counter in
`tests/test_mod_settings.py::test_sync_template_text_walks_built_template_in_lockstep` — the four
bare category headers (Battle Calculator / Battle Progress / Transitions / Garage Widget), the
Transitions group's two children (Events / Alt Press), and the two "Layout" steppers (`barPosX` /
`barPosY` — the header above them carries the Ctrl+drag tooltip instead, so the header itself is
NOT in this count; the v21 Orientation/Alignment radios both carry their own tooltip, so they
don't add to `tipless` either) — alongside `spacers == 7` (v21, grew from 6) for the
`None`-sentinel `Empty` rows.

The getters import NOTHING from the sibling bridges, so `gameface_bridge` / `battle_bridge` read
them without a cycle. Live state seeds from MSA in `register()`; defaults until then / if MSA absent.

## The non-bool settings: four radios + one slider

`progress_bar_variant`, `progress_bar_size`, and (as of v21) `progress_bar_orientation` /
`progress_bar_alignment` are the mod's **only** settings that are not plain bools, alongside the
`progress_hold_seconds` slider (a clamped int, not an index). MSA's `RadioButtonGroup` stores its
`value` as a **0-based option INDEX**:

- `PROGRESS_VARIANT_EFFICIENCY = 0` (the default), `PROGRESS_VARIANT_MOVING_AVERAGE = 1`.
  ⚠️ **The order FLIPPED in v13** and the stored raw int rides across **unchanged**, so an existing
  user's chosen bar swaps exactly once, silently — accepted deliberately, with no migration (one
  keyed on the old order would be indistinguishable from a fresh `0`);
- `PROGRESS_SIZE_DEFAULT = 0` (the shipped size), `PROGRESS_SIZE_LARGE = 1`;
- `PROGRESS_ORIENT_HORIZONTAL = 0` (the default — every existing user keeps it), `PROGRESS_ORIENT_VERTICAL = 1` (v21);
- `PROGRESS_ALIGN_DAMAGE_LOG = 0` (the default — every existing user keeps it), `PROGRESS_ALIGN_MINIMAP = 1`, `PROGRESS_ALIGN_FREE = 2` (v21).

`clamp_variant(v, max_index=PROGRESS_VARIANT_MOVING_AVERAGE)` is **shared** by all four radios;
each passes its own ceiling. `_coerce(key, value)` is a **six-way branch**, and the order matters:

```python
if key in _POS_KEYS:                 return clamp_pos(value)                       # px ints
if key == PROGRESS_VARIANT_KEY:      return clamp_variant(value)                   # radio index
if key == PROGRESS_SIZE_KEY:         return clamp_variant(value, PROGRESS_SIZE_LARGE)
if key == PROGRESS_ORIENTATION_KEY:  return clamp_variant(value, PROGRESS_ORIENT_VERTICAL)
if key == PROGRESS_ALIGNMENT_KEY:    return clamp_variant(value, PROGRESS_ALIGN_FREE)
if key == PROGRESS_HOLD_SECONDS_KEY: return clamp_hold_seconds(value)              # 1-30 int
return bool(value)                                                                 # everything else
```

Falling through to `bool()` would turn index `1` into `True`, round-trip that bool back into MSA
and destroy the setting. **`clamp_variant` must test `isinstance(v, bool)` FIRST** — `bool` is an
`int` subclass, so a plain `int()` silently passes `True` through as a legal `1`. Anything
non-numeric / negative / out-of-range / boolean falls back to `0` — the safe choice for all four
radios, since index 0 is in each case the behaviour the bar always had (or the "revert to
Horizontal / Damage Log" fallback for the two new ones). All four getters
(`progress_bar_variant()`, `progress_bar_size()`, `progress_bar_orientation()`,
`progress_bar_alignment()`) **re-clamp on read** (like the position getters), so a corrupt store
can never leak a bool or a stray index into the window picker or the widget.

`_radio()` (used for **all four** radios) builds the MSA descriptor dict **by hand** — the same shape
`templates.createRadioButtonGroup` emits (`type` / `text` / `varName` / `value` / `inline` /
`options`, plus `tooltip` only when there is one), verified against the decompiled vendored
`templates.pyc`. Two reasons, both load-bearing:

- `_template()` stays a pure, unit-testable dict with **no `gui.aslainMenu` import**;
- **`inline: True` is emitted as a plain KEY, never through the helper's `inline` KWARG.** The
  kwarg raises `TypeError` on MSA < 1.6.1; an unknown *key* just rides through, because MSA does
  no descriptor validation at all. So the repo gets the one-horizontal-row layout — which is what
  lets each standalone radio (2-option or, for Alignment, 3-option) cost one row instead of one
  stacked row per option — with the version floor structurally impossible.

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

- **Option labels live in `settings_i18n._VARIANT_OPTIONS` / `_SIZE_OPTIONS` / `_ORIENTATION_OPTIONS`
  / `_ALIGNMENT_OPTIONS`** (the last two added at v21), `{lang: (opt0, opt1[, opt2])}` tables that
  must stay **BESIDE `_PANEL`, never inside it** — `_PANEL`'s keys are partitioned **positionally**
  by `COL1_KEYS` / `COL2_KEYS`, and an option tuple is not a label/tooltip row. `build()` attaches
  each tuple onto the rendered `VARIANT_KEY` / `progressSize` / `progressOrientation` /
  `progressAlignment` entry, where `_radio()` reads it. Fallback is **whole-tuple, not per-option**
  (the set's meaning is positional, so half-English is worse than all-English).
- Those labels are **STRUCTURAL to MSA**: Aslain folds the option tuple into `_settingsStructure`,
  and `_sync_template_text` rewrites only `text` / `tooltip` — **never `options[].label`**. So
  adding, removing, or merely re-wording/re-localizing an option reaches an existing install
  **only** through a `SETTINGS_VERSION` bump. Unlike every other string in `settings_i18n`. The
  v21 Orientation/Alignment options got their order right at introduction — see
  `[[reordering-a-radio-groups-options-is-a-silent-value-migration]]` for why there's no cheap fix
  later.
- **RESOLVED — all four radios are normal `_PANEL` rows** with real labels ("Mode", "Scale",
  "Orientation", "Alignment"). v10 had blanked the variant radio's label (`_row(u"")`) so its
  options read as direct children of the Progress Bar checkbox; v13 made Mode/Scale standalone
  `inline` controls, so each needed its own name back, and Orientation/Alignment were introduced
  standalone from the start at v21. `build()` no longer synthesises a blank entry for `VARIANT_KEY`
  — it only bolts the option tuple onto the rendered row. **All four radios now carry a real
  tooltip** (a later maintainer override waived the "options say it all, so leave it tipless"
  invariant a prior test pass had protected) — Mode/Scale explain something the option words don't
  already say (timing, or Scale's meaning at all since nothing else in the panel spells it out),
  and Orientation/Alignment do the same. None of the four radios contribute to `tipless`; see the
  `tipless == 8` breakdown above.
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
`_sync_template_text` walk in lockstep — **26** and **9** slots (v21, `COL1_KEYS` grew from 24),
several of which are `None` sentinels for the `Empty` spacers. 11 language blocks. The six
`HEADER_KEYS` entries come out of
`build()` pre-wrapped in `<b>...</b>` — see the `HEADER_KEYS` section above for why that wrap must
live nowhere else.
`modDisplayName` stays the literal English brand. THE gotcha — MSA caches a COPY of the template
text at registration, so on an EXISTING install a client-language change never shows unless
`_sync_template_text` rewrites the stored template text in place (text-only, NO `settingsVersion`
bump) — is the harness rule; see `wotmod-i18n-settings` for the full mechanism and the
`uk`-not-`ua` EU quirk.

**Two mod-specific exceptions to "text is free":** all four radios' **option labels** are
structural (bump-only — see above), and **deleting** a text key (blanking a label) needs a bump too
because `_sync_template_text` overwrites but never removes. Renaming a **`varName`** is never free
either: `merge_settings` / `_apply` iterate `DEFAULTS` keys only with no rename/alias map, so a
rename silently resets every existing user's value. Rename the label, keep the key forever —
`progress_bar_enabled` is the shipped precedent (label went "Next Mark Progress Bar" → "Progress
Log" → "Progress Bar" → "Show"; the key never moved) — and `catBarPosition`'s header text going
"Bar Position" → "Layout" at v21 is the same move on a header key.

## Tests that guard this subsystem

Engine-free pytest (Python 3.13) — run the suite per `moe-build-release`:

- `tests/test_mod_settings.py` — `_coerce` / `clamp_variant` / `merge_settings` / `_apply`, the
  built template's per-column type + `varName` order, the label-only-tooltip regressions, and the
  `tipless == 8` / `spacers == 7` lockstep walk (the spacer branch also asserts the `None`-sentinel
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
