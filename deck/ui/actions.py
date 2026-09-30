"""Row actions: start/stop/restart, move, duplicate, delete."""
from tkinter import messagebox
import re
import time

import launchdeck_core as core
from deck.ui import state
from deck.ui.viewmodel import _swap_adjacent


class ActionsMixin:
    """Dashboard mixin (see deck/ui/app.py)."""

    def _act_run(self, w):
        wid = w.get("id", "")
        label = w.get("label", wid)
        if wid in self._pending:
            self.say(f"already {self._pending[wid].get('state', 'working')} '{label}'…")
            return
        verb = "stopping" if wid in state.running_snapshot() else "starting"
        self._act_async(lambda: state.toggle_start_stop(w), f"{verb} '{label}'…",
                        pending={wid: (verb, verb == "starting")})

    def _do_restart(self, w):
        try:
            result = core.kill_work(w)
            if result is not None:
                detail = (" (no safe target)" if not result else
                          " (PIDs " + ", ".join(map(str, result)) + ")")
                return f"restart blocked: stop '{w.get('label')}'{detail}"
        except Exception as e:
            return f"stop failed: {e}"
        time.sleep(1.5)
        rec = core.launch_work(w)
        return "restarted — fresh window" if rec else "start failed (nothing runnable?)"

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
        verb = "starting" if start else "stopping"
        self._act_async(lambda: self._do_all(members, start),
                        f"{verb} {len(fresh)} work(s)…",
                        pending={k: (verb, bool(start)) for k in fresh})

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

    def _toggle_group(self, gid):
        """Accordion: collapse/expand one group, persisting the choice.

        Only the kids container packs/unpacks -- rows keep their widgets
        and refs, so no rebuild and no blink. Counts refresh right after
        through the in-place path.
        """
        try:
            man = core.load_manifest()
            st = core.get_settings(man)
        except Exception:
            return
        col = [x for x in st.get("collapsed", []) if isinstance(x, str)]
        if gid in col:
            col.remove(gid)
            is_open = True
        else:
            col.append(gid)
            is_open = False
        st["collapsed"] = col
        man["settings"] = st
        try:
            core.save_manifest(man)
        except Exception as e:
            self.say(f"save failed: {e}")
            return
        refs = self._group_heads.get(gid)
        if refs is not None:
            try:
                if is_open:
                    refs["kids"].pack(fill="x")
                else:
                    refs["kids"].pack_forget()
                refs["tog"].itemconfig(refs["tog"]._txt,
                                       text="▾" if is_open else "▸")
            except Exception:
                pass
        self.refresh(quiet=True)

    def _do_all(self, members, start):
        msgs = []
        try:
            commandlines = core.scan_commandlines()
            if not core.scan_available() or not commandlines:
                return "status unavailable (process scan failed)"
        except Exception as e:
            return f"status unavailable ({e})"
        for m in members:
            running = core.is_running(m, commandlines)
            if start and not running:
                r = core.launch_work(m)
                msgs.append("started" if r else "FAILED")
            elif not start and running:
                try:
                    result = core.kill_work(m)
                    if result is None:
                        msgs.append("stopped")
                    else:
                        detail = (" (no safe target)" if not result else
                                  " (PIDs " + ", ".join(map(str, result)) + ")")
                        msgs.append(f"blocked{detail}")
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
            self.say(f"deleted '{w.get('label')}'")
            self.refresh(quiet=True)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e))

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
