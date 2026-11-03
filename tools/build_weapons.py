"""Test pack of the weapon options and the empty bays: py -3.14 tools/build_weapons.py --battle NAME

Reads data/weapon_variants.json. Each unit of a battle is a copy of the normal unit mtb_dwf_cha_malakai_thunderbarge with
some seat groups dropped or given an option's model, animation and weapon. One data entry per option; nothing of the
normal build changes: this writes only build/weapons/pack/tww3_mtb_weapons.pack, which is loaded instead of the v1 pack.
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import build as b1  # noqa: E402
import cannon_meta  # noqa: E402
import gun_models  # noqa: E402
import dbtable  # noqa: E402
import pfh5  # noqa: E402

OUT = REPO / "build" / "weapons"
PACK = "tww3_mtb_weapons.pack"
SCENARIO = "script/battle/tww3_mtb/tww3_mtb_weapons.xml"
SEP = chr(92)
SPEC = json.loads((REPO / "data" / "weapon_variants.json").read_text(encoding="utf-8"))
EXTRA_LAYOUTS = json.loads((REPO / "data" / "weapon_layouts.json").read_text(encoding="utf-8"))
LAYOUTS = dict(b1.LAYOUTS, **EXTRA_LAYOUTS)
ALL_SEATS = {seat for seats in SPEC["groups"].values() for seat in seats}


def f32(x):
    """A float as the table file will hold it, so a row reads back equal."""
    return struct.unpack("<f", struct.pack("<f", x))[0]


def game_rows(table):
    rows = []
    for _, blob in b1.gamepack.entries(b1.gamepack.DATA / "db.pack",
                                       lambda n: n.count(SEP) == 2 and n.split(SEP)[1] == f"{table}_tables"):
        rows += dbtable.decode(blob, [tuple(f) for f in LAYOUTS[table]["fields"]])
    return rows


def option_rows(key, opt, stock, t):
    """The rows of one seat option: a variant (own or stock), a weapon stats row, personalities. Returns seat -> personality."""
    variant = opt.get("variant")
    if opt.get("vmd") or opt.get("variant_file"):
        variant = f"mtb_v_{key}"
        like = b1.one(stock["variants"], variant_name=opt["variant_like"])
        t["variants"].append(dict(like, variant_name=variant, variant_filename=opt.get("variant_file", f"mtb_v_{key}"),
                                  scale=f32(opt.get("scale", like["scale"])), scale_variation=0.0))
    if opt.get("gun"):
        variant = f"mtb_v_{key}"
        like = b1.one(stock["variants"], variant_name=opt["variant_like"])
        t["variants"].append(dict(like, variant_name=variant, variant_filename=variant))
    weapon = opt.get("weapon")
    if "projectile" in opt:         # own copies of a weapon and its projectile, with some numbers changed
        change = opt["projectile"]
        base_weapon = next(r for r in stock["missile_weapons"] if r["key"] == weapon)
        base_projectile = next(r for r in stock["projectiles"] if r["key"] == base_weapon["default_projectile"])
        numbers = {k: (f32(v) if isinstance(base_projectile[k], float) else v) for k, v in change.items()}
        t["projectiles"].append(dict(base_projectile, key=f"mtb_p_{key}", **numbers))
        weapon = f"mtb_w_{key}"
        t["missile_weapons"].append(dict(base_weapon, key=weapon, default_projectile=f"mtb_p_{key}", **opt.get("weapon_fields", {})))
    stats = opt.get("stats")
    if weapon:
        stats = f"mtb_s_{key}"
        like = next(r for r in stock["battle_entity_stats"] if r["key"] == opt["stats_like"])
        t["battle_entity_stats"].append(dict(like, key=stats, primary_missile_weapon=weapon))
    seat_personality = {}
    for seat in SPEC["groups"][opt["group"]]:
        base = b1.one(stock["battle_personalities"], key=stock["_seat"][seat])
        table = opt.get("table", base["man_animations_table"])
        volley = gun_models.SPEC[opt["gun"]].get("volley") if opt.get("gun") else None
        if volley and opt.get("volley", True):
            table = cannon_meta.table_name(volley["tag"], "left" if seat.endswith("left") else "right")
        # One personality per seat, as the stock barge has: a shared one gives only one seat its model and weapon (battle rifles_a).
        personality = f"mtb_bp_{key}_{seat.removeprefix('ap_')}"
        row = dict(base, key=personality, man_animations_table=table)
        if variant:
            row["variant"] = variant
        if stats:
            row["battle_entity_stats"] = stats
        if opt.get("battle_entity"):
            row["battle_entity"] = opt["battle_entity"]
        if not any(r["key"] == personality for r in t["battle_personalities"]):
            t["battle_personalities"].append(row)
        seat_personality[seat] = personality
    return seat_personality


def test_unit(key, spec, v1, stock, t, built_options):
    """Rows of one test unit, a copy of the normal unit. spec: drop = groups without seats; use = options on their groups."""
    drop = {seat for g in spec.get("drop", []) for seat in SPEC["groups"][g]}
    swap = {}
    for option in spec.get("use", []):
        if option not in built_options:
            built_options[option] = option_rows(option, SPEC["options"][option], stock, t)
        swap.update(built_options[option])
    if spec.get("stock"):       # a stock unit of the game as it is, for comparison
        t["_men"][key] = spec["men"]
        return spec["stock"]
    land_unit = f"mtb_t_{key}"
    t["land_units"].append(dict(v1["land_units"][0], key=land_unit, **spec.get("land_unit_fields", {})))
    seats = []
    for row in v1["land_units_to_battle_personalities_junctions"]:
        seat = row["riders_attachment_point"]
        if seat not in drop:
            seats.append(dict(row, land_unit=land_unit, battle_personality=swap.get(seat, row["battle_personality"])))
    t["land_units_to_battle_personalities_junctions"] += seats
    t["main_units"].append(dict(v1["main_units"][0], unit=land_unit, land_unit=land_unit, num_men=len(seats)))
    t["unit_variants"].append(dict(v1["unit_variants"][0], name=land_unit, unit=land_unit, **spec.get("unit_variant_fields", {})))
    t["land_units_to_unit_abilites_junctions"] += [dict(r, land_unit=land_unit) for r in v1["land_units_to_unit_abilites_junctions"]]
    t["unit_banner_unit_height_offsets"].append(dict(v1["unit_banner_unit_height_offsets"][0], unit_record=land_unit))
    t["_men"][key] = len(seats)
    return land_unit


def battle_xml(battle, units, men):
    """Test units on a line facing +x; enemies per the battle's spec. tests_ai: the test army is under the game's AI."""
    spacing = battle.get("spacing", 60)
    x = battle.get("x", -60)
    lines = []
    keys = battle["units"]
    for i, key in enumerate(keys):
        z = (i - (len(keys) - 1) / 2) * spacing
        general = '<general><name>Malakai</name><star_rating level="1"/></general>' if i == 0 else ""
        lines.append(f'<unit num_soldiers="{men[key]}" script_name="t_{key}"><unit_type type="{units[key]}"/>'
                     f'<position x="{x}" y="{z}"/><orientation radians="{battle.get("orientation", 1.5708)}"/><width metres="45"/>'
                     f'<unit_experience level="0"/>{general}</unit>')
    tests = "\n".join(lines)
    lord_x = battle.get("enemy_lord_x", 500)
    enemy_lines = [f'<unit num_soldiers="1" script_name="enemy_lord"><unit_type type="wh_main_emp_cha_general_0"/>'
                   f'<position x="{lord_x}" y="0"/><orientation radians="4.7124"/><width metres="5"/>'
                   '<unit_experience level="0"/><general><name>enemy</name><star_rating level="1"/></general></unit>']
    for i, e in enumerate(battle.get("enemies", [])):
        enemy_lines.append(f'<unit num_soldiers="{e.get("men", 120)}" script_name="enemy_{i}">'
                           f'<unit_type type="{e.get("type", "wh_main_emp_inf_spearmen_0")}"/>'
                           f'<position x="{e["x"]}" y="{e["z"]}"/><orientation radians="4.7124"/><width metres="{e.get("width", 30)}"/>'
                           '<unit_experience level="0"/></unit>')
    enemies = "\n".join(enemy_lines)

    def army(faction, rows, side_x, radians):
        return (f'<army><faction>{faction}</faction><deployment_area><centre x="{side_x}" y="0.0"/><width metres="1000"/>'
                f'<height metres="1000"/><orientation radians="{radians}"/></deployment_area>'
                f'<camera_start_position x="{side_x}" y="700" z="-420"/><camera_target_position x="0" y="577" z="0"/>{rows}</army>')
    ours = army("wh_main_dwf_dwarfs", tests, -160.0, 1.5708)
    theirs = army("wh_main_emp_empire", enemies, 160.0, 4.7124)
    first, second = (theirs, ours) if battle.get("tests_ai") else (ours, theirs)
    win = "<victory_condition><kill_or_rout_enemy_ignore_reinforcements/></victory_condition>"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<battle>
  <alliance id="0">{first}{win}<rout_position x="-900" y="0"/></alliance>
  <alliance id="1">{second}{win}<rout_position x="900" y="0"/></alliance>
  <battle_description>
    <time_of_day>day</time_of_day><season>Spring</season><precipitation_type>dry</precipitation_type>
    <battle_script prepare_for_fade_in="false">script/battle/tww3_mtb/scenario.lua</battle_script>
    <type>classic</type><timeout_winning_alliance_index>1</timeout_winning_alliance_index><duration>3600</duration>
    <los_visibility_enabled>false</los_visibility_enabled>
  </battle_description>
  <weather><prevailing_wind x="1" y="0"/><environment_key>weather/battle/wh_day_desert_02.environment</environment_key></weather>
  <sea_surface_name>wind_level_0</sea_surface_name>
  <battle_map_definition><name>terrain\\battles\\mp_crossroads_flat\\</name><catchment_area>catchment_03</catchment_area></battle_map_definition>
</battle>
""".encode("utf-8")


def tour(battle):
    """Camera list: each camera set named in the battle is taken of each unit, or of the units named with the set."""
    out = []
    for item in battle["tour"]:
        cams = SPEC["cameras"][item["cameras"]]
        for key in item.get("units", battle["units"]):
            for cam in cams:
                shot = dict(cam, unit=f"t_{key}", name=f"{key}__{cam['name']}")
                for k in ("burst", "burst_ms", "speed", "settle_ms", "select"):
                    if k in item and k not in shot:
                        shot[k] = item[k]
                out.append(shot)
    return out


def to_lua(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "{" + ", ".join(to_lua(x) for x in v) + "}"
    return "{" + ", ".join(f"[{json.dumps(k)}] = {to_lua(x)}" for k, x in sorted(v.items())) + "}"


def probe(config):
    source = (REPO / "src" / "tww3_mtb_weapons_probe.lua").read_text(encoding="utf-8")
    marker = "local CONFIG = {} --@CONFIG@"
    if marker not in source:
        raise SystemExit("config marker not in the probe")
    return source.replace(marker, f"local CONFIG = {to_lua(config)}").encode("utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--battle", required=True)
    args = ap.parse_args(argv)
    battle = SPEC["battles"][args.battle]
    stock = b1.game_tables()
    for table in EXTRA_LAYOUTS:
        stock[table] = game_rows(table)
    v1 = b1.derive(stock, "rider")
    stock["_seat"] = {r["riders_attachment_point"]: r["battle_personality"]
                      for r in stock["land_units_to_battle_personalities_junctions"] if r["land_unit"] == b1.BARGE}
    if set(stock["_seat"]) != ALL_SEATS or len(ALL_SEATS) != 29:
        raise SystemExit(f"seat groups differ from the barge's seats: {set(stock['_seat']) ^ ALL_SEATS}")
    t = {k: list(v) for k, v in v1.items()}
    for table in EXTRA_LAYOUTS:
        t.setdefault(table, [])
    t["_men"] = {}
    units, built = {}, {}
    for key in battle["units"]:
        units[key] = test_unit(key, SPEC["units"][key], v1, stock, t, built)
    men = t.pop("_men")
    files = {}
    for table, rows in t.items():
        if rows:
            layout = LAYOUTS[table]
            files[f"db{SEP}{table}_tables{SEP}{b1.TABLE_NAME}"] = dbtable.encode(
                rows, [tuple(f) for f in layout["fields"]], layout["version"], table)
    files[f"text{SEP}db{SEP}tww3_mtb.loc"] = b1.loc_bytes(
        {f"land_units_onscreen_name_{b1.UNIT}": "Malakai Makaisson, Spirit of Grungni"}
        | {f"land_units_onscreen_name_{u}": "TEST " + k for k, u in units.items()})
    files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}{b1.VARIANT}.variantmeshdefinition"] = (
        b1.DATA / f"{b1.VARIANT}.variantmeshdefinition").read_bytes()
    for option in built:
        vmd = SPEC["options"][option].get("vmd")
        if vmd:
            files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}mtb_v_{option}.variantmeshdefinition"] = (
                REPO / "data" / "vmd" / vmd).read_bytes()
    for option in built:
        gun = SPEC["options"][option].get("gun")
        if gun:
            volley = gun_models.SPEC[gun].get("volley")
            if volley and SPEC["options"][option].get("volley", True):
                files.update(cannon_meta.files(volley))
                t["battle_animations_table"] += [r for r in cannon_meta.rows(volley) if r not in t["battle_animations_table"]]
            target = gun_models.build(gun)
            base = target.relative_to(gun_models.OUT).as_posix()
            for suffix in (".rigid_model_v2", ".wsmodel"):
                files[(base + suffix).replace("/", SEP)] = target.with_suffix(suffix).read_bytes()
            files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}mtb_v_{option}.variantmeshdefinition"] = (
                '<VARIANT_MESH><SLOT name="body"><VARIANT_MESH model="' + base + '.wsmodel" /></SLOT></VARIANT_MESH>').encode("utf-8")
    rows = t["battle_animations_table"]
    if rows:
        layout = LAYOUTS["battle_animations_table"]
        files[f"db{SEP}battle_animations_table_tables{SEP}{b1.TABLE_NAME}"] = dbtable.encode(
            rows, [tuple(f) for f in layout["fields"]], layout["version"], "battle_animations_table")
    files[f"ui{SEP}units{SEP}icons{SEP}{b1.CARD}.png"] = b1.vanilla_file(*b1.CARD_SOURCE)
    files[b1.PORTHOLE_SCENE] = b1.porthole_scene()
    files[f"script{SEP}battle{SEP}tww3_mtb{SEP}tww3_mtb_weapons.xml"] = battle_xml(battle, units, men)
    files[f"script{SEP}battle{SEP}tww3_mtb{SEP}scenario.lua"] = b"load_script_libraries()\n"
    config = {k: v for k, v in battle.items() if k not in ("units", "enemies", "tour", "spacing", "x", "tests_ai", "enemy_lord_x", "orientation")}
    config["tour"] = tour(battle)
    files[f"script{SEP}battle{SEP}mod{SEP}tww3_mtb_weapons_probe.lua"] = probe(config)
    files.update(cannon_meta.animpack(files))
    blob = pfh5.pack_files(files)
    # Read back: every table by its layout, every seat's personality known.
    read, _ = pfh5.read_pack(blob)
    for table, rows in t.items():
        if rows and dbtable.decode(read[f"db{SEP}{table}_tables{SEP}{b1.TABLE_NAME}"], [tuple(f) for f in LAYOUTS[table]["fields"]]) != rows:
            raise SystemExit(f"{table}: read back differs")
    known = {r["key"] for r in stock["battle_personalities"]} | {r["key"] for r in t["battle_personalities"]}
    for row in t["land_units_to_battle_personalities_junctions"]:
        if row["battle_personality"] not in known:
            raise SystemExit(f"broken reference: {row['battle_personality']}")
    (OUT / "pack").mkdir(parents=True, exist_ok=True)
    (OUT / "pack" / PACK).write_bytes(blob)
    manifest = {"pack": PACK, "pack_sha256": hashlib.sha256(blob).hexdigest(), "scenario": SCENARIO, "battle": args.battle,
                "units": units, "men": men, "shots": len(config["tour"])}
    (OUT / "pack" / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
