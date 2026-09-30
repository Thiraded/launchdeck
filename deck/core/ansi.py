"""ANSI SGR -> (text, color) runs for the log viewer."""

import re

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

    Pure helper for the deck log viewer (core stays UI-free; the viewer
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
