"""One weapon or empty-bay test battle: tools/run_battle.py's machine checks, launch, capture and cleanup with build/weapons.

  py -3.14 tools/build_weapons.py --battle empty
  py -3.14 tools/run_weapons.py --label empty --timeout 500 [--low]
"""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import run_battle as rb  # noqa: E402

rb.BUILD = REPO / "build" / "weapons"
rb.PACK_DIR = rb.BUILD / "pack"
rb.STOP = rb.BUILD / "STOP"

# The other project's test container (coordinator's message, 02.11.2026) does not block the game. Every other container still does.
IGNORED_CONTAINERS = {"agent-stormfiend"}
_busy = rb.busy_reasons


def busy_reasons():
    reasons = _busy()
    docker = "docker containers are running"
    if docker in reasons:
        names = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=30).stdout.split()
        if set(names) <= IGNORED_CONTAINERS:
            reasons.remove(docker)
    return reasons


rb.busy_reasons = busy_reasons

if __name__ == "__main__":
    sys.exit(rb.main())
