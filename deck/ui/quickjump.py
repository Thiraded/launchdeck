"""Project Quick Jump dialog for opening workspaces in VS Code."""
import os
import tkinter as tk

from deck.ui import dpi, icons, theme
from deck.ui.widgets import th_button
import launchdeck_core as core


def get_known_projects():
    """Discover distinct project directories from manifest and launcher."""
    projects = [
        {"name": "LaunchDeck (Launcher)", "path": str(core.HERE), "icon": "zap"},
    ]
    seen = {str(core.HERE).lower()}
    try:
        manifest = core.load_manifest()
        for w in manifest.get("works", []):
            label = w.get("label", w.get("id"))
            vars_dict = w.get("vars", {})
            p_dir = vars_dict.get("PROJECT") or vars_dict.get("APPDIR")
            if not p_dir:
                match = w.get("match", "")
                if ":\\" in match:
                    p_dir = match
            if p_dir and os.path.exists(p_dir):
                norm = os.path.normpath(p_dir).lower()
                if norm not in seen:
                    seen.add(norm)
                    projects.append({
                        "name": label,
                        "path": os.path.normpath(p_dir),
                        "icon": w.get("icon", "code"),
                    })
    except Exception:
        pass
    return projects


def open_projects_dialog(dashboard):
    """Show the Projects popup."""
    win, body = dashboard._popup_shell("Projects")

    list_frame = tk.Frame(body, bg=theme.TH_BG)
    list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 8))

    projects = get_known_projects()

    for proj in projects:
        row = tk.Frame(list_frame, bg=theme.TH_CARD, padx=8, pady=6)
        row.pack(fill="x", pady=3)

        info = tk.Frame(row, bg=theme.TH_CARD)
        info.pack(side="left", fill="x", expand=True)

        lbl_name = tk.Label(
            info,
            text=proj["name"],
            font=theme.TH_FONT_B,
            bg=theme.TH_CARD,
            fg=theme.TH_FG,
            anchor="w",
        )
        lbl_name.pack(fill="x")

        lbl_path = tk.Label(
            info,
            text=proj["path"],
            font=("Segoe UI", 8),
            bg=theme.TH_CARD,
            fg=theme.TH_DIM,
            anchor="w",
        )
        lbl_path.pack(fill="x")

        def _open(p_path=proj["path"]):
            dashboard._close_popup(win)
            dashboard.open_vscode(p_path)

        th_button(
            row,
            text="Open",
            command=_open,
            accent=True,
            icon="code",
            width=6,
        ).pack(side="right", padx=(8, 0))

    try:
        win.update_idletasks()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        dashboard._place_near_launcher(
            win,
            min(win.winfo_reqwidth(), sw - 32),
            min(win.winfo_reqheight(), sh - 120),
        )
    except Exception:
        pass

    dashboard._track_popup(win)
    return win
