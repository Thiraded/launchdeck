@echo off
title GPT Web MCP
echo.
echo ====================================
echo   GPT Web MCP - Tunnel Client (visible)
echo ====================================
echo.
set "TUNNELDIR=D:\_tunnel-client"
echo Running tunnel-client for %TUNNELDIR%...
echo Window left open so work-combo can detect/kill it.
cmd /k "title bg-gptweb-tunnel && cd /d %TUNNELDIR% && .\tunnel-client.exe run --profile-file .\chatgpt-mcp-workshop.yaml --control-plane.api-key \"file:%TUNNELDIR%\runtime-api-key.txt\""
echo Tunnel client closed.
pause
