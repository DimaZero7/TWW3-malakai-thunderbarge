"""The stern pressure tank of the Spirit of Grungni (the riveted cylinder with the red valve wheel beside the lower drive
gear, one per side) as a model of its own, cut from the stock hull (project venv or plain python with numpy):
  python tools/tank_part.py [OUT_DIR]

The user's decision (06.11.2026): it is the high-pressure tank of the "Forsage" (afterburner) building, absent from the
stock look and shown once that building is built. In the game's data every tank piece is bound to hull_0 alone (weight
255, no animation). Selected by connected piece and box (game axes x, y up, z forward; both sides mirrored) in every LOD:
the body with its end caps and bands, the U pipe, the valve neck and the valve wheel (hub and spokes).
Not taken: the neck down into the shaft housing and the lower gear's axle; both stay on the hull, where the axle is
lengthened over the housing and the neck meets it from below (variant B), so the tank sits over them as in the stock.

The model keeps the hull's frame and skeleton (bones and weights as in the stock file) and the stock hull materials (the
stock atlas holds the tank). It is not part of the mod.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import blender_rmv2 as br  # noqa: E402
import rmv2  # noqa: E402
from stern_armour_part import cut  # noqa: E402

GAME = REPO / "build" / "solid_hull" / "game"
NAME = "warmachines/aircraft/dwf_thunderbarge/tww3_mtb_dwf_thunderbarge_forsage_tank"
BOX = (2.25, 1.5, -8.2, 4.75, 3.35, -3.75)      # |x|, y, z min, then max: every tank piece lies inside
XMAX_MIN = 3.0                                   # and reaches past |x| 3.0 (the rope coils and gear parts do not)
AXLE = (2.3, 2.01, -6.51, 3.59, 2.72, -5.8)      # the lower gear's static axle (stays on the hull)
LUMP = (3.27, 1.57, -6.52, 4.01, 2.05, -5.77)    # the neck down into the shaft housing (stays on the hull)
TOL = 0.06


def select_tris(mesh):
    """{side: {"tank": [...], "axle": [...], "lump": [...]}} triangle indexes in one stock mesh."""
    out = {s: {"tank": [], "axle": [], "lump": []} for s in (1, -1)}
    for tris, b in br.pieces(mesh, br.weld(mesh, 3)):
        for s in (1, -1):
            x0, x1 = sorted((b[0] * s, b[3] * s))
            bb = (x0, b[1], b[2], x1, b[4], b[5])
            if not (x0 >= BOX[0] and x1 <= BOX[3] and b[1] >= BOX[1] and b[4] <= BOX[4] and b[2] >= BOX[2]
                    and b[5] <= BOX[5] and x1 > XMAX_MIN):
                continue
            if max(abs(a - c) for a, c in zip(bb, AXLE)) < TOL:
                out[s]["axle"] += tris
            elif max(abs(a - c) for a, c in zip(bb, LUMP)) < TOL:
                out[s]["lump"] += tris
            else:
                out[s]["tank"] += tris
            break
    return out


def build(out_dir):
    stock = rmv2.load((GAME / "stock.rigid_model_v2").read_bytes())
    ws = (GAME / "stock.wsmodel").read_text(encoding="utf-8")
    mats = {(int(a), int(b)): m for a, b, m in re.findall(r'<material lod_index="(\d+)" part_index="(\d+)">([^<]+)</material>', ws)}
    model = {"version": stock["version"], "skeleton": stock["skeleton"], "lods": [], "lod_headers": []}
    table, report = {}, {}
    for li, meshes in enumerate(stock["lods"]):
        sel = select_tris(meshes[0])
        tris = {t for s in sel.values() for t in s["tank"]}
        part = cut(meshes[0], tris)
        model["lods"].append([part])
        model["lod_headers"].append(stock["lod_headers"][li])
        table[li] = [mats[(li, 0)]]
        bones = {}
        for v in part.verts:
            bones[v.bone0] = bones.get(v.bone0, 0) + 1
        report[f"lod{li}"] = {"tris": len(part.tris), "verts": len(part.verts), "bones": dict(sorted(bones.items())),
                              "by_side": {s: {k: len(v) for k, v in d.items()} for s, d in sel.items()}}
    out = Path(out_dir)
    (out / NAME).parent.mkdir(parents=True, exist_ok=True)
    blob = rmv2.save(model)
    (out / (NAME + ".rigid_model_v2")).write_bytes(blob)
    (out / (NAME + ".wsmodel")).write_bytes(rmv2.wsmodel(NAME + ".rigid_model_v2", table))
    back = rmv2.load(blob)
    report["read_back"] = {f"lod{li}": [len(l[0].tris), len(l[0].verts)] for li, l in enumerate(back["lods"])}
    report["skeleton"] = back["skeleton"]
    report["materials"] = table
    return report


if __name__ == "__main__":
    od = sys.argv[1] if len(sys.argv) > 1 else REPO / "build" / "solid_hull_tank" / "tank_part"
    print(json.dumps(build(od), indent=1))
