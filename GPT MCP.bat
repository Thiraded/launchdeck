@echo off
title GPT MCP Inspector
echo.
echo ====================================
echo   GPT MCP - Inspector (visible)
echo ====================================
echo.
set "PROJECT=D:\Midnight-Rider"
echo Running MCP Inspector for %PROJECT%...
echo Window left open so work-combo can detect/kill it.
cmd /k "title bg-gptweb-inspector && npx -y @modelcontextprotocol/inspector npx -y @modelcontextprotocol/server-filesystem \"%PROJECT%\""
echo Inspector closed.
pause
