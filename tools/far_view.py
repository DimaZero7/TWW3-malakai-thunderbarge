"""Far views of the barge in a running battle session: the camera aims at a seat's real position, not at a guess from the unit's bearing.

  py -3.14 tools/far_view.py standard LABEL             the set of data/crew_cycle.json, key far_views
  py -3.14 tools/far_view.py sweep NAME --seat ap_captain --az -25 --el 15 --dists 40,90,200 [--frame 12 | --fov 40]
  py -3.14 tools/far_view.py burst NAME --seat ap_captain --az -25 --el 15 --dist 90 [--frame 12 | --fov 40] [--n 8] [--gap 0.2]

--frame keeps the same part of the barge in the picture at every distance (a long lens), so pictures compare; --fov is the player's own lens.
Burst: close successive frames with a still camera. The share of changed pixels between neighbours goes to burst.txt in the run folder:
a level of detail that blinks gives one frame far from the others. Only PrintWindow.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import capture  # noqa: E402
import crew_lua  # noqa: E402
import rc  # noqa: E402

CROP = 420      # the middle of the picture, where the camera aims


def fov_for(dist, frame):
    return round(2 * math.degrees(math.atan(frame / 2 / dist)), 3)


def aim(seat, az, el, dist, fov):
    # The barge keeps drifting towards its target: stopped again at every aim. Aimed twice, the second time right before the picture.
    row = crew_lua.run(f'if _G.mtb_crew_uc then _G.mtb_crew_uc:halt() end; return C.camera_seat("{seat}", {dist}, {az}, {el}, {fov})', 10)
    if not row["ok"]:
        raise RuntimeError(str(row["result"]))
    return row["result"]


def picture(name):
    s = rc.state()
    capture.unminimize_behind(s["pid"])     # a minimized window paints nothing; it comes back without activation
    hwnd = capture.find_window(s["pid"])
    if not hwnd:
        raise RuntimeError("no window")
    path = Path(s["run"]) / f"{name}.png"
    capture.save_shot(hwnd, path, (s["x_res"], s["y_res"]))
    return path


def sweep(name, seat, az, el, dists, frame=None, fov=None, settle=1.2):
    for dist in dists:
        aim(seat, az, el, dist, fov or fov_for(dist, frame))
        time.sleep(settle)
        aim(seat, az, el, dist, fov or fov_for(dist, frame))
        time.sleep(0.25)
        picture(f"{name}_{dist}")


def middle(s, px, w, h):
    x0, y0 = (w - CROP) // 2, (h - CROP) // 2
    return b"".join(px[(y0 + y) * w * 4 + x0 * 4:(y0 + y) * w * 4 + (x0 + CROP) * 4] for y in range(CROP))


def changed(a, b):
    """Share of pixels of the middle that differ by more than 24 in a channel."""
    total = hits = 0
    for i in range(0, len(a) - 3, 4 * 3):
        total += 1
        if abs(a[i] - b[i]) > 24 or abs(a[i + 1] - b[i + 1]) > 24 or abs(a[i + 2] - b[i + 2]) > 24:
            hits += 1
    return hits / max(total, 1)


def burst(name, seat, az, el, dist, frame=None, fov=None, n=8, gap=0.2, settle=1.5):
    s = rc.state()
    aim(seat, az, el, dist, fov or fov_for(dist, frame))
    time.sleep(settle)
    hwnd = capture.find_window(s["pid"])
    size = (s["x_res"], s["y_res"])
    frames = []
    begin = time.time()
    for _ in range(n):
        for _try in range(5):       # PrintWindow sometimes gives an all black frame: that is the capture, not the game
            try:
                w, h, px = capture.grab(hwnd)
            except OSError:         # PrintWindow fails now and then
                time.sleep(0.2)
                hwnd = capture.find_window(s["pid"]) or hwnd
                continue
            if w >= size[0] and h >= size[1]:
                px, w, h = capture.crop(w, px, size[0], size[1]), size[0], size[1]
            if capture.black_share(px) < 0.2:
                break
            time.sleep(0.03)
        frames.append((round(time.time() - begin, 2), w, h, px))
        time.sleep(gap)
    run = Path(s["run"])
    middles = [middle(s, f[3], f[1], f[2]) for f in frames]
    steps = [round(changed(middles[i], middles[i + 1]), 4) for i in range(n - 1)]
    firstlast = round(changed(middles[0], middles[-1]), 4)
    line = f"{name} dist={dist} times={[f[0] for f in frames]} neighbours={steps} first_last={firstlast}"
    with (run / "burst.txt").open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line, flush=True)
    worst = max(range(n - 1), key=lambda i: steps[i])
    for i in (worst, worst + 1):
        t, w, h, px = frames[i]
        (run / f"{name}_{dist}_f{i}.png").write_bytes(capture._png(w, h, px))
    return steps


def standard(label, key="far_views"):
    """A set of data/crew_cycle.json. The file is read at each call, so a session on hold takes a corrected camera."""
    spec = json.loads((REPO / "data" / "crew_cycle.json").read_text(encoding="utf-8"))[key]
    rc.send("bm:enable_cinematic_ui(true, true, false); return 1", 8)       # no panels in the pictures
    for view in spec["views"]:
        name = f'{label}_{view["name"]}'
        sweep(name, view["seat"], view["az"], view["el"], view.get("dists", spec["dists"]), view.get("frame"), view.get("fov"))
        for dist in view.get("burst", []):
            burst(name + "_burst", view["seat"], view["az"], view["el"], dist, view.get("frame"), view.get("fov"), spec["burst_n"], spec["burst_gap"])
    rc.send("bm:enable_cinematic_ui(false, true, false); return 1", 8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["standard", "sweep", "burst"])
    ap.add_argument("name")
    ap.add_argument("--seat", default="ap_captain")
    ap.add_argument("--az", type=float, default=-25)
    ap.add_argument("--el", type=float, default=15)
    ap.add_argument("--dists", default="40,90,200")
    ap.add_argument("--dist", type=float, default=90)
    ap.add_argument("--frame", type=float)
    ap.add_argument("--fov", type=float)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--gap", type=float, default=0.2)
    a = ap.parse_args()
    if a.what == "standard":
        standard(a.name)
    elif a.what == "sweep":
        sweep(a.name, a.seat, a.az, a.el, [float(x) for x in a.dists.split(",")], a.frame, a.fov)
    else:
        burst(a.name, a.seat, a.az, a.el, a.dist, a.frame, a.fov, a.n, a.gap)


if __name__ == "__main__":
    main()
