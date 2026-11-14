"""Proves tools/run_battle.py's FocusGuard without the game: a stand-in window (tools/tests/focus_standin.py) takes the foreground
the way the game does, the guard gives it back to a "user's" window. Only windows this test creates are shown, activated, minimised
or closed; only the PIDs it started are ended. No keys or mouse are sent.

  py -3.14 tools/tests/focus_guard_test.py [--only attach,minimize] [--seconds 9]

Per trial (one guard method, or the guard's default order, or none): the user's window comes up and takes the foreground, the stand-in
starts with SW_SHOWNOACTIVATE like Warhammer3.exe, takes the foreground at 1.5, 4 and 6.5 s (bursts of three) and recreates its window
at 5.2 s. Sampled every 10 ms: who has the foreground, whether the stand-in is minimised; every 0.4 s a PrintWindow picture of it
(tools/capture.py, as the sessions take them). Results: build/focus_guard_test/<time>/results.json, each guard's window.log, a table.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
import capture  # noqa: E402
import run_battle as rb  # noqa: E402

STANDIN = Path(__file__).with_name("focus_standin.py")
u = ctypes.WinDLL("user32", use_last_error=True)
for f, res, args in [(u.GetForegroundWindow, wt.HWND, []), (u.GetWindowThreadProcessId, wt.DWORD, [wt.HWND, ctypes.POINTER(wt.DWORD)]),
                     (u.IsIconic, wt.BOOL, [wt.HWND]), (u.IsWindowVisible, wt.BOOL, [wt.HWND]), (u.IsWindow, wt.BOOL, [wt.HWND])]:
    f.restype, f.argtypes = res, args


class TestGuard(rb.FocusGuard):
    def _by_bottom(self, fg, target):       # a candidate only: the game under the other windows, the foreground left alone
        self.push_behind(fg)
        self._wait_fg(lambda f: f == target, 0.05)
        return ""

    def _by_x(self, fg, target, game=True, mine=True, bring=True):
        me = self.k.GetCurrentThreadId()
        threads = {t for t in (self.thread_of(fg) if game else 0, self.thread_of(target) if mine else 0) if t and t != me}
        attached = [t for t in threads if self.u.AttachThreadInput(me, t, True)]
        try:
            self.u.SetForegroundWindow(target)
            if bring:
                self.u.BringWindowToTop(target)
        finally:
            for t in attached:
                self.u.AttachThreadInput(me, t, False)
        self._wait_fg(lambda f: f == target, 0.05)
        return f"attached {len(attached)}/{len(threads)}"

    def _by_gamenobring(self, fg, target):
        return self._by_x(fg, target, mine=False, bring=False)

    def _by_bothnobring(self, fg, target):
        return self._by_x(fg, target, bring=False)

    def _by_bothafter(self, fg, target):
        return self._by_x(fg, target)

    def _by_old(self, fg, target):          # the guard of run 20261114-222543, as it was: checked at once, attached to the game only
        note = "plain"
        if not (self.u.SetForegroundWindow(target) and self.u.GetForegroundWindow() == target):
            note = "attach to the game's thread"
            me, game_thread = self.k.GetCurrentThreadId(), self.thread_of(fg)
            attached = bool(self.u.AttachThreadInput(me, game_thread, True))
            try:
                self.u.SetForegroundWindow(target)
            finally:
                if attached:
                    self.u.AttachThreadInput(me, game_thread, False)
        at_once = self.u.GetForegroundWindow() == target
        later = self._wait_fg(lambda f: f == target, 0.2) == target
        return f"{note}; at once {'yes' if at_once else 'NO'}, within 200 ms {'yes' if later else 'no'}"


def owner(hwnd):
    pid = wt.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def windows_of(pid):
    found = []
    proto = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def visit(hwnd, _):
        if owner(hwnd) == pid and u.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True
    u.EnumWindows(proto(visit), 0)
    return found


def start(role, events, seconds, show=4, extra=()):
    info = subprocess.STARTUPINFO()
    info.dwFlags = subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = show
    return subprocess.Popen([sys.executable, str(STANDIN), "--role", role, "--events", str(events), "--seconds", str(seconds), *extra],
                            startupinfo=info)


class Helped:
    """The stand-in started by a short-lived helper process that exits at once: a launch the game cannot inherit our rights from?"""

    def __init__(self, events, seconds, extra):
        code = ("import subprocess,sys;i=subprocess.STARTUPINFO();i.dwFlags=subprocess.STARTF_USESHOWWINDOW;i.wShowWindow=4;"
                "p=subprocess.Popen(sys.argv[1:],startupinfo=i,creationflags=0x8);print(p.pid)")   # DETACHED_PROCESS
        argv = [sys.executable, str(STANDIN), "--role", "game", "--events", str(events), "--seconds", str(seconds), *extra]
        self.pid = int(subprocess.run([sys.executable, "-c", code, *argv], capture_output=True, text=True).stdout.strip())
        self.handle = ctypes.windll.kernel32.OpenProcess(0x00100000 | 0x1000 | 0x0001, False, self.pid)  # SYNCHRONIZE|QUERY|TERMINATE

    def poll(self):
        return None if ctypes.windll.kernel32.WaitForSingleObject(self.handle, 0) == 0x102 else 0

    def kill(self):
        ctypes.windll.kernel32.TerminateProcess(self.handle, 1)


def read_events(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()] if Path(path).exists() else []


def trial(name, methods, out, seconds, hang=0.0, switch_at=None, via_helper=False):
    folder = out / name
    folder.mkdir()
    user = start("user", folder / "user.jsonl", seconds + 6, show=1)
    end = time.perf_counter() + 3
    user_hwnd = None
    while time.perf_counter() < end:
        w = windows_of(user.pid)
        fg = u.GetForegroundWindow()
        if w and fg in w:
            user_hwnd = fg
            break
        time.sleep(0.01)
    if user_hwnd is None:
        user.kill()
        return {"trial": name, "error": "the user's stand-in window could not take the foreground"}
    time.sleep(0.3)
    t_launch = time.perf_counter()
    extra = ("--recreate", "5.2", "--hang", str(hang))
    game = Helped(folder / "game.jsonl", seconds, extra) if via_helper else start("game", folder / "game.jsonl", seconds, extra=extra)
    guard = TestGuard(game.pid, folder / "window.log", methods=methods).start() if methods else None
    samples, shots, last_hash = [], [], None
    next_shot = time.perf_counter() + 0.5
    user2, user2_hwnd = None, None
    while game.poll() is None and time.perf_counter() - t_launch < seconds + 3:
        now = time.perf_counter()
        if switch_at and user2 is None and now - t_launch > switch_at:     # "the user clicks another app": a second window of ours
            user2 = start("user", folder / "user2.jsonl", seconds + 4, show=1)
        if user2 is not None and user2_hwnd is None:
            w2 = windows_of(user2.pid)
            user2_hwnd = w2[0] if w2 else None
        fg = u.GetForegroundWindow()
        ws = windows_of(game.pid)
        iconic = any(u.IsIconic(w) for w in ws)
        samples.append((now, owner(fg) == game.pid if fg else False, fg in (user_hwnd, user2_hwnd), iconic, bool(ws)))
        if now >= next_shot and ws:
            next_shot = now + 0.4
            hwnd = ws[0]
            try:
                w, h, px = capture.grab(hwnd)
                digest = hashlib.md5(px).hexdigest()
                shots.append({"t": now - t_launch, "ok": True, "iconic": bool(u.IsIconic(hwnd)), "black": round(capture.black_share(px), 3),
                              "changed": digest != last_hash, "size": [w, h]})
                last_hash = digest
            except OSError as e:
                shots.append({"t": now - t_launch, "ok": False, "iconic": bool(u.IsIconic(hwnd)), "error": str(e)})
        time.sleep(0.01)
    if guard:
        guard.stop()
    if game.poll() is None:
        game.kill()
    user.kill()
    user.wait(5)
    if user2 is not None:
        user2.kill()
        user2.wait(5)
    ev = read_events(folder / "game.jsonl")
    takes = [e for e in ev if e["e"] == "take"]
    took = [e for e in takes if e["ok"]]
    # how long the stand-in held the foreground: the 10 ms samples
    held = sum(b[0] - a[0] for a, b in zip(samples, samples[1:]) if a[1])
    runs, cur = [], None
    for s in samples:
        if s[1] and cur is None:
            cur = s[0]
        if not s[1] and cur is not None:
            runs.append((s[0] - cur) * 1000)
            cur = None
    if cur is not None:
        runs.append((samples[-1][0] - cur) * 1000)
    iconic_time = sum(b[0] - a[0] for a, b in zip(samples, samples[1:]) if a[3])
    frames = [e["n"] for e in ev if e["e"] == "frames"]
    steps = [b - a for a, b in zip(frames, frames[1:])]
    first_window = next((e for e in ev if e["e"] == "window"), {})
    gev = guard.events if guard else []
    result = {
        "trial": name, "methods": list(methods),
        "first_show_took_foreground": first_window.get("fg"),
        "standin_take_calls": len(takes), "standin_takes_ok": len(took), "standin_takes_how": sorted({e["how"] for e in took}),
        "guard_takes": len(gev), "given_back_to_user": sum(1 for e in gev if e["to_prev"]),
        "given_back_to_second_window": sum(1 for e in gev if user2_hwnd and e["to"] == int(user2_hwnd)) if switch_at else None,
        "give_back_ms": [round(e["ms"]) for e in gev], "methods_used": [e["method"] for e in gev],
        "foreground_runs_ms": [round(r) for r in runs], "held_total_ms": round(held * 1000),
        "user_has_foreground_at_end": samples[-1][2] if samples else None,
        "minimised_total_ms": round(iconic_time * 1000), "minimised_at_end": samples[-1][3] if samples else None,
        "printwindow": {"shots": len(shots), "ok": sum(s["ok"] for s in shots), "not_black": sum(s.get("black", 1) < 0.5 for s in shots),
                        "changed": sum(s.get("changed", False) for s in shots), "while_minimised": [s for s in shots if s["iconic"]]},
        "frames_per_half_second_min": min(steps) if steps else None, "frames_total": frames[-1] if frames else None,
        "standin_minimised_events": sum(1 for e in ev if e["e"] == "size" and e["kind"] == "minimised"),
    }
    (folder / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--seconds", type=float, default=9)
    a = ap.parse_args()
    trials = [("none", ()), ("old", ("old",)), ("bottom", ("bottom",)), ("attach", ("attach",)), ("attach_both", ("attach_both",)),
              ("switch", ("switch",)), ("minimize", ("minimize",)), ("default", rb.FocusGuard.ORDER)]
    # the same with a stand-in whose window thread sleeps 1 s after each burst, as a game loading a campaign or battle
    trials += [(n + "_hung", m) for n, m in trials if n != "bottom"]
    trials += [("default_switch", rb.FocusGuard.ORDER), ("none_helper", ())]
    trials += [(n + h, (n,)) for n in ("gamenobring", "bothnobring", "bothafter") for h in ("", "_hung")]
    if a.only:
        trials = [t for t in trials if t[0] in a.only.split(",")]
    out = REPO / "build" / "focus_guard_test" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    original = u.GetForegroundWindow()
    results = []
    for name, methods in trials:
        r = trial(name, methods, out, a.seconds, hang=1.0 if name.endswith("_hung") else 0.0,
                  switch_at=3.0 if name.endswith("_switch") else None, via_helper=name.endswith("_helper"))
        results.append(r)
        print(json.dumps(r, ensure_ascii=False), flush=True)
        time.sleep(0.5)
    # the foreground back to the window that had it before the test (no window of ours is left)
    back = TestGuard(-1, out / "restore.log", methods=("attach", "switch"))
    fg = u.GetForegroundWindow()
    if original and u.IsWindow(original) and fg != original:
        back._by_attach(fg, original)
    restored = u.GetForegroundWindow() == original
    (out / "results.json").write_text(json.dumps({"results": results, "original_foreground_restored": restored}, indent=1),
                                      encoding="utf-8")
    print(f"\n{'trial':10} {'takes ok':>8} {'given back':>10} {'give-back ms':>18} {'held ms':>8} {'min ms':>7} {'shots ok/changed':>16}  methods")
    for r in results:
        if "error" in r:
            print(f"{r['trial']:10} {r['error']}")
            continue
        pw = r["printwindow"]
        print(f"{r['trial']:10} {r['standin_takes_ok']:>4}/{r['standin_take_calls']:<3} {r['given_back_to_user']:>4}/{r['guard_takes']:<5} "
              f"{','.join(map(str, r['give_back_ms'])):>18} {r['held_total_ms']:>8} {r['minimised_total_ms']:>7} "
              f"{pw['ok']:>6}/{pw['changed']:<9}  {','.join(r['methods_used'])}")
    print("original foreground restored:", restored, "| results:", out)


if __name__ == "__main__":
    main()
