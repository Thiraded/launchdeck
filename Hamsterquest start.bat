@echo off
title wc-hamsterquest
set "APPDIR=D:\projects\Hamsquest"

if not exist "%APPDIR%" (
  echo [wc-hamsterquest] %APPDIR% NOT FOUND (drive missing?).
  echo Window left open for inspection.
  pause
  exit /b 1
)

if not exist "%APPDIR%\package.json" (
  echo [wc-hamsterquest] package.json not found in %APPDIR%
  echo Window left open for inspection.
  pause
  exit /b 1
)

start "" cmd /k "cd /d \"%APPDIR%\" && call npm run dev"
echo [wc-hamsterquest] dev launch requested.
echo Open the new cmd window to watch the app boot.
