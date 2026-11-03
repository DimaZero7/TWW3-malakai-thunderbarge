"""Waits for the shared game, then runs one crew experiment: py -3.14 tools/crew_queue.py e1 [--wait 40] [--high] [--limit 900]

Busy means Warhammer3.exe, probe_game.lock, HUMAN_PLAYING, gpu-train.lock (see tools/crew_session.py). Checks every 75 s.
"""
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import crew_session  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    args = sys.argv[1:]
    wait = 40.0
    if "--wait" in args:
        i = args.index("--wait")
        wait = float(args[i + 1])
        del args[i:i + 2]
    end = time.time() + wait * 60
    while True:
        busy = crew_session.busy_without_docker()
        if not busy:
            break
        if time.time() > end:
            print("still busy after the wait:", busy)
            return 3
        print(time.strftime("%H:%M:%S"), "busy:", busy, flush=True)
        time.sleep(75)
    return subprocess.run([sys.executable, str(REPO / "tools" / "crew_run.py")] + args, stdin=subprocess.DEVNULL).returncode


if __name__ == "__main__":
    sys.exit(main())
