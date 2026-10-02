"""Tray icon + right-click quick menu (runs on the tray thread;
anything touching Tk is queued to state.actions)."""
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
    def on_hotkey(self, hid):
        """Global Alt+W pressed anywhere -> toggle the dashboard."""
        state.actions.put("toggle_ui")

    def on_tray_event(self, uid, ev):
        if uid in (0, 1):
            if ev in (WM_LBUTTONUP, 0x0203):
                state.actions.put("toggle_ui")
            elif ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu()

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
