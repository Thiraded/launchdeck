# Architecture — how the suite fits together

Entry point: `launchdeck` or `launchdeck.bat` opens the dashboard
(`launchdeck_dashboard.py`, pythonw, no console). All logic lives in
`launchdeck_core.py` (no UI); the dashboard funnels through `launch_work`
/ `kill_work`, so a core fix covers every Start/Stop path.

## Dashboard modules (`deck/ui/`)

`launchdeck_dashboard.py` is a 20-line entry shim; the deck lives in
`deck/ui/` (split 2026-09-30 from one 2,500-line file, behavior
unchanged):

| Module | Role |
|--------|------|
| `main.py` | `main()`: instance guard, hidden hotkey host, desktop button, Dashboard, mainloop. |
| `app.py` | `Dashboard`: window lifecycle, popups, `_poll` action pump, `_run_async`. Composed of the mixins below. |
| `worklist.py` / `actions.py` / `editors.py` / `logviewer.py` | Mixins: rows (build + in-place update), row actions, dialogs, log tail. |
| `launcher.py` | `DesktopLauncher`: draggable, always-on-top lightning button; reports moves to the dashboard for popup anchoring. |
| `hotkey.py` | `HotkeyHost`: hidden native message window for global-hotkey ownership. Tk work is queued to `state.actions`. |
| `state.py` | Shared mutable state + work ops: `log`, `actions` queue, `_running` (monitor thread), `hotkey_host`, `toggle_start_stop`. |
| `theme.py` | Palettes + fonts. `TH_*` are rebound on theme switch: read as `theme.TH_X`, never `from theme import`. |
| `widgets.py` / `viewmodel.py` | Themed Tk helpers / pure row+form helpers. |
| `icons.py` / `dpi.py` | SVG icon renderer (below) / DPI awareness. |
| `instance.py`, `selftest.py` | Named-mutex guard, `--self-test`. |

Rule: `state` and `theme` are imported as modules (`state.log(...)`), so
rebinding and `mock.patch.object(state, ...)` reach every caller.

## Core modules (`deck/core/`)

`launchdeck_core.py` is a facade (split 2026-10-01 from 2,200 lines, code
moved verbatim). `core.X` reads AND writes are forwarded to the module
that owns `X`, so `mock.patch.object(core, "scan_table", ...)` still
reaches `kill_work`. Inside `deck/core`, a cross-module name is always
qualified (`detect.scan_table`), never `from x import name`.

| Module | Role |
|--------|------|
| `common.py` | Repo root `HERE`, `_NO_WINDOW`. |
| `manifest.py` | `works.json` load/save, settings, hotkeys, group slugs. |
| `store.py` | `registry.json`, atomic write, `_StateMutex`. |
| `steps.py` | steps/vars -> generated `.bat`, log paths, editor text forms. |
| `ansi.py` | SGR color runs for the log viewer. |
| `detect.py` | Process table scans, identity tokens, `is_running`. |
| `jobs.py` | Job Object launch/stop (`kill-safety.md` "Job Objects"). |
| `kill.py` | `kill_work`: job stop, else the legacy passes. |
| `windows.py` | Find/close a work's windows (legacy Alt+F4 pass). |
| `model.py` | Pure tree model + selection state helpers. |
| `launch.py` | `run_work`, `launch_work`, `poll_launch`. |

Rule: a function local must never share a sibling module's name (a local
`steps` or `manifest` turns every `steps.x` in that function into an
UnboundLocalError). Import the module under an alias
(`manifest as manifest_mod`) where the name is part of a public
signature. `test_no_local_shadows_a_module` enforces this for
`deck/ui` and `deck/core`.

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
consumer: `launchdeck-helper.exe scan` when present (~0.07s), else one powershell
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
the same `.bat` runs, stdout/stderr go to `launchdeck_logs/<id>.log` (fresh per
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
lives in `kill-safety.md`. Detached all-terminal works launched by the deck
run in a Job Object and stop by job membership ("Job Objects"). Everything
else uses the legacy path: DOWN-ONLY seeds + descendants, protected
chain, NEVER-seed GUI list, token hygiene, registry runner identity,
common-parent validation for multi-process dev works, exact duplicate-runner
handling, `dry_run`, then three close passes (graceful
taskkill, Alt+F4 `WM_CLOSE`, identity revalidation, `/F` sweep). A final
scan confirms the targets are gone before
`unregister`; a failed scan or surviving PID is reported as blocked.

## Model / groups (`build_model`)

Group selected <=> any child selected (pure OR). Space on a group
toggles ALL children; clearing any child clears the group. Works that
are group members never render standalone.

## UI entry point

`launchdeck.bat` starts `launchdeck_dashboard.py` with `pythonw.exe`.
Launch shows the floating desktop button. Clicking it opens the dashboard
beside the button; clicking it again closes the dashboard and every dashboard
popup. Dragging the button while the dashboard is open moves the dashboard
with it. The native hotkey host stays hidden and owns Alt+W registration, so
no taskbar tray icon is needed.
