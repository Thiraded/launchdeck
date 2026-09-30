"""Themed Tk building blocks (buttons, circle icons, links)."""
import re
import tkinter as tk
import webbrowser

from deck.ui import dpi, icons, theme

_ICON_SET = frozenset(icons.names())


URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")

def _tag_links(txt, start, end):
    """Tag URL substrings in [start, end) with the clickable link tag."""
    try:
        text = txt.get(start, end)
    except Exception:
        return
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:!?)]")
        if not url:
            continue
        a = f"{start}+{m.start()}c"
        b = f"{start}+{m.start() + len(url)}c"
        try:
            txt.tag_add("link", a, b)
        except Exception:
            pass

def _open_link(event):
    """Open the clicked link-tagged URL in the default browser."""
    try:
        w = event.widget
        idx = w.index(f"@{event.x},{event.y}")
        rng = w.tag_prevrange("link", f"{idx}+1c") or w.tag_nextrange("link", idx)
        if rng:
            webbrowser.open(w.get(rng[0], rng[1]).strip())
    except Exception:
        pass
    return "break"

# Legacy glyph -> SVG icon name (assets/icons). Call sites may pass
# either; an unknown glyph falls back to text so nothing ever vanishes.
GLYPH_ICON = {
    "▶": "play", "⏹": "stop", "■": "stop", "🗑": "trash-2", "✎": "pencil",
    "↻": "rotate-cw", "⟳": "rotate-cw", "☰": "file-text", "▾": "chevron-down",
    "▸": "chevron-right", "▲": "chevron-up", "▼": "chevron-down",
    "×": "x", "✕": "x", "⌨": "settings", "+": "plus", "⧉": "copy",
}


def icon_name(glyph):
    """Glyph or icon name -> icon name, or None when neither is known."""
    if not glyph:
        return None
    name = GLYPH_ICON.get(glyph) or theme.EMOJI_ICON.get(glyph) or glyph
    return name if name in _ICON_SET else None


def _style_colors(style, parent_bg):
    """(fill, hover_fill, fg, hover_fg) per button style."""
    if style == "accent":
        return theme.TH_ACCENT, theme.TH_ACCENT_HI, "white", "white"
    if style == "danger":
        return parent_bg, theme.TH_DANGER, theme.TH_DIM, "white"
    if style == "ghost":
        return parent_bg, theme.TH_BTN_HI, theme.TH_DIM, theme.TH_FG
    return theme.TH_BTN, theme.TH_BTN_HI, theme.TH_FG, theme.TH_FG


def _parent_bg(parent):
    try:
        return parent.cget("bg")
    except Exception:
        return theme.TH_CARD


def th_button(parent, text, command, width=8, accent=False, style=None,
              icon=None):
    """Themed button. style: None (secondary) | 'accent' | 'ghost' | 'danger'.

    `accent=True` is shorthand for style='accent' (kept for old call sites).
    Ghost/danger blend into the parent surface (dim text, no box) so the
    primary action is the only thing that shouts; hover still fills.
    `icon` (SVG name) puts a tinted icon left of the text; the button then
    sizes to its content (Tk measures width in pixels once an image is set).
    """
    if accent:
        style = "accent"
    parent_bg = _parent_bg(parent)
    bg, abg, fg, hfg = _style_colors(style, parent_bg)
    if style == "danger":
        fg = theme.TH_DANGER
    kw = dict(width=width)
    b = tk.Button(parent, text=text, command=command,
                  font=("Segoe UI", 9), relief="flat", bd=0, padx=8, pady=3,
                  cursor="hand2", bg=bg, fg=fg,
                  activebackground=abg, activeforeground="white")
    b._style = style
    if icon:
        set_button_icon(b, icon, fg)
    else:
        b.config(**kw)
    if style == "ghost":
        b.bind("<Enter>", lambda _e, w=b: _hover_button(w, True))
        b.bind("<Leave>", lambda _e, w=b: _hover_button(w, False))
    return b


def set_button_icon(b, name, fg=None):
    """(Re)tint a th_button's icon; keeps text. fg defaults to its fg."""
    fg = fg or b.cget("fg")
    size = dpi.px(14)
    b._icon = name
    b._img = icons.photo(name, size, fg)
    b._img_hot = icons.photo(name, size, theme.TH_FG if b._style == "ghost"
                             else fg)
    txt = b.cget("text")
    b.config(image=b._img, compound="left", width=0,
             text=(" " + txt.lstrip()) if txt else "", padx=10)


def _hover_button(b, hot):
    b.config(fg=theme.TH_FG if hot else theme.TH_DIM)
    if getattr(b, "_icon", None):
        b.config(image=b._img_hot if hot else b._img)


def th_circle_btn(parent, glyph, command, style=None, size=24, font_size=10):
    """Circular icon button: antialiased SVG icon on a round plate.

    `glyph` is an icon name ("trash-2") or a legacy glyph ("🗑", mapped
    via GLYPH_ICON). styles: None (secondary fill) | 'accent' | 'danger'
    (dim until hovered, then red) | 'ghost' (no plate until hovered).
    Hover swaps a pre-rendered image; all icon-only actions share `size`
    (design px, DPI-scaled) so clusters line up exactly.

    Returned Label carries .recolor(fill, hover, fg) and .set_icon(glyph)
    for in-place state flips (no rebuild).
    """
    parent_bg = _parent_bg(parent)
    fill, hover, fg, hfg = _style_colors(style, parent_bg)
    box = dpi.px(size)
    st = {"fill": fill, "hover": hover, "fg": fg, "hfg": hfg,
          "glyph": glyph, "style": style, "hot": False}
    c = tk.Label(parent, bg=parent_bg, bd=0, cursor="hand2",
                 highlightthickness=0, padx=0, pady=0)

    def _img(hot):
        name = icon_name(st["glyph"])
        plate = st["hover"] if hot else st["fill"]
        if plate == parent_bg:
            plate = None  # transparent: let the surface show through
        return icons.photo(name, max(8, round(box * 0.58)),
                           st["hfg"] if hot else st["fg"],
                           box=box, plate=plate)

    def _paint():
        if icon_name(st["glyph"]):
            c.config(image=_img(st["hot"]), text="", width=0, height=0)
        else:  # unknown glyph: text fallback, same colors
            c.config(image="", text=st["glyph"], font=("Segoe UI", font_size),
                     fg=st["hfg"] if st["hot"] else st["fg"],
                     bg=(st["hover"] if st["hot"] else st["fill"]))

    def recolor(fill=None, hover=None, fg=None):
        """Restyle a live button (state flip without rebuilding the row)."""
        if fill is not None:
            st["fill"] = fill
        if hover is not None:
            st["hover"] = hover
        if fg is not None:
            st["fg"] = fg
            st["hfg"] = fg if fg == "white" else theme.TH_FG
        _paint()

    def set_icon(glyph):
        st["glyph"] = glyph
        _paint()

    def _hot(on):
        st["hot"] = on
        _paint()

    c.recolor, c.set_icon = recolor, set_icon
    c.bind("<Enter>", lambda _e: _hot(True))
    c.bind("<Leave>", lambda _e: _hot(False))
    c.bind("<Button-1>", lambda _e: command())
    _paint()
    return c


def icon_label(parent, name, color, size=16, plate=None, box=None,
               shape="circle"):
    """Static icon (no hover). Returns a Label with .set(name, color, plate).

    shape: plate shape (circle | pill | rounded). An unknown name (e.g. a
    custom emoji in works.json) renders as text on the same plate color,
    boxed to the same size so rows stay aligned.
    """
    lab = tk.Label(parent, bg=_parent_bg(parent), bd=0, padx=0, pady=0)
    bx = dpi.px(box or size)

    def set_(name, color, plate=None):
        if name and icon_name(name):
            lab.config(image=icons.photo(icon_name(name), dpi.px(size), color,
                                         box=bx, plate=plate,
                                         plate_shape=shape),
                       text="", bg=_parent_bg(parent))
        else:  # legacy emoji / unknown: text on a flat plate-colored cell
            lab.config(image=icons.photo(None, 1, color, box=bx),
                       compound="center", text=name or "", fg=color,
                       bg=plate or _parent_bg(parent),
                       font=("Segoe UI Emoji", 11))
    lab.set = set_
    set_(name, color, plate)
    return lab


def _short(text, n=22):
    """Truncate a row title so the status + icon cluster keep their room."""
    text = str(text)
    return text if len(text) <= n else text[:n - 1] + "…"
