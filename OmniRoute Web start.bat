@echo off
setlocal
set "GATEWAY_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Brave Apps\OmniRoute AI Gateway.lnk"

if not exist "%GATEWAY_LNK%" goto :no_lnk

title OmniRoute Web start
start "" "%GATEWAY_LNK%"
echo Gateway app launch requested.
echo Window left open for inspection.
pause
exit /b 0

:no_lnk
echo [OmniRoute Web] Shortcut not found: %GATEWAY_LNK%
echo Window left open for inspection.
pause
exit /b 1
