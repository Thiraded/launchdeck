# Architecture — how the suite fits together

Entry points: `launchdeck.bat` (console TUI `launchdeck.py`) and
`launchdeck-tray.bat` (dashboard `launchdeck_dashboard.py`, pythonw,
no console). All logic lives in `launchdeck_core.py` (no UI); both
frontends funnel through `launch_work` / `kill_work`, so a fix in
core covers every Start/Stop path.

## Dashboard modules (`deck/ui/`)

`launchdeck_dashboard.py` is a 20-line entry shim; the deck lives in
`deck/ui/` (split 2026-09-30 from one 2,500-line file, behavior
unchanged):

| Module | Role |
|--------|------|
| `main.py` | `main()`: instance guard, tray thread, Dashboard, mainloop. |
| `app.py` | `Dashboard`: window lifecycle, popups, `_poll` action pump, `_run_async`. Composed of the mixins below. |
| `worklist.py` / `actions.py` / `editors.py` / `logviewer.py` | Mixins: rows (build + in-place update), row actions, dialogs, log tail. |
| `tray.py` | `WorkTray` (tray thread). Tk work is queued to `state.actions`. |
| `state.py` | Shared mutable state + work ops: `log`, `actions` queue, `_running` (monitor thread), `tray_host`, `toggle_start_stop`. |
| `theme.py` | Palettes + fonts. `TH_*` are rebound on theme switch: read as `theme.TH_X`, never `from theme import`. |
| `widgets.py` / `viewmodel.py` | Themed Tk helpers / pure row+form helpers. |
| `icons.py` / `dpi.py` | SVG icon renderer (below) / DPI awareness. |
| `instance.py`, `selftest.py` | Named-mutex guard, `--self-test`. |

Rule: `state` and `theme` are imported as modules (`state.log(...)`), so
rebinding and `mock.patch.object(state, ...)` reach every caller.

## Icons (`deck/ui/icons.py`)

Tk 8.6 has no SVG and Pillow is off-limits, so `assets/icons/*.svg`
(Lucide-style, ISC, 24 grid, stroke 2) are parsed and rasterized in
pure Python: strokes by distance-to-segment (AA, round caps), fills by
supersampled nonzero scanline, optional circle/pill plate, emitted as
RGBA PNG -> `PhotoImage`. Cached per (name, size, color, plate). Cost:
~2.5 ms per icon cold, free warm. Canvas polygons are NOT an option
(no AA on Windows). Add an icon = drop an .svg using only path / line /
polyline / polygon / rect / circle / ellipse.

## State tokens (`launchdeck_core.py`)

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
it matters). An empty helper/WMI result is marked unavailable, so a Stop
or Start action never treats an unknown scan as "stopped". `WINDOWTITLE`
is not used — see `requirements.md`.

## Launch (`launch_work` -> `run_work`)

Default is `"run": "detached"`: NO console at all (`CREATE_NO_WINDOW`),
the same `.bat` runs, stdout/stderr go to `wc_logs/<id>.log` (fresh per
Start + `[deck] launch` marker), stdin is NUL. The deck log viewer is
the docker-logs equivalent (live 1s follow, ANSI colors); a work with
its own `"log"` key tails that file instead. Visible mode
(`cmd.exe /c start "" <bat>`, exactly one `""` title placeholder — a
stray second `""` once made it open Explorer instead) remains for
works without the key. `register(work)` records
`{label, bat, launched, pid, parent_pid, runner}` for detached roots (and the runner
for visible launches) into `registry.json`. A recorded PID is used only when
its command line still names the same runner. The deck never auto-closes after launch;
it is a persistent manager.

Runaway guard: one work may start at most `LAUNCH_BURST` (5) times per
`LAUNCH_WINDOW_S` (60s). (Was a lifetime `MAX_LAUNCHES`=16 per process,
which silently disabled Start in a long-lived tray.)

Generated runners (`materialize_steps`): label escaped for cmd
(`^&|<>()`, `%%`), `cd`/`pushd` steps end in `|| goto :deck_cd_failed`,
`@chcp 65001` only when the script is non-ASCII, and the file is not
rewritten when unchanged (cmd reads a running .bat by offset).

State files (`registry.json`, `works.json`) are written via temp file +
`os.replace` under a lock + named mutex; `scan_available()` is per-thread.

## Kill (`kill_work`)

Evolved past its original form (Terminate-every-match). Current design
lives in `kill-safety.md`: DOWN-ONLY seeds + descendants, protected
chain, NEVER-seed GUI list, token hygiene, registry runner identity,
common-parent validation for multi-process dev works, exact duplicate-runner
handling, `dry_run`, then three close passes (graceful
taskkill, Alt+F4 `WM_CLOSE`, identity revalidation, `/F` sweep). A final
scan confirms the targets are gone before `clear_hidden_work` +
`unregister`; a failed scan or surviving PID is reported as blocked.

## Model / groups (`build_model`)

Group selected <=> any child selected (pure OR). Space on a group
toggles ALL children; clearing any child clears the group. Works that
are group members never render standalone.

## launchdeck.py behavior

Cursor nav (Up/Down), `Space`/`t` toggles `[ ]`<->`[X]`, `Enter` acts on
every `[X]` (kill if `[-]`, else launch), `h` minimizes the cursor's
work window (see `windows.md`),
`Esc`/`q` quits (saves `launchdeck.settings.txt` preset). Live `[-]` from the
background thread; Enter trusts the visible cache over a fresh scan
(a failed scan must never turn a kill into an accidental launch).

## Key capture

`get_key()` reads the console INPUT buffer via `ReadConsoleInput`
(ctypes), not `msvcrt.getch()` (which drops keys, esp. Space, in
bat-spawned consoles). QuickEdit/Mouse modes are disabled at startup
so a mouse click can't freeze keyboard input.
