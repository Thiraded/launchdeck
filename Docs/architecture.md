# Architecture — how the suite fits together

Entry points: `wc.bat` (console TUI `wc.py`) and `wctray.bat`
(dashboard `wctray.py`, pythonw, no console). All logic lives in
`wc_core.py` (no UI); both frontends funnel through `launch_work` /
`kill_work`, so a fix in core covers every Start/Stop path.

## State tokens (`wc_core.py`)

```
OFF   " "   [ ]  not selected
ON    "x"   [X]  selected to act on (Space toggles)
RUN   "-"   [-]  detected as actually running (live, INFO only)
```

`[-]` is info only — you cannot cancel it by keypress. To stop a running
work you select it `[X]` and press Enter (kill).

## Detection (`scan_table` + `is_running`)

One shared process table `(pid, ppid, name, cmdline)` feeds every
consumer: `gowc.exe scan` when present (~0.07s), else one powershell
`Get-CimInstance Win32_Process` dump (~0.9s). `is_running` /
`live_running` / `poll_launch` match tokens against it in pure Python
(no per-work rescan; the live `[-]` monitor is a background thread).

Matching is case-insensitive substring (`-like` semantics; our tokens
carry no `-like` wildcards). Excludes `powershell*` (+ own chain where
it matters). `WINDOWTITLE` is not used — see `requirements.md`.

## Launch (`launch_work` -> `run_work`)

`cmd.exe /c start "" <bat>` opens the visible window hosting the `.bat`.
(`start` takes exactly one `""` title placeholder — a stray second `""`
once made it open Explorer instead.) `register(work)` records
`{label, bat, launched}` into `registry.json`. wc never auto-closes after launch;
it is a persistent manager.

`_launched_count` / `MAX_LAUNCHES` caps total spawns per session.

## Kill (`kill_work`)

Evolved past its original form (Terminate-every-match). Current design
lives in `kill-safety.md`: DOWN-ONLY seeds + descendants, protected
chain, NEVER-seed GUI list, token hygiene, `dry_run`, then three close
passes (graceful taskkill, Alt+F4 `WM_CLOSE`, `/F` sweep). Ends with
`clear_hidden_work` + `unregister`.

## Model / groups (`build_model`)

Group selected <=> any child selected (pure OR). Space on a group
toggles ALL children; clearing any child clears the group. Works that
are group members never render standalone.

## wc.py behavior

Cursor nav (Up/Down), `Space`/`t` toggles `[ ]`<->`[X]`, `Enter` acts on
every `[X]` (kill if `[-]`, else launch), `h` minimizes the cursor's
work window (see `windows.md`),
`Esc`/`q` quits (saves `wc.settings.txt` preset). Live `[-]` from the
background thread; Enter trusts the visible cache over a fresh scan
(a failed scan must never turn a kill into an accidental launch).

## Key capture

`get_key()` reads the console INPUT buffer via `ReadConsoleInput`
(ctypes), not `msvcrt.getch()` (which drops keys, esp. Space, in
bat-spawned consoles). QuickEdit/Mouse modes are disabled at startup
so a mouse click can't freeze keyboard input.
