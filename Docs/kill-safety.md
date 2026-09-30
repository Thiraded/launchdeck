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
3. **Token hygiene.** Kill seeds use the recorded runner path/name first;
   generic executable names, short tokens, and bare work ids are rejected.
   If the runner is gone, a configured path token must resolve to matching
   branches under one common dev parent present in the process table; roots
   with no shared parent are refused. Multiple exact generated runner roots
   are treated as duplicate instances of that work, never as a union with a
   second identity token. When a runner is present, an additional manually
   started root is accepted only when its command line names a file below the
   configured project path; a path mentioned only as `--env-file` or a
   working-directory option is ignored. Codex trusted workers whose command
   line only uses the project as a working directory are never seeds.
   Detection via
   `titles_for`/`is_running` is intentionally broader and is unaffected.
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

## Job Objects (Phase 1, 2026-10-01) — `deck/core/jobs.py`

A detached work whose steps are ALL `terminal` is launched suspended,
assigned to the named job `Local\launchdeck-job-<id>`, then resumed.
Every descendant is a job member, so for these works:

- `is_running` = the job has a live counted member (conhost and
  never-seed names are not counted). Token scan is the fallback only.
- `kill_work` = CTRL_BREAK to the work's console group (sent from a
  throwaway helper that attaches to the console), 5 s grace, then
  per-PID `TerminateProcess`, each PID re-checked with `IsProcessInJob`
  right before (no PID reuse). No tokens, no BFS, no revalidation scan.
  `dry_run` returns the member list.
- Never-seed names (rule 5) are never counted and never killed, even
  as members: `npx` tools can open a browser, and a browser that was not
  running yet is born INSIDE the job.
- `app` steps (Unity Hub, VSCode, Brave `.lnk`) are NOT jobbed: GUI
  handoff can pull the user's app into the job. They stay on the legacy
  passes below.
- No `KILL_ON_JOB_CLOSE`: works outlive the deck. A job's name dies with
  its last handle even while members run, so a handle copy is planted in
  the root child; a restarted deck reopens the job by name.
- Store Python (WindowsApps) relaunches through package activation and
  escapes the job. Works run node/npm, which stay inside; don't write a
  jobs test around `sys.executable`.
- Works started before this change (or by hand) have no job: they use
  the legacy path until their next Start from the deck.

## The three close passes (§4.9) — legacy (non-job works)

Over the SAME downward-only set: (1) graceful `taskkill /PID` (no `/F`,
console close request); (2) Alt+F4 `WM_CLOSE` to HWNDs owned by the same
downward set and its console-host children; the kill path does not walk
back into a user's hosting shell; (3) after a bounded 2.5s wait, revalidate
the runner and unchanged descendants, then run the per-PID `/F` sweep
(`gowc kill` when present; gone PIDs report and are ignored). A final scan
must confirm all target PIDs are gone before `clear_hidden_work` +
`unregister`; otherwise the registry is retained and the UI reports a
blocked stop.

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
