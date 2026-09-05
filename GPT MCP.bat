@echo off
setlocal
set "NAME=GPT MCP"
set "APPDIR=D:\Midnight-Rider"

if not exist "%APPDIR%\" goto :no_appdir

title [%NAME%] Inspector

cd /d "%APPDIR%"
cls
cmd /k "npx -y @modelcontextprotocol/inspector npx -y @modelcontextprotocol/server-filesystem "%APPDIR%""
exit /b 0

:no_appdir
title [%NAME%] ERROR
echo [%NAME%] %APPDIR% NOT FOUND -- drive missing.
echo Window left open for inspection.
pause
exit /b 1
