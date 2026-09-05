# 001: detached (docker-style) node worker — VALIDATED

Throwaway scratch process only (`wc-spike-detached-9f37` token, hidden
`ping` worker). Never touched a real work. Re-run:
`python -u spikes/001-detached-node/spike_detached.py`.

## Verdict: VALIDATED

### What worked (live, 2026-09-06)
- `CREATE_NO_WINDOW` launch -> zero HWNDs system-wide for the whole tree
  (root cmd + 2 children). No console to hide, lose, or Alt+F4.
- stdout redirected to a log file (`docker logs` equivalent) with content.
- Manifest-style token still matches CommandLine -> detection unchanged.
- Exact-PID structural kill (self + descendants only) -> all dead, no sweep.

### What didn't
- Nothing in the mechanism. Genuine limits live one level up (real build).

### Surprises
- Detached `cmd /c` still yields a 3-proc tree (wrapper + 2) — kill must
  take descendants, same as visible mode. No conhost appears at all.

### Recommendation for the real build
- Per-work manifest flag, e.g. `"run": "detached"` on the 5 node works
  (server/clint/quest/mcp/cli); GUI works (mr-*, omniroute-web) stay visible.
- `run_work` branch: detached = `Popen([cmd /c bat], CREATE_NO_WINDOW,
  stdout=log, stderr=STDOUT, stdin=DEVNULL)`; log path per work under
  `wc_logs/` (already ignored). Keep launching via the same `.bat` so
  cwd/env stay identical.
- Dashboard: per-row `log` button = tail viewer (tk Text + refresh).
  Hide/Show/park buttons become no-ops for detached rows (nothing to hide).
- Detection + kill paths need NO change (tokens match the same way;
  kill gets strictly safer — no conhost/window in the set).
- Kill the standing `requirements.md` "VISIBLE windows, never hidden"
  line (or scope it to non-detached works) — user explicitly overrode it.
- Caveats to document: detached stdin is DEVNULL (interactive npm prompts
  get EOF — answer via flags/config); `pause` in bats is harmless.
- Open risk NOT covered by this spike: `nodemon` long-run behavior
  detached (restarts, file-watch). Validate on hamster-server first in
  the real build before rolling to all five.
