"""Stock, previous and new hull side by side: blender --background --python tools/blender_solid_hull_tex_render.py -- OUT.png [view,view]

Rows with textures use base colour, normal map and material map; rows named grey have no textures, a grazing sun and the file's own normals, to show bumps of shape and normals.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import numpy as np

import blender_rmv2 as br
import blender_solid_hull_tex as t

args = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(args[0])
RAW = br.REPO / "build" / "solid_hull_tex" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
PREV = br.REPO / "build" / "solid_hull" / t.FOLDER / "tww3_mtb_hull_solid.rigid_model_v2"
NEW = t.OUT / t.FOLDER / "tww3_mtb_hull_solid.rigid_model_v2"
HULLS = (("stock", br.STOCK), ("previous", PREV), ("new", NEW))
PORT_L, PORT_R = (1.6, 1.25, 5.7), (-1.6, 1.25, 5.7)
FRONT, GRAZE = (0.9, 0.3, 0.6), (1.35, 0.0, 2.0)   # sun: mostly from the front, and low along the side
# name, LOD, eye, target, lens, sun, grey
VIEWS = [
    ("left_close", 0, (5.0, 1.5, 5.6), PORT_L, 55, FRONT, False),
    ("right_close", 0, (-5.0, 1.5, 5.6), PORT_R, 55, (0.9, 0.3, -0.6), False),
    ("left_graze", 0, (5.0, 1.5, 5.6), PORT_L, 55, GRAZE, False),
    ("right_graze", 0, (-5.0, 1.5, 5.6), PORT_R, 55, (1.35, 0.0, -2.0), False),
    ("left_oblique", 0, (4.2, 0.2, 9.0), (1.5, 1.2, 5.4), 55, GRAZE, False),
    ("left_lod1", 1, (10.0, 2.0, 7.0), (1.6, 1.2, 5.6), 60, FRONT, False),
    ("left_lod2", 2, (16.0, 3.0, 8.0), (1.6, 1.2, 4.0), 60, FRONT, False),
    ("left_lod3", 3, (34.0, 7.0, 18.0), (0.0, 4.0, 1.0), 55, FRONT, False),
    ("grey_left", 0, (6.0, 2.0, 5.2), (1.6, 1.8, 5.2), 45, GRAZE, True),
    ("grey_right", 0, (-6.0, 2.0, 5.2), (-1.6, 1.8, 5.2), 45, (1.35, 0.0, -2.0), True),
    ("grey_mid", 0, (6.0, 1.5, 0.0), (1.8, 1.5, 0.0), 45, GRAZE, True),
    ("grey_far", 1, (10.0, 2.0, 7.0), (1.6, 1.2, 5.6), 60, GRAZE, True),
]
if len(args) > 1:
    VIEWS = [v for v in VIEWS if v[0] in args[1].split(",")]

s = br.scene(bpy, samples=24)
sun = bpy.data.objects["sun"]
stock_mat = t.full_material("stock_full", *t.paths_stock())
new_mat = t.full_material("new_full", *t.paths_new())
grey = t.grey_material()
SIZE = (480, 340)
shots = {}
for name, path in HULLS:
    model = br.rmv2.load(Path(path).read_bytes())
    for view, lod, eye, target, lens, angle, is_grey in VIEWS:
        for ob in list(bpy.data.objects):
            if ob.type == "MESH":
                bpy.data.objects.remove(ob)
        mat = grey if is_grey else (new_mat if name == "new" else stock_mat)
        for mi, mesh in enumerate(model["lods"][lod]):
            br.add_mesh(bpy, mesh, f"{name}_{lod}_{mi}", mat)
        sun.rotation_euler = angle
        sun.data.energy = 2.0 if is_grey else 3
        s.world.node_tree.nodes["Background"].inputs[1].default_value = 0.12 if is_grey else 0.8
        file = RAW / f"{view}_{name}.png"
        br.shoot(bpy, s, eye, target, file, lens=lens, size=SIZE)
        shots[(view, name)] = file


def read(path):
    im = bpy.data.images.load(str(path), check_existing=False)
    w, h = im.size
    a = np.zeros((h, w, 4), dtype=np.float32)
    im.pixels.foreach_get(a.ravel())
    bpy.data.images.remove(im)
    return a


w, h = SIZE
gap = 5
rows = [v[0] for v in VIEWS]
sheet = np.ones((len(rows) * (h + gap) - gap, 3 * w + 2 * gap, 4), dtype=np.float32)
for r, view in enumerate(rows):
    y = sheet.shape[0] - (r + 1) * h - r * gap
    for c, (name, _) in enumerate(HULLS):
        x = c * (w + gap)
        sheet[y:y + h, x:x + w] = read(shots[(view, name)])
im = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=False)
im.pixels.foreach_set(sheet.ravel())
im.filepath_raw = str(OUT)
im.file_format = "PNG"
im.save()
print("rows:", rows)
