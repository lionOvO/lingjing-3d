$ErrorActionPreference = 'Stop'
$pixalWorkspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pixalPython = 'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\python.exe'
foreach ($pixalCase in @('robot', 'helmet')) {
    $pixalLog = Join-Path $pixalWorkspace "tmp\pixal-round5-clean-after-remesh-$pixalCase-20261019.log"
    if (Test-Path -LiteralPath $pixalLog) { throw 'Preserve previous trial log' }
    & $pixalPython -u (Join-Path $PSScriptRoot 'replay_pixal_postprocess_20261019.py') --snapshot (Join-Path $pixalWorkspace "tmp\pixal-round3-sparse-resume-$pixalCase-prediction-20261011.npz") --case $pixalCase --label "round5-clean-after-remesh-$pixalCase-20261019" --floaters-after-remesh *> $pixalLog
    if ($LASTEXITCODE -ne 0) { throw "Postprocess trial failed for $pixalCase" }
    Write-Output "Completed $pixalCase with original saved neural prediction; floaters cleaned after remeshing"
}
