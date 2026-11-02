"""Read entries of the game's own packs (PFH5, whole-file index, zstd or LZ4 per entry)."""
import struct
from pathlib import Path

from compression import zstd

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Total War WARHAMMER III")
DATA = GAME / "data"


def _lz4_block(src):
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        tok = src[i]
        i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break
        off = src[i] | src[i + 1] << 8
        i += 2
        m = tok & 15
        if m == 15:
            while True:
                b = src[i]
                i += 1
                m += b
                if b != 255:
                    break
        m += 4
        for _ in range(m):
            out.append(out[-off])
    return bytes(out)


def _lz4_frame(d):
    if d[:4] != b"\x04\x22\x4d\x18":
        raise ValueError("not an LZ4 frame")
    flags = d[4]
    p = 6 + (8 if flags & 8 else 0) + (4 if flags & 1 else 0) + 1
    out = bytearray()
    while True:
        size = struct.unpack_from("<I", d, p)[0]
        p += 4
        if size == 0:
            return bytes(out)
        raw = size & 0x80000000
        size &= 0x7fffffff
        block = d[p:p + size]
        p += size
        out += block if raw else _lz4_block(block)
        if flags & 0x10:
            p += 4


def _decompress(d):
    if d[4:8] == b"\x04\x22\x4d\x18":
        return _lz4_frame(d[4:])
    if d[4:8] == b"\x28\xb5\x2f\xfd":
        return zstd.decompress(d[4:])
    raise ValueError("unknown compression")


def entries(pack, want):
    """Yields (name, bytes) of the pack's entries whose name satisfies want(name)."""
    with open(pack, "rb") as f:
        magic, kind, _, dep_size, count, index_size, _ = struct.unpack("<4s6I", f.read(28))
        if magic != b"PFH5":
            raise ValueError(f"{pack}: not PFH5")
        ext = 20 if kind & 0x100 else 0
        f.read(ext)
        f.read(dep_size)
        index = f.read(index_size)
        pos, off = 0, 28 + ext + dep_size + index_size
        for _ in range(count):
            size = struct.unpack_from("<I", index, pos)[0]
            pos += 4 + (4 if kind & 0x40 else 0)
            compressed = index[pos]
            pos += 1
            end = index.index(0, pos)
            name = index[pos:end].decode("latin1")
            pos = end + 1
            if want(name):
                f.seek(off)
                d = f.read(size)
                yield name, _decompress(d) if compressed else d
            off += size
