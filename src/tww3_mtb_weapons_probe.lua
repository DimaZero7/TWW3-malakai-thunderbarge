-- Battle probe for the weapon and empty-bay tests. Loaded from script/battle/mod/ while tww3_mtb_weapons.pack is installed
-- (tools/run_weapons.py removes it afterwards). Test units have script names starting with "t_".
-- Logs every test unit to tww3_mtb_events.jsonl and asks run_battle.py for pictures with a camera relative to a unit.
-- The line below is replaced by tools/build_weapons.py with the battle's settings.
local CONFIG = {} --@CONFIG@

if not bm then return end
if _G.tww3_mtb_weapons_probe then return end
_G.tww3_mtb_weapons_probe = true

local LOG = 'tww3_mtb_events.jsonl'
local core_common = common

local function quote(s)
    local escaped = string.gsub(tostring(s), '[%z\1-\31\\"]', function(c)
        return string.format('\\u%04x', string.byte(c))
    end)
    return '"' .. escaped .. '"'
end
local function encode(v)
    local t = type(v)
    if t == 'nil' then return 'null' end
    if t == 'boolean' then return tostring(v) end
    if t == 'number' then
        if v ~= v or v == 1/0 or v == -1/0 then return 'null' end
        return string.format('%.4f', v)
    end
    if t == 'string' then return quote(v) end
    if t == 'table' then
        local keys, array = {}, true
        for k in pairs(v) do
            keys[#keys + 1] = k
            if type(k) ~= 'number' then array = false end
        end
        local out = {}
        if array then
            for i = 1, #v do out[i] = encode(v[i]) end
            return '[' .. table.concat(out, ',') .. ']'
        end
        for i, k in ipairs(keys) do out[i] = quote(k) .. ':' .. encode(v[k]) end
        return '{' .. table.concat(out, ',') .. '}'
    end
    return quote(tostring(v))
end
local function write_line(line)
    local f = io.open(LOG, 'a')
    if f then
        f:write(line .. '\n')
        f:close()
    end
end
local started_ms = nil
local function emit(event, row)
    row = row or {}
    row.event = event
    row.model_ms = bm:time_elapsed_ms()
    if started_ms then row.battle_s = (row.model_ms - started_ms) / 1000 end
    local ok, line = pcall(encode, row)
    if not ok then
        pcall(ModLog, '[tww3_mtb] encode failed: ' .. tostring(line))
        line = '{"event":"encode_error","of":"' .. tostring(event) .. '"}'
    end
    write_line(line)
end
local finished = false
local function fail(err)
    pcall(ModLog, '[tww3_mtb] error: ' .. tostring(err))
    local ok = pcall(emit, 'error', {message = tostring(err)})
    if not ok then pcall(write_line, '{"event":"error","message":"emit failed"}') end
end
local function guarded(fn)
    return function(...)
        if finished then return end
        local ok, err = pcall(fn, ...)
        if not ok then fail(err) end
    end
end
local function read(fn)
    local ok, v = pcall(fn)
    if ok then return v end
    return 'error'
end
local function cco(u, key)
    local ok, v = pcall(function()
        return core_common.get_context_value('CcoBattleUnit', tostring(u:unique_ui_id()), key)
    end)
    if ok then return v end
    return 'error'
end
local function xyz(u)
    local ok, p = pcall(function() return u:position() end)
    if not ok or not p then return nil end
    return {p:get_x(), p:get_y(), p:get_z()}
end
local function vec(x, y, z)
    local p = battle_vector:new()
    p:set_x(x)
    p:set_y(y)
    p:set_z(z)
    return p
end

-- State ---------------------------------------------------------------------------------------------
local tests = {}        -- script name -> {unit=, army=, side=}
local test_names = {}
local others = {}       -- units that are not test units, with their side and script name
local PROFILE_CCO = {'IsGeneral', 'NumEntities', 'NumEntitiesInitial', 'HealthValue', 'HealthMax', 'HealthPercent', 'Name',
    'UnitRecordContext.Key', 'UnitRecordContext.CategoryName', 'UnitRecordContext.ClassName', 'UnitRecordContext.Caste',
    'UnitRecordContext.NumMen', 'UnitDetailsContext.NumMen', 'MaxAmmo', 'PrimaryAmmoPercent', 'SecondaryAmmoPercent',
    'IsFiringMissiles', 'WeaponStrength', 'MissileRange', 'IsFlying', 'CanFly'}
local TICK_CCO = {'HealthValue', 'HealthMax', 'NumEntities', 'NumKills', 'DamageInflictedRecently', 'PrimaryAmmoPercent',
    'SecondaryAmmoPercent', 'IsMissileAttacking', 'IsFiringMissiles'}

local function list_of(fn)
    local ok, list = pcall(fn)
    if ok and type(list) == 'table' then
        local keys = {}
        for _, k in ipairs(list) do keys[#keys + 1] = tostring(k) end
        return keys
    end
    return 'unknown'
end

local function profile(name, t)
    local u = t.unit
    local row = {unit = name, side = t.side, type = read(function() return u:type() end),
        class = read(function() return u:unit_class() end),
        is_commanding_unit = read(function() return u:is_commanding_unit() end),
        initial_men = read(function() return u:initial_number_of_men() end),
        men_alive = read(function() return u:number_of_men_alive() end),
        missile_range = read(function() return u:missile_range() end),
        ammo = read(function() return u:unary_of_missile_ammo_left() end),
        flying = read(function() return u:is_currently_flying() end),
        can_fly = read(function() return u:can_fly() end),
        abilities = list_of(function() return u:owned_non_passive_special_abilities() end),
        pos = xyz(u), cco = {}}
    for _, key in ipairs(PROFILE_CCO) do
        local v = cco(u, key)
        row.cco[key] = v == nil and 'nil' or v
    end
    emit('unit_profile', row)
end

local function nearest_enemy(t)
    local best, best_d, total = nil, nil, 0
    local p = xyz(t.unit)
    local function consider(name, side, unit)
        if side == t.side then return end
        local men = read(function() return unit:number_of_men_alive() end)
        if men == 'error' or men <= 0 then return end
        total = total + men
        local q = xyz(unit)
        if p and q then
            local d = math.sqrt((p[1] - q[1]) ^ 2 + (p[3] - q[3]) ^ 2)
            if not best_d or d < best_d then best, best_d = name, d end
        end
    end
    for _, e in ipairs(others) do consider(e.name, e.side, e.unit) end
    for _, n in ipairs(test_names) do consider(n, tests[n].side, tests[n].unit) end
    return best, best_d, total
end

local function sample()
    for _, name in ipairs(test_names) do
        local t = tests[name]
        local u = t.unit
        local nearest, dist, enemy_men = nearest_enemy(t)
        local row = {unit = name, pos = xyz(u),
            bearing = read(function() return u:bearing() end),
            moving = read(function() return u:is_moving() end),
            flying = read(function() return u:is_currently_flying() end),
            men = read(function() return u:number_of_men_alive() end),
            hp = read(function() return u:unary_hitpoints() end),
            ammo = read(function() return u:unary_of_missile_ammo_left() end),
            routing = read(function() return u:is_routing() end),
            in_melee = read(function() return u:is_in_melee() end),
            under_fire = read(function() return u:is_under_missile_attack() end),
            nearest = nearest, nearest_m = dist, enemy_men = enemy_men, cco = {}}
        for _, key in ipairs(TICK_CCO) do
            local v = cco(u, key)
            row.cco[key] = v == nil and 'nil' or v
        end
        emit('sample', row)
    end
    local rows = {}
    for _, e in ipairs(others) do
        rows[#rows + 1] = {name = e.name, side = e.side, men = read(function() return e.unit:number_of_men_alive() end),
            routing = read(function() return e.unit:is_routing() end), pos = xyz(e.unit)}
    end
    emit('others', {units = rows})
end

-- Camera, relative to a unit: f metres along its bearing, r to its right, u above its position.
local function world(unit, f, r, u_)
    local p = xyz(unit)
    local b = (read(function() return unit:bearing() end) or 0) * 3.14159265 / 180
    local fx, fz = math.sin(b), math.cos(b)
    local rx, rz = math.cos(b), -math.sin(b)
    return p[1] + fx * f + rx * r, p[2] + u_, p[3] + fz * f + rz * r
end
local function aim(shot)
    local t = tests[shot.unit]
    local cx, cy, cz = world(t.unit, shot.f, shot.r, shot.u)
    local tx, ty, tz = world(t.unit, shot.tf, shot.tr, shot.tu)
    bm:camera():move_to(vec(cx, cy, cz), vec(tx, ty, tz), 0, false, shot.fov or 0)
end
local function select_card(shot)
    local t = tests[shot.unit]
    local row = {unit = shot.unit}
    local parent = find_uicomponent(core:get_ui_root(), 'battle_orders', 'cards_panel', 'review_DY')
    row.parent = parent and true or false
    if parent then
        local id = tostring(t.unit:unique_ui_id())
        for i = 0, parent:ChildCount() - 1 do
            local uic = UIComponent(parent:Find(i))
            if uic:Id() == id then
                row.card = true
                row.state_before = uic:CurrentState()
                uic:SimulateLClick()
                uic:SimulateMouseOn()
            end
        end
    end
    local details = find_uicomponent(core:get_ui_root(), 'battle_orders', 'button_toggle_unit_details')
        or find_uicomponent(core:get_ui_root(), 'button_toggle_unit_details')
    row.details_button = details and details:CurrentState() or false
    if details and not string.find(details:CurrentState(), 'selected') then details:SimulateLClick() end
    emit('select_card', row)
end

-- One picture or a burst of pictures per shot; the camera is aimed again before each.
local function run_tour(list, done)
    local i = 0
    local step
    local function frame(shot, n)
        aim(shot)
        local name = shot.name
        if (shot.burst or 1) > 1 then name = name .. '_' .. n end
        emit('shot', {name = name, unit = shot.unit, pos = xyz(tests[shot.unit].unit)})
        if n < (shot.burst or 1) then
            bm:callback(guarded(function() frame(shot, n + 1) end), shot.burst_ms or 500, 'tww3_mtb_burst')
        else
            bm:callback(guarded(step), CONFIG.shot_gap_ms, 'tww3_mtb_shot_gap')
        end
    end
    step = function()
        i = i + 1
        local shot = list[i]
        if not shot then
            if done then done() end
            return
        end
        if shot.speed then bm:modify_battle_speed(shot.speed) end
        aim(shot)
        if shot.select then
            local ok, err = pcall(select_card, shot)
            if not ok then emit('select_card', {error = tostring(err)}) end
        end
        bm:callback(guarded(function() frame(shot, 1) end), shot.settle_ms or CONFIG.shot_settle_ms, 'tww3_mtb_shot_settle')
    end
    guarded(step)()
end

local function finish(status)
    if finished then return end
    sample()
    for _, name in ipairs(test_names) do profile(name, tests[name]) end
    emit('result', {status = status})
    finished = true
    pcall(function() bm:remove_process('tww3_mtb_tick') end)
    pcall(function() bm:end_battle() end)
end

local function controller(army, units)
    local uc = army:create_unit_controller()
    for _, u in ipairs(units) do uc:add_units(u) end
    uc:take_control()
    return uc
end

-- Enemies that stand still and do not run, so that a test unit has a target for the whole battle.
local function hold_enemies()
    for _, e in ipairs(others) do
        local ok, err = pcall(function()
            local uc = controller(e.army, {e.unit})
            local at = CONFIG.enemy_pos and CONFIG.enemy_pos[e.name]
            if at then uc:teleport_to_location(vec(at[1], 0, at[2]), at[3] or 270, at[4] or 10) end
            uc:halt()
            uc:morale_behavior_fearless()
            if CONFIG.enemy_hold_fire then uc:fire_at_will(false) end
        end)
        if not ok then emit('hold_error', {unit = e.name, err = tostring(err)}) end
    end
end

-- Orders for the test units on the scripted side.
local function order_tests()
    for _, name in ipairs(test_names) do
        local t = tests[name]
        local spec = CONFIG.orders and CONFIG.orders[name] or CONFIG.default_order
        if spec then
            local ok, err = pcall(function()
                local uc = controller(t.army, {t.unit})
                t.uc = uc
                uc:fire_at_will(true)
                if spec.melee ~= nil then uc:melee(spec.melee) end
                if spec.attack_nearest then
                    local n = nearest_enemy(t)
                    for _, e in ipairs(others) do
                        if e.name == n then uc:attack_unit(e.unit, true, true) end
                    end
                end
                if spec.halt then uc:halt() end
            end)
            emit('order', {unit = name, spec = spec, ok = ok, err = ok and nil or tostring(err)})
        end
    end
end

local function start()
    if started_ms then return end
    started_ms = bm:time_elapsed_ms()
    bm:change_victory_countdown_limit(-1)
    bm:modify_battle_speed(CONFIG.speed or 1)
    emit('start', {})
    for _, name in ipairs(test_names) do profile(name, tests[name]) end
    sample()
    if CONFIG.enemy_hold then hold_enemies() end
    bm:repeat_callback(guarded(function()
        sample()
        local t = (bm:time_elapsed_ms() - started_ms) / 1000
        if t >= CONFIG.end_s then finish('completed') end
    end), CONFIG.tick_ms, 'tww3_mtb_tick')
    if CONFIG.watch_ms then
        -- Health of the other units, often: one drop per hit on a target with a single entity.
        bm:repeat_callback(guarded(function()
            local row = {}
            for _, e in ipairs(others) do
                row[e.name] = cco(e.unit, 'HealthValue')
            end
            emit('watch', {hp = row})
        end), CONFIG.watch_ms, 'tww3_mtb_watch')
    end
    if CONFIG.orders_at_ms then
        bm:callback(guarded(order_tests), CONFIG.orders_at_ms, 'tww3_mtb_orders')
    end
    bm:callback(guarded(function()
        run_tour(CONFIG.tour, guarded(function()
            emit('photoshoot_done', {})
            bm:modify_battle_speed(CONFIG.speed or 1)
            if CONFIG.end_after_tour_ms then
                bm:callback(guarded(function() finish('completed') end), CONFIG.end_after_tour_ms, 'tww3_mtb_end')
            end
        end))
    end), CONFIG.tour_at_ms, 'tww3_mtb_tour')
end

local function initialise()
    emit('loaded', {})
    local alliances = bm:alliances()
    for side = 1, alliances:count() do
        local armies = alliances:item(side):armies()
        for a = 1, armies:count() do
            local army = armies:item(a)
            local units = army:units()
            for i = 1, units:count() do
                local u = units:item(i)
                local name = u:name()
                if string.sub(name, 1, 2) == 't_' then
                    tests[name] = {unit = u, army = army, side = side}
                    test_names[#test_names + 1] = name
                else
                    others[#others + 1] = {unit = u, army = army, side = side, name = name}
                end
            end
        end
    end
    emit('ready', {phase = read(function() return bm:get_current_phase_name() end), tests = test_names})
    for _, name in ipairs(test_names) do profile(name, tests[name]) end
    bm:register_phase_change_callback('Deployed', guarded(start))
    local function deployment()
        bm:callback(guarded(function() bm:end_current_battle_phase() end), 1000, 'tww3_mtb_deployment_end')
    end
    bm:register_phase_change_callback('Deployment', guarded(deployment))
    local phase = bm:get_current_phase_name()
    if phase == 'Deployment' then deployment() end
    if phase == 'Deployed' then guarded(start)() end
end

guarded(initialise)()
