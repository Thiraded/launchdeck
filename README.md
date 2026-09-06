# wc-launcher

![Windows](https://img.shields.io/badge/Windows-0078D6?logo=windows&logoColor=white)
![Python 3](https://img.shields.io/badge/Python-3-3776AB?logo=python&logoColor=white)
![deps](https://img.shields.io/badge/deps-stdlib_only-brightgreen)

**One screen to start, watch, and stop every dev server and app you run.**
No consoles piling up, no forgotten background processes, no "which
terminal was the API server?" — every work launches **detached**, and the
dashboard shows what's actually alive right now with a live log tail.

Two frontends, one shared core (`wc_core.py`, zero dependencies):

| Entry | Role |
|-------|------|
| `wc.bat` → `wc.py` | Console TUI: Space select, Enter kill/launch |
| `wctray.bat` → `wctray.py` | Tray + dashboard twin (no console window) |

## Why not just more terminals?

- **1 work = 1 managed process tree.** Start/stop from one place instead
  of hunting windows.
- **Live detection, not wishful thinking.** The running dot comes from a
  real process scan every ~2 s — if the port is up, the dot is on.
- **Logs, not lost scrollback.** Each start truncates to a fresh per-work
  log with a `[launch …]` marker; the viewer follows in color with
  clickable URLs.
- **Safe kill by construction.** Down-only traversal (matches +
  descendants), a protected launcher chain, dry-run preview. It cannot
  take your editor, browser, or chat apps with it.
- **Optional Go accelerator** (`gowc/`) for sub-second scans on loaded
  machines; pure-Python fallback otherwise.

## Requirements

- Windows + Python 3 (stdlib only — nothing to `pip install`)
- Optional: Go toolchain to rebuild `gowc.exe`

## Quickstart

1. Clone, open the dashboard (`wctray.bat`) or console (`wc.bat`).
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
  "icon": "⚡"
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
| `wc_core.py` | Shared logic: manifest, detection, run/kill, registry. No UI |
| `wc.py` / `wctray.py` | The two frontends |
| `wc_tray.py` | Tray primitives (ctypes only) |
| `gowc/` | Optional Go scan/kill accelerator (`go build -o ../gowc.exe .` inside) |
| `Docs/` | All knowledge: architecture, kill-safety, tray, verification |

Runtime files (`registry.json`, `wc.settings.txt`, `wc_logs/`,
`works.local.json`) are local-only and git-ignored — never committed.

## Branches

- `main` — generic setup (this file's examples). For anyone to copy and use.

## Docs

Start at `AGENTS.md` (index) → `Docs/requirements.md`,
`Docs/architecture.md`, `Docs/verification.md`.
