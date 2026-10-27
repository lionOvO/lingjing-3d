$ErrorActionPreference = 'Stop'
$pixalWorkspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pixalRoot = 'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install'
$pixalPython = Join-Path $pixalRoot 'python_embeded\python.exe'
$pixalCustomNodes = Join-Path $pixalRoot 'ComfyUI\custom_nodes'
Set-Location -LiteralPath $pixalWorkspace

# Require all three audited full generations before any UV experiments.
& '.\.venv\Scripts\python.exe' 'scripts\archive_pixal_round3_validation.py'
if ($LASTEXITCODE -ne 0) { throw 'Three-category provenance validation failed' }
& '.\.venv\Scripts\python.exe' 'scripts\verify_pixal_robot_raw_snapshot.py'
if ($LASTEXITCODE -ne 0) { throw 'Preserved robot geometry comparison failed' }
$pixalQueue = Invoke-RestMethod -Uri 'http://127.0.0.1:8188/queue' -TimeoutSec 5
if ($pixalQueue.queue_running.Count -ne 0 -or $pixalQueue.queue_pending.Count -ne 0) { throw 'Do not stop a nonempty inference queue' }
$pixalPid = [int](Get-Content -LiteralPath 'tmp\comfy-general-round3-sparse-resume-20261011.pid')
$pixalProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$pixalPid"
if (-not $pixalProcess -or $pixalProcess.ExecutablePath -ne $pixalPython -or $pixalProcess.CommandLine -notlike '*main.py --listen 127.0.0.1 --port 8188*') { throw 'Inference PID no longer matches owned service' }
Stop-Process -Id $pixalPid
Write-Output "Stopped owned inference service $pixalPid; GPU bake trials now run separately"
$pixalSource = (Resolve-Path -LiteralPath (Join-Path $pixalCustomNodes 'Pixal3DValidationSnapshot')).Path
$pixalTarget = [System.IO.Path]::GetFullPath((Join-Path $pixalCustomNodes 'Pixal3DValidationSnapshot.disabled'))
if ([System.IO.Path]::GetDirectoryName($pixalSource) -ne $pixalCustomNodes -or [System.IO.Path]::GetDirectoryName($pixalTarget) -ne $pixalCustomNodes) { throw 'Diagnostic paths outside intended directory' }
if (Test-Path -LiteralPath $pixalTarget) { throw 'Preserve an existing disabled diagnostic plugin' }
Move-Item -LiteralPath $pixalSource -Destination $pixalTarget

& $pixalPython -u 'scripts\compare_pixal_fixed_geometry_uv.py'
if ($LASTEXITCODE -ne 0) { throw 'Fixed geometry UV trials failed; preserve partial outputs' }
& $pixalPython -u 'scripts\compare_pixal_surface_colors.py'
if ($LASTEXITCODE -ne 0) { throw 'Surface color comparison failed; preserve evidence' }
$pixalTrials = Get-Content -LiteralPath 'tmp\pixal-fixed-geometry-uv-comparison-20261011.json' -Raw | ConvertFrom-Json
foreach ($pixalTrial in $pixalTrials) {
    $pixalOverlapPath = "tmp\pixal-uv-overlap-$($pixalTrial.case)-$($pixalTrial.variant)-20261011.json"
    if (Test-Path -LiteralPath $pixalOverlapPath) { throw 'Preserve existing UV overlap audit' }
    & $pixalPython 'scripts\audit_pixal_uv_overlap.py' $pixalTrial.model --output $pixalOverlapPath
    if ($LASTEXITCODE -ne 0) { throw 'UV overlap audit failed' }
}
& '.\.venv\Scripts\python.exe' 'scripts\update_pixal_round3_viewer.py'
if ($LASTEXITCODE -ne 0) { throw 'Viewer inventory update failed' }

$pixalPreview = Get-NetTCPConnection -LocalPort 18765 -State Listen -ErrorAction SilentlyContinue
if (-not $pixalPreview) {
    $pixalPreviewProcess = Start-Process -FilePath (Join-Path $pixalWorkspace '.venv\Scripts\python.exe') -ArgumentList @('-u','tmp\texture-audit-server-20261008.py') -WorkingDirectory $pixalWorkspace -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $pixalWorkspace 'tmp\texture-audit-server-round3-20261011.log') -RedirectStandardError (Join-Path $pixalWorkspace 'tmp\texture-audit-server-round3-20261011.err.log')
    $pixalPreviewProcess.Id | Set-Content -LiteralPath 'tmp\texture-audit-server-round3-20261011.pid'
    Start-Sleep -Seconds 2
}
$pixalPreviewPage = Invoke-WebRequest -Uri 'http://127.0.0.1:18765/tmp/texture-audit-20261008.html' -TimeoutSec 5
if ($pixalPreviewPage.StatusCode -ne 200) { throw 'Expected local preview unavailable' }
$pixalBasenames = @()
foreach ($pixalCase in @('person','robot','helmet')) {
    $pixalMetric = Get-Content -LiteralPath "tmp\pixal-full-round3-sparse-resume-$pixalCase-metrics.json" -Raw | ConvertFrom-Json
    $pixalBasenames += [System.IO.Path]::GetFileName($pixalMetric[0].model)
}
foreach ($pixalTrial in $pixalTrials) { $pixalBasenames += [System.IO.Path]::GetFileName($pixalTrial.model) }
& 'D:\shujuku\nodejs\node.exe' 'tmp\render-audit-20261008.cjs' @pixalBasenames
if ($LASTEXITCODE -ne 0) { throw 'Multi-view render failed' }
Write-Output 'Numerical and render outputs complete; actual visual inspection still required'
