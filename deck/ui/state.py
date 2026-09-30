"""Process-wide deck state: log file, settings reads, live running
set (monitor thread), the tk action queue, and work ops shared by
the dashboard and the tray menu."""
from pathlib import Path
import queue
import threading
import time

import launchdeck_core as core
from deck.ui import theme


HERE = Path(__file__).resolve().parents[2]  # repo root

LOG = HERE / "wc_logs" / "launchdeck-tray.log"

APP_TIP = "Works"

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

_prev_running: set = set()

actions = queue.Queue()  # tray thread -> tk thread requests ("toggle_ui", ...)

# Woken by the tk thread after every action so the monitor re-scans NOW
# instead of at the next 3s tick (stale cache + refresh = white flash).
_rescan = threading.Event()

tray_host = None  # the live WorkTray, set by main() for park/unpark wiring

def running_snapshot():
    with _lock:
        return set(_running)

def monitor_loop(tray, notify_new=True):
    global _prev_running
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
            new = s - _prev_running
            if new and notify_new:
                try:
                    names = [w.get("label", wid) for w in manifest["works"]
                             if w.get("id") in new]
                    tray.notify("Work running", ", ".join(names)[:200])
                except Exception:
                    pass
            n_total = len(manifest.get("works", []))
            try:
                tray.set_tooltip(f"{APP_TIP} — {len(s)}/{n_total} running")
            except Exception:
                pass
            try:
                rehidden = core.sweep_hidden_windows(manifest)
                for wid, n in rehidden.items():
                    log(f"sweep re-hid {n} window(s) for {wid}")
            except Exception as e:
                log(f"sweep: {e}")
            _prev_running = s
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
