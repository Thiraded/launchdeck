@echo off
setlocal
set "PROJECT=D:\Midnight-Rider"
set "CODE=%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"

if not exist "%PROJECT%\" goto :no_project
if not exist "%CODE%" goto :no_code

title Midnight-Rider VSCode start
start "" "%CODE%" "%PROJECT%"
echo VS Code launched for %PROJECT%.
echo Window left open for inspection.
pause
exit /b 0

:no_project
echo [Midnight-Rider VSCode] %PROJECT% NOT FOUND -- drive missing.
echo Window left open for inspection.
pause
exit /b 1

:no_code
echo [Midnight-Rider VSCode] VS Code not found: %CODE%
echo Window left open for inspection.
pause
exit /b 1
