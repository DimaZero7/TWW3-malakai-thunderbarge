"""Copies entries of the game's packs into build/crew_cards_cache. Needs py -3.14 (zstd): py -3.14 tools/crew_cards_fetch.py <path> ...

Paths: lowercase, backslashes, as in the packs. Own reader because gamepack.py does not follow linked LZ4 blocks. With ?a+b+c it lists the names holding all the parts.
"""
import json
import struct
import sys
from compression import zstd
from pathlib import Path

DATA = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Total War WARHAMMER III\data")
CACHE = Path(__file__).resolve().parent.parent / "build" / "crew_cards_cache"
SKIP = ("audio", "local_", "tile", "terrain", "movies", "vfx", "shaders", "skyboxes", "vegetation", "tcamp")


def pack_index(pack):
    with open(pack, "rb") as f:
        _, kind, _, dep_size, count, index_size, _ = struct.unpack("<4s6I", f.read(28))
        ext = 20 if kind & 0x100 else 0
        f.read(ext + dep_size)
        idx = f.read(index_size)
    pos, off, out = 0, 28 + ext + dep_size + index_size, []
    for _ in range(count):
        size = struct.unpack_from("<I", idx, pos)[0]
        pos += 4 + (4 if kind & 0x40 else 0)
        comp = idx[pos]
        pos += 1
        end = idx.index(0, pos)
        out.append((idx[pos:end].decode("latin1"), off, size, comp))
        pos = end + 1
        off += size
    return out


def index():
    path = CACHE / "index.json"
    if path.exists():
        return json.loads(path.read_text())
    names = {}
    for pack in sorted(DATA.glob("*.pack")):
        if not pack.name.startswith(SKIP):
            for n, off, size, comp in pack_index(pack):
                names.setdefault(n.lower(), (pack.name, off, size, comp))
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(names))
    return names


def lz4_frame(d):
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
        if raw:
            out += block
        else:
            i, n = 0, len(block)
            while i < n:
                tok = block[i]
                i += 1
                lit = tok >> 4
                if lit == 15:
                    while True:
                        b = block[i]
                        i += 1
                        lit += b
                        if b != 255:
                            break
                out += block[i:i + lit]
                i += lit
                if i >= n:
                    break
                off = block[i] | block[i + 1] << 8
                i += 2
                m = tok & 15
                if m == 15:
                    while True:
                        b = block[i]
                        i += 1
                        m += b
                        if b != 255:
                            break
                m += 4
                for _ in range(m):
                    out.append(out[-off])
        if flags & 0x10:
            p += 4


def read(entry):
    pack, off, size, comp = entry
    with open(DATA / pack, "rb") as f:
        f.seek(off)
        d = f.read(size)
    if not comp:
        return d
    return lz4_frame(d[4:]) if d[4:8] == b"\x04\x22\x4d\x18" else zstd.decompress(d[4:])


def main():
    idx = index()
    for a in sys.argv[1:]:
        if a.startswith("?"):
            for k in idx:
                if all(w in k for w in a[1:].split("+")):
                    print(k, idx[k][2])
            continue
        key = a.lower().replace("/", "\\")
        if key not in idx:
            print("MISSING", key)
            continue
        out = CACHE / key.replace("\\", "__")
        if not out.exists():
            out.write_bytes(read(idx[key]))


if __name__ == "__main__":
    main()
