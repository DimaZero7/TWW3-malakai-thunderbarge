"""Export for the local web page of the airship screen (web/): py -3.14 tools/web_export.py [--data] [--models] [--vendor]

Everything goes to build/web/ (outside git): the game's models, textures and UI pictures must not reach the public repository.
  build/web/data.json       buildings of the barge as the mod builds them: the same functions as tools/build.py, nothing copied by hand
  build/web/models/*.gltf   the base barge (build/solid_hull_hatches without the shields) and each removed detail as a model of its own, LOD 0,
                            game axes mirrored to three.js (export_models)
  build/web/tex/*.png       their textures, DDS turned into PNG by tools/web_textures.py (py -3.10, Pillow)
  build/web/game/...        the game's own UI pictures the panel uses (frames, icons), at their pack paths
  build/web/vendor/three/   three.js, a pinned version from the npm registry
No option: all of it. Reads the game's packs (py -3.14 for zstd), writes nothing outside build/web.
"""
import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import blender_rmv2  # noqa: E402  (vertex attributes only; bpy is needed only by its scene functions)
import build  # noqa: E402
import crew_buildings  # noqa: E402
import crew_options  # noqa: E402
import crew_ui  # noqa: E402
import gamepack  # noqa: E402
import hull_parts  # noqa: E402
import rmv2  # noqa: E402

OUT = REPO / "build" / "web"
THREE = "0.170.0"
THREE_FILES = ["build/three.module.js", "build/three.core.js", "examples/jsm/controls/OrbitControls.js", "examples/jsm/loaders/GLTFLoader.js",
               "examples/jsm/utils/BufferGeometryUtils.js", "LICENSE"]
# The game's UI pictures of the panel (src/tww3_mtb_crew_ui.lua, tools/crew_ui.py).
GAME_UI = ["ui/skins/default/panel_back_border.png", "ui/skins/default/panel_back_tile.png", "ui/skins/default/panel_back_inner_frame.png",
           "ui/skins/default/panel_back_tile_stone.png", "ui/skins/default/panel_back_frame.png", "ui/skins/wh_main_dwf_dwarfs/panel_title_large.png",
           "ui/skins/default/icon_cross.png", "ui/skins/default/icon_treasury.png", "ui/skins/default/icon_income.png", "ui/skins/default/icon_padlock.png",
           "ui/skins/default/icon_check.png", "ui/skins/default/icon_end_turn.png", "ui/skins/default/icon_hourglass.png",
           "ui/skins/default/icon_stat_ranged_damage.png", "ui/skins/default/icon_stat_reload_time.png",
           "ui/skins/default/icon_stat_range.png", "ui/skins/default/icon_stat_ammo.png"]
# The base barge: the hull of build/solid_hull_hatches with the bomb hatches open in its geometry (parts/..._01_open) and their covers as a model of their own,
# so that the covers can go when the hatches are built. The other removed details are models of their own in build/solid_hull_*/<name>_part, in the hull's frame.
BASE = REPO / "build" / "solid_hull_hatches"
DT = "warmachines/aircraft/dwf_thunderbarge/"
BASE_HULL = ("parts/" + DT + "tww3_mtb_dwf_thunderbarge_01_open.rigid_model_v2", "parts/" + DT + "tww3_mtb_dwf_thunderbarge_grungni_01_open.wsmodel")
HATCH_COVERS = ("parts/" + DT + "tww3_mtb_dwf_thunderbarge_hatch_covers.rigid_model_v2", "parts/" + DT + "tww3_mtb_dwf_thunderbarge_hatch_covers.wsmodel")
# Details as models of their own: (folder of build/ that holds warmachines/..., model name). Their materials are the stock ones: a part reads the stock texture.
PART_MODELS = {
    "porthole": ("solid_hull_porthole/porthole_part", "tww3_mtb_dwf_thunderbarge_porthole"),
    "stern_armour": ("solid_hull_stern/stern_armour_part", "tww3_mtb_dwf_thunderbarge_stern_armour"),
    "forsage_tank": ("solid_hull_tank/tank_part", "tww3_mtb_dwf_thunderbarge_forsage_tank"),
    "bomb_hatches": ("solid_hull_hatches/hatches_part", "tww3_mtb_dwf_thunderbarge_bomb_hatches"),
}
# The round shields are not cut out of the model yet: cut here for the page, the way tools/hull_parts.py cuts details (connected pieces wholly inside a box),
# with a least size of the piece so that rivets and planks in the box stay. Boxes from the pieces of the hull's mesh 0 (both sides, mirrored in x):
# 6 shields on each side of the hull, 5 pieces each; 9 on each side of the balloon, 4 pieces each (docs/research/img/shields-diagnosis.png).
SHIELDS = {
    "side_shields": {"abs_x": (2.35, 2.9), "y": (1.3, 2.8), "z": (-1.8, 3.95), "least": 1.0, "pieces": 60},
    "balloon_shields": {"abs_x": (4.3, 6.1), "y": (13.9, 16.05), "z": (-9.7, 5.5), "least": 1.5, "pieces": 72},
}
# The gun port: the base hull has it closed with new geometry (planks and steel over it). Where the base differs from the stock hull around the port
# (data/hull_parts.json, patches.port.hole_box, widened) its triangles are the plug; the stock triangles of the same place, port included, are the part.
PORT_MARGIN = 0.5
STOCK_HULL = (hull_parts.SPEC["source"], hull_parts.SPEC["wsmodel"])


# ---------------- files of the game and of build/ ----------------
_found = {}


def game_files(paths):
    """{path: bytes} of the game's packs, one pass over all of them; a later pack wins, as in hull_parts.game_file. Missing paths are left out.
    Our own packs in the game's folder (tww3_*) are skipped: only the game's files."""
    norm = lambda p: p.replace("/", chr(92)).lower()
    want = {norm(p) for p in paths if norm(p) not in _found}
    if want:
        for pack in sorted(gamepack.DATA.glob("*.pack")):
            if pack.name.startswith(("audio", "local_", "tww3_")):
                continue
            for name, blob in gamepack.entries(pack, lambda n: n.lower() in want):
                _found[name.lower()] = blob
    return {p: _found[norm(p)] for p in paths if norm(p) in _found}


def source_file(path, root=None):
    """A file of a model: under root (a folder of build/ that holds warmachines/...) when it is there, otherwise the game's."""
    if root is not None and (root / path).exists():
        return (root / path).read_bytes()
    got = game_files([path])
    if path not in got:
        raise SystemExit(f"{path}: not in {root} nor in the game's packs")
    return got[path]


# ---------------- data: the same functions as the mod's build ----------------
def export_data():
    """The barge's building levels as tools/build.py makes them: build.derive + build.derive_campaign (crew_buildings.add_rows), the green lines of crew_ui.building_lines,
    the hire and upkeep of crew_ui. Nothing is copied by hand from data/crew_options.json, so a change there shows on the page after this export."""
    stock = build.game_tables()
    t = build.derive(stock, "rider")
    t = build.derive_campaign(stock, {k: [dict(r) for r in v] for k, v in t.items()})
    loc = t.pop("__building_loc__")
    t.pop("__building_files__")
    config = crew_options.CONFIG
    prefix = config["buildings_prefix"]
    bindings, levels, _ = crew_options.building_bindings(t, stock)
    lines = crew_ui.building_lines(config, t, stock, bindings)
    names = crew_ui.game_text("building_culture_variants_name_")
    rows = {r["level_name"]: r for r in stock["building_levels"]} | {r["level_name"]: r for r in t["building_levels"]}
    required = {}
    for r in t["building_level_required_buildings"]:
        required.setdefault(r["building_level"], []).append(r["required"])
    drawn = crew_buildings.icon_files()

    def name_of(key):
        return loc.get(f"building_culture_variants_name_{key}") or lines.get(f"building_culture_variants_name_{key}") or names.get(f"building_culture_variants_name_{key}", key)

    def green(short):
        out, n = [], 0
        while True:
            text = lines.get(f"effects_description_mtb_effect_crew_{short}" + (f"_{n}" if n else ""))
            if text is None:
                return out
            out.append(text)
            n += 1

    hull_chain = rows[prefix + "airship_hull_2"]["chain"]
    hull = sorted((r for r in rows.values() if r["chain"] == hull_chain), key=lambda r: r["level"])

    def level_of(row):
        short = row["level_name"].removeprefix(prefix)
        icon = crew_buildings.icon_of(short, drawn)
        return {"key": row["level_name"], "short": short, "chain": row["chain"], "level": row["level"], "name": name_of(row["level_name"]),
                "text": loc.get(f"building_short_description_texts_short_description_{row['level_name']}", ""),
                "cost": row["create_cost"], "turns": row["create_time"], "dev": row["development_point_cost"],
                "tier": row["primary_slot_building_building_level_requirement"] + 1,
                "requires": required.get(row["level_name"], []),
                # our own icon: data/ui/buildings/<file>.png, served by tools/web_serve.py at /mod/ui/buildings/
                "icon": (icon.removeprefix("tww3_mtb_") + ".png") if icon else None,
                "lines": green(short), "unlocks": [dict(b) for b in bindings.get(row["level_name"], [])]}

    chains = []
    for chain in config["new_chains"]:
        chain_rows = sorted((r for r in rows.values() if r["chain"] == chain["key"]), key=lambda r: r["level"])
        chains.append({"key": chain["key"], "levels": [level_of(r) for r in chain_rows]})
    groups = {}
    for group_key, group in config["groups"].items():
        groups[group_key] = {"name": group["ui"]["name"], "about": group["ui"]["about"], "start": group["start"], "seats": len(group["seats"]),
                             "mount": group.get("mount"), "mount_name": group.get("mount_name"),
                             "requires": prefix + group["requires"]["building"] if group.get("requires") else None,
                             "options": {k: {"name": (o.get("ui") or {}).get("name", k), "about": (o.get("ui") or {}).get("about", ""),
                                             "hidden": bool((o.get("ui") or {}).get("hidden") or (o.get("ui") or {}).get("none")),
                                             "card": crew_ui.own_card_name(config, group_key, k),
                                             "upkeep": crew_ui.upkeep(o, stock), "hire": crew_ui.hire(o, stock)} for k, o in group["options"].items()}}
    data = {"_about": "Made by tools/web_export.py from data/crew_options.json and the game's tables through the mod's own build functions. Do not edit.",
            "prefix": prefix, "hull": [level_of(r) for r in hull], "chains": chains, "groups": groups, "auto_active": [prefix + s for s in config["auto_active"]],
            "levels": levels, "art": json.loads((REPO / "data" / "crew_ui_art.json").read_text(encoding="utf-8"))}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    guns = next(c for c in chains if c["key"] == "mtb_guns")["levels"][0]
    print("data:", guns["name"], guns["cost"], "gold,", guns["turns"], "turn(s), tier", guns["tier"], "icon", guns["icon"], "lines", guns["lines"])
    return data


# ---------------- models ----------------
def material_textures(path, root):
    """{slot: texture path} of a .xml.material, and whether it is alpha tested."""
    text = source_file(path, root).decode("utf-8", "replace")
    slots = dict(re.findall(r"<slot[^>]*>([^<]+)</slot>\s*<source>([^<]+)</source>", text))
    return {"base": slots.get("t_xml_base_colour"), "normal": slots.get("t_xml_normal"), "material": slots.get("t_xml_material_map"),
            "alpha": "alpha_on" in path}


def load_model(geometry, wsmodel, root):
    """LOD 0 of a model: [(mesh, material path)]."""
    model = rmv2.load(source_file(geometry, root))
    mats = hull_parts.materials(source_file(wsmodel, root).decode("utf-8"))
    return [(mesh, mats[(0, part)]) for part, mesh in enumerate(model["lods"][0])]


def key_of(v):
    return round(v.x, 3), round(v.y, 3), round(v.z, 3)


def split(mesh, wanted):
    """(the mesh without the triangles of wanted, a mesh of only those)."""
    return hull_parts._select(mesh, set(range(len(mesh.tris))) - set(wanted)), hull_parts._select(mesh, set(wanted))


def shield_triangles(mesh, spec):
    """Triangles of the connected pieces wholly in the box (either side) and at least spec["least"] high and long."""
    found, pieces = set(), 0
    for tris, b in hull_parts.pieces(mesh):
        same_side = b[0] * b[3] > 0
        inside = (same_side and spec["abs_x"][0] <= min(abs(b[0]), abs(b[3])) and max(abs(b[0]), abs(b[3])) <= spec["abs_x"][1]
                  and spec["y"][0] <= b[1] and b[4] <= spec["y"][1] and spec["z"][0] <= b[2] and b[5] <= spec["z"][1])
        if inside and b[4] - b[1] >= spec["least"] and b[5] - b[2] >= spec["least"]:
            found.update(tris)
            pieces += 1
    return found, pieces


def bounds(mesh):
    xs, ys, zs = [v.x for v in mesh.verts], [v.y for v in mesh.verts], [v.z for v in mesh.verts]
    return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)


def port_split(base_mesh, stock_mesh, others=()):
    """(base triangles of the plug, stock triangles of the open port with its surroundings) around both ports. others: meshes of the other parts
    (the porthole stands near the port): their triangles belong to them, not to the port."""
    box = hull_parts.SPEC["patches"]["port"]["hole_box"]
    m = PORT_MARGIN

    # the porthole's own closed hole lies within the margin: its place (the box of its part, a little wider) is left to it
    ports = [b for b in (bounds(mm) for mm in others) if b[2] <= box[5] + m and b[5] >= box[2] - m and b[4] >= box[1] - m and b[1] <= box[4] + m]

    # the base keeps a wider band round it than the stock gives back: a seam may overlap a little, but it has no gap
    def near(mesh, t, keep=0.0):
        x, y, z = (sum(getattr(mesh.verts[i], a) for i in t) / 3 for a in "xyz")
        if any(b[0] - keep <= x <= b[3] + keep and b[1] - keep <= y <= b[4] + keep and b[2] - keep <= z <= b[5] + keep for b in ports):
            return False
        return box[0] - m <= abs(x) <= box[3] + m and box[1] - m <= y <= box[4] + m and box[2] - m <= z <= box[5] + m
    stock_keys = {key_of(v) for v in stock_mesh.verts}
    plug = {i for i, t in enumerate(base_mesh.tris) if near(base_mesh, t, 0.15) and any(key_of(base_mesh.verts[j]) not in stock_keys for j in t)}
    base_tris = {tuple(sorted(key_of(base_mesh.verts[j]) for j in t)) for k, t in enumerate(base_mesh.tris) if k not in plug}
    taken = base_tris | {tuple(sorted(key_of(m.verts[j]) for j in t)) for m in others for t in m.tris}
    port = {i for i, t in enumerate(stock_mesh.tris) if near(stock_mesh, t) and tuple(sorted(key_of(stock_mesh.verts[j]) for j in t)) not in taken}
    return plug, port


def tex_name(path, root):
    """PNG name of a texture: the folder of build/ it came from in front, so the same name from two folders does not clash."""
    if root is not None and (root / path).exists():
        return root.relative_to(REPO / "build").as_posix().replace("/", "__") + "__" + Path(path).stem + ".png"
    return Path(path).stem + ".png"


class Gltf:
    """One .gltf + .bin of several nodes. Game axes are left-handed (x right, y up, z forward): x is mirrored and the winding turned, so three.js shows
    the same ship, not its mirror image. Skinned models are already in their rest pose in the file, so no skeleton is needed."""

    def __init__(self, name):
        self.name = name
        self.blob = bytearray()
        self.views, self.accessors, self.meshes, self.materials, self.textures, self.images, self.nodes = [], [], [], [], [], [], []
        self.image_of, self.material_of = {}, {}
        self.wanted = []        # (texture path, root)
        self.box = [1e9, 1e9, 1e9, -1e9, -1e9, -1e9]

    def view(self, data, target):
        while len(self.blob) % 4:
            self.blob.append(0)
        self.views.append({"buffer": 0, "byteOffset": len(self.blob), "byteLength": len(data), "target": target})
        self.blob.extend(data)
        return len(self.views) - 1

    def texture(self, path, root):
        if not path:
            return None
        png = tex_name(path, root)
        if png not in self.image_of:
            self.images.append({"uri": "../tex/" + png})
            self.textures.append({"source": len(self.images) - 1, "sampler": 0})
            self.image_of[png] = len(self.textures) - 1
            self.wanted.append((path, root))
        return self.image_of[png]

    def material(self, path, root):
        key = (path, str(root))
        if key not in self.material_of:
            spec = material_textures(path, root)
            m = {"name": Path(path).name, "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.85}, "doubleSided": spec["alpha"]}
            base = self.texture(spec["base"], root)
            if base is not None:
                m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": base}
            normal = self.texture(spec["normal"], root)
            if normal is not None:
                m["normalTexture"] = {"index": normal}
            if spec["alpha"]:
                m.update(alphaMode="MASK", alphaCutoff=0.5)
            self.materials.append(m)
            self.material_of[key] = len(self.materials) - 1
        return self.material_of[key]

    def add(self, node, meshes, root):
        """A node of [(mesh, material path)], one primitive each. Returns its triangle count."""
        prims = []
        for mesh, material in meshes:
            if not mesh.tris:
                continue
            pos, nor, uv = bytearray(), bytearray(), bytearray()
            lo, hi = [1e9] * 3, [-1e9] * 3
            for v in mesh.verts:
                p = (-v.x, v.y, v.z)
                n = blender_rmv2.normal(v)
                pos += struct.pack("<3f", *p)
                nor += struct.pack("<3f", -n[0], n[1], n[2])
                uv += struct.pack("<2f", *blender_rmv2.uv(v))
                for i in range(3):
                    lo[i], hi[i] = min(lo[i], p[i]), max(hi[i], p[i])
            for i in range(3):
                self.box[i], self.box[i + 3] = min(self.box[i], lo[i]), max(self.box[i + 3], hi[i])
            idx = bytearray()
            for a, b, c in mesh.tris:
                idx += struct.pack("<3I", a, c, b)
            count = len(mesh.verts)
            a_pos = len(self.accessors)
            self.accessors.append({"bufferView": self.view(pos, 34962), "componentType": 5126, "count": count, "type": "VEC3", "min": lo, "max": hi})
            self.accessors.append({"bufferView": self.view(nor, 34962), "componentType": 5126, "count": count, "type": "VEC3"})
            self.accessors.append({"bufferView": self.view(uv, 34962), "componentType": 5126, "count": count, "type": "VEC2"})
            self.accessors.append({"bufferView": self.view(idx, 34963), "componentType": 5125, "count": len(mesh.tris) * 3, "type": "SCALAR"})
            prims.append({"attributes": {"POSITION": a_pos, "NORMAL": a_pos + 1, "TEXCOORD_0": a_pos + 2}, "indices": a_pos + 3,
                          "material": self.material(material, root)})
        self.meshes.append({"name": node, "primitives": prims})
        self.nodes.append({"mesh": len(self.meshes) - 1, "name": node})
        return sum(len(m.tris) for m, _ in meshes)

    def write(self, extras):
        gltf = {"asset": {"version": "2.0", "generator": "tools/web_export.py"}, "scene": 0, "scenes": [{"nodes": list(range(len(self.nodes)))}],
                "nodes": self.nodes, "meshes": self.meshes, "materials": self.materials, "textures": self.textures, "images": self.images,
                "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
                "buffers": [{"uri": f"{self.name}.bin", "byteLength": len(self.blob)}], "bufferViews": self.views, "accessors": self.accessors,
                "extras": dict(extras, box=self.box)}
        folder = OUT / "models"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{self.name}.bin").write_bytes(bytes(self.blob))
        (folder / f"{self.name}.gltf").write_text(json.dumps(gltf, indent=1), encoding="utf-8")
        return self.wanted


def export_models(stock_too=False):
    """build/web/models: hull_base (nodes hull, port_plug, hatch_covers) and one model per detail (part_<name>), all in the hull's frame."""
    report, textures = {}, []
    base = load_model(*BASE_HULL, BASE)
    stock = load_model(*STOCK_HULL, None)
    hull0, material0 = base[0]
    # the shields out of the base hull
    cuts = {}
    for name, spec in SHIELDS.items():
        tris, pieces = shield_triangles(hull0, spec)
        if pieces != spec["pieces"]:
            raise SystemExit(f"{name}: {pieces} pieces in the box, expected {spec['pieces']}: the hull changed, look at the box again")
        cuts[name] = tris
    hull0_cut, _ = split(hull0, set().union(*cuts.values()))
    part_meshes = {name: load_model(DT + model + ".rigid_model_v2", DT + model + ".wsmodel", REPO / "build" / folder) for name, (folder, model) in PART_MODELS.items()}
    plug, port = port_split(hull0_cut, stock[0][0], [m for meshes in part_meshes.values() for m, _ in meshes])
    hull0_open, plug_mesh = split(hull0_cut, plug)
    _, port_mesh = split(stock[0][0], port)
    g = Gltf("hull_base")
    report["hull"] = g.add("hull", [(hull0_open, material0)] + base[1:], BASE)
    report["port_plug"] = g.add("port_plug", [(plug_mesh, material0)], BASE)
    report["hatch_covers"] = g.add("hatch_covers", load_model(*HATCH_COVERS, BASE), BASE)
    textures += g.write({"source": str(BASE.relative_to(REPO)), "about": "the base barge: no shields, porthole, stern boards, forsage tank; port and hatches closed"})
    # the parts: shields (stock pieces read the stock texture: same triangles, same UV), the port, the details of build/solid_hull_*
    for name, tris in cuts.items():
        _, piece = split(hull0, tris)
        g = Gltf("part_" + name)
        report["part_" + name] = g.add(name, [(piece, stock[0][1])], None)
        textures += g.write({"source": f"cut from {BASE_HULL[0]} by tools/web_export.py, SHIELDS"})
    g = Gltf("part_port")
    report["part_port"] = g.add("port", [(port_mesh, stock[0][1])], None)
    textures += g.write({"source": "the stock hull around the port, tools/web_export.py, port_split"})
    for name, (folder, model) in PART_MODELS.items():
        root = REPO / "build" / folder
        g = Gltf("part_" + name)
        report["part_" + name] = g.add(name, part_meshes[name], root)
        textures += g.write({"source": f"build/{folder}/{DT}{model}"})
    if stock_too:
        g = Gltf("hull_stock")
        report["hull_stock"] = g.add("hull", stock, None)
        textures += g.write({"source": STOCK_HULL[0]})
    print("models, triangles of LOD 0:", report)
    raw = OUT / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (OUT / "tex").mkdir(parents=True, exist_ok=True)
    seen, jobs = set(), []
    for path, root in textures:
        png = tex_name(path, root)
        if png in seen:
            continue
        seen.add(png)
        target = raw / (Path(png).stem + ".dds")
        blob = source_file(path, root)
        if not target.exists() or target.read_bytes() != blob or not (OUT / "tex" / png).exists():
            target.write_bytes(blob)
            jobs.append([str(target), str(OUT / "tex" / png), "normal" if "normal" in Path(path).stem else "colour"])
    (raw / "jobs.json").write_text(json.dumps(jobs, indent=1), encoding="utf-8")
    # Pillow decodes BC1 and BC3; it is installed for Python 3.10, as for tools/crew_ui_art.py
    if jobs:
        subprocess.run(["py", "-3.10", str(REPO / "tools" / "web_textures.py"), str(raw / "jobs.json")], check=True)
    (OUT / "models" / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


def export_game_ui():
    got = game_files(GAME_UI)
    for path, blob in got.items():
        target = OUT / "game" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    missing = sorted(set(GAME_UI) - set(got))
    print(f"game UI pictures: {len(got)}" + (f", not in the packs: {missing}" if missing else ""))
    (OUT / "game" / "index.json").write_text(json.dumps(sorted(got), indent=1), encoding="utf-8")


def export_vendor():
    """three.js from the npm registry, a pinned version; npm checks the tarball's integrity."""
    folder = OUT / "vendor"
    folder.mkdir(parents=True, exist_ok=True)
    tgz = folder / f"three-{THREE}.tgz"
    if not tgz.exists():
        subprocess.run(["npm", "pack", f"three@{THREE}", "--pack-destination", str(folder)], check=True, shell=True)
    with tarfile.open(tgz) as tar:
        for rel in THREE_FILES:
            try:
                member = tar.getmember("package/" + rel)
            except KeyError:
                continue
            target = folder / "three" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
    print("three.js", THREE, "sha256 of the tarball", hashlib.sha256(tgz.read_bytes()).hexdigest()[:16])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", action="store_true")
    ap.add_argument("--models", action="store_true")
    ap.add_argument("--ui", action="store_true")
    ap.add_argument("--vendor", action="store_true")
    ap.add_argument("--stock", action="store_true", help="also the stock hull, for ?hull=stock")
    a = ap.parse_args()
    everything = not (a.data or a.models or a.ui or a.vendor)
    if everything or a.data:
        export_data()
    if everything or a.ui:
        export_game_ui()
    if everything or a.vendor:
        export_vendor()
    if everything or a.models:
        export_models(a.stock)
    (OUT / "manifest.json").write_text(json.dumps({"three": THREE, "base": str(BASE.relative_to(REPO))}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
