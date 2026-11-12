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
    drawing = art.paint("web_drawing", art.svg_page(art.balloon_placed() + art.rigging() + hull_items + rear_items + helmsman(), "#ffffff"), w, h)
    paper = art.parchment(w, h)
    ink_a = np.asarray(sketch.convert("RGB"), float) / 255
    ink_b = np.asarray(drawing.convert("RGB"), float) / 255
    rng = np.random.default_rng(99)
    patchy = np.clip(0.90 + 0.09 * art.noise((h, w), 1.3, rng) + 0.05 * art.noise((h, w), 20, rng), 0.55, 1.0)[..., None]
    out = paper * ink_a
    white = ink_b >= 0.985
    out = out * np.where(white, 1.0, 1 - (1 - ink_b) * patchy)
    return Image.fromarray(out.clip(0, 255).astype("uint8"), "RGB")


def helmsman():
    """A dwarf of the crew at the wheel (the user's decision: Malakai stands as a shooter at a side). crew_ui_art.malakai()'s wheel and pose, a plain
    coat, an iron helmet instead of the slayer's crest, a brown beard."""
    out = []
    x, y = 684, 372
    out.append(art.circle(x - 16, y + 8, 12, 1.6))
    for a_ in range(0, 360, 60):
        ca, sa = math.cos(math.radians(a_)), math.sin(math.radians(a_))
        out.append(art.path(f"M{x - 16:.1f} {y + 8:.1f} L{x - 16 + 12 * ca:.1f} {y + 8 + 12 * sa:.1f}", 1.0))
    out.append(art.shape(f"M{x - 5} {y + 28} L{x + 8} {y - 6} L{x + 19} {y + 28} Z", "#8a5428", 0.9))
    out.append(art.path(f"M{x - 5} {y + 28} L{x + 8} {y - 6} L{x + 19} {y + 28}", 1.4))
    out.append(art.circle(x + 8, y - 12, 6, 1.2, art.INK, "#f1d5a8"))
    out.append(art.path(f"M{x + 1.5} {y - 13} A 6.5 6.5 0 0 1 {x + 14.5} {y - 13} Z", 1.1, art.INK, "#6d6a62"))
    out.append(art.path(f"M{x + 8} {y - 19.5} L{x + 8} {y - 22}", 1.2))
    out.append(art.shape(f"M{x + 3} {y - 9} Q {x + 5} {y + 7} {x + 8} {y + 9} Q {x + 11} {y + 7} {x + 13} {y - 9} Z", "#9c4f20"))
    return out


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
    return art.balloon_placed() + art.rigging() + hull_pre + belt() + trim() + bombs() + hull_post + rear[:gear_start(rear)] + drive() + helmsman()


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
MARK = 34                        # a mark's size in units of the drawing: the portrait's face must read
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
    """A mark on a side of the plan, a ring of MARK x MARK: empty, lit by the mouse, or the copper ring round Malakai's portrait (the portrait is the
    game's own picture, laid in by the panel)."""
    c = MARK / 2
    if kind == "selected":
        return [art.circle(c, c, c - 1.5, 3.0, "#b5692e", "#2b2118"), art.circle(c, c, c - 1.5, 1.2, art.INK)]
    fill = "#f3d9a4" if kind == "hover" else "#fff1dc"
    return [art.circle(c, c, c - 1.5, 1.8 if kind == "hover" else 1.3, art.INK, fill), art.circle(c, c, c - 7, 0.7, art.INK, op=0.5),
            art.path(f"M{c - 4} {c} L{c + 4} {c} M{c} {c - 4} L{c} {c + 4}", 0.8, art.INK, op=0.5)]


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
    for kind in ("normal", "hover", "selected", "locked"):      # locked: the empty ring; the panel dims it while the barge is only ordered
        s = 4
        im = art.paint(f"web_mark_{kind}", art.svg_page(mark_items("normal" if kind == "locked" else kind), w=MARK, h=MARK, scale=s, filtered=False), MARK * s, MARK * s)
        im.save(OUT / f"mark_{kind}.png", optimize=True)
    figure = malakai_figure()
    layer("malakai_near", figure, places)
    layer("malakai_far", pencil_of(figure), places)
    # Malakai on the barge being built: over the hatched barge (moved by FRAME_DY as it is), near side pale ink under pencil, far side pencil only
    layer("malakai_near_build", [f'<g transform="translate(0 {FRAME_DY})">' + "".join(ink_pale(figure, 0.45) + pencil_of(figure)) + "</g>"], places)
    layer("malakai_far_build", [f'<g transform="translate(0 {FRAME_DY})" opacity="0.7">' + "".join(pencil_of(figure)) + "</g>"], places)
    phases = side_glow(GLOW_VARIANT)
    cx, half, y = PLAN[0] + PLAN[2] / 2, 22, PLAN[1] + 52
    return {"plan": PLAN, "mark": MARK, "marks": {"left": [cx - half - MARK / 2, y], "right": [cx + half - MARK / 2, y]},
            "portrait": "ui/portraits/round/mtb_malakai.png", "portrait_inset": 4, "glow": {"phases": phases, "size": GLOW_SIZE, "step_ms": 110}}


def side_glow(variant="a", out_prefix="glow"):
    """The warm ring round an empty side mark while the player has not chosen a side yet: a thin ring hugging the mark's edge, its phases switched by
    the panel's timer (as the game blinks a tutorial's button). The picture is GLOW_SIZE times the mark; the mark's ring edge is at 0.73 of its half.
    a: 8 phases, a narrow ring right on the edge, alpha 0.45..0.85; b: 6 phases, a little wider and softer, alpha 0.35..0.65, more golden."""
    import numpy as np
    from PIL import Image
    n = 128
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(xx - n / 2 + 0.5, yy - n / 2 + 0.5) / (n / 2)
    centre, width, phases, lo, hi, rgb = {"a": (0.78, 0.035, 8, 0.45, 0.85, (255, 160, 60)),
                                          "b": (0.80, 0.05, 6, 0.35, 0.65, (255, 196, 90))}[variant]
    ring = np.exp(-((r - centre) / width) ** 2)
    for i in range(phases):
        k = lo + (hi - lo) * (0.5 - 0.5 * math.cos(2 * math.pi * i / phases))
        rgba = np.zeros((n, n, 4), np.uint8)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = rgb
        rgba[..., 3] = np.clip(ring * 255 * k, 0, 255).astype(np.uint8)
        Image.fromarray(rgba, "RGBA").save(OUT / f"{out_prefix}_{i}.png", optimize=True)
    return phases


GLOW_SIZE = 1.3
GLOW_VARIANT = "a"

def pub_seen_through(variant=None):
    """The pub cabin seen through the hull's side, in the middle between the panel's solid box and its dashed place: a thin even outline (outside the
    ink's wobble, so it stays straight), a light warm wash, the men, table and barrels of crew_ui_art.occ_pub in ink, the hull's lines showing a little.
    a: plain line, wash 0.45, contents full; b: plain line and the deck beam's shade on top, wash 0.38; c: a fine dashed line, wash 0.42."""
    variant = variant or PUB_VARIANT
    x0, y0, x1, y1 = art.PUB
    inside = art.occ_pub()[2:]          # without occ_pub's solid box and dark beam
    wash, line = {"a": (0.45, ""), "b": (0.38, ""), "c": (0.42, 'stroke-dasharray="3 1.6"')}[variant]
    out = [f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="{art.PAPER}" opacity="{wash}"/>']
    if variant == "b":
        out.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="9" fill="#7a5128" opacity="0.35"/>')
    out.append(f'<g filter="url(#ink)">{"".join(inside)}</g>')
    out.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" fill="none" stroke="{art.INK}" stroke-width="1.3" opacity="0.9" {line}/>')
    return out


PUB_VARIANT = "b"


def layer_plain(name, parts, places):
    """As layer(), without the wobble over the whole picture: a part that wobbles marks it itself (<g filter="url(#ink)">)."""
    w, h = round(art.DRAW_W * art.SCALE), round(art.DRAW_H * art.SCALE)
    im = art.paint("web_" + name, art.svg_page(parts, filtered=False), w, h)
    box = im.getbbox()
    pad = 2
    box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, w), min(box[3] + pad, h))
    im.crop(box).save(OUT / f"{name}.png", optimize=True)
    places[name] = [round(box[0] / art.SCALE, 2), round(box[1] / art.SCALE, 2), round((box[2] - box[0]) / art.SCALE, 2), round((box[3] - box[1]) / art.SCALE, 2)]


def branch_selected_frames():
    """The frame of a selected node of a branch: the branch's colour, lighter, a bright inner rim, so the selection keeps the branch's colour."""
    from PIL import Image, ImageDraw
    colours = json.loads((REPO / "data" / "crew_options.json").read_text(encoding="utf-8"))["card_frames"]
    for name, pair in colours.items():
        if name.startswith("_"):
            continue
        light = tuple(min(255, v + 70) for v in pair[0]) + (255,)
        n = 148
        im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, n - 1, n - 1), outline=(30, 14, 0, 255), width=3)
        d.rectangle((3, 3, n - 4, n - 4), outline=tuple(pair[0]) + (255,), width=8)
        d.rectangle((11, 11, n - 12, n - 12), outline=light, width=4)
        d.rectangle((15, 15, n - 16, n - 16), outline=(255, 250, 225, 200), width=2)
        im.save(OUT / f"branch_frame_{name}_selected.png", optimize=True)

def branch_frames():
    """The frame of a side branch's nodes in the tree and its lines, one per colour of data/crew_options.json, card_frames (the crew cards' frames of the mod:
    gold for the riflemen, blue for the guns, ...): a square ring the slot's size, light outside, dark inside, light corners as the cards'."""
    from PIL import Image, ImageDraw
    colours = json.loads((REPO / "data" / "crew_options.json").read_text(encoding="utf-8"))["card_frames"]
    for name, pair in colours.items():
        if name.startswith("_"):
            continue
        light, dark = tuple(pair[0]) + (255,), tuple(pair[1]) + (255,)
        n = 148
        im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle((0, 0, n - 1, n - 1), outline=(30, 14, 0, 255), width=3)
        d.rectangle((3, 3, n - 4, n - 4), outline=light, width=6)
        d.rectangle((9, 9, n - 10, n - 10), outline=dark, width=2)
        corner = tuple(min(255, v + 60) for v in pair[0]) + (255,)
        for x, y in ((0, 0), (n - 18, 0), (0, n - 18), (n - 18, n - 18)):
            d.rectangle((x, y, x + 17, y + 17), fill=corner, outline=(30, 14, 0, 255), width=2)
        im.save(OUT / f"branch_frame_{name}.png", optimize=True)
        Image.new("RGBA", (4, 4), light).save(OUT / f"tree_line_{name}.png")


def aboard_frames():
    """The second variant of marking a crew aboard on its small unit card in the tree (web/js/panel.js, ?aboard=outline): a thin line of the crew group's
    colour laid over the game's own frame, inside the card's 23 x 50, drawn four times larger. The page's default is the game's frame recoloured
    (tools/web_export.py, recolour_card_frames)."""
    from PIL import Image, ImageDraw
    colours = json.loads((REPO / "data" / "crew_options.json").read_text(encoding="utf-8"))["card_frames"]
    for name, pair in colours.items():
        if name.startswith("_"):
            continue
        w, h = 92, 200
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle((2, 2, w - 3, h - 3), outline=tuple(pair[0]) + (255,), width=5)
        im.save(OUT / f"aboard_outline_{name}.png", optimize=True)


# ---------------- the riflemen's place on the drawing: the area the player clicks to choose the rifle crew ----------------
# The five rifle places of the near side beside Malakai's own (crew_ui_art.RIFLE_PLACES without MALAKAI_AT's): two at the bow rail, three at the waist.
CREW_PLACES = [(x, y) for x, y in art.RIFLE_PLACES if (x, y + 2) != MALAKAI_AT]


# The figures of the rifle crews are drawn from the game's models (rendered front and side into build/crew_models/<kind>_ref.png; nothing of the
# game is kept in the repository). What the models are, and what tells a kind apart when the figure is 20 px tall on the screen:
#   a dwarf        1.4 to 1.5 high and 1.4 across the hanging arms; the head with its beard is a third of the height, the shoulders nearly as wide as
#                  the dwarf is tall, the legs a quarter. Behind the rail he shows from the belt up: a wide block of shoulders, a big head set low.
#   pirates        dwf_slayer_pirates: a bare bald head with a headscarf knotted behind, a huge moustache standing out to both sides, a beard in
#                  thick plaits over a bare chest, bracers; no helm, no crest. A flintlock pistol with a flared muzzle, half his height, in one hand, a broad cutlass nearly his height in the other.
#                  Told by: bare skin, the moustache's bar across the face, the short gun held out and the blade raised.
#   quarrellers, thunderers, grudge-rakers    one body (dwf_warriors): a round helm with two horns up and a spike, a plaited beard to the belt, mail,
#                  a skirt. Told only by the weapon: the crossbow (0.9 long, its bow 0.77 across), the rifle (1.3, nearly his height, thin), the
#                  grudge-raker (1.4, a thick bundle of barrels with a drum behind).
#   torpedoes      dwf_irondrakes: a flat-topped closed helm with eye slits and no horns, a square beard of plates, heavy pauldrons, an apron. The
#                  drakegun is a fat tank 1.2 long with a thin nozzle. Told by: the flat helm, the square shoulders, the barrel-thick gun.
# Colours from the models' own base colour textures (decoded into build/crew_models/tex, not kept): the pirate's skin a warm pink tan, his beard
# ginger, his headscarf red (it is on the head's texture, with the knot's tails in the mesh); the warriors' mail silver grey with gold trim, the
# beard brown, the helm steel with bone horns; the irondrake's plate blue steel with gold, his drakegun copper; the thunderers' rifle grey steel on
# a brown stock; the grudge-raker steel barrels under much brass.
SKIN, GINGER, SCARF = "#d48e66", "#b5622a", "#a8261a"
MAIL, GOLD, BROWN, BONE, HELM = "#8f9296", "#c9a23c", "#6e4a2a", "#e8dcc0", "#7d7870"
PLATE, DRAKE, WOOD, BARREL = "#66727c", "#a8623c", "#6b4320", "#3d3a36"


def crew_figure(kind, x, y, s=1.0, detail=True):
    """A dwarf of a rifle crew at the rail, from the belt up, turned to the bow (left), after the game's model of its unit (see above): sloping
    shoulders wider than the head, the arms holding the weapon. detail False: without the small strokes (plaits, bands, trim)."""
    P = lambda dx, dy: f"{x + dx * s:.1f} {y + dy * s:.1f}"
    line = lambda d, w=1.0, fill="none", color=art.INK: art.path(d, w * s, color, fill)

    def limb(d, colour, w=3.4):         # an arm: the colour inside an ink line
        return [line(d, w + 1.6), line(d, w, color=colour)]

    out = []
    warrior = kind in ("quarrellers", "thunderers", "rakers")
    cloth = {"pirates": SKIN, "torpedoes": PLATE}.get(kind, MAIL)
    # the far arm and what lies behind the body
    if kind == "pirates":
        # the far arm raised with the cutlass (dwf_slayer_pirate_sword_1h: a broad straight blade nearly his height, the tip cut slanting, a small
        # guard); the pistol is in the other hand
        out.append(line(f"M{P(14.5, -19)} L{P(20, -37)} L{P(24.5, -38)} L{P(18.5, -18)} Z", 1.0, "#b9bcc0"))
        out.append(line(f"M{P(12, -17.5)} L{P(21, -19.5)}", 1.8, color=BARREL))
        out += limb(f"M{P(9, -12)} L{P(15, -11)} L{P(16.5, -17)}", SKIN)
    # the body: shoulders sloping from the neck, wider than the head
    out.append(line(f"M{P(-8, 0)} L{P(-10, -7)} Q {P(-12.5, -13)} {P(-5, -15.5)} L{P(4, -15.5)} Q {P(12, -13)} {P(10, -7)} L{P(8, 0)} Z", 1.1, cloth))
    if kind == "pirates":
        out.append(line(f"M{P(-8.4, -1.6)} L{P(8.4, -1.6)}", 2.0, color=WOOD))                       # the wide belt
    if warrior and detail:
        out.append(line(f"M{P(-9.6, -5)} L{P(9.6, -5)}", 0.8, color=GOLD))
    if kind == "torpedoes":             # the pauldrons, rounded plates with a gold edge
        for sx in (-1, 1):
            out.append(line(f"M{P(sx * 5, -16.5)} Q {P(sx * 13, -17.5)} {P(sx * 13.5, -9)} L{P(sx * 7, -9.5)} Z", 1.0, PLATE))
            out.append(line(f"M{P(sx * 13.5, -9)} L{P(sx * 7, -9.5)}", 1.1, color=GOLD))
    # the head, set low
    out.append(art.circle(x - 1 * s, y - 19.5 * s, 5.4 * s, 1.0 * s, art.INK, SKIN if kind == "pirates" else "#e3b08a"))
    if kind == "pirates":
        # the red headscarf over the skull with its knot behind; the plaited ginger beard down the bare chest; the moustache, wider than the head
        out.append(line(f"M{P(-6.4, -21)} A {5.4 * s:.1f} {5.4 * s:.1f} 0 0 1 {P(4.4, -21)} Z", 0.9, SCARF))
        out.append(line(f"M{P(4.2, -22)} L{P(8.5, -24.5)} M{P(4.2, -22)} L{P(9, -20.5)}", 1.3, color=SCARF))
        out.append(art.dot(x - 3.4 * s, y - 19.6 * s, 0.8 * s))
        out.append(line(f"M{P(-4.5, -15)} L{P(2.5, -15)} L{P(1.6, -4)} L{P(-1, -7)} L{P(-3.6, -4)} Z", 0.9, GINGER))
        out.append(line(f"M{P(-1, -17.2)} Q {P(-7, -14.2)} {P(-13, -19.5)} M{P(-1, -17.2)} Q {P(5, -14.2)} {P(11, -19.5)}", 3.4))
        out.append(line(f"M{P(-1, -17.2)} Q {P(-7, -14.2)} {P(-13, -19.5)} M{P(-1, -17.2)} Q {P(5, -14.2)} {P(11, -19.5)}", 2.0, color=GINGER))
    elif warrior:
        # the steel helm with its gold rim, the spike, two bone horns turned up; the brown beard to the belt
        out.append(line(f"M{P(-7, -20.5)} A {6 * s:.1f} {6.4 * s:.1f} 0 0 1 {P(5, -20.5)} Z", 1.0, HELM))
        out.append(line(f"M{P(-7, -20.5)} L{P(5, -20.5)}", 1.2, color=GOLD))
        out.append(line(f"M{P(-1, -26.5)} L{P(-1, -30)}", 1.4))
        for sx, hx in ((-1, -6.5), (1, 4.5)):
            d = f"M{P(hx, -22.5)} Q {P(hx + sx * 5, -23.5)} {P(hx + sx * 4, -30)}"
            out += [line(d, 2.6), line(d, 1.3, color=BONE)]
        out.append(line(f"M{P(-6, -17.5)} L{P(4, -17.5)} L{P(2.4, -5)} L{P(-1, -2.5)} L{P(-4.4, -5)} Z", 0.9, BROWN))
        if detail:
            out.append(line(f"M{P(-1, -16)} L{P(-1, -5)}", 0.6, color=BONE))
    else:
        # the irondrake: a flat-topped closed helm with a gold band and a slit, no horns; the beard a square below it
        out.append(line(f"M{P(-8, -18)} L{P(-8, -27)} L{P(6, -27)} L{P(6, -18)} Z", 1.1, PLATE))
        out.append(line(f"M{P(-8, -25)} L{P(6, -25)}", 1.2, color=GOLD))
        out.append(line(f"M{P(-6, -21.8)} L{P(-0.5, -21.8)}", 1.5))
        out.append(line(f"M{P(-6.5, -18)} L{P(4.5, -18)} L{P(4.5, -9)} L{P(-6.5, -9)} Z", 0.9, GINGER))
    # the near arm and the weapon before the body
    if kind == "pirates":
        # the near arm held out level, the pistol half his height, its muzzle flared
        out += limb(f"M{P(-9, -12)} L{P(-16, -11)}", SKIN)
        out.append(line(f"M{P(-15, -8)} L{P(-16.5, -12)} L{P(-27, -13)}", 2.3, color=BARREL))
        out.append(line(f"M{P(-27.5, -15.2)} L{P(-27.5, -10.8)}", 1.7, color=BARREL))
    elif kind == "quarrellers":
        # the crossbow level before him: the brown stock, the steel bow across its end, the string
        out.append(line(f"M{P(5, -8.5)} L{P(-21, -11.5)}", 3.4))
        out.append(line(f"M{P(5, -8.5)} L{P(-21, -11.5)}", 2.0, color=WOOD))
        out.append(line(f"M{P(-18, -21.5)} Q {P(-26.5, -11.5)} {P(-19, -2)}", 2.0, color=BARREL))
        out.append(line(f"M{P(-18, -21.5)} L{P(-9, -10)} L{P(-19, -2)}", 0.6))
        out += limb(f"M{P(-9, -12)} L{P(-12, -8.5)}", MAIL, 3.0) + limb(f"M{P(9, -12)} L{P(4, -7)}", MAIL, 3.0)
    elif kind == "thunderers":
        # the long rifle at the shoulder, aimed: the brown stock under the cheek, a thin steel barrel almost his height, gold bands
        out.append(line(f"M{P(9, -12)} L{P(2, -14.5)}", 4.6))
        out.append(line(f"M{P(9, -12)} L{P(2, -14.5)}", 3.2, color=WOOD))
        out.append(line(f"M{P(2, -14.5)} L{P(-33, -18.5)}", 1.7, color=BARREL))
        if detail:
            out.append(line(f"M{P(-12, -17.4)} L{P(-12, -14.8)} M{P(-24, -18.8)} L{P(-24, -16.2)}", 1.2, color=GOLD))
        out += limb(f"M{P(-9, -12)} L{P(-15, -14.5)}", MAIL, 3.0) + limb(f"M{P(9, -11)} L{P(5, -13)}", MAIL, 3.0)
    elif kind == "rakers":
        # the grudge-raker at the hip: a thick bundle of dark barrels bound in brass, a big brass drum by the hand
        for d in (-2.6, 0, 2.6):
            out.append(line(f"M{P(3, -6.5 + d)} L{P(-26, -8.5 + d)}", 2.0, color=BARREL))
        out.append(line(f"M{P(-12, -11.5)} L{P(-12, -3.8)} M{P(-22, -12)} L{P(-22, -4.4)}", 1.8, color=GOLD))
        out.append(art.circle(x - 1 * s, y - 6.5 * s, 4.8 * s, 1.0 * s, art.INK, GOLD))
        out += limb(f"M{P(-9, -12)} L{P(-9, -7)}", MAIL, 3.0) + limb(f"M{P(9, -12)} L{P(5, -7)}", MAIL, 3.0)
    else:
        # the drakegun at the hip: a fat copper tank, a thin nozzle with a bright head far out
        out.append(line(f"M{P(9, -1.5)} L{P(9, -8.5)} Q {P(0, -11)} {P(-11, -10.5)} L{P(-11, -3.5)} Q {P(0, -1)} {P(9, -1.5)} Z", 1.1, DRAKE))
        out.append(line(f"M{P(-11, -7)} L{P(-26, -8.5)}", 2.0, color=BARREL))
        out.append(art.dot(x - 27 * s, y - 8.6 * s, 2.4 * s, GOLD))
        if detail:
            out.append(line(f"M{P(3, -9.6)} L{P(3, -1.6)} M{P(-5, -10.6)} L{P(-5, -2.6)}", 1.0, color=GOLD))
    return out


# The player's page is shown smaller than the game's 1600 x 900: about 0.6 on the user's screen, the drawing's unit then 0.62 px. What must be seen
# at once is sized for a scale of 0.5: a line of CREW_LINE units is 1.5 px there, the tag's text of CREW_TEXT units 11 px.
CREW_LINE, CREW_TEXT = 2.9, 21.5
CREW_TAG = (478, 352, 150, 36)          # the tag over the waist, between the two nets: x, y, w, h
LIGHT = "#f3dfb4"                       # clean light parchment: an empty place cut out of the drawing's tone


def crew_ghost(x, y, s=0.9, variant="fill"):
    """A place nobody stands at: the outline of a dwarf at the rail. fill: a light parchment cut-out under a firm dashed ink line, seen at any scale;
    pencil: the first version, thin dashed graphite (too faint on the user's screen)."""
    body = f"M{x - 8 * s:.1f} {y:.1f} L{x - 7 * s:.1f} {y - 13 * s:.1f} L{x + 7 * s:.1f} {y - 13 * s:.1f} L{x + 8 * s:.1f} {y:.1f} Z"
    head = f"M{x - 5.5 * s:.1f} {y - 19 * s:.1f} A {5.5 * s:.1f} {5.5 * s:.1f} 0 1 1 {x + 5.5 * s:.1f} {y - 19 * s:.1f} A {5.5 * s:.1f} {5.5 * s:.1f} 0 1 1 {x - 5.5 * s:.1f} {y - 19 * s:.1f}"
    if variant == "pencil":
        return [art.path(body + " " + head, 1.1, PENCIL, extra='stroke-dasharray="3 2.4"', op=0.9)]
    return [art.path(body + " " + head, CREW_LINE, art.INK, LIGHT, extra='stroke-dasharray="4.5 3"')]


def crew_brackets(pad=0, w=CREW_LINE, color=None, op=1.0):
    """Dashed ink frames round the two rows of places (the bow rail, the waist), as a zone marked out on a drawing."""
    out = []
    for group in (CREW_PLACES[:2], CREW_PLACES[2:]):
        x0, x1 = min(x for x, _ in group) - 16 - pad, max(x for x, _ in group) + 16 + pad
        y0, y1 = min(y for _, y in group) - 30 - pad, max(y for _, y in group) + 5 + pad
        out.append(art.path(art.poly([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True), w, color or art.INK, extra='stroke-dasharray="9 6"', op=op))
    return out


def crew_tag(sign="plus", light=False):
    """The tag of the place, on a leader down to the waist: a slip of light parchment in an ink line with the group's name and a sign in a ring.
    plus: nobody yet, the place waits for a choice (as an empty slot of the game); swap: a crew stands, it can be changed."""
    x, y, w, h = CREW_TAG
    if sign == "wait":
        w += 24             # room for the turns beside the hourglass
    fill = "#fff0cc" if light else LIGHT
    out = [art.path(f"M{x + 74} {y + h} L{x + 71} {y + h + 30}", CREW_LINE * 0.8),          # the leader down to a place of the waist, clear of Malakai
           art.dot(x + 71, y + h + 32, 3.2),
           art.path(f"M{x + 6} {y} L{x + w} {y} L{x + w} {y + h} L{x + 6} {y + h} L{x} {y + h - 7} L{x} {y + 7} Z", CREW_LINE, art.INK, fill),
           f'<text x="{x + 12}" y="{y + h - 10.5}" font-family="Palatino Linotype, Book Antiqua, Georgia, serif" font-weight="bold" font-size="{CREW_TEXT}" fill="{art.INK}">Стрелки</text>']
    cx, cy, r = x + w - 19, y + h / 2, 11.5
    if sign == "wait":
        # a hire on its way: an hourglass and the turns left, in the tag's own ink and letters, in the sign's place (the ring drawn out into a pill)
        px0, px1 = x + w - 55, x + w - 7
        out.append(art.path(f"M{px0 + r} {cy - r} L{px1 - r} {cy - r} A {r} {r} 0 0 1 {px1 - r} {cy + r} L{px0 + r} {cy + r} A {r} {r} 0 0 1 {px0 + r} {cy - r} Z", CREW_LINE * 0.8, art.INK, "#e9b96a"))
        hx = px0 + 14
        out.append(art.path(f"M{hx - 5.5} {cy - 7} L{hx + 5.5} {cy - 7} L{hx - 5.5} {cy + 7} L{hx + 5.5} {cy + 7} Z", CREW_LINE * 0.7, art.INK, "#fff0cc"))
        out.append(f'<text x="{px1 - 20}" y="{y + h - 10.5}" font-family="Palatino Linotype, Book Antiqua, Georgia, serif" font-weight="bold" font-size="{CREW_TEXT}" fill="{art.INK}">1</text>')
        return out
    out.append(art.circle(cx, cy, r, CREW_LINE * 0.8, art.INK, "#e9b96a"))
    if sign == "plus":
        out.append(art.path(f"M{cx - 6.5} {cy} L{cx + 6.5} {cy} M{cx} {cy - 6.5} L{cx} {cy + 6.5}", CREW_LINE))
    else:       # two arrows, one each way: change
        out.append(art.path(f"M{cx - 6.5} {cy - 3} L{cx + 5.5} {cy - 3} M{cx + 2} {cy - 6.5} L{cx + 6} {cy - 3} "
                            f"M{cx + 6.5} {cy + 3.5} L{cx - 5.5} {cy + 3.5} M{cx - 2} {cy + 7} L{cx - 6} {cy + 3.5}", CREW_LINE * 0.75))
    return out


def crew_empty(variant="c"):
    """The riflemen's place with nobody in it, three looks (build/web/shots/crew_spot_variants.png):
    a: dashed ink frames of the zone and the tag; b: light cut-outs of the figures in a dashed ink line and the tag; c, the page's: b, and the warm
    pulse round the tag until the first choice (crew_glow, the panel's timer)."""
    figures = [g for x, y in CREW_PLACES for g in crew_ghost(x, y + 2)]
    if variant == "a":
        return crew_brackets() + crew_tag("plus")
    return figures + crew_tag("plus")


def crew_glow(out_prefix="crew_glow", tag=CREW_TAG):
    """The warm line round the tag while no crew was ever chosen: the same means and strength as the ring of Malakai's empty side (side_glow, variant a:
    8 phases, alpha 0.45..0.85, the same orange), here a rounded frame hugging the tag. Returns its box in units of the drawing and the phases."""
    import numpy as np
    from PIL import Image
    x, y, w, h = tag
    pad, k = 12, 2          # units round the tag, pixels a unit
    W, H = (w + 2 * pad) * k, (h + 2 * pad) * k
    yy, xx = np.mgrid[0:H, 0:W]
    dx = np.maximum(np.abs(xx - W / 2 + 0.5) - (w * k / 2 - 6), 0)
    dy = np.maximum(np.abs(yy - H / 2 + 0.5) - (h * k / 2 - 6), 0)
    dist = np.hypot(dx, dy) - 6             # the distance from the tag's edge, rounded at the corners
    ring = np.exp(-((dist - 5) / 4.2) ** 2)
    phases, lo, hi, rgb = 8, 0.45, 0.85, (255, 160, 60)
    for i in range(phases):
        a = lo + (hi - lo) * (0.5 - 0.5 * math.cos(2 * math.pi * i / phases))
        rgba = np.zeros((H, W, 4), np.uint8)
        rgba[..., 0], rgba[..., 1], rgba[..., 2] = rgb
        rgba[..., 3] = np.clip(ring * 255 * a, 0, 255).astype(np.uint8)
        Image.fromarray(rgba, "RGBA").save(OUT / f"{out_prefix}_{i}.png", optimize=True)
    return {"box": [x - pad, y - pad, w + 2 * pad, h + 2 * pad], "phases": phases}


SEPIA = art.INK_SOFT            # the soft brown ink of the drawing's own thin lines and shadows


def crew_sketch(kind, variant="c"):
    """A crew that is hired but not aboard yet, as a sketch at its places (build/web/shots/crew_hiring_variants.png):
    a: the kind's outline in pencil, no fills (the page's pencil of what is not built, its lines made firm enough for the page's real scale);
    b: the ink figures half see-through;
    c, the page's: the kind's outline in sepia over a light cut-out, as the empty places are cut out, with a few slanted sepia strokes across: a
    figure drawn in but not inked yet."""
    figures = [g for x, y in CREW_PLACES for g in crew_figure(kind, x, y + 2)]
    if variant == "b":
        return [f'<g filter="url(#ink)" opacity="0.5">{"".join(figures)}</g>']
    import re
    text = "".join(figures)
    line = PENCIL if variant == "a" else SEPIA
    text = re.sub(r'stroke="#[0-9a-fA-F]{6}"', f'stroke="{line}"', text)
    text = re.sub(r'fill="#[0-9a-fA-F]{6}"', 'fill="none"' if variant == "a" else f'fill="{LIGHT}"', text)
    text = re.sub(r'stroke-width="([0-9.]+)"', lambda m: f'stroke-width="{max(1.5, float(m.group(1)) * 0.85):.2f}"', text)
    if variant == "a":
        return [f'<g opacity="0.95">{text}</g>']
    out = [text]
    for x, y in CREW_PLACES:        # three slanted strokes over the body: the shading of a sketch
        for dx in (-5, 0, 5):
            out.append(art.path(f"M{x + dx - 3:.1f} {y + 1:.1f} L{x + dx + 3:.1f} {y - 10:.1f}", 0.9, SEPIA, op=0.75))
    return out


def crew_hiring_variants():
    """build/web/shots/crew_hiring_variants.png: the three looks of a hired crew that is not aboard yet, at the page's scale 1 and at the user's 0.6."""
    from PIL import Image, ImageDraw, ImageFont
    S, user = art.SCALE, 0.6
    base = Image.open(OUT / "blueprint_base.png").convert("RGBA")
    box = (round(230 * S), round(320 * S), round(700 * S), round(500 * S))
    w, h = round(art.DRAW_W * S), round(art.DRAW_H * S)
    place = json.loads((OUT / "layers.json").read_text(encoding="utf-8"))["places"]["malakai_near"]
    mal = Image.open(OUT / "malakai_near.png").convert("RGBA").resize((round(place[2] * S), round(place[3] * S)))
    cells = [("А: карандашный контур типа", "a"), ("Б: полупрозрачные чернила", "b"), ("В (выбран): контур сепией по светлому вырезу и лёгкая штриховка", "c")]
    one = 1.029 / S
    cw, ch = round((box[2] - box[0]) * one), round((box[3] - box[1]) * one)
    font = ImageFont.truetype("arial.ttf", 15)
    sheet = Image.new("RGB", (cw + round(cw * user) + 40, (ch + 30) * 3 + 10), (20, 18, 15))
    d = ImageDraw.Draw(sheet)
    for i, (title, variant) in enumerate(cells):
        im = base.copy()
        im.alpha_composite(art.paint(f"web_crew_hiring_{i}", art.svg_page(crew_sketch("pirates", variant) + crew_tag("wait"), filtered=False), w, h))
        im.alpha_composite(mal, (round(place[0] * S), round(place[1] * S)))
        crop = im.crop(box).convert("RGB")
        y = 10 + i * (ch + 30)
        d.text((10, y), title + "   |   масштаб 1 и 0.6", fill=(235, 189, 124), font=font)
        sheet.paste(crop.resize((cw, ch), Image.LANCZOS), (10, y + 22))
        sheet.paste(crop.resize((round(cw * user), round(ch * user)), Image.LANCZOS), (cw + 26, y + 22))
    target = REPO / "build" / "web" / "shots"
    target.mkdir(parents=True, exist_ok=True)
    sheet.save(target / "crew_hiring_variants.png")


def crew_area(places):
    """Layers of the riflemen's place: the empty figures, the tag in its two states and lit under the mouse, the frames shown under the mouse, the warm
    pulse of the tag, and the crew of each kind in ink."""
    layer_plain("crew_rifles_empty", [g for x, y in CREW_PLACES for g in crew_ghost(x, y + 2)], places)
    layer_plain("crew_rifles_tag_plus", crew_tag("plus"), places)
    layer_plain("crew_rifles_tag_swap", crew_tag("swap"), places)
    # under the mouse: the frames of the zone in soft ink and the tag's slip lighter; nothing brighter than the drawing
    layer_plain("crew_rifles_hover", crew_brackets(3, CREW_LINE * 0.8, art.INK_SOFT, 0.9), places)
    layer_plain("crew_rifles_tag_plus_hover", crew_tag("plus", True), places)
    layer_plain("crew_rifles_tag_swap_hover", crew_tag("swap", True), places)
    layer_plain("crew_rifles_tag_wait", crew_tag("wait"), places)
    layer_plain("crew_rifles_tag_wait_hover", crew_tag("wait", True), places)
    # a hire on its way: the ordered kind as a sketch at the places (crew_sketch), no chalk
    for kind in ("pirates", "quarrellers", "thunderers", "rakers", "torpedoes"):
        layer_plain(f"crew_rifles_{kind}_sketch", crew_sketch(kind), places)
    for kind in ("pirates", "quarrellers", "thunderers", "rakers", "torpedoes"):
        layer("crew_rifles_" + kind, [g for x, y in CREW_PLACES for g in crew_figure(kind, x, y + 2)], places)
    glow = crew_glow()
    tx, ty, tw, th = CREW_TAG
    x0, y0 = min(min(x for x, _ in CREW_PLACES) - 20, tx - 4), min(min(y for _, y in CREW_PLACES) - 36, ty - 4)
    x1, y1 = max(max(x for x, _ in CREW_PLACES) + 20, tx + tw + 24 + 4), max(y for _, y in CREW_PLACES) + 10
    return {"area": [x0, y0, x1 - x0, y1 - y0], "glow": glow, "step_ms": 110}


def crew_area_variants(user_scale=0.6):
    """build/web/shots/crew_spot_variants.png: the three looks of the empty place on the base drawing, at the page's scale 1 and at the user's."""
    from PIL import Image, ImageDraw, ImageFont
    S = art.SCALE
    base = Image.open(OUT / "blueprint_base.png").convert("RGBA")
    box = (round(230 * S), round(320 * S), round(700 * S), round(500 * S))
    w, h = round(art.DRAW_W * S), round(art.DRAW_H * S)
    place = json.loads((OUT / "layers.json").read_text(encoding="utf-8"))["places"]["malakai_near"]
    mal = Image.open(OUT / "malakai_near.png").convert("RGBA").resize((round(place[2] * S), round(place[3] * S)))
    glow = Image.open(OUT / "crew_glow_4.png").convert("RGBA")
    gb = crew_glow()["box"]
    cells = [("А: пунктирная рамка зоны и бирка", crew_empty("a"), False), ("Б: светлые силуэты в чернильном пунктире и бирка", crew_empty("b"), False),
             ("В (выбран): Б и тёплое свечение бирки до первого выбора", crew_empty("c"), True)]
    one = 1.029 / S         # the drawing's picture is drawn at 1.6 px a unit, the page at scale 1 shows a unit as 1.029 px
    cw, ch = round((box[2] - box[0]) * one), round((box[3] - box[1]) * one)
    font = ImageFont.truetype("arial.ttf", 15)
    sheet = Image.new("RGB", (cw + round(cw * user_scale) + 40, (ch + 30) * 3 + 10), (20, 18, 15))
    d = ImageDraw.Draw(sheet)
    for i, (title, parts, lit) in enumerate(cells):
        im = base.copy()
        if lit:
            im.alpha_composite(glow.resize((round(gb[2] * S), round(gb[3] * S))), (round(gb[0] * S), round(gb[1] * S)))
        im.alpha_composite(art.paint(f"web_crew_variant_{i}", art.svg_page(parts, filtered=False), w, h))
        im.alpha_composite(mal, (round(place[0] * S), round(place[1] * S)))
        crop = im.crop(box).convert("RGB")
        y = 10 + i * (ch + 30)
        d.text((10, y), title + "   |   масштаб 1 и масштаб пользователя " + str(user_scale), fill=(235, 189, 124), font=font)
        sheet.paste(crop.resize((cw, ch), Image.LANCZOS), (10, y + 22))
        sheet.paste(crop.resize((round(cw * user_scale), round(ch * user_scale)), Image.LANCZOS), (cw + 26, y + 22))
    target = REPO / "build" / "web" / "shots"
    target.mkdir(parents=True, exist_ok=True)
    sheet.save(target / "crew_spot_variants.png")


# ---------------- the other crew groups: guns in the bow ports, bombs over the hatches, throwers in the crow's nests ----------------
# The same language as the riflemen's place: what stands is inked at the places, an empty place is a light cut-out in a dashed ink line, a hire on its
# way is the kind sketched in sepia, a tag on a leader names the group with the sign of its state. Shapes and places from the game's models, rendered
# by tools/crew_cards.py's renderer (--plain; the side view and the lookout: build/crew_models/groups/*.png, nothing of the game kept in the repository):
#   guns       the port at the model's place (PORT_AT); every gun sits in the port's steel ball and points to the bow and a little down, as the guns of
#              the mod's cards stand (crew_cards.py, GUN_CAM, the stock aim). The stock gun: a plain steel barrel, a reinforce, a brass band, a flared
#              muzzle. Flaming shells: the same gun (the mod changes only its shell), told by its hot muzzle and the fire out of it. The organ gun
#              (tww3_mtb_organ): three barrels side by side in a copper and a brass clamp. The clatter gun (tww3_mtb_clatter2): a steel drum and a thin
#              bundle of barrels in three brass rings. The flame cannon (tww3_mtb_flame): a short body under brass bands, a thin neck and a gilt
#              dragon's head for a muzzle, fire out of its jaws. No crew shows: the guns stand in the hull, served from inside.
#   bombs      the bay doors are under the hull (crew_ui_art.BOMB_DOORS); the bombs above them are drawn seen through the hull's side, as the pub is:
#              a light window over each pair of doors, a rail with the bay's brass clamps (doors_right_01), two bombs a window (four seats: the near
#              and the far bomb of each bay side by side). The bomb (dwf_thunderbomb_grungni_01_rigid): a riveted steel cone up, a gilt rope band,
#              the body orange with a steel side, three steel fins down. The fire bomb is the same casing (the game burns it in flight): its body red
#              with a painted flame, a lit fuse on its nose.
#   nests      the rings on the balloon (crew_ui_art.CUPOLAS); a dwarf stands in each, the ring's front hides him to the waist. The grenades: Slayer
#              pirates (dwf_thunderbarge_crew_pirates_grenade: the rifle pirates' body), the far arm up with a black round bomb and its lit fuse. The
#              axes: rangers (cupola_axes.vmd: dwf_rangers), white fur coat with brown leather, a steel helm with big gilt horns, a white beard, a
#              throwing axe raised. The lookouts of «Вороньи гнёзда» (a detail of the tree, not a crew): the barge's lookout
#              (dwf_thunderbarge_crew_lookout: an artillery crewman), a steel cap, a ginger beard, white sleeves under a brown leather jerkin; the
#              model's hands are empty, the author's note wants a spyglass, so he holds a brass one to his eye.
GUN_AT = PORT_AT
# steel on a layer of its own: not multiplied into the parchment as the base drawing is, so a mid grey (the figures' mail is #8f9296)
STEEL_L, STEEL_D = "#aba69c", "#96918a"
GUN_ANGLE = 14          # degrees under the horizontal, towards the bow
SHIRT, LEATHER, FUR, HOT, FLAME, FLAME_IN = "#ece6d8", "#7a4a2a", "#f3efe6", "#c8321e", "#f08a2a", "#f7d25a"
BOMB_BODY, FIRE_BODY = "#d9733a", "#b8321c"


def gun_axes():
    a = math.radians(GUN_ANGLE)
    return (-math.cos(a), math.sin(a)), (math.sin(a), math.cos(a))


def gun_pt(t, o=0.0):
    """A point of the gun: t along the barrel from the port's centre to the muzzle, o across it (positive: its lower side)."""
    (ux, uy), (nx, ny) = gun_axes()
    return GUN_AT[0] + ux * t + nx * o, GUN_AT[1] + uy * t + ny * o


def tube(t0, t1, r0, r1, fill, w=1.4, o=0.0):
    """A length of round barrel seen from the side: its outline, a light line along its top, a shade under."""
    pts = [gun_pt(t0, o - r0), gun_pt(t1, o - r1), gun_pt(t1, o + r1), gun_pt(t0, o + r0)]
    out = [art.path(art.poly(pts, True), w, art.INK, fill)]
    out.append(art.path(art.poly([gun_pt(t0 + 1, o - r0 * 0.45), gun_pt(t1 - 1, o - r1 * 0.45)]), 0.9, "#fff8ec", op=0.8))
    out.append(art.hatch([gun_pt(t0, o + r0 * 0.3), gun_pt(t1, o + r1 * 0.3), gun_pt(t1, o + r1), gun_pt(t0, o + r0)], 90 - GUN_ANGLE + 60, 2.4, 0.6, art.INK, 0.7))
    return out


def band(t, wdt, r, fill, o=0.0, dots=True):
    pts = [gun_pt(t, o - r), gun_pt(t + wdt, o - r), gun_pt(t + wdt, o + r), gun_pt(t, o + r)]
    out = [art.path(art.poly(pts, True), 1.1, art.INK, fill)]
    if dots:
        for k in (-0.5, 0.5):
            out.append(art.dot(*gun_pt(t + wdt / 2, o + k * r), 0.8))
    return out


def muzzle_end(t, r, fill="#3d3a36", o=0.0):
    """The end face of a barrel seen a little from the side: a narrow ellipse across the barrel, the bore dark."""
    x, y = gun_pt(t, o)
    rot = -GUN_ANGLE + 90
    return [f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{r:.1f}" ry="{max(1.6, r * 0.32):.1f}" transform="rotate({rot:.1f} {x:.1f} {y:.1f})" fill="{STEEL_L}" stroke="{art.INK}" stroke-width="1.2"/>',
            f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{r * 0.6:.1f}" ry="{max(1.0, r * 0.2):.1f}" transform="rotate({rot:.1f} {x:.1f} {y:.1f})" fill="{fill}"/>']


def breech():
    """The steel ball in the port the guns turn in (the stock gun's mount): over the port's lid."""
    x, y = GUN_AT
    return [art.circle(x, y, 12.5, 1.6, art.INK, STEEL_L), art.hatch(crescent(x, y, 12.5, -5, -5), 50, 2.4, 0.7, art.INK, 0.7),
            art.path(f"M{x - 8:.1f} {y - 6:.1f} Q {x - 4:.1f} {y - 10:.1f} {x + 1:.1f} {y - 10:.1f}", 1.0, "#fff8ec", op=0.9)]


def fire_tongue(t, length, width, o=0.0):
    """Fire out of a muzzle along the barrel's line: an outer tongue and a bright core, ink round it."""
    tip, side = gun_pt(t + length, o), width / 2
    a, b = gun_pt(t, o - side), gun_pt(t, o + side)
    m1, m2 = gun_pt(t + length * 0.45, o - side * 1.25), gun_pt(t + length * 0.55, o + side * 1.15)
    outer = f"M{a[0]:.1f} {a[1]:.1f} Q {m1[0]:.1f} {m1[1]:.1f} {tip[0]:.1f} {tip[1]:.1f} Q {m2[0]:.1f} {m2[1]:.1f} {b[0]:.1f} {b[1]:.1f} Z"
    ci, ca, cb = gun_pt(t + length * 0.62, o), gun_pt(t + 1, o - side * 0.5), gun_pt(t + 1, o + side * 0.5)
    inner = f"M{ca[0]:.1f} {ca[1]:.1f} Q {gun_pt(t + length * 0.3, o - side * 0.6)[0]:.1f} {gun_pt(t + length * 0.3, o - side * 0.6)[1]:.1f} {ci[0]:.1f} {ci[1]:.1f} Q {gun_pt(t + length * 0.3, o + side * 0.6)[0]:.1f} {gun_pt(t + length * 0.3, o + side * 0.6)[1]:.1f} {cb[0]:.1f} {cb[1]:.1f} Z"
    return [art.path(outer, 1.3, HOT, FLAME), art.path(inner, 0.6, FLAME, FLAME_IN)]


def gun_items(kind):
    """The gun of a kind in the port (see above)."""
    out = breech()
    if kind in ("stock", "flaming"):
        out += tube(8, 22, 6.6, 6.3, STEEL_L) + tube(22, 58, 5.6, 5.0, STEEL_L)
        out += band(20, 3, 6.9, STEEL_L, dots=False) + band(31, 6, 6.4, BRASS)
        out += tube(58, 67, 5.6, 7.4, STEEL_L)
        if kind == "flaming":
            out += [art.path(art.poly([gun_pt(55, -5.6), gun_pt(67, -7.4), gun_pt(67, 7.4), gun_pt(55, 5.6)], True), 1.2, art.INK, "#e0602a")]
            out += muzzle_end(67, 7.4, HOT) + fire_tongue(67, 15, 11)
        else:
            out += muzzle_end(67, 7.4)
    elif kind == "organ":
        # a frame at the breech, three barrels side by side (four on the model, two and two: the far ones behind), a copper and a brass clamp
        out.append(art.path(art.poly([gun_pt(4, -12), gun_pt(16, -12), gun_pt(16, 12), gun_pt(4, 12)], True), 1.4, art.INK, STEEL_L))
        out.append(art.circle(*gun_pt(10, 0), 3.0, 1.0, art.INK, STEEL))
        for o, end in ((-7.2, 61), (0.0, 64), (7.2, 59)):
            out += tube(14, end, 3.5, 3.3, STEEL_D, 1.2, o) + muzzle_end(end, 3.4, "#3d3a36", o)
        out += band(22, 7, 11.2, COPPER_LIGHT) + band(37, 5, 11.0, BRASS)
    elif kind == "clatter":
        # the drum, then a thin bundle of barrels (their lines along it), three brass rings, the barrels' ends out of the last
        out += tube(8, 24, 7.2, 7.2, STEEL_L)
        # the bundle dark (the model's barrels are blackened steel) against the stock gun's light barrel, the rings broad and gilt
        out.append(art.path(art.poly([gun_pt(24, -4.6), gun_pt(70, -4.2), gun_pt(70, 4.2), gun_pt(24, 4.6)], True), 1.3, art.INK, "#5e5a55"))
        for o in (-2.3, 0.0, 2.3):
            out.append(art.path(art.poly([gun_pt(25, o), gun_pt(74, o * 1.1)]), 1.2, "#2e2b28"))
        for t in (32, 50, 62):
            out += band(t, 4.2, 7.0, BRASS, dots=False)
        for o in (-2.8, 0.0, 2.8):
            out.append(art.circle(*gun_pt(75, o * 1.1), 1.5, 0.8, art.INK, "#2e2b28"))
    else:       # flame
        out += tube(8, 42, 6.6, 6.0, STEEL_D)
        for t in (12, 22, 32):
            out += band(t, 5, 7.2, BRASS)
        out += tube(42, 52, 3.8, 3.8, BRASS)
        # the dragon's head: a gilt wedge, the upper jaw over the lower, an eye, the jaws open on the fire
        head = [gun_pt(50, -6.5), gun_pt(56, -8.5), gun_pt(66, -6.2), gun_pt(70, -3.2), gun_pt(62, -1.0), gun_pt(70, 3.0), gun_pt(64, 5.8), gun_pt(52, 6.5)]
        out.append(art.path(art.smooth(head, True), 1.4, art.INK, BRASS))
        out.append(art.dot(*gun_pt(57, -4.5), 1.3))
        out.append(art.path(art.poly([gun_pt(54, -8.2), gun_pt(52, -12), gun_pt(58, -9)]), 1.0, art.INK, BRASS))
        out += fire_tongue(66, 20, 10, -0.2)
    return out


COPPER_LIGHT = "#c8834a"


def gun_ghost():
    """The empty port's place: the stock gun's outline as a light cut-out in a dashed ink line."""
    x, y = GUN_AT
    pts = [gun_pt(10, -6.6), gun_pt(58, -5.0), gun_pt(67, -7.4), gun_pt(67, 7.4), gun_pt(58, 5.0), gun_pt(10, 6.6)]
    return [art.path(art.poly(pts, True), CREW_LINE, art.INK, LIGHT, extra='stroke-dasharray="4.5 3"'),
            art.path(f"M{x - 12.5:.1f} {y:.1f} A 12.5 12.5 0 1 1 {x + 12.5:.1f} {y:.1f} A 12.5 12.5 0 1 1 {x - 12.5:.1f} {y:.1f}", CREW_LINE, art.INK, LIGHT, extra='stroke-dasharray="4.5 3"')]


# the bombs' windows: over each pair of doors (crew_ui_art.BOMB_DOORS), under the side shields, down to the doors
def bomb_windows():
    out = []
    for x0, x1 in art.BOMB_DOORS:
        cx = (x0 + x1) / 2
        out.append((x0 + 5, 529, x1 - 5, art.hull_bottom(cx) - 11))
    return out


def bomb_shape(cx, top, fire=False, ghost=False):
    """A bomb standing nose up: the cone, the gilt band, the body, the fins. top: the nose's tip."""
    w, cone, band_h, body, fins = 7.5, 12, 3, 19, 9
    y1, y2, y3, y4 = top + cone, top + cone + band_h, top + cone + band_h + body, top + cone + band_h + body + fins
    outline = (f"M{cx:.1f} {top:.1f} Q {cx + w:.1f} {top + 5:.1f} {cx + w:.1f} {y1:.1f} L{cx + w - 0.8:.1f} {y3:.1f} L{cx + w + 3.5:.1f} {y4:.1f} "
               f"L{cx + 2:.1f} {y3 + 4:.1f} L{cx - 2:.1f} {y3 + 4:.1f} L{cx - w - 3.5:.1f} {y4:.1f} L{cx - w + 0.8:.1f} {y3:.1f} L{cx - w:.1f} {y1:.1f} "
               f"Q {cx - w:.1f} {top + 5:.1f} {cx:.1f} {top:.1f} Z")
    if ghost:
        return [art.path(outline, CREW_LINE * 0.85, art.INK, LIGHT, extra='stroke-dasharray="4 2.6"')]
    out = [art.path(outline, 1.3, art.INK, STEEL_L)]
    # the body: orange with its steel side (the model's halves), or the fire bomb's red with a painted flame
    out.append(art.path(art.poly([(cx - w, y2), (cx + w * 0.25, y2), (cx + w * 0.25 - 0.4, y3), (cx - w + 0.8, y3)], True), 0.9, art.INK, FIRE_BODY if fire else BOMB_BODY))
    if fire:
        out.append(art.path(f"M{cx - 4:.1f} {y3 - 1:.1f} Q {cx - 6.5:.1f} {y3 - 8:.1f} {cx - 2.5:.1f} {y2 + 4:.1f} Q {cx - 1.5:.1f} {y3 - 9:.1f} {cx + 1:.1f} {y3 - 7:.1f} "
                            f"Q {cx + 2:.1f} {y3 - 4:.1f} {cx:.1f} {y3 - 1:.1f} Z", 0.6, HOT, FLAME_IN))
    out.append(art.path(art.poly([(cx - w, y1), (cx + w, y1), (cx + w, y2), (cx - w, y2)], True), 0.9, art.INK, BRASS))
    for k in range(-2, 3):
        out.append(art.path(f"M{cx + k * 3 - 1:.1f} {y2:.1f} L{cx + k * 3 + 1:.1f} {y1:.1f}", 0.5, art.INK, op=0.8))
    out.append(art.path(f"M{cx:.1f} {y3 + 4:.1f} L{cx:.1f} {y4 + 1:.1f}", 1.4))
    for dy in (5, 9):
        out.append(art.dot(cx - 2.5, top + dy, 0.7))
    if fire:
        # the lit fuse on the nose
        out.append(art.path(f"M{cx:.1f} {top:.1f} Q {cx + 2:.1f} {top - 3:.1f} {cx + 1:.1f} {top - 5:.1f}", 0.9))
        f = f"M{cx - 3:.1f} {top - 5:.1f} Q {cx - 3.5:.1f} {top - 11:.1f} {cx + 1.5:.1f} {top - 16:.1f} Q {cx + 0.5:.1f} {top - 11:.1f} {cx + 4.5:.1f} {top - 8:.1f} Q {cx + 4:.1f} {top - 4:.1f} {cx + 1:.1f} {top - 4:.1f} Z"
        out.append(art.path(f, 1.0, HOT, FLAME))
    return out


def bomb_items(kind):
    """kind: None (empty: the windows, the rails and clamps, the bombs' places dashed), 'stock' or 'fire'."""
    out = []
    for x0, y0, x1, y1 in bomb_windows():
        cx = (x0 + x1) / 2
        out.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0:.1f}" fill="{art.PAPER}" opacity="0.42"/>')
        out.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="6" fill="#7a5128" opacity="0.35"/>')
        # the rail across and the bay's brass clamps that hold each bomb by its band
        out.append(art.path(f"M{x0 + 2} {y0 + 12} L{x1 - 2} {y0 + 12}", 2.2, art.INK))
        for bx in (cx - 11.5, cx + 11.5):
            if kind is None:
                out += bomb_shape(bx, y0 + 8, ghost=True)
            else:
                out += bomb_shape(bx, y0 + 8, fire=(kind == "fire"))
            out.append(art.path(art.poly([(bx - 9, y0 + 12), (bx - 9, y0 + 23), (bx - 6.5, y0 + 23)]), 1.4, art.INK))
            out.append(art.path(art.poly([(bx + 9, y0 + 12), (bx + 9, y0 + 23), (bx + 6.5, y0 + 23)]), 1.4, art.INK))
            out.append(art.path(f"M{bx - 9:.1f} {y0 + 13:.1f} L{bx - 9:.1f} {y0 + 22:.1f} M{bx + 9:.1f} {y0 + 13:.1f} L{bx + 9:.1f} {y0 + 22:.1f}", 0.9, BRASS))
        out.append(f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0:.1f}" fill="none" stroke="{art.INK}" stroke-width="1.3" opacity="0.9"/>')
    return out


NEST_S = 1.2            # the game stands the nests' throwers 1.2 times their size (crew_cards.py, cupola_card; data: cupola axes scale)
NEST_BASE = 47          # where a dwarf in a nest stands: the ring's front hides him below its rim (ring top at y - 26)


def ring_front(x, y):
    """The front of a nest's ring, drawn over the dwarf in it: the wooden band and the near half of the iron rim."""
    top = y - 26
    out = [art.shape(f"M{x - 24} {top + 1} L{x + 24} {top + 1} L{x + 24} {y} Q {x} {y + 8} {x - 24} {y} Z", "#a06c38")]
    for dx in (-18, -9, 0, 9, 18):
        out.append(art.path(f"M{x + dx} {top + 5} L{x + dx} {y + (3 if abs(dx) < 10 else 1)}", 0.9))
    out.append(art.path(f"M{x - 24} {top + 1} L{x - 24} {y} Q {x} {y + 8} {x + 24} {y} L{x + 24} {top + 1}", 1.9))
    out.append(f'<path d="M{x - 25} {top + 1} A 25 5 0 0 0 {x + 25} {top + 1} L{x + 18} {top + 1} A 18 3 0 0 1 {x - 18} {top + 1} Z" fill="#57504a" stroke="{art.INK}" stroke-width="1.7"/>')
    return out


def nest_figure(kind, x, y, s=1.0):
    """A dwarf in a nest from the chest up, turned to the bow (left): 'stock' a Slayer pirate with a grenade raised, 'axes' a ranger with a throwing axe
    raised, 'lookout' the lookout with a spyglass at his eye."""
    P = lambda dx, dy: f"{x + dx * s:.1f} {y + dy * s:.1f}"
    line = lambda d, w=1.0, fill="none", color=art.INK: art.path(d, w * s, color, fill)
    limb = lambda d, colour, w=3.4: [line(d, w + 1.6), line(d, w, color=colour)]
    out = []
    cloth = {"stock": SKIN, "axes": FUR, "lookout": LEATHER}[kind]
    if kind == "stock":
        # the far arm up over the head with the round black grenade, its fuse lit
        out += limb(f"M{P(8, -13)} L{P(14, -20)} L{P(15, -26)}", SKIN)
        out.append(art.circle(x + 15.5 * s, y - 30 * s, 4.4 * s, 1.1 * s, art.INK, "#3d3a36"))
        out.append(line(f"M{P(17.5, -33.5)} Q {P(19.5, -35)} {P(19, -36.5)}", 0.9))
        out.append(art.dot(x + 19 * s, y - 37 * s, 1.8 * s, FLAME))
    elif kind == "axes":
        # the far arm up, the throwing axe over the head: a short haft, the steel head's bit to the front
        out.append(line(f"M{P(14, -22)} L{P(17.5, -35)}", 2.4, color=WOOD))
        out.append(line(f"M{P(16.2, -30.5)} Q {P(10, -33)} {P(9.5, -37.5)} Q {P(14.5, -37)} {P(18.1, -35.2)} Z", 1.0, "#c9cdd2"))
        out += limb(f"M{P(8, -13)} L{P(13, -19)} L{P(15, -25)}", FUR)
        out.append(line(f"M{P(13.6, -23.5)} L{P(16.6, -22.8)}", 1.6, color=GOLD))
    # the body: sloping shoulders wider than the head
    out.append(line(f"M{P(-8, 0)} L{P(-10, -7)} Q {P(-12.5, -13)} {P(-5, -15.5)} L{P(4, -15.5)} Q {P(12, -13)} {P(10, -7)} L{P(8, 0)} Z", 1.1, cloth))
    if kind == "stock":
        out.append(line(f"M{P(-8.4, -1.6)} L{P(8.4, -1.6)}", 2.0, color=WOOD))
    if kind == "axes":
        out.append(line(f"M{P(-7, -14.5)} L{P(5, -1)}", 2.4, color=LEATHER))            # the leather strap across the white coat
        out.append(line(f"M{P(-9.6, -5)} L{P(9.6, -5)}", 0.9, color=GOLD))
    if kind == "lookout":
        # white sleeves out of the leather jerkin
        for sx in (-1, 1):
            out.append(line(f"M{P(sx * 7.5, -14.5)} Q {P(sx * 12, -12)} {P(sx * 10.5, -6)} L{P(sx * 7.5, -7)} Z", 0.9, SHIRT))
    out.append(art.circle(x - 1 * s, y - 19.5 * s, 5.4 * s, 1.0 * s, art.INK, SKIN if kind == "stock" else "#e3b08a"))
    if kind == "stock":
        out.append(line(f"M{P(-6.4, -21)} A {5.4 * s:.1f} {5.4 * s:.1f} 0 0 1 {P(4.4, -21)} Z", 0.9, SCARF))
        out.append(line(f"M{P(4.2, -22)} L{P(8.5, -24.5)} M{P(4.2, -22)} L{P(9, -20.5)}", 1.3, color=SCARF))
        out.append(line(f"M{P(-4.5, -15)} L{P(2.5, -15)} L{P(1.6, -4)} L{P(-1, -7)} L{P(-3.6, -4)} Z", 0.9, GINGER))
        out.append(line(f"M{P(-1, -17.2)} Q {P(-7, -14.2)} {P(-13, -19.5)} M{P(-1, -17.2)} Q {P(5, -14.2)} {P(11, -19.5)}", 3.4))
        out.append(line(f"M{P(-1, -17.2)} Q {P(-7, -14.2)} {P(-13, -19.5)} M{P(-1, -17.2)} Q {P(5, -14.2)} {P(11, -19.5)}", 2.0, color=GINGER))
        # the near arm down on the rim
        out += limb(f"M{P(-9, -12)} L{P(-13, -5)}", SKIN)
    elif kind == "axes":
        # the steel helm and its big gilt horns turned up and out, the long white beard
        out.append(line(f"M{P(-7, -20.5)} A {6 * s:.1f} {6.4 * s:.1f} 0 0 1 {P(5, -20.5)} Z", 1.0, HELM))
        out.append(line(f"M{P(-7, -20.5)} L{P(5, -20.5)}", 1.2, color=GOLD))
        for sx, hx in ((-1, -6.5), (1, 4.5)):
            d = f"M{P(hx, -23)} Q {P(hx + sx * 9, -24)} {P(hx + sx * 7, -34)}"
            out += [line(d, 3.4), line(d, 2.0, color=GOLD)]
        out.append(line(f"M{P(-6.5, -17.5)} L{P(4.5, -17.5)} L{P(3, -2)} L{P(-1, 1)} L{P(-5, -2)} Z", 0.9, FUR))
        out.append(line(f"M{P(-1, -15)} L{P(-1, -2)}", 0.6, color="#b9b2a2"))
        out += limb(f"M{P(-9, -12)} L{P(-13, -5)}", FUR)
    else:
        # the steel cap, the ginger beard, the spyglass at his eye along the bow
        out.append(line(f"M{P(-6.6, -21)} A {5.8 * s:.1f} {5.8 * s:.1f} 0 0 1 {P(4.6, -21)} Z", 1.0, HELM))
        out.append(line(f"M{P(-6, -17.5)} L{P(4, -17.5)} L{P(2.4, -6)} L{P(-1, -4)} L{P(-4.4, -6)} Z", 0.9, GINGER))
        out.append(line(f"M{P(-4, -20.5)} L{P(-23, -22.5)}", 4.4))
        out.append(line(f"M{P(-4, -20.5)} L{P(-23, -22.5)}", 2.8, color=BRASS))
        out.append(line(f"M{P(-15, -20.6)} L{P(-15, -22.8)}", 1.0))
        out += limb(f"M{P(-9, -12)} L{P(-13, -17)} L{P(-12, -21)}", SHIRT, 3.0)
    return out


def nest_items(kind):
    """A kind in both nests, each over the ring's back and under its front."""
    out = []
    for x, y in art.CUPOLAS:
        out += nest_figure(kind, x, NEST_BASE, NEST_S) + ring_front(x, y)
    return out


def sketch(items, strokes):
    """Hired, not aboard yet: the kind's outline in sepia over a light cut-out, a few slanted sepia strokes across (as crew_sketch, variant c)."""
    import re
    text = "".join(items)
    text = re.sub(r'stroke="#[0-9a-fA-F]{6}"', f'stroke="{SEPIA}"', text)
    text = re.sub(r'fill="#[0-9a-fA-F]{6}"', f'fill="{LIGHT}"', text)
    text = re.sub(r'stroke-width="([0-9.]+)"', lambda m: f'stroke-width="{max(1.5, float(m.group(1)) * 0.85):.2f}"', text)
    out = [text]
    for x, y in strokes:
        for dx in (-5, 0, 5):
            out.append(art.path(f"M{x + dx - 3:.1f} {y + 5:.1f} L{x + dx + 3:.1f} {y - 6:.1f}", 0.9, SEPIA, op=0.75))
    return out


# The tag of each group: its box (x, y, w, h), its word, its leaders (from the slip to a dot at the place)
GROUP_TAGS = {
    "cannons": {"box": (166, 606, 136, 36), "text": "Орудия", "leaders": [((266, 606), gun_pt(31, 0))]},
    "bombs": {"box": (490, 628, 128, 36), "text": "Бомбы", "leaders": [((508, 628), (449, 592)), ((600, 628), (656, 595))]},
    "cupolas": {"box": (462, 4, 136, 36), "text": "Гнёзда", "leaders": [("left", (410, 37)), ("right", (640, 37))]},
}


def group_tag(group, sign="plus", light=False):
    """As crew_tag: the slip of light parchment with the group's word and the sign of its state, the leaders to its places."""
    spec = GROUP_TAGS[group]
    x, y, w, h = spec["box"]
    if sign == "wait":
        w += 24
    fill = "#fff0cc" if light else LIGHT
    out = []
    for start, end in spec["leaders"]:
        if start == "left":
            start = (x, y + h / 2)
        elif start == "right":
            start = (x + w, y + h / 2)
        out.append(art.path(f"M{start[0]:.1f} {start[1]:.1f} L{end[0]:.1f} {end[1]:.1f}", CREW_LINE * 0.8))
        out.append(art.dot(end[0], end[1], 3.2))
    out.append(art.path(f"M{x + 6} {y} L{x + w} {y} L{x + w} {y + h} L{x + 6} {y + h} L{x} {y + h - 7} L{x} {y + 7} Z", CREW_LINE, art.INK, fill))
    out.append(f'<text x="{x + 12}" y="{y + h - 10.5}" font-family="Palatino Linotype, Book Antiqua, Georgia, serif" font-weight="bold" font-size="{CREW_TEXT}" fill="{art.INK}">{spec["text"]}</text>')
    cx, cy, r = x + w - 19, y + h / 2, 11.5
    if sign == "wait":
        px0, px1 = x + w - 55, x + w - 7
        out.append(art.path(f"M{px0 + r} {cy - r} L{px1 - r} {cy - r} A {r} {r} 0 0 1 {px1 - r} {cy + r} L{px0 + r} {cy + r} A {r} {r} 0 0 1 {px0 + r} {cy - r} Z", CREW_LINE * 0.8, art.INK, "#e9b96a"))
        hx = px0 + 14
        out.append(art.path(f"M{hx - 5.5} {cy - 7} L{hx + 5.5} {cy - 7} L{hx - 5.5} {cy + 7} L{hx + 5.5} {cy + 7} Z", CREW_LINE * 0.7, art.INK, "#fff0cc"))
        out.append(f'<text x="{px1 - 20}" y="{y + h - 10.5}" font-family="Palatino Linotype, Book Antiqua, Georgia, serif" font-weight="bold" font-size="{CREW_TEXT}" fill="{art.INK}">1</text>')
        return out
    out.append(art.circle(cx, cy, r, CREW_LINE * 0.8, art.INK, "#e9b96a"))
    if sign == "plus":
        out.append(art.path(f"M{cx - 6.5} {cy} L{cx + 6.5} {cy} M{cx} {cy - 6.5} L{cx} {cy + 6.5}", CREW_LINE))
    else:
        out.append(art.path(f"M{cx - 6.5} {cy - 3} L{cx + 5.5} {cy - 3} M{cx + 2} {cy - 6.5} L{cx + 6} {cy - 3} "
                            f"M{cx + 6.5} {cy + 3.5} L{cx - 5.5} {cy + 3.5} M{cx - 2} {cy + 7} L{cx - 6} {cy + 3.5}", CREW_LINE * 0.75))
    return out


def group_zones(group):
    """The boxes round a group's places (x0, y0, x1, y1): dashed frames under the mouse, and with the tag the box that takes the click."""
    if group == "cannons":
        pts = [gun_pt(t, o) for t in (-14, 74) for o in (-13, 13)]
        return [(min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))]
    if group == "bombs":
        return [(x0 - 3, y0 - 3, x1 + 3, y1 + 3) for x0, y0, x1, y1 in bomb_windows()]
    return [(x - 31, 6, x + 31, y + 10) for x, y in art.CUPOLAS]


def group_frames(group, pad=0, w=CREW_LINE, color=None, op=1.0):
    return [art.path(art.poly([(x0 - pad, y0 - pad), (x1 + pad, y0 - pad), (x1 + pad, y1 + pad), (x0 - pad, y1 + pad)], True), w, color or art.INK,
                     extra='stroke-dasharray="9 6"', op=op) for x0, y0, x1, y1 in group_zones(group)]


GROUP_KINDS = {"cannons": ["stock", "flaming", "organ", "clatter", "flame"], "bombs": ["stock", "fire"], "cupolas": ["stock", "axes"]}


def group_items(group, kind):
    if group == "cannons":
        return gun_items(kind)
    if group == "bombs":
        return bomb_items(kind)
    return nest_items(kind)


def group_strokes(group):
    """Where a sketch's slanted strokes go: on the bodies of what is drawn."""
    if group == "cannons":
        return [gun_pt(t, 0) for t in (24, 44)]
    if group == "bombs":
        return [((x0 + x1) / 2 + dx, y0 + 34) for x0, y0, x1, y1 in bomb_windows() for dx in (-11.5, 11.5)]
    return [(x, NEST_BASE - 8) for x, _ in art.CUPOLAS]


def group_glow(group):
    """The warm line round a group's tag until its first choice: the rifles' crew_glow, round this tag."""
    return {**crew_glow(f"crew_{group}_glow", GROUP_TAGS[group]["box"]), "prefix": f"crew_{group}_glow"}


def group_areas(places):
    """Layers of the guns', bombs' and nests' places, as crew_area() makes the riflemen's; returns their boxes and glows for layers.json."""
    out = {}
    for group, kinds in GROUP_KINDS.items():
        if group == "cannons":
            layer_plain("crew_cannons_empty", gun_ghost(), places)
        elif group == "bombs":
            layer_plain("crew_bombs_empty", bomb_items(None), places)
        for sign in ("plus", "swap", "wait"):
            layer_plain(f"crew_{group}_tag_{sign}", group_tag(group, sign), places)
            layer_plain(f"crew_{group}_tag_{sign}_hover", group_tag(group, sign, True), places)
        layer_plain(f"crew_{group}_hover", group_frames(group, 3, CREW_LINE * 0.8, art.INK_SOFT, 0.9), places)
        for kind in kinds:
            items = group_items(group, kind)
            if group == "cupolas":      # the dwarf sketched, the ring's front over him stays in ink
                items_sketch = sketch([g for x, _ in art.CUPOLAS for g in nest_figure(kind, x, NEST_BASE, NEST_S)], group_strokes(group)) + [g for x, y in art.CUPOLAS for g in ring_front(x, y)]
            else:
                items_sketch = sketch(items, group_strokes(group))
            layer_plain(f"crew_{group}_{kind}_sketch", items_sketch, places)
            layer(f"crew_{group}_{kind}", items, places)
        glow = group_glow(group)
        x0 = min(z[0] for z in group_zones(group))
        y0 = min(z[1] for z in group_zones(group))
        x1 = max(z[2] for z in group_zones(group))
        y1 = max(z[3] for z in group_zones(group))
        tx, ty, tw, th = GROUP_TAGS[group]["box"]
        x0, y0, x1, y1 = min(x0, tx - 4), min(y0, ty - 4), max(x1, tx + tw + 24 + 4), max(y1, ty + th + 4)
        out[group] = {"area": [round(x0, 1), round(y0, 1), round(x1 - x0, 1), round(y1 - y0, 1)], "glow": glow, "step_ms": 110}
    return out


# ---------------- details the tree brings that the base drawing lacked: the balloon's shields, the forsage tank, the nests' lookouts ----------------
# The balloon in the drawing is flatter than the model's and shorter: its places go by the balloon (nose 128, the tail cone's end 972 against the side
# view's 250 and 1450 px, build/crew_models/groups/stock_side.png), not by the hull's mx().
def balloon_x(px):
    return 128 + (px - 250) * (972 - 128) / (1450 - 250)


# Nine round shields on the balloon's middle (the model: seven in a row, a gap at the rear net, two more), 58 px across in the side view; their faces in
# the model's order: the helmed face, the rune Г, quartered red and steel with a hammer, the face, quartered, the rune B on red, quartered, Г, the face.
BALLOON_SHIELDS = [(595, "face"), (652, "rune_g"), (710, "quarter"), (768, "face"), (826, "quarter"), (884, "rune_b"), (940, "quarter"), (1065, "rune_g"), (1125, "face")]
BALLOON_SHIELD_Y = 181


def balloon_shields_items():
    out = []
    r = 58 * (972 - 128) / (1450 - 250) / 2
    for px, face in BALLOON_SHIELDS:
        x, y = balloon_x(px), BALLOON_SHIELD_Y
        out.append(art.circle(x, y, r, 1.5, art.INK, art.PAPER))
        out.append(art.circle(x, y, r - 3.2, 0.8))
        if face == "quarter":
            out.append(art.hatch([(x, y), (x - r + 3, y), (x - r + 4, y - r * 0.6), (x - r * 0.6, y - r + 4), (x, y - r + 3)], 45, 3.2, 0.7))
            out.append(art.hatch([(x, y), (x + r - 3, y), (x + r - 4, y + r * 0.6), (x + r * 0.6, y + r - 4), (x, y + r - 3)], 45, 3.2, 0.7))
            out.append(art.path(f"M{x - 5:.1f} {y + 9:.1f} L{x + 5:.1f} {y - 7:.1f}", 2.0, art.INK_SOFT))
            out.append(art.path(f"M{x + 1:.1f} {y - 11:.1f} L{x + 9:.1f} {y - 4:.1f}", 3.2, art.INK_SOFT))
        elif face == "face":
            out.append(art.hatch([(x - 10, y), (x, y - 10), (x + 10, y), (x, y + 10)], 45, 3.2, 0.7))
            out.append(art.path(f"M{x - 8:.1f} {y - 3:.1f} L{x - 3:.1f} {y - 1:.1f} M{x + 8:.1f} {y - 3:.1f} L{x + 3:.1f} {y - 1:.1f} M{x - 4:.1f} {y + 6:.1f} Q {x:.1f} {y + 10:.1f} {x + 4:.1f} {y + 6:.1f}", 1.4, art.INK_SOFT))
        elif face == "rune_g":
            out.append(art.path(f"M{x - 3:.1f} {y + 11:.1f} L{x - 3:.1f} {y - 11:.1f} L{x + 6:.1f} {y - 8:.1f}", 2.2, art.INK_SOFT))
        else:
            out.append(art.path(f"M{x - 5:.1f} {y - 11:.1f} L{x - 5:.1f} {y + 11:.1f} M{x - 5:.1f} {y - 11:.1f} L{x + 6:.1f} {y - 5:.1f} L{x - 5:.1f} {y:.1f} "
                                f"L{x + 6:.1f} {y + 6:.1f} L{x - 5:.1f} {y + 11:.1f}", 2.0, art.INK_SOFT))
        out.append(art.circle(x, y, 3.4, 1.0, art.INK, art.INK_SOFT))
    return out


def balloon_shields_area():
    r = 58 * (972 - 128) / (1450 - 250) / 2 + 3
    x0, x1 = balloon_x(BALLOON_SHIELDS[0][0]) - r, balloon_x(BALLOON_SHIELDS[-1][0]) + r
    return [(x0, BALLOON_SHIELD_Y - r), (x1, BALLOON_SHIELD_Y - r), (x1, BALLOON_SHIELD_Y + r), (x0, BALLOON_SHIELD_Y + r)]


# The forsage tank (build/solid_hull_tank/tank_part; the side view at the drive): a steel cylinder lying on the shaft's casing in front of the big gear,
# its rounded end to the stern, a short neck up at its fore end with the red valve wheel, a pipe looping under it. Measured off the side view through
# the hull's mapping (mx, my): the body z -5.3 .. -8.1, y 1.8 .. 3.0; the valve at z -5.8, y 3.0.
TANK = (mx(-5.34), my(2.97), mx(-8.14), my(1.80))


def forsage_tank_items():
    x0, y0, x1, y1 = TANK
    mid = (y0 + y1) / 2
    end = 14
    body = f"M{x0:.1f} {y0:.1f} L{x1 - end:.1f} {y0:.1f} Q {x1 + 2:.1f} {y0:.1f} {x1 + 2:.1f} {mid:.1f} Q {x1 + 2:.1f} {y1:.1f} {x1 - end:.1f} {y1:.1f} L{x0:.1f} {y1:.1f} Z"
    out = [art.path(body, 1.8, art.INK, STEEL_D), art.hatch([(x0, mid - 2), (x1, mid - 2), (x1, y1), (x0, y1)], 70, 3.0, 0.8)]
    out.append(art.path(f"M{x0 + 7:.1f} {y0 + 3:.1f} L{x1 - end - 6:.1f} {y0 + 3:.1f}", 1.0, "#fff8ec", op=0.9))
    for bx in (x0 + 4, x0 + 9, x1 - end - 2):
        out.append(art.path(f"M{bx:.1f} {y0:.1f} L{bx:.1f} {y1:.1f}", 1.2))
    for bx in (x0 + 26, x0 + 50):
        for by in (y0 + 5, y1 - 5):
            out.append(art.dot(bx, by, 1.0))
    # the pipe looping under it
    out.append(art.path(f"M{x0 + 18:.1f} {y1 - 9:.1f} L{x1 - 26:.1f} {y1 - 9:.1f} Q {x1 - 12:.1f} {y1 - 9:.1f} {x1 - 12:.1f} {y1 - 17:.1f}", 6.0, art.INK))
    out.append(art.path(f"M{x0 + 18:.1f} {y1 - 9:.1f} L{x1 - 26:.1f} {y1 - 9:.1f} Q {x1 - 12:.1f} {y1 - 9:.1f} {x1 - 12:.1f} {y1 - 17:.1f}", 3.4, STEEL_L))
    # the neck and the red valve wheel
    vx, vy = mx(-5.82), my(3.0) - 8
    out.append(art.path(art.poly([(vx - 5, y0 + 1), (vx - 4, vy + 4), (vx + 4, vy + 4), (vx + 5, y0 + 1)], True), 1.4, art.INK, STEEL_L))
    out.append(art.circle(vx, vy, 7, 1.6, art.INK, HOT))
    out.append(art.circle(vx, vy, 3.2, 1.0, art.INK, "#e8a07a"))
    for a_ in range(0, 360, 60):
        ca, sa = math.cos(math.radians(a_)), math.sin(math.radians(a_))
        out.append(art.path(f"M{vx + 3.2 * ca:.1f} {vy + 3.2 * sa:.1f} L{vx + 6.6 * ca:.1f} {vy + 6.6 * sa:.1f}", 1.0))
    return out


def forsage_tank_area():
    x0, y0, x1, y1 = TANK
    return [(x0 - 4, y0 - 20), (x1 + 6, y0 - 20), (x1 + 6, y1 + 4), (x0 - 4, y1 + 4)]


def lookouts_items():
    out = []
    for x, y in art.CUPOLAS:
        out += nest_figure("lookout", x, NEST_BASE, NEST_S) + ring_front(x, y)
    return out


def tree_parts(places, parts):
    """The layers of the details the tree brings that the base drawing had no picture of: ink, pencil (not for the lookouts: no rings, no nests to
    stand in), build."""
    for name, items, area, pencil in (("balloon_shields", balloon_shields_items(), balloon_shields_area(), True),
                                      ("forsage_tank", forsage_tank_items(), forsage_tank_area(), True),
                                      ("lookouts", lookouts_items(), [(352, 0), (700, 0), (700, 76), (352, 76)], False)):
        layer(f"{name}_ink", items, places)
        if pencil:
            layer(f"{name}_pencil", pencil_of(items), places)
        layer(f"{name}_build", build_of(items, area), places)
        parts[name] = {"pencil": f"{name}_pencil" if pencil else None, "build": f"{name}_build", "ink": f"{name}_ink"}


def tree_line():
    """The brass of the lines between the nodes of the tree of buildings (web/js/panel.js): one colour, stretched by the panel; the copper of the plates' edge."""
    from PIL import Image
    Image.new("RGBA", (4, 4), (197, 139, 74, 255)).save(OUT / "tree_line.png")


def node_back():
    """The parchment under a node's icon in the tree of buildings: a clean piece of the drawing's own paper (blueprint_planks.png, above the timber)."""
    from PIL import Image
    S = art.SCALE
    Image.open(OUT / "blueprint_planks.png").crop((round(470 * S), round(200 * S), round(530 * S), round(260 * S))).resize((96, 96)).save(OUT / "node_back.png", optimize=True)


# ---------------- sheets for checking: the game's model beside the drawing, the details with and without ----------------
REFS = REPO / "build" / "crew_models" / "groups"
SHEETS = REPO / "build" / "web" / "shots" / "groups"


def model_refs():
    """build/crew_models/groups: the game's models rendered plain by tools/crew_cards.py's renderer (its card scenes: the guns in the port, a bomb under
    the bay, the nests with their crews; the barge's lookout in a nest; the stock barge from the left), the references of the drawings above."""
    import numpy as np
    from PIL import Image
    import crew_cards as cc
    REFS.mkdir(parents=True, exist_ok=True)

    def plain(fr):
        col, mask = cc.lit(fr)
        return Image.fromarray((np.clip(col * mask[..., None] + .72 * (1 - mask[..., None]), 0, 1) * 255).astype(np.uint8))
    for name in ("cannons_stock", "cannons_flaming", "cannons_organ", "cannons_clatter", "cannons_flame", "bombs_stock", "bombs_fire", "cupolas_stock", "cupolas_axes"):
        if not (REFS / f"{name}.png").exists():
            plain(cc.CARDS[name][0](1)).save(REFS / f"{name}.png")
    if not (REFS / "cupolas_lookout.png").exists():
        plain(cc.cupola_card("dwf_thunderbarge_crew_lookout", cc.THROW, 0, ())[0](1)).save(REFS / "cupolas_lookout.png")
    if not (REFS / "stock_side.png").exists():
        fr = cc.Frame(1700, 1300, cc.look([90, 9.5, -1.7], [0, 9.5, -1.7]), 90 / 34.0)
        cc.draw_hull(fr, balloon=True)
        plain(fr).save(REFS / "stock_side.png")


def drawing_crop(layers_, box, k):
    """The base drawing with these layers over it, the box (units of the drawing) at the page's scale k (1.029 px a unit at 1)."""
    from PIL import Image
    data = json.loads((OUT / "layers.json").read_text(encoding="utf-8"))["places"]
    own = json.loads((REPO / "data" / "crew_ui_art.json").read_text(encoding="utf-8"))["layers"]
    S = art.SCALE
    base = Image.open(OUT / "blueprint_base.png").convert("RGBA")
    for name in layers_:
        p, path = (data[name], OUT / f"{name}.png") if name in data else (own[name], REPO / "data" / "ui" / f"{name}.png")
        im = Image.open(path).convert("RGBA").resize((round(p[2] * S), round(p[3] * S)), Image.LANCZOS)
        base.alpha_composite(im, (round(p[0] * S), round(p[1] * S)))
    crop = base.crop(tuple(round(v * S) for v in box)).convert("RGB")
    f = k * 1.029 / S
    return crop.resize((max(1, round(crop.width * f)), max(1, round(crop.height * f))), Image.LANCZOS)


# what of each model's render is the subject (x0, y0, x1, y1 of the 480 x 1040 render) and of the drawing (units), with the layers under it
REF_BOX = {"cannons": (0, 420, 480, 760), "bombs": (120, 560, 400, 1000), "cupolas": (0, 380, 420, 900)}
DRAW_BOX = {"cannons": ((236, 500, 372, 584), ["port_ink"]), "bombs": ((410, 515, 700, 606), ["side_shields_ink", "mount_bombs"]),
            "cupolas": ((340, 0, 712, 80), ["mount_cupolas"])}
KIND_NAMES = {"stock": "", "flaming": "огненные снаряды", "organ": "органное", "clatter": "пулемёт", "flame": "огненная пушка", "fire": "огненные", "axes": "топоры",
              "lookout": "дозорные (деталь)", "empty": "пусто", "sketch": "в найме"}


def figures_sheets():
    """build/web/shots/groups/figures_ref_<group>.png: a row a kind, the game's model (crew_cards' renderer) | the drawing at the page's scale 1 |
    the drawing at the user's 0.6, at their real size."""
    from PIL import Image, ImageDraw, ImageFont
    model_refs()
    SHEETS.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("arial.ttf", 15)
    names = {"cannons": {"stock": "пушка барки"}, "bombs": {"stock": "бомбы"}, "cupolas": {"stock": "гранаты (Мстители)"}}
    for group, kinds in GROUP_KINDS.items():
        rows = [(k, REFS / f"{group}_{k}.png", [f"crew_{group}_{k}"]) for k in kinds]
        if group == "cupolas":
            rows.append(("lookout", REFS / "cupolas_lookout.png", ["lookouts_ink"]))
        rows.append(("sketch", None, [f"crew_{group}_{kinds[-1]}_sketch"]))
        rows.append(("empty", None, [f"crew_{group}_empty"] if group != "cupolas" else ["lookouts_ink"]))
        box, under = DRAW_BOX[group]
        cells = []
        for kind, ref, lay in rows:
            model = Image.open(ref).convert("RGB").crop(REF_BOX[group]) if ref else None
            if model:
                model = model.resize((round(model.width * 200 / model.height), 200), Image.LANCZOS)
            one = drawing_crop(under + [l for l in lay if l in json.loads((OUT / "layers.json").read_text(encoding="utf-8"))["places"]], box, 1.0)
            if one.height < 120:
                one2 = one.resize((one.width * 2, one.height * 2), Image.LANCZOS)
            else:
                one2 = one
            six = drawing_crop(under + [l for l in lay if l in json.loads((OUT / "layers.json").read_text(encoding="utf-8"))["places"]], box, 0.6)
            cells.append((kind, model, one2, six, one2 is not one))
        mw = max(280, max((c[1].width for c in cells if c[1]), default=0))
        ow = max(c[2].width for c in cells)
        sw = max(c[3].width for c in cells)
        rh = max(max(c[1].height if c[1] else 0, c[2].height, c[3].height) for c in cells) + 34
        sheet = Image.new("RGB", (mw + ow + sw + 60, rh * len(cells) + 40), (24, 21, 17))
        d = ImageDraw.Draw(sheet)
        d.text((10, 8), "модель игры (рендер crew_cards.py)", fill=(235, 189, 124), font=font)
        d.text((mw + 30, 8), "чертёж, масштаб 1" + (" (×2 для глаза)" if any(c[4] for c in cells) else ""), fill=(235, 189, 124), font=font)
        d.text((mw + ow + 50, 8), "масштаб 0.6", fill=(235, 189, 124), font=font)
        for i, (kind, model, one, six, doubled) in enumerate(cells):
            y = 34 + i * rh
            label = names.get(group, {}).get(kind) or KIND_NAMES.get(kind, kind)
            d.text((10, y), f"{group}: {label}", fill=(232, 220, 192), font=font)
            if model:
                sheet.paste(model, (10, y + 20))
            sheet.paste(one, (mw + 30, y + 20))
            sheet.paste(six, (mw + ow + 50, y + 20))
        sheet.save(SHEETS / f"figures_ref_{group}.png")


def parts_sheet():
    """build/web/shots/groups/parts_sheet.png: every detail a building of the tree brings, the drawing without it | with it (ink), and being built,
    beside the stock side view of the game's model where it shows."""
    from PIL import Image, ImageDraw, ImageFont
    model_refs()
    font = ImageFont.truetype("arial.ttf", 15)
    side = Image.open(REFS / "stock_side.png").convert("RGB")
    own = json.loads((REPO / "data" / "crew_ui_art.json").read_text(encoding="utf-8"))["layers"]
    places = json.loads((OUT / "layers.json").read_text(encoding="utf-8"))["places"]
    blueprint = json.loads((REPO / "web" / "data" / "blueprint.json").read_text(encoding="utf-8"))
    specs = dict(blueprint["parts"]) | {k: v for k, v in blueprint["stages"]["hull1"]["parts"].items() if k not in ("frame", "barge")}
    # the stock side view's boxes of each detail (px of stock_side.png): the model as the game has it
    side_box = {"port": (520, 840, 700, 1000), "porthole": (520, 840, 700, 1000), "stern_armour": (880, 740, 1040, 1100), "forsage_tank": (900, 860, 1120, 980),
                "bomb_hatches": None, "side_shields": (600, 880, 880, 990), "balloon_shields": (540, 380, 1200, 480), "pub": None,
                "rings": (580, 180, 1060, 260), "lookouts": None}
    rows = []
    for key, spec in specs.items():
        ink = spec.get("ink")
        if not ink or (ink not in places and ink not in own):
            continue
        p = places.get(ink) or own[ink]
        box = (p[0] - 20, p[1] - 14, p[0] + p[2] + 20, p[1] + p[3] + 14)
        under = ["mount_cupolas"] if key == "lookouts" else []
        without = drawing_crop(under, box, 1.4)
        with_ = drawing_crop(under + [ink], box, 1.4)
        build = drawing_crop(under + [spec["build"]], box, 1.4) if spec.get("build") and spec["build"] in places else None
        ref = side.crop(side_box[key]) if side_box.get(key) else None
        if ref:
            ref = ref.resize((round(ref.width * min(1.0, 140 / ref.height)), round(ref.height * min(1.0, 140 / ref.height))), Image.LANCZOS)
        rows.append((spec["name"], without, with_, build, ref))
    cw = max(r[1].width for r in rows)
    mw = max((r[4].width for r in rows if r[4]), default=0)
    hs = [max(r[1].height, r[4].height if r[4] else 0) + 30 for r in rows]
    sheet = Image.new("RGB", (cw * 3 + mw + 60, sum(hs) + 34), (24, 21, 17))
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(("без неё", "с ней", "строится")):
        d.text((10 + i * (cw + 10), 8), t, fill=(235, 189, 124), font=font)
    d.text((10 + 3 * (cw + 10), 8), "модель игры (сток, вид слева)", fill=(235, 189, 124), font=font)
    for i, (name, a, b, c, ref) in enumerate(rows):
        y = 30 + sum(hs[:i])
        d.text((10, y), name + ("  (снизу корпуса: сбоку модели не видно)" if not ref and name.startswith("Бомб") else ""), fill=(232, 220, 192), font=font)
        for j, im in enumerate((a, b, c)):
            if im:
                sheet.paste(im, (10 + j * (cw + 10), y + 20))
        if ref:
            sheet.paste(ref, (10 + 3 * (cw + 10), y + 20))
    sheet.save(SHEETS / "parts_sheet.png")


def hiring_sheet():
    """build/web/shots/groups/hiring_states.png: each group's place in its states, as the page lays them (the tag of the state over the kind):
    empty, hired (the sketch, the hourglass), standing (ink, the arrows), another kind hired while one stands (ink, the hourglass); at 1 and at 0.6."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype("arial.ttf", 15)
    boxes = {"cannons": (150, 495, 380, 650), "bombs": (405, 512, 700, 670), "cupolas": (340, 0, 712, 80)}
    under = {"cannons": ["port_ink"], "bombs": ["side_shields_ink", "mount_bombs"], "cupolas": ["mount_cupolas"]}
    states = [("пусто", lambda g, k: ([f"crew_{g}_empty"] if g != "cupolas" else ["lookouts_ink"]) + [f"crew_{g}_tag_plus"]),
              ("в найме", lambda g, k: [f"crew_{g}_{k}_sketch", f"crew_{g}_tag_wait"]),
              ("стоит", lambda g, k: [f"crew_{g}_{k}", f"crew_{g}_tag_swap"]),
              ("стоит, нанят другой", lambda g, k: [f"crew_{g}_{k}", f"crew_{g}_tag_wait"])]
    rows = []
    for g, kinds in GROUP_KINDS.items():
        for scale in (1.0, 0.6):
            rows.append((f"{g}, масштаб {scale}", [drawing_crop(under[g] + f(g, kinds[0]), boxes[g], scale) for _, f in states]))
    cw = max(im.width for _, ims in rows for im in ims)
    hs = [max(im.height for im in ims) + 26 for _, ims in rows]
    sheet = Image.new("RGB", (cw * 4 + 50, sum(hs) + 30), (24, 21, 17))
    d = ImageDraw.Draw(sheet)
    for j, (t, _) in enumerate(states):
        d.text((10 + j * (cw + 10), 6), t, fill=(235, 189, 124), font=font)
    for i, (label, ims) in enumerate(rows):
        y = 28 + sum(hs[:i])
        d.text((10, y), label, fill=(232, 220, 192), font=font)
        for j, im in enumerate(ims):
            sheet.paste(im, (10 + j * (cw + 10), y + 20))
    sheet.save(SHEETS / "hiring_states.png")


def groups_only():
    """py -3.10 tools/web_art.py --groups: only the layers of the guns', bombs' and nests' places and of the tree's details, into layers.json as it is."""
    data = json.loads((OUT / "layers.json").read_text(encoding="utf-8"))
    places, parts = data["places"], data["parts"]
    areas = {"rifles": data["crew_areas"]["rifles"]} | group_areas(places)
    tree_parts(places, parts)
    (OUT / "layers.json").write_text(json.dumps(data | {"places": places, "parts": parts, "crew_areas": areas}, indent=1), encoding="utf-8")


def main():
    if "--groups" in sys.argv:
        groups_only()
        return
    if "--sheets" in sys.argv:
        figures_sheets()
        parts_sheet()
        hiring_sheet()
        return
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
    branch_frames()
    branch_selected_frames()
    aboard_frames()
    node_back()
    # the hull's second level being built over the frame (last: the drawings above keep their random hatching)
    layer("barge_build", barge_build(), places)
    parts["barge"] = {"pencil": None, "build": "barge_build", "ink": None}
    # the pub: the cabin seen through the hull's side, as the panel's dashed place of the pub was (crew_ui_art.bay_marks): a dashed outline, a thin wash,
    # the men, table and barrels of crew_ui_art.occ_pub in ink but a little see-through, so the planks and the drive show behind
    x0, y0, x1, y1 = art.PUB
    layer_plain("pub_ink", pub_seen_through(), places)
    layer("pub_build", build_of(pub_seen_through(), [(x0 - 6, y0 - 6), (x1 + 6, y0 - 6), (x1 + 6, y1 + 6), (x0 - 6, y1 + 6)]), places)
    parts["pub"] = {"pencil": None, "build": "pub_build", "ink": "pub_ink"}
    # where Malakai stands: the plan with its marks and his figure (last, as above)
    side = side_art(places)
    crew = crew_area(places)
    # the other groups' places and the details of the tree's buildings (last: the drawings above keep their random hatching)
    areas = {"rifles": {**crew, "glow": {**crew["glow"], "prefix": "crew_glow"}}} | group_areas(places)
    tree_parts(places, parts)
    (OUT / "layers.json").write_text(json.dumps(json.loads((OUT / "layers.json").read_text(encoding="utf-8")) | {"places": places, "parts": parts, "malakai_side": side, "crew_area": crew, "crew_areas": areas}, indent=1), encoding="utf-8")
    crew_area_variants()
    crew_hiring_variants()
    for f in sorted(OUT.glob("*.png")):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
