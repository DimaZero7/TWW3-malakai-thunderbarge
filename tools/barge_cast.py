"""In a running battle: flies the lord's barge to the nearest enemy and casts one ability, reading the game's own ability state.
py -3.14 tools/barge_cast.py NAME ABILITY [--range 55] [--self] [--ground] [--watch 25]
Writes build/barge_checks/NAME.txt; pictures go to the run's folder."""
import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import barge  # noqa: E402
import capture  # noqa: E402
import rc  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("name")
ap.add_argument("ability")
ap.add_argument("--range", type=float, default=55)
ap.add_argument("--self", action="store_true", dest="on_self")
ap.add_argument("--watch", type=float, default=25)
ap.add_argument("--speed", type=float, default=1)
a = ap.parse_args()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
out = barge.REPO / "build" / "barge_checks" / f"{a.name}.txt"
out.parent.mkdir(parents=True, exist_ok=True)
log = out.open("w", encoding="utf-8")


def say(*x):
    text = time.strftime("%H:%M:%S ") + " ".join(str(v) for v in x)
    print(text[:400], flush=True)
    log.write(text + "\n")
    log.flush()


def lua(code, wait=8):
    return barge.run(code, wait)["result"]


def shot(name):
    s = rc.state()
    hwnd = capture.find_window(s["pid"])
    if hwnd:
        capture.save_shot(hwnd, Path(s["run"]) / f"{a.name}_{name}.png", (s["x_res"], s["y_res"]))


KEY = a.ability
SETUP = """
local u, army, al = B.unit()
if not _G.mtb_uc then
  local uc = army:create_unit_controller()
  uc:add_units(u)
  uc:take_control()
  _G.mtb_uc = uc
end
"""
READ = 'local e, d = B.nearest(u, al); return string.format("near=%%d %%s | enemy_men=%%d | hp=%%s/%%s kills=%%s | %%s", d or -1, e and e:type() or "-", B.men(3 - al), tostring(B.cco(u,"HealthValue")), tostring(B.cco(u,"HealthMax")), tostring(B.cco(u,"NumKills")), B.ability(u, "%s"))' % KEY
say("before", lua(SETUP + READ))
end = time.time() + 120
lua("bm:modify_battle_speed(3); return 1")
while time.time() < end:
    r = lua(SETUP + 'local e, d = B.nearest(u, al); if not e then return "none" end; if d > %f then _G.mtb_uc:goto_location(e:position(), true) end; return math.floor(d)' % a.range)
    say("approach", r)
    if not str(r).isdigit() or int(r) <= a.range:
        break
    time.sleep(2)
lua("bm:modify_battle_speed(%f); return 1" % a.speed)
lua(SETUP + "_G.mtb_uc:halt(); return 1")
time.sleep(1)
lua(SETUP + "C.camera(-30, -30, 30, 15, 0, -10, 45); return 1")
time.sleep(1)
say("close", lua(SETUP + READ))
shot("0_before")
if a.on_self:
    r = barge.run(SETUP + 'local can = u:can_perform_special_ability("%s"); _G.mtb_uc:perform_special_ability("%s", u); return tostring(can)' % (KEY, KEY), 8)
else:
    r = barge.run(SETUP + 'local e = B.nearest(u, al); local can = u:can_perform_special_ability("%s"); _G.mtb_uc:perform_special_ability("%s", e); return tostring(can) .. " on " .. e:type()' % (KEY, KEY), 8)
say("cast", r["ok"], r["result"])
t0 = time.time()
n = 0
while time.time() - t0 < a.watch:
    say(f"t={time.time() - t0:.1f}", lua(SETUP + READ, 5))
    n += 1
    if n in (2, 4, 6, 8, 12, 16):
        shot(f"t{n}")
    time.sleep(0.8)
say("after", lua(SETUP + READ))
shot("9_after")
say("units\n" + str(lua("return B.units()")))
log.close()
