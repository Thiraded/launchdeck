@echo off
setlocal
set "APPDIR=D:\projects\HamsterWorld\backoffice"
set "PORT=5175"

if not exist "%APPDIR%\" goto :no_appdir
if not exist "%APPDIR%\package.json" goto :no_pkg

cd /d "%APPDIR%"
cls
cmd /k "npm run dev -- --host 0.0.0.0 --port %PORT% --strictPort"
exit /b 0

:no_appdir
echo [Hamster Client] %APPDIR% NOT FOUND -- drive missing.
echo Window left open for inspection.
pause
exit /b 1

:no_pkg
echo [Hamster Client] package.json not found in %APPDIR%
echo Window left open for inspection.
pause
exit /b 1
