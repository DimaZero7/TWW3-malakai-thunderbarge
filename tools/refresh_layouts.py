"""Regenerates data/db_layouts.json after a game patch: the table versions in db.pack + the columns of those
versions from the RPFM schema. Reads TWW3-batle-ai (its schema copy and RON parser), writes only our file.
py -3.14 tools/refresh_layouts.py [--check] [--add table ...]
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NEIGHBOUR = REPO.parent / "TWW3-batle-ai"
sys.path.insert(0, str(REPO / "tools"))
import dbtable  # noqa: E402
import gamepack  # noqa: E402

sys.path.insert(0, str(NEIGHBOUR))
from tools.nn import dbschema  # noqa: E402

TARGET = REPO / "data" / "db_layouts.json"


def fields(ron, table, version):
    at = ron.find(f'\n        "{table}_tables": [')
    if at < 0:
        raise SystemExit(f"{table}: not in the schema")
    found = dbschema._Ron(ron, ron.index("[", at) + 1)._seq("]")
    for item in found:
        if item["version"] == (version or 0):
            return [[f["name"], f["field_type"]] for f in item["fields"]]
    raise SystemExit(f"{table}: no version {version} in the schema")


def main():
    ron = (NEIGHBOUR / "build" / "rpfm" / "schema_wh3.ron").read_text(encoding="utf-8")
    old = json.loads(TARGET.read_text(encoding="utf-8"))
    wanted = set(old)
    if "--add" in sys.argv:
        wanted |= set(sys.argv[sys.argv.index("--add") + 1:])
    sep = chr(92)
    out = {}
    for name, blob in gamepack.entries(gamepack.DATA / "db.pack",
                                       lambda n: n.count(sep) == 2 and n.split(sep)[1].removesuffix("_tables") in wanted):
        table = name.split(sep)[1].removesuffix("_tables")
        version = dbtable.header(blob)[1]
        layout = fields(ron, table, version)
        dbtable.decode(blob, [tuple(f) for f in layout])    # must read the whole table
        out[table] = {"version": version, "fields": layout}
    text = json.dumps(out, indent=1, sort_keys=True)
    if "--check" in sys.argv:
        print("same as data/db_layouts.json" if out == old else "DIFFERS from data/db_layouts.json")
        return
    TARGET.write_text(text, encoding="utf-8")
    print(f"{len(out)} tables written")


if __name__ == "__main__":
    main()
