"""Checks the crew's hire in src/tww3_mtb_crew.lua as built, without the game: a fake campaign. Needs lupa: python tools/hire_offline.py

Reads the module out of build/campaign/pack/tww3_mtb_campaign.pack, so py -3.14 tools/build.py comes first. Each case stands alone.
The buildings are named by the level of the mod they stand for (mod_key of the author's tree: crew_weapons_1); their keys in the game come from
build/tree/tree_rows.json (the tree gives most of them new keys, data/tree_port.json В1).
A load is a new module on the same saved values and treasury: nothing may be taken or given by it.
"""
import json
import sys
from pathlib import Path

import lupa

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import pfh5  # noqa: E402

PACK = REPO / "build" / "campaign" / "pack" / "tww3_mtb_campaign.pack"
SEP = chr(92)

FAKE = r'''
saved, gold, turn, human, moves = saved or {}, gold or 10000, turn or 5, human == nil and true or human, 0
local faction = {}
function faction:is_human() return human end
function faction:treasury() return gold end
cm = {}
function cm:get_saved_value(k) return saved[k] end
function cm:set_saved_value(k, v) saved[k] = v end
function cm:turn_number() return turn end
function cm:get_faction() return faction end
function cm:treasury_mod(f, n) gold = gold + n; moves = moves + 1 end
function cm:get_local_faction_name() return 'wh3_dlc25_dwf_malakai' end
core = {}
function core:svr_save_string() end
function core:get_tm() return {real_callback = function() end} end
function core:add_listener() end
function ModLog() end
_G.tww3_mtb_campaign = {when_ready = function() end, file_log = function() end, find_malakai = function() return nil end}
'''
PREFIX = "wh3_dlc25_dwarf_spirit_of_grungni_"
TREE = json.loads((REPO / "build" / "tree" / "tree_rows.json").read_text(encoding="utf-8"))
KEYS = {r["mod_key"]: r["key"] for r in TREE["levels"] if r["mod_key"]}


def key(short):
    """The game's key of the tree's level that stands for the mod's level short."""
    return KEYS[short]


def source():
    files, _ = pfh5.read_pack(PACK.read_bytes())
    return files[f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew.lua"].decode("utf-8")


SRC = source()
failed = 0


def case(name, body):
    global failed
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(FAKE)
    load = lua.eval("function(src) local f, e = load(src); if not f then error(e) end; f(); local M = tww3_mtb_crew; M.status = 'applied'; M.apply = function() M.status = 'applied'; return true end; return M end")
    lua.globals().the_load = lambda: load(SRC)
    load(SRC)

    def run(code):
        return lua.execute(code)
    try:
        body(run)
        print("ok  ", name)
    except AssertionError as e:
        failed += 1
        print("FAIL", name, e)


def built(run, *shorts):
    run("local M = tww3_mtb_crew; " + " ".join(f"saved['mtb_crew_built'] = (saved['mtb_crew_built'] or '') .. '{key(s)}@1,'" for s in shorts))


def num(run, code):
    return run("return " + code)


def expect(run, code, want):
    got = num(run, code)
    assert got == want, f"{code}: {got!r}, wanted {want!r}"


def price(run, group, option):
    return num(run, f"tww3_mtb_crew.hire_of('{group}', '{option}')")


def order_paid(run):
    built(run, "airship_hull_2", "crew_weapons_1")
    cost = price(run, "rifles", "quarrellers")
    assert cost > 0, "a price"
    expect(run, "tww3_mtb_crew.choose('rifles', 'quarrellers')", True)
    expect(run, "gold", 10000 - cost)
    expect(run, "saved['mtb_crew_order_paid_rifles']", cost)
    expect(run, "tww3_mtb_crew.get().rifles", "empty")


def taken_back(run):
    built(run, "airship_hull_2", "crew_weapons_1")
    run("tww3_mtb_crew.choose('rifles', 'quarrellers')")
    expect(run, "tww3_mtb_crew.choose('rifles', 'empty')", True)
    expect(run, "gold", 10000)
    expect(run, "tww3_mtb_crew.orders().rifles", None)
    # the change of this turn is used, and a second back gives nothing
    run("tww3_mtb_crew.choose('rifles', 'empty')")
    expect(run, "gold", 10000)


def carried_out(run):
    built(run, "airship_hull_2", "crew_weapons_1")
    cost = price(run, "rifles", "quarrellers")
    run("tww3_mtb_crew.choose('rifles', 'quarrellers')")
    run("turn = turn + 1; tww3_mtb_crew.carry_out()")
    expect(run, "tww3_mtb_crew.get().rifles", "quarrellers")
    expect(run, "gold", 10000 - cost)
    expect(run, "saved['mtb_crew_order_paid_rifles']", False)


def replaced_and_back(run):
    built(run, "airship_hull_2", "crew_weapons_1", "crew_weapons_2")
    a, b = price(run, "rifles", "quarrellers"), price(run, "rifles", "thunderers")
    run("tww3_mtb_crew.choose('rifles', 'quarrellers'); turn = turn + 1; tww3_mtb_crew.carry_out()")
    run("tww3_mtb_crew.choose('rifles', 'thunderers'); turn = turn + 1; tww3_mtb_crew.carry_out()")
    expect(run, "gold", 10000 - a - b)
    run("tww3_mtb_crew.choose('rifles', 'quarrellers'); turn = turn + 1; tww3_mtb_crew.carry_out()")
    expect(run, "gold", 10000 - a - b - a)


def empty_free(run):
    built(run, "airship_hull_2", "mtb_guns_1")
    run("saved['mtb_crew_cannons'] = 'stock'; saved['mtb_crew_built'] = saved['mtb_crew_built'] .. '" + key("support_radius_1") + "@1," + key("mtb_guns_2") + "@1,'")
    expect(run, "tww3_mtb_crew.hire_of('cannons', 'empty')", 0)
    expect(run, "tww3_mtb_crew.choose('cannons', 'empty')", True)
    expect(run, "gold", 10000)


def no_gold(run):
    built(run, "airship_hull_2", "crew_weapons_1")
    run("gold = 1")
    ok, why = run("return tww3_mtb_crew.choose('rifles', 'quarrellers')")
    assert ok is False and "no gold" in why, (ok, why)
    expect(run, "gold", 1)
    expect(run, "tww3_mtb_crew.orders().rifles", None)
    expect(run, "tww3_mtb_crew.changed('rifles')", False)


def load_changes_nothing(run):
    built(run, "airship_hull_2", "crew_weapons_1")
    cost = price(run, "rifles", "quarrellers")
    run("tww3_mtb_crew.choose('rifles', 'quarrellers')")
    run("moves = 0; the_load()")
    expect(run, "moves", 0)
    expect(run, "gold", 10000 - cost)
    expect(run, "tww3_mtb_crew.orders().rifles", "quarrellers")
    # after the load the order still takes back in full, once
    run("tww3_mtb_crew.choose('rifles', 'empty'); tww3_mtb_crew.choose('rifles', 'empty')")
    expect(run, "gold", 10000)


def ai_free(run):
    run("human = false; saved = {}")
    expect(run, "tww3_mtb_crew.hire_of('rifles', 'quarrellers')", 0)


def stock_free(run):
    run("tww3_mtb_crew.status = 'stock: no memreader'")
    expect(run, "tww3_mtb_crew.hire_of('rifles', 'quarrellers')", 0)


def building_gone(run):
    built(run, "airship_hull_2", "crew_weapons_1")
    cost = price(run, "rifles", "quarrellers")
    assert cost > 0
    run("tww3_mtb_crew.choose('rifles', 'quarrellers')")
    expect(run, "gold", 10000 - cost)
    # the same path the reconcile takes: the order goes with its building, the gold comes back
    run("local M = tww3_mtb_crew; saved['mtb_crew_built'] = '" + key("airship_hull_2") + "@1,'")
    run("""
    local forces = {num_items = function() return 1 end, item_at = function() return {horde_details = function() return {is_null_interface = function() return false end,
      military_force_slot_list = function() return {num_items = function() return 1 end, item_at = function() return {has_building = function() return true end, building = function() return '""" + key("airship_hull_2") + """' end} end} end} end} end}
    local f = cm:get_faction()
    f.military_force_list = function() return forces end
    saved['mtb_crew_built'] = '""" + key("airship_hull_2") + """@1,""" + key("crew_weapons_1") + """@1'
    turn = turn + 1
    tww3_mtb_crew.reconcile()
    """)
    expect(run, "tww3_mtb_crew.orders().rifles", None)
    expect(run, "gold", 10000)


case("an order takes the price at once, the crew does not change yet", order_paid)
case("taking the order back returns all of it, once", taken_back)
case("carried out: nothing more, nothing back", carried_out)
case("what stood is not paid back; going back to it is paid again", replaced_and_back)
case("an empty option is free", empty_free)
case("too little gold: no order, no change used", no_gold)
case("a load neither takes nor gives", load_changes_nothing)
case("the AI pays nothing", ai_free)
case("without memreader Plus nothing", stock_free)
case("a building that goes takes the order and gives the gold back", building_gone)
print("failed:", failed)
sys.exit(1 if failed else 0)
