"""Reads a run's events and prints the checks of docs/v1.md. py -3.14 tools/report.py [run folder]; default: latest."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TIMER = "wh3_dlc25_unit_passive_unbinding_spirit_of_grungni"
WANT_ACTIVE = {"wh3_dlc25_lord_abilities_cinderblast_cluster_bomb", "wh3_dlc25_lord_abilities_deranged_munitions",
               "wh3_dlc25_unit_abilities_spear_of_grungni", "wh3_dlc25_unit_abilities_thunderburner"}
WANT_PASSIVE = {"wh3_dlc25_character_passive_artillery_master", "wh3_main_unit_passive_single_entity"}
NOT_WANTED = "deathblow"


def main():
    run = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted((REPO / "build" / "v1" / "runs").iterdir())[-1]
    rows = [json.loads(l) for l in (run / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    samples = [r for r in rows if r["event"] == "sample"]
    for r in samples:
        p = r.get("pos") or [0, 0, 0]
        print(f"{r.get('battle_s', 0):6.0f}s pos {p[0]:7.1f} {p[1]:6.1f} {p[2]:6.1f} moving={r.get('moving')} men={r.get('men')} "
              f"hp={r.get('hp')} ammo={r.get('ammo_cco')} firing={r.get('firing')} kills={r.get('kills')} "
              f"enemy_men={r.get('enemy_men')} dist={r.get('nearest_enemy_m')} commanding={r.get('commanding')}")
    profile = next(r for r in rows if r["event"] == "unit_profile" and r.get("tag") == "start")
    end_profile = next((r for r in rows if r["event"] == "unit_profile" and r.get("tag") == "end"), None)
    checks = [r for r in rows if r["event"] == "commander_check"]
    result = next((r for r in rows if r["event"] == "result"), None)
    print("run:", run)
    print("result:", result)
    print("commander checks:", json.dumps(checks[-1], ensure_ascii=False) if checks else None)
    print("ui category:", profile["cco"].get("UnitRecordContext.CategoryName"), "class:", profile.get("class"),
          "type:", profile.get("type"), "men:", profile.get("initial_men"))
    active, passive = set(profile["abilities_active"]), set(profile["abilities_passive"])
    print("missing abilities:", sorted((WANT_ACTIVE - active) | (WANT_PASSIVE - passive)))
    print("deathblow present:", sorted(a for a in active | passive if NOT_WANTED in a))
    print("timer ability present:", sorted(a for a in active | passive if a.startswith(TIMER)))
    if end_profile:
        late = set(end_profile["abilities_active"]) | set(end_profile["abilities_passive"])
        print("at the end: timer present:", sorted(a for a in late if a.startswith(TIMER)),
              "men:", end_profile.get("men_alive"), "battle_s:", end_profile.get("battle_s"))
    if samples:
        a, b = samples[0], samples[-1]
        moved = sum(((x[0] - y[0]) ** 2 + (x[2] - y[2]) ** 2) ** .5 for x, y in
                    zip([s["pos"] for s in samples[1:]], [s["pos"] for s in samples[:-1]]))
        print(f"path travelled {moved:.0f} m; enemy men {a.get('enemy_men')} -> {b.get('enemy_men')}; "
              f"ammo {a.get('ammo_cco')} -> {b.get('ammo_cco')}; kills -> {b.get('kills')}; "
              f"firing samples {sum(1 for s in samples if s.get('firing') is True)} of {len(samples)}; "
              f"last hp {b.get('hp')}, last men {b.get('men')}")
    for r in rows:
        if r["event"] in ("ability_try", "order", "error", "encode_error", "select_card"):
            print(json.dumps(r, ensure_ascii=False)[:260])


if __name__ == "__main__":
    main()
