"""The airship screen's own files in the pack (docs/design/port-to-game.md 3.2): the layouts src/tww3_mtb_ship_ui.lua creates its components from,
its text layouts and its pictures. Called by tools/ship_lua.py files() (tools/build.py packs it); the layouts of the old crew panel stay in
tools/crew_ui.py, whose helpers these are written with, and are not written twice.

  files(text_layouts)   {pack path: bytes}: ui/tww3_mtb/<layout>.twui.xml for every layout the screen uses and the old panel does not have, a text
                        layout for every entry of web/js/ui_text.mjs (carried by build/tree/ship_ui_config.json), the page's stage layers web/art/*.png
                        at ui/tww3_mtb/web/ (the path src/tww3_mtb_ship_ui.lua reads them by), and the pictures the page made from the game's own
                        (tools/web_export.py: the cards' frames recoloured, the close views of the crew, Malakai's round portrait) from build/web/game
                        when they are there: built, never tracked
  LAYOUTS               the layouts and what each draws
The game's own pictures are referenced by their pack path (ui/skins/default/...) and never copied.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import crew_ui  # noqa: E402

SEP = chr(92)
WEB_ART = REPO / "web" / "art"
GAME_COPY = REPO / "build" / "web" / "game"
D = "ui/skins/default/"
LIGHT = "#FFF8D7FF"
# the pictures made by tools/web_export.py out of the game's (recoloured or rendered): packed from the build when it has them
DERIVED = ["ui/skins/tww3_mtb", "ui/tww3_mtb_cards", "ui/portraits/round/mtb_malakai.png"]


def with_attrs(out, kind, attrs):
    """attrs (' name="value"') on the component's own element in <components>, where the game reads them. Not on its node in <hierarchy>, which
    names the component only: clipchildren put there was ignored by the game (runs/20261114-230723-ship_panel, ss_fresh_tree.png: the tree spilled
    over the header), while the probe's pp_clip, which carries it on the element, clipped (probe 14.11, 6a)."""
    if not attrs:
        return out
    mark = f'id="{kind}" '
    if out.count(mark) != 1:
        raise SystemExit(f"tools/crew_ui.py layout changed: no single {mark!r} to put {attrs!r} on")
    return out.replace(mark, mark + attrs.strip() + " ", 1)


def image(key, path, margin=None, interactive=False, colour=None, tile=False, attrs=""):
    """One picture over the component, stretched (margin: its 9-slice edges "l,t,r,b"); colour: the image's colour (RGBA)."""
    img = crew_ui.guid(key, "image", "main")
    state = crew_ui.state_xml("regular", key, 64, 64, [(img, margin, tile)], interactive=interactive)
    if colour:
        state = state.replace(f'componentimage="{img}"', f'componentimage="{img}" colour="{colour}"')
    return with_attrs(crew_ui.layout(key, "image", {"main": path}, [state], "regular"), "image", attrs)


def holder(key, interactive=False, attrs=""):
    """A box with no picture: a holder of other components (the stages of the drawing, the lines, the tree's content)."""
    return with_attrs(crew_ui.layout(key, "holder", {}, [crew_ui.state_xml("regular", key, 64, 64, [], interactive=interactive)], "regular"), "holder", attrs)


# ---------------- pictures coloured in advance ----------------
# The game's UIComponent has no colour of a picture at run time (probe 14.11, item 0: no SetCurrentStateImageColour), and the page colours some
# pictures (web/js/gameui.js SetImageColour: the picture's shape filled with the colour). Every (picture, colour) the screen asks for is made here once,
# with the shape's alpha and the colour, at tint_path(picture, colour): src/tww3_mtb_ship_uic.lua sets that picture in place of the colour.
# The sources are the game's own pictures as tools/web_export.py copied them to build/web/game (built, never tracked); without them no variant is made
# (tools/ui_layout_check.py then names the missing picture).
TINTS = [
    ("ui/skins/default/bar_white.png", (44, 140, 30)),          # the health bar of a crew's card (src/tww3_mtb_ship_ui.lua unitCard)
    ("ui/skins/default/bar_white.png", (235, 189, 124)),        # the stat bars of a unit's panel
    ("ui/skins/default/bar_white.png", (255, 211, 106)),        # a lit link into the slot under the mouse (K.LIT_IN)
    ("ui/skins/default/bar_white.png", (145, 231, 50)),         # a lit link out of it (K.LIT_OUT)
    ("ui/skins/default/building_frame_hover.png", (255, 211, 106)),     # the ring of a slot that the hovered one needs
    ("ui/skins/default/building_frame_hover.png", (145, 231, 50)),      # the ring of a slot that the hovered one opens
    ("ui/skins/default/building_frame_hover.png", (226, 40, 40)),       # the ring of a refused click
    ("ui/skins/default/unit_cat_holder_round_fill.png", (35, 158, 139)),    # the teal round of a level's development points (building_frame.twui.xml, dev_points: its light grey x #2CC7AF)
]
CLEAR = "ui/tww3_mtb/clear.png"     # a fully transparent picture: a holder that has a picture passes PropagateOpacity to its children


def tint_path(path, rgb):
    """The pack path of a picture coloured in advance (the same rule as src/tww3_mtb_ship_uic.lua tint_path)."""
    stem = path.rsplit("/", 1)[-1][:-4]
    return "ui/tww3_mtb/tint/" + stem + "_" + "".join(f"{c:02x}" for c in rgb) + ".png"


def _png_rgba(data):
    """(w, h, rows of RGBA bytes) of an 8-bit RGBA or RGB PNG, not interlaced (the game's UI pictures are): enough for the tints, no PIL in 3.14."""
    import struct
    import zlib
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, head = 8, b"", None
    while pos < len(data):
        n, tag = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, depth, ctype, _, _, interlace = head
    if depth != 8 or ctype not in (2, 6) or interlace:
        raise ValueError(f"PNG depth {depth} type {ctype} interlace {interlace}")
    bpp = 4 if ctype == 6 else 3
    raw, stride, rows, prev = zlib.decompress(idat), w * bpp, [], bytearray(w * bpp)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        rows.append(bytes(line) if bpp == 4 else bytes(v for k in range(w) for v in (*line[k * 3:k * 3 + 3], 255)))
    return w, h, rows


def _png_write(w, h, rows):
    import struct
    import zlib

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xffffffff)
    raw = b"".join(b"\x00" + r for r in rows)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def tinted(data, rgb):
    """The picture's shape (its alpha) filled with the colour, as the page draws a coloured picture (gameui.js SetImageColour, a mask)."""
    w, h, rows = _png_rgba(data)
    r, g, b = rgb
    return _png_write(w, h, [bytes(v for k in range(w) for v in (r, g, b, row[k * 4 + 3])) for row in rows])


def tint_files():
    """{pack path: bytes} of the coloured pictures whose sources are in build/web/game, and the transparent picture."""
    out = {CLEAR.replace("/", SEP): _png_write(1, 1, [bytes(4)])}
    for path, rgb in TINTS:
        src = GAME_COPY / path
        if src.exists():
            out[tint_path(path, rgb).replace("/", SEP)] = tinted(src.read_bytes(), rgb)
    return out


def m(l, t, r, b):
    """A picture's 9-slice edges as the game reads a margin: top, right, bottom, left (CSS order; the game's own layouts: separator_skull2.png
    "0,50,0,50" with its ornaments left and right, turns_banner_queued.png "0,40,0,30" with the hourglass in its left 30). Written l, t, r, b
    before: the separator got 50 at its top and bottom on a 14 high picture, and the game drew past it the neighbours of the picture in its texture
    (a white gunsight and a dark stroke under every rule: runs/20261115-012811-ship_panel, defect 4)."""
    return f"{t:.2f},{r:.2f},{b:.2f},{l:.2f}"


# The pictures most components of the screen show (a slot's parts, the lines, the cost plates): each has a picture layout img_<stem> of its own,
# made with it, so the game is not asked to SetImagePath once per component (the first sessions: 1502 calls, 0.345 s of the 2.1 s opening). The same
# list is src/tww3_mtb_ship_uic.lua PRESET_IMAGES; tools/ui_layout_check.py builds through it (a missing layout fails there).
PRESET_IMAGES = [D + n + ".png" for n in (
    "building_frame", "building_frame_hover", "building_frame_plain", "building_frame_selected", "building_frame_selected_hover", "constructing_1",
    "icon_check_green", "padlock", "icon_treasury", "turns_banner_queued", "icon_banner_bg", "red_text_banner_shadow", "unit_cat_holder_round",
    "unit_cat_holder_round_fill", "icon_hourglass", "unit_card_build_frame")] + ["ui/tww3_mtb/web/tree_line.png"]


def preset_layout(path):
    return "img_" + path.rsplit("/", 1)[-1][:-4]


# layout -> (what it is, its xml)
def layouts():
    return {**{preset_layout(p): (f"the picture {p}, made with its component", image(preset_layout(p), p)) for p in PRESET_IMAGES},
        "panel_ground": ("the panel's ground: the game's panel_back_tile.png in one piece, 9-slice", image("panel_ground", D + "panel_back_tile.png", m(10, 10, 10, 10))),
        "tree_pane": ("the working area's stone", image("tree_pane", D + "panel_back_tile_stone.png", m(8, 8, 8, 8))),
        "tree_page": ("the «Постройки» tab's page", holder("tree_page")),
        # probe 6: clipchildren on our own component (src/tww3_mtb_ship_uic.lua ENGINE.clips)
        "tree_window": ("the tree's window: takes a click, cuts its children", holder("tree_window", True, ' clipchildren="true"')),
        "tree_holder": ("the tree's content, moved under its window", holder("tree_holder")),
        # a transparent picture: PropagateOpacity passes from a component that has a picture (runs/20261114-230723-ship_panel, step opacity), and
        # the lines' holder is dimmed as one under a lit slot (src/tww3_mtb_ship_uic.lua, the opacity)
        "layer_holder": ("a holder of layers: the drawing's stages, the lines, the screen's root", image("layer_holder", CLEAR)),
        "hover_holder": ("the pictures shown while the mouse is over a crew place", holder("hover_holder")),
        "hit_area": ("a place that takes a click: a crew place, a card of a choice, a row of the crew", holder("hit_area", True)),
        "separator_skull": ("the game's title rule", image("separator_skull", D + "separator_skull2.png", m(50, 0, 50, 0))),
        "tooltip_frame": ("the game's tooltip window (building_information)", image("tooltip_frame", D + "tooltip_frame.png", m(15, 15, 15, 15))),
        "tooltip_instruction": ("the window under a unit's panel", image("tooltip_instruction", D + "tooltip_frame.png", m(16, 20, 16, 20))),
        "info_rule": ("the thin rule over a building window's foot", image("info_rule", D + "bar_white.png", colour="#6B4A26FF")),
        "unit_parchment": ("the unit information panel's ground", image("unit_parchment", D + "panel_back_tile.png", m(10, 10, 10, 10))),
        "unit_header": ("the head of a unit's stats", image("unit_header", D + "parchment_button_square_active.png", m(10, 10, 10, 10))),
        # question V5: a still in the game, not a clip: the dark plate the page plays its video on
        "movie": ("the place of a crew's clip: a dark plate", image("movie", crew_ui.UI_DIR + "backdrop.png", colour="#15110CFF")),
        "turns_banner": ("the game's banner of a recruitment's turns", image("turns_banner", D + "turns_banner_queued.png", m(30, 0, 40, 0))),
        "cost_plate": ("the plate of a recruitment's cost", image("cost_plate", D + "frame_text.png", m(4, 4, 4, 4))),
        "slider_handle_v": ("the scroll bar's handle", image("slider_handle_v", D + "slider_vertical_handle.png", m(0, 18, 0, 18), interactive=True)),
        "slider_handle_h": ("the scroll bar's handle", image("slider_handle_h", D + "slider_horizontal_handle.png", m(18, 0, 18, 0), interactive=True)),
        "foot_strip": ("the foot row's dark strip", image("foot_strip", crew_ui.UI_DIR + "backdrop.png", colour="#080706B8")),
        "button_mark": ("a mark of Malakai's side: a button of four states", crew_ui.button_layout("button_mark", "web/mark", margin=None)),
    }


def text_layout(key, spec):
    """A text layout of web/js/ui_text.mjs: the game's category and size, the colour, the alignment, one line or many."""
    align = {"center": "Center", "right": "Right"}.get(spec.get("align"))
    wrap = "Never split" if spec.get("nowrap") else None
    valign = "Top" if spec.get("valign") == "top" else "Center"
    leading = max(0, round((spec.get("line") or 0) - spec["size"] * 1.25)) if spec.get("line") else 1
    out = crew_ui.text_layout(key, spec["cat"], spec["pt"], spec["colour"].upper() + "FF", align, wrap, leading, valign, spec.get("preset") or "")
    if spec.get("outline"):
        # the game's black outline round the letters (building_frame.twui.xml, dy_num_points_required: text_outline_t0)
        mark = f'fontcat_name="{spec["cat"]}"'
        if out.count(mark) != 1:
            raise SystemExit(f"tools/crew_ui.py text layout changed: no single {mark!r} to put the outline on")
        out = out.replace(mark, mark + ' text_shader_name="text_outline_t0" textshadervars="0.00,0.00,0.00,1.00"', 1)
    return out


def files(text_layouts):
    def path(name, ext):
        return f"ui{SEP}tww3_mtb{SEP}{name}{ext}"
    old = set(crew_ui_layout_names())
    out = {}
    for name, (_, xml) in layouts().items():
        if name not in old:
            out[path(name, ".twui.xml")] = xml.encode("utf-8")
    for name, spec in text_layouts.items():
        if name not in old:
            out[path(name, ".twui.xml")] = text_layout(name, spec).encode("utf-8")
    for f in sorted(WEB_ART.glob("*.png")):
        out[f"ui{SEP}tww3_mtb{SEP}web{SEP}{f.name}"] = f.read_bytes()
    out.update(tint_files())
    for d in DERIVED:
        src = GAME_COPY / d
        for f in ([src] if src.suffix == ".png" else sorted(src.glob("*.png")) if src.exists() else []):
            if f.exists():
                out[SEP.join(f.relative_to(GAME_COPY).parts)] = f.read_bytes()
    return out


def crew_ui_layout_names():
    """The layouts tools/crew_ui.py already writes (the old panel's): not written again."""
    return ["image", "zone", "frame", "frame_dark", "frame_edge", "backdrop", "text_title", "text_head", "text_name", "text_name_grey", "text_body",
            "text_line", "text_line_grey", "text_copper", "text_note", "button_plate", "button_row"]
