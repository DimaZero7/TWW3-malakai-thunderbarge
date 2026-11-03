"""tools/run_game.py for the crew experiments, with one difference: a running docker container alone does not stop the launch.

The orchestrator decided this on 02.11.2026 for the night run: a neighbour's container without a lock is not a busy game.
Warhammer3.exe, probe_game.lock, HUMAN_PLAYING, gpu-train.lock and the neighbour's settings copy still stop it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_game as rg  # noqa: E402

DOCKER_REASON = "docker containers are running"
_busy = rg.rb.busy_reasons


def busy_without_docker():
    reasons = _busy()
    if DOCKER_REASON in reasons:
        print("note: docker containers are running, not treated as busy", flush=True)
    return [r for r in reasons if r != DOCKER_REASON]


rg.rb.busy_reasons = busy_without_docker

if __name__ == "__main__":
    sys.exit(rg.main())
