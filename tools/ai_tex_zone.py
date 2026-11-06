"""The zone to repaint and the plank rows around it, for the AI texture test: blender --background --python tools/ai_tex_zone.py

Writes build/solid_hull_ai/zone.npz and four stock crops of the zone's box as raw arrays. Reads stock files only; none of the earlier paint is used.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np

import blender_dds as bd
import blender_rmv2 as br
import blender_solid_hull as sh
import blender_solid_hull_tex as t

OUT = br.REPO / "build" / "solid_hull_ai"
OUT.mkdir(parents=True, exist_ok=True)
p = t.Paint()
# rows: the fitted curves at a step of one row over the whole box, so plank gaps can be drawn straight along them
x0, y0, x1, y1 = t.BOX
us = np.arange(x0, x1, dtype=np.float32)
cmin, cmax = p.wood.c(p.uu, p.vv).min(), p.wood.c(p.uu, p.vv).max()
np.savez_compressed(
    OUT / "zone.npz",
    box=np.array(t.BOX),
    zone=p.zone,
    above=p.above,
    depth=p.depth,
    wood_c=p.wood.c(p.uu, p.vv),
    belt_v=p.belt.f(us),
    us=us,
    painted=p.painted,
    ring=np.array(t.RING),
    shift=p.shift,
)
for part in ("base_colour", "normal", "material_map", "mask"):
    f = br.GAME_DIR / f"dwf_thunderbarge_grungni_01_{part}.dds"
    if f.exists():
        d = bd.Dds(str(f))
        print(part, d.level_size(0), d.mips)
        np.save(OUT / f"stock_{part}.npy", d.read(0, *t.BOX).astype(np.uint8))
print("zone px", int(p.zone.sum()), "c", cmin, cmax, "painted bbox", p.painted.min(axis=0), p.painted.max(axis=0), "ring", t.RING)
