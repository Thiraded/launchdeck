"""Find/close a work's windows (legacy kill's Alt+F4 pass; Docs/windows.md)."""

import ntpath
import os
import time

from deck.core import detect

WM_CLOSE = 0x0010  # Alt+F4 / clicking X -- the graceful window close


def close_work_windows(work: dict, target_pids: set[int] | None = None,
                       target_table: list[tuple[int, int, str, str]] | None = None) -> int:
    """Post WM_CLOSE (Alt+F4) to every top-level window in the work's tree.

    Killing the task alone can leave the bare terminal window behind
    (observed: the task dies, the `cmd /k` host survives with a dead
    prompt -- it can even be an ANCESTOR of every kill seed, so no
    downward process kill reaches it). Closing the WINDOW is what removes
    it: the console host exits and attached processes get the console
    close request, exactly as if the user pressed Alt+F4.

    Uses find_work_hwnds -- the same guarded owner set as the `h` key
    (own protected chain + powershell* + badgui never included). Returns
    the number of windows confirmed gone afterwards (bounded ~2s wait).
    Never raises; 0 means "no windows found / nothing to close".
    """
    if target_pids is None:
        hwnds = find_work_hwnds(work)
    else:
        table = target_table if target_table is not None else detect.scan_table()
        current_pids = set(target_pids)
        # Kill owns only the downward set. Do not walk from a child back into
        # a user's hosting shell just to close a window; that ancestor is not
        # part of the task being stopped. One level of children still catches
        # the console host owned by the target.
        hwnds = _hwnds_for_pids(current_pids, table,
                                include_ancestors=False)
    if not hwnds:
        return 0
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                        ctypes.c_void_p, ctypes.c_void_p]
        user32.PostMessageW.restype = ctypes.c_int
        user32.IsWindow.argtypes = [ctypes.c_void_p]
        user32.IsWindow.restype = ctypes.c_int
    except Exception:
        return 0
    hwnds = list(dict.fromkeys(hwnds))
    for hwnd in hwnds:
        try:
            if user32.IsWindow(hwnd):
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass
    for _ in range(8):
        try:
            if all(not user32.IsWindow(h) for h in hwnds):
                return len(hwnds)
        except Exception:
            break
        time.sleep(0.25)
    try:
        return sum(1 for h in hwnds if not user32.IsWindow(h))
    except Exception:
        return 0


# --------------------------------------------------------------------------
# Find the visible HWNDs owned by a work's process tree. Used by `h` to
# hide/show that work's terminal window without killing the process.
# --------------------------------------------------------------------------
def find_work_hwnds(work: dict) -> list[int]:
    """Return the HWNDs of every top-level window whose owning PID belongs
    to the work's process tree (i.e. processes whose CommandLine contains
    one of the work's match tokens). Returned HWNDs are safe to pass to
    ShowWindow / PostMessage."""
    toks = detect.kill_tokens_for(work)
    if not toks:
        return []
    # 1) collect candidate PIDs in pure Python over ONE shared table
    # (same NEVER-seed GUI guard as kill_work, via the shared set).
    table = detect.scan_table()
    names = {pid: (name or "") for pid, _pp, name, _c in table}
    cmds = {pid: (cmd or "") for pid, _p, _n, cmd in table}
    by_parent = {pid: ppid for pid, ppid, _n, _c in table}

    def _is_ps(pid: int) -> bool:
        return names.get(pid, "").lower().startswith("powershell")

    pids = {pid for pid, cmd in cmds.items()
            if cmd and not _is_ps(pid)
            and not detect._is_never_seed_process(names.get(pid, ""), cmd)
            and any(detect._identity_token_matches(t, cmd) for t in toks)}
    if not pids:
        return []
    # 2+3) owner set + EnumWindows. The ancestor walk (to reach the cmd.exe
    # host) lives ONLY in _hwnds_for_pids: bounded, stops at our protected
    # chain, and climbs through cmd.exe hosts only. The unbounded copy that
    # used to sit here reached explorer.exe / Code.exe for manually started
    # runs, and the one-level-down pass then pulled in every app they own.
    found = _hwnds_for_pids(pids, table)
    # 4) exact-title match: every launcher sets `title <works.json label>`
    # (§4.8), so the window is also findable by title when PID-ownership
    # mapping misses (reparented host, WT active-tab title). Guarded --
    # never a shared host (see _title_hwnds_guarded).
    try:
        for h in _title_hwnds_guarded(work.get("label") or "", table):
            if h not in found:
                found.append(h)
    except Exception:
        pass
    return found


def _hwnds_for_pids(pids: set[int],
                    table: list[tuple[int, int, str, str]] | None = None,
                    include_ancestors: bool = True) -> list[int]:
    """Enumerate top-level windows owned by the work's process tree.

    A console window is owned by conhost.exe, typically a CHILD of the
    work's cmd -- while matchable seeds (node with an absolute script
    path) sit BELOW that cmd. So raw-PID matching and upward-only walks
    both miss. Owner set = seeds + bounded ancestors of seeds (up to 8,
    stopping at our own protected chain) + one level of children below
    each (catches conhost + wrapper cmds). powershell* is traversed but
    never added (it hosts user sessions). Kill stays DOWNWARD-ONLY;
    this up+down-1 expansion applies to HIDE (reversible) only.
    Pure ctypes over the shared table, no extra scan."""
    import ctypes
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_int
    # PID -> (parent, name) maps from the shared table (no extra scan).
    if table is None:
        table = detect.scan_table()
    parent: dict[int, int] = {}
    names: dict[int, str] = {}
    children: dict[int, list[int]] = {}
    for pid, ppid, name, _cmd in table:
        parent[pid] = ppid
        names[pid] = (name or "").strip()
        children.setdefault(ppid, []).append(pid)

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
    if include_ancestors:
        # Up from each seed through cmd.exe hosts ONLY (bounded, stop at
        # protected/missing/root). Anything else -- powershell, explorer,
        # an IDE, a terminal app -- is the user's host, not the work's:
        # walking through it would reach Code.exe/explorer.exe and the
        # one-level-down pass below would then grab all of their windows.
        for s in list(owners):
            cur, depth = s, 0
            while depth < 8:
                par = parent.get(cur, 0)
                if not par or par in prot:
                    break
                if ntpath.basename(names.get(par, "")).lower() not in ("cmd.exe", "cmd"):
                    break
                owners.add(par)
                cur, depth = par, depth + 1
    # One level down (conhost + wrapper cmds). Never protected/powershell.
    for o in list(owners):
        for ch in children.get(o, []):
            if ch in prot or is_ps(ch) \
                    or detect._is_shared_window_host(names.get(ch, "")):
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


_TITLE_GUARD_NAMES = ("windowsterminal", "explorer")


def _title_hwnds_guarded(label: str,
                         table: list[tuple[int, int, str, str]] | None = None) -> list[int]:
    """Top-level windows whose title EXACTLY equals label, minus shared hosts.

    Exact case-insensitive match only: conhost defaults ('', 'C:\\...cmd.exe')
    can never collide, and no substring guessing that could grab a user
    window. Shared-host guard (applied AFTER matching): a hit owned by our
    own PID, by windowsterminal / explorer, or by powershell* is dropped --
    closing or hiding a shared Windows Terminal window would take the user's
    other tabs with it, so WT-manual runs keep process-level behavior only.
    Includes invisible windows (a hidden/parked orphan of the work still
    belongs to it; kill clears hidden tracking anyway). Never raises.
    """
    want = (label or "").strip().lower()
    if not want:
        return []
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                          ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
    except Exception:
        return []
    cands: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lparam):
        try:
            buf = ctypes.create_unicode_buffer(256)
            if user32.GetWindowTextW(hwnd, buf, 256) > 0 \
                    and (buf.value or "").strip().lower() == want:
                cands.append(int(hwnd))
        except Exception:
            pass
        return 1
    try:
        user32.EnumWindows(cb, 0)
    except Exception:
        return []
    _title_hwnds_guarded._cb = cb  # type: ignore[attr-defined]
    if not cands:
        return []
    owners = _hwnd_owner_pids(cands)
    src = table if table is not None else detect.scan_table()
    names = {pid: (name or "") for pid, _pp, name, _c in src}
    me = os.getpid()
    out = []
    for h in dict.fromkeys(cands):
        pid = owners.get(h, 0)
        if not pid or pid == me:
            continue
        nm = (names.get(pid) or "").lower()
        base = nm[:-4] if nm.endswith(".exe") else nm
        if base in _TITLE_GUARD_NAMES or base.startswith("powershell"):
            continue
        out.append(h)
    return out


def _hwnd_owner_pids(hwnds: list[int]) -> dict[int, int]:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.GetWindowThreadProcessId.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    except Exception:
        return {}
    owners = {}
    for hwnd in dict.fromkeys(hwnds):
        try:
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                owners[hwnd] = int(pid.value)
        except Exception:
            pass
    return owners
