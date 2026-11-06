"""Layers of the drawing for the stages of a building, for the web page of the airship screen: py -3.10 tools/web_art.py

Stages (docs/design/panel-upgrades-proposal.md, section 7): not built is pencil, being built is pale ink under red hatching, built is ink.
The ink of a part is the panel's own layer in data/ui (mount_cannons.png and so on, tools/crew_ui_art.py); this script draws only the other two stages,
with the same shapes and places as tools/crew_ui_art.py, painted the same way (headless Chrome, the same scale). Writes web/art/<part>_pencil.png,
<part>_build.png and their places in web/art/layers.json (x, y, w, h in units of the drawing, 1040 x 760, as data/crew_ui_art.json).
Also web/art/blueprint_base.png: the drawing of the base barge, without the details that buildings will bring (side shields, porthole, stern boards),
and those details as layers of their own (<part>_ink, _pencil, _build).
Python 3.10 for Pillow, as tools/crew_ui_art.py. Its work files go to build/crew_ui, as that script's.
"""
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import crew_ui_art as art  # noqa: E402

OUT = REPO / "web" / "art"
PENCIL = "#3f3d39"         # graphite on the parchment
CHALK = "#b81e06"          # the red of the selection chalk, crew_ui_art.chalk


def round_points(x, y, r, n=24):
    return [(x + r * math.cos(2 * math.pi * i / n), y + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def port_pencil():
    """The port as a construction sketch: thin graphite circles, the rivet marks, centre lines; no fill."""
    x, y = art.CANNON
    out = [art.circle(x, y, 17, 1.4, PENCIL, op=0.9), art.circle(x, y, 12, 1.0, PENCIL, op=0.8)]
    for a in range(0, 360, 45):
        out.append(art.circle(x + 14.5 * math.cos(math.radians(a)), y + 14.5 * math.sin(math.radians(a)), 1.0, 0.7, PENCIL, op=0.8))
    out.append(art.path(f"M{x - 24} {y} L{x + 24} {y} M{x} {y - 24} L{x} {y + 24}", 0.8, PENCIL, op=0.7, extra='stroke-dasharray="5 2 1 2"'))
    return out


def ink_pale(parts, op):
    return [f'<g opacity="{op}">{"".join(parts)}</g>']


def port_build():
    """Being built: the port's ink, pale, under red hatching, with the pencil lines still seen."""
    x, y = art.CANNON
    out = ink_pale(art.mount_cannons(), 0.45)
    out.append(art.hatch(round_points(x, y, 19), 45, 3.6, 1.1, CHALK, 0.75))
    out += port_pencil()
    return out




def layer(name, parts, places):
    """As crew_ui_art.layer, into web/art."""
    w, h = round(art.DRAW_W * art.SCALE), round(art.DRAW_H * art.SCALE)
    im = art.paint("web_" + name, art.svg_page(parts), w, h)
    box = im.getbbox()
    pad = 2
    box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, w), min(box[3] + pad, h))
    im.crop(box).save(OUT / f"{name}.png", optimize=True)
    places[name] = [round(box[0] / art.SCALE, 2), round(box[1] / art.SCALE, 2), round((box[2] - box[0]) / art.SCALE, 2), round((box[3] - box[1]) / art.SCALE, 2)]


# ---------------- the base barge: the panel's drawing without the details that buildings will bring ----------------
# tools/crew_ui_art.py draws them inside hull() and rear_parts(); they are taken out of those lists by the exact elements they start with, so the rest of
# the drawing is the panel's own. Each one taken out is kept as the ink layer of its part.
def _index(items, item, what):
    if item not in items:
        raise SystemExit(f"{what}: not found in tools/crew_ui_art.py's drawing: it changed, look again")
    return items.index(item)


def hull_split():
    """(hull before the shields, hull from its outline on, the side shields, the porthole) from crew_ui_art.hull(). The rope wale of the whole
    length is taken out of the first list: trim() draws the gunwale as the model has it."""
    items = art.hull()
    first_shield = _index(items, art.circle(430, 503, 22.5, 1.5, art.INK, "#fff1dc"), "first shield")
    porthole = _index(items, art.circle(300, 476, 13, 1.6, art.INK, "#fff1dc"), "porthole")
    outline = _index(items, art.path(art.poly(art.hull_outline(), True), 2.6), "hull outline")
    wale = wale_items()
    pre = [i for i in items[:first_shield] if i not in wale]
    if len(pre) != first_shield - len(wale):
        raise SystemExit("the rope wale of tools/crew_ui_art.py changed, look again")
    return pre, items[outline:], items[first_shield:porthole], items[porthole:outline]


STERN_FIN = "M672 616 L672 352 C 672 330 694 314 716 314 C 738 314 760 330 760 352 L760 626 L716 626 Z"


def rear_split():
    """(stern without the rudder boards, the rudder boards) from crew_ui_art.rear_parts(): the great wooden fins over the stern deck are the boards."""
    items = art.rear_parts()
    fin = _index(items, art.path(STERN_FIN, 2.4, art.INK, op=0.85, extra='stroke-dasharray="11 3"'), "stern boards")
    return items[:fin], items[fin:]


def blueprint_base(hull_items, rear_items):
    """As crew_ui_art.blueprint(): parchment, the faint notes, the ship in ink. No callout lines (the ship tab has no plates) and no dashed place of the pub."""
    import numpy as np
    from PIL import Image
    w, h = round(art.DRAW_W * art.SCALE), round(art.DRAW_H * art.SCALE)
    sketch = art.paint("web_sketch", art.svg_page(art.sketches(), "#ffffff"), w, h)
    drawing = art.paint("web_drawing", art.svg_page(art.balloon_placed() + art.rigging() + hull_items + rear_items + art.malakai(), "#ffffff"), w, h)
    paper = art.parchment(w, h)
    ink_a = np.asarray(sketch.convert("RGB"), float) / 255
    ink_b = np.asarray(drawing.convert("RGB"), float) / 255
    rng = np.random.default_rng(99)
    patchy = np.clip(0.90 + 0.09 * art.noise((h, w), 1.3, rng) + 0.05 * art.noise((h, w), 20, rng), 0.55, 1.0)[..., None]
    out = paper * ink_a
    white = ink_b >= 0.985
    out = out * np.where(white, 1.0, 1 - (1 - ink_b) * patchy)
    return Image.fromarray(out.clip(0, 255).astype("uint8"), "RGB")


def pencil_of(items):
    """Any ink part as a pencil sketch: graphite strokes, no fills, a little lighter."""
    import re
    text = "".join(items)
    text = re.sub(r'stroke="#[0-9a-fA-F]{6}"', f'stroke="{PENCIL}"', text)
    text = re.sub(r'fill="#[0-9a-fA-F]{6}"', 'fill="none"', text)
    text = re.sub(r'stroke-width="([0-9.]+)"', lambda m: f'stroke-width="{max(0.6, float(m.group(1)) * 0.7):.2f}"', text)
    return [f'<g opacity="0.85">{text}</g>']


def build_of(items, area):
    """Being built: the ink pale under red hatching over the part's area, the pencil lines over it."""
    return ink_pale(items, 0.45) + [art.hatch(area, 45, 3.6, 1.1, CHALK, 0.75)] + pencil_of(items)


# ---------------- the base barge as the model has it (compared with build/solid_hull_hatches side by side, 06.11.2026) ----------------
# Places come from the model: x = 246 + (8.3 - z) * 36 as tools/crew_ui_art.py; heights y = 598 - 41.5 * (y_model + 0.33), fitted to the drawn keel
# (y -0.33 on the model) and forecastle rail (4.2). The drawing's 35 per unit does not hold for the hull: it is a sketch, taller in the waist.
def mx(z):
    return 246 + (8.3 - z) * 36


def my(y):
    return 598 - 41.5 * (y + 0.33)


STEEL = "#9c968c"
BRASS = "#d9a76a"


def gear(cx, cy, r, n, spokes, hub, inner):
    teeth = []
    for i in range(n * 2):
        a = i * math.pi / n
        rr = r + (6 if i % 2 == 0 else 0)
        teeth.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    out = [art.shape(art.poly(teeth, True), "#fff1dc"), art.path(art.poly(teeth, True), 1.6), art.circle(cx, cy, inner, 1.3),
           art.circle(cx, cy, inner - 4, 0.8, art.INK, op=0.7), art.circle(cx, cy, hub, 1.4, art.INK, STEEL)]
    for k in range(spokes):
        a = math.radians(k * 360 / spokes + (0 if spokes == 4 else 22.5))      # the big gear's cross stands upright, as on the model
        ca, sa = math.cos(a), math.sin(a)
        w = 3.2 if spokes == 4 else 1.4
        out.append(art.path(f"M{cx + hub * ca:.1f} {cy + hub * sa:.1f} L{cx + (inner - 4) * ca:.1f} {cy + (inner - 4) * sa:.1f}", w))
    return out


def drive():
    """The screw's drive as on the model: the small gear high at the stern, the big gear before it, the gear's axle running down through a neck into the
    shaft's casing, the casing along the hull, a banded hub, the blades and the pointed cap."""
    out = []
    out += gear(mx(-8.25), my(3.67), 41, 11, 8, 6, 33)              # small gear, behind
    out += gear(mx(-6.25), my(2.5), 47, 12, 4, 9, 38)               # big gear, in front of it
    gx, gy = mx(-6.25), my(2.5)
    neck = f"M{gx - 7:.1f} {gy + 4:.1f} L{gx + 7:.1f} {gy + 4:.1f} L{gx + 13:.1f} {my(1.55):.1f} L{gx - 13:.1f} {my(1.55):.1f} Z"
    out += [art.shape(neck, "#fff1dc"), art.path(neck, 1.6), art.path(f"M{gx - 10:.1f} {gy + 26:.1f} L{gx + 10:.1f} {gy + 26:.1f}", 1.2)]
    # the casing: a long rounded tube from the waist past the stern
    x0, x1, top, bottom = mx(-4.6), mx(-8.1), my(1.67), my(0.83)
    mid = (top + bottom) / 2
    casing = f"M{x1:.1f} {top:.1f} L{x0 + 14:.1f} {top:.1f} C {x0 - 2:.1f} {top:.1f} {x0 - 6:.1f} {mid:.1f} {x0 - 6:.1f} {mid:.1f} C {x0 - 6:.1f} {mid:.1f} {x0 - 2:.1f} {bottom:.1f} {x0 + 14:.1f} {bottom:.1f} L{x1:.1f} {bottom:.1f} Z"
    out += [art.shape(casing, "#fff1dc"), art.path(casing, 1.8), art.hatch([(x0, mid + 4), (x1, mid + 4), (x1, bottom), (x0, bottom)], 70, 3.4, 0.7)]
    for bx in (x0 + 18, x0 + 46, x1 - 6):
        out.append(art.path(f"M{bx:.1f} {top - 1:.1f} L{bx:.1f} {bottom + 1:.1f} M{bx + 5:.1f} {top - 1:.1f} L{bx + 5:.1f} {bottom + 1:.1f}", 1.1))
        for ry in (top + 5, bottom - 5):
            out.append(art.dot(bx + 2.5, ry, 1.0))
    # the hub: a barrel with bands
    h0, h1 = mx(-8.1), mx(-9.2)
    hub = f"M{h0:.1f} {top + 1:.1f} L{h1:.1f} {top + 3:.1f} L{h1:.1f} {bottom - 3:.1f} L{h0:.1f} {bottom - 1:.1f} Z"
    out += [art.shape(hub, "#fff1dc"), art.path(hub, 1.6)]
    for k in range(1, 4):
        bx = h0 + (h1 - h0) * k / 4
        out.append(art.path(f"M{bx:.1f} {top + 2:.1f} L{bx:.1f} {bottom - 2:.1f}", 1.0))
    # blades: up, down, and two seen end on, then the pointed cap
    bx = mx(-9.6)
    for d in (-1, 1):
        tip = my(2.33) if d < 0 else my(0.17) + 18
        blade = f"M{bx - 4:.1f} {mid + d * 8:.1f} C {bx - 12:.1f} {mid + d * 30:.1f} {bx - 8:.1f} {tip:.1f} {bx + 2:.1f} {tip:.1f} C {bx + 10:.1f} {tip:.1f} {bx + 10:.1f} {mid + d * 30:.1f} {bx + 6:.1f} {mid + d * 8:.1f} Z"
        out += [art.shape(blade, "#fff1dc"), art.path(blade, 1.5)]
    for dy in (-6, 6):
        out += [art.path(f"M{bx - 9:.1f} {mid + dy:.1f} L{bx + 11:.1f} {mid + dy * 0.6:.1f}", 3.2), art.path(f"M{bx - 9:.1f} {mid + dy:.1f} L{bx + 11:.1f} {mid + dy * 0.6:.1f}", 1.4, "#fff1dc")]
    tip = mx(-11.1)
    cap = f"M{bx + 8:.1f} {mid - 9:.1f} L{bx + 8:.1f} {mid + 9:.1f} L{tip:.1f} {mid:.1f} Z"
    out += [art.shape(cap, "#fff1dc"), art.path(cap, 1.5), art.hatch([(bx + 8, mid), (tip, mid), (bx + 8, mid + 9)], 80, 3, 0.7)]
    return out


def belt():
    """The steel belt along the bottom of the hull, from under the bow's curve to the stern: plates with seams and rivets; the rod along it."""
    top = my(1.0)
    xs = [x for x in range(int(mx(7.1)), int(mx(-8.2)) + 1, 4) if art.hull_bottom(x) > top + 2]
    lower = [(x, art.hull_bottom(x) - 0.5) for x in xs]
    band = [(xs[0], top)] + [(xs[-1], top)] + lower[::-1]
    out = [art.shape(art.poly(band, True), STEEL, 0.5), art.path(f"M{xs[0]} {top:.1f} L{xs[-1]} {top:.1f}", 1.4)]
    x = xs[0] + 18
    while x < xs[-1] - 6:
        out.append(art.path(f"M{x:.1f} {top:.1f} L{x:.1f} {art.hull_bottom(x) - 1:.1f}", 0.8))
        for k in (-3, 3):
            out.append(art.dot(x + k, top + 4, 0.9))
        x += 0.85 * 36
    # the rod in front of the belt
    r0, r1, ry = mx(4.6), mx(-4.9), my(0.5)
    rod = f"M{r0:.1f} {ry - 3:.1f} L{r1:.1f} {ry - 3:.1f} Q {r1 + 4:.1f} {ry:.1f} {r1:.1f} {ry + 3:.1f} L{r0:.1f} {ry + 3:.1f} Q {r0 - 4:.1f} {ry:.1f} {r0:.1f} {ry - 3:.1f} Z"
    out += [art.shape(rod, "#fff1dc"), art.path(rod, 1.3)]
    return out


ROPE = "#8f5a2c"
IRON = "#d6cfc2"


def arc_pts(cx, cy, rx, ry, a0, a1, n=24):
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


def crescent(cx, cy, r, dx, dy):
    """The shaded side of a ball lit from the upper left: the ball minus a shifted ball."""
    out = []
    for i in range(41):
        a = math.radians(-60 + 210 * i / 40)
        out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    for i in range(41):
        a = math.radians(150 - 210 * i / 40)
        x, y = cx + dx + r * math.cos(a), cy + dy + r * math.sin(a)
        if math.hypot(x - cx, y - cy) <= r:
            out.append((x, y))
    return out


def ball(cx, cy, r, heavy=False):
    """An iron ball of four plates as on the model: the outline, one seam round the middle and one over the top (a cross on the side we see,
    a little turned), rivets in pairs beside the seams, the lug on top, the shade of a ball lit from the upper left."""
    out = [art.circle(cx, cy, r, 1.8, art.INK, IRON)]
    sh = crescent(cx, cy, r, -r * 0.42, -r * 0.42)
    out.append(art.hatch(sh, 50, 2.4, 0.8, art.INK, 0.8))
    if heavy:
        out.append(art.hatch(sh, 140, 2.8, 0.6, art.INK, 0.6))
    # the seams: double lines; the middle one bowed (seen a little from above), the upright one bowed (the ball turned a little)
    sx = cx - r * 0.12
    for k in (-1.3, 1.3):
        out.append(art.path(art.smooth(arc_pts(cx, cy + k + 1, r * 0.99, r * 0.16, 0, 180, 16)), 0.9))
        out.append(art.path(art.smooth(arc_pts(sx + k, cy, r * 0.22, r * 0.99, -90, 90, 16)), 0.9))
    # rivets in pairs beside the seams, on each plate
    for qx in (-1, 1):
        for qy in (-1, 1):
            out.append(art.dot(sx + qx * r * 0.45, cy + qy * r * 0.2 + 1, 1.3))
            out.append(art.dot(sx + r * 0.1 + qx * r * 0.2, cy + qy * r * 0.55, 1.3))
    out.append(f'<ellipse cx="{cx:.1f}" cy="{cy - r - 2.6:.1f}" rx="3.6" ry="3.0" fill="none" stroke="{art.INK}" stroke-width="1.5"/>')
    return out


def rope(points, w=1.6, twist=True):
    """A rope: a brown line in ink with short slanted strokes along it, as the drawing's wale."""
    d = art.smooth(points) if len(points) > 2 else art.poly(points)
    out = [art.path(d, w + 1.2, art.INK), art.path(d, w, ROPE)]
    if twist:
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            n = int(L / 3.2)
            for i in range(1, n):
                t = i / n
                x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
                ux, uy = (x1 - x0) / L, (y1 - y0) / L
                out.append(art.path(f"M{x - uy * 1.3 - ux * 0.9:.1f} {y + ux * 1.3 - uy * 0.9:.1f} L{x + uy * 1.3 + ux * 0.9:.1f} {y - ux * 1.3 + uy * 0.9:.1f}", 0.5, art.INK, op=0.8))
    return out


def knot(x, y, r=2.6):
    return [art.circle(x, y, r, 1.2, art.INK, ROPE)]


def cradle(cx, cy, r, kx, ky, twist=True, back=False):
    """The rope basket: from the knot two ropes run straight down in front of the ball to a ring round it under its middle; three ropes from the ring
    meet under the ball in a knot. back: the rope behind the ball, thin, seen past its side."""
    out = []
    ring = arc_pts(cx, cy + r * 0.42, r * 0.92, r * 0.22, 0, 180, 16)
    left, right = ring[-1], ring[0]
    if back:
        out.append(art.path(art.poly([(kx, ky), (cx - r * 1.0, cy - r * 0.1)]), 0.9, art.INK, op=0.7))
    out += rope([(kx, ky), ring[11]], twist=twist)
    out += rope([(kx, ky), (right[0] + 1.5, right[1])], twist=twist)
    out += rope(ring, 1.3, twist)
    bottom = (cx + r * 0.05, cy + r * 1.08)
    for i in (4, 11):
        out += rope([ring[i], bottom], 1.1, twist)
        out += knot(*ring[i], 1.9)
    out += rope([left, bottom], 1.1, twist)
    out += knot(*bottom, 2.3)
    out += knot(kx, ky, 3.0)
    return out


def bombs():
    """The two bombs that hang over the side, as on the model: iron balls of four riveted plates in a rope basket, hung by a knot from the forecastle's
    lower brass band and from the corner of the stern deck's trim. Size: 1.17 of the model across (r 24). Variant B of three tries (build/web/shots/bomb_variants.png), chosen by the user."""
    out = []
    for cx, cy, kx, ky in ((375, 478, 388, 445), (640, 476, 626, 439)):
        out += ball(cx, cy, 24) + cradle(cx, cy, 24, kx, ky, back=True)      # variant B, the user's choice: the rope behind the ball seen too
    return out


FORECASTLE_END = 405        # where the forecastle's rail steps down to the waist, as hull_top() has it


def wale_items():
    """The strings crew_ui_art.hull() writes for the rope wale along the whole hull."""
    a = [(x, art.hull_top(x) + 14) for x in range(250, 866, 12)]
    b = [(x, art.hull_top(x) + 27) for x in range(250, 866, 12)]
    items = [art.shape(art.poly(a + b[::-1], True), "#8f5a2c", 0.30), art.path(art.smooth(a), 1.5), art.path(art.smooth(b), 1.5)]
    items += [art.path(f"M{x} {art.hull_top(x) + 14 + 13:.1f} L{x + 6} {art.hull_top(x) + 14:.1f}", 0.7, art.INK, op=0.8) for x in range(256, 860, 8)]
    return items


def trim():
    """The gunwale as on the model: a brass cap rail with rivets along the whole top edge (down the forecastle's step and round the stern deck's),
    the rope wale between two brass bands only on the forecastle."""
    xs = list(range(250, 862, 4))
    top = [(x, art.hull_top(x)) for x in xs]
    low = [(x, art.hull_top(x) + 6) for x in xs]
    out = [art.shape(art.poly(top + low[::-1], True), BRASS, 0.55), art.path(art.smooth(low[::2]), 1.0)]
    for x in range(256, 858, 16):
        out.append(art.dot(x, art.hull_top(x) + 3, 0.9))
    fx = [x for x in range(250, FORECASTLE_END + 1, 6)]
    a = [(x, art.hull_top(x) + 14) for x in fx]
    b = [(x, art.hull_top(x) + 27) for x in fx]
    c = [(x, art.hull_top(x) + 33) for x in fx]
    out += [art.shape(art.poly(a + b[::-1], True), "#8f5a2c", 0.30), art.path(art.smooth(a), 1.5), art.path(art.smooth(b), 1.5),
            art.shape(art.poly(b + c[::-1], True), BRASS, 0.55), art.path(art.smooth(c), 1.0)]
    for x in range(256, FORECASTLE_END - 4, 8):
        out.append(art.path(f"M{x} {art.hull_top(x) + 27:.1f} L{x + 6} {art.hull_top(x) + 14:.1f}", 0.7, art.INK, op=0.8))
    # the groups of four rivets at the butt joints of the waist
    for z in (0.9, -3.8):
        for dx in (-2.5, 2.5):
            for dy in (-2.5, 2.5):
                out.append(art.dot(mx(z) + dx, my(1.25) + dy, 1.0))
    return out


def gear_start(items):
    """Where the old stern gear, shaft and screw start in crew_ui_art.rear_parts(): they end where the stern boards begin."""
    gx, gy, gr = 846, 424, 34
    teeth = []
    for i in range(28):
        a = i * math.pi / 14
        r = gr + (5 if i % 2 == 0 else 0)
        teeth.append((gx + r * math.cos(a), gy + r * math.sin(a)))
    return _index(items, art.shape(art.poly(teeth, True), "#fff1dc"), "stern gear")


PORT_AT = (mx(5.75), my(1.2))       # the port's centre on the model (data/hull_parts.json, port), on the steel belt's upper edge


def at_port(items):
    """Parts drawn round crew_ui_art.CANNON moved to the port's place on the model."""
    dx, dy = PORT_AT[0] - art.CANNON[0], PORT_AT[1] - art.CANNON[1]
    return [f'<g transform="translate({dx:.1f} {dy:.1f})">{"".join(items)}</g>']


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    hull_pre, hull_post, shields, porthole = hull_split()
    rear_items, stern = rear_split()
    # the hull with the steel belt, the gunwale and the hanging bombs under its outline; the stern with the drive as the model has it
    hull_items = hull_pre + belt() + trim() + bombs() + hull_post
    rear_items = rear_items[:gear_start(rear_items)] + drive()
    blueprint_base(hull_items, rear_items).save(OUT / "blueprint_base.png", optimize=True)
    places = {}
    # the port: no mark at all while it is not built (the base model has none); being built and built at its place on the model
    layer("port_build", at_port(port_build()), places)
    layer("port_ink", at_port(art.mount_cannons()), places)
    parts = {"port": {"pencil": None, "build": "port_build", "ink": "port_ink"}}
    # the details taken off the base barge: ink, pencil, build, ready for when their buildings are connected
    x, y = 300, 476
    removed = {
        "side_shields": (shields, [(404, 478), (696, 478), (696, 528), (404, 528)]),
        "porthole": (porthole, round_points(x, y, 15)),
        "stern_armour": (stern, [(672, 616), (672, 352), (716, 314), (760, 352), (760, 626), (716, 626)]),
    }
    for name, (items, area) in removed.items():
        # on its own layer a part is not multiplied into the parchment as the whole drawing is: its light fill takes the paper's tone, as the panel's layers do
        items = [i.replace('fill="#fff1dc"', f'fill="{art.PAPER}"') for i in items]
        layer(f"{name}_ink", items, places)
        layer(f"{name}_pencil", pencil_of(items), places)
        layer(f"{name}_build", build_of(items, area), places)
        parts[name] = {"pencil": f"{name}_pencil", "build": f"{name}_build", "ink": f"{name}_ink"}
    (OUT / "layers.json").write_text(json.dumps({
        "_about": "Made by tools/web_art.py. Places in units of the drawing (data/crew_ui_art.json, size). blueprint_base.png: the panel's drawing without the "
                  "details below, with the drive, steel belt, gunwale and bombs as the base model has them. The port is drawn at its place on the model.",
        "places": places, "parts": parts}, indent=1), encoding="utf-8")
    for f in sorted(OUT.glob("*.png")):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
