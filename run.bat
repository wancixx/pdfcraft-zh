@echo off
REM pdfcraft-zh launcher -- Windows double-click entry point.
REM Hands over to run.ps1 (PowerShell ships with Windows, so it always runs).

setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
set ERR=%ERRORLEVEL%

echo.
if "%ERR%"=="0" (
    echo Done.
) else (
    echo Exit code: %ERR%
)
pause
exit /b %ERR%
