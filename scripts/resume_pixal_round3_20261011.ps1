$ErrorActionPreference = 'Stop'
$pixalWorkspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pixalRoot = 'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install'
$pixalCustomNodes = Join-Path $pixalRoot 'ComfyUI\custom_nodes'
$pixalPython = Join-Path $pixalRoot 'python_embeded\python.exe'
$pixalLabel = 'round3-sparse-resume-20261011'
Set-Location -LiteralPath $pixalWorkspace

# Refuse to reuse or stop an unowned inference service.
$pixalListener = Get-NetTCPConnection -LocalPort 8188 -State Listen -ErrorAction SilentlyContinue
if ($pixalListener) { throw "Port 8188 is already owned by PID $($pixalListener.OwningProcess)" }
$pixalHashes = Get-Content -LiteralPath 'tmp\pixal-round3-source-sha-20261009.json' -Raw | ConvertFrom-Json
foreach ($pixalEntry in $pixalHashes) {
    if ((Get-FileHash -LiteralPath $pixalEntry.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $pixalEntry.sha256) { throw "Installed source changed: $($pixalEntry.path)" }
}
foreach ($pixalCase in @('person','robot','helmet')) {
    if (Test-Path -LiteralPath "tmp\pixal-round3-sparse-resume-$pixalCase-prediction-20261011.npz") { throw 'Preserve existing neural prediction; choose a new run version' }
}
$pixalSource = (Resolve-Path -LiteralPath (Join-Path $pixalCustomNodes 'Pixal3DValidationSnapshot.disabled')).Path
$pixalTarget = [System.IO.Path]::GetFullPath((Join-Path $pixalCustomNodes 'Pixal3DValidationSnapshot'))
if ([System.IO.Path]::GetDirectoryName($pixalSource) -ne $pixalCustomNodes -or [System.IO.Path]::GetDirectoryName($pixalTarget) -ne $pixalCustomNodes) { throw 'Diagnostic paths outside intended custom_nodes directory' }
if (Test-Path -LiteralPath $pixalTarget) { throw 'Do not overwrite an active diagnostic plugin' }
Move-Item -LiteralPath $pixalSource -Destination $pixalTarget
Copy-Item -LiteralPath 'scripts\comfy_pixal_validation_snapshot.py' -Destination (Join-Path $pixalTarget '__init__.py')
& (Join-Path $PSScriptRoot 'start_pixal_validation_service.ps1') -Label $pixalLabel -SavePrediction
$pixalPid = [int](Get-Content -LiteralPath "tmp\comfy-general-$pixalLabel.pid")

$pixalReady = $false
for ($pixalAttempt=0; $pixalAttempt -lt 45; $pixalAttempt++) {
    try {
        $pixalQueue = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/queue' -TimeoutSec 2
        $pixalSchema = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/object_info' -TimeoutSec 2
        if ($pixalSchema.PSObject.Properties.Name -contains 'PixalValidationSnapshot') { $pixalReady=$true; break }
    } catch { }
    Start-Sleep -Seconds 2
}
if (-not $pixalReady) { throw "Owned service $pixalPid has not become ready; no workflow submitted" }
Write-Output "Ready; validating three fresh business graphs on PID $pixalPid"
& $pixalPython -u 'scripts\run_pixal_round2_benchmarks.py' --pid $pixalPid --log "tmp\comfy-general-$pixalLabel.log" --label-prefix '20261011-round3-sparse-resume' --metrics-prefix 'pixal-full-round3-sparse-resume' --require-clean --save-prediction
if ($LASTEXITCODE -ne 0) { throw 'Full validation failed; preserve logs for diagnosis' }
