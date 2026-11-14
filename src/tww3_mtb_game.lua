-- The game for the airship screen's logic (src/tww3_mtb_ship.lua): the interface the page's fake game (web/js/game_sim.js, offline
-- tools/tests/fake_game.lua) has, over the campaign (docs/design/port-to-game.md, 3.3 and 4.1):
--
--   local Game = <this file>; local game = Game.new(config)        config: the ship config (tww3_mtb_ship_config.lua: prefix, levels)
--   game.treasury(), game.treasury_mod(delta), game.turn()
--   game.has_building(key)        the level or a higher one of its line stands in the horde's slots
--   game.standing(key)            exactly this level stands
--   game.under_construction(key)  the turns left while it is under construction, else nil
--   game.issue_building_command(key), game.cancel_construction(key), game.dismantle(key)
--   game.on(event, fn)            'FactionTurnStart' {turn}, 'MilitaryForceBuildingCompleteEvent' {building}, 'BuildingDemolished' {key}
--   Game.save(Ship, M, view), Game.load(Ship, M)        the module's state in the save (cm:set_saved_value / cm:get_saved_value)
--
-- What is proven in the game is used as it was proven (runs/20261104-191708: the order from the character's context, the cancel by the same
-- command, TurnsToCompletion; panel-upgrades-proposal.md 2: Dismantle on the slot). Every call still an assumption is in ASSUMED below, one
-- function each, with the probe item (tools/tests/port_probe.lua, docs/design/port-to-game.md 5, stage 1) that confirms it.
-- Loaded as a module: it returns its table and sets nothing global. Not run by the mod until the switch of src/tww3_mtb_crew_ui.lua is on.

local Game = {}

local FACTION = 'wh3_dlc25_dwf_malakai'
local SUBTYPE = 'wh3_dlc25_dwf_malakai'
local SLOTS = 'MilitaryForceContext.HordeContext.BuildingSlotList'

local function log(text) pcall(function() _G.tww3_mtb_campaign.file_log('[ship game] ' .. tostring(text)) end) end

-- ---------------- ASSUMED: each a single place, the probe item that confirms it ----------------
local ASSUMED = {}
-- The slot's construction: the level under construction and its turns. port_probe item 3 (slot reads: item_level, item_level2, turns). turns is
-- proven (191708: TurnsToCompletion = 1); which of the two key expressions answers is not.
function ASSUMED.construction(cqi, n)
    local base = SLOTS .. '.At(' .. n .. ').ConstructionItemContext'
    local okv, valid = pcall(common.get_context_value, 'CcoCampaignCharacter', cqi, 'IsContextValid(' .. base .. ')')
    if not okv or not valid then return nil end
    local key
    for _, e in ipairs({'.BuildingLevelRecordContext.Key', '.BuildingLevelContext.Key'}) do
        local ok, v = pcall(common.get_context_value, 'CcoCampaignCharacter', cqi, base .. e)
        if ok and type(v) == 'string' and v ~= '' then key = v; break end
    end
    local okt, turns = pcall(common.get_context_value, 'CcoCampaignCharacter', cqi, base .. '.TurnsToCompletion')
    if not key then return nil end
    return {key = key, turns = (okt and tonumber(turns)) or 1}
end
-- A dismantled building: the game has no event of it for a horde's slot that the mod knows (none found in the game's scripts). The adapter reads
-- the slot again a moment after its own Dismantle and tells it. port_probe item 13 (dismantle: the slot after it).
function ASSUMED.after_dismantle(fn) core:get_tm():real_callback(fn, 200, 'mtb_ship_dismantled') end
-- The order of the turn's events: the page's fake game tells FactionTurnStart first, then each completed building. In the game a completion may
-- come before the faction's turn start (port_probe item 12, the turn: the event order is logged). The adapter keeps a completion that comes before
-- the turn start of its turn and tells it right after that turn start: the module sees the page's order whatever the game's is.
ASSUMED.queue_completions = true

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
    function G.under_construction(key)
        local id = cqi()
        if not id then return nil end
        for _, s in ipairs(slots()) do
            local c = ASSUMED.construction(id, s.i)
            if c and c.key == key then return c.turns end
        end
        return nil
    end
    -- [игра: 191708] the order from the character's context, without selecting Malakai; the module reads the slot again after it (M.order)
    local function command(key, n)
        local ok, err = pcall(common.call_context_command, 'CcoCampaignCharacter', cqi(),
            'DatabaseRecordContext("CcoBuildingLevelRecord", "' .. key .. '").IssueCommandForBuildingBrowser(' .. SLOTS .. '.At(' .. n .. '))')
        if not ok then log('order ' .. key .. ': ' .. tostring(err)) end
        return ok
    end
    function G.issue_building_command(key)
        local n = slotFor(key)
        if not n then log('no slot for ' .. key); return false end
        return command(key, n)
    end
    -- [игра: 191708, stage 2b] the same command again cancels with the whole cost back (ConstructionItemContext.Cancel does not give it back)
    function G.cancel_construction(key)
        local id = cqi()
        if not id then return false end
        for _, s in ipairs(slots()) do
            local c = ASSUMED.construction(id, s.i)
            if c and c.key == key then return command(key, s.i) end
        end
        return false
    end
    -- [игра: panel-upgrades-proposal.md 2] Dismantle on the slot; the whole line goes (docs/summary.md 6). The rule whether it may: the module's
    function G.dismantle(key)
        for _, s in ipairs(slots()) do
            if s.key == key then
                local ok, err = pcall(common.call_context_command, 'CcoCampaignCharacter', cqi(), SLOTS .. '.At(' .. s.i .. ').Dismantle')
                if not ok then log('dismantle ' .. key .. ': ' .. tostring(err)); return false end
                ASSUMED.after_dismantle(function() if not G.standing(key) then emit('BuildingDemolished', {key = key}) end end)
                return true
            end
        end
        return false
    end

    function G.on(event, fn)
        listeners[event] = listeners[event] or {}
        listeners[event][#listeners[event] + 1] = fn
    end
    -- the game's events, as the module hears them
    local started, waiting = nil, {}
    core:remove_listener('tww3_mtb_ship_game_turn')
    core:remove_listener('tww3_mtb_ship_game_built')
    core:add_listener('tww3_mtb_ship_game_turn', 'FactionTurnStart', function(context) return context:faction():name() == FACTION end, function()
        started = G.turn()
        emit('FactionTurnStart', {turn = started})
        local q = waiting
        waiting = {}
        for _, key in ipairs(q) do emit('MilitaryForceBuildingCompleteEvent', {building = key}) end
    end, true)
    core:add_listener('tww3_mtb_ship_game_built', 'MilitaryForceBuildingCompleteEvent', function(context) return levels[context:building()] ~= nil end, function(context)
        local key = context:building()
        if ASSUMED.queue_completions and started ~= G.turn() then waiting[#waiting + 1] = key; return end
        emit('MilitaryForceBuildingCompleteEvent', {building = key})
    end, true)
    function G.stop()
        core:remove_listener('tww3_mtb_ship_game_turn')
        core:remove_listener('tww3_mtb_ship_game_built')
    end
    return G
end

-- The module's state in the save (docs/design/port-to-game.md 4.3): strings only, as the mod keeps its saved values (tww3_mtb_crew.lua)
function Game.save(Ship, M, view)
    for k, v in pairs(Ship.save_state(M, view)) do cm:set_saved_value(k, v) end
end
function Game.load(Ship, M)
    return Ship.load_state(M, function(k) return cm:get_saved_value(k) end)
end

Game.ASSUMED = ASSUMED
return Game
