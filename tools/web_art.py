"""Layers of the drawing for the stages of a building, for the web page of the airship screen: py -3.10 tools/web_art.py

Stages (docs/design/panel-upgrades-proposal.md, section 7): not built is pencil, being built is pale ink under red hatching, built is ink.
The ink of a part is the panel's own layer in data/ui (mount_cannons.png and so on, tools/crew_ui_art.py); this script draws only the other two stages,
with the same shapes and places as tools/crew_ui_art.py, painted the same way (headless Chrome, the same scale). Writes web/art/<part>_pencil.png,
<part>_build.png and their places in web/art/layers.json (x, y, w, h in units of the drawing, 1040 x 760, as data/crew_ui_art.json).
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


PARTS = {"port": {"ink": "mount_cannons", "pencil": port_pencil, "build": port_build}}


def layer(name, parts, places):
    """As crew_ui_art.layer, into web/art."""
    w, h = round(art.DRAW_W * art.SCALE), round(art.DRAW_H * art.SCALE)
    im = art.paint("web_" + name, art.svg_page(parts), w, h)
    box = im.getbbox()
    pad = 2
    box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, w), min(box[3] + pad, h))
    im.crop(box).save(OUT / f"{name}.png", optimize=True)
    places[name] = [round(box[0] / art.SCALE, 2), round(box[1] / art.SCALE, 2), round((box[2] - box[0]) / art.SCALE, 2), round((box[3] - box[1]) / art.SCALE, 2)]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    places = {}
    stages = {}
    for part, spec in PARTS.items():
        for stage in ("pencil", "build"):
            layer(f"{part}_{stage}", spec[stage](), places)
        stages[part] = {"pencil": f"{part}_pencil", "build": f"{part}_build", "ink": spec["ink"]}
    (OUT / "layers.json").write_text(json.dumps({"_about": "Made by tools/web_art.py. Places in units of the drawing (data/crew_ui_art.json, size); ink layers are in data/crew_ui_art.json, layers.",
                                                 "places": places, "parts": stages}, indent=1), encoding="utf-8")
    for f in sorted(OUT.glob("*.png")):
        print(f.name, f.stat().st_size)


if __name__ == "__main__":
    main()
