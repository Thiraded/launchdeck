@echo off
set "LC_SELF=%~f0"
if /i "%~1"=="__bg__" goto :main
powershell.exe -NoProfile -NonInteractive -EncodedCommand UwB0AGEAcgB0AC0AUAByAG8AYwBlAHMAcwAgAGMAbQBkAC4AZQB4AGUAIAAtAEEAcgBnAHUAbQBlAG4AdABMAGkAcwB0ACAAQAAoACcALwBkACcALAAnAC8AYwAnACwAKAAnACIAJwAgACsAIAAkAGUAbgB2ADoATABDAF8AUwBFAEwARgAgACsAIAAnACIAIABfAF8AYgBnAF8AXwAnACkAKQAgAC0AVwBpAG4AZABvAHcAUwB0AHkAbABlACAASABpAGQAZABlAG4A
exit

:main

set "PROJECT=D:\Midnight-Rider"

echo.
echo ================================
echo       Midnight-Rider Launcher
echo ================================
echo.

echo [1/2] Opening Unity...
start "" "C:\Program Files\Unity Hub\Unity Hub.exe" -- --projectPath "%PROJECT%"

echo [2/2] Opening VS Code...
cmd /c start "" "%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe" "%PROJECT%"

echo.
echo Goodbye!

exit