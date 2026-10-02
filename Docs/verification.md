# Verification — how DONE is proven

## Gates

- `python test_launchdeck_core.py` passes (model build, detection, group OR,
  kill-via-group, Space OFF->ON -> Enter acts).
- `python -m unittest -v test_kill_safety.py` passes using only mocked process
  tables and subprocess calls (ambiguous roots, runner/PID reuse,
  reparented descendants, failed sweeps, and scan failures).
- Headless key-sequence simulation: Space -> `[X]`, Enter ->
  kill/launch, Esc -> quit.
- **Manual smoke on Windows** (standing gate, still open): run `launchdeck`
  or click the Desktop shortcut; confirm the lightning button appears, drag it,
  click to open the dashboard beside it, and click again to close the dashboard
  and every child popup. Confirm Alt+W still toggles the dashboard. Start/Stop
  one selected work in the dashboard. Do NOT claim DONE until a human confirms
  this in the real window.
- Kill covers the `cmd` host AND child `node.exe` (no zombie windows).
- The deck never hangs the host: single shared scan, background `[-]`
  monitor (2s), no unbounded loops in the key path.

## Test policy (live machine — binding)

- **NEVER run `test_launchdeck_core.py` (or any process-spawning test) on a
  live user machine without explicit confirmation AND no live works
  running.** The harness spawns real `cmd` trees with the same shape
  as production launches; a kill step can sweep user processes
  (2026-08-30: appeared to kill the live `omniroute` CLI).
- `test_jobs.py` (opt-in: `LAUNCHDECK_SPAWN_TESTS=1`) spawns only its own
  node children, inside jobs in a per-run namespace
  (`Local\launchdeck-test-<pid>-*`), and kills only by job membership
  re-checked with `IsProcessInJob`, so no token match exists that could
  reach a user process. PROPOSED (needs the user's sign-off): allowed while
  live works run. Until they sign off, the rule above applies to it too.
  It was run once on 2026-10-01 with live works running; afterwards every
  user node process was still alive.
- Unit tests rebind `jobs.PREFIX` to that per-run namespace, so a mocked
  test never opens a real work's job.
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
