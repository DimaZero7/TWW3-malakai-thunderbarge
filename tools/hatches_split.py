"""The closed-hatch hull of the Spirit of Grungni as three parts that add up (project venv or plain python with numpy):
  python tools/hatches_split.py [HATCHES_DIR]          HATCHES_DIR default build/solid_hull_hatches; output HATCHES_DIR/parts

From the written whole hull (HATCHES_DIR/warmachines, hatches closed) and the stock:
  hull_open   the hull with the four holes in the bottom: the whole hull without the fill triangles (parts 1-2 as they are;
              materials and textures ours, as the whole hull's);
  covers      the fill over the four holes alone (one part, 4 LODs, the hull's skeleton, bones and our part-0 materials:
              its UVs read the steel moved to the free atlas spots of our textures);
  niches      the four stock niches (tools/hatches_part.py: one part, 4 LODs, stock bones and materials).
The whole closed hull stays as it is. Checks (printed): per LOD, hull_open + covers = the whole hull and hull_open + niches
= the hull before closing (build/solid_hull_tank, the stock bottom there), as multisets of triangles by corner bytes;
niche triangles byte-equal to the stock's.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import blender_rmv2 as br  # noqa: E402
import rmv2  # noqa: E402
import hatches_part  # noqa: E402
from stern_armour_part import cut  # noqa: E402

D = "warmachines/aircraft/dwf_thunderbarge/"
WHOLE = D + "tww3_mtb_dwf_thunderbarge_01.rigid_model_v2"
WHOLE_WS = D + "tww3_mtb_dwf_thunderbarge_grungni_01.wsmodel"
OPEN = D + "tww3_mtb_dwf_thunderbarge_01_open"
OPEN_WS = D + "tww3_mtb_dwf_thunderbarge_grungni_01_open.wsmodel"
COVERS = D + "tww3_mtb_dwf_thunderbarge_hatch_covers"
PREV = REPO / "build" / "solid_hull_tank" / WHOLE
SPOTS = [(576, 0, 768, 192), (1616, 0, 1792, 160)]        # the free atlas spots the fill reads (atlas px)
HATCH = hatches_part.HATCH


def fill_tris(mesh):
    """Fill triangles: every corner's UV in a spot and the centre in a hatch box."""
    out = []
    for ti, t in enumerate(mesh.tris):
        vs = [mesh.verts[i] for i in t]
        uv = [(br.uv(v)[0] * 4096, br.uv(v)[1] * 4096) for v in vs]
        if not all(any(x0 <= u <= x1 and y0 <= w <= y1 for x0, y0, x1, y1 in SPOTS) for u, w in uv):
            continue
        c = [sum(getattr(v, a) for v in vs) / 3 for a in "xyz"]
        if any(b[0] <= abs(c[0]) <= b[3] and b[1] <= c[1] <= b[4] and b[2] <= c[2] <= b[5] for b in HATCH.values()):
            out.append(ti)
    return out


def tri_bag(mesh, tris=None):
    tris = range(len(mesh.tris)) if tris is None else tris
    return Counter(tuple(sorted(mesh.verts[v].pack() for v in mesh.tris[t])) for t in tris)


def split(root):
    root = Path(root)
    out = root / "parts"
    whole = rmv2.load((root / WHOLE).read_bytes())
    ws = (root / WHOLE_WS).read_text(encoding="utf-8")
    mats = {(int(a), int(b)): m for a, b, m in re.findall(r'<material lod_index="(\d+)" part_index="(\d+)">([^<]+)</material>', ws)}
    open_m = {"version": whole["version"], "skeleton": whole["skeleton"], "lods": [], "lod_headers": list(whole["lod_headers"])}
    cov_m = {"version": whole["version"], "skeleton": whole["skeleton"], "lods": [], "lod_headers": list(whole["lod_headers"])}
    open_t, cov_t, rep = {}, {}, {}
    for li, meshes in enumerate(whole["lods"]):
        fill = set(fill_tris(meshes[0]))
        hull = cut(meshes[0], set(range(len(meshes[0].tris))) - fill)       # order of triangles kept
        open_m["lods"].append([hull] + [m.copy() for m in meshes[1:]])
        cov_m["lods"].append([cut(meshes[0], fill)])
        open_t[li] = [mats[(li, p)] for p in range(len(meshes))]
        cov_t[li] = [mats[(li, 0)]]
        rep[f"lod{li}"] = {"fill_tris": len(fill), "open_tris": len(hull.tris), "open_verts": len(hull.verts),
                           "covers_verts": len(cov_m["lods"][-1][0].verts)}
    for name, model, table, wsname in ((OPEN, open_m, open_t, OPEN_WS), (COVERS, cov_m, cov_t, COVERS + ".wsmodel")):
        p = out / (name + ".rigid_model_v2")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(rmv2.save(model))
        (out / wsname).write_bytes(rmv2.wsmodel(name + ".rigid_model_v2", table))
    rep["niches"] = hatches_part.build(out)
    rep["checks"] = check(root)
    return rep


def check(root):
    out = Path(root) / "parts"
    whole = rmv2.load((Path(root) / WHOLE).read_bytes())
    prev = rmv2.load(PREV.read_bytes())
    stock = rmv2.load((REPO / "build" / "solid_hull" / "game" / "stock.rigid_model_v2").read_bytes())
    op = rmv2.load((out / (OPEN + ".rigid_model_v2")).read_bytes())
    cv = rmv2.load((out / (COVERS + ".rigid_model_v2")).read_bytes())
    ni = rmv2.load((out / (hatches_part.NAME + ".rigid_model_v2")).read_bytes())
    rep = {}
    for li in range(len(whole["lods"])):
        o, c, n = op["lods"][li][0], cv["lods"][li][0], ni["lods"][li][0]
        st = stock["lods"][li][0]
        # the stock bottom in the hatch boxes: band and niche triangles there
        def in_boxes(mesh, t):
            cc = np.mean([(mesh.verts[v].x, mesh.verts[v].y, mesh.verts[v].z) for v in mesh.tris[t]], 0)
            return any(b[0] <= abs(cc[0]) <= b[3] and b[1] <= cc[1] <= b[4] and b[2] <= cc[2] <= b[5] for b in HATCH.values())
        st_zone = tri_bag(st, [t for t in range(len(st.tris)) if in_boxes(st, t)])
        on = Counter(tri_bag(o, [t for t in range(len(o.tris)) if in_boxes(o, t)])) + tri_bag(n)
        rep[f"lod{li}"] = {
            "open+covers==whole": tri_bag(o) + tri_bag(c) == tri_bag(whole["lods"][li][0]),
            "open+niches==prev(tank)": tri_bag(o) + tri_bag(n) == tri_bag(prev["lods"][li][0]),
            "open+niches==stock_in_hatch_boxes": on == st_zone,
            "parts1_2_same": all(a.verts[i].pack() == b.verts[i].pack() for a, b in zip(op["lods"][li][1:], whole["lods"][li][1:]) for i in range(len(a.verts)))
                             and all(a.tris == b.tris for a, b in zip(op["lods"][li][1:], whole["lods"][li][1:])),
            "covers_bones": sorted({v.bone0 for v in c.verts}), "skeleton": op["skeleton"] == whole["skeleton"] == cv["skeleton"] == ni["skeleton"],
            "lod_headers_same": op["lod_headers"] == cv["lod_headers"] == whole["lod_headers"]}
    return rep


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else REPO / "build" / "solid_hull_hatches"
    print(json.dumps(split(root), indent=1, default=str))
