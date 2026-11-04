"""Reads the written models back and compares them with the stock file: py -3.14 tools/blender_solid_hull_check.py

Skeleton, version, LOD headers, mesh count and everything in a mesh but the geometry must be the same bytes. All vertices of the hull must sit on the bones the stock hull's sit on.
The hole: in each LOD no edge with one triangle remains near the port, and the edges of the new piece are shared with the hull's triangles (no crack).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rmv2

REPO = Path(__file__).resolve().parent.parent
FOLDER = REPO / "build" / "solid_hull" / "warmachines" / "aircraft" / "dwf_thunderbarge"
stock = rmv2.load((REPO / "build" / "solid_hull" / "game" / "stock.rigid_model_v2").read_bytes())


def open_edges(mesh, near):
    ids, weld = {}, []
    for v in mesh.verts:
        weld.append(ids.setdefault((round(v.x, 3), round(v.y, 3), round(v.z, 3)), len(ids)))
    count = {}
    for a, b, c in mesh.tris:
        for i, j in ((a, b), (b, c), (c, a)):
            key = (min(weld[i], weld[j]), max(weld[i], weld[j]))
            count[key] = count.get(key, 0) + 1
    back = {w: i for i, w in enumerate(weld)}
    n = 0
    for (a, b), k in count.items():
        if k == 1 and near(mesh.verts[back[a]]) and near(mesh.verts[back[b]]):
            n += 1
    return n


def near_port(v):
    return 0.8 < abs(v.x) < 2.3 and 0.35 < v.y < 2.1 and 4.75 < v.z < 6.7


bad = 0
for name in ("tww3_mtb_hull_solid", "tww3_mtb_hull_solid_cut"):
    path = FOLDER / (name + ".rigid_model_v2")
    new = rmv2.load(path.read_bytes())
    same = (new["version"] == stock["version"], new["skeleton"] == stock["skeleton"], new["lod_headers"] == stock["lod_headers"], len(new["lods"]) == len(stock["lods"]))
    print(name, path.stat().st_size, "version, skeleton, LOD headers, LOD count same:", same)
    bad += not all(same)
    for li, (ours, theirs) in enumerate(zip(new["lods"], stock["lods"])):
        if len(ours) != len(theirs):
            print("  meshes differ", li)
            bad += 1
        for mi, (m, t) in enumerate(zip(ours, theirs)):
            same = (m.flag == t.flag, m.render == t.render, m.fixed[:712] == t.fixed[:712], m.attachments == t.attachments, m.textures == t.textures, m.strings == t.strings, m.extra == t.extra, m.vertex_type == t.vertex_type, m.head_tail == t.head_tail)
            if not all(same):
                print("  differ", li, mi, same)
                bad += 1
            bones_t = {(v.bone0, v.bone1, v.weight0, v.weight1) + (tuple(v.rest[:4]) if len(v.rest) == 24 else ()) for v in t.verts}
            bones_m = {(v.bone0, v.bone1, v.weight0, v.weight1) + (tuple(v.rest[:4]) if len(v.rest) == 24 else ()) for v in m.verts}
            if not bones_m <= bones_t:
                print("  new bone weights", li, mi, bones_m - bones_t)
                bad += 1
            if mi == 0:
                print(f"  LOD {li}: stock {len(t.verts)} v {len(t.tris)} t, new {len(m.verts)} v {len(m.tris)} t, open edges at the port: stock {open_edges(t, near_port)}, new {open_edges(m, near_port)}")
# The check itself: the stock hull with the port's pieces taken out has the hole, so it must find it.
SPEC = json.loads((REPO / "data" / "hull_parts.json").read_text(encoding="utf-8"))
BOXES = next(d for d in SPEC["details"] if d["name"] == "port")["boxes"]


def without_port(mesh):
    parent = list(range(len(mesh.verts)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, c in mesh.tris:
        parent[find(a)] = find(b)
        parent[find(c)] = find(a)
    groups = {}
    for i, v in enumerate(mesh.verts):
        groups.setdefault(find(i), []).append(v)
    away = set()
    for root, vs in groups.items():
        lo = [min(getattr(v, k) for v in vs) for k in "xyz"]
        hi = [max(getattr(v, k) for v in vs) for k in "xyz"]
        if any(all(lo[i] >= A[i] and hi[i] <= A[i + 3] for i in range(3)) for A in BOXES):
            away.add(root)
    return rmv2.keep_triangles(mesh, lambda a, b, c: find(a) not in away)


print("control, stock hull with the port taken out, open edges by LOD:", [open_edges(without_port(lod[0]), near_port) for lod in stock["lods"]])


def normals(mesh):
    """In the port's zone: triangles facing against their vertices' normals, and the largest angle between normals at one place."""
    at = 12 + (4 if len(mesh.verts[0].rest) == 24 else 0) - 12
    unit = lambda r: [r[at + k] / 127.5 - 1 for k in range(3)]
    against, seen = 0, {}
    worst = 1.0
    for tri in mesh.tris:
        vs = [mesh.verts[i] for i in tri]
        if not all(near_port(v) for v in vs):
            continue
        e1 = [vs[1].x - vs[0].x, vs[1].y - vs[0].y, vs[1].z - vs[0].z]
        e2 = [vs[2].x - vs[0].x, vs[2].y - vs[0].y, vs[2].z - vs[0].z]
        face = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        n = [sum(unit(v.rest)[k] for v in vs) for k in range(3)]
        if sum(a * b for a, b in zip(face, n)) < 0:
            against += 1
        for v in vs:
            key = (round(v.x, 3), round(v.y, 3), round(v.z, 3))
            u = unit(v.rest)
            if key in seen:
                worst = min(worst, sum(a * b for a, b in zip(u, seen[key])))
            else:
                seen[key] = u
    return against, round(worst, 3)


new = rmv2.load((FOLDER / "tww3_mtb_hull_solid.rigid_model_v2").read_bytes())
for li, lod in enumerate(new["lods"]):
    against, worst = normals(lod[0])
    print(f"  LOD {li}: triangles against their normals {against}, least cos between normals at one place {worst}")
    bad += against > 0
print("problems:", bad)
