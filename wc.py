"""work.py — Work Combo (wc) TUI: SELECT works, then RUN them.

    [ ] Hamster combo
       [ ] Hamster-Server start
       [ ] Hamster-Clint start
       [ ] Hamsterquest start
    ...

wc is a PURE LAUNCHER now. No running/kill logic lives here (that's kc's
job). On Enter it spawns every selected work in its OWN visible window, shows
per-terminal progress (running -> building -> ready/stable/done), and then
CLOSES ITSELF once everything has settled. If any work reports an error, wc
stays open and shows it until you quit (Esc/q).

Rules:
  * A group has no state of its own: it shows [x] iff any child is [x] (OR).
    Space on a group toggles ALL its children; clearing any child clears it.
  * Selection is remembered in wc.settings.txt (loaded on start / saved on quit).

Keys: Up/Down move | Space/t select | Enter run | Esc/q quit
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
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
WHITE_ON_BLUE = "\033[44m\033[37m"

# status -> (label, color)
STATUS_UI = {
    "starting": ("starting...", YELLOW),
    "running":  ("running / building", YELLOW),
    "ready":    ("ready", GREEN),
    "stable":   ("running (stable)", GREEN),
    "done":     ("done", GREEN),
    "failed":   ("FAILED", RED),
}


def state_box(s: str) -> str:
    if s == core.ON:
        return f"{GREEN}[x]{RESET}"
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
    print(f"{BOLD}  WORK COMBO  -  select & launch works{RESET}")
    print(f"{DIM}  Up/Down: move   Space/t: select   Enter: run   Esc/q: quit{RESET}")
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


def render_progress(recs, manifest):
    clear()
    print(f"{BOLD}  WORK COMBO  -  launching...{RESET}")
    print(f"{DIM}  (wc closes itself when all works settle; Esc/q to abort & stay){RESET}")
    print()
    work_by_id = {w["id"]: w for w in manifest.get("works", [])}
    any_failed = False
    all_settled = True
    for rec in recs:
        if rec.get("_missing"):
            st, detail = "failed", "bat not found"
        else:
            st, detail = core.poll_launch(rec, work_by_id.get(rec["id"]))
        label, color = STATUS_UI.get(st, (st, DIM))
        if st == "failed":
            any_failed = True
        if st not in core.SETTLED:
            all_settled = False
        tail = f"  {DIM}{detail}{RESET}" if detail else ""
        print(f"  {color}{label}{RESET}  {rec['label']}{tail}")
    print()
    if any_failed:
        print(f"{RED}  Some works reported an error — wc stays open.{RESET}")
        print(f"{DIM}  check each work's own log (works.json -> 'log'){RESET}")
    elif all_settled:
        print(f"{GREEN}  All works settled. Closing wc...{RESET}")
    else:
        print(f"{DIM}  waiting for works to settle...{RESET}")
    return any_failed, all_settled


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


def get_key() -> str:
    try:
        import msvcrt
        raw = msvcrt.getwch()
        ch = raw.decode("latin-1") if isinstance(raw, bytes) else raw
    except Exception:
        ch = sys.stdin.read(1)
    return ch


def read_arrow(ch: str):
    """If ch is an arrow prefix, read the follow-up code. Returns 'UP'/'DOWN'/None."""
    if ch in ("\x00", "\xe0"):
        try:
            import msvcrt
            raw2 = msvcrt.getwch()
            code = raw2.decode("latin-1") if isinstance(raw2, bytes) else raw2
        except Exception:
            code = ""
        if code == "H":
            return "UP"
        if code == "P":
            return "DOWN"
    return None


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
    # dedupe (a work could be ON and also under a selected group)
    seen, uniq = set(), []
    for node in out:
        if node.key not in seen:
            seen.add(node.key)
            uniq.append(node)
    return uniq


def main():
    manifest = core.load_manifest()
    model = core.build_model(manifest)
    if not model:
        print("No works defined in works.json")
        time.sleep(2)
        return
    states = load_states_from_preset(model)

    # ---- SELECT phase -------------------------------------------------
    rows = flatten(model)
    cursor = 0
    status = ""
    while True:
        render(model, states, cursor, status)
        status = ""

        ch = get_key()
        if ch == "\x1b" or ch in ("q", "Q"):
            try:
                save_preset(model, states)
            except Exception:
                pass
            return

        arrow = read_arrow(ch)
        if arrow == "UP":
            cursor = (cursor - 1) % len(rows)
            continue
        if arrow == "DOWN":
            cursor = (cursor + 1) % len(rows)
            continue

        node = rows[cursor][0]

        if ch == " " or ch in ("t", "T"):  # Space OR 't' ("tap") toggle select
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

        if ch == "\r" or ch == "\n":  # Enter -> run selected
            sel = selected_works(model, states)
            if not sel:
                status = "Nothing selected — Space to select, then Enter"
                continue
            try:
                save_preset(model, states)
            except Exception:
                pass
            run_phase(sel, manifest)
            # after run_phase returns, we're done launching; quit wc.
            return


def run_phase(sel, manifest):
    """Spawn every selected work in its own window, show progress, then
    auto-close wc. SAFETY: the monitor loop is bounded by a hard deadline
    (STABLE_MAX_SECONDS + slack) so wc can never hang the machine. If a work
    errored, we show it for up to FAILED_VIEW_SECONDS then close anyway."""
    from wc_core import STABLE_MAX_SECONDS

    recs = []
    for node in sel:
        if node.work:
            rec = core.launch_work(node.work)
            if rec:
                recs.append(rec)
            # missing .bat -> launch_work returned None; record as failed
            else:
                recs.append({
                    "id": node.key, "label": node.label, "work": node.work,
                    "launched": time.time(), "already": False, "_missing": True,
                })
    if not recs:
        return

    work_by_id = {w["id"]: w for w in manifest.get("works", [])}

    # --- monitor loop: bounded hard stop (no infinity loops) ---
    MONITOR_SECONDS = STABLE_MAX_SECONDS + 20   # total ceiling for monitoring
    FAILED_VIEW_SECONDS = 20                    # show errors this long, then exit
    start = time.time()
    failed_since = None
    while True:
        any_failed, all_settled = render_progress(recs, manifest)
        if any_failed and failed_since is None:
            failed_since = time.time()
        elapsed = time.time() - start
        if all_settled:
            time.sleep(0.6)          # brief "all settled" flash, then close
            break
        if failed_since is not None and (time.time() - failed_since) >= FAILED_VIEW_SECONDS:
            break
        if elapsed >= MONITOR_SECONDS:
            break
        time.sleep(1.0)
    # wc returns -> main() exits -> the window closes. (On error we showed it
    # for FAILED_VIEW_SECONDS; on timeout we close rather than hang forever.)


if __name__ == "__main__":
    main()
