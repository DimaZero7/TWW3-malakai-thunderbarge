"""The AI paint into DDS copies of the stock sheets: blender --background --python tools/ai_tex_write_dds.py -- final.npz OUT_DIR

Only blocks touching the zone are encoded anew, in every mip down to 16 pixels (same writer as tools/blender_solid_hull_tex.py).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np

import blender_dds as bd
import blender_rmv2 as br
import blender_solid_hull_tex as t

args = sys.argv[sys.argv.index("--") + 1:]
data = np.load(args[0])
out = Path(args[1]) / "warmachines" / "tex"
out.mkdir(parents=True, exist_ok=True)
zone = data["zone"]
for part in ("base_colour", "normal", "material_map"):
    dds = bd.Dds(str(br.GAME_DIR / f"dwf_thunderbarge_grungni_01_{part}.dds"))
    count = t.write_mips(dds, data[part].astype(np.float32), zone, part)
    dds.save(str(out / f"{t.OWN}_{part}.dds"))
    print(part, count)
