@echo off
setlocal
title Hermes

set "HERMES_EXE=%LOCALAPPDATA%\hermes\bin\hermes.exe"
if not exist "%HERMES_EXE%" set "HERMES_EXE=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\hermes.exe"

if exist "%HERMES_EXE%" (
    start "" "%HERMES_EXE%" %*
    exit /b 0
)

where hermes >nul 2>nul
if not errorlevel 1 (
    start "" hermes %*
    exit /b 0
)

echo Hermes executable not found.
echo Checked: %LOCALAPPDATA%\hermes\bin\hermes.exe
pause
exit /b 1