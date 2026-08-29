@echo off
setlocal
set "APPDIR=D:\projects\Hamsquest"

if not exist "%APPDIR%" (
  echo [Hamsterquest] %APPDIR% NOT FOUND (drive missing?).
  echo Window left open for inspection.
  pause
  exit /b 1
)

if not exist "%APPDIR%\package.json" (
  echo [Hamsterquest] package.json not found in %APPDIR%
  echo Window left open for inspection.
  pause
  exit /b 1
)

start "Hamsterquest" cmd /k "cd /d \"%APPDIR%\" && call npm run dev"
echo [Hamsterquest] started.
