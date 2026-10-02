"""registry.json + atomic, cross-process-locked state writes."""

import json
import os
import threading
import time
from pathlib import Path

from deck.core import common

REGISTRY = common.HERE / "registry.json"


# --------------------------------------------------------------------------
# registry (for fast lookup of currently-running works)
# --------------------------------------------------------------------------
# State files are read-modify-written by the dashboard and several
# worker threads. A truncating write_text let a concurrent reader see a
# half-written file (-> {} -> written back, dropping every key), and two
# writers lost each other's update. Writes now go to a temp file and are
# swapped in with os.replace (atomic on NTFS); read-modify-write sequences
# hold an in-process lock plus a cross-process named mutex.
_STATE_LOCK = threading.RLock()


class _StateMutex:
    """Cross-process lock (Windows named mutex); no-op elsewhere/on error."""

    NAME = "Local\\launchdeck-state"

    def __enter__(self):
        self._h = None
        if os.name != "nt":
            return self
        try:
            import ctypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = ctypes.c_void_p
            k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                         ctypes.c_wchar_p]
            k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            k32.WaitForSingleObject.restype = ctypes.c_uint
            h = k32.CreateMutexW(None, 0, self.NAME)
            if h:
                # WAIT_OBJECT_0 (0) or WAIT_ABANDONED (0x80) both mean owned.
                if k32.WaitForSingleObject(h, 5000) in (0, 0x80):
                    self._h, self._k32 = h, k32
                else:
                    k32.CloseHandle(ctypes.c_void_p(h))
        except Exception:
            self._h = None
        return self

    def __exit__(self, *exc):
        if self._h:
            import ctypes
            try:
                self._k32.ReleaseMutex(ctypes.c_void_p(self._h))
            finally:
                self._k32.CloseHandle(ctypes.c_void_p(self._h))
        return False


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        # A reader holding the file open can make replace fail briefly.
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.02)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def _load_registry() -> dict:
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_registry(data: dict) -> None:
    try:
        _atomic_write_text(REGISTRY, json.dumps(data, indent=2))
    except Exception:
        pass


def _update_registry(fn) -> None:
    """Locked read-modify-write of registry.json (fn mutates the dict)."""
    with _STATE_LOCK, _StateMutex():
        data = _load_registry()
        fn(data)
        _save_registry(data)


def register(work: dict, pid: int | None = None, runner: str = "") -> None:
    """Record that `work` was launched (with a timestamp)."""
    entry = {
        "label": work.get("label", work["id"]),
        "bat": work.get("bat", ""),
        "launched": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if pid:
        entry["pid"] = int(pid)
        entry["parent_pid"] = os.getpid()
    if runner:
        entry["runner"] = str(runner)
    _update_registry(lambda data: data.__setitem__(work["id"], entry))


def unregister(work: dict) -> None:
    _update_registry(lambda data: data.pop(work["id"], None))
