"""Themed Tk building blocks (buttons, circle icons, links)."""
import re
import tkinter as tk
import webbrowser

from deck.ui import theme


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

def th_button(parent, text, command, width=8, accent=False, style=None):
    """Themed button. style: None (secondary) | 'accent' | 'ghost' | 'danger'.

    `accent=True` is shorthand for style='accent' (kept for old call sites).
    Ghost/danger blend into the parent surface (dim text, no box) so the
    primary action is the only thing that shouts; hover still fills.
    """
    if accent:
        style = "accent"
    try:
        parent_bg = parent.cget("bg")
    except Exception:
        parent_bg = theme.TH_CARD
    bg, abg, fg = theme.TH_BTN, theme.TH_BTN_HI, theme.TH_FG
    if style == "accent":
        bg, abg, fg = theme.TH_ACCENT, theme.TH_ACCENT_HI, "white"
    elif style == "ghost":
        bg, abg, fg = parent_bg, theme.TH_BTN_HI, theme.TH_DIM
    elif style == "danger":
        bg, abg, fg = parent_bg, theme.TH_DANGER, theme.TH_DANGER
    b = tk.Button(parent, text=text, command=command, width=width,
                  font=("Segoe UI", 9), relief="flat", bd=0, padx=8, pady=3,
                  cursor="hand2", bg=bg, fg=fg,
                  activebackground=abg, activeforeground="white")
    if style == "ghost":
        b.bind("<Enter>", lambda _e, w=b: w.config(fg=theme.TH_FG))
        b.bind("<Leave>", lambda _e, w=b: w.config(fg=theme.TH_DIM))
    return b

def th_circle_btn(parent, glyph, command, style=None, size=24, font_size=10):
    """Circular icon button, snug around the glyph (tk has no round Button).

    A small Canvas blended into the parent: oval fill + centered glyph.
    styles: None (secondary fill) | 'accent' | 'danger' | 'ghost'.
    Hover fills; hand cursor throughout. All icon-only actions share
    `size`, so clusters line up exactly.
    """
    try:
        parent_bg = parent.cget("bg")
    except Exception:
        parent_bg = theme.TH_CARD
    fill, hover, fg = theme.TH_BTN, theme.TH_BTN_HI, theme.TH_FG
    if style == "accent":
        fill, hover, fg = theme.TH_ACCENT, theme.TH_ACCENT_HI, "white"
    elif style == "danger":
        fill, hover, fg = parent_bg, theme.TH_DANGER, theme.TH_DANGER
    elif style == "ghost":
        fill, hover, fg = parent_bg, theme.TH_BTN_HI, theme.TH_DIM
    c = tk.Canvas(parent, width=size, height=size, highlightthickness=0,
                  bd=0, bg=parent_bg, cursor="hand2")
    oval = c.create_oval(2, 2, size - 2, size - 2, fill=fill, outline="")
    txt = c.create_text(size // 2, size // 2 - 1, text=glyph,
                        font=("Segoe UI", font_size), fill=fg)
    c._oval, c._txt = oval, txt  # for in-place updates (no rebuild)
    st = {"fill": fill, "hover": hover, "fg": fg, "style": style}

    def recolor(fill=None, hover=None, fg=None):
        """Restyle a live circle (state flip without rebuilding the row)."""
        if fill is not None:
            st["fill"] = fill
        if hover is not None:
            st["hover"] = hover
        if fg is not None:
            st["fg"] = fg
        c.itemconfig(oval, fill=st["fill"])
        c.itemconfig(txt, fill=st["fg"])

    c.recolor = recolor

    def _enter(_e):
        c.itemconfig(oval, fill=st["hover"])
        c.itemconfig(txt, fill="white" if st["style"] in ("danger", "accent")
                     else theme.TH_FG)

    def _leave(_e):
        c.itemconfig(oval, fill=st["fill"])
        c.itemconfig(txt, fill=st["fg"])

    c.bind("<Enter>", _enter)
    c.bind("<Leave>", _leave)
    c.bind("<Button-1>", lambda _e: command())
    return c

def _short(text, n=22):
    """Truncate a row title so the status + icon cluster keep their room."""
    text = str(text)
    return text if len(text) <= n else text[:n - 1] + "…"
