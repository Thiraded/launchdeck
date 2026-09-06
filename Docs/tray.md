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

## Detached works (`"run": "detached"` — docker-logs model)

The default for ALL works since 2026-09-06 (user moved the whole
suite off visible windows). No console at all (`CREATE_NO_WINDOW`);
output goes to `wc_logs/<id>.log`, and the dashboard shows a log
viewer instead of Hide/Show (wc console `h` reports "no window"
for detached works). Viewer rules:

- Fresh log per Start (truncate + `[wc] launch …` marker) — old runs
  never pollute the tail.
- Live follow: 1s poll, new bytes appended only (no full redraw);
  a file shrink means a fresh launch, so the view reloads.
- ANSI colors render as text tags on a dark surface (server logs
  assume a dark console); widget capped at 2000 lines.
- URLs are clickable (underline + hand cursor, opens the default
  browser) — e.g. vite's `http://localhost:5175/`.
- Parsing lives in `wc_core.ansi_runs` (pure, tested); `wctray`
  only maps names to colors.

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
- [x] **2. Inline commands + variables** — DONE 2026-09-06.
      Editor has Commands (one per line, `app:` prefix = App step)
      + Vars (`NAME=value`) boxes; core `materialize_steps` writes
      `wc_logs/wc-gen-<id>.bat` (`set` lines, terminal lines, `app:`
      via `start`), so launch/log/detect/kill follow the .bat path
      (gen name added to kill tokens). Hamster-Clint migrated first.
      2026-09-06: ALL works are steps+vars, `bat` keys removed from
      config (files remain on disk, unused).
- [x] **3. New Group** — DONE 2026-09-06 (`+ Group` button, per-group
      rename/delete, label + member checklist dialog, `core.save_manifest`
      as the single writer; delete keeps works standalone).
- [x] **4. Dashboard scroll** — FIXED 2026-09-06 (root cause was NOT
      a missing scrollbar: content renders fully, 981px in a 600px
      window, but `<MouseWheel>` was never bound so the wheel did
      nothing and the thin dark bar looked absent. Fix: wheel bound
      on the toplevel, inner frame tracks canvas width, explicit
      scrollregion + view clamp after every rebuild; `self_test`
      asserts region + wheel binding).
- [x] **5. Real popup behavior** — DONE 2026-09-06 (`<FocusOut>` +
      delayed tree check dismisses only when focus leaves the whole
      dashboard tree — editor/log dialogs are child Toplevels so they
      keep it open; re-pinned bottom-right on every show).

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
