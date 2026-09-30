"""works.json + suite settings + hotkey parsing."""

import json
from pathlib import Path

from deck.core import common, store

MANIFEST = common.HERE / "works.json"
SETTINGS = common.HERE / "launchdeck.settings.txt"


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------
def load_manifest(path: Path = MANIFEST) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {"version": 1, "groups": [], "works": []}
    data.setdefault("groups", [])
    data.setdefault("works", [])
    return data


def work_by_id(manifest: dict, wid: str) -> dict | None:
    for w in manifest["works"]:
        if w.get("id") == wid:
            return w
    return None


def slug_group_id(label, manifest=None):
    """Slugged group id, unique within the manifest's groups."""
    stem = "".join(c.lower() if c.isalnum() else "-" for c in str(label)).strip("-")[:24].strip("-")
    base = ("g-" + stem) if stem else "g-group"
    taken = {g.get("id") for g in (manifest or {}).get("groups", [])}
    gid, n = base, 2
    while gid in taken:
        gid = "g-" + stem + "-" + str(n) if stem else "g-group-" + str(n)
        n += 1
    return gid


def save_manifest(manifest) -> None:
    """Write works.json -- the single writer for editor/group/delete ops.

    Atomic replace: a concurrent load_manifest() (monitor, 3s poll) used to
    hit the truncated file and get an EMPTY manifest back."""
    with store._STATE_LOCK, store._StateMutex():
        store._atomic_write_text(
            MANIFEST, json.dumps(manifest, indent=2, ensure_ascii=False))


_HOTKEY_MODS = {"ctrl": 0x2, "control": 0x2, "alt": 0x1,
                "shift": 0x4, "win": 0x8, "windows": 0x8, "meta": 0x8}


def parse_hotkey(text):
    """Parse 'ctrl+alt+1' -> (mods, vk) for RegisterHotKey, else None.

    Requires at least one modifier (a bare key would hijack normal
    typing). Key: 0-9, a-z, f1-f24.
    """
    parts = [p.strip().lower() for p in str(text or "").split("+")]
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return None
    mods = 0
    for m in parts[:-1]:
        if m not in _HOTKEY_MODS:
            return None
        mods |= _HOTKEY_MODS[m]
    if not mods:
        return None
    key = parts[-1]
    vk = None
    if len(key) == 1 and (key.isdigit() or ("a" <= key <= "z")):
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    if vk is None:
        return None
    return (mods, vk)


def canonical_hotkey(text):
    """Normalized storage form ('Ctrl + Alt + 1' -> 'ctrl+alt+1'), else None."""
    parsed = parse_hotkey(text)
    if not parsed:
        return None
    mods, vk = parsed
    names = []
    for name, bit in (("ctrl", 0x2), ("alt", 0x1), ("shift", 0x4), ("win", 0x8)):
        if mods & bit:
            names.append(name)
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        names.append(chr(vk).lower() if vk >= 0x41 else chr(vk))
    else:
        names.append("f" + str(vk - 0x6F))
    return "+".join(names)


def hotkey_conflicts(manifest, exclude_id=None):
    """key -> sorted work ids sharing it (only entries with 2+ ids)."""
    seen = {}
    for w in (manifest or {}).get("works", []):
        hk = canonical_hotkey(w.get("hotkey", ""))
        if not hk or w.get("id") == exclude_id:
            continue
        seen.setdefault(hk, []).append(w.get("id"))
    return {k: sorted(v) for k, v in seen.items() if len(v) > 1}


DEFAULT_HOTKEY = "alt+w"


def get_settings(manifest=None):
    """Suite settings dict (lives under the manifest's `settings` key)."""
    raw = ((manifest or {}).get("settings", {}) or {})
    return dict(raw) if isinstance(raw, dict) else {}
