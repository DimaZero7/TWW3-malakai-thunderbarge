"""The engine questions of docs/design/port-to-game.md, stage 1 (section 5, items 1-11, and 12-14 of the port's logic), answered in one unattended game.
Item 12 ends ONE turn (hard limit END_TURN_LIMIT); it comes after every item that needs no turn end and before the risky 6b and 9.

  py -3.14 tools/crew_cycle.py session port_probe --dry-run     everything but the game: checks, config, pack, Lua against a fake game, the plan
  py -3.14 tools/crew_cycle.py session port_probe               the run (only with the author's permission, CLAUDE.md «Общая игра»)
      --small              1280x720 instead of 1920x1080 (item 11 then measures that root, not 1080p)
      --limit N            hard limit of the whole session in seconds (default 3600)
      --stash-user-pack    the author's tww3_mtb_campaign.pack in data/ is moved aside for the run and put back after (tools/modular_test.py's
                           stash, hash checked). Only with the author's yes: without it the run refuses while his pack is there.

Answers: <run>/port_probe.jsonl (one JSON line per item, flushed at once; the last line says how the probe ended), <run>/port_probe_summary.txt,
pictures <run>/pp*.png. The run folder is build/campaign/runs/<time>-port_probe; build/port_probe/last_run.txt names it.

The launch goes through tools/run_game.py (its lock, closing of the game it started, the user's files restored) with this folder's pack
(build/port_probe/pack: the test remote with the probe's layouts + the built campaign pack), the lock line «mtb, начало HH:MM» and a docker
container alone not counted as busy (tools/crew_session.py). The probe Lua is tools/tests/port_probe.lua, sent through tools/rc.py.
"""
import argparse
import json
import shutil
import struct
import subprocess
import sys
import time
import zlib
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
TOOLS = REPO / "tools"
TESTS = TOOLS / "tests"
sys.path.insert(0, str(TOOLS))
import shared_game as sg  # noqa: E402  (the shared game's paths: one place)
OUT =REPO / "build" / "port_probe"
PACK = OUT / "pack"
CONFIG = OUT / "config.json"
LUA_FILE = TESTS / "port_probe.lua"
CAMPAIGN_PACK_DIR = REPO / "build" / "campaign" / "pack"
TREE = REPO / "web" / "data" / "tree_design.json"
PREFIX = "wh3_dlc25_dwarf_spirit_of_grungni_"
HULL_CHAIN = "wh3_dlc25_dwf_spirit_of_grungni_main_chain"
HIDDEN_CHAINS = {"wh3_dlc25_dwf_spirit_of_grungni_army_ability_1"}
SIDE_SET = "wh3_main_secondary_core_generic_horde"
FACTION_KEY = "wh3_dlc25_dwf_malakai"
SEP = chr(92)
DEFAULT_LIMIT = 3600
END_TURN_LIMIT = 480     # item 12: the turn end is the slowest and least sure step; after this the next items still run if the map answers
# Per item: seconds before the item is cut off (its steps stop, the next item goes on).
BUDGET = {"0": 60, "7": 120, "8": 150, "10": 60, "6a": 60, "5": 60, "11": 90, "setup": 60, "1": 240, "2": 240, "3": 90, "4": 900, "12": END_TURN_LIMIT + 240, "13": 120, "14": 60, "6b": 90, "9": 90}
RISKY = {"6b": "a game template (ui/templates/listview) instantiated in our layout",
         "9": "a game template with the game's own bindings (ui/templates/building_frame) given a context by script"}
UI_STRINGS = ["Дух Грунгни", "Постройки", "Корабль", "Экипаж", "Всё дерево", "Вблизи", "Казна: 12 345", "Закажите первую постройку — Заготовка под корабль",
              "Нужно: Корпус II, Пивной чертог", "Уже строится", "Не хватает золота", "+5%", "−30%", "2 500", "3 хода", "+N"]


def lua_literal(v):
    """A Lua 5.1 constant for a JSON-like value. Strings stay UTF-8; control bytes and quotes are escaped."""
    if v is None:
        return "nil"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        out = []
        for ch in v:
            if ch in "\\\"":
                out.append("\\" + ch)
            elif ord(ch) < 32:
                out.append("\\%03d" % ord(ch))
            else:
                out.append(ch)
        return '"' + "".join(out) + '"'
    if isinstance(v, (list, tuple)):
        return "{" + ",".join(lua_literal(x) for x in v) + "}"
    if isinstance(v, dict):
        return "{" + ",".join(f"[{lua_literal(str(k))}]={lua_literal(x)}" for k, x in v.items()) + "}"
    raise TypeError(type(v))


def lua_lib():
    text = LUA_FILE.read_text(encoding="utf-8")
    return text.rsplit("return 'ready'", 1)[0]


# ---------------------------------------------------------------- config: what the built pack has ----------------------------------------------------------------

def _decode_tables(files, layouts, names):
    import dbtable
    out = {}
    for name, blob in files.items():
        parts = name.split(SEP)
        if len(parts) == 3 and parts[0] == "db" and parts[1].removesuffix("_tables") in names:
            t = parts[1].removesuffix("_tables")
            out.setdefault(t, []).extend(dbtable.decode(blob, [tuple(f) for f in layouts[t]["fields"]]))
    return out


def make_config():
    """From the built campaign pack (the data developer's output) and the game's db.pack: the levels with several required rows,
    side chains to fill slots with, the hull's top level, costs, the slot cap; the author's tree for texts and the panel picture."""
    import dbtable
    import gamepack
    import pfh5
    layouts = json.loads((REPO / "data" / "db_layouts.json").read_text(encoding="utf-8"))
    names = {"building_levels", "building_level_required_buildings", "building_chain_set_items", "military_force_type_horde_details"}
    manifest = json.loads((CAMPAIGN_PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    pack_path = CAMPAIGN_PACK_DIR / manifest["packs"]["campaign"]
    files, _ = pfh5.read_pack(pack_path.read_bytes())
    mod = _decode_tables(files, layouts, names)
    stock = {}
    notes = []
    for name, blob in gamepack.entries(gamepack.DATA / "db.pack", lambda n: n.count(SEP) == 2 and n.split(SEP)[1].removesuffix("_tables") in names):
        t = name.split(SEP)[1].removesuffix("_tables")
        version = dbtable.header(blob)[1]
        if version != layouts[t]["version"]:
            notes.append(f"{t}: game version {version}, layout {layouts[t]['version']}: not read")
            continue
        stock.setdefault(t, []).extend(dbtable.decode(blob, [tuple(f) for f in layouts[t]["fields"]]))
    levels = {r["level_name"]: r for r in stock.get("building_levels", []) if r["level_name"].startswith(PREFIX)}
    levels.update({r["level_name"]: r for r in mod.get("building_levels", [])})
    required = {}
    for r in stock.get("building_level_required_buildings", []) + mod.get("building_level_required_buildings", []):
        required.setdefault(r["building_level"], [])
        if r["required"] not in required[r["building_level"]]:
            required[r["building_level"]].append(r["required"])
    side_chains = {r["chain"] for r in stock.get("building_chain_set_items", []) + mod.get("building_chain_set_items", []) if r["set"] == SIDE_SET and not r["remove"]}
    by_chain = {}
    for r in levels.values():
        by_chain.setdefault(r["chain"], []).append(r)
    for rows in by_chain.values():
        rows.sort(key=lambda r: r["level"])

    def prev_of(key):
        r = levels.get(key)
        if not r:
            return None
        lower = [x for x in by_chain[r["chain"]] if x["level"] == r["level"] - 1]
        return lower[0]["level_name"] if lower else None

    hull_rows = by_chain.get(HULL_CHAIN, [])
    hull_top = hull_rows[-1]["level_name"] if hull_rows else PREFIX + "airship_hull_5"
    candidates = []
    for key, parents in required.items():
        if len(parents) < 2 or key not in levels:
            continue
        hull_parents = [p for p in parents if levels.get(p, {}).get("chain") == HULL_CHAIN]
        candidates.append({"key": key, "parents": [p for p in parents if p not in hull_parents], "hull_parents": hull_parents, "prev": prev_of(key),
                           "chain": levels[key]["chain"], "tier": levels[key]["primary_slot_building_building_level_requirement"],
                           "cost": levels[key]["create_cost"], "turns": levels[key]["create_time"], "dev": levels[key]["development_point_cost"]})
    # one with two rows and one with three or more, parents not of the hull, the lowest tier first
    candidates.sort(key=lambda c: (len(c["hull_parents"]) > 0, c["tier"], -len(c["parents"])))
    chosen = []
    for want in (2, 3):
        pick = next((c for c in candidates if len(c["parents"]) >= 2 and (len(c["parents"]) == want or (want == 3 and len(c["parents"]) > 3)) and c not in chosen), None)
        if pick:
            chosen.append(pick)
    used_chains = {c["chain"] for c in chosen} | {levels[p]["chain"] for c in chosen for p in c["parents"] + ([c["prev"]] if c["prev"] else []) if p in levels}
    tree_names = {}
    if TREE.exists():
        for n in json.loads(TREE.read_text(encoding="utf-8"))["nodes"]:
            tree_names[PREFIX + (n["id"] if n["id"].startswith(("mtb_", "airship_hull_", "support_radius_")) else "mtb_" + n["id"])] = n.get("name", n["id"])
    # 13: a dependent level D (first of its chain) with one required row R1, where R1's own chain has a next level R2 that replaces it.
    pairs = []
    for key, parents in required.items():
        d = levels.get(key)
        if not d or len(parents) != 1 or d["level"] != 0 or d["chain"] in used_chains:
            continue
        r1 = levels.get(parents[0])
        if not r1 or r1["chain"] in used_chains or r1["chain"] == HULL_CHAIN:
            continue
        r2 = [x for x in by_chain[r1["chain"]] if x["level"] == r1["level"] + 1]
        if r2:
            pairs.append({"dependent": key, "dependent_name": tree_names.get(key), "r1": r1["level_name"], "r1_name": tree_names.get(r1["level_name"]),
                          "r2": r2[0]["level_name"], "r2_turns": r2[0]["create_time"], "r1_level": r1["level"], "dependent_chain": d["chain"], "r_chain": r1["chain"]})
    # the data developer's example first: «Склад оружия» needs «Пивной чертог I», which «Пивной чертог II» replaces
    pairs.sort(key=lambda p: (p["dependent_name"] != "Склад оружия", p["r1_level"] != 0, p["r2_turns"] != 1, p["dependent"]))
    pair = pairs[0] if pairs else None
    # 12: the cheapest one-turn first level of the author's tree with no requirement, of a chain nobody else uses
    busy_chains = used_chains | ({pair["dependent_chain"], pair["r_chain"]} if pair else set())
    turn_cands = [r for r in levels.values() if r["level"] == 0 and r["create_time"] == 1 and r["chain"] not in busy_chains and r["chain"] != HULL_CHAIN
                  and r["chain"] in side_chains and r["level_name"].startswith(PREFIX + "mtb_") and not required.get(r["level_name"]) and r["visible_in_ui"]]
    turn_cands.sort(key=lambda r: (r["create_cost"], r["level_name"]))
    one_turn = ({"key": turn_cands[0]["level_name"], "name": tree_names.get(turn_cands[0]["level_name"]), "cost": turn_cands[0]["create_cost"], "chain": turn_cands[0]["chain"]}
                if turn_cands else None)
    if one_turn:
        busy_chains.add(one_turn["chain"])
    fillers = []
    for chain, rows in sorted(by_chain.items(), key=lambda kv: (not kv[0].startswith("mtb_") and not kv[1][0]["level_name"].startswith(PREFIX + "mtb_"), kv[0])):
        if chain == HULL_CHAIN or chain in HIDDEN_CHAINS or chain not in side_chains or (chain in busy_chains and not (pair and chain == pair["r_chain"])):
            continue
        first = rows[0]
        if not first["visible_in_ui"]:
            continue
        fillers.append({"key": first["level_name"], "chain": chain, "cost": first["create_cost"], "turns": first["create_time"], "dev": first["development_point_cost"],
                        "tier": first["primary_slot_building_building_level_requirement"]})
    # R1 of item 13 is the first filler: item 2 stands it while filling the slots, so item 12/13 need no slot of their own for it
    if pair:
        r1 = [f for f in fillers if f["key"] == pair["r1"]]
        fillers = r1 + [f for f in fillers if f["key"] != pair["r1"] and f["chain"] != pair["r_chain"]]
    # 14: rows of building_effects_junction written as 0 (stock lines switched off): which buildings carry them
    zero_rows = []
    for name, blob in files.items():
        parts = name.split(SEP)
        if len(parts) == 3 and parts[1] == "building_effects_junction_tables":
            for r in dbtable.decode(blob, [tuple(f) for f in layouts["building_effects_junction"]["fields"]]):
                if r["value"] == 0:
                    zero_rows.append({"building": r["building"], "effect": r["effect"], "scope": r["effect_scope"]})
    horde = [r for r in mod.get("military_force_type_horde_details", []) if r["force_type"] == "MALAKAI_BOUND_HORDE"] or \
            [r for r in stock.get("military_force_type_horde_details", []) if r["force_type"] == "MALAKAI_BOUND_HORDE"]
    tree = json.loads(TREE.read_text(encoding="utf-8")) if TREE.exists() else {"nodes": []}
    nodes = [{"id": n["id"], "col": n.get("col", 0), "row": n.get("row", 0), "name": n.get("name", n["id"])} for n in tree["nodes"]]
    effects = []
    for n in tree["nodes"]:
        for e in n.get("effects", []):
            if e.get("text") and e["text"] not in effects:
                effects.append(e["text"])
    descriptions = [n["description"] for n in tree["nodes"] if n.get("description")][:4]
    cfg = {
        "made": datetime.now().isoformat(timespec="seconds"),
        "campaign_pack": {"path": str(pack_path), "bytes": pack_path.stat().st_size, "mtime": datetime.fromtimestamp(pack_path.stat().st_mtime).isoformat(timespec="seconds")},
        "slot_cap": horde[0]["slot_cap"] if horde else None,
        "hull_top": hull_top,
        "hull_levels": [r["level_name"] for r in hull_rows],
        "requires": {"rows_in_pack": sum(len(v) for v in required.values()), "multi_levels": len(candidates), "candidates": chosen,
                     "all_multi": [{"key": c["key"], "parents": c["parents"], "hull_parents": c["hull_parents"]} for c in candidates]},
        "fillers": fillers,
        "side_chains": len([c for c in by_chain if c in side_chains and c not in HIDDEN_CHAINS and c != HULL_CHAIN]),
        "texts": {"names": [n["name"] for n in nodes], "effects": effects[:16], "descriptions": descriptions, "ui": UI_STRINGS},
        "nodes": nodes,
        "turn": {"one_turn": one_turn, "pair": pair, "pairs": len(pairs)},
        "zero_effects": zero_rows,
        "notes": notes,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return cfg


# ---------------------------------------------------------------- the pack ----------------------------------------------------------------

def _png(rgb, w=8, h=8):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def probe_layouts():
    """{pack path: bytes}: the probe's own layouts and solid pictures under ui/tww3_mtb_pp/. Made with tools/crew_ui.py's writer, the format of the old panel's layouts."""
    import crew_ui as cu
    d = "ui/tww3_mtb_pp/"
    out = {}

    def put(name, text):
        out[f"ui{SEP}tww3_mtb_pp{SEP}{name}.twui.xml"] = text.encode("utf-8")
    for colour, rgb in (("red", (255, 0, 0)), ("green", (0, 255, 0)), ("black", (0, 0, 0))):
        out[f"ui{SEP}tww3_mtb_pp{SEP}{colour}.png"] = _png(rgb)
        put("pp_" + colour, cu.image_layout("pp_" + colour, d + colour + ".png"))
    zone = cu.layout("pp_zone", "zone", {}, [cu.state_xml("regular", "pp_zone", 64, 64, [], interactive=False)], "regular")
    put("pp_zone", zone)
    clip = cu.layout("pp_clip", "zone", {}, [cu.state_xml("regular", "pp_clip", 64, 64, [], interactive=False)], "regular")
    if 'id="zone" ' not in clip:
        raise SystemExit("crew_ui.layout changed: the clip attribute has no place")
    put("pp_clip", clip.replace('id="zone" ', 'id="zone" clipchildren="true" ', 1))
    img = {n: cu.guid("pp_button", "image", n) for n in ("normal", "hover")}
    states = [cu.state_xml("active", "pp_button", 120, 80, [(img["normal"], None, False)], {0: "hover"}),
              cu.state_xml("hover", "pp_button", 120, 80, [(img["hover"], None, False)], {1: "active"})]
    put("pp_button", cu.layout("pp_button", "button", {"normal": d + "red.png", "hover": d + "green.png"}, states, "active"))
    for key, cat, size, align, wrap, valign in (("pp_text_title", "header_24_bold", 24, "Center", "Never split", "Center"),
                                                ("pp_text_head", "header_18_bold", 18, None, "Never split", "Center"),
                                                ("pp_text_name", "header_14", 14, None, "Never split", "Center"),
                                                ("pp_text_line", "body_12", 12, None, "Never split", "Center"),
                                                ("pp_text_body", "body_12", 12, None, None, "Top")):
        put(key, cu.text_layout(key, cat, size, cu.TEXT_LIGHT, align, wrap, leading=2 if wrap is None else 1, valign=valign))
    return out


def build_pack():
    """build/port_probe/pack: tww3_mtb_harness.pack = the test remote of src/ for the three modes + the probe's layouts;
    tww3_mtb_campaign.pack copied from build/campaign/pack (the data developer's build, not changed)."""
    import pfh5
    manifest = json.loads((CAMPAIGN_PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    remote = (REPO / "src" / "tww3_mtb_remote.lua").read_bytes()
    files = {f"script{SEP}{m}{SEP}mod{SEP}tww3_mtb_remote.lua": remote for m in ("frontend", "campaign", "battle")}
    files.update(probe_layouts())
    PACK.mkdir(parents=True, exist_ok=True)
    harness = manifest["packs"]["harness"]
    campaign = manifest["packs"]["campaign"]
    blob = pfh5.pack_files(files)
    pfh5.read_pack(blob)
    (PACK / harness).write_bytes(blob)
    shutil.copy2(CAMPAIGN_PACK_DIR / campaign, PACK / campaign)
    (PACK / "manifest.json").write_text(json.dumps({"packs": {"harness": harness, "campaign": campaign}}, indent=1), encoding="utf-8")
    return {"harness": harness, "harness_files": sorted(files), "campaign": campaign, "campaign_bytes": (PACK / campaign).stat().st_size}


# ---------------------------------------------------------------- the checks before a launch ----------------------------------------------------------------

def checks():
    """[(what, ok, blocking, detail)]: CLAUDE.md «Общая игра с TWW3-batle-ai» and what tools/run_game.py would stop on."""
    import run_game as rg
    import run_battle as rb
    import hashlib
    out = []
    out.append(("no Warhammer3.exe in tasklist", not rb.game_running(), True, "tasklist /FI IMAGENAME eq Warhammer3.exe"))
    for what, path in sg.marks():
        out.append((f"no {what}", not path.exists(), True, str(path)))
    out.append(("the neighbour's state folder exists (our lock goes there; not created by us)", sg.NEIGHBOUR_STATE.is_dir(), True, str(sg.NEIGHBOUR_STATE)))
    try:
        busy = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True, timeout=30).stdout.strip()
        out.append(("docker ps empty (not blocking: crew_session.py rule, 02.11.2026; this probe needs no GPU training)", not busy, False, busy[:80] or "empty"))
    except (OSError, subprocess.TimeoutExpired) as e:
        out.append(("docker ps", True, False, f"not run: {e}"))
    out.append(("no other test session (build/campaign/session.json)", not rg.STATE.exists(), True, str(rg.STATE)))
    out.append(("no leftover files of an earlier run (build/installed.json)", not rb.MARKER.exists(), True, str(rb.MARKER)))
    out.append(("no copy of the user's folders from an interrupted run", not rg.BACKUP.exists(), False, f"{rg.BACKUP}: run_game.py restores it first"))
    out.append(("no mod list of ours in the game folder", not (rb.GAME / rb.MODLIST_NAME).exists(), True, str(rb.GAME / rb.MODLIST_NAME)))
    manifest_path = PACK / "manifest.json" if (PACK / "manifest.json").exists() else CAMPAIGN_PACK_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for kind, name in manifest["packs"].items():
        in_data = rb.GAME / "data" / name
        ours = PACK / name if (PACK / name).exists() else CAMPAIGN_PACK_DIR / name
        if in_data.exists():
            same = hashlib.sha256(in_data.read_bytes()).hexdigest() == hashlib.sha256(ours.read_bytes()).hexdigest()
            out.append((f"data/{name} is not another pack (the author's playtest pack)", same, True,
                        f"{in_data} {in_data.stat().st_size} bytes, {datetime.fromtimestamp(in_data.stat().st_mtime):%d.%m.%Y %H:%M}: " +
                        ("the same as ours, stays" if same else "another one: run_game.py stops. The author must agree to --stash-user-pack, or take it out himself")))
        else:
            out.append((f"data/{name} free", True, True, "not there"))
    used = (rb.GAME / "used_mods.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    dirs = [l.split('"')[1] for l in used if l.startswith("add_working_directory") and '"' in l]
    found = [d for d in dirs if (Path(d) / "memreader_plus.pack").exists()]
    out.append(("memreader_plus.pack in a folder of used_mods.txt (read only)", bool(found), True, found[0] if found else "not found"))
    prefs = rb.PREFS.read_bytes().decode("latin-1") if rb.PREFS.exists() else ""
    gpu = next((l for l in prefs.splitlines() if l.startswith("gfx_gpu ")), "")
    out.append(("the game's GPU setting is the RTX", "RTX" in gpu, True, gpu[:80]))
    scale = next((l.split(";")[0] for l in prefs.splitlines() if l.startswith("ui_scale ")), "?")
    out.append(("ui_scale of the user (not changed; at 1080p the game clamps it)", True, False, scale))
    return out


# ---------------------------------------------------------------- the probe's steps ----------------------------------------------------------------

class ItemTimeout(Exception):
    pass


class Probe:
    """Runs the items. transport(code, wait) -> {"ok", "result"}; session: the crew_cycle Session (log, shot, battle helpers) or a fake."""

    def __init__(self, cfg, transport, session, run_dir, fake=False):
        self.cfg, self.send, self.s, self.dir, self.fake = cfg, transport, session, Path(run_dir), fake
        self.lib = lua_lib()
        self.item_end = None
        self.results = {}
        self.jsonl = self.dir / "port_probe.jsonl"
        self.api = {}
        self.healthy = True

    # -- plumbing
    def sleep(self, seconds):
        if not self.fake:
            time.sleep(seconds)

    def z(self, name, args=None, wait=20):
        self.s.check_time()
        if self.item_end and time.time() > self.item_end:
            raise ItemTimeout(f"item time over before {name}")
        code = self.lib + f"\nreturn _G.mtb_pp.run({lua_literal(name)}, {lua_literal(args or {})})"
        row = self.send(code, wait)
        if row.get("ok") is None:
            return {"ok": False, "timeout": True, "err": str(row.get("result")), "item": name}
        if not row.get("ok"):
            return {"ok": False, "err": str(row.get("result"))[:2000], "item": name}
        try:
            return json.loads(row["result"])
        except (TypeError, ValueError):
            return {"ok": False, "err": "not JSON", "raw": str(row.get("result"))[:2000], "item": name}

    def data(self, name, args=None, wait=20):
        r = self.z(name, args, wait)
        if not r.get("ok"):
            raise RuntimeError(f"{name}: {r.get('err') or r}")
        return r.get("data") or {}

    def write(self, record):
        with self.jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()

    def grab(self):
        """(w, h, BGRA) of the game window at the game's resolution, or None (fake run, no window)."""
        if self.fake:
            return None
        import capture
        import rc
        st = rc.state()
        capture.unminimize_behind(st["pid"])
        hwnd = capture.find_window(st["pid"])
        if not hwnd:
            return None
        w, h, px = capture.grab(hwnd)
        x, y = st.get("x_res", w), st.get("y_res", h)
        if w >= x and h >= y:
            px, w, h = capture.crop(w, px, x, y), x, y
        return w, h, px

    @staticmethod
    def colour(img, root, x, y, r=3):
        """Mean (R, G, B) around the UI point x, y (root units)."""
        if not img:
            return None
        w, h, px = img
        sx, sy = w / root[0], h / root[1]
        cx, cy = int(x * sx), int(y * sy)
        acc, n = [0, 0, 0], 0
        for yy in range(max(0, cy - r), min(h, cy + r + 1)):
            for xx in range(max(0, cx - r), min(w, cx + r + 1)):
                i = (yy * w + xx) * 4
                acc[0] += px[i + 2]
                acc[1] += px[i + 1]
                acc[2] += px[i]
                n += 1
        return [round(a / n) for a in acc] if n else None

    def shot(self, name):
        if self.fake:
            return
        try:
            self.s.shot(name)
        except Exception as e:     # a picture never stops an item
            self.s.log("shot failed", name, e)

    # -- one item: isolated, timed, written at once
    def item(self, no, title, fn):
        record = {"item": no, "title": title, "risky": RISKY.get(no), "status": "error", "answer": None, "started": time.strftime("%H:%M:%S")}
        begin = time.time()
        self.item_end = begin + BUDGET.get(no, 120) * (1 if not self.fake else 100)
        self.s.log("=== item", no, title)
        try:
            status, answer, data = fn()
            record.update(status=status, answer=answer, data=data)
        except ItemTimeout as e:
            record.update(status="timeout", answer=f"cut off after {BUDGET.get(no)} s: {e}")
        except TimeoutError as e:
            if "hard limit" not in str(e):      # a wait of the item's own (a mode not reached, a panel not opened): only this item
                record.update(status="error", answer=f"TimeoutError: {e}")
                self.shot(f"pp_failed_{no}")
            else:       # the session's hard limit: written, then up
                record.update(status="hard_limit", answer=str(e))
                record["seconds"] = round(time.time() - begin, 1)
                self.write(record)
                raise
        except Exception as e:      # one item's failure never loses the others
            record.update(status="error", answer=f"{type(e).__name__}: {str(e)[:600]}")
            self.shot(f"pp_failed_{no}")
        finally:
            self.item_end = None
        record["seconds"] = round(time.time() - begin, 1)
        try:
            h = self.z("health", wait=10)
            record["health_after"] = h.get("data") if h.get("ok") else {"err": h.get("err")}
            self.healthy = bool(h.get("ok") and h["data"].get("ui_root"))
        except TimeoutError:
            raise
        except Exception as e:
            record["health_after"] = {"err": str(e)}
            self.healthy = False
        try:
            self.z("clear", wait=10)
        except TimeoutError:
            raise
        except Exception:
            pass
        self.write(record)
        self.results[no] = record
        self.s.log("item", no, record["status"], str(record["answer"])[:300])
        return record

    # -- 0. the API
    def i0(self):
        d = self.data("api")
        self.api = d
        missing = [k for k, v in d.get("flags", {}).items() if not v]
        return "answered", f"{d.get('count')} methods; root {d.get('root')}, screen {d.get('screen')}; missing: {missing or 'none'}; scroll/clip methods: {d.get('scroll_or_clip') or 'none'}", d

    # -- 7. TextDimensions
    def i7(self):
        t = self.cfg["texts"]
        strings = t["ui"] + t["names"] + t["effects"][:10]
        styles = [{"layout": "pp_text_name"}, {"layout": "pp_text_title"}, {"layout": "pp_text_line"}]
        first = self.data("text", {"styles": styles, "strings": strings}, 40)
        body = self.data("text", {"styles": [{"layout": "pp_text_body", "wrap": 300, "height": 200}], "strings": t["descriptions"] + t["effects"][:6]}, 30)
        self.sleep(0.8)
        later = self.data("text_again", {}, 30)
        rows = first.get("rows", [])
        now_ok = [r for r in rows if isinstance(r.get("now"), list) and len(r["now"]) >= 2 and (r["now"][0] or 0) > 0]
        later_ok = [r for r in later.get("rows", []) if isinstance(r.get("later"), list) and len(r["later"]) >= 2 and (r["later"][0] or 0) > 0]
        status = "answered" if rows and (now_ok or later_ok) else "inconclusive"
        answer = (f"TextDimensions on our text: {len(now_ok)}/{len(rows)} non-zero at once; after a frame (body only) {len(later_ok)}/{len(later.get('rows', []))}; "
                  f"TextDimensionsForText: {'works' if any(isinstance(r.get('for_text'), list) for r in rows) else 'absent or failing'}")
        return status, answer, {"single_line": rows, "wrapped_first": body.get("rows"), "wrapped_later": later.get("rows")}

    # -- 8. 1500 components
    def i8(self):
        t0 = time.time()
        a = self.data("many", {"n": 1500}, 120)
        a["wall_s_with_rc"] = round(time.time() - t0, 2)
        t1 = time.time()
        b = self.data("many", {"n": 1500, "texts": True}, 120)
        b["wall_s_with_rc"] = round(time.time() - t1, 2)
        answer = (f"1500 images: create {a.get('create_cpu_s', 0):.2f} s cpu ({a.get('create_wall_s')} s wall, {a['wall_s_with_rc']} s with the remote's poll), destroy {a.get('destroy_cpu_s', 0):.2f} s; "
                  f"with every 5th a text: create {b.get('create_cpu_s', 0):.2f} s, destroy {b.get('destroy_cpu_s', 0):.2f} s")
        return "answered" if a.get("made") == 1500 else "inconclusive", answer, {"images": a, "mixed": b}

    # -- 10. opacity
    def i10(self):
        d = self.data("opacity")
        self.sleep(0.8)
        later = self.data("rects")
        img = self.grab()
        self.shot("pp10_opacity")
        root = d.get("root")
        out = {}
        for c in d.get("cases", []):
            r = later.get("op_" + c["name"]) if isinstance(later.get("op_" + c["name"]), dict) and "x" in later.get("op_" + c["name"]) else c["rect"]
            out[c["name"]] = {"rgb": self.colour(img, root, r["x"] + r["w"] / 2, r["y"] + r["h"] / 2), "opacity": c.get("opacity"), "ok": c.get("ok"), "err": c.get("err")}
        d["pixels"] = out
        if not img:
            return "inconclusive", "no picture (fake run or no window): Opacity() values only " + json.dumps({k: v["opacity"] for k, v in out.items()}), d

        def red(name):
            p = out.get(name, {}).get("rgb")
            return p[0] if p else None
        control = red("control")
        verdict = {}
        for name in ("self_128", "parent_128", "parent_128_children", "grand_0"):
            v = red(name)
            if v is None or not control or control < 150:
                verdict[name] = "unknown"
            elif v > control * 0.8:
                verdict[name] = "no effect"
            elif v < 25:
                verdict[name] = "hidden"
            else:
                verdict[name] = f"half ({v}/{control})"
        status = "answered" if control and control > 150 else "inconclusive"
        return status, f"red channel: control {control}; " + "; ".join(f"{k}: {v}" for k, v in verdict.items()), d

    # -- 6a. clipping
    def i6a(self):
        d = self.data("clip")
        self.sleep(0.8)
        later = self.data("rects")
        img = self.grab()
        self.shot("pp6_clip")
        moved = self.data("clip_move")
        self.sleep(0.8)
        img2 = self.grab()
        self.shot("pp6_clip_moved")
        root = d.get("root")
        cases = {}
        for i, c in enumerate(d.get("cases", []), 1):
            h = later.get(f"holder{i}") if isinstance(later.get(f"holder{i}"), dict) and "x" in later.get(f"holder{i}") else c["holder"]
            c["holder_later"] = h
            outside = {"left": (h["x"] - 20, h["y"] + h["h"] / 2), "right": (h["x"] + h["w"] + 20, h["y"] + h["h"] / 2),
                       "top": (h["x"] + h["w"] / 2, h["y"] - 20), "bottom": (h["x"] + h["w"] / 2, h["y"] + h["h"] + 20)}
            inside = (h["x"] + h["w"] / 2, h["y"] + h["h"] / 2)
            after_bottom = (h["x"] + h["w"] / 2, h["y"] + h["h"] - 12)   # the child moved up by 120: this part of the holder is empty then
            cases[c["layout"]] = {"inside": self.colour(img, root, *inside), "outside": {k: self.colour(img, root, *p) for k, p in outside.items()},
                                  "moved_inside_bottom": self.colour(img2, root, *after_bottom), "moved_inside_top": self.colour(img2, root, h["x"] + h["w"] / 2, h["y"] + 12)}
        d["moved"], d["pixels"] = moved, cases
        if not img:
            return "inconclusive", "no picture: bounds only", d

        def is_red(p):
            return p and p[0] > 170 and p[1] < 90

        def is_dark(p):
            return p and p[0] < 60 and p[1] < 60
        clip, plain = cases.get("pp_clip", {}), cases.get("pp_zone", {})
        clipped = is_red(clip.get("inside")) and all(is_dark(p) for p in clip.get("outside", {}).values())
        control = is_red(plain.get("inside")) and all(is_red(p) for p in plain.get("outside", {}).values())
        moved_ok = is_red(clip.get("moved_inside_top")) and is_dark(clip.get("moved_inside_bottom"))
        if not is_red(clip.get("inside")):
            return "inconclusive", "our red child is not seen inside the holder: something covers the test area (see pp6_clip.png)", d
        answer = (f"clipchildren in our layout: {'clips' if clipped else 'does NOT clip'} (control without it {'overflows as expected' if control else 'unexpected'}); "
                  f"content moved by SetDockOffset under the clipping holder: {'stays clipped' if moved_ok else 'not as expected'}. "
                  "The mouse wheel on our own container cannot be tested without real input")
        return "answered", answer, d

    # -- 5. mouse events
    def i5(self):
        setup = self.data("mouse_setup")
        steps = []
        for call, target in (("SimulateMouseOn", "button"), ("SimulateMouseOff", "button"), ("SimulateLClick", "button"), ("SimulateMouseOn", "plain"), ("SimulateMouseOff", "plain")):
            steps.append(self.data("mouse_do", {"call": call, "target": target}))
            self.sleep(0.5)
            if call == "SimulateMouseOn" and target == "button":
                self.shot("pp5_hover")
        got = self.data("mouse_read")
        events = got.get("events", [])
        seen = {(e["event"], e["id"]) for e in events}
        on = ("ComponentMouseOn", "pp_button") in seen
        off = ("ComponentMouseOff", "pp_button") in seen
        click = ("ComponentLClickUp", "pp_button") in seen
        plain_on = ("ComponentMouseOn", "pp_plain") in seen
        hover_state = steps[0].get("state")
        answer = (f"listeners registered: {setup.get('registered')}; synthetic: MouseOn {'reached Lua' if on else 'not seen'}, MouseOff {'reached Lua' if off else 'not seen'}, "
                  f"LClickUp {'reached Lua' if click else 'not seen'}; non-interactive image MouseOn {'seen' if plain_on else 'not seen'}; "
                  f"button state after SimulateMouseOn: {hover_state}. Real mouse input is not tested (no global input allowed); the game's tours rely on the same calls")
        return ("answered" if on or off else "inconclusive"), answer, {"setup": setup, "steps": steps, "events": events}

    # -- 11. the panel on the root as it is
    def i11(self):
        d = self.data("panel", {"nodes": self.cfg["nodes"], "title": "Дух Грунгни", "bottom": "Закажите первую постройку — Заготовка под корабль"})
        self.sleep(1.0)
        self.shot("pp11_panel")
        self.z("clear")
        crew = self.z("crew_panel", {"open": True})
        self.sleep(1.5)
        self.shot("pp11_old_crew_panel")
        self.z("crew_panel", {"open": False})
        d["old_crew_panel"] = crew.get("data") or crew.get("err")
        img = None if self.fake else True
        answer = f"root {d.get('root')} (screen {d.get('screen')}), panel {d.get('panel')}, frame {d.get('frame')}; pictures pp11_panel.png, pp11_old_crew_panel.png"
        return ("answered" if img else "inconclusive"), answer, d

    # -- setup for the building items
    def setup(self):
        d = self.data("setup", {"hull": self.cfg["hull_top"], "gold": 400000, "dev": 600}, 30)
        hull_now = d.get("hull_now")
        ok = hull_now == self.cfg["hull_top"]
        return ("answered" if ok else "inconclusive"), f"hull now {hull_now} (wanted {self.cfg['hull_top']}: {'raised by cm:add_building_to_force' if ok else 'NOT raised: tiers may block orders'}); gold {d.get('info', {}).get('gold')}, points {d.get('info', {}).get('dev')}", d

    # -- 1. several required rows: AND or OR
    def i1(self):
        cands = self.cfg["requires"]["candidates"]
        if not cands:
            return "inconclusive", (f"the built pack has {self.cfg['requires']['multi_levels']} levels with two or more rows in building_level_required_buildings "
                                    "(not counting hull parents): the data developer's tree is not built yet"), self.cfg["requires"]
        self.z("select")
        self.sleep(1.5)
        out = []
        for c in cands:
            res = {"key": c["key"], "parents": c["parents"], "prev": c["prev"], "phases": []}
            taken_at = None
            for label, place in (("none", []), ("one", c["parents"][:1]), ("all", c["parents"])):
                r = self.data("requires", {"key": c["key"], "prev": c["prev"], "place": place, "parents": c["parents"], "order": taken_at is None}, 30)
                present = sum(1 for v in (r.get("parents_present") or {}).values() if v)
                phase = {"phase": label, "present": present, "of": len(c["parents"]), "slot": r.get("slot"), "added": r.get("added"),
                         "reads": {x["expr"]: x["r"] for x in r.get("reads", [])}, "ordered": r.get("ordered")}
                active = [v.get("v") for k, v in phase["reads"].items() if "IsActiveForBuildingBrowser" in k and "char " in k]
                phase["browser_active"] = active[0] if active else None
                if taken_at is None and r.get("ordered") and r.get("slot") is not None:
                    self.sleep(1.5)
                    chk = self.data("check", {"key": c["key"], "slot": r["slot"], "gold_before": r.get("gold_before")})
                    phase["check"] = chk
                    if chk.get("accepted"):
                        taken_at = (label, present)
                res["phases"].append(phase)
            n = len(c["parents"])
            if taken_at is None:
                verdict = "refused even with every parent standing: something else blocks it (see reads)"
            elif taken_at[1] == 0:
                verdict = "the order command does not check the requirements at all (taken with none standing)"
            elif taken_at[1] < n:
                verdict = f"OR: taken with {taken_at[1]} of {n} parents"
            else:
                verdict = f"AND: refused with fewer, taken with all {n}"
            browser = [(p["phase"], p["present"], p["browser_active"]) for p in res["phases"]]
            res["verdict"], res["browser"] = verdict, browser
            out.append(res)
        answer = " | ".join(f"{r['key'].removeprefix(PREFIX)} ({len(r['parents'])} parents): {r['verdict']}; browser IsActive by parents standing {[(b[1], b[2]) for b in r['browser']]}" for r in out)
        status = "answered" if all("something else" not in r["verdict"] for r in out) else "inconclusive"
        return status, answer, {"candidates": out}

    # -- 2. 18 slots, an order into the 16th and later
    def i2(self):
        info = self.data("slots")
        res = {"start": info, "slot_cap_in_pack": self.cfg["slot_cap"], "adds": [], "orders": []}
        side = info["num_items"] - 1
        present = set(info["slots"])
        fillers = [f for f in self.cfg["fillers"] if f["key"] not in present]
        self.reserved = None
        guard = 0
        while guard < 30:
            guard += 1
            fe = self.data("first_empty")
            slot = fe.get("slot")
            if slot is None or slot >= 16:
                break
            if not fillers:
                res["note"] = f"not enough side chains to fill up to slot 16 (first empty {slot})"
                break
            f = fillers.pop(0)
            before = fe["info"]["side_occupied"]
            a = self.data("add", {"keys": [f["key"]]})
            res["adds"].append({"key": f["key"], "at": a["adds"][0]["r"].get("at"), "ok": a["adds"][0]["r"].get("ok"), "occupied": a["info"]["side_occupied"]})
            if a["info"]["side_occupied"] <= before:
                res.setdefault("not_taken", []).append(f["key"])
        for _ in range(1):      # the 16th side slot only; 17 and 18 stay for items 4 and 12 (item 4's order is the test of a later slot)
            fe = self.data("first_empty")
            slot = fe.get("slot")
            if slot is None or not fillers:
                break
            f = fillers.pop(0)
            o = self.data("order", {"key": f["key"], "slot": slot, "way": "own"})
            self.sleep(1.5)
            chk = self.data("check", {"key": f["key"], "slot": slot, "gold_before": o.get("gold_before")})
            res["orders"].append({"key": f["key"], "slot": slot, "order": o, "check": chk, "accepted": chk.get("accepted")})
        fe = self.data("first_empty")
        res["free_for_item4"] = fe.get("slot")
        self.reserved = {"slot": fe.get("slot"), "filler": fillers[0] if fillers else None}
        res["end"] = fe.get("info")
        orders = "; ".join(f"side slot {o['slot']}: {'taken' if o['accepted'] else 'REFUSED'}" for o in res["orders"]) or "no order made"
        answer = f"the horde reports {info['num_items']} slots in the list ({side} side), context Size {info.get('cco_size')}, pack slot_cap {self.cfg['slot_cap']}; {orders}"
        if res.get("note"):
            answer += "; " + res["note"]
        status = "answered" if res["orders"] and any(o["slot"] >= 16 for o in res["orders"]) else "inconclusive"
        if side < 16:
            status, answer = "answered", answer + f": there is no 16th side slot (only {side})"
        return status, answer, res

    # -- 3. the cost
    def i3(self):
        probe = (getattr(self, "reserved", None) or {}).get("filler") or (self.cfg["fillers"][-1] if self.cfg["fillers"] else None)
        if not probe:
            return "inconclusive", "no unbuilt level to read", {}
        built = None
        for o in (self.results.get("2", {}).get("data") or {}).get("orders", []):
            if o.get("accepted"):
                built = o["slot"]
                break
        slot = (getattr(self, "reserved", None) or {}).get("slot")
        runs = {}
        self.z("deselect")
        self.sleep(1.5)
        runs["not_selected"] = self.data("cost", {"key": probe["key"], "slot": slot, "built_slot": built}, 30)
        self.z("select")
        self.sleep(1.5)
        runs["selected"] = self.data("cost", {"key": probe["key"], "slot": slot, "built_slot": built}, 30)
        hits = {}
        for label, run in runs.items():
            for row in run.get("reads", []):
                v = row["r"].get("v")
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    if abs(v - probe["cost"]) < 0.5 and probe["cost"]:
                        hits.setdefault("cost", []).append(f"{label}: {row['expr']}")
                    if abs(v - probe["turns"]) < 0.5 and probe["turns"] and "Time" in row["expr"]:
                        hits.setdefault("turns", []).append(f"{label}: {row['expr']}")
        answer = (f"{probe['key'].removeprefix(PREFIX)} costs {probe['cost']} in the pack: readable by {hits.get('cost') or 'NO expression'}; "
                  f"turns {probe['turns']}: {hits.get('turns') or 'none'}")
        return ("answered" if hits.get("cost") else "inconclusive"), answer, {"probe": probe, "hits": hits, "runs": runs}

    # -- 4. an order right after a battle
    def i4(self):
        res = {"steps": []}
        fe = self.data("first_empty")
        slot = fe.get("slot")
        present = set(fe["info"]["slots"])
        # a level of two or more turns: still being built after item 12's turn end, so item 12 can cancel it and item 13 gets its slot
        free = [f for f in self.cfg["fillers"] if f["key"] not in present]
        key = next((f["key"] for f in free if f["turns"] >= 2), None) or next((f["key"] for f in free), None)
        if slot is None or not key:
            return "inconclusive", f"nothing to order after the battle (free slot {slot}, unbuilt side level {key})", res
        res["slot"], res["key"] = slot, key
        if self.fake:
            res["battle"] = "not simulated in the fake run"
        else:
            res["battle"] = self.battle()
            if res["battle"] != "back on the map":
                return "inconclusive", f"no battle: {res['battle']}", res
        back = time.time()

        def attempt(label, way, select=False, wait_before=0.0):
            if select:
                self.z("select")
            self.sleep(wait_before)
            o = self.data("order", {"key": key, "slot": slot, "way": way})
            self.sleep(1.5)
            chk = self.data("check", {"key": key, "slot": slot, "gold_before": o.get("gold_before")})
            step = {"step": label, "since_map_s": round(time.time() - back, 1), "order": o, "check": chk, "accepted": chk.get("accepted")}
            res["steps"].append(step)
            return step["accepted"]
        done = (attempt("own way at once, nothing selected", "own") or
                attempt("own way after SelectAndZoom(false) + 1.5 s", "own", select=True, wait_before=1.5) or
                attempt("stock way (SelectedCharacter) right after", "selected") or
                attempt("own way 3 s later", "own", wait_before=3.0))
        first = next((s["step"] for s in res["steps"] if s["accepted"]), None)
        answer = (f"slot {slot}: " + ("; ".join(f"{s['step']}: {'taken' if s['accepted'] else 'not taken'}" for s in res["steps"])) +
                  (f". First that worked: {first}" if done else ". None worked"))
        return ("answered" if not self.fake else "inconclusive"), answer, res

    def battle(self):
        """A real campaign battle as tools/crew_cycle.py fights them: spawned goblins, attack, deployment ended, enemies killed by script."""
        s = self.s
        s.log("spawn", s.script("spawn_fight.lua")["result"])
        try:
            s.open_panel()
        except TimeoutError as e:
            if "hard limit" in str(e):
                raise
            return f"the pre-battle panel did not open: {e}"
        s.log(s.click("button_attack"))
        s.wait_mode("battle", 300)
        time.sleep(4)
        s.plain("bm:end_current_battle_phase(); return 1", 5)
        time.sleep(3)
        s.log(s.script("battle_kill_enemy.lua")["result"])
        for attempt in range(25):
            if s.visible("button_dismiss_results") != "-":
                break
            if attempt == 8:
                s.plain("bm:end_battle(); return 1", 5)
            time.sleep(3)
        s.log(s.click("button_dismiss_results"))
        s.wait_mode("campaign", 300)
        time.sleep(4)
        if not s.back_on_map():
            return "not back on the campaign map"
        return "back on the map"

    # -- 14. a building_effects_junction row written as 0: still in the level's effect list?
    def i14(self):
        rows = self.cfg.get("zero_effects") or []
        if not rows:
            return "inconclusive", "the built pack has no building_effects_junction row with value 0", {}
        keys = sorted({r["building"] for r in rows})
        effects = sorted({r["effect"] for r in rows})
        d = self.data("effects", {"keys": keys, "effects": effects}, 40)
        zero = {(r["building"], r["effect"]) for r in rows}
        found = []
        for lv in d.get("levels", []):
            for row in lv.get("rows", []):
                if (lv["key"], row.get("Key")) in zero:
                    found.append(f"{lv['key'].removeprefix(PREFIX)}: {row.get('Key')} value {row.get('Value')} text {str(row.get('LocalisedText') or row.get('Description'))[:60]!r}")
        sizes = {lv["key"].removeprefix(PREFIX): (lv.get("size"), lv.get("nonzero")) for lv in d.get("levels", [])}
        if not any(lv.get("size") for lv in d.get("levels", [])):
            return "inconclusive", f"EffectList not readable on the level record (sizes {sizes})", d
        answer = (f"zero rows still in the level's EffectList: {found or 'none'}; (size, non-zero) per level {sizes}. The info panel's own list is filled by C++ "
                  "(CampaignEffectsListTooltip): it may hide what the list keeps; opening it needs the horde tab, which the probe does not touch")
        return "answered", answer, d

    # -- 12. events around a turn end, a cancel, a dismantle
    def end_turn(self):
        """The game's next turn, with a hard limit; True when the player's turn came back."""
        if self.fake:
            return self.s.safe_end_turn()
        self.s.prog("return P.peace()")
        try:
            self.s.safe_end_turn(limit=END_TURN_LIMIT)
            return True
        except TimeoutError as e:
            if "hard limit" in str(e):
                raise
            self.s.log("turn end not back in time:", e)
            return False

    def i12(self):
        t = self.cfg.get("turn") or {}
        b, pair = t.get("one_turn"), t.get("pair")
        res = {"one_turn": b, "pair": pair}
        self.pre13 = {}
        if not b:
            return "inconclusive", "no one-turn first level without requirements in the author's tree", res
        fe = self.data("first_empty")
        slot_b = fe.get("slot")
        present = fe["info"]["slots"]
        if slot_b is None:
            return "inconclusive", "no free slot for the one-turn building", res
        r_slot = present.index(pair["r1"]) if pair and pair["r1"] in present else None
        watch = [slot_b] + ([r_slot] if r_slot is not None else [])
        res["events_on"] = self.data("events_on", {"watch": watch})
        self.slot_b = slot_b
        if pair and r_slot is not None:
            # 13's control, while slot_b is still empty: the dependent's availability with R1 standing
            self.pre13["with_r1"] = self.data("avail", {"key": pair["dependent"], "slot": slot_b, "r1": pair["r1"], "r2": pair["r2"]})
        self.data("events_mark", {"text": "orders"})
        o = self.data("order", {"key": b["key"], "slot": slot_b, "way": "own"})
        self.sleep(1.5)
        res["order_b"] = {"slot": slot_b, "order": o, "check": self.data("check", {"key": b["key"], "slot": slot_b, "gold_before": o.get("gold_before")})}
        if pair:
            if r_slot is not None:
                # R1 -> R2 by the game's command, finished by the same turn end (the real way a higher level replaces a lower one)
                o2 = self.data("order", {"key": pair["r2"], "slot": r_slot, "way": "own"})
                self.sleep(1.5)
                res["order_r2"] = {"slot": r_slot, "order": o2, "check": self.data("check", {"key": pair["r2"], "slot": r_slot, "gold_before": o2.get("gold_before")})}
            else:
                res["order_r2"] = f"{pair['r1']} is not standing (item 2 did not place it): no upgrade by order"
        mark = self.data("events_mark", {"text": "turn end"})["seq"]
        begin = time.time()
        back = self.end_turn()
        res["turn_end"] = {"back": back, "seconds": round(time.time() - begin, 1)}
        self.sleep(2)
        after = self.data("events_read", {"from": mark}, 40)
        res["turn_events"], res["noise"] = after.get("log"), after.get("noise")
        res["slots_after"] = after.get("slots")
        if not back and self.s.mode() != "campaign":
            return "inconclusive", f"the next turn did not come in {END_TURN_LIMIT} s and the map is not answering", res
        # a cancel: item 4's order (two turns or more) is still being built
        item4 = (self.results.get("4", {}).get("data") or {})
        cancel_slot = item4.get("slot") if any(s.get("accepted") for s in item4.get("steps", [])) else None
        if cancel_slot is None:
            for c in (self.results.get("1", {}).get("data") or {}).get("candidates", []):
                for p in c.get("phases", []):
                    if (p.get("check") or {}).get("accepted") and not c.get("prev"):
                        cancel_slot, item4 = p["slot"], {"key": c["key"]}
        if cancel_slot is not None:
            still = self.data("slot_read", {"slot": cancel_slot})
            if still.get("item"):
                m = self.data("events_mark", {"text": "cancel"})["seq"]
                c = self.data("cancel", {"key": item4.get("key"), "slot": cancel_slot})
                self.sleep(2)
                res["cancel"] = {"slot": cancel_slot, "command": c, "after": self.data("slot_read", {"slot": cancel_slot}), "events": self.data("events_read", {"from": m}).get("log")}
                self.free13 = cancel_slot
            else:
                res["cancel"] = f"slot {cancel_slot} is no longer being built: nothing to cancel"
        else:
            res["cancel"] = "no construction of two turns or more to cancel"
        # a dismantle by command of the one-turn building, now standing
        m = self.data("events_mark", {"text": "dismantle"})["seq"]
        dz = self.data("dismantle", {"slot": slot_b})
        self.sleep(2)
        res["dismantle"] = {"slot": slot_b, "command": dz, "events": self.data("events_read", {"from": m}).get("log")}
        self.data("events_off")
        # the verdict
        log = res["turn_events"] or []
        start = next((e for e in log if e["event"] == "FactionTurnStart"), None)
        done = [e for e in log if e["event"] in ("MilitaryForceBuildingCompleteEvent", "BuildingCompleted")]
        demolish = [e["event"] for e in log if "Demolish" in e["event"] or "Cancel" in e["event"]]

        def slot_state(e, n):
            for w in e.get("slots") or []:
                if isinstance(w, dict) and w.get("slot") == n:
                    return w.get("model")
            return None
        order_txt = "no FactionTurnStart of ours seen" if not start else (
            "no completion event seen" if not done else
            ("completion BEFORE FactionTurnStart" if all(e["seq"] < start["seq"] for e in done) else
             "completion AFTER FactionTurnStart" if all(e["seq"] > start["seq"] for e in done) else "completions on both sides of FactionTurnStart"))
        at_events = "; ".join(f"#{e['seq']} {e['event']} ({e['context'].get('building')}): slot {slot_b} = {str(slot_state(e, slot_b)).removeprefix(PREFIX)!r}" for e in done + ([start] if start else []))
        answer = (f"turn end {'came back' if back else 'NOT back'} in {res['turn_end']['seconds']} s; {order_txt}; at each: {at_events or '-'}; "
                  f"demolish/cancel-like events during the turn: {demolish or 'none'} (R1 -> R2 by order: {'taken' if isinstance(res.get('order_r2'), dict) and res['order_r2']['check'].get('accepted') else 'not taken'}); "
                  f"cancel fired {[e['event'] for e in (res['cancel'].get('events') or [])] if isinstance(res['cancel'], dict) else res['cancel']}; "
                  f"dismantle fired {[e['event'] for e in res['dismantle']['events'] or []] or 'nothing at once'} (dismantling {dz.get('dismantling')}; its end needs another turn, not ended)")
        return ("answered" if back and start and done else "inconclusive"), answer, res

    # -- 13. a requirement whose level was replaced by the next level of its own chain
    def i13(self):
        pair = (self.cfg.get("turn") or {}).get("pair")
        if not pair:
            return "inconclusive", "no dependent level with one required row whose chain has a next level", {}
        res = {"pair": pair, "with_r1": getattr(self, "pre13", {}).get("with_r1")}
        info = self.data("slots")
        if pair["r2"] not in info["slots"]:
            # R1 -> R2 by the turn did not happen: stand R2 by script, as the coordinator asked
            res["add_r2"] = self.data("add", {"keys": [pair["r2"]]})
            info = self.data("slots")
        res["r1_standing"], res["r2_standing"] = pair["r1"] in info["slots"], pair["r2"] in info["slots"]
        slot = getattr(self, "free13", None)
        fe = self.data("first_empty")
        if slot is None or (self.data("slot_read", {"slot": slot}).get("item")):
            slot = fe.get("slot")
        if slot is not None:
            res["with_r2"] = self.data("avail", {"key": pair["dependent"], "slot": slot, "r1": pair["r1"], "r2": pair["r2"]})
        else:       # no free slot: the reads that need none still count; IsActive against an occupied slot is false for another reason
            res["with_r2"] = self.data("avail", {"key": pair["dependent"], "slot": getattr(self, "slot_b", None) or 1, "r1": pair["r1"], "r2": pair["r2"]})
            res["with_r2"]["slot_occupied"] = True
        if slot is not None:
            o = self.data("order", {"key": pair["dependent"], "slot": slot, "way": "own"})
            self.sleep(1.5)
            res["order"] = {"slot": slot, "order": o, "check": self.data("check", {"key": pair["dependent"], "slot": slot, "gold_before": o.get("gold_before")})}

        def active(r):
            if not isinstance(r, dict):
                return None
            return next((x["r"].get("v") for x in r.get("reads", []) if x["expr"].startswith("char ") and "IsActiveForBuildingBrowser" in x["expr"]), None)
        taken = isinstance(res.get("order"), dict) and res["order"]["check"].get("accepted")
        ignores = "does not check" in str((self.results.get("1") or {}).get("answer"))
        answer = (f"{pair['dependent'].removeprefix(PREFIX)} needs {pair['r1'].removeprefix(PREFIX)}; standing now: R1 {res['r1_standing']}, R2 {res['r2_standing']} "
                  f"({'by the turn' if 'add_r2' not in res else 'by cm:add_building_to_force'}); browser IsActive with R1 {active(res['with_r1'])}, with R2 {active(res['with_r2'])}; "
                  f"order {'taken' if taken else 'refused' if slot is not None else 'not tried (no free slot)'}"
                  + ("; NOTE item 1 found the command does not check requirements, so only the browser read counts" if ignores else "")
                  + ("; NOTE no free slot: IsActive with R2 was read against an occupied slot, see AdditionalBuildingRequirementContext in the reads" if res["with_r2"].get("slot_occupied") else ""))
        ok = active(res["with_r2"]) is not None and not res["with_r2"].get("slot_occupied")
        return ("answered" if ok else "inconclusive"), answer, res

    # -- 6b (risky). the game's list template
    def i6b(self):
        d = self.data("listview", {"n": 30})
        self.sleep(0.8)
        self.shot("pp6b_listview")
        methods = [m for m in (self.api.get("scroll_or_clip") or []) if "lip" not in m]
        scroll = self.data("listview_scroll", {"methods": methods, "amount": 200})
        self.sleep(0.8)
        self.shot("pp6b_listview_moved")
        d["scroll"] = scroll
        slider = d.get("slider")
        answer = (f"listview in our layout: created; list_box {d.get('list_before')} -> {d.get('list_after')} after 30 rows, Layout(): {d.get('layout')}; "
                  f"its slider {'visible' if slider and slider.get('visible') else 'not visible'}; scroll methods tried {[t['method'] + ':' + str(t['ok']) for t in scroll.get('tried', [])] or 'none known'}. "
                  "The mouse wheel itself needs real input: not testable here (look at pp6b_listview*.png)")
        return ("answered" if not d.get("err") else "inconclusive"), answer, d

    # -- 9 (risky). building_frame with a context object
    def i9(self):
        key = None
        cands = self.cfg["requires"]["candidates"]
        if cands:
            key = cands[0]["key"]
        elif self.cfg["fillers"]:
            key = self.cfg["fillers"][0]["key"]
        info = self.data("slots")
        slot = next((i for i, k in enumerate(info["slots"]) if i > 0 and k), None)
        d = self.data("frame", {"key": key, "slot": slot}, 20)
        self.sleep(1.2)
        self.shot("pp9_building_frame")
        read = self.data("frame_read")
        d["read"] = read
        texts = [v.get("text") for f in read.values() if isinstance(f, dict) for v in f.values() if isinstance(v, dict) and v.get("text")]
        images = [v.get("image") for f in read.values() if isinstance(f, dict) for v in f.values() if isinstance(v, dict) and v.get("image")]
        filled = bool(texts or [i for i in images if "buildings" in str(i)])
        answer = (f"SetContextObject: {d.get('set')}; with a slot context on the parent: {d.get('slot_set')} / {d.get('second_set')}; "
                  f"template {'fills itself' if filled else 'stays empty'} (texts {texts[:4]}, images {images[:3]}); picture pp9_building_frame.png")
        return ("answered" if d.get("set") is True else "inconclusive"), answer, d

    # -- all of them
    def run(self):
        order = [("0", "API surface of UIComponent (no walk)", self.i0),
                 ("7", "TextDimensions on our own text", self.i7),
                 ("8", "time to create and destroy 1500 components", self.i8),
                 ("10", "SetOpacity on a nested layer", self.i10),
                 ("6a", "our own container with clipchildren clips its children", self.i6a),
                 ("5", "ComponentMouseOn / ComponentMouseOff reach Lua for our component", self.i5),
                 ("11", "the panel at the root of this resolution: bounds and pictures", self.i11),
                 ("14", "a building_effects_junction row set to 0: still in the level's effect list", self.i14),
                 ("setup", "gold, points, the hull raised to its top", self.setup),
                 ("1", "several building_level_required_buildings rows on a level: AND or OR", self.i1),
                 ("2", "slot capacity 18 and an order into the 16th+ slot", self.i2),
                 ("3", "reading a building's cost, Malakai selected and not", self.i3),
                 ("4", "an order right after a battle, retry after re-selecting", self.i4),
                 ("12", "event order at a turn start, on a cancel and a dismantle; the slot at each event", self.i12),
                 ("13", "a requirement whose level was replaced by the next level of its chain", self.i13),
                 ("6b", "the game's list template in our layout: clipping, slider, wheel", self.i6b),
                 ("9", "SetContextObject on ui/templates/building_frame", self.i9)]
        how = "completed"
        try:
            for no, title, fn in order:
                if no in RISKY and not self.healthy:
                    self.write({"item": no, "title": title, "status": "skipped", "answer": "the UI was not healthy after the previous item"})
                    continue
                if no in ("12", "13", "6b", "9") and not self.fake and self.s.mode() != "campaign":
                    self.write({"item": no, "title": title, "status": "skipped", "answer": "not on the campaign map (after item 4)"})
                    continue
                self.item(no, title, fn)
        except TimeoutError as e:
            how = f"hard limit: {e}"
        except Exception as e:
            how = f"error: {type(e).__name__}: {e}"
        return how

    def summary(self, how):
        lines = [f"port probe {datetime.now():%d.%m.%Y %H:%M}, ended: {how}"]
        for no, r in self.results.items():
            lines.append(f"[{no}] {r['status']:<12} {r['title']}: {r['answer']}")
        text = "\n".join(lines)
        (self.dir / "port_probe_summary.txt").write_text(text + "\n", encoding="utf-8")
        return text


# ---------------------------------------------------------------- the fake game (dry run, Lua 5.1 through lupa under Python 3.10) ----------------------------------------------------------------

FAKE_GAME = r"""
local reg, n_addr, listeners = {}, 0, {}
local U = {}
U.__index = U
local function new(id, parent, path)
  n_addr = n_addr + 1
  local u = setmetatable({_id = id, _kids = {}, _parent = parent, _x = 0, _y = 0, _w = 64, _h = 64, _op = 255, _state = 'active', _text = '', _vis = true, _addr = 'a' .. n_addr, _path = path}, U)
  reg[u._addr] = u
  if parent then parent._kids[#parent._kids + 1] = u end
  return u
end
function UIComponent(addr) local u = reg[addr]; if not u then error('bad address ' .. tostring(addr)) end; return u end
function U:Id() return self._id end
function U:CreateComponent(id, path)
  assert(type(id) == 'string' and type(path) == 'string', 'CreateComponent args')
  if self._dead then error('dead parent') end
  local u = new(id, self, path)
  if string.find(path, 'listview', 1, true) then local c = new('list_clip', u); new('list_box', c); new('vslider', u) end
  if string.find(path, 'building_frame', 1, true) then local k = new('known_parent', u); new('building_level', k); new('turns_center', k); new('square_building_button', u) end
  return u._addr
end
function U:Resize(w, h) assert(type(w) == 'number' and type(h) == 'number'); self._w, self._h = w, h end
function U:SetCanResizeWidth() end
function U:SetCanResizeHeight() end
function U:NumImages() return 1 end
function U:SetCanResizeCurrentStateImageWidth() end
function U:SetCanResizeCurrentStateImageHeight() end
function U:ResizeCurrentStateImage() end
function U:SetDockingPoint() end
function U:SetDockOffset(x, y) assert(type(x) == 'number' and type(y) == 'number'); self._x, self._y = x, y end
function U:MoveTo(x, y) self._x, self._y = x, y end
function U:Position() local x, y, p = self._x, self._y, self._parent; while p do x, y = x + p._x, y + p._y; p = p._parent end; return x, y end
function U:Bounds() return self._w, self._h end
function U:Width() return self._w end
function U:Height() return self._h end
function U:SetStateText(t) assert(type(t) == 'string'); self._text = t end
function U:GetStateText() return self._text end
function U:TextDimensions() return #self._text * 7, 18, 1 end
function U:SetOpacity(v) assert(type(v) == 'number'); self._op = v end
function U:Opacity() return self._op end
function U:SetImagePath(p) self._img = p end
function U:GetImagePath() return self._img or '' end
function U:Destroy() self._dead = true; local p = self._parent; if p then for i, k in ipairs(p._kids) do if k == self then table.remove(p._kids, i); break end end end end
local function fire(ev, id, ctx)
  ctx = ctx or {string = id}
  for _, l in pairs(listeners) do if l.event == ev and (l.cond == true or l.cond(ctx)) then l.cb(ctx) end end
end
_G.fake_fire = fire
function U:SimulateMouseOn() fire('ComponentMouseOn', self._id); self._state = 'hover' end
function U:SimulateMouseOff() fire('ComponentMouseOff', self._id); self._state = 'active' end
function U:SimulateLClick() fire('ComponentLClickUp', self._id) end
function U:CurrentState() return self._state end
function U:SetState(s) self._state = s end
function U:Visible() return self._vis end
function U:VisibleFromRoot() return self._vis end
function U:SetVisible(v) self._vis = v end
function U:SetContextObject(o) self._ctx = o end
function U:GetContextObject() return self._ctx end
function U:Layout() end
local root = new('root', nil, 'root'); root._w, root._h = 1920, 1080
local function find_in(u, name) for _, k in ipairs(u._kids) do if k._id == name then return k end; local f = find_in(k, name); if f then return f end end end
function find_uicomponent(parent, ...)
  local u = parent
  for _, name in ipairs({...}) do u = u and find_in(u, name) end
  return u or false
end
core = {get_ui_root = function() return root end, get_screen_resolution = function() return 1920, 1080 end,
  add_listener = function(self, name, ev, cond, cb) listeners[name] = {event = ev, cond = cond, cb = cb} end,
  remove_listener = function(self, name) listeners[name] = nil end}
-- the campaign
local slots, items, gold, dev = {'wh3_dlc25_dwarf_spirit_of_grungni_airship_hull_1'}, {}, 5000, 10
local N = 19
for i = 2, N do slots[i] = '' end
local slot_list = {num_items = function() return N end, item_at = function(self, i) local k = slots[i + 1]; return {has_building = function() return k ~= '' end, building = function() return k end} end}
local mf = {command_queue_index = function() return 7 end, horde_details = function() return {military_force_slot_list = function() return slot_list end} end}
local faction = {name = function() return 'wh3_dlc25_dwf_malakai' end, treasury = function() return gold end}
local malakai = {character_subtype_key = function() return 'wh3_dlc25_dwf_malakai_makaisson' end, command_queue_index = function() return 42 end,
  faction = function() return faction end, military_force = function() return mf end}
local clist = {num_items = function() return 1 end, item_at = function() return malakai end}
local flist = {num_items = function() return 1 end, item_at = function() return {character_list = function() return clist end} end}
local turn = 1
local function our(extra)
  local c = {faction = function() return faction end, character = function() return malakai end, military_force = function() return mf end}
  for k, v in pairs(extra or {}) do c[k] = v end
  return c
end
cm = {model = function() return {world = function() return {faction_list = function() return flist end} end} end,
  turn_number = function() return turn end,
  get_faction = function(self, n) return faction end,
  treasury_mod = function(self, f, v) gold = gold + v end,
  add_development_points_to_horde = function(self, m, v) dev = dev + v end,
  add_building_to_force = function(self, c, key)
    assert(c == 7, 'force cqi')
    if string.find(key, 'airship_hull', 1, true) then slots[1] = key; return end
    for i = 2, N do if slots[i] == '' and not items[i - 1] then slots[i] = key; return end end
  end}
local function slot_n(expr) return tonumber(string.match(expr, 'BuildingSlotList%.At%((%d+)%)')) end
common = {
  get_context_value = function(obj, id, expr)
    if string.find(expr, 'BadExpr', 1, true) then error('bad expression') end
    local n = slot_n(expr)
    if string.find(expr, 'BuildingSlotList.Size', 1, true) then return N end
    if string.find(expr, 'DevelopmentPoints', 1, true) then return dev end
    if n and string.find(expr, 'IsContextValid(', 1, true) and string.find(expr, 'ConstructionItemContext)', 1, true) then return items[n] ~= nil end
    if n and string.find(expr, '%.IsEmpty$') then return slots[n + 1] == '' end
    if n and string.find(expr, 'ConstructionItemContext.BuildingLevelRecordContext.Key', 1, true) then return items[n] end
    if string.find(expr, 'CreateCost(this)', 1, true) then return 1500 end
    if string.find(expr, 'PrimarySlotContext.BuildingContext.BuildingLevelRecordContext.Level', 1, true) then return 4 end
    if string.find(expr, 'IsActiveForBuildingBrowser', 1, true) then return true end
    if expr == 'EffectList.Size' then return 2 end
    if expr == 'EffectList.At(0).Key' then return 'wh3_dlc25_effect_agent_enable_recruitment_dignitary_dragon_slayer' end
    if expr == 'EffectList.At(0).Value' then return 0 end
    return nil
  end,
  call_context_command = function(obj, id, expr)
    local key = string.match(expr, '"CcoBuildingLevelRecord", "([^"]+)"') or id
    local n = slot_n(expr)
    if string.find(expr, 'IssueCommandForBuildingBrowser', 1, true) and n then
      if items[n] then items[n] = nil; gold = gold + 1500; fire('MilitaryForceBuildingCancelled', nil, our())
      else items[n] = key; gold = gold - 1500; fire('BuildingConstructionIssuedByPlayer', nil, our({building = function() return key end})) end
    end
    if string.find(expr, '.Dismantle', 1, true) and n then fire('CharacterHordeBuildingDemolished', nil, our({building = function() return slots[n + 1] end})) end
  end,
  get_localised_string = function(k) return 'text of ' .. k end}
-- a turn: the world's other factions, ours ends, constructions complete (one turn each here), ours starts
function fake_end_turn()
  fire('FactionTurnStart', nil, {faction = function() return {name = function() return 'wh_main_grn_greenskins' end} end})
  fire('FactionTurnEnd', nil, our())
  turn = turn + 1
  for n, key in pairs(items) do
    local old = slots[n + 1]
    slots[n + 1] = key
    items[n] = nil
    if old ~= '' then fire('CharacterHordeBuildingDemolished', nil, our({building = function() return old end})) end
    fire('MilitaryForceBuildingCompleteEvent', nil, our({building = function() return key end}))
  end
  fire('FactionTurnStart', nil, our())
  return 'turned'
end
cco = function(t, id) return {Call = function(self, e) return nil end} end
CampaignUI = {ClearSelection = function() end}
mtb = {log = function() end}
tww3_mtb_crew_ui = {blocked = function() return nil end, open = function() end, close = function() end, is_open = function() return true end}
"""


class FakeSession:
    def __init__(self, deadline):
        self.deadline = deadline

    def log(self, *a):
        print("  " + " ".join(str(x) for x in a)[:300], flush=True)

    def check_time(self):
        if time.time() > self.deadline:
            raise TimeoutError("hard limit of the session")

    def shot(self, name):
        pass

    def mode(self):
        return "campaign"


def fake_main(config_path):
    """Python 3.10 with lupa 2.8: the probe's Lua compiled as Lua 5.1, then every item driven by the same Probe code against a fake game."""
    from lupa import lua51
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)
    rt = lua51.LuaRuntime(unpack_returned_tuples=True)
    assert rt.eval("_VERSION") == "Lua 5.1", rt.eval("_VERSION")
    load = rt.eval("function(s, name) local f, err = loadstring(s, name); return f ~= nil, err end")
    for name, text in (("port_probe.lua", LUA_FILE.read_text(encoding="utf-8")), ("fake_game", FAKE_GAME)):
        ok, err = load(text, name)
        print(f"syntax {name}: {'ok' if ok else err}")
        if not ok:
            return 2
    rt.execute(FAKE_GAME)

    def transport(code, wait):
        try:
            return {"ok": True, "result": rt.execute(code)}
        except Exception as e:      # lupa.LuaError
            return {"ok": False, "result": str(e)}
    run_dir = OUT / "fake_run"
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    session = FakeSession(time.time() + 300)
    session.safe_end_turn = lambda: transport("return fake_end_turn()", 10).get("ok") is True
    probe = Probe(cfg, transport, session, run_dir, fake=True)
    how = probe.run()
    bad = [no for no, r in probe.results.items() if r["status"] in ("error", "timeout")]
    for no, r in probe.results.items():
        print(f"  [{no}] {r['status']}: {str(r['answer'])[:220]}")
    print("fake run:", how, "| items with Lua or Python errors:", bad or "none", "| log", probe.jsonl)
    return 1 if bad or how != "completed" else 0


# ---------------------------------------------------------------- the launch ----------------------------------------------------------------

def session_main(argv):
    """tools/run_game.py with build/port_probe/pack, the lock line of CLAUDE.md and a docker container alone not counted as busy."""
    import run_game as rg
    rb = rg.rb
    busy = rb.busy_reasons
    rb.busy_reasons = lambda: [r for r in busy() if r != "docker containers are running"]
    rg.PACK_DIR = PACK     # the lock line «mtb, начало HH:MM» is written by tools/shared_game.py
    return rg.main(argv)


def plan_text(args, limit):
    res = "1280x720" if args.small else "1920x1080"
    return "\n".join([
        "launch plan:",
        f"  1. {sys.executable} {Path(__file__).name} _session --label port_probe --timeout {limit + 120} --packs harness campaign --user-mods memreader_plus.pack"
        + ("" if args.small else " --set x_res=1920 y_res=1080"),
        f"     -> tools/run_game.py: lock {sg.LOCK} = «mtb, начало HH:MM»; packs from {PACK}; our mod list tww3_mtb_mods.txt",
        f"        (used_mods.txt only read); low graphics, windowed {res}, Normal difficulty, RTX checked; SW_SHOWNOACTIVATE + KeepBehind (no focus, under other windows);",
        "        the user's save/settings folders copied and put back; autosave off.",
        "  2. main menu -> new campaign wh3_dlc25_dwf_malakai (frontend.start_campaign), wait for the end turn button, peace with everyone, events accepted.",
        "  3. items 0, 7, 8, 10, 6a, 5, 11 (our own components only), 14 (reads), setup (gold, points, hull top), 1, 2, 3, 4 (one real battle),",
        f"     12 (ONE turn end by script, hard limit {END_TURN_LIMIT} s; then a cancel and a dismantle), 13, then the risky 6b, 9.",
        f"  4. STOP flag -> run_game.py closes only the game it started (its PID), waits until tasklist has no Warhammer3.exe, then removes the lock;",
        "     the same on an error, a timeout or a crash. Item 12 is the only turn end of the probe.",
        f"  hard limit {limit} s (~{limit // 60} min); expected 30-45 min: start and new campaign 8-12, UI items 3-4, buildings 4-6, battle 4-7, turn end with 12/13 3-10, risky 2.",
    ])


def run(args):
    limit = args.limit
    cfg = make_config()
    req = cfg["requires"]
    print(f"config {CONFIG}: campaign pack {cfg['campaign_pack']['bytes']} bytes of {cfg['campaign_pack']['mtime']}; slot_cap {cfg['slot_cap']}; hull top {cfg['hull_top']};")
    print(f"  required rows {req['rows_in_pack']}, levels with 2+ rows {req['multi_levels']}, chosen {[c['key'].removeprefix(PREFIX) + '<-' + ','.join(p.removeprefix(PREFIX) for p in c['parents']) for c in req['candidates']]};")
    print(f"  side chains {cfg['side_chains']}, fillers {len(cfg['fillers'])} ({', '.join(f['key'].removeprefix(PREFIX) for f in cfg['fillers'])}); tree nodes {len(cfg['nodes'])}; notes {cfg['notes'] or 'none'}")
    need = 15 + 3
    if len(cfg["fillers"]) + len({p for c in req["candidates"] for p in c["parents"]}) < need:
        print(f"  NOTE: item 2 needs about {need} distinct side chains to reach slot 16 and keep one for item 4; the pack has fewer: item 2 will be inconclusive until the tree is built")
    if not req["candidates"]:
        print("  NOTE: no level with two or more required rows in the pack yet: item 1 will be inconclusive until the data developer's build lands")
    if cfg["slot_cap"] != 18:
        print(f"  NOTE: slot_cap in the pack is {cfg['slot_cap']}, not 18 yet")
    built = build_pack()
    print(f"pack {PACK}: {built['harness']} ({len(built['harness_files'])} files), {built['campaign']} {built['campaign_bytes']} bytes (a copy of {CAMPAIGN_PACK_DIR})")
    print("checks before a launch (CLAUDE.md):")
    rows = checks()
    for what, ok, blocking, detail in rows:
        print(f"  [{'ok' if ok else ('STOP' if blocking else 'note')}] {what}: {detail}")
    blockers = [r for r in rows if r[2] and not r[1]]
    stash_blocked = [r for r in blockers if r[0].startswith("data/") and "author's" in r[0]]
    other_blockers = [r for r in blockers if r not in stash_blocked]
    fake = subprocess.run(["py", "-3.10", str(Path(__file__).resolve()), "_fake", str(CONFIG)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("Lua 5.1 check and fake game (py -3.10, lupa):")
    print("\n".join("  " + l for l in (fake.stdout + fake.stderr).strip().splitlines()[-40:]))
    print(plan_text(args, limit))
    if args.dry_run:
        print("\n".join(sg.describe()))
        state ="would launch" if not blockers else ("would STOP: " + "; ".join(r[0] for r in blockers))
        if stash_blocked and not other_blockers:
            state += " (with --stash-user-pack and the author's yes it would launch)"
        print("dry run:", state, "| fake game:", "ok" if fake.returncode == 0 else f"FAILED ({fake.returncode})")
        return 0 if fake.returncode == 0 else 1
    if fake.returncode != 0:
        print("not launching: the probe failed against the fake game")
        return 1
    if other_blockers or (stash_blocked and not args.stash_user_pack):
        print("not launching:", "; ".join(r[0] for r in blockers))
        return 3
    return launch(args, cfg, limit)


def launch(args, cfg, limit):
    import crew_cycle as cc
    import rc
    rg = cc.rg
    stashed, mt = None, None
    if args.stash_user_pack:
        import modular_test as mt
        if not mt.restore_user_pack(print):
            print("not launching: an earlier stash could not go back, see", mt.STASH)
            return 3
    started = time.time()
    session = cc.Session("port_probe", started + limit)
    session.current = {}
    cmd = [sys.executable, str(Path(__file__).resolve()), "_session", "--label", "port_probe", "--timeout", str(limit + 120),
           "--packs", "harness", "campaign", "--user-mods", "memreader_plus.pack"]
    if not args.small:
        cmd += ["--set", "x_res=1920", "y_res=1080"]
    OUT.mkdir(parents=True, exist_ok=True)
    proc, how, probe = None, "not started", None
    try:
        if args.stash_user_pack:
            stashed = mt.stash_user_pack(print)
        proc = subprocess.Popen(cmd, stdout=(OUT / "session.log").open("w", encoding="utf-8"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        end = time.time() + 60
        while not rg.STATE.exists():
            if proc.poll() is not None or time.time() > end:
                raise RuntimeError(f"the session did not start, see {OUT / 'session.log'}")
            time.sleep(1)
        session.dir = Path(rc.state()["run"])
        (OUT / "last_run.txt").write_text(str(session.dir), encoding="utf-8")
        shutil.copy2(CONFIG, session.dir / "port_probe_config.json")
        session.log("run", session.dir)
        session.wait_mode("frontend", 240)
        time.sleep(10)
        session.log(session.plain(f'frontend.start_campaign("wh3_main_combi", "wh3_main_combi", "{FACTION_KEY}"); return 1', 10)["result"])
        session.wait_mode("campaign", 900)
        time.sleep(8)
        end = time.time() + 200
        while time.time() < end and session.visible("button_end_turn") in ("-", "inactive"):
            time.sleep(3)
        session.shot("pp_map")
        session.log("peace", session.prog("return P.peace()")["result"])
        accept = ('local n = 0; for _ = 1, 4 do local e = mtb.find("events", true); local b = e and mtb.find("button_accept", true, e); '
                  'if b then b:SimulateLClick(); n = n + 1 end end; return n')
        for _ in range(2):
            session.log("events", session.plain(accept, 10)["result"])
            time.sleep(2)
        session.log("blockers", session.script("dismiss_blockers.lua")["result"])
        probe = Probe(cfg, rc.send, session, session.dir)
        how = probe.run()
    except Exception as e:      # the game must be closed in every case
        how = f"error before or between items: {type(e).__name__}: {e}"
        session.log("ERROR", how)
    finally:
        if proc is not None and proc.poll() is None:
            rg.STOP.write_text("stop")
        if proc is not None:
            try:
                proc.wait(240)
            except subprocess.TimeoutExpired:
                session.log("run_game.py did not end in 240 s: it keeps the lock while a game is in tasklist")
        gone = not cc.rg.rb.game_running()
        status = {}
        if session.dir and (session.dir / "status.json").exists():
            status = json.loads((session.dir / "status.json").read_text(encoding="utf-8"))
        restored = mt.restore_user_pack(print) if stashed else None
        final = {"item": "end", "finished": True, "how": how, "seconds": round(time.time() - started), "game_gone": gone,
                 "lock_removed": not sg.OUR_LOCK.match(sg.read_lock() or ""), "run_game": status, "user_pack_restored": restored}
        if probe:
            probe.write(final)
            print(probe.summary(how))
        elif session.dir:
            with (session.dir / "port_probe.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(final, ensure_ascii=False) + "\n")
        print("finished:", json.dumps(final, ensure_ascii=False))
    return 0 if how == "completed" and gone else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "_session":
        return session_main(argv[1:])
    if argv and argv[0] == "_fake":
        return fake_main(argv[1] if len(argv) > 1 else CONFIG)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--small", action="store_true")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--stash-user-pack", action="store_true")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
