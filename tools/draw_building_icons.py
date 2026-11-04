"""Draws the barge's building icons as vector stencils and writes them to data/ui/buildings/.

Format taken from the game's own ui/buildings/icons/dwarf_spirit_of_grungni_*.png: 74x74 RGBA, one flat
ink colour in RGB (green 26,42,27; the hull chain neutral 24,24,24), the drawing lives in alpha, 204 at most,
secondary parts around 130, a faint worn mottling on top. The burnt parchment tile (building_frame.png) and the
available or locked look come from the UI, so an icon has no tile and no disabled twin.

Runs on Python 3.10+ with Pillow, numpy, scipy, shapely. The vanilla icons for the sheet are read through
gamepack.py, which needs py -3.14, so that part runs in a subprocess.

    python tools/draw_building_icons.py                 all icons, the sheets, README
    python tools/draw_building_icons.py --only a,b      only these short keys, to a preview file
    python tools/draw_building_icons.py --preview FILE  also a big preview of what was drawn
"""
import argparse
import math
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter
from shapely import affinity as AF
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union as U

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ui" / "buildings"
SIZE = 74
SCALE = 12
N = SIZE * SCALE
PREFIX = "wh3_dlc25_dwarf_spirit_of_grungni_"
GREEN = (26, 42, 27)
GREY = (24, 24, 24)
MAX_ALPHA = 204
T1, T2, T3 = 1.0, 0.64, 0.42
GAP = 0.95
FLAT, ROUND = 2, 1


# ---------------------------------------------------------------- geometry
def P(*pts):
    return Polygon(pts).buffer(0)


def R(x0, y0, x1, y1):
    return box(x0, y0, x1, y1)


def RR(x0, y0, x1, y1, r):
    return box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, quad_segs=12)


def C(x, y, r):
    return Point(x, y).buffer(r, quad_segs=32)


def E(x, y, rx, ry):
    return AF.translate(AF.scale(Point(0, 0).buffer(1, quad_segs=32), rx, ry, origin=(0, 0)), x, y)


def L(pts, w, cap=ROUND, join=ROUND):
    return LineString(pts).buffer(w / 2, cap_style=cap, join_style=join, quad_segs=12)


def BEZ(p0, p1, p2, p3, n=28):
    out = []
    for i in range(n + 1):
        t = i / n
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def ARC(x, y, r, a0, a1, n=48, ry=None):
    ry = r if ry is None else ry
    return [(x + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), y + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def RING(x, y, r, w):
    return C(x, y, r).difference(C(x, y, r - w))


def ERING(x, y, rx, ry, w):
    return E(x, y, rx, ry).difference(E(x, y, rx - w, ry - w))


def rot(g, deg, o):
    """Clockwise on the screen, the y axis points down."""
    return AF.rotate(g, deg, origin=o)


def mv(g, dx, dy):
    return AF.translate(g, dx, dy)


def mir(g, x=37):
    return AF.scale(g, -1, 1, origin=(x, 0))


def sc(g, s, o=(0, 0)):
    return AF.scale(g, s, s, origin=o)


def gear(x, y, r, teeth=10, th=2.6, hole=0.0):
    """Toothed wheel: r is the outer radius, th the tooth height."""
    pts = []
    root = r - th
    for i in range(teeth):
        a = 2 * math.pi * i / teeth
        step = 2 * math.pi / teeth
        for da, rr in ((-0.30, root), (-0.17, r), (0.17, r), (0.30, root)):
            pts.append((x + rr * math.cos(a + da * step), y + rr * math.sin(a + da * step)))
    g = Polygon(pts).buffer(0)
    return g.difference(C(x, y, hole)) if hole else g


def teardrop(x, y, w, h, lean=0.0):
    """A flame tongue: base centre (x, y), width w, tip at (x + lean, y - h)."""
    tip = (x + lean, y - h)
    left = BEZ((x - w / 2, y), (x - w * .72, y - h * .38), (tip[0] - w * .16, y - h * .62), tip)
    right = BEZ(tip, (tip[0] + w * .30, y - h * .52), (x + w * .72, y - h * .30), (x + w / 2, y))
    bottom = ARC(x, y, w / 2, 0, 180, 16)
    return Polygon(left + right + bottom).buffer(0)


def flame(x, y, w, h):
    """A heraldic fire: curling tongues over a round belly. (x, y) is the base, w and h its size."""
    def q(a, b, bulge, n=14):
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        dx, dy = b[0] - a[0], b[1] - a[1]
        c = (mx - dy * bulge, my + dx * bulge)
        return [((1 - t) ** 2 * a[0] + 2 * (1 - t) * t * c[0] + t * t * b[0],
                 (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * c[1] + t * t * b[1]) for t in np.linspace(0, 1, n)]
    # unit coordinates: x -1..1 across, y 0..1 upward
    path = [((0, 0), (-.92, .26), .34), ((-.92, .26), (-.70, .70), -.20), ((-.70, .70), (-.50, .40), .10),
            ((-.50, .40), (-.30, .90), -.26), ((-.30, .90), (-.14, .52), .12), ((-.14, .52), (.10, 1.0), -.28),
            ((.10, 1.0), (.24, .50), -.14), ((.24, .50), (.56, .80), .26), ((.56, .80), (.58, .38), -.10),
            ((.58, .38), (.90, .58), .24), ((.90, .58), (.92, .24), -.16), ((.92, .24), (0, 0), .34)]
    pts = []
    for a, b, bulge in path:
        pts += q(a, b, bulge)
    return Polygon([(x + px * w / 2, y - py * h) for px, py in pts]).buffer(0)


def flame_small(x, y, w, h):
    """A bolder fire for small sizes: overlapping tongues around a round base."""
    return U([teardrop(x, y, w * .78, h, lean=w * .03),
              teardrop(x - w * .24, y, w * .52, h * .74, lean=-w * .13),
              teardrop(x + w * .25, y, w * .50, h * .68, lean=w * .15),
              teardrop(x - w * .36, y + h * .02, w * .32, h * .42, lean=-w * .14),
              teardrop(x + w * .38, y + h * .02, w * .30, h * .36, lean=w * .13)])


def barrel(x, y, w, h):
    """Upright barrel, centre (x, y)."""
    t, b = y - h / 2, y + h / 2
    hw = w / 2
    left = BEZ((x - hw * .76, t), (x - hw * 1.08, y - h * .22), (x - hw * 1.08, y + h * .22), (x - hw * .76, b))
    right = BEZ((x + hw * .76, b), (x + hw * 1.08, y + h * .22), (x + hw * 1.08, y - h * .22), (x + hw * .76, t))
    return Polygon(left + right).buffer(0)


def hh(x, x0, x1, H):
    u = min(max((x - x0) / (x1 - x0), 0), 1)
    s = u ** .8
    return H * max(0.0, 1 - abs(2 * s - 1) ** 2.6) ** .55


def hull(x0, x1, cy, H):
    xs = np.linspace(x0, x1, 90)
    return Polygon([(x, cy - hh(x, x0, x1, H)) for x in xs] + [(x, cy + hh(x, x0, x1, H)) for x in xs[::-1]]).buffer(0)


def hull_line(x0, x1, cy, H, f, xa=None, xb=None):
    xa = x0 if xa is None else xa
    xb = x1 if xb is None else xb
    return [(x, cy + f * hh(x, x0, x1, H)) for x in np.linspace(xa, xb, 50)]


def fins(x1, cy, H):
    top = P((x1 - 9, cy - H * .34), (x1 + 1, cy - H * .66), (x1 + 5, cy - H * .66), (x1 + 5, cy - H * .10), (x1 - 4, cy - H * .10))
    bot = AF.scale(top, 1, -1, origin=(0, cy))
    return U([top, bot, R(x1 - 7, cy - 1.8, x1 + 6, cy + 1.8)])


RUNES = {
    # Angular strokes in a unit box, drawn as thick lines; stems are shared so they read like Khazalid carving.
    "a": [[(.5, 0), (.5, 1)], [(.5, .12), (.95, .42)], [(.5, .42), (.95, .72)]],
    "b": [[(.5, 0), (.05, .5), (.5, 1), (.95, .5), (.5, 0)], [(.5, .3), (.5, .7)]],
    "c": [[(.5, .35), (.5, 1)], [(.05, 0), (.5, .35), (.95, 0)], [(.2, .68), (.8, .68)]],
    "d": [[(.08, 0), (.08, 1)], [(.92, 0), (.92, 1)], [(.08, .1), (.92, .9)], [(.92, .1), (.08, .9)]],
    "e": [[(.5, 0), (.5, 1)], [(.05, .3), (.5, 0), (.95, .3)], [(.05, .95), (.5, .65), (.95, .95)]],
}


def rune(kind, x, y, h, w):
    """Glyph centred on (x, y), h tall, strokes w wide."""
    bw = h * .72
    return U([L([(x - bw / 2 + px * bw, y - h / 2 + py * h) for px, py in stroke], w, cap=FLAT, join=2)
              for stroke in RUNES[kind]])


def cannon_shape(s=1.0):
    """Side view pointing along +x, breech at x=0, axis at y=0, 40 long, returns (solid, list of ring x)."""
    outline = [(-3, -1.4), (-1.5, -2.6), (-1, -4.4), (0, -5.6), (14, -5.0), (15, -5.8), (17, -5.8), (17.5, -4.6), (35, -3.6),
               (36, -4.8), (40, -5.2), (40, 5.2), (36, 4.8), (35, 3.6), (17.5, 4.6), (17, 5.8), (15, 5.8), (14, 5.0), (0, 5.6), (-1, 4.4),
               (-1.5, 2.6), (-3, 1.4)]
    g = Polygon(outline).buffer(0).union(C(-4, 0, 2.2))
    return sc(g, s)


def bomb(x, y0, y1, w):
    """Nose down, fins on top: returns (fins, body)."""
    h = y1 - y0
    bt = y0 + h * .22
    left = BEZ((x - w * .10, bt), (x - w * .44, bt + h * .10), (x - w * .52, y1 - h * .34), (x - w * .34, y1 - h * .10))
    nose = ARC(x, y1 - h * .10, w * .34, 180, 0, 20, ry=h * .10)
    right = BEZ((x + w * .34, y1 - h * .10), (x + w * .52, y1 - h * .34), (x + w * .44, bt + h * .10), (x + w * .10, bt))
    body = Polygon(left + nose[::1] + right).buffer(0)
    fin = U([P((x - w * .10, bt + 1.5), (x - w * .36, y0 + h * .10), (x - w * .36, y0), (x + w * .36, y0), (x + w * .36, y0 + h * .10), (x + w * .10, bt + 1.5))])
    return fin, body


def basket(x, yt, yb, rt, rb):
    """Crow's nest body seen from the side: a tapered tub with a rounded rim front."""
    rim = 1.0
    return Polygon(ARC(x, yt, rt, 180, 0, 24, ry=rim) + BEZ((x + rt, yt), (x + rt, yt + (yb - yt) * .5), (x + rb + 1, yb - 1), (x + rb, yb)) +
                   ARC(x, yb, rb, 0, 180, 24, ry=2) + BEZ((x - rb, yb), (x - rb - 1, yb - 1), (x - rt, yt + (yb - yt) * .5), (x - rt, yt))).buffer(0)


def dome(x0, x1, y0, H):
    """The barge's back under a mast or nest."""
    return Polygon(ARC((x0 + x1) / 2, y0 + H, (x1 - x0) / 2, 180, 360, 60, ry=H) + [(x1, y0 + H), (x0, y0 + H)]).buffer(0)


# ---------------------------------------------------------------- canvas
class Art:
    def __init__(self):
        self.a = np.zeros((N, N), np.float32)

    def _mask(self, g):
        img = Image.new("L", (N, N), 0)
        d = ImageDraw.Draw(img)
        polys = list(getattr(g, "geoms", [g]))
        flat = []
        for p in polys:
            flat.extend(getattr(p, "geoms", [p]))
        flat = [p for p in flat if p.geom_type == "Polygon" and not p.is_empty]
        for p in sorted(flat, key=lambda q: -q.area):
            d.polygon([(x * SCALE, y * SCALE) for x, y in p.exterior.coords], fill=255)
            for hole in p.interiors:
                d.polygon([(x * SCALE, y * SCALE) for x, y in hole.coords], fill=0)
        return np.asarray(img) > 127

    def ink(self, g, t=T1, gap=GAP):
        """Paints g in tone t; the gap around it keeps it apart from what lies behind."""
        if gap:
            self.a[self._mask(g.buffer(gap, quad_segs=8))] = 0
        self.a[self._mask(g)] = t
        return self

    def cut(self, g):
        self.a[self._mask(g)] = 0
        return self

    def cutl(self, pts, w=1.0, cap=FLAT):
        return self.cut(L(pts, w, cap=cap))

    def riv(self, pts, r=.8):
        return self.cut(U([C(x, y, r) for x, y in pts]))

    def finish(self, key, tint):
        tone = Image.fromarray((np.clip(self.a, 0, 1) * 255).astype(np.uint8)).resize((SIZE, SIZE), Image.LANCZOS)
        al = np.asarray(tone, np.float32) / 255
        rng = np.random.default_rng(zlib.crc32(key.encode()))
        low = gaussian_filter(rng.random((SIZE, SIZE)), 2.4)
        low = (low - low.min()) / (low.max() - low.min())
        fine = gaussian_filter(rng.random((SIZE, SIZE)), .7)
        fine = (fine - fine.mean()) / fine.std()
        wear = 1 - np.clip(low - .35, 0, 1) * .10 - np.clip(fine, 0, 3) * .010
        wear = np.where(al < .8, wear - np.clip(fine, -2, 2) * .045, wear)
        al = np.clip(al * wear, 0, 1)
        out = np.zeros((SIZE, SIZE, 4), np.uint8)
        out[..., :3] = tint
        out[..., 3] = np.round(al * MAX_ALPHA).astype(np.uint8)
        return Image.fromarray(out, "RGBA")


# ---------------------------------------------------------------- shared parts
def crate(a, x0, y0, x1, y1, t=T1, gap=GAP, brace=True):
    a.ink(R(x0, y0, x1, y1), t, gap)
    i = 1.7
    if (x1 - x0) > 8 and brace:
        a.cut(R(x0 + i, y0 + i, x1 - i, y1 - i).difference(R(x0 + i + .9, y0 + i + .9, x1 - i - .9, y1 - i - .9)))
        a.cutl([(x0 + i + .5, y1 - i - .5), (x1 - i - .5, y0 + i + .5)], .9)
    else:
        a.cut(R(x0 + i, y0 + i, x1 - i, y1 - i).difference(R(x0 + i + .8, y0 + i + .8, x1 - i - .8, y1 - i - .8)))


def keg(a, x, y, w, h, t=T1, gap=GAP, staves=3):
    b = barrel(x, y, w, h)
    a.ink(b, t, gap)
    for dy in (-.30, .30):
        yy = y + dy * h
        a.cutl([(x - w, yy - .4), (x + w, yy - .4)], .9)
        a.cutl([(x - w, yy + 1.6), (x + w, yy + 1.6)], .9)
    for i in range(staves):
        xx = x + (i - (staves - 1) / 2) * w / (staves + 1) * 1.05
        a.cut(L([(xx, y - h * .18), (xx, y + h * .18)], .8, cap=FLAT))


def mug(a, x, y, w, h, t=T1, handle=1, foam=True, gap=GAP):
    """Tankard: (x, y) centre of the body, w wide, h tall."""
    x0, x1, y0, y1 = x - w / 2, x + w / 2, y - h / 2, y + h / 2
    hx = x1 if handle > 0 else x0
    grip = ERING(hx + handle * .5, y, w * .36, h * .32, max(w * .13, 1.6))
    a.ink(grip, t, gap)
    a.ink(R(x0, y0, x1, y1), t, gap)
    band = max(h * .13, 1.5)
    a.cutl([(x0 - 1, y0 + band * 1.7), (x1 + 1, y0 + band * 1.7)], .9)
    a.cutl([(x0 - 1, y1 - band * 1.7), (x1 + 1, y1 - band * 1.7)], .9)
    if foam:
        r = w * .24
        a.ink(U([C(x0 + r * .8, y0 - r * .25, r), C(x, y0 - r * .85, r * 1.2), C(x1 - r * .8, y0 - r * .25, r),
                 R(x0 - .4, y0 - r * .3, x1 + .4, y0 + r * .6)]), t, gap)


def target(a, x, y, r, t=T1, gap=GAP):
    a.ink(C(x, y, r), t, gap)
    a.cut(RING(x, y, r * .78, r * .16))
    a.cut(RING(x, y, r * .44, r * .16))


def rifle_shape(ln=46.0):
    """Long gun along +x, the axis at y=0."""
    stock = P((0, 2.8), (2.4, 7.2), (6, 6.6), (15, 3.0), (19, 2.6), (19, -.6), (13, -.8), (2.0, 1.4))
    lock = R(17.5, -1.8, 24, 3.2)
    trig = L([(17.5, 3.4), (16.6, 5.4)], 1.1)
    bar = R(18, -1.4, ln - 2.5, 1.2)
    muz = R(ln - 3, -2, ln, 1.8)
    sight = P((ln - 12, -1.4), (ln - 11, -3), (ln - 9.5, -1.4))
    return U([stock, lock, trig, bar, muz, sight])


def pennant(x, y, ln, h, flip=1):
    """Swallow-tailed pennant from the mast at (x, y)."""
    return Polygon([(x, y)] + BEZ((x, y), (x + flip * ln * .4, y - h * .3), (x + flip * ln * .7, y + h * .2), (x + flip * ln, y + h * .05)) +
                   [(x + flip * ln * .78, y + h * .5)] +
                   BEZ((x + flip * ln, y + h * .95), (x + flip * ln * .7, y + h * 1.1), (x + flip * ln * .4, y + h * .7), (x, y + h))).buffer(0)


def sunburst(x, y, r0, r1, n=12, w=1.1, off=0):
    return U([L([(x + r0 * math.cos(math.radians(off + i * 360 / n)), y + r0 * math.sin(math.radians(off + i * 360 / n))),
                 (x + r1 * math.cos(math.radians(off + i * 360 / n)), y + r1 * math.sin(math.radians(off + i * 360 / n)))], w, cap=FLAT)
              for i in range(n)])


# ---------------------------------------------------------------- fuselage (grey ink)
def hull_body_seams(a, x0, x1, cy, H, plates=True):
    for f in (-.56, .56):
        a.cut(L(hull_line(x0, x1, cy, H, f), .9, cap=FLAT))
    if plates:
        for xs, (f0, f1) in (((16, 27, 38, 49), (-1.1, -.56)), ((21, 33, 45), (-.56, .56)), ((16, 27, 38, 49), (.56, 1.1))):
            for x in xs:
                a.cutl([(x, cy + f0 * hh(x, x0, x1, H)), (x, cy + f1 * hh(x, x0, x1, H))], .9)


def airship_hull_1(a):
    # An open ship skeleton: a curved keel, stem and stern posts, ribs left open at the top.
    def keel_y(x):
        u = (x - 9) / 56
        return 16 + 24 * max(0.0, math.sin(math.pi * min(max(u, 0), 1))) ** .55
    xs = np.linspace(9, 65, 50)
    sh = [L([(x, keel_y(x)) for x in xs], 3.6)]
    sh.append(L(BEZ((10, 18), (7.5, 14), (7, 11), (7.6, 7.5)), 3.2, cap=FLAT))
    sh.append(L(BEZ((64, 18), (66.5, 14), (67, 11), (66.4, 7.5)), 3.2, cap=FLAT))
    for x in (14.5, 21, 27.5, 34, 40.5, 47, 53.5, 60):
        y = keel_y(x)
        lean = (x - 37) * .10
        sh.append(L(BEZ((x, y), (x + lean * .1, y - 8), (x + lean * .7, 20), (x + lean, 13)), 2.3, cap=FLAT))
    sh.append(L([(x, keel_y(x) * .46 + 13.4 * .54) for x in np.linspace(12, 62, 30)], 1.4, cap=FLAT))
    sh.append(L(BEZ((10, 16), (24, 17.6), (34, 17.6), (44, 16.8), 16), 1.6, cap=FLAT))
    ship = U(sh)
    rail_y = lambda x: 62.6 - .075 * (x - 7)
    # scaffold poles and a beam behind
    for x, d in ((16, 1), (58, -1)):
        a.ink(L([(x, rail_y(x)), (x + d, 7)], 1.7, cap=FLAT), T2, gap=0)
    a.ink(L([(11, 9), (63, 9)], 1.5, cap=FLAT), T2, gap=0)
    a.ink(ship)
    # cradles on the slip
    for x, top in ((20, 37.4), (37, 41.6), (54, 37.4)):
        y = rail_y(x)
        a.ink(P((x - 2.6, top), (x + 2.6, top), (x + 5.2, y), (x - 5.2, y)))
        a.cutl([(x - 6, y - 3.8), (x + 6, y - 3.8)], .9)
    for x, d in ((8.6, 4.6), (65.4, -4.6)):
        a.ink(L([(x, rail_y(x)), (x + d, 27)], 1.9, cap=FLAT))
    rail = P((6.5, rail_y(6.5)), (67.5, rail_y(67.5)), (67.5, rail_y(67.5) + 4), (6.5, rail_y(6.5) + 4))
    a.ink(rail)
    for x in (12, 21, 30, 39, 48, 57):
        a.cutl([(x, rail_y(x) - 1), (x + .6, rail_y(x) + 6)], 1.0)


def airship_hull_2(a):
    x0, x1, cy, H = 7, 62, 27, 19
    a.ink(fins(x1, cy, H))
    b = hull(x0, x1, cy, H)
    a.ink(b)
    hull_body_seams(a, x0, x1, cy, H)
    a.cutl([(14, cy - 20), (14, cy + 20)], 1.0)
    for f in (-.78, .78):
        a.riv([(x, cy + f * hh(x, x0, x1, H)) for x in (10, 18.5, 24.5, 30, 35.5, 41, 46.5, 52.5)], .72)
    a.riv([(x, cy) for x in (10, 18, 27, 39, 51)], .72)
    # keel strap and belly plate
    for x in (24, 46):
        a.ink(R(x - 2.2, 44, x + 2.2, 53))
    a.ink(P((11, 50), (61, 50), (58, 56), (52, 63), (20, 63), (14, 57)))
    a.cutl([(10, 55.8), (62, 55.8)], .9)
    a.riv([(x, 59.5) for x in (24, 31, 38, 45)], .85)


def airship_hull_3(a):
    x0, x1, cy, H = 6, 62, 37, 25
    a.ink(fins(x1, cy, H))
    b = hull(x0, x1, cy, H)
    a.cut(b.buffer(.6))
    a.ink(b.difference(b.buffer(-2.6)), gap=0)
    for x in (13, 20.5, 28, 35.5, 43, 50.5):
        h = hh(x, x0, x1, H)
        a.ink(L(BEZ((x, cy + h), (x + 1.4, cy + h * .35), (x + 1.4, cy - h * .35), (x, cy - h)), 1.9, cap=FLAT), gap=0)
    for f in (-.58, .58):
        a.ink(L(hull_line(x0, x1, cy, H, f, x0 + 3, x1 - 2), 1.5, cap=FLAT), gap=0)
    plaque = RR(14.5, cy - 9.5, 50.5, cy + 9.5, 3.5)
    a.ink(plaque)
    for k, x in (("a", 23), ("b", 32.5), ("c", 42)):
        a.cut(rune(k, x, cy, 13, 1.75))


def airship_hull_4(a):
    x0, x1, cy, H = 6, 62, 37, 25
    a.ink(fins(x1, cy, H))
    b = hull(x0, x1, cy, H)
    a.cut(b.buffer(.6))
    a.ink(b.difference(b.buffer(-3.2)), gap=0)
    # solid nose and tail caps
    a.ink(b.intersection(R(0, 0, 11.5, 74)), gap=0)
    a.ink(b.intersection(R(55, 0, 74, 74)), gap=0)
    st = [11.5, 22.5, 33.5, 44.5, 55]
    for f0, f1 in ((-.92, -.12), (.12, .92)):
        for xa, xb in zip(st, st[1:]):
            ya0, ya1 = cy + f0 * hh(xa, x0, x1, H), cy + f1 * hh(xa, x0, x1, H)
            yb0, yb1 = cy + f0 * hh(xb, x0, x1, H), cy + f1 * hh(xb, x0, x1, H)
            a.ink(L([(xa, ya0), (xb, yb1)], 1.45, cap=FLAT), gap=0)
            a.ink(L([(xa, ya1), (xb, yb0)], 1.45, cap=FLAT), gap=0)
    for x in st:
        h = hh(x, x0, x1, H)
        a.ink(L([(x, cy - h), (x, cy + h)], 3.0, cap=FLAT), gap=0)
    a.ink(R(8, cy - 2.4, 58, cy + 2.4), gap=.8)
    pts = []
    for x in st[1:-1]:
        h = hh(x, x0, x1, H)
        pts += [(x, cy - h * .72), (x, cy + h * .72), (x, cy)]
    a.riv(pts, .78)
    a.riv([(9, cy - 7), (9, cy + 7), (59, cy - 4.4), (59, cy + 4.4)], .85)


def airship_hull_5(a):
    x0, x1, cy, H = 6, 62, 37, 21.5
    # glow above and below
    for sgn in (-1, 1):
        ray = U([L([(x, cy + sgn * (hh(x, x0, x1, H) + 2.2)), (x + (x - 34) * .10, cy + sgn * (hh(x, x0, x1, H) + 2.2 + ln))], 1.3, cap=FLAT)
                 for x, ln in ((14, 3), (20.5, 4.5), (27, 5.5), (33.5, 6), (40, 5.5), (46.5, 4.5), (53, 3))])
        a.ink(ray, T2, gap=0)
    a.ink(fins(x1, cy, H))
    b = hull(x0, x1, cy, H)
    a.ink(b)
    for f in (-.74, .74):
        a.cut(L(hull_line(x0, x1, cy, H, f), .9, cap=FLAT))
    for f in (-.88, .88):
        a.riv([(x, cy + f * hh(x, x0, x1, H)) for x in (12, 20, 27, 34, 41, 48, 55)], .72)
    a.cut(rune("e", 19.5, cy, 16, 2.3))
    a.cut(rune("b", 33, cy, 16, 2.3))
    a.cut(rune("c", 46.5, cy, 16, 2.3))
    a.riv([(9.5, cy), (56.5, cy)], 1.1)


# ---------------------------------------------------------------- crew training
def dummy(a, x, base, s=1.0, t=T1, reach=20.0):
    """A scarecrow-like straw dummy on a post with a target on its chest; reach is half the arm span."""
    a.ink(U([L([(x - 10 * s, base - 1.2 * s), (x + 10 * s, base - 1.2 * s)], 2.6 * s, cap=FLAT),
             L([(x - 8 * s, base - .5 * s), (x, base - 11 * s)], 2.0 * s, cap=FLAT),
             L([(x + 8 * s, base - .5 * s), (x, base - 11 * s)], 2.0 * s, cap=FLAT),
             R(x - 1.7 * s, base - 20 * s, x + 1.7 * s, base)]), t)
    # straw arms: bundles that thicken and fray towards the ends, tied near the shoulder
    for sg in (-1, 1):
        ax = x + sg * reach * s
        pts = [(x, base - 41 * s), (ax - sg * 3 * s, base - 43 * s)]
        for i, dy in enumerate((-43.6, -41.4, -39.4, -37, -34.8)):
            pts += [(ax + sg * (2.6 if i % 2 == 0 else 0) * s, base + dy * s)]
        pts += [(ax - sg * 3 * s, base - 35.6 * s), (x, base - 37 * s)]
        a.ink(Polygon(pts).buffer(0), t)
        a.cutl([(x + sg * reach * s * .62, base - 44 * s), (x + sg * reach * s * .62, base - 35 * s)], .9)
    # the straw body, its hem frayed over the post
    left = BEZ((x - 8.5 * s, base - 41.5 * s), (x - 13 * s, base - 33 * s), (x - 12.5 * s, base - 24 * s), (x - 10.5 * s, base - 17.5 * s))
    right = BEZ((x + 10.5 * s, base - 17.5 * s), (x + 12.5 * s, base - 24 * s), (x + 13 * s, base - 33 * s), (x + 8.5 * s, base - 41.5 * s))
    hem = []
    for i in range(1, 10):
        hem.append((x - 10.5 * s + i * 2.1 * s, base - (14 if i % 2 else 18.4) * s))
    a.ink(Polygon(left + hem + right).buffer(0), t)
    # the sack head with a rope at the neck
    a.ink(R(x - 2 * s, base - 45 * s, x + 2 * s, base - 41 * s), t, gap=0)
    a.ink(E(x, base - 50.6 * s, 7.4 * s, 7.2 * s), t)
    a.ink(R(x - 3.6 * s, base - 45 * s, x + 3.6 * s, base - 43 * s), t, gap=.6)
    # target on the chest
    a.cut(C(x, base - 29 * s, 7.8 * s))
    a.ink(C(x, base - 29 * s, 6.2 * s), t, gap=0)
    a.cut(RING(x, base - 29 * s, 4.2 * s, 1.1 * s))


def crew_weapons_1(a):
    dummy(a, 14.6, 67, .60, T2, reach=9)
    dummy(a, 59.4, 67, .60, T2, reach=9)
    dummy(a, 37, 67.2, .98, reach=21)
    a.riv([(30.5, 52), (44.5, 48)], .85)


def crew_weapons_2(a):
    a.ink(R(7, 31, 67, 35.5), T2)
    for x, y, r in ((18.5, 19, 10), (37, 19, 10), (55.5, 19, 10)):
        a.ink(R(x - 1.3, y + r - 1, x + 1.3, 36), T1, gap=0)
        target(a, x, y, r)
    # the arrow holes in the targets
    a.riv([(21.5, 16), (34, 21.5), (58, 23)], .85)
    rf = rifle_shape(48)
    g = mv(sc(rf, 1.12), 12, 45.5)
    a.ink(rot(g, 0, (37, 46)))
    # bench
    a.ink(R(7, 55, 67, 58.6))
    a.cut(U([L([(x, 54), (x, 60)], .9, cap=FLAT) for x in (19, 37, 55)]))
    for x in (14, 60):
        a.ink(P((x - 2.4, 58.6), (x + 2.4, 58.6), (x + 3.2, 67), (x - 3.2, 67)), gap=.4)
    # rest under the barrel
    a.ink(P((47, 55), (52, 55), (50.5, 48.4), (48.5, 48.4)), gap=.5)


def crew_weapons_3(a):
    # earth bank with the target, shot burst on it, a gun firing from the near end
    a.ink(sunburst(48, 25, 12.6, 18.4, n=16, w=1.5), T2, gap=0)
    target(a, 48, 25, 11.4)
    a.ink(R(45.4, 35.4, 50.6, 42), T1, gap=0)
    bank = Polygon(BEZ((7, 67), (24, 62), (30, 40), (47, 39.5)) + BEZ((47, 39.5), (58, 39), (61, 44), (67, 47)) + [(67, 67)]).buffer(0)
    a.ink(bank, T2)
    # posts of the fence along the bank
    for x, y in ((56, 41.5), (62, 44)):
        a.ink(R(x - .9, y - 5, x + .9, y + 1), T1, gap=.4)
    # the gun, muzzle up towards the target
    g = mv(rot(sc(cannon_shape(), .86), -24, (0, 0)), 11, 49)
    a.ink(g)
    a.ink(L([(18, 53), (8, 66.4)], 3.0), gap=.7)
    wheel = C(23, 56.6, 10)
    a.ink(wheel, gap=1.1)
    a.cut(RING(23, 56.6, 7.6, 1))
    a.cut(U([L([(23 + 2.6 * math.cos(t), 56.6 + 2.6 * math.sin(t)), (23 + 6.4 * math.cos(t), 56.6 + 6.4 * math.sin(t))], 1.1, cap=FLAT)
             for t in np.linspace(0, 2 * math.pi, 6, endpoint=False)]))


# ---------------------------------------------------------------- signals
def waving_flag(x, y, ln, h, flip=1):
    top = BEZ((x, y), (x + flip * ln * .33, y - h * .24), (x + flip * ln * .62, y + h * .20), (x + flip * ln, y + h * .02))
    bot = BEZ((x + flip * ln, y + h * 1.02), (x + flip * ln * .62, y + h * 1.20), (x + flip * ln * .33, y + h * .76), (x, y + h))
    return Polygon(top + bot).buffer(0)


def support_radius_1(a):
    for flip in (1, -1):
        px, py = 37 + flip * 15, 7.2
        fl = waving_flag(px, 8.2, 15.6, 14.5, flip)
        a.ink(fl, T1)
        # a code flag: a pale square in the middle
        a.cut(R(min(px + flip * 4.4, px + flip * 11.4), 12.4, max(px + flip * 4.4, px + flip * 11.4), 18.8))
        a.ink(L([(37 - flip * 27, 67.4), (px, py)], 2.7), T1, gap=.8)
    # lamp
    a.ink(ERING(37, 22.5, 6, 6, 1.8).intersection(R(0, 0, 74, 23)), T1)
    a.ink(P((30, 30), (33, 23), (41, 23), (44, 30)))
    a.cutl([(26, 26.5), (48, 26.5)], .9)
    body = RR(25, 30, 49, 58, 3)
    a.ink(body)
    a.ink(R(23, 58, 51, 62.5))
    a.cut(C(37, 44, 10.4))
    a.ink(RING(37, 44, 8.8, 1.5), gap=0)
    a.ink(sunburst(37, 44, 2.6, 6.2, n=12, w=1.05), gap=0)
    a.ink(C(37, 44, 1.9), gap=0)
    a.riv([(27.6, 33), (46.4, 33), (27.6, 55.5), (46.4, 55.5)], .85)
    a.cutl([(23, 60.2), (51, 60.2)], .9)


def tower(a, x, base, top, w, t=T1):
    legs = U([L([(x - w, base), (x - .6, top)], 1.9, cap=FLAT), L([(x + w, base), (x + .6, top)], 1.9, cap=FLAT)])
    a.ink(legs, t)
    n = 3
    bars = []
    for i in range(1, n + 1):
        f = i / (n + 1)
        y = base + (top - base) * f
        hw = w * (1 - f)
        bars.append(L([(x - hw, y), (x + hw, y)], 1.3, cap=FLAT))
    a.ink(U(bars), t, gap=0)


def lamp_head(a, x, y, r, t=T1):
    a.ink(sunburst(x, y, r + 1.4, r + 4.6, n=10, w=1.25, off=-90), t, gap=0)
    a.ink(R(x - r * 1.05, y + r * .5, x + r * 1.05, y + r * 1.2), t, gap=0)
    a.ink(C(x, y, r), t)
    a.cut(C(x, y, r * .42))


def support_radius_2(a):
    links = [((37, 15), (15.5, 34)), ((37, 15), (58.5, 34)), ((15.5, 34), (58.5, 34))]
    for p, q in links:
        ln = LineString([p, q]).length
        n = int(ln // 4.4)
        seg = []
        for i in range(2, n - 1, 1):
            f0, f1 = i / n, (i + .58) / n
            seg.append(L([(p[0] + (q[0] - p[0]) * f0, p[1] + (q[1] - p[1]) * f0),
                          (p[0] + (q[0] - p[0]) * f1, p[1] + (q[1] - p[1]) * f1)], 1.5, cap=FLAT))
        a.ink(U(seg), T1, gap=0)
    tower(a, 37, 65, 19.5, 8.5)
    lamp_head(a, 37, 15, 4.8)
    for x in (15.5, 58.5):
        tower(a, x, 65, 39, 6.5)
        lamp_head(a, x, 34, 4)
    a.ink(R(7, 64.5, 67, 67.4))
    a.cut(U([L([(x, 64), (x, 68)], .9, cap=FLAT) for x in (22, 52)]))


# ---------------------------------------------------------------- engines
def engines_1(a):
    a.ink(R(7, 62.5, 67, 66.8))
    a.cut(U([L([(x, 62), (x, 67.5)], .9, cap=FLAT) for x in (20, 37, 54)]))
    for x in (15, 41):
        a.ink(P((x - 4, 62.5), (x + 4, 62.5), (x + 2.6, 57), (x - 2.6, 57)))
    # steam
    a.ink(U([C(10.6, 18, 2.6), C(14, 14.8, 3.2), C(18.2, 13.6, 2.2)]), T2, gap=0)
    a.ink(R(12.2, 19.5, 15.6, 29), T1)
    a.ink(R(11.2, 19, 16.6, 20.8), T1, gap=0)
    boiler = RR(7.5, 27.5, 48, 58, 8.5)
    a.ink(boiler)
    for x in (18, 37.6):
        a.cutl([(x, 27), (x, 59)], 1.0)
    a.riv([(12.8, y) for y in (33.5, 39, 44.5, 50)] + [(42.6, y) for y in (33.5, 39, 44.5, 50)], .8)
    # firebox door
    a.cut(C(27.8, 43, 8.6))
    a.ink(C(27.8, 43, 7.2), gap=0)
    a.cut(U([L([(22, y), (33.6, y)], 1.0, cap=FLAT) for y in (39.8, 43, 46.2)]))
    # gauge
    a.ink(R(25.8, 19, 29.8, 28))
    a.ink(C(27.8, 14, 7.2))
    a.cut(C(27.8, 14, 5.2))
    a.ink(L([(27.8, 14), (31.2, 10.4)], 1.3, cap=FLAT), gap=0)
    a.ink(C(27.8, 14, 1.2), gap=0)
    # steam pipe to the cylinder
    a.ink(L([(41, 28), (41, 12.5), (56.5, 12.5), (56.5, 26)], 3.2, join=1), T1)
    a.cutl([(39, 21), (43, 21)], .9)
    a.cutl([(48, 10.5), (48, 14.5)], .9)
    a.ink(RR(50, 24.5, 63, 38.5, 1))
    a.ink(R(48.4, 24.2, 64.6, 27))
    a.cut(U([L([(50, y), (63, y)], .9, cap=FLAT) for y in (31, 34.6)]))
    a.ink(R(55, 38.5, 58, 46))
    # flywheel
    g = gear(55.5, 51, 11.4, teeth=10, th=2.5)
    a.ink(g)
    a.cut(RING(55.5, 51, 7.4, 1.0))
    a.cut(C(55.5, 51, 1.9))


def engines_2(a):
    cx, cy = 37, 50
    # lift chevrons between the cylinders
    for y, tone in ((21, T2), (29, T2)):
        a.ink(L([(30.5, y + 5), (37, y), (43.5, y + 5)], 2.5, cap=FLAT, join=2), tone, gap=0)
    for sg in (-1, 1):
        ang = sg * 33
        def place(g):
            return rot(mv(g, cx, cy), ang, (cx, cy))
        a.ink(place(L([(0, 0), (0, -18)], 4.2, cap=FLAT)))
        a.ink(place(RR(-7.2, -30.5, 7.2, -13.5, 1.2)))
        a.cut(place(U([L([(-8, y), (8, y)], 1.05, cap=FLAT) for y in (-17.5, -21, -24.5)])))
        a.ink(place(R(-8.6, -33.8, 8.6, -30.3)))
        fl = flame_small(0, -35.5, 12, 15)
        a.ink(place(fl), T1, gap=.7)
        a.cut(place(teardrop(0, -36, 3.8, 8.2)))
    g = gear(cx, cy, 15, teeth=12, th=3)
    a.ink(g)
    a.cut(RING(cx, cy, 10.4, 1.15))
    a.cut(U([rot(L([(cx, cy - 3.5), (cx, cy - 8.2)], 1.5, cap=FLAT), d, (cx, cy)) for d in (0, 72, 144, 216, 288)]))
    a.cut(C(cx, cy, 2.1))
    for a0, a1, r in ((30, 150, 18.4),):
        a.ink(L(ARC(cx, cy, r, a0, a1), 1.5, cap=FLAT), T2, gap=0)


def blade(ln=33.0, w=17.0):
    """Paddle along +x from the hub."""
    top = BEZ((5, -2.8), (11, -3.2), (16, -w / 2), (ln - 7, -w / 2))
    bot = BEZ((ln - 7, w / 2), (16, w / 2), (11, 3.2), (5, 2.8))
    tip = ARC(ln - 7, 0, 7, -90, 90, 16, ry=w / 2)
    return Polygon(top + tip + bot).buffer(0)


def engines_3(a):
    cx, cy = 37, 37
    a.ink(C(cx, cy, 13), T3, gap=0)
    for r, w in ((19, 1.5), (25, 1.5), (31, 1.5)):
        a.ink(RING(cx, cy, r, w), T2, gap=0)
    for d in (45, 135, 225, 315):
        b = rot(mv(blade(40, 19), cx, cy), d, (cx, cy))
        a.ink(b, gap=1.5)
        a.cut(rot(mv(L([(13, 0), (29, 0)], 1.0, cap=FLAT), cx, cy), d, (cx, cy)))
        a.cut(rot(mv(L([(31.5, -10), (31.5, 10)], 1.0, cap=FLAT), cx, cy), d, (cx, cy)))
    a.ink(C(cx, cy, 8.6), gap=1.2)
    a.cut(RING(cx, cy, 6.4, 1.0))
    a.cut(C(cx, cy, 1.9))


# ---------------------------------------------------------------- cargo
def sack(a, x, y, w, h, t=T1, gap=GAP):
    b = Polygon(BEZ((x - w * .22, y - h / 2 + 2.4), (x - w * .72, y - h * .1), (x - w * .62, y + h / 2), (x, y + h / 2)) +
                BEZ((x, y + h / 2), (x + w * .62, y + h / 2), (x + w * .72, y - h * .1), (x + w * .22, y - h / 2 + 2.4))).buffer(0)
    a.ink(U([b, P((x - w * .26, y - h / 2), (x + w * .26, y - h / 2), (x + w * .12, y - h / 2 + 3), (x - w * .12, y - h / 2 + 3))]), t, gap)
    a.cutl([(x - w * .3, y - h / 2 + 2.6), (x + w * .3, y - h / 2 + 2.6)], .9)


def cargo_hold_1(a):
    a.ink(U([L([(10, 9), (64, 25)], 1.4, cap=FLAT), L([(64, 28), (10, 45)], 1.4, cap=FLAT), L([(10, 48), (64, 63)], 1.4, cap=FLAT)]), T3, gap=0)
    # top shelf
    crate(a, 13, 13, 28.5, 25.5)
    a.ink(U([R(33, 17, 41, 25.5), E(37, 17.6, 4, 3.2), R(35.8, 10.5, 38.2, 15), R(35, 9.5, 39, 11.5)]))
    a.cutl([(32.5, 21), (41.5, 21)], .9)
    crate(a, 44.5, 15, 60.5, 25.5)
    # middle shelf
    keg(a, 20, 37.2, 13, 16.5, staves=2)
    crate(a, 30.5, 34.5, 42.5, 45.5, brace=False)
    sack(a, 52.5, 37.5, 13.5, 16)
    # bottom shelf
    crate(a, 13, 49.5, 33.5, 64)
    keg(a, 42, 56.8, 11.5, 14.5, staves=2)
    keg(a, 54.5, 56.8, 11.5, 14.5, staves=2)
    a.ink(U([R(7.5, 7.4, 11.3, 67.6), R(62.7, 7.4, 66.5, 67.6)]), gap=.7)
    for y in (6.6, 25.6, 45.4, 64):
        a.ink(R(7.5, y, 66.5, y + 3.2), gap=.6)
    a.riv([(9.4, 8.2), (64.6, 8.2), (9.4, 27.2), (64.6, 27.2), (9.4, 47), (64.6, 47), (9.4, 65.6), (64.6, 65.6)], .72)


def cargo_hold_2(a):
    arch = U([R(7, 28, 67, 67.2), E(37, 28, 30, 21.5)]).difference(U([R(13, 28, 61, 62.8), E(37, 28, 24, 16)]))
    a.ink(arch)
    for d in (-58, -30, 0, 30, 58):
        o = (37, 28)
        if d == 0:
            continue
        a.cut(rot(L([(37, 10), (37, 4)], 1.0, cap=FLAT), d, o).buffer(0))
    a.ink(P((32.4, 5.2), (41.6, 5.2), (40, 13.4), (34, 13.4)), gap=.8)
    a.cut(U([L([(6, y), (14, y)], 1.0, cap=FLAT) for y in (37, 48, 57)]))
    a.cut(U([L([(60, y), (68, y)], 1.0, cap=FLAT) for y in (37, 48, 57)]))
    # the stock inside
    crate(a, 40, 45.4, 59.5, 62.8)
    crate(a, 42.5, 30.5, 57, 44.4, brace=False)
    keg(a, 26.4, 51.4, 22, 23.4, staves=3)
    keg(a, 26.4, 30.8, 15.6, 16.4, staves=2)


def cargo_hold_3(a):
    # the hull side with an open hatch in it
    wall = Polygon([(7, 8), (67, 8), (67, 42)] + BEZ((67, 42), (52, 49), (22, 49), (7, 42))).buffer(0)
    a.ink(wall)
    a.cut(R(20.5, 14, 53.5, 54))
    a.cutl([(7, 24), (20, 24)], .9)
    a.cutl([(54, 24), (67, 24)], .9)
    a.riv([(10.5, 11.5), (17, 11.5), (10.5, 20), (17, 20), (57, 11.5), (63.5, 11.5), (57, 20), (63.5, 20),
           (10.5, 28.5), (17, 28.5), (10.5, 37), (17, 37), (57, 28.5), (63.5, 28.5), (57, 37), (63.5, 37)], .8)
    # the beam, the hook and the crate on it
    a.ink(R(20.5, 11, 53.5, 14.6), gap=0)
    a.ink(R(35.4, 14.6, 38.6, 18.2), gap=.5)
    a.ink(L([(37, 18), (37, 23.6)], 1.8, cap=FLAT), gap=.5)
    a.ink(L([(37, 23.4), (28.6, 29.6), (45.4, 29.6), (37, 23.4)], 1.3, cap=FLAT, join=2), gap=.5)
    crate(a, 26.5, 29.4, 47.5, 44.6)
    # the flap: hinged at the bottom edge of the opening, swung out and down
    door = P((19, 49.4), (55, 49.4), (63, 66.8), (11, 66.8))
    a.ink(door)
    a.cutl([(17, 54.4), (57, 54.4)], .95)
    for fx in (.33, .67):
        x0, x1 = 19 + 36 * fx, 11 + 52 * fx
        a.cutl([(x0, 55), (x1, 67.4)], .95)
    a.ink(U([R(24, 47.2, 30, 51), R(44, 47.2, 50, 51)]), gap=.7)
    # the chains hold the flap open
    a.ink(L([(23, 15), (15.6, 63)], 1.5, cap=FLAT), gap=.6)
    a.ink(L([(51, 15), (58.4, 63)], 1.5, cap=FLAT), gap=.6)


# ---------------------------------------------------------------- beer
def beer_hall_1(a):
    a.ink(P((37, 6.5), (67, 24), (67, 28.2), (7, 28.2), (7, 24)))
    a.cut(P((37, 12.4), (57, 24.2), (17, 24.2)))
    a.ink(U([R(8.5, 30, 65.5, 33.4)]), gap=.4)
    a.ink(rune("b", 37, 18.4, 9, 1.5), gap=0)
    for x in (13.5, 60.5):
        a.ink(R(x - 4.2, 34.8, x + 4.2, 37.4), gap=0)
        a.ink(R(x - 3, 37.4, x + 3, 60), gap=0)
        a.cut(U([L([(x + dx, 39.5), (x + dx, 57.5)], .85, cap=FLAT) for dx in (-1, 1)]))
        a.ink(R(x - 4.6, 60, x + 4.6, 63), gap=0)
    a.ink(R(7, 63.8, 67, 67.2), gap=.4)
    a.cut(U([L([(x, 63), (x, 68)], .9, cap=FLAT) for x in (24, 50)]))
    mug(a, 35, 50.8, 21, 22.6, handle=1)
    # drips of foam
    a.ink(R(27.4, 40, 30, 44.2), gap=0)
    a.ink(C(28.7, 44.2, 1.3), gap=0)
    a.riv([(30, 56.8), (35, 56.8), (40, 56.8)], .8)


def ham(a, x, y, s=1.0):
    """A roast leg on the bone: the thick end left, the bone with its knob up to the right."""
    meat = Polygon(BEZ((x - 10.5 * s, y + 3 * s), (x - 13.5 * s, y - 7.5 * s), (x - 3 * s, y - 13 * s), (x + 5.2 * s, y - 8.4 * s)) +
                   BEZ((x + 5.2 * s, y - 8.4 * s), (x + 8.6 * s, y - 6 * s), (x + 8.8 * s, y - 2 * s), (x + 6.6 * s, y + 3 * s))).buffer(0)
    bone = U([L([(x + 5 * s, y - 5 * s), (x + 13.2 * s, y - 10.2 * s)], 2.8 * s, cap=FLAT),
              C(x + 13.2 * s, y - 12 * s, 1.9 * s), C(x + 14.8 * s, y - 9.6 * s, 1.9 * s)])
    a.ink(bone)
    a.ink(meat)
    a.cut(L(BEZ((x - 7.6 * s, y - 1 * s), (x - 7 * s, y - 6 * s), (x - 2.6 * s, y - 9 * s), (x + 1.6 * s, y - 8.4 * s)), 1.0, cap=FLAT))
    a.cut(L(BEZ((x - 3.4 * s, y + .4 * s), (x - 3 * s, y - 2.4 * s), (x - .8 * s, y - 4.4 * s), (x + 2.4 * s, y - 4.4 * s)), 1.0, cap=FLAT))


def beer_hall_2(a):
    # on the table: the roast on its platter between two tankards
    ham(a, 35.6, 31, 1.3)
    a.ink(P((19, 31), (53, 31), (49, 35.2), (23, 35.2)))
    mug(a, 13.6, 26.4, 11, 14.4, handle=1)
    mug(a, 60.4, 26.4, 11, 14.4, handle=-1)
    a.ink(R(7, 35.6, 67, 40.6))
    a.cut(U([L([(x, 35), (x, 41.5)], .9, cap=FLAT) for x in (19, 37, 55)]))
    # the table's trestles and stretcher
    for x in (25, 49):
        a.ink(U([L([(x - 4.4, 66), (x + 4.4, 41)], 2.8, cap=FLAT), L([(x + 4.4, 66), (x - 4.4, 41)], 2.8, cap=FLAT)]))
    a.ink(R(25, 45.6, 49, 48), T2, gap=0)
    # the bench in front
    a.ink(R(7, 53.4, 67, 57.4))
    a.cut(U([L([(x, 53), (x, 58)], .9, cap=FLAT) for x in (19, 37, 55)]))
    for x in (11.5, 62.5):
        a.ink(P((x - 2.6, 57.4), (x + 2.6, 57.4), (x + 3.4, 67), (x - 3.4, 67)), gap=.4)


def beer_hall_3(a):
    # cloud underneath: it distils in the air
    cl = U([C(14, 62, 5), C(23, 60, 6.4), C(35, 60, 7), C(48, 60.4, 6.6), C(60, 62, 5.2), R(11, 62, 63, 67)])
    a.ink(cl, T2, gap=0)
    # the condenser tub
    keg(a, 56, 38, 16.5, 25, staves=2)
    # swan neck
    neck = BEZ((26, 26), (26, 10), (35, 8.5), (47, 11.5))
    neck2 = BEZ((47, 11.5), (53, 13), (55.5, 18), (55.5, 25))
    a.ink(L(neck + neck2, 4.2, cap=FLAT))
    # pot still
    pot = Polygon(ARC(26, 41, 17, 110, 430, 80)).buffer(0)
    a.ink(pot)
    a.ink(P((21.8, 24), (30.2, 24), (34, 30), (18, 30)))
    a.ink(R(19.5, 22.6, 32.5, 25), gap=.6)
    a.cut(L(ARC(26, 41, 13.4, 170, 250, 30), 1.2, cap=FLAT))
    a.cutl([(9, 47), (43, 47)], 1.0)
    a.riv([(14, 50), (20, 51.8), (26, 52.4), (32, 51.8), (38, 50)], .8)
    # firebox with a flame
    a.ink(R(14, 57, 38, 62), gap=.8)
    a.cut(U([L([(x, 58.4), (x, 60.8)], 1.5, cap=FLAT) for x in (18, 23, 28, 33)]))
    a.ink(U([R(16, 62, 20, 66.6), R(32, 62, 36, 66.6)]), gap=.6)
    # tap and a drop
    a.ink(L([(46.5, 46), (43.6, 46), (43.6, 50)], 1.8, cap=FLAT, join=2), gap=.5)
    a.ink(teardrop(43.6, 54.4, 2.8, 3.2), gap=.5)


# ---------------------------------------------------------------- guns
def port(a, x, y, r):
    a.ink(C(x, y, r + 3.2), gap=1.1)
    a.cut(C(x, y, r))
    a.riv([(x + (r + 1.6) * math.cos(t), y + (r + 1.6) * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 8, endpoint=False)], .72)


def guns_1(a):
    # the hull plate, a curve on top
    wall = Polygon(BEZ((7, 15), (24, 7.5), (50, 7.5), (67, 15)) + [(67, 66.5), (7, 66.5)]).buffer(0)
    a.ink(wall)
    a.cutl([(6, 59.6), (68, 59.6)], .95)
    a.cutl([(37, 7), (37, 59.6)], .95)
    a.cutl([(37, 59.6), (37, 67)], .95)
    a.riv([(x, 63.2) for x in (11, 21, 31, 43, 53, 63)] + [(33.6, y) for y in (17, 28, 39, 50)] + [(40.4, y) for y in (17, 28, 39, 50)], .78)
    for x, y, r in ((20.5, 44.6, 8.8), (53.5, 44.6, 8.8)):
        port(a, x, y, r)
        # the lid swung up on its hinge
        a.ink(R(x - 2.6, 27, x + 2.6, 34), gap=.8)
        a.ink(E(x, 22, 11.2, 6.2), gap=1)
        a.cut(ERING(x, 22, 8.4, 3.8, .95))
        a.riv([(x - 5.6, 22), (x + 5.6, 22)], .72)


def wheel_small(a, x, y, r, t=T1):
    a.ink(C(x, y, r), t)
    a.cut(C(x, y, r * .36))


def carriage(a, x0, x1, y, h, t=T1):
    """Gun carriage under a barrel, stepped at the rear."""
    a.ink(P((x0, y), (x1, y), (x1 - 3, y + h), (x0 + 2, y + h)), t)
    a.cut(L([(x0 + 4, y + h * .45), (x1 - 4, y + h * .45)], .85, cap=FLAT))


def guns_2(a):
    # far cannon
    g = mv(sc(cannon_shape(), .72), 25, 17)
    a.ink(g, T2)
    carriage(a, 23, 45, 21, 8, T2)
    wheel_small(a, 28, 30.5, 4.2, T2)
    wheel_small(a, 40, 30.5, 4.2, T2)
    a.ink(R(7, 35.2, 67, 37.8), T2, gap=.5)
    # near cannon
    g = mv(sc(cannon_shape(), 1.14), 14, 43.2)
    a.ink(g)
    a.cut(L([(25, 36), (25, 52)], .9, cap=FLAT))
    carriage(a, 11, 41, 49, 8.8)
    wheel_small(a, 18, 57.5, 5.6)
    wheel_small(a, 35, 57.5, 5.6)
    # deck planking and a stack of shot
    a.ink(R(7, 62.2, 67, 66.6))
    a.cut(U([L([(x, 62), (x, 67.2)], .9, cap=FLAT) for x in (17, 31, 45, 59)]))
    for x, y in ((47.4, 58.4), (55, 58.4), (62.6, 58.4), (51.2, 52.2), (58.8, 52.2)):
        a.ink(C(x, y, 3.5), gap=.55)


def shell(x, y0, y1, w):
    """Upright shell: a rounded head, a flat base."""
    hw = w / 2
    sh = y0 + (y1 - y0) * .42
    return Polygon(ARC(x, sh, hw, 180, 360, 28, ry=sh - y0) + [(x + hw, y1), (x - hw, y1)]).buffer(0)


def guns_3(a):
    # fire behind, the shells in front of it standing on the rack
    a.ink(flame(37, 44, 52, 38), T2, gap=0)
    for x, w, y0 in ((19.5, 14, 33), (37, 14, 29), (54.5, 14, 33)):
        s = shell(x, y0, 59, w)
        a.ink(s, gap=1.3)
        a.cut(L([(x - 8, 47.4), (x + 8, 47.4)], 1.0, cap=FLAT))
        a.cut(L([(x - 8, 50.6), (x + 8, 50.6)], 1.0, cap=FLAT))
        a.riv([(x, 41)], 1.3)
    a.ink(R(7.5, 59.2, 66.5, 63), gap=.8)
    a.ink(U([R(10, 63, 15, 67), R(59, 63, 64, 67)]), gap=.5)
    a.cut(U([L([(x, 58), (x, 64)], .9, cap=FLAT) for x in (28.5, 45.5)]))


def guns_4(a):
    # An organ gun from the front: four mouths, two by two, in iron bands between two wheels.
    for x in (13, 61):
        a.ink(ERING(x, 44, 6.4, 21, 2.3), gap=0)
        hub = E(x, 44, 2.2, 3.4)
        spokes = U([L([(x, 44), (x + 4.6 * math.cos(t), 44 + 19 * math.sin(t))], 1.5, cap=FLAT)
                    for t in np.linspace(0, 2 * math.pi, 8, endpoint=False)])
        a.ink(U([hub, spokes]), gap=0)
    # the axle and the frame behind the barrels
    a.ink(R(14, 42, 60, 46.4), gap=.8)
    a.ink(RR(19.6, 11, 54.4, 60.4, 2.4), gap=1.2)
    a.ink(R(17, 7.4, 57, 11.6), gap=.9)
    a.riv([(21, 9.5), (37, 9.5), (53, 9.5)], .85)
    for x, y, in ((28.2, 24), (45.8, 24), (28.2, 44.8), (45.8, 44.8)):
        a.cut(C(x, y, 9.3))
        a.ink(RING(x, y, 8.3, 2.3), gap=0)
        a.ink(C(x, y, 4), gap=0)
    a.riv([(37, 15.8), (37, 24), (37, 34.4), (37, 44.8), (37, 54)], .85)
    # the trail on the ground
    a.ink(P((23, 61.8), (51, 61.8), (56, 67), (18, 67)), gap=.7)
    a.cutl([(37, 61.4), (37, 67.4)], 1.0)


# ---------------------------------------------------------------- crow's nests
def crows_nest_1(a):
    a.ink(dome(9, 65, 58, 9.2))
    a.cut(L(ARC(37, 67.2, 28, 200, 340, 40, ry=6.4), .9, cap=FLAT))
    # a scaffold around the frame
    a.ink(U([L([(14, 60.5), (14, 9)], 1.8, cap=FLAT), L([(60, 60.5), (60, 9)], 1.8, cap=FLAT),
             L([(11, 13), (63, 13)], 1.5, cap=FLAT), L([(14, 47), (29, 25)], 1.3, cap=FLAT),
             L([(60, 47), (45, 25)], 1.3, cap=FLAT)]), T2, gap=0)
    a.ink(R(35, 8, 39, 60))
    a.cut(U([L([(35, y), (39, y)], .9, cap=FLAT) for y in (49.6, 54.4)]))
    a.ink(U([L([(37, 58), (23.4, 39.6)], 1.9, cap=FLAT), L([(37, 58), (50.6, 39.6)], 1.9, cap=FLAT)]))
    # the empty tub: hoops and ribs, no planks
    a.ink(ERING(37, 22, 19, 3.8, 2.0))
    bh = E(37, 40.5, 14.4, 2.8).difference(E(37, 40.5, 12.2, 1.2))
    a.ink(bh)
    ribs = [((18.6, 23), (23.4, 40)), ((26, 25.2), (28.4, 42.2)), ((37, 26), (37, 43)), ((48, 25.2), (45.6, 42.2)), ((55.4, 23), (50.6, 40))]
    a.ink(U([L(list(r), 1.9, cap=FLAT) for r in ribs]), gap=.5)
    a.ink(ERING(37, 22, 19, 3.8, 2.0).difference(E(37, 20, 30, 1.8)), gap=0)
    a.ink(R(17.4, 30.2, 56.6, 31.4).intersection(basket(37, 22, 40.5, 19, 14.4)), gap=0)


def nest(a, x, yt, yb, rt, rb, t=T1, planks=5):
    """A finished nest with a planked tub."""
    tub = basket(x, yt, yb, rt, rb)
    a.ink(tub, t)
    a.cutl([(x - rt - 1, yt + 2.8), (x + rt + 1, yt + 2.8)], .9)
    a.cutl([(x - rt - 1, yb - 2.8), (x + rt + 1, yb - 2.8)], .9)
    for i in range(1, planks):
        fx = i / planks * 2 - 1
        a.cutl([(x + fx * rt, yt + 3), (x + fx * rb, yb - 3)], .85)


def crows_nest_2(a):
    a.ink(dome(9, 65, 58, 9.2))
    a.cut(L(ARC(37, 67.2, 28, 200, 340, 40, ry=6.4), .9, cap=FLAT))
    # the far nest
    x = 56
    a.ink(R(x - 1.7, 16, x + 1.7, 60), T2, gap=.6)
    a.ink(pennant(x + 1, 15.6, 10, 5.4), T2, gap=.4)
    a.ink(U([L([(x - 7, 42.4), (x - .6, 56)], 1.7, cap=FLAT), L([(x + 7, 42.4), (x + .6, 56)], 1.7, cap=FLAT)]), T2, gap=.4)
    nest(a, x, 29, 42.4, 10.4, 7, T2, planks=3)
    # the near nest
    x = 26.5
    a.ink(R(x - 2.3, 7.4, x + 2.3, 61.5))
    a.ink(pennant(x + 1.4, 7.2, 15, 7.6), gap=.5)
    a.ink(U([L([(x - 10.5, 45), (x - 1, 58)], 1.9, cap=FLAT), L([(x + 10.5, 45), (x + 1, 58)], 1.9, cap=FLAT)]), gap=.5)
    # the lookout's helmet above the rim
    a.ink(Polygon(ARC(x - 8, 26.8, 4.8, 180, 360, 20)).buffer(0), gap=.6)
    a.ink(R(x - 9, 19.4, x - 7, 22.6), gap=0)
    nest(a, x, 26.6, 45, 17.6, 12)


def grenade(a, x, y, r, t=T1):
    a.ink(C(x, y, r), t, gap=.6)
    a.ink(U([R(x - 1.2, y - r - 1.8, x + 1.2, y - r + .5), L(BEZ((x, y - r - 1.6), (x + .4, y - r - 3.6), (x + 2.2, y - r - 3.2), (x + 3, y - r - 4.4), n=8), .9, cap=FLAT)]), t, gap=0)
    a.riv([(x - r * .36, y - r * .34)], r * .22)


def throwing_axe(x, y, s, deg):
    h = L([(0, 0), (0, 22 * s)], 1.9 * s, cap=FLAT)
    bl = Polygon(BEZ((-.8 * s, 1 * s), (-3.8 * s, 2 * s), (-7 * s, -.5 * s), (-9.2 * s, -3 * s)) +
                 BEZ((-9.2 * s, -3 * s), (-10.8 * s, 2 * s), (-10.6 * s, 7 * s), (-8.6 * s, 11.6 * s)) +
                 BEZ((-8.6 * s, 11.6 * s), (-6.6 * s, 9 * s), (-3.8 * s, 7 * s), (-.8 * s, 6.6 * s))).buffer(0)
    g = U([h, bl])
    return mv(rot(g, deg, (0, 11 * s)), x, y)


def crows_nest_3(a):
    a.ink(dome(9, 65, 58, 9.2))
    a.cut(L(ARC(37, 67.2, 28, 200, 340, 40, ry=6.4), .9, cap=FLAT))
    x = 37
    a.ink(R(x - 2.3, 7, x + 2.3, 60))
    a.ink(pennant(x + 1.5, 7, 17, 7.2), gap=.6)
    a.ink(U([L([(x - 11, 30), (x - 1, 47)], 1.8, cap=FLAT), L([(x + 11, 30), (x + 1, 47)], 1.8, cap=FLAT)]), gap=.5)
    nest(a, x, 13.6, 31, 19, 12.4)
    # an open ammunition box slung off the mast, grenades showing over its rim
    a.ink(U([R(x - 2.2, 33.4, 20, 35.6), L([(20, 35), (11, 44)], 1.3, cap=FLAT), L([(20, 35), (29, 44)], 1.3, cap=FLAT)]), gap=.5)
    for gx in (13.4, 20.2, 27):
        grenade(a, gx, 44.4, 3.5)
    crate(a, 9.4, 46, 31, 58.4, brace=False)
    # a rack of axes on the right
    a.ink(R(x + 2.3, 34, 64, 36.4), gap=.5)
    a.ink(throwing_axe(49, 35.4, .88, 0))
    a.ink(mir(throwing_axe(58.4, 35.4, .88, 0), 58.4))


# ---------------------------------------------------------------- bomb hatches
def bomb_bay_1(a):
    # the hull's ribs around, unfinished at the corners
    a.ink(U([L([(7, 12), (67, 12)], 2.0, cap=FLAT), L([(7, 62), (67, 62)], 2.0, cap=FLAT),
             L([(12, 7), (12, 67)], 2.0, cap=FLAT), L([(62, 7), (62, 67)], 2.0, cap=FLAT)]), T2, gap=0)
    frame = R(15, 15, 59, 59)
    a.ink(frame, gap=1.3)
    a.cut(R(19.2, 19.2, 54.8, 54.8))
    a.riv([(17.1, y) for y in (19, 28, 37, 46, 55)] + [(56.9, y) for y in (19, 28, 37, 46, 55)] +
          [(x, 17.1) for x in (28, 37, 46)] + [(x, 56.9) for x in (28, 37, 46)], .78)
    for x0, x1, hx, sg in ((20.2, 36.3, 20.2, 1), (37.7, 53.8, 53.8, -1)):
        a.ink(R(x0, 20.2, x1, 53.8), gap=0)
        # the strap hinges read as pale tapered irons on the leaf
        for y in (25.6, 48.4):
            a.cut(P((hx, y - 1.5), (hx + sg * 10, y - 1.5), (hx + sg * 13, y), (hx + sg * 10, y + 1.5), (hx, y + 1.5)))
        # the leaf is marked for the bomb that will sit over it
        cx = (x0 + x1) / 2
        f, b = bomb(cx, 30.4, 44, 7.2)
        a.cut(U([f, b]))


def rack_bomb(a, x, y0, y1, w, t=T1):
    f, b = bomb(x, y0, y1, w)
    a.ink(f, t)
    a.cut(L([(x - w, y0 + (y1 - y0) * .10), (x + w, y0 + (y1 - y0) * .10)], .95, cap=FLAT).intersection(f))
    a.ink(b, t, gap=.6)
    h = y1 - y0
    for fy in (.36, .74):
        a.cut(L([(x - w, y0 + h * fy), (x + w, y0 + h * fy)], .95, cap=FLAT).intersection(b))


def bomb_bay_2(a):
    a.ink(U([R(7, 8, 10.5, 67), R(63.5, 8, 67, 67)]), gap=.5)
    a.ink(R(7, 62.8, 67, 66), T2, gap=0)
    for x, y0, y1, w in ((21, 16, 61, 15.4), (37, 16, 61, 15.4), (53, 16, 61, 15.4)):
        rack_bomb(a, x, y0, y1, w)
        a.ink(R(x - 1.5, 12, x + 1.5, y0 + 1), gap=.4)
        a.riv([(x, y0 + (y1 - y0) * .55)], 1.2)
    a.ink(R(7, 7, 67, 12.2), gap=.7)
    a.riv([(x, 9.6) for x in (10, 21, 37, 53, 64)], .95)


def bomb_bay_3(a):
    a.ink(flame(37, 63, 50, 50), T2, gap=0)
    for x in (20.5, 53.5):
        rack_bomb(a, x, 17, 66, 21)
        a.ink(R(x - 1.7, 12, x + 1.7, 18), gap=.4)
        a.cut(U([teardrop(x, 54, 5.8, 9.6), teardrop(x - 2.6, 54, 3.2, 6, -.7), teardrop(x + 2.6, 54, 3.0, 5.4, .7)]))
    a.ink(R(9, 7, 65, 12.2), gap=.7)
    a.riv([(x, 9.6) for x in (12, 20.5, 37, 53.5, 62)], .95)


# ---------------------------------------------------------------- harpoon and torpedoes
def harpoon_winch_1(a):
    # the harpoon flying up to the right, its line running back to the drum
    a.ink(L(BEZ((30, 32), (30, 22), (36, 30), (41.4, 25.6)), 1.8, cap=FLAT))
    sh = 17.5
    head = U([R(-1.5, -sh, 1.5, 0), R(-3, -3.6, 3, 0),
              P((0, -sh - 13), (6.4, -sh - 1.8), (2.1, -sh - 3.8), (2.1, -sh + 2), (-2.1, -sh + 2), (-2.1, -sh - 3.8), (-6.4, -sh - 1.8))])
    a.ink(mv(rot(head, 45, (0, 0)), 41, 27))
    # the base and frame
    a.ink(R(7, 62.6, 62, 66.6))
    a.cut(U([L([(x, 62), (x, 67.2)], .9, cap=FLAT) for x in (20, 36, 50)]))
    for x in (12, 42):
        a.ink(P((x - 5.8, 62.6), (x + 5.8, 62.6), (x + 2.4, 42), (x - 2.4, 42)))
    # the drum with the turns of the rope
    a.ink(R(8.6, 31.5, 45.6, 53.8))
    a.ink(R(6, 27.6, 11.4, 57.6), gap=.8)
    a.ink(R(42.6, 27.6, 48, 57.6), gap=.8)
    a.cut(U([L([(11.4 + i * 3.1, 31), (13.8 + i * 3.1, 54.4)], 1.05, cap=FLAT) for i in range(-1, 10)]).intersection(R(11.6, 31, 42.4, 54.4)))
    # the gear and the crank on the near end
    g = gear(53, 45, 11.8, teeth=11, th=2.6)
    a.ink(g)
    a.cut(RING(53, 45, 7.8, 1.0))
    a.cut(C(53, 45, 1.9))
    a.ink(R(51.8, 54, 54.2, 62.8), gap=.4)
    a.ink(L([(53, 45), (63.6, 38)], 2.5, cap=FLAT), gap=.8)
    a.ink(L([(64, 38), (64, 30.6)], 3), gap=.6)
    a.ink(C(53, 45, 2.2), gap=.6)


def torpedo_shape(ln=56.0, d=12.0):
    """Side view pointing along +x: tail at 0, a pointed nose at ln, the axis at y=0."""
    r = d / 2
    body = Polygon([(8, -r * .78), (ln - 15, -r)] + BEZ((ln - 15, -r), (ln - 7, -r), (ln - 3, -r * .5), (ln, 0), n=14) +
                   BEZ((ln, 0), (ln - 3, r * .5), (ln - 7, r), (ln - 15, r), n=14) + [(8, r * .78), (4, r * .42), (4, -r * .42)]).buffer(0)
    fin_t = P((1, -r * 1.25), (5.4, -r * 1.25), (11, -r * .72), (6, -r * .4))
    fin_b = AF.scale(fin_t, 1, -1, origin=(0, 0))
    prop = U([R(-1, -1, 5, 1), R(-2, -r * .92, 0, r * .92)])
    return U([body, fin_t, fin_b, prop])


def torpedo_gallery_1(a):
    # the arcade above
    arcade = R(7, 7.5, 67, 26).difference(U([E(x, 26, 7.7, 13.2) for x in (18, 37, 56)]))
    a.ink(arcade)
    a.cutl([(6, 11.4), (68, 11.4)], .9)
    a.ink(U([R(7, 26, 10.6, 67), R(27.8, 26, 31.2, 40), R(42.8, 26, 46.2, 40), R(63.4, 26, 67, 67)]), gap=0)
    # the far torpedo
    t2 = mv(sc(torpedo_shape(), .84), 19, 31.5)
    a.ink(t2, T2)
    # the near torpedo
    t1 = mv(sc(torpedo_shape(), 1.0), 11.5, 47)
    a.ink(t1)
    for x in (24, 28.5, 48):
        a.cutl([(x, 39), (x, 55)], .95)
    a.riv([(34, 47), (39, 47), (44, 47)], .85)
    a.ink(R(7, 62.2, 67, 66.6))
    a.cut(U([L([(x, 62), (x, 67)], .9, cap=FLAT) for x in (18, 37, 56)]))
    for x in (22, 52):
        a.ink(P((x - 3.8, 62.2), (x + 3.8, 62.2), (x + 2.6, 52.6), (x - 2.6, 52.6)), gap=.6)


# ---------------------------------------------------------------- the list
ICONS = [
    ("airship_hull_1", GREY, "Заготовка под корабль", "Фюзеляж", airship_hull_1, False),
    ("airship_hull_2", GREY, "Прочный корпус", "Фюзеляж", airship_hull_2, False),
    ("airship_hull_3", GREY, "Каркас с рунами", "Фюзеляж", airship_hull_3, False),
    ("airship_hull_4", GREY, "Укрепленный каркас воздушного корабля", "Фюзеляж", airship_hull_4, False),
    ("airship_hull_5", GREY, "Корпус с рунами", "Фюзеляж", airship_hull_5, False),
    ("crew_weapons_1", GREEN, "Манекен для учебной стрельбы", "Тренировка экипажа", crew_weapons_1, False),
    ("crew_weapons_2", GREEN, "Тир", "Тренировка экипажа", crew_weapons_2, False),
    ("crew_weapons_3", GREEN, "Полигон", "Тренировка экипажа", crew_weapons_3, False),
    ("support_radius_1", GREEN, "Сигнальная система", "Сигналы", support_radius_1, False),
    ("support_radius_2", GREEN, "Сигнальная сеть", "Сигналы", support_radius_2, False),
    ("engines_1", GREEN, "Машинное отделение", "Двигатели", engines_1, False),
    ("engines_2", GREEN, "Повышенная мощность двигателя", "Двигатели", engines_2, False),
    ("engines_3", GREEN, "Большие пропеллеры", "Двигатели", engines_3, False),
    ("cargo_hold_1", GREEN, "Грузовые стеллажи", "Грузовой трюм", cargo_hold_1, False),
    ("cargo_hold_2", GREEN, "Хранилище", "Грузовой трюм", cargo_hold_2, False),
    ("cargo_hold_3", GREEN, "Упрощенный наружный грузовой люк", "Грузовой трюм", cargo_hold_3, False),
    ("beer_hall_1", GREEN, "Пивной чертог", "Пивная", beer_hall_1, False),
    ("beer_hall_2", GREEN, "Столовая", "Пивная", beer_hall_2, False),
    ("beer_hall_3", GREEN, "Воздушная винокурня", "Пивная", beer_hall_3, False),
    ("mtb_guns_1", GREEN, "Орудийные порты", "Пушки", guns_1, True),
    ("mtb_guns_2", GREEN, "Орудийная палуба", "Пушки", guns_2, True),
    ("mtb_guns_3", GREEN, "Огненный арсенал", "Пушки", guns_3, True),
    ("mtb_guns_4", GREEN, "Палата органных орудий", "Пушки", guns_4, True),
    ("mtb_nest_1", GREEN, "Заготовка под воронье гнездо", "Воронье гнездо", crows_nest_1, True),
    ("mtb_nest_2", GREEN, "Вороньи гнёзда", "Воронье гнездо", crows_nest_2, True),
    ("mtb_nest_3", GREEN, "Гнёзда с боеукладкой", "Воронье гнездо", crows_nest_3, True),
    ("mtb_hatches_1", GREEN, "Заготовка под бомбовые люки", "Люки", bomb_bay_1, True),
    ("mtb_hatches_2", GREEN, "Бомбовые стеллажи", "Люки", bomb_bay_2, True),
    ("mtb_hatches_3", GREEN, "Зажигательная укладка", "Люки", bomb_bay_3, True),
    ("mtb_harpoon_1", GREEN, "Гарпунная лебёдка", "Гарпун", harpoon_winch_1, True),
    ("mtb_torpedoes_1", GREEN, "Торпедная галерея", "Торпеды", torpedo_gallery_1, True),
]
VANILLA = ["airship_hull", "crew_weapons_training", "support_radius", "engines", "cargo_hold", "beer_hall"]


def render(entry):
    key, tint, _, _, fn, _ = entry
    a = Art()
    fn(a)
    return a.finish(key, tint)


# ---------------------------------------------------------------- sheets
def vanilla_files():
    """The stock icons and the parchment tile from the game's packs, through py -3.14 and gamepack.py."""
    out = Path(tempfile.gettempdir()) / "tww3_mtb_building_icon_refs"
    out.mkdir(exist_ok=True)
    if not (out / "building_frame.png").exists():
        code = (
            "import sys; sys.dont_write_bytecode = True; sys.path.insert(0, sys.argv[1]); import gamepack, pathlib\n"
            "o = pathlib.Path(sys.argv[2])\n"
            "w = lambda n: (n.lower().startswith('ui\\\\buildings\\\\icons\\\\dwarf_spirit_of_grungni_')"
            " or n.lower().endswith('\\\\default\\\\building_frame.png'))\n"
            "for p in ('ui.pack', 'ui2.pack'):\n"
            "    for n, b in gamepack.entries(gamepack.DATA / p, w):\n"
            "        (o / n.split(chr(92))[-1]).write_bytes(b)\n")
        subprocess.run(["py", "-3.14", "-c", code, str(ROOT / "tools"), str(out)], check=True)
    return out


def tiled(icon, frame, scale=1, dim=False):
    tile = frame.copy()
    tile.alpha_composite(icon)
    if dim:
        # The tree's locked look: desaturated, dark, as in docs/feedback/08-green-tree.png.
        arr = np.asarray(tile, np.float32)
        lum = arr[..., :3].mean(axis=2) * .48
        arr[..., :3] = np.stack([lum, lum, lum], axis=2)
        tile = Image.fromarray(arr.astype(np.uint8), "RGBA")
    if scale > 1:
        tile = tile.resize((SIZE * scale, SIZE * scale), Image.BICUBIC)
    return tile


def font(size, bold=False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(d, text, f, width):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + [cur]


def contact_sheet(rendered, refs):
    frame = Image.open(refs / "building_frame.png").convert("RGBA")
    bg = (20, 20, 22, 255)
    fg = (214, 204, 182)
    Z = 3
    cell_w, cell_h = SIZE * Z + 14, SIZE * Z + 44
    cols = 7
    van = [Image.open(refs / f"dwarf_spirit_of_grungni_{n}.png").convert("RGBA") for n in VANILLA]
    rows = math.ceil(len(rendered) / cols)
    W = cols * cell_w + 20
    H = 90 + cell_h + 30 + rows * cell_h + 40 + 2 * (SIZE + 14) * 1 + 70
    sheet = Image.new("RGBA", (W, H), bg)
    d = ImageDraw.Draw(sheet)
    f, fb = font(13), font(16, True)
    y = 10
    d.text((12, y), "Оригиналы игры, 3×: подпись это ключ значка в ui/buildings/icons", font=fb, fill=fg)
    y += 26
    for i, (n, im) in enumerate(zip(VANILLA, van)):
        x = 10 + i * cell_w
        sheet.alpha_composite(tiled(im, frame, Z), (x, y))
        d.text((x, y + SIZE * Z + 3), n, font=f, fill=fg)
    y += cell_h
    d.text((12, y), "Новые значки, 3×", font=fb, fill=fg)
    y += 26
    for i, (e, im) in enumerate(rendered):
        x, yy = 10 + (i % cols) * cell_w, y + (i // cols) * cell_h
        sheet.alpha_composite(tiled(im, frame, Z), (x, yy))
        for j, line in enumerate(wrap(d, e[2], f, SIZE * Z)[:2]):
            d.text((x, yy + SIZE * Z + 2 + j * 15), line, font=f, fill=fg)
    y += rows * cell_h + 6
    d.text((12, y), "Реальный размер, 74 px: оригиналы и новые вперемешку, в обычном виде и в затемнении дерева", font=fb, fill=fg)
    y += 26
    mixed = []
    pool = [im for _, im in rendered]
    for i, im in enumerate(van):
        mixed.append(im)
        mixed.extend(pool[i * 3:i * 3 + 3])
    mixed = mixed[:(W - 20) // (SIZE + 4)]
    for row, dim in enumerate((False, True)):
        for i, im in enumerate(mixed):
            sheet.alpha_composite(tiled(im, frame, 1, dim), (10 + i * (SIZE + 4), y + row * (SIZE + 6)))
    return sheet.convert("RGB").crop((0, 0, W, y + 2 * (SIZE + 6) + 8))


def write_readme(rendered):
    lines = ["# Значки построек барки", "",
             "Рисует `tools/draw_building_icons.py`. Формат как у `ui/buildings/icons/dwarf_spirit_of_grungni_*.png`: 74×74 RGBA, "
             "ровный цвет в RGB, рисунок в альфе, не больше 204. Плитку с обгорелым краем (`building_frame.png`) и вид «доступно/недоступно» "
             "делает интерфейс, поэтому отдельных серых версий нет: у игры их тоже нет.", "",
             "`contact-sheet.png` нужен только для проверки, в пак его не класть.", "",
             f"Имя файла это короткий ключ уровня из `data/crew_options.json`, полный ключ в таблицах: `{PREFIX}` + короткий.", "",
             "| Файл | Постройка | Ветка | |", "|---|---|---|---|"]
    for e, _ in rendered:
        key, _, name, chain, _, new = e
        lines.append(f"| `{key}.png` | {name} | {chain} | {'новый' if new else ''} |")
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def preview(rendered, refs, path, scale=4, cols=6):
    frame = Image.open(refs / "building_frame.png").convert("RGBA")
    rows = math.ceil(len(rendered) / cols)
    sh = Image.new("RGBA", (cols * (SIZE * scale + 4), rows * (SIZE * scale + 4)), (20, 20, 22, 255))
    for i, (_, im) in enumerate(rendered):
        sh.alpha_composite(tiled(im, frame, scale), ((i % cols) * (SIZE * scale + 4), (i // cols) * (SIZE * scale + 4)))
    sh.convert("RGB").save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated short keys; nothing is written to the mod, only the preview")
    ap.add_argument("--preview", help="write a big preview image here")
    ap.add_argument("--scale", type=int, default=4)
    ap.add_argument("--cols", type=int, default=6)
    args = ap.parse_args()
    chosen = ICONS
    if args.only:
        wanted = args.only.split(",")
        chosen = [e for e in ICONS if e[0] in wanted]
    rendered = [(e, render(e)) for e in chosen]
    refs = vanilla_files()
    if args.preview:
        preview(rendered, refs, args.preview, args.scale, args.cols)
    if args.only:
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for e, im in rendered:
        al = np.asarray(im)[..., 3]
        ys, xs = np.where(al > 20)
        print(f"{e[0]:20s} bbox {xs.min():2d},{ys.min():2d} {xs.max():2d},{ys.max():2d} max {al.max()} cover {(al > 100).mean():.2f}")
        im.save(OUT / f"{e[0]}.png", optimize=True)
    sheet = contact_sheet(rendered, refs)
    path = OUT / "contact-sheet.png"
    sheet.save(path, optimize=True)
    if path.stat().st_size >= 1_000_000:
        sheet.quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE).save(path, optimize=True)
    jpg = ROOT / "docs" / "research" / "img" / "building-icons.jpg"
    sheet.save(jpg, quality=88)
    write_readme(rendered)
    print(f"{len(rendered)} icons, sheet {path.stat().st_size // 1024} KB, jpg {jpg.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
