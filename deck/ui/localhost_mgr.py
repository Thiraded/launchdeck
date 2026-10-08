"""Localhost Manager: combines dev web links and 1-click port killer."""
import re
import subprocess
import tkinter as tk
import webbrowser

from deck.ui import dpi, theme
from deck.ui.widgets import th_button
import launchdeck_core as core

COMMON_DEV_PORTS = [3000, 3001, 5173, 5174, 5175, 8000, 8080]

PORT_SERVICES = {
    3000: {"name": "Hamster Server", "url": "http://localhost:3000"},
    3001: {"name": "Hamster Server 2", "url": "http://localhost:3001"},
    5175: {"name": "Hamster Client (Vite)", "url": "http://localhost:5175"},
    5173: {"name": "Vite Default", "url": "http://localhost:5173"},
    8080: {"name": "Localhost 8080", "url": "http://localhost:8080"},
    8000: {"name": "Localhost 8000", "url": "http://localhost:8000"},
}


def get_process_name(pid):
    """Resolve process name for a given PID."""
    try:
        flags = getattr(core, "_NO_WINDOW", 0)
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True, stderr=subprocess.DEVNULL, creationflags=flags,
        )
        line = out.strip().splitlines()[0]
        if line.startswith('"'):
            return line.split('","')[0].strip('"')
    except Exception:
        pass
    return "process"


def scan_listening_ports(target_ports=None):
    """Return dict of {port: {'pid': int, 'name': str}} for active listening ports."""
    filter_set = set(target_ports) if target_ports else None
    results = {}
    try:
        flags = getattr(core, "_NO_WINDOW", 0)
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            text=True, stderr=subprocess.DEVNULL, creationflags=flags,
        )
        pattern = re.compile(r"TCP\s+[\d\.]+:(\d+)\s+.*\s+LISTENING\s+(\d+)", re.IGNORECASE)
        for line in out.splitlines():
            m = pattern.search(line)
            if m:
                p_num = int(m.group(1))
                pid_num = int(m.group(2))
                if filter_set is None or p_num in filter_set:
                    if p_num not in results:
                        results[p_num] = {
                            "pid": pid_num,
                            "name": get_process_name(pid_num),
                        }
    except Exception:
        pass
    return results


def free_port(port_num):
    """Find and kill process listening on port_num."""
    listening = scan_listening_ports([port_num])
    if port_num not in listening:
        return False, f"Port {port_num} is not in use"
    pid_val = listening[port_num]["pid"]
    proc_name = listening[port_num]["name"]
    if pid_val <= 4:
        return False, "Cannot terminate system process"
    try:
        flags = getattr(core, "_NO_WINDOW", 0)
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid_val)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        return True, f"Freed port {port_num} ({proc_name} PID {pid_val})"
    except Exception as err:
        return False, f"Failed to kill PID {pid_val}: {err}"


def open_localhost_manager(dashboard):
    """Show the unified Localhost Manager popup."""
    win, body = dashboard._popup_shell("Localhost Manager")

    status_var = tk.StringVar(value="")
    lbl_status = tk.Label(
        body,
        textvariable=status_var,
        bg=theme.TH_BG,
        fg=theme.TH_DIM,
        font=("Segoe UI", 9),
        anchor="w",
    )
    lbl_status.pack(fill="x", padx=4, pady=(2, 6))

    list_frame = tk.Frame(body, bg=theme.TH_BG)
    list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 6))

    def _render():
        for child in list_frame.winfo_children():
            child.destroy()

        active = scan_listening_ports(COMMON_DEV_PORTS)
        all_ports = sorted(set(COMMON_DEV_PORTS) | set(active.keys()))

        for p in all_ports:
            row = tk.Frame(list_frame, bg=theme.TH_CARD, padx=8, pady=6)
            row.pack(fill="x", pady=2)

            is_online = p in active
            dot = "🟢" if is_online else "⚪"
            dot_color = theme.TH_GREEN if is_online else theme.TH_DIM

            tk.Label(
                row,
                text=dot,
                font=("Segoe UI", 8),
                bg=theme.TH_CARD,
                fg=dot_color,
            ).pack(side="left", padx=(0, 6))

            info = tk.Frame(row, bg=theme.TH_CARD)
            info.pack(side="left", fill="x", expand=True)

            svc = PORT_SERVICES.get(p, {})
            title_text = svc.get("name") or f"Port :{p}"
            if is_online:
                sub_text = f"http://localhost:{p}  •  {active[p]['name']} (PID {active[p]['pid']})"
            else:
                sub_text = f"http://localhost:{p}"

            lbl_title = tk.Label(
                info,
                text=title_text,
                font=theme.TH_FONT_B,
                bg=theme.TH_CARD,
                fg=theme.TH_FG,
                anchor="w",
            )
            lbl_title.pack(fill="x")

            lbl_sub = tk.Label(
                info,
                text=sub_text,
                font=("Segoe UI", 8),
                bg=theme.TH_CARD,
                fg=theme.TH_DIM,
                anchor="w",
            )
            lbl_sub.pack(fill="x")

            # Actions
            btn_box = tk.Frame(row, bg=theme.TH_CARD)
            btn_box.pack(side="right")

            if is_online:
                def _do_free(target_p=p):
                    ok, msg = free_port(target_p)
                    status_var.set(msg)
                    _render()

                th_button(
                    btn_box,
                    text="Free",
                    command=_do_free,
                    style="danger",
                    width=5,
                ).pack(side="right", padx=(4, 0))

            def _do_open(target_p=p):
                webbrowser.open(f"http://localhost:{target_p}")
                dashboard._close_popup(win)

            th_button(
                btn_box,
                text="Open",
                command=_do_open,
                accent=is_online,
                icon="globe",
                width=5,
            ).pack(side="right")

    _render()

    # Custom Port controls
    custom_box = tk.Frame(body, bg=theme.TH_CARD, padx=8, pady=6)
    custom_box.pack(fill="x", padx=4, pady=(4, 4))

    tk.Label(
        custom_box,
        text="Port:",
        bg=theme.TH_CARD,
        fg=theme.TH_FG,
        font=theme.TH_FONT,
    ).pack(side="left", padx=(0, 4))

    entry_port = tk.Entry(
        custom_box,
        width=8,
        bg=theme.TH_FIELD,
        fg=theme.TH_INPUT_FG,
        insertbackground=theme.TH_INPUT_FG,
        font=theme.TH_FONT,
        relief="flat",
        bd=3,
    )
    entry_port.pack(side="left", padx=(0, 6))
    entry_port.insert(0, "3000")

    def _open_custom():
        try:
            val = int(entry_port.get().strip())
            webbrowser.open(f"http://localhost:{val}")
            dashboard._close_popup(win)
        except ValueError:
            status_var.set("Invalid port number")

    def _free_custom():
        try:
            val = int(entry_port.get().strip())
            ok, msg = free_port(val)
            status_var.set(msg)
            _render()
        except ValueError:
            status_var.set("Invalid port number")

    th_button(custom_box, text="Open", command=_open_custom, width=5).pack(side="right", padx=(4, 0))
    th_button(custom_box, text="Free", command=_free_custom, style="danger", width=5).pack(side="right")

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
