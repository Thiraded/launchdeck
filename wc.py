"""wc.py — Work Combo (wc) TUI: the ONE tool to manage your works.

It is BOTH a launcher and a killer (kc was merged in here):

    [ ] Hamster-Server start
    [X] OmniRoute CLI start          <- selected (Space), will be acted on
       [-]                            <- actually running right now (info)

Keys:
  Up/Down  : move cursor
  Space    : toggle select [ ] <-> [X]   (mark what you want to act on)
  Enter    : ACT on every [X] node --
               * if it is running  [-]  -> KILL it (window closes)
               * if not running        -> LAUNCH it (opens its own window)
  h        : HIDE / SHOW the cursor's work terminal window
               (cursor on a [-] work -> hide it; cursor on the same again
                or any other work -> toggle; never touches the wc window)
  t        : leave-alone (skip on Enter)   [reserved]
  Esc / q  : quit

The [-] marker is LIVE (refreshed by a background thread, never blocks keys).
It is info only -- you cannot "cancel" it by keypress; to stop a running work
you select it [X] and press Enter (which kills the whole process tree AND
closes the visible window).

Selection is remembered in wc.settings.txt (loaded on start / saved on quit).
"""
import os
import sys
import threading
import time
from pathlib import Path

import wc_core as core

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
WHITE_ON_BLUE = "\033[44m\033[37m"

# Live running snapshots (id set) so the screen can show [-] markers without
# blocking the key loop. A background thread refreshes it every 2s.
_running_cache = set()
_running_lock = threading.Lock()


def _refresh_running_loop(manifest):
    global _running_cache
    while True:
        try:
            commandlines = core.scan_commandlines()
            s = {
                w["id"] for w in manifest.get("works", [])
                if w.get("detect") is not False
                and core.is_running(w, commandlines)
            }
        except Exception:
            s = set()
        with _running_lock:
            _running_cache = s
        time.sleep(2.0)


def start_running_monitor(manifest):
    t = threading.Thread(target=_refresh_running_loop, args=(manifest,), daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Per-work window hide/show. `h` on a [-] work hides that work's terminal
# (the cmd / bat / npx window the user is staring at). Press `h` again to
# bring it back. The wc window itself is NEVER touched by this.
# `h` MINIMIZES the work's window to the taskbar (like a normal app that
# runs in the background), not full hide. The user can click the taskbar
# icon to bring it back. This is what "background" feels like for a
# desktop app.
# ---------------------------------------------------------------------------
_minimized_hwnds: dict[str, list[int]] = {}  # work_key -> list of HWNDs we've minimized
SW_SHOWMINIMIZED = 2
SW_SHOWNOACTIVATE = 4
SW_RESTORE = 9


def _minimize_restore_work(work_key: str, hwnds: list[int], mode: int) -> int:
    """Minimize or restore a list of HWNDs. Returns the count of windows
    that actually changed state. Uses ShowWindowAsync so we don't deadlock
    if the owning thread is the one calling us."""
    if not hwnds:
        return 0
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.ShowWindowAsync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.ShowWindowAsync.restype = ctypes.c_int
    except Exception:
        return 0
    changed = 0
    for h in hwnds:
        try:
            if user32.ShowWindowAsync(h, mode):
                changed += 1
        except Exception:
            pass
    return changed


def toggle_work_window(node) -> str:
    """Minimize the cursor's work terminal to the taskbar (background);
    restore it if already minimized. Returns a human-readable status."""
    if node.kind != "work" or not node.work:
        return "h works on a running work line (cursor on [-])"
    if not node.is_running():
        return f"'{node.label}' is not running -- nothing to minimize"
    hwnds = core.find_work_hwnds(node.work)
    if not hwnds:
        return f"'{node.label}' is running but its window was not found"
    key = node.key
    if key in _minimized_hwnds and _minimized_hwnds[key]:
        # Currently minimized -> restore
        n = _minimize_restore_work(key, _minimized_hwnds.pop(key), SW_RESTORE)
        return f"Restored '{node.label}' ({n} window)"
    # Currently visible (or first time) -> minimize to taskbar
    n = _minimize_restore_work(key, hwnds, SW_SHOWMINIMIZED)
    if n:
        _minimized_hwnds[key] = hwnds
        return f"Minimized '{node.label}' to taskbar (h again to restore)"
    return f"Could not minimize '{node.label}'"


def is_node_running(n) -> bool:
    """True if node `n` is a work node currently detected as running (live)."""
    if not n.work:
        return False
    with _running_lock:
        return n.key in _running_cache


def state_box(s: str, running: bool = False) -> str:
    # [X] = selected to act on (Space toggles); [-] = running (info only).
    box = f"{GREEN}[X]{RESET}" if s == core.ON else f"{DIM}[ ]{RESET}"
    if running:
        box += f" {MAGENTA}[-]{RESET}"
    return box


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def flatten(model):
    rows = []
    for n in model:
        if n.kind == "group":
            rows.append((n, ""))
            for m in core.member_nodes(model, n):
                rows.append((m, "   "))
        else:
            rows.append((n, ""))
    return rows


def render(model, states, cursor, status):
    clear()
    print(f"{BOLD}  WORK COMBO  -  manage works (launch / kill){RESET}")
    print(f"{DIM}  [X]=select(Space)  [-]=running  Enter: kill[-]/launch  h: minimize work to taskbar  Esc/q: quit{RESET}")
    if status:
        print(f"  {YELLOW}{status}{RESET}")
    print()

    rows = flatten(model)
    for i, (n, indent) in enumerate(rows):
        box = state_box(states.get(n.key, core.OFF), is_node_running(n))
        line = f"  {indent}{box} {n.label}"
        if i == cursor:
            line = f"{WHITE_ON_BLUE}» {indent}{box} {n.label}{RESET}"
        print(line)

    print()
    print(f"{DIM}  cursor: {cursor + 1}/{len(rows)}{RESET}")


def load_states_from_preset(model):
    p = core.DESKTOP / "wc.settings.txt"
    sel = set()
    if p.exists():
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                s = line.strip()
                if s:
                    sel.add(s.lower())
        except Exception:
            pass
    states = {}
    for n in model:
        if n.kind == "group":
            continue
        if n.key.lower() in sel:
            states[n.key] = core.ON
        else:
            states[n.key] = core.OFF
    core.recompute_states(model, states)
    return states


def save_preset(model, states):
    p = core.DESKTOP / "wc.settings.txt"
    lines = [n.key for n in model if states.get(n.key) == core.ON]
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _disable_quickedit():
    """Turn OFF console QuickEdit mode. When QuickEdit is ON, a mouse click
    inside the console window PAUSES keyboard input (the window waits for a
    select/copy) -- which looks exactly like 'keys do nothing'. Disabling it
    keeps the window always accepting keys."""
    try:
        import msvcrt
        kernel32 = __import__("ctypes").windll.kernel32
        h = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        ENABLE_PROCESSED_INPUT = 0x0001
        ENABLE_LINE_INPUT = 0x0002
        ENABLE_ECHO_INPUT = 0x0004
        ENABLE_MOUSE_INPUT = 0x0010
        ENABLE_QUICK_EDIT = 0x0040
        # Keep processed/line/echo; drop mouse + quickedit so clicks don't
        # hijack the keyboard.
        new_mode = (ENABLE_PROCESSED_INPUT | ENABLE_LINE_INPUT | ENABLE_ECHO_INPUT)
        kernel32.SetConsoleMode(h, new_mode)
    except Exception:
        pass


def get_key() -> str:
    """Read one key via ReadConsoleInput (ctypes). This reads the real console
    INPUT buffer directly -- it is NOT affected by QuickEdit mode and works even
    when msvcrt.getch()/getwch() misbehave (e.g. bat-spawned windows). Returns a
    normalized token: ' ' (space), '\\r' (Enter), '\\x1b' (Esc), 'UP'/'DOWN', or
    the raw char. Falls back to stdin if no real console is attached."""
    try:
        import ctypes
        from ctypes import wintypes, Structure, c_ulong, c_ushort, c_short, c_wchar, c_int
        kernel32 = ctypes.windll.kernel32

        class KEY_EVENT_RECORD(Structure):
            _fields_ = [
                ("bKeyDown", c_int),
                ("wRepeatCount", c_ushort),
                ("wVirtualKeyCode", c_ushort),
                ("wVirtualScanCode", c_ushort),
                ("uChar", c_wchar),
                ("dwControlKeyState", c_ulong),
            ]

        class INPUT_RECORD(Structure):
            _fields_ = [("EventType", c_ushort), ("KeyEvent", KEY_EVENT_RECORD)]

        VK_CODE = {0x20: " ", 0x0D: "\r", 0x1B: "\x1b",
                   0x26: "UP", 0x28: "DOWN", 0x51: "q", 0x54: "t"}
        hIn = kernel32.GetStdHandle(-10)
        rec = INPUT_RECORD()
        nread = c_ulong(0)
        while True:
            got = kernel32.ReadConsoleInputW(hIn, ctypes.byref(rec), 1, ctypes.byref(nread))
            if got and nread.value == 1:
                if rec.EventType == 1 and rec.KeyEvent.bKeyDown:  # KEY_EVENT down
                    vk = rec.KeyEvent.wVirtualKeyCode
                    ch = rec.KeyEvent.uChar
                    if vk in VK_CODE:
                        return VK_CODE[vk]
                    if ch and ch != "\x00":
                        return ch
                # key-up or other event -> keep draining the buffer
                continue
            # No event ready: brief yield so we don't busy-spin. We do NOT fall
            # back to stdin here (stdin blocks forever in a real console app).
            time.sleep(0.02)
    except Exception:
        # last-resort fallback
        try:
            import msvcrt
            raw = msvcrt.getch()
            b = raw if isinstance(raw, bytes) else raw.encode("latin-1")
            if b in (b"\x00", b"\xe0"):
                try:
                    b2 = msvcrt.getch()
                    b2 = b2 if isinstance(b2, bytes) else b2.encode("latin-1")
                except Exception:
                    b2 = b""
                if b2 == b"H":
                    return "UP"
                if b2 == b"P":
                    return "DOWN"
                return ""
            return b.decode("latin-1")
        except Exception:
            try:
                return sys.stdin.read(1)
            except Exception:
                return ""


def selected_works(model, states) -> list:
    """All work nodes that are ON, expanded through groups."""
    out = []
    for n in model:
        if n.kind == "group":
            for m in core.member_nodes(model, n):
                if states.get(m.key) == core.ON:
                    out.append(m)
        else:
            if states.get(n.key) == core.ON:
                out.append(n)
    seen, uniq = set(), []
    for node in out:
        if node.key not in seen:
            seen.add(node.key)
            uniq.append(node)
    return uniq


def act_on_selected(model, states):
    """Enter handler: for every [X] node, KILL if running else LAUNCH.
    Returns a human-readable status string.

    Decision rule: trust the live [-] cache (what the user SEES) first. If the
    background monitor flagged this node as running, KILL it. Only if the cache
    says not-running do we do a fresh scan -- and even then, if the fresh scan
    disagrees we believe the cache, because a failed/empty scan must never turn
    a 'kill' into an accidental 'launch'."""
    sel = selected_works(model, states)
    if not sel:
        return "Nothing selected -- Space to select, then Enter"
    # Snapshot the live-running set the user is looking at.
    with _running_lock:
        running_set = set(_running_cache)
    killed, launched = [], []
    for node in sel:
        if not node.work:
            continue
        w = node.work
        is_run = node.key in running_set or core.is_running(w)
        if is_run:
            core.kill_work(w)
            killed.append(w.get("label", w["id"]))
        else:
            core.launch_work(w)
            launched.append(w.get("label", w["id"]))
    parts = []
    if killed:
        parts.append(f"Killed: {', '.join(killed)}")
    if launched:
        parts.append(f"Launched: {', '.join(launched)}")
    return " | ".join(parts) if parts else "Nothing to do"


def main():
    _disable_quickedit()  # so mouse clicks don't freeze keyboard input
    manifest = core.load_manifest()
    model = core.build_model(manifest)
    if not model:
        print("No works defined in works.json")
        time.sleep(2)
        return
    states = load_states_from_preset(model)

    # Live-running monitor in the background (does NOT block keys).
    start_running_monitor(manifest)

    rows = flatten(model)
    cursor = 0
    status = ""
    while True:
        render(model, states, cursor, status)
        status = ""

        ch = get_key()
        if ch in ("\x1b", "q", "Q"):
            try:
                save_preset(model, states)
            except Exception:
                pass
            return

        if ch == "h" or ch == "H":
            # Hide / show the cursor's WORK terminal window (not wc).
            node = rows[cursor][0]
            status = toggle_work_window(node)
            continue

        if ch == "UP":
            cursor = (cursor - 1) % len(rows)
            continue
        if ch == "DOWN":
            cursor = (cursor + 1) % len(rows)
            continue

        node = rows[cursor][0]

        if ch == " " or ch in ("t", "T"):  # Space OR 't' toggles selection
            key = node.key
            if node.kind == "group":
                members = core.member_nodes(model, node)
                if core.group_selected(states, members):
                    core.set_group_selection(states, members, core.OFF)
                else:
                    core.set_group_selection(states, members, core.ON)
            else:
                states[key] = core.next_on_space(states.get(key, core.OFF))
            continue

        if ch in ("\r", "\n", "\x0d", "\x0a"):  # Enter (any form) -> kill running / launch not-running
            status = act_on_selected(model, states)
            time.sleep(0.4)
            continue


if __name__ == "__main__":
    main()
