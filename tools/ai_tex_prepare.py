"""Inputs for generation, all from the stock sheet, in straightened space: picture, mask, line guide, style sample, rough starts.
Writes build/solid_hull_ai/work/{wood,steel}_*.png. Venv python. Earlier scripted paint is not read."""
import json

import cv2
import numpy as np
from PIL import Image

from ai_tex_common import OUT, WORK, Zone, rect, rect_map

SCALE = 4
W, H = 1216, 832
z = Zone()
U0 = 908
C0 = {"wood": -112, "steel": 40}
# plank gaps found at each side of the zone: row at the left edge (u=962), row at the right edge (u=1158)
GAPS = [(-15.4, -14.9), (1.1, 3.4), (46.1, 48.9)]
# plate seams of the belt: found on the stock further along, every 82 columns; rows at their ends fixed by looking at the sheet
SEAMS = [984, 1066, 1148]
STEEL_TOP = 88.0
rng = np.random.default_rng(7)


def save(name, a):
    Image.fromarray(a).save(WORK / f"{name}.png")


def px(u, c, c0):
    return (u - U0) * SCALE, (c - c0) * SCALE


def maps_for(c0, du=0.0):
    return rect_map(z, U0 + du, U0 + du + W / SCALE, c0, c0 + H / SCALE, SCALE)


def row_lerp(pic, mask):
    """Each row of the hole runs from the row's colour left of the hole to the colour right of it."""
    out = pic.astype(np.float32).copy()
    for y in range(mask.shape[0]):
        xs = np.nonzero(mask[y])[0]
        if not len(xs):
            continue
        a, b = xs[0], xs[-1]
        L = pic[y, max(a - 30, 0):max(a - 2, 1)].astype(np.float32).mean(axis=0)
        R = pic[y, min(b + 3, W - 2):min(b + 30, W - 1)].astype(np.float32).mean(axis=0)
        t = np.clip((np.arange(W) - a) / max(b - a, 1), 0, 1)[..., None]
        out[y, a:b + 1] = (L * (1 - t) + R * t)[a:b + 1]
    return out


def guide(pic, mask, lines):
    grey = cv2.cvtColor(pic, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(grey, (5, 5), 0), 30, 90)
    edges[cv2.dilate(mask, np.ones((9, 9), np.uint8)) > 0] = 0
    inside = np.zeros_like(edges)
    for (x0, y0), (x1, y1) in lines:
        cv2.line(inside, (int(x0), int(y0)), (int(x1), int(y1)), 255, 1, cv2.LINE_AA)
    inside[cv2.dilate(mask, np.ones((9, 9), np.uint8)) == 0] = 0
    return cv2.max(edges, inside)


def run():
    meta = {"scale": SCALE, "w": W, "h": H, "u0": U0, "c0": C0}
    # ------ wood: mask is the whole zone in the wood's window; only its wood part is used afterwards
    c0 = C0["wood"]
    maps = maps_for(c0)
    pic = rect(z.base[..., :3], maps)
    mask = (rect((z.zone * 255).astype(np.uint8), maps, cv2.INTER_LINEAR) > 100).astype(np.uint8) * 255
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    save("wood_pic", pic)
    save("wood_mask", mask)
    lines = []
    for cl, cr in GAPS:
        slope = (cr - cl) / (1158 - 962)
        for off in (-1.0, 1.0):         # a gap is a thin dark line: two edges
            lines.append((px(800, cl + slope * (800 - 962) + off * 0.6, c0), px(1400, cl + slope * (1400 - 962) + off * 0.6, c0)))
    lines.append((px(800, STEEL_TOP, c0), px(1400, STEEL_TOP, c0)))
    save("wood_guide", guide(pic, mask, lines))
    # with straight strokes of grain between the gaps
    dashes = list(lines)
    for _ in range(26):
        u = rng.uniform(950, 1130)
        c = rng.uniform(-20, 86)
        length = rng.uniform(25, 90)
        dashes.append((px(u, c, c0), px(u + length, c + rng.uniform(-0.3, 0.3), c0)))
    save("wood_guide_grain", guide(pic, mask, dashes))
    fill = row_lerp(pic, mask)
    save("wood_init_rows", np.clip(fill, 0, 255).astype(np.uint8))
    other = rect(z.base[..., :3], maps_for(c0, 195.0))
    a = cv2.GaussianBlur(mask, (31, 31), 0)[..., None] / 255.0
    save("wood_init_shift", np.clip(pic * (1 - a) + other * a, 0, 255).astype(np.uint8))
    # style sample: strips of clean planks either side of the zone, same scale as the picture
    big = rect_map(z, 1160, 1416, -12, 87, SCALE)
    a1 = rect(z.base[..., :3], big)
    big = rect_map(z, 760, 960, -60, 40, SCALE)
    a2 = rect(z.base[..., :3], big)
    save("wood_style", np.vstack([a1[:396, :800], cv2.resize(a2, (800, 396))]))

    # ------ steel: same way
    c0 = C0["steel"]
    maps = maps_for(c0)
    pic = rect(z.base[..., :3], maps)
    mask = (rect(((z.zone & ~z.above) * 255).astype(np.uint8), maps, cv2.INTER_LINEAR) > 100).astype(np.uint8) * 255
    mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    save("steel_pic", pic)
    save("steel_mask", mask)
    other = rect(z.base[..., :3], maps_for(c0, 164.0))
    a = cv2.GaussianBlur(mask, (31, 31), 0)[..., None] / 255.0
    save("steel_init_shift", np.clip(pic * (1 - a) + other * a, 0, 255).astype(np.uint8))
    big = rect_map(z, 1160, 1416, 91, 160, SCALE)
    s1 = rect(z.base[..., :3], big)
    save("steel_style", cv2.resize(s1, (1024, 552)))
    (OUT / "work" / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    # to look at
    sheet = np.vstack([np.hstack([np.array(Image.open(WORK / f"{n}.png").convert("RGB")) for n in row]) for row in (("wood_pic", "wood_guide_grain"), ("wood_init_rows", "wood_init_shift"), ("steel_pic", "steel_init_shift"))])
    save("prepare_view", cv2.resize(sheet, None, fx=0.45, fy=0.45, interpolation=cv2.INTER_AREA))


if __name__ == "__main__":
    run()
