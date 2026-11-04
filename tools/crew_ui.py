"""The crew panel's files: TWUI layouts, art of data/ui, the numbers of every option. Called by tools/crew_options.py.

The layouts are small hand-made .twui.xml files, the same format as the game's and as those of MCT (Workshop 2927955021): one component under a root, a state per look.
The game finds them by path: CreateComponent(id, "ui/tww3_mtb/image"). All text uses the game's own font categories, so Cyrillic works as on the rest of the UI.
The numbers (damage, reload, range) are read from the rows the build makes, so a change of data/crew_options.json shows up in the panel without any other edit.
"""
import json
import struct
import sys
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import gamepack  # noqa: E402

BUILDING_LINE_SCOPE = "force_to_force_own"
SEP = chr(92)
ART = REPO / "data" / "ui"
CARDS = ART / "crew_cards"
UI_DIR = "ui/tww3_mtb/"
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
TEXT_LIGHT = "#FFF8D7FF"
TEXT_COPPER = "#EBBD7CFF"
TEXT_GREY = "#8E8A80FF"


def guid(*parts):
    h = uuid.uuid5(NS, "/".join(str(p) for p in parts)).hex.upper()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:32]}"


def state_xml(name, key, w, h, images, transitions=None, interactive=True, disabled=False, text=None, shader=None):
    """images: list of (component image guid, margin or None, tile)."""
    this = guid(key, "state", name)
    attrs = f'this="{this}" name="{name}" width="{w}" height="{h}" uniqueguid="{this}"'
    if interactive:
        attrs += ' interactive="true"'
    if disabled:
        attrs += ' disabled="true"'
    body = ""
    if text:
        align = f' texthalign="{text["align"]}"' if text.get("align") else ""
        wrap = f' texthbehaviour="{text["wrap"]}"' if text.get("wrap") else ""
        body += (f'<component_text text=""{align}{wrap} textvalign="{text.get("valign", "Center")}" font_m_size="{text["size"]}" font_m_colour="{text["colour"]}" '
                 f'font_m_leading="{text.get("leading", 1)}" fontcat_name="{text["cat"]}"/>')
    if images:
        rows = []
        for i, (image, margin, tile) in enumerate(images):
            image_id = guid(key, name, "metric", i)
            extra = (f' margin="{margin}"' if margin else "") + (' tile="true"' if tile else "") + (f' shader_name="{shader}" shadervars="1.00,1.00,0.00,0.00"' if shader else "")
            rows.append(f'<image this="{image_id}" uniqueguid="{image_id}" componentimage="{image}" width="{w}" height="{h}"{extra}/>')
        body += "<imagemetrics>" + "".join(rows) + "</imagemetrics>"
    if transitions:
        rows = []
        for index, target in transitions.items():
            rows.append(f'<transition index="{index}" transition_m_target_state="{guid(key, "state", target)}" transition_m_interpolation_property_mask="64"/>')
        body += "<transitionmap>" + "".join(rows) + "</transitionmap>"
    return f"<{name} {attrs}>{body}</{name}>"


def layout(key, kind, images, states, default, sound=None, callbacks=""):
    """A layout with one component. kind is the component's element name, images: {name: path}."""
    root = guid(key, "root")
    root_state = guid(key, "root_state")
    root_image = guid(key, "root_image")
    root_metric = guid(key, "root_metric")
    comp = guid(key, "comp")
    image_rows = "".join(f'<component_image this="{guid(key, "image", n)}" uniqueguid="{guid(key, "image", n)}" imagepath="{p}"/>' for n, p in images.items())
    return f'''<?xml version="1.0"?>
<layout version="142" comment="" precache_condition="">
<hierarchy><root this="{root}"><{kind} this="{comp}"/></root></hierarchy>
<components>
<root this="{root}" id="root" tooltipslocalised="true" uniqueguid="{root}" currentstate="{root_state}" defaultstate="{root_state}">
<componentimages><component_image this="{root_image}" uniqueguid="{root_image}"/></componentimages>
<states><newstate this="{root_state}" name="NewState" width="1600" height="900" texthbehaviour="Never split" interactive="true" uniqueguid="{root_state}">
<imagemetrics><image this="{root_metric}" uniqueguid="{root_metric}" componentimage="{root_image}" width="1600" height="900" colour="#F0F0F0FF"/></imagemetrics></newstate></states>
</root>
<{kind} this="{comp}" id="{kind}" offset="0.00,0.00" allowhorizontalresize="true" allowverticalresize="true" priority="42" tooltipslocalised="false" uniqueguid="{comp}"{f' soundcategory="{sound}"' if sound else ""} currentstate="{guid(key, "state", default)}" defaultstate="{guid(key, "state", default)}">
{callbacks}<componentimages>{image_rows}</componentimages>
<states>{"".join(states)}</states>
</{kind}>
</components>
</layout>
'''


def image_layout(key, path="ui/skins/default/bullet_point.png", interactive=False, shader=None):
    img = guid(key, "image", "main")
    return layout(key, "image", {"main": path}, [state_xml("regular", key, 64, 64, [(img, None, False)], interactive=interactive, shader=shader)], "regular")


def zone_layout(key):
    """An invisible part of the drawing that takes clicks."""
    return layout(key, "zone", {}, [state_xml("regular", key, 64, 64, [])], "regular")


def frame_layout(key, border, tile):
    """A panel of the game's own skin: a tiled back in a frame, as ui/templates/panel_frame."""
    b, t = guid(key, "image", "border"), guid(key, "image", "tile")
    return layout(key, "frame", {"border": border, "tile": tile}, [state_xml("regular", key, 418, 530, [(t, "5.00,5.00,5.00,5.00", True), (b, "30.00,30.00,30.00,30.00", True)])], "regular")


def edge_layout(key, border):
    """Only a frame, over a picture. Takes no mouse."""
    b = guid(key, "image", "border")
    return layout(key, "frame", {"border": border}, [state_xml("regular", key, 418, 530, [(b, "30.00,30.00,30.00,30.00", True)], interactive=False)], "regular")


def backdrop_layout(key):
    img = guid(key, "image", "main")
    # A full screen dim that takes the mouse: nothing of the map or the HUD can be pressed while the panel is open.
    # One black picture stretched: the game's tiles have soft edges and show seams through the map.
    return layout(key, "backdrop", {"main": f"{UI_DIR}backdrop.png"}, [state_xml("regular", key, 1600, 900, [(img, None, False)])], "regular")


def text_layout(key, cat, size, colour, align=None, wrap=None, leading=1, valign="Center"):
    """wrap None: lines break at words, as most texts of the game; "Never split": one line."""
    return layout(key, "text", {}, [state_xml("active", key, 240, 20, [], interactive=False, text={"cat": cat, "size": size, "colour": colour, "align": align, "wrap": wrap, "leading": leading, "valign": valign})], "active")


def button_layout(key, base, margin="24.00,24.00,24.00,24.00"):
    """A plate that is a button. active, hover, down and down_off as the game's parchment_row; selected: chosen; inactive: locked, shows its tooltip, gives no click."""
    img = {n: guid(key, "image", n) for n in ("normal", "hover", "selected", "locked")}
    paths = {n: f"{UI_DIR}{base}_{n}.png" for n in img}
    w, h = (214, 70) if base == "plate" else (400, 86)
    s = lambda name, image, trans, **kw: state_xml(name, key, w, h, [(img[image], margin, False)], trans, **kw)
    states = [
        s("active", "normal", {0: "hover"}),
        s("hover", "hover", {1: "active", 2: "down"}),
        s("down", "selected", {1: "down_off", 3: "hover"}),
        s("down_off", "hover", {0: "down", 8: "active"}),
        s("selected", "selected", {0: "selected_hover"}),
        s("selected_hover", "selected", {1: "selected"}),
        s("inactive", "locked", {}, disabled=True),
        s("invalid", "hover", {1: "invalid"}),     # ordered for the next turn. A state that nothing moves away from by itself
    ]
    return layout(key, "button", paths, states, "active", sound="UI_GBL_TMP_Parchment_Row")


def files():
    """{pack path: bytes} of the layouts and the pictures."""
    def path(name, ext):
        return f"ui{SEP}tww3_mtb{SEP}{name}{ext}"
    out = {path(f.stem, ".png"): f.read_bytes() for f in sorted(ART.glob("*.png"))}
    if CARDS.exists():
        out |= {f"ui{SEP}tww3_mtb{SEP}crew_cards{SEP}{f.name}": f.read_bytes() for f in sorted(CARDS.glob("*.png"))}
    layouts = {
        "image": image_layout("image"),
        "zone": zone_layout("zone"),
        "frame": frame_layout("frame", "ui/skins/default/panel_back_border.png", "ui/skins/default/panel_back_tile.png"),
        "frame_dark": frame_layout("frame_dark", "ui/skins/default/panel_back_inner_frame.png", "ui/skins/default/panel_back_tile_stone.png"),
        "frame_edge": edge_layout("frame_edge", "ui/skins/default/panel_back_frame.png"),
        "backdrop": backdrop_layout("backdrop"),
        "text_title": text_layout("text_title", "header_24_bold", 24, TEXT_LIGHT, "Center", "Never split"),
        "text_head": text_layout("text_head", "header_18_bold", 18, TEXT_COPPER, None, "Never split"),
        "text_name": text_layout("text_name", "header_14", 14, TEXT_LIGHT, None, "Never split"),
        "text_name_grey": text_layout("text_name_grey", "header_14", 14, TEXT_GREY, None, "Never split"),
        "text_body": text_layout("text_body", "body_12", 12, TEXT_LIGHT, leading=2, valign="Top"),
        "text_line": text_layout("text_line", "body_12", 12, TEXT_LIGHT, None, "Never split"),
        "text_line_grey": text_layout("text_line_grey", "body_12", 12, TEXT_GREY, None, "Never split"),
        "text_copper": text_layout("text_copper", "body_12", 12, TEXT_COPPER, None, "Never split"),
        "text_note": text_layout("text_note", "body_12", 12, TEXT_GREY, leading=2, valign="Top"),
        "button_plate": button_layout("button_plate", "plate"),
        "button_row": button_layout("button_row", "row"),
    }
    for name, text in layouts.items():
        out[path(name, ".twui.xml")] = text.encode("utf-8")
    return out


def group_numbers(t, group_key, option_key, opt, group):
    """What the panel prints for one option, from the rows of the build."""
    if opt.get("empty") or opt.get("cover") or opt.get("cover_by_side") or opt.get("ability"):
        return {}
    personalities = {r["key"]: r for r in t["battle_personalities"]}
    stats_rows = {r["key"]: r for r in t["battle_entity_stats"]}
    weapons = {r["key"]: r for r in t["missile_weapons"]}
    row = personalities.get(f"mtb_bp_{option_key}_{group['seats'][0].removeprefix('ap_')}")
    if not row or not row.get("battle_entity_stats"):
        return {}
    stats = stats_rows.get(row["battle_entity_stats"]) or next((r for r in t["_stock"]["battle_entity_stats"] if r["key"] == row["battle_entity_stats"]), None)
    if not stats or not stats.get("primary_missile_weapon"):
        return {}
    weapon = weapons.get(stats["primary_missile_weapon"]) or next(r for r in t["_stock"]["missile_weapons"] if r["key"] == stats["primary_missile_weapon"])
    own = {r["key"]: r for r in t["projectiles"]}
    p = own.get(weapon["default_projectile"]) or next(r for r in t["_stock"]["projectiles"] if r["key"] == weapon["default_projectile"])
    out = {"damage": round(p["damage"]), "ap": round(p["ap_damage"]), "reload": round(p["base_reload_time"], 1), "range": round(p["effective_range"]),
           "shots": p["projectile_number"], "volley": p["shots_per_volley"], "burst": p["burst_size"], "ammo": opt.get("ammo")}
    explosion = p.get("explosion_type")
    if explosion:
        e = next((r for r in t["_stock"]["projectiles_explosions"] if r["key"] == explosion), None)
        if e:
            out.update(blast=round(e["detonation_damage"]), blast_ap=round(e["detonation_damage_ap"]), radius=round(e["detonation_radius"], 1))
    return out


def upkeep(opt, stock):
    """Gold per turn of an option: upkeep_cost x count / guns or men of the source unit, or the number by hand."""
    if "upkeep" in opt:
        return opt["upkeep"]
    source = opt.get("upkeep_from")
    if not source:
        return 0
    unit = next(r for r in stock["main_units"] if r["unit"] == source["unit"])
    land = next(r for r in stock["land_units"] if r["key"] == unit["land_unit"])
    size = land["num_engines"] or unit["num_men"]
    return round(unit["upkeep_cost"] * source["count"] / size)


def hire(opt, stock):
    """Gold to hire an option: recruitment_cost of the same source unit as the upkeep x count / its guns or men, or the number by hand. An empty option is free."""
    if "hire" in opt:
        return opt["hire"]
    source = opt.get("upkeep_from")
    if not source:
        return 0
    unit = next(r for r in stock["main_units"] if r["unit"] == source["unit"])
    land = next(r for r in stock["land_units"] if r["key"] == unit["land_unit"])
    size = land["num_engines"] or unit["num_men"]
    return round(unit["recruitment_cost"] * source["count"] / size)


def game_text(prefix):
    """{key: text} of the game's Russian texts whose keys start with prefix. A .loc: FF FE 'LOC' 00, i32, u32 count, then key, text as u16 length + UTF-16, a bool."""
    out = {}
    for _, blob in gamepack.entries(gamepack.DATA / "local_ru.pack", lambda n: n.endswith(".loc")):
        count = struct.unpack_from("<I", blob, 10)[0]
        pos = 14
        for _ in range(count):
            n = struct.unpack_from("<H", blob, pos)[0]
            key = blob[pos + 2:pos + 2 + n * 2].decode("utf-16-le", "replace")
            pos += 2 + n * 2
            n = struct.unpack_from("<H", blob, pos)[0]
            if key.startswith(prefix):
                out[key] = blob[pos + 2:pos + 2 + n * 2].decode("utf-16-le", "replace")
            pos += 2 + n * 2 + 1
    return out


def building_lines(config, t, stock, bindings):
    """The green lines of a building, in its list of effects: what it gives the barge. Written from data/crew_options.json, so the table changes in one place.
    A row of effects with no bonus: only its text does anything. One effect per line. Adds to the tables t, returns {loc key: text}."""
    prefix = config["buildings_prefix"]
    names = game_text("building_culture_variants_name_")
    renamed = {prefix + short: name for short, name in config.get("building_names", {}).items()}
    for chain in config.get("new_chains", []):
        renamed |= {prefix + level["key"]: level["name"] for level in chain["levels"]}

    def name_of(key):
        return renamed.get(key) or names.get(f"building_culture_variants_name_{key}", key)
    groups = config["groups"]
    mount_building = {b["group"]: k for k, pairs in bindings.items() for b in pairs if groups[b["group"]].get("mount") == b["option"]}
    like = next(r for r in stock["effects"] if r["effect"] == "wh3_dlc25_effect_ability_enable_thunderburner_upgraded")
    t.setdefault("effects", [])
    t.setdefault("building_effects_junction", [])
    loc = {}
    lines = {}
    for key, pairs in bindings.items():
        short = key.removeprefix(prefix)
        if short in config.get("no_auto_line", []):
            continue
        for binding in pairs:
            group, option = groups[binding["group"]], binding["option"]
            opt = group["options"][option]
            label = group["ui"]["name"].lower()
            name = opt["ui"]["name"]
            if group.get("mount") == option:
                text = f"Крепление: {group['mount_name']}, {len(group['seats'])} места, пока без оружия. Оружие открывают другие постройки, ставится в панели экипажа"
            elif group.get("mount"):
                need = f"Нужны {group['mount_name']} (постройка «{name_of(mount_building[binding['group']])}»)"
                if group.get("requires"):
                    need += f" и {group['requires']['name']} (постройка «{name_of(prefix + group['requires']['building'])}»)"
                text = f"Открывает в экипаже: {name} ({label}). {need}. Ставится в панели экипажа"
            elif opt.get("ability"):
                text = f"Открывает в экипаже: {name}, стрела на носу шара и способность в бою. Ставится в панели экипажа"
            elif short in config["auto_active"]:
                text = f"Экипаж: {name} ({label}) встают сразу"
            else:
                text = f"Открывает в экипаже: {name} ({label}). Ставится в панели экипажа"
            lines.setdefault(short, []).append(text)
    for short, more in config.get("building_lines", {}).items():
        lines.setdefault(short, []).extend(more)
    for short, texts in lines.items():
        for number, text in enumerate(texts):
            effect = f"mtb_effect_crew_{short}" + (f"_{number}" if number else "")
            t["effects"].append(dict(like, effect=effect, is_positive_value_good=True))
            t["building_effects_junction"].append({"building": prefix + short, "effect": effect, "effect_scope": BUILDING_LINE_SCOPE, "value": 1.0, "value_damaged": 1.0, "value_ruined": 0.0, "context_requirement": ""})
            loc[f"effects_description_{effect}"] = text
    for key, name in renamed.items():
        loc[f"building_culture_variants_name_{key}"] = name
    return loc


def own_card_name(config, group_key, key):
    """The name in data/ui/crew_cards of an option's own drawn card, or None. <group>_<option> first, then <option>: stock, say, is an option of several groups, so a bare name is taken only for a name no other group has."""
    if (CARDS / f"{group_key}_{key}_small.png").exists() or (CARDS / f"{group_key}_{key}.png").exists():
        return f"{group_key}_{key}"
    unique = sum(key in g["options"] for g in config["groups"].values()) == 1
    if unique and ((CARDS / f"{key}_small.png").exists() or (CARDS / f"{key}.png").exists()):
        return key
    return None


def drawn_path(name, small=False):
    """The pack's path of a drawn card, the small one on the tree when there is one."""
    if small and (CARDS / f"{name}_small.png").exists():
        return f"{UI_DIR}crew_cards/{name}_small.png"
    if (CARDS / f"{name}.png").exists():
        return f"{UI_DIR}crew_cards/{name}.png"
    return f"{UI_DIR}crew_cards/{name}_small.png"


def card_path(ui):
    """The picture of an option's card, as the panel shows it."""
    if ui.get("own_card"):
        return f"{UI_DIR}{ui['own_card']}.png"
    if ui.get("card"):
        return f"ui/units/icons/{ui['card']}.png"
    return None


def data(config, t, stock, bindings):
    """The Lua data of the panel."""
    t = dict(t, _stock=stock)
    art = json.loads((REPO / "data" / "crew_ui_art.json").read_text(encoding="utf-8"))
    unlocked_by = {(b["group"], b["option"]): key for key, pairs in bindings.items() for b in pairs}
    groups = {}
    for group_key, group in config["groups"].items():
        rows = []
        for key, opt in group["options"].items():
            ui = opt.get("ui") or {}
            if ui.get("hidden") or ui.get("none"):
                continue
            drawn = own_card_name(config, group_key, key)
            if drawn:
                ui = dict(ui, own_card="crew_cards/" + (drawn if (CARDS / f"{drawn}.png").exists() else drawn + "_small"))
            rows.append(dict(ui, key=key, numbers=group_numbers(t, group_key, key, opt, group), building=unlocked_by.get((group_key, key), ""), upkeep=upkeep(opt, stock), hire=hire(opt, stock)))
        # empty first, then in the order of the buildings table
        order = list(bindings)
        rows.sort(key=lambda r: -1 if r["key"] == "empty" else order.index(r["building"]) if r["building"] in order else 99)
        groups[group_key] = dict(group["ui"], rows=rows, seats=len(group["seats"]))
        if group.get("boost") and group["boost"]["steps"][0].get("effective_range"):
            groups[group_key]["range_steps"] = [step["effective_range"] for step in group["boost"]["steps"]]
        if group.get("requires"):
            groups[group_key]["requires_name"] = group["requires"]["name"]
            groups[group_key]["requires_building"] = config["buildings_prefix"] + group["requires"]["building"]
        none = group["options"].get("none")
        if none:
            groups[group_key]["none_name"] = none["ui"]["name"]
            groups[group_key]["mount_name"] = group["mount_name"]
            groups[group_key]["mount_building"] = unlocked_by[(group_key, group["mount"])]
    order = [g for g in ("cupolas", "harpoon", "cannons", "rifles", "bombs", "deck", "pub") if not config["groups"][g].get("always") and not config["groups"][g].get("no_panel")]
    # the crew cards on the buildings of the game's tree
    cards = {}
    for key, pairs in bindings.items():
        if key.removeprefix(config["buildings_prefix"]) in config.get("no_card", []):     # the hull's own row of the tree: the tile stands beside the others' columns
            continue
        for b in pairs:
            group = config["groups"][b["group"]]
            if group.get("no_panel") or group.get("mount") == b["option"]:
                continue
            option = group["options"][b["option"]]
            drawn = own_card_name(config, b["group"], b["option"])
            path = drawn_path(drawn, small=True) if drawn else card_path(option.get("ui") or {})
            if path:
                frame = group["card_frame"]
                cards.setdefault(key, []).append({"card": path, "frame": f"{UI_DIR}card_frame_{frame}.png"})
    return {"groups": groups, "art": art, "order": order, "drawn": ["cupolas", "harpoon", "cannons", "rifles", "bombs", "deck", "pub"], "building_cards": cards}
