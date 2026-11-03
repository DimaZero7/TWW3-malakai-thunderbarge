"""Runs Lua in the running session with the crew library first: py -3.14 tools/crew_lua.py [--wait 15] "return C.list()" """
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import rc  # noqa: E402

LIB = (REPO / "tools" / "tests" / "crew_lib.lua").read_text(encoding="utf-8")


def run(code, wait=15):
    return rc.send(LIB + "\nlocal C = _G.mtb_crew\n" + code, wait)


if __name__ == "__main__":
    args = sys.argv[1:]
    wait = 15
    if args and args[0] == "--wait":
        wait = float(args[1])
        args = args[2:]
    code = args[0]
    if code.endswith(".lua"):
        code = Path(code).read_text(encoding="utf-8")
    row = run(code, wait)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("OK" if row["ok"] else "FAIL" if row["ok"] is False else "NOANSWER", row.get("mode", ""))
    print(row["result"])
