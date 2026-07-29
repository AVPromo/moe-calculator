# 14th_ua's MoE Calculator — World of Tanks mod

Track your **Marks of Excellence (MoE)** progress for the vehicle you have selected,
in the Garage and live in battle. The mod reads the game's own MoE data and renders it
with the client's own mark art and interface styling, so it looks like a built-in part
of the interface rather than an add-on.

**English** · [Українська](#14th_uas-moe-calculator--українська)

|  |  |
|:--:|:--:|
| ![Garage MoE bar](assets/screenshots/garage.png) | ![In-battle MoE overlay](assets/screenshots/battle.png) |
| Garage MoE bar | In-battle overlay |

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
scoreboard is open, while you are spectating, and before you have a vehicle.

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

The panel has two columns.

**Column 1 — in battle.**

**In-Battle Widget** *(on by default)* — shows the live MoE overlay during battle. Uncheck to
hide it and disable the two options below. When it's on, these become available:

- **Show on Alt Key** *(off by default)* — shows the in-battle overlay only while the **Alt**
  key is held. When off, the overlay is shown at all times.
- **Counted Assistance** *(off by default)* — adds a third row to the battle overlay showing
  your counted assistance: the higher of tracking, spotting or stun assist, with an icon for
  whichever is leading.

**Progress Bar** *(off by default)* — shows the transient centre-screen bar. It's a separate
feature from the In-Battle Widget, so it works whether that one is on or off. Beneath it, two
options pick which bar you get:

- **Moving Average** *(default)* — your projected average against the next mark's requirement.
- **Damage Efficiency** — this battle's damage against the 65 / 85 / 95 / 100 % requirements.

**Column 2 — in the Garage.**

**In-Garage Widget** *(on by default)* — shows the MoE percentile bar in the Garage, on the
selected vehicle. Uncheck to hide it.

**Widget position (px)** — where the Garage widget is pinned. **Ctrl+drag** the widget to move
it (hold **Shift** to lock to one axis); the two steppers below show the pinned top-left
position in pixels:

- **Horizontal (left X)** / **Vertical (top Y)** — distance from the left / top screen edge.
  **0 / 0** means the default bottom-right position, which is also what the panel's per-mod
  **Reset** restores.
- **Follow Carousel Mode** *(on by default)* — a dragged widget keeps shifting vertically with
  the vehicle carousel (single / double rows) so it never overlaps it. When off, a pinned
  widget stays put regardless of the carousel.

These position settings apply to the Garage widget only — the in-battle overlay and the
centre-screen progress bar are not movable.

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

Панель складається з двох стовпців.

**Стовпець 1 — у бою.**

**Віджет у бою** *(увімкнено за замовчуванням)* — показує накладання класності наживо в бою.
Зніміть позначку, щоб сховати його та вимкнути два параметри нижче. Коли він увімкнений, стають
доступними:

- **Показувати по клавіші Alt** *(вимкнено за замовчуванням)* — показує бойове накладання лише
  поки утримується клавіша **Alt**. Коли вимкнено, накладання показується постійно.
- **Зарахована допомога** *(вимкнено за замовчуванням)* — додає третій рядок до накладання в
  бою: показує зараховану допомогу, більше з допомоги гусеницями, засвітом чи оглушенням, з
  піктограмою відповідного типу.

**Смуга прогресу** *(вимкнено за замовчуванням)* — показує тимчасову смугу в центрі екрана. Це
окрема функція від Віджета в бою, тож вона працює незалежно від того, увімкнений той чи ні. Нижче
два варіанти вибирають, яку смугу ви отримаєте:

- **Ковзне середнє** *(за замовчуванням)* — ваша прогнозована середня шкода відносно вимоги
  наступної позначки.
- **Ефективність шкоди** — шкода цього бою відносно вимог 65 / 85 / 95 / 100 %.

**Стовпець 2 — в Ангарі.**

**Віджет в ангарі** *(увімкнено за замовчуванням)* — показує смугу процентиля класності в
Ангарі на вибраній машині. Зніміть позначку, щоб сховати.

**Позиція віджета (px)** — де закріплений віджет Ангара. **Ctrl+перетягування** переміщує віджет
(утримуйте **Shift**, щоб зафіксувати за однією віссю); два лічильники нижче показують
закріплену позицію верхнього лівого кута в пікселях:

- **Горизонталь (лівий X)** / **Вертикаль (верхній Y)** — відстань від лівого / верхнього краю
  екрана. **0 / 0** означає стандартну позицію в правому нижньому куті, яку також повертає
  кнопка **скидання** мода в панелі.
- **Слідувати за каруселлю** *(увімкнено за замовчуванням)* — перетягнутий віджет продовжує
  зміщуватися по вертикалі разом із каруселлю техніки (один / два ряди), щоб ніколи її не
  перекривати. Коли вимкнено, закріплений віджет залишається на місці незалежно від каруселі.

Ці параметри позиції стосуються лише віджета в Ангарі — накладання в бою та смугу прогресу в
центрі екрана переміщувати не можна.

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
