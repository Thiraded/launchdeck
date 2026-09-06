# Launcher .bat template — single window, INLINE (unified 2026-09-05)

All work launchers follow the Hamster-Clint shape: ONE console window,
real command INLINE via `cmd /k`. NEVER a nested `start "X" cmd /k` —
that shape opened 2 windows and split kill/hide token coverage
(the Clint-vs-Server split from the PARK-IN-^ trial, see `tray.md`).

## Dev-server works

```bat
@echo off
setlocal
set "APPDIR=D:\path\to\app"

title <works.json label>      :: exact label, early (see Titles below)

if not exist "%APPDIR%\" goto :no_appdir
if not exist "%APPDIR%\package.json" goto :no_pkg

cd /d "%APPDIR%"
cls
cmd /k "<real command>"
exit /b 0

:no_appdir
echo [<Name>] %APPDIR% NOT FOUND -- drive missing.
echo Window left open for inspection.
pause
exit /b 1

:no_pkg
echo [<Name>] package.json not found in %APPDIR%
echo Window left open for inspection.
pause
exit /b 1
```

Rules: guards via `goto :label`, never `(...)` blocks — a `(`/`)`
inside an `echo` within a block breaks cmd parsing silently
(`. was unexpected at this time`, exit 255, nothing launches).
`cmd /k` (not `/c`) keeps the window open; no trailing `pause` needed
on the success path. Don't invent flags — keep each work's real command
as it was (Server stays plain `npm run dev`).
TRAP (2026-09-06, bisected): never a bare `npm`/`npx` line under
`setlocal` — npm.cmd ends with a `goto` to a nonexistent label, and
the failed goto unwinds the whole setlocal stack, reverting cwd to
the pre-`cd` dir before node spawns (symptom: ENOENT package.json at
the launcher dir while `echo %CD%` shows the right one). Hand bats
are immune only because the real command runs under `cmd /k` (fresh
child cmd); generated detached runners emit NO `setlocal` at all.

## GUI launchers (Unity Hub / VSCode / Web .lnk)

Same guards, then `start "" <exe/lnk>` (opens NO console), then `pause`
so the window stays for inspection, `exit /b 0`. `start` needs no
`cmd /c` wrapper (that spawns a pointless extra shell).

## Titles

Every launcher sets `title <works.json label>` (exact) as an early
action. Conhost keeps it for the window's life — UNTIL the backend
rewrites it: proven live that node/npm backends clear or replace the
title (omniroute-cli window showing `''`). So title is window-*lookup*
only (find step 4), never detection, never a kill seed. Shared-host
guard drops title hits owned by windowsterminal/explorer/powershell or
our own PID (closing a shared WT window would take the user's tabs).
If WT ever becomes the default terminal, per-tab close needs a
WT-specific API — revisit then.

## Exempt

`HamsterWorld Redis.bat` is an interactive Docker control panel, not a
launcher — outside this template.
