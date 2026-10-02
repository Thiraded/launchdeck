<p align="center">
  <h1 align="center">launchdeck</h1>
  <p align="center"><b>One screen to start, watch, and stop every dev server and app you run.</b></p>
  <p align="center">
    <img src="https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white" alt="Windows" />
    <img src="https://img.shields.io/badge/Python-3-3776AB?logo=python&logoColor=white" alt="Python 3" />
    <img src="https://img.shields.io/badge/deps-stdlib_only-brightgreen" alt="stdlib only" />
  </p>
</p>

No consoles piling up. No forgotten background processes. No "which
terminal was the API server?" — every work launches **detached**, and the
deck shows what's actually alive right now, with a live log tail.

<p align="center">
  <img src="assets/dashboard.png" alt="launchdeck dashboard" />
  <br /><i>The deck: groups, live running state, per-row actions.</i>
</p>

| | |
|---|---|
| <img src="assets/log-viewer.png" alt="log viewer" /> | <img src="assets/task-editor.png" alt="task editor" /> |
| <i>Live color log tail with clickable links.</i> | <i>New-task editor: commands, vars, match token.</i> |

## Why not just more terminals?

- **1 work = 1 managed process tree.** Start/stop from one place instead
  of hunting windows.
- **Live detection, not wishful thinking.** The running dot comes from a
  real process scan every ~2 s — if the port is up, the dot is on.
- **Logs, not lost scrollback.** Each start truncates to a fresh per-work
  log with a `[deck] launch …` marker; the viewer follows in color with
  clickable URLs.
- **Safe kill by construction.** Down-only traversal (matches +
  descendants), a protected launcher chain, dry-run preview. It cannot
  take your editor, browser, or chat apps with it.
- **Optional Go helper** (`launchdeck-helper/`) for sub-second scans on loaded
  machines; pure-Python fallback otherwise.

One dashboard UI and one shared core (`launchdeck_core.py`, zero dependencies):

| Entry | Role |
|-------|------|
| `launchdeck` / `launchdeck.bat` → `launchdeck_dashboard.py` | Tray + dashboard UI; no console window |

## Requirements

- Windows + Python 3 (stdlib only — nothing to `pip install`)
- Optional: Go toolchain to rebuild `launchdeck-helper.exe`

## Quickstart

1. Run `launchdeck` or `launchdeck.bat`. A floating lightning button appears on the desktop; click it to open the dashboard. Drag it to move it.
2. Add your works: dashboard editors (tasks / groups / settings) or edit
   `works.json` directly — one entry per work:

```json
{
  "id": "web-client",
  "label": "Web Client",
  "run": "detached",
  "vars": { "APPDIR": "D:\\examples\\web-client", "PORT": "5173" },
  "steps": [
    { "type": "terminal", "cmd": "cd /d \"%APPDIR%\"" },
    { "type": "terminal", "cmd": "npm run dev -- --port %PORT%" },
    { "type": "app", "cmd": "start \"\" \"%APPDIR%\\app.exe\"" }
  ],
  "match": "D:\\examples\\web-client",
  "detect": true,
  "icon": "zap"
}
```

- `steps`: `terminal` lines run in order in a hidden shell;
  `app:` lines open GUI apps (`start "" ...`).
- `match`: **must appear verbatim in the real backend process's
  CommandLine** (e.g. the project dir for `node.exe`, not a window title).
  Detection and kill both key off it.
- `detect: false` = fire-and-forget (no running state shown).
- Global hotkey (`alt+w` by default) toggles the dashboard from anywhere.

## Safety (kill model)

Kills go **down-only**: matched seed processes + their descendants.
The launcher chain (scanner, launcher PID, all ancestors) is a protected
set that can never enter a kill list. Preview with dry-run before any real
kill. Details: `Docs/kill-safety.md`.

## Layout

| Path | Role |
|------|------|
| `works.json` | Manifest: `groups[]` + `works[]` (edit me) |
| `launchdeck_core.py` | Shared logic: manifest, detection, run/kill, registry. No UI |
| `launchdeck_dashboard.py` | Dashboard UI entry point |
| `launchdeck_tray.py` | Win32 notification-icon and hidden-hotkey primitives (ctypes only) |
| `launchdeck-helper/` | Optional Go scan/kill helper (`go build -o ../launchdeck-helper.exe .` inside) |
| `assets/` | README screenshots |
| `Docs/` | All knowledge: architecture, kill-safety, tray, verification |

Runtime files (`registry.json`, `launchdeck.settings.txt`, `launchdeck_logs/`,
`works.local.json`) are local-only and git-ignored — never committed.

## Branches

- `main` — the only branch. `works.json` is git-ignored and yours alone.

## Docs

Start at `AGENTS.md` (index) → `Docs/requirements.md`,
`Docs/architecture.md`, `Docs/verification.md`.
