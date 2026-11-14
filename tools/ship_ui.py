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


def image(key, path, margin=None, interactive=False, colour=None, tile=False, attrs=""):
    """One picture over the component, stretched (margin: its 9-slice edges "l,t,r,b"); colour: the image's colour (RGBA)."""
    img = crew_ui.guid(key, "image", "main")
    state = crew_ui.state_xml("regular", key, 64, 64, [(img, margin, tile)], interactive=interactive)
    if colour:
        state = state.replace(f'componentimage="{img}"', f'componentimage="{img}" colour="{colour}"')
    out = crew_ui.layout(key, "image", {"main": path}, [state], "regular")
    return out.replace('<image this="' + crew_ui.guid(key, "comp") + '"', '<image this="' + crew_ui.guid(key, "comp") + '"' + attrs, 1) if attrs else out


def holder(key, interactive=False, attrs=""):
    """A box with no picture: a holder of other components (the stages of the drawing, the lines, the tree's content)."""
    out = crew_ui.layout(key, "holder", {}, [crew_ui.state_xml("regular", key, 64, 64, [], interactive=interactive)], "regular")
    return out.replace('<holder this="' + crew_ui.guid(key, "comp") + '"', '<holder this="' + crew_ui.guid(key, "comp") + '"' + attrs, 1) if attrs else out


def m(l, t, r, b):
    return f"{l:.2f},{t:.2f},{r:.2f},{b:.2f}"


# layout -> (what it is, its xml)
def layouts():
    return {
        "panel_ground": ("the panel's ground: the game's panel_back_tile.png in one piece, 9-slice", image("panel_ground", D + "panel_back_tile.png", m(10, 10, 10, 10))),
        "tree_pane": ("the working area's stone", image("tree_pane", D + "panel_back_tile_stone.png", m(8, 8, 8, 8))),
        "tree_page": ("the «Постройки» tab's page", holder("tree_page")),
        # probe 6: clipchildren on our own component (src/tww3_mtb_ship_uic.lua ENGINE.clips)
        "tree_window": ("the tree's window: takes a click, cuts its children", holder("tree_window", True, ' clipchildren="true"')),
        "tree_holder": ("the tree's content, moved under its window", holder("tree_holder")),
        "layer_holder": ("a holder of layers: the drawing's stages, the lines, the screen's root", holder("layer_holder")),
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
    return crew_ui.text_layout(key, spec["cat"], spec["pt"], spec["colour"].upper() + "FF", align, wrap, leading, valign)


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
