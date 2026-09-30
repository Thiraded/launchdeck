"""Tray icon + right-click quick menu (runs on the tray thread;
anything touching Tk is queued to state.actions)."""
import threading

from launchdeck_tray import TrayIcon
from launchdeck_tray import WM_CONTEXTMENU
from launchdeck_tray import WM_LBUTTONUP
from launchdeck_tray import WM_RBUTTONUP
import launchdeck_core as core
from deck.ui import state
from deck.ui import theme


# --------------------------------------------------------------------------
# tray with dynamic quick menu
# --------------------------------------------------------------------------
ID_DASHBOARD = 4001

ID_QUIT = 4002

ID_BASE = 5000  # per-work: BASE+i*2 = start/stop, +1 = log viewer

class WorkTray(TrayIcon):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parked = {}
        self._park_next = 100
        self._park_lock = threading.RLock()

    def toggle_console(self):
        state.actions.put("toggle_ui")  # left-click -> dashboard popup

    def on_hotkey(self, hid):
        """Global Alt+W pressed anywhere -> toggle the dashboard."""
        state.actions.put("toggle_ui")

    # parked work icons: wid -> {"uid": int, "hicon": handle}

    def on_tray_event(self, uid, ev):
        """Route main and parked icon clicks without racing icon cleanup."""
        if uid in (0, 1):
            if ev in (WM_LBUTTONUP, 0x0203):
                state.actions.put("toggle_ui")
            elif ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu()
            return
        with self._park_lock:
            match = next((wid for wid, info in self.parked.items()
                          if info.get("uid") == uid), None)
        if match is not None:
            state.actions.put(("unpark", match))

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
        state.log(f"parked '{label}' as tray icon uid={uid}")
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
            work = state.work_by_id(wid)
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
        from launchdeck_tray import (MF_STRING, MF_SEPARATOR, TPM_RIGHTBUTTON,
                             TPM_RETURNCMD, POINT)
        u32 = ctypes.windll.user32
        manifest = core.load_manifest()
        works = manifest.get("works", [])
        run = state.running_snapshot()
        hmenu = u32.CreatePopupMenu()
        u32.AppendMenuW(hmenu, MF_STRING, ID_DASHBOARD, "📋 Open dashboard")
        u32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        self._menu_ids = {}
        for i, w in enumerate(works[:25]):  # menu cap: 25 works
            wid = w.get("id", "")
            icon = w.get("icon", "⚡")
            dot = theme.DOT_ON if wid in run else theme.DOT_OFF
            verb = "Stop" if wid in run else "Start"
            item = f"{dot} {icon} {w.get('label', wid)} — {verb}"
            cmd = ID_BASE + i * 2
            self._menu_ids[cmd] = (wid, "run")
            u32.AppendMenuW(hmenu, MF_STRING, cmd, item[:120])
            if wid in run:
                cmd2 = cmd + 1
                self._menu_ids[cmd2] = (wid, "log")
                u32.AppendMenuW(hmenu, MF_STRING, cmd2, "      ☰ Log")
        u32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        u32.AppendMenuW(hmenu, MF_STRING, ID_QUIT, "Quit deck")
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
            state.actions.put("quit")
            return
        if cmd == ID_DASHBOARD:
            state.actions.put("show_ui")
            return
        wid_act = getattr(self, "_menu_ids", {}).get(cmd)
        if not wid_act:
            return
        wid, act = wid_act
        w = state.work_by_id(wid)
        if not w:
            return
        try:
            if act == "run":
                # Hand off to the Tk side (_act_run -> worker thread). Running
                # toggle_start_stop here blocked the tray message pump for the
                # whole stop (scans + 2.5s wait): icon dead, Alt+W ignored.
                state.actions.put(("run", wid))
            elif act == "log":
                state.actions.put(("log", wid))  # dashboard opens the viewer
            else:
                state.log(f"unknown menu action: {act}")
        except Exception as e:
            state.log(f"menu action failed: {e}")
