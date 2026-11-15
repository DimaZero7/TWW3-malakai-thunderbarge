"""Session «crew_hire»: the new panel's hire drives the old mod's crew mechanics in the real game (docs/design/port-to-game.md 8.6). ONE unattended
game, five turn ends, ONE battle: buildings by real orders, a kind hired through the panel's own handlers, the order changed within the turn, the turn
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
Since run 20261115-065150 (its «ok» rested on names and the mod's own words): every verdict rests on a fact read from the game (its components' texts,
tooltips and visibility, the treasury, the men in battle memory) and the summary ends with the table A-G (docs/tools-and-work-plan.md, crew_hire):
A Malakai and the helm from memory + close frames, B the panel against the game's moments, C the turn's report, D the demolish refund, E the panel's
ammunition against the battle's, F the drawn wording and its glyphs, G the start's speed. --break swap_models|panel_stays|event_stays|stale_blocker:
the dry run must fail (event_stays: «moment» says it could not dismiss the message and the later steps say «precondition failed»; stale_blocker:
«moment» says «MOD: stale blocker»). Since run 20261115-091818: the game's messages are answered only by a component visible from the root (the
panel holds several hidden button_accept / choice_button; the first by name is hidden), ONE incident is fired, each step after «moment»
establishes its own precondition, the seats' close frames are placed from the men's positions with candidates and a check for the rigging.
"""
import argparse
import json
import re
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
STAND_TOO = ("mtb_cargo_hold_3",)      # stood by script with the openers, by key (F, E: the ammunition bonus)
TURN = ss.END_TURN_LIMIT + 120
ss.BUDGET.update({"bridge": 60, "barge": 90, "turn_barge": TURN, "openers": 150, "turn_openers": TURN, "hire": 90, "changes": 120, "side": 60,
                  "turn_hire": TURN, "battle": 1000, "after_battle": 150, "demolish": 120, "turn_lose": TURN + 60, "lost": 90, "crew_smoke": 60,
                  "unit_window": 90, "moment": 150, "incident": 90, "refund_two": 90, "turn_refund2": TURN})
# stock incidents for the game's moment by script: in the game's data they have no payload and no option rows (db.pack incidents_tables minus
# cdir_events_incident_payloads_tables and cdir_events_incident_option_junctions_tables, 15.11): a message, nothing changes
INCIDENTS = ["wh3_main_incident_rifts_close_soon", "wh3_main_incident_rifts_close_imminent", "wh3_main_ie_incident_endgame_grudge_too_far_early_warning"]
# the stock HUD buttons whose stock full-screen panels the session opens over the game's event message (B.2, a fact for the author: are the game's
# own panels held back by a plain message?), by the game's own paths (wh3_prologue_kislev_expedition_interventions.lua), closed again by
# CampaignUI.ClosePanel (as the game's scripts close objectives_screen); diplomacy is left out (the mod's blocker counts it a modal panel)
STOCK_PANELS = [("technology", ["hud_campaign", "faction_buttons_docker", "button_technology"], "technology_panel"),
                ("missions", ["hud_campaign", "faction_buttons_docker", "button_group_management", "button_missions"], "objectives_screen")]
RISKY = {"battle": "ONE real battle (tools/crew_cycle.py Session.battle): the campaign Lua restarts after it",
         "turn_barge": "a turn end by script", "turn_openers": "a turn end by script", "turn_hire": "a turn end by script (the new turn's moments left up)",
         "turn_lose": "a turn end by script", "turn_refund2": "a turn end by script", "moment": "a stock incident by script when no moment came",
         "incident": "a stock incident by script"}


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
    # F, E: the cargo hold III stood with the openers: its ammunition x2 for every crew (the battle applies it) gives the crossbows' unit window
    # its bonus line «… с N до M» and the battle the ammunition the panel promises (run 20261115-065150 had neither)
    keys["stands"] += [r["key"] for r in conf["levels"] if r["key"].endswith(STAND_TOO)]
    options = {g["key"]: {o["key"]: {"hire": o["hire"], "upkeep": o["upkeep"], "ammo": o.get("ammo")} for o in g["options"]} for g in conf["groups"]}
    crew = json.loads((REPO / "data" / "crew_options.json").read_text(encoding="utf-8"))
    dem = by_name[PLAN["demolish"]]
    level2 = next(r for r in conf["levels"] if r["chain"] == dem["chain"] and r["level"] == dem["level"] + 1)
    keys["level2"] = level2["key"]
    names = {g["key"]: {o["key"]: o.get("name") for o in g["options"]} for g in conf["groups"]}
    costs = {r["key"]: r["cost"] for r in conf["levels"]}
    cfg["crew"] = {"plan": PLAN, "keys": keys, "options": options, "names": names, "costs": costs, "incidents": INCIDENTS, "malakai": crew.get("malakai_at_rail"),
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

class Precondition(Exception):
    """A step's own precondition could not be established (a game window in the way, the panel not opening): the step says so and stops, instead
    of failing deep inside a click (run 20261115-091818: one event message left up failed B.3, D and C in turn)."""


class CrewHireSession(ss.ShipSession):
    def __init__(self, cfg, transport, session, run_dir, fake=False):
        super().__init__(cfg, transport, session, run_dir, fake)
        self.lib = ch_lib()
        self.jsonl = self.dir / "crew_hire.jsonl"
        self.c = cfg["crew"]
        self.money_log = []
        self.table = []            # the rows of the summary's table (A-G): expected, measured, verdict, picture
        self.reasons = {}          # every refusal text the player reads, by where it was read
        self.fake_variants = {}    # the fake's battle: battle_personalities key -> variant (the session pack's tables)

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
    def turn(self, label, expect_upkeep, **kw):
        before = self.crew()
        self.data("money_on")
        mark = time.time()
        try:
            back = self.end_turn(**kw)
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

    # -- the turn end of the session (Probe.end_turn with two more ways: a picture while the AI's turn runs, the new turn's moments left up)
    def end_turn(self, after_end=None, keep_events=False):
        if self.fake:
            back = self.s.safe_end_turn()
            if after_end:
                after_end()
            return back
        self.s.prog("return P.peace()")
        try:
            self.s.safe_end_turn(limit=pp.END_TURN_LIMIT, keep_events=keep_events, after_end=after_end)
            return True
        except TimeoutError as e:
            if "hard limit" in str(e):
                raise
            self.s.log("turn end not back in time:", e)
            return False

    def row(self, item, expected, measured, verdict, picture=""):
        """One row of the table at the end of the summary (A-G): what was expected, what was MEASURED (a fact read from the game), the verdict."""
        self.table.append({"item": item, "expected": expected, "measured": measured, "verdict": verdict, "picture": picture})

    def shoot_crops(self, name, crops=None, quick=False):
        """A picture; crops {suffix: box in root units} are cut by the analysis (<name>_<suffix>.png, twice the size). quick: no read of the root first
        (the root of the last picture is used): a picture right after a call, when its moment matters (C: the foot within 0.5 s)."""
        if quick and self.shots:
            last = dict(list(self.shots.values())[-1])
            last.pop("crops", None)
            last["time"] = time.strftime("%H:%M:%S")
            self.shots[name] = last
            self.shot(name)
        else:
            self.shoot(name)
        if crops:
            self.shots[name]["crops"] = {k: v for k, v in crops.items() if v}
        (self.dir / "shots.json").write_text(json.dumps(self.shots, ensure_ascii=False, indent=1), encoding="utf-8")

    # -- E, F: the hired kind's unit window (its ammunition, its bonus line) and the picker's upkeep line, read back from the game's components
    def sunit_window(self):
        g, o = self.c["plan"]["hire"]
        r = self.cz("unit_window", {"group": g, "option": o}, 60)
        if r.get("opened") is False:
            return "failed", f"the panel did not open: {r.get('why')}", r
        self.sleep(0.8)
        bonus = (r.get("bonus_lines") or [{}])[0]
        self.shoot_crops("ch_unit_window", {"window": r.get("window_box"), "upkeep": r.get("upkeep_box"), "bonus": bonus.get("box")})
        import glyph_check
        ammo_text = r.get("ammo_text")
        self.panel_ammo = int(re.sub(r"\[\[[^\]]*\]\]", "", ammo_text or "").replace(" ", "").replace(" ", "") or 0) if re.search(r"\d", ammo_text or "") else None
        upkeep = self.upkeep_of(g, o)
        up_text = r.get("upkeep_text") or ""
        want_up = f"со следующего хода {upkeep}"
        bonus_text = bonus.get("text") or ""
        b_ok = bool(re.search(r"с \d+ до \d+", re.sub(r"\[\[[^\]]*\]\]", "", bonus_text)))
        bad = {t: glyph_check.bad_chars(t) for t in (up_text, bonus_text, r.get("ammo_note") or "") if t and glyph_check.bad_chars(t)}
        f_ok = want_up in up_text and b_ok and not bad
        e_measured = self.panel_ammo is not None
        self.row("F", f"upkeep line «…{want_up}», the bonus line «с N до M», only glyphs proven in the game's fonts (tools/glyph_check.py)",
                 f"upkeep «{up_text}»; bonus «{bonus_text}»; glyphs outside the proven set {bad or 'none'}", "ok" if f_ok else "differs",
                 "ch_unit_window_upkeep.png, ch_unit_window_bonus.png")
        answer = (f"unit window of {o}: {r.get('window')}, the card hovered {r.get('hovered')}; ammunition drawn «{ammo_text}» (note «{r.get('ammo_note')}»), the panel's "
                  f"numbers {r.get('ammo_model')}; rows {r.get('rows')}; bonus lines {[x.get('text') for x in r.get('bonus_lines') or []]}; the picker's upkeep line «{up_text}» "
                  f"(expected «…{want_up}»); glyphs outside the proven set {bad or 'none'}")
        return ("ok" if f_ok and e_measured else "differs"), answer, r

    # -- B.1 the turn end with the panel AND the crew's picker open: a moment later nothing of ours on the screen, the log says why
    def sturn_hire(self):
        g, o = self.c["plan"]["hire"]
        pre = self.cz("open_picker", {"group": g})
        self.sleep(0.5)
        open_before = pre.get("look") or {}
        self.shoot("ch_before_turn_end")
        self.cz("turn_watch_on")
        self.cz("log_mark")
        mid = {}

        def during():           # the AI's turn: what the player sees then (the real game only; the fake's turn is one call)
            time.sleep(2.0)
            mid["look"] = self.cz("look")
            self.shoot("ch_turn_end")
        back, once, text, d = self.turn("hire", self.upkeep_of(g, o), after_end=None if self.fake else during, keep_events=True)
        watch = self.cz("turn_watch_read")
        logs = (self.cz("log_since", {"has": "[ship screen]"}).get("lines")) or []
        snaps = watch.get("snaps") or []
        late = next((s["look"] for s in reversed(snaps) if s.get("at", "").startswith("0.6")), None)
        seen = mid.get("look") or late
        closed_lines = [l for l in logs if "] closed" in l]
        why = closed_lines[0].split("] closed", 1)[1].strip(": ") if closed_lines else None
        if seen is None:
            b1_verdict, b1_measured = "not measured", "no look at the screen during the AI's turn (the turn end event was not heard)"
        else:
            root = seen.get("root") or {}
            # gone: the screen closed, its holder hidden, our top-most layer off (a window flagged shown under the hidden holder is listed: it is
            # drawn only if top-most drew over a hidden holder, and the layer is off)
            gone = not seen.get("is_open") and not seen.get("topmost_on") and isinstance(root, dict) and root.get("own") is False
            b1_verdict = "ok" if gone and why else ("differs" if gone else "FAILED")
            b1_measured = (f"before: open {open_before.get('is_open')}, pickers {open_before.get('pickers')}; during the AI's turn (turn {seen.get('turn')}, local turn "
                           f"{seen.get('local_turn')}): open {seen.get('is_open')}, holder {root}, windows still flagged shown under it {seen.get('windows')}, pickers {seen.get('pickers')}, "
                           f"top-most layer {seen.get('topmost_on')}; the log: {closed_lines or 'NO «closed» line'}")
        self.row("B.1", "end turn with the panel and the picker open: everything of ours gone during the AI's turn; the log says it closed and why",
                 b1_measured, b1_verdict, "ch_before_turn_end.png, ch_turn_end.png")
        c = d["after"]
        plan = c.get("plan") or {}
        mk, side = self.c["malakai"], self.c["plan"]["side"]
        rifles = [s for s in self.c["rifle_seats"] if s != mk["seats"][side]]
        rows = {s: plan.get(s) for s in rifles}
        boosted = all(str(v).startswith(f"mtb_bp_{o}_") and str(v).endswith("_b1") for v in rows.values())
        ok = back and c["groups"][g].get("standing") == o and (c.get("old") or {}).get(g) == o and boosted and plan.get(mk["seats"][side]) == f"mtb_bp_malakai_rail_{side}" \
            and plan.get(mk["helm_seat"]) == mk["helm_crew"] and c.get("status") == "applied"
        self.before_battle = c
        status = "failed" if b1_verdict == "FAILED" else ("ok" if ok and once and b1_verdict == "ok" else "differs")
        return status, (f"B.1: {b1_measured} (reason «{why}»); {text}; the model {g} {c['groups'][g].get('standing')}, the old module {(c.get('old') or {}).get(g)}; "
                        f"the 11 rifle seats {'all ' + o + ' at boost 1' if boosted else rows}; Malakai {mk['seats'][side]} -> {plan.get(mk['seats'][side])}, helm -> "
                        f"{plan.get(mk['helm_seat'])}; crew status {c.get('status')}; bridge writes {c['bridge']['writes']}; cargo {c.get('cargo')} "
                        f"(the battle's {c.get('cargo_battle')})"), {**d, "watch": watch, "mid": mid, "log": logs}

    # -- the game's windows: answered by the visible path, a step's precondition established, ONE incident fired, the stock panels probed

    def answer_events(self, limit=8):
        """The game's event messages on the screen answered as the turn end answers them (I.answer_one: a dilemma's first visible choice, a message's
        visible tick, never a hidden component), one a call with a wait for the next queued one. -> (the paths clicked, the game's windows after)."""
        clicks = []
        for _ in range(limit):
            r = self.cz("answer_one")
            if not r.get("up"):
                break
            if not r.get("clicked"):
                clicks.append(f"nothing clicked: {r.get('why') or r.get('err')}")
                break
            clicks.append(r.get("how"))
            self.sleep(1.2)
        self.sleep(0.5)
        return clicks, self.cz("game_windows")

    def establish(self, what):
        """A step's precondition: no game window on the screen (event messages answered by the visible path, the stock panels this session opened
        closed by the game's call). Raises Precondition naming the window still in the way, or the mod's blocker that stays with nothing up."""
        w = self.cz("game_windows")
        closed = []
        for name in w.get("stock_up") or []:
            self.cz("stock_close", {"panel": name})
            closed.append(name)
        clicks = []
        if w.get("events_up") or closed:
            if closed:
                self.sleep(1.0)
            clicks, w = self.answer_events()
        if w.get("up"):
            raise Precondition(f"precondition failed ({what}): the game's window in the way: {'; '.join(w['up'])}; answered {len(clicks)} times by the visible "
                               f"path {clicks[-2:]}; the mod's blocker {w.get('blocker')}")
        b = w.get("blocker")
        if b not in (None, "none"):
            raise Precondition(f"precondition failed ({what}): MOD: stale blocker: no game window is up (events panel {w.get('events')}, the ui manager's "
                               f"event flag {w.get('ui_manager_event_panel')}, dilemma waits {w.get('dilemma_waits')}), yet G.blocker() says «{b}»")
        return {"answered": clicks, "closed": closed, "windows": w}

    def fire_incident(self):
        """ONE stock incident by script: a key, then up to 5 s for the game's IncidentOccuredEvent; the next key only when nothing was heard.
        -> (the key heard or None, [(key, the call's answer, heard)], the read after)."""
        tried = []
        for key in self.c["incidents"]:
            r = self.cz("incident", {"key": key}, 30)
            heard = r.get("heard") or []
            for _ in range(5):
                if heard:
                    break
                self.sleep(1.0)
                heard = self.cz("incident_read", {"keep": True}).get("heard") or []
            tried.append((key, r.get("call"), bool(heard)))
            if heard:
                self.sleep(1.0)         # the message is drawn a moment after the event
                return key, tried, self.cz("incident_read")
        return None, tried, self.cz("incident_read")

    def stock_probe(self, label):
        """B.2's fact for the author: with the game's own message up, do the stock HUD buttons open their stock full-screen panels? Each clicked as
        the player's click arrives, read from the game's components 1.5 s later, shot, closed again by CampaignUI.ClosePanel (its button again if not)."""
        rows = []
        for short, path, panel in STOCK_PANELS:
            c = self.cz("stock_click", {"path": path, "panel": panel})
            row = {"panel": panel, "button": c.get("path"), "found": c.get("found"), "state": c.get("state"), "clicked": c.get("clicked"),
                   "events_before": c.get("events_before"), "opened": None}
            if c.get("clicked") == "sent":
                self.sleep(1.5)
                r = self.cz("stock_read", {"panel": panel})
                self.shoot(f"ch_stock_{label}_{short}")
                self.cz("stock_close", {"panel": panel})
                self.sleep(1.0)
                r2 = self.cz("stock_read", {"panel": panel})
                how = "CampaignUI.ClosePanel"
                if r2.get("panel_up"):
                    self.cz("stock_click", {"path": path, "panel": panel})
                    self.sleep(1.0)
                    r2 = self.cz("stock_read", {"panel": panel})
                    how = "its HUD button again"
                row.update(opened=bool(r.get("panel_up")), message_stayed=bool(r.get("events_up")), blocker=r.get("blocker"), ui_manager_open=r.get("ui_manager_panel_open"),
                           closed=not r2.get("panel_up"), closed_by=how, message_after=bool(r2.get("events_up")), picture=f"ch_stock_{label}_{short}.png")
            rows.append(row)
        return rows

    @staticmethod
    def stock_text(rows):
        parts = []
        for r in rows:
            if r.get("opened") is None:
                parts.append(f"{r['panel']}: button {r.get('button')} found {r.get('found')}, state {r.get('state')}, {r.get('clicked')}: not measured")
            else:
                parts.append(f"{r['panel']} by {r['button']} (state {r.get('state')}): opened {r['opened']}, the message stayed {r['message_stayed']}, the mod's blocker "
                             f"{r.get('blocker')}; closed again {r['closed']} ({r['closed_by']}), the message still up {r['message_after']}")
        return "; ".join(parts)

    @staticmethod
    def stock_fact(rows):
        measured = [r for r in rows if r.get("opened") is not None]
        if not measured:
            return "not measured"
        return "yes" if any(r["opened"] for r in measured) else "no"

    # -- B.2 a turn start with the game's moment up (a dilemma or an event; ONE incident by script when none came): the HUD button inactive with
    # the reason, its click and the screen's own open refused, nothing of ours over the game's window; the stock panels over it (a fact); answered
    # by the visible path, the game's components say nothing is up, only then the mod's blocker; the panel opens by the HUD's own handler
    def smoment(self):
        g, _ = self.c["plan"]["hire"]
        b0 = self.cz("blocker")
        for _ in range(4):          # a dilemma of the turn start may come a moment after the end turn button is free
            if b0.get("adapter") not in ("none", None):
                break
            self.sleep(1.0)
            b0 = self.cz("blocker")
        source, fired = "came by itself at the turn start", None
        if b0.get("adapter") in ("none", None):
            fired, tried, r = self.fire_incident()
            b0 = r["blocker"]
            source = f"none came by itself: ONE incident by script {fired}, tried {tried}, heard {r.get('heard')}"
        if b0.get("adapter") in ("none", None):
            self.row("B.2", "the HUD button inactive with the reason; click and S.open refused; nothing of ours over the game's window", f"no moment: {source}",
                     "not measured")
            return "not_measured", f"no game moment to test against: {source}; blocker {b0}", {"blocker": b0}
        kind = b0.get("adapter")
        self.shoot("ch_moment")
        ev = self.cz("events_read")         # which components the game's message holds: the evidence for the tick
        hud = self.cz("hud", {"refresh": True, "hover": True})
        self.sleep(0.8)
        hb = hud.get("box") or {}
        crop = {"x": hb["x"] - 420, "y": hb["y"] - 260, "w": (hb.get("w") or 60) + 520, "h": (hb.get("h") or 60) + 320, "units": "game"} if hb.get("x") is not None else None
        self.shoot_crops("ch_hud_inactive", {"hud": crop})
        click = self.cz("hud_click", {"direct": True})
        tried = self.cz("try_open")
        self.sleep(0.6)
        self.shoot("ch_moment_refused")
        during = tried.get("look") or {}
        # 2: the game's own panels over the game's own message (the mod's rule is not changed: a fact for the author)
        stock = {kind: self.stock_probe(kind)}
        clicks, w = self.answer_events()
        if kind != "event" and fired is None and not w.get("up"):
            # a dilemma came by itself: the plain message too, ONE incident, the same probe, answered the same way
            fired2, tried2, _ = self.fire_incident()
            if fired2:
                stock["event"] = self.stock_probe("event")
                more, w = self.answer_events()
                clicks += more
        b1 = w.get("blocker")
        up = w.get("up") or []
        stale = not up and b1 not in (None, "none")
        hud2 = self.cz("hud", {"refresh": True})
        opened = {}
        if not up and not stale:
            # the panel opens as the player opens it: the HUD button (its click, then its handler when the click did not move it)
            hc = self.cz("hud_click", {"direct": True})
            opened = {"by_click": hc.get("after_simulated"), "by_handler": hc.get("after_direct"), "log": hc.get("log_simulated") or hc.get("log_direct")}
            self.cz("open_picker", {"group": g})
            self.sleep(0.6)
        self.shoot("ch_moment_after")
        self.cz("close")
        why = (b0.get("can_open") or {}).get("why") if isinstance(b0.get("can_open"), dict) else None
        tip_text = (hud.get("tooltip") or {}).get("text") or ""
        tip_game = (hud.get("tooltip") or {}).get("from") == "game"
        reasons = {"HUD tooltip (" + str((hud.get("tooltip") or {}).get("from")) + ")": tip_text, "S.open": tried.get("why"),
                   "the HUD click (log)": [l for l in (click.get("log_simulated") or []) + (click.get("log_direct") or []) if "open:" in l or "not opened" in l]}
        self.reasons.update({f"B.2 {k}": v for k, v in reasons.items()})
        root = during.get("root") or {}
        ok_hud = hud.get("state") == "inactive" and (not tip_game or (bool(why) and why in tip_text))
        ok_refused = not click.get("after_simulated") and not click.get("after_direct") and tried.get("ok") is False and bool(tried.get("why"))
        ok_nothing = not during.get("is_open") and not during.get("topmost_on") and not (isinstance(root, dict) and root.get("from_root"))
        ok_back = bool(opened.get("by_click") or opened.get("by_handler")) and hud2.get("state") != "inactive"
        answers = ev.get("answers") or []
        evidence = (f"the events panel holds {len(answers)} answer buttons: " + ", ".join(f"{a['path']} ({'shown' if a.get('visible') else 'hidden'})" for a in answers[:8])
                    + f"; the first button_accept by name (what find_uicomponent gave the old dismiss): {ev.get('first_by_name')}; the first choice_button by name "
                    f"{ev.get('first_choice_by_name')}; layouts shown {ev.get('layouts')}")
        answered = f"answered {len(clicks)} times by the visible path {clicks}; the game's windows after: {up or 'none'} (events panel {w.get('events')})"
        if up:
            verdict, status = f"FAILED: the session could not dismiss the message ({'; '.join(up)})", "failed"
        elif stale:
            verdict, status = "MOD: stale blocker", "failed"
        else:
            verdict = "ok" if ok_hud and ok_refused and ok_nothing and ok_back else "differs"
            status = "ok" if verdict == "ok" else "differs"
        measured = (f"{source}: blocker {kind} (events panel {b0.get('events')}, ui manager {b0.get('ui_manager_event_panel')}, dilemma waits "
                    f"{b0.get('dilemma_waits')}, CampaignUI {b0.get('campaign_ui')}); HUD button state {hud.get('state')}, mark {hud.get('mark')}, tooltip «{tip_text}» "
                    f"({'as the game holds it' if tip_game else 'NOT readable from the game: the picture only'}); "
                    f"click: SimulateLClick {click.get('simulated')} -> open {click.get('after_simulated')}, the handler -> open {click.get('after_direct')}; "
                    f"S.open -> {tried.get('ok')}, «{tried.get('why')}»; on the screen: open {during.get('is_open')}, holder {root}, windows {during.get('windows')}; "
                    f"{answered}; then the mod's blocker {b1}, the ui manager's event flag {w.get('ui_manager_event_panel')}; button after {hud2.get('state')}; "
                    f"the panel opened after by the HUD's click {opened.get('by_click')}, by its handler {opened.get('by_handler')}"
                    f"; {evidence}")
        self.row("B.2", "turn start with a dilemma/event: HUD button inactive with the reason; click and S.open refused; nothing of ours over it; answered by the "
                 "visible path -> the game's components show no message -> blocker nil -> the panel opens by the HUD", measured, verdict,
                 "ch_hud_inactive_hud.png, ch_moment_refused.png, ch_moment_after.png")
        facts = "; ".join(f"over {k}: {self.stock_fact(v)} ({self.stock_text(v)})" for k, v in stock.items())
        self.row("B.2 stock", "a fact for the author (the mod's rule unchanged): do the game's own HUD buttons open their full-screen panels over the game's message?",
                 f"stock panels open over an event message: {self.stock_fact(stock.get('event') or [])}; {facts}", "fact",
                 ", ".join(r["picture"] for v in stock.values() for r in v if r.get("picture")))
        answer = f"{verdict}: {measured}; stock panels: {facts}"
        return status, answer, {"before": b0, "events": ev, "hud": hud, "click": click, "tried": tried, "stock": stock, "answered": clicks, "windows_after": w,
                                "hud_after": hud2, "opened": opened}

    # -- B.3 ONE incident by script while the panel and the picker are open in the player's turn: the panel closes itself
    def sincident(self):
        g, _ = self.c["plan"]["hire"]
        expected = "incident by script with the panel and picker open: the panel closes itself"
        try:
            pre = self.establish("B.3")
            op = self.cz("open_picker", {"group": g})
            self.sleep(0.5)
            before = op.get("look") or {}
            if not op.get("opened") or not before.get("is_open"):
                raise Precondition(f"precondition failed (B.3): the panel did not open by S.open: «{op.get('why')}», blocker {before.get('blocker')}")
        except Precondition as e:
            self.row("B.3", expected, str(e), "precondition failed", "")
            return "failed", str(e), {}
        self.cz("log_mark")
        key, tried, r = self.fire_incident()
        logs = (self.cz("log_since", {"has": "[ship screen]"}).get("lines")) or []
        self.shoot("ch_incident")
        seen = r.get("look") or {}
        clicks, w = self.answer_events()
        if not key:
            self.row("B.3", expected, f"no incident issued: {tried}", "not measured", "ch_incident.png")
            return "not_measured", f"no incident was issued by the game: {tried}", {"tried": tried, "read": r}
        root = seen.get("root") or {}
        closed = [l for l in logs if "] closed" in l]
        gone = not seen.get("is_open") and not seen.get("topmost_on") and isinstance(root, dict) and root.get("own") is False
        verdict = "ok" if gone and closed else ("differs" if gone else "FAILED")
        up = w.get("up") or []
        stale = not up and w.get("blocker") not in (None, "none")
        measured = (f"before: open {before.get('is_open')}, pickers {before.get('pickers')} (precondition: answered {pre['answered']}); ONE incident {key} (tried {tried}); "
                    f"then open {seen.get('is_open')}, holder {root}, windows {seen.get('windows')}, pickers {seen.get('pickers')}, blocker {seen.get('blocker')}; log "
                    f"{closed or 'NO «closed» line'}; answered {len(clicks)} times by the visible path {clicks}; the game's windows after {up or 'none'}, the mod's "
                    f"blocker after {w.get('blocker')}")
        self.row("B.3", expected, measured, verdict, "ch_incident.png")
        if up:
            return "failed", measured + "; the session could not dismiss the message", {"tried": tried, "read": r, "log": logs, "after": w}
        if stale:
            return "failed", measured + "; MOD: stale blocker", {"tried": tried, "read": r, "log": logs, "after": w}
        return ("ok" if verdict == "ok" else ("failed" if verdict == "FAILED" else "differs")), measured, {"tried": tried, "read": r, "log": logs, "after": w}

    # -- A: the men of the battle read from memory: Malakai's own variant at his rail, the crew dwarf at the helm, nobody else his
    def malakai_check(self, text):
        mk, side = self.c["malakai"], self.c["plan"]["side"]
        other = "left" if side == "right" else "right"
        seats = {}
        for line in str(text).splitlines():
            m = re.match(r"^\d+ (\S+) (\S+) var=(\S+)", line)
            if m:
                seats[m.group(1)] = (m.group(2), m.group(3))
        rail, helm = mk["rail_variant"], mk["helm_variant"]
        seat, oseat = mk["seats"][side], mk["seats"][other]
        neighbour = re.sub(r"_1$", "_0", oseat)
        checks = []

        def chk(what, ok, got):
            checks.append({"check": what, "ok": bool(ok), "got": got})
        chk(f"{seat}: var={rail}", (seats.get(seat) or (None, None))[1] == rail, seats.get(seat))
        chk(f"{mk['helm_seat']}: row {mk['helm_crew']}, var={helm}", seats.get(mk["helm_seat"]) == (mk["helm_crew"], helm), seats.get(mk["helm_seat"]))
        n = sum(1 for r in seats.values() if r[1] == rail)
        chk(f"exactly one line var={rail}", n == 1, n)
        own = [s for s, r in seats.items() if r[1] == "mtb_dwf_malakai_captain"]
        chk("no line var=mtb_dwf_malakai_captain (Malakai at the wheel)", not own, own)
        o_var, n_var = (seats.get(oseat) or (None, None))[1], (seats.get(neighbour) or (None, None))[1]
        chk(f"{oseat} (the other side's seat 1): the hired kind's man, as {neighbour}", o_var is not None and o_var == n_var and o_var != rail, (seats.get(oseat), seats.get(neighbour)))
        return checks, len(seats)

    def fake_men(self):
        """The fake has no battle: the men a battle would read, from the crew module's seat plan and the pack's rows (their variants)."""
        plan = self.crew().get("plan") or {}
        lines = ["script (fake: the crew module's seat plan, the pack's battle_personalities -> variants)"]
        for i, (seat, row) in enumerate(sorted(plan.items())):
            lines.append(f"{i} {seat} {row} var={self.fake_variants.get(row, '?')} anim=- w=- at 0 0 0")
        text = "\n".join(lines)
        (self.dir / "men_crew_hire.txt").write_text(text, encoding="utf-8")
        return text

    # -- ONE battle by tools/crew_cycle.py: the men read from memory, every seat against the old module's choice, Malakai's two seats by the hook
    def sbattle(self):
        g, o = self.c["plan"]["hire"]
        if self.fake:
            restart = self.send("return fake_restart_crew()", 20)
            got = {"seats_ok": None, "fake": True}
            men = self.fake_men()
        else:
            mk, side = self.c["malakai"], self.c["plan"]["side"]
            self.s.malakai = {"seat": mk["seats"][side], "row": f"mtb_bp_malakai_rail_{side}", "helm_seat": mk["helm_seat"], "helm_row": mk["helm_crew"]}
            got = {}
            saver = self.s.save_result
            self.s.save_result = lambda result: (got.update(result), saver(result))
            try:
                # the overview frames first (crew_hire_right is the analysis' reference of the battle's light), then the seats' close frames placed from
                # the men's own positions (Session.seat_shots: every candidate shot, the analysis keeps the first the rigging does not block); the same
                # four again 3 s into the crew's fire, the battle slowed to a tenth meanwhile
                self.s.battle({"label": "crew_hire", "from_game": True, "ammo_report": True, "fight": 90, "shots": ["right", "left", "wheel_30", "deck", "helm_close"],
                               "seat_shots": SEAT_FRAMES, "fire_seat_shots": SEAT_FRAMES, "fire_shot_after": 3, "fight_cam": "right"})
            finally:
                self.s.save_result = saver
                self.s.malakai = None
            path = self.dir / "men_crew_hire.txt"
            men = path.read_text(encoding="utf-8") if path.exists() else ""
        checks, n = self.malakai_check(men)
        a_ok = n > 0 and all(c["ok"] for c in checks)
        self.row("A (memory)", "the men read from memory: his rail var=mtb_v_malakai_rail (once), the helm mtb_bp_helm_crew / mtb_v_helm_crew, no mtb_dwf_malakai_captain, "
                 "the other side's seat 1 an ordinary man of the hired kind",
                 ("no men read" if n == 0 else "; ".join(f"{'ok' if c['ok'] else 'FAIL'} {c['check']} (got {c['got']})" for c in checks)) + (" [fake: from the seat plan]" if self.fake else ""),
                 "ok" if a_ok else "FAILED", "men_crew_hire.txt")
        frames = [f"crew_hire_{n_}.png" for n_ in SEAT_FRAMES + ["helm_close"]] + [f"crew_hire_firing_{n_}.png" for n_ in SEAT_FRAMES] + ["crew_hire_fight.png"]
        cams = {**{n_: v for n_, v in (got.get("seat_shots") or {}).items()}, **{"firing " + n_: v for n_, v in (got.get("fire_seat_shots") or {}).items()}}
        self.camera_lines = cams
        self.row("A (look)", "his own body and rifle at the right rail with both neighbours (height, scale, feet, the rail), his head and hands (the rifle, the axe), the "
                 "same for the left seat 1 (an ordinary crossbowman), the engineer at the wheel; two frames of him from the proven overview cameras (deck 9°, right 7°); at deployment and 3 s into the fire; no frame misplaced (camera inside the rail) or blocked by the rigging",
                 "pictures only (judged by eye); each seat frame: the first candidate the rigging does not block (the analysis at the end)" if not self.fake
                 else "not measured (fake: no battle)", "see pictures" if not self.fake else "not measured", ", ".join(frames))
        start = None
        m = re.search(rf"{g} {o} (\d+)/(\d+)", str(got.get("ammo_report") or ""))
        if m:
            start = int(m.group(2))
        panel = getattr(self, "panel_ammo", None)
        e_verdict = "not measured" if start is None or panel is None else ("ok" if start == panel else "differs")
        self.row("E", "the panel's ammunition of the hired kind = the battle's start ammunition", f"panel {panel}, battle start {start} (report «{str(got.get('ammo_report'))[:120]}»)",
                 e_verdict, "ch_unit_window_window.png")
        want = self.c["group_seats"] + 1        # every seat of a group and the helm
        seats_ok = self.fake or (got.get("seats_ok") == want and not got.get("seats_bad") and got.get("back_on_map"))
        status = "failed" if not a_ok else ("ok" if seats_ok and e_verdict in ("ok", "not measured" if self.fake else "ok") else "differs")
        return status, (f"Malakai from memory: {'; '.join(('ok ' if c['ok'] else 'FAIL ') + c['check'] + ' got ' + str(c['got']) for c in checks)}; seats as the old module chose them: "
                        f"{got.get('seats_ok')} of {want} good, bad {got.get('seats_bad')}; fired {got.get('fired')}, kills {got.get('kills')}, the barge's hp {got.get('hp')}; "
                        f"the battle's ammunition {got.get('ammo_report')} (start {start}, the panel's {panel}); pictures {frames}; back on the map {got.get('back_on_map')}"), \
            {**got, "malakai_checks": checks}

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

    # -- D: the demolish by the panel's own round button (as the player); before it the game's refund on the slot, the adapter's, the tooltip; the
    # treasury right after; then the panel closed (C: the turn's report comes while it is closed)
    def sdemolish(self):
        k = self.c["keys"]["demolish"]
        try:
            pre = self.establish("D, the demolish by the panel's button")
            op = self.data("open", {}, 200)
            if not op.get("ok"):
                raise Precondition(f"precondition failed (D, the demolish by the panel's button): the panel did not open: «{op.get('err')}»")
        except Precondition as e:
            return "failed", str(e), {}
        self.data("click", {"id": "mtb_tab_tree", "keys": [k]})
        nodes = {n["key"]: n for n in self.data("nodes")["nodes"]}
        node = nodes.get(k)
        before = self.cz("refund_read", {"key": k})
        if not node:
            return "failed", f"{k} is not a slot of the tree (opened {op.get('ok')})", {"before": before}
        sel = self.data("click", {"id": f"mtb_tree_node_{node['index']}", "keys": [k]})
        self.sleep(0.6)
        raze = self.cz("raze_read", {"hover": True})
        self.sleep(0.8)
        self.shoot_crops("ch_raze_tooltip", {"raze": raze.get("box")})
        clicked = self.data("click", {"id": "mtb_ship_demolish", "keys": [k]})
        self.sleep(1.5)
        right_after = self.cz("refund_read", {"key": k})
        self.data("click", {"id": "mtb_ship_close", "keys": [k]})
        state = self.data("state", {"keys": [k]})["levels"][k]["status"].get("state")
        self.refund_one = {"key": k, "before": before, "right_after": right_after, "raze": raze}
        tip_text = (raze.get("tooltip") or {}).get("text") or ""
        n = right_after.get("adapter_refund")
        said = re.search(r"За снос вернётся ([\d\s ]+) золота", tip_text)
        self.reasons["D the round button's tooltip (" + str((raze.get("tooltip") or {}).get("from")) + ")"] = tip_text
        answer = (f"precondition: no game window (answered {pre['answered'] or 'nothing'}); {k.removeprefix(PREFIX)} slot {before.get('slot')}: the game's refund on the slot BuildingContext.DismantleRefundAmount {before.get('game_building_refund')}, "
                  f".DismantleRefundAmount {before.get('game_slot_refund')}; the adapter's {before.get('adapter_refund')}; the round button {raze.get('shown')}, tooltip "
                  f"«{tip_text}» ({(raze.get('tooltip') or {}).get('from')}); treasury before the order {before.get('treasury')}, right after {right_after.get('treasury')}; "
                  f"forecast M.turn_gold {right_after.get('turn_gold')}; the treasury's tooltip «{(right_after.get('gold_tooltip') or {}).get('text')}»; the faction's "
                  f"Income {right_after.get('faction')}, the HUD's income label «{right_after.get('hud_income')}»; status now {state} (expected dismantling); the panel closed")
        # the game's own slot says it is being dismantled (IsDismantling); the tooltip's number is the panel's word for what the turn will pay
        game_dis = (right_after.get("dismantling") or {}).get("v") is True
        return ("ok" if game_dis and said else "differs"), answer + f"; the game's IsDismantling {right_after.get('dismantling')}", \
            {"before": before, "after": right_after, "raze": raze, "select": sel, "click": clicked}

    @staticmethod
    def num(text):
        m = re.search(r"[-+]?\d[\d\s ]*", str(text or ""))
        return int(re.sub(r"[\s ]", "", m.group(0))) if m else None

    def money_verdict(self, label, pre, after_gold, model_moves, expect_refund_text):
        """The game's money of the turn against the panel's forecast: paid = Δtreasury - the faction's income (the context's Income, read before the
        turn); the refund the game paid = paid - the model's own treasury moves (the upkeep). -> (measured text, verdict, refund paid)."""
        before = pre.get("treasury")
        income = (pre.get("faction") or {}).get("income") if isinstance(pre.get("faction"), dict) else None
        fc = pre.get("turn_gold") or {}
        if before is None or after_gold is None or not isinstance(income, (int, float)):
            return (f"treasury {before} -> {after_gold}; Income {income}: the faction's income not readable, the refund not told apart from it"), "not measured", None
        paid = after_gold - before - income
        refund = paid - sum(model_moves or [])
        verdict = "ok" if round(paid) == round(fc.get("net", 0)) else "differs"
        return (f"treasury {before} -> {after_gold}, the faction's Income {income} (HUD label «{pre.get('hud_income')}»): paid besides income {round(paid)}, of it the refund "
                f"{round(refund)} (the model's own moves {model_moves}); forecast M.turn_gold {fc} -> net {fc.get('net')}; the adapter's refund {pre.get('adapter_refund')}, "
                f"the game's slot {pre.get('game_building_refund')} / {pre.get('game_slot_refund')}; {expect_refund_text}"), verdict, refund

    # -- C: the turn's report on the first open after the turn (the panel closed over the turn end); D: what the game paid against the forecast
    def sturn_lose(self):
        k = self.c["keys"]["demolish"]
        g, o = self.c["plan"]["hire"]
        pre = self.cz("refund_read", {"key": k})
        # D's own precondition: the dismantle ordered by the demolish step, as the game's slot says it (IsDismantling)
        d_pre = None if (pre.get("dismantling") or {}).get("v") is True else \
            f"precondition failed (D level I): the game's slot is not dismantling ({pre.get('dismantling')}): the demolish step did not order it ({(self.results.get('demolish') or {}).get('status')})"
        self.cz("close")
        back, once, text, d = self.turn("lose", 0)
        c = d["after"]
        plan = c.get("plan") or {}
        mk, side = self.c["malakai"], self.c["plan"]["side"]
        empty = all(plan.get(s) == "mtb_bp_empty" for s in self.c["rifle_seats"] if s != mk["seats"][side])
        name = self.c["names"][g][o]
        c_expected = ("the HUD's «!» before the open; the first open by the HUD's own handler; on it the drawn foot holds the report (the crossbows leaving); a "
                      "click within 1 s adds its line; after the read time the click's line alone")
        out = {**d, "pre": pre}
        # C's precondition, in the game's order: the turn start's messages answered (the game holds the panel back until then), nothing up
        try:
            est = self.establish("C, the first open after the turn")
        except Precondition as e:
            est, c_measured, c_verdict, c_ok, leaving = None, str(e), "precondition failed", False, False
            self.row("C", c_expected, c_measured, c_verdict, "")
        if est is not None:
            hud = self.cz("hud", {"refresh": True})
            hb = hud.get("box") or {}
            crop = {"x": hb["x"] - 120, "y": hb["y"] - 120, "w": (hb.get("w") or 60) + 240, "h": (hb.get("h") or 60) + 240, "units": "game"} if hb.get("x") is not None else None
            self.shoot_crops("ch_hud_mark", {"hud": crop})
            # the open, its foot and the click «Пусто» in ONE call: the click comes by the game's own timer CLICK_MS after the open (run
            # 20261115-095602: three round trips put it at +1.24 s, after the panel's read time of 1 s)
            t0 = time.time()
            op = self.cz("open_click", {"group": g, "option": "empty", "click_ms": CLICK_MS})
            t_open = time.time()
            self.shoot_crops("ch_report_open", {"foot": op.get("foot_box")}, quick=True)
            t_shot = time.time()
            self.sleep(max(0.2, CLICK_MS / 1000 - (t_shot - t_open)) + 0.4)
            cr = self.cz("click_result")
            p1 = cr.get("result") or {}
            game_after = cr.get("after_s")
            # the click's moment: the game's clock between the open and the click; the driver's when the game's is not read
            # (never earlier than the timer's own delay: os.clock is the process's clock, the fake's ticks take no time)
            t_click = t_open + max(game_after if isinstance(game_after, (int, float)) else 0, CLICK_MS / 1000)
            self.shoot_crops("ch_report_click", {"foot": op.get("foot_box")}, quick=True)
            self.sleep(2.0)
            seen_log = self.cz("log_since", {"has": "report"}).get("lines") or []
            p2 = self.cz("pick_read", {"group": g, "option": "empty"})
            self.shoot_crops("ch_report_after", {"foot": op.get("foot_box")}, quick=True)
            self.cz("close")
            foot0 = (op.get("foot") or "") + " " + str(op.get("foot_tip") or "")
            leaving = name in foot0 and "сошли с корабля" in foot0
            report = op.get("model_report") or ""
            f1, f2 = p1.get("foot") or "", p2.get("foot") or ""
            clicked = bool(p1) and "err" not in p1
            in_time = clicked and (t_click - t_open) < 1.0
            line2 = p2.get("model_message") or ""
            mark = hud.get("mark") or {}
            mark_on = isinstance(mark, dict) and mark.get("from_root") is True
            handler = op.get("handler_opened") is True
            c_ok = leaving and (report[:40] in f1 and f1 != (op.get("foot") or "")) and (report[:40] not in f2 if report else True) and any("seen" in l for l in seen_log)
            c_measured = (f"precondition: answered {est['answered'] or 'nothing'}, closed {est['closed'] or 'nothing'}, blocker {est['windows'].get('blocker')}; HUD button "
                          f"before the open: state {hud.get('state')}, «!» mark {mark}; the HUD's handler opened the panel: {handler} (blocker before it "
                          f"{op.get('blocker_before')}{', its error ' + str(op.get('handler_err')) if op.get('handler_err') else ''}); opened by {op.get('way')} "
                          f"{round(t_open - t0, 2)} s, picture at +{round(t_shot - t_open, 2)} s; the foot as drawn «{op.get('foot')}» (its tooltip «{op.get('foot_tip')}»); "
                          f"the crossbows leaving in it: {leaving}; click «Пусто» by the game's timer {CLICK_MS} ms after the open ({op.get('scheduled')}): done {clicked}, at +{round(t_click - t_open, 2)} s by the game's clock ({'os.clock' if isinstance(game_after, (int, float)) else 'not read: the scheduled time'}; within the 1 s read time: {in_time}): foot «{f1}»{(' ' + str(p1.get('err'))) if p1.get('err') else ''}; 2 s later the log "
                          f"{seen_log}; the click again: foot «{f2}» (the click's line «{line2}»)")
            if not handler:
                c_verdict = "FAILED: the HUD's handler did not open the panel with nothing in the way"
            elif c_ok and in_time and mark_on and hud.get("state") != "inactive":
                c_verdict = "ok"
            elif leaving and not in_time:
                # the report was on the first open, but «a click within 1 s adds its line» was not tried in time: not measured, never «differs»
                c_verdict = (f"not measured: the click «Пусто» {'did not come' if not clicked else f'came at +{round(t_click - t_open, 2)} s'}, not within the 1 s read time "
                             f"(the report on the first open: {leaving}, the «!» mark {mark_on})")
            else:
                c_verdict = "differs" if leaving else "FAILED"
            self.row("C", c_expected, c_measured, c_verdict, "ch_hud_mark_hud.png, ch_report_open_foot.png, ch_report_click_foot.png, ch_report_after_foot.png")
            out.update(hud=hud, open=op, click1=p1, click2=p2, seen_log=seen_log, times=[t0, t_open, t_shot, t_click], establish=est)
        moves = (self.money_log[-1] if self.money_log else {}).get("model") or []
        if d_pre:
            d_measured, d_verdict, refund = d_pre, "precondition failed", None
        else:
            d_measured, d_verdict, refund = self.money_verdict("lose", pre, c.get("gold"), moves, "expected refund of level I (1000 x 0.6) 600")
        self.refund_paid_one = refund
        self.row("D (level I)", "what the game paid at the turn = the panel's forecast (M.turn_gold); the refund 600 for «Манекен» (1000)", d_measured, d_verdict,
                 "ch_raze_tooltip_raze.png")
        ok = back and c["groups"][g].get("standing") == "empty" and (c.get("old") or {}).get(g) == "empty" and empty and leaving
        if c_verdict == "precondition failed" or d_verdict == "precondition failed" or c_verdict.startswith("FAILED"):
            status = "failed"
        else:
            status = "ok" if ok and once and c_verdict == "ok" and d_verdict == "ok" else "differs"
        return status, (f"C: {c_measured}; D: {d_measured}; {text}; the model {g} {c['groups'][g].get('standing')}, the old module {(c.get('old') or {}).get(g)}, the rifle seats "
                        f"{'empty' if empty else {s: plan.get(s) for s in self.c['rifle_seats']}}"), out

    # -- D at level II: «Тир» (crew_weapons_2: 1000 for level I + 1500 for II) stood by script and demolished: does the game give back 60 % of the
    # level (900) or of the line (1500)? One more turn end
    def srefund_two(self):
        k = self.c["keys"]["level2"]
        st = self.cz("stand", {"keys": [k]}, 60)
        self.sleep(1.0)
        pre = self.cz("refund_read", {"key": k})
        r = self.cz("demolish", {"key": k})
        self.sleep(1.5)
        after = self.cz("refund_read", {"key": k})
        self.refund_two = {"key": k, "before": pre, "right_after": after}
        ok = (r.get("result") or {}).get("ok")
        return ("ok" if ok else "differs"), (f"{k.removeprefix(PREFIX)} stood by script {st.get('add')}; the game's refund on the slot {pre.get('game_building_refund')} / "
                                             f"{pre.get('game_slot_refund')}, the adapter's {pre.get('adapter_refund')}; demolished by the model {r.get('result')}; treasury "
                                             f"{pre.get('treasury')} -> {after.get('treasury')} right after; forecast {after.get('turn_gold')}"), {"stand": st, "pre": pre, "after": after, "demolish": r}

    def sturn_refund2(self):
        k = self.c["keys"]["level2"]
        pre = self.cz("refund_read", {"key": k})
        back, once, text, d = self.turn("refund2", 0)
        moves = (self.money_log[-1] if self.money_log else {}).get("model") or []
        cost1, cost2 = self.c["costs"].get(self.c["keys"]["demolish"]), self.c["costs"].get(k)
        lvl, chain = round(cost2 * 0.6), round((cost1 + cost2) * 0.6)
        measured, verdict, refund = self.money_verdict("refund2", pre, d["after"].get("gold"), moves, f"60 % of the level {lvl}, of the line {chain}")
        settled = "not measured" if refund is None else ("the level" if round(refund) == lvl else "the line" if round(refund) == chain else f"neither ({round(refund)})")
        self.row("D (level II)", f"the refund of a level-II building: 60 % of the level ({lvl}) or of the line ({chain}); the forecast = what was paid", f"{measured}; counts: {settled}",
                 verdict, "")
        return ("ok" if back and verdict == "ok" else ("not_measured" if verdict == "not measured" else "differs")), f"{text}; {measured}; the refund counts {settled}", d

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
                 ("unit_window", "E, F: the hired kind's unit window (ammunition, bonus line) and the picker's upkeep line, read back from the game's components", self.sunit_window),
                 ("turn_hire", "turn end 3 with the panel and the picker OPEN (B.1: gone during the AI's turn); the order stands; the upkeep once; the new turn's moments kept",
                  self.sturn_hire),
                 ("moment", "B.2: the turn start's dilemma or event (or an incident by script): the HUD button, its click and S.open refused; answered, the panel opens",
                  self.smoment),
                 ("incident", "B.3: an incident by script with the panel and the picker open: the panel closes itself", self.sincident),
                 ("battle", "ONE battle: Malakai's and the helm's men from memory (A), close frames and the fire, the ammunition against the panel's (E)", self.sbattle),
                 ("after_battle", "the campaign Lua again: the bridge, the crew, the gold, the barge's strength", self.safter_battle),
                 ("demolish", "D: «Манекен» demolished by the panel's round button: the game's refund on the slot, the tooltip, the treasury; the panel closed", self.sdemolish),
                 ("turn_lose", "turn end 4: C the report on the first open (the HUD's mark, the foot, the clicks); D the money against the forecast", self.sturn_lose),
                 ("refund_two", "D: a level-II building (crew_weapons_2) stood by script and demolished", self.srefund_two),
                 ("turn_refund2", "turn end 5: the refund of level II, 900 (the level) or 1500 (the line)", self.sturn_refund2),
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
                if no == "turn_hire" and "turn NOT back" in str(rec.get("answer")):
                    raise pp.SessionAbort("the hire's turn did not come back: no battle on an unknown crew")
                if no in ("moment", "incident") and rec["status"] in ("failed", "timeout"):
                    # whatever the step left up is answered before the battle by the visible path (the battle's panel does not open over a dilemma);
                    # each later step establishes its own precondition all the same
                    try:
                        clicks, w = self.answer_events()
                        self.s.log("answered after", no, clicks, "up:", w.get("up"))
                    except Exception as e:
                        self.s.log("answering after", no, "failed", e)
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

    def g_row(self):
        """G: the start's speed from <run>/timeline.txt (tools/session_timeline.py): the seconds to a playable map, each intro entry skipped, the boot
        movies, the total."""
        path = self.dir / "timeline.txt"
        if not path.exists():
            self.row("G", "playable map in far less than this morning's ~300 s; the three intro entries skipped; boot movies off", "no timeline.txt" + (" (fake)" if self.fake else ""),
                     "not measured")
            return None
        t = path.read_text(encoding="utf-8")
        ready = re.search(r"launch -> map ready \(the whole start\)\s+(\d+) s", t)
        total = None
        stop = re.findall(r"\+\s*([\d.]+)\s+\S+\s+game gone", t)
        if stop:
            total = round(float(stop[-1]))
        skipped = {k: bool(re.search(rf"skip {k} ", t)) for k in ("movie", "flyover", "post_intro_scene")}
        movies = re.search(r"boot movies ([^;\n]+)", t)
        n = int(ready.group(1)) if ready else None
        self.ready_seconds = n
        self.row("G", "playable map well under this morning's ~300 s; movie, flyover and post-intro scene each skipped; boot movies off",
                 f"playable map at {n} s (this morning ~300 s); skipped {skipped}; boot movies {movies.group(1) if movies else 'not recorded'}; total run {total} s",
                 "ok" if n and n < 300 and all(skipped.values()) else ("not measured" if n is None else "differs"), "timeline.txt")
        return n

    def summary(self, how, analysis=None):
        lines = [f"crew hire session {datetime.now():%d.%m.%Y %H:%M}, ended: {how}"]
        if self.gifts:
            lines.append("given by script (points and gold short for an order): " + "; ".join(
                f"{g['step']} {g['key'].removeprefix(PREFIX)}: points {g['before'].get('points')} -> {g['after'].get('points')}, gold {g['before'].get('gold')} -> {g['after'].get('gold')}" for g in self.gifts))
        for no, r in self.results.items():
            lines.append(f"[{no}] {r['status']:<12} {r['title']}: {r['answer']}")
        table = [r for r in self.table if r["item"] != "G"]
        n = self.g_row()
        table.append(self.table[-1])
        lines.append("")
        lines.append(f"playable map at {n if n is not None else 'not measured'} s (this morning ~300 s)")
        if self.reasons:
            lines.append("refusal and refund texts the player reads: " + "; ".join(f"{k}: «{v}»" for k, v in self.reasons.items()))
        frames = {k: v for k, v in ((analysis or {}).get("frames") or {}).items() if not k.startswith("_")}
        if frames and not self.fake:
            # A (look): which candidate each seat frame kept, and the frames the rigging blocked from every candidate (named, not handed on)
            text = "; ".join(f"{k}: {v['verdict']}" + (f" ({v['chosen']}, dark share {v['candidates'].get(v['chosen'])}; candidates {v['candidates']})" if v.get("chosen") else "")
                             for k, v in frames.items())
            blocked = [k for k, v in frames.items() if v["verdict"] != "clear"]
            for r in self.table:
                if r["item"] == "A (look)":
                    r["measured"] = f"{analysis['frames'].get('_rule')}: {text}"
                    r["verdict"] = "see pictures" if not blocked else f"blocked or not shot: {', '.join(blocked)}"
            lines.append("seat frames (A): " + text)
        if getattr(self, "camera_lines", None):
            lines.append("seat cameras (C.seat_camera): " + "; ".join(f"{k}: {v}" for k, v in self.camera_lines.items()))
        bright = (analysis or {}).get("brightness") or {}
        if bright:
            lines.append("brightness of the battle's frames (mean luma of the centre, 0-255; below 45 too dark to judge a model): " +
                         ", ".join(f"{k} {v}" for k, v in bright.items()))
        if (analysis or {}).get("crops"):
            lines.append("close-ups cut: " + ", ".join(analysis["crops"]))
        lines.append("")
        lines.append("| item | expected | measured | verdict | picture |")
        lines.append("|---|---|---|---|---|")
        for r in table:
            cell = lambda s: str(s).replace("|", "/").replace("\n", " ")
            lines.append(f"| {r['item']} | {cell(r['expected'])} | {cell(r['measured'])} | {r['verdict']} | {r['picture']} |")
        text = "\n".join(lines)
        (self.dir / "crew_hire_summary.txt").write_text(text + "\n", encoding="utf-8")
        self.table = [r for r in self.table if r["item"] != "G"]       # the summary may be written again
        return text


# the seats' close frames (data/crew_cycle.json seat_frames): Malakai at the right rail, the left side's seat 1 (an ordinary crossbowman)
SEAT_FRAMES = ["mal_right", "mal_right_face", "seat1_left", "seat1_left_face", "mal_right_from_deck", "mal_right_from_right"]
# a frame is blocked when more than this share of its centre (24 px blocks) is darker than half the light of crew_hire_right's centre (the same
# battle's overview): run 20261115-091818's frames through the net 0.26-0.49, its clear frames 0.08-0.17
BLOCKED_SHARE, DARK_OF_REF = 0.22, 0.5
# C: the click «Пусто» this long after the open, by the game's own timer (the panel's read time is 1000 ms)
CLICK_MS = 500


def dark_share(Image, path, t):
    im = Image.open(path).convert("L")
    w, h = im.size
    box = im.crop((int(w * .25), int(h * .2), int(w * .75), int(h * .78)))
    small = box.resize((max(1, box.width // 24), max(1, box.height // 24)), Image.BOX)
    hist = small.histogram()
    n = sum(hist)
    return round(sum(hist[:max(1, int(t))]) / n, 3) if n else None


def choose_frames(run_dir, Image, ImageStat):
    """Each seat frame (deployment and fire): the first candidate (data/crew_cycle.json order) not blocked by the rigging, copied to the frame's own
    name; all candidates blocked: the least dark one, verdict «blocked». -> {frame: {candidates, chosen, verdict}}."""
    import shutil as sh
    spec = json.loads((REPO / "data" / "crew_cycle.json").read_text(encoding="utf-8")).get("seat_frames") or {}
    ref = run_dir / "crew_hire_right.png"
    if ref.exists():
        im = Image.open(ref).convert("L")
        w, h = im.size
        t = DARK_OF_REF * ImageStat.Stat(im.crop((int(w * .25), int(h * .2), int(w * .75), int(h * .78)))).mean[0]
        how = f"darker than {round(t)} (half of crew_hire_right's centre)"
    else:
        t, how = 28, "darker than 28 (no crew_hire_right.png)"
    out = {"_rule": f"misplaced: the camera not outside the seat's rail by C.seat_camera's geometry (not shot); blocked: more than {BLOCKED_SHARE} of the "
                    f"centre's 24 px blocks {how}"}
    # the camera lines of the battle (tools/crew_cycle.py Session.seat_shots): a candidate the geometry refused says «misplaced»
    path = run_dir / "seat_cameras.json"
    cams = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for prefix in ("crew_hire", "crew_hire_firing"):
        for name in SEAT_FRAMES:
            order = [c["c"] for c in (spec.get(name) or {}).get("candidates", [])]
            lines = (cams.get(prefix) or {}).get(name) or []
            misplaced = [l.split(":", 1)[0] for l in lines if ": misplaced" in l]
            got = {c: dark_share(Image, run_dir / f"{prefix}_{name}__{c}.png", t) for c in order if (run_dir / f"{prefix}_{name}__{c}.png").exists()}
            key = f"{prefix}_{name}"
            if not got:
                out[key] = {"candidates": {}, "chosen": None, "misplaced": misplaced, "verdict": "misplaced" if misplaced else "not shot"}
                continue
            clear = [c for c in order if c in got and got[c] is not None and got[c] <= BLOCKED_SHARE]
            chosen = clear[0] if clear else min(got, key=lambda c: got[c] if got[c] is not None else 1)
            sh.copy2(run_dir / f"{prefix}_{name}__{chosen}.png", run_dir / f"{key}.png")
            out[key] = {"candidates": got, "chosen": chosen, "misplaced": misplaced, "verdict": "clear" if clear else "blocked"}
    return out


def analyse(run_dir):
    """py -3.10 (PIL): the close-ups the session asked for (shots.json crops: <name>_<suffix>.png, twice the size), the seats' frames chosen among
    their candidates (blocked by the rigging or clear) and the brightness of the battle's frames (mean luma of the centre half): <run>/analysis.json."""
    run_dir = Path(run_dir)
    out = {"crops": [], "brightness": {}}
    try:
        from PIL import Image, ImageStat
    except ImportError:
        out["error"] = "no PIL"
        return out
    out["frames"] = choose_frames(run_dir, Image, ImageStat)
    shots = json.loads((run_dir / "shots.json").read_text(encoding="utf-8")) if (run_dir / "shots.json").exists() else {}
    for name, s in shots.items():
        png = run_dir / f"{name}.png"
        k = s.get("ui_scale_effective") or 1
        if not png.exists():
            continue
        im = Image.open(png)
        for suffix, c in (s.get("crops") or {}).items():
            kk = 1 if c.get("units") == "game" else k
            box = [max(0, round(c["x"] * kk)), max(0, round(c["y"] * kk)), min(im.width, round((c["x"] + c["w"]) * kk)), min(im.height, round((c["y"] + c["h"]) * kk))]
            if box[2] > box[0] and box[3] > box[1]:
                part = im.crop(box)
                part.resize((part.width * 2, part.height * 2), Image.NEAREST).save(run_dir / f"{name}_{suffix}.png")
                out["crops"].append(f"{name}_{suffix}.png")
    for png in sorted(run_dir.glob("crew_hire_*.png")):
        if png.stem.endswith(tuple(f"_{x}" for x in ("hud", "foot", "raze", "window", "upkeep", "bonus"))) or "__" in png.stem:
            continue
        im = Image.open(png).convert("L")
        w, h = im.size
        centre = im.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4))
        out["brightness"][png.name] = round(ImageStat.Stat(centre).mean[0])
    (run_dir / "analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


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

-- 15.11 afternoon: what the session's new steps read in the game, as the fake has it
local U = getmetatable(core:get_ui_root())
U.SetTooltipText = function(self, t) self._tip = t end
U.GetTooltipText = function(self) return self._tip or '', '' end
local root = core:get_ui_root()
-- the HUD's ring of buttons the mod's button lives in (src/tww3_mtb_crew_ui.lua refresh_button)
local docker = UIComponent(find_uicomponent(root, 'hud_campaign'):CreateComponent('faction_buttons_docker', 'x'))
UIComponent(docker:CreateComponent('button_group_management', 'x'))
local function make(parent, id, visible) local u = UIComponent(parent:CreateComponent(id, 'x')); if visible == false then u:SetVisible(false) end; return u end
-- the game's real-time callbacks after their delay (C: the click 500 ms after the open must come BEFORE the panel's read time of 1000 ms): a
-- fake_tick is 100 ms (the driver's sleep makes a tick per 100 ms); a callback runs at the first tick at or after its time, in the order of its time
do
  local tm, old_tick, now_ms, later = core:get_tm(), fake_tick, 0, {}
  tm.real_callback = function(self, fn, ms, name) later[#later + 1] = {fn = fn, due = now_ms + (tonumber(ms) or 0), name = name} end
  local remove = tm.remove_real_callback
  tm.remove_real_callback = function(self, name)
    for i = #later, 1, -1 do if later[i].name == name then table.remove(later, i) end end
    return remove(self, name)
  end
  fake_tick = function()
    local n = old_tick()
    now_ms = now_ms + 100
    local due, keep = {}, {}
    for _, c in ipairs(later) do if c.due <= now_ms then due[#due + 1] = c else keep[#keep + 1] = c end end
    later = keep
    table.sort(due, function(a, b) return a.due < b.due end)
    for _, c in ipairs(due) do pcall(c.fn); n = n + 1 end
    return n
  end
end
-- the game's UIComponent walk (ChildCount, Find(i)) for the session's walk of the events panel (tools/tests/crew_hire_session.lua)
U.ChildCount = function(self) return #self._kids end
U.Find = function(self, i)
  if type(i) == 'number' then local k = self._kids[i + 1]; return k and k._addr or nil end
  for _, k in ipairs(self._kids) do if k._id == i then return k._addr end end
end
-- the game's events panel as run 20261115-091818 showed it: ONE component for every message, hidden while none is queued, holding SEVERAL
-- components named button_accept and choice_button, most of them in hidden layouts and found by name BEFORE the tick of a plain message
-- (events > event_layouts > dilemma_active > choice_button (x2); > mission_active > mission_complete > footer > button_accept; > incident_active;
-- events > button_set > accept_holder > button_accept). A click on a hidden component does nothing; the tick answers the message on the screen and
-- the next queued one comes. The ui manager's flag is the game's (lib_campaign_ui.lua is_event_panel_open: the panel open and events Visible)
local events = make(root, 'events', false)
local layouts = make(events, 'event_layouts')
local dl = make(layouts, 'dilemma_active', false)
make(dl, 'choice_button'); make(dl, 'choice_button')
make(make(make(make(layouts, 'mission_active', false), 'mission_complete'), 'footer'), 'button_accept')
local incident_layout = make(layouts, 'incident_active', false)
local incident_text = make(incident_layout, 'dy_title')
local tick = make(make(make(events, 'button_set'), 'accept_holder'), 'button_accept')
local queue = {}
local function show()
  local on = #queue > 0
  events:SetVisible(on); incident_layout:SetVisible(on)
  if on then incident_text:SetStateText(queue[1]) end
end
fake_events_queue = queue
function fake_push_event(key) queue[#queue + 1] = key; show() end
local uim0 = cm.get_campaign_ui_manager
fake_event_flag = nil          -- a break may hold the ui manager's flag (stale_blocker)
cm.get_campaign_ui_manager = function()
  local u = uim0()
  u.is_event_panel_open = function() if fake_event_flag ~= nil then return fake_event_flag end; return events:Visible() end
  u.is_panel_open = function(self, name) if name == 'events' then return events:Visible() end; local p = find_uicomponent(root, name); return p and p:Visible() or false end
  return u
end
fake_incidents = {}
cm.trigger_incident = function(self, faction, key, now)
  if not fake_incidents[key] then return false end
  fake_push_event(key)
  fake_fire('IncidentOccuredEvent', nil, {dilemma = function() return key end, faction = function() return f end})
  return true
end
core:add_listener('fake_events_accept', 'ComponentLClickUp', function(c) return c.string == 'button_accept' end, function(c)
  local ok, b = pcall(UIComponent, c.component)
  if not (ok and b and b == tick and b:VisibleFromRoot()) then return end       -- a hidden button_accept: nothing happens
  table.remove(queue, 1); show()
end, true)
-- the game's turn start may open with a message (the game's real order for C: answered before the panel can open, then the first open's report)
fake_turn_events = {}
core:add_listener('fake_turn_start_events', 'FactionTurnStart', function(c) return c:faction():name() == 'wh3_dlc25_dwf_malakai' end, function()
  local key = fake_turn_events[cm:turn_number()]
  if key then fake_push_event(key) end
end, true)
-- the stock HUD buttons and their stock full-screen panels (each opened over the message here: the fake's guess, the game's answer is B.2's fact)
local docker0 = find_uicomponent(root, 'hud_campaign', 'faction_buttons_docker')
local stock_buttons = {button_technology = 'technology_panel', button_missions = 'objectives_screen'}
make(docker0, 'button_technology')
make(find_uicomponent(docker0, 'button_group_management'), 'button_missions')
local function stock_panel(name) local p = find_uicomponent(root, name); if not p then p = make(root, name, false) end; return p end
core:add_listener('fake_stock_buttons', 'ComponentLClickUp', function(c) return stock_buttons[c.string] ~= nil end, function(c)
  local p = stock_panel(stock_buttons[c.string]); p:SetVisible(not p:Visible())
end, true)
CampaignUI.ClosePanel = function(name) local p = find_uicomponent(root, name); if p then p:SetVisible(false) end end
-- the game's refund of a dismantle when the building goes (campaign_variables building_dismantle_recoup_multiplier_when_full_health 0.6 of the
-- level's price, rounded down: the fake's rule, the question the session asks the game) and the faction's income (none in the fake)
fake_costs = {}
core:add_listener('fake_refund', 'CharacterHordeBuildingDemolished', true, function(c)
  local ok, k = pcall(function() return c:building() end)
  local cost = ok and fake_costs[k]
  if cost then cm:treasury_mod('wh3_dlc25_dwf_malakai', math.floor(cost * 0.6)) end
end, true)
f.command_queue_index = function() return 3 end
local gcv = common.get_context_value
common.get_context_value = function(obj, id, expr)
  if obj == 'CcoCampaignFaction' then
    if expr == 'Income' then return 0 end
    if expr == 'TreasuryAmount' then return f:treasury() end
    return nil
  end
  return gcv(obj, id, expr)
end
-- the mod's own HUD button and its handlers: the REAL src/tww3_mtb_crew_ui.lua of the session pack (its switch on) in place of the stand-in;
-- started after the crew module, as the game's first tick starts both
local ui_ready = {}
function fake_load_ui(src)
  local keep = tww3_mtb_campaign.when_ready
  tww3_mtb_campaign.when_ready = function(cb) ui_ready[#ui_ready + 1] = cb end
  local fn = assert(loadstring(src, '@tww3_mtb_crew_ui.lua'))
  fn()
  tww3_mtb_campaign.when_ready = keep
  return tostring(tww3_mtb_crew_ui.NEW_SHIP_PANEL)
end
function fake_start_ui() for _, cb in ipairs(ui_ready) do cb() end; return #ui_ready end
"""


# --break for the fake (py -3.10 tools/tests/crew_hire_session.py _fake CONFIG --break NAME; also crew_cycle.py session crew_hire --dry-run --break NAME):
# the mod broken on purpose: the session must FAIL the step named here. Lua run in the fake before the first step, or a change of the pack's tables.
BREAKS = {
    # the panel does not close when the turn ends: its turn end listener is never added (the fake has no other faction's turn for the watch)
    "panel_stays": ("turn_hire", r"""
local add = core.add_listener
core.add_listener = function(self, name, ...) if name == 'tww3_mtb_ship_turn_end' then return end; return add(self, name, ...) end
"""),
    # Malakai's rail rows and the helm crew's row swap their variants, every row name kept (tools/seat_models.py swap_malakai_variants)
    "swap_models": ("battle", None),
    # the event message is not dismissed (the tick does nothing, as the hidden button_accept did in run 20261115-091818): «moment» must fail as the
    # session's own failure to answer it, and every later step that needs the screen must say «precondition failed», not fail deep in a click
    "event_stays": ("moment", "core:remove_listener('fake_events_accept')\n"),
    # the message is answered and gone from the screen, but the ui manager's flag the mod's blocker reads stays set: «moment» must say «MOD: stale
    # blocker» (a defect of the mod's rule, not of the session), the later steps the same as their precondition
    "stale_blocker": ("moment", r"""
local trig = cm.trigger_incident
cm.trigger_incident = function(...) local r = trig(...); if r then fake_event_flag = true end; return r end
"""),
}
# what the failing step must say for these breaks; and no cascade: every later step that fails says «precondition failed»
BREAK_SAYS = {"event_stays": "could not dismiss", "stale_blocker": "MOD: stale blocker"}
# the fake's turn start with a message of its own: turn 5, the turn after turn end 4 (turn_lose): C must answer it, then open by the HUD
FAKE_TURN_EVENTS = {5: "fake_turn_start_message"}


def fake_main(config_path, broken=None):
    import game_lua_env as genv
    import seat_models
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
    for key in cfg["crew"]["incidents"]:
        rt.globals().fake_incidents[key] = True
    for key, cost in cfg["crew"]["costs"].items():
        rt.globals().fake_costs[key] = cost
    for turn, key in FAKE_TURN_EVENTS.items():
        rt.globals().fake_turn_events[turn] = key
    if broken:
        step, lua = BREAKS[broken]
        if lua:
            rt.execute(lua)
        print(f"fake BROKEN on purpose: {broken} (the step that must fail: {step})")
    removed, lacks = genv.apply(rt)
    print(f"the game's Lua emulated (tools/game_lua_env.py): UTF-8 string.find/sub/len, removed {removed or 'nothing'}")
    conf = rt.execute(files[ss.FOLDER + "tww3_mtb_ship_config.lua"].decode("utf-8"))
    rt.globals().fake_set_levels(conf.levels)
    # the mod's first tick: the HUD's panel module (the real one, switch on) and the crew module (the real one): its bridge starts the screen
    print("the HUD's panel module, switch:", rt.globals().fake_load_ui(files[ss.CREW_UI].decode("utf-8")))
    print("first tick, the crew module:", rt.globals().fake_load_crew(files[CREW].decode("utf-8")), "| the HUD's panel started:", rt.globals().fake_start_ui())
    # the fake's battle: the men a battle would read are the crew module's seat plan with the pack's rows' variants (the break swaps them)
    tables = seat_models.pack_tables(files, json.loads((REPO / "data" / "db_layouts.json").read_text(encoding="utf-8")))
    mk = cfg["crew"]["malakai"]
    if broken == "swap_models":
        seat_models.swap_malakai_variants(tables, [f"mtb_bp_malakai_rail_{side}" for side in mk["seats"]], mk["helm_crew"])

    def transport(code, wait):
        try:
            return {"ok": True, "result": rt.execute(code)}
        except Exception as e:
            return {"ok": False, "result": str(e)}
    run_dir = OUT / ("fake_run" + (f"_broken_{broken}" if broken else ""))
    shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True)
    session = ss.FakeSession(time.time() + 600)
    session.safe_end_turn = lambda: transport("return fake_end_turn()", 10).get("ok") is True
    s = CrewHireSession(cfg, transport, session, run_dir, fake=True)
    s.fake_variants = {r["key"]: r.get("variant") for r in tables.get("battle_personalities", [])}
    how = s.run()
    log = rt.globals().fake_log
    (run_dir / "tww3_mtb_log.txt").write_text("\n".join(str(log[i]) for i in range(1, len(log) + 1)) + "\n", encoding="utf-8")
    print(s.summary(how, analyse(run_dir)))
    bad = [no for no, r in s.results.items() if r["status"] in ("failed", "timeout")]
    differs = [no for no, r in s.results.items() if r["status"] == "differs"]
    print("fake run:", how, "| steps failed:", bad or "none", "| differ:", differs or "none", "| folder", run_dir)
    if broken:
        step = BREAKS[broken][0]
        rec = s.results.get(step, {})
        caught = rec.get("status") == "failed"
        note = ""
        if broken in BREAK_SAYS:
            says = BREAK_SAYS[broken] in str(rec.get("answer"))
            names = list(s.results)
            later = names[names.index(step) + 1:] if step in names else []
            cascade = [no for no in later if s.results[no]["status"] in ("failed", "timeout") and "precondition failed" not in str(s.results[no]["answer"])]
            prec = [no for no in later if "precondition failed" in str(s.results[no]["answer"])]
            caught = caught and says and not cascade and bool(prec)
            note = (f"; it says «{BREAK_SAYS[broken]}»: {says}; later steps reporting their own precondition: {prec or 'none'}; a cascade (failed deep "
                    f"inside instead): {cascade or 'none'}")
        print(f"broken {broken}: " + (f"the dry run FAILS as it must: step {step} failed{note}" if caught else
                                      f"NOT CAUGHT: step {step} is {rec.get('status')}{note}: the dry run would pass a broken mod"))
        return 1 if caught else 0
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
        pp.skip_intro_plan(getattr(args, "skip_intro", True)),
        "  3. census, smoke (ship_panel's helpers and this session's, canary after each); load the screen by the switch; the bridge attached (else ABORT);",
        "     the hull II ordered (points and gold by script when short); turn end 1 (the barge, Malakai on it); the dummies and the gun ports stood by",
        "     script (idle force, no construction in a slot), the beer hall ordered; turn end 2 (the places; the bare bay and the boost in the old",
        "     module); crossbows hired by the picker's card (gold once, the seats unchanged); the order changed 4 times; Malakai to the right by the",
        "     plan's mark; save and read back;",
        "     E/F: the crossbows' unit window and the picker's upkeep line read back from the game's components (crops);",
        "     B.1: turn end 3 with the panel AND the picker open (a picture 2 s into the AI's turn: nothing of ours; the log's «closed: <why>»);",
        "     the order stands (11 crossbows at boost 1, Malakai at ap_crew_right_1, mtb_bp_helm_crew at the helm; upkeep once, by the model);",
        "     B.2: the new turn's dilemma/event left up (none: ONE stock incident without payload by script, the next key only if none was heard):",
        "     the HUD button inactive with its reason, its click and S.open refused; the stock buttons technology and missions clicked over the",
        "     message (a fact: do the game's own panels open over it?), closed again by CampaignUI.ClosePanel; the message answered by the VISIBLE",
        "     path (events > button_set > accept_holder > button_accept, a dilemma's visible choice), the game's components show nothing up, only",
        "     then the mod's blocker (still set: «MOD: stale blocker»), the panel opens by the HUD; B.3: ONE incident with the panel and the picker",
        "     open: it closes; every later step first establishes its own precondition (no game window) or says «precondition failed: <window>»;",
        "     ONE battle (A: men from memory: var=mtb_v_malakai_rail once at the right rail, mtb_v_helm_crew at the helm, no mtb_dwf_malakai_captain;",
        "     overview frames right, left, wheel_30, deck, helm_close; the seat frames mal_right(_face), seat1_left(_face) placed from the men's own",
        "     positions, outside the hull aft of the seat, three candidates each, again 3 s into the crew's fire at a tenth of the speed; the",
        "     candidate not outside the rail «misplaced» before the move; two frames of him from the deck and right cameras (9°, 7°); the",
        "     analysis keeps the first candidate the rigging does not block, «blocked» otherwise; E: the start ammunition against the panel's);",
        "     the campaign Lua again; D: «Манекен» demolished by the panel's round button (the game's refund on the slot, the tooltip, the",
        "     treasury), the panel closed; C/D: turn end 4: the turn start's messages answered, the HUD's «!», the first open BY THE HUD'S HANDLER",
        "     (FAILED if it does not open with nothing in the way), its foot (the crossbows leaving), «Пусто» by the game's timer 0.5 s after the open",
        "     in the same call (late: «not measured»), again 2 s",
        "     later; the money against the forecast; D: «Тир» (level II) stood by script and demolished, turn end 5: 900 or 1500; save.",
        "  4. STOP flag -> run_game.py closes only the game it started, waits until tasklist has no Warhammer3.exe, removes the lock;",
        "     timeline.txt (G) and the analysis (py -3.10: close-ups, the seat frames chosen, the frames' brightness), the summary's table A-G.",
        f"  hard limit {limit} s (~{limit // 60} min); expected 11-14 min (run 20261115-091818: 10 min 10 s; now the stock panels, the answers, the",
        "  demolish and C that measure, 28 seat frames instead of 7).",
    ])


def boot_movies():
    """The game's boot movies as the preferences have them now (read only): fe_game_intro_video_enabled."""
    try:
        import run_battle as rb
        prefs = rb.PREFS.read_bytes().decode("latin-1") if rb.PREFS.exists() else ""
        line = next((l for l in prefs.splitlines() if l.startswith("fe_game_intro_video_enabled ")), None)
        return f"fe_game_intro_video_enabled {line.split()[1].rstrip(';')}" if line else "fe_game_intro_video_enabled not in the preferences"
    except Exception as e:
        return f"not read: {e}"


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
    broken = getattr(args, "broken", None)
    fake = subprocess.run(["py", "-3.10", str(Path(__file__).resolve()), "_fake", str(CONFIG)] + (["--break", broken] if broken else []),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    print("the session against the fake game (py -3.10, lupa, the game's emulated Lua, the real crew module and HUD panel):")
    print("\n".join("  " + l for l in (fake.stdout + fake.stderr).strip().splitlines()[-90:]))
    print(plan_text(args, limit))
    skip_ok, skip_lines = pp.skip_intro_check()
    print("skip_intro.lua against a stub of the game's Esc stack (py -3.10, lupa):")
    print("\n".join("  " + l for l in skip_lines[-12:]))
    if broken:
        print(f"dry run with the mod broken on purpose ({broken}):", "FAILED, as it must" if fake.returncode != 0 else "PASSED: the session did not catch the break")
        return 1 if fake.returncode != 0 else 0
    if args.dry_run:
        print("\n".join(sg.describe()))
        state = "would launch" if not blockers else ("would STOP: " + "; ".join(r[0] for r in blockers))
        if stash_blocked and not other:
            state += " (with --stash-user-pack and the author's yes it would launch)"
        print("dry run:", state, "| fake game:", "ok" if fake.returncode == 0 else f"FAILED ({fake.returncode})", "| skip_intro:", "ok" if skip_ok else "FAILED")
        return 0 if fake.returncode == 0 and skip_ok else 1
    if fake.returncode != 0 or (args.skip_intro and not skip_ok):
        print("not launching: the session failed against the fake game" if fake.returncode != 0 else "not launching: skip_intro.lua failed its check")
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
    session.skip_intro = args.skip_intro
    session.current = {}
    movies = boot_movies()
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
        session.launch_started = rc.state().get("started")
        session.mark("launch (run_game.py)")
        session.new_campaign(pp.FACTION_KEY)     # the intro skipped unless --option skip_intro=0 (tools/crew_cycle.py Session.new_campaign)
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
        session.mark("stop asked")
        if proc is not None and proc.poll() is None:
            rg.STOP.write_text("stop")
        if proc is not None:
            try:
                proc.wait(240)
            except subprocess.TimeoutExpired:
                session.log("run_game.py did not end in 240 s: it keeps the lock while a game is in tasklist")
        gone = not cc.rg.rb.game_running()
        session.mark("game gone" if gone else "a game is still in tasklist")
        # G: the boot movies as the preferences had them at the launch (the game's own setting; run_game.py does not change it)
        session.finish_timeline(f"skip_intro {'on' if session.skip_intro else 'off'}; boot movies {movies}")
        status = {}
        if session.dir and (session.dir / "status.json").exists():
            status = json.loads((session.dir / "status.json").read_text(encoding="utf-8"))
        restored = mt.restore_user_pack(print) if stashed else None
        final = {"step": "end", "finished": True, "how": how, "seconds": round(time.time() - started), "game_gone": gone,
                 "lock_removed": not sg.OUR_LOCK.match(sg.read_lock() or ""), "run_game": status, "user_pack_restored": restored}
        analysis = None
        if session.dir:
            # the close-ups and the frames' brightness need PIL (py -3.10): after the game is gone, never a cost to the run's own results
            try:
                r = subprocess.run(["py", "-3.10", str(Path(__file__).resolve()), "_analyse", str(session.dir)], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=300)
                path = session.dir / "analysis.json"
                analysis = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"error": (r.stdout + r.stderr)[-500:]}
            except Exception as e:
                analysis = {"error": f"{type(e).__name__}: {e}"}
        if s:
            s.write(final)
            print(s.summary(how, analysis))
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
        broken = argv[argv.index("--break") + 1] if "--break" in argv else None
        rest = [a for a in argv[1:] if a not in ("--break", broken)]
        if broken and broken not in BREAKS:
            raise SystemExit(f"--break {broken}: one of {sorted(BREAKS)}")
        return fake_main(rest[0] if rest else CONFIG, broken)
    if argv and argv[0] == "_analyse":
        out = analyse(argv[1])
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--small", action="store_true")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    ap.add_argument("--stash-user-pack", action="store_true")
    ap.add_argument("--option", action="append", default=[], metavar="skip_intro=0|1", help="skip_intro=0: the new campaign's intro played, today's waits")
    ap.add_argument("--break", dest="broken", choices=sorted(BREAKS), default=None,
                    help="the dry run with the mod broken on purpose in the fake: it must FAIL (exit 1) and name the step")
    args = ap.parse_args(argv)
    if args.broken:
        args.dry_run = True
    args.skip_intro = pp.skip_intro_args(args.option)
    return run(args)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
