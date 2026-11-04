"""Reads back what tools/blender_solid_hull_tex.py wrote and compares it with the stock files: py -3.14 tools/blender_solid_hull_tex_check.py

Model: skeleton, LODs, materials' blocks, bones; open edges at the port, with a control; normals against the shape itself, in degrees (zone of port and porthole).
Textures: size, header, bytes changed. Materials and .wsmodel: name our own files only. Other models on the Grungni's sheets: which read the painted place.
"""
import json
import math
import re
import struct
import sys
from compression import zstd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gamepack
import hull_parts as hp
import rmv2

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "build" / "solid_hull_tex"
FOLDER = OUT / "warmachines" / "aircraft" / "dwf_thunderbarge"
GAME = REPO / "build" / "solid_hull" / "game"
stock = rmv2.load((GAME / "stock.rigid_model_v2").read_bytes())
bad = 0


def at(v):
    return 4 if len(v.rest) == 24 else 0


def nrm(v):
    a = at(v)
    return [v.rest[a + k] / 127.5 - 1 for k in range(3)]


def uv(v):
    return struct.unpack_from("<2e", v.rest, at(v) + 4)


def weld(mesh):
    ids, out = {}, []
    for v in mesh.verts:
        out.append(ids.setdefault((round(v.x, 3), round(v.y, 3), round(v.z, 3)), len(ids)))
    return out


def open_edges(mesh, near):
    w = weld(mesh)
    count = {}
    for a, b, c in mesh.tris:
        for i, j in ((a, b), (b, c), (c, a)):
            key = (min(w[i], w[j]), max(w[i], w[j]))
            count[key] = count.get(key, 0) + 1
    back = {x: i for i, x in enumerate(w)}
    return sum(1 for (a, b), k in count.items() if k == 1 and near(mesh.verts[back[a]]) and near(mesh.verts[back[b]]))


def near_port(v):
    return 0.8 < abs(v.x) < 2.3 and 0.35 < v.y < 2.1 and 4.75 < v.z < 6.7


def zone(v):
    return 0.8 < abs(v.x) < 2.5 and 0.2 < v.y < 3.0 and 4.2 < v.z < 7.2


def side_triangles(mesh):
    """Triangles of the two side pieces (planks and belt) and of the closing pieces."""
    w = weld(mesh)
    tris = []
    for ids, b in hp.pieces(mesh):
        edge = max(abs(b[0]), abs(b[3]))
        side = b[5] - b[2] > 15 and abs(edge - 2.38) < 0.08
        closing = min(abs(b[0]), abs(b[3])) > 0.7 and edge < 2.5 and b[1] > 0.2 and b[4] < 2.3 and b[2] > 4.7 and b[5] < 6.8 and b[3] * b[0] > 0
        if side or closing:
            tris.extend(mesh.tris[t] for t in ids)
    return tris, w


def against_shape(mesh):
    """Each place's file normal against the mean of its faces' normals: mean and largest angle, in the zone."""
    tris, w = side_triangles(mesh)
    faces = {}
    for a, b, c in tris:
        A, B, C = mesh.verts[a], mesh.verts[b], mesh.verts[c]
        e1 = (B.x - A.x, B.y - A.y, B.z - A.z)
        e2 = (C.x - A.x, C.y - A.y, C.z - A.z)
        f = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        for i in (a, b, c):
            s = faces.setdefault(w[i], [0.0, 0.0, 0.0])
            for k in range(3):
                s[k] += f[k]
    out = []
    seen = set()
    for t in tris:
        for i in t:
            v = mesh.verts[i]
            if i in seen or not near_port(v):
                continue
            seen.add(i)
            f, n = faces[w[i]], nrm(v)
            lf, ln = math.sqrt(sum(x * x for x in f)), math.sqrt(sum(x * x for x in n))
            if lf < 1e-9:
                continue
            out.append(math.degrees(math.acos(max(-1, min(1, sum(x * y for x, y in zip(f, n)) / (lf * ln))))))
    return round(sum(out) / len(out), 1), round(max(out), 1), len(out)


def without_port(mesh):
    boxes = next(d for d in hp.SPEC["details"] if d["name"] == "port")["boxes"]
    away = set()
    for tris, b in hp.pieces(mesh):
        if any(hp.inside(b, a) for a in boxes):
            away.update(tris)
    return hp._select(mesh, set(range(len(mesh.tris))) - away)


print("control, stock hull without the port, open edges by LOD:", [open_edges(without_port(lod[0]), near_port) for lod in stock["lods"]])
print("normals against the shape, stock without the port (mean, max, places):", [against_shape(without_port(lod[0])) for lod in stock["lods"]])
for name in ("tww3_mtb_hull_solid", "tww3_mtb_hull_solid_cut"):
    new = rmv2.load((FOLDER / (name + ".rigid_model_v2")).read_bytes())
    same = (new["version"] == stock["version"], new["skeleton"] == stock["skeleton"], new["lod_headers"] == stock["lod_headers"], len(new["lods"]) == len(stock["lods"]))
    print(name, "version, skeleton, LOD headers, LOD count same:", same)
    bad += not all(same)
    for li, (ours, theirs) in enumerate(zip(new["lods"], stock["lods"])):
        bad += len(ours) != len(theirs)
        for mi, (m, t) in enumerate(zip(ours, theirs)):
            same = (m.flag == t.flag, m.render == t.render, m.fixed[:712] == t.fixed[:712], m.attachments == t.attachments, m.textures == t.textures, m.strings == t.strings, m.extra == t.extra, m.vertex_type == t.vertex_type, m.head_tail == t.head_tail)
            if not all(same):
                print("  differ", li, mi, same)
                bad += 1
            key = lambda v: (v.bone0, v.bone1, v.weight0, v.weight1) + (tuple(v.rest[:4]) if len(v.rest) == 24 else ())
            if not {key(v) for v in m.verts} <= {key(v) for v in t.verts}:
                print("  new bone weights", li, mi)
                bad += 1
            if mi == 0:
                print(f"  LOD {li}: stock {len(t.verts)} v {len(t.tris)} t, new {len(m.verts)} v {len(m.tris)} t, open edges at the port {open_edges(m, near_port)}, normals against the shape {against_shape(m)}")
                bad += open_edges(m, near_port) > 0

total_raw = total_zstd = 0
for part in ("base_colour", "normal", "material_map"):
    a = (GAME / f"dwf_thunderbarge_grungni_01_{part}.dds").read_bytes()
    b = (OUT / "warmachines" / "tex" / f"tww3_mtb_solid_{part}.dds").read_bytes()
    head = 148 if a[84:88] == b"DX10" else 128
    diff = sum(1 for i in range(0, len(a), 8) if a[i:i + 8] != b[i:i + 8])
    packed = len(zstd.compress(b, 3))
    total_raw += len(b)
    total_zstd += packed
    print(f"{part}: size {len(b)} same {len(a) == len(b)}, header same {a[:head] == b[:head]}, 8 byte groups changed {diff} of {len(a) // 8}, zstd {packed}")
    bad += a[:head] != b[:head] or len(a) != len(b)
print("three textures, raw MB", round(total_raw / 1e6, 1), "zstd MB", round(total_zstd / 1e6, 1))

ws = (FOLDER / "tww3_mtb_hull_solid.wsmodel").read_text(encoding="utf-8")
materials = set(re.findall(r">([^<]+\.material)<", ws))
print(".wsmodel materials:", sorted(Path(m).name for m in materials))
for m in materials:
    t = (OUT / m).read_text(encoding="utf-8")
    tex = set(re.findall(r"warmachines/tex/([\w]+\.dds)", t))
    print(" ", Path(m).name, sorted(tex))
    bad += any("grungni_01_base_colour" in x or "grungni_01_normal" in x or "grungni_01_material_map" in x for x in tex)

report = json.loads((OUT / "solid_hull_tex.json").read_text(encoding="utf-8"))
print("normals replaced, by LOD, largest change in degrees:", [(l["lod"], round(l["side1"]["deg_before_mean"], 1), round(l["side1"]["deg_before_max"], 1), round(l["side1"]["deg_after_max"], 2)) for l in report["lods"]])

# who else reads the painted place on these sheets (all stay on the stock sheets, nothing of theirs changes)
CX, CY, R = 1060 / 4096, 3770 / 4096, 100 / 4096
files = {}
for pack in sorted(gamepack.DATA.glob("*.pack")):
    if pack.name.startswith(("audio", "local_")):
        continue
    for n, blob in gamepack.entries(pack, lambda n: n.lower().endswith(".wsmodel") and "grungni" in n.lower() and "thunderbarge" in n.lower()):
        files[n] = blob
print("models on the Grungni sheets:", len(files))
for n, blob in sorted(files.items()):
    text = blob.decode("utf-8", "replace")
    geometry = re.search(r"<geometry>([^<]+)</geometry>", text).group(1)
    try:
        model = rmv2.load(hp.game_file(geometry))
    except (ValueError, SystemExit, IndexError, struct.error) as e:
        print(" ", Path(n).name, "not read:", e)
        continue
    hits = 0
    for mesh in (model["lods"][0] if model["lods"] else []):
        for tri in mesh.tris:
            p = [uv(mesh.verts[i]) for i in tri]
            mid = ((p[0][0] + p[1][0] + p[2][0]) / 3, (p[0][1] + p[1][1] + p[2][1]) / 3)
            hits += any((q[0] - CX) ** 2 + (q[1] - CY) ** 2 < R * R for q in p + [mid])
    print(f"  {Path(n).name}: triangles of LOD 0 reading the painted place: {hits}")
print("problems:", bad)
