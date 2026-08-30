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

### 4.4 wc_tray.py — system tray (added 2026-08-30)
**Goal:** hide the wc console to a system-tray icon; pop a balloon when a
launched work is detected live. Press `h` in wc → tray, left-click toggles
window, right-click menu Show/Hide/Quit. X still really quits.

**Critical ctypes traps found in the field (do not regress):**
1. `kernel32.GetModuleHandleW(None)` MUST have its prototype set
   (`argtypes=[c_wchar_p]`, `restype=c_void_p`). Default 32-bit `int`
   return truncates the 64-bit handle on x64 Python → `CreateWindowExW`
   silently returns NULL → tray "not available" with no error.
2. The tray window CANNOT be `HWND_MESSAGE`. `TrackPopupMenu` requires a
   real top-level window that can be `SetForegroundWindow`-ed; on a
   message-only window, the menu pops but clicks vanish. Use
   `WS_POPUP` + `hWndParent=None`.
3. Popup-menu items deliver via `WM_COMMAND` with the command id in
   `wParam` low word. `WndProc` MUST handle `WM_COMMAND` or "Show /
   Hide / Quit" are dead.
4. For "Quit" from the tray, don't `os._exit(0)` blindly — wc's main
   loop is blocked in `get_key`. Write a synthetic Esc to the console
   input buffer (`WriteConsoleInputW` + `KEY_EVENT`) so the loop unwinds
   cleanly and the preset saves. Fall back to `_exit` only if that fails.
5. Diagnostic log lives at `wc_logs/tray.log`; each step of `_run` and
   `GetLastError` codes are recorded so future failures are visible.

**Tricky truth:** `wc_tray.hide_console` only hides the **wc** console
(`GetConsoleWindow()` of the wc process). It does NOT hide the .bat
windows each work opened (per AGENTS.md rule: works stay visible). So
pressing `h` cleans up the wc TUI; the work windows stay on screen —
that's the intended split.

### 4.5 kill_work — process tree (added 2026-08-30, after 2 stale-kill bugs)
**Original problem:** `kill_work` matched CommandLine tokens and Terminated
those PIDs only. For works like `gpt-mcp` whose bat spawned a nested
`start "X" cmd /k npx ...`, the cmd host window did not contain the
match token, so the npx child died but the cmd window stayed open as
a zombie. Reported by user: "kill says Killed but terminal stays alive".

**Fix:** Walk the process tree in PowerShell, both directions:
1. seed = any PID whose CommandLine contains a match token
2. walk descendants of seeded PIDs (BFS via `$children` map)
3. walk ancestors of seeded PIDs up to (but not past) `$me` (the
   PowerShell's own PID) and never into `powershell*`
4. For each *top-of-tree* cmd.exe in the kill set, `Terminate` it (this
   is the user's visible window -- Terminate the cmd host directly, not
   just its child npx). The conhost attached to the cmd is reparented
   to `wininit` when the cmd dies, so it closes too.
5. Belt-and-braces: re-query the top cmd.exe PIDs and `taskkill /F /T`
   each. `/T` kills the whole tree (cmd + npx + conhost) in one shot;
   this is what reliably closes the visible window.

**Critical PowerShell traps hit while writing this (do not regress):**
1. `-Command` on the command line CANNOT host multi-line `while`,
   `foreach`, etc. — it parses as one statement. The fix is to write
   the script to a temp .ps1 and use `-File`. Trying to be clever with
   `& { ... }` still fails because the top-level parser tokenizes each
   `;`-separated fragment as a complete statement.
2. **`$PID` is read-only.** Using `$pid` (any case) as a `foreach` loop
   variable raises `Cannot overwrite variable PID because it is
   read-only or constant` — and because we wrapped the body in
   `SilentlyContinue` + `-File`, the error was SWALLOWED silently. The
   `foreach ($pid in $kill)` block never executed. Use `$kpid` or any
   other name.
3. `Get-CimInstance Win32_Process` is the right API (not `Get-Process`).
   `Get-Process` doesn't expose CommandLine; you only get truncation.

### 4.6 h key — hide the cursor's WORK terminal (added 2026-08-30)
**Original problem (re-think):** `h` was hiding the **wc** console to
the system tray. User then asked for the tray icon removed and to hide
the work terminal instead, because hunting for the work window behind
several open terminals is the actual pain point.

**New behavior:**
- `h` on a work line that is `[-]` (running) -> find the HWNDs of that
  work's process tree and `ShowWindowAsync(SW_HIDE)` them all.
- `h` again on the same work (or any work) -> restore with
  `ShowWindowAsync(SW_RESTORE)`. Hidden state is tracked per work in
  `_hidden_hwnds: dict[key -> list[hwnd]]`.
- `h` on a `not-running` work line -> status message "not running,
  nothing to hide" (no-op).
- The wc console is NEVER touched. No tray, no minimize, no nothing.

**How we find the HWNDs (`find_work_hwnds` in wc_core.py):**
1. PowerShell: enumerate `Get-CimInstance Win32_Process`, collect
   PIDs whose CommandLine contains a work match token. Returns the
   PIDs as plaintext.
2. PowerShell: walk each PID up to its top-of-tree ancestor (skipping
   self, powershell*) so we also pick up the `cmd /c start ""` host.
3. ctypes `EnumWindows` over all top-level windows; keep HWNDs whose
   `GetWindowThreadProcessId` PID is in the set AND
   `IsWindowVisible(hwnd)`.

`wc_tray.py` is no longer imported. The file is left on disk for
reference but is dead code -- do not bring it back unless we need a
tray again.

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

---

## 6. Hermes self-discipline — machine-side-effect rule (added 2026-08-30)

**Two prior incidents on the same day, both because I ran broad commands
on a live user machine without checking what would be affected:**

1. **Infinite terminal spawn** — wc launch / kill debugging loop
   launched a runaway chain of windows the user had to manually close.
2. **Killed the user's live windows** — while cleaning up GPT MCP test
   leftovers, I ran `Get-CimInstance Win32_Process | Where-Object {
   $_.CommandLine -like '*GPT MCP*' -or $_.CommandLine -like
   '*modelcontextprotocol*' } | ForEach-Object { ...Terminate }`.
   The user's own Discord, browser, and other open processes were
   also matched by the loose pattern and killed.

**Rule for any future session on this machine (and any user machine):**

Before running ANY command that touches the user's live machine, answer
THESE THREE QUESTIONS in writing in the response BEFORE executing:

1. **What exact PIDs / names / paths will this affect?**
   Write them out. A `Where-Object {$_.Name -like 'cmd*'}` is too broad.
2. **Could any of those be the user's own open app?**
   Discord, VS Code, browser, dev servers, terminals, the IDE, the
   agent's own session — those are NOT test artifacts.
3. **Am I sure this affects only the test target and nothing else?**
   If the answer is "I don't know", STOP. Narrow the query (exact
   PID, exact path, exact exe name) or ASK the user.

**Default behavior:**

- Narrow + exact (specific PID, specific path) over broad pattern
- Show the target list to the user BEFORE killing, when in doubt
- Never run a sweeping `Get-CimInstance | Where {...broad...} |
  Terminate` on a live user machine
- Test artifacts (fake workers, leftover cmds from previous tests) are
  fine to clean up — but verify each one is actually a test artifact
  (its parent / creation time / CommandLine signature) before Terminate
- The user's open windows and dev sessions outrank my convenience. If a
  cleanup step feels risky, skip it and ask.

**Applies to:** taskkill, `Get-CimInstance | Invoke-CimMethod Terminate`,
`Stop-Process`, `sc stop`, `net stop`, `reg delete`, `Remove-Item` (broad
globs), `Format-Volume`, anything that mutates user-visible state on
the host machine.
