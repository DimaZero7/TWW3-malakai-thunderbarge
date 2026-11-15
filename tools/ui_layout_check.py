"""The airship screen's drawing proven without the game (docs/design/port-to-game.md, 4.2 «Экран без игры»):
    py -3.10 tools/ui_layout_check.py [--src] [--only TEXT] [--max-diffs N] [--session RUN]

Lua 5.1 (lupa.lua51). The modules as packed (build/campaign/pack/tww3_mtb_campaign.pack: py -3.14 tools/build.py first) or, with --src, as they are
in src/ with the configs of build/tree and the layouts and pictures tools/ship_lua.py would pack: src/tww3_mtb_ship_ui.lua over the game binding
src/tww3_mtb_ship_uic.lua over a stand-in of the game's own UIComponent (tools/tests/fake_uic.lua Fake.engine: the layouts of the pack, Resize
that scales the children unless told not to, no colour of a picture, SetOpacity on a component's own picture only, PropagateOpacity, TextDimensions
answering a boolean), over src/tww3_mtb_ship.lua, src/tww3_mtb_crew_model.lua and the fake game tools/tests/fake_game.lua.

For every state the page wrote (build/ui_dump/*.json: node tools/tests/ui_dump_export.mjs first) the same state is made on the Lua (the page's saved
state, its keys turned into the mod's save keys and read by Ship.load_state), the panel built at the same root (1600 x 900), the same clicks and the
mouse on the same component, three times:
  1. every window made at once, as the page makes them (panel.build_all), texts measured with the page's own numbers (the dump's measures): the
     binding's component tree compared with the page's (a component missing or extra, an offset or a size more than 1 unit apart, a text, state,
     picture, visibility, colour, shader, opacity, tooltip, glow, layer, interactive flag differing; a text the page never measured), and what the
     game would draw against what the binding asked (Fake.check_engine: the game's own sizes, the opacity each picture is drawn with, the pictures
     coloured in advance, the tree's content under a clipping ancestor);
  2. the windows made on first use, as in the game: every component the page shows is there and equal to the page's;
  3. as 2, with the game's text measures (--session: the dumps of an in-game session, its TextDimensions where it measured the same text at the same
     width, elsewhere the page's measure at the game's widths and line heights): the game's own sizes, and the windows under the mouse readable
     (Fake.check_windows: no text over another, the icons on their lines, nothing out of its window).
Besides: the layouts (clipchildren where the game reads it, a picture where the binding expects one) and the screen's own steps (a failed start
leaves nothing behind; close hides and the next open shows the same components again). A few differences from the page are the game's on purpose
(ACCEPTED below, each with its reason). Exit 1 on any difference.
"""
import argparse
import json
import re
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import lupa.lua51 as lupa51

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import pfh5  # noqa: E402

PACK = REPO / "build" / "campaign" / "pack" / "tww3_mtb_campaign.pack"
DUMPS = REPO / "build" / "ui_dump"
SIM = json.loads((REPO / "web" / "data" / "sim.json").read_text(encoding="utf-8"))      # the page's simulated game: its growth rule
SESSION_LAST = REPO / "build" / "ship_session" / "last_run.txt"
SEP = chr(92)
FOLDER = f"script{SEP}campaign{SEP}tww3_mtb{SEP}"
UI_FOLDER = f"ui{SEP}tww3_mtb{SEP}"
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


def layout_props(files):
    """{layout name: what the game reads from it} for every layout of ours in the pack: the component's element (the second under <components>)
    gives its kind, clipchildren, its default state's size, its pictures, its text's alignment; attributes on the component's node in <hierarchy>
    (where the game ignores them) are a problem."""
    out, problems = {}, []
    for key, blob in files.items():
        if not (key.startswith(UI_FOLDER) and key.endswith(".twui.xml")) or SEP in key[len(UI_FOLDER):]:
            continue
        name = key[len(UI_FOLDER):-len(".twui.xml")]
        root = ET.fromstring(blob.decode("utf-8"))
        node = list(list(root.find("hierarchy"))[0])[0]
        if set(node.attrib) - {"this"}:
            problems.append(f"layout {name}: {sorted(set(node.attrib) - {'this'})} on its <hierarchy> node, where the game ignores them")
        el = list(root.find("components"))[1]
        states = list(el.find("states"))
        default = next((s for s in states if s.get("this") == el.get("defaultstate")), states[0])
        images = list(el.find("componentimages"))
        text = default.find("component_text")
        paths = {i.get("this"): i.get("imagepath") for i in images}
        # the 9-slice edges of every state's picture, in the game's order (top, right, bottom, left): they must fit the picture, or the game draws
        # past its edge the neighbours of the picture in its texture (runs/20261115-012811-ship_panel, defect 4: a gunsight and a stroke under
        # every separator)
        for st in states:
            for im in (st.find("imagemetrics") if st.find("imagemetrics") is not None else []):
                mg, path = im.get("margin"), paths.get(im.get("componentimage"))
                if not mg or not path:
                    continue
                t, r, b, l = (float(v) for v in mg.split(","))
                size = picture_size(path)
                if size and (l + r > size[0] or t + b > size[1]):
                    problems.append(f"layout {name}: margin {mg} (top, right, bottom, left) does not fit {path} ({size[0]} x {size[1]}): the game draws past the picture")
        preset = text.get("font_colour_override_preset_key") if text is not None else None
        out[name] = {"kind": el.tag, "clip": el.get("clipchildren") == "true", "w": float(default.get("width")), "h": float(default.get("height")),
                     "images": len(images), "picture": bool(images) and default.find("imagemetrics") is not None, "text": text is not None,
                     "valign": text.get("textvalign") if text is not None else None, "align": text.get("texthalign") if text is not None else None,
                     "default": default.get("name"), "interactive": default.get("interactive") == "true", "preset": preset,
                     "image": next(iter(paths.values()), None) if len(paths) == 1 else None}
    return out, problems


def picture_size(path):
    """(w, h) of a picture by its pack path: the game's (build/web/game, as tools/web_export.py copied them) or ours (data/ui, web/art); None unknown."""
    for f in (REPO / "build" / "web" / "game" / path, REPO / "data" / "ui" / path.split("/")[-1], REPO / "web" / "art" / path.split("/")[-1]):
        if f.exists():
            head = f.read_bytes()[:24]
            if head[:8] == b"\x89PNG\r\n\x1a\n":
                return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")
    return None


def session_dumps(arg):
    """The dumps of the last in-game session (build/ship_session/last_run.txt) or of --session: [(name, rows)]."""
    run = Path(arg) if arg else (Path(SESSION_LAST.read_text(encoding="utf-8").strip()) if SESSION_LAST.exists() else None)
    if not run or not run.exists():
        return None, []
    return run, [(f.stem, json.loads(f.read_text(encoding="utf-8"))["components"]) for f in sorted(run.glob("dump_*.json"))]


def game_text_model(dumps):
    """What the game's TextDimensions answered in a session: {layout|width|text: [w, h]} where it measured a text at the width the binding gave
    (the game's own Width() equal to it), and by layout the median ratio of the game's width to the page's and the game's height of one line."""
    exact = {}
    for _, rows in dumps:
        for r in rows:
            td, lw = r.get("td"), r.get("lw")
            if isinstance(td, list) and len(td) >= 2 and isinstance(td[0], (int, float)) and r.get("text") and lw == r.get("w"):
                exact[f"{r['layout']}|{r['w']}|{r['text']}"] = [td[0], td[1]]
    return exact


def game_measures(page, exact):
    """The page's measures turned into the game's: the session's own answer where it has one; elsewhere the page's width times the game's ratio
    for that layout (median, else of all), and the page's lines times the game's height of one line for that layout (its least height of a text
    the page measured as one line)."""
    ratio, line = defaultdict(list), defaultdict(list)
    for key, g in exact.items():
        p = page.get(key)
        if not p or not p[0]:
            continue
        lay = key.split("|", 1)[0]
        ratio[lay].append(g[0] / p[0])
        if len(p) > 2 and p[2] == 1:
            line[lay].append(g[1])
    all_ratio = statistics.median([x for v in ratio.values() for x in v]) if ratio else 0.96
    all_line_k = statistics.median([g[1] / page[k][1] for k, g in exact.items() if k in page and page[k][1]]) if exact else 0.75
    out = {}
    for key, p in page.items():
        if key.startswith("ink|"):
            out[key] = p
            continue
        if key in exact:
            out[key] = exact[key]
            continue
        lay, w, _ = key.split("|", 2)
        k = statistics.median(ratio[lay]) if ratio[lay] else all_ratio
        n = p[2] if len(p) > 2 else 1
        h = n * min(line[lay]) if line[lay] and n else p[1] * all_line_k
        out[key] = [min(round(p[0] * k), int(float(w))), round(h)]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", action="store_true", help="the modules of src/ and the configs of build/tree in place of the pack's")
    ap.add_argument("--only", default=None, help="only the states whose name has this text")
    ap.add_argument("--max-diffs", type=int, default=15, help="the differences printed per state (all are counted)")
    ap.add_argument("--profile", action="store_true", help="print the drawing's own time by section and the model's calls (windows on first use)")
    ap.add_argument("--session", default=None, help="the run folder of an in-game session whose TextDimensions to use (default: the last)")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="backslashreplace")
    except AttributeError:
        pass
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
        try:
            import gamepack  # noqa: F401
        except ImportError:
            # tools/gamepack.py needs Python 3.14 (compression.zstd); the layouts' writers do not read the game's packs
            import types
            sys.modules["gamepack"] = types.ModuleType("gamepack")
        import crew_ui
        import ship_lua
        ui_files = {**crew_ui.files(), **ship_lua.files()}
    else:
        if not PACK.exists():
            sys.exit(f"no pack {PACK}: py -3.14 tools/build.py first (or --src)")
        files, _ = pfh5.read_pack(PACK.read_bytes())
        ui_files = files

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
    Uic = module("tww3_mtb_ship_uic.lua")
    Screen = module("tww3_mtb_ship_screen.lua")
    # every JSON text into Lua by the module's own decoder (Ship.decode, under the game's string functions), as the mod reads its saved state
    decode = Ship.decode
    if files is None:
        config = decode((REPO / "build" / "tree" / "ship_config.json").read_text(encoding="utf-8"))
        cfg = decode((REPO / "build" / "tree" / "ship_ui_config.json").read_text(encoding="utf-8"))
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
        return json.dumps(v, ensure_ascii=False, separators=(",", ":"))

    total_diffs = 0
    started = time.time()
    # ---- the layouts as the game reads them ----
    props, layout_problems = layout_props(ui_files)
    pack_paths = {k.replace(SEP, "/"): True for k in ui_files if k.lower().endswith(".png")}
    no_picture = py(Uic.NO_PICTURE) or {}
    for name, p in props.items():
        if not p["text"] and p["picture"] == bool(no_picture.get(name)):
            layout_problems.append(f"layout {name}: {'a' if p['picture'] else 'no'} picture, src/tww3_mtb_ship_uic.lua NO_PICTURE says otherwise")
    if not props.get("tree_window", {}).get("clip"):
        layout_problems.append("layout tree_window: no clipchildren on its component: the tree is drawn over the panel (ss_fresh_tree.png of 20261114-230723)")
    for line in layout_problems:
        print("layouts: " + line)
    total_diffs += len(layout_problems)
    lprops = lua.table_from({k: lua.table_from(v) for k, v in props.items()})
    lpack = lua.table_from(pack_paths)

    # the game's text measures of the last in-game session
    run, dumps = session_dumps(args.session)
    exact = game_text_model(dumps)

    # the Lua side of one state: the game's part of the page's save on the fake game, the mod's part as the save keys the mod writes (Ship.save_state)
    # read back by Ship.load_state, the panel built on that over the binding over the stand-in of the game's UIComponent, the view acted on. Every JSON
    # text decoded by Ship.decode. mode: 'page' (all windows at once), 'lazy' (on first use), 'game' (on first use, the game's text measures)
    build_state = lua.eval("""function(UI, Uic, Ship, CM, FakeGame, FakeUIC, config, cfg, game_json, saved, actions_json, measures_json, layouts, pack, mode)
        local snap, actions, measures = Ship.decode(game_json), Ship.decode(actions_json), Ship.decode(measures_json)
        -- the horde's growth as the page had it (web/data/sim.json: growth_base, growth_threshold; the snapshot's growth accumulated): the foot
        -- row's «… следующая единица через N ходов» is the same then
        local game = FakeGame.new(config, {turn = snap.turn, gold = snap.gold, income = 0, demolish = 'chain', built = {}, dev_points = snap.dev,
                                           growth = snap.growth, growth_base = snap.growth_base, growth_threshold = snap.growth_threshold,
                                           ask_cancel = snap.ask_cancel, async = snap.async})
        game.restore({turn = snap.turn, gold = snap.gold, dev = snap.dev, growth = snap.growth, built = snap.built, queue = snap.queue, dismantles = snap.dismantles})
        local M = Ship.make(config, game, CM)
        local keep = Ship.load_state(M, function(k) return saved[k] end)
        -- with the game's measures at the game's root of the sessions (1920 x 1080, the panel 180 from the screen's edge): a window placed by the
        -- screen's edge instead of the panel's shows there (run 20261115-030121, ss_info_corner), not at the page's 1600 x 900
        local E = FakeUIC.engine{layouts = layouts, measures = measures, w = mode == 'game' and 1920 or 1600, h = mode == 'game' and 1080 or 900}
        local saved_g = {UIComponent = UIComponent, core = core}
        UIComponent = function(x) return x end
        core = {get_ui_root = function() return E.root end}
        -- the ink of the title: the page's own measure (ENGINE.ink is what the game would answer)
        local ENGINE = Uic.ENGINE
        local ink, unmeasured = ENGINE.ink, {}
        ENGINE.ink = function(text, size)
            local key = 'ink|text_title|' .. string.format('%.6g', size) .. '|' .. (text or '')
            local m = measures[key]
            if m then return m end
            unmeasured[#unmeasured + 1] = key
            return ink(text, size)
        end
        ENGINE.children_keep = nil
        for k in pairs(ENGINE.measured) do ENGINE.measured[k] = 0 end
        local ok, res = pcall(function()
            local ui = Uic.new('ui/tww3_mtb/', cfg.text)
            local root = ui.root('mtb_ship_screen')
            local t0 = os.clock()
            local panel = UI.make_panel{root = root, M = M, cfg = cfg, CM = CM, Ship = Ship, flags = {}, keep = {tab = keep.tab, pan = keep.scroll}, lazy = mode ~= 'page', ui = ui, profile = mode == 'lazy'}
            panel.refresh()
            local built = os.clock() - t0
            local made, calls = ui.count, 0
            for _, n in pairs(E.calls) do calls = calls + n end
            local images = E.calls.SetImagePath or 0
            if mode == 'page' then panel.build_all(); panel.refresh() end
            for _, a in ipairs(actions) do
                local c = ui.by_id(a[2])
                if not c then error('no component ' .. a[2]) end
                if a[1] == 'click' then panel.click(c)
                elseif a[1] == 'show' then panel.view.pan.show(panel.view.tree[tonumber(string.sub(a[2], #'mtb_tree_node_' + 1)) + 1])
                else ui.mouse_on(a[2]) end
            end
            for _, k in ipairs(E.unmeasured) do unmeasured[#unmeasured + 1] = k end
            -- the mouse and the tree as a player moves them (with the game's text measures: the windows' real sizes), after the dump's rows are taken
            local rows = ui.dump(root)
            local foot = mode == 'game' and FakeUIC.check_foot(panel.view, M) or {}
            local scen = mode == 'game' and FakeUIC.scenarios(panel, ui, root) or {}
            for _, p in ipairs(foot) do scen[#scen + 1] = p end
            -- the drawing's own time by section and the model's calls (src/tww3_mtb_ship_ui.lua env.profile): the opening, the state's actions, then
            -- «Всё дерево» and back, each with the refresh it makes
            local prof = panel.profile and panel.profile(true)
            if mode == 'lazy' and prof then
                local fit = ui.by_id('mtb_tree_fit')
                if fit and fit.visible then panel.click(fit); prof.fit = panel.profile(true); panel.click(fit); prof.back = panel.profile(true) end
            end
            return {rows = rows, scenarios = scen, image_calls = images, profile = mode == 'lazy' and prof or nil, unmeasured = mode ~= 'game' and unmeasured or {}, made = made, calls = calls, seconds = built,
                    engine = FakeUIC.check_engine(root, E, pack), windows = mode == 'game' and FakeUIC.check_windows(root, E) or {},
                    colours = FakeUIC.check_colours(root, cfg.text, cfg.colours or {}),
                    total = ui.count, measured = ENGINE.measured}
        end)
        ENGINE.ink = ink
        UIComponent, core = saved_g.UIComponent, saved_g.core
        if not ok then error(res) end
        return res
    end""")

    def accepted(path, field):
        return any(rx.search(path) and f == field for rx, f, _ in ACCEPTED_RE)

    def compare(page, mine, partial=False):
        """The differences of the binding's rows from the page's; partial: only the rows both have, and a component the page shows missing."""
        diffs, fields = [], 0
        shown = set()
        for p, r in page.items():
            parent = p.rsplit("/", 1)[0] if "/" in p else None
            if r.get("visible") and (parent is None or parent in shown):
                shown.add(p)
        for p in page:
            if p not in mine and (not partial or p in shown):
                diffs.append(f"missing in the Lua: {p} ({page[p]['layout']})" + (" (the page shows it)" if partial else ""))
        for p in mine:
            if p not in page:
                diffs.append(f"extra in the Lua: {p} ({mine[p]['layout']})")
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
        return diffs, fields

    def show(title, lines):
        print(title)
        for line in lines[: args.max_diffs]:
            print("    " + line)
        if len(lines) > args.max_diffs:
            print(f"    ... and {len(lines) - args.max_diffs} more")

    total_rows = total_fields = 0
    summary = []
    kinds = Counter()
    opened = []
    for name in states:
        if args.only and args.only not in name:
            continue
        d = json.loads((DUMPS / f"{name}.json").read_text(encoding="utf-8"))
        snap = d["snapshot"]
        # the game's own save (its buildings, the queue, the treasury, the turn)
        game_l = {
            "turn": snap["turn"], "gold": snap["gold"], "built": [mk(k) for k in snap["built"]],
            "queue": [{"key": mk(k), "turns_left": q["turns_left"], "paid": q["paid"], "dev": q.get("dev") or 0, "turn": q.get("turn", snap["turn"])}
                      for k, q in snap["queue"]],
            "dismantles": [mk(k) for k in snap.get("dismantles") or []],
            # the horde's development points (None: the page does not model them) and the game's window before a cancel (the dump's own sim)
            **({"dev": snap["dev"]} if snap.get("dev") is not None else {}),
            **({"growth": snap["growth"], "growth_base": SIM.get("growth_base", 0), "growth_threshold": SIM.get("growth_threshold", 20)} if snap.get("growth") is not None else {}),
            "ask_cancel": bool((d.get("sim") or {}).get("ask_cancel")),
            "async": bool((d.get("sim") or {}).get("async")),
        }
        # the mod's save: the page's state written as the keys Ship.save_state writes (src/tww3_mtb_ship.lua, SAVE_KEYS), the panel on «Постройки»
        # at its home place (the page's exporter forgets the tab and the tree's place of the last visit)
        crew = [(g, st) for g, st in (snap.get("crew") or {}).items() if st]
        ship = snap.get("ship") or {}
        msg = snap.get("message") or {}
        saved = {
            "mtb_crew_groups": ",".join(g for g, _ in crew),
            **{"mtb_crew_" + g: lj({"standing": st["standing"], **({"order": st["order"]} if st.get("order") else {})}) for g, st in crew},
            "mtb_crew_chosen": lj(snap.get("crew_chosen") or {}),
            "mtb_ship_news": lj({**ship["news"], "built": [mk(k) for k in ship["news"].get("built", [])]}) if ship.get("news") else "",
            "mtb_ship_unseen": "1" if ship.get("unseen") else "0",
            "mtb_ship_message": msg.get("text") or "",
            "mtb_ship_turn_line": lj(msg["turn_line"]) if msg.get("turn_line") else "",
            "mtb_ship_report": lj(msg["report"]) if msg.get("report") else "",
            "mtb_malakai_side_chosen": "1" if snap.get("side_chosen") else "0",
            "mtb_ship_tab": "tree",
            "mtb_ship_scroll": "",
        }
        if snap.get("side"):
            saved["mtb_malakai_side"] = snap["side"]
        page = {r["path"]: r for r in d["components"]}
        measures = d["measures"]
        state_diffs = 0
        for mode in ("page", "lazy", "game"):
            if mode == "game" and not exact:
                continue
            ms = game_measures(measures, exact) if mode == "game" else measures
            try:
                out = py(build_state(UI, Uic, Ship, CM, FakeGame, FakeUIC, config, cfg, lj(game_l), lua.table_from(saved), lj(d["actions"]), lj(ms),
                                     lprops, lpack, mode))
            except lupa51.LuaError as e:
                print(f"[{name}, {mode}] the Lua failed: {e}")
                state_diffs += 1
                continue
            mine = {r["path"]: r for r in out["rows"]}
            diffs, fields = [], 0
            if mode != "game":
                diffs, fields = compare(page, mine, partial=mode == "lazy")
                for k in dict.fromkeys(out["unmeasured"] or []):
                    diffs.append(f"a text the page never measured: {k}")
            engine = [f"{e['kind']}: {e['path']}: {e['text']}" for e in (out["engine"] or []) + (out.get("colours") or [])]
            windows = [f"{e['kind']}: {e['path']}: {e['text']}" for e in (out["windows"] or []) + (out.get("scenarios") or [])]
            state_diffs += len(diffs) + len(engine) + len(windows)
            kinds.update(f"{mode}: page" for _ in diffs)
            kinds.update(f"{mode}: {e['kind']}" for e in (out["engine"] or []) + (out["windows"] or []) + (out.get("colours") or []) + (out.get("scenarios") or []))
            if mode == "page":
                total_rows += len(page)
                total_fields += fields
                layouts = Counter(r["layout"] for r in out["rows"])
                print(f"{name}: {len(page)} components on the page, {len(mine)} in the Lua (all windows made: {layouts['image']} images, "
                      f"{sum(v for k, v in layouts.items() if k.startswith('text_'))} texts), {len(diffs)} differences, {len(engine)} in what the game draws")
            elif mode == "lazy":
                opened.append((out["made"], out["calls"], out["seconds"]))
                if args.profile and out.get("profile"):
                    for part in ("sections", "model", "fit", "back"):
                        p = out["profile"].get(part)
                        if not p:
                            continue
                        rows_ = (p.items() if part in ("sections", "model") else [(f"{k} [{part}]", v) for k, v in {**p.get("sections", {}), **{"model " + m: x for m, x in p.get("model", {}).items()}}.items()])
                        rows_ = sorted(rows_, key=lambda kv: -kv[1]["s"])[:12]
                        print(f"    profile {part}: " + "; ".join(f"{k} {v['n']}x {v['s'] * 1000:.1f} ms" for k, v in rows_))
                print(f"    windows on first use: {out['made']} components at the opening ({out['calls']} calls into the game's UIComponent, "
                      f"{out['calls'] / max(1, out['made']):.1f} per component, SetImagePath {out.get('image_calls')}), {out['total']} after the state's actions; {len(diffs)} differences from what "
                      f"the page shows, {len(engine)} in what the game draws")
            else:
                print(f"    with the game's text measures: {len(engine)} differences in what the game draws, {len(windows)} in the windows")
            show(f"    [{mode}]", diffs + engine + windows) if diffs or engine or windows else None
        total_diffs += state_diffs
        summary.append((name, state_diffs))

    # ---- the screen: a failed start leaves nothing, close hides and open shows the same components again ----
    if not args.only:
        screen = lua.eval("""function(Screen, UI, Uic, Ship, CM, FakeGame, FakeUIC, config, cfg, layouts)
            local E = FakeUIC.engine{layouts = layouts, measures = {}, w = 1600, h = 900}
            local saved = {UIComponent = UIComponent, core = core, cm = cm, find_uicomponent = find_uicomponent}
            local listeners, timers, log = {}, {}, {}
            UIComponent = function(x) return x end
            local tm = {repeat_real_callback = function(_, fn, ms, name) timers[name] = fn end, real_callback = function(_, fn) fn() end,
                        remove_real_callback = function(_, name) timers[name] = nil end}
            core = {get_ui_root = function() return E.root end, get_tm = function() return tm end,
                    add_listener = function(_, name) listeners[name] = true end, remove_listener = function(_, name) listeners[name] = nil end}
            cm = {steal_escape_key_with_callback = function() end, release_escape_key_with_callback = function() end}
            local advisor = E.root:CreateComponent('advice_interface', 'image')
            local radar = E.root:CreateComponent('radar_things', 'image')
            find_uicomponent = function(_, name) if name == 'advice_interface' then return advisor elseif name == 'radar_things' then return radar end end
            local function count(t) local n = 0; for _ in pairs(t) do n = n + 1 end; return n end
            local ok, res = pcall(function()
                local broken = true
                local Game = {new = function(c) if broken then error('the game is not ready') end; return FakeGame.new(c, {turn = 1, gold = 6000, income = 0, built = {}}) end,
                              load = function() return {} end, save = function() end}
                local mods = {tww3_mtb_ship = Ship, tww3_mtb_crew_model = CM, tww3_mtb_ship_config = config, tww3_mtb_ship_ui_config = cfg,
                              tww3_mtb_ship_ui = UI, tww3_mtb_ship_uic = Uic, tww3_mtb_game = Game}
                local function load(n) return mods[n] end
                local r = {}
                r.first = Screen.start(load)
                r.first_open = Screen.open()
                broken = false
                r.second = Screen.start(load)
                r.opened = Screen.open()
                r.made = Screen.ui.count
                r.advisor_hidden = not advisor.visible
                r.hud_hidden = not radar.visible
                r.timers = count(timers)
                local ui = Screen.ui
                Screen.hover('mtb_tree_node_0')
                local tip = Screen.panel.view.tree[1].info.tip
                r.tip_shown = tip.visible == true
                Screen.close()
                r.closed_hidden = Screen.root.uic.visible == false and Screen.is_open() == false
                r.tip_after_close = tip.visible
                r.advisor_back = advisor.visible
                r.hud_back = radar.visible
                r.listeners_after_close = count(listeners)
                r.timers_after_close = count(timers)
                local before = 0
                for _, n in pairs(E.calls) do before = before + n end
                r.reopened = Screen.open()
                r.reopen_calls = -before
                for _, n in pairs(E.calls) do r.reopen_calls = r.reopen_calls + n end
                r.same = Screen.ui == ui and Screen.ui.count == r.made + (ui.count - r.made)
                r.reused = Screen.reused
                r.shown_again = Screen.root.uic.visible == true
                r.timers_again = count(timers)
                Screen.destroy()
                return r
            end)
            UIComponent, core, cm, find_uicomponent = saved.UIComponent, saved.core, saved.cm, saved.find_uicomponent
            if not ok then error(res) end
            return res
        end""")
        try:
            r = py(screen(Screen, UI, Uic, Ship, CM, FakeGame, FakeUIC, config, cfg, lprops))
            want = {"first": False, "first_open": False, "second": True, "opened": True, "advisor_hidden": True, "tip_shown": True, "closed_hidden": True,
                    "tip_after_close": False, "advisor_back": True, "hud_hidden": True, "hud_back": True, "listeners_after_close": 0, "timers_after_close": 0, "reopened": True, "reused": True,
                    "shown_again": True}
            bad = [f"{k}: {r.get(k)!r}, expected {v!r}" for k, v in want.items() if r.get(k) != v]
            if r.get("timers_again") != r.get("timers"):
                bad.append(f"timers after the reopen {r.get('timers_again')}, at the first open {r.get('timers')}")
            total_diffs += len(bad)
            show(f"the screen (src/tww3_mtb_ship_screen.lua): a failed start, open, hover, close, reopen: {len(bad)} problems, {r.get('made')} components at the opening, "
                 f"{r.get('reopen_calls')} calls into the game's UIComponent to show it again", bad)
        except lupa51.LuaError as e:
            total_diffs += 1
            print(f"the screen failed: {e}")
    if opened:
        made = max(o[0] for o in opened)
        print(f"opening: at most {made} components, {max(o[1] for o in opened) / max(1, made):.1f} calls each into the game's UIComponent "
              f"({max(o[2] for o in opened):.2f} s of the drawing's own Lua here)")
    print(f"ui layout ({lua.eval('_VERSION')}, {'src' if args.src else 'pack'}): {len(summary)} states, {total_rows} components and {total_fields} fields compared "
          f"with the page; the game's text measures {'of ' + str(run) + ' (' + str(len(exact)) + ' texts)' if exact else 'not found (no session): step 3 skipped'}; "
          f"{total_diffs} differences; accepted on purpose: {len(ACCEPTED)} rules ({time.time() - started:.0f} s)")
    if kinds:
        print("    by kind: " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))
    for _, f, why in ACCEPTED:
        print(f"    accepted {f}: {why}")
    return 1 if total_diffs else 0


if __name__ == "__main__":
    sys.exit(main())
