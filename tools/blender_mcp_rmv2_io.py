"""Inside Blender: load a rigid_model_v2 into the scene and write edited meshes back, for live work through the Blender MCP.

Each RMV2 vertex becomes one Blender vertex (no welding) with its index in the "src" attribute, so stock vertices are written back byte for byte.
A new vertex has src = -1 and gets its weights from the nearest stock vertex and its tangents recomputed. Mesh data keeps the game's coordinates;
objects are only turned to stand Z up on screen.
"""
import math
import struct
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector
from mathutils.kdtree import KDTree

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import rmv2  # noqa: E402

STOCK = REPO / "build" / "solid_hull_mcp" / "stock"
SOURCE = STOCK / "dwf_thunderbarge_01.rigid_model_v2"
BASE = STOCK / "dwf_thunderbarge_grungni_01_base_colour.dds"
NORMAL = STOCK / "dwf_thunderbarge_grungni_01_normal.dds"


def data_at(vertex):
    """Offset in .rest of normal, uv, tangent, bitangent."""
    return 4 if len(vertex.rest) == 24 else 0


def vertex_attrs(v):
    at = data_at(v)
    r = v.rest
    n = Vector((r[at] / 127.5 - 1, r[at + 1] / 127.5 - 1, r[at + 2] / 127.5 - 1))
    uv = struct.unpack_from("<2e", r, at + 4)
    return n, uv


def material():
    mat = bpy.data.materials.get("grungni")
    if mat:
        return mat
    mat = bpy.data.materials.new("grungni")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(str(BASE), check_existing=True)
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.6
    nt = nodes.new("ShaderNodeTexImage")
    nt.image = bpy.data.images.load(str(NORMAL), check_existing=True)
    nt.image.colorspace_settings.name = "Non-Color"
    # The game's normal maps keep X in alpha and Y in green.
    comb = nodes.new("ShaderNodeCombineColor")
    sep = nodes.new("ShaderNodeSeparateColor")
    links.new(nt.outputs["Color"], sep.inputs[0])
    links.new(nt.outputs["Alpha"], comb.inputs[0])
    links.new(sep.outputs[1], comb.inputs[1])
    comb.inputs[2].default_value = 1.0
    nm = nodes.new("ShaderNodeNormalMap")
    links.new(comb.outputs[0], nm.inputs["Color"])
    links.new(nm.outputs[0], bsdf.inputs["Normal"])
    return mat


def build_object(name, mesh_rmv, collection):
    verts = [(v.x, v.y, v.z) for v in mesh_rmv.verts]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [tuple(t) for t in mesh_rmv.tris])
    attrs = [vertex_attrs(v) for v in mesh_rmv.verts]
    me.attributes.new("src", "INT", "POINT").data.foreach_set("value", range(len(verts)))
    uv = me.uv_layers.new(name="UVMap")
    for loop in me.loops:
        u, w = attrs[loop.vertex_index][1]
        uv.uv[loop.index].vector = (u, 1 - w)
    me.normals_split_custom_set_from_vertices([tuple(a[0].normalized()) for a in attrs])
    me.materials.append(material())
    ob = bpy.data.objects.new(name, me)
    ob.rotation_euler = (math.pi / 2, 0, 0)
    collection.objects.link(ob)
    return ob


def load_scene():
    model = rmv2.load(SOURCE.read_bytes())
    out = {}
    for li, meshes in enumerate(model["lods"]):
        col = bpy.data.collections.new(f"LOD{li}")
        bpy.context.scene.collection.children.link(col)
        for mi, m in enumerate(meshes):
            ob = build_object(f"L{li}_m{mi}", m, col)
            out[ob.name] = (len(m.verts), len(m.tris))
    return out


def show_lod(lod):
    for col in bpy.context.scene.collection.children:
        if col.name.startswith("LOD"):
            on = col.name == f"LOD{lod}"
            col.hide_render = not on
            col.hide_viewport = not on


def open_edges(ob, box=None, digits=3):
    """Edges used by one triangle only, vertices welded by position. box: local min x, y, z, max x, y, z. Returns the edges' ends."""
    me = ob.data
    key = lambda v: tuple(round(c, digits) for c in v.co)
    count = {}
    for p in me.polygons:
        ks = [key(me.vertices[i]) for i in p.vertices]
        for a, b in zip(ks, ks[1:] + ks[:1]):
            if a != b:
                e = (a, b) if a < b else (b, a)
                count[e] = count.get(e, 0) + 1
    out = [e for e, n in count.items() if n == 1]
    if box:
        def within(k):
            return all(box[i] <= k[i] <= box[i + 3] for i in range(3))
        out = [e for e in out if within(e[0]) and within(e[1])]
    return out


def _tangents(me):
    """Per Blender vertex: tangent and bitangent from the UV map."""
    me.calc_tangents(uvmap="UVMap")
    tan, bit = {}, {}
    for loop in me.loops:
        tan.setdefault(loop.vertex_index, loop.tangent.copy())
        bit.setdefault(loop.vertex_index, loop.bitangent.copy())
    me.free_tangents()
    return tan, bit


def _byte(c):
    return max(0, min(255, round((c + 1) * 127.5)))


def _rewrite_normal(v, n):
    """A stock vertex of the rim takes a new normal; tangent and bitangent are kept square to it."""
    at = data_at(v)
    old = vertex_attrs(v)[0].normalized()
    n = n.normalized()
    if old.dot(n) > 0.9995:
        return
    r = bytearray(v.rest)
    r[at:at + 3] = bytes((_byte(n.x), _byte(n.y), _byte(n.z)))
    for off in (8, 12):
        t = Vector((r[at + off] / 127.5 - 1, r[at + off + 1] / 127.5 - 1, r[at + off + 2] / 127.5 - 1))
        t = (t - n * t.dot(n)).normalized()
        r[at + off:at + off + 3] = bytes((_byte(t.x), _byte(t.y), _byte(t.z)))
    v.rest = bytes(r)


def mesh_to_rmv2(ob, stock):
    """A copy of the stock mesh with the object's geometry. Stock vertices keep their bytes except position."""
    me = ob.data
    me.update()
    src = [0] * len(me.vertices)
    me.attributes["src"].data.foreach_get("value", src)
    tree = KDTree(len(stock.verts))
    for i, v in enumerate(stock.verts):
        tree.insert((v.x, v.y, v.z), i)
    tree.balance()
    corner_uv = {}
    corner_n = {}
    uv = me.uv_layers["UVMap"].uv
    nrm = me.attributes.get("nrm")
    for loop in me.loops:
        corner_uv.setdefault(loop.vertex_index, uv[loop.index].vector.copy())
        if nrm:
            corner_n.setdefault(loop.vertex_index, nrm.data[loop.vertex_index].vector.copy())
    tan, bit = _tangents(me)
    out = stock.copy()
    verts, new_count = [], 0
    for i, mv in enumerate(me.vertices):
        if src[i] >= 0:
            v = stock.verts[src[i]].copy()
            if (Vector((v.x, v.y, v.z)) - mv.co).length > 1e-4:   # moved
                v.x, v.y, v.z = mv.co
            u = corner_uv.get(i, Vector(vertex_attrs(v)[1]))   # a loose vertex has no corner
            old = vertex_attrs(v)[1] if i in corner_uv else (u.x, 1 - u.y)
            if abs(old[0] - u.x) + abs(old[1] - (1 - u.y)) > 1e-5:    # a hull corner of the rim, pushed outward in UV
                at = data_at(v)
                r = bytearray(v.rest)
                r[at + 4:at + 8] = struct.pack("<2e", u.x, 1 - u.y)
                v.rest = bytes(r)
            if nrm and i in corner_n:
                _rewrite_normal(v, corner_n[i])
        else:
            _, near, _ = tree.find(mv.co)
            v = stock.verts[near].copy()
            v.x, v.y, v.z = mv.co
            at = data_at(v)
            n, t, b = corner_n[i], tan[i], bit[i]
            u = corner_uv[i]
            r = bytearray(v.rest)
            r[at:at + 3] = bytes((_byte(n.x), _byte(n.y), _byte(n.z)))
            r[at + 4:at + 8] = struct.pack("<2e", u.x, 1 - u.y)
            # On the game's vertices the first slot runs against Blender's bitangent (dot -0.87), the second with its tangent (0.87).
            r[at + 8:at + 11] = bytes((_byte(-b.x), _byte(-b.y), _byte(-b.z)))
            r[at + 12:at + 15] = bytes((_byte(t.x), _byte(t.y), _byte(t.z)))
            v.rest = bytes(r)
            new_count += 1
        verts.append(v)
    out.verts = verts
    me.calc_loop_triangles()
    out.tris = [tuple(t.vertices) for t in me.loop_triangles]
    return out, new_count


def write_model(path):
    """Writes the model from the L{lod}_m{mesh} objects."""
    model = rmv2.load(SOURCE.read_bytes())
    report = {}
    for li, meshes in enumerate(model["lods"]):
        for mi, stock in enumerate(meshes):
            if mi:
                continue    # only the hull's first mesh is edited; the others stay as the game has them
            ob = bpy.data.objects[f"L{li}_m{mi}"]
            new, created = mesh_to_rmv2(ob, stock)
            if len(new.verts) > 65535:
                raise ValueError("too many vertices")
            meshes[mi] = new
            report[ob.name] = {"verts": [len(stock.verts), len(new.verts)], "tris": [len(stock.tris), len(new.tris)], "new_verts": created}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(rmv2.save(model))
    return report


def setup_render():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("sky") if not scene.world else scene.world
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.78, 0.82, 1)
    world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sun = bpy.data.objects.get("Light")
    sun.data.type = "SUN"
    sun.data.energy = 2.5
    sun.rotation_euler = (math.radians(50), 0, math.radians(30))
    scene.view_settings.view_transform = "Standard"


def aim(target, direction, dist, lens=50, res=(480, 360)):
    """Camera at target (game coordinates) + direction * dist. Screen is Z up: game (x, y, z) -> (x, -z, y)."""
    tg = Vector((target[0], -target[2], target[1]))
    d = Vector((direction[0], -direction[2], direction[1])).normalized()
    cam = bpy.data.objects["Camera"]
    cam.location = tg + d * dist
    cam.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    cam.data.lens = lens
    cam.data.clip_start = 0.05
    scene = bpy.context.scene
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.resolution_percentage = 100


def shot(path, target, direction, dist, lens=50, res=(480, 360), lod=None):
    if lod is not None:
        show_lod(lod)
    aim(target, direction, dist, lens, res)
    scene = bpy.context.scene
    scene.render.filepath = str(path)
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
