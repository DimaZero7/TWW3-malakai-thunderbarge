"""The author's tree in the build: the game's facts out, the page's models over the tree (tools/tree_export.mjs), its rows back in. Called by tools/build.py.

  facts(stock)        build/tree/game_facts.json: what tools/tree_export.mjs needs to know of the game (Malakai's stock levels and chains, their effects and units,
                      every effect and unit key, the scopes and where the game uses them). Python decides nothing here: every rule is in the .mjs and data/tree_port.json.
  export(stock)       facts, then node tools/tree_export.mjs -> build/tree/tree_rows.json, read back
  crew_config(base, rows)   data/crew_options.json with its building sections taken from the tree: what the current crew Lua (src/tww3_mtb_crew.lua, the old panel)
                      reads by building key, so it works on the new keys until stage 2 replaces it
Run alone: py -3.14 tools/tree_port.py  (writes the two files and prints the counts).
"""
import collections
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

OUT = REPO / "build" / "tree"
FACTS = OUT / "game_facts.json"
ROWS = OUT / "tree_rows.json"
PREFIX = "wh3_dlc25_dwarf_spirit_of_grungni_"
CHAIN_PREFIX = "wh3_dlc25_dwf_spirit_of_grungni_"
FORCE = "MALAKAI_BOUND_HORDE"


def facts(stock):
    """The game's side of the port, written to build/tree/game_facts.json."""
    ours = {r["level_name"]: r for r in stock["building_levels"] if r["level_name"].startswith(PREFIX)}
    chains = {}
    for r in ours.values():
        chains.setdefault(r["chain"], []).append(r)
    set_items = collections.defaultdict(list)
    for r in stock["building_chain_set_items"]:
        if r["chain"]:
            set_items[r["chain"]].append(r["set"])
    building_sets = collections.defaultdict(list)
    for r in stock["building_set_to_building_junctions"]:
        if r["building_chain"]:
            building_sets[r["building_chain"]].append(r["building_set"])
    horde_chains = {c for c, sets in set_items.items() if any(s and "horde" in s for s in sets)}
    horde_levels = {r["level_name"] for r in stock["building_levels"] if r["chain"] in horde_chains}
    samples = collections.defaultdict(lambda: {"grungni": collections.Counter(), "horde": collections.Counter()})
    for r in stock["building_effects_junction"]:
        if r["building"] in ours:
            samples[r["effect"]]["grungni"][r["effect_scope"]] += 1
        if r["building"] in horde_levels:
            samples[r["effect"]]["horde"][r["effect_scope"]] += 1
    vanilla_effects = collections.defaultdict(list)
    for r in stock["building_effects_junction"]:
        if r["building"] in ours:
            vanilla_effects[r["building"]].append({k: r[k] for k in ("effect", "effect_scope", "value", "value_damaged", "value_ruined", "context_requirement")})
    vanilla_units = collections.defaultdict(list)
    for r in stock["building_units_allowed"]:
        if r["building"] in ours:
            vanilla_units[r["building"]].append(r["unit"])
    horde = next(r for r in stock["military_force_type_horde_details"] if r["force_type"] == FORCE)
    out = {
        "_about": "Made by tools/tree_port.py from the game's db.pack for tools/tree_export.mjs. Do not edit.",
        "prefix": PREFIX, "force": FORCE, "stock_slot_cap": horde["slot_cap"],
        "levels": {k: {"chain": r["chain"], "level": r["level"], "cost": r["create_cost"], "time": r["create_time"], "dev": r["development_point_cost"],
                       "requirement": r["primary_slot_building_building_level_requirement"], "visible": r["visible_in_ui"], "instance": r["building_instance_key"]}
                   for k, r in sorted(ours.items())},
        "chains": {c: {"levels": [r["level_name"] for r in sorted(rows, key=lambda r: r["level"]) if r["visible_in_ui"]],
                       "set_items": sorted(s for s in set_items.get(c, []) if s), "building_sets": sorted(building_sets.get(c, []))}
                   for c, rows in sorted(chains.items()) if c.startswith(CHAIN_PREFIX)},
        "vanilla_effects": dict(sorted(vanilla_effects.items())),
        "vanilla_units": {k: sorted(v) for k, v in sorted(vanilla_units.items())},
        "effects": sorted(r["effect"] for r in stock["effects"]),
        "scope_source": {r["key"]: r["source"] for r in stock["campaign_effect_scopes"]},
        "scope_samples": {e: {side: c[side].most_common() for side in ("grungni", "horde")} for e, c in sorted(samples.items())},
        "units": {r["unit"]: {"tier": r["tier"]} for r in stock["main_units"]},
        "units_allowed_keys": sorted(r["key"] for r in stock["building_units_allowed"]),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    FACTS.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    return out


def export(stock):
    """The tree's rows: build/tree/tree_rows.json, made by the page's models (tools/tree_export.mjs). Stops the build on an error of the tree."""
    facts(stock)
    node = shutil.which("node")
    if not node:
        raise SystemExit("node is not on the machine: tools/tree_export.mjs runs the page's models over the tree")
    run = subprocess.run([node, str(REPO / "tools" / "tree_export.mjs"), "--facts", str(FACTS), "--out", str(ROWS)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    sys.stdout.write(run.stdout)
    if run.returncode != 0:
        raise SystemExit("tools/tree_export.mjs: " + (run.stderr or run.stdout)[-3000:])
    return load()


def load():
    return json.loads(ROWS.read_text(encoding="utf-8"))


def crew_config(base, rows):
    """data/crew_options.json as the build reads it, its building sections from the tree (rows["crew_config"]): the bindings of crew options to levels,
    the levels that set an option at once, the ammunition of the cargo line, the boosts, the abilities' levels, the names. The groups' own requirement of
    another building (the guns: signals) is not in the tree and goes. The sections of the old chains (new_chains, building_edits, building_requires,
    building_effects, building_lines) are emptied: the tree's rows replace them."""
    cfg = copy.deepcopy(base)
    crew = rows["crew_config"]
    cfg["buildings"] = {short: [list(p) for p in pairs] for short, pairs in crew["buildings"].items()}
    cfg["auto_active"] = list(crew["auto_active"])
    cfg["ammo_mod"] = dict(crew["ammo_mod"])
    cfg["building_names"] = dict(crew["names"])
    cfg["slot_cap"] = rows["slot_cap"]
    for key in ("new_chains", "building_requires", "building_lines"):
        cfg[key] = [] if key == "new_chains" else {}
    cfg["building_edits"] = {"_about": "the tree's rows (tools/tree_export.mjs) replace this section"}
    cfg["building_effects"] = {}
    cfg["no_auto_line"] = []
    for group_key, group in cfg["groups"].items():
        group.pop("requires", None)
        boost = crew["boost"].get(group_key)
        if boost:
            group["boost"] = {"buildings": list(boost["buildings"]), "steps": [dict(s) for s in boost["steps"]], "_note": "from the tree (tools/tree_export.mjs)"}
        else:
            group.pop("boost", None)
    for key, spec in cfg["abilities"].items():
        if not key.startswith("_"):
            spec["enabled_by"] = list(crew["abilities"].get(key, []))
    return cfg


def main():
    import build
    rows = export(build.game_tables())
    print(json.dumps(rows["counts"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
