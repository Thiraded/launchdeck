@echo off
title wc-hamster-clint
set "APPDIR=D:\projects\HamsterWorld\backoffice"
set "PORT=5173"

if not exist "%APPDIR%" (
  echo [wc-hamster-clint] %APPDIR% NOT FOUND (drive missing?).
  echo Window left open for inspection.
  pause
  exit /b 1
)

if not exist "%APPDIR%\package.json" (
  echo [wc-hamster-clint] package.json not found in %APPDIR%
  echo Window left open for inspection.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [wc-hamster-clint] npm not found in PATH.
  echo Window left open for inspection.
  pause
  exit /b 1
)

start "" cmd /k "cd /d \"%APPDIR%\" && npm run dev -- --host 0.0.0.0 --port %PORT% --strictPort"
echo [wc-hamster-clint] dev launch requested on http://localhost:%PORT%
echo Open the new cmd window to watch Vite boot.
