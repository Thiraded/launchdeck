"""Process-wide deck state: settings, live running set, the Tk action
queue, and work ops shared by the dashboard and native host."""
from pathlib import Path
import queue
import threading
import time

import launchdeck_core as core
from deck.ui import theme


HERE = Path(__file__).resolve().parents[2]  # repo root

LOG = HERE / "launchdeck_logs" / "launchdeck-tray.log"

def collapsed_groups():
    """Set of collapsed group ids (manifest settings.collapsed)."""
    try:
        col = core.get_settings(core.load_manifest()).get("collapsed", [])
    except Exception:
        col = []
    return {x for x in col if isinstance(x, str)}

def dashboard_theme():
    """Active theme name from manifest settings (settings.theme)."""
    try:
        t = core.get_settings(core.load_manifest()).get("theme", "dark")
    except Exception:
        t = "dark"
    return t if t in theme.PALETTES else "dark"

def dashboard_compact():
    """Single-line rows? From manifest settings (settings.compact)."""
    try:
        return bool(core.get_settings(core.load_manifest()).get("compact", True))
    except Exception:
        return True

def log(msg):
    try:
        LOG.parent.mkdir(exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S") + " " + msg + "\n")
    except Exception:
        pass

# --------------------------------------------------------------------------
# live state (background thread)
# --------------------------------------------------------------------------
_running: set = set()

_lock = threading.Lock()

actions = queue.Queue()  # native host -> Tk thread requests ("toggle_ui", ...)

# Woken by the tk thread after every action so the monitor re-scans NOW
# instead of at the next 3s tick (stale cache + refresh = white flash).
_rescan = threading.Event()

hotkey_host = None  # hidden native host owning the global hotkey window

def running_snapshot():
    with _lock:
        return set(_running)

def monitor_loop():
    while True:
        try:
            manifest = core.load_manifest()
            cls = core.scan_commandlines()
            if not core.scan_available() or not cls:
                raise RuntimeError("process scan unavailable")
            s = {w["id"] for w in manifest.get("works", [])
                 if w.get("detect") is not False and core.is_running(w, cls)}
            with _lock:
                global _running
                _running = s
        except Exception as e:
            log(f"monitor: {e}")
        _rescan.wait(3.0)  # periodic tick, or instant when an action lands
        _rescan.clear()

# --------------------------------------------------------------------------
# work ops (shared by dashboard + quick menu)
# --------------------------------------------------------------------------
def work_by_id(wid):
    return core.work_by_id(core.load_manifest(), wid)

def toggle_start_stop(work):
    """Start if stopped, stop if running. Returns status string."""
    try:
        commandlines = core.scan_commandlines()
        if not core.scan_available() or not commandlines:
            return f"status unavailable for '{work.get('label')}' (process scan failed)"
    except Exception as e:
        return f"status unavailable for '{work.get('label')}' ({e})"
    if core.is_running(work, commandlines):
        try:
            result = core.kill_work(work)
            if result is not None:
                detail = (" (no safe target)" if not result else
                          " (PIDs " + ", ".join(map(str, result)) + ")")
                return f"stop blocked '{work.get('label')}'{detail}"
            return f"stopped '{work.get('label')}'"
        except Exception as e:
            return f"stop failed: {e}"
    else:
        rec = core.launch_work(work)
        if rec is None:
            return f"cannot launch '{work.get('label')}' (nothing runnable?)"
        return f"started '{work.get('label')}'"
