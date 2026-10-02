"""Always-on-top desktop button that toggles the dashboard popup."""
import tkinter as tk

from deck.ui import dpi, icons, theme


class DesktopLauncher:
    """A draggable lightning button kept visible while the deck is running."""

    _TRANSPARENT = "#010101"

    def __init__(self, master, on_toggle, on_move, position=None):
        self.on_toggle = on_toggle
        self.on_move = on_move
        self.size = dpi.px(56)
        self._press = None
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
        self.button.bind("<Enter>", lambda _e: self._paint(True))
        self.button.bind("<Leave>", lambda _e: self._paint(False))
        self.button.bind("<ButtonPress-1>", self._on_press)
        self.button.bind("<B1-Motion>", self._on_drag)
        self.button.bind("<ButtonRelease-1>", self._on_release)

    def _paint(self, hover):
        plate = theme.TH_ACCENT_HI if hover else theme.TH_ACCENT
        self._image = icons.photo("zap", max(8, round(self.size * 0.48)),
                                  "white", box=self.size, plate=plate)
        self.button.configure(image=self._image)

    def _set_position(self, x, y, notify=True):
        try:
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
        except tk.TclError:
            sw, sh = self.size, self.size
        x = min(max(0, int(x)), max(0, sw - self.size))
        y = min(max(0, int(y)), max(0, sh - self.size))
        self._position = (x, y)
        try:
            self.window.geometry(f"{self.size}x{self.size}+{x}+{y}")
        except tk.TclError:
            pass
        if notify:
            self.on_move()

    def position(self):
        return self._position

    def show(self):
        try:
            self.window.deiconify()
            self.window.lift()
            self.window.attributes("-topmost", True)
            self.visible = True
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
        return "break"
