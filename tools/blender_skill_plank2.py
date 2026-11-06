"""Second pass over the wood of the closed gun port (numpy only, so it runs inside the live Blender through MCP).

User's marks on the first pass: the bottom plank had two parallel gaps (the laid one and one carried along an arc from the
right, where the gap is not an arc), and the wood of the patch was soft (candidates averaged, gaps erased by averaging
along rows, one stretch of the gap tiled with its nail mark three times).

This pass rebuilds the wood of the patch from the stock atlas, sharp:
  * plank structure: the belt edge and the two gaps above it are measured on the stock outside the patch; inside it each
    gap is a Hermite curve meeting the stock gap in place and slope on both sides (one gap, entering where the stock one
    enters and leaving where the stock one leaves);
  * a pixel's plank coordinate q: -1 at the belt edge, 0 on the first gap, 1 on the second, above it the distance;
  * the wood is cut into strips of q (strip borders run along the grain); every strip copies one stretch of clean stock
    wood at the same q (one source per pixel, bicubic, no averaging), each strip from another place, so nothing repeats
    in a row;
  * the patch meets the stock on a cut that runs across the strips where fill and stock agree best (dynamic programming
    per row, as in image quilting), feathered over 1.5 px, instead of the 16 px cross-grain blend.
Base colour, normal and material map take the same source pixels.

  import blender_skill_plank2 as p2; p2.build()      -> report; p2.OUT holds the new windows
  p2.push_live()                                      writes them into the scene's images (new_*)
  p2.save_dds()                                       writes level 0 and mips of the box to build/solid_hull_skill/tex/
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from blender_dds import Dds  # noqa: E402

GAME = REPO / "build" / "solid_hull" / "game"
TEX = REPO / "build" / "solid_hull_skill" / "tex"
NAMES = ("base_colour", "normal", "material_map")
WIN = (640, 3456, 1664, 4096)
BOX = (896, 3584, 1280, 3968)
AC = (1268.2, 4852.0)                      # centre of the plank arcs (atlas)
CENTRE, R, FEATHER, STRETCH = (1052.0, 3787.0), 94.0, 16.0, 1.1
PORTHOLE_C, PORTHOLE_KEEP = (1031.0, 3652.0), 51.0
KNOT_SR = (165.0, 265.0, 1146.0, 1184.0)     # the knot right of the port, as (s0, s1, r0, r1): never a source
RS = 1120.0                                # arc length scale of s
SRC_RANGES = ((-215.0, -112.0), (92.0, 432.0))     # s ranges of clean stock wood (left of the port, right of it)
G1_ANCH, G2_ANCH = (-112.0, 88.0), (-110.0, 95.0)  # where the stock gaps stop being trusted (patch side)
STRIPS = (-0.5, 0.3, 0.75, 1.35, 1.85)     # strip borders in q (gaps at 0 and 1 stay inside strips)
OUT = {}
STATE = {}


def stock(name):
    return GAME / f"dwf_thunderbarge_grungni_01_{name}.dds"


def cur_path(name):
    return TEX / f"tww3_mtb_dwf_thunderbarge_grungni_01_{name}.dds"


# ---- small numpy filters ------------------------------------------------------------------------------------------
def box(a, ry, rx):
    """Mean over a (2ry+1) x (2rx+1) box, edges clamped."""
    a = np.asarray(a, np.float64)
    p = np.pad(a, ((ry + 1, ry), (rx + 1, rx)), mode="edge")
    c = p.cumsum(0).cumsum(1)
    h, w = a.shape
    s = c[2 * ry + 1:2 * ry + 1 + h, 2 * rx + 1:2 * rx + 1 + w] - c[:h, 2 * rx + 1:2 * rx + 1 + w] \
        - c[2 * ry + 1:2 * ry + 1 + h, :w] + c[:h, :w]
    return s / ((2 * ry + 1) * (2 * rx + 1))


def dilate(m, r):
    return box(m.astype(np.float32), r, r) > 1e-6


def erode(m, r):
    return box(m.astype(np.float32), r, r) > 1 - 1e-6


def sample(img, x, y, cubic=True):
    """img h x w x c at window coords x, y (arrays); Catmull-Rom or bilinear; edges clamped."""
    h, w = img.shape[:2]
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    if not cubic:
        g = lambda yy, xx: img[np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1)]
        return (g(y0, x0) * (1 - fx) + g(y0, x0 + 1) * fx) * (1 - fy) + (g(y0 + 1, x0) * (1 - fx) + g(y0 + 1, x0 + 1) * fx) * fy

    def wts(t):
        return [((-t + 2) * t - 1) * t / 2, ((3 * t - 5) * t * t + 2) / 2, ((-3 * t + 4) * t + 1) * t / 2, (t - 1) * t * t / 2]
    wx, wy = wts(fx), wts(fy)
    acc = 0
    for j in range(4):
        yy = np.clip(y0 + j - 1, 0, h - 1)
        row = 0
        for i in range(4):
            row = row + img[yy, np.clip(x0 + i - 1, 0, w - 1)] * wx[i]
        acc = acc + row * wy[j]
    return acc


# ---- geometry of the atlas ----------------------------------------------------------------------------------------
_ac = (AC[0] - WIN[0], AC[1] - WIN[1])
_phc = math.atan2(CENTRE[1] - AC[1], CENTRE[0] - AC[0])


def to_sr(x, y):
    """Window px -> (s arc length from the port's angle, r distance from the arc centre)."""
    return (np.arctan2(y - _ac[1], x - _ac[0]) - _phc) * RS, np.hypot(x - _ac[0], y - _ac[1])


def from_sr(s, r):
    ph = _phc + s / RS
    return _ac[0] + r * np.cos(ph), _ac[1] + r * np.sin(ph)


def defect_d(x, y):
    return np.hypot((x - (CENTRE[0] - WIN[0])) / STRETCH, y - (CENTRE[1] - WIN[1]))


def porthole_d(x, y):
    return np.hypot(x - (PORTHOLE_C[0] - WIN[0]), y - (PORTHOLE_C[1] - WIN[1]))


def wood_steel(base):
    b = base[..., :3]
    sat, lum = b.max(-1) - b.min(-1), b.mean(-1)
    return (sat >= 30) & (lum < 150), (sat < 28) & (lum > 90)


def hermite(s, s0, r0, d0, s1, r1, d1):
    L = s1 - s0
    t = np.clip((s - s0) / L, 0, 1)
    h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
    return h00 * r0 + h10 * L * d0 + h01 * r1 + h11 * L * d1


def measure(st, cu):
    """Belt edge (stock and current) and the two gaps over it, as functions of s."""
    S = np.arange(-340.0, 701.0)
    Rr = np.arange(1000.0, 1211.0)
    SS, RR = np.meshgrid(S, Rr)
    X, Y = from_sr(SS, RR)
    ny = sample(st["normal"][..., 1:2], X.ravel(), Y.ravel(), cubic=False).reshape(SS.shape)

    def belt_of(base, g):
        """Highest steel row with wood right over it, under the first gap (paint and the yellow plate over the belt
        and grey spots in the wood stay out)."""
        bc = sample(base, X.ravel(), Y.ravel(), cubic=False).reshape(SS.shape + (4,))
        wood, steel = wood_steel(bc)
        out = np.full(len(S), np.nan)
        lim = g(S) - 12
        for j in range(len(S)):
            for k in np.where(steel[:, j] & (Rr < lim[j]))[0][::-1]:
                if k + 7 < len(Rr) and wood[k + 1:k + 7, j].mean() > 0.6:
                    out[j] = Rr[k] + 0.5
                    break
        return out

    def track(s0, s1, r_lo, r_hi):
        pts = []
        for s in np.arange(s0, s1 + 1, 2.0):
            j = int(s + 340)
            col = ny[:, j - 1:j + 2].mean(1)
            lo, hi = int(r_lo(s) - 1000), int(r_hi(s) - 1000)
            k = lo + int(np.argmin(col[lo:hi]))
            pts.append((s, Rr[k], col[k]))
        return np.array(pts)

    def robust(pts, deg):
        k = np.ones(len(pts), bool)
        for _ in range(4):
            c = np.polyfit(pts[k, 0], pts[k, 1], deg)
            res = np.abs(pts[:, 1] - np.polyval(c, pts[:, 0]))
            k = res < max(2.5 * np.median(res[k]), 1.5)
        return c, float(np.abs(res[k]).max()), int(k.sum())
    g1l, e1l, n1l = robust(track(-200, -106, lambda s: 1098 + 0.15 * (s + 200) - 8, lambda s: 1098 + 0.15 * (s + 200) + 8), 1)
    g1r, e1r, n1r = robust(track(84, 430, lambda s: 1122 + 0.045 * (s - 90) - 7, lambda s: 1122 + 0.045 * (s - 90) + 7), 2)
    g2l, e2l, n2l = robust(track(-220, -106, lambda s: 1149 + 0.11 * (s + 220) - 7, lambda s: 1149 + 0.11 * (s + 220) + 7), 1)
    t2 = track(56, 430, lambda s: 1166 + 0.045 * (s - 60) - 6, lambda s: 1166 + 0.045 * (s - 60) + 6)
    t2 = t2[(t2[:, 0] < 170) | (t2[:, 0] > 255)]                         # the knot sits on this gap
    g2r, e2r, n2r = robust(t2, 2)

    def curve(cl, cr, anch):
        s0, s1 = anch
        r0, d0 = np.polyval(cl, s0), np.polyval(np.polyder(cl), s0)
        r1, d1 = np.polyval(cr, s1), np.polyval(np.polyder(cr), s1)
        return lambda s: np.where(s <= s0, np.polyval(cl, s), np.where(s >= s1, np.polyval(cr, s), hermite(s, s0, r0, d0, s1, r1, d1)))
    g1, g2 = curve(g1l, g1r, G1_ANCH), curve(g2l, g2r, G2_ANCH)
    belt_s, belt_c = belt_of(st["base_colour"], g1), belt_of(cu["base_colour"], g1)
    ok_s, ok_c = np.isfinite(belt_s), np.isfinite(belt_c)
    def runmed(v, k=10):                    # rivets and paint at the edge: a running median over 21 columns, then a box
        p = np.pad(v, k, mode="edge")
        return np.median(np.lib.stride_tricks.sliding_window_view(p, 2 * k + 1), -1)
    sm_s = box(runmed(np.interp(S, S[ok_s], belt_s[ok_s]))[None], 0, 3)[0]
    sm_c = box(runmed(np.interp(S, S[ok_c], belt_c[ok_c]))[None], 0, 3)[0]
    bs = lambda s: np.interp(s, S, sm_s)
    bc = lambda s: np.interp(s, S, sm_c)
    rep = {"gap1_fit_err_px_left_right": [round(e1l, 2), round(e1r, 2)], "gap1_points": [n1l, n1r],
           "gap2_fit_err_px_left_right": [round(e2l, 2), round(e2r, 2)], "gap2_points": [n2l, n2r],
           "gap1_r_at_s_-112_0_88": [round(float(g1(np.array(v))), 1) for v in (-112.0, 0.0, 88.0)],
           "gap2_r_at_s_-110_0_95": [round(float(g2(np.array(v))), 1) for v in (-110.0, 0.0, 95.0)],
           "belt_cols_stock_current": [int(ok_s.sum()), int(ok_c.sum())]}
    return g1, g2, bs, bc, rep


def q_of(s, r, g1, g2, belt):
    a, b, c = belt(s), g1(s), g2(s)
    return np.where(r < b, (r - b) / np.maximum(b - a, 8), np.where(r < c, (r - b) / np.maximum(c - b, 8), 1 + (r - c) / 45.0))


def r_of(s, q, g1, g2, belt):
    a, b, c = belt(s), g1(s), g2(s)
    return np.where(q < 0, b + q * (b - a), np.where(q < 1, b + q * (c - b), c + (q - 1) * 45.0))


# ---- the rebuild --------------------------------------------------------------------------------------------------
def build():
    st = {k: Dds(stock(k)).read(0, *WIN).astype(np.float32) for k in NAMES}
    cu = {k: Dds(cur_path(k)).read(0, *WIN).astype(np.float32) for k in NAMES}
    H, W = st["base_colour"].shape[:2]
    g1, g2, belt_s, belt_c, rep = measure(st, cu)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    d, dph = defect_d(xx, yy), porthole_d(xx, yy)
    m = np.clip((R + FEATHER - d) / FEATHER, 0, 1) * np.clip((dph - PORTHOLE_KEEP) / 6.0, 0, 1)
    wood_c, steel_c = wood_steel(cu["base_colour"])
    wood_s, steel_s = wood_steel(st["base_colour"])
    s_px, r_px = to_sr(xx, yy)
    q_px = q_of(s_px, r_px, g1, g2, belt_c)
    region = (m > 0) & ~dilate(steel_c, 3) & (q_px > -0.9) & (dph > PORTHOLE_KEEP + 5)
    stock_ok = ~dilate(steel_s, 3) & (d > R + 2) & (dph > PORTHOLE_KEEP + 5)

    # bad source pixels: the port, the porthole ring, bright paint, the knot, steel, outside the clean ranges
    lum = st["base_colour"][..., :3].mean(-1)
    bad = dilate(erode(lum > 150, 3), 6) | dilate(steel_s, 2)
    bad |= (s_px > KNOT_SR[0]) & (s_px < KNOT_SR[1]) & (r_px > KNOT_SR[2]) & (r_px < KNOT_SR[3])

    def src_clean(sx, sy, ss):
        inr = np.zeros(ss.shape, bool)
        for a, b in SRC_RANGES:
            inr |= (ss >= a) & (ss <= b)
        ix, iy = np.clip(np.round(sx).astype(int), 0, W - 1), np.clip(np.round(sy).astype(int), 0, H - 1)
        return inr & (defect_d(sx, sy) > R + FEATHER + 4) & (porthole_d(sx, sy) > PORTHOLE_KEEP + 4) & ~bad[iy, ix]

    def src_xy(s, q, sh):
        s2 = s + sh
        r2 = r_of(s2, q, g1, g2, belt_s)
        x2, y2 = from_sr(s2, r2)
        return x2, y2, s2

    # strips and their sources: one shift per strip (or two, split across the grain where needed)
    edges = (-np.inf,) + STRIPS + (np.inf,)
    cands = list(range(214, 352, 6)) + list(range(-92, -150, -6))
    sel_pts = region
    ys, xs = np.where(sel_pts)
    s_r, q_r = s_px[ys, xs], q_px[ys, xs]
    plan, used = [], []
    for k in range(len(edges) - 1):
        ins = (q_r >= edges[k] - 0.06) & (q_r < edges[k + 1] + 0.06)
        if not ins.any():
            plan.append(None)
            continue
        s_k, q_k = s_r[ins], q_r[ins]
        scores = []
        for sh in cands:
            x2, y2, s2 = src_xy(s_k, q_k, sh)
            ok = src_clean(x2, y2, s2)
            near = min([abs(sh - u) for u in used[-1:]] + [999])
            scores.append((ok.mean(), sh, ok, near))
        full = [t for t in scores if t[0] > 0.998 and t[3] >= 24]
        if full:
            # among clean ones prefer the middle of the range not used by the strip below
            pick = sorted(full, key=lambda t: abs(t[1] - (280 if t[1] > 0 else -125)) + (60 if t[1] in used else 0))[0]
            plan.append({"segs": [(pick[1], -np.inf, np.inf)], "s_range": [float(s_k.min()), float(s_k.max())]})
            used.append(pick[1])
            continue
        # two shifts: the left part of the strip from one, the right part from another, split where both are clean
        best = None
        for fa, sa, oka, _ in scores:
            for fb, sb, okb, _ in scores:
                if sa == sb:
                    continue
                for split in np.arange(s_k.min() + 20, s_k.max() - 20, 4.0):
                    lo, hi = s_k < split + 12, s_k > split - 12
                    if oka[lo].all() and okb[hi].all():
                        sc = abs(split - (s_k.min() + s_k.max()) / 2)
                        if best is None or sc < best[0]:
                            best = (sc, sa, sb, split)
        if best is None:
            info = []
            for f, sh, ok, _ in scores:
                bad_s = s_k[~ok]
                info.append((sh, round(float(f), 3), [round(float(bad_s.min()), 1), round(float(bad_s.max()), 1)] if len(bad_s) else None))
            raise RuntimeError(f"strip {k}: no clean source; s {s_k.min():.0f}..{s_k.max():.0f}; {info}")
        plan.append({"segs": [(best[1], -np.inf, best[3]), (best[2], best[3], np.inf)], "s_range": [float(s_k.min()), float(s_k.max())]})
        used.append(best[2])
    rep["strips"] = [None if p is None else {"shifts": [int(a) for a, _, _ in p["segs"]],
                                             "split_s": [round(float(b), 1) for _, b, _ in p["segs"][1:]], "s_range": [round(v, 1) for v in p["s_range"]]}
                     for p in plan]

    # fill on the unwrapped grid (for the cuts) and at the region's pixels
    def fill_at(s, q, img_names, cut_split=None):
        """Values of the fill at (s, q): strip weights (1.5 px feather along the grain), segments by s."""
        res = {k: np.zeros(s.shape + (4,), np.float32) for k in img_names}
        wsum = np.zeros(s.shape, np.float32)
        band = 1.5 / 40.0
        for k, p in enumerate(plan):
            if p is None:
                continue
            w = np.clip((q - edges[k]) / band + 0.5, 0, 1) * np.clip((edges[k + 1] - q) / band + 0.5, 0, 1)
            if not (w > 0).any():
                continue
            for si, (sh, a, b) in enumerate(p["segs"]):
                if len(p["segs"]) > 1:
                    sp = cut_split[k](q) if cut_split is not None else p["segs"][1][1]
                    ws = np.clip((s - sp) / 1.5 + 0.5, 0, 1)
                    ws = 1 - ws if si == 0 else ws
                else:
                    ws = 1.0
                ww = w * ws
                sel = ww > 0
                if not sel.any():
                    continue
                x2, y2, _ = src_xy(s[sel], q[sel], sh)
                for nm in img_names:
                    res[nm][sel] += ww[sel, None] * sample(st[nm], x2, y2)
                wsum[sel] += ww[sel]
        for nm in img_names:
            res[nm] /= np.maximum(wsum, 1e-6)[..., None]
        return res

    def feat(vals):
        """What the cut compares: brightness of the base colour and the normal's slopes."""
        return np.stack([vals["base_colour"][..., :3].mean(-1), vals["normal"][..., 1], vals["normal"][..., 3]], -1)

    # cut positions: per row of r on the unwrapped grid, left and right of the port, and inside split strips
    Sg = np.arange(-170.0, 171.0)
    Rg = np.arange(1040.0, 1215.0)
    SG, RG = np.meshgrid(Sg, Rg)
    XG, YG = from_sr(SG, RG)
    QG = q_of(SG, RG, g1, g2, belt_c)
    dG, phG = defect_d(XG, YG), porthole_d(XG, YG)
    regG = sample(region[..., None].astype(np.float32), XG.ravel(), YG.ravel(), cubic=False).reshape(SG.shape) > 0.5
    okG = sample(stock_ok[..., None].astype(np.float32), XG.ravel(), YG.ravel(), cubic=False).reshape(SG.shape) > 0.99
    FG = fill_at(SG, QG, ("base_colour", "normal"))
    SGv = {k: sample(st[k], XG.ravel(), YG.ravel()).reshape(SG.shape + (4,)) for k in ("base_colour", "normal")}
    diff = np.abs(feat(FG) - feat(SGv)) @ np.array([1.0, 0.6, 0.6])
    cost = box(diff, 2, 3)

    def dp(costm, allowed, lam=2.0, step=2):
        """Min-cost path, one column per row, |change| <= step per row; rows without allowed cells are skipped."""
        n, w = costm.shape
        c = np.where(allowed, costm, np.inf)
        acc = c.copy()
        back = np.zeros((n, w), int)
        rows = [i for i in range(n) if allowed[i].any()]
        prev = None
        for i in rows:
            if prev is not None:
                best = np.full(w, np.inf)
                arg = np.zeros(w, int)
                for dd in range(-step, step + 1):
                    sh = np.roll(acc[prev], dd) + lam * abs(dd)
                    if dd > 0:
                        sh[:dd] = np.inf
                    elif dd < 0:
                        sh[dd:] = np.inf
                    better = sh < best
                    best[better], arg[better] = sh[better], (np.arange(w) - dd)[better]
                if np.isfinite(best[allowed[i]]).any():
                    acc[i] = c[i] + best
                    back[i] = arg
                else:
                    back[i] = -1
            prev = i
        path = {}
        j = int(np.argmin(acc[rows[-1]]))
        for n_i in range(len(rows) - 1, -1, -1):
            i = rows[n_i]
            path[i] = j
            if n_i == 0:
                break
            b = back[i, j]
            j = int(np.argmin(acc[rows[n_i - 1]])) if b < 0 or not np.isfinite(acc[i, j]) else int(b)
        return path

    # left and right cuts: inside the outer feather ring, where the stock is clean
    ring = (dG > R + 3) & (dG < R + FEATHER - 1) & okG & (phG > PORTHOLE_KEEP + 6)
    cuts = {}
    for side in (-1, 1):
        allowed = ring & (np.sign(SG) == side)
        path = dp(cost, allowed)
        cuts[side] = {Rg[i]: Sg[j] for i, j in path.items()}
    # rows without a cut (no ring there): the fill ends where the region ends
    rows_l = np.array(sorted(cuts[-1])), np.array(sorted(cuts[1]))
    cL = lambda r: np.interp(r, rows_l[0], [cuts[-1][v] for v in rows_l[0]])
    cR = lambda r: np.interp(r, rows_l[1], [cuts[1][v] for v in rows_l[1]])
    # splits inside two-shift strips: also cut where the two sources agree
    split_fn = {}
    for k, p in enumerate(plan):
        if p is None or len(p["segs"]) == 1:
            continue
        (sa, _, sp), (sb, _, _) = p["segs"]
        inside = (QG >= edges[k] - 0.1) & (QG < edges[k + 1] + 0.1)
        xa, ya, _ = src_xy(SG, QG, sa)
        xb, yb, _ = src_xy(SG, QG, sb)
        va = {nm: sample(st[nm], xa.ravel(), ya.ravel()).reshape(SG.shape + (4,)) for nm in ("base_colour", "normal")}
        vb = {nm: sample(st[nm], xb.ravel(), yb.ravel()).reshape(SG.shape + (4,)) for nm in ("base_colour", "normal")}
        cst = box(np.abs(feat(va) - feat(vb)) @ np.array([1.0, 0.6, 0.6]), 2, 3)
        allowed = inside & (np.abs(SG - sp) < 12)
        path = dp(cst, allowed)
        qs = np.array([QG[i, j] for i, j in sorted(path.items())])
        ss = np.array([Sg[j] for i, j in sorted(path.items())])
        o = np.argsort(qs)
        split_fn[k] = (lambda qq, qs=qs[o], ss=ss[o]: np.interp(qq, qs, ss))
    rep["cut_rows_left_right"] = [len(cuts[-1]), len(cuts[1])]

    # compose at the pixels
    sel = dilate(region, 1)
    ys, xs = np.where(sel)
    s_k, r_k, q_k = s_px[ys, xs], r_px[ys, xs], q_px[ys, xs]
    F = fill_at(s_k, q_k, NAMES, cut_split=split_fn)
    c_in = np.clip(np.minimum(s_k - cL(r_k), cR(r_k) - s_k) / 1.5 + 0.5, 0, 1)
    c_in = np.where(stock_ok[ys, xs] & wood_s[ys, xs], c_in, 1.0)          # no usable stock: fill
    Wsoft = box(region.astype(np.float32), 1, 1)[ys, xs]
    for nm in NAMES:
        out = cu[nm].copy()
        inner = st[nm][ys, xs] * (1 - c_in[:, None]) + F[nm] * c_in[:, None]
        out[ys, xs] = cu[nm][ys, xs] * (1 - Wsoft[:, None]) + inner * Wsoft[:, None]
        OUT[nm] = np.clip(out, 0, 255)
    STATE.update(region=region, m=m, cu=cu, st=st)
    rep["pixels_rebuilt"] = int((Wsoft > 0).sum())
    return rep


# ---- output -------------------------------------------------------------------------------------------------------
_CACHE = {}


def push_live(names=NAMES, prefix="new_"):
    """Writes OUT into the live images (atlas y -> Blender row 4095 - y) and refreshes them."""
    import bpy
    x0, y0, x1, y1 = WIN
    for nm in names:
        img = bpy.data.images[prefix + nm]
        w, h = img.size
        if nm not in _CACHE:
            px = np.empty(w * h * 4, np.float32)
            img.pixels.foreach_get(px)
            _CACHE[nm] = px.reshape(h, w, 4)
        px = _CACHE[nm]
        px[h - y1:h - y0, x0:x1] = OUT[nm][::-1] / 255.0
        img.pixels.foreach_set(px.ravel())
        img.update()


def save_dds():
    """Level 0 and the mips of BOX, only blocks the region touched (others keep their bytes)."""
    rep = {}
    bx0, by0 = BOX[0] - WIN[0], BOX[1] - WIN[1]
    bw, bh = BOX[2] - BOX[0], BOX[3] - BOX[1]
    for nm in NAMES:
        diff = np.abs(OUT[nm] - STATE["cu"][nm]).max(-1) > 0.5
        dds = Dds(cur_path(nm))
        cur = OUT[nm][by0:by0 + bh, bx0:bx0 + bw]
        mk = diff[by0:by0 + bh, bx0:bx0 + bw].astype(np.float32)
        assert not diff.sum() - mk.sum(), "change outside the box"
        levels = 0
        for level in range(dds.mips):
            s = 1 << level
            w_, h_ = bw // s, bh // s
            if w_ < 4 or h_ < 4 or w_ % 4 or h_ % 4:
                break
            if level:
                cur = cur.reshape(h_, 2, w_, 2, 4).mean((1, 3))
                mk = mk.reshape(h_, 2, w_, 2).max((1, 3))
            only = mk.reshape(h_ // 4, 4, w_ // 4, 4).max((1, 3)) > 0
            dds.write(level, BOX[0] // s, BOX[1] // s, np.clip(np.round(cur), 0, 255).astype(np.uint8), only=only)
            levels += 1
        dds.save(cur_path(nm))
        rep[nm] = {"levels": levels, "changed_px": int(diff.sum())}
    return rep
