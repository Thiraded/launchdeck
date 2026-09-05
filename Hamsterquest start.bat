@echo off
setlocal
set "APPDIR=D:\projects\Hamsquest"

title Hamsterquest start

if not exist "%APPDIR%\" goto :no_appdir
if not exist "%APPDIR%\package.json" goto :no_pkg

cd /d "%APPDIR%"
cls
cmd /k "npm run dev"
exit /b 0

:no_appdir
echo [Hamsterquest] %APPDIR% NOT FOUND -- drive missing.
echo Window left open for inspection.
pause
exit /b 1

:no_pkg
echo [Hamsterquest] package.json not found in %APPDIR%
echo Window left open for inspection.
pause
exit /b 1
