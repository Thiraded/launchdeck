@echo off
title OmniRoute Web Gateway
echo.
echo ====================================
echo   OmniRoute - Web Gateway (Brave)
echo ====================================
echo.
Invoke-Item "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Brave Apps\OmniRoute AI Gateway.lnk"  || start "" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Brave Apps\OmniRoute AI Gateway.lnk"
echo Gateway app launch requested.
echo Window left open for inspection.
pause
