# Verification — how DONE is proven

## Gates

- `python test_launchdeck_core.py` passes (model build, detection, group OR,
  kill-via-group, Space OFF->ON -> Enter acts).
- Headless key-sequence simulation: Space -> `[X]`, Enter ->
  kill/launch, Esc -> quit.
- **Manual smoke on Windows** (standing gate, still open): open
  `launchdeck.bat`, Space on a work (`[ ]`->`[X]`), Enter on a running `[-]`
  work kills it, Enter on a stopped one launches it. Do NOT claim DONE
  until a human confirms this in the real window.
- Kill covers the `cmd` host AND child `node.exe` (no zombie windows).
- The deck never hangs the host: single shared scan, background `[-]`
  monitor (2s), no unbounded loops in the key path.

## Test policy (live machine — binding)

- **NEVER run `test_launchdeck_core.py` (or any process-spawning test) on a
  live user machine without explicit confirmation AND no live works
  running.** The harness spawns real `cmd` trees with the same shape
  as production launches; a kill step can sweep user processes
  (2026-08-30: appeared to kill the live `omniroute` CLI).
- Prefer `dry_run` (read-only PID lists) + synthetic scratch PIDs you
  own (hidden `ping`/`ping -n`, exact PID, verify death, then
  idempotency on the dead PID).
- New-window/console tests: hidden or message-only windows only —
  never flash a visible window on the user's screen.
- Decoding: every `subprocess` capture uses
  `encoding="utf-8", errors="replace"` (2026-09-06: Thai bytes in a
  browser tab's CommandLine crashed scans under locale `cp1252`).
- Delete scratch files only after a verified pass, never chained
  with the run itself.
