"""Reads and rewrites parts of the game's BC1 and BC3 DDS files, numpy only. Everything outside the rewritten blocks stays the same bytes, so header, format and mip count are the stock file's.

  dds = Dds(path)
  rgba = dds.read(level, x0, y0, x1, y1)      # uint8 array, h x w x 4, in file units (no colour conversion); the box is rounded out to blocks by the caller
  dds.write(level, x0, y0, rgba)              # x0, y0 multiples of 4; rgba size multiples of 4
  dds.save(path)
"""
import struct

import numpy as np


class Dds:
    def __init__(self, path):
        self.b = bytearray(open(path, "rb").read())
        self.h, self.w = struct.unpack_from("<II", self.b, 12)
        self.mips = struct.unpack_from("<I", self.b, 28)[0]
        four = bytes(self.b[84:88])
        self.base = 128
        if four == b"DX10":
            dxgi = struct.unpack_from("<I", self.b, 128)[0]
            self.base = 148
            self.kind = {70: 1, 71: 1, 72: 1, 76: 3, 77: 3, 78: 3}[dxgi]
            self.dxgi = dxgi
        else:
            self.kind = {b"DXT1": 1, b"DXT5": 3}[four]
            self.dxgi = None
        self.block = 8 if self.kind == 1 else 16
        self.offsets = []
        at = self.base
        w, h = self.w, self.h
        for _ in range(self.mips):
            self.offsets.append((at, w, h))
            at += ((w + 3) // 4) * ((h + 3) // 4) * self.block
            w, h = max(1, w // 2), max(1, h // 2)

    def level_size(self, level):
        return self.offsets[level][1:]

    def _blocks(self, level, bx0, by0, bx1, by1):
        at, w, h = self.offsets[level]
        per_row = (w + 3) // 4
        rows = []
        for by in range(by0, by1):
            start = at + (by * per_row + bx0) * self.block
            rows.append(np.frombuffer(self.b, np.uint8, (bx1 - bx0) * self.block, start))
        return np.stack(rows).reshape(by1 - by0, bx1 - bx0, self.block)

    def read(self, level, x0, y0, x1, y1):
        """Pixels of a box aligned to blocks."""
        bx0, by0, bx1, by1 = x0 // 4, y0 // 4, (x1 + 3) // 4, (y1 + 3) // 4
        raw = self._blocks(level, bx0, by0, bx1, by1).reshape(-1, self.block)
        colour = raw if self.kind == 1 else raw[:, 8:]
        rgb, a3 = _decode_colour(colour)
        if self.kind == 3:
            alpha = _decode_alpha(raw[:, :8])
        else:
            alpha = a3
        px = np.concatenate((rgb, alpha[..., None]), axis=2)     # n x 16 x 4
        n = (by1 - by0, bx1 - bx0)
        px = px.reshape(n[0], n[1], 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(n[0] * 4, n[1] * 4, 4)
        return px

    def write(self, level, x0, y0, rgba, only=None):
        """rgba: pixels of a box aligned to blocks. only: bool array by block, which blocks are written; others keep their bytes."""
        h, w = rgba.shape[:2]
        n = (h // 4, w // 4)
        px = rgba.reshape(n[0], 4, n[1], 4, 4).transpose(0, 2, 1, 3, 4).reshape(-1, 16, 4).astype(np.float32)
        colour = _encode_colour(px[..., :3])
        raw = colour if self.kind == 1 else np.concatenate((_encode_alpha(px[..., 3]), colour), axis=1)
        raw = raw.reshape(n[0], n[1], self.block)
        at, tw, _ = self.offsets[level]
        per_row = (tw + 3) // 4
        bx0, by0 = x0 // 4, y0 // 4
        for by in range(n[0]):
            for bx in range(n[1]):
                if only is None or only[by, bx]:
                    start = at + ((by0 + by) * per_row + bx0 + bx) * self.block
                    self.b[start:start + self.block] = raw[by, bx].tobytes()

    def save(self, path):
        with open(path, "wb") as f:
            f.write(self.b)


def _565(c):
    r = ((c >> 11) & 31) * 255 // 31
    g = ((c >> 5) & 63) * 255 // 63
    b = (c & 31) * 255 // 31
    return np.stack((r, g, b), axis=-1).astype(np.int32)


def _decode_colour(raw):
    c0 = raw[:, 0].astype(np.int32) | raw[:, 1].astype(np.int32) << 8
    c1 = raw[:, 2].astype(np.int32) | raw[:, 3].astype(np.int32) << 8
    bits = raw[:, 4].astype(np.int64) | raw[:, 5].astype(np.int64) << 8 | raw[:, 6].astype(np.int64) << 16 | raw[:, 7].astype(np.int64) << 24
    a, b = _565(c0), _565(c1)
    four = (c0 > c1)[:, None]
    p2 = np.where(four, (2 * a + b) // 3, (a + b) // 2)
    p3 = np.where(four, (a + 2 * b) // 3, 0)
    table = np.stack((a, b, p2, p3), axis=1)
    idx = np.stack([(bits >> (2 * i)) & 3 for i in range(16)], axis=1)
    rgb = np.take_along_axis(table, idx[..., None], axis=1).astype(np.uint8)
    alpha = np.where((~four) & (idx == 3), 0, 255).astype(np.uint8)
    return rgb, alpha


def _decode_alpha(raw):
    a0, a1 = raw[:, 0].astype(np.int32), raw[:, 1].astype(np.int32)
    bits = np.zeros(len(raw), np.int64)
    for i in range(6):
        bits |= raw[:, 2 + i].astype(np.int64) << (8 * i)
    idx = np.stack([(bits >> (3 * i)) & 7 for i in range(16)], axis=1)
    table = np.zeros((len(raw), 8), np.int32)
    table[:, 0], table[:, 1] = a0, a1
    eight = a0 > a1
    for k in range(2, 8):
        table[:, k] = np.where(eight, ((8 - k) * a0 + (k - 1) * a1) // 7, 0)
    for k in range(2, 6):
        table[:, k] = np.where(eight, table[:, k], ((6 - k) * a0 + (k - 1) * a1) // 5)
    table[:, 6] = np.where(eight, table[:, 6], 0)
    table[:, 7] = np.where(eight, table[:, 7], 255)
    return np.take_along_axis(table, idx, axis=1).astype(np.uint8)


def _encode_colour(px):
    """n x 16 x 3 floats, 0..255 -> n x 8 bytes, 4 colour blocks: the block's main axis, ends refined by a least squares step."""
    n = len(px)
    mean = px.mean(axis=1, keepdims=True)
    d = px - mean
    cov = np.einsum("nij,nik->njk", d, d)
    axis = np.ones((n, 3), np.float32)
    for _ in range(8):
        axis = np.einsum("njk,nk->nj", cov, axis)
        axis /= np.linalg.norm(axis, axis=1, keepdims=True) + 1e-6
    t = np.einsum("nij,nj->ni", d, axis)
    lo = mean[:, 0] + t.min(axis=1, keepdims=True) * axis
    hi = mean[:, 0] + t.max(axis=1, keepdims=True) * axis
    weights = np.array((0.0, 1 / 3, 2 / 3, 1.0), np.float32)
    for _ in range(2):      # nearest of the four, then the best ends for that choice
        span = hi - lo
        f = np.einsum("nij,nj->ni", px - lo[:, None], span) / (np.einsum("nj,nj->n", span, span)[:, None] + 1e-6)
        w = weights[np.clip(np.rint(f * 3).astype(int), 0, 3)]
        a, b = (1 - w), w
        aa, ab, bb = (a * a).sum(1), (a * b).sum(1), (b * b).sum(1)
        ax = np.einsum("ni,nij->nj", a, px)
        bx = np.einsum("ni,nij->nj", b, px)
        det = aa * bb - ab * ab
        ok = np.abs(det) > 1e-6
        safe = np.where(ok, det, 1.0)
        new_lo = (bb[:, None] * ax - ab[:, None] * bx) / safe[:, None]
        new_hi = (aa[:, None] * bx - ab[:, None] * ax) / safe[:, None]
        lo = np.where(ok[:, None], new_lo, lo)
        hi = np.where(ok[:, None], new_hi, hi)
    q = lambda c: ((np.clip(np.rint(c[:, 0] * 31 / 255), 0, 31).astype(np.int32) << 11)
                   | (np.clip(np.rint(c[:, 1] * 63 / 255), 0, 63).astype(np.int32) << 5)
                   | np.clip(np.rint(c[:, 2] * 31 / 255), 0, 31).astype(np.int32))
    c0, c1 = q(hi), q(lo)
    swap = c0 < c1
    c0, c1 = np.where(swap, c1, c0), np.where(swap, c0, c1)
    # the same as the decoder: c0 == c1 would be the 3 colour mode, whose index 3 is transparent; index 0 there is right for all
    a, b = _565(c0), _565(c1)
    table = np.stack((a, b, (2 * a + b) // 3, (a + 2 * b) // 3), axis=1).astype(np.float32)
    dist = ((px[:, :, None, :] - table[:, None, :, :]) ** 2).sum(axis=3)
    idx = dist.argmin(axis=2)
    idx = np.where((c0 == c1)[:, None], 0, idx)
    bits = (idx.astype(np.int64) << (2 * np.arange(16))).sum(axis=1)
    out = np.zeros((n, 8), np.uint8)
    out[:, 0], out[:, 1], out[:, 2], out[:, 3] = c0 & 255, c0 >> 8, c1 & 255, c1 >> 8
    for i in range(4):
        out[:, 4 + i] = (bits >> (8 * i)) & 255
    return out


def _encode_alpha(alpha):
    """n x 16 floats -> n x 8 bytes, the 8 value mode."""
    n = len(alpha)
    a0 = np.clip(np.rint(alpha.max(axis=1)), 0, 255).astype(np.int32)
    a1 = np.clip(np.rint(alpha.min(axis=1)), 0, 255).astype(np.int32)
    same = a0 == a1
    a0 = np.where(same & (a0 < 255), a0 + 1, a0)
    a1 = np.where(same & (a0 == a1), a1 - 1, a1)
    table = np.zeros((n, 8), np.float32)
    table[:, 0], table[:, 1] = a0, a1
    for k in range(2, 8):
        table[:, k] = ((8 - k) * a0 + (k - 1) * a1) // 7
    idx = np.abs(alpha[:, :, None] - table[:, None, :]).argmin(axis=2)
    bits = (idx.astype(np.int64) << (3 * np.arange(16))).sum(axis=1)
    out = np.zeros((n, 8), np.uint8)
    out[:, 0], out[:, 1] = a0, a1
    for i in range(6):
        out[:, 2 + i] = (bits >> (8 * i)) & 255
    return out
