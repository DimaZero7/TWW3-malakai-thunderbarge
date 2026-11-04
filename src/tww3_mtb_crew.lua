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
--   tww3_mtb_crew.get()                    {group = option}
--   tww3_mtb_crew.unlocked()               {group = {option = true}}
--   tww3_mtb_crew.status                   'applied', 'not applied', 'stock: <reason>'
--
-- A human Malakai's buildings only unlock options (CONFIG.buildings, from data/crew_options.json); the player places them in the crew panel
-- (src/tww3_mtb_crew_ui.lua). Only the buildings of CONFIG.auto_active also set their option. The built list is saved and the unlocked set is
-- worked out from it: a building that no longer stands leaves it and locks its option again, and if that option stood in the barge the group goes
-- to what its latest still standing building unlocks, or to its start, with one message to the player. A higher level of the same chain counts as
-- the lower one still standing. Under the AI nothing follows: start_ai.
--
-- The panel orders, the turn carries out: what stands now stays for all battles of this turn, an order goes in at the faction's turn start, with the upkeep.
-- One order per group per turn, kept in the save; picking what stands now takes the order back, which uses that turn's change. A demolished building acts at
-- once and takes back an order for what it unlocked, and does not count as the group's change. The first barge's pirates (CONFIG.auto_active) stand at once.
--
-- Upkeep: paid from the treasury at the faction's turn start for what stands, only while he is on the barge and the crew can be written.
--
-- Two kinds of group are not seats to choose. always: the group holds that option whatever is saved (the deck crew). off_bundle: no seats, an ability the unit
-- has by its tables; an effect bundle on Malakai's force takes it away while the group is on its start (the harpoon). Without memreader Plus and under the AI
-- there is no bundle: the unit has the ability, as stock. The harpoon's model comes from the hull's animation table, so the land unit's pointer to its mount row is
-- written with the seats: one mount has the table with the harpoon, the other a copy without it. The game reads it when it creates the unit.
local CONFIG = {} --@CONFIG@

local SAVE_PREFIX = 'mtb_crew_'
local HOME_FACTION = 'wh3_dlc25_dwf_malakai'
local PROFILE = SAVE_PREFIX .. 'profile'    -- saved: 'player' or 'ai', decided once, when the campaign starts
local BUILT = SAVE_PREFIX .. 'built'        -- saved: 'key@turn,key@turn', oldest first
local ORDER, CHANGED = SAVE_PREFIX .. 'order_', SAVE_PREFIX .. 'changed_'    -- saved per group: the option ordered; the turn of its last change
local PAID = SAVE_PREFIX .. 'paid'          -- saved: the turn the upkeep was last paid on
local ANCILLARY = 'mtb_anc_mount_dwf_malakai_thunderbarge'
local DB_ROOT = '48 8B 0D ?? ?? ?? ?? 4C 8B C0 48 8B 91 ?? ?? ?? ?? 48 8B CB E8 ?? ?? ?? ?? 48 85 C0 74 ?? 48 8B 0D ?? ?? ?? ?? 48 89 81'
local TABLE_MARK = '48 8D 41 28 48 89 02 48 8B 41 58 49 89 00 C3'
local TABLE_SLOTS, TABLE_SLOT_SIZE = 1812, 0x38
-- Land unit record: the vector of autonomous riders. Seat: row pointer, pointer to the attachment name.
local SEATS_CAPACITY, SEATS_SIZE, SEATS_DATA, SEAT_STRIDE, SEAT_NAME = 0x48, 0x4c, 0x50, 0x18, 8
local ROW_KEY = 8

local M = {status = 'not applied', writes = 0, patterns = {root = DB_ROOT, mark = TABLE_MARK}}
_G.tww3_mtb_crew = M

local reported = false
local tables = nil      -- {name = table pointer}; only read, one scan per game mode

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

function M.get()
    local out = {}
    local field = profile() == 'player' and 'start' or 'start_ai'
    for group, spec in pairs(CONFIG.groups) do
        local saved = cm:get_saved_value(SAVE_PREFIX .. group)
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
    for group, spec in pairs(CONFIG.groups) do
        if spec.mount_on then
            local on, off = row(mr, found.mounts, spec.mount_on), row(mr, found.mounts, spec.mount_off)
            if not mount_offset then
                for o = 0, 0x400, 8 do
                    local v = mr.read_pointer(land_unit, o)
                    if v == on or v == off then
                        mount_offset = o
                        break
                    end
                end
                log('mount at ' .. tostring(mount_offset))
            end
            if not mount_offset then error('the mount of the land unit is not found') end
            local wanted = choice[group] == spec.start and off or on
            local current = mr.read_pointer(land_unit, mount_offset)
            if current ~= on and current ~= off then error('the land unit has another mount') end
            if current ~= wanted then mr.write(land_unit, mount_offset, wanted) end
        end
    end
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
    local wanted = {}
    for group, spec in pairs(CONFIG.groups) do
        for _, seat in ipairs(spec.seats) do wanted[seat] = CONFIG.seats[seat][choice[group]] end
    end
    -- The plain ship: the holes of the bays that are not there.
    local patch_code = (choice.cannons == 'none' and 'c' or '') .. (choice.bombs == 'none' and 'b' or '')
    wanted[CONFIG.patch_seat] = CONFIG.patch_rows[patch_code == '' and 'none' or patch_code]
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

function M.apply()
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

-- On foot, under the AI or with a stock crew nothing is paid.
local function paying()
    if profile() ~= 'player' or string.sub(tostring(M.status), 1, 5) == 'stock' then return false end
    local malakai = _G.tww3_mtb_campaign and _G.tww3_mtb_campaign.find_malakai()
    return malakai and malakai:has_ancillary(ANCILLARY) or false
end

function M.upkeep()
    if not paying() then return 0, 0 end
    local choice = M.get()
    local now = sum_upkeep(choice)
    for group in pairs(CONFIG.groups) do
        choice[group] = cm:get_saved_value(ORDER .. group) or choice[group]
    end
    return now, sum_upkeep(choice)
end

function M.upkeep_of(group, option)
    return (CONFIG.upkeep[group] or {})[option] or 0
end

-- Paid once at each of the faction's turn starts, for what stands then. The game's flat income effect does not take a negative value (run panel_main, 04.11):
-- so straight from the treasury, and the panel and the log show it.
function M.pay_upkeep()
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
        local binding = CONFIG.buildings[item.key]
        if binding then out[binding.group][binding.option] = true end
    end
    return out
end

-- Has the group its bay? The building of its mount option makes it. A group without a mount always has.
function M.mount_ready(group)
    local spec = CONFIG.groups[group]
    return not spec.mount or M.unlocked()[group][spec.mount] == true
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
    local open = M.unlocked()[group]
    if not open then return false, 'unknown group ' .. tostring(group) end
    if CONFIG.groups[group].always then return false, 'not a choice ' .. group end
    if not open[option] then return false, 'locked ' .. tostring(option) end
    if not M.mount_ready(group) then return false, 'no mount ' .. group end
    if option == CONFIG.groups[group].start and CONFIG.groups[group].mount then return false, 'not a choice ' .. option end
    local current, order = M.get()[group], cm:get_saved_value(ORDER .. group)
    if M.changed(group) then
        if order and option == current then
            cm:set_saved_value(ORDER .. group, false)
            log('order taken back ' .. group)
            if M.on_changed then pcall(M.on_changed) end
            return true
        end
        return false, 'changed this turn'
    end
    if option == current then return true end
    cm:set_saved_value(ORDER .. group, option)
    cm:set_saved_value(CHANGED .. group, cm:turn_number())
    log('order ' .. group .. '=' .. option)
    if M.on_changed then pcall(M.on_changed) end
    return true
end

-- The faction's turn start: the orders go in.
function M.carry_out()
    if profile() ~= 'player' then return end
    for group, option in pairs(M.orders()) do
        cm:set_saved_value(ORDER .. group, false)
        log('order done ' .. group .. '=' .. option)
        M.set(group, option)
    end
end

-- A building of the table is complete: its option is unlocked. It becomes active only for the buildings of CONFIG.auto_active.
function M.on_built(key)
    local binding = CONFIG.buildings[key]
    if not binding or profile() ~= 'player' then return false end
    local list = {}
    for _, item in ipairs(read_built()) do
        if item.key ~= key then list[#list + 1] = item end
    end
    list[#list + 1] = {key = key, turn = cm:turn_number()}
    write_built(list)
    log('built ' .. key .. ': unlocked ' .. binding.group .. '=' .. binding.option)
    if M.on_unlocked then pcall(M.on_unlocked, binding.group, binding.option) end
    -- The first pirates, and a bare mount: it appears at once, in a group that had nothing.
    if CONFIG.auto_active[key] and M.get()[binding.group] == CONFIG.groups[binding.group].start then return M.set(binding.group, binding.option) end
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
    for group, option in pairs(M.orders()) do
        if not open[group][option] or not M.mount_ready(group) then
            cm:set_saved_value(ORDER .. group, false)
            log('order gone with its building ' .. group .. '=' .. option)
        end
    end
    for group, spec in pairs(CONFIG.groups) do
        if not open[group][active[group]] or (active[group] ~= spec.start and not M.mount_ready(group)) then
            local option = spec.start
            if M.mount_ready(group) then
                for _, item in ipairs(kept) do
                    local binding = CONFIG.buildings[item.key]
                    if binding and binding.group == group then option = binding.option end
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

local function guarded(fn)
    return function(...)
        local ok, err = pcall(fn, ...)
        if not ok then report(err) end
    end
end

_G.tww3_mtb_campaign.when_ready(function()
    guarded(profile)()
    guarded(M.reconcile)()
    guarded(M.apply)()
    guarded(M.sync_abilities)()
    -- the new campaign's first tick converts his force: looked at again when that is over
    core:get_tm():real_callback(guarded(M.sync_abilities), 1500, 'mtb_crew_sync_abilities')
    core:add_listener('tww3_mtb_crew_built', 'MilitaryForceBuildingCompleteEvent',
        function(context) return CONFIG.buildings[context:building()] ~= nil end,
        guarded(function(context) M.on_built(context:building()) end), true)
    core:add_listener('tww3_mtb_crew_turn', 'FactionTurnStart',
        function(context) return context:faction():name() == HOME_FACTION end,
        guarded(function()
            M.reconcile()
            M.carry_out()
            M.sync_abilities()
            M.pay_upkeep()
            if M.on_changed then pcall(M.on_changed) end
        end), true)
end)
