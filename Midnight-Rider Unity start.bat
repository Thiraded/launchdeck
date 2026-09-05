@echo off
setlocal
set "PROJECT=D:\Midnight-Rider"
set "HUB=C:\Program Files\Unity Hub\Unity Hub.exe"

if not exist "%PROJECT%\" goto :no_project
if not exist "%HUB%" goto :no_hub

title Midnight-Rider Unity start
start "" "%HUB%" -- --projectPath "%PROJECT%"
echo Unity Hub launched for %PROJECT%.
echo Window left open for inspection.
pause
exit /b 0

:no_project
echo [Midnight-Rider Unity] %PROJECT% NOT FOUND -- drive missing.
echo Window left open for inspection.
pause
exit /b 1

:no_hub
echo [Midnight-Rider Unity] Unity Hub not found: %HUB%
echo Window left open for inspection.
pause
exit /b 1
