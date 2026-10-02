"""launchdeck_dashboard.py — floating desktop button + Works dashboard.

The always-on-top lightning button opens the borderless dashboard. Drag the
button to move it; the dashboard follows its position. Clicking the button
again closes the dashboard and all child popups.

  * the dashboard has [+ New Task] + per-work edit/delete -> writes works.json.
  * ALL works are detached (no console): output goes to launchdeck_logs and the
    log button tails it live. Stop = kill tree.

Entry point only (launchdeck.bat runs this file via pythonw). The
code lives in deck/ui/ -- see Docs/architecture.md "Dashboard modules".
Stdlib only (ctypes + tkinter).
"""
from deck.ui.main import main

if __name__ == "__main__":
    main()
