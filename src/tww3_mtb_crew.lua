-- The barge's crew: one unit, each group of seats set to one option. The options are rows of battle_personalities in the pack
-- (data/crew_options.json, tools/crew_options.py); this module points the seats of OUR land unit at them through memreader Plus.
--
-- The game reads a unit's seat list when it creates the unit in a battle, and the list lives until the game closes. So the seats
-- are written once when a campaign starts and again when a choice changes, never during a battle. Nothing is allocated in the game.
--
-- Anything unexpected (no memreader Plus, a pattern gone after a patch, a seat list that does not look right): nothing is written,
-- the unit keeps its stock crew from the tables, the reason goes once to the log and once to the player.
--
--   tww3_mtb_crew.set('rifles', 'quarr')   choose; saved in the campaign, applied at once
--   tww3_mtb_crew.get()                    {group = option}
--   tww3_mtb_crew.status                   'applied', 'not applied', 'stock: <reason>'
local CONFIG = {} --@CONFIG@

local SAVE_PREFIX = 'mtb_crew_'
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
    if not found.land_units or not found.battle_personalities then error('tables not found') end
    tables = found
    return found
end

local function row(mr, table_pointer, key)
    local node = mr.map_find_key(mr.add(table_pointer, 0x28), key)
    if not node then error('no row ' .. key) end
    local _, data = mr.read_array(table_pointer, 0x08)
    return mr.read_pointer(data, mr.read_uint32(node, 0x20) * 8)
end

function M.get()
    local out = {}
    for group, spec in pairs(CONFIG.groups) do
        local saved = cm:get_saved_value(SAVE_PREFIX .. group)
        local option = spec.start
        for _, known in ipairs(spec.options) do
            if known == saved then option = saved end
        end
        out[group] = option
    end
    return out
end

-- The whole list is worked out and checked first; the write is the last step, so a failure leaves the unit as it was.
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

function M.set(group, option)
    local spec = CONFIG.groups[group]
    if not spec then return false, 'unknown group ' .. tostring(group) end
    for _, known in ipairs(spec.options) do
        if known == option then
            cm:set_saved_value(SAVE_PREFIX .. group, option)
            return M.apply()
        end
    end
    return false, 'unknown option ' .. tostring(option)
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

cm:add_first_tick_callback(function()
    local ok, err = pcall(M.apply)
    if not ok then report(err) end
end)
