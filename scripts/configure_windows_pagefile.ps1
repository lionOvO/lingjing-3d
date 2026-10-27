$ErrorActionPreference = 'Stop'

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell.exe -Verb RunAs -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath)
    exit
}

# Keep the pagefile on the internal D: drive. Do not place it on the external
# E: drive because removable disks may be unavailable during Windows startup.
$computer = Get-CimInstance Win32_ComputerSystem
if ($computer.AutomaticManagedPagefile) {
    Set-CimInstance -InputObject $computer -Property @{ AutomaticManagedPagefile = $false } | Out-Null
}
$existing = Get-CimInstance Win32_PageFileSetting -Filter "Name='D:\\pagefile.sys'" -ErrorAction SilentlyContinue
if ($existing) {
    Set-CimInstance -InputObject $existing -Property @{ InitialSize = [uint32]24576; MaximumSize = [uint32]32768 } | Out-Null
} else {
    New-CimInstance -Namespace root/cimv2 -ClassName Win32_PageFileSetting -Property @{ Name = 'D:\pagefile.sys'; InitialSize = [uint32]24576; MaximumSize = [uint32]32768 } | Out-Null
}

Write-Host '已配置 D:\pagefile.sys：初始 24576 MB，最大 32768 MB。'
Write-Host '请重启 Windows，然后重新启动 ComfyUI。'
