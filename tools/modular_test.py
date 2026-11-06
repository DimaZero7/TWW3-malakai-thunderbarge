"""The one-battle experiment of docs/design/modular-parts.md (section 6): details of the barge by addition, in a test pack of its own.

  py -3.14 tools/modular_test.py build        build/modular/test/tww3_mtb_modular_test.pack, its manifest and test_config.json, then check
  py -3.14 tools/modular_test.py check        the offline checks of the built pack (tables, references, models, Lua, check_mod)
  py -3.14 tools/modular_test.py run [--two] [--save NAME] [--ignore-docker]
                                              the battle, one command: see run() below for the steps; the game is always closed
  py -3.14 tools/modular_test.py restore      puts the user's tww3_mtb_campaign.pack back from build/modular/test/stash (hash checked)
  py -3.14 tools/modular_test.py verdict RUN  the verdict of a run folder again (build/campaign/runs/...)

The test pack is the built mod (build/campaign/pack/tww3_mtb_campaign.pack, read, never written) plus:
  - the hull: the open hull of build/solid_hull_hatches/parts (port closed, porthole, stern boards and forsage tank taken out, four holes
    in the bottom) with our materials and textures; the stern rudder boards (build/solid_hull_stern/stern_armour_part) stay a slot of the
    hull's definition, because they hang on rudder_left_0 / rudder_right_0: mounts bare / stern_armour x harpoon / none.
  - three details as seats of their own, rigid on hull_0 (tools/modular_parts.py: the seat's frame from the tech skeleton):
    the forsage tank (on / off), the porthole (on / off), the bomb hatches (on = the four stock niches, off = the four covers that close
    the holes). Each seat is one more junction row on an attachment point the crew already uses: 29 + 3 = 32 seats, num_men 32.
  - src/tww3_mtb_crew.lua as built, patched: 32 seats; detail seats are found by their current row (on or off of that detail), crew
    seats by name as before; the hull's mount row by harpoon and slot details. The tables hold "on" (the stock look), the Lua writes
    the test's states before the battle, as it writes the crew. src/tww3_mtb_ammo.lua as built with 32 riders.
Nothing of data/, src/ or tools/build.py changes; the normal build stays as it was.

Known differences from the mod, on purpose: the solid hull keeps the pub and the cupola rings in its model (the mod cuts them out and puts
them on seats), so the test's crew is pub=empty and cupolas=none, and cannons=none (the solid hull has its gun port closed).
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import dbtable  # noqa: E402
import gamepack  # noqa: E402
import pfh5  # noqa: E402
import rmv2  # noqa: E402

SEP = chr(92)
TEST = REPO / "build" / "modular" / "test"
PACK_NAME = "tww3_mtb_modular_test.pack"
USER_PACK = "tww3_mtb_campaign.pack"
BASE_DIR = REPO / "build" / "campaign" / "pack"
BASE = BASE_DIR / USER_PACK
HARNESS = BASE_DIR / "tww3_mtb_harness.pack"
STASH = TEST / "stash"
CONFIG_FILE = TEST / "test_config.json"
TABLE_NAME = "!tww3_mtb"
UNIT = "mtb_dwf_cha_malakai_thunderbarge"
D = "warmachines/aircraft/dwf_thunderbarge/"
OWN_MOUNT = "mtb_mnt_thunderbarge_grungni"            # tools/crew_options.py: the mod's hull mount rows, copied for the test's
NO_HARPOON_MOUNT = "mtb_mnt_thunderbarge_no_harpoon"
HULL_VARIANT = "wh3_dlc25_dwf_mnt_veh_thunderbarge_grungni"
HIDDEN = "wh3_dlc23_chd_veh_hidden_rider"
CREW_LUA = f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew.lua"
AMMO_LUA = f"script{SEP}battle{SEP}mod{SEP}tww3_mtb_ammo.lua"
HULL_ROOT = REPO / "build" / "solid_hull_hatches"
OPEN_MODEL = D + "tww3_mtb_dwf_thunderbarge_01_open.rigid_model_v2"
OPEN_WS = D + "tww3_mtb_dwf_thunderbarge_grungni_01_open.wsmodel"
HULL_SKELETON_HEALTH = 12580     # HealthMax with 29 seats, every crew (docs/research/weapon-variants-test.md); one seat adds 8
PER_SEAT_HEALTH = 8

# The details as seats. model: the cut model in hull space (zeppelin01, one bone); off_model: what the off row shows (None: nothing).
PARTS = [
    {"name": "forsage_tank", "root": "build/solid_hull_tank/tank_part", "model": D + "tww3_mtb_dwf_thunderbarge_forsage_tank", "off_model": None, "test": "on"},
    {"name": "porthole", "root": "build/solid_hull_porthole/porthole_part", "model": D + "tww3_mtb_dwf_thunderbarge_porthole", "off_model": None, "test": "on"},
    {"name": "bomb_hatches", "root": "build/solid_hull_hatches/parts", "model": D + "tww3_mtb_dwf_thunderbarge_bomb_hatches",
     "off_model": D + "tww3_mtb_dwf_thunderbarge_hatch_covers", "test": "off"},
]
# The details on moving bones: slots of the hull's definition, one mount row per subset, times the harpoon.
HULL_SLOTS = [{"name": "stern_armour", "root": "build/solid_hull_stern/stern_armour_part", "model": D + "tww3_mtb_dwf_thunderbarge_stern_armour", "test": "on"}]
# The crew of the battle: groups that fire (rifles), nothing that doubles a detail the solid hull still has (pub, rings) or meets its closed port.
CHOICE = {"rifles": "thunderers", "cannons": "none", "cupolas": "none", "bombs": "none", "deck": "stock", "pub": "empty", "harpoon": "on"}
# --two: a second battle with every detail switched the other way, bombs in the open niches.
SECOND = {"choice": dict(CHOICE, bombs="stock", harpoon="empty"),
          "parts": {"forsage_tank": "off", "porthole": "off", "bomb_hatches": "on", "stern_armour": "off"}}
DEFAULT_SAVE = "Новаторы_Автосохранение353408270.save"    # the save of runs/20261104-175714-cycle_fb_shot: Malakai on the barge, every building
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def one(rows, **kw):
    found = [r for r in rows if all(r[k] == v for k, v in kw.items())]
    if len(found) != 1:
        raise SystemExit(f"expected one row for {kw}, found {len(found)}")
    return dict(found[0])


def to_lua(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "{" + ", ".join(to_lua(x) for x in v) + "}"
    return "{" + ", ".join(f"[{json.dumps(k, ensure_ascii=False)}] = {to_lua(x)}" for k, x in sorted(v.items())) + "}"


def layouts():
    out = json.loads((REPO / "data" / "db_layouts.json").read_text(encoding="utf-8"))
    out.update(json.loads((REPO / "data" / "weapon_layouts.json").read_text(encoding="utf-8")))
    return out


def pack_tables(files, lay):
    out = {}
    for name, blob in files.items():
        if name.startswith("db" + SEP) and name.endswith(SEP + TABLE_NAME):
            table = name.split(SEP)[1].removesuffix("_tables")
            out[table] = dbtable.decode(blob, [tuple(f) for f in lay[table]["fields"]])
    return out


def to_unit(x, y, z, scale=1.2):
    """A point of hull space as the battle's unit frame of tools/tests/crew_lib.lua: forward, right, up. Checked against the men of
    runs/20261104-175714-cycle_fb_shot: the tech skeleton's points through F land on the men within 0.1-0.5 m; hull x < 0 is the left side."""
    return [round(scale * z, 2), round(scale * x, 2), round(scale * y, 2)]


# ---------------------------------------------------------------- the Lua patch -------------------------------------------------------

PART_HELPERS = r'''
-- tww3_mtb_modular_test (tools/modular_test.py): details on seats of their own and the hull's slot details. A detail's state is saved
-- (mtb_part_<name> = 'on' / 'off'), its default is the test's; a detail seat is known by its current row, which is its on or its off row.
local PART_SAVE = 'mtb_part_'
function M.part_state(name)
    local spec = CONFIG.parts[name] or CONFIG.hull_slots[name]
    local saved = cm:get_saved_value(PART_SAVE .. name)
    if saved == 'on' or saved == 'off' then return saved end
    return spec.test
end

function M.parts()
    local out = {}
    for name in pairs(CONFIG.parts) do out[#out + 1] = name .. '=' .. M.part_state(name) end
    for name in pairs(CONFIG.hull_slots) do out[#out + 1] = name .. '=' .. M.part_state(name) end
    table.sort(out)
    return table.concat(out, ' ')
end

function M.set_parts(states)
    for name, state in pairs(states) do
        if not (CONFIG.parts[name] or CONFIG.hull_slots[name]) or (state ~= 'on' and state ~= 'off') then return false, 'bad detail ' .. tostring(name) end
    end
    for name, state in pairs(states) do cm:set_saved_value(PART_SAVE .. name, state) end
    local ok = M.apply()
    log('details ' .. M.parts() .. ': ' .. tostring(M.status))
    return ok
end

local function part_rows(mr, found)
    local out, count = {}, 0
    for name, spec in pairs(CONFIG.parts) do
        local on, off = row(mr, found.battle_personalities, spec.on), row(mr, found.battle_personalities, spec.off)
        if mr.read_string(on, ROW_KEY) ~= spec.on or mr.read_string(off, ROW_KEY) ~= spec.off then error('row check failed: detail ' .. name) end
        local item = {name = name, seat = spec.seat, want = M.part_state(name) == 'on' and on or off}
        out[tostring(on)], out[tostring(off)] = item, item
        count = count + 1
    end
    return out, count
end

local function hull_code()
    local names = {}
    for name in pairs(CONFIG.hull_slots) do
        if M.part_state(name) == 'on' then names[#names + 1] = name end
    end
    table.sort(names)
    return #names > 0 and ('_' .. table.concat(names, '_')) or ''
end

'''

# (old, new): every old text must be found exactly once in the built module.
CREW_PATCHES = [
    ("local mount_offset = nil\n", "local mount_offset = nil\n" + PART_HELPERS),
    ("    local code = (choice.harpoon == CONFIG.groups.harpoon.start and 'n' or 'h') .. (choice.cannons == 'none' and 'c' or '') .. ((choice.bombs == 'none' or choice.bombs == 'empty') and 'b' or '')\n",
     "    local code = (choice.harpoon == CONFIG.groups.harpoon.start and 'n' or 'h') .. hull_code()\n"),
    ("    local plan, seen = {}, 0\n",
     "    local plan, seen = {}, 0\n    local parts_by_row, part_count = part_rows(mr, found)\n    local parts_seen = 0\n"),
    ("        local key = wanted[name]\n        if key then\n",
     "        local part = parts_by_row[tostring(mr.read_pointer(data, i * SEAT_STRIDE))]\n"
     "        local key = (not part) and wanted[name]\n"
     "        if part then\n"
     "            if part.seat ~= name then error('detail ' .. part.name .. ' on ' .. tostring(name)) end\n"
     "            if part.done then error('detail ' .. part.name .. ' twice') end\n"
     "            part.done = true\n"
     "            plan[#plan + 1] = {i * SEAT_STRIDE, part.want}\n"
     "            parts_seen = parts_seen + 1\n"
     "        elseif key then\n"),
    ("    if seen ~= need then error('found ' .. seen .. ' of ' .. need .. ' seats') end\n",
     "    if seen ~= need then error('found ' .. seen .. ' of ' .. need .. ' seats') end\n"
     "    if parts_seen ~= part_count then error('found ' .. parts_seen .. ' of ' .. part_count .. ' detail seats') end\n"),
    ("    M.writes = M.writes + 1\n", "    M.writes = M.writes + 1\n    log('written, details ' .. M.parts())\n"),
]


def patch_once(text, old, new, what):
    if text.count(old) != 1:
        raise SystemExit(f"{what}: the text to patch is there {text.count(old)} times, not once: {old[:70]!r}")
    return text.replace(old, new)


def patch_crew(source, extra):
    lines = source.split("\n")
    at = [i for i, line in enumerate(lines) if line.startswith("local CONFIG = {")]
    if len(at) != 1 or "--@CONFIG@" in source:
        raise SystemExit("crew Lua: the built CONFIG line is not there once")
    block = ["-- tww3_mtb_modular_test: the config of the experiment (tools/modular_test.py)"] + [f"CONFIG.{k} = {to_lua(v)}" for k, v in sorted(extra.items())]
    text = "\n".join(lines[:at[0] + 1] + block + lines[at[0] + 1:])
    for old, new in CREW_PATCHES:
        text = patch_once(text, old, new, "crew Lua")
    return text


def patch_ammo(source, seats):
    """32 riders, and the base of the pool for 32: the game's pool is primary_ammo x num_men (run 20261106-184308: scale 1.10 = 32 / 29,
    rifles 466 shots instead of 422), so a base of 29 men gave every group 10 % more."""
    text = patch_once(source, '["seat_count"] = 29', f'["seat_count"] = {seats}', "ammo Lua")
    m = re.findall(r'\["primary_base"\] = (\d+)', text)
    if len(m) != 1 or int(m[0]) % 29:
        raise SystemExit(f"ammo Lua: primary_base {m}")
    return patch_once(text, f'["primary_base"] = {m[0]}', f'["primary_base"] = {int(m[0]) // 29 * seats}', "ammo Lua")


# ---------------------------------------------------------------- build ----------------------------------------------------------------

def load_model(root, path):
    p = REPO / root / (path + ".rigid_model_v2")
    if not p.exists():
        raise SystemExit(f"no model {p}")
    return rmv2.load(p.read_bytes())


def build():
    import hull_parts
    import modular_parts as mp
    lay = layouts()
    base_blob = BASE.read_bytes()
    files, _ = pfh5.read_pack(base_blob)
    t = pack_tables(files, lay)
    stock = mp.tables({"variants", "battle_personalities"})
    frames, bone_names = mp.tech_frames(mp.game_file(mp.TECH))
    aps = {n: f for n, f in frames.items() if n.startswith("ap_") and n not in mp.AVOID}
    dummy = one(stock["variants"], variant_name="dummy_variant")
    hull_var = one(stock["variants"], variant_name=HULL_VARIANT)
    hidden = one(stock["battle_personalities"], key=HIDDEN)
    seat_rows = {r["riders_attachment_point"]: r for r in t["land_units_to_battle_personalities_junctions"] if r["land_unit"] == UNIT}
    if len(seat_rows) != 29:
        raise SystemExit(f"the built mod has {len(seat_rows)} seats, not 29")
    added = {"variants": [], "battle_personalities": [], "land_units_to_battle_personalities_junctions": [], "mounts": []}
    new_files, lua_parts, report, targets = {}, {}, {"parts": {}}, {}

    def add_model(path, model, materials):
        new_files[(path + ".rigid_model_v2").replace("/", SEP)] = rmv2.save(model)
        new_files[(path + ".wsmodel").replace("/", SEP)] = rmv2.wsmodel(path + ".rigid_model_v2", materials)

    for spec in PARTS:
        name = spec["name"]
        model = load_model(spec["root"], spec["model"])
        bones = [bone_names[i] for i in mp.bones_of(model)]
        if model["skeleton"] != "zeppelin01" or len(bones) != 1:
            raise SystemExit(f"{name}: skeleton {model['skeleton']}, bones {bones}: not a rigid detail")
        cx, cy, cz = mp.centre(model)
        fitting = {n: f for n, f in aps.items() if f[0] == bones[0] and n in seat_rows}
        ap, frame = min(fitting.items(), key=lambda item: math.dist((mp.F[0] * cx, cy, mp.F[2] * cz), item[1][2]))
        rows = {}
        for state, path in (("on", spec["model"]), ("off", spec["off_model"])):
            key = f"mtb_bp_part_{name}_{state}"
            row = dict(hidden, key=key, autonomous_rider_hero=False)
            if path:
                source = model if state == "on" else load_model(spec["root"], path)
                if [bone_names[i] for i in mp.bones_of(source)] != bones or source["skeleton"] != "zeppelin01":
                    raise SystemExit(f"{name} {state}: another bone than the on model")
                seat = mp.seat_model(source, frame)
                out = f"{D}tww3_mtb_part_{name}_{state}"
                add_model(out, seat, mp.materials(spec["root"], path))
                variant = f"mtb_v_part_{name}_{state}"
                new_files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}{variant}.variantmeshdefinition"] = mp.vmd([("part", out + ".wsmodel")]).encode()
                added["variants"].append(dict(dummy, variant_name=variant, variant_filename=variant, scale=hull_var["scale"]))
                row["variant"] = variant
                box = rmv2.bounding_box([v for m in source["lods"][0] for v in m.verts])
                rows[state] = {"model": out, "triangles_by_lod": [sum(len(m.tris) for m in lod) for lod in seat["lods"]],
                               "box_hull": [round(v, 2) for v in box]}
            else:
                rows[state] = {"model": None, "variant": row["variant"]}
            added["battle_personalities"].append(row)
        # the table holds on: the stock look, also for the AI and without memreader Plus
        added["land_units_to_battle_personalities_junctions"].append(dict(seat_rows[ap], battle_personality=f"mtb_bp_part_{name}_on"))
        lua_parts[name] = {"seat": ap, "on": f"mtb_bp_part_{name}_on", "off": f"mtb_bp_part_{name}_off", "test": spec["test"]}
        box = rmv2.bounding_box([v for m in model["lods"][0] for v in m.verts])
        centre = ((box[0] + box[3]) / 2, (box[1] + box[4]) / 2, (box[2] + box[5]) / 2)
        targets[name] = {"unit": to_unit(*centre), "size_m": round(1.2 * max(box[3] - box[0], box[4] - box[1], box[5] - box[2]), 2),
                         "left": to_unit(box[0], centre[1], centre[2])}
        _, r, tt = frame
        report["parts"][name] = {"bone": bones[0], "seat": ap, "seat_rotation_is_F": [[round(v, 2) for v in row_] for row_ in r] == [[-1, 0, 0], [0, 1, 0], [0, 0, -1]],
                                 "seat_point_unit": to_unit(mp.F[0] * tt[0], tt[1], mp.F[2] * tt[2]), "rows": rows, "test": spec["test"]}

    # The hull: the open hull with its materials and textures, and the slot details as subsets, times the harpoon.
    for rel in (OPEN_MODEL, OPEN_WS):
        new_files[rel.replace("/", SEP)] = (HULL_ROOT / "parts" / rel).read_bytes()
    for folder in ("materials", "tex"):
        for p in sorted((HULL_ROOT / "warmachines" / folder).glob("tww3_mtb_*")):
            new_files[f"warmachines{SEP}{folder}{SEP}{p.name}"] = p.read_bytes()
    slot_ws = {}
    for spec in HULL_SLOTS:
        for suffix in (".rigid_model_v2", ".wsmodel"):
            new_files[(spec["model"] + suffix).replace("/", SEP)] = (REPO / spec["root"] / (spec["model"] + suffix)).read_bytes()
        m = load_model(spec["root"], spec["model"])
        box = rmv2.bounding_box([v for mm in m["lods"][0] for v in mm.verts])
        targets[spec["name"]] = {"unit": to_unit((box[0] + box[3]) / 2, (box[1] + box[4]) / 2, (box[2] + box[5]) / 2),
                                 "size_m": round(1.2 * max(box[3] - box[0], box[4] - box[1], box[5] - box[2]), 2)}
        slot_ws[spec["name"]] = spec["model"] + ".wsmodel"
    own = one(t["mounts"], key=OWN_MOUNT)
    no_harpoon_table = one(t["mounts"], key=NO_HARPOON_MOUNT)["animation"]
    hull_mounts = {}
    names = [s["name"] for s in HULL_SLOTS]
    from itertools import combinations
    for k in range(len(names) + 1):
        for subset in combinations(names, k):
            code = "_".join(sorted(subset)) or "bare"
            variant = f"mtb_mnt_hull_{code}"
            new_files[f"variantmeshes{SEP}variantmeshdefinitions{SEP}{variant}.variantmeshdefinition"] = hull_parts.variant_definition(OPEN_WS, [slot_ws[n] for n in sorted(subset)])
            added["variants"].append(dict(hull_var, variant_name=variant, variant_filename=variant))
            for harpoon, table in (("h", own["animation"]), ("n", no_harpoon_table)):
                key = f"{variant}_{harpoon}"
                added["mounts"].append(dict(own, key=key, variant=variant, animation=table))
                hull_mounts[harpoon + ("_" + code if subset else "")] = key
    default_mount = hull_mounts["h_" + "_".join(sorted(names))]

    # Rows into the tables of the pack.
    for table, rows in added.items():
        t[table] = t[table] + rows
    seats_total = 29 + len(PARTS)
    for row in t["land_units"]:
        if row["key"] == UNIT:
            row["mount"] = default_mount
    for row in t["main_units"]:
        if row["land_unit"] == UNIT:
            row["num_men"] = seats_total
    for table, rows in t.items():
        layout = lay[table]
        files[f"db{SEP}{table}_tables{SEP}{TABLE_NAME}"] = dbtable.encode(rows, [tuple(f) for f in layout["fields"]], layout["version"], table)

    # Lua.
    crew = files[CREW_LUA].decode("utf-8")
    files[CREW_LUA] = patch_crew(crew, {"seat_count": seats_total, "hull_mounts": hull_mounts, "parts": lua_parts,
                                        "hull_slots": {s["name"]: {"test": s["test"]} for s in HULL_SLOTS}}).encode("utf-8")
    files[AMMO_LUA] = patch_ammo(files[AMMO_LUA].decode("utf-8"), seats_total).encode("utf-8")
    clash = sorted(set(new_files) & set(files))
    if clash:
        raise SystemExit(f"the test's files would replace the mod's: {clash[:5]}")
    files.update(new_files)
    blob = pfh5.pack_files(files)
    TEST.mkdir(parents=True, exist_ok=True)
    (TEST / PACK_NAME).write_bytes(blob)
    shutil.copy2(HARNESS, TEST / HARNESS.name)
    (TEST / "manifest.json").write_text(json.dumps({"packs": {"harness": HARNESS.name, "campaign": PACK_NAME}}, indent=1), encoding="utf-8")
    config = {
        "_about": "Read by tools/modular_test.py run at each step: views can be corrected between runs. unit: forward, right, up of the battle's unit frame in metres.",
        "choice": CHOICE, "parts": {s["name"]: s["test"] for s in PARTS + HULL_SLOTS}, "second": SECOND,
        "seat_count": seats_total, "health_max": HULL_SKELETON_HEALTH + PER_SEAT_HEALTH * len(PARTS),
        "lua_parts": lua_parts, "hull_mounts": hull_mounts, "targets": targets, "views": views(targets),
    }
    CONFIG_FILE.write_text(json.dumps(config, indent=1, ensure_ascii=False), encoding="utf-8")
    report.update(base_sha256=sha(BASE), pack_sha256=hashlib.sha256(blob).hexdigest(), pack_bytes=len(blob), files=len(files),
                  added_rows={k: len(v) for k, v in added.items()}, seats=seats_total, default_mount=default_mount, hull_mounts=hull_mounts,
                  new_files=sorted(new_files))
    (TEST / "build_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("pack_sha256", "pack_bytes", "files", "added_rows", "seats", "default_mount")}, indent=1))
    for name, p in report["parts"].items():
        print(name, p["seat"], "frame is F" if p["seat_rotation_is_F"] else "rotated frame", p["rows"]["on"].get("triangles_by_lod"))
    print(TEST / PACK_NAME)


def views(targets):
    """The pictures of the battle. kind still: the barge stopped, close; move: during a straight run and a turn; far: a long lens from 40, 90, 200 m
    (frame: metres across the picture), with a burst at 200 m against blinking levels of detail. az: degrees from the bow, negative = the left side."""
    tank, port, hatch, stern = (targets[n]["unit"] for n in ("forsage_tank", "porthole", "bomb_hatches", "stern_armour"))
    port_left = targets["porthole"]["left"]
    tank_left = targets["forsage_tank"]["left"]
    return {
        "still": [
            {"name": "stern_left", "at": stern, "dist": 17, "az": -140, "el": 14, "fov": 45},
            {"name": "stern_right", "at": stern, "dist": 17, "az": 140, "el": 14, "fov": 45},
            {"name": "bow_left", "at": port, "dist": 13, "az": -45, "el": 6, "fov": 45},
            {"name": "bow_front", "at": [port[0], 0, port[2]], "dist": 20, "az": 0, "el": 10, "fov": 50},
            {"name": "porthole_close", "at": port_left, "dist": 5, "az": -80, "el": 4, "fov": 45},
            {"name": "below", "at": hatch, "dist": 14, "az": -35, "el": -55, "fov": 55},
            {"name": "below_side", "at": hatch, "dist": 12, "az": -90, "el": -25, "fov": 55},
            {"name": "tank_close", "at": tank, "dist": 9, "az": -55, "el": 35, "fov": 50},
            {"name": "tank_gear", "at": tank_left, "dist": 5, "az": -95, "el": 8, "fov": 50},
            {"name": "deck_top", "at": [0, 0, tank[2]], "dist": 22, "az": -160, "el": 55, "fov": 55},
        ],
        "move": [
            {"name": "tank", "at": tank, "dist": 14, "az": -55, "el": 30, "fov": 55},
            {"name": "porthole", "at": port_left, "dist": 12, "az": -70, "el": 8, "fov": 55},
            {"name": "stern", "at": stern, "dist": 18, "az": -140, "el": 12, "fov": 55},
            {"name": "below", "at": hatch, "dist": 16, "az": -40, "el": -45, "fov": 60},
        ],
        "far": {"dists": [40, 90, 200], "burst_at": 200, "burst_n": 10, "burst_gap": 0.1, "views": [
            {"name": "far_tank", "at": tank, "az": -55, "el": 25, "frame": 12},
            {"name": "far_porthole", "at": port_left, "az": -70, "el": 8, "frame": 8},
            {"name": "far_stern", "at": stern, "az": -140, "el": 12, "frame": 14},
            {"name": "far_below", "at": hatch, "az": -40, "el": -6, "frame": 14},    # -35 from 200 m put the camera into the ground (run 20261106-184308)
            {"name": "far_player", "at": [0, 0, 6], "az": -30, "el": 20, "fov": 40, "dists": [200]},
        ]},
    }


# ---------------------------------------------------------------- offline checks --------------------------------------------------------

def check():
    """Everything without the game. Prints FAIL lines; exit 1 if any."""
    import check_mod
    import modular_parts as mp
    errors = []

    def fail(text):
        errors.append(text)
        print("FAIL", text)
    lay = layouts()
    blob = (TEST / PACK_NAME).read_bytes()
    files, _ = pfh5.read_pack(blob)
    base_files, _ = pfh5.read_pack(BASE.read_bytes())
    t = pack_tables(files, lay)
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    for table, rows in t.items():         # read back equals what was encoded
        if dbtable.header(files[f"db{SEP}{table}_tables{SEP}{TABLE_NAME}"])[1] != lay[table]["version"]:
            fail(f"{table}: version")
    # everything of the mod is there, unchanged but the tables and the two scripts
    changed = sorted(n for n in base_files if files.get(n) != base_files[n])
    allowed = {n for n in base_files if n.startswith("db" + SEP)} | {CREW_LUA, AMMO_LUA}
    if set(changed) - allowed or set(base_files) - set(files):
        fail(f"mod files changed or missing: {sorted(set(changed) - allowed)[:5]}")
    print(f"pack: {len(files)} files, {len(blob)} bytes; of the mod's {len(base_files)} files {len(changed)} changed: tables and 2 scripts")
    # seats
    seats = [r for r in t["land_units_to_battle_personalities_junctions"] if r["land_unit"] == UNIT]
    mu = one(t["main_units"], land_unit=UNIT)
    if len(seats) != config["seat_count"] or mu["num_men"] != len(seats):
        fail(f"{len(seats)} seats, num_men {mu['num_men']}, expected {config['seat_count']}")
    by_ap = {}
    for r in seats:
        by_ap.setdefault(r["riders_attachment_point"], []).append(r["battle_personality"])
    doubled = {ap: v for ap, v in by_ap.items() if len(v) > 1}
    want = {p["seat"]: p for p in config["lua_parts"].values()}
    if set(doubled) != set(want) or any(sum(x == want[ap]["on"] for x in v) != 1 for ap, v in doubled.items()):
        fail(f"two seats on a point: {doubled}")
    print("seats:", len(seats), "num_men", mu["num_men"], "| two seats on", {ap: v for ap, v in doubled.items()})
    # references: rows, variants, definitions, models, materials, textures
    import build as mod_build
    stock = mod_build.game_tables()
    pers = {r["key"]: r for r in stock["battle_personalities"]} | {r["key"]: r for r in t["battle_personalities"]}
    variants = {r["variant_name"]: r for r in stock["variants"]} | {r["variant_name"]: r for r in t["variants"]}
    mounts = {r["key"]: r for r in t["mounts"]}
    stats = {r["key"]: r for r in stock["battle_entity_stats"]} | {r["key"]: r for r in t.get("battle_entity_stats", [])}
    for r in seats:
        if r["battle_personality"] not in pers:
            fail(f"seat {r['riders_attachment_point']}: no row {r['battle_personality']}")
    for name, p in config["lua_parts"].items():
        for state in ("on", "off"):
            row = pers.get(p[state])
            if not row:
                fail(f"{name}: no row {p[state]}")
                continue
            if row["variant"] not in variants:
                fail(f"{p[state]}: no variant {row['variant']}")
            if row["autonomous_rider_hero"]:
                fail(f"{p[state]}: a hero seat")
            st = stats.get(row["battle_entity_stats"]) if row["battle_entity_stats"] else None
            if st and st.get("primary_missile_weapon"):
                fail(f"{p[state]}: a weapon {st['primary_missile_weapon']}")
            if row["man_animations_table"] != pers[HIDDEN]["man_animations_table"] or row["battle_entity"] != pers[HIDDEN]["battle_entity"]:
                fail(f"{p[state]}: not the hidden rider's table and entity")
    lu = one(t["land_units"], key=UNIT)
    if lu["mount"] not in mounts or lu["mount"] not in config["hull_mounts"].values():
        fail(f"land unit mount {lu['mount']}")
    for key in config["hull_mounts"].values():
        m = mounts.get(key)
        if not m or m["variant"] not in variants:
            fail(f"mount {key}")
    names = {n.lower() for n in files}
    game_names = {}
    need_models, need_materials, need_textures = set(), set(), set()
    for name, b in files.items():
        if name.endswith(".variantmeshdefinition") and ("mtb_v_part_" in name or "mtb_mnt_hull_" in name):
            need_models |= {m.replace("/", SEP).lower() for m in re.findall(r'model="([^"]+)"', b.decode())}
    for name in sorted(n for n in files if n.endswith(".wsmodel") and ("tww3_mtb_part_" in n or "_open" in n or "stern_armour" in n)):
        text = files[name].decode()
        geo = re.findall(r"<geometry>([^<]+)</geometry>", text)
        if len(geo) != 1 or geo[0].replace("/", SEP).lower() not in names:
            fail(f"{name}: geometry {geo}")
        model = rmv2.load(files[geo[0].replace("/", SEP)])
        lods = {int(x) for x in re.findall(r'lod_index="(\d+)"', text)}
        if lods != set(range(len(model["lods"]))):
            fail(f"{name}: materials for LODs {sorted(lods)}, model has {len(model['lods'])}")
        need_materials |= {m.replace("/", SEP).lower() for m in re.findall(r">([^<>]+\.xml\.material)<", text)}
        if "tww3_mtb_part_" in name:
            bones = mp.bones_of(model)
            if model["skeleton"] != "default_skeleton" or bones != [0] or len(model["lods"]) != 4:
                fail(f"{name}: skeleton {model['skeleton']}, bones {bones}, {len(model['lods'])} LODs")
        elif model["skeleton"] != "zeppelin01":
            fail(f"{name}: skeleton {model['skeleton']}")
    for name in need_materials:
        if name in names:
            need_textures |= {m.replace("/", SEP).lower() for m in re.findall(r"<source>([^<]+)</source>", files[next(n for n in files if n.lower() == name)].decode())}
    wanted = {n for n in need_models | need_materials | need_textures if n not in names}
    for pack in sorted(gamepack.DATA.glob("*.pack")):
        if pack.name.startswith(("audio", "local_", "tww3_")) or not wanted - set(game_names):
            continue
        for n, _ in gamepack.entries(pack, lambda n: n.lower() in wanted):
            game_names[n.lower()] = pack.name
    for n in sorted(wanted - set(game_names)):
        fail(f"not in the pack or the game: {n}")
    print(f"models named by the new definitions: {len(need_models)}, materials {len(need_materials)}, textures {len(need_textures)}; from the game: {len(game_names)}")
    # every seat model, put on its seat by the game's tech skeleton (R q + t, then F into hull space), lands on the cut model's own place
    frames, _ = mp.tech_frames(mp.game_file(mp.TECH))
    for spec in PARTS:
        p = config["lua_parts"][spec["name"]]
        _, rot, tt = frames[p["seat"]]
        for state, path in (("on", spec["model"]), ("off", spec["off_model"])):
            if not path:
                continue
            source = load_model(spec["root"], path)
            seat = rmv2.load(files[f"{D}tww3_mtb_part_{spec['name']}_{state}.rigid_model_v2".replace("/", SEP)])
            worst = 0.0
            for lod_a, lod_b in zip(source["lods"], seat["lods"]):
                for ma, mb in zip(lod_a, lod_b):
                    for va, vb in zip(ma.verts, mb.verts):
                        w = [tt[k] + sum(rot[k][j] * (vb.x, vb.y, vb.z)[j] for j in range(3)) for k in range(3)]
                        worst = max(worst, math.dist((va.x, va.y, va.z), (mp.F[0] * w[0], w[1], mp.F[2] * w[2])))
            if worst > 0.005:
                fail(f"{spec['name']} {state}: the seat model lands up to {worst:.3f} m off its place")
            print(f"{spec['name']} {state} on {p['seat']}: lands on its place within {worst * 1000:.1f} mm ({mp.TECH.rsplit('/', 1)[1]})")
    # Lua: the patch is in, the config is right, it parses, and the offline run of the seat writer (tools/modular_offline.py, lupa)
    crew = files[CREW_LUA].decode("utf-8")
    for needle in ("CONFIG.seat_count = 32", "part_rows(mr, found)", "hull_code()", "M.set_parts"):
        if needle not in crew:
            fail(f"crew Lua: no {needle}")
    if '["seat_count"] = 32' not in files[AMMO_LUA].decode("utf-8") or '["primary_base"] = 1280' not in files[AMMO_LUA].decode("utf-8"):
        fail("ammo Lua: seat_count 32 and primary_base 40 x 32")
    out = subprocess.run([shutil.which("python") or "python", str(REPO / "tools" / "modular_offline.py")], capture_output=True, text=True, errors="replace")
    print(out.stdout.strip()[-3000:])
    if out.returncode != 0:
        fail("offline Lua run: " + (out.stdout + out.stderr)[-600:])
    # check_mod on the test pack: the mod's own checks still hold with the test's rows added
    check_mod.PACK = TEST / PACK_NAME
    check_mod.errors.clear()
    code = check_mod.main()
    if code:
        fail(f"check_mod on the test pack: {len(check_mod.errors)} failures")
    print("check:", "OK" if not errors else f"{len(errors)} failures")
    return 1 if errors else 0


# ---------------------------------------------------------------- the user's pack -------------------------------------------------------

def stash_user_pack(log):
    """Moves data/tww3_mtb_campaign.pack out of the game for the run: copied to build/modular/test/stash, hash compared, then removed from data/."""
    import run_battle as rb
    source = rb.GAME / "data" / USER_PACK
    if not source.exists():
        log("no user pack in data/: nothing to stash")
        return None
    STASH.mkdir(parents=True, exist_ok=True)
    digest, size = sha(source), source.stat().st_size
    target = STASH / USER_PACK
    shutil.copy2(source, target)
    if sha(target) != digest:
        target.unlink()
        raise SystemExit("the stash copy differs from the user's pack: nothing moved")
    record = {"path": str(source), "sha256": digest, "bytes": size, "mtime": source.stat().st_mtime, "when": datetime.now().isoformat()}
    (STASH / "stash.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    source.unlink()
    log("user pack stashed", digest[:16], size)
    return record


def restore_user_pack(log=print):
    """Puts the stashed pack back where it was and checks the hash. Returns True when data/ has the user's pack as it was (or nothing was stashed)."""
    record_file = STASH / "stash.json"
    if not record_file.exists():
        return True
    record = json.loads(record_file.read_text(encoding="utf-8"))
    source, target = STASH / USER_PACK, Path(record["path"])
    if target.exists():
        if sha(target) == record["sha256"]:
            log("user pack already in place, same hash")
            source.unlink(missing_ok=True)
            record_file.unlink()
            return True
        log("RESTORE STOPPED: data/ has another", USER_PACK, "now; the stash stays in", STASH)
        return False
    if not source.exists() or sha(source) != record["sha256"]:
        log("RESTORE STOPPED: the stash copy is missing or changed", source)
        return False
    shutil.copy2(source, target)
    if sha(target) != record["sha256"]:
        target.unlink()
        log("RESTORE FAILED: the copy in data/ differs; the stash stays in", STASH)
        return False
    source.unlink()
    record_file.unlink()
    log("user pack restored", record["sha256"][:16], "same hash")
    return True


# ---------------------------------------------------------------- the battle ------------------------------------------------------------

AIM = r'''
local function vec(x, y, z) local v = battle_vector:new(); v:set_x(x); v:set_y(y); v:set_z(z); return v end
local u = C.lord_unit()
if not u then return 'no lord' end
if mtb_halt and _G.mtb_crew_uc then _G.mtb_crew_uc:halt() end
local p, b = u:position(), u:bearing() * math.pi / 180
local f, r, up = mtb_at[1], mtb_at[2], mtb_at[3]
local x, y, z = p:get_x() + math.sin(b) * f + math.cos(b) * r, p:get_y() + up, p:get_z() + math.cos(b) * f - math.sin(b) * r
local a, e = b + mtb_az * math.pi / 180, mtb_el * math.pi / 180
local cx, cy, cz = x + math.sin(a) * math.cos(e) * mtb_dist, y + math.sin(e) * mtb_dist, z + math.cos(a) * math.cos(e) * mtb_dist
bm:camera():move_to(vec(cx, cy, cz), vec(x, y, z), 0, false, mtb_fov)
return string.format('target %.1f %.1f %.1f camera %.1f %.1f %.1f bearing %.0f', x, y, z, cx, cy, cz, u:bearing())
'''

# The lord's unit fights for real: a controller, fire at will, NOT invincible (tools/tests/crew_fight.lua makes it invincible).
FIGHT = r'''
local lord = C.lord_unit()
if not lord then return 'no lord' end
local lord_army, enemy_alliance
local alliances = bm:alliances()
for a = 1, alliances:count() do
  local armies = alliances:item(a):armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      if us:item(j):type() == C.LAND_UNIT then lord_army, enemy_alliance = armies:item(i), alliances:item(3 - a) end
    end
  end
end
local uc = lord_army:create_unit_controller()
uc:add_units(lord)
uc:take_control()
uc:fire_at_will(true)
_G.mtb_crew_uc = uc
_G.mtb_crew_enemy = enemy_alliance
bm:modify_battle_speed(3)
return 'controller ready, not invincible; ' .. tostring(C.order())
'''

# A straight run or a turn: a point mtb_dist ahead, mtb_side degrees off the bow.
RUN = r'''
local u = C.lord_unit()
local p, b = u:position(), u:bearing() * math.pi / 180
local a = b + mtb_side * math.pi / 180
_G.mtb_crew_uc:goto_location(battle_vector:new(p:get_x() + math.sin(a) * mtb_dist, p:get_y(), p:get_z() + math.cos(a) * mtb_dist), true)
return string.format('run to %.0f deg, bearing %.0f', mtb_side, u:bearing())
'''


def run(args):
    """One command for the whole experiment:
      1. refuses when the machine is busy (Warhammer3.exe in tasklist, probe_game.lock, HUMAN_PLAYING, gpu-train.lock, the neighbour's settings copy,
         docker unless --ignore-docker); puts back a pack left in the stash by an earlier interrupted run;
      2. moves the user's data/tww3_mtb_campaign.pack to build/modular/test/stash (sha256 compared);
      3. starts tools/run_game.py with this folder's manifest (harness + test pack + memreader Plus from the Workshop), the save, good models at 1280x720,
         Normal, RTX checked; run_game.py writes probe_game.lock (one line «mtb, начало HH:MM», as agreed with the neighbour), keeps the window behind,
         backs up the user's settings and saves and restores them, and always closes the game it started and removes the lock only when tasklist has no game;
      4. on the campaign map: the crew of test_config.json, the details' states written through memreader Plus, the seat list read back (32);
      5. the battle: pre-battle panel, men and rows in memory, still pictures, a real fight (not invincible), pictures in a straight run and a turn,
         long-lens pictures from 40, 90 and 200 m with a burst at 200 m, the ammunition report; the enemy killed, back on the map;
         with --two the same again with every detail switched the other way;
      6. the session ends (STOP flag), the user's pack goes back with its hash checked, pictures get JPG copies and a sheet, verdict.txt is written."""
    import capture  # noqa: F401  (Windows only: fails early if missing)
    import crew_cycle as cc
    import far_view
    import rc
    import run_game as rg
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    manifest = json.loads((TEST / "manifest.json").read_text(encoding="utf-8"))
    for name in manifest["packs"].values():
        if not (TEST / name).exists():
            raise SystemExit(f"no {name}: py -3.14 tools/modular_test.py build")
    if args.save and not (rg.SAVES / args.save).exists():
        raise SystemExit(f"no save {rg.SAVES / args.save}")
    if not restore_user_pack():
        raise SystemExit("the stash of an earlier run could not go back: look at build/modular/test/stash first")
    busy = rg.rb.busy_reasons()
    if args.ignore_docker:
        busy = [b for b in busy if b != "docker containers are running"]
    if rg.STATE.exists():
        busy.append(f"{rg.STATE} remains from another session")
    if busy:
        print("BUSY, not launching:", "; ".join(busy), flush=True)
        return 3
    limit = args.limit * (2 if args.two else 1)
    started = time.time()
    session = cc.Session("modular_test", started + limit)
    session.current = dict(config["choice"])
    cmd = [sys.executable, str(Path(__file__).resolve()), "_session", "--label", "modular_test", "--timeout", str(limit + 120),
           "--packs", "harness", "campaign", "--user-mods", "memreader_plus.pack", "--high-graphics", "--set", "x_res=1280", "y_res=720"]
    if args.save:
        cmd += ["--save", args.save, "--args", f"game_startup_mode campaign_load {args.save}"]
    if args.ignore_docker:
        cmd.append("--ignore-docker")
    TEST.mkdir(parents=True, exist_ok=True)
    outcome, stashed, proc = "failed", None, None
    try:
        stashed = stash_user_pack(session.log)
        proc = subprocess.Popen(cmd, stdout=(TEST / "session.log").open("w", encoding="utf-8"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        end = time.time() + 60
        while not rg.STATE.exists():
            if proc.poll() is not None or time.time() > end:
                raise RuntimeError("the session did not start, see build/modular/test/session.log")
            time.sleep(1)
        session.dir = Path(rc.state()["run"])
        (TEST / "last_run.txt").write_text(str(session.dir), encoding="utf-8")
        for name in (CONFIG_FILE.name, "build_report.json"):      # the verdict reads the run's own copies, not a later build's
            shutil.copy2(TEST / name, session.dir / name)
        session.log("run", session.dir, "stash", bool(stashed))
        session.wait_mode("campaign", 900)
        time.sleep(8)
        session.shot("map")
        session.log("blockers", session.script("dismiss_blockers.lua")["result"])
        battles = [("b1", config["choice"], config["parts"])]
        if args.two:
            battles.append(("b2", config["second"]["choice"], config["second"]["parts"]))
        for label, choice, parts in battles:
            battle(session, cc, far_view, label, choice, parts)
        outcome = "done"
    except Exception as e:  # the game must be closed in every case
        session.log("ERROR", type(e).__name__, e)
    finally:
        if proc is not None:
            if proc.poll() is None:     # the flag ends run_game.py's loop: the game closed, the user's files back, the lock off when tasklist has no game
                rg.STOP.write_text("stop")
            try:
                proc.wait(240)
            except subprocess.TimeoutExpired:
                session.log("session did not end in 240 s: run_game.py keeps the lock while a game is in tasklist")
        restored = restore_user_pack(session.log)
        session.log("experiment", outcome, "seconds", round(time.time() - started), "user pack back:", restored)
    if session.dir:
        status = session.dir / "status.json"
        extra = {"outcome": outcome, "user_pack_restored": restored, "stashed": stashed, "seconds": round(time.time() - started)}
        (session.dir / "experiment.json").write_text(json.dumps(extra, indent=1, ensure_ascii=False), encoding="utf-8")
        pictures(session.dir)
        print(verdict(session.dir))
        if not status.exists():
            print("no status.json: the session wrapper did not finish, check tasklist and build/modular/test/session.log")
    return 0 if outcome == "done" and restored else 1


def aim(session, view, halt=True, dist=None, fov=None):
    code = (f"mtb_at = {{{view['at'][0]}, {view['at'][1]}, {view['at'][2]}}}; mtb_az = {view['az']}; mtb_el = {view['el']}; "
            f"mtb_dist = {dist or view['dist']}; mtb_fov = {fov or view['fov']}; mtb_halt = {'true' if halt else 'false'}\n" + AIM)
    return session.lua(code, 10)["result"]


def battle(s, cc, far_view, label, choice, parts):
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    s.log("=== battle", label, choice, parts)
    s.current = dict(choice)
    s.choose(choice)
    states = "{" + ", ".join(f"{k} = '{v}'" for k, v in parts.items()) + "}"
    row = s.plain(f"local ok, err = tww3_mtb_crew.set_parts({states}); return tostring(ok) .. ' ' .. tostring(err) .. ' | ' .. tostring(tww3_mtb_crew.status) .. ' | ' .. tww3_mtb_crew.parts()", 15)
    s.log("details", row["result"])
    pre = s.lua("return C.list()", 20)
    (s.dir / f"pre_{label}.txt").write_text(str(pre["result"]), encoding="utf-8")
    s.log("seat list before the battle", str(pre["result"]).split("\n")[0])
    s.log("spawn", s.script("spawn_fight.lua")["result"])
    s.open_panel()
    s.shot(f"{label}_prebattle_panel")
    s.log(s.click("button_attack"))
    s.wait_mode("battle", 300)
    time.sleep(4)
    men = s.lua("return C.men()", 20)
    (s.dir / f"men_{label}.txt").write_text(str(men["result"]), encoding="utf-8")
    read = s.plain((cc.TESTS / "battle_read.lua").read_text(encoding="utf-8"), 15)
    (s.dir / f"read_{label}.txt").write_text(str(read["result"]), encoding="utf-8")
    first = s.lua("return C.stats()", 8)
    s.log("stats before the fight", first["result"])
    (s.dir / f"stats0_{label}.txt").write_text(str(first["result"]), encoding="utf-8")
    s.gpu_note()
    # still pictures, the barge not moving yet (deployment)
    s.plain("bm:enable_cinematic_ui(true, true, false); return 1", 5)
    for view in config["views"]["still"]:
        s.log("aim", view["name"], aim(s, view, halt=False))
        time.sleep(1.5)
        s.shot(f"{label}_{view['name']}")
    s.plain("bm:enable_cinematic_ui(false, true, false); return 1", 5)
    # the fight: up to 90 s at speed 3, the stats every 5 s
    s.plain("bm:end_current_battle_phase(); return 1", 5)
    time.sleep(3)
    s.log("fight", s.lua(FIGHT, 10)["result"])
    stats, fired_at, begun = [], None, time.time()
    while time.time() - begun < cc.scaled(90):
        time.sleep(5)
        r = s.lua("C.order(); return C.stats()", 8)
        stats.append(str(r["result"]))
        m = re.search(r"pct=([\d.]+) kills=(\d+)", str(r["result"]))
        if m and fired_at is None and (int(m.group(2)) > 0 or float(m.group(1)) < 0.9995):
            fired_at = time.time()
            s.log("fired", r["result"])
        if fired_at and time.time() - fired_at > 25:
            break
    (s.dir / f"stats_{label}.txt").write_text("\n".join(stats), encoding="utf-8")
    ammo = s.plain("return tostring(tww3_mtb_ammo.status) .. ' cargo ' .. tostring(tww3_mtb_ammo.cargo) .. ' | ' .. tww3_mtb_ammo.report() .. "
                   "' || LOG ' .. table.concat(tww3_mtb_ammo.log_lines, ' ; ')", 8)
    (s.dir / f"ammo_{label}.txt").write_text(str(ammo["result"]), encoding="utf-8")
    s.log("ammo", ammo["result"])
    s.shot(f"{label}_fight")
    men2 = s.lua("return C.men()", 20)
    (s.dir / f"men_after_{label}.txt").write_text(str(men2["result"]), encoding="utf-8")
    # in motion: a straight run, then a turn, speed 1, the camera aimed right before each picture
    s.plain("bm:modify_battle_speed(1); bm:enable_cinematic_ui(true, true, false); return 1", 5)
    for phase, side in (("straight", 0), ("turn", 120)):
        s.log("run", s.lua(f"mtb_side = {side}; mtb_dist = 400\n" + RUN, 8)["result"])
        time.sleep(5 if phase == "straight" else 1.5)
        for view in config["views"]["move"]:
            aim(s, view, halt=False)
            s.shot(f"{label}_move_{phase}_{view['name']}")
    # far: the long lens from 40, 90, 200 m, the barge stopped; a burst at 200 m against blinking
    far = config["views"]["far"]
    targets = {v["name"]: v for v in far["views"]}
    far_view.aim = lambda name, az, el, dist, fov: aim(s, dict(targets[name], az=az, el=el), halt=True, dist=dist, fov=fov)
    for view in far["views"]:
        try:
            far_view.sweep(f"{label}_{view['name']}", view["name"], view["az"], view["el"], view.get("dists", far["dists"]), view.get("frame"), view.get("fov"))
            if view.get("frame"):
                far_view.burst(f"{label}_{view['name']}_burst", view["name"], view["az"], view["el"], far["burst_at"], view["frame"], None, far["burst_n"], far["burst_gap"])
        except Exception as e:      # a picture lost is not a reason to lose the rest
            s.log("far view failed", view["name"], type(e).__name__, e)
    s.plain("bm:enable_cinematic_ui(false, true, false); return 1", 5)
    s.log(s.script("battle_kill_enemy.lua")["result"])
    for attempt in range(25):
        if s.visible("button_dismiss_results") != "-":
            break
        if attempt == 8:
            s.plain("bm:end_battle(); return 1", 5)
        time.sleep(3)
    s.log(s.click("button_dismiss_results"))
    s.wait_mode("campaign", 300)
    time.sleep(4)
    s.back_on_map()


# ---------------------------------------------------------------- pictures and verdict --------------------------------------------------

SHEET = r'''
import sys, pathlib
from PIL import Image, ImageDraw
run = pathlib.Path(sys.argv[1]); out = run / "jpg"; out.mkdir(exist_ok=True)
pngs = sorted(run.glob("*.png"))
for p in pngs:
    Image.open(p).convert("RGB").save(out / (p.stem + ".jpg"), quality=88)
for label in ("b1", "b2"):
    key = [p for p in pngs if p.stem.startswith(label + "_") and "_burst" not in p.stem and "_f" not in p.stem[-4:]]
    if not key:
        continue
    w, h, cols = 480, 270, 4
    rows = (len(key) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, (h + 18) * rows), (20, 20, 20))
    d = ImageDraw.Draw(sheet)
    for i, p in enumerate(key):
        x, y = (i % cols) * w, (i // cols) * (h + 18)
        sheet.paste(Image.open(p).convert("RGB").resize((w, h)), (x, y + 18))
        d.text((x + 4, y + 3), p.stem, fill=(255, 255, 255))
    sheet.save(out / f"sheet_{label}.jpg", quality=85)
print(len(pngs), "pictures as JPG in", out)
'''


def pictures(run_dir):
    """JPG copies of every PrintWindow picture and a sheet per battle, with the plain Python that has Pillow."""
    py = shutil.which("python")
    out = subprocess.run([py or "python", "-c", SHEET, str(run_dir)], capture_output=True, text=True, errors="replace")
    print((out.stdout + out.stderr).strip()[-400:])


def men_lines(text):
    """{index: (ap, key, w, (x, y, z))} of tools/tests/crew_lib.lua C.men()."""
    out = {}
    text = text.split("vector 180")[0]
    for m in re.finditer(r"^(\d+) (\S+) (\S+) var=(\S+) anim=(\S+) w=(\S+) at (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)", text, re.M):
        out[int(m.group(1))] = (m.group(2), m.group(3), m.group(6), (float(m.group(7)), float(m.group(8)), float(m.group(9))), m.group(4))
    return out


def verdict(run_dir):
    """Lines PASS / FAIL / INFO / LOOK from the files of a run; written to verdict.txt and verdict.json."""
    run_dir = Path(run_dir)
    config = json.loads(((run_dir / CONFIG_FILE.name) if (run_dir / CONFIG_FILE.name).exists() else CONFIG_FILE).read_text(encoding="utf-8"))
    report_file = (run_dir / "build_report.json") if (run_dir / "build_report.json").exists() else TEST / "build_report.json"
    lines = []

    def line(kind, text):
        lines.append(f"{kind:5} {text}")

    def read(name):
        p = run_dir / name
        return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    log = read("tww3_mtb_log.txt")
    for label, parts in (("b1", config["parts"]), ("b2", config["second"]["parts"])):
        pre = read(f"pre_{label}.txt")
        if not pre:
            continue
        want = {p["seat"]: (name, p[parts[name]], p["on" if parts[name] == "off" else "off"]) for name, p in config["lua_parts"].items()}
        head = pre.split("\n")[0]
        n = config["seat_count"]
        line("PASS" if head.strip() == f"size {n} cap {n}" else "FAIL", f"{label} seat list in memory before the battle: {head.strip()} (want size {n} cap {n})")
        for name, p in config["lua_parts"].items():
            keys = re.findall(rf"^\d+ {p['seat']} (\S+)", pre, re.M)
            good = p[parts[name]] in keys and p["on" if parts[name] == "off" else "off"] not in keys
            line("PASS" if good else "FAIL", f"{label} written before the battle: {name} {parts[name]} on {p['seat']}: rows there {keys}")
        men = read(f"men_{label}.txt")
        m = re.search(r"script (\d+)/(\d+)", men)
        v = re.search(r"vector 110: (\d+)", men)
        line("PASS" if m and v and m.group(1) == m.group(2) == v.group(1) == str(n) else "FAIL",
             f"{label} men in the battle: script {m.group(1) + '/' + m.group(2) if m else '-'}, vector {v.group(1) if v else '-'} (want {n})")
        ml = men_lines(men)
        unit = re.search(r"unit at (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) bearing (-?[\d.]+)", men)
        built = json.loads(report_file.read_text(encoding="utf-8"))["parts"] if report_file.exists() else {}
        for name, p in config["lua_parts"].items():
            mine = [x for x in ml.values() if x[1] == p[parts[name]]]
            crew = [x for x in ml.values() if x[0] == p["seat"] and not x[1].startswith("mtb_bp_part_")]
            if len(mine) != 1:
                line("FAIL", f"{label} {name}: {len(mine)} men with {p[parts[name]]}")
                continue
            gap = math.dist(mine[0][3], crew[0][3]) if crew else None
            line("PASS" if mine[0][2] in ("-", "no_missile") else "FAIL", f"{label} {name}: row {mine[0][1]} var={mine[0][4]} weapon {mine[0][2]}")
            line("PASS" if gap is not None and gap < 0.3 else "LOOK", f"{label} {name}: the detail's man stands {gap if gap is None else round(gap, 2)} m from the crew's man on {p['seat']}")
            if unit and name in built:
                f, r, u = built[name]["seat_point_unit"]
                x0, y0, z0, b = (float(unit.group(i)) for i in range(1, 5))
                b = math.radians(b)
                expect = (x0 + math.sin(b) * f + math.cos(b) * r, y0 + u, z0 + math.cos(b) * f - math.sin(b) * r)
                line("INFO", f"{label} {name}: the seat point from the tech skeleton is {math.dist(expect, mine[0][3]):.2f} m from the detail's man (the frame formula's place)")
        stats0 = read(f"stats0_{label}.txt")
        hp = re.search(r"hp=(\S+)/(\S+)", stats0)
        if hp:
            try:
                got = float(hp.group(2))
                line("PASS" if abs(got - config["health_max"]) < 0.5 else "FAIL",
                     f"{label} HealthMax {got:.0f}, want {config['health_max']} = {HULL_SKELETON_HEALTH} + {len(PARTS)} x {PER_SEAT_HEALTH} (29 seats: {HULL_SKELETON_HEALTH})")
            except ValueError:
                line("FAIL", f"{label} HealthMax {hp.group(0)}")
        else:
            line("FAIL", f"{label} no stats before the fight: {stats0[:120]}")
        stats = read(f"stats_{label}.txt").splitlines()
        fired = [x for x in stats for m in [re.search(r"pct=([\d.]+) kills=(\d+)", x)] if m and (int(m.group(2)) > 0 or float(m.group(1)) < 0.9995)]
        line("PASS" if fired else "FAIL", f"{label} the crew fired: {stats[-1] if stats else '-'}")
        ammo = read(f"ammo_{label}.txt")
        line("PASS" if ammo.startswith("running") and "part" not in ammo.split("|| LOG")[0] else "FAIL", f"{label} ammunition module: {ammo.split('|| LOG')[0][:240]}")
        scale = re.findall(r"running, .*? scale ([\d.]+)", ammo)
        line("INFO", f"{label} ammunition scale in the log: {scale} (1.00: the pool does not grow with the seats; 1.10: it does, primary_base must count 32)")
        after = read(f"men_after_{label}.txt")
        a = re.search(r"script (\d+)/(\d+)", after)
        line("INFO", f"{label} men after the fight: {a.group(0) if a else '-'} (a detail seat dying would show as fewer)")
    crew_log = [x for x in log.splitlines() if "[crew]" in x]
    bad = [x for x in crew_log if "stock:" in x or "mount:" in x or "error" in x.lower()]
    line("PASS" if crew_log and not bad else "FAIL", f"crew module log: {len(crew_log)} lines, problems: {bad[:3]}")
    line("INFO", "details written: " + "; ".join(x.split("[crew]")[-1].strip() for x in crew_log if "details" in x)[-300:])
    burst = read("burst.txt")
    for b in burst.splitlines():
        m = re.search(r"^(\S+) dist=(\S+) .* neighbours=\[([^\]]*)\]", b)
        if m:
            steps = sorted(float(x) for x in m.group(3).split(",") if x.strip())
            worst, median = (steps[-1], steps[len(steps) // 2]) if steps else (0.0, 0.0)
            if worst == 0:
                line("LOOK", f"burst {m.group(1)} at {m.group(2)} m: all frames the same: the camera saw nothing that moves (in the ground?)")
            elif worst < 0.05 or worst < 2.5 * median:
                line("INFO", f"burst {m.group(1)} at {m.group(2)} m: change {median:.3f}..{worst:.3f} between every pair, steady: the barge drifting, no blink")
            else:
                line("LOOK", f"burst {m.group(1)} at {m.group(2)} m: one pair {worst:.3f} against {median:.3f}: look at that pair for a blinking detail")
    status = json.loads(read("status.json") or "{}")
    exp = json.loads(read("experiment.json") or "{}")
    line("PASS" if status.get("game_gone") and status.get("prefs_restored") and (status.get("user_files") or {}).get("saves_identical") else "FAIL",
         f"cleanup: game closed {status.get('game_gone')}, settings back {status.get('prefs_restored')}, saves {(status.get('user_files') or {}).get('saves_identical')}, status {status.get('status')}")
    line("PASS" if exp.get("user_pack_restored") else "FAIL", f"user's {USER_PACK} back in data/ with the same hash: {exp.get('user_pack_restored')} (stashed: {bool(exp.get('stashed'))})")
    line("LOOK", "jpg/sheet_b1.jpg: tank_close, tank_gear: the tank sits on the deck against the gear, as build/solid_hull_tank/shots and the stock barge")
    line("LOOK", "bow_left, porthole_close: the porthole in its opening on the bow, not turned (its seat ap_crew_left_upper_0 has a rotated frame)")
    line("LOOK", "below, below_side: no hatches, the bottom closed by the covers (b1); in b2 the four niches with the bomb doors")
    line("LOOK", "stern_left, stern_right: the rudder boards on the rudders (hull slot) in b1, none in b2")
    line("LOOK", "move_straight_*, move_turn_*: the details stay on the hull in the run and in the turn; far_*_40/90/200: there, no gap, a shadow")
    line("LOOK", "b1_prebattle_panel: the unit card, the number of men")
    text = "\n".join(lines)
    (run_dir / "verdict.txt").write_text(text + "\n", encoding="utf-8")
    (run_dir / "verdict.json").write_text(json.dumps(lines, indent=1, ensure_ascii=False), encoding="utf-8")
    return text


# ---------------------------------------------------------------- main -----------------------------------------------------------------

def session_main(argv):
    """tools/run_game.py with the test's manifest and the agreed lock line; docker counts as busy unless --ignore-docker."""
    import run_game as rg
    rb = rg.rb
    if "--ignore-docker" in argv:
        argv = [a for a in argv if a != "--ignore-docker"]
        busy = rb.busy_reasons
        rb.busy_reasons = lambda: [r for r in busy() if r != "docker containers are running"]
    rg.PACK_DIR = TEST

    class Lock(type(rb.LOCK)):
        def write_text(self, data, encoding=None, errors=None, newline=None):
            return super().write_text(f"mtb, начало {datetime.now():%H:%M}\n", encoding="utf-8")
    rb.LOCK = Lock(rb.LOCK)
    return rg.main(argv)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "_session":
        return session_main(sys.argv[2:])
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["build", "check", "run", "restore", "verdict"])
    ap.add_argument("run_dir", nargs="?")
    ap.add_argument("--two", action="store_true", help="a second battle with every detail switched the other way")
    ap.add_argument("--save", default=DEFAULT_SAVE, help="a save of build/campaign/saves with Malakai on the barge")
    ap.add_argument("--limit", type=int, default=1200, help="hard limit of one battle's session in seconds")
    ap.add_argument("--ignore-docker", action="store_true", help="a running docker container alone does not stop the launch")
    args = ap.parse_args()
    if args.what == "build":
        build()
        return check()
    if args.what == "check":
        return check()
    if args.what == "restore":
        return 0 if restore_user_pack() else 1
    if args.what == "verdict":
        print(verdict(args.run_dir or (TEST / "last_run.txt").read_text(encoding="utf-8").strip()))
        return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
