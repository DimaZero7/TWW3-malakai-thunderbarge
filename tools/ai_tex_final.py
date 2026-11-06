"""The chosen planks and steel into the box, normal and material map for the zone, files for the DDS writer and the variants as PNG: venv python, ai_tex_final.py WOOD STEEL [OTHER_WOOD,...]"""
import json
import sys

import numpy as np
from PIL import Image

import ai_tex_compose as ac
from ai_tex_common import OUT

wood, steel = sys.argv[1], sys.argv[2]
z = ac.z
colour, rep = ac.compose(wood=wood)
colour, rep2 = ac.compose(steel=steel, base=colour)
rep.update(rep2)
maps, rep3 = ac.maps(colour)
rep.update(rep3)
rep["chosen"] = [wood, steel]
np.savez_compressed(OUT / "final.npz", zone=z.zone, base_colour=colour, normal=maps["normal"], material_map=maps["material_map"])
var = OUT / "variants"
var.mkdir(exist_ok=True)
Image.fromarray(ac.crop_box(colour[..., :3]).astype(np.uint8)).save(var / f"final_{wood}_{steel}.png")
Image.fromarray(ac.crop_box(z.base[..., :3])).save(var / "stock.png")
nm = maps["normal"]
Image.fromarray(np.stack([nm[..., 3], nm[..., 1], np.full(nm.shape[:2], 255.0)], axis=2)[tuple(slice(None) for _ in range(2))].astype(np.uint8)).crop((200, 220, 560, 520)).save(var / "final_normal_UVchannels.png")
Image.fromarray(np.stack([z.normal[..., 3], z.normal[..., 1], np.full(nm.shape[:2], 255)], axis=2).astype(np.uint8)).crop((200, 220, 560, 520)).save(var / "stock_normal_UVchannels.png")
if len(sys.argv) > 3:
    for other in sys.argv[3].split(","):
        if other.startswith("wood"):
            col, _ = ac.compose(wood=other)
        else:
            col, _ = ac.compose(steel=other, base=ac.compose(wood=wood)[0])
        Image.fromarray(ac.crop_box(col[..., :3]).astype(np.uint8)).save(var / f"{other}.png")
(OUT / "final_report.json").write_text(json.dumps(rep, indent=1), encoding="utf-8")
print(json.dumps(rep))
