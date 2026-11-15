-- The barge's crew: one unit, each group of seats set to one option. The options are rows of battle_personalities in the pack
-- (data/crew_options.json, tools/crew_options.py); this module points the seats of OUR land unit at them through memreader Plus.
--
-- The game reads a unit's seat list when it creates the unit in a battle, and the list lives until the game closes. So the seats
-- are written once when a campaign starts and again when a choice changes, never during a battle. Nothing is allocated in the game.
--
-- Anything unexpected (no memreader Plus, a pattern gone after a patch, a seat list that does not look right): nothing is written,
-- the unit keeps its stock crew from the tables, the reason goes once to the log and once to the player.
--
--   tww3_mtb_crew.set('rifles', 'quarr')   sets an option, unlocked or not (the tests); saved in the campaign, applied at once
--   tww3_mtb_crew.choose('rifles', 'quarr')  the panel's way: an order for the next turn, of an unlocked option, one per group per turn
--   tww3_mtb_crew.orders()                 {group = option ordered for the next turn}
--   tww3_mtb_crew.upkeep()                 gold per turn now, gold per turn with the orders
--   tww3_mtb_crew.hire_of(group, option)   gold to hire it, taken when it is ordered
--   tww3_mtb_crew.get()                    {group = option}
--   tww3_mtb_crew.unlocked()               {group = {option = true}}
--   tww3_mtb_crew.status                   'applied', 'not applied', 'stock: <reason>'
--   tww3_mtb_crew.seat_plan()              {seat = battle_personalities key}: what apply() points the seats at
--   tww3_mtb_crew.malakai_seat()           the new panel's Malakai at the rail {side, seat, row, helm_seat, helm_row}, or nil
--   tww3_mtb_crew.bridge                   the new panel's bridge: .S the screen, .sync(reason), .lose(reason), .writes
--
-- A human Malakai's buildings only unlock options (CONFIG.buildings, from data/crew_options.json); the player places them in the crew panel
-- (src/tww3_mtb_crew_ui.lua). Only the buildings of CONFIG.auto_active also set their option, and only a bare mount or a group the panel does not list. The built list is saved and the unlocked set is
-- worked out from it: a building that no longer stands leaves it and locks its option again, and if that option stood in the barge the group goes
-- to what its latest still standing building unlocks, or to its start, with one message to the player. A higher level of the same chain counts as
-- the lower one still standing. Under the AI nothing follows: start_ai.
--
-- The panel orders, the turn carries out: what stands now stays for all battles of this turn, an order goes in at the faction's turn start, with the upkeep.
-- One order per group per turn, kept in the save; picking what stands now takes the order back, which uses that turn's change. A demolished building acts at
-- once and takes back an order for what it unlocked, and does not count as the group's change. A bare mount and the pub (CONFIG.auto_active) stand at once.
--
-- Boost: some buildings make a group better without changing its option (accuracy of the shooters, range and accuracy of the guns). The numbers live in rows of that group's own weapons,
-- one set of seat rows per level, so nothing else of the unit is touched: the seats point at option@level. Requires: a group's weapons may need another building too (the guns: signals).
-- Ammunition: the level of the cargo chain goes to the battle through the game's scripted value registry, read by src/tww3_mtb_ammo.lua.
--
-- Hire: an option costs gold once, taken at once when it is ordered, with what is taken kept in the save beside the order. Taking the order back returns all of it, so does a building that
-- takes the order with it. What stands now is not paid back when it is replaced, and going back to an option taken off is paid again. An empty option is free. The treasury and the saved values
-- go into the same save, so a load neither takes nor returns anything by itself. Buildings placing an option by themselves (CONFIG.auto_active) are free.
--
-- Upkeep: paid from the treasury at the faction's turn start for what stands, only while he is on the barge and the crew can be written.
--
-- Two kinds of group are not seats to choose. always: the group holds that option whatever is saved (the deck crew). off_bundle: no seats, an ability the unit
-- has by its tables; an effect bundle on Malakai's force takes it away while the group is on its start (the harpoon). Without memreader Plus and under the AI
-- there is no bundle: the unit has the ability, as stock. The harpoon's model comes from the hull's animation table, so the land unit's pointer to its mount row is
-- written with the seats: a row per look of the hull (harpoon or not, patches over the port and the bomb niches). The game reads it when it creates the unit.
--
-- THE NEW PANEL (src/tww3_mtb_crew_ui.lua NEW_SHIP_PANEL on; docs/design/port-to-game.md 8.6): the new screen's model (src/tww3_mtb_ship.lua over
-- src/tww3_mtb_crew_model.lua) is the one book of the crew. What stands in it is what the seats carry: get() reads the model (or, before the screen
-- has started, the model's saved state, the same key mtb_crew_<group>); the model's own change (a hire, the turn start, a building gone) makes the
-- bridge below write the seats with the code above. The model takes the hire and the upkeep; choose(), carry_out() and pay_upkeep() do nothing then,
-- and set() refuses the groups the model owns. The buildings' boosts, the cargo and the bays are read from the game's slots (the screen's adapter),
-- not from the built list. Malakai stands at a rail (CONFIG.malakai: 11 riflemen and him on the twelfth seat of his side, a crew dwarf at the helm).
-- With the switch off nothing of this runs: every function behaves as before (a saved state of the new panel is read for its standing crew only).
local CONFIG = {} --@CONFIG@

local SAVE_PREFIX = 'mtb_crew_'
local HOME_FACTION = 'wh3_dlc25_dwf_malakai'
local PROFILE = SAVE_PREFIX .. 'profile'    -- saved: 'player' or 'ai', decided once, when the campaign starts
local BUILT = SAVE_PREFIX .. 'built'        -- saved: 'key@turn,key@turn', oldest first
local ORDER, CHANGED = SAVE_PREFIX .. 'order_', SAVE_PREFIX .. 'changed_'    -- saved per group: the option ordered; the turn of its last change
local PAID = SAVE_PREFIX .. 'paid'          -- saved: the turn the upkeep was last paid on
local ORDER_PAID = SAVE_PREFIX .. 'order_paid_'    -- saved per group: the gold taken for the order that waits
local ANCILLARY = 'mtb_anc_mount_dwf_malakai_thunderbarge'
local DB_ROOT = '48 8B 0D ?? ?? ?? ?? 4C 8B C0 48 8B 91 ?? ?? ?? ?? 48 8B CB E8 ?? ?? ?? ?? 48 85 C0 74 ?? 48 8B 0D ?? ?? ?? ?? 48 89 81'
local TABLE_MARK = '48 8D 41 28 48 89 02 48 8B 41 58 49 89 00 C3'
local TABLE_SLOTS, TABLE_SLOT_SIZE = 1812, 0x38
-- Land unit record: the vector of autonomous riders. Seat: row pointer, pointer to the attachment name.
local SEATS_CAPACITY, SEATS_SIZE, SEATS_DATA, SEAT_STRIDE, SEAT_NAME = 0x48, 0x4c, 0x50, 0x18, 8
local ROW_KEY = 8

local M = {status = 'not applied', writes = 0, patterns = {root = DB_ROOT, mark = TABLE_MARK}}
_G.tww3_mtb_crew = M
-- The new panel only: Malakai at the rail of his side (CONFIG.malakai). false: he keeps the helm and twelve riflemen stand (В6 (б)).
M.MALAKAI_AT_RAIL = true

local reported = false
local tables = nil      -- {name = table pointer}; only read, one scan per game mode
local smatch = string.match

-- The new screen's model: the bridge's state (below). B.S is the screen (src/tww3_mtb_ship_screen.lua: S.M the model, S.game the adapter) once
-- attached; nil with the switch off, under the AI, or while the screen has not started.
local B = {S = nil, applied = nil}
M.bridge = B
local function new_panel()
    local ui = _G.tww3_mtb_crew_ui
    return ui ~= nil and ui.NEW_SHIP_PANEL == true
end
M.new_panel = new_panel
-- the groups the new panel's places show (not the deck that always stands, not the pub only a building sets)
local function owned(group)
    local spec = CONFIG.groups[group]
    return spec ~= nil and not spec.always and not spec.no_panel
end
M.owned = owned
-- the standing option in a saved value: the old mod's plain option, or the new model's {"order":...,"standing":"x"} (src/tww3_mtb_ship.lua encode)
local function standing_of(saved)
    if type(saved) ~= 'string' then return saved end
    if smatch(saved, '^{') then return smatch(saved, '"standing":"([^"]*)"') end
    return saved
end

local function log(text)
    pcall(function() _G.tww3_mtb_campaign.file_log('[crew] ' .. tostring(text)) end)
    pcall(ModLog, '[tww3_mtb_crew] ' .. tostring(text))
    if _G.mtb and _G.mtb.log then pcall(_G.mtb.log, 'crew', text) end
end

-- The reason once per session of this script, and one message to the player.
local function report(reason)
    M.status = 'stock: ' .. tostring(reason)
    if reported then return end
    reported = true
    log(M.status)
    pcall(function()
        local faction = cm:get_local_faction_name(true)
        -- Lua restarts after every battle: the player is told once per campaign, not after each battle.
        if faction and not cm:get_saved_value(SAVE_PREFIX .. 'told') then
            cm:set_saved_value(SAVE_PREFIX .. 'told', true)
            cm:show_message_event(faction, 'ui_text_replacements_localised_text_mtb_crew_failed_title',
                'ui_text_replacements_localised_text_mtb_crew_failed_primary',
                'ui_text_replacements_localised_text_mtb_crew_failed_secondary', true, 1701)
        end
    end)
end

local function find_tables(mr)
    if tables then return tables end
    local root, count = mr.find_pattern(M.patterns.root)
    if count ~= 1 then error('database pattern matched ' .. tostring(count) .. ' times') end
    local mark, mark_count = mr.find_pattern(M.patterns.mark)
    if mark_count ~= 1 then error('table pattern matched ' .. tostring(mark_count) .. ' times') end
    local app = mr.add(mr.add(root, 7), mr.read_int32(root, 3, true))
    local db = mr.read_pointer(mr.read_pointer(app, 0), mr.read_int32(root, 13, true))
    local found = {}
    for i = 0, TABLE_SLOTS - 1 do
        local t = mr.read_pointer(db, i * TABLE_SLOT_SIZE)
        if not mr.is_null(t) and mr.read_chain(t, 0, 0) == mark then
            found[mr.read_string(mr.read_pointer(t, 0x58), 0)] = t
        end
    end
    if not found.land_units or not found.battle_personalities or not found.mounts then error('tables not found') end
    tables = found
    return found
end

local function row(mr, table_pointer, key)
    local node = mr.map_find_key(mr.add(table_pointer, 0x28), key)
    if not node then error('no row ' .. key) end
    local _, data = mr.read_array(table_pointer, 0x08)
    return mr.read_pointer(data, mr.read_uint32(node, 0x20) * 8)
end

local function profile()
    local saved = cm:get_saved_value(PROFILE)
    if saved then return saved end
    local home = cm:get_faction(HOME_FACTION)
    saved = home and home:is_human() and 'player' or 'ai'
    cm:set_saved_value(PROFILE, saved)
    return saved
end
M.profile = profile

-- The new panel: what the model has standing in a group (its own option for an empty bay is the bay: the mount option), the model's saved state
-- before the screen has started. nil: the model says nothing of it.
local function model_standing(group)
    local model = B.S and B.S.M
    if model then
        local ok, v = pcall(model.crew, group)
        if ok then return v end
    end
    return standing_of(cm:get_saved_value(SAVE_PREFIX .. group))
end

function M.get()
    local out = {}
    local field = profile() == 'player' and 'start' or 'start_ai'
    local model = field == 'start' and new_panel()
    for group, spec in pairs(CONFIG.groups) do
        local raw = cm:get_saved_value(SAVE_PREFIX .. group)
        local of_model = type(raw) == 'string' and smatch(raw, '^{') ~= nil
        local saved = standing_of(raw)
        if model and owned(group) then saved, of_model = model_standing(group), true end
        -- the model's empty place of a bay is the bay; without the bay's building it is the plain ship (start: none)
        if of_model and spec.mount and saved == spec.mount and not M.mount_ready(group) then saved = spec.start end
        local option = spec[field]
        for _, known in ipairs(spec.options) do
            if known == saved then option = saved end
        end
        out[group] = spec.always or option
    end
    return out
end

-- The whole list is worked out and checked first; the write is the last step, so a failure leaves the unit as it was.
-- Where the land unit holds its mount: looked for by the pointer's value, so nothing is read through a wrong pointer.
local mount_offset = nil

local function write_mounts(mr, found, land_unit, choice)
    local known = {}
    for _, key in pairs(CONFIG.hull_mounts) do known[tostring(row(mr, found.mounts, key))] = true end
    if not mount_offset then
        for o = 0, 0x400, 8 do
            if known[tostring(mr.read_pointer(land_unit, o))] then
                mount_offset = o
                break
            end
        end
        log('mount at ' .. tostring(mount_offset))
    end
    if not mount_offset then error('the mount of the land unit is not found') end
    if not known[tostring(mr.read_pointer(land_unit, mount_offset))] then error('the land unit has another mount') end
    -- the hull as it looks now: harpoon or not, patches over the holes of the bays that are not there
    local code = (choice.harpoon == CONFIG.groups.harpoon.start and 'n' or 'h') .. (choice.cannons == 'none' and 'c' or '') .. ((choice.bombs == 'none' or choice.bombs == 'empty') and 'b' or '')
    mr.write(land_unit, mount_offset, row(mr, found.mounts, CONFIG.hull_mounts[code]))
end

-- The new panel's Malakai at the rail: {side, seat, row, helm_seat, helm_row} (CONFIG.malakai, tools/crew_options.py): his own model on the seat
-- of his side that the page gives him (web/js/main.js: ap_crew_<side>_1), no weapon there, a crew dwarf with the wheel at the helm. nil: he keeps
-- the helm (the switch off, M.MALAKAI_AT_RAIL false, the AI, no data). The side is the model's (src/tww3_mtb_ship.lua malakai_side, saved as
-- mtb_malakai_side), left by default as there.
function M.malakai_seat()
    local mk = CONFIG.malakai
    if not mk or not M.MALAKAI_AT_RAIL or not new_panel() or profile() ~= 'player' then return nil end
    local side
    local model = B.S and B.S.M
    if model then
        local ok, s = pcall(model.malakai_side)
        if ok then side = s end
    end
    side = side or cm:get_saved_value('mtb_malakai_side')
    if side ~= 'left' and side ~= 'right' then side = 'left' end
    return {side = side, seat = mk.seats[side], row = mk.rows[side], helm_seat = mk.helm_seat, helm_row = mk.helm_crew}
end

-- What the seats are pointed at: {seat = battle_personalities key}, the choice's option on every seat of its group (at the boost's level), and
-- Malakai's two seats on the new panel. Pure: the write below checks every key against the game first.
function M.seat_plan(choice)
    choice = choice or M.get()
    local wanted = {}
    for group, spec in pairs(CONFIG.groups) do
        local level = M.boost_level(group)
        for _, seat in ipairs(spec.seats) do
            wanted[seat] = (level > 0 and CONFIG.seats[seat][choice[group] .. '@' .. level]) or CONFIG.seats[seat][choice[group]]
        end
    end
    local mk = M.malakai_seat()
    if mk then
        wanted[mk.seat], wanted[mk.helm_seat] = mk.row, mk.helm_row
    elseif CONFIG.malakai and new_panel() and profile() == 'player' then
        wanted[CONFIG.malakai.helm_seat] = CONFIG.malakai.helm_own      -- back at the helm (the seat list lives until the game closes)
    end
    return wanted
end

local function write_seats()
    local mr = _G.memreader_plus
    if not mr then error('memreader Plus is not loaded') end
    local found = find_tables(mr)
    local land_unit = row(mr, found.land_units, CONFIG.land_unit)
    local capacity, size = mr.read_uint32(land_unit, SEATS_CAPACITY), mr.read_uint32(land_unit, SEATS_SIZE)
    if size ~= CONFIG.seat_count or capacity ~= CONFIG.seat_count then
        error('seat list is ' .. tostring(size) .. '/' .. tostring(capacity) .. ', not ' .. CONFIG.seat_count)
    end
    local data = mr.read_pointer(land_unit, SEATS_DATA)
    local choice = M.get()
    local wanted = M.seat_plan(choice)
    local plan, seen = {}, 0
    for i = 0, size - 1 do
        local name = mr.read_string(mr.read_pointer(data, i * SEAT_STRIDE + SEAT_NAME), 0)
        local key = wanted[name]
        if key then
            local pointer = row(mr, found.battle_personalities, key)
            if mr.read_string(pointer, ROW_KEY) ~= key then error('row check failed: ' .. key) end
            plan[#plan + 1] = {i * SEAT_STRIDE, pointer}
            seen = seen + 1
        elseif not CONFIG.fixed[name] then
            error('unknown seat ' .. tostring(name))
        end
    end
    local need = 0
    for _ in pairs(wanted) do need = need + 1 end
    if seen ~= need then error('found ' .. seen .. ' of ' .. need .. ' seats') end
    for _, item in ipairs(plan) do mr.write(data, item[1], item[2]) end
    M.writes = M.writes + 1
    -- Only the look of one thing depends on this: a failure leaves the crew written and the harpoon on the model, as stock.
    local ok, err = pcall(write_mounts, mr, found, land_unit, choice)
    if not ok then log('mount: ' .. tostring(err)) end
    return seen
end

-- What the battle reads: the ammunition of every crew, by the cargo chain. Written with the seats.
local function save_ammo_mod()
    core:svr_save_string('mtb_crew_ammo_mod', tostring(profile() == 'player' and M.ammo_mod() or 1))
end

function M.apply()
    pcall(save_ammo_mod)
    local ok, result = pcall(write_seats)
    if ok then
        M.status = 'applied'
        return true
    end
    report(result)
    return false
end

-- The bundles of the ability groups, for what is chosen now. Applied to the force, so a new army gets it at the next turn start.
function M.sync_abilities()
    if profile() ~= 'player' then return end
    local malakai = _G.tww3_mtb_campaign and _G.tww3_mtb_campaign.find_malakai()
    if not malakai or not malakai:has_military_force() then return end
    local force = malakai:military_force()
    local choice = M.get()
    local stock = string.sub(tostring(M.status), 1, 5) == 'stock'
    for group, spec in pairs(CONFIG.groups) do
        if spec.off_bundle then
            local off = not stock and choice[group] == spec.start
            local has = force:has_effect_bundle(spec.off_bundle)
            if off and not has then
                cm:apply_effect_bundle_to_force(spec.off_bundle, force:command_queue_index(), 0)
                log(group .. ': off')
            elseif has and not off then
                cm:remove_effect_bundle_from_force(spec.off_bundle, force:command_queue_index())
                log(group .. ': on')
            end
        end
    end
end

-- What the crew costs per turn: now, and with the orders of this turn.
local function sum_upkeep(choice)
    local total = 0
    for group, option in pairs(choice) do
        total = total + ((CONFIG.upkeep[group] or {})[option] or 0)
    end
    return total
end

-- On foot, under the AI or with a stock crew nothing is paid. The new panel's adapter asks the same (src/tww3_mtb_game.lua crew_pays).
local function paying()
    if profile() ~= 'player' or string.sub(tostring(M.status), 1, 5) == 'stock' then return false end
    local malakai = _G.tww3_mtb_campaign and _G.tww3_mtb_campaign.find_malakai()
    return malakai and malakai:has_ancillary(ANCILLARY) or false
end
M.paying = paying

function M.upkeep()
    if not paying() then return 0, 0 end
    local choice = M.get()
    local now = sum_upkeep(choice)
    for group in pairs(CONFIG.groups) do
        choice[group] = cm:get_saved_value(ORDER .. group) or choice[group]
    end
    return now, sum_upkeep(choice)
end

-- What the option costs to hire. Without memreader Plus there is no choice, and the AI does not pay.
function M.hire_of(group, option)
    if profile() ~= 'player' or string.sub(tostring(M.status), 1, 5) == 'stock' then return 0 end
    return (CONFIG.hire[group] or {})[option] or 0
end

function M.gold()
    return cm:get_faction(HOME_FACTION):treasury()
end

function M.can_pay(group, option)
    return M.gold() >= M.hire_of(group, option)
end

-- An order goes away: the gold taken for it comes back, unless it went in.
local function drop_order(group, give_back)
    local paid = cm:get_saved_value(ORDER_PAID .. group) or 0
    cm:set_saved_value(ORDER .. group, false)
    cm:set_saved_value(ORDER_PAID .. group, false)
    if give_back and paid > 0 then
        cm:treasury_mod(HOME_FACTION, paid)
        log('hire given back ' .. group .. ' ' .. paid)
    end
end

function M.upkeep_of(group, option)
    return (CONFIG.upkeep[group] or {})[option] or 0
end

-- Paid once at each of the faction's turn starts, for what stands then. The game's flat income effect does not take a negative value (run panel_main, 04.11):
-- so straight from the treasury, and the panel and the log show it.
function M.pay_upkeep()
    if new_panel() then return end      -- the new panel's model takes the upkeep at the turn start (src/tww3_mtb_ship.lua): once, there
    if profile() ~= 'player' or cm:get_saved_value(PAID) == cm:turn_number() then return end
    cm:set_saved_value(PAID, cm:turn_number())
    local total = M.upkeep()
    if total > 0 then
        cm:treasury_mod(HOME_FACTION, -total)
        log('upkeep paid ' .. total .. ' on turn ' .. cm:turn_number())
    end
end

function M.set(group, option)
    local spec = CONFIG.groups[group]
    if not spec then return false, 'unknown group ' .. tostring(group) end
    if new_panel() and owned(group) and profile() == 'player' then return false, 'the new panel owns ' .. group .. ': hire through it' end
    for _, known in ipairs(spec.options) do
        if known == option then
            cm:set_saved_value(SAVE_PREFIX .. group, option)
            local ok = M.apply()
            pcall(M.sync_abilities)
            if M.on_changed then pcall(M.on_changed) end
            return ok
        end
    end
    return false, 'unknown option ' .. tostring(option)
end

local function read_built()
    local out = {}
    for key, turn in string.gmatch(cm:get_saved_value(BUILT) or '', '([^@,]+)@(%d+)') do
        out[#out + 1] = {key = key, turn = tonumber(turn)}
    end
    return out
end

local function write_built(list)
    local parts = {}
    for _, item in ipairs(list) do parts[#parts + 1] = item.key .. '@' .. item.turn end
    cm:set_saved_value(BUILT, table.concat(parts, ','))
end

-- What is open to the player: {group = {option = true}}. A group's start is always open.
function M.unlocked()
    local out = {}
    for group, spec in pairs(CONFIG.groups) do out[group] = {[spec.start] = true} end
    for _, item in ipairs(read_built()) do
        for _, binding in ipairs(CONFIG.buildings[item.key] or {}) do out[binding.group][binding.option] = true end
    end
    return out
end

-- Does the building stand (a higher level of its chain counts)? The new panel asks the game's slots through the screen's adapter, the one source
-- the model reads too (src/tww3_mtb_game.lua has_building); otherwise, and before the screen has started, the built list.
local function is_built(key)
    local game = B.S and B.S.game
    if game and new_panel() then
        local ok, v = pcall(game.has_building, key)
        if ok then return v == true end
    end
    for _, item in ipairs(read_built()) do
        if item.key == key then return true end
    end
    return false
end
M.is_built = is_built

-- How many buildings of the group's boost stand: the row level of its seats. The AI and a stock crew have none.
function M.boost_level(group)
    local list = CONFIG.groups[group].boost
    if not list or profile() ~= 'player' then return 0 end
    local level = 0
    for i, key in ipairs(list) do
        if is_built(key) then level = i end
    end
    return level
end

-- The ammunition of every crew with the cargo chain.
function M.ammo_mod()
    local mod = 1
    if B.S and new_panel() then
        for key, m in pairs(CONFIG.ammo_mod) do
            if m > mod and is_built(key) then mod = m end
        end
        return mod
    end
    for _, item in ipairs(read_built()) do
        local m = CONFIG.ammo_mod[item.key]
        if m and m > mod then mod = m end
    end
    return mod
end

-- The other building the group's weapons need, besides the bay.
function M.requires_ok(group)
    local key = CONFIG.groups[group].requires
    return not key or is_built(key)
end

-- Has the group its bay? The building of its mount option makes it. A group without a mount always has.
function M.mount_ready(group)
    local spec = CONFIG.groups[group]
    if not spec.mount then return true end
    -- the new panel: the model's place of the group (the bay's building stands and the barge is carried)
    local model = B.S and B.S.M
    if model and new_panel() and owned(group) then
        local ok, v = pcall(model.crew_place, group)
        if ok then return v == true end
    end
    return M.unlocked()[group][spec.mount] == true
end

-- Has he the hull that makes a barge? The panel's button asks this.
function M.has_barge()
    for _, item in ipairs(read_built()) do
        if item.key == CONFIG.panel_building then return true end
    end
    return false
end

function M.orders()
    local out = {}
    for group in pairs(CONFIG.groups) do
        local option = cm:get_saved_value(ORDER .. group)
        if option then out[group] = option end
    end
    return out
end

-- Has this group had its change of this turn?
function M.changed(group)
    return cm:get_saved_value(CHANGED .. group) == cm:turn_number()
end

-- The panel's click: an order for the next turn. Picking what stands now takes back this turn's order.
function M.choose(group, option)
    if new_panel() then return false, 'the new panel orders the crew' end
    local open = M.unlocked()[group]
    if not open then return false, 'unknown group ' .. tostring(group) end
    if CONFIG.groups[group].always then return false, 'not a choice ' .. group end
    if not open[option] then return false, 'locked ' .. tostring(option) end
    if not M.mount_ready(group) then return false, 'no mount ' .. group end
    if option == CONFIG.groups[group].start and CONFIG.groups[group].mount then return false, 'not a choice ' .. option end
    if option ~= CONFIG.groups[group].mount and not M.requires_ok(group) then return false, 'needs another building ' .. group end
    local current, order = M.get()[group], cm:get_saved_value(ORDER .. group)
    if M.changed(group) then
        if order and option == current then
            drop_order(group, true)
            log('order taken back ' .. group)
            if M.on_changed then pcall(M.on_changed) end
            return true
        end
        return false, 'changed this turn'
    end
    if option == current then return true end
    local cost = M.hire_of(group, option)
    if M.gold() < cost then return false, 'no gold ' .. cost end
    if cost > 0 then
        cm:treasury_mod(HOME_FACTION, -cost)
        cm:set_saved_value(ORDER_PAID .. group, cost)
    end
    cm:set_saved_value(ORDER .. group, option)
    cm:set_saved_value(CHANGED .. group, cm:turn_number())
    log('order ' .. group .. '=' .. option .. ' hire ' .. cost)
    if M.on_changed then pcall(M.on_changed) end
    return true
end

-- The faction's turn start: the orders go in.
function M.carry_out()
    if profile() ~= 'player' or new_panel() then return end      -- the new panel: the model's turn start puts its orders in
    for group, option in pairs(M.orders()) do
        drop_order(group, false)
        log('order done ' .. group .. '=' .. option)
        M.set(group, option)
    end
end

-- A building of the table is complete: its options are unlocked. One becomes active only for the buildings of CONFIG.auto_active. A building of a boost or of the cargo chain acts at once.
function M.on_built(key)
    if not CONFIG.followed[key] or profile() ~= 'player' then return false end
    local list = {}
    for _, item in ipairs(read_built()) do
        if item.key ~= key then list[#list + 1] = item end
    end
    list[#list + 1] = {key = key, turn = cm:turn_number()}
    write_built(list)
    local bindings = CONFIG.buildings[key] or {}
    local set_any = false
    for _, binding in ipairs(bindings) do
        log('built ' .. key .. ': unlocked ' .. binding.group .. '=' .. binding.option)
        if M.on_unlocked and not CONFIG.groups[binding.group].no_panel then pcall(M.on_unlocked, binding.group, binding.option) end
        -- A bare mount and a group the panel does not list (the pub) appear at once, in a group that had nothing. A crew the player chooses
        -- in the panel is only unlocked, also by such a building (the beer hall's pirates).
        local group = CONFIG.groups[binding.group]
        -- the new panel: the model's bays appear by themselves (its place); only a group the panel does not list (the pub) is set here
        local by_model = new_panel() and owned(binding.group)
        if not by_model and CONFIG.auto_active[key] and (group.no_panel or group.mount == binding.option) and M.get()[binding.group] == group.start then
            M.set(binding.group, binding.option)
            set_any = true
        end
    end
    if B.S and new_panel() then B.sync('built ' .. key)
    elseif not set_any then M.apply() end
    if M.on_changed then pcall(M.on_changed) end
    return true
end

-- {chain = highest level} in the human Malakai's horde. nil when no horde with the hull is found: then nothing is decided.
local function standing_levels()
    local forces = cm:get_faction(HOME_FACTION):military_force_list()
    local out, hull = {}, false
    for i = 0, forces:num_items() - 1 do
        local details = forces:item_at(i):horde_details()
        if not details:is_null_interface() then
            local slots = details:military_force_slot_list()
            for j = 0, slots:num_items() - 1 do
                local known = slots:item_at(j):has_building() and CONFIG.levels[slots:item_at(j):building()]
                if known then
                    out[known.chain] = math.max(out[known.chain] or -1, known.level)
                    hull = true
                end
            end
        end
    end
    return hull and out or nil
end

-- Demolished buildings leave the list and lock their options again. A group whose active option was locked by this goes to what its
-- latest still standing building unlocks, or to its start; the player gets one message. Buildings of this turn stay: the slot may still be
-- catching up with the completion event.
function M.reconcile()
    if profile() ~= 'player' then return false end
    local list = read_built()
    if #list == 0 then return false end
    local levels = standing_levels()
    if not levels then return false end
    local kept = {}
    local turn = cm:turn_number()
    for _, item in ipairs(list) do
        local known = CONFIG.levels[item.key]
        if not known or item.turn == turn or (levels[known.chain] and levels[known.chain] >= known.level) then
            kept[#kept + 1] = item
        else
            log('gone ' .. item.key)
        end
    end
    if #kept == #list then return false end
    write_built(kept)
    local open, active, lost = M.unlocked(), M.get(), false
    -- the new panel: the groups of its places are the model's (its lose(), the bridge below); here only the others (the pub)
    local by_model = new_panel()
    for group, option in pairs(M.orders()) do
        if by_model and owned(group) then
            -- an order of the old panel left in a save: the bridge has taken it into the model
        elseif not open[group][option] or not M.mount_ready(group) or (option ~= CONFIG.groups[group].mount and not M.requires_ok(group)) then
            drop_order(group, true)
            log('order gone with its building ' .. group .. '=' .. option)
        end
    end
    for group, spec in pairs(CONFIG.groups) do
        local needs_more = active[group] ~= spec.start and active[group] ~= spec.mount and not M.requires_ok(group)
        if by_model and owned(group) then
            -- the model's
        elseif not open[group][active[group]] or (active[group] ~= spec.start and not M.mount_ready(group)) or needs_more then
            local option = spec.start
            if M.mount_ready(group) then
                for _, item in ipairs(kept) do
                    for _, binding in ipairs(CONFIG.buildings[item.key] or {}) do
                        if binding.group == group and (binding.option == spec.mount or M.requires_ok(group)) then option = binding.option end
                    end
                end
            end
            log('locked ' .. group .. '=' .. active[group] .. ', now ' .. option)
            M.set(group, option)
            lost = true
        end
    end
    if lost then
        pcall(function()
            cm:show_message_event(HOME_FACTION, 'ui_text_replacements_localised_text_mtb_crew_lost_title',
                'ui_text_replacements_localised_text_mtb_crew_lost_primary',
                'ui_text_replacements_localised_text_mtb_crew_lost_secondary', true, 1701)
        end)
    end
    if B.S and by_model then B.sync('buildings gone') else M.apply() end      -- a boost or the ammunition may have gone with the building
    if M.on_changed then pcall(M.on_changed) end
    return true
end

function M.built()
    return cm:get_saved_value(BUILT) or ''
end

-- For the failure test: the next apply() searches the game again, with whatever M.patterns holds.
function M.forget_tables()
    tables = nil
end

function M.options()
    local out = {}
    for group, spec in pairs(CONFIG.groups) do out[group] = spec.options end
    return out
end

-- The generated data, read only (the offline replay tools/crew_bridge_offline.py checks the seat plan against it)
function M.config() return CONFIG end

-- ---------------- the new panel's bridge (docs/design/port-to-game.md 8.6) ----------------
-- The model (B.S.M) is the book; this writes the seats when what it says changed. Its errors go to the log only: the crew's own failure path
-- (report: a stock crew and a message to the player) is for the memory, not for the bridge.
local function bridge_guarded(what, fn)
    return function(...)
        local ok, err = pcall(fn, ...)
        if not ok then log('bridge ' .. what .. ': ' .. tostring(err)) end
        return ok and err
    end
end

local function group_keys()
    local out = {}
    for g in pairs(CONFIG.groups) do out[#out + 1] = g end
    table.sort(out)
    return out
end
-- the model's empty option of a group (src/tww3_mtb_ship.lua emptyOf: the bay, else the start)
local function model_empty(model, g)
    local spec = model.groups and model.groups[g]
    return spec and (spec.mount or spec.start) or CONFIG.groups[g].mount or CONFIG.groups[g].start
end

-- What the seats are written for: the choice, every group's boost level, Malakai's seat, the cargo. Equal: nothing to write.
function B.signature()
    local choice, parts = M.get(), {}
    for _, g in ipairs(group_keys()) do parts[#parts + 1] = g .. '=' .. tostring(choice[g]) .. '@' .. M.boost_level(g) end
    local mk = M.malakai_seat()
    parts[#parts + 1] = 'malakai=' .. (mk and mk.seat or 'helm')
    parts[#parts + 1] = 'cargo=' .. tostring(M.ammo_mod())
    return table.concat(parts, ' ')
end

-- The model changed (a hire, a cancel, the turn start, a building in or out): the seats, the harpoon's bundle and the cargo written again by the code
-- of the old panel, when they differ from what was written last. -> true when it wrote
function B.sync(reason)
    if not (B.S and new_panel()) then return false end
    local sig = B.signature()
    if sig == B.applied then return false end
    B.applied = sig
    local ok = M.apply()
    pcall(M.sync_abilities)
    B.writes = (B.writes or 0) + 1
    log('bridge ' .. tostring(reason) .. ': ' .. sig .. (ok and '' or ' (not written: ' .. tostring(M.status) .. ')'))
    if M.on_changed then pcall(M.on_changed) end
    return true
end

local function save_model()
    local S = B.S
    if S.save then pcall(S.save) end
    if S.panel and S.shown then pcall(S.panel.refresh) end
end

-- A save of the old panel: its waiting orders (mtb_crew_order_<group> with the gold taken for them, mtb_crew_order_paid_<group>) become the model's
-- orders with that gold held, so a cancel gives it back and the turn start puts them in; a bay's plain 'none' is the model's empty bay. The plain
-- standing options are already the model's (src/tww3_mtb_ship.lua load_state reads them).
function B.migrate()
    local model = B.S.M
    local have, list = {}, {}
    for _, st in ipairs(model.crew_snapshot()) do have[st.group] = st end
    for _, g in ipairs(group_keys()) do
        local spec = CONFIG.groups[g]
        if owned(g) and model.groups and model.groups[g] then
            local st = have[g]
            local s = {group = g, standing = st and st.standing or model.crew(g), order = st and st.order or nil}
            local touched = false
            local empty = model_empty(model, g)
            if spec.mount and s.standing == spec.start and spec.start ~= empty then s.standing = empty; touched = true end
            local old = cm:get_saved_value(ORDER .. g)
            if old then
                if not s.order and old ~= s.standing then s.order = {option = old, paid = tonumber(cm:get_saved_value(ORDER_PAID .. g)) or 0} end
                cm:set_saved_value(ORDER .. g, false)
                cm:set_saved_value(ORDER_PAID .. g, false)
                touched = true
                log('bridge: the old order ' .. g .. '=' .. tostring(old) .. ' is the model\'s now')
            end
            if touched then list[#list + 1] = s end
        end
    end
    if #list == 0 then return false end
    model.set_crew_silently(list)
    save_model()
    return true
end

-- A building gone without an event the model hears (the stock horde tab's dismantle, a load, a battle): the model's drop_locked()
-- (src/tww3_mtb_ship.lua: its lose() for every place whose option no standing building opens now, an order of a closed option back with its
-- gold, a standing crew of one gone without, and the panel's line saying so). Only while the horde and the barge are there: a wounded Malakai
-- has no force, and nothing is decided.
function B.lose(reason)
    local S = B.S
    if not (S and new_panel()) then return false end
    local model = S.M
    local okc, carried = pcall(model.carried)
    if not (okc and carried) or standing_levels() == nil then return false end
    local before = {}
    for _, st in ipairs(model.crew_snapshot()) do before[st.group] = st end
    local any = model.drop_locked()
    if not any then return false end
    for _, st in ipairs(model.crew_snapshot()) do
        local was = before[st.group]
        if was and (was.standing ~= st.standing or (was.order and was.order.option) ~= (st.order and st.order.option)) then
            log('bridge ' .. tostring(reason) .. ': ' .. st.group .. ' ' .. tostring(was.standing) .. '/' .. tostring(was.order and was.order.option)
                .. ' -> ' .. tostring(st.standing) .. '/' .. tostring(st.order and st.order.option) .. ', gone with its building')
        end
    end
    save_model()
    return true
end

-- The screen of the new panel (src/tww3_mtb_crew_ui.lua ship_screen: started once, the same the HUD's button opens): the bridge listens to its
-- model. For a human Malakai only, as the panel.
function B.attach()
    if B.S then return true end
    if not new_panel() or profile() ~= 'player' then return false end
    local okf, faction = pcall(function() return cm:get_local_faction_name(true) end)
    if not okf or faction ~= HOME_FACTION then return false end
    local ui = _G.tww3_mtb_crew_ui
    local ok, S = pcall(ui.ship_screen)
    if not ok or type(S) ~= 'table' or not S.M then
        log('bridge: the new screen did not start (' .. tostring(S) .. '): the seats follow its saved state')
        return false
    end
    B.S = S
    bridge_guarded('migrate', B.migrate)()
    S.M.on_change(bridge_guarded('change', function() B.sync('model') end))
    log('bridge: attached to the new screen\'s model')
    return true
end

local function guarded(fn)
    return function(...)
        local ok, err = pcall(fn, ...)
        if not ok then report(err) end
    end
end

_G.tww3_mtb_campaign.when_ready(function()
    guarded(profile)()
    bridge_guarded('attach', B.attach)()      -- first: get() reads the model from here on
    guarded(M.reconcile)()
    bridge_guarded('lose', B.lose)('load')
    guarded(M.apply)()
    if B.S then bridge_guarded('signature', function() B.applied = B.signature() end)() end
    guarded(M.sync_abilities)()
    -- the new campaign's first tick converts his force: looked at again when that is over
    core:get_tm():real_callback(guarded(M.sync_abilities), 1500, 'mtb_crew_sync_abilities')
    core:add_listener('tww3_mtb_crew_built', 'MilitaryForceBuildingCompleteEvent',
        function(context) return CONFIG.followed[context:building()] ~= nil end,
        guarded(function(context) M.on_built(context:building()) end), true)
    core:add_listener('tww3_mtb_crew_turn', 'FactionTurnStart',
        function(context) return context:faction():name() == HOME_FACTION end,
        guarded(function()
            if new_panel() then
                -- the model's own turn start (the screen's adapter listens to the same event) puts its orders in and takes the upkeep; its change
                -- writes the seats (B.sync). After every listener of the event (the next tick): what went without an event, then the seats.
                M.reconcile()
                M.sync_abilities()
                core:get_tm():real_callback(bridge_guarded('turn', function()
                    B.attach()
                    B.lose('turn')
                    B.sync('turn')
                end), 1, 'mtb_crew_bridge_turn')
            else
                M.reconcile()
                M.carry_out()
                M.sync_abilities()
                M.pay_upkeep()
            end
            if M.on_changed then pcall(M.on_changed) end
        end), true)
    -- The new panel: a battle about to be fought gets the seats as the model stands, also after a change no event told (a building a script
    -- stood: cm:add_building_to_force sends none, port-to-game.md 3.4). The game creates the unit from the seat list when the battle loads
    -- [предположение: after PendingBattle; the session crew_hire reads the seats in the battle].
    core:add_listener('tww3_mtb_crew_bridge_battle', 'PendingBattle', function() return B.S ~= nil and new_panel() end,
        bridge_guarded('battle', function() B.sync('battle') end), true)
end)
