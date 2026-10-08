"""Always-on-top desktop button that toggles the dashboard popup."""
import sys
import tkinter as tk

from deck.ui import dpi, icons, theme

_HAVE_WIN32 = False
if sys.platform == "win32":
    try:
        import ctypes
        from ctypes import wintypes
        _user32 = ctypes.windll.user32
        _user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_uint
        ]
        _user32.SetWindowPos.restype = wintypes.BOOL
        _HWND_TOPMOST = ctypes.cast(-1, wintypes.HWND)
        _SWP_FLAGS = 0x0001 | 0x0002 | 0x0010 | 0x0040  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW
        _HAVE_WIN32 = True
    except Exception:
        _HAVE_WIN32 = False


def enforce_win32_topmost(target_win):
    """Enforce topmost at Win32 OS level without stealing keyboard focus."""
    if not target_win:
        return
    try:
        if not target_win.winfo_exists():
            return
        target_win.lift()
    except Exception:
        pass
    if _HAVE_WIN32:
        try:
            root_hwnd = _user32.GetAncestor(target_win.winfo_id(), 3)  # GA_ROOT
            if root_hwnd and _user32.IsWindow(root_hwnd):
                if _user32.IsIconic(root_hwnd) or not _user32.IsWindowVisible(root_hwnd):
                    _user32.ShowWindow(root_hwnd, 4)  # SW_SHOWNOACTIVATE
                _user32.SetWindowPos(root_hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_FLAGS)
        except Exception:
            pass


class DesktopLauncher:
    """A draggable lightning button kept visible while the deck is running."""

    _TRANSPARENT = "#010101"

    def __init__(self, master, on_toggle, on_move, position=None, on_context_menu=None):
        self.on_toggle = on_toggle
        self.on_move = on_move
        self.on_context_menu = on_context_menu
        self.size = dpi.px(56)
        self._press = None
        self._r_press = None
        self._dragged = False
        self.visible = False

        self.window = tk.Toplevel(master)
        self.window.overrideredirect(True)
        self.window.configure(bg=self._TRANSPARENT)
        self.window.attributes("-topmost", True)
        try:
            self.window.attributes("-transparentcolor", self._TRANSPARENT)
        except tk.TclError:
            # Older Tk builds keep the square surface; the button still works.
            self.window.configure(bg=theme.TH_BG)
            self._TRANSPARENT = theme.TH_BG
        self.window.resizable(False, False)

        try:
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
        except tk.TclError:
            sw, sh = self.size * 4, self.size * 4
        margin_x = dpi.px(20)
        margin_y = dpi.px(76)  # leave the taskbar clear at the default spot
        self._position = position or (sw - self.size - margin_x,
                                      sh - self.size - margin_y)
        self._set_position(*self._position, notify=False)
        self.window.geometry(f"{self.size}x{self.size}+{self._position[0]}+"
                             f"{self._position[1]}")

        self.button = tk.Label(
            self.window, bg=self._TRANSPARENT, bd=0, padx=0, pady=0,
            highlightthickness=0, cursor="hand2")
        self.button.pack(fill="both", expand=True)
        self._paint(False)
        self.button.bind("<Enter>", lambda _e: self._on_enter())
        self.button.bind("<Leave>", lambda _e: self._paint(False))
        self.button.bind("<ButtonPress-1>", self._on_press)
        self.button.bind("<B1-Motion>", self._on_drag)
        self.button.bind("<ButtonRelease-1>", self._on_release)
        self.button.bind("<ButtonPress-3>", self._on_r_press)
        self.button.bind("<ButtonRelease-3>", self._on_r_release)

        try:
            self.window.update_idletasks()
            self.enforce_topmost()
        except Exception:
            pass

    def _paint(self, hover):
        plate = theme.TH_ACCENT_HI if hover else theme.TH_ACCENT
        name = getattr(self, "_icon_name", "zap")
        self._image = icons.photo(name, max(8, round(self.size * 0.48)),
                                  "white", box=self.size, plate=plate)
        self.button.configure(image=self._image)

    def set_icon(self, name):
        self._icon_name = name
        self._paint(False)

    def _on_enter(self):
        self._paint(True)
        self.enforce_topmost()

    def enforce_topmost(self):
        enforce_win32_topmost(self.window)

    def _schedule_keep_topmost(self):
        try:
            if self.visible and self.window.winfo_exists():
                if self._press is None:
                    self.enforce_topmost()
                self.window.after(500, self._schedule_keep_topmost)
        except Exception:
            pass

    def _set_position(self, x, y, notify=True):
        try:
            if _HAVE_WIN32:
                vx = _user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
                vy = _user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
                vw = _user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
                vh = _user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
                if vw <= 0 or vh <= 0:
                    vx, vy, vw, vh = 0, 0, self.window.winfo_screenwidth(), self.window.winfo_screenheight()
            else:
                vx, vy = 0, 0
                vw = self.window.winfo_screenwidth()
                vh = self.window.winfo_screenheight()
        except Exception:
            vx, vy, vw, vh = 0, 0, self.size * 4, self.size * 4
        x = min(max(vx, int(x)), max(vx, vx + vw - self.size))
        y = min(max(vy, int(y)), max(vy, vy + vh - self.size))
        self._position = (x, y)
        x_str = f"+{x}" if x >= 0 else str(x)
        y_str = f"+{y}" if y >= 0 else str(y)
        try:
            self.window.geometry(f"{self.size}x{self.size}{x_str}{y_str}")
        except tk.TclError:
            pass
        if notify:
            self.on_move()

    def position(self):
        return self._position

    def show(self):
        try:
            self.window.deiconify()
            self.window.update_idletasks()
            self.enforce_topmost()
            self.visible = True
            self._schedule_keep_topmost()
        except tk.TclError:
            self.visible = False

    def _on_press(self, event):
        x, y = self.position()
        self._press = (event.x_root, event.y_root, x, y)
        self._dragged = False
        return "break"

    def _on_drag(self, event):
        if self._press is None:
            return "break"
        px, py, x, y = self._press
        dx, dy = event.x_root - px, event.y_root - py
        if not self._dragged and max(abs(dx), abs(dy)) < dpi.px(4):
            return "break"
        self._dragged = True
        self._set_position(x + dx, y + dy)
        return "break"

    def _on_release(self, _event):
        if self._press is not None and not self._dragged:
            self.on_toggle()
        self._press = None
        self._dragged = False
        self.enforce_topmost()
        return "break"

    def _on_r_press(self, event):
        self._r_press = (event.x_root, event.y_root)
        return "break"

    def _on_r_release(self, event):
        trigger = False
        if self._r_press is not None:
            px, py = self._r_press
            if max(abs(event.x_root - px), abs(event.y_root - py)) < dpi.px(6):
                trigger = True
        else:
            trigger = True
        self._r_press = None
        if trigger and self.on_context_menu:
            self.on_context_menu(event.x_root, event.y_root)
        return "break"

