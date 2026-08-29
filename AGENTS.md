# AGENTS.md — Work Combo (wc) launcher suite

> Windows desktop launcher for the user's dev "works". Plain Python TUIs
> (no external deps) driven by `works.json`. This file documents the
> project AND the current rework task. Read it before touching `wc*.py`.

---

## 1. What this project is

A single-screen launcher that starts/stops the user's development servers and
apps. Each "work" is a Windows `.bat` that opens its OWN visible console
window. Two TUIs orchestrate them:

- **wc** (work combo) — SELECT works and RUN them.
- **tc** (task combo) — *[target state]* list currently-RUNNING works and KILL them.
  (Today this role is filled by `kc.py`; the rework renames/repurposes it to `tc`.)

The user's standing demands (architectural constraints — do not regress):
- **Inline-tree UI**, one column with `SPACE` indentation for group members.
  NOT a two-pane layout.
- Works launch via `.bat` that open **VISIBLE** windows (never hidden/backgrounded).
- Running-state is detected **live** from process CommandLine via
  `Get-CimInstance Win32_Process`, matching the `.bat` basename (or an explicit
  `match` token). MUST exclude `powershell*` processes and the launcher's own
  PID. `WINDOWTITLE` is unreliable — do not use it.
- `works.json` groups list their members by `id`; a member must NOT also appear
  as a standalone top-level work (no duplication).
- GPT is split into **`GPT Web start`** (tunnel client) and **`GPT MCP start`**
  (MCP Inspector), uppercase labels.
- `wc` is the entry point users launch (via `wc.bat` / `wc.lnk`).

---

## 2. File layout

| File | Role |
|------|------|
| `works.json` | Manifest: `groups[]` (id/label/members) + `works[]` (id/label/bat/match/detect). |
| `wc_core.py` | Pure logic shared by both TUIs: manifest load, detection, run/kill, registry, model, state machine. NO UI. |
| `wc.py` | Work-combo TUI (SELECT + RUN). **Being slimmed down in this task.** |
| `kc.py` | Kill-combo TUI (list running + kill). **Being replaced by `tc.py` in this task.** |
| `tc.py` | *[new]* Task-combo TUI (list running + kill). Target replacement for `kc.py`. |
| `test_wc_core.py` | Headless integration test (fake workers, live detection, kill, state machine). |
| `wc.bat` / `wc.lnk` | Launcher for `wc.py` (hermes venv python, then `pause`). |
| `tc.bat` | *[new]* Launcher for `tc.py` — must open a real window, NOT background. |
| `registry.json` | Runtime: written by wc when a work launches; read by tc/kc to list running. |
| `wc.settings.txt` | Selection preset (lowercased work ids), loaded on start / saved on quit. |

---

## 3. Current architecture

### State tokens (selection column) — `wc_core.py`
```
OFF         " "   [ ]  not selected
ON          "x"   [x]  selected to run
RUN         "-"   [-]  detected as actually running (live)
LEFT_ALONE  "_"   [.]  don't touch on Enter/kill  (tc/kc only)
```

### Detection (`is_running`)
PowerShell one-liner over `Win32_Process`; excludes `powershell*` and self PID;
matches any token in `titles_for(work)` (= explicit `match`, else `.bat` basename).
Used by both wc (to show `[-]`) and tc (to list running).

### Launch (`run_work`)
`cmd.exe /c start "" <bat>` → spawns a new **visible** console window, then
`register(work)` writes `registry.json`.
> Past bug (fixed): a stray second `""` made `start` open the folder in Explorer
> instead of running the `.bat`. Keep exactly one `""` title placeholder.

### Kill (`kill_work`)
PowerShell `Invoke-CimMethod -MethodName Terminate` on every process whose
CommandLine matches the work's tokens (covers the console `cmd` AND child
`node.exe` from `npm run dev`). Then `unregister(work)`.

### Model / groups
A group has NO state of its own: `group selected <=> any child selected` (pure
OR). Space on a group toggles ALL children; clearing any child clears the group.
`build_model` skips works that are members of a group (no duplicate standalone).

### wc.py behavior today
Inline tree, cursor nav (Up/Down), `Space`/`t` toggle select, `Enter` runs
(`[x]`) or kills (`[-]`) the node and its members, `Esc`/`q` quit. Saves preset
to `wc.settings.txt` on exit. **Persists as a menu after every action.**

### kc.py behavior today
Lists only registry entries still alive, `Enter` kills, `t` leaves-alone,
`Esc`/`q` quit.

---

## 4. TASK — split wc/kc into wc + tc

**Why:** wc doing select+run AND running-state+kill is "too much". Separate the
kill/running concern into its own tool (`tc`), and make wc a pure launcher.

### 4.1 wc.py — slim to SELECT + RUN only
- **Remove** the `[-]` (RUN) state and all kill logic from wc.
- wc becomes: pick works/groups (Space), `Enter` runs selected. No running
  detection column, no kill.
- **On `Enter`:** spawn each selected work in its OWN visible window (via
  `launch_work_tracked`, which wraps the real `.bat` in a `wc_logs/<id>.track.bat`
  that tees output to `<id>.log.txt` and writes a `__WC_DONE__ <code>` sentinel),
  then **show per-terminal launch progress** (running -> ready/stable/done/failed),
  then **close wc's own window** (wc exits — transient launcher, not a menu).
  - Consequence: `wc.bat`'s trailing `pause` was REMOVED (wc self-exists).
- **Per-terminal progress semantics** (`poll_launch` in `wc_core.py`):
  - `ready`  — a `ready` marker string (from `work["ready"]`) appeared in the log.
  - `stable` — still alive past `GRACE_SECONDS` with no error/ready (server up).
  - `done`   — `.bat` exited 0 (e.g. Unity finished opening).
  - `failed` — non-zero exit, error keyword in log, or process vanished.
- **ANTI-RUNAWAY SAFETY (do NOT remove):**
  - `launch_work_tracked` never spawns more than `MAX_LAUNCHES` (16) windows
    total, and refuses to spawn a 2nd window for a work already alive
    (`_already_tracked_alive`).
  - `poll_launch` declares `stable` after `STABLE_MAX_SECONDS` (60) so the
    monitor loop is ALWAYS finite.
  - `wc.run_phase` monitor loop has a hard `MONITOR_SECONDS` ceiling and on
    error shows it for only `FAILED_VIEW_SECONDS` then closes. **No `while True`
    without a deadline anywhere in the launch path.**
  - Past incident: an unbounded poll loop + `start` spawning spiked the host.
    These caps exist specifically to stop that class of bug.

### 4.2 kc.py — the kill combo (NOTE: "tc" was a typo; the tool is `kc`)
- `kc` lists **currently-running** works (from `registry.json` — only what wc
  launched) and lets you kill them with `Enter`; `t` leaves-alone; Esc/q quit.
  Flat list (no inline tree). This is unchanged behavior.
- **kc must run in a real visible window** — `kc.bat` was ADDED for this
  (before, kc had no launcher and looked "backgrounded"). `kc.bat` opens a
  console and stays until quit, like `wc.bat` minus the auto-close.

### 4.3 things to delete / rename
- Nothing renamed. `kc.py` is the kill tool (not `tc`). `wc.py` is the launcher.
- `[-]`/`LEFT_ALONE` handling lives ONLY in kc (removed from wc).

---

## 5. Verification (how to prove DONE)
- `python test_wc_core.py` passes (model build, detection, group OR, kill-via-group,
  LEFT_ALONE no-op). Extend it to cover the new wc/tc split if logic moves.
- Manual smoke (Windows): `wc.bat` opens, selecting a group + Enter spawns each
  work's window and wc then closes itself; `kc.bat` opens a window, lists the
  running works (from registry.json), `Enter` kills them and they disappear.
- Confirm killing covers both the `cmd` host and child `node.exe` (npm dev).
- Confirm wc can NEVER hang the host: `MAX_LAUNCHES`, `STABLE_MAX_SECONDS`, and
  the `run_phase` deadline are all in place. No unbounded `while True` in the
  launch path.
