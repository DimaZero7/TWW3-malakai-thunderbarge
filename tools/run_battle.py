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
import shared_game  # noqa: E402
from shared_game import GPU_LOCK, HUMAN, LOCK, NEIGHBOUR_PREFS_BACKUP  # noqa: E402,F401  (the paths live in shared_game.py)

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Total War WARHAMMER III")
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


class FocusGuard:
    """Keeps the game out of the foreground for the whole run (CLAUDE.md: the game runs without focus, under other windows).

    Why the game gets it: STARTUPINFO's SW_SHOWNOACTIVATE only covers the first ShowWindow; the game then activates its own window
    (again when it recreates the window or loads a campaign or battle), and Windows lets it. Our process is not the foreground one, so a
    plain SetForegroundWindow back is refused (run 20261114-222543: REFUSED in 2 ms), and LockSetForegroundWindow, AllowSetForegroundWindow
    and SPI_SETFOREGROUNDLOCKTIMEOUT only work for a caller that already may set the foreground. No keys and no mouse are ever sent.

    start() runs a thread for the whole run: a foreground event hook (EVENT_SYSTEM_FOREGROUND) plus a 20 ms poll. When the game is in
    the foreground, the methods are tried in order until the window that had it has it again:
      attach_both  this thread's input attached to the game's (foreground) thread AND the target window's thread, then
                   BringWindowToTop + SetForegroundWindow on the target: accepted every time in the stand-in test, ~10 ms (the old
                   guard attached to the game's thread only and was refused, as in run 20261114-222543); while the game's window
                   thread pumps no messages (loading), the call waits for it and the foreground comes back the moment the game wakes;
      attach       the same attached to the target's thread only: never waits on the game, but Windows accepts it only sometimes;
      minimize     ShowWindowAsync(game, SW_MINIMIZE): Windows itself activates the next window in Z order; if that is not the
                   target, attach from there; then ShowWindowAsync(game, SW_SHOWNOACTIVATE) at once (a minimised window neither
                   renders nor answers PrintWindow, so it never stays minimised; at most once per 1.5 s); last resort;
      switch       SwitchToThisWindow(target): not in the default order, refused in tools/tests/focus_guard_test.py.
    and the game window goes to the bottom of the Z order without activation. The user is never fought: when another window (not the
    game) becomes the foreground, that window is remembered; if it is closed, the next window in Z order gets the foreground back.
    A click into the game is given back too, and the log says so. Every take, give-back, refusal and user switch goes to the log
    with milliseconds; self.events keeps the same for tests. Proof without the game: py -3.14 tools/tests/focus_guard_test.py.
    """

    ORDER = ("attach_both", "attach", "minimize")
    MIN_GAP = 1.5       # seconds between two minimise-and-restore of the game window

    def __init__(self, pid, log, methods=ORDER, poll=0.02):
        import ctypes
        import ctypes.wintypes as wt
        import threading
        self.ctypes, self.wt, self.threading = ctypes, wt, threading
        u = self.u = ctypes.WinDLL("user32", use_last_error=True)
        k = self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        H, D, B = wt.HWND, wt.DWORD, wt.BOOL
        for f, res, args in [
            (u.GetForegroundWindow, H, []), (u.GetWindowThreadProcessId, D, [H, ctypes.POINTER(D)]),
            (u.SetForegroundWindow, B, [H]), (u.IsWindow, B, [H]), (u.IsIconic, B, [H]), (u.BringWindowToTop, B, [H]),
            (u.AttachThreadInput, B, [D, D, B]), (u.GetWindowTextW, ctypes.c_int, [H, wt.LPWSTR, ctypes.c_int]),
            (u.SwitchToThisWindow, None, [H, B]), (u.ShowWindowAsync, B, [H, ctypes.c_int]),
            (u.SetWindowPos, B, [H, H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]),
            (u.GetLastInputInfo, B, [ctypes.c_void_p]), (u.SystemParametersInfoW, B, [wt.UINT, wt.UINT, ctypes.c_void_p, wt.UINT]),
            (u.SetWinEventHook, wt.HANDLE, [D, D, wt.HMODULE, ctypes.c_void_p, D, D, D]), (u.UnhookWinEvent, B, [wt.HANDLE]),
            (u.MsgWaitForMultipleObjects, D, [D, ctypes.c_void_p, B, D, D]),
            (u.PeekMessageW, B, [ctypes.c_void_p, H, wt.UINT, wt.UINT, wt.UINT]),
            (u.TranslateMessage, B, [ctypes.c_void_p]), (u.DispatchMessageW, ctypes.c_ssize_t, [ctypes.c_void_p]),
            (u.IsWindowVisible, B, [H]), (u.GetWindowLongW, ctypes.c_long, [H, ctypes.c_int]),
            (u.GetWindowTextLengthW, ctypes.c_int, [H]), (u.EnumWindows, B, [ctypes.c_void_p, wt.LPARAM]),
            (k.GetCurrentThreadId, D, []), (k.GetTickCount, D, []), (k.OpenProcess, wt.HANDLE, [D, B, D]),
            (k.CloseHandle, B, [wt.HANDLE]), (k.QueryFullProcessImageNameW, B, [wt.HANDLE, D, wt.LPWSTR, ctypes.POINTER(D)]),
        ]:
            f.restype, f.argtypes = res, args
        self.pid, self.log, self.methods, self.poll = pid, log, tuple(methods), poll
        self.prev = None            # the window that gets the foreground back
        self.landed = None          # a window our minimise handed the foreground to that is not prev: not a user's choice
        self.taken = self.given = 0
        self.events = []            # one dict per take, for tests
        self._hold = None           # the take in progress: dict
        self._last_min = -1e9
        self._minimized = None
        self._no_fg = False
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._flag = False
        fg = u.GetForegroundWindow()
        if fg and self.owner(fg) != pid:
            self.prev = fg
        lock_timeout = wt.DWORD()
        u.SystemParametersInfoW(0x2000, 0, ctypes.byref(lock_timeout), 0)      # SPI_GETFOREGROUNDLOCKTIMEOUT, read only
        self.write(f"focus guard: foreground before the game {self.describe(self.prev)}; methods {', '.join(self.methods)}; "
                   f"user idle {self.idle_ms() / 1000:.0f} s; ForegroundLockTimeout {lock_timeout.value} ms")

    # ---- helpers
    def write(self, text):
        with Path(self.log).open("a", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%H:%M:%S.%f")[:-3] + " " + text + "\n")

    def owner(self, hwnd):
        pid = self.wt.DWORD()
        self.u.GetWindowThreadProcessId(hwnd, self.ctypes.byref(pid))
        return pid.value

    def thread_of(self, hwnd):
        return self.u.GetWindowThreadProcessId(hwnd, None)

    def is_game(self, hwnd):
        return bool(hwnd) and self.owner(hwnd) == self.pid

    def idle_ms(self):
        info = (self.wt.UINT * 2)(8, 0)        # LASTINPUTINFO
        self.u.GetLastInputInfo(info)
        return (self.k.GetTickCount() - info[1]) & 0xFFFFFFFF

    def describe(self, hwnd):
        if not hwnd:
            return "none"
        buf = self.ctypes.create_unicode_buffer(120)
        self.u.GetWindowTextW(hwnd, buf, 120)
        exe = "?"
        handle = self.k.OpenProcess(0x1000, False, self.owner(hwnd))       # PROCESS_QUERY_LIMITED_INFORMATION
        if handle:
            name = self.ctypes.create_unicode_buffer(400)
            size = self.wt.DWORD(400)
            if self.k.QueryFullProcessImageNameW(handle, 0, name, self.ctypes.byref(size)):
                exe = name.value.rsplit("\\", 1)[-1]
            self.k.CloseHandle(handle)
        return f"{int(hwnd)} {exe} «{buf.value[:50]}»"

    def next_window(self):
        """The topmost visible, not minimised, not tool top-level window that is not the game's, or None (EnumWindows is in Z order)."""
        found = []
        proto = self.ctypes.WINFUNCTYPE(self.wt.BOOL, self.wt.HWND, self.wt.LPARAM)

        def visit(hwnd, _):
            ex = self.u.GetWindowLongW(hwnd, -20)        # GWL_EXSTYLE
            if (self.u.IsWindowVisible(hwnd) and not self.u.IsIconic(hwnd) and not ex & 0x80 and not ex & 0x8000000   # TOOLWINDOW, NOACTIVATE
                    and self.u.GetWindowTextLengthW(hwnd) and not self.is_game(hwnd)):
                found.append(hwnd)
                return False
            return True
        cb = proto(visit)
        self.u.EnumWindows(cb, 0)
        return found[0] if found else None

    def _wait_fg(self, done, seconds):
        end = time.perf_counter() + seconds
        while True:
            fg = self.u.GetForegroundWindow()
            if done(fg) or time.perf_counter() > end:
                return fg
            time.sleep(0.002)

    def push_behind(self, game):
        # HWND_BOTTOM; NOSIZE | NOMOVE | NOACTIVATE | NOOWNERZORDER | ASYNCWINDOWPOS: a busy game thread cannot block the guard
        self.u.SetWindowPos(game, 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0200 | 0x4000)

    # ---- the methods: each returns a short note; success is judged by the foreground afterwards
    def _by_attach(self, fg, target, with_foreground=False):
        me = self.k.GetCurrentThreadId()
        threads = {t for t in (self.thread_of(fg) if with_foreground else 0, self.thread_of(target)) if t and t != me}
        attached = [t for t in threads if self.u.AttachThreadInput(me, t, True)]
        try:
            self.u.BringWindowToTop(target)
            self.u.SetForegroundWindow(target)
        finally:
            for t in attached:
                self.u.AttachThreadInput(me, t, False)
        self._wait_fg(lambda f: f == target, 0.05 if with_foreground else 0.02)
        return f"attached {len(attached)}/{len(threads)}"

    def _by_attach_both(self, fg, target):
        return self._by_attach(fg, target, with_foreground=True)

    def _by_switch(self, fg, target):
        self.u.SwitchToThisWindow(target, True)
        self._wait_fg(lambda f: f == target, 0.05)
        return ""

    def _by_minimize(self, fg, target):
        game = fg
        self._last_min = time.perf_counter()
        self._minimized = game
        note = ""
        try:
            self.u.ShowWindowAsync(game, 6)        # SW_MINIMIZE: the system activates the next window in Z order
            now = self._wait_fg(lambda f: f and not self.is_game(f), 0.5)
            if target and now and not self.is_game(now) and now != target:
                note = f"Windows chose {self.describe(now)}; "
                self._by_attach(now, target)
        finally:
            self._restore(game)
        if self.u.IsIconic(game):
            note += "STILL MINIMISED"
        return note + "restored without activation"

    def _restore(self, game):
        self.u.ShowWindowAsync(game, 4)            # SW_SHOWNOACTIVATE: back to its size, not activated
        end = time.perf_counter() + 2
        while self.u.IsIconic(game) and time.perf_counter() < end:
            time.sleep(0.005)
        self.push_behind(game)
        if not self.u.IsIconic(game):
            self._minimized = None

    # ---- the watch
    def tick(self):
        """One check; the thread of start() calls it every 20 ms and on every foreground change."""
        with self._lock:
            self._check()

    def _check(self):
        fg = self.u.GetForegroundWindow()
        if not fg:
            if not self._no_fg:
                self._no_fg = True
                self.write("no foreground window")
            return
        self._no_fg = False
        if not self.is_game(fg):
            if self._hold:
                self._close_hold(fg)
            if fg != self.prev and fg != self.landed:
                self.prev, self.landed = fg, None
                self.write(f"foreground now {self.describe(fg)}: remembered as the window to give back to")
            return
        now = time.perf_counter()
        if not self._hold:
            self.taken += 1
            idle = self.idle_ms()
            self._hold = {"n": self.taken, "t": now, "window": int(fg), "attempts": 0, "tried": [], "next": now,
                          "user_input_ms": idle, "logged": now}
            why = ""
            if idle < 500:
                why = (f"; the user's own input {idle} ms before it (a click into the game?): given back anyway, "
                       f"automated runs stay unfocused (CLAUDE.md)")
            self.write(f"the game took the foreground (#{self.taken}) {self.describe(fg)}{why}")
        hold = self._hold
        if now < hold["next"]:
            return
        target = self.prev if self.prev and self.u.IsWindow(self.prev) else None
        if not target:
            target = self.next_window()
            if target and not hold.get("next_logged"):
                hold["next_logged"] = True
                self.write(f"  #{hold['n']}: the remembered window is gone; giving it to the next window in Z order {self.describe(target)}")
        hold["attempts"] += 1
        for name in self.methods:
            if name != "minimize" and not target:
                continue            # nothing to give back to: only the minimise hands the foreground to the next window
            if name == "minimize" and now - self._last_min < self.MIN_GAP:
                continue
            t0 = time.perf_counter()
            note = getattr(self, "_by_" + name)(fg, target)
            after = self.u.GetForegroundWindow()
            ms = (time.perf_counter() - t0) * 1000
            ok = bool(after) and not self.is_game(after)
            hold["tried"].append(f"{name} {'ok' if ok else 'refused'} {ms:.0f} ms{(' (' + note + ')') if note else ''}")
            if ok:
                hold["method"] = name
                if not self.prev or not self.u.IsWindow(self.prev):
                    self.prev = after
                elif after != self.prev:
                    self.landed = after
                break
        else:
            self.push_behind(fg)
            hold["next"] = time.perf_counter() + 0.1       # every 100 ms while Windows refuses everything
            if hold["attempts"] == 1 or time.perf_counter() - hold["logged"] > 5:
                hold["logged"] = time.perf_counter()
                self.write(f"  #{hold['n']} still in the game after {(time.perf_counter() - hold['t']) * 1000:.0f} ms, "
                           f"attempt {hold['attempts']}: " + "; ".join(hold["tried"][-len(self.methods):]))
            return
        self.push_behind(fg)
        self._close_hold(self.u.GetForegroundWindow())

    def _close_hold(self, fg):
        hold, self._hold = self._hold, None
        ms = (time.perf_counter() - hold["t"]) * 1000
        method = hold.get("method", "none of ours (the foreground moved by itself)")
        if "method" in hold:
            self.given += 1
        self.write(f"  #{hold['n']} given back to {self.describe(fg)} by {method} in {ms:.0f} ms, attempts {hold['attempts']}"
                   + (f"; tried: {'; '.join(hold['tried'])}" if hold["tried"] else ""))
        self.events.append(dict(hold, back=time.perf_counter(), ms=ms, to=int(fg), method=method,
                                to_prev=bool(self.prev) and fg == self.prev))

    def _run(self):
        ctypes, wt = self.ctypes, self.wt
        proto = ctypes.WINFUNCTYPE(None, wt.HANDLE, wt.DWORD, wt.HWND, ctypes.c_long, ctypes.c_long, wt.DWORD, wt.DWORD)

        def on_foreground(*_):
            self._flag = True
        self._callback = proto(on_foreground)
        hook = self.u.SetWinEventHook(3, 3, None, ctypes.cast(self._callback, ctypes.c_void_p), 0, 0, 0)  # EVENT_SYSTEM_FOREGROUND
        msg = (ctypes.c_byte * 64)()
        failed = False
        try:
            while not self._stop.is_set():
                self.u.MsgWaitForMultipleObjects(0, None, False, int(self.poll * 1000), 0x04FF)   # QS_ALLINPUT
                while self.u.PeekMessageW(msg, None, 0, 0, 1):    # PM_REMOVE
                    self.u.TranslateMessage(msg)
                    self.u.DispatchMessageW(msg)
                self._flag = False
                try:
                    self.tick()
                except Exception as e:      # never let the guard die silently
                    if not failed:
                        failed = True
                        self.write(f"focus guard error: {e!r}")
        finally:
            if hook:
                self.u.UnhookWinEvent(hook)

    def start(self):
        self._thread = self.threading.Thread(target=self._run, name="focus-guard", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(5)
        with self._lock:
            if self._minimized and self.u.IsWindow(self._minimized) and self.u.IsIconic(self._minimized):
                self._restore(self._minimized)
        self.write(f"focus guard stopped: the game took the foreground {self.taken} times, given back {self.given}")


def game_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Warhammer3.exe", "/NH"], capture_output=True, text=True).stdout
    return "Warhammer3.exe" in out


def busy_reasons():
    reasons = []
    if game_running():
        reasons.append("Warhammer3.exe is running")
    reasons += shared_game.busy_reasons()
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
    ap.add_argument("--low", action="store_true", help="low graphics, a small window")
    args = ap.parse_args(argv)

    if args.low:
        GRAPHICS.update(x_res=1280, y_res=720, gfx_aa=0, gfx_texture_quality=0, gfx_unit_quality=0, gfx_shadow_quality=0,
                        gfx_sky_quality=0, gfx_terrain_quality=0, gfx_lighting_quality=0, gfx_effects_quality=0)
    busy = busy_reasons()
    if busy:
        print("BUSY, not launching:", "; ".join(busy))
        return 3
    manifest = json.loads((PACK_DIR / "manifest.json").read_text(encoding="utf-8"))
    source = PACK_DIR / manifest["pack"]
    if sha(source) != manifest["pack_sha256"]:
        raise SystemExit("pack differs from its manifest: build again")
    if args.dry_run:
        print("\n".join(shared_game.describe()))
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

    lock = shared_game.take_lock()
    process = None
    guard = None
    status = "setup_failed"
    started = time.time()
    try:
        shutil.copy(source, pack_path)
        modlist.write_bytes(mod_text.encode())
        set_prefs()
        arguments = f"game_startup_mode battle {manifest['scenario']}; {MODLIST_NAME};"
        info = subprocess.STARTUPINFO()
        info.dwFlags = subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = 4    # SW_SHOWNOACTIVATE: do not take the focus from whatever the user is doing
        process = subprocess.Popen(f'"{GAME / "Warhammer3.exe"}" {arguments}', cwd=GAME, startupinfo=info)
        guard = FocusGuard(process.pid, run / "window.log").start()      # its own thread for the whole run
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
        if guard is not None:
            guard.stop()
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
            cleanup["lock_removed"] = shared_game.release_lock(lock)
        else:
            cleanup["lock"] = "kept: a game is still in tasklist"
        (run / "status.json").write_text(json.dumps(cleanup, indent=1), encoding="utf-8")
        print("finished:", json.dumps(cleanup), "run:", run, flush=True)
    return 0 if status == "completed" else 1


# The game is always closed by stop_own_game in the finally above: after a result, an error, a timeout,
# a stop flag or an exception in this script. Only the PID this script started is touched.


if __name__ == "__main__":
    sys.exit(main())
