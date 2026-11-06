"""Renders for the comparison: blender --background --python tools/ai_tex_render.py -- TEX_DIR RAW_DIR [view,view]

Columns: stock hull and sheets; the closed hull with the script's sheets; the same closed hull with the AI sheets. The closed hull (build/solid_hull_tex) has its texture coordinates running through the hole. Also saves the sheets' crops for the texture row.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import numpy as np

import blender_dds as bd
import blender_rmv2 as br
import blender_solid_hull_tex as t

args = sys.argv[sys.argv.index("--") + 1:]
TEX, RAW = Path(args[0]), Path(args[1])
RAW.mkdir(parents=True, exist_ok=True)
HULL = t.OUT / t.FOLDER / "tww3_mtb_hull_solid.rigid_model_v2"
PORT_L, PORT_R = (1.6, 1.25, 5.7), (-1.6, 1.25, 5.7)
FRONT, GRAZE = (0.9, 0.3, 0.6), (1.35, 0.0, 2.0)
VIEWS = [
    ("left_close", 0, (5.0, 1.5, 5.6), PORT_L, 55, FRONT),
    ("right_close", 0, (-5.0, 1.5, 5.6), PORT_R, 55, (0.9, 0.3, -0.6)),
    ("left_graze", 0, (5.0, 1.5, 5.6), PORT_L, 55, GRAZE),
    ("right_graze", 0, (-5.0, 1.5, 5.6), PORT_R, 55, (1.35, 0.0, -2.0)),
    ("left_tight", 0, (3.6, 1.35, 5.7), PORT_L, 55, FRONT),
    ("left_oblique", 0, (4.2, 0.2, 9.0), (1.5, 1.2, 5.4), 55, GRAZE),
    ("left_far", 1, (10.0, 2.0, 7.0), (1.6, 1.2, 5.6), 60, FRONT),
]
if len(args) > 2:
    VIEWS = [v for v in VIEWS if v[0] in args[2].split(",")]
ai_paths = (TEX / f"{t.OWN}_base_colour.dds", TEX / f"{t.OWN}_normal.dds", TEX / f"{t.OWN}_material_map.dds")
COLS = [("stock", br.STOCK, t.paths_stock()), ("script", HULL, t.paths_new()), ("ai", HULL, ai_paths)]

s = br.scene(bpy, samples=24)
sun = bpy.data.objects["sun"]
for col, path, tex in COLS:
    mat = t.full_material("mat_" + col, *tex)
    model = br.rmv2.load(Path(path).read_bytes())
    for view, lod, eye, target, lens, angle in VIEWS:
        for ob in list(bpy.data.objects):
            if ob.type == "MESH":
                bpy.data.objects.remove(ob)
        for mi, mesh in enumerate(model["lods"][lod]):
            br.add_mesh(bpy, mesh, f"{col}_{lod}_{mi}", mat)
        sun.rotation_euler = angle
        sun.data.energy = 3
        s.world.node_tree.nodes["Background"].inputs[1].default_value = 0.8
        br.shoot(bpy, s, eye, target, RAW / f"{view}_{col}.png", lens=lens, size=(560, 400))
    d = bd.Dds(str(tex[0]))
    np.save(RAW / f"crop_{col}.npy", d.read(0, *t.BOX).astype(np.uint8))
print("views", [v[0] for v in VIEWS])
