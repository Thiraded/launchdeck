# Tray (wctray dashboard) — behavior, backlog, trials

`wctray.py` (via `wctray.bat`, pythonw, no console): tray icon +
dashboard popup (PowerToys-Workspaces style) with per-work
Open/Hide/Show/Stop/Restart, [+ New Task], per-work edit/delete
(writes `works.json`). Hide = true hide (`SW_HIDE`: gone from taskbar
AND Alt+Tab, process keeps running). Stop = kill tree + close window.
Restart = kill + fresh launch (the way out of headless-orphan state).

Row actions run on worker threads with `after()`-back marshalling —
scans once blocked the tk mainloop ("UI hangs" bug). The monitor
re-hides new windows of hidden-marked works every cycle
(`sweep_hidden_windows`; kill clears hidden tracking), rebuilds the
dashboard only on running/hidden/manifest change (no flicker), and
per-work tray icons appear on Hide (green, click to restore).

## ctypes traps (do not regress)

`kernel32.GetModuleHandleW(None)` needs its prototype set
(`argtypes=[c_wchar_p]`, `restype=c_void_p`) — default 32-bit `int`
return truncates the 64-bit handle and `CreateWindowExW` silently
returns NULL. The tray window CANNOT be `HWND_MESSAGE`
(`TrackPopupMenu` needs a real foreground-able top-level window:
`WS_POPUP` + `hWndParent=None`). Popup items arrive via `WM_COMMAND`
(command id in `wParam` low word) — `WndProc` MUST handle it. Quit from
the tray writes a synthetic Esc into the console input buffer
(`WriteConsoleInputW` + `KEY_EVENT`) so the loop unwinds and the preset
saves (`os._exit` only as fallback). Keep the `WINFUNCTYPE` callback
referenced until `EnumWindows` returns. Diagnostics: `wc_logs/tray.log`.

## Backlog (user feedback 2026-09-05, in order, one at a time)

- [x] **1. Hide is broken** — FIXED 2026-09-05 (owner set = seeds +
      bounded ancestors + 1 child level; NEVER-seed GUI after `omniroute`
      matched Brave via tab URL; omniroute `hwnds=0` was the same bug).
- [ ] **2. Inline commands + variables** — New Task should accept typed
      commands, not just `.bat` files. Design: `steps` + `vars` with
      `%VAR%` expansion, Terminal vs App step types. Scope: hamster
      combo first, migrate the rest, then delete the `.bat` launchers.
      Detection `match` tokens stay CommandLine-based.
- [ ] **3. New Group** — create (label + member works), rename, delete.
      Persisted in `works.json`.
- [ ] **4. Dashboard scroll** — content cut at Midnight-Rider combo;
      `<MouseWheel>` binding + region check so all 8 works reach.
- [ ] **5. Real popup behavior** — auto-dismiss on focus loss, pinned
      near tray; editor dialogs must not trigger dismiss.

## PARK-IN-^ trial (2026-09-05 evening) — verdict: STILL BROKEN

Per-work tray icon on Hide + click-to-restore + auto-remove, all
headless-verified (synthetic-click e2e PASS). Live: 3 parks of
Hamster-Clint, window never came back. Ranked hypotheses: dead-icon
clicks silent no-op / restore lands behind windows / Clint
single-console shape vs token coverage / sweep-vs-restore race.
Needed from user (never arrived): green icon count, click behavior.
Superseded by the headless doctrine (see `windows.md`) — a parked
window whose process dies is unrecoverable by design; Restart is the
way out.
