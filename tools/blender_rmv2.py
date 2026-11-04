"""Shared by the blender_ scripts: vertex attributes of rmv2.py's vertices, and a Blender scene of a game model. Runs in Blender's Python (needs bpy only in the scene functions).

A vertex's .rest after the weights: normal, UV (2 half floats), tangent, bitangent, colour, 4 bytes each. Type 4 has its 4 weights in front of them, type 3 keeps them in .weight0 and 1.
Bytes are b / 127.5 - 1 in the order x, y, z with a sign byte last. Game axes are x, y up, z forward; Blender shows them as (x, z, y).
"""
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import rmv2  # noqa: E402

GAME_DIR = REPO / "build" / "solid_hull" / "game"
STOCK = GAME_DIR / "stock.rigid_model_v2"


def _at(v):
    return 4 if len(v.rest) == 24 else 0


def normal(v):
    r, a = v.rest, _at(v)
    return tuple(r[a + i] / 127.5 - 1 for i in range(3))


def uv(v):
    return struct.unpack_from("<2e", v.rest, _at(v) + 4)


def tangent(v):
    r, a = v.rest, _at(v) + 8
    return tuple(r[a + i] / 127.5 - 1 for i in range(3))


def bitangent(v):
    r, a = v.rest, _at(v) + 12
    return tuple(r[a + i] / 127.5 - 1 for i in range(3))


def set_shading(v, n=None, uv_=None, t=None, b=None):
    """Writes back the vertex's normal, UV, tangent, bitangent; what is None stays."""
    r, a = bytearray(v.rest), _at(v)
    enc = lambda x: max(0, min(255, round((x + 1) * 127.5)))
    if n is not None:
        r[a:a + 3] = bytes(enc(x) for x in n)
    if uv_ is not None:
        r[a + 4:a + 8] = struct.pack("<2e", *uv_)
    if t is not None:
        r[a + 8:a + 11] = bytes(enc(x) for x in t)
    if b is not None:
        r[a + 12:a + 15] = bytes(enc(x) for x in b)
    v.rest = bytes(r)


def to_blender(p):
    return (p[0], p[2], p[1])


def weld(mesh, digits=3):
    """{vertex: welded id} by position: the file splits vertices at UV seams."""
    ids, out = {}, []
    for v in mesh.verts:
        out.append(ids.setdefault((round(v.x, digits), round(v.y, digits), round(v.z, digits)), len(ids)))
    return out


def material(bpy, name="hull"):
    """The base colour and normal map of the Grungni's textures. Only a look for comparing pictures: the game's shader is not imitated."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    uvn = tree.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = "UVMap"
    col = tree.nodes.new("ShaderNodeTexImage")
    col.image = bpy.data.images.load(str(GAME_DIR / "dwf_thunderbarge_grungni_01_base_colour.dds"), check_existing=True)
    col.interpolation = "Cubic"
    tree.links.new(uvn.outputs[0], col.inputs[0])
    tree.links.new(col.outputs[0], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.65
    bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def add_mesh(bpy, mesh, name, mat):
    """A Blender object of one rmv2 mesh, with its normals and UV as in the file."""
    me = bpy.data.meshes.new(name)
    verts = [to_blender((v.x, v.y, v.z)) for v in mesh.verts]
    me.from_pydata(verts, [], [(a, c, b) for a, b, c in mesh.tris])     # the axes swap turns the winding
    me.update()
    layer = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        u, w = uv(mesh.verts[loop.vertex_index])
        layer.data[loop.index].uv = (u, 1 - w)
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.normals_split_custom_set_from_vertices([to_blender(normal(v)) for v in mesh.verts])
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def scene(bpy, samples=24):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = samples
    s.cycles.use_denoising = False
    s.render.image_settings.file_format = "PNG"
    world = bpy.data.worlds.new("w")
    s.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.8, 0.9, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 0.8
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 3
    ob = bpy.data.objects.new("sun", sun)
    ob.rotation_euler = (0.9, 0.3, 0.6)
    s.collection.objects.link(ob)
    return s


def shoot(bpy, s, eye, target, path, lens=50, size=(900, 700)):
    """A camera at eye looking at target, in game coordinates."""
    from mathutils import Vector
    cam = s.camera
    if cam is None:
        data = bpy.data.cameras.new("cam")
        cam = bpy.data.objects.new("cam", data)
        s.collection.objects.link(cam)
        s.camera = cam
    cam.data.lens = lens
    cam.data.clip_start = 0.01
    e, t = Vector(to_blender(eye)), Vector(to_blender(target))
    cam.location = e
    cam.rotation_euler = (t - e).to_track_quat("-Z", "Y").to_euler()
    s.render.resolution_x, s.render.resolution_y = size
    s.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def pieces(mesh, welded=None):
    """Connected pieces: [(triangle indexes, box)]. welded (from weld()) joins across UV seams."""
    ids = welded if welded is not None else list(range(len(mesh.verts)))
    parent = list(range(max(ids) + 1 if ids else 0))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, c in mesh.tris:
        ra, rb = find(ids[a]), find(ids[b])
        if ra != rb:
            parent[ra] = rb
        rc, ra = find(ids[c]), find(ids[a])
        if rc != ra:
            parent[rc] = ra
    groups = {}
    for i, tri in enumerate(mesh.tris):
        groups.setdefault(find(ids[tri[0]]), []).append(i)
    out = []
    for tris in groups.values():
        verts = {v for i in tris for v in mesh.tris[i]}
        xs, ys, zs = zip(*((mesh.verts[v].x, mesh.verts[v].y, mesh.verts[v].z) for v in verts))
        out.append((tris, (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))))
    return out
