"""wc_core.py — pure logic for the work combo (wc) and kill combo (kc) TUIs.

Key concepts
-----------
* Work Combo (wc): SELECT / RUN. A group has NO state of its own -- its
  selection is the logical OR of its children:
      group selected  <=>  (any child selected)
  So: Space on a group selects all children; Space again clears them;
  clearing any child clears the group too.
* Running state `[-]` is detected live from the process CommandLine (token =
  .bat basename or explicit `match`). It is shown separately from selection.
* Kill Combo (kc): lists ONLY works that are currently running, lets you kill
  them. It relies on a small registry (registry.json) that wc writes when it
  starts something, so kc can find + terminate the right processes quickly.
"""
import json
import os
import subprocess
import time
from pathlib import Path

DESKTOP = Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "Desktop"
if not DESKTOP.exists():
    DESKTOP = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
MANIFEST = DESKTOP / "works.json"
REGISTRY = DESKTOP / "registry.json"

# State tokens (selection column)
OFF = " "   # [ ] not selected
ON = "x"    # [x] selected to run
RUN = "-"   # [-] running (verified alive)
LEFT_ALONE = "_"  # [.] left alone (don't touch on Enter/kill)

HIDDEN_B64 = (
    "UwB0AGEAcgB0AC0AUAByAG8AYwBlAHMAcwAgAGMAbQBkAC4AZQB4AGUAIAAtAEEAcgBnAHUAbQBlAG4AdABM"
    "AGkAcwB0ACAAQAAoACcALwBkACcALAAnAC8AYwAnACwAKAAnACIAJwAgACsAIAAkAGUAbgB2ADoATABDAF8AUwBFAUwARg"
    "AgACsAIAAnACIAIABfAF8AYgBnAF8AXwAnACkAKQAgAC0AVwBpAG4AZABvAHcAUwB0AHkAbABlACAASABpAGQAZABlAG4A"
)


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


# --------------------------------------------------------------------------
# detection
# --------------------------------------------------------------------------
def titles_for(work: dict) -> list[str]:
    """Substrings to match against a running process CommandLine. Prefer an
    explicit `match`, else the .bat basename (our runners spawn a child cmd
    whose CommandLine contains the .bat name). Console `title` is NOT used."""
    m = work.get("match")
    if m:
        return [m] if isinstance(m, str) else [x for x in m if x]
    bat = work.get("bat") or ""
    if bat:
        return [os.path.basename(bat)]
    return []


def kill_tokens_for(work: dict) -> list[str]:
    toks = list(titles_for(work))
    proj = work.get("proj")
    if proj:
        toks.append(proj)
    return toks


def is_running(work: dict) -> bool:
    """True if any live (non-powershell, non-self) process CommandLine contains
    a match token. If `detect` is False we never track running state."""
    if work.get("detect") is False:
        return False
    tokens = titles_for(work)
    if not tokens:
        return False
    ps = (
        "$me = $PID;"
        "$tokens = @('" + "','".join(tokens) + "');"
        "$hit = $false;"
        "foreach ($p in (Get-CimInstance Win32_Process)) {"
        "  if ($p.ProcessId -eq $me) { continue }"
        "  if ($null -eq $p.CommandLine) { continue }"
        "  if ($p.Name -like 'powershell*') { continue }"
        "  foreach ($t in $tokens) {"
        "    if ($p.CommandLine -like \"*$($t)*\") { $hit = $true }"
        "  }"
        "};"
        "if ($hit) { Write-Output 'RUNNING' }"
    )
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=15,
        )
        return "RUNNING" in (r.stdout or "")
    except Exception:
        return False


# --------------------------------------------------------------------------
# run / kill
# --------------------------------------------------------------------------
def run_work(work: dict) -> None:
    """Launch the work's .bat in a VISIBLE terminal window (no hidden
    self-relaunch). Each work opens its own window. Registers it too."""
    bat = work.get("bat")
    if not bat or not os.path.exists(bat):
        return
    # Windows `start` treats the FIRST quoted token as the window title.
    # A single `""` is the title placeholder; the NEXT token is the command.
    # Passing `"" "" "bat"` made the 2nd empty string the command, which
    # `start` resolves to opening the working FOLDER in Explorer (the
    # "Enter opens a folder instead of running" bug). Use exactly one `""`.
    subprocess.Popen(["cmd.exe", "/c", "start", "", bat], shell=False)
    register(work)


def kill_work(work: dict) -> None:
    """Kill processes whose CommandLine contains our match token(s) or proj
    path (covers the console cmd AND child node.exe from npm run dev)."""
    toks = kill_tokens_for(work)
    if not toks:
        return
    ps = (
        "$toks = @('" + "','".join(toks) + "');"
        "foreach ($p in (Get-CimInstance Win32_Process)) {"
        "  if ($null -eq $p.CommandLine) { continue }"
        "  if ($p.Name -like 'powershell*') { continue }"
        "  foreach ($t in $toks) {"
        "    if ($p.CommandLine -like \"*$($t)*\") {"
        "      $p | Invoke-CimMethod -MethodName Terminate -ErrorAction SilentlyContinue | Out-Null"
        "    }"
        "  }"
        "}"
    )
    try:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=20,
        )
    except Exception:
        pass
    unregister(work)


# --------------------------------------------------------------------------
# registry  (so kc can list + kill running works quickly)
# --------------------------------------------------------------------------
def _load_registry() -> dict:
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_registry(data: dict) -> None:
    try:
        REGISTRY.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def register(work: dict) -> None:
    """Record that `work` was launched (with a timestamp)."""
    data = _load_registry()
    data[work["id"]] = {
        "label": work.get("label", work["id"]),
        "bat": work.get("bat", ""),
        "launched": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _save_registry(data)


def unregister(work: dict) -> None:
    data = _load_registry()
    data.pop(work["id"], None)
    _save_registry(data)


def registry_running() -> list[dict]:
    """Return registry entries whose work is actually still running."""
    data = _load_registry()
    out = []
    for wid, info in data.items():
        w = work_by_id(load_manifest(), wid)
        if w and is_running(w):
            out.append({"id": wid, **info})
    return out


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
class Node:
    def __init__(self, key, label, kind, work=None, group_members=None):
        self.key = key
        self.label = label
        self.kind = kind          # 'group' | 'work'
        self.work = work
        self.group_members = group_members or []

    def is_running(self):
        return is_running(self.work) if self.work else False


def build_model(manifest: dict) -> list[Node]:
    nodes = []
    members_of_groups = set()
    for g in manifest.get("groups", []):
        members_of_groups.update(g.get("members", []))
    for g in manifest.get("groups", []):
        nodes.append(Node(g["id"], g["label"], "group",
                          group_members=list(g.get("members", []))))
    for w in manifest.get("works", []):
        if w.get("id") in members_of_groups:
            continue
        nodes.append(Node(w["id"], w["label"], "work", work=w))
    return nodes


def member_nodes(model: list[Node], group: Node) -> list[Node]:
    by_id = {n.key: n for n in model}
    out = []
    manifest = load_manifest()
    work_by_id = {w["id"]: w for w in manifest.get("works", [])}
    for mid in group.group_members:
        if mid in by_id:
            out.append(by_id[mid])
        elif mid in work_by_id:
            out.append(Node(mid, work_by_id[mid].get("label", mid),
                            "work", work=work_by_id[mid]))
    return out


# --------------------------------------------------------------------------
# state machine  (selection only; running is detected live)
# --------------------------------------------------------------------------
def next_on_space(state: str) -> str:
    """Space toggles OFF<->ON; never touches RUN/LEFT_ALONE."""
    if state == OFF:
        return ON
    if state == ON:
        return OFF
    return state


def group_selected(member_states: dict, members: list[Node]) -> bool:
    """A group is selected iff ANY child is selected (pure OR)."""
    return any(member_states.get(m.key) == ON for m in members)


def set_group_selection(states: dict, members: list[Node], value: str) -> None:
    for m in members:
        if value == ON:
            if states.get(m.key) != RUN:
                states[m.key] = ON
        else:  # clear
            if states.get(m.key) == ON:
                states[m.key] = OFF


def enter_action(state: str, node: Node, model: list[Node], states: dict | None = None):
    """Return list of (action, work) to run/kill. Group acts on its members."""
    if states is None:
        states = {}
    if node.kind == "group":
        members = member_nodes(model, node)
        if state == ON:
            acts = [("run", m.work) for m in members if not m.is_running()]
            return acts
        if state == RUN:
            acts = [("kill", m.work) for m in members
                    if m.is_running() and states.get(m.key) != LEFT_ALONE]
            return acts
        return []
    # work node
    if state == ON and not node.is_running():
        return [("run", node.work)]
    if state == RUN:
        return [("kill", node.work)]
    return []


def recompute_states(model: list[Node], states: dict) -> None:
    """Recompute RUN (detected) + group selection (OR of children).
    Selection of a child is preserved; groups are always derived."""
    # 1) mark running children
    for n in model:
        if n.kind != "group":
            continue
        members = member_nodes(model, n)
        for m in members:
            if m.is_running() and states.get(m.key) != LEFT_ALONE:
                states[m.key] = RUN
            elif states.get(m.key) == RUN and not m.is_running():
                states[m.key] = OFF
    # 2) derive group selection from children (pure OR)
    for n in model:
        if n.kind == "group":
            members = member_nodes(model, n)
            if group_selected(states, members):
                states[n.key] = ON
            else:
                states[n.key] = OFF
