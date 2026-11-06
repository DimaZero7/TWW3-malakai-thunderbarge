"""Grid of snapshots with captions (project venv: tools_ext/blender_skill_venv). Usage:
  blender_skill_sheet.py OUT.png COLS [--title TEXT] [--max N] IMG[=caption] ...
Rows are filled left to right; the sheet is scaled down so its long side is at most --max px (default 1600).
"""
import sys

from PIL import Image, ImageDraw, ImageFont


def main(argv):
    out, cols = argv[0], int(argv[1])
    rest, title, limit = argv[2:], None, 1600
    items = []
    i = 0
    while i < len(rest):
        if rest[i] == "--title":
            title, i = rest[i + 1], i + 2
        elif rest[i] == "--max":
            limit, i = int(rest[i + 1]), i + 2
        else:
            path, _, cap = rest[i].partition("=")
            items.append((path, cap))
            i += 1
    ims = [Image.open(p).convert("RGB") for p, _ in items]
    w, h = max(im.width for im in ims), max(im.height for im in ims)
    cap_h, top = 22, (34 if title else 0)
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, top + rows * (h + cap_h)), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
        tfont = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = tfont = ImageFont.load_default()
    if title:
        d.text((8, 6), title, fill=(235, 235, 235), font=tfont)
    for k, (im, (_, cap)) in enumerate(zip(ims, items)):
        x, y = (k % cols) * w, top + (k // cols) * (h + cap_h)
        sheet.paste(im, (x, y + cap_h))
        d.text((x + 6, y + 3), cap, fill=(235, 235, 235), font=font)
    scale = min(1.0, limit / max(sheet.size))
    if scale < 1:
        sheet = sheet.resize((round(sheet.width * scale), round(sheet.height * scale)), Image.LANCZOS)
    sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main(sys.argv[1:])
