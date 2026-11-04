"""Inside Blender: closes the gun port's hole of the hull in place. The port's pieces are already cut; the hole's rim is the hull's own vertices.
The plug repeats the rim's vertices, follows a quadratic fit of the hull around the hole and takes its UV from a clean stretch of planks and steel: DONOR maps the hull's
own UV inside the hole, where the atlas holds the port's smeared paint, onto the plates and planks next along. Rim normals become the hull's real ones and the hull's rim corners move out in UV, past the smears.
"""
import struct

import bmesh
import bpy
import numpy as np
from mathutils import Vector

import blender_mcp_rmv2_io as io
import rmv2

HOLE = {1: (0.9, 0.45, 5.0, 2.05, 2.0, 6.5), -1: (-2.05, 0.45, 5.0, -0.9, 2.0, 6.5)}
_stock = {}


def stock_mesh(li):
    if li not in _stock:
        _stock[li] = rmv2.load(io.SOURCE.read_bytes())["lods"][li][0]
    return _stock[li]


def donor(u, v, p):
    # squeeze: planks a little narrower above the steel, to leave out a knot at the donor's upper edge
    squeezed = p.get("vs0", v) + (v - p.get("vs0", v)) * p.get("squeeze", 1.0)
    return (u + p["du"] + p.get("rot", 0) * (v - p.get("v0", 0)), squeezed + p["dv"] + p["shear"] * (u - p["u0"]))


def key(co):
    return tuple(round(c, 3) for c in co)


def rim(bm, uvl, box):
    """Ordered loops [(vert, uv)] around the hole, in the direction hull faces run them reversed."""
    count = {}
    for f in bm.faces:
        for l in f.loops:
            a, b = key(l.vert.co), key(l.link_loop_next.vert.co)
            if a != b:
                k = (a, b) if a < b else (b, a)
                count.setdefault(k, []).append(l)
    nxt = {}
    for k, ls in count.items():
        if len(ls) == 1 and all(box[i] <= c[i] <= box[i + 3] for c in k for i in range(3)):
            l = ls[0]
            nxt[key(l.link_loop_next.vert.co)] = l    # the plug runs the edge the other way: from the next vert back to this one
    start = next(iter(nxt))
    out, at = [], start
    while True:
        l = nxt[at]
        out.append((l.link_loop_next.vert, l.link_loop_next[uvl].uv.copy()))
        at = key(l.vert.co)
        if at == start:
            break
        if len(out) > len(nxt):
            raise ValueError("rim does not close")
    if len(out) != len(nxt):
        raise ValueError(f"rim: {len(out)} of {len(nxt)}")
    return out


def surface(loop, normals):
    """Hermite patch over the rim: from each rim point along its tangent plane to a centre raised by what the rim's normals ask for."""
    mid = sum((v.co for v, _ in loop), Vector((0, 0, 0))) / len(loop)
    axis = sum(normals, Vector((0, 0, 0))).normalized()
    rise = []
    tangents = []
    for (v, _), nr in zip(loop, normals):
        to_mid = mid - v.co
        t = to_mid - nr * to_mid.dot(nr)
        t.normalize()
        radial = to_mid - axis * to_mid.dot(axis)
        run = radial.length
        slope = t.dot(axis) / max(t.dot(radial.normalized()), 0.2)
        rise.append((v.co - mid).dot(axis) + slope * run / 2)
        tangents.append(t)
    centre = mid + axis * (sum(rise) / len(rise))

    def at(k, s):
        """Point s of the way from the centre (0) to rim vertex k (1)."""
        p0 = loop[k][0].co
        d = (centre - p0)
        m0 = tangents[k] * d.length
        m1 = d - axis * d.dot(axis)
        t = 1 - s
        h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
        return p0 * h00 + m0 * h10 + centre * h01 + m1 * h11
    return centre, axis, at


def ensure_nrm(ob, li):
    me = ob.data
    if "nrm" in me.attributes:
        return
    stock = stock_mesh(li)
    src = [0] * len(me.vertices)
    me.attributes["src"].data.foreach_get("value", src)
    a = me.attributes.new("nrm", "FLOAT_VECTOR", "POINT")
    for i, s in enumerate(src):
        a.data[i].vector = io.vertex_attrs(stock.verts[s])[0].normalized()


def fill(ob, li, side, p, rings):
    """Replaces this side's plug. rings: scales of the rims inside, largest first. Returns numbers."""
    ensure_nrm(ob, li)
    me = ob.data
    uvmap = me.uv_layers[0].uv
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv[0]
    srcl = bm.verts.layers.int["src"]
    nl = bm.verts.layers.float_vector["nrm"]
    box = HOLE[side]
    old = [v for v in bm.verts if v[srcl] == -1 and all(box[i] - 0.02 <= v.co[i] <= box[i + 3] + 0.02 for i in range(3))]
    if old:
        bmesh.ops.delete(bm, geom=old, context="VERTS")
    loop = rim(bm, uvl, box)
    center = sum((t for _, t in loop), Vector((0, 0))) / len(loop)
    radius = max((t - center).length for _, t in loop)
    stock = stock_mesh(li)
    # The stock normals at the rim lean into the port's flange, 16 to 41 degrees off the hull. The rim takes the hull's real normal, in the hull's vertices too.
    rimn = []
    for v, _ in loop:
        rimn.append(sum((f.normal * f.calc_area() for f in v.link_faces), Vector((0, 0, 0))).normalized())
    bykey_n = {key(v.co): nr for (v, _), nr in zip(loop, rimn)}
    for v in bm.verts:
        if v[srcl] >= 0 and key(v.co) in bykey_n:
            v[nl] = bykey_n[key(v.co)]
    # The hull's own faces touching the rim sample the port's smears: their rim corners are pushed outward in UV.
    bykey = {key(v.co): t for v, t in loop}
    for v in bm.verts:
        if v[srcl] >= 0 and key(v.co) in bykey:
            u0, w0 = io.vertex_attrs(stock.verts[v[srcl]])[1]
            t0 = Vector((u0, 1 - w0))
            if (t0 - center).length < radius * 1.5:
                for l in v.link_loops:
                    l[uvl].uv = center + (t0 - center) * p.get("warp", 1.0)
    loop = [(v, Vector((io.vertex_attrs(stock.verts[v[srcl]])[1][0], 1 - io.vertex_attrs(stock.verts[v[srcl]])[1][1]))) for v, _ in loop]
    center = sum((t for _, t in loop), Vector((0, 0))) / len(loop)
    centre, axis, at = surface(loop, rimn)
    # Plug runs: the outer ring repeats the rim, inner rings shrink it to the centre, last a fan.
    layers = [[] for _ in range(len(rings) + 1)]
    for i, (v, t) in enumerate(loop):
        nv = bm.verts.new(v.co)
        nv[srcl] = -1
        nv[nl] = rimn[i]
        layers[0].append((nv, t))
    for ri, s in enumerate(rings):
        for i, (v, t) in enumerate(loop):
            q = center + (t - center) * s
            nv = bm.verts.new(at(i, s))
            nv[srcl] = -1
            nv[nl] = (axis * (1 - s) + rimn[i] * s).normalized()
            layers[ri + 1].append((nv, q))
    cv = bm.verts.new(centre)
    cv[srcl] = -1
    cv[nl] = axis
    N = len(loop)
    faces = []

    def tri(a, b, c):
        face = bm.faces.new((a[0], b[0], c[0]))
        for l, s in zip(face.loops, (a, b, c)):
            l[uvl].uv = s[1]
        faces.append(face)
    for r in range(len(rings)):
        o, i_ = layers[r], layers[r + 1]
        for k in range(N):
            k2 = (k + 1) % N
            tri(o[k], o[k2], i_[k2])
            tri(o[k], i_[k2], i_[k])
    last = layers[-1]
    for k in range(N):
        tri(last[k], last[(k + 1) % N], (cv, center))
    # The steel's top line: the plug is cut along it, between the rim vertices nearest to where the line meets the rim, and each part takes its own stretch of the atlas.
    ia = min(range(N), key=lambda k: (loop[k][1] - Vector(p["chord"][0])).length)
    ib = min(range(N), key=lambda k: (loop[k][1] - Vector(p["chord"][1])).length)
    pa, pb = layers[0][ia][0].co.copy(), layers[0][ib][0].co.copy()
    plane_no = (pb - pa).cross(axis).normalized()
    low = min(loop, key=lambda e: e[1].y)[0].co
    if (low - pa).dot(plane_no) < 0:
        plane_no = -plane_no    # points to the steel
    geom = list(faces) + list({e for f in faces for e in f.edges}) + list({v for f in faces for v in f.verts})
    cut = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=pa, plane_no=plane_no, dist=1e-4, clear_inner=False, clear_outer=False)
    cut_edges = [e for e in cut["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    bmesh.ops.split_edges(bm, edges=cut_edges)
    def plug_faces():
        return [f for f in bm.faces if all(v[srcl] == -1 and all(box[i] - 0.02 <= v.co[i] <= box[i + 3] + 0.02 for i in range(3)) for v in f.verts)]

    # A second cut along the plank line above the steel: the strip under it takes a darker stretch, like the planks to both sides of the hole.
    ic = min(range(N), key=lambda k: (loop[k][1] - Vector(p["line"][0])).length)
    id_ = min(range(N), key=lambda k: (loop[k][1] - Vector(p["line"][1])).length)
    pc, pd = loop[ic][0].co.copy(), loop[id_][0].co.copy()
    line_no = (pd - pc).cross(axis).normalized()
    if (low - pc).dot(line_no) < 0:
        line_no = -line_no
    if {ic, id_} != {ia, ib}:
        planks = [f for f in plug_faces() if (f.calc_center_median() - pa).dot(plane_no) <= 0]
        geom = planks + list({e for f in planks for e in f.edges}) + list({v for f in planks for v in f.verts})
        cut2 = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=pc, plane_no=line_no, dist=1e-4, clear_inner=False, clear_outer=False)
        bmesh.ops.split_edges(bm, edges=[e for e in cut2["geom_cut"] if isinstance(e, bmesh.types.BMEdge)])
    plug = plug_faces()
    for f in plug:
        mid_f = f.calc_center_median()
        if (mid_f - pa).dot(plane_no) > 0:
            which = p["steel"]
        elif (mid_f - pc).dot(line_no) > 0:
            which = p["strip"]
        else:
            which = p["plank"]
        for l in f.loops:
            t = l[uvl].uv.copy()
            l[uvl].uv = donor(t.x, t.y, which)
    bm.to_mesh(me)
    bm.free()
    me.update()
    a = me.attributes["nrm"]
    me.normals_split_custom_set_from_vertices([tuple(a.data[i].vector) for i in range(len(me.vertices))])
    return {"rim": N, "chord": [ia, ib], "plug_faces": len(plug), "cut": len(cut_edges)}


# The values found by looking: UV inside the hole -> a stretch of the atlas. The steel part keeps the plate joint below the hole; the plank part and the strip under the plank line match the tone and the lines around the hole.
CENTER = (0.25732421875, 0.079498291015625)
PARAMS = {
    "warp": 1.12,
    "chord": ((0.2423, 0.0693), (0.2761, 0.0771)),
    "steel": {"du": 0.0403, "dv": 0.0094, "shear": -0.154, "u0": 0.2405},
    "line": ((0.2401, 0.082), (0.2749, 0.085)),
    "strip": {"du": 0.048, "dv": 0.0068, "shear": -0.17, "rot": -0.0125, "u0": CENTER[0], "v0": CENTER[1]},
    "plank": {"du": -0.042, "dv": -0.0022, "shear": 0.2, "u0": CENTER[0], "squeeze": 0.85, "vs0": 0.083},
}
PIECES = [(0.9, 0.45, 5.0, 2.05, 1.98, 6.5), (-2.05, 0.45, 5.0, -0.9, 1.98, 6.5)]    # data/hull_parts.json, details, port


def cut_port(ob):
    """Removes the connected pieces that lie entirely inside the port's boxes."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    seen, dead = set(), []
    for v in bm.verts:
        if v in seen:
            continue
        stack, piece = [v], []
        seen.add(v)
        while stack:
            x = stack.pop()
            piece.append(x)
            for e in x.link_edges:
                o = e.other_vert(x)
                if o not in seen:
                    seen.add(o)
                    stack.append(o)
        if any(all(b[i] <= x.co[i] <= b[i + 3] for x in piece for i in range(3)) for b in PIECES):
            dead += piece
    bmesh.ops.delete(bm, geom=dead, context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()


def close_all(cut=False):
    """All LODs, both sides, on the L{lod}_m0 objects made by blender_mcp_rmv2_io.load_scene()."""
    out = {}
    for li in range(4):
        ob = bpy.data.objects[f"L{li}_m0"]
        if cut:
            cut_port(ob)
        rings = [0.75, 0.5, 0.25] if li < 2 else [0.5]
        for side in (1, -1):
            out[f"L{li}{'+' if side > 0 else '-'}"] = fill(ob, li, side, PARAMS, rings)
    return out
