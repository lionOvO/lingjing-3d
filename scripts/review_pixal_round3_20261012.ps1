$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
& 'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\python.exe' 'scripts\render_pixal_review_sheets.py'
if ($LASTEXITCODE -ne 0) { throw 'Review sheet generation failed' }
& 'D:\shujuku\nodejs\node.exe' 'scripts\smoke_pixal_round3_viewers.cjs'
if ($LASTEXITCODE -ne 0) { throw 'Viewer smoke validation failed' }
