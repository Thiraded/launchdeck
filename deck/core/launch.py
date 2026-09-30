"""run_work / launch_work / poll_launch."""

import os
import subprocess
import threading
import time
from pathlib import Path

from deck.core import common, store, steps, detect, jobs

def run_work(work: dict) -> bool:
    """Launch the work's .bat in a VISIBLE terminal window (no hidden
    self-relaunch). ONE window per work: `start` opens the window that
    hosts the .bat itself (mandatory -- without it the child would share
    wc's own console), and the .bat MUST be the §4.8 inline shape
    (`cd` -> `cls` -> `cmd /k`, no nested `start`) so a second window
    never appears. Registers it too."""
    step_list = work.get("steps") or []
    bat = work.get("bat")
    gen = ""
    if step_list:
        # Inline steps (backlog #2): materialize to a generated .bat so
        # execution, logging, detection and kill follow the SAME path as
        # .bat works. The stored `bat` (if any) is only a fallback.
        try:
            gen = steps.materialize_steps(work, visible=work.get("run") != "detached")
        except Exception:
            gen = ""
    runner = gen or bat
    if not runner or not os.path.exists(runner):
        return False
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
        try:
            logf = open(steps.work_log_path(work), "w", encoding="utf-8",
                        errors="replace")
            logf.write(f"[deck] launch {time.strftime('%Y-%m-%d %H:%M:%S')} :: {runner}\n")
            logf.flush()
            popen_kw = dict(stdout=logf, stderr=subprocess.STDOUT,
                            stdin=subprocess.DEVNULL)
            proc = None
            if jobs.eligible(work):
                # Kernel-owned identity: the job IS the kill set. If the job
                # cannot be used the child was killed before it ran; fall back.
                try:
                    proc = jobs.spawn(work["id"], ["cmd.exe", "/c", runner], **popen_kw)
                except OSError:
                    proc = None
            if proc is None:
                proc = subprocess.Popen(["cmd.exe", "/c", runner], shell=False,
                                        creationflags=common._NO_WINDOW, **popen_kw)
            logf.close()
        except Exception:
            try:
                logf.close()
            except Exception:
                pass
            return False
        store.register(work, pid=proc.pid, runner=runner)
        return True
    try:
        subprocess.Popen(["cmd.exe", "/c", "start", "", runner], shell=False)
    except Exception:
        return False
    store.register(work, runner=runner)
    return True
# A server that never exits is considered "stable" once it has been alive
# this long with no error. Launchers that exit on their own settle via the
# is_running() check turning False.
GRACE_SECONDS = 12
# HARD SAFETY CAP: if a launcher stays alive this long with no `ready` string
# and no error, we declare it `stable` and STOP polling it. This prevents wc
# from ever looping forever. (No work should need longer than this to show it
# is alive-and-well.)
STABLE_MAX_SECONDS = 60
# Runaway guard: at most LAUNCH_BURST starts of ONE work per LAUNCH_WINDOW_S.
# (Was a lifetime MAX_LAUNCHES=16 per process -- the tray lives for days, so
# the 17th Start/Restart silently did nothing until the deck was restarted.)
LAUNCH_BURST = 5
LAUNCH_WINDOW_S = 60.0

_launch_times: dict[str, list[float]] = {}
_launch_lock = threading.Lock()

ERROR_KEYWORDS = (
    "traceback", "fatal error", "error:", "exception in",
    "cannot be found", "access is denied", "connection refused",
    "command not found",
)


def launch_work(work: dict, commandlines: list[str] | None = None) -> dict | None:
    """Spawn `work`'s .bat (which launches the real background process). Returns
    a monitor record, or None if the .bat is missing. Caller (wc) decides
    whether to kill a running instance first -- this just launches.

    SAFETY: a single work can start at most LAUNCH_BURST times per
    LAUNCH_WINDOW_S (stops a runaway retry loop, never a normal session).
    """
    wid = work.get("id", "")
    if not wid:
        return None
    now = time.monotonic()
    with _launch_lock:
        recent = [t for t in _launch_times.get(wid, [])
                  if now - t < LAUNCH_WINDOW_S]
        _launch_times[wid] = recent
        if len(recent) >= LAUNCH_BURST:
            return None
    # Steps-works (backlog #2) materialize their own runner inside
    # run_work; `bat`, when present, is only a fallback for them.
    if not work.get("steps"):
        realbat = work.get("bat")
        if not realbat or not os.path.exists(realbat):
            return None
    if not run_work(work):
        return None
    with _launch_lock:
        _launch_times.setdefault(wid, []).append(time.monotonic())
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
    alive = detect.is_running(work, commandlines)
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
