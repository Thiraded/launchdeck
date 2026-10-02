@echo off
REM The launchdeck command always opens the tray dashboard UI.
set "PYW=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"
cd /d "%~dp0"
start "" "%PYW%" "%~dp0launchdeck_dashboard.py" %*
