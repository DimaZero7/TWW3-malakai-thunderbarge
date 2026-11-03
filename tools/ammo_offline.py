"""Checks src/tww3_mtb_ammo.lua as built, without the game: a fake memory, a fake battle. Needs lupa: python tools/ammo_offline.py

Reads the module out of build/campaign/pack/tww3_mtb_campaign.pack, so py -3.14 tools/build.py comes first. Each case stands alone.
"""
import re
import struct
import sys
from pathlib import Path

import lupa

REPO = Path(__file__).resolve().parent.parent
PACK = REPO / "build" / "campaign" / "pack" / "tww3_mtb_campaign.pack"

FAKE = r'''
mem, T, repeats, logged = {}, 0, {}, {}
local function P(name) mem[name] = mem[name] or {}; return name end
local function S(p, o, v) mem[P(p)][o] = v end
_G.P, _G.S = P, S
local mr = {}
function mr.read_pointer(p, o) local v = mem[p] and mem[p][o or 0]; if v == nil then error("bad read " .. tostring(p) .. " " .. tostring(o)) end; return v end
function mr.read_int32(p, o) return mem[p][o] or 0 end
mr.read_uint32, mr.read_float = mr.read_int32, mr.read_int32
function mr.read_uint8(p, o) local v = mem[p][o]; if v == true then return 1 elseif not v then return 0 end; return v end
function mr.read_string(p, o) return mem[p][o] end
function mr.is_null(p) return p == nil or p == "null" end
function mr.uint32(x) return x end
function mr.write(p, o, v) writes = writes + 1; mem[p][o] = v end
function mr.read_vector(p, o) if broken then error("broken") end; return mem[p][o] end
function mr.add(p, o) return p end
function mr.find_pattern(s) if bad_pattern then return nil, 0 end; return "root", 1 end
function mr.read_chain(t) return "root" end
function mr.map_find_key(t, key) local i = mem[t].index[key]; if not i then return nil end; S("node_" .. key, 0x20, i); return "node_" .. key end
function mr.read_array(t) return #mem[t].rows, "data_" .. t end
function mr.ud_topointer(u) return "script_unit" end
_G.fake_mr = mr
function ModLog(s) logged[#logged + 1] = s end
local function row_table(name, keys)
  S(name, "index", {}); mem[name].rows = {}
  local data = P("data_" .. name)
  for i, key in ipairs(keys) do
    if name ~= "land_units" then S(key, 8, key) end; mem[name].index[key] = i - 1; mem[name].rows[i] = key; S(data, (i - 1) * 8, key)
  end
end
_G.row_table = row_table
local unit = {ammo_left = function() return mem.bu[0x3d90] end, type = function() return "mtb_dwf_cha_malakai_thunderbarge" end}
local list1 = {count = function() return 1 end, item = function() return unit end}
local armies = {count = function() return 1 end, item = function() return {units = function() return list1 end} end}
local alliances = {count = function() return 1 end, item = function() return {armies = function() return armies end} end}
bm = {
  alliances = function() return alliances end,
  time_elapsed_ms = function() return T end,
  get_current_phase_name = function() return "Deployment" end,
  register_phase_change_callback = function() end,
  repeat_callback = function(self, f, i, name) repeats[name] = f end,
  remove_callback = function(self, name) repeats[name] = nil end,
}
S("script_unit", 8, "bu"); S("script_unit", 0, "null"); S("script_unit", 0x10, "null"); S("bu", 0x50, "mtb_dwf_cha_malakai_thunderbarge")
S("bu", 0x30, "battle"); S("battle", 0x440, "world"); S("world", 8, "battle"); S("world", 0x1c8, "mgr"); S("mgr", 0x10, {})
S("bu", 0x114, 29); S("bu", 0x118, "men")
for k, v in pairs({[0x3d90] = 1160, [0x3d94] = 1160, [0x3d98] = 1160, [0x3d9c] = 0, [0x3da0] = 1450, [0x3da4] = 1450, [0x3da8] = 1450, [0x3dac] = 1}) do S("bu", k, v) end
S("root", 3, 0); S("root", 13, 0); S("root", 0, "app"); S("app", 0, "db"); P("db")
'''


def config_of(source):
    """The generated CONFIG as Lua text, the module itself."""
    match = re.search(r"^local CONFIG = .*$", source, re.M)
    return match.group(0)


def module_from_pack():
    sys.path.insert(0, str(REPO / "tools"))
    import pfh5
    files, _ = pfh5.read_pack(PACK.read_bytes())
    return files["script" + chr(92) + "battle" + chr(92) + "mod" + chr(92) + "tww3_mtb_ammo.lua"].decode("utf-8")


class World:
    def __init__(self, source, choice):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute("writes = 0; bad_pattern = false; broken = false; memreader_on = true")
        self.lua.execute(FAKE)
        self.source = source
        self.choice = choice
        self.setup()

    def run(self, code):
        return self.lua.execute(code)

    def setup(self):
        lua = self.lua
        config = lua.execute(config_of(self.source).replace("local CONFIG =", "return"))
        keys = []
        for group in config["groups"].values():
            for option in group["options"].values():
                for row in option["rows"].values():
                    keys.append((row["key"], row["secondary"]))
        names = ["wh3_dlc25_dwf_thunderbarge_grudge_raker_grungni", "wh3_dlc25_dwf_thunderbarge_cannon"] + [k for k, _ in keys]
        quoted = ",".join('"' + n + '"' for n in names)
        lua.execute(f'row_table("missile_weapons", {{{quoted}}}); row_table("land_units", {{"mtb_dwf_cha_malakai_thunderbarge"}})')
        lua.execute('S("wh3_dlc25_dwf_thunderbarge_grudge_raker_grungni", 0x30, true); S("wh3_dlc25_dwf_thunderbarge_cannon", 0x30, false)')
        for key, secondary in keys:
            lua.execute(f'S("{key}", 0x30, {str(secondary).lower()}); S("{key}", 0x28, "{key}_list"); S("{key}_list", 0, "{key}_proj")')
        # The table scan of the module: slot 0 and 1 hold the two tables.
        lua.execute('mem.db[0] = "missile_weapons"; mem.db[0x38] = "land_units"')
        lua.execute('for i = 2, 1811 do mem.db[i * 0x38] = "null" end')
        lua.execute('mem.missile_weapons[0x58] = "name_w"; S("name_w", 0, "missile_weapons"); mem.land_units[0x58] = "name_l"; S("name_l", 0, "land_units")')
        seats = {"rifles": 12, "cannons": 2, "cupolas": 2, "bombs": 4}
        i = 0
        real = {"rifles": [f"ap_crew_{s}_{n}" for s in ("left", "right") for n in ("0", "1", "2", "3", "upper_0", "upper_1")],
                "cannons": ["ap_cannon_left", "ap_cannon_right"], "cupolas": ["ap_cupola_front", "ap_cupola_rear"],
                "bombs": ["ap_bomb_bay_left_front", "ap_bomb_bay_left_rear", "ap_bomb_bay_right_front", "ap_bomb_bay_right_rear"]}
        self.men = {}
        for group, count in seats.items():
            weapon = self.choice.get(group)
            for n in range(count):
                man = f"{group}{n}"
                self.men.setdefault(group, []).append(man)
                lua.execute(f'S("men", {i * 8}, "{man}"); S("{man}", 0xb70, "seat_{man}"); S("seat_{man}", 0, "per_{man}"); S("seat_{man}", 8, "name_{man}");'
                            f'S("name_{man}", 0, "{real[group][n]}"); S("per_{man}", 0x38, "st_{man}"); S("st_{man}", 0x20, "{weapon}")')
                i += 1
        while i < 29:
            man = f"deck{i}"
            lua.execute(f'S("men", {i * 8}, "{man}"); S("{man}", 0xb70, "seat_{man}"); S("seat_{man}", 0, "per_{man}"); S("seat_{man}", 8, "name_{man}");'
                        f'S("name_{man}", 0, "ap_deck"); S("per_{man}", 0x38, "null")')
            i += 1

    def load(self, memreader=True):
        self.lua.execute("_G.memreader_plus = " + ("fake_mr" if memreader else "nil"))
        self.lua.execute(self.source)

    def fire(self, group, man=0, number=1, record=None, state=0):
        """Puts `number` new projectiles of a man into the game's list; each one takes 1 from the pool only for the first of a shot."""
        weapon = self.choice[group]
        record = record or f"{weapon}_proj"
        self.count = getattr(self, "count", 0) + 1
        for n in range(number):
            name = f"p{self.count}_{n}"
            self.lua.execute(f'S("{name}", 0xc0, {state}); S("{name}", 0x11c, 0); S("{name}", 0x20, "{group}{man}"); S("{name}", 0x90, "{record}");'
                             f'table.insert(mem.mgr[0x10], "{name}")')
        if state == 0 and record == f"{weapon}_proj":
            self.lua.execute("mem.bu[0x3d90] = mem.bu[0x3d90] - 1")

    def tick(self, seconds=0.1):
        self.lua.execute(f'T = T + {seconds * 1000}; if repeats.tww3_mtb_ammo then repeats.tww3_mtb_ammo() end')

    def get(self, code):
        return self.lua.execute("return " + code)


def check(name, condition, detail=""):
    print(("ok  " if condition else "FAIL"), name, detail)
    if not condition:
        check.failed += 1


check.failed = 0

STOCK = {"rifles": "mtb_w_rifles_stock", "cannons": "mtb_w_cannons_stock", "cupolas": "mtb_w_cupolas_stock", "bombs": "mtb_w_bombs_stock"}


def main():
    source = module_from_pack()
    w = World(source, STOCK)
    w.load()
    check("running", w.get("tww3_mtb_ammo.status") == "running", w.get("tww3_mtb_ammo.status"))
    check("pool is the sum", w.get("mem.bu[0x3d90]") == 120 and w.get("mem.bu[0x3d98]") == 120, w.get("mem.bu[0x3d90]"))
    check("second pool empty, finite", w.get("mem.bu[0x3da0]") == 0 and w.get("mem.bu[0x3dac]") == 0)
    check("rifles on the first pool", w.get('mem.mtb_w_rifles_stock[0x30]') is False)
    w.lua.execute('tww3_mtb_ammo.set_ammo("cannons", 2); tww3_mtb_ammo.set_ammo("rifles", 3)')
    check("pool follows set_ammo", w.get("mem.bu[0x3d90]") == 55, w.get("mem.bu[0x3d90]"))
    w.fire("cannons", 0)
    w.tick()
    w.fire("rifles", 0, 3)
    w.fire("rifles", 1, 2)       # one pellet of this shot is late
    w.tick()
    w.fire("rifles", 1, 1, state=2)   # not flying: a hit, not a shot
    w.tick()
    check("three pellets are one shot", w.get("tww3_mtb_ammo.read().rifles.shots") == 2, w.get("tww3_mtb_ammo.report()"))
    w.lua.execute('table.insert(mem.mgr[0x10], "late"); S("late", 0xc0, 0); S("late", 0x11c, 0); S("late", 0x20, "rifles1"); S("late", 0x90, "mtb_w_rifles_stock_proj")')
    w.tick()
    check("the late pellet is the same shot", w.get("tww3_mtb_ammo.read().rifles.shots") == 2)
    w.fire("cannons", 1)
    w.tick()
    check("cannons dry", w.get("tww3_mtb_ammo.read().cannons.ammo") == 0 and w.get("tww3_mtb_ammo.read().cannons.dry_at") is not None)
    check("their row on the empty pool", w.get("mem.mtb_w_cannons_stock[0x30]") is True)
    check("the others stay", w.get("mem.mtb_w_cupolas_stock[0x30]") is False and w.get("mem.mtb_w_rifles_stock[0x30]") is False)
    w.fire("rifles", 2, 3)
    w.fire("rifles", 3, 3)
    w.fire("rifles", 4, 3)       # one more than left: no negative count
    w.tick()
    check("no negative count", w.get("tww3_mtb_ammo.read().rifles.ammo") == 0, w.get("tww3_mtb_ammo.report()"))
    check("the overshoot is counted", w.get("tww3_mtb_ammo.read().rifles.shots") == 5)
    check("pool equals what is left", w.get("mem.bu[0x3d90]") == 50, w.get("mem.bu[0x3d90]"))
    check("engine count", w.get("tww3_mtb_ammo.engine") == 7, w.get("tww3_mtb_ammo.engine"))
    w.fire("bombs", 0, record="something_else")
    w.tick()
    check("what a bomb breaks into is not a shot", w.get("tww3_mtb_ammo.read().bombs.shots") == 0 and w.get("tww3_mtb_ammo.others.bombs") == 1)
    w.lua.execute('tww3_mtb_ammo.set_ammo("cannons", 3)')
    w.tick()
    check("new ammunition, fires again", w.get("mem.mtb_w_cannons_stock[0x30]") is False and w.get("tww3_mtb_ammo.read().cannons.dry_at") is None)
    w.lua.execute("mem.bu[0x3d90] = mem.bu[0x3d90] + 30")
    w.tick()
    check("the game's refill goes to the groups", w.get("mem.bu[0x3d90]") > 53 and w.get("tww3_mtb_ammo.read().bombs.ammo") == 20, w.get("tww3_mtb_ammo.report()"))
    for _ in range(5):
        w.lua.execute("broken = true")
        w.tick()
    check("failure in battle gives the stock back", w.get("tww3_mtb_ammo.status").startswith("off:") and w.get("mem.bu[0x3dac]") == 1 and w.get("mem.bu[0x3da0]") == 1450
          and w.get("mem.mtb_w_rifles_stock[0x30]") is True and w.get("repeats.tww3_mtb_ammo") is None, w.get("tww3_mtb_ammo.status"))

    w = World(source, STOCK)
    w.load(memreader=False)
    check("no memreader: off, no writes", w.get("tww3_mtb_ammo.status").startswith("off: memreader") and w.get("writes") == 0)

    w = World(source, STOCK)
    w.lua.execute("bad_pattern = true")
    w.load()
    check("no pattern: off, no writes", "database pattern" in w.get("tww3_mtb_ammo.status") and w.get("writes") == 0, w.get("tww3_mtb_ammo.status"))

    w = World(source, dict(STOCK, cannons="not_ours"))
    w.lua.execute('S("not_ours", 8, "not_ours")')
    w.load()
    check("a foreign weapon: off, pools untouched", w.get("tww3_mtb_ammo.status").startswith("off:") and w.get("mem.bu[0x3d90]") == 1160 and w.get("mem.bu[0x3dac]") == 1, w.get("tww3_mtb_ammo.status"))

    w = World(source, STOCK)
    w.lua.execute("mem.bu[0x3d90] = 2320; mem.bu[0x3d94] = 2320; mem.bu[0x3d98] = 2320")
    w.load()
    check("an effect doubling the pool doubles the groups", w.get("tww3_mtb_ammo.read().rifles.start") == 80 and w.get("mem.bu[0x3d90]") == 240, w.get("mem.bu[0x3d90]"))

    w = World(source, dict(STOCK, cannons="mtb_w_cannons_stock", bombs=None))
    w.lua.execute('for i = 0, 3 do mem["st_bombs" .. i][0x20] = "null" end')
    w.load()
    check("an empty group has no count", w.get("tww3_mtb_ammo.read().bombs") is None and w.get("mem.bu[0x3d90]") == 100, w.get("mem.bu[0x3d90]"))

    print("failed:", check.failed)
    return 1 if check.failed else 0


if __name__ == "__main__":
    sys.exit(main())
