"""Regenerates the mod from clean: py -3.14 tools/build.py [--pattern rider|barge]

Reads the stock rows from the game's db.pack, derives the new unit's rows (new keys only), writes
table fragments named !tww3_mtb (sorted before the game's data__), a .loc, the variant file, the
battle XML and the probe into build/v1/tww3_mtb_v1.pack, then reads the pack back and checks it.
The campaign pack (build/campaign/pack/tww3_mtb_campaign.pack) carries the author's tree of buildings: tools/tree_port.py runs tools/tree_export.mjs over
web/data/tree_design.json with the switches of data/tree_port.json into build/tree/tree_rows.json, and its rows go into the tables as they are.
It also carries the airship screen's logic modules and their config (tools/ship_lua.py, tools/ship_config.mjs: build/tree/ship_config.json), inert.
Touches nothing outside build/ (no game folder).
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
import crew_buildings  # noqa: E402
import crew_options  # noqa: E402
import dbtable  # noqa: E402
import gamepack  # noqa: E402
import pfh5  # noqa: E402
import ship_lua  # noqa: E402
import tree_port  # noqa: E402

OUT = REPO / "build" / "v1"
DATA = REPO / "data"
TABLE_NAME = "!tww3_mtb"
PACK = "tww3_mtb_v1.pack"
HARNESS_PACK = "tww3_mtb_harness.pack"
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
LAYOUTS.update(json.loads((DATA / "weapon_layouts.json").read_text(encoding="utf-8")))   # the crew options' weapons


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


# ---------------- campaign pack: everything of v1 plus the mount item, the summon switched off, the barge's upgrades ----------
ANCILLARY = "mtb_anc_mount_dwf_malakai_thunderbarge"
ANCILLARY_LIKE = "wh2_dlc12_anc_mount_skv_ikit_claw_doomwheel"
UNIFORM = "mtb_uniform_dwf_malakai_thunderbarge"
UNIFORM_STOCK = "wh3_dlc25_uniform_dwf_malakai_makaisson"
ART_SET = "wh3_dlc25_art_set_dwf_malakai_makaisson"
SUBTYPE = "wh3_dlc25_dwf_malakai_makaisson"
UNIT_SET = "mtb_dwf_malakai_thunderbarge"
SUMMON_SET = "dwf_spirit_of_grungni_summon"
SUMMON_EFFECT = "wh3_dlc25_effect_army_ability_enable_spirit_of_grungni_summon_1"
HORDE_BUILDINGS = "wh3_dlc25_dwarf_spirit_of_grungni_"
HULL_CHAIN = "wh3_dlc25_dwf_spirit_of_grungni_main_chain"
CAMPAIGN_PACK = "tww3_mtb_campaign.pack"
HARPOON_ABILITY = "wh3_dlc25_unit_abilities_spear_of_grungni"
HARPOON_EFFECT = "mtb_effect_harpoon_off"
HARPOON_BUNDLE = "mtb_bundle_harpoon_off"
# The rows of the summon's set that are the barge's upgrades, not its timer.
UPGRADE_ROWS = {"thunderburner_dwf_spirit_of_grungni": "mtb_thunderburner", "thunderburner_upgraded_dwf_spirit_of_grungni": "mtb_thunderburner_upgraded",
                "awe_inspiring_sight_dwf_spirit_of_grungni": "mtb_awe_inspiring_sight"}


def derive_campaign(g, t, tree=None, config=None):
    """Adds the campaign's rows to the v1 rows t. New keys, except building_effects_junction, where the same keys override.
    tree: build/tree/tree_rows.json (tools/tree_port.export) and config: data/crew_options.json with the tree's building sections (tree_port.crew_config):
    the buildings are the author's tree. Without them: the old chains of data/crew_options.json (what tools/web_export.py shows the page as the mod)."""
    t["ancillaries"] = [dict(one(g["ancillaries"], key=ANCILLARY_LIKE), key=ANCILLARY, provided_bodyguard_unit=UNIT)]
    t["ancillaries_included_agent_subtypes"] = [{"agent_subtype": SUBTYPE, "ancillary": ANCILLARY}]
    # The map keeps Malakai's own model (filename) and animation; only the battle model (battle_filename) changes.
    t["agent_uniforms"] = [dict(one(g["agent_uniforms"], uniform_name=UNIFORM_STOCK), uniform_name=UNIFORM, battle_filename=VARIANT)]
    t["campaign_character_uniform_ancillary_junctions"] = [{"ancillary": ANCILLARY, "art_set": ART_SET, "uniform": UNIFORM}]
    t["campaign_map_attrition_unit_immunities"] = [dict(r, unit=UNIT) for r in g["campaign_map_attrition_unit_immunities"]
                                                   if r["unit"] == BARGE]

    # The barge's upgrades through our own unit set: never the summon's set, which carries the timer.
    t["unit_sets"] = [dict(one(g["unit_sets"], key=SUMMON_SET), key=UNIT_SET)]
    t["unit_set_to_unit_junctions"] = t["unit_set_to_unit_junctions"] + [
        dict(next(r for r in g["unit_set_to_unit_junctions"] if r["unit_record"] == BARGE and r["unit_set"] == SUMMON_SET),
             unit_record=UNIT, unit_set=UNIT_SET)]
    t["unit_set_unit_ability_junctions"] = [dict(one(g["unit_set_unit_ability_junctions"], key=old), key=new, unit_set=UNIT_SET)
                                            for old, new in UPGRADE_ROWS.items()]
    t["effect_bonus_value_unit_set_unit_ability_junctions"] = [
        dict(r, unit_set_ability=UPGRADE_ROWS[r["unit_set_ability"]])
        for r in g["effect_bonus_value_unit_set_unit_ability_junctions"] if r["unit_set_ability"] in UPGRADE_ROWS]
    t["effect_bonus_value_ids_unit_sets"] = [dict(r, unit_set=UNIT_SET) for r in g["effect_bonus_value_ids_unit_sets"]
                                             if r["unit_set"] == SUMMON_SET]
    stock_weapons = [r for r in g["unit_missile_weapon_junctions"] if r["unit"] == BARGE]
    new_id = {old["id"]: new["id"] for old, new in zip(stock_weapons, t["unit_missile_weapon_junctions"])}
    t["effect_bonus_value_missile_weapon_junctions"] = [
        dict(r, missile_weapon_junction=new_id[r["missile_weapon_junction"]])
        for r in g["effect_bonus_value_missile_weapon_junctions"] if r["missile_weapon_junction"] in new_id]

    # The harpoon: an effect that takes the stock ability away. The bundle holding it is applied by src/tww3_mtb_crew.lua while the harpoon group is off.
    # The way the game's own upgrade switches off the plain Thunderburner: effect, bonus "disable", a row of our unit set. Without the bundle: as stock.
    t["unit_set_unit_ability_junctions"].append({"key": "mtb_harpoon", "unit_ability": HARPOON_ABILITY, "unit_set": UNIT_SET})
    t["effects"] = [dict(one(g["effects"], effect="wh3_dlc25_effect_ability_enable_thunderburner_upgraded"), effect=HARPOON_EFFECT)]
    t["effect_bundles"] = [dict(next(r for r in g["effect_bundles"] if r["bundle_target"] == "force"), key=HARPOON_BUNDLE, localised_title="Гарпун снят",
                                localised_description="Стрела на носу шара снята: способности в бою нет. Поставить можно в панели экипажа.", ui_icon="general_ability.png")]
    t["effect_bundles_to_effects_junctions"] = [{"effect_bundle_key": HARPOON_BUNDLE, "effect_key": HARPOON_EFFECT, "effect_scope": "force_to_force_own", "value": 1.0, "advancement_stage": "start_turn_completed"}]
    t["effect_bonus_value_unit_set_unit_ability_junctions"].append({"bonus_value_id": "disable", "effect": HARPOON_EFFECT, "unit_set_ability": "mtb_harpoon"})

    # Tiers: the side buildings stand from airship_hull_2 on, each level on its own row of the tree, plus the new chains: tools/crew_buildings.py.
    t["building_levels"] = []
    # No second barge in ordinary battles: the buildings stop enabling the summon. Quest battles enable it by their own bundle.
    t["building_effects_junction"] = [dict(r, value=0.0, value_damaged=0.0, value_ruined=0.0)
                                      for r in g["building_effects_junction"] if r["effect"] == SUMMON_EFFECT]
    if tree is not None:
        t["__building_loc__"], t["__building_files__"] = crew_buildings.add_tree_rows(t, g, tree, config)
    else:
        t["__building_loc__"], t["__building_files__"] = crew_buildings.add_rows(t, g)
    return t


def build_campaign(blob_files, tables, stock):
    """build/campaign/pack/tww3_mtb_campaign.pack from the v1 files (without the test battle and its probe)."""
    sep = chr(92)
    out = REPO / "build" / "campaign" / "pack"
    out.mkdir(parents=True, exist_ok=True)
    # the author's tree: its rows (build/tree/tree_rows.json) and the crew config the current Lua reads by building, both from the tree
    tree = tree_port.export(stock)
    crew_options.use_config(tree_port.crew_config(crew_options.CONFIG, tree))
    tables = derive_campaign(stock, {k: [dict(r) for r in v] for k, v in tables.items()}, tree, crew_options.CONFIG)
    building_loc, building_files = tables.pop("__building_loc__"), tables.pop("__building_files__")
    files = {k: v for k, v in blob_files.items() if not k.startswith(f"script{sep}battle") and not k.startswith(f"db{sep}")}
    files.update(crew_options.extend(tables, stock, UNIT, BARGE))
    building_text = json.loads(files.pop("__building_text__")) | building_loc
    files.update(building_files)
    for table, rows in tables.items():
        layout = LAYOUTS[table]
        files[f"db{sep}{table}_tables{sep}{TABLE_NAME}"] = dbtable.encode(rows, [tuple(f) for f in layout["fields"]], layout["version"], table)
    files[f"text{sep}db{sep}tww3_mtb.loc"] = loc_bytes(json.loads((DATA / "campaign_text.json").read_text(encoding="utf-8")) | building_text | {
        f"land_units_onscreen_name_{UNIT}": "Malakai Makaisson, Spirit of Grungni"})
    files[f"script{sep}campaign{sep}mod{sep}tww3_mtb_campaign.lua"] = (REPO / "src" / "tww3_mtb_campaign.lua").read_bytes()
    # the airship screen's logic (src/tww3_mtb_ship.lua, src/tww3_mtb_crew_model.lua) and its config from the tree: packed outside script/campaign/mod,
    # so the game does not run them yet (tools/ship_lua.py); tools/lua_vectors.py replays the page's vectors on them
    files.update(ship_lua.files())
    blob = pfh5.pack_files(files)
    (out / CAMPAIGN_PACK).write_bytes(blob)
    # read back
    read, _ = pfh5.read_pack(blob)
    for table, rows in tables.items():
        back = dbtable.decode(read[f"db{sep}{table}_tables{sep}{TABLE_NAME}"], [tuple(f) for f in LAYOUTS[table]["fields"]])
        if back != rows:
            raise SystemExit(f"{table}: read back differs")
    if any(r["unit_set"] == SUMMON_SET for r in tables["unit_set_to_unit_junctions"]):
        raise SystemExit("the unit is in the summon's set: the timer would come back")
    if sum(r["effect"] == SUMMON_EFFECT for r in tables["building_effects_junction"]) != 6:
        raise SystemExit("expected 6 building rows of the summon")
    if any("unbinding" in r["unit_ability"] for r in tables["unit_set_unit_ability_junctions"]):
        raise SystemExit("a timer ability in our unit set")
    print("campaign tables:", {t: len(r) for t, r in tables.items()})
    return {"campaign": CAMPAIGN_PACK}


def build_harness(modes=("frontend", "campaign", "battle")):
    """build/campaign/pack/tww3_mtb_harness.pack: only the test remote, for frontend, campaign and battle."""
    sep = chr(92)
    out = REPO / "build" / "campaign" / "pack"
    out.mkdir(parents=True, exist_ok=True)
    remote = (REPO / "src" / "tww3_mtb_remote.lua").read_bytes()
    files = {f"script{sep}{m}{sep}mod{sep}tww3_mtb_remote.lua": remote for m in modes}
    blob = pfh5.pack_files(files)
    (out / HARNESS_PACK).write_bytes(blob)
    return {"harness": HARNESS_PACK}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", choices=["rider", "barge"], default="rider")
    ap.add_argument("--target", choices=["v1", "harness"], default="v1")
    ap.add_argument("--harness-modes", nargs="+", default=["frontend", "campaign", "battle"])
    args = ap.parse_args(argv)
    if args.target == "harness":
        packs = build_harness(tuple(args.harness_modes))
        out = REPO / "build" / "campaign" / "pack"
        (out / "manifest.json").write_text(json.dumps({"packs": packs}, indent=1), encoding="utf-8")
        print(packs)
        return

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
    camp_out = REPO / "build" / "campaign" / "pack"
    camp_packs = dict(build_harness(), **build_campaign(files, tables, stock))
    (camp_out / "manifest.json").write_text(json.dumps({"packs": camp_packs}, indent=1), encoding="utf-8")
    summary = verify(blob, tables, stock)
    manifest = {"pack": PACK, "pack_sha256": hashlib.sha256(blob).hexdigest(), "scenario": SCENARIO,
                "unit": UNIT, "pattern": args.pattern, "entries": sorted(files), **summary}
    (OUT / "pack" / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("pack_sha256", "pattern", "seats", "abilities", "unit_sets", "attributes")}, indent=1))
    print(f"{len(files)} files, {len(blob)} bytes: {OUT / 'pack' / PACK}")


if __name__ == "__main__":
    main()
