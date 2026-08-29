# AGENTS.md — Work Combo (wc) launcher suite

> Windows desktop launcher for the user's dev "works". Plain Python TUIs
> (no external deps) driven by `works.json`. This file documents the
> project AND the current rework task. Read it before touching `wc*.py`.

---

## 1. What this project is

A single-screen launcher that starts/stops the user's development servers and
apps. Each "work" is a Windows `.bat` that opens its OWN visible console
window.

**Current shape (post-rework): ONE TUI does both jobs:**

- **wc** (work combo) — the ONLY tool. SELECT works (Space → `[X]`) and
  `Enter` either **KILLS** a running work (`[-]`) or **LAUNCHES** a not-running
  one. Lists live running state with a `[-]` marker.

`kc` (the old separate kill tool) is **being deleted** — its role is merged
into `wc`. See §4.3.

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
| `wc_core.py` | Pure logic shared by the TUI: manifest load, detection, run/kill, registry, model, state machine. NO UI. |
| `wc.py` | The ONE TUI: SELECT (Space → `[X]`) + `Enter` KILLS running `[-]` / LAUNCHES not-running. Live `[-]` via background thread. |
| `test_wc_core.py` | Headless integration test (fake workers, live detection, kill, state machine). |
| `wc.bat` / `wc.lnk` | Launcher for `wc.py` (hermes venv python). Opens a real visible window. |
| `registry.json` | Runtime: written by wc when a work launches; read to list running. |
| `wc.settings.txt` | Selection preset (lowercased work ids), loaded on start / saved on quit. |
| `kc.py` / `kc.bat` / `kc.lnk` | **DELETED** — kill role merged into `wc.py`. Do not resurrect. |

---

## 3. Current architecture

### State tokens (selection column) — `wc_core.py`
```
OFF         " "   [ ]  not selected
ON          "x"   [X]  selected to act on (Space toggles)
RUN         "-"   [-]  detected as actually running (live, INFO only)
```
`[-]` is info only — you cannot "cancel" it by keypress; to stop a running
work you select it `[X]` and press Enter (which kills it).

### Detection (`scan_commandlines` + `is_running`)
A SINGLE PowerShell call to `Get-CimInstance Win32_Process` returns ALL
command lines once; `is_running`/`live_running`/`registry_running`/`poll_launch`
reuse that list and match tokens in pure Python (no per-work rescan). This is
~9x faster than the old per-work loop and does NOT block the key loop.
Excludes `powershell*` and self PID. `WINDOWTITLE` is not used.

### Launch (`launch_work`)
`cmd.exe /c start "" <bat>` → spawns a new **visible** console window.
(`start` must have exactly one `""` title placeholder — a stray second `""`
made it open Explorer instead. Do not regress.)
`wc` no longer auto-closes after launch (it is a persistent manager now, not a
transient launcher).

### Kill (`kill_work`)
PowerShell `Invoke-CimMethod -MethodName Terminate` on every process whose
CommandLine matches the work's tokens (covers the console `cmd` AND child
`node.exe` from `npm run dev`). Then `unregister(work)`.

### Model / groups
A group has NO state of its own: `group selected <=> any child selected` (pure
OR). Space on a group toggles ALL children; clearing any child clears the group.
`build_model` skips works that are members of a group (no duplicate standalone).

### wc.py behavior today
Inline tree, cursor nav (Up/Down), `Space`/`t` toggles select `[ ]`↔`[X]`,
`Enter` acts on every `[X]` node — KILL if running (`[-]`) else LAUNCH.
`Esc`/`q` quit. Saves preset to `wc.settings.txt` on exit.
Live `[-]` refreshed by a background thread (never blocks keys).

### Key capture (IMPORTANT — see §4 bug)
`get_key()` reads the console INPUT buffer directly via `ReadConsoleInput`
(ctypes), NOT `msvcrt.getch()`. QuickEdit/Mouse console modes are disabled on
startup so a mouse click inside the window does not freeze keyboard input.

---

## 4. TASK — merge kill into wc, delete kc

**Why:** Keeping kill in a separate `kc` tool meant the user had to juggle two
windows and `kc` "couldn't be used". Decision: collapse everything into `wc`.

### 4.1 wc.py — SELECT + KILL + LAUNCH (done)
- Space toggles `[ ]`↔`[X]` (select what to act on).
- Enter on a `[X]` node: if running (`[-]`) → KILL; else → LAUNCH.
- Live `[-]` marker via background thread.
- Key capture via `ReadConsoleInput` + QuickEdit disabled.

### 4.2 kc — DELETED
`kc.py`, `kc.bat`, `kc.lnk` removed (commit `f4aa58f`). Kill lives in `wc` now.
Do not bring kc back.

### 4.3 OPEN BUG — wc select+kill does NOT work in the real window yet
Status: **NOT FIXED / UNVERIFIED.**
- The state machine is proven correct via headless simulation (Space → `[X]`,
  Enter → kill/launch, Esc → quit all work).
- BUT on the user's actual machine, pressing `Space` in the `wc.bat` window
  does NOT toggle `[ ]`→`[X]` — i.e. key capture fails in the live window.
- Attempted fix: switched `get_key()` to `ReadConsoleInput` (ctypes) and
  disabled QuickEdit (commit `d04d0c6`). This is UNVERIFIED — the user must
  re-test `wc.bat`. If it still fails, the window is likely not receiving
  console input (focus / spawn issue) and we must fall back to a different
  input path (e.g. non-blocking `kbhit`/`getch` loop, or reading from a pipe).
- **Do NOT claim DONE until the user confirms Space-select + Enter-kill works
  in the real `wc.bat` window.**

---

## 5. Verification (how to prove DONE)
- `python test_wc_core.py` passes (model build, detection, group OR, kill-via-group,
  Space OFF→ON → Enter acts). — **PASSING.**
- Headless key-sequence simulation confirms the state machine: Space → `[X]`,
  Enter → kill/launch, Esc → quit. — **PASSING.**
- **OUTSTANDING:** Manual smoke on Windows — open `wc.bat`, press `Space` on a
  work, confirm `[ ]`→`[X]`, press `Enter`, confirm a running `[-]` work is
  KILLED (and a not-running one is launched). This is the gate for DONE and is
  currently failing / unverified.
- Confirm killing covers both the `cmd` host and child `node.exe` (npm dev).
- Confirm wc never hangs the host: `scan_commandlines` is a single scan, the
  live `[-]` monitor is a background thread with a 2s sleep (finite), no
  unbounded `while True` in the key path.
