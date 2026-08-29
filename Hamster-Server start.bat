@echo off
setlocal
set "APPDIR=D:\projects\HamsterWorld\server"

if not exist "%APPDIR%" (
  echo [Hamster Server] %APPDIR% NOT FOUND (drive missing?).
  echo Window left open for inspection.
  pause
  exit /b 1
)

if not exist "%APPDIR%\package.json" (
  echo [Hamster Server] package.json not found in %APPDIR%
  echo Window left open for inspection.
  pause
  exit /b 1
)

start "Hamster Server" cmd /k "cd /d \"%APPDIR%\" && call npm run dev"
echo [Hamster Server] started.
