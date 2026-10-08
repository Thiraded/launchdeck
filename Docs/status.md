# Status — current state and open gates (updated 2026-10-08)

## 2026-10-08 — Speed Dial (FAB) UI with Bloom Animation, Opposite Exit Door, and Independent Floating Dashboard

- Replaced direct rectangular dashboard toggle with minimal Speed Dial (FAB Menu) inspired by modern floating action menus (`deck/ui/speeddial.py`):
  - Left-click on floating desktop button toggles Speed Dial expanding with smooth 60fps cubic ease-out bloom animation.
  - Features stack in one direction (Works Dashboard, Away Note, Sticky Note, VS Code Projects, Localhost Manager).
  - Dedicated **Exit** action with door icon (`assets/icons/door-open.svg`) in red plate blooms out on the **opposite** side of the launcher.
  - Floating button switches dynamically between lightning bolt (`zap`) and close (`x`). Drag-to-reposition remains smooth.
- Implemented suite of convenience tools:
  - **Localhost Manager** (`deck/ui/localhost_mgr.py`): Unified dev browser links and 1-click port killer into a single popup with live status indicators (🟢 / ⚪), process names, PID inspection, and custom port freeing.
  - **Multi-Instance Persistent Sticky Notes** (`deck/ui/stickynote.py`): Draggable, always-on-top notes with editable titles in the header, `+` button to spawn sibling notes, `×` to delete notes, auto-saving to `launchdeck_logs/sticky_notes.json`.
  - **Project Quick Jump** (`deck/ui/quickjump.py`): 1-click launcher for workspace directories (LaunchDeck, HamsterWorld, Midnight-Rider, HammonQuest) in VS Code, with clean minimal labels.
  - **Freely Floating Works Dashboard**: Works dashboard floats completely independently from the launcher button (does not follow launcher when moved), remembers user's dragged position, and initial position sits cleanly beside the launcher/dial zone with zero overlap.
  - **Unified Button Anchoring**: All new popups (`Localhost Manager`, `Projects`, `Away Note`) anchor directly beside the launcher button using unified placement geometry.
- Away Message feature (`deck/ui/away.py`):
  - Interactive prompt dialog (`open_away_prompt`) with multi-row wrapping flow layout for preset chips.
  - Fullscreen darkened overlay (`AwayOverlay`) with smooth animated fade-in / fade-out up to 0.92 alpha, clean AFK badge, and keyboard/mouse dismissal.
- Validation: 65 tests pass across the test suite (`test_ui_smoke.py`, `test_tray_foundation.py`, `test_kill_safety.py`). `test_no_local_shadows_a_module` passed clean. Zero subprocess console flashing.

## 2026-10-06 — drag restoration and seamless topmost

- Fixed desktop button drag and repositioning: removed redundant
  `target_win.attributes("-topmost", True)` from `enforce_win32_topmost`.
  Calling Tkinter's `attributes("-topmost", True)` during or immediately after
  geometry updates invoked Tk's internal Windows wrapper sync, which clobbered
  the pending coordinates and snapped the window back to its initial position.
- Win32 `SetWindowPos` (`HWND_TOPMOST | SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW`)
  maintains true OS-level topmost without interfering with Tkinter's geometry.
- Periodic 500ms topmost ticker is paused during active drag (`_press is None` guard),
  and per-pixel drag calls now update geometry smoothly without redundant OS calls,
  re-asserting topmost cleanly on release.
- Validation: 53 tests pass (`test_ui_smoke.py`, `test_tray_foundation.py`,
  `test_kill_safety.py`). Self-test passes clean. Live drag simulation verified.

## 2026-10-05 — true always-on-top reinforcement and startup fix

- Desktop launcher and Dashboard now reinforce Win32 `HWND_TOPMOST` via
  `SetWindowPos` (`SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW`).
  Root cause of missing topmost at startup: Tkinter recreates/realizes the OS
  window wrapper during initial event mapping, so pre-mapping `attributes("-topmost", True)`
  left the window below active apps until clicked once.
- Continuous topmost enforcement: `DesktopLauncher` runs a 500ms ticker and
  enforces topmost on enter/press/drag/release; `Dashboard` reinforces on `_poll`
  while visible. Windows minimized or obscured by Win+D / Show Desktop are
  restored non-intrusively via `SW_SHOWNOACTIVATE`.
- Multi-monitor bounds: launcher position is clamped using virtual screen metrics
  (`SM_XVIRTUALSCREEN`, `SM_CXVIRTUALSCREEN`, etc.) instead of primary monitor width.
- Auto-dismiss guard: `_maybe_autodismiss` ignores clicks while the launcher button
  is pressed, eliminating the toggle flicker race. Clean exit with `os._exit(0)`
  prevents ghost processes from locking `Local\launchdeck-dashboard`.
- Validation: 53 tests pass (`test_ui_smoke.py`, `test_tray_foundation.py`,
  `test_kill_safety.py`). Self-test passes clean.

## 2026-10-02 — desktop launcher source update (not live yet)

- Source now starts with a draggable, always-on-top lightning button. It opens
  the dashboard beside itself; clicking it again hides the dashboard and all
  child popups. The taskbar tray icon is removed from the new launch path; a
  hidden native host still owns Alt+W.
- The running deck processes listed below are still on the old build. They were
  not restarted during this change, so the floating button has not had a live
  Windows smoke check yet.
- Validation: `py_compile` passed for the changed Python modules; the guarded
  safe suite passed all 52 tests. The icon preview was checked at its 56px
  render size.

## 2026-10-02 — single UI and shortcuts

- `launchdeck` now starts the dashboard UI; the terminal frontend was removed.
  Desktop and Startup shortcuts point to `D:\launchdeck\launchdeck.bat`.
- Dashboard processes 16912 and 19960 are still running pre-change code.
  Active work runners are PIDs 13364, 5932, and 31128; their command lines and
  registry entries reference runner files under the previous runtime folder.
  Keep that folder and the old helper executable until these processes stop
  naturally. The updated source writes to `launchdeck_logs/` and uses the
  renamed helper after the old dashboard exits.
- The old profile directory was moved after confirming no `Code.exe` command
  line references it. The next LaunchDeck start uses the renamed profile path.

## 2026-10-01 — Job Objects (pending live check)

Next steps + live checklist: `Docs/plan.md` sections 6 and 9.

- Detached all-terminal works (hamster-*, hamsterquest, hamstermap,
  omniroute-cli, gpt-mcp) now start inside a named Job Object; Stop is
  CTRL_BREAK + job-member kill (`Docs/kill-safety.md` "Job Objects").
  Proven by `test_jobs.py` (own node children only). NOT yet proven on a
  real work: the next Start of each work from the NEW deck is its first
  jobbed launch. Works already running were started the old way and keep
  the legacy Stop until restarted.
- Same day: core split into `deck/core/` behind the `launchdeck_core`
  facade (old vs new core compared on the real manifest: identical), and
  the dormant hide/show/park subsystem + console `h` key removed.

## 2026-09-30 — pending live check

- Dashboard moved to `deck/ui/` and redesigned with SVG icons + DPI
  awareness. Tests: kill_safety + tray_foundation + ui_smoke (fake
  manifest, 54 OK). A Dashboard rendered on the fake manifest was
  checked visually at 100% scale, dark + light. NOT yet verified: a
  live deck restart, 125/150% scaling, the tray hotkey after the DPI
  change.

## Live right now

- hamster-clint: RUNNING (vite :5175, HTTP 200 — started through the
  steps path after the setlocal fix; proves batless launch end-to-end).
- hamster-server: state unknown since the morning full-close test --
  check the dashboard dot before touching :3000 consumers.
- deck dashboard: RUNNING on the old tray build; source changes are not loaded
  until that instance exits and the updated launcher starts.
- hamsterquest / mr-* / omniroute-* / gpt-mcp: stopped (never Started
  on the steps path yet -- each first Start is still unverified live).

## Verified working

- Detached steps launch for all 8 works (config has no `bat` keys;
  legacy `.bat` files removed 2026-09-06). Clint proven live (HTTP 200).
- setlocal+npm cwd trap found by bisection (T1-T11) and fixed
  (generated bats emit no `setlocal`); recorded in `bat-template.md`
  and the launcher skill.
- Log viewer: fresh log per Start, live 1s color follow, clickable
  URLs, pinned beside the dashboard.
- Dashboard: wheel scroll, borderless, focus choreography (viewer
  clicks keep both, dashboard clicks kill popups, outside kills all),
  task/group editors + settings in the same popup class.
- Editor: inline steps/vars, group create/rename/delete, hotkey setting.
- self-test: scroll/wheel, editors, slug, dismiss, hotkey parse +
  marshal contract, borderless, popup class -- all PASS headless.

## Open gates (need a human at the keyboard)

1. After the existing deck instance exits, start the updated deck and verify
   the floating button, drag-and-follow popup, click-again dismissal, and Alt+W.
2. Start each stopped work once from the dashboard (server, quest,
   unity, vscode, cli, web, mcp) -- first live boot on the steps path.
3. The old hide-quality and full-close gates are PRE-detached doctrine --
   hide/minimize no longer applies to detached works. The console UI smoke
   gate retired with the terminal frontend on 2026-10-02.
4. `test_launchdeck_core.py` -- still blocked while live works run.

## Known issues (accepted, documented)

- deck uv-venv "twin" (FIXED 2026-09-30, unverified live): two pythonw
  processes is NORMAL -- the venv redirector (parent, never runs Python)
  + the real deck (child). The old birth-time election could make the
  real deck exit at boot; the reaper looked for children, never the
  parent. Replaced by the named mutex `Local\launchdeck-dashboard`.
- `registry.json` dropped keys (FIXED 2026-09-30): truncating writes +
  unlocked read-modify-write races, not "churn". Now atomic replace +
  in-process lock + named mutex `Local\launchdeck-state` (manifest too).
  Still runtime state -- never commit.
- omniroute-cli/web detection-positive on Brave tab URLs (cosmetic;
  do not "fix" by broadening tokens).
- Pre-existing orphans (PARK-era invisible cmd) -- never auto-touched.
