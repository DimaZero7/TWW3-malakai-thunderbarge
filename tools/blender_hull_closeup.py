"""One big straight picture at the port, for looking at the join: blender --background --python tools/blender_hull_closeup.py -- MODEL OUT.png [LOD] [wire|none] [top|port] [full]

With full, the texture copies of tools/blender_solid_hull_tex.py and their normal map and material map."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
import blender_rmv2 as br
a = sys.argv[sys.argv.index("--") + 1:]
lod = int(a[2]) if len(a) > 2 else 0
m = br.rmv2.load(Path(a[0]).read_bytes())
s = br.scene(bpy, samples=16)
mat = br.material(bpy)
if len(a) > 5:
    import blender_solid_hull_tex as t
    mat = t.full_material("full", *t.paths_new())
mesh = m["lods"][lod][0]
ob = br.add_mesh(bpy, mesh, "h", mat)
if len(a) > 3 and a[3] == "wire":
    w = ob.modifiers.new("w", "WIREFRAME")
    w.thickness = 0.004
    w.use_replace = False
    w.material_offset = 1
    black = bpy.data.materials.new("k")
    black.use_nodes = True
    next(n for n in black.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = (1, 1, 0, 1)
    ob.data.materials.append(black)
eye, target = ((5.0, 1.25, 5.65), (1.6, 1.15, 5.65)) if len(a) < 5 or a[4] != "top" else ((5.0, 2.4, 5.2), (1.7, 2.2, 5.2))
br.shoot(bpy, s, eye, target, a[1], lens=70, size=(1000, 760))
