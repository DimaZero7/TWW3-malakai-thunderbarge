"""One test session of the real game, driven from outside with tools/rc.py. Used for the campaign tests.

  py -3.14 tools/run_game.py --label name --packs harness [campaign] [--args "game_startup_mode ..."] [--timeout 1800]

Reuses the rules of tools/run_battle.py: no launch while the game, a lock, HUMAN_PLAYING, gpu-train.lock or docker is busy;
own mod list; difficulty Normal, windowed; everything restored; the game this script started is ALWAYS closed
(result, error, timeout, crash, exception in this script) and the lock comes off only when tasklist has no game.

The user's data: save_games and the small settings folders are copied before the start and compared after. A changed or
missing file of the user is put back; a new file (ours, a test save or an autosave) goes to build/campaign/saves/ and leaves
the game's folder. A save from build/campaign/saves/ is put in place for the session with --save NAME and removed after.
Autosaves are off for the session (incremental_autosave_enabled false).
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
import run_battle as rb  # noqa: E402

CAMPAIGN = REPO / "build" / "campaign"
PACK_DIR = CAMPAIGN / "pack"
SAVES = CAMPAIGN / "saves"
STATE = CAMPAIGN / "session.json"
STOP = CAMPAIGN / "STOP"
USER = rb.PREFS.parent.parent
GUARDED = ["save_games", "advice_history", "army_setups", "battle_preferences", "event_feed", "resume", "replays", "scripts"]
BACKUP = REPO / "build" / "user_backup"
SESSION_FILES = ["tww3_mtb_events.jsonl", "tww3_mtb_cmd.lua", "tww3_mtb_rc.jsonl"]
SETTINGS = dict(rb.GRAPHICS, campaign_difficulty=1, incremental_autosave_enabled="false")
LOW_GRAPHICS = dict(SETTINGS, x_res=1280, y_res=720, gfx_aa=0, gfx_texture_quality=0, gfx_unit_quality=0, gfx_shadow_quality=0,
                    gfx_sky_quality=0, gfx_terrain_quality=0, gfx_lighting_quality=0, gfx_effects_quality=0)
# Integrated GPU (the RTX is out of the machine): the same plus a lower render scale. Unit size stays: the men counted must not change.
IGPU_GRAPHICS = dict(LOW_GRAPHICS, gfx_resolution_scale=0.5, gfx_texture_filtering=0, gfx_distortion="false", porthole_3d="false")
SW_SHOWNOACTIVATE = 4
SW_SHOWMINNOACTIVE = 7
PLAIN_SETTINGS = {"battle_difficulty": 1, "campaign_difficulty": 1, "incremental_autosave_enabled": "false"}


def tree_hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def backup_user():
    """Copies the guarded folders, unless a copy of an interrupted run is there: that copy is the truth then."""
    if BACKUP.exists():
        restore_user(None)
    BACKUP.mkdir(parents=True)
    for name in GUARDED:
        source = USER / name
        if source.exists():
            shutil.copytree(source, BACKUP / name)
    (BACKUP / "hashes.json").write_text(json.dumps(tree_hashes(BACKUP)), encoding="utf-8")


def restore_user(run):
    """Puts the user's files back; new files of save_games move to our store. Returns a report."""
    report = {"restored": [], "new_moved": [], "new_removed": []}
    hashes = json.loads((BACKUP / "hashes.json").read_text(encoding="utf-8"))
    for name in GUARDED:
        target, saved = USER / name, BACKUP / name
        if not saved.exists() and not target.exists():
            continue
        for rel, digest in hashes.items():
            if not rel.startswith(name + "/"):
                continue
            path = USER / rel
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(BACKUP / rel, path)
                report["restored"].append(rel)
        if target.exists():
            for path in target.rglob("*"):
                rel = path.relative_to(USER).as_posix()
                if path.is_file() and rel not in hashes:
                    if name == "save_games":
                        SAVES.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(path), SAVES / path.name)
                        report["new_moved"].append(path.name)
                    else:
                        path.unlink()
                        report["new_removed"].append(rel)
    now = tree_hashes(USER / "save_games") if (USER / "save_games").exists() else {}
    want = {k.removeprefix("save_games/"): v for k, v in hashes.items() if k.startswith("save_games/")}
    report["saves_identical"] = now == want
    if report["saves_identical"]:
        shutil.rmtree(BACKUP)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="session")
    ap.add_argument("--packs", nargs="+", default=["harness"], choices=["harness", "campaign"])
    ap.add_argument("--args", default="")
    ap.add_argument("--save", help="a save of build/campaign/saves to make available for this session")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--user-mods", nargs="*", default=[])
    ap.add_argument("--user-mods-file", help="a text file with one pack name per line")
    ap.add_argument("--high-graphics", action="store_true", help="full quality models, for pictures")
    ap.add_argument("--plain-settings", action="store_true", help="keep the user's graphics settings for this session")
    ap.add_argument("--igpu", action="store_true", help="the lowest settings, for the integrated GPU")
    ap.add_argument("--minimized", action="store_true", help="ask Windows to show the game minimized and not active")
    ap.add_argument("--set", nargs="*", default=[], metavar="KEY=VALUE", help="more settings for this session only, restored after it")
    args = ap.parse_args(argv)

    busy = rb.busy_reasons()
    if busy:
        print("BUSY, not launching:", "; ".join(busy), flush=True)
        return 3
    manifest = json.loads((PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    kept = rb.remove_installed()
    if kept:
        raise SystemExit(f"our earlier files changed, not touching them: {kept}")
    names = [manifest["packs"][p] for p in args.packs]
    modlist = rb.GAME / rb.MODLIST_NAME
    for name in names:
        if (rb.GAME / "data" / name).exists():
            raise SystemExit(f"{name} is already in data/")
    if modlist.exists():
        raise SystemExit("an earlier mod list remains")
    for name in SESSION_FILES:
        (rb.GAME / name).unlink(missing_ok=True)

    run = CAMPAIGN / "runs" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + args.label)
    run.mkdir(parents=True)
    # --user-mods NAME...: packs of the user's used_mods.txt to load too (read only, from where they are).
    used = (rb.GAME / "used_mods.txt").read_text(encoding="utf-8", errors="replace").splitlines()
    extra_dirs = [l for l in used if l.startswith("add_working_directory")]
    mod_text = ""
    wanted_mods = list(args.user_mods)
    if args.user_mods_file:
        wanted_mods += [l.strip() for l in Path(args.user_mods_file).read_text(encoding="utf-8").splitlines() if l.strip()]
    for wanted in wanted_mods:
        found = [d for d in extra_dirs if (Path(d.split('"')[1]) / wanted).exists()]
        if not found:
            raise SystemExit(f"{wanted}: not found in the user's working directories")
        mod_text += found[0] + "\n" + f'mod "{wanted}";\n'
    mod_text += "".join(f'mod "{n}";\n' for n in names)
    entries = [{"path": str(rb.GAME / "data" / n), "sha256": rb.sha(PACK_DIR / n)} for n in names]
    entries.append({"path": str(modlist), "sha256": hashlib.sha256(mod_text.encode()).hexdigest()})
    rb.MARKER.parent.mkdir(exist_ok=True)
    rb.MARKER.write_text(json.dumps(entries), encoding="utf-8")

    rb.LOCK.parent.mkdir(parents=True, exist_ok=True)
    rb.LOCK.write_text("TWW3-malakai-thunderbarge campaign test " + datetime.now().isoformat() + "\n", encoding="utf-8")
    process = None
    status = "setup_failed"
    started = time.time()
    placed_save = None
    STOP.unlink(missing_ok=True)
    try:
        backup_user()
        for name in names:
            shutil.copy(PACK_DIR / name, rb.GAME / "data" / name)
        modlist.write_bytes(mod_text.encode())
        if args.save:
            placed_save = USER / "save_games" / args.save
            shutil.copy2(SAVES / args.save, placed_save)
        rb.GRAPHICS.clear()
        settings = PLAIN_SETTINGS if args.plain_settings else IGPU_GRAPHICS if args.igpu else (SETTINGS if args.high_graphics else LOW_GRAPHICS)
        settings = dict(settings, **dict(item.split("=", 1) for item in args.set))
        rb.GRAPHICS.update(settings)
        rb.set_prefs()
        start_args = f"{args.args}; {rb.MODLIST_NAME};" if args.args else f"{rb.MODLIST_NAME};"
        info = subprocess.STARTUPINFO()
        info.dwFlags = subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = SW_SHOWMINNOACTIVE if args.minimized else SW_SHOWNOACTIVATE
        process = subprocess.Popen(f'"{rb.GAME / "Warhammer3.exe"}" {start_args}', cwd=rb.GAME, startupinfo=info)
        STATE.write_text(json.dumps({"pid": process.pid, "run": str(run), "started": started,
                                     "x_res": settings.get("x_res", 2560), "y_res": settings.get("y_res", 1440)}), encoding="utf-8")
        print(f"started PID {process.pid}, run {run}", flush=True)
        status = "timeout"
        behind = rb.capture.KeepBehind(process.pid, run / "window.log")
        while time.time() - started < args.timeout:
            behind.tick()
            if process.poll() is not None:
                status = f"process_exited_{process.returncode}"
                break
            if STOP.exists():
                STOP.unlink()
                status = "stopped_by_flag"
                break
            crash = [p for p in rb.CRASH_DIR.glob("*") if p.stat().st_mtime > started] if rb.CRASH_DIR.exists() else []
            if crash:
                status = "crash_report"
                time.sleep(5)       # the game may still be writing its dump
                for p in crash:
                    if p.is_file() and p.suffix != ".mdmp":
                        try:
                            shutil.copy(p, run)
                        except OSError:
                            pass
                break
            time.sleep(0.5)
    finally:
        cleanup = {"status": status, "seconds": round(time.time() - started)}
        game_gone = rb.stop_own_game(process)
        cleanup["game_gone"] = game_gone
        for name in SESSION_FILES:
            path = rb.GAME / name
            if path.exists():
                shutil.copy(path, run / name)
        if game_gone:
            cleanup["kept"] = rb.remove_installed()
            for name in SESSION_FILES:
                (rb.GAME / name).unlink(missing_ok=True)
            cleanup["prefs_restored"] = rb.restore_prefs()
            if placed_save is not None:
                placed_save.unlink(missing_ok=True)
            cleanup["user_files"] = restore_user(run)
            rb.LOCK.unlink(missing_ok=True)
        else:
            cleanup["lock"] = "kept: a game is still in tasklist"
        STATE.unlink(missing_ok=True)
        (run / "status.json").write_text(json.dumps(cleanup, indent=1, ensure_ascii=False), encoding="utf-8")
        print("finished:", json.dumps(cleanup, ensure_ascii=False), "run:", run, flush=True)
    return 0 if status in ("stopped_by_flag",) else 1


if __name__ == "__main__":
    sys.exit(main())
