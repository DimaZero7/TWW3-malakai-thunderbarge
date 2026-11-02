"""Runs a test Lua with variables set: py -3.14 tools/rc_lua.py tools/tests/click_named.lua mtb_name=button_attack [--wait 15]"""
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main():
    script = Path(sys.argv[1])
    code = ""
    extra = []
    args = sys.argv[2:]
    while args:
        a = args.pop(0)
        if a == "--wait":
            extra = ["--wait", args.pop(0)]
        else:
            name, _, value = a.partition("=")
            code += f'{name} = "{value}"\n'
    code += script.read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False, encoding="utf-8") as f:
        f.write(code)
    try:
        subprocess.run([sys.executable, str(REPO / "tools" / "rc.py"), "--file", f.name] + extra, check=False)
    finally:
        Path(f.name).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
