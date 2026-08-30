@echo off
setlocal
set "APPDIR=D:\projects\Hamsquest"

if not exist "%APPDIR%" goto :no_appdir
if not exist "%APPDIR%\package.json" goto :no_pkg

pushd "%APPDIR%"
start "Hamsterquest" cmd /k "call npm run dev"
popd
echo [Hamsterquest] started.
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
