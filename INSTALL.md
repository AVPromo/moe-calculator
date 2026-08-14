# 14th_ua's MoE Calculator — Installation Guide

A World of Tanks mod that tracks your **Marks of Excellence (MoE)** progress for the
selected vehicle:

- **In the Garage** — a percentile bar with the 1 / 2 / 3-mark milestones (65% / 85% /
  95%), the combined damage each mark needs, and your current average combined damage and
  mark percentage. **Ctrl+drag** it to move it anywhere on screen (**Shift** locks the drag
  to one axis).
- **In battle** — a small overlay over the HUD showing your live combined damage against
  your projected average, and your projected MoE percentage with the change versus where
  you started the battle.
- **In battle, centre screen** *(off by default)* — a transient progress bar that fades in,
  holds for a few seconds (five by default, adjustable) and fades out on its own; **hold Alt**
  to bring it up at any time. Two mutually exclusive variants: **Damage Efficiency** *(default)*
  (this battle's damage against the 65 / 85 / 95 / 100 % requirements) or **Moving Average**
  (your projected average between the mark you hold and the next mark's requirement, plus this
  battle's contribution and an ETA in battles to the next mark). Turn it on in Settings, where
  three switches also control when it comes up (on events, on Alt, or always). **Ctrl+drag** it
  to reposition it — shared by both variants.

It uses the game's own mark art.

---

## Requirements

| Requirement | Detail |
|-------------|--------|
| **Game** | World of Tanks **EU (Wargaming)** client, version **2.3.1.2**. Built and tested against this version. |
| **Dependency** | **OpenWG GameFace** (required). The installer sets this up for you; for a manual install you add it yourself. |
| **Optional** | **ModsSettingsAPI** — adds the in-game settings panel: the Garage and Battle widgets on/off, the centre-screen progress bar and its variant, and the Garage widget's position. The installer adds it if missing; without it the mod still runs with both widgets enabled and the progress bar off. |

---

## Install with the installer (recommended)

1. Close World of Tanks completely (exit the Game Center launcher too).
2. Run **`MoECalculator-Setup-3.0.0.exe`**.
3. Confirm your World of Tanks folder when the installer shows it — the folder that
   contains `version.xml`. The installer detects it automatically in most cases.
4. If a newer version is available on GitHub, the installer offers to download and run the
   latest installer for you — accept to always get the newest build.
5. The installer adds OpenWG GameFace (and ModsSettingsAPI, for the settings panel) when
   your client doesn't already have them, then installs the mod into `mods\<version>\`.
6. Start the game and go to the Garage.

To remove the mod later, use its entry in Windows **Apps & features**, or re-run the
installer. OpenWG GameFace and ModsSettingsAPI stay in place for other mods that use them.

---

## Manual install

1. Get **OpenWG GameFace** from the official WG mod portal (**wgmods.net**) or the OpenWG
   project's GitLab releases, and install its `.wotmod` into your game's `mods\<version>\`
   folder. If you already run other GameFace mods you likely have it.
2. Open your World of Tanks folder and the version-matched mods folder inside it:

   ```
   <World of Tanks>\mods\2.3.1.2\
   ```

   The folder name matches your installed client version. After a game update the version
   changes and you move the mod into the new version folder.

3. Copy **`com.14th_ua.moe_calculator_3.0.0.wotmod`** into that folder.
4. Delete any older version of this mod from the same folder first.
5. *(Optional)* Add **ModsSettingsAPI** (`aslain.modssettingsapi`) into the same folder to
   get the in-game settings panel. Without it the mod runs with both widgets enabled.
6. Fully restart the game client: exit completely and relaunch.

The `mods\2.3.1.2\` folder then holds the OpenWG GameFace `.wotmod`,
`com.14th_ua.moe_calculator_3.0.0.wotmod`, and (optionally) the ModsSettingsAPI `.wotmod`.

---

## Verifying it works

1. Launch the game and go to the **Garage**.
2. Select a vehicle. The MoE bar appears in the vehicle-parameters area, with the 1 / 2 /
   3-mark milestone ticks and your current average combined damage and mark percentage.
3. Enter a battle — the in-battle overlay appears over the HUD and updates live as you deal
   damage.

---

## Settings

With **ModsSettingsAPI** installed, open the in-game **Modification list** window (added by
the bundled Mods List API) and find **14th_ua's MoE Calculator**. The panel has two columns,
each grouped into named categories; a feature's own on/off switch is simply labelled
**Enabled**.

**Column 1 — in battle:**

- **Battle Calculator** — **Enabled** *(on)* controls the overlay over the HUD. Its children
  are only available while it's on:
  - **Alt Press** *(off)* — show the overlay only while **Alt** is held.
  - **Counted Assistance Row** *(on)* — add a third overlay row with your counted assistance.
- **Battle Progress** — **Enabled** *(off)* controls the transient centre-screen bar, a
  separate feature from the Battle Calculator, so it works whether that one is on or off:
  - **Events** / **Alt Press** / **Always** *(on / on / off)* — three switches deciding
    *when* the bar comes up: on a tracked battle event, while Alt is held, or permanently
    (which then greys out the other two).
  - **Mode** — **Damage Efficiency** *(the default)* or **Moving Average**.
  - **Scale** — **Default** or **Large**.
  - **Transitions** — **Enabled** *(on)*, with **Events** / **Alt Press** children (whether
    the bar animates its entry/exit for each trigger, or appears and disappears instantly) and
    a **Hold Duration (s)** slider *(1–30, default 5)* for how long it stays up before fading.
  - **Bar Position** — **Horizontal (left X)** / **Vertical (top Y)** *(0 = auto)*, shared by
    both variants. **Ctrl+drag** the bar to set it.

**Column 2 — in the Garage:**

- **Garage Widget** — **Enabled** *(on)* controls the Garage percentile bar.
- **Layout** — the Garage widget's position:
  - **Follow Carousel Mode** *(on)* — a dragged widget keeps shifting vertically with the
    vehicle carousel so it never overlaps it. When off, it stays put.
  - **Horizontal (left X)** / **Vertical (top Y)** — where the widget is pinned, in pixels
    from the left / top screen edge. **Ctrl+drag** the widget to move it (**Shift** locks to
    one axis). **0 / 0** is the default bottom-right position, which the panel's per-mod
    **Reset** also restores.

Changes apply immediately.

---

## Troubleshooting

**The bar / overlay doesn't show up.**
- Confirm OpenWG GameFace is installed in the same `mods\<version>\` folder.
- Confirm the `.wotmod` is in the folder matching your client version (for example
  `mods\2.3.1.2\`).
- Check that no loose copy of the mod sits under `res_mods\<version>\scripts\client\`, which
  would override the packaged mod. Keep only the `.wotmod` in `mods\<version>\`.
- Fully restart the client after installing.

**A game update stopped it from working.**
- Game updates change the version folder. Move the `.wotmod` from the old `mods\<old-version>\`
  into the new `mods\<new-version>\`. A new client version may also need a rebuilt mod — check
  for an updated release.

**Special / event hangars.**
- The Garage bar may not appear in event / special hangars; it returns in the normal Garage.

---

## Uninstalling

Remove the mod through its Windows **Apps & features** entry, or delete
`com.14th_ua.moe_calculator_3.0.0.wotmod` from `mods\<version>\`, then restart the client.

---

*Mod by 14th_ua. Built for WoT EU 2.3.1.2.*
