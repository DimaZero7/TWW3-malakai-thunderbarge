"""Export for the local web page of the airship screen (web/): py -3.14 tools/web_export.py [--data] [--models] [--vendor]

Everything goes to build/web/ (outside git): the game's models, textures and UI pictures must not reach the public repository.
  build/web/data.json       buildings of the barge as the mod builds them: the same functions as tools/build.py, nothing copied by hand
  build/web/models/*.gltf   the base barge (build/solid_hull_hatches without the shields) and each removed detail as a model of its own, LOD 0,
                            game axes mirrored to three.js (export_models)
  build/web/tex/*.png       their textures, DDS turned into PNG by tools/web_textures.py (py -3.10, Pillow)
  build/web/catalog.json    the game's effects of the dwarfs' buildings and the dwarfs' army units, for the constructor (export_catalog)
  build/web/overview.json   every chain of the barge with its levels, effects, crew options, units, model details (export_overview)
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
import dbtable  # noqa: E402
import gamepack  # noqa: E402
import hull_parts  # noqa: E402
import rmv2  # noqa: E402

OUT = REPO / "build" / "web"
THREE = "0.170.0"
THREE_FILES = ["build/three.module.js", "build/three.core.js", "examples/jsm/controls/OrbitControls.js", "examples/jsm/loaders/GLTFLoader.js",
               "examples/jsm/utils/BufferGeometryUtils.js", "LICENSE"]
# Malakai's portrait of the game (character portholes), and the round copy of its face the side marks show (tools/web_textures.py, round)
PORTRAIT = "ui/portraits/portholes/no_culture/dwf_malakai_makaisson_0.png"
PORTRAIT_ROUND = "ui/portraits/round/mtb_malakai.png"
PORTRAIT_FACE = [92, 0, 222, 130]       # the face's square in the 300 x 164 portrait
# The game's UI pictures of the panel (src/tww3_mtb_crew_ui.lua, tools/crew_ui.py).
GAME_UI = ["ui/skins/default/panel_back_border.png", "ui/skins/default/panel_back_tile.png", "ui/skins/default/panel_back_inner_frame.png",
           "ui/skins/default/panel_back_tile_stone.png", "ui/skins/default/panel_back_frame.png", "ui/skins/wh_main_dwf_dwarfs/panel_title_large.png",
           "ui/skins/default/icon_cross.png", "ui/skins/default/icon_treasury.png", "ui/skins/default/icon_income.png", "ui/skins/default/icon_padlock.png",
           "ui/skins/default/icon_check.png", "ui/skins/default/icon_end_turn.png", "ui/skins/default/icon_hourglass.png",
           "ui/skins/default/icon_stat_ranged_damage.png", "ui/skins/default/icon_stat_reload_time.png",
           "ui/skins/default/icon_stat_range.png", "ui/skins/default/icon_stat_ammo.png", PORTRAIT,
           # the building tree's slot (ui/templates/building_frame.twui.xml, square_building_button and its cost and turns banners)
           "ui/skins/default/building_frame.png", "ui/skins/default/building_frame_plain.png", "ui/skins/default/building_frame_hover.png",
           "ui/skins/default/building_frame_selected.png", "ui/skins/default/building_frame_selected_hover.png", "ui/skins/default/icon_check_green.png", "ui/skins/default/build_frame_cross.png",
           "ui/skins/default/padlock.png", "ui/skins/default/icon_banner_bg.png", "ui/skins/default/red_text_banner_shadow.png",
           "ui/skins/default/turns_banner_queued.png", "ui/skins/default/turns_banner.png", "ui/skins/default/1x1_transparent_white.png",
           # the small unit cards beside a slot of the game's building browser (ui/templates/building_frame.twui.xml, units_list): the frame over the unit's
           # picture; the pictures of the units themselves come with export_data (unit_card_of)
           "ui/skins/default/unit_card_build_frame.png",
           # the game's building information window (ui/campaign ui/building_information.twui.xml and its entries)
           "ui/skins/default/tooltip_frame.png", "ui/skins/default/separator_skull2.png", "ui/skins/default/unit_cat_holder_round.png",
           "ui/skins/default/replenishement_positive.png",
           # the army panel's unit card (ui/common ui/land_unit_card.twui.xml), for the crew's choice: the frame over the unit's picture, the plate of the
           # number of men and its bar, the half round of the unit's category, the frame of the selected card
           "ui/skins/default/unit_card_frame_plain.png", "ui/skins/default/unit_card_back.png", "ui/skins/default/bar_white.png",
           "ui/skins/default/unit_card_semicircle.png", "ui/skins/default/unit_card_selected.png",
           # the game's unit information panel (ui/common ui/unit_information.twui.xml): the parchment, the header of its stats, the icons of its top bar
           "ui/skins/default/parchment_texture_v_rolls.png", "ui/skins/default/parchment_button_square_active.png", "ui/skins/default/parchment_header_min.png",
           "ui/skins/default/icon_entity_small.png", "ui/skins/default/parchment_divider_2.png", "ui/skins/default/bar_back.png",
           "ui/skins/default/icon_stat_damage.png",
           "ui/skins/default/modifier_icon_armour_piercing.png",
           "ui/skins/default/frame_text.png"]      # the plate of a recruitment card's cost
GAME_UI += [f"ui/skins/default/constructing_{i}.png" for i in range(1, 13)]
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
# The pub (table, barrels, mugs) and the crow's nests' rings: the mod cuts them out of the hull by the boxes of data/hull_parts.json (tools/hull_parts.py,
# details pub and rings) and stands them on crew seats the beer hall and the nests switch on. The base hull of build/solid_hull_* still has them: cut the same way.
MOD_DETAILS = ["pub", "rings"]
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
def campaign_text():
    """The mod's own texts (data/campaign_text.json): tools/build.py writes them into the pack's .loc, over the game's."""
    return json.loads((REPO / "data" / "campaign_text.json").read_text(encoding="utf-8"))


def unit_group_icons():
    """{ui unit group: icon} of the game's ui_unit_groupings table, whose icon is not always the key (missile_infantry_crossbow: missile_infantry_bow_dwf).
    The table has no layout in data/db_layouts.json: its rows are read as they lie, strings with a u16 length."""
    out = {}
    for _, blob in gamepack.entries(gamepack.DATA / "db.pack", lambda n: n.lower().startswith("db" + chr(92) + "ui_unit_groupings_tables")):
        strings, pos = [], 0
        for m in re.finditer(rb"[a-z0-9_]{4,}", blob):
            start, text = m.start(), m.group()
            if start >= 2 and struct.unpack_from("<H", blob, start - 2)[0] == len(text):
                strings.append((start, text.decode()))
        # a row is icon, key, parent group, one after another: runs of strings that follow each other at once, taken three at a time
        run = []
        for start, text in strings + [(-1, "")]:
            if run and start == run[-1][0] + len(run[-1][1]) + 2:
                run.append((start, text))
                continue
            for i in range(0, len(run) - 2, 3):
                out.setdefault(run[i + 1][1], run[i][1])
            run = [(start, text)]
    return out


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
                "game_name": names.get(f"building_culture_variants_name_{row['level_name']}"),      # the game's own name, when the mod renames it
                "text": loc.get(f"building_short_description_texts_short_description_{row['level_name']}") or campaign_text().get(f"building_short_description_texts_short_description_{row['level_name']}", ""),
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
    # the game's own side chains of the barge too (the beer hall, the crew training, ...), visible ones only, so the page's tree can hold them
    ours = {c["key"] for c in config["new_chains"]}
    for chain in sorted({r["chain"] for r in rows.values() if r["level_name"].startswith(prefix)} - ours - {hull_chain}):
        chain_rows = sorted((r for r in rows.values() if r["chain"] == chain and r["level_name"].startswith(prefix)), key=lambda r: r["level"])
        if any(r["visible_in_ui"] for r in chain_rows):
            chains.append({"key": chain, "levels": [level_of(r) for r in chain_rows if r["visible_in_ui"]]})
    # The game's own unit card of a crew option, as the army panel shows the unit it is taken from (upkeep_from): the picture of unit_variants.unit_card,
    # the category icon of main_units.ui_unit_group_land, the number of men aboard. Copies of the game's pictures go to build/web/game only.
    variant_card = {r["unit"]: r["unit_card"] for r in stock["unit_variants"]}
    unit_group = {r["unit"]: r["ui_unit_group_land"] for r in stock["main_units"]}
    group_icons = unit_group_icons()
    unit_pictures = []

    unit_of_card = {}
    for unit, picture in variant_card.items():
        unit_of_card.setdefault(picture, unit)

    def unit_card_of(option):
        source = option.get("upkeep_from") or {}
        unit = source.get("unit")
        if not unit or unit not in variant_card:
            return None
        if option.get("stock"):
            # the barge's own crew (its upkeep is the barge's): the card the mod's panel shows for it (ui.card, a unit of the game that stands for
            # it: the cannon, the gyrobomber, the miners with charges), its category from that unit
            picture = (option.get("ui") or {}).get("card")
            unit = unit_of_card.get(picture)
            if not picture or not unit:
                return None
            card = {"picture": f"ui/units/icons/{picture}.png", "category": f"ui/common ui/unit_category_icons/{group_icons.get(unit_group[unit], unit_group[unit])}.png", "men": source["count"]}
        else:
            card = {"picture": f"ui/units/icons/{variant_card[unit]}.png", "category": f"ui/common ui/unit_category_icons/{group_icons.get(unit_group[unit], unit_group[unit])}.png", "men": source["count"]}
        unit_pictures.extend([card["picture"], card["category"]])
        return card

    def drawn_card_of(group_key, key):
        """The mod's own drawn card of an option (data/ui/crew_cards, tools/crew_cards.py: the game's models rendered on the barge), as a pack path the
        page serves from data/ui; None when the mod has none."""
        name = crew_ui.own_card_name(config, group_key, key)
        if not name:
            return None
        return crew_ui.drawn_path(name)

    def fragments_of(option):
        """A bomb that bursts into burning pieces in the air (an explosion with shrapnel): the blast of one piece, from the game's tables."""
        weapon = option.get("weapon")
        w = next((r for r in stock["missile_weapons"] if r["key"] == weapon), None) if weapon else None
        p = next((r for r in stock["projectiles"] if r["key"] == w["default_projectile"]), None) if w else None
        e = next((r for r in stock["projectiles_explosions"] if r["key"] == p["explosion_type"]), None) if p and p.get("explosion_type") else None
        piece = next((r for r in stock["projectiles"] if r["key"] == e["shrapnel"]), None) if e and e.get("shrapnel") else None
        if not piece or not piece.get("explosion_type"):
            return None
        pe = next((r for r in stock["projectiles_explosions"] if r["key"] == piece["explosion_type"]), None)
        return {"blast": round(pe["detonation_damage"]), "blast_ap": round(pe["detonation_damage_ap"]), "radius": round(pe["detonation_radius"], 1)} if pe else None

    # the crew's own rows (seats, weapons, projectiles), as tools/build.py adds them to the campaign pack: the numbers of each option come from them
    crew_tables = {k: [dict(r) for r in v] for k, v in t.items() if isinstance(v, list)}
    crew_options.extend(crew_tables, stock, build.UNIT, build.BARGE)
    crew_tables["_stock"] = stock
    groups = {}
    for group_key, group in config["groups"].items():
        groups[group_key] = {"name": group["ui"]["name"], "about": group["ui"]["about"], "start": group["start"], "seats": len(group["seats"]),
                             "mount": group.get("mount"), "mount_name": group.get("mount_name"), "card_frame": group.get("card_frame"),
                             # buildings that make the group shoot tighter: the spread of its shots times this (data/crew_options.json, boost)
                             "boost": [{"building": prefix + b, "spread": step["calibration_area"], "range": step.get("effective_range")}
                                       for b, step in zip(group["boost"]["buildings"], group["boost"]["steps"])] if group.get("boost") else [],
                             "requires": prefix + group["requires"]["building"] if group.get("requires") else None,
                             "options": {k: {"name": (o.get("ui") or {}).get("name", k), "about": (o.get("ui") or {}).get("about", ""),
                                             "hidden": bool((o.get("ui") or {}).get("hidden") or (o.get("ui") or {}).get("none")),
                                             "card": crew_ui.own_card_name(config, group_key, k), "unit_card": unit_card_of(o),
                                             "drawn_card": drawn_card_of(group_key, k),
                                             # what the mod's panel writes instead of a number (a bomb falls under the barge) and a burst's pieces
                                             "range_text": (o.get("ui") or {}).get("range_text"), "fragments": fragments_of(o),
                                             # the crew's own weapon as the mod builds it (the numbers of the mod's panel, crew_ui.group_numbers)
                                             "numbers": crew_ui.group_numbers(crew_tables, group_key, k, o, group),
                                             "upkeep": crew_ui.upkeep(o, stock), "hire": crew_ui.hire(o, stock)} for k, o in group["options"].items()}}
    data = {"_about": "Made by tools/web_export.py from data/crew_options.json and the game's tables through the mod's own build functions. Do not edit.",
            "prefix": prefix, "ammo_mod": {prefix + k: v for k, v in config["ammo_mod"].items()}, "hull": [level_of(r) for r in hull], "chains": chains, "groups": groups, "auto_active": [prefix + s for s in config["auto_active"]],
            "levels": levels, "art": json.loads((REPO / "data" / "crew_ui_art.json").read_text(encoding="utf-8"))}
    OUT.mkdir(parents=True, exist_ok=True)
    for path, blob in game_files(sorted(set(unit_pictures))).items():
        target = OUT / "game" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
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
    # the mod's own details out of their meshes, by its boxes and its rule (connected pieces wholly inside a box)
    mod_cuts = {}
    for name in MOD_DETAILS:
        detail = next(d for d in hull_parts.SPEC["details"] if d["name"] == name)
        mesh = base[detail["mesh"]][0]
        tris = set()
        for piece, box in hull_parts.pieces(mesh):
            if any(hull_parts.inside(box, area) for area in detail["boxes"]):
                tris.update(piece)
        if not tris:
            raise SystemExit(f"{name}: nothing of data/hull_parts.json's boxes in the base hull")
        mod_cuts[name] = (detail["mesh"], tris)
    removed = {0: set().union(*cuts.values())}
    for mi, tris in mod_cuts.values():
        removed[mi] = removed.get(mi, set()) | tris
    hull0_cut, _ = split(hull0, removed[0])
    base = [(base[i][0] if i not in removed or i == 0 else split(base[i][0], removed[i])[0], base[i][1]) for i in range(len(base))]
    part_meshes = {name: load_model(DT + model + ".rigid_model_v2", DT + model + ".wsmodel", REPO / "build" / folder) for name, (folder, model) in PART_MODELS.items()}
    plug, port = port_split(hull0_cut, stock[0][0], [m for meshes in part_meshes.values() for m, _ in meshes])
    hull0_open, plug_mesh = split(hull0_cut, plug)
    _, port_mesh = split(stock[0][0], port)
    g = Gltf("hull_base")
    report["hull"] = g.add("hull", [(hull0_open, material0)] + base[1:], BASE)
    report["port_plug"] = g.add("port_plug", [(plug_mesh, material0)], BASE)
    report["hatch_covers"] = g.add("hatch_covers", load_model(*HATCH_COVERS, BASE), BASE)
    textures += g.write({"source": str(BASE.relative_to(REPO)), "about": "the base barge: no shields, porthole, stern boards, forsage tank, pub, nests' rings; port and hatches closed"})
    # the parts: shields (stock pieces read the stock texture: same triangles, same UV), the port, the details of build/solid_hull_*
    for name, tris in cuts.items():
        _, piece = split(hull0, tris)
        g = Gltf("part_" + name)
        report["part_" + name] = g.add(name, [(piece, stock[0][1])], None)
        textures += g.write({"source": f"cut from {BASE_HULL[0]} by tools/web_export.py, SHIELDS"})
    for name, (mi, tris) in mod_cuts.items():
        _, piece = split(load_model(*BASE_HULL, BASE)[mi][0], tris)
        g = Gltf("part_" + name)
        report["part_" + name] = g.add(name, [(piece, stock[mi][1])], None)
        textures += g.write({"source": f"cut from {BASE_HULL[0]} by data/hull_parts.json, details {name} (tools/hull_parts.py's rule)"})
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


# ---------------- the overview of all the barge's chains, for planning (web/js/overview.js) ----------------
_replacements = {}


def effect_text(template, value):
    """The game's text of an effect with its value put in: %+n signed, %n plain; {{tr:key}} from the game's text replacements; picture and colour tags out."""
    if not _replacements:
        _replacements.update(crew_ui.game_text("ui_text_replacements_localised_text_"))
    v = int(value) if float(value).is_integer() else round(value, 2)
    text = template.replace("%+n", f"{v:+}" if isinstance(v, int) else f"{v:+g}").replace("%n", f"{v}")
    for _ in range(3):
        text = re.sub(r"\{\{tr:([^}]+)\}\}", lambda m: _replacements.get("ui_text_replacements_localised_text_" + m.group(1), m.group(1)), text)
    text = re.sub(r"\[\[img:[^\]]*\]\]\[\[/img\]\]", "", text)
    return re.sub(r"\[\[/?col[^\]]*\]\]", "", text).replace("||", " ").replace("\\n", " ").strip()


def units_allowed(stock_prefix):
    """building_units_allowed rows of the barge's buildings. The table is not in data/db_layouts.json: its columns come from the RPFM schema the way
    tools/refresh_layouts.py reads them (TWW3-batle-ai, read only). None when that schema is not there."""
    try:
        import refresh_layouts
        ron = (refresh_layouts.NEIGHBOUR / "build" / "rpfm" / "schema_wh3.ron").read_text(encoding="utf-8")
    except Exception as e:      # noqa: BLE001  the neighbour project or its schema is missing: the overview goes without recruitment
        print("units allowed: no schema,", e)
        return None
    sep = chr(92)
    for name, blob in gamepack.entries(gamepack.DATA / "db.pack", lambda n: n.count(sep) == 2 and n.split(sep)[1] == "building_units_allowed_tables"):
        fields = refresh_layouts.fields(ron, "building_units_allowed", dbtable.header(blob)[1])
        rows = dbtable.decode(blob, [tuple(f) for f in fields])
        return [r for r in rows if r["building"].startswith(stock_prefix)]
    return None


def export_overview():
    """build/web/overview.json: every chain of the barge (the hull and the side chains, the game's and this mod's) with each level as the mod's build makes it:
    name, icon, tier, price, turns, development points, what must stand first, every effect row with the game's text and value, the crew options it opens
    (with hire and upkeep), the units it allows, the abilities it enables, the detail of the model it brings (web/data/blueprint.json)."""
    stock = build.game_tables()
    t = build.derive(stock, "rider")
    t = build.derive_campaign(stock, {k: [dict(r) for r in v] for k, v in t.items()})
    loc = t.pop("__building_loc__")
    t.pop("__building_files__")
    config = crew_options.CONFIG
    prefix = config["buildings_prefix"]
    bindings, _, _ = crew_options.building_bindings(t, stock)
    lines = crew_ui.building_lines(config, t, stock, bindings)     # adds our effect rows to t too
    names = crew_ui.game_text("building_culture_variants_name_")
    # the game's texts, then the mod's own (data/campaign_text.json, into the pack's .loc by tools/build.py) over them, as the game shows them
    descriptions = crew_ui.game_text("building_short_description_texts_short_description_") | campaign_text()
    effect_texts = crew_ui.game_text("effects_description_") | {k: v for k, v in campaign_text().items() if k.startswith("effects_description_")}
    unit_names = crew_ui.game_text("land_units_onscreen_name_")
    texts = effect_texts | {k: v for k, v in (loc | lines).items() if k.startswith("effects_description_")}
    rows = {r["level_name"]: r for r in stock["building_levels"]} | {r["level_name"]: r for r in t["building_levels"]}
    rows = {k: r for k, r in rows.items() if k.startswith(prefix)}
    variants = {r["building"]: r for r in stock["building_culture_variants"] if r["building"].startswith(prefix)}
    variants |= {r["building"]: r for r in t["building_culture_variants"]}
    chains_info = {r["key"]: r for r in stock["building_chains"]} | {r["key"]: r for r in t["building_chains"]}
    # effect rows: ours (the !tww3_mtb table) override the game's rows of the same building, effect and scope, as in the game
    effects, changed = {}, set()
    for r in stock["building_effects_junction"]:
        if r["building"].startswith(prefix):
            effects[(r["building"], r["effect"], r["effect_scope"])] = r
    for r in t["building_effects_junction"]:
        key = (r["building"], r["effect"], r["effect_scope"])
        if key in effects:
            changed.add(key)
        effects[key] = r
    priority = {r["effect"]: r["priority"] for r in stock["effects"]} | {r["effect"]: r["priority"] for r in t["effects"]}
    # the icon of an effect in the game's lists (effects.icon, a file of ui/campaign ui/effect_bundles) and whether a positive value is good (green)
    effect_rows = {r["effect"]: r for r in stock["effects"]} | {r["effect"]: r for r in t["effects"]}
    required = {}
    for r in stock["building_level_required_buildings"] + t["building_level_required_buildings"]:
        if r["building_level"].startswith(prefix):
            required.setdefault(r["building_level"], []).append(r["required"])
    allowed = units_allowed(prefix)
    unit_land = {r["unit"]: r["land_unit"] for r in stock["main_units"]}
    abilities = {}
    for key, spec in config["abilities"].items():
        if not key.startswith("_"):
            for short in spec["enabled_by"]:
                abilities.setdefault(prefix + short, []).append({"key": key, "name": spec["name"], "about": spec["about"]})
    blueprint = json.loads((REPO / "web" / "data" / "blueprint.json").read_text(encoding="utf-8"))
    parts_of = {}
    for part, spec in blueprint["parts"].items():
        if spec.get("building"):
            parts_of.setdefault(prefix + spec["building"], []).append({"key": part, "name": spec["name"], "enabled": spec["enabled"]})
    groups = config["groups"]
    hull_chain = rows[prefix + "airship_hull_2"]["chain"]
    hull_names = {r["level"] + 1: names.get(f"building_culture_variants_name_{k}", k) for k, r in rows.items() if r["chain"] == hull_chain}
    renamed = {prefix + s: n for s, n in config.get("building_names", {}).items()} | {prefix + l["key"]: l["name"] for c in config["new_chains"] for l in c["levels"]}

    def name_of(key):
        return renamed.get(key) or names.get(f"building_culture_variants_name_{key}") or None

    icons = []
    chains = {}
    for key, r in rows.items():
        chains.setdefault(r["chain"], []).append(r)
    out = []
    for chain, levels in chains.items():
        levels.sort(key=lambda r: r["level"])
        if not any(r["visible_in_ui"] for r in levels):
            continue            # the game's own hidden chains (the summon, the ones marked to be deleted)
        cards, missing = [], set()
        for r in levels:
            key = r["level_name"]
            v = variants.get(key, {})
            icon = v.get("icon")
            if icon and icon.startswith("tww3_mtb_"):
                icon_url = "/mod/ui/buildings/" + icon.removeprefix("tww3_mtb_") + ".png"
            elif icon:
                icon_url = "/build/game/ui/buildings/icons/" + icon + ".png"
                icons.append("ui/buildings/icons/" + icon + ".png")
            else:
                icon_url = None
            effs = []
            for (b, e, scope), row in effects.items():
                if b != key:
                    continue
                template = texts.get(f"effects_description_{e}")
                effs.append({"effect": e, "scope": scope, "value": row["value"], "text": effect_text(template, row["value"]) if template else None,
                             "ours": e.startswith("mtb_"), "changed": (b, e, scope) in changed, "off": (b, e, scope) in changed and not row["value"],
                             "icon": "ui/campaign ui/effect_bundles/" + effect_rows[e]["icon"] if effect_rows.get(e, {}).get("icon") else None,
                             "good": (row["value"] >= 0) == bool(effect_rows.get(e, {}).get("is_positive_value_good", True)),
                             # hidden in the game's lists: priority 0, as the game's own hidden effects (the mod's hidden_effects too)
                             "hidden": "(HIDDEN" in (template or "") or priority.get(e) == 0})
            opens = []
            for b in bindings.get(key, []):
                g, o = groups[b["group"]], groups[b["group"]]["options"][b["option"]]
                opens.append({"group": b["group"], "group_name": g["ui"]["name"], "option": b["option"], "name": (o.get("ui") or {}).get("name", b["option"]),
                              "mount": g.get("mount") == b["option"], "mount_name": g.get("mount_name"),
                              # the panel lists the group (a choice of the crew panel); the pub is not a choice, buildings set it
                              "panel": not g.get("no_panel"),
                              "hire": crew_ui.hire(o, stock), "upkeep": crew_ui.upkeep(o, stock), "auto": key.removeprefix(prefix) in config["auto_active"] and bool(g.get("no_panel") or g.get("mount") == b["option"]),
                              "requires": prefix + g["requires"]["building"] if g.get("requires") else None})
            units = sorted({unit_names.get(f"land_units_onscreen_name_{unit_land.get(u['unit'], u['unit'])}", u["unit"]) for u in allowed if u["building"] == key}) if allowed else None
            need = list(required.get(key, []))
            below = next((x for x in levels if x["level"] == r["level"] - 1), None)
            card = {"key": key, "short": key.removeprefix(prefix), "level": r["level"], "name": name_of(key), "icon": icon_url,
                    "game_name": names.get(f"building_culture_variants_name_{key}"),
                    "text": loc.get(f"building_short_description_texts_short_description_{key}") or descriptions.get(f"building_short_description_texts_short_description_{v.get('short_description', key)}"),
                    "tier": r["primary_slot_building_building_level_requirement"] + 1 if chain != hull_chain else r["level"] + 1,
                    "hull_needed": hull_names.get(r["primary_slot_building_building_level_requirement"] + 1) if chain != hull_chain else None,
                    "cost": r["create_cost"], "turns": r["create_time"], "dev": r["development_point_cost"], "visible": r["visible_in_ui"],
                    "after": name_of(below["level_name"]) if below else None,
                    "requires": [{"key": n, "name": name_of(n)} for n in need],
                    "effects": effs, "opens": opens, "units": units, "abilities": abilities.get(key, []), "parts": parts_of.get(key, []),
                    "ours": key.removeprefix(prefix).startswith("mtb_")}
            # only what the player sees counts: the game's hidden effects and the ones the mod switches off are never shown
            seen = [e for e in effs if not e["hidden"] and not e["off"]]
            for field, bad in (("name", card["name"] is None), ("icon", icon_url is None), ("cost", not card["cost"] and r["level"] > 0),
                               ("effect text", any(e["text"] is None for e in seen)), ("description", not card["text"]),
                               ("effect text not in Russian", any(e["text"] and not re.search("[а-яА-Я]", e["text"]) for e in seen))):
                if bad:
                    missing.add(field)
            icons.extend(x["icon"] for x in effs if x["icon"])
            cards.append(card)
        crew = sorted({o["group_name"] for c in cards for o in c["opens"]})
        out.append({"chain": chain, "category": chains_info.get(chain, {}).get("chain_category"), "hull": chain == hull_chain,
                    "ours": all(c["ours"] for c in cards), "crew": crew, "title": cards[0]["name"] or chain, "cards": cards, "missing": sorted(missing)})
    order = ["cannons", "rifles", "cupolas", "bombs", "harpoon", "pub", "deck"]
    group_names = [groups[g]["ui"]["name"] for g in order if g in groups]

    def rank(c):
        if c["hull"]:
            return (0, 0)
        if c["crew"]:
            return (1, min(group_names.index(n) if n in group_names else 99 for n in c["crew"]), min(x["tier"] for x in c["cards"]))
        return (2, min(x["tier"] for x in c["cards"]), c["title"])
    out.sort(key=rank)
    got = game_files(icons)
    for path, blob in got.items():
        target = OUT / "game" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    data = {"_about": "Made by tools/web_export.py, export_overview: the mod's build functions over data/crew_options.json and the game's tables. Do not edit.",
            "units_from_schema": allowed is not None, "chains": out}
    (OUT / "overview.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("overview:", len(out), "chains,", sum(len(c["cards"]) for c in out), "levels; incomplete:", {c["title"]: c["missing"] for c in out if c["missing"]})


# ---------------- the constructor's catalogue: the game's effects and the dwarfs' army units (web/js/effects_model.mjs, constructor.js) ----------------
# The stat icons of the game's unit information panel (ui/common ui/unit_information.twui.xml, dynamic_stats) for an army unit's panel on the page.
UNIT_STAT_ICONS = ["ui/skins/default/icon_stat_health.png", "ui/skins/default/icon_stat_armour.png", "ui/skins/default/icon_stat_morale.png",
                   "ui/skins/default/icon_stat_speed.png", "ui/skins/default/icon_stat_attack.png", "ui/skins/default/icon_stat_defence.png",
                   "ui/skins/default/icon_stat_charge_bonus.png", "ui/skins/default/icon_stat_ranged_damage.png", "ui/skins/default/icon_stat_range.png",
                   "ui/skins/default/icon_stat_ammo.png", "ui/skins/default/icon_stat_reload_time.png", "ui/skins/default/icon_stat_damage.png",
                   "ui/skins/default/modifier_icon_armour_piercing.png", "ui/skins/default/icon_income.png", "ui/skins/default/icon_treasury.png",
                   "ui/skins/default/icon_entity_small.png", "ui/skins/default/unit_card_build_frame.png", "ui/skins/default/icon_hourglass.png"]
# the level of a building on its slot (ui/templates/building_frame.twui.xml, building_level: 20 x 20 at the slot's lower left corner, one picture a level)
UNIT_STAT_ICONS += [f"ui/skins/default/settlement_silver_numeral_{i}.png" for i in range(1, 6)]
# The dwarfs' unit keys (the game's own and its DLCs'); the faction's roster of custom battles is wh_main_dwf_dwarfs, Malakai's own units end in _malakai
DWARF_UNITS = ("wh_main_dwf_", "wh_dlc06_dwf_", "wh2_dlc10_dwf_", "wh3_dlc25_dwf_")


def armour_values():
    """{armour key: armour value} of unit_armour_types. Not in data/db_layouts.json; the layout of its version 6 read off the file: the value (i32), the key,
    the audio material (optional string). dbtable.decode reads the whole file with it or raises, so a wrong guess cannot pass. {} when it does not read."""
    sep = chr(92)
    for _, blob in gamepack.entries(gamepack.DATA / "db.pack", lambda n: n.count(sep) == 2 and n.split(sep)[1] == "unit_armour_types_tables"):
        if dbtable.header(blob)[1] != 6:
            return {}
        try:
            return {r["key"]: r["value"] for r in dbtable.decode(blob, [("value", "I32"), ("key", "StringU8"), ("audio", "OptionalStringU8")])}
        except ValueError:
            return {}
    return {}


def export_catalog():
    """build/web/catalog.json, for the constructor:
      game_effects  every effect the dwarfs' buildings use in the game (building_effects_junction of dwarf and Spirit of Grungni buildings), not hidden,
                    with its Russian text (%+n where the value goes), its icon (effects.icon), whether a positive value is good, its category, the scopes
                    and values it is used with
      army_units    the dwarfs' army units (main_units of the dwarf prefixes, no heroes, lords, renowned regiments, summoned or multiplayer ones): name,
                    card picture, category icon, caste, men, recruitment and upkeep, and the stats the game's unit panel shows, from land_units,
                    battle_entities, the missile weapon's projectile and unit_armour_types. Not read: the melee weapon (no layout of melee_weapons)."""
    stock = build.game_tables()
    names = crew_ui.game_text("land_units_onscreen_name_")
    # the game's texts, the mod's own over them (data/campaign_text.json goes into the pack's .loc), as the game shows them
    texts = crew_ui.game_text("effects_description_") | {k: v for k, v in campaign_text().items() if k.startswith("effects_description_")}
    effect_rows = {r["effect"]: r for r in stock["effects"]}
    uses = {}
    # the effects the barge's buildings use as the mod builds them (build/web/overview.json, export_overview): the line of sight of the nests is a
    # row of the mod's own table, not of the game's
    overview = OUT / "overview.json"
    if overview.exists():
        for chain in json.loads(overview.read_text(encoding="utf-8"))["chains"]:
            for card in chain["cards"]:
                for e in card["effects"]:
                    if not e["ours"] and not e["hidden"] and not e["off"]:
                        uses.setdefault(e["effect"], []).append((e["scope"], e["value"]))
    for r in stock["building_effects_junction"]:
        if not re.search(r"dwf|dwarf", r["building"]) or "_chd_" in r["building"] or "chaos_dwarf" in r["building"] or r["effect"].startswith("mtb_"):
            continue
        uses.setdefault(r["effect"], []).append((r["effect_scope"], r["value"]))
    effects = []
    for key, used in sorted(uses.items()):
        row, template = effect_rows.get(key), texts.get(f"effects_description_{key}")
        if not row or not template or "(HIDDEN" in template or row["priority"] == 0:
            continue
        # the game's template with %+n / %n kept as the place of the value; picture tags out, replacements put in (effect_text does both)
        text = effect_text(template.replace("%+n", "\x01").replace("%n", "\x02"), 0)
        text = text.replace("\x01", "%+n").replace("\x02", "%n")
        if not re.search("[а-яА-Я]", text):
            continue
        values = sorted({round(v, 2) for _, v in used})
        effects.append({"key": key, "text": text, "icon": "ui/campaign ui/effect_bundles/" + row["icon"] if row.get("icon") else None,
                        "positive_good": bool(row["is_positive_value_good"]), "category": row["category"],
                        "scopes": sorted({s for s, _ in used}), "values": values[:12], "uses": len(used)})
    icons = sorted({e["icon"] for e in effects if e["icon"]})
    # army units
    lands = {r["key"]: r for r in stock["land_units"]}
    entities = {r["key"]: r for r in stock["battle_entities"]}
    weapons = {r["key"]: r for r in stock["missile_weapons"]}
    projectiles = {r["key"]: r for r in stock["projectiles"]}
    variant_card = {r["unit"]: r["unit_card"] for r in stock["unit_variants"]}
    group_icons = unit_group_icons()
    armour = armour_values()
    units, pictures = [], []
    for m in sorted(stock["main_units"], key=lambda r: r["unit"]):
        key = m["unit"]
        if not key.startswith(DWARF_UNITS) or m["caste"] in ("hero", "lord") or m["is_renown"] or m["recruitment_cost"] <= 0:
            continue
        if re.search(r"_summoned|_mp$|thunderbarge|_ror$", key) or key not in variant_card or m["land_unit"] not in lands:
            continue
        lu = lands[m["land_unit"]]
        entity = entities.get(lu["man_entity"], {})
        # the missile weapon: the unit's own, or the war machine's (its engine has it; battlefield_engines is not read: the weapon named as the engine)
        weapon_key = lu["primary_missile_weapon"] or (lu["engine"] and lu["engine"].replace("_art_", "_", 1))
        weapon = weapons.get(weapon_key or "")
        p = projectiles.get(weapon["default_projectile"]) if weapon else None
        stats = {"men": m["num_men"], "engines": lu["num_engines"], "melee_attack": lu["melee_attack"], "melee_defence": lu["melee_defence"],
                 "charge": lu["charge_bonus"], "leadership": lu["morale"], "speed": round(entity.get("run_speed", 0) * 10) if entity else None,
                 "armour": armour.get(lu["armour"]),
                 # the men's health; a war machine's or a mount's own health is in tables the page does not read
                 "health": (entity.get("hit_points", 0) + lu["bonus_hit_points"]) * m["num_men"] if entity and not lu["num_engines"] and not lu["mount"] else None}
        if p:
            stats.update(missile_damage=round(p["damage"]), missile_ap=round(p["ap_damage"]), range=round(p["effective_range"]),
                         reload=round(p["base_reload_time"], 1), ammo=lu["primary_ammo"], shots=p["projectile_number"])
        card = {"picture": f"ui/units/icons/{variant_card[key]}.png",
                "category": f"ui/common ui/unit_category_icons/{group_icons.get(m['ui_unit_group_land'], m['ui_unit_group_land'])}.png"}
        pictures += [card["picture"], card["category"]]
        units.append({"key": key, "name": names.get(f"land_units_onscreen_name_{m['land_unit']}", key), "caste": m["caste"], "group": m["ui_unit_group_land"],
                      "variant": "malakai" if key.endswith("_malakai") else "grudge" if "grudge_reward" in key else None,
                      "hire": m["recruitment_cost"], "upkeep": m["upkeep_cost"], "tier": m["tier"], "card": card, "stats": stats})
    got = game_files(sorted(set(icons + pictures + UNIT_STAT_ICONS)))
    for path, blob in got.items():
        target = OUT / "game" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    have = set(got)
    for e in effects:
        if e["icon"] and e["icon"] not in have:
            e["icon"] = None
    data = {"_about": "Made by tools/web_export.py, export_catalog: the game's effects of the dwarfs' buildings and the dwarfs' army units, for the constructor. Do not edit.",
            "game_effects": effects, "army_units": units, "stat_icons": sorted(p for p in UNIT_STAT_ICONS if p in have), "armour_read": bool(armour)}
    (OUT / "catalog.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print("catalog:", len(effects), "game effects,", len(units), "army units; pictures", len(got), "of", len(set(icons + pictures + UNIT_STAT_ICONS)))


def recolour_card_frames(got):
    """The game's frames of a unit card (unit_card_build_frame.png of the small card, red; unit_card_frame_plain.png of the army panel's card) in each
    colour of the crew groups (data/crew_options.json, card_frames), for the crew aboard: build/web/game/ui/skins/tww3_mtb/<name>_<colour>.png. Same size,
    same shape, every pixel's brightness kept; in the mod they would be files of the pack. Copies of game pictures: they stay in build/."""
    colours = {k: v[0] for k, v in crew_options.CONFIG["card_frames"].items() if not k.startswith("_")}
    target = OUT / "game" / "ui" / "skins" / "tww3_mtb"
    target.mkdir(parents=True, exist_ok=True)
    code = ("import sys, json\nfrom PIL import Image\nsrc = Image.open(sys.argv[1]).convert('RGBA')\ncolours = json.loads(sys.argv[3])\n"
            "px = list(src.getdata())\ntop = max(max(p[:3]) for p in px if p[3]) or 1\n"
            "for name, c in colours.items():\n"
            "    out = Image.new('RGBA', src.size)\n"
            "    out.putdata([tuple(min(255, round(v * max(p[:3]) / top)) for v in c) + (p[3],) for p in px])\n"
            "    out.save(sys.argv[2] + '_' + name + '.png')\n")
    for name in ("unit_card_build_frame", "unit_card_frame_plain"):
        path = f"ui/skins/default/{name}.png"
        if path not in got:
            continue
        source = OUT / "raw" / f"{name}.png"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(got[path])
        subprocess.run(["py", "-3.10", "-c", code, str(source), str(target / name), json.dumps(colours)], check=True)


def export_game_ui():
    got = game_files(GAME_UI)
    for path, blob in got.items():
        target = OUT / "game" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    recolour_card_frames(got)
    missing = sorted(set(GAME_UI) - set(got))
    print(f"game UI pictures: {len(got)}" + (f", not in the packs: {missing}" if missing else ""))
    (OUT / "game" / "index.json").write_text(json.dumps(sorted(got), indent=1), encoding="utf-8")
    if PORTRAIT in got:
        jobs = OUT / "raw" / "round_jobs.json"
        jobs.parent.mkdir(parents=True, exist_ok=True)
        jobs.write_text(json.dumps([[str(OUT / "game" / PORTRAIT), str(OUT / "game" / PORTRAIT_ROUND), "round", PORTRAIT_FACE]]), encoding="utf-8")
        (OUT / "game" / PORTRAIT_ROUND).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["py", "-3.10", str(REPO / "tools" / "web_textures.py"), str(jobs)], check=True)


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
    ap.add_argument("--overview", action="store_true", help="only build/web/overview.json and its icons")
    ap.add_argument("--catalog", action="store_true", help="only build/web/catalog.json (the constructor's game effects and army units) and its pictures")
    a = ap.parse_args()
    everything = not (a.data or a.models or a.ui or a.vendor or a.overview or a.catalog)
    if everything or a.data:
        export_data()
    if everything or a.overview:
        export_overview()
    if everything or a.catalog:
        export_catalog()
    if everything or a.ui:
        export_game_ui()
    if everything or a.vendor:
        export_vendor()
    if everything or a.models:
        export_models(a.stock)
    (OUT / "manifest.json").write_text(json.dumps({"three": THREE, "base": str(BASE.relative_to(REPO))}, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
