<##
.SYNOPSIS
  Resolve Docker independently of the shell's inherited PATH and report daemon state.
.##>
$ErrorActionPreference = 'Continue'
$candidates = @(
  '%USERPROFILE%\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe',
  'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
)
$docker = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $docker) {
  Write-Error 'Docker CLI 未找到。请确认 Docker Desktop 已安装。'
  exit 9009
}
Write-Host "Docker CLI: $docker"
& $docker --version
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $docker info *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Warning 'Docker CLI 已找到，但 Docker Desktop 引擎未运行。请先启动 Docker Desktop。'
  exit 1
}
Write-Host 'Docker 引擎: running'
& $docker compose version
exit $LASTEXITCODE
