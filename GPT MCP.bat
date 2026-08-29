@echo off
title GPT MCP Inspector
echo.
echo ====================================
echo   GPT MCP - Inspector (visible)
echo ====================================
echo.
set "PROJECT=D:\Midnight-Rider"
if not exist "%PROJECT%" (
  echo [GPT MCP] %PROJECT% not found.
  echo Window left open for inspection.
  pause
  exit /b 1
)
echo Running MCP Inspector for %PROJECT%...
start "GPT MCP Inspector" cmd /k "cd /d %PROJECT% && npx -y @modelcontextprotocol/inspector npx -y @modelcontextprotocol/server-filesystem %PROJECT%"
echo Inspector launch requested.
