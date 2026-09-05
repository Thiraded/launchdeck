# Windows (hide / find / close) — owner sets, titles, capture, headless

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
never touched. Not found after a bounded retry (3 x 0.8s, covers the
launch race) → honest message (see Headless below), never a bare
"not found".

## Launch capture (retitle-proof, restart-proof)

Backends rewrite console titles, and in-memory tracking died with
restarts (orphaning hidden windows). So `launch_work` spawns a daemon
that polls `find_work_hwnds` for NEW visible windows (owner-based —
retitles can't escape it), records `{hwnd, title, pid}` into
`registry.json`, and greys out the X button (see below). `find` step 0
prefers recorded HWNDs validated live (`IsWindow` + owner alive).
Kill clears them via `unregister`.

## X button disarmed (`_disarm_close_button`)

`DeleteMenu(SC_CLOSE)` on conhost-owned work windows at capture time.
A stray X-click while node survives the console-close was the #1
headless creator; our WM_CLOSE/taskkill paths bypass menu state, so
Stop/Restart are unaffected. GUI apps never touched.

## Headless doctrine (researched 2026-09-06)

Proven live (Clint: full healthy tree incl. conhost, zero HWNDs
system-wide, `MainWindowHandle=0`) + outside reports (npm/node survive
their console being closed): Win32 binds console<->window once at
creation. `AttachConsole`/`AllocConsole` affect the CALLER only; ConPTY
re-host needs pty ownership from birth. **NO API re-windows a running
process.** Virtual desktops and elevation do NOT hide windows from
EnumWindows (ruled out); SW_HIDE windows still enumerate — so "no HWND
at all" always means truly windowless.

Therefore PREVENT (X-disarm) + REBIRTH (`r` in wc.py = kill + bounded
settle + fresh launch, cursor work or group; wctray Restart button is
the same doctrine), never "restore". `h` on running-but-windowless
says NO window and points at `r`.

## Known gaps (not bugs, documented limits)

- Pre-existing orphans with no tokens and default titles can't be
  attributed — never touched automatically (ask first).
- WT-manual runs: guarded out (closing a shared WT window would take
  the user's tabs); process-level kill only.
- wc.py has no respawn sweep (wctray does): a dev server forking a
  fresh console after minimize leaves the new one visible.
- Minimized-tracking is per wc.py session for restore; recorded HWNDs
  (registry) survive restarts for find/close.
