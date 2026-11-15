"""Which model a seat row really shows: battle_personalities row -> variants row -> .variantmeshdefinition -> the meshes it names.

A seat's row NAME says nothing about the man on it (run 20261115-065150-crew_hire: mtb_bp_malakai_rail_right showed a slayer pirate, the helm's
"crew" row a daemon slayer). The checks of Malakai at the rail (tools/check_mod.py, tools/crew_bridge_offline.py, tools/hire_offline.py) resolve
the row down to its meshes with this module and ask: is his own body there (dwf_malakai_01), is the wheel in his hands, a rifle on be_prop_3.

Definitions are read from the mod's pack first, then from the game (game: a function path -> bytes or None; tools/hull_parts.game_file under
py -3.14). Under py -3.10 the game's packs cannot be read (tools/gamepack.py needs compression.zstd): a stock definition is then "unknown",
and every check here asks for a fact to be PROVEN, so an unknown model never passes as Malakai or as the helm's crew.
"""
import re
import xml.etree.ElementTree as ET

SEP = chr(92)
MALAKAI_BODY = "variantmeshes/wh_variantmodels/hu3/dwf/dwf_malakai/dwf_malakai_01.wsmodel"
WHEEL = "props/dwf_thunderbarge_steering_wheel"
RIFLE_PROP = "be_prop_3"


def definition_path(filename):
    return f"variantmeshes{SEP}variantmeshdefinitions{SEP}{filename}.variantmeshdefinition"


class Resolver:
    def __init__(self, files, game=None):
        """files: {pack path: bytes} of the mod's pack; game: path -> bytes (raises SystemExit or returns None when missing), or None."""
        self.files = {k.lower(): v for k, v in files.items()}
        self.game = game
        self.cache = {}

    def text(self, path):
        """(text, 'pack' | 'game') or (None, None)."""
        key = path.replace("/", SEP).lower()
        if key in self.files:
            return self.files[key].decode("utf-8", "replace"), "pack"
        if self.game:
            try:
                blob = self.game(path.replace(SEP, "/"))
            except SystemExit:
                blob = None
            if blob is not None:
                return blob.decode("utf-8", "replace"), "game"
        return None, None

    def slots(self, text, depth=0):
        """[(slot name, attach point or None, [mesh paths, lower, forward slashes])], references followed. None: a reference that cannot be read."""
        root = ET.fromstring(text.lstrip("﻿").strip())
        out = []
        for slot in root.iter("SLOT"):
            meshes = []
            for el in slot:
                if el.tag == "VARIANT_MESH" and el.get("model"):
                    meshes.append(el.get("model").replace(SEP, "/").lower())
                elif el.tag == "VARIANT_MESH_REFERENCE" and depth < 4:
                    inner, _ = self.text(el.get("definition"))
                    if inner is None:
                        return None
                    sub = self.slots(inner, depth + 1)
                    if sub is None:
                        return None
                    meshes += [m for _, _, ms in sub for m in ms]
            out.append((slot.get("name"), slot.get("attach_point"), meshes))
        return out

    def model(self, variant_row):
        """What a variants row shows: {variant, file, source, figure: [meshes], props: {attach point: [meshes]}, known, malakai, wheel, rifle}."""
        name = variant_row["variant_name"]
        if name in self.cache:
            return self.cache[name]
        text, source = self.text(definition_path(variant_row["variant_filename"]))
        slots = self.slots(text) if text is not None else None
        out = {"variant": name, "file": variant_row["variant_filename"], "source": source, "known": slots is not None, "figure": [], "props": {}}
        for _, attach, meshes in slots or []:
            if attach is None:
                out["figure"] += meshes
            elif attach.startswith("be_prop_") and meshes:
                out["props"].setdefault(attach, []).extend(meshes)
        out["malakai"] = MALAKAI_BODY in out["figure"]
        out["wheel"] = any(WHEEL in m for ms in out["props"].values() for m in ms)
        out["rifle"] = bool(out["props"].get(RIFLE_PROP))
        self.cache[name] = out
        return out


def seat_models(files, tables, stock=None, game=None, keys=None):
    """{battle_personalities key: model (Resolver.model) | None (no row or no variants row)} over the pack's tables and, if given, the game's.
    keys: only these rows."""
    def merged(table, key):
        out = {r[key]: r for r in (stock or {}).get(table, [])}
        out |= {r[key]: r for r in tables.get(table, [])}
        return out
    pers, variants = merged("battle_personalities", "key"), merged("variants", "variant_name")
    resolver = Resolver(files, game)
    out = {}
    for key in (keys if keys is not None else pers):
        row = pers.get(key)
        variant = row and variants.get(row.get("variant"))
        out[key] = resolver.model(variant) if variant else None
    return out


def pack_tables(files, layouts, names=("battle_personalities", "variants")):
    """The mod's own rows of these tables, read from the pack's files (tools/dbtable.py; works under py -3.10)."""
    import dbtable
    out = {}
    for path, blob in files.items():
        parts = path.split(SEP)
        if len(parts) == 3 and parts[0] == "db" and parts[1].removesuffix("_tables") in names:
            table = parts[1].removesuffix("_tables")
            out[table] = dbtable.decode(blob, [tuple(f) for f in layouts[table]["fields"]])
    return out


def swap_malakai_variants(tables, rail_rows, helm_row):
    """A deliberate break for the checks: the rail rows get the helm crew's variant and the helm crew row the rail's, every row name as before."""
    pers = {r["key"]: r for r in tables["battle_personalities"]}
    rails = [pers[k] for k in rail_rows]
    rail_variant, helm_variant = rails[0]["variant"], pers[helm_row]["variant"]
    for r in rails:
        r["variant"] = helm_variant
    pers[helm_row]["variant"] = rail_variant
    print(f"BROKEN on purpose: {rail_rows} -> {helm_variant}, {helm_row} -> {rail_variant}")


def malakai_problems(models, mk):
    """The facts of Malakai at the rail (crew module data mk: seats, rows, helm_crew, helm_own, rail_variant, helm_variant): one line per failure.
    His rail rows: his own body, no wheel, a rifle in the hands (be_prop_3), the variant the config names. The helm's crew: a figure without his body,
    the wheel. His own helm row (switch off): his body and the wheel."""
    out = []

    def of(key):
        m = models.get(key)
        if not m or not m["known"]:
            out.append(f"{key}: its model cannot be resolved ({m and m['variant']})")
            return None
        return m
    for side, key in mk["rows"].items():
        m = of(key)
        if m and (not m["malakai"] or m["wheel"] or not m["rifle"] or (mk.get("rail_variant") and m["variant"] != mk["rail_variant"])):
            out.append(f"{key} ({side} rail): variant {m['variant']} figure {short(m['figure'])} props {short(m['props'])}: not Malakai's own body with his rifle")
    m = of(mk["helm_crew"])
    if m and (m["malakai"] or not m["wheel"] or not m["figure"] or (mk.get("helm_variant") and m["variant"] != mk["helm_variant"])):
        out.append(f"{mk['helm_crew']} (helm, crew): variant {m['variant']} figure {short(m['figure'])}: not a crew dwarf at the wheel")
    if mk.get("helm_own"):
        m = of(mk["helm_own"])
        if m and (not m["malakai"] or not m["wheel"]):
            out.append(f"{mk['helm_own']} (helm, Malakai's own): variant {m['variant']} figure {short(m['figure'])}: not Malakai at the wheel")
    return out


def short(x):
    """Mesh paths shown by their file names."""
    if isinstance(x, dict):
        return {k: short(v) for k, v in x.items()}
    return [re.sub(r".*/", "", m) for m in x]
