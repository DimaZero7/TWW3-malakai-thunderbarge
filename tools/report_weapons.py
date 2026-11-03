"""Table of one weapon test battle: py -3.14 tools/report_weapons.py [run folder]; the last run by default.

For each test unit: men, health, ammunition and kills at the start and at the end, how far it moved, what stood nearest.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "build" / "weapons" / "runs"


def main():
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(RUNS.iterdir())[-1]
    rows = [json.loads(line) for line in (run / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    print(run.name, json.loads((run / "status.json").read_text(encoding="utf-8")) if (run / "status.json").exists() else "no status")
    first, last, moved, under_fire, melee = {}, {}, {}, {}, {}
    for row in rows:
        if row.get("event") == "sample":
            unit = row["unit"]
            first.setdefault(unit, row)
            if unit in last and row.get("pos") and last[unit].get("pos"):
                a, b = row["pos"], last[unit]["pos"]
                moved[unit] = moved.get(unit, 0) + ((a[0] - b[0]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5
            under_fire[unit] = under_fire.get(unit, 0) + (row.get("under_fire") is True)
            melee[unit] = melee.get(unit, 0) + (row.get("in_melee") is True)
            last[unit] = row
    for row in rows:
        if row.get("event") == "unit_profile" and row.get("battle_s") is None:
            cco = row.get("cco", {})
            print("profile", row["unit"], "men", row.get("men_alive"), "/", row.get("initial_men"), "range", row.get("missile_range"),
                  "hp", cco.get("HealthValue"), "/", cco.get("HealthMax"), "entities", cco.get("NumEntities"),
                  "cat", cco.get("UnitRecordContext.CategoryName"), "abilities", len(row.get("abilities") or []))
    header = f"{'unit':16} {'men':>9} {'hp':>13} {'ammo':>13} {'prim%':>11} {'sec%':>11} {'kills':>5} {'moved':>6} {'y':>6} {'near m':>6} nearest"
    print(header)
    for unit, end in last.items():
        start = first[unit]

        def pair(key, fmt="{:.2f}"):
            a, b = start.get(key), end.get(key)
            try:
                return f"{fmt.format(a)}>{fmt.format(b)}"
            except (TypeError, ValueError):
                return f"{a}>{b}"

        def cco(key):
            a, b = start["cco"].get(key), end["cco"].get(key)
            try:
                return f"{a:.2f}>{b:.2f}"
            except (TypeError, ValueError):
                return f"{a}>{b}"
        print(f"{unit:16} {pair('men', '{:.0f}'):>9} {pair('hp'):>13} {pair('ammo'):>13} {cco('PrimaryAmmoPercent'):>11} "
              f"{cco('SecondaryAmmoPercent'):>11} {end['cco'].get('NumKills')!s:>5} {moved.get(unit, 0):>6.0f} {end['pos'][1] if end.get('pos') else 0:>6.1f} "
              f"{end.get('nearest_m') or 0:>6.0f} {end.get('nearest')}")
    others = [row for row in rows if row.get("event") == "others"]
    if others:
        print("others at the end:", [(u["name"], round(u["men"]) if isinstance(u["men"], float) else u["men"]) for u in others[-1]["units"]])
    errors = [row for row in rows if row.get("event") in ("error", "hold_error", "encode_error")]
    if errors:
        print("errors:", errors[:5])


if __name__ == "__main__":
    main()
