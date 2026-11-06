"""Removes the bow porthole (frame, glass, hinge and latches, the steel flange) from the closed-port hull in a live Blender
(run through Blender MCP) and closes its place with the hull's planks. Blender axes (game x, z forward, y up shown as
x, y, z). The +x porthole is mirrored to -x; GEO-lod* (the accepted closed-port hull) sit 8 m along +x of STOCK-lod*.

How the porthole is built (stock): a housing (tube, glass, lid ring; 160 faces at LOD0) and 9 small hinge and latch
pieces sit in a hole of the hull; around the hole the hull carries a raised steel flange (hull faces, its bolts painted
on the plank atlas: a ring of radius 50.3 px around (1027.9, 3639.3)). LOD3 has the housing welded to the hull.

  import blender_skill_porthole as bp
  sel = bp.select(li, side)        stock face indexes of the porthole on STOCK-lod{li} (housing, pins, flange), by kind
  bp.fill(li, side, report)        removes them from GEO-lod{li} and closes the hole (blender_skill_fill_port's surface,
                                   normal field and patch), UVs of the patch from the planks around
  bp.move_eye(li)                  the figurehead's eye reads the porthole's glass on the atlas: its UVs follow the copy
  bp.look(path, target, dir, ...)  a shot with an own view (the user's view is restored)
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.geometry import delaunay_2d_cdt

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import blender_skill_fill_port as fp  # noqa: E402
import blender_skill_viewshot as vs  # noqa: E402

WORK = REPO / "build" / "solid_hull_porthole"
GEO_DX = 8.0            # object location of GEO-lod* (their mesh coordinates are the stock ones)
PH_C = np.array((1.953, 5.796, 2.497))     # +x porthole: centre of the housing (plane fit), LOD0
PH_N = np.array((0.930, 0.356, -0.097))    # its axis (outwards)
UV_C, UV_R = (1027.9, 3639.3), 50.3        # the flange as painted on the atlas
FLANGE_UV = 47.0                           # a hull face with a corner inside this atlas radius is flange
HOUSING_UV_FAR = 300.0                     # LOD3: hull-welded faces mapped this far from the ring are the housing
HOUSING_RR = 0.55                          # ... and lie within this of the axis (the housing reaches 0.51)
NEAR_R, NEAR_H = 0.75, 0.5                 # the porthole's pieces lie within this of its axis (plane radius, height)
EYE_GAME = np.array((0.55, 6.95, 6.55))    # the figurehead's eye (+x), Blender axes
EYE_SRC = (992, 3608, 1056, 3672)
EYE_DST = (1280, 2624)


def view_rot(d):
    d = Vector(d).normalized()
    return (-d).to_track_quat("Z", "Y")


def look(path, target, direction, dist=1.6, rake=False, scale=1):
    return vs.shot(str(path), loc=Vector(target), rot=view_rot(direction), dist=dist, rake=rake, scale=scale)


def mesh_arrays(me):
    P = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", P)
    return P.reshape(-1, 3)


def pieces(me, sel_faces):
    """Welded connected pieces among the faces: [[face indexes]]."""
    P = mesh_arrays(me)
    key = [tuple(np.round(p, 4)) for p in P]
    par = {}

    def f_(x):
        while par.setdefault(x, x) != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for i in sel_faces:
        ks = [key[v] for v in me.polygons[i].vertices]
        for k in ks[1:]:
            a, b = f_(ks[0]), f_(k)
            if a != b:
                par[a] = b
    grp = {}
    for i in sel_faces:
        grp.setdefault(f_(key[me.polygons[i].vertices[0]]), []).append(i)
    return list(grp.values())


def loop_uv_px(me):
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers["UVMap"].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2) * 4096
    uv[:, 1] = 4096 - uv[:, 1]
    return uv


def frame(side):
    return PH_C * (side, 1, 1), PH_N * (side, 1, 1)


def select(li, side):
    """Stock face indexes of the porthole on STOCK-lod{li}: {"housing": [...], "pins": [...], "flange": [...]}."""
    me = bpy.data.objects[f"STOCK-lod{li}"].data
    P = mesh_arrays(me)
    c, n = frame(side)
    d = P - c
    h = d @ n
    rr = np.linalg.norm(d - np.outer(h, n), axis=1)
    hull = np.zeros(len(me.polygons), bool)
    me.attributes["hull"].data.foreach_get("value", hull)
    uv = loop_uv_px(me)
    uvr = np.hypot(uv[:, 0] - UV_C[0], uv[:, 1] - UV_C[1])
    near = [f.index for f in me.polygons if all(rr[v] < NEAR_R and abs(h[v]) < NEAR_H for v in f.vertices)]
    out = {"housing": [], "pins": [], "flange": []}
    for p in pieces(me, near):
        if hull[p[0]]:
            for i in p:
                lr = uvr[list(me.polygons[i].loop_indices)]
                if lr.min() > HOUSING_UV_FAR and max(rr[v] for v in me.polygons[i].vertices) < HOUSING_RR:
                    out["housing"].append(i)              # LOD3: the housing is welded to the hull
                elif lr.min() < FLANGE_UV:
                    out["flange"].append(i)
        elif len(p) >= 30 and max(rr[v] for i in p for v in me.polygons[i].vertices) > 0.3 and min(rr[v] for i in p for v in me.polygons[i].vertices) < 0.15:
            out["housing"] += p
        else:
            out["pins"] += p
    return out


# ---- geometry ----------------------------------------------------------------------------------------------------
FIT_R = 1.0             # thin plate spline of the hull shape through the kept outward hull vertices within this
FIELD_R = (0.62, 1.05)  # the smooth normal field is fitted to the current normals in this ring (clear of the flange)
BLEND_IN, BLEND_OUT = 0.62, 0.85   # kept vertices: field normal inside, their own outside
OUTWARD = 0.3
H_MIN = -0.5
GRID = (0.12, 0.16, 0.24, 0.32)
UV_NEAR = 140.0         # px: kept vertices whose UV lies this near the ring belong to the plank sheet around it


def _local(P, pc, n, t1, t2):
    d = P - pc
    return d @ t1, d @ t2, d @ n


def geo_faces(li, stock_faces):
    """GEO-lod{li} faces that are the given STOCK-lod{li} faces (matched by the stock vertex index attribute)."""
    sme, gme = bpy.data.objects[f"STOCK-lod{li}"].data, bpy.data.objects[f"GEO-lod{li}"].data
    want = {frozenset(sme.polygons[i].vertices) for i in stock_faces}
    st = np.empty(len(gme.vertices), np.int32)
    gme.attributes["stock"].data.foreach_get("value", st)
    return [f.index for f in gme.polygons if frozenset(int(st[v]) for v in f.vertices) in want]



def _cycles(edges):
    """Boundary edges split into simple cycles (vertex key lists); a vertex where two loops touch splits a figure eight."""
    adj = {}
    for x, y in edges:
        adj.setdefault(x, []).append(y)
        adj.setdefault(y, []).append(x)
    used, cycles = set(), []
    for x0, y0 in edges:
        if tuple(sorted((x0, y0))) in used:
            continue
        trail, cur = [x0], y0
        used.add(tuple(sorted((x0, y0))))
        while cur != x0:
            trail.append(cur)
            nxt = [y for y in adj[cur] if tuple(sorted((cur, y))) not in used]
            if not nxt:
                break
            used.add(tuple(sorted((cur, nxt[0]))))
            cur = nxt[0]
        if cur != x0:
            continue
        stack, pos = [], {}
        for v in trail + [x0]:
            if v in pos:
                i = pos[v]
                if len(stack) - i >= 3:
                    cycles.append(stack[i:])
                for w in stack[i + 1:]:
                    pos.pop(w, None)
                stack = stack[:i + 1]
            else:
                pos[v] = len(stack)
                stack.append(v)
    return cycles


def _rim_loop(edges, shared):
    """The boundary edges split into simple cycles (a vertex the housing touches splits a figure eight); the cycle with
    the most edges shared with kept faces is the hole's rim (edges open already, as where the closed port's patch of a
    low LOD stops short of the flange, go into it too). Returns its vertex keys in order."""
    adj = {}
    for x, y in edges:
        adj.setdefault(x, []).append(y)
        adj.setdefault(y, []).append(x)
    used = set()
    cycles = []
    for x0, y0 in edges:
        if tuple(sorted((x0, y0))) in used:
            continue
        trail, cur, prev = [x0], y0, x0
        used.add(tuple(sorted((x0, y0))))
        while cur != x0:
            trail.append(cur)
            nxt = [y for y in adj[cur] if tuple(sorted((cur, y))) not in used]
            if not nxt:
                break
            nx = nxt[0]
            used.add(tuple(sorted((cur, nx))))
            prev, cur = cur, nx
        if cur != x0:
            continue
        # split a closed trail at repeated vertices into simple cycles
        stack, pos = [], {}
        for v in trail + [x0]:
            if v in pos:
                i = pos[v]
                cycles.append(stack[i:])
                for w in stack[i + 1:]:
                    pos.pop(w, None)
                stack = stack[:i + 1]
            else:
                pos[v] = len(stack)
                stack.append(v)
    best, score = None, -1
    for c in cycles:
        if len(c) < 3:
            continue
        sh = sum(1 for i in range(len(c)) if tuple(sorted((c[i], c[(i + 1) % len(c)]))) in shared)
        if sh > score:
            best, score = c, sh
    return best

def fill(li, side, report, faces=None):
    """Removes the porthole from GEO-lod{li} on one side and closes the hole. Faces: stock indexes (select())."""
    ob = bpy.data.objects[f"GEO-lod{li}"]
    me = ob.data
    if faces is None:
        s = select(li, side)
        faces = s["housing"] + s["pins"] + s["flange"]
    removed = geo_faces(li, faces)
    missing = len(faces) - len(removed)          # LOD2-3: the closed port's patch already took the flange's lowest faces
    rem_set = set(removed)
    nv = len(me.vertices)
    P = mesh_arrays(me)
    NRM = np.empty(nv * 3)
    me.attributes["nrm"].data.foreach_get("vector", NRM)
    NRM = NRM.reshape(-1, 3)
    st = np.empty(nv, np.int32)
    me.attributes["stock"].data.foreach_get("value", st)
    hull = np.zeros(len(me.polygons), bool)
    me.attributes["hull"].data.foreach_get("value", hull)
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    luv = np.empty(len(me.loops) * 2)
    me.uv_layers["UVMap"].data.foreach_get("uv", luv)
    VUV = np.zeros((nv, 2))
    VUV[lv] = luv.reshape(-1, 2)
    vpx = np.c_[VUV[:, 0] * 4096, (1 - VUV[:, 1]) * 4096]
    vuvr = np.hypot(vpx[:, 0] - UV_C[0], vpx[:, 1] - UV_C[1])
    keyof = [tuple(np.round(p, 4)) for p in P]

    # the frame: the housing centre, the axis from the kept hull normals around
    c0, n0 = frame(side)
    d = P - c0
    h0 = d @ n0
    rr0 = np.linalg.norm(d - np.outer(h0, n0), axis=1)
    used_keys = set()
    for f in me.polygons:
        if hull[f.index] and f.index not in rem_set:
            used_keys.update(keyof[v] for v in f.vertices)
    ring_v = [i for i in range(nv) if keyof[i] in used_keys and 0.6 < rr0[i] < 1.0 and abs(h0[i]) < 0.4 and NRM[i] @ n0 > 0.5]
    n = NRM[ring_v].mean(0)
    n /= np.linalg.norm(n)
    t1 = np.cross(n, (0, 0, 1.0))
    t1 /= np.linalg.norm(t1)
    t2 = np.cross(n, t1)
    pc = c0
    a, b, h = _local(P, pc, n, t1, t2)
    rr = np.hypot(a, b)

    # hole boundary (welded): with the porthole gone, the kept hull faces around end at one or more loops (the flange's
    # outer edge; on LOD2-3 also the hull's own round opening behind the housing, and where the closed port's patch
    # stops short of the flange). The outermost loop is the rim; kept faces inside it go too.
    def wedges(fi):
        vs_ = me.polygons[fi].vertices
        return [tuple(sorted((keyof[vs_[i]], keyof[vs_[(i + 1) % len(vs_)]]))) for i in range(len(vs_))]
    near = (rr < 0.8) & (np.abs(h) < 0.4)
    near_k = {keyof[i] for i in range(nv) if near[i]}
    cnt = {}
    for f in me.polygons:
        if f.index in rem_set or not hull[f.index] or not any(near[v] for v in f.vertices):
            continue
        for e in wedges(f.index):
            cnt[e] = cnt.get(e, 0) + 1
    bedges = [e for e, c_ in cnt.items() if c_ == 1 and e[0] in near_k and e[1] in near_k]
    cyc = _cycles(bedges)
    assert cyc, f"lod{li} side {side}: no rim loop"
    def area(c):
        A = np.array(c)
        x_, y_, _ = _local(A, pc, n, t1, t2)
        return abs(np.sum(x_ * np.roll(y_, -1) - np.roll(x_, -1) * y_)) / 2
    loop = max(cyc, key=area)
    loop_set = set(loop)
    LA, LB, _ = _local(np.array(loop), pc, n, t1, t2)
    poly = np.c_[LA, LB]

    def inside_poly(x, y):
        c_ = False
        for i in range(len(poly)):
            (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % len(poly)]
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                c_ = not c_
        return c_
    inner = []
    for f in me.polygons:
        if f.index in rem_set or not hull[f.index] or not all(near[v] for v in f.vertices):
            continue
        if any(keyof[v] not in loop_set for v in f.vertices) and all(keyof[v] in loop_set or inside_poly(a[v], b[v]) for v in f.vertices):
            ca, cb = np.mean([a[v] for v in f.vertices]), np.mean([b[v] for v in f.vertices])
            if inside_poly(ca, cb):
                inner.append(f.index)
    removed = removed + inner
    rem_set = set(removed)
    used_keys = set()
    for f in me.polygons:
        if hull[f.index] and f.index not in rem_set:
            used_keys.update(keyof[v] for v in f.vertices)
    er, ek = {}, {}
    for fi in removed:
        for e in wedges(fi):
            er[e] = er.get(e, 0) + 1
    rem_keys = {k for e in er for k in e}
    for f in me.polygons:
        if f.index in rem_set:
            continue
        if any(keyof[v] in rem_keys for v in f.vertices):
            for e in wedges(f.index):
                ek[e] = ek.get(e, 0) + 1
    open_rim = sum(1 for i in range(len(loop)) if tuple(sorted((loop[i], loop[(i + 1) % len(loop)]))) not in ek)
    LP = np.array(loop)
    la, lb, lh = _local(LP, pc, n, t1, t2)
    if np.sum(la * np.roll(lb, -1) - np.roll(la, -1) * lb) < 0:
        LP, la, lb, lh = LP[::-1], la[::-1], lb[::-1], lh[::-1]
        loop = loop[::-1]
    loop_set = set(loop)

    # shape: thin plate spline through the kept outward hull vertices around (and the rim)
    cand = {}
    for i in range(nv):
        if keyof[i] in used_keys and (keyof[i] not in rem_keys or keyof[i] in loop_set) and rr[i] < FIT_R and h[i] > H_MIN and NRM[i] @ n > OUTWARD:
            cand.setdefault(keyof[i], i)
    for k in loop:
        cand.setdefault(k, keyof.index(k))
    ci = np.array(list(cand.values()))
    model = fp.tps_fit(a[ci], b[ci], h[ci])
    fit_res = h[ci] - fp.tps_eval(model, a[ci], b[ci])[0]
    # normal field from the current normals in a ring clear of the flange
    ring = {}
    for i in range(nv):
        if keyof[i] in used_keys and keyof[i] not in rem_keys and FIELD_R[0] < rr[i] < FIELD_R[1] and h[i] > H_MIN and NRM[i] @ n > OUTWARD:
            ring.setdefault(keyof[i], i)
    fi_ = np.array(list(ring.values()))
    field = fp.field_fit(a[fi_], b[fi_], NRM[fi_], n, t1, t2, 3 if len(fi_) >= 18 else 2)
    fnr = fp.surf_normal(n, t1, t2, *fp.field_eval(field, a[fi_], b[fi_]))
    field_dev = np.degrees(np.arccos(np.clip((fnr * NRM[fi_]).sum(1), -1, 1)))
    # the rim goes onto the smoothed surface
    snap_h = fp.tps_eval(model, la, lb)[0]
    port_keys = {keyof[i] for i in range(nv) if st[i] < 0}
    fixed = np.array([k in port_keys for k in loop])          # rim vertices of the closed port's patch stay as they are
    keep_res = np.where(fixed, lh - snap_h, 0.0)
    snap_h = np.where(fixed, lh, snap_h)
    LPn = pc + la[:, None] * t1 + lb[:, None] * t2 + snap_h[:, None] * n
    moved = {k: p for k, p, f in zip(loop, LPn, fixed) if not f}
    rim_move_mm = float(np.abs(np.where(fixed, 0.0, lh - fp.tps_eval(model, la, lb)[0])).max() * 1000)

    # UV of the patch: thin plate splines u(a, b), v(a, b) through the rim and the kept plank vertices around
    uvk = {}
    for i in range(nv):
        if keyof[i] in used_keys and rr[i] < FIT_R and vuvr[i] < UV_NEAR and NRM[i] @ n > OUTWARD:
            uvk.setdefault(keyof[i], []).append(i)
    for k in loop:
        us = {tuple(np.round(VUV[i], 5)) for i in uvk.get(k, [])}
        assert len(us) <= 1, f"lod{li} side {side}: a rim vertex has {len(us)} plank UVs"
    uv_keys = [k for k in uvk if k not in rem_keys or k in loop_set]
    ka = np.array([uvk[k][0] for k in uv_keys])
    UU = VUV[ka]
    mu = fp.tps_fit(a[ka], b[ka], UU[:, 0], lam=0.0)
    mv = fp.tps_fit(a[ka], b[ka], UU[:, 1], lam=0.0)
    # rim UVs: the plank copy's own; a rim vertex only open edges reached (low LODs, no kept face) takes the fitted map
    rim_uv, rim_uv_fitted = [], 0
    for k, x_, y_ in zip(loop, la, lb):
        cs = uvk.get(k, [])
        if cs:
            rim_uv.append(VUV[cs[0]])
        else:
            rim_uv.append((float(fp.tps_eval(mu, x_, y_)[0][0]), float(fp.tps_eval(mv, x_, y_)[0][0])))
            rim_uv_fitted += 1
    rim_uv = np.array(rim_uv)

    # patch: rim + hex grid, constrained Delaunay
    pts = [(float(x), float(y)) for x, y in zip(la, lb)]
    nb = len(pts)
    seg = np.c_[la, lb]

    def inside(q):
        x, y, cnt = q[0], q[1], False
        for i in range(nb):
            (x0, y0), (x1, y1) = seg[i], seg[(i + 1) % nb]
            if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                cnt = not cnt
        return cnt

    def dist_to_poly(q):
        dd = 1e9
        for i in range(nb):
            p0, p1 = seg[i], seg[(i + 1) % nb]
            t = np.clip(np.dot(q - p0, p1 - p0) / max(np.dot(p1 - p0, p1 - p0), 1e-12), 0, 1)
            dd = min(dd, np.linalg.norm(q - p0 - t * (p1 - p0)))
        return dd
    grid = GRID[li]
    ext = np.abs(seg).max() + grid
    for j, y in enumerate(np.arange(-ext, ext, grid * math.sqrt(3) / 2)):
        for x in np.arange(-ext + (grid / 2 if j % 2 else 0), ext, grid):
            q = np.array((x, y))
            if inside(q) and dist_to_poly(q) > 0.6 * grid:
                pts.append((float(x), float(y)))
    cdt = delaunay_2d_cdt([Vector(p) for p in pts], [(i, (i + 1) % nb) for i in range(nb)], [], 1, 1e-6)
    cverts, cfaces, orig = cdt[0], cdt[2], cdt[3]
    assert len(cverts) == len(pts) and all(len(o) == 1 for o in orig), "CDT added or merged vertices"
    cfaces = [[orig[i][0] for i in f] for f in cfaces]
    A2 = np.array(pts)
    H2 = fp.tps_eval(model, A2[:, 0], A2[:, 1])[0]
    if fixed.any():                              # meet the port patch's rim, fading over ~0.12 m (blender_skill_fill_port)
        d2 = ((A2[:, None, :] - np.c_[la, lb][None]) ** 2).sum(-1)
        g = np.exp(-d2 / (2 * 0.12 ** 2))
        H2 += (g * keep_res[None]).sum(1) / np.maximum(g.sum(1), 1.0)
    W = pc + A2[:, :1] * t1 + A2[:, 1:] * t2 + H2[:, None] * n
    W[:nb] = LPn
    PN = fp.surf_normal(n, t1, t2, *fp.field_eval(field, A2[:, 0], A2[:, 1]))
    UVp = np.c_[fp.tps_eval(mu, A2[:, 0], A2[:, 1])[0], fp.tps_eval(mv, A2[:, 0], A2[:, 1])[0]]
    UVp[:nb] = rim_uv

    # normals of kept outward hull vertices around: the field normal, fading to their own; port patch vertices untouched
    edited, devs = 0, []
    for i in range(nv):
        if not (keyof[i] in used_keys and rr[i] < BLEND_OUT and h[i] > H_MIN and NRM[i] @ n > OUTWARD) or st[i] < 0:
            continue
        sn = fp.surf_normal(n, t1, t2, *fp.field_eval(field, a[i], b[i]))[0]
        w = np.clip((BLEND_OUT - rr[i]) / (BLEND_OUT - BLEND_IN), 0, 1)
        w = w * w * (3 - 2 * w)
        if keyof[i] in moved:
            w = 1.0
        dev = math.degrees(math.acos(np.clip(NRM[i] @ sn, -1, 1)))
        if dev > 50:
            continue
        devs.append(dev * w)
        new = (1 - w) * NRM[i] + w * sn
        NRM[i] = new / np.linalg.norm(new)
        edited += 1
    copies = {}
    loop_keys = set(loop)
    for i in range(nv):
        if keyof[i] in loop_keys:
            copies.setdefault(keyof[i], []).append(i)
    BN = np.array([NRM[max(copies[k], key=lambda i: NRM[i] @ n)] for k in loop])
    PN[:nb] = BN

    # write: move the rim, delete the porthole, add the patch
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    for i in range(nv):
        if keyof[i] in moved:
            bm.verts[i].co = Vector(moved[keyof[i]])
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in removed], context="FACES_ONLY")
    hl = bm.faces.layers.bool.get("hull")
    sl = bm.verts.layers.int.get("stock")
    uvl = bm.loops.layers.uv["UVMap"]
    new_v = [bm.verts.new(Vector(p)) for p in W]
    for v in new_v:
        v[sl] = -1
    made = 0
    for f in cfaces:
        idx = list(f)
        fnn = (Vector(W[f[1]]) - Vector(W[f[0]])).cross(Vector(W[f[2]]) - Vector(W[f[0]]))
        if fnn.dot(Vector(n)) < 0:
            idx = idx[::-1]
        face = bm.faces.new([new_v[i] for i in idx])
        face.smooth = True
        face[hl] = True
        for l, k in zip(face.loops, idx):
            l[uvl].uv = Vector(UVp[k])
        made += 1
    bm.to_mesh(me)
    bm.free()
    assert len(me.vertices) == nv + len(W), "new vertices are expected at the end"
    NRM2 = np.vstack([NRM, PN])
    me.attributes["nrm"].data.foreach_set("vector", NRM2.ravel())
    me.normals_split_custom_set_from_vertices([tuple(x) for x in NRM2])
    me.update()
    uv_px = np.c_[UVp[:, 0] * 4096, (1 - UVp[:, 1]) * 4096]
    report[f"lod{li}_{'R' if side > 0 else 'L'}"] = {
        "removed_faces": len(removed), "faces_already_gone": missing, "rim_verts": nb, "rim_kept_port_verts": int(fixed.sum()), "rim_edges_open_before": open_rim, "inner_faces_removed": len(inner), "rim_uv_fitted": rim_uv_fitted, "patch_verts": len(W), "patch_tris": made,
        "fit_pts": len(ci), "tps_res_mm": round(float(np.abs(fit_res).max()) * 1000, 2), "rim_move_mm": round(rim_move_mm, 1),
        "field_pts": len(fi_), "field_dev_deg_mean_max": [round(float(field_dev.mean()), 1), round(float(field_dev.max()), 1)],
        "normals_edited": edited, "normal_change_deg_max": round(float(max(devs)) if devs else 0.0, 1),
        "uv_pts": len(ka), "patch_uv_r_px_max": round(float(np.hypot(uv_px[:, 0] - UV_C[0], uv_px[:, 1] - UV_C[1]).max()), 1),
        "hole_radius_m": [round(float(np.hypot(la, lb).min()), 3), round(float(np.hypot(la, lb).max()), 3)]}
    return dict(pc=pc, n=n, t1=t1, t2=t2)


def drop_loose(li):
    me = bpy.data.objects[f"GEO-lod{li}"].data
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
    return len(loose_e), len(loose_v)


def move_eye(li):
    """The figurehead eye (+x) reads the middle of the porthole glass on the atlas; its vertices follow the copy of those
    pixels to EYE_DST. Only vertices near the eye whose every UV lies in EYE_SRC."""
    me = bpy.data.objects[f"GEO-lod{li}"].data
    P = mesh_arrays(me)
    uv = loop_uv_px(me)
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    near = np.linalg.norm(P - EYE_GAME, axis=1) < 0.35
    x0, y0, x1, y1 = EYE_SRC
    inbox = (uv[:, 0] >= x0) & (uv[:, 0] < x1) & (uv[:, 1] >= y0) & (uv[:, 1] < y1)
    faces = [f.index for f in me.polygons if all(near[v] for v in f.vertices) and all(inbox[l] for l in f.loop_indices)]
    verts = {v for i in faces for v in me.polygons[i].vertices}
    loops = np.where(np.isin(lv, list(verts)))[0]
    assert inbox[loops].all(), "an eye vertex is shared with a face reading elsewhere"
    dx, dy = EYE_DST[0] - x0, EYE_DST[1] - y0
    raw = np.empty(len(me.loops) * 2)
    me.uv_layers["UVMap"].data.foreach_get("uv", raw)
    raw = raw.reshape(-1, 2)
    raw[loops, 0] += dx / 4096
    raw[loops, 1] -= dy / 4096
    me.uv_layers["UVMap"].data.foreach_set("uv", raw.ravel())
    me.update()
    return {"faces": len(faces), "verts": len(verts), "loops": int(len(loops))}
