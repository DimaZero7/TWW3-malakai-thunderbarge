"""Wood over the removed bow porthole (numpy only: runs in the live Blender through MCP or in the project venv).

The porthole's steel ring is painted on the hull's plank atlas: a disc of radius 50.3 px around (1027.9, 3639.3) with a
2-4 px dark outline. Its planks are concentric arcs around AC (as for the closed gun port, blender_skill_plank2), so the
atlas is read in (s, r): r the distance from AC, s the arc length from the porthole's angle (px at the porthole's r).

  * gaps: every plank gap crossing the disc is measured on the stock left and right of it (minimum of the normal map's G,
    per column), fitted per side, and joined inside by a Hermite curve meeting both sides in place and slope;
  * plank coordinate q: integer on each gap, linear between them, so a source pixel at the same q sits at the same place
    in its plank;
  * the wood inside is cut into strips along the grain (borders between the gaps), each strip copies one stretch of clean
    stock wood at the same q from left or right of the porthole (one source per pixel, bicubic, no averaging);
  * the fill meets the surrounding atlas on a cut running across the strips where they agree best (dynamic programming
    per row of r), feathered over 1.5 px. Pixels the closed port patch rebuilt are never touched.
Base colour, normal and material map take the same source pixels.

The figurehead's eye (+x side, all LODs) reads the middle of the porthole disc. EYE_SRC is copied to EYE_DST (a free spot
of the atlas, no triangle reads it) and the eye's UVs move by the same offset, so it keeps its look.

  import blender_skill_porthole_tex as pt; rep = pt.build()   -> pt.OUT holds the new windows
  pt.push_live()                                               writes them into the scene's images (new_*)
  pt.save_dds()                                                level 0 and the mips of BOX and of EYE_DST
"""
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from blender_dds import Dds  # noqa: E402
from blender_skill_plank2 import box, dilate, erode, hermite, sample, wood_steel  # noqa: E402

GAME = REPO / "build" / "solid_hull" / "game"
ACC = REPO / "build" / "keep" / "hull_port_closed_v1" / "warmachines" / "tex"
TEX = REPO / "build" / "solid_hull_porthole" / "tex"
NAMES = ("base_colour", "normal", "material_map")
WIN = (640, 3328, 1664, 4096)              # read window (sources)
BOX = (896, 3456, 1152, 3712)              # rewritten box at level 0 (128-aligned)
AC = (1268.2, 4852.0)                      # centre of the plank arcs (atlas)
PC, PR = (1027.9, 3639.3), 50.3            # porthole ring on the atlas: centre, outer radius (circle fit, residual 0.3 px)
ZONE = 57.0                                # repainted out to here: ring 50.3, outline to ~55, normal bevel
CUT_EXTRA = 20.0                           # the joints lie this far past the zone's widest chord in each strip
CUT_OUT = 100.0                             # the cut to the surrounding atlas lies between ZONE and this (past the dark halo)
EYE_SRC = (992, 3608, 1056, 3672)          # the figurehead eye's UVs lie in (1010..1042, 3630..3654)
EYE_DST = (1280, 2624)                     # free 64 x 64 (16 px free margin) in the grey padding band
OUT = {}
DEBUG = {}
STATE = {}


def stock(name):
    return GAME / f"dwf_thunderbarge_grungni_01_{name}.dds"


def acc(name):
    return ACC / f"tww3_mtb_dwf_thunderbarge_grungni_01_{name}.dds"


def cur_path(name):
    return TEX / f"tww3_mtb_dwf_thunderbarge_grungni_01_{name}.dds"


# ---- (s, r) frame -------------------------------------------------------------------------------------------------
_ac = np.array((AC[0] - WIN[0], AC[1] - WIN[1]))
_pc = np.array((PC[0] - WIN[0], PC[1] - WIN[1]))
RS = float(np.hypot(*(_pc - _ac)))         # 1236.3: s in px at the porthole's radius
R0 = RS
_ph0 = math.atan2(_pc[1] - _ac[1], _pc[0] - _ac[0])


def to_sr(x, y):
    return (np.arctan2(y - _ac[1], x - _ac[0]) - _ph0) * RS, np.hypot(x - _ac[0], y - _ac[1])


def from_sr(s, r):
    ph = _ph0 + s / RS
    return _ac[0] + r * np.cos(ph), _ac[1] + r * np.sin(ph)


def ring_d(x, y):
    return np.hypot(x - _pc[0], y - _pc[1])


def half_chord(r, rad):
    """Half width in s of the circle of radius rad around the porthole at radius r (0 where it does not reach)."""
    d = np.abs(np.asarray(r, float) - R0)
    return np.sqrt(np.clip(rad * rad - d * d, 0, None))


# ---- measuring the gaps -------------------------------------------------------------------------------------------
GAPS0 = (1122.0, 1167.0, 1210.0, 1252.0, 1292.5)   # rough radii of the gaps (unwrap): the plank over the steel belt, the gap under the disc,
                                                   # two gaps across it, the top one running intact just over the ring
SIDE = (60.0, 200.0)                       # |s| range where each side is measured (farther out the gaps bend away)
GAP_MODE = ("bevel", "bevel", "bevel", "bevel", "dark")      # the top gap has its bright edge above, not below: darkest row there
GAP_WIN = (8, 6, 6, 6, 3)
LOW = 1                                    # index of the gap under the disc (kept stock); q counts gaps from GAPS0[0]
GAP_SIDE = ((110.0, 210.0), SIDE, SIDE, SIDE, (0.0, 120.0))     # the lowest one only clear of the closed port
GAP_SIDE_SRC = ((110.0, 250.0),) + ((60.0, 250.0),) * 3 + ((0.0, 210.0),)    # wider fits for the sources only (the gaps bend a little out there)
TRUST = 62.0                               # inside |s| < half chord of this radius the stock is not trusted


def robust(pts, deg):
    k = np.ones(len(pts), bool)
    for _ in range(4):
        c = np.polyfit(pts[k, 0], pts[k, 1], deg)
        res = np.abs(pts[:, 1] - np.polyval(c, pts[:, 0]))
        k = res < max(2.5 * np.median(res[k]), 1.5)
    return c, float(res[k].max()), int(k.sum())


def runmed(v, k):
    p = np.pad(v, k, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(p, 2 * k + 1), -1)


R_LO = 1090.0
GAP_LUM = 175.0                            # a column with brighter base colour near the gap is paint, not wood


def track(st, excl=(), deg=2, sides=None):
    """Each gap per side. On the base colour a gap is a thin dark line with the plank's bright bevel 2 px below it
    (towards smaller r); per column (3 columns averaged) the row maximising lum(r - 2) - lum(r) within +-6 px of the
    rough radius, sub-pixel by a parabola through the dark minimum. Then a robust polynomial in s per side.
    Returns [{side: (coeffs, s points, r points, max residual of kept points, kept count)}] in GAPS0 order."""
    S = np.arange(-SIDE[1] - 4, SIDE[1] + 5.0)
    Rr = np.arange(R_LO, 1320.0)
    SS, RR = np.meshgrid(S, Rr)
    X, Y = from_sr(SS, RR)
    lum = sample(st["base_colour"], X.ravel(), Y.ravel(), cubic=False).reshape(SS.shape + (4,))[..., :3].mean(-1)
    lum3 = (lum[:, :-2] + lum[:, 1:-1] + lum[:, 2:]) / 3
    S3 = S[1:-1]
    out = []
    for g0, mode, win, side_rng in zip(GAPS0, GAP_MODE, GAP_WIN, sides or GAP_SIDE):
        sides = {}
        for side in (-1, 1):
            pts = []
            for j in range(len(S3)):
                s = S3[j]
                if not (side_rng[0] <= side * s <= side_rng[1]) or abs(s) < half_chord(g0, TRUST) + 2 or any(a <= s <= b for a, b in excl):
                    continue
                k0 = int(g0 - R_LO)
                if lum3[k0 - 10:k0 + 11, j].max() > GAP_LUM:
                    continue
                ks = np.arange(k0 - win, k0 + win + 1)
                sc = lum3[ks - 2, j] - lum3[ks, j] if mode == "bevel" else -lum3[ks, j]
                k = int(ks[np.argmax(sc)])
                a, b, c = lum3[k - 1, j], lum3[k, j], lum3[k + 1, j]
                off = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) > 1e-6 else 0.0
                pts.append((s, Rr[k] + float(np.clip(off, -0.5, 0.5))))
            pts = np.array(pts)
            c, err, n = robust(pts, deg)
            sides[side] = (c, pts[:, 0], pts[:, 1], err, n)
        out.append(sides)
    return out


# ---- the rebuild --------------------------------------------------------------------------------------------------
TOP_KEEP = 1290.5                          # r above which the stock stays: the top gap runs intact just over the ring
STRIPS = (1.55, 2.5, 3.45)                 # strip borders in q (gaps at 1, 2, 3, 4 stay inside strips)
PLANK_W = 41.5                             # plank width beyond the outer gaps (px)
SRC_ABS = (62.0, 195.0)                    # |s| of clean stock wood (where the source gap fits hold)
BAD_SR = ((-82.0, -64.0, 1182.0, 1198.0),   # knot under the porthole's left       (s0, s1, r0, r1): never a source
          (-118.0, -88.0, 1193.0, 1222.0),  # diagonal scratch over the lower gap
          (-145.0, -133.0, 1164.0, 1174.0), # dark speck on the gap under the disc
          (184.0, 196.0, 1213.0, 1225.0),   # reddish spot right of the porthole (a 3 px speck at (-150, 1234) is left in)
          (183.0, 240.0, 1150.0, 1178.0),   # dark splinter on the gap under the disc, right
          (200.0, 226.0, 1112.0, 1142.0))   # light splinter over the belt plank, right
PORT_C, PORT_R, PORT_STRETCH = (1052.0, 3787.0), 94.0, 1.1     # the closed gun port (blender_skill_plank2): never a source
SHIFTS = [(d, 0) for d in tuple(range(90, 301, 3)) + tuple(range(-90, -301, -3))] +          [(d, m) for m in (-3, -2, -1, 1, 2, 3) for d in tuple(range(60, 301, 3)) + tuple(range(-60, -301, -3))]
# a source is (shift along the planks, planks up or down): the same place in another plank is wood of the same make;
# >= 90 px along the same plank, >= 60 px in another one, so no copy sits next to its source
SPLIT_W = 12.0                             # neighbouring pieces of a strip overlap this far around their bound (the cut between them goes there)
STRIP_ORDER = (1, 2, 0, 3)
TONE_GAIN = True                           # one brightness factor per piece (base colour only) to meet the wood around
GAIN_MAX = 1.25
NPIECE = 2                                 # pieces per strip
BRANCH = 30                                 # choices per strip tried in the search over strips
TOPN = 40                                  # candidates kept per piece for the joint choice
FAR_PEN = 4.0                              # an outer piece from the other side of the porthole
REUSE_DS_NEXT = 90.0                      # (the plank sheet left of the porthole is spoilt by a knot and a scratch: not enough clean wood otherwise)
REUSE_DS = 60.0                            # px along the planks between two copies of the same wood in strips one apart
FP_GAP = 8.0                               # px: source footprints of different pieces stay this far apart along the planks
PROFILE_BIN = 12.0                         # tone profile of a piece: medians over bins this long
STEP_W = 2.0                               # weight of the tone step where the two pieces meet
LOW_KEEP = 3.0                             # the gap under the disc stays stock: the fill starts this far over it


def gap_fns(tr, tr_src):
    """Target gap curves (Hermite across the disc) and source gap curves (side fits) for each gap."""
    tgt, src = [], []
    for gi, sides in enumerate(tr):
        cl, cr = sides[-1][0], sides[1][0]
        h = max(float(half_chord(GAPS0[gi], TRUST)), 20.0)
        r0, d0 = np.polyval(cl, -h), np.polyval(np.polyder(cl), -h)
        r1, d1 = np.polyval(cr, h), np.polyval(np.polyder(cr), h)
        tgt.append(lambda s, cl=cl, cr=cr, h=h, r0=r0, d0=d0, r1=r1, d1=d1: np.where(
            s <= -h, np.polyval(cl, s), np.where(s >= h, np.polyval(cr, s), hermite(s, -h, r0, d0, h, r1, d1))))
        # sources: the measured columns themselves (outliers off a cubic dropped, running median of 7), so the gaps
        # bending far out from the porthole are followed where a polynomial would miss them by 1.5 px
        fn = {}
        for side in (-1, 1):
            ss, rr_ = tr_src[gi][side][1], tr_src[gi][side][2]
            c3 = np.polyfit(ss, rr_, 3)
            keep = np.abs(rr_ - np.polyval(c3, ss)) < 2.0
            o = np.argsort(ss[keep])
            fn[side] = (ss[keep][o], runmed(rr_[keep][o], 3))
        src.append(lambda s, fl=fn[-1], fr=fn[1]: np.where(s < 0, np.interp(s, *fl), np.interp(s, *fr)))
    return tgt, src


def q_of(s, r, G):
    g = [f(s) for f in G]
    q = np.where(r < g[0], (r - g[0]) / PLANK_W, 0.0)
    for i in range(len(g) - 1):
        q = np.where((r >= g[i]) & (r < g[i + 1]), i + (r - g[i]) / np.maximum(g[i + 1] - g[i], 8.0), q)
    return np.where(r >= g[-1], len(g) - 1 + (r - g[-1]) / PLANK_W, q)


def r_of(s, q, G):
    g = [f(s) for f in G]
    n = len(g)
    r = np.where(q < 0, g[0] + q * PLANK_W, g[-1] + (q - (n - 1)) * PLANK_W)
    for i in range(n - 1):
        r = np.where((q >= i) & (q < i + 1), g[i] + (q - i) * (g[i + 1] - g[i]), r)
    return r


def _rot_normal(v, ang):
    """Normal map pixels (G = y, A = x, both 0..255, y pointing down the atlas: measured on the stock gap bevels, which
    face the arc centre's radial direction with a constant offset only in this convention) turned by ang (radians)."""
    nx, ny = (v[..., 3] - 127.5) / 127.5, (v[..., 1] - 127.5) / 127.5
    c, s = np.cos(ang), np.sin(ang)
    out = v.copy()
    out[..., 3] = (c * nx - s * ny) * 127.5 + 127.5
    out[..., 1] = (s * nx + c * ny) * 127.5 + 127.5
    return out


def _dp(costm, allowed, lam=2.0, step=2):
    """Min-cost path, one column per row, |change| <= step per row (blender_skill_plank2)."""
    n, w = costm.shape
    c = np.where(allowed, costm, np.inf)
    acc_ = c.copy()
    back = np.zeros((n, w), int)
    rows = [i for i in range(n) if allowed[i].any()]
    prev = None
    for i in rows:
        if prev is not None:
            best = np.full(w, np.inf)
            arg = np.zeros(w, int)
            for dd in range(-step, step + 1):
                sh = np.roll(acc_[prev], dd) + lam * abs(dd)
                if dd > 0:
                    sh[:dd] = np.inf
                elif dd < 0:
                    sh[dd:] = np.inf
                better = sh < best
                best[better], arg[better] = sh[better], (np.arange(w) - dd)[better]
            if np.isfinite(best[allowed[i]]).any():
                acc_[i] = c[i] + best
                back[i] = arg
            else:
                back[i] = -1
        prev = i
    path = {}
    j = int(np.argmin(acc_[rows[-1]]))
    for n_i in range(len(rows) - 1, -1, -1):
        i = rows[n_i]
        path[i] = j
        if n_i == 0:
            break
        b = back[i, j]
        j = int(np.argmin(acc_[rows[n_i - 1]])) if b < 0 or not np.isfinite(acc_[i, j]) else int(b)
    return path


def _feat(vals):
    return np.stack([vals["base_colour"][..., :3].mean(-1), vals["normal"][..., 1], vals["normal"][..., 3]], -1)


def build():
    st = {k: Dds(stock(k)).read(0, *WIN).astype(np.float32) for k in NAMES}
    ac = {k: Dds(acc(k)).read(0, *WIN).astype(np.float32) for k in NAMES}
    H, W = st["base_colour"].shape[:2]
    tr = track(st)
    tr_src = track(st, sides=GAP_SIDE_SRC)
    G, GS = gap_fns(tr, tr_src)
    rep = {"gaps": {}}
    for i, g0 in enumerate(GAPS0):
        h = float(half_chord(g0, TRUST))
        rep["gaps"][str(g0)] = {"r_left_edge": round(float(GS[i](np.array(-h - 1e-3))), 2), "r_right_edge": round(float(GS[i](np.array(h + 1e-3))), 2),
                                "fit_err_px_left_right": [round(tr[i][-1][3], 2), round(tr[i][1][3], 2)],
                                "points_left_right": [tr[i][-1][4], tr[i][1][4]], "r_at_s0": round(float(G[i](np.array(0.0))), 2)}
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    s_px, r_px = to_sr(xx, yy)
    dph = ring_d(xx, yy)
    acc_changed = np.zeros((H, W), bool)
    for nm in NAMES:
        acc_changed |= np.abs(ac[nm] - st[nm]).max(-1) > 2
    acc_changed = dilate(acc_changed, 1)
    g_lo, g_hi = G[LOW](s_px) + LOW_KEEP, np.minimum(G[-1](s_px) - 2.0, TOP_KEEP)
    # boards, not a disc: each strip along the grain is filled out to a cross-grain joint a little past the porthole
    # (its widest chord of the zone), each strip to its own joint, as a carpenter would set in board pieces
    edges = (-np.inf,) + STRIPS + (np.inf,)
    q_px = q_of(s_px, r_px, G)
    strip_of = np.digitize(q_px, STRIPS)
    rr0 = np.arange(R0 - ZONE - 2, R0 + ZONE + 3, 0.5)
    q0 = q_of(np.zeros_like(rr0), rr0, G)
    lo0, hi0 = G[LOW](np.array(0.0)) + LOW_KEEP, min(float(G[-1](np.array(0.0))) - 2.0, TOP_KEEP)
    chord = np.array([float(half_chord(rr0[(np.digitize(q0, STRIPS) == k) & (rr0 > lo0) & (rr0 < hi0)], ZONE + 1).max(initial=0.0))
                      for k in range(len(edges) - 1)])
    reach = chord[strip_of] + CUT_EXTRA + 2
    region = (np.abs(s_px) < reach) & (r_px > g_lo - 1) & (r_px < g_hi + 1) & ~acc_changed
    rep["joint_from_s"] = [round(float(c), 1) for c in chord]

    # bad source pixels: the ring and its halo, the closed port, paint, steel, unique marks
    lum = st["base_colour"][..., :3].mean(-1)
    _, steel = wood_steel(st["base_colour"])
    bad = dilate(erode(lum > 150, 2), 5) | dilate(steel, 2) | (dph < ZONE + 10)     # thin bright bevels are wood, not paint; the halo is wood (tone decides)
    bad |= np.hypot((xx + WIN[0] - PORT_C[0]) / PORT_STRETCH, yy + WIN[1] - PORT_C[1]) < PORT_R + 16 + 6
    for a, b, c, d in BAD_SR:
        bad |= (s_px > a) & (s_px < b) & (r_px > c) & (r_px < d)
    alum = ac["base_colour"][..., :3].mean(-1)

    def src_xy(s, q, sh):
        s2 = s + sh[0]
        x2, y2 = from_sr(s2, r_of(s2, q + sh[1], GS))
        return x2, y2, s2

    def src_clean(x2, y2, s2):
        ix, iy = np.clip(np.round(x2).astype(int), 0, W - 1), np.clip(np.round(y2).astype(int), 0, H - 1)
        return (np.abs(s2) >= SRC_ABS[0]) & (np.abs(s2) <= SRC_ABS[1]) & ~bad[iy, ix]

    def src_lum(x2, y2):
        ix, iy = np.clip(np.round(x2).astype(int), 0, W - 1), np.clip(np.round(y2).astype(int), 0, H - 1)
        return lum[iy, ix]

    # strips along the grain, each in NPIECE pieces split across the grain; a piece copies one stretch of clean stock
    # wood. The pieces of a strip are chosen together: the tone along each follows the surrounding wood of the strip
    # (its left tone at the left end, its right tone at the right end, linear between) and neighbours meet with little
    # tone step. No source pixel goes in twice (no repeats), over all strips: a search over the strips' best choices.
    # The dark halo around the porthole is replaced, not copied; no tone is pulled or blended.
    ys, xs = np.where(region)
    s_r, q_r = s_px[ys, xs], q_px[ys, xs]
    plan = [None] * (len(edges) - 1)

    def overlap(f, g):
        """Footprints (q0, q1, s0, s1, strip, target s shift) that would show the same wood twice. The same wood may go into
        two strips when the two copies sit far apart along the planks: REUSE_DS, or REUSE_DS_NEXT for neighbouring strips."""
        if not (min(f[1], g[1]) - max(f[0], g[0]) > 0.15 and f[2] < g[3] + FP_GAP and g[2] < f[3] + FP_GAP):
            return False                     # (q margins of strips may touch)
        if f[4] == g[4]:
            return True
        return abs(f[5] - g[5]) < (REUSE_DS if abs(f[4] - g[4]) >= 2 else REUSE_DS_NEXT)

    info = {}
    for k in range(len(edges) - 1):
        ins = (q_r >= edges[k] - 0.06) & (q_r < edges[k + 1] + 0.06)
        if not ins.any():
            continue
        s_k, q_k = s_r[ins], q_r[ins]
        a_, b_ = float(s_k.min()), float(s_k.max())
        tone = {}
        for side in (-1, 1):
            m = (np.abs(s_px) > chord[k] + CUT_EXTRA) & (np.abs(s_px) < chord[k] + CUT_EXTRA + 25) & (np.sign(s_px) == side) & (q_px >= max(edges[k], LOW - 0.2)) & (q_px < min(edges[k + 1], len(GAPS0) - 0.8)) & ~acc_changed
            tone[side] = float(np.median(alum[m]))
        bounds = np.linspace(a_, b_, NPIECE + 1)
        pieces = []
        for i in range(NPIECE):
            lo_s = bounds[i] - (0 if i == 0 else SPLIT_W)
            hi_s = bounds[i + 1] + (0 if i == NPIECE - 1 else SPLIT_W)
            sel = (s_k >= lo_s) & (s_k <= hi_s)
            bins = np.arange(lo_s, hi_s + 1e-6, PROFILE_BIN)
            bi = np.clip(np.digitize(s_k[sel], bins) - 1, 0, len(bins) - 2)
            centres = 0.5 * (bins[:-1] + bins[1:])
            want = tone[-1] + (tone[1] - tone[-1]) * np.clip((centres - a_) / max(b_ - a_, 1.0), 0, 1)
            mid = 0.5 * (bounds[i] + bounds[i + 1])
            cands = []
            for sh in SHIFTS:
                if (q_k[sel] + sh[1]).min() < 0.0 or (q_k[sel] + sh[1]).max() > len(GAPS0) - 1.0:
                    continue                     # only between measured gaps
                x2, y2, s2 = src_xy(s_k[sel], q_k[sel], sh)
                if src_clean(x2, y2, s2).mean() < 0.998:
                    continue
                if (q_k[sel] + sh[1]).min() < LOW and np.abs(s2).min() < GAP_SIDE_SRC[0][0]:
                    continue                     # the lowest gap is measured only clear of the closed port
                fp_ = (float((q_k[sel] + sh[1]).min()), float((q_k[sel] + sh[1]).max()), float(s2.min()), float(s2.max()), k, sh[0])
                lv_ = src_lum(x2, y2)
                prof = np.array([np.median(lv_[bi == j]) if (bi == j).any() else np.nan for j in range(len(centres))])
                ok = np.isfinite(prof)
                far = FAR_PEN if (abs(mid) > 30 and np.sign(sh[0]) != np.sign(mid)) else 0.0
                # the piece's overall tone counts most (a patch reads by its mean), its run along the plank less
                err = abs(float(np.mean(lv_)) - float(np.mean(want))) + 0.3 * float(np.mean(np.abs(prof[ok] - want[ok])))
                cands.append((err + far, sh, prof[ok], fp_, float(np.mean(lv_)), float(np.mean(want))))
            if not cands:
                raise RuntimeError(f"strip {k} piece {i}: no clean source for s {lo_s:.0f}..{hi_s:.0f}")
            # keep variety: the best candidate per plank, side and 20 px of source position, then the best TOPN of those
            buck = {}
            for c in sorted(cands, key=lambda t: t[0]):
                buck.setdefault((c[1][1], np.sign(c[1][0]), int(c[3][2] // 20)), c)
            pieces.append(sorted(buck.values(), key=lambda t: t[0])[:TOPN])
        info[k] = dict(a=a_, b=b_, tone=tone, bounds=bounds, pieces=pieces)

    def combos(k, used, n_best):
        """The strip's n_best choices of pieces (score, pieces), none overlapping used footprints or each other."""
        pieces, found = info[k]["pieces"], []

        def walk(i, chosen, score):
            if len(found) >= n_best and score >= found[-1][0]:
                return
            if i == NPIECE:
                found.append((score, list(chosen)))
                found.sort(key=lambda t: t[0])
                del found[n_best:]
                return
            for c in pieces[i]:
                if any(overlap(c[3], g) for g in used) or any(c[1] == d[1] or overlap(c[3], d[3]) for d in chosen):
                    continue                     # one source pixel never goes in twice
                step = abs(chosen[-1][2][-2:].mean() - c[2][:2].mean()) if chosen else 0.0
                chosen.append(c)
                walk(i + 1, chosen, score + c[0] + STEP_W * step)
                chosen.pop()
        walk(0, [], 0.0)
        return found

    STATE.update(info=info, combos=combos)
    order = [k for k in STRIP_ORDER if k in info]
    best = [None]

    def search(j, used, total, picked):
        if best[0] is not None and total >= best[0][0]:
            return
        if j == len(order):
            best[0] = (total, dict(picked))
            return
        k = order[j]
        for sc, ch in combos(k, used, BRANCH):
            picked[k] = ch
            search(j + 1, used + [c[3] for c in ch], total + sc, picked)
            del picked[k]
    search(0, [], 0.0, {})
    if best[0] is None:
        raise RuntimeError("no choice of sources for all strips without a repeat")
    for k, ch in best[0][1].items():
        I = info[k]
        steps = [round(float(abs(ch[i][2][-2:].mean() - ch[i + 1][2][:2].mean())), 1) for i in range(NPIECE - 1)]
        gains = [float(np.clip(c[5] / c[4], 1 / GAIN_MAX, GAIN_MAX)) if TONE_GAIN else 1.0 for c in ch]
        segs = [(c[1], float(I["bounds"][i]), float(I["bounds"][i + 1]), gains[i], round(c[0], 1)) for i, c in enumerate(ch)]
        plan[k] = {"segs": segs, "s_range": [I["a"], I["b"]], "tone_left_right": [round(I["tone"][-1], 1), round(I["tone"][1], 1)], "steps": steps}
    rep["strips"] = [None if p is None else {"sources": [list(t[0]) for t in p["segs"]], "bounds": [round(t[1], 1) for t in p["segs"]] + [round(p["s_range"][1], 1)],
                                             "tone_left_right": p["tone_left_right"], "profile_err": [t[4] for t in p["segs"]],
                                             "tone_steps": p["steps"], "gains": [round(t[3], 3) for t in p["segs"]]} for p in plan]

    def fill_at(s, q, img_names, splits=None):
        """Fill at (s, q): strips by q (1.5 px feather along the grain), segments by s (1.5 px), normals turned with the arc."""
        res = {k: np.zeros(s.shape + (4,), np.float32) for k in img_names}
        wsum = np.zeros(s.shape, np.float32)
        band = 1.5 / PLANK_W
        for k, p in enumerate(plan):
            if p is None:
                continue
            w = np.clip((q - edges[k]) / band + 0.5, 0, 1) * np.clip((edges[k + 1] - q) / band + 0.5, 0, 1)
            if not (w > 0).any():
                continue
            n = len(p["segs"])
            for si, (sh, a, b, gain, _) in enumerate(p["segs"]):
                lo = -np.inf if si == 0 else (splits[(k, si)](q) if splits and (k, si) in splits else a)
                hi = np.inf if si == n - 1 else (splits[(k, si + 1)](q) if splits and (k, si + 1) in splits else b)
                ws = np.clip((s - lo) / 1.5 + 0.5, 0, 1) * np.clip((hi - s) / 1.5 + 0.5, 0, 1)
                ww = w * ws
                sel = ww > 0
                if not np.any(sel):
                    continue
                x2, y2, _ = src_xy(s[sel], q[sel], sh)
                for nm in img_names:
                    v = sample(st[nm], x2, y2)
                    if nm == "base_colour" and gain != 1.0:
                        v = v.copy()
                        v[:, :3] *= gain             # TONE_GAIN only: one factor per piece, the wood stays as sharp
                    if nm == "normal":
                        v = _rot_normal(v, -sh[0] / RS)
                    res[nm][sel] += ww[sel, None] * v
                wsum[sel] += ww[sel]
        for nm in img_names:
            res[nm] /= np.maximum(wsum, 1e-6)[..., None]
        return res

    # the cut to the surroundings: per row of r on the unwrapped grid, left and right
    Sg = np.arange(-(CUT_OUT + 12), CUT_OUT + 13.0)
    Rg = np.arange(np.floor(R0 - CUT_OUT - 2), TOP_KEEP + 2)
    SG, RG = np.meshgrid(Sg, Rg)
    XG, YG = from_sr(SG, RG)
    QG = q_of(SG, RG, G)
    dG = ring_d(XG, YG)
    accG = sample(acc_changed[..., None].astype(np.float32), XG.ravel(), YG.ravel(), cubic=False).reshape(SG.shape) > 0.01
    inG = (RG > G[LOW](SG) + LOW_KEEP - 1) & (RG < np.minimum(G[-1](SG) - 2.0, TOP_KEEP) + 1)
    # segment splits first (the fill on the grid needs them): where the two sources agree, within 12 px of the bound
    splits = {}
    for k, p in enumerate(plan):
        if p is None:
            continue
        inside = (QG >= edges[k] - 0.1) & (QG < edges[k + 1] + 0.1)
        for si in range(1, len(p["segs"])):
            sa, sb, bd = p["segs"][si - 1][0], p["segs"][si][0], p["segs"][si][1]
            xa, ya, _ = src_xy(SG, QG, sa)
            xb, yb, _ = src_xy(SG, QG, sb)
            va = {nm: sample(st[nm], xa.ravel(), ya.ravel()).reshape(SG.shape + (4,)) for nm in ("base_colour", "normal")}
            vb = {nm: sample(st[nm], xb.ravel(), yb.ravel()).reshape(SG.shape + (4,)) for nm in ("base_colour", "normal")}
            va["normal"], vb["normal"] = _rot_normal(va["normal"], -sa[0] / RS), _rot_normal(vb["normal"], -sb[0] / RS)
            cst = box(np.abs(_feat(va) - _feat(vb)) @ np.array([1.0, 0.6, 0.6]), 2, 3)
            path = _dp(cst, inside & (np.abs(SG - bd) < 12))
            qs = np.array([QG[i, j] for i, j in sorted(path.items())])
            ss = np.array([Sg[j] for i, j in sorted(path.items())])
            o = np.argsort(qs)
            splits[(k, si)] = (lambda qq, qs=qs[o], ss=ss[o]: np.interp(qq, qs, ss))
    FG = fill_at(SG, QG, ("base_colour", "normal"), splits)
    AV = {k: sample(ac[k], XG.ravel(), YG.ravel()).reshape(SG.shape + (4,)) for k in ("base_colour", "normal")}
    cost = box(np.abs(_feat(FG) - _feat(AV)) @ np.array([1.0, 0.6, 0.6]), 2, 3)
    stripG = np.digitize(QG, STRIPS)
    cuts, cut_cost = {}, []
    for k in range(len(edges) - 1):
        for side in (-1, 1):
            allowed = (stripG == k) & (np.abs(SG) > chord[k] + 1) & (np.abs(SG) < chord[k] + CUT_EXTRA) & (np.sign(SG) == side) & ~accG & inG
            if not allowed.any():
                continue
            path = _dp(cost, allowed)
            rows = np.array(sorted(path))
            cuts[(k, side)] = (Rg[rows], np.array([Sg[path[i]] for i in rows], float))
            cut_cost.append(round(float(np.mean([cost[i, j] for i, j in path.items()])), 1))

    def cut_at(k, side, r):
        if (k, side) not in cuts:
            return np.full(np.shape(r), side * 1e9)
        rr1, ss1 = cuts[(k, side)]
        return np.interp(r, rr1, ss1)
    cL = lambda r, k: cut_at(k, -1, r)
    cR = lambda r, k: cut_at(k, 1, r)
    rep["cuts"] = len(cuts)
    rep["cut_mean_cost_left_right"] = cut_cost

    # compose: the fill inside the cuts and always in the zone; the gaps under and over the disc stay stock; 1.5 px feathers
    ys, xs = np.where(region)
    s_k, r_k, q_k = s_px[ys, xs], r_px[ys, xs], q_px[ys, xs]
    F = fill_at(s_k, q_k, NAMES, splits)
    kk = strip_of[ys, xs]
    lo_c, hi_c = np.zeros(len(ys)), np.zeros(len(ys))
    for k in range(len(edges) - 1):
        sel = kk == k
        lo_c[sel], hi_c[sel] = cL(r_k[sel], k), cR(r_k[sel], k)
    c_in = np.clip(np.minimum(s_k - lo_c, hi_c - s_k) / 1.5 + 0.5, 0, 1)
    c_in = np.where(dph[ys, xs] <= ZONE, 1.0, c_in)
    c_in = c_in * np.clip((g_hi[ys, xs] - r_k) / 1.5 + 0.5, 0, 1) * np.clip((r_k - g_lo[ys, xs]) / 1.5 + 0.5, 0, 1)
    for nm in NAMES:
        out = ac[nm].copy()
        out[ys, xs] = ac[nm][ys, xs] * (1 - c_in[:, None]) + F[nm] * c_in[:, None]
        OUT[nm] = np.clip(out, 0, 255)
    x0, y0, x1, y1 = EYE_SRC
    for nm in NAMES:
        OUT["eye_" + nm] = Dds(stock(nm)).read(0, x0, y0, x1, y1).astype(np.float32)
    STATE.update(region=region, comp=(ys, xs, c_in), ac=ac, st=st, G=G, GS=GS, tr=tr, plan=plan, cuts=(cL, cR), splits=splits, q_px=q_px, acc_changed=acc_changed)
    rep["pixels_rebuilt"] = int((c_in > 0).sum())
    rep["zone_px_not_rebuilt"] = int(((dph <= ZONE) & (r_px < g_hi - 1) & (r_px > g_lo + 1) & ~region).sum())
    rep["accepted_patch_px_changed"] = int((acc_changed & (np.abs(OUT["base_colour"] - ac["base_colour"]).max(-1) > 0.5)).sum())
    return rep


# ---- output -------------------------------------------------------------------------------------------------------
_CACHE = {}


def _windows():
    ex, ey = EYE_DST
    return [(WIN, ""), ((ex, ey, ex + 64, ey + 64), "eye_")]


LIVE = "live_"


def push_live(prefix="new_", material="MAT-grungni-new"):
    """Writes OUT into live images (atlas y -> Blender row 4095 - y) shown by the material's texture nodes.
    A DDS image loaded in Blender keeps its compressed blocks and the viewport draws those: pixels written into it show
    for BC1 (base colour) but not for the BC3 normal map. So the first call makes plain images live_<name> with the
    file's pixels and points the material's nodes at them; restore_dds() points them back after the files are written."""
    import bpy
    mat = bpy.data.materials[material]
    for nm in NAMES:
        src = bpy.data.images[prefix + nm]
        w, h = src.size
        img = bpy.data.images.get(LIVE + nm)
        if nm not in _CACHE:
            px = np.empty(w * h * 4, np.float32)
            src.pixels.foreach_get(px)
            _CACHE[nm] = px.reshape(h, w, 4)
        if img is None:
            img = bpy.data.images.new(LIVE + nm, w, h, alpha=True)
            img.colorspace_settings.name = src.colorspace_settings.name
            img.alpha_mode = src.alpha_mode
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None and node.image.name == prefix + nm:
                node.image = img
        px = _CACHE[nm]
        for (x0, y0, x1, y1), key in _windows():
            px[h - y1:h - y0, x0:x1] = OUT[key + nm][::-1] / 255.0
        img.pixels.foreach_set(px.ravel())
        img.update()


def restore_dds(prefix="new_", material="MAT-grungni-new"):
    """Reloads the written DDS files into the scene images and points the material back at them."""
    import bpy
    mat = bpy.data.materials[material]
    for nm in NAMES:
        src = bpy.data.images[prefix + nm]
        src.filepath = str(cur_path(nm))
        src.reload()
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image is not None and node.image.name == LIVE + nm:
                node.image = src


def save_dds():
    """Level 0 and the mips of BOX and of the eye's new place, only blocks that changed (others keep their bytes).
    Starts from the accepted textures each time, so a pass never builds on the last one."""
    rep = {}
    bx0, by0 = BOX[0] - WIN[0], BOX[1] - WIN[1]
    bw, bh = BOX[2] - BOX[0], BOX[3] - BOX[1]
    ex, ey = EYE_DST
    for nm in NAMES:
        dds = Dds(acc(nm))
        diff = np.abs(OUT[nm] - STATE["ac"][nm]).max(-1) > 0.5
        inbox = diff[by0:by0 + bh, bx0:bx0 + bw]
        assert diff.sum() == inbox.sum(), "change outside the box"
        for (x0, y0), cur, mk in (((BOX[0], BOX[1]), OUT[nm][by0:by0 + bh, bx0:bx0 + bw], inbox.astype(np.float32)),
                                  ((ex, ey), OUT["eye_" + nm], np.ones((64, 64), np.float32))):
            h_, w_ = mk.shape
            for level in range(dds.mips):
                s = 1 << level
                w2, h2 = w_ // s, h_ // s
                if w2 < 4 or h2 < 4 or w2 % 4 or h2 % 4:
                    break
                if level:
                    cur = cur.reshape(h2, 2, w2, 2, 4).mean((1, 3))
                    mk = mk.reshape(h2, 2, w2, 2).max((1, 3))
                only = mk.reshape(h2 // 4, 4, w2 // 4, 4).max((1, 3)) > 0
                dds.write(level, x0 // s, y0 // s, np.clip(np.round(cur), 0, 255).astype(np.uint8), only=only)
        TEX.mkdir(parents=True, exist_ok=True)
        dds.save(cur_path(nm))
        rep[nm] = {"changed_px_level0": int(diff.sum())}
    return rep
