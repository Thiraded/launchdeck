@echo off
title OmniRoute Web Gateway
echo.
echo ====================================
echo   OmniRoute - Web Gateway (Brave)
echo ====================================
echo.
set "GATEWAY_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Brave Apps\OmniRoute AI Gateway.lnk"
if exist "%GATEWAY_LNK%" (
  start "" "%GATEWAY_LNK%"
) else (
  echo [OmniRoute Web] Shortcut not found: %GATEWAY_LNK%
  echo Window left open for inspection.
  pause
  exit /b 1
)
echo Gateway app launch requested.
echo Window left open for inspection.
