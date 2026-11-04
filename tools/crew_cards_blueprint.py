"""Trial crew card in the style of the crew panel's blueprint: pen lines on old parchment, hatching, copper accents: python tools/crew_cards_blueprint.py

Drawn in code as the panel is (tools/crew_ui_art.py: its pen, hatch, wobble filter, parchment and colours), painted by Chrome. Bow to the left, the side recedes to the bow.
Writes docs/research/img/crew-card-blueprint-test.png and crew-card-blueprint-compare.png; touches nothing in data/.
"""
import io
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.dont_write_bytecode = True
import crew_ui_art as art  # noqa: E402
from crew_ui_art import COPPER, INK, INK_SOFT, STEEL, circle, dot, fmt, hatch, path, poly, shape, smooth  # noqa: E402

art.TEMP = ROOT / "build" / "crew_cards_blueprint"     # not the panel's own folder
IMG = ROOT / "docs" / "research" / "img"
DW, DH = 240, 520
SCALE = 4
LINE = 2.3            # 1 px and a little on the 120 x 260 card
THIN = 1.35
SKIN, BEARD, COAT, WOOD, HORN, HELM, TRIM = "#dcae74", "#9c4f20", "#8a5428", "#a86c38", "#e6c591", "#4c3b28", "#c98a46"


def horn(pl, base, bend, tip, w):
    """A tapered curved horn with its ring lines."""
    (bx, by), (mx, my), (tx, ty) = pl.pts(base, bend, tip)
    s = pl.s
    dx, dy = tx - bx, ty - by
    ln = math.hypot(dx, dy)
    nx, ny = -dy / ln, dx / ln
    left = [(bx + nx * w * s, by + ny * w * s), (mx + nx * w * .62 * s, my + ny * w * .62 * s), (tx, ty)]
    right = [(mx - nx * w * .62 * s, my - ny * w * .62 * s), (bx - nx * w * s, by - ny * w * s)]
    out = [path(smooth(left + right) + " Z", LINE, INK, HORN)]
    for t in (.28, .52):
        qx, qy = bx + (mx - bx) * t * 1.6, by + (my - by) * t * 1.6
        k = w * s * (1 - t * .5)
        out.append(path(f"M{fmt(qx + nx * k, qy + ny * k)} L{fmt(qx - nx * k, qy - ny * k)}", THIN * .85, INK, op=.75))
    return out


def limb(points, width, fill, line=LINE):
    """A thick round stroke with an inked edge: an arm."""
    d = smooth(points)
    return [path(d, width + line * 1.6, INK), path(d, width, fill)]


class Place:
    """Local coordinates of a figure: x to the right, y down, the origin where the waist meets the rail."""

    def __init__(self, x, y, s):
        self.x, self.y, self.s = x, y, s

    def p(self, px, py):
        return self.x + px * self.s, self.y + py * self.s

    def pts(self, *points):
        return [self.p(*q) for q in points]


def crossbow(pl, butt, tip, span=35.0):
    """Aimed out over the side, down and to the left: a short stock and, square across its nose, the arc of the bow with its string, the shape nothing else on the ship has."""
    s = pl.s
    bx, by = pl.p(*butt)
    tx, ty = pl.p(*tip)
    ln = math.hypot(tx - bx, ty - by)
    ux, uy = (tx - bx) / ln, (ty - by) / ln
    nx, ny = -uy, ux
    at = lambda t, off=0.0: (bx + ux * ln * t + nx * off * s, by + uy * ln * t + ny * off * s)
    # the bow lies square across the stock, a little turned to the viewer
    wx, wy = .34, .94
    across = lambda t, off, fwd=0.0: (bx + ux * ln * t + (wx * off + ux * fwd) * s, by + uy * ln * t + (wy * off + uy * fwd) * s)
    out = []
    t = .93
    a0, a1 = across(t, -span, -9), across(t, span, -9)
    bow = smooth([a0, across(t, -span * .62, 3), across(t, 0, 7), across(t, span * .62, 3), a1])
    catch = at(.40)
    out.append(path(poly([a0, catch, a1]), LINE + 2.6, "#d9a868"))     # a paper halo keeps the bow's shape apart from the coat
    out.append(path(poly([a0, catch, a1]), max(THIN * s + .25, 1.4), INK))
    out.append(path(bow, 8 * s + 6.0, "#d9a868"))
    out.append(path(bow, 8 * s + 2.5, INK))
    out.append(path(bow, 8 * s, "#2c2a28"))
    out.append(path(smooth([across(t, -span * .62, 4.5), across(t, 0, 8.6), across(t, span * .62, 4.5)]), 1.3, "#a9a59c"))
    for q in (a0, a1):        # the bow's tips, knobs the string hooks on
        out.append(circle(*q, 3.1 * s, LINE * .8, INK, TRIM))
    stock = [at(-.05, -8), at(.2, -5.5), at(.5, -5), at(1.04, -3.8), at(1.04, 3.8), at(.5, 5), at(.22, 6), at(.03, 12)]
    out.append(path(poly(stock, True), LINE, INK, WOOD))
    out.append(hatch(stock, angle=math.degrees(math.atan2(uy, ux)) + 62, gap=4.2 * s, w=.85, op=.5))
    out.append(path(poly([at(.93, -6), at(.93, 6)]), LINE * 1.1, INK))
    out.append(circle(*catch, 3.3 * s, THIN, INK, TRIM))
    # the stirrup in front of the bow
    out.append(path(smooth([at(1.04, -6.5), at(1.24), at(1.04, 6.5)]), LINE * .9, INK))
    return out, at


def dwarf(pl, butt, tip):
    """From the waist up, facing left and a little to the viewer: the butt in his right shoulder, the right hand at the trigger, the left under the fore-stock."""
    s = pl.s
    p = pl.p
    out = []
    bow_parts, at = crossbow(pl, butt, tip)
    # the body
    body = pl.pts((31, 8), (34, -30), (27, -58), (8, -69), (-16, -66), (-27, -46), (-30, -20), (-28, 8))
    out.append(path(smooth(body), LINE, INK, COAT))
    out.append(hatch(pl.pts((33, 8), (34, -30), (26, -56), (12, -50), (10, 8)), angle=68, gap=4.4 * s, w=.95, op=.7))
    out.append(path(poly(pl.pts((-29, -8), (32, -10), (33, -1), (-29, 1)), True), LINE * .9, INK, "#5e3a1c"))
    out.append(path(poly(pl.pts((-7, -10), (5, -10), (5, 0), (-7, 0)), True), THIN, INK, TRIM))
    # the right arm: far side, the elbow out, the forearm to the trigger
    trigger = at(.24, 4)
    out += limb([p(-20, -54), p(-29, -36), trigger], 10.5 * s, "#7a4a22")
    # the beard, short enough to leave the stock in sight
    beard = pl.pts((-23, -78), (-33, -66), (-34, -50), (-27, -38), (-21, -45), (-13, -34), (-6, -45), (1, -42), (5, -56), (5, -70), (-6, -76))
    out.append(path(smooth(beard, True), LINE, INK, BEARD))
    for line in (((-24, -68), (-25, -55)), ((-16, -69), (-15, -53)), ((-7, -70), (-6, -56))):
        out.append(path(poly(pl.pts(*line)), THIN * .85, INK, op=.75))
    # the head in profile, the eye low over the stock
    face = pl.pts((6, -84), (6, -71), (-5, -67), (-20, -69), (-24, -74), (-32, -77), (-26, -82), (-22, -90), (-5, -94))
    out.append(path(smooth(face, True), LINE, INK, SKIN))
    out.append(dot(*p(-16, -79), 1.9 * s + .4))
    out.append(path(poly(pl.pts((-23, -85), (-12, -86))), LINE, INK))
    # the far horn, the helmet, the near horn
    out += horn(pl, (-20, -100), (-34, -106), (-37, -124), 6)
    out.append(path(smooth(pl.pts((-26, -87), (-23, -103), (-9, -112), (7, -106), (15, -90))) + " Z", LINE, INK, HELM))
    out.append(path(poly(pl.pts((-28, -88), (17, -90), (17, -83), (-27, -82)), True), LINE * .9, INK, TRIM))
    for q in ((-18, -85), (-6, -86), (6, -86)):
        out.append(dot(*p(*q), 1.5 * s, INK))
    out += horn(pl, (10, -98), (27, -104), (31, -128), 8)
    # the crossbow, then the fingers of the right hand on its grip
    out += bow_parts
    out.append(circle(*at(.24, 2.5), 6.4 * s, LINE, INK, SKIN))
    for off in (-.035, 0, .035):
        out.append(path(poly([at(.24 + off, -3), at(.24 + off, 7)]), THIN * .85, INK))
    # the left arm: near side, from the shoulder forward to the fore-stock
    hand = at(.60, 5)
    out += limb([p(10, -54), p(6, -28), p(-16, -24), hand], 11.5 * s, COAT)
    out.append(path(smooth(pl.pts((-3, -58), (2, -69), (18, -68), (24, -54), (15, -44), (2, -46)), True), LINE, INK, COPPER))
    for q in ((6, -61), (15, -60), (10, -52)):
        out.append(dot(*p(*q), 1.35 * s))
    out.append(circle(*hand, 6.9 * s, LINE, INK, SKIN))
    for off in (-.035, 0, .035):
        out.append(path(poly([at(.60 + off, -3.2), at(.60 + off, 7)]), THIN * .85, INK))
    return out


def rail_y(x):
    """The top of the side: it recedes towards the bow, up and to the left."""
    return 282 + .15 * x + .00034 * (x - 120) ** 2


def hull():
    out = []
    top = [(x, rail_y(x)) for x in range(-8, 256, 12)]
    band = [(x, y + 21 + x * .03) for x, y in top]
    belly = [(x, 448 + .12 * x - .0012 * (x - 150) ** 2 + 34) for x in range(256, -9, -12)]
    out.append(shape(poly(top + belly, True), "#d09a5c", .97))
    # the rail: a hatched band like the panel's
    rail = top + band[::-1]
    out.append(path(poly(rail, True), LINE, INK, "#b97a40"))
    out.append(hatch(rail, angle=118, gap=4.0, w=1.1, color=INK, op=.85))
    # planks under the shields, a shade at the bottom
    for k in (0.60, 0.78, .92):
        line = [(x, band[i][1] + (belly[-1 - i][1] - band[i][1]) * k) for i, (x, _) in enumerate(top)]
        out.append(path(smooth(line), THIN, INK))
    shade = [(x, band[i][1] + (belly[-1 - i][1] - band[i][1]) * .74) for i, (x, _) in enumerate(top)]
    out.append(hatch(shade + belly, angle=62, gap=4.6, w=.95, op=.7))
    out.append(path(smooth(belly), LINE * 1.1, INK))
    # the shields stand along the side, as on the panel: copper and paper, a cross or the rune
    n = 0
    for x, r in ((222, 33), (163, 29), (112, 25.5), (67, 22.5), (27, 20)):
        y = rail_y(x) + 21 + r + 4
        fill = "#c9925a" if n % 2 else COPPER
        out.append(circle(x, y, r, LINE, INK, fill))
        out.append(circle(x, y, r - 4.6, THIN, INK))
        out.append(circle(x, y, r * .18, THIN, INK, "#e0b57c"))
        if n % 2 == 0:
            out.append(path(f"M{fmt(x - r * .6, y - r * .6)} L{fmt(x + r * .6, y + r * .6)} M{fmt(x + r * .6, y - r * .6)} L{fmt(x - r * .6, y + r * .6)}", LINE * .95, INK))
        else:
            out.append(path(poly([(x - r * .25, y + r * .56), (x - r * .25, y - r * .56), (x + r * .32, y - r * .22), (x - r * .25, y + .02 * r), (x + r * .32, y + r * .28), (x - r * .25, y + r * .56)]), LINE * .95, INK))
        n += 1
    return out


def background():
    """What stands behind the men: the net of ropes and pale construction lines of the sheet."""
    out = []
    op = .42
    for i in range(7):
        x0, x1 = 66 + i * 26, 38 + i * 38
        out.append(path(f"M{fmt(x0, 8)} L{fmt(x1, 300)}", THIN, INK_SOFT, op=op))
    for y, a, b in ((44, 66, 222), (88, 60, 240), (132, 56, 254)):
        out.append(path(smooth([(a - 4, y + 8), ((a + b) / 2, y + 16), (b + 6, y + 6)]), THIN, INK_SOFT, op=op))
    # the gear sketched in the upper corner, as on the panel's margins
    cx, cy, r = 52, 66, 26
    out.append(circle(cx, cy, r, THIN, INK_SOFT, op=.4))
    out.append(circle(cx, cy, r * .3, THIN, INK_SOFT, op=.4))
    for k in range(10):
        a = k * math.pi / 5
        out.append(path(f"M{fmt(cx + r * math.cos(a), cy + r * math.sin(a))} L{fmt(cx + (r + 6) * math.cos(a), cy + (r + 6) * math.sin(a))}", 2.4, INK_SOFT, op=.4))
    for k in range(5):
        a = k * math.pi / 5
        out.append(path(f"M{fmt(cx - r * .9 * math.cos(a), cy - r * .9 * math.sin(a))} L{fmt(cx + r * .9 * math.cos(a), cy + r * .9 * math.sin(a))}", THIN * .8, INK_SOFT, op=.34))
    return out


def scene():
    parts = background()
    # the far man first; the rail then hides everything below their waists
    parts += dwarf(Place(76, rail_y(76) + 3, .88), (0, -57), (-70, -46))
    parts += dwarf(Place(187, rail_y(187) + 3, 1.08), (0, -57), (-74, -46))
    parts += hull()
    return parts


def build():
    art.TEMP.mkdir(parents=True, exist_ok=True)
    ink = art.paint("card", art.svg_page(scene(), w=DW, h=DH, scale=SCALE), DW * SCALE, DH * SCALE)
    w, h = DW * SCALE, DH * SCALE
    paper = Image.fromarray(art.parchment(w // 2, h // 2).astype(np.uint8)).resize((w, h), Image.BICUBIC).convert("RGBA")
    paper.alpha_composite(ink)
    big = paper.convert("RGB")
    return big


def main():
    big = build()
    ref = Image.open(ROOT / "build" / "crew_cards_cache" / "ui__units__infopics__wh_main_dwf_organ_gun.png").convert("RGBA")
    alpha = ref.getchannel("A")
    small = big.resize((120, 260), Image.LANCZOS)
    card = small.convert("RGBA")
    card.putalpha(alpha)
    card.save(IMG / "crew-card-blueprint-test.png", optimize=True)
    icon = big.resize((60, 130), Image.LANCZOS)
    painted = Image.open(ROOT / "data" / "ui" / "crew_cards" / "rifles_quarrellers.png").convert("RGBA")
    panel = Image.open(ROOT / "data" / "ui" / "blueprint.png").convert("RGB").crop((300, 560, 940, 960)).resize((480, 300), Image.LANCZOS)
    cream = (232, 228, 218, 255)
    sheet = Image.new("RGBA", (1500, 860), cream)
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype("arial.ttf", 16)
    def put(im, x, y, label):
        sheet.alpha_composite(im.convert("RGBA"), (x, y))
        d.text((x, y - 22), label, font=f, fill=(40, 40, 40))
    put(card.resize((360, 780), Image.BICUBIC), 20, 44, "Новая, x3 (из 120x260)")
    put(big.resize((360, 780), Image.LANCZOS), 400, 44, "Исходник, без рваного края")
    put(card, 790, 44, "Новая 120x260")
    put(painted, 930, 44, "Живописная")
    put(icon, 790, 340, "Новая 60x130")
    put(painted.resize((60, 130), Image.LANCZOS), 930, 340, "Живописная")
    put(panel, 790, 530, "Панель, фрагмент")
    sheet.convert("RGB").save(IMG / "crew-card-blueprint-compare.png", optimize=True)


if __name__ == "__main__":
    main()
