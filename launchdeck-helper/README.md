# launchdeck-helper — fast Win32 helper for the launchdeck suite

Stdlib-only Go (`syscall` + `unsafe`, no deps, no network to build).
`launchdeck_core.py` uses `launchdeck-helper.exe` when it sits next to it, otherwise falls back
to the powershell scans (same results, ~4x slower per spawn).

```
cd launchdeck-helper && go build -o ../launchdeck-helper.exe .
```

Graduated from `spikes/002-launchdeck-helper-scan` (VALIDATED: 0 content mismatches vs
`Get-CimInstance` over ~285 procs; scan 200-350ms single-threaded).

## Protocol

- `scan` -> stdout lines `pid|ppid|name|commandline` sorted by pid
  (16-worker fan-out; 32-bit/protected targets come out with empty cmd)
  (exit 1 if the snapshot itself fails)
- `kill <pid>..` -> `killed <pid>` / `dead <pid>` / `denied <pid>` per PID,
  exit 0 always
- `version` -> `launchdeck-helper 1.1.0`
