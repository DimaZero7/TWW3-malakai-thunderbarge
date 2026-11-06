"""Reads back what blender_skill_write_rmv2 wrote and compares it with the stock files (plain python + numpy).

  python tools/blender_skill_check_out.py      prints a JSON report
"""
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import rmv2  # noqa: E402

GAME = REPO / "build" / "solid_hull" / "game"
OUT = REPO / "build" / "solid_hull_skill" / "out"
NEW = OUT / "warmachines/aircraft/dwf_thunderbarge/tww3_mtb_dwf_thunderbarge_01.rigid_model_v2"
PORT = np.array((1.559, 1.223, 5.769))          # game axes (x, y up, z forward)
AXIS = np.array((0.873, -0.356, 0.335))


def open_edges_near(mesh, side, radius=1.3):
    pc, n = PORT * (side, 1, 1), AXIS * (side, 1, 1)
    key = [(round(v.x, 3), round(v.y, 3), round(v.z, 3)) for v in mesh.verts]
    P = np.array([(v.x, v.y, v.z) for v in mesh.verts])
    d = P - pc
    h = d @ n
    rr = np.linalg.norm(d - np.outer(h, n), axis=1)
    near = (rr < radius) & (h > -0.7)
    cnt = {}
    for t in mesh.tris:
        if not any(near[i] for i in t):
            continue
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            e = tuple(sorted((key[a], key[b])))
            cnt[e] = cnt.get(e, 0) + 1
    inner = [e for e, c in cnt.items() if c == 1 and all(
        np.linalg.norm(np.cross(np.array(p) - pc, n)) < radius - 0.15 for p in e)]
    return len(inner)


def dds_info(path):
    b = path.read_bytes()
    h, w = struct.unpack_from("<II", b, 12)
    return {"size": len(b), "w": w, "h": h, "mips": struct.unpack_from("<I", b, 28)[0], "fourcc": b[84:88].decode("latin1"),
            "header": b[:148]}


def main():
    s = rmv2.load((GAME / "stock.rigid_model_v2").read_bytes())
    blob = NEW.read_bytes()
    m = rmv2.load(blob)
    rep = {"version": [s["version"], m["version"]], "skeleton": [s["skeleton"], m["skeleton"]],
           "lods": [len(s["lods"]), len(m["lods"])], "lod_headers_same": s["lod_headers"] == m["lod_headers"],
           "file_bytes": [len((GAME / "stock.rigid_model_v2").read_bytes()), len(blob)], "lod": {}}
    for li, (sl, ml) in enumerate(zip(s["lods"], m["lods"])):
        r = {"meshes": [len(sl), len(ml)]}
        for pi, (a, b) in enumerate(zip(sl, ml)):
            same = dict(name=a.name == b.name, vertex_type=a.vertex_type == b.vertex_type, flag=(a.flag, a.render) == (b.flag, b.render),
                        attachments=a.attachments == b.attachments, textures=a.textures == b.textures, strings=a.strings == b.strings,
                        fixed=a.fixed[:712] == b.fixed[:712], extra=a.extra == b.extra, head_tail=a.head_tail == b.head_tail)
            entry = {"same": all(same.values()) or same, "tris": [len(a.tris), len(b.tris)], "verts": [len(a.verts), len(b.verts)]}
            if pi:
                entry["verts_identical"] = all(x.pack() == y.pack() for x, y in zip(a.verts, b.verts)) and a.tris == b.tris
            else:
                entry["open_edges_port_zone_R_L"] = [[open_edges_near(a, 1), open_edges_near(a, -1)], [open_edges_near(b, 1), open_edges_near(b, -1)]]
                bad = sum(1 for v in b.verts if not all(math.isfinite(c) for c in (v.x, v.y, v.z)))
                entry["nonfinite_positions"] = bad
                bones = {(v.bone0, v.rest[:4] if len(v.rest) == 24 else bytes((v.weight0, v.weight1))) for v in b.verts} - \
                        {(v.bone0, v.rest[:4] if len(v.rest) == 24 else bytes((v.weight0, v.weight1))) for v in a.verts}
                entry["new_bone_weight_combos"] = len(bones)
            r[f"part{pi}"] = entry
        rep["lod"][li] = r
    tex = {}
    for k in ("base_colour", "normal", "material_map"):
        a = dds_info(GAME / f"dwf_thunderbarge_grungni_01_{k}.dds")
        b = dds_info(OUT / f"warmachines/tex/tww3_mtb_dwf_thunderbarge_grungni_01_{k}.dds")
        sa, sb = (GAME / f"dwf_thunderbarge_grungni_01_{k}.dds").read_bytes(), (OUT / f"warmachines/tex/tww3_mtb_dwf_thunderbarge_grungni_01_{k}.dds").read_bytes()
        diff = np.frombuffer(sa, np.uint8) != np.frombuffer(sb, np.uint8)
        tex[k] = {"fourcc": a["fourcc"], "w_h": [b["w"], b["h"]], "mips": [a["mips"], b["mips"]], "size_same": a["size"] == b["size"],
                  "header_same": a["header"] == b["header"], "bytes_changed": int(diff.sum()), "bytes_changed_pct": round(100 * diff.mean(), 3)}
    rep["textures"] = tex
    ws = (OUT / "warmachines/aircraft/dwf_thunderbarge/tww3_mtb_dwf_thunderbarge_grungni_01.wsmodel").read_text()
    rep["wsmodel_parts"] = ws.count("<material ")
    rep["wsmodel_new_materials"] = ws.count("tww3_mtb_")
    for f in (OUT / "warmachines/materials").glob("*.material"):
        t = f.read_text()
        rep[f"material {f.name}"] = {"new_tex_refs": t.count("tww3_mtb_dwf"), "stock_mask_ref": "grungni_01_mask.dds" in t}
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
