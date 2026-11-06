"""The four bomb-hatch niches of the Spirit of Grungni (two per side, in the hull bottom beside the keel) as a model of
their own, cut from the stock hull (project venv or plain python with numpy):
  python tools/hatches_part.py [OUT_DIR]

The user's decision (06.11.2026): the hatches are not in the stock look; they come back with the buildings of the bomb
branch. A niche is a recess in the steel bottom: two end walls, two side walls (the light frame seen from below) and a
dark ceiling about 0.5..0.8 m up. In the game's data every niche vertex is bound to bone 3 (the hull bone) alone with
weight 255, no animation; the doors that open are separate models (doors_left / doors_right with the bombs), not in the
hull. Selected per LOD: triangles of hull part 0 whose centre lies in a hatch box (game axes |x| 0.45..2.0, y -0.25..0.95,
z 1.7..3.65 front, -4.0..-2.1 rear) and whose UVs are off the bottom steel band of the atlas (the band's own triangles
around the hole stay on the hull).

Note: the closed hull (build/solid_hull_hatches) covers each hole with a flush steel fill, so this model alone shows
nothing from outside: shown with the bomb buildings it needs a hull without the fill (the fill as a model of its own,
or the hull variant with the holes). It keeps the hull's frame, skeleton and stock materials. Not part of the mod.
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
NAME = "warmachines/aircraft/dwf_thunderbarge/tww3_mtb_dwf_thunderbarge_bomb_hatches"
HATCH = {"front": (0.45, -0.25, 1.7, 2.0, 0.95, 3.65), "rear": (0.45, -0.25, -4.0, 2.0, 0.95, -2.1)}   # |x|, y, z
BAND = (1080, 3755, 2520, 4010)          # the bottom steel band, atlas px (rows from the top)


def select_tris(mesh):
    """{"front+": [...], "front-": [...], "rear+": [...], "rear-": [...]} niche triangle indexes of one stock mesh."""
    out = {}
    for ti, t in enumerate(mesh.tris):
        vs = [mesh.verts[i] for i in t]
        c = [sum(getattr(v, a) for v in vs) / 3 for a in "xyz"]
        uv = [(br.uv(v)[0] * 4096, br.uv(v)[1] * 4096) for v in vs]
        band = all(BAND[0] <= u <= BAND[2] and BAND[1] <= w <= BAND[3] for u, w in uv)
        for k, b in HATCH.items():
            if b[0] <= abs(c[0]) <= b[3] and b[1] <= c[1] <= b[4] and b[2] <= c[2] <= b[5] and not band:
                out.setdefault(f"{k}{'+' if c[0] > 0 else '-'}", []).append(ti)
    return out


def build(out_dir):
    stock = rmv2.load((GAME / "stock.rigid_model_v2").read_bytes())
    ws = (GAME / "stock.wsmodel").read_text(encoding="utf-8")
    mats = {(int(a), int(b)): m for a, b, m in re.findall(r'<material lod_index="(\d+)" part_index="(\d+)">([^<]+)</material>', ws)}
    model = {"version": stock["version"], "skeleton": stock["skeleton"], "lods": [], "lod_headers": []}
    table, report = {}, {}
    for li, meshes in enumerate(stock["lods"]):
        sel = select_tris(meshes[0])
        tris = {t for s in sel.values() for t in s}
        part = cut(meshes[0], tris)
        model["lods"].append([part])
        model["lod_headers"].append(stock["lod_headers"][li])
        table[li] = [mats[(li, 0)]]
        bones = {}
        for v in part.verts:
            key = f"{v.bone0}/{v.rest[0] if len(v.rest) == 24 else v.weight0}"
            bones[key] = bones.get(key, 0) + 1
        report[f"lod{li}"] = {"tris": len(part.tris), "verts": len(part.verts), "bone/weight": bones,
                              "by_hatch": {k: len(v) for k, v in sorted(sel.items())}}
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
    od = sys.argv[1] if len(sys.argv) > 1 else REPO / "build" / "solid_hull_hatches" / "hatches_part"
    print(json.dumps(build(od), indent=1))
