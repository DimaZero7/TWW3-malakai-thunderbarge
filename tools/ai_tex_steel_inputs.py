"""Inputs of the steel pass, with the chosen planks already in place above the belt: venv python, ai_tex_steel_inputs.py WOOD_NAME"""
import sys

import cv2
import numpy as np
from PIL import Image

import ai_tex_compose as ac
import ai_tex_prepare as ap
from ai_tex_common import WORK, rect, rect_map

z = ac.z
colour, _ = ac.compose(wood=sys.argv[1])
c0 = ap.C0["steel"]
maps = ap.maps_for(c0)
pic = rect(np.clip(colour[..., :3], 0, 255).astype(np.uint8), maps)
mask = (rect(((z.zone & ~z.above) * 255).astype(np.uint8), maps, cv2.INTER_LINEAR) > 100).astype(np.uint8) * 255
mask = cv2.dilate(mask, np.ones((5, 5), np.uint8))
ap.save("steel_pic", pic)
ap.save("steel_mask", mask)

# the seam below the zone, carried straight up
ref = rect(z.base[..., :3], maps).astype(np.float32).mean(axis=2)
points = []
for c in range(166, 200, 3):
    y = int((c - c0) * ap.SCALE)
    a, b = int((1035 - ap.U0) * ap.SCALE), int((1080 - ap.U0) * ap.SCALE)
    row = cv2.GaussianBlur(ref[y - 3:y + 4, a:b], (9, 1), 0).mean(axis=0)
    points.append((c, ap.U0 + (a + int(row.argmax())) / ap.SCALE))
points = np.array(points)
k, m = np.polyfit(points[:, 0], points[:, 1], 1)
print("seam at c=165:", k * 165 + m, "c=92:", k * 92 + m, "slope", k, "points", points[:3].tolist())
top, bottom = 90.0, 170.0
lines = []
for off in (-0.8, 0.8):
    lines.append((ap.px(k * top + m + off, top, c0), ap.px(k * bottom + m + off, bottom, c0)))
guide = ap.guide(pic, mask, lines)
# the belt's edge where the zone's split runs, not a straight row
belt = rect((z.above * 255).astype(np.uint8), maps, cv2.INTER_LINEAR)
edge = cv2.Canny(belt, 60, 180)
edge[cv2.dilate(mask, np.ones((9, 9), np.uint8)) == 0] = 0
guide = cv2.max(guide, edge)
for du in (-9.5, 9.5):
    x, y = ap.px(k * 97 + m + du, 97, c0)
    cv2.circle(guide, (int(x), int(y)), 10, 255, 1, cv2.LINE_AA)
ap.save("steel_guide", guide)

# rough start: the same rows of plates further along (the same seam lands at the same place)
sources = []
for shift in (190.0, 164.0):
    sources.append(rect(z.base[..., :3], ap.maps_for(c0, shift)).astype(np.float32))
split = int((1040 - ap.U0) * ap.SCALE)
t = np.clip((np.arange(ap.W) - split) / 40.0 + 0.5, 0, 1)[None, :, None]
other = sources[0] * (1 - t) + sources[1] * t
a = cv2.GaussianBlur(mask, (21, 21), 0)[..., None] / 255.0
ap.save("steel_init_shift", np.clip(pic * (1 - a) + other * a, 0, 255).astype(np.uint8))
ap.save("steel_init", np.clip(ap.row_lerp(pic, mask), 0, 255).astype(np.uint8))
sheet = np.hstack([np.array(Image.open(WORK / f"{n}.png").convert("RGB")) for n in ("steel_pic", "steel_guide", "steel_init")])
ap.save("steel_inputs_view", cv2.resize(sheet, None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA))
