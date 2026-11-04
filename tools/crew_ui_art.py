"""Draws the crew panel's art: a flat dwarf engineer's sketch of the Spirit of Grungni, in the look of the game's own ui/eventpics/dwf/spirit_of_grungni.png.

  py -3.10 tools/crew_ui_art.py            all pictures into data/ui/ and their places into data/crew_ui_art.json
  py -3.10 tools/crew_ui_art.py --preview  also build/crew_ui/preview.png: every part on, one group selected

Python 3.10 because of numpy, scipy and Pillow; the pictures are kept in the repository, so tools/build.py does not need them. The line work is
SVG written here and painted by headless Chrome, with its own empty profile in build/crew_ui. Layers:
  blueprint.png        parchment and ink: the barge with its bays empty, construction lines, side sketches, the leader lines of the callouts
  occ_<group>.png      what stands in a group's bay when it is not empty (riflemen, barrels, domes, bombs, deck crew)
  sel_<group>.png      the red chalk over a group's bay when it is the selected one
  plate.png, row.png   frames in the game's dark steel and copper; icon_button.png: the icon of the button in the HUD
Coordinates in this file are those of the panel's scheme, DRAW_W x DRAW_H; pictures are painted at SCALE times that, the size they have on a 2560 x 1440
screen with the UI at 1.6. The plates of the callouts are live components, tools/crew_options.py hands their places to src/tww3_mtb_crew_ui.lua.
"""
import argparse
import json
import math
import random
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "ui"
TEMP = REPO / "build" / "crew_ui"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
DRAW_W, DRAW_H = 1040, 760
SCALE = 1.6
INK = "#3b2110"
INK_SOFT = "#5e3a1c"
PAPER = "#d7a667"         # occupies the lines under a part in the layers with alpha
COPPER = "#b5692e"
STEEL = "#4a4640"
PLATE_W, PLATE_H = 214, 70
# Where the callouts stand, top left corner, and the point of the drawing each one's line ends at.
# The places of the parts come from the game's model and seats (side view of dwf_thunderbarge_01 and seat positions read in a battle, bow to the left).
# Along the hull x = 246 + (8.3 - z) * 36, the balloon is shortened to fit the page. Heights: keel y = 598, 35 per model unit.
PLATES = {
    "cupolas": {"at": (14, 14), "to": (358, 50)},
    "harpoon": {"at": (14, 272), "to": (92, 181)},
    "cannons": {"at": (60, 672), "to": (339, 552)},
    "rifles": {"at": (370, 672), "to": (492, 456)},
    "bombs": {"at": (680, 672), "to": (656, 606)},
}
RNG = random.Random(1701)


def fmt(*numbers):
    return " ".join(f"{n:.1f}" for n in numbers)


def poly(points, close=False):
    out = "M" + " L".join(fmt(x, y) for x, y in points)
    return out + (" Z" if close else "")


def smooth(points, close=False):
    """Catmull-Rom through the points, as cubic Beziers."""
    pts = list(points)
    if close:
        pts = [pts[-1]] + pts + pts[:2]
    else:
        pts = [pts[0]] + pts + [pts[-1]]
    out = [f"M{fmt(*pts[1])}"]
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        out.append(f"C{fmt(*c1)} {fmt(*c2)} {fmt(*p2)}")
    return " ".join(out) + (" Z" if close else "")


def path(d, w=1.4, color=INK, fill="none", op=1.0, extra=""):
    return f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round" opacity="{op}" {extra}/>'


def shape(d, fill, op=1.0):
    return f'<path d="{d}" fill="{fill}" stroke="none" opacity="{op}"/>'


def circle(x, y, r, w=1.2, color=INK, fill="none", op=1.0):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" stroke="{color}" stroke-width="{w}" opacity="{op}"/>'


def dot(x, y, r=1.2, color=INK, op=1.0):
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}" opacity="{op}"/>'


def hatch(points, angle=60, gap=5.0, w=0.7, color=INK_SOFT, op=0.6, cid=[0]):
    """Parallel strokes clipped to a polygon, the way the shadows of the sketch are made."""
    cid[0] += 1
    name = f"h{cid[0]}"
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    diag = math.hypot(x1 - x0, y1 - y0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    a = math.radians(angle)
    dx, dy = math.cos(a), math.sin(a)
    nx, ny = -dy, dx
    lines = []
    t = -diag / 2
    while t < diag / 2:
        jitter = RNG.uniform(-gap * 0.18, gap * 0.18)
        ax, ay = cx + nx * (t + jitter) - dx * diag / 2, cy + ny * (t + jitter) - dy * diag / 2
        bx, by = cx + nx * (t + jitter) + dx * diag / 2, cy + ny * (t + jitter) + dy * diag / 2
        lines.append(f"M{fmt(ax, ay)} L{fmt(bx, by)}")
        t += gap
    return (f'<clipPath id="{name}"><path d="{poly(points, True)}"/></clipPath>'
            f'<path clip-path="url(#{name})" d="{" ".join(lines)}" stroke="{color}" stroke-width="{w}" fill="none" opacity="{op}"/>')


# ---------------- the outline of the ship ----------------
def hull_top(x):
    """The deck line at x: forecastle, waist, aftercastle."""
    pts = [(250, 414), (300, 410), (405, 414), (418, 430), (432, 450), (470, 454), (600, 452), (622, 436), (640, 404), (700, 396), (780, 394), (858, 396)]
    return interp(pts, x)


def hull_bottom(x):
    pts = [(246, 462), (254, 504), (274, 540), (312, 568), (364, 586), (470, 596), (620, 598), (760, 596), (812, 584), (846, 552), (864, 490), (866, 396)]
    return interp(pts, x)


def interp(pts, x):
    if x <= pts[0][0]:
        return pts[0][1]
    for (a, b), (c, d) in zip(pts, pts[1:]):
        if x <= c:
            return b + (d - b) * (x - a) / (c - a)
    return pts[-1][1]


def hull_outline():
    top = [(x, hull_top(x)) for x in range(250, 866, 8)]
    bow = [(866, 396), (867, 460), (864, 492), (848, 550), (814, 582), (762, 596), (620, 599), (470, 597), (364, 586), (312, 569), (274, 541), (254, 506), (246, 464), (246, 432)]
    return top + bow


def balloon_half(x):
    t = max(-1.0, min(1.0, (x - 530) / 402))
    return 134 * (1 - abs(t) ** 2.5) ** 0.60


def balloon():
    cy = 168
    xs = [128 + i * (804 / 90) for i in range(91)]
    upper = [(x, cy - balloon_half(x)) for x in xs]
    lower = [(x, cy + balloon_half(x)) for x in xs]
    outline = upper + lower[::-1]
    out = [shape(poly(outline, True), "#fff4e0")]
    # the shade of its lower side: wash and strokes
    shade = [(x, cy + balloon_half(x) * 0.42) for x in xs] + lower[::-1]
    out.append(shape(poly(shade, True), "#c88f55", 0.30))
    top_shade = [(x, cy - balloon_half(x)) for x in xs] + [(x, cy - balloon_half(x) * 0.70) for x in xs[::-1]]
    out.append(shape(poly(top_shade, True), "#c88f55", 0.14))
    out.append(hatch(shade, 58, 6.5, 0.8, INK_SOFT, 0.55))
    # long seams
    for f in (-0.82, -0.58, -0.32, -0.08, 0.16, 0.40, 0.62, 0.84):
        pts = [(x, cy + balloon_half(x) * f) for x in xs[3:-3]]
        out.append(path(smooth(pts[::3]), 0.8 + 0.3 * abs(f), INK, op=0.75))
    # ribs: bowed outward from the middle
    for t in (-0.80, -0.62, -0.44, -0.27, -0.10, 0.08, 0.26, 0.44, 0.62, 0.80):
        x = 530 + t * 402
        h = balloon_half(x)
        bulge = t * 46
        pts = [(x + bulge * (1 - s * s), cy + s * h) for s in [i / 12 for i in range(-12, 13)]]
        wide = abs(t) in (0.44, 0.27)
        out.append(path(smooth(pts), 2.2 if wide else 1.0, INK, op=0.9))
        if wide:    # straps with rivets
            pts2 = [(x + 7 + bulge * (1 - s * s), cy + s * h) for s in [i / 12 for i in range(-12, 13)]]
            out.append(path(smooth(pts2), 1.0, INK, op=0.85))
            for s in [i / 12 for i in range(-11, 12, 2)]:
                out.append(dot(x + 3.5 + bulge * (1 - s * s), cy + s * h, 1.1))
    # the wide belt along the lower side
    belt_a = [(x, cy + balloon_half(x) * 0.47) for x in xs[8:-8]]
    belt_b = [(x, cy + balloon_half(x) * 0.58) for x in xs[8:-8]]
    out.append(shape(poly(belt_a + belt_b[::-1], True), "#9a5a2a", 0.34))
    out.append(path(smooth(belt_a[::3]), 1.4))
    out.append(path(smooth(belt_b[::3]), 1.4))
    for i in range(0, len(belt_a), 3):
        out.append(dot((belt_a[i][0] + belt_b[i][0]) / 2, (belt_a[i][1] + belt_b[i][1]) / 2, 1.3))
    out.append(path(poly(outline, True), 2.4))
    out.append(path(poly(outline, True), 1.0, INK, op=0.6, extra='transform="translate(1.6,1.2)"'))
    # nose cap
    for dy in (-16, -8, 0, 8, 16):
        out.append(path(f"M128 168 Q 150 {168 + dy * 0.7:.1f} 178 {168 + dy * 3.2:.1f}", 0.9))
    out.append(path("M128 168 L116 168", 3.0))
    # tail: the stern runs on into a cone with a ring, the outline of the balloon goes on without a gap
    x0, h0 = 880, balloon_half(880)
    y_top, y_bottom = 168 - h0, 168 + h0
    cone = f"M{x0} {y_top:.1f} C 920 {y_top + 26:.1f} 952 {y_top + (152 - y_top) * 0.72:.1f} 972 152 L972 184 C 952 {y_bottom - (y_bottom - 184) * 0.72:.1f} 920 {y_bottom - 26:.1f} {x0} {y_bottom:.1f} Z"
    out.append(shape(cone, "#fff4e0"))
    out.append(hatch([(x0, 186), (972, 174), (972, 184), (x0, y_bottom)], 70, 4, 0.7))
    out.append(path(cone[:cone.rindex(" Z")], 2.4))
    out.append(path(f"M{x0} {y_top:.1f} Q {x0 + 12} 168 {x0} {y_bottom:.1f}", 1.5))
    for x in (905, 930, 952):
        half = (168 - y_top) + (152 - y_top - (168 - y_top)) * 0 - (x - x0) / (972 - x0) * (152 - y_top)
        out.append(path(f"M{x} {168 - half:.1f} Q {x + 6} 168 {x} {168 + half:.1f}", 0.8))
    fin_top = [(955, 136), (1006, 74), (1016, 92), (996, 138), (976, 156)]
    fin_bottom = [(955, 200), (1006, 262), (1016, 244), (996, 198), (976, 180)]
    for fin in (fin_top, fin_bottom):
        out.append(shape(poly(fin, True), "#fff4e0"))
        out.append(path(poly(fin, True), 1.7))
        out.append(hatch(fin, 25, 4.5, 0.7))
    out.append(path("M968 168 L1020 168", 2.2))
    out.append(shape("M1032 168 L1012 159 L1016 168 L1012 177 Z", INK))
    return out


def balloon_placed():
    return ['<g transform="translate(0 26) scale(1 0.92)">' + "".join(balloon()) + "</g>"]


def occ_harpoon():
    """The barbed spear on the balloon's nose, in the same place as balloon_placed() draws the balloon."""
    out = [path("M118 168 L60 168", 2.6), path("M118 171 L62 171", 1.0), shape("M46 169 L84 154 L74 169 L84 184 Z", "#e7c489"),
           path("M46 169 L84 154 L74 169 L84 184 Z", 1.8), hatch([(46, 169), (84, 154), (74, 169), (84, 184)], 80, 3, 0.7)]
    for i in range(3):
        x = 100 + i * 9
        out.append(path(f"M{x} 168 L{x - 8} 158 M{x} 170 L{x - 8} 180", 1.0))
    return ['<g transform="translate(0 26) scale(1 0.92)">' + "".join(out) + "</g>"]


def rigging():
    out = []
    # truss under the balloon
    out.append(shape("M330 298 L770 298 L770 318 L330 318 Z", "#fff4e0"))
    out.append(path("M326 300 L774 300 M326 318 L774 318", 2.0))
    x = 330
    up = True
    pts = []
    while x <= 770:
        pts.append((x, 301 if up else 317))
        up = not up
        x += 18
    out.append(path(poly(pts), 0.9))
    for hx in (340, 460, 580, 700):
        out.append(path(f"M{hx} 292 L{hx} 300 M{hx + 12} 292 L{hx + 12} 300", 1.3))
    # two rope nets down to the deck
    for (t0, t1, b0, b1, y_b) in ((352, 492, 420, 472, 448), (590, 770, 652, 736, 400)):
        n = 6
        rows = 7
        tops = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
        bots = [b0 + (b1 - b0) * i / n for i in range(n + 1)]
        for a, b in zip(tops, bots):
            sag = RNG.uniform(-1.5, 1.5)
            out.append(path(f"M{a:.1f} 318 Q {(a + b) / 2 + sag:.1f} {(318 + y_b) / 2:.1f} {b:.1f} {y_b}", 1.25))
        for r in range(1, rows + 1):
            f = r / (rows + 1)
            y = 318 + (y_b - 318) * f
            pts = [(a + (b - a) * f, y + (2 if i % 2 else -1)) for i, (a, b) in enumerate(zip(tops, bots))]
            out.append(path(smooth(pts), 1.0))
            for p in pts:
                out.append(circle(p[0], p[1], 1.5, 0.8, INK, "#fff4e0"))
    return out


def hull():
    out = []
    outline = hull_outline()
    out.append(shape(poly(outline, True), "#fff1dc"))
    # shade of the lower hull
    low = [(x, hull_top(x) + (hull_bottom(x) - hull_top(x)) * 0.62) for x in range(250, 866, 8)] + [(x, hull_bottom(x)) for x in range(866, 246, -8)]
    out.append(shape(poly(low, True), "#b8824c", 0.26))
    out.append(hatch(low, 52, 5.2, 0.8, INK_SOFT, 0.6))
    # planks
    for k in range(1, 9):
        f = k / 9
        pts = [(x, hull_top(x) + (hull_bottom(x) - hull_top(x)) * f) for x in range(252, 866, 12)]
        out.append(path(smooth(pts), 0.8, INK, op=0.72))
        # butt joints
        for x in range(262 + (k * 61) % 120, 860, 170):
            y = hull_top(x) + (hull_bottom(x) - hull_top(x)) * f
            y2 = hull_top(x) + (hull_bottom(x) - hull_top(x)) * (k + 1) / 9
            out.append(path(f"M{x} {y:.1f} L{x} {y2:.1f}", 0.6, INK, op=0.6))
    # wale with a rope pattern
    a = [(x, hull_top(x) + 14) for x in range(250, 866, 12)]
    b = [(x, hull_top(x) + 27) for x in range(250, 866, 12)]
    out.append(shape(poly(a + b[::-1], True), "#8f5a2c", 0.30))
    out.append(path(smooth(a), 1.5))
    out.append(path(smooth(b), 1.5))
    for x in range(256, 860, 8):
        y = hull_top(x) + 14
        out.append(path(f"M{x} {y + 13:.1f} L{x + 6} {y:.1f}", 0.7, INK, op=0.8))
    # shields along the side
    for i, x in enumerate(range(430, 671, 40)):      # seven on the model, overlapping
        y = 503
        out.append(circle(x, y, 22.5, 1.5, INK, "#fff1dc"))
        out.append(circle(x, y, 19, 0.7))
        out.append(circle(x, y, 4, 1.0, INK, INK_SOFT))
        if i % 3 == 0:
            out.append(path(f"M{x - 13} {y - 13} L{x + 13} {y + 13} M{x + 13} {y - 13} L{x - 13} {y + 13}", 2.4, INK_SOFT))
        elif i % 3 == 1:
            out.append(hatch([(x - 16, y), (x, y - 16), (x + 16, y), (x, y + 16)], 45, 3.5, 0.7))
        else:
            out.append(path(f"M{x - 5} {y - 12} L{x - 5} {y + 12} M{x - 5} {y - 12} L{x + 7} {y - 5} L{x - 5} {y} L{x + 7} {y + 6} L{x - 5} {y + 12}", 2.0, INK_SOFT))
    # portholes
    for (x, y) in ((300, 476),):
        out.append(circle(x, y, 13, 1.6, INK, "#fff1dc"))
        out.append(circle(x, y, 9, 1.0, INK, "#6d7f7c"))
        for a_ in range(0, 360, 45):
            out.append(dot(x + 11 * math.cos(math.radians(a_)), y + 11 * math.sin(math.radians(a_)), 0.9))
    out.append(path(poly(outline, True), 2.6))
    out.append(path(poly(outline, True), 1.0, INK, op=0.5, extra='transform="translate(1.4,1.4)"'))
    # the skid under the keel
    out.append(path("M352 612 L800 612 M352 618 L800 618", 1.6))
    out.append(path("M352 612 L340 615 L352 618", 1.4))
    for x in range(380, 800, 62):
        out.append(path(f"M{x} {hull_bottom(x) - 1:.1f} L{x} 612 M{x + 6} {hull_bottom(x + 6) - 1:.1f} L{x + 6} 612", 1.2))
    # stem post and the griffon's head above the forecastle: hooked beak, open jaw, swept crest
    out.append(shape("M250 432 C 248 416 256 404 266 392 L292 396 C 284 406 278 412 276 416 L250 432 Z", "#fff1dc"))
    out.append(path("M248 434 C 248 416 256 404 266 392", 2.3))
    out.append(path("M276 414 C 280 406 286 402 292 396", 1.8))
    head = ("M232 334 C 222 334 214 330 208 322 L198 328 C 192 324 188 318 188 312 L204 310 L192 304 C 184 308 176 306 172 300 "
            "C 178 286 192 276 208 276 C 216 262 232 248 262 240 C 256 250 254 256 252 262 C 262 254 276 250 288 252 C 280 260 274 268 270 276 "
            "C 276 274 284 274 290 276 C 280 284 272 292 268 302 C 270 314 266 326 256 334 Z")
    parts = [shape(head, "#fff1dc"), path(head, 2.8),
             path("M204 278 C 198 288 194 296 190 304", 1.3),
             path("M214 298 L240 288 C 240 296 228 302 214 298 Z", 1.6, INK, "#fff1dc"), dot(230, 294, 2.5), path("M208 292 L244 280", 3.2),
             path("M222 272 C 234 262 248 256 258 254 M234 276 C 246 268 260 262 276 258 M246 284 C 256 278 268 274 280 276 M238 316 C 244 316 252 312 258 302 M226 322 C 232 324 238 324 244 322", 1.2),
             hatch([(232, 334), (256, 334), (268, 304), (254, 290), (240, 306), (226, 322)], 40, 4.0, 0.8, INK_SOFT, 0.65)]
    out.append('<g transform="translate(278 392) scale(0.8) translate(-245 -334)">' + "".join(parts) + "</g>")
    # spine teeth along the bow
    for i, y in enumerate(range(434, 536, 18)):
        x = hull_outline_bow(y)
        out.append(shape(f"M{x:.1f} {y} L{x - 12:.1f} {y + 6} L{x:.1f} {y + 13} Z", "#fff1dc"))
        out.append(path(f"M{x:.1f} {y} L{x - 12:.1f} {y + 6} L{x:.1f} {y + 13}", 1.3))
    return out


def hull_outline_bow(y):
    pts = [(432, 246), (462, 246), (506, 254), (541, 274), (569, 312)]
    for (a, b), (c, d) in zip(pts, pts[1:]):
        if y <= c:
            return b + (d - b) * (y - a) / (c - a)
    return pts[-1][1]


def rear_parts():
    out = []
    # the boiler tower with its fire windows, at the stern
    out.append(shape("M762 396 L762 304 L836 304 L836 396 Z", "#fff1dc"))
    out.append(path("M762 398 L762 304 L836 304 L836 398", 2.2))
    for y in range(314, 358, 7):
        out.append(path(f"M760 {y} Q 799 {y + 5} 838 {y}", 1.3))
    out.append(shape("M756 304 L842 304 L836 292 L762 292 Z", "#fff1dc"))
    out.append(path("M756 304 L842 304 L836 292 L762 292 Z", 1.8))
    for x in (772, 790, 808, 826):
        out.append(shape(f"M{x - 5} 384 L{x - 5} 366 Q {x} 359 {x + 5} 366 L{x + 5} 384 Z", "#8c3b12", 0.75))
        out.append(path(f"M{x - 5} 384 L{x - 5} 366 Q {x} 359 {x + 5} 366 L{x + 5} 384 Z", 1.2))
    out.append(hatch([(820, 304), (836, 304), (836, 396), (820, 396)], 75, 3.5, 0.8))
    # the two short stacks and the great curved arm up to the balloon's tail, with a claw at its end
    out.append(path("M784 292 L784 262 M812 292 L812 266", 7, INK))
    out.append(path("M784 292 L784 262 M812 292 L812 266", 4, "#e8c692"))
    out.append(path("M800 292 C 822 264 866 246 926 226", 10, INK))
    out.append(path("M800 292 C 822 264 866 246 926 226", 6.5, "#e8c692"))
    out.append(shape("M922 220 L946 204 L942 218 L956 218 L942 228 L948 240 L928 232 Z", "#fff1dc"))
    out.append(path("M922 220 L946 204 L942 218 L956 218 L942 228 L948 240 L928 232 Z", 1.5))
    for x, y in ((846, 262), (880, 246)):
        out.append(path(f"M{x - 3} {y - 8} L{x + 3} {y + 8}", 1.4))
    # paddle wheel and gear at the stern
    gx, gy, gr = 846, 424, 34
    teeth = []
    for i in range(28):
        a = i * math.pi / 14
        r = gr + (5 if i % 2 == 0 else 0)
        teeth.append((gx + r * math.cos(a), gy + r * math.sin(a)))
    out.append(shape(poly(teeth, True), "#fff1dc"))
    out.append(path(poly(teeth, True), 1.6))
    out.append(circle(gx, gy, gr - 6, 1.0))
    out.append(circle(gx, gy, 7, 1.4, INK, "#8f5a2c"))
    for a_ in range(0, 360, 45):
        ca, sa = math.cos(math.radians(a_)), math.sin(math.radians(a_))
        out.append(path(f"M{gx + 7 * ca:.1f} {gy + 7 * sa:.1f} L{gx + (gr - 6) * ca:.1f} {gy + (gr - 6) * sa:.1f}", 1.5))
    # shaft and the two screws
    out.append(shape("M860 512 L918 516 L918 534 L860 538 Z", "#fff1dc"))
    out.append(path("M860 512 L918 516 L918 534 L860 538", 1.8))
    for x in (874, 888, 902):
        out.append(path(f"M{x} 513 L{x} 537", 1.2))
    out.append(hatch([(860, 528), (918, 528), (918, 534), (860, 538)], 80, 3, 0.8))
    for bx in (920, 942):
        blade = f"M{bx} 525 C {bx - 14} 500 {bx - 8} 478 {bx + 8} 468 C {bx + 14} 490 {bx + 10} 510 {bx + 2} 525 C {bx + 10} 540 {bx + 14} 560 {bx + 8} 582 C {bx - 8} 572 {bx - 14} 550 {bx} 525 Z"
        out.append(shape(blade, "#fff1dc"))
        out.append(path(blade, 1.6))
    out.append(path("M918 520 L958 525 L918 530", 2.0))
    out.append(hatch([(938, 525), (934, 500), (950, 470), (954, 500)], 20, 3.2, 0.7))
    out.append(hatch([(938, 525), (934, 550), (950, 580), (954, 550)], 160, 3.2, 0.7))
    # The great wooden fins stand on the hull's sides over the stern deck, arched at the top. Drawn as a see-through outline: the deck and its crew are behind them.
    fin = "M672 616 L672 352 C 672 330 694 314 716 314 C 738 314 760 330 760 352 L760 626 L716 626 Z"
    out.append(path(fin, 2.4, INK, op=0.85, extra='stroke-dasharray="11 3"'))
    for x in (690, 708, 726, 744):
        out.append(path(f"M{x} 330 L{x} 616", 0.8, INK, op=0.42))
    for y in (372, 560):
        out.append(path(f"M672 {y} L760 {y}", 2.2, INK, op=0.55))
        for x in (686, 716, 746):
            out.append(circle(x, y, 3.6, 1.0, INK, "#a87240", 0.7))
    out.append(hatch([(672, 600), (760, 600), (760, 626), (716, 626), (672, 616)], 72, 4.4, 0.8))
    return out


def malakai():
    """A small fixed figure at the wheel: he is always on board."""
    out = []
    x, y = 684, 372
    out.append(circle(x - 16, y + 8, 12, 1.6))
    for a_ in range(0, 360, 60):
        ca, sa = math.cos(math.radians(a_)), math.sin(math.radians(a_))
        out.append(path(f"M{x - 16:.1f} {y + 8:.1f} L{x - 16 + 12 * ca:.1f} {y + 8 + 12 * sa:.1f}", 1.0))
    out.append(shape(f"M{x - 5} {y + 28} L{x + 8} {y - 6} L{x + 19} {y + 28} Z", "#a84c1c", 0.9))
    out.append(path(f"M{x - 5} {y + 28} L{x + 8} {y - 6} L{x + 19} {y + 28}", 1.4))
    out.append(circle(x + 8, y - 12, 6, 1.2, INK, "#f1d5a8"))
    out.append(shape(f"M{x + 3} {y - 16} L{x + 8} {y - 34} L{x + 13} {y - 16} Z", "#c8501a"))
    out.append(path(f"M{x + 3} {y - 16} L{x + 8} {y - 34} L{x + 13} {y - 16}", 0.9))
    out.append(shape(f"M{x + 3} {y - 9} Q {x + 5} {y + 7} {x + 8} {y + 9} Q {x + 11} {y + 7} {x + 13} {y - 9} Z", "#c8501a"))
    return out


def bay_marks():
    """What stands in the drawing when a group is empty: a shut port, closed doors, the dashed places of the rings and of the pub."""
    out = []
    # the pub under the stern deck
    x0, y0, x1, y1 = PUB
    out.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" stroke="{INK}" stroke-width="1.2" stroke-dasharray="6 3"/>')
    return out


def mount_cannons():
    """Only the port: a round lid with rivets."""
    x, y = CANNON
    out = [circle(x, y, 17, 2.0, INK, "#d9a76a"), circle(x, y, 12, 1.2, INK, "#8f5a2c")]
    for a_ in range(0, 360, 45):
        out.append(dot(x + 14.5 * math.cos(math.radians(a_)), y + 14.5 * math.sin(math.radians(a_)), 1.0))
    return out


def mount_bombs():
    """Only the bomb doors in the bottom: a front pair and a rear pair, seen from the side as one each."""
    out = []
    for x0, x1 in BOMB_DOORS:
        y0, y1 = hull_bottom(x0), hull_bottom(x1)
        out.append(shape(poly([(x0, y0 - 10), (x1, y1 - 10), (x1, y1 + 1), (x0, y0 + 1)], True), "#d9a76a"))
        out.append(path(poly([(x0, y0 - 10), (x1, y1 - 10), (x1, y1 + 1), (x0, y0 + 1)], True), 1.7))
        out.append(path(f"M{(x0 + x1) / 2:.1f} {y0 - 10:.1f} L{(x0 + x1) / 2:.1f} {y1 + 1:.1f}", 1.1))
        for hx in (x0 + 4, x1 - 4):
            out.append(dot(hx, y0 - 5, 1.2))
    return out


def ring(x, y):
    top = y - 26
    out = [shape(f"M{x - 24} {top} L{x + 24} {top} L{x + 24} {y} Q {x} {y + 8} {x - 24} {y} Z", "#a06c38")]
    for dx in (-18, -9, 0, 9, 18):
        out.append(path(f"M{x + dx} {top + 2} L{x + dx} {y + (3 if abs(dx) < 10 else 1)}", 0.9))
    out.append(path(f"M{x - 24} {top} L{x - 24} {y} Q {x} {y + 8} {x + 24} {y} L{x + 24} {top}", 1.9))
    out.append(f'<ellipse cx="{x}" cy="{top + 1}" rx="25" ry="5" fill="#57504a" stroke="{INK}" stroke-width="1.7"/>')
    out.append(f'<ellipse cx="{x}" cy="{top + 1}" rx="18" ry="3" fill="#2a1a10"/>')
    return out


def mount_cupolas():
    """Only the crow's nests on the balloon, nobody in them."""
    return [p for x, y in CUPOLAS for p in ring(x, y)]


MOUNT = {"cannons": mount_cannons, "bombs": mount_bombs, "cupolas": mount_cupolas}
BOMB_DOORS = [(418, 480), (625, 687)]
CUPOLAS = [(382, 64), (668, 64)]
CANNON = (339, 552)
PUB = (672, 446, 816, 512)
RIFLE_PLACES = [(323, 411), (362, 412), (441, 454), (492, 454), (548, 454), (601, 452)]    # six on each side


def dwarf(x, y, scale=1.0, facing=-1, gun=True, helm="#4c3b28", beard="#9c4f20"):
    """A small dwarf from the chest up, behind the rail, with a long gun."""
    s = scale
    out = []
    if gun:
        out.append(path(f"M{x:.1f} {y - 8 * s:.1f} L{x + facing * 22 * s:.1f} {y - 14 * s:.1f}", 2.2 * s, INK))
    out.append(shape(f"M{x - 8 * s:.1f} {y:.1f} L{x - 7 * s:.1f} {y - 13 * s:.1f} L{x + 7 * s:.1f} {y - 13 * s:.1f} L{x + 8 * s:.1f} {y:.1f} Z", "#8a5428"))
    out.append(path(f"M{x - 8 * s:.1f} {y:.1f} L{x - 7 * s:.1f} {y - 13 * s:.1f} L{x + 7 * s:.1f} {y - 13 * s:.1f} L{x + 8 * s:.1f} {y:.1f}", 1.0 * s))
    out.append(shape(f"M{x - 5 * s:.1f} {y - 17 * s:.1f} L{x + 5 * s:.1f} {y - 17 * s:.1f} L{x + facing * 1 * s:.1f} {y - 5 * s:.1f} Z", beard))
    out.append(circle(x, y - 19 * s, 5 * s, 1.0 * s, INK, "#dcae74"))
    out.append(path(f"M{x - 6 * s:.1f} {y - 20 * s:.1f} A {6 * s:.1f} {6 * s:.1f} 0 0 1 {x + 6 * s:.1f} {y - 20 * s:.1f} Z", 1.0 * s, INK, helm))
    out.append(path(f"M{x - 6 * s:.1f} {y - 22 * s:.1f} Q {x - 10 * s:.1f} {y - 23 * s:.1f} {x - 9 * s:.1f} {y - 27 * s:.1f} M{x + 6 * s:.1f} {y - 22 * s:.1f} Q {x + 10 * s:.1f} {y - 23 * s:.1f} {x + 9 * s:.1f} {y - 27 * s:.1f}", 1.2 * s))
    return out


def occ_rifles():
    out = []
    for x, y in RIFLE_PLACES:
        out += dwarf(x, y + 2, 0.9)
    return out


def occ_cannons():
    out = []
    x, y = CANNON
    # the sponson and twin barrels, pointing down and forward
    out.append(path(f"M{x - 4} {y - 3} L{x - 66} {y + 36}", 13, INK))
    out.append(path(f"M{x - 4} {y - 3} L{x - 66} {y + 36}", 9.5, "#57504a"))
    out.append(path(f"M{x + 2} {y + 7} L{x - 58} {y + 46}", 13, INK))
    out.append(path(f"M{x + 2} {y + 7} L{x - 58} {y + 46}", 9.5, "#62594f"))
    for t in (0.25, 0.55, 0.92):
        ax, ay = x - 4 + (-62) * t, y - 3 + 39 * t
        out.append(path(f"M{ax - 4:.1f} {ay - 7:.1f} L{ax + 12:.1f} {ay + 15:.1f}", 3, COPPER))
    out.append(circle(x, y, 17, 2.0, INK, COPPER))
    out.append(circle(x, y, 8, 1.4, INK, "#57504a"))
    for a_ in range(0, 360, 45):
        out.append(dot(x + 13 * math.cos(math.radians(a_)), y + 13 * math.sin(math.radians(a_)), 1.0))
    return out


def occ_bombs():
    out = []
    for x0, x1 in BOMB_DOORS:
        cx = (x0 + x1) / 2
        top = hull_bottom(cx)
        # doors hanging open and a pair of bombs: left and right of the hull, seen from the side
        out.append(path(f"M{x0} {hull_bottom(x0):.1f} L{x0 + 5} {top + 22:.1f} M{x1} {hull_bottom(x1):.1f} L{x1 - 5} {top + 22:.1f}", 3.0, INK))
        for bx, by in ((cx - 13, top + 14), (cx + 13, top + 18)):
            out.append(shape(f"M{bx - 11:.1f} {by:.1f} A 11 11 0 1 1 {bx + 11:.1f} {by:.1f} A 11 11 0 1 1 {bx - 11:.1f} {by:.1f} Z", "#5b5247"))
            out.append(circle(bx, by, 11, 1.5))
            out.append(path(f"M{bx - 7:.1f} {by - 8:.1f} Q {bx:.1f} {by - 12:.1f} {bx + 7:.1f} {by - 8:.1f}", 1.0, "#cdb78f"))
            out.append(path(f"M{bx - 9:.1f} {by + 4:.1f} Q {bx:.1f} {by + 10:.1f} {bx + 9:.1f} {by + 4:.1f}", 1.3, COPPER))
            out.append(shape(f"M{bx - 4:.1f} {by + 10:.1f} L{bx + 4:.1f} {by + 10:.1f} L{bx + 7:.1f} {by + 19:.1f} L{bx - 7:.1f} {by + 19:.1f} Z", COPPER))
            out.append(path(f"M{bx - 4:.1f} {by + 10:.1f} L{bx + 4:.1f} {by + 10:.1f} L{bx + 7:.1f} {by + 19:.1f} L{bx - 7:.1f} {by + 19:.1f} Z", 1.0))
    return out


def occ_cupolas():
    """The model's cupolas: a wooden ring with an iron rim on top of the balloon, a dwarf standing in it."""
    out = []
    for x, y in CUPOLAS:
        out += ring(x, y)
        out += dwarf(x, y - 23, 0.95, -1, False, "#5b5247", "#b98a42")
    return out


def occ_deck():
    """The fireman and the lookout on the stern deck, the pub under it: the hull's side cut away, a table, benches, barrels, four men."""
    out = []
    out += dwarf(716, 396, 0.85, -1, False, "#5b5247", "#7f4a26")
    out += dwarf(742, 396, 0.85, 1, False, "#4c3b28", "#b98a42")
    x0, y0, x1, y1 = PUB
    out.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="#d9a76a" stroke="{INK}" stroke-width="1.9"/>')
    out.append(f'<rect x="{x0 + 1}" y="{y0 + 1}" width="{x1 - x0 - 2}" height="10" fill="#7a5128" opacity="0.65"/>')
    out.append(path(f"M{x0 + 2} {y1 - 7} L{x1 - 2} {y1 - 7}", 1.3))
    # lanterns
    for lx in (696, 752):
        out.append(path(f"M{lx} {y0} L{lx} {y0 + 12}", 1.0))
        out.append(circle(lx, y0 + 15, 3.4, 1.0, INK, "#e8a93e"))
    for dx, facing in ((692, 1), (712, -1)):
        out += dwarf(dx, y1 - 8, 0.72, facing, False, "#4c3b28", "#9c4f20")
    for dx, facing in ((728, 1), (748, -1)):
        out += dwarf(dx, y1 - 8, 0.72, facing, False, "#5b5247", "#b98a42")
    out.append(path(f"M686 {y1 - 16} L754 {y1 - 16}", 2.6))
    out.append(path(f"M694 {y1 - 16} L694 {y1 - 7} M746 {y1 - 16} L746 {y1 - 7}", 1.6))
    for bx, by in ((778, y1 - 8), (798, y1 - 8), (788, y1 - 26)):
        out.append(f'<ellipse cx="{bx}" cy="{by - 10}" rx="10" ry="12" fill="#a06c38" stroke="{INK}" stroke-width="1.3"/>')
        out.append(path(f"M{bx - 10} {by - 14} Q {bx} {by - 11} {bx + 10} {by - 14} M{bx - 10} {by - 6} Q {bx} {by - 3} {bx + 10} {by - 6}", 1.0))
    return out


def sel_shapes(group):
    if group == "rifles":
        return [(342, 397, 44, 28), (520, 438, 100, 28)]
    if group == "cannons":
        return [(310, 572, 48, 34)]
    if group == "bombs":
        return [((a + b) / 2, hull_bottom((a + b) / 2) + 8, (b - a) / 2 + 12, 30) for a, b in BOMB_DOORS]
    if group == "cupolas":
        return [(x, y - 24, 34, 32) for x, y in CUPOLAS]
    if group == "harpoon":
        return [(84, 181, 44, 24)]
    return [(744, 480, 76, 38), (728, 378, 28, 26)]


OCC = {"rifles": occ_rifles, "cannons": occ_cannons, "bombs": occ_bombs, "cupolas": occ_cupolas, "deck": occ_deck, "harpoon": occ_harpoon}


def sketches():
    """The faint notes around the drawing: a gear train, shields, a screw, an arrow, columns of rune writing, construction lines."""
    out = []
    # construction lines
    out.append(path("M12 181 L1030 181", 0.7, INK, op=0.35, extra='stroke-dasharray="14 4 2 4"'))
    out.append(path("M530 16 L530 652", 0.7, INK, op=0.30, extra='stroke-dasharray="14 4 2 4"'))
    for y in range(40, 600, 40):
        out.append(path(f"M6 {y} L14 {y}", 0.6, INK, op=0.35))
        out.append(path(f"M1026 {y} L1034 {y}", 0.6, INK, op=0.35))
    for x in range(40, 1040, 40):
        out.append(path(f"M{x} 6 L{x} 14", 0.6, INK, op=0.35))
    # gear train, lower middle
    for (x, y, r, n) in ((70, 540, 42, 18), (124, 592, 26, 12), (994, 372, 28, 14)):
        pts = []
        for i in range(n * 2):
            a = i * math.pi / n
            rr = r + (5 if i % 2 == 0 else 0)
            pts.append((x + rr * math.cos(a), y + rr * math.sin(a)))
        out.append(path(poly(pts, True), 1.0, INK_SOFT, op=0.42))
        out.append(circle(x, y, r * 0.72, 0.8, INK_SOFT, op=0.42))
        out.append(circle(x, y, r * 0.2, 0.9, INK_SOFT, op=0.42))
        for a_ in range(0, 360, 60):
            ca, sa = math.cos(math.radians(a_)), math.sin(math.radians(a_))
            out.append(path(f"M{x + r * 0.2 * ca:.1f} {y + r * 0.2 * sa:.1f} L{x + r * 0.72 * ca:.1f} {y + r * 0.72 * sa:.1f}", 0.9, INK_SOFT, op=0.42))
    # a shield and a screw, top corners
    out.append(path("M34 300 L100 300 L100 344 Q 92 374 67 386 Q 42 374 34 344 Z", 1.1, INK_SOFT, op=0.40))
    out.append(path("M67 300 L67 386 M34 342 L100 342", 0.8, INK_SOFT, op=0.40))
    out.append(hatch([(67, 342), (100, 342), (92, 374), (67, 386)], 55, 5, 0.6, INK_SOFT, 0.36))
    # rune writing
    for col_x, col_y, n in ((960, 40, 7), (988, 40, 5), (22, 396, 6), (120, 400, 4), (970, 690, 3)):
        out += runes(col_x, col_y, n)
    # a dimension along the hull
    out.append(path("M246 640 L246 652 M866 640 L866 652 M246 646 L866 646", 0.7, INK, op=0.40))
    out.append(path("M246 646 L254 643 M246 646 L254 649 M866 646 L858 643 M866 646 L858 649", 0.7, INK, op=0.40))
    return out


def runes(x, y, n):
    out = []
    for i in range(n):
        gx, gy = x, y + i * 24
        pts = [(gx + RNG.choice((-6, 0, 6)), gy + RNG.choice((-8, -3, 3, 8))) for _ in range(RNG.randint(3, 4))]
        out.append(path(poly(pts), 1.0, INK_SOFT, op=0.42))
        if RNG.random() < 0.5:
            out.append(path(f"M{gx - 6} {gy + 8} L{gx + 6} {gy + 8}", 0.8, INK_SOFT, op=0.42))
    return out


def leaders():
    out = []
    for group, spec in PLATES.items():
        px, py = spec["at"]
        tx, ty = spec["to"]
        # from the plate's nearest edge to the part, ending in a dot and a small ring
        if group == "cupolas":
            sx, sy = px + PLATE_W, py + PLATE_H / 2
        else:
            sx, sy = (min(max(tx, px + 30), px + PLATE_W - 30), py)
        out.append(path(f"M{sx:.1f} {sy:.1f} L{tx} {ty}", 1.4, INK))
        if group == "cupolas":      # on to the rear one, along the top of the balloon
            out.append(path(f"M{tx} {ty} L{tx + 20} 24 L{CUPOLAS[1][0] - 40} 24 L{CUPOLAS[1][0] - 26} {CUPOLAS[1][1] - 14}", 1.1, INK))
            out.append(circle(CUPOLAS[1][0] - 26, CUPOLAS[1][1] - 14, 4.0, 1.2, INK, "#fff1dc"))
            out.append(dot(CUPOLAS[1][0] - 26, CUPOLAS[1][1] - 14, 1.5))
        out.append(circle(tx, ty, 4.6, 1.3, INK, "#fff1dc"))
        out.append(dot(tx, ty, 1.7))
    return out


# ---------------- painting ----------------
WOBBLE = ('<filter id="ink" x="-5%" y="-5%" width="110%" height="110%"><feTurbulence type="fractalNoise" baseFrequency="0.028" numOctaves="2" seed="7"/>'
          '<feDisplacementMap in="SourceGraphic" scale="2.4"/></filter>')


def svg_page(parts, background=None, w=DRAW_W, h=DRAW_H, scale=SCALE, filtered=True):
    body = "".join(parts)
    group = f'<g filter="url(#ink)">{body}</g>' if filtered else body
    return (f'<!doctype html><html><head><meta charset="utf-8"><style>html,body{{margin:0;padding:0;background:{background or "transparent"};overflow:hidden}}svg{{display:block}}</style></head><body>'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{round(w * scale)}" height="{round(h * scale)}" viewBox="0 0 {w} {h}"><defs>{WOBBLE}</defs>{group}</svg></body></html>')


def paint(name, html, w, h):
    """Chrome paints html into TEMP/name.png, with alpha."""
    TEMP.mkdir(parents=True, exist_ok=True)
    source = TEMP / f"{name}.html"
    target = TEMP / f"{name}.png"
    source.write_text(html, encoding="utf-8")
    target.unlink(missing_ok=True)
    # headless Chrome reserves part of a small window: paint with margin, then crop
    subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--user-data-dir={TEMP / 'chrome'}", "--no-first-run", "--force-device-scale-factor=1",
                    "--default-background-color=00000000", f"--window-size={w},{h + 200}", f"--screenshot={target}", source.as_uri()],
                   check=True, capture_output=True, timeout=120)
    from PIL import Image
    im = Image.open(target).convert("RGBA").crop((0, 0, w, h))
    im.save(target)
    return im


def noise(shape, sigma, rng):
    from scipy.ndimage import gaussian_filter
    n = gaussian_filter(rng.standard_normal(shape), sigma, mode="reflect")
    return n / n.std()


def parchment(w, h):
    """Warm old paper with stains and a dark edge, after the colours of the game's sketch."""
    import numpy as np
    from scipy.ndimage import gaussian_filter
    rng = np.random.default_rng(1701)
    large = 0.5 * noise((h, w), 90, rng) + 0.3 * noise((h, w), 34, rng)
    medium = 0.6 * noise((h, w), 9, rng) + 0.5 * noise((h, w), 3, rng)
    grain = noise((h, w), 0.8, rng)
    fibres = gaussian_filter(rng.standard_normal((h, w)), (0.6, 7.0))
    fibres = fibres / fibres.std()
    yy, xx = np.mgrid[0:h, 0:w]
    u, v = (xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)
    edge = (np.abs(u) ** 3.2 + np.abs(v) ** 3.2) ** (1 / 3.2)
    vignette = np.clip((edge - 0.56) / 0.50, 0, 1) ** 1.5
    # tones: from a light amber through old orange to dark brown
    light = np.array([232, 180, 112], float)
    mid = np.array([196, 134, 72], float)
    dark = np.array([76, 50, 30], float)
    t = 0.36 + 0.10 * large + 0.042 * medium + 0.018 * grain + 0.018 * fibres
    t = np.clip(t, 0, 1)[..., None]
    rgb = np.where(t < 0.5, light + (mid - light) * (t / 0.5), mid + (dark - mid) * ((t - 0.5) / 0.5))
    # a green-grey cast in one corner, like the sketch of the game
    cast = np.clip(1 - np.hypot(u + 0.75, v + 0.70) / 0.95, 0, 1)[..., None]
    rgb = rgb * (1 - 0.26 * cast) + np.array([150, 148, 92], float) * 0.26 * cast
    # stains
    blot = np.clip(noise((h, w), 55, rng) - 1.7, 0, 2)[..., None]
    rgb = rgb * (1 - 0.10 * blot)
    speck = np.clip(noise((h, w), 1.2, rng) - 2.9, 0, 1)[..., None]
    rgb = rgb * (1 - 0.55 * speck)
    v3 = vignette[..., None]
    rgb = rgb * (1 - 0.78 * v3) + dark * 0.34 * v3
    return rgb.clip(0, 255)


def blueprint():
    import numpy as np
    from PIL import Image
    w, h = round(DRAW_W * SCALE), round(DRAW_H * SCALE)
    sketch = paint("sketch", svg_page(sketches(), "#ffffff"), w, h)
    drawing = paint("drawing", svg_page(balloon_placed() + rigging() + hull() + bay_marks() + rear_parts() + malakai() + leaders(), "#ffffff"), w, h)
    paper = parchment(w, h)
    ink_a = np.asarray(sketch.convert("RGB"), float) / 255
    ink_b = np.asarray(drawing.convert("RGB"), float) / 255
    # ink that is not even, and fades a little in places
    rng = np.random.default_rng(99)
    patchy = np.clip(0.90 + 0.09 * noise((h, w), 1.3, rng) + 0.05 * noise((h, w), 20, rng), 0.55, 1.0)[..., None]
    out = paper * ink_a
    white = ink_b >= 0.985
    faded = 1 - (1 - ink_b) * patchy
    out = out * np.where(white, 1.0, faded)
    return Image.fromarray(out.clip(0, 255).astype("uint8"), "RGB")


def layer(name, parts, places):
    """A layer with alpha, cropped to what it holds. places[name] = x, y, w, h in scheme units."""
    w, h = round(DRAW_W * SCALE), round(DRAW_H * SCALE)
    im = paint(name, svg_page(parts), w, h)
    box = im.getbbox()
    pad = 2
    box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, w), min(box[3] + pad, h))
    im = im.crop(box)
    im.save(OUT / f"{name}.png", optimize=True)
    places[name] = [round(box[0] / SCALE, 2), round(box[1] / SCALE, 2), round((box[2] - box[0]) / SCALE, 2), round((box[3] - box[1]) / SCALE, 2)]
    return im, box


def chalk(group):
    """Red chalk: a soft wash and a rough ring round the group's parts."""
    defs = '<filter id="soft" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="9"/></filter>'
    wash = []
    rings = []
    for (x, y, rx, ry) in sel_shapes(group):
        wash.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx * 1.05:.1f}" ry="{ry * 1.05:.1f}" fill="#ff5a12"/>')
        rings.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{rx + 3:.1f}" ry="{ry + 3:.1f}" fill="none" stroke="#b81e06" stroke-width="2.6" transform="rotate({RNG.uniform(-3, 3):.1f} {x:.1f} {y:.1f})"/>')
    return [f'<defs>{defs}</defs><g filter="url(#soft)" opacity="0.34">{"".join(wash)}</g><g filter="url(#ink)">{"".join(rings)}</g>']


# ---------------- frames in the game's steel and copper: 9-slice pictures, the corners are not stretched ----------------
def frame_svg(w, h, kind):
    """A plate: dark steel with a copper edge and rivets. kind: plate, row."""
    pal = {
        "normal": ("#17140f", "#2b241a", "#8a5a2c", "#c58b4a"),
        "hover": ("#2a2115", "#3e3220", "#c58b4a", "#ebbd7c"),
        "selected": ("#2c1809", "#50290c", "#e0963c", "#ffd48a"),
        "locked": ("#141414", "#1e1e1c", "#55524a", "#77736a"),
    }[kind]
    top, bottom, edge, light = pal
    r = 5
    grad = f'<linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{bottom}"/><stop offset="1" stop-color="{top}"/></linearGradient>'
    out = [f'<defs>{grad}</defs>',
           f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="{r}" fill="url(#g)" stroke="#080604" stroke-width="2"/>',
           f'<rect x="3" y="3" width="{w - 6}" height="{h - 6}" rx="{r - 1}" fill="none" stroke="{edge}" stroke-width="1.8"/>',
           f'<path d="M6 4.5 L{w - 6} 4.5" stroke="{light}" stroke-width="0.9" opacity="0.65"/>',
           f'<rect x="6" y="6" width="{w - 12}" height="{h - 12}" rx="{r - 2}" fill="none" stroke="#000000" stroke-width="0.9" opacity="0.55"/>']
    for x, y in ((9, 9), (w - 9, 9), (9, h - 9), (w - 9, h - 9)):
        out.append(f'<circle cx="{x}" cy="{y}" r="2.6" fill="{edge}" stroke="#0a0705" stroke-width="0.7"/>')
        out.append(f'<circle cx="{x - 0.7}" cy="{y - 0.7}" r="0.9" fill="{light}"/>')
    return out


def icon_button():
    """The HUD button's icon: a whole airship well inside the round button, thin copper on the button's blue, as the game's icons. Painted at twice the size it is shown."""
    size = 110
    dark, light, mid, deep = "#2c1508", "#f3c98a", "#c98a46", "#7d4a1e"
    out = ['<defs><linearGradient id="b" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f6d7a0"/><stop offset="0.55" stop-color="#c98a46"/><stop offset="1" stop-color="#7d4a1e"/></linearGradient>'
           '<linearGradient id="h" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d9a062"/><stop offset="1" stop-color="#6e3f18"/></linearGradient>'
           '<filter id="s" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="1.3"/></filter></defs>']
    body = []
    # balloon: 54 wide, 25 high, with a nose and a small tail
    balloon_d = "M28 45 C 28 35 40 30 55 30 C 68 30 79 34 83 41 L88 38 L88 52 L83 49 C 79 56 68 60 55 60 C 40 60 28 55 28 45 Z"
    body.append(f'<path d="{balloon_d}" fill="url(#b)" stroke="{dark}" stroke-width="2.4" stroke-linejoin="round"/>')
    for d in ("M39 32 Q 33 45 39 58", "M55 30 L55 60", "M71 33 Q 77 45 71 57"):
        body.append(f'<path d="{d}" fill="none" stroke="{dark}" stroke-width="1.5"/>')
    body.append(f'<path d="M29 46 C 45 49 66 49 83 45" fill="none" stroke="{dark}" stroke-width="1.5"/>')
    body.append(f'<path d="M22 45 L28 45" stroke="{dark}" stroke-width="2.2"/>')
    # ropes
    for d in ("M44 59 L47 68", "M55 60 L55 68", "M66 59 L63 68"):
        body.append(f'<path d="{d}" stroke="{dark}" stroke-width="1.6"/>')
    # hull: a small boat with a raised bow and a screw at the stern
    hull_d = "M36 68 L75 68 L72 76 C 70 80 44 80 41 76 Z"
    body.append(f'<path d="{hull_d}" fill="url(#h)" stroke="{dark}" stroke-width="2.2" stroke-linejoin="round"/>')
    body.append(f'<path d="M36 68 C 34 65 34 62 37 60 C 39 62 40 65 40 68" fill="{mid}" stroke="{dark}" stroke-width="1.7"/>')
    body.append(f'<path d="M75 73 L80 73 M80 69 L80 77" stroke="{dark}" stroke-width="1.8"/>')
    out.append(f'<g filter="url(#s)" opacity="0.65" transform="translate(1.2 1.8)">' + "".join(p.replace("url(#b)", dark).replace("url(#h)", dark).replace(mid, dark) for p in body) + "</g>")
    out += body
    # a small highlight on the balloon
    out.append(f'<path d="M36 37 C 42 34 49 33 54 33" fill="none" stroke="{light}" stroke-width="1.5" opacity="0.8"/>')
    return out, size


def card_harpoon():
    """The harpoon's card, in the size of the game's unit cards: the spear on dark steel."""
    w, h = 60, 130
    out = ['<defs><linearGradient id="c" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2b2118"/><stop offset="1" stop-color="#14100b"/></linearGradient></defs>',
           f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" fill="url(#c)" stroke="#6b4a26" stroke-width="1.6"/>',
           '<path d="M30 114 L30 34" stroke="#d9a062" stroke-width="3"/>',
           '<path d="M30 12 L42 44 L30 36 L18 44 Z" fill="#f0c88a" stroke="#2c1508" stroke-width="1.6" stroke-linejoin="round"/>',
           '<path d="M30 112 L20 98 M30 112 L40 98 M30 100 L20 86 M30 100 L40 86 M30 88 L22 76 M30 88 L38 76" stroke="#c98a46" stroke-width="1.8" fill="none"/>']
    return out, w, h


def card_empty():
    """The card of an empty place: dark, a dashed outline, the size of the game's unit cards."""
    w, h = 60, 130
    out = [f'<rect x="1" y="1" width="{w - 2}" height="{h - 2}" fill="#16120d" stroke="#6b4a26" stroke-width="1.6"/>',
           f'<rect x="7" y="7" width="{w - 14}" height="{h - 14}" fill="none" stroke="#8a5a2c" stroke-width="1.2" stroke-dasharray="5 4"/>',
           f'<path d="M20 55 L40 75 M40 55 L20 75" stroke="#8a5a2c" stroke-width="2.2" stroke-linecap="round"/>']
    return out, w, h


def frames():
    for kind in ("normal", "hover", "selected", "locked"):
        for name, w, h in (("plate", 214, 70), ("row", 400, 86)):
            s = 2
            im = paint(f"{name}_{kind}", svg_page(frame_svg(w, h, kind), w=w, h=h, scale=s, filtered=False), w * s, h * s)
            im.save(OUT / f"{name}_{kind}.png", optimize=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    bp = blueprint()
    bp.save(OUT / "blueprint.png", optimize=True)
    places = {}
    layers = {}
    for group, fn in MOUNT.items():
        layers[f"mount_{group}"] = layer(f"mount_{group}", fn(), places)
    for group, fn in OCC.items():
        layers[f"occ_{group}"] = layer(f"occ_{group}", fn(), places)
        layers[f"sel_{group}"] = layer(f"sel_{group}", chalk(group), places)
    frames()
    parts, w, h = card_harpoon()
    paint("card_harpoon", svg_page(parts, w=w, h=h, scale=2, filtered=False), w * 2, h * 2).save(OUT / "card_harpoon.png", optimize=True)
    Image.new("RGB", (8, 8), (0, 0, 0)).save(OUT / "backdrop.png")
    parts, w, h = card_empty()
    paint("card_empty", svg_page(parts, w=w, h=h, scale=2, filtered=False), w * 2, h * 2).save(OUT / "card_empty.png", optimize=True)
    parts, size = icon_button()
    paint("icon_button", svg_page(parts, w=size, h=size, scale=1, filtered=False), size, size).save(OUT / "icon_button.png", optimize=True)
    zones = {group: [[round(v, 1) for v in zone] for zone in sel_shapes(group)] for group in OCC}
    (REPO / "data" / "crew_ui_art.json").write_text(json.dumps({"size": [DRAW_W, DRAW_H], "plate": [PLATE_W, PLATE_H], "plates": PLATES, "layers": places, "zones": zones}, indent=1), encoding="utf-8")
    if args.preview:
        canvas = bp.convert("RGBA")
        for group in OCC:
            im, box = layers[f"occ_{group}"]
            canvas.alpha_composite(im, (box[0], box[1]))
        im, box = layers["sel_cannons"]
        canvas.alpha_composite(im, (box[0], box[1]))
        canvas.convert("RGB").save(TEMP / "preview.png")
        bp.save(TEMP / "preview_empty.png")
    for f in sorted(OUT.glob("*.png")):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    sys.exit(main())
