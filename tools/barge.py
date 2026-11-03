"""Lua in the running session with crew_lib.lua and barge_lib.lua first: py -3.14 tools/barge.py [--wait 15] "return B.units()" | file.lua"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import rc  # noqa: E402

TESTS = REPO / "tools" / "tests"
PREFIX = (TESTS / "crew_lib.lua").read_text(encoding="utf-8") + "\n" + (TESTS / "barge_lib.lua").read_text(encoding="utf-8") + "\nlocal C, B = _G.mtb_crew, _G.mtb_barge\n"


def run(code, wait=15):
    return rc.send(PREFIX + code, wait)


if __name__ == "__main__":
    args = sys.argv[1:]
    wait = 15
    if args and args[0] == "--wait":
        wait, args = float(args[1]), args[2:]
    code = args[0]
    if code.endswith(".lua"):
        code = Path(code).read_text(encoding="utf-8")
    row = run(code, wait)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("OK" if row["ok"] else "FAIL" if row["ok"] is False else "NOANSWER", row.get("mode", ""))
    print(row["result"])
