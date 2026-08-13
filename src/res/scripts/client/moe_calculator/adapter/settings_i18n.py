# -*- coding: utf-8 -*-
"""Localize the mod's OWN settings-panel prose with bundled translation tables.

The ModsSettingsAPI panel (see ``bridge/mod_settings.py``) is the one user-facing
surface the mod can't localize through the game's resource strings: its checkbox
labels and tooltips are mod-invented prose with no in-game equivalent (unlike the widget
text, which ``adapter/i18n.py`` resolves by reusing WG's own strings -- see that module).
So we ship our own ``{lang: {key: entry}}`` tables and pick the block matching the client's
active language, exactly the pattern the wotmod-architecture skill recommends for a mod's
own strings. Mirrors the sibling Garage Progress Bar mod's ``settings_i18n`` mechanism.

Everything here is PURE and unit-tested EXCEPT ``client_language()`` -- the one call
that reads the engine (``helpers.getClientLanguage()``), guarded so the module still
imports (and the resolver still runs) under pytest with the game closed.

English (``_PANEL['en']``) is the always-complete master. Every other language is
overlaid onto it PER KEY: a key a language hasn't translated falls back to the English
text for that key alone (and is underscore-marked when ``i18n.MARK_UNTRANSLATED`` is on,
matching the widget's diagnostic). An unknown client code degrades to full English.

FOUR radios (``VARIANT_KEY`` = "Mode", ``progressSize`` = "Scale", ``progressOrientation`` =
"Orientation" and ``progressAlignment`` = "Alignment") are normal ``_PANEL`` rows; ``build()``
only bolts their language-dependent OPTION tuples (``_VARIANT_OPTIONS`` / ``_SIZE_OPTIONS`` /
``_ORIENTATION_OPTIONS`` / ``_ALIGNMENT_OPTIONS``) onto the rendered entry, where
``mod_settings._radio`` reads them. Those option-label tuples are STRUCTURAL to MSA -- Aslain
folds them into its ``_settingsStructure`` signature and ``_sync_template_text`` only ever
rewrites a stored control's ``text``/``tooltip``, never ``options[].label`` -- so reordering,
adding, removing or merely re-wording an option reaches an EXISTING install only through a
``mod_settings.SETTINGS_VERSION`` bump; get the order right the first time.

The panel is grouped into five CATEGORIES, each a label header row followed by that feature's
controls and separated by an ``Empty`` spacer row. Column 1 now holds the In-Battle Calculator
(``catBattleCalc``, with the calcPreview live preview Image after its controls) plus EVERY
garage-related group: the Garage Widget master (``catGarage``) and its "Layout" positioning group
(``positioning``), with the barPreview live preview Image closing the column (moved here from
column 2 as of ``mod_settings.SETTINGS_VERSION`` 26->27, so both previews sit together). Column 2
holds the WHOLE Progress Bar feature: ``catBattleProgress``, the standalone Mode/Scale radios,
``catTransitions`` and the Progress Bar's own "Layout" group (``catBarPosition``). A category row
carries no ``varName``,
and most are text-only (no tooltip -- their ``_row`` is a label alone and ``_render`` emits no
``tooltip`` key); ``catBarPosition`` is the exception, and carries the Ctrl+drag prose for the
label-only controls below it, exactly as column 1's "Layout" header (``positioning``) does for
its own pair. ``catBarPosition``'s own displayed LABEL is "Layout" (the i18n KEY is unchanged --
a rename buys nothing positionally; see ``mod_settings``'s SETTINGS_VERSION history) --
``positioning`` and ``catBarPosition`` are two DIFFERENT categories, now in different columns,
that merely share a display name.
Because the header names the feature, each feature's master checkbox is simply labelled
"Enabled" (was "Show"). ``build()`` wraps every category header (plus the "Layout" header --
see ``HEADER_KEYS``) in ``<b>...</b>``; ``mod_settings._label`` then only adds the matching
``useHTML`` key and never touches the text itself, so ``_template()`` and
``_sync_template_text()`` always compare byte-identical strings (see ``build()``'s docstring
for why that matters). The ``positionSub`` ("Position") row that heads the two steppers is
deliberately excluded from ``HEADER_KEYS``, so the weight difference reads as hierarchy. An
``Empty`` row has no text at all, so ``COL1_KEYS`` / ``COL2_KEYS`` give it a ``None`` sentinel
slot rather than a key -- see those tuples. A spacer also heads the standalone Mode / Scale
radios, the "Transitions" and "Layout" (``catBarPosition``) categories, the hold-duration Slider
itself (right after the Transitions group's two switch children) and the "Position" sub-label,
matching the existing category-separator spacers. The "Layout" category's own two standalone
radios (Orientation, Alignment) sit ABOVE its two X/Y steppers, both STANDALONE like every other
control in that category.

NOTE on terminology: the non-English blocks use each locale's natural wording for
"widget", "Garage", "battle" and "Marks of Excellence". The official Marks-of-Excellence
noun per language is still worth a spot-check against a running client before a release; the
mechanism supports any code and never breaks on an unverified one.

Ukrainian code CONFIRMED: the EU 2.3.0.1 client's ``#settings:LANGUAGE_CODE`` resolves to
``'uk'`` (verified against ``res/text/lc_messages/settings.mo`` + the client's own
``dog_tag_composer.SUPPORTED_LANGUAGES``, which lists ``'uk'``, never ``'ua'``). So the
``'uk'`` table key matches ``getClientLanguage()`` directly; the ``ua`` alias below never
fires on this client and is kept only as defense for an odd client build.
"""
from moe_calculator._compat import LOG_CURRENT_EXCEPTION
from moe_calculator.adapter import i18n

# The default client language + the value returned when the engine read fails.
DEFAULT_LANGUAGE = u"en"

# getClientLanguage() code quirks -> our table keys. The EU client returns 'uk' for
# Ukrainian (confirmed -- see module docstring), so this ua->uk alias is defensive only;
# extend if a client variant surfaces a non-standard code (Chinese/Portuguese, region suffix).
_ALIASES = {
    u"ua": u"uk",
}


def _norm(code):
    """Normalize a client language code to a table key (pure, engine-free).

    ``None``/empty -> u"". Otherwise lowercase, ``-`` -> ``_``, apply ``_ALIASES``, and
    if the full code isn't a known block fall back to the primary subtag
    (``"pt_br"`` -> ``"pt"``). The result is not guaranteed to be a ``_PANEL`` key --
    ``resolve`` treats an unknown key as "English"."""
    if not code:
        return u""
    c = code.strip().lower().replace(u"-", u"_")
    c = _ALIASES.get(c, c)
    if c in _PANEL:
        return c
    # Try the primary subtag (before the first "_"), also through the alias map.
    base = c.split(u"_", 1)[0]
    base = _ALIASES.get(base, base)
    return base


def _row(label, header=None, body=None):
    """A panel entry: a label plus an optional (header, body) tooltip. Parts are kept
    separate so the ``{HEADER}/{BODY}`` markup is assembled ONCE in ``_render`` rather
    than baked into every translation string."""
    e = {u"label": label}
    if header is not None or body is not None:
        e[u"ttHeader"] = header or u""
        e[u"ttBody"] = body or u""
    return e


# The panel key of the Progress Bar's variant radio ("Mode"). A normal _PANEL row like every other
# label; build() only bolts its option tuple on. Sole owner of the string, used by COL1_KEYS below,
# build() and mod_settings._radio.
VARIANT_KEY = u"progressVariant"

# The panel key of the in-battle per-vehicle mode-override hotkey control. A normal _PANEL row
# (label + tooltip, no options) -- mod_settings wires it into a template column and COL*_KEYS.
VARIANT_HOTKEY_KEY = u"variantHotkey"

# Ordered key list per column -- the wire order of the controls in the MSA template. Used by
# mod_settings to walk a stored template in lockstep.
#
# RESTRUCTURED: column 1 now holds the In-Battle Calculator group PLUS every garage-related
# group -- "Battle Calculator" (the In-Battle Widget master + its two children), a spacer, then
# "Garage Widget" (the standalone garage master, key catGarage -- no children of its own), a
# spacer, then the garage's "Layout" group (key positioning -- its bold header, Follow Carousel,
# a spacer, the non-bold "Position" sub-label, then the X/Y numeric steppers). Column 2 now holds
# the WHOLE Progress Bar feature, in its previous internal order: "Battle Progress" (the Progress
# Bar master + its three VISIBILITY children), a spacer, the standalone Mode and Scale radios, a
# spacer, "Transitions" (its own category header + master + two switch children), a spacer, the
# UNGROUPED hold-duration Slider, a spacer, and "Layout" (key catBarPosition, displayed text
# "Layout" -- its header, then the standalone Orientation and Alignment radios ABOVE the two
# standalone X/Y steppers that mirror the bar's Ctrl+drag). Only two columns -- a third does not
# render in the panel at all. No control was added, removed or renamed by this move -- see
# mod_settings's SETTINGS_VERSION history for why the reorder still owes a bump.
#
# EVERY control gets a slot, including the ones that carry no varName (the cat* headers) -- the zip
# in _sync_template_text is POSITIONAL, so a missing key here pairs every LATER control with the
# wrong text. A row with no text AT ALL (the Empty spacers) takes a `None` SENTINEL slot rather
# than a key: the sync walk's `if not rendered: continue` then skips it for free, with no
# type-sniffing branch and with the alignment intact.
#
# SIXTEEN slots (14 after the 23->24 column swap, +1 for the calcPreview Image's None sentinel at
# 24->25, +1 for the barPreview Image's trailing None sentinel moving in from column 2 at 26->27;
# see mod_settings's SETTINGS_VERSION history).
COL1_KEYS = (u"catBattleCalc", u"battleWidget", u"battleAltKey", u"countedAssist",
             None,                                   # calcPreview Image (no i18n text)
             None,                                   # Empty spacer
             u"catGarage", u"garageWidget",
             None,
             u"positioning", u"followCarousel",
             None,
             u"positionSub", u"posX", u"posY",
             None)                                   # barPreview Image (no i18n text)
# Column 2: the WHOLE Progress Bar feature (was column 1's tail), unchanged internally.
# TWENTY-THREE slots (21 after the 23->24 column swap, +1 for the variantHotkey HotKey control
# spliced in right after VARIANT_KEY at 25->26, +1 for the progressAutoToggleThreshold Slider
# spliced in right after it at 27->28; the barPreview Image's trailing None sentinel that briefly
# lived here at 24->25 MOVED to COL1_KEYS's tail at 26->27; see COL1_KEYS above).
COL2_KEYS = (u"catBattleProgress", u"progressBar",
             u"progressShowEvents", u"progressShowAlt", u"progressShowAlways",
             None,
             VARIANT_KEY, VARIANT_HOTKEY_KEY, u"progressAutoToggleThreshold", u"progressSize",
             None,
             u"catTransitions", u"progressTransitions",
             u"progressTransEvents", u"progressTransManual",
             None,
             u"progressHoldSeconds",
             None,
             u"catBarPosition", u"progressOrientation", u"progressAlignment",
             u"barPosX", u"barPosY")

# The six CATEGORY/GROUP header keys that render BOLD (see build()). "positionSub"
# ("Position") is deliberately EXCLUDED -- it is the non-bold sub-label under "Layout", and
# the weight difference is what makes the hierarchy read. "catBarPosition" IS bold: it is a
# column-1 CATEGORY in its own right, not a sub-level of the one above it.
HEADER_KEYS = frozenset((u"catBattleCalc", u"catBattleProgress", u"catTransitions",
                         u"catBarPosition", u"catGarage", u"positioning"))

# The variant radio's OPTION LABELS, in wire (index) order: 0 = Damage Efficiency (the default
# since v13), 1 = Moving Average (the original next-mark bar). THE ORDER FLIPPED in v13 and the
# stored raw int rides across unchanged, so an existing user's chosen bar swaps once -- see
# mod_settings.SETTINGS_VERSION. Its own table, not a _PANEL entry: an option tuple is not a
# label/tooltip row, and _PANEL's keys are partitioned POSITIONALLY by COL1_KEYS/COL2_KEYS.
#
# GOTCHA these labels are STRUCTURAL to MSA, not text: Aslain folds the option tuple into its
# _settingsStructure signature, and mod_settings._sync_template_text only ever rewrites a
# stored control's text/tooltip -- never options[].label. So adding, removing OR merely
# re-wording/re-localizing an option reaches an EXISTING install only through a
# mod_settings.SETTINGS_VERSION bump, unlike every other string in this module.
_VARIANT_OPTIONS = {
    u"en": (u"Damage Efficiency", u"Moving Average"),
    u"de": (u"Schadenseffizienz", u"Gleitender Durchschnitt"),
    u"fr": (u"Efficacité des dégâts", u"Moyenne glissante"),
    u"es": (u"Eficiencia de daño", u"Media móvil"),
    u"it": (u"Efficienza dei danni", u"Media mobile"),
    u"pl": (u"Efektywność obrażeń", u"Średnia krocząca"),
    u"cs": (u"Efektivita poškození", u"Klouzavý průměr"),
    u"ru": (u"Эффективность урона", u"Скользящее среднее"),
    u"uk": (u"Ефективність шкоди", u"Ковзне середнє"),
    u"hu": (u"Sebzéshatékonyság", u"Mozgóátlag"),
    u"tr": (u"Hasar verimliliği", u"Hareketli ortalama"),
}

# The size radio's OPTION LABELS, in wire (index) order: 0 = Default (the shipped size), 1 =
# Large. Same table shape, same whole-tuple fallback and the same STRUCTURAL-to-MSA gotcha as
# _VARIANT_OPTIONS above -- re-wording one needs a mod_settings.SETTINGS_VERSION bump. Unlike the
# variant radio this control DOES carry a label ("Size"), so it has a normal _PANEL row too.
_SIZE_OPTIONS = {
    u"en": (u"Default", u"Large"),
    u"de": (u"Standard", u"Groß"),
    u"fr": (u"Par défaut", u"Grande"),
    u"es": (u"Predeterminada", u"Grande"),
    u"it": (u"Predefinita", u"Grande"),
    u"pl": (u"Domyślna", u"Duża"),
    u"cs": (u"Výchozí", u"Velké"),
    u"ru": (u"Стандартный", u"Большой"),
    u"uk": (u"Стандартний", u"Великий"),
    u"hu": (u"Alapértelmezett", u"Nagy"),
    u"tr": (u"Varsayılan", u"Büyük"),
}

# The orientation radio's OPTION LABELS (v21), in wire (index) order: 0 = Horizontal (the shipped
# axis, the default), 1 = Vertical. Same table shape, same whole-tuple fallback and the same
# STRUCTURAL-to-MSA gotcha as _VARIANT_OPTIONS / _SIZE_OPTIONS above -- re-wording, reordering or
# adding an option here reaches an EXISTING install only through a mod_settings.SETTINGS_VERSION
# bump. Every language already has a plain "Horizontal"/"Vertical" adjective on hand (see
# posX/posY/barPosX/barPosY's axis-hint labels below), reused verbatim here.
_ORIENTATION_OPTIONS = {
    u"en": (u"Horizontal", u"Vertical"),
    u"de": (u"Horizontal", u"Vertikal"),
    u"fr": (u"Horizontale", u"Verticale"),
    u"es": (u"Horizontal", u"Vertical"),
    u"it": (u"Orizzontale", u"Verticale"),
    u"pl": (u"Pozioma", u"Pionowa"),
    u"cs": (u"Vodorovná", u"Svislá"),
    u"ru": (u"Горизонтальная", u"Вертикальная"),
    u"uk": (u"Горизонтальна", u"Вертикальна"),
    u"hu": (u"Vízszintes", u"Függőleges"),
    u"tr": (u"Yatay", u"Dikey"),
}

# The alignment radio's OPTION LABELS, in wire (index) order: 0 = Fixed (the default; v23
# COLLAPSED the old three options -- Damage Log / Minimap / Free -- into two, Fixed resolving
# INTERNALLY by Orientation, see bar_window.BarHost._resolve), 1 = Free (unchanged). Same table
# shape, same whole-tuple fallback and the same STRUCTURAL-to-MSA gotcha as the three option
# tables above -- and the SAME reordering hazard the v13 variant flip hit, so this table's own
# migration (mod_settings._migrate_pre_v23_alignment) maps the raw stored int explicitly rather
# than trusting a relabel.
_ALIGNMENT_OPTIONS = {
    u"en": (u"Fixed", u"Free"),
    u"de": (u"Fest", u"Frei"),
    u"fr": (u"Fixe", u"Libre"),
    u"es": (u"Fija", u"Libre"),
    u"it": (u"Fisso", u"Libero"),
    u"pl": (u"Stałe", u"Swobodne"),
    u"cs": (u"Pevné", u"Volné"),
    u"ru": (u"Фиксированная", u"Свободная"),
    u"uk": (u"Фіксована", u"Вільна"),
    u"hu": (u"Rögzített", u"Szabad"),
    u"tr": (u"Sabit", u"Serbest"),
}


# The translation tables, lang-major so each language is one contiguous, translator-
# editable block. 'en' is the master (every key present); the rest are overlaid per key.
_PANEL = {
    u"en": {
        # The three CATEGORY headers -- text only, no tooltip (a bare header row has nothing to
        # explain and nothing to hover). They name the feature, so each master below reads "Enabled".
        u"catGarage": _row(u"Garage Widget"),
        u"catBattleCalc": _row(u"Battle Calculator"),
        u"catBattleProgress": _row(u"Battle Progress"),
        u"garageWidget": _row(
            u"Enabled", u"In-Garage widget",
            u"Shows the Marks of Excellence percentile bar in the Garage, on the "
            u"selected vehicle. Uncheck to hide it."),
        u"battleWidget": _row(
            u"Enabled", u"In-Battle widget",
            u"Shows the live Marks of Excellence overlay during battle. Uncheck to "
            u"hide it and disable the options below."),
        u"battleAltKey": _row(
            u"Alt Press", u"Show on Alt key",
            u"Shows the in-battle overlay only while the Alt key is held. When off, the "
            u"overlay is shown at all times."),
        u"countedAssist": _row(
            u"Counted Assistance Row", u"Counted assistance",
            u"Adds a third row to the battle overlay showing your counted assistance: the "
            u"higher of tracking, spotting or stun assist, with an icon for whichever is "
            u"leading."),
        # The Progress Bar MASTER (its varName is still progress_bar_enabled -- only the label
        # changed). Its tooltip covers the bar itself and the two Mode/Scale radios below (both
        # still label-only rows); the three visibility children now carry their own tooltips
        # instead of being spelled out here (that sentence was dropped as redundant).
        u"progressBar": _row(
            u"Enabled", u"Progress bar",
            u"Shows a bar in the centre of the screen while you play, then fades it away on "
            u"its own. Hold Alt to bring it up at any time. Pick which bar below. "
            u"Damage Efficiency: marks your damage this battle against the requirements for "
            u"the 65 / 85 / 95 / 100 % marks. Moving Average: marks where your projected "
            u"average damage sits between the mark you hold and the next mark's requirement."),
        # The three VISIBILITY children -- when the bar comes up. Each now carries its own
        # tooltip (the master's used to spell all three out; that sentence was redundant once
        # these rows had their own prose, so it was dropped).
        u"progressShowEvents": _row(
            u"Events", u"Show on events",
            u"Raises the bar on its own whenever a tracked event happens in battle, then "
            u"fades it away again. Ignored while Always is on."),
        u"progressShowAlt": _row(
            u"Alt Press", u"Show on Alt key",
            u"Shows the bar only while you hold the Alt key. Ignored while Always is on."),
        u"progressShowAlways": _row(
            u"Always", u"Always show",
            u"Keeps the bar on screen permanently; it never fades. Overrides both switches "
            u"above, which grey out while this is on."),
        # Both radios now carry a tooltip too (maintainer override -- the "options say it all"
        # invariant a prior pass protected with a dedicated test is waived). Each adds INFO beyond
        # what's already said elsewhere rather than repeating it: progressBar's own tooltip above
        # already spells out what "Damage Efficiency" / "Moving Average" mean, so Mode's tooltip
        # covers WHEN a mode-switch takes effect instead; Scale has no explanation anywhere else in
        # the panel, so it explains the option words directly. Options themselves still come from
        # _VARIANT_OPTIONS / _SIZE_OPTIONS via build().
        u"progressVariant": _row(
            u"Mode", u"Bar mode",
            u"Switches between the two progress bars described above. Takes effect the next "
            u"time the bar comes up."),
        u"progressSize": _row(
            u"Scale", u"Bar scale",
            u"Default: the bar's normal size. Large: draws it bigger, for easier reading from "
            u"a distance."),
        # The two v21 radios: which axis the bar draws on, and which anchor the position
        # steppers below offset from. Both carry a tooltip, same reasoning as Mode/Scale above.
        u"progressOrientation": _row(
            u"Orientation", u"Bar orientation",
            u"Horizontal is the bar's original layout. Vertical draws it standing upright, "
            u"sized to sit beside the minimap. Takes effect the next time the bar comes up."),
        u"progressAlignment": _row(
            u"Alignment", u"Bar alignment",
            u"Which anchor the position steppers below offset from. Fixed: the bar's built-in "
            u"spot, chosen automatically by orientation -- horizontal sits centred at the "
            u"screen's bottom edge, above the damage log; vertical sits beside the minimap, near "
            u"its bottom-left corner, following the minimap's current size. Free: an unanchored "
            u"position, set automatically once you drag the bar or edit a stepper. Under Fixed "
            u"the position is locked; dragging and the steppers below only work under Free."),
        # The Transitions CATEGORY header (its own category since the hold-duration slider joined
        # the group) + the master, its two children and the slider. The two children stay
        # label-only rows whose meaning the master's prose spells out (no tt* -> _render emits no
        # tooltip key); the master now reads "Enabled" like every other master under a header.
        u"catTransitions": _row(u"Transitions"),
        u"progressTransitions": _row(
            u"Enabled", u"Bar transitions",
            u"The bar fades and slides as it appears and disappears. Uncheck this to make every "
            u"appearance instant instead, or turn off just one switch below. Events covers the "
            u"bar reacting to what happens in battle; Alt Press covers bringing it up with the "
            u"Alt key, matching the game's own interface, which does not animate on Alt."),
        u"progressTransEvents": _row(u"Events"),
        u"progressTransManual": _row(u"Alt Press"),
        u"progressHoldSeconds": _row(
            u"Hold Duration (s)", u"Hold duration",
            u"How long the bar stays on screen, in seconds, after an event raises it. Holding "
            u"Alt keeps it up for as long as the key is held, whatever this is set to. The fade "
            u"in and the fade out are not counted."),
        # --- drag-to-reposition group (translated across every shipped language; see COL2_KEYS). ---
        u"positioning": _row(
            u"Layout", u"Widget position",
            u"Ctrl+drag the Garage widget to move it (hold Shift to lock to one axis). The "
            u"steppers below show its pinned top-left position in pixels; 0 / 0 means the "
            u"default bottom-right position. Use the per-mod Reset to return to default."),
        # NEW info, not a repeat of "positioning"'s drag instructions or posX/posY's per-axis
        # tooltips: that both steppers apply the moment you change them.
        u"positionSub": _row(
            u"Position", u"Position steppers",
            u"Both steppers below apply immediately, without needing to drag the widget."),
        u"posX": _row(
            u"Horizontal (left X)", u"Horizontal position",
            u"The pinned widget's distance from the left screen edge, in pixels. 0 restores "
            u"the automatic bottom-right position."),
        u"posY": _row(
            u"Vertical (top Y)", u"Vertical position",
            u"The pinned widget's distance from the top screen edge, in pixels. 0 restores "
            u"the automatic bottom-right position."),
        # --- the IN-BATTLE bar's Ctrl+drag position (column 1's fourth category). The two
        # steppers are LABEL-ONLY rows -- their axis hint says it all and the header's
        # tooltip above carries the whole feature's prose, exactly like the Transitions
        # group's two switches. Labels deliberately mirror posX/posY's: the same two axes,
        # the same top-left reference corner, just a different widget. ---
        u"catBarPosition": _row(
            u"Layout", u"In-battle bar position",
            u"Hold Ctrl in battle and drag the bar to move it. The steppers below show where "
            u"it is pinned, in pixels from the top-left corner of the screen; 0 / 0 means the "
            u"default centred position. Use the per-mod Reset to return to default."),
        u"barPosX": _row(u"Horizontal (left X)"),
        u"barPosY": _row(u"Vertical (top Y)"),
        u"followCarousel": _row(
            u"Follow Carousel", u"Follow Carousel Mode",
            u"When on, a dragged widget keeps shifting vertically with the vehicle carousel "
            u"(single / double rows) so it never overlaps it. When off, a pinned widget stays "
            u"fixed regardless of the carousel."),
        u"variantHotkey": _row(
            u"Mode Override Key", u"In-battle mode override",
            u"The key you press in battle to switch this vehicle's progress-bar mode "
            u"between Damage Efficiency and Moving Average. The mod remembers each "
            u"vehicle's choice. After you switch, the bar reloads and reappears after "
            u"a few seconds. Default: K."),
        u"progressAutoToggleThreshold": _row(
            u"Automatic Mode Toggle", u"Automatic mode toggle",
            u"When a vehicle's mark progress reaches this percent before battle, its bar "
            u"mode switches automatically, the same as pressing the override key above. "
            u"Only fires once per vehicle. 100% turns this off."),
    },

    u"de": {
        u"catGarage": _row(u"Garage-Widget"),
        u"catBattleCalc": _row(u"Gefechtsrechner"),
        u"catBattleProgress": _row(u"Gefechtsfortschritt"),
        u"progressShowEvents": _row(
            u"Ereignisse", u"Bei Ereignissen anzeigen",
            u"Blendet die Leiste von selbst ein, sobald im Gefecht etwas Verfolgtes "
            u"passiert, und lässt sie danach wieder verschwinden. Wird ignoriert, solange "
            u"Immer aktiv ist."),
        u"progressShowAlt": _row(
            u"Alt drücken", u"Auf Alt-Taste anzeigen",
            u"Zeigt die Leiste nur, solange die Alt-Taste gehalten wird. Wird ignoriert, "
            u"solange Immer aktiv ist."),
        u"progressShowAlways": _row(
            u"Immer", u"Immer anzeigen",
            u"Lässt die Leiste dauerhaft auf dem Bildschirm stehen; sie verschwindet nie. "
            u"Hat Vorrang vor beiden Schaltern oben, die dabei ausgegraut werden."),
        u"progressVariant": _row(
            u"Modus", u"Leistenmodus",
            u"Wechselt zwischen den beiden oben beschriebenen Leisten. Wird wirksam, sobald "
            u"die Leiste das nächste Mal erscheint."),
        u"progressSize": _row(
            u"Skalierung", u"Leistengröße",
            u"Standard: die normale Größe der Leiste. Groß: zeigt sie größer an, für bessere "
            u"Lesbarkeit aus der Entfernung."),
        u"progressOrientation": _row(
            u"Ausrichtung", u"Leistenausrichtung",
            u"Horizontal ist das ursprüngliche Layout der Leiste. Vertikal zeigt sie "
            u"aufrecht stehend, passend zur Platzierung neben der Minikarte. Wird wirksam, "
            u"sobald die Leiste das nächste Mal erscheint."),
        u"progressAlignment": _row(
            u"Verankerung", u"Verankerung der Leiste",
            u"Von welchem Ankerpunkt aus die Positionsfelder unten wirken. Fest: der eingebaute "
            u"Platz der Leiste, automatisch anhand der Ausrichtung gewählt -- horizontal sitzt "
            u"sie mittig am unteren Bildschirmrand, über dem Schadensprotokoll; vertikal sitzt "
            u"sie neben der Minikarte, nahe ihrer unteren linken Ecke, passend zur aktuellen "
            u"Größe der Minikarte. Frei: eine unverankerte Position, automatisch gesetzt, sobald "
            u"du die Leiste ziehst oder ein Feld änderst. Unter Fest ist die Position gesperrt; "
            u"Ziehen und die Felder unten wirken nur unter Frei."),
        u"garageWidget": _row(
            u"Aktiviert", u"Garage-Widget",
            u"Zeigt die Marken-Prozentanzeige in der Garage beim ausgewählten Fahrzeug. "
            u"Zum Ausblenden abwählen."),
        u"battleWidget": _row(
            u"Aktiviert", u"Gefechts-Widget",
            u"Zeigt die Live-Marken-Anzeige im Gefecht. Zum Ausblenden abwählen; die "
            u"Optionen unten werden dann deaktiviert."),
        u"battleAltKey": _row(
            u"Alt drücken", u"Auf Alt-Taste anzeigen",
            u"Zeigt die Gefechtsanzeige nur, solange die Alt-Taste gehalten wird. Wenn "
            u"deaktiviert, wird die Anzeige dauerhaft angezeigt."),
        u"countedAssist": _row(
            u"Angerechnete Unterstützung (Zeile)", u"Angerechnete Unterstützung",
            u"Fügt der Gefechtsanzeige eine dritte Zeile mit deiner angerechneten "
            u"Unterstützung hinzu: dem höheren Wert aus Ketten-, Aufklärungs- oder "
            u"Betäubungsunterstützung, mit einem Symbol für den führenden Wert."),
        u"progressBar": _row(
            u"Aktiviert", u"Fortschrittsleiste",
            u"Zeigt während des Spiels eine Leiste in der Bildschirmmitte, die von selbst "
            u"wieder verschwindet. Halte Alt, um sie jederzeit einzublenden. Wähle unten, "
            u"welche Leiste. "
            u"Schadenseffizienz: zeigt deinen Schaden in diesem Gefecht im Verhältnis zu den "
            u"Anforderungen der Marken 65 / 85 / 95 / 100 %. Gleitender Durchschnitt: zeigt, wo "
            u"dein voraussichtlicher Durchschnittsschaden zwischen der Marke, die du hast, und "
            u"der Anforderung der nächsten Marke liegt."),
        u"catTransitions": _row(u"Übergänge"),
        u"progressTransitions": _row(
            u"Aktiviert", u"Übergänge der Leiste",
            u"Die Leiste blendet ein und gleitet, wenn sie erscheint und verschwindet. Deaktiviere "
            u"dies, damit jedes Erscheinen sofort erfolgt, oder schalte unten nur einen Schalter "
            u"ab. Ereignisse betrifft die Reaktion der Leiste auf das Geschehen im Gefecht; Alt "
            u"drücken betrifft das Einblenden mit der Alt-Taste, wie in der Spieloberfläche "
            u"selbst, die bei Alt nichts animiert."),
        u"progressTransEvents": _row(u"Ereignisse"),
        u"progressTransManual": _row(u"Alt drücken"),
        u"progressHoldSeconds": _row(
            u"Haltedauer (s)", u"Haltedauer",
            u"Wie lange die Leiste nach einem Ereignis auf dem Bildschirm bleibt, in Sekunden. "
            u"Solange Alt gehalten wird, bleibt sie unabhängig davon eingeblendet. Ein- und "
            u"Ausblenden werden nicht mitgezählt."),
        u"positioning": _row(
            u"Layout", u"Widget-Position",
            u"Ziehe das Garage-Widget mit Strg+Ziehen, um es zu verschieben (halte "
            u"Umschalt gedrückt, um es auf eine Achse zu beschränken). Die Felder unten "
            u"zeigen seine fixierte Position oben links in Pixeln; 0 / 0 bedeutet die "
            u"Standardposition unten rechts. Nutze das Zurücksetzen des Mods, um zum "
            u"Standard zurückzukehren."),
        u"positionSub": _row(
            u"Position", u"Positions-Felder",
            u"Beide Felder unten wirken sofort, ganz ohne das Widget zu ziehen."),
        u"posX": _row(
            u"Horizontal (links X)", u"Horizontale Position",
            u"Abstand des fixierten Widgets vom linken Bildschirmrand in Pixeln. 0 stellt "
            u"die automatische Position unten rechts wieder her."),
        u"posY": _row(
            u"Vertikal (oben Y)", u"Vertikale Position",
            u"Abstand des fixierten Widgets vom oberen Bildschirmrand in Pixeln. 0 stellt "
            u"die automatische Position unten rechts wieder her."),
        u"catBarPosition": _row(
            u"Layout", u"Position der Leiste im Gefecht",
            u"Halte im Gefecht Strg gedrückt und ziehe die Leiste, um sie zu verschieben. Die "
            u"Felder unten zeigen ihre fixierte Position in Pixeln von der oberen linken "
            u"Bildschirmecke; 0 / 0 bedeutet die zentrierte Standardposition. Nutze das "
            u"Zurücksetzen des Mods, um zum Standard zurückzukehren."),
        u"barPosX": _row(u"Horizontal (links X)"),
        u"barPosY": _row(u"Vertikal (oben Y)"),
        u"followCarousel": _row(
            u"Karussell folgen", u"Karussell folgen",
            u"Wenn aktiviert, verschiebt sich ein gezogenes Widget weiterhin vertikal mit "
            u"dem Fahrzeugkarussell (eine / zwei Reihen), sodass es dieses nie überdeckt. "
            u"Wenn deaktiviert, bleibt ein fixiertes Widget unabhängig vom Karussell an "
            u"seiner Stelle."),
        u"variantHotkey": _row(
            u"Modus-Wechseltaste", u"Modus-Wechsel im Gefecht",
            u"Die Taste, die du im Gefecht drückst, um den Fortschrittsleisten-Modus dieses "
            u"Fahrzeugs zwischen Schadenseffizienz und Gleitendem Durchschnitt "
            u"umzuschalten. Der Mod merkt sich die Wahl für jedes Fahrzeug. Nach dem "
            u"Wechsel lädt die Leiste neu und erscheint nach ein paar Sekunden wieder. "
            u"Standard: K."),
        u"progressAutoToggleThreshold": _row(
            u"Automatische Modusumschaltung", u"Automatische Modusumschaltung",
            u"Wenn der Markenfortschritt eines Fahrzeugs vor dem Gefecht diesen "
            u"Prozentsatz erreicht, wechselt der Leistenmodus automatisch, genauso wie "
            u"mit der Wechseltaste oben. Wirkt nur einmal pro Fahrzeug. 100 % schaltet "
            u"dies aus."),
    },

    u"fr": {
        u"catGarage": _row(u"Widget du garage"),
        u"catBattleCalc": _row(u"Calculateur de bataille"),
        u"catBattleProgress": _row(u"Progression en bataille"),
        u"progressShowEvents": _row(
            u"Événements", u"Afficher sur événement",
            u"Affiche la barre d'elle-même dès qu'un événement suivi se produit en bataille, "
            u"puis la fait disparaître à nouveau. Ignoré tant que Toujours est actif."),
        u"progressShowAlt": _row(
            u"Appui sur Alt", u"Afficher avec la touche Alt",
            u"Affiche la barre uniquement tant que la touche Alt est maintenue. Ignoré tant "
            u"que Toujours est actif."),
        u"progressShowAlways": _row(
            u"Toujours", u"Toujours afficher",
            u"Laisse la barre affichée en permanence à l'écran ; elle ne disparaît jamais. "
            u"Prime sur les deux interrupteurs ci-dessus, qui se grisent tant que celui-ci "
            u"est actif."),
        u"progressVariant": _row(
            u"Mode", u"Mode de la barre",
            u"Bascule entre les deux barres décrites ci-dessus. Prend effet la prochaine fois "
            u"que la barre apparaît."),
        u"progressSize": _row(
            u"Échelle", u"Taille de la barre",
            u"Par défaut : taille normale de la barre. Grande : l'affiche plus grande, pour une "
            u"meilleure lisibilité à distance."),
        u"progressOrientation": _row(
            u"Orientation", u"Orientation de la barre",
            u"Horizontale est la disposition d'origine de la barre. Verticale l'affiche debout, "
            u"dimensionnée pour se placer à côté de la minicarte. Prend effet la prochaine "
            u"fois que la barre apparaît."),
        u"progressAlignment": _row(
            u"Alignement", u"Alignement de la barre",
            u"Depuis quel point d'ancrage les compteurs de position ci-dessous se décalent. "
            u"Fixe : l'emplacement intégré de la barre, choisi automatiquement selon "
            u"l'orientation -- horizontale, elle se centre en bas de l'écran, au-dessus du "
            u"journal des dégâts ; verticale, elle se place à côté de la minicarte, près de son "
            u"coin inférieur gauche, selon la taille actuelle de la minicarte. Libre : une "
            u"position non ancrée, définie automatiquement dès que vous faites glisser la "
            u"barre ou modifiez un compteur. Sous Fixe, la position est verrouillée ; le "
            u"glisser et les compteurs ci-dessous ne fonctionnent que sous Libre."),
        u"garageWidget": _row(
            u"Activé", u"Widget du garage",
            u"Affiche la barre de centile des marques d'excellence dans le garage, sur le "
            u"véhicule sélectionné. Décochez pour la masquer."),
        u"battleWidget": _row(
            u"Activé", u"Widget de bataille",
            u"Affiche la superposition des marques d'excellence en direct pendant la "
            u"bataille. Décochez pour la masquer et désactiver les options ci-dessous."),
        u"battleAltKey": _row(
            u"Appui sur Alt", u"Afficher avec la touche Alt",
            u"Affiche la superposition de bataille uniquement tant que la touche Alt est "
            u"maintenue. Lorsque cette option est désactivée, la superposition est "
            u"affichée en permanence."),
        u"countedAssist": _row(
            u"Ligne d'assistance comptabilisée", u"Assistance comptabilisée",
            u"Ajoute une troisième ligne à la superposition de bataille indiquant votre "
            u"assistance comptabilisée : la plus élevée entre l'assistance par chenilles, "
            u"par détection ou par étourdissement, avec une icône pour celle qui domine."),
        u"progressBar": _row(
            u"Activé", u"Barre de progression",
            u"Affiche une barre au centre de l'écran pendant la partie, puis la fait "
            u"disparaître d'elle-même. Maintenez Alt pour l'afficher à tout moment. "
            u"Choisissez la barre ci-dessous. "
            u"Efficacité des dégâts : situe vos dégâts de la bataille en cours par rapport aux "
            u"exigences des marques 65 / 85 / 95 / 100 %. Moyenne glissante : indique où se "
            u"situent vos dégâts moyens prévus entre la marque que vous possédez et l'exigence "
            u"de la marque suivante."),
        u"catTransitions": _row(u"Transitions"),
        u"progressTransitions": _row(
            u"Activé", u"Transitions de la barre",
            u"La barre s'estompe et glisse lorsqu'elle apparaît et disparaît. Décochez ceci pour "
            u"que chaque apparition soit instantanée, ou désactivez un seul interrupteur "
            u"ci-dessous. Événements concerne la réaction de la barre à ce qui se passe en "
            u"bataille ; Appui sur Alt concerne son affichage avec la touche Alt, comme "
            u"l'interface du jeu elle-même, qui n'anime rien avec Alt."),
        u"progressTransEvents": _row(u"Événements"),
        u"progressTransManual": _row(u"Appui sur Alt"),
        u"progressHoldSeconds": _row(
            u"Durée d'affichage (s)", u"Durée d'affichage",
            u"Combien de temps la barre reste à l'écran, en secondes, après qu'un événement l'a "
            u"fait apparaître. Tant que la touche Alt est maintenue, elle reste affichée quelle "
            u"que soit cette valeur. Les fondus d'entrée et de sortie ne sont pas comptés."),
        u"positioning": _row(
            u"Disposition", u"Position du widget",
            u"Ctrl+glisser pour déplacer le widget du garage (maintenez Maj pour le "
            u"verrouiller sur un axe). Les compteurs ci-dessous indiquent sa position "
            u"épinglée en haut à gauche, en pixels ; 0 / 0 correspond à la position par "
            u"défaut en bas à droite. Utilisez la réinitialisation du mod pour revenir au "
            u"réglage par défaut."),
        u"positionSub": _row(
            u"Position", u"Compteurs de position",
            u"Les deux compteurs ci-dessous s'appliquent immédiatement, sans avoir à faire "
            u"glisser le widget."),
        u"posX": _row(
            u"Horizontale (X gauche)", u"Position horizontale",
            u"Distance du widget épinglé par rapport au bord gauche de l'écran, en "
            u"pixels. 0 rétablit la position automatique en bas à droite."),
        u"posY": _row(
            u"Verticale (Y haut)", u"Position verticale",
            u"Distance du widget épinglé par rapport au bord supérieur de l'écran, en "
            u"pixels. 0 rétablit la position automatique en bas à droite."),
        u"catBarPosition": _row(
            u"Disposition", u"Position de la barre en bataille",
            u"En bataille, maintenez Ctrl et faites glisser la barre pour la déplacer. Les "
            u"compteurs ci-dessous indiquent sa position épinglée, en pixels depuis le coin "
            u"supérieur gauche de l'écran ; 0 / 0 correspond à la position centrée par défaut. "
            u"Utilisez la réinitialisation du mod pour revenir à la valeur par défaut."),
        u"barPosX": _row(u"Horizontale (X gauche)"),
        u"barPosY": _row(u"Verticale (Y haut)"),
        u"followCarousel": _row(
            u"Suivre le carrousel", u"Suivre le carrousel",
            u"Activé, un widget déplacé continue de se décaler verticalement avec le "
            u"carrousel des véhicules (une / deux rangées) afin de ne jamais le "
            u"chevaucher. Désactivé, un widget épinglé reste fixe quel que soit le "
            u"carrousel."),
        u"variantHotkey": _row(
            u"Touche de changement de mode", u"Changement de mode en bataille",
            u"La touche que vous appuyez en bataille pour basculer le mode de la barre de "
            u"progression de ce véhicule entre Efficacité des dégâts et Moyenne glissante. "
            u"Le mod mémorise le choix de chaque véhicule. Après le changement, la barre "
            u"se recharge et réapparaît après quelques secondes. Par défaut : K."),
        u"progressAutoToggleThreshold": _row(
            u"Changement de mode automatique", u"Changement de mode automatique",
            u"Lorsque la progression des marques d'un véhicule atteint ce pourcentage "
            u"avant la bataille, le mode de la barre change automatiquement, comme avec "
            u"la touche de changement ci-dessus. Ne se déclenche qu'une fois par "
            u"véhicule. 100 % désactive cette fonction."),
    },

    u"es": {
        u"catGarage": _row(u"Widget del garaje"),
        u"catBattleCalc": _row(u"Calculadora de batalla"),
        u"catBattleProgress": _row(u"Progreso en batalla"),
        u"progressShowEvents": _row(
            u"Eventos", u"Mostrar en eventos",
            u"Muestra la barra por sí sola en cuanto ocurre un evento seguido en la batalla, "
            u"y luego la oculta de nuevo. Se ignora mientras Siempre está activado."),
        u"progressShowAlt": _row(
            u"Pulsar Alt", u"Mostrar con la tecla Alt",
            u"Muestra la barra solo mientras mantienes pulsada la tecla Alt. Se ignora "
            u"mientras Siempre está activado."),
        u"progressShowAlways": _row(
            u"Siempre", u"Mostrar siempre",
            u"Mantiene la barra en pantalla de forma permanente; nunca se oculta. Anula los "
            u"dos interruptores anteriores, que se atenúan mientras este está activado."),
        u"progressVariant": _row(
            u"Modo", u"Modo de la barra",
            u"Alterna entre las dos barras descritas arriba. Se aplica la próxima vez que "
            u"aparezca la barra."),
        u"progressSize": _row(
            u"Escala", u"Tamaño de la barra",
            u"Predeterminada: el tamaño normal de la barra. Grande: la muestra más grande, para "
            u"facilitar la lectura a distancia."),
        u"progressOrientation": _row(
            u"Orientación", u"Orientación de la barra",
            u"Horizontal es la disposición original de la barra. Vertical la muestra de pie, "
            u"dimensionada para colocarse junto al minimapa. Se aplica la próxima vez que "
            u"aparezca la barra."),
        u"progressAlignment": _row(
            u"Alineación", u"Alineación de la barra",
            u"Desde qué punto de anclaje se desplazan los contadores de posición de abajo. "
            u"Fija: la posición integrada de la barra, elegida automáticamente según la "
            u"orientación -- horizontal se centra en la parte inferior de la pantalla, sobre el "
            u"registro de daños; vertical se coloca junto al minimapa, cerca de su esquina "
            u"inferior izquierda, según el tamaño actual del minimapa. Libre: una posición sin "
            u"anclar, establecida automáticamente al arrastrar la barra o editar un contador. "
            u"Bajo Fija, la posición está bloqueada; arrastrar y los contadores de abajo solo "
            u"funcionan bajo Libre."),
        u"garageWidget": _row(
            u"Activado", u"Widget del garaje",
            u"Muestra la barra de percentil de las marcas de excelencia en el garaje, en "
            u"el vehículo seleccionado. Desmarca para ocultarla."),
        u"battleWidget": _row(
            u"Activado", u"Widget de batalla",
            u"Muestra la superposición de marcas de excelencia en directo durante la "
            u"batalla. Desmarca para ocultarla y desactivar las opciones de abajo."),
        u"battleAltKey": _row(
            u"Pulsar Alt", u"Mostrar con la tecla Alt",
            u"Muestra la superposición de batalla solo mientras se mantiene pulsada la "
            u"tecla Alt. Cuando está desactivado, la superposición se muestra en todo "
            u"momento."),
        u"countedAssist": _row(
            u"Fila de asistencia contada", u"Asistencia contada",
            u"Añade una tercera fila a la superposición de batalla que muestra tu "
            u"asistencia contada: la mayor entre la asistencia por orugas, por detección "
            u"o por aturdimiento, con un icono para la que predomine."),
        u"progressBar": _row(
            u"Activado", u"Barra de progreso",
            u"Muestra una barra en el centro de la pantalla durante la partida y luego la "
            u"oculta por sí sola. Mantén pulsado Alt para mostrarla en cualquier momento. "
            u"Elige abajo qué barra. "
            u"Eficiencia de daño: sitúa tu daño de esta batalla frente a los requisitos de las "
            u"marcas del 65 / 85 / 95 / 100 %. Media móvil: indica dónde se sitúa tu daño medio "
            u"previsto entre la marca que tienes y el requisito de la siguiente marca."),
        u"catTransitions": _row(u"Transiciones"),
        u"progressTransitions": _row(
            u"Activado", u"Transiciones de la barra",
            u"La barra se atenúa y desliza al aparecer y desaparecer. Desmarca esto para que cada "
            u"aparición sea instantánea, o desactiva solo uno de los interruptores de abajo. "
            u"Eventos se refiere a la barra reaccionando a lo que ocurre en la batalla; Pulsar "
            u"Alt se refiere a mostrarla con la tecla Alt, igual que la interfaz del propio "
            u"juego, que no anima nada con Alt."),
        u"progressTransEvents": _row(u"Eventos"),
        u"progressTransManual": _row(u"Pulsar Alt"),
        u"progressHoldSeconds": _row(
            u"Duración en pantalla (s)", u"Duración en pantalla",
            u"Cuánto tiempo permanece la barra en pantalla, en segundos, después de que un evento "
            u"la muestre. Mientras mantengas Alt seguirá visible, sea cual sea este valor. Las "
            u"transiciones de entrada y salida no se cuentan."),
        u"positioning": _row(
            u"Disposición", u"Posición del widget",
            u"Ctrl+arrastrar para mover el widget del garaje (mantén Mayús para "
            u"bloquearlo en un eje). Los contadores de abajo muestran su posición fijada "
            u"de la esquina superior izquierda, en píxeles; 0 / 0 es la posición "
            u"predeterminada en la esquina inferior derecha. Usa el restablecimiento del "
            u"mod para volver al valor predeterminado."),
        u"positionSub": _row(
            u"Posición", u"Contadores de posición",
            u"Ambos contadores de abajo se aplican de inmediato, sin necesidad de arrastrar el "
            u"widget."),
        u"posX": _row(
            u"Horizontal (X izquierda)", u"Posición horizontal",
            u"Distancia del widget fijado al borde izquierdo de la pantalla, en píxeles. "
            u"0 restaura la posición automática en la esquina inferior derecha."),
        u"posY": _row(
            u"Vertical (Y superior)", u"Posición vertical",
            u"Distancia del widget fijado al borde superior de la pantalla, en píxeles. 0 "
            u"restaura la posición automática en la esquina inferior derecha."),
        u"catBarPosition": _row(
            u"Disposición", u"Posición de la barra en combate",
            u"En combate, mantén pulsado Ctrl y arrastra la barra para moverla. Los contadores "
            u"de abajo muestran su posición fijada, en píxeles desde la esquina superior "
            u"izquierda de la pantalla; 0 / 0 es la posición centrada predeterminada. Usa el "
            u"restablecimiento del mod para volver al valor predeterminado."),
        u"barPosX": _row(u"Horizontal (X izquierda)"),
        u"barPosY": _row(u"Vertical (Y superior)"),
        u"followCarousel": _row(
            u"Seguir el carrusel", u"Seguir el carrusel",
            u"Cuando está activado, un widget arrastrado sigue desplazándose "
            u"verticalmente con el carrusel de vehículos (una / dos filas) para no "
            u"superponerse a él. Cuando está desactivado, un widget fijado permanece fijo "
            u"sin importar el carrusel."),
        u"variantHotkey": _row(
            u"Tecla de cambio de modo", u"Cambio de modo en combate",
            u"La tecla que pulsas en combate para alternar el modo de la barra de progreso "
            u"de este vehículo entre Eficiencia de daño y Media móvil. El mod recuerda la "
            u"elección de cada vehículo. Después de cambiar, la barra se recarga y "
            u"reaparece tras unos segundos. Predeterminada: K."),
        u"progressAutoToggleThreshold": _row(
            u"Cambio de modo automático", u"Cambio de modo automático",
            u"Cuando el progreso de marcas de un vehículo alcanza este porcentaje antes "
            u"de la batalla, el modo de la barra cambia automáticamente, igual que con "
            u"la tecla de cambio de arriba. Solo se activa una vez por vehículo. 100 % "
            u"lo desactiva."),
    },

    u"it": {
        u"catGarage": _row(u"Widget del garage"),
        u"catBattleCalc": _row(u"Calcolatore di battaglia"),
        u"catBattleProgress": _row(u"Progresso in battaglia"),
        u"progressShowEvents": _row(
            u"Eventi", u"Mostra sugli eventi",
            u"Mostra la barra da sola non appena accade un evento monitorato in battaglia, "
            u"poi la fa scomparire di nuovo. Ignorato mentre Sempre è attivo."),
        u"progressShowAlt": _row(
            u"Premi Alt", u"Mostra con il tasto Alt",
            u"Mostra la barra solo mentre tieni premuto il tasto Alt. Ignorato mentre Sempre "
            u"è attivo."),
        u"progressShowAlways": _row(
            u"Sempre", u"Mostra sempre",
            u"Lascia la barra fissa sullo schermo in modo permanente; non scompare mai. "
            u"Prevale sui due interruttori sopra, che restano in grigio finché questo è "
            u"attivo."),
        u"progressVariant": _row(
            u"Modalità", u"Modalità della barra",
            u"Passa da una barra all'altra tra le due descritte sopra. Ha effetto la prossima "
            u"volta che la barra appare."),
        u"progressSize": _row(
            u"Scala", u"Dimensione della barra",
            u"Predefinita: la dimensione normale della barra. Grande: la mostra più grande, per "
            u"una lettura più facile a distanza."),
        u"progressOrientation": _row(
            u"Orientamento", u"Orientamento della barra",
            u"Orizzontale è la disposizione originale della barra. Verticale la mostra in "
            u"piedi, dimensionata per stare accanto alla minimappa. Ha effetto la prossima "
            u"volta che la barra appare."),
        u"progressAlignment": _row(
            u"Allineamento", u"Allineamento della barra",
            u"Da quale punto di ancoraggio partono i contatori di posizione sotto. Fisso: la "
            u"posizione predefinita della barra, scelta automaticamente in base "
            u"all'orientamento -- orizzontale si centra in basso sullo schermo, sopra il "
            u"registro danni; verticale si posiziona accanto alla minimappa, vicino al suo "
            u"angolo inferiore sinistro, in base alla dimensione attuale della minimappa. "
            u"Libero: una posizione non ancorata, impostata automaticamente trascinando la "
            u"barra o modificando un contatore. Con Fisso la posizione è bloccata; il "
            u"trascinamento e i contatori sotto funzionano solo con Libero."),
        u"garageWidget": _row(
            u"Abilitato", u"Widget del garage",
            u"Mostra la barra di percentile dei marchi di merito nel garage, sul veicolo "
            u"selezionato. Deseleziona per nasconderla."),
        u"battleWidget": _row(
            u"Abilitato", u"Widget di battaglia",
            u"Mostra la sovrapposizione dei marchi di merito in tempo reale durante la "
            u"battaglia. Deseleziona per nasconderla e disattivare le opzioni "
            u"sottostanti."),
        u"battleAltKey": _row(
            u"Premi Alt", u"Mostra con il tasto Alt",
            u"Mostra la sovrapposizione di battaglia solo mentre si tiene premuto il "
            u"tasto Alt. Quando è disattivato, la sovrapposizione è sempre visibile."),
        u"countedAssist": _row(
            u"Riga assistenza conteggiata", u"Assistenza conteggiata",
            u"Aggiunge una terza riga alla sovrapposizione di battaglia che mostra la tua "
            u"assistenza conteggiata: la più alta tra assistenza ai cingoli, "
            u"all'avvistamento o allo stordimento, con un'icona per quella prevalente."),
        u"progressBar": _row(
            u"Abilitato", u"Barra di progresso",
            u"Mostra una barra al centro dello schermo durante la partita, poi scompare da "
            u"sola. Tieni premuto Alt per mostrarla in qualsiasi momento. Scegli sotto quale "
            u"barra. "
            u"Efficienza dei danni: colloca i tuoi danni di questa battaglia rispetto ai "
            u"requisiti dei marchi 65 / 85 / 95 / 100 %. Media mobile: indica dove si collocano "
            u"i tuoi danni medi previsti tra il marchio che possiedi e il requisito del marchio "
            u"successivo."),
        u"catTransitions": _row(u"Transizioni"),
        u"progressTransitions": _row(
            u"Abilitato", u"Transizioni della barra",
            u"La barra sfuma e scorre quando appare e scompare. Deseleziona questa voce perché "
            u"ogni comparsa sia istantanea, oppure disattiva un solo interruttore qui sotto. "
            u"Eventi riguarda la barra che reagisce a ciò che accade in battaglia; Premi Alt "
            u"riguarda il richiamarla con il tasto Alt, come l'interfaccia del gioco stesso, che "
            u"con Alt non anima nulla."),
        u"progressTransEvents": _row(u"Eventi"),
        u"progressTransManual": _row(u"Premi Alt"),
        u"progressHoldSeconds": _row(
            u"Durata di permanenza (s)", u"Durata di permanenza",
            u"Per quanto tempo la barra resta sullo schermo, in secondi, dopo che un evento l'ha "
            u"richiamata. Tenendo premuto Alt resta visibile a prescindere da questo valore. Le "
            u"dissolvenze di entrata e di uscita non sono conteggiate."),
        u"positioning": _row(
            u"Disposizione", u"Posizione del widget",
            u"Ctrl+trascina per spostare il widget del garage (tieni premuto Maiusc per "
            u"bloccarlo su un asse). I contatori sotto mostrano la sua posizione fissata "
            u"in alto a sinistra, in pixel; 0 / 0 indica la posizione predefinita in "
            u"basso a destra. Usa il ripristino del mod per tornare al valore "
            u"predefinito."),
        u"positionSub": _row(
            u"Posizione", u"Contatori di posizione",
            u"Entrambi i contatori sotto si applicano immediatamente, senza dover trascinare "
            u"il widget."),
        u"posX": _row(
            u"Orizzontale (X sinistra)", u"Posizione orizzontale",
            u"Distanza del widget fissato dal bordo sinistro dello schermo, in pixel. 0 "
            u"ripristina la posizione automatica in basso a destra."),
        u"posY": _row(
            u"Verticale (Y alto)", u"Posizione verticale",
            u"Distanza del widget fissato dal bordo superiore dello schermo, in pixel. 0 "
            u"ripristina la posizione automatica in basso a destra."),
        u"catBarPosition": _row(
            u"Disposizione", u"Posizione della barra in battaglia",
            u"In battaglia, tieni premuto Ctrl e trascina la barra per spostarla. I contatori "
            u"sotto mostrano la sua posizione fissata, in pixel dall'angolo in alto a sinistra "
            u"dello schermo; 0 / 0 indica la posizione centrata predefinita. Usa il ripristino "
            u"del mod per tornare al valore predefinito."),
        u"barPosX": _row(u"Orizzontale (X sinistra)"),
        u"barPosY": _row(u"Verticale (Y alto)"),
        u"followCarousel": _row(
            u"Segui il carosello", u"Segui il carosello",
            u"Quando è attivo, un widget trascinato continua a spostarsi verticalmente "
            u"con il carosello dei veicoli (una / due file) in modo da non sovrapporsi "
            u"mai ad esso. Quando è disattivato, un widget fissato resta fermo "
            u"indipendentemente dal carosello."),
        u"variantHotkey": _row(
            u"Tasto di cambio modalità", u"Cambio modalità in battaglia",
            u"Il tasto che premi in battaglia per cambiare la modalità della barra di "
            u"progresso di questo veicolo tra Efficienza dei danni e Media mobile. Il mod "
            u"ricorda la scelta di ogni veicolo. Dopo il cambio, la barra si ricarica e "
            u"riappare dopo alcuni secondi. Predefinito: K."),
        u"progressAutoToggleThreshold": _row(
            u"Cambio modalità automatico", u"Cambio modalità automatico",
            u"Quando il progresso dei marchi di un veicolo raggiunge questa percentuale "
            u"prima della battaglia, la modalità della barra cambia automaticamente, "
            u"come con il tasto di cambio sopra. Si attiva solo una volta per veicolo. "
            u"Il 100% lo disattiva."),
    },

    u"pl": {
        u"catGarage": _row(u"Widżet w garażu"),
        u"catBattleCalc": _row(u"Kalkulator bitewny"),
        u"catBattleProgress": _row(u"Postęp w bitwie"),
        u"progressShowEvents": _row(
            u"Zdarzenia", u"Pokaż przy zdarzeniach",
            u"Pokazuje pasek samoczynnie, gdy w bitwie wystąpi śledzone zdarzenie, po czym "
            u"znów znika. Ignorowane, gdy włączone jest Zawsze."),
        u"progressShowAlt": _row(
            u"Naciśnij Alt", u"Pokaż na klawiszu Alt",
            u"Pokazuje pasek tylko podczas przytrzymania klawisza Alt. Ignorowane, gdy "
            u"włączone jest Zawsze."),
        u"progressShowAlways": _row(
            u"Zawsze", u"Zawsze pokazuj",
            u"Utrzymuje pasek na ekranie na stałe; nigdy nie znika. Ma pierwszeństwo przed "
            u"obydwoma przełącznikami powyżej, które są wyszarzone, gdy ta opcja jest "
            u"włączona."),
        u"progressVariant": _row(
            u"Tryb", u"Tryb paska",
            u"Przełącza między dwoma paskami opisanymi powyżej. Zaczyna działać przy "
            u"następnym pojawieniu się paska."),
        u"progressSize": _row(
            u"Skala", u"Rozmiar paska",
            u"Domyślna: normalny rozmiar paska. Duża: pokazuje go większym, dla łatwiejszego "
            u"odczytu z odległości."),
        u"progressOrientation": _row(
            u"Orientacja", u"Orientacja paska",
            u"Pozioma to pierwotny układ paska. Pionowa pokazuje go w pozycji stojącej, "
            u"dopasowanego rozmiarem do miejsca obok minimapy. Zaczyna działać przy "
            u"następnym pojawieniu się paska."),
        u"progressAlignment": _row(
            u"Zakotwiczenie", u"Zakotwiczenie paska",
            u"Od którego punktu odniesienia liczą się liczniki pozycji poniżej. Stałe: "
            u"wbudowane miejsce paska, wybierane automatycznie według orientacji -- pozioma "
            u"ustawia się na środku dolnej krawędzi ekranu, nad dziennikiem obrażeń; pionowa "
            u"ustawia się obok minimapy, blisko jej lewego dolnego rogu, zgodnie z aktualnym "
            u"rozmiarem minimapy. Swobodne: pozycja bez punktu odniesienia, ustawiana "
            u"automatycznie po przeciągnięciu paska lub edycji licznika. Przy Stałe pozycja "
            u"jest zablokowana; przeciąganie i liczniki poniżej działają tylko przy Swobodne."),
        u"garageWidget": _row(
            u"Włączone", u"Widżet w garażu",
            u"Pokazuje pasek percentyla znaków doskonałości w garażu, na wybranym "
            u"pojeździe. Odznacz, aby ukryć."),
        u"battleWidget": _row(
            u"Włączone", u"Widżet w bitwie",
            u"Pokazuje nakładkę znaków doskonałości na żywo podczas bitwy. Odznacz, aby "
            u"ją ukryć i wyłączyć opcje poniżej."),
        u"battleAltKey": _row(
            u"Naciśnij Alt", u"Pokaż na klawiszu Alt",
            u"Pokazuje nakładkę bitewną tylko podczas przytrzymania klawisza Alt. Gdy "
            u"wyłączone, nakładka jest wyświetlana przez cały czas."),
        u"countedAssist": _row(
            u"Wiersz zaliczonego wsparcia", u"Zaliczone wsparcie",
            u"Dodaje trzeci wiersz nakładki bitewnej pokazujący twoje zaliczone wsparcie: "
            u"wyższą z wartości wsparcia przez unieruchomienie, wykrycie lub ogłuszenie, z "
            u"ikoną dla przeważającej."),
        u"progressBar": _row(
            u"Włączone", u"Pasek postępu",
            u"Pokazuje pasek na środku ekranu w trakcie gry, a potem znika on samoczynnie. "
            u"Przytrzymaj Alt, aby wyświetlić go w dowolnym momencie. Wybierz poniżej, który "
            u"pasek. "
            u"Efektywność obrażeń: pokazuje twoje obrażenia w tej bitwie na tle wymagań znaków "
            u"65 / 85 / 95 / 100 %. Średnia krocząca: wskazuje, gdzie twoje przewidywane średnie "
            u"obrażenia wypadają między znakiem, który posiadasz, a wymaganiem następnego "
            u"znaku."),
        u"catTransitions": _row(u"Przejścia"),
        u"progressTransitions": _row(
            u"Włączone", u"Przejścia paska",
            u"Pasek pojawia się i znika z przygaszeniem oraz przesunięciem. Odznacz tę opcję, aby "
            u"każde pojawienie było natychmiastowe, albo wyłącz tylko jeden z przełączników "
            u"poniżej. Zdarzenia dotyczą reakcji paska na to, co dzieje się w bitwie; Naciśnij "
            u"Alt dotyczy wywołania go klawiszem Alt, tak jak w interfejsie samej gry, który "
            u"przy Alt nic nie animuje."),
        u"progressTransEvents": _row(u"Zdarzenia"),
        u"progressTransManual": _row(u"Naciśnij Alt"),
        u"progressHoldSeconds": _row(
            u"Czas wyświetlania (s)", u"Czas wyświetlania",
            u"Jak długo pasek pozostaje na ekranie, w sekundach, po tym jak wywoła go zdarzenie. "
            u"Przy przytrzymanym Alt pozostaje widoczny niezależnie od tej wartości. Przygaszenie "
            u"przy pojawianiu się i zniknięciu nie jest liczone."),
        u"positioning": _row(
            u"Układ", u"Pozycja widżetu",
            u"Ctrl+przeciągnij, aby przesunąć widżet garażu (przytrzymaj Shift, aby "
            u"zablokować do jednej osi). Liczniki poniżej pokazują przypiętą pozycję "
            u"lewego górnego rogu w pikselach; 0 / 0 oznacza domyślną pozycję w prawym "
            u"dolnym rogu. Użyj resetu moda, aby wrócić do wartości domyślnej."),
        u"positionSub": _row(
            u"Pozycja", u"Liczniki pozycji",
            u"Oba liczniki poniżej działają natychmiast, bez konieczności przeciągania "
            u"widżetu."),
        u"posX": _row(
            u"Pozioma (lewy X)", u"Pozycja pozioma",
            u"Odległość przypiętego widżetu od lewej krawędzi ekranu, w pikselach. 0 "
            u"przywraca automatyczną pozycję w prawym dolnym rogu."),
        u"posY": _row(
            u"Pionowa (górny Y)", u"Pozycja pionowa",
            u"Odległość przypiętego widżetu od górnej krawędzi ekranu, w pikselach. 0 "
            u"przywraca automatyczną pozycję w prawym dolnym rogu."),
        u"catBarPosition": _row(
            u"Układ", u"Pozycja paska w bitwie",
            u"W bitwie przytrzymaj Ctrl i przeciągnij pasek, aby go przesunąć. Liczniki "
            u"poniżej pokazują jego przypiętą pozycję w pikselach od lewego górnego rogu "
            u"ekranu; 0 / 0 oznacza domyślną pozycję na środku. Użyj resetu moda, aby wrócić "
            u"do wartości domyślnej."),
        u"barPosX": _row(u"Pozioma (lewy X)"),
        u"barPosY": _row(u"Pionowa (górny Y)"),
        u"followCarousel": _row(
            u"Podążaj za karuzelą", u"Podążaj za karuzelą",
            u"Gdy włączone, przeciągnięty widżet nadal przesuwa się w pionie wraz z "
            u"karuzelą pojazdów (jeden / dwa rzędy), aby nigdy jej nie zasłaniać. Gdy "
            u"wyłączone, przypięty widżet pozostaje na miejscu niezależnie od karuzeli."),
        u"variantHotkey": _row(
            u"Klawisz zmiany trybu", u"Zmiana trybu w bitwie",
            u"Klawisz, który naciskasz w bitwie, aby przełączyć tryb paska postępu tego "
            u"pojazdu między Efektywnością obrażeń a Średnią kroczącą. Mod zapamiętuje "
            u"wybór dla każdego pojazdu. Po zmianie pasek przeładowuje się i pojawia się "
            u"ponownie po kilku sekundach. Domyślnie: K."),
        u"progressAutoToggleThreshold": _row(
            u"Automatyczna zmiana trybu", u"Automatyczna zmiana trybu",
            u"Gdy postęp znaków pojazdu przed bitwą osiągnie ten procent, tryb paska "
            u"zmienia się automatycznie, tak jak za pomocą klawisza zmiany powyżej. "
            u"Działa tylko raz na pojazd. 100% wyłącza tę funkcję."),
    },

    u"cs": {
        u"catGarage": _row(u"Widget v garáži"),
        u"catBattleCalc": _row(u"Bitevní kalkulátor"),
        u"catBattleProgress": _row(u"Postup v bitvě"),
        u"progressShowEvents": _row(
            u"Události", u"Zobrazit při událostech",
            u"Zobrazí lištu samovolně, jakmile v bitvě nastane sledovaná událost, a poté ji "
            u"znovu skryje. Ignorováno, když je zapnuto Vždy."),
        u"progressShowAlt": _row(
            u"Stisk Alt", u"Zobrazit na klávese Alt",
            u"Zobrazuje lištu jen po dobu podržení klávesy Alt. Ignorováno, když je zapnuto "
            u"Vždy."),
        u"progressShowAlways": _row(
            u"Vždy", u"Vždy zobrazit",
            u"Nechá lištu trvale na obrazovce; nikdy nezmizí. Má přednost před oběma "
            u"přepínači výše, které jsou po dobu jeho zapnutí zašedlé."),
        u"progressVariant": _row(
            u"Režim", u"Režim lišty",
            u"Přepíná mezi oběma lištami popsanými výše. Projeví se při příštím zobrazení "
            u"lišty."),
        u"progressSize": _row(
            u"Měřítko", u"Velikost lišty",
            u"Výchozí: běžná velikost lišty. Velké: zobrazí ji větší, pro snazší čtení z "
            u"dálky."),
        u"progressOrientation": _row(
            u"Orientace", u"Orientace lišty",
            u"Vodorovná je původní rozvržení lišty. Svislá ji zobrazí na výšku, s rozměry "
            u"pro umístění vedle minimapy. Projeví se při příštím zobrazení lišty."),
        u"progressAlignment": _row(
            u"Ukotvení", u"Ukotvení lišty",
            u"Od kterého ukotvení se počítají čítače pozice níže. Pevné: vestavěné místo "
            u"lišty, vybrané automaticky podle orientace -- vodorovná se vystředí na spodním "
            u"okraji obrazovky, nad deníkem poškození; svislá se umístí vedle minimapy, "
            u"poblíž jejího levého dolního rohu, podle aktuální velikosti minimapy. Volné: "
            u"neukotvená pozice, nastavená automaticky po přetažení lišty nebo úpravě "
            u"čítače. V režimu Pevné je pozice uzamčená; tažení a čítače níže fungují jen v "
            u"režimu Volné."),
        u"garageWidget": _row(
            u"Povoleno", u"Widget v garáži",
            u"Zobrazuje percentilovou lištu znaků cti v garáži u vybraného vozidla. "
            u"Zrušením zaškrtnutí ji skryjete."),
        u"battleWidget": _row(
            u"Povoleno", u"Widget v bitvě",
            u"Zobrazuje živý překryv znaků cti během bitvy. Zrušením zaškrtnutí jej "
            u"skryjete a vypnete možnosti níže."),
        u"battleAltKey": _row(
            u"Stisk Alt", u"Zobrazit na klávese Alt",
            u"Zobrazuje bojový překryv pouze při podržení klávesy Alt. Když je vypnuto, "
            u"překryv se zobrazuje trvale."),
        u"countedAssist": _row(
            u"Řádek započtené asistence", u"Započtená asistence",
            u"Přidá do bojového překryvu třetí řádek zobrazující tvou započtenou "
            u"asistenci: vyšší z asistence pásy, průzkumem nebo omráčením, s ikonou pro "
            u"převažující."),
        u"progressBar": _row(
            u"Povoleno", u"Lišta postupu",
            u"Zobrazuje uprostřed obrazovky lištu během hry a poté sama zmizí. Podržením "
            u"klávesy Alt ji zobrazíš kdykoli. Níže vyber, kterou lištu. "
            u"Efektivita poškození: ukazuje tvé poškození v této bitvě vůči požadavkům znaků "
            u"65 / 85 / 95 / 100 %. Klouzavý průměr: ukazuje, kde se tvé předpokládané průměrné "
            u"poškození nachází mezi znakem, který máš, a požadavkem dalšího znaku."),
        u"catTransitions": _row(u"Přechody"),
        u"progressTransitions": _row(
            u"Povoleno", u"Přechody lišty",
            u"Lišta se při zobrazení a zmizení prolíná a posouvá. Zrušením zaškrtnutí bude každé "
            u"zobrazení okamžité, nebo vypni jen jeden z přepínačů níže. Události se týkají reakce "
            u"lišty na to, co se děje v bitvě; Stisk Alt se týká jejího vyvolání klávesou Alt, "
            u"stejně jako v rozhraní samotné hry, které při Altu nic neanimuje."),
        u"progressTransEvents": _row(u"Události"),
        u"progressTransManual": _row(u"Stisk Alt"),
        u"progressHoldSeconds": _row(
            u"Doba zobrazení (s)", u"Doba zobrazení",
            u"Jak dlouho lišta zůstane na obrazovce, ve sekundách, poté co ji vyvolá událost. "
            u"Při podržení Altu zůstává zobrazená bez ohledu na tuto hodnotu. Prolnutí na začátku "
            u"a na konci se nepočítá."),
        u"positioning": _row(
            u"Rozvržení", u"Pozice widgetu",
            u"Ctrl+táhnutím přesuneš widget garáže (podržením Shift jej uzamkneš na jednu "
            u"osu). Čítače níže ukazují jeho ukotvenou pozici levého horního rohu v "
            u"pixelech; 0 / 0 znamená výchozí pozici vpravo dole. Pro návrat na výchozí "
            u"hodnotu použij reset modu."),
        u"positionSub": _row(
            u"Pozice", u"Čítače pozice",
            u"Oba čítače níže se projeví okamžitě, bez nutnosti tažení widgetu."),
        u"posX": _row(
            u"Vodorovná (levé X)", u"Vodorovná pozice",
            u"Vzdálenost ukotveného widgetu od levého okraje obrazovky v pixelech. 0 "
            u"obnoví automatickou pozici vpravo dole."),
        u"posY": _row(
            u"Svislá (horní Y)", u"Svislá pozice",
            u"Vzdálenost ukotveného widgetu od horního okraje obrazovky v pixelech. 0 "
            u"obnoví automatickou pozici vpravo dole."),
        u"catBarPosition": _row(
            u"Rozvržení", u"Pozice lišty v bitvě",
            u"V bitvě podrž Ctrl a tažením lištu přesuneš. Čítače níže ukazují její ukotvenou "
            u"pozici v pixelech od levého horního rohu obrazovky; 0 / 0 znamená výchozí pozici "
            u"uprostřed. Pro návrat na výchozí hodnotu použij reset modu."),
        u"barPosX": _row(u"Vodorovná (levé X)"),
        u"barPosY": _row(u"Svislá (horní Y)"),
        u"followCarousel": _row(
            u"Sledovat kolotoč", u"Sledovat kolotoč",
            u"Když je zapnuto, tažený widget se dál posouvá svisle spolu s kolotočem "
            u"vozidel (jedna / dvě řady), aby jej nikdy nepřekrýval. Když je vypnuto, "
            u"ukotvený widget zůstává na místě bez ohledu na kolotoč."),
        u"variantHotkey": _row(
            u"Klávesa přepnutí režimu", u"Přepnutí režimu v bitvě",
            u"Klávesa, kterou v bitvě stiskneš pro přepnutí režimu lišty postupu tohoto "
            u"vozidla mezi Efektivitou poškození a Klouzavým průměrem. Mod si pamatuje "
            u"volbu pro každé vozidlo. Po přepnutí se lišta znovu načte a znovu se zobrazí "
            u"po několika sekundách. Výchozí: K."),
        u"progressAutoToggleThreshold": _row(
            u"Automatické přepnutí režimu", u"Automatické přepnutí režimu",
            u"Když postup známek vozidla před bitvou dosáhne tohoto procenta, režim "
            u"lišty se automaticky přepne, stejně jako klávesou přepnutí výše. Spustí "
            u"se jen jednou na vozidlo. 100 % tuto funkci vypne."),
    },

    u"ru": {
        u"catGarage": _row(u"Виджет в ангаре"),
        u"catBattleCalc": _row(u"Боевой калькулятор"),
        u"catBattleProgress": _row(u"Прогресс в бою"),
        u"progressShowEvents": _row(
            u"События", u"Показывать по событиям",
            u"Показывает полосу самостоятельно, как только в бою происходит "
            u"отслеживаемое событие, а затем снова скрывает её. Игнорируется, пока включено "
            u"Всегда."),
        u"progressShowAlt": _row(
            u"Нажатие Alt", u"Показывать по клавише Alt",
            u"Показывает полосу только пока удерживается клавиша Alt. Игнорируется, пока "
            u"включено Всегда."),
        u"progressShowAlways": _row(
            u"Всегда", u"Показывать всегда",
            u"Оставляет полосу на экране постоянно; она никогда не исчезает. Имеет "
            u"приоритет над обоими переключателями выше, которые становятся серыми, пока эта "
            u"опция включена."),
        u"progressVariant": _row(
            u"Режим", u"Режим полосы",
            u"Переключает между двумя полосами, описанными выше. Вступает в силу при "
            u"следующем появлении полосы."),
        u"progressSize": _row(
            u"Масштаб", u"Масштаб полосы",
            u"Стандартный: обычный размер полосы. Большой: показывает её крупнее, для удобного "
            u"чтения на расстоянии."),
        u"progressOrientation": _row(
            u"Ориентация", u"Ориентация полосы",
            u"Горизонтальная -- исходное расположение полосы. Вертикальная показывает её "
            u"стоящей, с размерами для размещения рядом с миникартой. Вступает в силу при "
            u"следующем появлении полосы."),
        u"progressAlignment": _row(
            u"Привязка", u"Привязка полосы",
            u"От какой точки отсчитываются счётчики позиции ниже. Фиксированная: встроенное "
            u"место полосы, выбираемое автоматически по ориентации -- горизонтальная "
            u"располагается по центру нижнего края экрана, над журналом повреждений; "
            u"вертикальная располагается рядом с миникартой, у её нижнего левого угла, в "
            u"соответствии с текущим размером миникарты. Свободная: позиция без привязки, "
            u"задаётся автоматически при перетаскивании полосы или изменении счётчика. В "
            u"режиме Фиксированная позиция заблокирована; перетаскивание и счётчики ниже "
            u"работают только в режиме Свободная."),
        u"garageWidget": _row(
            u"Включено", u"Виджет в ангаре",
            u"Показывает полосу процентиля отметок классности в ангаре на выбранной "
            u"машине. Снимите галочку, чтобы скрыть."),
        u"battleWidget": _row(
            u"Включено", u"Виджет в бою",
            u"Показывает наложение отметок классности в реальном времени в бою. Снимите "
            u"галочку, чтобы скрыть его и отключить параметры ниже."),
        u"battleAltKey": _row(
            u"Нажатие Alt", u"Показывать по клавише Alt",
            u"Показывает боевое наложение только пока удерживается клавиша Alt. Когда "
            u"выключено, наложение показывается постоянно."),
        u"countedAssist": _row(
            u"Строка засчитанного содействия", u"Засчитанное содействие",
            u"Добавляет в наложение боя третью строку с вашим засчитанным содействием: "
            u"большее из содействия гусеницами, разведкой или оглушением, со значком для "
            u"преобладающего."),
        u"progressBar": _row(
            u"Включено", u"Полоса прогресса",
            u"Показывает полосу в центре экрана во время боя, затем она исчезает сама. "
            u"Удерживайте Alt, чтобы показать её в любой момент. Выберите ниже, какую полосу. "
            u"Эффективность урона: показывает ваш урон в этом бою относительно требований "
            u"отметок 65 / 85 / 95 / 100 %. Скользящее среднее: показывает, где находится ваш "
            u"прогнозируемый средний урон между имеющейся отметкой и требованием следующей."),
        u"catTransitions": _row(u"Переходы"),
        u"progressTransitions": _row(
            u"Включено", u"Переходы полосы",
            u"Полоса появляется и исчезает с плавным затуханием и сдвигом. Снимите эту галочку, "
            u"чтобы любое появление было мгновенным, либо отключите только один переключатель "
            u"ниже. События отвечают за реакцию полосы на то, что происходит в бою; Нажатие Alt "
            u"отвечает за её вызов клавишей Alt, как в самом интерфейсе игры, который при Alt "
            u"ничего не анимирует."),
        u"progressTransEvents": _row(u"События"),
        u"progressTransManual": _row(u"Нажатие Alt"),
        u"progressHoldSeconds": _row(
            u"Длительность показа (с)", u"Длительность показа",
            u"Сколько секунд полоса остаётся на экране после того, как её вызвало событие. Пока "
            u"удерживается Alt, она остаётся на экране независимо от этого значения. Появление и "
            u"исчезновение не учитываются."),
        u"positioning": _row(
            u"Расположение", u"Позиция виджета",
            u"Ctrl+перетаскивание перемещает виджет ангара (удерживайте Shift, чтобы "
            u"зафиксировать по одной оси). Счётчики ниже показывают закреплённую позицию "
            u"верхнего левого угла в пикселях; 0 / 0 означает стандартную позицию в "
            u"правом нижнем углу. Используйте сброс мода, чтобы вернуть значение по "
            u"умолчанию."),
        u"positionSub": _row(
            u"Позиция", u"Счётчики позиции",
            u"Оба счётчика ниже применяются немедленно, без необходимости перетаскивать "
            u"виджет."),
        u"posX": _row(
            u"Горизонтальная (левый X)", u"Позиция по горизонтали",
            u"Расстояние закреплённого виджета от левого края экрана в пикселях. 0 "
            u"восстанавливает автоматическую позицию в правом нижнем углу."),
        u"posY": _row(
            u"Вертикальная (верхний Y)", u"Позиция по вертикали",
            u"Расстояние закреплённого виджета от верхнего края экрана в пикселях. 0 "
            u"восстанавливает автоматическую позицию в правом нижнем углу."),
        u"catBarPosition": _row(
            u"Расположение", u"Позиция полосы в бою",
            u"В бою удерживайте Ctrl и перетащите полосу, чтобы переместить её. Счётчики ниже "
            u"показывают её закреплённую позицию в пикселях от верхнего левого угла экрана; 0 "
            u"/ 0 означает стандартную позицию по центру. Используйте сброс мода, чтобы "
            u"вернуть значение по умолчанию."),
        u"barPosX": _row(u"Горизонтальная (левый X)"),
        u"barPosY": _row(u"Вертикальная (верхний Y)"),
        u"followCarousel": _row(
            u"Следовать за каруселью", u"Следовать за каруселью",
            u"Когда включено, перетащенный виджет продолжает смещаться по вертикали "
            u"вместе с каруселью техники (один / два ряда), чтобы не перекрывать её. "
            u"Когда выключено, закреплённый виджет остаётся на месте независимо от "
            u"карусели."),
        u"variantHotkey": _row(
            u"Клавиша смены режима", u"Смена режима в бою",
            u"Клавиша, которую вы нажимаете в бою, чтобы переключить режим полосы "
            u"прогресса этой машины между Эффективностью урона и Скользящим средним. "
            u"Мод запоминает выбор для каждой машины. После переключения полоса "
            u"перезагружается и появляется снова через несколько секунд. По умолчанию: K."),
        u"progressAutoToggleThreshold": _row(
            u"Автоматическое переключение режима", u"Автоматическое переключение режима",
            u"Когда прогресс отметок машины перед боем достигает этого процента, режим "
            u"полосы переключается автоматически, так же как клавишей переключения "
            u"выше. Срабатывает только один раз на машину. 100% отключает эту функцию."),
    },

    u"uk": {
        u"catGarage": _row(u"Віджет в ангарі"),
        u"catBattleCalc": _row(u"Бойовий калькулятор"),
        u"catBattleProgress": _row(u"Прогрес у бою"),
        u"progressShowEvents": _row(
            u"Події", u"Показувати за подіями",
            u"Показує смугу самостійно, щойно в бою стається відстежувана подія, а потім "
            u"знову ховає її. Ігнорується, поки увімкнено Завжди."),
        u"progressShowAlt": _row(
            u"Натискання Alt", u"Показувати по клавіші Alt",
            u"Показує смугу лише поки утримується клавіша Alt. Ігнорується, поки увімкнено "
            u"Завжди."),
        u"progressShowAlways": _row(
            u"Завжди", u"Показувати завжди",
            u"Залишає смугу на екрані постійно; вона ніколи не зникає. Має пріоритет над "
            u"обома перемикачами вище, які стають сірими, поки цей увімкнено."),
        u"progressVariant": _row(
            u"Режим", u"Режим смуги",
            u"Перемикає між двома смугами, описаними вище. Набуває чинності під час "
            u"наступної появи смуги."),
        u"progressSize": _row(
            u"Масштаб", u"Масштаб смуги",
            u"Стандартний: звичайний розмір смуги. Великий: показує її більшою, для зручного "
            u"читання на відстані."),
        u"progressOrientation": _row(
            u"Орієнтація", u"Орієнтація смуги",
            u"Горизонтальна -- початкове розташування смуги. Вертикальна показує її "
            u"вертикально, з розміром для розміщення поруч із мінікартою. Набуває чинності "
            u"під час наступної появи смуги."),
        u"progressAlignment": _row(
            u"Прив'язка", u"Прив'язка смуги",
            u"Від якої точки відраховуються лічильники позиції нижче. Фіксована: вбудоване "
            u"місце смуги, обране автоматично залежно від орієнтації -- горизонтальна "
            u"розташовується по центру нижнього краю екрана, над журналом ушкоджень; "
            u"вертикальна розташовується поруч із мінікартою, біля її нижнього лівого кута, "
            u"відповідно до поточного розміру мінікарти. Вільна: позиція без прив'язки, "
            u"встановлюється автоматично після перетягування смуги чи зміни лічильника. У "
            u"режимі Фіксована позиція заблокована; перетягування і лічильники нижче "
            u"працюють лише в режимі Вільна."),
        u"garageWidget": _row(
            u"Увімкнено", u"Віджет в ангарі",
            u"Показує смугу процентиля позначок класності в ангарі на вибраній машині. "
            u"Зніміть позначку, щоб сховати."),
        u"battleWidget": _row(
            u"Увімкнено", u"Віджет у бою",
            u"Показує накладання позначок класності в реальному часі в бою. Зніміть "
            u"позначку, щоб сховати його та вимкнути параметри нижче."),
        u"battleAltKey": _row(
            u"Натискання Alt", u"Показувати по клавіші Alt",
            u"Показує бойове накладання лише поки утримується клавіша Alt. Коли вимкнено, "
            u"накладання показується постійно."),
        u"countedAssist": _row(
            u"Рядок зарахованої допомоги", u"Зарахована допомога",
            u"Додає третій рядок до накладання в бою: показує зараховану допомогу, більше "
            u"з допомоги гусеницями, засвітом чи оглушенням, з піктограмою відповідного "
            u"типу."),
        u"progressBar": _row(
            u"Увімкнено", u"Смуга прогресу",
            u"Показує смугу в центрі екрана під час бою, потім вона зникає сама. Утримуйте "
            u"Alt, щоб показати її будь-коли. Виберіть нижче, яку смугу. "
            u"Ефективність шкоди: показує вашу шкоду в цьому бою відносно вимог позначок "
            u"65 / 85 / 95 / 100 %. Ковзне середнє: показує, де перебуває ваша прогнозована "
            u"середня шкода між наявною позначкою та вимогою наступної."),
        u"catTransitions": _row(u"Переходи"),
        u"progressTransitions": _row(
            u"Увімкнено", u"Переходи смуги",
            u"Смуга з'являється та зникає з плавним затуханням і зсувом. Зніміть цю позначку, щоб "
            u"будь-яка поява була миттєвою, або вимкніть лише один перемикач нижче. Події "
            u"відповідають за реакцію смуги на те, що відбувається в бою; Натискання Alt "
            u"відповідає за її виклик клавішею Alt, як в інтерфейсі самої гри, який при Alt "
            u"нічого не анімує."),
        u"progressTransEvents": _row(u"Події"),
        u"progressTransManual": _row(u"Натискання Alt"),
        u"progressHoldSeconds": _row(
            u"Тривалість показу (с)", u"Тривалість показу",
            u"Скільки секунд смуга залишається на екрані після того, як її викликала подія. Поки "
            u"утримується Alt, вона залишається на екрані незалежно від цього значення. Поява та "
            u"зникнення не враховуються."),
        u"positioning": _row(
            u"Розташування", u"Позиція віджета",
            u"Ctrl+перетягування переміщує віджет ангара (утримуйте Shift, щоб "
            u"зафіксувати за однією віссю). Лічильники нижче показують закріплену позицію "
            u"верхнього лівого кута в пікселях; 0 / 0 означає стандартну позицію в правому "
            u"нижньому куті. Використайте скидання мода, щоб повернути значення за "
            u"замовчуванням."),
        u"positionSub": _row(
            u"Позиція", u"Лічильники позиції",
            u"Обидва лічильники нижче застосовуються негайно, без потреби перетягувати "
            u"віджет."),
        u"posX": _row(
            u"Горизонтальна (лівий X)", u"Позиція по горизонталі",
            u"Відстань закріпленого віджета від лівого краю екрана в пікселях. 0 "
            u"відновлює автоматичну позицію в правому нижньому куті."),
        u"posY": _row(
            u"Вертикальна (верхній Y)", u"Позиція по вертикалі",
            u"Відстань закріпленого віджета від верхнього краю екрана в пікселях. 0 "
            u"відновлює автоматичну позицію в правому нижньому куті."),
        u"catBarPosition": _row(
            u"Розташування", u"Позиція смуги в бою",
            u"У бою утримуйте Ctrl і перетягніть смугу, щоб перемістити її. Лічильники нижче "
            u"показують її закріплену позицію в пікселях від верхнього лівого кута екрана; 0 / "
            u"0 означає стандартну позицію по центру. Використайте скидання мода, щоб "
            u"повернути значення за замовчуванням."),
        u"barPosX": _row(u"Горизонтальна (лівий X)"),
        u"barPosY": _row(u"Вертикальна (верхній Y)"),
        u"followCarousel": _row(
            u"Слідувати за каруселлю", u"Слідувати за каруселлю",
            u"Коли увімкнено, перетягнутий віджет продовжує зміщуватися по вертикалі "
            u"разом із каруселлю техніки (один / два ряди), щоб ніколи її не перекривати. "
            u"Коли вимкнено, закріплений віджет залишається на місці незалежно від "
            u"каруселі."),
        u"variantHotkey": _row(
            u"Клавіша зміни режиму", u"Зміна режиму в бою",
            u"Клавіша, яку ви натискаєте в бою, щоб перемкнути режим смуги прогресу цієї "
            u"машини між Ефективністю шкоди та Ковзним середнім. Мод запам'ятовує вибір "
            u"для кожної машини. Після перемикання смуга перезавантажується і з'являється "
            u"знову через кілька секунд. За замовчуванням: K."),
        u"progressAutoToggleThreshold": _row(
            u"Автоматичне перемикання режиму", u"Автоматичне перемикання режиму",
            u"Коли прогрес позначок машини перед боєм досягає цього відсотка, режим "
            u"смуги перемикається автоматично, так само як клавішею перемикання вище. "
            u"Спрацьовує лише один раз на машину. 100% вимикає цю функцію."),
    },

    u"hu": {
        u"catGarage": _row(u"Garázs-widget"),
        u"catBattleCalc": _row(u"Csata-kalkulátor"),
        u"catBattleProgress": _row(u"Haladás a csatában"),
        u"progressShowEvents": _row(
            u"Események", u"Megjelenítés eseményekre",
            u"Magától megjeleníti a sávot, amint a csatában egy figyelt esemény történik, "
            u"majd újra eltünteti. Figyelmen kívül marad, amíg a Mindig be van kapcsolva."),
        u"progressShowAlt": _row(
            u"Alt lenyomása", u"Megjelenítés az Alt billentyűre",
            u"Csak az Alt billentyű nyomva tartása közben jeleníti meg a sávot. Figyelmen "
            u"kívül marad, amíg a Mindig be van kapcsolva."),
        u"progressShowAlways": _row(
            u"Mindig", u"Mindig megjelenítés",
            u"Végig a képernyőn tartja a sávot; sosem tűnik el. Felülbírálja a fenti két "
            u"kapcsolót, amelyek eközben szürkén jelennek meg."),
        u"progressVariant": _row(
            u"Mód", u"Sáv módja",
            u"Váltás a fent leírt két sáv között. A sáv következő megjelenésekor lép "
            u"életbe."),
        u"progressSize": _row(
            u"Méretezés", u"Sáv mérete",
            u"Alapértelmezett: a sáv normál mérete. Nagy: nagyobb méretben jeleníti meg, hogy "
            u"távolról is könnyebb legyen olvasni."),
        u"progressOrientation": _row(
            u"Tájolás", u"Sáv tájolása",
            u"A Vízszintes a sáv eredeti elrendezése. A Függőleges állva jeleníti meg, a "
            u"kistérkép mellé illő mérettel. A sáv következő megjelenésekor lép életbe."),
        u"progressAlignment": _row(
            u"Igazítás", u"Sáv igazítása",
            u"Melyik horgonyponthoz képest tolódnak el az alábbi pozíció-számlálók. "
            u"Rögzített: a sáv beépített helye, automatikusan a tájolás alapján kiválasztva "
            u"-- vízszintesen a képernyő alján középre igazítva, a sérülésnapló fölött "
            u"jelenik meg; függőlegesen a kistérkép mellett, annak bal alsó sarkánál, a "
            u"kistérkép aktuális méretéhez igazodva. Szabad: nem rögzített pozíció, "
            u"automatikusan beáll, amint elhúzod a sávot vagy módosítasz egy számlálót. "
            u"Rögzített módban a pozíció zárolva van; a húzás és az alábbi számlálók csak "
            u"Szabad módban működnek."),
        u"garageWidget": _row(
            u"Engedélyezve", u"Garázs-widget",
            u"Megjeleníti a kiválósági jelek percentilis sávját a garázsban, a "
            u"kiválasztott járművön. Vedd ki a pipát az elrejtéshez."),
        u"battleWidget": _row(
            u"Engedélyezve", u"Csata-widget",
            u"Megjeleníti az élő kiválósági jelek átfedést a csatában. Vedd ki a pipát az "
            u"elrejtéshez és az alábbi beállítások letiltásához."),
        u"battleAltKey": _row(
            u"Alt lenyomása", u"Megjelenítés az Alt billentyűre",
            u"Csak az Alt billentyű nyomva tartása közben jeleníti meg a csataátfedést. "
            u"Ha ki van kapcsolva, az átfedés mindig látható."),
        u"countedAssist": _row(
            u"Beszámított segítés sora", u"Beszámított segítés",
            u"Egy harmadik sort ad a csataátfedéshez, amely a beszámított segítésedet "
            u"mutatja: a lánctalpas, felderítő vagy kábító segítés közül a nagyobbat, a "
            u"vezető típus ikonjával."),
        u"progressBar": _row(
            u"Engedélyezve", u"Haladási sáv",
            u"Sávot jelenít meg a képernyő közepén játék közben, majd magától eltűnik. Tartsd "
            u"nyomva az Altot, hogy bármikor előhívd. Alább válaszd ki, melyik sávot. "
            u"Sebzéshatékonyság: a mostani csatában elért sebzésedet a 65 / 85 / 95 / 100 %-os "
            u"jelek követelményeihez méri. Mozgóátlag: megmutatja, hol áll a várható "
            u"átlagsebzésed a birtokolt jel és a következő jel követelménye között."),
        u"catTransitions": _row(u"Átmenetek"),
        u"progressTransitions": _row(
            u"Engedélyezve", u"A sáv átmenetei",
            u"A sáv elhalványulva és elcsúszva jelenik meg és tűnik el. Vedd ki innen a pipát, "
            u"hogy minden megjelenés azonnali legyen, vagy kapcsold ki csak az egyik alábbi "
            u"váltót. Az Események a sávnak a csatában történtekre adott reakciójára vonatkozik; "
            u"az Alt lenyomása az Alt billentyűvel való előhívásra, ahogy a játék saját felülete "
            u"is teszi, amely Altra nem animál semmit."),
        u"progressTransEvents": _row(u"Események"),
        u"progressTransManual": _row(u"Alt lenyomása"),
        u"progressHoldSeconds": _row(
            u"Megjelenítés hossza (s)", u"Megjelenítés hossza",
            u"Meddig marad a sáv a képernyőn, másodpercben, miután egy esemény előhívta. Az Alt "
            u"nyomva tartása közben ettől függetlenül látható marad. A be- és kihalványodás nincs "
            u"beszámítva."),
        u"positioning": _row(
            u"Elrendezés", u"Widget pozíciója",
            u"Ctrl+húzással mozgathatod a garázs-widgetet (tartsd nyomva a Shiftet az egy "
            u"tengelyre rögzítéshez). Az alábbi számlálók a rögzített bal felső pozíciót "
            u"mutatják pixelben; a 0 / 0 az alapértelmezett jobb alsó pozíciót jelenti. Az "
            u"alapértelmezéshez való visszatéréshez használd a mod visszaállítását."),
        u"positionSub": _row(
            u"Pozíció", u"Pozíció-számlálók",
            u"Az alábbi két számláló azonnal érvénybe lép, a widget húzása nélkül."),
        u"posX": _row(
            u"Vízszintes (bal X)", u"Vízszintes pozíció",
            u"A rögzített widget távolsága a képernyő bal szélétől, pixelben. A 0 "
            u"visszaállítja az automatikus jobb alsó pozíciót."),
        u"posY": _row(
            u"Függőleges (felső Y)", u"Függőleges pozíció",
            u"A rögzített widget távolsága a képernyő felső szélétől, pixelben. A 0 "
            u"visszaállítja az automatikus jobb alsó pozíciót."),
        u"catBarPosition": _row(
            u"Elrendezés", u"Csatasáv pozíciója",
            u"Csatában tartsd nyomva a Ctrlt, és húzd a sávot a mozgatáshoz. Az alábbi "
            u"számlálók a rögzített pozíciót mutatják pixelben a képernyő bal felső sarkától; "
            u"a 0 / 0 az alapértelmezett középső pozíciót jelenti. Az alapértelmezéshez való "
            u"visszatéréshez használd a mod visszaállítását."),
        u"barPosX": _row(u"Vízszintes (bal X)"),
        u"barPosY": _row(u"Függőleges (felső Y)"),
        u"followCarousel": _row(
            u"Körhinta követése", u"Körhinta követése",
            u"Bekapcsolva egy elhúzott widget továbbra is függőlegesen mozog a "
            u"járműkörhintával (egy / két sor) együtt, hogy sose fedje azt. Kikapcsolva "
            u"egy rögzített widget a körhintától függetlenül a helyén marad."),
        u"variantHotkey": _row(
            u"Mód váltó billentyű", u"Mód váltás csatában",
            u"A billentyű, amelyet csatában megnyomva válthatsz e jármű haladási "
            u"sávjának módja között, Sebzéshatékonyság és Mozgóátlag közt. A mod "
            u"megjegyzi az egyes járművek választását. A váltás után a sáv újratöltődik, "
            u"és néhány másodperc múlva jelenik meg újra. Alapértelmezett: K."),
        u"progressAutoToggleThreshold": _row(
            u"Automatikus mód váltás", u"Automatikus mód váltás",
            u"Amikor egy jármű jelhaladása a csata előtt eléri ezt a százalékot, a sáv "
            u"módja automatikusan átvált, ugyanúgy, mint a fenti váltóbillentyűvel. "
            u"Csak egyszer lép életbe járművenként. A 100% kikapcsolja ezt."),
    },

    u"tr": {
        u"catGarage": _row(u"Garaj widget'ı"),
        u"catBattleCalc": _row(u"Savaş hesaplayıcı"),
        u"catBattleProgress": _row(u"Savaş ilerlemesi"),
        u"progressShowEvents": _row(
            u"Olaylar", u"Olaylarda göster",
            u"Savaşta izlenen bir olay gerçekleştiğinde çubuğu kendiliğinden gösterir, "
            u"ardından yeniden gizler. Her zaman açıkken yok sayılır."),
        u"progressShowAlt": _row(
            u"Alt basımı", u"Alt tuşuyla göster",
            u"Çubuğu yalnızca Alt tuşunu basılı tutarken gösterir. Her zaman açıkken yok "
            u"sayılır."),
        u"progressShowAlways": _row(
            u"Her zaman", u"Her zaman göster",
            u"Çubuğu ekranda kalıcı olarak tutar; asla kaybolmaz. Bu açıkken soluklaşan "
            u"yukarıdaki iki anahtarın önüne geçer."),
        u"progressVariant": _row(
            u"Mod", u"Çubuk modu",
            u"Yukarıda açıklanan iki çubuk arasında geçiş yapar. Çubuğun bir sonraki "
            u"görünüşünde etkili olur."),
        u"progressSize": _row(
            u"Ölçek", u"Çubuk boyutu",
            u"Varsayılan: çubuğun normal boyutu. Büyük: uzaktan daha kolay okumak için daha "
            u"büyük gösterir."),
        u"progressOrientation": _row(
            u"Yönelim", u"Çubuk yönelimi",
            u"Yatay, çubuğun özgün düzenidir. Dikey, minimap'in yanına oturacak boyutta, "
            u"onu ayakta gösterir. Çubuğun bir sonraki görünüşünde etkili olur."),
        u"progressAlignment": _row(
            u"Hizalama", u"Çubuk hizalaması",
            u"Aşağıdaki konum sayaçlarının hangi çıpa noktasına göre kaydığı. Sabit: çubuğun "
            u"yerleşik konumu, yönelime göre otomatik seçilir -- yatayken ekranın alt "
            u"kenarının ortasında, hasar günlüğünün üstünde durur; dikeyken minimap'in "
            u"yanında, sol alt köşesine yakın, minimap'in mevcut boyutuna göre durur. "
            u"Serbest: sürüklendiğinde veya bir sayaç düzenlendiğinde otomatik olarak "
            u"ayarlanan, çıpasız bir konum. Sabit modda konum kilitlidir; sürükleme ve "
            u"aşağıdaki sayaçlar yalnızca Serbest modda çalışır."),
        u"garageWidget": _row(
            u"Etkin", u"Garaj widget'ı",
            u"Seçili araçta, garajda üstünlük işaretleri yüzdelik çubuğunu gösterir. "
            u"Gizlemek için işareti kaldır."),
        u"battleWidget": _row(
            u"Etkin", u"Savaş widget'ı",
            u"Savaş sırasında canlı üstünlük işaretleri katmanını gösterir. Gizlemek ve "
            u"aşağıdaki seçenekleri devre dışı bırakmak için işareti kaldır."),
        u"battleAltKey": _row(
            u"Alt basımı", u"Alt tuşuyla göster",
            u"Savaş katmanını yalnızca Alt tuşu basılı tutulurken gösterir. Kapalıyken "
            u"katman her zaman gösterilir."),
        u"countedAssist": _row(
            u"Sayılan yardım satırı", u"Sayılan yardım",
            u"Savaş katmanına, sayılan yardımını gösteren üçüncü bir satır ekler: palet, "
            u"tespit veya sersemletme yardımından en yükseği, öndeki için bir simgeyle."),
        u"progressBar": _row(
            u"Etkin", u"İlerleme çubuğu",
            u"Oyun sırasında ekranın ortasında bir çubuk gösterir, sonra kendiliğinden "
            u"kaybolur. Herhangi bir anda görüntülemek için Alt tuşunu basılı tut. Hangi çubuk "
            u"olacağını aşağıdan seç. "
            u"Hasar verimliliği: bu savaştaki hasarını 65 / 85 / 95 / 100 % işaretlerinin "
            u"gereksinimlerine göre konumlandırır. Hareketli ortalama: beklenen ortalama "
            u"hasarının, sahip olduğun işaret ile sonraki işaretin gereksinimi arasında nerede "
            u"olduğunu gösterir."),
        u"catTransitions": _row(u"Geçişler"),
        u"progressTransitions": _row(
            u"Etkin", u"Çubuğun geçişleri",
            u"Çubuk göründüğünde ve kaybolduğunda soluklaşarak kayar. Her görünüşün anında olması "
            u"için bunun işaretini kaldır, ya da aşağıdaki anahtarlardan yalnızca birini kapat. "
            u"Olaylar, çubuğun savaşta olanlara verdiği tepkiyi kapsar; Alt basımı ise Alt tuşuyla "
            u"çağırmayı kapsar, tıpkı Alt ile hiçbir şeyi canlandırmayan oyunun kendi arayüzü "
            u"gibi."),
        u"progressTransEvents": _row(u"Olaylar"),
        u"progressTransManual": _row(u"Alt basımı"),
        u"progressHoldSeconds": _row(
            u"Ekranda kalma süresi (s)", u"Ekranda kalma süresi",
            u"Bir olay çubuğu çağırdıktan sonra çubuğun ekranda kaç saniye kaldığı. Alt tuşu "
            u"basılı tutulduğu sürece, bu değer ne olursa olsun ekranda kalır. Giriş ve çıkış "
            u"solmaları sayılmaz."),
        u"positioning": _row(
            u"Yerleşim", u"Widget konumu",
            u"Garaj widget'ını taşımak için Ctrl+sürükle (bir eksene kilitlemek için "
            u"Shift'i basılı tut). Aşağıdaki sayaçlar, sabitlenmiş sol üst konumu piksel "
            u"cinsinden gösterir; 0 / 0 varsayılan sağ alt konumu ifade eder. Varsayılana "
            u"dönmek için modun sıfırlamasını kullan."),
        u"positionSub": _row(
            u"Konum", u"Konum sayaçları",
            u"Aşağıdaki her iki sayaç da widget'ı sürüklemeye gerek kalmadan hemen "
            u"uygulanır."),
        u"posX": _row(
            u"Yatay (sol X)", u"Yatay konum",
            u"Sabitlenmiş widget'ın ekranın sol kenarına uzaklığı, piksel cinsinden. 0, "
            u"otomatik sağ alt konumu geri yükler."),
        u"posY": _row(
            u"Dikey (üst Y)", u"Dikey konum",
            u"Sabitlenmiş widget'ın ekranın üst kenarına uzaklığı, piksel cinsinden. 0, "
            u"otomatik sağ alt konumu geri yükler."),
        u"catBarPosition": _row(
            u"Yerleşim", u"Savaştaki çubuk konumu",
            u"Savaşta Ctrl'yi basılı tut ve çubuğu taşımak için sürükle. Aşağıdaki sayaçlar "
            u"sabitlenmiş konumu ekranın sol üst köşesinden piksel cinsinden gösterir; 0 / 0 "
            u"varsayılan ortalanmış konumu ifade eder. Varsayılana dönmek için modun "
            u"sıfırlamasını kullan."),
        u"barPosX": _row(u"Yatay (sol X)"),
        u"barPosY": _row(u"Dikey (üst Y)"),
        u"followCarousel": _row(
            u"Karuseli takip et", u"Karuseli takip et",
            u"Açıkken, sürüklenen bir widget araç karuseliyle (tek / çift sıra) birlikte "
            u"dikey olarak kaymayı sürdürür, böylece onu asla örtmez. Kapalıyken, "
            u"sabitlenmiş bir widget karuselden bağımsız olarak yerinde kalır."),
        u"variantHotkey": _row(
            u"Mod Değiştirme Tuşu", u"Savaşta mod değiştirme",
            u"Bu aracın ilerleme çubuğu modunu Hasar verimliliği ile Hareketli ortalama "
            u"arasında değiştirmek için savaşta bastığın tuş. Mod her aracın seçimini "
            u"hatırlar. Değiştirdikten sonra çubuk yeniden yüklenir ve birkaç saniye sonra "
            u"yeniden görünür. Varsayılan: K."),
        u"progressAutoToggleThreshold": _row(
            u"Otomatik Mod Değiştirme", u"Otomatik mod değiştirme",
            u"Bir aracın işaret ilerlemesi savaştan önce bu yüzdeye ulaştığında, çubuk "
            u"modu yukarıdaki değiştirme tuşuyla aynı şekilde otomatik olarak değişir. "
            u"Araç başına yalnızca bir kez tetiklenir. %100 bunu kapatır."),
    },
}


def resolve(lang):
    """The merged ``{key: entry}`` for ``lang`` (PURE, engine-free -- the testable core).

    Each key comes from ``lang``'s block if present, else falls back to the English
    entry FOR THAT KEY. An unknown/empty code yields the full English bundle."""
    en = _PANEL[DEFAULT_LANGUAGE]
    tbl = _PANEL.get(_norm(lang)) or {}
    out = {}
    for k in en:
        out[k] = tbl.get(k, en[k])
    return out


def _render(entry, mark=False):
    """Turn one panel ``entry`` into the ``{"text", "tooltip"}`` the MSA template wants,
    assembling the ``{HEADER}/{BODY}`` markup once. A label-only entry (no ``tt*``) has
    no ``tooltip`` key. When ``mark`` (an English fallback and ``i18n.MARK_UNTRANSLATED``
    is on) the text/tooltip are underscore-tagged, matching the widget's diagnostic."""
    out = {u"text": entry.get(u"label", u"")}
    if u"ttHeader" in entry or u"ttBody" in entry:
        out[u"tooltip"] = u"{HEADER}%s{/HEADER}{BODY}%s{/BODY}" % (
            entry.get(u"ttHeader", u""), entry.get(u"ttBody", u""))
    if mark:
        out[u"text"] = i18n._mark(out[u"text"])
        if u"tooltip" in out:
            out[u"tooltip"] = i18n._mark(out[u"tooltip"])
    return out


def _options(table, code):
    """The localized option tuple for one option-bearing control (PURE). WHOLE-TUPLE fallback,
    not per-option: the options are one ordered set whose meaning is positional, so a
    half-translated tuple would be worse than plain English (marked when the diagnostic is on)."""
    opts = table.get(code)
    if opts:
        return tuple(opts)
    return tuple(i18n._mark(o) for o in table[DEFAULT_LANGUAGE])


def build(lang):
    """The rendered panel text for ``lang``: ``{key: {"text", "tooltip"}}`` (PURE), plus an
    ``"options"`` tuple on each of the FOUR option-bearing controls (``VARIANT_KEY``,
    ``"progressSize"``, ``"progressOrientation"`` and ``"progressAlignment"``).

    A key the language didn't translate is rendered from English and marked (when
    ``i18n.MARK_UNTRANSLATED`` is on) so English leaks are spottable in-client.

    The six ``HEADER_KEYS`` come out wrapped in ``<b>...</b>`` (MSA Labels render HTML).
    The wrap happens HERE and ONLY here -- never in the ``_PANEL`` tables (translation data
    stays markup-free) and never in ``mod_settings._template()`` -- and AFTER the fallback
    mark, so a marked fallback stays visible inside it. Both consumers of this function must
    see the SAME string: ``_template()`` builds the fresh template from it, and
    ``_sync_template_text()`` compares a STORED component's text against it. If ``_label()``
    wrapped independently, every ``register()`` call -- including the one that just built the
    freshly-bolded template -- would see a mismatch, strip the bold back out, and fire a
    pointless ``saveState()``; one source of truth makes that divergence impossible by
    construction."""
    code = _norm(lang)
    en = _PANEL[DEFAULT_LANGUAGE]
    tbl = _PANEL.get(code) or {}
    out = {}
    for k, en_entry in en.items():
        translated = k in tbl
        out[k] = _render(tbl.get(k, en_entry), mark=not translated)
    for k in HEADER_KEYS:
        out[k][u"text"] = u"<b>%s</b>" % out[k][u"text"]
    # All four radios have a normal _PANEL row (their "Mode" / "Scale" / "Orientation" /
    # "Alignment" labels), so all build() adds is the option tuple -- and it rides on the
    # RENDERED entry (where mod_settings._radio reads it) rather than in _PANEL, so the
    # positional COL*_KEYS partition stays label/tooltip-only.
    #
    # NOTE these option-label tuples are STRUCTURAL to MSA (see the tables' own comments above):
    # Aslain folds them into its _settingsStructure signature and _sync_template_text never
    # rewrites options[].label, so reordering one later is a SILENT VALUE MIGRATION that nothing
    # raises on -- a stored option INDEX suddenly names a different option. Get the order right
    # once; a SETTINGS_VERSION bump is the only way to fix it after the fact.
    out[VARIANT_KEY][u"options"] = _options(_VARIANT_OPTIONS, code)
    out[u"progressSize"][u"options"] = _options(_SIZE_OPTIONS, code)
    out[u"progressOrientation"][u"options"] = _options(_ORIENTATION_OPTIONS, code)
    out[u"progressAlignment"][u"options"] = _options(_ALIGNMENT_OPTIONS, code)
    return out


def client_language():
    """The client's active language code, normalized to a table key -- the ONE engine
    read here. Guarded + lazy-imported so the module still imports under pytest and a
    missing/renamed helper degrades to English rather than raising into MSA setup."""
    try:
        import helpers
        return _norm(helpers.getClientLanguage()) or DEFAULT_LANGUAGE
    except Exception:
        LOG_CURRENT_EXCEPTION()
        return DEFAULT_LANGUAGE


def panel_text():
    """The rendered panel text for the CLIENT's active language (public entry point for
    mod_settings). English on any read failure."""
    return build(client_language())
