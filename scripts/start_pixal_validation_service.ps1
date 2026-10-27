param([string]$Label = 'round3-memory-final-20261009', [switch]$SavePrediction)
$pixalRoot = 'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install'
$pixalPython = Join-Path $pixalRoot 'python_embeded\python.exe'
$pixalCompiler = Join-Path $pixalRoot 'python_embeded\Lib\site-packages\triton\backends\nvidia\bin\ptxas.exe'
$pixalWorkspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not (Test-Path -LiteralPath $pixalCompiler)) { throw 'Local ptxas compiler is missing' }
# The installed Windows Triton build derives the setting from ptxas.exe.
[Environment]::SetEnvironmentVariable('TRITON_PTXAS.EXE_PATH', $pixalCompiler, 'Process')
[Environment]::SetEnvironmentVariable('TRITON_PTXAS_PATH', $pixalCompiler, 'Process')
& $pixalCompiler --version
if ($LASTEXITCODE -ne 0) { throw 'Local compiler version check failed' }
& $pixalPython -c 'from triton import knobs; print(knobs.nvidia.ptxas)'
if ($LASTEXITCODE -ne 0) { throw 'Triton compiler lookup failed' }
$pixalLog = Join-Path $pixalWorkspace "tmp\comfy-general-$Label.log"
$pixalErrorLog = Join-Path $pixalWorkspace "tmp\comfy-general-$Label.err.log"
if ((Test-Path -LiteralPath $pixalLog) -or (Test-Path -LiteralPath $pixalErrorLog)) { throw 'Use a new label to preserve existing logs' }
$pixalArguments = @('-u','main.py','--listen','127.0.0.1','--port','8188','--lowvram','--use-pytorch-cross-attention','--disable-all-custom-nodes','--whitelist-custom-nodes','ComfyUI-Trellis2-GGUF')
if ($SavePrediction) { $pixalArguments += 'Pixal3DValidationSnapshot' }
$pixalProcess = Start-Process -FilePath $pixalPython -ArgumentList $pixalArguments -WorkingDirectory (Join-Path $pixalRoot 'ComfyUI') -WindowStyle Hidden -PassThru -RedirectStandardOutput $pixalLog -RedirectStandardError $pixalErrorLog
$pixalProcess.Id | Set-Content (Join-Path $pixalWorkspace "tmp\comfy-general-$Label.pid")
Write-Output "Started owned validation service PID $($pixalProcess.Id)"
