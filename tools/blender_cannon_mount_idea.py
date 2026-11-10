"""Mock-up of the cannon's armoured sleeve (docs/design/cannon-mount.md), run inside the user's Blender on build/stock_cannons/scene.blend.
Adds the collection cannon_mount_idea only; nothing stock is changed.  exec(open(path).read()) or import and call build()."""
import math
import bpy
from mathutils import Matrix, Vector

COLL = "cannon_mount_idea"
YAW, PITCH = 15.0, 10.0          # the proposed sector, degrees each way from the rest pose
L = 0.90                         # mouth of the sleeve, metres from the pivot along the barrel
RX_IN, RZ_IN = 0.55, 0.47        # the mouth's inner half sizes: L * tan(sector) + the barrel's radius 0.31
WALL = 0.06
SEG = 32
# atlas regions of the Grungni hull (u0, u1, v0, v1): the riveted steel belt, the gold band, plain steel
UV_WALL = (0.363, 0.445, 0.031, 0.075)   # four clean plates of the steel belt between its two inserts, laid back and forth around the sleeve
UV_LIP = (0.06, 0.60, 0.207, 0.222)
UV_DOME = (0.52, 0.77, 0.735, 0.790)
RING_N = {"left": Vector((-0.869, 0.337, -0.363)), "right": Vector((0.869, 0.337, -0.363))}   # measured: the hull ring's normal


def collection():
    c = bpy.data.collections.get(COLL)
    if c:
        for o in list(c.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    else:
        c = bpy.data.collections.new(COLL)
        bpy.context.scene.collection.children.link(c)
    return c


class Builder:
    def __init__(self):
        self.v, self.f, self.uv = [], [], []

    def strip(self, ring_a, ring_b, region, flip=False, vrange=(0.0, 1.0), repeat=1):
        """Quads between two closed rings of points; UV: u around, v between the rings."""
        n = len(ring_a)
        base = len(self.v)
        self.v += list(ring_a) + list(ring_b)
        u0, u1, v0, v1 = region
        for i in range(n):
            j = (i + 1) % n
            quad = [base + i, base + j, base + n + j, base + n + i]
            pp = lambda x: 1 - abs((x * repeat) % 2 - 1) if repeat > 1 else x      # back and forth, so that the piece of the atlas has no seam
            fu = [pp(i / n), pp((i + 1) / n), pp((i + 1) / n), pp(i / n)]
            fv = [vrange[0], vrange[0], vrange[1], vrange[1]]
            if flip:
                quad.reverse(); fu.reverse(); fv.reverse()
            self.f.append(quad)
            self.uv.append([(u0 + (u1 - u0) * a, v0 + (v1 - v0) * b) for a, b in zip(fu, fv)])

    def mesh(self, name, mat, coll):
        me = bpy.data.meshes.new(name)
        me.from_pydata([tuple(p) for p in self.v], [], self.f)
        layer = me.uv_layers.new(name="UVMap")
        k = 0
        for poly, uvs in zip(me.polygons, self.uv):
            for li, uv in zip(poly.loop_indices, uvs):
                layer.data[li].uv = uv
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
        me.materials.append(mat)
        me.update()
        import bmesh
        bm = bmesh.new(); bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me); bm.free()
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        return ob


def sleeve(side, coll, mat):
    gun = bpy.data.objects[f"cannon_{side}"]
    P = gun.matrix_world.translation.copy()
    a = (gun.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized()
    a.z = 0; a.normalize()
    up = Vector((0, 0, 1))
    s = a.cross(up).normalized()
    n = RING_N[side].normalized()
    b = Builder()

    def ring(t, rx, rz, cut=False):
        pts = []
        for i in range(SEG):
            th = 2 * math.pi * i / SEG
            off = s * (rx * math.cos(th)) + up * (rz * math.sin(th))
            tt = t
            if cut:      # where this generator meets the ring's plane, 5 cm inside the hull
                tt = min((-0.05 - off.dot(n)) / a.dot(n), L - 0.2)
            pts.append(P + a * tt + off)
        return pts
    rxo, rzo = RX_IN + WALL, RZ_IN + WALL
    flip = side == "right"       # s changes hand with the side
    b.strip(ring(0, rxo, rzo, cut=True), ring(L - 0.14, rxo, rzo), UV_WALL, flip, repeat=4)                      # the wall
    lo = 0.045                                                                                           # the lip, a band proud of the wall
    b.strip(ring(L - 0.14, rxo, rzo), ring(L - 0.14, rxo + lo, rzo + lo), UV_LIP, flip, (0.0, 0.2))
    b.strip(ring(L - 0.14, rxo + lo, rzo + lo), ring(L + 0.02, rxo + lo, rzo + lo), UV_LIP, flip)
    b.strip(ring(L + 0.02, rxo + lo, rzo + lo), ring(L + 0.02, RX_IN, RZ_IN), UV_LIP, flip, (0.8, 1.0))
    b.strip(ring(L + 0.02, RX_IN, RZ_IN), ring(0.25, RX_IN, RZ_IN), UV_DOME, flip)                       # the bore, seen through the mouth
    # the foot: a riveted band where the sleeve sits on the hull ring's plane
    def foot(rx, rz, lift):
        pts = []
        for i in range(SEG):
            th = 2 * math.pi * i / SEG
            off = s * (rx * math.cos(th)) + up * (rz * math.sin(th))
            pts.append(P + a * ((lift - off.dot(n)) / a.dot(n)) + off)
        return pts
    b.strip(foot(rxo, rzo, 0.10), foot(rxo + 0.035, rzo + 0.035, 0.10), UV_LIP, not flip, (0.0, 0.2))
    b.strip(foot(rxo + 0.035, rzo + 0.035, 0.10), foot(rxo + 0.035, rzo + 0.035, -0.05), UV_LIP, not flip)
    return b.mesh(f"mount_{side}", mat, coll), P, a, s


def ghost(side, coll, P, yaw, pitch, tag):
    """A copy of the stock cannon turned about the pivot: yaw about the world's Z, pitch about the barrel's side axis."""
    gun = bpy.data.objects[f"cannon_{side}"]
    ob = bpy.data.objects.new(f"sector_{side}_{tag}", gun.data)
    coll.objects.link(ob)
    a = (gun.matrix_world.to_3x3() @ Vector((0, 1, 0))).normalized()
    sgn = -1 if side == "left" else 1          # positive yaw: outwards, away from the bow
    rz = Matrix.Rotation(math.radians(-yaw * sgn), 4, "Z")
    side_axis = (rz.to_3x3() @ a).cross(Vector((0, 0, 1)))
    rp = Matrix.Rotation(math.radians(pitch), 4, side_axis)
    ob.matrix_world = Matrix.Translation(P) @ rp @ rz @ Matrix.Translation(-P) @ gun.matrix_world
    return ob


def build():
    coll = collection()
    mat = bpy.data.materials["grungni_hull"]
    out = {}
    for side in ("left", "right"):
        ob, P, a, s = sleeve(side, coll, mat)
        for tag, yaw, pitch in (("yaw_out", YAW, 0), ("yaw_in", -YAW, 0), ("up", 0, PITCH), ("down", 0, -PITCH),
                                ("stock_90", 90, 0), ("stock_fwd", -20, 0)):
            g = ghost(side, coll, P, yaw, pitch, tag)
            g.hide_viewport = True
        out[side] = [round(x, 3) for x in P]
    return out
