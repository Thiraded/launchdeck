"""wc_tray.py — system-tray host for wc, using ONLY ctypes (no dependencies).

Windows already ships the shell tray API; we talk to it directly so wc gains a
system-tray icon + show/hide without pulling in pystray/Pillow.

Public surface:
  TrayIcon(tip="...", color=(r,g,b))
    .start()                     # spin up the icon on a background thread
    .stop()                      # remove icon, end the thread
    .hide_console() / .show_console() / .toggle_console()
    .notify(title, text)         # balloon tooltip (e.g. "work is running")
    .on_quit = callable          # called when the user picks Quit in the menu
    .quit_event                  # threading.Event set when Quit is chosen
    .available                   # True if a console+tray could be created

Behavior (per user decision 2026-08-30):
  * Clicking the X on the wc console really quits (safe).
  * "h" in wc hides the console to the tray; the tray icon (left-click toggles,
    right-click menu = Show / Hide / Quit) brings it back.
  * When a launched work is detected as running, wc fires a balloon so the user
    knows "it opened" without having to open the window.

Everything is wrapped: if the tray can't be created (headless / no explorer),
wc keeps running normally and hiding is simply a no-op.
"""
import ctypes
import ctypes.wintypes as wt
import threading
import time
import os as _os
import traceback as _tb

# diagnostic log (independent of wc_core) so failures are visible
_TRAY_LOG_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "wc_logs")
_TRAY_LOG_PATH = _os.path.join(_TRAY_LOG_DIR, "tray.log")


def _tray_log(msg):
    try:
        _os.makedirs(_TRAY_LOG_DIR, exist_ok=True)
        with open(_TRAY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass

try:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    gdi32 = ctypes.windll.gdi32
    shell32 = ctypes.windll.shell32
    _HAVE_WIN = True
except Exception:
    _HAVE_WIN = False


# --------------------------------------------------------------------------
# constants
# --------------------------------------------------------------------------
WM_USER = 0x0400
WM_DESTROY = 0x0002
WM_APP_SHUTDOWN = WM_USER + 0x31
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

NULL = 0
IDI_APPLICATION = 32512

NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_INFO = 0x00000010

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIM_SETVERSION = 0x00000004

NIIF_NONE = 0x00000000
NIIF_INFO = 0x00000001
NIIF_WARNING = 0x00000002
NIIF_ERROR = 0x00000003
NIIF_NOSOUND = 0x00000010

SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9

HWND_MESSAGE = ctypes.c_void_p(-3)
WS_POPUP = 0x80000000

IDM_SHOW = 1001
IDM_HIDE = 1002
IDM_QUIT = 1003

TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100

MF_STRING = 0x0000
MF_SEPARATOR = 0x00000800

CS_OWNDC = 0x00000020


# --------------------------------------------------------------------------
# structs
# --------------------------------------------------------------------------
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("hWnd", ctypes.c_void_p),
        ("uID", ctypes.c_ulong),
        ("uFlags", ctypes.c_ulong),
        ("uCallbackMessage", ctypes.c_ulong),
        ("hIcon", ctypes.c_void_p),
        ("szTip", ctypes.c_wchar * 128),
        ("dwState", ctypes.c_ulong),
        ("dwStateMask", ctypes.c_ulong),
        ("szInfo", ctypes.c_wchar * 256),
        ("uVersion", ctypes.c_uint),   # union: uTimeout | uVersion
        ("szInfoTitle", ctypes.c_wchar * 64),
        ("dwInfoFlags", ctypes.c_ulong),
        ("guidItem", GUID),
        ("hBalloonIcon", ctypes.c_void_p),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_ulong),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", ctypes.c_ulong),
        ("biSizeImage", ctypes.c_ulong),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_ulong),
        ("biClrImportant", ctypes.c_ulong),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_byte * 4)]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", ctypes.c_int),
        ("xHotspot", ctypes.c_uint),
        ("yHotspot", ctypes.c_uint),
        ("hbmMask", ctypes.c_void_p),
        ("hbmColor", ctypes.c_void_p),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hWnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_uint64),
        ("lParam", ctypes.c_int64),
        ("time", ctypes.c_ulong),
        ("pt", POINT),
        ("lPrivate", ctypes.c_ulong),
    ]


class WNDCLASSEX(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("style", ctypes.c_uint),
        ("lpfnWndProc", ctypes.c_void_p),  # filled as WNDPROC below
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
        ("hIconSm", ctypes.c_void_p),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_int64, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, ctypes.c_int64
)


# --------------------------------------------------------------------------
# argtypes / restypes (set once)
# --------------------------------------------------------------------------
def _set_prototypes():
    user32.DefWindowProcW.argtypes = (
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, ctypes.c_int64)
    user32.DefWindowProcW.restype = ctypes.c_int64

    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEX)]
    user32.RegisterClassExW.restype = ctypes.c_ushort

    user32.UnregisterClassW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p]
    user32.UnregisterClassW.restype = ctypes.c_int

    user32.CreateWindowExW.argtypes = (
        ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    user32.CreateWindowExW.restype = ctypes.c_void_p

    user32.DestroyWindow.argtypes = [ctypes.c_void_p]
    user32.DestroyWindow.restype = ctypes.c_int

    user32.GetMessageW.argtypes = [
        ctypes.POINTER(MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
    user32.GetMessageW.restype = ctypes.c_int

    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.TranslateMessage.restype = ctypes.c_int

    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = ctypes.c_int64

    user32.PostQuitMessage.argtypes = [ctypes.c_int]
    user32.PostQuitMessage.restype = None

    user32.PostMessageW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, ctypes.c_int64]
    user32.PostMessageW.restype = ctypes.c_int

    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.ShowWindow.restype = ctypes.c_int

    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.SetForegroundWindow.restype = ctypes.c_int

    kernel32.GetConsoleWindow.argtypes = []
    kernel32.GetConsoleWindow.restype = ctypes.c_void_p

    user32.CreatePopupMenu.argtypes = []
    user32.CreatePopupMenu.restype = ctypes.c_void_p

    user32.AppendMenuW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_ulong, ctypes.c_wchar_p]
    user32.AppendMenuW.restype = ctypes.c_int

    user32.DestroyMenu.argtypes = [ctypes.c_void_p]
    user32.DestroyMenu.restype = ctypes.c_int

    user32.TrackPopupMenu.argtypes = (
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    user32.TrackPopupMenu.restype = ctypes.c_uint

    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.GetCursorPos.restype = ctypes.c_int

    user32.LoadIconW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.LoadIconW.restype = ctypes.c_void_p

    user32.CreateIconIndirect.argtypes = [ctypes.POINTER(ICONINFO)]
    user32.CreateIconIndirect.restype = ctypes.c_void_p

    user32.DestroyIcon.argtypes = [ctypes.c_void_p]
    user32.DestroyIcon.restype = ctypes.c_int

    user32.RegisterWindowMessageW.argtypes = [ctypes.c_wchar_p]
    user32.RegisterWindowMessageW.restype = ctypes.c_uint

    gdi32.CreateDIBSection.argtypes = (
        ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), ctypes.c_uint,
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_uint)
    gdi32.CreateDIBSection.restype = ctypes.c_void_p

    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteObject.restype = ctypes.c_int

    shell32.Shell_NotifyIconW.argtypes = [
        ctypes.c_ulong, ctypes.POINTER(NOTIFYICONDATA)]
    shell32.Shell_NotifyIconW.restype = ctypes.c_int

    kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p

    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = ctypes.c_ulong

    kernel32.FormatMessageW.argtypes = (
        ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
        ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_void_p)
    kernel32.FormatMessageW.restype = ctypes.c_ulong

    user32.SetWindowLongPtrW.argtypes = (
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p)
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p


# --------------------------------------------------------------------------
# icon generation (solid colored square, generated — no asset file needed)
# --------------------------------------------------------------------------
def make_square_icon(color=(0, 120, 215)):
    """Return an HICON for a solid `color` square, or the system default icon."""
    try:
        r, g, b = (int(x) & 0xFF for x in color)
        W = H = 32

        # color bitmap (32bpp, BGRA)
        cbmi = BITMAPINFO()
        cbmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        cbmi.bmiHeader.biWidth = W
        cbmi.bmiHeader.biHeight = -H  # top-down
        cbmi.bmiHeader.biPlanes = 1
        cbmi.bmiHeader.biBitCount = 32
        cbmi.bmiHeader.biCompression = 0
        ppv = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(
            NULL, ctypes.byref(cbmi), 0, ctypes.byref(ppv), None, 0)
        if not hbmp:
            raise ctypes.WinError()
        addr = ppv.value
        # dark rounded-square + lightning bolt (drawn per-pixel, no assets)
        bgr, bgg, bgb = (30, 33, 38)
        RAD = 7

        def inside(x, y):
            if RAD <= x < W - RAD:
                return True
            if RAD <= y < H - RAD:
                return True
            cx = RAD if x < RAD else W - 1 - RAD
            cy = RAD if y < RAD else H - 1 - RAD
            return (x - cx) ** 2 + (y - cy) ** 2 <= RAD * RAD

        bolt = [(19, 3), (9, 18), (14, 18), (12, 29), (23, 12), (17, 12)]

        def in_poly(x, y, poly):
            ins = False
            j = len(poly) - 1
            for i in range(len(poly)):
                xi, yi = poly[i]
                xj, yj = poly[j]
                if ((yi > y) != (yj > y)) and (
                        x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                    ins = not ins
                j = i
            return ins

        pixels = bytearray(W * H * 4)
        for yy in range(H):
            for xx in range(W):
                if not inside(xx, yy):
                    continue  # transparent corner (mask bit below)
                o = (yy * W + xx) * 4
                if in_poly(xx, yy, bolt):
                    pixels[o + 0] = b
                    pixels[o + 1] = g
                    pixels[o + 2] = r
                else:
                    pixels[o + 0] = bgb
                    pixels[o + 1] = bgg
                    pixels[o + 2] = bgr
                pixels[o + 3] = 255
        ctypes.memmove(addr, bytes(pixels), len(pixels))

        # 1bpp mask (all zero => fully opaque)
        mbmi = BITMAPINFO()
        mbmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        mbmi.bmiHeader.biWidth = W
        mbmi.bmiHeader.biHeight = -H
        mbmi.bmiHeader.biPlanes = 1
        mbmi.bmiHeader.biBitCount = 1
        mask_row = ((W + 31) // 32) * 4
        mask_size = mask_row * H
        pmask = ctypes.c_void_p()
        hmask = gdi32.CreateDIBSection(
            NULL, ctypes.byref(mbmi), 0, ctypes.byref(pmask), None, 0)
        if not hmask:
            raise ctypes.WinError()
        # 1bpp mask: transparent outside the rounded rect, opaque inside
        # (MSB-first bits, rows padded to 32 bits)
        mask = bytearray(mask_size)
        for y in range(H):
            for x in range(W):
                if not inside(x, y):
                    mask[y * mask_row + x // 8] |= 1 << (7 - (x % 8))
        ctypes.memmove(pmask, bytes(mask), mask_size)

        ii = ICONINFO()
        ii.fIcon = True
        ii.xHotspot = 0
        ii.yHotspot = 0
        ii.hbmMask = hmask
        ii.hbmColor = hbmp
        hicon = user32.CreateIconIndirect(ctypes.byref(ii))
        if not hicon:
            raise ctypes.WinError()
        # The icon copies the bitmaps, so we can release them.
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteObject(hmask)
        return hicon
    except Exception as e:
        _tray_log(f"[icon] generation failed: {e}")
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if hmask:
            gdi32.DeleteObject(hmask)
        return None


# --------------------------------------------------------------------------
# TrayIcon
# --------------------------------------------------------------------------
_INSTANCE = None  # module-global so the WNDPROC can reach the live instance


def _wndproc(hwnd, msg, wparam, lparam):
    inst = _INSTANCE
    if inst is None:
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    if msg == inst.msg:
        # Version 4 packs the icon id into HIWORD(lParam); legacy callbacks
        # put it in wParam. Explorer may reject NIM_SETVERSION for a
        # secondary icon, so accept both layouts.
        ev = int(lparam) & 0xFFFF
        packed_uid = (int(lparam) >> 16) & 0xFFFF
        uid = packed_uid or (int(wparam) & 0xFFFF)
        # Per-icon routing (parked work icons share this window): an
        # instance-level hook gets first refusal with (uid, event).
        handler = getattr(inst, "on_tray_event", None)
        if callable(handler):
            try:
                handler(uid, ev)
            except Exception as e:
                _tray_log(f"[wndproc] on_tray_event failed: {e}")
            return 0
        if ev in (WM_LBUTTONUP, 0x0203):  # 0x0203 = WM_LBUTTONDBLCLK
            try:
                inst.toggle_console()
            except Exception:
                pass
            return 0
        if ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
            _tray_log(f"[wndproc] right-click on icon → _show_menu")
            try:
                inst._show_menu()
            except Exception:
                pass
            return 0
        return 0
    if msg == inst.taskbar_created:
        try:
            if inst._add_icon():
                inst.available = True
                inst._on_taskbar_created()
            else:
                inst.available = False
        except Exception as e:
            inst.available = False
            _tray_log(f"[taskbar] rebuild failed: {e}")
        return 0
    if msg == WM_APP_SHUTDOWN:
        inst._shutdown_on_tray_thread()
        return 0
    if msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        return 0
    if msg == WM_COMMAND:
        # Menu item clicked: wParam low-word is the command id
        try:
            cmd = wparam & 0xFFFF
            inst._on_menu(cmd)
        except Exception:
            pass
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


class TrayIcon:
    def __init__(self, tip="Work Combo (wc)", color=(0, 120, 215)):
        self.tip = (tip or "wc")[:127]
        self.color = color
        self.msg = WM_USER + 1
        self.hwnd = None
        self.hinst = None
        self.icon = None
        self.available = False
        self._alive = False
        self._visible = True  # console currently shown
        self._thread = None
        self._wndproc_cb = None  # keep the WNDPROC alive (no GC)
        self.on_quit = None
        self.quit_event = threading.Event()
        self.console_hwnd = None
        self.taskbar_created = 0
        self.last_error = ""
        self._init_ok = False
        self._cleanup_done = False
        self._cleanup_in_progress = False
        if _HAVE_WIN:
            try:
                _set_prototypes()
                self.taskbar_created = user32.RegisterWindowMessageW(
                    "TaskbarCreated")
                self.console_hwnd = kernel32.GetConsoleWindow()
                self._init_ok = True
            except Exception as e:
                self.console_hwnd = None
                self.last_error = f"Win32 initialization failed: {e}"
                _tray_log(f"[init] {self.last_error}: {_tb.format_exc()}")

    # -- lifecycle --------------------------------------------------------
    def _last_err(self):
        try:
            code = kernel32.GetLastError()
            if not code:
                return ""
            buf = ctypes.create_unicode_buffer(512)
            kernel32.FormatMessageW(
                0x00001000, None, code, 0, buf, 512, None)  # FORMAT_MESSAGE_FROM_SYSTEM
            msg = buf.value.strip() if buf.value else ""
            full = f"err {code:#x}: {msg}" if msg else f"err {code:#x}"
            self.last_error = full
            return full
        except Exception as e:
            return f"(GetLastError failed: {e})"

    def start(self):
        if not _HAVE_WIN:
            self.last_error = "not Windows"
            return False
        if not self._init_ok:
            if not self.last_error:
                self.last_error = "Win32 initialization incomplete"
            return False
        if self._thread and self._thread.is_alive():
            return self.available
        self._cleanup_done = False
        self._cleanup_in_progress = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        for _ in range(150):  # up to ~3s: wait for icon to come up
            if self.available or not self._thread.is_alive():
                break
            time.sleep(0.02)
        if not self.available:
            _tray_log(f"[start] FAILED — {self.last_error}")
        return self.available

    def _run(self):
        global _INSTANCE
        _INSTANCE = self
        _tray_log("[_run] thread started")
        try:
            self.hinst = kernel32.GetModuleHandleW(None)
            _tray_log(f"[_run] hinst={self.hinst!r}")
            self._wndproc_cb = WNDPROC(_wndproc)
            cls = WNDCLASSEX()
            cls.cbSize = ctypes.sizeof(WNDCLASSEX)
            cls.style = CS_OWNDC
            cls.lpfnWndProc = ctypes.cast(self._wndproc_cb, ctypes.c_void_p)
            cls.hInstance = self.hinst
            cls.lpszClassName = "wcTrayClass"
            atom = user32.RegisterClassExW(ctypes.byref(cls))
            if not atom:
                _tray_log(f"[_run] RegisterClassExW failed: {self._last_err()}")
                return
            _tray_log(f"[_run] class registered atom={atom}")

            self.hwnd = user32.CreateWindowExW(
                0, "wcTrayClass", "wcTray", WS_POPUP,
                0, 0, 0, 0, None, None, self.hinst, None)
            if not self.hwnd:
                _tray_log(f"[_run] CreateWindowExW failed: {self._last_err()}")
                user32.UnregisterClassW("wcTrayClass", self.hinst)
                return
            _tray_log(f"[_run] hwnd={self.hwnd!r}")

            self.icon = make_square_icon(self.color)
            if not self.icon or not self._add_icon():
                self.last_error = self.last_error or "failed to add tray icon"
                return
            self.available = True
            self._alive = True
            _tray_log("[_run] icon added — available=True")

            msg = MSG()
            while user32.GetMessageW(ctypes.byref(msg), NULL, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            _tray_log("[_run] message loop ended")
        except Exception as e:
            self.available = False
            _tray_log(f"[_run] EXCEPTION: {e}\n{_tb.format_exc()}")
        finally:
            self._cleanup_native()
            self._alive = False
            self.available = False
            if _INSTANCE is self:
                _INSTANCE = None

    def _on_taskbar_created(self):
        """Subclass hook to rebuild secondary icons after Explorer restarts."""

    def _before_tray_shutdown(self):
        """Subclass hook executed on the tray thread before native cleanup."""

    def _cleanup_native(self):
        """Release native resources once, on the native window owner thread."""
        if self._cleanup_done or self._cleanup_in_progress:
            return
        self._cleanup_in_progress = True
        try:
            self._before_tray_shutdown()
        except Exception as e:
            _tray_log(f"[cleanup] hook failed: {e}")
        try:
            if self.hwnd:
                self._remove_icon()
        except Exception as e:
            _tray_log(f"[cleanup] remove icon failed: {e}")
        try:
            if self.icon:
                user32.DestroyIcon(self.icon)
                self.icon = None
        except Exception as e:
            _tray_log(f"[cleanup] destroy icon failed: {e}")
        destroyed = not self.hwnd
        try:
            if self.hwnd:
                destroyed = bool(user32.DestroyWindow(self.hwnd))
        except Exception as e:
            _tray_log(f"[cleanup] destroy window failed: {e}")
        if destroyed:
            self.hwnd = None
        try:
            if destroyed and self.hinst:
                user32.UnregisterClassW("wcTrayClass", self.hinst)
        except Exception as e:
            _tray_log(f"[cleanup] unregister class failed: {e}")

        self._cleanup_in_progress = False
        self._cleanup_done = self.hwnd is None

    def _shutdown_on_tray_thread(self):
        self._cleanup_native()
        user32.PostQuitMessage(0)

    def stop(self, timeout=3.0):
        """Ask the tray thread to tear down its own native window."""
        thread = self._thread
        if thread and thread.is_alive() and self.hwnd:
            posted = False
            try:
                posted = bool(user32.PostMessageW(
                    self.hwnd, WM_APP_SHUTDOWN, 0, 0))
                if not posted:
                    _tray_log(f"[stop] PostMessageW failed: {self._last_err()}")
            except Exception as e:
                _tray_log(f"[stop] shutdown post failed: {e}")
            if not posted:
                return False
            if threading.current_thread() is not thread:
                thread.join(timeout)
                if thread.is_alive():
                    _tray_log("[stop] tray thread did not exit before timeout")
                    return False
            elif thread.is_alive():
                return False
        self.available = False
        return True

    # -- icon -------------------------------------------------------------
    def _add_icon(self):
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = self.msg
        nid.hIcon = self.icon
        nid.szTip = self.tip
        res = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        _tray_log(f"[_add_icon] Shell_NotifyIconW(NIM_ADD) -> {res}")
        if not res:
            _tray_log(f"[_add_icon] FAILED: {self._last_err()}")
            return False
        # opt into the modern (Vista+) balloon behavior
        nid.uVersion = 4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(nid))
        return True

    def _remove_icon(self):
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

    def set_tooltip(self, text):
        self.tip = (text or "wc")[:127]
        if not (self.hwnd and self._alive):
            return
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_TIP
        nid.szTip = self.tip
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def notify(self, title, text, info_flags=NIIF_INFO):
        """Show a balloon tooltip. info_flags: NIIF_INFO/WARNING/ERROR."""
        if not (self.hwnd and self._alive):
            return
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_INFO
        nid.szInfo = (text or "")[:255]
        nid.szInfoTitle = (title or "")[:63]
        nid.dwInfoFlags = info_flags | NIIF_NOSOUND
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    # -- parked work icons (one tray icon per hidden work) ------------------
    def add_work_icon(self, uid, tip, color=(63, 185, 80)):
        """Add a secondary tray icon (parked hidden work). Returns HICON or None."""
        hicon = None
        registered = False
        succeeded = False
        try:
            hicon = make_square_icon(color)
            if not hicon:
                return None
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd = self.hwnd
            nid.uID = uid
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = self.msg
            nid.hIcon = hicon
            nid.szTip = (tip or "work")[:127]
            ok = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
            _tray_log(f"[add_work_icon] uid={uid} NIM_ADD -> {ok}")
            if not ok:
                return None
            registered = True
            # Prefer v4 callbacks, but keep the successfully added icon when
            # Explorer rejects NIM_SETVERSION. _wndproc supports the legacy
            # wParam icon-id layout too.
            nid.uVersion = 4
            if not shell32.Shell_NotifyIconW(
                    NIM_SETVERSION, ctypes.byref(nid)):
                _tray_log(
                    f"[add_work_icon] uid={uid} NIM_SETVERSION failed; "
                    "using legacy callbacks")
            succeeded = True
            return hicon
        except Exception as e:
            _tray_log(f"[add_work_icon] EXCEPTION: {e}")
            return None
        finally:
            if hicon and not succeeded:
                if registered:
                    try:
                        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                    except Exception:
                        pass
                try:
                    user32.DestroyIcon(hicon)
                except Exception:
                    pass

    def del_work_icon(self, uid, hicon=None):
        """Remove a parked work icon; destroys its icon handle too."""
        try:
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd = self.hwnd
            nid.uID = uid
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
        except Exception:
            pass
        if hicon:
            try:
                user32.DestroyIcon(hicon)
            except Exception:
                pass

    # -- console show/hide ------------------------------------------------
    def _resolve_console(self):
        """Re-fetch GetConsoleWindow() if we don't have one yet (handles the
        case where wc was launched from a launcher that hadn't attached a
        console yet, or via wc.bat which gives us one very early)."""
        if not self.console_hwnd and _HAVE_WIN:
            try:
                self.console_hwnd = kernel32.GetConsoleWindow() or None
            except Exception:
                pass
        return self.console_hwnd

    def show_console(self):
        h = self._resolve_console()
        _tray_log(f"[show_console] hwnd={h!r} prev={self._visible}")
        if h:
            user32.ShowWindow(h, SW_RESTORE)
            user32.SetForegroundWindow(h)
        self._visible = True

    def hide_console(self):
        h = self._resolve_console()
        _tray_log(f"[hide_console] hwnd={h!r} prev={self._visible}")
        if h:
            r = user32.ShowWindow(h, SW_HIDE)
            _tray_log(f"[hide_console] ShowWindow returned {r}")
        else:
            _tray_log("[hide_console] NO console hwnd to hide")
        self._visible = False

    def toggle_console(self):
        if self._visible:
            self.hide_console()
        else:
            self.show_console()

    @property
    def visible(self):
        return self._visible

    # -- menu -------------------------------------------------------------
    def _show_menu(self):
        hmenu = user32.CreatePopupMenu()
        user32.AppendMenuW(
            hmenu, MF_STRING, IDM_SHOW,
            "Show" if not self._visible else "Show (already shown)")
        user32.AppendMenuW(
            hmenu, MF_STRING, IDM_HIDE,
            "Hide" if self._visible else "Hide (already hidden)")
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, IDM_QUIT, "Quit wc")
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        # Bring the (now-foreground-capable) tray window forward, then show
        # the popup. This is the prerequisite Windows requires for
        # TrackPopupMenu to deliver clicks via WM_COMMAND.
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(
            hmenu, TPM_RIGHTBUTTON | TPM_RETURNCMD | 0x0080,  # +TPM_NONOTIFY
            pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(hmenu)
        if cmd:
            self._on_menu(cmd)

    def _on_menu(self, cmd):
        if cmd == IDM_SHOW:
            self.show_console()
        elif cmd == IDM_HIDE:
            self.hide_console()
        elif cmd == IDM_QUIT:
            self.quit_event.set()
            try:
                if self.on_quit:
                    self.on_quit()
            except Exception:
                pass
            # If the wc main loop is blocked in get_key, signal it via a
            # fake keypress on the console input buffer. Fall back to a hard
            # exit only if that fails.
            try:
                import ctypes as _c
                import ctypes.wintypes as _wt
                hIn = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
                inp = (_c.c_ubyte * 28)()
                inp[0] = 0x1B  # KEY_EVENT
                _c.windll.kernel32.WriteConsoleInputW(hIn, inp, 1, None)
            except Exception:
                try:
                    _os._exit(0)
                except Exception:
                    pass


if __name__ == "__main__":
    # tiny self-demo so you can verify the tray without wc:
    #   python wc_tray.py
    t = TrayIcon(tip="wc tray demo")
    if not t.start():
        print("tray not available in this environment")
    else:
        print("tray up — right-click for Show/Hide/Quit, left-click toggles window")
        try:
            t.notify("Hello", "wc tray is alive")
        except Exception:
            pass
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            t.stop()
