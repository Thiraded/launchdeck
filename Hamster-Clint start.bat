@echo off
setlocal
set "APPDIR=D:\projects\HamsterWorld\backoffice"
set "PORT=5173"

if not exist "%APPDIR%" (
  echo [Hamster Client] %APPDIR% NOT FOUND (drive missing?).
  echo Window left open for inspection.
  pause
  exit /b 1
)

if not exist "%APPDIR%\package.json" (
  echo [Hamster Client] package.json not found in %APPDIR%
  echo Window left open for inspection.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [Hamster Client] npm not found in PATH.
  echo Window left open for inspection.
  pause
  exit /b 1
)

start "Hamster Client" cmd /k "cd /d \"%APPDIR%\" && npm run dev -- --host 0.0.0.0 --port %PORT% --strictPort"
echo [Hamster Client] started on http://localhost:%PORT%
