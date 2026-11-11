"""The sheet of the tree's icons for the audit (docs/design/tree-audit.md): every building's icon on the game's parchment tile, with its name; the new and
the redrawn marked, «было | стало» for the changed ones.
    python tools/tests/tree_audit_icons_sheet.py [after.json] [before.json] [out.png]
Defaults: build/web/audit/tree_design.audit.json, build/web/tree_design.user_before_audit.json, build/web/shots/audit/icons_sheet.png.
The old picture of a redrawn icon is read from build/web/audit/<key>.before.png (git show HEAD:data/ui/buildings/<key>.png)."""
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
after = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "build/web/audit/tree_design.audit.json").read_text(encoding="utf-8"))
before = json.loads(Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "build/web/tree_design.user_before_audit.json").read_text(encoding="utf-8"))
out = Path(sys.argv[3] if len(sys.argv) > 3 else ROOT / "build/web/shots/audit/icons_sheet.png")
REDRAWN = {"airship_hull_3"}
frame = Image.open(Path(tempfile.gettempdir()) / "tww3_mtb_building_icon_refs" / "building_frame.png").convert("RGBA")


def icon_file(path):
    if not path:
        return None
    if path.startswith("ui/buildings/icons/tww3_mtb_"):
        return ROOT / "data/ui/buildings" / (path.removeprefix("ui/buildings/icons/tww3_mtb_"))
    return ROOT / "build/web/game" / path


def tile(path, z=2, file=None):
    t = frame.copy()
    f = file or icon_file(path)
    if f and f.exists():
        t.alpha_composite(Image.open(f).convert("RGBA").resize((74, 74)))
    else:
        d = ImageDraw.Draw(t)
        d.text((22, 30), "нет", fill=(120, 40, 30, 255), font=font(14, True))
    return t.resize((74 * z, 74 * z), Image.BICUBIC)


def font(size, bold=False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap(d, text, f, width):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return [x for x in lines + [cur] if x]


old = {n["id"]: n for n in before["nodes"]}
Z, PAD = 2, 10
cell_w, cell_h = 74 * Z * 2 + 3 * PAD + 6, 74 * Z + 64
cols = 4
nodes = sorted(after["nodes"], key=lambda n: (-n["row"], n["col"]))
rows = (len(nodes) + cols - 1) // cols
W, H = cols * cell_w + PAD, 60 + rows * cell_h + PAD
sheet = Image.new("RGBA", (W, H), (22, 20, 18, 255))
d = ImageDraw.Draw(sheet)
fg, dim, new_c, chg_c = (222, 210, 186), (150, 140, 120), (130, 220, 110), (255, 190, 90)
d.text((PAD, 10), f"Значки всех {len(nodes)} построек дерева (2×). Зелёная метка — новый значок, жёлтая — перерисован; слева «было», справа «стало».",
       font=font(15, True), fill=fg)
for i, n in enumerate(nodes):
    x, y = PAD + (i % cols) * cell_w, 50 + (i // cols) * cell_h
    o = old.get(n["id"], {})
    key = (n["icon"] or "").removeprefix("ui/buildings/icons/tww3_mtb_").removesuffix(".png")
    redrawn = key in REDRAWN
    changed = (o.get("icon") != n["icon"]) or redrawn
    if changed:
        before_file = ROOT / "build/web/audit" / f"{key}.before.png" if redrawn else None
        sheet.alpha_composite(tile(o.get("icon"), Z, before_file), (x, y))
        d.text((x + 74 * Z + 3, y + 74 * Z // 2 - 10), "→", font=font(18, True), fill=fg)
        sheet.alpha_composite(tile(n["icon"], Z), (x + 74 * Z + PAD + 12, y))
        mark, col = ("перерисован", chg_c) if redrawn else ("новый", new_c)
        d.rounded_rectangle((x + 74 * Z + PAD + 12, y - 2, x + 74 * Z + PAD + 12 + 92, y + 16), 4, fill=(20, 20, 20, 220))
        d.text((x + 74 * Z + PAD + 16, y), mark, font=font(13, True), fill=col)
    else:
        sheet.alpha_composite(tile(n["icon"], Z), (x, y))
        d.text((x + 74 * Z + PAD, y + 4), key, font=font(12), fill=dim)
    name = n["name"] + ("" if o.get("name") == n["name"] else f"  (было: {o.get('name', '').strip()})")
    for j, line in enumerate(wrap(d, name, font(13, True), cell_w - PAD * 2)[:3]):
        d.text((x, y + 74 * Z + 4 + j * 16), line, font=font(13, True), fill=fg)
out.parent.mkdir(parents=True, exist_ok=True)
sheet.convert("RGB").save(out)
print(out, sheet.size)
