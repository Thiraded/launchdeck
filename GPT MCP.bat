@echo off
title GPT MCP Inspector
set "PROJECT=D:\Midnight-Rider"
if not exist "%PROJECT%" (
  echo [GPT MCP] %PROJECT% not found.
  pause
  exit /b 1
)
cd /d %PROJECT%
cls
npx -y @modelcontextprotocol/inspector npx -y @modelcontextprotocol/server-filesystem %PROJECT%
