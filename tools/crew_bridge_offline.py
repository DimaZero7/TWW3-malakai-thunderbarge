"""The new panel's crew bridge without the game (docs/design/port-to-game.md 8.6): py -3.10 tools/crew_bridge_offline.py [--only TEXT] [--break NAME]

Every scenario of build/vectors made on the author's tree (node tools/tests/vectors_export.mjs) is replayed on the screen's model AND on the old
mod's crew module as packed (build/campaign/pack: py -3.14 tools/build.py first) with NEW_SHIP_PANEL on, in one fake campaign under the game's
emulated Lua (tools/game_lua_env.py): tools/tests/crew_bridge_replay.lua. The old module's memory write is a recorder of what it would write. After
every step the answer must hold:
  * the gold is the page's (the vectors' treasury) and the old mechanics moved none: the hire and the upkeep are taken once, by the model;
  * the seats carry what the model has standing (a bay's empty place: the bay or the plain ship), at the boost level of the buildings standing,
    Malakai at the rail of the model's side and a crew dwarf at the helm; the cargo handed to the battle is the standing cargo building's; the
    harpoon's bundle is on exactly while the harpoon's place is empty; nothing written is stale;
  * the numbers the panel shows (crew bonuses and ammunition) equal what the battle applies, except the known gaps: the tree's effects the port
    skips (build/tree/tree_rows.json, port.as = skip: stage 5) and the mod's own sources of the screen's data the battle has not. The gaps are
    listed with how often each was seen; anything else is a mismatch.
--break NAME breaks the packed crew module on purpose (upkeep_twice, no_sync, no_drop, bay, malakai, old_turn) to show the replay catching it.
Exit 1 on any mismatch.
"""
import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import pfh5  # noqa: E402
import game_lua_env as genv  # noqa: E402
import lua_vectors as lv  # noqa: E402

PACK = REPO / "build" / "campaign" / "pack" / "tww3_mtb_campaign.pack"
VECTORS = REPO / "build" / "vectors"
TREE = REPO / "build" / "tree" / "tree_rows.json"
SEP = chr(92)
FOLDER = f"script{SEP}campaign{SEP}tww3_mtb{SEP}"
CREW = f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew.lua"
OWNED = ["rifles", "cannons", "bombs", "cupolas", "harpoon"]
CREW_KINDS = ("ammo", "accuracy", "range", "reload", "damage")

# deliberate breaks of the packed crew module: (what is replaced, by what, what the replay must then say)
BREAKS = {
    "upkeep_twice": [("    if new_panel() then return end      -- the new panel's model takes the upkeep", "    if false then return end      -- BROKEN, was: the new panel's model takes the upkeep"),
                     ("                M.sync_abilities()\n                core:get_tm():real_callback(bridge_guarded('turn'",
                      "                M.sync_abilities()\n                M.pay_upkeep()\n                core:get_tm():real_callback(bridge_guarded('turn'")],
    "no_sync": [("    if sig == B.applied then return false end", "    if true then return false end")],
    "no_drop": [("    local any = model.drop_locked()", "    local any = false")],
    "bay": [("if of_model and spec.mount and saved == spec.mount and not M.mount_ready(group)", "if false and of_model")],
    "malakai": [("M.MALAKAI_AT_RAIL = true", "M.MALAKAI_AT_RAIL = false")],
    "old_turn": [("            if new_panel() then\n                -- the model's own turn start", "            if false then\n                -- the model's own turn start"),
                 ("    if profile() ~= 'player' or new_panel() then return end      -- the new panel: the model's turn start", "    if profile() ~= 'player' then return end      --"),
                 ("    if new_panel() then return end      -- the new panel's model takes the upkeep", "    if false then return end      -- BROKEN, was: the new panel's model takes the upkeep")],
}


def expectations(tree):
    """What the tree says the battle has (tools/tree_export.mjs crew_config, the packed crew module's data) and what of the panel it lacks."""
    prefix = tree["prefix"]
    name_of = {r["key"]: r["name"] for r in tree["levels"]}
    crew = tree["crew_config"]
    boost = {g: {"keys": [prefix + s for s in b["buildings"]], "steps": b["steps"]} for g, b in crew["boost"].items()}
    ammo_mod = {prefix + s: m for s, m in crew["ammo_mod"].items()}
    unapplied, skipped = {}, []
    for r in tree["levels"]:
        for e in r["effects"]:
            if e.get("kind") in CREW_KINDS and e["port"]["as"] == "skip":
                unapplied[f"{r['name']}|{e['kind']}|{e.get('target') or 'all'}"] = True
                skipped.append((r["name"], e["kind"], e.get("target") or "all", e.get("value"), e["port"].get("why")))
    battle_mod = {}
    for g, b in boost.items():
        for key, step in zip(b["keys"], b["steps"]):
            if "calibration_area" in step:
                battle_mod[f"{name_of.get(key, key)}|accuracy|{g}"] = True
            if "effective_range" in step:
                battle_mod[f"{name_of.get(key, key)}|range|{g}"] = True
    for key in ammo_mod:
        for g in OWNED:
            battle_mod[f"{name_of.get(key, key)}|ammo|{g}"] = True
    return {"boost": boost, "ammo_mod": ammo_mod, "unapplied": unapplied, "battle_mod": battle_mod, "owned": {g: True for g in OWNED}}, skipped


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--break", dest="broken", choices=sorted(BREAKS), default=None)
    ap.add_argument("--max-diffs", type=int, default=12)
    args = ap.parse_args(argv)
    if not PACK.exists():
        sys.exit(f"no pack {PACK}: py -3.14 tools/build.py first")
    meta = json.loads((VECTORS / "meta.json").read_text(encoding="utf-8"))
    files, _ = pfh5.read_pack(PACK.read_bytes())
    crew_src = files[CREW].decode("utf-8")
    if args.broken:
        for old, new in BREAKS[args.broken]:
            if crew_src.count(old) != 1:
                sys.exit(f"--break {args.broken}: the line «{old[:70]}» is not in the packed crew module once ({crew_src.count(old)})")
            crew_src = crew_src.replace(old, new, 1)
    tree = json.loads(TREE.read_text(encoding="utf-8"))
    X, skipped = expectations(tree)

    lua, info = genv.new_runtime()
    lv.F32 = True
    modules = {n: files[FOLDER + n].decode("utf-8") for n in ("tww3_mtb_crew_model.lua", "tww3_mtb_ship.lua", "tww3_mtb_ship_config.lua")}
    CM = genv.load_mod(lua, modules["tww3_mtb_crew_model.lua"], "tww3_mtb_crew_model.lua")
    Ship = genv.load_mod(lua, modules["tww3_mtb_ship.lua"], "tww3_mtb_ship.lua")
    packed = genv.load_mod(lua, modules["tww3_mtb_ship_config.lua"], "tww3_mtb_ship_config.lua")
    Fake = genv.load_mod(lua, (REPO / "tools" / "tests" / "fake_game.lua").read_text(encoding="utf-8"), "fake_game.lua")
    VR = genv.load_mod(lua, (REPO / "tools" / "tests" / "vectors_replay.lua").read_text(encoding="utf-8"), "vectors_replay.lua")(Ship, CM, Fake)
    load_mod = lua.execute(genv.LOAD_MOD)
    load_crew = lua.eval("function(load) return function(src) return load(src, 'tww3_mtb_crew.lua') end end")(load_mod)
    decode = Ship.decode

    def lua_json(v):
        return decode(json.dumps(lv.numbers_as_game(v, 0), ensure_ascii=False))

    if not lv.same(lv.py(packed), meta["config"]):
        sys.exit("the pack's ship config is not the one of build/vectors: py -3.14 tools/build.py, then node tools/tests/vectors_export.mjs")
    author = lua_json(lv.py(packed))
    R = genv.load_mod(lua, (REPO / "tools" / "tests" / "crew_bridge_replay.lua").read_text(encoding="utf-8"), "crew_bridge_replay.lua")(
        Ship, CM, Fake, VR, crew_src, load_crew, lua_json(X))

    started = time.time()
    diffs = shown = scenarios = steps = writes = 0
    first = {}

    def report(text):
        nonlocal diffs, shown
        diffs += 1
        kind = text.split("]", 1)[-1].strip().split(" ", 1)[0]
        first.setdefault(kind, text)
        if shown < args.max_diffs:
            shown += 1
            print("MISMATCH " + text)

    for name in meta["files"]:
        if name == "units.json":
            continue
        for sc in json.loads((VECTORS / name).read_text(encoding="utf-8"))["scenarios"]:
            if sc["config"] != "author" or (args.only and args.only not in sc["name"]):
                continue
            scenarios += 1
            try:
                w = R.world(author, lua_json(sc["sim"]))
            except Exception as e:      # lupa.LuaError
                report(f"[{sc['name']}] the world does not start: {e}")
                continue
            expected = dict(sc["obs0"])
            for i, st in enumerate(sc["steps"], 1):
                action = {k: v for k, v in st.items() if k not in ("ret", "set", "del")}
                try:
                    ret = R.apply(w, lua_json(action))
                except Exception as e:
                    report(f"[{sc['name']}] step {i} {json.dumps(action, ensure_ascii=False)}: the Lua failed: {e}")
                    break
                steps += 1
                if ret != st["ret"]:
                    report(f"[{sc['name']}] step {i} answer {ret!r}, the page {st['ret']!r}")
                expected.update(st["set"])
                for f in st.get("del", []):
                    expected.pop(f, None)
                want = {"treasury": expected.get("treasury"),
                        "crew": {g: expected[f"crew.{g}"] for g in OWNED if expected.get(f"crew.{g}") is not None},
                        "order": {g: expected.get(f"crew.{g}.order") or False for g in OWNED if f"crew.{g}" in expected}}
                try:
                    problems = lv.py(R.check(w, lua_json(want))) or []
                except Exception as e:
                    report(f"[{sc['name']}] step {i}: the check failed: {e}")
                    break
                for p in problems:
                    report(f"[{sc['name']}] step {i} {action.get('do')}: {p}")
                if problems:
                    break       # one scenario's first divergence is what matters; the rest follows from it
            writes += R.writes(w)

    gaps = lv.py(R.gaps()) or []
    for line, n in (lv.py(R.info) or {}).items():
        print(f"info: {n}x {line}")
    print(f"crew bridge ({lua.eval('_VERSION')}, game env{', BROKEN: ' + args.broken if args.broken else ''}): {scenarios} scenarios on the author's tree, "
          f"{steps} steps, {writes} seat writes recorded, {diffs} mismatches ({time.time() - started:.0f} s)")
    if first:
        print("first mismatch of each kind:")
        for text in first.values():
            print("  " + text[:400])
    print(f"known gaps, the panel shows what the battle does not apply yet ({len(gaps)} kinds; the tree's effects skipped by the port: {len(skipped)}):")
    for g in sorted(gaps, key=lambda g: -g["count"]):
        print(f"  {g['count']:>6}x  {g['line']}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
