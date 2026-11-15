"""Session «crew_hire»: the new panel's hire drives the old mod's crew mechanics in the real game (docs/design/port-to-game.md 8.6). ONE unattended
game, four turn ends, ONE battle: buildings by real orders, a kind hired through the panel's own handlers, the order changed within the turn, the turn
start puts it in, the seats read back through the old module and in the battle, the gold and the upkeep taken once, Malakai at the rail of his side,
then the opening building demolished and the crew gone from the seats and the panel.

  py -3.14 tools/crew_cycle.py session crew_hire --dry-run     everything but the game: the session pack, the checks of CLAUDE.md, every step
                                                               against the fake game with the REAL packed crew module (py -3.10, lupa, the game's
                                                               emulated Lua), the plan
  py -3.14 tools/crew_cycle.py session crew_hire               the run (only with the author's permission, CLAUDE.md «Общая игра»)
      --small, --limit N, --stash-user-pack                    as the session ship_panel

The panel is on FOR THE SESSION ONLY: build/crew_hire/pack/tww3_mtb_campaign.pack is build/campaign/pack's with tww3_mtb_crew_ui.lua's switch true
and the panel's modules from src/ (tools/tests/ship_session.py session_files). The machinery is ship_panel's and the probe's: the launch, the lock,
the stash, the shutdown (tools/run_game.py, tools/shared_game.py), the smoke, the isolation of every step, the early abort; the battle is
tools/crew_cycle.py's (Session.battle: the men of the battle read from memory, the seats checked, the ammunition's report).
Answers: <run>/crew_hire.jsonl (a line per step), crew_hire_summary.txt, ch_*.png, men_crew_hire.txt, stats_crew_hire.txt; build/crew_hire/last_run.txt.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
TOOLS = REPO / "tools"
TESTS = TOOLS / "tests"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TESTS))
import port_probe as pp  # noqa: E402
import ship_session as ss  # noqa: E402
import shared_game as sg  # noqa: E402

OUT = REPO / "build" / "crew_hire"
PACK = OUT / "pack"
CONFIG = OUT / "config.json"
LUA_FILE = TESTS / "crew_hire_session.lua"
SEP = chr(92)
CREW = f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew.lua"
DEFAULT_LIMIT = 3600
PREFIX = pp.PREFIX
OWNED = ["rifles", "cannons", "bombs", "cupolas", "harpoon"]
# the buildings, by the names of the author's tree (build/tree/ship_config.json): the barge and the beer hall (pirates) by real orders (their
# completions are the game's events); the dummies (crossbows and the riflemen's boost: they need «Склад оружия» first) and the gun ports (the bay:
# tier IV and two workshops) stood by script on the idle force BEFORE any construction is in a slot (port-to-game.md 3.4: a script's add lands in a
# slot under construction otherwise); the kind hired, the one ordered instead, the side Malakai is moved to, the building demolished for the loss
PLAN = {"barge": "Прочный корпус", "orders": ["Пивной чертог"], "stands": ["Манекен для учебной стрельбы", "Орудийные порты"], "hire": ("rifles", "quarrellers"),
        "other": ("rifles", "pirates"), "side": "right", "demolish": "Манекен для учебной стрельбы"}
TURN = ss.END_TURN_LIMIT + 120
ss.BUDGET.update({"bridge": 60, "barge": 90, "turn_barge": TURN, "openers": 150, "turn_openers": TURN, "hire": 90, "changes": 120, "side": 60,
                  "turn_hire": TURN, "battle": 900, "after_battle": 150, "demolish": 90, "turn_lose": TURN, "lost": 90, "crew_smoke": 60})
RISKY = {"battle": "ONE real battle (tools/crew_cycle.py Session.battle): the campaign Lua restarts after it",
         "turn_barge": "a turn end by script", "turn_openers": "a turn end by script", "turn_hire": "a turn end by script", "turn_lose": "a turn end by script"}


def ch_lib():
    mine = LUA_FILE.read_text(encoding="utf-8").rsplit("return 'ready'", 1)[0]
    return ss.ss_lib() + "\n;(function()\n" + mine + "\nend)()\n"


# ---------------------------------------------------------------- the session's pack and config ----------------------------------------------------------------

def build_pack():
    """build/crew_hire/pack: ship_panel's session pack (the switch on, the screen's modules from src/) with the crew module as built; the crew module
    of build/campaign/pack must be the one of src/ (its data is generated: py -3.14 tools/build.py)."""
    import pfh5
    files, deps, manifest, replaced = ss.session_files()
    packed = files[CREW].decode("utf-8")
    src = (REPO / "src" / "tww3_mtb_crew.lua").read_text(encoding="utf-8")
    head, _, tail = src.partition("local CONFIG = {} --@CONFIG@")
    if not packed.startswith(head) or not packed.endswith(tail):
        raise SystemExit("the packed tww3_mtb_crew.lua is not src/'s: py -3.14 tools/build.py")
    remote = (REPO / "src" / "tww3_mtb_remote.lua").read_bytes()
    harness = {f"script{SEP}{m}{SEP}mod{SEP}tww3_mtb_remote.lua": remote for m in ("frontend", "campaign", "battle")}
    PACK.mkdir(parents=True, exist_ok=True)
    names = manifest["packs"]
    (PACK / names["harness"]).write_bytes(pfh5.pack_files(harness))
    blob = pfh5.pack_files(files, deps)
    back, _ = pfh5.read_pack(blob)
    if ss.SWITCH_ON not in back[ss.CREW_UI].decode("utf-8"):
        raise SystemExit("the session pack does not read back with the switch on")
    (PACK / names["campaign"]).write_bytes(blob)
    (PACK / "manifest.json").write_text(json.dumps({"packs": names}, indent=1), encoding="utf-8")
    return {"campaign": names["campaign"], "bytes": len(blob), "files": len(files), "replaced_from_src": replaced}


def use_own_pack():
    """ship_panel's helpers read this session's pack and config (in this process only)."""
    ss.PACK, ss.CONFIG, ss.OUT = PACK, CONFIG, OUT


def make_config():
    use_own_pack()
    cfg = ss.make_config(dict(ss.OPTIONS))
    conf = json.loads((REPO / "build" / "tree" / "ship_config.json").read_text(encoding="utf-8"))
    by_name = {r["name"]: r for r in conf["levels"]}
    keys = {"barge": by_name[PLAN["barge"]]["key"], "orders": [by_name[n]["key"] for n in PLAN["orders"]], "stands": [by_name[n]["key"] for n in PLAN["stands"]],
            "demolish": by_name[PLAN["demolish"]]["key"]}
    options = {g["key"]: {o["key"]: {"hire": o["hire"], "upkeep": o["upkeep"], "ammo": o.get("ammo")} for o in g["options"]} for g in conf["groups"]}
    crew = json.loads((REPO / "data" / "crew_options.json").read_text(encoding="utf-8"))
    cfg["crew"] = {"plan": PLAN, "keys": keys, "options": options, "malakai": crew.get("malakai_at_rail"),
                   "rifle_seats": crew["groups"]["rifles"]["seats"], "group_seats": sum(len(g["seats"]) for g in crew["groups"].values())}
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
    return cfg


def checks():
    old = pp.PACK
    pp.PACK = PACK
    try:
        return pp.checks()
    finally:
        pp.PACK = old


# ---------------------------------------------------------------- the steps ----------------------------------------------------------------

class CrewHireSession(ss.ShipSession):
    def __init__(self, cfg, transport, session, run_dir, fake=False):
        super().__init__(cfg, transport, session, run_dir, fake)
        self.lib = ch_lib()
        self.jsonl = self.dir / "crew_hire.jsonl"
        self.c = cfg["crew"]
        self.money_log = []

    def cz(self, name, args=None, wait=20):
        self.s.check_time()
        if self.item_end and time.time() > self.item_end:
            raise pp.ItemTimeout(f"step time over before {name}")
        row = self.send(self.lib + f"\nreturn _G.mtb_ch.run({pp.lua_literal(name)}, {pp.lua_literal(args or {})})", wait)
        if not row.get("ok"):
            raise RuntimeError(f"{name}: {str(row.get('result'))[:3000]}")
        r = json.loads(row["result"])
        if not r.get("ok"):
            self.last_fail = r
            raise RuntimeError(f"{name}: {r.get('err')}")
        return r.get("data") or {}

    def crew(self):
        return self.cz("crew")

    def hire_of(self, group, option):
        return (self.c["options"].get(group, {}).get(option) or {}).get("hire") or 0

    def upkeep_of(self, group, option):
        return (self.c["options"].get(group, {}).get(option) or {}).get("upkeep") or 0

    # -- the bridge attached at the campaign's start: the crew module reads the model, Malakai at the rail of the default side
    def sbridge(self):
        c = self.crew()
        mk = self.c["malakai"]
        plan = c.get("plan") or {}
        rail = plan.get(mk["seats"]["left"]), plan.get(mk["helm_seat"])
        ok = c.get("new_panel") and c["bridge"]["attached"] and rail == ("mtb_bp_malakai_rail_left", mk["helm_crew"])
        answer = (f"switch {c.get('new_panel')}; bridge attached {c['bridge']['attached']} (writes {c['bridge']['writes']}); crew status {c.get('status')}; the old "
                  f"module's choice {c.get('old')}; Malakai {c.get('malakai')}; seat {mk['seats']['left']} -> {rail[0]}, helm -> {rail[1]}; gold {c.get('gold')}")
        if not (c.get("new_panel") and c["bridge"]["attached"]):
            raise pp.SessionAbort("the bridge did not attach to the new screen: " + answer)
        return ("ok" if ok else "differs"), answer, c

    # -- a building by a real order of the model (points and gold by script when short, as ship_panel's orders)
    def order(self, key, label):
        gates, gtext = self.ensure(key, label)
        before = self.crew()
        r = self.cz("order", {"key": key})
        self.sleep(2.0)
        st = self.data("state", {"keys": [key]})
        lv = st["levels"][key]
        taken = lv["status"].get("state") == "building" or lv.get("under_construction") is not None
        return taken, f"{key.removeprefix(PREFIX)}: {gtext}; the model's answer {r.get('result')}; now {lv['status'].get('state')}, construction {lv.get('construction')}", \
            {"gates": gates, "before": before, "order": r, "state": lv}

    def sbarge(self):
        k = self.c["keys"]["barge"]
        taken, text, d = self.order(k, "barge")
        return ("ok" if taken else "failed"), text, d

    def sopeners(self):
        keys = self.c["keys"]["stands"]
        st = self.cz("stand", {"keys": keys}, 60)
        stood = self.data("state", {"keys": keys})["levels"]
        texts = [f"stood by script {[k.removeprefix(PREFIX) for k in keys]}: {st.get('add')}; standing now "
                 f"{ {k.removeprefix(PREFIX): stood[k].get('standing') for k in keys} }; the bridge wrote at once {st.get('wrote')}"]
        out, all_taken = {"stand": st}, all(stood[k].get("standing") for k in keys)
        for k in self.c["keys"]["orders"]:
            taken, text, d = self.order(k, "opener")
            out[k], all_taken = d, all_taken and taken
            texts.append(("taken " if taken else "NOT taken ") + text)
        return ("ok" if all_taken else "differs"), "; ".join(texts), out

    # -- a turn end with the treasury's movers watched (ship_panel's money wrapper: every cm:treasury_mod with its stack, the old pay_upkeep's delta)
    def turn(self, label, expect_upkeep):
        before = self.crew()
        self.data("money_on")
        mark = time.time()
        try:
            back = self.end_turn()
        finally:
            money = self.data("money_read")
            self.data("money_off")
        self.sleep(2.0)
        after = self.crew()
        calls = money.get("calls") or []
        model = [c.get("amount") for c in calls if c.get("what") == "cm:treasury_mod" and "tww3_mtb_game" in str(c.get("stack"))]
        old_tm = [c.get("amount") for c in calls if c.get("what") == "cm:treasury_mod" and "tww3_mtb_crew" in str(c.get("stack")) and "tww3_mtb_game" not in str(c.get("stack"))]
        old_pay = [c.get("delta") for c in calls if c.get("what") == "tww3_mtb_crew.pay_upkeep" and c.get("delta")]
        self.money_log.append({"turn": label, "model": model, "old_tm": old_tm, "old_pay": old_pay})
        once = (model == ([-expect_upkeep] if expect_upkeep else [])) and not old_tm and not old_pay
        text = (f"turn {'came back' if back else 'NOT back'} in {round(time.time() - mark)} s; the treasury moved by the model {model} (expected "
                f"{[-expect_upkeep] if expect_upkeep else 'none'}), by the old module {old_tm or 'nothing'}, the old pay_upkeep {old_pay or 'nothing'}; "
                f"gold {before.get('gold')} -> {after.get('gold')} (the game's income in it); model upkeep now {after.get('model_upkeep')}; the panel says «{after.get('message')}»")
        return back, once, text, {"before": before, "after": after, "money": money}

    def sturn_barge(self):
        back, once, text, d = self.turn("barge", 0)
        c = d["after"]
        k = self.c["keys"]["barge"]
        st = self.data("state", {"keys": [k]})["levels"][k]
        on = c.get("paying")
        return ("ok" if back and st["status"].get("state") == "built" and on and once else "differs"), \
            f"{text}; {k.removeprefix(PREFIX)} {st['status'].get('state')}; on the barge (the old module's paying) {on}; crew_pays {c.get('crew_pays')}", d

    def sturn_openers(self):
        back, once, text, d = self.turn("openers", 0)
        c = d["after"]
        g = c.get("groups") or {}
        places = {x: (g.get(x) or {}).get("place") for x in OWNED}
        ok = back and places.get("rifles") and places.get("cannons") and (c.get("old") or {}).get("cannons") == "empty" and (c.get("boost") or {}).get("rifles") == 1
        return ("ok" if ok and once else "differs"), (f"{text}; places {places}; the old module: cannons {(c.get('old') or {}).get('cannons')} (the bare bay: "
                                                     f"expected empty), rifles boost {(c.get('boost') or {}).get('rifles')} (expected 1); rifles open {g.get('rifles', {}).get('options')}"), d

    # -- the hire through the panel's own handlers: the area, the card; the gold once, the order waits, the seats unchanged
    def shire(self):
        g, o = self.c["plan"]["hire"]
        r = self.cz("pick", {"group": g, "option": o}, 60)
        if r.get("missing"):
            return "failed", f"no component {r['missing']} on the panel", r
        self.sleep(0.8)
        self.shoot("ch_picker")
        b, a = r["before"], r["after"]
        hire = self.hire_of(g, o)
        paid = (b.get("gold") or 0) - (a.get("gold") or 0)
        ga = a["groups"][g]
        ok = paid == hire and ga.get("order") == o and (a.get("old") or {}).get(g) == (b.get("old") or {}).get(g) and a.get("plan") == b.get("plan")
        self.start_gold = b.get("gold")
        return ("ok" if ok else "differs"), (f"{g}: {o} by the card's click: paid {paid} (the hire {hire}); the model {ga.get('standing')} -> order {ga.get('order')}; the note "
                                             f"«{ga.get('note')}»; the old module still {(a.get('old') or {}).get(g)}; seats {'unchanged' if a.get('plan') == b.get('plan') else 'CHANGED'}"), r

    def schanges(self):
        g, o = self.c["plan"]["hire"]
        _, other = self.c["plan"]["other"]
        start = getattr(self, "start_gold", None)
        steps, ok = [], True
        for opt, want_paid in ((other, self.hire_of(g, other)), (o, self.hire_of(g, o)), ("empty", 0), (o, self.hire_of(g, o))):
            r = self.cz("pick", {"group": g, "option": opt}, 60)
            if r.get("missing"):
                steps.append(f"{opt}: no card"); ok = False
                continue
            a = r["after"]
            held = (start or 0) - (a.get("gold") or 0)
            order = a["groups"][g].get("order")
            good = held == want_paid and order == (None if opt == "empty" else opt)
            ok = ok and good
            steps.append(f"{opt}: order {order}, held {held} (expected {want_paid}){'' if good else ' WRONG'}")
        return ("ok" if ok else "differs"), "the gold is the hire of the order that waits, after each click: " + "; ".join(steps), {"steps": steps}

    def sside(self):
        side = self.c["plan"]["side"]
        r = self.cz("side", {"side": side})
        if r.get("missing"):
            return "differs", f"no mark {r['missing']} on the plan", r
        c = r["crew"]
        mk = self.c["malakai"]
        plan = c.get("plan") or {}
        ok = c.get("side") == side and plan.get(mk["seats"][side]) == f"mtb_bp_malakai_rail_{side}" and plan.get(mk["helm_seat"]) == mk["helm_crew"]
        self.shoot("ch_side")
        return ("ok" if ok else "differs"), (f"side {c.get('side')}; {mk['seats'][side]} -> {plan.get(mk['seats'][side])}; {mk['seats']['left']} -> {plan.get(mk['seats']['left'])}; "
                                             f"helm -> {plan.get(mk['helm_seat'])}; bridge writes {c['bridge']['writes']}"), r

    def sturn_hire(self):
        self.cz("close")
        g, o = self.c["plan"]["hire"]
        back, once, text, d = self.turn("hire", self.upkeep_of(g, o))
        c = d["after"]
        plan = c.get("plan") or {}
        mk, side = self.c["malakai"], self.c["plan"]["side"]
        rifles = [s for s in self.c["rifle_seats"] if s != mk["seats"][side]]
        rows = {s: plan.get(s) for s in rifles}
        boosted = all(str(v).startswith(f"mtb_bp_{o}_") and str(v).endswith("_b1") for v in rows.values())
        ok = back and c["groups"][g].get("standing") == o and (c.get("old") or {}).get(g) == o and boosted and plan.get(mk["seats"][side]) == f"mtb_bp_malakai_rail_{side}" \
            and plan.get(mk["helm_seat"]) == mk["helm_crew"] and c.get("status") == "applied"
        self.before_battle = c
        return ("ok" if ok and once else "differs"), (f"{text}; the model {g} {c['groups'][g].get('standing')}, the old module {(c.get('old') or {}).get(g)}; the 11 rifle seats "
                                                     f"{'all ' + o + ' at boost 1' if boosted else rows}; Malakai {mk['seats'][side]} -> {plan.get(mk['seats'][side])}, helm -> "
                                                     f"{plan.get(mk['helm_seat'])}; crew status {c.get('status')}; bridge writes {c['bridge']['writes']}; cargo {c.get('cargo')} "
                                                     f"(the battle's {c.get('cargo_battle')})"), d

    # -- ONE battle by tools/crew_cycle.py: the men read from memory, every seat against the old module's choice, Malakai's two seats by the hook
    def sbattle(self):
        if self.fake:
            restart = self.send("return fake_restart_crew()", 20)
            c = self.crew()
            return "info", f"the battle is not simulated in the fake; the campaign Lua restarted instead: {restart.get('result')}; the bridge attached {c['bridge']['attached']}, " \
                           f"the old module {c.get('old')}", {"crew": c}
        mk, side = self.c["malakai"], self.c["plan"]["side"]
        self.s.malakai = {"seat": mk["seats"][side], "row": f"mtb_bp_malakai_rail_{side}", "helm_seat": mk["helm_seat"], "helm_row": mk["helm_crew"]}
        got = {}
        saver = self.s.save_result
        self.s.save_result = lambda result: (got.update(result), saver(result))
        try:
            self.s.battle({"label": "crew_hire", "from_game": True, "ammo_report": True, "fight": 90, "shots": ["right", "left", "wheel_30", "deck"]})
        finally:
            self.s.save_result = saver
            self.s.malakai = None
        want = self.c["group_seats"] + 1        # every seat of a group and the helm
        ok = got.get("seats_ok") == want and not got.get("seats_bad") and got.get("back_on_map")
        return ("ok" if ok else "differs"), (f"seats as the old module chose them: {got.get('seats_ok')} of {want} good, bad {got.get('seats_bad')} (Malakai's two seats checked "
                                             f"by the hook); fired {got.get('fired')}, kills {got.get('kills')}, the barge's hp {got.get('hp')}, ammo left {got.get('ammo')}; "
                                             f"the battle's ammunition {got.get('ammo_report')}; back on the map {got.get('back_on_map')}; men in men_crew_hire.txt"), got

    def safter_battle(self):
        d = self.data("load", {}, 120)      # the campaign Lua started again: the screen as the switch gives it now
        c = self.crew()
        self.sleep(3.0)
        c2 = self.crew()
        barge = self.cz("barge")
        b = getattr(self, "before_battle", {}) or {}
        same = c.get("old") == b.get("old") and c.get("plan") == b.get("plan")
        g, o = self.c["plan"]["hire"]
        return ("ok" if same and c["bridge"]["attached"] and c2.get("gold") == c.get("gold") else "differs"), \
            (f"after the battle: screen by {d.get('how')}; bridge attached {c['bridge']['attached']}; the crew {'as before the battle' if same else 'CHANGED: ' + str(c.get('old'))}; "
             f"the model {g} {c['groups'][g].get('standing')}; gold {c.get('gold')} then {c2.get('gold')} (a load moves nothing); the barge's strength {barge.get('strength')} "
             f"(what the battle took), harpoon bundle {barge.get('harpoon_off')}"), {"crew": c, "barge": barge}

    # -- the losses: the building that opened the kind demolished (the model's own demolish), the turn: the crew leaves the seats and the panel says so
    def sdemolish(self):
        k = self.c["keys"]["demolish"]
        r = self.cz("demolish", {"key": k})
        return ("ok" if (r.get("result") or {}).get("ok") else "differs"), f"{k.removeprefix(PREFIX)}: {r.get('result')}; status {r.get('status')}", r

    def sturn_lose(self):
        back, once, text, d = self.turn("lose", 0)
        c = d["after"]
        g, o = self.c["plan"]["hire"]
        plan = c.get("plan") or {}
        mk, side = self.c["malakai"], self.c["plan"]["side"]
        empty = all(plan.get(s) == "mtb_bp_empty" for s in self.c["rifle_seats"] if s != mk["seats"][side])
        msg = str(c.get("message") or "")
        ok = back and c["groups"][g].get("standing") == "empty" and (c.get("old") or {}).get(g) == "empty" and empty and "сошли с корабля" in msg
        self.sleep(1.0)
        self.cz("pick", {"group": g, "option": "empty"}, 60)        # the picker open on the place: what the player sees now
        self.sleep(0.8)
        self.shoot("ch_lost")
        self.cz("close")
        return ("ok" if ok and once else "differs"), (f"{text}; the model {g} {c['groups'][g].get('standing')}, the old module {(c.get('old') or {}).get(g)}, the rifle seats "
                                                     f"{'empty' if empty else {s: plan.get(s) for s in self.c['rifle_seats']}}; boost {c.get('boost')}; the panel: «{msg}»"), d

    def screw_smoke(self):
        row = self.send(self.lib + "\nreturn _G.mtb_ch.smoke()", 30)
        text = str(row.get("result"))
        bad = [l for l in text.splitlines() if "\tERR" in l]
        return ("ok" if row.get("ok") and not bad else "failed"), f"this session's helpers: {text.replace(chr(10), '; ')}", {"raw": text}

    def run(self):
        order = [("census", "Lua environment census", self.icensus),
                 ("smoke", "ship_panel's helpers once each, a canary after each", self.ssmoke),
                 ("crew_smoke", "this session's helpers once each", self.screw_smoke),
                 ("load", "the panel's modules by the switch", self.sload),
                 ("configure", "the probe's answers as options", self.sconfigure),
                 ("bridge", "the crew module attached to the screen's model; Malakai at the default rail, a crew dwarf at the helm", self.sbridge),
                 ("barge", "the barge's hull ordered by the model (a real order)", self.sbarge),
                 ("turn_barge", "turn end 1: the barge built, Malakai on it; the treasury's movers watched", self.sturn_barge),
                 ("openers", "the openers: the dummies (crossbows + the riflemen's boost) and the gun ports (the bay) by script, the beer hall (pirates) ordered", self.sopeners),
                 ("turn_openers", "turn end 2: the places open; the old module sees the bare bay and the boost", self.sturn_openers),
                 ("hire", "a kind hired through the panel's own handlers: the gold once, the order waits, the seats unchanged", self.shire),
                 ("changes", "the order changed four times in the turn: the gold always the hire of the order that waits", self.schanges),
                 ("side", "Malakai's side by its mark on the plan: the seat plan follows", self.sside),
                 ("save", "the state saved and read back", self.ssave("before the hire's turn")),
                 ("turn_hire", "turn end 3: the order stands; the seats as the old module writes them; the upkeep taken once, by the model", self.sturn_hire),
                 ("battle", "ONE battle: the men read from memory against the old module's choice, Malakai's seats, the ammunition", self.sbattle),
                 ("after_battle", "the campaign Lua again: the bridge, the crew, the gold, the barge's strength", self.safter_battle),
                 ("demolish", "the building that opened the kind demolished by the model", self.sdemolish),
                 ("turn_lose", "turn end 4: the crew goes with its building: the seats empty, the panel says so", self.sturn_lose),
                 ("save_final", "saved and read back at the end", self.ssave("at the end"))]
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
                if no in ("load", "bridge", "crew_smoke") and rec["status"] in ("failed", "timeout"):
                    raise pp.SessionAbort(f"step {no} {rec['status']}: {str(rec.get('answer'))[:800]}")
                if no == "turn_hire" and rec["status"] == "failed":
                    raise pp.SessionAbort("the hire's turn did not come back: no battle on an unknown crew")
        except pp.SessionAbort as e:
            how = f"aborted early: {e}"
            self.write({"step": "abort", "status": "aborted", "answer": str(e)})
            self.s.log("ABORT", e)
        except TimeoutError as e:
            how = f"hard limit: {e}"
        except Exception as e:
            how = f"error: {type(e).__name__}: {e}"
        (self.dir / "crew_hire_money.json").write_text(json.dumps(self.money_log, ensure_ascii=False, indent=1), encoding="utf-8")
        return how

    def summary(self, how, analysis=None):
        lines = [f"crew hire session {datetime.now():%d.%m.%Y %H:%M}, ended: {how}"]
        if self.gifts:
            lines.append("given by script (points and gold short for an order): " + "; ".join(
                f"{g['step']} {g['key'].removeprefix(PREFIX)}: points {g['before'].get('points')} -> {g['after'].get('points')}, gold {g['before'].get('gold')} -> {g['after'].get('gold')}" for g in self.gifts))
        for no, r in self.results.items():
            lines.append(f"[{no}] {r['status']:<9} {r['title']}: {r['answer']}")
        text = "\n".join(lines)
        (self.dir / "crew_hire_summary.txt").write_text(text + "\n", encoding="utf-8")
        return text


# ---------------------------------------------------------------- the fake game (dry run; py -3.10, lupa) ----------------------------------------------------------------

# After ship_panel's fake campaign: its stand-in of the old crew module replaced by the REAL one of the session pack (its data generated by the build),
# with what the module reads of the campaign; its memory write is a recorder (no memreader in the fake), as tools/crew_bridge_offline.py's.
FAKE_CREW = r"""
local f = cm:get_faction()
local m = f:character_list():item_at(0)
local mf = m:military_force()
local bundles, svr, ready = {}, {}, {}
f.is_human = function() return true end
f.military_force_list = function() return {num_items = function() return 1 end, item_at = function() return mf end} end
m.has_ancillary = function() return true end
mf.has_effect_bundle = function(_, b) return bundles[b] == true end
cm.apply_effect_bundle_to_force = function(_, b) bundles[b] = true end
cm.remove_effect_bundle_from_force = function(_, b) bundles[b] = nil end
cm.show_message_event = function() end
core.svr_save_string = function(_, k, v) svr[k] = v end
core.svr_load_string = function(_, k) return svr[k] end
ModLog = function() end
tww3_mtb_campaign.when_ready = function(cb) ready[#ready + 1] = cb end
tww3_mtb_campaign.find_malakai = function() return m end
core:remove_listener('fake_old_crew_turn')
fake_crew_writes = 0
local crew_src
function fake_load_crew(src)
  crew_src = src or crew_src
  ready = {}
  tww3_mtb_crew = nil
  local fn = assert(loadstring(crew_src, '@tww3_mtb_crew.lua'))
  fn()
  local C = tww3_mtb_crew
  C.apply = function()
    fake_crew_writes = fake_crew_writes + 1
    C.last_plan = C.seat_plan()
    core:svr_save_string('mtb_crew_ammo_mod', tostring(C.ammo_mod()))
    C.status = 'applied'
    return true
  end
  for _, cb in ipairs(ready) do cb() end
  return tostring(C.status) .. ', writes ' .. fake_crew_writes
end
function fake_restart_crew() return fake_load_crew(nil) end
"""


def fake_main(config_path):
    import game_lua_env as genv
    from lupa import lua51
    use_own_pack()
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    rt = lua51.LuaRuntime(unpack_returned_tuples=True)
    load = rt.eval("function(s, name) local f, err = loadstring(s, name); return f ~= nil, err end")
    for name, text in (("the sent chunk", ch_lib() + "\nreturn 1"), ("fake game", pp.FAKE_GAME), ("fake campaign", ss.FAKE_CAMPAIGN), ("fake crew", FAKE_CREW)):
        ok, err = load(text, name)
        print(f"syntax {name}: {'ok' if ok else err}")
        if not ok:
            return 2
    rt.execute(pp.FAKE_GAME)
    rt.execute(ss.FAKE_CAMPAIGN)
    rt.execute(FAKE_CREW)
    files = ss.pack_files_now()
    for n in ss.ALL_MODULES:
        rt.globals().fake_files[f"script/campaign/tww3_mtb/{n}.lua"] = files[ss.FOLDER + n + ".lua"].decode("utf-8")
    removed, lacks = genv.apply(rt)
    print(f"the game's Lua emulated (tools/game_lua_env.py): UTF-8 string.find/sub/len, removed {removed or 'nothing'}")
    conf = rt.execute(files[ss.FOLDER + "tww3_mtb_ship_config.lua"].decode("utf-8"))
    rt.globals().fake_set_levels(conf.levels)
    # the mod's first tick: the crew module (the real one) starts, its bridge starts the screen by the switch
    print("first tick, the crew module:", rt.globals().fake_load_crew(files[CREW].decode("utf-8")))

    def transport(code, wait):
        try:
            return {"ok": True, "result": rt.execute(code)}
        except Exception as e:
            return {"ok": False, "result": str(e)}
    run_dir = OUT / "fake_run"
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    session = ss.FakeSession(time.time() + 600)
    session.safe_end_turn = lambda: transport("return fake_end_turn()", 10).get("ok") is True
    s = CrewHireSession(cfg, transport, session, run_dir, fake=True)
    how = s.run()
    print(s.summary(how))
    bad = [no for no, r in s.results.items() if r["status"] in ("failed", "timeout")]
    differs = [no for no, r in s.results.items() if r["status"] == "differs"]
    print("fake run:", how, "| steps failed:", bad or "none", "| differ:", differs or "none", "| folder", run_dir)
    return 1 if bad or differs or how != "completed" else 0


# ---------------------------------------------------------------- the launch ----------------------------------------------------------------

def session_main(argv):
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
        f"  1. {sys.executable} {Path(__file__).name} _session --label crew_hire --timeout {limit + 120} --packs harness campaign --user-mods memreader_plus.pack"
        + ("" if args.small else " --set x_res=1920 y_res=1080"),
        f"     -> tools/run_game.py: lock {sg.LOCK} = «mtb, начало HH:MM»; packs from {PACK} (the switch on); our mod list; used_mods.txt only read;",
        f"        low graphics, windowed {res}, Normal difficulty, RTX checked; no focus, under other windows (focus guard); the user's folders put back.",
        "  2. main menu -> new campaign wh3_dlc25_dwf_malakai, the end turn button, peace with everyone, events accepted.",
        "  3. census, smoke (ship_panel's helpers and this session's, canary after each); load the screen by the switch; the bridge attached (else ABORT);",
        "     the hull II ordered (points and gold by script when short); turn end 1 (the barge, Malakai on it); the dummies and the gun ports stood by",
        "     script (idle force, no construction in a slot), the beer hall ordered; turn end 2 (the places; the bare bay and the boost in the old",
        "     module); crossbows hired by the picker's card (gold once,",
        "     the seats unchanged); the order changed 4 times (pirates, crossbows, nobody, crossbows: the gold each time); Malakai to the right by the",
        "     plan's mark; save and read back; turn end 3 (the order stands: 11 crossbows at boost 1 + Malakai at ap_crew_right_1 + the crew captain",
        "     at the helm; the upkeep moved once, by the model, none by the old module); ONE battle (tools/crew_cycle.py: men from memory, every seat",
        "     against the old module's choice, Malakai's seats by the hook, the ammunition's report, pictures right/left/wheel_30/deck); the campaign",
        "     Lua again (the bridge, the crew, the barge's strength); the dummies demolished; turn end 4 (the crossbows leave the seats, the panel",
        "     says so; a picture of the place); save and read back.",
        "  4. STOP flag -> run_game.py closes only the game it started, waits until tasklist has no Warhammer3.exe, removes the lock.",
        f"  hard limit {limit} s (~{limit // 60} min); expected 25-35 min: start and new campaign 8-12, four turn ends 4-8 (86 s each on 15.11), the battle 5-8, the rest 4-6.",
    ])


def run(args):
    limit = args.limit
    built = build_pack()
    print(f"session pack {PACK}: {built['campaign']} {built['bytes']} bytes, {built['files']} files; switch on; the screen's modules from src/ (differing from "
          f"build/campaign/pack): {built['replaced_from_src'] or 'none'}; the crew module as built (its src/ checked)")
    cfg = make_config()
    print(f"config {CONFIG}: keys {cfg['crew']['keys']}")
    print("checks before a launch (CLAUDE.md):")
    rows = checks()
    for what, ok, blocking, detail in rows:
        print(f"  [{'ok' if ok else ('STOP' if blocking else 'note')}] {what}: {detail}")
    blockers = [r for r in rows if r[2] and not r[1]]
    stash_blocked = [r for r in blockers if r[0].startswith("data/") and "author's" in r[0]]
    other = [r for r in blockers if r not in stash_blocked]
    fake = subprocess.run(["py", "-3.10", str(Path(__file__).resolve()), "_fake", str(CONFIG)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("the session against the fake game (py -3.10, lupa, the game's emulated Lua, the real crew module):")
    print("\n".join("  " + l for l in (fake.stdout + fake.stderr).strip().splitlines()[-60:]))
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
    session = cc.Session("crew_hire", started + limit)
    session.current = {}
    cmd = [sys.executable, str(Path(__file__).resolve()), "_session", "--label", "crew_hire", "--timeout", str(limit + 120),
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
        shutil.copy2(CONFIG, session.dir / "crew_hire_config.json")
        session.log("run", session.dir)
        session.wait_mode("frontend", 240)
        time.sleep(10)
        session.log(session.plain(f'frontend.start_campaign("wh3_main_combi", "wh3_main_combi", "{pp.FACTION_KEY}"); return 1', 10)["result"])
        session.wait_mode("campaign", 900)
        time.sleep(8)
        end = time.time() + 200
        while time.time() < end and session.visible("button_end_turn") in ("-", "inactive"):
            time.sleep(3)
        session.shot("ch_map")
        session.log("peace", session.prog("return P.peace()")["result"])
        accept = ('local n = 0; for _ = 1, 4 do local e = mtb.find("events", true); local b = e and mtb.find("button_accept", true, e); '
                  'if b then b:SimulateLClick(); n = n + 1 end end; return n')
        for _ in range(2):
            session.log("events", session.plain(accept, 10)["result"])
            time.sleep(2)
        session.log("blockers", session.script("dismiss_blockers.lua")["result"])
        s = CrewHireSession(cfg, rc.send, session, session.dir)
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
        if s:
            s.write(final)
            print(s.summary(how))
        elif session.dir:
            with (session.dir / "crew_hire.jsonl").open("a", encoding="utf-8") as f:
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
