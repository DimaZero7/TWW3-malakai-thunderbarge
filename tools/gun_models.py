"""Guns for the barge's cannon seats, cut from the game's own war machine models: py -3.14 tools/gun_models.py [name ...]

A gun is read from data/gun_models.json: a source model, the source bones to keep, where each group of bones goes, and the bone of
the zeppelin01_cannon skeleton all of it is rigidly bound to. Writes build/weapons/models/<path>.rigid_model_v2 and .wsmodel, the
same paths they have in the pack. All LODs of the source are converted. Nothing is written outside build/.
"""
import json
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import gamepack  # noqa: E402
import rmv2  # noqa: E402

SPEC = json.loads((REPO / "data" / "gun_models.json").read_text(encoding="utf-8"))
OUT = REPO / "build" / "weapons" / "models"
SKELETON = "zeppelin01_cannon"
ATTACHMENTS = [(name, bone, rmv2.IDENTITY) for name, bone in (("animRoot", 0), ("root", 1), ("cannon_0", 2), ("cannon_1", 3))]
BONE = {"root": 1, "cannon_0": 2, "cannon_1": 3}
FOLDER = "warmachines/aircraft/dwf_thunderbarge/cannon"
STOCK_DISTANCES = (20.0, 40.0, 60.0, 10000.0)


def game_file(path):
    target = path.replace("/", "\\").lower()
    for pack in sorted(gamepack.DATA.glob("*.pack")):
        if pack.name.startswith(("audio", "local_")):
            continue
        for _, blob in gamepack.entries(pack, lambda n: n.lower() == target):
            return blob
    raise SystemExit(f"{path} is not in the game's packs")


def dominant_bone(v):
    return v.bone0 if v.weight0 >= v.weight1 else v.bone1


def axis_of(verts):
    """Straight line through a barrel: centres of its front and rear thirds. Returns f(z) -> (x, y)."""
    zs = [v.z for v in verts]
    lo, hi = min(zs), max(zs)
    span = hi - lo

    def centre(z0, z1):
        part = [v for v in verts if z0 <= v.z <= z1] or verts     # few vertices: the whole part's box
        xs, ys = [v.x for v in part], [v.y for v in part]
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    z_rear, z_front = lo + span * 0.45, hi - span * 0.05
    (x0, y0), (x1, y1) = centre(z_rear - span * 0.05, z_rear + span * 0.05), centre(z_front - span * 0.05, z_front + span * 0.05)
    dz = z_front - z_rear

    def line(z):
        t = (z - z_rear) / dz
        return x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
    return line, hi


def convert_lod(meshes, spec, frames):
    """Keeps the wanted triangles, moves them onto the new axes, binds them to one bone."""
    bind = BONE[spec.get("bind", "cannon_0")]
    scale = spec.get("scale", 1.0)
    wanted = {}          # source bone -> group
    for group in spec["groups"]:
        for bone in group["bones"]:
            wanted[bone] = group
    out = []
    for mesh in meshes:
        new = rmv2.keep_triangles(mesh, lambda a, b, c: all(dominant_bone(mesh.verts[i]) in wanted for i in (a, b, c)))
        for v in new.verts:
            group = wanted[dominant_bone(v)]
            line, muzzle = frames[group["name"]]
            ax, ay = line(v.z) if group.get("along_axis", True) else line(muzzle)
            dx, dy = group.get("to", [0, 0])
            v.x = (v.x - ax) * scale + dx
            v.y = (v.y - ay) * scale + dy
            v.z = (v.z - muzzle) * scale + spec["muzzle_z"]
            v.bone0, v.bone1, v.weight0, v.weight1 = bind, 0, 255, 0
        new.attachments = list(ATTACHMENTS)
        out.append(new)
    return out


def part_copy(mesh, part, place):
    """One placed copy of a part: the source bones around their own axis, scaled across and along it. Rigid, on the gun's bone."""
    bones = set(part["bones"])
    new = rmv2.keep_triangles(mesh, lambda a, b, c: all(dominant_bone(mesh.verts[i]) in bones for i in (a, b, c)))
    span = part.get("z")        # only this stretch of the source's length
    if span and part.get("clamp"):     # low LODs have long triangles over the whole barrel: kept, and pressed into the stretch
        new = rmv2.keep_triangles(new, lambda a, b, c: any(new.verts[i].z >= span[0] for i in (a, b, c)))
        for v in new.verts:
            v.z = min(max(v.z, span[0]), span[1])
    elif span:
        new = rmv2.keep_triangles(new, lambda a, b, c: all(span[0] <= new.verts[i].z <= span[1] for i in (a, b, c)))
    return new


def part_levels(part, default_bind):
    """One mesh per level of a part of a gun, placed by its recipe (see assemble). None on a level where the source has nothing."""
    model = rmv2.load(game_file(part["source"]))
    bones = set(part["bones"])
    ref = [v for m in model["lods"][0] for v in m.verts if dominant_bone(v) in bones]
    span = part.get("z") or (min(v.z for v in ref), max(v.z for v in ref))
    ref = [v for v in ref if span[0] <= v.z <= span[1]]
    axis = part.get("axis_z") or span      # the stretch whose middle is the part's axis: a barrel's front, not the lock on top of it
    around = [v for v in ref if axis[0] <= v.z <= axis[1]] or ref
    cx = (min(v.x for v in around) + max(v.x for v in around)) / 2
    cy = (min(v.y for v in around) + max(v.y for v in around)) / 2
    z0 = min(v.z for v in ref)
    out = []
    for source_lod in part["lods"]:
        merged = None
        for mesh in model["lods"][source_lod]:
            for dx, dy in part.get("copies", [[0, 0]]):
                one = part_copy(mesh, part, None)
                for v in one.verts:
                    if not part.get("keep_place"):
                        v.x = (v.x - cx) * part["across"] + dx
                        v.y = (v.y - cy) * part["across"] + dy
                        v.z = (v.z - z0) * part["along"] + part["z_to"]
                    v.rebind(BONE[part.get("bind", default_bind)])
                one.attachments = list(ATTACHMENTS)
                if merged is None:
                    merged = one
                else:
                    rmv2.append(merged, one)
        out.append(merged if merged is not None and merged.tris else None)
    return out, model


def assemble(name, spec):
    """A gun built of parts of several models. spec["parts"]: source, material, bones, lods (source LOD per level), across, along (scales), z_to (where
    the part's rear goes on the barrel's axis), z (the stretch of the source to take), axis_z, copies [[dx, dy], ...]. Each part is one mesh of its own material."""
    levels = len(STOCK_DISTANCES)
    result = {"skeleton": SKELETON, "lods": [[] for _ in range(levels)]}
    materials = {i: [] for i in range(levels)}     # a part with no triangles on a low level is left out of that level
    for part in spec["parts"]:
        meshes, model = part_levels(part, spec.get("bind", "cannon_0"))
        result.setdefault("version", model["version"])
        for level, mesh in enumerate(meshes):
            if mesh is not None:
                result["lods"][level].append(mesh)
                materials[level].append(part["material"])
    result["lod_headers"] = [struct.pack("<fI", d, level) + model["lod_headers"][0][8:] for level, d in enumerate(STOCK_DISTANCES)]
    path = f"{FOLDER}/tww3_mtb_{name}"
    rm = rmv2.save(result)
    ws = rmv2.wsmodel(path + ".rigid_model_v2", materials)
    back = rmv2.load(rm)
    bones = {dominant_bone(v) for meshes in back["lods"] for m in meshes for v in m.verts}
    if back["skeleton"] != SKELETON or not bones <= set(BONE.values()):
        raise SystemExit(f"{name}: read back: skeleton {back['skeleton']}, bones {bones}")
    target = OUT / Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.with_suffix(".rigid_model_v2").write_bytes(rm)
    target.with_suffix(".wsmodel").write_bytes(ws)
    bb = rmv2.bounding_box([v for m in back["lods"][0] for v in m.verts])
    print(json.dumps({"name": name, "bytes": len(rm), "tris_by_lod": [sum(len(m.tris) for m in meshes) for meshes in back["lods"]], "box": [round(x, 2) for x in bb]}))
    return target


def build(name):
    spec = SPEC[name]
    if spec.get("parts"):
        return assemble(name, spec)
    model = rmv2.load(game_file(spec["source"]))
    # The axes come from LOD 0, so that every LOD moves the same way.
    frames = {}
    verts = model["lods"][0][0].verts if model["lods"][0] else []
    for group in spec["groups"]:
        axis_bones = group.get("axis_bones", group["bones"])
        frames[group["name"]] = axis_of([v for v in verts if dominant_bone(v) in axis_bones])
    lods = [convert_lod(meshes, spec, frames) for meshes in model["lods"]]
    keep = [i for i, meshes in enumerate(lods) if sum(len(m.tris) for m in meshes)]
    materials = [spec["material"]] if spec["groups"] else []
    if not spec["groups"]:
        keep = list(range(len(lods)))
        for i in keep:
            lods[i] = []
    if spec.get("base"):
        # A second part from another model, left where it is on its own bones: the stock gun's rear as a mount for a short gun.
        base = rmv2.load(game_file(spec["base"]["source"]))
        keep = [i for i in keep if i < len(base["lods"])]
        for i in keep:
            for mesh in base["lods"][i]:
                wanted = set(spec["base"]["bones"])
                lods[i].append(rmv2.keep_triangles(mesh, lambda a, b, c: all(dominant_bone(mesh.verts[v]) in wanted for v in (a, b, c))))
        materials.append(spec["base"]["material"])
    result = {"version": model["version"], "skeleton": SKELETON, "lods": [lods[i] for i in keep],
              "lod_headers": [model["lod_headers"][i] for i in keep]}
    if spec.get("lods"):        # which LODs of the source to keep, at the stock cannon's distances
        chosen = spec["lods"]
        result["lods"] = [result["lods"][i] for i in chosen]
        result["lod_headers"] = [struct.pack("<fI", d, level) + result["lod_headers"][chosen[level]][8:]
                                 for level, d in enumerate(STOCK_DISTANCES[:len(chosen)])]
        keep = [keep[i] for i in chosen]
    if spec.get("static"):      # no animation: the piece stands as it is, on the root of the default skeleton of hidden seats
        result["skeleton"] = "default_skeleton"
        for meshes in result["lods"]:
            for mesh in meshes:
                mesh.attachments = [ATTACHMENTS[0]]
                for v in mesh.verts:
                    v.rebind(0)
    if spec.get("mount"):       # parts of a real mount around a gun cut from a whole model: the ball in the port, the sleeve
        by_level = {i: list(materials) for i in range(len(result["lods"]))}
        for part in spec["mount"]:
            meshes, _ = part_levels(part, "cannon_0")
            for level, mesh in enumerate(meshes[:len(result["lods"])]):
                if mesh is not None:
                    result["lods"][level].append(mesh)
                    by_level[level].append(part["material"])
    else:
        by_level = {i: materials for i in range(len(keep))}
    path = f"{FOLDER}/tww3_mtb_{name}"
    rm = rmv2.save(result)
    ws = rmv2.wsmodel(path + ".rigid_model_v2", by_level)
    # Read back: the file must parse, on our skeleton, with only the bound bone.
    back = rmv2.load(rm)
    bones = {dominant_bone(v) for meshes in back["lods"] for m in meshes for v in m.verts}
    if not spec.get("static") and (back["skeleton"] != SKELETON or not bones <= set(BONE.values())):
        raise SystemExit(f"{name}: read back: skeleton {back['skeleton']}, bones {bones}")
    target = OUT / Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.with_suffix(".rigid_model_v2").write_bytes(rm)
    target.with_suffix(".wsmodel").write_bytes(ws)
    bb = rmv2.bounding_box([v for m in back["lods"][0] for v in m.verts])
    info = {"name": name, "bytes": len(rm), "tris_by_lod": [sum(len(m.tris) for m in meshes) for meshes in back["lods"]],
            "box": [round(x, 2) for x in bb]}
    print(json.dumps(info))
    return target


def main():
    for name in sys.argv[1:] or SPEC:
        build(name)


if __name__ == "__main__":
    main()
