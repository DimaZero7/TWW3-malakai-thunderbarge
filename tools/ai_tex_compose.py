"""From a generated picture back to the sheet: straightened space to pixels of the box, seam pass, normals and material map. Venv python.

Seam: the difference to the stock along the zone's outer edge (low frequencies only) is spread over the zone by a membrane, so colour runs on without a feathered band. The port's outer ring and the porthole do not count as edge.
Normals and material map: a small filter learned from this sheet, from a patch of the colour to the stock's channel, separately for planks and for steel, then the same seam pass.
"""
import json

import cv2
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spl
from PIL import Image

from ai_tex_common import OUT, WORK, Zone, unrect_coords

GEN = WORK / "gen"
RAMP = 10.0
z = Zone()
meta = json.loads((WORK / "meta.json").read_text(encoding="utf-8"))
SCALE, U0 = meta["scale"], meta["u0"]


def load(name):
    return np.array(Image.open(GEN / f"{name}.png").convert("RGB")).astype(np.float32)


def to_box(img, kind):
    """A straightened picture to pixels of the box, anti-aliased."""
    blur = cv2.GaussianBlur(img, (0, 0), SCALE * 0.3)
    mx, my = unrect_coords(z, U0, meta["c0"][kind], SCALE)
    return cv2.remap(blur, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def membrane(diff, region, known):
    """Laplace solve over region; values fixed where known; neighbours neither in region nor known are free."""
    idx = -np.ones(region.shape, int)
    ys, xs = np.nonzero(region)
    idx[ys, xs] = np.arange(len(ys))
    rows, cols, vals, rhs_i, rhs_v = [], [], [], [], []
    b = np.zeros((len(ys), diff.shape[2]))
    for k, (y, x) in enumerate(zip(ys, xs)):
        deg = 0
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if region[ny, nx]:
                rows.append(k), cols.append(idx[ny, nx]), vals.append(-1.0)
                deg += 1
            elif known[ny, nx]:
                b[k] += diff[ny, nx]
                deg += 1
        rows.append(k), cols.append(k), vals.append(max(deg, 1) + 1e-3)
    A = sp.csc_matrix((vals, (rows, cols)), shape=(len(ys), len(ys)))
    lu = spl.splu(A)
    out = np.zeros(diff.shape, np.float32)
    for ch in range(diff.shape[2]):
        out[ys, xs, ch] = lu.solve(b[:, ch])
    return out


def seam(painted, stock, region, sigma=2.5, limit=45.0):
    """painted, stock: h x w x n. Returns painted with the membrane added inside region. Pixels of the ring keep out of the edge."""
    ring = np.hypot(z.uu - z.ring[0], z.vv - z.ring[1]) < z.ring[2] + 2.5
    other = z.zone & ~region
    known = ~region & ~other & ~ring
    # blur each side only over its own valid pixels
    def soft(img, valid):
        w = cv2.GaussianBlur(valid.astype(np.float32), (0, 0), sigma)[..., None]
        v = cv2.GaussianBlur(img * valid[..., None].astype(np.float32), (0, 0), sigma)
        if v.ndim == 2:
            v = v[..., None]
        return v / np.maximum(w, 1e-3)
    a = soft(stock, known & ~region)
    # the painted picture also exists outside the zone (it was generated over context), so compare it there
    outside_band = cv2.dilate(region.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & known
    b = soft(painted, region | outside_band)
    diff = np.clip(a - b, -limit, limit)
    fix = membrane(diff, region, known)
    out = stock.copy()
    # the zone's outer margin is clean stock wood or steel: fade into it over its outer RAMP pixels
    alpha = np.clip(z.depth / RAMP, 0, 1)[..., None]
    alpha = alpha * alpha * (3 - 2 * alpha)
    out[region] = (stock * (1 - alpha) + (painted + fix) * alpha)[region]
    return out


def match_grain(painted, stock, region, sample, cap=1.4):
    """Same strength of fine detail as the stock planks or steel around."""
    def hf(img):
        return img - cv2.GaussianBlur(img, (0, 0), 6)
    gain = hf(stock)[sample].std(axis=0) / np.maximum(hf(painted)[region].std(axis=0), 1e-3)
    gain = np.clip(gain, 0.6, cap)
    low = cv2.GaussianBlur(painted, (0, 0), 6)
    return low + hf(painted) * gain, gain


def samples():
    """Clean stock areas used as examples: planks and steel, without the ring, the porthole, the zone and things on the sheet that are neither."""
    near = cv2.dilate(z.zone.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    hole = np.hypot(z.uu - z.ring[0], z.vv - z.ring[1]) < z.ring[2] + 5
    wood = (z.uu > 930) & (z.uu < 1400) & (z.c > -105) & (z.c < 84) & ~near & ~hole
    steel = (z.uu > 1130) & (z.uu < 1400) & (z.c > 92) & (z.c < 135) & ~near
    return wood, steel


def learn(colour, target, sample, size=5, count=120000, seed=3):
    """Ridge from a size x size patch of RGB + a wider gray window to the target's channels. Returns predict(colour) and the fit's R2."""
    rng = np.random.default_rng(seed)
    grey = colour.mean(axis=2)
    ys, xs = np.nonzero(sample)
    pick = rng.choice(len(ys), min(count, len(ys)), replace=False)
    R = size // 2
    offs = [(dy, dx) for dy in range(-R, R + 1) for dx in range(-R, R + 1)]
    def features(ys_, xs_):
        f = [grey[ys_ + dy, xs_ + dx] for dy, dx in offs] + [colour[ys_, xs_, c] for c in range(3)]
        return np.stack(f, axis=1) / 255.0
    X = features(ys[pick], xs[pick])
    Y = target[ys[pick], xs[pick]].astype(np.float32)
    mx, my = X.mean(axis=0), Y.mean(axis=0)
    Xc = X - mx
    A = Xc.T @ Xc + np.eye(X.shape[1]) * 1e-2
    w = np.linalg.solve(A, Xc.T @ (Y - my))
    pred = Xc @ w + my
    r2 = 1 - ((Y - pred) ** 2).sum(axis=0) / np.maximum(((Y - my) ** 2).sum(axis=0), 1e-6)
    def predict(col, ys_, xs_):
        g2 = col.mean(axis=2)
        f = [g2[ys_ + dy, xs_ + dx] for dy, dx in offs] + [col[ys_, xs_, c] for c in range(3)]
        Xn = np.stack(f, axis=1) / 255.0
        return (Xn - mx) @ w + my
    return predict, r2


def compose(wood=None, steel=None, base=None):
    """base: pixels of the box to start from (default stock). Returns colour of the box (float h x w x 4), a report."""
    stock = z.base.astype(np.float32)
    out = (stock if base is None else base).copy()
    wood_s, steel_s = samples()
    report = {}
    if wood is not None:
        box = to_box(load(wood), "wood")
        region = z.zone & z.above
        box, gain = match_grain(box, stock[..., :3], region, wood_s)
        report["wood_gain"] = gain.tolist()
        out[..., :3] = seam(box, out[..., :3], region)
    if steel is not None:
        box = to_box(load(steel), "steel")
        region = z.zone & ~z.above
        box, gain = match_grain(box, stock[..., :3], region, steel_s)
        report["steel_gain"] = gain.tolist()
        # steel is grey on the stock: keep the generated brightness, take the colour cast of the steel around
        lum = box.mean(axis=2, keepdims=True)
        cast = (stock[..., :3][steel_s] - stock[..., :3][steel_s].mean(axis=1, keepdims=True)).mean(axis=0)
        box = lum + cast
        out[..., :3] = seam(box, out[..., :3], region)
        # the belt's top edge: generated steel draws it a little ragged, so smooth it along the edge (it runs nearly along u here)
        edge = (cv2.distanceTransform((~z.above).astype(np.uint8), cv2.DIST_L2, 3) < 3.5) & region
        along = cv2.blur(out[..., :3], (7, 1))
        out[..., :3][edge] = along[edge]
    return np.clip(out, 0, 255), report


def maps(colour):
    """Normal and material map of the zone from the final colour. Returns dict of box arrays, and fit quality per channel."""
    wood_s, steel_s = samples()
    stock_col = z.base[..., :3].astype(np.float32)
    res, report = {}, {}
    for name, stock_map, chans in (("normal", z.normal, (1, 3)), ("material_map", z.matmap, (0, 1))):
        out = stock_map.astype(np.float32).copy()
        for kind, sample, region in (("wood", wood_s, z.zone & z.above), ("steel", steel_s, z.zone & ~z.above)):
            target = stock_map[..., chans]
            predict, r2 = learn(stock_col, target, sample)
            ys, xs = np.nonzero(region)
            pred = predict(colour[..., :3], ys, xs)
            layer = out[..., chans].copy()
            layer[ys, xs] = pred
            if name == "material_map":
                band = cv2.dilate(region.astype(np.uint8), np.ones((31, 31), np.uint8)).astype(bool) & ~z.zone & (z.above if kind == "wood" else ~z.above)
                band &= np.hypot(z.uu - z.ring[0], z.vv - z.ring[1]) > z.ring[2] + 5
                # the fit smears sparse values (metal in scratches) into a grey film: give it the stock's distribution of values, in the fit's order
                for j, ch in enumerate(chans):
                    ref = np.sort(stock_map[..., ch][band].astype(np.float32))
                    order = np.argsort(np.argsort(pred[:, j]))
                    layer[ys, xs, j] = ref[(order * (len(ref) - 1) / max(len(order) - 1, 1)).astype(int)]
            if name == "normal":
                # the fit keeps only what the colour explains, so it comes out flat: bring its fine detail up to the stock's strength
                boosted, g = match_grain(layer, stock_map[..., chans].astype(np.float32), region, sample, cap=3.0)
                layer[ys, xs] = boosted[ys, xs]
                report[f"{name}_{kind}_detail_gain"] = [round(float(x), 2) for x in g]
            fixed = seam(layer, out[..., chans], region)
            out[..., chans[0]], out[..., chans[1]] = fixed[..., 0], fixed[..., 1]
            report[f"{name}_{kind}_r2"] = [round(float(x), 3) for x in r2]
        res[name] = np.clip(out, 0, 255)
    return res, report


def crop_box(img, pad=30):
    ys, xs = np.nonzero(z.zone)
    return img[ys.min() - pad:ys.max() + pad, xs.min() - pad:xs.max() + pad]
