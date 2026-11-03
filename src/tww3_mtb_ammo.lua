-- Each crew group of the barge has its own ammunition, in battle (docs/design/separate-ammo.md).
--
-- The game has one unit with two pools, and a man's weapon row says which pool he uses (read at every shot). So: every group's weapon
-- is our own row (tools/crew_options.py). At the start of a battle all of them use the primary pool, which holds the sum of the groups,
-- and the secondary pool is emptied. Every 100 ms of battle time this module counts the group's new projectiles from the game's list
-- (the shooter tells the man, the man tells the group). When a group has none left, one byte in its row moves it to the empty pool: the
-- game itself says those men have no ammunition, the others go on. Lua restarts with each battle, so a new battle starts full.
--
-- Anything unexpected (no memreader Plus, a pattern gone after a patch, something that does not look right): the stock pools and bytes
-- are put back or never changed, the reason goes once to the log. Nothing is allocated in the game and no game code is changed.
--
--   tww3_mtb_ammo.read()                  {group = {ammo, start, shots, dry_at, last_shot, after_dry}}
--   tww3_mtb_ammo.report()                the same as a line
--   tww3_mtb_ammo.set_ammo(group, n)      for tests: a new start value, a dry group fires again
--   tww3_mtb_ammo.status                  'waiting', 'running', 'off: <reason>'
local CONFIG = {} --@CONFIG@

if not bm then return end

-- Battle unit: pool = {current, max, start, infinite flag}. Weapon row: the pool byte, the list of projectile rows.
local PRIMARY, SECONDARY, POOL_FLAG = 0x3d90, 0x3da0, 12
local UNIT_LAND_UNIT, UNIT_BATTLE, UNIT_RIDERS = 0x50, 0x30, 0x110
local MAN_SEAT, SEAT_ROW, SEAT_NAME, ROW_STATS, STATS_WEAPON = 0xb70, 0, 8, 0x38, 0x20
local WEAPON_POOL_BYTE, WEAPON_PROJECTILES, ROW_KEY = 0x30, 0x28, 8
local BATTLE_WORLD, WORLD_BATTLE, WORLD_PROJECTILES, ACTIVE_LIST = 0x440, 8, 0x1c8, 0x10
local PROJECTILE_SHOOTER, PROJECTILE_ROW, PROJECTILE_STATE, PROJECTILE_TIME = 0x20, 0x90, 0xc0, 0x11c
local FLYING, DONE = 0, 7
local LYING = {[5] = true, [6] = true}
local TIMER = 'tww3_mtb_ammo'
local DB_ROOT = '48 8B 0D ?? ?? ?? ?? 4C 8B C0 48 8B 91 ?? ?? ?? ?? 48 8B CB E8 ?? ?? ?? ?? 48 85 C0 74 ?? 48 8B 0D ?? ?? ?? ?? 48 89 81'
local TABLE_MARK = '48 8D 41 28 48 89 02 48 8B 41 58 49 89 00 C3'
local TABLE_SLOTS, TABLE_SLOT_SIZE = 1812, 0x38

local M = {status = 'waiting', polls = 0, engine = 0, counted = 0, ms_sum = 0, ms_max = 0, listed = 0, states = {}, others = {}, log_lines = {}, patterns = {root = DB_ROOT, mark = TABLE_MARK}}
_G.tww3_mtb_ammo = M

local mr, bu
local groups = {}       -- {key = {option, ammo, start, shots, rows, dry_at, last_shot, after_dry}}
local men = {}          -- {man pointer = {group, units, spent}}
local records = {}      -- {projectile row pointer = shots per object}
local live = {}         -- {projectile pointer = {st, t, c}}
local list_owner
local last_pool
local errors = 0
local stock_secondary
local all_rows = {}     -- {{ptr, secondary}}: every row of ours

local function log(text)
    M.log_lines[#M.log_lines + 1] = text
    pcall(ModLog, '[tww3_mtb_ammo] ' .. tostring(text))
    if _G.mtb and _G.mtb.log then pcall(_G.mtb.log, 'ammo', text) end
end

local function off(reason)
    M.status = 'off: ' .. tostring(reason)
    log(M.status)
end

local function now()
    return bm:time_elapsed_ms() / 1000
end

local function find_tables()
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
    if not found.land_units or not found.missile_weapons then error('tables not found') end
    return found
end

local function row(table_pointer, key)
    local node = mr.map_find_key(mr.add(table_pointer, 0x28), key)
    if not node then error('no row ' .. key) end
    local _, data = mr.read_array(table_pointer, 0x08)
    return mr.read_pointer(data, mr.read_uint32(node, 0x20) * 8)
end

local function weapon_row(table_pointer, key)
    local pointer = row(table_pointer, key)
    if mr.read_string(pointer, ROW_KEY) ~= key then error('row check failed: ' .. key) end
    return pointer
end

local function find_lord()
    local alliances = bm:alliances()
    for a = 1, alliances:count() do
        local armies = alliances:item(a):armies()
        for i = 1, armies:count() do
            local units = armies:item(i):units()
            for j = 1, units:count() do
                if units:item(j):type() == CONFIG.land_unit then return units:item(j) end
            end
        end
    end
end

-- The game's unit behind the script's one: the script object or a field of it, checked by its land unit row.
local function battle_unit(unit, land_unit)
    local base = mr.ud_topointer(unit)
    local function is_unit(p)
        local ok, v = pcall(mr.read_pointer, p, UNIT_LAND_UNIT)
        return ok and v == land_unit
    end
    if is_unit(base) then return base end
    for _, offset in ipairs({8, 0x10, 0x18, 0x20, 0x28}) do
        local ok, p = pcall(mr.read_pointer, base, offset)
        if ok and not mr.is_null(p) and is_unit(p) then return p end
    end
    error('no battle unit behind the script unit')
end

local function pool_of(offset)
    return {mr.read_int32(bu, offset), mr.read_int32(bu, offset + 4), mr.read_int32(bu, offset + 8), mr.read_int32(bu, offset + POOL_FLAG)}
end

local function write_pool(offset, values)
    mr.write(bu, offset, mr.uint32(values[1]))
    mr.write(bu, offset + 4, mr.uint32(values[2]))
    mr.write(bu, offset + 8, mr.uint32(values[3]))
    mr.write(bu, offset + POOL_FLAG, mr.uint32(values[4]))
end

local function set_rows(rows, secondary)
    for _, pointer in ipairs(rows) do mr.write(pointer, WEAPON_POOL_BYTE, secondary) end
end

local function sum_of(field)
    local total = 0
    for _, group in pairs(groups) do total = total + group[field] end
    return total
end

local function write_primary_total()
    local total = sum_of('start')
    write_pool(PRIMARY, {sum_of('ammo'), total, total, 0})
    last_pool = sum_of('ammo')
end

-- Looks through everything and writes last, so a failure leaves the stock pools and bytes.
local function attach(unit)
    local tables = find_tables()
    for _, check in ipairs(CONFIG.checks) do
        local pointer = weapon_row(tables.missile_weapons, check[1])
        if (mr.read_uint8(pointer, WEAPON_POOL_BYTE) ~= 0) ~= check[2] then error('pool byte of ' .. check[1] .. ' is not as expected') end
    end
    -- Memory lives until the game closes: the rows may be as the last battle left them.
    local weapon_of = {}
    for group_key, group in pairs(CONFIG.groups) do
        for option_key, option in pairs(group.options) do
            for _, weapon in ipairs(option.rows) do
                local pointer = weapon_row(tables.missile_weapons, weapon.key)
                mr.write(pointer, WEAPON_POOL_BYTE, weapon.secondary)
                all_rows[#all_rows + 1] = {pointer, weapon.secondary}
                weapon_of[weapon.key] = {group = group_key, option = option_key, spec = option}
            end
        end
    end
    local land_unit = row(tables.land_units, CONFIG.land_unit)
    bu = battle_unit(unit, land_unit)
    local size = mr.read_uint32(bu, UNIT_RIDERS + 4)
    if size ~= CONFIG.seat_count then error('riders ' .. tostring(size) .. ', not ' .. CONFIG.seat_count) end
    local primary, secondary = pool_of(PRIMARY), pool_of(SECONDARY)
    if primary[1] ~= unit:ammo_left() then error('primary pool ' .. tostring(primary[1]) .. ' is not ammo_left ' .. tostring(unit:ammo_left())) end
    local battle = mr.read_pointer(bu, UNIT_BATTLE)
    local world = mr.read_pointer(battle, BATTLE_WORLD)
    if mr.read_pointer(world, WORLD_BATTLE) ~= battle then error('world does not point back at the battle') end
    list_owner = mr.read_pointer(world, WORLD_PROJECTILES)
    -- The seats tell the groups, the weapon of each man the option. Weapon effects scale the start values as they scale the stock pool.
    local scale = primary[1] / CONFIG.primary_base
    if scale < 0.1 or scale > 10 then error('primary pool ' .. tostring(primary[1]) .. ' for a base of ' .. CONFIG.primary_base) end
    local data = mr.read_pointer(bu, UNIT_RIDERS + 8)
    local found_groups, found_men, found_records = {}, {}, {}
    for i = 0, size - 1 do
        local man = mr.read_pointer(data, i * 8)
        local seat = mr.read_pointer(man, MAN_SEAT)
        if mr.is_null(seat) then error('a man without a seat') end
        local stats = mr.read_pointer(mr.read_pointer(seat, SEAT_ROW), ROW_STATS)
        local weapon = not mr.is_null(stats) and mr.read_pointer(stats, STATS_WEAPON) or nil
        if weapon and not mr.is_null(weapon) then
            local key = mr.read_string(weapon, ROW_KEY)
            local known = weapon_of[key]
            if not known then error('a man with the weapon ' .. key .. ' that is not ours') end
            local name = mr.read_string(mr.read_pointer(seat, SEAT_NAME), 0)
            if CONFIG.seat_group[name] ~= known.group then error('seat ' .. name .. ' with a weapon of ' .. known.group) end
            local group = found_groups[known.group]
            if group and group.option ~= known.option then error('two options in ' .. known.group) end
            if not group then
                local ammo = math.max(1, math.floor(known.spec.ammo * scale + 0.5))
                group = {option = known.option, ammo = ammo, start = ammo, shots = 0, rows = {}, after_dry = 0}
                for _, row_spec in ipairs(known.spec.rows) do
                    local pointer = weapon_row(tables.missile_weapons, row_spec.key)
                    group.rows[#group.rows + 1] = pointer
                    found_records[mr.read_pointer(mr.read_pointer(pointer, WEAPON_PROJECTILES), 0)] = row_spec.per_shot
                end
                found_groups[known.group] = group
            end
            found_men[man] = {group = known.group, units = 0, spent = 0}
        end
    end
    -- Every check passed: the only writes that change anything.
    stock_secondary = secondary
    groups, men, records, live = found_groups, found_men, found_records, {}
    for _, group in pairs(groups) do set_rows(group.rows, false) end
    -- All zero: the game's full refill copies the maximum into the current value.
    write_pool(SECONDARY, {0, 0, 0, 0})
    write_primary_total()
    M.status = 'running'
    local parts = {}
    for key, group in pairs(groups) do parts[#parts + 1] = key .. '=' .. group.option .. ':' .. group.ammo end
    table.sort(parts)
    log('running, ' .. table.concat(parts, ' ') .. ' scale ' .. string.format('%.2f', scale))
end

-- Back to what the tables say, when something fails during a battle.
local function give_up(reason)
    pcall(bm.remove_callback, bm, TIMER)
    for _, item in ipairs(all_rows) do pcall(mr.write, item[1], WEAPON_POOL_BYTE, item[2]) end
    if stock_secondary then pcall(write_pool, SECONDARY, stock_secondary) end
    off(reason)
end

local function count_shot(man_state, per_shot, t)
    man_state.units = man_state.units + 1 / per_shot
    local spent = math.ceil(man_state.units - 0.001)
    local new = spent - man_state.spent
    if new <= 0 then return end
    man_state.spent = spent
    local group = groups[man_state.group]
    group.shots = group.shots + new
    M.counted = M.counted + new
    group.ammo = math.max(0, group.ammo - new)
    group.last_shot = t
    if group.dry_at then group.after_dry = group.after_dry + new end
end

local function read_list(t)
    local list = mr.read_vector(list_owner, ACTIVE_LIST, {0, 'pointer'}, 8) or {}
    if #list > M.listed then M.listed = #list end
    local c = M.polls
    for i = 1, #list do
        local p = list[i]
        if p then
            local st, age = mr.read_int32(p, PROJECTILE_STATE), mr.read_float(p, PROJECTILE_TIME)
            local known = live[p]
            -- A slot of the list is used again: the old one was done, or the flight clock went back.
            if known and ((known.st == DONE and st ~= DONE) or (st ~= DONE and not LYING[st] and age + 0.001 < known.t)) then known = nil end
            if known then
                known.st, known.t, known.c = st, age, c
            else
                live[p] = {st = st, t = age, c = c}
                local man_state = men[mr.read_pointer(p, PROJECTILE_SHOOTER)]
                if man_state then
                    M.states[st] = (M.states[st] or 0) + 1
                    if st == FLYING then
                        local record = mr.read_pointer(p, PROJECTILE_ROW)
                        local per_shot = records[record]
                        if per_shot then
                            count_shot(man_state, per_shot, t)
                        else
                            -- Not the weapon's own projectile: what a shell breaks into, or an ability.
                            local name = man_state.group
                            M.others[name] = (M.others[name] or 0) + 1
                        end
                    end
                end
            end
        end
    end
    for p, known in pairs(live) do
        if c - known.c >= 3 then live[p] = nil end
    end
end

-- The pool always holds what the groups have left. A rise of the pool is the game's own refill, an ability: it goes to the groups.
local function sync_pool(t)
    local current = mr.read_int32(bu, PRIMARY)
    local want = sum_of('ammo')
    if last_pool and current < last_pool then M.engine = M.engine + last_pool - current end
    local rise = last_pool and current - last_pool or 0
    if rise >= math.max(3, sum_of('start') * 0.02) then
        local start = sum_of('start')
        for _, group in pairs(groups) do
            group.ammo = math.min(group.start, group.ammo + math.ceil(rise * group.start / start))
        end
        want = sum_of('ammo')
        log(string.format('%.1f refill %d', t, rise))
    end
    for key, group in pairs(groups) do
        if group.ammo <= 0 and not group.dry_at then
            group.dry_at = t
            set_rows(group.rows, true)
            log(string.format('%.1f %s out of ammunition after %d shots', t, key, group.shots))
        elseif group.ammo > 0 and group.dry_at then
            group.dry_at = nil
            set_rows(group.rows, false)
            log(string.format('%.1f %s has ammunition again: %d', t, key, group.ammo))
        end
    end
    if current ~= want then mr.write(bu, PRIMARY, mr.uint32(want)) end
    last_pool = want
end

local function poll()
    local started = os.clock()
    M.polls = M.polls + 1
    local t = now()
    read_list(t)
    sync_pool(t)
    local spent = (os.clock() - started) * 1000
    M.ms_sum = M.ms_sum + spent
    if spent > M.ms_max then M.ms_max = spent end
end

local function guarded_poll()
    local ok, err = pcall(poll)
    if ok then
        errors = 0
    else
        errors = errors + 1
        if errors >= 5 then give_up('polling failed: ' .. tostring(err)) end
    end
end

function M.read()
    local out = {}
    for key, group in pairs(groups) do
        out[key] = {option = group.option, ammo = group.ammo, start = group.start, shots = group.shots, dry_at = group.dry_at,
                    last_shot = group.last_shot, after_dry = group.after_dry}
    end
    return out
end

function M.report()
    local parts = {}
    for key, group in pairs(groups) do
        parts[#parts + 1] = string.format('%s %s %d/%d shots %d dry %s last %s after %d', key, group.option, group.ammo, group.start, group.shots,
            group.dry_at and string.format('%.1f', group.dry_at) or '-', group.last_shot and string.format('%.1f', group.last_shot) or '-', group.after_dry)
    end
    table.sort(parts)
    local states = {}
    for st, n in pairs(M.states) do states[#states + 1] = st .. ':' .. n end
    table.sort(states)
    local others = {}
    for key, n in pairs(M.others) do others[#others + 1] = key .. ':' .. n end
    table.sort(others)
    return string.format('%s | t %.1f pool %d counted %d engine %d polls %d ms %.2f/%.1f list %d states %s others %s', table.concat(parts, ' | '), now(),
        bu and mr.read_int32(bu, PRIMARY) or -1, M.counted, M.engine, M.polls, M.polls > 0 and M.ms_sum / M.polls or 0, M.ms_max, M.listed,
        table.concat(states, ','), table.concat(others, ','))
end

function M.set_ammo(key, value)
    local group = groups[key]
    if not group then return false end
    group.ammo, group.start = value, value
    if M.status == 'running' then write_primary_total() end
    return true
end

local attached = false
local function try_attach()
    if attached then return end
    if not mr then
        mr = _G.memreader_plus
        if not mr then
            attached = true
            off('memreader Plus is not loaded')
            return
        end
    end
    local ok, unit = pcall(find_lord)
    if not ok or not unit then return end     -- no barge in this battle, or it has not arrived yet
    attached = true
    local done, err = pcall(attach, unit)
    if done then
        bm:repeat_callback(guarded_poll, 100, TIMER)
    else
        off(err)
    end
end
M.try_attach = try_attach

-- The barge may arrive later as reinforcements: the check is cheap.
bm:register_phase_change_callback('Deployment', try_attach)
bm:register_phase_change_callback('Deployed', function()
    try_attach()
    if not attached then bm:repeat_callback(function()
        try_attach()
        if attached then bm:remove_callback('tww3_mtb_ammo_wait') end
    end, 2000, 'tww3_mtb_ammo_wait') end
end)
if bm:get_current_phase_name() == 'Deployment' or bm:get_current_phase_name() == 'Deployed' then try_attach() end
