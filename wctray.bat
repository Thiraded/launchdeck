@echo off
REM wctray — works in the system tray (no console window)
set "PYW=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"
cd /d "%~dp0"
start "" "%PYW%" "%~dp0wctray.py"
