# History — repository moves, renames, incidents

## 2026-10-02 — one UI and LaunchDeck commands

The `launchdeck` command, Desktop shortcut, and Startup shortcut now open the
tray dashboard. The console frontend and its separate launch command were
removed. The user command folder and isolated VS Code profiles were moved to
LaunchDeck-named paths. Existing work processes keep their original runner,
log, registry, and helper paths until they stop naturally; see `status.md`.

## Repository move — 2026-09-05

The suite moved out of the Desktop repository into `D:\launchdeck`, separating
project files from unrelated Desktop items. Paths and launch shims were
repointed, and the repository now uses `Thiraded/launchdeck@main`.

## Product rename — 2026-09-06

LaunchDeck became the public product and repository name. Entry modules,
settings, generated runner prefix, and dashboard identity were renamed. The
optional Go process helper was kept as a separate accelerator. Screenshots
were added to the README.

## One branch and local configuration — 2026-09-06

The repository settled on one `main` branch. Machine-local configuration,
registry state, settings, logs, and executables are ignored; fresh clones start
with an empty manifest and add works through the dashboard.

## Incidents that shaped the rules

- **2026-08-30:** a debug loop spawned repeated terminals; an overly broad kill
  pattern reached Discord, a browser, and VS Code. This led to the
  machine-side-effect rule, DOWN-ONLY traversal, and token hygiene
  (`kill-safety.md`).
- **2026-09-05:** an ancestor walk reached the agent session and user apps.
  This led to the protected process chain (`kill-safety.md`).
- **2026-09-05/06:** a headless work kept running without a window. This led to
  the headless doctrine (`windows.md`).
- **2026-09-06:** Thai bytes in a browser tab command line crashed scans under
  `cp1252`. Captures now use UTF-8 with replacement (`verification.md`).

## Hide-path revert — 2026-09-06

The hide-path experiment made the `h` key less reliable than the prior shape.
The launcher was reverted while UTF-8 hardening stayed. Runtime logs and
registry state remained machine-local, and the Hermes shim stayed in place.

## Public repository cleanup — 2026-09-06

The public repository kept source, docs, and screenshots. Generated launchers,
spike scratch files, and runtime state remained local and ignored.
