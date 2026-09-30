"""Dashboard: window lifecycle, popups, action pump, async runner.
Feature areas are mixins (worklist / logviewer / editors / actions)."""
import os
import queue
import threading
import time
import tkinter as tk

from launchdeck_tray import register_hotkey
from launchdeck_tray import unregister_hotkey
import launchdeck_core as core
from deck.ui import dpi, icons, state
from deck.ui import theme
from deck.ui.actions import ActionsMixin
from deck.ui.editors import EditorsMixin
from deck.ui.logviewer import LogViewerMixin
from deck.ui.widgets import th_button, th_circle_btn
from deck.ui.worklist import WorklistMixin


class Dashboard(WorklistMixin, LogViewerMixin, EditorsMixin, ActionsMixin):
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
        theme._apply_palette(state.dashboard_theme())
        r = tk.Tk()
        dpi.scale(r)  # px() for pixel sizes; fonts scale via tk scaling
        r.title("Works")
        # Borderless popup (backlog #5): no title bar, no X -- clicking
        # outside dismisses it, so chrome is dead weight.
        r.overrideredirect(True)
        r.configure(bg=theme.TH_BG)
        r.attributes("-topmost", True)
        r.resizable(False, False)
        try:
            sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
            W, H = dpi.px(480), dpi.px(600)
            r.geometry(f"{W}x{H}+{sw - W - dpi.px(16)}+{sh - H - dpi.px(60)}")
        except Exception:
            pass
        # Brand hairline: 2px accent strip, the only saturated thing
        # besides the primary buttons (borderless popup has no chrome).
        tk.Frame(r, bg=theme.TH_ACCENT, height=2).pack(fill="x")
        top = tk.Frame(r, bg=theme.TH_BG)
        top.pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(top, text="Works", font=theme.TH_FONT_TITLE,
                 bg=theme.TH_BG, fg=theme.TH_FG).pack(side="left")
        th_button(top, text="New", command=self.open_editor,
                  accent=True, icon="plus").pack(side="right")
        th_button(top, text="Group",
                  command=lambda: self.open_group_editor(None),
                  icon="folder-plus").pack(side="right", padx=(0, 4))
        th_circle_btn(top, "settings", command=self.open_settings,
                      style="ghost").pack(side="right", padx=(0, 4))
        th_circle_btn(top, "rotate-cw", command=self.refresh,
                      style="ghost").pack(side="right", padx=(0, 2))
        self.status_var = tk.StringVar(value="")
        tk.Label(r, textvariable=self.status_var, fg=theme.TH_DIM, bg=theme.TH_BG,
                 font=("Segoe UI", 9)).pack(fill="x", padx=14, pady=(0, 2))
        body = tk.Frame(r, bg=theme.TH_BG)
        body.pack(fill="both", expand=True, padx=12, pady=4)
        canvas = tk.Canvas(body, highlightthickness=0, bg=theme.TH_BG)
        scroll = tk.Scrollbar(body, command=canvas.yview, relief="flat", bd=0,
                              width=12, bg=theme.TH_BTN, troughcolor=theme.TH_BG,
                              activebackground=theme.TH_BTN_HI, highlightthickness=0)
        self.list_frame = tk.Frame(canvas, bg=theme.TH_BG)
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
        bot = tk.Frame(r, bg=theme.TH_BG)
        bot.pack(fill="x", padx=14, pady=(4, 12))
        th_button(bot, text="works.json",
                  command=lambda: os.startfile(str(core.MANIFEST)),
                  width=12, style="ghost").pack(side="left")
        th_button(bot, text="Quit",
                  command=lambda: state.actions.put("quit"),
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
        elif isinstance(action, tuple) and len(action) == 2 and action[0] == "log":
            w = state.work_by_id(action[1])
            if w is not None:
                self.show()
                self.open_log_viewer(w)
        elif isinstance(action, tuple) and len(action) == 2 and action[0] == "run":
            w = state.work_by_id(action[1])
            if w is not None:
                self._act_run(w)  # same double-fire guard as the row button
        elif isinstance(action, tuple) and len(action) == 2 and action[0] == "call":
            action[1]()  # worker-thread completion, marshalled onto Tk
        elif action == "refresh":
            self.refresh()
        elif action == "quit":
            try:
                if state.tray_host is not None and getattr(state.tray_host, "hwnd", None):
                    unregister_hotkey(state.tray_host.hwnd, 1)
            except Exception:
                pass
            try:
                if state.tray_host is not None:
                    state.tray_host.stop()
            finally:
                self.root.destroy()
        else:
            state.log(f"unknown action: {action!r}")

    def _poll(self):
        gen = getattr(self, "_gen", 0)
        while True:
            try:
                action = state.actions.get_nowait()
            except queue.Empty:
                break
            try:
                self._handle_action(action)
            except Exception as e:
                state.log(f"action {action!r} failed: {e}")
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
        # (running set or the manifest itself). Otherwise just
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
                sig = (frozenset(state.running_snapshot()),
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
                    self.say(f"{len(state.running_snapshot())} running")
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

    def _place_near_tray(self, win=None, W=None, H=None):
        """Pin a window bottom-right (taskbar/resolution may have moved).

        The dashboard pins to the corner; secondary windows (log viewer)
        sit LEFT of it when it is visible instead of on top of it.
        W/H are device pixels; default = the dashboard (480x600 design px).
        """
        try:
            win = win or self.root
            W = W or dpi.px(480)
            H = H or dpi.px(600)
            sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
            edge, bar = dpi.px(16), dpi.px(60)
            x = sw - W - edge
            if win is not self.root and self.visible:
                x = x - dpi.px(400) - dpi.px(12)
                if x < 0:
                    x = sw - W - edge
            win.geometry(f"{W}x{H}+{x}+{sh - H - bar}")
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
            if state.tray_host is None or not getattr(state.tray_host, "hwnd", None):
                return
            hk = core.canonical_hotkey(
                core.get_settings(core.load_manifest()).get(
                    "hotkey", core.DEFAULT_HOTKEY)) or core.DEFAULT_HOTKEY
            parsed = core.parse_hotkey(hk)
            if not parsed:
                return
            mods, vk = parsed
            if register_hotkey(state.tray_host.hwnd, 1, mods, vk):
                self._hotkey_on = True
                state.log(f"global hotkey {hk} registered")
                self.say(f"hotkey {hk} on")
        except Exception as e:
            state.log(f"hotkey ensure failed: {e}")

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
        win.configure(bg=theme.TH_CARD_EDGE)
        win.attributes("-topmost", True)
        win.resizable(False, False)
        outer = tk.Frame(win, bg=theme.TH_BG)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        head = tk.Frame(outer, bg=theme.TH_BG)
        head.pack(fill="x", padx=10, pady=(8, 2))
        ttl = tk.Label(head, text=title, font=theme.TH_FONT_B,
                       bg=theme.TH_BG, fg=theme.TH_FG)
        ttl.pack(side="left")
        th_circle_btn(head, "x", lambda: self._close_popup(win),
                      style="ghost").pack(side="right")
        self._draggable(win, head, ttl)
        body = tk.Frame(outer, bg=theme.TH_BG)
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
        icons.clear_cache()  # images belong to the dead root + old palette
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

    def _sweep_pending(self):
        """Clear transitional marks the live snapshot confirms (or timeout).

        Called every _poll tick: blue starting… survives until the work
        is ACTUALLY running, so a stale cache can never flash white in
        between.
        """
        pending = getattr(self, "_pending", None)
        if not pending:
            return
        try:
            run = state.running_snapshot()
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

        def _done(m=msg):
            # Runs on the Tk thread (via the actions queue): _pending is
            # iterated by render/_sweep_pending there, and Tk itself is not
            # thread-safe (root.after from a worker was the old path).
            # Start/stop marks stay until the live snapshot CONFIRMS them
            # (swept by _poll); only fire-and-forget marks clear here.
            for k in pending_wids:
                e = self._pending.get(k)
                if e is not None and e.get("expect") is None:
                    self._pending.pop(k, None)
            self.say(m)
            try:
                state._rescan.set()  # fresh scan NOW so confirm lands fast
            except Exception:
                pass
            self.refresh(quiet=True)
        state.actions.put(("call", _done))  # _poll (250ms) runs it on the Tk thread
