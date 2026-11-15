"""Checks the crew's hire in src/tww3_mtb_crew.lua as built, without the game: a fake campaign. Needs lupa: python tools/hire_offline.py

Reads the module out of build/campaign/pack/tww3_mtb_campaign.pack, so py -3.14 tools/build.py comes first. Each case stands alone.
The buildings are named by the level of the mod they stand for (mod_key of the author's tree: crew_weapons_1); their keys in the game come from
build/tree/tree_rows.json (the tree gives most of them new keys, data/tree_port.json В1).
A load is a new module on the same saved values and treasury: nothing may be taken or given by it.
The cases «new panel» run with src/tww3_mtb_crew_ui.lua's switch on and the screen not started: the old order, upkeep and set() step aside for
the model, the seats follow the model's saved state, Malakai stands at the rail (docs/design/port-to-game.md 8.6). With the model itself:
py -3.10 tools/crew_bridge_offline.py.
Malakai's seats are checked by the MODEL their rows show (tools/seat_models.py), not by the rows' names; --break swap_models swaps the variants of
his rail rows and the helm crew's row in the read tables to show that check failing.
"""
import json
import sys
from pathlib import Path

import lupa

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import pfh5  # noqa: E402
import seat_models  # noqa: E402

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


FILES, _ = pfh5.read_pack(PACK.read_bytes())
SRC = FILES[f"script{SEP}campaign{SEP}mod{SEP}tww3_mtb_crew.lua"].decode("utf-8")
# the model each of the pack's seat rows shows (tools/seat_models.py; the game's own definitions are not read here: a stock one is unknown)
TABLES = seat_models.pack_tables(FILES, json.loads((REPO / "data" / "db_layouts.json").read_text(encoding="utf-8")))
if "--break" in sys.argv and sys.argv[sys.argv.index("--break") + 1:][:1] == ["swap_models"]:     # the model check must catch it
    seat_models.swap_malakai_variants(TABLES, ["mtb_bp_malakai_rail_left", "mtb_bp_malakai_rail_right"], "mtb_bp_helm_crew")
MODELS = seat_models.seat_models(FILES, TABLES)
failed = 0


def case(name, body, new_panel=False):
    """new_panel: src/tww3_mtb_crew_ui.lua's switch on, the screen not started (the module reads the model's saved state, docs/design/port-to-game.md
    8.6); the replay of the bridge with the model itself is tools/crew_bridge_offline.py."""
    global failed
    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(FAKE)
    lua.execute("_G.tww3_mtb_campaign.find_malakai = function() return {has_ancillary = function() return true end} end")
    if new_panel:
        lua.execute("_G.tww3_mtb_crew_ui = {NEW_SHIP_PANEL = true, ship_screen = function() return nil end}")
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


def upkeep_paid(run):
    """The control of the new panel's case below: with the old panel the upkeep of what stands is taken at the turn start."""
    built(run, "airship_hull_2", "crew_weapons_1")
    run("saved['mtb_crew_rifles'] = 'quarrellers'")
    cost = num(run, "tww3_mtb_crew.upkeep_of('rifles', 'quarrellers')")
    assert cost > 0, "an upkeep"
    run("tww3_mtb_crew.pay_upkeep()")
    expect(run, "gold", 10000 - cost)


MODEL_STATE = '{"order":{"option":"thunderers","paid":100},"standing":"quarrellers"}'


def new_no_old_order(run):
    built(run, "airship_hull_2", "crew_weapons_1")
    ok, why = run("return tww3_mtb_crew.choose('rifles', 'quarrellers')")
    assert ok is False and "new panel" in why, (ok, why)
    expect(run, "gold", 10000)
    expect(run, "tww3_mtb_crew.orders().rifles", None)


def new_no_old_upkeep(run):
    built(run, "airship_hull_2", "crew_weapons_1")
    run("saved['mtb_crew_rifles'] = '" + MODEL_STATE + "'")
    run("tww3_mtb_crew.pay_upkeep(); tww3_mtb_crew.carry_out()")
    expect(run, "gold", 10000)
    expect(run, "moves", 0)
    expect(run, "tww3_mtb_crew.get().rifles", "quarrellers")


def new_reads_model(run):
    run("saved['mtb_crew_rifles'] = '" + MODEL_STATE + "'")
    expect(run, "tww3_mtb_crew.get().rifles", "quarrellers")
    # the model's empty bay is the plain ship without the bay's building, the bay with it
    run("saved['mtb_crew_cannons'] = '{\"standing\":\"empty\"}'")
    expect(run, "tww3_mtb_crew.get().cannons", "none")
    built(run, "airship_hull_2", "mtb_guns_1")
    expect(run, "tww3_mtb_crew.get().cannons", "empty")


def new_set_refuses(run):
    ok, why = run("return tww3_mtb_crew.set('rifles', 'pirates')")
    assert ok is False and "new panel" in why, (ok, why)
    expect(run, "tww3_mtb_crew.set('pub', 'stock')", True)
    expect(run, "tww3_mtb_crew.get().pub", "stock")


def old_reads_model(run):
    run("saved['mtb_crew_rifles'] = '" + MODEL_STATE + "'")
    expect(run, "tww3_mtb_crew.get().rifles", "quarrellers")


def plan_models(run):
    """{seat: model (tools/seat_models.py) of the row the module would write}: who stands where, not the rows' names."""
    plan = run("return tww3_mtb_crew.seat_plan()")
    return {seat: MODELS.get(row) for seat, row in plan.items()}


def malakai_where(run, side):
    """His own body on exactly the rail seat of his side, with his rifle and no wheel; at the helm a crew dwarf with the wheel, not him."""
    mk = run("return tww3_mtb_crew.config().malakai")
    models = plan_models(run)
    rail, helm = models.get(mk.seats[side]), models.get(mk.helm_seat)
    assert rail and rail["malakai"] and rail["rifle"] and not rail["wheel"] and rail["variant"] == mk.rail_variant, \
        f"{mk.seats[side]}: {rail and (rail['variant'], seat_models.short(rail['figure']), seat_models.short(rail['props']))}, not Malakai with his rifle"
    assert helm and helm["known"] and not helm["malakai"] and helm["wheel"] and helm["variant"] == mk.helm_variant, \
        f"{mk.helm_seat}: {helm and (helm['variant'], seat_models.short(helm['figure']))}, not a crew dwarf at the wheel"
    others = sorted(seat for seat, m in models.items() if m and m["malakai"] and seat != mk.seats[side])
    assert not others, f"Malakai's body also on {others}"


def new_malakai_seat(run):
    expect(run, "tww3_mtb_crew.seat_plan().ap_crew_left_1", "mtb_bp_malakai_rail_left")
    expect(run, "tww3_mtb_crew.seat_plan().ap_captain", "mtb_bp_helm_crew")
    malakai_where(run, "left")
    run("saved['mtb_malakai_side'] = 'right'")
    expect(run, "tww3_mtb_crew.seat_plan().ap_crew_right_1", "mtb_bp_malakai_rail_right")
    expect(run, "tww3_mtb_crew.seat_plan().ap_crew_left_1", "mtb_bp_empty")
    malakai_where(run, "right")
    # a crew standing on the other rifle seats, its boost: his seat and his look stay his
    run("saved['mtb_crew_rifles'] = '" + MODEL_STATE + "'")
    malakai_where(run, "right")
    expect(run, "tww3_mtb_crew.seat_plan().ap_crew_left_1", "mtb_bp_quarrellers_crew_left_1")
    run("tww3_mtb_crew.boost_level = function() return 2 end")
    malakai_where(run, "right")
    expect(run, "tww3_mtb_crew.seat_plan().ap_crew_left_1", "mtb_bp_quarrellers_crew_left_1_b2")
    # switched off: as stock, Malakai at the wheel and nowhere else
    run("tww3_mtb_crew.MALAKAI_AT_RAIL = false")
    expect(run, "tww3_mtb_crew.seat_plan().ap_captain", "mtb_dwf_veh_thunderbarge_grungni_malakai_captain")
    models = plan_models(run)
    helm = models["ap_captain"]
    assert helm["malakai"] and helm["wheel"], f"switched off: the helm shows {helm['variant']}, not Malakai at the wheel"
    others = sorted(seat for seat, m in models.items() if m and m["malakai"] and seat != "ap_captain")
    assert not others, f"switched off: Malakai's body also on {others}"


def old_no_malakai(run):
    expect(run, "tww3_mtb_crew.seat_plan().ap_captain", None)
    expect(run, "tww3_mtb_crew.seat_plan().ap_crew_left_1", "mtb_bp_empty")
    expect(run, "tww3_mtb_crew.malakai_seat()", None)


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
case("the upkeep of what stands is taken at the turn start", upkeep_paid)
case("old panel: a save of the new panel is read for its standing crew", old_reads_model)
case("old panel: Malakai keeps the helm, 12 rifle seats", old_no_malakai)
case("new panel: the old panel's order is refused, nothing taken", new_no_old_order, new_panel=True)
case("new panel: the old upkeep and the old orders take nothing (the model takes them)", new_no_old_upkeep, new_panel=True)
case("new panel: the seats get the model's standing crew; its empty bay is the plain ship until the bay is built", new_reads_model, new_panel=True)
case("new panel: set() refuses a place of the panel, not the pub", new_set_refuses, new_panel=True)
case("new panel: Malakai at the rail of his side, a crew dwarf at the helm; back at the helm when switched off", new_malakai_seat, new_panel=True)
print("failed:", failed)
sys.exit(1 if failed else 0)
sys.exit(1 if failed else 0)
