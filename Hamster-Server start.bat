@echo off
setlocal
set "APPDIR=D:\projects\HamsterWorld\server"

if not exist "%APPDIR%" goto :no_appdir
if not exist "%APPDIR%\package.json" goto :no_pkg

pushd "%APPDIR%"
start "Hamster Server" cmd /k "call npm run dev"
popd
echo [Hamster Server] started.
exit /b 0

:no_appdir
echo [Hamster Server] %APPDIR% NOT FOUND -- drive missing.
echo Window left open for inspection.
pause
exit /b 1

:no_pkg
echo [Hamster Server] package.json not found in %APPDIR%
echo Window left open for inspection.
pause
exit /b 1
