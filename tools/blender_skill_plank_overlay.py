"""Draws the plank gap lines (traced on the hull through the atlas arcs) and the belt edge over renders.
  blender_skill_plank_overlay.py PROJ.json KEY IMG OUT        KEY: entry of PROJ.json made in Blender for that camera
Yellow: gaps found on both sides of the port; red: gaps found left of it; blue: right of it; green: belt edge.
"""
import json
import sys

from PIL import Image, ImageDraw

COL = {"both": (255, 220, 0), "left": (255, 40, 40), "right": (60, 120, 255), "edge": (0, 220, 90)}


def main(proj, key, img, out):
    d = json.load(open(proj))[key]
    im = Image.open(img).convert("RGB")
    dr = ImageDraw.Draw(im)
    for kind, segs in d.items():
        for a, b in segs:
            if a and b:
                dr.line([tuple(a), tuple(b)], fill=COL[kind], width=2)
    im.save(out)


if __name__ == "__main__":
    main(*sys.argv[1:5])
