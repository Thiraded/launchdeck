"""Task / group / settings editor dialogs."""
from tkinter import filedialog
from tkinter import messagebox
import os
import tkinter as tk

from launchdeck_tray import unregister_hotkey
import launchdeck_core as core
from deck.ui import state
from deck.ui import theme
from deck.ui.viewmodel import _swap_adjacent, _unique_id, _work_to_form
from deck.ui.widgets import th_button, th_circle_btn


class EditorsMixin:
    """Dashboard mixin (see deck/ui/app.py)."""

    # -- group editor (backlog #3) ----------------------------------------
    def open_group_editor(self, group=None):
        manifest = core.load_manifest()
        win, body = self._popup_shell("Rename Group" if group else "New Group")
        namevar = tk.StringVar(value=(group or {}).get("label", ""))
        tk.Label(body, text="Label", bg=theme.TH_BG, fg=theme.TH_FG).grid(
            row=0, column=0, sticky="w", padx=8, pady=6)
        tk.Entry(body, textvariable=namevar, width=40, relief="flat", bd=4,
                 bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG,
                 insertbackground=theme.TH_INPUT_FG).grid(
            row=0, column=1, padx=8, pady=6)
        tk.Label(body, text="Members", bg=theme.TH_BG, fg=theme.TH_FG).grid(
            row=1, column=0, sticky="nw", padx=8)
        box = tk.Frame(body, bg=theme.TH_BG)
        box.grid(row=1, column=1, sticky="w", padx=8, pady=3)
        current = set((group or {}).get("members", []))
        checks = {}
        for w in manifest.get("works", []):
            wid = w.get("id", "")
            var = tk.BooleanVar(value=wid in current)
            checks[wid] = var
            tk.Checkbutton(box, text=w.get("label", wid), variable=var,
                           bg=theme.TH_BG, fg=theme.TH_FG, selectcolor=theme.TH_FIELD,
                           activebackground=theme.TH_BG, activeforeground=theme.TH_FG,
                           anchor="w").pack(fill="x")
        # Order lives here (not on every row): members in order, ▲▼ to
        # move, membership ticks stay in sync both ways.
        by_id = {w.get("id"): w for w in manifest.get("works", [])}
        order = [m for m in (group or {}).get("members", []) if m in by_id]
        tk.Label(body, text="Order (top = first):", bg=theme.TH_BG, fg=theme.TH_FG).grid(
            row=2, column=0, sticky="nw", padx=8, pady=3)
        obox = tk.Frame(body, bg=theme.TH_BG)
        obox.grid(row=2, column=1, sticky="w", padx=8, pady=3)
        lb = tk.Listbox(obox, width=40, height=min(6, max(3, len(order) + 1)),
                        relief="flat", bd=4, bg=theme.TH_FIELD, fg=theme.TH_FG,
                        selectbackground=theme.TH_ACCENT,
                        selectforeground="white",
                        highlightthickness=0, activestyle="none")
        lb.pack(side="left")
        abox = tk.Frame(obox, bg=theme.TH_BG)
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
            tk.Label(body, text="Fork from:", bg=theme.TH_BG, fg=theme.TH_FG).grid(
                row=3, column=0, sticky="w", padx=8, pady=3)
            gforkvar = tk.StringVar(value="(blank — fresh)")
            gforkopts = ["(blank — fresh)"] + [
                f"{g2.get('label', g2.get('id'))} [{g2.get('id')}]"
                for g2 in manifest.get("groups", [])]
            om_gfork = tk.OptionMenu(body, gforkvar, *gforkopts)
            om_gfork.configure(bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG, relief="flat",
                               bd=0, activebackground=theme.TH_BTN_HI,
                               highlightthickness=0)
            om_gfork["menu"].configure(bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG)
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

    # -- settings (suite hotkey) ------------------------------------------
    def open_settings(self):
        manifest = core.load_manifest()
        st0 = core.get_settings(manifest)
        current = st0.get("hotkey", core.DEFAULT_HOTKEY)
        win, body = self._popup_shell("Settings")
        tk.Label(body, text="Global hotkey (modifiers + key):", bg=theme.TH_BG,
                 fg=theme.TH_FG).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        ent = tk.Entry(body, width=24, relief="flat", bd=4,
                       bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG,
                       insertbackground=theme.TH_INPUT_FG)
        ent.grid(row=0, column=1, padx=8, pady=6)
        ent.insert(0, current)
        tk.Label(body, text="Theme:", bg=theme.TH_BG,
                 fg=theme.TH_FG).grid(row=1, column=0, sticky="w", padx=8, pady=3)
        themevar = tk.StringVar(value=st0.get("theme", "dark"))
        om_theme = tk.OptionMenu(body, themevar, "dark", "light")
        om_theme.configure(bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG, relief="flat", bd=0,
                           activebackground=theme.TH_BTN_HI, highlightthickness=0)
        om_theme["menu"].configure(bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG)
        om_theme.grid(row=1, column=1, sticky="w", padx=8, pady=3)
        compactvar = tk.BooleanVar(value=bool(st0.get("compact", True)))
        tk.Checkbutton(body, text="compact rows (one line per work)",
                       variable=compactvar, bg=theme.TH_BG, fg=theme.TH_FG,
                       selectcolor=theme.TH_FIELD, activebackground=theme.TH_BG,
                       activeforeground=theme.TH_FG).grid(
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
                if state.tray_host is not None and getattr(state.tray_host, "hwnd", None):
                    unregister_hotkey(state.tray_host.hwnd, 1)
            except Exception:
                pass
            self._hotkey_on = False
            self._ensure_hotkey()
            if getattr(self, "_hotkey_on", False):
                hk_msg = f"hotkey {hk} on"
            else:
                hk_msg = f"hotkey {hk} saved -- taken, grabs when free"
                state.log(f"hotkey {hk} taken at settings save")
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
            tk.Label(body, text=cap, bg=theme.TH_BG, fg=theme.TH_FG).grid(
                row=i + 1, column=0, sticky="w", padx=8, pady=3)
            tk.Entry(body, textvariable=vals[key], width=44, relief="flat", bd=4,
                     bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG,
                     insertbackground=theme.TH_INPUT_FG).grid(
                         row=i + 1, column=1, padx=8, pady=3)
        th_button(body, text="Browse…",
                  command=lambda: vals["bat"].set(
                      filedialog.askopenfilename(
                          initialdir=str(state.HERE),
                          filetypes=[("Launchers", "*.bat *.lnk *.exe"), ("All", "*.*")]) or vals["bat"].get()),
                  width=9).grid(row=2, column=2, padx=8)
        tk.Label(body, text="Icon", bg=theme.TH_BG, fg=theme.TH_FG).grid(
            row=4, column=0, sticky="w", padx=8, pady=3)
        om_icon = tk.OptionMenu(body, vals["icon"], *theme.ICON_CHOICES)
        om_icon.configure(bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG, relief="flat", bd=0,
                          activebackground=theme.TH_BTN_HI, highlightthickness=0)
        om_icon["menu"].configure(bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG)
        om_icon.grid(row=4, column=1, sticky="w", padx=8)
        tk.Label(body, text="Group", bg=theme.TH_BG, fg=theme.TH_FG).grid(
            row=5, column=0, sticky="w", padx=8, pady=3)
        groups = ["(none — standalone)"] + [f"{g.get('label')} [{g.get('id')}]" for g in manifest.get("groups", [])]
        gvar = tk.StringVar(value="(none — standalone)")
        if vals["group"].get():
            for txt in groups:
                if vals["group"].get() in txt:
                    gvar = tk.StringVar(value=txt)
        om_grp = tk.OptionMenu(body, gvar, *groups)
        om_grp.configure(bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG, relief="flat", bd=0,
                         activebackground=theme.TH_BTN_HI, highlightthickness=0)
        om_grp["menu"].configure(bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG)
        om_grp.grid(row=5, column=1, sticky="w", padx=8)
        tk.Checkbutton(body, text="detect running state", variable=vals["detect"],
                       bg=theme.TH_BG, fg=theme.TH_FG, selectcolor=theme.TH_FIELD,
                       activebackground=theme.TH_BG, activeforeground=theme.TH_FG).grid(
            row=6, column=1, sticky="w", padx=8)
        tk.Label(body, text="Commands: one per line (app: prefix = App step, else Terminal). "
                           "Non-empty = inline mode, overrides .bat at launch.",
                 bg=theme.TH_BG, fg=theme.TH_DIM, font=theme.TH_FONT_S).grid(
            row=7, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 0))
        txt_steps = tk.Text(body, width=64, height=5, relief="flat", bd=4,
                            bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG,
                            insertbackground=theme.TH_INPUT_FG,
                            font=("Consolas", 9))
        txt_steps.grid(row=8, column=0, columnspan=3, padx=8, pady=3, sticky="we")
        if (work or {}).get("steps"):
            txt_steps.insert("1.0", core.steps_to_text(work.get("steps")))
        tk.Label(body, text="Vars: NAME=value per line (%NAME% usable in commands).",
                 bg=theme.TH_BG, fg=theme.TH_DIM, font=theme.TH_FONT_S).grid(
            row=9, column=0, columnspan=3, sticky="w", padx=8, pady=(6, 0))
        txt_vars = tk.Text(body, width=64, height=3, relief="flat", bd=4,
                           bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG,
                           insertbackground=theme.TH_INPUT_FG,
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
            ids = [x.get("id") for x in man.get("works", [])]
            wid = (work or {}).get("id") or ("w-" + "".join(
                c.lower() if c.isalnum() else "-" for c in label).strip("-")[:24])
            if not (work or {}).get("id"):
                # Creation (incl. fork): forking twice must mint "copy 2",
                # never silently overwrite the first copy.
                wid = _unique_id(wid, ids)
            entry = dict(work or {})
            entry.update({"id": wid, "label": label,
                          "icon": vals["icon"].get(),
                          "detect": bool(vals["detect"].get()),
                          "run": "detached"})  # the only mode: every save migrates
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
            tk.Label(body, text="Fork from:", bg=theme.TH_BG, fg=theme.TH_FG).grid(
                row=0, column=0, sticky="w", padx=8, pady=3)
            forkvar = tk.StringVar(value="(blank — fresh)")
            forkopts = ["(blank — fresh)"] + [
                f"{w2.get('label', w2.get('id'))} [{w2.get('id')}]"
                for w2 in manifest.get("works", [])]
            om_fork = tk.OptionMenu(body, forkvar, *forkopts)
            om_fork.configure(bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG, relief="flat", bd=0,
                              activebackground=theme.TH_BTN_HI, highlightthickness=0)
            om_fork["menu"].configure(bg=theme.TH_FIELD, fg=theme.TH_INPUT_FG)
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
            mv = tk.Frame(body, bg=theme.TH_BG)
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
