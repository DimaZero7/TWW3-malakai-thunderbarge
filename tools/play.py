"""Plays the mod by hand: the built mod and memreader Plus for one run of the game, then everything as it was.

  py -3.14 tools/play.py                 main menu: start a new campaign as Malakai ("Новаторы" of the Dwarfs)
  py -3.14 tools/play.py --my-mods       the same with all the mods of used_mods.txt too
  py -3.14 tools/play.py --continue      goes on with the last campaign played through this script
  py -3.14 tools/play.py --check         everything but the game: puts the files in place, shows them, takes them away
  py -3.14 tools/play.py --clean         after a crash of this script: takes our files away, gives the user's files back

Your own settings stay on: nothing in preferences.script.txt is changed for the run. used_mods.txt is only read: the game gets a list file of ours by its command line.
Your save folder is copied first and given back after: saves made in this run move to build/campaign/saves/, a changed file of yours comes back from the copy.
Use a new campaign: the mod does not support older saves, and a campaign made with it loads only with it.
The same goes for the other small folders of tools/run_game.py, also scripts/ with the settings: what you change in the game's options during the run does not stay.
The game must be closed before this starts, and this waits until you close it. The usual lock of the shared game is on during the run.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import run_game as rg  # noqa: E402

rb = rg.rb
MEMREADER = "memreader_plus.pack"
STORE = rg.SAVES
LAST = REPO / "build" / "campaign" / "play_last_save.txt"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def mod_list(my_mods, pack_name):
    """The text of our list file: the lines of used_mods.txt we need, then our pack last, so it wins."""
    used = (rb.GAME / "used_mods.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    dirs = [line for line in used if line.startswith("add_working_directory")]
    if my_mods:
        kept = [line for line in used if line.strip() and "tww3_mtb" not in line]
    else:
        found = [d for d in dirs if (Path(d.split('"')[1]) / MEMREADER).exists()]
        if not found:
            raise SystemExit(f"{MEMREADER} is not in any folder of used_mods.txt: subscribe to it in the Workshop first")
        kept = [found[0], f'mod "{MEMREADER}";']
    if not any(MEMREADER in line for line in kept):
        found = [d for d in dirs if (Path(d.split('"')[1]) / MEMREADER).exists()]
        if not found:
            raise SystemExit(f"{MEMREADER} is not in any folder of used_mods.txt")
        kept += [found[0], f'mod "{MEMREADER}";']
    return "\n".join(kept + [f'mod "{pack_name}";']) + "\n"


def install(text, pack_name):
    pack, listed = rb.GAME / "data" / pack_name, rb.GAME / rb.MODLIST_NAME
    if pack.exists() or listed.exists():
        raise SystemExit(f"{pack_name} or {rb.MODLIST_NAME} is already in the game's folder: run with --clean")
    source = rg.PACK_DIR / pack_name
    entries = [{"path": str(pack), "sha256": rb.sha(source)}, {"path": str(listed), "sha256": hashlib.sha256(text.encode()).hexdigest()}]
    rb.MARKER.parent.mkdir(exist_ok=True)
    rb.MARKER.write_text(json.dumps(entries), encoding="utf-8")
    shutil.copy(source, pack)
    listed.write_bytes(text.encode())


def clean():
    """Only our own files, and the user's guarded folders back. Refuses while the game runs."""
    if rb.game_running():
        raise SystemExit("the game is running: close it first")
    kept = rb.remove_installed()
    report = rg.restore_user(None) if rg.BACKUP.exists() else {"restored": [], "new_moved": [], "saves_identical": None}
    rb.LOCK.unlink(missing_ok=True)
    print("removed; kept because changed:", kept)
    print("your saves the same as before:", report.get("saves_identical"), "| given back:", report.get("restored"), "| moved to the store:", report.get("new_moved"))
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--my-mods", action="store_true", help="all the mods of used_mods.txt too")
    ap.add_argument("--continue", dest="resume", action="store_true", help="the last campaign played through this script")
    ap.add_argument("--check", action="store_true", help="files in place and away, no game")
    ap.add_argument("--clean", action="store_true", help="only the cleaning up")
    args = ap.parse_args()
    if args.clean:
        clean()
        return 0
    busy = rb.busy_reasons()
    if busy:
        raise SystemExit("not now: " + "; ".join(busy))
    kept = rb.remove_installed()
    if kept:
        raise SystemExit(f"earlier files of ours changed, not touching them: {kept}")
    manifest = json.loads((rg.PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    pack_name = manifest["packs"]["campaign"]
    if not (rg.PACK_DIR / pack_name).exists():
        raise SystemExit("no pack: py -3.14 tools/build.py")
    text = mod_list(args.my_mods, pack_name)
    resume = None
    if args.resume:
        name = LAST.read_text(encoding="utf-8").strip() if LAST.exists() else ""
        if not name or not (STORE / name).exists():
            raise SystemExit("nothing to go on with yet: play a campaign through this script and save it first")
        resume = name
    rb.LOCK.parent.mkdir(parents=True, exist_ok=True)
    rb.LOCK.write_text("TWW3-malakai-thunderbarge: the user plays " + datetime.now().isoformat() + "\n", encoding="utf-8")
    process = None
    try:
        rg.backup_user()
        install(text, pack_name)
        if resume:
            shutil.copy2(STORE / resume, rg.USER / "save_games" / resume)
        before = {p.name for p in (rg.USER / "save_games").glob("*.save")}
        if args.check:
            print("mod list", rb.MODLIST_NAME + ":")
            print(text)
            print("in place:", (rb.GAME / "data" / pack_name).exists(), (rb.GAME / rb.MODLIST_NAME).exists(), "| used_mods.txt untouched: only read")
            return 0
        start = f"game_startup_mode campaign_load {resume}; {rb.MODLIST_NAME};" if resume else f"{rb.MODLIST_NAME};"
        print("starting the game; this waits until you close it. Steam must be running.", flush=True)
        process = subprocess.Popen(f'"{rb.GAME / "Warhammer3.exe"}" {start}', cwd=rb.GAME)
        process.wait()
        for _ in range(60):
            if not rb.game_running():
                break
            time.sleep(1)
        new = sorted((p for p in (rg.USER / "save_games").glob("*.save") if p.name not in before), key=lambda p: p.stat().st_mtime)
        if new:
            LAST.write_text(new[-1].name, encoding="utf-8")
        elif resume:
            LAST.write_text(resume, encoding="utf-8")
    finally:
        if rb.game_running():
            print("the game still runs: close it, then run: py -3.14 tools/play.py --clean")
        else:
            clean()     # the placed save, also when saved over, goes back to the store with the new ones
    return 0


if __name__ == "__main__":
    sys.exit(main())
