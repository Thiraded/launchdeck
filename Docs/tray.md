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

## Global hotkey (2026-09-06)

One key for the tray itself (default **Alt+W**, changeable in Settings
— the ⌨ button; stored under manifest `settings.hotkey`): toggles the
dashboard from anywhere (`RegisterHotKey` on the tray window,
`WM_HOTKEY` -> `toggle_ui`). Taken keys are logged, never fatal, and
_poll retries every 15s until registered. Unregistered on quit.
Thread rule (2026-09-06 root cause of every "taken" before it):
`RegisterHotKey` must run on the window's OWNER thread -- direct calls
from the tk thread fail with 1408, which used to be misreported as a
conflict. Registration is therefore marshalled via `SendMessageTimeout`
(`WM_APP_HOTKEY_REG`, mods in HIWORD, magic `HOTKEY_OK` back because
`DefWindowProc`'s 0 must never read as success).

## Popup behavior (backlog #5, revised 2026-09-06)

Borderless (`overrideredirect`, no title/X — clicking elsewhere
dismisses, so chrome is dead weight), pinned bottom-right, topmost.
Dismiss choreography: clicking the **log viewer** keeps both windows;
clicking the **dashboard** closes open log viewers (`FocusIn`); clicking
**anywhere else** closes everything (`FocusOut` tree check + hide).
Task/group editors open like the log viewer (measured size, left of
the dashboard when it fits). All three are ONE popup class
(`_track_popup`): clicking the dashboard closes them, clicking
elsewhere closes everything, clicking one of them keeps all.

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

## Dashboard look (2026-09-06)

Single-line compact rows (default; `settings.compact=false` keeps the
roomy two-line card): status edge + dot + title + status on one line,
clicking the label toggles Start/Stop. Icon-only actions are 26px
circles snug to the glyph (canvas oval+text — tk has no round Button):
blue ▶ start, ⏹ stop, ☰ log, ↻ restart, ✎ edit, red 🗑 delete.
Text buttons stay rectangular (+ New / + Group / Start all / Save…).
Settings holds Theme (dark/light, log viewer stays dark) + compact
toggle; a theme switch rebuilds the popup (`_rebuild`, retires the old
`_poll` via generation counter). All popups (log viewer, editors,
settings) are borderless (`_popup_shell`: hairline edge + custom
header with title + ×, drag by the header) — no OS title bar anywhere.

## Transitional states + log toggle (2026-09-06)

Every Start/Stop/Restart/Hide/Start-all lands instantly: the row shows
`starting…`/`stopping…`/`restarting…`/`hiding…` in accent + the status
line names the work, on the same tick as the click (no waiting for the
scan). The pending mark also guards double-clicks — re-firing while
pending just says `already starting…`, so a fast double Start can
never spawn twice. ☰ is a per-work toggle now: second click closes
that work's viewer instead of spawning a duplicate (`_log_wins`;
×/dismiss/changing theme all unregister).

## Custom order + status icon (2026-09-06)

Ordering lives in the editors, not on the rows: the group editor has
an Order list (▲▼ moves, membership ticks sync both ways) and the
task editor has ↑ Up / ↓ Down. Manifest order IS the display order;
editor saves never re-sort (`self_test` guards the no-sort).
Fork-twice is safe: the prefill label bumps ("copy 2") and creation
mints a fresh id (`_unique_id`) instead of overwriting the first copy.
Groups collapse accordion-style (▸/▾ header, choice persisted in
`settings.collapsed`); collapsing only unpacks the kids container,
so rows keep their widgets and there is no rebuild blink.
The work icon carries the state color itself
(green running / dim stopped / blue transitional) and the dot is
gone; edge bar + status word back it up, so nothing is lost even
where Windows renders the emoji in full color.

## Confirm-then-clear + in-place refresh (2026-09-06)

No more blue→white→green: a transitional mark clears only when the
live snapshot CONFIRMS it (or after 20s), and every action wakes the
monitor (`_rescan` event) so confirm lands in ~1s instead of the
next 3s tick. Refresh is surgical now — same layout updates text and
colors in place (`_rows` refs + circle `recolor`); only a structural
change (add/remove/move/label/group/theme) rebuilds the tree, keyed
by `_struct_sig`. No destroy-all means no blink. (If tkinter's
in-place ever hits its limits, the escape hatch is a retained-mode
UI — customtkinter, PyQt, or an Electron/Tauri shell — but nothing
today needs it.)

## Duplicating (2026-09-06)

No clone button on the rows — forking lives in the creation flows:
+New has "Fork from" (prefills label/steps/vars/group/icon, label +
" copy" so save mints a fresh id), +Group has the same for groups,
and the edit dialogs have a Duplicate button (work / group) that
clones in place right after the original. Pure prefill helper
`_work_to_form` is headless-tested; the manifest write path is
covered with a byte-exact restore.

## Detached-only (2026-09-06)

Hide is retired, never coming back: every editor save stamps
`"run": "detached"`, rows and the tray menu show Log only (the
windowed branch is gone), and `_do_hide` is a loud stub so any
stale caller fails visibly instead of silently. The core
hide/show/park backend stays dormant underneath (its tests still
pass) — ripping it out is a separate job with no UI payoff.

## VSCode tracking (2026-09-06)

Stock `code.exe` is single-instance: opening a folder from the CLI
only signals the running instance, so the project path NEVER lands
in any persistent CommandLine — `match: Code.exe` lit every VSCode
work at once, and worse, Stop seeded kills on Code.exe (NOT in the
protected GUI set) taking every VSCode window down. Fix: each
tracked VSCode work launches its own profile
(`--user-data-dir %LOCALAPPDATA%\wc-vscode\<id>`, stock extensions
shared via `--extensions-dir`) and matches on that unique dir
fragment. Dots track per-project, kills stay inside that instance
tree, stock VSCode is never touched. First Start opens a fresh
profile window (sign in for Settings Sync); old windows are
unaffected. A fresh profile is vanilla (default dark): pre-seed it by
copying the stock `%APPDATA%\Code\User` settings/snippets/profiles
into each `%LOCALAPPDATA%\wc-vscode\<id>\User` (extensions are
already shared via `--extensions-dir`, so the theme comes along).

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
