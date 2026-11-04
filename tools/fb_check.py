"""The whole batch of docs/feedback.md in one running game: py -3.14 tools/crew_cycle.py session fb_live (it holds), then py -3.14 tools/fb_check.py [stage ...]

Stages run in order in the same game process: buildings by real orders (gold and points by script), the crew read from the game after each, a few battles in a row with the seats read from
memory, the speed measured in the air, pictures. A failed stage is written to the log and the next one goes on. Results: build/crew/cycle/results.jsonl, session fb_main; pictures in the run's folder.
Ends the session unless --keep.
"""
import argparse
import math
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import crew_cycle as cc  # noqa: E402
import rc  # noqa: E402

TESTS = cc.TESTS
KILL_LIMIT = 20

MEASURE = r"""
local u = C.lord_unit()
local p = u:position()
local uc = _G.mtb_crew_uc
if mtb_step == 'order' then
  local a = _G.mtb_dir or 1
  _G.mtb_dir = -a
  uc:goto_location(battle_vector:new(p:get_x() + a * 350, p:get_y(), p:get_z() + a * 350), true)
  return 'ordered'
end
local t = bm:time_elapsed_ms()
local last = _G.mtb_last
_G.mtb_last = {x = p:get_x(), z = p:get_z(), t = t}
if not last or t == last.t then return 'first' end
return string.format('%.3f', math.sqrt((p:get_x() - last.x) ^ 2 + (p:get_z() - last.z) ^ 2) / ((t - last.t) / 1000))
"""


class Run(cc.Session):
    def ok(self, label, good, note=""):
        self.save_result({"session": self.name, "label": label, "kind": "fb", "ok": bool(good), "note": str(note)[:500]})
        if not good:
            self.fails.append(label)

    def expect_state(self, label, parts, absent=()):
        text = str(self.prog("return P.state()")["result"])
        missing = [p for p in parts if p not in text] + ["NOT " + p for p in absent if p in text]
        self.ok(label, not missing, f"missing {missing}: {text}" if missing else text)
        return text

    def build(self, *names, turns=1):
        self.order({"prog_build": ",".join(names), "dev": 40, "gold": 40000})
        time.sleep(1)
        have = str(self.prog("return P.ctx('MilitaryForceContext.HordeContext.BuildingSlotList.Size')")["result"])
        self.log("slots", have)
        for _ in range(turns):
            self.prog("return P.peace()")
            self.safe_end_turn()
        self.prog("return P.peace()")
        self.script("dismiss_blockers.lua")

    def speed(self, label, seconds=12):
        """Metres per battle second of the unit in level flight, the last stretch of a long straight order."""
        self.plain(f"mtb_step='order'\n" + MEASURE, 8)
        time.sleep(seconds)     # speed 3: the ramp is over
        self.plain("mtb_step='sample'\n" + MEASURE, 8)
        values = []
        for _ in range(4):
            time.sleep(1.5)
            r = str(self.plain("mtb_step='sample'\n" + MEASURE, 8)["result"])
            try:
                values.append(float(r))
            except ValueError:
                pass
        values.sort()
        return values[len(values) // 2] if values else None

    def fight(self, label, shots=(), speed=False, forsage=False, abilities=None):
        result = {"session": self.name, "label": label, "kind": "battle"}
        self.sync_current()
        self.log("=== fight", label, self.current)
        self.log("spawn", self.script("spawn_fight.lua")["result"])
        self.open_panel()
        self.log(self.click("button_attack"))
        self.wait_mode("battle", 300)
        time.sleep(4)
        men = self.lua("return C.men()", 20)
        (self.dir / f"men_{label}.txt").write_text(str(men["result"]), encoding="utf-8")
        read = str(self.plain((TESTS / "battle_read.lua").read_text(encoding="utf-8"), 15)["result"])
        (self.dir / f"read_{label}.txt").write_text(read, encoding="utf-8")
        result["seats_ok"], result["seats_bad"] = self.seats_ok(men["result"], {})
        for cam in cc.SPEC["cameras"]:
            if cam["name"] in shots:
                self.lua(f'return C.camera({cam["f"]},{cam["r"]},{cam["u"]},{cam["tf"]},{cam["tr"]},{cam["tu"]},{cam["fov"]})', 10)
                time.sleep(1.5)
                self.shot(f'{label}_{cam["name"]}')
        self.plain("bm:end_current_battle_phase(); return 1", 5)
        time.sleep(3)
        self.log("fight", self.lua((TESTS / "crew_fight.lua").read_text(encoding="utf-8"), 10)["result"])
        self.plain("bm:modify_battle_speed(3); return 1", 5)
        result["ammo"] = str(self.plain("return tostring(tww3_mtb_ammo.status) .. ' cargo ' .. tostring(tww3_mtb_ammo.cargo) .. ' | ' .. tww3_mtb_ammo.report()", 8)["result"])
        if speed:
            result["speed"] = self.lua(f"mtb_step='order'\n{MEASURE}", 8) and None
            self.lua("mtb_step='sample'\n" + MEASURE, 8)
            result["speed"] = self.speed_c(14)
        if forsage:
            # at speed 1: the ability lasts 15 seconds of the battle's clock
            self.plain("bm:modify_battle_speed(1); return 1", 5)
            result["speed_before_forsage"] = self.speed_c(6)
            ability = self.plain('mtb_ability = "mtb_forsage"\n' + (TESTS / "battle_ability.lua").read_text(encoding="utf-8"), 8)
            result["forsage_cast"] = str(ability["result"])
            time.sleep(2.5)
            self.shot(f"{label}_forsage_on")
            self.lua("mtb_step='sample'\n" + MEASURE, 8)
            values = []
            for _ in range(4):
                time.sleep(1.2)
                try:
                    values.append(float(str(self.lua("mtb_step='sample'\n" + MEASURE, 8)["result"])))
                except ValueError:
                    pass
            self.log("forsage speed", values)
            result["speed_forsage"] = max(values) if values else None
            self.plain("bm:modify_battle_speed(3); return 1", 5)
            time.sleep(4)
            self.shot(f"{label}_after_forsage")
        self.shot(f"{label}_fight")
        result["abilities"] = re.findall(r"mtb_\w+|\w*spear_of_grungni\w*|\w*thunderburner\w*", read)[:12]
        self.save_result(result)
        self.results[label] = result
        self.log(self.script("battle_kill_enemy.lua")["result"])
        for attempt in range(KILL_LIMIT):
            if self.visible("button_dismiss_results") != "-":
                break
            if attempt == 8:
                self.plain("bm:end_battle(); return 1", 5)
            time.sleep(3)
        self.log(self.click("button_dismiss_results"))
        self.wait_mode("campaign", 300)
        time.sleep(4)
        self.back_on_map()
        self.prog("return P.peace()")
        return result

    def speed_c(self, seconds):
        """With crew_lib's C in the environment."""
        self.lua("mtb_step='order'\n" + MEASURE, 8)
        time.sleep(seconds)
        self.lua("mtb_step='sample'\n" + MEASURE, 8)
        values = []
        for _ in range(4):
            time.sleep(1.2)
            r = str(self.lua("mtb_step='sample'\n" + MEASURE, 8)["result"])
            try:
                values.append(float(r))
            except ValueError:
                pass
        values.sort()
        self.log("speed", values)
        return values[len(values) // 2] if values else None

    def tree(self, label, category="compartments"):
        """The game's tree of an empty slot, as the mouse opens it, with the cards laid on it."""
        code = (TESTS / "tree_open.lua").read_text(encoding="utf-8")
        self.prog("return P.select_malakai()")
        time.sleep(1)
        self.click("tab_horde_buildings")
        time.sleep(1)
        self.log("tree 1", self.plain(f'mtb_step="slot"; mtb_set="{category}"\n' + code, 8)["result"])
        time.sleep(1)
        self.log("tree 2", self.plain(f'mtb_step="set"; mtb_set="{category}"\n' + code, 8)["result"])
        time.sleep(1.2)
        self.shot(label + "_hover")
        healthy = self.plain("return type(core:get_ui_root():Id())", 8)["result"]
        self.log("ui after hover", healthy)
        self.ok(label + "_ui_healthy", healthy == "string", healthy)
        if healthy != "string":
            return
        self.log("tree 3", self.plain(f'mtb_step="read"; mtb_set="{category}"\n' + code, 8)["result"])
        self.shot(label)


def hire_stage(s):
    """The hire of docs/design/barge-loadout.md in the game: gold is read after every step, clicks are the panel's own."""
    Q = (TESTS / "crew_panel.lua").read_text(encoding="utf-8") + "\nlocal Q = _G.mtb_panel\n"

    def gold():
        return float(s.plain("return cm:get_faction('wh3_dlc25_dwf_malakai'):treasury()", 8)["result"])

    def q(code):
        return str(s.plain(Q + code, 15)["result"])

    def lua(code):
        return str(s.plain(code, 10)["result"])

    def crew():
        return lua("return tww3_mtb_crew.get().rifles .. ' order=' .. tostring(tww3_mtb_crew.orders().rifles) .. ' paid=' .. tostring(cm:get_saved_value('mtb_crew_order_paid_rifles')) .. ' changed=' .. tostring(tww3_mtb_crew.changed('rifles'))")

    def log_lines(pattern):
        path = cc.rg.rb.GAME / "tww3_mtb_log.txt"
        text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        return [x for x in text.splitlines() if re.search(pattern, x)][-4:]

    # 1. an order through a click on the panel's row
    s.build("airship_hull_2", "mtb_nest_1", "mtb_hatches_1")
    s.build("crew_weapons_1", "mtb_guns_1", "beer_hall_1")
    s.build("airship_hull_3")
    s.build("crew_weapons_2", "support_radius_1", "mtb_nest_2", "mtb_hatches_2")
    s.build("mtb_guns_2", turns=2)
    s.prog("return P.peace()")
    s.plain('tww3_mtb_crew.set("cannons", "stock"); return 1', 8)
    hire_a, hire_b = 82, 105
    g0 = gold()
    q("Q.click_button(); return 1")
    time.sleep(1.5)
    q("Q.plate('rifles'); return 1")
    time.sleep(0.8)
    s.shot("h_panel_before")
    q("Q.row('quarrellers'); return 1")
    time.sleep(1)
    g1 = gold()
    state = crew()
    s.shot("h_panel_ordered")
    s.ok("h1_order_pays", g0 - g1 == hire_a and state.startswith("pirates order=quarrellers") and f"paid={hire_a}" in state, f"{g0} -> {g1}: {state}")
    # 2. taking it back
    q("Q.row('pirates'); return 1")
    time.sleep(1)
    g2 = gold()
    state = crew()
    s.ok("h2_back_returns", g2 == g0 and "order=false" in state or "order=nil" in state and g2 == g0, f"{g2}: {state}")
    answer = lua("return tostring(select(2, tww3_mtb_crew.choose('rifles', 'quarrellers')))")
    s.ok("h2_second_order_refused", "changed" in answer and gold() == g0, answer)
    # the panel's other groups, for the pictures
    q("Q.plate('cannons'); return 1")
    time.sleep(0.8)
    s.shot("h_panel_cannons")
    q("Q.plate('bombs'); return 1")
    time.sleep(0.8)
    s.shot("h_panel_bombs")
    q("Q.plate('cupolas'); return 1")
    time.sleep(0.8)
    s.shot("h_panel_cupolas")
    q("Q.close(); return 1")
    s.prog("return P.peace()")
    s.safe_end_turn()
    s.prog("return P.peace()")
    # 7. too little gold
    have = gold()
    lua(f"cm:treasury_mod('wh3_dlc25_dwf_malakai', {-(have - 10):.0f}); return 1")
    time.sleep(0.5)
    q("Q.click_button(); return 1")
    time.sleep(1.5)
    q("Q.plate('rifles'); return 1")
    time.sleep(0.8)
    s.shot("h_panel_poor")
    tip = q("return Q.hover_row('quarrellers')")
    time.sleep(1)
    s.shot("h_panel_poor_tip")
    desc = lua("return mtb.dump(tww3_mtb_crew_ui.describe())")
    q("Q.row('quarrellers'); return 1")
    time.sleep(0.8)
    state = crew()
    s.ok("h7_no_gold", "order=false" in state or "order=nil" in state, f"gold {gold()} {state} | {desc[:300]} | tip {tip[:200]}")
    s.ok("h7_no_change_used", "changed=false" in state and gold() == 10, state)
    q("Q.close(); return 1")
    lua(f"cm:treasury_mod('wh3_dlc25_dwf_malakai', {have - 10:.0f}); return 1")
    # 3, 4. a save with the order waiting, a real load through the game's menu; a battle reloads the campaign too
    g3 = gold()
    s.ok("h3_choose", lua("return tostring(tww3_mtb_crew.choose('rifles', 'quarrellers'))") == "true", crew())
    g4 = gold()
    s.ok("h3_paid", g3 - g4 == hire_a, f"{g3} -> {g4}")
    s.save_game("tww3_mtb_hire_load.save")
    time.sleep(2)
    lua("_G.mtb_before_load = true; return 1")
    loaded = False
    for step in ("button_menu", "button_load"):
        s.log("menu", s.click(step))
        time.sleep(2)
    s.shot("h_load_panel")
    pick = lua("""local list = mtb.find('savegames', true); if not list then return 'no list' end
local box = find_uicomponent(list, 'list_box') or list; local n = box:ChildCount(); if n == 0 then return 'empty' end
local first = UIComponent(box:Find(0)); first:SimulateLClick(); return first:Id() .. ' of ' .. n""")
    s.log("load pick", pick)
    time.sleep(1.5)
    s.log("confirm", s.click("button_confirm_load"))
    time.sleep(3)
    for name in ("button_tick",):
        if s.visible(name) != "-":
            s.log(s.click(name))
    end_time = time.time() + 200
    while time.time() < end_time:
        time.sleep(4)
        row = rc.send("return mtb and mtb.mode .. ' ' .. tostring(_G.mtb_before_load) .. ' ' .. tostring(tww3_mtb_crew and tww3_mtb_crew.status)", 5)
        text = str(row.get("result"))
        s.log("loading", text[:100])
        if row.get("ok") and "campaign nil" in text and "applied" in text:
            loaded = True
            break
    s.log("really loaded", loaded)
    s.shot("h_after_load")
    if loaded:
        time.sleep(6)
        s.script("dismiss_blockers.lua")
        g5 = gold()
        state = crew()
        s.ok("h3_load_same", g5 == g4 and "order=quarrellers" in state and f"paid={hire_a}" in state, f"{g4} -> {g5}: {state}")
        # 4. taken back after the load, once
        lua("tww3_mtb_crew.choose('rifles', 'pirates'); tww3_mtb_crew.choose('rifles', 'pirates'); return 1")
        s.ok("h4_back_once_after_load", gold() == g4 + hire_a, f"{gold()} from {g4}: {crew()}")
        s.prog("return P.peace()")
        s.safe_end_turn()
        lua("return tostring(tww3_mtb_crew.choose('rifles', 'quarrellers'))")
    else:
        s.log("no load: the battle's reload instead")
        s.back_on_map(5)
    state = crew()
    g6 = gold()
    s.fight("h_reload", ("left",))
    after = crew()
    s.ok("h3_battle_reload", after == state and gold() >= g6, f"{state} {g6} -> {after} {gold()}: gold may only rise by the battle's loot")
    # the turn carries the order out, without a second charge; 9. upkeep as ever
    upkeep = lua("return tostring(tww3_mtb_crew.upkeep())")
    g7 = gold()
    s.prog("return P.peace()")
    s.safe_end_turn()
    s.prog("return P.peace()")
    g8 = gold()
    state = crew()
    s.ok("h3_turn_carries_out", state.startswith("quarrellers") and ("paid=false" in state or "paid=nil" in state), f"{g7} -> {g8}: {state}; upkeep {upkeep}; {log_lines('upkeep paid|order done')}")
    # 5. replacing: nothing back; going back: paid again
    g = gold()
    lua("tww3_mtb_crew.choose('rifles', 'thunderers'); return 1")
    s.ok("h5_replace_no_refund", g - gold() == hire_b, f"{g} -> {gold()}")
    s.safe_end_turn()
    s.prog("return P.peace()")
    g = gold()
    lua("tww3_mtb_crew.choose('rifles', 'quarrellers'); return 1")
    s.ok("h5_back_paid_again", g - gold() == hire_a, f"{g} -> {gold()}; {crew()}")
    s.safe_end_turn()
    s.prog("return P.peace()")
    # 6. a building goes with an order waiting: the gold comes back
    lua("return 1")
    before = gold()
    order = lua("return tostring(tww3_mtb_crew.choose('rifles', 'thunderers'))")
    s.log("order for the demolish", order, crew())
    paid_now = before - gold()
    s.log("dismantle", s.prog_file("prog_build.lua", mtb_dismantle="crew_weapons_2")["result"])
    s.prog("return P.peace()")
    s.safe_end_turn()
    s.prog("return P.peace()")
    lines = log_lines("hire given back|gone|order gone|locked|upkeep paid")
    state = crew()
    s.ok("h6_demolish_gives_back", any("hire given back rifles" in x for x in lines) and "order=false" in state or "order=nil" in state, f"paid {paid_now}; {state}; {lines}")


def stages(s):
    yield "tree", lambda: s.tree("f_tree_start")
    yield "start", lambda: (
        s.expect_state("f_start", ["slots=airship_hull_1,", "rifles=empty", "cannons=none", "bombs=none", "cupolas=none", "deck=stock", "pub=empty", "harpoon=empty"]),
        s.shot("f_map_start"))

    def prep():
        s.build("mtb_nest_1", "mtb_hatches_1", "airship_hull_2")
        s.expect_state("f_barge", ["airship_hull_2", "mtb_nest_1", "mtb_hatches_1", "rifles=pirates", "cupolas=empty", "bombs=empty", "cannons=none", "pub=empty", "deck=stock"])
        s.fight("f1_plain", ("left", "right", "below", "deck"), speed=True)
    yield "prep_and_plain_hull", prep

    def first():
        panel = s.panel_state()
        s.ok("f_panel_no_pub", "pub" not in str(s.plain("return mtb.dump(tww3_mtb_crew_ui.describe())", 8)["result"]).split("rows")[0], panel)
        refused = s.plain('return tostring(select(2, tww3_mtb_crew.choose("cannons", "stock")))', 8)["result"]
        s.ok("f_no_guns_yet", refused != "nil", refused)
        s.build("beer_hall_1", "crew_weapons_1", "engines_1", "cargo_hold_1", "mtb_guns_1", "mtb_nest_2", "mtb_hatches_2")
        s.expect_state("f_first", ["beer_hall_1", "crew_weapons_1", "engines_1", "cargo_hold_1", "mtb_guns_1", "pub=stock", "cannons=empty", "rifles=pirates"])
        s.plain('tww3_mtb_crew.set("rifles", "quarrellers"); tww3_mtb_crew.set("cupolas", "axes"); tww3_mtb_crew.set("bombs", "stock"); return 1', 8)
        r = s.fight("f2_first", ("left", "deck", "below"), speed=True)
        men = (s.dir / "men_f2_first.txt").read_text(encoding="utf-8")
        s.ok("f_rifles_boost1", "mtb_bp_quarrellers_crew_left_0_b1" in men, re.findall(r"ap_crew_left_0 \S+", men))
        s.ok("f_cargo_115", "cargo 1.1" in str(r.get("ammo")), r.get("ammo"))
        s.ok("f_pub_there", "mtb_bp_stock_pub_left_front" in men, re.findall(r"ap_pub_left_front \S+", men))
    yield "first_row", first

    def second():
        refused = s.plain('return tostring(select(2, tww3_mtb_crew.choose("cannons", "stock")))', 8)["result"]
        s.ok("f_guns_locked", refused != "nil", refused)
        s.build("airship_hull_3")
        s.build("support_radius_1", "crew_weapons_2", "engines_2", "mtb_nest_3", "beer_hall_2")
        s.build("mtb_guns_2", "mtb_harpoon_1", turns=2)
        s.expect_state("f_second", ["mtb_guns_2", "support_radius_1", "mtb_harpoon_1", "engines_2"])
        answer = s.plain('return tostring(tww3_mtb_crew.choose("cannons", "stock")) .. " " .. mtb.dump(tww3_mtb_crew.orders())', 8)["result"]
        s.ok("f_order_gun", "cannons=stock" in str(answer), answer)
        s.plain('tww3_mtb_crew.choose("harpoon", "on"); tww3_mtb_crew.choose("cupolas", "stock"); return 1', 8)
        s.prog("return P.peace()")
        s.safe_end_turn()
        s.prog("return P.peace()")
        s.expect_state("f_gun_on", ["cannons=stock", "harpoon=on", "cupolas=stock"])
        s.plain('tww3_mtb_crew.set("rifles", "thunderers"); return 1', 8)
        r = s.fight("f3_mid", ("left", "front"), speed=True, forsage=True)
        men = (s.dir / "men_f3_mid.txt").read_text(encoding="utf-8")
        s.ok("f_gun_boost1", "mtb_bp_stock_cannon_left_b1" in men, re.findall(r"ap_cannon_left \S+", men))
        s.ok("f_rifles_boost2", "_b2" in " ".join(re.findall(r"ap_crew_left_0 \S+", men)), re.findall(r"ap_crew_left_0 \S+", men))
        s.ok("f_forsage_there", any("forsage" in a for a in r.get("abilities", [])), r.get("abilities"))
    yield "second_row", second

    def top():
        s.build("airship_hull_4")
        s.build("support_radius_2", "crew_weapons_3", "cargo_hold_2", "mtb_torpedoes_1", "mtb_guns_3", "mtb_hatches_3", turns=2)
        s.build("airship_hull_5")
        s.build("engines_3", "cargo_hold_3", "mtb_guns_4", turns=3)
        s.expect_state("f_top", ["mtb_guns_4", "engines_3", "support_radius_2", "cargo_hold_3", "mtb_hatches_3", "mtb_torpedoes_1"])
        s.plain('tww3_mtb_crew.set("cannons", "organ"); tww3_mtb_crew.set("rifles", "rakers"); tww3_mtb_crew.set("bombs", "fire"); return 1', 8)
        r = s.fight("f4_flagship", ("left", "right", "front", "below", "deck", "back"), speed=True)
        men = (s.dir / "men_f4_flagship.txt").read_text(encoding="utf-8")
        s.ok("f_organ_boost2", "mtb_bp_organ_cannon_left_b2" in men, re.findall(r"ap_cannon_left \S+", men))
        s.ok("f_cargo_160", "cargo 1.60" in str(r.get("ammo")) or "cargo 1.6" in str(r.get("ammo")), r.get("ammo"))
        s.plain("tww3_mtb_crew_ui.open(); return 1", 8)
        time.sleep(1.5)
        s.shot("f_panel_flagship")
        s.plain("tww3_mtb_crew_ui.close(); return 1", 8)
        ratio = (r.get("speed") or 0) / (s.results["f1_plain"].get("speed") or 1)
        s.ok("f_speed_15", 1.08 < ratio < 1.25, f"speed {r.get('speed')} against {s.results['f1_plain'].get('speed')}: {ratio:.3f}")
    yield "top_row", top

    def demolish():
        s.save_result({"session": s.name, "label": "dismantle support_radius", "kind": "dismantle", "turns": s.demolish({"prog_dismantle": "support_radius_2"})})
        s.expect_state("f_signal_gone", ["cannons=empty"], absent=("support_radius_2",))
    yield "demolish_signal", demolish

    def hatches():
        s.plain('tww3_mtb_crew.set("bombs", "empty"); tww3_mtb_crew.set("cannons", "none"); return 1', 8)
        s.fight("f5_hatches", ("below", "left"))
        s.plain('tww3_mtb_crew.set("bombs", "none"); return 1', 8)
        s.fight("f6_no_hatches", ("below",))
    yield "hatches", hatches
    yield "hire", lambda: hire_stage(s)


class _Panel:
    pass


def panel_state(self):
    return str(self.plain("return mtb.dump(tww3_mtb_crew_ui.describe())", 8)["result"])


Run.panel_state = panel_state


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--limit", type=int, default=2400)
    ap.add_argument("--scale", type=float, default=1.0, help="all waits times N: with the user's mods the game answers later")
    args = ap.parse_args()
    cc.SCALE = args.scale
    s = Run("fb_main", time.time() + args.limit)
    s.dir = Path(rc.state()["run"])
    s.current = {g: v["start"] for g, v in cc.OPTIONS["groups"].items()}
    s.fails, s.results = [], {}
    for name, step in stages(s):
        if (args.only and name not in args.only) or (not args.only and name in ("hatches", "hire")):
            continue
        s.log("=== stage", name)
        try:
            step()
        except Exception as e:      # one stage's failure must not lose the next ones
            s.log("STAGE FAILED", name, type(e).__name__, e)
            s.fails.append(name)
            s.shot("failed_" + name)
    s.log("fails", s.fails)
    if not args.keep:
        (cc.OUT / "CONTINUE").write_text("go")
    return 1 if s.fails else 0


if __name__ == "__main__":
    sys.exit(main())
