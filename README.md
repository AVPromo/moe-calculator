# 14th_ua's MoE Calculator — World of Tanks mod

Track your **Marks of Excellence (MoE)** progress for the vehicle you have selected,
in the Garage and live in battle. The mod reads the game's own MoE data and renders it
with the client's own mark art and interface styling, so it looks like a built-in part
of the interface rather than an add-on.

**English** · [Українська](#14th_uas-moe-calculator--українська)

|  |  |
|:--:|:--:|
| ![In-battle MoE overlay](assets/screenshots/battle.png) | ![Garage MoE bar](assets/screenshots/garage.png) |
| In-battle overlay | Garage MoE bar |
| ![Progress bar — Moving Average](assets/screenshots/progress_moving_average.png) | ![Progress bar — Damage Efficiency](assets/screenshots/progress_damage_efficiency.png) |
| Progress bar — Moving Average | Progress bar — Damage Efficiency |

## What it shows

### Garage MoE bar

A percentile bar in the vehicle-parameters panel with milestone ticks at **65% / 85% /
95%** — the 1 / 2 / 3-mark thresholds — each drawn with the client's own mark art. Every
tick is labelled with the combined damage that mark requires, and the bar fills to your
current standing. Above it, a readout shows your current average combined damage and your
current mark percentage for the selected vehicle.

**Ctrl+drag** the widget to move it anywhere on screen (hold **Shift** to lock the drag to
one axis). Where you drop it is remembered; the panel also has numeric position fields and a
**Follow Carousel Mode** option — see Settings.

### In-battle overlay

A compact overlay over the HUD with two lines (an optional third row shows counted
assistance — see Settings):

- **Live combined damage vs your projected average** — the number is coloured by sign
  (red below your projection, white at it, green above).
- **Your projected MoE percentage** with the signed change versus where you started the
  battle.

### In-battle progress bar *(off by default)*

A wide bar in the **centre of the screen**, separate from the corner overlay. It fades in
when there is something new to show, holds for about five seconds, then fades out on its own.
**Hold Alt** to bring it up at any time — that works regardless of the overlay's "Show on Alt
Key" setting. The bar never takes mouse input, and it stays hidden while the **Tab**
scoreboard is open, while you are spectating, and before you have a vehicle. Settings let you
draw it **Large** and switch the fades off so it appears and disappears instantly.

Turn it on in Settings and pick **one** of two bars — they are mutually exclusive:

- **Moving Average** *(default)* — where your career projected average combined damage sits
  between the mark you already hold and the next mark's requirement, with this battle's signed
  contribution beside it. It comes up whenever that projection moves. It needs a career
  baseline, so it shows nothing in replays, or after a relogin until you have visited the
  Garage.
- **Damage Efficiency** — this battle's combined damage against all four requirements
  (**65% / 85% / 95% / 100%**) laid out on four equal quarters, with every requirement you
  have already passed lit up. No baseline needed, and it comes up on its own each time your
  damage this battle reaches a new high.

The bar's position is **not** configurable: the **Widget position (px)** fields and **Follow
Carousel Mode** apply to the Garage widget only. On a vehicle whose mark thresholds could not
be fetched, neither bar draws — the Garage bar still does.

## Compatibility

| Requirement | Detail |
|-------------|--------|
| **Game** | World of Tanks **EU 2.3.1.0** (Wargaming global client). Built and tested against this version. |
| **Required** | **OpenWG GameFace** 1.1.6+ — install it first, or the widget will not appear. From [wgmods.net](https://wgmods.net) or [gitlab.com/openwg/wot.gameface](https://gitlab.com/openwg/wot.gameface). |

## Download & install

**Easiest — the one-click installer (Windows).** Download the latest
**`MoECalculator-Setup-<version>.exe`** from the
[**GitHub Releases**](https://github.com/drizzer14/moe-calculator/releases) page and run
it (close the game first). It finds your World of Tanks folder, installs the mod into
`mods\<version>\`, and adds its bundled dependencies — **OpenWG GameFace**,
**ModsSettingsAPI**, and **ModsList** — for any you don't already have. On each
run it also checks GitHub and offers to fetch the newest
installer, so a copy you keep around stays current.

**Manual installation.** Grab `com.14th_ua.moe_calculator_<version>.wotmod` from the same
Releases page and follow **[`INSTALL.md`](./INSTALL.md)** — it covers the manual copy,
verifying it works, troubleshooting, and uninstalling.

## Settings

The mod adds a settings panel to the in-game **mod-settings menu**, provided by
**ModsSettingsAPI (MSA)** — the standard settings host bundled with the installer. If MSA
isn't loaded, the mod still runs with both widgets on by default; you just won't see the panel.

The panel is grouped into named **categories**, each a plain header row followed by that
feature's controls — so a feature's own on/off switch is simply labelled **Show**. Column 1
holds the two in-battle features, column 2 the Garage one:

| Setting | Default | What it does |
|---|---|---|
| *Battle Calculator* | — | Category header for the in-battle overlay. |
| **Show** | On | Shows the live MoE overlay during battle. |
| ↳ **Show on Alt Key** | Off | Shows the overlay only while **Alt** is held; when off it is visible at all times. |
| ↳ **Counted Assistance** | Off | Adds a third overlay row: the higher of tracking, spotting or stun assist, with an icon for whichever leads. |
| *Battle Progress* | — | Category header for the centre-screen progress bar. |
| **Show** | Off | Shows the centre-screen bar, which fades out on its own; hold **Alt** to bring it back. Pick the mode and size below. |
| ↳ *(mode)* | Moving Average | The two mutually exclusive modes, **Moving Average** and **Damage Efficiency** — the panel shows them as an unlabelled pair of radio buttons. |
| ↳ **Size** | Default | **Default** or **Large**. Large redraws the whole bar half again as tall and twice as wide — same layout, just bigger. |
| **Transitions** | On | The bar fades and slides as it appears and disappears. Turn a switch below off to make it appear and disappear **instantly** instead; the bar still shows and still hides, only the motion is skipped. |
| ↳ **Events** | On | Animates the bar when something in battle brings it up (a damage tick) and lets it go again. |
| ↳ **Manual** | On | Animates the **Alt** peek. Off matches the game's own interface, which does not animate on Alt. |
| *Garage Widget* | — | Category header for the Garage bar. |
| **Show** | On | Shows the MoE percentile bar in the Garage, on the selected vehicle. |
| **Widget position (px)** | — | Header only: **Ctrl+drag** the Garage widget to pin it (hold **Shift** to lock to one axis). |
| **Horizontal (left X)** | 0 = auto | The pinned widget's distance from the left screen edge, in pixels. |
| **Vertical (top Y)** | 0 = auto | The same for the top screen edge. |
| **Follow Carousel Mode** | On | A pinned widget keeps shifting vertically with the vehicle carousel (single / double rows) so it never overlaps it. |

Unchecking a checkbox that has indented children (the two **Show** boxes in column 1, and
**Transitions**) greys those children out; the Garage settings have no such master. **Transitions**
sits alongside the progress bar's own **Show** rather than under it, so it stays clickable while the
bar is off — it simply has nothing to affect until you switch the bar on. **0 / 0** is the default
bottom-right position, which is also what the panel's per-mod **Reset** restores. The position
settings apply to the Garage widget only — the in-battle overlay and the centre-screen progress bar
are not movable. What each progress-bar mode shows, and the career baseline **Moving Average**
needs, is described under *In-battle progress bar* above.

## Notes

- **After a game update**, move the `.wotmod` to the new `mods\<version>\` folder. A new
  client version may need a rebuilt mod — check the Releases page.

## MoE data source

The per-tank mark thresholds (the combined damage each mark needs) come from the **official
Wargaming API** — the real damage distribution, so the numbers are authoritative and current.
Thresholds are cached locally so switching vehicles is instant.

## Modpacks & license

Free to use, redistribute, and include in modpacks as long as it stays free and credits the
author (**14th_ua**) with a link back to this repository — see [`LICENSE.md`](./LICENSE.md).
For modpacks, add only the `.wotmod` and list OpenWG GameFace as a required dependency; don't
bundle GameFace yourself.

## Contributing / developers

Building, deploying, testing, and the repo layout are documented in
[`CLAUDE.md`](./CLAUDE.md) (and the dev loop in [`tools/dev/README.md`](./tools/dev/README.md)).

---

# 14th_ua's MoE Calculator — Українська

Відстежуйте прогрес **Знаків Класності** (Marks of Excellence) для обраної техніки — в
Ангарі та наживо в бою. Мод читає власні дані гри про класність і малює їх рідними іконками
та стилем інтерфейсу клієнта, тож він виглядає як вбудована частина інтерфейсу, а не
стороннє доповнення.

[English](#14th_uas-moe-calculator--world-of-tanks-mod) · **Українська**

|  |  |
|:--:|:--:|
| ![Смуга класності в Ангарі](assets/screenshots/garage.png) | ![Оверлей у бою](assets/screenshots/battle.png) |
| Смуга класності в Ангарі | Оверлей у бою |
| ![Смуга прогресу — Ковзне середнє](assets/screenshots/progress_moving_average.png) | ![Смуга прогресу — Ефективність шкоди](assets/screenshots/progress_damage_efficiency.png) |
| Смуга прогресу — Ковзне середнє | Смуга прогресу — Ефективність шкоди |

## Що показує

### Смуга класності в Ангарі

Смуга за перцентилем у панелі параметрів техніки з позначками на **65% / 85% / 95%** —
пороги 1 / 2 / 3 знаків — кожна намальована рідною іконкою знака з клієнта. Кожна позначка
підписана комбінованою шкодою, потрібною для цього знака, а смуга заповнюється до вашого
поточного стану. Над нею — ваша поточна середня комбінована шкода й поточний відсоток знака
для обраної техніки.

**Ctrl+перетягування** переміщує віджет у будь-яке місце екрана (утримуйте **Shift**, щоб
зафіксувати перетягування за однією віссю). Місце, де ви його відпустили, запам'ятовується; у
панелі також є числові поля позиції та параметр **Слідувати за каруселлю** — див. Налаштування.

### Оверлей у бою

Компактний оверлей над HUD із двома рядками (необов'язковий третій рядок показує зараховану
допомогу — див. Налаштування):

- **Поточна комбінована шкода проти прогнозованого середнього** — число забарвлене за знаком
  (червоне нижче прогнозу, біле на рівні, зелене вище).
- **Прогнозований відсоток знака** зі знаком зміни відносно початку бою.

### Смуга прогресу в бою *(вимкнено за замовчуванням)*

Широка смуга в **центрі екрана**, окрема від кутового оверлея. Вона з'являється, коли є що
показати, тримається близько п'яти секунд і зникає сама. **Утримуйте Alt**, щоб показати її
будь-коли — це працює незалежно від параметра оверлея «Показувати по клавіші Alt». Смуга ніколи
не перехоплює керування мишею й залишається схованою, поки відкрита таблиця результатів
(**Tab**), під час спостереження за іншим гравцем і доки у вас немає техніки.

Увімкніть її в Налаштуваннях і виберіть **одну** з двох смуг — вони взаємовиключні:

- **Ковзне середнє** *(за замовчуванням)* — де перебуває ваша прогнозована середня комбінована
  шкода за кар'єру між наявною позначкою та вимогою наступної, з підписаним внеском цього бою
  поруч. З'являється щоразу, коли цей прогноз змінюється. Потребує базового значення кар'єри,
  тож у реплеях, а також після повторного входу, доки ви не зайшли в Ангар, вона нічого не
  показує.
- **Ефективність шкоди** — шкода цього бою відносно всіх чотирьох вимог (**65% / 85% / 95% /
  100%**), розкладених на чотири рівні чверті, з підсвіченими вимогами, які ви вже пройшли. Не
  потребує базового значення й з'являється сама щоразу, коли ваша шкода в цьому бою досягає
  нового максимуму.

Позиція смуги **не** налаштовується: поля **Позиція віджета (px)** та **Слідувати за каруселлю**
стосуються лише віджета в Ангарі. На техніці, для якої не вдалося отримати пороги знаків, жодна
зі смуг не малюється — смуга в Ангарі все одно працює.

## Сумісність

| Вимога | Деталі |
|--------|--------|
| **Гра** | World of Tanks **EU 2.3.1.0** (глобальний клієнт Wargaming). Зібрано й перевірено для цієї версії. |
| **Обов'язково** | **OpenWG GameFace** 1.1.6+ — встановіть першим, інакше віджет не з'явиться. З [wgmods.net](https://wgmods.net) або [gitlab.com/openwg/wot.gameface](https://gitlab.com/openwg/wot.gameface). |

## Завантаження та встановлення

**Найпростіше — інсталятор в один клік (Windows).** Завантажте найновіший
**`MoECalculator-Setup-<version>.exe`** зі сторінки
[**релізів на GitHub**](https://github.com/drizzer14/moe-calculator/releases) і запустіть
(спершу закрийте гру). Він знаходить папку World of Tanks, встановлює мод у `mods\<version>\`
і додає вкладені залежності — **OpenWG GameFace**, **ModsSettingsAPI** та **ModsList** — для
тих, яких ще немає. Під час кожного запуску
він також перевіряє GitHub і пропонує завантажити найновіший інсталятор, тож збережена копія
залишається актуальною.

**Встановлення вручну.** Візьміть `com.14th_ua.moe_calculator_<version>.wotmod` з тієї ж
сторінки релізів і дотримуйтесь **[`INSTALL.md`](./INSTALL.md)** — там описано ручне
копіювання, перевірку роботи, усунення несправностей і видалення.

## Налаштування

Мод додає панель до внутрішньоігрового **меню налаштувань модів**, яке надає
**ModsSettingsAPI (MSA)** — стандартний застосунок налаштувань, що йде разом з інсталятором.
Якщо MSA не завантажено, мод усе одно працює з увімкненими за замовчуванням віджетами — просто
не буде панелі.

Стовпець 1 містить параметри для бою, стовпець 2 — для Ангара:

| Налаштування | За замовчуванням | Що робить |
|---|---|---|
| **Віджет у бою** | Увімк. | Показує накладання класності наживо під час бою. |
| ↳ **Показувати по клавіші Alt** | Вимк. | Показує накладання лише поки утримується **Alt**; коли вимкнено — показує постійно. |
| ↳ **Зарахована допомога** | Вимк. | Додає третій рядок накладання: більше з допомоги гусеницями, засвітом чи оглушенням, з піктограмою переважного типу. |
| **Смуга прогресу** | Вимк. | Показує смугу в центрі екрана, яка зникає сама; утримуйте **Alt**, щоб повернути її. Режим виберіть нижче. |
| ↳ **Режим** | Ковзне середнє | Вибір між двома взаємовиключними режимами — **Ковзне середнє** та **Ефективність шкоди**; у панелі це пара радіокнопок без підпису. |
| **Віджет в ангарі** | Увімк. | Показує смугу процентиля класності в Ангарі на вибраній машині. |
| **Позиція віджета (px)** | — | Лише заголовок: **Ctrl+перетягування** закріплює віджет Ангара (**Shift** фіксує за однією віссю). |
| **Горизонталь (лівий X)** | 0 = авто | Відстань закріпленого віджета від лівого краю екрана в пікселях. |
| **Вертикаль (верхній Y)** | 0 = авто | Те саме для верхнього краю екрана. |
| **Слідувати за каруселлю** | Увімк. | Закріплений віджет продовжує зміщуватися по вертикалі разом із каруселлю техніки (один / два ряди), щоб ніколи її не перекривати. |

Знята позначка з головного параметра (**Віджет у бою**, **Смуга прогресу**) робить його вкладені
рядки неактивними; параметри Ангара головного не мають. **0 / 0** — стандартна позиція в правому
нижньому куті, яку також повертає кнопка **скидання** мода в панелі. Параметри позиції стосуються
лише віджета в Ангарі — накладання в бою та смугу прогресу в центрі екрана переміщувати не можна.
Що показує кожен режим смуги прогресу і яке базове значення кар'єри потрібне для **Ковзного
середнього** — описано вище в розділі *Смуга прогресу в бою*.

## Примітки

- **Після оновлення гри** перемістіть `.wotmod` у нову папку `mods\<версія>\`. Нова версія
  клієнта може потребувати перезібраного мода — перевіряйте сторінку релізів.

## Джерело даних класності

Пороги знаків для кожної техніки (комбінована шкода, потрібна для знака) беруться з
**офіційного API Wargaming** — це реальний розподіл шкоди, тож числа автентичні й актуальні.
Пороги кешуються локально, тож перемикання техніки миттєве.

## Модпаки та ліцензія

Вільно використовувати, поширювати та включати в модпаки, доки це залишається безкоштовним і
зазначає автора (**14th_ua**) з посиланням на цей репозиторій — див. [`LICENSE.md`](./LICENSE.md).
Для модпаків додавайте лише `.wotmod` і вкажіть OpenWG GameFace як обов'язкову залежність; не
вкладайте GameFace самі.

## Розробка

Збірка, розгортання, тести та структура репозиторію описані в [`CLAUDE.md`](./CLAUDE.md) (а
цикл розробки — у [`tools/dev/README.md`](./tools/dev/README.md)).
