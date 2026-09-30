"""Dashboard work list: build rows, update them in place."""
import tkinter as tk

import launchdeck_core as core
from deck.ui import dpi, icons, state
from deck.ui import theme
from deck.ui.viewmodel import _freeze, _row_view
from deck.ui.widgets import (_short, icon_label, set_button_icon, th_button,
                             th_circle_btn)


def _group_count(on, total):
    return f"{on}/{total} running"


class WorklistMixin:
    """Dashboard mixin (see deck/ui/app.py)."""

    def refresh(self, quiet=False):
        if self.root is None:
            return
        manifest = core.load_manifest()
        run = state.running_snapshot()
        by_id = {w.get("id"): w for w in manifest.get("works", [])}
        shown = set()

        compact = state.dashboard_compact()
        # Layout key: state flips update rows IN PLACE (no blink).
        # Works are fingerprinted WHOLE (any config edit rebuilds --
        # otherwise row buttons keep a stale dict and Edit shows
        # pre-edit values). Running/hidden/pending stay out: those
        # flip constantly and update in place.
        struct = (compact,
                  tuple((g.get("id"), g.get("label"),
                         tuple(m for m in g.get("members", [])))
                        for g in manifest.get("groups", [])),
                  tuple((w.get("id"),
                         tuple(sorted((k, _freeze(v))
                                      for k, v in w.items())))
                        for w in manifest.get("works", [])))
        collapsed = state.collapsed_groups()

        def _icon_btns(holder, w, v):
            """Uniform circular cluster (all 24px, snug to the glyph).

            Packed right in reverse so the visual order is
            toggle · log · restart · edit · delete.
            The toggle is the only accent; delete is the only red.
            (Ordering lives in the group/task editors, not here.
            Duplicating too: fork from +New / +Group, or Duplicate
            inside the edit dialogs.)
            Returns the toggle button (recolored in place on state flip).
            Secondary actions are ghost (dim, no plate until hovered) so
            the toggle is the only filled thing in the row.
            """
            th_circle_btn(holder, "trash-2", lambda w=w: self.delete_work(w),
                          style="danger").pack(side="right")
            th_circle_btn(holder, "pencil", lambda w=w: self.open_editor(w),
                          style="ghost").pack(side="right", padx=(0, 2))
            th_circle_btn(holder, "rotate-cw", lambda w=w: self._act_restart(w),
                          style="ghost").pack(side="right", padx=(0, 2))
            # Detached is the only mode: no window exists, so the log
            # viewer (docker-logs equivalent) stands in for Hide.
            # A legacy windowed entry gets Log too -- edit + save
            # migrates it to detached. There is no Hide anymore.
            th_circle_btn(holder, "file-text",
                          lambda w=w: self.open_log_viewer(w),
                          style="ghost").pack(side="right", padx=(0, 2))
            tog = th_circle_btn(holder, "stop" if v["running"] else "play",
                                lambda w=w: self._act_run(w),
                                style=None if v["running"] else "accent")
            tog.pack(side="right", padx=(0, 6))
            return tog

        def _tile(parent, v):
            """Rounded icon tile: work icon tinted by state."""
            return icon_label(parent, v["icon"], v["icon_c"], size=18,
                              box=30, plate=theme.TH_FIELD, shape="rounded")

        def _status(parent, v, text):
            """Status word led by a colored dot (image + text, one Label)."""
            return tk.Label(parent, text=text, font=theme.TH_FONT_S,
                            bg=theme.TH_CARD, fg=v["sub_c"], compound="left",
                            image=icons.photo("dot", dpi.px(10), v["dot_c"]),
                            padx=0)

        def _compact_row(main, w, v):
            """One line: icon · title · status · icon cluster. Returns refs."""
            line = tk.Frame(main, bg=theme.TH_CARD)
            line.pack(fill="x", padx=(8, 8), pady=6)
            btns = tk.Frame(line, bg=theme.TH_CARD)
            btns.pack(side="right", padx=(8, 0))
            tog = _icon_btns(btns, w, v)
            # tile carries the state color; the dot + word back it up.
            iconlab = _tile(line, v)
            iconlab.pack(side="left", padx=(0, 8))
            title = tk.Label(line,
                             text=_short(w.get('label', w.get('id', ''))),
                             font=theme.TH_FONT_B, bg=theme.TH_CARD, fg=theme.TH_FG,
                             cursor="hand2")
            title.pack(side="left")
            st = _status(line, v, f" {v['sub']}")
            st.config(cursor="hand2")
            st.pack(side="left", padx=(8, 0))
            # the label IS the big target: click toggles Start/Stop.
            for lab in (title, st):
                lab.bind("<Button-1>", lambda _e, w=w: self._act_run(w))
            return {"kind": "compact", "icon": iconlab, "title": title,
                    "sub": st, "tog": tog}

        def _roomy_row(main, w, v):
            """Two-line card. Returns refs for in-place updates."""
            topl = tk.Frame(main, bg=theme.TH_CARD)
            topl.pack(fill="x", padx=(8, 10), pady=(8, 0))
            iconlab = _tile(topl, v)
            iconlab.pack(side="left", padx=(0, 10))
            txt = tk.Frame(topl, bg=theme.TH_CARD)
            txt.pack(side="left", fill="x", expand=True)
            title = tk.Label(txt, text=w.get('label', w.get('id', '')),
                             font=theme.TH_FONT_B, bg=theme.TH_CARD, fg=theme.TH_FG,
                             cursor="hand2", anchor="w")
            title.pack(anchor="w")
            title.bind("<Button-1>", lambda _e, w=w: self._act_run(w))
            sublab = _status(txt, v, f" {v['sub']}")
            sublab.pack(anchor="w")
            btns = tk.Frame(main, bg=theme.TH_CARD)
            btns.pack(fill="x", padx=10, pady=(6, 8))
            left = tk.Frame(btns, bg=theme.TH_CARD)
            left.pack(side="left")
            right = tk.Frame(btns, bg=theme.TH_CARD)
            right.pack(side="right")
            tog_btn = th_button(left, "Stop" if v["running"] else "Start",
                                lambda w=w: self._act_run(w),
                                accent=not v["running"],
                                icon="stop" if v["running"] else "play")
            tog_btn.pack(side="left")
            log_btn = th_button(left, "Log",
                                lambda w=w: self.open_log_viewer(w),
                                icon="file-text")
            log_btn.pack(side="left", padx=(6, 0))
            th_circle_btn(right, "trash-2", lambda w=w: self.delete_work(w),
                          style="danger").pack(side="right")
            th_circle_btn(right, "pencil", lambda w=w: self.open_editor(w),
                          style="ghost").pack(side="right", padx=(0, 2))
            th_circle_btn(right, "rotate-cw", lambda w=w: self._act_restart(w),
                          style="ghost").pack(side="right", padx=(0, 2))
            return {"kind": "roomy", "icon": iconlab, "title": title,
                    "sub": sublab, "tog_btn": tog_btn, "log_btn": log_btn}

        def work_row(parent, w):
            """Build one row, registering live refs for in-place updates."""
            wid = w.get("id", "")
            shown.add(wid)
            v = _row_view(w, run, self._pending)
            row = tk.Frame(parent, bg=theme.TH_CARD, padx=0, pady=0,
                           highlightbackground=theme.TH_CARD_EDGE,
                           highlightthickness=1)
            row.pack(fill="x", pady=4, padx=2)
            # icon carries the running color; the edge bar stays too.
            edge = tk.Frame(row,
                            bg=theme.TH_GREEN if v["running"] else theme.TH_CARD_EDGE,
                            width=3)
            edge.pack(side="left", fill="y")
            main = tk.Frame(row, bg=theme.TH_CARD)
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
                gid = g.get("id")
                members = [by_id[m] for m in g.get("members", []) if m in by_id]
                if not members:
                    continue
                on = sum(1 for m in members if m.get("id") in run)
                is_open = gid not in collapsed
                gframe = tk.Frame(self.list_frame, bg=theme.TH_BG)
                gframe.pack(fill="x", pady=(10, 2))
                head = tk.Frame(gframe, bg=theme.TH_BG)
                head.pack(fill="x", padx=2, pady=(0, 2))
                tog = th_circle_btn(head,
                                    "chevron-down" if is_open else "chevron-right",
                                    lambda gid=gid: self._toggle_group(gid),
                                    style="ghost", size=22)
                tog.pack(side="left")
                title = tk.Label(head, text=f" {g.get('label', gid)}",
                                 font=theme.TH_FONT_SECTION, bg=theme.TH_BG, fg=theme.TH_FG,
                                 cursor="hand2")
                title.pack(side="left")
                title.bind("<Button-1>",
                           lambda _e, gid=gid: self._toggle_group(gid))
                cnt = tk.Label(head, text=_group_count(on, len(members)),
                               font=theme.TH_FONT_S, bg=theme.TH_BG,
                               fg=theme.TH_GREEN if on else theme.TH_DIM)
                cnt.pack(side="left", padx=(8, 0))
                kids = tk.Frame(gframe, bg=theme.TH_BG)
                kids.pack(fill="x")
                self._group_heads[gid] = {"tog": tog, "title": title,
                                          "cnt": cnt, "kids": kids}
                for m in members:
                    work_row(kids, m)
                brow = tk.Frame(kids, bg=theme.TH_BG)
                brow.pack(fill="x", padx=6, pady=(0, 8))
                if not is_open:
                    kids.pack_forget()
                th_button(brow, text="Start all",
                          command=lambda ms=members: self._act_all(ms, True),
                          accent=True, icon="play").pack(side="left")
                th_circle_btn(brow, "trash-2", lambda g=g: self.delete_group(g),
                              style="danger").pack(side="right")
                th_circle_btn(brow, "pencil", lambda g=g: self.open_group_editor(g),
                              style="ghost").pack(side="right", padx=(0, 2))
                th_button(brow, text="Stop all",
                          command=lambda ms=members: self._act_all(ms, False),
                          style="ghost", icon="stop").pack(side="right", padx=(0, 4))
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
                refs = self._group_heads.get(g.get("id"))
                if not refs:
                    continue
                try:
                    members = [by_id[m] for m in g.get("members", [])
                               if m in by_id]
                    on = sum(1 for m in members if m.get("id") in run)
                    refs["title"].config(
                        text=f" {g.get('label', g.get('id'))}")
                    refs["cnt"].config(
                        text=_group_count(on, len(members)),
                        fg=theme.TH_GREEN if on else theme.TH_DIM)
                    refs["tog"].set_icon(
                        "chevron-down" if g.get("id") not in collapsed
                        else "chevron-right")
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
            refs["edge"].config(bg=theme.TH_GREEN if v["running"] else theme.TH_CARD_EDGE)
            refs["icon"].set(v["icon"], v["icon_c"], theme.TH_FIELD)
            refs["sub"].config(
                text=f" {v['sub']}", fg=v["sub_c"],
                image=icons.photo("dot", dpi.px(10), v["dot_c"]))
            if refs.get("kind") == "compact":
                refs["title"].config(
                    text=_short(w.get('label', w.get('id', ''))))
                tog = refs.get("tog")
                if tog is not None:
                    if v["running"]:
                        tog.recolor(theme.TH_BTN, theme.TH_BTN_HI, theme.TH_FG)
                    else:
                        tog.recolor(theme.TH_ACCENT, theme.TH_ACCENT_HI, "white")
                    tog.set_icon("stop" if v["running"] else "play")
            else:
                refs["title"].config(text=w.get('label', w.get('id', '')))
                tb = refs.get("tog_btn")
                if tb is not None:
                    if v["running"]:
                        tb.config(text="Stop", bg=theme.TH_BTN, fg=theme.TH_FG,
                                  activebackground=theme.TH_BTN_HI)
                        set_button_icon(tb, "stop", theme.TH_FG)
                    else:
                        tb.config(text="Start", bg=theme.TH_ACCENT, fg="white",
                                  activebackground=theme.TH_ACCENT_HI)
                        set_button_icon(tb, "play", "white")
                lb = refs.get("log_btn")
                if lb is not None:
                    lb.config(text="Log")
        except Exception:
            pass
