@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  python -u "%~dp0scripts\start_local.py" %*
) else (
  py -3 -u "%~dp0scripts\start_local.py" %*
)
set "LAUNCH_EXIT_CODE=%ERRORLEVEL%"
if not "%LINGJING_NO_PAUSE%"=="1" pause
exit /b %LAUNCH_EXIT_CODE%
