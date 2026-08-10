<#
  gen_bar_tuner_vertical.ps1 -- PowerShell (pwsh 7+ / Windows PowerShell 5.1). Run from the repo root:

      pwsh tools\dev\gen_bar_tuner_vertical.ps1 [-Out TASKS/refs/in-battle-bar-tuner-vertical.html]
                                                 [-Backdrop <any image>] [-ExtractIcons] [-SelfCheck]
                                                 [-EmitCss [-CssOut TASKS/refs/MoEProgressVertical.css]]
                                                 [-Artifact [-ArtifactOut TASKS/refs/in-battle-bar-tuner-vertical.artifact.html]]

  -Artifact writes a SKELETON-FREE variant (no <!DOCTYPE>/<html>/<head>/<body> -- just <title>,
  <style>, the markup and <script>) for publishing as a Claude Artifact, whose host wraps the
  given HTML in its own document skeleton and enforces a strict CSP (no external hosts at all).
  DERIVED from the same $tpl as the normal output, never a forked template, so the two cannot
  drift -- every asset is already a base64 data: URI via Asset() above, so nothing further is
  needed to satisfy "zero external hosts".

  Sibling of gen_bar_tuner.ps1 (the HORIZONTAL in-battle MoE progress bar tuner), NOT a flag on it --
  see tools/dev/README.md for why this repo keeps independent tuner scripts (gen_overlay_tuner.ps1 /
  eff_bar_tuner.html are the same pattern). This one designs a VERTICAL variant: class prefix .mpv-
  (never .mp-, so the emitted CSS can never collide with the shipped horizontal bar). The bar does
  not exist in the mod yet -- TUNER ONLY, and -EmitCss writes exclusively under TASKS/refs/.

  Axis: value 0 at the BOTTOM of the track, 100% at the TOP -- fill grows bottom->top, height not
  width. Reuses the horizontal tuner's asset/base64 machinery (backdrop jpg, MoEBattle.ttf,
  checker.png, the 7 tick icons), its rem() (stage) / REM() (emit) split, -SelfCheck and -EmitCss.

  ADDED for this variant: a mock in-battle minimap (bottom-right corner, zero inset, size from the
  measured logical-px table in tools/dev/measure_minimap.py:44-47) so the stage preview shows where
  the bar lands relative to it. stageW/stageH simulate the logical resolution being checked; mmIdx
  (0-5) picks the minimap size index; mmGap (logical px, default 8) is the bar's clearance from it
  (measured from the tick's outer edge, not the track's own edge -- see the .mpv-anchor comment);
  mmGapBottom (logical px, default 8) is the bar's clearance from the screen's bottom edge.
  This minimap-relative math is PREVIEW-ONLY -- it never reaches the emitted CSS (same reason the
  horizontal tuner's offX/offY never do: in-game placement is a Python window.move(), not CSS).
#>
param(
  [string]$Out = "TASKS/refs/in-battle-bar-tuner-vertical.html",
  [string]$Backdrop,
  [string]$GameDir = "D:/Games/World_of_Tanks_EU",
  [switch]$ExtractIcons,
  [switch]$SelfCheck,
  [switch]$EmitCss,
  [string]$CssOut = "TASKS/refs/MoEProgressVertical.css",
  [switch]$Artifact,
  [string]$ArtifactOut = "TASKS/refs/in-battle-bar-tuner-vertical.artifact.html"
)
$ErrorActionPreference = "Stop"

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

function Asset($rel) {
  $p = Join-Path $repo $rel
  if (-not (Test-Path $p)) { throw "gen_bar_tuner_vertical: missing asset -> $p (run with -ExtractIcons if this is TASKS/refs/icons/)" }
  [Convert]::ToBase64String([IO.File]::ReadAllBytes($p))
}

# ---- tick icons (identical set/paths to gen_bar_tuner.ps1 -- same glyphs, same repo-local cache) --
$ICONS = @(
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_damage.png',
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_barrel_mark.png',
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_top.png',
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_battles.png',
  'gui/maps/icons/library/marksOnGun/mark_1.png',
  'gui/maps/icons/library/marksOnGun/mark_2.png',
  'gui/maps/icons/library/marksOnGun/mark_3.png'
)
function IconRel($inner) { "TASKS/refs/icons/" + (($inner -replace '^gui/maps/icons/', '') -replace '/', '__') }

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
    if (-not (Test-Path -LiteralPath $pkg)) { throw "gen_bar_tuner_vertical: missing package -> $pkg" }
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
  if ($want.Count) { throw "gen_bar_tuner_vertical: not found in any gui-part pkg -> $($want.Keys -join ', ')" }
}
if ($ExtractIcons) { ExtractIconsNow }


# -Backdrop: resize ANY image to 1600x900 JPEG q82, inline it (verbatim from gen_bar_tuner.ps1).
function Backdrop64($path) {
  $p = if ([IO.Path]::IsPathRooted($path)) { $path } else { Join-Path $repo $path }
  if (-not (Test-Path -LiteralPath $p)) { throw "gen_bar_tuner_vertical: -Backdrop not found -> $p" }
  Add-Type -AssemblyName System.Drawing
  try { $src = [Drawing.Image]::FromFile($p) }
  catch { throw "gen_bar_tuner_vertical: -Backdrop is not a decodable image -> $p ($($_.Exception.Message))" }
  $tmp = Join-Path ([IO.Path]::GetTempPath()) "gen_bar_tuner_vertical_bg.jpg"
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

$bg  = if ($Backdrop) { Backdrop64 $Backdrop } else { Asset "TASKS/refs/tuner-backdrop-ribbon.jpg" }
$ttf = Asset "src/res/gui/gameface/mods/14th_ua/MoECalculator/MoEBattle.ttf"
$ck  = Asset "src/res/gui/gameface/mods/14th_ua/MoECalculator/checker.png"
$ico = @{}
foreach ($i in $ICONS) { $ico[[IO.Path]::GetFileNameWithoutExtension($i)] = Asset (IconRel $i) }

$tpl = @'
<!DOCTYPE html><meta charset="utf-8"><title>MoE in-battle progress bar (vertical) - tuner</title>
<style>
  @font-face{font-family:"MoEBattle";font-weight:400;font-style:normal;src:url(data:font/ttf;base64,__TTF__) format("truetype")}
  @font-face{font-family:"MoEBattle";font-weight:500;font-style:normal;src:url(data:font/ttf;base64,__TTF__) format("truetype")}
  @font-face{font-family:"MoEBattle";font-weight:600;font-style:normal;src:url(data:font/ttf;base64,__TTF__) format("truetype")}
  @font-face{font-family:"MoEBattle";font-weight:700;font-style:normal;src:url(data:font/ttf;base64,__TTF__) format("truetype")}
  :root{--bg:#14151a;--panel:#1d2027;--ink:#e9e6df;--muted:#8b93a1;--line:#2b2f38;--gold:#c79a3f}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI",system-ui,sans-serif;display:flex;min-height:100vh}
  .stagewrap{flex:1;display:flex;align-items:flex-start;justify-content:center;padding:20px;overflow:auto}
  .stage{position:relative;flex:none;border-radius:6px;overflow:hidden;background-color:#000;
    background-image:url("data:image/jpeg;base64,__BG__");background-size:cover;background-position:center;background-repeat:no-repeat;
    box-shadow:0 10px 40px rgba(0,0,0,.5);outline:1px solid var(--line)}
  .stage.drop{outline:2px dashed var(--gold)}

  /* mock in-battle minimap: bottom-right corner, ZERO inset (measured fact, see
     tools/dev/measure_minimap.py:7-10,44-47) -- preview-only, never part of the emitted CSS. */
  #mmMock{position:absolute;right:0;bottom:0;z-index:15;border:1px solid var(--gold);
    background:rgba(30,34,42,.55);box-sizing:border-box;pointer-events:none;
    display:flex;align-items:center;justify-content:center;
    font-family:"Segoe UI",system-ui,sans-serif;font-size:11px;color:var(--gold);letter-spacing:.05em}

  /* ================= THE VERTICAL BAR UNDER DESIGN (.mpv-*, NEVER .mp- -- see the header) =====
     Axis: 0 at the BOTTOM, 100% at the TOP. Anchor sits bottom-right of the stage. ONE shared
     clearance origin: from the track's centreline, half the tick's CROSS-axis length (tickW) --
     i.e. the tick's outer edge, which overhangs the track by (tickW-trackW)/2 each side (ticks are
     wider than the track). The anchor's right inset is `mmGap` logical px clear of the mock
     minimap's left edge, MEASURED FROM THAT TICK OUTER EDGE, not the track's own right edge. Its
     bottom inset is `mmGapBottom` logical px clear of the stage's bottom (== the minimap's bottom,
     since the minimap has zero inset) -- the bar is no longer flush with the screen edge. Position
     is PREVIEW-ONLY: in-game a WindowImpl places the real window from Python, like the horizontal bar. */
  .mpv-anchor{position:absolute;right:var(--anchorr);bottom:var(--anchorb);z-index:9000;pointer-events:none}
  #moe-bar-root{position:relative;width:var(--trackw);height:var(--barh);
    font-family:"MoEBattle","Arial Narrow",sans-serif;text-align:center;opacity:0}
  #moe-bar-root.mpv-hold{opacity:1}
  /* Backdrop: the shipped .mb-backdrop two-layer trick, axes swapped vs the horizontal tuner --
     there the bleed ran horizontally past the bar's ends; here it runs VERTICALLY (bdBleedY), and
     the box that used to be an explicit, hand-tuned vertical rect (bdTop/bdH) is now an explicit
     horizontal one (bdLeft/bdW), because the track is the narrow dimension either way. */
  .mpv-backdrop{position:absolute;left:var(--bdleft);top:var(--bdtop);width:var(--bdw);height:var(--bdh);z-index:0}
  /* PER-ROW STRIPS -- the shipped composition draws the dither on these (one per number row),
     NOT on .mpv-backdrop (kept only as the invisible surface bounding-box marker). Right edge
     flush on the surface's minimap-facing edge; per-row `top` only. */
  .mpv-bd{position:absolute;left:var(--bdstripleft);width:var(--bdstripw);height:var(--bdstriph);z-index:0}
  .mpv-bd::before{content:"";position:absolute;left:0;top:0;width:100%;height:100%;
    background:var(--ckbg) repeat;background-size:var(--cksize);background-position:0 0;
    image-rendering:pixelated;opacity:var(--dotop);-webkit-mask:var(--dotmask);mask:var(--dotmask)}
  .mpv-bd::after{content:"";position:absolute;left:0;top:0;width:100%;height:100%;z-index:-1;background:var(--uggrad)}
  .mpv-bd-1{top:var(--bd1top)}.mpv-bd-2{top:var(--bd2top)}.mpv-bd-3{top:var(--bd3top)}.mpv-bd-4{top:var(--bd4top)}
  .mpv-track{position:relative;z-index:1;width:100%;height:100%;background:var(--trackbg)}
  /* Garage dash-grid + outset ring, cloned from the horizontal tuner (MoECalculator.css:277-296,
     see gen_bar_tuner.ps1 for the full mask-not-overlay history) -- ROTATED: the gradient direction
     is `0deg` ("to top" in CSS), so its first stop sits at the track's BOTTOM edge, matching the
     axis convention (0% value == bottom). The gap stripe is still an OPAQUE colour (gapA), not
     `transparent`: our .mpv-fill is a solid colour, unlike the garage's own pattern-art mask. */
  .mpv-track::after{content:"";position:absolute;left:0;top:0;width:100%;height:100%;z-index:1;
    background:var(--dashbg);box-shadow:var(--bdrsh)}
  /* THE FILL IS A MASK, NOT AN OVERLAY (garage-progress-bar-fill-is-a-mask) -- grows bottom->top. */
  .mpv-fill{position:absolute;left:0;bottom:0;width:100%;height:0;background:var(--fillbg);
    transition:height var(--tickdur) var(--tickease) var(--tickdelay)}
  .mpv-fill.mpv-up{background:var(--upfill)}
  .mpv-fill.mpv-down{background:var(--dnfill)}
  /* Ticks: fixed on the CROSS axis (left:50%), moving on the TRACKED axis (bottom + translateY(50%)
     -- centres a box positioned via `bottom` on that row, the vertical analogue of the horizontal
     tuner's left+translateX(-50%)). Geometry (cross-length/along-thickness) and the cross-axis (X)
     nudge are INDEPENDENT PER TICK TYPE -- end/pre/proj each own their own three knobs, never
     merged (the same never-merge rule the icon Y-nudges already follow). */
  .mpv-tick{position:absolute;left:50%;z-index:2}
  .mpv-end{background:var(--endcol);width:var(--tickwend);height:var(--tickhend);
    transform:translate(-50%,50%) translateX(var(--tickxend))}
  .mpv-bottom{bottom:0}
  .mpv-top{bottom:100%}
  .mpv-pre{background:var(--precol);width:var(--tickwpre);height:var(--tickhpre);
    transform:translate(-50%,50%) translateX(var(--tickxpre))}
  .mpv-proj{background:var(--projcol);box-shadow:var(--projsh);width:var(--tickwproj);height:var(--tickhproj);
    transform:translate(-50%,50%) translateX(var(--tickxproj));
    transition:bottom var(--tickdur) var(--tickease) var(--tickdelay)}
  .mpv-proj.mpv-up{box-shadow:var(--projshup)}
  .mpv-proj.mpv-down{box-shadow:var(--projshdn)}

  /* ---- Captions. FIXED-ANCHOR, DIGIT-COUNT-INDEPENDENT (bug fix -- verified analytically +
     numerically, mirrors eff_bar_tuner_vertical.html's shipped fix for the SAME class of defect).
     A shrink-wrapped box centred via left:50%+translateX(-50%) keeps the NUMERAL's own centroid
     fixed, but any child glued to the numeral's growing edge (its icon) still drifts in ABSOLUTE
     terms by half of any digit-count width change -- self-centering never gives ANY child a truly
     fixed screen position, because BOTH of the box's edges move as content width changes. The one
     shared clearance origin (trackCentre +/- tickW/2, see the anchor comment above) fixes this: ALL
     THREE captions now share ONE fixed right edge -- right:100%+left:auto (promoted onto the shared
     .mpv-cap rule) -- pinned to the track's own left edge, clear of the tick's outer-edge overhang
     via the shared padding-right:var(--gapp) (the same term capP already used). Numeral-then-icon
     DOM order (see item 2) means the ICON is always the LAST in-flow child, so it sits flush
     against that fixed edge and is now PROVABLY invariant to digit count -- verified 913 / 2,913 /
     12,913 all land the icon's right edge at the exact same computed line. Only the numeral (and,
     on capC, the delta hanging off ITS left edge) is free to grow/shrink LEFTWARD, away from the
     fixed anchor -- exactly like capP already did, and like the numeral-side content in the
     shipped sibling's fixed r4/current captions. */
  .mpv-cap{position:absolute;display:flex;flex-direction:row;align-items:center;white-space:nowrap;
    z-index:3;right:100%;left:auto}
  /* GAP DIRECTION IS NOT SYMMETRIC IN GAMEFACE (gameface-drops-margin-on-the-anchored-side):
     `bottom:100%`+margin-bottom and `right:100%`+margin-right are IGNORED on an absolutely
     positioned box -- padding on THOSE two sides instead. `top:100%`+margin-top works as written. */
  /* capxR/capxC/capxP: residual X nudges off the shared right-anchor, defaulted to 0 (trim only --
     see the anchor comment above; a non-zero default here would mean the anchor itself is wrong). */
  .mpv-capR{bottom:100%;padding-bottom:var(--gapr);padding-right:var(--gapp);
    transform:translateX(var(--capxr));font-size:var(--rfs);line-height:var(--rlh)}
  /* capC (bottom, STATIC) now carries projAvg + the delta -- no bottom-tracking, so no transition
     is declared on it (it never had a moving `bottom` to animate; that was a leftover). */
  .mpv-capC{top:100%;margin-top:var(--gapc);padding-right:var(--gapp);
    transform:translateX(var(--capxc));font-size:var(--cfs);line-height:var(--clh)}
  /* capP (left, MOVING) now tracks the .mpv-pre tick and shows preAvg. The pre tick itself never
     animates within one replay (matches the horizontal bar's own .mp-tick.mp-pre / .mp-cap.up),
     so capP's `bottom` is set once per apply() alongside it -- no transition needed here either. */
  .mpv-capP{padding-right:var(--gapp);transform:translateY(50%) translateX(var(--capxp));
    font-size:var(--pfs);line-height:var(--plh)}
  /* Icon now follows its numeral (DOM order flipped) -- the gap moves to the icon's LEFT. */
  .mpv-cap .mpv-ico{margin-left:var(--icogap)}
  .mpv-cap .mpv-v,.mpv-cap .mpv-eta,.mpv-cap .mpv-d{color:#ffffff;font-weight:var(--wt);letter-spacing:var(--ls);text-shadow:var(--textsh)}
  /* Text sign = a coloured GLOW, never a fill (shipped .mb-up/.mb-down convention). */
  .mpv-v.mpv-up,.mpv-d-num.mpv-up,.mpv-eta.mpv-up{text-shadow:var(--textsh),0 0 var(--dgw) var(--upc),0 0 var(--dgt) var(--upc)}
  .mpv-v.mpv-down,.mpv-d-num.mpv-down,.mpv-eta.mpv-down{text-shadow:var(--textsh),0 0 var(--dgw) var(--dnc),0 0 var(--dgt) var(--dnc)}
  /* Delta is an IN-FLOW flex child now, ordered FIRST (delta, numeral, icon) -- not an out-of-flow
     box hanging off a content-dependent edge (that was the digit-count bug's exact mechanism: a
     percentage anchored to a box whose own width/position depends on content). margin-right is an
     ORDINARY in-flow flex gap, not subject to the anchored-side margin drop (that trap only bites
     a margin on the SAME side as an element's OWN absolute-positioning inset -- this element has
     none). Digit count can still move it TOGETHER with the numeral it modifies (expected -- it is
     semantically attached to the numeral), but it can never again disturb the icon, which stays
     flush against the shared fixed anchor regardless of what grows on this side of the row. */
  .mpv-cap .mpv-d{margin-right:var(--dgap);font-size:var(--dfs);transform:translateY(var(--dy));line-height:var(--dlh);opacity:0;transition:opacity var(--dfadms) var(--dfadease)}
  .mpv-ico.none{display:none}

  /* ---- Icon glyphs. Identical split/derivation to the horizontal tuner (GLYPH ::after, GLOW
     ::before z-index:-1, derived background-size off the MEASURED alpha>32 bbox). The per-role Y
     nudge (icoYP/icoYC/icoYR) is a font-BASELINE correction within a horizontal row and is
     UNCHANGED by the bar's overall orientation -- see gen_bar_tuner.ps1's note. */
  .mpv-ico{position:relative;display:block;flex:none;width:var(--icobox);height:var(--icobox);transform:translate(0,0)}
  .mpv-capP .mpv-ico{transform:translate(0,var(--icoyp))}
  .mpv-capC .mpv-ico{transform:translate(0,var(--icoyc))}
  .mpv-capR .mpv-ico{transform:translate(0,var(--icoyr))}
  /* Numeral baseline Y nudge is PER CAPTION GROUP now -- never merge these three. */
  .mpv-capR .mpv-v,.mpv-capR .mpv-eta{transform:translateY(var(--numyr))}
  .mpv-capC .mpv-v{transform:translateY(var(--numyc))}
  .mpv-capP .mpv-v{transform:translateY(var(--numyp))}
  .mpv-ico::before{content:"";position:absolute;left:50%;top:50%;z-index:-1;
    width:106%;height:106%;transform:translate(-50%,-50%);
    background:radial-gradient(circle at 50% 50%,var(--icoglow) 0%,transparent 73%)}
  .mpv-capR .mpv-ico::before{background:radial-gradient(circle at 50% 50%,var(--reqglow) 0%,transparent 73%)}
  .mpv-ico::after{content:"";position:absolute;left:0;top:0;width:100%;height:100%;
    background-repeat:no-repeat;background-position:center}
  .mpv-ico.dmgp{width:var(--dmgpbox);height:var(--dmgpbox)}
  .mpv-ico.dmgc{width:var(--dmgcbox);height:var(--dmgcbox)}
  .mpv-ico.dmgp::after{background-image:var(--dmgpimg);background-size:var(--dmgpsz);filter:brightness(3)}
  .mpv-ico.dmgc::after{background-image:var(--dmgcimg);background-size:var(--dmgcsz);filter:brightness(3)}
  .mpv-ico.moe{width:var(--markbox);height:var(--markbox)}
  .mpv-ico.moe::after{background-image:var(--moeimg);background-size:var(--moesz);filter:brightness(3)}
  .mpv-ico.mk{width:var(--markbox);height:var(--markbox)}
  .mpv-ico.mk::after{background-size:contain}
  .mpv-ico.mk1::after{background-image:url(data:image/png;base64,__ICO_MK1__)}
  .mpv-ico.mk2::after{background-image:url(data:image/png;base64,__ICO_MK2__)}
  .mpv-ico.mk3::after{background-image:url(data:image/png;base64,__ICO_MK3__)}
  /* etaGap is now the gap BETWEEN the two numeral+icon pairs (mark-icon -> eta-numeral), so it
     lives on the eta numeral's margin-left; the battles icon keeps the plain uniform icoGap. */
  .mpv-capR .mpv-eta{margin-left:var(--etagap)}
  .mpv-ico.battles::before{background:radial-gradient(circle at 50% 50%,var(--icoglow) 0%,transparent 73%)}
  .mpv-ico.battles::after{background-image:var(--battlesimg);background-size:var(--battlessz);filter:brightness(3)}

  #moe-bar-root.mpv-full .mpv-track,#moe-bar-root.mpv-full .mpv-fill,#moe-bar-root.mpv-full .mpv-tick{box-shadow:0 0 var(--glowb) var(--glowc)}
  #moe-bar-root.mpv-full .mpv-fill{background:var(--fullfill)}
  #moe-bar-root.mpv-full .mpv-v{text-shadow:var(--textsh),0 0 var(--glowb) var(--glowc),0 0 var(--glowb2) var(--glowc)}

  /* ================= panel (unchanged chrome from the horizontal tuner) ================= */
  .panel{width:380px;flex:none;background:var(--panel);border-left:1px solid var(--line);padding:18px 18px 60px;overflow:auto;height:100vh;position:sticky;top:0}
  .panel h1{font-size:16px;margin:0 0 4px;font-weight:800}
  .seg{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
  .seg button{flex:1;background:#14151a;border:1px solid var(--line);color:var(--ink);padding:6px 4px;border-radius:6px;font-size:11.5px;cursor:pointer}
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
</style>

<div class="stagewrap"><div class="stage" id="stage">
  <div id="mmMock"></div>
  <div class="mpv-anchor" id="mpv-anchor"><div id="moe-bar-root" class="mpv-hold">
    <div class="mpv-backdrop"></div>
    <div class="mpv-bd mpv-bd-1"></div><div class="mpv-bd mpv-bd-2"></div><div class="mpv-bd mpv-bd-3"></div><div class="mpv-bd mpv-bd-4"></div>
    <div class="mpv-track">
      <div class="mpv-fill"></div>
      <div class="mpv-tick mpv-end mpv-bottom"></div>
      <div class="mpv-tick mpv-pre"></div>
      <div class="mpv-tick mpv-proj"></div>
      <div class="mpv-tick mpv-end mpv-top"></div>
      <div class="mpv-cap mpv-capP"><span class="mpv-v">2,905</span><i class="mpv-ico dmgp"></i></div>
    </div>
    <div class="mpv-cap mpv-capR"><span class="mpv-v">3,050</span><i class="mpv-ico mk mk2"></i><span class="mpv-eta">18</span><i class="mpv-ico battles"></i></div>
    <div class="mpv-cap mpv-capC"><span class="mpv-d">(<span class="mpv-d-num">+8</span>)</span><span class="mpv-v">2,913</span><i class="mpv-ico dmgc"></i></div>
  </div></div>
</div></div>

<div class="panel">
  <h1>In-battle MoE progress bar (VERTICAL) &mdash; tuner</h1>
  <input type="file" id="shot" accept="image/*">
  <div class="seg" id="axisSeg">
    <button data-a="mark" class="on">prev&rarr;next mark</button><button data-a="zero">0&rarr;next</button><button data-a="win">windowed</button>
  </div>
  <div class="row2">
    <label><input type="checkbox" id="cHold" checked> hold visible</label>
    <label><input type="checkbox" id="cBounds"> bounds</label>
    <label><input type="checkbox" id="cBd" checked> backdrop</label>
    <label><input type="checkbox" id="cDash" checked> track dashes</label>
    <label><input type="checkbox" id="cBdr" checked> track border</label>
  </div>
  <div class="seg"><button id="bReplay">Replay</button><button id="bTick">Damage tick</button><button id="bFull">Fulfil</button></div>
  <div class="axisout" id="axisOut"></div>
  <div id="controls"></div>
  <div class="out" id="out"></div>
  <button class="copy" id="copyBtn">Copy CSS</button>
  <p class="note">Minimap-relative placement is <b>preview only</b> -- it never reaches the emitted CSS (in-game the window is positioned from Python). Icons/backdrop/font are <b>base64-inlined</b> for the browser; the emitted CSS carries the real <code>img://</code> urls.</p>
</div>

<script>
  // ---- minimap-relative placement (PREVIEW ONLY -- see the header) --------------------------
  // Measured logical-px size per index, invariant across resolution AND interface scale -- see
  // tools/dev/measure_minimap.py:44-47 ("[228, 279, 329, 409, 510, 628]").
  var MM_SIZES=[228,279,329,409,510,628];
  function mmSize(){return MM_SIZES[st.mmIdx];}
  // ONE shared clearance origin: the tick's OUTER edge (half its cross-length past the track's own
  // edge -- ticks are wider than the track). Used on BOTH the minimap gap and the left-caption gap.
  // "If more than one tick cross-length exists, use the largest" -- now THREE independent
  // per-type cross-lengths exist (tickWEnd/tickWPre/tickWProj), so the overhang is derived off
  // whichever of the three is widest at the moment, never a stale single shared knob.
  function halfOverhang(){return Math.max(0,Math.max(st.tickWEnd,st.tickWPre,st.tickWProj)-st.trackW)/2;}
  // barRight/barBottom are logical-px COORDINATES on the simulated stageW x stageH screen (distance
  // from the screen's top-left): the bar's TICK's outer right edge sits `mmGap` px left of the
  // minimap's left edge (so the track's own right edge sits `mmGap+halfOverhang` left of it), and
  // its bottom edge sits `mmGapBottom` px clear of the screen's bottom (== the minimap's bottom,
  // since the minimap has zero inset).
  function barRightPx(){return st.stageW-mmSize()-st.mmGap-halfOverhang();}
  function barBottomPx(){return st.stageH-st.mmGapBottom;}
  // DISPLAY_W: the stage box's own on-screen width in browser px, fixed like the horizontal
  // tuner's 1600x900 -- pxrem (px per logical rem) is DERIVED from it so 1rem stays EXACTLY 1
  // logical px on the simulated stageW x stageH screen (never a second, independently-tunable
  // knob that could disagree with the placement math it is meant to render).
  var DISPLAY_W=1600;
  // Clamp .mpv-capP's tracked bottom% into a window that keeps its OWN box clear of capR/capC by
  // at least `capPClear` rem (logical px) at either axis extreme -- the vertical analogue of the
  // horizontal tuner's %-of-axis clamp (tools/dev/README.md:405-411): there a caption could only
  // collide with the OTHER moving caption anywhere along the axis; here capP only ever collides
  // with the two STATIC captions, and only at the two ends, so the clamp corridor is derived
  // straight from the axis length (barH) rather than from a live de-collision pass.
  function clampCapPPct(p){
    if(st.barH<=0)return p;
    var clr=Math.min(50,st.capPClear/st.barH*100);
    return Math.max(clr,Math.min(100-clr,p));
  }

  var CKURI="data:image/png;base64,__CK__", CKTILE=4;
  var THR={0:0,1:2450,2:3050,3:3620,100:4400};
  var DGA=0.9;
  var DMG={damage:{u:"data:image/png;base64,__ICO_DMG__",bb:0.219},
           barrel_mark:{u:"data:image/png;base64,__ICO_BM__",bb:0.328}};
  var MOEURI="data:image/png;base64,__ICO_TOP__", MOEBB=0.273;
  var BATTLESURI="data:image/png;base64,__ICO_BATTLES__", BATTLESBB=0.226563;
  var IMGDIR="img://gui/maps/icons/", QT="personal_missions_30/quest_type/128x128/";
  var IMG={damage:IMGDIR+QT+"icon_battle_condition_damage.png",
           barrel_mark:IMGDIR+QT+"icon_battle_condition_barrel_mark.png",
           top:IMGDIR+QT+"icon_battle_condition_top.png",
           battles:IMGDIR+QT+"icon_battle_condition_battles.png",
           mk:[IMGDIR+"library/marksOnGun/mark_1.png",IMGDIR+"library/marksOnGun/mark_2.png",IMGDIR+"library/marksOnGun/mark_3.png"]};
  function rem(v){return (v*st.pxrem).toFixed(2)+"px";}
  function REM(v){return v+"rem";}
  // THE "LARGE" SIZE MODE's extra x-factor == MoEBarTransient.js's SIZE_XF (4/3). The root font
  // already delivers SIZE_F (1.25) to EVERY rem, so an x-length owes this factor ALONE to reach
  // 5/3 total -- pure SIZE_XF, never SIZE_F (verified against all nine shipped .mp-lg values:
  // 200->266.667, -80->-106.667, 360->480, 2->2.667, 1->1.333, 4->5.333, 3->4, 0.35->0.467,
  // 4.2->5.6). 3dp with trailing zeros trimmed, the shipped block's own precision.
  // ON THIS BAR THE AXES ARE SWAPPED, so "x-length" now names the CROSS axis: track thickness,
  // tick cross-spans, backdrop left/width, caption padding-right/translateX, the icon and delta
  // gaps. The bar's LENGTH, the tick thicknesses, every font/line-height, the vertical caption
  // gaps AND the dash grid (0deg == a y-period here, unlike the horizontal bar's 90deg) are
  // y/uniform lengths the root font already scales -- they must NOT be restated.
  function X43(v){return +(v*4/3).toFixed(3);}
  function lh(fs){return Math.ceil(fs*2*1.2565)/2;}
  function fmt(n){return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g,",");}
  function hexA(hex,a){var n=parseInt(hex.slice(1),16);return "rgba("+((n>>16)&255)+","+((n>>8)&255)+","+(n&255)+","+a+")";}

  var SCHEMA=[
    ["Layout",[
      {id:"barH",label:"Bar length (rem, the vertical axis)",min:80,max:800,step:5,val:200},
      {id:"trackW",label:"Track thickness (rem) - shipped horizontal cross-axis = 3",min:1,max:30,step:0.5,val:3},
      {id:"tickWEnd",label:"End ticks (top/bottom) span across the track, cross-axis (rem)",min:1,max:20,step:0.5,val:9},
      {id:"tickWPre",label:"Pre tick span across the track, cross-axis (rem)",min:1,max:20,step:0.5,val:9},
      {id:"tickWProj",label:"Proj tick span across the track, cross-axis (rem)",min:1,max:20,step:0.5,val:9},
      {id:"tickHEnd",label:"End ticks (top/bottom) thickness along the axis (rem)",min:0.5,max:20,step:0.5,val:2},
      {id:"tickHPre",label:"Pre tick thickness along the axis (rem)",min:0.5,max:20,step:0.5,val:2},
      {id:"tickHProj",label:"Proj tick thickness along the axis (rem)",min:0.5,max:20,step:0.5,val:2},
      {id:"tickXEnd",label:"End ticks (top/bottom) cross-axis (X) nudge (rem)",min:-20,max:20,step:0.5,val:0},
      {id:"tickXPre",label:"Pre tick cross-axis (X) nudge (rem)",min:-20,max:20,step:0.5,val:0},
      {id:"tickXProj",label:"Proj tick cross-axis (X) nudge (rem)",min:-20,max:20,step:0.5,val:0},
      {id:"gapR",label:"Track TOP -> capR gap (rem, padding)",min:0,max:40,step:0.5,val:6},
      {id:"gapC",label:"Track BOTTOM -> capC gap (rem, margin)",min:0,max:40,step:0.5,val:6},
      {id:"gapP",label:"Track LEFT -> capP gap (rem, padding)",min:0,max:40,step:0.5,val:3},
      {id:"capPClear",label:"capP min clearance from either end (rem)",min:0,max:60,step:0.5,val:10},
      {id:"capxR",label:"capR residual X nudge off the shared right-anchor (rem) - per-group geometry, tuned",min:-40,max:40,step:0.5,val:14},
      {id:"capxC",label:"capC residual X nudge off the shared right-anchor (rem) - per-group geometry, tuned",min:-40,max:40,step:0.5,val:16},
      {id:"capxP",label:"capP residual X nudge off the shared right-anchor (rem) - beside the tick, stays 0",min:-40,max:40,step:0.5,val:0}]],
    ["Minimap-relative placement (preview only -- never emitted)",[
      {id:"stageW",label:"Simulated screen width (logical px)",min:640,max:7680,step:10,val:1920},
      {id:"stageH",label:"Simulated screen height (logical px)",min:360,max:4320,step:10,val:1080},
      {id:"mmIdx",label:"Minimap size index (0-5, measure_minimap.py table)",min:0,max:5,step:1,val:0},
      {id:"mmGap",label:"Bar -> minimap clearance (logical px)",min:0,max:60,step:1,val:8},
      {id:"mmGapBottom",label:"Bar -> screen bottom clearance (logical px)",min:0,max:60,step:1,val:30}]],
    ["Type",[
      {id:"rFS",label:"capR font size (rem)",min:8,max:35,step:1,val:14},
      {id:"cFS",label:"capC font size (rem)",min:8,max:35,step:1,val:16},
      {id:"pFS",label:"capP font size (rem)",min:8,max:35,step:1,val:14},
      {id:"dFS",label:"Delta (+N) size (rem)",min:6,max:35,step:1,val:12},
      {id:"dGap",label:"Numeral -> delta gap (em of the delta's OWN size)",min:0,max:2,step:0.05,val:0.35},
      {id:"dY",label:"Delta Y nudge (rem)",min:-6,max:6,step:0.25,val:1.5},
      {id:"wt",label:"Weight",min:300,max:700,step:100,val:600},
      {id:"ls",label:"Letter-spacing (em)",min:-0.1,max:0.2,step:0.005,val:0},
      {id:"shBlur",label:"Text-shadow blur (rem)",min:0,max:30,step:0.5,val:1},
      {id:"shAlpha",label:"Text-shadow alpha",min:0,max:1,step:0.01,val:0.5},
      {id:"shColor",label:"Text-shadow colour",color:true,val:"#000000"}]],
    ["Colour",[
      {id:"trackCol",label:"Track colour",color:true,val:"#000000"},
      {id:"trackA",label:"Track alpha",min:0,max:1,step:0.01,val:0.45},
      {id:"dashW",label:"Dash MARK width (rem) - garage art = 2",min:0.5,max:20,step:0.5,val:2},
      {id:"dashGap",label:"Dash GAP width (rem) - garage art = 1",min:0.5,max:20,step:0.5,val:1},
      {id:"dashCol",label:"Dash MARK colour (garage cream)",color:true,val:"#ece6da"},
      {id:"dashA",label:"Dash MARK alpha - garage art = 41/255",min:0,max:1,step:0.01,val:0.16},
      {id:"gapCol",label:"Dash GAP colour (garage dark) - paints OVER the fill",color:true,val:"#0d0e10"},
      {id:"gapA",label:"Dash GAP alpha - 1 = fill masked to the marks (garage look), 0 = old",min:0,max:1,step:0.01,val:0.5},
      {id:"bdrW",label:"Border width (rem) - garage = 1",min:0,max:8,step:0.5,val:1},
      {id:"bdrCol",label:"Border colour (garage near-black)",color:true,val:"#0d0e10"},
      {id:"bdrA",label:"Border alpha - garage = 0.5",min:0,max:1,step:0.01,val:0.5},
      {id:"fillCol",label:"Fill colour (NEUTRAL - keep it off upCol/dnCol)",color:true,val:"#ede6d9"},
      {id:"fillA",label:"Fill alpha",min:0,max:1,step:0.01,val:0.8},
      {id:"endCol",label:"End tick colour (axis stops)",color:true,val:"#ede6d9"},
      {id:"endA",label:"End tick alpha",min:0,max:1,step:0.01,val:0.8},
      {id:"preCol",label:"Pre tick colour",color:true,val:"#ede6d9"},
      {id:"preA",label:"Pre tick alpha",min:0,max:1,step:0.01,val:0.75},
      {id:"projCol",label:"Proj tick colour",color:true,val:"#ffffff"},
      {id:"projA",label:"Proj tick alpha",min:0,max:1,step:0.01,val:1},
      {id:"projGlowCol",label:"Proj tick glow colour (NEUTRAL)",color:true,val:"#ffffff"},
      {id:"projGlowA",label:"Proj tick glow alpha",min:0,max:1,step:0.01,val:0.5},
      {id:"projGlowB",label:"Proj tick glow radius (rem)",min:0,max:40,step:0.5,val:6},
      {id:"projGlowB2",label:"Proj tick glow tight core (rem)",min:0,max:20,step:0.5,val:2},
      {id:"glowCol",label:"Glow colour (icon gold)",color:true,val:"#ffcd5a"},
      {id:"glowA",label:"Glow alpha",min:0,max:1,step:0.01,val:0.5},
      {id:"glowB",label:"Glow radius (rem)",min:0,max:60,step:0.5,val:8},
      {id:"glowB2",label:"Glow tight core (rem)",min:0,max:30,step:0.5,val:2},
      {id:"fullFillA",label:"MET-state gold FILL alpha",min:0,max:1,step:0.01,val:0.8},
      {id:"upCol",label:"Delta + glow (shipped .mb-up green)",color:true,val:"#7bec37"},
      {id:"dnCol",label:"Delta - glow (shipped .mb-down red)",color:true,val:"#d3443f"},
      {id:"dGlowW",label:"Delta glow WIDE pass (rem)",min:0,max:30,step:0.5,val:6},
      {id:"dGlowT",label:"Delta glow TIGHT core (rem)",min:0,max:30,step:0.5,val:1}]],
    ["Icons",[
      {id:"icoBox",label:"Base .mpv-ico box (rem)",min:6,max:40,step:1,val:13},
      {id:"dmgPBox",label:"capP damage icon box (rem)",min:6,max:40,step:1,val:14},
      {id:"dmgCBox",label:"capC damage icon box (rem)",min:6,max:40,step:1,val:16},
      {id:"icoFill",label:"Icon target fill (glyph / box)",min:0.2,max:1,step:0.01,val:0.75},
      {id:"markBox",label:"Mark icon box (rem) - 24px art, blurs above ~24",min:6,max:40,step:1,val:17},
      {id:"icoGap",label:"Numeral -> icon gap (rem, icon is RIGHT)",min:0,max:20,step:0.5,val:1},
      {id:"etaGap",label:"Mark icon -> eta numeral gap (rem)",min:0,max:20,step:0.5,val:4},
      {id:"icoGlowCol",label:"capP/capC damage icon glow colour",color:true,val:"#ffcd5a"},
      {id:"icoGlowA",label:"capP/capC damage icon glow alpha (0 = off)",min:0,max:1,step:0.01,val:0.5},
      {id:"reqGlowCol",label:"capR mark icon glow colour",color:true,val:"#1a1a1a"},
      {id:"reqGlowA",label:"capR mark icon glow alpha (0 = off)",min:0,max:1,step:0.01,val:0.5},
      {id:"dmgPIco",label:"capP glyph",opts:["damage","barrel_mark"],val:"barrel_mark"},
      {id:"dmgCIco",label:"capC glyph",opts:["damage","barrel_mark"],val:"damage"},
      {id:"icoYP",label:"capP icon Y offset (rem, signed)",min:-20,max:20,step:0.1,val:0},
      {id:"icoYC",label:"capC icon Y offset (rem, signed)",min:-20,max:20,step:0.1,val:1},
      {id:"icoYR",label:"capR icon Y offset (rem, signed)",min:-20,max:20,step:0.1,val:0.5},
      {id:"numYR",label:"capR numeral baseline Y nudge (rem)",min:-4,max:4,step:0.1,val:-0.5},
      {id:"numYC",label:"capC numeral baseline Y nudge (rem)",min:-4,max:4,step:0.1,val:-0.5},
      {id:"numYP",label:"capP numeral baseline Y nudge (rem)",min:-4,max:4,step:0.1,val:-0.5}]],
    ["Backdrop",[
      {id:"bdBleedY",label:"Vertical bleed past the bar's ends (rem)",min:0,max:200,step:1,val:80},
      {id:"bdLeft",label:"Left (rem, negative = wider than the track)",min:-120,max:40,step:0.5,val:-34},
      {id:"bdW",label:"Width (rem, EXPLICIT)",min:10,max:200,step:1,val:46},
      // PER-ROW STRIPS (.mpv-bd, mimicking the corner overlay's .mb-bd-N). Left/width are NOT
      // free -- they MIRROR the invisible SURFACE the JS pushes (body.mpv #moe-bar-box == 112rem
      // wide, its left edge at -(V_PAD_X_REM - V_BOX_LEFT_REM) == -104 root-rem), so every strip's
      // minimap-facing (right) edge lands flush on the surface's own right edge (root x 8 Default /
      // 10 Large) with zero gap. The Large twins are their OWN literals (the surface's Large left
      // is -(padX - boxLeft*SIZE_XF), which is not a clean *4/3 of the Default). Change the JS
      // surface (V_BOX_*/V_PAD_*) and these must move with it. Tops are per-row seeds the maintainer
      // converges in-client.
      {id:"bdStripLeft",label:"Strip left == surface left (rem)",min:-160,max:0,step:0.001,val:-104},
      {id:"bdStripW",label:"Strip width == surface width (rem)",min:10,max:200,step:0.001,val:115},
      {id:"bdStripLeftLg",label:"Strip left, Large (rem)",min:-200,max:0,step:0.001,val:-115.333},
      {id:"bdStripWLg",label:"Strip width, Large (rem)",min:10,max:220,step:0.001,val:127.2},
      {id:"bdStripH",label:"Strip height, shared (rem)",min:6,max:120,step:1,val:30},
      {id:"bd1T",label:"Strip 1 top (eta row, rem)",min:-160,max:240,step:0.5,val:-54},
      {id:"bd2T",label:"Strip 2 top (req row, rem)",min:-160,max:240,step:0.5,val:-30},
      {id:"bd3T",label:"Strip 3 top (proj row, rem)",min:-160,max:240,step:0.5,val:85},
      {id:"bd4T",label:"Strip 4 top (current row, rem)",min:-160,max:240,step:0.5,val:201},
      {id:"dotAlpha",label:"Dither strength (opacity)",min:0,max:1,step:0.01,val:0.1},
      {id:"dotRX",label:"Dither fade size X (%)",min:0,max:250,step:1,val:112},
      {id:"dotRY",label:"Dither fade size Y (%)",min:0,max:250,step:1,val:110},
      {id:"dotIn",label:"Dither solid to (%)",min:0,max:100,step:1,val:0},
      {id:"dotOut",label:"Dither gone by (%)",min:0,max:120,step:1,val:67},
      {id:"dotAX",label:"Dither solid CORE x (%) - 100 = minimap edge, 0 = numerals",min:0,max:100,step:1,val:90},
      {id:"ugAX",label:"Radial underlay core x (%)",min:0,max:100,step:1,val:90},
      {id:"ugRX",label:"Radial size X (%)",min:0,max:250,step:1,val:152},
      {id:"ugRY",label:"Radial size Y (%)",min:0,max:250,step:1,val:57},
      {id:"ug1a",label:"Radial inner alpha",min:0,max:1,step:0.01,val:0.35},
      {id:"ug1p",label:"Radial inner pos (%)",min:0,max:100,step:1,val:0},
      {id:"ug2a",label:"Radial outer alpha",min:0,max:1,step:0.01,val:0},
      {id:"ug2p",label:"Radial outer pos (%)",min:0,max:100,step:1,val:70}]],
    ["Animation",[
      {id:"fadeIn",label:"Fade-in (ms)",min:0,max:3000,step:50,val:600},
      {id:"hold",label:"Hold (ms)",min:0,max:12000,step:100,val:5000},
      {id:"fadeOut",label:"Fade-out (ms)",min:0,max:3000,step:50,val:600},
      {id:"slide",label:"Slide distance (rem, signed FLOAT)",min:-85,max:85,step:0.1,val:20},
      {id:"fadeEase",label:"Slide/fade-IN easing",opts:["ease-in","ease-out","ease-in-out","ease","linear","cubic-bezier(.2,.8,.2,1)"],val:"ease-in"},
      {id:"outEase",label:"Slide/fade-OUT easing",opts:["ease-in","ease-out","ease-in-out","ease","linear","cubic-bezier(.2,.8,.2,1)"],val:"ease-in"},
      {id:"tickDelay",label:"Tick-move delay (ms)",min:0,max:4000,step:50,val:600},
      {id:"tickDur",label:"Tick-move duration (ms)",min:0,max:4000,step:50,val:600},
      {id:"tickEase",label:"Tick-move easing",opts:["ease-in","ease-out","ease-in-out","ease","linear","cubic-bezier(.2,.8,.2,1)"],val:"cubic-bezier(.2,.8,.2,1)"},
      {id:"dFadeMs",label:"Delta (+N) fade-in duration (ms)",min:0,max:2000,step:50,val:600},
      {id:"dFadeEase",label:"Delta (+N) fade-in easing",opts:["ease-in","ease-out","ease-in-out","ease","linear","cubic-bezier(.2,.8,.2,1)"],val:"cubic-bezier(.2,.8,.2,1)"}]],
    ["Mock data (BattleSnapshot shape)",[
      {id:"marks",label:"Marks held (0-3) - resets the two thresholds",min:0,max:3,step:1,val:1},
      {id:"thrPrev",label:"thresholds[m] - axis bottom end",min:0,max:6000,step:10,val:2450},
      {id:"thrNext",label:"thresholds[m+1] - requirement",min:100,max:6000,step:10,val:3050},
      {id:"preAvg",label:"pre_avg (career moving average, capC)",min:0,max:6000,step:1,val:2905},
      {id:"projAvg",label:"proj_avg (after this battle, capP + the proj tick)",min:0,max:6000,step:1,val:2913},
      {id:"winN",label:"Windowed mode: +/- N damage",min:5,max:600,step:5,val:60}]]
  ];

  var st={}, axis="mark", UI={};
  SCHEMA.forEach(function(sec){sec[1].forEach(function(c){st[c.id]=c.val;});});
  st.holdVis=true; st.bounds=false; st.bd=true; st.dashOn=true; st.bdrOn=true;

  var anchor=document.getElementById("mpv-anchor"),
      root=document.getElementById("moe-bar-root"),
      fill=root.querySelector(".mpv-fill"),
      tPre=root.querySelector(".mpv-pre"), tProj=root.querySelector(".mpv-proj"),
      capP=root.querySelector(".mpv-capP"),
      capC=root.querySelector(".mpv-capC"), capR=root.querySelector(".mpv-capR"),
      bd=root.querySelector(".mpv-backdrop"), mm=document.getElementById("mmMock"),
      stageEl=document.getElementById("stage"),
      dyn=document.createElement("style");
  document.head.appendChild(dyn);
  var capDN=capC.querySelector(".mpv-d-num");
  function capV(c){return c.querySelector(".mpv-v");}
  function capI(c){return c.querySelector(".mpv-ico");}
  function setIco(c,k){var i=capI(c);
    i.className="mpv-ico"+(k===0?" none":k===4?" moe":" mk mk"+k);}

  function bounds(){
    if(axis==="zero") return [0,st.thrNext];
    if(axis==="win")  return [st.projAvg-st.winN,st.projAvg+st.winN];
    return [st.marks>0?st.thrPrev:0,st.thrNext];
  }
  function pct(v){var b=bounds(),w=b[1]-b[0];if(w<=0)return 0;return Math.max(0,Math.min(1,(v-b[0])/w))*100;}
  function met(){return st.projAvg>=st.thrNext;}

  function trackBg(){return hexA(st.trackCol,st.trackA);}
  function fillBg(){return hexA(st.fillCol,st.fillA);}
  function dashBg(u){if(!st.dashOn)return "none";var c=hexA(st.dashCol,st.dashA),
      g=st.gapA>0?hexA(st.gapCol,st.gapA):"transparent";
    return "repeating-linear-gradient(0deg,"+c+" "+u(0)+","+c+" "+u(st.dashW)+","+g+" "+u(st.dashW)+
      ","+g+" "+u(st.dashW+st.dashGap)+")";}
  function bdrSh(u){return st.bdrOn?"0 0 0 "+u(st.bdrW)+" "+hexA(st.bdrCol,st.bdrA):"none";}
  function projSh(u,c){c=c||hexA(st.projGlowCol,st.projGlowA);
    return "0 0 "+u(st.projGlowB)+" "+c+",0 0 "+u(st.projGlowB2)+" "+c;}
  function dotMask(){return "radial-gradient("+st.dotRX+"% "+st.dotRY+"% at "+st.dotAX+"% 50%,#000 "+st.dotIn+"%,transparent "+st.dotOut+"%)";}
  function ugGrad(){return "radial-gradient("+st.ugRX+"% "+st.ugRY+"% at "+st.ugAX+"% 50%,rgba(0,0,0,"+st.ug1a+") "+st.ug1p+"%,rgba(0,0,0,"+st.ug2a+") "+st.ug2p+"%)";}
  function textSh(){return "0px 0px "+rem(st.shBlur)+" "+hexA(st.shColor,st.shAlpha);}
  function total(){return st.fadeIn+st.hold+st.fadeOut;}
  function icoSz(bb){return (100/bb*st.icoFill).toFixed(1)+"%";}

  function setPos(v,anim){
    var p=pct(v).toFixed(3)+"%";
    fill.style.transition=anim?"":"none";tProj.style.transition=anim?"":"none";
    fill.style.height=p;tProj.style.bottom=p;
  }
  // capP now tracks the PRE tick, not the proj tick -- and like that tick it never animates
  // within one replay (preAvg is this battle's fixed starting point), so both are positioned
  // together, once per apply(), with no transition.
  function setPreTick(){
    var p=pct(st.preAvg).toFixed(3)+"%";
    tPre.style.bottom=p;
    capP.style.bottom=clampCapPPct(pct(st.preAvg)).toFixed(3)+"%";
  }

  // capC (static, below the track) shows proj_avg + the delta from pre_avg -- the shipped
  // horizontal convention (bottom-centre = proj_avg, and the ONLY caption that glows). capP
  // (tracks the moving pre tick) shows pre_avg and never glows, matching the pre tick itself.
  var capD=capC.querySelector(".mpv-d");
  function showVal(revealed){
    var d=st.projAvg-st.preAvg;
    capV(capC).textContent=fmt(st.projAvg);
    capV(capP).textContent=fmt(st.preAvg);
    capD.style.opacity=revealed?"1":"0";
    capDN.textContent=(d>0?"+":d<0?"-":"")+fmt(Math.abs(d));
    if(!revealed)return;
    var glows=Math.round(Math.abs(d))!==0;
    [capV(capC),capDN,fill,tProj].forEach(function(e){
      e.classList.toggle("mpv-up",glows&&d>0);e.classList.toggle("mpv-down",glows&&d<0);});
  }

  function apply(){
    if(st.marks!==st._marks){st._marks=st.marks;
      var nx=st.marks>=3?100:st.marks+1;
      set("thrPrev",THR[st.marks]);set("thrNext",THR[nx]);}
    // pxrem is DERIVED from the simulated stageW (see DISPLAY_W's note) -- never a second knob
    // that could disagree with the minimap placement math.
    st.pxrem=DISPLAY_W/st.stageW;
    document.documentElement.style.fontSize=st.pxrem+"px";
    stageEl.style.width=DISPLAY_W+"px";
    stageEl.style.height=(DISPLAY_W*st.stageH/st.stageW).toFixed(1)+"px";
    mm.style.width=rem(mmSize());mm.style.height=rem(mmSize());
    mm.textContent="MINIMAP idx"+st.mmIdx+" "+mmSize()+"px";
    var S=anchor.style, ovh=halfOverhang();
    S.setProperty("--anchorr",rem(mmSize()+st.mmGap+ovh));
    S.setProperty("--anchorb",rem(st.mmGapBottom));
    S.setProperty("--barh",rem(st.barH));S.setProperty("--trackw",rem(st.trackW));
    S.setProperty("--tickwend",rem(st.tickWEnd));S.setProperty("--tickhend",rem(st.tickHEnd));S.setProperty("--tickxend",rem(st.tickXEnd));
    S.setProperty("--tickwpre",rem(st.tickWPre));S.setProperty("--tickhpre",rem(st.tickHPre));S.setProperty("--tickxpre",rem(st.tickXPre));
    S.setProperty("--tickwproj",rem(st.tickWProj));S.setProperty("--tickhproj",rem(st.tickHProj));S.setProperty("--tickxproj",rem(st.tickXProj));
    S.setProperty("--gapr",rem(st.gapR));S.setProperty("--gapc",rem(st.gapC));S.setProperty("--gapp",rem(st.gapP+ovh));
    S.setProperty("--capxr",rem(st.capxR));S.setProperty("--capxc",rem(st.capxC));S.setProperty("--capxp",rem(st.capxP));
    S.setProperty("--rfs",rem(st.rFS));S.setProperty("--cfs",rem(st.cFS));S.setProperty("--pfs",rem(st.pFS));
    S.setProperty("--rlh",rem(lh(st.rFS)));S.setProperty("--clh",rem(lh(st.cFS)));S.setProperty("--plh",rem(lh(st.pFS)));
    S.setProperty("--wt",st.wt);S.setProperty("--ls",st.ls+"em");S.setProperty("--textsh",textSh());
    S.setProperty("--trackbg",trackBg());S.setProperty("--fillbg",fillBg());
    S.setProperty("--upfill",hexA(st.upCol,st.fillA));S.setProperty("--dnfill",hexA(st.dnCol,st.fillA));
    S.setProperty("--endcol",hexA(st.endCol,st.endA));
    S.setProperty("--precol",hexA(st.preCol,st.preA));S.setProperty("--projcol",hexA(st.projCol,st.projA));
    S.setProperty("--dashbg",dashBg(rem));S.setProperty("--bdrsh",bdrSh(rem));
    S.setProperty("--projsh",projSh(rem));
    S.setProperty("--projshup",projSh(rem,hexA(st.upCol,DGA)));
    S.setProperty("--projshdn",projSh(rem,hexA(st.dnCol,DGA)));
    S.setProperty("--icobox",rem(st.icoBox));S.setProperty("--markbox",rem(st.markBox));
    S.setProperty("--icogap",rem(st.icoGap));S.setProperty("--etagap",rem(st.etaGap));S.setProperty("--icoglow",hexA(st.icoGlowCol,st.icoGlowA));
    S.setProperty("--reqglow",hexA(st.reqGlowCol,st.reqGlowA));
    S.setProperty("--icoyp",rem(st.icoYP));S.setProperty("--icoyc",rem(st.icoYC));S.setProperty("--icoyr",rem(st.icoYR));
    S.setProperty("--numyr",rem(st.numYR));S.setProperty("--numyc",rem(st.numYC));S.setProperty("--numyp",rem(st.numYP));
    S.setProperty("--dfs",rem(st.dFS));S.setProperty("--dgap",st.dGap+"em");S.setProperty("--dy",rem(st.dY));
    S.setProperty("--dlh",rem(lh(st.dFS)));
    S.setProperty("--dmgpbox",rem(st.dmgPBox));S.setProperty("--dmgcbox",rem(st.dmgCBox));
    S.setProperty("--dmgpimg","url("+DMG[st.dmgPIco].u+")");S.setProperty("--dmgpsz",icoSz(DMG[st.dmgPIco].bb));
    S.setProperty("--dmgcimg","url("+DMG[st.dmgCIco].u+")");S.setProperty("--dmgcsz",icoSz(DMG[st.dmgCIco].bb));
    S.setProperty("--moeimg","url("+MOEURI+")");S.setProperty("--moesz",icoSz(MOEBB));
    S.setProperty("--battlesimg","url("+BATTLESURI+")");S.setProperty("--battlessz",icoSz(BATTLESBB));
    S.setProperty("--glowc",hexA(st.glowCol,st.glowA));S.setProperty("--glowb",rem(st.glowB));S.setProperty("--glowb2",rem(st.glowB2));
    S.setProperty("--fullfill",hexA(st.glowCol,st.fullFillA));
    S.setProperty("--upc",hexA(st.upCol,DGA));S.setProperty("--dnc",hexA(st.dnCol,DGA));
    S.setProperty("--dgw",rem(st.dGlowW));S.setProperty("--dgt",rem(st.dGlowT));
    S.setProperty("--tickdur",st.tickDur+"ms");S.setProperty("--tickdelay",st.tickDelay+"ms");S.setProperty("--tickease",st.tickEase);
    S.setProperty("--dfadms",st.dFadeMs+"ms");S.setProperty("--dfadease",st.dFadeEase);
    S.setProperty("--bdleft",rem(st.bdLeft));S.setProperty("--bdw",rem(st.bdW));
    S.setProperty("--bdtop",rem(-st.bdBleedY));S.setProperty("--bdh",rem(st.barH+2*st.bdBleedY));
    S.setProperty("--bdstripleft",rem(st.bdStripLeft));S.setProperty("--bdstripw",rem(st.bdStripW));
    S.setProperty("--bdstriph",rem(st.bdStripH));
    S.setProperty("--bd1top",rem(st.bd1T));S.setProperty("--bd2top",rem(st.bd2T));
    S.setProperty("--bd3top",rem(st.bd3T));S.setProperty("--bd4top",rem(st.bd4T));
    S.setProperty("--ckbg","url("+CKURI+")");
    S.setProperty("--cksize",(CKTILE*st.pxrem).toFixed(3)+"px "+(CKTILE*st.pxrem).toFixed(3)+"px");
    S.setProperty("--dotop",st.dotAlpha);S.setProperty("--dotmask",dotMask());S.setProperty("--uggrad",ugGrad());
    bd.style.display="none";
    root.querySelectorAll(".mpv-bd").forEach(function(e){e.style.display=st.bd?"block":"none";});
    root.style.outline=st.bounds?"1px dashed #ff5":"none";
    root.classList.toggle("mpv-full",met());
    var b=bounds();
    capV(capR).textContent=fmt(b[1]);
    setIco(capR,st.marks>=3?4:st.marks+1);
    showVal(true);
    setPreTick();
    if(!root.classList.contains("mpv-run"))setPos(st.projAvg,false);
    dyn.textContent=keyframes();
    var dp=pct(st.projAvg)-pct(st.preAvg);
    document.getElementById("axisOut").textContent=
      "axis "+fmt(b[0])+" -> "+fmt(b[1])+"   (span "+fmt(b[1]-b[0])+")\n"+
      "pre "+pct(st.preAvg).toFixed(2)+"%  ->  proj "+pct(st.projAvg).toFixed(2)+"%   (move "+dp.toFixed(2)+"% = "+
        (dp/100*st.barH).toFixed(1)+"rem)\n"+
      (met()?"requirement MET -> gold glow":"requirement not met")+"\n\n"+
      "-- minimap placement (preview only) --\n"+
      "stage "+st.stageW+"x"+st.stageH+" logical px, minimap idx "+st.mmIdx+" = "+mmSize()+"px\n"+
      "tick outer-edge overhang = (tickW-trackW)/2 = "+ovh.toFixed(2)+"rem\n"+
      "bar right = stageW-mmSize-mmGap-overhang = "+barRightPx()+"px\n"+
      "bar bottom = stageH-mmGapBottom = "+barBottomPx()+"px\n"+
      "bar box left = barRight-trackW = "+(barRightPx()-st.trackW).toFixed(1)+"px\n"+
      "bar box top  = barBottom-barH  = "+(barBottomPx()-st.barH).toFixed(1)+"px";
    document.getElementById("out").textContent=cssOut();
  }

  function slideStops(u){
    var s=st.slide;
    return ["translateY("+u(s)+")","translateY("+u(0)+")","translateY("+u(0)+")","translateY("+u(s)+")"];
  }
  function keyframes(){
    var t=total()||1,a=(st.fadeIn/t*100).toFixed(2),b=((st.fadeIn+st.hold)/t*100).toFixed(2),y=slideStops(rem);
    return "@keyframes mpv-life{"+
      "0%{opacity:0;transform:"+y[0]+";animation-timing-function:"+st.fadeEase+"}"+
      a+"%{opacity:1;transform:"+y[1]+";animation-timing-function:linear}"+
      b+"%{opacity:1;transform:"+y[2]+";animation-timing-function:"+st.outEase+"}"+
      "100%{opacity:0;transform:"+y[3]+"}}\n"+
      "#moe-bar-root.mpv-run{animation:mpv-life "+t+"ms both}\n";
  }

  function replay(){
    root.classList.remove("mpv-run","mpv-hold");void root.offsetWidth;
    setPos(st.preAvg,false);void root.offsetWidth;
    root.classList.add("mpv-run");
    requestAnimationFrame(function(){setPos(st.projAvg,true);});
  }
  root.addEventListener("animationend",function(e){
    if(e.animationName!=="mpv-life")return;
    root.classList.remove("mpv-run");
    if(st.holdVis)root.classList.add("mpv-hold");
    setPos(st.projAvg,false);
  });

  // ONE builder for the emitted fade/hold/fade run block, called TWICE with different names --
  // so the TWIN cannot drift from its sibling by construction (the shipped MoEProgress.css keeps
  // its mp-life / mp-life-b pair identical BY HAND, which is exactly the thing that can rot).
  function lifeBlock(name,cls){
    var t=total()||1,ka=(st.fadeIn/t*100).toFixed(2),kb=((st.fadeIn+st.hold)/t*100).toFixed(2),
        y=slideStops(REM);
    return "@keyframes "+name+" {\n"+
      "    0% { opacity: 0; transform: "+y[0]+"; animation-timing-function: "+st.fadeEase+"; }\n"+
      "  "+ka+"% { opacity: 1; transform: "+y[1]+"; animation-timing-function: linear; }\n"+
      "  "+kb+"% { opacity: 1; transform: "+y[2]+"; animation-timing-function: "+st.outEase+"; }\n"+
      "  100% { opacity: 0; transform: "+y[3]+"; }\n}\n"+
      "#moe-bar-root."+cls+" { animation: "+name+" "+t+"ms both; }\n";
  }
  // THE "LARGE" SIZE MODE block (mod_settings.progress_bar_size == 1), mirroring the shipped
  // MoEProgress.css's own appended `.mp-lg` block -- see X43() above for which lengths belong here
  // and why the rest must NOT be restated.
  //   SCOPE: `.mpv-lg` goes on the BODY (MoEBarTransient.applySize), WG's own ancestor-class
  //   idiom. Every selector below is its base rule plus one class, so it out-specifies it.
  //   NOT COMPOUND, and deliberately: the horizontal pair that must be compound is the
  //   INTERFACE-SCALE one (`.mp-s1.mp-lg`, both classes on document.body, where a lone `.mp-s1`
  //   rule would match under Large too and, being later in the file, win). This tuner has no
  //   interface-scale notion and emits no `.mpv-s1` rule at all, so there is no lone-class rule
  //   for a descendant combinator to lose to. Add an `.mpv-s1` pair later and its Large half owes
  //   the compound `.mpv-s1.mpv-lg`.
  //   A transform declaration REPLACES its base outright, so any transform below restates the
  //   WHOLE declaration verbatim (including the y/percentage terms, which take no factor).
  function largeBlock(){
    var pr=X43(st.gapP+halfOverhang())+"rem";
    function tick(cls,w,x){
      return ".mpv-lg .mpv-tick.mpv-"+cls+" { width: "+X43(w)+"rem;\n"+
        "  transform: translate(-50%, 50%) translateX("+X43(x)+"rem); }\n";
    }
    return ".mpv-lg #moe-bar-root { width: "+X43(st.trackW)+"rem; }\n"+
      ".mpv-lg .mpv-backdrop { left: "+X43(st.bdLeft)+"rem; width: "+X43(st.bdW)+"rem; }\n"+
      ".mpv-lg .mpv-bd { left: "+st.bdStripLeftLg+"rem; width: "+st.bdStripWLg+"rem; }\n"+
      tick("end",st.tickWEnd,st.tickXEnd)+tick("pre",st.tickWPre,st.tickXPre)+
      tick("proj",st.tickWProj,st.tickXProj)+
      ".mpv-lg .mpv-capR { padding-right: "+pr+"; transform: translateX("+X43(st.capxR)+"rem); }\n"+
      ".mpv-lg .mpv-capC { padding-right: "+pr+"; transform: translateX("+X43(st.capxC)+"rem); }\n"+
      ".mpv-lg .mpv-capP { padding-right: "+pr+";\n"+
      "  transform: translateY(50%) translateX("+X43(st.capxP)+"rem); }\n"+
      ".mpv-lg .mpv-cap .mpv-ico { margin-left: "+X43(st.icoGap)+"rem; }\n"+
      ".mpv-lg .mpv-cap .mpv-d { margin-right: "+X43(st.dGap)+"em; }\n"+
      ".mpv-lg .mpv-capR .mpv-eta { margin-left: "+X43(st.etaGap)+"rem; }\n";
  }

  function cssOut(){
    var timings={fadeInMs:st.fadeIn,holdMs:st.hold,fadeOutMs:st.fadeOut,totalMs:total(),
      slideRem:st.slide,slideEasingIn:st.fadeEase,slideEasingOut:st.outEase,
      tickDelayMs:st.tickDelay,tickDurationMs:st.tickDur,tickEasing:st.tickEase,
      deltaFadeMs:st.dFadeMs,deltaFadeEasing:st.dFadeEase,axisMode:axis,windowN:st.winN,
      topGlyph:st.dmgPIco,bottomGlyph:st.dmgCIco};
    return "/* MoEProgressVertical.css -- VERTICAL variant of the in-battle centre-screen MoE\n"+
      "   progress bar (class prefix .mpv-, never .mp-). Tuned in the browser\n"+
      "   (tools/dev/gen_bar_tuner_vertical.ps1) and copied VERBATIM; the battle window has no\n"+
      "   hot-reload. Position comes from Python (window.move()), NOT from CSS -- the tuner's own\n"+
      "   minimap-relative placement preview never reaches this file. Font: the bundled MoEBattle\n"+
      "   numeric subset, 19 glyphs (digits % ( ) + - , . / space) -- NO LETTERS.\n"+
      "   Axis: 0% at the BOTTOM, 100% at the TOP -- fill grows bottom->top (height, not width). */\n\n"+
      "#moe-bar-root {\n  position: relative;\n  width: "+st.trackW+"rem;\n  height: "+st.barH+"rem;\n"+
      "  font-family: \"MoEBattle\", \"Arial Narrow\", sans-serif;\n  text-align: center;\n  opacity: 0;\n}\n"+
      ".mpv-backdrop {\n  position: absolute;\n  left: "+st.bdLeft+"rem;\n  top: "+(-st.bdBleedY)+"rem;\n"+
      "  width: "+st.bdW+"rem;\n  height: "+(st.barH+2*st.bdBleedY)+"rem;\n  z-index: 0;\n}\n"+
      ".mpv-bd {\n  position: absolute;\n  left: "+st.bdStripLeft+"rem;\n  width: "+st.bdStripW+"rem;\n"+
      "  height: "+st.bdStripH+"rem;\n  z-index: 0;\n}\n"+
      ".mpv-bd::before {\n  content: \"\";\n  position: absolute; left: 0; top: 0; width: 100%; height: 100%;\n"+
      "  background: url(checker.png) repeat;\n  background-size: auto;\n  background-position: 0px 0px;\n"+
      "  image-rendering: pixelated;\n  opacity: "+st.dotAlpha+";\n  mask: "+dotMask()+";\n}\n"+
      ".mpv-bd::after {\n  content: \"\";\n  position: absolute; left: 0; top: 0; width: 100%; height: 100%;\n"+
      "  z-index: -1;\n  background: "+ugGrad()+";\n}\n"+
      ".mpv-bd-1 { top: "+st.bd1T+"rem; }\n.mpv-bd-2 { top: "+st.bd2T+"rem; }\n"+
      ".mpv-bd-3 { top: "+st.bd3T+"rem; }\n.mpv-bd-4 { top: "+st.bd4T+"rem; }\n"+
      ".mpv-track {\n  position: relative;\n  z-index: 1;\n  width: 100%;\n  height: 100%;\n  background: "+trackBg()+";\n}\n"+
      "/* Garage dash grid, rotated (0deg == \"to top\", so the first stop sits at the BOTTOM edge).\n"+
      "   background-size: 100% <period>rem tiles the gradient from a single period-sized tile instead\n"+
      "   of rasterizing it once across the whole track length -- without it the dash ink smears over\n"+
      "   ~4 device px instead of a crisp 2 (the sibling MoEEfficiencyVertical.css carries the same\n"+
      "   fix). The period is a Y-length the root font already scales via SIZE_F, so it takes no\n"+
      "   .mpv-lg twin below. */\n"+
      ".mpv-track::after {\n  content: \"\";\n  position: absolute; left: 0; top: 0; width: 100%; height: 100%;\n"+
      "  z-index: 1;\n  background-image: "+dashBg(REM)+";\n"+
      "  background-size: 100% "+REM(st.dashW+st.dashGap)+";\n  box-shadow: "+bdrSh(REM)+";\n}\n"+
      ".mpv-fill {\n  position: absolute;\n  left: 0;\n  bottom: 0;\n  width: 100%;\n  height: 0;\n  background: "+fillBg()+";\n"+
      "  transition: height "+st.tickDur+"ms "+st.tickEase+" "+st.tickDelay+"ms;\n}\n"+
      ".mpv-fill.mpv-up   { background: "+hexA(st.upCol,st.fillA)+"; }\n"+
      ".mpv-fill.mpv-down { background: "+hexA(st.dnCol,st.fillA)+"; }\n"+
      ".mpv-tick {\n  position: absolute;\n  left: 50%;\n  z-index: 2;\n}\n"+
      ".mpv-tick.mpv-end {\n  background: "+hexA(st.endCol,st.endA)+";\n  width: "+st.tickWEnd+"rem;\n  height: "+st.tickHEnd+"rem;\n"+
      "  transform: translate(-50%, 50%) translateX("+st.tickXEnd+"rem);\n}\n"+
      ".mpv-tick.mpv-bottom { bottom: 0; }\n"+
      ".mpv-tick.mpv-top    { bottom: 100%; }\n"+
      ".mpv-tick.mpv-pre {\n  background: "+hexA(st.preCol,st.preA)+";\n  width: "+st.tickWPre+"rem;\n  height: "+st.tickHPre+"rem;\n"+
      "  transform: translate(-50%, 50%) translateX("+st.tickXPre+"rem);\n}\n"+
      ".mpv-tick.mpv-proj  {\n  background: "+hexA(st.projCol,st.projA)+";\n  box-shadow: "+projSh(REM)+";\n"+
      "  width: "+st.tickWProj+"rem;\n  height: "+st.tickHProj+"rem;\n"+
      "  transform: translate(-50%, 50%) translateX("+st.tickXProj+"rem);\n"+
      "  transition: bottom "+st.tickDur+"ms "+st.tickEase+" "+st.tickDelay+"ms;\n}\n"+
      ".mpv-tick.mpv-proj.mpv-up   { box-shadow: "+projSh(REM,hexA(st.upCol,DGA))+"; }\n"+
      ".mpv-tick.mpv-proj.mpv-down { box-shadow: "+projSh(REM,hexA(st.dnCol,DGA))+"; }\n"+
      "/* FIXED-ANCHOR captions, digit-count-independent (bug fix, mirrors\n"+
      "   eff_bar_tuner_vertical.html's shipped fix for the same defect): a shrink-wrapped box\n"+
      "   centred via left:50%+translateX(-50%) never gives any child a truly fixed screen position\n"+
      "   (both its edges move as content width changes), so all THREE captions now share ONE fixed\n"+
      "   right edge -- right:100%+left:auto, pinned to the track's own left edge -- clear of the\n"+
      "   tick's outer-edge overhang via the shared padding-right below. Numeral-then-icon DOM order\n"+
      "   means each caption's icon is the LAST in-flow child, so it sits flush against that fixed\n"+
      "   edge and is provably invariant to digit count. Only the numeral (and capC's delta, hanging\n"+
      "   off ITS left edge) grows/shrinks LEFTWARD, away from the anchor. capP is also the ONLY one\n"+
      "   that moves, tracking the pre tick's `bottom` -- and like that tick it never animates within\n"+
      "   one replay, so no transition is declared. */\n"+
      ".mpv-cap {\n  position: absolute;\n  display: flex;\n  flex-direction: row;\n  align-items: center;\n"+
      "  white-space: nowrap;\n  z-index: 3;\n  right: 100%;\n  left: auto;\n}\n"+
      "/* Gameface drops margin on the bottom/right ANCHORED side (gameface-drops-margin-on-the-\n"+
      "   anchored-side) -- padding on the bottom/right anchored sides; margin works as written on\n"+
      "   capC's top:100% anchor. padding-right (shared by all three captions) also carries the\n"+
      "   tick's outer-edge overhang (see the anchor comment above), so it clears the tick, not just\n"+
      "   the track. */\n"+
      ".mpv-capR { bottom: 100%; padding-bottom: "+st.gapR+"rem; padding-right: "+(st.gapP+halfOverhang())+"rem;\n"+
      "            transform: translateX("+st.capxR+"rem); font-size: "+st.rFS+"rem; line-height: "+lh(st.rFS)+"rem; }\n"+
      ".mpv-capC { top: 100%; margin-top: "+st.gapC+"rem; padding-right: "+(st.gapP+halfOverhang())+"rem;\n"+
      "            transform: translateX("+st.capxC+"rem); font-size: "+st.cFS+"rem; line-height: "+lh(st.cFS)+"rem; }\n"+
      ".mpv-capP { padding-right: "+(st.gapP+halfOverhang())+"rem; transform: translateY(50%) translateX("+st.capxP+"rem);\n"+
      "            font-size: "+st.pFS+"rem; line-height: "+lh(st.pFS)+"rem; }\n"+
      "/* Icon follows its numeral (DOM order: numeral, then icon) -- gap on the icon's LEFT. */\n"+
      ".mpv-cap .mpv-ico { margin-left: "+st.icoGap+"rem; }\n"+
      ".mpv-cap .mpv-v,\n.mpv-cap .mpv-eta,\n.mpv-cap .mpv-d {\n  color: #ffffff;\n  font-weight: "+st.wt+";\n"+
      "  letter-spacing: "+st.ls+"em;\n"+
      "  text-shadow: 0rem 0rem "+st.shBlur+"rem "+hexA(st.shColor,st.shAlpha)+";\n}\n"+
      "/* Delta is an IN-FLOW flex child, ordered FIRST (delta, numeral, icon) -- an ordinary\n"+
      "   margin-right gap, not an out-of-flow box hanging off a content-dependent edge (the exact\n"+
      "   mechanism of the digit-count bug this fixes). */\n"+
      ".mpv-cap .mpv-d {\n  margin-right: "+st.dGap+"em;\n  font-size: "+st.dFS+"rem;\n"+
      "  transform: translateY("+st.dY+"rem);\n  line-height: "+lh(st.dFS)+"rem;\n  opacity: 0;\n"+
      "  transition: opacity "+st.dFadeMs+"ms "+st.dFadeEase+";\n}\n"+
      ".mpv-v.mpv-up,\n.mpv-d-num.mpv-up,\n.mpv-eta.mpv-up {\n  color: #ffffff;\n"+
      "  text-shadow: 0rem 0rem "+st.shBlur+"rem "+hexA(st.shColor,st.shAlpha)+",\n"+
      "               0rem 0rem "+st.dGlowW+"rem "+hexA(st.upCol,DGA)+",\n"+
      "               0rem 0rem "+st.dGlowT+"rem "+hexA(st.upCol,DGA)+";\n}\n"+
      ".mpv-v.mpv-down,\n.mpv-d-num.mpv-down,\n.mpv-eta.mpv-down {\n  color: #ffffff;\n"+
      "  text-shadow: 0rem 0rem "+st.shBlur+"rem "+hexA(st.shColor,st.shAlpha)+",\n"+
      "               0rem 0rem "+st.dGlowW+"rem "+hexA(st.dnCol,DGA)+",\n"+
      "               0rem 0rem "+st.dGlowT+"rem "+hexA(st.dnCol,DGA)+";\n}\n"+
      ".mpv-ico {\n  position: relative;\n  display: block;\n  flex: none;\n  width: "+st.icoBox+"rem;\n"+
      "  height: "+st.icoBox+"rem;\n  transform: translate(0rem, 0rem);\n}\n"+
      ".mpv-capP .mpv-ico { transform: translate(0rem, "+st.icoYP+"rem); }\n"+
      ".mpv-capC .mpv-ico { transform: translate(0rem, "+st.icoYC+"rem); }\n"+
      ".mpv-capR .mpv-ico { transform: translate(0rem, "+st.icoYR+"rem); }\n"+
      ".mpv-capR .mpv-v,\n.mpv-capR .mpv-eta { transform: translateY("+st.numYR+"rem); }\n"+
      ".mpv-capC .mpv-v { transform: translateY("+st.numYC+"rem); }\n"+
      ".mpv-capP .mpv-v { transform: translateY("+st.numYP+"rem); }\n"+
      ".mpv-ico::before {\n  content: \"\";\n  position: absolute;\n  left: 50%;\n  top: 50%;\n  z-index: -1;\n"+
      "  width: 106%;\n  height: 106%;\n  transform: translate(-50%, -50%);\n"+
      "  background: radial-gradient(circle at 50% 50%, "+hexA(st.icoGlowCol,st.icoGlowA)+" 0%, transparent 73%);\n}\n"+
      ".mpv-capR .mpv-ico::before {\n"+
      "  background: radial-gradient(circle at 50% 50%, "+hexA(st.reqGlowCol,st.reqGlowA)+" 0%, transparent 73%);\n}\n"+
      ".mpv-ico::after {\n  content: \"\";\n  position: absolute; left: 0; top: 0; width: 100%; height: 100%;\n"+
      "  background-repeat: no-repeat;\n  background-position: center;\n}\n"+
      ".mpv-ico.dmgp { width: "+st.dmgPBox+"rem; height: "+st.dmgPBox+"rem; }\n"+
      ".mpv-ico.dmgc { width: "+st.dmgCBox+"rem; height: "+st.dmgCBox+"rem; }\n"+
      ".mpv-ico.dmgp::after {\n  background-image: url("+IMG[st.dmgPIco]+");\n"+
      "  background-size: "+icoSz(DMG[st.dmgPIco].bb)+";\n  filter: brightness(3);\n}\n"+
      ".mpv-ico.dmgc::after {\n  background-image: url("+IMG[st.dmgCIco]+");\n"+
      "  background-size: "+icoSz(DMG[st.dmgCIco].bb)+";\n  filter: brightness(3);\n}\n"+
      ".mpv-ico.moe { width: "+st.markBox+"rem; height: "+st.markBox+"rem; }\n"+
      ".mpv-ico.moe::after {\n  background-image: url("+IMG.top+");\n"+
      "  background-size: "+icoSz(MOEBB)+";\n  filter: brightness(3);\n}\n"+
      ".mpv-ico.mk { width: "+st.markBox+"rem; height: "+st.markBox+"rem; }\n"+
      ".mpv-ico.mk::after { background-size: contain; }\n"+
      ".mpv-ico.mk1::after { background-image: url("+IMG.mk[0]+"); }\n"+
      ".mpv-ico.mk2::after { background-image: url("+IMG.mk[1]+"); }\n"+
      ".mpv-ico.mk3::after { background-image: url("+IMG.mk[2]+"); }\n"+
      "/* etaGap is the gap BETWEEN the two numeral+icon pairs (mark-icon -> eta-numeral); the\n"+
      "   battles icon itself keeps only the plain uniform icoGap after its own eta numeral. */\n"+
      ".mpv-capR .mpv-eta { margin-left: "+st.etaGap+"rem; }\n"+
      ".mpv-ico.battles::before {\n  background: radial-gradient(circle at 50% 50%, "+hexA(st.icoGlowCol,st.icoGlowA)+" 0%, transparent 73%);\n}\n"+
      ".mpv-ico.battles::after {\n  background-image: url("+IMG.battles+");\n"+
      "  background-size: "+icoSz(BATTLESBB)+";\n  filter: brightness(3);\n}\n"+
      ".mpv-ico.none { display: none; }\n"+
      "#moe-bar-root.mpv-full .mpv-track,\n#moe-bar-root.mpv-full .mpv-fill,\n#moe-bar-root.mpv-full .mpv-tick {\n"+
      "  box-shadow: 0 0 "+st.glowB+"rem "+hexA(st.glowCol,st.glowA)+";\n}\n"+
      "#moe-bar-root.mpv-full .mpv-fill {\n  background: "+hexA(st.glowCol,st.fullFillA)+";\n}\n"+
      "#moe-bar-root.mpv-full .mpv-v {\n"+
      "  text-shadow: 0rem 0rem "+st.shBlur+"rem "+hexA(st.shColor,st.shAlpha)+",\n"+
      "               0 0 "+st.glowB+"rem "+hexA(st.glowCol,st.glowA)+",\n"+
      "               0 0 "+st.glowB2+"rem "+hexA(st.glowCol,st.glowA)+";\n}\n"+
      lifeBlock("mpv-life","mpv-run")+
      "/* THE RE-TRIGGER TWIN -- byte-identical to @keyframes mpv-life above apart from the name\n"+
      "   (emitted from ONE builder, so it cannot drift). A baked fade/hold/fade keyframe cannot be\n"+
      "   re-triggered in place: JS restarts the transient with remove-class -> force-reflow ->\n"+
      "   re-add-class, which is UNPROVEN in Coherent/Gameface, and if the engine coalesces the\n"+
      "   re-add with the run it just cancelled the restart is a NO-OP -- which, because\n"+
      "   #moe-bar-root rests at opacity 0 under `both` fill, leaves the bar permanently INVISIBLE\n"+
      "   after its first appearance. So the JS ALTERNATES between .mpv-run and .mpv-run-b\n"+
      "   (MoEBarTransient.js RUN_CLASSES/RUN_NAMES): consecutive runs carry DIFFERENT\n"+
      "   animation-names, which the engine cannot coalesce. Without this pair the vertical bar\n"+
      "   cannot re-raise for a second battle event at all. */\n"+
      lifeBlock("mpv-life-b","mpv-run-b")+"\n"+
      "/* ===== THE \"LARGE\" SIZE MODE (mod_settings.progress_bar_size == 1). The mode is delivered\n"+
      "   by the ROOT FONT SIZE (MoEBarTransient.js SIZE_F == 1.25), which IS the rem->px factor in\n"+
      "   Gameface, so that one write re-lays the whole composition 1.25x and correctly leaves every\n"+
      "   %, em, gradient stop and derived background-size ratio alone. What is left is the CROSS-AXIS\n"+
      "   (screen-x) lengths, which must reach 5/3 total and therefore owe SIZE_XF == 4/3 ALONE on top\n"+
      "   of it -- so every declaration below is an x-length and nothing else. Do NOT add a font-size,\n"+
      "   a bar length, a tick thickness, a vertical gap or a keyframe here: the root font already has\n"+
      "   them and restating one would DOUBLE-APPLY SIZE_F. The dash grid is a y-period on this bar\n"+
      "   (0deg == \"to top\"), unlike the horizontal bar's 90deg twin, so it takes no rule either. */\n"+
      largeBlock()+"\n"+
      "/* Animation timings for phase 2's JS:\n"+
      JSON.stringify(timings,null,2)+"\n*/\n";
  }

  // ---- panel wiring (unchanged idiom from the horizontal tuner) ----
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
  [["cHold","holdVis"],["cBounds","bounds"],["cBd","bd"],["cDash","dashOn"],["cBdr","bdrOn"]].forEach(function(p){
    document.getElementById(p[0]).addEventListener("change",function(e){
      st[p[1]]=e.target.checked;
      if(p[1]==="holdVis")root.classList.toggle("mpv-hold",st.holdVis&&!root.classList.contains("mpv-run"));
      apply();});
  });
  document.querySelectorAll("#axisSeg button").forEach(function(b){b.addEventListener("click",function(){
    axis=b.dataset.a;document.querySelectorAll("#axisSeg button").forEach(function(x){x.classList.remove("on");});
    b.classList.add("on");apply();});});
  document.getElementById("bReplay").addEventListener("click",replay);
  document.getElementById("bTick").addEventListener("click",function(){
    var step=st.projAvg-st.preAvg;if(step<=0)step=Math.max(1,(st.thrNext-st.projAvg)*(2/101));
    set("preAvg",st.projAvg);set("projAvg",+(st.projAvg+step).toFixed(0));apply();replay();});
  document.getElementById("bFull").addEventListener("click",function(){
    set("preAvg",st.thrNext-Math.max(1,Math.round((st.thrNext-st.preAvg)*(2/101))));
    set("projAvg",st.thrNext);apply();replay();});
  document.getElementById("copyBtn").addEventListener("click",function(){
    var t=cssOut();if(navigator.clipboard)navigator.clipboard.writeText(t);
    var b=document.getElementById("copyBtn");b.textContent="Copied";setTimeout(function(){b.textContent="Copy CSS";},1300);});

  var stage=document.getElementById("stage");
  function useShot(f){if(!f)return;var r=new FileReader();
    r.onload=function(){stage.style.backgroundImage="url("+r.result+")";};r.readAsDataURL(f);}
  document.getElementById("shot").addEventListener("change",function(e){useShot(e.target.files[0]);});
  ["dragenter","dragover"].forEach(function(ev){stage.addEventListener(ev,function(e){e.preventDefault();stage.classList.add("drop");});});
  ["dragleave","drop"].forEach(function(ev){stage.addEventListener(ev,function(e){e.preventDefault();stage.classList.remove("drop");});});
  stage.addEventListener("drop",function(e){useShot(e.dataTransfer.files[0]);});

  // ---- REGRESSION TEST for the digit-count anchor fix (bar-tuner-digit-count-anchor-fix) -------
  // Needs a REAL layout engine (getBoundingClientRect) -- this file also runs headless (vm shim,
  // check_bar_vertical.js), which has no layout at all (offsetWidth is a flat literal). Skip
  // cleanly there, and make the skip VISIBLE (console.log), not silent -- a check nobody can see
  // ran is indistinguishable from a check that never existed.
  function checkCaptionInvariance(){
    var out=[], fail=0;
    function ok(name,cond){out.push((cond?"PASS  ":"FAIL  ")+name);if(!cond)fail++;}
    var probe;
    try{
      probe=document.createElement("span");probe.textContent="12345678";
      probe.style.position="absolute";document.body.appendChild(probe);
      var w=probe.getBoundingClientRect&&probe.getBoundingClientRect().width;
      document.body.removeChild(probe);
    }catch(e){w=undefined;}
    if(!(typeof w==="number"&&w>0)){
      var msg="SKIP  caption digit-count invariance (no real layout engine here -- run this "+
        "tuner's checkCaptionInvariance() in an actual browser/Artifact to exercise it)";
      console.log(msg);
      return {skipped:true,out:[msg]};
    }
    var wasPre=st.preAvg,wasProj=st.projAvg;
    function nearPx(a,b){return Math.abs(a-b)<0.5;}
    var icoC=root.querySelector(".mpv-capC .mpv-ico");
    // 3 / 5 / 7 digits, each step +2 glyphs (per the task's own negative-control guidance -- a
    // 1-glyph step can hide under subpixel rounding), well inside a fixed axis so only the
    // caption's own box geometry is under test.
    var samples=[100,12345,1234567].map(function(v){
      st.preAvg=v;st.projAvg=v+8;apply();
      var ic=icoC.getBoundingClientRect(),dl=capD.getBoundingClientRect();
      return {v:v,digits:fmt(v).replace(/\D/g,"").length,icoX:ic.left,dX:dl.left};
    });
    st.preAvg=wasPre;st.projAvg=wasProj;apply();
    ok("sample digit counts differ by >=2 each step (not vacuous): "+
       samples.map(function(s){return s.digits;}).join(","),
       samples[1].digits-samples[0].digits>=2&&samples[2].digits-samples[1].digits>=2);
    ok("capC icon x-position is IDENTICAL at 3/5/7-digit projAvg ("+
       samples.map(function(s){return s.icoX.toFixed(2);}).join(" / ")+")",
       nearPx(samples[0].icoX,samples[1].icoX)&&nearPx(samples[1].icoX,samples[2].icoX));
    ok("capC delta x-position at 3/5/7-digit projAvg ("+
       samples.map(function(s){return s.dX.toFixed(2);}).join(" / ")+") -- EXPECTED to move: the "+
       "delta is in-flow beside the numeral, on the side that grows away from the fixed icon "+
       "anchor, not the anchored side itself; only the ICON is required to be invariant",
       true);
    out.forEach(function(l){console.log(l);});
    return {skipped:false,pass:fail===0,out:out};
  }

  apply();replay();checkCaptionInvariance();
</script>
'@

$tpl = $tpl.Replace('__BG__', $bg).Replace('__TTF__', $ttf).Replace('__CK__', $ck).
  Replace('__ICO_DMG__', $ico['icon_battle_condition_damage']).
  Replace('__ICO_BM__', $ico['icon_battle_condition_barrel_mark']).
  Replace('__ICO_TOP__', $ico['icon_battle_condition_top']).
  Replace('__ICO_BATTLES__', $ico['icon_battle_condition_battles']).
  Replace('__ICO_MK1__', $ico['mark_1']).Replace('__ICO_MK2__', $ico['mark_2']).Replace('__ICO_MK3__', $ico['mark_3'])

$dest = if ([IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path $repo $Out }
if ($SelfCheck) { $dest = Join-Path ([IO.Path]::GetTempPath()) "gen_bar_tuner_vertical_selfcheck.html" }
New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
[IO.File]::WriteAllText($dest, $tpl, (New-Object System.Text.UTF8Encoding($false)))

# ---- Artifact variant: DERIVED from the same $tpl (never a forked template -- the two must not
# drift). An Artifact host wraps whatever it is given in its OWN <!doctype html><head><body>
# skeleton, so the only difference from $tpl is dropping the leading <!DOCTYPE html><meta
# charset="utf-8"> and shortening <title> -- the <style>/markup/<script> that follow are
# byte-identical to $tpl's. Every asset is already inlined as a data: URI by Asset() above, so
# this stays a strict-CSP, zero-external-host document with no further work.
$tplArtifact = $tpl -replace '^<!DOCTYPE html><meta charset="utf-8"><title>[^<]*</title>', `
  '<title>Vertical MoE Progress Bar Tuner</title>'
if ($tplArtifact -eq $tpl) { throw "gen_bar_tuner_vertical: artifact header substitution matched nothing -- the template's opening tags drifted" }

if ($SelfCheck) {
  $fail = @()
  if (-not (Test-Path $dest)) { $fail += "not written: $dest" }
  else {
    $len = (Get-Item $dest).Length
    if ($len -lt 100KB) { $fail += "too small: $len bytes (expected > 100 KB of inlined assets)" }
    $raw = Get-Content $dest -Raw
    if ($raw -match '__[A-Z_]+__') { $fail += "unsubstituted placeholder: $($Matches[0])" }
    $hasRootFontPin = $raw -match 'documentElement\.style\.fontSize'
    $styleMatch = [regex]::Match($raw, '(?s)<style>(.*?)</style>')
    if ($styleMatch.Success) {
      $noComments = $styleMatch.Groups[1].Value -replace '(?s)/\*.*?\*/', ''
      if (-not $hasRootFontPin -and ($noComments -match '[0-9.]+rem[;}]')) {
        $fail += "literal rem in live style block with no root font-size pin: $($Matches[0])"
      }
    }
    # ---- vertical-tuner-specific invariants (a size/placeholder check alone is NOT a real gate --
    # see bar-tuner-selfcheck-is-not-a-gate) ----
    if ($raw -notmatch '\.mpv-[a-zA-Z-]') { $fail += "no .mpv- class found -- did this drift onto .mp-?" }
    if ($raw -match '(?<!\.)\bmp-[a-zA-Z-]+') { $fail += "found a bare .mp- token -- the horizontal bar's class prefix leaked in" }
    if ($raw -notmatch '228,\s*279,\s*329,\s*409,\s*510,\s*628') { $fail += "minimap size table [228,279,329,409,510,628] not found (measure_minimap.py)" }
    if ($raw -notmatch 'id:"mmGap"[^}]*val:8\b') { $fail += "mmGap default is not 8" }
    if ($raw -notmatch 'id:"mmGapBottom"[^}]*val:30\b') { $fail += "mmGapBottom default is not 30" }
    if ($raw -notmatch 'id:"capxR"[^}]*val:14\b') { $fail += "capxR default is not 14" }
    if ($raw -notmatch 'id:"capxC"[^}]*val:16\b') { $fail += "capxC default is not 16" }
    if ($raw -notmatch 'id:"capxP"[^}]*val:0\b') { $fail += "capxP default is not 0" }
    # ---- Artifact-variant cleanliness (checked unconditionally -- cheap, in-memory, derived from
    # the same $tpl, so this is real protection against the header substitution silently no-oping
    # or a future edit re-adding a skeleton tag). Byte size + the "real reference, not base64
    # noise" external-host scan are the more thorough pass in check_bar_vertical.js. ----
    foreach ($tag in @('<!DOCTYPE', '<html', '<head', '<body')) {
      if ($tplArtifact -match [regex]::Escape($tag)) { $fail += "artifact variant still contains a $tag tag" }
    }
    if ($tplArtifact -notmatch '<title>') { $fail += "artifact variant lost its <title>" }
  }
  if ($fail.Count) { $fail | ForEach-Object { Write-Output "FAIL: $_" }; exit 1 }
  Write-Output ("self-check OK: {0} ({1:N0} bytes, no leftover placeholders, .mpv- present, minimap table present, mmGap default 8, mmGapBottom default 30, capxR/capxC/capxP defaults 14/16/0, artifact variant skeleton-tag-free)" -f $dest, $len)
  exit 0
}
Write-Output ("wrote {0} ({1:N0} bytes)" -f $dest, (Get-Item $dest).Length)

if ($Artifact) {
  $art = if ([IO.Path]::IsPathRooted($ArtifactOut)) { $ArtifactOut } else { Join-Path $repo $ArtifactOut }
  New-Item -ItemType Directory -Force -Path (Split-Path $art -Parent) | Out-Null
  [IO.File]::WriteAllText($art, $tplArtifact, (New-Object System.Text.UTF8Encoding($false)))
  Write-Output ("wrote {0} ({1:N0} bytes) -- artifact-ready, no doctype/html/head/body, zero external hosts" `
    -f $art, (Get-Item $art).Length)
}

# ---- -EmitCss: the settled stylesheet as a real file (verbatim driver idiom from
# gen_bar_tuner.ps1 -- cssOut() is NOT reimplemented here, for the same drift reason). ----------
$DRIVER = @'
// Written by gen_bar_tuner_vertical.ps1 -EmitCss. node <this> <tuner.html> <out.css>
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
const ctx = { document: { head: El(), body: El(), documentElement: El(), createElement: El,
    querySelectorAll: () => [], getElementById: id => byId[id] || (byId[id] = El()) },
  navigator: { clipboard: { writeText: t => { COPIED = t; } } },
  requestAnimationFrame: f => f(), setTimeout: () => 0, clearTimeout: () => { },
  FileReader: function () { this.readAsDataURL = () => { }; },
  console, JSON, Math, Object, String, Number, parseFloat, parseInt, isNaN, Array };
ctx.window = ctx;
vm.runInContext(m[1], vm.createContext(ctx), { filename: 'tuner.js' });
byId['copyBtn']._ev.click({});
if (typeof COPIED !== 'string' || !COPIED.length) throw new Error('Copy CSS produced nothing');
if (COPIED !== ctx.cssOut()) throw new Error('clipboard bytes != cssOut()');
if (COPIED !== byId['out'].textContent) throw new Error('clipboard bytes != the panel preview');
if (/undefined|NaN|\[object|var\(--|__[A-Z_]+__/.test(COPIED)) throw new Error('unresolved value in emitted CSS');
fs.writeFileSync(process.argv[3], COPIED);
'@
if ($EmitCss) {
  if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "gen_bar_tuner_vertical: -EmitCss needs node on PATH (it runs the tuner's own cssOut() headlessly)"
  }
  $css = if ([IO.Path]::IsPathRooted($CssOut)) { $CssOut } else { Join-Path $repo $CssOut }
  New-Item -ItemType Directory -Force -Path (Split-Path $css -Parent) | Out-Null
  $drv = Join-Path ([IO.Path]::GetTempPath()) "gen_bar_tuner_vertical_emitcss.js"
  [IO.File]::WriteAllText($drv, $DRIVER, (New-Object System.Text.UTF8Encoding($false)))
  try {
    & node $drv $dest $css
    if ($LASTEXITCODE -ne 0) { throw "gen_bar_tuner_vertical: -EmitCss driver failed (node exit $LASTEXITCODE)" }
  } finally { Remove-Item -LiteralPath $drv -Force -ErrorAction SilentlyContinue }
  $raw = [IO.File]::ReadAllText($css)
  Write-Output ("wrote {0} ({1:N0} bytes, {2:N0} lines) -- Copy-CSS-identical at the schema defaults" `
    -f $css, [Text.Encoding]::UTF8.GetByteCount($raw), ($raw.ToCharArray() | Where-Object { $_ -eq "`n" }).Count)
}
