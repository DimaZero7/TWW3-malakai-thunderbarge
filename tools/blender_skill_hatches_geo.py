"""Closes the four bomb hatches of GEO-lod0..3 in the live Blender (scene build/solid_hull_hatches/work.blend; through MCP:
sys.path += tools; import blender_skill_hatches_geo as G; G.run(); then blender_skill_write_rmv2.write(out, tex)).

Blender axes: x, y = game z (forward), z = game y (up). Mesh coordinates are the stock frame (GEO-lod0 is only shown at
x + 8 by its object). Every run starts from TANKHULL-lod* (the hull before this pass, copied once).

Per hatch: the niche (end walls, side walls, the dark ceiling: every face in the hatch box whose UV is not on the bottom
band) goes; its hole in the hull bottom is a ring of 7..8 band vertices, a front and a rear cross-section of the
bottom (the hull is a straight prism there: the band faces in front of and behind the hole span the same four lines).
The fill zips the two chains by height, so its facets lie on the same lines as the band faces around it, flush.
New vertices: the position and stored normal of the rim vertex they sit on; UV = the band UV + the hatch's patch
offset (blender_skill_hatches_tex.ZONES[...]["patch"], whole pixels; the patch at the free spot holds the band's steel run over the hole).
"""


import bpy
import bmesh
import numpy as np

HATCH = {"front": (0.45, 1.7, -0.25, 2.0, 3.65, 0.95), "rear": (0.45, -4.0, -0.25, 2.0, -2.1, 0.95)}   # |x|, y, z (Blender)
PATCH = {"front": (-696, -3780), "rear": (-248, -3796)}       # = blender_skill_hatches_tex.ZONES[...]["patch"] (atlas px)
BAND_UV = (1080, 3755, 2520, 4010)                            # the bottom band in atlas px (rows from the top)


def snapshot():
    for i in range(4):
        n = f"TANKHULL-lod{i}"
        if n not in bpy.data.objects:
            g = bpy.data.objects[f"GEO-lod{i}"]
            ob = g.copy(); ob.data = g.data.copy(); ob.name = n; ob.data.name = n
            for c in g.users_collection:
                c.objects.link(ob)
            ob.hide_set(True)


def reset(i):
    g, s = bpy.data.objects[f"GEO-lod{i}"], bpy.data.objects[f"TANKHULL-lod{i}"]
    old = g.data
    g.data = s.data.copy(); g.data.name = f"GEO-lod{i}"
    if old.users == 0:
        bpy.data.meshes.remove(old)


def _px(uv):
    return uv[0] * 4096, (1 - uv[1]) * 4096


def _in_band(pxs):
    return all(BAND_UV[0] <= u <= BAND_UV[2] and BAND_UV[1] <= v <= BAND_UV[3] for u, v in pxs)


def _zone_of(c, dx):
    x = c[0] - dx
    for k, b in HATCH.items():
        if b[0] <= abs(x) <= b[3] and b[1] <= c[1] <= b[4] and b[2] <= c[2] <= b[5]:
            return k, (1 if x > 0 else -1)
    return None


def close(i):
    ob = bpy.data.objects[f"GEO-lod{i}"]
    dx = 0.0                     # mesh coordinates are the stock frame (the object location only shifts the view)
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv["UVMap"]
    st_l = bm.verts.layers.int.get("stock")
    nr_l = bm.verts.layers.float_vector.get("nrm")
    bm.faces.ensure_lookup_table()
    niche = {}
    for f in bm.faces:
        z = _zone_of(f.calc_center_median(), dx)
        if z and not _in_band([_px(l[uvl].uv) for l in f.loops]):
            niche.setdefault(z, []).append(f)
    rep = {}
    new_faces = []
    for (zn, side), faces in sorted(niche.items()):
        fs = set(faces)
        # boundary edges of the hole: edges of niche faces whose other face is a band face (welded by position)
        key = lambda v: tuple(np.round(np.array(v.co), 4))
        band_edges = {}
        b = HATCH[zn]
        for f in bm.faces:
            if f in fs:
                continue
            c = f.calc_center_median()
            if not (b[1] - 1.5 <= c[1] <= b[4] + 1.5 and abs(c[2]) < 1.5):
                continue
            for l in f.loops:
                e = tuple(sorted((key(l.vert), key(l.link_loop_next.vert))))
                band_edges.setdefault(e, []).append((f, l))
        rim = {}
        for f in faces:
            for l in f.loops:
                e = tuple(sorted((key(l.vert), key(l.link_loop_next.vert))))
                if e in band_edges:
                    for bf, bl in band_edges[e]:
                        for ll in (bl, bl.link_loop_next):
                            rim[key(ll.vert)] = (ll.vert, tuple(ll[uvl].uv))
        bmesh.ops.delete(bm, geom=faces, context="FACES_ONLY")
        pts = list(rim.values())
        ys = np.array([v.co[1] for v, _ in pts])
        yf, yr = ys.max(), ys.min()
        front = sorted([p for p in pts if abs(p[0].co[1] - yf) < 0.05], key=lambda p: p[0].co[2])
        rear = sorted([p for p in pts if abs(p[0].co[1] - yr) < 0.05], key=lambda p: p[0].co[2])
        if len(front) + len(rear) != len(pts) or len(front) < 2 or len(rear) < 2:
            raise RuntimeError(f"LOD {i} {zn} {side}: rim not two chains ({len(front)}, {len(rear)}, {len(pts)})")
        ox, oy = PATCH[zn]

        def nv(p):
            v, uv = p
            n = bm.verts.new(v.co)
            n[st_l] = -1
            n[nr_l] = v[nr_l]
            return n, (uv[0] + ox / 4096.0, uv[1] - oy / 4096.0)
        F = [nv(p) for p in front]
        R = [nv(p) for p in rear]
        # zip the two chains by height
        a = b_ = 0
        tris = []
        while a < len(F) - 1 or b_ < len(R) - 1:
            if b_ == len(R) - 1 or (a < len(F) - 1 and F[a + 1][0].co[2] <= R[b_ + 1][0].co[2]):
                tris.append((F[a], F[a + 1], R[b_])); a += 1
            else:
                tris.append((F[a], R[b_ + 1], R[b_])); b_ += 1
        for t in tris:
            vs = [x[0] for x in t]
            nrm = sum((np.array(v[nr_l]) for v in vs), np.zeros(3))
            e1, e2 = np.array(vs[1].co - vs[0].co), np.array(vs[2].co - vs[0].co)
            if np.dot(np.cross(e1, e2), nrm) < 0:
                t = (t[0], t[2], t[1])
            f = bm.faces.new([x[0] for x in t])
            for l, x in zip(f.loops, t):
                l[uvl].uv = x[1]
            new_faces.append(f)
        rep[f"{zn}{'+' if side > 0 else '-'}"] = dict(niche_faces=len(faces), rim=[len(front), len(rear)], fill_tris=len(tris))
    bm.to_mesh(me)
    bm.free()
    # the new faces (all corners new, stock -1; bmesh may put them in the slots of the deleted ones) are hull faces
    st = np.empty(len(me.vertices), np.int32)
    me.attributes["stock"].data.foreach_get("value", st)
    hull = np.zeros(len(me.polygons), bool)
    me.attributes["hull"].data.foreach_get("value", hull)
    fill = [p.index for p in me.polygons if all(st[v] < 0 for v in p.vertices) and _zone_of(p.center, dx)]
    hull[fill] = True
    me.attributes["hull"].data.foreach_set("value", hull)
    rep["fill_faces"] = len(fill)
    drop_loose(me)
    return rep


def drop_loose(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    loose_e = [e for e in bm.edges if not e.link_faces]
    bmesh.ops.delete(bm, geom=loose_e, context="EDGES")
    loose_v = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose_v, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    nr = np.empty(len(me.vertices) * 3)
    me.attributes["nrm"].data.foreach_get("vector", nr)
    me.normals_split_custom_set_from_vertices([tuple(x) for x in nr.reshape(-1, 3)])
    me.update()


def run():
    snapshot()
    out = {}
    for i in range(4):
        reset(i)
        out[f"lod{i}"] = close(i)
        out[f"lod{i}"]["faces"] = len(bpy.data.objects[f"GEO-lod{i}"].data.polygons)
    return out
