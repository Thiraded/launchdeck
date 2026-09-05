@echo off
set "PY=%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python.exe"
cd /d "%~dp0"
"%PY%" "%~dp0wc.py"
