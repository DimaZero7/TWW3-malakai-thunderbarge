"""The bow porthole of the Spirit of Grungni as a model of its own, cut from the stock hull (project venv or py -3.14):
  python tools/porthole_part.py [FACES_JSON] [OUT_DIR]

FACES_JSON (build/solid_hull_porthole/porthole_faces_stock.json, from blender_skill_porthole.select in Blender) lists
per LOD and side the stock hull's triangles of the porthole: the housing (tube, glass, lid ring), 9 hinge and latch
pieces and the steel flange around it (hull triangles whose texture is the ring painted on the plank atlas). Both sides
go into one model in the hull's own frame and skeleton, like the hull_frame details of tools/hull_parts.py, with the stock
hull materials: the stock atlas still has the ring and the glass, our hull atlas has planks there.
It is not part of the mod: it waits for the lookout post upgrade.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import rmv2  # noqa: E402

GAME = REPO / "build" / "solid_hull" / "game"
NAME = "warmachines/aircraft/dwf_thunderbarge/tww3_mtb_dwf_thunderbarge_porthole"


def select(mesh, tris):
    out = mesh.copy()
    remap, verts, new = {}, [], []
    for i in sorted(tris):
        t = []
        for v in mesh.tris[i]:
            if v not in remap:
                remap[v] = len(verts)
                verts.append(mesh.verts[v].copy())
            t.append(remap[v])
        new.append(tuple(t))
    out.verts, out.tris = verts, new
    return out


def build(faces_json, out_dir):
    faces = json.loads(Path(faces_json).read_text(encoding="utf-8"))
    stock = rmv2.load((GAME / "stock.rigid_model_v2").read_bytes())
    ws = (GAME / "stock.wsmodel").read_text(encoding="utf-8")
    mats = {(int(a), int(b)): m for a, b, m in re.findall(r'<material lod_index="(\d+)" part_index="(\d+)">([^<]+)</material>', ws)}
    model = {"version": stock["version"], "skeleton": stock["skeleton"], "lods": [], "lod_headers": []}
    table, report = {}, {}
    for li, meshes in enumerate(stock["lods"]):
        tris = set()
        for side in (1, -1):
            for kind in ("housing", "pins", "flange"):
                tris |= set(faces[f"{li}_{side}"][kind])
        part = select(meshes[0], tris)
        model["lods"].append([part])
        model["lod_headers"].append(stock["lod_headers"][li])
        table[li] = [mats[(li, 0)]]
        report[f"lod{li}"] = {"tris": len(part.tris), "verts": len(part.verts)}
    out = Path(out_dir)
    (out / NAME).parent.mkdir(parents=True, exist_ok=True)
    blob = rmv2.save(model)
    (out / (NAME + ".rigid_model_v2")).write_bytes(blob)
    (out / (NAME + ".wsmodel")).write_bytes(rmv2.wsmodel(NAME + ".rigid_model_v2", table))
    back = rmv2.load(blob)                         # read back
    report["read_back"] = {f"lod{li}": [len(l[0].tris), len(l[0].verts)] for li, l in enumerate(back["lods"])}
    report["materials"] = table
    return report


if __name__ == "__main__":
    fj = sys.argv[1] if len(sys.argv) > 1 else REPO / "build" / "solid_hull_porthole" / "porthole_faces_stock.json"
    od = sys.argv[2] if len(sys.argv) > 2 else REPO / "build" / "solid_hull_porthole" / "porthole_part"
    print(json.dumps(build(fj, od), indent=1))
