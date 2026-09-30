"""Job Objects: kernel-owned process identity for deck-launched works.

A detached terminal work starts suspended, joins the named job
`Local\\launchdeck-job-<id>`, then resumes, so every descendant (npm ->
node -> esbuild ...) is a job member with no string guessing. The member
list IS the kill set; `IsProcessInJob` re-checks each PID right before
TerminateProcess, so a recycled PID can never be hit.

Rules (spike 2026-09-30, see Docs/kill-safety.md "Job Objects"):
* No KILL_ON_JOB_CLOSE: works must outlive a deck restart.
* A job's NAME dies with its last handle even while members run, so a
  copy of the handle is planted in the root child; a restarted deck (or
  the console TUI) reopens the job by name.
* Only all-terminal works are jobbed. `app` steps hand off to GUI apps
  (Brave, Unity Hub) that may be born inside the job; those stay on the
  legacy path. A browser a terminal work opens (npx inspector) can still
  land in the job: never-seed names are never counted and never killed.
* Stop = CTRL_BREAK to the work's console group (node/npm exit cleanly
  in ~100 ms), bounded grace, then per-PID TerminateProcess.
"""
import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes as W

PREFIX = "Local\\launchdeck-job-"   # tests rebind this to an isolated namespace
STOP_GRACE_S = 5.0

CREATE_SUSPENDED = 0x4
CREATE_NEW_PROCESS_GROUP = 0x200
CREATE_NO_WINDOW = 0x08000000
_JOB_ALL = 0x1F001F
_PROC_TERMINATE_QUERY = 0x0001 | 0x1000   # TERMINATE | QUERY_LIMITED_INFORMATION
_DUP_SAME_ACCESS = 0x2
_NOT_COUNTED = frozenset({"conhost.exe"})  # console host: lives and dies with members

_ON = os.name == "nt"
_handles: dict[str, int] = {}
_lock = threading.Lock()

if _ON:
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    for _fn, _res in (("CreateJobObjectW", W.HANDLE), ("OpenJobObjectW", W.HANDLE),
                      ("OpenProcess", W.HANDLE), ("OpenThread", W.HANDLE),
                      ("CreateToolhelp32Snapshot", W.HANDLE)):
        getattr(_k32, _fn).restype = _res
    _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, W.LPCWSTR]
    _k32.OpenJobObjectW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
    _k32.QueryInformationJobObject.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                               W.DWORD, ctypes.c_void_p]
    _k32.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
    _k32.IsProcessInJob.argtypes = [W.HANDLE, W.HANDLE, ctypes.POINTER(W.BOOL)]
    _k32.DuplicateHandle.argtypes = [W.HANDLE, W.HANDLE, W.HANDLE,
                                     ctypes.POINTER(W.HANDLE), W.DWORD, W.BOOL, W.DWORD]
    _k32.TerminateProcess.argtypes = [W.HANDLE, W.UINT]
    _k32.CloseHandle.argtypes = [W.HANDLE]
    _k32.Process32FirstW.argtypes = _k32.Process32NextW.argtypes = [W.HANDLE, ctypes.c_void_p]
    _k32.Thread32First.argtypes = _k32.Thread32Next.argtypes = [W.HANDLE, ctypes.c_void_p]


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", W.DWORD),
                ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD),
                ("pcPriClassBase", W.LONG), ("dwFlags", W.DWORD),
                ("szExeFile", W.WCHAR * 260)]


class _THREADENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD),
                ("th32OwnerProcessID", W.DWORD), ("tpBasePri", W.LONG),
                ("tpDeltaPri", W.LONG), ("dwFlags", W.DWORD)]


def eligible(work: dict) -> bool:
    """Jobbed = Windows, detached, and every step a terminal step."""
    steps = work.get("steps") or []
    return (_ON and work.get("run") == "detached" and bool(steps)
            and all((s.get("type") or "terminal") == "terminal" for s in steps))


def job_name(wid: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(wid))
    return PREFIX + safe


def _open(wid: str, create: bool = False) -> int | None:
    """Cached handle to the work's job; opened by name (another deck may
    have created it), created only when launching."""
    with _lock:
        h = _handles.get(wid)
        if h:
            return h
        name = job_name(wid)
        h = _k32.OpenJobObjectW(_JOB_ALL, False, name)
        if not h and create:
            h = _k32.CreateJobObjectW(None, name)
        if h:
            _handles[wid] = h
        return h or None


def _pids(h: int) -> list[int]:
    class _List(ctypes.Structure):
        _fields_ = [("assigned", W.DWORD), ("listed", W.DWORD),
                    ("ids", ctypes.c_size_t * 1024)]
    buf = _List()
    if not _k32.QueryInformationJobObject(h, 3, ctypes.byref(buf),  # BasicProcessIdList
                                          ctypes.sizeof(buf), None):
        return []
    return sorted(int(buf.ids[i]) for i in range(buf.listed))


def _names(pids) -> dict[int, str]:
    """pid -> lowercase exe name, ONE Toolhelp snapshot (no process spawn)."""
    want, out = set(pids), {}
    if not want:
        return out
    snap = _k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == W.HANDLE(-1).value:
        return out
    try:
        e = _PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = _k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.th32ProcessID in want:
                out[e.th32ProcessID] = e.szExeFile.lower()
            ok = _k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        _k32.CloseHandle(snap)
    return out


def members(wid: str, never=frozenset()) -> list[int]:
    """Job member PIDs that count as the work (conhost + never-seed names
    like a browser the work happened to open are excluded)."""
    if not _ON:
        return []
    h = _open(wid)
    if not h:
        return []
    pids = _pids(h)
    names = _names(pids)
    return [p for p in pids
            if p in names and names[p] not in _NOT_COUNTED and names[p] not in never]


def managed(wid: str, never=frozenset()) -> bool:
    return bool(members(wid, never))


def _resume(pid: int) -> int:
    snap = _k32.CreateToolhelp32Snapshot(0x4, 0)  # TH32CS_SNAPTHREAD
    n = 0
    try:
        t = _THREADENTRY32()
        t.dwSize = ctypes.sizeof(t)
        ok = _k32.Thread32First(snap, ctypes.byref(t))
        while ok:
            if t.th32OwnerProcessID == pid:
                th = _k32.OpenThread(0x2, False, t.th32ThreadID)  # SUSPEND_RESUME
                if th:
                    _k32.ResumeThread(th)
                    _k32.CloseHandle(th)
                    n += 1
            ok = _k32.Thread32Next(snap, ctypes.byref(t))
    finally:
        _k32.CloseHandle(snap)
    return n


def spawn(wid: str, argv, **popen_kw) -> subprocess.Popen:
    """Popen *argv* inside the work's job. The child never runs a single
    instruction outside the job (suspended until assigned). If the job
    cannot be used, the child is killed before it ever ran and OSError is
    raised -- the caller decides whether to fall back."""
    h = _open(wid, create=True)
    if not h:
        raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
    flags = popen_kw.pop("creationflags", 0)
    p = subprocess.Popen(argv, creationflags=flags | CREATE_SUSPENDED
                         | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW, **popen_kw)
    ph = W.HANDLE(int(p._handle))
    if not _k32.AssignProcessToJobObject(h, ph):
        err = ctypes.get_last_error()
        _k32.TerminateProcess(ph, 1)
        raise OSError(err, "AssignProcessToJobObject failed")
    # Keep the job name alive for as long as the root lives.
    dup = W.HANDLE()
    _k32.DuplicateHandle(W.HANDLE(-1), W.HANDLE(h), ph, ctypes.byref(dup),
                         0, False, _DUP_SAME_ACCESS)
    if not _resume(p.pid):
        _k32.TerminateProcess(ph, 1)
        raise OSError(0, "could not resume the launched process")
    return p


# CTRL_BREAK is delivered to a console process GROUP, from inside that
# console. The deck must not attach itself (pythonw has no console, and a
# stray event could reach us), so a throwaway helper attaches instead. Its
# handler returns TRUE: it survives the event it broadcasts.
_SENDER = (
    "import ctypes,sys\n"
    "k=ctypes.WinDLL('kernel32',use_last_error=True)\n"
    "H=ctypes.WINFUNCTYPE(ctypes.c_int,ctypes.c_uint)(lambda e:1)\n"
    "k.FreeConsole()\n"
    "if not k.AttachConsole(int(sys.argv[1])): sys.exit(2)\n"
    "k.SetConsoleCtrlHandler(H,1)\n"
    "sys.exit(0 if k.GenerateConsoleCtrlEvent(1,int(sys.argv[2])) else 3)\n")


def _python_console() -> str:
    exe = sys.executable
    base = os.path.basename(exe).lower()
    if base == "pythonw.exe":
        cand = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.exists(cand):
            return cand
    return exe


def ctrl_break(attach_pid: int, group: int) -> bool:
    try:
        r = subprocess.run([_python_console(), "-c", _SENDER, str(attach_pid), str(group)],
                           capture_output=True, timeout=10, creationflags=CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception:
        return False


def _terminate_if_member(h: int, pid: int) -> bool:
    """TerminateProcess *pid* only if it is (still) in job *h*."""
    ph = _k32.OpenProcess(_PROC_TERMINATE_QUERY, False, pid)
    if not ph:
        return False
    try:
        inside = W.BOOL()
        if not _k32.IsProcessInJob(ph, h, ctypes.byref(inside)) or not inside:
            return False
        return bool(_k32.TerminateProcess(ph, 1))
    finally:
        _k32.CloseHandle(ph)


def stop(wid: str, group: int | None = None, never=frozenset(),
         protected=frozenset(), grace: float = STOP_GRACE_S) -> list[int]:
    """Graceful then forced stop of the work's job. Returns survivors
    (empty = stopped). Never touches a never-seed name or a protected PID."""
    h = _open(wid)
    if not h:
        return []
    targets = [p for p in members(wid, never) if p not in protected]
    if not targets:
        return []
    # The group id is the root's PID (CREATE_NEW_PROCESS_GROUP) and stays
    # valid after the root exits; attach through any live member.
    attach = group if group in targets else targets[0]
    ctrl_break(attach, group or attach)
    deadline = time.monotonic() + max(0.0, grace)
    while time.monotonic() < deadline:
        if not [p for p in members(wid, never) if p not in protected]:
            return []
        time.sleep(0.05)
    # Hard stop: the member list is re-read, and each PID re-checked
    # against the job right before TerminateProcess (no PID reuse).
    for pid in members(wid, never):
        if pid not in protected:
            _terminate_if_member(h, pid)
    time.sleep(0.1)
    return [p for p in members(wid, never) if p not in protected]
