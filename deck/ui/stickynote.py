"""Persistent, draggable, multi-instance floating sticky notes with custom titles."""
import json
import time
import tkinter as tk

from deck.ui import dpi, theme
from deck.ui.launcher import enforce_win32_topmost
from deck.ui.widgets import th_circle_btn
import launchdeck_core as core

NOTES_FILE = core.HERE / "launchdeck_logs" / "sticky_notes.json"


class StickyNote:
    """A single draggable floating sticky note with custom title."""

    def __init__(self, master, note_id, title="Note", content="", pos=None,
                 on_update=None, on_new=None, on_delete=None):
        self.master = master
        self.note_id = note_id
        self.on_update = on_update
        self.on_new = on_new
        self.on_delete = on_delete
        self._save_timer = None

        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.configure(bg=theme.TH_CARD_EDGE)
        self.window.attributes("-topmost", True)
        self.window.resizable(False, False)

        w, h = dpi.px(260), dpi.px(230)
        if pos:
            x, y = pos
        else:
            sw = self.window.winfo_screenwidth()
            x, y = max(20, sw - dpi.px(320)), dpi.px(90)
        self.window.geometry(f"{w}x{h}+{x}+{y}")

        outer = tk.Frame(self.window, bg=theme.TH_BG)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        # Amber accent strip
        amber_color = "#F59E0B"
        strip = tk.Frame(outer, bg=amber_color, height=dpi.px(3))
        strip.pack(fill="x")

        # Header bar
        head = tk.Frame(outer, bg=theme.TH_CARD)
        head.pack(fill="x", padx=8, pady=(4, 3))

        # Editable Title Entry
        self.title_var = tk.StringVar(value=title or "Note")
        title_entry = tk.Entry(
            head,
            textvariable=self.title_var,
            font=theme.TH_FONT_B,
            bg=theme.TH_CARD,
            fg=theme.TH_FG,
            insertbackground=theme.TH_FG,
            relief="flat",
            bd=0,
            width=14,
        )
        title_entry.pack(side="left", fill="x", expand=True, padx=(2, 4))
        title_entry.bind("<KeyRelease>", lambda _e: self._schedule_save())

        # Buttons on right: + (new note) and x (delete note)
        th_circle_btn(
            head, "x", command=self.delete_note,
            style="ghost", font_size=8,
        ).pack(side="right")

        th_circle_btn(
            head, "plus", command=self.create_sibling,
            style="ghost", font_size=8,
        ).pack(side="right", padx=(0, 2))

        self._setup_drag(head, strip)

        # Content Text Box
        self.txt = tk.Text(
            outer,
            bg="#181B22",
            fg="#F0F4F8",
            insertbackground="#F0F4F8",
            font=("Segoe UI", 10),
            wrap="word",
            relief="flat",
            bd=0,
            padx=10,
            pady=8,
        )
        self.txt.pack(fill="both", expand=True)
        if content:
            self.txt.insert("1.0", content)

        self.txt.bind("<KeyRelease>", lambda _e: self._schedule_save())
        self.txt.bind("<FocusOut>", lambda _e: self._trigger_update())

        enforce_win32_topmost(self.window)

    def _setup_drag(self, *handles):
        drag_pos = {}

        def _down(event):
            drag_pos["x"], drag_pos["y"] = event.x_root, event.y_root
            try:
                drag_pos["gx"], drag_pos["gy"] = self.window.winfo_x(), self.window.winfo_y()
            except Exception:
                drag_pos["gx"], drag_pos["gy"] = 0, 0

        def _move(event):
            try:
                nx = drag_pos["gx"] + event.x_root - drag_pos["x"]
                ny = drag_pos["gy"] + event.y_root - drag_pos["y"]
                self.window.geometry(f"+{nx}+{ny}")
            except Exception:
                pass

        def _up(_event):
            self._trigger_update()
            enforce_win32_topmost(self.window)

        for h in handles:
            h.bind("<ButtonPress-1>", _down)
            h.bind("<B1-Motion>", _move)
            h.bind("<ButtonRelease-1>", _up)

    def _schedule_save(self):
        if self._save_timer:
            try:
                self.window.after_cancel(self._save_timer)
            except Exception:
                pass
        self._save_timer = self.window.after(350, self._trigger_update)

    def _trigger_update(self):
        if self.on_update:
            self.on_update(self)

    def to_data(self):
        try:
            gx, gy = self.window.winfo_x(), self.window.winfo_y()
        except Exception:
            gx, gy = 200, 200
        return {
            "id": self.note_id,
            "title": self.title_var.get().strip() or "Note",
            "content": self.txt.get("1.0", "end-1c"),
            "x": gx,
            "y": gy,
        }

    def create_sibling(self):
        if self.on_new:
            self.on_new(self)

    def delete_note(self):
        if self.on_delete:
            self.on_delete(self)
        try:
            self.window.destroy()
        except Exception:
            pass

    def close(self):
        self._trigger_update()
        try:
            self.window.destroy()
        except Exception:
            pass

    def _save_content(self):
        self._trigger_update()


class StickyNoteManager:
    """Manages multi-instance sticky notes and persistence."""

    def __init__(self, master):
        self.master = master
        self.active_notes = {}  # note_id -> StickyNote

    def load_saved_data(self):
        try:
            if NOTES_FILE.exists():
                return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        # Fallback to legacy single note if exists
        legacy_file = core.HERE / "launchdeck_logs" / "sticky_note.txt"
        if legacy_file.exists():
            try:
                content = legacy_file.read_text(encoding="utf-8")
                return [{"id": "note_1", "title": "Note 1", "content": content, "x": 300, "y": 120}]
            except Exception:
                pass
        return []

    def save_all(self):
        try:
            NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
            saved = [n.to_data() for n in self.active_notes.values() if n.window.winfo_exists()]
            NOTES_FILE.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def toggle(self):
        """Toggle all sticky notes open / closed."""
        # If any are open, close them all
        alive = [n for n in self.active_notes.values() if n.window.winfo_exists()]
        if alive:
            self.save_all()
            for n in alive:
                try:
                    n.window.destroy()
                except Exception:
                    pass
            self.active_notes.clear()
            return None

        # Otherwise, open all saved notes or create 1 fresh note
        saved = self.load_saved_data()
        if not saved:
            saved = [{"id": f"note_{int(time.time())}", "title": "Note 1", "content": "", "x": 300, "y": 120}]

        spawned = []
        for item in saved:
            spawned.append(self._spawn_note(item))
        return spawned[0] if spawned else None

    def _spawn_note(self, item):
        nid = item.get("id") or f"note_{int(time.time() * 1000)}"
        pos = (item.get("x", 200), item.get("y", 120))
        note = StickyNote(
            self.master,
            note_id=nid,
            title=item.get("title", "Note"),
            content=item.get("content", ""),
            pos=pos,
            on_update=lambda _n: self.save_all(),
            on_new=self._on_new_note,
            on_delete=self._on_delete_note,
        )
        self.active_notes[nid] = note
        return note

    def _on_new_note(self, parent_note):
        try:
            px, py = parent_note.window.winfo_x(), parent_note.window.winfo_y()
        except Exception:
            px, py = 200, 120
        new_id = f"note_{int(time.time() * 1000)}"
        count = len(self.active_notes) + 1
        item = {
            "id": new_id,
            "title": f"Note {count}",
            "content": "",
            "x": px + dpi.px(30),
            "y": py + dpi.px(30),
        }
        note = self._spawn_note(item)
        self.save_all()
        return note

    def _on_delete_note(self, note):
        self.active_notes.pop(note.note_id, None)
        self.save_all()
