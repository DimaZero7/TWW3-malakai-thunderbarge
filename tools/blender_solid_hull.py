"""Closes the cannon port's hole in the hull so the side looks whole: blender --background --python tools/blender_solid_hull.py

The hull's side is one island of the texture sheet, unwrapped without distortion, so a hole in the model is a hole in the island. The painter used the pixels inside
that hole for the port's own ring, so texture coordinates cannot simply run across it. What runs across it here:

- rows: the planks are curves in the sheet. A row is v = c + f(u); f is fitted to the pixels. The steel belt has its own f, the belt's top edge.
- fold: a point of the hole takes the pixels of its row, read backwards from where the row meets the hole's edge (2 * u_edge - u). So at the edge there is no jump at all and
  plank gaps run straight on. The fold of the left half and the fold of the right half meet on a seam, chosen where the two agree most (a cheapest path through the hole).
  Triangles are added where a straight triangle would not follow the fold or would read the hole's pixels.
- belt: under the belt's edge the hole is a shallow cap, too shallow for a fold. It reads the steel some plates further along the belt, the shift that best matches the plates around.
- shape: positions and normals are a thin plate spline of the hull's vertices around the hole; the edge vertices are the hull's own.

Writes under build/solid_hull/: tww3_mtb_hull_solid (the stock model, port taken out, hole closed), tww3_mtb_hull_solid_cut (the same without the details
tools/hull_parts.py moves out of the hull: pub, cupola rings; the mod's hull without its port), solid_hull.json.
Needs build/solid_hull/game (see tools/blender_rmv2.py); the texture sheet as base_colour.png.
"""
import bisect
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import numpy as np
from mathutils.geometry import delaunay_2d_cdt
from mathutils import Vector

import blender_rmv2 as br

rmv2 = br.rmv2
OUT = br.REPO / "build" / "solid_hull"
FOLDER = "warmachines/aircraft/dwf_thunderbarge"
SOURCE = FOLDER + "/dwf_thunderbarge_01.rigid_model_v2"
STOCK_WS = FOLDER + "/dwf_thunderbarge_grungni_01.wsmodel"
SPEC = json.loads((br.REPO / "data" / "hull_parts.json").read_text(encoding="utf-8"))
PORT_BOXES = next(d for d in SPEC["details"] if d["name"] == "port")["boxes"]
STEP = {0: 18.0, 1: 22.0, 2: 30.0, 3: 40.0}      # spacing of the inner vertices, in pixels of the sheet
TOLERANCE = {0: 4.0, 1: 6.0, 2: 8.0, 3: 14.0}    # how far a triangle may stray from the fold, in pixels
ROUNDS = {0: 4, 1: 3, 2: 3, 3: 2}
PORTHOLE = (1028.0, 3639.0, 52.0)   # the porthole's ring on the sheet, in pixels: centre and radius, read off the sheet
SHIFT_RANGE = (500, 720)        # along the belt to the plates between the two bomb hatches of the sheet


def load_sheet():
    im = bpy.data.images.load(str(br.GAME_DIR / "base_colour.png"))
    w, h = im.size
    a = np.zeros((h, w, 4), dtype=np.float32)
    im.pixels.foreach_get(a.ravel())
    return a[::-1, :, :3].copy()


SHEET = load_sheet()
H, W = SHEET.shape[:2]


def sample(u, v):
    """Pixels at u, v (in pixels), nearest."""
    return SHEET[np.clip(np.rint(v).astype(int), 0, H - 1), np.clip(np.rint(u).astype(int), 0, W - 1)]


def lum(rgb):
    return rgb @ np.array((0.3, 0.6, 0.1))


class Row:
    """v = c (1 + g x) + a x + b x^2 + d x^3, x = u - u0: planks bend, and they close up towards the bow"""

    def __init__(self, u0, a, b, d=0.0, c0=0.0, g=0.0):
        self.u0, self.a, self.b, self.d, self.c0, self.g = u0, a, b, d, c0, g

    def f(self, u):
        x = u - self.u0
        return self.c0 + x * (self.a + x * (self.b + x * self.d))

    # The rows of the two sides of the hole, measured apart, do not quite meet: over the hole's width a row moves by shift + scale * c more.
    shift, scale, lo, hi = 0.0, 0.0, 0.0, 1.0

    def blend(self, u):
        x = np.clip((self.hi - u) / (self.hi - self.lo), 0.0, 1.0)
        return x * x * (3 - 2 * x)

    def c(self, u, v):
        s = self.blend(u)
        return ((v - self.f(u)) / (1 + self.g * (u - self.u0)) - self.shift * s) / (1 + self.scale * s)

    def v(self, u, c):
        s = self.blend(u)
        return self.f(u) + (c + (self.shift + self.scale * c) * s) * (1 + self.g * (u - self.u0))


def inside_poly(u, v, poly):
    """Numpy arrays u, v; poly an array of points."""
    n = len(poly)
    res = np.zeros(u.shape, bool)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        hit = ((ay > v) != (by > v)) & (u < (bx - ax) * (v - ay) / (by - ay + 1e-12) + ax)
        res ^= hit
    return res


def fit_wood(poly, belt):
    """The planks' curve: the one along which the pixels around the hole change least."""
    u0, v0 = poly.mean(axis=0)
    r = np.ptp(poly[:, 0]) / 2
    uu, vv = np.meshgrid(np.arange(u0 - 3.2 * r, u0 + 4.5 * r), np.arange(v0 - 2.0 * r, v0 + 1.1 * r))
    keep = ~inside_poly(uu, vv, poly * 1.0 + 0) & (vv < belt.f(uu) - 6)
    # the rings of the porthole and of the port are grey, the planks brown
    rgb = sample(uu, vv)
    keep &= rgb[..., 0] > 1.25 * rgb[..., 2]
    uu, vv = uu[keep], vv[keep]
    y = lum(sample(uu, vv))
    v0 = float(vv.mean())

    def spread(a, b, d, g):
        row = Row(u0, a, b, d, v0, g)
        bins = np.rint(row.c(uu, vv) * 1.0).astype(int)
        bins -= bins.min()
        n = np.bincount(bins)
        s = np.bincount(bins, y)
        s2 = np.bincount(bins, y * y)
        ok = n > 40
        return (s2[ok] - s[ok] ** 2 / n[ok]).sum() / n[ok].sum()
    # f is measured at v0, so that g does not move it
    best = min(((spread(a, b, 0.0, 0.0), a, b) for a in np.linspace(-0.45, 0.1, 56) for b in np.linspace(-0.0002, 0.002, 45)))
    p = [best[1], best[2], 0.0, 0.0]
    steps = [0.01, 0.00005, 2e-7, 0.0003]
    value = best[0]
    for _ in range(10):
        for k in range(4):
            for move in (-3, -2, -1, 1, 2, 3):
                t = list(p)
                t[k] += move * steps[k]
                now = spread(*t)
                if now < value:
                    value, p = now, t
        steps = [x * 0.8 for x in steps]
    return Row(u0, p[0], p[1], p[2], v0, p[3]), value


def align_sides(row, poly, belt):
    """Compares the planks just left and just right of the hole along the rows, and sets the row's correction so the plank gaps of the two sides meet."""
    lo, hi = poly[:, 0].min(), poly[:, 0].max()
    row.lo, row.hi = lo, hi
    top = poly[:, 1].min() - 80
    bottom = min(belt.f(lo), belt.f(hi)) - 6
    cs = np.arange(row.c(hi, top), row.c(hi, bottom))

    def profile(columns, shift, scale, s):
        sum_ = np.zeros(cs.shape)
        for u in columns:
            sum_ += lum(sample(np.full(cs.shape, u), row.f(u) + (cs + (shift + scale * cs) * s)))
        return sum_ - sum_.mean()
    right = profile(np.arange(hi + 4, hi + 34, 3), 0.0, 0.0, 0.0)
    best = None
    for shift in np.arange(-70, 71, 1.0):
        for scale in np.arange(-0.3, 1.01, 0.02):
            left = profile(np.arange(lo - 34, lo - 4, 3), shift, scale, 1.0)
            score = float(left @ right) / (np.linalg.norm(left) * np.linalg.norm(right) + 1e-9)
            if best is None or score > best[0]:
                best = (score, shift, scale)
    row.shift, row.scale = float(best[1]), float(best[2])
    return best


def fit_belt(poly):
    """The belt's top edge: dark planks above, bright steel below, read from columns left and right of the hole."""
    lo, hi = poly[:, 0].min(), poly[:, 0].max()
    top, bottom = poly[:, 1].min(), poly[:, 1].max()
    pts = []
    for u in list(np.arange(lo - 110, lo - 2, 4)) + list(np.arange(hi + 2, hi + 110, 4)):
        vs = np.arange(top - 10, bottom + 70)
        rgb = sample(np.full(vs.shape, u), vs)
        bright = (lum(rgb) > 0.2) & (rgb[:, 0] < 1.25 * rgb[:, 2])
        run = np.convolve(bright.astype(int), np.ones(6, int), "same") >= 6
        if run.any():
            pts.append((u, vs[np.argmax(run)] - 3))
    pts = np.array(pts)
    u0 = poly[:, 0].mean()
    for _ in range(3):      # what is not the edge (a rivet, a highlight) falls out
        coef = np.polyfit(pts[:, 0] - u0, pts[:, 1], 3)
        err = np.abs(np.polyval(coef, pts[:, 0] - u0) - pts[:, 1])
        pts = pts[err <= max(2.0, np.median(err) * 2.5)]
    d, b, a, c = coef
    return Row(u0, a, b, d, c), float(err.mean())


class TPS:
    """Thin plate spline over 2D points, of any number of values per point."""

    def __init__(self, pts, values, smooth=1e-3):
        self.pts = np.asarray(pts, float)
        self.scale = np.ptp(self.pts, axis=0).max()
        p = self.pts / self.scale
        n = len(p)
        K = self._k(p, p) + np.eye(n) * smooth
        P = np.c_[np.ones(n), p]
        A = np.r_[np.c_[K, P], np.c_[P.T, np.zeros((3, 3))]]
        self.w = np.linalg.solve(A, np.r_[np.asarray(values, float), np.zeros((3, np.asarray(values).shape[1]))])

    @staticmethod
    def _k(a, b):
        d2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=2)
        return 0.5 * d2 * np.log(d2 + 1e-12)

    def __call__(self, q):
        q = np.atleast_2d(np.asarray(q, float)) / self.scale
        return np.c_[self._k(q, self.pts / self.scale), np.ones(len(q)), q] @ self.w


def px(v):
    u, w = br.uv(v)
    return np.array((u * W, w * H))


def side_piece(mesh, sign):
    """The triangles of the planks' and belt's piece on one side."""
    for tris, b in br.pieces(mesh):
        edge = b[3] if sign > 0 else -b[0]
        if abs(edge - 2.38) < 0.05 and b[5] - b[2] > 15:
            return tris
    raise SystemExit("no side piece")


def rim_loop(mesh, tris, sign):
    """The hole: indexes of vertices in order, walking the edges with one triangle (welded, as vertices split at UV seams), near the port."""
    ids = br.weld(mesh)
    count, rep = {}, {}
    for t in tris:
        a = mesh.tris[t]
        for i, j in ((a[0], a[1]), (a[1], a[2]), (a[2], a[0])):
            key = (min(ids[i], ids[j]), max(ids[i], ids[j]))
            count[key] = count.get(key, 0) + 1
            rep[ids[i]], rep[ids[j]] = i, j
    near = {}
    for (a, b), n in count.items():
        if n != 1:
            continue
        ok = True
        for k in (a, b):
            v = mesh.verts[rep[k]]
            ok &= 0.6 < v.x * sign < 2.4 and 0.2 < v.y < 2.3 and 4.7 < v.z < 6.8
        if ok:
            near.setdefault(a, []).append(b)
            near.setdefault(b, []).append(a)
    seen, loops = set(), []
    for start in near:
        if start in seen:
            continue
        loop, stack = [], [start]       # the connected part of these edges
        while stack:
            k = stack.pop()
            if k not in seen:
                seen.add(k)
                loop.append(k)
                stack.extend(near[k])
        if all(len(near[k]) == 2 for k in loop) and len(loop) >= 5:
            loops.append(loop)
    if len(loops) != 1:
        raise SystemExit(f"the hole's edge: {len(loops)} closed loops")
    start = loops[0][0]
    loop, prev, cur = [start], None, start
    while True:
        nxt = [k for k in near[cur] if k != prev]
        prev, cur = cur, nxt[0]
        if cur == start:
            break
        loop.append(cur)
    return [rep[k] for k in loop]


def key_on_rim(a, b, rim_edges):
    return (a, b) in rim_edges


def grown_hole(mesh, tris, rim):
    """One ring of the hull's triangles around the hole goes too: the painter's shadow of the port lies on them. Returns (the triangles out, the new edge's vertices in order)."""
    ids = br.weld(mesh)
    on_rim = {ids[i] for i in rim}
    rim_edges = {(min(ids[a], ids[b]), max(ids[a], ids[b])) for a, b in zip(rim, rim[1:] + rim[:1])}
    count = {}
    for t in tris:
        a = mesh.tris[t]
        for i, j in ((a[0], a[1]), (a[1], a[2]), (a[2], a[0])):
            count.setdefault((min(ids[i], ids[j]), max(ids[i], ids[j])), []).append(t)
    outer = {k for k, ts in count.items() if len(ts) == 1 and k not in rim_edges}
    out = set()
    for t in tris:
        a = mesh.tris[t]
        keys = [(min(ids[i], ids[j]), max(ids[i], ids[j])) for i, j in ((a[0], a[1]), (a[1], a[2]), (a[2], a[0]))]
        # A triangle on the piece's outer edge stays: that edge is the bow's trim.
        if any(ids[i] in on_rim for i in a) and not any(k in outer for k in keys):
            out.add(t)
    count, rep = {}, {}
    for t in tris:
        a = mesh.tris[t]
        for i, j in ((a[0], a[1]), (a[1], a[2]), (a[2], a[0])):
            key = (min(ids[i], ids[j]), max(ids[i], ids[j]))
            count.setdefault(key, []).append(t)
            if t not in out:        # the vertex that shares the UV and everything with the hull that stays
                rep[ids[i]], rep[ids[j]] = i, j
    near = {}
    for (a, b), ts in count.items():
        if (len(ts) == 2 and (ts[0] in out) != (ts[1] in out)) or (len(ts) == 1 and key_on_rim(a, b, rim_edges) and ts[0] not in out):
            near.setdefault(a, []).append(b)
            near.setdefault(b, []).append(a)
    if not near or any(len(v) != 2 for v in near.values()):
        raise SystemExit("the grown hole's edge is not one simple loop: " + str(sorted(len(v) for v in near.values())))
    start = next(iter(near))
    loop, prev, cur = [start], None, start
    while True:
        nxt = [k for k in near[cur] if k != prev]
        prev, cur = cur, nxt[0]
        if cur == start:
            break
        loop.append(cur)
    if len(loop) != len(near):
        raise SystemExit("the grown hole's edge is more than one loop")
    return out, [rep[k] for k in loop]


def crossings(row, c, poly):
    """Where a row meets the polygon: [(u, edge index)] sorted by u."""
    out = []
    n = len(poly)
    for i in range(n):
        A, B = poly[i], poly[(i + 1) % n]
        ha, hb = row.c(*A) - c, row.c(*B) - c
        if (ha <= 0) != (hb <= 0):
            t = ha / (ha - hb)
            for _ in range(3):      # the row is curved: a few steps along the edge
                P = A + t * (B - A)
                d = row.c(*P) - c
                slope = hb - ha
                t = min(1, max(0, t - d / slope))
            out.append(((A + t * (B - A))[0], i))
    return sorted(out)


class Fold:
    """One kind of surface in the hole (the planks or the belt), split by a seam."""

    def __init__(self, row, poly, sector, seam, outer=None):
        self.row, self.poly = row, poly
        self.sector = sector        # edges of the hole's polygon that have this surface beyond them
        self.seam = seam            # [(c, u)] sorted by c
        self.outer = outer

    def valid(self, c):
        """The edge u on the left and on the right for this row; None where beyond it is the other surface."""
        cross = crossings(self.row, c, self.poly)
        if len(cross) < 2:
            return None, None
        (ul, el), (ur, er) = cross[0], cross[-1]
        return (ul if el in self.sector else None), (ur if er in self.sector else None)

    def split(self, c):
        cs = [s[0] for s in self.seam]
        i = bisect.bisect_left(cs, c)
        if i <= 0:
            return self.seam[0][1]
        if i >= len(cs):
            return self.seam[-1][1]
        t = (c - cs[i - 1]) / (cs[i] - cs[i - 1])
        return self.seam[i - 1][1] + t * (self.seam[i][1] - self.seam[i - 1][1])

    def side(self, q):
        c = self.row.c(*q)
        ul, ur = self.valid(c)
        if ul is None and ur is None:
            return 0 if q[0] < self.split(c) else 1
        if ul is None:
            return 1
        if ur is None:
            return 0
        return 0 if q[0] < self.split(c) else 1

    def uv(self, q, side):
        if self.outer is not None and not inside_poly(np.array([q[0]]), np.array([q[1]]), self.outer)[0]:
            return np.array(q, float)       # this far LOD's hole is wider here than the nearest LOD's: the sheet is clean
        c = self.row.c(*q)
        ul, ur = self.valid(c)
        edge = ul if side == 0 else ur
        if edge is None:
            edge = ur if side == 0 else ul
        if edge is None:        # the row only touches the hole
            return np.array(q, float)
        u = 2 * edge - q[0]
        # Along the row, as far as the porthole's ring on the sheet: the grain only stretches along itself there, so it does not show.
        path = np.linspace(edge, u, 40)
        hit = np.hypot(path - PORTHOLE[0], self.row.v(path, c) - PORTHOLE[1]) < PORTHOLE[2]
        if hit.any():
            u = path[max(0, int(np.argmax(hit)) - 1)]
        return np.array((u, self.row.v(u, c)))


def belt_table(poly, far=800):
    """The belt's top edge as read column by column to the right of the hole: u and v as arrays, smoothed."""
    hi = poly[:, 0].max()
    top, bottom = poly[:, 1].min(), poly[:, 1].max()
    us, vs_out = [], []
    last = None
    for u in np.arange(hi + 2, hi + far, 3):
        vs = np.arange(top - 30, bottom + 40)
        rgb = sample(np.full(vs.shape, u), vs)
        bright = (lum(rgb) > 0.2) & (rgb[:, 0] < 1.25 * rgb[:, 2])
        run = np.convolve(bright.astype(int), np.ones(6, int), "same") >= 6
        if run.any():
            v = float(vs[np.argmax(run)] - 3)
            if last is None or abs(v - last) < 6:
                us.append(u)
                vs_out.append(v)
                last = v
    us, vs_out = np.array(us), np.array(vs_out)
    smooth = np.convolve(np.r_[[vs_out[0]] * 3, vs_out, [vs_out[-1]] * 3], np.ones(7) / 7, "valid")
    return us, smooth


class Shift:
    """The belt's cap: the same row of the belt, further along."""

    def __init__(self, edge, table, shift):
        self.edge, self.table, self.shift = edge, table, shift

    def f(self, u):
        return np.interp(u, *self.table)

    def side(self, q):
        return 0

    def uv(self, q, side):
        c = self.edge.c(*q)
        u = q[0] + self.shift
        return np.array((u, self.f(u) + c))


def find_shift(belt, table, poly):
    """The distance along the belt at which the steel around the hole's lower edge looks most the same. Past the hole's width, so the cap never reads the hole."""
    centre = poly.mean(axis=0)
    pts = []
    n = len(poly)
    for i in range(n):
        for t in np.linspace(0, 1, 12, endpoint=False):
            p = poly[i] + t * (poly[(i + 1) % n] - poly[i])
            if belt.c(*p) > 1:
                d = p - centre
                for out in (2, 5, 9):
                    pts.append(p + d / np.linalg.norm(d) * out)
    pts = np.array(pts)
    c = pts[:, 1] - belt.f(pts[:, 0])
    here = sample(pts[:, 0], pts[:, 1])
    best = None
    for x in np.arange(*SHIFT_RANGE):
        u = pts[:, 0] + x
        diff = float(np.abs(sample(u, np.interp(u, *table) + c) - here).sum(axis=1).mean())
        if best is None or diff < best[0]:
            best = (diff, float(x))
    return best[1], best[0]


def seam_path(row, poly, sector, c_lo, c_hi, step=3.0):
    """The cheapest way from one end to the other: at each row the place where the left fold and the right fold show the same pixels."""
    rows = []
    for c in np.arange(c_lo, c_hi, step):
        cross = crossings(row, c, poly)
        if len(cross) < 2 or cross[0][1] not in sector or cross[-1][1] not in sector:
            continue
        ul, ur = cross[0][0], cross[-1][0]
        if ur - ul < 8:
            continue
        rows.append((c, ul, ur))
    if not rows:
        return []
    lo, hi = min(r[1] for r in rows), max(r[2] for r in rows)
    grid = np.arange(lo, hi + 1, 1.0)
    cost = []
    for c, ul, ur in rows:
        left = sample(2 * ul - grid, row.v(2 * ul - grid, c))
        right = sample(2 * ur - grid, row.v(2 * ur - grid, c))
        here = np.abs(left - right).sum(axis=1) + 0.002 * np.abs(grid - (ul + ur) / 2)
        here[(grid < ul + 2) | (grid > ur - 2)] = 1e6
        cost.append(here)
    cost = np.array(cost)
    total = cost[0].copy()
    back = []
    reach = int(step * 1.5)
    for k in range(1, len(cost)):
        best = np.stack([np.roll(total, s) + 0.01 * abs(s) for s in range(-reach, reach + 1)])
        arg = best.argmin(axis=0)
        back.append(arg - reach)
        total = best.min(axis=0) + cost[k]
    i = int(total.argmin())
    path = [i]
    for b in reversed(back):
        i = (i - b[i]) % len(grid)
        path.append(i)
    path.reverse()
    return [(rows[k][0], float(grid[path[k]])) for k in range(len(rows))]


def thin(points, gap):
    out = [points[0]]
    for p in points[1:]:
        if np.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= gap:
            out.append(p)
    return out


def close_side(mesh, sign, wood_row, belt_lod0, table, shift, step, tolerance, rounds, report, full_hole=None, painted=None):
    """The piece closing one side's hole: (vertices, triangles) of rmv2 vertices."""
    tris = side_piece(mesh, sign)
    gone, rim = grown_hole(mesh, tris, rim_loop(mesh, tris, sign))
    tris = [t for t in tris if t not in gone]       # the hull that stays gives the shape
    poly = np.array([px(mesh.verts[i]) for i in rim])
    n = len(rim)
    # the belt's edge meets the hole at two of its vertices
    d = [abs(belt_lod0.c(*p)) for p in poly]
    left = int(np.argmin([d[i] + 1000 * (poly[i][0] > poly[:, 0].mean()) for i in range(n)]))
    right = int(np.argmin([d[i] + 1000 * (poly[i][0] < poly[:, 0].mean()) for i in range(n)]))
    # the belt through these two points exactly
    dl, dr = belt_lod0.c(*poly[left]), belt_lod0.c(*poly[right])
    span = poly[right][0] - poly[left][0]

    class Edge(Row):
        def f(self, u):
            return belt_lod0.f(u) + dl + (dr - dl) * np.clip((u - poly[left][0]) / span, -0.5, 1.5)
    belt = Edge(0, 0, 0)
    # the hole's edges above the belt and below it
    def walk(a, b):
        out, i = [], a
        while i != b:
            out.append(i)
            i = (i + 1) % n
        return out
    one, two = walk(left, right), walk(right, left)
    v1 = np.mean([poly[i][1] for i in one + [right]])
    v2 = np.mean([poly[i][1] for i in two + [left]])
    top_edges, low_edges = (set(one), set(two)) if v1 < v2 else (set(two), set(one))

    # the belt's edge across the hole
    chord = [poly[left]]
    for u in np.arange(poly[left][0] + step, poly[right][0] - step * 0.5, step):
        if inside_poly(np.array([u]), np.array([belt.f(u)]), poly)[0]:
            chord.append(np.array((u, belt.f(u))))
    chord.append(poly[right])

    # the seams
    def tops_bottoms(row, edges):
        cs = [row.c(*poly[i]) for e in edges for i in (e, (e + 1) % n)]
        return min(cs), max(cs)

    def tops_bottoms_of(row, shape, chosen):
        cs = [row.c(*shape[i]) for e in chosen for i in (e, (e + 1) % len(shape))]
        return min(cs), max(cs)

    lo, hi = tops_bottoms(wood_row, top_edges)
    wood_seam = seam_path(wood_row, poly, top_edges, lo + 1, hi)

    # A far LOD's edge has fewer vertices and cuts inside the painted hole: there the fold starts from the nearest LOD's edge, or it would read the hole's pixels.
    hole, hole_top = poly, top_edges
    if full_hole is not None:
        hole = full_hole
        m = len(hole)
        hole_top = {i for i in range(m) if belt_lod0.c(*((hole[i] + hole[(i + 1) % m]) / 2)) < 0}
        lo, hi = tops_bottoms_of(wood_row, hole, hole_top)
        wood_seam = seam_path(wood_row, hole, hole_top, lo + 1, hi)
    wood = Fold(wood_row, hole, hole_top, wood_seam, outer=full_hole)
    steel = Shift(belt, table, shift)

    # all points in the sheet's plane
    points, kinds, edges = [], [], []

    def add(q, kind):
        for i, p in enumerate(points):
            if np.hypot(*(p - q)) < 0.3:
                return i
        points.append(np.array(q, float))
        kinds.append(kind)
        return len(points) - 1
    rim_at = [add(p, ("rim", rim[i])) for i, p in enumerate(poly)]
    for i in range(n):
        edges.append((rim_at[i], rim_at[(i + 1) % n]))
    chord_at = [rim_at[left]] + [add(q, ("chord",)) for q in chord[1:-1]] + [rim_at[right]]
    edges += list(zip(chord_at, chord_at[1:]))

    def seam_line(fold, seam, near_rim, near_chord):
        """A line of vertices from the hole's edge (or the belt's edge) to the belt's edge, along the fold's seam."""
        if not seam:
            return
        q = [np.array((u, fold.row.v(u, c))) for c, u in seam]
        q = [p for p in q if inside_poly(np.array([p[0]]), np.array([p[1]]), poly)[0] and p[1] < belt.f(p[0]) - step * 0.5]
        q = thin(q, step * 0.8)
        at = []
        # the ends: the nearest vertex of the hole's edge and of the belt's edge
        first = min(near_rim, key=lambda i: np.hypot(*(points[i] - q[0])))
        at.append(first)
        at += [add(p, ("seam",)) for p in q if min(np.hypot(*(points[i] - p)) for i in rim_at) > step * 0.4 and min(np.hypot(*(points[i] - p)) for i in chord_at) > step * 0.4]
        last = min(near_chord, key=lambda i: np.hypot(*(points[i] - q[-1])))
        at.append(last)
        edges.extend(zip(at, at[1:]))
    fixed_edges = len(edges)        # the hole's edge and the belt's edge; what follows is the seam, which a far LOD may lose
    top_rim = [rim_at[e] for e in top_edges]
    seam_line(wood, wood_seam, top_rim, chord_at)

    # the inner vertices
    us = np.arange(poly[:, 0].min(), poly[:, 0].max(), step)
    vs = np.arange(poly[:, 1].min(), poly[:, 1].max(), step)
    for u in us:
        for v in vs:
            q = np.array((u, v))
            if inside_poly(np.array([u]), np.array([v]), poly)[0] and min(np.hypot(*(p - q)) for p in points) > step * 0.55:
                add(q, ("in",))

    def region(a, b, c):
        q = (points[a] + points[b] + points[c]) / 3
        fold = "wood" if q[1] < belt.f(q[0]) else "belt"
        f = wood if fold == "wood" else steel
        return fold, f.side(q)

    def sheet_at(p, reg):
        """Where a point of the hole reads the sheet, in this region."""
        if kinds[p][0] == "rim" and reg[0] == "wood" and full_hole is None:
            return px(mesh.verts[kinds[p][1]])
        return (wood if reg[0] == "wood" else steel).uv(points[p], reg[1])

    centre_in = hole.mean(axis=0)
    shrunk = centre_in + (hole - centre_in) * 0.97
    painted_shrunk = shrunk if painted is None else painted.mean(axis=0) + (painted - painted.mean(axis=0)) * 0.98

    def reads_hole(ua, ub, uc):
        """Does the triangle, as the sheet sees it, pass over the hole: its edges and middle, sampled."""
        t = np.linspace(0, 1, 9)[:, None]
        m = np.r_[ua + t * (ub - ua), ub + t * (uc - ub), uc + t * (ua - uc), [(ua + ub + uc) / 3]]
        ring = np.hypot(m[:, 0] - PORTHOLE[0], m[:, 1] - PORTHOLE[1]) < PORTHOLE[2]
        return bool((inside_poly(m[:, 0], m[:, 1], shrunk) | inside_poly(m[:, 0], m[:, 1], painted_shrunk) | ring).any())

    def triangulate():
        coords = [Vector((p[0], p[1])) for p in points]
        out = delaunay_2d_cdt(coords, edges, [rim_at], 1, 1e-4)
        if len(out[0]) != len(points):
            del edges[fixed_edges:]
            out = delaunay_2d_cdt(coords, edges, [rim_at], 1, 1e-4)
        if len(out[0]) != len(points):
            del edges[len(rim_at):]        # the belt's edge too: in the farthest LOD it is only as sharp as its triangles
            out = delaunay_2d_cdt(coords, edges, [rim_at], 1, 1e-4)
        if len(out[0]) != len(points):
            raise SystemExit(f"the triangulation added {len(out[0]) - len(points)} vertices at LOD step {step}: lines cross")
        return [[out[3][i][0] for i in face] for face in out[2]]

    for _ in range(rounds):
        added = 0
        for a, b, c in triangulate():
            reg = region(a, b, c)
            if reg[0] != "wood":
                continue
            ua, ub, uc = (sheet_at(p, reg) for p in (a, b, c))
            q = (points[a] + points[b] + points[c]) / 3
            want = wood.uv(q, reg[1])
            got = (ua + ub + uc) / 3
            in_hole = reads_hole(ua, ub, uc)
            if (in_hole or np.hypot(*(want - got)) > tolerance) and min(np.hypot(*(p - q)) for p in points) > 1.5:
                add(q, ("in",))
                added += 1
        if not added:
            break
    faces = triangulate()
    # shape from the hull around the hole
    around, seen = [], {}
    centre = poly.mean(axis=0)
    radius = np.ptp(poly[:, 0]) / 2
    for t in tris:
        for i in mesh.tris[t]:
            q = px(mesh.verts[i])
            if i not in seen and np.hypot(*(q - centre)) < radius * 2.2:
                seen[i] = 1
                around.append(i)
    knots, xyz, nor = [], [], []
    for i in around:
        q = px(mesh.verts[i])
        if any(np.hypot(*(q - k)) < 1.0 for k in knots):
            continue
        knots.append(q)
        v = mesh.verts[i]
        xyz.append((v.x, v.y, v.z))
        nor.append(br.normal(v))
    shape = TPS(knots, xyz)
    normals = TPS(knots, nor, smooth=1e-2)
    fitted = shape(poly)
    actual = np.array([[mesh.verts[i].x, mesh.verts[i].y, mesh.verts[i].z] for i in rim])

    template = mesh.verts[rim[0]]
    verts, faces_out, key_at = [], [], {}
    reading_hole = 0
    grad = {}

    def vertex(p, reg, flat=None):
        """flat: a place on the sheet for a thin triangle that would otherwise pass over the hole's pixels; it reads one spot of the planks."""
        key = (p, reg, None if flat is None else tuple(flat))
        if key in key_at:
            return key_at[key]
        kind = kinds[p]
        q = points[p]
        if kind[0] == "rim":
            v = mesh.verts[kind[1]].copy()
            if reg[0] == "belt" or full_hole is not None:        # its own place on the sheet; shape and bones as the hull's
                uvq = sheet_at(p, reg)
                br.set_shading(v, uv_=(float(uvq[0] / W), float(uvq[1] / H)))
        else:
            v = template.copy()
            x, y, z = shape(q)[0]
            v.x, v.y, v.z = float(x), float(y), float(z)
            nn = normals(q)[0]
            uvq = sheet_at(p, reg)
            br.set_shading(v, n=tuple(nn / np.linalg.norm(nn)), uv_=(float(uvq[0] / W), float(uvq[1] / H)))
        if flat is not None:
            br.set_shading(v, uv_=(float(flat[0] / W), float(flat[1] / H)))
        key_at[key] = len(verts)
        verts.append(v)
        return key_at[key]

    for face in faces:
        a, b, c = face
        reg = region(a, b, c)
        flat = None
        if reg[0] == "wood":
            where = [sheet_at(p, reg) for p in (a, b, c)]
            if reads_hole(*where):
                reading_hole += 1
                flat = max(where, key=lambda w: min(np.hypot(*(w - hole.mean(axis=0))), np.hypot(w[0] - PORTHOLE[0], w[1] - PORTHOLE[1]) - PORTHOLE[2]))
        tri = [vertex(p, reg, flat) for p in (a, b, c)]
        P = [np.array((verts[i].x, verts[i].y, verts[i].z)) for i in tri]
        N = np.cross(P[1] - P[0], P[2] - P[0])
        area = np.linalg.norm(N)
        if area < 1e-7:
            continue
        if N @ np.array(br.normal(verts[tri[0]])) < 0:      # as the hull's triangles: right hand, outwards
            tri = [tri[0], tri[2], tri[1]]
            P = [P[0], P[2], P[1]]
        faces_out.append(tuple(tri))
        U = [np.array(br.uv(verts[i])) for i in tri]
        e1, e2, d1, d2 = P[1] - P[0], P[2] - P[0], U[1] - U[0], U[2] - U[0]
        det = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(det) < 1e-10:
            continue
        # the file's tangent runs along V and its bitangent along U (measured on the stock planks)
        dpdu = (e1 * d2[1] - e2 * d1[1]) / det
        dpdv = (e2 * d1[0] - e1 * d2[0]) / det
        for i in tri:
            g = grad.setdefault(i, [np.zeros(3), np.zeros(3)])
            g[0] += dpdv / max(np.linalg.norm(dpdv), 1e-6) * area
            g[1] += dpdu / max(np.linalg.norm(dpdu), 1e-6) * area
    for i, (gt, gb) in grad.items():
        N = np.array(br.normal(verts[i]))
        N /= np.linalg.norm(N)
        t = gt - N * (gt @ N)
        b = gb - N * (gb @ N)
        br.set_shading(verts[i], t=tuple(t / np.linalg.norm(t)), b=tuple(b / np.linalg.norm(b)))

    # plain measures
    report.append({"side": sign, "hole_vertices": n, "vertices": len(verts), "triangles": len(faces_out), "seam_rows": len(wood_seam), "triangles_reading_hole": reading_hole,
                   "fit_at_edge": float(np.abs(fitted - actual).max())})
    return verts, faces_out, gone


def port_pieces(mesh):
    remove = set()
    for tris, b in br.pieces(mesh):
        for area in PORT_BOXES:
            if b[0] >= area[0] and b[1] >= area[1] and b[2] >= area[2] and b[3] <= area[3] and b[4] <= area[4] and b[5] <= area[5]:
                remove.update(tris)
    return remove


def select(mesh, indexes):
    keep = set(indexes)
    return rmv2.keep_triangles_at(mesh, keep) if hasattr(rmv2, "keep_triangles_at") else _select(mesh, keep)


def _select(mesh, keep):
    out = mesh.copy()
    remap, verts, tris = {}, [], []
    for i, tri in enumerate(mesh.tris):
        if i in keep:
            new = []
            for v in tri:
                if v not in remap:
                    remap[v] = len(verts)
                    verts.append(mesh.verts[v].copy())
                new.append(remap[v])
            tris.append(tuple(new))
    out.verts, out.tris = verts, tris
    return out


def main():
    stock = br.STOCK.read_bytes()
    model = rmv2.load(stock)
    lod0 = model["lods"][0][0]
    piece = side_piece(lod0, 1)
    rim0 = rim_loop(lod0, piece, 1)
    painted = np.array([px(lod0.verts[i]) for i in rim0])     # the hole the painter left in the sheet
    poly0 = np.array([px(lod0.verts[i]) for i in grown_hole(lod0, piece, rim0)[1]])
    belt, belt_err = fit_belt(painted)
    wood, spread = fit_wood(painted, belt)
    align = align_sides(wood, painted, belt)
    print("plank fit", wood.a, wood.b, wood.d, wood.g, "spread", spread, "sides: agreement, shift, scale", align, flush=True)
    table = belt_table(painted)
    shift, shift_diff = find_shift(belt, table, poly0)
    print("belt's cap reads", shift, "pixels along, difference", shift_diff, flush=True)
    print("planks: slope", wood.a, "bend", wood.b, "belt edge", belt.a, belt.b, belt.d, "error px", belt_err, flush=True)

    report = {"rows": {"planks": [wood.a, wood.b, wood.d, wood.g], "belt_error_px": belt_err, "belt_shift": shift}, "lods": []}
    solid = rmv2.load(stock)
    for li, meshes in enumerate(solid["lods"]):
        hull = meshes[0]
        rep = []
        ring = set()
        mesh = hull.copy()
        mesh.verts, mesh.tris = [], []
        for sign in (1, -1):
            verts, tris, gone = close_side(hull, sign, wood, belt, table, shift, STEP[li], TOLERANCE[li], ROUNDS[li], rep, full_hole=poly0 if li >= 2 else None, painted=painted)
            ring |= gone
            base = len(mesh.verts)
            mesh.verts.extend(verts)
            mesh.tris.extend((a + base, b + base, c + base) for a, b, c in tris)
        cut = port_pieces(hull) | ring
        whole = _select(hull, set(range(len(hull.tris))) - cut)
        rmv2.append(whole, mesh)
        meshes[0] = whole
        report["lods"].append({"lod": li, "stock": (len(hull.verts), len(hull.tris)), "port_triangles_out": len(cut), "new": (len(mesh.verts), len(mesh.tris)),
                               "result": (len(whole.verts), len(whole.tris)), "sides": rep})
        print(report["lods"][-1], flush=True)

    # the wsmodel names materials by LOD and mesh: the same ones
    folder = OUT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    import re
    ws = (br.GAME_DIR / "stock.wsmodel").read_text(encoding="utf-8")
    table = {}
    for m in re.finditer(r"<material ([^>]*)>([^<]+)</material>", ws):
        table[(int(re.search(r'lod_index="(\d+)"', m.group(1)).group(1)), int(re.search(r'part_index="(\d+)"', m.group(1)).group(1)))] = m.group(2)
    (folder / "tww3_mtb_hull_solid.rigid_model_v2").write_bytes(rmv2.save(solid))
    (folder / "tww3_mtb_hull_solid.wsmodel").write_text(ws.replace(SOURCE, FOLDER + "/tww3_mtb_hull_solid.rigid_model_v2"), encoding="utf-8")
    # the mod's own cut, as tools/hull_parts.py does it, on the closed hull
    cut_model = rmv2.load(rmv2.save(solid))
    for detail in SPEC["details"]:
        if detail["name"] == "port":
            continue
        for meshes in cut_model["lods"]:
            mesh = meshes[detail["mesh"]]
            away = set()
            for tris, b in br.pieces(mesh):
                for area in detail["boxes"]:
                    if all(b[i] >= area[i] for i in range(3)) and all(b[i] <= area[i] for i in range(3, 6)) and (len(area) < 7 or b[3] - b[0] >= area[6]):
                        away.update(tris)
            meshes[detail["mesh"]] = _select(mesh, set(range(len(mesh.tris))) - away)
    (folder / "tww3_mtb_hull_solid_cut.rigid_model_v2").write_bytes(rmv2.save(cut_model))
    (folder / "tww3_mtb_hull_solid_cut.wsmodel").write_text(ws.replace(SOURCE, FOLDER + "/tww3_mtb_hull_solid_cut.rigid_model_v2"), encoding="utf-8")
    (OUT / "solid_hull.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


main()
