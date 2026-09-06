# wc-launcher

Single-screen launcher for dev servers and apps on Windows.
Each work starts **detached** (no console window; output goes to a per-work
log file with a live color tail viewer in the dashboard).

Two frontends, one shared core (`wc_core.py`, stdlib only):

| Entry | Role |
|-------|------|
| `wc.bat` → `wc.py` | Console TUI: Space select, Enter kill/launch |
| `wctray.bat` → `wctray.py` | Tray + dashboard twin (no console) |

## Requirements

- Windows + Python 3 (stdlib only, no pip packages)
- Optional: Go toolchain to rebuild the `gowc` scan helper

## Quickstart

1. Copy this repo, open the dashboard (`wctray.bat`) or console (`wc.bat`).
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
- `personal` — real local config with actual project paths.

## Docs

Start at `AGENTS.md` (index) → `Docs/requirements.md`,
`Docs/architecture.md`, `Docs/verification.md`.
