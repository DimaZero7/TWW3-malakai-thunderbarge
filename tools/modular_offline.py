"""The seat writer of the modular test pack without the game: plain python with lupa (python tools/modular_offline.py).

Reads src/tww3_mtb_crew.lua as tools/modular_test.py patched it into build/modular/test/tww3_mtb_modular_test.pack and runs it against a fake
memreader Plus: the database root, the table list, battle_personalities / land_units / mounts as maps of rows, the land unit's seat vector of
32 elements built from the pack's junction rows (in their order: two seats on three points) and its mount pointer. Cases:
  1. the first apply: every crew seat holds the row of its option, every detail seat the row of its test state, the mount row is the hull's
     look (harpoon x stern boards); 2. again: the same; 3. every detail switched: rows and mount follow; 4. a crew change keeps the details;
  5. a detail row missing from the table: nothing written, status stock; 6. the stock 29-seat vector: refused, nothing written.
"""
import json
import re
import sys
from pathlib import Path

import lupa

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import dbtable  # noqa: E402
import pfh5  # noqa: E402

TEST = REPO / "build" / "modular" / "test"
SEP = chr(92)
UNIT = "mtb_dwf_cha_malakai_thunderbarge"

FAKE = r'''
mem, str, maps, LOG, saved, writes = {}, {}, {}, {}, {}, 0
local next_addr = 0x100000
function alloc(n) local a = next_addr; next_addr = next_addr + (n or 0x1000); return a end
ROOT, MARK, VT, APP, DB = alloc(), alloc(), alloc(), alloc(), alloc(0x80000)
mem[ROOT + 7] = APP; mem[APP] = DB; mem[VT] = MARK
mr = {}
function mr.find_pattern(p) if p == PAT_ROOT then return ROOT, 1 elseif p == PAT_MARK then return MARK, 1 end return nil, 0 end
function mr.add(a, n) return a + n end
function mr.read_int32(a, off) return 0 end
function mr.read_pointer(a, off) return mem[a + (off or 0)] or 0 end
function mr.read_uint32(a, off) return mem[a + (off or 0)] or 0 end
function mr.is_null(p) return p == nil or p == 0 end
function mr.read_chain(p, ...) for _, off in ipairs({...}) do p = mem[p + off] or 0 end return p end
function mr.read_string(p, off) return str[p + (off or 0)] end
function mr.map_find_key(a, key) return maps[a] and maps[a][key] end
function mr.read_array(t, off) return mem[t + off], mem[t + off + 8] end
function mr.write(p, off, v) mem[p + off] = v; writes = writes + 1 end
_G.memreader_plus = mr
tables_by_name = {}
function make_table(slot, name, keys)
  local t = alloc()
  mem[DB + slot * 0x38] = t
  mem[t] = VT
  local namep = alloc(64); str[namep] = name; mem[t + 0x58] = namep
  local data = alloc(8 * (#keys + 1))
  mem[t + 0x08], mem[t + 0x10] = #keys, data
  maps[t + 0x28] = {}
  local rows = {}
  for i, key in ipairs(keys) do
    local r = alloc(0x200); str[r + 8] = key
    mem[data + (i - 1) * 8] = r
    local node = alloc(64); mem[node + 0x20] = i - 1
    maps[t + 0x28][key] = node
    rows[key] = r
  end
  tables_by_name[name] = {t = t, rows = rows}
  return rows
end
function seat_vector(lu, list)
  local data = alloc(0x18 * (#list + 1))
  mem[lu + 0x48], mem[lu + 0x4c], mem[lu + 0x50] = #list, #list, data
  for i, item in ipairs(list) do
    local namep = alloc(64); str[namep] = item[1]
    mem[data + (i - 1) * 0x18] = tables_by_name.battle_personalities.rows[item[2]] or error('no row ' .. item[2])
    mem[data + (i - 1) * 0x18 + 8] = namep
  end
  return data
end
local faction = {}
function faction:is_human() return true end
function faction:treasury() return 10000 end
cm = {}
function cm:get_saved_value(k) return saved[k] end
function cm:set_saved_value(k, v) saved[k] = v end
function cm:turn_number() return 5 end
function cm:get_faction() return faction end
function cm:get_local_faction_name() return 'wh3_dlc25_dwf_malakai' end
function cm:show_message_event() end
function cm:treasury_mod() end
core = {}
function core:svr_save_string() end
function core:get_tm() return {real_callback = function() end} end
function core:add_listener() end
function ModLog() end
_G.tww3_mtb_campaign = {when_ready = function() end, file_log = function(s) LOG[#LOG + 1] = s end, find_malakai = function() return nil end}
'''

# After the module ran: what the vector holds, by element.
DUMP = r'''
local lu = tables_by_name.land_units.rows[LAND_UNIT]
local data = mem[lu + 0x50]
local key_of = {}
for k, r in pairs(tables_by_name.battle_personalities.rows) do key_of[r] = k end
local mount_of = {}
for k, r in pairs(tables_by_name.mounts.rows) do mount_of[r] = k end
local out = {}
for i = 0, mem[lu + 0x4c] - 1 do out[#out + 1] = str[mem[data + i * 0x18 + 8]] .. '=' .. tostring(key_of[mem[data + i * 0x18]]) end
out[#out + 1] = 'MOUNT=' .. tostring(mount_of[mem[lu + 0x110]])
return table.concat(out, '\n')
'''


def main():
    files, _ = pfh5.read_pack((TEST / "tww3_mtb_modular_test.pack").read_bytes())
    config = json.loads((TEST / "test_config.json").read_text(encoding="utf-8"))
    lay = json.loads((REPO / "data" / "db_layouts.json").read_text(encoding="utf-8"))

    def table(name):
        return dbtable.decode(files[f"db{SEP}{name}_tables{SEP}!tww3_mtb"], [tuple(f) for f in lay[name]["fields"]])
    source = files[f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew.lua"].decode("utf-8")
    # the sim only: the module's CONFIG made visible
    source = re.sub(r"(?m)^(local CONFIG = \{.*)$", r"\1\n_G.MTB_CONFIG = CONFIG", source, count=1)
    junctions = [(r["riders_attachment_point"], r["battle_personality"]) for r in table("land_units_to_battle_personalities_junctions") if r["land_unit"] == UNIT]
    keys = sorted({r["key"] for r in table("battle_personalities")} | {k for _, k in junctions} | set(re.findall(r'"([a-z0-9_]+)"', source)))
    mounts = sorted({r["key"] for r in table("mounts")})
    land_unit = next(r for r in table("land_units") if r["key"] == UNIT)
    failed = []

    def fresh(seat_list=junctions, drop=None, mount=land_unit["mount"]):
        lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        g = lua.globals()
        g.PAT_ROOT = re.search(r"local DB_ROOT = '([^']+)'", source).group(1)
        g.PAT_MARK = re.search(r"local TABLE_MARK = '([^']+)'", source).group(1)
        g.LAND_UNIT = UNIT
        lua.execute(FAKE)
        make = lua.eval("make_table")
        make(0, "land_units", lua.table_from([UNIT]))
        make(1, "battle_personalities", lua.table_from([k for k in keys if k != drop]))
        make(2, "mounts", lua.table_from(mounts))
        lu = lua.eval(f"tables_by_name.land_units.rows['{UNIT}']")
        if drop is None or drop not in {k for _, k in seat_list}:
            lua.eval("seat_vector")(lu, lua.table_from([lua.table_from(x) for x in seat_list]))
        lua.execute(f"mem[{lu} + 0x110] = tables_by_name.mounts.rows['{mount}']")
        loader = lua.eval("function(src) local f, e = load(src); if not f then error(e) end; f(); return tww3_mtb_crew end")
        loader(source)
        return lua

    def state(lua):
        return dict(line.split("=", 1) for line in lua.execute(DUMP).split("\n"))

    def vector(lua):
        return lua.execute(DUMP).split("\n")[:-1]

    def expect(name, good, note=""):
        print(("ok   " if good else "FAIL ") + name + (f": {note}" if note and not good else ""))
        if not good:
            failed.append(name)

    def wanted(lua, parts, harpoon_on):
        """{element text} the vector must hold for the current choice and these detail states."""
        cfg = lua.eval("_G.MTB_CONFIG")
        choice = lua.eval("tww3_mtb_crew.get()")
        crew = {}
        for group, spec in cfg.groups.items():
            for seat in spec.seats.values():
                crew[seat] = cfg.seats[seat][choice[group]]
        out = []
        part_of = {p["seat"]: p for p in config["lua_parts"].values()}
        detail_rows = {p["on"] for p in config["lua_parts"].values()} | {p["off"] for p in config["lua_parts"].values()}
        seen = set()
        for ap, key in junctions:
            if key in detail_rows:
                name = next(n for n, p in config["lua_parts"].items() if key in (p["on"], p["off"]))
                out.append(f"{ap}={config['lua_parts'][name][parts[name]]}")
            elif ap in crew:
                out.append(f"{ap}={crew[ap]}")
            else:
                out.append(f"{ap}={key}")       # fixed: captain, thunderburner
            seen.add(ap)
        slots = sorted(n for n in config["parts"] if n not in config["lua_parts"] and parts[n] == "on")
        code = ("h" if harpoon_on else "n") + ("_" + "_".join(slots) if slots else "")
        return out, config["hull_mounts"][code]

    test_parts = dict(config["parts"])
    # 1. the first apply, the player's start crew (harpoon empty = the hull without it)
    lua = fresh()
    ok = lua.execute("return tww3_mtb_crew.apply()")
    status = lua.execute("return tww3_mtb_crew.status")
    want, mount = wanted(lua, test_parts, False)
    got = vector(lua)
    expect("1 apply: status applied", ok and status == "applied", f"{ok} {status} {list(lua.eval('LOG').values())}")
    expect("1 apply: 32 elements as wanted", got == want, f"{[(a, b) for a, b in zip(got, want) if a != b][:6]}")
    expect("1 apply: mount row", state(lua)["MOUNT"] == mount, f"{state(lua)['MOUNT']} != {mount}")
    expect("1 apply: details logged", any("written, details" in x for x in lua.eval("LOG").values()), list(lua.eval("LOG").values()))
    # 2. again
    before = got
    lua.execute("tww3_mtb_crew.apply()")
    expect("2 apply again: unchanged", vector(lua) == before)
    # 3. the test's crew and every detail switched
    for group, option in config["choice"].items():
        lua.execute(f"assert(tww3_mtb_crew.set('{group}', '{option}'))")
    want, mount = wanted(lua, test_parts, config["choice"]["harpoon"] == "on")
    expect("3 test crew: vector", vector(lua) == want, f"{[(a, b) for a, b in zip(vector(lua), want) if a != b][:6]}")
    expect("3 test crew: mount with harpoon and stern boards", state(lua)["MOUNT"] == mount, f"{state(lua)['MOUNT']} != {mount}")
    flipped = {n: ("off" if s == "on" else "on") for n, s in test_parts.items()}
    states = "{" + ", ".join(f"{k} = '{v}'" for k, v in flipped.items()) + "}"
    ok = lua.execute(f"return tww3_mtb_crew.set_parts({states})")
    want, mount = wanted(lua, flipped, config["choice"]["harpoon"] == "on")
    expect("3 every detail switched: vector", ok and vector(lua) == want, f"{[(a, b) for a, b in zip(vector(lua), want) if a != b][:6]}")
    expect("3 every detail switched: mount", state(lua)["MOUNT"] == mount, f"{state(lua)['MOUNT']} != {mount}")
    expect("3 parts() text", lua.execute("return tww3_mtb_crew.parts()") == " ".join(f"{k}={v}" for k, v in sorted(flipped.items())))
    # 4. a crew change keeps the details
    lua.execute("assert(tww3_mtb_crew.set('rifles', 'quarrellers'))")
    want, mount = wanted(lua, flipped, config["choice"]["harpoon"] == "on")
    expect("4 crew change keeps the details", vector(lua) == want, f"{[(a, b) for a, b in zip(vector(lua), want) if a != b][:6]}")
    bad = lua.execute("return tostring(select(2, tww3_mtb_crew.set_parts({nothing = 'on'})))")
    expect("4 unknown detail refused", "bad detail" in str(bad), bad)
    # 5. a detail row missing: nothing written
    missing = config["lua_parts"]["porthole"]["off"]
    lua = fresh(drop=missing)
    before = lua.execute(DUMP)
    ok = lua.execute("return tww3_mtb_crew.apply()")
    expect("5 missing detail row: refused", not ok and str(lua.execute("return tww3_mtb_crew.status")).startswith("stock"), lua.execute("return tww3_mtb_crew.status"))
    expect("5 missing detail row: nothing written", lua.execute(DUMP) == before and lua.execute("return writes") == 0)
    # 6. the stock vector of 29 seats
    stock29 = [x for x in junctions if not x[1].startswith("mtb_bp_part_")]
    lua = fresh(seat_list=stock29)
    ok = lua.execute("return tww3_mtb_crew.apply()")
    expect("6 a 29-seat vector: refused, nothing written", not ok and lua.execute("return writes") == 0, lua.execute("return tww3_mtb_crew.status"))
    print("offline:", "OK" if not failed else f"{len(failed)} failures")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
