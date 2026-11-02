"""Regenerates the mod from clean: py -3.14 tools/build.py [--pattern rider|barge]

Reads the stock rows from the game's db.pack, derives the new unit's rows (new keys only), writes
table fragments named !tww3_mtb (sorted before the game's data__), a .loc, the variant file, the
battle XML and the probe into build/v1/tww3_mtb_v1.pack, then reads the pack back and checks it.
Touches nothing outside build/v1 (no game folder).
"""
import argparse
import hashlib
import json
import shutil
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import dbtable  # noqa: E402
import gamepack  # noqa: E402
import pfh5  # noqa: E402

OUT = REPO / "build" / "v1"
DATA = REPO / "data"
TABLE_NAME = "!tww3_mtb"
PACK = "tww3_mtb_v1.pack"
SCENARIO = "script/battle/tww3_mtb/tww3_mtb_v1.xml"

UNIT = "mtb_dwf_cha_malakai_thunderbarge"
CAPTAIN = "mtb_dwf_veh_thunderbarge_grungni_malakai_captain"
VARIANT = "mtb_dwf_malakai_captain"
CARD = "mtb_dwf_cha_malakai_card"
# The unit panel's porthole: a copy of the barge's stock scene with Malakai's model, the captain's pose and a near camera.
PORTHOLE_SCENE = "composite_scene\\porthole\\mtb_malakai_porthole_01.csc"
PORTHOLE_SOURCE = "composite_scene\\porthole\\wm_zeppelin_grungni_porthole_01.csc"
# Vanilla Malakai art, copied into the pack at build time, unchanged: card as 60x130 unit icon.
CARD_SOURCE = ("ui2.pack", "ui\\portraits\\units\\no_culture\\dwf_malakai_makaisson_0.png")

BARGE = "wh3_dlc25_dwf_veh_thunderbarge_grungni"
MALAKAI = "wh3_dlc25_dwf_cha_malakai_makaisson"
CAPTAIN_STOCK = "wh3_dlc25_dwf_veh_thunderbarge_grungni_captain"
CAPTAIN_VARIANT_STOCK = "wh3_dlc25_dwf_veh_thunderbarge_grungni_crew_captain"
CAPTAIN_ANIM = "hu3_dlc25_zeppelin01_crew_captain"
MALAKAI_ENTITY = "wh3_dlc25_dwf_cha_malakai_makaisson_blood"
TIMER_PREFIX = "wh3_dlc25_unit_passive_unbinding_spirit_of_grungni"
SET_NEVER = "dwf_spirit_of_grungni_summon"
# Malakai's unit sets that describe the character (effects and ability sets for him).
MALAKAI_SETS = {"dwf_malakai_only", "legendary_lord", "dwf_all_units_characters", "dwf_slayers_and_ungrim"}

LAYOUTS = json.loads((DATA / "db_layouts.json").read_text(encoding="utf-8"))


def game_tables():
    """{table: rows} of the tables we copy from, read from db.pack with raw floats."""
    wanted = set(LAYOUTS)
    out = {}
    sep = chr(92)
    for name, blob in gamepack.entries(gamepack.DATA / "db.pack",
                                       lambda n: n.count(sep) == 2 and n.split(sep)[1].removesuffix("_tables") in wanted):
        table = name.split(sep)[1].removesuffix("_tables")
        version = dbtable.header(blob)[1]
        if version != LAYOUTS[table]["version"]:
            raise SystemExit(f"{table}: the game has version {version}, data/db_layouts.json has "
                             f"{LAYOUTS[table]['version']}: the game was patched, refresh the layouts")
        out[table] = dbtable.decode(blob, [tuple(f) for f in LAYOUTS[table]["fields"]])
    return out


def one(rows, **kw):
    found = [r for r in rows if all(r[k] == v for k, v in kw.items())]
    if len(found) != 1:
        raise SystemExit(f"expected one row for {kw}, found {len(found)}")
    return dict(found[0])


def derive(g, pattern):
    """The new unit's rows per table. pattern 'rider': hero rider on the mount (Tehenhauin's way).
    pattern 'barge': man_entity and man_animation stay the barge's, as on the stock barge."""
    t = {}
    barge_lu = one(g["land_units"], key=BARGE)
    mal_lu = one(g["land_units"], key=MALAKAI)

    lu = dict(barge_lu, key=UNIT, attribute_group=UNIT, **{"class": "com"})
    if pattern == "rider":
        lu.update(man_animation=CAPTAIN_ANIM, man_entity=MALAKAI_ENTITY)
    lu.update(historical_description_text=mal_lu["historical_description_text"],
              short_description_text=mal_lu["short_description_text"],
              capture_tier=mal_lu["capture_tier"], key_building_capture_tier=mal_lu["key_building_capture_tier"],
              score_capture_tier=mal_lu["score_capture_tier"], selection_vo=mal_lu["selection_vo"],
              selected_vo_secondary=mal_lu["selected_vo_secondary"], selected_vo_tertiary=mal_lu["selected_vo_tertiary"])
    t["land_units"] = [lu]

    barge_mu = one(g["main_units"], unit=BARGE)
    mal_mu = one(g["main_units"], unit=MALAKAI)
    mu = dict(barge_mu, unit=UNIT, land_unit=UNIT, caste="lord", create_time=mal_mu["create_time"],
              ui_unit_group_land=mal_mu["ui_unit_group_land"], tier=mal_mu["tier"],
              in_encyclopedia=False, multiplayer_cap=0, multiplayer_qb_cap=0,
              audio_voiceover_actor_group=mal_mu["audio_voiceover_actor_group"],
              porthole_camera=barge_mu["porthole_camera"], porthole_composite_scene=PORTHOLE_SCENE,
              is_renown=False, can_be_bribed=False,
              melee_cp=mal_mu["melee_cp"], missile_cp=barge_mu["missile_cp"])
    t["main_units"] = [mu]

    seats = []
    for row in g["land_units_to_battle_personalities_junctions"]:
        if row["land_unit"] == BARGE:
            row = dict(row, land_unit=UNIT)
            if row["battle_personality"] == CAPTAIN_STOCK:
                row["battle_personality"] = CAPTAIN
            seats.append(row)
    t["land_units_to_battle_personalities_junctions"] = seats
    if len(seats) != mu["num_men"]:
        raise SystemExit(f"{len(seats)} seats for {mu['num_men']} men")

    t["battle_personalities"] = [dict(one(g["battle_personalities"], key=CAPTAIN_STOCK), key=CAPTAIN, variant=VARIANT,
                                      man_animations_table=CAPTAIN_ANIM, battle_entity=MALAKAI_ENTITY,
                                      autonomous_rider_hero=True)]

    t["variants"] = [dict(one(g["variants"], variant_name=CAPTAIN_VARIANT_STOCK), variant_name=VARIANT,
                          variant_filename=VARIANT)]

    t["unit_variants"] = [dict(one(g["unit_variants"], unit=BARGE), name=UNIT, unit=UNIT, variant=VARIANT, unit_card=CARD)]

    abilities = []
    seen = set()
    for row in g["land_units_to_unit_abilites_junctions"]:
        if row["land_unit"] in (BARGE, MALAKAI) and not row["ability"].startswith(TIMER_PREFIX):
            if row["ability"] not in seen:
                seen.add(row["ability"])
                abilities.append(dict(row, land_unit=UNIT))
    t["land_units_to_unit_abilites_junctions"] = abilities

    t["unit_attributes_groups"] = [{"group_name": UNIT}]
    attrs = {r["attribute"] for r in g["unit_attributes_to_groups_junctions"] if r["attribute_group"] == BARGE}
    attrs |= {r["attribute"] for r in g["unit_attributes_to_groups_junctions"] if r["attribute_group"] == MALAKAI
              and r["attribute"] in ("unbreakable", "encourages")}
    t["unit_attributes_to_groups_junctions"] = [{"attribute": a, "attribute_group": UNIT} for a in sorted(attrs)]

    weapons = [r for r in g["unit_missile_weapon_junctions"] if r["unit"] == BARGE]
    t["unit_missile_weapon_junctions"] = [dict(r, unit=UNIT, id=1910000000 + i) for i, r in enumerate(weapons)]

    t["unit_banner_unit_height_offsets"] = [dict(one(g["unit_banner_unit_height_offsets"], unit_record=BARGE),
                                                 unit_record=UNIT)]

    sets = [r for r in g["unit_set_to_unit_junctions"] if r["unit_record"] == MALAKAI and r["unit_set"] in MALAKAI_SETS]
    sets += [r for r in g["unit_set_to_unit_junctions"] if r["unit_record"] == BARGE and r["exclude"]]
    t["unit_set_to_unit_junctions"] = [dict(r, unit_record=UNIT) for r in sets]
    if any(r["unit_set"] == SET_NEVER for r in t["unit_set_to_unit_junctions"]):
        raise SystemExit(f"{SET_NEVER} would bring the timer back")

    bullets = [r for r in g["ui_unit_bullet_point_unit_overrides"] if r["unit_key"] == BARGE]
    t["ui_unit_bullet_point_unit_overrides"] = [dict(r, unit_key=UNIT) for r in bullets]
    return t


def porthole_scene():
    """The barge's stock porthole scene with its strings and a few floats replaced. Strings: u16 length + ASCII,
    in a table at the end of the file. Floats: tag 0A + f32, at the offsets the stock file has them."""
    blob = bytearray(vanilla_file("data.pack", PORTHOLE_SOURCE))
    for offset, stock, new in [(108, -0.041, 0.0), (113, 13.45, 0.0),                # the model at the origin
                               (588, 9.704, 0.564), (604, 10.487, 0.95), (620, 56.569, 3.2),  # the camera, near (stock yaw is 10 deg: x = z * 0.176)
                               (955, -0.142, 0.0), (960, 10.126, -50.0), (988, 14.986, 100.0)]:  # second model: out of sight
        if blob[offset] != 0x0A or abs(struct.unpack_from("<f", blob, offset + 1)[0] - stock) > 0.01:
            raise SystemExit(f"{PORTHOLE_SOURCE}: no float {stock} at {offset}: the game changed the scene")
        struct.pack_into("<f", blob, offset + 1, new)
    blob = bytes(blob)
    model = b"variantmeshes\\wh_variantmodels\\hu3\\dwf\\dwf_malakai\\dwf_malakai_01.wsmodel"
    for old, new in [(b"animations\\battle\\zeppelin01\\stand\\zeppelin01_stand_01.anim",
                      b"animations\\battle\\humanoid03\\subset\\zeppelin_crew\\driver\\zeppelin01_back_crew_driver_stand_01.anim"),
                     (b"warmachines\\aircraft\\dwf_thunderbarge\\dwf_thunderbarge_grungni_01.wsmodel", model),
                     (b"warmachines\\aircraft\\dwf_thunderbarge\\harpoon\\dwf_thunderbarge_harpoon_01.wsmodel", model)]:
        tagged = struct.pack("<H", len(old)) + old
        if blob.count(tagged) != 1:
            raise SystemExit(f"{PORTHOLE_SOURCE}: string {old!r} not found once")
        blob = blob.replace(tagged, struct.pack("<H", len(new)) + new)
    return blob


def vanilla_file(pack_name, entry):
    """One file of the game's packs (any data pack: the name in CARD_SOURCE is only tried first)."""
    packs = [gamepack.DATA / pack_name] + sorted(gamepack.DATA.glob("ui*.pack")) + sorted(gamepack.DATA.glob("data*.pack"))
    for pack in packs:
        for name, blob in gamepack.entries(pack, lambda n: n.lower() == entry.lower()):
            return blob
    raise SystemExit(f"{entry} is not in the game's packs")


def loc_bytes(rows):
    """{key: text} -> a .loc file: FF FE 'LOC' 00, i32 version 1, u32 count, key, text, bool."""
    out = bytearray(b"\xff\xfeLOC\x00" + struct.pack("<iI", 1, len(rows)))
    for key, text in sorted(rows.items()):
        for s in (key, text):
            raw = s.encode("utf-16-le")
            out += struct.pack("<H", len(raw) // 2) + raw
        out += b"\x00"
    return bytes(out)


def probe_lua(config):
    def lua(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, str):
            return json.dumps(v)
        if isinstance(v, list):
            return "{" + ", ".join(lua(x) for x in v) + "}"
        return "{" + ", ".join(f"[{json.dumps(k)}] = {lua(x)}" for k, x in sorted(v.items())) + "}"
    source = (REPO / "src" / "tww3_mtb_probe.lua").read_text(encoding="utf-8")
    marker = "local CONFIG = {} --@CONFIG@"
    if marker not in source:
        raise SystemExit("config marker not in the probe")
    return source.replace(marker, f"local CONFIG = {lua(config)}").encode("utf-8")


def verify(blob, tables, stock):
    """Reads the pack back: every table by its layout; references must resolve to stock or our rows."""
    files, _ = pfh5.read_pack(blob)
    got = {}
    sep = chr(92)
    for table, rows in tables.items():
        name = f"db{sep}{table}_tables{sep}{TABLE_NAME}"
        fields = [tuple(f) for f in LAYOUTS[table]["fields"]]
        back = dbtable.decode(files[name], fields)
        if back != rows or dbtable.header(files[name])[1] != LAYOUTS[table]["version"]:
            raise SystemExit(f"{table}: read back differs")
        got[table] = back
    lu = got["land_units"][0]
    mu = got["main_units"][0]
    if lu["class"] != "com" or mu["caste"] != "lord":
        raise SystemExit("not a lord")
    if mu["num_men"] != len(got["land_units_to_battle_personalities_junctions"]) or mu["num_men"] != 29:
        raise SystemExit("seat count")
    points = [r["riders_attachment_point"] for r in got["land_units_to_battle_personalities_junctions"]]
    if len(set(points)) != 29 or "ap_captain" not in points:
        raise SystemExit("seats")
    if len({r["id"] for r in got["unit_missile_weapon_junctions"]}
           | {r["id"] for r in stock["unit_missile_weapon_junctions"]}) != (
            len(got["unit_missile_weapon_junctions"]) + len(stock["unit_missile_weapon_junctions"])):
        raise SystemExit("weapon junction id collides with a stock row")
    entities = {r["key"] for r in stock["battle_entities"]}
    mounts = {r["key"] for r in stock["mounts"]}
    variants = {r["variant_name"] for r in stock["variants"]} | {VARIANT}
    personalities = {r["key"] for r in stock["battle_personalities"]} | {CAPTAIN}
    for key, ok in [(lu["man_entity"], lu["man_entity"] in entities), (lu["mount"], lu["mount"] in mounts),
                    (got["battle_personalities"][0]["battle_entity"], got["battle_personalities"][0]["battle_entity"] in entities),
                    (got["unit_variants"][0]["variant"], got["unit_variants"][0]["variant"] in variants)]:
        if not ok:
            raise SystemExit(f"broken reference: {key}")
    for r in got["land_units_to_battle_personalities_junctions"]:
        if r["battle_personality"] not in personalities:
            raise SystemExit(f"broken reference: {r['battle_personality']}")
    if any(r["ability"].startswith(TIMER_PREFIX) for r in got["land_units_to_unit_abilites_junctions"]):
        raise SystemExit("timer ability in the unit")
    return {"seats": len(points), "abilities": [r["ability"] for r in got["land_units_to_unit_abilites_junctions"]],
            "unit_sets": [r["unit_set"] for r in got["unit_set_to_unit_junctions"]],
            "attributes": [r["attribute"] for r in got["unit_attributes_to_groups_junctions"]]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", choices=["rider", "barge"], default="rider")
    args = ap.parse_args(argv)

    if OUT.exists():
        for item in ("pack",):
            shutil.rmtree(OUT / item, ignore_errors=True)
    (OUT / "pack").mkdir(parents=True, exist_ok=True)

    stock = game_tables()
    tables = derive(stock, args.pattern)
    sep = chr(92)
    files = {}
    for table, rows in tables.items():
        layout = LAYOUTS[table]
        files[f"db{sep}{table}_tables{sep}{TABLE_NAME}"] = dbtable.encode(
            rows, [tuple(f) for f in layout["fields"]], layout["version"], table)
    files[f"text{sep}db{sep}tww3_mtb.loc"] = loc_bytes({
        f"land_units_onscreen_name_{UNIT}": "Malakai Makaisson, Spirit of Grungni",
    })
    files[f"variantmeshes{sep}variantmeshdefinitions{sep}{VARIANT}.variantmeshdefinition"] = (
        DATA / f"{VARIANT}.variantmeshdefinition").read_bytes()
    files[f"ui{sep}units{sep}icons{sep}{CARD}.png"] = vanilla_file(*CARD_SOURCE)
    files[PORTHOLE_SCENE] = porthole_scene()
    scenario = (DATA / "battle_v1.xml").read_text(encoding="utf-8").replace("@UNIT@", UNIT).encode("utf-8")
    files["script" + sep + "battle" + sep + "tww3_mtb" + sep + "tww3_mtb_v1.xml"] = scenario
    files["script" + sep + "battle" + sep + "tww3_mtb" + sep + "scenario.lua"] = b"load_script_libraries()\n"
    config = json.loads((DATA / "probe_config.json").read_text(encoding="utf-8"))
    lua = probe_lua(config)
    files["script" + sep + "battle" + sep + "mod" + sep + "tww3_mtb_probe.lua"] = lua

    blob = pfh5.pack_files(files)
    (OUT / "pack" / PACK).write_bytes(blob)
    (OUT / "pack" / "tww3_mtb_probe.lua").write_bytes(lua)
    summary = verify(blob, tables, stock)
    manifest = {"pack": PACK, "pack_sha256": hashlib.sha256(blob).hexdigest(), "scenario": SCENARIO,
                "unit": UNIT, "pattern": args.pattern, "entries": sorted(files), **summary}
    (OUT / "pack" / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("pack_sha256", "pattern", "seats", "abilities", "unit_sets", "attributes")}, indent=1))
    print(f"{len(files)} files, {len(blob)} bytes: {OUT / 'pack' / PACK}")


if __name__ == "__main__":
    main()
