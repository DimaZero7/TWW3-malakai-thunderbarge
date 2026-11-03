"""Barge strength checks in a new Malakai campaign, nothing invincible.

  py -3.14 tools/barge_hp.py die NAME --crew stock|empty    the barge flies into archers until it dies; hit points each 2 s, then the lord's wound
  py -3.14 tools/barge_hp.py auto NAME --trials 3           autoresolve against the same army, empty and stock crew in turn; balance and losses

Writes build/barge_checks/NAME.txt. Hard limit per launch; the game is closed in every case.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import barge  # noqa: E402
import crew_cycle  # noqa: E402
import crew_session  # noqa: E402
import rc  # noqa: E402
import run_game as rg  # noqa: E402

OUT = barge.REPO / "build" / "barge_checks"
TESTS = barge.TESTS
GROUPS = ("rifles", "cannons", "cupolas", "bombs", "deck")
ARCHERS = ",".join(["wh_main_grn_inf_night_goblin_archers"] * 8 + ["wh_main_grn_inf_goblin_archers"] * 8)
ARMY = ",".join(["wh_main_grn_inf_black_orcs"] * 3 + ["wh_main_grn_inf_orc_big_uns"] * 3 + ["wh_main_grn_mon_giant"] + ["wh_main_grn_art_doom_diver_catapult"])
FORCE = """
local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local out = {wounded = c:is_wounded(), force = c:has_military_force()}
if c:has_military_force() then
  local ul = c:military_force():unit_list()
  local parts = {}
  local total = 0
  for i = 0, ul:num_items() - 1 do
    local u = ul:item_at(i)
    local p = u:percentage_proportion_of_full_strength()
    total = total + p
    parts[#parts + 1] = u:unit_key() .. "=" .. string.format("%.1f", p)
  end
  out.units, out.mean = table.concat(parts, " "), string.format("%.1f", total / math.max(1, ul:num_items()))
end
return out
"""
ENEMY_CQI = """
local f = cm:get_faction("wh_main_grn_greenskins")
local mfl, best = f:military_force_list(), nil
for i = 0, mfl:num_items() - 1 do
  local q = mfl:item_at(i):command_queue_index()
  if mfl:item_at(i):unit_list():num_items() >= 6 and (not best or q > best) then best = q end
end
_G.mtb_target_cqi = best
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["die", "auto"])
    ap.add_argument("name")
    ap.add_argument("--crew", default="stock")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--limit", type=int, default=800)
    ap.add_argument("--alone", action="store_true", help="die: the barge is the only unit of the army")
    ap.add_argument("--order", help="auto: crews of the trials, comma list")
    ap.add_argument("--burn", action="store_true", help="die: the barge also runs its Thunderburner, which damages itself")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)
    log = (OUT / f"{a.name}.txt").open("w", encoding="utf-8")

    def say(*x):
        text = time.strftime("%H:%M:%S ") + " ".join(str(v) for v in x)
        print(text[:400], flush=True)
        log.write(text + "\n")
        log.flush()

    busy = crew_session.busy_without_docker()
    if busy:
        raise SystemExit(f"busy: {busy}")
    s = crew_cycle.Session(a.name, time.time() + a.limit)
    s.current = {}
    cmd = [sys.executable, str(barge.REPO / "tools" / "crew_session.py"), "--label", "bc_" + a.name, "--timeout", str(a.limit + 60), "--packs", "harness", "campaign", "--user-mods", "memreader_plus.pack"]
    session_log = (OUT / f"session_{a.name}.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=session_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    ok = False

    def crew(option):
        code = "".join(f'assert(tww3_mtb_crew.set("{g}", "{option}"))\n' for g in GROUPS)
        say("crew", option, s.plain(code + "return tostring(tww3_mtb_crew.status)")["result"])

    def spawn(units):
        code = f'mtb_units = "{units}"\n' + (TESTS / "spawn_fight.lua").read_text(encoding="utf-8")
        say("spawn", s.plain(code)["result"])
        s.open_panel()

    try:
        end = time.time() + 60
        while not rg.STATE.exists():
            if proc.poll() is not None or time.time() > end:
                raise RuntimeError("the session did not start")
            time.sleep(1)
        s.dir = Path(rc.state()["run"])
        say("run", s.dir)
        s.wait_mode("frontend", 240)
        time.sleep(10)
        s.plain('frontend.start_campaign("wh3_main_combi", "wh3_main_combi", "wh3_dlc25_dwf_malakai"); return 1')
        s.wait_mode("campaign", 420)
        for _ in range(90):
            if "hud_campaign" in str(s.script("status.lua")["result"]):
                break
            time.sleep(3)
        for _ in range(6):
            s.script("dismiss_blockers.lua")
            time.sleep(1)
        if a.what == "auto":
            order = a.order.split(",") if a.order else ["empty", "stock"] * a.trials
            for n, option in enumerate(order):
                label = f"{option}{n // 2 + 1}"
                say("=== trial", label)
                crew(option)
                healed = s.plain('local f = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader():military_force(); local ok, e = pcall(function() cm:heal_military_force(f) end); return tostring(ok) .. " " .. tostring(e)')
                say("heal", healed["result"])
                say("before", s.plain(FORCE)["result"])
                spawn(ARMY)
                balance = ENEMY_CQI + (TESTS / "barge_balance.lua").read_text(encoding="utf-8")
                say("balance", s.plain(balance)["result"])
                other = "empty" if option == "stock" else "stock"
                crew(other)     # the same moment, the same armies, the other crew
                say("balance, other crew", s.plain(balance)["result"])
                crew(option)
                s.shot(f"{label}_panel")
                s.click("button_autoresolve")
                time.sleep(4)
                s.shot(f"{label}_result")
                say("back on map", s.back_on_map())
                after = s.plain(FORCE)["result"]
                say("after", after)
                if "force=false" in str(after):
                    say("the army is gone, the trials end here")
                    break
                s.plain("_G.mtb_target_cqi = nil; return 1")
                time.sleep(2)
        else:
            crew(a.crew)
            if a.alone:     # the archers have nothing else to shoot at
                code = 'mtb_remove = "^wh"' + chr(10) + (TESTS / "barge_setup.lua").read_text(encoding="utf-8")
                say("alone", s.plain(code, 15)["result"])
                time.sleep(3)
            spawn(ARCHERS)
            s.shot("panel")
            s.click("button_attack")
            s.wait_mode("battle", 300)
            time.sleep(4)
            say("deploy\n" + str(barge.run("return B.units()", 15)["result"]))
            s.plain("bm:end_current_battle_phase(); bm:modify_battle_speed(3); return 1")
            time.sleep(2)
            setup = """
local u, army, al = B.unit()
if not _G.mtb_uc then
  local uc = army:create_unit_controller()
  uc:add_units(u)
  uc:take_control()
  uc:fire_at_will(true)
  _G.mtb_uc = uc
end
"""
            if a.burn:
                say("burn", barge.run(setup + 'local can = u:can_perform_special_ability("wh3_dlc25_unit_abilities_thunderburner"); _G.mtb_uc:perform_special_ability("wh3_dlc25_unit_abilities_thunderburner", u); return tostring(can) .. " " .. B.ability(u, "wh3_dlc25_unit_abilities_thunderburner")', 8)["result"])
            started = time.time()
            read = """
local e, d = B.nearest(u, al)
if e and d > 40 then _G.mtb_uc:goto_location(e:position(), true) end
return string.format("near=%d men=%d/%d hp=%s/%s kills=%s enemy_men=%d commander=%s visible=%s", d or -1, u:number_of_men_alive(), u:initial_number_of_men(), tostring(B.cco(u, "HealthValue")), tostring(B.cco(u, "HealthMax")), tostring(B.cco(u, "NumKills")), B.men(3 - al), tostring(army:is_commander_alive()), tostring(u:is_valid_target()))
"""
            shots = 0
            dead = False
            while time.time() - started < 240:
                r = barge.run(setup + read, 6)
                say(f"t={time.time() - started:.0f}", r["result"])
                text = str(r["result"])
                if " men=0/" in text or "hp=0/" in text or "commander=false" in text or "a nil value" in text:   # a dead barge leaves the unit list
                    if not dead:
                        s.shot("death")
                    dead = True
                    say("dead")
                    time.sleep(3)
                    s.shot("after_death")
                    break
                if shots < 3 and time.time() - started > 15 * (shots + 1):
                    shots += 1
                    barge.run("C.camera(-45, -35, 35, 15, 0, 0, 50); return 1", 6)
                    s.shot(f"fight{shots}")
                time.sleep(2)
            say("units\n" + str(barge.run("return B.units()", 8)["result"]))
            say("dead", dead)
            for attempt in range(15):     # with nothing left the game ends the battle itself
                if s.visible("button_dismiss_results") != "-":
                    say("the battle ended by itself")
                    break
                time.sleep(3)
            else:
                say("kill enemy", s.script("battle_kill_enemy.lua")["result"])
                for attempt in range(25):
                    if s.visible("button_dismiss_results") != "-":
                        break
                    if attempt == 8:
                        s.plain("bm:end_battle(); return 1", 5)
                    time.sleep(3)
            s.shot("results")
            say(s.click("button_dismiss_results"))
            s.wait_mode("campaign", 300)
            time.sleep(4)
            say("back on map", s.back_on_map())
            say("wound", s.script("wound_state.lua")["result"])
            s.shot("map_after")
            say("panels", s.script("status.lua")["result"])
        ok = True
    except Exception as e:  # the game must be closed in every case
        say("ERROR", type(e).__name__, e)
    finally:
        rg.STOP.write_text("stop")
        try:
            proc.wait(180)
        except subprocess.TimeoutExpired:
            say("session did not end in 180 s")
        session_log.close()
        say("closed", ok)
        log.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
