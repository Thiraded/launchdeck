"""kc.py — Kill Combo TUI: lists ONLY currently-running works and lets you
kill them. Reads registry.json (written by wc when it launches something) and
verifies each entry is still alive via live process detection.

Keys: Up/Down move | Enter kill | t leave-alone | Esc/q quit
"""
import os
import sys
import time
from pathlib import Path

import wc_core as core

RESET = "\033[0m"
BOLD = "\033[1m"
MAGENTA = "\033[35m"
RED = "\033[31m"
DIM = "\033[2m"
WHITE_ON_BLUE = "\033[44m\033[37m"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def render(running, states, cursor, status):
    clear()
    print(f"{BOLD}  KILL COMBO  -  running works (kill with Enter){RESET}")
    print(f"{DIM}  Up/Down: move   Enter: kill   t: leave-alone   Esc/q: quit{RESET}")
    if status:
        print(f"  {RED}{status}{RESET}")
    print()

    if not running:
        print(f"  {DIM}(nothing running){RESET}")
        print()
        print(f"{DIM}  cursor: 0/0{RESET}")
        return

    for i, item in enumerate(running):
        key = item["id"]
        box = f"{MAGENTA}[-]{RESET}" if states.get(key) != core.LEFT_ALONE else f"{DIM}[.]{RESET}"
        line = f"  {box} {item.get('label', key)}"
        if i == cursor:
            line = f"{WHITE_ON_BLUE}» {box} {item.get('label', key)}{RESET}"
        print(line)

    print()
    print(f"{DIM}  cursor: {cursor + 1}/{len(running)}{RESET}")


def main():
    manifest = core.load_manifest()
    states = {}   # id -> LEFT_ALONE or not
    cursor = 0
    status = ""

    while True:
        running = core.registry_running()
        # drop states for works no longer running
        states = {k: v for k, v in states.items() if any(r["id"] == k for r in running)}
        if cursor >= len(running):
            cursor = max(0, len(running) - 1)

        render(running, states, cursor, status)
        status = ""

        try:
            import msvcrt
            raw = msvcrt.getwch()
            ch = raw.decode("latin-1") if isinstance(raw, bytes) else raw
        except Exception:
            ch = sys.stdin.read(1)

        if ch == "\x1b" or ch in ("q", "Q"):
            break

        if ch in ("\x00", "\xe0"):
            try:
                raw2 = msvcrt.getwch()
                code = raw2.decode("latin-1") if isinstance(raw2, bytes) else raw2
            except Exception:
                code = ""
            if code == "H":
                cursor = (cursor - 1) % max(1, len(running))
            elif code == "P":
                cursor = (cursor + 1) % max(1, len(running))
            continue

        if not running:
            continue

        item = running[cursor]
        wid = item["id"]
        work = core.work_by_id(manifest, wid)

        if ch == "\r" or ch == "\n":  # Enter -> kill
            if states.get(wid) == core.LEFT_ALONE:
                status = f"Skipped (left alone): {item.get('label', wid)}"
            elif work:
                core.kill_work(work)
                status = f"Killed {item.get('label', wid)}"
            time.sleep(0.4)
            continue

        if ch in ("t", "T"):  # leave-alone
            if states.get(wid) == core.LEFT_ALONE:
                states.pop(wid, None)
                status = f"Will kill next time: {item.get('label', wid)}"
            else:
                states[wid] = core.LEFT_ALONE
                status = f"Left alone: {item.get('label', wid)}"
            continue


if __name__ == "__main__":
    main()
