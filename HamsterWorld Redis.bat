@echo off
setlocal

:: HamsterWorld Redis control panel (Docker Desktop backend)
:: - Shows current state (running / stopped)
:: - Spacebar toggles auto-start on Docker Desktop launch
:: - Enter / arrows choose action: Start | Stop | Restart | Open shell | Exit
:: - q / Esc quits

set "CONTAINER=hamsterworld-redis"
set "REDIS_HOST=127.0.0.1"
set "REDIS_PORT=6379"

:loop
cls
echo ============================================================
echo   HamsterWorld Redis  (Docker : hamsterworld-redis)
echo ============================================================
echo.

:: --- state checks (each call, fresh) ---
set "STATE=stopped"
for /f %%S in ('powershell -NoProfile -Command "(Get-CimInstance Win32_Process -Filter 'Name=\"redis-server.exe\"' -ErrorAction SilentlyContinue) -ne $null" 2^>nul') do set "STATE=running"

:: Detect docker container state
set "DOCKER_STATE="
for /f %%X in ('docker inspect -f "{{.State.Running}}" %CONTAINER% 2^>nul') do set "DOCKER_STATE=%%X"

echo   Container state : %DOCKER_STATE%
echo   Local TCP 6379  : %STATE%
echo.

if /i "%DOCKER_STATE%"=="true" goto :menu_running
goto :menu_stopped

:menu_running
echo   [Enter / ->]  Stop Redis
echo   [R]          Restart Redis
echo   [S]          Open redis-cli shell
echo   [T]          Toggle auto-start with Docker Desktop
echo   [Q / Esc]    Quit
echo.
choice /c RSQ /n /m "Choose:"
set "ACT=%errorlevel%"
if %ACT%==1 goto :do_restart
if %ACT%==2 goto :do_shell
if %ACT%==3 goto :do_toggle_autostart
goto :loop

:menu_stopped
echo   [Enter / ->]  Start Redis
echo   [T]          Toggle auto-start with Docker Desktop
echo   [Q / Esc]    Quit
echo.
choice /c SQ /n /m "Choose:"
set "ACT=%errorlevel%"
if %ACT%==1 goto :do_start
if %ACT%==2 goto :do_toggle_autostart
goto :loop

:do_start
echo.
echo Starting %CONTAINER%...
docker start %CONTAINER%
echo.
echo Verifying with redis-cli...
docker exec %CONTAINER% redis-cli -h %REDIS_HOST% -p %REDIS_PORT% ping
echo.
pause
goto :loop

:do_restart
echo.
echo Restarting %CONTAINER%...
docker restart %CONTAINER%
echo.
docker exec %CONTAINER% redis-cli -h %REDIS_HOST% -p %REDIS_PORT% ping
echo.
pause
goto :loop

:do_stop
echo.
echo Stopping %CONTAINER%...
docker stop %CONTAINER%
echo.
pause
goto :loop

:do_shell
echo.
echo Opening redis-cli shell inside %CONTAINER% (type 'exit' to leave)...
docker exec -it %CONTAINER% redis-cli -h %REDIS_HOST% -p %REDIS_PORT%
goto :loop

:do_toggle_autostart
echo.
echo Auto-start is currently controlled by Docker's --restart flag (unless-stopped).
echo If the container is stopped, this option will toggle it on/off via update.
powershell -NoProfile -Command ^
    "$name='%CONTAINER%'; ^
     $cur = (docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' $name 2>$null).Trim(); ^
     if ($cur -eq 'unless-stopped') { ^
        docker update --restart no $name | Out-Null; ^
        Write-Host 'Auto-start: OFF (container will NOT restart on Docker reboot)' -Foreground Yellow ^
     } else { ^
        docker update --restart unless-stopped $name | Out-Null; ^
        Write-Host 'Auto-start: ON (container restarts unless manually stopped)' -Foreground Green ^
     }"
echo.
pause
goto :loop