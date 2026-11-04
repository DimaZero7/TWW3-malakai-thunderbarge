"""Talks to the running test session (tools/run_game.py).

  py -3.14 tools/rc.py "return mtb.mode"              runs Lua in the game, prints the result
  py -3.14 tools/rc.py --file script.lua              same, from a file
  py -3.14 tools/rc.py --shot name                    picture of the game window only (PrintWindow) into the run folder
  py -3.14 tools/rc.py --events [N]                   the last N lines of the probe's log
  py -3.14 tools/rc.py --state                        session state, window size
  py -3.14 tools/rc.py --stop                         end the session (the game is closed, the user's files restored)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import capture  # noqa: E402
import run_game as rg  # noqa: E402

GAME = rg.rb.GAME
CMD, RC = GAME / "tww3_mtb_cmd.lua", GAME / "tww3_mtb_rc.jsonl"
COUNTER = rg.CAMPAIGN / "rc_counter.txt"


def state():
    if not rg.STATE.exists():
        raise SystemExit("no session is running")
    return json.loads(rg.STATE.read_text(encoding="utf-8"))


def send(code, wait):
    state()
    n = int(COUNTER.read_text()) + 1 if COUNTER.exists() else 1
    COUNTER.write_text(str(n))
    temp = CMD.with_name(f"{CMD.stem}.{os.getpid()}.tmp")    # a session's own steps may be sending at the same moment
    temp.write_text(f"--id {n}\n{code}\n", encoding="utf-8")
    for attempt in range(40):       # the game may have the file open for its poll at this moment
        try:
            temp.replace(CMD)
            break
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.1)
    end = time.time() + wait
    while time.time() < end:
        if RC.exists():
            for line in RC.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("id") == n:
                    return row
        time.sleep(0.1)
    return {"id": n, "ok": None, "result": f"no answer in {wait} s (game busy or loading)"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("code", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--shot")
    ap.add_argument("--events", nargs="?", const=20, type=int)
    ap.add_argument("--state", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--wait", type=float, default=15)
    args = ap.parse_args()
    if args.stop:
        rg.STOP.write_text("stop")
        print("stop asked")
    elif args.state:
        print(state())
    elif args.shot:
        s = state()
        capture.unminimize_behind(s["pid"])
        hwnd = capture.find_window(s["pid"])
        if not hwnd:
            raise SystemExit("no window")
        path = Path(s["run"]) / f"{args.shot}.png"
        print(path, "black", capture.save_shot(hwnd, path, (s.get("x_res", rg.SETTINGS["x_res"]), s.get("y_res", rg.SETTINGS["y_res"]))))
    elif args.events is not None:
        path = GAME / "tww3_mtb_events.jsonl"
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
        print("\n".join(lines[-args.events:]))
    else:
        code = Path(args.file).read_text(encoding="utf-8") if args.file else args.code
        row = send(code, args.wait)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(("OK" if row["ok"] else "FAIL" if row["ok"] is False else "NOANSWER"), row.get("mode", ""))
        print(row["result"])


if __name__ == "__main__":
    main()
