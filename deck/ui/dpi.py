"""DPI awareness for Tk on Windows.

Without this, Windows bitmap-stretches the whole Tk window at 125/150%
display scaling (blurry text + icons). Must run BEFORE tk.Tk().

System-aware (not per-monitor): Tk 8.6 does not relayout on
WM_DPICHANGED, so per-monitor would leave wrong sizes after a move.
Tk then derives `tk scaling` from the real DPI, so point-sized fonts
scale themselves; pixel sizes (widths, pads, icons) go through px().
"""
import os

_scale = 1.0


def enable() -> bool:
    if os.name != "nt":
        return False
    import ctypes
    try:
        # PROCESS_SYSTEM_DPI_AWARE
        return ctypes.windll.shcore.SetProcessDpiAwareness(1) == 0
    except Exception:
        try:
            return bool(ctypes.windll.user32.SetProcessDPIAware())
        except Exception:
            return False


def scale(root) -> float:
    """Pixel scale factor vs 96 dpi; cached for px()."""
    global _scale
    try:
        _scale = max(1.0, root.winfo_fpixels("1i") / 96.0)
    except Exception:
        _scale = 1.0
    return _scale


def px(n) -> int:
    """Design pixels (at 96 dpi) -> device pixels."""
    return int(round(n * _scale))
