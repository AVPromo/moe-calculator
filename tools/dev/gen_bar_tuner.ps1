<#
  gen_bar_tuner.ps1 -- PowerShell (pwsh 7+ / Windows PowerShell 5.1). Run from the repo root:

      pwsh tools\dev\gen_bar_tuner.ps1 [-Out TASKS/refs/in-battle-bar-tuner.html]
                                       [-Backdrop <any image>] [-ExtractIcons] [-SelfCheck]
                                       [-EmitCss [-CssOut TASKS/refs/MoEProgress.css]]

  Emits ONE self-contained HTML tuner for the NEW in-battle centre-screen MoE progress bar
  (class prefix .mp-, mirrors the shipped overlay's .mb-). The bar does not exist in the mod
  yet -- this tuner IS its design surface, and its "Copy CSS" output is the handoff into the
  eventual MoEProgress.css. Rationale: a registered Gameface battle WINDOW cannot be
  hot-reloaded, so every CSS tweak in-game costs a full client relaunch (same reason
  gen_overlay_tuner.ps1 exists).

  Assets (backdrop jpg / MoEBattle.ttf / checker.png / the 6 tick icons) are base64-inlined so
  the HTML works from any path with no sibling files. The tuner runs in a BROWSER, where the
  in-game img:// scheme does not resolve -- hence the inlining; the EMITTED css still carries
  img:// urls.

  -ExtractIcons pulls the 6 needed PNGs out of the client's gui-part{1..4}.pkg into
  TASKS/refs/icons/ using gen_icon_picker.ps1's flat "__" naming (they are SCATTERED across all
  four packages, so all four are scanned). Idempotent: already-present files are skipped. Run it
  once; afterwards plain generation just inlines them, and a MISSING icon aborts BY PATH.

  -EmitCss writes the settled stylesheet to a REAL FILE (-CssOut, default
  TASKS/refs/MoEProgress.css) instead of leaving it in the browser's clipboard: it runs the
  generated HTML's own <script> in a headless DOM shim under node and CLICKS the Copy CSS
  button, so the bytes are the button's bytes -- cssOut() is never re-implemented here (a
  PowerShell copy of it would drift the moment a slider changes). Needs node on PATH.
  Phase 2 copies the result to src/res/gui/gameface/mods/14th_ua/MoECalculator/MoEProgress.css.

  -Backdrop takes ANY image (e.g. a raw 3840x2160 WoT screenshot) and resizes it to the
  stage's exact 1600x900 -- no manual pre-resize step. A source that is not 16:9 is
  CENTRE-CROPPED, never distorted: the stage geometry and the SCALE = 1600/3840 calibration
  both assume a 16:9 frame. Omit it and the pre-encoded default is inlined verbatim
  (tuner-backdrop-ribbon.jpg -- a shot with a REAL WG fly-up ribbon at ~74vh; the older
  no-ribbon tuner-backdrop.jpg stays beside it as the previous reference).
#>
param(
  [string]$Out = "TASKS/refs/in-battle-bar-tuner.html",
  [string]$Backdrop,
  [string]$GameDir = "D:/Games/World_of_Tanks_EU",
  [switch]$ExtractIcons,
  [switch]$SelfCheck,
  [switch]$EmitCss,
  [string]$CssOut = "TASKS/refs/MoEProgress.css"
)
$ErrorActionPreference = "Stop"

# Repo root from this script's location (tools/dev -> tools -> repo). Never hardcode a
# session scratchpad path -- gen_overlay_tuner.ps1 did and its $out is now dead.
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

function Asset($rel) {
  $p = Join-Path $repo $rel
  if (-not (Test-Path $p)) { throw "gen_bar_tuner: missing asset -> $p (run with -ExtractIcons if this is TASKS/refs/icons/)" }
  [Convert]::ToBase64String([IO.File]::ReadAllBytes($p))
}

# ---- tick icons -------------------------------------------------------------------------
# Inner res paths, and the flat repo-relative name each lands under (gen_icon_picker.ps1's
# scheme: drop the gui/maps/icons/ prefix, "/" -> "__"). TASKS/refs is gitignored, so these
# are LOCAL artifacts -- re-extract with -ExtractIcons on a fresh clone.
$ICONS = @(
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_damage.png',
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_barrel_mark.png',
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_top.png',
  'gui/maps/icons/library/marksOnGun/mark_1.png',
  'gui/maps/icons/library/marksOnGun/mark_2.png',
  'gui/maps/icons/library/marksOnGun/mark_3.png'
)
function IconRel($inner) { "TASKS/refs/icons/" + (($inner -replace '^gui/maps/icons/', '') -replace '/', '__') }

# Idempotent: only the missing ones are hunted, and the scan stops early once none are left.
# The 6 files live in DIFFERENT gui-part packages (damage=2, barrel_mark+mark_1=3, mark_2=4,
# mark_3+top=1), so all four are opened rather than guessing. Each ZipArchive is disposed -- a
# leaked handle keeps a 1.3 GB package open.
function ExtractIconsNow {
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $dir = Join-Path $repo "TASKS/refs/icons"
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $want = @{}
  foreach ($i in $ICONS) { $d = Join-Path $repo (IconRel $i); if (-not (Test-Path -LiteralPath $d)) { $want[$i] = $d } }
  if ($want.Count -eq 0) { Write-Output "icons: all $($ICONS.Count) already present -> $dir"; return }
  foreach ($n in 1..4) {
    if ($want.Count -eq 0) { break }
    $pkg = Join-Path $GameDir "res/packages/gui-part$n.pkg"
    if (-not (Test-Path -LiteralPath $pkg)) { throw "gen_bar_tuner: missing package -> $pkg" }
    $zip = [IO.Compression.ZipFile]::OpenRead($pkg)
    try {
      foreach ($e in $zip.Entries) {
        $dest = $want[$e.FullName]
        if ($dest) {
          [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $dest, $true)
          Write-Output ("  gui-part{0}.pkg -> {1}" -f $n, (Split-Path $dest -Leaf))
          $want.Remove($e.FullName)
        }
      }
    } finally { $zip.Dispose() }
  }
  if ($want.Count) { throw "gen_bar_tuner: not found in any gui-part pkg -> $($want.Keys -join ', ')" }
}
if ($ExtractIcons) { ExtractIconsNow }


# -Backdrop: resize ANY image to the stage's exact 1600x900, JPEG q82, inline it, bin the temp.
# Non-16:9 sources are CENTRE-CROPPED (see the header). Every GDI+ handle is disposed --
# a leaked Image locks the source file on Windows.
function Backdrop64($path) {
  $p = if ([IO.Path]::IsPathRooted($path)) { $path } else { Join-Path $repo $path }
  if (-not (Test-Path -LiteralPath $p)) { throw "gen_bar_tuner: -Backdrop not found -> $p" }
  Add-Type -AssemblyName System.Drawing
  try { $src = [Drawing.Image]::FromFile($p) }
  catch { throw "gen_bar_tuner: -Backdrop is not a decodable image -> $p ($($_.Exception.Message))" }
  $tmp = Join-Path ([IO.Path]::GetTempPath()) "gen_bar_tuner_bg.jpg"
  $bmp = $null; $g = $null
  try {
    $cw = $src.Width; $ch = [int][Math]::Round($src.Width * 9.0 / 16.0)
    if ($ch -gt $src.Height) { $ch = $src.Height; $cw = [int][Math]::Round($src.Height * 16.0 / 9.0) }
    $cx = [int](($src.Width - $cw) / 2); $cy = [int](($src.Height - $ch) / 2)
    $bmp = New-Object Drawing.Bitmap 1600, 900
    $g = [Drawing.Graphics]::FromImage($bmp)
    $g.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $g.PixelOffsetMode   = [Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.DrawImage($src, (New-Object Drawing.Rectangle 0, 0, 1600, 900),
                 $cx, $cy, $cw, $ch, [Drawing.GraphicsUnit]::Pixel)
    $enc = [Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq "image/jpeg" }
    $ep = New-Object Drawing.Imaging.EncoderParameters 1
    $ep.Param[0] = New-Object Drawing.Imaging.EncoderParameter ([Drawing.Imaging.Encoder]::Quality), 82
    $bmp.Save($tmp, $enc, $ep); $ep.Dispose()
  } finally { if ($g) { $g.Dispose() }; if ($bmp) { $bmp.Dispose() }; $src.Dispose() }
  try { [Convert]::ToBase64String([IO.File]::ReadAllBytes($tmp)) }
  finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
}

# Default = the pre-encoded 1600x900 shot (inlined as-is; no pointless re-encode).
$bg  = if ($Backdrop) { Backdrop64 $Backdrop } else { Asset "TASKS/refs/tuner-backdrop-ribbon.jpg" }
$ttf = Asset "src/res/gui/gameface/mods/14th_ua/MoECalculator/MoEBattle.ttf"     # 19-glyph numeric subset -- NO LETTERS
$ck  = Asset "src/res/gui/gameface/mods/14th_ua/MoECalculator/checker.png"       # 4px tile = 2x2 cells @2px (gen_checker.py)
# 128x128 RGBA quest-type glyphs + the 24x24 marksOnGun cuts. Missing -> Asset throws by path.
$ico = @{}
foreach ($i in $ICONS) { $ico[[IO.Path]::GetFileNameWithoutExtension($i)] = Asset (IconRel $i) }

$tpl = @'
<!DOCTYPE html><meta charset="utf-8"><title>MoE in-battle progress bar - tuner</title>
<style>
  /* The REAL game font, the single cut the mod bundles. Every weight maps to it (no synthesis).
     19-GLYPH NUMERIC SUBSET: digits and % ( ) + - , . / and space. NO LETTERS -- any word
     label inside #moe-bar-root renders BLANK. Panel chrome uses a system font on purpose. */
  @font-face{font-family:"MoEBattle";font-weight:400;font-style:normal;src:url(data:font/ttf;base64,__TTF__) format("truetype")}
  @font-face{font-family:"MoEBattle";font-weight:500;font-style:normal;src:url(data:font/ttf;base64,__TTF__) format("truetype")}
  @font-face{font-family:"MoEBattle";font-weight:600;font-style:normal;src:url(data:font/ttf;base64,__TTF__) format("truetype")}
  @font-face{font-family:"MoEBattle";font-weight:700;font-style:normal;src:url(data:font/ttf;base64,__TTF__) format("truetype")}
  :root{--bg:#14151a;--panel:#1d2027;--ink:#e9e6df;--muted:#8b93a1;--line:#2b2f38;--gold:#c79a3f}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI",system-ui,sans-serif;display:flex;min-height:100vh}
  .stagewrap{flex:1;display:flex;align-items:flex-start;justify-content:center;padding:20px;overflow:auto}
  .stage{position:relative;width:1600px;height:900px;flex:none;border-radius:6px;overflow:hidden;background-color:#000;
    background-image:url("data:image/jpeg;base64,__BG__");background-size:cover;background-position:center;background-repeat:no-repeat;
    box-shadow:0 10px 40px rgba(0,0,0,.5);outline:1px solid var(--line)}
  .stage.drop{outline:2px dashed var(--gold)}

  /* ================= THE BAR UNDER DESIGN (.mp-*, mirrors the shipped .mb-*) =================
     TUNER-ONLY wrapper: it owns the stage centring (left:50% + translateX(-50%)) so that
     #moe-bar-root's transform is free for the slide keyframes. In-game a second WindowImpl
     positions the window from Python, so the emitted CSS has neither the wrapper nor any vw/vh.
     All the --custom props are set on the wrapper and INHERIT down. Base opacity 0: .mp-hold
     pins it visible for tuning, .mp-run plays the transient sequence. */
  .mp-anchor{position:absolute;left:50%;top:var(--top);margin-left:var(--offx);
    transform:translateX(-50%);width:var(--barw);z-index:9000;pointer-events:none}
  #moe-bar-root{position:relative;width:100%;
    font-family:"MoEBattle","Arial Narrow",sans-serif;text-align:center;opacity:0}
  #moe-bar-root.mp-hold{opacity:1}
  /* Backdrop -- the .mb-backdrop two-layer trick verbatim: checker dither on ::before over a
     dark radial underlay on ::after (z-index:-1, scoped by the backdrop's own z-index:0).
     EXPLICIT width+height, single top/left anchor -- Coherent collapses top+bottom stretches. */
  .mp-backdrop{position:absolute;left:var(--bdleft);top:var(--bdtop);width:var(--bdw);height:var(--bdh);z-index:0}
  .mp-backdrop::before{content:"";position:absolute;left:0;top:0;width:100%;height:100%;
    background:var(--ckbg) repeat;background-size:var(--cksize);background-position:0 0;
    image-rendering:pixelated;opacity:var(--dotop);-webkit-mask:var(--dotmask);mask:var(--dotmask)}
  .mp-backdrop::after{content:"";position:absolute;left:0;top:0;width:100%;height:100%;z-index:-1;background:var(--uggrad)}
  /* Track/fill/ticks: EXPLICIT dimensions (Gameface animates nothing it cannot measure). */
  .mp-track{position:relative;z-index:1;width:100%;height:var(--trackh);background:var(--trackbg)}
  /* GARAGE TREATMENT, cloned onto this track (MoECalculator.css:284-296): the hangar bar's dash
     grid + its ring. The garage gets the dashes from WG's own art, bg_pattern_small.png (a 99x2
     strip = 2rem dash + 1rem gap, cream rgb(236,230,218) @ alpha 41/255 = 0.16, repeat-x at
     background-size:99rem 2rem) -- a browser cannot resolve img://, so the SAME geometry is
     re-drawn as a repeating-linear-gradient and each number is a slider. The garage's "border" is
     NOT a border: it is `box-shadow: 0 0 0 1rem rgba(13,14,16,0.5)` -- an OUTSET ring, which is
     why it never disturbed the box model. Both live on ONE pseudo: it takes an explicit
     left/top/width/height box (Coherent will not stretch from a dual anchor), z-index:1 puts BOTH
     gradient stripes ABOVE the auto-z .mp-fill -- and the GAP stripe is a REAL DARK COLOUR, not
     `transparent`, because that is what the garage actually does: the hangar's .moe-fill
     (MoECalculator.css:304-326) has NO background-color at all -- it paints filled_pattern_small.png
     ONLY, in phase with the track's bg_pattern_small (same 99rem 2rem / left center) -- so its
     transparent gaps show the dark track backing and the fill exists ONLY inside the dash marks.
     The garage grid is therefore a MASK, not an overlay. Our .mp-fill is a SOLID colour, so an
     OPAQUE gap stripe (gapA:1) is what reproduces that read; gapA:0 gives back the old fully
     transparent gap (fill at full strength between the dashes). The gradient sits on the TRACK's
     pseudo, so its origin is the track's LEFT EDGE and the phase is identical across the reached
     and unreached halves whatever the fill width. Still BELOW the z-index:2 ticks, and the ring's outset spread paints
     OUTSIDE the track box -- so trackH is untouched, the tick/bdTop centring cannot shift, and
     the fill sits flush inside the ring at 0% and at 100%. Putting the ring here rather than on
     .mp-track also keeps it alive under .mp-full / .mp-pulse, which both overwrite the track's
     own box-shadow. --dashbg / --bdrsh go to `none` when their checkbox is off. */
  .mp-track::after{content:"";position:absolute;left:0;top:0;width:100%;height:100%;z-index:1;
    background:var(--dashbg);box-shadow:var(--bdrsh)}
  .mp-fill{position:absolute;left:0;top:0;height:100%;width:0;background:var(--fillbg);
    transition:width var(--tickdur) var(--tickease) var(--tickdelay)}
  /* THE FILL IS THE ONE PLACE THE SIGN BECOMES A REAL COLOUR. The text convention below (glow,
     never a fill) exists to keep NUMERALS legible over bright and dark map areas; a solid bar has
     no glyph to keep readable, so it takes the sign directly -- same upCol/dnCol as the numerals'
     glow, so bar and numbers agree. Zero delta -> neither class -> the neutral --fillbg. Two-class
     selectors so they out-specify .mp-fill, and `transition` is NOT restated (width only). */
  .mp-fill.mp-up{background:var(--upfill)}
  .mp-fill.mp-down{background:var(--dnfill)}
  .mp-tick{position:absolute;top:50%;width:var(--tickw);height:var(--tickh);transform:translate(-50%,-50%);z-index:2}
  .mp-end{background:var(--endcol)}
  .mp-left{left:0}
  .mp-right{left:100%}
  .mp-pre{background:var(--precol)}
  /* The CURRENT tick carries its own glow -- the same two-pass shape (wide + tight core) as the
     gold .mp-full ring and the text glow, so the visual language stays one family. NOTE the
     specificity: #moe-bar-root.mp-full .mp-tick is id+2 classes and BEATS this 2-class rule, so
     once the requirement is met the gold takes the whole bar over, this glow included. Deliberate
     -- no knob fights it. */
  .mp-proj{background:var(--projcol);box-shadow:var(--projsh);
    transition:left var(--tickdur) var(--tickease) var(--tickdelay)}
  /* ...AND IT TAKES THE SIGN, exactly like the numerals it carries (JS toggles .mp-up/.mp-down on
     this tick in the SAME forEach as the caption numerals and the fill). Same upCol/dnCol as the
     text glow at the same fixed DGA alpha, with the TICK's own two-pass radii -- so re-dialling
     upCol/dnCol moves text and tick together. NEUTRAL NEEDS NO RULE: --projsh above IS the
     neutral. `transition` is deliberately NOT restated -- a declaration-only override leaves the
     base `left` transition intact; restating it would re-arm it. */
  .mp-proj.mp-up{box-shadow:var(--projshup)}
  .mp-proj.mp-down{box-shadow:var(--projshdn)}

  /* ---- FOUR labelled ticks: each tick bar gets a CAPTION (icon LEFT, numerals right, ONE row).
     TWO of them stack vertically on the CENTRE ticks -- pre_avg ABOVE (.up), proj_avg BELOW
     (.dn) -- and that split is load-bearing: those two sit ~1.3% apart on the default axis, so
     one above / one below is the only thing keeping both legible. The two AXIS-END captions are
     .side instead: vertically centred on the track's midline, hanging OUTSIDE its left/right
     edge. Captions are absolutely positioned in the TRACK's coordinate space (not inside the
     tick), so their width never affects the tick geometry.
     WHAT translateX(-50%) CENTRES ON THE TICK IS THE NUMERAL, NOT THE ROW. A centre caption's
     row is icon + numeral (+ delta on .dn), so centring the whole box put the DIGITS left of
     their own tick by half the icon+gap -- and the .dn one drifted as the delta's text width
     changed. Both siblings are therefore taken OUT of the width the transform halves, by the
     mechanism each one's constraint allows (see .mp-capP/.mp-capC .mp-ico and .mp-cap .mp-d
     below): what is left in flow is the numeral alone, so -50% of the box IS -50% of the digits.
     Same end state as the sibling Damage Efficiency bar, reached differently -- there .mp-cap is
     not a flex row at all.
     GAMEFACE: plain `flex-direction: row` -- the earlier `column-reverse` variant was never
     verified in Coherent and is GONE, so there is no unverified flex mode left here. */
  .mp-cap{position:absolute;left:0;transform:translateX(-50%);display:flex;flex-direction:row;
    align-items:center;white-space:nowrap;z-index:3}
  /* GAP DIRECTION IS NOT SYMMETRIC IN GAMEFACE. `bottom:100%` + margin-bottom (and
     `right:100%` + margin-right below) are IGNORED by Coherent on an absolutely
     positioned box -- confirmed in-game, both gaps rendered 0, and 0/515 precedents in
     WG's own _dist corpus. padding-bottom / padding-right have several and DO apply, so
     those two directions use padding. The top:100%+margin-top / left:100%+margin-left
     twins work as written -- do not "unify" them onto padding. */
  .mp-cap.up{bottom:100%;padding-bottom:var(--gapreq);font-size:var(--reqfs);line-height:var(--reqlh)}
  .mp-cap.dn{top:100%;margin-top:var(--gapcur);font-size:var(--curfs);line-height:var(--curlh)}
  /* SIDE (axis-end) captions: the .mp-tick centring trick -- top:50% + translateY(-50%) -- so the
     row's box centres on the track midline. `left:auto` is REQUIRED on the left one because
     .mp-cap sets left:0 and right:100% alone would not release it. Two classes so the transform
     out-specifies .mp-cap's translateX(-50%): these are NOT centred on a tick, they are pushed
     off the end. Nothing shares a band with them any more, so there is no de-collision pass and
     JS measures nothing here. The translateY(-50%) is on the CAPTION box; the per-role .mp-ico
     nudge is on a CHILD, so the two transforms never clobber each other (and the ::before glow's
     z-index:-1 stays scoped by .mp-ico's own transform). Own font size (--endfs): these are no
     longer "the top captions", so they must not inherit .up's. */
  .mp-cap.side{top:50%;transform:translateY(-50%);font-size:var(--endfs);line-height:var(--endlh)}
  .mp-cap.side.mp-capL{left:auto;right:100%;padding-right:var(--gapendl)}
  .mp-cap.side.mp-capR{left:100%;margin-left:var(--gapendr)}
  /* The ONE gap, on every caption. The two CENTRE captions then cancel their icon's whole outer
     width with a negative margin-left -- see the .mp-capP / .mp-capC rules below. */
  .mp-cap .mp-ico{margin-right:var(--icogap)}
  .mp-cap .mp-v,.mp-cap .mp-d{color:#ffffff;font-weight:var(--wt);letter-spacing:var(--ls);text-shadow:var(--textsh)}
  /* SHIPPED CONVENTION (MoEBattle.css .mb-up/.mb-down): FOR TEXT the sign is a coloured GLOW,
     never a fill -- the numerals stay WHITE, because a coloured glyph loses legibility over a
     bright or dark map. Do NOT "fix" this into color:green/red later. (The .mp-fill rule above
     DOES take the sign as a real background colour on purpose -- that reasoning is about glyphs
     and a solid bar has none. Text glows, bar fills; both read the same upCol/dnCol.) The glow is
     a TRIPLE text-shadow: the dark legibility drop, then a wide pass, then a tight core pass.
     Zero delta gets neither class -> white + the dark drop only.
     WHO glows (exactly the shipped set, one row up): the bottom-centre caption's MAIN NUMBER
     (.mp-capC's .mp-v == the shipped .mb-value.mb-up) AND the delta's NUMBER child
     (.mp-d-num == .mb-delta-num) -- NOT the delta's parens, which are static text nodes on the
     .mp-d wrapper and keep the plain white treatment, and NOT the other three captions (the two
     requirement ends + pre_avg carry no sign, so JS never puts the class on them). */
  /* ~= the shipped .mb-delta 4.5rem @14rem. font-size + translateY are the EFFICIENCY bar's delta
     values (12rem / the 2.5rem half of its translate(4.2rem, 2.5rem)), carried over after a live
     pass; HARDCODED like the .35em gap beside them -- no knob, so a re-emit keeps them. Its X half
     needs no counterpart: 0.35em of the delta's own 12rem IS 4.2rem.
     OUT OF FLOW off the numeral's right edge, the other half of the numeral-centring in .mp-cap's
     note. A margin cannot cancel THIS sibling's width: the digits change, so any fixed negative
     would leave the centring drifting with the delta's text. `left:100%` + margin-left is the SAFE
     anchored pair (Coherent honours the left/top twins; it is `right:100%`+margin-right and
     `bottom:100%`+margin-bottom that render a 0 gap), and it keeps the .35em gap exactly as tuned.
     NO `top` HERE ON PURPOSE: an abspos child of a flex container takes its static position as if
     it were the sole flex item, so align-items:center keeps the vertical placement the in-flow box
     had and translateY below stays the whole Y story. `top:0` would be the sibling efficiency
     bar's form, but it anchors to the content-box TOP and would lift the delta by half the row's
     leftover height -- do not "unify" them.
     The delta FADES in at the numeral swap: opacity 0 ->
     1 with a transition, NOT visibility (which cannot interpolate). display:none would work for
     the centring now that the box is out of flow -- it did NOT before, and that is why opacity was
     chosen -- but opacity is what interpolates, so it stays. No `visibility` alongside it: this is
     a pointer-events:none overlay, so there is nothing to hit-test or focus behind a 0-alpha box.
     ONE transition declaration on .mp-d, naming ONLY opacity -- explicit ms + easing in the
     emitted CSS (Gameface drops a transition whose property starts from an unresolvable var()). */
  .mp-cap .mp-d{position:absolute;left:100%;margin-left:.35em;font-size:12rem;transform:translateY(2.5rem);line-height:15.5rem;opacity:0;transition:opacity var(--dfadms) var(--dfadease)}
  .mp-v.mp-up,.mp-d-num.mp-up{text-shadow:var(--textsh),0 0 var(--dgw) var(--upc),0 0 var(--dgt) var(--upc)}
  .mp-v.mp-down,.mp-d-num.mp-down{text-shadow:var(--textsh),0 0 var(--dgw) var(--dnc),0 0 var(--dgt) var(--dnc)}
  /* Only the bottom-centre caption animates (it rides proj_avg); pre_avg's stays put. */
  .mp-cap.mp-capC{transition:left var(--tickdur) var(--tickease) var(--tickdelay)}
  .mp-ico.none{display:none}

  /* ---- Icon glyphs. The .mb-ico split verbatim: GLYPH on ::after, GLOW on ::before with
     z-index:-1, because an element's own background always paints BELOW its pseudos. The
     transform keeps .mp-ico a stacking context so that -1 stays scoped here. The glow is TWO
     independent colours at the tuned defaults: the centre damage pair keeps the gold halo, the
     two axis-end requirement marks are a DARK DROP (see the override below the base rule).
     FRAMING: quest_type/128x128 glyphs are 128px canvases with a small centred glyph
     (measured: damage bbox 0.219, barrel_mark 0.328, top 0.273 of the canvas), so the shipped overlay's
     flat background-size:260% frames them at 57% vs 85% fill -- visibly different weights.
     Here the size is DERIVED: size% = 100 * (canvas/glyph) * targetFill, one slider for both.
     marksOnGun cuts are 24x24 and ALREADY warm cream (~#ede6d9) -> no brightness() (that is
     only for the flat grey #d1d1d1 quest_type line art). Constant canvas, glyph y 5..17 for all
     three, WIDTH grows with the count (mark_1 x 9..14, mark_2 x 6..17, mark_3 x 3..20), so
     background-size:contain on ONE fixed box makes mark_1 render ~1/3 the width of mark_3 --
     do not trim per count. They are only 24px: above ~24rem they visibly blur. */
  .mp-ico{position:relative;display:block;flex:none;width:var(--icobox);height:var(--icobox);
    transform:translate(0,0)}
  /* PER-ROLE VERTICAL NUDGE. The four glyph families sit differently on their baselines (the
     24px marksOnGun cuts vs the 128px quest_type line art), so each caption's icon gets its own
     signed Y. It stays on the SAME `transform` -- that transform is what makes .mp-ico a stacking
     context and scopes the ::before glow's z-index:-1, so it must never be dropped for a margin.
     ::before is centred INSIDE this transformed box (left/top 50% + its own translate(-50%,-50%),
     a separate transform), so the glow rides along and its centring is untouched at any Y.
     ...AND, ON THE TWO CENTRE CAPTIONS ONLY, THE ICON'S WIDTH CANCELLED -- the first half of the
     numeral-centring in .mp-cap's note. margin-left is -(this caption's own icon box + the gap),
     so the icon's OUTER width is exactly 0 (-box-gap + box + gap): the numeral starts at the
     caption's origin and the glyph still paints one --icogap to its left, unmoved. A MARGIN and
     not position:absolute precisely so the icon stays IN FLOW -- it keeps the transform above
     (both the Y and the stacking context), and out of flow it would need a top:50% that, on .up,
     resolves against a PADDING box carrying --gapreq. PER CAPTION because the box is per caption
     (dmgP / dmgC are independent sliders). NOT on the two .side captions: they are not centred on
     anything, they are pushed off the axis ends by their own gap, so cancelling their icon would
     just slide the label inwards over the track. */
  .mp-capL .mp-ico{transform:translate(0,var(--icoyl))}
  .mp-capP .mp-ico{transform:translate(0,var(--icoyp));margin-left:var(--dmgpml)}
  .mp-capC .mp-ico{transform:translate(0,var(--icoyc));margin-left:var(--dmgcml)}
  .mp-capR .mp-ico{transform:translate(0,var(--icoyr))}
  /* SIDE-CAPTION NUMERAL NUDGE -- font metrics, NOT a box-height problem. MoEBattle.ttf is
     asc 2088 / desc 486 @ upem 2048 = a 1.2568em line box (17.60rem at the 14rem side size),
     while the digit ink spans only -0.0132..0.7192em -> its centre sits 0.0381em = 0.53rem BELOW
     the line box centre, which is what translateY(-50%) actually centres on the track midline.
     So the numerals render ~0.53rem low and this pulls them back. min-height would be a NO-OP
     (the box is already 17.60rem; markBox's 17 < 17.60). .side only -- .up/.dn are not centred
     on the midline, so they must NOT inherit it. .mp-v is a flex item, so transform applies. */
  .mp-cap.side .mp-v{transform:translateY(var(--numy))}
  /* 106% == the overlay's 18rem glow behind a 17rem icon, expressed as a ratio so it follows
     whichever box (icon or mark) the element uses. Alpha 0 turns the glow off. */
  .mp-ico::before{content:"";position:absolute;left:50%;top:50%;z-index:-1;
    width:106%;height:106%;transform:translate(-50%,-50%);
    background:radial-gradient(circle at 50% 50%,var(--icoglow) 0%,transparent 73%)}
  /* The two axis-end (.side) MoE REQUIREMENT icons take their own glow colour+alpha -- independent
     of the two centre damage icons above. BACKGROUND ONLY: the base rule keeps supplying z-index:-1,
     the 106% box and its own translate(-50%,-50%), and this targets ::before (never .mp-ico), so
     .mp-ico's transform -- which both carries the per-role Y (icoYL/icoYR) AND is what scopes that
     z-index:-1 to the icon -- is untouched. Includes the general-MoE glyph at 3 marks (it is still
     .mp-capR .mp-ico). Specificity (0,2,1) > the base (0,1,1), so only the gradient is overridden. */
  .mp-capL .mp-ico::before,.mp-capR .mp-ico::before{background:radial-gradient(circle at 50% 50%,var(--reqglow) 0%,transparent 73%)}
  .mp-ico::after{content:"";position:absolute;left:0;top:0;width:100%;height:100%;
    background-repeat:no-repeat;background-position:center}
  /* TWO independent damage glyphs: dmgp = top-centre (pre_avg), dmgc = bottom-centre (proj_avg).
     Separate box AND separate glyph choice, each with its own derived background-size. */
  .mp-ico.dmgp{width:var(--dmgpbox);height:var(--dmgpbox)}
  .mp-ico.dmgc{width:var(--dmgcbox);height:var(--dmgcbox)}
  .mp-ico.dmgp::after{background-image:var(--dmgpimg);background-size:var(--dmgpsz);filter:brightness(3)}
  .mp-ico.dmgc::after{background-image:var(--dmgcimg);background-size:var(--dmgcsz);filter:brightness(3)}
  /* Box PARITY WITH .mk off the SAME markBox knob, not a second slider: .moe replaces the right
     caption's mark glyph at 3 marks, so the two are never on screen together and dragging them
     apart could only make that one moment inconsistent. Without it .moe fell back to .mp-ico's
     icoBox and the icon silently shrank 17 -> 13rem. (markBox's "blurs above ~24rem" ceiling is
     the 24px marksOnGun art's, not this 128px glyph's -- split the knob only if a future tuning
     actually wants them apart.) */
  .mp-ico.moe{width:var(--markbox);height:var(--markbox)}
  .mp-ico.moe::after{background-image:var(--moeimg);background-size:var(--moesz);filter:brightness(3)}
  .mp-ico.mk{width:var(--markbox);height:var(--markbox)}
  .mp-ico.mk::after{background-size:contain}
  .mp-ico.mk1::after{background-image:url(data:image/png;base64,__ICO_MK1__)}
  .mp-ico.mk2::after{background-image:url(data:image/png;base64,__ICO_MK2__)}
  .mp-ico.mk3::after{background-image:url(data:image/png;base64,__ICO_MK3__)}

  /* Requirement met -> the WHOLE bar takes the gold glow. */
  #moe-bar-root.mp-full .mp-track,#moe-bar-root.mp-full .mp-fill,#moe-bar-root.mp-full .mp-tick{box-shadow:0 0 var(--glowb) var(--glowc)}
  /* ...and the FILL also turns the same gold. Its OWN rule: the grouped selector above is the
     box-shadow for all three elements, and the background must land on .mp-fill ONLY. (1,2,0)
     beats .mp-fill.mp-up/.mp-down at (0,2,0), so gold wins over the sign colour. No `transition`
     restated here -- width stays the only animated property; the background flips. */
  #moe-bar-root.mp-full .mp-fill{background:var(--fullfill)}
  #moe-bar-root.mp-full .mp-v{text-shadow:var(--textsh),0 0 var(--glowb) var(--glowc),0 0 var(--glowb2) var(--glowc)}

  /* ================= panel ================= */
  .panel{width:380px;flex:none;background:var(--panel);border-left:1px solid var(--line);padding:18px 18px 60px;overflow:auto;height:100vh;position:sticky;top:0}
  .panel h1{font-size:16px;margin:0 0 4px;font-weight:800}
  .seg{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
  .seg button{flex:1;background:#14151a;border:1px solid var(--line);color:var(--ink);padding:6px 4px;border-radius:6px;font-size:11.5px;cursor:pointer}
  .seg button.on{border-color:var(--gold);color:var(--gold);font-weight:700}
  details{border:1px solid var(--line);border-radius:8px;margin-bottom:8px;background:#191b21}
  summary{padding:9px 12px;font-size:12.5px;font-weight:700;cursor:pointer;color:var(--gold);letter-spacing:.03em;text-transform:uppercase}
  .grp{padding:4px 12px 12px}
  .ctl{margin:8px 0}
  .ctl .lab{display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px}
  .ctl .inp{display:flex;gap:8px;align-items:center}
  .ctl input[type=range]{flex:1;accent-color:var(--gold)}
  .ctl input[type=number]{width:66px;background:#0f1013;border:1px solid var(--line);color:var(--ink);border-radius:5px;padding:4px 6px;font-size:12px;font-variant-numeric:tabular-nums}
  .ctl input[type=color]{width:38px;height:26px;background:none;border:1px solid var(--line);border-radius:5px;padding:0;cursor:pointer}
  .ctl select{flex:1;background:#0f1013;border:1px solid var(--line);color:var(--ink);border-radius:5px;padding:4px 6px;font-size:12px}
  .row2{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:4px 0 12px;font-size:12.5px}
  .row2 label{display:flex;gap:6px;align-items:center;cursor:pointer}
  .out{background:#0f1013;border:1px solid var(--line);border-radius:8px;padding:11px;font-family:"Cascadia Code",Consolas,monospace;font-size:10.5px;color:#b9c2cf;white-space:pre;overflow-x:auto;line-height:1.5}
  .copy{margin-top:9px;width:100%;background:var(--gold);color:#1a160c;border:0;border-radius:8px;padding:10px;font-weight:800;font-size:13px;cursor:pointer}
  .axisout{background:#0f1013;border:1px solid var(--gold);border-radius:8px;padding:9px 11px;margin-bottom:9px;
    font-family:"Cascadia Code",Consolas,monospace;font-size:11px;color:var(--gold);font-weight:700;
    font-variant-numeric:tabular-nums;line-height:1.5;white-space:pre}
  .note{font-size:10.5px;color:var(--muted);margin-top:12px;line-height:1.5}
  #shot{width:100%;font-size:11px;color:var(--muted);margin-bottom:10px}

  /* mock fly-up ribbon stack (WG's feed is Scaleform -- no CSS to copy, this is a stand-in so
     the "below these events" vertical gap can be judged against a DEEP feed; the backdrop
     already shows one real ribbon, so this is OFF by default). System font: it has LETTERS.
     translateY(-100%) makes ribY the feed's BASELINE (newest ribbon, older ones above) --
     the same edge offY has to clear, so the two numbers compare directly. */
  #ribbons{position:absolute;z-index:20;display:none;transform:translateY(-100%);
    font-family:"Segoe UI",system-ui,sans-serif;pointer-events:none}
  #ribbons.on{display:block}
  #ribbons .rb{font-size:15px;font-weight:700;letter-spacing:.04em;color:#f2ede2;text-shadow:0 0 4px #000,0 1px 2px #000;
    margin-bottom:7px;white-space:nowrap;opacity:0}
  /* LOOPS while the checkbox is on -- a one-shot stack would vanish and leave nothing to judge
     the "below these events" gap against. */
  #ribbons.on .rb{animation:rb-up 2.4s ease-out infinite}
  #ribbons.on .rb:nth-child(2){animation-delay:.35s}
  #ribbons.on .rb:nth-child(3){animation-delay:.7s}
  @keyframes rb-up{0%{opacity:0;transform:translateY(14px)}14%{opacity:1;transform:translateY(0)}
    70%{opacity:1;transform:translateY(-6px)}100%{opacity:0;transform:translateY(-22px)}}

  /* dither magnifier -- the sub-pixel trap this whole tuner family exists to catch */
  #loupe{position:absolute;top:12px;right:12px;width:230px;background:rgba(10,11,14,.94);
    border:1px solid var(--line);border-radius:8px;padding:9px;font-family:"Segoe UI",system-ui,sans-serif;z-index:50}
  #loupe .loupelab{font-size:10px;letter-spacing:.08em;color:var(--gold);font-weight:700;margin-bottom:6px}
  #loupeSwatch{position:relative;height:110px;border-radius:5px;overflow:hidden;background-image:linear-gradient(180deg,#2a2f38,#14161b)}
  #loupeDither{position:absolute;left:0;top:0;right:0;bottom:0;image-rendering:pixelated;background-repeat:repeat}
  #loupeCap{font-size:10px;color:var(--muted);margin-top:6px;line-height:1.4}
</style>

<div class="stagewrap"><div class="stage" id="stage">
  <div class="mp-anchor" id="mp-anchor"><div id="moe-bar-root" class="mp-hold">
    <div class="mp-backdrop"></div>
    <div class="mp-track">
      <div class="mp-fill"></div>
      <div class="mp-tick mp-end mp-left"></div>
      <div class="mp-tick mp-pre"></div>
      <div class="mp-tick mp-proj"></div>
      <div class="mp-tick mp-end mp-right"></div>
      <!-- 2 captions on the CENTRE ticks (pre_avg above, proj_avg below - the animated one) and
           2 BESIDE the axis ends (.side, vertically centred on the track, hanging off each edge).
           Icon stays LEFT in all four (DOM: icon, value, delta) -- on the left-hand .side label
           that puts the NUMBER nearest the axis it labels, which is the right way round. -->
      <div class="mp-cap side mp-capL"><i class="mp-ico mk mk1"></i><span class="mp-v">2,450</span></div>
      <div class="mp-cap up mp-capP"><i class="mp-ico dmgp"></i><span class="mp-v">2,905</span></div>
      <!-- Shipped .mb-delta > .mb-delta-num split verbatim: the PARENS are static text nodes on
           the .mp-d wrapper (plain white, dark drop only) and only the signed NUMBER child
           .mp-d-num takes the sign glow. The main .mp-v glows too (bottom caption only). -->
      <div class="mp-cap dn mp-capC"><i class="mp-ico dmgc"></i><span class="mp-v">2,913</span><span class="mp-d">(<span class="mp-d-num">+8</span>)</span></div>
      <div class="mp-cap side mp-capR"><i class="mp-ico mk mk2"></i><span class="mp-v">3,050</span></div>
    </div>
  </div></div>
  <div id="ribbons"><div class="rb">DAMAGE 452</div><div class="rb">ASSIST 189</div><div class="rb">DESTROYED</div></div>
  <div id="loupe"><div class="loupelab">DITHER MAGNIFIER</div><div id="loupeSwatch"><div id="loupeDither"></div></div><div id="loupeCap"></div></div>
</div></div>

<div class="panel">
  <h1>In-battle MoE progress bar &mdash; tuner</h1>
  <input type="file" id="shot" accept="image/*">
  <div class="seg" id="axisSeg">
    <button data-a="mark" class="on">prev&rarr;next mark</button><button data-a="zero">0&rarr;next</button><button data-a="win">windowed</button>
  </div>
  <div class="row2">
    <label><input type="checkbox" id="cHold" checked> hold visible</label>
    <label><input type="checkbox" id="cBounds"> bounds</label>
    <label><input type="checkbox" id="cRib"> mock ribbons</label>
    <label><input type="checkbox" id="cBd" checked> backdrop</label>
    <label><input type="checkbox" id="cPulse"> glow pulse</label>
    <!-- These two DO reach the emitted CSS (unlike `backdrop`, which is a stage-preview toggle):
         off emits `none` for the dash background / the ring shadow. -->
    <label><input type="checkbox" id="cDash" checked> track dashes</label>
    <label><input type="checkbox" id="cBdr" checked> track border</label>
  </div>
  <div class="seg"><button id="bReplay">Replay</button><button id="bTick">Damage tick</button><button id="bFull">Fulfil</button></div>
  <div class="ctl"><div class="lab"><span>Timing preset &mdash; real WG values only</span></div>
    <div class="inp"><select id="preset"></select></div></div>
  <div class="axisout" id="axisOut"></div>
  <div id="controls"></div>
  <div class="out" id="out"></div>
  <button class="copy" id="copyBtn">Copy CSS</button>
  <p class="note">Emitted CSS ends with a JSON block of the animation timings (now including the <b>slide distance + both easings</b>) &mdash; phase 2's JS needs the numbers, not just the CSS. Icons here are <b>base64-inlined</b> (a browser cannot resolve <code>img://</code>); the emitted CSS carries the real <code>img://</code> urls. Re-extract them from the client with <code>-ExtractIcons</code>. <b>checker.png is inlined as shipped</b> (4px tile = 2x2 cells @2px); change the cell size with <code>tools/dev/gen_checker.py --cell N</code>, not here.</p>
</div>

<script>
  // Stage = a real 1600x900 frame of the 3840-wide client, so 1 stage px == 1/SCALE game px.
  // 1rem == 1 logical px; PXREM (px per rem on THIS stage) is calibrated exactly as in
  // gen_overlay_tuner.ps1: 2.0 px/rem @3840 * (1600/3840). Exposed as a slider.
  var SCALE=1600/3840, PXVW=16, PXVH=9;
  var CKURI="data:image/png;base64,__CK__", CKTILE=4;   // shipped checker.png: 4px tile @3840
  var THR={0:0,1:2450,2:3050,3:3620,100:4400};          // snapshot.thresholds shape (D65/D85/D95/D100)
  var DGA=0.9;   // delta sign-glow alpha -- the shipped .mb-up/.mb-down 0.9, not a knob
  // Centre-caption glyph choice -- picked INDEPENDENTLY for the top (pre_avg) and bottom
  // (proj_avg) captions, so the two centre damage icons can differ. The shipped .mb-ico.dmg
  // actually paints barrel_mark, so "match the in-battle widget" and "use a distinct damage
  // glyph" CONFLICT -- the maintainer picks, per icon.
  // Values are the measured glyph bbox fraction of the 128px canvas (see the CSS note).
  var DMG={damage:{u:"data:image/png;base64,__ICO_DMG__",bb:0.219},
           barrel_mark:{u:"data:image/png;base64,__ICO_BM__",bb:0.328}};
  // The general-MoE glyph that REPLACES the right caption's mark at 3 marks. It is
  // icon_battle_condition_TOP, not barrel_mark -- barrel_mark is the top-centre damage glyph now,
  // and one glyph cannot say both "your average" and "the top requirement". Same 128px quest_type
  // canvas and the same flat grey line art, so it takes brightness(3) like its neighbours; bb is
  // its measured ink (35x24 of 128 -> 0.273 on the max dimension, the same alpha>32 convention
  // that gives damage 0.219 and barrel_mark 0.328).
  var MOEURI="data:image/png;base64,__ICO_TOP__", MOEBB=0.273;
  // In-game equivalents of the inlined URIs above (emitted CSS only -- img:// is dead in a browser).
  var IMGDIR="img://gui/maps/icons/", QT="personal_missions_30/quest_type/128x128/";
  var IMG={damage:IMGDIR+QT+"icon_battle_condition_damage.png",
           barrel_mark:IMGDIR+QT+"icon_battle_condition_barrel_mark.png",
           top:IMGDIR+QT+"icon_battle_condition_top.png",
           mk:[IMGDIR+"library/marksOnGun/mark_1.png",IMGDIR+"library/marksOnGun/mark_2.png",IMGDIR+"library/marksOnGun/mark_3.png"]};
  function rem(v){return (v*st.pxrem).toFixed(2)+"px";}
  // THE PINNED LINE BOX -- used by BOTH halves (the live preview's custom properties and the
  // -EmitCss builder), because a caption's box height must not depend on the rem->px factor.
  // `line-height: normal` makes the line box the font's ascent+descent+gap SNAPPED UP TO WHOLE
  // DEVICE PIXELS, so measured in rem it SHRINKS as that factor grows: a 16rem caption is 21.000rem
  // at factor 1, 20.500 at 2, 20.125 at 24 (all three measured live). The captions place their
  // glyph off that box -- .mp-ico is a flex item under align-items:center here, and top:50% of the
  // same box on the sibling efficiency bar -- so HALF that variation lands straight in the icon's Y
  // and the numerals drift apart at low interface scales (reported at 3440x1440, factor 1).
  // R == 1.2565 is MoEBattle.ttf's fitted line ratio: ceil(font_px*R) reproduces all six measured
  // boxes (16/32/384px -> 21/41/483, 12/24/288px -> 16/31/362), and the fit corridor is
  // (1.25521, 1.25694]. PINNED AT THE FACTOR-2 VALUE, not at the font's true unsnapped ratio: the
  // maintainer's own render IS factor 2 and must not move by even one device pixel, whereas a
  // `1.2565em` line-height would compute to 40.2px there and shift everything 0.75px.
  // Halves are exact in rem (x.0 / x.5), so the emitted length stays a plain decimal.
  // NO LARGE-MODE TWIN: line-height is a uniform (vertical) length, so the root font alone scales
  // it (SIZE_F) -- a size-mode twin would DOUBLE-apply it, and
  // tests/test_progress_surface_mirror.py's large-mode walk refuses one.
  function lh(fs){return Math.ceil(fs*2*1.2565)/2;}
  function fmt(n){return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g,",");}
  function hexA(hex,a){var n=parseInt(hex.slice(1),16);return "rgba("+((n>>16)&255)+","+((n>>8)&255)+","+(n&255)+","+a+")";}

  // schema: [section,[ {id,label,min,max,step,val} | {id,label,color:true,val} | {id,label,opts:[],val} ]]
  var EASE=["ease-in","ease-out","ease-in-out","ease","linear","cubic-bezier(.2,.8,.2,1)"];
  // The exact ribbon-feed timing is NOT statically recoverable: WG's in-battle event feed is
  // Scaleform Flash and its fade lives in ABC bytecode. So nothing here is invented -- every
  // preset is a real, documented WG value, sourced in its comment. Selecting one SETS the
  // sliders; they stay independently editable afterwards.
  var PRESETS=[
    // gui/gameface/.../battle_notifier/BattleNotifierView.css -- the transient: 4s ease-in with
    // opacity stops at 0/20/80/100 => 800 in / 2400 hold / 800 out. NO LONGER the schema default:
    // the maintainer tuned to 600/5000/600 (total 6200, stops 9.68/90.32) in the browser.
    {n:"BattleNotifier transient - 4s ease-in, 20/80 stops",
     v:{fadeIn:800,hold:2400,fadeOut:800,fadeEase:"ease-in",outEase:"ease-in"}},
    // same file -- its show transition: `opacity .3s ease-in, transform .3s ease-in`. The closest
    // real WG value for a SHORT slide; hold is not part of it, so the transient's 2400 is kept.
    {n:"BattleNotifier show transition - .3s ease-in",
     v:{fadeIn:300,hold:2400,fadeOut:300,fadeEase:"ease-in",outEase:"ease-in"}},
    // vehicle_messages_panel.xml (BigWorld packed xml), direction=up -- literally a Y-axis slide:
    // lifeTime=2000, alphaSpeed=1000. Mapped as fade=alphaSpeed, hold=lifeTime; BigWorld ramps
    // alpha at a constant rate, hence linear.
    {n:"vehicle_messages_panel (up) - life 2000 / alpha 1000",
     v:{fadeIn:1000,hold:2000,fadeOut:1000,fadeEase:"linear",outEase:"linear"}},
    // player_messages_panel.xml, direction=up: lifeTime=12000, alphaSpeed=3000. Same mapping.
    {n:"player_messages_panel (up) - life 12000 / alpha 3000",
     v:{fadeIn:3000,hold:12000,fadeOut:3000,fadeEase:"linear",outEase:"linear"}}
  ];
  var SCHEMA=[
    ["Layout",[
      // 200 is the SETTLED track width (was 300). It is the ONE knob behind
      // `#moe-bar-root { width: Nrem }` in the emit, and three other emitted numbers FOLLOW it:
      // .mp-backdrop's left/width (barW + 2*bdBleedX = 360rem), the axis readout's rem/px
      // conversion, and -- outside this file -- MoEProgress.js's BOX_W_REM, which mirrors that
      // backdrop width (so 200 => BOX_W_REM 360, VIEW_W_REM 380, the hand-appended
      // `#moe-bar-box { width: 380rem }`). SHIFT_X_REM is PAD_REM - BOX_LEFT_REM and does NOT
      // move with barW. 200 = 3*66 + 2, so the 3rem dash period still ends on a WHOLE 2rem mark
      // flush with the right edge -- no truncated dash or gap (see dashW/dashGap below).
      {id:"barW",label:"Bar width (rem)",min:80,max:800,step:5,val:200},
      {id:"trackH",label:"Track thickness (rem)",min:1,max:30,step:0.5,val:3},
      {id:"tickW",label:"Tick width (rem)",min:1,max:20,step:0.5,val:2},
      {id:"tickH",label:"Tick height (rem)",min:2,max:60,step:0.5,val:9},
      {id:"gapReq",label:"Top caption (pre_avg) -> track gap (rem)",min:0,max:40,step:0.5,val:6},
      {id:"gapCur",label:"Track -> bottom caption gap (rem)",min:0,max:40,step:0.5,val:6},
      // The two axis-end captions hang OUTSIDE the track ends (right:100% / left:100%), so these
      // are their horizontal clearance from the end. TWO sliders, deliberately independent: the two
      // side rows are not the same width (the left one carries the held mark glyph, the right the
      // chased one) and the maintainer tuned them apart, so a single symmetric knob cannot express
      // the settled look. They also emit DIFFERENT properties -- padding-right on the left, because
      // Gameface renders margin on the `right:100%` anchored side as 0 (see the CSS note above), and
      // margin-left on the right, where that direction works. (They replace the old capGap clamp
      // margin, which existed only because the end captions used to share the upper band with
      // pre_avg's -- they no longer do, so there is nothing to de-collide.)
      {id:"gapEndL",label:"Track LEFT end -> left side caption gap (rem, padding)",min:0,max:60,step:0.5,val:8},
      {id:"gapEndR",label:"Track RIGHT end -> right side caption gap (rem, margin)",min:0,max:60,step:0.5,val:3},
      {id:"offX",label:"Centre X offset (rem)",min:-300,max:300,step:1,val:0},
      // Measured off tuner-backdrop-ribbon.jpg: the REAL "400 x Damage Caused x Taschenratte"
      // fly-up occupies x 725..935, y 658..676 -> left 45.3vw, baseline 75.1vh, centre 51.9vw.
      // offY is the TRACK's y; the backdrop is centred on it (--bdtop negative), so the feed
      // clearance to check is offY*9px - |bdTop|*pxrem against the 75.1vh ribbon baseline.
      {id:"offY",label:"Y offset - below the ribbon feed (vh)",min:0,max:100,step:0.1,val:86.5},
      {id:"ribX",label:"Mock ribbon stack X (vw)",min:0,max:100,step:0.1,val:45.3},
      {id:"ribY",label:"Mock ribbon feed BASELINE Y (vh) - stack grows upward",min:0,max:100,step:0.1,val:75.1}]],
    ["Type",[
      // WG's battle ladder: 8/10/11/12/14/16/18/20/30/35 rem (body font-size:14rem).
      {id:"reqFS",label:"Top caption (pre_avg) size (rem)",min:8,max:35,step:1,val:14},
      {id:"curFS",label:"Bottom caption (proj_avg) size (rem)",min:8,max:35,step:1,val:16},
      // The two axis-end captions used to be .up and so inherited reqFS. They are .side now, and
      // .up no longer describes them -- own knob, defaulted to the 14 they were already showing.
      {id:"endFS",label:"Side (axis-end) caption size (rem)",min:8,max:35,step:1,val:14},
      {id:"wt",label:"Weight",min:300,max:700,step:100,val:600},
      {id:"ls",label:"Letter-spacing (em)",min:-0.1,max:0.2,step:0.005,val:0},
      {id:"shBlur",label:"Text-shadow blur (rem)",min:0,max:30,step:0.5,val:1},
      {id:"shAlpha",label:"Text-shadow alpha",min:0,max:1,step:0.01,val:0.5},
      {id:"shColor",label:"Text-shadow colour",color:true,val:"#000000"}]],
    ["Colour",[
      // Defaults from the shipped palette: white numerals, the dim .mb-sep cream for the static
      // tick, black-0.3 backdrop family for the track, and the icon gold for the glow.
      {id:"trackCol",label:"Track colour",color:true,val:"#000000"},
      {id:"trackA",label:"Track alpha",min:0,max:1,step:0.01,val:0.45},
      // THE GARAGE BAR'S OWN NUMBERS (MoECalculator.css:277-296), transferred 1:1 -- the hangar
      // track paints WG's bg_pattern_small.png, a 99x2 strip at background-size:99rem 2rem, i.e.
      // 1 art px == 1rem: 2rem dash + 1rem gap = a 3rem period, cream rgb(236,230,218) at alpha
      // 41/255 = 0.16. The scale transfers as-is (the garage's period is 3rem on a 2rem-tall
      // track; here the same 3rem period runs across a 3rem-tall one, the same density), so
      // nothing was rescaled. At the settled barW 200 that is 66 whole 3rem periods (198rem)
      // plus a final FULL 2rem mark ending flush at the right edge -- the remainder is exactly
      // one dash and no gap, so do NOT "compensate" these two: they are separately tuned to
      // WG's art. (The only barW values that truncate mid-mark are the ones where barW mod 3
      // is 1; step 5 hits those at 205, 220, 235, ...) Dash colour is
      // #ece6da == rgb(236,230,218).
      {id:"dashW",label:"Dash MARK width (rem) - garage art = 2",min:0.5,max:20,step:0.5,val:2},
      {id:"dashGap",label:"Dash GAP width (rem) - garage art = 1",min:0.5,max:20,step:0.5,val:1},
      {id:"dashCol",label:"Dash MARK colour (garage cream)",color:true,val:"#ece6da"},
      {id:"dashA",label:"Dash MARK alpha - garage art = 41/255",min:0,max:1,step:0.01,val:0.16},
      // THE GAP IS A COLOUR NOW, not `transparent` -- the fix for "the fill reads as sitting on top
      // of the dark grid". The garage's .moe-fill (MoECalculator.css:304-326) has NO
      // background-color: it is filled_pattern_small.png ONLY, so its transparent gaps show the
      // dark track backing and the fill lives exclusively inside the dash marks -- the garage grid
      // is a MASK. Our fill is a solid colour, so an OPAQUE gap stripe (gapA 1) reproduces that
      // exactly; the maintainer's tuned default is 0.5, i.e. the mask dialled back halfway -- the
      // dashes still read as a grid over the fill but the fill stays continuous underneath.
      // Colour = the garage's own dark (#0d0e10, the hue of the track backing rgba(13,14,16,0.45)
      // and the ring rgba(13,14,16,0.5)). gapA 0 -> the old fully transparent gap.
      {id:"gapCol",label:"Dash GAP colour (garage dark) - paints OVER the fill",color:true,val:"#0d0e10"},
      {id:"gapA",label:"Dash GAP alpha - 1 = fill masked to the marks (garage look), 0 = old",min:0,max:1,step:0.01,val:0.5},
      // The garage's "border" is an OUTSET ring shadow, not a border: 0 0 0 1rem rgba(13,14,16,.5)
      // (#0d0e10 @ 0.5). Kept as a shadow here for the same reason -- zero box-model impact.
      {id:"bdrW",label:"Border width (rem) - garage = 1",min:0,max:8,step:0.5,val:1},
      {id:"bdrCol",label:"Border colour (garage near-black)",color:true,val:"#0d0e10"},
      {id:"bdrA",label:"Border alpha - garage = 0.5",min:0,max:1,step:0.01,val:0.5},
      // Fill: the NEUTRAL colour is the cream #ede6d9 at 0.8. It used to be the .mb-up green --
      // identical to upCol -- which made every cold damage event flash GREEN for the entry
      // animation before the delta's sign class landed, even on the way down. Neutral must not be
      // any sign's colour. fillA drives ALL THREE fill backgrounds (neutral + up + down all read
      // hexA(...,st.fillA)), so re-dial the COLOUR here, never the alpha.
      // The MET-state gold fill has its OWN alpha (fullFillA below), not this one.
      // Expect to re-dial by eye: a cream fill makes the cream dash marks (dashCol @ dashA 0.16)
      // near-invisible over the reached half, leaving the opaque gapCol stripe to carry the grid.
      {id:"fillCol",label:"Fill colour (NEUTRAL - keep it off upCol/dnCol)",color:true,val:"#ede6d9"},
      {id:"fillA",label:"Fill alpha",min:0,max:1,step:0.01,val:0.8},
      {id:"endCol",label:"End tick colour (axis stops)",color:true,val:"#ede6d9"},
      {id:"endA",label:"End tick alpha",min:0,max:1,step:0.01,val:0.8},
      {id:"preCol",label:"Pre tick colour",color:true,val:"#ede6d9"},
      {id:"preA",label:"Pre tick alpha",min:0,max:1,step:0.01,val:0.75},
      {id:"projCol",label:"Proj tick colour",color:true,val:"#ffffff"},
      // Fully opaque by design: the CURRENT tick is the one the eye must find first, so it reads
      // solid white while the pre/end stops sit behind it at 0.75 / 0.8.
      {id:"projA",label:"Proj tick alpha",min:0,max:1,step:0.01,val:1},
      // The CURRENT tick's own glow -- same two-pass (wide + tight core) shape as the gold
      // .mp-full ring and the text glow. Restrained by default: white, half alpha, 6/2rem.
      // .mp-full's id+2-class rule OUT-SPECIFIES it, so met-requirement gold wins (by design).
      // This pair is the NEUTRAL glow only: a signed delta swaps the colour to upCol/dnCol (at DGA)
      // while keeping the B/B2 radii below -- so the radii knobs govern all three states at once.
      {id:"projGlowCol",label:"CURRENT tick glow colour (NEUTRAL; sign uses upCol/dnCol)",color:true,val:"#ffffff"},
      {id:"projGlowA",label:"CURRENT tick glow alpha",min:0,max:1,step:0.01,val:0.5},
      {id:"projGlowB",label:"CURRENT tick glow radius (rem)",min:0,max:40,step:0.5,val:6},
      {id:"projGlowB2",label:"CURRENT tick glow tight core (rem)",min:0,max:20,step:0.5,val:2},
      {id:"glowCol",label:"Glow colour (icon gold)",color:true,val:"#ffcd5a"},
      {id:"glowA",label:"Glow alpha",min:0,max:1,step:0.01,val:0.5},
      {id:"glowB",label:"Glow radius (rem)",min:0,max:60,step:0.5,val:8},
      {id:"glowB2",label:"Glow tight core (rem)",min:0,max:30,step:0.5,val:2},
      // MET-STATE FILL COLOUR: once proj_avg >= thresholds[m+1] the fill stops being green/red and
      // becomes the SAME gold as the glow -- glowCol, deliberately NOT a second gold picker (one
      // gold, one place to change it). Only the ALPHA is its own: the glow's 0.5 is far too faint
      // for a solid bar, so this defaults to 0.8 == fillA, i.e. the bar's DENSITY does not change
      // when it turns gold, only its hue. Its rule `#moe-bar-root.mp-full .mp-fill` is id+2-class
      // (1,2,0) and so out-specifies .mp-fill.mp-up/.mp-down at (0,2,0) -- the gold wins over the
      // sign colour with no !important and no JS. `transition` is NOT restated there: the
      // background FLIPS, only width interpolates.
      {id:"fullFillA",label:"MET-state gold FILL alpha (uses the glow colour)",min:0,max:1,step:0.01,val:0.8},
      // Delta sign colours -- the SHIPPED .mb-up/.mb-down values verbatim, applied as a GLOW
      // (never a fill; the numerals stay white). Alpha is fixed at the shipped 0.9 (DGA).
      {id:"upCol",label:"Delta + glow (shipped .mb-up green)",color:true,val:"#7bec37"},
      {id:"dnCol",label:"Delta - glow (shipped .mb-down red)",color:true,val:"#d3443f"},
      {id:"dGlowW",label:"Delta glow WIDE pass (rem)",min:0,max:30,step:0.5,val:6},
      {id:"dGlowT",label:"Delta glow TIGHT core (rem)",min:0,max:30,step:0.5,val:1}]],
    ["Icons (framed by MEASURED glyph bbox, not a flat zoom)",[
      // targetFill is the ONE knob that matches the two quest_type glyphs visually: the emitted
      // background-size is 100*(canvas/glyph)*targetFill per family. The maintainer's tuned 0.75
      // lands damage at 342.5% and barrel_mark at 228.7% (verified: 100/0.219*0.75 and
      // 100/0.328*0.75). The earlier 0.6 gave 274% / 182.9%; the shipped flat 260% gave 57% vs
      // 85% fill -- mismatched, which is why the size is derived at all.
      // TOP and BOTTOM centre damage icons are fully independent (glyph + box). This knob is the
      // BASE .mp-ico box, which every caption now overrides (dmgp/dmgc take their own, .mk and
      // .moe both take markBox), so it governs nothing on screen -- it only sets the emitted
      // .mp-ico fallback width. Nothing to tune here unless a new caption is added.
      {id:"icoBox",label:"Base .mp-ico box (rem) - every caption overrides it",min:6,max:40,step:1,val:13},
      {id:"dmgPBox",label:"TOP damage icon box (rem)",min:6,max:40,step:1,val:14},
      {id:"dmgCBox",label:"BOTTOM damage icon box (rem)",min:6,max:40,step:1,val:16},
      {id:"icoFill",label:"Icon target fill (glyph / box)",min:0.2,max:1,step:0.01,val:0.75},
      // marksOnGun cuts are 24x24: past ~24rem they blur. background-size:contain, one box.
      // Left/right SHARE this one (both are marksOnGun cuts of the same 24px canvas).
      {id:"markBox",label:"Mark icon box (rem) - 24px art, blurs above ~24",min:6,max:40,step:1,val:17},
      // ONE gap knob now: the icon sits LEFT of the numerals on one row -> margin-right.
      {id:"icoGap",label:"Icon -> numerals gap (rem, icon is LEFT)",min:0,max:20,step:0.5,val:1},
      // TWO INDEPENDENT ICON GLOWS. This pair governs the two CENTRE DAMAGE icons only (top
      // pre_avg + bottom proj_avg) -- it used to borrow glowCol, so it has its own colour now.
      {id:"icoGlowCol",label:"CENTRE damage icon glow colour",color:true,val:"#ffcd5a"},
      {id:"icoGlowA",label:"CENTRE damage icon glow alpha (0 = off)",min:0,max:1,step:0.01,val:0.5},
      // ...and this pair the MoE REQUIREMENT icons: the mark glyphs on the two axis-end .side
      // captions, INCLUDING the general-MoE glyph that replaces the right one at 3 marks. Scoped as
      // `.mp-capL .mp-ico::before, .mp-capR .mp-ico::before` -- BACKGROUND ONLY, so the base
      // .mp-ico::before rule keeps supplying z-index:-1 + the 106% box + its own translate, and
      // .mp-ico's per-role Y transform (icoYL/icoYR) is not touched at all. THE SPLIT IS TUNED NOW
      // and the two groups no longer agree: the side marks got a DARK DROP (near-black #1a1a1a @
      // 0.5) while the centre damage pair kept the gold halo (icoGlowCol #ffcd5a @ 0.5). That is
      // why the split exists -- do not "restore" these to the gold.
      {id:"reqGlowCol",label:"REQUIREMENT (side mark) icon glow colour",color:true,val:"#1a1a1a"},
      {id:"reqGlowA",label:"REQUIREMENT (side mark) icon glow alpha (0 = off)",min:0,max:1,step:0.01,val:0.5},
      // barrel_mark on TOP: the mark glyph reads as "the average that earns marks", and the
      // general-MoE slot below it is icon_battle_condition_top now, so the two no longer collide.
      {id:"dmgPIco",label:"TOP centre glyph (pre_avg)",opts:["damage","barrel_mark"],val:"barrel_mark"},
      {id:"dmgCIco",label:"BOTTOM centre glyph (proj_avg)",opts:["damage","barrel_mark"],val:"damage"},
      // Signed per-ROLE baseline nudge (the glyph families sit differently on their baselines).
      // Stays on .mp-ico's own transform -- see the CSS note; a margin would kill the glow scope.
      {id:"icoYL",label:"LEFT mark icon Y offset (rem, signed)",min:-20,max:20,step:0.1,val:0.5},
      {id:"icoYP",label:"TOP damage icon Y offset (rem, signed)",min:-20,max:20,step:0.1,val:0},
      {id:"icoYC",label:"BOTTOM damage icon Y offset (rem, signed)",min:-20,max:20,step:0.1,val:1},
      {id:"icoYR",label:"RIGHT mark icon Y offset (rem, signed)",min:-20,max:20,step:0.1,val:0.5},
      // ...and the same nudge for the side captions' NUMERALS -- a FONT METRICS fix, not a box fix.
      // MoEBattle.ttf is asc 2088 / desc 486 at upem 2048 = a 1.2568em line box (17.60rem at the
      // 14rem side font-size), but the digit ink only spans -0.0132..0.7192em, so the ink centre
      // sits 0.0381em = 0.53rem BELOW the line box's centre -- i.e. below the track midline that
      // .mp-cap.side's translateY(-50%) centres the box on. Hence a signed transform on the .mp-v
      // child (it is a flex item, so transform applies). Do NOT "fix" this with min-height: the box
      // is ALREADY 17.60rem tall, so any min-height <= that (e.g. markBox's 17) is a literal no-op.
      // The tuner inlines the real ttf, so this is dialled in the browser -- a battle WINDOW cannot
      // hot-reload, so every guess made in-game costs a full client relaunch.
      {id:"numY",label:"Side caption numeral Y (rem)",min:-4,max:4,step:0.1,val:-0.5}]],
    ["Backdrop (checker + radial, cloned from .mb-backdrop)",[
      {id:"bdBleedX",label:"Horizontal bleed (rem)",min:0,max:200,step:1,val:80},
      // Captions are ABSOLUTE now, so the root's flow height is just the track -> the backdrop is
      // centred on the track: bdTop = -(bdH - trackH)/2. That recomputation is why the old -10
      // does NOT transfer: -10 dated from when the captions were IN FLOW and the root was ~72rem
      // tall, so top:-10 already sat above the whole stack; with an absolute-caption root the same
      // -10 shoves the backdrop up off the track entirely. The maintainer's tuning returned -34
      // UNCHANGED (the formula at trackH 3 would say -34.5 -- they kept -34; do not "correct" it).
      {id:"bdTop",label:"Top (rem, negative = above)",min:-120,max:40,step:0.5,val:-34},
      {id:"bdH",label:"Height (rem, EXPLICIT)",min:10,max:200,step:1,val:72},
      {id:"dotAlpha",label:"Dither strength (opacity)",min:0,max:1,step:0.01,val:0.1},
      {id:"dotRX",label:"Dither fade size X (%)",min:0,max:250,step:1,val:56},
      {id:"dotRY",label:"Dither fade size Y (%)",min:0,max:250,step:1,val:110},
      {id:"dotIn",label:"Dither solid to (%)",min:0,max:100,step:1,val:0},
      {id:"dotOut",label:"Dither gone by (%)",min:0,max:120,step:1,val:67},
      {id:"ugRX",label:"Radial size X (%)",min:0,max:250,step:1,val:76},
      {id:"ugRY",label:"Radial size Y (%)",min:0,max:250,step:1,val:57},
      {id:"ug1a",label:"Radial inner alpha",min:0,max:1,step:0.01,val:0.35},
      {id:"ug1p",label:"Radial inner pos (%)",min:0,max:100,step:1,val:0},
      {id:"ug2a",label:"Radial outer alpha",min:0,max:1,step:0.01,val:0},
      {id:"ug2p",label:"Radial outer pos (%)",min:0,max:100,step:1,val:70},
      {id:"loupeZoom",label:"Magnifier zoom (px / game-px)",min:1,max:12,step:1,val:5}]],
    ["Animation (preset dropdown above = the real WG values; sliders stay editable)",[
      {id:"fadeIn",label:"Fade-in (ms)",min:0,max:3000,step:50,val:600},
      {id:"hold",label:"Hold (ms)",min:0,max:12000,step:100,val:5000},
      {id:"fadeOut",label:"Fade-out (ms)",min:0,max:3000,step:50,val:600},
      // Y-axis slide, folded into the SAME mp-life keyframe as the opacity (one animation).
      // Signed: +1 enters from 1rem BELOW and the exit RETURNS the way it came (0 -> +1, i.e. back
      // DOWN), so the bar drops out of frame rather than flying through it. NOT the WG
      // vehicle_messages_panel continue-upward idiom -- deliberately reversed. Negative flips both.
      // ONE distance for in and out: in and out have never wanted different amplitudes. Add a
      // second knob only if they ever do.
      // UNITS -- READ BEFORE TOUCHING slideStops(). This value goes through the unit function
      // (rem() on the stage, REM in the emitted CSS) like every other geometry knob, so 1 here is
      // 1 logical game px == ~0.83 stage px at pxrem 0.833. It did NOT until this was fixed:
      // slideStops() emitted a literal `rem`, and since the tuner HTML declares no root font-size
      // the browser's 16px default made the stage render 1 as 19.2 rem-equivalents. So the slide
      // was tuned against a stage showing 19.2x the travel it claimed: the look approved at "1" was
      // really ~19.2rem, and the 1rem that shipped ran as a single, physically imperceptible px.
      // Hence val 20 -- the maintainer's approved replacement (see MoEProgress.css's mp-life note),
      // which is also WG's own dominant non-zero keyframe translate (their floor is 3rem, so 1rem
      // was an order of magnitude below anything WG animates). Never re-introduce a literal unit
      // here -- the stage lies silently when you do.
      // RANGE +/-85rem = the largest keyframe translate WG themselves animate, so the settled 20
      // is not pinned at the maximum and the whole WG-plausible span stays explorable.
      // FRACTIONAL (step 0.1) so a sub-logical-px nudge stays expressible at the small end -- the
      // emitted translateY() prints the float as-is.
      {id:"slide",label:"Slide distance (rem, signed FLOAT - + = up from below)",min:-85,max:85,step:0.1,val:20},
      {id:"fadeEase",label:"Slide/fade-IN easing",opts:EASE,val:"ease-in"},
      {id:"outEase",label:"Slide/fade-OUT easing",opts:EASE,val:"ease-in"},
      {id:"tickDelay",label:"Tick-move delay (ms) - default = fade-in",min:0,max:4000,step:50,val:600},
      {id:"tickDur",label:"Tick-move duration (ms)",min:0,max:4000,step:50,val:600},
      {id:"tickEase",label:"Tick-move easing",opts:EASE,val:"cubic-bezier(.2,.8,.2,1)"},
      // The (+N) delta FADES in at the swap rather than snapping. OPACITY, not visibility and not
      // display: opacity keeps the box laid out exactly as visibility did (removing it would
      // re-centre the translateX(-50%) caption row mid-animation -- the original reason display was
      // rejected, still valid), and it is the only one of the three a transition can interpolate.
      // Duration + easing default to the TICK MOVE's (tickDur 600 / tickEase), so the delta finishes
      // appearing exactly when the fill and tick finish moving -- one commit gesture, one curve.
      {id:"dFadeMs",label:"Delta (+N) fade-in duration (ms)",min:0,max:2000,step:50,val:600},
      {id:"dFadeEase",label:"Delta (+N) fade-in easing",opts:EASE,val:"cubic-bezier(.2,.8,.2,1)"},
      {id:"pulseMs",label:"Glow pulse period (ms)",min:200,max:4000,step:50,val:1200}]],
    ["Mock data (BattleSnapshot shape)",[
      {id:"marks",label:"Marks held (0-3) - resets the two thresholds",min:0,max:3,step:1,val:1},
      {id:"thrPrev",label:"thresholds[m] - axis left end",min:0,max:6000,step:10,val:2450},
      {id:"thrNext",label:"thresholds[m+1] - requirement",min:100,max:6000,step:10,val:3050},
      {id:"preAvg",label:"pre_avg (career moving average)",min:0,max:6000,step:1,val:2905},
      {id:"projAvg",label:"proj_avg (after this battle)",min:0,max:6000,step:1,val:2913},
      {id:"winN",label:"Windowed mode: +/- N damage",min:5,max:600,step:5,val:60},
      {id:"pxrem",label:"px per rem on this stage",min:0.2,max:3,step:0.001,val:+(2.0*SCALE).toFixed(3)}]]
  ];

  var st={}, axis="mark", UI={};
  SCHEMA.forEach(function(sec){sec[1].forEach(function(c){st[c.id]=c.val;});});
  // NOTE: holdVis (the checkbox), NOT hold -- st.hold is the hold-DURATION slider above.
  // rib defaults OFF: the backdrop already carries a real WG fly-up ribbon, so the mock stack
  // would read as two feeds. Turn it on to judge the gap against a looping 3-deep stack.
  st.holdVis=true; st.bounds=false; st.rib=false; st.bd=true; st.pulse=false;
  // The two garage-cloned track treatments default ON (that is how the hangar bar ships).
  st.dashOn=true; st.bdrOn=true;

  var anchor=document.getElementById("mp-anchor"),
      root=document.getElementById("moe-bar-root"),
      fill=root.querySelector(".mp-fill"),
      tPre=root.querySelector(".mp-pre"), tProj=root.querySelector(".mp-proj"),
      capL=root.querySelector(".mp-capL"), capP=root.querySelector(".mp-capP"),
      capC=root.querySelector(".mp-capC"), capR=root.querySelector(".mp-capR"),
      bd=root.querySelector(".mp-backdrop"), ribs=document.getElementById("ribbons"),
      dyn=document.createElement("style");
  document.head.appendChild(dyn);
  // The signed NUMBER inside the delta's parens -- the only part of "(+8)" that glows.
  var capDN=capC.querySelector(".mp-d-num");
  function capV(c){return c.querySelector(".mp-v");}
  function capI(c){return c.querySelector(".mp-ico");}
  // The mark glyph for a caption: k in 1..3 -> mk<k>; k=4 (marks=3, no higher mark) -> the
  // general MoE glyph; k=0 (marks=0, nothing held) -> nothing at all.
  function setIco(c,k){var i=capI(c);
    i.className="mp-ico"+(k===0?" none":k===4?" moe":" mk mk"+k);}

  // ---- axis: the one knob that decides whether a 1/50th-of-the-gap nudge is visible ----
  function bounds(){
    if(axis==="zero") return [0,st.thrNext];
    if(axis==="win")  return [st.projAvg-st.winN,st.projAvg+st.winN];
    return [st.marks>0?st.thrPrev:0,st.thrNext];
  }
  function pct(v){var b=bounds(),w=b[1]-b[0];if(w<=0)return 0;return Math.max(0,Math.min(1,(v-b[0])/w))*100;}
  function met(){return st.projAvg>=st.thrNext;}

  function trackBg(){return hexA(st.trackCol,st.trackA);}
  function fillBg(){return hexA(st.fillCol,st.fillA);}
  // The three garage/glow builders take a UNIT function: rem() for the live stage (px on this
  // 1600x900 frame) and REM for the emitted CSS (literal rem). Same string both ways otherwise.
  function REM(v){return v+"rem";}
  // Garage dash grid re-drawn as a gradient (bg_pattern_small.png is img://, dead in a browser).
  // LONG-FORM 4 stops, not the modern two-position shorthand -- Coherent's CSS subset is old.
  // The GAP stripe carries its own colour+alpha so it paints OVER the fill (see the .mp-track::after
  // note: the garage's fill is pattern art with transparent gaps, i.e. a mask). gapA 0 emits the
  // literal `transparent` -- the exact old output, not an rgba(...,0) that renders the same.
  function dashBg(u){if(!st.dashOn)return "none";var c=hexA(st.dashCol,st.dashA),
      g=st.gapA>0?hexA(st.gapCol,st.gapA):"transparent";
    return "repeating-linear-gradient(90deg,"+c+" 0px,"+c+" "+u(st.dashW)+","+g+" "+u(st.dashW)+
      ","+g+" "+u(st.dashW+st.dashGap)+")";}
  // Garage ring: an OUTSET spread shadow (no `inset`), so it paints outside the track box and the
  // box model -- hence trackH and the tick/bdTop centring -- is untouched.
  function bdrSh(u){return st.bdrOn?"0 0 0 "+u(st.bdrW)+" "+hexA(st.bdrCol,st.bdrA):"none";}
  // Optional `c` (an already-resolved rgba) swaps the colour while keeping the tick's own two-pass
  // radii -- that is how the .mp-up/.mp-down tick glows borrow upCol/dnCol without a second knob.
  function projSh(u,c){c=c||hexA(st.projGlowCol,st.projGlowA);
    return "0 0 "+u(st.projGlowB)+" "+c+",0 0 "+u(st.projGlowB2)+" "+c;}
  function dotMask(){return "radial-gradient("+st.dotRX+"% "+st.dotRY+"% at 50% 50%,#000 "+st.dotIn+"%,transparent "+st.dotOut+"%)";}
  function ugGrad(){return "radial-gradient("+st.ugRX+"% "+st.ugRY+"% at 50% 50%,rgba(0,0,0,"+st.ug1a+") "+st.ug1p+"%,rgba(0,0,0,"+st.ug2a+") "+st.ug2p+"%)";}
  function textSh(){return "0px 0px "+rem(st.shBlur)+" "+hexA(st.shColor,st.shAlpha);}
  function total(){return st.fadeIn+st.hold+st.fadeOut;}
  // background-size that frames a centred glyph to a target fraction of its box.
  function icoSz(bb){return (100/bb*st.icoFill).toFixed(1)+"%";}

  // Position fill + moving tick + its caption. anim=false snaps (used to rewind before a replay).
  function setPos(v,anim){
    var p=pct(v).toFixed(3)+"%";
    fill.style.transition=anim?"":"none";tProj.style.transition=anim?"":"none";capC.style.transition=anim?"":"none";
    fill.style.width=p;tProj.style.left=p;capC.style.left=p;
  }

  // The bottom-centre numeral shows pre_avg while the bar fades + slides IN, then swaps to
  // proj_avg at tickDelay -- the same instant the fill/tick begin their move (that delay IS the
  // CSS transition-delay on both), so the number never claims a gain the bar has not shown yet.
  // The DELTA, the sign glow and the FILL colour all arrive WITH the swap for the same reason.
  // The delta FADES in (opacity 0 -> 1, transition on .mp-d) rather than snapping: opacity keeps
  // the box laid out, so the translateX(-50%) centring of the caption row cannot shift -- the same
  // reason display was rejected -- and unlike visibility it interpolates.
  // swapped is module state so apply() (called by every slider) re-renders the CURRENT phase
  // instead of snapping the numeral forward; swapT is cleared on every replay so a pending swap
  // from an aborted run cannot fire into the next one.
  var swapped=true, swapT=null, capD=capC.querySelector(".mp-d");
  function showVal(sw){
    var d=st.projAvg-st.preAvg, cv=capV(capC);
    cv.textContent=fmt(sw?st.projAvg:st.preAvg);
    capD.style.opacity=sw?"1":"0";
    capDN.textContent=(d>0?"+":d<0?"-":"")+fmt(Math.abs(d));
    // THE COLD-ENTRY WINDOW KEEPS THE PREVIOUS COMMITTED SIGN. Before the swap the new sign is not
    // known yet, so the entry must not flash a neutral: it paints in whatever the LAST sw==true
    // call left on these elements and only crosses over AT the swap (red bar that earns damage
    // reads red, then turns green; a bar that was and stays red never blinks). Hence the early
    // return -- sw==false deliberately removes nothing. The very first show has nothing committed,
    // so it gets no class at all and falls back to the neutral cream --fillbg.
    if(!sw)return;
    // THE CLASSES KEY OFF THE ROUNDED VALUE SO GLYPH AND GLOW CAN NEVER DISAGREE. `d` is a raw
    // float but the text above is rounded by fmt(), so an unrounded test glowed GREEN on a
    // displayed "(+0)" (any 0 < d < 0.5) and RED on "(-0)". Tested on the MAGNITUDE exactly as
    // fmt() rounds it -- NOT Math.round(d), which is -0 at d == -0.5 while the text reads "(-1)".
    // Zero -> NEITHER class, on the numerals, the fill AND the current tick alike: each falls back
    // to its neutral (white + dark drop / --fillbg / --projsh). This is the ONE path that still
    // CLEARS, and it must: a rounded-zero commit has to wipe the carried-over sign colour, or a
    // stale red survives into the neutral "(+0)" state.
    var glows=Math.round(Math.abs(d))!==0;
    [cv,capDN,fill,tProj].forEach(function(e){
      e.classList.toggle("mp-up",glows&&d>0);e.classList.toggle("mp-down",glows&&d<0);});
  }

  function apply(){
    // Marks slider drives the two thresholds off the real snapshot table (m=3 -> the 100% stop).
    if(st.marks!==st._marks){st._marks=st.marks;
      var nx=st.marks>=3?100:st.marks+1;
      set("thrPrev",THR[st.marks]);set("thrNext",THR[nx]);}
    var S=anchor.style;
    S.setProperty("--top",(st.offY*PXVH).toFixed(1)+"px");S.setProperty("--offx",rem(st.offX));
    S.setProperty("--barw",rem(st.barW));S.setProperty("--trackh",rem(st.trackH));
    S.setProperty("--tickw",rem(st.tickW));S.setProperty("--tickh",rem(st.tickH));
    S.setProperty("--gapreq",rem(st.gapReq));S.setProperty("--gapcur",rem(st.gapCur));
    S.setProperty("--gapendl",rem(st.gapEndL));S.setProperty("--gapendr",rem(st.gapEndR));
    S.setProperty("--reqfs",rem(st.reqFS));S.setProperty("--curfs",rem(st.curFS));
    S.setProperty("--endfs",rem(st.endFS));
    // ...and each caption's PINNED line box, DERIVED from the same font-size knob (see lh()): a
    // literal here would leave the box behind the next size retune, which is the whole failure
    // mode being fixed.
    S.setProperty("--reqlh",rem(lh(st.reqFS)));S.setProperty("--curlh",rem(lh(st.curFS)));
    S.setProperty("--endlh",rem(lh(st.endFS)));
    S.setProperty("--wt",st.wt);S.setProperty("--ls",st.ls+"em");S.setProperty("--textsh",textSh());
    S.setProperty("--trackbg",trackBg());S.setProperty("--fillbg",fillBg());
    // The fill's signed colours: the SAME upCol/dnCol the numerals glow with, at the fill's own
    // alpha so the existing fill-alpha knob keeps governing the bar.
    S.setProperty("--upfill",hexA(st.upCol,st.fillA));S.setProperty("--dnfill",hexA(st.dnCol,st.fillA));
    S.setProperty("--endcol",hexA(st.endCol,st.endA));
    S.setProperty("--precol",hexA(st.preCol,st.preA));S.setProperty("--projcol",hexA(st.projCol,st.projA));
    // Garage-cloned track treatment (dash grid + outset ring, both on .mp-track::after) and the
    // CURRENT tick's own two-pass glow.
    S.setProperty("--dashbg",dashBg(rem));S.setProperty("--bdrsh",bdrSh(rem));
    S.setProperty("--projsh",projSh(rem));
    // The CURRENT tick's SIGNED glows: upCol/dnCol at DGA, the tick's own radii (see projSh).
    S.setProperty("--projshup",projSh(rem,hexA(st.upCol,DGA)));
    S.setProperty("--projshdn",projSh(rem,hexA(st.dnCol,DGA)));
    // Icons: size DERIVED from the measured bbox so both families land at the same visual fill.
    S.setProperty("--icobox",rem(st.icoBox));S.setProperty("--markbox",rem(st.markBox));
    // Two independent icon glows: --icoglow = the centre damage pair, --reqglow = the two .side
    // requirement marks (the ::before override; neither touches .mp-ico's transform).
    S.setProperty("--icogap",rem(st.icoGap));S.setProperty("--icoglow",hexA(st.icoGlowCol,st.icoGlowA));
    S.setProperty("--reqglow",hexA(st.reqGlowCol,st.reqGlowA));
    S.setProperty("--icoyl",rem(st.icoYL));S.setProperty("--icoyp",rem(st.icoYP));
    S.setProperty("--icoyc",rem(st.icoYC));S.setProperty("--icoyr",rem(st.icoYR));
    S.setProperty("--numy",rem(st.numY));
    S.setProperty("--dmgpbox",rem(st.dmgPBox));S.setProperty("--dmgcbox",rem(st.dmgCBox));
    // ...and the negative margin that cancels each of those boxes out of the caption's width, so
    // translateX(-50%) centres the NUMERAL on the tick (see .mp-capP/.mp-capC .mp-ico). Derived
    // from the SAME two sliders + icoGap -- never a literal, or a retune breaks the centring.
    S.setProperty("--dmgpml",rem(-(st.dmgPBox+st.icoGap)));S.setProperty("--dmgcml",rem(-(st.dmgCBox+st.icoGap)));
    S.setProperty("--dmgpimg","url("+DMG[st.dmgPIco].u+")");S.setProperty("--dmgpsz",icoSz(DMG[st.dmgPIco].bb));
    S.setProperty("--dmgcimg","url("+DMG[st.dmgCIco].u+")");S.setProperty("--dmgcsz",icoSz(DMG[st.dmgCIco].bb));
    S.setProperty("--moeimg","url("+MOEURI+")");S.setProperty("--moesz",icoSz(MOEBB));
    S.setProperty("--glowc",hexA(st.glowCol,st.glowA));S.setProperty("--glowb",rem(st.glowB));S.setProperty("--glowb2",rem(st.glowB2));
    // MET-state fill: the glow's own gold (glowCol), the fill's own alpha.
    S.setProperty("--fullfill",hexA(st.glowCol,st.fullFillA));
    // Delta sign glow (shipped alpha 0.9, fixed -- see DGA).
    S.setProperty("--upc",hexA(st.upCol,DGA));S.setProperty("--dnc",hexA(st.dnCol,DGA));
    S.setProperty("--dgw",rem(st.dGlowW));S.setProperty("--dgt",rem(st.dGlowT));
    S.setProperty("--tickdur",st.tickDur+"ms");S.setProperty("--tickdelay",st.tickDelay+"ms");S.setProperty("--tickease",st.tickEase);
    S.setProperty("--dfadms",st.dFadeMs+"ms");S.setProperty("--dfadease",st.dFadeEase);
    // backdrop: explicit box, bled past the bar on both sides
    S.setProperty("--bdleft",rem(-st.bdBleedX));S.setProperty("--bdw",rem(st.barW+2*st.bdBleedX));
    S.setProperty("--bdtop",rem(st.bdTop));S.setProperty("--bdh",rem(st.bdH));
    S.setProperty("--ckbg","url("+CKURI+")");
    // checker at TRUE game scale -- fine cells go sub-pixel HERE, read them in the magnifier
    S.setProperty("--cksize",(CKTILE*SCALE).toFixed(3)+"px "+(CKTILE*SCALE).toFixed(3)+"px");
    S.setProperty("--dotop",st.dotAlpha);S.setProperty("--dotmask",dotMask());S.setProperty("--uggrad",ugGrad());
    bd.style.display=st.bd?"block":"none";
    root.style.outline=st.bounds?"1px dashed #ff5":"none";
    root.classList.toggle("mp-full",met());
    // ---- the four labelled ticks ----------------------------------------------------------
    // End labels read the AXIS ends, which in the mark/zero modes ARE thresholds[m]/[m+1] (or 0
    // / the 100% stop). In windowed mode the ends are the window, so the mark glyphs there read
    // as direction rather than as a stop -- expected.
    var b=bounds();
    capV(capL).textContent=fmt(b[0]);                   // prev requirement (0 when marks=0)
    capV(capR).textContent=fmt(b[1]);                     // next requirement (100% stop at m=3)
    setIco(capL,st.marks);                                // marks=0 -> no icon at all
    setIco(capR,st.marks>=3?4:st.marks+1);                // marks=3 -> the general MoE glyph
    capV(capP).textContent=fmt(st.preAvg);
    // The sign lands on THREE elements, all off the same proj_avg - pre_avg: the bottom caption's
    // main number and its delta's NUMBER child (as a GLOW), plus the fill (as a real background).
    // The parens stay on the .mp-d wrapper (untouched, plain white) and the other three captions
    // never get the class -- same split as the shipped .mb-value.mb-up + .mb-delta-num.mb-up.
    // Which phase is rendered is showVal's job (pre until the swap); apply() only re-renders it.
    showVal(swapped);
    tPre.style.left=pct(st.preAvg).toFixed(3)+"%";
    capP.style.left=pct(st.preAvg).toFixed(3)+"%";
    if(!root.classList.contains("mp-run"))setPos(st.projAvg,false);
    ribs.classList.toggle("on",st.rib);
    ribs.style.left=(st.ribX*PXVW).toFixed(1)+"px";ribs.style.top=(st.ribY*PXVH).toFixed(1)+"px";
    dyn.textContent=keyframes();
    loupe();
    var dp=pct(st.projAvg)-pct(st.preAvg);
    document.getElementById("axisOut").textContent=
      "axis "+fmt(b[0])+" -> "+fmt(b[1])+"   (span "+fmt(b[1]-b[0])+")\n"+
      "pre "+pct(st.preAvg).toFixed(2)+"%  ->  proj "+pct(st.projAvg).toFixed(2)+"%   (move "+dp.toFixed(2)+"% = "+
        (dp/100*st.barW).toFixed(1)+"rem = "+(dp/100*st.barW*st.pxrem).toFixed(1)+" stage px)\n"+
      (met()?"requirement MET -> gold glow":"requirement not met");
    document.getElementById("out").textContent=cssOut();
  }

  // The transient sequence lives in keyframes so the emitted CSS is the same thing the mod ships.
  // GAMEFACE: a transform transition needs MATCHING FUNCTION LISTS across every keyframe, so
  // translateY() appears on ALL FOUR stops (0rem on the held ones) -- never bare on some and
  // absent on others. Separate in/out easings inside ONE animation means per-stop
  // animation-timing-function; the middle stop is linear so the hold does not creep.
  // The exit RETURNS the way it came (+s -> 0 -> 0 -> +s): it slides in from below and drops back
  // DOWN out of frame. Same distance both ways.
  // UNIT FUNCTION, exactly like dashBg/bdrSh/projSh: rem() for the live stage, REM for the
  // emitted CSS. It used to emit a literal `rem` for both, which made it the ONE value that
  // bypassed the pxrem calibration -- see the slide slider's comment for what that cost.
  function slideStops(u){
    var s=st.slide;
    return ["translateY("+u(s)+")","translateY("+u(0)+")","translateY("+u(0)+")","translateY("+u(s)+")"];
  }
  function keyframes(){
    var t=total()||1,a=(st.fadeIn/t*100).toFixed(2),b=((st.fadeIn+st.hold)/t*100).toFixed(2),y=slideStops(rem);
    return "@keyframes mp-life{"+
      "0%{opacity:0;transform:"+y[0]+";animation-timing-function:"+st.fadeEase+"}"+
      a+"%{opacity:1;transform:"+y[1]+";animation-timing-function:linear}"+
      b+"%{opacity:1;transform:"+y[2]+";animation-timing-function:"+st.outEase+"}"+
      "100%{opacity:0;transform:"+y[3]+"}}\n"+
      "@keyframes mp-pulse{0%,100%{box-shadow:0 0 "+rem(st.glowB)+" "+hexA(st.glowCol,st.glowA)+"}"+
      "50%{box-shadow:0 0 "+rem(st.glowB*2)+" "+hexA(st.glowCol,Math.min(1,st.glowA*1.6).toFixed(2))+"}}\n"+
      "#moe-bar-root.mp-run{animation:mp-life "+t+"ms both}\n"+
      "#moe-bar-root.mp-full.mp-pulse .mp-track{animation:mp-pulse "+st.pulseMs+"ms ease-in-out infinite}\n";
  }

  function loupe(){
    var d=document.getElementById("loupeDither"),tile=CKTILE*st.loupeZoom;
    d.style.backgroundImage="url("+CKURI+")";d.style.backgroundSize=tile+"px "+tile+"px";d.style.opacity=st.dotAlpha;
    document.getElementById("loupeCap").textContent=st.loupeZoom+"x - shipped checker.png (2px cells @3840) at opacity "+
      st.dotAlpha+" - the stage paints this "+(st.loupeZoom/SCALE).toFixed(1)+"x smaller (true game scale)";
  }

  // fade-in -> ON COMPLETION the tick+fill move AND the numeral swaps pre->proj -> hold -> fade-out.
  // clearTimeout FIRST: hitting Replay mid-sequence must not let the previous run's pending swap
  // fire into this one. Replay/Damage tick/Fulfil all route through here, so they all get this.
  // The delta's fade is CANCELLED here the same way setPos(...,false) cancels the tick move:
  // transition:none, snap opacity to 0, force a reflow, then hand the transition back -- so a
  // half-finished fade from an aborted run never keeps running into the new cycle.
  function replay(){
    clearTimeout(swapT);capD.style.transition="none";swapped=false;showVal(false);
    root.classList.remove("mp-run","mp-hold");void root.offsetWidth;
    setPos(st.preAvg,false);void root.offsetWidth;
    capD.style.transition="";
    root.classList.add("mp-run");
    requestAnimationFrame(function(){setPos(st.projAvg,true);});
    // Same delay the fill/tick transitions carry, so number and bar commit together.
    swapT=setTimeout(function(){swapped=true;showVal(true);},st.tickDelay);
  }
  root.addEventListener("animationend",function(e){
    if(e.animationName!=="mp-life")return;
    root.classList.remove("mp-run");
    if(st.holdVis)root.classList.add("mp-hold");
    setPos(st.projAvg,false);
    // Belt and braces: a tickDelay longer than the whole transient would otherwise leave the
    // resting bar showing pre_avg forever. This forced settle also lands the delta's fade at
    // opacity 1 (showVal(true) sets it outright, so a cancelled fade cannot strand it part-way).
    clearTimeout(swapT);swapped=true;showVal(true);
  });

  function cssOut(){
    var timings={fadeInMs:st.fadeIn,holdMs:st.hold,fadeOutMs:st.fadeOut,totalMs:total(),
      slideRem:st.slide,slideEasingIn:st.fadeEase,slideEasingOut:st.outEase,
      fadeEasing:st.fadeEase,tickDelayMs:st.tickDelay,tickDurationMs:st.tickDur,tickEasing:st.tickEase,
      // Phase 2's JS needs to know WHEN the bottom numeral flips pre_avg -> proj_avg (and the delta
      // + sign classes appear). It TRACKS tickDelayMs by construction rather than being a second
      // knob -- number and bar commit together. Fork it only if they ever must differ.
      valueSwapMs:st.tickDelay,
      // The (+N) delta's opacity fade, which STARTS at valueSwapMs. Phase 2's JS only has to set
      // opacity 1 there (and back to 0 on a re-run) -- the CSS owns the curve.
      deltaFadeMs:st.dFadeMs,deltaFadeEasing:st.dFadeEase,
      glowPulseMs:st.pulseMs,axisMode:axis,windowN:st.winN,
      topGlyph:st.dmgPIco,bottomGlyph:st.dmgCIco};
    var t=total()||1,ka=(st.fadeIn/t*100).toFixed(2),kb=((st.fadeIn+st.hold)/t*100).toFixed(2),y=slideStops(REM);
    return "/* MoEProgress.css -- in-battle centre-screen MoE progress bar. Tuned in the browser\n"+
      "   (tools/dev/gen_bar_tuner.ps1) and copied VERBATIM; the battle window has no hot-reload.\n"+
      "   Position comes from Python (window.move()), NOT from CSS -- tuner stage placement was\n"+
      "   top "+st.offY+"vh, centre offset "+st.offX+"rem. Font: the bundled MoEBattle numeric subset,\n"+
      "   19 glyphs (digits % ( ) + - , . / space) -- NO LETTERS, a word label renders blank.\n"+
      "   Sizes in rem (1rem == 1 logical px); colours by VALUE (Gameface drops a declaration\n"+
      "   whose var() cannot resolve). JS sets .mp-fill width and the .mp-proj / .mp-capC left as\n"+
      "   percentages, and toggles .mp-up/.mp-down on the fill + the bottom numerals. The two\n"+
      "   axis-end captions are pure CSS (they hang off the track ends), so JS measures nothing. */\n\n"+
      "#moe-bar-root {\n  position: absolute;\n  left: 0;\n  top: 0;\n  width: "+st.barW+"rem;\n"+
      "  z-index: 9000;\n  pointer-events: none;\n  text-align: center;\n"+
      "  font-family: \"MoEBattle\", \"Arial Narrow\", sans-serif;\n  opacity: 0;\n}\n"+
      "/* Backdrop = the .mb-backdrop two-layer trick: checker dither over a dark radial underlay.\n"+
      "   EXPLICIT width+height with a single top/left anchor -- Coherent collapses a top+bottom\n"+
      "   stretch. checker.png + the ttf sit RIGHT BESIDE this CSS (bare sibling urls). */\n"+
      ".mp-backdrop {\n  position: absolute;\n  left: "+(-st.bdBleedX)+"rem;\n  top: "+st.bdTop+"rem;\n"+
      "  width: "+(st.barW+2*st.bdBleedX)+"rem;\n  height: "+st.bdH+"rem;\n  z-index: 0;\n}\n"+
      ".mp-backdrop::before {\n  content: \"\";\n  position: absolute; left: 0; top: 0; width: 100%; height: 100%;\n"+
      "  background: url(checker.png) repeat;\n  background-size: auto;\n  background-position: 0px 0px;\n"+
      "  image-rendering: pixelated;\n  opacity: "+st.dotAlpha+";\n  mask: "+dotMask()+";\n}\n"+
      ".mp-backdrop::after {\n  content: \"\";\n  position: absolute; left: 0; top: 0; width: 100%; height: 100%;\n"+
      "  z-index: -1;\n  background: "+ugGrad()+";\n}\n"+
      ".mp-track {\n  position: relative;\n  z-index: 1;\n  width: 100%;\n  height: "+st.trackH+"rem;\n  background: "+trackBg()+";\n}\n"+
      "/* THE GARAGE BAR'S TRACK TREATMENT, cloned (MoECalculator.css:277-296 -- #moe-root .moe-track).\n"+
      "   The hangar bar gets its vertical dashes from WG's OWN art, a 99x2 strip drawn at\n"+
      "   background-size:99rem 2rem, i.e. 1 art px == 1rem -> 2rem dash + 1rem gap (3rem period),\n"+
      "   cream rgb(236,230,218) at alpha 41/255 = 0.16, repeat-x from the left edge. Same numbers\n"+
      "   here, re-drawn as a gradient because they are SLIDERS in the tuner (a fixed PNG cannot\n"+
      "   follow them) AND because the GAP needs a colour of its own (next paragraph).\n"+
      "   IF Coherent ever drops repeating-linear-gradient, the verified fallback is the garage's own\n"+
      "   line, which renders correctly in the hangar today:\n"+
      "       background-image: url(img://gui/maps/icons/ui/progressbar/bg_pattern_small.png);\n"+
      "       background-repeat: repeat-x; background-size: 99rem 2rem; background-position: left center;\n"+
      "   -- pixel-identical for the MARKS at 2 / 1 / #ece6da / 0.16, but that PNG's gaps are\n"+
      "   TRANSPARENT, so it is only equivalent at gap alpha 0. To keep the masked look on that\n"+
      "   fallback the fill itself would have to carry the pattern (which is literally what the\n"+
      "   hangar does -- see below).\n"+
      "   The garage's \"border\" is NOT a border either: `box-shadow: 0 0 0 1rem rgba(13,14,16,0.5)`,\n"+
      "   an OUTSET ring. Kept as a shadow for the same reason -- a real `border` would grow the\n"+
      "   track past "+st.trackH+"rem and drag the tick centring (top:50%) and the backdrop's bdTop\n"+
      "   centring with it. An outset shadow has ZERO box-model impact, so no box-sizing needed.\n"+
      "   BOTH live on ONE pseudo, with the explicit left/top/width/height box Coherent needs (it\n"+
      "   will not stretch a pseudo from a top+bottom / left+right pair). z-index:1 puts BOTH gradient\n"+
      "   stripes ABOVE the auto-z .mp-fill, and THE GAP STRIPE IS AN OPAQUE DARK COLOUR, not\n"+
      "   `transparent` -- because that is what the hangar bar actually does. Its .moe-fill\n"+
      "   (MoECalculator.css:304-326) has NO background-color whatsoever: it paints\n"+
      "   filled_pattern_small.png ONLY, at the SAME background-size:99rem 2rem / background-position:\n"+
      "   left center as the track's bg_pattern_small, so the two grids are in phase and the fill\n"+
      "   exists ONLY inside the dash marks while the gaps show the dark track backing. The garage\n"+
      "   grid is a MASK, not a wash over a solid bar. This fill IS a solid colour, so the opaque gap\n"+
      "   stripe is what reproduces that read; drop the gap alpha to 0 and the fill floods the gaps\n"+
      "   again (the earlier look, where the bar read as sitting ON TOP of the grid). PHASE: the\n"+
      "   gradient is on the TRACK's pseudo, so its origin is the track's LEFT EDGE -- never the\n"+
      "   fill's right edge -- and the dashes stay in phase across the reached and unreached halves at\n"+
      "   every fill width. Still BELOW the z-index:2 ticks. The ring on the PSEUDO rather\n"+
      "   than on .mp-track also survives .mp-full / .mp-pulse, which both overwrite the track's own\n"+
      "   box-shadow. And because the ring is outset, the fill is flush inside it at 0% and 100%:\n"+
      "   never visually inset, never overlapping. */\n"+
      ".mp-track::after {\n  content: \"\";\n  position: absolute; left: 0; top: 0; width: 100%; height: 100%;\n"+
      "  z-index: 1;\n  background: "+dashBg(REM)+";\n  box-shadow: "+bdrSh(REM)+";\n}\n"+
      "/* Explicit dimensions + a single animated property per rule: Gameface will not interpolate\n"+
      "   what it cannot measure, and a transform transition needs matching function lists. */\n"+
      ".mp-fill {\n  position: absolute;\n  left: 0;\n  top: 0;\n  height: 100%;\n  width: 0;\n  background: "+fillBg()+";\n"+
      "  transition: width "+st.tickDur+"ms "+st.tickEase+" "+st.tickDelay+"ms;\n}\n"+
      "/* THE FILL IS THE ONE PLACE THE SIGN BECOMES A REAL COLOUR. The text rule further down\n"+
      "   (glow, never a fill) is there to keep NUMERALS legible over bright and dark map areas --\n"+
      "   a solid bar has no glyph to keep readable, so it takes the sign directly. Same upCol /\n"+
      "   dnCol as the numerals' glow, so bar and numbers always agree. Zero delta -> NEITHER class\n"+
      "   -> the neutral background above. Two-class selectors so these out-specify .mp-fill, and\n"+
      "   `transition` is deliberately NOT restated here: width stays the ONLY animated property\n"+
      "   (never `transition: all` -- the background must flip, not interpolate). JS toggles the\n"+
      "   class at the same moment it swaps the numeral, i.e. after the entry animation.\n"+
      "   THE NEUTRAL ABOVE MUST NOT BE EITHER SIGN'S COLOUR: it was once the same green as upCol,\n"+
      "   which made every cold damage event flash green through the entry animation (before the sign\n"+
      "   class lands) even while the delta was negative. It is the cream #ede6d9 now. */\n"+
      ".mp-fill.mp-up   { background: "+hexA(st.upCol,st.fillA)+"; }\n"+
      ".mp-fill.mp-down { background: "+hexA(st.dnCol,st.fillA)+"; }\n"+
      "/* FOUR ticks: the two axis ENDS (prev / next requirement), pre_avg, and proj_avg. */\n"+
      ".mp-tick {\n  position: absolute;\n  top: 50%;\n  width: "+st.tickW+"rem;\n  height: "+st.tickH+"rem;\n"+
      "  transform: translate(-50%, -50%);\n  z-index: 2;\n}\n"+
      ".mp-tick.mp-end   { background: "+hexA(st.endCol,st.endA)+"; }\n"+
      ".mp-tick.mp-left  { left: 0; }\n"+
      ".mp-tick.mp-right { left: 100%; }\n"+
      ".mp-tick.mp-pre   { background: "+hexA(st.preCol,st.preA)+"; }\n"+
      "/* The CURRENT tick carries its OWN glow: the same two-pass shape (wide pass + tight core) as\n"+
      "   the gold .mp-full ring and the sign/text glows, so the whole bar speaks one visual language.\n"+
      "   SPECIFICITY, deliberately not fought: `#moe-bar-root.mp-full .mp-tick` below is id + 2\n"+
      "   classes and therefore BEATS this 2-class rule, so the moment the requirement is met the gold\n"+
      "   takes over this tick along with the rest of the bar. That is the intent -- met-requirement\n"+
      "   gold owns the whole bar -- so there is no override knob here. `transition` stays LEFT ONLY;\n"+
      "   the glow is static and must not interpolate. */\n"+
      ".mp-tick.mp-proj  {\n  background: "+hexA(st.projCol,st.projA)+";\n  box-shadow: "+projSh(REM)+";\n"+
      "  transition: left "+st.tickDur+"ms "+st.tickEase+" "+st.tickDelay+"ms;\n}\n"+
      "/* ...AND IT TAKES THE SIGN, exactly like the numerals it carries (JS toggles .mp-up/.mp-down on\n"+
      "   this tick in the same forEach as the caption numerals and the fill -- showVal). Same upCol /\n"+
      "   dnCol as the text glow at the same fixed alpha, with the TICK's own two-pass radii, so\n"+
      "   re-dialling a sign colour moves text and tick together -- which IS \"the same colours as the\n"+
      "   text\". Box-shadow, not text-shadow: the tick is an empty box with no glyphs, and\n"+
      "   filter: drop-shadow would compose with its translate(-50%,-50%). NEUTRAL NEEDS NO RULE --\n"+
      "   the base rule above IS the neutral. SPECIFICITY: these are (0,3,0), out-specifying the\n"+
      "   (0,2,0) base, while `#moe-bar-root.mp-full .mp-tick` is (1,2,0) and still wins on its id, so\n"+
      "   met-requirement gold keeps owning this tick. `transition` is deliberately NOT restated\n"+
      "   (declaration-only override) -- restating it would re-arm the left transition. */\n"+
      ".mp-tick.mp-proj.mp-up   { box-shadow: "+projSh(REM,hexA(st.upCol,DGA))+"; }\n"+
      ".mp-tick.mp-proj.mp-down { box-shadow: "+projSh(REM,hexA(st.dnCol,DGA))+"; }\n"+
      "/* Captions live in the TRACK's coordinate space. The two CENTRE ones stack vertically on\n"+
      "   their tick: pre_avg ABOVE (.up), proj_avg BELOW (.dn, the only one that moves). THAT split\n"+
      "   is load-bearing -- those two sit ~1% apart, so putting them on one side would overlap.\n"+
      "   The two AXIS-END ones are .side: vertically centred on the track's midline and hanging\n"+
      "   OUTSIDE its left / right edge. Each caption is ONE ROW: icon LEFT (DOM order: icon, value,\n"+
      "   delta), numerals right, margin-right as the single gap -- on the left-hand side label that\n"+
      "   puts the NUMBER nearest the axis it labels, which is the right way round. GAMEFACE: plain\n"+
      "   `flex-direction: row`; the earlier `column-reverse` variant (never verified in Coherent)\n"+
      "   is gone, so no unverified flex mode remains.\n"+
      "   WHAT translateX(-50%) CENTRES ON THE TICK IS THE NUMERAL, NOT THE ROW. Centring the whole\n"+
      "   box put the DIGITS left of their own tick by half the icon+gap, and on .dn it drifted as\n"+
      "   the delta's text width changed. So both siblings are taken OUT of the width the transform\n"+
      "   halves, each by the mechanism its constraint allows -- the icon by a negative margin that\n"+
      "   cancels its own box (.mp-capP / .mp-capC .mp-ico), the text-width-dependent delta by going\n"+
      "   out of flow (.mp-cap .mp-d) -- leaving the numeral as the caption's ONLY in-flow content,\n"+
      "   so -50% of the box IS -50% of the digits. Same end state as the sibling Damage Efficiency\n"+
      "   bar, reached differently: there .mp-cap is not a flex row at all. */\n"+
      ".mp-cap {\n  position: absolute;\n  left: 0;\n  transform: translateX(-50%);\n  display: flex;\n"+
      "  flex-direction: row;\n  align-items: center;\n  white-space: nowrap;\n  z-index: 3;\n}\n"+
      "/* GAP DIRECTION IS NOT SYMMETRIC IN GAMEFACE: `bottom: 100%` + margin-bottom (and\n"+
      "   `right: 100%` + margin-right below) are IGNORED by Coherent on an absolutely positioned\n"+
      "   box -- confirmed in-game, both gaps rendered 0, and 0/515 precedents in WG's own _dist\n"+
      "   corpus, while padding-bottom / padding-right have several and DO apply. Hence padding on\n"+
      "   those two directions only; the top:100%+margin-top / left:100%+margin-left twins work as\n"+
      "   written and must NOT be \"unified\" onto padding. */\n"+
      "/* EVERY CAPTION PINS ITS LINE BOX, and that is a BUG FIX, not a style choice. With\n"+
      "   `line-height: normal` the line box is the font's ascent+descent+gap SNAPPED UP TO WHOLE\n"+
      "   DEVICE PIXELS, so in rem it is NOT constant -- it shrinks as the rem->px factor grows. For a\n"+
      "   16rem caption, measured live: 21.000rem at factor 1, 20.500 at 2, 20.125 at 24 (and for the\n"+
      "   12rem delta: 16.000 / 15.500 / 15.083). .mp-ico is a flex item under align-items: center, so\n"+
      "   HALF that variation goes straight into the glyph's Y -- the icon and delta read ~0.75rem low\n"+
      "   relative to the numeral at factor 1 versus factor 2 (reported at 3440x1440).\n"+
      "   THE VALUE: ceil(font_rem * 2 * 1.2565) / 2, i.e. the FACTOR-2 box expressed in rem. 1.2565 is\n"+
      "   MoEBattle.ttf's fitted line ratio and ceil(font_px * 1.2565) reproduces all six measurements\n"+
      "   above. Pinned at the factor-2 value ON PURPOSE rather than at the font's true unsnapped\n"+
      "   ratio: factor 2 is the render this composition was approved on and must not move by even one\n"+
      "   device pixel, while a `1.2565em` line-height computes to 40.2px there and would shift it\n"+
      "   0.75px. Every pin below is therefore byte-identical to what `normal` already yielded at\n"+
      "   factor 2, and only factors != 2 change.\n"+
      "   NO LARGE-MODE TWIN, EVER: line-height is a uniform (vertical) length, so the root font\n"+
      "   (SIZE_F) scales it alone -- a twin would double-apply it. The residual this does NOT fix is\n"+
      "   the glyph's own ascent snap INSIDE the pinned box (sub-0.5rem, and it moves the numeral and\n"+
      "   the delta together rather than pulling them apart).\n"+
      "   ...AND THE PIN IS NOW LOAD-BEARING FOR A SECOND FIX, which is why it must not be reverted or\n"+
      "   turned back into an em: it makes each caption's box a CONSTANT number of rem, so the vertical\n"+
      "   anchor of the pieces hanging off it -- (line box - own box) / 2 + the tuned nudge -- is a\n"+
      "   constant too, and CAN be quantised. It is not, however, a whole number of DEVICE pixels: at the\n"+
      "   shipped values it lands on a quarter of a rem (.mp-capC's glyph: (20.5-16)/2 + 1 == 3.25rem),\n"+
      "   which is whole only where the rem->px factor is a multiple of 4. At factor 2 it is a whole HALF\n"+
      "   pixel -- the approved render. At factor 1 (interface scale 1, reported at 3440x1440) it is 0.75\n"+
      "   of a device pixel, so the engine resolves the glyph's box origin DOWN-SCREEN. NO CORRECTION IS\n"+
      "   SHIPPED FOR IT YET, and the reason is worth keeping: a correction has to apply at factor 1 and NOT\n"+
      "   at factor 2, and nothing inside these registered views is known to report the interface scale --\n"+
      "   the surface push that proves the geometry (viewEnv.resizeViewRem) is a write-only C++ sink, and a\n"+
      "   root-font read keyed a whole build that never took effect at any scale. See\n"+
      "   tests/test_caption_anchor_quantisation.py for the measurements and the four attempts. */\n"+
      ".mp-cap.up { bottom: 100%; padding-bottom: "+st.gapReq+"rem; font-size: "+st.reqFS+"rem;\n"+
      "             line-height: "+lh(st.reqFS)+"rem; }\n"+
      ".mp-cap.dn { top: 100%; margin-top: "+st.gapCur+"rem; font-size: "+st.curFS+"rem;\n"+
      "             line-height: "+lh(st.curFS)+"rem; }\n"+
      "/* SIDE (axis-end) captions -- the .mp-tick vertical trick: top:50% + translateY(-50%) centres\n"+
      "   the flex row's box on the track midline. `left: auto` is REQUIRED on the left one because\n"+
      "   .mp-cap sets left:0 and right:100% alone would not release it. TWO classes so the transform\n"+
      "   out-specifies .mp-cap's translateX(-50%): these are not centred on a tick, they are pushed\n"+
      "   off the end by their OWN, INDEPENDENTLY TUNED gap -- and by different properties:\n"+
      "   padding-right on the LEFT one (margin is dropped on the `right:100%` anchored side -- see\n"+
      "   the note above), margin-left on the RIGHT one, where that direction works. Nothing\n"+
      "   shares a band with them, so there is no\n"+
      "   de-collision pass and JS never measures or repositions them. The translateY(-50%) is on the\n"+
      "   CAPTION box while the per-role icon nudge is on the .mp-ico CHILD, so the two transforms\n"+
      "   cannot clobber each other and .mp-ico keeps its own stacking context (see below). Their\n"+
      "   font-size is their OWN (not .up's): these are side labels, not top labels. */\n"+
      ".mp-cap.side { top: 50%; transform: translateY(-50%); font-size: "+st.endFS+"rem;\n"+
      "               line-height: "+lh(st.endFS)+"rem; }\n"+
      "/* SIDE-CAPTION NUMERAL NUDGE -- a FONT METRICS correction, not a box-height problem.\n"+
      "   MoEBattle.ttf is ascender 2088 / descender 486 at upem 2048 = a 1.2568em line box\n"+
      "   (17.60rem at the "+st.endFS+"rem side font-size), but the digit ink spans only\n"+
      "   -0.0132em..0.7192em of the em box -- so the ink's centre sits 0.0381em = 0.53rem BELOW the\n"+
      "   line box's centre, and it is the BOX that .mp-cap.side's translateY(-50%) centres on the\n"+
      "   track midline. Result: the numerals read ~0.53rem low; this transform pulls them back.\n"+
      "   Do NOT \"fix\" this with min-height/line-height on the caption -- the box is ALREADY\n"+
      "   17.60rem tall, so any min-height at or below that (the 17rem mark box, say) is a literal\n"+
      "   no-op. (The line-height PIN above is not that fix and does not disturb this one: it states\n"+
      "   the snapped-up box, "+lh(st.endFS)+"rem, which is what `normal` already yielded at BOTH\n"+
      "   factor 1 and factor 2 for this font size -- it only stops the box shrinking at higher\n"+
      "   factors, and the ink offset it corrects is a font-metrics constant either way.)\n"+
      "   Scoped to .side only: .up/.dn hang off the track edges instead of being centred on\n"+
      "   the midline, so they must never pick this up. .mp-v is a flex item of the .mp-cap row, so\n"+
      "   a transform applies to it (it would not on a bare inline span). */\n"+
      ".mp-cap.side .mp-v { transform: translateY("+st.numY+"rem); }\n"+
      ".mp-cap.side.mp-capL { left: auto; right: 100%; padding-right: "+st.gapEndL+"rem; }\n"+
      ".mp-cap.side.mp-capR { left: 100%; margin-left: "+st.gapEndR+"rem; }\n"+
      "/* The ONE gap, on every caption. The two CENTRE captions then cancel their icon's whole outer\n"+
      "   width with a negative margin-left further down -- see the .mp-capP / .mp-capC rules. */\n"+
      ".mp-cap .mp-ico { margin-right: "+st.icoGap+"rem; }\n"+
      ".mp-cap .mp-v,\n.mp-cap .mp-d {\n  color: #ffffff;\n  font-weight: "+st.wt+";\n"+
      "  letter-spacing: "+st.ls+"em;\n"+
      "  text-shadow: 0rem 0rem "+st.shBlur+"rem "+hexA(st.shColor,st.shAlpha)+";\n}\n"+
      "/* FOR TEXT THE SIGN IS A COLOURED GLOW, NEVER A FILL (shipped .mb-up/.mb-down): the numerals\n"+
      "   stay WHITE and a green/red text-shadow halo carries the sign, layered OVER the dark\n"+
      "   legibility drop so it reads on bright AND dark map areas. Do NOT \"fix\" this into\n"+
      "   color: green/red. (The .mp-fill.mp-up/.mp-down rules above ARE a real colour fill, on\n"+
      "   purpose: that argument is about keeping GLYPHS readable and a solid bar has no glyph.\n"+
      "   Text glows, bar fills, both off the same upCol/dnCol -- do not \"unify\" them either way.)\n"+
      "   Triple shadow: dark drop, WIDE pass, TIGHT core pass.\n"+
      "   THE SPLIT (verbatim from MoEBattle.css's .mb-delta > .mb-delta-num): the delta wrapper\n"+
      "   .mp-d holds the PARENS as static text nodes and keeps the plain white treatment; only\n"+
      "   its .mp-d-num child carries the signed digits and the glow -- so \"(\" and \")\" never glow.\n"+
      "   Markup: <span class=\"mp-d\">(<span class=\"mp-d-num\">+8</span>)</span>.\n"+
      "   WHO GLOWS: the BOTTOM-CENTRE caption only -- its main number (.mp-capC .mp-v) and the\n"+
      "   delta number, both off the SAME proj_avg - pre_avg sign. The two requirement captions and\n"+
      "   the top-centre pre_avg caption are plain white: JS must never put .mp-up/.mp-down on\n"+
      "   them. A ZERO delta gets NEITHER class -> white + the dark drop only, so a sub-precision\n"+
      "   change never reads as a win. (The selectors are element-scoped, .mp-v.mp-up not bare\n"+
      "   .mp-up, so they out-specify the .mp-cap .mp-v base rule above.) */\n"+
      "/* em, not rem: the two caption rows have different font-sizes and this gap should track\n"+
      "   them. 0.35em == the shipped .mb-delta's 4.5rem at its 14rem font-size.\n"+
      "   SIZE + NUDGE ARE THE EFFICIENCY BAR'S, carried over after a live pass (MoEEfficiency.css's\n"+
      "   `.mp-cap .mp-d`: font-size 12rem, translate(4.2rem, 2.5rem)). The X half must NOT be added\n"+
      "   again: 0.35em of the delta's OWN 12rem font-size IS 4.2rem, which is exactly how that 4.2rem\n"+
      "   was tuned. So the font-size below is load-bearing for the gap too -- change it and the gap\n"+
      "   moves with it.\n"+
      "   OUT OF FLOW off the numeral's right edge -- the second half of the numeral-centring in\n"+
      "   .mp-cap's note. A negative margin cannot cancel THIS sibling the way it cancels the icon:\n"+
      "   the digits change, so any fixed value would leave the centring drifting with the delta's\n"+
      "   text width. `left: 100%` + margin-left is the SAFE anchored pair (Coherent honours the\n"+
      "   left/top twins; it is `right:100%`+margin-right and `bottom:100%`+margin-bottom that render\n"+
      "   a 0 gap), and it keeps the 0.35em gap byte-for-byte as tuned. Same idiom as the sibling\n"+
      "   MoEEfficiency.css, one declaration short of it: NO `top` HERE, ON PURPOSE. An abspos child\n"+
      "   of a flex container takes its static position as if it were the sole flex item, so\n"+
      "   align-items: center keeps the vertical placement the in-flow box already had and the\n"+
      "   translateY below stays the whole Y story. That bar's `top: 0` anchors to the content-box TOP\n"+
      "   instead, which here would lift the delta by half the row's leftover height -- do not\n"+
      "   \"unify\" them.\n"+
      "   THE DELTA FADES IN at the numeral swap (valueSwapMs): JS sets opacity 1 there and back to\n"+
      "   0 when it re-runs the transient -- the curve is here, not in JS. OPACITY, not visibility\n"+
      "   (which cannot interpolate). display:none would no longer disturb the centring now that the\n"+
      "   box is out of flow -- it DID before, and that is why opacity was picked -- but opacity is\n"+
      "   what interpolates, so it stays. No\n"+
      "   `visibility` alongside: this whole widget is pointer-events:none, so a 0-alpha box has\n"+
      "   nothing to hit-test or focus. ONE transition declaration here, naming ONLY opacity, with\n"+
      "   EXPLICIT ms + easing -- Gameface drops a transition on a property whose value starts from\n"+
      "   a var() it cannot resolve, so never express these two through a custom property.\n"+
      "   CANCELLING it (a re-run mid-fade): set transition:none, opacity 0, force a reflow, then\n"+
      "   restore the transition -- the same idiom the fill/tick rewind uses. */\n"+
      ".mp-cap .mp-d {\n  position: absolute;\n  left: 100%;\n  margin-left: 0.35em;\n"+
      "  font-size: 12rem;\n"+
      "  transform: translateY(2.5rem);\n"+
      // The delta's own line box, pinned by the same rule as the captions above (lh(12) == 15.5) --
      // spelled as a literal because its font-size is one too (no knob owns it).
      "  line-height: 15.5rem;\n  opacity: 0;\n"+
      "  transition: opacity "+st.dFadeMs+"ms "+st.dFadeEase+";\n}\n"+
      ".mp-v.mp-up,\n.mp-d-num.mp-up {\n  color: #ffffff;\n"+
      "  text-shadow: 0rem 0rem "+st.shBlur+"rem "+hexA(st.shColor,st.shAlpha)+",\n"+
      "               0rem 0rem "+st.dGlowW+"rem "+hexA(st.upCol,DGA)+",\n"+
      "               0rem 0rem "+st.dGlowT+"rem "+hexA(st.upCol,DGA)+";\n}\n"+
      ".mp-v.mp-down,\n.mp-d-num.mp-down {\n  color: #ffffff;\n"+
      "  text-shadow: 0rem 0rem "+st.shBlur+"rem "+hexA(st.shColor,st.shAlpha)+",\n"+
      "               0rem 0rem "+st.dGlowW+"rem "+hexA(st.dnCol,DGA)+",\n"+
      "               0rem 0rem "+st.dGlowT+"rem "+hexA(st.dnCol,DGA)+";\n}\n"+
      "/* Only the bottom-centre caption animates (it rides proj_avg); pre_avg's stays put. */\n"+
      ".mp-cap.mp-capC { transition: left "+st.tickDur+"ms "+st.tickEase+" "+st.tickDelay+"ms; }\n"+
      "/* Icon glyphs. GLYPH on ::after, GLOW on ::before with z-index:-1 -- an element's own\n"+
      "   background paints BELOW its pseudos, which is why the two are split (same as .mb-ico).\n"+
      "   The transform keeps .mp-ico a stacking context so that -1 stays scoped here. 106% == the\n"+
      "   overlay's 18rem glow behind a 17rem icon, as a ratio so it follows either box. The glow is\n"+
      "   TWO COLOURS: this base rule is the gold halo the CENTRE damage icons wear; the two axis-end\n"+
      "   requirement marks override it to a dark drop in the next rule.\n"+
      "   FRAMING is derived, not a flat zoom: background-size = 100*(canvas/glyph)*"+st.icoFill+"\n"+
      "   from the MEASURED bboxes (damage 0.219, barrel_mark 0.328, top 0.273 of the 128px canvas), computed\n"+
      "   PER ICON -- the top and bottom centre glyphs are chosen independently, so each carries its\n"+
      "   own background-size. The shipped overlay's flat 260% framed those two at 57% vs 85% fill\n"+
      "   -- visibly different.\n"+
      "   NOTE: .mb-ico.dmg in the shipped widget actually paints barrel_mark, so \"match the\n"+
      "   in-battle widget\" and \"use a distinct damage glyph\" conflict -- this build picked\n"+
      "   "+st.dmgPIco+" (top) / "+st.dmgCIco+" (bottom). brightness(3) lifts the flat grey #d1d1d1 quest_type line art; the\n"+
      "   marksOnGun cuts are 24x24 and ALREADY warm cream (~#ede6d9) -> NO brightness on them.\n"+
      "   Their canvas is constant (glyph y 5..17) and only the WIDTH grows with the count\n"+
      "   (mark_1 x 9..14, mark_2 x 6..17, mark_3 x 3..20), so background-size:contain on ONE\n"+
      "   fixed box renders mark_1 at ~1/3 the width of mark_3 -- do NOT trim per count. At 24px\n"+
      "   of source art they visibly blur above ~24rem. */\n"+
      ".mp-ico {\n  position: relative;\n  display: block;\n  flex: none;\n  width: "+st.icoBox+"rem;\n"+
      "  height: "+st.icoBox+"rem;\n  transform: translate(0rem, 0rem);\n}\n"+
      "/* PER-ROLE VERTICAL NUDGE. Each glyph family sits differently on its baseline (24px\n"+
      "   marksOnGun cuts vs 128px quest_type line art), so every caption's icon gets its own\n"+
      "   signed Y. It MUST stay on this same `transform`: the transform is what makes .mp-ico a\n"+
      "   stacking context and so scopes the ::before glow's z-index:-1 -- swap it for a margin and\n"+
      "   the glow escapes and paints under the whole caption. ::before is centred INSIDE this\n"+
      "   transformed box (left/top 50% + its OWN translate(-50%,-50%)), so the glow travels with\n"+
      "   the glyph and its centring is unaffected at any Y.\n"+
      "   ...AND, ON THE TWO CENTRE CAPTIONS ONLY, THE ICON'S WIDTH CANCELLED -- the first half of the\n"+
      "   numeral-centring in .mp-cap's note. margin-left is -(this caption's own icon box + the gap),\n"+
      "   so the icon's OUTER width is exactly 0 (-box-gap + box + gap): the numeral starts at the\n"+
      "   caption's origin and the glyph still paints "+st.icoGap+"rem to its left, unmoved. A MARGIN and not\n"+
      "   position:absolute precisely so the icon stays IN FLOW -- it keeps the transform above (both\n"+
      "   the Y and the stacking context), and out of flow it would need a top:50% that, on .up,\n"+
      "   resolves against a PADDING box carrying "+st.gapReq+"rem and would drop the glyph half that gap.\n"+
      "   PER CAPTION because the box is per caption (dmgP / dmgC are independent sliders), and\n"+
      "   DERIVED from those sliders + icoGap -- a literal would break the centring on the next\n"+
      "   retune. NOT on the two .side captions: they are not centred on anything, they are pushed\n"+
      "   off the axis ends by their own gap, so cancelling their icon would just slide the label\n"+
      "   inwards over the track. */\n"+
      ".mp-capL .mp-ico { transform: translate(0rem, "+st.icoYL+"rem); }\n"+
      ".mp-capP .mp-ico { transform: translate(0rem, "+st.icoYP+"rem); margin-left: "+
      (-(st.dmgPBox+st.icoGap))+"rem; }\n"+
      ".mp-capC .mp-ico { transform: translate(0rem, "+st.icoYC+"rem); margin-left: "+
      (-(st.dmgCBox+st.icoGap))+"rem; }\n"+
      ".mp-capR .mp-ico { transform: translate(0rem, "+st.icoYR+"rem); }\n"+
      ".mp-ico::before {\n  content: \"\";\n  position: absolute;\n  left: 50%;\n  top: 50%;\n  z-index: -1;\n"+
      "  width: 106%;\n  height: 106%;\n  transform: translate(-50%, -50%);\n"+
      "  background: radial-gradient(circle at 50% 50%, "+hexA(st.icoGlowCol,st.icoGlowA)+" 0%, transparent 73%);\n}\n"+
      "/* THE TWO AXIS-END (.side) MoE REQUIREMENT ICONS GLOW INDEPENDENTLY of the two centre damage\n"+
      "   icons -- own colour, own alpha, and TUNED APART: these two are a DARK DROP (near-black\n"+
      "   "+st.reqGlowCol+" at half alpha) rather than a halo, while the centre pair keeps the gold. Deliberate, not a\n"+
      "   leftover -- the mark glyphs read better lifted off the map by a shadow.\n"+
      "   This targets ::before and sets BACKGROUND ONLY, so:\n"+
      "     - the base rule above still supplies z-index:-1, the 106% box and its own\n"+
      "       translate(-50%,-50%), i.e. the glow's radius geometry is identical for both groups;\n"+
      "     - .mp-ico's OWN transform is not touched, and that matters twice over -- it carries the\n"+
      "       per-role Y nudge (icoYL / icoYR) AND it is the stacking context that scopes the\n"+
      "       z-index:-1 to the icon. Never move this override onto .mp-ico.\n"+
      "   Covers the general-MoE glyph that replaces the right mark at 3 marks (still .mp-capR\n"+
      "   .mp-ico). Specificity (0,2,1) > the base (0,1,1), so only the gradient is replaced. */\n"+
      ".mp-capL .mp-ico::before,\n.mp-capR .mp-ico::before {\n"+
      "  background: radial-gradient(circle at 50% 50%, "+hexA(st.reqGlowCol,st.reqGlowA)+" 0%, transparent 73%);\n}\n"+
      ".mp-ico::after {\n  content: \"\";\n  position: absolute; left: 0; top: 0; width: 100%; height: 100%;\n"+
      "  background-repeat: no-repeat;\n  background-position: center;\n}\n"+
      "/* dmgp = TOP centre (pre_avg), dmgc = BOTTOM centre (proj_avg) -- independent glyph AND box. */\n"+
      ".mp-ico.dmgp { width: "+st.dmgPBox+"rem; height: "+st.dmgPBox+"rem; }\n"+
      ".mp-ico.dmgc { width: "+st.dmgCBox+"rem; height: "+st.dmgCBox+"rem; }\n"+
      ".mp-ico.dmgp::after {\n  background-image: url("+IMG[st.dmgPIco]+");\n"+
      "  background-size: "+icoSz(DMG[st.dmgPIco].bb)+";\n  filter: brightness(3);\n}\n"+
      ".mp-ico.dmgc::after {\n  background-image: url("+IMG[st.dmgCIco]+");\n"+
      "  background-size: "+icoSz(DMG[st.dmgCIco].bb)+";\n  filter: brightness(3);\n}\n"+
      "/* Box parity with .mp-ico.mk: this glyph REPLACES the right caption's mark at 3 marks, so\n"+
      "   without its own size it would inherit .mp-ico's "+st.icoBox+"rem and visibly shrink the caption's icon\n"+
      "   "+st.markBox+" -> "+st.icoBox+"rem at that one moment. "+st.markBox+"rem is already the caption's icon width at marks 1-3, so\n"+
      "   restating it here introduces no new maximum. */\n"+
      ".mp-ico.moe { width: "+st.markBox+"rem; height: "+st.markBox+"rem; }\n"+
      ".mp-ico.moe::after {\n  background-image: url("+IMG.top+");\n"+
      "  background-size: "+icoSz(MOEBB)+";\n  filter: brightness(3);\n}\n"+
      ".mp-ico.mk { width: "+st.markBox+"rem; height: "+st.markBox+"rem; }\n"+
      ".mp-ico.mk::after { background-size: contain; }\n"+
      ".mp-ico.mk1::after { background-image: url("+IMG.mk[0]+"); }\n"+
      ".mp-ico.mk2::after { background-image: url("+IMG.mk[1]+"); }\n"+
      ".mp-ico.mk3::after { background-image: url("+IMG.mk[2]+"); }\n"+
      "/* marks=0 -> the left caption carries NO icon at all. */\n"+
      ".mp-ico.none { display: none; }\n"+
      "/* proj_avg >= thresholds[m+1] -> the WHOLE bar takes the gold glow. */\n"+
      "#moe-bar-root.mp-full .mp-track,\n#moe-bar-root.mp-full .mp-fill,\n#moe-bar-root.mp-full .mp-tick {\n"+
      "  box-shadow: 0 0 "+st.glowB+"rem "+hexA(st.glowCol,st.glowA)+";\n}\n"+
      "/* ...and the FILL's own COLOUR becomes that same gold -- the requirement being met outranks\n"+
      "   the up/down sign. It needs a rule of its OWN: the grouped selector above is the box-shadow\n"+
      "   for the track, the fill AND the ticks, whereas this background must land on .mp-fill only.\n"+
      "   SPECIFICITY: `#moe-bar-root.mp-full .mp-fill` is (1,2,0) and .mp-fill.mp-up / .mp-fill.mp-down\n"+
      "   are (0,2,0), so the gold wins on its own -- no !important, and JS keeps toggling the sign\n"+
      "   classes exactly as before (they simply stop being visible on the fill while .mp-full is on).\n"+
      "   Same gold as the glow (ONE gold in this file), its own alpha because a solid bar needs more\n"+
      "   than the glow's. `transition` is NOT restated: width remains the ONLY animated property --\n"+
      "   the background FLIPS, it does not interpolate, and `transition: all` would break that. */\n"+
      "#moe-bar-root.mp-full .mp-fill {\n  background: "+hexA(st.glowCol,st.fullFillA)+";\n}\n"+
      "#moe-bar-root.mp-full .mp-v {\n"+
      "  text-shadow: 0rem 0rem "+st.shBlur+"rem "+hexA(st.shColor,st.shAlpha)+",\n"+
      "               0 0 "+st.glowB+"rem "+hexA(st.glowCol,st.glowA)+",\n"+
      "               0 0 "+st.glowB2+"rem "+hexA(st.glowCol,st.glowA)+";\n}\n"+
      "/* WG's transient idiom (battle_notifier/BattleNotifierView.css): ONE animation, opacity\n"+
      "   stops at the fade boundaries. JS adds .mp-run to play it and sets the fill/tick target\n"+
      "   AFTER the fade-in completes (tick delay below == the fade-in duration by default). On that\n"+
      "   SAME delay (valueSwapMs in the JSON below) JS swaps the bottom numeral pre_avg -> proj_avg\n"+
      "   and reveals the delta, its sign glow and the fill colour: while the bar is still arriving\n"+
      "   it must not claim a gain it has not shown.\n"+
      "   The Y-axis SLIDE is folded into the same keyframe. GAMEFACE: a transform transition\n"+
      "   needs MATCHING FUNCTION LISTS across every keyframe -> translateY() on ALL FOUR stops\n"+
      "   (0rem on the held ones), never bare on some and absent on others, and the element keeps\n"+
      "   explicit dimensions. Separate in/out easings inside one animation means per-stop\n"+
      "   animation-timing-function; the middle stop is linear so the hold does not creep.\n"+
      "   The exit RETURNS THE WAY IT CAME: the bar slides up from below and drops back DOWN out of\n"+
      "   frame, so the 100% stop repeats the 0% translateY (both +slide) rather than negating it.\n"+
      "   This is NOT WG's vehicle_messages_panel continue-upward idiom -- deliberately reversed. */\n"+
      "@keyframes mp-life {\n"+
      "    0% { opacity: 0; transform: "+y[0]+"; animation-timing-function: "+st.fadeEase+"; }\n"+
      "  "+ka+"% { opacity: 1; transform: "+y[1]+"; animation-timing-function: linear; }\n"+
      "  "+kb+"% { opacity: 1; transform: "+y[2]+"; animation-timing-function: "+st.outEase+"; }\n"+
      "  100% { opacity: 0; transform: "+y[3]+"; }\n}\n"+
      "#moe-bar-root.mp-run { animation: mp-life "+t+"ms both; }\n"+
      "@keyframes mp-pulse {\n  0%, 100% { box-shadow: 0 0 "+st.glowB+"rem "+hexA(st.glowCol,st.glowA)+"; }\n"+
      "  50% { box-shadow: 0 0 "+(st.glowB*2)+"rem "+hexA(st.glowCol,Math.min(1,st.glowA*1.6).toFixed(2))+"; }\n}\n"+
      "#moe-bar-root.mp-full.mp-pulse .mp-track { animation: mp-pulse "+st.pulseMs+"ms ease-in-out infinite; }\n\n"+
      "/* Animation timings for phase 2's JS (the numbers, not just the CSS):\n"+
      JSON.stringify(timings,null,2)+"\n*/\n";
  }

  // ---- panel wiring ----
  function set(id,v){st[id]=v;var u=UI[id];if(u){if(u.rg)u.rg.value=v;if(u.nu)u.nu.value=v;if(u.sel)u.sel.value=v;}}
  var host=document.getElementById("controls");
  SCHEMA.forEach(function(sec){
    var det=document.createElement("details");det.open=true;
    det.innerHTML="<summary>"+sec[0]+"</summary>";
    var g=document.createElement("div");g.className="grp";
    sec[1].forEach(function(c){
      var w=document.createElement("div");w.className="ctl";
      w.innerHTML="<div class='lab'><span>"+c.label+"</span></div><div class='inp'></div>";
      var inp=w.querySelector(".inp");UI[c.id]={};
      if(c.color){
        inp.innerHTML="<input type='color'>";var ci=inp.querySelector("input");ci.value=st[c.id];
        ci.addEventListener("input",function(){st[c.id]=ci.value;apply();});
      }else if(c.opts){
        inp.innerHTML="<select>"+c.opts.map(function(o){return "<option>"+o+"</option>";}).join("")+"</select>";
        var se=inp.querySelector("select");se.value=st[c.id];UI[c.id].sel=se;
        se.addEventListener("change",function(){st[c.id]=se.value;apply();});
      }else{
        inp.innerHTML="<input type='range' min='"+c.min+"' max='"+c.max+"' step='"+c.step+"'>"+
          "<input type='number' min='"+c.min+"' max='"+c.max+"' step='"+c.step+"'>";
        var rg=inp.querySelector("input[type=range]"),nu=inp.querySelector("input[type=number]");
        rg.value=st[c.id];nu.value=st[c.id];UI[c.id].rg=rg;UI[c.id].nu=nu;
        var upd=function(v){v=parseFloat(v);if(isNaN(v))return;set(c.id,v);apply();};
        rg.addEventListener("input",function(){upd(rg.value);});
        nu.addEventListener("input",function(){upd(nu.value);});
      }
      g.appendChild(w);
    });
    det.appendChild(g);host.appendChild(det);
  });
  [["cHold","holdVis"],["cBounds","bounds"],["cRib","rib"],["cBd","bd"],["cPulse","pulse"],
   ["cDash","dashOn"],["cBdr","bdrOn"]].forEach(function(p){
    document.getElementById(p[0]).addEventListener("change",function(e){
      st[p[1]]=e.target.checked;
      if(p[1]==="holdVis")root.classList.toggle("mp-hold",st.holdVis&&!root.classList.contains("mp-run"));
      if(p[1]==="pulse")root.classList.toggle("mp-pulse",st.pulse);
      apply();});
  });
  // Preset -> sliders (one-way: the sliders remain editable, and tickDelay follows the fade-in
  // since that is what "move the tick once it is visible" means).
  var psel=document.getElementById("preset");
  psel.innerHTML=PRESETS.map(function(p,i){return "<option value='"+i+"'>"+p.n+"</option>";}).join("");
  psel.addEventListener("change",function(){
    var v=PRESETS[+psel.value].v;
    Object.keys(v).forEach(function(k){set(k,v[k]);});
    set("tickDelay",v.fadeIn);apply();replay();});
  document.querySelectorAll("#axisSeg button").forEach(function(b){b.addEventListener("click",function(){
    axis=b.dataset.a;document.querySelectorAll("#axisSeg button").forEach(function(x){x.classList.remove("on");});
    b.classList.add("on");apply();});});
  document.getElementById("bReplay").addEventListener("click",replay);
  // One more battle: today's proj becomes the new pre, and the same EWMA-sized nudge is applied
  // again (EWMA_K = 2/101, so ~1/50th of the gap to the requirement per battle).
  document.getElementById("bTick").addEventListener("click",function(){
    var step=st.projAvg-st.preAvg;if(step<=0)step=Math.max(1,(st.thrNext-st.projAvg)*(2/101));
    set("preAvg",st.projAvg);set("projAvg",+(st.projAvg+step).toFixed(0));apply();replay();});
  document.getElementById("bFull").addEventListener("click",function(){
    set("preAvg",st.thrNext-Math.max(1,Math.round((st.thrNext-st.preAvg)*(2/101))));
    set("projAvg",st.thrNext);apply();replay();});
  document.getElementById("copyBtn").addEventListener("click",function(){
    var t=cssOut();if(navigator.clipboard)navigator.clipboard.writeText(t);
    var b=document.getElementById("copyBtn");b.textContent="Copied";setTimeout(function(){b.textContent="Copy CSS";},1300);});

  // re-shoot the backdrop: file input or drop anywhere on the stage
  var stage=document.getElementById("stage");
  function useShot(f){if(!f)return;var r=new FileReader();
    r.onload=function(){stage.style.backgroundImage="url("+r.result+")";};r.readAsDataURL(f);}
  document.getElementById("shot").addEventListener("change",function(e){useShot(e.target.files[0]);});
  ["dragenter","dragover"].forEach(function(ev){stage.addEventListener(ev,function(e){e.preventDefault();stage.classList.add("drop");});});
  ["dragleave","drop"].forEach(function(ev){stage.addEventListener(ev,function(e){e.preventDefault();stage.classList.remove("drop");});});
  stage.addEventListener("drop",function(e){useShot(e.dataTransfer.files[0]);});

  apply();replay();
</script>
'@

$tpl = $tpl.Replace('__BG__', $bg).Replace('__TTF__', $ttf).Replace('__CK__', $ck).
  Replace('__ICO_DMG__', $ico['icon_battle_condition_damage']).
  Replace('__ICO_BM__', $ico['icon_battle_condition_barrel_mark']).
  Replace('__ICO_TOP__', $ico['icon_battle_condition_top']).
  Replace('__ICO_MK1__', $ico['mark_1']).Replace('__ICO_MK2__', $ico['mark_2']).Replace('__ICO_MK3__', $ico['mark_3'])

$dest = if ([IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path $repo $Out }
if ($SelfCheck) { $dest = Join-Path ([IO.Path]::GetTempPath()) "gen_bar_tuner_selfcheck.html" }
New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
[IO.File]::WriteAllText($dest, $tpl, (New-Object System.Text.UTF8Encoding($false)))

if ($SelfCheck) {
  $fail = @()
  if (-not (Test-Path $dest)) { $fail += "not written: $dest" }
  else {
    $len = (Get-Item $dest).Length
    if ($len -lt 100KB) { $fail += "too small: $len bytes (expected > 100 KB of inlined assets)" }
    if ((Get-Content $dest -Raw) -match '__[A-Z_]+__') { $fail += "unsubstituted placeholder: $($Matches[0])" }
  }
  if ($fail.Count) { $fail | ForEach-Object { Write-Output "FAIL: $_" }; exit 1 }
  Write-Output ("self-check OK: {0} ({1:N0} bytes, no leftover placeholders)" -f $dest, $len)
  exit 0
}
Write-Output ("wrote {0} ({1:N0} bytes)" -f $dest, (Get-Item $dest).Length)

# ---- -EmitCss: the settled stylesheet as a real file -------------------------------------
# cssOut() is NOT reimplemented here. The generated HTML's own <script> is run in a headless DOM
# shim under node and the REAL "Copy CSS" click handler is invoked, so the file is byte-identical
# to what the browser copies at the SCHEMA defaults (the driver asserts clipboard == cssOut() and
# == the panel's live preview, and refuses an unresolved var()/NaN/placeholder). Two ways to get
# the same string cannot drift; a PowerShell port of cssOut() would drift on the next slider.
$DRIVER = @'
// Written by gen_bar_tuner.ps1 -EmitCss. node <this> <tuner.html> <out.css>
const fs = require('fs'), vm = require('vm');
const html = fs.readFileSync(process.argv[2], 'utf8');
const m = html.match(/<script>([\s\S]*)<\/script>/);
if (!m) throw new Error('no <script> block in ' + process.argv[2]);
const El = () => { const sm = {}; const e = {
  children: [], _sel: {}, className: '', textContent: '', innerHTML: '', value: '', dataset: {},
  offsetWidth: 60, checked: false, files: [],
  style: new Proxy({ setProperty: (k, v) => { sm[k] = v; } }, { set(t, k, v) { sm[k] = v; return true; },
    get(t, k) { return k in t ? t[k] : sm[k]; } }),
  classList: { _s: new Set(), add(...c) { c.forEach(x => this._s.add(x)); },
    remove(...c) { c.forEach(x => this._s.delete(x)); },
    toggle(c, f) { (f === undefined ? !this._s.has(c) : f) ? this._s.add(c) : this._s.delete(c); },
    contains(c) { return this._s.has(c); } },
  addEventListener(t, f) { (e._ev = e._ev || {})[t] = f; },
  appendChild(c) { e.children.push(c); return c; },
  querySelector(s) { return e._sel[s] || (e._sel[s] = El()); },
  querySelectorAll() { return []; } }; return e; };
const byId = {};
let COPIED = null;
const ctx = { document: { head: El(), body: El(), createElement: El, querySelectorAll: () => [],
    getElementById: id => byId[id] || (byId[id] = El()) },
  navigator: { clipboard: { writeText: t => { COPIED = t; } } },
  requestAnimationFrame: f => f(), setTimeout: () => 0, clearTimeout: () => { },
  FileReader: function () { this.readAsDataURL = () => { }; },
  console, JSON, Math, Object, String, Number, parseFloat, parseInt, isNaN, Array };
ctx.window = ctx;
vm.runInContext(m[1], vm.createContext(ctx), { filename: 'tuner.js' });
byId['copyBtn']._ev.click({});                       // the REAL Copy CSS handler
if (typeof COPIED !== 'string' || !COPIED.length) throw new Error('Copy CSS produced nothing');
if (COPIED !== ctx.cssOut()) throw new Error('clipboard bytes != cssOut()');
if (COPIED !== byId['out'].textContent) throw new Error('clipboard bytes != the panel preview');
if (/undefined|NaN|\[object|var\(--|__[A-Z_]+__/.test(COPIED)) throw new Error('unresolved value in emitted CSS');
fs.writeFileSync(process.argv[3], COPIED);
'@
if ($EmitCss) {
  if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "gen_bar_tuner: -EmitCss needs node on PATH (it runs the tuner's own cssOut() headlessly)"
  }
  $css = if ([IO.Path]::IsPathRooted($CssOut)) { $CssOut } else { Join-Path $repo $CssOut }
  New-Item -ItemType Directory -Force -Path (Split-Path $css -Parent) | Out-Null
  $drv = Join-Path ([IO.Path]::GetTempPath()) "gen_bar_tuner_emitcss.js"
  [IO.File]::WriteAllText($drv, $DRIVER, (New-Object System.Text.UTF8Encoding($false)))
  try {
    & node $drv $dest $css
    if ($LASTEXITCODE -ne 0) { throw "gen_bar_tuner: -EmitCss driver failed (node exit $LASTEXITCODE)" }
  } finally { Remove-Item -LiteralPath $drv -Force -ErrorAction SilentlyContinue }
  $raw = [IO.File]::ReadAllText($css)
  Write-Output ("wrote {0} ({1:N0} bytes, {2:N0} lines) -- Copy-CSS-identical at the schema defaults" `
    -f $css, [Text.Encoding]::UTF8.GetByteCount($raw), ($raw.ToCharArray() | Where-Object { $_ -eq "`n" }).Count)

  # ---- advisory: the hand-edited blocks this emit does NOT carry --------------------------
  # The shipped stylesheet is the emit PLUS blocks added/rewritten by hand, so copying a fresh
  # emit over it silently drops them. One marker per block; another one is ONE line here. The
  # value says what dropping it breaks -- the first four have already cost a relaunch each.
  $APPENDED = [ordered]@{
    '@font-face'   = 'the bundled MoEBattle @font-face -- without it every numeral silently falls back to Arial Narrow'
    '#moe-bar-box' = 'the body/#moe-bar-box sizing shim -- without it the size calculation times out and the engine clobbers the surface to 256x256'
    'mp-life-b'    = 'the mp-life-b alternating-identity twin -- without it the JS restart is a no-op and the bar never reappears after its first run'
    '.mp-s1'       = 'the interface-scale caption correction (.mp-s1 / .mp-s1.mp-lg on .mp-capC .mp-ico AND on .mp-cap .mp-d) -- without it the bottom-centre damage glyph and its delta each sit one device pixel low at interface scale 1, at both sizes'
    # NOT an appended block but a REWRITTEN one: .mp-track::after ships WG's own tiling idiom
    # (background-image + one 3rem period + background-size + background-repeat) with an OPAQUE
    # gap, while this emit still writes a single track-wide `background:` gradient at gapA 0.5.
    # A naive copy silently reverts both -- the tiling AND the mask read.
    'background-size: 3rem 100%' = 'the WG-idiom dash tiling on .mp-track::after (one 3rem period tiled by background-size, opaque rgb(13,14,16) gap) -- this emit writes one track-wide gradient at gapA 0.5 instead, which floods the gaps and un-masks the fill'
  }
  # Purely advisory: warns, never fails, and a missing/unreadable shipped file is not an error.
  # ($ErrorActionPreference is Stop, hence the explicit try -- and no `$x = try {}`/`= if {}`
  # assignment-from-statement, which Windows PowerShell 5.1 cannot parse.)
  $shipped = $null
  try { $shipped = [IO.File]::ReadAllText((Join-Path $repo "src/res/gui/gameface/mods/14th_ua/MoECalculator/MoEProgress.css")) } catch { }
  $missing = @()
  if ($shipped) { $missing = @($APPENDED.Keys | Where-Object { $shipped.Contains($_) -and -not $raw.Contains($_) }) }
  if ($missing.Count) {
    Write-Warning "the shipped MoEProgress.css carries hand-edited blocks this emit does NOT (some appended, some REWRITTEN in place). Copying it over the shipped file WILL DROP them -- RE-APPLY EACH BY HAND after copying:"
    $missing | ForEach-Object { Write-Warning ("  {0}  ->  {1}" -f $_, $APPENDED[$_]) }
  }
}
