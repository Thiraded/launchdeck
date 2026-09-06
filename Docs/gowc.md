# gowc.exe — Go scan/kill accelerator

Pure-stdlib Go (`syscall` + `unsafe`, no deps, no network to build).
`launchdeck_core.py` uses `gowc.exe` when it sits next to it, else IDENTICAL
powershell fallbacks — never a hard dependency.

## Protocol

- `scan` -> stdout lines `pid|ppid|name|commandline` sorted by pid
  (16-worker fan-out over `CreateToolhelp32Snapshot`; command lines
  from the PEB via `NtQueryInformationProcess` + `ReadProcessMemory`).
- `kill <pid>..` -> `killed <pid>` / `dead <pid>` per PID, exit 0
  always (in-process `TerminateProcess`; a stale PID never fails
  the sweep).
- `version` -> version string.

## Numbers (live, ~275 procs)

`scan_table` 0.85s -> 0.07s, kill dry_run 0.83s -> 0.06s,
`find_work_hwnds` (was 3 spawns) 2.67s -> 0.07s. Pass-3 sweep uses one
`gowc kill` call instead of N taskkill spawns; pass 1 stays
taskkill-no-`/F` (graceful console-close has no Go equivalent, and
`GenerateConsoleCtrlEvent`/CTRL_C only breaks to prompt anyway).

## Spike 002 verdict (VALIDATED with constraints)

Same-minute diff vs `Get-CimInstance`: 142 exact command-line
matches, 137 both-empty, **0** go-empty-but-ps-has, **0** content
mismatches (2 apparent diffs were exited bash wrappers — churn).
Token checks identical, incl. the Brave tab-URL PID. 32-bit targets
from this 64-bit build would read empty (NtWow64 path not
implemented) — no such case observed; the powershell fallback covers
it. <100ms needs deeper fan-out tuning (currently ~170ms) — optional.

## Rebuild & ship

```
cd gowc && go build -o ../gowc.exe .
```

Commit the exe (~2.5MB) so it works without the toolchain.
`gowc/README.md` holds the short form of this page.
