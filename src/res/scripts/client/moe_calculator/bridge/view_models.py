# -*- coding: utf-8 -*-
"""Wulf ViewModel definitions for the widget's data channel.

Two models: MarkTickVM (one milestone tick) and MoEVM (the root model exposed as
`moeData`, holding the scalar fields + the ticks array). v1 is read-only, so there are
no reverse-channel commands.

IMPORTANT -- the numeric property indices below are HAND-MAINTAINED and MUST match the
_addXProperty registration order: `_setNumber(i, v)` / `_setString(i, v)` address the
i-th registered property, so reordering or inserting a property without renumbering
every setter silently mismaps fields. The JS reader reads these by NAME, so the names
are the contract with the widget. PC-only (needs the live frameworks.wulf).
"""
from frameworks.wulf import ViewModel, Array


class MarkTickVM(ViewModel):
    def __init__(self, properties=4, commands=0):
        super(MarkTickVM, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(MarkTickVM, self)._initialize()
        self._addNumberProperty("percent", 0)          # 0  fixed axis position 65/85/95
        self._addNumberProperty("markCount", 0)        # 1  1/2/3
        self._addNumberProperty("damageRequired", 0)   # 2  combined dmg for this mark (0 = unknown)
        self._addBoolProperty("reached", False)        # 3  player already holds this mark
        # NOTE: no per-tick `icon` property -- the widget draws a flat, nation-agnostic glyph
        # (MoECalculator.js FLAT_MARK) for every tick, so the old nation-art URL was dead.

    def setPercent(self, v):
        self._setNumber(0, v)

    def setMarkCount(self, v):
        self._setNumber(1, v)

    def setDamageRequired(self, v):
        self._setNumber(2, v)

    def setReached(self, v):
        self._setBool(3, v)


class MoEVM(ViewModel):
    def __init__(self, properties=18, commands=1):
        super(MoEVM, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(MoEVM, self)._initialize()
        self._addBoolProperty("visible", True)         # 0  false hides the bar
        self._addStringProperty("nation", "")          # 1  nation id ('germany', ...)
        self._addNumberProperty("marks", 0)            # 2  current marks 0..3
        self._addRealProperty("curPercent", 0.0)       # 3  current percentile (float -- MUST be Real:
                                                       #    _setNumber casts to int() and drops the decimals)
        self._addNumberProperty("curAvgDamage", 0)     # 4  current moving-avg combined dmg
        self._addRealProperty("fill", 0.0)             # 5  bar fill 0..100 (== curPercent; Real for a
                                                       #    smooth sub-percent edge, same int() reason)
        self._addBoolProperty("hasData", False)        # 6  external thresholds loaded
        self._addNumberProperty("carouselRows", 1)     # 7  1 single / 2 double (positioning)
        self._addBoolProperty("carouselSmall", False)  # 8  double-row: small vs tall adaptive
        self._addArrayProperty("ticks", Array())       # 9  [MarkTickVM] * 3, ascending
        self._addNumberProperty("endDamageRequired", 0)  # 10  100th-pct dmg goalpost (0 = unknown)
        self._addStringProperty("labels", "")          # 11  JSON {key: localized text} for the tooltip
        # --- drag-to-reposition channel (APPENDED after the 12 v1 read props so the JS's
        # name/index reads of 0..11 don't shift). posX/posY = the widget's top-LEFT px anchor
        # (0 = auto: keep the CSS bottom-right default). posW/posH = the viewport px the pin was
        # captured at, so a resolution / UI-scale change rescales it proportionally (see
        # applyPosition in MoECalculator.js). followCarousel = ride the carousel's vertical
        # shifts even after a pin (default True). Echoed every push; written back via setPosition. ---
        self._addNumberProperty("posX", 0)             # 12  top-left x px (0 = auto/CSS default)
        self._addNumberProperty("posY", 0)             # 13  top-left y px (0 = auto/CSS default)
        self._addNumberProperty("posW", 0)             # 14  viewport px a pinned pos was captured at
        self._addNumberProperty("posH", 0)             # 15  viewport px a pinned pos was captured at
        self._addBoolProperty("followCarousel", True)  # 16  keep riding carousel vertical shifts
        # Monotonic per-push counter (APPENDED last so the JS's name/index reads of 0..16 don't
        # shift). On a freshly-mounted (cold) subview the engine withholds the data-changed event
        # until the view next composites (in an idle garage: only when the camera moves), so the JS
        # ModelObserver never fires and a reset / stepper-to-0 position push is dropped -- the widget
        # stays pinned. The widget polls this `rev` as a cheap change-signal and re-renders when it
        # moves (cold-mount self-heal; see pollForChanges in MoECalculator.js).
        self._addNumberProperty("rev", 0)              # 17  push counter (bumped FIRST every push)
        # Reverse channel: the JS drag/stepper reports the final px here. Wulf delivers the
        # JS-supplied {x, y, w, h} MAP to the handler wired in gameface_bridge._connect_commands.
        self.setPosition = self._addCommand("setPosition")  # arg: {x, y, w, h} px (drag / rescale echo)

    def setVisible(self, v):
        self._setBool(0, v)

    def setNation(self, v):
        self._setString(1, v)

    def setMarks(self, v):
        self._setNumber(2, v)

    def setCurPercent(self, v):
        self._setReal(3, v)

    def setCurAvgDamage(self, v):
        self._setNumber(4, v)

    def setFill(self, v):
        self._setReal(5, v)

    def setHasData(self, v):
        self._setBool(6, v)

    def setCarouselRows(self, v):
        self._setNumber(7, v)

    def setCarouselSmall(self, v):
        self._setBool(8, v)

    def setEndDamageRequired(self, v):
        self._setNumber(10, v)

    def setLabels(self, v):
        self._setString(11, v)

    def setPosX(self, v):
        self._setNumber(12, v)

    def setPosY(self, v):
        self._setNumber(13, v)

    def setPosW(self, v):
        self._setNumber(14, v)

    def setPosH(self, v):
        self._setNumber(15, v)

    def setFollowCarousel(self, v):
        self._setBool(16, v)

    def setRev(self, v):
        self._setNumber(17, v)

    def getTicks(self):
        return self._getArray(9)

    @staticmethod
    def getTicksType():
        return MarkTickVM


class BattleMoEVM(ViewModel):
    """Root model for the in-battle overlay. It IS the registered MoEBattleView's own root
    ViewModel (the JS reads it with a root ModelObserver(), NOT via a nested submodel).
    Flat (no ticks array) -- the four readouts + gating flags. Read-only (no reverse-channel
    commands). Indices are hand-maintained to match the _addXProperty order; JS reads by NAME."""
    def __init__(self, properties=10, commands=0):
        super(BattleMoEVM, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(BattleMoEVM, self)._initialize()
        self._addBoolProperty("visible", False)          # 0  false hides the overlay
        self._addNumberProperty("combinedDamage", 0)     # 1  live CD this battle
        self._addNumberProperty("projAvgDamage", 0)      # 2  EWMA-projected avg incl. this CD
        self._addRealProperty("curPercent", 0.0)         # 3  MoE percentile of the projection (float --
                                                         #    MUST be Real: _setNumber casts to int())
        self._addRealProperty("pctDelta", 0.0)           # 4  signed delta vs pre-battle standing (float, Real)
        self._addBoolProperty("hasData", False)          # 5  threshold table usable (percent real)
        self._addBoolProperty("hasBaseline", False)      # 6  career baseline present; false (replay/
                                                         #    relogin) -> proj/percent/delta dashed out
        self._addNumberProperty("countedAssist", 0)      # 7  counted assistance = max(track, spot, stun)
        self._addStringProperty("assistKind", "assist")  # 8  which stream leads: track|spot|stun|assist
                                                         #    (selects the third-row icon)
        self._addBoolProperty("assistVisible", False)    # 9  "Enable Counted Assistance" setting; JS also
                                                         #    hides the row while countedAssist == 0

    def setVisible(self, v):
        self._setBool(0, v)

    def setCombinedDamage(self, v):
        self._setNumber(1, v)

    def setProjAvgDamage(self, v):
        self._setNumber(2, v)

    def setCurPercent(self, v):
        self._setReal(3, v)

    def setPctDelta(self, v):
        self._setReal(4, v)

    def setHasData(self, v):
        self._setBool(5, v)

    def setHasBaseline(self, v):
        self._setBool(6, v)

    def setCountedAssist(self, v):
        self._setNumber(7, v)

    def setAssistKind(self, v):
        self._setString(8, v)

    def setAssistVisible(self, v):
        self._setBool(9, v)


class ProgressVM(ViewModel):
    """Root model for the centre-screen transient MoE progress bar (MoEProgressView).

    Its OWN model, not an extension of BattleMoEVM: all ten of that model's slots are in use and
    the bar needs almost none of them (it works in COMBINED DAMAGE along the mark axis, not in
    percentiles). Like BattleMoEVM this IS the registered view's root ViewModel -- the JS reads it
    with a bare ModelObserver() and no unwrap. READ-ONLY, like BattleMoEVM: the Ctrl+drag reposition
    is driven entirely from Python now (adapter/battle_input samples the keys, bar_window re-places
    the window absolutely from the live cursor), so the `setPosition` reverse command this model used
    to carry is gone and `commands` is back to 0. Nothing else ever used it -- the settings panel's
    position steppers write mod_settings directly.

    Deliberately NO `rev` push counter: the battle window is a private, always-compositing view
    (never a cold hangar sub-view), so it has never needed the garage's cold-mount change signal.
    The "did anything actually change?" test that decides whether to replay the transient is done
    JS-side by comparing the previously pushed values -- see MoEProgress.js.

    Indices are hand-maintained to match the _addXProperty order; the JS reads by NAME. The two
    axis ends AND projAvg are Real: _setNumber casts to int(), which would round a requirement off
    and -- far worse for projAvg -- destroy the whole signal. projAvg moves by k * combined_damage
    (k ~= 0.02), so a full battle's worth of damage shifts it by a couple of DAMAGE POINTS; the JS
    change-detect compares pushed values, so an int() there quantised almost every real update away
    and the bar essentially never showed. MoEProgress.js's fmt() rounds for display."""

    def __init__(self, properties=16, commands=0):
        super(ProgressVM, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(ProgressVM, self)._initialize()
        self._addBoolProperty("visible", False)      # 0  false -> the bar never appears
        self._addNumberProperty("marks", 0)          # 1  marks held 0..3 (selects the end glyphs)
        self._addRealProperty("axisLo", 0.0)         # 2  the DISPLAY floor: where a zero-damage
                                                     #    battle lands (domain.progress_axis_lo), NOT
                                                     #    the held mark's requirement -- that segment
                                                     #    is far too wide for one battle to move
                                                     #    visibly. The JS paints no mark glyph here
        self._addRealProperty("axisHi", 0.0)         # 3  requirement CHASED (the 100 stop at 3 marks)
        self._addNumberProperty("preAvg", 0)         # 4  career moving-avg combined damage
        self._addRealProperty("projAvg", 0.0)        # 5  the same, with this battle folded in (EWMA).
                                                     #    Real, NOT Number: the per-battle nudge is a
                                                     #    few damage points, so int() quantised the
                                                     #    JS change-detect signal away entirely
        self._addBoolProperty("hasData", False)      # 6  the MARK axis is usable -- mark_axis's own
                                                     #    verdict, which axisLo's display floor
                                                     #    deliberately does not get to change
        self._addBoolProperty("altHeld", False)      # 7  Alt currently down -> pull the bar up and
                                                     #    hold it (an ADDITIVE show trigger, not a gate)
        self._addNumberProperty("barSize", 0)        # 8  mod_settings.progress_bar_size(): 0 = the
                                                     #    shipped size, 1 = LARGE (x5/3 wide, x1.25
                                                     #    tall, fonts + icons x1.25). APPENDED, so
                                                     #    nothing above is renumbered. The JS turns it
                                                     #    into a 1.25x ROOT FONT, the .mp-lg body class and a
                                                     #    re-derived surface push
                                                     #    (MoEBarTransient.applySize); Python's half
                                                     #    is PROGRESS_ANCHOR_Y_SHIFT_LARGE
        self._addBoolProperty("transEvents", True)    # 9  animate the enter/exit when a BATTLE EVENT
                                                     #    pulls the bar up / lets it go. APPENDED.
                                                     #    The MASTER checkbox is already folded in by
                                                     #    mod_settings.progress_transitions_events(),
                                                     #    so the JS never sees it -- false here means
                                                     #    "instant", full stop. Default True == what
                                                     #    shipped (an animated bar)
        self._addBoolProperty("transManual", True)    # 10 the same for the ALT PEEK's enter/exit
                                                     #    (progress_transitions_manual())
        self._addBoolProperty("showEvents", True)     # 11 may a BATTLE EVENT raise the bar at all
                                                     #    (mod_settings.progress_show_events, with
                                                     #    "Always" already folded in). APPENDED.
                                                     #    A DIFFERENT axis from transEvents above:
                                                     #    this is WHETHER it comes up, that one is
                                                     #    only HOW it moves. The other two
                                                     #    visibility switches need no field --
                                                     #    "Alt Press" and "Always" are both folded
                                                     #    into `altHeld` by
                                                     #    mod_settings.progress_alt_held(), because
                                                     #    a permanently-held Alt IS "Always"
        self._addNumberProperty("holdMs", 5000)        # 12 how long the bar stays up once it is up,
                                                     #    in MS (mod_settings.progress_hold_seconds
                                                     #    * 1000). APPENDED. NOT master-folded --
                                                     #    a duration, not a switch. The default IS
                                                     #    MoEBarTransient's baked HOLD_MS, and the
                                                     #    JS reads an absent field as that same
                                                     #    5000 rather than 0 (fail soft toward the
                                                     #    SHIPPED bar)
        self._addBoolProperty("ctrlHeld", False)      # 13 Ctrl currently down -> the bar HOLDS ITSELF
                                                     #    UP for the reposition gesture, exactly like
                                                     #    altHeld (you cannot grab a bar that has
                                                     #    faded out). APPENDED. NOT settings-folded:
                                                     #    it is a raw key state, not a switch. The JS
                                                     #    reads it as `=== true` -- absent must mean
                                                     #    NOT held, or an unpushed frame would peek
                                                     #    forever and the bar would never come down.
                                                     #    It no longer opens an input hit rect: the
                                                     #    drag needs no mouse input in the document
                                                     #    at all, so that rect stays collapsed
        self._addNumberProperty("etaBattles", -1)     # 14 repeats of THIS battle needed to reach
                                                     #    axisHi (domain.battles_to_axis_hi): a
                                                     #    positive count, 0 once the requirement is
                                                     #    already met, -1 = no data. APPENDED.
                                                     #    Number, not Real -- it is an integer count
                                                     #    of battles. The JS appends it to the delta
                                                     #    caption and renders nothing below 1, so
                                                     #    the -1 default is also the safe absent
                                                     #    value
        self._addBoolProperty("vertical", False)      # 15 draw the VERTICAL composition instead of
                                                     #    the horizontal one
                                                     #    (mod_settings.progress_bar_orientation ==
                                                     #    PROGRESS_ORIENT_VERTICAL). APPENDED, and
                                                     #    the `properties=` count above is bumped
                                                     #    WITH it -- the fake VM in tests ignores
                                                     #    the declared count, so an append without
                                                     #    the bump is green in pytest and broken
                                                     #    live. A STATE bool, so the JS reads it
                                                     #    `=== true` (like ctrlHeld, NOT like the
                                                     #    transition switches' `!== false`): the
                                                     #    shipped composition is HORIZONTAL, so an
                                                     #    absent field must fail soft to it.
                                                     #    MoEProgress.js branches on it ONCE, at
                                                     #    mount -- it picks the DOM, the class
                                                     #    prefix and the surface size, not a style
                                                     #    -- so a live flip is delivered by Python
                                                     #    closing and reopening the window
                                                     #    (battle_bridge.apply_settings). Python's
                                                     #    placement half is already
                                                     #    orientation-aware (bar_window._resolve /
                                                     #    domain.VERTICAL_ANCHOR_Y_SHIFT)

    def setVisible(self, v):
        self._setBool(0, v)

    def setMarks(self, v):
        self._setNumber(1, v)

    def setAxisLo(self, v):
        self._setReal(2, v)

    def setAxisHi(self, v):
        self._setReal(3, v)

    def setPreAvg(self, v):
        self._setNumber(4, v)

    def setProjAvg(self, v):
        self._setReal(5, v)

    def setHasData(self, v):
        self._setBool(6, v)

    def setAltHeld(self, v):
        self._setBool(7, v)

    def setBarSize(self, v):
        self._setNumber(8, v)

    def setTransEvents(self, v):
        self._setBool(9, v)

    def setTransManual(self, v):
        self._setBool(10, v)

    def setShowEvents(self, v):
        self._setBool(11, v)

    def setHoldMs(self, v):
        self._setNumber(12, v)

    def setCtrlHeld(self, v):
        self._setBool(13, v)

    def setEtaBattles(self, v):
        self._setNumber(14, v)

    def setVertical(self, v):
        self._setBool(15, v)


class EfficiencyVM(ViewModel):
    """Root model for the centre-screen DAMAGE EFFICIENCY bar (MoEEfficiencyView) -- the radio
    alternative to the Moving Average bar above.

    Its OWN model, and ProgressVM is deliberately left untouched: that bar's two-end mark axis
    (axisLo/axisHi) must keep working byte-identically, while this one plots THIS BATTLE's
    combined damage against ALL FOUR requirements at once, so it needs four axis stops rather
    than two. Like the other two battle models this IS the registered view's root ViewModel (the
    JS reads it with a bare ModelObserver() and no unwrap). READ-ONLY -- see ProgressVM on why the
    `setPosition` reverse command is gone and `commands` is 0; no `rev` counter for the same reason
    as ProgressVM (a private, always-compositing battle view).

    THE FOUR REQUIREMENT STOPS ARE Real, NOT Number: _setNumber casts to int() (ProgressVM's
    docstring, and the same trap that quantised projAvg away), which would round a requirement
    off its exact WG value and shift every tick's axis arithmetic. barX is Real for a smooth
    sub-percent fill edge. `damage` / `band` are genuinely whole -> Number.

    NO `damageDelta`: the bar's "last increment" is derived and latched in MoEEfficiency.js off
    successive `damage` pushes (it already holds both values for its change-detect), so this model
    carries no state the bridge has to keep between pushes. Dropping it RENUMBERED every property
    after it -- barX 3->2 and so on down -- which is exactly the hand-maintained-index hazard this
    module's header warns about. `battleEpoch` is therefore APPENDED after altHeld rather than
    filed next to `damage` where it reads best: an append renumbers nothing.

    Indices are hand-maintained to match the _addXProperty order; the JS reads by NAME."""

    def __init__(self, properties=18, commands=0):
        super(EfficiencyVM, self).__init__(properties=properties, commands=commands)

    def _initialize(self):
        super(EfficiencyVM, self)._initialize()
        self._addBoolProperty("visible", False)     # 0  false -> the bar never appears
        self._addNumberProperty("damage", 0)        # 1  this battle's combined damage (int)
        self._addRealProperty("barX", 0.0)          # 2  `damage` on the axis, 0..100 % of the bar
                                                    #    (domain.efficiency_bar_x -- do NOT
                                                    #    recompute it in JS)
        self._addNumberProperty("band", 0)          # 3  0..4 highest requirement PASSED, `>=`
                                                    #    inclusive (domain.efficiency_band);
                                                    #    selects .mp-b-{w,g,t,v,au}
        self._addRealProperty("r65", 0.0)           # 4  requirement for 1 mark  (Real, not Number)
        self._addRealProperty("r85", 0.0)           # 5  requirement for 2 marks (Real)
        self._addRealProperty("r95", 0.0)           # 6  requirement for 3 marks (Real)
        self._addRealProperty("r100", 0.0)          # 7  the 100th-pct goalpost  (Real)
        self._addBoolProperty("hasData", False)     # 8  the five-stop axis is usable (all four
                                                    #    requirements present + ascending)
        self._addBoolProperty("altHeld", False)     # 9  Alt currently down -> pull the bar up and
                                                    #    hold it (ADDITIVE show trigger, not a gate)
        self._addNumberProperty("battleEpoch", 0)   # 10 a monotonic per-battle counter (NOT the
                                                    #    arenaUniqueID: _setNumber int-casts and a
                                                    #    64-bit arena id would be mangled). Only
                                                    #    needs to DIFFER between battles -- it is
                                                    #    MoEEfficiency.js's battle-boundary signal
                                                    #    for resetting its damage-delta latch
        self._addNumberProperty("barSize", 0)       # 11 mod_settings.progress_bar_size(): 0 = the
                                                    #    shipped size, 1 = LARGE (x5/3 wide, x1.25
                                                    #    tall, fonts + icons x1.25). APPENDED, so
                                                    #    nothing above is renumbered. Same wire meaning
                                                    #    as ProgressVM's -- the JS turns it into a
                                                    #    1.25x ROOT FONT, the .mp-lg body class, a
                                                    #    re-derived surface AND (this bar only) the
                                                    #    caption clamp's px<->rem factor
        self._addBoolProperty("transEvents", True)   # 12 animate the enter/exit when a BATTLE EVENT
                                                    #    pulls the bar up / lets it go. APPENDED.
                                                    #    Same wire meaning as ProgressVM's: the
                                                    #    Transitions MASTER is already folded in by
                                                    #    mod_settings.progress_transitions_events(),
                                                    #    so false here means "instant", full stop
        self._addBoolProperty("transManual", True)   # 13 the same for the ALT PEEK's enter/exit
                                                    #    (progress_transitions_manual())
        self._addBoolProperty("showEvents", True)    # 14 may a BATTLE EVENT raise the bar at all
                                                    #    (mod_settings.progress_show_events, with
                                                    #    "Always" already folded in). APPENDED.
                                                    #    Same wire meaning as ProgressVM's, and the
                                                    #    same DIFFERENT axis from transEvents: this
                                                    #    is WHETHER it comes up, that is only HOW.
                                                    #    "Alt Press" / "Always" ride on `altHeld`
                                                    #    (mod_settings.progress_alt_held)
        self._addNumberProperty("holdMs", 5000)      # 15 how long the bar stays up once it is up, in
                                                    #    MS (mod_settings.progress_hold_seconds *
                                                    #    1000). APPENDED. Same wire meaning as
                                                    #    ProgressVM's; NOT master-folded (a
                                                    #    duration, not a switch), and the default IS
                                                    #    MoEBarTransient's baked HOLD_MS
        self._addBoolProperty("ctrlHeld", False)    # 16 Ctrl currently down -> HOLD the bar up for
                                                    #    the reposition gesture (it opens no input
                                                    #    hit rect any more). APPENDED. Same wire
                                                    #    meaning as ProgressVM's, including the
                                                    #    `=== true` read on the JS side
        self._addBoolProperty("vertical", False)    # 17 draw the VERTICAL composition instead of the
                                                    #    horizontal one
                                                    #    (mod_settings.progress_bar_orientation ==
                                                    #    PROGRESS_ORIENT_VERTICAL). APPENDED, and the
                                                    #    `properties=` count above is bumped WITH it
                                                    #    -- the fake VM in tests ignores the declared
                                                    #    count, so an append without the bump is
                                                    #    green in pytest and broken live. Same wire
                                                    #    meaning as ProgressVM's, including the
                                                    #    `=== true` STATE-bool read: the shipped
                                                    #    composition is HORIZONTAL. Branched on ONCE,
                                                    #    at mount (it picks the DOM, the class prefix
                                                    #    and the surface size, not a style), so a
                                                    #    live flip is delivered by Python closing and
                                                    #    reopening the window

    def setVisible(self, v):
        self._setBool(0, v)

    def setDamage(self, v):
        self._setNumber(1, v)

    def setBarX(self, v):
        self._setReal(2, v)

    def setBand(self, v):
        self._setNumber(3, v)

    def setR65(self, v):
        self._setReal(4, v)

    def setR85(self, v):
        self._setReal(5, v)

    def setR95(self, v):
        self._setReal(6, v)

    def setR100(self, v):
        self._setReal(7, v)

    def setHasData(self, v):
        self._setBool(8, v)

    def setAltHeld(self, v):
        self._setBool(9, v)

    def setBattleEpoch(self, v):
        self._setNumber(10, v)

    def setBarSize(self, v):
        self._setNumber(11, v)

    def setTransEvents(self, v):
        self._setBool(12, v)

    def setTransManual(self, v):
        self._setBool(13, v)

    def setShowEvents(self, v):
        self._setBool(14, v)

    def setHoldMs(self, v):
        self._setNumber(15, v)

    def setCtrlHeld(self, v):
        self._setBool(16, v)

    def setVertical(self, v):
        self._setBool(17, v)
