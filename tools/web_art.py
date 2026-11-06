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
    """(hull without shields and porthole, the side shields, the porthole) from crew_ui_art.hull()."""
    items = art.hull()
    first_shield = _index(items, art.circle(430, 503, 22.5, 1.5, art.INK, "#fff1dc"), "first shield")
    porthole = _index(items, art.circle(300, 476, 13, 1.6, art.INK, "#fff1dc"), "porthole")
    outline = _index(items, art.path(art.poly(art.hull_outline(), True), 2.6), "hull outline")
    return items[:first_shield] + items[outline:], items[first_shield:porthole], items[porthole:outline]


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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    hull_items, shields, porthole = hull_split()
    rear_items, stern = rear_split()
    blueprint_base(hull_items, rear_items).save(OUT / "blueprint_base.png", optimize=True)
    places = {}
    # the port: its ink is the panel's own mount_cannons (data/ui), pencil and build drawn here
    layer("port_pencil", port_pencil(), places)
    layer("port_build", port_build(), places)
    parts = {"port": {"pencil": "port_pencil", "build": "port_build", "ink": "mount_cannons"}}
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
        "_about": "Made by tools/web_art.py. Places in units of the drawing (data/crew_ui_art.json, size). The ink of the port is data/ui/mount_cannons.png, "
                  "placed by data/crew_ui_art.json; every other layer is in web/art. blueprint_base.png: the panel's drawing without the details below.",
        "places": places, "parts": parts}, indent=1), encoding="utf-8")
    for f in sorted(OUT.glob("*.png")):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
