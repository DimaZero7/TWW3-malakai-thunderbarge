"""Everything about the built mod that can be checked without the game: py -3.14 tools/check_mod.py [--pack P] [--rows R]

Reads the rows back from build/campaign/pack/tww3_mtb_campaign.pack and compares them with the author's tree as build/tree/tree_rows.json gives it (tools/tree_export.mjs),
data/crew_options.json and the game's db.pack.
The tree (check_tree): every level of the tree is a row with its chain, level, cost, turns, development points and engine tier; its culture variant has the tree's icon, and the
icon's file is in the pack; its name and description are the tree's; its effect rows are exactly the tree's (game effects with their scopes, the stock effects set to 0 on a
stock key, the lines of text) besides the crew's lines and the mod's abilities, and no effect the tree leaves out is there; its units, requirements and upgrades are the tree's;
every chain has its superchain, instance, set and availability; every key the rows name exists in the game or the pack (effects, scopes, units, levels, sets); the game's own
check is never looser than the tree (the hull a level needs, its parents); the stock chains Malakai's AI builds are as the game has them (data/tree_port.json, В3).
The rest: levels run on from each other, each on its own row of the tree; every seat of every option at every boost level has a row, with a variant and a weapon that exist; every
model a definition names is in the pack or the game; every text is there; config and rows agree; Lua parses. Prints one line per failure, exit 1 if any.
"""
import argparse
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import build  # noqa: E402
import crew_options  # noqa: E402
import dbtable  # noqa: E402
import gamepack  # noqa: E402
import pfh5  # noqa: E402
import tree_port  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEP = chr(92)
PACK = REPO / "build" / "campaign" / "pack" / "tww3_mtb_campaign.pack"
CONFIG = crew_options.CONFIG        # with the tree's building sections, once main() has read the tree's rows
PREFIX = CONFIG["buildings_prefix"]
errors = []


def f32(x):
    return struct.unpack("<f", struct.pack("<f", float(x)))[0]


def check_tree(t, stock, loc, files, rows):
    """The pack's building rows against the tree's (build/tree/tree_rows.json) and the game's data. One readable line per difference."""
    P = rows["prefix"]
    levels = {r["level_name"]: r for r in t["building_levels"]}
    stock_levels = {r["level_name"]: r for r in stock["building_levels"]}
    stock_chains = {r["key"] for r in stock["building_chains"]}
    effects_known = {r["effect"] for r in stock["effects"]} | {r["effect"] for r in t["effects"]}
    scopes = {r["key"] for r in stock["campaign_effect_scopes"]}
    units_known = {r["unit"] for r in stock["main_units"]}
    variants = {r["building"]: r for r in t["building_culture_variants"]}
    chains = {c["key"]: c for c in rows["chains"]}
    tree_keys = {r["key"] for r in rows["levels"]}
    # 1. every level: its row as the tree gives it
    for r in rows["levels"]:
        key, row = r["key"], levels.get(r["key"])
        name = f"«{r['name']}» ({key})"
        if not row:
            fail(f"{name}: no building_levels row")
            continue
        want = {"chain": r["chain"], "level": r["level"], "create_cost": r["cost"], "create_time": r["turns"], "development_point_cost": r["dev"],
                "primary_slot_building_building_level_requirement": r["requirement"], "visible_in_ui": True}
        if not r["vanilla"]:
            want["building_instance_key"] = chains[r["chain"]]["instance"]
        for field, value in want.items():
            if row[field] != value:
                fail(f"{name}: {field} is {row[field]!r} in the pack, the tree has {value!r}")
        if r["vanilla"]:
            stock_row = stock_levels.get(key)
            if not stock_row:
                fail(f"{name}: a stock key that is not in the game")
            else:
                for field, value in stock_row.items():
                    if field not in want and row[field] != value:
                        fail(f"{name}: {field} of the stock level changed ({stock_row[field]!r} -> {row[field]!r})")
        elif key in stock_levels:
            fail(f"{name}: a new key that the game already has")
        if row["chain"] not in stock_chains and row["chain"] not in {c["key"] for c in t["building_chains"]}:
            fail(f"{name}: its chain {row['chain']} is in neither the game nor the pack")
        # the icon and the texts
        v = variants.get(key)
        if not v or not r["icon"] or v["icon"] != r["icon"]["name"]:
            fail(f"{name}: icon {v and v['icon']!r} in the pack, the tree has {r['icon'] and r['icon']['name']!r}")
        elif f"ui{SEP}buildings{SEP}icons{SEP}{v['icon']}.png" not in files:
            fail(f"{name}: the icon's file ui/buildings/icons/{v['icon']}.png is not in the pack")
        if v and v["short_description"] != key:
            fail(f"{name}: short_description {v['short_description']!r}, its text is under {key}")
        for loc_key, text in ((f"building_culture_variants_name_{key}", r["name"]), (f"building_short_description_texts_short_description_{key}", r["description"])):
            if loc.get(loc_key) != text:
                fail(f"{name}: text {loc_key} is {loc.get(loc_key)!r}, the tree has {text!r}")
        # the game's check never looser than the tree: the hull the tree asks for (by the tier, or a row of its own), every other parent a row or the
        # level below in the line
        own_rows = {q["required"] for q in t["building_level_required_buildings"] if q["building_level"] == key}
        by_id = {x["id"]: x for x in rows["levels"]}
        if not r["hull"] and r["requirement"] + 1 < (r["tier_own"] or 0):
            fail(f"{name}: needs hull level {r['requirement'] + 1} in the game, its own tier is {r['tier_own']}")
        for parent in r["requires"]:
            p = by_id.get(parent)
            if not p or parent == r["prev"] or r["hull"]:
                continue
            if p["hull"] and p["tier_engine"] <= r["requirement"] + 1:
                continue
            if p["key"] not in own_rows:
                fail(f"{name}: the tree requires «{p['name']}», neither the engine tier nor a building_level_required_buildings row says so")
    # 2. the chains of the lines
    sets_known = {r["key"] for r in stock["building_sets"]}
    chain_sets_known = {r["key"] for r in stock["building_chain_sets"]}
    rules = rows["source"]["port"]["rules"]
    for c in rows["chains"]:
        if c["vanilla"]:
            if c["key"] not in stock_chains:
                fail(f"chain {c['key']}: a stock chain that is not in the game")
            if any(x["key"] == c["key"] for x in t["building_chains"]):
                fail(f"chain {c['key']}: the stock chain is overridden")
            continue
        row = next((x for x in t["building_chains"] if x["key"] == c["key"]), None)
        if not row:
            fail(f"chain {c['key']}: no building_chains row")
            continue
        if row["building_superchain"] != c["superchain"] or not any(x["key"] == c["superchain"] for x in t["building_superchains"]):
            fail(f"chain {c['key']}: superchain {row['building_superchain']} missing")
        if not any(x["key"] == c["instance"] and x["num_instances"] == 1 for x in t["building_instances"]):
            fail(f"chain {c['key']}: instance {c['instance']} missing")
        if not any(x["chain"] == c["key"] and x["set"] == rules["chain_set"] and not x["remove"] for x in t["building_chain_set_items"]):
            fail(f"chain {c['key']}: not in the horde's set {rules['chain_set']}")
        if not any(x["building_chain"] == c["key"] and x["id"] == rules["culture_set"] for x in t["building_chain_availability_sets"]):
            fail(f"chain {c['key']}: not available to {rules['culture_set']}")
        if not any(x["building_chain"] == c["key"] and x["building_set"] == c["set"] for x in t["building_set_to_building_junctions"]):
            fail(f"chain {c['key']}: not in the building set {c['set']}")
        if c["set"] not in sets_known:
            fail(f"chain {c['key']}: the building set {c['set']} is not in the game")
    if rules["chain_set"] not in chain_sets_known:
        fail(f"the chain set {rules['chain_set']} is not in the game")
    if not any(r["id"] == rules["culture_set"] for r in stock["building_chain_availability_sets"]):
        fail(f"the availability set {rules['culture_set']} is used by no chain of the game")
    # 3. upgrades and requirements: exactly the tree's, pointing at levels that exist
    all_levels = set(stock_levels) | set(levels)
    got_up = {(r["from"], r["to"]) for r in t["building_upgrades_junction"]}
    want_up = {(r["from"], r["to"]) for r in rows["upgrades"]}
    for pair in sorted(want_up - got_up):
        fail(f"upgrade {pair[0]} -> {pair[1]}: in the tree, not in the pack")
    for pair in sorted(got_up - want_up):
        fail(f"upgrade {pair[0]} -> {pair[1]}: in the pack, not in the tree")
    got_req = {(r["building_level"], r["required"]) for r in t["building_level_required_buildings"]}
    want_req = {(r["building_level"], r["required"]) for r in rows["requirements"]}
    for pair in sorted(want_req - got_req):
        fail(f"requirement {pair[0]} needs {pair[1]}: in the tree, not in the pack")
    for pair in sorted(got_req - want_req):
        fail(f"requirement {pair[0]} needs {pair[1]}: in the pack, not in the tree")
    for a, b in got_up | got_req:
        for k in (a, b):
            if k not in all_levels:
                fail(f"{k}: named by an upgrade or a requirement, a level of neither the game nor the pack")
    # 4. effects: exactly the tree's rows on its levels, besides the crew's lines and the abilities of the mod
    pk = lambda r: (r["building"], r["effect"], r["context_requirement"])  # noqa: E731
    got = {pk(r): r for r in t["building_effects_junction"]}
    abilities_of = {}
    for key, spec in CONFIG["abilities"].items():
        if not key.startswith("_"):
            for short in spec["enabled_by"]:
                abilities_of.setdefault(P + short, set()).add("mtb_effect_ability_" + key.removeprefix("mtb_"))
    left = set(rows["source"]["port"]["rules"].get("vanilla_effects_left", []))
    for r in rows["levels"]:
        name = f"«{r['name']}» ({r['key']})"
        want = {}
        for e in r["rows"]["effects"] + r["rows"]["zero"]:
            want[pk(e)] = e
        for e in r["rows"]["text"]:
            want[(r["key"], e["effect"], "")] = dict(e, building=r["key"], effect_scope="force_to_force_own", value_damaged=e["value"], value_ruined=0, context_requirement="")
        for k, e in want.items():
            g = got.get(k)
            if not g:
                fail(f"{name}: effect {e['effect']} = {e['value']} of the tree is not in the pack")
                continue
            for field in ("effect_scope", "value", "value_damaged", "value_ruined"):
                if (g[field] != e[field]) if field == "effect_scope" else (g[field] != f32(e[field])):
                    fail(f"{name}: effect {e['effect']} {field} is {g[field]!r} in the pack, the tree has {e[field]!r}")
            if e["effect"] not in effects_known:
                fail(f"{name}: effect {e['effect']} is in neither the game nor the pack")
            if g["effect_scope"] not in scopes:
                fail(f"{name}: scope {g['effect_scope']} is not in the game")
            if e["effect"].startswith("mtb_effect_line_") and not loc.get(f"effects_description_{e['effect']}"):
                fail(f"{name}: the line {e['effect']} has no text")
        for k, g in got.items():
            if k[0] != r["key"] or k in want:
                continue
            if g["effect"].startswith(f"mtb_effect_crew_{r['short']}") or g["effect"] in abilities_of.get(r["key"], set()) or (r["vanilla"] and g["effect"] in left):
                continue
            fail(f"{name}: effect {g['effect']} = {g['value']} in the pack is not the tree's")
        # nothing the tree leaves out is there: a skipped game effect has no row on this level (on a stock key the stock row stays only where the tree says so)
        for s in r["skipped"]:
            e = next((x for x in r["effects"] if x["from"] == s["from"] and x["id"] == s["id"]), None)
            key = e and (e["effect"] or None)
            if key and (r["key"], key, "") in got and not r["vanilla"]:
                fail(f"{name}: {key} is left out by the tree ({s['why']}) but has a row")
    # 5. units: the tree's whole list of every level, keys of the table unique and none the game's
    stock_unit_keys = {r["key"] for r in stock["building_units_allowed"]}
    got_units = {(r["building"], r["unit"]) for r in t["building_units_allowed"]}
    want_units = {(u["building"], u["unit"]) for r in rows["levels"] for u in r["rows"]["units"]}
    for pair in sorted(want_units - got_units):
        fail(f"{pair[0]}: unit {pair[1]} of the tree is not allowed in the pack")
    for pair in sorted(got_units - want_units):
        fail(f"{pair[0]}: unit {pair[1]} allowed in the pack, not in the tree")
    for r in rows["levels"]:
        allowed = {u for b, u in got_units if b == r["key"]} | (set(rows_vanilla_units(stock, r["key"])) if r["vanilla"] else set())
        if not set(r["units_full"]) <= allowed or (not r["vanilla"] and allowed != set(r["units_full"])):
            fail(f"«{r['name']}»: allows {sorted(allowed)} in the game, the tree's whole list is {r['units_full']}")
    keys = [r["key"] for r in t["building_units_allowed"]]
    if len(keys) != len(set(keys)) or set(keys) & stock_unit_keys:
        fail("building_units_allowed: a key twice or one of the game's: a stock row would be replaced")
    for b, u in got_units:
        if u not in units_known:
            fail(f"{b}: unit {u} is not in main_units")
        if b not in tree_keys:
            fail(f"{b}: units allowed on a level that is not the tree's")
    # 6. the horde's slots
    horde = [r for r in t["military_force_type_horde_details"] if r["force_type"] == "MALAKAI_BOUND_HORDE"]
    stock_horde = next(r for r in stock["military_force_type_horde_details"] if r["force_type"] == "MALAKAI_BOUND_HORDE")
    if len(horde) != 1 or horde[0]["slot_cap"] != rows["slot_cap"]:
        fail(f"slot_cap {horde and horde[0]['slot_cap']} in the pack, data/tree_port.json has {rows['slot_cap']}")
    elif any(horde[0][f] != stock_horde[f] for f in stock_horde if f != "slot_cap"):
        fail("military_force_type_horde_details: a field besides slot_cap changed")
    side_lines = sum(1 for c in rows["chains"] if not c["hull"])
    if rows["slot_cap"] < side_lines:
        fail(f"slot_cap {rows['slot_cap']} for {side_lines} side lines of the tree")
    # 7. what the AI builds: the stock side chains the tree does not use, as the game has them (В3)
    ai = rows["vanilla_ai"]
    for key in ai["levels"]:
        row = levels.get(key)
        if row is None:
            if ai["mode"] == "hide":
                fail(f"{key}: В3 hide, but its row is not overridden")
            continue
        changed = [f for f in row if row[f] != stock_levels[key][f]]
        if ai["mode"] != "hide" or changed != ["visible_in_ui"]:
            fail(f"{key}: a stock level of the AI changed: {changed}")
    for chain in ai["chains"]:
        removed = [r for r in t["building_chain_set_items"] if r["chain"] == chain]
        if (ai["mode"] == "remove") != bool(removed and all(r["remove"] for r in removed)):
            fail(f"{chain}: set items {removed} do not match В3 mode {ai['mode']}")
        for table, field in (("building_chains", "key"), ("building_set_to_building_junctions", "building_chain"), ("building_chain_availability_sets", "building_chain")):
            if any(r[field] == chain for r in t[table]):
                fail(f"{chain}: overridden in {table}")
    ai_levels = set(ai["levels"])
    summon = set(rows["source"]["port"]["rules"].get("vanilla_effects_left", []))
    for r in t["building_effects_junction"]:
        if r["building"] in ai_levels and r["effect"] not in summon:
            fail(f"{r['building']}: a stock effect of an AI level overridden ({r['effect']})")
    for r in t["building_upgrades_junction"] + t["building_level_required_buildings"]:
        for k in r.values():
            if k in ai_levels:
                fail(f"{k}: a stock level of the AI named by our upgrades or requirements")
    # 8. the crew Lua got the tree's bindings
    crew_lua = files[f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew.lua"].decode("utf-8")
    for short in rows["crew_config"]["buildings"]:
        if f'["{P}{short}"]' not in crew_lua:
            fail(f"{short}: the crew Lua does not know the level that opens its crew")


def rows_vanilla_units(stock, key):
    return [r["unit"] for r in stock["building_units_allowed"] if r["building"] == key]


def fail(text):
    errors.append(text)
    print("FAIL", text)


def loc_read(blob):
    import struct
    count = struct.unpack_from("<I", blob, 10)[0]
    pos, out = 14, {}
    for _ in range(count):
        n = struct.unpack_from("<H", blob, pos)[0]
        key = blob[pos + 2:pos + 2 + n * 2].decode("utf-16-le")
        pos += 2 + n * 2
        n = struct.unpack_from("<H", blob, pos)[0]
        out[key] = blob[pos + 2:pos + 2 + n * 2].decode("utf-16-le")
        pos += 2 + n * 2 + 1
    return out


def lua_syntax(files):
    """Every script of the pack through the compiler of Lua 5.1, the game's Lua (lupa.lua51 of Python 3.10: py -3.10, as tools/lua_vectors.py)."""
    py = shutil.which("py")
    code = ("import sys,lupa.lua51 as l,pathlib\nrt=l.LuaRuntime(unpack_returned_tuples=True)\nassert rt.eval('_VERSION')=='Lua 5.1', rt.eval('_VERSION')\n"
            "comp=rt.eval('function(s, n) local f, e = loadstring(s, n); if f then return true end; return e end')\nbad=0\n"
            "for p in sys.argv[1:]:\n  src=pathlib.Path(p).read_text(encoding='utf-8')\n"
            "  r=comp(src, '@'+pathlib.Path(p).name)\n  if r is not True:\n    print('FAIL lua',p,r); bad=1\nsys.exit(bad)\n")
    temp = REPO / "build" / "check_lua"
    temp.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, blob in files.items():
        if name.endswith(".lua"):
            target = temp / name.replace(SEP, "_")
            target.write_bytes(blob)
            paths.append(str(target))
    out = subprocess.run([py, "-3.10", "-c", code, *paths], capture_output=True, text=True, errors="replace")
    if out.returncode != 0:
        fail("lua syntax: " + (out.stdout + out.stderr)[-400:])
    return len(paths)


def main(argv=None):
    global CONFIG
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default=str(PACK))
    ap.add_argument("--rows", default=str(tree_port.ROWS))
    ap.add_argument("--vectors", action="store_true", help="also the page's vectors on the pack's Lua (node tools/tests/vectors_export.mjs, py -3.10 tools/lua_vectors.py; about 3 min) and the "
                    "screen's drawing (node tools/tests/ui_dump_export.mjs, py -3.10 tools/ui_layout_check.py; about 2 min more)")
    args = ap.parse_args(argv)
    files, _ = pfh5.read_pack(Path(args.pack).read_bytes())
    tree_rows = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    CONFIG = tree_port.crew_config(crew_options.CONFIG, tree_rows)
    t = {table: [] for table in build.LAYOUTS}
    for name, blob in files.items():
        if name.startswith("db" + SEP):
            table = name.split(SEP)[1].removesuffix("_tables")
            t[table] = dbtable.decode(blob, [tuple(f) for f in build.LAYOUTS[table]["fields"]])
    stock = build.game_tables()
    loc = loc_read(files[f"text{SEP}db{SEP}tww3_mtb.loc"])
    # 0. the author's tree
    check_tree(t, stock, loc, files, tree_rows)
    shared_row = {(r["shares_row_with"], r["key"]) for r in tree_rows["levels"] if r["shares_row_with"]}

    def merged(table, key):
        out = {r[key]: r for r in stock.get(table, [])}
        out |= {r[key]: r for r in t.get(table, [])}
        return out
    levels = merged("building_levels", "level_name")
    chains = merged("building_chains", "key")
    instances = merged("building_instances", "key")
    superchains = merged("building_superchains", "key")
    variants_cul = {r["building"] for r in stock["building_culture_variants"]} | {r["building"] for r in t["building_culture_variants"]}
    upgrades = {(r["from"], r["to"]) for r in stock["building_upgrades_junction"]} | {(r["from"], r["to"]) for r in t["building_upgrades_junction"]}
    side = [k for k, r in levels.items() if k.startswith(PREFIX) and r["visible_in_ui"]]
    by_chain = {}
    for k in side:
        by_chain.setdefault(levels[k]["chain"], []).append(levels[k])
    # 1. buildings
    for key in side:
        r = levels[key]
        if key not in variants_cul:
            fail(f"{key}: no building_culture_variants row")
        if r["chain"] not in chains:
            fail(f"{key}: no chain {r['chain']}")
        if r["building_instance_key"] not in instances:
            fail(f"{key}: no instance {r['building_instance_key']}")
        if f"building_culture_variants_name_{key}" not in loc and not any(k.endswith(key) for k in ("",)) and r["chain"].startswith("mtb"):
            fail(f"{key}: no name")
    for chain, rows in by_chain.items():
        rows.sort(key=lambda r: r["level"])
        rows_seen = set()
        for i, r in enumerate(rows):
            if r["level"] != i:
                fail(f"{chain}: level {r['level']} at place {i}")
            tier = r["primary_slot_building_building_level_requirement"]
            if tier in rows_seen and not chain.endswith("main_chain") and (rows[i - 1]["level_name"], r["level_name"]) not in shared_row:
                fail(f"{chain}: two levels on tree row {tier + 1}: the lower one is hidden")
            rows_seen.add(tier)
            if i and tier < rows[i - 1]["primary_slot_building_building_level_requirement"]:
                fail(f"{chain}: tree rows go down at {r['level_name']}")
            if i and (rows[i - 1]["level_name"], r["level_name"]) not in upgrades:
                fail(f"{chain}: no upgrade {rows[i - 1]['level_name']} -> {r['level_name']}")
    # 2, 3 (the old chains of data/crew_options.json, their tiers and price bands) are the tree's now: check_tree, the tree's own numbers
    # 4. config against rows: bindings, seats, weapons
    pers = merged("battle_personalities", "key")
    stats = merged("battle_entity_stats", "key")
    weapons = merged("missile_weapons", "key")
    projectiles = merged("projectiles", "key")
    variant_rows = merged("variants", "variant_name")
    crew_lua = files[f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew.lua"].decode("utf-8")
    for short, pairs in CONFIG["buildings"].items():
        if PREFIX + short not in levels:
            fail(f"binding {short}: no such level")
        for group, option in pairs:
            spec = CONFIG["groups"][group]["options"].get(option)
            if not spec or spec.get("disabled"):
                fail(f"binding {short}: {group}/{option} missing or disabled")
    bound = {(g, o) for pairs in CONFIG["buildings"].values() for g, o in pairs}
    for group, spec in CONFIG["groups"].items():
        for key, opt in spec["options"].items():
            if opt.get("disabled"):
                if f"mtb_bp_{key}_" in crew_lua or any(p.startswith(f"mtb_bp_{key}_") for p in pers):
                    fail(f"{group}/{key}: disabled but in the pack")
                continue
            ui = opt.get("ui") or {}
            if not ui.get("hidden") and not ui.get("none") and key != spec.get("always") and key != "empty" and (group, key) not in bound:
                fail(f"{group}/{key}: no building opens it")
    for seat_group in CONFIG["groups"].values():
        boost = seat_group.get("boost")
        for key, opt in seat_group["options"].items():
            if opt.get("disabled") or opt.get("empty") or opt.get("ability"):
                continue
            base = [p for p in pers if p.startswith(f"mtb_bp_{key}_")]
            if not base and not opt.get("rings_only"):
                fail(f"{key}: no seat rows")
    for name, r in {k: v for k, v in pers.items() if k.startswith("mtb_bp_")}.items():
        if r.get("variant") and r["variant"] not in variant_rows:
            fail(f"{name}: variant {r['variant']} not found")
        stat = r.get("battle_entity_stats")
        if stat and stat not in stats:
            fail(f"{name}: stats {stat} not found")
        if stat:
            w = stats[stat].get("primary_missile_weapon")
            if w and w not in weapons:
                fail(f"{name}: weapon {w} not found")
            if w and weapons[w]["default_projectile"] not in projectiles:
                fail(f"{w}: projectile not found")
    # boost numbers: the guns' range is the stock number x 1.1, x 1.2
    for group, spec in CONFIG["groups"].items():
        boost = spec.get("boost")
        if not boost:
            continue
        for key, opt in spec["options"].items():
            if opt.get("disabled") or opt.get("empty") or opt.get("cover") or (opt.get("ui") or {}).get("hidden") or opt.get("rings_only"):
                continue
            first_seat = spec["seats"][0].removeprefix("ap_")
            base_row = pers.get(f"mtb_bp_{key}_{first_seat}")
            if not base_row:
                fail(f"{group}/{key}: no base row")
                continue
            base_p = projectiles[weapons[stats[base_row["battle_entity_stats"]]["primary_missile_weapon"]]["default_projectile"]]
            for level, step in enumerate(boost["steps"], 1):
                row = pers.get(f"mtb_bp_{key}_{first_seat}_b{level}")
                if not row:
                    fail(f"{group}/{key}: no row of level {level}")
                    continue
                p = projectiles[weapons[stats[row["battle_entity_stats"]]["primary_missile_weapon"]]["default_projectile"]]
                for field, mult in step.items():
                    if abs(p[field] - base_p[field] * mult) > max(0.51, abs(base_p[field]) * 0.001) and field == "effective_range":
                        fail(f"{key} level {level}: {field} {p[field]} of {base_p[field]} x {mult}")
                    if field != "effective_range" and abs(p[field] - base_p[field] * mult) > 0.001 * max(1, abs(base_p[field])):
                        fail(f"{key} level {level}: {field} {p[field]} of {base_p[field]} x {mult}")
    # 5. models named by the definitions: in the pack or the game
    names = {n.lower() for n in files}
    need = set()
    for name, blob in files.items():
        if name.endswith(".variantmeshdefinition"):
            need |= {m.replace("/", SEP).lower() for m in re.findall(r'model="([^"]+)"', blob.decode("utf-8", "replace"))}
    missing = sorted(m for m in need if m not in names)
    found = set()
    wanted = set(missing)
    for pack in sorted(gamepack.DATA.glob("*.pack")):
        if pack.name.startswith(("audio", "local_")) or not wanted - found:
            continue
        for n, _ in gamepack.entries(pack, lambda n: n.lower() in wanted):
            found.add(n.lower())
    for m in sorted(wanted - found):
        fail(f"model not in the pack or the game: {m}")
    # wsmodels of ours name a geometry of ours
    for name, blob in files.items():
        if name.endswith(".wsmodel"):
            for g in re.findall(r"<geometry>([^<]+)</geometry>|<rigid_model[^>]*>([^<]+)<", blob.decode("utf-8", "replace")):
                pass
    # 6. texts of the effects of buildings
    desc = {r["effect"] for r in t["effects"]}
    for r in t["building_effects_junction"]:
        if r["effect"] in desc and f"effects_description_{r['effect']}" not in loc:
            fail(f"{r['effect']}: no text")
    for r in t["unit_abilities"]:
        if f"unit_abilities_onscreen_name_{r['key']}" not in loc:
            fail(f"{r['key']}: no ability name")
    # the frames of the crew cards
    panel = files[f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew_ui.lua"].decode("utf-8")
    for name in set(re.findall(r"ui/tww3_mtb/(card_frame_\w+)\.png", panel)):
        if f"ui{SEP}tww3_mtb{SEP}{name}.png" not in files:
            fail(f"{name}: not in the pack")
    # in the game a chest is a building's price, upkeep is coins
    if "'upkeep_icon', 'ui/skins/default/icon_income.png'" not in panel or "'hire_icon', 'ui/skins/default/icon_treasury.png'" not in panel:
        fail("the panel's icons: upkeep is coins, hire is the chest")
    # the hire: the sum, an empty option free
    import crew_ui
    for group, spec in CONFIG["groups"].items():
        for key, opt in spec["options"].items():
            if opt.get("disabled"):
                continue
            cost = crew_ui.hire(opt, stock)
            source = opt.get("upkeep_from")
            if opt.get("empty") or not source:
                if cost != 0:
                    fail(f"{group}/{key}: hire {cost} of a free option")
            elif cost <= 0 and "hire" not in opt:
                fail(f"{group}/{key}: no price")
    # the frame's colour comes from the crew group, nowhere else
    for group, spec in CONFIG["groups"].items():
        for key, opt in spec["options"].items():
            if "card_frame" in opt:
                fail(f"{group}/{key}: a frame of its own: the colour belongs to the group")
    for short, pairs in CONFIG["buildings"].items():
        for group, option in pairs:
            spec = CONFIG["groups"][group]
            if spec.get("no_panel") or spec.get("mount") == option or short in CONFIG.get("no_card", []):
                continue
            if f"card_frame_{spec['card_frame']}.png" not in panel:
                fail(f"{short}: no frame {spec['card_frame']} of group {group}")
    # 7. Lua
    count = lua_syntax(files)
    # 8. the airship screen's logic: the page's answers replayed on the packed Lua (docs/design/port-to-game.md, 4.2)
    if args.vectors:
        if Path(args.pack).resolve() != PACK.resolve():
            fail("--vectors replays the built pack only (tools/lua_vectors.py reads build/campaign/pack)")
        for cmd in ([shutil.which("node"), str(REPO / "tools" / "tests" / "vectors_export.mjs")], [shutil.which("py"), "-3.10", str(REPO / "tools" / "lua_vectors.py")]):
            run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            print((run.stdout + run.stderr).strip()[-2500:])
            if run.returncode != 0:
                fail(f"{Path(cmd[-1]).name}: exit {run.returncode}")
                break
        # 9. the airship screen's drawing: the page's screen in its reference states (a headless Chrome, its own server on port 8775 or MTB_PORT)
        # against the packed Lua drawing the same states (docs/design/port-to-game.md, 4.2 «Экран без игры»)
        node = shutil.which("node")
        major = int(subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v").split(".")[0] or 0)
        websocket = ["--experimental-websocket"] if major < 22 else []       # tools/tests/cdp.mjs needs a global WebSocket
        for cmd in ([node, *websocket, str(REPO / "tools" / "tests" / "ui_dump_export.mjs")], [shutil.which("py"), "-3.10", str(REPO / "tools" / "ui_layout_check.py")]):
            run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            print((run.stdout + run.stderr).strip()[-2500:])
            if run.returncode != 0:
                fail(f"{Path(cmd[-1]).name}: exit {run.returncode}")
                break
    print(f"{len(side)} building levels in {len(by_chain)} chains, {sum(1 for p in pers if p.startswith('mtb_bp_'))} seat rows, {count} scripts, {len(loc)} texts, {len(errors)} failures")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
