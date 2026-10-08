"""Away note overlay and message prompt dialog."""
import sys
import time
import tkinter as tk

from deck.ui import dpi, theme
from deck.ui.launcher import enforce_win32_topmost
from deck.ui.widgets import th_button

_HAVE_WIN32 = False
if sys.platform == "win32":
    try:
        import ctypes
        _user32 = ctypes.windll.user32
        _HAVE_WIN32 = True
    except Exception:
        _HAVE_WIN32 = False


def get_virtual_screen_geometry(master):
    """Return (vx, vy, vw, vh) representing the full virtual desktop."""
    if _HAVE_WIN32:
        try:
            vx = _user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
            vy = _user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
            vw = _user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
            vh = _user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
            if vw > 0 and vh > 0:
                return vx, vy, vw, vh
        except Exception:
            pass
    try:
        vw = master.winfo_screenwidth()
        vh = master.winfo_screenheight()
    except Exception:
        vw, vh = 1920, 1080
    return 0, 0, vw, vh


def get_display_center(master, anchor_pos=None):
    """Return (cx, cy) pixel coordinates where the centered card should appear."""
    vx, vy, vw, vh = get_virtual_screen_geometry(master)
    try:
        sw = master.winfo_screenwidth()
        sh = master.winfo_screenheight()
    except Exception:
        sw, sh = vw, vh

    if anchor_pos:
        ax, ay = anchor_pos
        if sw > 0 and sh > 0:
            mon_x = (int(ax) // sw) * sw
            mon_y = (int(ay) // sh) * sh
            return mon_x + sw // 2, mon_y + sh // 2
    return vx + vw // 2, vy + vh // 2


class AwayOverlay:
    """Full-screen darkened overlay displaying an away note in the center."""

    def __init__(self, master, message, anchor_pos=None, on_close=None):
        self.master = master
        self.message = (message or "").strip() or "Away from keyboard"
        self.on_close = on_close
        self.target_alpha = 0.92
        self._closing = False
        self._ticker_id = None

        vx, vy, vw, vh = get_virtual_screen_geometry(master)
        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.configure(bg="#000000")
        self.window.attributes("-topmost", True)
        try:
            self.window.attributes("-alpha", 0.0)
        except Exception:
            pass

        pos_x = f"+{vx}" if vx >= 0 else str(vx)
        pos_y = f"+{vy}" if vy >= 0 else str(vy)
        self.window.geometry(f"{vw}x{vh}{pos_x}{pos_y}")

        cx, cy = get_display_center(master, anchor_pos)
        rel_x = cx - vx
        rel_y = cy - vy

        self._build_content(rel_x, rel_y)

        enforce_win32_topmost(self.window)
        self._bind_events(self.window)
        self._schedule_keep_topmost()
        self._fade_in(0.0)

    def _build_content(self, rel_x, rel_y):
        wrapper = tk.Frame(self.window, bg="#000000")
        wrapper.pack(fill="both", expand=True)

        card_outer = tk.Frame(wrapper, bg="#2A3348", padx=1, pady=1)
        card_outer.place(x=rel_x, y=rel_y, anchor="center")

        msg_len = len(self.message)
        if msg_len <= 8:
            font_size = 32
            wrap_w = dpi.px(480)
            pad_x = dpi.px(56)
        elif msg_len <= 20:
            font_size = 28
            wrap_w = dpi.px(580)
            pad_x = dpi.px(48)
        elif msg_len <= 45:
            font_size = 22
            wrap_w = dpi.px(680)
            pad_x = dpi.px(40)
        else:
            font_size = 18
            wrap_w = dpi.px(780)
            pad_x = dpi.px(32)

        card = tk.Frame(card_outer, bg="#0D111A", padx=pad_x, pady=dpi.px(32))
        card.pack(fill="both", expand=True)

        accent_bar = tk.Frame(card, bg=theme.TH_ACCENT, height=dpi.px(3))
        accent_bar.pack(fill="x", pady=(0, dpi.px(18)))

        now_time = time.strftime("%H:%M")
        badge_text = f"AFK • {now_time}"
        lbl_badge = tk.Label(
            card, text=badge_text,
            font=("Segoe UI", 11, "bold"),
            bg="#0D111A", fg=theme.TH_ACCENT_HI,
        )
        lbl_badge.pack(pady=(0, dpi.px(14)))

        lbl_msg = tk.Label(
            card, text=self.message,
            font=("Segoe UI", font_size, "bold"),
            bg="#0D111A", fg="#FFFFFF",
            justify="center",
            wraplength=wrap_w,
        )
        lbl_msg.pack(padx=dpi.px(12), pady=(0, dpi.px(22)))

        sep = tk.Frame(card, bg="#1E2536", height=1)
        sep.pack(fill="x", pady=(0, dpi.px(14)))

        lbl_hint = tk.Label(
            card,
            text="Click or press Esc to dismiss",
            font=("Segoe UI", 9),
            bg="#0D111A", fg="#7A8699",
        )
        lbl_hint.pack()

        for w in (wrapper, card_outer, card, accent_bar, lbl_badge, lbl_msg, sep, lbl_hint):
            self._bind_events(w)

    def _bind_events(self, widget):
        for btn in ("<ButtonPress-1>", "<ButtonPress-2>", "<ButtonPress-3>"):
            widget.bind(btn, lambda _e: self.dismiss())
        widget.bind("<Key>", lambda _e: self.dismiss())

    def _schedule_keep_topmost(self):
        try:
            if not self._closing and self.window.winfo_exists():
                enforce_win32_topmost(self.window)
                self._ticker_id = self.window.after(1000, self._schedule_keep_topmost)
        except Exception:
            pass

    def _fade_in(self, current_alpha):
        if self._closing or not self.window.winfo_exists():
            return
        next_alpha = min(self.target_alpha, current_alpha + 0.10)
        try:
            self.window.attributes("-alpha", next_alpha)
        except Exception:
            pass
        if next_alpha < self.target_alpha:
            self.window.after(16, lambda: self._fade_in(next_alpha))

    def dismiss(self):
        if self._closing:
            return
        self._closing = True
        if self._ticker_id:
            try:
                self.window.after_cancel(self._ticker_id)
            except Exception:
                pass
            self._ticker_id = None

        def _fade_out(current_alpha):
            if not self.window.winfo_exists():
                return
            next_alpha = max(0.0, current_alpha - 0.15)
            try:
                self.window.attributes("-alpha", next_alpha)
            except Exception:
                pass
            if next_alpha > 0.0:
                self.window.after(16, lambda: _fade_out(next_alpha))
            else:
                try:
                    if self.on_close:
                        self.on_close()
                    self.window.destroy()
                except Exception:
                    pass

        try:
            cur = float(self.window.attributes("-alpha"))
        except Exception:
            cur = self.target_alpha
        _fade_out(cur)


def open_away_prompt(dashboard):
    """Open the dialog prompting the user to type an away message."""
    win, body = dashboard._popup_shell("Away Note")

    preset_box = tk.Frame(body, bg=theme.TH_BG)
    preset_box.pack(fill="x", padx=4, pady=(0, 8))

    presets = [
        "cooking",
        "7-11",
        "อาบน้ำ",
        "ล้างจาน",
        "ฟังยุ ร้องเรียกเหมียวๆเดี๋ยวก็มา",
    ]

    txt = tk.Text(
        body,
        height=3,
        width=42,
        relief="flat",
        bd=4,
        bg=theme.TH_FIELD,
        fg=theme.TH_INPUT_FG,
        insertbackground=theme.TH_INPUT_FG,
        font=theme.TH_FONT,
        wrap="word",
    )
    txt.pack(fill="x", padx=4, pady=(0, 10))

    def _append_preset(val):
        try:
            if txt.tag_ranges("sel"):
                txt.delete("sel.first", "sel.last")
        except Exception:
            pass

        cur_text = txt.get("1.0", "end-1c")
        if cur_text in ("Away from keyboard", "ไม่อยู่ที่โต๊ะชั่วคราว (Away from keyboard)"):
            txt.delete("1.0", "end")
            cur_text = ""

        if not cur_text.strip():
            txt.insert("1.0", val)
            txt.mark_set(tk.INSERT, f"1.0+{len(val)}c")
        else:
            try:
                insert_idx = txt.index(tk.INSERT)
            except Exception:
                insert_idx = "end-1c"

            try:
                prev_char = txt.get(f"{insert_idx}-1c", insert_idx)
            except Exception:
                prev_char = " "

            prefix = " " if prev_char and not prev_char.isspace() else ""
            txt.insert(insert_idx, prefix + val)
            txt.mark_set(tk.INSERT, f"{insert_idx}+{len(prefix + val)}c")

        txt.see(tk.INSERT)
        txt.focus_set()

    # Sort presets: short chips first by length, then longer phrases
    sorted_presets = sorted(presets, key=lambda s: (len(s) > 16, len(s), s))

    max_row_chars = 34
    current_row = tk.Frame(preset_box, bg=theme.TH_BG)
    current_row.pack(fill="x", pady=(0, 4))
    char_count = 0

    for p in sorted_presets:
        item_len = len(p) + 4
        if char_count > 0 and (char_count + item_len > max_row_chars):
            current_row = tk.Frame(preset_box, bg=theme.TH_BG)
            current_row.pack(fill="x", pady=(0, 4))
            char_count = 0

        btn = th_button(
            current_row,
            text=f"+ {p}",
            command=lambda v=p: _append_preset(v),
            style="ghost",
        )
        btn.configure(font=("Segoe UI", 8), cursor="hand2")
        btn.pack(side="left", padx=(0, 4))
        char_count += item_len

    last_msg = getattr(dashboard, "_last_away_msg", "")
    if not last_msg:
        last_msg = "Away from keyboard"
    txt.insert("1.0", last_msg)
    txt.tag_add("sel", "1.0", "end")
    txt.focus_set()

    def _submit():
        user_text = txt.get("1.0", "end-1c").strip()
        if not user_text:
            user_text = "Away from keyboard"
        dashboard._last_away_msg = user_text
        dashboard._close_popup(win)
        dashboard.show_away_overlay(user_text)

    btn_bar = tk.Frame(body, bg=theme.TH_BG)
    btn_bar.pack(fill="x", padx=4, pady=(2, 4))

    th_button(
        btn_bar,
        text="close",
        command=lambda: dashboard._close_popup(win),
        width=8,
        style="ghost",
    ).pack(side="left")

    th_button(
        btn_bar,
        text="Clear",
        command=lambda: (txt.delete("1.0", "end"), txt.focus_set()),
        width=6,
        style="ghost",
    ).pack(side="left", padx=(6, 0))

    th_button(
        btn_bar,
        text="Enter",
        command=_submit,
        accent=True,
        icon="monitor",
    ).pack(side="right")

    txt.bind("<Return>", lambda _e: (_submit(), "break")[1])
    win.bind("<Escape>", lambda _e: dashboard._close_popup(win))

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
