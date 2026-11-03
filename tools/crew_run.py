"""One crew experiment in the real game: the same unit, a different set of seats in each battle of one session.

  py -3.14 tools/crew_run.py e1 [--high] [--limit 900]

Uses tools/run_game.py (its checks, lock, restore and closing of the game) with memreader Plus from the Workshop folder.
Pictures only through PrintWindow. Results in the run folder under build/campaign/runs: men_*.txt, seats_*.txt, *.png, log.txt.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import capture  # noqa: E402
import crew_lua  # noqa: E402
import rc  # noqa: E402
import run_game as rg  # noqa: E402

SPEC = json.loads((REPO / "data" / "crew_scenarios.json").read_text(encoding="utf-8"))
SAVE = "tww3_mtb_malakai_t1.save"
TESTS = REPO / "tools" / "tests"


def suffix(ap):
    name = ap.removeprefix("ap_")
    if name.startswith("cupola") or name in ("fireman", "lookout"):
        return "crew_" + name
    if name == "crew_barrel":
        return "pub_barrel"
    return name


def seat_map(seats):
    out = {}
    for group, key in seats.items():
        for ap in SPEC["groups"].get(group, [group]):
            out[ap] = key.replace("{suffix}", suffix(ap)).replace("{seat}", ap.removeprefix("ap_"))
    return out


class Run:
    def __init__(self, deadline):
        self.deadline = deadline
        self.dir = None

    def log(self, *a):
        text = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(text, flush=True)
        if self.dir:
            with (self.dir / "log.txt").open("a", encoding="utf-8") as f:
                f.write(text + "\n")

    def check_time(self):
        if time.time() > self.deadline:
            raise TimeoutError("time limit of the experiment")

    def lua(self, code, wait=15):
        self.check_time()
        return crew_lua.run(code, wait)

    def plain(self, code, wait=15):
        self.check_time()
        return rc.send(code, wait)

    def wait_mode(self, mode, limit=300):
        end = time.time() + limit
        while time.time() < end:
            self.check_time()
            row = rc.send("return mtb.mode", 3)
            if row["ok"] and row["result"] == mode:
                return True
            time.sleep(2)
        raise TimeoutError(f"mode {mode} not reached in {limit} s")

    def shot(self, name):
        s = rc.state()
        hwnd = capture.find_window(s["pid"])
        if not hwnd:
            self.log("shot", name, "no window")
            return
        black = capture.save_shot(hwnd, self.dir / f"{name}.png", (s["x_res"], s["y_res"]))
        self.log("shot", name, "black" if black else "ok")

    def script(self, name, **values):
        code = "".join(f'{k} = "{v}"\n' for k, v in values.items()) + (TESTS / name).read_text(encoding="utf-8")
        return self.plain(code)

    def visible(self, name):
        row = self.plain(f'local b = mtb.find("{name}", true); return b and tostring(b:CurrentState()) or "-"', 5)
        return row["result"] if row["ok"] else "-"

    def click(self, name):
        return self.plain(f'return mtb.click("{name}")', 5)["result"]

    def wait_button(self, name, limit=60):
        end = time.time() + limit
        while time.time() < end:
            state = self.visible(name)
            if state != "-":
                return state
            time.sleep(1)
        raise TimeoutError(f"button {name} did not appear in {limit} s")

    def open_battle_panel(self):
        """Notices can stop the attack order, so it is repeated with them closed until the pre-battle panel opens."""
        time.sleep(3)
        for attempt in range(8):
            if self.visible("button_attack") != "-":
                return
            self.log("blockers", self.script("dismiss_blockers.lua")["result"])
            self.log("attack", self.script("attack_nearest.lua")["result"])
            for _ in range(8):
                time.sleep(1)
                if self.visible("button_attack") != "-":
                    return
        self.shot("no_panel")
        raise TimeoutError("the pre-battle panel did not open")

    def camera_shots(self, cameras, prefix):
        for cam in cameras:
            self.lua(f'return C.camera({cam["f"]},{cam["r"]},{cam["u"]},{cam["tf"]},{cam["tr"]},{cam["tu"]},{cam["fov"]})', 10)
            time.sleep(2.0)
            self.shot(f'{prefix}_{cam["name"]}')

    def battle(self, b):
        label = b["label"]
        self.log("=== battle", label)
        seats = seat_map(b["seats"]) if b.get("seats") else {}
        code = "local m = {}\n" + "".join(f'm["{k}"] = "{v}"\n' for k, v in seats.items())
        row = self.lua(code + 'local done = C.apply(m); return #done .. "\\n" .. C.list()')
        (self.dir / f"seats_{label}.txt").write_text(str(row["result"]), encoding="utf-8")
        self.log("apply", row["ok"], str(row["result"])[:60])
        if not row["ok"]:
            raise RuntimeError(row["result"])
        self.log("spawn", self.script("spawn_fight.lua")["result"])
        self.open_battle_panel()
        self.shot(f"{label}_prebattle")
        time.sleep(1)
        self.log(self.click("button_attack"))
        self.wait_mode("battle", 300)
        time.sleep(4)
        row = self.lua("return C.men()", 20)
        (self.dir / f"men_{label}_deploy.txt").write_text(str(row["result"]), encoding="utf-8")
        self.log("men", row["ok"], str(row["result"])[:80])
        row = self.lua("return C.vectors()", 20)
        (self.dir / f"vectors_{label}.txt").write_text(str(row["result"]), encoding="utf-8")
        self.camera_shots(SPEC["cameras"], label)
        self.log(self.plain("bm:end_current_battle_phase(); return 'phase ended'", 5)["result"])
        fight = b.get("fight", 8)
        time.sleep(3)
        self.log(self.lua((TESTS / "crew_fight.lua").read_text(encoding="utf-8"), 10)["result"])
        end = time.time() + fight
        n = 0
        stats = []
        while time.time() < end:
            time.sleep(10)
            n += 1
            r = self.lua("return C.stats()", 8)
            stats.append(str(r["result"]))
            self.log("stats", r["result"])
            if n == 2:
                self.camera_shots([c for c in SPEC["cameras"] if c["name"] in ("left","right")], f"{label}_fight")
        (self.dir / f"stats_{label}.txt").write_text("\n".join(stats), encoding="utf-8")
        row = self.lua("return C.men()", 20)
        (self.dir / f"men_{label}_fight.txt").write_text(str(row["result"]), encoding="utf-8")
        self.log(self.script("battle_kill_enemy.lua")["result"])
        for attempt in range(20):
            if self.visible("button_dismiss_results") != "-":
                break
            if attempt == 6:
                self.plain("bm:end_battle(); return 1", 5)
            time.sleep(3)
        self.shot(f"{label}_result")
        self.log(self.click("button_dismiss_results"))
        self.wait_mode("campaign", 300)
        time.sleep(5)
        self.shot(f"{label}_back")
        for attempt in range(15):
            if self.visible("button_end_turn") != "-":
                break
            for name in ("button_captive_option_kill", "button_dismiss", "button_accept"):
                if self.visible(name) != "-":
                    self.log(self.click(name))
                    break
            time.sleep(2)
        self.log("panel", self.script("panel.lua")["result"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario")
    ap.add_argument("--high", action="store_true")
    ap.add_argument("--limit", type=int, default=1200)
    args = ap.parse_args()
    started = time.time()
    run = Run(started + args.limit)
    cmd = [sys.executable, str(REPO / "tools" / "crew_session.py"), "--label", "crew_" + args.scenario, "--timeout", str(args.limit + 120),
           "--packs", "harness", "campaign", "--user-mods", "memreader_plus.pack", "--save", SAVE,
           "--args", f"game_startup_mode campaign_load {SAVE}"]
    if args.high:
        cmd.append("--high-graphics")
    if rg.STATE.exists():
        raise SystemExit("a session is running")
    log = (REPO / "build" / "campaign" / f"crew_{args.scenario}.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    result = "failed"
    try:
        end = time.time() + 60
        while not rg.STATE.exists():
            if proc.poll() is not None or time.time() > end:
                raise RuntimeError("the session did not start, see build/campaign/crew_*.log")
            time.sleep(1)
        run.dir = Path(rc.state()["run"])
        run.log("run", run.dir)
        run.wait_mode("campaign", 300)
        time.sleep(8)
        run.shot("map")
        row = run.lua("return C.list()", 20)
        (run.dir / "seats_pristine.txt").write_text(str(row["result"]), encoding="utf-8")
        run.log("list", row["ok"], str(row["result"])[:200])
        if not row["ok"]:
            raise RuntimeError(row["result"])
        run.log("blockers", run.script("dismiss_blockers.lua")["result"])
        for battle in SPEC["scenarios"][args.scenario]["battles"]:
            run.battle(battle)
        result = "done"
    except Exception as e:  # the game must be closed in every case
        run.log("ERROR", type(e).__name__, e)
    finally:
        rg.STOP.write_text("stop")
        try:
            proc.wait(180)
        except subprocess.TimeoutExpired:
            run.log("session did not end in 180 s")
        run.log("result", result, "seconds", round(time.time() - started))
    return 0 if result == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
