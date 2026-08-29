@echo off
title GPT Web MCP
echo.
echo ====================================
echo   GPT Web MCP - Tunnel Client (visible)
echo ====================================
echo.
set "TUNNELDIR=D:\_tunnel-client"
if not exist "%TUNNELDIR%" (
  echo [GPT Web MCP] %TUNNELDIR% not found.
  echo Window left open for inspection.
  pause
  exit /b 1
)
echo Running tunnel-client for %TUNNELDIR%...
start "GPT Web MCP" cmd /k "cd /d %TUNNELDIR% && .\tunnel-client.exe run --profile-file .\chatgpt-mcp-workshop.yaml --control-plane.api-key file:%TUNNELDIR%\runtime-api-key.txt"
echo Tunnel client launch requested.
