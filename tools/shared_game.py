"""The game installation shared with the neighbouring project TWW3-batle-ai (CLAUDE.md, «Общая игра с TWW3-batle-ai»).
The ONE place of its paths: every launcher of ours imports them from here.

The neighbour's own rule (read only, see tools/tests/shared_game_test.py, which fails if these drift):
  state/probe_game.lock   one runner holds the game; the text is the holder's token. bridge/launcher/launch.ps1 and
                          ops/guard.* refuse unless their BAI_LOCK_HELD equals that text, so any non-empty line of ours blocks them.
  state/HUMAN_PLAYING     the user plays.
  build/gpu-train.lock    the GPU lock of the training (net/common/gpu.py).
  build/preferences.script.backup.txt   the launcher's copy of the user's preferences.script.txt while its game runs.
The old folder build/steps/ is gone; a file there still counts as busy (a half-moved state).

We write only LOCK, one line «mtb, начало HH:MM», created atomically, and remove it only while it still says what we wrote.
Nothing else is created in the neighbour's tree: without its state/ folder we refuse to launch (the neighbour could not see us).
"""
import os
import re
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
NEIGHBOUR_ROOT = REPO.parent / "TWW3-batle-ai"
NEIGHBOUR_STATE = NEIGHBOUR_ROOT / "state"                                       # bridge/config.py STATE, ops/guard.py STATE
LOCK = NEIGHBOUR_STATE / "probe_game.lock"                                       # ops/guard.py LOCK, launch.ps1 $lockFile
HUMAN = NEIGHBOUR_STATE / "HUMAN_PLAYING"                                        # ops/guard.py HUMAN
GPU_LOCK = NEIGHBOUR_ROOT / "build" / "gpu-train.lock"                           # net/common/gpu.py LOCK
NEIGHBOUR_PREFS_BACKUP = NEIGHBOUR_ROOT / "build" / "preferences.script.backup.txt"  # launch.ps1 $prefsBackup
OLD_STEPS = NEIGHBOUR_ROOT / "build" / "steps"                                   # before the neighbour's move: only read
OLD_LOCK = OLD_STEPS / "probe_game.lock"
OLD_HUMAN = OLD_STEPS / "HUMAN_PLAYING"

OUR_LOCK = re.compile(r"^mtb, начало \d\d:\d\d$")


def marks():
    """[(what, path)]: every file whose presence means the game is not ours to start."""
    return [("probe_game.lock", LOCK), ("HUMAN_PLAYING", HUMAN), ("gpu-train.lock", GPU_LOCK),
            ("the neighbour's settings copy", NEIGHBOUR_PREFS_BACKUP),
            ("probe_game.lock at the old path", OLD_LOCK), ("HUMAN_PLAYING at the old path", OLD_HUMAN)]


def busy_reasons(state=None):
    """Why we may not start the game, from the files alone ([] when free). state: the folder of LOCK (tests)."""
    state = Path(state) if state else NEIGHBOUR_STATE
    reasons = [f"{path} exists" for _, path in marks() if path.exists()]
    if not state.is_dir():
        reasons.append(f"{state} is missing: our lock would be invisible to the neighbour, not creating it there")
    return reasons


def lock_text(now=None):
    return f"mtb, начало {(now or datetime.now()):%H:%M}"


def take_lock(lock=None):
    """Writes our lock (exclusive create) and returns its text; raises SystemExit if it cannot be ours."""
    lock = Path(lock) if lock else LOCK
    if not lock.parent.is_dir():
        raise SystemExit(f"not launching: {lock.parent} is missing, the neighbour would not see our lock (not creating it)")
    text = lock_text()
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        raise SystemExit(f"not launching: {lock} exists ({read_lock(lock)!r})") from None
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")
    return text


def read_lock(lock=None):
    try:
        return Path(lock or LOCK).read_text(encoding="utf-8-sig").strip()
    except OSError:
        return None


def release_lock(text=None, lock=None):
    """Removes the lock only while it says `text` (or, with no text, any line of ours: a cleanup after a crash). True if removed."""
    lock = Path(lock) if lock else LOCK
    now = read_lock(lock)
    if now is None or not (now == text if text else OUR_LOCK.match(now)):
        return False
    lock.unlink()
    return True


def describe():
    """Lines for a dry run: what is checked and where the lock would go."""
    lines = ["shared game (tools/shared_game.py):"]
    for what, path in marks():
        lines.append(f"  check {what}: {path} -> {'EXISTS' if path.exists() else 'absent'}")
    lines.append(f"  state folder {NEIGHBOUR_STATE}: {'present' if NEIGHBOUR_STATE.is_dir() else 'MISSING (launch refused)'}")
    lines.append(f"  lock would be written to {LOCK} = «{lock_text()}»")
    return lines
