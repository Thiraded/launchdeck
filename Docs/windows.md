# Windows (find / close) — owner sets, titles, headless

Hide/show/park and the console `h` key were removed on 2026-10-01 (every
work is detached; there is no window to hide). Window finding remains
for the legacy kill's Alt+F4 pass on GUI works.

## Finding a work's windows (`find_work_hwnds`, `launchdeck_core.py`)

1. **Seeds**: CommandLine token match over the shared table (minus
   powershell*, NEVER-seed GUI, plus the `.bat` basename + long-enough
   work id via `kill_tokens_for`).
2. **Ancestors** (only in `_hwnds_for_pids`): bounded walk up (8, stops
   at our protected chain) THROUGH `cmd.exe` HOSTS ONLY, so the `cmd`
   host is included. Upward-only matching alone misses, because
   matchable seeds (node) sit BELOW the window owner. Any other parent
   (powershell, IDE, explorer, terminal app) stops the walk: it is the
   user's host. (2026-09-30: `find_work_hwnds` had its own UNBOUNDED
   copy of this walk that reached Code.exe/explorer.exe for manual runs;
   removed, covered by `test_find_work_hwnds_never_climbs_into_ide_or_explorer`.)
3. **Owner set** (`_hwnds_for_pids`): seeds + bounded cmd ancestors + ONE
   level of children (catches conhost + wrapper cmds, which own the
   visible window). Powershell never added. EnumWindows
   keeps top-level windows owned by the set that are `IsWindowVisible`.
4. **Exact title** (`_title_hwnds_guarded`): window title exactly equals
   the work label (case-insensitive), minus shared-host guard. Catches
   reparented hosts. Includes invisible windows.

The up+down expansion is for CLOSE (WM_CLOSE) only.
Kill stays DOWNWARD-ONLY — see `kill-safety.md`.

## Headless doctrine (researched 2026-09-06)

Proven live (Clint: full healthy tree incl. conhost, zero HWNDs
system-wide, `MainWindowHandle=0`) + outside reports (npm/node survive
their console being closed): Win32 binds console<->window once at
creation. `AttachConsole`/`AllocConsole` affect the CALLER only; ConPTY
re-host needs pty ownership from birth. **NO API re-windows a running
process.** Virtual desktops and elevation do NOT hide windows from
EnumWindows (ruled out); SW_HIDE windows still enumerate — so "no HWND
at all" always means truly windowless.

Therefore: no "restore" — Stop the work and Start it fresh for a new
window (the deck's Restart button does exactly this). `h` on
running-but-windowless reports not-found (see above).

## Known gaps (not bugs, documented limits)

- Pre-existing orphans with no tokens and default titles can't be
  attributed — never touched automatically (ask first).
- WT-manual runs: guarded out (closing a shared WT window would take
  the user's tabs); process-level kill only.
- The dashboard owns the respawn sweep: a dev server that creates a fresh
  console after start is handled by the dashboard's window pass.
