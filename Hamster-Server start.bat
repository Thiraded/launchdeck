@echo off
title wc-hamster-server
set "APPDIR=D:\projects\HamsterWorld\server"

if not exist "%APPDIR%" (
  echo [wc-hamster-server] %APPDIR% NOT FOUND (drive missing?).
  echo Window left open for inspection.
  pause
  exit /b 1
)

if not exist "%APPDIR%\package.json" (
  echo [wc-hamster-server] package.json not found in %APPDIR%
  echo Window left open for inspection.
  pause
  exit /b 1
)

start "" cmd /k "cd /d \"%APPDIR%\" && call npm run dev"
echo [wc-hamster-server] dev launch requested.
echo Open the new cmd window to watch the server boot.
