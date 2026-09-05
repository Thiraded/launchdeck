@echo off
setlocal
set "LOGDIR=%LOCALAPPDATA%\bg-launcher-logs"
set "OLOG=%LOGDIR%\bg-omniroute-cli.log"

mkdir "%LOGDIR%" 2>nul

title OmniRoute CLI start
cls
echo CLI output log: %OLOG%
echo.
cmd /k "omniroute > \"%OLOG%\" 2>&1"
exit /b 0
