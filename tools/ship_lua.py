"""The airship screen's logic modules in the campaign pack (docs/design/port-to-game.md, 4.1). Called by tools/build.py.

  config()   node tools/ship_config.mjs -> build/tree/ship_config.json: the author's tree as the page builds it, in the mod's keys (read back)
  files()    {pack path: bytes}: src/tww3_mtb_ship.lua, src/tww3_mtb_crew_model.lua and the generated tww3_mtb_ship_config.lua (`return {...}`)

They go to script/campaign/tww3_mtb/, not script/campaign/mod/: the game runs only the scripts of mod/ by itself, so these are packed and inert
until the game adapter of a later stage loads them. Each returns its table and sets nothing global.
tools/lua_vectors.py reads them out of the pack and replays build/vectors on them.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CONFIG = REPO / "build" / "tree" / "ship_config.json"
SEP = chr(92)
FOLDER = f"script{SEP}campaign{SEP}tww3_mtb{SEP}"
MODULES = {"tww3_mtb_ship.lua": REPO / "src" / "tww3_mtb_ship.lua", "tww3_mtb_crew_model.lua": REPO / "src" / "tww3_mtb_crew_model.lua"}
CONFIG_NAME = "tww3_mtb_ship_config.lua"


def config():
    node = shutil.which("node")
    if not node:
        raise SystemExit("node is not on the machine: tools/ship_config.mjs runs the page's models over the tree")
    if not (REPO / "build" / "web" / "data.json").exists():
        raise SystemExit("build/web/data.json is missing: py -3.14 tools/web_export.py --data (the crew groups, their hire and upkeep)")
    run = subprocess.run([node, str(REPO / "tools" / "ship_config.mjs"), "--out", str(CONFIG)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    sys.stdout.write(run.stdout)
    if run.returncode != 0:
        raise SystemExit("tools/ship_config.mjs: " + (run.stderr or run.stdout)[-3000:])
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def lua(v):
    """A Lua literal of a JSON value (no null: tools/ship_config.mjs leaves no null in the config)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)
    if isinstance(v, str):
        if any(ord(c) < 32 for c in v):
            raise SystemExit(f"a control character in a text of the ship config: {v!r}")
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "{" + ", ".join(lua(x) for x in v) + "}"
    if isinstance(v, dict):
        return "{" + ", ".join(f"[{json.dumps(k, ensure_ascii=False)}] = {lua(x)}" for k, x in sorted(v.items())) + "}"
    raise SystemExit(f"the ship config holds a {type(v).__name__}: {v!r}")


def files():
    cfg = config()
    out = {FOLDER + name: path.read_bytes() for name, path in MODULES.items()}
    out[FOLDER + CONFIG_NAME] = ("-- Made by tools/ship_lua.py from build/tree/ship_config.json (tools/ship_config.mjs). Do not edit.\nreturn " + lua(cfg) + "\n").encode("utf-8")
    return out
