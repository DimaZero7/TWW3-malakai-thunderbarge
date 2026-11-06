"""The comparison sheet from the renders of tools/ai_tex_render.py: venv python, ai_tex_sheet.py RAW_DIR OUT.png"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

RAW, OUT = Path(sys.argv[1]), Path(sys.argv[2])
COLS = ["stock", "script", "ai"]
LABEL = {"stock": "stock", "script": "current script version", "ai": "AI version"}
VIEWS = ["left_close", "right_close", "left_graze", "right_graze", "left_tight", "left_oblique", "left_far"]
W, H, GAP = 560, 400, 6
# the zone's part of the sheet: pixels of the box
X0, X1, Y0, Y1 = 940 - 680, 1180 - 680, 3660 - 3400, 3890 - 3400
crops = []
for c in COLS:
    a = np.load(RAW / f"crop_{c}.npy")[Y0:Y1, X0:X1, :3]
    crops.append(Image.fromarray(a).resize((W, int(W * a.shape[0] / a.shape[1])), Image.BICUBIC))
ch = crops[0].height
rows = [v for v in VIEWS if (RAW / f"{v}_stock.png").exists()]
sheet = Image.new("RGB", (3 * W + 2 * GAP, 22 + ch + GAP + len(rows) * (H + GAP)), "white")
d = ImageDraw.Draw(sheet)
for i, c in enumerate(COLS):
    d.text((i * (W + GAP) + 6, 5), LABEL[c], fill="black")
    sheet.paste(crops[i], (i * (W + GAP), 22))
for r, v in enumerate(rows):
    y = 22 + ch + GAP + r * (H + GAP)
    for i, c in enumerate(COLS):
        sheet.paste(Image.open(RAW / f"{v}_{c}.png").convert("RGB"), (i * (W + GAP), y))
sheet.save(OUT)
print(sheet.size)
