"""Shared data of the AI texture test: the zone, and the planks straightened (x along the row, y across the rows), so generation sees straight rows. Run with the ComfyUI venv's python."""
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "build" / "solid_hull_ai"
WORK = OUT / "work"
WORK.mkdir(parents=True, exist_ok=True)


class Zone:
    def __init__(self):
        z = np.load(OUT / "zone.npz")
        self.box = [int(x) for x in z["box"]]
        self.x0, self.y0, self.x1, self.y1 = self.box
        self.zone, self.above, self.depth, self.c = z["zone"], z["above"], z["depth"], z["wood_c"].astype(np.float32)
        self.belt_v = z["belt_v"].astype(np.float32)   # v of the belt's edge for every u of the box
        self.ring = z["ring"]
        self.shift = float(z["shift"])
        self.h, self.w = self.zone.shape
        self.vv, self.uu = np.mgrid[self.y0:self.y1, self.x0:self.x1].astype(np.float32)
        self.base = np.load(OUT / "stock_base_colour.npy")
        self.normal = np.load(OUT / "stock_normal.npy")
        self.matmap = np.load(OUT / "stock_material_map.npy")
        self.mask = np.load(OUT / "stock_mask.npy")

    def v_of(self, u, c):
        """v for sheet column u (array of ints inside the box) and row c: the rows are monotonic in v in each column."""
        out = np.zeros(np.broadcast(u, c).shape, np.float32)
        ub, cb = np.broadcast_arrays(u, c)
        for col in np.unique(ub):
            i = int(col) - self.x0
            s = ub == col
            out[s] = np.interp(cb[s], self.c[:, i], self.vv[:, i])
        return out


def rect_map(zone, u0, u1, c0, c1, scale):
    """cv2.remap maps from straightened pixels to pixels of the box."""
    W, H = int((u1 - u0) * scale), int((c1 - c0) * scale)
    xs = u0 + (np.arange(W) + 0.5) / scale
    ys = c0 + (np.arange(H) + 0.5) / scale
    mapx = np.tile(xs, (H, 1)).astype(np.float32)
    mapy = np.zeros((H, W), np.float32)
    for k in range(W):
        fu = xs[k]
        i = int(np.clip(fu - zone.x0, 0, zone.w - 2))
        t = fu - zone.x0 - i
        col = zone.c[:, i] * (1 - t) + zone.c[:, i + 1] * t
        mapy[:, k] = np.interp(ys, col, zone.vv[:, i])
    return mapx - zone.x0, mapy - zone.y0


def rect(img, maps, interp=cv2.INTER_CUBIC):
    return cv2.remap(img, maps[0], maps[1], interp, borderMode=cv2.BORDER_REPLICATE)


def unrect_coords(zone, u0, c0, scale):
    """For every box pixel: where it lies in the straightened picture."""
    return ((zone.uu - u0) * scale).astype(np.float32), ((zone.c - c0) * scale).astype(np.float32)
