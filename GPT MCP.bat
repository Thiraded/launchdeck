@echo off
set "PROJECT=D:\Midnight-Rider"
if not exist "%PROJECT%" (
  echo [GPT MCP] %PROJECT% not found.
  pause
  exit /b 1
)
cd /d %PROJECT%
REM Single window: this bat's own console becomes the npx host. No nested
REM `start` so we don't get an extra "outer wrapper" window that does
REM nothing after the bat returns. `title` names the window so the user
REM sees "GPT MCP Inspector" in the taskbar.
title GPT MCP Inspector
cls
npx -y @modelcontextprotocol/inspector npx -y @modelcontextprotocol/server-filesystem %PROJECT%
