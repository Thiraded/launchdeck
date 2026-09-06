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
import re
import socket
import subprocess
import sys
import threading
import time
import webbrowser
import datetime
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox
from pathlib import Path

import wc_core as core
from wc_tray import TrayIcon, WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU
from wc_tray import register_hotkey, unregister_hotkey

HERE = Path(__file__).resolve().parent
LOG = HERE / "wc_logs" / "wctray.log"
APP_TIP = "Works"

# ANSI fg name (wc_core.ansi_runs) -> viewer color. Server logs assume a
# dark console, so the log viewer is dark too (docker-logs style).
LOG_FG = {
    "black": "#808080", "red": "#cd3131", "green": "#0dbc79",
    "yellow": "#e5e510", "blue": "#2472c8", "magenta": "#bc3fbc",
    "cyan": "#11a8cd", "white": "#e5e5e5", "gray": "#767676",
    "bright-red": "#f14c4c", "bright-green": "#23d18b",
    "bright-yellow": "#f5f543", "bright-blue": "#3b8eea",
    "bright-magenta": "#d670d6", "bright-cyan": "#29b8db",
    "bright-white": "#ffffff",
}

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


def _tag_links(txt, start, end):
    """Tag URL substrings in [start, end) with the clickable link tag."""
    try:
        text = txt.get(start, end)
    except Exception:
        return
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:!?)]")
        if not url:
            continue
        a = f"{start}+{m.start()}c"
        b = f"{start}+{m.start() + len(url)}c"
        try:
            txt.tag_add("link", a, b)
        except Exception:
            pass


def _open_link(event):
    """Open the clicked link-tagged URL in the default browser."""
    try:
        w = event.widget
        idx = w.index(f"@{event.x},{event.y}")
        rng = w.tag_prevrange("link", f"{idx}+1c") or w.tag_nextrange("link", idx)
        if rng:
            webbrowser.open(w.get(rng[0], rng[1]).strip())
    except Exception:
        pass
    return "break"

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
    cv = d.list_frame.master
    assert cv.cget("scrollregion") not in ("", "0 0 0 0"), cv.cget("scrollregion")
    assert d.root.bind("<MouseWheel>"), "wheel binding missing (backlog #4)"
    print(f"self-test: scrollregion {cv.cget('scrollregion')} + wheel OK")
    w = next(x for x in manifest["works"] if x.get("id") == "hamster-clint")
    ed = d.open_editor(w)
    d.root.update_idletasks()
    assert ed is not None and ed.winfo_exists(), "editor did not build"
    d._close_popup(ed)
    print("self-test: editor (steps prefill) OK")
    ed0 = d.open_editor(None)
    d.root.update_idletasks()
    assert ed0 is not None and ed0.winfo_exists(), "new-task editor (fork) did not build"
    d._close_popup(ed0)
    man0 = core.load_manifest()
    f = _work_to_form(man0["works"][0], man0)
    assert f["label"].endswith(" copy")
    assert f["match"] == str(man0["works"][0].get("match", "") or "")
    assert f["steps"] == core.steps_to_text(man0["works"][0].get("steps") or [])
    print("self-test: fork prefill OK")
    man = core.load_manifest()
    assert core.slug_group_id("Hamster combo", man) != "hamstercombo"
    assert core.slug_group_id("New Group", man) == "g-new-group"
    ged = d.open_group_editor(None)
    d.root.update_idletasks()
    assert ged is not None and ged.winfo_exists(), "group editor did not build"
    _found, _i = [ged], 0
    while _i < len(_found):
        _found.extend(_found[_i].winfo_children())
        _i += 1
    assert any(isinstance(_x, tk.Listbox) for _x in _found), "group editor needs the order list"
    d._close_popup(ged)
    print("self-test: group editor + slug OK")
    assert d.root.bind("<FocusOut>"), "popup dismiss binding missing (backlog #5)"
    d._maybe_autodismiss()  # hidden popup: must no-op, never raise
    assert d.visible is False
    print("self-test: popup dismiss wiring OK")
    assert core.parse_hotkey("ctrl+alt+1") == (0x3, 0x31)
    assert core.parse_hotkey("1") is None
    assert core.parse_hotkey("ctrl+f24") == (0x2, 0x87)
    assert core.canonical_hotkey("Ctrl + Alt + 1") == "ctrl+alt+1"
    assert core.hotkey_conflicts(
        {"works": [{"id": "a", "hotkey": "ctrl+alt+1"},
                   {"id": "b", "hotkey": "ctrl+alt+1"}]}) == {"ctrl+alt+1": ["a", "b"]}
    from wc_tray import register_hotkey as _rh, unregister_hotkey as _uh
    hwnd = d.root.winfo_id()
    # A tk window has no wc handler: DefWindowProc's 0 must read as a
    # clean False (never a false-positive success).
    assert _rh(hwnd, 65001, 0x3, 0x87) is False
    assert _uh(hwnd, 65001) is False
    print("self-test: hotkey parse + marshal contract OK")
    assert d.root.overrideredirect(), "dashboard must be borderless"
    lv = d.open_log_viewer(w)
    d.root.update_idletasks()
    assert lv is not None and lv in d._popups
    st = d.open_settings()
    d.root.update_idletasks()
    assert st is not None and st in d._popups
    assert len(d._popups) == 2
    d._close_popups()
    assert d._popups == [] and not lv.winfo_exists() and not st.winfo_exists()
    d._ensure_hotkey()
    assert not getattr(d, "_hotkey_on", False)
    print("self-test: borderless + popup class + settings + hotkey ensure OK")
    assert _apply_palette("light") == "light"
    assert TH_BG == PALETTES["light"]["BG"]
    _apply_palette("dark")
    assert TH_BG == PALETTES["dark"]["BG"]
    print("self-test: theme palettes roundtrip OK")
    sh, _sbody = d._popup_shell("test shell")
    d.root.update_idletasks()
    assert sh.overrideredirect() and sh.winfo_exists(), "popup shell must be borderless"
    d._close_popup(sh)
    assert not sh.winfo_exists()
    print("self-test: borderless popup shell + close OK")
    cb = th_circle_btn(d.root, "▶", lambda: None, style="accent")
    assert len(cb.find_all()) == 2, "circle button must be oval+glyph"
    assert cb.cget("cursor") == "hand2"
    assert hasattr(cb, "recolor")
    cb.destroy()
    print("self-test: circle button OK")
    w = next(x for x in manifest["works"] if x.get("id") == "hamster-clint")
    lv = d.open_log_viewer(w)
    assert lv is not None and d._log_wins.get("hamster-clint") is lv
    assert d.open_log_viewer(w) is None  # toggle: second click closes
    assert "hamster-clint" not in d._log_wins and not lv.winfo_exists()
    print("self-test: log toggle (open/close, no duplicates) OK")
    d._pending["x-test"] = {"state": "starting", "expect": True,
                            "until": time.monotonic() + 20}
    d._act_run({"id": "x-test", "label": "X-Test"})
    assert d._pending.get("x-test", {}).get("state") == "starting", "guard must not clear pending"
    assert "already starting" in d.status_var.get()
    d._pending.pop("x-test", None)
    print("self-test: pending double-click guard OK")
    v = _row_view({"id": "a", "label": "A"}, set(), {})
    assert (v["sub"], v["icon_c"], v["running"]) == ("stopped", TH_DIM, False)
    v = _row_view({"id": "a", "label": "A"}, {"a"}, {})
    assert (v["sub"], v["icon_c"], v["running"]) == ("running", TH_GREEN, True)
    v = _row_view({"id": "a", "label": "A"}, set(),
                  {"a": {"state": "starting", "expect": True, "until": 0}})
    assert (v["sub"], v["sub_c"]) == ("starting…", TH_ACCENT)
    print("self-test: row view-model OK")
    d.refresh()
    f1 = {k: r["frame"] for k, r in d._rows.items()}
    d.refresh()
    f2 = {k: r["frame"] for k, r in d._rows.items()}
    assert f1 and f1 == f2, "same layout must update in place (no rebuild)"
    print("self-test: in-place refresh OK")
    assert _swap_adjacent(["a", "b", "c"], "b", -1) == ["b", "a", "c"]
    assert _swap_adjacent(["a", "b", "c"], "b", +1) == ["a", "c", "b"]
    assert _swap_adjacent(["a", "b", "c"], "a", -1) == ["a", "b", "c"]
    assert _swap_adjacent(["a", "b", "c"], "c", +1) == ["a", "b", "c"]
    assert _swap_adjacent(["a"], "a", +1) == ["a"]
    raw = core.MANIFEST.read_text(encoding="utf-8")
    try:
        w0 = core.load_manifest()["works"][0]
        n0 = len(core.load_manifest()["works"])
        d._duplicate_work(w0)
        man1 = core.load_manifest()
        assert len(man1["works"]) == n0 + 1
        ids1 = [x["id"] for x in man1["works"]]
        at = ids1.index(w0["id"])
        got = man1["works"][at + 1]
        assert got["label"].endswith(" copy") and got["id"] != w0["id"]
        assert {k: v for k, v in got.items() if k not in ("id", "label")} == \
               {k: v for k, v in w0.items() if k not in ("id", "label")}
    finally:
        core.MANIFEST.write_text(raw, encoding="utf-8")
        d.refresh()
    print("self-test: duplicate (+byte-exact restore) OK")
    src = Path(__file__).read_text(encoding="utf-8")
    assert 'man["works"]' + '.sort' not in src, \
        "editor save must not re-sort (custom order)"
    print("self-test: custom-order swap + no-autosort OK")
    d.root.destroy()
    print("SELF-TEST OK")
    return 0

ICON_CHOICES = ["\u26a1", "\U0001f5a5", "\U0001f3ae", "\U0001f310", "\U0001f4e6", "\U0001f680", "\U0001f527", "\U0001f3a8", "\U0001f916", "\U0001f4be", "\U0001f4dd", "\U0001f3b5"]
DOT_ON, DOT_OFF = "🟢", "⚪"

# -- themes (stdlib tk only, no deps) -----------------------------------------
# tkinter can't do rounded corners or shadows, so hierarchy comes from
# spacing + hairlines + ONE accent. Blue = primary action only, red =
# destructive only, everything else quiet gray. The log viewer stays dark
# in both themes (server logs assume a dark console).
PALETTES = {
    "dark": {
        "BG": "#15171C", "CARD": "#1F232B", "CARD_EDGE": "#2E3542",
        "FIELD": "#2A303B", "INPUT_FG": "#FFFFFF",
        "FG": "#EDEFF2", "DIM": "#8F97A5", "FAINT": "#5D6572",
        "ACCENT": "#3E7BFA", "ACCENT_HI": "#5B92FF",
        "BTN": "#2A303B", "BTN_HI": "#374052",
        "DANGER": "#E5534B", "DANGER_HI": "#F1655C",
        "GREEN": "#3FB950", "GRAY": "#596069",
    },
    "light": {
        "BG": "#E9ECF1", "CARD": "#FFFFFF", "CARD_EDGE": "#D4DAE3",
        "FIELD": "#E2E7EE", "INPUT_FG": "#1A1D21",
        "FG": "#1B1E23", "DIM": "#5C6470", "FAINT": "#8A93A0",
        "ACCENT": "#2F6BEE", "ACCENT_HI": "#3E7BFA",
        "BTN": "#E0E5EC", "BTN_HI": "#CFD6E0",
        "DANGER": "#D92D20", "DANGER_HI": "#B42318",
        "GREEN": "#1A7F37", "GRAY": "#A6AEB9",
    },
}
_TH_KEYS = ("BG", "CARD", "CARD_EDGE", "FIELD", "INPUT_FG", "FG", "DIM",
            "FAINT", "ACCENT", "ACCENT_HI", "BTN", "BTN_HI", "DANGER",
            "DANGER_HI", "GREEN", "GRAY")


def _apply_palette(name):
    """Point the TH_* globals at a palette. Widgets read them at build
    time, so a theme switch = apply + full rebuild (see _rebuild)."""
    pal = PALETTES.get(name, PALETTES["dark"])
    g = globals()
    for k in _TH_KEYS:
        g["TH_" + k] = pal[k]
    return name if name in PALETTES else "dark"


_apply_palette("dark")
TH_FONT = ("Segoe UI", 10)
TH_FONT_B = ("Segoe UI", 10, "bold")
TH_FONT_S = ("Segoe UI", 8)
TH_FONT_TITLE = ("Segoe UI", 13, "bold")
TH_FONT_SECTION = ("Segoe UI", 10, "bold")


def th_button(parent, text, command, width=8, accent=False, style=None):
    """Themed button. style: None (secondary) | 'accent' | 'ghost' | 'danger'.

    `accent=True` is shorthand for style='accent' (kept for old call sites).
    Ghost/danger blend into the parent surface (dim text, no box) so the
    primary action is the only thing that shouts; hover still fills.
    """
    if accent:
        style = "accent"
    try:
        parent_bg = parent.cget("bg")
    except Exception:
        parent_bg = TH_CARD
    bg, abg, fg = TH_BTN, TH_BTN_HI, TH_FG
    if style == "accent":
        bg, abg, fg = TH_ACCENT, TH_ACCENT_HI, "white"
    elif style == "ghost":
        bg, abg, fg = parent_bg, TH_BTN_HI, TH_DIM
    elif style == "danger":
        bg, abg, fg = parent_bg, TH_DANGER, TH_DANGER
    b = tk.Button(parent, text=text, command=command, width=width,
                  font=("Segoe UI", 9), relief="flat", bd=0, padx=8, pady=3,
                  cursor="hand2", bg=bg, fg=fg,
                  activebackground=abg, activeforeground="white")
    if style == "ghost":
        b.bind("<Enter>", lambda _e, w=b: w.config(fg=TH_FG))
        b.bind("<Leave>", lambda _e, w=b: w.config(fg=TH_DIM))
    return b


def th_circle_btn(parent, glyph, command, style=None, size=24, font_size=10):
    """Circular icon button, snug around the glyph (tk has no round Button).

    A small Canvas blended into the parent: oval fill + centered glyph.
    styles: None (secondary fill) | 'accent' | 'danger' | 'ghost'.
    Hover fills; hand cursor throughout. All icon-only actions share
    `size`, so clusters line up exactly.
    """
    try:
        parent_bg = parent.cget("bg")
    except Exception:
        parent_bg = TH_CARD
    fill, hover, fg = TH_BTN, TH_BTN_HI, TH_FG
    if style == "accent":
        fill, hover, fg = TH_ACCENT, TH_ACCENT_HI, "white"
    elif style == "danger":
        fill, hover, fg = parent_bg, TH_DANGER, TH_DANGER
    elif style == "ghost":
        fill, hover, fg = parent_bg, TH_BTN_HI, TH_DIM
    c = tk.Canvas(parent, width=size, height=size, highlightthickness=0,
                  bd=0, bg=parent_bg, cursor="hand2")
    oval = c.create_oval(2, 2, size - 2, size - 2, fill=fill, outline="")
    txt = c.create_text(size // 2, size // 2 - 1, text=glyph,
                        font=("Segoe UI", font_size), fill=fg)
    c._oval, c._txt = oval, txt  # for in-place updates (no rebuild)
    st = {"fill": fill, "hover": hover, "fg": fg, "style": style}

    def recolor(fill=None, hover=None, fg=None):
        """Restyle a live circle (state flip without rebuilding the row)."""
        if fill is not None:
            st["fill"] = fill
        if hover is not None:
            st["hover"] = hover
        if fg is not None:
            st["fg"] = fg
        c.itemconfig(oval, fill=st["fill"])
        c.itemconfig(txt, fill=st["fg"])

    c.recolor = recolor

    def _enter(_e):
        c.itemconfig(oval, fill=st["hover"])
        c.itemconfig(txt, fill="white" if st["style"] in ("danger", "accent")
                     else TH_FG)

    def _leave(_e):
        c.itemconfig(oval, fill=st["fill"])
        c.itemconfig(txt, fill=st["fg"])

    c.bind("<Enter>", _enter)
    c.bind("<Leave>", _leave)
    c.bind("<Button-1>", lambda _e: command())
    return c


def _short(text, n=22):
    """Truncate a row title so the status + icon cluster keep their room."""
    text = str(text)
    return text if len(text) <= n else text[:n - 1] + "…"


def _swap_adjacent(ids, wid, direction):
    """Move wid one step in an id list; no-op at the edges. Pure."""
    ids = list(ids)
    if wid not in ids:
        return ids
    i, j = ids.index(wid), ids.index(wid) + direction
    if j < 0 or j >= len(ids):
        return ids
    ids[i], ids[j] = ids[j], ids[i]
    return ids


def _row_view(w, run, pending):
    """Pure view-model for one row (headless-testable, no widgets).

    Returns dict: running, hidden, icon, icon_c, sub, sub_c.
    """
    wid = w.get("id", "")
    running = wid in run
    icon = w.get("icon", "⚡")
    hidden = core.is_work_hidden(w)
    pend = (pending or {}).get(wid)
    if pend:
        state = pend.get("state", "")
        return {"running": running, "hidden": hidden, "icon": icon,
                "icon_c": TH_ACCENT, "sub": state + "…", "sub_c": TH_ACCENT}
    if w.get("run") == "detached" and running:
        sub = "running · no window — see log"
    else:
        sub = "running" if running else "stopped"
    if hidden:
        sub += "  ·  hidden"
    return {"running": running, "hidden": hidden, "icon": icon,
            "icon_c": TH_GREEN if running else TH_DIM,
            "sub": sub, "sub_c": TH_DIM}


def _work_to_form(src, manifest):
    """Prefill values for the task editor when forking src (pure).

    Label gets " copy" so the save path mints a fresh id instead of
    overwriting the source. Group is the editor's display string.
    """
    disp = "(none — standalone)"
    for g in manifest.get("groups", []):
        if src.get("id") in g.get("members", []):
            disp = f"{g.get('label')} [{g.get('id')}]"
            break
    return {"label": (src.get("label", "") or "") + " copy",
            "bat": src.get("bat", "") or "",
            "match": str(src.get("match", "") or ""),
            "icon": src.get("icon", "⚡") or "⚡",
            "group": disp,
            "detect": bool(src.get("detect", True)),
            "steps": core.steps_to_text(src.get("steps") or []),
            "vars": core.vars_to_text(src.get("vars") or {})}


def dashboard_theme():
    """Active theme name from manifest settings (settings.theme)."""
    try:
        t = core.get_settings(core.load_manifest()).get("theme", "dark")
    except Exception:
        t = "dark"
    return t if t in PALETTES else "dark"


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
            return f"cannot launch '{work.get('label')}' (nothing runnable?)"
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

    def on_hotkey(self, hid):
        """Global Alt+W pressed anywhere -> toggle the dashboard."""
        actions.put("toggle_ui")

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
        self._canvas = None
        self._popups = []
        self.visible = False
        self._gen = 0  # bumped by _rebuild so the old _poll retires
        # wid -> {"state", "expect" (running? True/False/None), "until"}.
        # Start/stop marks clear only when the live snapshot CONFIRMS
        # them (or times out) -- never on a stale cache (white flash).
        self._pending = {}
        self._log_wins = {}  # wid -> open log viewer (toggle, never duplicates)
        self._rows = {}  # wid -> live row widgets (in-place refresh)
        self._group_heads = {}  # gid -> LabelFrame (count text updates)
        self._struct_sig = None  # layout key: full rebuild only on change

    def ensure(self):
        if self.root is not None:
            return
        _apply_palette(dashboard_theme())
        r = tk.Tk()
        r.title("Works")
        # Borderless popup (backlog #5): no title bar, no X -- clicking
        # outside dismisses it, so chrome is dead weight.
        r.overrideredirect(True)
        r.configure(bg=TH_BG)
        r.attributes("-topmost", True)
        r.resizable(False, False)
        try:
            sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
            W, H = 480, 600
            r.geometry(f"{W}x{H}+{sw - W - 16}+{sh - H - 60}")
        except Exception:
            pass
        # Brand hairline: 2px accent strip, the only saturated thing
        # besides the primary buttons (borderless popup has no chrome).
        tk.Frame(r, bg=TH_ACCENT, height=2).pack(fill="x")
        top = tk.Frame(r, bg=TH_BG)
        top.pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(top, text="Works", font=TH_FONT_TITLE,
                 bg=TH_BG, fg=TH_FG).pack(side="left")
        th_button(top, text="+ New", command=self.open_editor,
                  width=8, accent=True).pack(side="right")
        th_button(top, text="+ Group",
                  command=lambda: self.open_group_editor(None),
                  width=8).pack(side="right", padx=(0, 4))
        th_circle_btn(top, "⌨", command=self.open_settings,
                      style="ghost").pack(side="right", padx=(0, 4))
        th_circle_btn(top, "⟳", command=self.refresh,
                      style="ghost").pack(side="right", padx=(0, 4))
        self.status_var = tk.StringVar(value="")
        tk.Label(r, textvariable=self.status_var, fg=TH_DIM, bg=TH_BG,
                 font=("Segoe UI", 9)).pack(fill="x", padx=14, pady=(0, 2))
        body = tk.Frame(r, bg=TH_BG)
        body.pack(fill="both", expand=True, padx=12, pady=4)
        canvas = tk.Canvas(body, highlightthickness=0, bg=TH_BG)
        scroll = tk.Scrollbar(body, command=canvas.yview, relief="flat", bd=0,
                              width=12, bg=TH_BTN, troughcolor=TH_BG,
                              activebackground=TH_BTN_HI, highlightthickness=0)
        self.list_frame = tk.Frame(canvas, bg=TH_BG)
        self.list_frame.bind("<Configure>",
                             lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.list_frame, anchor="nw",
                                 tags=("listwin",))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._canvas = canvas
        # Wheel scroll (Windows: delta/120 per notch). Bound on the
        # toplevel: wheel over any row/label bubbles up to it (plain
        # widgets don't consume <MouseWheel>). Without this the ONLY
        # way down was dragging the thin bar (backlog #4).
        r.bind("<MouseWheel>",
               lambda ev, cv=canvas: cv.yview_scroll(-1 * int(ev.delta / 120),
                                                     "units"))
        # Inner frame follows the canvas width (no horizontal squeeze).
        canvas.bind("<Configure>",
                    lambda ev, cv=canvas: cv.itemconfig("listwin",
                                                        width=ev.width))
        bot = tk.Frame(r, bg=TH_BG)
        bot.pack(fill="x", padx=14, pady=(4, 12))
        th_button(bot, text="works.json",
                  command=lambda: os.startfile(str(core.MANIFEST)),
                  width=12, style="ghost").pack(side="left")
        th_button(bot, text="Quit",
                  command=lambda: actions.put("quit"),
                  width=8, style="ghost").pack(side="right")
        r.withdraw()
        r.protocol("WM_DELETE_WINDOW", self.hide)
        # Real-popup behavior (backlog #5): any focus leaving the whole
        # dashboard tree schedules a dismiss check (editors/dialogs are
        # child Toplevels, so focus inside them keeps us open).
        r.bind("<FocusOut>", lambda _e: r.after(150, self._maybe_autodismiss))
        # Clicking the dashboard kills open log viewers (they belong to
        # it); clicking elsewhere kills everything via _maybe_autodismiss.
        r.bind("<FocusIn>", lambda _e: self._close_popups())
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
                if tray_host is not None and getattr(tray_host, "hwnd", None):
                    unregister_hotkey(tray_host.hwnd, 1)
            except Exception:
                pass
            try:
                if tray_host is not None:
                    tray_host.stop()
            finally:
                self.root.destroy()
        else:
            log(f"unknown action: {action!r}")

    def _poll(self):
        gen = getattr(self, "_gen", 0)
        while True:
            try:
                action = actions.get_nowait()
            except queue.Empty:
                break
            try:
                self._handle_action(action)
            except Exception as e:
                log(f"action {action!r} failed: {e}")
        if gen != getattr(self, "_gen", 0):
            return  # rebuilt since: the new tree runs its own poll
        try:
            self.root.after(250, self._poll)
        except Exception:
            pass
        # Global-hotkey self-heal (see _ensure_hotkey): cheap timer check.
        if time.time() - getattr(self, "_last_hk", 0) > 15:
            self._last_hk = time.time()
            self._ensure_hotkey()
        # No-flicker refresh: rebuild ONLY when something actually changed
        # (running set, hidden set, or the manifest itself). Otherwise just
        # touch the cheap status line -- destroying + rebuilding the whole
        # list every 3s is what made it blink.
        if self.visible:
            try:
                self._sweep_pending()  # confirm transitional marks in place
            except Exception:
                pass
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
        try:
            self._sweep_pending()  # drop stale marks before first paint
        except Exception:
            pass
        self.refresh()
        self._place_near_tray()
        self.root.deiconify()
        try:
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
        self.visible = True

    def hide(self):
        try:
            self._close_popups()
        except Exception:
            pass
        try:
            self.root.withdraw()
        except Exception:
            pass
        self.visible = False

    def _place_near_tray(self, win=None, W=480, H=600):
        """Pin a window bottom-right (taskbar/resolution may have moved).

        The dashboard pins to the corner; secondary windows (log viewer)
        sit LEFT of it when it is visible instead of on top of it.
        """
        try:
            win = win or self.root
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            x = sw - W - 16
            if win is not self.root and self.visible:
                x = x - 400 - 12
                if x < 0:
                    x = sw - W - 16
            win.geometry(f"{W}x{H}+{x}+{sh - H - 60}")
        except Exception:
            pass

    def _ensure_hotkey(self):
        """Register the suite hotkey; self-heal on a timer (backlog #5).

        Registration is marshalled to the tray (owner) thread -- a
        direct call from here fails with 1408. Retries until registered;
        silent while taken (no log spam); logs the grab once it lands.
        """
        if getattr(self, "_hotkey_on", False):
            return
        try:
            if tray_host is None or not getattr(tray_host, "hwnd", None):
                return
            hk = core.canonical_hotkey(
                core.get_settings(core.load_manifest()).get(
                    "hotkey", core.DEFAULT_HOTKEY)) or core.DEFAULT_HOTKEY
            parsed = core.parse_hotkey(hk)
            if not parsed:
                return
            mods, vk = parsed
            if register_hotkey(tray_host.hwnd, 1, mods, vk):
                self._hotkey_on = True
                log(f"global hotkey {hk} registered")
                self.say(f"hotkey {hk} on")
        except Exception as e:
            log(f"hotkey ensure failed: {e}")

    def _maybe_autodismiss(self):
        """Dismiss when focus leaves the whole dashboard tree (backlog #5).

        Editor/log dialogs are Toplevel children of the root, so focus
        inside them keeps the popup open; only focus going outside the
        app (or nowhere) dismisses it.
        """
        try:
            if not self.visible or self.root is None:
                return
            try:
                focus = self.root.focus_displayof()
            except Exception:
                focus = None
            if focus is None:
                self.hide()
                return
            if not str(focus).startswith(str(self.root)):
                self.hide()
        except Exception:
            pass

    def _forget_win(self, win):
        """Close a popup AND drop its log-viewer registration (toggle-off)."""
        for k, v in list(self._log_wins.items()):
            if v is win:
                self._log_wins.pop(k, None)
        self._close_popup(win)

    def _close_popup(self, win):
        for k, v in list(self._log_wins.items()):
            if v is win:
                self._log_wins.pop(k, None)
        try:
            if win in self._popups:
                self._popups.remove(win)
        except Exception:
            pass
        try:
            if win.winfo_exists():
                win.destroy()
        except Exception:
            pass

    def _close_popups(self):
        for k, v in list(self._log_wins.items()):
            self._log_wins.pop(k, None)
        wins, self._popups = list(self._popups), []
        for w in wins:
            try:
                if w.winfo_exists():
                    w.destroy()
            except Exception:
                pass

    def _track_popup(self, win):
        """One popup class: log viewers AND editors share tracking,
        tray-side positioning, and the dashboard-click dismiss rule."""
        self._popups.append(win)
        win.protocol("WM_DELETE_WINDOW",
                     lambda w=win: self._close_popup(w))

        def _focus_out(_e, w=win):
            def _check():
                try:
                    if not w.winfo_exists():
                        return
                    try:
                        focus = w.focus_displayof()
                    except Exception:
                        focus = None
                    # Focus left for the dashboard -> its FocusIn closes
                    # us; focus left the app -> close ourselves now.
                    if focus is None or not str(focus).startswith(str(self.root)):
                        self._close_popup(w)
                except Exception:
                    pass
            win.after(150, _check)

        win.bind("<FocusOut>", _focus_out)
        return win

    @staticmethod
    def _draggable(win, *handles):
        """Click-drag a borderless popup by its header (no title bar)."""
        pos = {}

        def _down(ev):
            pos["x"], pos["y"] = ev.x_root, ev.y_root
            try:
                pos["gx"], pos["gy"] = win.winfo_x(), win.winfo_y()
            except Exception:
                pos["gx"], pos["gy"] = 0, 0

        def _move(ev):
            try:
                win.geometry(f"+{pos['gx'] + ev.x_root - pos['x']}"
                             f"+{pos['gy'] + ev.y_root - pos['y']}")
            except Exception:
                pass

        for h in handles:
            h.bind("<ButtonPress-1>", _down)
            h.bind("<B1-Motion>", _move)

    def _popup_shell(self, title):
        """Borderless popup: hairline edge + custom header (title + ×).

        All dashboard popups (log viewer, editors, settings) share this --
        no OS title bar anywhere. Returns (win, body): build content in
        body. The × has a hand cursor and closes via _close_popup.
        """
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.configure(bg=TH_CARD_EDGE)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        outer = tk.Frame(win, bg=TH_BG)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        head = tk.Frame(outer, bg=TH_BG)
        head.pack(fill="x", padx=10, pady=(8, 2))
        ttl = tk.Label(head, text=title, font=TH_FONT_B,
                       bg=TH_BG, fg=TH_FG)
        ttl.pack(side="left")
        th_circle_btn(head, "×", lambda: self._close_popup(win),
                      style="ghost").pack(side="right")
        self._draggable(win, head, ttl)
        body = tk.Frame(outer, bg=TH_BG)
        body.pack(fill="both", expand=True, padx=10, pady=(2, 10))
        return win, body

    def _rebuild(self):
        """Destroy + rebuild the popup (theme switch). Restarts _poll.

        Open popups belong to the old root and close with it -- the
        settings window that triggered this included, so call it LAST
        in the save handler.
        """
        was = self.visible
        self._gen = getattr(self, "_gen", 0) + 1  # retire the old _poll
        try:
            self._close_popups()
        except Exception:
            pass
        try:
            if self.root is not None:
                self.root.destroy()
        except Exception:
            pass
        self.root = None
        self.status_var = None
        self.list_frame = None
        self._canvas = None
        self._popups = []
        self._pending = {}
        self._log_wins = {}
        self._rows = {}
        self._group_heads = {}
        self._struct_sig = None
        self._last_sig = None
        self.visible = False
        self.ensure()  # re-applies the palette + schedules a fresh _poll
        if was:
            self.show()

    def say(self, msg):
        try:
            self.status_var.set(msg)
        except Exception:
            pass

    def refresh(self, quiet=False):
        if self.root is None:
            return
        manifest = core.load_manifest()
        run = running_snapshot()
        by_id = {w.get("id"): w for w in manifest.get("works", [])}
        shown = set()

        compact = dashboard_compact()
        # Layout key: state flips update rows IN PLACE (no blink);
        # only a real structural change rebuilds the widget tree.
        struct = (compact,
                  tuple((g.get("id"), g.get("label"),
                         tuple(m for m in g.get("members", [])))
                        for g in manifest.get("groups", [])),
                  tuple(w.get("id") for w in manifest.get("works", [])))

        def _icon_btns(holder, w, v):
            """Uniform circular cluster (all 24px, snug to the glyph).

            Packed right in reverse so the visual order is
            toggle · log · restart · edit · delete.
            The toggle is the only accent; delete is the only red.
            (Ordering lives in the group/task editors, not here.
            Duplicating too: fork from +New / +Group, or Duplicate
            inside the edit dialogs.)
            Returns the toggle canvas (recolored in place on state flip).
            """
            th_circle_btn(holder, "🗑", lambda w=w: self.delete_work(w),
                          style="danger").pack(side="right")
            th_circle_btn(holder, "✎", lambda w=w: self.open_editor(w),
                          ).pack(side="right", padx=(0, 4))
            th_circle_btn(holder, "↻", lambda w=w: self._act_restart(w),
                          ).pack(side="right", padx=(0, 4))
            if w.get("run") == "detached":
                # No window exists in detached mode -- Hide is meaningless;
                # the log viewer is the docker-logs equivalent instead.
                th_circle_btn(holder, "☰",
                              lambda w=w: self.open_log_viewer(w),
                              ).pack(side="right", padx=(0, 4))
            else:
                th_button(holder, "Show" if v["hidden"] else "Hide",
                          lambda w=w: self._act_hide(w),
                          width=6).pack(side="right", padx=(0, 4))
            tog = th_circle_btn(holder, "⏹" if v["running"] else "▶",
                                lambda w=w: self._act_run(w),
                                style=None if v["running"] else "accent")
            tog.pack(side="right", padx=(0, 4))
            return tog

        def _compact_row(main, w, v):
            """One line: icon · title · status · icon cluster. Returns refs."""
            line = tk.Frame(main, bg=TH_CARD)
            line.pack(fill="x", padx=10, pady=6)
            btns = tk.Frame(line, bg=TH_CARD)
            btns.pack(side="right", padx=(8, 0))
            tog = _icon_btns(btns, w, v)
            # the icon carries the state color (green / dim / blue);
            # edge bar + status word back it up, so no dot is needed.
            iconlab = tk.Label(line, text=v["icon"], fg=v["icon_c"],
                               bg=TH_CARD, font=TH_FONT_B)
            iconlab.pack(side="left")
            title = tk.Label(line,
                             text=f" {_short(w.get('label', w.get('id', '')))}",
                             font=TH_FONT_B, bg=TH_CARD, fg=TH_FG,
                             cursor="hand2")
            title.pack(side="left")
            st = tk.Label(line, text=f"  ·  {v['sub']}", font=TH_FONT_S,
                          bg=TH_CARD, fg=v["sub_c"], cursor="hand2")
            st.pack(side="left")
            # the label IS the big target: click toggles Start/Stop.
            for lab in (title, st):
                lab.bind("<Button-1>", lambda _e, w=w: self._act_run(w))
            return {"kind": "compact", "icon": iconlab, "title": title,
                    "sub": st, "tog": tog}

        def _roomy_row(main, w, v):
            """Two-line card. Returns refs for in-place updates."""
            topl = tk.Frame(main, bg=TH_CARD)
            topl.pack(fill="x", padx=10, pady=(8, 0))
            iconlab = tk.Label(topl, text=v["icon"], fg=v["icon_c"],
                               bg=TH_CARD, font=TH_FONT_B)
            iconlab.pack(side="left")
            title = tk.Label(topl, text=f" {w.get('label', w.get('id', ''))}",
                             font=TH_FONT_B, bg=TH_CARD, fg=TH_FG,
                             cursor="hand2")
            title.pack(side="left")
            title.bind("<Button-1>", lambda _e, w=w: self._act_run(w))
            sublab = tk.Label(main, text=v["sub"], font=TH_FONT_S,
                              bg=TH_CARD, fg=v["sub_c"])
            sublab.pack(anchor="w", padx=26)
            btns = tk.Frame(main, bg=TH_CARD)
            btns.pack(fill="x", padx=10, pady=(6, 8))
            left = tk.Frame(btns, bg=TH_CARD)
            left.pack(side="left")
            right = tk.Frame(btns, bg=TH_CARD)
            right.pack(side="right")
            tog_btn = th_button(left, "Stop" if v["running"] else "Start",
                                lambda w=w: self._act_run(w),
                                width=8, accent=not v["running"])
            tog_btn.pack(side="left")
            if w.get("run") == "detached":
                log_btn = th_button(left, "Log",
                                    lambda w=w: self.open_log_viewer(w),
                                    width=8)
                log_btn.pack(side="left", padx=(6, 0))
            else:
                log_btn = th_button(left, "Show" if v["hidden"] else "Hide",
                                    lambda w=w: self._act_hide(w),
                                    width=8)
                log_btn.pack(side="left", padx=(6, 0))
            th_circle_btn(right, "🗑", lambda w=w: self.delete_work(w),
                          style="danger").pack(side="right")
            th_circle_btn(right, "✎", lambda w=w: self.open_editor(w),
                          ).pack(side="right", padx=(0, 4))
            th_circle_btn(right, "↻", lambda w=w: self._act_restart(w),
                          ).pack(side="right", padx=(0, 4))
            return {"kind": "roomy", "icon": iconlab, "title": title,
                    "sub": sublab, "tog_btn": tog_btn, "log_btn": log_btn}

        def work_row(parent, w):
            """Build one row, registering live refs for in-place updates."""
            wid = w.get("id", "")
            shown.add(wid)
            v = _row_view(w, run, self._pending)
            row = tk.Frame(parent, bg=TH_CARD, padx=0, pady=0,
                           highlightbackground=TH_CARD_EDGE,
                           highlightthickness=1)
            row.pack(fill="x", pady=4, padx=2)
            # icon carries the running color; the edge bar stays too.
            edge = tk.Frame(row,
                            bg=TH_GREEN if v["running"] else TH_CARD_EDGE,
                            width=3)
            edge.pack(side="left", fill="y")
            main = tk.Frame(row, bg=TH_CARD)
            main.pack(side="left", fill="both", expand=True)
            if compact:
                refs = _compact_row(main, w, v)
            else:
                refs = _roomy_row(main, w, v)
            refs.update(frame=row, edge=edge)
            self._rows[wid] = refs

        if struct != getattr(self, "_struct_sig", None) or not getattr(self, "_rows", None):
            for ch in self.list_frame.winfo_children():
                ch.destroy()
            self._rows = {}
            self._group_heads = {}
            for g in manifest.get("groups", []):
                members = [by_id[m] for m in g.get("members", []) if m in by_id]
                if not members:
                    continue
                on = sum(1 for m in members if m.get("id") in run)
                gf = tk.LabelFrame(self.list_frame, text=f"  {g.get('label', g.get('id'))}  ·  {on}/{len(members)} running  ",
                                   font=TH_FONT_SECTION,
                                   bg=TH_BG, fg=TH_DIM, relief="flat", bd=0,
                                   labelanchor="nw")
                gf.pack(fill="x", pady=(10, 2))
                self._group_heads[g.get("id")] = gf
                for m in members:
                    work_row(gf, m)
                brow = tk.Frame(gf, bg=TH_BG)
                brow.pack(fill="x", padx=6, pady=(0, 8))
                th_button(brow, text="▶ Start all",
                          command=lambda ms=members: self._act_all(ms, True),
                          width=10, accent=True).pack(side="left")
                th_circle_btn(brow, "🗑", lambda g=g: self.delete_group(g),
                              style="danger").pack(side="right")
                th_circle_btn(brow, "✎", lambda g=g: self.open_group_editor(g),
                              ).pack(side="right", padx=(0, 4))
                th_button(brow, text="⏹ Stop all",
                          command=lambda ms=members: self._act_all(ms, False),
                          width=10, style="ghost").pack(side="right", padx=(0, 4))
            for w in manifest.get("works", []):
                if w.get("id") not in shown:
                    work_row(self.list_frame, w)
            self._struct_sig = struct
        else:
            # Same layout: touch text/colors only. No destroy, no blink.
            for w in manifest.get("works", []):
                refs = self._rows.get(w.get("id"))
                if refs is not None:
                    self._update_row(refs, w, run)
            for g in manifest.get("groups", []):
                head = self._group_heads.get(g.get("id"))
                if head is None:
                    continue
                try:
                    members = [by_id[m] for m in g.get("members", [])
                               if m in by_id]
                    on = sum(1 for m in members if m.get("id") in run)
                    head.config(text=f"  {g.get('label', g.get('id'))}  ·  {on}/{len(members)} running  ")
                except Exception:
                    pass
        if not quiet:
            self.say(f"{len(run)} running")
        # Scroll health (backlog #4): explicit region after every rebuild
        # (never depend on a <Configure> arriving), and clamp a stale
        # view back into range when the content shrank.
        try:
            cv = self._canvas
            if cv is not None:
                self.list_frame.update_idletasks()
                box = cv.bbox("all")
                if box:
                    cv.configure(scrollregion=box)
                    h = cv.winfo_height()
                    if self.visible and h > 1:
                        span = box[3] - box[1] - h
                        if span <= 0:
                            cv.yview_moveto(0)
                        else:
                            first, _last = cv.yview()
                            if first * (box[3] - box[1]) > span:
                                cv.yview_moveto(span / (box[3] - box[1]))
        except Exception:
            pass

    def _update_row(self, refs, w, run):
        """In-place row update: text + colors only, never destroy.

        Same tick, no widget churn -- this is what killed the blink.
        Structural changes (add/remove/move/label) still take the full
        rebuild path via the struct key.
        """
        try:
            v = _row_view(w, run, self._pending)
        except Exception:
            return
        try:
            refs["edge"].config(bg=TH_GREEN if v["running"] else TH_CARD_EDGE)
            refs["icon"].config(text=v["icon"], fg=v["icon_c"])
            if refs.get("kind") == "compact":
                refs["title"].config(
                    text=f" {_short(w.get('label', w.get('id', '')))}")
                refs["sub"].config(text=f"  ·  {v['sub']}", fg=v["sub_c"])
                tog = refs.get("tog")
                if tog is not None:
                    if v["running"]:
                        tog.recolor(TH_BTN, TH_BTN_HI, TH_FG)
                    else:
                        tog.recolor(TH_ACCENT, TH_ACCENT_HI, "white")
                    try:
                        tog.itemconfig(tog._txt,
                                       text="⏹" if v["running"] else "▶")
                    except Exception:
                        pass
            else:
                refs["title"].config(
                    text=f" {w.get('label', w.get('id', ''))}")
                refs["sub"].config(text=v["sub"], fg=v["sub_c"])
                tb = refs.get("tog_btn")
                if tb is not None:
                    if v["running"]:
                        tb.config(text="Stop", bg=TH_BTN, fg=TH_FG,
                                  activebackground=TH_BTN_HI)
                    else:
                        tb.config(text="Start", bg=TH_ACCENT, fg="white",
                                  activebackground=TH_ACCENT_HI)
                lb = refs.get("log_btn")
                if lb is not None:
                    if w.get("run") == "detached":
                        lb.config(text="Log")
                    else:
                        lb.config(text="Show" if v["hidden"] else "Hide")
        except Exception:
            pass

    def _sweep_pending(self):
        """Clear transitional marks the live snapshot confirms (or timeout).

        Called every _poll tick: blue starting… survives until the work
        is ACTUALLY running, so a stale cache can never flash white in
        between. Fire-and-forget marks (hide/show) never reach here.
        """
        pending = getattr(self, "_pending", None)
        if not pending:
            return
        try:
            run = running_snapshot()
            now = time.monotonic()
        except Exception:
            return
        cleared = False
        for wid, e in list(pending.items()):
            e = e or {}
            ex = e.get("expect")
            if ex is None or (wid in run) == ex or now >= e.get("until", 0):
                pending.pop(wid, None)
                cleared = True
        if cleared:
            try:
                self.refresh(quiet=True)
            except Exception:
                pass

    # -- row actions (ALL async: scans/kills block for seconds and must
    # never freeze the tk mainloop -- that freeze was the real bug) -------
    def _act_async(self, fn, working_msg, pending=None):
        """Run fn on a worker; `pending` = {wid: (state, expect)}.

        The transitional mark (starting…/stopping…) lands on the same
        tick as the click, and it guards double-clicks: a guarded
        handler refuses to re-fire while its work is pending, so a fast
        double Start can never spawn the work twice. `expect` is the
        running-state that clears the mark (None = clear on finish).
        """
        if pending:
            now = time.monotonic()
            for k, v in pending.items():
                st, ex = v
                self._pending[k] = {"state": st, "expect": ex,
                                    "until": now + 20}
        self.say(working_msg)
        self.refresh(quiet=True)
        th = threading.Thread(target=self._run_async,
                              args=(fn, list(pending or {})), daemon=True)
        th.start()

    def _run_async(self, fn, pending_wids):
        try:
            msg = fn()
        except Exception as e:
            msg = f"failed: {e}"
        # Start/stop marks stay until the live snapshot CONFIRMS them
        # (swept by _poll); only fire-and-forget marks clear here.
        for k in pending_wids:
            e = self._pending.get(k)
            if e is not None and e.get("expect") is None:
                self._pending.pop(k, None)

        def _done(m=msg):
            self.say(m)
            try:
                _rescan.set()  # fresh scan NOW so confirm lands fast
            except Exception:
                pass
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

    def open_log_viewer(self, w):
        """Live color tail for a detached work's log (docker-logs equivalent).

        Incremental follow (1s poll, new bytes only -- no full redraw, no
        flicker); a shrink means a fresh launch truncated the log, so the
        view reloads. ANSI colors render via wc_core.ansi_runs tags.
        A work with its own `"log"` key tails that file instead.
        Open = click, close = click again (toggle per work, never
        duplicates): a second click on ☰ closes that work's viewer
        instead of spawning another one.
        """
        wid = w.get("id", "")
        label = w.get("label", wid or "?")
        old = self._log_wins.get(wid)
        if old is not None:
            try:
                alive = bool(old.winfo_exists())
            except Exception:
                alive = False
            self._forget_win(old)
            if alive:
                self.say(f"closed log: {label}")
                return
        try:
            path = core.work_display_log_path(w)
        except Exception as e:
            self.say(f"log path failed: {e}")
            return
        win, body = self._popup_shell(f"log: {label}")
        self._place_near_tray(win, 760, 460)
        self._track_popup(win)
        self._log_wins[wid] = win
        txt = tk.Text(body, wrap="none", bg="#1e1e1e", fg="#d4d4d4",
                      insertbackground="#d4d4d4", selectbackground="#264f78")
        txt.pack(fill="both", expand=True)
        for _name, _color in LOG_FG.items():
            txt.tag_config(f"fg-{_name}", foreground=_color)
        txt.tag_config("link", foreground="#4ea6ff", underline=True)
        txt.tag_bind("link", "<Button-1>", _open_link)
        txt.tag_bind("link", "<Enter>",
                     lambda e: e.widget.config(cursor="hand2"))
        txt.tag_bind("link", "<Leave>", lambda e: e.widget.config(cursor=""))
        txt.config(state="disabled")
        bar = tk.Frame(body, bg=TH_BG)
        bar.pack(fill="x", pady=(6, 0))
        state = {"pos": 0}

        def _insert_runs(chunk):
            txt.config(state="normal")
            start = txt.index("end-1c")
            for seg, fg in core.ansi_runs(chunk):
                txt.insert("end", seg, (f"fg-{fg}",) if fg else ())
            _tag_links(txt, start, txt.index("end-1c"))
            if int(txt.index("end-1c").split(".")[0]) > 2000:
                txt.delete("1.0", "1000.0")
            txt.see("end")
            txt.config(state="disabled")

        def _full_load():
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    tail = f.readlines()[-150:]
                    state["pos"] = f.tell()
            except OSError:
                tail = ["(no log yet -- Start the work first)\n"]
                state["pos"] = 0
            txt.config(state="normal")
            txt.delete("1.0", "end")
            txt.config(state="disabled")
            _insert_runs("".join(tail))

        def _follow():
            try:
                if not win.winfo_exists():
                    return
                try:
                    size = os.path.getsize(path)
                except OSError:
                    win.after(1000, _follow)
                    return
                if size < state["pos"]:
                    _full_load()  # fresh launch truncated the log
                elif size > state["pos"]:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        f.seek(state["pos"])
                        chunk = f.read()
                        state["pos"] = f.tell()
                    if chunk:
                        _insert_runs(chunk)
                win.after(1000, _follow)
            except Exception:
                pass

        th_button(bar, text="Reload",
                  command=lambda: win.after(0, _full_load),
                  width=8).pack(side="left")
        tk.Label(bar, text=path, bg=TH_BG, fg=TH_DIM,
                 font=TH_FONT_S).pack(side="left", padx=8)
        _full_load()
        win.after(1000, _follow)
        return win

    def _act_run(self, w):
        wid = w.get("id", "")
        label = w.get("label", wid)
        if wid in self._pending:
            self.say(f"already {self._pending[wid].get('state', 'working')} '{label}'…")
            return
        state = "stopping" if wid in running_snapshot() else "starting"
        self._act_async(lambda: toggle_start_stop(w), f"{state} '{label}'…",
                        pending={wid: (state, state == "starting")})

    def _act_hide(self, w):
        wid = w.get("id", "")
        label = w.get("label", wid)
        if wid in self._pending:
            self.say(f"already {self._pending[wid].get('state', 'working')} '{label}'…")
            return
        try:
            hiding = not core.is_work_hidden(w)
        except Exception:
            hiding = True
        state = "hiding" if hiding else "showing"
        self._act_async(lambda: self._do_hide(w), f"{state} '{label}'…",
                        pending={wid: (state, None)})

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
        return "restarted — fresh window" if rec else "start failed (nothing runnable?)"

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
        wid = w.get("id", "")
        label = w.get("label", wid)
        if wid in self._pending:
            self.say(f"already {self._pending[wid].get('state', 'working')} '{label}'…")
            return
        self._act_async(lambda: self._do_restart(w),
                        f"restarting '{label}'…",
                        pending={wid: ("restarting", True)})

    def _act_all(self, members, start):
        fresh = [m.get("id", "") for m in members
                 if m.get("id", "") not in self._pending]
        if not fresh:
            self.say("already working…")
            return
        state = "starting" if start else "stopping"
        self._act_async(lambda: self._do_all(members, start),
                        f"{state} {len(fresh)} work(s)…",
                        pending={k: (state, bool(start)) for k in fresh})

    def _move_work(self, w, direction):
        """Custom sort: swap with the adjacent visible sibling, persist.

        direction -1 = up, +1 = down, within the work's own list only
        (its group, or the ungrouped tail). Manifest order is the
        display order, so the move survives restarts and editor saves.
        Tiny local JSON write — safe on the tk thread, no scan.
        """
        wid = w.get("id", "")
        label = w.get("label", wid)
        try:
            man = core.load_manifest()
        except Exception:
            return
        groups = man.get("groups", [])
        gid = next((g.get("id") for g in groups
                    if wid in g.get("members", [])), None)
        if gid is not None:
            g = next(g for g in groups if g.get("id") == gid)
            new = _swap_adjacent(g.get("members", []), wid, direction)
            if new == list(g.get("members", [])):
                self.say("already at the "
                         + ("top" if direction < 0 else "bottom"))
                return
            g["members"] = new
        else:
            ids = [x.get("id") for x in man.get("works", [])
                   if not any(x.get("id") in g.get("members", [])
                              for g in groups)]
            new = _swap_adjacent(ids, wid, direction)
            if new == ids:
                self.say("already at the "
                         + ("top" if direction < 0 else "bottom"))
                return
            pos = {v: i for i, v in enumerate(new)}
            man["works"] = sorted(
                man.get("works", []),
                key=lambda x: pos.get(x.get("id"), len(pos)))
        try:
            core.save_manifest(man)
        except Exception as e:
            self.say(f"move failed: {e}")
            return
        self.say(f"moved '{label}' "
                 + ("up" if direction < 0 else "down"))
        self.refresh(quiet=True)

    def _duplicate_work(self, w):
        """Clone a work: same config, new id, placed right after the original
        (same group slot too). Tiny local JSON write — tk thread is fine."""
        wid = w.get("id", "")
        try:
            man = core.load_manifest()
        except Exception:
            return
        src = next((x for x in man.get("works", []) if x.get("id") == wid),
                   None)
        if src is None:
            self.say("already gone — refresh and retry")
            self.refresh(quiet=True)
            return
        base = (re.sub(r"[^a-z0-9]+", "-",
                       str(src.get("label", wid) or wid).lower())
                .strip("-")[:20] or "work")
        ids = {x.get("id") for x in man.get("works", [])}
        nid, n = base, 2
        while nid in ids:
            nid = f"{base}-{n}"
            n += 1
        entry = dict(src)
        entry["id"] = nid
        entry["label"] = (src.get("label", wid) or wid) + " copy"
        works = man.get("works", [])
        at = next((i for i, x in enumerate(works) if x.get("id") == wid),
                  len(works) - 1)
        works.insert(at + 1, entry)
        man["works"] = works
        for g in man.get("groups", []):
            if wid in g.get("members", []):
                g["members"].insert(g["members"].index(wid) + 1, nid)
        try:
            core.save_manifest(man)
        except Exception as e:
            self.say(f"duplicate failed: {e}")
            return
        self.say(f"duplicated '{entry['label']}'")
        self.refresh(quiet=True)

    def _duplicate_group(self, group):
        """Clone a group: same members, fresh id+label. Tk-thread safe."""
        gid = (group or {}).get("id", "")
        try:
            man = core.load_manifest()
        except Exception:
            return
        src = next((g for g in man.get("groups", [])
                    if g.get("id") == gid), None)
        if src is None:
            self.say("group gone — refresh and retry")
            self.refresh(quiet=True)
            return
        have = {x.get("id") for x in man.get("works", [])}
        members = [m for m in src.get("members", []) if m in have]
        label = (src.get("label", gid) or gid) + " copy"
        nid = core.slug_group_id(label, man)
        man.setdefault("groups", []).append(
            {"id": nid, "label": label, "members": members})
        try:
            core.save_manifest(man)
        except Exception as e:
            self.say(f"duplicate failed: {e}")
            return
        self.say(f"duplicated group '{label}'")
        self.refresh(quiet=True)

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
            core.save_manifest(manifest)
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

    # -- group editor (backlog #3) ----------------------------------------
    def open_group_editor(self, group=None):
        manifest = core.load_manifest()
        win, body = self._popup_shell("Rename Group" if group else "New Group")
        namevar = tk.StringVar(value=(group or {}).get("label", ""))
        tk.Label(body, text="Label", bg=TH_BG, fg=TH_FG).grid(
            row=0, column=0, sticky="w", padx=8, pady=6)
        tk.Entry(body, textvariable=namevar, width=40, relief="flat", bd=4,
                 bg=TH_FIELD, fg=TH_INPUT_FG,
                 insertbackground=TH_INPUT_FG).grid(
            row=0, column=1, padx=8, pady=6)
        tk.Label(body, text="Members", bg=TH_BG, fg=TH_FG).grid(
            row=1, column=0, sticky="nw", padx=8)
        box = tk.Frame(body, bg=TH_BG)
        box.grid(row=1, column=1, sticky="w", padx=8, pady=3)
        current = set((group or {}).get("members", []))
        checks = {}
        for w in manifest.get("works", []):
            wid = w.get("id", "")
            var = tk.BooleanVar(value=wid in current)
            checks[wid] = var
            tk.Checkbutton(box, text=w.get("label", wid), variable=var,
                           bg=TH_BG, fg=TH_FG, selectcolor=TH_FIELD,
                           activebackground=TH_BG, activeforeground=TH_FG,
                           anchor="w").pack(fill="x")
        # Order lives here (not on every row): members in order, ▲▼ to
        # move, membership ticks stay in sync both ways.
        by_id = {w.get("id"): w for w in manifest.get("works", [])}
        order = [m for m in (group or {}).get("members", []) if m in by_id]
        tk.Label(body, text="Order (top = first):", bg=TH_BG, fg=TH_FG).grid(
            row=2, column=0, sticky="nw", padx=8, pady=3)
        obox = tk.Frame(body, bg=TH_BG)
        obox.grid(row=2, column=1, sticky="w", padx=8, pady=3)
        lb = tk.Listbox(obox, width=40, height=min(6, max(3, len(order) + 1)),
                        relief="flat", bd=4, bg=TH_FIELD, fg=TH_FG,
                        selectbackground=TH_ACCENT,
                        selectforeground="white",
                        highlightthickness=0, activestyle="none")
        lb.pack(side="left")
        abox = tk.Frame(obox, bg=TH_BG)
        abox.pack(side="left", padx=(6, 0))
        th_circle_btn(abox, "▲", lambda: _ord_move(-1),
                      font_size=9).pack(pady=2)
        th_circle_btn(abox, "▼", lambda: _ord_move(+1),
                      font_size=9).pack(pady=2)

        def _lb_sync(sel=None):
            lb.delete(0, "end")
            for mid in order:
                lb.insert("end", by_id.get(mid, {}).get("label", mid))
            if sel is not None and order:
                lb.selection_set(max(0, min(sel, len(order) - 1)))

        def _ord_move(direction):
            try:
                sel = lb.curselection()[0]
            except IndexError:
                return
            new = _swap_adjacent(order, order[sel], direction)
            if new != order:
                order[:] = new
                _lb_sync(sel + direction)

        def _on_toggle(wid, *a):
            if checks[wid].get():
                if wid not in order:
                    order.append(wid)
            elif wid in order:
                order.remove(wid)
            _lb_sync()

        for _wid, _var in checks.items():
            _var.trace_add("write", lambda *a, wid=_wid: _on_toggle(wid))
        _lb_sync()
        # Fork: +Group starts from an existing group's config.
        if group is None:
            tk.Label(body, text="Fork from:", bg=TH_BG, fg=TH_FG).grid(
                row=3, column=0, sticky="w", padx=8, pady=3)
            gforkvar = tk.StringVar(value="(blank — fresh)")
            gforkopts = ["(blank — fresh)"] + [
                f"{g2.get('label', g2.get('id'))} [{g2.get('id')}]"
                for g2 in manifest.get("groups", [])]
            om_gfork = tk.OptionMenu(body, gforkvar, *gforkopts)
            om_gfork.configure(bg=TH_FIELD, fg=TH_INPUT_FG, relief="flat",
                               bd=0, activebackground=TH_BTN_HI,
                               highlightthickness=0)
            om_gfork["menu"].configure(bg=TH_FIELD, fg=TH_INPUT_FG)
            om_gfork.grid(row=3, column=1, sticky="w", padx=8, pady=3)

            def _on_gfork(*a):
                sel = gforkvar.get()
                if sel.startswith("(blank"):
                    return
                sid = sel.split("[")[-1].rstrip("]")
                src = next((g for g in manifest.get("groups", [])
                            if g.get("id") == sid), None)
                if src is None:
                    return
                namevar.set((src.get("label", "") or "") + " copy")
                for wid2, var2 in checks.items():
                    var2.set(wid2 in src.get("members", []))
                # membership traces rebuild `order` via _on_toggle.

            gforkvar.trace_add("write", _on_gfork)

        def save():
            label = namevar.get().strip()
            if not label:
                messagebox.showwarning("Missing", "Group label is required.")
                return
            man = core.load_manifest()
            gid = (group or {}).get("id") or core.slug_group_id(label, man)
            members = [mid for mid in order
                       if mid in [x.get("id") for x in man.get("works", [])]]
            groups = man.get("groups", [])
            hit = [g for g in groups if g.get("id") == gid]
            if hit:
                hit[0]["label"] = label
                hit[0]["members"] = members
            else:
                groups.append({"id": gid, "label": label, "members": members})
                man["groups"] = groups
            try:
                core.save_manifest(man)
            except Exception as e:
                messagebox.showerror("Save failed", str(e))
                return
            win.destroy()
            self.say(f"saved group '{label}'")
            self.refresh(quiet=True)

        if (group or {}).get("id"):
            th_button(body, text="Duplicate",
                      command=lambda: self._duplicate_group(group),
                      width=11).grid(row=4, column=0, sticky="w",
                                     padx=8, pady=10)
        th_button(body, text="Save", command=save, width=14,
                  accent=True).grid(row=4, column=1, pady=10)
        try:
            win.update_idletasks()
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            self._place_near_tray(win, min(win.winfo_reqwidth(), sw - 32),
                                  min(win.winfo_reqheight(), sh - 120))
        except Exception:
            pass
        self._track_popup(win)
        return win

    def delete_group(self, group):
        if not messagebox.askyesno("Delete group",
                                    f"Remove group '{group.get('label')}'? (its works stay standalone)"):
            return
        try:
            man = core.load_manifest()
            man["groups"] = [g for g in man.get("groups", [])
                             if g.get("id") != group.get("id")]
            core.save_manifest(man)
            self.say(f"deleted group '{group.get('label')}'")
            self.refresh(quiet=True)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e))

    # -- settings (suite hotkey) ------------------------------------------
    def open_settings(self):
        manifest = core.load_manifest()
        st0 = core.get_settings(manifest)
        current = st0.get("hotkey", core.DEFAULT_HOTKEY)
        win, body = self._popup_shell("Settings")
        tk.Label(body, text="Global hotkey (modifiers + key):", bg=TH_BG,
                 fg=TH_FG).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ent = tk.Entry(body, width=24, relief="flat", bd=4,
                       bg=TH_FIELD, fg=TH_INPUT_FG,
                       insertbackground=TH_INPUT_FG)
        ent.grid(row=0, column=1, padx=8, pady=6)
        ent.insert(0, current)
        tk.Label(body, text="Theme:", bg=TH_BG,
                 fg=TH_FG).grid(row=1, column=0, sticky="w", padx=8, pady=3)
        themevar = tk.StringVar(value=st0.get("theme", "dark"))
        om_theme = tk.OptionMenu(body, themevar, "dark", "light")
        om_theme.configure(bg=TH_FIELD, fg=TH_INPUT_FG, relief="flat", bd=0,
                           activebackground=TH_BTN_HI, highlightthickness=0)
        om_theme["menu"].configure(bg=TH_FIELD, fg=TH_INPUT_FG)
        om_theme.grid(row=1, column=1, sticky="w", padx=8, pady=3)
        compactvar = tk.BooleanVar(value=bool(st0.get("compact", True)))
        tk.Checkbutton(body, text="compact rows (one line per work)",
                       variable=compactvar, bg=TH_BG, fg=TH_FG,
                       selectcolor=TH_FIELD, activebackground=TH_BG,
                       activeforeground=TH_FG).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=8, pady=3)

        def save():
            hk = core.canonical_hotkey(ent.get().strip())
            if not hk:
                messagebox.showwarning("Bad hotkey",
                                       "Use modifiers + key, e.g. alt+w "
                                       "(keys: 0-9, a-z, f1-f24).")
                return
            man = core.load_manifest()
            st = core.get_settings(man)
            old_theme = st.get("theme", "dark")
            st["hotkey"] = hk
            st["theme"] = themevar.get()
            st["compact"] = bool(compactvar.get())
            man["settings"] = st
            try:
                core.save_manifest(man)
            except Exception as e:
                messagebox.showerror("Save failed", str(e))
                return
            try:
                if tray_host is not None and getattr(tray_host, "hwnd", None):
                    unregister_hotkey(tray_host.hwnd, 1)
            except Exception:
                pass
            self._hotkey_on = False
            self._ensure_hotkey()
            if getattr(self, "_hotkey_on", False):
                hk_msg = f"hotkey {hk} on"
            else:
                hk_msg = f"hotkey {hk} saved -- taken, grabs when free"
                log(f"hotkey {hk} taken at settings save")
            if st["theme"] != old_theme:
                self._rebuild()  # LAST: closes this window with the old root
                self.say(f"{hk_msg} · theme {st['theme']}")
            else:
                win.destroy()
                self.say(hk_msg)
                self.refresh(quiet=True)

        th_button(body, text="Save", command=save, width=14,
                  accent=True).grid(row=3, column=1, pady=10)
        try:
            win.update_idletasks()
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            self._place_near_tray(win, min(win.winfo_reqwidth(), sw - 32),
                                  min(win.winfo_reqheight(), sh - 120))
        except Exception:
            pass
        self._track_popup(win)
        return win

    # -- config editor ----------------------------------------------------
    def open_editor(self, work=None):
        manifest = core.load_manifest()
        win, body = self._popup_shell("Edit Task" if work else "New Task")
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
            tk.Label(body, text=cap, bg=TH_BG, fg=TH_FG).grid(
                row=i + 1, column=0, sticky="w", padx=8, pady=3)
            tk.Entry(body, textvariable=vals[key], width=44, relief="flat", bd=4,
                     bg=TH_FIELD, fg=TH_INPUT_FG,
                     insertbackground=TH_INPUT_FG).grid(
                         row=i + 1, column=1, padx=8, pady=3)
        th_button(body, text="Browse…",
                  command=lambda: vals["bat"].set(
                      filedialog.askopenfilename(
                          initialdir=str(HERE),
                          filetypes=[("Launchers", "*.bat *.lnk *.exe"), ("All", "*.*")]) or vals["bat"].get()),
                  width=9).grid(row=2, column=2, padx=8)
        tk.Label(body, text="Icon", bg=TH_BG, fg=TH_FG).grid(
            row=4, column=0, sticky="w", padx=8, pady=3)
        om_icon = tk.OptionMenu(body, vals["icon"], *ICON_CHOICES)
        om_icon.configure(bg=TH_FIELD, fg=TH_INPUT_FG, relief="flat", bd=0,
                          activebackground=TH_BTN_HI, highlightthickness=0)
        om_icon["menu"].configure(bg=TH_FIELD, fg=TH_INPUT_FG)
        om_icon.grid(row=4, column=1, sticky="w", padx=8)
        tk.Label(body, text="Group", bg=TH_BG, fg=TH_FG).grid(
            row=5, column=0, sticky="w", padx=8, pady=3)
        groups = ["(none — standalone)"] + [f"{g.get('label')} [{g.get('id')}]" for g in manifest.get("groups", [])]
        gvar = tk.StringVar(value="(none — standalone)")
        if vals["group"].get():
            for txt in groups:
                if vals["group"].get() in txt:
                    gvar = tk.StringVar(value=txt)
        om_grp = tk.OptionMenu(body, gvar, *groups)
        om_grp.configure(bg=TH_FIELD, fg=TH_INPUT_FG, relief="flat", bd=0,
                         activebackground=TH_BTN_HI, highlightthickness=0)
        om_grp["menu"].configure(bg=TH_FIELD, fg=TH_INPUT_FG)
        om_grp.grid(row=5, column=1, sticky="w", padx=8)
        tk.Checkbutton(body, text="detect running state", variable=vals["detect"],
                       bg=TH_BG, fg=TH_FG, selectcolor=TH_FIELD,
                       activebackground=TH_BG, activeforeground=TH_FG).grid(
            row=6, column=1, sticky="w", padx=8)
        tk.Label(body, text="Commands: one per line (app: prefix = App step, else Terminal). "
                           "Non-empty = inline mode, overrides .bat at launch.",
                 bg=TH_BG, fg=TH_DIM, font=TH_FONT_S).grid(
            row=7, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 0))
        txt_steps = tk.Text(body, width=64, height=5, relief="flat", bd=4,
                            bg=TH_FIELD, fg=TH_INPUT_FG,
                            insertbackground=TH_INPUT_FG,
                            font=("Consolas", 9))
        txt_steps.grid(row=8, column=0, columnspan=3, padx=8, pady=3, sticky="we")
        if (work or {}).get("steps"):
            txt_steps.insert("1.0", core.steps_to_text(work.get("steps")))
        tk.Label(body, text="Vars: NAME=value per line (%NAME% usable in commands).",
                 bg=TH_BG, fg=TH_DIM, font=TH_FONT_S).grid(
            row=9, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 0))
        txt_vars = tk.Text(body, width=64, height=3, relief="flat", bd=4,
                           bg=TH_FIELD, fg=TH_INPUT_FG,
                           insertbackground=TH_INPUT_FG,
                           font=("Consolas", 9))
        txt_vars.grid(row=10, column=0, columnspan=3, padx=8, pady=3, sticky="we")
        if (work or {}).get("vars"):
            txt_vars.insert("1.0", core.vars_to_text(work.get("vars")))

        def save():
            label = vals["label"].get().strip()
            bat = vals["bat"].get().strip()
            match = vals["match"].get().strip()
            steps_raw = txt_steps.get("1.0", "end").strip()
            vars_raw = txt_vars.get("1.0", "end").strip()
            steps = core.parse_steps_text(steps_raw)
            if not label or (not bat and not steps):
                messagebox.showwarning("Missing", "Label + (start file or commands) are required.")
                return
            if steps and not match and not bat:
                messagebox.showwarning("Missing", "Match token is required for file-less steps works (detection needs it).")
                return
            if bat and not os.path.exists(bat):
                if not messagebox.askyesno("File not found",
                                           f"'{bat}' does not exist.\nSave anyway?"):
                    return
            man = core.load_manifest()
            wid = (work or {}).get("id") or ("w-" + "".join(
                c.lower() if c.isalnum() else "-" for c in label).strip("-")[:24])
            entry = dict(work or {})
            entry.update({"id": wid, "label": label,
                          "icon": vals["icon"].get(),
                          "detect": bool(vals["detect"].get())})
            if steps:
                # Inline mode: steps win at launch; a stored `bat` stays
                # only as fallback (Hamster-Clint keeps both).
                entry["steps"] = steps
                if vars_raw.strip():
                    entry["vars"] = core.parse_vars_text(vars_raw)
                else:
                    entry.pop("vars", None)
                if bat:
                    entry["bat"] = bat
                else:
                    entry.pop("bat", None)
                if match:
                    entry["match"] = match
                elif bat:
                    entry["match"] = os.path.basename(bat)
            else:
                entry["bat"] = bat
                entry["match"] = match or os.path.basename(bat)
                entry.pop("steps", None)
                entry.pop("vars", None)
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
            # No sorting here: manifest order IS the display order
            # (custom sort survives every save).
            try:
                core.save_manifest(man)
            except Exception as e:
                messagebox.showerror("Save failed", str(e))
                return
            win.destroy()
            self.say(f"saved '{label}'")
            self.refresh(quiet=True)

        # Fork: +New starts from an existing work's config (pure prefill;
        # the " copy" label mints a fresh id on save, never overwrites).
        if work is None:
            tk.Label(body, text="Fork from:", bg=TH_BG, fg=TH_FG).grid(
                row=0, column=0, sticky="w", padx=8, pady=3)
            forkvar = tk.StringVar(value="(blank — fresh)")
            forkopts = ["(blank — fresh)"] + [
                f"{w2.get('label', w2.get('id'))} [{w2.get('id')}]"
                for w2 in manifest.get("works", [])]
            om_fork = tk.OptionMenu(body, forkvar, *forkopts)
            om_fork.configure(bg=TH_FIELD, fg=TH_INPUT_FG, relief="flat", bd=0,
                              activebackground=TH_BTN_HI, highlightthickness=0)
            om_fork["menu"].configure(bg=TH_FIELD, fg=TH_INPUT_FG)
            om_fork.grid(row=0, column=1, sticky="w", padx=8, pady=3)

            def _on_fork(*a):
                sel = forkvar.get()
                if sel.startswith("(blank"):
                    return
                sid = sel.split("[")[-1].rstrip("]")
                src = next((x for x in manifest.get("works", [])
                            if x.get("id") == sid), None)
                if src is None:
                    return
                f = _work_to_form(src, manifest)
                vals["label"].set(f["label"])
                vals["bat"].set(f["bat"])
                vals["match"].set(f["match"])
                vals["icon"].set(f["icon"])
                vals["detect"].set(f["detect"])
                gvar.set(f["group"])
                txt_steps.delete("1.0", "end")
                txt_steps.insert("1.0", f["steps"])
                txt_vars.delete("1.0", "end")
                txt_vars.insert("1.0", f["vars"])

            forkvar.trace_add("write", _on_fork)
        # Ordering for this work (standalone or grouped): moves within
        # its own visible list, dashboard refreshes underneath.
        if (work or {}).get("id"):
            mv = tk.Frame(body, bg=TH_BG)
            mv.grid(row=11, column=0, sticky="w", padx=8, pady=10)
            th_button(mv, text="↑ Up",
                      command=lambda: self._move_work(work, -1),
                      width=7).grid(row=0, column=0, padx=(0, 4))
            th_button(mv, text="↓ Down",
                      command=lambda: self._move_work(work, +1),
                      width=7).grid(row=0, column=1)
            th_button(mv, text="Duplicate",
                      command=lambda: self._duplicate_work(work),
                      width=9).grid(row=0, column=2, padx=(4, 0))
        th_button(body, text="Save", command=save, width=14,
                  accent=True).grid(row=11, column=1, pady=10)
        try:
            win.update_idletasks()
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            self._place_near_tray(win, min(win.winfo_reqwidth(), sw - 32),
                                  min(win.winfo_reqheight(), sh - 120))
        except Exception:
            pass
        self._track_popup(win)
        return win


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
        dash._ensure_hotkey()
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
