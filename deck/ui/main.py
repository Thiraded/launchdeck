"""Deck entry point (launchdeck_dashboard.py forwards here)."""
from tkinter import messagebox
import os
import sys
import threading
import tkinter as tk
import traceback

from deck.ui import state
from deck.ui.app import Dashboard
from deck.ui.instance import ensure_single_instance
from deck.ui.selftest import self_test
from deck.ui.tray import WorkTray


# --------------------------------------------------------------------------
def main():
    state.log("deck starting")
    try:
        import faulthandler
        faulthandler.enable(file=open(state.LOG, "a", encoding="utf-8"))
    except Exception:
        pass
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    ensure_single_instance()
    tray = WorkTray(tip=f"{state.APP_TIP} — starting…", color=(0, 120, 215))
    state.tray_host = tray
    try:
        if not tray.start():
            state.log(f"tray not available: {tray.last_error}")
        th = threading.Thread(target=state.monitor_loop, args=(tray,), daemon=True)
        th.start()
        dash = Dashboard()
        dash.ensure()
        dash._ensure_hotkey()
        state.log("deck ready (tray + dashboard up)")

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
        state.log("FATAL:\n" + traceback.format_exc())
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("deck crashed",
                                 "deck hit an error. See wc_logs/launchdeck-tray.log")
            r.destroy()
        except Exception:
            pass
        os._exit(1)
