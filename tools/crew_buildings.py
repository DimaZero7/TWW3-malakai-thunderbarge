"""The barge's buildings: tiers and prices of stock levels, the chains this mod adds, the slots of the horde, abilities given by buildings. Called by tools/build.py.

add_tree_rows: the author's tree (web/data/tree_design.json) as build/tree/tree_rows.json gives it (tools/tree_export.mjs, data/tree_port.json): the build's way.
add_rows: the old chains of data/crew_options.json (new_chains, building_edits): what tools/web_export.py still shows the page as «the mod».
Everything of add_rows comes from data/crew_options.json. The tree of a slot draws a chain's level on the row of its hull requirement, so two levels of a chain on one row hide the lower one:
every level here stands on its own row. tier 1 is the hull's row I; the requirement field counts from 0. New rows are copies of a stock level of the same kind.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

SEP = chr(92)
CONFIG = json.loads((REPO / "data" / "crew_options.json").read_text(encoding="utf-8"))
ICONS = REPO / "data" / "ui" / "buildings"
PREFIX = CONFIG["buildings_prefix"]
FORCE = "MALAKAI_BOUND_HORDE"
SECONDARY_SET = "wh3_main_secondary_core_generic_horde"
CULTURE_SET = "wh_main_bas_dwf"
LIKE_LEVEL = PREFIX + "engines_2"
LIKE_CHAIN = "wh3_dlc25_dwf_spirit_of_grungni_engines"
ENABLE_LIKE = "wh3_dlc25_effect_ability_enable_thunderburner_upgraded"
SCOPE = "force_to_force_own"
BUILDING_LINE_SCOPE = "force_to_force_own"     # a line of text only (as tools/crew_ui.py writes the crew's lines)
FIRST_ABILITY_ID = 1910100000


def one(rows, **kw):
    found = [r for r in rows if all(r[k] == v for k, v in kw.items())]
    if len(found) != 1:
        raise SystemExit(f"expected one row for {kw}, found {len(found)}")
    return dict(found[0])


def icon_files():
    """{icon name: bytes} of data/ui/buildings: an icon of a level (crew_weapons_1.png) or of a whole chain (crew_weapons.png)."""
    if not ICONS.exists():
        return {}
    return {p.stem.removeprefix(PREFIX): p.read_bytes() for p in sorted(ICONS.glob("*.png")) if p.stem != "contact-sheet"}


def icon_of(short, drawn):
    """Our own icon's key for a level, or None: the stock one or the placeholder of the config stays."""
    chain, _, number = short.rpartition("_")
    drawn_chain = CONFIG.get("icon_names", {}).get(chain, chain)
    for name in (f"{drawn_chain}_{number}", short, chain):
        if name in drawn:
            return "tww3_mtb_" + name
    return None


def add_rows(t, g):
    """Adds to the tables t. Returns ({loc key: text}, {pack path: bytes})."""
    for table in ("building_levels", "building_chains", "building_instances", "building_superchains", "building_chain_set_items", "building_chain_availability_sets",
                  "building_set_to_building_junctions", "building_upgrades_junction", "building_culture_variants", "military_force_type_horde_details", "building_level_required_buildings",
                  "unit_abilities", "unit_special_abilities", "special_ability_phases", "special_ability_to_special_ability_phase_junctions", "special_ability_phase_stat_effects",
                  "special_ability_to_auto_deactivate_flags", "effects", "building_effects_junction", "unit_set_unit_ability_junctions", "effect_bonus_value_unit_set_unit_ability_junctions"):
        t.setdefault(table, [])
    loc, files = {}, {}
    drawn = icon_files()
    # the rows of stock levels with a tier or price of ours
    stock_levels = {r["level_name"]: r for r in g["building_levels"]}
    edited = {r["level_name"]: r for r in t["building_levels"]}
    for short, edit in CONFIG["building_edits"].items():
        if short.startswith("_"):
            continue
        key = PREFIX + short
        row = edited.get(key)
        if row is None:
            row = dict(stock_levels[key])
            t["building_levels"].append(row)
            edited[key] = row
        if "tier" in edit:
            row["primary_slot_building_building_level_requirement"] = edit["tier"] - 1
        if "cost" in edit:
            row["create_cost"] = edit["cost"]
        if "time" in edit:
            row["create_time"] = edit["time"]
    # more slots in the horde: one for each new chain
    t["military_force_type_horde_details"].append(dict(one(g["military_force_type_horde_details"], force_type=FORCE), slot_cap=CONFIG["slot_cap"]))
    # the new chains stand in the barge's own green category, with the others
    like_level, like_chain = stock_levels[LIKE_LEVEL], one(g["building_chains"], key=LIKE_CHAIN)
    variant_like = next(r for r in g["building_culture_variants"] if r["building"] == LIKE_LEVEL)
    for order, chain in enumerate(CONFIG["new_chains"]):
        chain_key, superchain, instance = chain["key"], f"mtb_sch_{chain['key']}", PREFIX + chain["key"]
        t["building_superchains"].append({"key": superchain})
        t["building_instances"].append({"key": instance, "num_instances": 1})
        t["building_chains"].append(dict(like_chain, key=chain_key, building_superchain=superchain, optional_sort_order=order))
        t["building_chain_set_items"].append({"chain": chain_key, "remove": False, "set": SECONDARY_SET, "super_chain": None})
        t["building_chain_availability_sets"].append({"building_chain": chain_key, "id": CULTURE_SET})
        t["building_set_to_building_junctions"].append({"building_chain": chain_key, "building_level": None, "building_set": CONFIG["building_set"]["key"], "exclude": False})
        previous = None
        for number, level in enumerate(chain["levels"]):
            key = PREFIX + level["key"]
            t["building_levels"].append(dict(like_level, level_name=key, chain=chain_key, level=number, create_time=level["time"], create_cost=level["cost"],
                                             building_instance_key=instance, development_point_cost=level["dev"],
                                             primary_slot_building_building_level_requirement=level["tier"] - 1))
            icon = icon_of(level["key"], drawn) or level["icon"]
            t["building_culture_variants"].append(dict(variant_like, building=key, icon=icon, short_description=key))
            loc[f"building_culture_variants_name_{key}"] = level["name"]
            loc[f"building_short_description_texts_short_description_{key}"] = level["text"]
            if previous:
                t["building_upgrades_junction"].append({"from": previous, "to": key})
            previous = key
    # stock levels with an icon of ours
    new_keys = {level["key"] for chain in CONFIG["new_chains"] for level in chain["levels"]}
    for row in g["building_culture_variants"]:
        short = row["building"].removeprefix(PREFIX)
        if row["building"].startswith(PREFIX) and short not in new_keys and row["building"] in stock_levels and stock_levels[row["building"]]["visible_in_ui"]:
            icon = icon_of(short, drawn)
            if icon:
                t["building_culture_variants"].append(dict(row, icon=icon))
    for name, blob in drawn.items():
        files[f"ui{SEP}buildings{SEP}icons{SEP}tww3_mtb_{name}.png"] = blob
    for short, needed in CONFIG.get("building_requires", {}).items():
        t["building_level_required_buildings"].append({"building_level": PREFIX + short, "required": PREFIX + needed})
    # real effects with the game's own text
    for short, effects in CONFIG.get("building_effects", {}).items():
        for e in effects:
            t["building_effects_junction"].append({"building": PREFIX + short, "effect": e["effect"], "effect_scope": e["scope"], "value": float(e["value"]),
                                                   "value_damaged": float(e["value"]), "value_ruined": 0.0, "context_requirement": ""})
    hidden_and_abilities(t, g, loc, CONFIG)
    return loc, files


TABLES = ("building_levels", "building_chains", "building_instances", "building_superchains", "building_chain_set_items", "building_chain_availability_sets",
          "building_set_to_building_junctions", "building_upgrades_junction", "building_culture_variants", "military_force_type_horde_details", "building_level_required_buildings",
          "building_units_allowed", "unit_abilities", "unit_special_abilities", "special_ability_phases", "special_ability_to_special_ability_phase_junctions",
          "special_ability_phase_stat_effects", "special_ability_to_auto_deactivate_flags", "effects", "building_effects_junction", "unit_set_unit_ability_junctions",
          "effect_bonus_value_unit_set_unit_ability_junctions")
EFFECT_ICONS = "ui/campaign ui/effect_bundles/"


def add_tree_rows(t, g, rows, config):
    """The author's tree into the tables t: every row as build/tree/tree_rows.json gives it (tools/tree_export.mjs decides them all, nothing is decided here).
    config: data/crew_options.json with the tree's building sections (tools/tree_port.py crew_config), for the abilities. Returns ({loc key: text}, {pack path: bytes})."""
    for table in TABLES:
        t.setdefault(table, [])
    loc, files = {}, {}
    rules = rows["source"]["port"]["rules"]
    stock_levels = {r["level_name"]: r for r in g["building_levels"]}
    stock_variants = {r["building"]: r for r in g["building_culture_variants"] if r["culture"] is None and r["subculture"] is None and r["faction"] is None}
    like_level_key = PREFIX + rules["level_like"]
    like_chain = one(g["building_chains"], key=stock_levels[like_level_key]["chain"])
    t["military_force_type_horde_details"].append(dict(one(g["military_force_type_horde_details"], force_type=FORCE), slot_cap=rows["slot_cap"]))
    chains = {c["key"]: c for c in rows["chains"]}
    for c in rows["chains"]:
        if c["vanilla"]:
            continue
        t["building_superchains"].append({"key": c["superchain"]})
        t["building_instances"].append({"key": c["instance"], "num_instances": 1})
        t["building_chains"].append(dict(like_chain, key=c["key"], building_superchain=c["superchain"], optional_sort_order=c["sort_order"]))
        t["building_chain_set_items"].append({"chain": c["key"], "remove": False, "set": rules["chain_set"], "super_chain": None})
        t["building_chain_availability_sets"].append({"building_chain": c["key"], "id": rules["culture_set"]})
        t["building_set_to_building_junctions"].append({"building_chain": c["key"], "building_level": None, "building_set": c["set"], "exclude": False})
    drawn = icon_files()
    like_effect = one(g["effects"], effect=ENABLE_LIKE)
    text_effects = {}
    for r in rows["levels"]:
        key = r["key"]
        stock = stock_levels.get(key)
        fields = dict(create_cost=r["cost"], create_time=r["turns"], development_point_cost=r["dev"], primary_slot_building_building_level_requirement=r["requirement"], visible_in_ui=True)
        if r["vanilla"]:
            t["building_levels"].append(dict(stock, **fields))
            t["building_culture_variants"].append(dict(stock_variants[key], icon=r["icon"]["name"], short_description=key))
        else:
            like = stock_levels.get(PREFIX + r["mod_key"]) if r["mod_key"] and (PREFIX + r["mod_key"]) in stock_levels else stock_levels[like_level_key]
            t["building_levels"].append(dict(like, level_name=key, chain=r["chain"], level=r["level"], building_instance_key=chains[r["chain"]]["instance"], **fields))
            t["building_culture_variants"].append(dict(stock_variants[like["level_name"]], building=key, icon=r["icon"]["name"], short_description=key))
        loc[f"building_culture_variants_name_{key}"] = r["name"]
        loc[f"building_short_description_texts_short_description_{key}"] = r["description"]
        for e in r["rows"]["effects"] + r["rows"]["zero"]:
            t["building_effects_junction"].append({k: (float(e[k]) if k.startswith("value") else e[k]) for k in ("building", "effect", "effect_scope", "value", "value_damaged", "value_ruined", "context_requirement")})
        for e in r["rows"]["text"]:
            t["building_effects_junction"].append({"building": key, "effect": e["effect"], "effect_scope": BUILDING_LINE_SCOPE, "value": float(e["value"]), "value_damaged": float(e["value"]),
                                                   "value_ruined": 0.0, "context_requirement": ""})
            text_effects[e["effect"]] = e
        for u in r["rows"]["units"]:
            t["building_units_allowed"].append(dict(u))
    # the lines of text: an effect of ours each, its description the line, green or red as the author's
    icon_of_line = {f"mtb_effect_line_{x['from'].removeprefix('mtb_')}_{x['id']}": x.get("icon") for r in rows["levels"] for x in r["effects"]}
    for effect, e in sorted(text_effects.items()):
        icon = icon_of_line.get(effect) or ""
        icon = icon[len(EFFECT_ICONS):] if icon.startswith(EFFECT_ICONS) else like_effect["icon"]
        t["effects"].append(dict(like_effect, effect=effect, is_positive_value_good=bool(e["good"]), icon=icon, icon_negative=icon))
        loc[f"effects_description_{effect}"] = e["text"]
    t["building_upgrades_junction"] += [dict(u) for u in rows["upgrades"]]
    t["building_level_required_buildings"] += [dict(q) for q in rows["requirements"]]
    for r in rows["levels"]:
        name = r["icon"]["name"].removeprefix("tww3_mtb_")
        if name not in drawn:
            raise SystemExit(f"{r['id']}: no drawing data/ui/buildings/{name}.png")
    for name, blob in drawn.items():
        files[f"ui{SEP}buildings{SEP}icons{SEP}tww3_mtb_{name}.png"] = blob
    # В3: the stock side chains the tree does not use (data/tree_port.json vanilla_chains)
    ai = rows["vanilla_ai"]
    if ai["mode"] == "hide":
        for key in ai["levels"]:
            t["building_levels"].append(dict(stock_levels[key], visible_in_ui=False))
    elif ai["mode"] == "remove":
        for chain in ai["chains"]:
            t["building_chain_set_items"].append({"chain": chain, "remove": True, "set": rules["chain_set"], "super_chain": None})
    hidden_and_abilities(t, g, loc, config)
    # one row per key: the build's own rows (the summon at 0) and the tree's never meet
    seen = set()
    for row in t["building_effects_junction"]:
        pk = (row["building"], row["effect"], row["context_requirement"])
        if pk in seen:
            raise SystemExit(f"building_effects_junction: two rows for {pk}")
        seen.add(pk)
    return loc, files


def hidden_and_abilities(t, g, loc, config):
    """The game's effects hidden from its lists, and the mod's abilities enabled by levels (config abilities, enabled_by: short keys)."""
    # effects of the game hidden from its lists: priority 0 and no icon, as the game's own hidden effects (data/crew_options.json, hidden_effects)
    for key in config.get("hidden_effects", {}).get("effects", []):
        t["effects"].append(dict(one(g["effects"], effect=key), priority=0, icon=None, icon_negative=None))
    # abilities: an enabling effect on our unit set, as the barge's own upgrades
    like_effect = one(g["effects"], effect=ENABLE_LIKE)
    for number, (key, spec) in enumerate(k for k in config["abilities"].items() if not k[0].startswith("_")):
        model = spec["model"]
        t["unit_abilities"].append(dict(one(g["unit_abilities"], key=model), key=key, icon_name=spec["icon"], requires_effect_enabling=False, is_unit_upgrade=False))
        changes = {"key": key, "unique_id": FIRST_ABILITY_ID + number}
        if "active_time" in spec:
            changes.update(active_time=float(spec["active_time"]), recharge_time=float(spec["recharge"]), initial_recharge=0.0, wind_up_time=0.0)
        t["unit_special_abilities"].append(dict(one(g["unit_special_abilities"], key=model), **changes))
        phase = {"id": key, "hp_change_frequency": 0.0, "damage_amount": 0, "max_damaged_entities": 0}
        if "active_time" in spec:
            phase["duration"] = float(spec["active_time"])
        t["special_ability_phases"].append(dict(one(g["special_ability_phases"], id=model), **phase))
        t["special_ability_to_special_ability_phase_junctions"].append(dict(one(g["special_ability_to_special_ability_phase_junctions"], special_ability=model), special_ability=key, phase=key))
        t["special_ability_phase_stat_effects"].append({"phase": key, "value": __import__("struct").unpack("<f", __import__("struct").pack("<f", spec["speed"]))[0], "stat": "scalar_speed", "how": "mult"})
        for row in g["special_ability_to_auto_deactivate_flags"]:
            if row["special_ability"] == model and "active_time" in spec:
                t["special_ability_to_auto_deactivate_flags"].append(dict(row, special_ability=key))
        effect = "mtb_effect_ability_" + key.removeprefix("mtb_")
        t["unit_set_unit_ability_junctions"].append({"key": key, "unit_ability": key, "unit_set": "mtb_dwf_malakai_thunderbarge"})
        t["effects"].append(dict(like_effect, effect=effect, priority=1))
        t["effect_bonus_value_unit_set_unit_ability_junctions"].append({"bonus_value_id": "enable", "effect": effect, "unit_set_ability": key})
        for short in spec["enabled_by"]:
            t["building_effects_junction"].append({"building": PREFIX + short, "effect": effect, "effect_scope": SCOPE, "value": 1.0, "value_damaged": 1.0, "value_ruined": 0.0, "context_requirement": ""})
        loc[f"unit_abilities_onscreen_name_{key}"] = spec["name"]
        loc[f"unit_abilities_tooltip_text_{key}"] = spec["about"]
        loc[f"effects_description_{effect}"] = spec["name"]
