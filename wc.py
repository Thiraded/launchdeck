"""work.py — Work Combo (wc) TUI: SELECT / RUN works in an inline tree.

    [ ] Hamster combo
       [ ] Hamster-Server start
       [ ] Hamster-Clint start
       [ ] Hamsterquest start
    ...

Rules:
  * A group has no state of its own: it shows [x] iff any child is [x]
    (pure OR). Space on a group toggles ALL its children; clearing any
    child clears the group.
  * [-] means the work is detected as actually running (live process check).
  * Enter on [x] runs it; Enter on [-] kills it. Enter on a group does the
    same for every member.

Keys: Up/Down move | Space/t select | Enter run/kill | Esc/q quit
"""
import os
import sys
import time
from pathlib import Path

import wc_core as core

RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
MAGENTA = "\033[35m"
DIM = "\033[2m"
WHITE_ON_BLUE = "\033[44m\033[37m"


def state_box(s: str) -> str:
    if s == core.ON:
        return f"{GREEN}[x]{RESET}"
    if s == core.RUN:
        return f"{MAGENTA}[-]{RESET}"
    if s == core.LEFT_ALONE:
        return f"{DIM}[.]{RESET}"
    return f"{DIM}[ ]{RESET}"


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
    print(f"{BOLD}  WORK COMBO  -  select & start works{RESET}")
    print(f"{DIM}  Up/Down: move   Space/t: select   Enter: run/kill   Esc/q: quit{RESET}")
    if status:
        print(f"  {MAGENTA}{status}{RESET}")
    print()

    rows = flatten(model)
    for i, (n, indent) in enumerate(rows):
        box = state_box(states.get(n.key, core.OFF))
        line = f"  {indent}{box} {n.label}"
        if i == cursor:
            line = f"{WHITE_ON_BLUE}» {indent}{box} {n.label}{RESET}"
        print(line)

    print()
    print(f"{DIM}  cursor: {cursor + 1}/{len(rows)}{RESET}")


def load_states_from_preset(model):
    manifest = core.load_manifest()
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
    all_ids = [g["id"] for g in manifest.get("groups", [])] + \
              [w["id"] for w in manifest.get("works", [])]
    states = {}
    for wid in all_ids:
        if wid.lower() in sel:
            states[wid] = core.ON
        else:
            node = next((n for n in model if n.key == wid), None)
            work = node.work if node else None
            states[wid] = core.RUN if (work and core.is_running(work)) else core.OFF
    return states


def save_preset(model, states):
    p = core.DESKTOP / "wc.settings.txt"
    lines = [n.key for n in model if states.get(n.key) == core.ON]
    p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main():
    manifest = core.load_manifest()
    model = core.build_model(manifest)
    if not model:
        print("No works defined in works.json")
        time.sleep(2)
        return
    states = load_states_from_preset(model)
    core.recompute_states(model, states)

    rows = flatten(model)
    cursor = 0
    status = ""

    while True:
        render(model, states, cursor, status)
        status = ""

        try:
            import msvcrt
            raw = msvcrt.getwch()
            ch = raw.decode("latin-1") if isinstance(raw, bytes) else raw
        except Exception:
            ch = sys.stdin.read(1)

        if ch == "\x1b" or ch in ("q", "Q"):
            break

        # Arrow keys: 0x00 or 0xE0 + code
        if ch in ("\x00", "\xe0"):
            try:
                raw2 = msvcrt.getwch()
                code = raw2.decode("latin-1") if isinstance(raw2, bytes) else raw2
            except Exception:
                code = ""
            if code == "H":   # Up
                cursor = (cursor - 1) % len(rows)
            elif code == "P":  # Down
                cursor = (cursor + 1) % len(rows)
            continue

        node = rows[cursor][0]

        if ch == "\r" or ch == "\n":  # Enter
            acts = core.enter_action(states.get(node.key, core.OFF), node, model, states)
            for action, work in acts:
                if action == "run":
                    core.run_work(work)
                    status = f"Started {work.get('label', '?')}"
                elif action == "kill":
                    core.kill_work(work)
                    status = f"Stopped {work.get('label', '?')}"
            core.recompute_states(model, states)
            time.sleep(0.4)
            continue

        if ch == " " or ch in ("t", "T"):  # Space OR 't' ("tap") toggle select
            key = node.key
            if node.kind == "group":
                members = core.member_nodes(model, node)
                if core.group_selected(states, members):
                    # clear all children
                    core.set_group_selection(states, members, core.OFF)
                else:
                    # select all children
                    core.set_group_selection(states, members, core.ON)
            else:
                states[key] = core.next_on_space(states.get(key, core.OFF))
            continue

    try:
        save_preset(model, states)
    except Exception:
        pass


if __name__ == "__main__":
    main()
