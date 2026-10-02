# AGENTS.md — LaunchDeck launcher suite

> Python dashboard UI (stdlib only) + optional Go helper, driven by
> `works.json`, living in `D:\launchdeck` (git: `Thiraded/launchdeck@main`).
> This file is the INDEX: what the project is, where things are, the one
> rule that never bends, and links into `Docs/`. Knowledge lives in
> `Docs/` — keep it there, keep this file small.

## What this is

Single-screen launcher that starts/stops dev servers and apps. Each
work runs DETACHED (no console; output to `launchdeck_logs/`, live color tail
in the dashboard viewer). The `launchdeck` command opens the tray dashboard
through `launchdeck.bat`; the terminal interface has been retired. Details:
`Docs/architecture.md`.

## Layout

| Path | Role |
|------|------|
| `works.json` | Manifest: `groups[]` + `works[]` (id/label/bat/match/detect). |
| `launchdeck_core.py` → `deck/core/` | Shared logic: manifest, detection, run/kill, registry, model. NO UI. `launchdeck_core` is the facade (map: `Docs/architecture.md`); `deck/core/jobs.py` = Job Object launch/stop (`Docs/kill-safety.md`). |
| `launchdeck_dashboard.py` (`launchdeck.bat`) | The UI entry point (funnels through core). Dashboard code is in `deck/ui/` (map: `Docs/architecture.md`). |
| `assets/icons/*.svg` | UI icons, rendered by `deck/ui/icons.py` (stdlib). |
| `launchdeck_tray.py` | Tray primitives (ctypes only). Reference; see `Docs/tray.md`. |
| `launchdeck-gen-<id>.bat` (in `launchdeck_logs/`, generated) | Per-work runners, materialized from manifest steps (see `Docs/bat-template.md`). |
| `hermess.bat` | Hermes launcher (moved in here; shimmed from `launchdeck-bin`). |
| `launchdeck-helper/` + `launchdeck-helper.exe` | Optional Go scan/kill helper (see `Docs/launchdeck-helper.md`). |
| `registry.json` | Runtime: launches (root PID + runner). |
| `launchdeck.settings.txt` | Legacy console selection preset; retained as local state. |
| `test_launchdeck_core.py`, `test_tray_foundation.py`, `test_kill_safety.py`, `test_ui_smoke.py`, `test_jobs.py` | Tests (policy in `Docs/verification.md`). `test_launchdeck_core.py` and opt-in `test_jobs.py` spawn processes. |
| `Docs/` | ALL knowledge (below). `spec-*.md` history stays at root. |

Outside the repo: Desktop and Startup each have `launchdeck.lnk`;
`%LOCALAPPDATA%\launchdeck-bin` holds the `launchdeck` and `hermess` commands.

## Docs (read these before touching the area)

- `Docs/requirements.md` — standing constraints. Do not regress.
- `Docs/architecture.md` — tokens, detection, launch, kill-overview, model, keys.
- `Docs/bat-template.md` — the one true launcher shape + titles.
- `Docs/kill-safety.md` — DOWN-ONLY, protected set, dry_run, passes, traps.
- `Docs/windows.md` — find/close, headless doctrine.
- `Docs/tray.md` — deck behavior, backlog, PARK trial.
- `Docs/launchdeck-helper.md` — Go helper protocol, numbers, rebuild.
- `Docs/verification.md` — gates + live-machine test policy.
- `Docs/history.md` — moves, rename, incidents.
- `Docs/status.md` — what is live/verified/open RIGHT NOW. Read first.
- `Docs/plan.md` — full remaining-work plan + session handoff (traps, tests, backlog). Read second.

Skills that apply here: `windows-launcher-lifecycle` (start/detect/kill
workflow + machine-side-effect discipline), `spike` (validate before
build). Load them; they hold the proven snippets.
(Old § map, for code comments referencing them: §4.5/§4.7/§4.9/§6 →
`kill-safety.md`, §4.8 → `bat-template.md`, §4.6/§4.11 → `windows.md`,
§4.4/§7 → `tray.md`, §4.10 → `launchdeck-helper.md`, §8 → `verification.md`.)

## The one rule (compact form — full text in `Docs/kill-safety.md`)

Before ANY command touching the live machine, write out: (1) exact
PIDs / names / paths affected, (2) whether any could be the user's own
app, (3) certainty it hits only the target — else STOP and narrow/ask.
Narrow + exact always; show kill lists before killing when in doubt.
