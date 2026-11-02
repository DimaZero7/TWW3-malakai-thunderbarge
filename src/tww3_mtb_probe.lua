-- Battle probe of the Malakai barge lord. Loaded by the game from script/battle/mod/ in every
-- battle while the pack is installed (tools/run_battle.py removes it afterwards).
-- Writes tww3_mtb_events.jsonl in the game's working directory; run_battle.py copies it to build/.
-- The line below is replaced by tools/build.py with the run's settings.
local CONFIG = {} --@CONFIG@

if not bm then return end
if _G.tww3_mtb_probe then return end
_G.tww3_mtb_probe = true

local LOG = 'tww3_mtb_events.jsonl'
local core_common = common

-- JSON ------------------------------------------------------------------------------------------
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

-- Safe reads -------------------------------------------------------------------------------------
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
local lord, lord_army, lord_uc
local enemies = {}
local start_pos, barge_y

local function list_of(fn)
    local ok, list = pcall(fn)
    if ok and type(list) == 'table' then
        local keys = {}
        for _, k in ipairs(list) do keys[#keys + 1] = tostring(k) end
        return keys
    end
    return 'unknown'
end

local CCO_KEYS = {'IsGeneral', 'IsCharacter', 'HasCharacterRank', 'CharacterRank', 'IsRenown', 'IsSpawnedUnit',
    'NumEntities', 'NumEntitiesInitial', 'HealthValue', 'HealthMax', 'Name', 'UnitRecordContext.Key',
    'UnitRecordContext.IsRenown', 'UnitRecordContext.Caste', 'UnitRecordContext.UnitCaste',
    'UnitRecordContext.LandUnitContext.Key', 'UnitRecordContext.CategoryName', 'UnitRecordContext.ClassName',
    'UnitDetailsContext.Mass', 'UnitDetailsContext.IsGeneral', 'UnitDetailsContext.IsCharacter',
    'CommanderContext.Name', 'CharacterContext.Name', 'AgentSubtypeRecordContext.Key'}

local function profile(u, tag)
    local row = {tag = tag, name = read(function() return u:name() end),
        type = read(function() return u:type() end),
        class = read(function() return u:unit_class() end),
        is_commanding_unit = read(function() return u:is_commanding_unit() end),
        initial_men = read(function() return u:initial_number_of_men() end),
        men_alive = read(function() return u:number_of_men_alive() end),
        missile_range = read(function() return u:missile_range() end),
        flying = read(function() return u:is_currently_flying() end),
        can_fly = read(function() return u:can_fly() end),
        is_war_machine = read(function() return u:is_war_machine() end),
        is_artillery = read(function() return u:is_artillery() end),
        abilities_active = list_of(function() return u:owned_non_passive_special_abilities() end),
        abilities_passive = list_of(function() return u:owned_passive_special_abilities() end),
        pos = xyz(u), cco = {}}
    for _, key in ipairs(CCO_KEYS) do
        local v = cco(u, key)
        row.cco[key] = v == nil and 'nil' or v
    end
    emit('unit_profile', row)
end

local function commander_check()
    local gen = read(function() return bm:get_general(lord_army) end)
    local gen_name = read(function() return gen and gen ~= 'error' and gen:name() or false end)
    local sunit_general = read(function()
        local all = script_units:new('tww3_mtb_army')
        local units = lord_army:units()
        for i = 1, units:count() do
            all:add_sunits(script_unit:new(units:item(i)))
        end
        local general = all:get_general_sunit()
        return {count = all:num_generals(), name = general.unit:name(), type = general.unit:type()}
    end)
    emit('commander_check', {
        unit_name = read(function() return lord:name() end),
        unit_type = read(function() return lord:type() end),
        is_commanding_unit = read(function() return lord:is_commanding_unit() end),
        bm_get_general_name = gen_name,
        script_units_general = sunit_general,
        army_is_commander_alive = read(function() return lord_army:is_commander_alive() end),
        army_is_commander_invincible = read(function() return lord_army:is_commander_invincible() end),
        cco_is_general = cco(lord, 'IsGeneral'),
        cco_is_character = cco(lord, 'IsCharacter'),
    })
end

local function enemy_men()
    local total = 0
    for _, e in ipairs(enemies) do
        total = total + (read(function() return e:number_of_men_alive() end) or 0)
    end
    return total
end

local function distance_nearest_enemy()
    local p = xyz(lord)
    if not p then return nil end
    local best
    for _, e in ipairs(enemies) do
        local q = xyz(e)
        if q and read(function() return e:number_of_men_alive() end) ~= 0 then
            local d = math.sqrt((p[1] - q[1]) ^ 2 + (p[3] - q[3]) ^ 2)
            if not best or d < best then best = d end
        end
    end
    return best
end

local function sample()
    emit('sample', {pos = xyz(lord),
        bearing = read(function() return lord:bearing() end),
        moving = read(function() return lord:is_moving() end),
        men = read(function() return lord:number_of_men_alive() end),
        hp = read(function() return lord:unary_hitpoints() end),
        ammo = read(function() return lord:unary_of_missile_ammo_left() end),
        ammo_cco = cco(lord, 'PrimaryAmmoPercent'),
        firing = cco(lord, 'IsFiringMissiles'),
        kills = cco(lord, 'NumKills'),
        damage_recent = cco(lord, 'DamageInflictedRecently'),
        commanding = read(function() return lord:is_commanding_unit() end),
        routing = read(function() return lord:is_routing() end),
        shattered = read(function() return lord:is_shattered() end),
        withdrawing = cco(lord, 'IsWithdrawing'),
        passive = list_of(function() return lord:owned_passive_special_abilities() end),
        enemy_men = enemy_men(),
        nearest_enemy_m = distance_nearest_enemy(),
        terrain_y = read(function()
            local p = xyz(lord)
            return bm:get_terrain_height(p[1], p[3])
        end)})
end

-- Selects the unit by clicking its card, opens the details panel; logs what it found.
local function select_card(shot)
    local row = {}
    local uic_parent = find_uicomponent(core:get_ui_root(), 'battle_orders', 'cards_panel', 'review_DY')
    row.parent = uic_parent and true or false
    if uic_parent then
        local id = tostring(lord:unique_ui_id())
        for i = 0, uic_parent:ChildCount() - 1 do
            local uic = UIComponent(uic_parent:Find(i))
            if uic:Id() == id then
                row.card = true
                row.state_before = uic:CurrentState()
                uic:SimulateLClick()
                if shot.hover then uic:SimulateMouseOn() end
            end
        end
    end
    local details = find_uicomponent(core:get_ui_root(), 'battle_orders', 'button_toggle_unit_details')
        or find_uicomponent(core:get_ui_root(), 'button_toggle_unit_details')
    row.details_button = details and details:CurrentState() or false
    if details and not string.find(details:CurrentState(), 'selected') then details:SimulateLClick() end
    emit('select_card', row)
end

-- Camera, relative to the barge: f metres along its bearing, r to its right, u above its position.
local function world(f, r, u_)
    local p = xyz(lord)
    local b = (read(function() return lord:bearing() end) or 0) * 3.14159265 / 180
    local fx, fz = math.sin(b), math.cos(b)
    local rx, rz = math.cos(b), -math.sin(b)
    local base_y = p[2]
    return p[1] + fx * f + rx * r, base_y + u_, p[3] + fz * f + rz * r
end

local function aim(shot)
    local cx, cy, cz = world(shot.f, shot.r, shot.u)
    local tx, ty, tz = world(shot.tf, shot.tr, shot.tu)
    bm:camera():move_to(vec(cx, cy, cz), vec(tx, ty, tz), 0, false, shot.fov or 0)
end

-- Runs the shots one by one: aim, wait for the picture to settle, ask for a capture.
local function run_shots(list, done)
    local i = 0
    local function step()
        i = i + 1
        local shot = list[i]
        if not shot then
            if done then done() end
            return
        end
        aim(shot)
        if shot.select then
            local ok, err = pcall(select_card, shot)
            if not ok then emit('select_card', {error = tostring(err)}) end
        end
        bm:callback(guarded(function()
            aim(shot)
            emit('shot', {name = shot.name, pos = xyz(lord)})
            bm:callback(guarded(step), CONFIG.shot_gap_ms, 'tww3_mtb_shot_gap')
        end), CONFIG.shot_settle_ms, 'tww3_mtb_shot_settle')
    end
    guarded(step)()
end

local function finish(status)
    if finished then return end
    sample()
    commander_check()
    profile(lord, 'end')
    emit('result', {status = status})
    finished = true
    pcall(function() bm:remove_process('tww3_mtb_tick') end)
    pcall(function() bm:end_battle() end)
end

local function fight_stage()
    bm:modify_battle_speed(CONFIG.fight_speed)
    lord_uc = lord_army:create_unit_controller()
    lord_uc:add_units(lord)
    lord_uc:take_control()
    local target = enemies[1]
    for _, e in ipairs(enemies) do
        if read(function() return e:missile_range() end) == 0 then target = e end
    end
    -- Move first (proof of movement) towards the enemy line, then an attack order.
    local p = xyz(lord)
    local q = xyz(target)
    local dx, dz = q[1] - p[1], q[3] - p[3]
    local len = math.sqrt(dx * dx + dz * dz)
    local goal = vec(p[1] + dx / len * CONFIG.move_m, p[2], p[3] + dz / len * CONFIG.move_m)
    lord_uc:goto_location(goal, true)
    emit('order', {kind = 'move', goal = {goal:get_x(), goal:get_y(), goal:get_z()}})
    bm:callback(guarded(function()
        emit('order', {kind = 'attack', target = read(function() return target:name() end)})
        lord_uc:melee(false)
        lord_uc:fire_at_will(true)
        lord_uc:attack_unit(target, true, true)
    end), CONFIG.attack_after_ms, 'tww3_mtb_attack')
    -- Refresh the attack order: a dead or routed target leaves the unit idle.
    bm:repeat_callback(guarded(function()
        for _, e in ipairs(enemies) do
            local men = read(function() return e:number_of_men_alive() end)
            if men ~= 0 and men ~= 'error' and not read(function() return e:is_routing() end) then
                lord_uc:attack_unit(e, true, true)
                return
            end
        end
    end), 30000, 'tww3_mtb_attack_refresh')
    -- Try the abilities (a real use, not only ownership); each result is logged.
    for _, try in ipairs(CONFIG.ability_tries) do
        bm:callback(guarded(function()
            local can = read(function() return lord:can_perform_special_ability(try.key) end)
            local ok, err = false, 'not allowed'
            if can == true then
                ok, err = pcall(function() lord_uc:perform_special_ability(try.key, lord) end)
            end
            emit('ability_try', {key = try.key, can = can, called = ok, err = ok and nil or tostring(err)})
        end), try.at_ms, 'tww3_mtb_ability_' .. try.key)
    end
    -- Evidence pictures during the fight.
    for _, stage in ipairs(CONFIG.fight_shots) do
        bm:callback(guarded(function()
            run_shots({stage})
        end), stage.at_ms, 'tww3_mtb_fight_shot_' .. stage.name)
    end
end

local function start()
    if started_ms then return end
    started_ms = bm:time_elapsed_ms()
    bm:change_victory_countdown_limit(-1)
    bm:modify_battle_speed(1)
    emit('start', {})
    profile(lord, 'start')
    commander_check()
    sample()
    bm:repeat_callback(guarded(function()
        sample()
        local t = (bm:time_elapsed_ms() - started_ms) / 1000
        if t >= CONFIG.end_s then finish('completed') end
        local alive = read(function() return lord:number_of_men_alive() end)
        if alive == 0 then finish('lord_dead') end
    end), CONFIG.tick_ms, 'tww3_mtb_tick')
    bm:callback(guarded(function()
        run_shots(CONFIG.shots, guarded(function()
            emit('photoshoot_done', {})
            fight_stage()
        end))
    end), CONFIG.first_shot_ms, 'tww3_mtb_first_shot')
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
                if u:name() == 'mtb_lord' then
                    lord, lord_army = u, army
                end
                if side == 2 then enemies[#enemies + 1] = u end
            end
        end
    end
    if not lord then error('unit mtb_lord not found') end
    emit('ready', {phase = read(function() return bm:get_current_phase_name() end),
        player_controlled = read(function() return lord_army:is_player_controlled() end)})
    profile(lord, 'loaded')
    for _, e in ipairs(enemies) do profile(e, 'enemy') end
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
