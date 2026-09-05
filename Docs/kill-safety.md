# Kill safety — rules written in incidents

## The 2026-09-05 incident (do not regress)

The old kill walked ancestors + auto-added the bare work id as a token
(a 1-char id matches the whole machine). It taskkilled `cmd.exe`
ancestors across the system — the agent's own session shell, Discord,
VSCode, and work windows. Two rules came out of it that can never be
relaxed.

## Hard rules

1. **DOWN ONLY.** Seeds + BFS over the children map. Never walk up to
   ancestors for killing.
2. **PROTECTED set.** Scanner + launcher python PID + every ancestor of
   the launcher up to the root. Never in the kill list, even on token
   match. `powershell*` is never killed (hosts user sessions).
3. **Token hygiene.** `kill_tokens_for` adds the bare work id only if
   `len >= 4`; `kill_work` drops every token shorter than 3 chars.
   (Detection via `titles_for`/`is_running` is unaffected.)
4. **`dry_run` first.** `kill_work(work, dry_run=True)` returns the
   sorted kill PID list WITHOUT killing. Show it and get approval
   BEFORE any real kill when in doubt.
5. **NEVER-seed GUI list** (shared with hide-seeds): brave, chrome,
   msedge, firefox, opera, vivaldi, arc, explorer, discord, slack,
   teams. A token can match a browser tab URL or chat content
   (proven: `omniroute` seeded Brave PID 4524 via tab URL).
6. **No `/T`, ever.** Per-PID `taskkill /F` (or one `gowc kill` call).
   Tree-kill cascades into shared conhosts of unrelated windows.
7. **No `WINDOWTITLE`**, no `Get-Process` (no CommandLine there) —
   `Get-CimInstance Win32_Process` (or `gowc scan`) only.

## The three close passes (§4.9)

Over the SAME downward-only set: (1) graceful `taskkill /PID` (no `/F`,
console close request); (2) Alt+F4 `WM_CLOSE` to every HWND in the
guarded owner set (a leftover `cmd /k` host can be an *ancestor* of
every seed — process-only DOWN kill can't reach it, closing its window
terminates it via the console); (3) after a bounded 2.5s wait, per-PID
`/F` sweep (`gowc kill` when present; gone PIDs report and are ignored).
Ends with `clear_hidden_work` + `unregister`.

## Machine-side-effect rule (all sessions, all machines)

Before running ANY command that touches the user's live machine, answer
in writing BEFORE executing:

1. **What exact PIDs / names / paths will this affect?** Write them out.
2. **Could any of those be the user's own open app?** Discord, VS Code,
   browser, dev servers, terminals, IDE, agent session — NOT test
   artifacts, even on pattern match.
3. **Am I sure this affects only the test target and nothing else?**
   If "I don't know", STOP — narrow it or ASK.

Narrow + exact over broad pattern. Show the target list BEFORE killing
when in doubt. Test artifacts are fine to clean up only after verifying
each one IS a test artifact. User windows outrank convenience.

## PowerShell traps (hit while writing kills — do not regress)

- **`$PID` is read-only.** Never as a loop variable (`$kpid` instead);
  under `SilentlyContinue` the error vanishes and the loop silently
  never runs (rc=0, nothing happens).
- **`-Command` can't host multi-line `while`/`foreach`.** Write temp
  `.ps1` + `-File` for non-trivial scripts.
- **f-string braces:** double ALL PowerShell `{`/`}` in Python f-strings.
- **Debug "did nothing":** capture stderr to a file; rerun the exact
  script via manual `powershell -File`.
