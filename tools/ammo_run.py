"""One launch of the game for docs/design/separate-ammo.md: does a crew group run dry on its own while the others keep firing?

  py -3.14 tools/ammo_run.py [--limit 1200] [--step 35] [--save tww3_mtb_crew_a.save] [--igpu]

Runs through tools/run_game.py like tools/crew_cycle.py: waits for the game, the lock and HUMAN_PLAYING, closes the game after
every outcome, restores the user's files. One battle, the whole crew stock; the steps of tools/tests/ammo_probe.lua change the
two ammo pools and the pool byte of the weapon rows in memory. The result goes to report.txt in the run folder.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import capture  # noqa: E402
import crew_cycle as cc  # noqa: E402
import crew_session  # noqa: E402
import rc  # noqa: E402
import run_game as rg  # noqa: E402

PROBE = cc.TESTS / "ammo_probe.lua"
STEPS = ["base", "rifles_low", "guns_dry", "resume", "bombs_dry", "cupolas_dry", "primary_low", "refilled"]
SHOTS = {"base", "rifles_low", "primary_low"}
STOCK = {"rifles": "stock", "cannons": "stock", "cupolas": "stock", "bombs": "stock", "deck": "stock"}


def shot(s, name):
    """A picture must never stop the experiment. --set keeps the window size as text in the session state."""
    try:
        state = rc.state()
        hwnd = capture.find_window(state["pid"])
        capture.save_shot(hwnd, s.dir / f"{name}.png", (int(state["x_res"]), int(state["y_res"])))
    except Exception as e:
        s.log("picture failed", name, type(e).__name__, e)


def run_steps(s, step_seconds):
    report = s.dir / "report.txt"

    def note(*a):
        s.log(*a)
        with report.open("a", encoding="utf-8") as f:
            f.write(" ".join(str(x) for x in a) + "\n")

    def must(row):
        if not row["ok"]:
            raise RuntimeError(row["result"])
        return row["result"]

    s.current = dict(STOCK)
    s.choose(STOCK)
    s.log("blockers", s.script("dismiss_blockers.lua")["result"])
    s.log("spawn", s.script("spawn_fight.lua")["result"])
    s.open_panel()
    s.log(s.click("button_attack"))
    s.wait_mode("battle", 420)
    time.sleep(4)
    (s.dir / "men.txt").write_text(str(s.lua("return C.men()", 20)["result"]), encoding="utf-8")
    s.plain("bm:end_current_battle_phase(); return 1", 5)
    time.sleep(3)
    note("fight", s.lua((cc.TESTS / "crew_fight.lua").read_text(encoding="utf-8"), 15)["result"])
    must(s.lua(PROBE.read_text(encoding="utf-8"), 15))
    note("attach\n" + str(must(s.plain("return _G.mtb_ammo.attach()", 20))))
    note(s.plain("return _G.mtb_ammo.keep_enemy()", 15)["result"])

    # The barge flies in first: the steps count only when it is in range of the enemy.
    end = time.time() + 180
    near = None
    while time.time() < end:
        s.check_time()
        row = s.lua("C.order(); return C.stats()", 10)
        m = cc.re.search(r"near=(\d+)", str(row["result"]))
        near = int(m.group(1)) if m else None
        s.log("approach", str(row["result"])[:160])
        if near is not None and near <= 60:
            break
        time.sleep(4)
    note("near at the start", near)
    s.plain("bm:modify_battle_speed(1); return 1", 5)
    must(s.plain("return _G.mtb_ammo.start(100, 6)", 10))

    for name in STEPS:
        must(s.plain(f'return _G.mtb_ammo.phase("{name}")', 10))
        note("step", name, s.plain("return _G.mtb_ammo.ui()", 8)["result"])
        sim_start = s.sim_ms()
        real_end = time.time() + step_seconds * 5
        shot_done = False
        loops = 0
        while time.time() < real_end:
            s.check_time()
            time.sleep(4)
            loops += 1
            if loops % 3 == 0:
                s.lua("C.order(); return 1", 8)
            now = s.sim_ms()
            elapsed = (now - sim_start) / 1000 if now is not None and sim_start is not None else 0
            if name in SHOTS and not shot_done and elapsed > step_seconds * 0.7:
                shot(s, f"ui_{name}")
                shot_done = True
            if elapsed >= step_seconds:
                break
        note("end", name, s.plain("return _G.mtb_ammo.ui()", 8)["result"])
        report_text = must(s.plain("return _G.mtb_ammo.report()", 10))
        (s.dir / "table.txt").write_text(str(report_text), encoding="utf-8")
    note("table\n" + str(must(s.plain("return _G.mtb_ammo.report()", 10))))
    note(s.lua("return C.stats()", 8)["result"])
    note(s.plain("return _G.mtb_ammo.restore()", 8)["result"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1200)
    ap.add_argument("--step", type=int, default=35, help="battle seconds of each step")
    ap.add_argument("--save", default="tww3_mtb_crew_a.save")
    ap.add_argument("--igpu", action="store_true")
    ap.add_argument("--set", nargs="*", default=[])
    args = ap.parse_args()

    busy_end = time.time() + 3 * 3600
    while crew_session.busy_without_docker():
        if time.time() > busy_end:
            raise SystemExit("still busy")
        time.sleep(30)

    started = time.time()
    session = cc.Session("ammo", started + args.limit)
    cc.SCALE = 2.0 if args.igpu else 1.0     # waits only; the hard limit stays
    cmd = [sys.executable, str(REPO / "tools" / "crew_session.py"), "--label", "ammo", "--timeout", str(args.limit + 120),
           "--packs", "harness", "campaign", "--user-mods", "memreader_plus.pack",
           "--save", args.save, "--args", f"game_startup_mode campaign_load {args.save}"]
    if args.igpu:
        cmd.append("--igpu")
    if args.set:
        cmd += ["--set", *args.set]
    cc.OUT.mkdir(parents=True, exist_ok=True)
    log = (cc.OUT / "session_ammo.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    outcome = "failed"
    ours = False
    try:
        end = time.time() + 60
        # STATE may belong to another agent's session if the queue was lost in the last moment: only our own run counts.
        while not (rg.STATE.exists() and "-ammo" in rc.state()["run"]):
            if proc.poll() is not None or time.time() > end:
                raise RuntimeError("the session did not start, see " + str(cc.OUT / "session_ammo.log"))
            time.sleep(1)
        ours = True
        session.dir = Path(rc.state()["run"])
        session.log("run", session.dir)
        session.wait_mode("campaign", 420)
        time.sleep(8)
        session.last_step = True
        run_steps(session, args.step)
        outcome = "done"
    except Exception as e:  # the game must be closed in every case
        session.log("ERROR", type(e).__name__, e)
    finally:
        if ours:           # never stop a session of another agent
            rg.STOP.write_text("stop")
        try:
            proc.wait(180)
        except subprocess.TimeoutExpired:
            session.log("session did not end in 180 s")
        session.log("session", outcome, "seconds", round(time.time() - started))
    return 0 if outcome == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
