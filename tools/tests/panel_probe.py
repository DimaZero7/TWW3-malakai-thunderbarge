"""One run for section 8 of docs/design/panel-upgrades-proposal.md: py -3.14 tools/crew_cycle.py session fb_hire, then py -3.14 tools/tests/panel_probe.py [stage ...]

Every answer goes to the run's log.txt and to build/crew/cycle/results.jsonl, session panel_probe. Pictures in the run's folder. Probes only: the frozen mod is not changed.
"""
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "tools"))
import crew_cycle as cc  # noqa: E402
import fb_check as fc  # noqa: E402
import rc  # noqa: E402

TESTS = cc.TESTS
LIB = (TESTS / "prog_lib.lua").read_text(encoding="utf-8") + "\n" + (TESTS / "panel_probe.lua").read_text(encoding="utf-8").rsplit("return 'ready'", 1)[0] + "\nlocal P = _G.mtb_prog\nlocal Q0 = 1\n"


class Probe(fc.Run):
    def z(self, code, wait=20):
        row = rc.send(LIB + code, wait)
        return str(row.get("result"))

    def note(self, label, value):
        self.log(label, value)
        self.save_result({"session": "panel_probe", "label": label, "kind": "probe", "state": str(value)[:1500]})
        return value

    def q(self, label, code, shot=None, wait=1.0):
        value = self.z(code)
        self.note(label, value)
        if shot:
            time.sleep(wait)
            self.shot(shot)
        return value


def tab(s):
    s.q("1 start", "Z=_G.mtb_z; Z.select(); return Z.tab_state()", "p1_start", 1.5)
    s.q("1 siblings", "return _G.mtb_z.siblings()")
    s.q("1 hide", "return _G.mtb_z.hide_tab()", "p1_hidden", 1)
    s.q("1 after 1 s", "return _G.mtb_z.tab_state()")
    s.q("1 after deselect", "local Z=_G.mtb_z; Z.deselect(); return Z.tab_state()")
    time.sleep(1)
    s.q("1 after reselect", "local Z=_G.mtb_z; Z.select(); return Z.tab_state()")
    time.sleep(1.5)
    s.q("1 after reselect +1.5 s", "return _G.mtb_z.tab_state()", "p1_reselect")
    # open it, then back to the army tab through the game's own tab: hiding it while open breaks the bindings (run 20261104-191037)
    s.q("1 open it", "local b=_G.mtb_z.F('tab_horde_buildings'); b:SimulateLClick(); return _G.mtb_z.tab_state()", "p1_tab_open", 1.2)
    s.q("1 to the army tab", "local b=_G.mtb_z.F('tab_army'); b:SimulateLClick(); return _G.mtb_z.tab_state()", None)
    time.sleep(1)
    s.q("1 hide again", "return _G.mtb_z.hide_tab()", "p1_hide_again", 1)
    s.q("1 health", "return tostring(_G.mtb_z.healthy())")
    # the strip of the horde on the map
    s.q("1 click bar", "return _G.mtb_z.click_bar()", "p1_bar_clicked", 1.5)
    s.q("1 tab after the bar", "return _G.mtb_z.tab_state()")
    # with a watcher that hides it again
    s.q("1 watch", "local Z=_G.mtb_z; Z.watch_tab(); return Z.tab_state()")
    for i in range(3):
        s.z("local Z=_G.mtb_z; Z.deselect(); return 1")
        time.sleep(0.5)
        s.z("local Z=_G.mtb_z; Z.select(); return 1")
        time.sleep(1)
    s.q("1 watcher after 3 selections", "return tostring(_G.mtb_tab_shown) .. ' ' .. _G.mtb_z.tab_state()", "p1_watched")


def order(s):
    s.q("2 give", "return _G.mtb_z.give(60000, 60)")
    # nobody selected, the stock expression
    s.q("2 none selected, stock way", "local Z=_G.mtb_z; Z.deselect(); local g=Z.gold(); local r=Z.order('airship_hull_2', 0, 'selected'); return r .. ' gold ' .. g .. ' -> ' .. Z.gold()")
    time.sleep(1.5)
    s.q("2 read", "local Z=_G.mtb_z; return Z.gold() .. ' ' .. Z.slot_read(0)", "p2_none_selected")
    # nobody selected, the record reached from the character's context
    s.q("2 none selected, own way", "local Z=_G.mtb_z; Z.deselect(); local g=Z.gold(); local r=Z.order('airship_hull_2', 0, 'own'); return r .. ' gold ' .. g .. ' -> ' .. Z.gold()")
    time.sleep(1.5)
    read = s.q("2 read own", "local Z=_G.mtb_z; return Z.gold() .. ' ' .. Z.slot_read(0)")
    if "item=true" not in read:
        # selected in the same call, tab hidden
        s.q("2 select and order at once", "local Z=_G.mtb_z; Z.hide_tab(); Z.select(); local g=Z.gold(); local r=Z.order('airship_hull_2', 0, 'selected'); return r .. ' gold ' .. g .. ' -> ' .. Z.gold()")
        time.sleep(1.5)
        read = s.q("2 read at once", "local Z=_G.mtb_z; return Z.gold() .. ' ' .. Z.slot_read(0)")
    if "item=true" not in read:
        s.q("2 selected a moment ago", "local Z=_G.mtb_z; Z.select(); return 1")
        time.sleep(3)
        s.q("2 order", "local Z=_G.mtb_z; local g=Z.gold(); local r=Z.order('airship_hull_2', 0, 'selected'); return r .. ' gold ' .. g .. ' -> ' .. Z.gold()")
        time.sleep(1.5)
        read = s.q("2 read after wait", "local Z=_G.mtb_z; return Z.gold() .. ' ' .. Z.slot_read(0)")
    # the cancel
    gold = s.z("return _G.mtb_z.gold()")
    s.q("2 cancel", "return _G.mtb_z.cancel(0)")
    time.sleep(1.5)
    s.q("2 after cancel", f"local Z=_G.mtb_z; return 'gold {gold} -> ' .. Z.gold() .. ' ' .. Z.slot_read(0)")
    # and the order again, for the rest of the run; a side building through the panel's own situation: crew panel not open, tab hidden
    s.q("2 order again", "local Z=_G.mtb_z; Z.select(); return Z.order('airship_hull_2', 0, 'selected')")
    time.sleep(1.5)
    s.q("2 side buildings", "local Z=_G.mtb_z; local n=Z.first_empty(); return Z.order('mtb_nest_1', n, 'selected') .. ' slot ' .. n")
    time.sleep(1)
    s.q("2 read side", "local Z=_G.mtb_z; local n=Z.first_empty(); return Z.slot_read(1) .. ' | ' .. Z.slot_read(2) .. ' | next empty ' .. tostring(n)", "p2_ordered")


def reads(s):
    s.q("3 reads, nothing open", "local Z=_G.mtb_z; Z.select(); return Z.reads('mtb_guns_1', Z.first_empty())")
    s.q("3 reads, deselected", "local Z=_G.mtb_z; Z.deselect(); return Z.reads('mtb_guns_1', Z.first_empty())")
    s.z("return _G.mtb_z.select()")


def units(s):
    s.q("4 listen", "return _G.mtb_z.listen_units()")
    s.q("4 stance and units", "local Z=_G.mtb_z; return Z.fleet() .. ' | ' .. Z.units()")
    s.q("4 can before", "local Z=_G.mtb_z; return 'miner ' .. Z.can('wh_main_dwf_inf_miners_0') .. ' warrior ' .. Z.can('wh_main_dwf_inf_dwarf_warrior_0') .. ' cannon ' .. Z.can('wh_main_dwf_art_cannon')")
    s.q("4 grant, one", "return _G.mtb_z.grant('wh_main_dwf_inf_dwarf_warrior_0')", "p4_grant", 1.5)
    s.q("4 after", "local Z=_G.mtb_z; return Z.fleet() .. ' | ' .. Z.first_unit_strength('wh_main_dwf_inf_dwarf_warrior_0')")
    s.q("4 fill", "local Z=_G.mtb_z; local o={} for i=1,22 do o[#o+1]=Z.grant('wh_main_dwf_inf_miners_0'):match('units (%d+)') end return table.concat(o,',') .. ' | ' .. Z.fleet()")
    time.sleep(1)
    s.q("4 full", "local Z=_G.mtb_z; return Z.grant('wh_main_dwf_inf_longbeards') .. ' | ' .. Z.fleet()", "p4_full", 1)


def recruit(s):
    s.q("5 button", "local Z=_G.mtb_z; Z.select(); return Z.recruit_button()")
    time.sleep(1)
    s.q("5 where and home", "local Z=_G.mtb_z; return Z.where() .. ' | ' .. Z.home_settlement()")
    s.q("5 open at sea", "return _G.mtb_z.open_recruit()", "p5_recruit_field", 1.5)
    s.q("5 list", "return _G.mtb_z.recruit_list()")
    s.q("5 close", "return _G.mtb_z.open_recruit()")
    s.q("5 go home", "return _G.mtb_z.go_home()")
    time.sleep(3)
    s.q("5 at home", "local Z=_G.mtb_z; Z.select(); return Z.where() .. ' | ' .. Z.recruit_button()")
    time.sleep(1)
    s.q("5 open at home", "return _G.mtb_z.open_recruit()", "p5_recruit_home", 1.5)
    s.q("5 list at home", "return _G.mtb_z.recruit_list()")
    s.q("5 real click", "return _G.mtb_z.click_recruit('dwf')", "p5_recruit_clicked", 1)
    s.q("5 queue", "local Z=_G.mtb_z; return Z.queue() .. ' | ' .. Z.units()")
    s.q("5 by context command", "return _G.mtb_z.recruit_by_cco('wh_main_dwf_inf_miners_0')")
    time.sleep(1)
    s.q("5 queue after", "local Z=_G.mtb_z; return Z.queue() .. ' | ' .. Z.units()")
    s.q("5 close", "return _G.mtb_z.open_recruit()")
    # the lock
    s.q("5 other lord", "return _G.mtb_z.other_lord()")
    time.sleep(3)
    s.q("5 lock on him", "local Z=_G.mtb_z; Z.select(); return 1")
    time.sleep(1.5)
    s.q("5 lock", "return _G.mtb_z.lock_recruit()", "p5_locked", 1)
    s.q("5 locked +1 s", "return _G.mtb_z.recruit_button()")
    s.q("5 to the other", "local Z=_G.mtb_z; return Z.select_other()")
    time.sleep(1.5)
    s.q("5 the other's button", "return _G.mtb_z.recruit_button()", "p5_other", 1)
    s.q("5 back to him", "local Z=_G.mtb_z; Z.select(); return 1")
    time.sleep(1.5)
    s.q("5 his button again", "return _G.mtb_z.recruit_button()")
    s.q("5 override on", "local Z=_G.mtb_z; return Z.ui_lock(true) .. ' ' .. Z.recruit_button()")
    s.q("5 override other", "local Z=_G.mtb_z; return Z.select_other()")
    time.sleep(1.5)
    s.q("5 override other's button", "return _G.mtb_z.recruit_button()", "p5_override_other", 1)
    s.q("5 override off", "local Z=_G.mtb_z; Z.select(); return Z.ui_lock(false)")


def opacity(s):
    s.q("6 open", "tww3_mtb_crew_ui.open(); return tostring(tww3_mtb_crew_ui.is_open())", "p6_before", 1.5)
    s.q("6 opacity", "return _G.mtb_z.opacity(60)", "p6_opacity_60", 1)
    s.q("6 opacity 0", "return _G.mtb_z.opacity(0)", "p6_opacity_0", 1)
    s.z("tww3_mtb_crew_ui.close(); return 1")


def after_battle(s):
    """A battle: is the tab back, is the watcher gone, does an order right after it work."""
    s.q("1 before the battle", "local Z=_G.mtb_z; Z.unwatch_tab(); Z.hide_tab(); return Z.tab_state()")
    s.fight("p_battle", ("left",))
    # right after the battle: Lua is new
    s.q("1 after the battle", "local Z=_G.mtb_z; return Z.tab_state() .. ' | watcher ' .. tostring(_G.mtb_tab_shown)")
    n = s.z("return tostring(_G.mtb_z.first_empty())")
    s.q("2 order right after a battle, nothing selected before", f"local Z=_G.mtb_z; Z.select(); local g=Z.gold(); local r=Z.order('mtb_guns_1', {n}, 'selected'); return r .. ' gold ' .. g .. ' -> ' .. Z.gold()")
    time.sleep(1.5)
    read = s.q("2 read", f"return _G.mtb_z.slot_read({n})")
    s.note("2 worked right after a battle", "item=true" in read)
    if "item=true" not in read:
        time.sleep(3)
        s.q("2 again after 3 s", f"local Z=_G.mtb_z; local r=Z.order('mtb_guns_1', {n}, 'selected'); return r")
        time.sleep(1.5)
        s.q("2 read again", f"return _G.mtb_z.slot_read({n})")
    # the army's upkeep and the granted men after a turn
    s.q("1 hide, then a load", "local Z=_G.mtb_z; Z.watch_tab(); return Z.hide_tab()")


def after_load(s):
    s.save_game("tww3_mtb_panel_probe.save")
    time.sleep(2)
    s.z("_G.mtb_before_load = true; return 1")
    for step in ("button_menu", "button_load"):
        s.log("menu", s.click(step))
        time.sleep(2)
    s.log("pick", s.plain("local list = mtb.find('savegames', true); local box = find_uicomponent(list, 'list_box') or list; UIComponent(box:Find(0)):SimulateLClick(); return box:ChildCount()", 8)["result"])
    time.sleep(1.5)
    s.log(s.click("button_confirm_load"))
    end = time.time() + 200
    while time.time() < end:
        time.sleep(4)
        row = rc.send("return mtb and mtb.mode .. ' ' .. tostring(_G.mtb_before_load) .. ' ' .. tostring(tww3_mtb_crew and tww3_mtb_crew.status)", 5)
        if row.get("ok") and "campaign nil" in str(row.get("result")) and "applied" in str(row.get("result")):
            s.note("1 loaded", True)
            break
    time.sleep(6)
    s.script("dismiss_blockers.lua")
    s.q("1 after the load", "local Z=_G.mtb_z; Z.select(); return Z.tab_state()")
    time.sleep(1.5)
    s.q("1 after the load +1.5 s", "return _G.mtb_z.tab_state() .. ' | ' .. _G.mtb_z.siblings()", "p1_after_load")
    s.q("4 granted survive the load", "local Z=_G.mtb_z; return Z.units() .. ' ' .. Z.fleet()")
    s.q("3 reads after the load", "local Z=_G.mtb_z; return Z.reads('mtb_guns_1', Z.first_empty())")


def next_turn(s):
    s.q("4 before the turn", "local Z=_G.mtb_z; return Z.gold() .. ' ' .. Z.units() .. ' ' .. Z.first_unit_strength('wh_main_dwf_inf_dwarf_warrior_0')")
    s.prog("return P.peace()")
    s.safe_end_turn()
    s.prog("return P.peace()")
    s.q("4 after the turn", "local Z=_G.mtb_z; return Z.gold() .. ' ' .. Z.units() .. ' ' .. Z.first_unit_strength('wh_main_dwf_inf_dwarf_warrior_0') .. ' ' .. Z.fleet()")


def plan_b(s):
    s.z("_G.mtb_z.unwatch_tab(); return 1")
    s.q("7 before", "local Z=_G.mtb_z; Z.select(); return Z.state() .. ' | ' .. Z.tab_state()", "p7_before", 1)
    s.q("7 convert", "return _G.mtb_z.to_army()")
    time.sleep(3)
    s.q("7 after", "local Z=_G.mtb_z; Z.select(); return Z.state() .. ' | ' .. Z.tab_state()", "p7_army_map", 2)
    s.q("7 tab", "return _G.mtb_z.siblings()")
    s.q("7 barge item", "local c=_G.mtb_prog.malakai(); return tostring(c:has_ancillary('mtb_anc_mount_dwf_malakai_thunderbarge')) .. ' ' .. tostring(c:military_force():unit_list():item_at(0):unit_key())")
    s.prog("return P.peace()")
    s.safe_end_turn()
    s.prog("return P.peace()")
    s.q("7 next turn", "local Z=_G.mtb_z; return Z.state() .. ' | ' .. Z.tab_state()", "p7_next_turn", 1)
    s.q("7 wound", "return _G.mtb_z.wound(2)")
    time.sleep(2)
    s.q("7 wounded", "return _G.mtb_z.state()", "p7_wounded", 1)
    s.safe_end_turn()
    s.prog("return P.peace()")
    s.q("7 a turn later", "return _G.mtb_z.state()")
    s.safe_end_turn()
    s.prog("return P.peace()")
    s.q("7 two turns later", "local Z=_G.mtb_z; Z.select(); return Z.state() .. ' | ' .. Z.tab_state()", "p7_back", 1.5)


STAGES = [("tab", tab), ("order", order), ("reads", reads), ("turn", lambda s: (s.prog("return P.peace()"), s.safe_end_turn(), s.prog("return P.peace()"))), ("units", units), ("recruit", recruit), ("opacity", opacity),
          ("after_battle", after_battle), ("after_load", after_load), ("next_turn", next_turn), ("plan_b", plan_b)]


def main():
    s = Probe("panel_probe", time.time() + 1700)
    s.dir = Path(rc.state()["run"])
    s.current = {g: v["start"] for g, v in cc.OPTIONS["groups"].items()}
    s.fails, s.results = [], {}
    only = sys.argv[1:]
    for name, step in STAGES:
        if only and name not in only:
            continue
        s.log("=== stage", name)
        try:
            step(s)
        except Exception as e:
            s.log("STAGE FAILED", name, type(e).__name__, str(e)[:300])
            s.fails.append(name)
            try:
                s.shot("failed_" + name)
            except Exception:
                pass
        healthy = s.z("return tostring(_G.mtb_z.healthy())")
        s.note("health after " + name, healthy)
        if healthy != "true":
            s.log("BINDINGS BROKEN, stopping")
            break
    s.log("fails", s.fails)
    (cc.OUT / "CONTINUE").write_text("go")


if __name__ == "__main__":
    main()
