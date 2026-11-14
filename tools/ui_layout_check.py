"""The airship screen's drawing proven without the game (docs/design/port-to-game.md, 4.2 «Экран без игры»):
    py -3.10 tools/ui_layout_check.py [--src] [--only TEXT] [--max-diffs N]

Lua 5.1 (lupa.lua51). The modules as packed (build/campaign/pack/tww3_mtb_campaign.pack: py -3.14 tools/build.py first) or, with --src, as they are
in src/ with the configs of build/tree: src/tww3_mtb_ship_ui.lua over src/tww3_mtb_ship.lua and src/tww3_mtb_crew_model.lua, the fake game
tools/tests/fake_game.lua and the fake UIComponent tools/tests/fake_uic.lua. For every state the page wrote (build/ui_dump/*.json: node
tools/tests/ui_dump_export.mjs first) the same state is made on the Lua (the page's saved state, its keys turned into the mod's), the panel built
at the same root (1600 x 900), the same clicks and the mouse on the same component, and the Lua's component tree is compared with the page's: a
component missing or extra, an offset or a size more than 1 unit apart, a text, state, picture, visibility, colour, shader, opacity, tooltip, glow,
layer, interactive flag differing. Texts are measured with the page's own numbers (the dump's measures); a text the page never measured is a
difference too. A few differences are the game's on purpose (ACCEPTED below, each with its reason). Exit 1 on any difference.
"""
import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

import lupa.lua51 as lupa51

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import pfh5  # noqa: E402

PACK = REPO / "build" / "campaign" / "pack" / "tww3_mtb_campaign.pack"
DUMPS = REPO / "build" / "ui_dump"
SEP = chr(92)
FOLDER = f"script{SEP}campaign{SEP}tww3_mtb{SEP}"
POS = ("x", "y", "w", "h")
EXACT = ("layout", "visible", "text", "state", "image", "colour", "shader", "opacity", "tooltip", "glow", "layer", "interactive", "blank", "image_opacity")
NEAR = ("text_size", "scale")

# What the game draws differently from the page on purpose: (path pattern, field, why). Nothing else may differ.
ACCEPTED = [
    (r"/mtb_tree_node_\d+/constructing$", "visible", "question V5: no clock-wipe of a construction in the game, the turns banner and the pale slot say it"),
    (r"/tree_page/tree_bar_(track|top|bottom|left|right|handle)_?\w*$", "interactive", "the scroll bar takes the game's click; the page takes it by its own mouse listeners"),
]
ACCEPTED_RE = [(re.compile(p), f, why) for p, f, why in ACCEPTED]


def py(v):
    if lupa51.lua_type(v) == "table":
        keys = list(v.keys())
        if keys and all(isinstance(k, int) for k in keys) and sorted(keys) == list(range(1, len(keys) + 1)):
            return [py(v[i]) for i in range(1, len(keys) + 1)]
        return {str(k): py(x) for k, x in v.items()}
    return v


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", action="store_true", help="the modules of src/ and the configs of build/tree in place of the pack's")
    ap.add_argument("--only", default=None, help="only the states whose name has this text")
    ap.add_argument("--max-diffs", type=int, default=15, help="the differences printed per state (all are counted)")
    args = ap.parse_args(argv)
    index = DUMPS / "index.json"
    if not index.exists():
        sys.exit("no dumps of the page: node tools/tests/ui_dump_export.mjs first (a Node with a global WebSocket)")
    states = json.loads(index.read_text(encoding="utf-8"))["states"]

    lua = lupa51.LuaRuntime(unpack_returned_tuples=True)
    if lua.eval("_VERSION") != "Lua 5.1":
        sys.exit("not Lua 5.1: " + str(lua.eval("_VERSION")))
    # the game's string library (UTF-8 find / sub / len, find with 3 arguments and no patterns; the originals as find_lua, sub_lua, len_lua),
    # before any module is loaded: a call the game would not take fails here, not in the game (build/port_probe/lua_env_census.txt)
    try:
        from game_lua_env import GAME_STRINGS
    except ImportError:
        sys.path.insert(0, str(REPO / "tools" / "tests"))
        from port_probe import GAME_STRINGS
    lua.execute(GAME_STRINGS)
    load = lua.eval("function(src, name) local f, e = loadstring(src, '@' .. name); if not f then error(e) end; return f() end")
    if args.src:
        files = None
    else:
        if not PACK.exists():
            sys.exit(f"no pack {PACK}: py -3.14 tools/build.py first (or --src)")
        files, _ = pfh5.read_pack(PACK.read_bytes())

    def module(name):
        if files is None:
            return load((REPO / "src" / name).read_text(encoding="utf-8"), name)
        key = FOLDER + name
        if key not in files:
            sys.exit(f"{name} is not in the pack: py -3.14 tools/build.py")
        return load(files[key].decode("utf-8"), name)

    CM = module("tww3_mtb_crew_model.lua")
    Ship = module("tww3_mtb_ship.lua")
    UI = module("tww3_mtb_ship_ui.lua")
    # JSON into Lua tables here, not by the module's decoder: what is compared is the drawing, and the module's own JSON is the logic's pass
    def to_lua(v):
        if isinstance(v, dict):
            return lua.table_from({k: to_lua(x) for k, x in v.items() if x is not None})
        if isinstance(v, list):
            return lua.table_from([to_lua(x) for x in v])
        return v

    def decode(text):
        return to_lua(json.loads(text))
    if files is None:
        config = decode((REPO / "build" / "tree" / "ship_config.json").read_text(encoding="utf-8"))
        cfg_json = json.loads((REPO / "build" / "tree" / "ship_ui_config.json").read_text(encoding="utf-8"))
        cfg = decode(json.dumps(cfg_json, ensure_ascii=False))
    else:
        config = module("tww3_mtb_ship_config.lua")
        cfg = module("tww3_mtb_ship_ui_config.lua")
        cfg_json = py(cfg)
    FakeGame = load((REPO / "tools" / "tests" / "fake_game.lua").read_text(encoding="utf-8"), "fake_game.lua")
    FakeUIC = load((REPO / "tools" / "tests" / "fake_uic.lua").read_text(encoding="utf-8"), "fake_uic.lua")
    prefix = cfg_json["data"]["rows"][0]["key"][: -len(cfg_json["data"]["rows"][0]["id"])] if cfg_json["data"]["rows"] else ""
    # the page's keys (prefix + the node) -> the mod's
    key_of = {prefix + r["id"]: r["key"] for r in cfg_json["data"]["rows"]}

    def mk(k):
        return key_of.get(k, k)

    def lj(v):
        return decode(json.dumps(v, ensure_ascii=False))

    # the Lua side of one state: the page's saved state on the fake game and the module, the panel built, the view acted on
    build_state = lua.eval("""function(UI, Ship, CM, FakeGame, FakeUIC, config, cfg, snap, actions, measures)
        local game = FakeGame.new(config, {turn = snap.turn, gold = snap.gold, income = 0, demolish = 'step_down', built = {}})
        game.restore({turn = snap.turn, gold = snap.gold, built = snap.built, queue = snap.queue})
        local M = Ship.make(config, game, CM)
        if snap.side then M.set_side_silently(snap.side) end
        M.set_side_chosen_silently(snap.side_chosen)
        M.set_crew_silently(snap.crew)
        M.set_crew_chosen_silently(snap.crew_chosen)
        M.set_news_silently(snap.ship)
        M.set_message_silently(snap.message)
        M.sync_ship()
        local ui = FakeUIC.new{measures = measures, text = cfg.text, w = 1600, h = 900}
        local t0 = os.clock()
        local panel = UI.make_panel{root = ui.root, M = M, cfg = cfg, CM = CM, Ship = Ship, flags = {}, keep = {tab = 'tree'}}
        panel.refresh()
        local built = os.clock() - t0
        local made = ui.count
        for _, a in ipairs(actions) do
            local c = ui.find(a[2])
            if not c then error('no component ' .. a[2]) end
            if a[1] == 'click' then panel.click(c) else ui.mouse_on(c) end
        end
        return {rows = ui.dump(), unmeasured = ui.unmeasured, made = made, seconds = built}
    end""")

    def accepted(path, field):
        return any(rx.search(path) and f == field for rx, f, _ in ACCEPTED_RE)

    started = time.time()
    total_diffs = total_rows = total_fields = 0
    summary = []
    for name in states:
        if args.only and args.only not in name:
            continue
        d = json.loads((DUMPS / f"{name}.json").read_text(encoding="utf-8"))
        snap = d["snapshot"]
        snap_l = {
            "turn": snap["turn"], "gold": snap["gold"], "built": [mk(k) for k in snap["built"]],
            "queue": [{"key": mk(k), "turns_left": q["turns_left"], "paid": q["paid"]} for k, q in snap["queue"]],
            "side": snap.get("side"), "side_chosen": bool(snap.get("side_chosen")),
            "crew": [{"group": g, "standing": st["standing"], **({"order": st["order"]} if st.get("order") else {})} for g, st in (snap.get("crew") or {}).items() if st],
            "crew_chosen": snap.get("crew_chosen") or {},
            "ship": {"unseen": bool((snap.get("ship") or {}).get("unseen")),
                     **({"news": {**snap["ship"]["news"], "built": [mk(k) for k in snap["ship"]["news"].get("built", [])]}} if (snap.get("ship") or {}).get("news") else {})},
            "message": snap.get("message") or {},
        }
        snap_l = {k: v for k, v in snap_l.items() if v is not None}
        try:
            out = py(build_state(UI, Ship, CM, FakeGame, FakeUIC, config, cfg, lj(snap_l), lj(d["actions"]), lj(d["measures"])))
        except lupa51.LuaError as e:
            print(f"[{name}] the Lua failed: {e}")
            total_diffs += 1
            continue
        mine = {r["path"]: r for r in out["rows"]}
        page = {r["path"]: r for r in d["components"]}
        diffs = []
        for p in page:
            if p not in mine:
                diffs.append(f"missing in the Lua: {p} ({page[p]['layout']})")
        for p in mine:
            if p not in page:
                diffs.append(f"extra in the Lua: {p} ({mine[p]['layout']})")
        fields = 0
        for p, a in page.items():
            b = mine.get(p)
            if not b:
                continue
            for f in POS:
                fields += 1
                va, vb = a.get(f), b.get(f)
                if va is None or vb is None or abs(va - vb) > 1:
                    diffs.append(f"{p}: {f} page {va}, Lua {vb}")
            for f in EXACT:
                fields += 1
                va, vb = a.get(f), b.get(f)
                if f == "visible" and va is not None:
                    va, vb = bool(va), bool(vb)
                if va != vb and not accepted(p, f):
                    diffs.append(f"{p}: {f} page {json.dumps(va, ensure_ascii=False)}, Lua {json.dumps(vb, ensure_ascii=False)}")
            for f in NEAR:
                fields += 1
                va, vb = a.get(f), b.get(f)
                if (va is None) != (vb is None) or (va is not None and abs(va - vb) > 0.01):
                    diffs.append(f"{p}: {f} page {va}, Lua {vb}")
        for k in dict.fromkeys(out["unmeasured"] or []):
            diffs.append(f"a text the page never measured: {k}")
        total_diffs += len(diffs)
        total_rows += len(page)
        total_fields += fields
        layouts = Counter(r["layout"] for r in out["rows"])
        summary.append((name, len(page), len(mine), len(diffs), out["seconds"]))
        print(f"{name}: {len(page)} components on the page, {len(mine)} in the Lua ({out['made']} made: {layouts['image']} images, "
              f"{sum(v for k, v in layouts.items() if k.startswith('text_'))} texts), {len(diffs)} differences")
        for line in diffs[: args.max_diffs]:
            print("    " + line)
        if len(diffs) > args.max_diffs:
            print(f"    ... and {len(diffs) - args.max_diffs} more")
    # The game binding (src/tww3_mtb_ship_uic.lua) run once over a stand-in of the game's UIComponent that takes any call: every method the drawing
    # calls exists in the binding, and the binding's own steps (the hover, the scale of «Всё дерево», the scroll bar) run without an error.
    if not args.only:
        Uic = module("tww3_mtb_ship_uic.lua")
        smoke = lua.eval("""function(UI, Uic, Ship, CM, FakeGame, config, cfg)
            local calls, made = {}, 0
            local function stub()
                made = made + 1
                return setmetatable({}, {__index = function(_, k)
                    calls[k] = (calls[k] or 0) + 1
                    return function(_, ...)
                        if k == 'CreateComponent' then return stub() end
                        if k == 'Width' then return 1600 elseif k == 'Height' then return 900 elseif k == 'NumImages' then return 1 end
                        return nil
                    end
                end})
            end
            local saved = {UIComponent = UIComponent, core = core}
            UIComponent = function(x) return x end
            core = {get_ui_root = function() return stub() end}
            local ok, err = pcall(function()
                local game = FakeGame.new(config, {turn = 1, gold = 6000, income = 0, built = {}})
                local M = Ship.make(config, game, CM)
                local ui = Uic.new('ui/tww3_mtb/', cfg.text)
                local root = ui.root('mtb_ship_screen')
                local panel = UI.make_panel{root = root, M = M, cfg = cfg, CM = CM, Ship = Ship, flags = {}, keep = {}}
                panel.refresh()
                for _, id in ipairs({'mtb_tree_node_0', 'mtb_tree_node_1', 'tree_bar_bottom', 'tree_bar_track_vertical', 'mtb_tree_fit', 'mtb_tree_fit', 'mtb_tab_ship', 'mtb_crew_area_rifles', 'mtb_tab_tree'}) do
                    local c = ui.by_id(id)
                    if c then panel.click(c) end
                end
                ui.mouse_on('mtb_tree_node_2'); ui.mouse_on('frame')
            end)
            UIComponent, core = saved.UIComponent, saved.core
            return {ok = ok, err = tostring(err), made = made}
        end""")
        r = py(smoke(UI, Uic, Ship, CM, FakeGame, config, cfg))
        if not r["ok"]:
            total_diffs += 1
            print(f"the game binding failed over the stand-in UIComponent: {r['err']}")
        else:
            print(f"the game binding (src/tww3_mtb_ship_uic.lua) over a stand-in UIComponent: {r['made']} components made, built, clicked, hovered without an error")
    print(f"ui layout ({lua.eval('_VERSION')}, {'src' if args.src else 'pack'}): {len(summary)} states, {total_rows} components and {total_fields} fields compared, "
          f"{total_diffs} differences; accepted on purpose: {len(ACCEPTED)} rules ({time.time() - started:.0f} s)")
    for _, f, why in ACCEPTED:
        print(f"    accepted {f}: {why}")
    return 1 if total_diffs else 0


if __name__ == "__main__":
    sys.exit(main())
