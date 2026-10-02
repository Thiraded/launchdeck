"""kill_work: job-member stop, else the legacy DOWN-ONLY passes (Docs/kill-safety.md)."""

import ntpath
import os
import subprocess
import time

from deck.core import common, store, steps, detect, windows, jobs

def _seed_pids_for_work(work: dict,
                        table: list[tuple[int, int, str, str]],
                        protected: set[int] | None = None) -> set[int]:
    """Find safe root seeds without walking outside a work's identity.

    A registered launch PID is preferred.  Otherwise runner identities may
    select duplicate exact wrappers plus a manually started primary root from
    the configured project path. Without a runner, path tokens are accepted
    only when their matching roots share a live common dev parent; unrelated
    roots are refused rather than merged into one kill.
    """
    by_parent = {pid: ppid for pid, ppid, _name, _cmd in table}
    names = {pid: (name or "") for pid, _ppid, name, _cmd in table}
    cmds = {pid: (cmd or "") for pid, _ppid, _name, cmd in table}
    protected = set(protected or ())
    toks = [t.lower() for t in detect.kill_tokens_for(work)]
    if not toks:
        return set()

    registry = store._load_registry()
    info = registry.get(work.get("id"), {})
    if not isinstance(info, dict):
        info = {}
    rejected_registry_pid = 0
    preferred_registry_pid = 0
    try:
        registered_pid = int(info.get("pid"))
    except (TypeError, ValueError):
        registered_pid = 0
    if registered_pid in cmds:
        command = cmds[registered_pid].lower()
        runner_ids = [x for x in detect._runner_identity(work, info) if x]
        runner_matches = bool(runner_ids) and any(
            detect._identity_token_matches(identity, command) for identity in runner_ids)
        try:
            recorded_parent = int(info.get("parent_pid"))
        except (TypeError, ValueError):
            recorded_parent = 0
        parent_matches = (not recorded_parent or
                          by_parent.get(registered_pid) == recorded_parent)
        host_name = ntpath.basename(names.get(registered_pid, "")).lower()
        if registered_pid not in protected \
                and not detect._is_never_seed_process(
                    names.get(registered_pid, ""), command) \
                and not names.get(registered_pid, "").lower().startswith("powershell") \
                and host_name in {"cmd.exe", "cmd"} \
                and parent_matches and runner_matches:
            preferred_registry_pid = registered_pid
        else:
            # A present but mismatching launch PID is a possible PID reuse.
            # Keep it out of fallback matching, but allow a fresh root with
            # the recorded runner identity to be found safely.
            rejected_registry_pid = registered_pid
    # The recorded process may have exited normally while its GUI child stays
    # alive (for example, a `start` step). In that case the strict token path
    # below may still identify the child; ambiguity is refused there.

    rejected_tree: set[int] = set()
    if rejected_registry_pid:
        rejected_tree.add(rejected_registry_pid)
        changed = True
        while changed:
            changed = False
            for pid, parent_pid in by_parent.items():
                if parent_pid in rejected_tree and pid not in rejected_tree:
                    rejected_tree.add(pid)
                    changed = True

    def _match_info(token: str) -> tuple[set[int], set[int]]:
        matches = {
            pid for pid, command in cmds.items()
            if command and detect._identity_token_matches(token, command)
            and pid not in protected
            and pid not in rejected_tree
            and not names.get(pid, "").lower().startswith("powershell")
            and not detect._is_never_seed_process(names.get(pid, ""), command)
        }
        if not matches:
            return set(), set()
        roots = set()
        for pid in matches:
            cur = pid
            seen = set()
            has_matching_parent = False
            while cur not in seen:
                seen.add(cur)
                cur = by_parent.get(cur, 0)
                if not cur:
                    break
                if cur in matches:
                    has_matching_parent = True
                    break
            if not has_matching_parent:
                roots.add(pid)
        return matches, roots

    def _configured_path_tokens() -> list[str]:
        paths = [
            str(token) for token in detect.titles_for(work)
            if "\\" in str(token) or ":" in str(token)
        ]
        if not paths:
            for var_name in ("APPDIR", "PROJECT", "VSCDATA"):
                raw = (work.get("vars") or {}).get(var_name)
                if raw and ("\\" in str(raw) or ":" in str(raw)):
                    paths.append(steps.expand_work_vars(str(raw), work))
                    break
        return paths

    def _manual_primary_roots(path_tokens: list[str],
                              excluded: set[str]) -> set[int]:
        found: set[int] = set()
        for path_token in path_tokens:
            if detect._windows_path_text(path_token) in excluded:
                continue
            _path_matches, path_roots = _match_info(path_token)
            found.update(
                pid for pid in path_roots
                if detect._primary_path_identity_matches(
                    path_token, cmds.get(pid, "")))
        return found

    runner_tokens = [t for t in detect._runner_identity(work, info) if t]
    if preferred_registry_pid:
        path_tokens = _configured_path_tokens()
        runner_set = {detect._windows_path_text(x) for x in runner_tokens}
        return {preferred_registry_pid} | _manual_primary_roots(
            path_tokens, runner_set)

    # A runner basename is stronger than a user-supplied match/path token.
    # Multiple exact generated runner roots are duplicate launches of this
    # same work (a common result of a previously blocked Stop), so they are
    # all safe seeds; only a primary path below the configured project may be
    # added as a manually started instance.
    for token in runner_tokens:
        matches, roots = _match_info(token)
        if matches:
            runner_roots = {
                pid for pid in roots
                if ntpath.basename(names.get(pid, "")).lower() in {"cmd", "cmd.exe"}
                and detect._identity_token_matches(token, cmds.get(pid, ""))
            }
            if runner_roots:
                # Also pick up an instance started manually from the same
                # configured project directory.  Only a primary file path
                # counts here; a foreign ``--env-file`` reference does not.
                runner_set = {detect._windows_path_text(x) for x in runner_tokens}
                return runner_roots | _manual_primary_roots(
                    _configured_path_tokens(), runner_set)
            return set()

    # The wrapper may already have exited while a child remains.  Accept
    # fallback tokens only when every usable token belongs to the same tree.
    candidates: list[int] = []
    for token in toks:
        matches, roots = _match_info(token)
        if "\\" in token or ":" in token:
            roots = {pid for pid in roots
                     if detect._primary_path_identity_matches(
                         token, cmds.get(pid, ""))}
        if roots:
            candidates.extend(roots)
    if not candidates:
        return set()

    def _ancestors(pid: int) -> list[int]:
        chain = []
        cur = pid
        seen = set()
        while cur and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            cur = by_parent.get(cur, 0)
        return chain

    # Several services from one dev workspace can be sibling branches under a
    # shared dev runner (frontend + backend is the normal example).  Accept
    # those roots when the common parent is present in this table and is not a
    # shared desktop host.  We still seed only the matching roots and walk
    # DOWN from them; the common parent itself is never added to the kill set.
    shared = set(_ancestors(candidates[0]))
    for root in candidates[1:]:
        shared.intersection_update(_ancestors(root))
    if not shared:
        return set()
    common_pid = next((pid for pid in _ancestors(candidates[0])
                       if pid in shared and pid in names), 0)
    if not common_pid or common_pid in protected or detect._is_never_seed_process(
            names.get(common_pid, ""), cmds.get(common_pid, "")):
        return set()
    # Prefer the deepest candidate when one token matched an ancestor and
    # another matched its child. This keeps fallback matching DOWN-only and
    # avoids turning a user's hosting shell into a kill seed.
    seeds = set(candidates)

    def _is_ancestor(ancestor: int, child: int) -> bool:
        cur = child
        seen = set()
        while cur and cur not in seen:
            if cur == ancestor:
                return True
            seen.add(cur)
            cur = by_parent.get(cur, 0)
        return False

    return {root for root in seeds
            if not any(root != other and _is_ancestor(root, other)
                       for other in seeds)}


def kill_work(work: dict, dry_run: bool = False) -> list[int] | None:
    """Kill the work's process tree: matched processes + their DESCENDANTS.

    SAFETY (2026-09-05 incident — the old ancestor walk killed the agent's
    own session shell plus the user's Discord/VSCode/work windows): this
    function walks DOWN ONLY and NEVER walks up to ancestors. The launcher
    (this python), its whole parent chain, and the scanner powershell form
    a PROTECTED set that can never enter the kill list — even if their
    CommandLine happens to contain a match token (e.g. our own shell
    echoing the token in its command line).

    Close happens in THREE passes so no dead terminal is left behind
    ("kill = exit the window, not just stop the task"):
    1. graceful `taskkill /PID` (NO /F) on the whole kill set -- this
       sends the console close request, so the window-owning cmd exits
       through its normal path and its window closes (GUI apps get
       WM_CLOSE and shut down cleanly instead of being ripped away);
    2. Alt+F4 the work's windows via close_work_windows (WM_CLOSE to
       every HWND in the work's guarded owner set). Needed because a
       leftover `cmd /k` host can be an ANCESTOR of every seed (old
       nested-start windows) -- process-only DOWN kill can never reach
       it, but closing its WINDOW terminates it via the console;
    3. after a short bounded wait, per-PID `taskkill /F` on the same set
       as the sweep -- PIDs already gone just report "not found"
       (captured + ignored); anything that ignored both closes dies here.
    The kill set itself is unchanged: the matched seed (the visible
    `cmd /K bat.bat` wrapper carries the bat basename as a token via
    kill_tokens_for, so it is a seed directly -- no upward walk needed)
    plus every descendant (npm/node/npx children). Per-PID kills (no /T)
    avoid cascading into shared conhosts of unrelated windows.
    powershell* processes are never killed (they host user sessions).

    With dry_run=True, returns the sorted kill PID list WITHOUT killing —
    show it to the user BEFORE any real kill. A successful real kill returns
    None. If identity revalidation or the force sweep leaves a target alive,
    the surviving PID list is returned and the registry entry is retained so
    the caller can report the blocked stop and retry safely.
    """
    # Deck-launched job: the kernel member list is the whole kill set (no
    # tokens, no BFS, no revalidation). Never-seed names are excluded.
    if jobs.eligible(work):
        wid = work.get("id", "")
        mine = {os.getpid()}
        targets = [p for p in jobs.members(wid, detect._NEVER_SEED_GUI) if p not in mine]
        if targets:
            if dry_run:
                return sorted(targets)
            root = (store._load_registry().get(wid) or {}).get("pid")
            left = jobs.stop(wid, group=root, never=detect._NEVER_SEED_GUI, protected=mine)
            if left:
                return sorted(left)
            store.unregister(work)
            return None
    # Drop dangerously short tokens (1-2 chars match the whole machine --
    # e.g. a 1-letter work id). Killing is destructive: a tiny token can
    # never be what anyone wants. Detection (is_running) is unaffected.
    toks = [t for t in detect.kill_tokens_for(work) if len(t) >= 3]
    if not toks:
        return []
    my_pid = os.getpid()  # the LaunchDeck process -- never touch
    # Seeds + DOWN expansion computed in pure Python over ONE shared table
    # (no per-kill PowerShell scan; Trap: NEVER use $pid as a loop variable
    # applied to the old inline script -- gone with it).
    table = detect.scan_table()
    if not table:
        return []
    by_parent: dict[int, int] = {}
    names: dict[int, str] = {}
    cmds: dict[int, str] = {}
    children: dict[int, list[int]] = {}
    for pid, ppid, name, cmd in table:
        by_parent[pid] = ppid
        names[pid] = name or ""
        cmds[pid] = cmd or ""
        children.setdefault(ppid, []).append(pid)

    def _is_ps(pid: int) -> bool:
        return names.get(pid, "").lower().startswith("powershell")

    # Protected = launcher + every ancestor of the launcher up to the root.
    # (The old inline script also excluded its own scanner PID -- moot now:
    # it was powershell* and dead by match time.) Nothing in here can ever
    # be killed.
    prot = {my_pid}
    cur, guard = my_pid, 0
    while guard < 64:
        guard += 1
        anc = by_parent.get(cur, 0)
        if not anc or anc in prot:
            break
        prot.add(anc)
        cur = anc
    # Seeds are either a validated registered launch root or an unambiguous
    # identity-token match.  Neither path walks upward to find kill roots.
    seed = _seed_pids_for_work(work, table, prot)
    # Expand DOWN ONLY (BFS over children). Protected PIDs are never added
    # even if parented under a seed; powershell* is traversed through but
    # never added (it hosts user sessions).
    kill: set[int] = set()
    seen: set[int] = set()
    root_for: dict[int, int] = {}
    queue = list(seed)
    for s in seed:
        seen.add(s)
        kill.add(s)
        root_for[s] = s
    while queue:
        c = queue.pop()
        for ch in children.get(c, []):
            if ch in prot or ch in seen:
                continue
            seen.add(ch)
            if not _is_ps(ch):
                kill.add(ch)
            root_for[ch] = root_for.get(c, c)
            queue.append(ch)
    pids = sorted(kill)
    if not pids:
        return []
    if dry_run:
        return pids
    def _tk(args: list[str], timeout: int) -> None:
        try:
            subprocess.run(
                ["taskkill.exe"] + args,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                creationflags=common._NO_WINDOW,
            )
        except Exception:
            pass
    # Pass 1 (graceful): ask every PID in the downward set to exit through
    # its normal close path -- the window-owning cmd exits and its terminal
    # window closes instead of lingering as a dead prompt. No /F, no /T.
    for kpid in pids:
        _tk(["/PID", str(kpid)], 10)
    # Pass 2 (Alt+F4): WM_CLOSE the work's terminal windows. Killing the
    # task alone can leave the bare window behind (a leftover `cmd /k`
    # host can be an ANCESTOR of every seed, unreachable by DOWN kill) --
    # closing the WINDOW is what removes it. Same guarded owner set as
    # the `h` key (protected chain + badgui never included).
    try:
        windows.close_work_windows(work, target_pids=set(pids), target_table=table)
    except Exception:
        pass
    # Bounded wait so the closes can land (windows die fast, and
    # stragglers are swept in pass 3 -- this sleep never gates on state).
    time.sleep(2.5)
    # Refresh the table before the destructive pass.  A PID may have exited
    # and been reused during the graceful/window-close wait; only retain a
    # PID whose name, parent, and command line still match the original row.
    revalidated = False
    try:
        fresh = detect.scan_table()
        if not fresh:
            raise RuntimeError("process scan unavailable during revalidation")
        current = {pid: (ppid, name or "", cmd or "")
                   for pid, ppid, name, cmd in fresh}
        original = {pid: (by_parent.get(pid, 0), names.get(pid, ""),
                          cmds.get(pid, "")) for pid in pids}
        original_pids = set(pids)

        def _same_identity(pid: int) -> bool:
            """Check the stable process identity, ignoring a changed PPID."""
            row = current.get(pid)
            old = original.get(pid)
            return bool(row and old and row[1:] == old[1:])

        def _root_is_current(root: int) -> bool:
            # A launch root is expected to keep its parent.  A changed root
            # is treated as PID reuse, never as a force-kill candidate.
            return root in current and current[root] == original.get(root)

        def _safe_descendant(pid: int, root: int) -> bool:
            """Validate an unchanged original descendant without PPID pinning.

            Windows reparents a child when a wrapper exits.  Walking the
            *original* parent chain keeps that orphan target safe while still
            rejecting a changed intermediate PID.  A present root with any
            changed identity blocks the whole branch.
            """
            if pid == root or not _same_identity(pid):
                return False
            cur = pid
            chain_seen: set[int] = set()
            while cur != root:
                if cur in chain_seen:
                    return False
                chain_seen.add(cur)
                parent_pid = by_parent.get(cur, 0)
                if parent_pid not in original_pids:
                    return False
                if parent_pid in current and not _same_identity(parent_pid):
                    return False
                cur = parent_pid
            return not (root in current and not _root_is_current(root))

        keep: set[int] = set()
        for root in seed:
            if _root_is_current(root):
                keep.add(root)
            elif root in current:
                # The root still exists but its identity changed: it may be
                # an unrelated process with a recycled PID.
                continue
            # If the root is gone, unchanged descendants may have been
            # reparented and remain safe to sweep.
            for pid in pids:
                if root_for.get(pid) == root and _safe_descendant(pid, root):
                    keep.add(pid)
        pids = sorted(keep)
        revalidated = True
    except Exception:
        # If identity cannot be revalidated, the graceful pass has already
        # been attempted, but a force sweep is unsafe. Keep the registry so
        # the UI reports that the stop needs another attempt.
        revalidated = False

    if not revalidated:
        return sorted(set(pids))

    # Pass 3 (sweep): kill stragglers -- ONE helper call when available
    # (in-process TerminateProcess; already-gone PIDs report "dead" and are
    # ignored), else the per-PID taskkill /F loop. No /T ever: tree-kill
    # cascades into shared conhost processes of unrelated windows.
    swept = False
    if detect._launchdeck_helper_available():
        try:
            r = subprocess.run(
                [str(detect._LAUNCHDECK_HELPER), "kill"] + [str(k) for k in pids],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                creationflags=common._NO_WINDOW,
            )
            swept = r.returncode == 0
        except Exception:
            swept = False
    if not swept:
        for kpid in pids:
            _tk(["/F", "/PID", str(kpid)], 10)

    # Do not claim success merely because taskkill/helper returned. Both can
    # report success for a stale PID, and a permissions or protected-process
    # failure is otherwise silent.  A second scan is still read-only; if it
    # fails, retain the registry and report the targets as unresolved.
    if pids:
        try:
            after_sweep = detect.scan_table()
        except Exception:
            return sorted(set(pids))
        if not after_sweep:
            return sorted(set(pids))
        live_after = {pid for pid, _ppid, _name, _cmd in after_sweep}
        remaining = sorted(pid for pid in pids if pid in live_after)
        if remaining:
            return remaining
    store.unregister(work)
    return None
