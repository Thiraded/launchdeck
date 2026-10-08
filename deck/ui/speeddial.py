"""Speed Dial (Floating Action Menu) inspired by modern mobile/desktop FABs."""
import tkinter as tk

from deck.ui import dpi, icons, theme
from deck.ui.launcher import enforce_win32_topmost


class SpeedDialMenu:
    """Floating Action Menu that expands vertically from the launcher button."""

    _TRANSPARENT = "#010101"

    def __init__(self, master, launcher_ref, items, on_close=None, on_quit=None):
        self.master = master
        self.launcher_ref = launcher_ref
        self.items = items
        self.on_close = on_close
        self.on_quit = on_quit
        self.visible = False
        self._anim_step = 0
        self._anim_timer = None

        # Main window for app features
        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.configure(bg=self._TRANSPARENT)
        self.window.attributes("-topmost", True)
        try:
            self.window.attributes("-transparentcolor", self._TRANSPARENT)
        except tk.TclError:
            self.window.configure(bg=theme.TH_BG)
            self._TRANSPARENT = theme.TH_BG
        self.window.resizable(False, False)

        # Opposite window for Exit door button
        self.exit_window = tk.Toplevel(master)
        self.exit_window.overrideredirect(True)
        self.exit_window.configure(bg=self._TRANSPARENT)
        self.exit_window.attributes("-topmost", True)
        try:
            self.exit_window.attributes("-transparentcolor", self._TRANSPARENT)
        except tk.TclError:
            self.exit_window.configure(bg=theme.TH_BG)
        self.exit_window.resizable(False, False)

        self._images = []  # Keep references
        self._rows = []
        self._exit_row = None
        self._win_coords = (0, 0, 0, 0)
        self._exit_coords = (0, 0, 0, 0)
        self._build_ui()
        self.reposition()

        # Dismiss when focus is lost
        self.window.bind("<FocusOut>", lambda _e: self._maybe_dismiss())
        self.exit_window.bind("<FocusOut>", lambda _e: self._maybe_dismiss())
        enforce_win32_topmost(self.window)
        enforce_win32_topmost(self.exit_window)

    def _build_ui(self):
        btn_sz = dpi.px(42)
        ic_sz = max(8, round(btn_sz * 0.46))

        # Main items container
        self._container = tk.Frame(self.window, bg=self._TRANSPARENT)
        self._container.pack(fill="both", expand=True)

        for item in self.items:
            row = tk.Frame(self._container, bg=self._TRANSPARENT)

            lbl = tk.Label(
                row,
                text=item["label"],
                font=("Segoe UI", 9, "bold"),
                bg="#181C24",
                fg="#FFFFFF",
                padx=dpi.px(10),
                pady=dpi.px(4),
                cursor="hand2",
            )
            lbl.pack(side="left", padx=(0, dpi.px(8)))

            img_norm = icons.photo(
                item["icon"], ic_sz, "white",
                box=btn_sz, plate=item.get("plate", theme.TH_ACCENT),
            )
            img_hi = icons.photo(
                item["icon"], ic_sz, "white",
                box=btn_sz, plate=item.get("plate_hi", theme.TH_ACCENT_HI),
            )
            self._images.extend([img_norm, img_hi])

            btn_circ = tk.Label(
                row,
                image=img_norm,
                bg=self._TRANSPARENT,
                bd=0,
                padx=0,
                pady=0,
                highlightthickness=0,
                cursor="hand2",
            )
            btn_circ.pack(side="right")

            def _on_enter(_e, l=lbl, b=btn_circ, ih=img_hi):
                l.configure(bg="#2E3542")
                b.configure(image=ih)

            def _on_leave(_e, l=lbl, b=btn_circ, inorm=img_norm):
                l.configure(bg="#181C24")
                b.configure(image=inorm)

            def _on_click(_e, cmd=item["command"]):
                self.close()
                cmd()

            for w in (lbl, btn_circ):
                w.bind("<Enter>", _on_enter)
                w.bind("<Leave>", _on_leave)
                w.bind("<Button-1>", _on_click)

            self._rows.append(row)

        # Exit door button in exit_window
        self._exit_container = tk.Frame(self.exit_window, bg=self._TRANSPARENT)
        self._exit_container.pack(fill="both", expand=True)

        exit_row = tk.Frame(self._exit_container, bg=self._TRANSPARENT)

        lbl_exit = tk.Label(
            exit_row,
            text="Quit",
            font=("Segoe UI", 9, "bold"),
            bg="#181C24",
            fg="#FFFFFF",
            padx=dpi.px(10),
            pady=dpi.px(4),
            cursor="hand2",
        )
        lbl_exit.pack(side="left", padx=(0, dpi.px(8)))

        img_exit_norm = icons.photo(
            "door-open", ic_sz, "white",
            box=btn_sz, plate="#DC2626",
        )
        img_exit_hi = icons.photo(
            "door-open", ic_sz, "white",
            box=btn_sz, plate="#EF4444",
        )
        self._images.extend([img_exit_norm, img_exit_hi])

        btn_exit = tk.Label(
            exit_row,
            image=img_exit_norm,
            bg=self._TRANSPARENT,
            bd=0,
            padx=0,
            pady=0,
            highlightthickness=0,
            cursor="hand2",
        )
        btn_exit.pack(side="right")

        def _on_exit_enter(_e, l=lbl_exit, b=btn_exit, ih=img_exit_hi):
            l.configure(bg="#2E3542")
            b.configure(image=ih)

        def _on_exit_leave(_e, l=lbl_exit, b=btn_exit, inorm=img_exit_norm):
            l.configure(bg="#181C24")
            b.configure(image=inorm)

        def _on_exit_click(_e):
            self.close()
            if self.on_quit:
                self.on_quit()

        for w in (lbl_exit, btn_exit):
            w.bind("<Enter>", _on_exit_enter)
            w.bind("<Leave>", _on_exit_leave)
            w.bind("<Button-1>", _on_exit_click)

        self._exit_row = exit_row

    def reposition(self):
        """Align speed dial directly beside/above the launcher button."""
        if not self.launcher_ref:
            return
        lx, ly = self.launcher_ref.position()
        l_sz = getattr(self.launcher_ref, "size", dpi.px(56))
        btn_sz = dpi.px(42)
        gap = dpi.px(6)
        num_items = len(self._rows)

        dw = dpi.px(220)
        dh = num_items * (btn_sz + gap) + gap

        ew = dpi.px(130)
        eh = btn_sz + gap * 2

        sw = self.window.winfo_screenwidth()
        sh = self.window.winfo_screenheight()

        x = lx + l_sz - dw
        if x < 4:
            x = 4

        # If launcher is in lower half of screen: main items go UP, exit goes DOWN
        if ly > dh + dpi.px(20):
            y = ly - dh - gap
            ex = lx + l_sz - ew
            ey = ly + l_sz + gap
            if ey + eh > sh - 4:
                ex = lx - ew - gap
                ey = ly + (l_sz - eh) // 2
        else:
            y = ly + l_sz + gap
            ex = lx + l_sz - ew
            ey = ly - eh - gap
            if ey < 4:
                ex = lx - ew - gap
                ey = ly + (l_sz - eh) // 2

        self._win_coords = (x, y, dw, dh)
        self._exit_coords = (ex, ey, ew, eh)

        pos_x = f"+{x}" if x >= 0 else str(x)
        pos_y = f"+{y}" if y >= 0 else str(y)
        self.window.geometry(f"{dw}x{dh}{pos_x}{pos_y}")

        pos_ex = f"+{ex}" if ex >= 0 else str(ex)
        pos_ey = f"+{ey}" if ey >= 0 else str(ey)
        self.exit_window.geometry(f"{ew}x{eh}{pos_ex}{pos_ey}")

    def show(self):
        self.reposition()
        self.visible = True
        self.window.deiconify()
        self.exit_window.deiconify()
        self.window.lift()
        self.exit_window.lift()
        enforce_win32_topmost(self.window)
        enforce_win32_topmost(self.exit_window)

        if self._anim_timer:
            try:
                self.window.after_cancel(self._anim_timer)
            except Exception:
                pass
            self._anim_timer = None

        self._anim_step = 0
        self._animate()

    def _animate(self):
        if not self.visible or not self.window.winfo_exists():
            return
        total_steps = 7
        t = (self._anim_step + 1) / total_steps
        ease = 1.0 - (1.0 - t) ** 3  # cubic ease-out

        btn_sz = dpi.px(42)
        gap = dpi.px(6)
        _x, _y, dw, dh = self._win_coords
        _ex, _ey, ew, eh = self._exit_coords

        num_items = len(self._rows)
        for i, row in enumerate(self._rows):
            if _y < self.launcher_ref.position()[1]:
                target_y = dh - (btn_sz + gap) * (i + 1)
                start_y = dh
            else:
                target_y = gap + (btn_sz + gap) * i
                start_y = 0
            cur_y = int(start_y + (target_y - start_y) * ease)
            row.place(x=0, y=cur_y, width=dw, height=btn_sz)

        if self._exit_row:
            if _ey > self.launcher_ref.position()[1]:
                exit_start_y = 0
                exit_target_y = gap
            elif _ey < self.launcher_ref.position()[1]:
                exit_start_y = eh
                exit_target_y = gap
            else:
                exit_start_y = gap
                exit_target_y = gap
            cur_ey = int(exit_start_y + (exit_target_y - exit_start_y) * ease)
            self._exit_row.place(x=0, y=cur_ey, width=ew, height=btn_sz)

        self._anim_step += 1
        if self._anim_step < total_steps:
            self._anim_timer = self.window.after(16, self._animate)
        else:
            self._anim_timer = None

    def close(self):
        if not self.visible:
            return
        self.visible = False
        if self._anim_timer:
            try:
                self.window.after_cancel(self._anim_timer)
            except Exception:
                pass
            self._anim_timer = None
        try:
            self.window.withdraw()
        except Exception:
            pass
        try:
            self.exit_window.withdraw()
        except Exception:
            pass
        if self.on_close:
            self.on_close()

    def destroy(self):
        self.close()
        try:
            self.window.destroy()
        except Exception:
            pass
        try:
            self.exit_window.destroy()
        except Exception:
            pass

    def _maybe_dismiss(self):
        def _check():
            try:
                if not self.visible:
                    return
                f = None
                try:
                    f = self.master.focus_displayof()
                except Exception:
                    pass
                if f is None:
                    self.close()
                    return
                f_str = str(f)
                if not (f_str.startswith(str(self.window)) or f_str.startswith(str(self.exit_window))):
                    self.close()
            except Exception:
                pass
        self.window.after(160, _check)
