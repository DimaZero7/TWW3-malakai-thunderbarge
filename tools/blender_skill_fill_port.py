"""Closes the bow gun port of the stock barge hull in a live Blender (run through Blender MCP). Stage 1: geometry and normals.

Blender axes (game x, y up, z forward shown as x, z, y). The port of the +x side is mirrored to -x.
Per LOD and side:
  1. frame: port axis and centre from a plane + circle fit to the ring lip (refined per LOD from the stock values);
  2. port faces: hull faces with a vertex inside the ring foot (rr < R_CUT) above the tube bottom;
  3. hole boundary: welded edges shared by removed and kept faces, one closed loop;
  4. shape: smoothed thin plate spline h = f(a, b) through the kept outer hull vertices around the port (no porthole
     housing, no inner faces); the hole boundary vertices are moved onto it (a few cm: the stock bulge at the ring);
     normal field: slopes of a cubic fitted to the stock normals in a ring clear of the flange's tilt. The stock
     low-poly hull's positions are lumpy and do not agree with its normals, so shape and shading are fitted apart;
  5. patch: the boundary loop plus a hex grid inside, constrained Delaunay; heights from the spline;
  6. normals: patch and boundary vertices get the field normal; kept hull vertices around get it too, fading to
     stock outwards and towards the porthole housing.
The patch has its own vertices (boundary copies at the stock positions), as the game splits vertices anyway.
Vertex attribute "stock" = stock vertex index or -1 for new ones; "nrm" = the vertex normal written to the game.
"""
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
import blender_rmv2 as br  # noqa: E402
import rmv2  # noqa: E402

PC0 = np.array((1.559, 5.768, 1.245))     # port centre, +x side, LOD0 (lip circle fit)
N0 = np.array((0.876, 0.333, -0.349))     # port axis
R_CUT = 0.785          # ring foot radius in the port plane (lip outer edge 0.745, foot 0.77, hull from 0.796)
H_MIN = -0.7           # tube bottom is at h = -0.5; deeper vertices are other parts of the hull
FIT_R = 1.75           # surface fit radius
BLEND_IN, BLEND_OUT = 1.15, 1.75   # normals: full surface normal inside, stock outside
GRID = (0.15, 0.2, 0.3, 0.4)   # patch interior spacing per LOD (the hull gets coarser)
MAX_EDIT_DEG = 50      # a stock normal further than this from the field is not hull side: left alone
TPS_LAMBDA = 0.1       # thin plate smoothing of the shape: irons out the stock bulge of the vertices next to the ring
FIELD_R = (1.1, 1.8)   # stock normals in this ring (clear of the flange's tilt) define the smooth normal field
FIELD_DEG = 3
OUTWARD = 0.3          # fit and normal edits only on vertices whose stock normal faces out (n . N > OUTWARD)
PORTHOLE = np.array((1.917, 5.777, 2.504))  # +x porthole centre (its open loop)
PORTHOLE_R = 0.45      # the porthole housing: out of the fit, its normals kept
PORTHOLE_FADE = 0.2    # normal edits fade in over this distance beyond the housing


def frame(n):
    t1 = np.cross(n, (0, 0, 1.0))
    t1 /= np.linalg.norm(t1)
    return t1, np.cross(n, t1)


def local(P, pc, n):
    t1, t2 = frame(n)
    d = P - pc
    return d @ t1, d @ t2, d @ n


def stock_normals(li):
    m = rmv2.load(br.STOCK.read_bytes())
    return np.array([br.to_blender(br.normal(v)) for v in m["lods"][li][0].verts])


def refine_frame(P, side):
    pc, n = PC0 * (side, 1, 1), N0 * (side, 1, 1)
    for _ in range(4):
        a, b, h = local(P, pc, n)
        rr = np.hypot(a, b)
        lip = P[(rr > 0.42) & (rr < 0.86) & (h > -0.2) & (h < 0.2)]
        c = lip.mean(0)
        nn = np.linalg.svd(lip - c)[2][2]
        nn = nn if nn @ n > 0 else -nn
        t1, t2 = frame(nn)
        d = lip - c
        A = np.c_[2 * (d @ t1), 2 * (d @ t2), np.ones(len(d))]
        s = np.linalg.lstsq(A, (d @ t1) ** 2 + (d @ t2) ** 2, rcond=None)[0]
        pc, n = c + s[0] * t1 + s[1] * t2, nn
        R = math.sqrt(s[2] + s[0] ** 2 + s[1] ** 2)
    return pc, n, R, len(lip)


def quad(a, b):
    return np.stack([np.ones_like(a), a, b, a * a, a * b, b * b], 1)


def _phi(r2):
    return np.where(r2 > 0, 0.5 * r2 * np.log(np.maximum(r2, 1e-30)), 0.0)    # r^2 log r


def tps_fit(a, b, h, lam=TPS_LAMBDA):
    """Thin plate spline h(a, b): the least-bending surface through the hull vertices (lam: slight smoothing)."""
    X = np.c_[a, b]
    K = _phi(((X[:, None] - X[None]) ** 2).sum(-1)) + lam * np.eye(len(X))
    Pm = np.c_[np.ones(len(X)), X]
    A = np.block([[K, Pm], [Pm.T, np.zeros((3, 3))]])
    sol = np.linalg.solve(A, np.r_[h, np.zeros(3)])
    return X, sol[:-3], sol[-3:]


def tps_eval(model, a, b):
    X, w, c = model
    Q = np.c_[np.atleast_1d(a), np.atleast_1d(b)]
    D = Q[:, None] - X[None]
    r2 = (D ** 2).sum(-1)
    h = _phi(r2) @ w + c[0] + Q @ c[1:]
    g = np.where(r2 > 0, np.log(np.maximum(r2, 1e-30)) + 1, 0.0)          # d(r^2 log r)/dx = x (2 log r + 1)
    ga = (g * D[..., 0]) @ w + c[1]
    gb = (g * D[..., 1]) @ w + c[2]
    return h, ga, gb


def _mono(a, b, deg):
    a, b = np.atleast_1d(a), np.atleast_1d(b)
    da, db = [], []
    for d in range(1, deg + 1):
        for i in range(d + 1):
            p, q = d - i, i
            da.append(p * a ** max(p - 1, 0) * b ** q if p else np.zeros_like(a))
            db.append(q * a ** p * b ** max(q - 1, 0) if q else np.zeros_like(a))
    return np.stack(da, 1), np.stack(db, 1)


def field_fit(a, b, N, n, t1, t2, deg=FIELD_DEG):
    """Slopes of a polynomial surface h(a, b) fitted to vertex normals: the smooth normal field that the hull's shading implies."""
    ga, gb = -(N @ t1) / (N @ n), -(N @ t2) / (N @ n)
    Da, Db = _mono(a, b, deg)
    return np.linalg.lstsq(np.vstack([Da, Db]), np.r_[ga, gb], rcond=None)[0], deg


def field_eval(field, a, b):
    c, deg = field
    Da, Db = _mono(a, b, deg)
    return Da @ c, Db @ c


def surf_normal(n, t1, t2, ga, gb):
    N = n[None] - np.atleast_1d(ga)[:, None] * t1 - np.atleast_1d(gb)[:, None] * t2
    return N / np.linalg.norm(N, axis=1)[:, None]


def fill(li, side, report):
    src = bpy.data.objects[f"STOCK-lod{li}"]
    name = f"GEO-lod{li}"
    ob = bpy.data.objects.get(name)
    if ob is None or side == 1:               # +x first: start from a fresh stock copy
        if ob is not None:
            bpy.data.objects.remove(ob)
        ob = bpy.data.objects.new(name, src.data.copy())
        ob.data.name = name
        src.users_collection[0].objects.link(ob)
        me = ob.data
        nrm = stock_normals(li)
        att = me.attributes.new("nrm", "FLOAT_VECTOR", "POINT")
        att.data.foreach_set("vector", nrm.ravel())
        st = me.attributes.new("stock", "INT", "POINT")
        st.data.foreach_set("value", list(range(len(me.vertices))))
    me = ob.data
    nv = len(me.vertices)
    P = np.empty(nv * 3)
    me.vertices.foreach_get("co", P)
    P = P.reshape(-1, 3)
    NRM = np.empty(nv * 3)
    me.attributes["nrm"].data.foreach_get("vector", NRM)
    NRM = NRM.reshape(-1, 3)
    hull = np.zeros(len(me.polygons), bool)
    me.attributes["hull"].data.foreach_get("value", hull)

    keyof = [tuple(np.round(p, 4)) for p in P]
    hull_v = np.zeros(nv, bool)
    for f in me.polygons:
        if hull[f.index]:
            hull_v[list(f.vertices)] = True
    near = hull_v & (np.abs(P[:, 0] - side * 1.5) < 1.2) & (np.abs(P[:, 1] - 5.77) < 1.3) & (np.abs(P[:, 2] - 1.25) < 1.3)
    pc, n, R_lip, nlip = refine_frame(P[near], side)
    t1, t2 = frame(n)
    a, b, h = local(P, pc, n)
    rr = np.hypot(a, b)

    # 2. port faces
    removed = [f.index for f in me.polygons if hull[f.index]
               and any(rr[v] < R_CUT and h[v] > H_MIN for v in f.vertices)]
    rem_set = set(removed)
    # 3. boundary loop on welded positions
    def wedges(fi):
        vs = me.polygons[fi].vertices
        return [tuple(sorted((keyof[vs[i]], keyof[vs[(i + 1) % len(vs)]]))) for i in range(len(vs))]
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
    bedges = [e for e in er if er[e] == 1]                      # the removed region's rim: shared with kept faces or open
    odd = [e for e in bedges if e not in ek]                    # open in the stock too (a lower LOD's porthole opening)
    fixed = {k for e in odd for k in e}                         # these stay where they are, and so do
    nbr = {}
    for x, y in bedges:
        nbr.setdefault(x, []).append(y)
        nbr.setdefault(y, []).append(x)
    assert all(len(v) == 2 for v in nbr.values()), "boundary is not a simple loop"
    start = next(iter(nbr))
    loop, prev = [start], None
    while True:
        nx = [y for y in nbr[loop[-1]] if y != prev]
        nx = nx[0] if prev is not None else nbr[start][0]
        if nx == start:
            break
        prev = loop[-1]
        loop.append(nx)
    assert len(loop) == len(nbr), "more than one boundary loop"
    LP = np.array(loop)
    la, lb, lh = local(LP, pc, n)
    if np.sum(la * np.roll(lb, -1) - np.roll(la, -1) * lb) < 0:       # counter-clockwise seen from outside
        LP, la, lb, lh = LP[::-1], la[::-1], lb[::-1], lh[::-1]
        loop = loop[::-1]
    fixed |= {k for k, x, y in zip(loop, la, lb) if math.hypot(x, y) > BLEND_IN}   # far rim vertices (coarse LODs)

    # 4. surface: thin plate spline through the kept outer hull vertices around the port
    ph = PORTHOLE * (side, 1, 1)
    used_keys = set()
    for f in me.polygons:
        if hull[f.index] and f.index not in rem_set:
            used_keys.update(keyof[v] for v in f.vertices)
    cand = {}
    for i in range(nv):
        if (keyof[i] in used_keys and rr[i] < FIT_R and h[i] > H_MIN and NRM[i] @ n > OUTWARD
                and np.linalg.norm(P[i] - ph) > PORTHOLE_R):
            cand.setdefault(keyof[i], i)
    for k in loop:                                              # the hole boundary always constrains the surface
        cand.setdefault(k, keyof.index(k))
    ci = np.array(list(cand.values()))
    model = tps_fit(a[ci], b[ci], h[ci])
    fit_res = h[ci] - tps_eval(model, a[ci], b[ci])[0]
    qc = np.linalg.lstsq(quad(a[ci], b[ci]), h[ci], rcond=None)[0]
    quad_res = h[ci] - quad(a[ci], b[ci]) @ qc
    bres = lh - tps_eval(model, la, lb)[0]
    ring = {}
    for i in range(nv):
        if (keyof[i] in used_keys and FIELD_R[0] < rr[i] < FIELD_R[1] and h[i] > H_MIN and NRM[i] @ n > OUTWARD
                and np.linalg.norm(P[i] - ph) > PORTHOLE_R + PORTHOLE_FADE):
            ring.setdefault(keyof[i], i)
    fi = np.array(list(ring.values()))
    field = field_fit(a[fi], b[fi], NRM[fi], n, t1, t2, FIELD_DEG if len(fi) >= 18 else 2)
    fn = surf_normal(n, t1, t2, *field_eval(field, a[fi], b[fi]))
    field_dev = np.degrees(np.arccos(np.clip((fn * NRM[fi]).sum(1), -1, 1)))
    # the hole boundary goes onto the smoothed surface (all stock copies of each vertex move with it)
    snap_h = tps_eval(model, la, lb)[0]
    LP = pc + la[:, None] * t1 + lb[:, None] * t2 + snap_h[:, None] * n
    moved = {k: p for k, p in zip(loop, LP) if k not in fixed}
    LP = np.array([moved.get(k, k) for k in loop])
    keep_res = np.array([lh[j] - snap_h[j] if loop[j] in fixed else 0.0 for j in range(len(loop))])

    # 5. patch: boundary + hex grid, constrained Delaunay inside the loop
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
        d = 1e9
        for i in range(nb):
            p0, p1 = seg[i], seg[(i + 1) % nb]
            t = np.clip(np.dot(q - p0, p1 - p0) / max(np.dot(p1 - p0, p1 - p0), 1e-12), 0, 1)
            d = min(d, np.linalg.norm(q - p0 - t * (p1 - p0)))
        return d
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
    cfaces = [[orig[i][0] for i in f] for f in cfaces]       # back to input vertex order
    A2 = np.array(pts)
    H2 = tps_eval(model, A2[:, 0], A2[:, 1])[0]
    if keep_res.any():                                          # meet the unmoved boundary vertices, fading over ~0.2 m
        d2 = ((A2[:, None, :] - np.c_[la, lb][None]) ** 2).sum(-1)
        g = np.exp(-d2 / (2 * 0.12 ** 2))
        H2 += (g * keep_res[None]).sum(1) / np.maximum(g.sum(1), 1.0)
    W = pc + A2[:, :1] * t1 + A2[:, 1:] * t2 + H2[:, None] * n
    W[:nb] = LP                                                 # boundary copies sit exactly on the (snapped) stock vertices
    PN = surf_normal(n, t1, t2, *field_eval(field, A2[:, 0], A2[:, 1]))

    # 6. normals of kept outer hull vertices around: the surface normal, fading to stock
    edited = skipped = 0
    dev_before = []
    for i in range(nv):
        pdist = np.linalg.norm(P[i] - ph)
        if not (keyof[i] in used_keys and rr[i] < BLEND_OUT and h[i] > H_MIN and NRM[i] @ n > OUTWARD
                and pdist > PORTHOLE_R):
            continue
        sn = surf_normal(n, t1, t2, *field_eval(field, a[i], b[i]))[0]
        w = np.clip((BLEND_OUT - rr[i]) / (BLEND_OUT - BLEND_IN), 0, 1)
        w = w * w * (3 - 2 * w)
        wp = np.clip((pdist - PORTHOLE_R) / PORTHOLE_FADE, 0, 1)
        w *= wp * wp * (3 - 2 * wp)
        if keyof[i] in moved:
            w = 1.0          # the moved rim takes the field normal outright
        dev = math.degrees(math.acos(np.clip(NRM[i] @ sn, -1, 1)))
        if dev > MAX_EDIT_DEG:
            skipped += 1
            continue
        dev_before.append(dev)
        new = (1 - w) * NRM[i] + w * sn
        NRM[i] = new / np.linalg.norm(new)
        edited += 1

    copies = {}
    for i in range(nv):
        if keyof[i] in moved or keyof[i] in fixed:
            copies.setdefault(keyof[i], []).append(i)
    # a rim position can carry several stock copies (UV seams, hard edges): the hull side's one faces out the most
    BN = np.array([NRM[max(copies[k], key=lambda i: NRM[i] @ n)] for k in loop])
    PN[:nb] = BN                                                # boundary copies share the stock vertex's final normal
    # patch vertices out beyond BLEND_IN lean towards their rim's normals (the field is not trusted that far out)
    pr = np.hypot(A2[nb:, 0], A2[nb:, 1])
    wf = np.clip((BLEND_OUT - pr) / (BLEND_OUT - BLEND_IN), 0, 1)
    wf = wf * wf * (3 - 2 * wf)
    if (wf < 1).any():
        d2 = ((A2[nb:, None, :] - np.c_[la, lb][None]) ** 2).sum(-1)
        idw = 1.0 / np.maximum(d2, 1e-9) ** 1.5
        rimn = (idw[..., None] * BN[None]).sum(1) / idw.sum(1)[:, None]
        mix = wf[:, None] * PN[nb:] + (1 - wf[:, None]) * rimn
        PN[nb:] = mix / np.linalg.norm(mix, axis=1)[:, None]

    # write: delete port faces, append the patch
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
    new_v = [bm.verts.new(Vector(p)) for p in W]
    for v in new_v:
        v[sl] = -1
    made = 0
    for f in cfaces:
        vs = [new_v[i] for i in f]
        fn = (Vector(W[f[1]]) - Vector(W[f[0]])).cross(Vector(W[f[2]]) - Vector(W[f[0]]))
        if fn.dot(Vector(n)) < 0:
            vs = vs[::-1]
        face = bm.faces.new(vs)
        face.smooth = True
        face[hl] = True          # BMesh reuses the deleted faces' slots: flags go on here, not by index afterwards
        made += 1
    bm.to_mesh(me)
    bm.free()
    assert len(me.vertices) == nv + len(W), "new vertices are expected at the end"
    NRM2 = np.vstack([NRM, PN])
    me.attributes["nrm"].data.foreach_set("vector", NRM2.ravel())
    me.normals_split_custom_set_from_vertices([tuple(x) for x in NRM2])
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.update()

    report[f"lod{li}_{'R' if side > 0 else 'L'}"] = {
        "centre": [round(float(x), 3) for x in pc], "axis": [round(float(x), 3) for x in n],
        "lip_R": round(R_lip, 3), "lip_verts": nlip,
        "removed_tris": len(removed), "boundary_verts": len(loop), "rim_kept_in_place": len(fixed & set(loop)), "open_rim_edges_kept": len(odd),
        "patch_verts": len(W), "patch_tris": made,
        "fit_pts": len(ci),
        "tps_res_mm": round(float(np.abs(fit_res).max()) * 1000, 2),
        "quad_rms_mm": round(float(np.sqrt((quad_res ** 2).mean())) * 1000, 1),
        "boundary_snap_mm": round(float(max([abs(r) for k, r in zip(loop, bres) if k not in fixed] or [0])) * 1000, 1),
        "field_pts": len(fi), "field_dev_deg": [round(float(field_dev.mean()), 1), round(float(field_dev.max()), 1)],
        "field_deg": field[1], "normals_edited": edited, "normals_skipped": skipped,
        "dev_before_deg": [round(float(np.max(dev_before)), 1), round(float(np.mean(dev_before)), 1)] if dev_before else None,
    }
    return ob, dict(pc=pc, n=n, t1=t1, t2=t2, model=model, field=field, side=side)


def _zone(me, ctx, radius):
    P = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", P)
    P = P.reshape(-1, 3)
    a, b, h = local(P, ctx["pc"], ctx["n"])
    return P, a, b, h, np.hypot(a, b)


def measure(li, ctx, radius=1.15):
    """Numbers for one side of one LOD, stock against work: open welded edges of hull faces within `radius` of the port
    axis, triangles, and how far vertex normals there stand from the smooth field (degrees)."""
    out = {}
    pc, n, t1, t2, field = ctx["pc"], ctx["n"], ctx["t1"], ctx["t2"], ctx["field"]
    ph = PORTHOLE * (ctx["side"], 1, 1)
    for tag, name in (("stock", f"STOCK-lod{li}"), ("work", f"GEO-lod{li}")):
        me = bpy.data.objects[name].data
        P, a, b, h, rr = _zone(me, ctx, radius)
        if tag == "stock":
            N = stock_normals(li)
        else:
            N = np.empty(len(P) * 3)
            me.attributes["nrm"].data.foreach_get("vector", N)
            N = N.reshape(-1, 3)
        hull = np.zeros(len(me.polygons), bool)
        me.attributes["hull"].data.foreach_get("value", hull)
        key = [tuple(np.round(p, 4)) for p in P]
        inz = (rr < radius) & (h > H_MIN)
        cnt, zone_tris = {}, 0
        for f in me.polygons:
            if not hull[f.index] or not all(inz[v] for v in f.vertices):
                continue
            zone_tris += 1
            vs = f.vertices
            for i in range(len(vs)):
                e = tuple(sorted((key[vs[i]], key[vs[(i + 1) % len(vs)]])))
                cnt[e] = cnt.get(e, 0) + 1
        # an edge is open if no hull face at all (in or out of the zone) shares it
        zone_edges = {e for e, c in cnt.items() if c == 1}
        for f in me.polygons:
            if hull[f.index] and any(inz[v] for v in f.vertices) and not all(inz[v] for v in f.vertices):
                vs = f.vertices
                for i in range(len(vs)):
                    zone_edges.discard(tuple(sorted((key[vs[i]], key[vs[(i + 1) % len(vs)]]))))
        near_ph = sum(1 for e in zone_edges if min(np.linalg.norm(np.array(e[0]) - ph), np.linalg.norm(np.array(e[1]) - ph)) < PORTHOLE_R)
        # normals of outward hull vertices in the zone (not the porthole housing) against the field
        hv = np.zeros(len(P), bool)
        for f in me.polygons:
            if hull[f.index]:
                hv[list(f.vertices)] = True
        sel = np.where(hv & inz & (np.linalg.norm(P - ph, axis=1) > PORTHOLE_R + PORTHOLE_FADE) & (N @ n > OUTWARD))[0]
        if tag == "stock":
            sel = sel[rr[sel] > R_CUT]          # the ring itself is no hull side
        sn = surf_normal(n, t1, t2, *field_eval(field, a[sel], b[sel]))
        dev = np.degrees(np.arccos(np.clip((sn * N[sel]).sum(1), -1, 1)))
        out[tag] = {"tris_total": len(me.polygons), "zone_tris": zone_tris, "open_edges_zone": len(zone_edges),
                    "open_edges_at_porthole": near_ph, "normal_dev_deg_mean_max": [round(float(dev.mean()), 1), round(float(dev.max()), 1)],
                    "verts_checked": len(sel)}
        if tag == "work":
            # geometric faces of the patch against the field: how far the shape leans from the shading
            st = np.empty(len(P), np.int32)
            me.attributes["stock"].data.foreach_get("value", st)
            fd = []
            for f in me.polygons:
                if all(st[v] < 0 for v in f.vertices) and all(inz[v] for v in f.vertices):
                    c = np.mean([P[v] for v in f.vertices], 0)
                    ca, cb, _ = local(c[None], pc, n)
                    s_n = surf_normal(n, t1, t2, *field_eval(field, ca, cb))[0]
                    fd.append(math.degrees(math.acos(np.clip(np.dot(s_n, np.array(f.normal)), -1, 1))))
            out[tag]["patch_face_vs_field_deg_mean_max"] = [round(float(np.mean(fd)), 1), round(float(np.max(fd)), 1)] if fd else None
    return out
