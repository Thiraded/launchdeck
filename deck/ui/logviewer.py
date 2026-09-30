"""Live log viewer window (docker-logs style tail)."""
import os
import tkinter as tk

import launchdeck_core as core
from deck.ui import dpi, theme
from deck.ui.widgets import _open_link, _tag_links, th_button


class LogViewerMixin:
    """Dashboard mixin (see deck/ui/app.py)."""

    def open_log_viewer(self, w):
        """Live color tail for a detached work's log (docker-logs equivalent).

        Incremental follow (1s poll, new bytes only -- no full redraw, no
        flicker); a shrink means a fresh launch truncated the log, so the
        view reloads. ANSI colors render via launchdeck_core.ansi_runs tags.
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
        self._place_near_tray(win, dpi.px(760), dpi.px(460))
        self._track_popup(win)
        self._log_wins[wid] = win
        txt = tk.Text(body, wrap="none", bg="#1e1e1e", fg="#d4d4d4",
                      insertbackground="#d4d4d4", selectbackground="#264f78")
        txt.pack(fill="both", expand=True)
        for _name, _color in theme.LOG_FG.items():
            txt.tag_config(f"fg-{_name}", foreground=_color)
        txt.tag_config("link", foreground="#4ea6ff", underline=True)
        txt.tag_bind("link", "<Button-1>", _open_link)
        txt.tag_bind("link", "<Enter>",
                     lambda e: e.widget.config(cursor="hand2"))
        txt.tag_bind("link", "<Leave>", lambda e: e.widget.config(cursor=""))
        txt.config(state="disabled")
        bar = tk.Frame(body, bg=theme.TH_BG)
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
        tk.Label(bar, text=path, bg=theme.TH_BG, fg=theme.TH_DIM,
                 font=theme.TH_FONT_S).pack(side="left", padx=8)
        _full_load()
        win.after(1000, _follow)
        return win
