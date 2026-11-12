"""The second half of tools/tests/panel_probe.py in the same running game: the cancel, real recruitment with room in the army, opacity, what a battle and a load do, plan B."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import panel_probe as pp  # noqa: E402

cc, rc = pp.cc, pp.rc
Z = "local Z=_G.mtb_z; "


def toggle(s):
    s.q("2b state", Z + "return _G.mtb_prog.slots() .. ' | ' .. Z.gold() .. ' | ' .. Z.slot_read(0)")
    s.q("2b own way", Z + "Z.deselect(); return Z.order('airship_hull_2', 0, 'own')")
    time.sleep(1.5)
    s.q("2b read 1", Z + "return Z.gold() .. ' ' .. Z.slot_read(0)")
    s.q("2b same order again", Z + "return Z.order('airship_hull_2', 0, 'own')")
    time.sleep(1.5)
    s.q("2b read 2", Z + "return Z.gold() .. ' ' .. Z.slot_read(0)")
    s.q("2b order third time", Z + "return Z.order('airship_hull_2', 0, 'own')")
    time.sleep(1.5)
    s.q("2b read 3", Z + "return Z.gold() .. ' ' .. Z.slot_read(0)")
    s.prog("return P.peace()")
    s.safe_end_turn()
    s.prog("return P.peace()")
    s.q("2b next turn", Z + "return _G.mtb_prog.slots() .. ' | ' .. tostring(tww3_mtb_crew.get().rifles) .. ' | ' .. Z.state()")


def side(s):
    s.q("2c tab hidden, nobody selected, own way", Z + "Z.select(); Z.hide_tab(); Z.deselect(); local n=Z.first_empty(); _G.mtb_n=n; local g=Z.gold(); return n .. ' ' .. Z.order('crew_weapons_1', n, 'own') .. ' gold ' .. g")
    time.sleep(1.5)
    s.q("2c read", Z + "return Z.gold() .. ' ' .. Z.slot_read(_G.mtb_n)", "p2c_side_ordered", 0.5)
    s.q("3 reads with an active slot", Z + "Z.select(); return Z.reads('mtb_guns_1', Z.first_empty())")


def recruit(s):
    s.q("5b army tab", Z + "Z.select(); Z.F('tab_army'):SimulateLClick(); return Z.tab_state() .. ' | ' .. Z.recruit_button() .. ' | ' .. Z.where()", "p5b_army_tab", 1.5)
    s.q("5b make room", Z + "local c=_G.mtb_prog.malakai(); local look=cm:char_lookup_str(c); for i=1,6 do cm:remove_unit_from_character(look,'wh_main_dwf_inf_miners_0') end; return Z.units()")
    time.sleep(1)
    s.q("5b can", Z + "return 'miner0 ' .. Z.can('wh_main_dwf_inf_miners_0') .. ' miner1 ' .. Z.can('wh_main_dwf_inf_miners_1') .. ' warrior ' .. Z.can('wh_main_dwf_inf_dwarf_warrior_0') .. ' slayer ' .. Z.can('wh_main_dwf_inf_slayers') .. ' cannon ' .. Z.can('wh_main_dwf_art_cannon')")
    s.q("5b open", "return _G.mtb_z.open_recruit()", "p5b_recruit_open", 1.5)
    s.q("5b list", "return _G.mtb_z.recruit_list()")
    s.q("5b real click", "return _G.mtb_z.click_recruit('dwf')", "p5b_recruit_clicked", 1)
    s.q("5b queue", Z + "return Z.queue() .. ' | ' .. Z.units()")
    s.q("5b gold", Z + "return Z.gold()")
    s.q("5b by context command", "return _G.mtb_z.recruit_by_cco('wh_main_dwf_inf_miners_0')")
    time.sleep(1)
    s.q("5b gold after", Z + "return Z.gold() .. ' | ' .. Z.units()")
    s.q("5b close", "return _G.mtb_z.open_recruit()")
    s.q("5b lock", "return _G.mtb_z.lock_recruit()", "p5b_locked", 1)
    s.q("5b click while locked", Z + "return Z.open_recruit() .. ' | ' .. Z.recruit_list()")
    s.q("5b deselect, select", Z + "Z.deselect(); return 1")
    time.sleep(0.8)
    s.q("5b select", Z + "Z.select(); return 1")
    time.sleep(1.2)
    s.q("5b his button after reselect", "return _G.mtb_z.recruit_button()")
    s.prog("return P.peace()")
    before = s.z(Z + "return Z.gold() .. ' ' .. Z.units()")
    s.safe_end_turn()
    s.prog("return P.peace()")
    s.q("5b the queue a turn later", Z + "return 'before: " + before[:300].replace('"', "") + " | now ' .. Z.gold() .. ' ' .. Z.units()")


def opacity(s):
    s.q("6 open", "tww3_mtb_crew_ui.open(); return tostring(tww3_mtb_crew_ui.is_open())", "p6_before", 1.5)
    s.q("6 opacity 60", "return _G.mtb_z.opacity(60)", "p6_opacity_60", 1)
    s.q("6 opacity 0", "return _G.mtb_z.opacity(0)", "p6_opacity_0", 1)
    s.q("6 close", "tww3_mtb_crew_ui.close(); return tostring(tww3_mtb_crew_ui.is_open())")


STAGES = [("toggle", toggle), ("side", side), ("recruit", recruit), ("opacity", opacity), ("after_battle", pp.after_battle), ("after_load", pp.after_load), ("next_turn", pp.next_turn), ("plan_b", pp.plan_b)]


def main():
    s = pp.Probe("panel_probe", time.time() + 1500)
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
        healthy = s.z("return tostring(_G.mtb_z.healthy())")
        s.note("health after " + name, healthy)
        if healthy != "true":
            s.log("BINDINGS BROKEN, stopping")
            break
    s.log("fails", s.fails)
    (cc.OUT / "CONTINUE").write_text("go")


if __name__ == "__main__":
    main()
