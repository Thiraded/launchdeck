"""Single-instance guard (named mutex)."""
import os
import time

from deck.ui import state


_INSTANCE_MUTEX = "Local\\launchdeck-dashboard"

_instance_handle = None

def ensure_single_instance(timeout_s=30):
    """Own the deck's named mutex, or exit quietly.

    Replaces the old PowerShell birth-time election + stillborn-twin reaper
    + localhost port lock. Root cause of the "uv-venv twin": a venv
    pythonw.exe is a redirector that spawns the base interpreter as its
    CHILD with the same command line. Both matched the election filter, the
    real deck (child) always saw the redirector (parent) as an elder, and a
    1-second birth-time tie + PID order decided whether the REAL deck exited
    at boot. The reaper looked for children of `me` -- the twin is the
    parent -- so it never matched. The redirector never runs Python, so it
    can never take this mutex: exactly one deck owns it. The kernel drops
    it when the owner dies, so a Restart handoff just waits (bounded).
    """
    global _instance_handle
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    ERROR_ALREADY_EXISTS = 183
    deadline = time.time() + timeout_s
    while True:
        h = k32.CreateMutexW(None, 1, _INSTANCE_MUTEX)
        err = ctypes.get_last_error()
        if h and err != ERROR_ALREADY_EXISTS:
            _instance_handle = h  # held for the life of the process
            return
        if h:
            k32.CloseHandle(h)
        if not h:
            state.log(f"[guard] CreateMutexW failed ({err}) -- running unguarded")
            return
        if time.time() >= deadline:
            state.log("[guard] another deck owns the instance mutex -- exiting quietly")
            os._exit(0)
        time.sleep(0.5)
