$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pixalPython = 'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\python.exe'
$pixalBakes = Get-Content -LiteralPath 'tmp\pixal-fixed-geometry-uv-comparison-20261012-padding.json' -Raw | ConvertFrom-Json
if ($pixalBakes.Count -ne 9) { throw 'Require all nine fresh bake controls' }
$pixalOld = Get-Content -LiteralPath 'tmp\pixal-fixed-geometry-uv-comparison-20261011.json' -Raw | ConvertFrom-Json
$pixalCombinedPath = 'tmp\pixal-round4-color-trials-20261012.json'
if (Test-Path -LiteralPath $pixalCombinedPath) { throw 'Preserve previous control inventory' }
@($pixalOld) + @($pixalBakes) | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $pixalCombinedPath -Encoding utf8
& $pixalPython -u 'scripts\compare_pixal_surface_colors.py' --trials $pixalCombinedPath --output 'tmp\pixal-round4-surface-colors-20261012.json'
if ($LASTEXITCODE -ne 0) { throw 'Color or controlled mip comparison failed' }
foreach ($pixalBake in $pixalBakes) {
    $pixalKey = "$($pixalBake.case)-$($pixalBake.variant)-20261012"
    $pixalQuality = "tmp\pixal-round4-export-quality-$pixalKey.json"
    $pixalOverlap = "tmp\pixal-round4-overlap-$pixalKey.json"
    if ((Test-Path -LiteralPath $pixalQuality) -or (Test-Path -LiteralPath $pixalOverlap)) { throw 'Preserve existing audit' }
    & $pixalPython 'scripts\audit_pixal_mesh_quality.py' $pixalBake.model --output $pixalQuality --require-clean
    if ($LASTEXITCODE -ne 0) { throw 'Export geometry audit failed' }
    & $pixalPython 'scripts\audit_pixal_uv_overlap.py' $pixalBake.model --output $pixalOverlap
    if ($LASTEXITCODE -ne 0) { throw 'Overlap audit failed' }
}
$pixalBasenames = @($pixalBakes | ForEach-Object { [System.IO.Path]::GetFileName($_.model) })
& 'D:\shujuku\nodejs\node.exe' 'tmp\render-audit-20261008.cjs' @pixalBasenames
if ($LASTEXITCODE -ne 0) { throw 'Control renders failed' }
Write-Output 'Round4 controls complete; inspect numerical tradeoffs and actual images before promotion'
