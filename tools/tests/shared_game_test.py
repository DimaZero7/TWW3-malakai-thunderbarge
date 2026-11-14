"""The shared game's paths and lock (tools/shared_game.py) against the neighbour's code: py -3.14 tools/tests/shared_game_test.py
Reads TWW3-batle-ai (never writes there) and fails if its lock, HUMAN_PLAYING, GPU lock or settings copy moved away from our constants.
The lock writer is tried on a temp folder only. Skips the neighbour's part with a message when that repo is absent. Prints a line a check."""
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import shared_game as sg  # noqa: E402

failed = 0


def check(name, ok, extra=""):
    global failed
    failed += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"  {extra}"))


def text(rel):
    return (sg.NEIGHBOUR_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def rel(path):
    return path.relative_to(sg.NEIGHBOUR_ROOT).as_posix()


def neighbour():
    cfg, gpy, gps, launch, gpu = (text(p) for p in ("bridge/config.py", "ops/guard.py", "ops/guard.ps1",
                                                     "bridge/launcher/launch.ps1", "net/common/gpu.py"))
    state = re.search(r'^STATE\s*=\s*ROOT\s*/\s*"([^"]+)"', cfg, re.M)
    check("bridge/config.py STATE = ROOT / <our state folder>", state and state.group(1) == rel(sg.NEIGHBOUR_STATE), state and state.group(0))
    for name, path in (("LOCK", sg.LOCK), ("HUMAN", sg.HUMAN)):
        m = re.search(rf'^{name}\s*=\s*STATE\s*/\s*"([^"]+)"', gpy, re.M)
        check(f"ops/guard.py {name} = STATE / {path.name} (= our {rel(path)})", m and state and f"{state.group(1)}/{m.group(1)}" == rel(path), m and m.group(0))
    g_state = re.search(r"^\$GuardState\s*=.*'(\w+)'\)?\s*$", gps, re.M)
    check("ops/guard.ps1 $GuardState is the state folder", g_state and g_state.group(1) == sg.NEIGHBOUR_STATE.name, g_state and g_state.group(0))
    check("ops/guard.ps1 joins 'probe_game.lock' and 'HUMAN_PLAYING'", f"'{sg.LOCK.name}'" in gps and f"'{sg.HUMAN.name}'" in gps)
    l_state = re.search(r"^\$stateDir\s*=\s*Join-Path\s+\$repo\s+'([^']+)'", launch, re.M)
    l_lock = re.search(r"^\$lockFile\s*=\s*Join-Path\s+\$stateDir\s+'([^']+)'", launch, re.M)
    check("launch.ps1 reads <state>/probe_game.lock", l_state and l_lock and f"{l_state.group(1)}/{l_lock.group(1)}" == rel(sg.LOCK),
          (l_state and l_state.group(0), l_lock and l_lock.group(0)))
    check("launch.ps1 checks <state>/HUMAN_PLAYING", f"Join-Path $stateDir '{sg.HUMAN.name}'" in launch)
    # a lock it does not hold stops it: refused unless BAI_LOCK_HELD equals the lock's text (ours never sets it)
    check("launch.ps1 refuses a lock whose text is not its BAI_LOCK_HELD", re.search(r"-not \$env:BAI_LOCK_HELD -or .*-ne \$held\) \{ throw", launch) is not None)
    backup = re.search(r"^\$prefsBackup\s*=\s*Join-Path\s+\$repo\s+'([^']+)'", launch, re.M)
    check("launch.ps1 $prefsBackup is our NEIGHBOUR_PREFS_BACKUP", backup and backup.group(1).replace("\\", "/") == rel(sg.NEIGHBOUR_PREFS_BACKUP), backup and backup.group(0))
    gl = re.search(r'^LOCK\s*=\s*ROOT\s*/\s*"(\w+)"\s*/\s*"([^"]+)"', gpu, re.M)
    check("net/common/gpu.py LOCK is our GPU_LOCK", gl and "/".join(gl.groups()) == rel(sg.GPU_LOCK), gl and gl.group(0))


def writer():
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "state"
        lock = state / "probe_game.lock"
        try:
            sg.take_lock(lock)
            check("no state folder: refused", False, "took the lock")
        except SystemExit as e:
            check("no state folder: refused, nothing created", not state.exists(), str(e))
        check("no state folder: busy", any("is missing" in r for r in sg.busy_reasons(state)))
        state.mkdir()
        token = sg.take_lock(lock)
        raw = lock.read_bytes()
        check("lock is one line «mtb, начало HH:MM» in UTF-8, no BOM", raw == (token + "\n").encode("utf-8") and sg.OUR_LOCK.match(token), raw)
        check("ops/guard.py reads it as the same text (utf-8-sig, strip)", lock.read_text(encoding="utf-8-sig").strip() == token)
        try:
            sg.take_lock(lock)
            check("second take refused", False)
        except SystemExit:
            check("second take refused (exclusive create)", True)
        check("release with another text keeps it", not sg.release_lock("mtb, начало 00:00", lock) and lock.exists())
        check("release with our text removes it", sg.release_lock(token, lock) and not lock.exists())
        lock.write_text("label live 2026-11-14T10:00:00 pid 1\n", encoding="utf-8")
        check("cleanup never removes the neighbour's lock", not sg.release_lock(None, lock) and lock.exists())


def main():
    for what, path in sg.marks():
        check(f"{what} is inside the neighbour's repo", sg.NEIGHBOUR_ROOT in path.parents)
    check("our lock is written in the state folder", sg.LOCK.parent == sg.NEIGHBOUR_STATE)
    if (sg.NEIGHBOUR_ROOT / "bridge" / "config.py").exists():
        neighbour()
    else:
        print(f"skip the neighbour's code: {sg.NEIGHBOUR_ROOT} is absent")
    writer()
    print("failed:", failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
