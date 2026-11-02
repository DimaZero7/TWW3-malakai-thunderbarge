"""One test battle: checks the machine is free, installs the pack, starts the game, follows the probe's log,
captures pictures when it asks, stops the game it started and cleans up.

  py -3.14 tools/run_battle.py [--label x] [--timeout 700] [--dry-run]

Rules (CLAUDE.md, shared with TWW3-batle-ai): no launch while Warhammer3.exe, probe_game.lock, HUMAN_PLAYING,
gpu-train.lock or a docker container is there; our own mod list, used_mods.txt untouched; difficulty Normal;
preferences backed up and restored byte for byte; only our files removed; a leftover of a crashed run is
removed by the next start (build/installed.json lists what was put in the game folder, before the copy).
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import capture  # noqa: E402

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Total War WARHAMMER III")
NEIGHBOUR = REPO.parent / "TWW3-batle-ai" / "build"
LOCK = NEIGHBOUR / "steps" / "probe_game.lock"
HUMAN = NEIGHBOUR / "steps" / "HUMAN_PLAYING"
GPU_LOCK = NEIGHBOUR / "gpu-train.lock"
NEIGHBOUR_PREFS_BACKUP = NEIGHBOUR / "preferences.script.backup.txt"
PREFS = Path.home() / "AppData" / "Roaming" / "The Creative Assembly" / "Warhammer3" / "scripts" / "preferences.script.txt"
CRASH_DIR = PREFS.parent.parent / "crash_report"
BUILD = REPO / "build" / "v1"
PACK_DIR = BUILD / "pack"
PREFS_BACKUP = REPO / "build" / "preferences.script.backup.txt"
MARKER = REPO / "build" / "installed.json"
EVENTS_NAME = "tww3_mtb_events.jsonl"
MODLIST_NAME = "tww3_mtb_mods.txt"
STOP = BUILD / "STOP"   # create this file to end the current run with the normal shutdown and cleanup

# Windowed, so the window can be captured; models and textures at full quality for the pictures.
GRAPHICS = {
    "battle_difficulty": 1, "x_res": 1920, "y_res": 1080, "gfx_fullscreen": "false", "gfx_resolution_scale": 1.0,
    "gfx_dlss": 0, "gfx_aa": 2, "gfx_texture_quality": 3, "gfx_unit_quality": 3, "gfx_ssao": "false",
    "gfx_depth_of_field": 0, "gfx_fog": 0, "gfx_sky_quality": 1, "gfx_building_quality": 0, "gfx_water_quality": 0,
    "gfx_shadow_quality": 1, "gfx_tree_quality": 0, "gfx_grass_quality": 0, "gfx_terrain_quality": 1,
    "gfx_lighting_quality": 1, "gfx_effects_quality": 1, "gfx_screen_space_reflections": "false",
    "gfx_screen_space_shadows": "false", "gfx_cloth_simulation": "false",
}


def game_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Warhammer3.exe", "/NH"], capture_output=True, text=True).stdout
    return "Warhammer3.exe" in out


def busy_reasons():
    reasons = []
    if game_running():
        reasons.append("Warhammer3.exe is running")
    for path in (LOCK, HUMAN, GPU_LOCK, NEIGHBOUR_PREFS_BACKUP):
        if path.exists():
            reasons.append(f"{path} exists")
    try:
        containers = subprocess.run(["docker", "ps", "-q"], capture_output=True, text=True, timeout=30).stdout.strip()
        if containers:
            reasons.append("docker containers are running")
    except (OSError, subprocess.TimeoutExpired):
        pass
    return reasons


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def remove_installed():
    """Removes what the marker lists, each file only if unchanged. Returns files that were kept."""
    if not MARKER.exists():
        return []
    kept = []
    for entry in json.loads(MARKER.read_text(encoding="utf-8")):
        path = Path(entry["path"])
        if not path.exists():
            continue
        if sha(path) == entry["sha256"]:
            path.unlink()
        else:
            kept.append(str(path))
    if not kept:
        MARKER.unlink()
    return kept


def set_prefs():
    if PREFS_BACKUP.exists():       # left by an interrupted run of ours: it is the user's file
        PREFS.write_bytes(PREFS_BACKUP.read_bytes())
        PREFS_BACKUP.unlink()
    raw = PREFS.read_bytes()
    text = raw.decode("latin-1")
    if "RTX" not in re.search(r"(?m)^gfx_gpu [^\r\n]*", text).group(0):
        raise SystemExit("the game's GPU setting is not the RTX")
    PREFS_BACKUP.write_bytes(raw)
    for key, value in GRAPHICS.items():
        pattern = rf"(?m)^{re.escape(key)} [^;\r\n]*;"
        if not re.search(pattern, text):
            raise SystemExit(f"{key} is not in the preferences file")
        text = re.sub(pattern, f"{key} {value};", text)
    PREFS.write_bytes(text.encode("latin-1"))


def restore_prefs():
    if PREFS_BACKUP.exists():
        PREFS.write_bytes(PREFS_BACKUP.read_bytes())
        if sha(PREFS) == sha(PREFS_BACKUP):
            PREFS_BACKUP.unlink()
            return True
    return False


def stop_own_game(process):
    """Closes the game this script started (only that PID) and waits until tasklist has no game.
    Returns True when no Warhammer3.exe is left. The lock comes off only after this returns True."""
    if process is not None and process.poll() is None:
        process.terminate()
        for _ in range(40):
            if process.poll() is not None:
                break
            time.sleep(0.5)
        if process.poll() is None:
            subprocess.run(["taskkill", "/F", "/PID", str(process.pid)], capture_output=True)
    for _ in range(60):
        if not game_running():
            return True
        time.sleep(1)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="run")
    ap.add_argument("--timeout", type=int, default=720)
    ap.add_argument("--load-timeout", type=int, default=360)
    ap.add_argument("--start-timeout", type=int, default=240)
    ap.add_argument("--dry-run", action="store_true", help="only the checks; no file is written")
    args = ap.parse_args(argv)

    busy = busy_reasons()
    if busy:
        print("BUSY, not launching:", "; ".join(busy))
        return 3
    manifest = json.loads((PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    source = PACK_DIR / manifest["pack"]
    if sha(source) != manifest["pack_sha256"]:
        raise SystemExit("pack differs from its manifest: build again")
    if args.dry_run:
        print("free; would launch", manifest["scenario"])
        return 0

    kept = remove_installed()
    if kept:
        raise SystemExit(f"our earlier files changed, not touching them: {kept}")
    pack_path = GAME / "data" / manifest["pack"]
    modlist = GAME / MODLIST_NAME
    events = GAME / EVENTS_NAME
    if pack_path.exists() or modlist.exists():
        raise SystemExit("files of an earlier run remain: inspect them")
    if events.exists():
        events.unlink()

    run = BUILD / "runs" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + args.label)
    run.mkdir(parents=True)
    shutil.copy(PACK_DIR / "manifest.json", run)
    mod_text = f'mod "{manifest["pack"]}";\n'
    MARKER.parent.mkdir(exist_ok=True)
    MARKER.write_text(json.dumps([
        {"path": str(pack_path), "sha256": manifest["pack_sha256"]},
        {"path": str(modlist), "sha256": hashlib.sha256(mod_text.encode()).hexdigest()},
    ]), encoding="utf-8")

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text("TWW3-malakai-thunderbarge battle " + datetime.now().isoformat() + "\n", encoding="utf-8")
    process = None
    status = "setup_failed"
    started = time.time()
    try:
        shutil.copy(source, pack_path)
        modlist.write_bytes(mod_text.encode())
        set_prefs()
        arguments = f"game_startup_mode battle {manifest['scenario']}; {MODLIST_NAME};"
        process = subprocess.Popen(f'"{GAME / "Warhammer3.exe"}" {arguments}', cwd=GAME)
        print(f"started PID {process.pid}, run {run}", flush=True)
        status = "timeout"
        offset, loaded, fighting, loaded_at = 0, False, False, 0.0
        buffer = ""
        log = run / "events.jsonl"
        hwnd = None
        while time.time() - started < args.timeout:
            if process.poll() is not None:
                status = f"process_exited_{process.returncode}"
                break
            if STOP.exists():
                STOP.unlink()
                status = "stopped_by_flag"
                break
            crash = [p for p in CRASH_DIR.glob("*") if p.stat().st_mtime > started] if CRASH_DIR.exists() else []
            if crash:
                for p in crash:
                    if p.is_file():
                        shutil.copy(p, run)
                status = "crash_report"
                break
            if not loaded and time.time() - started > args.load_timeout:
                status = "not_loaded"
                break
            if loaded and not fighting and time.time() - loaded_at > args.start_timeout:
                status = "not_started"
                break
            if hwnd is None:
                hwnd = capture.find_window(process.pid)
            if events.exists() and events.stat().st_size > offset:
                with open(events, "rb") as f:
                    f.seek(offset)
                    chunk = f.read()
                offset += len(chunk)
                buffer += chunk.decode("utf-8", "replace").replace("\r", "")
                lines = buffer.split("\n")
                buffer = lines.pop()
                done = False
                with open(log, "a", encoding="utf-8") as out:
                    for line in lines:
                        out.write(line + "\n")
                        row = json.loads(line)
                        event = row.get("event")
                        if event in ("loaded", "ready", "start", "photoshoot_done", "order", "error", "result", "ability_try"):
                            print(line[:400], flush=True)
                        if event == "loaded":
                            loaded, loaded_at = True, time.time()
                        if event == "start":
                            fighting = True
                        if event == "shot":
                            hwnd = capture.find_window(process.pid) or hwnd
                            target = run / f"{row['name']}.png"
                            if hwnd is None:
                                print("shot asked, no window", flush=True)
                            else:
                                black = capture.save_shot(hwnd, target, (GRAPHICS["x_res"], GRAPHICS["y_res"]))
                                print(f"shot {row['name']}: black={black}", flush=True)
                        if event in ("error", "encode_error"):
                            print(line[:400], flush=True)
                            status = "lua_error"
                            done = True
                        if event == "result":
                            status, done = row.get("status", "completed"), True
                if done:
                    break
            time.sleep(0.2)
        if status == "completed":
            time.sleep(2)   # let the last lines reach the file before the game is closed
    finally:
        cleanup = {"status": status, "seconds": round(time.time() - started)}
        game_gone = stop_own_game(process)
        cleanup["game_gone"] = game_gone
        if events.exists():
            shutil.copy(events, run / "events.raw.jsonl")
        if game_gone:
            cleanup["kept"] = remove_installed()
            if events.exists() and sha(events) == sha(run / "events.raw.jsonl"):
                events.unlink()
            cleanup["prefs_restored"] = restore_prefs()
        else:
            cleanup["kept"] = "game still running: nothing removed"
        if game_gone:
            LOCK.unlink(missing_ok=True)
        else:
            cleanup["lock"] = "kept: a game is still in tasklist"
        (run / "status.json").write_text(json.dumps(cleanup, indent=1), encoding="utf-8")
        print("finished:", json.dumps(cleanup), "run:", run, flush=True)
    return 0 if status == "completed" else 1


# The game is always closed by stop_own_game in the finally above: after a result, an error, a timeout,
# a stop flag or an exception in this script. Only the PID this script started is touched.


if __name__ == "__main__":
    sys.exit(main())
