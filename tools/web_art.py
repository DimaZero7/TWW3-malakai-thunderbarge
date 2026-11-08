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


# ---------------- the hull's first level: «Заготовка под корабль», timber laid out on the ground, no ship yet ----------------
# As a dwarf yard would have it: the ground, cross-timbers (dunnage) keeping the wood off the earth, a long stack of planks bound with rope, a short stack
# of boards, the keel beam on top with its frame mortises marked, three curved frames leaning on the short stack, a mallet and a saw. Same pen as the ship.
GROUND = 610
RNG_GRAIN = __import__("random").Random(2611)


def plank(x0, x1, y, h=8, grain=2):
    """A plank seen from the side: the body, grain along it, the end grain at both ends."""
    out = [art.shape(art.poly([(x0, y - h), (x1, y - h), (x1, y), (x0, y)], True), "#fff1dc"), art.path(art.poly([(x0, y - h), (x1, y - h), (x1, y), (x0, y)], True), 1.3)]
    for k in range(grain):
        gy = y - h * (k + 1) / (grain + 1)
        a = x0 + 6 + RNG_GRAIN.uniform(0, 30)
        while a < x1 - 20:
            b = min(x1 - 6, a + RNG_GRAIN.uniform(40, 110))
            out.append(art.path(f"M{a:.1f} {gy + RNG_GRAIN.uniform(-0.6, 0.6):.1f} L{b:.1f} {gy + RNG_GRAIN.uniform(-0.6, 0.6):.1f}", 0.55, art.INK, op=0.7))
            a = b + RNG_GRAIN.uniform(14, 40)
    for x in (x0, x1):
        out.append(art.path(f"M{x:.1f} {y - h + 2:.1f} Q {x + (2 if x == x0 else -2):.1f} {y - h / 2:.1f} {x:.1f} {y - 2:.1f}", 0.6, art.INK, op=0.7))
    return out


def rope_band(x, y0, y1):
    return [art.path(f"M{x - 2} {y0:.1f} L{x - 2} {y1:.1f} M{x + 2} {y0:.1f} L{x + 2} {y1:.1f}", 1.0)] + \
        [art.path(f"M{x - 2} {y + 2.5:.1f} L{x + 2} {y:.1f}", 0.7) for y in range(int(y0) + 2, int(y1) - 1, 3)]


def planks(layout="a"):
    """layout a: the long stack with the keel on top, curved frames leaning on the boards; b: the keel on its own blocks on the ground, the planks in
    two low stacks, the frame timbers still straight in a bundle; c: one tall stack crosswise-stickered, the keel beside it."""
    RNG_GRAIN.seed(2611)
    if layout == "b":
        return planks_b()
    if layout == "c":
        return planks_c()
    out = []
    # the ground and the earth under it
    out.append(art.path(f"M236 {GROUND} L884 {GROUND}", 1.8))
    out.append(art.hatch([(240, GROUND), (880, GROUND), (868, GROUND + 18), (252, GROUND + 18)], 25, 5.5, 0.7, art.INK_SOFT, 0.55))
    for x in range(262, 870, 37):
        out.append(art.dot(x + RNG_GRAIN.uniform(-8, 8), GROUND + RNG_GRAIN.uniform(4, 14), RNG_GRAIN.uniform(0.8, 1.8), art.INK_SOFT, 0.7))
    # cross-timbers under the stacks, seen end on
    for x in (318, 505, 700, 790):
        out += [art.shape(art.poly([(x - 8, GROUND - 12), (x + 8, GROUND - 12), (x + 8, GROUND), (x - 8, GROUND)], True), "#e8c692"),
                art.path(art.poly([(x - 8, GROUND - 12), (x + 8, GROUND - 12), (x + 8, GROUND), (x - 8, GROUND)], True), 1.3),
                art.circle(x, GROUND - 6, 3.2, 0.6, art.INK, op=0.7), art.circle(x, GROUND - 6, 1.4, 0.5, art.INK, op=0.7)]
    # the long stack: six planks, a little uneven, two rope bands
    y = GROUND - 12
    for i in range(6):
        out += plank(292 + RNG_GRAIN.uniform(-10, 10), 724 + RNG_GRAIN.uniform(-12, 8), y)
        y -= 8
    top_long = y
    out += rope_band(362, top_long, GROUND - 12) + rope_band(652, top_long, GROUND - 12)
    out.append(art.hatch([(292, GROUND - 12 - 18), (724, GROUND - 12 - 18), (724, GROUND - 12), (292, GROUND - 12)], 60, 4.5, 0.6, art.INK_SOFT, 0.45))
    # the keel beam on top
    out += keel(296, 712, top_long, 13)
    # the short stack of boards
    y = GROUND - 12
    for i in range(4):
        out += plank(742 + RNG_GRAIN.uniform(-6, 6), 846 + RNG_GRAIN.uniform(-6, 4), y, 7, 1)
        y -= 7
    top_short = y
    # three curved frames leaning against it
    for i, dx in enumerate((0, 16, 32)):
        x0 = 744 + dx
        frame = f"M{x0} {top_short:.1f} C {x0 + 4} {top_short - 40:.1f} {x0 + 24} {top_short - 74:.1f} {x0 + 58} {top_short - 92:.1f}"
        out += [art.path(frame, 6.2, art.INK), art.path(frame, 3.8, "#e8c692")]
    # a mallet leaning on the long stack and a saw on the boards
    out += [art.path(f"M732 {GROUND - 1} L748 {GROUND - 58}", 3.2), art.path(f"M732 {GROUND - 1} L748 {GROUND - 58}", 1.4, "#e8c692"),
            art.shape(art.poly([(738, GROUND - 70), (760, GROUND - 64), (756, GROUND - 50), (734, GROUND - 56)], True), "#e8c692"),
            art.path(art.poly([(738, GROUND - 70), (760, GROUND - 64), (756, GROUND - 50), (734, GROUND - 56)], True), 1.4)]
    sy = top_short
    saw = [(770, sy), (838, sy - 6), (838, sy - 1), (772, sy + 4)]
    out += [art.shape(art.poly(saw, True), "#d9d2c4"), art.path(art.poly(saw, True), 1.2)]
    for x in range(774, 836, 4):
        out.append(art.path(f"M{x} {sy + 3.6 - (x - 772) * 0.075:.1f} L{x + 2} {sy + 5.6 - (x - 772) * 0.075:.1f}", 0.6))
    out += [art.shape(art.poly([(838, sy - 8), (852, sy - 10), (852, sy + 1), (838, sy + 1)], True), "#a87240"), art.path(art.poly([(838, sy - 8), (852, sy - 10), (852, sy + 1), (838, sy + 1)], True), 1.2)]
    return out


def ground():
    out = [art.path(f"M236 {GROUND} L884 {GROUND}", 1.8),
           art.hatch([(240, GROUND), (880, GROUND), (868, GROUND + 18), (252, GROUND + 18)], 25, 5.5, 0.7, art.INK_SOFT, 0.55)]
    for x in range(262, 870, 37):
        out.append(art.dot(x + RNG_GRAIN.uniform(-8, 8), GROUND + RNG_GRAIN.uniform(4, 14), RNG_GRAIN.uniform(0.8, 1.8), art.INK_SOFT, 0.7))
    return out


def block(x, y, w=16, h=12):
    """A timber seen end on: the square and its year rings."""
    return [art.shape(art.poly([(x - w / 2, y - h), (x + w / 2, y - h), (x + w / 2, y), (x - w / 2, y)], True), "#e8c692"),
            art.path(art.poly([(x - w / 2, y - h), (x + w / 2, y - h), (x + w / 2, y), (x - w / 2, y)], True), 1.3),
            art.circle(x, y - h / 2, min(w, h) * 0.27, 0.6, art.INK, op=0.7), art.circle(x, y - h / 2, min(w, h) * 0.11, 0.5, art.INK, op=0.7)]


def keel(k0, k1, y, kh=13):
    """The keel beam lying flat: heavy, its fore end (to the left, where the drawing's bow is) cut to a point, the mortises of the frames marked along it,
    runes at its after end."""
    body = [(k0, y - kh / 2), (k0 + 8, y - kh), (k1, y - kh), (k1, y), (k0 + 8, y)]
    out = [art.shape(art.poly(body, True), "#e8c692"), art.path(art.poly(body, True), 1.6)]
    for x in range(int(k0) + 34, int(k1) - 14, 36):
        out.append(art.path(f"M{x} {y - kh:.1f} L{x} {y - kh + 5:.1f} L{x + 6} {y - kh + 5:.1f} L{x + 6} {y - kh:.1f}", 1.0))
    r = k1 - 22
    out.append(art.path(f"M{r} {y - 10:.1f} L{r} {y - 2:.1f} M{r - 3} {y - 7:.1f} L{r + 3} {y - 7:.1f} M{r + 7} {y - 10:.1f} L{r + 10} {y - 4:.1f} L{r + 7} {y - 2:.1f}", 0.9))
    return out


def tools(mx_, sy):
    """A mallet leaning at mx_ and a saw lying at sy on the short stack."""
    out = [art.path(f"M{mx_} {GROUND - 1} L{mx_ + 16} {GROUND - 58}", 3.2), art.path(f"M{mx_} {GROUND - 1} L{mx_ + 16} {GROUND - 58}", 1.4, "#e8c692")]
    head = [(mx_ + 6, GROUND - 70), (mx_ + 28, GROUND - 64), (mx_ + 24, GROUND - 50), (mx_ + 2, GROUND - 56)]
    out += [art.shape(art.poly(head, True), "#e8c692"), art.path(art.poly(head, True), 1.4)]
    saw = [(770, sy), (838, sy - 6), (838, sy - 1), (772, sy + 4)]
    out += [art.shape(art.poly(saw, True), "#d9d2c4"), art.path(art.poly(saw, True), 1.2)]
    for x in range(774, 836, 4):
        out.append(art.path(f"M{x} {sy + 3.6 - (x - 772) * 0.075:.1f} L{x + 2} {sy + 5.6 - (x - 772) * 0.075:.1f}", 0.6))
    grip = [(838, sy - 8), (852, sy - 10), (852, sy + 1), (838, sy + 1)]
    out += [art.shape(art.poly(grip, True), "#a87240"), art.path(art.poly(grip, True), 1.2)]
    return out


def planks_b():
    """The keel on its blocks where the ship will stand, the planks in two low stacks beside it, the frame timbers straight in a bundle: the yard ready to lay
    the frame on the keel."""
    out = ground()
    # the keel on three blocks, along the ship's own length (x 290..740)
    for x in (318, 520, 716):
        out += block(x, GROUND, 18, 30)
    out += keel(290, 740, GROUND - 30, 14)
    # the planks: two low stacks in front, on the ground
    y = GROUND
    for i in range(3):
        out += plank(300 + RNG_GRAIN.uniform(-6, 6), 500 + RNG_GRAIN.uniform(-6, 6), y + 0.0, 7, 1)
        y -= 7
    y = GROUND
    for i in range(3):
        out += plank(540 + RNG_GRAIN.uniform(-6, 6), 730 + RNG_GRAIN.uniform(-6, 6), y, 7, 1)
        y -= 7
    out += rope_band(400, GROUND - 21, GROUND) + rope_band(635, GROUND - 21, GROUND)
    # the frame timbers: a bundle of straight pieces leaning on two trestles at the stern end
    for x in (772, 842):
        out += [art.path(f"M{x - 12} {GROUND} L{x} {GROUND - 40} L{x + 12} {GROUND}", 2.2), art.path(f"M{x - 8} {GROUND - 26} L{x + 8} {GROUND - 26}", 1.2)]
    for i in range(5):
        y = GROUND - 42 - i * 6
        out += plank(752 + i * 2, 864 - i * 2, y, 6, 1)
    out += rope_band(808, GROUND - 72, GROUND - 42)
    return out


def planks_c():
    """One tall stack laid with sticks between the layers so the wood dries, the keel on blocks beside it, a short stack of boards and the tools."""
    out = ground()
    y = GROUND
    for layer_ in range(5):
        for x in (330, 470, 610):
            out += block(x, y, 10, 6)
        y -= 6
        for k in range(2):
            out += plank(306 + RNG_GRAIN.uniform(-8, 8), 640 + RNG_GRAIN.uniform(-10, 6), y, 8, 1)
            y -= 8
    for x in (680, 840):
        out += block(x, GROUND, 18, 16)
    out += keel(664, 852, GROUND - 16, 14)
    y = GROUND - 30
    for i in range(3):
        out += plank(700 + RNG_GRAIN.uniform(-5, 5), 830 + RNG_GRAIN.uniform(-5, 5), y, 7, 1)
        y -= 7
    out += tools(648, y)
    return out


# ---------------- the hull's first level built: the frame on the slip ----------------
# The timber of layout b goes up: the keel lies on its blocks along the ship's whole length, the stem and stern posts stand at its ends, the frames (ribs)
# stand on it across the hull, a batten runs along their heads, the lowest strakes of planking close the bottom; what is left of the planks lies in a stack
# on the ground and on the trestles. No balloon, no machinery. Drawn in the ship's own places (hull_top/hull_bottom of tools/crew_ui_art.py), raised so that
# the keel lies on blocks above the ground, so that the barge later rises out of the same lines.
FRAME_DY = -18          # the keel's bottom from the drawn ship's 598 to 580, on blocks standing on the ground at 610


def ftop(x):
    return art.hull_top(x) + FRAME_DY


def fbottom(x):
    return art.hull_bottom(x) + FRAME_DY


def frame_outline():
    return [(x, y + FRAME_DY) for x, y in art.hull_outline()]


def frame_items(variant="a"):
    out = []
    # blocks under the keel, from the ground up to the hull's bottom
    for x in (330, 450, 580, 710, 800):
        h = GROUND - fbottom(x)
        out += block(x, GROUND, 18, h)
    xs = list(range(262, 852, 6))
    # the lowest strakes: planking from the keel up a third of the side, seams along it, shaded
    k = 0.30
    strake_top = [(x, fbottom(x) - (fbottom(x) - ftop(x)) * k) for x in xs]
    bottom = [(x, fbottom(x)) for x in xs]
    out += [art.shape(art.poly(strake_top + bottom[::-1], True), "#fff1dc"), art.path(art.poly(strake_top + bottom[::-1], True), 1.4)]
    for f in (1 / 3, 2 / 3):
        seam = [(x, fbottom(x) - (fbottom(x) - ftop(x)) * k * f) for x in xs[::3]]
        out.append(art.path(art.smooth(seam), 0.8, art.INK, op=0.8))
    out.append(art.hatch(strake_top[::4] + bottom[::-4], 52, 5.2, 0.8, art.INK_SOFT, 0.55))
    # the frames: one every 26 across the hull, from the strakes up to the sheer; heavier every third
    step = 26
    for i, x in enumerate(range(272, 852, step)):
        y0 = fbottom(x) - (fbottom(x) - ftop(x)) * k
        y1 = ftop(x)
        w = 4.5 if i % 3 == 0 else 3.2
        if variant == "b":       # a frame is a U across the ship: seen from the side, its near arm, bowed a little outward at the turn of the bilge
            d = f"M{x:.1f} {y0:.1f} Q {x - 4:.1f} {(y0 + y1) / 2:.1f} {x:.1f} {y1:.1f}"
        else:
            d = f"M{x:.1f} {y0:.1f} L{x:.1f} {y1:.1f}"
        out += [art.path(d, w + 2.2, art.INK), art.path(d, w, "#e8c692")]
    # the batten along the frames' heads, and a second one halfway down
    for f in (0.0, 0.5):
        line = [(x, ftop(x) + (fbottom(x) - ftop(x)) * f * 0.7) for x in xs[::3]]
        out += [art.path(art.smooth(line), 4.2, art.INK), art.path(art.smooth(line), 2.2, "#e8c692")]
    # the stem post at the bow and the stern post, along the outline's ends
    # both run along the hull's own ends: from the keel round the bottom's curve and up to the sheer
    stem = [(x, fbottom(x)) for x in range(330, 252, -10)] + [(247, 470 + FRAME_DY), (246, 440 + FRAME_DY), (250, 414 + FRAME_DY)]
    stern = [(x, fbottom(x)) for x in range(790, 862, 10)] + [(866, 470 + FRAME_DY), (866, 430 + FRAME_DY), (866, 398 + FRAME_DY)]
    for post in (stem, stern):
        out += [art.path(art.smooth(post), 9, art.INK), art.path(art.smooth(post), 6, "#e8c692")]
    # the keel along the bottom
    keel_line = [(x, fbottom(x) - 2) for x in range(300, 816, 8)]
    out += [art.path(art.smooth(keel_line), 9, art.INK), art.path(art.smooth(keel_line), 6, "#e8c692")]
    if variant == "b":           # scaffold poles and a walkway plank along the side
        for x in (300, 520, 760):
            out += [art.path(f"M{x} {GROUND} L{x} {ftop(x) - 30:.1f}", 3.4, art.INK), art.path(f"M{x} {GROUND} L{x} {ftop(x) - 30:.1f}", 1.6, "#e8c692")]
        walk = 520
        out += plank(290, 770, walk, 6, 1)
    # what is left of the timber: a low stack between the blocks and the boards on the trestles past the stern
    y = GROUND
    for i in range(2):
        out += plank(470 + RNG_GRAIN.uniform(-4, 4), 560 + RNG_GRAIN.uniform(-4, 4), y, 6, 1)
        y -= 6
    for x in (902, 972):
        out += [art.path(f"M{x - 12} {GROUND} L{x} {GROUND - 40} L{x + 12} {GROUND}", 2.2), art.path(f"M{x - 8} {GROUND - 26} L{x + 8} {GROUND - 26}", 1.2)]
    for i in range(3):
        out += plank(884 + i * 2, 994 - i * 2, GROUND - 42 - i * 6, 6, 1)
    return out


def frame_sheet_items(variant="a"):
    RNG_GRAIN.seed(2612)
    return ground_wide() + frame_items(variant)


def ground_wide():
    out = [art.path(f"M180 {GROUND} L1010 {GROUND}", 1.8),
           art.hatch([(184, GROUND), (1006, GROUND), (994, GROUND + 18), (196, GROUND + 18)], 25, 5.5, 0.7, art.INK_SOFT, 0.55)]
    for x in range(200, 1000, 37):
        out.append(art.dot(x + RNG_GRAIN.uniform(-8, 8), GROUND + RNG_GRAIN.uniform(4, 14), RNG_GRAIN.uniform(0.8, 1.8), art.INK_SOFT, 0.7))
    return out


def frame_build(variant="a"):
    """Being built, over the bare timber: the frame pale with red hatching over the hull's place, its pencil lines over it."""
    RNG_GRAIN.seed(2612)
    items = frame_items(variant)
    return ink_pale(items, 0.35) + [art.hatch(frame_outline(), 45, 4.2, 1.1, CHALK, 0.6)] + pencil_of(items)


def ship_items():
    """Every ink item of the base barge's drawing, for a pencil ghost of it."""
    hull_pre, hull_post, _, _ = hull_split()
    rear, _ = rear_split()
    return art.balloon_placed() + art.rigging() + hull_pre + belt() + trim() + bombs() + hull_post + rear[:gear_start(rear)] + drive() + art.malakai()


def ghost_of(items, op=0.42):
    """The ship as a faint construction drawing: pencil lines only, no fills, no hatching."""
    import re
    text = "".join(i for i in items if "clip-path" not in i)
    text = re.sub(r'stroke="#[0-9a-fA-F]{6}"', f'stroke="{PENCIL}"', text)
    text = re.sub(r'fill="#[0-9a-fA-F]{6}"', 'fill="none"', text)
    text = re.sub(r'stroke-width="([0-9.]+)"', lambda m: f'stroke-width="{min(1.0, max(0.5, float(m.group(1)) * 0.55)):.2f}"', text)
    return [f'<g opacity="{op}">{text}</g>']


def hull_outline_area():
    """The ship's hull and balloon as polygons, for the hatching of the hull while it is built."""
    balloon = [(x, 26 + 0.92 * (168 - art.balloon_half(x))) for x in range(128, 933, 12)] + [(x, 26 + 0.92 * (168 + art.balloon_half(x))) for x in range(932, 127, -12)]
    return [art.hull_outline(), balloon]


def sheet(drawing_items):
    """A drawing of the panel: parchment, the faint notes, these items in ink (as crew_ui_art.blueprint())."""
    import numpy as np
    from PIL import Image
    w, h = round(art.DRAW_W * art.SCALE), round(art.DRAW_H * art.SCALE)
    sketch = art.paint("web_sketch", art.svg_page(art.sketches(), "#ffffff"), w, h)
    drawing = art.paint("web_drawing", art.svg_page(drawing_items, "#ffffff"), w, h)
    paper = art.parchment(w, h)
    ink_a = np.asarray(sketch.convert("RGB"), float) / 255
    ink_b = np.asarray(drawing.convert("RGB"), float) / 255
    rng = np.random.default_rng(99)
    patchy = np.clip(0.90 + 0.09 * art.noise((h, w), 1.3, rng) + 0.05 * art.noise((h, w), 20, rng), 0.55, 1.0)[..., None]
    out = paper * ink_a
    white = ink_b >= 0.985
    out = out * np.where(white, 1.0, 1 - (1 - ink_b) * patchy)
    return Image.fromarray(out.clip(0, 255).astype("uint8"), "RGB")


def barge_build():
    """The hull's second level being built, over the frame: the base barge pale with red hatching over its hull and balloon, its pencil lines over it.
    Moved by FRAME_DY onto the frame, so it rises out of the frame's own lines (the built barge sheet stands at the drawing's own height)."""
    items = ship_items()
    hull, balloon = hull_outline_area()
    body = ink_pale(items, 0.3) + [art.hatch(hull, 45, 4.2, 1.1, CHALK, 0.55), art.hatch(balloon, 45, 4.2, 1.1, CHALK, 0.45)] + pencil_of(items)
    return [f'<g transform="translate(0 {FRAME_DY})">' + "".join(body) + "</g>"]


# ---------------- where Malakai stands: a small plan of the ship from above with a mark on each side, and his figure on the drawing ----------------
# The user's decision (docs/design/barge-upgrades-ideas.md, «Место Малакая»): a deckhand takes the wheel, Malakai stands as a shooter on one side, the
# player picks which. The plan sits in the drawing's lower left corner, bow up, the port side on the left as seen from above; the marks are buttons of
# their own (web/js/panel.js). The drawing shows the ship's port side (bow to the left), so Malakai on the port side is drawn in ink at a rifle place,
# on the starboard side the same figure in pencil: he stands behind the near side, out of sight of a true side view.
PLAN = (40, 560, 80, 150)        # x, y, w, h of the plan in units of the drawing
MARK = 22                        # a mark's size in units of the drawing
MALAKAI_AT = (492, 456)          # a rifle place of the waist (crew_ui_art.RIFLE_PLACES), on the rail


def plan_items():
    x0, y0, w, h = PLAN
    cx = x0 + w / 2
    bow, stern = y0 + 8, y0 + h - 10
    half = 22
    outline = [(cx, bow), (cx + half * 0.55, bow + 22), (cx + half, bow + 52), (cx + half, stern - 26), (cx + half * 0.8, stern - 6), (cx, stern),
               (cx - half * 0.8, stern - 6), (cx - half, stern - 26), (cx - half, bow + 52), (cx - half * 0.55, bow + 22)]
    out = [art.shape(art.smooth(outline, True), art.PAPER), art.path(art.smooth(outline, True), 1.8)]
    inner = [(cx + (px - cx) * 0.8, bow + 8 + (py - bow) * 0.9) for px, py in outline]
    out.append(art.path(art.smooth(inner, True), 0.9, art.INK, op=0.8))
    for dx in (-8, 0, 8):
        out.append(art.path(f"M{cx + dx} {bow + 30} L{cx + dx} {stern - 16}", 0.6, art.INK, op=0.6))
    # the boiler tower and the wheel at the stern, the bow's figure
    out += [art.shape(art.poly([(cx - 9, stern - 34), (cx + 9, stern - 34), (cx + 9, stern - 20), (cx - 9, stern - 20)], True), "#e8c692"),
            art.path(art.poly([(cx - 9, stern - 34), (cx + 9, stern - 34), (cx + 9, stern - 20), (cx - 9, stern - 20)], True), 1.2),
            art.circle(cx, stern - 44, 4, 1.0), art.path(f"M{cx} {bow} L{cx} {bow - 6}", 1.6)]
    out.append(art.hatch(outline[2:5] + [(cx, stern), (cx, bow + 52)], 50, 4, 0.6, art.INK_SOFT, 0.45))
    return out


def mark_items(kind):
    """A mark on a side of the plan, drawn in a box of MARK x MARK: empty ring, ring lit by the mouse, Malakai seen from above (a head with the slayer's
    crest)."""
    c = MARK / 2
    if kind == "selected":
        return [art.circle(c, c, c - 1.5, 1.6, art.INK, "#e8c692"), art.circle(c, c + 1, 5.5, 1.0, art.INK, "#dcae74"),
                art.shape(f"M{c - 2} {c - 7} L{c + 2} {c - 7} L{c + 1.4} {c + 6} L{c - 1.4} {c + 6} Z", "#c8501a"), art.path(f"M{c} {c - 7} L{c} {c + 6}", 0.6)]
    fill = "#f3d9a4" if kind == "hover" else "#fff1dc"
    return [art.circle(c, c, c - 1.5, 1.6 if kind == "hover" else 1.2, art.INK, fill), art.circle(c, c, c - 6, 0.7, art.INK, op=0.6)]


def malakai_figure():
    """Malakai as a shooter at the rail: the dwarf of the crew layers in his colours, with the slayer's crest."""
    x, y = MALAKAI_AT
    out = art.dwarf(x, y, 1.05, -1, True, helm="#c8501a", beard="#c8501a")
    out.append(art.shape(f"M{x - 2} {y - 26} L{x + 2} {y - 26} L{x + 1} {y - 38} L{x - 1} {y - 38} Z", "#c8501a"))
    out.append(art.path(f"M{x - 2} {y - 26} L{x} {y - 39} L{x + 2} {y - 26}", 0.9))
    return out


def side_art(places):
    """The plan, its three marks, Malakai near and far."""
    from PIL import Image
    layer("plan_ship", plan_items(), places)
    for kind in ("normal", "hover", "selected"):
        s = 4
        im = art.paint(f"web_mark_{kind}", art.svg_page(mark_items(kind), w=MARK, h=MARK, scale=s, filtered=False), MARK * s, MARK * s)
        im.save(OUT / f"mark_{kind}.png", optimize=True)
    figure = malakai_figure()
    layer("malakai_near", figure, places)
    layer("malakai_far", pencil_of(figure), places)
    return {"plan": PLAN, "mark": MARK, "marks": {"left": [PLAN[0] + 4, PLAN[1] + 62], "right": [PLAN[0] + PLAN[2] - 4 - MARK, PLAN[1] + 62]}}


def tree_line():
    """The brass of the lines between the nodes of the tree of buildings (web/js/panel.js): one colour, stretched by the panel; the copper of the plates' edge."""
    from PIL import Image
    Image.new("RGBA", (4, 4), (197, 139, 74, 255)).save(OUT / "tree_line.png")


def node_back():
    """The parchment under a node's icon in the tree of buildings: a clean piece of the drawing's own paper (blueprint_planks.png, above the timber)."""
    from PIL import Image
    S = art.SCALE
    Image.open(OUT / "blueprint_planks.png").crop((round(470 * S), round(200 * S), round(530 * S), round(260 * S))).resize((96, 96)).save(OUT / "node_back.png", optimize=True)


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
    # the start of the ship: the bare timber of layout b, a quarter larger round the middle of the ground so the sheet is less empty (last: the drawings above
    # keep their random hatching)
    sheet([f'<g transform="translate(560 {GROUND}) scale(1.25) translate(-560 -{GROUND})">' + "".join(planks("b")) + "</g>"]).save(OUT / "blueprint_planks.png", optimize=True)
    # the hull's first level built: the frame on the slip (variant a of build/web/shots/frame_variants.png), and its stage of being built over the timber
    sheet(frame_sheet_items("a")).save(OUT / "blueprint_frame.png", optimize=True)
    layer("frame_build", frame_build("a"), places)
    parts["frame"] = {"pencil": None, "build": "frame_build", "ink": None}
    (OUT / "layers.json").write_text(json.dumps(json.loads((OUT / "layers.json").read_text(encoding="utf-8")) | {"places": places, "parts": parts}, indent=1), encoding="utf-8")
    tree_line()
    node_back()
    # the hull's second level being built over the frame (last: the drawings above keep their random hatching)
    layer("barge_build", barge_build(), places)
    parts["barge"] = {"pencil": None, "build": "barge_build", "ink": None}
    # where Malakai stands: the plan with its marks and his figure (last, as above)
    side = side_art(places)
    (OUT / "layers.json").write_text(json.dumps(json.loads((OUT / "layers.json").read_text(encoding="utf-8")) | {"places": places, "parts": parts, "malakai_side": side}, indent=1), encoding="utf-8")
    for f in sorted(OUT.glob("*.png")):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
