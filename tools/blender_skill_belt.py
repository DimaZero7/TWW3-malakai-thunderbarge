"""Steel belt under the closed gun port, rebuilt from the stock atlas (project venv: numpy, scipy, Pillow).

  blender_skill_belt.py build       new steel into build/solid_hull_skill/tex/ (base: the DDS as they were before this
                                    pass, build/steel_belt/backup/; the old fill's edge line: build/steel_belt/de_col.npy,
                                    from blender_skill_tex.py's own edge code); run caps after it
  blender_skill_belt.py dry         the same without writing, preview build/steel_belt/dry.png
  blender_skill_belt.py caps        copies the stock port box (all block-aligned mips) to a free atlas spot for the
                                    barrel caps, governor balls and one small piece that sampled it (their UVs move there)

How the belt is built (atlas px; the structure measured on the stock, see docs/research/img/steel-belt-diagnosis.png):
  * only the port's painting on the steel is replaced (polygon PAINT); everything the old fill overwrote outside it
    goes back to the stock pixels;
  * the belt's top edge: the stock edge (smoothed) outside the painting, a straight blend of its offset across it;
  * seam A (between the wide bow plate and the next plate) continues the measured stock line up to the edge, shaped like
    seam B with the measured difference in lean;
  * gloss and tone change with the depth below the edge on every plate (matte band 20-80 px down, glossier and darker
    lower), so every source keeps the depth t below its own edge;
  * seam A and right of it: plate B-C placed by distance from seam B (seam B -> seam A) at the same depth: the seam's
    profile, the rivet right of the seam and the plate's texture and gloss at that depth come with it;
  * the bow plate left of seam A: its own clean part further left, along the edge, same depth (first clean of a few
    shifts; the bow-row rivet at 946 lands at 1035 and continues the stock row 903, 946, 989.5);
  * the rivet left of seam A: a whole bow plate rivet (1044.2, 3879.6) at the place of the stock pair (seam B: -10.2 px,
    same depth), integer offset;
  * an edge-following copy turns the edge's direction, so the normals of that copy are turned by the same angle;
  * cuts between sources are feathered 1.5 px; no averaging of sources. All maps take the same source pixels.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage as nd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from blender_dds import Dds  # noqa: E402
from blender_skill_plank2 import sample  # noqa: E402  (Catmull-Rom)

GAME = REPO / "build" / "solid_hull" / "game"
TEX = REPO / "build" / "solid_hull_skill" / "tex"
BACK = REPO / "build" / "steel_belt" / "backup"            # the DDS as they were before this pass
NAMES = ("base_colour", "normal", "material_map")
WIN = (640, 3456, 1664, 4096)
BOX = (896, 3584, 1280, 3968)
CENTRE, R, FEATHER, STRETCH = (1052.0, 3787.0), 94.0, 16.0, 1.1     # the old fill's zone (blender_skill_tex.py)
PAINT = [(987, 3760), (987, 3808), (993, 3809), (997, 3811), (997, 3834), (1005, 3841), (1020, 3845), (1050, 3850), (1076, 3850), (1096, 3845), (1112, 3842),
         (1119, 3827), (1126, 3811), (1131, 3798), (1132, 3760)]      # the port's painting on the steel (stock)
PAINT_DIL, RAMP = 1.0, 1.5
EDGE_SKIP = (986, 1150)                    # no stock edge here (the painted disc)
BOW_DX = (-89, -75, -103)                  # bow plate: candidate shifts along the edge, first clean wins
BOW_SRC_X = (884, 984)                     # clean bow plate columns (tip .. the painting / rivet 989.5)
RIVETS_OFF = [(903.1, 3875.8), (946.2, 3844.3), (989.5, 3818.7)]   # never copied by the shifts (a sheared copy is oval)
ROW_RIVET = ((946.2, 3844.3), 1035.2)      # bow row 903, 946, 989.5 continues at 1035 (same depth), whole rivet
RIVET_R = 8.5                              # rivet with its dark ring
CUT_A = -3.5                               # bow copy | B-C copy: just left of seam A's profile (-2 .. +3 px)
STAMP_SRC, STAMP_R = (1044.2, 3879.6), 6.5     # the stock bow plate rivet left of seam A (mid pair): compact halo
B_LEFT = (1139.5, 3786.2)                  # stock rivet left of seam B: its place relative to the seam and edge
B_RIGHT = (1161.7, 3783.4)                 # stock rivet right of seam B
CAP_SRC, CAP_DST = (896, 3584, 1280, 3968), (512, 1024)          # caps box: stock -> free spot (multiples of 128; the
#   caps' u stays under 0.25 so the half-float UVs keep their 0.5 px step: the moved UVs are exact)


def stock(nm):
    return GAME / f"dwf_thunderbarge_grungni_01_{nm}.dds"


def cur(nm):
    return TEX / f"tww3_mtb_dwf_thunderbarge_grungni_01_{nm}.dds"


def back(nm):
    return BACK / f"tww3_mtb_dwf_thunderbarge_grungni_01_{nm}.dds"


def poly_mask(poly, H, W):
    from PIL import Image, ImageDraw
    im = Image.new("L", (W, H), 0)
    ImageDraw.Draw(im).polygon([(x - WIN[0], y - WIN[1]) for x, y in poly], fill=1)
    return np.array(im) > 0


def edge_raw(bc, guess):
    """Belt top edge per column: where the wood's saturation gives way to grey steel (sub-pixel), near guess."""
    sat = bc[..., :3].max(-1) - bc[..., :3].min(-1)
    H, W = sat.shape
    et = np.full(W, np.nan)
    for x in range(W):
        y0 = int(guess[x]) - 8
        if y0 < 1 or y0 + 17 >= H:
            continue
        col = sat[y0:y0 + 17, x]
        for k in range(1, 15):
            if col[k - 1] >= 30 > col[k] and (col[k:k + 3] < 30).all():
                et[x] = y0 + k - 1 + (col[k - 1] - 30) / max(col[k - 1] - col[k], 1e-3)
                break
    return et


def seam_track(na, x_guess, rows, half=5):
    """Seam position per row: peak of |d/dx| of the normal's X (alpha), 5 rows smoothed, parabolic sub-pixel."""
    g = np.abs(np.diff(na.astype(float), axis=1))
    g = nd.uniform_filter1d(g, 5, axis=0)
    xs = []
    x = x_guess
    for y in rows:
        j0 = int(round(x)) - half
        seg = g[y, j0:j0 + 2 * half + 1]
        k = int(np.argmax(seg))
        if 0 < k < len(seg) - 1:
            a, b, c = seg[k - 1], seg[k], seg[k + 1]
            off = 0.5 * (a - c) / max(a - 2 * b + c, -1e9) if (a - 2 * b + c) < 0 else 0.0
        else:
            off = 0.0
        x = j0 + k + off + 0.5            # diff sits between columns
        xs.append(x)
    return np.array(xs)


def measure(st):
    import blender_skill_tex as T
    bc = st["base_colour"]
    H, W = bc.shape[:2]
    edge, _, _ = T.analyse(bc)
    ecol = np.polyval(edge, np.arange(W, dtype=float))
    et = edge_raw(bc, ecol)
    xa = np.arange(W) + WIN[0]
    ok = np.isfinite(et) & (np.abs(et - ecol) < 4) & ~((xa > EDGE_SKIP[0]) & (xa < EDGE_SKIP[1]))
    off = np.interp(np.arange(W), np.where(ok)[0], (et - ecol)[ok])
    off = nd.median_filter(off, 11)
    lo, hi = EDGE_SKIP[0] - WIN[0], EDGE_SKIP[1] - WIN[0]
    off[lo:hi + 1] = np.interp(np.arange(lo, hi + 1), [lo, hi], [off[lo], off[hi]])
    off = nd.uniform_filter1d(off, 5)
    e_st = ecol + off                                          # smoothed stock edge, bridged over the painting
    jitter = (et - e_st)[ok]
    # the rim (the bright bevel line under the edge): what the eye follows; sources and copies are placed by it
    lum = nd.median_filter(bc[..., :3].mean(-1), size=(1, 5))
    rim = np.full(W, np.nan)
    for x in range(W):
        y0 = int(e_st[x]) - 3
        if y0 < 1 or y0 + 13 >= H:
            continue
        c = lum[y0:y0 + 12, x]
        k = int(np.argmax(c))
        off_ = 0.0
        if 0 < k < len(c) - 1 and (c[k - 1] - 2 * c[k] + c[k + 1]) < 0:
            off_ = 0.5 * (c[k - 1] - c[k + 1]) / (c[k - 1] - 2 * c[k] + c[k + 1])
        rim[x] = y0 + k + off_
    rok = ok & np.isfinite(rim)
    roff = np.interp(np.arange(W), np.where(rok)[0], (rim - ecol)[rok])
    roff = nd.median_filter(roff, 11)
    roff[lo:hi + 1] = np.interp(np.arange(lo, hi + 1), [lo, hi], [roff[lo], roff[hi]])
    roff = nd.uniform_filter1d(roff, 5)
    rim_st = ecol + roff
    # seams: B (whole height), A (under the painting only), in window rows
    na = st["normal"][..., 3]
    rowsB = np.arange(3772, 3961) - WIN[1]
    xB = seam_track(na, 1150.3 - WIN[0], rowsB)
    rowsA = np.arange(3852, 3949) - WIN[1]           # below 3948 a rivet (1053, 3953) pulls the track
    xA = seam_track(na, 1064.0 - WIN[0], rowsA)
    pB = np.polyfit(rowsB, xB, 2)
    dAB = xA - np.polyval(pB, rowsA)                           # A - B: a straight function of y (lean difference)
    pD = np.polyfit(rowsA, dAB, 1)
    resA = dAB - np.polyval(pD, rowsA)
    pA_meas = np.polyfit(rowsA, xA, 2)
    return dict(e_st=e_st, rim_st=rim_st, ecol=ecol, et=et, ok=ok, pB=pB, pD=pD, pA_meas=pA_meas, rowsA=rowsA, xA=xA, rowsB=rowsB, xB=xB,
                rep={"edge_jitter_std": round(float(jitter.std()), 2), "rim_minus_edge_px_p5_50_95": [round(float(v), 2) for v in np.percentile((rim_st - e_st)[rok], [5, 50, 95])], "B_fit_res_px": round(float(np.abs(xB - np.polyval(pB, rowsB)).max()), 2),
                     "A_minus_B_fit": [round(float(v), 4) for v in pD], "A_fit_res_px": round(float(np.abs(resA).max()), 2),
                     "A_top_model_vs_quadratic_px": round(float(np.polyval(pB, 3786 - WIN[1]) + np.polyval(pD, 3786 - WIN[1])
                                                               - np.polyval(pA_meas, 3786 - WIN[1])), 2)})


def rotate_normal(n, ang):
    """Turns the tangent-space X (alpha) and Y (green) of normal pixels by ang (rad, atlas axes, y down)."""
    nx, ny = n[..., 3] - 127.5, n[..., 1] - 127.5
    c, s = np.cos(ang), np.sin(ang)
    out = n.copy()
    out[..., 3] = nx * c - ny * s + 127.5
    out[..., 1] = nx * s + ny * c + 127.5
    return out


def build():
    st = {nm: Dds(stock(nm)).read(0, *WIN).astype(np.float32) for nm in NAMES}
    cu = {nm: Dds(back(nm)).read(0, *WIN).astype(np.float32) for nm in NAMES}
    H, W = st["base_colour"].shape[:2]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    M = measure(st)
    e_st = M["e_st"]
    de_col = np.load(REPO / "build" / "steel_belt" / "de_col.npy")      # the old fill's edge (current wood ends there)
    e_new = np.minimum(e_st, de_col + 0.3)
    rim = M["rim_st"]                                                    # stock rim, bridged straight over the painting
    sl_st = sl_new = np.gradient(nd.uniform_filter1d(rim, 9))
    cols = np.arange(W)
    E = lambda x: np.interp(x, cols, rim)                                # dest and source depth: below the rim line
    ES = E
    TH_N = lambda x: np.arctan(np.interp(x, cols, sl_new))
    TH_S = lambda x: np.arctan(np.interp(x, cols, sl_st))
    B = lambda y: np.polyval(M["pB"], y)
    yA0 = 3852 - WIN[1]
    shiftA = np.polyval(M["pA_meas"], yA0) - (B(yA0) + np.polyval(M["pD"], yA0))

    def Ax(y):
        y = np.asarray(y, float)
        return np.where(y >= yA0, np.polyval(M["pA_meas"], y), B(y) + np.polyval(M["pD"], y) + shiftA)
    m_old = np.clip((R + FEATHER - np.hypot((xx - (CENTRE[0] - WIN[0])) / STRETCH, yy - (CENTRE[1] - WIN[1]))) / FEATHER, 0, 1)
    P = poly_mask(PAINT, H, W)
    wP = np.clip((PAINT_DIL + RAMP - nd.distance_transform_edt(~P)) / RAMP, 0, 1)
    ys_, xs_ = np.where(wP > 0)
    sy = slice(ys_.min() - 2, ys_.max() + 3)
    sx = slice(xs_.min() - 2, xs_.max() + 3)
    Y, X = yy[sy, sx], xx[sy, sx]
    t = Y - E(X)
    dA = X - Ax(Y)
    # seam A and right of it: plate B-C by distance from seam B, same depth below its edge
    xa = B(Y - 13) + dA
    for _ in range(5):
        ya = ES(xa) + t
        xa = B(ya) + dA
    smp_a = {nm: sample(st[nm], xa.ravel(), ya.ravel()).reshape(Y.shape + (4,)) for nm in NAMES}
    smp_a["normal"] = rotate_normal(smp_a["normal"], TH_N(X) - TH_S(xa))
    # bow plate: further left along the edge, first clean shift
    lab = np.full(Y.shape, -1)
    cand = []
    for k, dx in enumerate(BOW_DX):
        xb = X + dx
        yb = ES(xb) + t
        ax, ay = xb + WIN[0], yb + WIN[1]
        ok = (ax >= BOW_SRC_X[0]) & (ax <= BOW_SRC_X[1])
        for rx, ry in RIVETS_OFF:
            ok &= np.hypot(ax - rx, ay - ry) > RIVET_R
        lab[(lab < 0) & ok] = k
        s = {nm: sample(st[nm], xb.ravel(), yb.ravel()).reshape(Y.shape + (4,)) for nm in NAMES}
        s["normal"] = rotate_normal(s["normal"], TH_N(X) - TH_S(xb))
        cand.append(s)
    need_bow = (dA < CUT_A + RAMP) & (wP[sy, sx] > 0) & (t > -2)
    missing = int((need_bow & (lab < 0)).sum())
    lab[lab < 0] = 0
    wk = [nd.uniform_filter((lab == k).astype(np.float32), 3) for k in range(len(BOW_DX))]
    tot = np.sum(wk, 0)
    w_a = np.clip((dA - CUT_A) / RAMP + 0.5, 0, 1)[..., None]
    new = {}
    for nm in NAMES:
        bow = sum(w[..., None] * c[nm] for w, c in zip(wk, cand)) / tot[..., None]
        new[nm] = smp_a[nm] * w_a + bow * (1 - w_a)
    # the rivet left of seam A: a whole bow plate rivet where the stock pair has it at seam B
    dA_bl = (B_LEFT[0] - WIN[0]) - B(B_LEFT[1] - WIN[1])
    t_bl = (B_LEFT[1] - WIN[1]) - ES(B_LEFT[0] - WIN[0])
    yc = 3790.0 - WIN[1]
    for _ in range(6):
        xc = float(Ax(yc)) + dA_bl
        yc = float(E(xc)) + t_bl
    (rsx, rsy), rdx = ROW_RIVET
    rx = rdx - WIN[0]
    stamps = [(STAMP_SRC, (xc, yc)), ((rsx, rsy), (rx, float(E(rx)) + (rsy - WIN[1]) - float(ES(rsx - WIN[0]))))]
    # the rivet right of seam A comes with the B-C copy, but sheared and resampled: put the same stock rivet back whole
    dA_br = (B_RIGHT[0] - WIN[0]) - B(B_RIGHT[1] - WIN[1])
    t_br = (B_RIGHT[1] - WIN[1]) - ES(B_RIGHT[0] - WIN[0])
    yr = 3790.0 - WIN[1]
    for _ in range(6):
        xr = float(Ax(yr)) + dA_br
        yr = float(E(xr)) + t_br
    stamps.append((B_RIGHT, (xr, yr)))
    offs = []
    for (ssx, ssy), (dx_, dy_) in stamps:
        sx0, sy0 = ssx - WIN[0], ssy - WIN[1]
        ox, oy = int(round(dx_ - sx0)), int(round(dy_ - sy0))
        offs.append([ox, oy, round(dx_ + WIN[0], 1), round(dy_ + WIN[1], 1)])
        ws = np.clip((STAMP_R - np.hypot(X - (sx0 + ox), Y - (sy0 + oy))) / RAMP + 0.5, 0, 1)[..., None]
        for nm in NAMES:
            src = st[nm][(Y - oy).astype(int), (X - ox).astype(int)]
            new[nm] = new[nm] * (1 - ws) + src * ws
    # tone and gloss drift slowly over a plate (a painted gradient), so a copy can sit a few units off where it meets the
    # stock: a smooth offset (harmonic inside the painting, from the smoothed difference on a ring just outside) brings
    # base colour and material map level with the stock; the detail stays the copy's own (one source per pixel)
    dom = (wP[sy, sx] > 0) & (t > 1)
    ring = ~dom & nd.binary_dilation(dom, np.ones((5, 5), bool)) & (t > 1)
    offs_rep = {}
    for nm, chs in (("base_colour", (0, 1, 2)), ("material_map", (0, 1))):
        for c in chs:
            diff = st[nm][sy, sx][..., c] - new[nm][..., c]
            lum_d = st["base_colour"][sy, sx][..., :3].mean(-1) - new["base_colour"][..., :3].mean(-1)
            use = ring & (np.abs(lum_d - np.median(lum_d[ring])) < 25)     # rivets, seams on the ring left out
            g = np.where(use, diff, 0.0)
            den = nd.gaussian_filter(use.astype(float), 6)
            fixed = nd.gaussian_filter(g, 6) / np.maximum(den, 1e-6)
            D = np.where(dom, float(np.median(diff[ring])), np.where(ring, fixed, 0.0))
            free = dom.copy()
            known = dom | ring
            for _ in range(3000):
                Dp = np.pad(D, 1, mode="edge")
                kp = np.pad(known, 1)
                nb = [(Dp[:-2, 1:-1], kp[:-2, 1:-1]), (Dp[2:, 1:-1], kp[2:, 1:-1]), (Dp[1:-1, :-2], kp[1:-1, :-2]), (Dp[1:-1, 2:], kp[1:-1, 2:])]
                sm = sum(np.where(k, v, D) for v, k in nb)
                D = np.where(free, sm / 4.0, D)
            new[nm][..., c] = np.where(dom, new[nm][..., c] + D, new[nm][..., c])
            offs_rep[f"{nm}{c}"] = [round(float(np.percentile(D[dom], 5)), 1), round(float(np.percentile(D[dom], 95)), 1)]
    # composite: new steel inside the painting, stock steel elsewhere in the old zone, current wood above the edge
    zone = (m_old > 0) & (yy > e_new[None, :] - 2.0)
    b = np.clip(yy - (e_new[None, :] - 0.6) + 0.5, 0, 1)[..., None]
    out = {}
    for nm in NAMES:
        steel = st[nm].copy()
        w = wP[sy, sx][..., None]
        steel[sy, sx] = steel[sy, sx] * (1 - w) + new[nm] * w
        o = cu[nm].copy()
        o[zone] = (cu[nm] * (1 - b) + steel * b)[zone]
        out[nm] = np.clip(o, 0, 255)
    used = [int(((lab == k) & need_bow).sum()) for k in range(len(BOW_DX))]
    rep = dict(M["rep"])
    rep.update({"paint_px": int(P.sum()), "zone_px": int(zone.sum()),
                "edge_new_minus_old_px_p5_50_95": [round(float(v), 2) for v in np.percentile((e_new - de_col)[925 - WIN[0]:1180 - WIN[0]], [5, 50, 95])],
                "seam_A_x_at_3786_3852": [round(float(Ax(3786 - WIN[1]) + WIN[0]), 1), round(float(Ax(yA0) + WIN[0]), 1)],
                "bow_px_per_shift": used, "bow_px_without_clean_source": missing,
                "bc_src_x": [round(float(xa[(w_a[..., 0] > 0) & (wP[sy, sx] > 0)].min() + WIN[0]), 1), round(float(xa[(w_a[..., 0] > 0) & (wP[sy, sx] > 0)].max() + WIN[0]), 1)],
                "bc_src_y": [round(float(ya[(w_a[..., 0] > 0) & (wP[sy, sx] > 0)].min() + WIN[1]), 1), round(float(ya[(w_a[..., 0] > 0) & (wP[sy, sx] > 0)].max() + WIN[1]), 1)],
                "normal_turn_deg_bc_bow": [round(float(np.degrees(np.median((TH_N(X) - TH_S(xa))[wP[sy, sx] > 0]))), 1),
                                           round(float(np.degrees(np.median((TH_N(X) - TH_S(X + BOW_DX[0]))[wP[sy, sx] > 0]))), 1)],
                "stamps_offset_and_dest": offs, "tone_offset_p5_p95": offs_rep,
                "rivet_B_left_rel_seam_edge": [round(float(dA_bl), 2), round(float(t_bl), 2)], "transition_px": RAMP})
    np.savez_compressed(REPO / "build" / "steel_belt" / "belt_out.npz", **{nm: out[nm].astype(np.float32) for nm in NAMES})
    return out, cu, st, rep

def save(out, cu, st):
    """Level 0 and mips of BOX. A block whose pixels equal the stock gets the stock bytes; equal to the current: kept;
    otherwise encoded (mips from 2x2 means of level 0)."""
    rep = {}
    bx0, by0 = BOX[0] - WIN[0], BOX[1] - WIN[1]
    bw, bh = BOX[2] - BOX[0], BOX[3] - BOX[1]
    for nm in NAMES:
        dds, sdds = Dds(back(nm)), Dds(stock(nm))
        o = out[nm][by0:by0 + bh, bx0:bx0 + bw]
        oq = np.clip(np.round(o), 0, 255)
        is_st = (np.abs(oq - st[nm][by0:by0 + bh, bx0:bx0 + bw]).max(-1) < 0.5)
        is_cu = (np.abs(oq - cu[nm][by0:by0 + bh, bx0:bx0 + bw]).max(-1) < 0.5)
        outside = np.ones((H_ := out[nm].shape[0], out[nm].shape[1]), bool)
        outside[by0:by0 + bh, bx0:bx0 + bw] = False
        assert np.abs(out[nm] - cu[nm]).max(-1)[outside].max() < 0.5, "change outside the box"
        lv = o
        counts = {"stock_blocks": 0, "kept_blocks": 0, "encoded_blocks": 0}
        for level in range(dds.mips):
            s = 1 << level
            w_, h_ = bw // s, bh // s
            if w_ < 4 or h_ < 4 or w_ % 4 or h_ % 4:
                break
            if level:
                lv = lv.reshape(h_, 2, w_, 2, 4).mean((1, 3))
            fs = 4 * s
            st_blk = is_st.reshape(bh // fs, fs, bw // fs, fs).all((1, 3))
            cu_blk = is_cu.reshape(bh // fs, fs, bw // fs, fs).all((1, 3))
            enc = ~st_blk & ~cu_blk
            dds.write(level, BOX[0] // s, BOX[1] // s, np.clip(np.round(lv), 0, 255).astype(np.uint8), only=enc)
            at, tw, _ = dds.offsets[level]
            sat_, _, _ = sdds.offsets[level]
            per_row = (tw + 3) // 4
            for by, bx in zip(*np.where(st_blk & ~cu_blk)):
                k = ((BOX[1] // s // 4 + by) * per_row + BOX[0] // s // 4 + bx) * dds.block
                dds.b[at + k:at + k + dds.block] = sdds.b[sat_ + k:sat_ + k + dds.block]
            counts["stock_blocks"] += int((st_blk & ~cu_blk).sum())
            counts["kept_blocks"] += int(cu_blk.sum())
            counts["encoded_blocks"] += int(enc.sum())
        dds.save(cur(nm))
        rep[nm] = counts
    return rep


def caps():
    """Byte copy of the stock blocks of CAP_SRC to CAP_DST in every block-aligned mip of the three DDS (in place)."""
    x0, y0, x1, y1 = CAP_SRC
    dx0, dy0 = CAP_DST
    rep = {}
    for nm in NAMES:
        dds, sdds = Dds(cur(nm)), Dds(stock(nm))
        levels = 0
        for level in range(dds.mips):
            s = 1 << level
            if any(v % (4 * s) for v in (x0, y0, x1, y1, dx0, dy0)):
                break
            at, tw, _ = dds.offsets[level]
            sat_, _, _ = sdds.offsets[level]
            per_row = (tw + 3) // 4
            for by in range((y1 - y0) // (4 * s)):
                src = sat_ + ((y0 // (4 * s) + by) * per_row + x0 // (4 * s)) * dds.block
                dst = at + ((dy0 // (4 * s) + by) * per_row + dx0 // (4 * s)) * dds.block
                n = (x1 - x0) // (4 * s) * dds.block
                dds.b[dst:dst + n] = sdds.b[src:src + n]
            levels += 1
        dds.save(cur(nm))
        rep[nm] = levels
    return rep


if __name__ == "__main__":
    if sys.argv[1] == "build":
        out, cu_, st_, rep = build()
        rep["save"] = save(out, cu_, st_)
        print(json.dumps(rep, indent=1))
    elif sys.argv[1] == "caps":
        print(json.dumps(caps()))


def preview(out, cu, st, path, box=(930, 3755, 1190, 3885), k=3):
    """Atlas crops stock | before | after (base colour, normal X), k times."""
    from PIL import Image
    x0, y0, x1, y1 = (box[0] - WIN[0], box[1] - WIN[1], box[2] - WIN[0], box[3] - WIN[1])
    rows = []
    for ch in ("base_colour", "normal_a", "material_map"):
        tiles = []
        for src in (st, cu, out):
            a = src["normal"][y0:y1, x0:x1, 3] if ch == "normal_a" else src[ch][y0:y1, x0:x1, :3]
            im = Image.fromarray(np.clip(np.round(a), 0, 255).astype(np.uint8)).convert("RGB")
            tiles.append(im.resize((im.width * k, im.height * k), Image.NEAREST))
        rows.append(tiles)
    w, h = rows[0][0].size
    sheet = Image.new("RGB", (3 * w + 8, 3 * h + 8), (255, 0, 0))
    for r, tiles in enumerate(rows):
        for c, im in enumerate(tiles):
            sheet.paste(im, (c * (w + 4), r * (h + 4)))
    sheet.save(path)


if __name__ == "__main__" and sys.argv[1] == "dry":
    out, cu_, st_, rep = build()
    preview(out, cu_, st_, str(REPO / "build" / "steel_belt" / "dry.png"))
    print(json.dumps(rep, indent=1))
