"""Ends N turns of the running test session, closing notices, and prints a state line after each.
py -3.14 tools/turns.py N [--state tools/tests/wound_state.lua] [--until-unwounded]
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tools" / "tests"


def lua(path, wait=10):
    r = subprocess.run([sys.executable, str(REPO / "tools" / "rc.py"), "--file", str(path), "--wait", str(wait)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int)
    ap.add_argument("--state", default=str(TESTS / "wound_state.lua"))
    ap.add_argument("--until-unwounded", action="store_true")
    ap.add_argument("--turn-timeout", type=int, default=240)
    args = ap.parse_args()
    for _ in range(args.n):
        before = re.search(r"turn=(\d+)", lua(TESTS / "status.lua"))
        start = int(before.group(1)) if before else -1
        lua(TESTS / "dismiss_blockers.lua")
        time.sleep(2)
        lua(TESTS / "end_turn.lua")
        t0 = time.time()
        text = ""
        while time.time() - t0 < args.turn_timeout:
            text = lua(TESTS / "status.lua", 5)
            m = re.search(r"turn=(\d+)", text)
            if m and int(m.group(1)) > start and "whose=wh3_dlc25_dwf_malakai" in text and "hud_campaign" in text:
                break
            if "no session" in text:
                print("session ended")
                return
            if "diplomacy_dropdown" in text or "events" in text or "appoint_new_general" in text:
                lua(TESTS / "dismiss_blockers.lua", 5)
            time.sleep(3)
        else:
            print("no new turn in", args.turn_timeout, "s:", text[:200], flush=True)
            return
        state = lua(args.state).splitlines()[-1]
        print(f"{int(time.time() - t0)} s", state[:300], flush=True)
        if args.until_unwounded and "wounded=false" in state:
            return


if __name__ == "__main__":
    main()
