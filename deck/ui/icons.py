"""SVG icons for Tk, stdlib only (Tk 8.6 has no SVG, no Pillow allowed).

assets/icons/*.svg (Lucide-style: 24 grid, stroke 2, round caps) are
parsed into polylines, rasterized ANTIALIASED into an alpha mask
(strokes by distance-to-segment, fills by supersampled scanline), then
tinted and composited over an optional plate (circle / pill) into an
RGBA PNG that Tk's PhotoImage loads natively.

Canvas polygons can't do this: Tk on Windows draws them without AA.

Supported SVG subset (all our assets use nothing else): path (every
command incl. arcs), line, polyline, polygon, rect (rx/ry), circle,
ellipse; attributes fill / stroke / stroke-width, inherited from <svg>.

Public:
  mask(name, size)                      -> bytearray alpha (size*size)
  png(name, size, color, ...)           -> PNG bytes (no Tk needed)
  photo(name, size, color, ...)         -> cached tk.PhotoImage
  plate_png(w, h, color, radius=None)   -> PNG of a rounded plate only
"""
from __future__ import annotations

import base64
import math
import re
import struct
import xml.etree.ElementTree as ET
import zlib
from functools import lru_cache
from pathlib import Path

ICON_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons"
_SS = 4  # vertical subsamples per pixel for fills

# -- colors -------------------------------------------------------------------

_NAMED = {"white": (255, 255, 255), "black": (0, 0, 0)}


def rgb(color) -> tuple[int, int, int]:
    """'#RRGGBB' / '#RGB' / 'white' / (r, g, b) -> (r, g, b)."""
    if isinstance(color, tuple):
        return color
    c = str(color).strip().lower()
    if c in _NAMED:
        return _NAMED[c]
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        raise ValueError(f"unsupported color {color!r}")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


# -- SVG parsing --------------------------------------------------------------

_ARC_FLAGS = re.compile(r"[01]")

def _arc_points(x1, y1, rx, ry, phi, fa, fs, x2, y2):
    """SVG arc (endpoint form) -> points after the start (spec F.6.5)."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [(x2, y2)]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if lam > 1:
        s = math.sqrt(lam)
        rx, ry = rx * s, ry * s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx = cp * cxp - sp * cyp + (x1 + x2) / 2
    cy = sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry,
             (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not fs and dt > 0:
        dt -= 2 * math.pi
    elif fs and dt < 0:
        dt += 2 * math.pi
    n = max(4, int(abs(dt) * max(rx, ry) * 1.5))
    out = []
    for i in range(1, n + 1):
        t = t1 + dt * i / n
        x = cx + rx * math.cos(t) * cp - ry * math.sin(t) * sp
        y = cy + rx * math.cos(t) * sp + ry * math.sin(t) * cp
        out.append((x, y))
    out[-1] = (x2, y2)
    return out


def _bez(p0, p1, p2, p3, n=12):
    out = []
    for i in range(1, n + 1):
        t = i / n
        u = 1 - t
        out.append((u * u * u * p0[0] + 3 * u * u * t * p1[0]
                    + 3 * u * t * t * p2[0] + t * t * t * p3[0],
                    u * u * u * p0[1] + 3 * u * u * t * p1[1]
                    + 3 * u * t * t * p2[1] + t * t * t * p3[1]))
    return out
_NUM = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_CMD_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4,
             "T": 2, "A": 7, "Z": 0}


class _Scan:
    """Char scanner for path data (arc flags can be glued: 'a1 1 0 011 1')."""

    def __init__(self, d):
        self.d, self.i = d, 0

    def _skip(self):
        while self.i < len(self.d) and self.d[self.i] in " \t\r\n,":
            self.i += 1

    def cmd(self):
        self._skip()
        if self.i < len(self.d) and self.d[self.i].isalpha():
            self.i += 1
            return self.d[self.i - 1]
        return None

    def more(self):
        self._skip()
        return self.i < len(self.d) and not self.d[self.i].isalpha()

    def num(self):
        self._skip()
        m = _NUM.match(self.d, self.i)
        if not m:
            raise ValueError(f"bad path data at {self.i}: {self.d[self.i:self.i+10]!r}")
        self.i = m.end()
        return float(m.group())

    def flag(self):
        self._skip()
        m = _ARC_FLAGS.match(self.d, self.i)
        if not m:
            raise ValueError(f"bad arc flag at {self.i}")
        self.i += 1
        return m.group() == "1"


def _path_points(d: str):
    """Path data -> [(points, closed)] in user units."""
    sc = _Scan(d)
    subs, pts = [], []
    x = y = sx = sy = 0.0
    lc = lq = None  # last cubic / quad control point (for S / T)
    cmd = None
    while True:
        c = sc.cmd()
        if c is None:
            if cmd is None or not sc.more():
                break
            if cmd in "Zz":
                raise ValueError("numbers after closepath")
            c = cmd  # implicit repeat
        if c in "Zz":
            if pts:
                subs.append((pts, True))
            pts = []
            x, y = sx, sy
            cmd, lc, lq = c, None, None
            continue
        rel = c.islower()
        C = c.upper()
        first = True
        while first or sc.more():
            first = False
            ox, oy = (x, y) if rel else (0.0, 0.0)
            if C == "M":
                if pts:
                    subs.append((pts, False))
                x, y = ox + sc.num(), oy + sc.num()
                sx, sy = x, y
                pts = [(x, y)]
                C = "L"  # subsequent pairs are lineto
                lc = lq = None
                continue
            if not pts:
                pts = [(x, y)]
            if C == "L":
                x, y = ox + sc.num(), oy + sc.num()
                pts.append((x, y))
                lc = lq = None
            elif C == "H":
                x = ox + sc.num()
                pts.append((x, y))
                lc = lq = None
            elif C == "V":
                y = oy + sc.num()
                pts.append((x, y))
                lc = lq = None
            elif C in "CS":
                if C == "C":
                    c1 = (ox + sc.num(), oy + sc.num())
                else:
                    c1 = (2 * x - lc[0], 2 * y - lc[1]) if lc else (x, y)
                c2 = (ox + sc.num(), oy + sc.num())
                end = (ox + sc.num(), oy + sc.num())
                pts.extend(_bez((x, y), c1, c2, end))
                lc, lq = c2, None
                x, y = end
            elif C in "QT":
                if C == "Q":
                    q = (ox + sc.num(), oy + sc.num())
                else:
                    q = (2 * x - lq[0], 2 * y - lq[1]) if lq else (x, y)
                end = (ox + sc.num(), oy + sc.num())
                c1 = (x + 2 / 3 * (q[0] - x), y + 2 / 3 * (q[1] - y))
                c2 = (end[0] + 2 / 3 * (q[0] - end[0]),
                      end[1] + 2 / 3 * (q[1] - end[1]))
                pts.extend(_bez((x, y), c1, c2, end))
                lq, lc = q, None
                x, y = end
            elif C == "A":
                rx, ry, phi = sc.num(), sc.num(), sc.num()
                fa, fs = sc.flag(), sc.flag()
                end = (ox + sc.num(), oy + sc.num())
                pts.extend(_arc_points(x, y, rx, ry, phi, fa, fs, *end))
                x, y = end
                lc = lq = None
            else:
                raise ValueError(f"unsupported path command {c!r}")
        # an implicit repeat after M/m is lineto (SVG spec)
        cmd = ("l" if rel else "L") if c in "Mm" else c
    if pts:
        subs.append((pts, False))
    return subs


def _f(el, key, default=0.0):
    v = el.get(key)
    return float(v) if v not in (None, "") else default


def _shape_to_d(el) -> str | None:
    """Non-path primitives -> path data (one parser for everything)."""
    tag = el.tag.rsplit("}", 1)[-1]
    if tag == "path":
        return el.get("d", "")
    if tag == "line":
        return (f"M{_f(el, 'x1')} {_f(el, 'y1')}"
                f"L{_f(el, 'x2')} {_f(el, 'y2')}")
    if tag in ("polyline", "polygon"):
        nums = [float(n) for n in _NUM.findall(el.get("points", ""))]
        if len(nums) < 4:
            return None
        d = f"M{nums[0]} {nums[1]}" + "".join(
            f"L{nums[i]} {nums[i + 1]}" for i in range(2, len(nums) - 1, 2))
        return d + ("Z" if tag == "polygon" else "")
    if tag == "rect":
        x, y = _f(el, "x"), _f(el, "y")
        w, h = _f(el, "width"), _f(el, "height")
        rx = el.get("rx")
        ry = el.get("ry")
        rx = float(rx) if rx else (float(ry) if ry else 0.0)
        ry = float(ry) if ry else rx
        rx, ry = min(rx, w / 2), min(ry, h / 2)
        if not rx:
            return f"M{x} {y}h{w}v{h}h{-w}Z"
        return (f"M{x + rx} {y}H{x + w - rx}A{rx} {ry} 0 0 1 {x + w} {y + ry}"
                f"V{y + h - ry}A{rx} {ry} 0 0 1 {x + w - rx} {y + h}"
                f"H{x + rx}A{rx} {ry} 0 0 1 {x} {y + h - ry}"
                f"V{y + ry}A{rx} {ry} 0 0 1 {x + rx} {y}Z")
    if tag in ("circle", "ellipse"):
        cx, cy = _f(el, "cx"), _f(el, "cy")
        if tag == "circle":
            rx = ry = _f(el, "r")
        else:
            rx, ry = _f(el, "rx"), _f(el, "ry")
        return (f"M{cx - rx} {cy}A{rx} {ry} 0 1 0 {cx + rx} {cy}"
                f"A{rx} {ry} 0 1 0 {cx - rx} {cy}Z")
    return None


@lru_cache(maxsize=None)
def load(name: str):
    """Parse assets/icons/<name>.svg -> (viewbox_size, [(pts, closed, fill, stroke_w)])."""
    root = ET.parse(ICON_DIR / f"{name}.svg").getroot()
    vb = [float(v) for v in root.get("viewBox", "0 0 24 24").split()]
    base_fill = root.get("fill", "none")
    base_stroke = root.get("stroke", "none")
    base_sw = _f(root, "stroke-width", 1.0)
    shapes = []
    for el in root.iter():
        if el is root:
            continue
        d = _shape_to_d(el)
        if not d:
            continue
        fill = el.get("fill", base_fill) not in ("none", "")
        stroke = el.get("stroke", base_stroke) not in ("none", "")
        sw = _f(el, "stroke-width", base_sw) if stroke else 0.0
        for pts, closed in _path_points(d):
            shapes.append(([(px - vb[0], py - vb[1]) for px, py in pts],
                           closed, fill, sw))
    return max(vb[2], vb[3]), tuple(shapes)


# -- rasterizer ---------------------------------------------------------------

def _stroke_into(buf, size, pts, closed, hw):
    """Max-accumulate AA coverage of a round-capped polyline (half-width hw)."""
    segs = list(zip(pts, pts[1:]))
    if closed and len(pts) > 1:
        segs.append((pts[-1], pts[0]))
    if not segs:
        segs = [(pts[0], pts[0])]
    r = hw + 0.5
    for (ax, ay), (bx, by) in segs:
        dx, dy = bx - ax, by - ay
        ll = dx * dx + dy * dy
        x0 = max(0, int(min(ax, bx) - r))
        x1 = min(size - 1, int(max(ax, bx) + r) + 1)
        y0 = max(0, int(min(ay, by) - r))
        y1 = min(size - 1, int(max(ay, by) + r) + 1)
        for py in range(y0, y1 + 1):
            cy = py + 0.5
            row = py * size
            for px in range(x0, x1 + 1):
                cx = px + 0.5
                if ll:
                    t = ((cx - ax) * dx + (cy - ay) * dy) / ll
                    t = 0.0 if t < 0 else 1.0 if t > 1 else t
                    qx, qy = ax + t * dx - cx, ay + t * dy - cy
                else:
                    qx, qy = ax - cx, ay - cy
                cov = hw + 0.5 - math.sqrt(qx * qx + qy * qy)
                if cov > 0:
                    cov = 1.0 if cov >= 1 else cov
                    if cov > buf[row + px]:
                        buf[row + px] = cov


def _fill_into(buf, size, polys):
    """Nonzero-winding AA fill of closed polygons (supersampled rows)."""
    edges = []
    for pts in polys:
        n = len(pts)
        for i in range(n):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
            if y0 != y1:
                edges.append((x0, y0, x1, y1, 1 if y1 > y0 else -1))
    if not edges:
        return
    acc = [0.0] * (size * size)
    step = 1.0 / _SS
    for py in range(size):
        for s in range(_SS):
            sy = py + (s + 0.5) * step
            xs = []
            for x0, y0, x1, y1, w in edges:
                lo, hi = (y0, y1) if y0 < y1 else (y1, y0)
                if lo <= sy < hi:
                    xs.append((x0 + (sy - y0) * (x1 - x0) / (y1 - y0), w))
            if not xs:
                continue
            xs.sort()
            wind = 0
            for i in range(len(xs) - 1):
                wind += xs[i][1]
                if not wind:
                    continue
                a, b = max(0.0, xs[i][0]), min(float(size), xs[i + 1][0])
                if b <= a:
                    continue
                row = py * size
                ia, ib = int(a), int(b)
                if ia == ib:
                    acc[row + ia] += (b - a) * step
                    continue
                acc[row + ia] += (ia + 1 - a) * step
                for px in range(ia + 1, min(ib, size)):
                    acc[row + px] += step
                if ib < size:
                    acc[row + ib] += (b - ib) * step
    for i, v in enumerate(acc):
        if v > buf[i]:
            buf[i] = 1.0 if v > 1 else v


@lru_cache(maxsize=512)
def mask(name: str, size: int, stroke: float | None = None) -> tuple:
    """Alpha coverage (0..1 floats, row-major size*size) for icon `name`.

    `stroke` overrides the SVG stroke-width (in viewBox units)."""
    vb, shapes = load(name)
    k = size / vb
    buf = [0.0] * (size * size)
    fills = []
    for pts, closed, fill, sw in shapes:
        sp = [(x * k, y * k) for x, y in pts]
        if fill and len(sp) > 2:
            fills.append(sp)
        if sw:
            _stroke_into(buf, size, sp, closed, (stroke or sw) * k / 2)
    if fills:
        _fill_into(buf, size, fills)
    return tuple(buf)


def _plate_cov(w, h, radius, px, py):
    """AA coverage of a rounded rect [0,w]x[0,h] with corner `radius`."""
    cx, cy = px + 0.5, py + 0.5
    qx = abs(cx - w / 2) - (w / 2 - radius)
    qy = abs(cy - h / 2) - (h / 2 - radius)
    ox, oy = max(qx, 0.0), max(qy, 0.0)
    dist = math.sqrt(ox * ox + oy * oy) + min(max(qx, qy), 0.0) - radius
    cov = 0.5 - dist
    return 0.0 if cov <= 0 else 1.0 if cov >= 1 else cov


def _encode_png(w, h, rgba: bytearray) -> bytes:
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(
            ">I", zlib.crc32(c) & 0xFFFFFFFF)
    stride = w * 4
    raw = b"".join(b"\x00" + bytes(rgba[y * stride:(y + 1) * stride])
                   for y in range(h))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


def compose(name, size, color, box=None, plate=None, plate_shape="circle",
            radius=None, stroke=None) -> bytes:
    """PNG: icon tinted `color`, centered in `box` (int or (w, h)),
    optionally over a `plate` color. plate_shape: circle | pill | rounded.
    name=None renders the plate alone."""
    bw, bh = (box, box) if isinstance(box, int) else (box or (size, size))
    if plate_shape == "circle":
        rad = min(bw, bh) / 2
    elif plate_shape == "pill":
        rad = bh / 2
    else:
        rad = radius if radius is not None else min(bw, bh) / 4
    out = bytearray(bw * bh * 4)
    pr, pg, pb = rgb(plate) if plate else (0, 0, 0)
    if plate:
        for py in range(bh):
            for px in range(bw):
                a = _plate_cov(bw, bh, rad, px, py)
                if a:
                    i = (py * bw + px) * 4
                    out[i:i + 4] = bytes((pr, pg, pb, int(a * 255 + 0.5)))
    if name:
        cr, cg, cb = rgb(color)
        m = mask(name, size, stroke)
        ox, oy = (bw - size) // 2, (bh - size) // 2
        for y in range(size):
            ty = y + oy
            if not 0 <= ty < bh:
                continue
            for x in range(size):
                a = m[y * size + x]
                tx = x + ox
                if not a or not 0 <= tx < bw:
                    continue
                i = (ty * bw + tx) * 4
                da = out[i + 3] / 255
                oa = a + da * (1 - a)
                out[i] = int((cr * a + out[i] * da * (1 - a)) / oa + 0.5)
                out[i + 1] = int((cg * a + out[i + 1] * da * (1 - a)) / oa + 0.5)
                out[i + 2] = int((cb * a + out[i + 2] * da * (1 - a)) / oa + 0.5)
                out[i + 3] = int(oa * 255 + 0.5)
    return _encode_png(bw, bh, out)


_PHOTOS: dict = {}


def photo(name, size, color, **kw):
    """Cached tk.PhotoImage of compose(...). Cache is per Tk interpreter
    (a destroyed root invalidates its images)."""
    import tkinter as tk
    root = tk._default_root
    key = (id(root), name, size, str(color), tuple(sorted(kw.items())))
    img = _PHOTOS.get(key)
    if img is None:
        img = tk.PhotoImage(
            data=base64.b64encode(compose(name, size, color, **kw)))
        _PHOTOS[key] = img
    return img


def clear_cache():
    """Drop PhotoImages (theme switch / root rebuild)."""
    _PHOTOS.clear()


def names() -> list[str]:
    return sorted(p.stem for p in ICON_DIR.glob("*.svg"))
