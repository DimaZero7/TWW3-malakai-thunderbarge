-- The game for the airship screen's logic (src/tww3_mtb_ship.lua): the interface the page's fake game (web/js/game_sim.js, offline
-- tools/tests/fake_game.lua) has, over the campaign (docs/design/port-to-game.md, 3.3, 4.1 and 8):
--
--   local Game = <this file>; local game = Game.new(config)        config: the ship config (tww3_mtb_ship_config.lua: prefix, levels)
--   game.treasury(), game.treasury_mod(delta), game.turn()
--   game.cost(key), game.dev_cost(key)   the gold and the development points the game takes for a level (CreateCost / DevelopmentPointCost
--                                        from Malakai's context; the data's when the game does not answer)
--   game.development_points()            the horde's development points now («избыток населения»; nil when not readable)
--   game.has_building(key)               the level or a higher one of its line stands in the horde's slots
--   game.standing(key)                   exactly this level stands
--   game.under_construction(key)         the turns left while it is under construction, else nil (0 turns: it stands already, not a construction)
--   game.issue_building_command(key)     the order; true when the slot read again shows it. Refused: game.refusal(key) = the game's reason or nil
--   game.cancel_construction(key)        the cancel; a construction of an earlier turn opens the game's window: game.cancel_asked(key) while it is
--                                        open, then CancelAnswered {key, cancelled}
--   game.dismantle(key), game.dismantling(key)   the Dismantle (after CanDismantle; never the hull); the building stands until the turn ends
--   game.on(event, fn)                   FactionTurnEnd {turn}; BuildingDemolished {key} (at Malakai's next turn start, before FactionTurnStart);
--                                        FactionTurnStart {turn}; MilitaryForceBuildingCompleteEvent {building} (after it); CancelAnswered
--   Game.save(Ship, M, view), Game.load(Ship, M)        the module's state in the save (cm:set_saved_value / cm:get_saved_value)
--
-- What the probe of 14.11 and the session of 14.11 (runs 20261114-222543, 20261114-230723) proved is used as proven: the order from the character's
-- context without a selection; the game refuses an order silently (the command answers ok) when the development points are short, so the slot is
-- read again after every order; the construction's key is BuildingLevelRecordContext.Key; a completion comes before Malakai's FactionTurnStart
-- with the old turn number, its slot already holding the new level; the cancel of an earlier turn's construction asks in the game's window; a
-- Dismantle leaves the building standing until the turn ends. What is still a guess is in ASSUMED, one place each.
-- Loaded as a module: it returns its table and sets nothing global. Not run by the mod until the switch of src/tww3_mtb_crew_ui.lua is on.

local Game = {}

local FACTION = 'wh3_dlc25_dwf_malakai'
local SUBTYPE = 'wh3_dlc25_dwf_malakai_makaisson'     -- his agent subtype (src/tww3_mtb_campaign.lua; the faction key is the shorter one)
local SLOTS = 'MilitaryForceContext.HordeContext.BuildingSlotList'
local SAVE_DISMANTLING = 'mtb_ship_dismantling'       -- the keys whose Dismantle was given this turn, comma-separated ('' none)
local sfind = string.find_lua or string.find
local ssub = string.sub_lua or string.sub

local function log(text) pcall(function() _G.tww3_mtb_campaign.file_log('[ship game] ' .. tostring(text)) end) end

-- one read of Malakai's context: the value, or nil when the expression does not answer
local function read(cqi, expr)
    if not cqi then return nil end
    local ok, v = pcall(common.get_context_value, 'CcoCampaignCharacter', cqi, expr)
    if ok then return v end
    return nil
end
local function record(key) return 'DatabaseRecordContext("CcoBuildingLevelRecord", "' .. key .. '")' end
local function slot(n) return SLOTS .. '.At(' .. n .. ')' end

-- ---------------- ASSUMED: each a single place ----------------
local ASSUMED = {}
-- The slot's construction: its level and the turns left. The key is BuildingLevelRecordContext.Key (probe 14.11, items 1, 2, 12: the other
-- expression never answered). At the moment of its completion the construction is still there with 0 turns while the level already stands
-- (8.2): 0 turns is no construction. TurnsToCompletion not read: still one (guess).
function ASSUMED.construction(cqi, n)
    local base = slot(n) .. '.ConstructionItemContext'
    if read(cqi, 'IsContextValid(' .. base .. ')') ~= true then return nil end
    local key = read(cqi, base .. '.BuildingLevelRecordContext.Key')
    if type(key) ~= 'string' or key == '' then return nil end
    local turns = tonumber(read(cqi, base .. '.TurnsToCompletion'))
    if turns == nil then turns = 1 end
    if turns <= 0 then return nil end
    return {key = key, turns = turns}
end
-- The order of the turn's events: completions come before Malakai's FactionTurnStart (8.2). Held while his turn is not running (from his
-- FactionTurnEnd to his FactionTurnStart) and told right after the turn start: the module sees the page's order. false: told as they come.
ASSUMED.queue_completions = true
-- The game's own confirmation window (the cancel of an earlier turn's construction): dialogue_box at the root (the game's scripts:
-- wh3_battle_prologue_values.lua), found by name, open only when visible (session 14.11: a dialogue_box was found while none was on the screen).
function ASSUMED.dialog_open()
    local ok, open = pcall(function()
        local db = find_uicomponent(core:get_ui_root(), 'dialogue_box')
        return db and db:VisibleFromRoot() and true or false
    end)
    return ok and open or false
end
-- How often the slot is read again while the game's window is open, and for how long at most (ms)
ASSUMED.cancel_poll_ms, ASSUMED.cancel_poll_max_ms = 250, 600000
-- A Dismantle that the game executes at once after all (not seen: the runs of 03.11 and 14.11 show the building until the turn ends): the slot is
-- read again this long after the command and the building told gone then
ASSUMED.dismantle_check_ms = 300

-- ---------------- the campaign ----------------
local function malakai()
    local f = cm:get_faction(FACTION)
    if not f or f:is_null_interface() then return nil end
    local cl = f:character_list()
    for i = 0, cl:num_items() - 1 do
        local c = cl:item_at(i)
        if c:character_subtype_key() == SUBTYPE and c:has_military_force() then return c end
    end
    return nil
end

function Game.new(config)
    local G = {}
    local levels = {}
    for _, r in ipairs(config.levels) do levels[r.key] = r end
    local listeners = {}
    local function emit(event, ctx) for _, fn in ipairs(listeners[event] or {}) do local ok, e = pcall(fn, ctx); if not ok then log(event .. ': ' .. tostring(e)) end end end
    G.emit = emit

    local function cqi() local m = malakai(); return m and tostring(m:command_queue_index()) or nil end
    -- the horde's slots: {i (0 = the hull's), key or ''}; none without Malakai's force (wounded: docs/design/port-to-game.md 1.3, the panel reads only)
    local function slots()
        local m = malakai()
        if not m then return {} end
        local details = m:military_force():horde_details()
        if details:is_null_interface() then return {} end
        local list, out = details:military_force_slot_list(), {}
        for i = 0, list:num_items() - 1 do
            local s = list:item_at(i)
            out[#out + 1] = {i = i, key = s:has_building() and s:building() or ''}
        end
        return out
    end
    G.slots = slots
    function G.treasury() local f = cm:get_faction(FACTION); return f and f:treasury() or 0 end
    function G.treasury_mod(d) cm:treasury_mod(FACTION, d) end
    function G.turn() return cm:model():turn_number() end
    -- [игра: 222543 п. 3] CreateCost(this) from his context = the pack's price, no selection needed; the data's when it does not answer
    function G.cost(key)
        local v = tonumber(read(cqi(), record(key) .. '.CreateCost(this)'))
        if v and v > 0 then return v end
        return levels[key] and levels[key].cost or 0
    end
    -- [игра: 222543 п. 3; 230723] DevelopmentPointCost(this) = the row's development_point_cost
    function G.dev_cost(key)
        local v = tonumber(read(cqi(), record(key) .. '.DevelopmentPointCost(this)'))
        if v and v >= 0 then return v end
        return levels[key] and levels[key].dev or 0
    end
    -- [игра: 222543 setup, 230723 requirement step] the horde's points (0 at the start of a campaign; the probe's script gave 50)
    function G.development_points() return tonumber(read(cqi(), 'MilitaryForceContext.HordeContext.DevelopmentPoints')) end
    function G.standing(key)
        for _, s in ipairs(slots()) do if s.key == key then return true end end
        return false
    end
    function G.has_building(key)
        local row = levels[key]
        for _, s in ipairs(slots()) do
            if s.key == key then return true end
            local l = levels[s.key]
            if l and row and l.chain == row.chain and l.level > row.level then return true end
        end
        return false
    end
    -- the slot a level is built in: its line's own (a level of the same chain stands or is under construction there), else the first empty side slot
    -- without a construction (the probe's orders went so: 222543 items 1, 2, 12)
    local function slotFor(key)
        local row, id = levels[key], cqi()
        if not row or not id then return nil end
        local empty
        for _, s in ipairs(slots()) do
            local l = levels[s.key]
            if l and l.chain == row.chain then return s.i end
            local c = ASSUMED.construction(id, s.i)
            if c and levels[c.key] and levels[c.key].chain == row.chain then return s.i end
            if s.key == '' and s.i > 0 and not c and not empty then empty = s.i end
        end
        if row.level == 0 and row.chain == (levels[config.levels[1].key] or {}).chain then return 0 end      -- the hull's line: the main slot
        return empty
    end
    G.slot_for = slotFor
    function G.under_construction(key)
        local id = cqi()
        if not id then return nil end
        for _, s in ipairs(slots()) do
            local c = ASSUMED.construction(id, s.i)
            if c and c.key == key then return c.turns end
        end
        return nil
    end

    -- What can refuse an order, as the game reads it before the command (230723: HasEnoughDevelopmentPoints was the only false gate)
    local function gates(id, key, n)
        local R = record(key)
        return {active = read(id, R .. '.IsActiveForBuildingBrowser(' .. slot(n) .. ')'), enough = read(id, R .. '.HasEnoughDevelopmentPoints(this)'),
                afford = read(id, R .. '.CanAfford(this)'), locked = read(id, R .. '.IsLockedByLevel(this)'),
                points = tonumber(read(id, 'MilitaryForceContext.HordeContext.DevelopmentPoints')), dev = tonumber(read(id, R .. '.DevelopmentPointCost(this)'))}
    end
    G.gates = function(key, n) return gates(cqi(), key, n or slotFor(key)) end
    local function said(v) if v == nil then return 'nil' end return tostring(v) end
    -- the game's reason of a refusal, in the words of the panel's own reasons (src/tww3_mtb_ship.lua M.reason); nil when no gate says why
    local function reasonOf(g)
        if g.enough == false then
            if g.dev and g.points then return 'не хватает избытка населения (нужно ' .. said(g.dev) .. ', есть ' .. said(g.points) .. ')' end
            return 'не хватает избытка населения'
        end
        if g.afford == false then return 'не хватает золота' end
        if g.locked == true then return 'корпус ниже нужного яруса' end
        return nil
    end
    local refusals = {}
    function G.refusal(key) return refusals[key] end
    -- [игра: 191708; 222543 пп. 1, 2] the order from the character's context, without selecting Malakai
    local function command(key, n)
        local ok, err = pcall(common.call_context_command, 'CcoCampaignCharacter', cqi(), record(key) .. '.IssueCommandForBuildingBrowser(' .. slot(n) .. ')')
        if not ok then log('order ' .. key .. ': ' .. tostring(err)) end
        return ok
    end
    -- The order. The module orders only what it shows open: a gate of the game that says no is a disagreement, logged with the game's reasons.
    -- The command is given anyway (the game is the judge), the slot read again: true when it shows the construction.
    function G.issue_building_command(key)
        refusals[key] = nil
        local n = slotFor(key)
        if not n then log('no slot for ' .. key); refusals[key] = 'на корабле нет свободного места'; return false end
        local id = cqi()
        local g = gates(id, key, n)
        if g.active ~= true then
            log('the panel offers ' .. key .. ' but the game would refuse it in slot ' .. n .. ': IsActiveForBuildingBrowser ' .. said(g.active) ..
                ', HasEnoughDevelopmentPoints ' .. said(g.enough) .. ' (' .. said(g.points) .. ' of ' .. said(g.dev) .. '), CanAfford ' .. said(g.afford) ..
                ', IsLockedByLevel ' .. said(g.locked))
        end
        command(key, n)
        local c = ASSUMED.construction(id, n)
        if c and c.key == key then return true end
        refusals[key] = reasonOf(g)
        log('order ' .. key .. ' in slot ' .. n .. ' not taken (the slot read again): ' .. said(refusals[key]))
        return false
    end

    -- [игра: 191708, stage 2b] the same command again cancels with the whole cost back (ConstructionItemContext.Cancel does not give it back). A
    -- construction of an earlier turn: the game asks in its window (222543 п. 12) and nothing changes until it is answered. The window is the
    -- player's (as in the stock game); the slot is read again until the construction is gone or the window closed.
    local asked = {}
    function G.cancel_asked(key) return asked[key] == true end
    local function finishAsk(key, cancelled)
        asked[key] = nil
        pcall(function() core:get_tm():remove_real_callback('mtb_ship_cancel_ask') end)
        emit('CancelAnswered', {key = key, cancelled = cancelled})
    end
    function G.cancel_construction(key)
        local id = cqi()
        if not id or asked[key] then return false end
        for _, s in ipairs(slots()) do
            local c = ASSUMED.construction(id, s.i)
            if c and c.key == key then
                command(key, s.i)
                local still = ASSUMED.construction(id, s.i)
                if not (still and still.key == key) then return true end
                if not ASSUMED.dialog_open() then log('cancel ' .. key .. ': the slot did not change and no window of the game is open'); return false end
                asked[key] = true
                local n, waited = s.i, 0
                core:get_tm():repeat_real_callback(function()
                    waited = waited + ASSUMED.cancel_poll_ms
                    local now = ASSUMED.construction(cqi(), n)
                    if not (now and now.key == key) then finishAsk(key, true)
                    elseif not ASSUMED.dialog_open() or waited > ASSUMED.cancel_poll_max_ms then finishAsk(key, false) end
                end, ASSUMED.cancel_poll_ms, 'mtb_ship_cancel_ask')
                return true
            end
        end
        return false
    end

    -- [игра: 20261103-162910; 222543 п. 12] Dismantle on the slot after its CanDismantle; the whole line goes (docs/summary.md 6) at the end of the
    -- turn. The mark is kept in the save and checked at Malakai's next turn start (BuildingDemolished then). The hull never (CanDismantle false).
    local marks = {}
    do
        local ok, s = pcall(function() return cm:get_saved_value(SAVE_DISMANTLING) end)
        if ok and type(s) == 'string' then
            local pos = 1
            while pos <= #s do
                local j = sfind(s, ',', pos, true) or (#s + 1)
                local k = ssub(s, pos, j - 1)
                if levels[k] then marks[#marks + 1] = k end
                pos = j + 1
            end
        end
    end
    local function saveMarks() pcall(function() cm:set_saved_value(SAVE_DISMANTLING, table.concat(marks, ',')) end) end
    function G.dismantling(key)
        local row = levels[key]
        if not row then return false end
        for _, k in ipairs(marks) do
            if levels[k].chain == row.chain and G.standing(k) then return true end
        end
        return false
    end
    local function dropMark(key)
        local keep = {}
        for _, k in ipairs(marks) do if k ~= key then keep[#keep + 1] = k end end
        marks = keep
        saveMarks()
    end
    function G.dismantle(key)
        local id = cqi()
        for _, s in ipairs(slots()) do
            if s.key == key then
                if s.i == 0 then log('dismantle ' .. key .. ': the hull is not dismantled'); return false end
                local can = read(id, slot(s.i) .. '.CanDismantle')
                if can == false then log('dismantle ' .. key .. ': CanDismantle false in slot ' .. s.i); return false end
                local ok, err = pcall(common.call_context_command, 'CcoCampaignCharacter', id, slot(s.i) .. '.Dismantle')
                if not ok then log('dismantle ' .. key .. ': ' .. tostring(err)); return false end
                marks[#marks + 1] = key
                saveMarks()
                pcall(function()
                    core:get_tm():real_callback(function()
                        if not G.standing(key) and not G.has_building(key) then
                            log('dismantle ' .. key .. ': gone at once (not at the turn end)')
                            dropMark(key)
                            emit('BuildingDemolished', {key = key})
                        end
                    end, ASSUMED.dismantle_check_ms, 'mtb_ship_dismantle_check')
                end)
                return true
            end
        end
        return false
    end

    function G.on(event, fn)
        listeners[event] = listeners[event] or {}
        listeners[event][#listeners[event] + 1] = fn
    end
    -- the game's events, as the module hears them. inTurn: Malakai's turn is running (false from his FactionTurnEnd to his FactionTurnStart;
    -- true after a load, which happens in his turn)
    local inTurn, waiting = true, {}
    G.in_turn = function() return inTurn end
    local function ours(context) local ok, f = pcall(function() return context:faction():name() end); return ok and f == FACTION end
    core:remove_listener('tww3_mtb_ship_game_end')
    core:remove_listener('tww3_mtb_ship_game_turn')
    core:remove_listener('tww3_mtb_ship_game_built')
    core:add_listener('tww3_mtb_ship_game_end', 'FactionTurnEnd', ours, function()
        inTurn = false
        emit('FactionTurnEnd', {turn = G.turn()})
    end, true)
    core:add_listener('tww3_mtb_ship_game_turn', 'FactionTurnStart', ours, function()
        inTurn = true
        -- the dismantles of the turn that ended: gone now (or not: logged, the mark dropped all the same)
        local was = marks
        marks = {}
        saveMarks()
        for _, k in ipairs(was) do
            if not G.standing(k) and not G.has_building(k) then emit('BuildingDemolished', {key = k})
            else log('dismantle ' .. k .. ': still standing at the turn start') end
        end
        emit('FactionTurnStart', {turn = G.turn()})
        local q = waiting
        waiting = {}
        for _, key in ipairs(q) do emit('MilitaryForceBuildingCompleteEvent', {building = key}) end
    end, true)
    core:add_listener('tww3_mtb_ship_game_built', 'MilitaryForceBuildingCompleteEvent', function(context) return levels[context:building()] ~= nil end, function(context)
        local key = context:building()
        if ASSUMED.queue_completions and not inTurn then waiting[#waiting + 1] = key; return end
        emit('MilitaryForceBuildingCompleteEvent', {building = key})
    end, true)
    function G.stop()
        core:remove_listener('tww3_mtb_ship_game_end')
        core:remove_listener('tww3_mtb_ship_game_turn')
        core:remove_listener('tww3_mtb_ship_game_built')
        pcall(function() core:get_tm():remove_real_callback('mtb_ship_cancel_ask') end)
        pcall(function() core:get_tm():remove_real_callback('mtb_ship_dismantle_check') end)
    end
    return G
end

-- The module's state in the save (docs/design/port-to-game.md 4.3): strings only, as the mod keeps its saved values (tww3_mtb_crew.lua). The
-- dismantle marks are saved by the game's side itself when they change (SAVE_DISMANTLING).
function Game.save(Ship, M, view)
    for k, v in pairs(Ship.save_state(M, view)) do cm:set_saved_value(k, v) end
end
function Game.load(Ship, M)
    return Ship.load_state(M, function(k) return cm:get_saved_value(k) end)
end

Game.ASSUMED = ASSUMED
Game.SAVE_DISMANTLING = SAVE_DISMANTLING
return Game
