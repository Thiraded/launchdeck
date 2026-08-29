@echo off
title Midnight-Rider VSCode
set "PROJECT=D:\Midnight-Rider"
echo.
echo ================================
echo   Midnight-Rider - VS Code
echo ================================
echo.
cmd /c start "" "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" "%PROJECT%"
echo VS Code launched for %PROJECT%.
echo Window left open for inspection.
pause
