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

Both radios (``VARIANT_KEY`` = "Mode" and ``progressSize`` = "Scale") are normal ``_PANEL`` rows;
``build()`` only bolts their language-dependent OPTION tuples (``_VARIANT_OPTIONS`` /
``_SIZE_OPTIONS``) onto the rendered entry, where ``mod_settings._radio`` reads them.

The panel is grouped into three CATEGORIES, each a bare label header row (``catBattleCalc`` /
``catBattleProgress`` in column 1, ``catGarage`` in column 2) followed by that feature's
controls, with an ``Empty`` spacer row between them. A category row is text-only: no ``varName``
and NO tooltip, so its ``_row`` carries a label alone and ``_render`` emits no ``tooltip`` key.
Because the header names the feature, each feature's master checkbox is simply labelled
"Enabled" (was "Show"). ``build()`` wraps every category header (plus the "Layout" header --
see ``HEADER_KEYS``) in ``<b>...</b>``; ``mod_settings._label`` then only adds the matching
``useHTML`` key and never touches the text itself, so ``_template()`` and
``_sync_template_text()`` always compare byte-identical strings (see ``build()``'s docstring
for why that matters). The ``positionSub`` ("Position") row that heads the two steppers is
deliberately excluded from ``HEADER_KEYS``, so the weight difference reads as hierarchy. An
``Empty`` row has no text at all, so ``COL1_KEYS`` / ``COL2_KEYS`` give it a ``None`` sentinel
slot rather than a key -- see those tuples.

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

# Ordered key list per column -- the wire order of the controls in the MSA template. Used by
# mod_settings to walk a stored template in lockstep. Column 1 is TWO CATEGORIES separated by an
# Empty spacer row: "Battle Calculator" (the In-Battle Widget master + its two children), then
# "Battle Progress" (the Progress Bar master + its three VISIBILITY children, the standalone Mode
# and Scale radios, then the Transitions master + its two children -- a SECOND group under the same
# category header, so it adds no cat* row). Column 2 is the "Garage Widget" category header, the
# garage master, a spacer, then the "Layout" group. Only two columns -- a third does not render in
# the panel at all.
#
# EVERY control gets a slot, including the ones that carry no varName (the cat* headers) -- the zip
# in _sync_template_text is POSITIONAL, so a missing key here pairs every LATER control with the
# wrong text. A row with no text AT ALL (the Empty spacers) takes a `None` SENTINEL slot rather
# than a key: the sync walk's `if not rendered: continue` then skips it for free, with no
# type-sniffing branch and with the alignment intact.
COL1_KEYS = (u"catBattleCalc", u"battleWidget", u"battleAltKey", u"countedAssist",
             None,
             u"catBattleProgress", u"progressBar",
             u"progressShowEvents", u"progressShowAlt", u"progressShowAlways",
             VARIANT_KEY, u"progressSize",
             u"progressTransitions", u"progressTransEvents", u"progressTransManual")
# Column 2: the category header, the standalone In-Garage Widget master, a spacer, then the
# "Layout" group -- its bold header, Follow Carousel, a non-bold "Position" sub-label, then the
# X/Y numeric steppers (in that exact control order, so _sync_template_text walks it in lockstep).
# EIGHT slots (grew from seven): "positionSub" is the new sub-label heading the two steppers.
COL2_KEYS = (u"catGarage", u"garageWidget", None, u"positioning", u"followCarousel",
             u"positionSub", u"posX", u"posY")

# The four CATEGORY/GROUP header keys that render BOLD (see build()). "positionSub"
# ("Position") is deliberately EXCLUDED -- it is the non-bold sub-label under "Layout", and
# the weight difference is what makes the hierarchy read.
HEADER_KEYS = frozenset((u"catBattleCalc", u"catBattleProgress", u"catGarage", u"positioning"))

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
    u"pl": (u"Domyślny", u"Duży"),
    u"cs": (u"Výchozí", u"Velká"),
    u"ru": (u"Стандартная", u"Большая"),
    u"uk": (u"Стандартна", u"Велика"),
    u"hu": (u"Alapértelmezett", u"Nagy"),
    u"tr": (u"Varsayılan", u"Büyük"),
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
        # Both radios carry a label and no tooltip -- their option labels say it all. The options
        # themselves come from _VARIANT_OPTIONS / _SIZE_OPTIONS via build().
        u"progressVariant": _row(u"Mode"),
        u"progressSize": _row(u"Scale"),
        # The Transitions master + its two children. Only the MASTER carries a tooltip: the two
        # children are one-word switches whose meaning the master's prose spells out, so they are
        # label-only rows (no tt* -> _render emits no tooltip key).
        u"progressTransitions": _row(
            u"Transitions", u"Bar transitions",
            u"The bar fades and slides when it appears and disappears. Turn a switch off to make "
            u"it appear and disappear instantly instead. Events covers the bar reacting to what "
            u"happens in battle; Alt Press covers bringing it up with the Alt key, matching the "
            u"game's own interface, which does not animate on Alt."),
        u"progressTransEvents": _row(u"Events"),
        u"progressTransManual": _row(u"Alt Press"),
        # --- drag-to-reposition group (translated across every shipped language; see COL2_KEYS). ---
        u"positioning": _row(
            u"Layout", u"Widget position",
            u"Ctrl+drag the Garage widget to move it (hold Shift to lock to one axis). The "
            u"steppers below show its pinned top-left position in pixels; 0 / 0 means the "
            u"default bottom-right position. Use the per-mod Reset to return to default."),
        u"positionSub": _row(u"Position"),
        u"posX": _row(
            u"Horizontal (left X)", u"Horizontal position",
            u"The pinned widget's distance from the left screen edge, in pixels. 0 restores "
            u"the automatic bottom-right position."),
        u"posY": _row(
            u"Vertical (top Y)", u"Vertical position",
            u"The pinned widget's distance from the top screen edge, in pixels. 0 restores "
            u"the automatic bottom-right position."),
        u"followCarousel": _row(
            u"Follow Carousel", u"Follow Carousel Mode",
            u"When on, a dragged widget keeps shifting vertically with the vehicle carousel "
            u"(single / double rows) so it never overlaps it. When off, a pinned widget stays "
            u"fixed regardless of the carousel."),
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
        u"progressVariant": _row(u"Modus"),
        u"progressSize": _row(u"Skalierung"),
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
        u"progressTransitions": _row(
            u"Übergänge", u"Übergänge der Leiste",
            u"Die Leiste blendet ein und gleitet, wenn sie erscheint und verschwindet. Deaktiviere "
            u"einen Schalter, damit sie stattdessen sofort erscheint und verschwindet. Ereignisse "
            u"betrifft die Reaktion der Leiste auf das Geschehen im Gefecht; Alt drücken betrifft "
            u"das Einblenden mit der Alt-Taste, wie in der Spieloberfläche selbst, die bei Alt "
            u"nichts animiert."),
        u"progressTransEvents": _row(u"Ereignisse"),
        u"progressTransManual": _row(u"Alt drücken"),
        u"positioning": _row(
            u"Layout", u"Widget-Position",
            u"Ziehe das Garage-Widget mit Strg+Ziehen, um es zu verschieben (halte "
            u"Umschalt gedrückt, um es auf eine Achse zu beschränken). Die Felder unten "
            u"zeigen seine fixierte Position oben links in Pixeln; 0 / 0 bedeutet die "
            u"Standardposition unten rechts. Nutze das Zurücksetzen des Mods, um zum "
            u"Standard zurückzukehren."),
        u"positionSub": _row(u"Position"),
        u"posX": _row(
            u"Horizontal (links X)", u"Horizontale Position",
            u"Abstand des fixierten Widgets vom linken Bildschirmrand in Pixeln. 0 stellt "
            u"die automatische Position unten rechts wieder her."),
        u"posY": _row(
            u"Vertikal (oben Y)", u"Vertikale Position",
            u"Abstand des fixierten Widgets vom oberen Bildschirmrand in Pixeln. 0 stellt "
            u"die automatische Position unten rechts wieder her."),
        u"followCarousel": _row(
            u"Karussell folgen", u"Karussell folgen",
            u"Wenn aktiviert, verschiebt sich ein gezogenes Widget weiterhin vertikal mit "
            u"dem Fahrzeugkarussell (eine / zwei Reihen), sodass es dieses nie überdeckt. "
            u"Wenn deaktiviert, bleibt ein fixiertes Widget unabhängig vom Karussell an "
            u"seiner Stelle."),
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
        u"progressVariant": _row(u"Mode"),
        u"progressSize": _row(u"Échelle"),
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
        u"progressTransitions": _row(
            u"Transitions", u"Transitions de la barre",
            u"La barre s'estompe et glisse lorsqu'elle apparaît et disparaît. Désactivez un "
            u"interrupteur pour qu'elle apparaisse et disparaisse instantanément. Événements "
            u"concerne la réaction de la barre à ce qui se passe en bataille ; Appui sur Alt "
            u"concerne son affichage avec la touche Alt, comme l'interface du jeu elle-même, qui "
            u"n'anime rien avec Alt."),
        u"progressTransEvents": _row(u"Événements"),
        u"progressTransManual": _row(u"Appui sur Alt"),
        u"positioning": _row(
            u"Disposition", u"Position du widget",
            u"Ctrl+glisser pour déplacer le widget du garage (maintenez Maj pour le "
            u"verrouiller sur un axe). Les compteurs ci-dessous indiquent sa position "
            u"épinglée en haut à gauche, en pixels ; 0 / 0 correspond à la position par "
            u"défaut en bas à droite. Utilisez la réinitialisation du mod pour revenir au "
            u"réglage par défaut."),
        u"positionSub": _row(u"Position"),
        u"posX": _row(
            u"Horizontal (X gauche)", u"Position horizontale",
            u"Distance du widget épinglé par rapport au bord gauche de l'écran, en "
            u"pixels. 0 rétablit la position automatique en bas à droite."),
        u"posY": _row(
            u"Vertical (Y haut)", u"Position verticale",
            u"Distance du widget épinglé par rapport au bord supérieur de l'écran, en "
            u"pixels. 0 rétablit la position automatique en bas à droite."),
        u"followCarousel": _row(
            u"Suivre le carrousel", u"Suivre le carrousel",
            u"Activé, un widget déplacé continue de se décaler verticalement avec le "
            u"carrousel des véhicules (une / deux rangées) afin de ne jamais le "
            u"chevaucher. Désactivé, un widget épinglé reste fixe quel que soit le "
            u"carrousel."),
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
        u"progressVariant": _row(u"Modo"),
        u"progressSize": _row(u"Escala"),
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
        u"progressTransitions": _row(
            u"Transiciones", u"Transiciones de la barra",
            u"La barra se atenúa y desliza al aparecer y desaparecer. Desactiva un interruptor "
            u"para que aparezca y desaparezca al instante. Eventos se refiere a la barra "
            u"reaccionando a lo que ocurre en la batalla; Pulsar Alt se refiere a mostrarla con "
            u"la tecla Alt, igual que la interfaz del propio juego, que no anima nada con Alt."),
        u"progressTransEvents": _row(u"Eventos"),
        u"progressTransManual": _row(u"Pulsar Alt"),
        u"positioning": _row(
            u"Disposición", u"Posición del widget",
            u"Ctrl+arrastrar para mover el widget del garaje (mantén Mayús para "
            u"bloquearlo en un eje). Los contadores de abajo muestran su posición fijada "
            u"de la esquina superior izquierda, en píxeles; 0 / 0 es la posición "
            u"predeterminada en la esquina inferior derecha. Usa el restablecimiento del "
            u"mod para volver al valor predeterminado."),
        u"positionSub": _row(u"Posición"),
        u"posX": _row(
            u"Horizontal (X izquierda)", u"Posición horizontal",
            u"Distancia del widget fijado al borde izquierdo de la pantalla, en píxeles. "
            u"0 restaura la posición automática en la esquina inferior derecha."),
        u"posY": _row(
            u"Vertical (Y superior)", u"Posición vertical",
            u"Distancia del widget fijado al borde superior de la pantalla, en píxeles. 0 "
            u"restaura la posición automática en la esquina inferior derecha."),
        u"followCarousel": _row(
            u"Seguir el carrusel", u"Seguir el carrusel",
            u"Cuando está activado, un widget arrastrado sigue desplazándose "
            u"verticalmente con el carrusel de vehículos (una / dos filas) para no "
            u"superponerse a él. Cuando está desactivado, un widget fijado permanece fijo "
            u"sin importar el carrusel."),
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
        u"progressVariant": _row(u"Modalità"),
        u"progressSize": _row(u"Scala"),
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
        u"progressTransitions": _row(
            u"Transizioni", u"Transizioni della barra",
            u"La barra sfuma e scorre quando appare e scompare. Disattiva un interruttore perché "
            u"appaia e scompaia istantaneamente. Eventi riguarda la barra che reagisce a ciò che "
            u"accade in battaglia; Premi Alt riguarda il richiamarla con il tasto Alt, come "
            u"l'interfaccia del gioco stesso, che con Alt non anima nulla."),
        u"progressTransEvents": _row(u"Eventi"),
        u"progressTransManual": _row(u"Premi Alt"),
        u"positioning": _row(
            u"Disposizione", u"Posizione del widget",
            u"Ctrl+trascina per spostare il widget del garage (tieni premuto Maiusc per "
            u"bloccarlo su un asse). I contatori sotto mostrano la sua posizione fissata "
            u"in alto a sinistra, in pixel; 0 / 0 indica la posizione predefinita in "
            u"basso a destra. Usa il ripristino del mod per tornare al valore "
            u"predefinito."),
        u"positionSub": _row(u"Posizione"),
        u"posX": _row(
            u"Orizzontale (X sinistra)", u"Posizione orizzontale",
            u"Distanza del widget fissato dal bordo sinistro dello schermo, in pixel. 0 "
            u"ripristina la posizione automatica in basso a destra."),
        u"posY": _row(
            u"Verticale (Y alto)", u"Posizione verticale",
            u"Distanza del widget fissato dal bordo superiore dello schermo, in pixel. 0 "
            u"ripristina la posizione automatica in basso a destra."),
        u"followCarousel": _row(
            u"Segui il carosello", u"Segui il carosello",
            u"Quando è attivo, un widget trascinato continua a spostarsi verticalmente "
            u"con il carosello dei veicoli (una / due file) in modo da non sovrapporsi "
            u"mai ad esso. Quando è disattivato, un widget fissato resta fermo "
            u"indipendentemente dal carosello."),
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
        u"progressVariant": _row(u"Tryb"),
        u"progressSize": _row(u"Skala"),
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
        u"progressTransitions": _row(
            u"Przejścia", u"Przejścia paska",
            u"Pasek pojawia się i znika z przygaszeniem oraz przesunięciem. Wyłącz przełącznik, "
            u"aby pojawiał się i znikał natychmiast. Zdarzenia dotyczą reakcji paska na to, co "
            u"dzieje się w bitwie; Naciśnij Alt dotyczy wywołania go klawiszem Alt, tak jak w "
            u"interfejsie samej gry, który przy Alt nic nie animuje."),
        u"progressTransEvents": _row(u"Zdarzenia"),
        u"progressTransManual": _row(u"Naciśnij Alt"),
        u"positioning": _row(
            u"Układ", u"Pozycja widżetu",
            u"Ctrl+przeciągnij, aby przesunąć widżet garażu (przytrzymaj Shift, aby "
            u"zablokować do jednej osi). Liczniki poniżej pokazują przypiętą pozycję "
            u"lewego górnego rogu w pikselach; 0 / 0 oznacza domyślną pozycję w prawym "
            u"dolnym rogu. Użyj resetu moda, aby wrócić do wartości domyślnej."),
        u"positionSub": _row(u"Pozycja"),
        u"posX": _row(
            u"Poziomo (lewy X)", u"Pozycja pozioma",
            u"Odległość przypiętego widżetu od lewej krawędzi ekranu, w pikselach. 0 "
            u"przywraca automatyczną pozycję w prawym dolnym rogu."),
        u"posY": _row(
            u"Pionowo (górny Y)", u"Pozycja pionowa",
            u"Odległość przypiętego widżetu od górnej krawędzi ekranu, w pikselach. 0 "
            u"przywraca automatyczną pozycję w prawym dolnym rogu."),
        u"followCarousel": _row(
            u"Podążaj za karuzelą", u"Podążaj za karuzelą",
            u"Gdy włączone, przeciągnięty widżet nadal przesuwa się w pionie wraz z "
            u"karuzelą pojazdów (jeden / dwa rzędy), aby nigdy jej nie zasłaniać. Gdy "
            u"wyłączone, przypięty widżet pozostaje na miejscu niezależnie od karuzeli."),
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
        u"progressVariant": _row(u"Režim"),
        u"progressSize": _row(u"Měřítko"),
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
        u"progressTransitions": _row(
            u"Přechody", u"Přechody lišty",
            u"Lišta se při zobrazení a zmizení prolíná a posouvá. Vypnutím přepínače se bude "
            u"zobrazovat a mizet okamžitě. Události se týkají reakce lišty na to, co se děje v "
            u"bitvě; Stisk Alt se týká jejího vyvolání klávesou Alt, stejně jako v rozhraní "
            u"samotné hry, které při Altu nic neanimuje."),
        u"progressTransEvents": _row(u"Události"),
        u"progressTransManual": _row(u"Stisk Alt"),
        u"positioning": _row(
            u"Rozvržení", u"Pozice widgetu",
            u"Ctrl+táhnutím přesuneš widget garáže (podržením Shift jej uzamkneš na jednu "
            u"osu). Čítače níže ukazují jeho ukotvenou pozici levého horního rohu v "
            u"pixelech; 0 / 0 znamená výchozí pozici vpravo dole. Pro návrat na výchozí "
            u"hodnotu použij reset modu."),
        u"positionSub": _row(u"Pozice"),
        u"posX": _row(
            u"Vodorovně (levé X)", u"Vodorovná pozice",
            u"Vzdálenost ukotveného widgetu od levého okraje obrazovky v pixelech. 0 "
            u"obnoví automatickou pozici vpravo dole."),
        u"posY": _row(
            u"Svisle (horní Y)", u"Svislá pozice",
            u"Vzdálenost ukotveného widgetu od horního okraje obrazovky v pixelech. 0 "
            u"obnoví automatickou pozici vpravo dole."),
        u"followCarousel": _row(
            u"Sledovat kolotoč", u"Sledovat kolotoč",
            u"Když je zapnuto, tažený widget se dál posouvá svisle spolu s kolotočem "
            u"vozidel (jedna / dvě řady), aby jej nikdy nepřekrýval. Když je vypnuto, "
            u"ukotvený widget zůstává na místě bez ohledu na kolotoč."),
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
        u"progressVariant": _row(u"Режим"),
        u"progressSize": _row(u"Масштаб"),
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
        u"progressTransitions": _row(
            u"Переходы", u"Переходы полосы",
            u"Полоса появляется и исчезает с плавным затуханием и сдвигом. Отключите "
            u"переключатель, чтобы она появлялась и исчезала мгновенно. События отвечают за "
            u"реакцию полосы на то, что происходит в бою; Нажатие Alt отвечает за её вызов "
            u"клавишей Alt, как в самом интерфейсе игры, который при Alt ничего не анимирует."),
        u"progressTransEvents": _row(u"События"),
        u"progressTransManual": _row(u"Нажатие Alt"),
        u"positioning": _row(
            u"Расположение", u"Позиция виджета",
            u"Ctrl+перетаскивание перемещает виджет ангара (удерживайте Shift, чтобы "
            u"зафиксировать по одной оси). Счётчики ниже показывают закреплённую позицию "
            u"верхнего левого угла в пикселях; 0 / 0 означает стандартную позицию в "
            u"правом нижнем углу. Используйте сброс мода, чтобы вернуть значение по "
            u"умолчанию."),
        u"positionSub": _row(u"Позиция"),
        u"posX": _row(
            u"Горизонталь (левый X)", u"Позиция по горизонтали",
            u"Расстояние закреплённого виджета от левого края экрана в пикселях. 0 "
            u"восстанавливает автоматическую позицию в правом нижнем углу."),
        u"posY": _row(
            u"Вертикаль (верхний Y)", u"Позиция по вертикали",
            u"Расстояние закреплённого виджета от верхнего края экрана в пикселях. 0 "
            u"восстанавливает автоматическую позицию в правом нижнем углу."),
        u"followCarousel": _row(
            u"Следовать за каруселью", u"Следовать за каруселью",
            u"Когда включено, перетащенный виджет продолжает смещаться по вертикали "
            u"вместе с каруселью техники (один / два ряда), чтобы не перекрывать её. "
            u"Когда выключено, закреплённый виджет остаётся на месте независимо от "
            u"карусели."),
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
        u"progressVariant": _row(u"Режим"),
        u"progressSize": _row(u"Масштаб"),
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
        u"progressTransitions": _row(
            u"Переходи", u"Переходи смуги",
            u"Смуга з'являється та зникає з плавним затуханням і зсувом. Вимкніть перемикач, щоб "
            u"вона з'являлася та зникала миттєво. Події відповідають за реакцію смуги на те, що "
            u"відбувається в бою; Натискання Alt відповідає за її виклик клавішею Alt, як в "
            u"інтерфейсі самої гри, який при Alt нічого не анімує."),
        u"progressTransEvents": _row(u"Події"),
        u"progressTransManual": _row(u"Натискання Alt"),
        u"positioning": _row(
            u"Розташування", u"Позиція віджета",
            u"Ctrl+перетягування переміщує віджет ангара (утримуйте Shift, щоб "
            u"зафіксувати за однією віссю). Лічильники нижче показують закріплену позицію "
            u"верхнього лівого кута в пікселях; 0 / 0 означає стандартну позицію в правому "
            u"нижньому куті. Використайте скидання мода, щоб повернути значення за "
            u"замовчуванням."),
        u"positionSub": _row(u"Позиція"),
        u"posX": _row(
            u"Горизонталь (лівий X)", u"Позиція по горизонталі",
            u"Відстань закріпленого віджета від лівого краю екрана в пікселях. 0 "
            u"відновлює автоматичну позицію в правому нижньому куті."),
        u"posY": _row(
            u"Вертикаль (верхній Y)", u"Позиція по вертикалі",
            u"Відстань закріпленого віджета від верхнього краю екрана в пікселях. 0 "
            u"відновлює автоматичну позицію в правому нижньому куті."),
        u"followCarousel": _row(
            u"Слідувати за каруселлю", u"Слідувати за каруселлю",
            u"Коли увімкнено, перетягнутий віджет продовжує зміщуватися по вертикалі "
            u"разом із каруселлю техніки (один / два ряди), щоб ніколи її не перекривати. "
            u"Коли вимкнено, закріплений віджет залишається на місці незалежно від "
            u"каруселі."),
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
        u"progressVariant": _row(u"Mód"),
        u"progressSize": _row(u"Méretezés"),
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
        u"progressTransitions": _row(
            u"Átmenetek", u"A sáv átmenetei",
            u"A sáv elhalványulva és elcsúszva jelenik meg és tűnik el. Kapcsolj ki egy váltót, "
            u"hogy azonnal jelenjen meg és tűnjön el. Az Események a sávnak a csatában "
            u"történtekre adott reakciójára vonatkozik; az Alt lenyomása az Alt billentyűvel való "
            u"előhívásra, ahogy a játék saját felülete is teszi, amely Altra nem animál semmit."),
        u"progressTransEvents": _row(u"Események"),
        u"progressTransManual": _row(u"Alt lenyomása"),
        u"positioning": _row(
            u"Elrendezés", u"Widget pozíciója",
            u"Ctrl+húzással mozgathatod a garázs-widgetet (tartsd nyomva a Shiftet az egy "
            u"tengelyre rögzítéshez). Az alábbi számlálók a rögzített bal felső pozíciót "
            u"mutatják pixelben; a 0 / 0 az alapértelmezett jobb alsó pozíciót jelenti. Az "
            u"alapértelmezéshez való visszatéréshez használd a mod visszaállítását."),
        u"positionSub": _row(u"Pozíció"),
        u"posX": _row(
            u"Vízszintes (bal X)", u"Vízszintes pozíció",
            u"A rögzített widget távolsága a képernyő bal szélétől, pixelben. A 0 "
            u"visszaállítja az automatikus jobb alsó pozíciót."),
        u"posY": _row(
            u"Függőleges (felső Y)", u"Függőleges pozíció",
            u"A rögzített widget távolsága a képernyő felső szélétől, pixelben. A 0 "
            u"visszaállítja az automatikus jobb alsó pozíciót."),
        u"followCarousel": _row(
            u"Körhinta követése", u"Körhinta követése",
            u"Bekapcsolva egy elhúzott widget továbbra is függőlegesen mozog a "
            u"járműkörhintával (egy / két sor) együtt, hogy sose fedje azt. Kikapcsolva "
            u"egy rögzített widget a körhintától függetlenül a helyén marad."),
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
        u"progressVariant": _row(u"Mod"),
        u"progressSize": _row(u"Ölçek"),
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
        u"progressTransitions": _row(
            u"Geçişler", u"Çubuğun geçişleri",
            u"Çubuk göründüğünde ve kaybolduğunda soluklaşarak kayar. Anında görünüp kaybolması "
            u"için bir anahtarı kapat. Olaylar, çubuğun savaşta olanlara verdiği tepkiyi kapsar; "
            u"Alt basımı ise Alt tuşuyla çağırmayı kapsar, tıpkı Alt ile hiçbir şeyi "
            u"canlandırmayan oyunun kendi arayüzü gibi."),
        u"progressTransEvents": _row(u"Olaylar"),
        u"progressTransManual": _row(u"Alt basımı"),
        u"positioning": _row(
            u"Yerleşim", u"Widget konumu",
            u"Garaj widget'ını taşımak için Ctrl+sürükle (bir eksene kilitlemek için "
            u"Shift'i basılı tut). Aşağıdaki sayaçlar, sabitlenmiş sol üst konumu piksel "
            u"cinsinden gösterir; 0 / 0 varsayılan sağ alt konumu ifade eder. Varsayılana "
            u"dönmek için modun sıfırlamasını kullan."),
        u"positionSub": _row(u"Konum"),
        u"posX": _row(
            u"Yatay (sol X)", u"Yatay konum",
            u"Sabitlenmiş widget'ın ekranın sol kenarına uzaklığı, piksel cinsinden. 0, "
            u"otomatik sağ alt konumu geri yükler."),
        u"posY": _row(
            u"Dikey (üst Y)", u"Dikey konum",
            u"Sabitlenmiş widget'ın ekranın üst kenarına uzaklığı, piksel cinsinden. 0, "
            u"otomatik sağ alt konumu geri yükler."),
        u"followCarousel": _row(
            u"Karuseli takip et", u"Karuseli takip et",
            u"Açıkken, sürüklenen bir widget araç karuseliyle (tek / çift sıra) birlikte "
            u"dikey olarak kaymayı sürdürür, böylece onu asla örtmez. Kapalıyken, "
            u"sabitlenmiş bir widget karuselden bağımsız olarak yerinde kalır."),
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
    ``"options"`` tuple on each of the two option-bearing controls (``VARIANT_KEY`` and
    ``"progressSize"``).

    A key the language didn't translate is rendered from English and marked (when
    ``i18n.MARK_UNTRANSLATED`` is on) so English leaks are spottable in-client.

    The four ``HEADER_KEYS`` come out wrapped in ``<b>...</b>`` (MSA Labels render HTML).
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
    # Both radios have a normal _PANEL row (their "Mode" / "Scale" labels), so all build() adds is
    # the option tuple -- and it rides on the RENDERED entry (where mod_settings._radio reads it)
    # rather than in _PANEL, so the positional COL*_KEYS partition stays label/tooltip-only.
    out[VARIANT_KEY][u"options"] = _options(_VARIANT_OPTIONS, code)
    out[u"progressSize"][u"options"] = _options(_SIZE_OPTIONS, code)
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
