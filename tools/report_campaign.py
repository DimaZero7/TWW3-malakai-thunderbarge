"""Compares the snapshots written by tools/tests/snapshot.lua. py -3.14 tools/report_campaign.py [run ...]
Prints each snapshot as label + fields, and the differences between before_save (first run) and after_load (second run)."""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "build" / "campaign" / "runs"
IGNORED = {"label"}


def parse(text):
    """The remote's dump of a table: {a=1, b={1=x, 2=y}} into nested dicts."""
    pos = 0

    def value():
        nonlocal pos
        if text[pos] == "{":
            pos += 1
            out = {}
            while text[pos] != "}":
                m = re.match(r"([^=,{}]+)=", text[pos:])
                key = m.group(1).strip()
                pos += m.end()
                out[key] = value()
                if text[pos:pos + 2] == ", ":
                    pos += 2
            pos += 1
            return out
        m = re.match(r"[^,{}]*(?:,[^ =,{}][^,{}]*)*", text[pos:])
        pos += m.end()
        return m.group(0).strip()

    return value()


def snapshots(run):
    rows = []
    path = run / "tww3_mtb_events.jsonl"
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        row = json.loads(line)
        if row.get("event") == "snapshot":
            rows.append(parse(row["text"]))
    return rows


def main():
    names = sys.argv[1:] or ["20261102-180707-c1", "20261102-183031-c2"]
    all_rows = {}
    for name in names:
        for snap in snapshots(RUNS / name):
            all_rows.setdefault(snap.get("label"), []).append((name, snap))
            print(name, snap.get("label"), "turn", snap.get("turn"), "rank", snap.get("rank"), "unit", snap.get("general_unit"),
                  "items", list((snap.get("anc") or {}).values()), "skills", len(snap.get("skills") or {}),
                  "wounded", snap.get("wounded"), "xp", snap.get("xp"))
    before = [s for s in all_rows.get("before_save", [])]
    after = [s for s in all_rows.get("after_load", [])]
    if before and after:
        a, b = before[-1][1], after[-1][1]
        keys = (set(a) | set(b)) - IGNORED
        diff = {k: (a.get(k), b.get(k)) for k in sorted(keys) if a.get(k) != b.get(k)}
        print("before_save vs after_load:", "IDENTICAL" if not diff else diff)
        print("compared fields:", sorted(keys))


if __name__ == "__main__":
    main()
