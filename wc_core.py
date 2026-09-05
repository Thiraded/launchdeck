"""wc_core.py — pure logic for the work combo (wc) and kill combo (kc) TUIs.

Key concepts
-----------
* Work Combo (wc): SELECT / RUN. A group has NO state of its own -- its
  selection is the logical OR of its children:
      group selected  <=>  (any child selected)
  So: Space on a group selects all children; Space again clears them;
  clearing any child clears the group too.
* Running state `[-]` is detected live from the process CommandLine (token =
  .bat basename or explicit `match`). It is shown separately from selection.
* Kill Combo (kc): lists ONLY works that are currently running, lets you kill
  them. It relies on a small registry (registry.json) that wc writes when it
  starts something, so kc can find + terminate the right processes quickly.
"""
import json
import os
import subprocess
import time
from pathlib import Path

# Background subprocesses (powershell scans, taskkill) must not flash a
# console window when wc runs under pythonw (wctray has no console to
# inherit, so Windows pops a visible terminal on EVERY scan otherwise).
# Works launched via run_work() are EXCLUDED -- those must stay VISIBLE.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

DESKTOP = Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "Desktop"
if not DESKTOP.exists():
    DESKTOP = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
MANIFEST = DESKTOP / "works.json"
REGISTRY = DESKTOP / "registry.json"

# The manifest most recently used to build the model. member_nodes() reads
# works from HERE (not from disk) so group membership is consistent with the
# tree wc/kc actually render. Set by build_model().
_CURRENT_MANIFEST = None

# State tokens (selection column)
OFF = " "   # [ ] not selected
ON = "x"    # [x] selected to run
RUN = "-"   # [-] running (verified alive)
LEFT_ALONE = "_"  # [.] left alone (don't touch on Enter/kill)


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------
def load_manifest(path: Path = MANIFEST) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {"version": 1, "groups": [], "works": []}
    data.setdefault("groups", [])
    data.setdefault("works", [])
    return data


def work_by_id(manifest: dict, wid: str) -> dict | None:
    for w in manifest["works"]:
        if w.get("id") == wid:
            return w
    return None


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------
def titles_for(work: dict) -> list[str]:
    """Substrings to match against a running process CommandLine. Prefer an
    explicit `match`, else the .bat basename (our runners spawn a child cmd
    whose CommandLine contains the .bat name). Console `title` is NOT used."""
    m = work.get("match")
    if m:
        return [m] if isinstance(m, str) else [x for x in m if x]
    bat = work.get("bat") or ""
    if bat:
        return [os.path.basename(bat)]
    return []


def kill_tokens_for(work: dict) -> list[str]:
    """Match tokens to kill a work's process tree. Beyond `match` and the bat
    basename (titles_for), we also include a low-cardinality token derived
    from the work id so the outer `cmd /K "bat.bat"` wrapper is reachable
    even when it has no match token of its own (e.g. GPT MCP's wrapper
    CommandLine is just `cmd /K "GPT MCP.bat`)."""
    toks = list(titles_for(work))
    proj = work.get("proj")
    if proj:
        toks.append(proj)
    # Always add a token that the outer wrapper is GUARANTEED to contain
    # (the bat basename, or the work id if no bat). This makes the
    # outermost `cmd /K "bat.bat"` (the one whose window the user sees)
    # a seed so the tree walk includes it.
    bat = work.get("bat") or ""
    if bat:
        bn = os.path.basename(bat)
        if bn and bn not in toks:
            toks.append(bn)
    wid = work.get("id") or ""
    # Auto-adding the bare work id is a guess for reaching the outer
    # `cmd /K "bat.bat"` wrapper -- but a short id (e.g. "a") matches the
    # whole machine as a kill token (2026-09-05 incident). Only add it
    # when it is specific enough to be safe.
    if wid and wid not in toks and len(wid) >= 4:
        toks.append(wid)
    return toks


def scan_commandlines() -> list[str]:
    """Return the CommandLine of every live non-powershell, non-self process in
    ONE scan. Call this once and reuse the list for many is_running checks
    instead of spawning a powershell per work (that's what made kc lag)."""
    ps = (
        "$me = $PID;"
        "foreach ($p in (Get-CimInstance Win32_Process)) {"
        "  if ($p.ProcessId -eq $me) { continue }"
        "  if ($null -eq $p.CommandLine) { continue }"
        "  if ($p.Name -like 'powershell*') { continue }"
        "  Write-Output $p.CommandLine"
        "}"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=15,
            creationflags=_NO_WINDOW,
        )
        return [ln for ln in (r.stdout or "").splitlines() if ln]
    except Exception:
        return []


def is_running(work: dict, commandlines: list[str] | None = None) -> bool:
    """True if any live (non-powershell, non-self) process CommandLine contains
    a match token. If `detect` is False we never track running state. Pass a
    pre-scanned `commandlines` list (from scan_commandlines) to avoid spawning
    a powershell per call."""
    if work.get("detect") is False:
        return False
    tokens = titles_for(work)
    if not tokens:
        return False
    if commandlines is None:
        commandlines = scan_commandlines()
    toks_low = [t.lower() for t in tokens]
    for line in commandlines:
        low = line.lower()
        for t in toks_low:
            if t and t in low:
                return True
    return False


# --------------------------------------------------------------------------
# run / kill
# --------------------------------------------------------------------------
def run_work(work: dict) -> None:
    """Launch the work's .bat in a VISIBLE terminal window (no hidden
    self-relaunch). Each work opens its own window. Registers it too."""
    bat = work.get("bat")
    if not bat or not os.path.exists(bat):
        return
    # Windows `start` treats the FIRST quoted token as the window title.
    # A single `""` is the title placeholder; the NEXT token is the command.
    # Passing `"" "" "bat"` made the 2nd empty string the command, which
    # `start` resolves to opening the working FOLDER in Explorer (the
    # "Enter opens a folder instead of running" bug). Use exactly one `""`.
    subprocess.Popen(["cmd.exe", "/c", "start", "", bat], shell=False)
    register(work)


def kill_work(work: dict, dry_run: bool = False) -> list[int] | None:
    """Kill the work's process tree: matched processes + their DESCENDANTS.

    SAFETY (2026-09-05 incident — the old ancestor walk killed the agent's
    own session shell plus the user's Discord/VSCode/work windows): this
    function walks DOWN ONLY and NEVER walks up to ancestors. The launcher
    (this python), its whole parent chain, and the scanner powershell form
    a PROTECTED set that can never enter the kill list — even if their
    CommandLine happens to contain a match token (e.g. our own shell
    echoing the token in its command line).

    The reliable way to close a console window (cmd /k, npx, etc.) on
    Windows is `taskkill /F` on the kill set: the matched seed itself
    (the visible `cmd /K bat.bat` wrapper carries the bat basename as a
    token via kill_tokens_for, so it is a seed directly — no upward walk
    needed) plus every descendant (npm/node/npx children). Per-PID /F
    (no /T) avoids cascading into shared conhosts of unrelated windows.
    powershell* processes are never killed (they host user sessions).

    With dry_run=True, returns the sorted kill PID list WITHOUT killing —
    show it to the user BEFORE any real kill. Otherwise kills each PID,
    unregisters the work, and returns None.
    """
    # Drop dangerously short tokens (1-2 chars match the whole machine --
    # e.g. a 1-letter work id). Killing is destructive: a tiny token can
    # never be what anyone wants. Detection (is_running) is unaffected.
    toks = [t for t in kill_tokens_for(work) if len(t) >= 3]
    if not toks:
        return [] if dry_run else None
    my_pid = os.getpid()  # the python (wc) process -- never touch
    toks_ps = ",".join("'" + t.replace("'", "''") + "'" for t in toks)
    # Single PowerShell call: seeds (token match, minus protected) then
    # BFS DOWN through the children map. No ancestor walk, ever.
    # (Trap: NEVER use $pid as a loop variable -- $PID is read-only.)
    ps = (
        "$ErrorActionPreference = 'SilentlyContinue'; "
        "$me = $PID; "
        "$wcPID = " + str(my_pid) + "; "
        "$toks = @(" + toks_ps + "); "
        "$byId = @{}; $children = @{}; "
        "foreach ($p in (Get-CimInstance Win32_Process)) "
        "{ $byId[$p.ProcessId] = $p; $parid = $p.ParentProcessId; "
        "if (-not $children.ContainsKey($parid)) { $children[$parid] = New-Object System.Collections.Generic.List[int] }; "
        "$children[$parid].Add($p.ProcessId) }; "
        # Protected = scanner + launcher + every ancestor of the launcher
        # up to the root. Nothing in here can ever be killed.
        "$prot = New-Object System.Collections.Generic.HashSet[int]; "
        "[void]$prot.Add($me); [void]$prot.Add($wcPID); "
        "$cur = $wcPID; $guard = 0; "
        "while ($cur -gt 0 -and $guard -lt 64) "
        "{ $guard++; $anc = $byId[$cur]; if ($null -eq $anc) { break }; "
        "$nx = $anc.ParentProcessId; if ($nx -le 0 -or $prot.Contains($nx)) { break }; "
        "[void]$prot.Add($nx); $cur = $nx }; "
        # Seeds: CommandLine token match, skipping powershell* + protected.
        "$seed = New-Object System.Collections.Generic.HashSet[int]; "
        "foreach ($p in $byId.Values) { "
        "  if ($null -eq $p.CommandLine) { continue } "
        "  if ($p.Name -like 'powershell*') { continue } "
        # Interactive GUI apps are NEVER valid kill seeds: a match token can
        # appear in a browser tab URL / chat window (2026-09-05: token
        # 'omniroute' matched the user's Brave PID 4524 -- Stop would have
        # taken down the whole browser). Keep in sync with find_work_hwnds.
        "  if (@('brave.exe','chrome.exe','msedge.exe','firefox.exe','opera.exe','vivaldi.exe','arc.exe','explorer.exe','discord.exe','slack.exe','teams.exe') -contains $p.Name) { continue } "
        "  if ($prot.Contains($p.ProcessId)) { continue } "
        "  foreach ($t in $toks) { "
        "    if ($p.CommandLine -like ('*' + $t + '*')) { "
        "      [void]$seed.Add($p.ProcessId); break "
        "    } "
        "  } "
        "} "
        # Expand DOWN ONLY (BFS over children). Protected PIDs are never
        # added even if parented under a seed; powershell* is traversed
        # through but never added (it hosts user sessions).
        "$kill = New-Object System.Collections.Generic.HashSet[int]; "
        "$seen = New-Object System.Collections.Generic.HashSet[int]; "
        "$queue = New-Object System.Collections.Generic.Queue[int]; "
        "foreach ($s in $seed) { [void]$seen.Add($s); [void]$kill.Add($s); $queue.Enqueue($s) }; "
        "while ($queue.Count -gt 0) { "
        "  $c = $queue.Dequeue(); "
        "  if ($children.ContainsKey($c)) { "
        "    foreach ($ch in $children[$c]) { "
        "      if ($prot.Contains($ch)) { continue }; "
        "      if (-not $seen.Add($ch)) { continue }; "
        "      $chn = $byId[$ch]; "
        "      if ($null -eq $chn -or $chn.Name -notlike 'powershell*') { [void]$kill.Add($ch) }; "
        "      $queue.Enqueue($ch) "
        "    } "
        "  } "
        "} "
        "foreach ($k in $kill) { Write-Output $k }"
    )
    pids: list[int] = []
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=15,
            creationflags=_NO_WINDOW,
        )
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
    except Exception:
        pass
    pids = sorted(set(pids))
    if dry_run:
        return pids
    try:
        for kpid in pids:
            # `taskkill /F` (no /T) on EACH pid in the downward set. We
            # deliberately avoid /T because tree-kill cascades into shared
            # conhost processes of unrelated windows.
            subprocess.run(
                ["taskkill.exe", "/F", "/PID", str(kpid)],
                capture_output=True, text=True, timeout=10,
                creationflags=_NO_WINDOW,
            )
    except Exception:
        pass
    _HIDDEN_HWNDS.pop(work.get("id", ""), None)  # dead windows need no tracking
    unregister(work)
    return None


# --------------------------------------------------------------------------
# Find the visible HWNDs owned by a work's process tree. Used by `h` to
# hide/show that work's terminal window without killing the process.
# --------------------------------------------------------------------------
def find_work_hwnds(work: dict) -> list[int]:
    """Return the HWNDs of every top-level window whose owning PID belongs
    to the work's process tree (i.e. processes whose CommandLine contains
    one of the work's match tokens). Returned HWNDs are safe to pass to
    ShowWindow / PostMessage."""
    toks = kill_tokens_for(work)
    if not toks:
        return []
    # 1) collect candidate PIDs in pure Python
    cls = scan_commandlines()
    pids: set[int] = set()
    # also need the PID for each CommandLine
    ps = (
        "$me = $PID; "
        "$toks = @(" + ", ".join("'" + t.replace("'", "''") + "'" for t in toks) + "); "
        # Same NEVER-seed GUI list as kill_work (a token can hide in a tab
        # URL -- we must never hide the user's browser/chat/shell).
        "$badgui = @('brave.exe','chrome.exe','msedge.exe','firefox.exe','opera.exe','vivaldi.exe','arc.exe','explorer.exe','discord.exe','slack.exe','teams.exe'); "
        "foreach ($p in (Get-CimInstance Win32_Process)) { "
        "  if ($null -eq $p.CommandLine) { continue } "
        "  if ($p.Name -like 'powershell*') { continue } "
        "  if ($badgui -contains $p.Name) { continue } "
        "  if ($p.ProcessId -eq $me) { continue } "
        "  foreach ($t in $toks) { "
        "    if ($p.CommandLine -like ('*' + $t + '*')) { "
        "      Write-Output $p.ProcessId; break "
        "    } "
        "  } "
        "}"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=15,
            creationflags=_NO_WINDOW,
        )
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))
    except Exception:
        return []
    if not pids:
        return []
    # 2) walk to ancestors so we also hide the cmd.exe host
    try:
        anc_ps = (
            "$me = $PID; "
            "$seeds = @(" + ",".join(str(p) for p in pids) + "); "
            "$byId = @{}; foreach ($p in (Get-CimInstance Win32_Process)) { $byId[$p.ProcessId] = $p }; "
            "$all = New-Object System.Collections.Generic.HashSet[int]; "
            "foreach ($s in $seeds) { [void]$all.Add($s) }; "
            "foreach ($s in $seeds) { "
            "  $cur = $s; "
            "  while ($true) { "
            "    $p = $byId[$cur]; if ($null -eq $p) { break }; "
            "    $ppid = $p.ParentProcessId; "
            "    if ($ppid -eq 0 -or $ppid -eq $me) { break }; "
            "    $par = $byId[$ppid]; if ($null -eq $par) { break }; "
            "    if ($par.Name -like 'powershell*') { break }; "
            "    if ($all.Add($ppid)) { $cur = $ppid } else { break } "
            "  } "
            "} "
            "foreach ($x in $all) { Write-Output $x }"
        )
        ar = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", anc_ps],
            capture_output=True, text=True, timeout=15,
            creationflags=_NO_WINDOW,
        )
        for line in (ar.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                pids.add(int(line))
    except Exception:
        pass
    # 3) find top-level windows owned by any of these PIDs (Win32 EnumWindows)
    return _hwnds_for_pids(pids)


def _hwnds_for_pids(pids: set[int]) -> list[int]:
    """Enumerate top-level windows owned by the work's process tree.

    A console window is owned by conhost.exe, typically a CHILD of the
    work's cmd -- while matchable seeds (node with an absolute script
    path) sit BELOW that cmd. So raw-PID matching and upward-only walks
    both miss. Owner set = seeds + bounded ancestors of seeds (up to 8,
    stopping at our own protected chain) + one level of children below
    each (catches conhost + wrapper cmds). powershell* is traversed but
    never added (it hosts user sessions). Kill stays DOWNWARD-ONLY;
    this up+down-1 expansion applies to HIDE (reversible) only.
    Pure ctypes + one PowerShell call, no deps."""
    import ctypes
    user32 = ctypes.windll.user32
    # PID -> (parent, name) maps (one scan).
    parent: dict[int, int] = {}
    names: dict[int, str] = {}
    children: dict[int, list[int]] = {}
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "foreach ($p in (Get-CimInstance Win32_Process)) { "
             "Write-Output ($p.ProcessId.ToString() + '|' + $p.ParentProcessId.ToString() + '|' + $p.Name) }"],
            capture_output=True, text=True, timeout=15,
            creationflags=_NO_WINDOW,
        )
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split("|")
            if len(parts) != 3 or not parts[0].strip().isdigit():
                continue
            pid = int(parts[0].strip())
            try:
                ppid = int(parts[1].strip())
            except Exception:
                ppid = 0
            parent[pid] = ppid
            names[pid] = parts[2].strip()
            children.setdefault(ppid, []).append(pid)
    except Exception:
        pass

    def is_ps(pid: int) -> bool:
        return (names.get(pid) or "").lower().startswith("powershell")

    # Protected = our own chain (never hide our/the agent's windows).
    me = os.getpid()
    prot: set[int] = {me}
    cur, guard = me, 0
    while guard < 64:
        guard += 1
        par = parent.get(cur, 0)
        if not par or par in prot:
            break
        prot.add(par)
        cur = par

    owners: set[int] = set()
    for s in pids:
        if s in prot or is_ps(s):
            continue
        owners.add(s)
    # Up from each seed (bounded, stop at protected/missing/root).
    for s in list(owners):
        cur, depth = s, 0
        while depth < 8:
            par = parent.get(cur, 0)
            if not par or par in prot:
                break
            if not is_ps(par):
                owners.add(par)
            cur, depth = par, depth + 1
    # One level down (conhost + wrapper cmds). Never protected/powershell.
    for o in list(owners):
        for ch in children.get(o, []):
            if ch in prot or is_ps(ch):
                continue
            owners.add(ch)
    if not owners:
        return []

    found: list[int] = []
    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lparam):
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) in owners:
            try:
                if user32.IsWindowVisible(hwnd):
                    found.append(int(hwnd))
            except Exception:
                pass
        return 1
    try:
        user32.EnumWindows(cb, 0)
    except Exception:
        pass
    # keep the callback alive until EnumWindows returns
    _hwnds_for_pids._cb = cb  # type: ignore[attr-defined]
    return found


# --------------------------------------------------------------------------
# True hide/show (tray-grade): SW_HIDE removes the window from the taskbar
# AND Alt+Tab while the process keeps running. Restore with SW_SHOW.
# Hidden HWNDs are tracked per work id because a hidden window no longer
# enumerates as visible and can't be re-found by scan.
# --------------------------------------------------------------------------
_HIDDEN_HWNDS: dict[str, list[int]] = {}


def set_hwnds_visible(hwnds: list[int], show: bool) -> int:
    """ShowWindowAsync(SW_SHOW/SW_HIDE) over `hwnds`. Returns changed count."""
    if not hwnds:
        return 0
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.ShowWindowAsync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.ShowWindowAsync.restype = ctypes.c_int
    except Exception:
        return 0
    SW_HIDE, SW_SHOW = 0, 5
    changed = 0
    for h in hwnds:
        try:
            if user32.ShowWindowAsync(h, SW_SHOW if show else SW_HIDE):
                changed += 1
        except Exception:
            pass
    return changed


def hide_work_windows(work: dict, retries: int = 3) -> tuple[int, str]:
    """True-hide a running work's windows (gone from taskbar + Alt+Tab).

    Retries the scan: right after Start the wrapper window exists before
    any matchable child (node) has spawned, so the first scan can miss
    a window that is staring at the user. Only the miss path waits.
    """
    wid = work.get("id", "")
    hwnds = find_work_hwnds(work)
    tries = 0
    while not hwnds and tries < retries and is_running(work):
        time.sleep(2.5)
        tries += 1
        hwnds = find_work_hwnds(work)
    if not hwnds:
        if _HIDDEN_HWNDS.get(wid):
            return 0, "already hidden"
        if is_running(work):
            return 0, "running but has no window (headless)"
        return 0, "not running -- nothing to hide"
    n = set_hwnds_visible(hwnds, False)
    if n:
        _HIDDEN_HWNDS[wid] = hwnds
        return n, f"hid {n} window(s) — task still running"
    return 0, "could not hide window"


def show_work_windows(work: dict) -> tuple[int, str]:
    """Restore windows hidden by hide_work_windows."""
    wid = work.get("id", "")
    hwnds = _HIDDEN_HWNDS.get(wid) or []
    if not hwnds:
        return 0, "nothing hidden for this work"
    n = set_hwnds_visible(hwnds, True)
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        for h in hwnds:
            try:
                user32.SetForegroundWindow(h)
                break
            except Exception:
                pass
    except Exception:
        pass
    _HIDDEN_HWNDS.pop(wid, None)
    return n, f"restored {n} window(s)"


def is_work_hidden(work: dict) -> bool:
    return bool(_HIDDEN_HWNDS.get(work.get("id", "")))


def hidden_work_ids() -> set[str]:
    """Ids of works currently marked hidden (have tracked HWNDs)."""
    return {wid for wid, h in _HIDDEN_HWNDS.items() if h}


def sweep_hidden_windows(manifest: dict) -> dict[str, int]:
    """Re-hide newly visible windows of hidden-marked works.

    Dev servers fork fresh consoles AFTER hiding (npm/vite children);
    the 3s monitor calls this so strays are re-hidden automatically.
    Returns {work_id: newly_hidden_count}. No-op when nothing hidden.
    """
    reswept: dict[str, int] = {}
    if not _HIDDEN_HWNDS:
        return reswept
    by_id = {w.get("id"): w for w in manifest.get("works", [])}
    for wid in list(_HIDDEN_HWNDS):
        w = by_id.get(wid)
        if w is None:
            continue
        try:
            hwnds = find_work_hwnds(w)  # visible ones only
        except Exception:
            continue
        if not hwnds:
            continue
        n = set_hwnds_visible(hwnds, False)
        if n:
            merged = list(dict.fromkeys(_HIDDEN_HWNDS.get(wid, []) + hwnds))
            _HIDDEN_HWNDS[wid] = merged
            reswept[wid] = n
    return reswept


# --------------------------------------------------------------------------
# registry  (so kc can list + kill running works quickly)
# --------------------------------------------------------------------------
def _load_registry() -> dict:
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_registry(data: dict) -> None:
    try:
        REGISTRY.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def register(work: dict) -> None:
    """Record that `work` was launched (with a timestamp)."""
    data = _load_registry()
    data[work["id"]] = {
        "label": work.get("label", work["id"]),
        "bat": work.get("bat", ""),
        "launched": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_registry(data)


def unregister(work: dict) -> None:
    data = _load_registry()
    data.pop(work["id"], None)
    _save_registry(data)


def registry_running() -> list[dict]:
    """Return registry entries whose work is still alive. This is the list kc
    uses to display and kill currently-running works. Scans processes once."""
    data = _load_registry()
    out = []
    manifest = load_manifest()
    commandlines = scan_commandlines()
    for wid, info in data.items():
        w = work_by_id(manifest, wid)
        if w and is_running(w, commandlines):
            out.append({"id": wid, **info})
    return out


def live_running(manifest: dict | None = None, commandlines: list[str] | None = None) -> list[dict]:
    """Return all works currently detected as running LIVE (not just what wc
    registered). Used by kc to list + kill works you started by any means.
    Pass a pre-scanned `commandlines` (from scan_commandlines) to do the whole
    scan in a single powershell call instead of one per work."""
    if manifest is None:
        manifest = load_manifest()
    if commandlines is None:
        commandlines = scan_commandlines()
    out = []
    for w in manifest.get("works", []):
        if w.get("detect") is False:
            continue
        if is_running(w, commandlines):
            out.append({"id": w["id"], "label": w.get("label", w["id"]),
                        "bat": w.get("bat", "")})
    return out


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
class Node:
    def __init__(self, key, label, kind, work=None, group_members=None):
        self.key = key
        self.label = label
        self.kind = kind          # 'group' | 'work'
        self.work = work
        self.group_members = group_members or []

    def is_running(self):
        return is_running(self.work) if self.work else False


def build_model(manifest: dict) -> list[Node]:
    global _CURRENT_MANIFEST
    _CURRENT_MANIFEST = manifest
    nodes = []
    members_of_groups = set()
    for g in manifest.get("groups", []):
        members_of_groups.update(g.get("members", []))
    for g in manifest.get("groups", []):
        nodes.append(Node(g["id"], g["label"], "group",
                          group_members=list(g.get("members", []))))
    for w in manifest.get("works", []):
        if w.get("id") in members_of_groups:
            continue
        nodes.append(Node(w["id"], w["label"], "work", work=w))
    return nodes


def member_nodes(model: list[Node], group: Node) -> list[Node]:
    by_id = {n.key: n for n in model}
    out = []
    manifest = _CURRENT_MANIFEST if _CURRENT_MANIFEST is not None else load_manifest()
    work_by_id = {w["id"]: w for w in manifest.get("works", [])}
    for mid in group.group_members:
        if mid in by_id:
            out.append(by_id[mid])
        elif mid in work_by_id:
            out.append(Node(mid, work_by_id[mid].get("label", mid),
                            "work", work=work_by_id[mid]))
    return out


# --------------------------------------------------------------------------
# state machine  (selection only; running is detected live)
# --------------------------------------------------------------------------
def next_on_space(state: str) -> str:
    """Space toggles selection: OFF<->ON. A running work (RUN) is treated as
    'not yet selected' for kill purposes, so Space on a RUN node selects it
    (ON) -- i.e. 'mark this running work to be killed'. LEFT_ALONE is left
    untouched by Space."""
    if state == ON:
        return OFF
    if state == OFF or state == RUN:
        return ON
    return state


def group_selected(member_states: dict, members: list[Node]) -> bool:
    """A group is selected iff ANY child is selected (pure OR)."""
    return any(member_states.get(m.key) == ON for m in members)


def set_group_selection(states: dict, members: list[Node], value: str) -> None:
    for m in members:
        if value == ON:
            if states.get(m.key) != RUN:
                states[m.key] = ON
        else:  # clear
            if states.get(m.key) == ON:
                states[m.key] = OFF


def enter_action(state: str, node: Node, model: list[Node], states: dict | None = None):
    """Return list of (action, work) to run/kill. Group acts on its members."""
    if states is None:
        states = {}
    if node.kind == "group":
        members = member_nodes(model, node)
        if state == ON:
            acts = [("run", m.work) for m in members if not m.is_running()]
            return acts
        if state == RUN:
            acts = [("kill", m.work) for m in members
                    if m.is_running() and states.get(m.key) != LEFT_ALONE]
            return acts
        return []
    # work node
    if state == ON and not node.is_running():
        return [("run", node.work)]
    if state == RUN:
        return [("kill", node.work)]
    return []


def recompute_states(model: list[Node], states: dict) -> None:
    """Recompute RUN (detected) + group selection (OR of children).
    Selection of a child is preserved; groups are always derived."""
    # 1) mark running children (but never override an explicit ON selection --
    #    if the user selected a running work to kill, keep it ON so Space sticks)
    for n in model:
        if n.kind != "group":
            continue
        members = member_nodes(model, n)
        for m in members:
            if m.is_running() and states.get(m.key) == OFF:
                states[m.key] = RUN
            elif states.get(m.key) == RUN and not m.is_running():
                states[m.key] = OFF
    # 2) derive group selection from children (pure OR)
    for n in model:
        if n.kind == "group":
            members = member_nodes(model, n)
            if group_selected(states, members):
                states[n.key] = ON
            else:
                states[n.key] = OFF


# -------------------------------------------------------------------------
# launch + progress  (used by wc's "run then monitor" flow)
# -------------------------------------------------------------------------
# A "work" is the BACKGROUND process its .bat spawns — NOT the launcher window.
# E.g. OmniRoute CLI's .bat does `Start-Process ... 'title bg-omniroute-cli &&
# omniroute'` (hidden); Hamster does `npm run dev` (node); Unity -> Unity
# Hub.exe; VSCode -> Code.exe. The launcher window itself is just an inspector
# that `pause`s and can be closed harmlessly.
#
# So wc's "progress" works by:
#   * RUN: spawn the .bat (which in turn spawns the real bg process).
#   * is_running(work) = does the real bg process exist? (match token, or the
#     executable basename) — same live detection kc uses to list/kill.
#   * done/ready/failed: read from the bg process's OWN log if `log` is set;
#     otherwise a long-lived bg process with no error == stable.
# We do NOT wrap the .bat in a tracker window (that would be an extra, useless
# window). We simply watch the real process.
import re

LAUNCH_DIR = DESKTOP / "wc_logs"
# A server that never exits is considered "stable" once it has been alive
# this long with no error. Launchers that exit on their own settle via the
# is_running() check turning False.
GRACE_SECONDS = 12
# HARD SAFETY CAP: if a launcher stays alive this long with no `ready` string
# and no error, we declare it `stable` and STOP polling it. This prevents wc
# from ever looping forever. (No work should need longer than this to show it
# is alive-and-well.)
STABLE_MAX_SECONDS = 60
# Global ceiling on how many times wc will spawn `start ""` in one run.
MAX_LAUNCHES = 16

_launched_count = 0

ERROR_KEYWORDS = (
    "traceback", "fatal error", "error:", "exception in",
    "cannot be found", "access is denied", "connection refused",
    "command not found",
)


def _ensure_launch_dir() -> Path:
    try:
        LAUNCH_DIR.mkdir(exist_ok=True)
    except Exception:
        pass
    return LAUNCH_DIR


def _already_running(work: dict) -> bool:
    """True if the work's REAL background process is already alive — so wc
    doesn't spawn a 2nd one."""
    return is_running(work)


def launch_work(work: dict, commandlines: list[str] | None = None) -> dict | None:
    """Spawn `work`'s .bat (which launches the real background process). Returns
    a monitor record, or None if the .bat is missing. Caller (wc) decides
    whether to kill a running instance first -- this just launches.

    SAFETY: never spawns more than MAX_LAUNCHES windows total. The launcher
    window opens then immediately `pause`s (harmless) -- the REAL process is
    what we detect/kill.
    """
    global _launched_count
    wid = work.get("id", "")
    if not wid:
        return None
    if _launched_count >= MAX_LAUNCHES:
        return None
    realbat = work.get("bat")
    if not realbat or not os.path.exists(realbat):
        return None
    run_work(work)   # spawns the .bat in its own visible window (per wc_core)
    _launched_count += 1
    return {"id": wid, "label": work.get("label", wid), "work": work,
            "launched": time.time(), "already": False}


def _read_log(work: dict) -> str:
    log = work.get("log")
    if not log:
        return ""
    p = Path(log) if isinstance(log, (str, Path)) else None
    if not p or not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _scan_error(text: str) -> str:
    low = text.lower()
    for kw in ERROR_KEYWORDS:
        if kw in low:
            return kw
    return ""


# Status values returned by poll_launch:
#   starting | running | ready | stable | done | failed
SETTLED = ("ready", "stable", "done")


def poll_launch(rec: dict, work: dict | None = None, commandlines: list[str] | None = None) -> tuple[str, str]:
    """Return (status, detail) for a launched work, watching its REAL bg proc.

    SAFETY: a work still alive but with no `ready` marker and no error past
    STABLE_MAX_SECONDS is declared `stable` — so wc's monitor loop always ends.
    Pass a pre-scanned `commandlines` (from scan_commandlines) to avoid one
    powershell spawn per poll per work."""
    work = work or rec.get("work") or {}
    if rec.get("already"):
        return ("stable", "already running")
    alive = is_running(work, commandlines)
    if not alive:
        # real process gone -> either it exited (done) or died (failed)
        logtxt = _read_log(work)
        err = _scan_error(logtxt)
        if err:
            return ("failed", err)
        return ("done", "")
    # alive: look for ready marker / error in its log
    logtxt = _read_log(work)
    ready = work.get("ready")
    if ready and str(ready).lower() in logtxt.lower():
        return ("ready", "")
    err = _scan_error(logtxt)
    if err:
        return ("failed", err)
    age = time.time() - rec.get("launched", 0)
    if age >= STABLE_MAX_SECONDS:
        return ("stable", "")
    if age >= GRACE_SECONDS:
        return ("stable", "")
    return ("running", "")


