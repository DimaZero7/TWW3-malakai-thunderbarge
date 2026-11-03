"""Own animation tables of the barge's cannon, for guns that fire one barrel after another.

The game fires as many shots as the weapon's shots_per_volley allows and the animation has FIRE_POS entries (battles volley2, volley3:
one entry, one shot). A replaced .anm.meta or .bin under the game's own name has no effect (battle volley4); new names do work. So each
gun gets copies of the two tables and of their per-direction metadata under new names of the same length, with a FIRE_POS and a muzzle
flash per shot. The animations stay the game's. Nothing of the stock barge changes.

data/gun_models.json, a gun's "volley": {"tag": five letters, "shots": [[dx, dy], ...] in metres from the barrel's axis, "spacing": seconds}
"""
import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import gamepack  # noqa: E402

SEP = chr(92)
TAG = re.compile(rb"([\x04-\x20])\x00([A-Z_]{4,32})")
SIDES = ("left", "right")
STOCK_TABLE = "zeppelin01_dlc25_cannon_{}"
SKELETON = "zeppelin01_cannon"
BIN = "animations/database/battle/bin/{}.bin"
_cache = {}


def game_file(path):
    target = path.replace("/", SEP).lower()
    if target in _cache:
        return _cache[target]
    found = None
    for pack in sorted(gamepack.DATA.glob("*.pack")):
        if pack.name.startswith(("anim", "data")) and not pack.name.endswith("_dds.pack"):
            for _, blob in gamepack.entries(pack, lambda n: n.lower() == target):
                found = blob
    if found is None:
        raise SystemExit(f"{path} is not in the game's packs")
    _cache[target] = found
    return found


def split(meta):
    version, count = struct.unpack_from("<II", meta, 0)
    starts, pos = [], 8
    while True:
        m = TAG.search(meta, pos)
        if not m:
            break
        if m.group(1)[0] == len(m.group(2)):
            starts.append(m.start())
            pos = m.end()
        else:
            pos = m.start() + 1
    if len(starts) != count or (starts and starts[0] != 8):
        raise SystemExit(f"unexpected .anm.meta: {count} entries, found {len(starts)}")
    return version, [meta[a:b] for a, b in zip(starts, starts[1:] + [len(meta)])]


def name_of(entry):
    return entry[2:2 + struct.unpack_from("<H", entry, 0)[0]]


def at_time(entry, seconds):
    new = bytearray(entry)
    struct.pack_into("<ff", new, 2 + len(name_of(entry)) + 4, seconds, seconds)
    return new


def volley_meta(meta, shots, spacing):
    """The metadata with one FIRE_POS and one flash per shot, at the barrels' offsets, one after another."""
    version, entries = split(meta)
    fire_at = next(i for i, e in enumerate(entries) if name_of(e) == b"FIRE_POS")
    flash_at = next(i for i, e in enumerate(entries) if name_of(e) == b"EFFECT")
    fire, flash = entries[fire_at], entries[flash_at]
    start = struct.unpack_from("<f", fire, 2 + len(b"FIRE_POS") + 4)[0]
    x, y, z = struct.unpack_from("<3f", fire, len(fire) - 12)
    flash_z = flash.index(struct.pack("<f", -2.25))     # the flash's position in the cannon's bone: x, y, -2.25
    fx, fy = struct.unpack_from("<2f", flash, flash_z - 8)
    new_fires, new_flashes = [], []
    for n, (dx, dy) in enumerate(shots):
        when = start + n * spacing
        one = at_time(fire, when)
        struct.pack_into("<3f", one, len(fire) - 12, x + dx, y + dy, z)
        new_fires.append(bytes(one))
        one = at_time(flash, when)
        struct.pack_into("<2f", one, flash_z - 8, fx + dx, fy + dy)
        new_flashes.append(bytes(one))
    others = [e for i, e in enumerate(entries) if i not in (fire_at, flash_at)]
    out = new_fires + new_flashes + others
    return struct.pack("<II", version, len(out)) + b"".join(out)


def animpack(files_):
    """The .bin tables among the pack's files as one .animpack in the same folder: the game registers tables from these.
    The format: u32 count, then for each file u16 name length, name, u32 size, bytes. {pack path: bytes} of the new file, or {}."""
    prefix = BIN.format("").removesuffix(".bin").replace("/", SEP)
    bins = sorted(k for k in files_ if k.lower().startswith(prefix.lower()) and k.lower().endswith(".bin"))
    if not bins:
        return {}
    out = bytearray(struct.pack("<I", len(bins)))
    for key in bins:
        name = key.replace(SEP, "/").encode("ascii")
        out += struct.pack("<H", len(name)) + name + struct.pack("<I", len(files_[key])) + files_[key]
    return {prefix + "!tww3_mtb_tables.animpack": bytes(out)}


def table_name(tag, side):
    return STOCK_TABLE.format(side).replace("zeppelin01", f"zep{tag}01")


def rows(volley):
    """battle_animations_table rows of a gun's two tables."""
    return [{"key": table_name(volley["tag"], side), "skeleton": SKELETON} for side in SIDES]


def files(volley):
    """{pack path: bytes}: the .bin of both sides and the renamed metadata."""
    tag = volley["tag"]
    if len(tag) != 5:
        raise SystemExit(f"tag {tag}: must be 5 letters, so that the names in the .bin keep their length")
    out = {}
    for side in SIDES:
        stock = STOCK_TABLE.format(side)
        table = game_file(BIN.format(stock))
        pattern = rb"animations/[A-Za-z0-9_/.\-]+?/cannon_" + side.encode() + rb"_fire_[a-z0-9_]+\.anm\.meta"
        paths = sorted({m.decode() for m in re.findall(pattern, table)})
        if not paths:
            raise SystemExit(f"{stock}: no per-direction metadata")
        for path in paths:
            renamed = path.replace(f"/cannon_{side}_", f"/z{tag}_{side}_")
            if len(renamed) != len(path):
                raise SystemExit("name length")
            table = table.replace(path.encode(), renamed.encode())
            out[renamed.replace("/", SEP)] = volley_meta(game_file(path), volley["shots"], volley["spacing"])
        name = table_name(tag, side)
        table = table.replace(stock.encode(), name.encode(), 1)
        out[BIN.format(name).replace("/", SEP)] = table
    return out
