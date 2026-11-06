"""Atlas work for the closed gun port (project venv python, numpy + Pillow; DDS through tools/blender_dds.py).

  blender_skill_tex.py crop X0 Y0 X1 Y1 OUT_DIR      crops of the stock base colour, normal, material map, mask (PNG)
  blender_skill_tex.py fix                         writes the patched copies to build/solid_hull_skill/tex/
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from blender_dds import Dds  # noqa: E402

GAME = REPO / "build" / "solid_hull" / "game"
OUT = REPO / "build" / "solid_hull_skill" / "tex"
MAPS = ("base_colour", "normal", "material_map", "mask")


def stock(name):
    return GAME / f"dwf_thunderbarge_grungni_01_{name}.dds"


def crop(x0, y0, x1, y1, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in MAPS:
        d = Dds(stock(name))
        px = d.read(0, x0, y0, x1, y1)
        Image.fromarray(px[..., :3]).save(out_dir / f"crop_{name}_rgb.png")
        Image.fromarray(px[..., 3]).save(out_dir / f"crop_{name}_a.png")
        print(name, d.kind, d.dxgi, d.w, d.h, d.mips, px[..., :4].reshape(-1, 4).mean(0).round(1))


if __name__ == "__main__":
    if sys.argv[1] == "crop":
        crop(*map(int, sys.argv[2:6]), sys.argv[6])


# ---- the fix ------------------------------------------------------------------------------------------------------
# All coordinates are atlas pixels of level 0. The painted port (disc, ring, its shadow) sits where the hull's planks
# meet the steel belt. Each part is refilled from the same atlas along its own structure:
#   wood: along the plank family (planks are curves y = q(x) + w; the fill keeps w, so gaps continue straight and
#         parallel and are the very planks of the neighbourhood);
#   steel: along the belt's top edge (y = e(x) + t; the fill keeps t, so the edge, the rivet row and the plate seams
#         continue; the shift is one plate seam spacing so a seam lands where the stock seam enters the disc).
# Tone is checked (medians of the fill against a ring just outside, per material); the material map (metal, gloss)
# is shifted to the ring's medians, base colour and normal are not.
BOX = (896, 3584, 1280, 3968)        # rewritten box at level 0 (aligned to 128 so mips stay block aligned)
WIN = (640, 3456, 1664, 4096)        # read window for the sources
CENTRE, R, FEATHER = (1052.0, 3787.0), 94.0, 16.0
STRETCH_X = 1.1                      # the defect is a little wider than tall (the ring's padding streaks at the sides)
PORTHOLE_C, PORTHOLE_KEEP = (1031.0, 3652.0), 51.0   # the porthole's own painted ring stays
WOOD_SHIFTS = (-136, -150, 200, 230)                 # x shifts of the wood source along the planks, first clean wins
STEEL_SHIFTS = (164, 246, 328, 410, -164, -246)                # x shifts of the steel along the belt edge: whole plate seam spacings


def _bilinear(img, xs, ys):
    from scipy import ndimage as nd
    return np.stack([nd.map_coordinates(img[..., c], [ys, xs], order=1, mode="nearest") for c in range(img.shape[2])], -1)


def analyse(base):
    """Belt edge e(x) and plank slope q'(x), in window pixel coordinates."""
    from scipy import ndimage as nd
    b = base[..., :3].astype(float)
    sat, lum = b.max(2) - b.min(2), b.mean(2)
    grey = (sat < 28) & (lum > 90)
    cx, cy = CENTRE[0] - WIN[0], CENTRE[1] - WIN[1]
    pts = []
    for x in range(int(cx) - 190, int(cx) + 230, 3):
        if abs(x - cx) < R + 8:
            continue
        col = grey[int(cy) - 130:int(cy) + 150, x]
        run = np.convolve(col.astype(int), np.ones(6, int), "valid")
        idx = np.where(run == 6)[0]
        if len(idx):
            pts.append((x, int(cy) - 130 + idx[0]))
    pts = np.array(pts, float)
    keep = np.ones(len(pts), bool)
    for _ in range(4):
        c = np.polyfit(pts[keep, 0], pts[keep, 1], 3)
        res = np.abs(pts[:, 1] - np.polyval(c, pts[:, 0]))
        keep = res < max(2.5 * np.median(res[keep]), 2.0)
    edge = c
    # plank slope from the structure tensor of the normal map's Y channel is done by the caller (needs the normal)
    return edge, pts, keep


def plank_profile(normal, edge):
    from scipy import ndimage as nd
    g = normal[..., 1].astype(float)
    cx, cy = CENTRE[0] - WIN[0], CENTRE[1] - WIN[1]
    xs, sl = [], []
    for x0 in range(int(cx) - 260, int(cx) + 260, 40):
        if abs(x0 + 20 - cx) < R + 30:
            continue
        top = int(cy) - 170
        bot = int(min(np.polyval(edge, x0 + 20) - 12, cy + 40))
        if bot - top < 40:
            continue
        r = g[top:bot, x0:x0 + 40]
        gy, gx = nd.sobel(r, 0), nd.sobel(r, 1)
        J = np.array([[(gx * gx).sum(), (gx * gy).sum()], [(gx * gy).sum(), (gy * gy).sum()]])
        w, v = np.linalg.eigh(J)
        d = v[:, 1]
        xs.append(x0 + 20)
        sl.append(-d[0] / d[1])
    p = np.polyfit(xs, sl, 1)            # q'(x) linear in x
    q = np.polyint(p)                    # q(x), any constant
    return q, np.array(xs), np.array(sl)


def fix():
    OUT.mkdir(parents=True, exist_ok=True)
    win = {}
    for name in ("base_colour", "normal", "material_map"):
        win[name] = Dds(stock(name)).read(0, *WIN).astype(np.float32)
    edge, pts, keep = analyse(win["base_colour"])
    q, qx, qs = plank_profile(win["normal"], edge)
    H, W = win["base_colour"].shape[:2]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = CENTRE[0] - WIN[0], CENTRE[1] - WIN[1]
    d = np.hypot((xx - cx) / STRETCH_X, yy - cy)
    dph = np.hypot(xx - (PORTHOLE_C[0] - WIN[0]), yy - (PORTHOLE_C[1] - WIN[1]))
    m = np.clip((R + FEATHER - d) / FEATHER, 0, 1) * np.clip((dph - PORTHOLE_KEEP) / 6.0, 0, 1)   # defect, feathered
    e = np.polyval(edge, xx)
    steel = yy > e
    pcx, pcy = PORTHOLE_C[0] - WIN[0], PORTHOLE_C[1] - WIN[1]

    from scipy import ndimage as nd
    bc = win["base_colour"][..., :3]
    sat, lum = bc.max(2) - bc.min(2), bc.mean(2)
    big = nd.binary_opening((sat > 45) | (lum > 225), np.ones((9, 9), bool))      # large painted items on steel, not rivets
    bad_steel = nd.binary_dilation(big, np.ones((13, 13), bool))
    bad_wood = nd.binary_dilation(nd.binary_opening(lum > 150, np.ones((7, 7), bool)), np.ones((13, 13), bool))

    def clean(sx, sy, bad):
        """Source pixels free of the port's paint, the porthole's ring and the atlas features at the left."""
        ax, ay = sx + WIN[0], sy + WIN[1]
        return ((np.hypot((sx - cx) / STRETCH_X, sy - cy) > R + FEATHER + 4) & (np.hypot(sx - pcx, sy - pcy) > PORTHOLE_KEEP + 4)
                & (ax > 830) & ~((ax < 885) & (ay > 3800)) & (sx > 2) & (sx < W - 3) & (sy > 2) & (sy < H - 3)
                & ~bad[np.clip(np.round(sy).astype(int), 0, H - 1), np.clip(np.round(sx).astype(int), 0, W - 1)])

    def pick(cands):
        """First clean candidate per pixel; the choice is softened over a few pixels so source switches do not show."""
        from scipy import ndimage as nd
        taken = np.zeros_like(xx, bool)
        ws = []
        for sx, sy, ok in cands:
            first = ok & ~taken
            taken |= ok
            w = nd.gaussian_filter(first.astype(np.float32), 5.0) * ok
            ws.append(w)
        tot = np.sum(ws, 0)
        return [(sx, sy, w / np.maximum(tot, 1e-6)) for (sx, sy, _), w in zip(cands, ws)], tot > 1e-6

    def plank_src(sh):
        sx = xx + sh
        return sx, yy - np.polyval(q, xx) + np.polyval(q, sx)

    def edge_src(sh):
        sx = xx + sh
        return sx, yy - e + np.polyval(edge, sx)

    wc = []
    for sh in WOOD_SHIFTS:                                        # planks first: keep the plank coordinate
        sx, sy = plank_src(sh)
        wc.append((sx, sy, clean(sx, sy, bad_wood) & (sy < np.polyval(edge, sx) - 3)))
    for sh in (200, 240, -150):                                   # the strip just above the belt: keep the edge coordinate
        sx, sy = edge_src(sh)
        wc.append((sx, sy, clean(sx, sy, bad_wood) & (sy < np.polyval(edge, sx) - 1)))
    wpick, wok = pick(wc)
    sc = []
    for sh in STEEL_SHIFTS:
        sx, sy = edge_src(sh)
        sc.append((sx, sy, clean(sx, sy, bad_steel) & (sy > np.polyval(edge, sx) + 1)))
    spick, sok = pick(sc)
    need = m > 0
    report_missing = [int((~wok & need & (yy < e)).sum()), int((~sok & need & (yy >= e)).sum())]

    def sample(img, picks, ok):
        acc = np.zeros(img.shape, np.float32)
        for sx, sy, w in picks:
            sel = w > 0
            if sel.any():
                acc[sel] += w[sel, None] * _bilinear(img, sx[sel], sy[sel])
        acc[~ok] = img[~ok]
        return acc
    blend = np.clip((yy - e) + 0.5, 0, 1)[..., None]               # one pixel wide transition at the edge
    ring = (d > R + FEATHER + 4) & (d < R + FEATHER + 34) & (dph > PORTHOLE_KEEP + 6)
    report = {"edge_points": int(keep.sum()), "edge_res_px": float(np.abs(pts[keep, 1] - np.polyval(edge, pts[keep, 0])).max()),
              "plank_slopes": [[int(a), round(float(b), 3)] for a, b in zip(qx, qs)], "without_source_px_wood_steel": report_missing}
    out = {}
    for name, img in win.items():
        wood = sample(img, wpick, wok)
        stl = sample(img, spick, sok)
        fill = wood * (1 - blend) + stl * blend
        for cls in (False, True):                                    # tone check against the ring outside (reported, not applied:
            sel = ring & (steel == cls)                              # the sources are the same planks and plates nearby)
            insel = (m > 0.99) & (steel == cls)
            if sel.sum() > 50 and insel.sum() > 50:
                ring_med, fill_med = np.median(img[sel], 0), np.median(fill[insel], 0)
                report[f"{name}_mean_{'steel' if cls else 'wood'}_ring_vs_fill"] = [
                    [round(float(x), 1) for x in ring_med], [round(float(x), 1) for x in fill_med]]
                if name == "material_map":                           # gloss must match, or the fill shines in spots
                    fill[steel == cls] += (ring_med - fill_med)[None, :]
        res = img * (1 - m[..., None]) + fill * m[..., None]
        out[name] = np.clip(res, 0, 255)
        bx0, by0 = BOX[0] - WIN[0], BOX[1] - WIN[1]
        Image.fromarray(out[name][by0:by0 + BOX[3] - BOX[1], bx0:bx0 + BOX[2] - BOX[0], :3].astype(np.uint8)).save(OUT / f"box_{name}_rgb.png")
        Image.fromarray(img[by0:by0 + BOX[3] - BOX[1], bx0:bx0 + BOX[2] - BOX[0], :3].astype(np.uint8)).save(OUT / f"box_{name}_stock_rgb.png")
        if name == "normal":
            Image.fromarray(out[name][by0:by0 + BOX[3] - BOX[1], bx0:bx0 + BOX[2] - BOX[0], 3].astype(np.uint8)).save(OUT / "box_normal_a.png")
            Image.fromarray(img[by0:by0 + BOX[3] - BOX[1], bx0:bx0 + BOX[2] - BOX[0], 3].astype(np.uint8)).save(OUT / "box_normal_stock_a.png")
    # write level 0 and the mips of the box
    bx0, by0 = BOX[0] - WIN[0], BOX[1] - WIN[1]
    bw, bh = BOX[2] - BOX[0], BOX[3] - BOX[1]
    mbox = m[by0:by0 + bh, bx0:bx0 + bw]
    for name in out:
        dds = Dds(stock(name))
        cur = out[name][by0:by0 + bh, bx0:bx0 + bw]
        mk = mbox
        levels = 0
        for level in range(dds.mips):
            s = 1 << level
            w_, h_ = bw // s, bh // s
            if w_ < 4 or h_ < 4 or w_ % 4 or h_ % 4:
                break
            x0, y0 = BOX[0] // s, BOX[1] // s
            if level:
                cur = cur.reshape(h_, 2, w_, 2, 4).mean((1, 3))
                mk = mk.reshape(h_, 2, w_, 2).max((1, 3))
            only = mk.reshape(h_ // 4, 4, w_ // 4, 4).max((1, 3)) > 0
            dds.write(level, x0, y0, np.clip(np.round(cur), 0, 255).astype(np.uint8), only=only)
            levels += 1
        dds.save(OUT / f"tww3_mtb_dwf_thunderbarge_grungni_01_{name}.dds")
        report[f"{name}_levels_written"] = levels
    (OUT / "fix_report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report))


if __name__ == "__main__" and sys.argv[1] == "fix":
    fix()
