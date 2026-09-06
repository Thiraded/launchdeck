# AGENTS.md — Work Combo (wc) launcher suite

> Plain Python TUIs (stdlib only) + optional Go helper, driven by
> `works.json`, living in `D:\workcombo` (git: `Thiraded/launchdeck@main`).
> This file is the INDEX: what the project is, where things are, the one
> rule that never bends, and links into `Docs/`. Knowledge lives in
> `Docs/` — keep it there, keep this file small.

## What this is

Single-screen launcher that starts/stops dev servers and apps. Each
work runs DETACHED (no console; output to `wc_logs/`, live color tail
in the dashboard viewer). `launchdeck` (console TUI: Space select,
Enter kill/launch) and `launchdeck-tray` (dashboard, pythonw) are the
two frontends. `kc` is dead — do not resurrect. Details: `Docs/architecture.md`.

## Layout

| Path | Role |
|------|------|
| `works.json` | Manifest: `groups[]` + `works[]` (id/label/bat/match/detect). |
| `launchdeck_core.py` | Shared logic: manifest, detection, run/kill, registry, model. NO UI. |
| `launchdeck.py` / `launchdeck_dashboard.py` (`launchdeck.bat`, `launchdeck-tray.bat`) | The two frontends (funnel through core). |
| `launchdeck_tray.py` | Tray primitives (ctypes only). Reference; see `Docs/tray.md`. |
| `launchdeck-gen-<id>.bat` (in `wc_logs/`, generated) | Per-work runners, materialized from manifest steps (see `Docs/bat-template.md`). |
| `hermess.bat` | Hermes launcher (moved in here; shimmed from `wc-bin`). |
| `gowc/` + `gowc.exe` | Optional Go scan/kill accelerator (see `Docs/gowc.md`). |
| `registry.json` | Runtime: launches, hidden tracking. Churns; normal. |
| `launchdeck.settings.txt` | Selection preset. |
| `test_launchdeck_core.py`, `test_tray_foundation.py` | Tests (policy in `Docs/verification.md`). |
| `Docs/` | ALL knowledge (below). `spec-*.md` history stays at root. |

Outside the repo: Desktop keeps only `launchdeck.lnk`; `%LOCALAPPDATA%\wc-bin`
holds the `launchdeck` / `launchdeck-tray` / `hermess` shims.

## Docs (read these before touching the area)

- `Docs/requirements.md` — standing constraints. Do not regress.
- `Docs/architecture.md` — tokens, detection, launch, kill-overview, model, keys.
- `Docs/bat-template.md` — the one true launcher shape + titles.
- `Docs/kill-safety.md` — DOWN-ONLY, protected set, dry_run, passes, traps.
- `Docs/windows.md` — find/hide/close, headless doctrine.
- `Docs/tray.md` — deck behavior, backlog, PARK trial.
- `Docs/gowc.md` — Go helper protocol, numbers, rebuild.
- `Docs/verification.md` — gates + live-machine test policy.
- `Docs/history.md` — moves, rename, incidents.
- `Docs/status.md` — what is live/verified/open RIGHT NOW. Read first.

Skills that apply here: `windows-launcher-lifecycle` (start/detect/kill
workflow + machine-side-effect discipline), `spike` (validate before
build). Load them; they hold the proven snippets.
(Old § map, for code comments referencing them: §4.5/§4.7/§4.9/§6 →
`kill-safety.md`, §4.8 → `bat-template.md`, §4.6/§4.11 → `windows.md`,
§4.4/§7 → `tray.md`, §4.10 → `gowc.md`, §8 → `verification.md`.)

## The one rule (compact form — full text in `Docs/kill-safety.md`)

Before ANY command touching the live machine, write out: (1) exact
PIDs / names / paths affected, (2) whether any could be the user's own
app, (3) certainty it hits only the target — else STOP and narrow/ask.
Narrow + exact always; show kill lists before killing when in doubt.
