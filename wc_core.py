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
import re
import subprocess
import threading
import time
from pathlib import Path

# Background subprocesses (powershell scans, taskkill) must not flash a
# console window when wc runs under pythonw (wctray has no console to
# inherit, so Windows pops a visible terminal on EVERY scan otherwise).
# Works launched via run_work() are EXCLUDED -- those must stay VISIBLE.
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

HERE = Path(__file__).resolve().parent
# Legacy location (before 2026-09-05 the suite lived on the Desktop).
DESKTOP = Path(os.environ.get("USERPROFILE", "")) / "OneDrive" / "Desktop"
if not DESKTOP.exists():
    DESKTOP = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
MANIFEST = HERE / "works.json"
REGISTRY = HERE / "registry.json"
SETTINGS = HERE / "wc.settings.txt"

# Optional speed helper (pure-stdlib Go, built from gowc/): when gowc.exe sits
# next to this file, scans/kills go through it (~0.2s vs ~0.9s per spawn).
# Absent -> identical powershell fallbacks. Never a hard dependency.
_GOWC = HERE / "gowc.exe"


def _gowc_available() -> bool:
    try:
        return os.path.isfile(_GOWC)
    except Exception:
        return False


# Process names that are NEVER valid kill/hide seeds, even on token match
# (a token can hide in a browser tab URL or chat content -- 2026-09-05 the
# token 'omniroute' matched the user's Brave PID 4524). One shared set for
# kill_work + find_work_hwnds (was copy-pasted in two PowerShell blobs).
_NEVER_SEED_GUI = frozenset({
    "brave.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe",
    "vivaldi.exe", "arc.exe", "explorer.exe", "discord.exe", "slack.exe",
    "teams.exe",
})

# The manifest most recently used to build the model. member_nodes() reads
# works from HERE (not from disk) so group membership is consistent with the
# tree wc/kc actually render. Set by build_model().
_CURRENT_MANIFEST = None

# State tokens (selection column)
OFF = " "   # [ ] not selected
ON = "x"    # [x] selected to run
RUN = "-"   # [-] running (verified alive)
LEFT_ALONE = "_"  # [.] left alone (don't touch on Enter/kill)


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
    """Match tokens to kill a work's process tree. Beyond `match` and the bat
    basename (titles_for), we also include a low-cardinality token derived
    from the work id so the outer `cmd /K "bat.bat"` wrapper is reachable
    even when it has no match token of its own (e.g. GPT MCP's wrapper
    CommandLine is just `cmd /K "GPT MCP.bat`)."""
    toks = list(titles_for(work))
    proj = work.get("proj")
    if proj:
        toks.append(proj)
    # Always add a token that the outer wrapper is GUARANTEED to contain
    # (the bat basename, or the work id if no bat). This makes the
    # outermost `cmd /K "bat.bat"` (the one whose window the user sees)
    # a seed so the tree walk includes it.
    bat = work.get("bat") or ""
    if bat:
        bn = os.path.basename(bat)
        if bn and bn not in toks:
            toks.append(bn)
    wid = work.get("id") or ""
    # Auto-adding the bare work id is a guess for reaching the outer
    # `cmd /K "bat.bat"` wrapper -- but a short id (e.g. "a") matches the
    # whole machine as a kill token (2026-09-05 incident). Only add it
    # when it is specific enough to be safe.
    if wid and wid not in toks and len(wid) >= 4:
        toks.append(wid)
    # Steps-works run a generated .bat (materialize_steps): its wrapper
    # CommandLine carries the gen name, so seed it exactly like a .bat
    # basename (deterministic -- computable here without launching).
    if work.get("steps"):
        gen = gen_bat_name(work)
        if gen not in toks:
            toks.append(gen)
    return toks


def scan_table() -> list[tuple[int, int, str, str]]:
    """Full process table as (pid, ppid, name, cmdline) rows -- the ONE data
    source every consumer shares. gowc.exe scan when present (~0.2s), else
    ONE powershell dump (~0.9s). Previously each consumer spawned its own
    scan (find_work_hwnds alone did 3 = ~2.7s). No rows are excluded here;
    each consumer applies its own filters (powershell*, protected, ...)."""
    rows = _scan_table_gowc()
    if rows is None:
        rows = _scan_table_ps()
    return rows


def _parse_table_rows(text: str) -> list[tuple[int, int, str, str]]:
    out: list[tuple[int, int, str, str]] = []
    for line in (text or "").splitlines():
        parts = line.split("|", 3)
        if len(parts) != 4 or not parts[0].strip().isdigit():
            continue
        try:
            ppid = int(parts[1].strip())
        except Exception:
            ppid = 0
        out.append((int(parts[0].strip()), ppid,
                    parts[2].strip(), parts[3]))
    return out


def _scan_table_gowc() -> list[tuple[int, int, str, str]] | None:
    """Fast path via gowc.exe; None when unavailable or failed (fallback)."""
    if not _gowc_available():
        return None
    try:
        r = subprocess.run(
            [str(_GOWC), "scan"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            creationflags=_NO_WINDOW,
        )
        if r.returncode != 0:
            return None
        return _parse_table_rows(r.stdout)
    except Exception:
        return None


def _scan_table_ps() -> list[tuple[int, int, str, str]]:
    """Fallback: the same table from ONE powershell dump."""
    ps = ("foreach ($p in (Get-CimInstance Win32_Process)) { " +
          "Write-Output ($p.ProcessId.ToString() + '|' + " +
          "$p.ParentProcessId.ToString() + '|' + $p.Name + '|' + " +
          "$p.CommandLine) }")
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive",
             "-Command", ps],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
            creationflags=_NO_WINDOW,
        )
        return _parse_table_rows(r.stdout)
    except Exception:
        return []


def scan_commandlines() -> list[str]:
    """Return the CommandLine of every live non-powershell process in ONE
    shared scan. Call this once and reuse the list for many is_running checks
    instead of scanning per work (that's what made kc lag). Now a projection
    over scan_table (gowc-accelerated when present)."""
    return [cmd for (_pid, _pp, name, cmd) in scan_table()
            if cmd and not (name or "").lower().startswith("powershell")]


def is_running(work: dict, commandlines: list[str] | None = None) -> bool:
    """True if any live (non-powershell, non-self) process CommandLine contains
    a match token. If `detect` is False we never track running state. Pass a
    pre-scanned `commandlines` list (from scan_commandlines) to avoid spawning
    a powershell per call."""
    if work.get("detect") is False:
        return False
    tokens = titles_for(work)
    if not tokens:
        return False
    if commandlines is None:
        commandlines = scan_commandlines()
    toks_low = [t.lower() for t in tokens]
    for line in commandlines:
        low = line.lower()
        for t in toks_low:
            if t and t in low:
                return True
    return False


# --------------------------------------------------------------------------
# run / kill
# --------------------------------------------------------------------------
def work_log_path(work: dict) -> str:
    """Log file for a detached work (docker-logs equivalent). Under
    wc_logs/ (git-ignored). Created on first detached launch."""
    wid = work.get("id", "work")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in wid)
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wc_logs")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, safe + ".log")


def work_display_log_path(work: dict) -> str:
    """Log file the viewer tails for a detached work.

    A work with its own `"log"` key (e.g. omniroute-cli, whose .bat
    redirects to `%LOCALAPPDATA%\\bg-launcher-logs\\...`) shows THAT file;
    everyone else shows the per-launch `wc_logs/<id>.log`. Only wc_logs
    files are truncated on Start -- external logs are owned by their app.
    """
    own = work.get("log")
    if own:
        return os.path.expandvars(str(own))
    return work_log_path(work)


GEN_BAT_PREFIX = "wc-gen-"


def work_vars(work: dict) -> dict:
    """`vars` mapping for a steps-work (NAME -> value, both strings)."""
    raw = work.get("vars") or {}
    return {str(k): str(v) for k, v in raw.items() if str(k).strip()}


_VAR_RE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")


def expand_work_vars(text: str, work: dict) -> str:
    """Expand %NAME% from the work's `vars`, then process environ.

    Nested refs resolve recursively (a var value may itself contain
    %REFS%, e.g. OLOG built on LOGDIR built on %LOCALAPPDATA%), with a
    cycle guard that leaves circular refs intact. Unknown names are
    left intact (cmd.exe gets its own chance at them at runtime).
    Precedence is vars-first: a var shadows the process environ.
    Used for previews/tests -- execution relies on `set` lines in the
    generated .bat instead (single expansion, no doubles).
    """
    vs = work_vars(work)

    def _resolve(name, seen):
        if name in seen:
            return "%" + name + "%"
        if name in vs:
            return _VAR_RE.sub(lambda m: _resolve(m.group(1), seen | {name}),
                               vs[name])
        return os.environ.get(name, "%" + name + "%")

    return _VAR_RE.sub(lambda m: _resolve(m.group(1), frozenset()),
                       str(text))


def gen_bat_name(work: dict) -> str:
    """Deterministic generated-.bat basename for a steps-work."""
    wid = work.get("id", "work")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in wid)
    return GEN_BAT_PREFIX + safe + ".bat"


def materialize_steps(work: dict, visible: bool = False) -> str:
    """Write `wc_logs/wc-gen-<id>.bat` from `steps`+`vars`; return its path.

    The generated file follows the inline launcher shape (title early,
    `set` lines, terminal steps as sequential lines, `app:` steps via
    `start ""`). Terminal steps run PLAIN in detached mode (no window
    to keep open); in visible mode the LAST terminal step is wrapped
    in `cmd /k` (mirrors the template). CRLF, like hand-written bats.
    """
    steps = work.get("steps") or []
    label = work.get("label", work.get("id", "work"))
    # NO `setlocal` here -- on purpose (2026-09-06 trap): npm.cmd ends
    # with `goto` to a nonexistent label, and that failed-goto unwinds
    # the whole setlocal stack, reverting cwd to the pre-cd directory
    # before node spawns (proven: identical bat +/- setlocal = works /
    # ENOENT at the launcher dir). Hand bats are immune only because
    # they run npm under `cmd /k` (fresh child cmd). Vars leaking into
    # our own throwaway wrapper is harmless.
    lines = ["@echo off"]
    # Values are pre-expanded here (nested refs resolved once): cmd.exe
    # expands %REFS% single-pass at runtime, so a stored value like
    # %LOGDIR% inside OLOG would otherwise survive literally.
    for k, v in work_vars(work).items():
        lines.append("set " + chr(34) + k + "=" + expand_work_vars(v, work) + chr(34))
    lines.append(f"title {label}")
    terms = [s for s in steps if (s.get("type") or "terminal") == "terminal"]
    last_term = terms[-1] if terms else None
    for s in steps:
        cmd = str(s.get("cmd", "")).strip()
        if not cmd:
            continue
        if (s.get("type") or "terminal") == "app":
            lines.append(f'start "" {cmd}')
        elif visible and s is last_term:
            lines.append(f'cmd /k "{cmd}"')
        else:
            lines.append(cmd)
    lines.append("exit /b 0")
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wc_logs")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, gen_bat_name(work))
    with open(path, "w", encoding="utf-8", errors="replace", newline="") as f:
        CRLF = chr(13) + chr(10)
        f.write(CRLF.join(lines) + CRLF)
    return path


def parse_steps_text(text: str) -> list[dict]:
    """Parse editor steps: one command per line.

    Lines starting with 'app:' (case-insensitive) become App steps
    (GUI launch via start); everything else is a Terminal step.
    Blank lines are skipped.
    """
    out = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line[:4].lower() == "app:":
            cmd = line[4:].strip()
            if cmd:
                out.append({"type": "app", "cmd": cmd})
        else:
            out.append({"type": "terminal", "cmd": line})
    return out


def parse_vars_text(text: str) -> dict:
    """Parse editor vars: NAME=value per line; blanks and #-comments skipped."""
    out = {}
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        if name:
            out[name] = value.strip()
    return out


def steps_to_text(steps) -> str:
    """Editor prefill: steps back to one-command-per-line form."""
    lines = []
    for s in steps or []:
        cmd = str((s or {}).get("cmd", "")).strip()
        if not cmd:
            continue
        if ((s or {}).get("type") or "terminal") == "app":
            lines.append("app: " + cmd)
        else:
            lines.append(cmd)
    return chr(10).join(lines)


def vars_to_text(vars) -> str:
    """Editor prefill: vars back to NAME=value per line."""
    return chr(10).join(
        str(k) + "=" + str(v) for k, v in (vars or {}).items())


_ANSI_ESC_RE = re.compile(
    r"\x1b\[([0-9;?]*)([@-~])"            # CSI (SGR when the final byte is 'm')
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC ... ST
    r"|\x1b\([0-9A-Z]"                     # charset select
    r"|\x1b[=>MEHc7-9]"                    # misc single-char escapes
    r"|\x1b"                               # bare/malformed ESC
)

# SGR foreground code -> canonical name (viewer maps names to widget colors).
_SGR_FG = {
    30: "black", 31: "red", 32: "green", 33: "yellow",
    34: "blue", 35: "magenta", 36: "cyan", 37: "white",
    90: "gray", 91: "bright-red", 92: "bright-green", 93: "bright-yellow",
    94: "bright-blue", 95: "bright-magenta", 96: "bright-cyan",
    97: "bright-white",
}


def ansi_runs(text: str) -> list[tuple[str, str | None]]:
    """Split *text* into (segment, fg-name|None) runs from ANSI SGR codes.

    Pure helper for the wctray log viewer (core stays UI-free; the viewer
    maps names to widget colors). All non-SGR escapes are stripped,
    unknown SGR codes ignored, bare/malformed ESC dropped.
    """
    runs: list[tuple[str, str | None]] = []
    fg: str | None = None
    pos = 0
    for m in _ANSI_ESC_RE.finditer(text):
        if m.start() > pos:
            runs.append((text[pos:m.start()], fg))
        if m.group(2) == "m":  # SGR: update fg; every other escape: strip
            for code in m.group(1).split(";"):
                n = int(code) if code.isdigit() else 0
                if n == 0 or n == 39:
                    fg = None
                elif n in _SGR_FG:
                    fg = _SGR_FG[n]
                # 1/2/22 (bold/dim) + backgrounds (40-47,100-107): ignored,
                # fg is preserved -- server logs only color the foreground.
        pos = m.end()
    if pos < len(text):
        runs.append((text[pos:], fg))
    return [(seg, c) for seg, c in runs if seg]


def strip_ansi(text: str) -> str:
    """Plain-text version of *text* (fallbacks, tests, non-color contexts)."""
    return "".join(seg for seg, _ in ansi_runs(text))


def run_work(work: dict) -> None:
    """Launch the work's .bat in a VISIBLE terminal window (no hidden
    self-relaunch). ONE window per work: `start` opens the window that
    hosts the .bat itself (mandatory -- without it the child would share
    wc's own console), and the .bat MUST be the §4.8 inline shape
    (`cd` -> `cls` -> `cmd /k`, no nested `start`) so a second window
    never appears. Registers it too."""
    steps = work.get("steps") or []
    bat = work.get("bat")
    gen = ""
    if steps:
        # Inline steps (backlog #2): materialize to a generated .bat so
        # execution, logging, detection and kill follow the SAME path as
        # .bat works. The stored `bat` (if any) is only a fallback.
        try:
            gen = materialize_steps(work, visible=work.get("run") != "detached")
        except Exception:
            gen = ""
    runner = gen or bat
    if not runner or not os.path.exists(runner):
        return
    # Windows `start` treats the FIRST quoted token as the window title.
    # A single `""` is the title placeholder; the NEXT token is the command.
    # Passing `"" "" "bat"` made the 2nd empty string the command, which
    # `start` resolves to opening the working FOLDER in Explorer (the
    # "Enter opens a folder instead of running" bug). Use exactly one `""`.
    if work.get("run") == "detached":
        # Docker-style: NO console at all (CREATE_NO_WINDOW) -- there is
        # never a window to hide, lose, or Alt+F4, so the hide-fight and
        # headless orphans cannot happen. The SAME .bat runs, so cwd/env
        # are identical to visible mode; output goes to the per-work log
        # (docker-logs equivalent). stdin is NUL: `pause` sails through,
        # interactive prompts get EOF (answer via flags/config instead).
        # NOTE: no `start` here -- that is what opens a window.
        # Fresh log per launch (docker-run semantics): append mode kept
        # every restart's history forever, so the viewer showed stale
        # output ("cache from old log"). The marker delimits runs.
        logf = open(work_log_path(work), "w", encoding="utf-8",
                    errors="replace")
        logf.write(f"[wc] launch {time.strftime('%Y-%m-%d %H:%M:%S')} :: {runner}\n")
        logf.flush()
        subprocess.Popen(["cmd.exe", "/c", runner], shell=False,
                         stdout=logf, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL,
                         creationflags=_NO_WINDOW)
        register(work)
        return
    subprocess.Popen(["cmd.exe", "/c", "start", "", runner], shell=False)
    register(work)


def kill_work(work: dict, dry_run: bool = False) -> list[int] | None:
    """Kill the work's process tree: matched processes + their DESCENDANTS.

    SAFETY (2026-09-05 incident — the old ancestor walk killed the agent's
    own session shell plus the user's Discord/VSCode/work windows): this
    function walks DOWN ONLY and NEVER walks up to ancestors. The launcher
    (this python), its whole parent chain, and the scanner powershell form
    a PROTECTED set that can never enter the kill list — even if their
    CommandLine happens to contain a match token (e.g. our own shell
    echoing the token in its command line).

    Close happens in THREE passes so no dead terminal is left behind
    ("kill = exit the window, not just stop the task"):
    1. graceful `taskkill /PID` (NO /F) on the whole kill set -- this
       sends the console close request, so the window-owning cmd exits
       through its normal path and its window closes (GUI apps get
       WM_CLOSE and shut down cleanly instead of being ripped away);
    2. Alt+F4 the work's windows via close_work_windows (WM_CLOSE to
       every HWND in the work's guarded owner set). Needed because a
       leftover `cmd /k` host can be an ANCESTOR of every seed (old
       nested-start windows) -- process-only DOWN kill can never reach
       it, but closing its WINDOW terminates it via the console;
    3. after a short bounded wait, per-PID `taskkill /F` on the same set
       as the sweep -- PIDs already gone just report "not found"
       (captured + ignored); anything that ignored both closes dies here.
    The kill set itself is unchanged: the matched seed (the visible
    `cmd /K bat.bat` wrapper carries the bat basename as a token via
    kill_tokens_for, so it is a seed directly -- no upward walk needed)
    plus every descendant (npm/node/npx children). Per-PID kills (no /T)
    avoid cascading into shared conhosts of unrelated windows.
    powershell* processes are never killed (they host user sessions).

    With dry_run=True, returns the sorted kill PID list WITHOUT killing —
    show it to the user BEFORE any real kill. Otherwise kills each PID,
    unregisters the work, and returns None.
    """
    # Drop dangerously short tokens (1-2 chars match the whole machine --
    # e.g. a 1-letter work id). Killing is destructive: a tiny token can
    # never be what anyone wants. Detection (is_running) is unaffected.
    toks = [t for t in kill_tokens_for(work) if len(t) >= 3]
    if not toks:
        return [] if dry_run else None
    my_pid = os.getpid()  # the python (wc) process -- never touch
    # Seeds + DOWN expansion computed in pure Python over ONE shared table
    # (no per-kill PowerShell scan; Trap: NEVER use $pid as a loop variable
    # applied to the old inline script -- gone with it).
    table = scan_table()
    by_parent: dict[int, int] = {}
    names: dict[int, str] = {}
    cmds: dict[int, str] = {}
    children: dict[int, list[int]] = {}
    for pid, ppid, name, cmd in table:
        by_parent[pid] = ppid
        names[pid] = name or ""
        cmds[pid] = cmd or ""
        children.setdefault(ppid, []).append(pid)

    def _is_ps(pid: int) -> bool:
        return names.get(pid, "").lower().startswith("powershell")

    # Protected = launcher + every ancestor of the launcher up to the root.
    # (The old inline script also excluded its own scanner PID -- moot now:
    # it was powershell* and dead by match time.) Nothing in here can ever
    # be killed.
    prot = {my_pid}
    cur, guard = my_pid, 0
    while guard < 64:
        guard += 1
        anc = by_parent.get(cur, 0)
        if not anc or anc in prot:
            break
        prot.add(anc)
        cur = anc
    # Seeds: CommandLine token match, skipping powershell* + NEVER-seed GUI
    # + protected. (PowerShell -like is case-insensitive substring, matched
    # here with .lower(); our tokens carry no -like wildcards.)
    toks_low = [t.lower() for t in toks]
    seed: set[int] = set()
    for pid, cmd in cmds.items():
        if not cmd or _is_ps(pid):
            continue
        if names.get(pid, "").lower() in _NEVER_SEED_GUI:
            continue
        if pid in prot:
            continue
        low = cmd.lower()
        if any(t and t in low for t in toks_low):
            seed.add(pid)
    # Expand DOWN ONLY (BFS over children). Protected PIDs are never added
    # even if parented under a seed; powershell* is traversed through but
    # never added (it hosts user sessions).
    kill: set[int] = set()
    seen: set[int] = set()
    queue = list(seed)
    for s in seed:
        seen.add(s)
        kill.add(s)
    while queue:
        c = queue.pop()
        for ch in children.get(c, []):
            if ch in prot or ch in seen:
                continue
            seen.add(ch)
            if not _is_ps(ch):
                kill.add(ch)
            queue.append(ch)
    pids = sorted(kill)
    if dry_run:
        return pids
    def _tk(args: list[str], timeout: int) -> None:
        try:
            subprocess.run(
                ["taskkill.exe"] + args,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                creationflags=_NO_WINDOW,
            )
        except Exception:
            pass
    # Pass 1 (graceful): ask every PID in the downward set to exit through
    # its normal close path -- the window-owning cmd exits and its terminal
    # window closes instead of lingering as a dead prompt. No /F, no /T.
    for kpid in pids:
        _tk(["/PID", str(kpid)], 10)
    # Pass 2 (Alt+F4): WM_CLOSE the work's terminal windows. Killing the
    # task alone can leave the bare window behind (a leftover `cmd /k`
    # host can be an ANCESTOR of every seed, unreachable by DOWN kill) --
    # closing the WINDOW is what removes it. Same guarded owner set as
    # the `h` key (protected chain + badgui never included).
    try:
        close_work_windows(work)
    except Exception:
        pass
    # Bounded wait so the closes can land (windows die fast, and
    # stragglers are swept in pass 3 -- this sleep never gates on state).
    time.sleep(2.5)
    # Pass 3 (sweep): kill stragglers -- ONE gowc call when available
    # (in-process TerminateProcess; already-gone PIDs report "dead" and are
    # ignored), else the per-PID taskkill /F loop. No /T ever: tree-kill
    # cascades into shared conhost processes of unrelated windows.
    swept = False
    if _gowc_available():
        try:
            r = subprocess.run(
                [str(_GOWC), "kill"] + [str(k) for k in pids],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                creationflags=_NO_WINDOW,
            )
            swept = r.returncode == 0
        except Exception:
            swept = False
    if not swept:
        for kpid in pids:
            _tk(["/F", "/PID", str(kpid)], 10)
    clear_hidden_work(work)  # dead windows need no tracking
    unregister(work)
    return None


WM_CLOSE = 0x0010  # Alt+F4 / clicking X -- the graceful window close


def close_work_windows(work: dict) -> int:
    """Post WM_CLOSE (Alt+F4) to every top-level window in the work's tree.

    Killing the task alone can leave the bare terminal window behind
    (observed: the task dies, the `cmd /k` host survives with a dead
    prompt -- it can even be an ANCESTOR of every kill seed, so no
    downward process kill reaches it). Closing the WINDOW is what removes
    it: the console host exits and attached processes get the console
    close request, exactly as if the user pressed Alt+F4.

    Uses find_work_hwnds -- the same guarded owner set as the `h` key
    (own protected chain + powershell* + badgui never included). Returns
    the number of windows confirmed gone afterwards (bounded ~2s wait).
    Never raises; 0 means "no windows found / nothing to close".
    """
    hwnds = find_work_hwnds(work)
    if not hwnds:
        return 0
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                        ctypes.c_void_p, ctypes.c_void_p]
        user32.PostMessageW.restype = ctypes.c_int
        user32.IsWindow.argtypes = [ctypes.c_void_p]
        user32.IsWindow.restype = ctypes.c_int
    except Exception:
        return 0
    hwnds = list(dict.fromkeys(hwnds))
    for hwnd in hwnds:
        try:
            if user32.IsWindow(hwnd):
                user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass
    for _ in range(8):
        try:
            if all(not user32.IsWindow(h) for h in hwnds):
                return len(hwnds)
        except Exception:
            break
        time.sleep(0.25)
    try:
        return sum(1 for h in hwnds if not user32.IsWindow(h))
    except Exception:
        return 0


# --------------------------------------------------------------------------
# Find the visible HWNDs owned by a work's process tree. Used by `h` to
# hide/show that work's terminal window without killing the process.
# --------------------------------------------------------------------------
def find_work_hwnds(work: dict) -> list[int]:
    """Return the HWNDs of every top-level window whose owning PID belongs
    to the work's process tree (i.e. processes whose CommandLine contains
    one of the work's match tokens). Returned HWNDs are safe to pass to
    ShowWindow / PostMessage."""
    toks = kill_tokens_for(work)
    if not toks:
        return []
    # 1) collect candidate PIDs in pure Python over ONE shared table
    # (same NEVER-seed GUI guard as kill_work, via the shared set).
    table = scan_table()
    names = {pid: (name or "") for pid, _pp, name, _c in table}
    cmds = {pid: (cmd or "") for pid, _p, _n, cmd in table}
    by_parent = {pid: ppid for pid, ppid, _n, _c in table}

    def _is_ps(pid: int) -> bool:
        return names.get(pid, "").lower().startswith("powershell")

    toks_low = [t.lower() for t in toks]
    pids = {pid for pid, cmd in cmds.items()
            if cmd and not _is_ps(pid)
            and names.get(pid, "").lower() not in _NEVER_SEED_GUI
            and any(t and t in cmd.lower() for t in toks_low)}
    if not pids:
        return []
    # 2) walk to ancestors (pure Python, same rules as the old inline
    # script) so we also hide the cmd.exe host
    allp = set(pids)
    for s in list(pids):
        cur = s
        while True:
            ppid = by_parent.get(cur, 0)
            if not ppid:
                break
            par_name = names.get(ppid)
            if par_name is None:
                break
            if par_name.lower().startswith("powershell"):
                break
            if ppid in allp:
                break
            allp.add(ppid)
            cur = ppid
    pids = allp
    # 3) find top-level windows owned by any of these PIDs (Win32 EnumWindows)
    found = _hwnds_for_pids(pids, table)
    # 4) exact-title match: every launcher sets `title <works.json label>`
    # (§4.8), so the window is also findable by title when PID-ownership
    # mapping misses (reparented host, WT active-tab title). Guarded --
    # never a shared host (see _title_hwnds_guarded).
    try:
        for h in _title_hwnds_guarded(work.get("label") or "", table):
            if h not in found:
                found.append(h)
    except Exception:
        pass
    return found


def _hwnds_for_pids(pids: set[int],
                    table: list[tuple[int, int, str, str]] | None = None) -> list[int]:
    """Enumerate top-level windows owned by the work's process tree.

    A console window is owned by conhost.exe, typically a CHILD of the
    work's cmd -- while matchable seeds (node with an absolute script
    path) sit BELOW that cmd. So raw-PID matching and upward-only walks
    both miss. Owner set = seeds + bounded ancestors of seeds (up to 8,
    stopping at our own protected chain) + one level of children below
    each (catches conhost + wrapper cmds). powershell* is traversed but
    never added (it hosts user sessions). Kill stays DOWNWARD-ONLY;
    this up+down-1 expansion applies to HIDE (reversible) only.
    Pure ctypes over the shared table, no extra scan."""
    import ctypes
    user32 = ctypes.windll.user32
    user32.GetWindowThreadProcessId.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_int
    # PID -> (parent, name) maps from the shared table (no extra scan).
    if table is None:
        table = scan_table()
    parent: dict[int, int] = {}
    names: dict[int, str] = {}
    children: dict[int, list[int]] = {}
    for pid, ppid, name, _cmd in table:
        parent[pid] = ppid
        names[pid] = (name or "").strip()
        children.setdefault(ppid, []).append(pid)

    def is_ps(pid: int) -> bool:
        return (names.get(pid) or "").lower().startswith("powershell")

    # Protected = our own chain (never hide our/the agent's windows).
    me = os.getpid()
    prot: set[int] = {me}
    cur, guard = me, 0
    while guard < 64:
        guard += 1
        par = parent.get(cur, 0)
        if not par or par in prot:
            break
        prot.add(par)
        cur = par

    owners: set[int] = set()
    for s in pids:
        if s in prot or is_ps(s):
            continue
        owners.add(s)
    # Up from each seed (bounded, stop at protected/missing/root).
    for s in list(owners):
        cur, depth = s, 0
        while depth < 8:
            par = parent.get(cur, 0)
            if not par or par in prot:
                break
            if not is_ps(par):
                owners.add(par)
            cur, depth = par, depth + 1
    # One level down (conhost + wrapper cmds). Never protected/powershell.
    for o in list(owners):
        for ch in children.get(o, []):
            if ch in prot or is_ps(ch):
                continue
            owners.add(ch)
    if not owners:
        return []

    found: list[int] = []
    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lparam):
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) in owners:
            try:
                if user32.IsWindowVisible(hwnd):
                    found.append(int(hwnd))
            except Exception:
                pass
        return 1
    try:
        user32.EnumWindows(cb, 0)
    except Exception:
        pass
    # keep the callback alive until EnumWindows returns
    _hwnds_for_pids._cb = cb  # type: ignore[attr-defined]
    return found


_TITLE_GUARD_NAMES = ("windowsterminal", "explorer")


def _title_hwnds_guarded(label: str,
                         table: list[tuple[int, int, str, str]] | None = None) -> list[int]:
    """Top-level windows whose title EXACTLY equals label, minus shared hosts.

    Exact case-insensitive match only: conhost defaults ('', 'C:\\...cmd.exe')
    can never collide, and no substring guessing that could grab a user
    window. Shared-host guard (applied AFTER matching): a hit owned by our
    own PID, by windowsterminal / explorer, or by powershell* is dropped --
    closing or hiding a shared Windows Terminal window would take the user's
    other tabs with it, so WT-manual runs keep process-level behavior only.
    Includes invisible windows (a hidden/parked orphan of the work still
    belongs to it; kill clears hidden tracking anyway). Never raises.
    """
    want = (label or "").strip().lower()
    if not want:
        return []
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                          ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int
    except Exception:
        return []
    cands: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _lparam):
        try:
            buf = ctypes.create_unicode_buffer(256)
            if user32.GetWindowTextW(hwnd, buf, 256) > 0 \
                    and (buf.value or "").strip().lower() == want:
                cands.append(int(hwnd))
        except Exception:
            pass
        return 1
    try:
        user32.EnumWindows(cb, 0)
    except Exception:
        return []
    _title_hwnds_guarded._cb = cb  # type: ignore[attr-defined]
    if not cands:
        return []
    owners = _hwnd_owner_pids(cands)
    src = table if table is not None else scan_table()
    names = {pid: (name or "") for pid, _pp, name, _c in src}
    me = os.getpid()
    out = []
    for h in dict.fromkeys(cands):
        pid = owners.get(h, 0)
        if not pid or pid == me:
            continue
        nm = (names.get(pid) or "").lower()
        base = nm[:-4] if nm.endswith(".exe") else nm
        if base in _TITLE_GUARD_NAMES or base.startswith("powershell"):
            continue
        out.append(h)
    return out


# --------------------------------------------------------------------------
# True hide/show (tray-grade): SW_HIDE removes the window from the taskbar
# AND Alt+Tab while the process keeps running. Restore with SW_SHOW.
# Hidden HWNDs are tracked per work id because a hidden window no longer
# enumerates as visible and can't be re-found by scan.
# --------------------------------------------------------------------------
_HIDDEN_HWNDS: dict[str, list[int]] = {}
_HIDDEN_HWND_PIDS: dict[str, dict[int, int]] = {}
_HIDDEN_LOCK = threading.RLock()
_RESTORING_WORKS: set[str] = set()
_WINDOW_OP_LOCKS: dict[str, threading.RLock] = {}


def _window_op_lock(wid: str) -> threading.RLock:
    with _HIDDEN_LOCK:
        return _WINDOW_OP_LOCKS.setdefault(wid, threading.RLock())


def clear_hidden_work(work_or_id) -> None:
    """Forget hidden-window tracking for a stopped or deleted work."""
    wid = work_or_id if isinstance(work_or_id, str) else work_or_id.get("id", "")
    with _window_op_lock(wid):
        with _HIDDEN_LOCK:
            _HIDDEN_HWNDS.pop(wid, None)
            _HIDDEN_HWND_PIDS.pop(wid, None)
            _RESTORING_WORKS.discard(wid)


def _hwnd_owner_pids(hwnds: list[int]) -> dict[int, int]:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.GetWindowThreadProcessId.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    except Exception:
        return {}
    owners = {}
    for hwnd in dict.fromkeys(hwnds):
        try:
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                owners[hwnd] = int(pid.value)
        except Exception:
            pass
    return owners


def _valid_hwnds(hwnds: list[int], expected_pids: dict[int, int] | None = None) -> list[int]:
    """Return unique handles that still identify live windows."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.IsWindow.argtypes = [ctypes.c_void_p]
        user32.IsWindow.restype = ctypes.c_int
    except Exception:
        return []
    owners = _hwnd_owner_pids(hwnds) if expected_pids is not None else {}
    valid = []
    for hwnd in dict.fromkeys(hwnds):
        try:
            if not hwnd or not user32.IsWindow(hwnd):
                continue
            if expected_pids is not None and owners.get(hwnd) != expected_pids.get(hwnd):
                continue
            valid.append(hwnd)
        except Exception:
            pass
    return valid


def _set_hwnds_visible_confirmed(hwnds: list[int], show: bool, expected_pids: dict[int, int] | None = None) -> list[int]:
    """Request visibility and return handles confirmed in the target state."""
    hwnds = _valid_hwnds(hwnds, expected_pids)
    if not hwnds:
        return []
    try:
        import ctypes
        user32 = ctypes.windll.user32
        user32.ShowWindowAsync.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    except Exception:
        return []
    command = 9 if show else 0  # SW_RESTORE / SW_HIDE
    for hwnd in hwnds:
        try:
            user32.ShowWindowAsync(hwnd, command)
        except Exception:
            pass
    confirmed = []
    for _ in range(20):
        confirmed = []
        for hwnd in hwnds:
            try:
                if bool(user32.IsWindowVisible(hwnd)) is show:
                    confirmed.append(hwnd)
            except Exception:
                pass
        if len(confirmed) == len(hwnds):
            break
        time.sleep(0.025)
    return confirmed


def set_hwnds_visible(hwnds: list[int], show: bool) -> int:
    return len(_set_hwnds_visible_confirmed(hwnds, show))


def hide_work_windows(work: dict, retries: int = 3) -> tuple[int, str]:
    """True-hide a running work window while retaining restore handles."""
    wid = work.get("id", "")
    with _window_op_lock(wid):
        with _HIDDEN_LOCK:
            if _HIDDEN_HWNDS.get(wid):
                return 0, "already hidden"
        hwnds = find_work_hwnds(work)
        tries = 0
        while not hwnds and tries < retries and is_running(work):
            time.sleep(2.5)
            tries += 1
            hwnds = find_work_hwnds(work)
        hwnds = _valid_hwnds(hwnds)
        if not hwnds:
            if is_running(work):
                return 0, "running but has no window (headless)"
            return 0, "not running -- nothing to hide"
        owners = _hwnd_owner_pids(hwnds)
        hidden = _set_hwnds_visible_confirmed(hwnds, False, owners)
        if hidden:
            with _HIDDEN_LOCK:
                restoring = wid in _RESTORING_WORKS
                if not restoring:
                    _HIDDEN_HWNDS[wid] = hidden
                    _HIDDEN_HWND_PIDS[wid] = _hwnd_owner_pids(hidden)
            if restoring:
                _set_hwnds_visible_confirmed(hidden, True)
                return 0, "hide cancelled by restore"
            if len(hidden) == len(hwnds):
                return len(hidden), f"hid {len(hidden)} window(s) -- task still running"
            return len(hidden), f"partially hid {len(hidden)}/{len(hwnds)} window(s)"
        return 0, "could not confirm hidden window"


def show_work_windows(work: dict) -> tuple[int, str]:
    """Restore tracked windows without racing the monitor re-hide sweep."""
    wid = work.get("id", "")
    with _window_op_lock(wid):
        with _HIDDEN_LOCK:
            hwnds = list(_HIDDEN_HWNDS.pop(wid, []))
            owners = dict(_HIDDEN_HWND_PIDS.pop(wid, {}))
            if not hwnds:
                return 0, "nothing hidden for this work"
            _RESTORING_WORKS.add(wid)
        valid = _valid_hwnds(hwnds, owners)
        if not valid:
            with _HIDDEN_LOCK:
                _RESTORING_WORKS.discard(wid)
            return 0, "hidden window no longer exists"
        visible = _set_hwnds_visible_confirmed(valid, True, owners)
        n = len(visible)
        if n:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
                user32.SetForegroundWindow.restype = ctypes.c_int
                user32.SetForegroundWindow(visible[0])
            except Exception:
                pass
        with _HIDDEN_LOCK:
            _RESTORING_WORKS.discard(wid)
            remaining = [hwnd for hwnd in valid if hwnd not in visible]
            if remaining:
                _HIDDEN_HWNDS[wid] = remaining
                _HIDDEN_HWND_PIDS[wid] = {h: owners[h] for h in remaining if h in owners}
        if n == len(valid):
            return n, f"restored {n} window(s)"
        return n, f"restore incomplete ({n}/{len(valid)} visible)"


def is_work_hidden(work: dict) -> bool:
    with _HIDDEN_LOCK:
        return bool(_HIDDEN_HWNDS.get(work.get("id", "")))


def hidden_work_ids() -> set[str]:
    """Ids of works currently marked hidden."""
    with _HIDDEN_LOCK:
        return {wid for wid, hwnds in _HIDDEN_HWNDS.items() if hwnds}


def sweep_hidden_windows(manifest: dict) -> dict[str, int]:
    """Re-hide respawned windows, serialized with user restore."""
    with _HIDDEN_LOCK:
        candidates = [wid for wid in _HIDDEN_HWNDS if wid not in _RESTORING_WORKS]
    by_id = {w.get("id"): w for w in manifest.get("works", [])}
    reswept = {}
    for wid in candidates:
        work = by_id.get(wid)
        if work is None:
            continue
        with _window_op_lock(wid):
            with _HIDDEN_LOCK:
                if wid not in _HIDDEN_HWNDS:
                    continue
            try:
                hwnds = _valid_hwnds(find_work_hwnds(work))
            except Exception:
                continue
            owners = _hwnd_owner_pids(hwnds)
            hidden = _set_hwnds_visible_confirmed(hwnds, False, owners)
            if hidden:
                with _HIDDEN_LOCK:
                    merged = list(dict.fromkeys(_HIDDEN_HWNDS.get(wid, []) + hidden))
                    _HIDDEN_HWNDS[wid] = merged
                    _HIDDEN_HWND_PIDS[wid] = _hwnd_owner_pids(merged)
                reswept[wid] = len(hidden)
    return reswept


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
    """Return registry entries whose work is still alive. This is the list kc
    uses to display and kill currently-running works. Scans processes once."""
    data = _load_registry()
    out = []
    manifest = load_manifest()
    commandlines = scan_commandlines()
    for wid, info in data.items():
        w = work_by_id(manifest, wid)
        if w and is_running(w, commandlines):
            out.append({"id": wid, **info})
    return out


def live_running(manifest: dict | None = None, commandlines: list[str] | None = None) -> list[dict]:
    """Return all works currently detected as running LIVE (not just what wc
    registered). Used by kc to list + kill works you started by any means.
    Pass a pre-scanned `commandlines` (from scan_commandlines) to do the whole
    scan in a single powershell call instead of one per work."""
    if manifest is None:
        manifest = load_manifest()
    if commandlines is None:
        commandlines = scan_commandlines()
    out = []
    for w in manifest.get("works", []):
        if w.get("detect") is False:
            continue
        if is_running(w, commandlines):
            out.append({"id": w["id"], "label": w.get("label", w["id"]),
                        "bat": w.get("bat", "")})
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
    global _CURRENT_MANIFEST
    _CURRENT_MANIFEST = manifest
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
    manifest = _CURRENT_MANIFEST if _CURRENT_MANIFEST is not None else load_manifest()
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
    """Space toggles selection: OFF<->ON. A running work (RUN) is treated as
    'not yet selected' for kill purposes, so Space on a RUN node selects it
    (ON) -- i.e. 'mark this running work to be killed'. LEFT_ALONE is left
    untouched by Space."""
    if state == ON:
        return OFF
    if state == OFF or state == RUN:
        return ON
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
    # 1) mark running children (but never override an explicit ON selection --
    #    if the user selected a running work to kill, keep it ON so Space sticks)
    for n in model:
        if n.kind != "group":
            continue
        members = member_nodes(model, n)
        for m in members:
            if m.is_running() and states.get(m.key) == OFF:
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


# -------------------------------------------------------------------------
# launch + progress  (used by wc's "run then monitor" flow)
# -------------------------------------------------------------------------
# A "work" is the BACKGROUND process its .bat spawns — NOT the launcher window.
# E.g. OmniRoute CLI's .bat does `Start-Process ... 'title bg-omniroute-cli &&
# omniroute'` (hidden); Hamster does `npm run dev` (node); Unity -> Unity
# Hub.exe; VSCode -> Code.exe. The launcher window itself is just an inspector
# that `pause`s and can be closed harmlessly.
#
# So wc's "progress" works by:
#   * RUN: spawn the .bat (which in turn spawns the real bg process).
#   * is_running(work) = does the real bg process exist? (match token, or the
#     executable basename) — same live detection kc uses to list/kill.
#   * done/ready/failed: read from the bg process's OWN log if `log` is set;
#     otherwise a long-lived bg process with no error == stable.
# We do NOT wrap the .bat in a tracker window (that would be an extra, useless
# window). We simply watch the real process.
import re

LAUNCH_DIR = HERE / "wc_logs"
# A server that never exits is considered "stable" once it has been alive
# this long with no error. Launchers that exit on their own settle via the
# is_running() check turning False.
GRACE_SECONDS = 12
# HARD SAFETY CAP: if a launcher stays alive this long with no `ready` string
# and no error, we declare it `stable` and STOP polling it. This prevents wc
# from ever looping forever. (No work should need longer than this to show it
# is alive-and-well.)
STABLE_MAX_SECONDS = 60
# Global ceiling on how many times wc will spawn `start ""` in one run.
MAX_LAUNCHES = 16

_launched_count = 0

ERROR_KEYWORDS = (
    "traceback", "fatal error", "error:", "exception in",
    "cannot be found", "access is denied", "connection refused",
    "command not found",
)


def _ensure_launch_dir() -> Path:
    try:
        LAUNCH_DIR.mkdir(exist_ok=True)
    except Exception:
        pass
    return LAUNCH_DIR


def _already_running(work: dict) -> bool:
    """True if the work's REAL background process is already alive — so wc
    doesn't spawn a 2nd one."""
    return is_running(work)


def launch_work(work: dict, commandlines: list[str] | None = None) -> dict | None:
    """Spawn `work`'s .bat (which launches the real background process). Returns
    a monitor record, or None if the .bat is missing. Caller (wc) decides
    whether to kill a running instance first -- this just launches.

    SAFETY: never spawns more than MAX_LAUNCHES windows total. The launcher
    window opens then immediately `pause`s (harmless) -- the REAL process is
    what we detect/kill.
    """
    global _launched_count
    wid = work.get("id", "")
    if not wid:
        return None
    if _launched_count >= MAX_LAUNCHES:
        return None
    # Steps-works (backlog #2) materialize their own runner inside
    # run_work; `bat`, when present, is only a fallback for them.
    if not work.get("steps"):
        realbat = work.get("bat")
        if not realbat or not os.path.exists(realbat):
            return None
    run_work(work)   # spawns the .bat in its own visible window (per wc_core)
    _launched_count += 1
    return {"id": wid, "label": work.get("label", wid), "work": work,
            "launched": time.time(), "already": False}


def _read_log(work: dict) -> str:
    log = work.get("log")
    if not log:
        return ""
    p = Path(log) if isinstance(log, (str, Path)) else None
    if not p or not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _scan_error(text: str) -> str:
    low = text.lower()
    for kw in ERROR_KEYWORDS:
        if kw in low:
            return kw
    return ""


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
    """Write works.json -- the single writer for editor/group/delete ops."""
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


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


# Status values returned by poll_launch:
#   starting | running | ready | stable | done | failed
SETTLED = ("ready", "stable", "done")


def poll_launch(rec: dict, work: dict | None = None, commandlines: list[str] | None = None) -> tuple[str, str]:
    """Return (status, detail) for a launched work, watching its REAL bg proc.

    SAFETY: a work still alive but with no `ready` marker and no error past
    STABLE_MAX_SECONDS is declared `stable` — so wc's monitor loop always ends.
    Pass a pre-scanned `commandlines` (from scan_commandlines) to avoid one
    powershell spawn per poll per work."""
    work = work or rec.get("work") or {}
    if rec.get("already"):
        return ("stable", "already running")
    alive = is_running(work, commandlines)
    if not alive:
        # real process gone -> either it exited (done) or died (failed)
        logtxt = _read_log(work)
        err = _scan_error(logtxt)
        if err:
            return ("failed", err)
        return ("done", "")
    # alive: look for ready marker / error in its log
    logtxt = _read_log(work)
    ready = work.get("ready")
    if ready and str(ready).lower() in logtxt.lower():
        return ("ready", "")
    err = _scan_error(logtxt)
    if err:
        return ("failed", err)
    age = time.time() - rec.get("launched", 0)
    if age >= STABLE_MAX_SECONDS:
        return ("stable", "")
    if age >= GRACE_SECONDS:
        return ("stable", "")
    return ("running", "")


