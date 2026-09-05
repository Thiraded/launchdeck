"""wctray.py — wc in the Windows system tray (notification area, bottom-right).

Click the tray icon -> popup dashboard (PowerToys Workspaces style):
    [icon] label            (o) running / ( ) stopped   [Open/Hide/Show/Stop]

  * tray icon lives at the taskbar's far right (notification area).
  * left-click = open/close the dashboard popup near the tray.
  * right-click = quick menu (dashboard + per-work Start/Stop + Quit).
  * dashboard has [+ New Task] + per-work edit/delete -> writes works.json.
  * Hide = true hide (SW_HIDE: gone from taskbar AND Alt+Tab, process keeps
    running). Show brings it back. Stop = kill tree + close window.
  * optional "icon" per work in works.json (emoji, e.g. "icon": "🎮").

Stdlib only (ctypes + tkinter). Run via wctray.bat (pythonw, no console).
"""
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
import datetime
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox
from pathlib import Path

import wc_core as core
from wc_tray import TrayIcon, WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU

HERE = Path(__file__).resolve().parent
LOG = HERE / "wc_logs" / "wctray.log"
APP_TIP = "Works"

_SINGLE_PORT = 51237  # wctray single-instance lock (OS releases it on exit)
_lock_sock = None


def am_spawned_twin():
    """True if another wctray instance should own this boot (we exit).

    Total-order election among all live wctray processes: the OLDEST
    survives (ties broken by smallest PID); everyone else exits quietly.
    This deterministically kills the uv-venv double-exec twin (always
    younger than its spawner), extra double-clicks, and ghosts of races
    past -- with no timing races and no dialogs. An orphaned twin with
    no older sibling alive takes over (correct failover).
    Only exact-signature rows count (python exe + wctray.py in cmdline).
    Fail-open (run) if the check itself errors.
    """
    try:
        if "--self-test" in sys.argv:
            return False
        me = os.getpid()
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
             "foreach ($p in (Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\") ) "
             "{ if ($p.CommandLine -like '*wctray.py*') "
             "{ Write-Output ($p.ProcessId.ToString() + '|' + $p.ConvertToDateTime($p.CreationDate).ToString('yyyyMMddHHmmss')) } }"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
            creationflags=getattr(core, "_NO_WINDOW", 0))
        mine = ""
        elders = []
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split("|")
            if len(parts) != 2 or not parts[0].strip().isdigit():
                continue
            pid, born = int(parts[0].strip()), parts[1].strip()
            if pid == me:
                mine = born
            else:
                elders.append((born, pid))
        if not mine:
            return False  # we are not even listed -- proceed
        for born, pid in elders:
            if born < mine or (born == mine and pid < me):
                log(f"[election] elder wctray pid={pid} born={born} owns this boot -- exiting")
                return True
    except Exception as e:
        log(f"[election] failed open: {e}")
    return False


def ensure_single_instance(timeout_s=30):
    """If another wctray is already running, tell the user and exit.

    Prevents the duplicate-tray-icon trap (clicks landing on a stale
    instance while a second one owns the real state)."""
    global _lock_sock
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    deadline = time.time() + timeout_s
    while True:
        try:
            s.bind(("127.0.0.1", _SINGLE_PORT))
            break
        except OSError:
            if time.time() >= deadline:
                log("[guard] port still held after wait -- exiting quietly")
                os._exit(0)
            time.sleep(2)
    _lock_sock = s  # keep bound for the life of the process


def self_test():
    """Smoke without clicks: scan + build the dashboard off-screen."""
    manifest = core.load_manifest()
    cls = core.scan_commandlines()
    print(f"self-test: {len(manifest.get('works', []))} works, "
          f"{len(manifest.get('groups', []))} groups, scan {len(cls)} lines")
    d = Dashboard()
    d.ensure()
    d.refresh()
    d.root.update_idletasks()
    print(f"self-test: dashboard rows: {len(d.list_frame.winfo_children())}")
    d.root.destroy()
    print("SELF-TEST OK")
    return 0

ICON_CHOICES = ["\u26a1", "\U0001f5a5", "\U0001f3ae", "\U0001f310", "\U0001f4e6", "\U0001f680", "\U0001f527", "\U0001f3a8", "\U0001f916", "\U0001f4be", "\U0001f4dd", "\U0001f3b5"]
DOT_ON, DOT_OFF = "🟢", "⚪"

# -- dark PowerToys-style theme (stdlib tk only, no deps) --------------------
TH_BG = "#1E2126"        # window
TH_CARD = "#2A2E35"      # work card
TH_FIELD = "#3C4043"     # entries
TH_FG = "#E8EAED"        # text
TH_DIM = "#9AA0A6"       # secondary text
TH_ACCENT = "#4C8DFF"    # primary buttons / highlights
TH_ACCENT_HI = "#5A9BFF"
TH_BTN = "#3A3F47"       # secondary buttons
TH_BTN_HI = "#4A5058"
TH_GREEN = "#3FB950"
TH_GRAY = "#6B7280"
TH_FONT = ("Segoe UI", 10)
TH_FONT_B = ("Segoe UI", 10, "bold")
TH_FONT_S = ("Segoe UI", 8)


def th_button(parent, text, command, width=8, accent=False):
    return tk.Button(parent, text=text, command=command, width=width,
                     font=("Segoe UI", 9), relief="flat", bd=0, padx=8, pady=3,
                     cursor="hand2",
                     bg=TH_ACCENT if accent else TH_BTN, fg="white",
                     activebackground=TH_ACCENT_HI if accent else TH_BTN_HI,
                     activeforeground="white")


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
        time.sleep(3.0)


# --------------------------------------------------------------------------
# stillborn-twin reaper (uv-venv launcher spawns the uv base interpreter
# running our own script as OUR child on every start; the twin hangs
# before main() -- no port, no tray icon -- and would pile up forever)
# --------------------------------------------------------------------------
def reap_stillborn_twins(first_delay=60, period=300):
    """Reap only exact-signature stillborn children; log everything.

    A child is reaped iff ALL hold: name is python(w).exe, its command
    line contains wctray.py, its interpreter DIFFERS from ours, and it is
    older than 90s. Anything unparseable or doubtful is left alone.
    """
    import datetime
    try:
        mine = (sys.executable or "").lower()
    except Exception:
        mine = ""
    me = os.getpid()

    def scan_once():
        try:
            r = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "$me=" + str(me) + "; foreach ($p in (Get-CimInstance Win32_Process)) "
                 "{ if ($p.ParentProcessId -eq $me -and $null -ne $p.CommandLine "
                 "-and $p.CommandLine -like '*wctray.py*') "
                 "{ Write-Output ($p.ProcessId.ToString() + '|' + $p.Name + '|' + $p.ExecutablePath "
                 "+ '|' + $p.ConvertToDateTime($p.CreationDate).ToString('yyyyMMddHHmmss')) } }"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
                creationflags=getattr(core, "_NO_WINDOW", 0))
        except Exception as e:
            log(f"[reaper] scan failed: {e}")
            return
        now = datetime.datetime.now()
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split("|")
            if len(parts) < 4:
                continue
            pid_s, name, exe, born_s = (p.strip() for p in parts[:4])
            if not pid_s.isdigit():
                continue
            pid = int(pid_s)
            if pid == me:
                continue
            if (name or "").lower() not in ("python.exe", "pythonw.exe"):
                continue
            if not exe or (exe or "").lower() == mine:
                continue  # same interpreter as us -- never touch
            try:
                born = datetime.datetime.strptime(born_s[:14], "%Y%m%d%H%M%S")
            except Exception:
                continue  # unparseable age -- touch nothing
            if (now - born).total_seconds() < 90:
                continue
            log(f"[reaper] reaping stillborn twin pid={pid} exe={exe}")
            try:
                subprocess.run(["taskkill.exe", "/F", "/PID", str(pid)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
                               creationflags=getattr(core, "_NO_WINDOW", 0))
            except Exception as e:
                log(f"[reaper] reap failed: {e}")

    time.sleep(first_delay)
    while True:
        try:
            scan_once()
        except Exception as e:
            log(f"[reaper] {e}")
        time.sleep(period)


# --------------------------------------------------------------------------
# work ops (shared by dashboard + quick menu)
# --------------------------------------------------------------------------
def work_by_id(wid):
    return core.work_by_id(core.load_manifest(), wid)


def toggle_start_stop(work):
    """Start if stopped, stop if running. Returns status string."""
    if core.is_running(work):
        try:
            core.kill_work(work)
            return f"stopped '{work.get('label')}'"
        except Exception as e:
            return f"stop failed: {e}"
    else:
        rec = core.launch_work(work)
        if rec is None:
            return f"cannot launch '{work.get('label')}' (bat missing?)"
        return f"started '{work.get('label')}'"


def toggle_hide_show(work):
    if core.is_work_hidden(work):
        _n, msg = core.show_work_windows(work)
        return msg
    if not core.is_running(work):
        return "not running — nothing to hide"
    _n, msg = core.hide_work_windows(work)
    return msg


# --------------------------------------------------------------------------
# tray with dynamic quick menu
# --------------------------------------------------------------------------
ID_DASHBOARD = 4001
ID_QUIT = 4002
ID_BASE = 5000  # per-work: BASE+i*2 = start/stop, +1 = hide/show


class WorkTray(TrayIcon):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parked = {}
        self._park_next = 100
        self._park_lock = threading.RLock()

    def toggle_console(self):
        actions.put("toggle_ui")  # left-click -> dashboard popup

    # parked work icons: wid -> {"uid": int, "hicon": handle}

    def on_tray_event(self, uid, ev):
        """Route main and parked icon clicks without racing icon cleanup."""
        if uid in (0, 1):
            if ev in (WM_LBUTTONUP, 0x0203):
                actions.put("toggle_ui")
            elif ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu()
            return
        with self._park_lock:
            match = next((wid for wid, info in self.parked.items()
                          if info.get("uid") == uid), None)
        if match is not None:
            actions.put(("unpark", match))

    def park_work(self, wid, label):
        """Park a hidden work as its own tray icon. Idempotent."""
        with self._park_lock:
            if wid in self.parked:
                return True
            if not (self.hwnd and self._alive):
                return False
            uid = self._park_next
            self._park_next += 1
            hicon = self.add_work_icon(
                uid, f"\U0001f7e2 {label} (hidden) -- click to restore")
            if not hicon:
                return False
            self.parked[wid] = {"uid": uid, "hicon": hicon, "label": label}
        log(f"parked '{label}' as tray icon uid={uid}")
        try:
            self.notify("Parked in tray", f"{label} -- click its icon to restore")
        except Exception:
            pass
        return True

    def unpark_work(self, wid, restore=True):
        """Restore first; keep the icon when restoration is incomplete."""
        with self._park_lock:
            info = self.parked.get(wid)
        if info is None:
            return None
        if restore:
            work = work_by_id(wid)
            if work is not None:
                _count, message = core.show_work_windows(work)
                if core.is_work_hidden(work):
                    return message
            else:
                message = f"work '{wid}' no longer exists"
        else:
            message = f"unparked '{wid}'"
        with self._park_lock:
            info = self.parked.pop(wid, None)
            if info is not None:
                self.del_work_icon(info["uid"], info.get("hicon"))
        return message

    def sync_parked(self):
        try:
            hidden = core.hidden_work_ids()
        except Exception:
            return
        with self._park_lock:
            stale = [wid for wid in self.parked if wid not in hidden]
        for wid in stale:
            self.unpark_work(wid, restore=False)

    def unpark_all(self):
        with self._park_lock:
            work_ids = list(self.parked)
        for wid in work_ids:
            self.unpark_work(wid, restore=False)

    def _on_taskbar_created(self):
        """Recreate parked icons after Explorer loses notification state."""
        import ctypes
        with self._park_lock:
            for wid, info in list(self.parked.items()):
                hicon = self.add_work_icon(
                    info["uid"], f"\U0001f7e2 {info.get('label', wid)} (hidden)")
                if hicon:
                    old = info.get("hicon")
                    info["hicon"] = hicon
                    if old:
                        try:
                            ctypes.windll.user32.DestroyIcon(old)
                        except Exception:
                            pass

    def _before_tray_shutdown(self):
        self.unpark_all()


    def _show_menu(self):
        import ctypes
        from wc_tray import (MF_STRING, MF_SEPARATOR, TPM_RIGHTBUTTON,
                             TPM_RETURNCMD, POINT)
        u32 = ctypes.windll.user32
        manifest = core.load_manifest()
        works = manifest.get("works", [])
        run = running_snapshot()
        hmenu = u32.CreatePopupMenu()
        u32.AppendMenuW(hmenu, MF_STRING, ID_DASHBOARD, "📋 Open dashboard")
        u32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        self._menu_ids = {}
        for i, w in enumerate(works[:25]):  # menu cap: 25 works
            wid = w.get("id", "")
            icon = w.get("icon", "⚡")
            dot = DOT_ON if wid in run else DOT_OFF
            verb = "Stop" if wid in run else "Start"
            item = f"{dot} {icon} {w.get('label', wid)} — {verb}"
            cmd = ID_BASE + i * 2
            self._menu_ids[cmd] = (wid, "run")
            u32.AppendMenuW(hmenu, MF_STRING, cmd, item[:120])
            if wid in run:
                hid = "Show" if core.is_work_hidden(w) else "Hide"
                item2 = f"      {hid} window"
                cmd2 = cmd + 1
                self._menu_ids[cmd2] = (wid, "hide")
                u32.AppendMenuW(hmenu, MF_STRING, cmd2, item2)
        u32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        u32.AppendMenuW(hmenu, MF_STRING, ID_QUIT, "Quit wctray")
        pt = POINT()
        u32.GetCursorPos(ctypes.byref(pt))
        u32.SetForegroundWindow(self.hwnd)
        cmd = u32.TrackPopupMenu(
            hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD | 0x0080,
            pt.x, pt.y, 0, self.hwnd, None)
        u32.DestroyMenu(hmenu)
        if cmd:
            self._on_menu(cmd)

    def _on_menu(self, cmd):
        if cmd == ID_QUIT:
            self.quit_event.set()
            actions.put("quit")
            return
        if cmd == ID_DASHBOARD:
            actions.put("show_ui")
            return
        wid_act = getattr(self, "_menu_ids", {}).get(cmd)
        if not wid_act:
            return
        wid, act = wid_act
        w = work_by_id(wid)
        if not w:
            return
        try:
            if act == "run":
                log(toggle_start_stop(w))
            else:
                msg = toggle_hide_show(w)
                try:
                    if core.is_work_hidden(w):
                        self.park_work(wid, w.get("label", wid))
                    else:
                        self.unpark_work(wid, restore=False)
                except Exception as e:
                    log(f"menu park: {e}")
                log(msg)
        except Exception as e:
            log(f"menu action failed: {e}")


# --------------------------------------------------------------------------
# dashboard popup (tkinter, near the tray)
# --------------------------------------------------------------------------
class Dashboard:
    def __init__(self):
        self.root = None
        self.status_var = None
        self.list_frame = None
        self.visible = False

    def ensure(self):
        if self.root is not None:
            return
        r = tk.Tk()
        r.title("Works")
        r.configure(bg=TH_BG)
        r.attributes("-topmost", True)
        r.resizable(False, False)
        try:
            sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
            W, H = 400, 600
            r.geometry(f"{W}x{H}+{sw - W - 16}+{sh - H - 60}")
        except Exception:
            pass
        top = tk.Frame(r, bg=TH_BG)
        top.pack(fill="x", padx=12, pady=(12, 4))
        tk.Label(top, text="⚡ Works", font=("Segoe UI", 14, "bold"),
                 bg=TH_BG, fg="white").pack(side="left")
        th_button(top, text="+ New Task", command=self.open_editor,
                  width=10, accent=True).pack(side="right")
        th_button(top, text="⟳", command=self.refresh,
                  width=3).pack(side="right", padx=(0, 6))
        self.status_var = tk.StringVar(value="")
        tk.Label(r, textvariable=self.status_var, fg="#E3B341", bg=TH_BG,
                 font=("Segoe UI", 9)).pack(fill="x", padx=12)
        body = tk.Frame(r, bg=TH_BG)
        body.pack(fill="both", expand=True, padx=12, pady=4)
        canvas = tk.Canvas(body, highlightthickness=0, bg=TH_BG)
        scroll = tk.Scrollbar(body, command=canvas.yview, relief="flat", bd=0,
                              width=12, bg=TH_BTN, troughcolor=TH_BG,
                              activebackground=TH_BTN_HI, highlightthickness=0)
        self.list_frame = tk.Frame(canvas, bg=TH_BG)
        self.list_frame.bind("<Configure>",
                             lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        bot = tk.Frame(r, bg=TH_BG)
        bot.pack(fill="x", padx=12, pady=(4, 12))
        th_button(bot, text="Open works.json",
                  command=lambda: os.startfile(str(core.MANIFEST)),
                  width=15).pack(side="left")
        th_button(bot, text="Quit tray",
                  command=lambda: actions.put("quit"),
                  width=10).pack(side="right")
        r.withdraw()
        r.protocol("WM_DELETE_WINDOW", self.hide)
        self.root = r
        self.refresh()
        r.after(800, self._poll)

    def _handle_action(self, action):
        if action == "toggle_ui":
            self.toggle()
        elif action == "show_ui":
            self.show()
        elif isinstance(action, tuple) and len(action) == 2 and action[0] == "unpark":
            self._do_unpark_action(action[1])
        elif action == "refresh":
            self.refresh()
        elif action == "quit":
            try:
                if tray_host is not None:
                    tray_host.stop()
            finally:
                self.root.destroy()
        else:
            log(f"unknown action: {action!r}")

    def _poll(self):
        while True:
            try:
                action = actions.get_nowait()
            except queue.Empty:
                break
            try:
                self._handle_action(action)
            except Exception as e:
                log(f"action {action!r} failed: {e}")
        try:
            self.root.after(250, self._poll)
        except Exception:
            pass
        # No-flicker refresh: rebuild ONLY when something actually changed
        # (running set, hidden set, or the manifest itself). Otherwise just
        # touch the cheap status line -- destroying + rebuilding the whole
        # list every 3s is what made it blink.
        now = time.time()
        if self.visible and now - getattr(self, "_last", 0) > 3:
            self._last = now
            try:
                man = core.load_manifest()
                sig = (frozenset(running_snapshot()),
                       frozenset(core.hidden_work_ids()),
                       tuple((w.get("id"), w.get("label"), w.get("icon"),
                              w.get("bat"), w.get("match")) for w in man.get("works", [])),
                       tuple((g.get("id"), g.get("label"), tuple(g.get("members", [])))
                             for g in man.get("groups", [])))
            except Exception:
                sig = None
            if sig is not None and sig != getattr(self, "_last_sig", None):
                self._last_sig = sig
                self.refresh(quiet=True)
            else:
                try:
                    self.say(f"{len(running_snapshot())} running")
                except Exception:
                    pass

    def toggle(self):
        self.ensure()
        self.show() if not self.visible else self.hide()

    def show(self):
        self.ensure()
        self.refresh()
        self.root.deiconify()
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
        self.visible = True

    def hide(self):
        try:
            self.root.withdraw()
        except Exception:
            pass
        self.visible = False

    def say(self, msg):
        try:
            self.status_var.set(msg)
        except Exception:
            pass

    def refresh(self, quiet=False):
        if self.root is None:
            return
        for ch in self.list_frame.winfo_children():
            ch.destroy()
        manifest = core.load_manifest()
        run = running_snapshot()
        by_id = {w.get("id"): w for w in manifest.get("works", [])}
        shown = set()

        def work_row(parent, w):
            wid = w.get("id", "")
            shown.add(wid)
            running = wid in run
            icon = w.get("icon", "⚡")
            hidden = core.is_work_hidden(w)
            dot_c = TH_GREEN if running else TH_GRAY
            sub = "running" if running else "stopped"
            if hidden:
                sub += "  ·  hidden"
            row = tk.Frame(parent, bg=TH_CARD, padx=2, pady=2,
                           highlightbackground="#3A3F47", highlightthickness=1)
            row.pack(fill="x", pady=3, padx=2)
            topl = tk.Frame(row, bg=TH_CARD)
            topl.pack(fill="x", padx=8, pady=(6, 0))
            tk.Label(topl, text="\u25cf", fg=dot_c, bg=TH_CARD,
                     font=("Segoe UI", 11)).pack(side="left")
            tk.Label(topl, text=f" {icon} {w.get('label', wid)}",
                     font=TH_FONT_B, bg=TH_CARD, fg=TH_FG).pack(side="left")
            tk.Label(row, text=sub, font=TH_FONT_S,
                     bg=TH_CARD, fg=TH_DIM).pack(anchor="w", padx=28)
            btns = tk.Frame(row, bg=TH_CARD)
            btns.pack(fill="x", padx=8, pady=(4, 6))
            th_button(btns, "Stop" if running else "Start",
                      lambda w=w: self._act_run(w),
                      width=8, accent=not running).pack(side="left")
            th_button(btns, "Show" if hidden else "Hide",
                      lambda w=w: self._act_hide(w),
                      width=8).pack(side="left", padx=4)
            th_button(btns, "↻", lambda w=w: self._act_restart(w),
                      width=3).pack(side="left")
            th_button(btns, "\u270f\ufe0f", lambda w=w: self.open_editor(w),
                      width=3).pack(side="left", padx=(4, 0))
            th_button(btns, "🗑", lambda w=w: self.delete_work(w),
                      width=3).pack(side="left", padx=4)

        for g in manifest.get("groups", []):
            members = [by_id[m] for m in g.get("members", []) if m in by_id]
            if not members:
                continue
            on = sum(1 for m in members if m.get("id") in run)
            gf = tk.LabelFrame(self.list_frame, text=f"  \U0001f4c1 {g.get('label', g.get('id'))}  ({on}/{len(members)})  ",
                               font=("Segoe UI", 10, "bold"),
                               bg=TH_BG, fg=TH_ACCENT, relief="flat", bd=0,
                               labelanchor="nw")
            gf.pack(fill="x", pady=6)
            for m in members:
                work_row(gf, m)
            brow = tk.Frame(gf, bg=TH_BG)
            brow.pack(fill="x", padx=6, pady=(0, 6))
            th_button(brow, text="▶ Start all",
                      command=lambda ms=members: self._act_all(ms, True),
                      width=10, accent=True).pack(side="left")
            th_button(brow, text="\u23f9 Stop all",
                      command=lambda ms=members: self._act_all(ms, False),
                      width=10).pack(side="left", padx=4)
        for w in manifest.get("works", []):
            if w.get("id") not in shown:
                work_row(self.list_frame, w)
        if not quiet:
            self.say(f"{len(run)} running")

    # -- row actions (ALL async: scans/kills block for seconds and must
    # never freeze the tk mainloop -- that freeze was the real bug) -------
    def _act_async(self, fn, working_msg):
        self.say(working_msg)
        th = threading.Thread(target=self._run_async, args=(fn,), daemon=True)
        th.start()

    def _run_async(self, fn):
        try:
            msg = fn()
        except Exception as e:
            msg = f"failed: {e}"

        def _done(m=msg):
            self.say(m)
            self.refresh(quiet=True)
            try:
                if tray_host is not None:
                    tray_host.sync_parked()
            except Exception as e:
                log(f"park sync: {e}")
        try:
            self.root.after(0, _done)
        except Exception:
            pass

    def _act_run(self, w):
        self._act_async(lambda: toggle_start_stop(w), "working…")

    def _act_hide(self, w):
        self._act_async(lambda: self._do_hide(w), "working…")

    def _do_hide(self, w):
        msg = toggle_hide_show(w)
        try:
            if core.is_work_hidden(w):
                if tray_host is not None and tray_host.park_work(
                        w["id"], w.get("label", w["id"])):
                    msg += " — parked in tray ^"
            else:
                if tray_host is not None:
                    tray_host.unpark_work(w["id"], restore=False)
        except Exception as e:
            log(f"park wiring: {e}")
        return msg

    def _do_restart(self, w):
        try:
            core.kill_work(w)
        except Exception as e:
            return f"stop failed: {e}"
        time.sleep(1.5)
        rec = core.launch_work(w)
        return "restarted — fresh window" if rec else "start failed (bat missing?)"

    def _do_unpark_action(self, wid):
        """Work-icon click in tray: restore its window, drop the icon."""
        if tray_host is None:
            return
        try:
            res = tray_host.unpark_work(wid, restore=True)
        except Exception as e:
            res = f"restore failed: {e}"
        if res is not None:
            self.say(res)
            self.refresh(quiet=True)

    def _act_restart(self, w):
        self._act_async(lambda: self._do_restart(w), "restarting…")

    def _act_all(self, members, start):
        self._act_async(lambda: self._do_all(members, start), "working…")

    def _do_all(self, members, start):
        msgs = []
        for m in members:
            running = core.is_running(m)
            if start and not running:
                r = core.launch_work(m)
                msgs.append("started" if r else "FAILED")
            elif not start and running:
                try:
                    core.kill_work(m)
                    msgs.append("stopped")
                except Exception as e:
                    msgs.append(f"err {e}")
        return ", ".join(msgs) or "nothing to do"

    def delete_work(self, w):
        if not messagebox.askyesno("Delete task",
                                    f"Remove '{w.get('label')}' from works.json?\n(running process is NOT killed)"):
            return
        try:
            manifest = core.load_manifest()
            manifest["works"] = [x for x in manifest["works"] if x.get("id") != w.get("id")]
            for g in manifest.get("groups", []):
                g["members"] = [m for m in g.get("members", []) if m != w.get("id")]
            core.MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            core.clear_hidden_work(w)
            try:
                if tray_host is not None:
                    tray_host.unpark_work(w.get("id", ""), restore=False)
            except Exception:
                pass
            self.say(f"deleted '{w.get('label')}'")
            self.refresh(quiet=True)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e))

    # -- config editor ----------------------------------------------------
    def open_editor(self, work=None):
        manifest = core.load_manifest()
        win = tk.Toplevel(self.root)
        win.title("Edit Task" if work else "New Task")
        win.attributes("-topmost", True)
        win.resizable(False, False)
        win.configure(bg=TH_BG)
        vals = {
            "label": tk.StringVar(value=(work or {}).get("label", "")),
            "bat": tk.StringVar(value=(work or {}).get("bat", "")),
            "match": tk.StringVar(value=str((work or {}).get("match", ""))),
            "icon": tk.StringVar(value=(work or {}).get("icon", "⚡")),
            "group": tk.StringVar(value=""),
            "detect": tk.BooleanVar(value=(work or {}).get("detect", True)),
        }
        # find current group
        if work:
            for g in manifest.get("groups", []):
                if work.get("id") in g.get("members", []):
                    vals["group"].set(g.get("id", ""))
        fields = [("Label", "label"), ("Start file (.bat/.lnk/.exe)", "bat"),
                  ("Match token (CommandLine)", "match")]
        for i, (cap, key) in enumerate(fields):
            tk.Label(win, text=cap, bg=TH_BG, fg=TH_FG).grid(
                row=i, column=0, sticky="w", padx=8, pady=3)
            tk.Entry(win, textvariable=vals[key], width=44, relief="flat", bd=4,
                     bg=TH_FIELD, fg="white", insertbackground="white").grid(
                         row=i, column=1, padx=8, pady=3)
        th_button(win, text="Browse…",
                  command=lambda: vals["bat"].set(
                      filedialog.askopenfilename(
                          initialdir=str(HERE),
                          filetypes=[("Launchers", "*.bat *.lnk *.exe"), ("All", "*.*")]) or vals["bat"].get()),
                  width=9).grid(row=1, column=2, padx=8)
        tk.Label(win, text="Icon", bg=TH_BG, fg=TH_FG).grid(
            row=3, column=0, sticky="w", padx=8, pady=3)
        om_icon = tk.OptionMenu(win, vals["icon"], *ICON_CHOICES)
        om_icon.configure(bg=TH_FIELD, fg="white", relief="flat", bd=0,
                          activebackground=TH_BTN_HI, highlightthickness=0)
        om_icon["menu"].configure(bg=TH_FIELD, fg="white")
        om_icon.grid(row=3, column=1, sticky="w", padx=8)
        tk.Label(win, text="Group", bg=TH_BG, fg=TH_FG).grid(
            row=4, column=0, sticky="w", padx=8, pady=3)
        groups = ["(none — standalone)"] + [f"{g.get('label')} [{g.get('id')}]" for g in manifest.get("groups", [])]
        gvar = tk.StringVar(value="(none — standalone)")
        if vals["group"].get():
            for txt in groups:
                if vals["group"].get() in txt:
                    gvar = tk.StringVar(value=txt)
        om_grp = tk.OptionMenu(win, gvar, *groups)
        om_grp.configure(bg=TH_FIELD, fg="white", relief="flat", bd=0,
                         activebackground=TH_BTN_HI, highlightthickness=0)
        om_grp["menu"].configure(bg=TH_FIELD, fg="white")
        om_grp.grid(row=4, column=1, sticky="w", padx=8)
        tk.Checkbutton(win, text="detect running state", variable=vals["detect"],
                       bg=TH_BG, fg=TH_FG, selectcolor=TH_FIELD,
                       activebackground=TH_BG, activeforeground=TH_FG).grid(
            row=5, column=1, sticky="w", padx=8)

        def save():
            label = vals["label"].get().strip()
            bat = vals["bat"].get().strip()
            match = vals["match"].get().strip()
            if not label or not bat:
                messagebox.showwarning("Missing", "Label + start file are required.")
                return
            if not os.path.exists(bat):
                if not messagebox.askyesno("File not found",
                                           f"'{bat}' does not exist.\nSave anyway?"):
                    return
            man = core.load_manifest()
            wid = (work or {}).get("id") or ("w-" + "".join(
                c.lower() if c.isalnum() else "-" for c in label).strip("-")[:24])
            entry = {"id": wid, "label": label, "bat": bat,
                     "match": match or os.path.basename(bat),
                     "icon": vals["icon"].get(), "detect": bool(vals["detect"].get())}
            ids = [x.get("id") for x in man["works"]]
            if wid in ids:
                man["works"] = [entry if x.get("id") == wid else x for x in man["works"]]
            else:
                man["works"].append(entry)
            # group assignment
            gsel = gvar.get()
            gid = ""
            if not gsel.startswith("(none"):
                gid = gsel.split("[")[-1].rstrip("]")
            for g in man.get("groups", []):
                members = [m for m in g.get("members", []) if m != wid]
                if g.get("id") == gid:
                    members.append(wid)
                g["members"] = members
            man["works"].sort(key=lambda x: x.get("label", ""))
            man["works"] = sorted(man["works"], key=lambda x: x.get("label", ""))
            man["works"].sort(key=lambda x: 0 if x.get("id") in
                              {m for g in man.get("groups", []) for m in g.get("members", [])} else 1)
            try:
                core.MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as e:
                messagebox.showerror("Save failed", str(e))
                return
            win.destroy()
            self.say(f"saved '{label}'")
            self.refresh(quiet=True)

        th_button(win, text="Save", command=save, width=14,
                  accent=True).grid(row=6, column=1, pady=10)


# --------------------------------------------------------------------------
def main():
    log("wctray starting")
    try:
        import faulthandler
        faulthandler.enable(file=open(LOG, "a", encoding="utf-8"))
    except Exception:
        pass
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    if am_spawned_twin():
        os._exit(0)
    ensure_single_instance()
    tray = WorkTray(tip=f"{APP_TIP} — starting…", color=(0, 120, 215))
    global tray_host
    tray_host = tray
    try:
        if not tray.start():
            log(f"tray not available: {tray.last_error}")
        th = threading.Thread(target=monitor_loop, args=(tray,), daemon=True)
        th.start()
        rp = threading.Thread(target=reap_stillborn_twins, daemon=True)
        rp.start()
        dash = Dashboard()
        dash.ensure()
        log("wctray ready (tray + dashboard up)")

        dash.show()  # visible on startup: proves life, teaches where it lives
        try:
            dash.root.mainloop()
        finally:
            try:
                tray.stop()
            except Exception:
                pass
    except Exception:
        # pythonw has no console: without this, failures are invisible
        # and leave ghost tray icons behind.
        log("FATAL:\n" + traceback.format_exc())
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("wctray crashed",
                                 "wctray hit an error. See wc_logs/wctray.log")
            r.destroy()
        except Exception:
            pass
        os._exit(1)


if __name__ == "__main__":
    main()
