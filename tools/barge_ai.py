"""One battle against Malakai under the game's AI, every unit tracked. The player's units stand still, then advance.
py -3.14 tools/barge_ai.py NAME [--no-mod] [--setup FILE.lua] [--passive 90] [--advance 150] [--crew stock|empty] [--limit 900]
Writes build/barge_checks/ai_NAME.txt (a table of every unit each 10 s). Hard limit for the whole launch; the game is closed in every case.
Summary: py -3.14 tools/barge_ai.py NAME --report
"""
import argparse
import math
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import barge  # noqa: E402
import capture  # noqa: E402
import crew_session  # noqa: E402
import rc  # noqa: E402
import run_game as rg  # noqa: E402

TESTS = barge.TESTS
OUT = barge.REPO / "build" / "barge_checks"
ROW = re.compile(r"(\d) (\S+) x=(-?\d+) y=(-?\d+) z=(-?\d+) men=(\d+)/(\d+) hp=(\S+)/(\S+) ai=(\S+) fly=(\S+) melee=(\S+) kills=(\S+) ammo=(\S+)")
ADVANCE = """
local alliances = bm:alliances()
local mine
for k = 1, alliances:count() do
  local armies = alliances:item(k):armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      if B.cco(us:item(j), "IsUnderAIControl") == false then mine = k end
    end
  end
end
local target
local eu = alliances:item(3 - mine):armies():item(1):units()
for j = 1, eu:count() do if eu:item(j):is_commanding_unit() then target = eu:item(j) end end
local armies = alliances:item(mine):armies()
local n = 0
for i = 1, armies:count() do
  local army = armies:item(i)
  local uc = army:create_unit_controller()
  local us = army:units()
  for j = 1, us:count() do uc:add_units(us:item(j)); n = n + 1 end
  uc:take_control()
  uc:goto_location(target:position(), true)
  _G["mtb_player_uc" .. i] = uc
end
return n .. " units of alliance " .. mine .. " sent to " .. target:type()
"""


def report(name):
    """Per unit and phase: how far it got from where the phase began, its men, health, kills."""
    seq = {"passive": {}, "advance": {}}
    phase = None
    for line in (OUT / f"ai_{name}.txt").read_text(encoding="utf-8").splitlines():
        m = re.search(r"t=\d+ (passive|advance)", line)
        if m:
            phase = m.group(1)
            continue
        if re.match(r"\d\d:\d\d:\d\d", line):
            phase = None
            continue
        m = ROW.match(line)
        if m and phase:
            seq[phase].setdefault((m.group(1), m.group(2)), []).append(m.groups())
    keys = sorted({k for p in seq.values() for k in p})
    for k in keys:
        parts = []
        for ph in ("passive", "advance"):
            s = seq[ph].get(k)
            if s:
                a, b = s[0], s[-1]
                d = math.hypot(int(b[2]) - int(a[2]), int(b[4]) - int(a[4]))
                parts.append(f"{ph} {d:.0f} m, men {b[5]}/{b[6]}, hp {b[7]}/{b[8]}, kills {b[12]}, ammo {b[13][:5]}")
        print(k[0], k[1], " | ".join(parts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--no-mod", action="store_true")
    ap.add_argument("--setup")
    ap.add_argument("--passive", type=int, default=90)
    ap.add_argument("--advance", type=int, default=150)
    ap.add_argument("--crew", default="stock")
    ap.add_argument("--limit", type=int, default=900)
    ap.add_argument("--high", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.report:
        report(a.name)
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    log = (OUT / f"ai_{a.name}.txt").open("w", encoding="utf-8")

    def say(*x):
        text = time.strftime("%H:%M:%S ") + " ".join(str(v) for v in x)
        print(text[:300], flush=True)
        log.write(text + "\n")
        log.flush()

    def plain(code, wait=10):
        return rc.send(code, wait)

    def script(name):
        return plain((TESTS / name).read_text(encoding="utf-8"))["result"]

    def wait_mode(m, limit):
        end = time.time() + limit
        while time.time() < end:
            r = rc.send("return mtb.mode", 3)
            if r["ok"] and r["result"] == m:
                return
            time.sleep(2)
        raise TimeoutError(f"mode {m}")

    def shot(name):
        s = rc.state()
        hwnd = capture.find_window(s["pid"])
        if hwnd:
            capture.save_shot(hwnd, Path(s["run"]) / f"ai_{a.name}_{name}.png", (s["x_res"], s["y_res"]))

    busy = crew_session.busy_without_docker()
    if busy:
        raise SystemExit(f"busy: {busy}")
    packs = ["harness"] if a.no_mod else ["harness", "campaign"]
    cmd = [sys.executable, str(barge.REPO / "tools" / "crew_session.py"), "--label", "bc_ai_" + a.name, "--timeout", str(a.limit), "--packs", *packs, "--user-mods", "memreader_plus.pack"]
    if a.high:
        cmd.append("--high-graphics")
    session_log = (OUT / f"session_ai_{a.name}.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=session_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    ok = False
    try:
        end = time.time() + 60
        while not rg.STATE.exists():
            if proc.poll() is not None or time.time() > end:
                raise RuntimeError("the session did not start")
            time.sleep(1)
        say("run", rc.state()["run"])
        wait_mode("frontend", 240)
        time.sleep(10)
        plain('frontend.start_campaign("wh3_main_combi", "wh3_main_combi", "wh_main_dwf_dwarfs"); return 1')
        wait_mode("campaign", 420)
        for _ in range(90):
            if "hud_campaign" in str(plain((TESTS / "status.lua").read_text(encoding="utf-8"), 5)["result"]):
                break
            time.sleep(3)
        for _ in range(6):
            script("dismiss_blockers.lua")
            time.sleep(1)
        if not a.no_mod:
            say("crew", plain('for _, g in ipairs({"rifles","cannons","cupolas","bombs","deck"}) do assert(tww3_mtb_crew.set(g, "%s")) end return tostring(tww3_mtb_crew.status)' % a.crew)["result"])
        if a.setup:
            say("setup", plain(Path(a.setup).read_text(encoding="utf-8"), 15)["result"])
            time.sleep(3)
        for _ in range(10):
            say("meet", script("crew_ai_meet.lua"))
            time.sleep(6)
            if plain('local b = mtb.find("button_attack", true); return b and "yes" or "no"', 5)["result"] == "yes":
                break
            script("dismiss_blockers.lua")
        else:
            raise TimeoutError("no panel")
        shot("panel")
        plain('return mtb.click("button_attack")')
        wait_mode("battle", 300)
        time.sleep(4)
        say("deploy\n" + str(barge.run("return B.units()", 15)["result"]))
        plain("bm:end_current_battle_phase(); bm:modify_battle_speed(3); return 1")
        started = time.time()

        def tick(label):
            r = barge.run("return B.units()", 8)["result"]
            say(f"t={time.time() - started:.0f} {label}\n{r}")

        while time.time() - started < a.passive:
            time.sleep(10)
            tick("passive")
        shot("passive")
        if a.advance:
            say("advance", barge.run(ADVANCE, 15)["result"])
            second = time.time()
            while time.time() - second < a.advance:
                time.sleep(10)
                tick("advance")
            shot("advance")
        barge.run("if C.lord_unit() then C.camera(-45, -35, 35, 15, 0, 0, 50) end return 1", 8)
        time.sleep(1.5)
        shot("wide")
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
