"""Steel over the four bomb hatches of the Spirit of Grungni, rebuilt from the stock atlas (project venv: numpy, scipy, Pillow).

  python tools/blender_skill_hatches_tex.py dry     builds, previews to build/solid_hull_hatches/shots/, prints the report
  python tools/blender_skill_hatches_tex.py build   the same, then the three DDS into build/solid_hull_hatches/tex/
                                                    (base: build/solid_hull_hatches/orig/tex_tank, the textures before this pass)
The model side is tools/blender_skill_hatches_geo.py (live Blender); its UV offsets are ZONES[...]["patch"] here.
The parts (hull with holes, covers, niches) are cut from the written model by tools/hatches_split.py.

How the atlas lies (measured, see structure.md): the hull bottom is one band of steel plates (atlas rows ~3764..4005,
u along the ship, about 102 px/m); both sides of the hull read the same band (mirror). Plate seams run across the band
(transverse seams of the hull), a plate is 80..153 px long. Each hatch hole maps to a rectangle of the band, which holds
other parts' painting (packed island with a white glow, read by deck fittings, fins, the stern chimney cap): it stays.

What is built, per hatch (zone Z around the hole and around the hatch frame rivets):
  * NEW: pieces of the stock band at the same rows, left to right; a piece is anchored on a seam (x_src = S_src(y) + x -
    S_dst(y), smooth seam tracks, so the copied seam lies on the destination seam's line, which runs on from its stubs
    above and below the hole) or is a plain shift of a plate's clean interior. Rivets come whole with their seam. One
    source per pixel: neighbouring pieces meet on a minimum-error cut (dynamic programming down the rows), 1.5 px ramp.
  * the hatch frame rivets around the hole (corners, and at the crossing seams just above / below it) are replaced;
  * NEW meets the stock on a minimum-error cut inside a ring around the must-replace area (top, bottom, left, right);
  * tone and gloss: a smooth offset (harmonic inside, from the smoothed difference on the ring), base colour and
    material map only; detail stays the source's own.
Written: (1) the band itself outside the hole (ring, frame rivets, the unread glow) where no other part reads it, mips
recomputed there; (2) the whole zone as a patch at a free atlas spot; the new hull faces over each hole read the patch
(UV = band UV + PATCH offset, a whole pixel shift; the spot's u stays below 0.5, so the half-float UVs are exact).
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage as nd
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
W = REPO / "build" / "solid_hull_hatches"          # work folder: orig/, tex/, shots/
sys.path.insert(0, str(REPO / "tools"))
from blender_dds import Dds  # noqa: E402
from blender_skill_plank2 import sample  # noqa: E402  (Catmull-Rom)
import blender_rmv2 as br  # noqa: E402
import rmv2  # noqa: E402

GAME = REPO / "build" / "solid_hull" / "game"
BASE = W / "orig" / "tex_tank"          # the textures before this pass (= build/solid_hull_tank/tex)
OUTTEX = W / "tex"
MODEL = REPO / "build" / "solid_hull_tank" / "warmachines/aircraft/dwf_thunderbarge/tww3_mtb_dwf_thunderbarge_01.rigid_model_v2"
NAMES = ("base_colour", "normal", "material_map")
BAND = (1152, 3712, 2560, 4096)         # loaded window (aligned to 64)
ROWS = (3768, 3996)                     # rows where seams are tracked
SEAM_GUESS = [1231, 1320, 1401, 1489, 1573, 1655, 1745, 1832, 1948, 2101, 2192, 2280]
RAMP = 1.5
RING = 6

ZONES = {
    "front": dict(
        rect=(1286, 3808, 1448, 3944),
        poly=[(1293, 3808), (1445, 3810), (1445, 3852), (1448, 3892), (1442, 3944), (1286, 3942), (1289, 3896), (1288, 3850)],
        frame=[(1280.5, 3820.5), (1275.7, 3933.0), (1456.7, 3817.7), (1456.1, 3935.5), (1331.4, 3798.4), (1391.0, 3799.5), (1326.8, 3952.0), (1386.2, 3952.2)],
        keep=[(1473.1, 3837.7), (1475.0, 3900.8), (1311.0, 3774.4), (1332.0, 3775.4), (1391.9, 3776.2), (1415.5, 3775.0), (1325.3, 3985.4), (1386.0, 3985.3)],
        cross=[1320, 1401],
        # (dest x0, x1, dest anchor seam or None, source seam or None, dx for interior)
        pieces=[(1256, 1368, 1320, 1655, None), (1356, 1462, 1401, 2192, None), (1452, 1476, 1489, 1832, None)],
        patch=(-696, -3780), box=(576, 0, 768, 192)),
    "rear": dict(
        rect=(1870, 3808, 2029, 3942),
        poly=[(1870, 3808), (2026, 3810), (2026, 3852), (2029, 3892), (2024, 3942), (1871, 3940), (1870, 3890), (1871, 3850)],
        frame=[(1937.2, 3799.0), (1962.2, 3797.5), (1935.2, 3949.4), (1959.8, 3951.2), (2037.6, 3835.7), (2041.7, 3903.0)],
        keep=[(1842.5, 3827.5), (1840.7, 3888.1), (2090.9, 3851.0), (2096.1, 3912.1)],
        cross=[1948],
        pieces=[(1852, 1904, 1832, 2101, None), (1890, 1996, 1948, 1745, None), (1984, 2036, None, None, -466), (2026, 2062, None, None, 284)],
        patch=(-248, -3796), box=(1616, 0, 1792, 160)),
}
FRAME_R = 8.0          # a frame rivet with its dark ring
KEEP_R = 7.5


def load(path_of):
    return {nm: Dds(path_of(nm)).read(0, *BAND).astype(np.float32) for nm in NAMES}


def stock_path(nm):
    return GAME / f"dwf_thunderbarge_grungni_01_{nm}.dds"


def base_path(nm):
    return BASE / f"tww3_mtb_dwf_thunderbarge_grungni_01_{nm}.dds"


def out_path(nm):
    return OUTTEX / f"tww3_mtb_dwf_thunderbarge_grungni_01_{nm}.dds"


# ---- seams ------------------------------------------------------------------------------------------------------------
def track_raw(na, guess, rows, half=4):
    g = nd.uniform_filter1d(na.astype(float), 3, axis=0)
    xs = np.full(len(rows), np.nan)
    depth = np.full(len(rows), np.nan)
    x = guess
    for i, y in enumerate(rows):
        j0 = int(round(x)) - half
        seg = g[y - BAND[1], j0 - BAND[0]:j0 - BAND[0] + 2 * half + 1]
        k = int(np.argmin(seg))
        off = 0.0
        if 0 < k < len(seg) - 1:
            a, b, c = seg[k - 1], seg[k], seg[k + 1]
            den = a - 2 * b + c
            off = 0.5 * (a - c) / den if den > 0 else 0.0
        xs[i] = j0 + k + off
        depth[i] = seg[k] - np.median(seg)
        if abs(xs[i] - guess) < 6:
            x = xs[i]
    return xs, depth


def seams(na):
    """{guess: dict(rows, raw, ok, smooth(y) callable, fit report)}. Rows inside a hatch zone are not used for a seam
    that crosses it; the smooth track there is the quadratic through the stubs above and below."""
    rows = np.arange(*ROWS)
    out = {}
    for s in SEAM_GUESS:
        raw, depth = track_raw(na, s, rows)
        ok = np.isfinite(raw) & (depth < -6)
        crossing = None
        for zn, z in ZONES.items():
            if s in z["cross"]:
                crossing = zn
                ok &= ~((rows >= z["rect"][1] - 18) & (rows <= z["rect"][3] + 18))
        med = nd.median_filter(np.where(ok, raw, s), 9)
        ok &= np.abs(raw - med) < 1.5
        p2 = np.polyfit(rows[ok], raw[ok], 2)
        if crossing:
            sm_rows, sm = rows, np.polyval(p2, rows)
        else:
            # running median of the measured track (follows the hand-drawn wiggle at > 21 rows), gaps bridged linearly
            r_ok, x_ok = rows[ok], raw[ok]
            filled = np.interp(rows, r_ok, x_ok)
            sm = nd.uniform_filter1d(nd.median_filter(filled, 21, mode="nearest"), 7, mode="nearest")
            sm_rows = rows
        res = raw[ok] - np.interp(rows[ok], sm_rows, sm)
        above = ok & (rows < 3800)
        below = ok & (rows > 3955)
        out[s] = dict(rows=rows, raw=raw, ok=ok, sm=sm, crossing=crossing,
                      rep=dict(points=int(ok.sum()), above=int(above.sum()), below=int(below.sum()),
                               res_max=round(float(np.abs(res).max()), 2), res_rms=round(float(np.sqrt((res ** 2).mean())), 2),
                               res_above=round(float(np.abs(raw[above] - np.interp(rows[above], sm_rows, sm)).max()), 2) if above.any() else None,
                               res_below=round(float(np.abs(raw[below] - np.interp(rows[below], sm_rows, sm)).max()), 2) if below.any() else None,
                               x_top_mid_bottom=[round(float(np.interp(y, sm_rows, sm)), 1) for y in (3790, 3876, 3962)]))
    return out


def S(seam, y):
    return np.interp(y, seam["rows"], seam["sm"])


# ---- pieces -------------------------------------------------------------------------------------------------------------
def disc_mask(shape, origin, pts, r):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    m = np.zeros(shape, bool)
    for x, y in pts:
        m |= np.hypot(xx + origin[0] - x, yy + origin[1] - y) <= r
    return m


def poly_mask(shape, origin, poly):
    im = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(im).polygon([(x - origin[0], y - origin[1]) for x, y in poly], fill=1, outline=1)
    return np.array(im) > 0


def zone_geometry(z):
    """Zone box (x0, y0, x1, y1) in atlas px and masks in it: N (must be new), K (stock rivets to keep)."""
    r = z["rect"]
    xs = [r[0] - 2, r[2] + 2] + [x - FRAME_R for x, _ in z["frame"]] + [x + FRAME_R for x, _ in z["frame"]]
    ys = [r[1] - 2, r[3] + 2] + [y - FRAME_R for _, y in z["frame"]] + [y + FRAME_R for _, y in z["frame"]]
    box = (int(np.floor(min(xs))) - RING, int(np.floor(min(ys))) - RING, int(np.ceil(max(xs))) + RING + 1, int(np.ceil(max(ys))) + RING + 1)
    shape = (box[3] - box[1], box[2] - box[0])
    N = np.zeros(shape, bool)
    N[r[1] - 2 - box[1]:r[3] + 3 - box[1], r[0] - 2 - box[0]:r[2] + 3 - box[0]] = True
    N |= disc_mask(shape, box[:2], z["frame"], FRAME_R)
    K = disc_mask(shape, box[:2], z["keep"], KEEP_R)
    return box, N, K


def piece_image(st, sm, box, piece):
    """The stock sampled for one piece over the whole zone box (all maps), and its source x per pixel."""
    x0, x1, dst, src, dx = piece
    yy, xx = np.mgrid[box[1]:box[3], box[0]:box[2]].astype(np.float64)
    if dst is not None:
        xs = S(sm[src], yy) + (xx - S(sm[dst], yy))
    else:
        xs = xx + dx
    out = {nm: sample(st[nm], (xs - BAND[0]).ravel(), (yy - BAND[1]).ravel()).reshape(xx.shape + (4,)) for nm in NAMES}
    return out, xs, yy


def feat(img):
    return np.concatenate([img["base_colour"][..., :3].mean(-1, keepdims=True), img["normal"][..., 3:4], img["normal"][..., 1:2]], -1)


def dp_cut(cost, lo, hi, step=1, smooth=0.0):
    """Path down the rows: one column per row in [lo, hi] (absolute indexes into cost's columns), |change| <= step.
    Returns the column per row of the cheapest path."""
    H, Wd = cost.shape
    INF = 1e18
    acc = np.full((H, Wd), INF)
    back = np.zeros((H, Wd), np.int32)
    allowed = np.zeros((H, Wd), bool)
    for y in range(H):
        allowed[y, max(0, lo[y]):min(Wd, hi[y] + 1)] = True
    acc[0] = np.where(allowed[0], cost[0], INF)
    for y in range(1, H):
        best = np.full(Wd, INF)
        arg = np.zeros(Wd, np.int32)
        for d in range(-step, step + 1):
            prev = np.roll(acc[y - 1], d)
            if d > 0:
                prev[:d] = INF
            elif d < 0:
                prev[d:] = INF
            prev = prev + smooth * abs(d)
            better = prev < best
            best = np.where(better, prev, best)
            arg = np.where(better, np.arange(Wd) - d, arg)
        acc[y] = np.where(allowed[y], best + cost[y], INF)
        back[y] = arg
    path = np.zeros(H, np.int32)
    path[-1] = int(np.argmin(acc[-1]))
    if acc[-1, path[-1]] >= INF:
        raise RuntimeError("no cut path")
    for y in range(H - 1, 0, -1):
        path[y - 1] = back[y, path[y]]
    return path


def build_zone(zn, st, cu, sm, report):
    z = ZONES[zn]
    box, N, K = zone_geometry(z)
    H, Wd = N.shape
    yy, xx = np.mgrid[box[1]:box[3], box[0]:box[2]].astype(np.float64)
    imgs, srcx = [], []
    for p in z["pieces"]:
        im, xs, _ = piece_image(st, sm, box, p)
        imgs.append(im)
        srcx.append(xs)
    # left to right: label per pixel by cuts in the overlaps
    lab = np.zeros((H, Wd), np.int32)
    cuts = []
    for i in range(1, len(imgs)):
        a, b = feat(imgs[i - 1]), feat(imgs[i])
        cost = np.abs(a - b).sum(-1)
        lo = np.full(H, z["pieces"][i][0] - box[0] + 2)
        hi = np.full(H, z["pieces"][i - 1][1] - box[0] - 2)
        path = dp_cut(cost, lo, hi, step=1, smooth=2.0)
        cuts.append(path)
        lab[np.arange(Wd)[None, :] > path[:, None] + 0.0] = i
    # cut ramps: weight of piece i from its left cut
    new = {nm: imgs[0][nm].copy() for nm in NAMES}
    for i in range(1, len(imgs)):
        w = np.clip((np.arange(Wd)[None, :] - cuts[i - 1][:, None] - 0.5) / RAMP + 0.5, 0, 1)[..., None]
        for nm in NAMES:
            new[nm] = new[nm] * (1 - w) + imgs[i][nm] * w
    # source of each pixel (report and checks)
    sx = np.choose(lab, srcx)
    # the cut against the stock: inside a ring around N; four sides by DP, K stays stock
    stk = {nm: cu[nm][box[1] - BAND[1]:box[3] - BAND[1], box[0] - BAND[0]:box[2] - BAND[0]] for nm in NAMES}
    err = np.abs(feat(new) - feat(stk)).sum(-1)
    err = np.where(K, 1e6, err)
    rows_n = np.where(N.any(1))[0]
    cols_n = np.where(N.any(0))[0]
    nl = np.array([np.where(N[y])[0].min() if N[y].any() else Wd for y in range(H)])
    nr = np.array([np.where(N[y])[0].max() if N[y].any() else -1 for y in range(H)])
    nt = np.array([np.where(N[:, x])[0].min() if N[:, x].any() else H for x in range(Wd)])
    nb = np.array([np.where(N[:, x])[0].max() if N[:, x].any() else -1 for x in range(Wd)])
    left = dp_cut(err, np.zeros(H, int), np.minimum(nl - 1, RING), smooth=1.0)
    right = dp_cut(err, np.maximum(nr + 1, Wd - 1 - RING), np.full(H, Wd - 1), smooth=1.0)
    top = dp_cut(err.T, np.zeros(Wd, int), np.minimum(nt - 1, RING), smooth=1.0)
    bot = dp_cut(err.T, np.maximum(nb + 1, H - 1 - RING), np.full(Wd, H - 1), smooth=1.0)
    X, Y = np.mgrid[0:H, 0:Wd][1], np.mgrid[0:H, 0:Wd][0]
    d_in = np.minimum.reduce([X - left[:, None], right[:, None] - X, Y - top[None, :], bot[None, :] - Y]).astype(float)
    m = np.clip(d_in / RAMP + 0.5, 0, 1)
    m = np.where(K & ~N, 0.0, m)
    m = np.maximum(m, N.astype(float))
    # tone: smooth offset from the ring (stock known there), harmonic inside
    dom = m > 0.5
    ring = ~dom & nd.binary_dilation(dom, np.ones((7, 7), bool)) & ~K
    offs = {}
    for nm, chs in (("base_colour", (0, 1, 2)), ("material_map", (0, 1, 2))):
        for c in chs:
            diff = stk[nm][..., c] - new[nm][..., c]
            lum_d = stk["base_colour"][..., :3].mean(-1) - new["base_colour"][..., :3].mean(-1)
            use = ring & (np.abs(lum_d - np.median(lum_d[ring])) < 25)
            g = np.where(use, diff, 0.0)
            den = nd.gaussian_filter(use.astype(float), 6)
            fixed = nd.gaussian_filter(g, 6) / np.maximum(den, 1e-6)
            D = np.where(dom, float(np.median(diff[use])), np.where(ring, fixed, 0.0))
            for _ in range(4000):
                Dp = np.pad(D, 1, mode="edge")
                sm4 = (Dp[:-2, 1:-1] + Dp[2:, 1:-1] + Dp[1:-1, :-2] + Dp[1:-1, 2:]) / 4.0
                D = np.where(dom, sm4, D)
            new[nm][..., c] = new[nm][..., c] + D * (m > 0)
            offs[f"{nm}{c}"] = [round(float(np.percentile(D[dom], 5)), 1), round(float(np.percentile(D[dom], 95)), 1)]
    V = {nm: np.clip(stk[nm] * (1 - m[..., None]) + new[nm] * m[..., None], 0, 255) for nm in NAMES}
    # checks: sources clean (outside both zones' boxes, outside earlier passes x < 1190, inside the band window)
    bad = 0
    for zn2, z2 in ZONES.items():
        b2, _, _ = zone_geometry(z2)
        bad += int(((sx >= b2[0] - 3) & (sx <= b2[2] + 3) & (m > 0)).sum())
    bad_prev = int(((sx < 1192) & (m > 0)).sum())
    used = {i: [round(float(sx[(lab == i) & (m > 0)].min()), 1), round(float(sx[(lab == i) & (m > 0)].max()), 1)] if ((lab == i) & (m > 0)).any() else None
            for i in range(len(imgs))}
    report[zn] = dict(box=box, px_new=int((m > 0).sum()), must_new=int(N.sum()), source_x_per_piece=used, src_px_in_a_zone=bad,
                      src_px_in_earlier_edit=bad_prev, tone_offset_p5_p95=offs, transition_px=RAMP,
                      cut_cols_between_pieces=[[int(c.min() + box[0]), int(c.max() + box[0])] for c in cuts],
                      ring_cut=dict(left=[int(left.min()), int(left.max())], right=[int(right.min()), int(right.max())],
                                    top=[int(top.min()), int(top.max())], bottom=[int(bot.min()), int(bot.max())]))
    return dict(box=box, m=m, V=V, new=new, N=N, K=K, lab=lab, sx=sx, cuts=cuts)


# ---- readers of the band near the hatches: every triangle but the hull bottom's own band faces ------------------------
def readers_mask(model_path, boxes, pad=2):
    model = rmv2.load(Path(model_path).read_bytes())
    H, Wd = BAND[3] - BAND[1], BAND[2] - BAND[0]
    im = Image.new("L", (Wd, H), 0)
    d = ImageDraw.Draw(im)
    n = 0
    for lod in model["lods"]:
        for pi, mesh in enumerate(lod):
            for t in mesh.tris:
                uv = np.array([br.uv(mesh.verts[i]) for i in t]) * 4096
                if not any(uv[:, 0].max() >= b[0] - 4 and uv[:, 0].min() <= b[2] + 4 and uv[:, 1].max() >= b[1] - 4 and uv[:, 1].min() <= b[3] + 4 for b in boxes):
                    continue
                cy = np.mean([mesh.verts[i].y for i in t])
                band = pi == 0 and cy < 1.0 and uv[:, 0].min() >= 1080 and uv[:, 0].max() <= 2520 and uv[:, 1].min() >= 3755 and uv[:, 1].max() <= 4010
                if band:
                    continue
                d.polygon([(u - BAND[0], v - BAND[1]) for u, v in uv], fill=255, outline=255)
                n += 1
    R = np.array(im) > 0
    return nd.binary_dilation(R, iterations=pad), n


def build():
    st = load(stock_path)
    cu = load(base_path)
    sm = seams(st["normal"][..., 3])
    rep = {"seams": {s: v["rep"] for s, v in sm.items()}}
    zones = {zn: build_zone(zn, st, cu, sm, rep) for zn in ZONES}
    R, nread = readers_mask(MODEL, [z["box"] for z in zones.values()])
    rep["reader_tris"] = nread
    # the virtual band: the stock band with the new steel over each zone (also over the hole: the patch shows it)
    Vfull = {nm: cu[nm].copy() for nm in NAMES}
    for zn, Z in zones.items():
        x0, y0, x1, y1 = Z["box"]
        for nm in NAMES:
            Vfull[nm][y0 - BAND[1]:y1 - BAND[1], x0 - BAND[0]:x1 - BAND[0]] = Z["V"][nm]
    # level 0 of the band in place: new where no other part reads it (outside the hole that is the ring and the frame
    # rivets; inside it, the glow that nothing reads)
    zone_any = np.zeros(R.shape, bool)
    for Z in zones.values():
        x0, y0, x1, y1 = Z["box"]
        zone_any[y0 - BAND[1]:y1 - BAND[1], x0 - BAND[0]:x1 - BAND[0]] |= Z["m"] > 0
        x0r, y0r, x1r, y1r = (Z["box"][0], Z["box"][1], Z["box"][2], Z["box"][3])
    holes = np.zeros(R.shape, bool)
    for z in ZONES.values():
        holes |= poly_mask(R.shape, BAND[:2], z["poly"])
    write0 = ~R
    for z in ZONES.values():
        r = z["rect"]
        inside = np.zeros(R.shape, bool)
        inside[r[1] - BAND[1]:r[3] - BAND[1] + 1, r[0] - BAND[0]:r[2] - BAND[0] + 1] = True
        write0 &= ~inside | ~R
    F0 = {nm: np.where((write0 & (zone_any | holes))[..., None], Vfull[nm], cu[nm]) for nm in NAMES}
    conflict = int((zone_any & ~holes & R).sum())
    rep["band_px_needing_new_but_read_by_others"] = conflict
    rep["band_px_written_level0"] = int((np.abs(F0["base_colour"] - cu["base_colour"]).max(-1) > 0.5).sum())
    return dict(st=st, cu=cu, sm=sm, zones=zones, R=R, Vfull=Vfull, F0=F0, rep=rep)


# ---- writing ----------------------------------------------------------------------------------------------------------
def _down(a, k):
    for _ in range(k):
        h, w = a.shape[0] // 2, a.shape[1] // 2
        a = a[:h * 2, :w * 2].reshape(h, 2, w, 2, -1).mean((1, 3))
    return a


def save(B):
    """Band: level 0 = F0; each mip level of the blocks near the zones = 2x2 means of the virtual band where the texel
    (with a 1 texel margin) touches no other part's UVs, of F0 where it does; blocks that come out equal keep their
    bytes. Patches: the virtual band over each hole, at its spot, all levels; at levels where a block of the spot also
    holds texels outside the spot, those texels keep their decoded values (the block is re-encoded)."""
    rep = {}
    OUTTEX.mkdir(parents=True, exist_ok=True)
    gx0, gy0 = (BAND[0] // 256) * 256, (BAND[1] // 256) * 256      # window aligned for 6 levels
    for nm in NAMES:
        dds = Dds(base_path(nm))
        counts = {}
        # band blocks near the zones: per zone a box aligned to 64 px
        for zn, Z in B["zones"].items():
            x0, y0, x1, y1 = Z["box"]
            ax0, ay0 = (x0 - 16) // 64 * 64, (y0 - 16) // 64 * 64
            ax1, ay1 = -(-(x1 + 16) // 64) * 64, -(-(y1 + 16) // 64) * 64
            ay1 = min(ay1, 4096)
            sl = (slice(ay0 - BAND[1], ay1 - BAND[1]), slice(ax0 - BAND[0], ax1 - BAND[0]))
            f0 = B["F0"][nm][sl]
            vf = B["Vfull"][nm][sl]
            rr = B["R"][sl].astype(float)
            cur0 = B["cu"][nm][sl]
            n_enc = 0
            for level in range(dds.mips):
                s = 1 << level
                w_, h_ = (ax1 - ax0) // s, (ay1 - ay0) // s
                if w_ < 4 or h_ < 4 or w_ % 4 or h_ % 4:
                    break
                if level == 0:
                    lv = f0
                else:
                    touch = _down(rr[..., None], level)[..., 0] > 0
                    touch = nd.binary_dilation(touch, iterations=1)
                    lv = np.where(touch[..., None], _down(f0, level), _down(vf, level))
                old = dds.read(level, ax0 // s, ay0 // s, ax1 // s, ay1 // s).astype(np.float32)
                q = np.clip(np.round(lv), 0, 255)
                if nm == "base_colour":
                    q[..., 3] = 255
                # only texels whose footprint holds a changed pixel (others keep their bytes)
                near = _down((np.abs(vf - cur0).max(-1, keepdims=True) > 0.5).astype(float), level)[..., 0] > 0
                # (no margin: a texel whose footprint holds no changed pixel keeps its stock filtering)
                q = np.where(near[..., None], q, old)
                changed = (np.abs(q - old).max(-1) > 0.5)
                blk = changed.reshape(h_ // 4, 4, w_ // 4, 4).any((1, 3))
                dds.write(level, ax0 // s, ay0 // s, q.astype(np.uint8), only=blk)
                n_enc += int(blk.sum())
            counts[f"band_{zn}_blocks"] = n_enc
        # patches
        for zn, Z in B["zones"].items():
            z = ZONES[zn]
            px, py = z["patch"]
            bx0, by0, bx1, by1 = z["box"]
            src = B["Vfull"][nm][by0 - py - BAND[1]:by1 - py - BAND[1], bx0 - px - BAND[0]:bx1 - px - BAND[0]]
            n_enc = 0
            for level in range(dds.mips):
                s = 1 << level
                lx0, ly0, lx1, ly1 = bx0 / s, by0 / s, bx1 / s, by1 / s
                if lx1 - lx0 < 1:
                    break
                # block-aligned box at this level that covers the spot
                ax0, ay0 = int(lx0) // 4 * 4, int(ly0) // 4 * 4
                ax1, ay1 = -(-int(np.ceil(lx1)) // 4) * 4, -(-int(np.ceil(ly1)) // 4) * 4
                old = dds.read(level, ax0, ay0, ax1, ay1).astype(np.float32)
                lv = _down(src, level)
                q = old.copy()
                ix0, iy0 = int(np.ceil(lx0)) - ax0, int(np.ceil(ly0)) - ay0
                q[iy0:iy0 + lv.shape[0], ix0:ix0 + lv.shape[1]] = np.clip(np.round(lv), 0, 255)
                if nm == "base_colour":
                    q[..., 3] = 255
                changed = np.abs(q - old).max(-1) > 0.5
                h_, w_ = changed.shape
                blk = changed.reshape(h_ // 4, 4, w_ // 4, 4).any((1, 3))
                dds.write(level, ax0, ay0, q.astype(np.uint8), only=blk)
                n_enc += int(blk.sum())
            counts[f"patch_{zn}_blocks"] = n_enc
        dds.save(out_path(nm))
        rep[nm] = counts
    return rep


def check_written(B):
    """Re-read the written DDS: level 0 of the band and patch equal to what was built (within BC error), and nothing
    changed outside the written boxes."""
    rep = {}
    for nm in NAMES:
        a = Dds(base_path(nm)).read(0, 0, 0, 4096, 4096).astype(np.float32)
        b = Dds(out_path(nm)).read(0, 0, 0, 4096, 4096).astype(np.float32)
        ch = np.abs(a - b).max(-1) > 0
        lab, n = nd.label(nd.binary_dilation(ch, iterations=4))
        boxes = [(s[1].start, s[0].start, s[1].stop, s[0].stop) for s in nd.find_objects(lab)]
        rep[nm] = dict(changed_px=int(ch.sum()), regions=boxes)
        for zn, z in ZONES.items():
            px, py = z["patch"]
            bx0, by0, bx1, by1 = z["box"]
            want = B["Vfull"][nm][by0 - py - BAND[1]:by1 - py - BAND[1], bx0 - px - BAND[0]:bx1 - px - BAND[0]]
            got = b[by0:by1, bx0:bx1]
            rep[nm][f"patch_{zn}_err_mean_max"] = [round(float(np.abs(got - want)[..., :3].mean()), 2), round(float(np.abs(got - want)[..., :3].max()), 1)]
    return rep


# ---- previews ----------------------------------------------------------------------------------------------------------
def preview_simple(B, path, k=3, which="bc"):
    tiles = []
    for zn, Z in B["zones"].items():
        x0, y0, x1, y1 = Z["box"]
        x0 -= 30; x1 += 30; y0 -= 14; y1 += 14
        sl = (slice(y0 - BAND[1], y1 - BAND[1]), slice(x0 - BAND[0], x1 - BAND[0]))
        pair = []
        for src in (B["st"], B["Vfull"]):
            if which == "bc":
                a = src["base_colour"][sl][..., :3]
            elif which == "mm":
                a = src["material_map"][sl][..., :3]
            else:
                a = np.repeat(src["normal"][sl][..., 3 if which == "na" else 1][..., None], 3, -1)
            im = Image.fromarray(np.clip(np.round(a), 0, 255).astype(np.uint8))
            pair.append(im.resize((im.width * k, im.height * k), Image.NEAREST))
        tiles.append(pair)
    w = sum(p[0].width for p in tiles) + 8 * (len(tiles) - 1)
    h = max(p[0].height for p in tiles)
    sheet = Image.new("RGB", (w, 2 * h + 8), (255, 255, 255))
    x = 0
    for p in tiles:
        sheet.paste(p[0], (x, 0))
        sheet.paste(p[1], (x, h + 8))
        x += p[0].width + 8
    sheet.save(path)


if __name__ == "__main__":
    B = build()
    for which in ("bc", "na", "ng", "mm"):
        preview_simple(B, str(W / "shots" / f"atlas_{which}.png"), which=which)
    if len(sys.argv) > 1 and sys.argv[1] == "build":
        B["rep"]["save"] = save(B)
        B["rep"]["check"] = check_written(B)
    print(json.dumps(B["rep"], indent=1, default=str))
