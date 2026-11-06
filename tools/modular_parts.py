"""Offline prototype of the barge's details by addition (docs/design/modular-parts.md). Not part of the build:
  py -3.14 tools/modular_parts.py
writes build/modular/ only: the rows, definitions, seat models and the Lua config the scheme would add, and report.json with the counts.

The scheme: a detail whose every vertex hangs on one bone that an attachment point of the hull also hangs on (hull_0, balloon_0) is a
seat of its own: one more row of land_units_to_battle_personalities_junctions on that point (two seats on one point: the Sisters of
Twilight in the game), with two rows of battle_personalities, on and off. src/tww3_mtb_crew.lua would write on or off into it as it writes
the crew. A detail on a moving bone (the stern rudders on rudder_left_0 / rudder_right_0) stays a slot of the hull's definition, and only
those details, with the harpoon, are multiplied into mount rows.

The attachment points and their frames come from the hull's tech skeleton (variants.tech_folder of the mount: the stock .anim there). A hull
vertex p goes into the seat's frame as R^T (F p - t), F = diag(-1, 1, -1): the formula gives exactly the pub's hand-measured origin on
ap_crew_barrel (data/hull_parts.json). The seat's variant row has the hull's scale (1.2), as the stock seat variants do; the model is unscaled.
"""
import json
import math
import re
import struct
import sys
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import dbtable  # noqa: E402
import gamepack  # noqa: E402
import rmv2  # noqa: E402

OUT = REPO / "build" / "modular"
SEP = chr(92)
UNIT = "mtb_dwf_cha_malakai_thunderbarge"
BARGE = "wh3_dlc25_dwf_veh_thunderbarge_grungni"
HULL_VARIANT = "wh3_dlc25_dwf_mnt_veh_thunderbarge_grungni"
HULL_MOUNT = "wh3_dlc25_dwf_mnt_veh_thunderbarge_grungni"
HULL_TABLE = "zeppelin01_dlc25_thunderbarge_grungni"
NO_HARPOON_TABLE = HULL_TABLE.replace("zeppelin01", "zepnoharp1")
OWN_HULL_WS = "warmachines/aircraft/dwf_thunderbarge/tww3_mtb_hull.wsmodel"
# The tech skeleton the game uses for our hull: dwf_thunderbarge.anim, not _01. The men of runs/20261106-184308-modular_test and
# 20261104-175714-cycle_fb_shot stand on its points within 0.05 m (mean, positions printed to 0.1 m); on _01 0.3 m, up to 0.97 m.
# With _01 the porthole on ap_crew_left_upper_0 (30 deg there, 90 deg here) went into the hull and onto the bow (docs/design/modular-parts.md).
TECH = "warmachines/aircraft/dwf_thunderbarge/thunderbarge_tech/dwf_thunderbarge.anim"
HIDDEN = "wh3_dlc23_chd_veh_hidden_rider"
AVOID = {"ap_thunderburner"}          # a weapon seat: a patch on it once took the ability's place (docs/design/progression-proposal.md)
F = (-1.0, 1.0, -1.0)

# One line per detail. part: the folder of its cut model (build/solid_hull_*/<x>_part); default: what the tables hold, so the AI's barge
# and a barge without memreader Plus (the stock look: on).
PARTS = [
    {"name": "porthole", "part": "build/solid_hull_porthole/porthole_part", "default": "on"},
    {"name": "forsage_tank", "part": "build/solid_hull_tank/tank_part", "default": "on"},
    {"name": "stern_armour", "part": "build/solid_hull_stern/stern_armour_part", "default": "on"},
    {"name": "bomb_hatches", "part": "build/solid_hull_hatches/hatches_part", "default": "on"},
    {"name": "side_shields", "part": None, "default": "on"},        # cut by boxes, tools/hull_parts.py: no model yet
    {"name": "balloon_shields", "part": None, "default": "on"},
]


# --- the game's data -----------------------------------------------------------------------------------------------------------

def game_file(path):
    target = path.replace("/", SEP).lower()
    found = None
    for pack in sorted(gamepack.DATA.glob("*.pack")):
        if pack.name.startswith(("anim", "warmachines", "data")) and "_dds" not in pack.name:
            for _, blob in gamepack.entries(pack, lambda n: n.lower() == target):
                found = blob
    if found is None:
        raise SystemExit(f"{path} is not in the game's packs")
    return found


def tables(names):
    layouts = json.loads((REPO / "data" / "db_layouts.json").read_text(encoding="utf-8"))
    out = {}
    for name, blob in gamepack.entries(gamepack.DATA / "db.pack", lambda n: n.count(SEP) == 2 and n.split(SEP)[1].removesuffix("_tables") in names):
        table = name.split(SEP)[1].removesuffix("_tables")
        if dbtable.header(blob)[1] != layouts[table]["version"]:
            raise SystemExit(f"{table}: the game was patched, refresh data/db_layouts.json")
        out.setdefault(table, []).extend(dbtable.decode(blob, [tuple(f) for f in layouts[table]["fields"]]))
    return out


def one(rows, **kw):
    found = [r for r in rows if all(r[k] == v for k, v in kw.items())]
    if len(found) != 1:
        raise SystemExit(f"expected one row for {kw}, found {len(found)}")
    return dict(found[0])


# --- the tech skeleton: names, parents, rest frames (pure Python port of tools/card_anim.py, frame 0) -----------------------------

def qmat(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]


def tech_frames(blob):
    """{bone: (parent name, R 3x3, t)} in the model's space."""
    b = blob
    if struct.unpack_from("<I", b, 0)[0] != 8:
        raise SystemExit("tech .anim: not version 8")
    p = 12
    n = struct.unpack_from("<H", b, p)[0]
    p += 2 + n + 8
    count = struct.unpack_from("<I", b, p)[0]
    p += 4
    names, parents = [], []
    for _ in range(count):
        n = struct.unpack_from("<H", b, p)[0]
        names.append(b[p + 2:p + 2 + n].decode())
        parents.append(struct.unpack_from("<i", b, p + 2 + n)[0])
        p += 2 + n + 4
    p += 8
    tk, rk = list(struct.unpack_from(f"<{count}b", b, p)), list(struct.unpack_from(f"<{count}b", b, p + count))
    p += 2 * count
    nt, nr = struct.unpack_from("<II", b, p)
    p += 8
    trange = [struct.unpack_from("<6f", b, p + i * 24) for i in range(nt)]
    p += nt * 24
    rrange = [struct.unpack_from("<8f", b, p + i * 32) for i in range(nr)]
    p += nr * 32 + 8

    def t_of(size, i, at):
        if size == 12:
            return list(struct.unpack_from("<3f", b, at))
        raw = struct.unpack_from("<3B", b, at)
        return [trange[i][3 + k] + raw[k] / 255 * trange[i][k] for k in range(3)]

    def r_of(size, i, at):
        if size == 8:
            q = [v / 32767 for v in struct.unpack_from("<4h", b, at)]
        else:
            raw = struct.unpack_from("<4B", b, at)
            q = [rrange[i][4 + k] + raw[k] / 255 * rrange[i][k] for k in range(4)]
        norm = math.sqrt(sum(v * v for v in q)) or 1.0
        return [v / norm for v in q]
    st, sr = {}, {}
    for i, k in enumerate(tk):
        if k < 0:
            st[i] = t_of(-k, i, p)
            p += -k
    for i, k in enumerate(rk):
        if k < 0:
            sr[i] = r_of(-k, i, p)
            p += -k
    p += 12
    loc_t, loc_r = {}, {}
    for i, k in enumerate(tk):
        if k > 0:
            loc_t[i] = t_of(k, i, p)
            p += k
        else:
            loc_t[i] = st.get(i, [0.0, 0.0, 0.0])
    for i, k in enumerate(rk):
        if k > 0:
            loc_r[i] = r_of(k, i, p)
            p += k
        else:
            loc_r[i] = sr.get(i, [0.0, 0.0, 0.0, 1.0])
    world = []
    for i, parent in enumerate(parents):
        r, t = qmat(loc_r[i]), loc_t[i]
        if parent >= 0:
            pr, pt = world[parent]
            r = [[sum(pr[a][k] * r[k][c] for k in range(3)) for c in range(3)] for a in range(3)]
            t = [pt[a] + sum(pr[a][k] * t[k] for k in range(3)) for a in range(3)]
        world.append((r, t))
    return {names[i]: (names[parents[i]] if parents[i] >= 0 else None, world[i][0], world[i][1]) for i in range(count)}, names


def to_seat(frame, x, y, z):
    _, r, t = frame
    q = (F[0] * x - t[0], F[1] * y - t[1], F[2] * z - t[2])
    return tuple(sum(r[k][a] * q[k] for k in range(3)) for a in range(3))


# --- the details ------------------------------------------------------------------------------------------------------------------

def part_model(folder):
    files = sorted((REPO / folder).rglob("*.rigid_model_v2")) if folder and (REPO / folder).exists() else []
    if not files:
        return None, None
    path = files[0]
    pack_path = path.relative_to(REPO / folder).with_suffix("").as_posix()
    return rmv2.load(path.read_bytes()), pack_path


def bones_of(model):
    return sorted({v.bone0 for meshes in model["lods"] for m in meshes for v in m.verts}
                  | {v.bone1 for meshes in model["lods"] for m in meshes for v in m.verts if v.weight1})


def centre(model):
    vs = [v for m in model["lods"][0] for v in m.verts]
    return tuple(sum(getattr(v, a) for v in vs) / len(vs) for a in "xyz")


def materials(folder, pack_path):
    ws = (REPO / folder / (pack_path + ".wsmodel")).read_text(encoding="utf-8")
    out = {}
    for m in re.finditer(r'<material part_index="(\d+)" lod_index="(\d+)">([^<]+)</material>', ws):
        out.setdefault(int(m.group(2)), {})[int(m.group(1))] = m.group(3)
    return {lod: [parts[i] for i in sorted(parts)] for lod, parts in out.items()}


def seat_model(model, frame):
    """The detail in the seat's frame, rigid on the root of default_skeleton, as the covers of empty seats (tools/gun_models.py, static)."""
    new = {"version": model["version"], "skeleton": "default_skeleton", "lods": [], "lod_headers": list(model["lod_headers"])}
    for meshes in model["lods"]:
        lod = []
        for mesh in meshes:
            m = mesh.copy()
            for v in m.verts:
                v.x, v.y, v.z = to_seat(frame, v.x, v.y, v.z)
                v.rebind(0)
            m.attachments = [("animRoot", 0, rmv2.IDENTITY)]
            lod.append(m)
        new["lods"].append(lod)
    return new


def vmd(models):
    slots = "".join(f'\t<SLOT name="{name}" >\n\t\t<VARIANT_MESH model="{model}" />\n\t</SLOT>\n' for name, model in models)
    return f"<VARIANT_MESH>\n{slots}</VARIANT_MESH>\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    stock = tables({"variants", "mounts", "battle_personalities", "land_units_to_battle_personalities_junctions"})
    frames, bone_names = tech_frames(game_file(TECH))
    aps = {n: f for n, f in frames.items() if n.startswith("ap_") and n not in AVOID}
    hull_var = one(stock["variants"], variant_name=HULL_VARIANT)
    hidden = one(stock["battle_personalities"], key=HIDDEN)
    dummy = one(stock["variants"], variant_name="dummy_variant")
    seat_rows = {r["riders_attachment_point"]: r for r in stock["land_units_to_battle_personalities_junctions"] if r["land_unit"] == BARGE}
    t = {"land_units_to_battle_personalities_junctions": [], "battle_personalities": [], "variants": [], "mounts": []}
    files, report, lua_parts, hull_details, errors = {}, {"details": {}}, {}, [], []
    for spec in PARTS:
        name = spec["name"]
        model, pack_path = part_model(spec["part"])
        if model is None:
            report["details"][name] = {"kind": "waiting", "why": "no cut model yet"}
            continue
        if model["skeleton"] != "zeppelin01":
            errors.append(f"{name}: skeleton {model['skeleton']}")
            continue
        bones = [bone_names[i] for i in bones_of(model)]
        cx, cy, cz = centre(model)
        fitting = {n: f for n, f in aps.items() if len(bones) == 1 and f[0] == bones[0]}
        if not fitting:
            # On a moving bone, or on several: a slot of the hull's definition, keeping the hull's skeleton and weights.
            hull_details.append((name, pack_path + ".wsmodel"))
            files[f"models/{pack_path}.rigid_model_v2"] = (REPO / spec["part"] / (pack_path + ".rigid_model_v2")).read_bytes()
            files[f"models/{pack_path}.wsmodel"] = (REPO / spec["part"] / (pack_path + ".wsmodel")).read_bytes()
            report["details"][name] = {"kind": "hull slot", "bones": bones, "why": "no attachment point hangs on " + "+".join(bones)}
            continue

        def distance(item):
            _, _, tt = item[1]
            return math.dist((F[0] * cx, cy, F[2] * cz), tt)
        ap, frame = min(fitting.items(), key=distance)
        out_path = f"warmachines/aircraft/dwf_thunderbarge/tww3_mtb_part_{name}"
        seat = seat_model(model, frame)
        back = rmv2.load(rmv2.save(seat))
        if back["skeleton"] != "default_skeleton" or bones_of(back) != [0] or len(back["lods"]) != len(model["lods"]):
            errors.append(f"{name}: read back of the seat model")
        files[f"models/{out_path}.rigid_model_v2"] = rmv2.save(seat)
        files[f"models/{out_path}.wsmodel"] = rmv2.wsmodel(out_path + ".rigid_model_v2", materials(spec["part"], pack_path))
        variant = f"mtb_v_part_{name}"
        files[f"variantmeshdefinitions/{variant}.variantmeshdefinition"] = vmd([("part", out_path + ".wsmodel")]).encode()
        t["variants"].append(dict(dummy, variant_name=variant, variant_filename=variant, scale=hull_var["scale"]))
        on, off = f"mtb_bp_part_{name}_on", f"mtb_bp_part_{name}_off"
        t["battle_personalities"].append(dict(hidden, key=on, variant=variant, autonomous_rider_hero=False))
        t["battle_personalities"].append(dict(hidden, key=off, autonomous_rider_hero=False))
        like = seat_rows[ap]
        t["land_units_to_battle_personalities_junctions"].append(dict(like, land_unit=UNIT, battle_personality=on if spec["default"] == "on" else off))
        lua_parts[name] = {"seat": ap, "on": on, "off": off}
        ext = rmv2.bounding_box([v for m in seat["lods"][0] for v in m.verts])
        report["details"][name] = {"kind": "seat", "bone": bones[0], "seat": ap, "seat_rotation_is_F": [[round(v, 2) for v in row] for row in frame[1]] == [[-1, 0, 0], [0, 1, 0], [0, 0, -1]],
                                   "seat_to_detail_m": round(distance((ap, frame)), 2), "box_in_seat_frame": [round(v, 2) for v in ext],
                                   "triangles_by_lod": [sum(len(m.tris) for m in lod) for lod in seat["lods"]]}
    # The hull: its own definition with each subset of the details that must stay on it; times the harpoon (an animation table).
    like_mount = one(stock["mounts"], key=HULL_MOUNT)
    hull_mounts = {}
    names = [n for n, _ in hull_details]
    for k in range(len(names) + 1):
        for subset in combinations(range(len(names)), k):
            code = "_".join(sorted(names[i] for i in subset)) or "bare"
            variant = f"mtb_mnt_hull_{code}"
            files[f"variantmeshdefinitions/{variant}.variantmeshdefinition"] = vmd([("body", OWN_HULL_WS)] + [(f"d{i}", hull_details[i][1]) for i in subset]).encode()
            t["variants"].append(dict(hull_var, variant_name=variant, variant_filename=variant))
            for harpoon, table in (("h", HULL_TABLE), ("n", NO_HARPOON_TABLE)):
                key = f"{variant}_{harpoon}"
                t["mounts"].append(dict(like_mount, key=key, variant=variant, animation=table))
                hull_mounts[harpoon + ("_" + code if subset else "")] = key
    lua = {"parts": lua_parts, "hull_parts": names, "hull_mounts": hull_mounts}
    # A check of the formula on the one seat measured by hand: the pub on ap_crew_barrel, data/hull_parts.json.
    pub = next(d for d in json.loads((REPO / "data" / "hull_parts.json").read_text(encoding="utf-8"))["details"] if d["name"] == "pub")
    at = to_seat(frames[pub["seat"]], 0.0, 0.0, 0.0)
    report["formula_vs_pub"] = {"hand_origin": pub["seat_origin"], "formula_origin": [round(-v, 3) for v in at]}
    seats, hulls = len(lua_parts), len(names)
    n_all = seats + hulls
    report["counts"] = {
        "seat_details": seats, "hull_details": hulls,
        "per_seat_detail": {"config_lines": 1, "junction_rows": 1, "battle_personalities": 2, "variants": 1, "definitions": 1, "model_files": 2},
        "hull_definitions": 2 ** hulls, "mount_rows": 2 ** (hulls + 1),
        "rows_added_total": sum(len(v) for v in t.values()),
        "if_all_were_hull_combinations": {"definitions": 2 ** n_all, "mount_rows": 2 ** (n_all + 1)},
        "seat_vector": 29 + seats,
    }
    report["errors"] = errors
    for path, blob in files.items():
        target = OUT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    (OUT / "tables.json").write_text(json.dumps(t, indent=1, ensure_ascii=False), encoding="utf-8")
    (OUT / "lua_config.json").write_text(json.dumps(lua, indent=1), encoding="utf-8")
    (OUT / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=1, ensure_ascii=False))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
