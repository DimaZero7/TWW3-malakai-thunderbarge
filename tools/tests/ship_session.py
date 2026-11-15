"""Session «ship_panel»: the mod's NEW airship panel (src/tww3_mtb_ship_screen.lua) opened in the real game for the first time, exercised through its
own handlers, and brought back as evidence (docs/design/port-to-game.md, 5, stages 2 and 3). ONE unattended game, ONE turn end, ONE battle (the last step).

  py -3.14 tools/crew_cycle.py session ship_panel --dry-run     everything but the game: checks, the session pack, every step against a fake game
                                                                 under the game's emulated Lua (py -3.10, lupa), the analysis, the plan
  py -3.14 tools/crew_cycle.py session ship_panel               the run (only with the author's permission, CLAUDE.md «Общая игра»)
      --small              1280x720 instead of 1920x1080
      --limit N            hard limit of the whole session in seconds (default 3600)
      --stash-user-pack    the author's tww3_mtb_campaign.pack in data/ moved aside for the run and put back after (hash checked), as the probe
  py -3.10 tools/tests/ship_session.py _analyse RUN_DIR         the analysis of a run folder again (comparisons, expected texts), no game

The panel is switched on FOR THE SESSION ONLY: build/ship_session/pack/tww3_mtb_campaign.pack is a copy of build/campaign/pack's with
script/campaign/mod/tww3_mtb_crew_ui.lua's `M.NEW_SHIP_PANEL = false` turned true and the panel's modules (script/campaign/tww3_mtb/) taken
from src/ as they are now. src/ and build/campaign/pack are not changed.

Answers in the run folder (build/campaign/runs/<time>-ship_panel; build/ship_session/last_run.txt names it): ship_session.jsonl (one line per step,
flushed at once; the last says how it ended), ship_session_summary.txt, dump_<state>.json (the live panel in the rows of tools/tests/fake_uic.lua,
with what the game's UIComponent answers per row), ss_<state>.png (PrintWindow, no focus), analysis.json and analysis.txt (the comparisons).
The launch, the lock, the stash and the shutdown are tools/tests/port_probe.py's machinery (tools/run_game.py, tools/shared_game.py).
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
TOOLS = REPO / "tools"
TESTS = TOOLS / "tests"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TESTS))
import port_probe as pp  # noqa: E402  (the probe's machinery: Probe, census, checks, fake UIComponent, lua_literal)
import shared_game as sg  # noqa: E402

OUT = REPO / "build" / "ship_session"
PACK = OUT / "pack"
CONFIG = OUT / "config.json"
LUA_FILE = TESTS / "ship_session.lua"
CAMPAIGN_PACK_DIR = REPO / "build" / "campaign" / "pack"
DUMPS = REPO / "build" / "ui_dump"
SEP = chr(92)
FOLDER = f"script{SEP}campaign{SEP}tww3_mtb{SEP}"
CREW_UI = f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew_ui.lua"
SWITCH_OFF, SWITCH_ON = "M.NEW_SHIP_PANEL = false", "M.NEW_SHIP_PANEL = true"
SRC_MODULES = ["tww3_mtb_ship", "tww3_mtb_crew_model", "tww3_mtb_ship_ui", "tww3_mtb_ship_uic", "tww3_mtb_game", "tww3_mtb_ship_screen"]
ALL_MODULES = SRC_MODULES[:2] + ["tww3_mtb_ship_config", "tww3_mtb_ship_ui_config"] + SRC_MODULES[2:]
DEFAULT_LIMIT = 3600
END_TURN_LIMIT = pp.END_TURN_LIMIT       # the probe's item 12 budget: the same turn end, the same limit
PAGE = 250                               # rows of a dump per remote call
# Per step: seconds before the step is cut off (the next one goes on). The open builds ~3800 components (probe item 8 times 1500).
BUDGET = {"census": 60, "smoke": 120, "gates_fresh": 60, "requirement": 150, "agree": 120, "agree_after_turn": 120, "load": 150, "configure": 30, "frames_closed": 30, "open": 240, "frames_open": 30, "diag": 90,
          "dump_fresh_tree": 300, "dump_fresh_tree_info": 300, "dump_fresh_ship": 300, "order": 60, "cancel": 60, "order_again": 60, "tabs": 60, "info": 60,
          "unit": 60, "picker": 90, "scroll": 90, "close_reopen": 120, "escape": 60, "save": 60, "opacity": 30, "fit": 120, "views": 90, "views_after_turn": 60, "demolish": 90, "order_long": 60,
          "turn": END_TURN_LIMIT + 120, "dump_after_turn": 300, "cancel_previous": 120, "save_final": 60, "simulated": 30, "finish": 60, "battle_orders": 900,
          "resize_log": 30, "points": 120, "hover_shots": 90}
RISKY = {"fit": "«Всё дерево»: the binding lays ~3000 components out again at the scale (ENGINE.scale_by_layout): CPU, not bindings",
         "demolish": "the game's Dismantle command on a slot (game state; the building stands until the turn ends)",
         "turn": "the turn end by script (the probe's item 12 way, hard limit END_TURN_LIMIT); cm.treasury_mod and pay_upkeep wrapped during it",
         "simulated": "SimulateMouseOn on our slot (the probe: it changes the look, sends no event)",
         "battle_orders": "ONE real battle (the probe's way): the campaign Lua restarts after it, so nothing of the panel can follow"}
# The engine probe's answers (tools/tests/port_probe.py) as configuration: None keeps the module's own choice (src/tww3_mtb_ship_uic.lua ENGINE,
# src/tww3_mtb_game.lua ASSUMED). Set here or per run with --option NAME=VALUE (true/false/a number/a word). The step "configure" applies them on
# the screen's own modules before the first open. Which probe item answers which option:
#   engine.measure_text   item 7  TextDimensions non-zero at once: 'game' | zero at once (even if right a frame later): 'chars'
#   engine.clips          item 6a clipchildren clips our children: True | it does not: False (the binding hides what lies outside itself)
#   engine.wheel          item 6b the game's list template scrolls by the wheel in our layout: True (not used by the panel yet) | False
#   engine.building_frame item 9  the template fills itself from SetContextObject: True (an experiment, not used by the panel) | False
#   engine.tint           (no item) SetCurrentStateImageColour raises: 'opacity' | it answers: 'auto'
#   engine.profile        (no item) the calls into the game's UIComponent counted and timed by method (src/tww3_mtb_ship_uic.lua): the open, the
#                         reopen and «Всё дерево» say which call makes them slow. On by default for the session; False: no cost at all
#   assumed.queue_completions  item 12 completions come BEFORE our FactionTurnStart: True | always after it: False (either way the page's order)
#   assumed.dismantle_check_ms  the adapter reads the slot again this long after its Dismantle (a dismantle the game would execute at once; the runs
#                         show it at the turn's end: the module then says «сносится» until the turn start)
#   session.click / session.hover  item 5 SimulateLClick / SimulateMouseOn reach the panel's listeners: 'simulate' | not: 'direct' (the listener's own function)
OPTIONS = {"engine.measure_text": None, "engine.clips": None, "engine.wheel": None, "engine.building_frame": None, "engine.tint": None, "engine.profile": True,
           "assumed.queue_completions": None, "assumed.dismantle_check_ms": None,
           "session.click": "direct", "session.hover": "direct"}
DIAG_IMAGES = ["ui/skins/default/icon_cross.png", "ui/skins/default/building_frame_hover.png", "ui/skins/wh_main_dwf_dwarfs/panel_title_large.png",
               "ui/skins/default/slider_vertical_mid.png", "ui/tww3_mtb/web/tree_line.png", "ui/tww3_mtb/backdrop.png"]


def ss_lib():
    """port_probe.lua's helpers, then this session's, in a function of its own (its locals do not count against the chunk's 200)."""
    mine = LUA_FILE.read_text(encoding="utf-8").rsplit("return 'ready'", 1)[0]
    return pp.lua_lib() + "\n(function()\n" + mine + "\nend)()\n"


# ---------------------------------------------------------------- the session's pack ----------------------------------------------------------------

def session_files():
    """{pack path: bytes} of the session's campaign pack: build/campaign/pack's with the switch on and the panel's modules from src/."""
    import pfh5
    manifest = json.loads((CAMPAIGN_PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    files, deps = pfh5.read_pack((CAMPAIGN_PACK_DIR / manifest["packs"]["campaign"]).read_bytes())
    text = files[CREW_UI].decode("utf-8")
    if text.count(SWITCH_OFF) != 1:
        raise SystemExit(f"{CREW_UI}: the line «{SWITCH_OFF}» is not there exactly once ({text.count(SWITCH_OFF)}): src/tww3_mtb_crew_ui.lua changed")
    files[CREW_UI] = text.replace(SWITCH_OFF, SWITCH_ON, 1).encode("utf-8")
    replaced = []
    for name in SRC_MODULES:
        key = FOLDER + name + ".lua"
        if key not in files:
            raise SystemExit(f"{key} is not in the campaign pack: py -3.14 tools/build.py")
        src = (REPO / "src" / (name + ".lua")).read_bytes()
        if files[key] != src:
            replaced.append(name)
        files[key] = src
    return files, deps, manifest, replaced


def build_pack():
    import pfh5
    files, deps, manifest, replaced = session_files()
    remote = (REPO / "src" / "tww3_mtb_remote.lua").read_bytes()
    harness = {f"script{SEP}{m}{SEP}mod{SEP}tww3_mtb_remote.lua": remote for m in ("frontend", "campaign", "battle")}
    PACK.mkdir(parents=True, exist_ok=True)
    names = manifest["packs"]
    (PACK / names["harness"]).write_bytes(pfh5.pack_files(harness))
    blob = pfh5.pack_files(files, deps)
    back, _ = pfh5.read_pack(blob)
    if SWITCH_ON not in back[CREW_UI].decode("utf-8"):
        raise SystemExit("the session pack does not read back with the switch on")
    (PACK / names["campaign"]).write_bytes(blob)
    (PACK / "manifest.json").write_text(json.dumps({"packs": names}, indent=1), encoding="utf-8")
    return {"campaign": names["campaign"], "bytes": len(blob), "files": len(files), "replaced_from_src": replaced, "harness": names["harness"]}


def pack_files_now():
    import pfh5
    manifest = json.loads((PACK / "manifest.json").read_text(encoding="utf-8"))
    files, _ = pfh5.read_pack((PACK / manifest["packs"]["campaign"]).read_bytes())
    return files


def inline_sources(files=None):
    files = files or pack_files_now()
    return {n: files[FOLDER + n + ".lua"].decode("utf-8") for n in ALL_MODULES}


def parse_options(items):
    """OPTIONS with --option NAME=VALUE applied (true/false/none, a number, else the word)."""
    out = dict(OPTIONS)
    for item in items or []:
        name, _, value = item.partition("=")
        if name not in OPTIONS:
            raise SystemExit(f"--option {name}: not one of {sorted(OPTIONS)}")
        low = value.strip().lower()
        out[name] = True if low == "true" else False if low == "false" else None if low in ("none", "") else int(low) if low.isdigit() else value.strip()
    return out


def requirement_keys():
    """The keys of the requirement test (port-to-game.md 8.4) from the generated ship config: «Пивной чертог» (level I of its chain), the chain's
    level II, «Склад оружия» (requires level I), hull II (the store's tier)."""
    conf = json.loads((REPO / "build" / "tree" / "ship_config.json").read_text(encoding="utf-8"))
    levels = conf["levels"]
    beer1 = next((r for r in levels if r["name"] == "Пивной чертог" and r["level"] == 0), None)
    store = next((r for r in levels if r["name"] == "Склад оружия"), None)
    if not beer1 or not store:
        return {"error": "«Пивной чертог» or «Склад оружия» not in build/tree/ship_config.json"}
    chain = [r for r in levels if r["chain"] == beer1["chain"]]
    beer2 = next((r for r in chain if r["level"] == 1), None)
    hull2 = next((h["key"] for h in conf["hull_tiers"] if h["tier"] == store["tier"]), None)
    return {"beer1": beer1["key"], "beer2": beer2 and beer2["key"], "store": store["key"], "store_requires": store["requires"], "store_tier": store["tier"],
            "hull2": hull2, "chain_keys": [r["key"] for r in chain]}


def make_config(options=None):
    files = pack_files_now()
    layouts = sorted(n.split(SEP)[-1][: -len(".twui.xml")] for n in files if n.startswith(f"ui{SEP}tww3_mtb{SEP}") and n.endswith(".twui.xml") and f"{SEP}web{SEP}" not in n)
    index = json.loads((DUMPS / "index.json").read_text(encoding="utf-8")) if (DUMPS / "index.json").exists() else {"states": []}
    cfg = {"made": datetime.now().isoformat(timespec="seconds"), "layouts": layouts, "images": DIAG_IMAGES, "page_states": index["states"],
           "pack": str(PACK), "options": options or dict(OPTIONS), "user_ui_scale": None}
    cfg["req_test"] = requirement_keys()
    conf = json.loads((REPO / "build" / "tree" / "ship_config.json").read_text(encoding="utf-8"))
    cfg["nest_key"] = next((r["key"] for r in conf["levels"] if r["name"] == "Вороньи гнёзда" and r["level"] == 0), None)
    try:        # the user's ui_scale (read only; run_game.py keeps it, the game clamps it at small roots)
        import run_battle as rb
        prefs = rb.PREFS.read_bytes().decode("latin-1") if rb.PREFS.exists() else ""
        cfg["user_ui_scale"] = next((l.split(";")[0].split()[1] for l in prefs.splitlines() if l.startswith("ui_scale ")), None)
    except Exception as e:
        cfg["user_ui_scale"] = f"not read: {e}"
    OUT.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return cfg


def checks():
    """port_probe.checks() (CLAUDE.md «Общая игра»), with this session's pack compared against data/."""
    old = pp.PACK
    pp.PACK = PACK
    try:
        return pp.checks()
    finally:
        pp.PACK = old


# ---------------------------------------------------------------- the steps ----------------------------------------------------------------

class ShipSession(pp.Probe):
    """The steps, on the probe's plumbing (transport, flushed jsonl, pictures, the turn end with its limit)."""

    def __init__(self, cfg, transport, session, run_dir, fake=False):
        super().__init__(cfg, transport, session, run_dir, fake)
        self.lib = ss_lib()
        self.jsonl = self.dir / "ship_session.jsonl"
        self.actions = []          # what was done to the logic, for the offline replay of the expected texts
        self.shots = {}
        self.key = None
        self.abort = None
        self.gifts = []            # points and gold given by script (ensure), told in the summary

    def sleep(self, seconds):
        if self.fake:
            # the fake's timers (the game's real callbacks) run at a sleep, a tick for each 100 ms of it (the adapter counts its waits so)
            self.send(f"return fake_ticks({max(1, round(seconds * 10))})", 5)
        else:
            time.sleep(seconds)

    def z(self, name, args=None, wait=20):
        self.s.check_time()
        if self.item_end and time.time() > self.item_end:
            raise pp.ItemTimeout(f"step time over before {name}")
        code = self.lib + f"\nreturn _G.mtb_ss.run({pp.lua_literal(name)}, {pp.lua_literal(args or {})})"
        row = self.send(code, wait)
        if row.get("ok") is None:
            return {"ok": False, "timeout": True, "err": str(row.get("result")), "item": name}
        if not row.get("ok"):
            return {"ok": False, "err": str(row.get("result"))[:4000], "item": name}
        try:
            return json.loads(row["result"])
        except (TypeError, ValueError):
            return {"ok": False, "err": "not JSON", "raw": str(row.get("result"))[:2000], "item": name}

    def shoot(self, name, crop=None):
        """A picture of the game window and the root it was taken at; the game's advisor dismissed first (it covers the panel's top left corner).
        crop: a box in root units ({x, y, w, h}) the analysis cuts out at the picture's full resolution (<name>_crop.png): a close-up."""
        if not getattr(self, "advisor_gone", False):
            a = self.data("advisor_off")
            self.advisor_gone = bool(a.get("dismissed"))
            self.advisor = a
        root = self.data("root")
        screen = root.get("screen") or [None, None]
        scale = round(screen[0] / root["w"], 4) if screen[0] and root.get("w") else None     # the UI scale as the game applies it: pixels per root unit
        self.shots[name] = {"root": root, "ui_scale_effective": scale, "user_ui_scale": self.cfg.get("user_ui_scale"), "time": time.strftime("%H:%M:%S")}
        if crop:
            self.shots[name]["crop"] = crop
        self.shot(name)
        (self.dir / "shots.json").write_text(json.dumps(self.shots, ensure_ascii=False, indent=1), encoding="utf-8")

    def item(self, no, title, fn):
        record = {"step": no, "title": title, "risky": RISKY.get(no), "status": "failed", "answer": None, "started": time.strftime("%H:%M:%S")}
        begin = time.time()
        self.item_end = begin + BUDGET.get(no, 90) * (1 if not self.fake else 100)
        self.last_fail = None
        self.s.log("=== step", no, title)
        try:
            status, answer, data = fn()
            record.update(status=status, answer=answer, data=data)
        except pp.ItemTimeout as e:
            record.update(status="timeout", answer=f"cut off after {BUDGET.get(no)} s: {e}")
        except TimeoutError as e:
            if "hard limit" in str(e):
                record.update(status="hard_limit", answer=str(e), seconds=round(time.time() - begin, 1))
                self.write(record)
                raise
            record.update(status="failed", answer=f"TimeoutError: {e}")
        except pp.SessionAbort:
            raise
        except Exception as e:      # one step's failure never loses the others
            record.update(status="failed", answer=f"{type(e).__name__}: {str(e)[:3000]}", python=traceback.format_exc()[-1500:])
        finally:
            self.item_end = None
        if record["status"] in ("failed", "timeout"):
            if self.last_fail:
                record["failed_call"] = self.last_fail
            self.shot(f"ss_failed_{no}")
        record["seconds"] = round(time.time() - begin, 1)
        try:
            h = self.z("health", wait=10)
            record["health_after"] = h.get("data") if h.get("ok") else {"err": h.get("err")}
            self.healthy = bool(h.get("ok") and not h["data"].get("canary"))
        except TimeoutError:
            raise
        except Exception as e:
            record["health_after"] = {"err": str(e)}
            self.healthy = False
        self.write(record)
        self.results[no] = record
        self.s.log("step", no, record["status"], str(record["answer"])[:300])
        return record

    # -- the smoke of this session's own helpers (text lines, as the probe's)
    def ssmoke(self):
        path = self.dir / "smoke.txt"
        row = self.send(self.lib + "\nreturn _G.mtb_ss.smoke({})", 60)
        text = str(row.get("result"))
        path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
        if not row.get("ok"):
            return "failed", f"the smoke chunk itself failed (does the file load?): {text[:800]}", {"raw": text[:4000]}
        steps = [l.split("\t") for l in text.splitlines() if l.startswith("S\t")]
        info = dict(l.split("\t")[1:3] for l in text.splitlines() if l.startswith("C\t"))
        failed = [s for s in steps if len(s) > 2 and s[2].startswith("ERR")]
        self.smoke_broken = info.get("first_broken", "none") != "none"
        answer = (f"{len(steps)} steps, {len(failed)} failed: " + ("; ".join(f"{s[1]}: {s[2][4:200]}" for s in failed) or "none") +
                  f"; bindings first broken after: {info.get('first_broken')}; file smoke.txt")
        return ("ok" if not failed else "differs"), answer, {"steps": [{"step": s[1], "result": s[2], "canary": s[3] if len(s) > 3 else ""} for s in steps]}

    # -- a. load and open
    def sload(self):
        d = self.data("load", {}, 120)
        if not d.get("started"):
            self.s.log("load: no started screen by the switch nor by loadfile; the sources inline")
            d["inline"] = self.data("load_inline", {"sources": inline_sources()}, 120)
            d["how"] = d["inline"].get("how")
            d["started"] = d["inline"].get("ok")
        mods = d.get("modules") or {}
        envs = {n: (m.get("env") or {}) for n, m in mods.items()}
        bad_env = [n for n, e in envs.items() if e and not e.get("no_function") and not e.get("core")]
        answer = (f"switch {d.get('switch')}; ship_screen() -> {d.get('switch_call')} in {d.get('switch_seconds', 0):.2f} s; started by: {d.get('how') or 'NOTHING'}"
                  + (f"; required modules whose functions do NOT see core: {bad_env}" if bad_env else "")
                  + (f"; fallback {d.get('fallback')}" if d.get("fallback") else ""))
        if not d.get("started"):
            self.diagnose("load")
            raise pp.SessionAbort("the panel's modules did not load: " + answer)
        if (self.results.get("requirement") or {}).get("status") in ("info", "differs"):
            # the requirement step stood hull II and the beer hall by script: no event told the module, so its next news would name them
            d["resync"] = self.data("resync")
            answer += "; the module's ship baseline resynced after the requirement step's script adds"
        return ("ok" if d.get("how") == "switch" else "differs"), answer, d

    def diagnose(self, why):
        """The cheap diagnostics before an abort: every layout made once, the text layouts measured, some image paths."""
        try:
            d = self.data("diag", {"layouts": self.cfg["layouts"], "images": self.cfg["images"]}, 60)
        except Exception as e:
            d = {"err": str(e)}
        bad = {k: v for k, v in (d.get("layouts") or {}).items() if not v.get("ok")}
        self.write({"step": "diag", "why": why, "status": "info", "answer": f"layouts that failed to create: {sorted(bad) or 'none'}", "data": d})
        return d

    def sconfigure(self):
        opts = self.cfg.get("options") or OPTIONS
        engine = {k.split(".", 1)[1]: v for k, v in opts.items() if k.startswith("engine.") and v is not None}
        assumed = {k.split(".", 1)[1]: v for k, v in opts.items() if k.startswith("assumed.") and v is not None}
        d = self.data("configure", {"engine": engine, "assumed": assumed})
        return "ok", (f"set {d.get('set') or 'nothing (the modules keep their own)'}; ENGINE now {d.get('engine_now')}, ASSUMED now {d.get('assumed_now')}; "
                      f"clicks {opts.get('session.click')}, hovers {opts.get('session.hover')}"), d

    def data(self, name, args=None, wait=20):
        # the session's way of clicking and hovering (OPTIONS session.click / session.hover), unless a step names its own
        if name in ("click", "hover") and args is not None and "way" not in args:
            args = dict(args, way=(self.cfg.get("options") or OPTIONS).get(f"session.{name}") or "direct")
        return super().data(name, args, wait)

    @staticmethod
    def profile_text(p, n=6):
        """The heaviest calls into the game's UIComponent of a profile (ENGINE.profile): method calls / seconds."""
        if not p:
            return "no profile (ENGINE.profile off)"
        top = sorted((p.get("seconds") or {}).items(), key=lambda kv: -kv[1])[:n]
        return (f"{p.get('total_calls')} calls, {p.get('total_seconds', 0):.3f} s in the game's UIComponent; heaviest: "
                + ", ".join(f"{k} {p['calls'].get(k)} / {v:.3f} s" for k, v in top))

    @staticmethod
    def logic_text(l):
        """Where an open's time went besides the game's UIComponent calls: the model (src/tww3_mtb_ship.lua, its outermost calls: the adapter's
        reads inside), the adapter's context reads, and what is left for the drawing's own Lua (ship_session.lua prof_read)."""
        if not l:
            return "no logic profile"
        f = lambda v: f"{v:.3f}" if isinstance(v, (int, float)) else str(v)
        tops = lambda rows: ", ".join(f"{r['name']} {r['calls']} / {f(r['seconds'])} s" for r in (rows or [])[:5]) or "none"
        return (f"LOGIC: wall {f(l.get('wall'))} s = UIComponent {f(l.get('ui_seconds'))} + model {f(l.get('model_outer'))} ({l.get('model_outer_calls')} outer calls; "
                f"heaviest {tops(l.get('model_top'))}) + the drawing's own Lua {f(l.get('drawing_own'))}; inside the model the adapter read the game "
                f"{l.get('adapter_reads')} times in {f(l.get('adapter_read_seconds'))} s (functions: {tops(l.get('adapter_fn'))}; expressions: "
                f"{tops(l.get('adapter_expr'))})")

    def sopen(self):
        d = self.data("open", {}, 200)
        if not d.get("ok"):
            diag = self.diagnose("open")
            d["diag"] = diag
            raise pp.SessionAbort(f"the panel did not open: {str(d.get('err'))[:1500]}; last component made: {d.get('last_made')}; "
                                  f"made before the failure: {d.get('failed_count')}")
        self.sleep(1.0)
        m = d.get("measured") or {}
        status = "ok" if not m.get("chars") else "differs"
        return status, (f"opened by {d.get('how')}: {d.get('count')} components in {d.get('build_seconds', 0):.2f} s cpu ({d.get('seconds', 0):.2f} s with the call); "
                        f"root {d.get('root')}; texts measured by the game's TextDimensions {m.get('game')}, by the characters {m.get('chars')} "
                        f"(0 measured: the layout used the estimate), empty {m.get('empty')}; tab {d['state'].get('tab')}; foot «{d['state'].get('foot')}»; "
                        f"header points «{d['state'].get('points_text')}»; reused {d.get('reused')}; PROFILE: {self.profile_text(d.get('profile'))}; "
                        f"{self.logic_text(d.get('logic'))}"), d

    # -- b. a dump, paged, written to the run folder
    def dump(self, name, keys=None, only=None, look=None):
        """The live panel's rows (every window made first: the panel's build_all, as the page's dumps); only: the rows of some components
        (a slot's look); look: what the analysis compares them with (the page's state and its slot)."""
        head = self.data("dump_begin", {"live": True, "keys": keys or [], "only": only or []}, 120)
        rows = []
        while len(rows) < head["rows"]:
            page = self.data("dump_page", {"from": len(rows) + 1, "n": PAGE}, 60)
            if not page.get("rows"):
                break
            rows += page["rows"]
        snap = self.data("snapshot", {}, 30)
        out = {"name": name, "root": head.get("root"), "state": head.get("state"), "snapshot": snap, "components": rows, "seconds": head.get("seconds"),
               "made_by_build_all": head.get("made_by_build_all"), "only": only or None, "look": look}
        (self.dir / f"dump_{name}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out

    def sdump(self, name, page_state=True):
        def fn():
            d = self.dump(name)
            self.shoot("ss_" + name)
            texts = [r for r in d["components"] if "td" in r]
            measured = [r for r in texts if isinstance(r.get("td"), list) and (r["td"][0] or 0) > 0]
            note = f"; the page has a state {name}: compared in the analysis" if page_state and name in self.cfg["page_states"] else ""
            return "ok", f"{len(d['components'])} rows, {len(texts)} texts ({len(measured)} with a non-zero TextDimensions); root {d['root']}{note}", \
                {"rows": len(d["components"]), "root": d["root"], "file": f"dump_{name}.json"}
        return fn

    # -- the wrapper's line about Resize(w, h, false) in the mod's log, and the answer it keeps
    def sresize_log(self):
        d = self.data("resize_log")
        lines = d.get("lines") or []
        return ("ok" if lines else "info"), (f"ENGINE.children_keep {d.get('children_keep')} (true: Resize(w, h, false) keeps the children's sizes; false: the wrapper "
                                             f"gives them back after each resize); the mod log read {d.get('log_read')}; its lines: {lines[-3:] or 'none'}"), d

    def slot_look(self, name, node, page_state, title):
        """A slot's look as the game draws it: a close-up picture, its building window, and its components dumped for the analysis to compare
        with the page's slot in the same state (page_state: build/ui_dump/<state>.json, its slot the one its actions hover)."""
        i = node["index"]
        box = self.data("slot_box", {"index": i})
        crop = {"x": box.get("x", 0) - 60, "y": box.get("y", 0) - 50, "w": (box.get("w") or 74) + 200, "h": (box.get("h") or 74) + 110} if "x" in box else None
        self.data("hover", {"id": "frame"})
        self.sleep(0.4)
        self.shoot(f"ss_{name}", crop)
        h = self.data("hover", {"id": f"mtb_tree_node_{i}", "keys": [node["key"]]})
        self.sleep(0.6)
        self.shoot(f"ss_{name}_info")
        only = [f"mtb_tree_node_{i}", f"mtb_tree_node_dev_{i}", f"mtb_tree_node_cost_{i}", f"building_information_{i}", "frame/points", "frame/points_icon", "frame/gold"]
        self.dump(name, keys=[node["key"]], only=only, look={"index": i, "key": node["key"], "page": page_state, "title": title})
        self.data("hover", {"id": "frame"})
        return h

    # -- the development points: the header's number, a slot's teal round (red when short), its window's reason (the page's early_tree_short)
    def spoints(self):
        nodes = self.data("nodes")["nodes"]
        st = self.data("state", {"keys": [n["key"] for n in nodes]})
        short = [n for n in nodes if n.get("short")]
        rounds = [n for n in nodes if (st["levels"].get(n["key"]) or {}).get("dev_visible")]
        target = (short or rounds or [None])[0]
        root = self.data("root")
        fx, fy = (root["w"] - min(root["w"] - 40, 1560)) / 2, (root["h"] - min(root["h"] - 30, 870)) / 2      # the panel's frame (panel.js makePanel)
        self.shoot("ss_points_header", {"x": fx, "y": fy, "w": 600, "h": 70})
        if not target:
            return "info", f"header points «{st.get('points_text')}»; no slot shows a round of points (none costs any, or all stand)", {"state": st}
        h = self.slot_look("points_short" if target in short else "points_round", target, "early_tree_short", "a slot short of development points" if target in short else "a slot that costs points")
        lv = (h.get("state") or {}).get("levels", {}).get(target["key"]) or {}
        lv = lv or (self.data("state", {"keys": [target["key"]]})["levels"].get(target["key"]) or {})
        answer = (f"header points «{st.get('points_text')}» (the game's DevelopmentPoints {(self.data('points') or {}).get('points')}); {len(short)} slots short of points, "
                  f"{len(rounds)} with a round; {target['name']} ({target['key'].removeprefix(pp.PREFIX)}): round {lv.get('dev_visible')} «{lv.get('dev_text')}», price «{lv.get('cost_text')}», "
                  f"padlock {lv.get('padlock')}; its window {h.get('info') or 'NOT shown'}; pictures ss_points_short*.png / ss_points_round*.png")
        return ("ok" if lv.get("dev_visible") and h.get("info") else "differs"), answer, {"state": st, "target": target, "hover": h}

    # -- the windows under the mouse in the game's own drawing: a slot with links (lit links, rings), a locked slot close up
    def shover_shots(self):
        nodes = self.data("nodes")["nodes"]
        linked = [n for n in nodes if n.get("requires")] or nodes
        out = {}
        a = linked[min(len(linked) - 1, 3)]
        out["links"] = self.data("hover", {"id": f"mtb_tree_node_{a['index']}", "keys": [a["key"]]})
        self.sleep(0.6)
        self.shoot("ss_hover_links")
        self.data("hover", {"id": "frame"})
        locked = [n for n in nodes if n["state"] == "locked" and not n.get("short") and not n.get("poor")]
        if locked:
            n = locked[0]
            box = self.data("slot_box", {"index": n["index"]})
            out["locked"] = self.data("hover", {"id": f"mtb_tree_node_{n['index']}", "keys": [n["key"]]})
            self.sleep(0.6)
            self.shoot("ss_hover_locked", {"x": box["x"] - 60, "y": box["y"] - 50, "w": box["w"] + 520, "h": box["h"] + 260} if "x" in box else None)
            self.data("hover", {"id": "frame"})
        lk = (out["links"] or {}).get("links") or {}
        return ("ok" if lk.get("lit") else "differs"), (f"{a['name']}: lit pieces {lk.get('lit')}, rings needed {lk.get('needed')} / opened {lk.get('opened')}, window "
                                                        f"{'shown' if out['links'].get('info') else 'NOT shown'}; locked {locked[0]['name'] if locked else 'none'}: window "
                                                        f"{'shown' if (out.get('locked') or {}).get('info') else 'NOT shown'}; ss_hover_links.png, ss_hover_locked.png (+ _crop)"), out

    # -- d. behaviour
    def pick_key(self):
        """The first open building of the tree that is not the hull (the hull cannot be demolished in the game: CanDismantle false), one turn
        long if there is one (it must complete in the session's one turn); else the first open one."""
        nodes = self.data("nodes")["nodes"]
        opened = [n for n in nodes if n["state"] == "open" or n.get("short")]       # short of points only: the step gives them (ensure)
        # not the hull, nor what rests on the chain this session demolishes (the beer hall of the requirement test)
        avoid = set(self.cfg.get("req_test", {}).get("chain_keys") or [])
        side = [n for n in opened if not n.get("hull") and not avoid & set(n.get("requires") or []) and n["key"] not in avoid]
        one = [n for n in side if n.get("turns") == 1]
        pick = (one or side or opened or [None])[0]
        return pick, nodes

    def click_sim(self, id_, keys, done):
        """A click by the game's own event (SimulateLClick on our component: ComponentLClickUp reaches the panel's listener, probe 14.11 item 5),
        read 1.5 s later; only if it did nothing, the listener's own function. Returns (state, way)."""
        self.right_after = self.data("click", {"id": id_, "keys": keys, "way": "simulate"}, 30).get("state")
        self.sleep(1.5)
        st = self.data("state", {"keys": keys})
        if done(st):
            return st, "simulate"
        self.data("click", {"id": id_, "keys": keys, "way": "direct"}, 30)
        self.sleep(1.5)
        return self.data("state", {"keys": keys}), "direct (the simulated click did nothing)"

    def ensure(self, key, label):
        """What the game reads before an order of key (the adapter's slot): gold, development points, its gates. Points or gold short: the
        difference given by script, as the probe's setup does (the session of 14.11 had 0 points and every order was refused), and said so.
        -> (gates, text)"""
        g = self.data("gates", {"key": key})
        have, need = g.get("points"), g.get("dev") or 0
        short_dev = need - (have or 0) if need else 0
        short_gold = (g.get("cost") or 0) - (g.get("gold") or 0)
        text = f"before: points {have}, the level asks {need}; gold {g.get('gold')}, cost {g.get('cost')}; IsActive {g.get('active')} (enough {g.get('enough')}, afford {g.get('afford')}, locked by level {g.get('locked_by_level')}); the panel {(g.get('panel') or {}).get('state')}"
        if short_dev > 0 or short_gold > 0:
            gave = self.data("give", {"dev": max(0, short_dev), "gold": max(0, short_gold) + (1000 if short_gold > 0 else 0)})
            self.gifts.append({"step": label, "key": key, **gave})
            g2 = self.data("gates", {"key": key})
            text += (f"; SHORT, given by script: points {gave['before'].get('points')} -> {gave['after'].get('points')}, gold {gave['before'].get('gold')} -> "
                     f"{gave['after'].get('gold')}; now IsActive {g2.get('active')}, the panel {(g2.get('panel') or {}).get('state')}")
            g = dict(g2, given=gave, before=g)
        return g, text

    def control(self, key, slot):
        """The probe's own order helper (worked in run 20261114-222543), same building, same slot, right after the adapter's refused one: taken
        here and not there isolates the adapter. Cancelled at once when taken."""
        o = self.data("pp", {"item": "order", "args": {"key": key, "slot": slot, "way": "own"}})
        self.sleep(1.5)
        chk = self.data("pp", {"item": "check", "args": {"key": key, "slot": slot, "gold_before": o.get("gold_before")}})
        out = {"order": o, "check": chk, "taken": chk.get("accepted")}
        if chk.get("accepted"):
            out["cancel"] = self.data("pp", {"item": "cancel", "args": {"key": key, "slot": slot}})
            self.sleep(1.5)
        return out

    def record(self, what, key, before, after):
        self.actions.append({"do": what, "key": key, "gold_before": (before.get("treasury") or {}).get("game"), "points_before": before.get("points"),
                             "growth_before": (before.get("growth") or {}).get("now"),
                             "got": {k: after.get(k) for k in ("message", "first_step", "unseen", "news", "foot", "mark", "crew_upkeep", "turn")},
                             "status": ((after.get("levels") or {}).get(key) or {}).get("status", {}).get("state") if key else None,
                             "treasury": after.get("treasury")})

    def sorder(self, label="order"):
        def fn():
            if not self.key:
                pick, nodes = self.pick_key()
                if not pick:
                    poor = [n for n in nodes if n.get("poor")]
                    return "failed", f"no node open to order (poor: {[n['name'] for n in poor[:5]]})", {"nodes": nodes[:20]}
                self.key, self.node = pick["key"], pick
            k = self.key
            gates, gtext = self.ensure(k, label)
            cost = self.data("cost", {"key": k})
            before = self.data("state", {"keys": [k]})
            after, way = self.click_sim(f"mtb_tree_node_{self.node['index']}", [k], lambda st: st["levels"][k]["status"].get("state") == "building")
            self.record("order", k, before, after)
            lv = after["levels"][k]
            paid = (before["treasury"].get("game") or 0) - (after["treasury"].get("game") or 0)
            ok = lv["status"].get("state") == "building" and lv.get("under_construction") is not None and any(c.get("level") == k for c in lv.get("construction") or [])
            # DEFECT 1 of 20261115-012811: the order went in and the panel said it did not. Now: nothing said until the game applies it, then the truth
            ra = getattr(self, "right_after", None) or {}
            ra_lv = (ra.get("levels") or {}).get(k) or {}
            said_ok = str(after.get("message") or "").startswith("Заказано: «")
            same_t = after["treasury"].get("game") == after["treasury"].get("adapter")
            game_cost = (cost.get("cost") or {}).get("v")
            answer = (f"{self.node['name']} ({k.removeprefix(pp.PREFIX)}) by {way}: status {lv['status'].get('state')}, adapter turns {lv.get('under_construction')}, "
                      f"game construction (slot re-read) {lv.get('construction')}; paid {paid} (the tree says {self.node.get('cost')}, the game's CreateCost {game_cost}, "
                      f"CreateTime {(cost.get('time') or {}).get('v')}); treasury game {after['treasury'].get('game')} adapter {after['treasury'].get('adapter')}; "
                      f"message «{after.get('message')}»; foot «{after.get('foot')}»; RIGHT AFTER THE CLICK (the game not yet applied): status "
                      f"{ra_lv.get('status')}, message «{ra.get('message')}»")
            ctrl = None
            if not ok:
                ctrl = self.control(k, gates.get("slot"))
                answer += (f"; CONTROL by the probe's helper, same building, slot {gates.get('slot')}: {'TAKEN (the adapter differs)' if ctrl.get('taken') else 'refused too (the game refuses it: see the gates)'}")
            answer = gtext + "; " + answer
            status = "ok" if ok and same_t and paid == self.node.get("cost") and said_ok else ("differs" if ok else "failed")
            return status, answer, {"before": before, "way": way, "cost": cost, "after": after, "right_after": ra, "gates": gates, "control": ctrl}
        return fn

    def scancel(self):
        k = self.key
        if not k:
            return "skipped", "nothing ordered", {}
        before = self.data("state", {"keys": [k]})
        ra = self.data("click", {"id": f"mtb_tree_node_{self.node['index']}", "keys": [k]}, 30).get("state") or {}
        self.sleep(1.5)
        after = self.data("state", {"keys": [k]})
        self.record("cancel", k, before, after)
        lv = after["levels"][k]
        back = (after["treasury"].get("game") or 0) - (before["treasury"].get("game") or 0)
        ok = lv["status"].get("state") == "open" and not lv.get("construction")
        said_ok = str(after.get("message") or "").startswith("Отменено: «")
        answer = (f"status {lv['status'].get('state')}, construction {lv.get('construction')}; gold back {back} (paid {self.node.get('cost')}); points "
                  f"{before.get('points')} -> {after.get('points')}; message «{after.get('message')}»; right after the click: status "
                  f"{((ra.get('levels') or {}).get(k) or {}).get('status')}, message «{ra.get('message')}»")
        return ("ok" if ok and back == self.node.get("cost") and said_ok else "differs" if ok else "failed"), answer, {"before": before, "right_after": ra, "after": after}

    def stabs(self):
        out = {}
        out["ship"], w1 = self.click_sim("mtb_tab_ship", [], lambda st: st.get("tab") == "ship")
        self.shoot("ss_tab_ship")
        out["tree"], w2 = self.click_sim("mtb_tab_tree", [], lambda st: st.get("tab") == "tree")
        ok = out["ship"].get("tab") == "ship" and out["tree"].get("tab") == "tree"
        return ("ok" if ok else "failed"), (f"tab after «Корабль» ({w1}): {out['ship'].get('tab')}, mark {out['ship'].get('mark')}; after «Постройки» ({w2}): "
                                            f"{out['tree'].get('tab')}"), out

    def sinfo(self):
        # the first slot the mouse can be on (the panel lets a slot outside the tree's window take no hover: src/tww3_mtb_ship_uic.lua reachable)
        first = self.node["index"] if self.key else 0
        nodes = self.data("nodes")["nodes"]
        for idx in [first] + [n["index"] for n in nodes if n["index"] != first][:40]:
            h = self.data("hover", {"id": f"mtb_tree_node_{idx}", "profile": True})
            if h.get("hovered") == f"mtb_tree_node_{idx}":
                break
        self.sleep(0.8)
        self.shoot("ss_info_window")
        info = h.get("info")
        self.data("hover", {"id": "frame"})
        return ("ok" if info else "failed"), (f"hover on mtb_tree_node_{idx}: hovered {h.get('hovered')}, building window {info or 'NOT shown'}; "
                                              f"{self.logic_text(h.get('logic'))}"), h

    def sunit(self):
        ids = self.data("ids", {"prefix": "mtb_crew_card_"})["ids"]
        ids = [i for i in ids if not i.startswith("mtb_crew_card_pick_")]
        army = self.data("ids", {"prefix": "mtb_army_card_"})["ids"]
        if not (ids or army):
            return "info", "no unit card on the tree", {}
        # the first card the mouse can be on (one outside the tree's window takes no hover)
        for target in (ids + army)[:30]:
            h = self.data("hover", {"id": target})
            if h.get("unit") or h.get("hovered") == target:
                break
        self.sleep(0.8)
        self.shoot("ss_unit_panel")
        self.data("hover", {"id": "frame"})
        return ("ok" if h.get("unit") or target.startswith("mtb_army") else "differs"), f"hover on {target}: unit panel {h.get('unit') or 'not shown'}", h

    def spicker(self):
        p = self.data("places")
        open_places = [x for x in p["places"] if x.get("place")]
        if not open_places:
            return "info", f"no crew place is open (the barge carried: {p.get('carried')}): the picker and its unit panel cannot be reached in a fresh campaign", p
        g = open_places[0]["group"]
        self.data("click", {"id": "mtb_tab_ship"})
        r = self.data("click", {"id": f"mtb_crew_area_{g}"})
        self.sleep(0.8)
        self.shoot("ss_crew_picker")
        picks = self.data("ids", {"prefix": f"mtb_crew_card_pick_{g}:"})["ids"]
        h = {}
        for pid in picks[:4]:       # the «nobody» card has no unit panel
            h = self.data("hover", {"id": pid})
            if h.get("unit"):
                break
        self.sleep(0.6)
        self.shoot("ss_crew_unit")
        opened = [x for x in self.data("places")["places"] if x.get("open")]
        e = self.data("escape", {})
        still = [x for x in self.data("places")["places"] if x.get("open")]
        self.data("click", {"id": "mtb_tab_tree"})
        ok = bool(opened) and not still and e.get("state", {}).get("open")
        return ("ok" if ok else "differs"), (f"place {g}: picker open {[x['group'] for x in opened]}, {len(picks)} cards; unit panel {h.get('unit')}; Esc: picker still open "
                                             f"{[x['group'] for x in still] or 'none'}, the panel still open {e.get('state', {}).get('open')}"), {"places": p, "click": r, "hover": h}

    def sscroll(self):
        bars = self.data("ids", {"prefix": "tree_bar_"})["ids"]
        before = self.data("state")
        steps = []
        for id_ in [i for i in ("tree_bar_bottom", "tree_bar_right", "tree_bar_track_vertical", "tree_bar_top", "tree_bar_left") if i in bars]:
            r = self.data("click", {"id": id_})
            steps.append({"id": id_, "pan": r["state"].get("pan")})
        self.sleep(0.6)
        self.shoot("ss_scrolled")
        moved = [s for s in steps if s["pan"] != before.get("pan")]
        return ("ok" if moved or not bars else "differs"), f"bars {bars}; pan before {before.get('pan')}; after each click {[(s['id'], s['pan']) for s in steps]}", {"steps": steps}

    def sviews(self):
        """The pictures the reviewer of 20261115-012811 asked for, each isolated: the tree at its very top and bottom, a slot short of points not
        hovered, a building window near the bottom right corner; the drawing's own time by section (src/tww3_mtb_ship_ui.lua profile)."""
        out = {"drawing_profile_before": self.data("drawing_profile").get("profile")}
        self.data("click", {"id": "mtb_tab_tree"})
        for where in ("bottom", "top"):
            out[where] = self.data("pan", {"where": where})
            self.sleep(0.6)
            self.shoot(f"ss_tree_{where}")
        out["short"] = self.data("pan", {"status": "short"})
        self.sleep(0.6)
        self.shoot("ss_short_unhovered")
        out["bottom_again"] = self.data("pan", {"where": "bottom"})
        c = self.data("corner_slot")
        if c.get("id"):
            out["corner"] = self.data("hover", {"id": c["id"]})
            self.sleep(0.6)
            self.shoot("ss_info_corner")
            self.data("hover", {"id": "frame"})
        out["drawing_profile"] = self.data("drawing_profile").get("profile")
        ok = all(out.get(k, {}).get("pan") for k in ("bottom", "top"))
        return ("ok" if ok else "differs"), (f"bottom {out['bottom'].get('pan')}, top {out['top'].get('pan')}, a short slot shown {out['short'].get('shown')}, "
                                             f"corner window {(out.get('corner') or {}).get('info')}"), out

    def sviews_after_turn(self):
        """After the turn: «Корабль» with the turn's news, the crew list beside the tree, the drawing's own time of the refreshes."""
        out = {}
        self.data("click", {"id": "mtb_tab_ship"})
        # the player looked at «Корабль»: the tab's «!» goes (the panel's M.ship_seen); the offline replay must do the same (analyse, E)
        self.actions.append({"do": "ship_seen"})
        self.sleep(0.8)
        self.shoot("ss_ship_after_turn")
        self.data("click", {"id": "mtb_tab_tree"})
        self.sleep(0.6)
        self.shoot("ss_crew_list_after_turn")
        out["drawing_profile"] = self.data("drawing_profile").get("profile")
        return "ok", "«Корабль» and the crew list after the turn shot; the drawing's profile kept", out

    def sfit(self):
        self.data("profile_mark")
        r = self.data("click", {"id": "mtb_tree_fit"}, 120)
        pr = self.data("profile_read")
        prof, logic = pr.get("profile"), pr.get("logic")
        self.sleep(1.0)
        self.shoot("ss_whole_tree")
        # a slot's building window over the whole tree made smaller (the window keeps the game's size)
        h = self.data("hover", {"id": "mtb_tree_node_0"})
        self.sleep(0.6)
        self.shoot("ss_whole_tree_hover")
        self.data("hover", {"id": "frame"})
        r2 = self.data("click", {"id": "mtb_tree_fit"}, 120)
        a, b = r["state"], r2["state"]
        ok = (a.get("pan") or {}).get("z", 1) < 1 and (b.get("pan") or {}).get("z") == 1
        return ("ok" if ok else "differs"), (f"«Всё дерево»: z {(a.get('pan') or {}).get('z')} label «{a.get('fit_label')}» in {r.get('seconds', 0):.2f} s "
                                             f"(PROFILE: {self.profile_text(prof)}; {self.logic_text(logic)}); hover there: window {h.get('info') or 'NOT shown'}; "
                                             f"«Вблизи»: z {(b.get('pan') or {}).get('z')} label «{b.get('fit_label')}» in {r2.get('seconds', 0):.2f} s"), {"fit": r, "profile": prof, "hover": h, "back": r2}

    def sclose(self):
        before = self.data("state")
        self.data("click", {"id": "mtb_ship_close"})
        self.sleep(1.0)
        c = self.data("closed")
        r = self.data("reopen", {}, 200)
        self.sleep(0.8)
        after = r.get("state") or {}
        ok = not c.get("is_open") and not c.get("root_visible") and r.get("ok") and after.get("tab") == before.get("tab") and after.get("pan") == before.get("pan") and r.get("reused")
        return ("ok" if ok else "differs"), (f"after the cross: open {c.get('is_open')}, our root left {c.get('root_left')} (on the screen {c.get('root_visible')}); reopened {r.get('ok')} in "
                                             f"{r.get('build_seconds', 0):.2f} s, shown again without a rebuild (S.reused) {r.get('reused')}; tab {before.get('tab')} -> {after.get('tab')}, "
                                             f"pan {before.get('pan')} -> {after.get('pan')}; PROFILE of the reopen: {self.profile_text(r.get('profile'))}; "
                                             f"{self.logic_text(r.get('logic'))}"), {"closed": c, "reopen": r}

    def sescape(self):
        e = self.data("escape", {})
        self.sleep(0.8)
        closed = self.data("closed")
        r = self.data("reopen", {}, 200)
        ok = (not e.get("err")) and not closed.get("is_open") and r.get("ok")
        return ("ok" if ok else "failed"), f"Esc with nothing open: panel open after {closed.get('is_open')} (expected closed); reopened {r.get('ok')}; {e.get('err') or ''}", {"escape": e, "reopen": r}

    def ssave(self, label):
        def fn():
            d = self.data("save_check", {}, 30)
            bad, rt = d.get("differ") or [], d.get("round_trip_differ") or []
            shared = {k: (d["before"].get(k), d["want"].get(k)) for k in d.get("want", {}) if k.startswith("mtb_crew_") and k not in ("mtb_crew_groups", "mtb_crew_chosen")}
            answer = (f"{len(d.get('want', {}))} keys saved; read back differ: {[x['key'] for x in bad] or 'none'}; Ship.load_state then save again differs: "
                      f"{[x['key'] for x in rt] or 'none'}; keys shared with the old mod (before -> now): {shared or 'none'}; old mod's get() {d.get('old_mod_get_before')} -> {d.get('old_mod_get_after')}")
            return ("ok" if not bad and not rt else "differs"), answer, d
        return fn

    # -- e. one turn
    # -- the FIRST game-state action: does level II of a chain satisfy a requirement on level I? (port-to-game.md 8.4, first row)
    def srequirement(self):
        """On the idle force of the new campaign (nothing under construction: cm:add_building_to_force is used only so, probe 14.11 item 1):
        hull II stood (the weapons store is tier 2; hull I would lock it by tier whatever its requirement), then beer hall I, then beer hall II
        over it; after each the game's IsActiveForBuildingBrowser of the weapons store against an EMPTY slot; then one real order of it, the slot
        read again, and the order cancelled in the same turn (immediate, full refund) so the force is idle again."""
        rq = self.cfg.get("req_test") or {}
        if not rq.get("store"):
            return "skipped", f"the config has no «Склад оружия» / «Пивной чертог» I, II: {rq}", rq
        out = {"keys": rq}

        def active(r):
            return next((x["r"].get("v") for x in r.get("reads", []) if x["expr"].startswith("char ") and "IsActiveForBuildingBrowser" in x["expr"]), None)

        def read(label):
            fe = self.data("pp", {"item": "first_empty"})
            n = fe.get("slot")
            r = self.data("pp", {"item": "avail", "args": {"key": rq["store"], "slot": n}}) if n is not None else {"err": "no empty slot"}
            out[label] = {"slot": n, "active": active(r), "slots": fe.get("info", {}).get("slots"), "reads": r.get("reads")}
            return out[label]["active"]
        start = self.data("pp", {"item": "slots"})
        pending = [i for i in range(1, start["num_items"]) if self.data("pp", {"item": "slot_read", "args": {"slot": i}}).get("item")]
        if pending:
            return "skipped", f"a construction is pending in slots {pending}: no script add on a busy force (probe 14.11, item 1)", start
        # the session of 14.11 read IsActive False in every state: HasEnoughDevelopmentPoints was False (0 points, the store asks 2) while gold, tier
        # and slot were right. Points first (the probe's setup gave 50), so that the only thing left to decide the read is the requirement.
        # Script-stood buildings do not spoil the read on an idle force: the probe stood the hatches' parents so and the order was taken (222543 item 1).
        g0 = self.data("gates", {"key": rq["store"]})
        out["points_at_start"] = {"points": g0.get("points"), "store_asks": g0.get("dev"), "gold": g0.get("gold")}
        need = max(0, (g0.get("dev") or 2) - (g0.get("points") or 0))
        out["given"] = self.data("give", {"dev": need, "gold": 0 if (g0.get("gold") or 0) >= 10000 else 10000}) if need else None
        a0 = read("hull_1_only")
        if start["slots"][0] != rq["hull2"]:
            out["add_hull"] = self.data("pp", {"item": "add", "args": {"keys": [rq["hull2"]]}})
        a_h = read("hull_2")
        out["add_beer_1"] = self.data("pp", {"item": "add", "args": {"keys": [rq["beer1"]]}})
        a1 = read("beer_1")
        out["add_beer_2"] = self.data("pp", {"item": "add", "args": {"keys": [rq["beer2"]]}})
        a2 = read("beer_2")
        slots = out["beer_2"]["slots"] or []
        replaced = rq["beer2"] in slots and rq["beer1"] not in slots
        n = out["beer_2"]["slot"]
        order = {}
        if n is not None:
            o = self.data("pp", {"item": "order", "args": {"key": rq["store"], "slot": n, "way": "own"}})
            self.sleep(1.5)
            chk = self.data("pp", {"item": "check", "args": {"key": rq["store"], "slot": n, "gold_before": o.get("gold_before")}})
            order = {"order": o, "check": chk, "taken": chk.get("accepted")}
            if chk.get("accepted"):
                c = self.data("pp", {"item": "cancel", "args": {"key": rq["store"], "slot": n}})
                self.sleep(1.5)
                order["cancel"] = c
                order["after_cancel"] = self.data("pp", {"item": "slot_read", "args": {"slot": n}})
                order["gold_after_cancel"] = self.data("pp", {"item": "slots"}).get("gold")
        out["order"] = order
        out["points_after"] = self.data("points")
        g1 = {x["expr"].split(").", 1)[-1]: (x.get("r") or {}).get("v") for x in (out.get("beer_1") or {}).get("reads") or [] if x["expr"].startswith("char ")}
        if a1 is not True:
            verdict = (f"INCONCLUSIVE: with beer hall I standing the store is not active either ({a1}): something else blocks it: HasEnoughDevelopmentPoints "
                       f"{g1.get('HasEnoughDevelopmentPoints(this)')}, CanAfford {g1.get('CanAfford(this)')}, IsLockedByLevel {g1.get('IsLockedByLevel(this)')}")
        elif a2 is True:
            verdict = "II SATISFIES the requirement on I (active with II standing)"
        else:
            verdict = f"ONLY LEVEL I satisfies it: active with I, {a2} with II (port-to-game.md 8.3 options (б)/(в))"
        pts = out["points_at_start"]
        answer = (f"points at the start {pts['points']} (the store asks {pts['store_asks']})"
                  + (f", {need} given by script ({out['given']['before'].get('points')} -> {out['given']['after'].get('points')})" if out.get("given") else "")
                  + f"; points after the order and its cancel {out['points_after'].get('points')}; "
                  f"[REQUIREMENT II vs I] {verdict}; the real order with II standing {'TAKEN' if order.get('taken') else 'REFUSED'} (slot re-read "
                  f"{(order.get('check') or {}).get('item_level')}); IsActive with hull I only {a0}, hull II {a_h}, beer I {a1}, beer II {a2}; "
                  f"beer II replaced I in its slot: {replaced}; the order cancelled in the same turn: {bool(order.get('cancel'))}")
        status = "info" if "INCONCLUSIVE" not in verdict else "differs"
        return status, answer, out

    # -- the fresh campaign: what refuses an order before anything is done (points, gold, tier, the slot), read only
    def sgates_fresh(self):
        rq = self.cfg.get("req_test") or {}
        keys = [k for k in (rq.get("store"), rq.get("beer1"), rq.get("hull2"), self.cfg.get("nest_key")) if k]
        rows = {k.removeprefix(pp.PREFIX): self.data("gates", {"key": k}) for k in keys}
        pts = next(iter(rows.values()), {}).get("points")
        answer = f"points {pts}, gold {next(iter(rows.values()), {}).get('gold')}, hull level {next(iter(rows.values()), {}).get('hull_level')}; " + "; ".join(
            f"{k}: asks {r.get('dev')} points / {r.get('cost')} gold, IsActive {r.get('active')} (enough {r.get('enough')}, afford {r.get('afford')}, "
            f"locked by level {r.get('locked_by_level')}), slot {r.get('slot')}" for k, r in rows.items())
        return "info", answer, rows

    # -- the panel's verdict on every building against the game's IsActiveForBuildingBrowser
    def sagree(self, label):
        def fn():
            d = self.data("agree", {}, 90)
            bad = d.get("disagree") or []
            states = {}
            for r in d.get("rows") or []:
                states[r["state"]] = states.get(r["state"], 0) + 1
            answer = (f"{label}: points {d.get('points')}, gold {d.get('gold')}; the panel's states {states}; disagreements {len(bad)}: " +
                      ("; ".join(f"{r['key'].removeprefix(pp.PREFIX)} panel {r['state']} ({r.get('why') or ''}) vs game {r.get('active')} {r.get('gates')}" for r in bad[:8]) or "none"))
            return ("ok" if not bad else "differs"), answer, d
        return fn

    # -- cheap engine facts
    def sopacity(self):
        d = self.data("opacity_test")
        self.sleep(0.8)
        self.shoot("ss_opacity_parent_with_image")
        self.data("clear")
        return "info", "parent with an image, child image: " + "; ".join(
            f"{k}: parent {v.get('parent')}, child {v.get('child')}" + (f" ({v.get('err')})" if v.get("err") else "") for k, v in d.items()) + \
            "; picture ss_opacity_parent_with_image.png", d

    def sframes(self, label):
        def fn():
            self.data("frames_on")
            t0 = time.time()
            self.sleep(3.0)
            d = self.data("frames_off")
            wall = time.time() - t0
            fps = round(d.get("frames", 0) / wall, 1) if wall > 0 else None
            self.frames = getattr(self, "frames", {})
            self.frames[label] = fps
            return "info", f"{label}: {d.get('frames')} timer calls in {wall:.1f} s = {fps} per second (one per frame at most)", {**d, "wall": wall, "fps": fps}
        return fn

    # -- demolish BEFORE the turn: the game keeps the building until the turn ends (probe 14.11, 8.2); the turn step reads what happened
    def sdemolish(self):
        out = {}
        if getattr(self, "node", None) and self.node.get("hull"):
            out["hull"] = self.data("can_demolish", {"key": self.key})
        rq = self.cfg.get("req_test") or {}
        k = rq.get("beer2")
        nodes = {n["key"]: n for n in self.data("nodes")["nodes"]}
        node = nodes.get(k)
        st = self.data("state", {"keys": [k]}) if node else None
        if not node or st["levels"][k]["status"].get("state") != "built":
            return "skipped", f"{k} not standing (the requirement step did not stand it): nothing to demolish", {**out, "state": st}
        dlg = self.data("dialog")
        out["dialog"] = dlg
        if dlg.get("open"):
            return "skipped", f"a window of the game is open on the screen ({dlg.get('text')}): the dismantle is issued only with none (probe 14.11, 8.2)", out
        # session 14.11 stopped here for a dialogue_box that was present but not on the screen (VisibleFromRoot {dlg.get('visible_from_root')})
        slot = st["levels"][k].get("model_slot")
        can = self.data("dismantle_read", {"key": k, "slot": slot})
        sel = self.data("click", {"id": f"mtb_tree_node_{node['index']}", "keys": [k]})
        self.sleep(0.6)
        self.shoot("ss_raze_button")
        if not sel["state"].get("raze"):
            return "differs", f"the built slot clicked: options {sel['state'].get('options')}, the round button not shown", {**out, "select": sel}
        before = sel["state"]
        r = self.data("click", {"id": "mtb_ship_demolish", "keys": [k]})
        self.sleep(2.0)
        read = self.data("dismantle_read", {"key": k, "slot": slot})
        self.record("demolish", k, before, read["state"])
        self.dismantled = {"key": k, "slot": slot, "gold": read["state"]["treasury"].get("game")}
        hull = out.get("hull")
        hull_txt = ""
        if hull:
            hull_txt = (f"hull {self.key.removeprefix(pp.PREFIX)}: the panel allows its demolish {hull.get('panel_ok')}, the game's CanDismantle {hull.get('game_can')}"
                        + (" (BUG: the panel offers what the game refuses)" if hull.get("panel_ok") and (hull.get("game_can") or {}).get("v") is False else "") + "; ")
        # observations only: the panel's dismantle state is being changed («being dismantled until the turn ends»)
        state = read["state"]["levels"][k]["status"].get("state")
        # the slot being dismantled as the game draws it (the page's dismantling_tree), and a click on it: refused with the reason
        look = {}
        if state == "dismantling":
            look["hover"] = self.slot_look("dismantling", node, "dismantling_tree", "a slot being dismantled")
            look["click"] = self.data("click", {"id": f"mtb_tree_node_{node['index']}", "keys": [k]})
        self.dismantled["points"] = before.get("points")
        answer = (hull_txt + f"{k.removeprefix(pp.PREFIX)} (slot {slot}): CanDismantle before {can.get('can')}; round button shown, the panel's preview "
                  f"«{((before.get('levels') or {}).get(k) or {}).get('demolish_preview')}»; after it the panel says "
                  f"«{read['state'].get('message')}», status {state} (expected dismantling); the game: slot model {read.get('model_slot')}, "
                  f"IsDismantling {read.get('dismantling')}, building {read.get('building')}; a dialogue_box present {dlg.get('present')} (on the screen {dlg.get('open')}, "
                  f"{dlg.get('text')}); the turn step reads the slot at the turn start; a click on it then: «{((look.get('click') or {}).get('state') or {}).get('message')}»; "
                  f"pictures ss_dismantling*.png")
        return ("ok" if state == "dismantling" else "differs"), answer, {**out, "can": can, "select": sel, "click": r, "read": read, "look": look}

    # -- an order of two turns or more, left for the turn: cancelled after it (the game's confirmation window)
    def sorder_long(self):
        nodes = self.data("nodes")["nodes"]
        avoid = set((self.cfg.get("req_test") or {}).get("chain_keys") or [])
        mine = {n["chain"] for n in nodes if n["key"] == self.key}
        cands = [n for n in nodes if (n["state"] == "open" or n.get("short")) and (n.get("turns") or 0) >= 2 and not n.get("hull") and n["chain"] not in mine
                 and not avoid & set(n.get("requires") or []) and n["key"] not in avoid]
        if not cands:
            self.long = None
            return "info", "no building of two turns or more is open: the cancel of an earlier turn's order cannot be tested", {}
        n = cands[0]
        gates, gtext = self.ensure(n["key"], "order_long")
        before = self.data("state", {"keys": [n["key"]]})
        after, way = self.click_sim(f"mtb_tree_node_{n['index']}", [n["key"]], lambda st: st["levels"][n["key"]]["status"].get("state") == "building")
        self.record("order", n["key"], before, after)
        self.long = n if after["levels"][n["key"]]["status"].get("state") == "building" else None
        return ("ok" if self.long else "failed"), (gtext + f"; {n['name']} ({n['turns']} turns) by {way}: status {after['levels'][n['key']]['status'].get('state')}, "
                                                   f"slot re-read {after['levels'][n['key']].get('construction')}; message «{after.get('message')}»"), {**after, "gates": gates}

    # -- e. one turn: the events as the panel sees them, the upkeep, the dismantle's end
    def sturn(self):
        k = self.key
        keys = [x for x in (k, (getattr(self, "dismantled", None) or {}).get("key"), (getattr(self, "long", None) or {}).get("key")) if x]
        before = self.data("state", {"keys": keys})
        pts_before = self.data("points")
        self.data("money_on")
        self.data("watch_on", {"keys": keys})
        mark = time.time()
        try:
            back = self.end_turn()
        finally:
            money = self.data("money_read")
            self.data("money_off")
            watch = self.data("watch_read")
            self.data("watch_off")
        (self.dir / "turn_events.json").write_text(json.dumps(watch, ensure_ascii=False, indent=1), encoding="utf-8")
        self.sleep(2)
        closed = self.data("closed")
        r = self.data("reopen", {}, 200)
        self.sleep(1.0)
        after = self.data("state", {"keys": keys})
        pts_after = self.data("points")
        self.record("end_turn", k, before, after)
        calls = money.get("calls") or []
        new = [c for c in calls if c.get("what") == "cm:treasury_mod" and "tww3_mtb_game" in str(c.get("stack"))]
        old = [c for c in calls if c.get("what") == "tww3_mtb_crew.pay_upkeep"]
        old_tm = [c for c in calls if c.get("what") == "cm:treasury_mod" and "tww3_mtb_crew" in str(c.get("stack")) and "tww3_mtb_game" not in str(c.get("stack"))]
        lv = (after.get("levels") or {}).get(k) or {}
        upkeep = ("BOTH charge" if new and (any(c.get("delta") for c in old) or old_tm) else "the new model only" if new else
                  "the old mod only" if any(c.get("delta") for c in old) or old_tm else "nobody charged (no crew standing)")
        evs = watch.get("events") or []
        seen = []
        for e in evs:
            b = e.get("building")
            seen.append(f"{e['event']}{'(' + b.removeprefix(pp.PREFIX) + ')' if b else ''}@t{e.get('turn')}: {((e.get('levels') or {}).get(k) or {}).get('state') if k else '-'}")
        dis = getattr(self, "dismantled", None)
        dis_txt = ""
        if dis:
            ts = next((e for e in evs if e["event"] == "FactionTurnStart"), None)
            at_start = ((ts or {}).get("levels") or {}).get(dis["key"]) or {}
            dem = [e["event"] for e in evs if "Demolish" in e["event"]]
            dis_txt = (f"; dismantled {dis['key'].removeprefix(pp.PREFIX)}: at our FactionTurnStart the game's slot model {at_start.get('model_slot')}, the panel's status "
                       f"{at_start.get('state')}; now {((after.get('levels') or {}).get(dis['key']) or {}).get('state')}; demolish events {dem or 'none'}; "
                       f"gold before the turn {dis.get('gold')}, after {after['treasury'].get('game')} (a refund is not told apart from income here: turn_events.json)")
        answer = (f"turn {'came back' if back else 'NOT back'} in {round(time.time() - mark)} s; the panel closed by the turn end: {not closed.get('is_open')}; "
                  f"reopened {r.get('ok')}; {k and k.removeprefix(pp.PREFIX)} now {lv.get('status', {}).get('state')} (model slot {lv.get('model_slot')}); "
                  f"mark {after.get('mark')}, unseen {after.get('unseen')}; message «{after.get('message')}»; events in order, with the panel's status of the order "
                  f"right after each: {seen}; upkeep: {upkeep} (new model's treasury_mod {[c.get('amount') for c in new]}, old pay_upkeep deltas "
                  f"{[c.get('delta') for c in old]}, old treasury_mod {[c.get('amount') for c in old_tm]}; new model's upkeep {before.get('crew_upkeep')})" + dis_txt +
                  f"; DEVELOPMENT POINTS and GROWTH of the turn (the game's horde browser expressions): points {pts_before.get('points')} -> {pts_after.get('points')}, "
                  f"growth {pts_before.get('growth')} -> {pts_after.get('growth')}, its parts before {pts_before.get('growth_parts')}; the adapter's growth "
                  f"{pts_before.get('adapter_growth')} -> {pts_after.get('adapter_growth')}; the panel waits for: «{pts_after.get('waiting')}»; "
                  f"MilitaryForceDevelopmentPointChange events {sum(1 for e in evs if e['event'] == 'MilitaryForceDevelopmentPointChange')}"
                  + (f"; points around the dismantle (the game's raze refund multiplier 0.8): {dis.get('points')} before it, {pts_after.get('points')} after the turn" if dis else ""))
        status = "ok" if back and lv.get("status", {}).get("state") == "built" and upkeep != "BOTH charge" else ("differs" if back else "failed")
        return status, answer, {"before": before, "after": after, "money": money, "watch": watch, "closed": closed, "reopen": r, "points": [pts_before, pts_after]}

    # -- the cancel of an earlier turn's order: the game asks; the window is answered by script (test only) and must be gone afterwards
    def scancel_previous(self):
        """DEFECT 2 of 20261115-012811: the window «Отменить строительство» was on the screen (ss_cancel_dialog.png) but a dialogue_box found by
        name was the HUD's hidden one (hud_campaign > rush_confirmation_holder > dialogue_box), so the adapter said «не прошла» and the session
        did not answer. Now: the adapter waits (pending, then asked), the window is taken from the game's events where they give it, its parents
        named; the tick answered by script (test only); gold, points and events before and after the answer."""
        n = getattr(self, "long", None)
        if not n:
            return "skipped", "no order of two turns was left for the turn", {}
        k = n["key"]
        before = self.data("state", {"keys": [k]})
        if before["levels"][k]["status"].get("state") != "building":
            return "info", f"{k} is no longer under construction after the turn ({before['levels'][k]['status']})", before
        self.data("watch_on", {"keys": [k]})
        self.data("panels_on")
        pts0 = self.data("points")
        ra = self.data("click", {"id": f"mtb_tree_node_{n['index']}", "keys": [k], "way": "direct"}).get("state") or {}
        self.sleep(1.5)
        asked = self.data("state", {"keys": [k]})
        dlg = self.data("dialog", {"guid": True})
        self.shoot("ss_cancel_dialog")
        if asked["levels"][k]["status"].get("asked"):
            self.dump("asked", keys=[k], only=[f"mtb_tree_node_{n['index']}", f"mtb_tree_node_dev_{n['index']}", f"mtb_tree_node_cost_{n['index']}", "frame/message"],
                      look={"index": n["index"], "key": k, "page": "asked_tree", "title": "a cancel waiting for the game's window"})
        pts1 = self.data("points")
        answered, after = None, asked
        if dlg.get("open"):
            answered = self.data("dialog_answer", {"button": "tick"})
            self.sleep(2.0)          # the adapter reads the slot every 250 ms while the window waits (src/tww3_mtb_game.lua ask)
            after = self.data("state", {"keys": [k]})
        dlg2 = self.data("dialog")
        gone = not dlg2.get("open")
        ev = self.data("watch_read").get("events")
        self.data("watch_off")
        if not gone:
            self.data("dialog_answer", {"button": "cancel"})
            self.sleep(1.0)
            gone = not self.data("dialog").get("open")
        self.data("panels_off")
        pts2 = self.data("points")
        self.record("cancel", k, before, after)
        g0, g1, g2 = before["treasury"].get("game"), asked["treasury"].get("game"), after["treasury"].get("game")
        win = dlg.get("window") or {}
        answer = (f"{n['name']}: right after the panel's click: status {((ra.get('levels') or {}).get(k) or {}).get('status')}, message «{ra.get('message')}»; "
                  f"1.5 s later: the panel says «{asked.get('message')}», status {asked['levels'][k]['status']} (expected building, asked); "
                  f"the window {'ON THE SCREEN by ' + str(dlg.get('way')) if dlg.get('open') else 'NOT FOUND'} (id {win.get('id')}, parents «{win.get('parents')}», "
                  f"text «{win.get('text')}», tick {win.get('tick')}); a dialogue_box by name: {dlg.get('by_name')}; ok_group {dlg.get('ok_group')}; FindByGuid {dlg.get('by_guid')}; the game's panel events {dlg.get('panels')}; "
                  f"answered {answered}; gold {g0} -> {g1} before the answer -> {g2} after the tick (paid {n.get('cost')}); points {pts0.get('points')} -> "
                  f"{pts1.get('points')} -> {pts2.get('points')}; the panel after the answer «{after.get('message')}», status "
                  f"{after['levels'][k]['status'].get('state')}, slot {after['levels'][k].get('construction')}; events {[e['event'] for e in ev or []]}; "
                  f"no window left afterwards: {gone}")
        refunded = g2 is not None and g1 is not None and g2 - g1 == n.get("cost")
        status = "ok" if gone and refunded and str(after.get("message") or "").startswith("Отменено: «") else ("differs" if dlg.get("open") else "failed")
        return status, answer, {"before": before, "right_after": ra, "asked": asked, "dialog": dlg, "answered": answered, "after": after, "dialog_after": dlg2,
                                "events": ev, "points": [pts0, pts1, pts2]}

    # -- orders after a battle, cleanly: a chain not in the force into an empty slot before (control) and after one battle
    def sbattle_orders(self):
        nodes = self.data("nodes")["nodes"]
        busy = set(self.data("pp", {"item": "slots"}).get("slots") or [])
        building = {n["key"] for n in nodes if n["state"] in ("building", "dismantling")}
        chains_busy = {n["chain"] for n in nodes if n["key"] in busy or n["key"] in building}
        # the session of 15.11 found none: after its turn the force had 0 points, every building «short» (locked by points only); ensure gives
        # the points and the gold by script, as for the other orders
        cands = [n for n in nodes if (n["state"] == "open" or n.get("short") or n.get("poor")) and not n.get("hull") and n["chain"] not in chains_busy]
        cands.sort(key=lambda n: (n["state"] != "open", n.get("turns") or 1))
        if not cands:
            return "info", f"no building of a chain not in the force is open or short of points / gold only: {[(n['key'].removeprefix(pp.PREFIX), n['state']) for n in nodes][:12]}", {}
        k = cands[0]["key"]
        res = {"key": k}

        def attempt(label):
            res[label + "_gates"], res[label + "_ensure"] = self.ensure(k, "battle_orders_" + label)
            fe = self.data("pp", {"item": "first_empty"})
            n = fe.get("slot")
            o = self.data("pp", {"item": "order", "args": {"key": k, "slot": n, "way": "own"}})
            self.sleep(1.5)
            chk = self.data("pp", {"item": "check", "args": {"key": k, "slot": n, "gold_before": o.get("gold_before")}})
            res[label] = {"slot": n, "order": o, "check": chk, "taken": chk.get("accepted")}
            if chk.get("accepted"):
                res[label]["cancel"] = self.data("pp", {"item": "cancel", "args": {"key": k, "slot": n}})
                self.sleep(1.5)
                res[label]["after_cancel"] = self.data("pp", {"item": "slot_read", "args": {"slot": n}})
            return chk.get("accepted")
        before = attempt("before")
        if self.fake:
            return "info", f"control before a battle: {'taken' if before else 'REFUSED'}; the battle is not simulated in the fake", res
        res["battle"] = self.battle()
        if res["battle"] != "back on the map":
            return "info", f"control before: {'taken' if before else 'REFUSED'}; no battle: {res['battle']}", res
        after = attempt("after")
        return "info", (f"[ORDER AFTER A BATTLE] {k.removeprefix(pp.PREFIX)} into an empty slot, points and gold ensured first: before the battle "
                        f"{'taken' if before else 'REFUSED'} ({res.get('before_ensure')}), right after it {'taken' if after else 'REFUSED'} ({res.get('after_ensure')}) "
                        f"(slot re-read; each cancelled in its turn)"), res

    def ssimulated(self):
        h = self.data("hover", {"id": "mtb_tree_node_0", "way": "simulate"})
        self.sleep(0.6)
        return "info", f"SimulateMouseOn on mtb_tree_node_0 -> hovered {h.get('hovered')} (the probe: no ComponentMouseOn comes to Lua; the panel's hovers are called directly)", h

    def sfinish(self):
        d = self.data("finish")
        return "info", f"closed at the end; started by {d.get('how')}; timer calls per second {getattr(self, 'frames', {})}", d

    def run(self):
        order = [("census", "Lua environment census (the probe's, standalone)", self.icensus),
                 ("smoke", "each of this session's helpers once, protected, a canary of the game's bindings after each", self.ssmoke),
                 ("gates_fresh", "the fresh campaign, read only: development points, gold, hull, and every gate of the game for the first buildings", self.sgates_fresh),
                 ("requirement", "FIRST game state: does level II of a chain satisfy a requirement on level I (idle force, empty slot, points given first, one real order)", self.srequirement),
                 ("load", "the panel's modules by the switch (tww3_mtb_crew_ui.ship_screen()), else loadfile + our environment, else inline", self.sload),
                 ("configure", "the probe's answers as ENGINE / ASSUMED options on the screen's modules (OPTIONS, --option)", self.sconfigure),
                 ("frames_closed", "timer calls per second, the panel closed", self.sframes("closed")),
                 ("open", "the panel opened: components, build time, root, how the texts were measured", self.sopen),
                 ("frames_open", "timer calls per second with ~3800 components on screen", self.sframes("open")),
                 ("agree", "the panel's verdict on every building against the game's IsActiveForBuildingBrowser (and its gates where they disagree)", self.sagree("before the orders")),
                 ("dump_fresh_tree", "the live panel dumped (page state fresh_tree)", self.sdump("fresh_tree")),
                 ("info", "a building's window by the hover handler (page state fresh_tree_info); over the advisor and the event feed: see the picture", self.sinfo),
                 ("dump_fresh_tree_info", "dump with the window shown", self.sdump_hover("fresh_tree_info")),
                 ("dump_fresh_ship", "the «Корабль» tab dumped (page state fresh_ship)", self.sdump_tab("fresh_ship")),
                 ("resize_log", "the wrapper's mod-log line about Resize(w, h, false) and ENGINE.children_keep", self.sresize_log),
                 ("points", "the development points: the header, a slot's round (red when short), its window (page state early_tree_short)", self.spoints),
                 ("hover_shots", "the windows under the mouse in the game: a slot with links lit, a locked slot close up", self.shover_shots),
                 ("order", "order the first building by the game's click on its slot; treasury, cost and slot by the adapter and the game", self.sorder()),
                 ("cancel", "cancel it by the same click, in the same turn", self.scancel),
                 ("order_again", "order it again (it stays for the turn)", self.sorder()),
                 ("tabs", "switch the tabs by the game's click", self.stabs),
                 ("unit", "a unit panel over a slot's crew card (hover)", self.sunit),
                 ("picker", "a crew picker and its unit panel, if a place is open", self.spicker),
                 ("scroll", "the tree scrolled by the scroll bar handlers", self.sscroll),
                 ("close_reopen", "close by the cross, reopen: tab and scroll kept", self.sclose),
                 ("escape", "Esc (the stolen key's callback) with nothing open closes the panel", self.sescape),
                 ("save", "the state saved through the adapter and read back by Ship.load_state", self.ssave("before the turn")),
                 ("opacity", "SetOpacity / PropagateOpacity on a parent that has an image", self.sopacity),
                 ("fit", "«Всё дерево» and back", self.sfit),
                 ("views", "the tree at its top and bottom, a short slot not hovered, a window at the bottom right; the drawing's own time", self.sviews),
                 ("demolish", "the demolish path (beer hall II), issued before the turn, no dialog open", self.sdemolish),
                 ("order_long", "an order of two turns or more, left for the turn", self.sorder_long),
                 ("turn", "ONE turn end by script; the events as the panel sees them; the upkeep; the dismantle's end", self.sturn),
                 ("dump_after_turn", "the panel after the turn dumped", self.sdump("after_turn", page_state=False)),
                 ("views_after_turn", "«Корабль» with the turn's news and the crew list, after the turn", self.sviews_after_turn),
                 ("agree_after_turn", "the panel's verdict on every building against the game's, after the turn", self.sagree("after the turn")),
                 ("cancel_previous", "the cancel of the earlier turn's order: the game's window, answered, gold, events; none left after", self.scancel_previous),
                 ("save_final", "saved and read back after the turn", self.ssave("at the end")),
                 ("simulated", "SimulateMouseOn on our slot (no hover event expected)", self.ssimulated),
                 ("finish", "the panel closed by its own path", self.sfinish),
                 ("battle_orders", "an order into an empty slot before and right after ONE battle (the battle restarts the campaign Lua: last)", self.sbattle_orders)]
        how = "completed"
        try:
            for no, title, fn in order:
                if no in RISKY and not self.healthy:
                    rec = {"step": no, "title": title, "status": "skipped", "answer": "the game's bindings were not healthy after the previous step"}
                    self.write(rec)
                    self.results[no] = rec
                    continue
                rec = self.item(no, title, fn)
                if no == "smoke" and self.smoke_broken:
                    raise pp.SessionAbort(f"the game's bindings broke during the smoke: {str(rec.get('answer'))[:600]}")
                if no in ("load", "open") and rec["status"] in ("failed", "timeout"):
                    self.diagnose(no)
                    raise pp.SessionAbort(f"step {no} {rec['status']}: {str(rec.get('answer'))[:800]}")
        except pp.SessionAbort as e:
            how = f"aborted early: {e}"
            self.write({"step": "abort", "status": "aborted", "answer": str(e)})
            self.s.log("ABORT", e)
        except TimeoutError as e:
            how = f"hard limit: {e}"
        except Exception as e:
            how = f"error: {type(e).__name__}: {e}"
        (self.dir / "actions.json").write_text(json.dumps(self.actions, ensure_ascii=False, indent=1), encoding="utf-8")
        return how

    def sdump_hover(self, name):
        dump = self.sdump(name)

        def fn():
            self.data("hover", {"id": "mtb_tree_node_0"})
            self.sleep(0.6)
            try:
                return dump()
            finally:
                self.data("hover", {"id": "frame"})
        return fn

    def sdump_tab(self, name):
        dump = self.sdump(name)

        def fn():
            self.data("click", {"id": "mtb_tab_ship"})
            self.sleep(0.8)
            try:
                return dump()
            finally:
                self.data("click", {"id": "mtb_tab_tree"})
        return fn

    def summary(self, how, analysis=None):
        lines = [f"ship panel session {datetime.now():%d.%m.%Y %H:%M}, ended: {how}"]
        if self.gifts:
            lines.append("given by script (points and gold short for an order): " + "; ".join(
                f"{g['step']} {g['key'].removeprefix(pp.PREFIX)}: points {g['before'].get('points')} -> {g['after'].get('points')}, gold {g['before'].get('gold')} -> {g['after'].get('gold')}" for g in self.gifts))
        for no, r in self.results.items():
            lines.append(f"[{no}] {r['status']:<9} {r['title']}: {r['answer']}")
        if analysis:
            lines += ["", "analysis:"] + analysis
        text = "\n".join(lines)
        (self.dir / "ship_session_summary.txt").write_text(text + "\n", encoding="utf-8")
        return text


# ---------------------------------------------------------------- the fake game (dry run; py -3.10, lupa) ----------------------------------------------------------------

# After port_probe.FAKE_GAME (its UIComponent registry, core's listeners, find_uicomponent, fake_fire), before the game's string functions:
# the campaign the panel's adapter reads (src/tww3_mtb_game.lua), the timers, the saved values, the stolen Esc, the old mod's upkeep,
# tww3_mtb_crew_ui with the switch on and the switch's own two ways of loading a module (require, loadfile) over the session pack's files.
FAKE_CAMPAIGN = r"""
local string, table = {find = string.find, match = string.match}, {sort = table.sort, remove = table.remove}
local pairs, ipairs, tonumber, type, pcall, loadstring = pairs, ipairs, tonumber, type, pcall, loadstring
local U = getmetatable(core:get_ui_root())
for _, m in ipairs({'SetInteractive', 'SetTooltipText', 'SetCurrentStateImageColour', 'SetCurrentStateImageOpacity', 'ShaderTechniqueSet', 'ShaderVarsSet',
  'RegisterTopMost', 'PropagateOpacity'}) do if not U[m] then U[m] = function() end end end
-- as the game's UIComponent: Parent() an address, VisibleFromRoot() false when any parent is hidden, a click's event carries the component
function U:Parent() return self._parent and self._parent._addr or nil end
function U:VisibleFromRoot() local u = self; while u do if not u._vis then return false end; u = u._parent end; return true end
function U:SimulateLClick() fake_fire('ComponentLClickUp', nil, {string = self._id, component = self._addr}) end
local function make(parent, id, visible) local u = UIComponent(parent:CreateComponent(id, 'x')); if visible == false then u:SetVisible(false) end; return u end
-- the HUD's own hidden confirmation (ui/campaign ui/hud_campaign.twui.xml: hud_campaign > rush_confirmation_holder (hidden) > dialogue_box >
-- text_holder, both_group > button_tick, button_cancel): made first, so a search by name finds it before any popup (session 15.11)
do
  local hud = make(core:get_ui_root(), 'hud_campaign')
  local db = make(make(hud, 'rush_confirmation_holder', false), 'dialogue_box')
  make(db, 'text_holder')
  local both = make(db, 'both_group')
  make(both, 'button_tick'); make(both, 'button_cancel')
end
-- the game's popup (ui/common ui/dialogue_box.twui.xml): dialogue_box > dy_text, purchase_options (hidden) > button_cancel, both_group >
-- button_tick, button_cancel, ok_group (hidden) > button_tick; at the end of the root
local function popup(text)
  local db = make(core:get_ui_root(), 'dialogue_box')
  make(db, 'dy_text'):SetStateText(text)
  make(make(db, 'purchase_options', false), 'button_cancel')
  local both = make(db, 'both_group')
  make(both, 'button_tick'); make(both, 'button_cancel')
  make(make(db, 'ok_group', false), 'button_tick')
  return db
end
local FACTION, SUBTYPE = 'wh3_dlc25_dwf_malakai', 'wh3_dlc25_dwf_malakai_makaisson'
local LEVELS = {}
function fake_set_levels(rows) for _, r in ipairs(rows) do LEVELS[r.key] = r end end
local N = 19
local slots, items, gold, turn, saved, escape, dismantling = {}, {}, 4000, 1, {}, {}, {}
local dev = 0           -- the horde's development points: 0 at the start of a campaign (session 14.11)
-- the horde's growth (game_sim.js): the game's 20 a point, at most 50 points; per turn the standing levels' «Рост орды» (config growth)
local growth, NEED, MAXDEV = 0, 20, 50
local function growth_per_turn() local s = 0; for i = 0, N - 1 do local r = LEVELS[slots[i]]; if r then s = s + (r.growth or 0) end end; return s end
-- the game applies a command a moment later (session 15.11): the commands wait for the next fake_tick
local commands = {}
for i = 0, N - 1 do slots[i] = '' end
slots[0] = 'wh3_dlc25_dwarf_spirit_of_grungni_airship_hull_1'
local faction
local slot_list = {num_items = function() return N end, item_at = function(self, i) local k = slots[i]; return {has_building = function() return k ~= '' end, building = function() return k end} end}
local details = {is_null_interface = function() return false end, military_force_slot_list = function() return slot_list end}
local mf = {command_queue_index = function() return 7 end, horde_details = function() return details end}
local malakai = {character_subtype_key = function() return SUBTYPE end, command_queue_index = function() return 42 end, has_military_force = function() return true end,
  military_force = function() return mf end, faction = function() return faction end, is_null_interface = function() return false end}
local clist = {num_items = function() return 1 end, item_at = function() return malakai end}
faction = {name = function() return FACTION end, treasury = function() return gold end, character_list = function() return clist end, is_null_interface = function() return false end}
local flist = {num_items = function() return 1 end, item_at = function() return faction end}
local function ours(extra) local c = {faction = function() return faction end, character = function() return malakai end}; for k, v in pairs(extra or {}) do c[k] = v end; return c end
local function fire(ev, ctx) fake_fire(ev, nil, ctx) end
cm = {model = function() return {world = function() return {faction_list = function() return flist end} end, turn_number = function() return turn end} end,
  turn_number = function() return turn end, get_faction = function() return faction end, get_local_faction_name = function() return FACTION end,
  treasury_mod = function(self, f, v) gold = gold + v end,
  add_development_points_to_horde = function(self, m, v) dev = dev + v end,
  dismiss_advice = function() end,
  get_campaign_ui_manager = function() return {get_char_selected = function() return 'character_cqi:42' end} end,
  add_building_to_force = function(self, c, key)
    local r = LEVELS[key]
    if string.find(key, 'airship_hull_', 1, true) then slots[0] = key; return end
    for i = 1, N - 1 do local o = LEVELS[slots[i]]; if r and o and o.chain == r.chain then slots[i] = key; return end end
    for i = 1, N - 1 do if slots[i] == '' and not items[i] then slots[i] = key; return end end
  end,
  set_saved_value = function(self, k, v) saved[k] = v end, get_saved_value = function(self, k) return saved[k] end,
  steal_escape_key_with_callback = function(self, name, fn) escape[name] = fn end, release_escape_key_with_callback = function(self, name) escape[name] = nil end}
local function slot_n(expr) return tonumber(string.match(expr, 'BuildingSlotList%.At%((%d+)%)')) end
local function has(s, x) return string.find(s, x, 1, true) ~= nil end
common = {
  get_context_value = function(obj, id, expr)
    local n = slot_n(expr)
    local rkey = string.match(expr, '"CcoBuildingLevelRecord", "([^"]+)"')
    if rkey then
      local r = LEVELS[rkey] or {}
      if has(expr, '.CreateCost(') then return r.cost end
      if has(expr, '.CreateTime(') then return r.turns end
      if has(expr, '.DevelopmentPointCost(') then return r.dev or 0 end
      if has(expr, '.HasEnoughDevelopmentPoints(') then return dev >= (r.dev or 0) end
      if has(expr, '.CanAfford(') then return gold >= (r.cost or 0) end
      local hull = LEVELS[slots[0]]
      local tier_ok = (r.tier or 0) <= ((hull and hull.level or 0) + 1)
      if has(expr, '.IsLockedByLevel(') then return not tier_ok end
      if has(expr, '.IsActiveForBuildingBrowser(') then
        -- as the game's browser: the slot holds the level below (an upgrade) or nothing (a first level), no construction, every required building
        -- standing (it or a higher level of its line), the hull's tier, the points, the gold
        if n == nil or items[n] or not tier_ok or dev < (r.dev or 0) or gold < (r.cost or 0) then return false end
        local here = LEVELS[slots[n]]
        if (r.level or 0) > 0 then if not (here and here.chain == r.chain and here.level == r.level - 1) then return false end
        elseif slots[n] ~= '' then return false end
        for _, q in ipairs(r.requires or {}) do
          local want, stands = LEVELS[q], false
          for i = 0, N - 1 do local l = LEVELS[slots[i]]; if slots[i] == q or (l and want and l.chain == want.chain and l.level > want.level) then stands = true end end
          if not stands then return false end
        end
        return true
      end
      return nil
    end
    if has(expr, 'HordeContext.AccumulatedGrowth') then return growth end
    if has(expr, 'HordeContext.GrowthPerTurn') then return growth_per_turn() end
    if has(expr, 'HordeContext.GrowthThresholdForPoint') then return NEED end
    if has(expr, 'HordeContext.TurnsUntilNextGrowthPoint') then local per = growth_per_turn(); if per <= 0 or dev >= MAXDEV then return 0 end; return math.ceil((NEED - growth) / per) end
    if has(expr, 'HordeContext.HasMaxDevelopmentPoints') then return dev >= MAXDEV end
    if has(expr, 'GrowthFactorList.At(0).StringValue') then return 'Постройки' end
    if has(expr, 'GrowthFactorList.At(0).IntValue') then return growth_per_turn() end
    if has(expr, 'HordeContext.DevelopmentPoints') then return dev end
    if n then
      if has(expr, 'IsContextValid(') and has(expr, 'ConstructionItemContext') then return items[n] ~= nil end
      if has(expr, 'ConstructionItemContext.BuildingLevelRecordContext.Key') then return items[n] and items[n].key or nil end
      if has(expr, 'ConstructionItemContext.TurnsToCompletion') then return items[n] and items[n].turns or nil end
      if has(expr, 'ConstructionItemContext') then return nil end
      if has(expr, '.IsEmpty') then return slots[n] == '' end
      if has(expr, '.IsDismantling') then return dismantling[n] == true end
      if has(expr, '.CanDismantle') then return n > 0 and slots[n] ~= '' end
      if has(expr, 'BuildingContext.BuildingLevelRecordContext.Key') then return slots[n] ~= '' and slots[n] or nil end
    end
    if has(expr, 'BuildingSlotList.Size') then return N end
    return nil
  end,
  call_context_command = function(obj, id, expr)
    -- applied at the next fake_tick, as the game applies it a moment later (session 15.11)
    commands[#commands + 1] = function() fake_command(obj, id, expr) end
  end,
  get_localised_string = function(k) return 'text of ' .. k end}
function fake_command(obj, id, expr)
    local n = slot_n(expr)
    local key = string.match(expr, '"CcoBuildingLevelRecord", "([^"]+)"')
    if n and has(expr, 'IssueCommandForBuildingBrowser') and key then
      if items[n] and items[n].turn < turn then
        -- a construction of an earlier turn: the game asks first in its popup (probe 14.11, item 12; session 15.11); the tick cancels with the refund
        local db = popup('Строительство еще не окончено. Вы действительно хотите отменить возведение этой постройки?')
        local slot = n
        core:add_listener('fake_dialog', 'ComponentLClickUp', function(c) return c.string == 'button_tick' or c.string == 'button_cancel' end, function(c)
          local ok, b = pcall(UIComponent, c.component)
          local mine = ok and b and b._parent and b._parent._parent == db
          if not mine then return end
          if c.string == 'button_tick' and items[slot] then gold = gold + items[slot].paid; dev = dev + (items[slot].dev or 0); items[slot] = nil; fire('MilitaryForceBuildingCancelled', ours()) end
          db:Destroy(); core:remove_listener('fake_dialog')
        end, true)
      elseif items[n] then gold = gold + items[n].paid; dev = dev + (items[n].dev or 0); items[n] = nil; fire('MilitaryForceBuildingCancelled', ours())
      else
        local r = LEVELS[key] or {cost = 1000, turns = 1}
        if gold < r.cost or dev < (r.dev or 0) then return end        -- refused silently, as the game (session 14.11: no points)
        items[n] = {key = key, turns = r.turns, paid = r.cost, dev = r.dev or 0, turn = turn}; gold = gold - r.cost; dev = dev - (r.dev or 0)
        fire('BuildingConstructionIssuedByPlayer', ours({building = function() return key end}))
      end
    elseif n and has(expr, '.Dismantle') then
      dismantling[n] = true       -- the building stands until the turn ends (probe 14.11, item 12; runs of 03.11)
    end
end
-- the timers: a real callback runs at the next fake_tick (the driver's sleep), as the game's runs a moment later
local queue, repeats = {}, {}
local tm = {real_callback = function(self, fn, ms, name) queue[#queue + 1] = fn end,
  repeat_real_callback = function(self, fn, ms, name) repeats[name or fn] = fn end, remove_real_callback = function(self, name) repeats[name] = nil end}
core.get_tm = function() return tm end
function fake_tick()
  local c = commands; commands = {}
  for _, fn in ipairs(c) do fn() end
  local q = queue; queue = {}
  for _, fn in ipairs(q) do pcall(fn) end
  local r = {}
  for _, fn in pairs(repeats) do r[#r + 1] = fn end
  for _, fn in ipairs(r) do pcall(fn) end
  return #q
end
function fake_ticks(n) local m = 0; for _ = 1, n do m = m + fake_tick() end; return m end
-- a turn: ours ends, the constructions count down, the completions come BEFORE our turn start (the order the adapter must cope with), then it
function fake_end_turn()
  fake_tick()
  fire('FactionTurnEnd', ours())
  growth = growth + growth_per_turn()
  while growth >= NEED do growth = growth - NEED; if dev < MAXDEV then dev = dev + 1 end end
  turn = turn + 1
  local done = {}
  for n, it in pairs(items) do it.turns = it.turns - 1; if it.turns <= 0 then done[#done + 1] = n end end
  table.sort(done)
  for n in pairs(dismantling) do local old = slots[n]; slots[n] = ''; fire('CharacterHordeBuildingDemolished', ours({building = function() return old end})) end
  dismantling = {}
  for _, n in ipairs(done) do local key = items[n].key; slots[n] = key; items[n] = nil; fire('MilitaryForceBuildingCompleteEvent', ours({building = function() return key end})) end
  fire('FactionTurnStart', ours())
  fake_tick()
  return 'turned'
end
-- the old mod: its upkeep at our turn start, through the field (as its listener calls M.pay_upkeep())
tww3_mtb_crew = {upkeep = function() return 0 end, get = function() return {rifles = saved.mtb_crew_rifles} end}
function tww3_mtb_crew.pay_upkeep() local u = tww3_mtb_crew.upkeep(); if u > 0 then cm:treasury_mod(FACTION, -u) end end
core:add_listener('fake_old_crew_turn', 'FactionTurnStart', function(c) return c:faction():name() == FACTION end, function() _G.tww3_mtb_crew.pay_upkeep() end, true)
tww3_mtb_campaign = {file_log = function(t) fake_log[#fake_log + 1] = t end}
fake_log = {}
-- the session pack's script/campaign/tww3_mtb/ files; require finds nothing (as the game's may not), loadfile reads them
fake_files = {}
require = function(p) error("module '" .. tostring(p) .. "' not found (fake)") end
loadfile = function(p) local s = fake_files[p]; if not s then return nil, 'cannot open ' .. tostring(p) end; return loadstring(s, '@' .. p) end
tww3_mtb_crew_ui = {NEW_SHIP_PANEL = true}
local screen = nil
local function ship_module(name)       -- src/tww3_mtb_crew_ui.lua ship_module, line for line
  local path = 'script/campaign/tww3_mtb/' .. name
  local ok, mod = pcall(require, path)
  if ok and type(mod) == 'table' then return mod end
  local okf, f = pcall(function() return loadfile(path .. '.lua') end)
  if okf and f then local ok2, m2 = pcall(f); if ok2 and type(m2) == 'table' then return m2 end end
  return nil
end
function tww3_mtb_crew_ui.ship_screen()
  if not tww3_mtb_crew_ui.NEW_SHIP_PANEL then return nil end
  screen = screen or ship_module('tww3_mtb_ship_screen')
  if screen and screen.start(ship_module) then return screen end
  return nil
end
"""


class FakeSession(pp.FakeSession):
    pass


# --break for the fake: the failures the session must diagnose (each a guess of what the game may do)
BREAKS = {
    # the game's require finds the files but runs them with _G as their environment, where core, common, UIComponent are nil (the census)
    "require_env": r"""
local loadstring, setfenv, setmetatable, pairs, error = loadstring, setfenv, setmetatable, pairs, error
local bare = {}
for k, v in pairs(_G) do if k ~= 'core' and k ~= 'common' and k ~= 'UIComponent' and k ~= 'find_uicomponent' then bare[k] = v end end
require = function(p) local s = fake_files[p .. '.lua']; if not s then error("module '" .. p .. "' not found") end; local f = loadstring(s, '@' .. p); setfenv(f, bare); return f() end
""",
    # neither require nor loadfile finds the pack's files: only the inline sources are left
    "load": "loadfile = function(p) return nil, 'cannot open ' .. tostring(p) .. ' (fake: no file access)' end\n",
    # a layout that the game cannot make: the open fails half way
    "open": r"""
local U = getmetatable(core:get_ui_root())
local create, find = U.CreateComponent, string.find
U.CreateComponent = function(self, id, path) if find(path, 'text_title', 1, true) then error('cannot create ' .. path .. ' (fake)') end; return create(self, id, path) end
""",
}


def fake_main(config_path, broken=None):
    import game_lua_env as genv
    from lupa import lua51
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    rt = lua51.LuaRuntime(unpack_returned_tuples=True)
    load = rt.eval("function(s, name) local f, err = loadstring(s, name); return f ~= nil, err end")
    for name, text in (("port_probe.lua", pp.LUA_FILE.read_text(encoding="utf-8")), ("ship_session.lua", LUA_FILE.read_text(encoding="utf-8")),
                       ("the sent chunk", ss_lib() + "\nreturn 1"), ("fake game", pp.FAKE_GAME), ("fake campaign", FAKE_CAMPAIGN)):
        ok, err = load(text, name)
        print(f"syntax {name}: {'ok' if ok else err}")
        if not ok:
            return 2
    rt.execute(pp.FAKE_GAME)
    rt.execute(FAKE_CAMPAIGN)
    files = pack_files_now()
    for n in ALL_MODULES:
        rt.globals().fake_files[f"script/campaign/tww3_mtb/{n}.lua"] = files[FOLDER + n + ".lua"].decode("utf-8")
    if broken:
        rt.execute(BREAKS[broken])
        print(f"fake BROKEN on purpose: {broken}")
    removed, lacks = genv.apply(rt)
    print(f"the game's Lua emulated (tools/game_lua_env.py): UTF-8 string.find/sub/len, removed {removed or 'nothing'}")
    # the levels' costs for the fake's orders: the session pack's own config, loaded as the game would load it
    conf = rt.execute(files[FOLDER + "tww3_mtb_ship_config.lua"].decode("utf-8"))
    rt.globals().fake_set_levels(conf.levels)
    # the mod's first tick with the switch on (src/tww3_mtb_crew_ui.lua: the screen's logic for the whole session)
    first = rt.execute("local ok, e = pcall(tww3_mtb_crew_ui.ship_screen); return tostring(ok) .. ' ' .. type(e)")
    print("first tick ship_screen():", first)

    def transport(code, wait):
        try:
            return {"ok": True, "result": rt.execute(code)}
        except Exception as e:
            return {"ok": False, "result": str(e)}
    run_dir = OUT / ("fake_run" + (f"_broken_{broken}" if broken else ""))
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    session = FakeSession(time.time() + 600)
    session.safe_end_turn = lambda: transport("return fake_end_turn()", 10).get("ok") is True
    s = ShipSession(cfg, transport, session, run_dir, fake=True)
    how = s.run()
    log = rt.globals().fake_log
    (run_dir / "tww3_mtb_log.txt").write_text("\n".join(str(log[i]) for i in range(1, len(log) + 1)) + "\n", encoding="utf-8")
    lines = analyse(run_dir)
    print(s.summary(how, lines))
    bad = [no for no, r in s.results.items() if r["status"] in ("failed", "timeout")]
    print("fake run:", how, "| steps failed:", bad or "none", "| folder", run_dir)
    if broken:      # a broken fake must be diagnosed: «open» aborts with the layout named; «load» and «require_env» go on by the next way
        want = {"open": how.startswith("aborted") and "text_title" in how, "load": s.results.get("load", {}).get("data", {}).get("how") == "inline",
                "require_env": s.results.get("load", {}).get("data", {}).get("how") == "loadfile"}[broken]
        print(f"broken {broken}: diagnosed as expected: {want}")
        return 0 if want else 1
    return 1 if bad or how != "completed" else 0


# ---------------------------------------------------------------- the analysis (py -3.10: Lua for the offline sides) ----------------------------------------------------------------

def compare_rows(ref, got):
    """[line] of every difference between two dumps, by tools/ui_layout_check.py's rules (POS within 1 unit, EXACT, NEAR, ACCEPTED).
    TODO(ui_layout_check): its loop is inline in main(); a compare(page_rows, lua_rows) there would let this call it instead."""
    import ui_layout_check as ulc

    def accepted(path, field):
        return any(rx.search(path) and f == field for rx, f, _ in ulc.ACCEPTED_RE)
    a, b = {r["path"]: r for r in ref}, {r["path"]: r for r in got}
    out = [f"missing in the game: {p} ({a[p]['layout']})" for p in a if p not in b]
    out += [f"extra in the game: {p} ({b[p]['layout']})" for p in b if p not in a]
    for p, x in a.items():
        y = b.get(p)
        if not y:
            continue
        for f in ulc.POS:
            if x.get(f) is None or y.get(f) is None or abs(x[f] - y[f]) > 1:
                out.append(f"{p}: {f} ref {x.get(f)}, game {y.get(f)}")
        for f in ulc.EXACT:
            va, vb = x.get(f), y.get(f)
            if f == "visible" and va is not None:
                va, vb = bool(va), bool(vb)
            if va != vb and not accepted(p, f):
                out.append(f"{p}: {f} ref {json.dumps(va, ensure_ascii=False)}, game {json.dumps(vb, ensure_ascii=False)}")
        for f in ulc.NEAR:
            va, vb = x.get(f), y.get(f)
            if (va is None) != (vb is None) or (va is not None and abs(va - vb) > 0.01):
                out.append(f"{p}: {f} ref {va}, game {vb}")
    return out


def engine_vs_wrapper(rows):
    """What the game's UIComponent answers against what the wrapper told it: the place relative to the parent (docking point 1), the size, the
    visibility (visible and not blank and not culled), the state, the text. {field: [lines]}."""
    by = {r["path"]: r for r in rows}
    out = {}

    def add(f, line):
        out.setdefault(f, []).append(line)
    for r in rows:
        if "ax" not in r or isinstance(r.get("ax"), dict):
            if isinstance(r.get("ax"), dict):
                add("error", f"{r['path']}: Position {r['ax']}")
            continue
        k = r.get("k") or 1
        parent = by.get(r["path"].rsplit("/", 1)[0]) if "/" in r["path"] else None
        if parent and isinstance(parent.get("ax"), (int, float)):
            for f, lf, pf in (("x", "ax", "ax"), ("y", "ay", "ay")):
                want = round(r[f] * k)
                rel = r[lf] - parent[pf]
                if abs(rel - want) > 1:
                    add("place", f"{r['path']}: {f} wrapper {want}, game {rel}")
        if isinstance(r.get("lw"), (int, float)):
            for f, lf in (("w", "lw"), ("h", "lh")):
                if abs(r[lf] - round(r[f] * k)) > 1:
                    add("size", f"{r['path']}: {f} wrapper {round(r[f] * k)}, game {r[lf]}")
        shown = bool(r.get("visible")) and not r.get("blank") and not r.get("culled")
        if isinstance(r.get("lvis"), bool) and r["lvis"] != shown:
            add("visible", f"{r['path']}: wrapper {shown}, game {r['lvis']}")
        if r.get("state") is not None and isinstance(r.get("lstate"), str) and r["lstate"] != r["state"]:
            add("state", f"{r['path']}: wrapper {r['state']}, game {r['lstate']}")
        if "text" in r and isinstance(r.get("ltext"), str) and r["ltext"] != r["text"]:
            add("text", f"{r['path']}: wrapper {r['text']!r}, game {r['ltext']!r}")
    return out


# A slot's look (a dump with "look": the session's slot_look): the components that make the state of a slot, compared with the page's slot of the
# same state (build/ui_dump/<state>.json; its slot the one the state's actions name). Paths with the slot's index replaced, places relative to the
# slot, numbers in texts and pictures as «#» (the cost and the level differ from building to building, the look does not).
LOOK_PARTS = ("", "/check", "/padlock", "/turns_banner", "/turns", "/plain", "dev:", "dev:/fill", "dev:/value", "cost:", "cost:/red", "cost:/value")
LOOK_FIELDS = ("visible", "image", "colour", "shader", "opacity", "image_opacity", "layout", "w", "h", "dx", "dy", "text")


def slot_look(rows, index):
    """{part: {field: value}} of the slot index's own components in a dump (LOOK_PARTS)."""
    import re
    by = {r["path"]: r for r in rows}
    slot = next((r for p, r in by.items() if p.endswith(f"/mtb_tree_node_{index}")), None)
    if not slot:
        return {}
    base = slot["path"]
    holder = base.rsplit("/", 1)[0]
    num = lambda v: re.sub(r"\d+", "#", v) if isinstance(v, str) else v
    out = {}
    for part in LOOK_PARTS:
        if part.startswith("dev:") or part.startswith("cost:"):
            kind, tail = part.split(":", 1)
            path = f"{holder}/mtb_tree_node_{kind}_{index}{tail}"
        else:
            path = base + part
        r = by.get(path)
        if not r:
            continue
        row = {f: r.get(f) for f in LOOK_FIELDS if f in r}
        if not part:
            row["dx"], row["dy"] = 0, 0
        elif part.startswith(("/", "dev:/", "cost:/")):
            row["dx"], row["dy"] = r.get("x"), r.get("y")        # a child: its place in its parent
        else:
            row["dx"], row["dy"] = (r.get("x") or 0) - (slot.get("x") or 0), (r.get("y") or 0) - (slot.get("y") or 0)     # beside the slot
        if "visible" in row:
            row["visible"] = bool(row["visible"])
        for f in ("text", "image"):
            if f in row:
                row[f] = num(row[f])
        if part == "/plain" and isinstance(row.get("image"), str):
            row["image"] = re.sub(r"branch_frame_\w+?(_selected)?\.png", r"branch_frame_*\1.png", row["image"])
        out[part or "slot"] = row
    return out


def compare_look(page_rows, page_index, game_rows, game_index):
    """[line] where the game's slot looks otherwise than the page's slot of the same state."""
    a, b = slot_look(page_rows, page_index), slot_look(game_rows, game_index)

    def seen(look, part):
        # shown with its holder: a hidden round's number is nothing the player sees
        root = part.split('/', 1)[0] if part.startswith(('dev:', 'cost:')) else 'slot'
        return bool(look.get(part, {}).get('visible')) and bool(look.get(root, {}).get('visible', True))
    out = []
    for part in sorted(set(a) | set(b)):
        if part in a and part in b and not seen(a, part) and not seen(b, part):
            continue
        if part not in b:
            out.append(f"{part}: missing in the game")
            continue
        if part not in a:
            out.append(f"{part}: missing on the page")
            continue
        for f in LOOK_FIELDS:
            va, vb = a[part].get(f), b[part].get(f)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and f in ("w", "h", "dx", "dy"):
                if abs(va - vb) > 1:
                    out.append(f"{part}: {f} page {va}, game {vb}")
            elif va != vb:
                out.append(f"{part}: {f} page {json.dumps(va, ensure_ascii=False)}, game {json.dumps(vb, ensure_ascii=False)}")
    return out


def crops(run_dir):
    """The close-ups the session asked for (shots.json crop: a box in root units), cut out of the pictures at their full resolution."""
    shots = run_dir / "shots.json"
    if not shots.exists():
        return []
    try:
        from PIL import Image
    except ImportError:
        return ["close-ups not cut: no PIL"]
    made = []
    for name, s in json.loads(shots.read_text(encoding="utf-8")).items():
        c, k, png = s.get("crop"), s.get("ui_scale_effective"), run_dir / f"{name}.png"
        if not (c and k and png.exists()):
            continue
        im = Image.open(png)
        box = [max(0, round(c["x"] * k)), max(0, round(c["y"] * k)), min(im.width, round((c["x"] + c["w"]) * k)), min(im.height, round((c["y"] + c["h"]) * k))]
        if box[2] > box[0] and box[3] > box[1]:
            im.crop(box).save(run_dir / f"{name}_crop.png")
            made.append(f"{name}_crop.png")
    return made


def page_measures():
    out = {}
    for p in sorted(DUMPS.glob("*.json")):
        if p.name == "index.json":
            continue
        out.update(json.loads(p.read_text(encoding="utf-8")).get("measures") or {})
    return out


def text_measures(rows, measures):
    """Every text: the game's TextDimensions against the page's measure of the same layout, width and text (where the page measured it)."""
    out = []
    for r in rows:
        td = r.get("td")
        if not isinstance(td, list):
            continue
        key = f"{r['layout']}|{r['w']}|{r.get('text', '')}"
        m = measures.get(key)
        out.append({"path": r["path"], "layout": r["layout"], "w": r["w"], "text": r.get("text"), "game": td, "page": m,
                    "dw": (td[0] - m[0]) if m and td[0] is not None else None, "dh": (td[1] - m[1]) if m and td[1] is not None else None})
    return out


REPLAY_LUA = r"""
return function(Ship, CM, FakeGame, config, start, actions)
  -- the game's points and growth at the start (the horde's own growth: the game's per turn less the standing levels' «Рост орды»): the turns of
  -- the replay make the points by the fake's rule, so a turn line that differs is the growth rule differing from the game's
  local g = start.growth
  local base = 0
  if g then
    base = g.per_turn or 0
    for _, k in ipairs(start.built or {}) do for _, l in ipairs(config.levels) do if l.key == k then base = base - (l.growth or 0) end end end
  end
  local game = FakeGame.new(config, {turn = start.turn, gold = start.gold, income = 0, demolish = 'chain', built = {}, dev_points = start.dev,
    growth = g and g.now or 0, growth_base = base, growth_threshold = g and g.need or 20})
  local q = {}
  for _, x in ipairs(start.queue or {}) do local r = nil; for _, l in ipairs(config.levels) do if l.key == x.key then r = l end end; q[#q + 1] = {key = x.key, turns_left = x.turns_left or 1, paid = r and r.cost or 0, dev = x.dev or 0} end
  game.restore({turn = start.turn, gold = start.gold, dev = start.dev, growth = g and g.now or 0, built = start.built, queue = q})
  local M = Ship.make(config, game, CM)
  Ship.load_state(M, function(k) return start.saved[k] end)
  local out = {}
  for i, a in ipairs(actions) do
    if a.gold_before then game.set_gold(a.gold_before) end
    if a.points_before ~= nil then game.set_dev(a.points_before) end
    if a.growth_before ~= nil then game.set_growth(a.growth_before) end
    if a['do'] == 'order' then M.order(a.key)
    elseif a['do'] == 'cancel' then M.cancel(a.key)
    elseif a['do'] == 'end_turn' then game.end_turn()
    elseif a['do'] == 'demolish' then M.demolish(a.key)
    elseif a['do'] == 'ship_seen' then M.ship_seen()      -- the session showed «Корабль» (sviews_after_turn)
    -- stood by script (cm:add_building_to_force) in the game: here silently; if the game fires its completion event for it, the panel's news
    -- will say so and differ from this (a finding about add_building_to_force, not about the panel)
    elseif a['do'] == 'stand' then local s = game.snapshot(); s.built[#s.built + 1] = a.key; game.restore(s) end
    local news = M.ship_news()
    out[i] = {message = M.message(), first_step = M.first_step(), foot_tail = M.foot_tail and M.foot_tail() or '', waiting = M.waiting(), unseen = M.ship_unseen(), news = news and Ship.encode(news) or nil,
      status = a.key and M.status(a.key).state or nil, crew_upkeep = M.crew_upkeep()}
  end
  return out
end
"""

OFFLINE_PANEL_LUA = r"""
return function(UI, Ship, CM, FakeGame, FakeUIC, config, cfg, snap, measures)
  -- the game's development points and the adapter's marks of a building being dismantled, as the game had them (I.snapshot)
  local game = FakeGame.new(config, {turn = snap.turn, gold = snap.gold, income = 0, demolish = 'chain', built = {}, dev_points = snap.dev})
  local q = {}
  for _, x in ipairs(snap.queue or {}) do q[#q + 1] = {key = x.key, turns_left = x.turns_left or 1, paid = 0, dev = x.dev or 0, turn = snap.turn} end
  game.restore({turn = snap.turn, gold = snap.gold, dev = snap.dev, built = snap.built, queue = q, dismantles = snap.dismantles or {}})
  local M = Ship.make(config, game, CM)
  Ship.load_state(M, function(k) return snap.saved[k] end)
  local ui = FakeUIC.new{measures = measures, text = cfg.text, w = snap.root.w, h = snap.root.h}
  local panel = UI.make_panel{root = ui.root, M = M, cfg = cfg, CM = CM, Ship = Ship, flags = {}, keep = {tab = snap.keep.tab, pan = snap.keep.scroll}}
  -- what src/tww3_mtb_ship_screen.lua S.open adds to the panel in the game: the cross takes the click, the dim over the map
  panel.view.close:SetInteractive(true)
  panel.view.root:SetOpacity(150)
  panel.refresh()
  if panel.build_all then panel.build_all(); panel.refresh() end      -- every window made, as the session's dumps (I.dump_begin)
  if snap.hovered then local c = ui.find(snap.hovered); if c then ui.mouse_on(c) end end
  return {rows = ui.dump(), unmeasured = ui.unmeasured}
end
"""


def analyse(run_dir):
    """The comparisons of a run folder; writes analysis.json and analysis.txt; returns the text lines (per comparison: ok / differs / failed and
    the first lines of each difference)."""
    import game_lua_env as genv
    import ui_layout_check as ulc
    run_dir = Path(run_dir)
    files = pack_files_now()
    rt, _ = genv.new_runtime()

    def module(name):
        return genv.load_mod(rt, files[FOLDER + name + ".lua"].decode("utf-8"), name + ".lua")
    Ship, CM, UI = module("tww3_mtb_ship"), module("tww3_mtb_crew_model"), module("tww3_mtb_ship_ui")
    config, cfg = module("tww3_mtb_ship_config"), module("tww3_mtb_ship_ui_config")
    FakeGame = genv.load_mod(rt, (TESTS / "fake_game.lua").read_text(encoding="utf-8"), "fake_game.lua")
    FakeUIC = genv.load_mod(rt, (TESTS / "fake_uic.lua").read_text(encoding="utf-8"), "fake_uic.lua")

    def to_lua(v):
        if isinstance(v, dict):
            return rt.table_from({k: to_lua(x) for k, x in v.items() if x is not None})
        if isinstance(v, list):
            return rt.table_from([to_lua(x) for x in v])
        return v
    report, lines = {}, []

    def head(name, diffs, total=None, note=""):
        status = "ok" if not diffs else "differs"
        lines.append(f"[{name}] {status}: {len(diffs)} differences" + (f" of {total}" if total is not None else "") + (f"; {note}" if note else ""))
        for d in diffs[:6]:
            lines.append("      " + d)
        return status
    pm = page_measures()
    for dump_path in sorted(run_dir.glob("dump_*.json")):
        d = json.loads(dump_path.read_text(encoding="utf-8"))
        name, rows = d["name"], d["components"]
        rep = {}
        # A: the page's dump of the same state
        page = DUMPS / f"{name}.json"
        if page.exists():
            pd = json.loads(page.read_text(encoding="utf-8"))
            diffs = compare_rows(pd["components"], rows)
            rep["page"] = {"differences": diffs, "page_root": pd.get("root"), "game_root": d.get("root"), "page_snapshot": pd.get("snapshot", {}).get("built")}
            note = (f"page root {pd.get('root')}, game root {d.get('root')}; the page's campaign: gold {pd['snapshot'].get('gold')}, built {len(pd['snapshot'].get('built') or [])}; "
                    f"the game's: gold {d['snapshot'].get('gold')}, built {[k.removeprefix(pp.PREFIX) for k in d['snapshot'].get('built') or []]}")
            rep["page"]["status"] = head(f"{name}: game vs the page", diffs, len(pd["components"]), note)
        # A2: a slot's look against the page's slot in the same state (the dumps of the points, the dismantling, the asked cancel)
        look = d.get("look")
        if look:
            page = DUMPS / f"{look['page']}.json"
            if page.exists():
                pd = json.loads(page.read_text(encoding="utf-8"))
                ids = [a[1] for a in pd.get("actions") or [] if str(a[1]).startswith("mtb_tree_node_")]
                pi = int(ids[-1].rsplit("_", 1)[1]) if ids else None
                diffs = compare_look(pd["components"], pi, rows, look["index"]) if pi is not None else ["the page's state names no slot"]
                rep["look"] = {"page": look["page"], "page_index": pi, "game_index": look["index"], "differences": diffs}
                rep["look"]["status"] = head(f"{name}: {look.get('title')}: the game's slot vs the page's ({look['page']})", diffs, len(LOOK_PARTS))
            else:
                lines.append(f"[{name}: look] no page state {look['page']}: node tools/tests/ui_dump_export.mjs")
        if d.get("only"):
            report[name] = rep          # a slot's rows only: the whole-panel comparisons do not apply
            continue
        # D: the same Lua offline (fake UIComponent) at the game's state, root and TextDimensions: what is left is the game binding's own doing
        snap = d["snapshot"]
        measures = {k: v for k, v in pm.items() if k.startswith("ink|")}
        for r in rows:
            if isinstance(r.get("td"), list) and len(r["td"]) >= 3 and r["td"][0] is not None:
                measures[f"{r['layout']}|{r['w']}|{r.get('text', '')}"] = r["td"]
        try:
            off = rt.execute(OFFLINE_PANEL_LUA)(UI, Ship, CM, FakeGame, FakeUIC, config, cfg, to_lua(snap), to_lua(measures))
            orows = ulc.py(off)["rows"]
            diffs = compare_rows(orows, rows)
            rep["offline"] = {"differences": diffs, "unmeasured": ulc.py(off).get("unmeasured")}
            rep["offline"]["status"] = head(f"{name}: game vs the same Lua offline at the game's state and root", diffs, len(orows))
        except Exception as e:
            rep["offline"] = {"status": "failed", "error": str(e)[:2000]}
            lines.append(f"[{name}: offline] failed: {str(e)[:300]}")
        # B: the game's UIComponent against the wrapper
        ev = engine_vs_wrapper(rows)
        flat_ev = [f"{f}: {l}" for f, ls in ev.items() for l in ls]
        rep["engine"] = {"by_field": {f: len(ls) for f, ls in ev.items()}, "first": {f: ls[:10] for f, ls in ev.items()}}
        rep["engine"]["status"] = head(f"{name}: the game's UIComponent vs the wrapper", flat_ev, len(rows), f"by field {rep['engine']['by_field'] or '-'}")
        # C: TextDimensions against the page's measures
        tm = text_measures(rows, pm)
        both = [t for t in tm if t["page"]]
        zero = [t for t in tm if t.get("text") and (not t["game"] or not t["game"][0])]
        far = [f"{t['layout']} w{t['w']} «{str(t['text'])[:50]}»: game {t['game']}, page {t['page']}" for t in both if abs(t["dw"] or 0) > 1 or abs(t["dh"] or 0) > 1]
        ratios = sorted(t["game"][0] / t["page"][0] for t in both if t["page"][0] and t["game"] and t["game"][0])
        rep["text"] = {"texts": len(tm), "with_page_measure": len(both), "zero_in_game": len(zero), "far": far, "all": tm,
                       "width_ratio_median": ratios[len(ratios) // 2] if ratios else None}
        rep["text"]["status"] = head(f"{name}: TextDimensions vs the page's measures", far, len(both),
                                     f"{len(tm)} texts, {len(zero)} non-empty ones zero in the game; median width game/page {rep['text']['width_ratio_median']}")
        report[name] = rep
    # E: the expected texts, the same actions replayed offline from the game's own start
    acts = json.loads((run_dir / "actions.json").read_text(encoding="utf-8")) if (run_dir / "actions.json").exists() else []
    # a run made before the session recorded it: «Корабль» was shown after the turn (step views_after_turn, ss_ship_after_turn.png), which clears
    # the tab's «!» (M.ship_seen) — the replay does the same there (run 20261115-030121: «unseen expected True, game False» after the next cancel)
    if acts and not any(a["do"] == "ship_seen" for a in acts) and (run_dir / "ss_ship_after_turn.png").exists():
        at = next((i for i, a in enumerate(acts) if a["do"] == "end_turn"), None)
        if at is not None:
            acts.insert(at + 1, {"do": "ship_seen"})
    first = run_dir / "dump_fresh_tree.json"
    if acts and first.exists():
        start = json.loads(first.read_text(encoding="utf-8"))["snapshot"]
        try:
            want = ulc.py(rt.execute(REPLAY_LUA)(Ship, CM, FakeGame, config, to_lua(start), to_lua([{k: v for k, v in a.items() if k in ("do", "key", "gold_before", "points_before", "growth_before")} for a in acts])))
            diffs, notes = [], []
            for i, a in enumerate(acts):
                w = want[i] if isinstance(want, list) else want.get(str(i + 1), {})
                if "got" not in a:          # an action of the view (ship_seen): nothing read back
                    continue
                for f in ("message", "first_step", "unseen", "news"):
                    if w.get(f) != a["got"].get(f):
                        diffs.append(f"after {a['do']} {str(a.get('key')).removeprefix(pp.PREFIX)}: {f} expected {w.get(f)!r}, game {a['got'].get(f)!r}")
                if a.get("status") is not None and w.get("status") != a["status"]:
                    if a["do"] == "demolish":       # the replay's fake removes it at once; the game keeps it until the turn ends (probe 14.11, 8.2)
                        notes.append(f"after demolish: status expected by the replay {w.get('status')}, the game's panel {a['status']} (the game dismantles at the turn end)")
                    else:
                        diffs.append(f"after {a['do']}: status expected {w.get('status')}, game {a['status']}")
                foot, msg, tail = a["got"].get("foot"), w.get("message") or w.get("first_step") or "", w.get("foot_tail") or ""
                # the foot row: the whole, or its first part cut with … and, on the second line, the part that says what to wait for (M.foot_tail)
                first, _, rest = (foot or "").partition("… ")
                cut_ok = (foot or "").endswith("…") and msg.startswith(foot[:-1].rstrip()) or (rest != "" and msg.startswith(first.rstrip()) and msg.endswith(rest))
                if foot is not None and foot != msg and not cut_ok:
                    diffs.append(f"after {a['do']}: the foot line «{foot}», expected «{msg}» (or its cut with …)")
                elif foot is not None and tail and not foot.endswith(tail):
                    diffs.append(f"after {a['do']}: the foot line «{foot}» lost what the player waits for «{tail}»")
                if a["got"].get("mark") is not None and w.get("unseen") is not None and a["do"] == "end_turn" and bool(a["got"]["mark"]) != bool(w["unseen"]):
                    diffs.append(f"after the turn: the «!» mark {a['got']['mark']}, expected {w['unseen']} (the tree tab is shown)")
            report["texts"] = {"expected": want, "game": [a.get("got") for a in acts], "differences": diffs, "notes": notes}
            report["texts"]["status"] = head("ship news, messages, «!» vs the same actions replayed offline (byte for byte)", diffs, len([a for a in acts if "got" in a]) * 4,
                                             "; ".join(notes))
        except Exception as e:
            report["texts"] = {"status": "failed", "error": str(e)[:2000]}
            lines.append(f"[texts] failed: {str(e)[:400]}")
    made = crops(run_dir)
    if made:
        lines.append("close-ups: " + ", ".join(made))
    (run_dir / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (run_dir / "analysis.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


# ---------------------------------------------------------------- the launch ----------------------------------------------------------------

def session_main(argv):
    """tools/run_game.py with build/ship_session/pack, as port_probe.session_main does with its own."""
    import run_game as rg
    rb = rg.rb
    busy = rb.busy_reasons
    rb.busy_reasons = lambda: [r for r in busy() if r != "docker containers are running"]
    rg.PACK_DIR = PACK
    return rg.main(argv)


def plan_text(args, limit):
    res = "1280x720" if args.small else "1920x1080"
    return "\n".join([
        "launch plan:",
        f"  1. {sys.executable} {Path(__file__).name} _session --label ship_panel --timeout {limit + 120} --packs harness campaign --user-mods memreader_plus.pack"
        + ("" if args.small else " --set x_res=1920 y_res=1080"),
        f"     -> tools/run_game.py: lock {sg.LOCK} = «mtb, начало HH:MM»; packs from {PACK} (the switch on); our mod list; used_mods.txt only read;",
        f"        low graphics, windowed {res}, Normal difficulty, RTX checked; no focus, under other windows (focus guard); the user's folders put back.",
        "  2. main menu -> new campaign wh3_dlc25_dwf_malakai (as the probe), the end turn button, peace with everyone, events accepted.",
        "  3. census, smoke (this session's helpers, canary after each); FIRST game state: the requirement II vs I (script adds on the idle force, one real",
        "     order, cancelled); load (the switch's way, else loadfile, else inline) and open — on a failure the",
        "     diagnostics (every layout made, text layouts measured, image paths) and an ABORT; dumps fresh_tree / fresh_tree_info / fresh_ship with",
        "     pictures; order (the game's click), cancel, order; tabs; unit panel; crew picker; scroll; close/reopen; Esc; save and read back; opacity; «Всё дерево»;",
        f"     the dismantle issued and an order of 2 turns left; ONE turn end (hard limit {END_TURN_LIMIT} s; events, upkeep and the dismantle's end logged);",
        "     the panel after it; the earlier turn's cancel with the game's window answered; save again; then ONE battle with a clean order before and after.",
        "  4. STOP flag -> run_game.py closes only the game it started, waits until tasklist has no Warhammer3.exe, removes the lock; then the analysis",
        "     (py -3.10) compares the dumps with the page and with the offline Lua, the game's TextDimensions with the page's measures, the texts with a replay.",
        f"  hard limit {limit} s (~{limit // 60} min); expected 35-45 min: start and new campaign 8-12, steps before the turn 6-10, turn end 2-8, the battle 5-8, the rest 3-5.",
    ])


def run(args):
    limit = args.limit
    built = build_pack()
    print(f"session pack {PACK}: {built['campaign']} {built['bytes']} bytes, {built['files']} files; switch {SWITCH_ON!r}; modules taken from src/ "
          f"(differing from build/campaign/pack): {built['replaced_from_src'] or 'none'}")
    cfg = make_config(parse_options(args.option))
    print(f"config {CONFIG}: {len(cfg['layouts'])} layouts, page states {cfg['page_states']}; user ui_scale {cfg['user_ui_scale']}")
    print("options (the probe's answers; None = the module's own):", ", ".join(f"{k}={v}" for k, v in cfg["options"].items()))
    print("checks before a launch (CLAUDE.md):")
    rows = checks()
    for what, ok, blocking, detail in rows:
        print(f"  [{'ok' if ok else ('STOP' if blocking else 'note')}] {what}: {detail}")
    blockers = [r for r in rows if r[2] and not r[1]]
    stash_blocked = [r for r in blockers if r[0].startswith("data/") and "author's" in r[0]]
    other = [r for r in blockers if r not in stash_blocked]
    fake = subprocess.run(["py", "-3.10", str(Path(__file__).resolve()), "_fake", str(CONFIG)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("the session against the fake game (py -3.10, lupa, the game's emulated Lua):")
    print("\n".join("  " + l for l in (fake.stdout + fake.stderr).strip().splitlines()[-80:]))
    print(plan_text(args, limit))
    if args.dry_run:
        print("\n".join(sg.describe()))
        state = "would launch" if not blockers else ("would STOP: " + "; ".join(r[0] for r in blockers))
        if stash_blocked and not other:
            state += " (with --stash-user-pack and the author's yes it would launch)"
        print("dry run:", state, "| fake game:", "ok" if fake.returncode == 0 else f"FAILED ({fake.returncode})")
        return 0 if fake.returncode == 0 else 1
    if fake.returncode != 0:
        print("not launching: the session failed against the fake game")
        return 1
    if other or (stash_blocked and not args.stash_user_pack):
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
    session = cc.Session("ship_panel", started + limit)
    cmd = [sys.executable, str(Path(__file__).resolve()), "_session", "--label", "ship_panel", "--timeout", str(limit + 120),
           "--packs", "harness", "campaign", "--user-mods", "memreader_plus.pack"]
    if not args.small:
        cmd += ["--set", "x_res=1920", "y_res=1080"]
    OUT.mkdir(parents=True, exist_ok=True)
    proc, how, s = None, "not started", None
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
        shutil.copy2(CONFIG, session.dir / "ship_session_config.json")
        session.log("run", session.dir)
        session.wait_mode("frontend", 240)
        time.sleep(10)
        session.log(session.plain(f'frontend.start_campaign("wh3_main_combi", "wh3_main_combi", "{pp.FACTION_KEY}"); return 1', 10)["result"])
        session.wait_mode("campaign", 900)
        time.sleep(8)
        end = time.time() + 200
        while time.time() < end and session.visible("button_end_turn") in ("-", "inactive"):
            time.sleep(3)
        session.shot("ss_map")
        session.log("peace", session.prog("return P.peace()")["result"])
        accept = ('local n = 0; for _ = 1, 4 do local e = mtb.find("events", true); local b = e and mtb.find("button_accept", true, e); '
                  'if b then b:SimulateLClick(); n = n + 1 end end; return n')
        for _ in range(2):
            session.log("events", session.plain(accept, 10)["result"])
            time.sleep(2)
        session.log("blockers", session.script("dismiss_blockers.lua")["result"])
        s = ShipSession(cfg, rc.send, session, session.dir)
        how = s.run()
    except Exception as e:      # the game must be closed in every case
        how = f"error before or between steps: {type(e).__name__}: {e}"
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
        final = {"step": "end", "finished": True, "how": how, "seconds": round(time.time() - started), "game_gone": gone,
                 "lock_removed": not sg.OUR_LOCK.match(sg.read_lock() or ""), "run_game": status, "user_pack_restored": restored}
        lines = None
        if session.dir:
            an = subprocess.run(["py", "-3.10", str(Path(__file__).resolve()), "_analyse", str(session.dir)], capture_output=True, text=True, encoding="utf-8", errors="replace")
            lines = (an.stdout + an.stderr).strip().splitlines()
        if s:
            s.write(final)
            print(s.summary(how, lines))
        elif session.dir:
            with (session.dir / "ship_session.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(final, ensure_ascii=False) + "\n")
        print("finished:", json.dumps(final, ensure_ascii=False))
    return 0 if how == "completed" and gone else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "_session":
        return session_main(argv[1:])
    if argv and argv[0] == "_fake":
        broken = argv[argv.index("--break") + 1] if "--break" in argv else None
        rest = [a for a in argv[1:] if a not in ("--break", broken)]
        return fake_main(rest[0] if rest else CONFIG, broken)
    if argv and argv[0] == "_analyse":
        print("\n".join(analyse(argv[1])))
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--small", action="store_true")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--stash-user-pack", action="store_true")
    ap.add_argument("--option", action="append", default=[], metavar="NAME=VALUE", help="a probe answer as an ENGINE / ASSUMED option (OPTIONS)")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
