"""launchdeck_dashboard.py — launchdeck in the Windows system tray (notification area, bottom-right).

Click the tray icon -> popup dashboard (PowerToys Workspaces style):
    [icon] label            (o) running / ( ) stopped   [Start/Log/Stop]

  * tray icon lives at the taskbar's far right (notification area).
  * left-click = open/close the dashboard popup near the tray.
  * right-click = quick menu (dashboard + per-work Start/Stop/Log + Quit).
  * dashboard has [+ New Task] + per-work edit/delete -> writes works.json.
  * ALL works are detached (no console): output goes to launchdeck_logs and the
    log button tails it live. Stop = kill tree.

Entry point only (launchdeck.bat runs this file via pythonw). The
code lives in deck/ui/ -- see Docs/architecture.md "Dashboard modules".
Stdlib only (ctypes + tkinter).
"""
from deck.ui.main import main

if __name__ == "__main__":
    main()
