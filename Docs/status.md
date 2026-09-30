# Status — current state and open gates (2026-09-06 evening)

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
- deck (tray): RUNNING, but on pre-marshal code -- needs ONE more restart
  to load the hotkey-marshal + borderless + popup-class build.
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

1. Restart the deck -> Alt+W must toggle the dashboard (then the agent
   marshal-probes the live tray window to confirm end-to-end).
2. Start each stopped work once from the dashboard (server, quest,
   unity, vscode, cli, web, mcp) -- first live boot on the steps path.
3. The old standing gates (hide-quality, full-close, console smoke)
   are PRE-detached doctrine -- hide/minimize no longer applies to
   detached works. Needs a Docs decision (retire or re-scope), not a
   keyboard drill.
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
