# Windows (hide / find / close) — owner sets, titles, headless

## Finding a work's windows (`find_work_hwnds`, `wc_core.py`)

1. **Seeds**: CommandLine token match over the shared table (minus
   powershell*, NEVER-seed GUI, plus the `.bat` basename + long-enough
   work id via `kill_tokens_for`).
2. **Ancestors**: bounded walk up (8, stops at our protected chain) so
   the `cmd` host is included. Upward-only matching alone misses,
   because matchable seeds (node) sit BELOW the window owner.
3. **Owner set** (`_hwnds_for_pids`): seeds + bounded ancestors + ONE
   level of children (catches conhost + wrapper cmds, which own the
   visible window). Powershell traversed, never added. EnumWindows
   keeps top-level windows owned by the set that are `IsWindowVisible`.
4. **Exact title** (`_title_hwnds_guarded`): window title exactly equals
   the work label (case-insensitive), minus shared-host guard. Catches
   reparented hosts. Includes invisible windows.

The up+down expansion is for HIDE/CLOSE (reversible-ish) only.
Kill stays DOWNWARD-ONLY — see `kill-safety.md`.

## `h` key (wc.py) — minimize to taskbar

`h` on a running work minimizes its windows (`SW_SHOWMINIMIZED`, normal
background-app feel — still on taskbar/Alt+Tab) and tracks HWNDs in
`_minimized_hwnds`; `h` again restores (`SW_RESTORE`). The wc console is
never touched. When no window is found it reports
"running but its window was not found" (see Headless below).

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
window (wctray's Restart button does exactly this). `h` on
running-but-windowless reports not-found (see above).

## Known gaps (not bugs, documented limits)

- Pre-existing orphans with no tokens and default titles can't be
  attributed — never touched automatically (ask first).
- WT-manual runs: guarded out (closing a shared WT window would take
  the user's tabs); process-level kill only.
- wc.py has no respawn sweep (wctray does): a dev server forking a
  fresh console after minimize leaves the new one visible.
