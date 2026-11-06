"""Export for the local web page of the airship screen (web/): py -3.14 tools/web_export.py [--data] [--models] [--vendor]

Everything goes to build/web/ (outside git): the game's models, textures and UI pictures must not reach the public repository.
  build/web/data.json       buildings of the barge as the mod builds them: the same functions as tools/build.py, nothing copied by hand
  build/web/models/*.gltf   hull without the gun port (build/keep/hull_port_closed_v1) and the stock hull with it, LOD 0, game axes mirrored to three.js
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
KEEP = REPO / "build" / "keep" / "hull_port_closed_v1"
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
HULLS = {
    # name: (geometry source, .wsmodel source): "keep:" is a file of build/keep/hull_port_closed_v1, otherwise a path in the game's packs
    "hull_closed": ("keep:warmachines/aircraft/dwf_thunderbarge/tww3_mtb_dwf_thunderbarge_01.rigid_model_v2",
                    "keep:warmachines/aircraft/dwf_thunderbarge/tww3_mtb_dwf_thunderbarge_grungni_01.wsmodel"),
    "hull_port": (hull_parts.SPEC["source"], hull_parts.SPEC["wsmodel"]),
}


# ---------------- files of the game and of build/keep ----------------
_found = {}


def game_files(paths):
    """{path: bytes} of the game's packs, one pass over all of them; a later pack wins, as in hull_parts.game_file. Missing paths are left out."""
    want = {p.replace("/", "\\").lower(): p for p in paths if p.replace("/", "\\").lower() not in _found}
    if want:
        for pack in sorted(gamepack.DATA.glob("*.pack")):
            if pack.name.startswith(("audio", "local_")):
                continue
            for name, blob in gamepack.entries(pack, lambda n: n.lower() in want):
                _found[name.lower()] = blob
    return {p: _found[p.replace("/", "\\").lower()] for p in paths if p.replace("/", "\\").lower() in _found}


def source_file(path):
    if path.startswith("keep:"):
        return (KEEP / path.removeprefix("keep:")).read_bytes()
    local = KEEP / path
    if path.startswith("warmachines/") and local.exists():      # a file of the accepted hull overrides the game's, as in the mod's pack
        return local.read_bytes()
    got = game_files([path])
    if path not in got:
        raise SystemExit(f"{path}: not in build/keep nor in the game's packs")
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
def material_textures(path):
    """{slot: texture path} of a .xml.material, and whether it is alpha tested."""
    text = source_file(path).decode("utf-8", "replace")
    slots = dict(re.findall(r"<slot[^>]*>([^<]+)</slot>\s*<source>([^<]+)</source>", text))
    return {"base": slots.get("t_xml_base_colour"), "normal": slots.get("t_xml_normal"), "material": slots.get("t_xml_material_map"),
            "alpha": "alpha_on" in path}


def to_gltf(name, geometry, wsmodel):
    """LOD 0 of a game model as .gltf + .bin. Game axes are left-handed (x right, y up, z forward): x is mirrored and the winding turned, so three.js shows
    the same ship, not its mirror image. The hull is skinned, but in its file every vertex is already in the rest pose, so no skeleton is needed."""
    model = rmv2.load(source_file(geometry))
    ws = source_file(wsmodel).decode("utf-8")
    mats = hull_parts.materials(ws)
    blob = bytearray()
    views, accessors, meshes_out, materials, textures, images, nodes = [], [], [], [], [], [], []
    image_of = {}

    def view(data, target):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), "target": target})
        blob.extend(data)
        return len(views) - 1

    def texture(path, tex_list):
        if not path:
            return None
        png = Path(path).stem + ".png"
        if png not in image_of:
            images.append({"uri": "../tex/" + png})
            textures.append({"source": len(images) - 1, "sampler": 0})
            image_of[png] = len(textures) - 1
            tex_list.append(path)
        return image_of[png]

    wanted = []
    box = [1e9, 1e9, 1e9, -1e9, -1e9, -1e9]
    for part, mesh in enumerate(model["lods"][0]):
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
            box[i], box[i + 3] = min(box[i], lo[i]), max(box[i + 3], hi[i])
        idx = bytearray()
        for a, b, c in mesh.tris:
            idx += struct.pack("<3I", a, c, b)
        count = len(mesh.verts)
        a_pos = len(accessors)
        accessors.append({"bufferView": view(pos, 34962), "componentType": 5126, "count": count, "type": "VEC3", "min": lo, "max": hi})
        accessors.append({"bufferView": view(nor, 34962), "componentType": 5126, "count": count, "type": "VEC3"})
        accessors.append({"bufferView": view(uv, 34962), "componentType": 5126, "count": count, "type": "VEC2"})
        accessors.append({"bufferView": view(idx, 34963), "componentType": 5125, "count": len(mesh.tris) * 3, "type": "SCALAR"})
        spec = material_textures(mats[(0, part)])
        m = {"name": Path(mats[(0, part)]).name, "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.85}, "doubleSided": spec["alpha"]}
        base = texture(spec["base"], wanted)
        if base is not None:
            m["pbrMetallicRoughness"]["baseColorTexture"] = {"index": base}
        normal = texture(spec["normal"], wanted)
        if normal is not None:
            m["normalTexture"] = {"index": normal}
        if spec["alpha"]:
            m.update(alphaMode="MASK", alphaCutoff=0.5)
        materials.append(m)
        meshes_out.append({"name": f"{mesh.name}_{part}", "primitives": [{"attributes": {"POSITION": a_pos, "NORMAL": a_pos + 1, "TEXCOORD_0": a_pos + 2},
                                                                          "indices": a_pos + 3, "material": len(materials) - 1}]})
        nodes.append({"mesh": len(meshes_out) - 1, "name": meshes_out[-1]["name"]})
    gltf = {"asset": {"version": "2.0", "generator": "tools/web_export.py"}, "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes,
            "meshes": meshes_out, "materials": materials, "textures": textures, "images": images,
            "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 10497, "wrapT": 10497}],
            "buffers": [{"uri": f"{name}.bin", "byteLength": len(blob)}], "bufferViews": views, "accessors": accessors,
            "extras": {"source": geometry, "wsmodel": wsmodel, "box": box}}
    folder = OUT / "models"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.bin").write_bytes(bytes(blob))
    (folder / f"{name}.gltf").write_text(json.dumps(gltf, indent=1), encoding="utf-8")
    print(f"model {name}: {sum(len(m.tris) for m in model['lods'][0])} triangles, box {[round(x, 2) for x in box]}, textures {[Path(p).name for p in wanted]}")
    return wanted


def export_models():
    textures = []
    for name, (geometry, wsmodel) in HULLS.items():
        textures += [p for p in to_gltf(name, geometry, wsmodel) if p not in textures]
    raw = OUT / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    jobs = []
    for path in textures:
        target = raw / Path(path).name
        target.write_bytes(source_file(path))
        kind = "normal" if "normal" in Path(path).stem else "colour"
        jobs.append([str(target), str(OUT / "tex" / (Path(path).stem + ".png")), kind])
    (OUT / "tex").mkdir(parents=True, exist_ok=True)
    (raw / "jobs.json").write_text(json.dumps(jobs, indent=1), encoding="utf-8")
    # Pillow decodes BC1 and BC3; it is installed for Python 3.10, as for tools/crew_ui_art.py
    subprocess.run(["py", "-3.10", str(REPO / "tools" / "web_textures.py"), str(raw / "jobs.json")], check=True)


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
    a = ap.parse_args()
    everything = not (a.data or a.models or a.ui or a.vendor)
    if everything or a.data:
        export_data()
    if everything or a.ui:
        export_game_ui()
    if everything or a.vendor:
        export_vendor()
    if everything or a.models:
        export_models()
    (OUT / "manifest.json").write_text(json.dumps({"three": THREE, "keep": str(KEEP.relative_to(REPO))}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
