@echo off
title OmniRoute CLI
echo.
echo ====================================
echo   OmniRoute - CLI (visible)
echo ====================================
echo.
set "LOGDIR=%LOCALAPPDATA%\bg-launcher-logs"
mkdir "%LOGDIR%" 2>nul
set "OLOG=%LOGDIR%\bg-omniroute-cli.log"
echo CLI output log: %OLOG%
echo.
start "OmniRoute CLI" cmd /k "omniroute > \"%OLOG%\" 2>&1"
echo CLI launch requested.
echo Window left open for inspection.
