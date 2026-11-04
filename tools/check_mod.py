"""Everything about the built mod that can be checked without the game: py -3.14 tools/check_mod.py

Reads the rows back from build/campaign/pack/tww3_mtb_campaign.pack and compares them with data/crew_options.json and the game's db.pack:
every building row has its culture variant, chain, instance and set; levels run on from each other, each on its own row of the tree; costs and times are in the agreed range;
requirements and upgrades point at real rows; every seat of every option at every boost level has a row, with a variant and a weapon that exist; every model a definition names is in
the pack or the game; every text is there; config and rows agree; Lua parses. Prints one line per failure, exit 1 if any.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import build  # noqa: E402
import dbtable  # noqa: E402
import gamepack  # noqa: E402
import pfh5  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
SEP = chr(92)
PACK = REPO / "build" / "campaign" / "pack" / "tww3_mtb_campaign.pack"
CONFIG = json.loads((REPO / "data" / "crew_options.json").read_text(encoding="utf-8"))
PREFIX = CONFIG["buildings_prefix"]
errors = []


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
    """Every script of the pack and of src/ through the Lua compiler, when one is on the machine (tools/ammo_offline.py needs lupa)."""
    py = shutil.which("python")
    code = ("import sys,lupa,pathlib\nrt=lupa.LuaRuntime()\nbad=0\nfor p in sys.argv[1:]:\n  src=pathlib.Path(p).read_text(encoding='utf-8')\n"
            "  r=rt.globals().load(src)\n  if r is None or (isinstance(r,tuple) and r[0] is None):\n    print('FAIL lua',p,r); bad=1\nsys.exit(bad)\n")
    temp = REPO / "build" / "check_lua"
    temp.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, blob in files.items():
        if name.endswith(".lua"):
            target = temp / name.replace(SEP, "_")
            target.write_bytes(blob)
            paths.append(str(target))
    out = subprocess.run([py, "-c", code, *paths], capture_output=True, text=True, errors="replace")
    if out.returncode != 0:
        fail("lua syntax: " + (out.stdout + out.stderr)[-400:])
    return len(paths)


def main():
    files, _ = pfh5.read_pack(PACK.read_bytes())
    t = {}
    for name, blob in files.items():
        if name.startswith("db" + SEP):
            table = name.split(SEP)[1].removesuffix("_tables")
            t[table] = dbtable.decode(blob, [tuple(f) for f in build.LAYOUTS[table]["fields"]])
    stock = build.game_tables()
    loc = loc_read(files[f"text{SEP}db{SEP}tww3_mtb.loc"])

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
            if tier in rows_seen and not chain.endswith("main_chain"):
                fail(f"{chain}: two levels on tree row {tier + 1}: the lower one is hidden")
            rows_seen.add(tier)
            if i and tier < rows[i - 1]["primary_slot_building_building_level_requirement"]:
                fail(f"{chain}: tree rows go down at {r['level_name']}")
            if i and (rows[i - 1]["level_name"], r["level_name"]) not in upgrades:
                fail(f"{chain}: no upgrade {rows[i - 1]['level_name']} -> {r['level_name']}")
    # 2. new chains: all the tables a chain needs, tiers and prices
    set_key = CONFIG["building_set"]["key"]
    avail = {r["building_chain"] for r in t["building_chain_availability_sets"]}
    items = {r["chain"] for r in t["building_chain_set_items"]}
    sets = {r["building_chain"]: r["building_set"] for r in t["building_set_to_building_junctions"]}
    for chain in CONFIG["new_chains"]:
        key = chain["key"]
        if key not in avail or key not in items or sets.get(key) != set_key:
            fail(f"{key}: not in availability, set items or the set")
        if chains[key]["building_superchain"] not in superchains:
            fail(f"{key}: no superchain")
        for level in chain["levels"]:
            r = levels[PREFIX + level["key"]]
            if r["primary_slot_building_building_level_requirement"] != level["tier"] - 1 or r["create_cost"] != level["cost"] or r["create_time"] != level["time"]:
                fail(f"{level['key']}: row and config differ")
            if not 1 <= level["time"] <= 3:
                fail(f"{level['key']}: time {level['time']}")
            band = {1: (300, 2000), 2: (750, 3000), 3: (1500, 6000), 4: (3000, 8000), 5: (6000, 12000)}[level["tier"]]
            if not band[0] <= level["cost"] <= band[1]:
                fail(f"{level['key']}: cost {level['cost']} out of {band} of tier {level['tier']}")
            for prefix in ("building_culture_variants_name_", "building_short_description_texts_short_description_"):
                if prefix + PREFIX + level["key"] not in loc:
                    fail(f"{level['key']}: no text {prefix}")
    if len(set(side)) - 5 > 0:
        cap = merged("military_force_type_horde_details", "force_type")["MALAKAI_BOUND_HORDE"]["slot_cap"]
        need = len({levels[k]["chain"] for k in side})
        if cap < need:
            fail(f"slot_cap {cap} for {need} chains")
    # 3. all side chains start from tier II, except the preparation buildings
    for chain, rows in by_chain.items():
        first = rows[0]
        if chain.endswith("main_chain"):
            continue
        tier = first["primary_slot_building_building_level_requirement"] + 1
        if tier < 2 and first["level_name"].removeprefix(PREFIX) not in ("mtb_nest_1", "mtb_hatches_1"):
            fail(f"{chain}: starts on tier {tier}")
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
    # 7. Lua
    count = lua_syntax(files)
    print(f"{len(side)} building levels in {len(by_chain)} chains, {sum(1 for p in pers if p.startswith('mtb_bp_'))} seat rows, {count} scripts, {len(loc)} texts, {len(errors)} failures")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
