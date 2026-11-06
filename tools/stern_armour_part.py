"""The stern armour of the Spirit of Grungni (the big plank boards with iron bands beside the propeller drive) as a model of
its own, cut from the stock hull (project venv or plain python with numpy):
  python tools/stern_armour_part.py [OUT_DIR] [--board-only]

In the game's data the boards are the rudders: each board and its three iron domes are bound to the bone rudder_left_0 /
rudder_right_0 of the skeleton zeppelin01 and swing about 20 degrees in the move and death animations. They hang on a
top hinge axle and two lower struts, whose hull ends are on hull_0 and outer ends on the rudder bone. All of it is
selected here by connected piece and box (game axes x, y up, z forward; both sides mirrored), in every LOD: the board
(one piece), its three domes and, unless --board-only, the axle and the two struts.

The model keeps the hull's frame and skeleton (bones and weights as in the stock file), so shown as another slot of the
hull's definition it moves with the rudder animation. Materials are the stock hull ones: the stock atlas holds the
boards. It is not part of the mod: it waits for the armour upgrade.
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import blender_rmv2 as br  # noqa: E402
import rmv2  # noqa: E402

GAME = REPO / "build" / "solid_hull" / "game"
NAME = "warmachines/aircraft/dwf_thunderbarge/tww3_mtb_dwf_thunderbarge_stern_armour"
BOARD_BOX = (3.55, -1.4, -6.25, 6.15, 6.65, -3.25)   # |x|, y, z min, then max: the board and its domes lie inside
BOARD_ZMAX_MIN = -5.4                               # the red valve wheel and its pins (also inside) end at z -5.51
MOUNT = [(2.34, 2.85, -5.02, 4.94, 3.69, -4.17),     # top hinge axle, from the gear hub to the top dome
         (1.64, -0.24, -5.18, 4.22, 1.42, -4.7),     # lower struts, from the bottom rail to the lower domes
         (1.64, -0.19, -4.43, 4.02, 1.42, -3.77)]
MOUNT_TOL = 0.05


def select_tris(mesh, mount=True):
    """{side: {"board": [...], "mount": [...]}} triangle indexes of the stern armour in one stock mesh."""
    out = {s: {"board": [], "mount": []} for s in (1, -1)}
    for tris, b in br.pieces(mesh, br.weld(mesh, 3)):
        for s in (1, -1):
            x0, x1 = sorted((b[0] * s, b[3] * s))
            bb = (x0, b[1], b[2], x1, b[4], b[5])
            if (x0 >= BOARD_BOX[0] and x1 <= BOARD_BOX[3] and b[1] >= BOARD_BOX[1] and b[4] <= BOARD_BOX[4]
                    and b[2] >= BOARD_BOX[2] and b[5] <= BOARD_BOX[5] and b[5] > BOARD_ZMAX_MIN):
                out[s]["board"] += tris
            elif mount and any(max(abs(a - c) for a, c in zip(bb, m)) < MOUNT_TOL for m in MOUNT):
                out[s]["mount"] += tris
    return out


def cut(mesh, tris):
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


def build(out_dir, mount=True):
    stock = rmv2.load((GAME / "stock.rigid_model_v2").read_bytes())
    ws = (GAME / "stock.wsmodel").read_text(encoding="utf-8")
    mats = {(int(a), int(b)): m for a, b, m in re.findall(r'<material lod_index="(\d+)" part_index="(\d+)">([^<]+)</material>', ws)}
    model = {"version": stock["version"], "skeleton": stock["skeleton"], "lods": [], "lod_headers": []}
    table, report = {}, {}
    for li, meshes in enumerate(stock["lods"]):
        sel = select_tris(meshes[0], mount)
        tris = {t for s in sel.values() for k in s.values() for t in k}
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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    od = args[0] if args else REPO / "build" / "solid_hull_stern" / "stern_armour_part"
    print(json.dumps(build(od, mount="--board-only" not in sys.argv), indent=1))
