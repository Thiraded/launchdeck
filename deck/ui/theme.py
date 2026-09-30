"""Palettes, fonts, log colors. TH_* are rebound by _apply_palette:
always read them as theme.TH_X (never `from theme import TH_X`)."""

# ANSI fg name (launchdeck_core.ansi_runs) -> viewer color. Server logs assume a
# dark console, so the log viewer is dark too (docker-logs style).
LOG_FG = {
    "black": "#808080", "red": "#cd3131", "green": "#0dbc79",
    "yellow": "#e5e510", "blue": "#2472c8", "magenta": "#bc3fbc",
    "cyan": "#11a8cd", "white": "#e5e5e5", "gray": "#767676",
    "bright-red": "#f14c4c", "bright-green": "#23d18b",
    "bright-yellow": "#f5f543", "bright-blue": "#3b8eea",
    "bright-magenta": "#d670d6", "bright-cyan": "#29b8db",
    "bright-white": "#ffffff",
}

# Work icons: SVG names (assets/icons). works.json written before
# 2026-09-30 holds emoji; EMOJI_ICON maps those so old manifests render
# the same icon without a migration.
ICON_CHOICES = ["zap", "monitor", "gamepad-2", "globe", "package", "rocket",
                "wrench", "palette", "bot", "database", "file-text", "music",
                "terminal", "server", "code", "map", "app-window"]
EMOJI_ICON = dict(zip(["\u26a1", "\U0001f5a5", "\U0001f3ae", "\U0001f310",
                       "\U0001f4e6", "\U0001f680", "\U0001f527", "\U0001f3a8",
                       "\U0001f916", "\U0001f4be", "\U0001f4dd", "\U0001f3b5"],
                      ICON_CHOICES))

DOT_ON, DOT_OFF = "🟢", "⚪"

# -- themes (stdlib tk only, no deps) -----------------------------------------
# tkinter can't do rounded corners or shadows, so hierarchy comes from
# spacing + hairlines + ONE accent. Blue = primary action only, red =
# destructive only, everything else quiet gray. The log viewer stays dark
# in both themes (server logs assume a dark console).
PALETTES = {
    "dark": {
        "BG": "#15171C", "CARD": "#1F232B", "CARD_EDGE": "#2E3542",
        "FIELD": "#2A303B", "INPUT_FG": "#FFFFFF",
        "FG": "#EDEFF2", "DIM": "#8F97A5", "FAINT": "#5D6572",
        "ACCENT": "#3E7BFA", "ACCENT_HI": "#5B92FF",
        "BTN": "#2A303B", "BTN_HI": "#374052",
        "DANGER": "#E5534B", "DANGER_HI": "#F1655C",
        "GREEN": "#3FB950", "GRAY": "#596069",
    },
    "light": {
        "BG": "#E9ECF1", "CARD": "#FFFFFF", "CARD_EDGE": "#D4DAE3",
        "FIELD": "#E2E7EE", "INPUT_FG": "#1A1D21",
        "FG": "#1B1E23", "DIM": "#5C6470", "FAINT": "#8A93A0",
        "ACCENT": "#2F6BEE", "ACCENT_HI": "#3E7BFA",
        "BTN": "#E0E5EC", "BTN_HI": "#CFD6E0",
        "DANGER": "#D92D20", "DANGER_HI": "#B42318",
        "GREEN": "#1A7F37", "GRAY": "#A6AEB9",
    },
}

_TH_KEYS = ("BG", "CARD", "CARD_EDGE", "FIELD", "INPUT_FG", "FG", "DIM",
            "FAINT", "ACCENT", "ACCENT_HI", "BTN", "BTN_HI", "DANGER",
            "DANGER_HI", "GREEN", "GRAY")

def _apply_palette(name):
    """Point the TH_* globals at a palette. Widgets read them at build
    time, so a theme switch = apply + full rebuild (see _rebuild)."""
    pal = PALETTES.get(name, PALETTES["dark"])
    g = globals()
    for k in _TH_KEYS:
        g["TH_" + k] = pal[k]
    return name if name in PALETTES else "dark"

_apply_palette("dark")

TH_FONT = ("Segoe UI", 10)

TH_FONT_B = ("Segoe UI", 10, "bold")

TH_FONT_S = ("Segoe UI", 8)

TH_FONT_TITLE = ("Segoe UI", 13, "bold")

TH_FONT_SECTION = ("Segoe UI", 10, "bold")
