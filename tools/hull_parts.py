"""The Spirit of Grungni's hull with some details moved out of it, into models of the seats they belong to: py -3.14 tools/hull_parts.py

data/hull_parts.json lists the details by mesh and box: a connected piece of the hull entirely inside a box is a part of the detail, in
every LOD. The hull is written as our own model, used only by our own mount and variant rows, so the Thunderbarge and the stock Spirit of
Grungni keep the game's files. Each detail becomes a model in the frame of one seat, bound to the root of the rider's skeleton.
"""
import json
import math
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import gamepack  # noqa: E402
import rmv2  # noqa: E402

SPEC = json.loads((REPO / "data" / "hull_parts.json").read_text(encoding="utf-8"))
OUT = REPO / "build" / "weapons" / "models"
SEP = chr(92)
RIDER_SKELETON = "humanoid03"
RIDER_ATTACHMENTS = [("animroot", 0, rmv2.IDENTITY)]
_files = {}


def game_file(path):
    target = path.replace("/", SEP).lower()
    if target not in _files:
        found = None
        for pack in sorted(gamepack.DATA.glob("*.pack")):
            if not pack.name.startswith(("audio", "local_")):
                for _, blob in gamepack.entries(pack, lambda n: n.lower() == target):
                    found = blob
        if found is None:
            raise SystemExit(f"{path} is not in the game's packs")
        _files[target] = found
    return _files[target]


def pieces(mesh):
    """Connected pieces: [(triangle indexes, box)]."""
    parent = list(range(len(mesh.verts)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b, c in mesh.tris:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
        rc, ra = find(c), find(a)
        if rc != ra:
            parent[rc] = ra
    groups = {}
    for i, tri in enumerate(mesh.tris):
        groups.setdefault(find(tri[0]), []).append(i)
    out = []
    for tris in groups.values():
        verts = {v for i in tris for v in mesh.tris[i]}
        xs, ys, zs = zip(*((mesh.verts[v].x, mesh.verts[v].y, mesh.verts[v].z) for v in verts))
        out.append((tris, (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))))
    return out


def inside(box, area):
    if not (box[0] >= area[0] and box[1] >= area[1] and box[2] >= area[2] and box[3] <= area[3] and box[4] <= area[4] and box[5] <= area[5]):
        return False
    return len(area) < 7 or box[3] - box[0] >= area[6]


def materials(wsmodel):
    """{(lod, part): material path} of a .wsmodel."""
    out = {}
    for m in re.finditer(r"<material ([^>]*)>([^<]+)</material>", wsmodel):
        lod = int(re.search(r'lod_index="(\d+)"', m.group(1)).group(1))
        part = int(re.search(r'part_index="(\d+)"', m.group(1)).group(1))
        out[(lod, part)] = m.group(2)
    return out


def build():
    """Writes the models under build/weapons/models. Returns {pack path: bytes} and {detail: .wsmodel path}."""
    source = rmv2.load(game_file(SPEC["source"]))
    stock_ws = game_file(SPEC["wsmodel"]).decode("utf-8")
    stock_materials = materials(stock_ws)
    moved = {d["name"]: [] for d in SPEC["details"]}
    report = {}
    for li, meshes in enumerate(source["lods"]):
        for mi, mesh in enumerate(meshes):
            remove = set()
            for detail in SPEC["details"]:
                if detail["mesh"] != mi:
                    continue
                keep = set()
                for tris, box in pieces(mesh):
                    if any(inside(box, area) for area in detail["boxes"]):
                        keep.update(tris)
                if keep:
                    part = _select(mesh, keep)
                    moved[detail["name"]].append((li, mi, part))
                    report.setdefault(detail["name"], {})[li] = len(keep)
                remove |= keep
            if remove:
                meshes[mi] = _select(mesh, set(range(len(mesh.tris))) - remove)
    files = {}
    hull_path = SPEC["out"] + ".rigid_model_v2"
    files[hull_path.replace("/", SEP)] = rmv2.save(source)
    ws = stock_ws.replace(SPEC["source"], hull_path)
    if ws == stock_ws:
        raise SystemExit("the hull's .wsmodel does not name its geometry as expected")
    files[(SPEC["out"] + ".wsmodel").replace("/", SEP)] = ws.encode("utf-8")
    models = {}
    for detail in SPEC["details"]:
        parts = moved[detail["name"]]
        lods = sorted({li for li, _, _ in parts})
        model = {"version": source["version"], "skeleton": RIDER_SKELETON, "lods": [], "lod_headers": []}
        table = {}
        ox, oy, oz = detail["seat_origin"]
        for new_li, li in enumerate(lods):
            mesh = next(p for l, _, p in parts if l == li).copy()
            for v in mesh.verts:
                # The hull is drawn at the variant's scale (1.2 for the Spirit of Grungni), a rider's model is not: the detail needs it in its numbers.
                s = detail.get("scale", 1.0)
                near = detail.get("move_rear")      # measured from pictures: a ring goes where its man stands
                dz = near["dz"] if near and v.z < near["z_below"] else 0.0
                v.x, v.y, v.z = (v.x - ox) * s, (v.y - oy) * s, (v.z - oz) * s + dz
                v.rebind(0)
            mesh.attachments = list(RIDER_ATTACHMENTS)
            model["lods"].append([mesh])
            model["lod_headers"].append(source["lod_headers"][li])
            table[new_li] = [detail.get("material", stock_materials[(li, detail["mesh"])])]
        base = f"{detail['out']}"
        files[(base + ".rigid_model_v2").replace("/", SEP)] = rmv2.save(model)
        files[(base + ".wsmodel").replace("/", SEP)] = rmv2.wsmodel(base + ".rigid_model_v2", table)
        models[detail["name"]] = base + ".wsmodel"
    print("hull parts, triangles by LOD:", report, flush=True)
    files.update(patches(source, stock_materials, models))
    return files, models


def _both_sides(mesh):
    """Each triangle also the other way round: a patch is seen from one side, and which one its winding makes it is not worth a run of the game."""
    mesh.tris = [t for a, b, c in mesh.tris for t in ((a, b, c), (a, c, b))]


def _patch_model(source, mesh, material, out, name, models):
    """A model on the hull's own skeleton, in the hull's frame: it is another slot of the hull's definition."""
    model = {"version": source["version"], "skeleton": source["skeleton"], "lods": [[mesh]], "lod_headers": [source["lod_headers"][0]]}
    models[name] = out + ".wsmodel"
    return {(out + ".rigid_model_v2").replace("/", SEP): rmv2.save(model),
            (out + ".wsmodel").replace("/", SEP): rmv2.wsmodel(out + ".rigid_model_v2", {0: [material]})}


def patches(source, stock_materials, models):
    """The plain ship of a barge without its bays: pieces over the port and the bomb niches (data/hull_parts.json, patches). A variant of the mount has them as a slot."""
    spec = SPEC["patches"]
    hull = source["lods"][0][0]
    material = stock_materials[(0, 0)]
    files = {}

    def centre(t):
        return tuple(sum(getattr(hull.verts[i], axis) for i in t) / 3 for axis in "xyz")
    # plates: a triangle of the steel around the niches gives the look, the height comes from the rim
    want = spec["bombs"]["template"]
    template = next(t for t in hull.tris if want["x"][0] <= centre(t)[0] <= want["x"][1] and want["z"][0] <= centre(t)[2] <= want["z"][1] and centre(t)[1] < want["y_below"])
    corners = [hull.verts[i] for i in template]
    mesh = hull.copy()
    mesh.verts, mesh.tris = [], []
    x0, x1 = spec["bombs"]["x"]
    for sign in (1, -1):
        for z0, z1 in spec["bombs"]["z"]:
            base = len(mesh.verts)
            for n, (x, z) in enumerate(((x0, z0), (x1, z0), (x1, z1), (x0, z1))):
                v = corners[min(n, 2)].copy()
                v.x, v.y, v.z = x * sign, spec["bombs"]["y"], z
                mesh.verts.append(v)
            mesh.tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    _both_sides(mesh)
    files.update(_patch_model(source, mesh, material, spec["bombs"]["out"], "patch_bombs", models))
    # over the port: a round lid in the colour of the planks, in the plane of the port's outer ring. Each side has its own template, for the normals.
    port = spec["port"]
    box = port["ring_box"]
    rim = [v for v in hull.verts if v.x > 1.3 and box[0] <= v.z <= box[1] and box[2] <= v.y <= box[3]]
    # the plane of the port's outermost vertices, a little beyond the farthest of them: x = a + b z + c y
    points = [(v.z, v.y, v.x) for v in rim]
    n_ = len(points)
    zm, ym, xm = (sum(p_[i] for p_ in points) / n_ for i in range(3))
    szz = sum((p_[0] - zm) ** 2 for p_ in points)
    syy = sum((p_[1] - ym) ** 2 for p_ in points)
    szy = sum((p_[0] - zm) * (p_[1] - ym) for p_ in points)
    szx = sum((p_[0] - zm) * (p_[2] - xm) for p_ in points)
    syx = sum((p_[1] - ym) * (p_[2] - xm) for p_ in points)
    det = szz * syy - szy * szy
    slope_z, slope_y = (szx * syy - syx * szy) / det, (syx * szz - szx * szy) / det
    lift = max(x - (xm + slope_z * (z - zm) + slope_y * (y - ym)) for z, y, x in points)

    def plank(sign):
        def area(t):
            a_, b_, c_ = (hull.verts[i] for i in t)
            return abs((b_.y - a_.y) * (c_.z - a_.z) - (b_.z - a_.z) * (c_.y - a_.y))
        want_ = port["template"]
        found = [t for t in hull.tris if want_["z"][0] <= centre(t)[2] <= want_["z"][1] and want_["y"][0] <= centre(t)[1] <= want_["y"][1] and centre(t)[0] * sign > want_["x_above"]]
        return [hull.verts[i] for i in max(found, key=area)]
    mesh = hull.copy()
    mesh.verts, mesh.tris = [], []
    sides = 32
    for sign in (1, -1):
        corners_ = plank(sign)
        base = len(mesh.verts)
        for n in range(sides + 1):
            v = corners_[n % 3].copy()
            if n == sides:
                y, z = port["y"], port["z"]
            else:
                angle = 2 * math.pi * n / sides
                y, z = port["y"] + port["radius"] * math.sin(angle), port["z"] + port["radius"] * math.cos(angle)
            v.x, v.y, v.z = (xm + slope_z * (z - zm) + slope_y * (y - ym) + lift + port["proud"]) * sign, y, z
            mesh.verts.append(v)
        for n in range(sides):
            mesh.tris.append((base + sides, base + n, base + (n + 1) % sides))
    _both_sides(mesh)
    files.update(_patch_model(source, mesh, material, port["out"], "patch_port", models))
    return files


def _select(mesh, indexes):
    out = mesh.copy()
    remap, verts, tris = {}, [], []
    for i in sorted(indexes):
        new = []
        for v in mesh.tris[i]:
            if v not in remap:
                remap[v] = len(verts)
                verts.append(mesh.verts[v].copy())
            new.append(remap[v])
        tris.append(tuple(new))
    out.verts, out.tris = verts, tris
    return out


def variant_definition(hull_wsmodel, extra=()):
    """The hull's stock .variantmeshdefinition with our model in it, and models more as slots of their own."""
    stock = game_file(SPEC["definition"]).decode("utf-8")
    new = stock.replace(SPEC["wsmodel"], hull_wsmodel)
    if new == stock:
        raise SystemExit("the hull's definition does not name its model as expected")
    end = new.rindex("</VARIANT_MESH>")
    slots = "".join(f'\t<SLOT name="patch{i}" >\n\t\t<VARIANT_MESH model="{model}" />\n\t</SLOT>\n' for i, model in enumerate(extra))
    return (new[:end] + slots + new[end:]).encode("utf-8")


if __name__ == "__main__":
    written, parts_of = build()
    print({k: len(v) for k, v in written.items()}, parts_of)
