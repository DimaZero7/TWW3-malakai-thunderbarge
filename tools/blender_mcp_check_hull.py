"""Reads the written hull and compares it with the stock one: py -3.14 tools/blender_mcp_check_hull.py"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import rmv2  # noqa: E402

STOCK = REPO / "build/solid_hull_mcp/stock/dwf_thunderbarge_01.rigid_model_v2"
NEW = REPO / "build/solid_hull_mcp/dwf_thunderbarge_01.rigid_model_v2"
HOLE = {"+x": (0.9, 0.45, 5.0, 2.05, 2.0, 6.5), "-x": (-2.05, 0.45, 5.0, -0.9, 2.0, 6.5)}


def num(b, a, n):
    return [b[a + i] / 127.5 - 1 for i in range(n)]


def unit(v):
    d = sum(c * c for c in v) ** 0.5 or 1
    return [c / d for c in v]


def faces(m):
    out = []
    for t in m.tris:
        a, b, c = [(m.verts[i].x, m.verts[i].y, m.verts[i].z) for i in t]
        e, f = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)]
        out.append(((e[1] * f[2] - e[2] * f[1], e[2] * f[0] - e[0] * f[2], e[0] * f[1] - e[1] * f[0]), t))
    return out


def open_in(m, box, digits=3):
    key = [tuple(round(c, digits) for c in (v.x, v.y, v.z)) for v in m.verts]
    count = {}
    for t in m.tris:
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            ka, kb = key[a], key[b]
            if ka != kb:
                k = (ka, kb) if ka < kb else (kb, ka)
                count[k] = count.get(k, 0) + 1
    return [k for k, n in count.items() if n != 2 and all(box[i] <= p[i] <= box[i + 3] for p in k for i in range(3))]


old, new = rmv2.load(STOCK.read_bytes()), rmv2.load(NEW.read_bytes())
print("version", old["version"], new["version"], "| skeleton", old["skeleton"], new["skeleton"], "| LODs", len(old["lods"]), len(new["lods"]))
print("LOD headers same:", old["lod_headers"] == new["lod_headers"])
for li, (lo, ln) in enumerate(zip(old["lods"], new["lods"])):
    print(f"LOD{li} meshes {len(lo)} {len(ln)}, hull verts {len(lo[0].verts)} -> {len(ln[0].verts)}, tris {len(lo[0].tris)} -> {len(ln[0].tris)};",
          "all meshes tris", sum(len(m.tris) for m in lo), "->", sum(len(m.tris) for m in ln), "verts", sum(len(m.verts) for m in lo), "->", sum(len(m.verts) for m in ln))
    for mi, (a, b) in enumerate(zip(lo, ln)):
        same = (a.fixed == b.fixed, a.attachments == b.attachments, a.textures == b.textures, a.strings == b.strings, a.extra == b.extra, a.vertex_type == b.vertex_type, a.flag == b.flag, a.render == b.render, a.head_tail == b.head_tail)
        if not all(same):
            print("  material differs", mi, same)
        if mi and ([(v.pack()) for v in a.verts] != [(v.pack()) for v in b.verts] or a.tris != b.tris):
            print("  other mesh changed", mi)
    m, s = ln[0], lo[0]
    print("  open edges in the port's box:", {k: len(open_in(m, b)) for k, b in HOLE.items()}, "stock:", {k: len(open_in(s, b)) for k, b in HOLE.items()})
    # stock vertices left, plug vertices
    packed = {v.pack() for v in s.verts}
    plug = [i for i, v in enumerate(m.verts) if v.pack() not in packed]
    at = 4 if len(m.verts[0].rest) == 24 else 0
    pset = set(plug)
    bad_wind = total = 0
    dots_n, tan_up, bit_up = [], [], []
    for fn, t in faces(m):
        if all(i in pset for i in t):
            n = unit(num(m.verts[t[0]].rest, at, 3))
            total += 1
            if sum(a * b for a, b in zip(fn, n)) <= 0:
                bad_wind += 1
    bones = {(m.verts[i].bone0, m.verts[i].bone1, m.verts[i].weight0, m.verts[i].weight1, m.verts[i].rest[:at] if at else b"") for i in plug}
    stock_near = {(v.bone0, v.bone1, v.weight0, v.weight1, v.rest[:at] if at else b"") for v in s.verts if any(all(b[k] - 0.8 <= c <= b[k + 3] + 0.8 for k, c in enumerate((v.x, v.y, v.z))) for b in HOLE.values())}
    print(f"  changed or new vertices {len(plug)}; plug faces wrong way {bad_wind} of {total}; weights in plug {len(bones)}, all among the hull's near the port: {bones <= stock_near}")
    # normals and tangents: length and squareness on the new vertices
    worst = 0
    for i in plug:
        r = m.verts[i].rest
        n, tg, bt = unit(num(r, at, 3)), unit(num(r, at + 8, 3)), unit(num(r, at + 12, 3))
        worst = max(worst, abs(sum(a * b for a, b in zip(n, tg))), abs(sum(a * b for a, b in zip(n, bt))))
    print(f"  worst normal-tangent dot {worst:.3f}; uv range", [round(min(rmv2_u for rmv2_u in (__import__('struct').unpack_from('<2e', m.verts[i].rest, at + 4)[k] for i in plug)), 3) for k in (0, 1)], [round(max(__import__('struct').unpack_from('<2e', m.verts[i].rest, at + 4)[k] for i in plug), 3) for k in (0, 1)])
