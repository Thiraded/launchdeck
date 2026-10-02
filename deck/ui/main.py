"""Deck entry point (launchdeck_dashboard.py forwards here)."""
from tkinter import messagebox
import os
import sys
import threading
import tkinter as tk
import traceback

from deck.ui import dpi, state
from deck.ui.app import Dashboard
from deck.ui.instance import ensure_single_instance
from deck.ui.selftest import self_test
from deck.ui.hotkey import HotkeyHost


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
    # before ANY window (native host hwnd included): otherwise Windows
    # bitmap-stretches the deck at 125/150% scaling (blurry).
    dpi.enable()
    host = HotkeyHost()
    state.hotkey_host = host
    try:
        if not host.start():
            state.log(f"hotkey host not available: {host.last_error}")
        th = threading.Thread(target=state.monitor_loop, daemon=True)
        th.start()
        dash = Dashboard()
        dash.ensure()
        dash.show_launcher()
        dash._ensure_hotkey()
        state.log("deck ready (desktop button + dashboard ready)")

        try:
            dash.root.mainloop()
        finally:
            try:
                host.stop()
            except Exception:
                pass
    except Exception:
        # pythonw has no console: without this, failures are invisible
        # and leave a ghost native host behind.
        state.log("FATAL:\n" + traceback.format_exc())
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("deck crashed",
                                 "deck hit an error. See launchdeck_logs/launchdeck-tray.log")
            r.destroy()
        except Exception:
            pass
        os._exit(1)
