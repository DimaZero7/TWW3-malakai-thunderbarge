"""The crew options of the barge: data/crew_options.json -> rows, files and the Lua data of the mod. One option = one entry.

Called by tools/build.py. For every seat of a group and every option there is one battle_personalities row, as the stock barge
has; the unit stays one and src/tww3_mtb_crew.lua points its seats at these rows before a battle. The junction rows keep the stock
crew, so without memreader Plus the unit is the stock barge. Every option's weapon is a copy under our key, also for the stock crew:
src/tww3_mtb_ammo.lua changes a byte in it during a battle (docs/design/separate-ammo.md).
"""
import json
import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import cannon_meta  # noqa: E402
import crew_ui  # noqa: E402
import gamepack  # noqa: E402
import gun_models  # noqa: E402
import hull_parts  # noqa: E402

SEP = chr(92)
CONFIG = json.loads((REPO / "data" / "crew_options.json").read_text(encoding="utf-8"))
for _group in CONFIG["groups"].values():    # disabled: the data stays in the file, the game gets nothing of it
    _group["options"] = {k: o for k, o in _group["options"].items() if not o.get("disabled")}


def use_config(config):
    """The config this module builds from: data/crew_options.json by default; tools/build.py gives it the same with the building sections of the author's
    tree (tools/tree_port.py crew_config)."""
    global CONFIG
    for group in config["groups"].values():
        group["options"] = {k: o for k, o in group["options"].items() if not o.get("disabled")}
    CONFIG = config
EMPTY_ROW = "mtb_bp_empty"
HULL_TABLE = "zeppelin01_dlc25_thunderbarge_grungni"
HULL_VARIANT = "wh3_dlc25_dwf_mnt_veh_thunderbarge_grungni"
HULL_MOUNT = "wh3_dlc25_dwf_mnt_veh_thunderbarge_grungni"
OWN_HULL = "mtb_mnt_thunderbarge_grungni"
NO_HARPOON_MOUNT = "mtb_mnt_thunderbarge_no_harpoon"
TAG = re.compile(rb"([\x04-\x20])\x00([A-Z_]{4,32})")


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def one(rows, **kw):
    found = [r for r in rows if all(r[k] == v for k, v in kw.items())]
    if len(found) != 1:
        raise SystemExit(f"expected one row for {kw}, found {len(found)}")
    return dict(found[0])


def seats_of_config():
    return {seat for group in CONFIG["groups"].values() for seat in group["seats"]}


def stock_definition(variant_row):
    """The text of a stock variant's .variantmeshdefinition."""
    return hull_parts.game_file(f"variantmeshes/variantmeshdefinitions/{variant_row['variant_filename']}.variantmeshdefinition").decode("utf-8")


def with_detail(definition, model):
    """A definition with one more body part: a detail moved out of the hull into this seat's model."""
    end = definition.rindex("</VARIANT_MESH>")
    slot = f'\t<SLOT name="hull_detail" >\n\t\t<VARIANT_MESH model="{model}" />\n\t</SLOT>\n'
    return definition[:end] + slot + definition[end:]


def ammo_row(weapon, projectile):
    """One weapon row for src/tww3_mtb_ammo.lua. per_shot: objects in the game's projectile list for one unit of ammunition.
    A burst costs per object: Iron Drakes, 42 objects against 40 units (run cycle_ammo_main, clatter_drakes)."""
    return {"key": weapon["key"], "secondary": weapon["use_secondary_ammo_pool"], "per_shot": projectile["projectile_number"]}


def ammo_entry(opt, group_key, key, rows):
    if not opt.get("ammo"):
        raise SystemExit(f"{group_key} / {key}: a weapon without ammo in data/crew_options.json")
    return {"ammo": opt["ammo"], "rows": rows}


def boost_rows(group_key, key, opt, group, t, weapon_row, projectile, seat_rows, ammo):
    """The same option at each level of its group's boost (data/crew_options.json, boost): the numbers live in the projectile, so a bonus touches this group only.
    Rows: projectile, weapon, stats, one seat row each. Returns {seat: {level: personality}}."""
    out = {}
    if not group.get("boost") or (opt.get("ui") or {}).get("hidden"):
        return out
    for level, step in enumerate(group["boost"]["steps"], 1):
        numbers = {k: (round(projectile[k] * v) if isinstance(projectile[k], int) else f32(projectile[k] * v)) for k, v in step.items()}
        new_projectile = dict(projectile, key=f"mtb_p_{key}_b{level}", **numbers)
        t["projectiles"].append(new_projectile)
        new_weapon = dict(weapon_row, key=f"mtb_w_{key}_b{level}", default_projectile=new_projectile["key"])
        t["missile_weapons"].append(new_weapon)
        ammo[group_key][key]["rows"].append(ammo_row(new_weapon, new_projectile))
        stats = f"mtb_s_{key}_b{level}"
        like_stats = next(r for r in t["battle_entity_stats"] if r["primary_missile_weapon"] == weapon_row["key"])
        t["battle_entity_stats"].append(dict(like_stats, key=stats, primary_missile_weapon=new_weapon["key"]))
        for seat, row in seat_rows.items():
            name = f"{row['key']}_b{level}"
            t["battle_personalities"].append(dict(row, key=name, battle_entity_stats=stats))
            out.setdefault(seat, {})[level] = name
    return out


def option_rows(group_key, key, opt, group, stock, t, stock_seat, details, ammo, own_stats):
    """Rows and definition files of one option. Returns {seat: personality}, {pack path: bytes}."""
    files = {}
    seat_details = group.get("seat_details", {})
    if opt.get("empty"):
        return {seat: EMPTY_ROW for seat in group["seats"]}, files
    if opt.get("rings_only"):   # the hull's detail on its seat, nobody in it
        like = one(stock["battle_personalities"], key=CONFIG["empty_like"])
        seat_details = group.get("seat_details", {})
        out = {}
        for seat in group["seats"]:
            out[seat] = f"mtb_bp_empty_{seat.removeprefix('ap_')}"
            row = dict(like, key=out[seat])
            if seat in seat_details:
                name = f"mtb_v_{group_key}_{key}_{seat.removeprefix('ap_')}"
                t["variants"].append(dict(one(stock["variants"], variant_name="dummy_variant"), variant_name=name, variant_filename=name))
                files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}{name}.variantmeshdefinition"] = (
                    f'<VARIANT_MESH><SLOT name="hull_detail"><VARIANT_MESH model="{details[seat_details[seat]]}" /></SLOT></VARIANT_MESH>').encode("utf-8")
                row["variant"] = name
            t["battle_personalities"].append(row)
        return out, files
    if opt.get("ability"):      # no seat of its own: src/tww3_mtb_crew.lua turns the ability on and off with an effect bundle
        return {}, files
    variant = opt.get("variant")
    if opt.get("vmd") or opt.get("variant_file"):
        variant = f"mtb_v_{key}"
        like = one(stock["variants"], variant_name=opt["variant_like"])
        t["variants"].append(dict(like, variant_name=variant, variant_filename=opt.get("variant_file", variant),
                                  scale=f32(opt.get("scale", like["scale"])), scale_variation=0.0))
    if opt.get("gun"):
        variant = f"mtb_v_{group_key}_{key}"
        like = one(stock["variants"], variant_name=opt["variant_like"])
        t["variants"].append(dict(like, variant_name=variant, variant_filename=variant))
    covers = opt.get("cover_by_side") or ({"left": opt["cover"], "right": opt["cover"]} if opt.get("cover") else {})
    if covers:
        # An empty seat with a cover: the hidden row's table, entity and no weapon (a seat with a firing table fires the unit's weapon, run p_hull).
        like = one(stock["battle_personalities"], key=CONFIG["empty_like"])
        out = {}
        for seat in group["seats"]:
            side = "left" if "left" in seat else "right"
            name = f"mtb_v_{group_key}_{key}_{side}"
            if not any(r["variant_name"] == name for r in t["variants"]):
                t["variants"].append(dict(one(stock["variants"], variant_name="dummy_variant"), variant_name=name, variant_filename=name))
                target = gun_models.build(covers[side])
                base = target.relative_to(gun_models.OUT).as_posix()
                for suffix in (".rigid_model_v2", ".wsmodel"):
                    files[(base + suffix).replace("/", SEP)] = target.with_suffix(suffix).read_bytes()
                files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}{name}.variantmeshdefinition"] = (
                    '<VARIANT_MESH><SLOT name="body"><VARIANT_MESH model="' + base + '.wsmodel" /></SLOT></VARIANT_MESH>').encode("utf-8")
            out[seat] = f"mtb_bp_{key}_{seat.removeprefix('ap_')}"
            t["battle_personalities"].append(dict(like, key=out[seat], variant=name))
        return out, files
    weapon = opt.get("weapon")
    stats = opt.get("stats")
    weapon_row = base_projectile = None
    # Every group's weapon is a row of our own, also for the stock crew: src/tww3_mtb_ammo.lua changes one byte of the row during a battle.
    if weapon:
        base_weapon = one(stock["missile_weapons"], key=weapon)
        base_projectile = one(stock["projectiles"], key=base_weapon["default_projectile"])
        projectile_key = base_projectile["key"]
        if "projectile" in opt:     # own copy of the projectile too, with some numbers changed
            numbers = {k: (f32(v) if isinstance(base_projectile[k], float) else v) for k, v in opt["projectile"].items()}
            base_projectile = dict(base_projectile, key=f"mtb_p_{key}", **numbers)
            t["projectiles"].append(base_projectile)
            projectile_key = base_projectile["key"]
        weapon = f"mtb_w_{key}"
        weapon_row = dict(base_weapon, key=weapon, default_projectile=projectile_key, **opt.get("weapon_fields", {}))
        t["missile_weapons"].append(weapon_row)
        stats = f"mtb_s_{key}"
        like = one(stock["battle_entity_stats"], key=opt["stats_like"])
        t["battle_entity_stats"].append(dict(like, key=stats, primary_missile_weapon=weapon))
        ammo[group_key][key] = ammo_entry(opt, group_key, key, [ammo_row(weapon_row, base_projectile)])
    elif not stats:
        seat_stats = {one(stock["battle_personalities"], key=stock_seat[seat])["battle_entity_stats"] for seat in group["seats"]}
        armed = [s for s in seat_stats if s and one(stock["battle_entity_stats"], key=s)["primary_missile_weapon"]]
        if armed:
            if len(seat_stats) != 1:
                raise SystemExit(f"{group_key} / {key}: seats with different weapons: {sorted(seat_stats)}")
            like = one(stock["battle_entity_stats"], key=armed[0])
            base_weapon = one(stock["missile_weapons"], key=like["primary_missile_weapon"])
            weapon, stats = f"mtb_w_{group_key}_{key}", f"mtb_s_{group_key}_{key}"
            weapon_row = dict(base_weapon, key=weapon)
            t["missile_weapons"].append(weapon_row)
            t["battle_entity_stats"].append(dict(like, key=stats, primary_missile_weapon=weapon))
            base_projectile = one(stock["projectiles"], key=base_weapon["default_projectile"])
            ammo[group_key][key] = ammo_entry(opt, group_key, key, [ammo_row(weapon_row, base_projectile)])
            if key == "stock":
                own_stats[armed[0]] = (group_key, key, stats)
    volley = gun_models.SPEC[opt["gun"]].get("volley") if opt.get("gun") else None
    out = {}
    seat_rows = {}
    for seat in group["seats"]:
        base = one(stock["battle_personalities"], key=stock_seat[seat])
        personality = f"mtb_bp_{key}_{seat.removeprefix('ap_')}"
        # autonomous_rider_hero is off on every seat: in a campaign battle a hero seat of a character's unit shows the character's own
        # model on its skeleton (Malakai's clones along the rail, shards at the cannon ports and bomb doors). The stock row is left alone.
        row = dict(base, key=personality, man_animations_table=opt.get("table", base["man_animations_table"]), autonomous_rider_hero=False)
        if volley:
            row["man_animations_table"] = cannon_meta.table_name(volley["tag"], "left" if seat.endswith("left") else "right")
        if variant:
            row["variant"] = variant
        if stats:
            row["battle_entity_stats"] = stats
        if seat in seat_details:
            # This seat also carries a detail of the hull: the option's definition plus that model.
            own = next((r for r in t["variants"] if r["variant_name"] == row["variant"]), None)
            row_variant = own or one(stock["variants"], variant_name=row["variant"])
            if opt.get("vmd"):
                text = (REPO / "data" / "vmd" / opt["vmd"]).read_text(encoding="utf-8")
            else:
                text = stock_definition(row_variant)
            detail_variant = f"mtb_v_{group_key}_{key}_{seat.removeprefix('ap_')}"
            # No far model of its own: at a distance a far model is shown instead of the whole definition, without the detail.
            t["variants"].append(dict(row_variant, variant_name=detail_variant, variant_filename=detail_variant,
                                      low_poly_filename=None, super_low_poly_filename=None))
            files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}{detail_variant}.variantmeshdefinition"] = with_detail(
                text, details[seat_details[seat]]).encode("utf-8")
            row["variant"] = detail_variant
        t["battle_personalities"].append(row)
        out[seat] = personality
        seat_rows[seat] = row
    if weapon_row is not None:
        for seat, levels in boost_rows(group_key, key, opt, group, t, weapon_row, base_projectile, seat_rows, ammo).items():
            for level, name in levels.items():
                out[f"{seat}@{level}"] = name
    if volley and not any(r["key"] == cannon_meta.table_name(volley["tag"], "left") for r in t.setdefault("battle_animations_table", [])):
        t["battle_animations_table"] += cannon_meta.rows(volley)
    return out, files


def option_files(group_key, key, opt):
    files = {}
    if opt.get("vmd"):
        files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}mtb_v_{key}.variantmeshdefinition"] = (
            REPO / "data" / "vmd" / opt["vmd"]).read_bytes()
    if opt.get("gun"):
        spec = gun_models.SPEC[opt["gun"]]
        target = gun_models.build(opt["gun"])
        base = target.relative_to(gun_models.OUT).as_posix()
        for suffix in (".rigid_model_v2", ".wsmodel"):
            files[(base + suffix).replace("/", SEP)] = target.with_suffix(suffix).read_bytes()
        files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}mtb_v_{group_key}_{key}.variantmeshdefinition"] = (
            '<VARIANT_MESH><SLOT name="body"><VARIANT_MESH model="' + base + '.wsmodel" /></SLOT></VARIANT_MESH>').encode("utf-8")
        if spec.get("volley"):
            files.update(cannon_meta.files(spec["volley"]))
    return files


def game_files(names):
    """{lower path with backslashes: bytes} from the animation packs; a later pack wins, as in the game."""
    wanted = {n.lower() for n in names}
    out = {}
    for pack in sorted(gamepack.DATA.glob("*.pack")):
        if not pack.name.startswith(("anim", "data")) or pack.name.endswith("_dds.pack"):
            continue
        for name, blob in gamepack.entries(pack, lambda n: n.lower() in wanted):
            out[name.lower()] = blob
    return out


def without_figures(meta):
    """An .anm.meta without its ANIMATED_PROP entries that show a person. Returns the new bytes, or None if nothing changes."""
    version, count = struct.unpack_from("<II", meta, 0)
    starts = []
    pos = 8
    while True:
        m = TAG.search(meta, pos)
        if not m:
            break
        if m.group(1)[0] == len(m.group(2)):
            starts.append(m.start())
            pos = m.end()
        else:
            pos = m.start() + 1
    if len(starts) != count or (starts and starts[0] != 8):
        raise SystemExit(f"unexpected .anm.meta: {count} entries, found {len(starts)}")
    entries = [meta[a:b] for a, b in zip(starts, starts[1:] + [len(meta)])]
    kept = [e for e in entries if not (e[2:15] == b"ANIMATED_PROP" and b"wh_variantmodels" in e.lower())]
    if len(kept) == len(entries):
        return None
    return struct.pack("<II", version, len(kept)) + b"".join(kept)


def hull_files():
    """The Spirit of Grungni's animation table with the people of its metadata taken out (the figure standing at the bow).

    The people are ANIMATED_PROP entries of the hull's .anm.meta files. Some of those files are shared with the ordinary Thunderbarge,
    so they are copied under new names and the table's .bin is replaced under its own name, pointing at the copies. Every name keeps
    its length, so the .bin only needs bytes replaced. The figure goes from every Spirit of Grungni, the summoned one too, and stays
    on the ordinary Thunderbarge. A copy of the table under a new name does not work: the attachment points turn 90 degrees and the
    crew hangs in the air (run 20261103-005545). Returns {pack path: bytes}."""
    bin_name = f"animations{SEP}database{SEP}battle{SEP}bin{SEP}{HULL_TABLE}.bin"
    table = game_files([bin_name])[bin_name.lower()]
    paths = sorted({m.decode() for m in re.findall(rb"animations/[A-Za-z0-9_/.\-]+?\.anm\.meta", table)})
    metas = game_files([p.replace("/", SEP) for p in paths])
    files = {}
    for path in paths:
        blob = metas.get(path.replace("/", SEP).lower())
        new = without_figures(blob) if blob else None
        if new is None:
            continue
        folder, _, name = path.rpartition("/")
        if not name.startswith("zeppelin01_"):
            raise SystemExit(f"cannot rename {path} with its length kept")
        renamed = folder + "/" + "mtb_zep_01_" + name.removeprefix("zeppelin01_")
        table = table.replace(path.encode(), renamed.encode())
        files[renamed.replace("/", SEP)] = new
    if not files:
        raise SystemExit("no figure found in the hull's metadata: the game changed")
    files[bin_name] = table
    return files


def hull_without_harpoon(table):
    """A copy of the hull's animation table with the harpoon out of its metadata. The harpoon is an ANIMATED_PROP of the table's persistent metadata and of
    some animations, not part of the hull. Same-length new names, as tools/cannon_meta.py: a new table through the .animpack is what the game takes.
    Returns {pack path: bytes}."""
    stock = cannon_meta.game_file(cannon_meta.BIN.format(HULL_TABLE))
    bin_bytes = stock.replace(HULL_TABLE.encode(), table.encode(), 1)
    paths = sorted({m.decode() for m in re.findall(rb"animations/[A-Za-z0-9_/.\-]+?\.anm\.meta", stock)})
    files = {}
    for path in paths:
        try:
            meta = cannon_meta.game_file(path)
        except SystemExit:
            continue
        if b"dwf_thunderbarge_harpoon" not in meta:
            continue
        version, entries = cannon_meta.split(meta)
        kept = [e for e in entries if not (cannon_meta.name_of(e) == b"ANIMATED_PROP" and b"dwf_thunderbarge_harpoon" in e)]
        folder, _, name = path.rpartition("/")
        if not name.startswith("zeppelin01_"):
            raise SystemExit(f"cannot rename {path} with its length kept")
        renamed = folder + "/" + "mtb_zep_nh_" + name.removeprefix("zeppelin01_")
        bin_bytes = bin_bytes.replace(path.encode(), renamed.encode())
        files[renamed.replace("/", SEP)] = struct.pack("<II", version, len(kept)) + b"".join(kept)
    if not files:
        raise SystemExit("no harpoon found in the hull's metadata: the game changed")
    files[cannon_meta.BIN.format(table).replace("/", SEP)] = bin_bytes
    return files


def to_lua(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)      # Lua has no \\u escapes
    if isinstance(v, list):
        return "{" + ", ".join(to_lua(x) for x in v) + "}"
    return "{" + ", ".join(f"[{json.dumps(k, ensure_ascii=False)}] = {to_lua(x)}" for k, x in sorted(v.items())) + "}"


def weapon_upgrades(t, stock, unit, ammo, own_stats):
    """The barge's upgrades (flaming cannon shells, fire bombs) swap the weapon of a stats row in unit_missile_weapon_junctions.
    The stock crew has stats rows of its own now, so these rows follow them, with weapon rows of their own too."""
    for row in t["unit_missile_weapon_junctions"]:
        if row["unit"] != unit:
            continue
        if row["battle_entity_stats_override"] not in own_stats:
            raise SystemExit(f"a weapon upgrade of unknown stats: {row}")
        group_key, key, stats = own_stats[row["battle_entity_stats_override"]]
        base_weapon = one(stock["missile_weapons"], key=row["missile_weapon"])
        weapon = dict(base_weapon, key=f"mtb_w_{group_key}_{key}_upgrade")
        t["missile_weapons"].append(weapon)
        projectile = one(stock["projectiles"], key=base_weapon["default_projectile"])
        ammo[group_key][key]["rows"].append(ammo_row(weapon, projectile))
        row["missile_weapon"], row["battle_entity_stats_override"] = weapon["key"], stats


def ammo_module(t, stock, unit, barge, ammo):
    """The battle module with its data."""
    land_unit = one(stock["land_units"], key=barge)
    data = {"land_unit": unit, "seat_count": 29, "primary_base": land_unit["primary_ammo"] * 29, "ammo_mod_key": "mtb_crew_ammo_mod",
            "checks": [["wh3_dlc25_dwf_thunderbarge_grudge_raker_grungni", True], ["wh3_dlc25_dwf_thunderbarge_cannon", False]],
            "seat_group": {seat: key for key, group in CONFIG["groups"].items() for seat in group["seats"] if ammo[key]},
            "groups": {key: {"options": options} for key, options in ammo.items() if options}}
    source = (REPO / "src" / "tww3_mtb_ammo.lua").read_text(encoding="utf-8")
    marker = "local CONFIG = {} --@CONFIG@"
    if marker not in source:
        raise SystemExit("config marker not in src/tww3_mtb_ammo.lua")
    return source.replace(marker, f"local CONFIG = {to_lua(data)}").encode("utf-8")


def building_bindings(t, stock):
    """data/crew_options.json "buildings" for the Lua module: full key -> [{group, option}]. A building may open several options. levels: chain and level of every level of the
    chains that the module follows, so it can tell that a bound building counts as standing when a higher level of its chain replaced it."""
    prefix = CONFIG["buildings_prefix"]
    rows = {r["level_name"]: r for r in stock["building_levels"]} | {r["level_name"]: r for r in t["building_levels"]}
    bindings = {}
    for short, pairs in CONFIG["buildings"].items():
        key = prefix + short
        if key not in rows:
            raise SystemExit(f"crew_options.json: no building {key}")
        for group, option in pairs:
            if option not in CONFIG["groups"].get(group, {}).get("options", {}):
                raise SystemExit(f"crew_options.json: {short}: no option {group} / {option}")
        bindings[key] = [{"group": group, "option": option} for group, option in pairs]
    followed = set(bindings) | {prefix + s for s in CONFIG["ammo_mod"]}
    # the building that makes the barge (src/tww3_mtb_crew.lua, has_barge) is followed even when it unlocks no crew option
    followed.add(prefix + CONFIG["auto_active"][0])
    for group in CONFIG["groups"].values():
        followed |= {prefix + s for s in group.get("boost", {}).get("buildings", [])}
        if group.get("requires"):
            followed.add(prefix + group["requires"]["building"])
    chains = {rows[key]["chain"] for key in followed}
    levels = {key: {"chain": r["chain"], "level": r["level"]} for key, r in rows.items() if r["chain"] in chains and r["visible_in_ui"]}
    return bindings, levels, sorted(followed)


def extend(t, stock, unit, barge, table_name_check=True):
    """Adds the rows of all options to the tables t. Returns {pack path: bytes}, with the Lua module."""
    stock_seat = {r["riders_attachment_point"]: r["battle_personality"]
                  for r in stock["land_units_to_battle_personalities_junctions"] if r["land_unit"] == barge}
    fixed = set(CONFIG["fixed_seats"])
    if set(stock_seat) != seats_of_config() | fixed or len(stock_seat) != 29:
        raise SystemExit(f"crew groups differ from the barge's seats: {set(stock_seat) ^ (seats_of_config() | fixed)}")
    for table in ("variants", "battle_personalities", "battle_entity_stats", "missile_weapons", "projectiles", "battle_animations_table", "mounts"):
        t.setdefault(table, [])
    files, details = {}, {}
    if CONFIG.get("own_hull"):
        files, details = hull_parts.build()
        like_variant = one(stock["variants"], variant_name=HULL_VARIANT)
        like_mount = one(stock["mounts"], key=HULL_MOUNT)
        t["variants"].append(dict(like_variant, variant_name=OWN_HULL, variant_filename=OWN_HULL))
        t["mounts"].append(dict(like_mount, key=OWN_HULL, variant=OWN_HULL))
        for row in t["land_units"]:
            if row["key"] == unit:
                row["mount"] = OWN_HULL
        files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}{OWN_HULL}.variantmeshdefinition"] = hull_parts.variant_definition(hull_parts.SPEC["out"] + ".wsmodel", [details["port"]])
        # The same hull without the harpoon on it: src/tww3_mtb_crew.lua points the land unit at this mount while the harpoon is not chosen.
        table = HULL_TABLE.replace("zeppelin01", "zepnoharp1")
        files.update(hull_without_harpoon(table))
        t["battle_animations_table"].append({"key": table, "skeleton": "zeppelin01"})
        t["mounts"].append(dict(like_mount, key=NO_HARPOON_MOUNT, variant=OWN_HULL, animation=table))
        # The hull's look is one mount row per combination: harpoon or not, patch over the ports, patch over the bomb niches. See write_mounts of src/tww3_mtb_crew.lua.
        hull_mounts = {"h": OWN_HULL, "n": NO_HARPOON_MOUNT}
        # The port is cut out of the hull: a hull with guns has it as a slot, without them a plug fills the hole.
        for code, models in (("c", ["patch_port"]), ("b", ["port", "patch_bombs"]), ("cb", ["patch_port", "patch_bombs"])):
            name = f"{OWN_HULL}_{code}"
            t["variants"].append(dict(like_variant, variant_name=name, variant_filename=name))
            files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}{name}.variantmeshdefinition"] = hull_parts.variant_definition(hull_parts.SPEC["out"] + ".wsmodel", [details[m] for m in models])
            t["mounts"].append(dict(like_mount, key=name, variant=name))
            t["mounts"].append(dict(like_mount, key=f"{NO_HARPOON_MOUNT}_{code}", variant=name, animation=table))
            hull_mounts["h" + code], hull_mounts["n" + code] = name, f"{NO_HARPOON_MOUNT}_{code}"
    like_empty = one(stock["battle_personalities"], key=CONFIG["empty_like"])
    t["battle_personalities"].append(dict(like_empty, key=EMPTY_ROW))
    seats = {}
    ammo, own_stats = {}, {}
    bindings, levels, followed = building_bindings(t, stock)
    prefix = CONFIG["buildings_prefix"]
    data = {"land_unit": unit, "seat_count": len(stock_seat), "groups": {}, "seats": seats, "fixed": {s: stock_seat[s] for s in fixed},
            "hull_mounts": hull_mounts, "upkeep": {g: {k: crew_ui.upkeep(o, stock) for k, o in spec["options"].items()} for g, spec in CONFIG["groups"].items()},
            "hire": {g: {k: crew_ui.hire(o, stock) for k, o in spec["options"].items()} for g, spec in CONFIG["groups"].items()},
            "buildings": bindings, "levels": levels, "followed": {key: True for key in followed}, "ammo_mod": {prefix + s: v for s, v in CONFIG["ammo_mod"].items()}, "auto_active": {prefix + short: True for short in CONFIG["auto_active"]}, "panel_building": prefix + CONFIG["auto_active"][0]}
    for group_key, group in CONFIG["groups"].items():
        data["groups"][group_key] = {"start": group["start"], "start_ai": group["start_ai"], "options": sorted(group["options"]), "seats": group["seats"]}
        for field in ("always", "off_bundle", "mount", "no_panel"):
            if group.get(field):
                data["groups"][group_key][field] = group[field]
        if group.get("boost"):
            data["groups"][group_key]["boost"] = [prefix + s for s in group["boost"]["buildings"]]
        if group.get("requires"):
            data["groups"][group_key]["requires"] = prefix + group["requires"]["building"]
        ammo[group_key] = {}
        for key, opt in group["options"].items():
            rows_of_option, definition_files = option_rows(group_key, key, opt, group, stock, t, stock_seat, details, ammo, own_stats)
            for seat, personality in rows_of_option.items():
                seat, _, level = seat.partition("@")
                seats.setdefault(seat, {})[f"{key}@{level}" if level else key] = personality
            files.update(definition_files)
            files.update(option_files(group_key, key, opt))
    weapon_upgrades(t, stock, unit, ammo, own_stats)
    if CONFIG.get("remove_bow_figure"):
        files.update(hull_files())
    # The tables hold the stock crew: without memreader Plus, or before the module has written, the unit is the stock barge.
    for row in t["land_units_to_battle_personalities_junctions"]:
        if row["land_unit"] == unit:
            for group in CONFIG["groups"].values():
                seat = row["riders_attachment_point"]
                if seat in group["seats"]:
                    row["battle_personality"] = seats[seat][group["start_ai"]]
    files.update(cannon_meta.animpack(files))
    known = {r["key"] for r in stock["battle_personalities"]} | {r["key"] for r in t["battle_personalities"]}
    for seat, options in seats.items():
        for key, personality in options.items():
            if personality not in known:
                raise SystemExit(f"{seat} / {key}: no row {personality}")
    source = (REPO / "src" / "tww3_mtb_crew.lua").read_text(encoding="utf-8")
    marker = "local CONFIG = {} --@CONFIG@"
    if marker not in source:
        raise SystemExit("config marker not in src/tww3_mtb_crew.lua")
    files[f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew.lua"] = source.replace(marker, f"local CONFIG = {to_lua(data)}").encode("utf-8")
    panel = (REPO / "src" / "tww3_mtb_crew_ui.lua").read_text(encoding="utf-8")
    panel_marker = "local DATA = {} --@CONFIG@"
    if panel_marker not in panel:
        raise SystemExit("config marker not in src/tww3_mtb_crew_ui.lua")
    files[f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew_ui.lua"] = panel.replace(panel_marker, f"local DATA = {to_lua(crew_ui.data(CONFIG, t, stock, bindings))}").encode("utf-8")
    files.update(crew_ui.files())
    files["__building_text__"] = json.dumps(crew_ui.building_lines(CONFIG, t, stock, bindings), ensure_ascii=False).encode("utf-8")
    files[f"script{SEP}battle{SEP}mod{SEP}tww3_mtb_ammo.lua"] = ammo_module(t, stock, unit, barge, ammo)
    return files
