<#
  gen_overlay_tuner.ps1 -- PowerShell (pwsh 7+ / Windows PowerShell 5.1). Run from the repo root:

      pwsh tools\dev\gen_overlay_tuner.ps1 [-Out TASKS/refs/in-battle-overlay-tuner.html]
                                            [-GameDir D:/Games/World_of_Tanks_EU] [-ExtractIcons]

  REBUILD (2026-08-12): the previous version of this script hardcoded a stale, now-deleted
  session scratchpad path at line 1 ($dir) -- it could not run at all, let alone regenerate a
  correct tuner. The tuner file it left behind was ALSO architecturally stale: per-row
  `.mb-row::before` pseudo-backdrops + negative-margin row pitch (the bug MoEBattle.css's own
  comments say was fixed) and zero markup for the row-3 / countedAssist state.

  This version does NOT tune anything -- the calculator overlay has no design knobs left to
  tune (unlike the bar tuners, which host live sliders). It is a PREVIEW HARNESS: it embeds the
  shipped MoEBattle.css VERBATIM (only the two @font-face/img:// asset URLs are swapped for
  data: URIs so the file opens standalone in a browser -- the emitted rule TEXT is untouched)
  around the EXACT DOM ensureRoot() builds (MoEBattle.js:78-112), frozen at two data states
  (countedAssist on/off) toggled by a tiny inline <script> that mirrors render()'s row-3 toggle
  (MoEBattle.js:170-185) -- NOT a copy of the tuning-slider apply() pattern the bar tuners use.
  Drift gate: tools/dev/check_overlay_css.js re-derives the same substitution from the live CSS
  and asserts byte-equality, so a future MoEBattle.css edit cannot silently leave this stale.

  -ExtractIcons pulls the 5 needed quest_type icon PNGs (barrel_mark, improve, assist,
  assist_track, assist_radio, assist_stun) out of the client's gui-part{1..4}.pkg into
  TASKS/refs/icons/ (gen_bar_tuner.ps1's flat "__" naming; TASKS/refs is gitignored, so this is a
  fresh-clone step, not a repo asset). Idempotent -- already-present files are skipped.
#>
param(
  [string]$Out = "TASKS/refs/in-battle-overlay-tuner.html",
  [string]$GameDir = "D:/Games/World_of_Tanks_EU",
  [switch]$ExtractIcons
)
$ErrorActionPreference = "Stop"

# Repo root from this script's location (tools/dev -> tools -> repo). Never hardcode a
# session scratchpad path -- that is exactly how the old version of this script died.
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

$CSS_PATH = Join-Path $repo "src/res/gui/gameface/mods/14th_ua/MoECalculator/MoEBattle.css"
$TTF_PATH = Join-Path $repo "src/res/gui/gameface/mods/14th_ua/MoECalculator/MoEBattle.ttf"

$ICONS = @(
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_barrel_mark.png',
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_improve.png',
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_assist.png',
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_assist_track.png',
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_assist_radio.png',
  'gui/maps/icons/personal_missions_30/quest_type/128x128/icon_battle_condition_assist_stun.png'
)
function IconRel($inner) { "TASKS/refs/icons/" + (($inner -replace '^gui/maps/icons/', '') -replace '/', '__') }

# Idempotent, same strategy as gen_bar_tuner.ps1 -- the icons are scattered across the four
# gui-part packages, so all four are scanned rather than guessing which one holds which.
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
    if (-not (Test-Path -LiteralPath $pkg)) { throw "gen_overlay_tuner: missing package -> $pkg" }
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
  if ($want.Count) { throw "gen_overlay_tuner: not found in any gui-part pkg -> $($want.Keys -join ', ')" }
}
if ($ExtractIcons) { ExtractIconsNow }

function Asset($rel) {
  $p = Join-Path $repo $rel
  if (-not (Test-Path -LiteralPath $p)) { throw "gen_overlay_tuner: missing asset -> $p (run with -ExtractIcons)" }
  [Convert]::ToBase64String([IO.File]::ReadAllBytes($p))
}

if (-not (Test-Path -LiteralPath $CSS_PATH)) { throw "gen_overlay_tuner: shipped CSS not found -> $CSS_PATH" }
$css = [IO.File]::ReadAllText($CSS_PATH)
$fontB64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($TTF_PATH))

# --- substitution 1: the @font-face src (bare-sibling + coui:// -- neither resolves from a
# standalone file opened in a browser) -> a data: URI. check_overlay_css.js re-derives this
# exact regex from the live CSS and asserts byte-equality against what is embedded below, so the
# REST of the stylesheet (every rule, every comment) stays provably verbatim.
$fontRe = [regex]::new('src:\s*url\(MoEBattle\.ttf\)\s*format\("truetype"\),\s*\r?\n\s*url\("coui://[^"]*"\)\s*format\("truetype"\);')
if (-not $fontRe.IsMatch($css)) { throw "gen_overlay_tuner: @font-face src pattern not found -- MoEBattle.css drifted" }
$css = $fontRe.Replace($css, ('src: url(data:font/ttf;base64,' + $fontB64 + ') format("truetype");'), 1)

# --- substitution 2: the six img:// quest_type icon urls -> data: URIs (same reasoning).
$iconMap = @{
  'icon_battle_condition_barrel_mark.png'  = (Asset (IconRel $ICONS[0]))
  'icon_battle_condition_improve.png'      = (Asset (IconRel $ICONS[1]))
  'icon_battle_condition_assist.png'       = (Asset (IconRel $ICONS[2]))
  'icon_battle_condition_assist_track.png' = (Asset (IconRel $ICONS[3]))
  'icon_battle_condition_assist_radio.png' = (Asset (IconRel $ICONS[4]))
  'icon_battle_condition_assist_stun.png'  = (Asset (IconRel $ICONS[5]))
}
foreach ($name in $iconMap.Keys) {
  $find = 'img://gui/maps/icons/personal_missions_30/quest_type/128x128/' + $name
  if (-not $css.Contains($find)) { throw "gen_overlay_tuner: icon url not found -- $find (MoEBattle.css drifted)" }
  $css = $css.Replace($find, ('data:image/png;base64,' + $iconMap[$name]))
}

# --- the exact DOM ensureRoot() builds (MoEBattle.js:83-109), frozen at the countedAssist=ON
# values. The OFF state is reached by the inline <script> below toggling the SAME two
# inline-style flips render() performs at MoEBattle.js:182-184 -- no second copy of the markup.
$dom = @'
<div class="mb-backdrop mb-bd-1"></div>
<div class="mb-backdrop mb-bd-2"></div>
<div class="mb-backdrop mb-bd-3"></div>
<div class="mb-row">
  <span class="mb-ico dmg"></span>
  <span class="mb-value mb-cd mb-up">3,180</span>
  <span class="mb-sep">/</span>
  <span class="mb-value mb-avg">2,910</span>
</div>
<div class="mb-row">
  <span class="mb-ico pct"></span>
  <span class="mb-value mb-pct">84.73%</span>
  <span class="mb-delta">(<span class="mb-delta-num mb-up">+0.42%</span>)</span>
</div>
<div class="mb-row mb-row-assist">
  <span class="mb-ico ast spot"></span>
  <span class="mb-value mb-ast">640</span>
</div>
'@

$html = @"
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>MoE Calculator overlay -- frozen preview</title>
<style>
$css
</style>
</head>
<body>
<div id="moe-battle-root"></div>
<script>
// NOT part of the mirrored widget -- a render()-lockstep toggle so this ONE frozen DOM can show
// either data state (MoEBattle.js:170-185) without a second markup copy. window.setAssist(bool)
// is the render entry point gen_settings_previews.py calls before each screenshot.
document.getElementById("moe-battle-root").innerHTML = $($dom | ConvertTo-Json);
window.setAssist = function (on) {
  var row = document.querySelector(".mb-row-assist"), bd3 = document.querySelector(".mb-bd-3");
  row.style.display = on ? "" : "none";
  bd3.style.display = on ? "" : "none";
};
window.setAssist(true);
</script>
</body>
</html>
"@

$outPath = if ([IO.Path]::IsPathRooted($Out)) { $Out } else { Join-Path $repo $Out }
New-Item -ItemType Directory -Force -Path (Split-Path $outPath -Parent) | Out-Null
[IO.File]::WriteAllText($outPath, $html, (New-Object System.Text.UTF8Encoding($false)))
Write-Output ("wrote {0} ({1:N0} bytes)" -f $outPath, (Get-Item $outPath).Length)
