"""Before and after pictures of the hull: blender --background --python tools/blender_solid_hull_render.py -- OUT.png [--raw DIR]

Columns: stock, closed. Rows: close at the port on the left and the right side, oblique, from afar (LOD 2 and 3 at their own distances). Same camera, same light, the Grungni's base colour.
The stock file and the new file are read as the game would; tools/blender_rmv2.py draws them.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import numpy as np

import blender_rmv2 as br

args = sys.argv[sys.argv.index("--") + 1:]
OUT = Path(args[0])
RAW = br.REPO / "build" / "solid_hull" / "raw"
RAW.mkdir(exist_ok=True, parents=True)
NEW = br.REPO / "build" / "solid_hull" / "warmachines" / "aircraft" / "dwf_thunderbarge" / "tww3_mtb_hull_solid.rigid_model_v2"
stock = br.rmv2.load(br.STOCK.read_bytes())
new = br.rmv2.load(NEW.read_bytes())

# name, LOD, eye, target, lens
VIEWS = [
    ("left_close", 0, (5.0, 1.5, 5.6), (1.6, 1.25, 5.7), 55),
    ("right_close", 0, (-5.0, 1.5, 5.6), (-1.6, 1.25, 5.7), 55),
    ("left_oblique", 0, (4.2, 0.2, 9.0), (1.5, 1.2, 5.4), 55),
    ("left_lod1", 1, (10.0, 2.0, 7.0), (1.6, 1.2, 5.6), 60),
    ("left_lod2", 2, (16.0, 3.0, 8.0), (1.6, 1.2, 4.0), 60),
    ("left_lod3", 3, (34.0, 7.0, 18.0), (0.0, 4.0, 1.0), 55),
    ("right_lod3", 3, (-34.0, 7.0, 18.0), (0.0, 4.0, 1.0), 55),
]
if len(args) > 1 and args[1] == "--only":
    VIEWS = [v for v in VIEWS if v[0] in args[2].split(",")]

s = br.scene(bpy, samples=32)
mat = br.material(bpy)
SIZE = (620, 440)
shots = {}
for name, model in (("stock", stock), ("closed", new)):
    last = None
    for view, lod, eye, target, lens in VIEWS:
        if last != lod:
            for ob in list(bpy.data.objects):
                if ob.type == "MESH":
                    bpy.data.objects.remove(ob)
            for mi, mesh in enumerate(model["lods"][lod]):
                br.add_mesh(bpy, mesh, f"{name}_{lod}_{mi}", mat)
            last = lod
        path = RAW / f"{view}_{name}.png"
        br.shoot(bpy, s, eye, target, path, lens=lens, size=SIZE)
        shots[(view, name)] = path


def read(path):
    im = bpy.data.images.load(str(path))
    w, h = im.size
    a = np.zeros((h, w, 4), dtype=np.float32)
    im.pixels.foreach_get(a.ravel())
    return a


rows = [v[0] for v in VIEWS]
w, h = SIZE
gap = 6
sheet = np.ones((len(rows) * (h + gap) - gap, 2 * w + gap, 4), dtype=np.float32)
for r, view in enumerate(rows):
    y = sheet.shape[0] - (r + 1) * h - r * gap      # Blender's pixels start at the bottom
    sheet[y:y + h, 0:w] = read(shots[(view, "stock")])
    sheet[y:y + h, w + gap:2 * w + gap] = read(shots[(view, "closed")])
im = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=False)
im.pixels.foreach_set(sheet.ravel())
im.filepath_raw = str(OUT)
im.file_format = "PNG"
im.save()
print("rows:", rows)
