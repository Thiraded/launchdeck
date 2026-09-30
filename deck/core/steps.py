"""Inline steps/vars -> generated launcher .bat; log paths; editor text forms."""

import os
import re

from deck.core import common

# --------------------------------------------------------------------------
# run / kill
# --------------------------------------------------------------------------
def work_log_path(work: dict) -> str:
    """Log file for a detached work (docker-logs equivalent). Under
    wc_logs/ (git-ignored). Created on first detached launch."""
    wid = work.get("id", "work")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in wid)
    d = os.path.join(str(common.HERE), "wc_logs")
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


GEN_BAT_PREFIX = "launchdeck-gen-"


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
    """Write `wc_logs/launchdeck-gen-<id>.bat` from `steps`+`vars`; return its path.

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
    # The label is user text: unescaped, `A & calc` ran `calc` from `title`.
    lines.append("title " + _cmd_escape(label))
    terms = [s for s in steps if (s.get("type") or "terminal") == "terminal"]
    last_term = terms[-1] if terms else None
    has_cd = False
    for s in steps:
        cmd = str(s.get("cmd", "")).strip()
        if not cmd:
            continue
        if (s.get("type") or "terminal") == "app":
            lines.append(f'start "" {cmd}')
        elif visible and s is last_term:
            lines.append(f'cmd /k "{cmd}"')
        elif _is_cd_step(cmd):
            # A missing drive/dir used to fall through and run the next step
            # (npm run dev) in the launcher's directory. Other steps keep
            # plain semantics on purpose (`mkdir ... 2>nul` is expected to
            # fail when the dir exists).
            lines.append(cmd + " || goto :deck_cd_failed")
            has_cd = True
        else:
            lines.append(cmd)
    lines.append("exit /b 0")
    if has_cd:
        # goto-label guard, never a (...) block (see bat-template.md).
        lines += [":deck_cd_failed",
                  "echo [deck] working directory not found -- steps aborted",
                  "exit /b 1"]
    body = chr(13) + chr(10)
    text = body.join(lines) + body
    if not text.isascii():
        # cmd parses .bat files in the OEM codepage; switch to UTF-8 first
        # so non-ASCII paths/labels survive (ASCII scripts stay untouched).
        text = "@chcp 65001 >nul" + body + text
    d = os.path.join(str(common.HERE), "wc_logs")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, gen_bat_name(work))
    # cmd.exe reads a running .bat by byte offset: rewriting it under a live
    # instance makes that instance resume mid-way through the NEW text. Only
    # write when the content actually changed (the Restart case is identical).
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            if f.read() == text:
                return path
    except (OSError, UnicodeDecodeError):
        pass
    with open(path, "w", encoding="utf-8", errors="replace", newline="") as f:
        f.write(text)
    return path


_CMD_META = "^&|<>()"


def _cmd_escape(text: str) -> str:
    """Escape cmd metacharacters so *text* is literal on an unquoted line."""
    out = str(text).replace("%", "%%")
    return "".join("^" + ch if ch in _CMD_META else ch for ch in out)


def _is_cd_step(cmd: str) -> bool:
    low = cmd.strip().lower()
    return low == "cd" or low.startswith(("cd ", "cd/", "cd\\", "cd\"",
                                          "chdir ", "pushd "))


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
