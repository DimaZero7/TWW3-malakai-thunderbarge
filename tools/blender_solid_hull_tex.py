"""The whole hull with its own texture copies: blender --background --python tools/blender_solid_hull_tex.py

In the live Blender (MCP): import this module and call run(), then show() puts the three hulls in the scene.

- Paint: on copies of the Grungni's sheets the port's ring and its shadow are replaced (base colour, normal, material map; the mask is empty here and stays the stock file).
  Planks: each row reads itself backwards from the zone's edge, the two sides cross-fade on the cheapest seam. Steel: the plates further along the belt, faded into the plates around.
  Normals follow the same mapping, turned by its Jacobian. Only blocks touching the zone are encoded anew, in every mip down to 16 pixels; header and format stay the stock file's.
- Model: the stock hull, port out, its hole filled with texture coordinates that simply run on (no fold in the model). Nothing else of the hull goes.
- Normals: the file's normals bend towards the flanges of the port and the porthole. In the zone they are replaced by those of a smooth surface fitted to the hull further away.

Writes under build/solid_hull_tex/, same paths as in a pack. Needs build/solid_hull/game (see tools/blender_rmv2.py).
"""
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

import blender_dds as bd
import blender_rmv2 as br
import blender_solid_hull as sh

rmv2 = br.rmv2
OUT = br.REPO / "build" / "solid_hull_tex"
FOLDER = "warmachines/aircraft/dwf_thunderbarge"
SOURCE = FOLDER + "/dwf_thunderbarge_01.rigid_model_v2"
OWN = "tww3_mtb_solid"       # prefix of own materials and textures
TEX = "warmachines/tex"
MAT = "warmachines/materials"
BOX = (680, 3400, 2000, 4000)       # what the paint reads and writes, in pixels of the sheet
MARGIN_WOOD, MARGIN_STEEL = 18.0, 24.0
FEATHER_SEAM, FEATHER_STEEL = 10.0, 10.0
RING = (sh.PORTHOLE[0], sh.PORTHOLE[1], sh.PORTHOLE[2] + 2.0)
STEP = {0: 30.0, 1: 30.0, 2: 50.0, 3: 70.0}
NORMAL_INNER, NORMAL_OUTER = 1.7, 3.0     # the new normals in full up to this many radii of the hole, faded out at the second


def dist_to_poly(uu, vv, poly):
    best = np.full(uu.shape, 1e9, dtype=np.float32)
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        d = b - a
        t = np.clip(((uu - a[0]) * d[0] + (vv - a[1]) * d[1]) / (d @ d), 0, 1)
        best = np.minimum(best, np.hypot(uu - a[0] - t * d[0], vv - a[1] - t * d[1]))
    return best


def bilinear(img, x0, y0, u, v):
    """img: h x w x n float; u, v in pixels of the sheet."""
    x, y = np.clip(u - x0, 0, img.shape[1] - 1.001), np.clip(v - y0, 0, img.shape[0] - 1.001)
    xi, yi = x.astype(int), y.astype(int)
    fx, fy = (x - xi)[..., None], (y - yi)[..., None]
    return (img[yi, xi] * (1 - fx) * (1 - fy) + img[yi, xi + 1] * fx * (1 - fy) + img[yi + 1, xi] * (1 - fx) * fy + img[yi + 1, xi + 1] * fx * fy)


class Paint:
    """Where each pixel of the zone reads the sheet: planks left and right with a weight, steel with a weight against what is there."""

    def __init__(self):
        model = rmv2.load(br.STOCK.read_bytes())
        lod0 = model["lods"][0][0]
        piece = sh.side_piece(lod0, 1)
        self.rim = sh.rim_loop(lod0, piece, 1)
        self.painted = np.array([sh.px(lod0.verts[i]) for i in self.rim])
        self.belt, self.belt_err = sh.fit_belt(self.painted)
        self.wood, self.spread = sh.fit_wood(self.painted, self.belt)
        self.align = sh.align_sides(self.wood, self.painted, self.belt)
        self.table = sh.belt_table(self.painted)
        centre = self.painted.mean(axis=0)
        self.shift, self.shift_diff = sh.find_shift(self.belt, self.table, centre + (self.painted - centre) * 1.45)
        self.base = bd.Dds(str(br.GAME_DIR / "dwf_thunderbarge_grungni_01_base_colour.dds"))
        self.base_img = self.base.read(0, *BOX).astype(np.float32)
        x0, y0, x1, y1 = BOX
        self.vv, self.uu = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        dist = dist_to_poly(self.uu, self.vv, self.painted)
        inside = sh.inside_poly(self.uu, self.vv, self.painted)
        above = self.vv < self.belt.f(self.uu)
        margin = np.where(above, MARGIN_WOOD, MARGIN_STEEL)
        zone = inside | (dist < margin)
        zone &= np.hypot(self.uu - RING[0], self.vv - RING[1]) > RING[2]
        self.zone, self.above = zone, above
        self.depth = np.where(inside, margin + dist, margin - dist)     # how far in from the zone's outer edge
        self._wood()
        self._steel()
        self.report = {"belt_error_px": self.belt_err, "steel_shift_px": self.shift, "plank_sides": [float(x) for x in self.align], "zone_pixels": int(zone.sum()), "wood_both_invalid": self.lost, "gap_offset_px": [float(self.delta.min()), float(self.delta.max())]}

    def _wood(self):
        zone = self.zone & self.above
        ys, xs = np.nonzero(zone)
        u, v = self.uu[ys, xs], self.vv[ys, xs]
        c = self.wood.c(u, v)
        bins = np.rint(c).astype(int)
        lo = bins.min()
        n = bins.max() - lo + 1
        ul, ur = np.full(n, 1e9), np.full(n, -1e9)
        np.minimum.at(ul, bins - lo, u)
        np.maximum.at(ur, bins - lo, u)
        # the edge of each row, a little smoothed: pixels are steps
        have = ul < 1e8
        idx = np.arange(n)
        ul, ur = np.interp(idx, idx[have], ul[have]), np.interp(idx, idx[have], ur[have])
        kernel = np.ones(3) / 3
        ul, ur = np.convolve(np.r_[ul[0], ul, ul[-1]], kernel, "valid"), np.convolve(np.r_[ur[0], ur, ur[-1]], kernel, "valid")

        def read(side_edges, u_, c_):
            """Where a pixel reads for a fold at this edge of its row, and whether that place is planks."""
            edge = np.interp(c_, idx + lo, side_edges)
            target = 2 * edge - u_
            tv = self.wood.v(target, c_)
            ok = tv < self._edge_v(target) - 2
            ok &= np.hypot(target - RING[0], tv - RING[1]) > RING[2]
            return target, tv, ok, edge

        # the seam: at each row, where the two reads agree most
        grid = np.arange(np.floor(ul.min()), np.ceil(ur.max()) + 1)
        cost = np.zeros((n, len(grid)), np.float32)
        for k in range(n):
            cc = np.full(grid.shape, lo + k, dtype=np.float32)
            lu, lv, lok, _ = read(ul, grid, cc)
            ru, rv, rok, _ = read(ur, grid, cc)
            a = bilinear(self.base_img, BOX[0], BOX[1], lu, lv)[..., :3]
            b = bilinear(self.base_img, BOX[0], BOX[1], ru, rv)[..., :3]
            cost[k] = np.abs(a - b).sum(axis=1) + 200 * (~lok | ~rok) + 0.05 * np.abs(grid - (ul[k] + ur[k]) / 2)
            cost[k][(grid < ul[k]) | (grid > ur[k])] = 2000
        total = cost[0].copy()
        back = []
        for k in range(1, n):
            options = np.stack([np.roll(total, s) + 3.0 * abs(s) for s in (-2, -1, 0, 1, 2)])
            arg = options.argmin(axis=0)
            back.append(arg - 2)
            total = options.min(axis=0) + cost[k]
        i = int(total.argmin())
        path = [i]
        for b in reversed(back):
            i = int((i - b[i]) % len(grid))
            path.append(i)
        seam = grid[np.array(path[::-1])]
        seam = np.convolve(np.r_[[seam[0]] * 4, seam, [seam[-1]] * 4], np.ones(9) / 9, "valid")

        # What each side shows along the seam, row by row: the same plank gaps should come at the same row. The offset found is shared by the two sides, growing from their edges to the seam.
        rows = idx + lo
        def profile(edges):
            total = np.zeros(n, np.float32)
            for off in (-6, -3, 0, 3, 6):
                lu_, lv_, _, _ = read(edges, seam + off, rows.astype(np.float32))
                total += sh.lum(bilinear(self.base_img, BOX[0], BOX[1], lu_, lv_)[..., :3])
            return total - np.convolve(total, np.ones(41) / 41, "same")
        pl, pr = profile(ul), profile(ur)
        offs = np.arange(-24, 25)
        score = np.zeros((n, len(offs)), np.float32)
        window = np.ones(17) / 17
        for j, o in enumerate(offs):
            score[:, j] = np.convolve(pl * np.interp(rows + o, rows, pr), window, "same")
        best = score[0].copy()
        back = []
        for k in range(1, n):
            options = np.stack([np.roll(best, t) - 40.0 * abs(t) for t in (-1, 0, 1)])
            arg = options.argmax(axis=0)
            back.append(arg - 1)
            best = options.max(axis=0) + score[k]
        j = int(best.argmax())
        chain = [j]
        for b in reversed(back):
            j = int((j - b[j]) % len(offs))
            chain.append(j)
        delta = offs[np.array(chain[::-1])].astype(np.float32)
        delta = np.convolve(np.r_[[delta[0]] * 7, delta, [delta[-1]] * 7], np.ones(15) / 15, "valid")
        self.delta = delta

        self.wood_px = (ys, xs)
        self.wood_c = c
        s = np.interp(c, rows, seam)
        d = np.interp(c, rows, delta)
        edge_l, edge_r = np.interp(c, rows, ul), np.interp(c, rows, ur)
        tl = np.clip((u - edge_l) / np.maximum(s - edge_l, 1.0), 0, 1)
        tr = np.clip((edge_r - u) / np.maximum(edge_r - s, 1.0), 0, 1)
        lu, lv, lok, le = read(ul, u, c - d * 0.5 * tl)
        ru, rv, rok, re_ = read(ur, u, c + d * 0.5 * tr)
        w = np.clip((u - s) / (2 * FEATHER_SEAM) + 0.5, 0, 1)
        w = w * w * (3 - 2 * w)                     # 0: the left read, 1: the right
        w = np.where(lok & ~rok, 0.0, np.where(rok & ~lok, 1.0, w))
        self.lost = int((~lok & ~rok).sum())
        self.wood_reads = (lu, lv, ru, rv, w, le, re_)
        self.wood_seam = (idx + lo, seam)

    def _edge_v(self, u):
        return np.where(u > self.painted[:, 0].max(), np.interp(u, *self.table), self.belt.f(u))

    def _steel(self):
        zone = self.zone & ~self.above
        ys, xs = np.nonzero(zone)
        u, v = self.uu[ys, xs], self.vv[ys, xs]
        c = v - self.belt.f(u)
        tu = u + self.shift
        tv = np.interp(tu, *self.table) + c
        self.steel_px = (ys, xs)
        self.steel_reads = (tu, tv, np.clip(self.depth[ys, xs] / FEATHER_STEEL, 0, 1))

    def paint_level0(self, img, normal=False):
        """img: the stock pixels of BOX, float h x w x 4. Returns the painted pixels."""
        x0, y0 = BOX[:2]
        out = img.copy()
        ys, xs = self.wood_px
        lu, lv, ru, rv, w, le, re_ = self.wood_reads
        a = bilinear(img, x0, y0, lu, lv)
        b = bilinear(img, x0, y0, ru, rv)
        if normal:
            a = self._turn(a, self.uu[ys, xs], self.wood_c, le, flip=True)
            b = self._turn(b, self.uu[ys, xs], self.wood_c, re_, flip=True)
        out[ys, xs] = a * (1 - w[..., None]) + b * w[..., None]
        ys, xs = self.steel_px
        tu, tv, alpha = self.steel_reads
        s = bilinear(img, x0, y0, tu, tv)
        out[ys, xs] = out[ys, xs] * (1 - alpha[..., None]) + s * alpha[..., None]
        return out

    def _turn(self, n, u, c, edge, flip):
        """The normal map at the place read, turned for this pixel: u runs backwards, and the row's slope at the two places differs.
        Channels: alpha along U, green along V, as they vary across the plank gaps."""
        out = n.copy()
        nu, nv = n[:, 3] / 127.5 - 1, n[:, 1] / 127.5 - 1
        target = 2 * edge - u
        here = (self.wood.v(u + 1, c) - self.wood.v(u - 1, c)) / 2
        there = (self.wood.v(target + 1, c) - self.wood.v(target - 1, c)) / 2
        # a gap along the row has gradient (-slope, 1) nv in both places
        new_u = -nu - (here + there) * nv * self.channel_sign
        out[:, 3] = np.clip((new_u + 1) * 127.5, 0, 255)
        return out

    def measure_channels(self, normal_img):
        """How the stored U channel goes with the V channel on a slanted plank gap: the sign the turn needs."""
        x0, y0 = BOX[:2]
        ys, xs = np.nonzero((self.uu > 700) & (self.uu < 880) & (self.vv > 3650) & (self.vv < 3800) & self.above)
        slope = (self.wood.f(self.uu[ys, xs] + 1) - self.wood.f(self.uu[ys, xs] - 1)) / 2
        nu = normal_img[ys, xs, 3] / 127.5 - 1
        nv = normal_img[ys, xs, 1] / 127.5 - 1
        k = float((nu * nv * slope).sum() / ((nv * slope) ** 2).sum())
        self.channel_sign = 1.0 if k < 0 else -1.0     # nu = -slope nv when both channels are the plain gradient
        return k


def write_mips(dds, img, zone, name):
    """Level 0 from img (pixels of BOX), then each smaller level from the one above, only in the zone's box; blocks without the zone keep their bytes."""
    x0, y0, x1, y1 = BOX
    ys, xs = np.nonzero(zone)
    zx0, zx1 = int(xs.min()) + x0, int(xs.max()) + x0 + 1
    zy0, zy1 = int(ys.min()) + y0, int(ys.max()) + y0 + 1
    only = np.zeros(((y1 - y0) // 4, (x1 - x0) // 4), bool)
    for by in range(only.shape[0]):
        for bx in range(only.shape[1]):
            only[by, bx] = zone[by * 4:by * 4 + 4, bx * 4:bx * 4 + 4].any()
    dds.write(0, x0, y0, np.clip(np.rint(img), 0, 255), only)
    count = {0: int(only.sum())}
    box = (zx0 // 4 * 4 - 8, zy0 // 4 * 4 - 8, (zx1 + 3) // 4 * 4 + 8, (zy1 + 3) // 4 * 4 + 8)
    for level in range(1, dds.mips):
        w, h = dds.level_size(level)
        if min(w, h) < 16:
            break
        box8 = (box[0] // 8 * 8, box[1] // 8 * 8, (box[2] + 7) // 8 * 8, (box[3] + 7) // 8 * 8)
        above = dds.read(level - 1, *box8).astype(np.float32)
        rows, cols = above.shape[0] // 2, above.shape[1] // 2
        small = above.reshape(rows, 2, cols, 2, 4).mean(axis=(1, 3))
        new_box = (box8[0] // 2, box8[1] // 2, box8[2] // 2, box8[3] // 2)
        dds.write(level, new_box[0], new_box[1], np.rint(small))
        count[level] = int(small.shape[0] * small.shape[1] / 16)
        box = new_box
    return count


def smooth_surface(lod0, sign, painted):
    """A smooth surface over the side, from the sheet's plane to the hull's points, fitted without the vertices next to the port and the porthole. Returns normal(q)."""
    centre = painted.mean(axis=0)
    r = np.ptp(painted[:, 0]) / 2
    knots, xyz = [], []
    seen = []
    for t in sh.side_piece(lod0, sign):
        for i in lod0.tris[t]:
            q = sh.px(lod0.verts[i])
            d = np.hypot(*(q - centre))
            if d > 4.2 * r or d < 1.45 * r or np.hypot(q[0] - sh.PORTHOLE[0], q[1] - sh.PORTHOLE[1]) < sh.PORTHOLE[2] * 1.35:
                continue
            if any(np.hypot(*(q - k)) < 1.0 for k in seen):
                continue
            seen.append(q)
            v = lod0.verts[i]
            knots.append(q)
            xyz.append((v.x, v.y, v.z))
    surface = sh.TPS(knots, xyz, smooth=0.02)

    def normal(q, reference):
        q = np.asarray(q, float)
        d = 2.0
        du = surface(q + (d, 0))[0] - surface(q - (d, 0))[0]
        dv = surface(q + (0, d))[0] - surface(q - (0, d))[0]
        n = np.cross(du, dv)
        n /= np.linalg.norm(n)
        return n if n @ np.asarray(reference) >= 0 else -n
    return normal, surface, len(knots)


def fill_hole(mesh, tris, sign, step, normal):
    """The hole's piece: same texture coordinates running on, positions from a spline of the hull around it (exact at the edge), normals from the smooth surface."""
    rim = sh.rim_loop(mesh, tris, sign)
    poly = np.array([sh.px(mesh.verts[i]) for i in rim])
    points = [p for p in poly]
    us = np.arange(poly[:, 0].min(), poly[:, 0].max(), step)
    vs = np.arange(poly[:, 1].min(), poly[:, 1].max(), step)
    for u in us:
        for v in vs:
            q = np.array((u, v))
            if sh.inside_poly(np.array([u]), np.array([v]), poly)[0] and min(np.hypot(*(p - q)) for p in points) > step * 0.55:
                points.append(q)
    n = len(rim)
    out = delaunay_2d_cdt([Vector(p) for p in points], [(i, (i + 1) % n) for i in range(n)], [list(range(n))], 1, 1e-4)
    if len(out[0]) != len(points):
        raise SystemExit("the hole's triangulation added vertices")
    faces = [[out[3][i][0] for i in face] for face in out[2]]
    centre, radius = poly.mean(axis=0), np.ptp(poly[:, 0]) / 2
    knots, xyz, seen = [], [], []
    for t in tris:
        for i in mesh.tris[t]:
            q = sh.px(mesh.verts[i])
            if np.hypot(*(q - centre)) < radius * 2.2 and not any(np.hypot(*(q - k)) < 1.0 for k in seen):
                v = mesh.verts[i]
                seen.append(q)
                knots.append(q)
                xyz.append((v.x, v.y, v.z))
    shape = sh.TPS(knots, xyz)
    verts = []
    W, H = sh.W, sh.H
    template = mesh.verts[rim[0]]
    for k, q in enumerate(points):
        if k < n:
            v = mesh.verts[rim[k]].copy()
        else:
            v = template.copy()
            x, y, z = shape(q)[0]
            v.x, v.y, v.z = float(x), float(y), float(z)
            br.set_shading(v, uv_=(float(q[0] / W), float(q[1] / H)))
        br.set_shading(v, n=tuple(normal(q, br.normal(mesh.verts[rim[k if k < n else 0]]))))
        verts.append(v)
    grad = {}
    tris_out = []
    for a, b, c in faces:
        P = [np.array((verts[i].x, verts[i].y, verts[i].z)) for i in (a, b, c)]
        N = np.cross(P[1] - P[0], P[2] - P[0])
        if N @ np.array(br.normal(verts[a])) < 0:
            b, c = c, b
            P = [P[0], P[2], P[1]]
        tris_out.append((a, b, c))
        U = [np.array(br.uv(verts[i])) for i in (a, b, c)]
        e1, e2, d1, d2 = P[1] - P[0], P[2] - P[0], U[1] - U[0], U[2] - U[0]
        det = d1[0] * d2[1] - d1[1] * d2[0]
        if abs(det) < 1e-10:
            continue
        dpdu, dpdv = (e1 * d2[1] - e2 * d1[1]) / det, (e2 * d1[0] - e1 * d2[0]) / det
        for i in (a, b, c):
            g = grad.setdefault(i, [np.zeros(3), np.zeros(3)])
            g[0] += dpdv
            g[1] += dpdu
    for i, (gt, gb) in grad.items():
        nn = np.array(br.normal(verts[i]))
        nn /= np.linalg.norm(nn)
        t, b = gt - nn * (gt @ nn), gb - nn * (gb @ nn)
        br.set_shading(verts[i], t=tuple(t / np.linalg.norm(t)), b=tuple(b / np.linalg.norm(b)))
    return verts, tris_out


def angle(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return float(np.degrees(np.arccos(np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1))))


def repair_normals(mesh, tris, normal, painted):
    """The hull's vertices in the zone take the smooth surface's normal, faded out further away. Returns the deviations before and after, in degrees, of vertices inside the inner radius."""
    centre = painted.mean(axis=0)
    r = np.ptp(painted[:, 0]) / 2
    before, after, touched = [], [], set()
    for t in tris:
        for i in mesh.tris[t]:
            if i in touched:
                continue
            touched.add(i)
            v = mesh.verts[i]
            q = sh.px(v)
            d = np.hypot(*(q - centre)) / r
            ring = (np.hypot(q[0] - sh.PORTHOLE[0], q[1] - sh.PORTHOLE[1]) - sh.PORTHOLE[2]) / r
            w = min(np.clip((NORMAL_OUTER - d) / (NORMAL_OUTER - NORMAL_INNER), 0, 1), 1.0) if ring > 0.8 else 1.0
            w = max(w, np.clip((1.0 - ring), 0, 1)) if ring < 1 else w
            if w <= 0:
                continue
            old = np.array(br.normal(v))
            smooth = normal(q, old)
            new = old * (1 - w) + smooth * w
            new /= np.linalg.norm(new)
            if d < NORMAL_INNER:
                before.append(angle(old, smooth))
                after.append(angle(new, smooth))
            tangent, bitangent = np.array(br.tangent(v)), np.array(br.bitangent(v))
            t2, b2 = tangent - new * (tangent @ new), bitangent - new * (bitangent @ new)
            br.set_shading(v, n=tuple(new), t=tuple(t2 / np.linalg.norm(t2)), b=tuple(b2 / np.linalg.norm(b2)))
    return before, after


def build_model(paint):
    stock = br.STOCK.read_bytes()
    lod0 = rmv2.load(stock)["lods"][0][0]
    solid = rmv2.load(stock)
    surfaces = {}
    for sign in (1, -1):
        surfaces[sign] = smooth_surface(lod0, sign, paint.painted)
    report = []
    for li, meshes in enumerate(solid["lods"]):
        hull = meshes[0]
        tally = {"lod": li, "stock": (len(hull.verts), len(hull.tris))}
        new = hull.copy()
        new.verts, new.tris = [], []
        cut = sh.port_pieces(hull)
        for sign in (1, -1):
            tris = sh.side_piece(hull, sign)
            normal = surfaces[sign][0]
            verts, faces = fill_hole(hull, tris, sign, STEP[li], normal)
            before, after = repair_normals(hull, tris, normal, paint.painted)
            tally[f"side{sign}"] = {"new": (len(verts), len(faces)), "deg_before_mean": float(np.mean(before)), "deg_before_max": float(np.max(before)), "deg_after_max": float(np.max(after)), "fit_knots": surfaces[sign][2]}
            base = len(new.verts)
            new.verts.extend(verts)
            new.tris.extend((a + base, b + base, c + base) for a, b, c in faces)
        whole = sh._select(hull, set(range(len(hull.tris))) - cut)
        rmv2.append(whole, new)
        meshes[0] = whole
        tally["result"] = (len(whole.verts), len(whole.tris))
        report.append(tally)
    return solid, report


def write_material(name):
    """A copy of a Grungni material with our textures; the mask stays the stock file."""
    import blender_rmv2  # noqa
    text = (br.GAME_DIR / "materials" / (name + ".xml.material")).read_text(encoding="utf-8")
    own = name.replace("dwf_thunderbarge_grungni_01", OWN)
    text = text.replace(name, own)
    for part in ("base_colour", "normal", "material_map"):
        text = text.replace(f"warmachines/tex/dwf_thunderbarge_grungni_01_{part}.dds", f"{TEX}/{OWN}_{part}.dds")
    path = OUT / MAT / (own + ".xml.material")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return f"{MAT}/{own}.xml.material"


def run(textures=True):
    """Builds everything; returns the report."""
    paint = Paint()
    report = dict(paint.report)
    report["belt_shift"] = paint.shift
    tex_dir = OUT / TEX
    tex_dir.mkdir(parents=True, exist_ok=True)
    zone_all = paint.zone
    if textures:
        for part, normal in (("base_colour", False), ("material_map", False), ("normal", True)):
            dds = bd.Dds(str(br.GAME_DIR / f"dwf_thunderbarge_grungni_01_{part}.dds"))
            img = dds.read(0, *BOX).astype(np.float32)
            if normal:
                report["normal_channel_k"] = paint.measure_channels(img)
            done = paint.paint_level0(img, normal)
            write_mips(dds, done, zone_all, part)
            dds.save(str(tex_dir / f"{OWN}_{part}.dds"))
    solid, lods = build_model(paint)
    report["lods"] = lods
    folder = OUT / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    ws = (br.GAME_DIR / "stock.wsmodel").read_text(encoding="utf-8")
    for name in sorted(set(re.findall(r"warmachines/materials/([\w]+)\.xml\.material", ws))):
        own = write_material(name)
        ws = ws.replace(f"warmachines/materials/{name}.xml.material", own)
    (folder / "tww3_mtb_hull_solid.rigid_model_v2").write_bytes(rmv2.save(solid))
    (folder / "tww3_mtb_hull_solid.wsmodel").write_text(ws.replace(SOURCE, FOLDER + "/tww3_mtb_hull_solid.rigid_model_v2"), encoding="utf-8")
    cut = rmv2.load(rmv2.save(solid))
    for detail in sh.SPEC["details"]:
        if detail["name"] == "port":
            continue
        for meshes in cut["lods"]:
            mesh = meshes[detail["mesh"]]
            away = set()
            for tris, b in br.pieces(mesh):
                for area in detail["boxes"]:
                    if all(b[i] >= area[i] for i in range(3)) and all(b[i] <= area[i] for i in range(3, 6)) and (len(area) < 7 or b[3] - b[0] >= area[6]):
                        away.update(tris)
            meshes[detail["mesh"]] = sh._select(mesh, set(range(len(mesh.tris))) - away)
    (folder / "tww3_mtb_hull_solid_cut.rigid_model_v2").write_bytes(rmv2.save(cut))
    (folder / "tww3_mtb_hull_solid_cut.wsmodel").write_text(ws.replace(SOURCE, FOLDER + "/tww3_mtb_hull_solid_cut.rigid_model_v2"), encoding="utf-8")
    (OUT / "solid_hull_tex.json").write_text(json.dumps(report, indent=1, default=float), encoding="utf-8")
    return report


def full_material(name, base, normal, matmap):
    """Base colour, the DXT5 normal map (alpha U, green V), material map (red metal, green roughness). Close to, not the same as, the game's shader."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    tree.links.new(bsdf.outputs[0], out.inputs[0])
    uvn = tree.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "UVMap"

    def tex(path, colour):
        n = tree.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(str(path), check_existing=True)
        n.image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
        n.image.alpha_mode = "CHANNEL_PACKED"
        n.interpolation = "Cubic"
        tree.links.new(uvn.outputs[0], n.inputs[0])
        return n
    b, nm, m = tex(base, True), tex(normal, False), tex(matmap, False)
    tree.links.new(b.outputs[0], bsdf.inputs["Base Color"])
    sep = tree.nodes.new("ShaderNodeSeparateColor")
    tree.links.new(m.outputs[0], sep.inputs[0])
    tree.links.new(sep.outputs[0], bsdf.inputs["Metallic"])
    tree.links.new(sep.outputs[1], bsdf.inputs["Roughness"])
    # the normal: x from alpha, y from green, z from the two
    sn = tree.nodes.new("ShaderNodeSeparateColor")
    tree.links.new(nm.outputs[0], sn.inputs[0])
    comb = tree.nodes.new("ShaderNodeCombineColor")
    tree.links.new(nm.outputs[1], comb.inputs[0])
    tree.links.new(sn.outputs[1], comb.inputs[1])
    comb.inputs[2].default_value = 1.0
    node = tree.nodes.new("ShaderNodeNormalMap")
    node.uv_map = "UVMap"
    tree.links.new(comb.outputs[0], node.inputs[1])
    tree.links.new(node.outputs[0], bsdf.inputs["Normal"])
    return mat


def grey_material(name="grey"):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.5, 0.5, 0.5, 1)
    bsdf.inputs["Roughness"].default_value = 0.45
    return mat


def paths_new():
    t = OUT / TEX
    return t / f"{OWN}_base_colour.dds", t / f"{OWN}_normal.dds", t / f"{OWN}_material_map.dds"


def paths_stock():
    g = br.GAME_DIR
    return g / "dwf_thunderbarge_grungni_01_base_colour.dds", g / "dwf_thunderbarge_grungni_01_normal.dds", g / "dwf_thunderbarge_grungni_01_material_map.dds"


def show():
    """Live Blender: the three hulls side by side (stock, previous, new) with textures, collection 'solid_hull_tex'; saves build/solid_hull_tex/work.blend."""
    coll = bpy.data.collections.get("solid_hull_tex") or bpy.data.collections.new("solid_hull_tex")
    if coll.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    for ob in list(coll.objects):
        bpy.data.objects.remove(ob)
    stock_mat = full_material("stock_full", *paths_stock())
    new_mat = full_material("new_full", *paths_new())
    prev = br.REPO / "build" / "solid_hull" / FOLDER / "tww3_mtb_hull_solid.rigid_model_v2"
    new = OUT / FOLDER / "tww3_mtb_hull_solid.rigid_model_v2"
    for name, path, mat, dx in (("stock", br.STOCK, stock_mat, -16.0), ("previous", prev, stock_mat, 0.0), ("new", new, new_mat, 16.0)):
        mesh = rmv2.load(Path(path).read_bytes())["lods"][0][0]
        ob = br.add_mesh(bpy, mesh, f"hull_{name}", mat)
        for c in ob.users_collection:
            c.objects.unlink(ob)
        coll.objects.link(ob)
        ob.location.x = dx
    OUT.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "work.blend"), copy=True)


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, default=float))
