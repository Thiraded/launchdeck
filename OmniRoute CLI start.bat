@echo off
title OmniRoute CLI
echo.
echo ====================================
echo   OmniRoute - CLI (hidden output)
echo ====================================
echo.
echo CLI runs in background; log: %LOCALAPPDATA%\bg-launcher-logs\bg-omniroute-cli.log
echo.
powershell.exe -NoProfile -NonInteractive -Command "$logDir = Join-Path $env:LOCALAPPDATA 'bg-launcher-logs'; New-Item -ItemType Directory -Force -Path $logDir | Out-Null; $oLog = Join-Path $logDir 'bg-omniroute-cli.log'; $inner = 'title bg-omniroute-cli && omniroute > \"' + $oLog + '\" 2>&1'; Start-Process cmd.exe -ArgumentList ('/d /s /c \"' + $inner + '\"') -WindowStyle Hidden"
echo CLI started.
echo Window left open for inspection.
pause
