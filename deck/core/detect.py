"""Process table scans, identity tokens, is_running (jobs first)."""

import ntpath
import os
import subprocess
import threading

from deck.core import common, manifest as manifest_mod, store, steps, jobs

# Optional speed helper (pure-stdlib Go, built from gowc/): when gowc.exe sits
# next to this file, scans/kills go through it (~0.2s vs ~0.9s per spawn).
# Absent -> identical powershell fallbacks. Never a hard dependency.
_GOWC = common.HERE / "gowc.exe"
# Per-thread: the monitor thread and action workers scan concurrently, and a
# shared flag let one thread's `scan_available()` read another's result.
_SCAN_STATE = threading.local()


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

# The desktop agent can run a Node worker with a user's project directory as
# an argument (for example, ``--working-dir D:\\HammonQuest``).  That path is
# a working-directory reference, not a launch identity for the project.  Keep
# those workers out of both process-tree seeding and window targeting.  The
# marker is deliberately narrow: ordinary Node dev servers are unaffected.
_NEVER_SEED_COMMAND_MARKERS = frozenset({
    "trusted-worker.js",
    "\\cua_node\\",
})


def _is_never_seed_name(name: str) -> bool:
    """Return whether a process name must never seed a kill/hide traversal."""
    value = str(name or "").strip().strip('"').replace("\\", "/")
    return value.rsplit("/", 1)[-1].lower() in _NEVER_SEED_GUI


def _is_never_seed_process(name: str, command: str = "") -> bool:
    """Whether a row must never seed a work kill/window traversal."""
    if _is_never_seed_name(name):
        return True
    cmd = str(command or "").replace("/", "\\").lower()
    return any(marker in cmd for marker in _NEVER_SEED_COMMAND_MARKERS)

# Kill matching is stricter than live detection. Bare executable names are
# classes of processes, not identities for one work.
_TARGET_VAR_NAMES = frozenset({"APPDIR", "PROJECT", "VSCDATA"})
_GENERIC_PROCESS_TOKENS = frozenset({
    "cmd", "cmd.exe", "conhost", "conhost.exe", "node", "node.exe",
    "python", "python.exe", "pythonw", "pythonw.exe", "npm", "npm.cmd",
    "npx", "npx.cmd", "powershell", "powershell.exe",
})


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


def _specific_kill_token(token) -> bool:
    """Whether *token* has enough identity to seed a kill traversal."""
    value = str(token or "").strip().strip('"').lower()
    if len(value) < 3 or value in _GENERIC_PROCESS_TOKENS:
        return False
    if value.startswith(steps.GEN_BAT_PREFIX.lower()):
        return True
    if any(ch in value for ch in ("\\", "/", ":")):
        return True
    if value.endswith((".bat", ".cmd", ".lnk")):
        return True
    # A bare executable name identifies a program, not this work's instance.
    if value.endswith((".exe", ".com", ".dll")):
        return False
    # Keep useful file-less service tokens, but reject short/common names.
    return len(value) >= 8


def _append_unique_token(out: list[str], token) -> None:
    value = str(token or "").strip()
    if value and _specific_kill_token(value) \
            and value.lower() not in {x.lower() for x in out}:
        out.append(value)


def _is_shared_window_host(name: str) -> bool:
    base = (name or "").strip().lower()
    return base in {"explorer.exe", "windowsterminal.exe", "wt.exe"}


def _windows_path_text(value) -> str:
    """Normalize a path fragment for case-insensitive Windows cmd matching."""
    return str(value or "").strip().strip('"').replace("/", "\\").lower()


def _identity_token_matches(token: str, command: str) -> bool:
    """Match an identity token at a path boundary, not inside another path.

    ``D:\\HammonQuest`` must not match ``D:\\HammonQuest-old``.  A path
    followed by a slash is the strongest form (a project file below the
    configured directory); exact argument forms ending at whitespace/quotes
    are also accepted for generated runner commands and ``cd`` steps.
    """
    needle = _windows_path_text(token)
    haystack = _windows_path_text(command)
    if not needle or not haystack:
        return False
    if "\\" not in needle and ":" not in needle:
        return needle in haystack
    start = haystack.find(needle)
    while start >= 0:
        end = start + len(needle)
        if end == len(haystack) or haystack[end] in "\\/ \t\"'=;&":
            return True
        start = haystack.find(needle, start + 1)
    return False


def _primary_path_identity_matches(token: str, command: str) -> bool:
    """Whether a path token names code launched from that directory.

    A process can mention another work's directory only as configuration,
    such as ``--env-file=D:\\HamsterWorld\\server\\.env``.  That is not
    enough to claim the process for the work.  Require a file below the
    directory and ignore common configuration/working-directory options.
    """
    needle = _windows_path_text(token)
    haystack = _windows_path_text(command)
    if not needle or "\\" not in needle or not haystack:
        return False
    start = haystack.find(needle)
    weak_prefixes = (
        "--env-file=", "--env-file ",
        "--working-dir=", "--working-dir ",
        "--cwd=", "--cwd ",
        "--project=", "--project ",
    )
    file_suffixes = (".bat", ".cmd", ".js", ".cjs", ".mjs", ".py",
                     ".exe", ".com")
    while start >= 0:
        end = start + len(needle)
        if end < len(haystack) and haystack[end] in "\\/":
            prefix = haystack[max(0, start - 64):start]
            if not any(prefix.endswith(option) for option in weak_prefixes):
                return True
        elif needle.endswith(file_suffixes) \
                and (end == len(haystack)
                     or haystack[end] in " \t\"'=;&"):
            prefix = haystack[max(0, start - 64):start]
            if not any(prefix.endswith(option) for option in weak_prefixes):
                return True
        start = haystack.find(needle, start + 1)
    return False


def _runner_identity(work: dict, registry_info: dict) -> list[str]:
    """Return identity strings for the process recorded as the launch root.

    A registry PID is only trustworthy when its command line still names the
    runner that created it.  Prefer the recorded absolute runner path; for old
    registry entries without that field, use the deterministic runner name
    from the current work.  Do not fall back to a broad ``match`` token here:
    that is exactly how a recycled PID can become an unrelated kill root.
    """
    info = registry_info if isinstance(registry_info, dict) else {}
    recorded = str(info.get("runner") or "").strip()
    if recorded:
        return [_windows_path_text(recorded)]
    runner = ""
    if work.get("steps"):
        runner = steps.gen_bat_name(work)
    elif work.get("bat"):
        runner = ntpath.basename(str(work.get("bat")))
    return [_windows_path_text(runner)] if runner else []


def kill_tokens_for(work: dict) -> list[str]:
    """Return identity-bearing tokens for a work's kill traversal.

    Detection tokens stay broad, but kill tokens discard generic executable
    names and short ids. Generated runner names and configured target paths
    provide stable identities for the outer wrapper and its children.
    """
    toks: list[str] = []
    for token in titles_for(work):
        _append_unique_token(toks, token)
    bat = work.get("bat") or ""
    if bat:
        bn = os.path.basename(bat)
        _append_unique_token(toks, bn)
    # Steps-works run a generated .bat (materialize_steps): its wrapper
    # CommandLine carries the gen name, so seed it exactly like a .bat
    # basename (deterministic -- computable here without launching).
    if work.get("steps"):
        _append_unique_token(toks, steps.gen_bat_name(work))
    _append_unique_token(toks, work.get("proj"))
    for name in _TARGET_VAR_NAMES:
        raw = (work.get("vars") or {}).get(name)
        if raw:
            try:
                _append_unique_token(toks, steps.expand_work_vars(str(raw), work))
            except Exception:
                _append_unique_token(toks, raw)
    return toks


def scan_table() -> list[tuple[int, int, str, str]]:
    """Full process table as (pid, ppid, name, cmdline) rows -- the ONE data
    source every consumer shares. gowc.exe scan when present (~0.2s), else
    ONE powershell dump (~0.9s). Previously each consumer spawned its own
    scan (find_work_hwnds alone did 3 = ~2.7s). No rows are excluded here;
    each consumer applies its own filters (powershell*, protected, ...)."""
    rows = _scan_table_gowc()
    # A successful-but-empty helper result is not a usable process table on a
    # live Windows machine.  Fall back so a scan failure cannot turn Stop into
    # Start or make a managed process look absent.
    if not rows:
        rows = _scan_table_ps()
    _SCAN_STATE.ok = bool(rows)
    return rows


def scan_available() -> bool:
    """Whether THIS thread's most recent process-table scan produced rows.

    A Windows process table cannot legitimately be empty.  Callers that must
    choose between Stop and Start use this guard so a transient WMI/helper
    failure never turns an unknown running work into a second launch.
    """
    return bool(getattr(_SCAN_STATE, "ok", False))


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
            creationflags=common._NO_WINDOW,
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
            creationflags=common._NO_WINDOW,
        )
        return _parse_table_rows(r.stdout)
    except Exception:
        return []


def scan_commandlines() -> list[str]:
    """Return the CommandLine of every live non-powershell process in ONE
    shared scan. Call this once and reuse the list for many is_running checks
    instead of scanning per work (that's what made kc lag). Now a projection
    over scan_table (gowc-accelerated when present)."""
    me = os.getpid()
    return [cmd for (pid, _pp, name, cmd) in scan_table()
            if pid != me and cmd
            and not (name or "").lower().startswith("powershell")]


def is_running(work: dict, commandlines: list[str] | None = None) -> bool:
    """True if any live (non-powershell, non-self) process CommandLine contains
    a match token. If `detect` is False we never track running state. Pass a
    pre-scanned `commandlines` list (from scan_commandlines) to avoid spawning
    a powershell per call."""
    if work.get("detect") is False:
        return False
    if jobs.eligible(work) and jobs.managed(work.get("id", ""), _NEVER_SEED_GUI):
        return True
    tokens = titles_for(work)
    if not tokens:
        return False
    if commandlines is None:
        commandlines = scan_commandlines()
    for line in commandlines:
        for t in tokens:
            if t and _identity_token_matches(t, line):
                return True
    return False


def registry_running() -> list[dict]:
    """Return registry entries whose work is still alive. This is the list kc
    uses to display and kill currently-running works. Scans processes once."""
    data = store._load_registry()
    out = []
    manifest = manifest_mod.load_manifest()
    commandlines = scan_commandlines()
    for wid, info in data.items():
        w = manifest_mod.work_by_id(manifest, wid)
        if w and is_running(w, commandlines):
            out.append({"id": wid, **info})
    return out


def live_running(manifest: dict | None = None, commandlines: list[str] | None = None) -> list[dict]:
    """Return all works currently detected as running LIVE (not just what wc
    registered). Used by kc to list + kill works you started by any means.
    Pass a pre-scanned `commandlines` (from scan_commandlines) to do the whole
    scan in a single powershell call instead of one per work."""
    if manifest is None:
        manifest = manifest_mod.load_manifest()
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
