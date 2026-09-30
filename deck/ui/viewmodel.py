"""Pure helpers: row view state, editor form mapping, ordering."""

import launchdeck_core as core
from deck.ui import theme


def _swap_adjacent(ids, wid, direction):
    """Move wid one step in an id list; no-op at the edges. Pure."""
    ids = list(ids)
    if wid not in ids:
        return ids
    i, j = ids.index(wid), ids.index(wid) + direction
    if j < 0 or j >= len(ids):
        return ids
    ids[i], ids[j] = ids[j], ids[i]
    return ids

def _unique_id(base, ids):
    """Fresh id off base; never collides (fork-twice guard). Pure."""
    ids = set(ids)
    nid, n = base, 2
    while nid in ids:
        nid = f"{base}-{n}"
        n += 1
    return nid

def _row_view(w, run, pending):
    """Pure view-model for one row (headless-testable, no widgets).

    Returns dict: running, hidden, icon, icon_c, sub, sub_c, dot_c.
    icon is an SVG name (or a legacy emoji, mapped/falls back in widgets).
    """
    wid = w.get("id", "")
    running = wid in run
    icon = w.get("icon") or "zap"
    hidden = core.is_work_hidden(w)
    pend = (pending or {}).get(wid)
    if pend:
        state = pend.get("state", "")
        return {"running": running, "hidden": hidden, "icon": icon,
                "icon_c": theme.TH_ACCENT, "sub": state + "…",
                "sub_c": theme.TH_ACCENT, "dot_c": theme.TH_ACCENT}
    # detached is the only mode: the log button is the window stand-in,
    # so the status word stays short.
    sub = "running" if running else "stopped"
    if hidden:
        sub += "  ·  hidden"
    return {"running": running, "hidden": hidden, "icon": icon,
            "icon_c": theme.TH_GREEN if running else theme.TH_DIM,
            "sub": sub, "sub_c": theme.TH_DIM,
            "dot_c": theme.TH_GREEN if running else theme.TH_FAINT}

def _work_to_form(src, manifest):
    """Prefill values for the task editor when forking src (pure).

    Label gets " copy" so the save path mints a fresh id instead of
    overwriting the source. Group is the editor's display string.
    """
    disp = "(none — standalone)"
    for g in manifest.get("groups", []):
        if src.get("id") in g.get("members", []):
            disp = f"{g.get('label')} [{g.get('id')}]"
            break
    stem = (src.get("label", "") or "") + " copy"
    labels = {w.get("label", "") for w in manifest.get("works", [])}
    label, n = stem, 2
    while label in labels:
        label = f"{stem} {n}"
        n += 1
    return {"label": label,
            "bat": src.get("bat", "") or "",
            "match": str(src.get("match", "") or ""),
            "icon": src.get("icon") or "zap",
            "group": disp,
            "detect": bool(src.get("detect", True)),
            "steps": core.steps_to_text(src.get("steps") or []),
            "vars": core.vars_to_text(src.get("vars") or {})}

def _freeze(value):
    """Stable string for struct comparison (lists/dicts included)."""
    try:
        return repr(value)
    except Exception:
        return ""
