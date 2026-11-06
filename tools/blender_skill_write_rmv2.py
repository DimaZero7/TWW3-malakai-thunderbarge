"""Writes the closed hull from the live Blender scene (GEO-lod0..3) to a rigid_model_v2, a .wsmodel and material copies.
Run in Blender (through MCP): import, then write(). Output under build/solid_hull_skill/out/ with game paths.

Hull mesh (part 0) of each LOD: stock vertices keep their bytes unless moved or re-normalled (then position / normal are
written and tangent, bitangent re-orthogonalised with their handedness); patch vertices copy the stock rim vertex at
the same place (bones, weights, colour, W) or the nearest hull vertex, and take their own position, normal and UV.
Unused stock vertices (the removed ring) are dropped. Parts 1 and 2 are the stock bytes.
"""
import math
import re
import sys
from pathlib import Path

import bpy
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import blender_rmv2 as br  # noqa: E402
import rmv2  # noqa: E402

OUT = REPO / "build" / "solid_hull_skill" / "out"
GEOM = "warmachines/aircraft/dwf_thunderbarge/tww3_mtb_dwf_thunderbarge_01.rigid_model_v2"
TEX = {k: f"warmachines/tex/tww3_mtb_dwf_thunderbarge_grungni_01_{k}.dds" for k in ("base_colour", "normal", "material_map")}
MATDIR = REPO / "build" / "solid_hull" / "game" / "materials"


def to_game(p):
    return (p[0], p[2], p[1])


def _unit(v):
    v = np.asarray(v, float)
    return v / max(np.linalg.norm(v), 1e-9)


def _reframe(v, n):
    """Tangent and bitangent of vertex v re-orthogonalised to the new normal n (game axes), handedness kept."""
    t, b, n0 = np.array(br.tangent(v)), np.array(br.bitangent(v)), np.array(br.normal(v))
    sign = 1.0 if np.dot(np.cross(n0, t), b) >= 0 else -1.0
    t2 = _unit(t - np.dot(t, n) * n)
    return t2, sign * np.cross(n, t2)


def hull_mesh(li, stock_mesh):
    ob = bpy.data.objects[f"GEO-lod{li}"]
    me = ob.data
    nv = len(me.vertices)
    P = np.empty(nv * 3)
    me.vertices.foreach_get("co", P)
    P = P.reshape(-1, 3)
    st = np.empty(nv, np.int32)
    me.attributes["stock"].data.foreach_get("value", st)
    NR = np.empty(nv * 3)
    me.attributes["nrm"].data.foreach_get("vector", NR)
    NR = NR.reshape(-1, 3)
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    luv = np.empty(len(me.loops) * 2)
    me.uv_layers["UVMap"].data.foreach_get("uv", luv)
    VUV = np.zeros((nv, 2))
    VUV[lv] = luv.reshape(-1, 2)
    tris = []
    for f in me.polygons:
        a, b, c = f.vertices
        tris.append((a, c, b))                     # back to the game's winding
    used = sorted({i for t in tris for i in t})
    key = {}
    for i, v in enumerate(stock_mesh.verts):
        key.setdefault((round(v.x, 4), round(v.y, 4), round(v.z, 4)), []).append(i)
    stock_xyz = np.array([(v.x, v.y, v.z) for v in stock_mesh.verts])
    out = stock_mesh.copy()
    out.verts, out.tris = [], []
    remap = {}
    moved = renormed = new = uv_moved = 0
    for i in used:
        gp = np.array(to_game(P[i]))
        gn = _unit(to_game(NR[i]))
        if st[i] >= 0:
            src = stock_mesh.verts[st[i]]
            v = src.copy()
            if np.linalg.norm(gp - stock_xyz[st[i]]) > 1e-4:
                v.x, v.y, v.z = map(float, gp)
                moved += 1
            n0 = np.array(br.normal(src))
            if math.degrees(math.acos(np.clip(np.dot(_unit(n0), gn), -1, 1))) > 0.5:
                t2, b2 = _reframe(src, gn)
                br.set_shading(v, n=gn, t=t2, b=b2)
                renormed += 1
            new_uv = (float(VUV[i, 0]), float(1 - VUV[i, 1]))
            if max(abs(a - b) for a, b in zip(new_uv, br.uv(src))) > 1e-6:      # moved in the scene (barrel caps etc.)
                br.set_shading(v, uv_=new_uv)
                uv_moved += 1
        else:
            k = (round(gp[0], 4), round(gp[1], 4), round(gp[2], 4))
            cands = key.get(k)
            if cands:
                tmpl = max(cands, key=lambda j: np.dot(br.normal(stock_mesh.verts[j]), gn))
            else:
                tmpl = int(np.argmin(((stock_xyz - gp) ** 2).sum(1)))
            src = stock_mesh.verts[tmpl]
            v = src.copy()
            v.x, v.y, v.z = map(float, gp)
            t2, b2 = _reframe(src, gn)
            br.set_shading(v, n=gn, uv_=(float(VUV[i, 0]), float(1 - VUV[i, 1])), t=t2, b=b2)
            new += 1
        remap[i] = len(out.verts)
        out.verts.append(v)
    out.tris = [tuple(remap[i] for i in t) for t in tris]
    if len(out.verts) > 65535:
        raise ValueError("too many vertices")
    return out, dict(verts=len(out.verts), tris=len(out.tris), moved=moved, renormed=renormed, new=new, uv_moved=uv_moved,
                     dropped=len(stock_mesh.verts) - (len(used) - new))


def material_copy(name):
    """A copy of a stock .xml.material with the hull's three textures pointed at the new files."""
    text = (MATDIR / name).read_text(encoding="utf-8")
    for k, path in TEX.items():
        text = text.replace(f"warmachines/tex/dwf_thunderbarge_grungni_01_{k}.dds", path)
    text = text.replace(f"<name>{name[:-len('.material')]}</name>", f"<name>tww3_mtb_{name[:-len('.material')]}</name>")
    return text


def write():
    stock_blob = br.STOCK.read_bytes()
    model = rmv2.load(stock_blob)
    report = {}
    for li in range(len(model["lods"])):
        mesh, rep = hull_mesh(li, model["lods"][li][0])
        model["lods"][li][0] = mesh
        report[f"lod{li}"] = rep
    blob = rmv2.save(model)
    gpath = OUT / GEOM
    gpath.parent.mkdir(parents=True, exist_ok=True)
    gpath.write_bytes(blob)
    # wsmodel: part 0 gets the material copies, the other parts stay stock
    ws = (REPO / "build" / "solid_hull" / "game" / "stock.wsmodel").read_text(encoding="utf-8")
    ws = ws.replace("warmachines/aircraft/dwf_thunderbarge/dwf_thunderbarge_01.rigid_model_v2", GEOM)
    used = set()

    def part0(m):
        name = m.group(2).split("/")[-1]
        used.add(name)
        return f'{m.group(1)}warmachines/materials/tww3_mtb_{name}</material>'
    ws = re.sub(r'(<material lod_index="\d+" part_index="0">)([^<]+)</material>', part0, ws)
    wpath = OUT / "warmachines" / "aircraft" / "dwf_thunderbarge" / "tww3_mtb_dwf_thunderbarge_grungni_01.wsmodel"
    wpath.write_text(ws, encoding="utf-8")
    mdir = OUT / "warmachines" / "materials"
    mdir.mkdir(parents=True, exist_ok=True)
    for name in sorted(used):
        (mdir / f"tww3_mtb_{name}").write_text(material_copy(name), encoding="utf-8")
    tdir = OUT / "warmachines" / "tex"
    tdir.mkdir(parents=True, exist_ok=True)
    for k in TEX:
        src = REPO / "build" / "solid_hull_skill" / "tex" / f"tww3_mtb_dwf_thunderbarge_grungni_01_{k}.dds"
        (tdir / src.name).write_bytes(src.read_bytes())
    report["files"] = [str(p.relative_to(OUT)) for p in sorted(OUT.rglob("*")) if p.is_file()]
    return report
