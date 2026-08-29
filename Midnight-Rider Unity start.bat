@echo off
title Midnight-Rider Unity
set "PROJECT=D:\Midnight-Rider"
echo.
echo ================================
echo   Midnight-Rider - Unity Hub
echo ================================
echo.
start "" "C:\Program Files\Unity Hub\Unity Hub.exe" -- --projectPath "%PROJECT%"
echo Unity Hub launched for %PROJECT%.
echo Window left open for inspection.
pause
