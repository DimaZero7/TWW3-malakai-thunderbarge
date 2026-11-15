-- The game for the airship screen's logic (src/tww3_mtb_ship.lua): the interface the page's fake game (web/js/game_sim.js, offline
-- tools/tests/fake_game.lua) has, over the campaign (docs/design/port-to-game.md, 3.3, 4.1 and 8):
--
--   local Game = <this file>; local game = Game.new(config)        config: the ship config (tww3_mtb_ship_config.lua: prefix, levels)
--   game.treasury(), game.treasury_mod(delta), game.turn()
--   game.cost(key), game.dev_cost(key)   the gold and the development points the game takes for a level (CreateCost / DevelopmentPointCost
--                                        from Malakai's context; the data's when the game does not answer)
--   game.development_points()            the horde's development points now («избыток населения»; nil when not readable)
--   game.growth()                        the horde's growth: {now, per_turn, need, turns, max} (AccumulatedGrowth, GrowthPerTurn,
--                                        GrowthThresholdForPoint, TurnsUntilNextGrowthPoint, HasMaxDevelopmentPoints); nil when not readable
--   game.has_building(key)               the level or a higher one of its line stands in the horde's slots
--   game.standing(key)                   exactly this level stands
--   game.under_construction(key)         the turns left while it is under construction, else nil (0 turns: it stands already, not a construction)
--   game.issue_building_command(key)     the order. true: the slot shows it at once; 'pending': the game applies it a moment later (session 15.11:
--                                        the slot read right after the command was the old one), CommandResult {key, kind = 'order'} tells when
--                                        the slot shows it or the wait is over (refused: game.refusal(key) = the game's reason or nil)
--   game.cancel_construction(key)        the cancel, 'pending' the same way (CommandResult {key, kind = 'cancel'}). A construction of an earlier turn
--                                        opens the game's window: game.cancel_asked(key) while it waits, then CancelAnswered {key, cancelled}
--   game.dismantle(key), game.dismantling(key), game.dismantle_takes(key)   the Dismantle (after CanDismantle; never the hull); the building
--                                        stands until the turn ends, then the slot's whole building goes (its lower levels with it)
--   game.dismantle_refund(key)           the gold the game gives back when the dismantled level goes (DismantleRefundAmount; the data's rule)
--   game.blocker()                       the game's own moment the panel gives way to: nil, or 'turn' (another faction's), 'battle', 'dilemma',
--                                        'event', 'panel' (a full-screen panel of the game), 'dialog' (the game's window: dialogue_box)
--   game.on(event, fn)                   FactionTurnEnd {turn}; BuildingDemolished {key} (at Malakai's next turn start, before FactionTurnStart);
--                                        FactionTurnStart {turn}; MilitaryForceBuildingCompleteEvent {building} (after it); CommandResult;
--                                        CancelAnswered
--   game.profile_on(bool), game.profile_read(), game.invalidate()     the adapter's own time (calls and seconds per function and per context
--                                        expression), the reads cached until the next change
--   Game.save(Ship, M, view), Game.load(Ship, M)        the module's state in the save (cm:set_saved_value / cm:get_saved_value)
--
-- What the probe of 14.11 and the sessions of 14.11 and 15.11 (runs 20261114-222543, 20261114-230723, 20261115-012811) proved is used as proven:
-- the order from the character's context without a selection; the game refuses an order silently (the command answers ok) when the development
-- points are short; the game applies an order and a cancel a moment after the command, not in the same call; the construction's key is
-- BuildingLevelRecordContext.Key; a completion comes before Malakai's FactionTurnStart with the old turn number, its slot already holding the new
-- level; the cancel of an earlier turn's construction asks in the game's window («Отменить строительство»); a Dismantle leaves the building
-- standing until the turn ends and then the slot is empty (the lower level of the line does not come back). What is still a guess is in ASSUMED.
-- Loaded as a module: it returns its table and sets nothing global. Not run by the mod until the switch of src/tww3_mtb_crew_ui.lua is on.

local Game = {}

local FACTION = 'wh3_dlc25_dwf_malakai'
local SUBTYPE = 'wh3_dlc25_dwf_malakai_makaisson'     -- his agent subtype (src/tww3_mtb_campaign.lua; the faction key is the shorter one)
local SLOTS = 'MilitaryForceContext.HordeContext.BuildingSlotList'
local HORDE = 'MilitaryForceContext.HordeContext.'
local SAVE_DISMANTLING = 'mtb_ship_dismantling'       -- the keys whose Dismantle was given this turn, comma-separated ('' none)
local sfind = string.find_lua or string.find
local ssub = string.sub_lua or string.sub
local sgsub = string.gsub
local clock = os.clock

local function log(text) pcall(function() _G.tww3_mtb_campaign.file_log('[ship game] ' .. tostring(text)) end) end

-- ---------------- the profile: calls and seconds per function of the adapter and per context expression ----------------
local P = nil         -- nil: off (the cost is one test per call)
local function pattern(expr)
    -- the expression without its keys and slot numbers: one row per kind of read
    return (sgsub(sgsub(expr, '"[^"]*"', '"*"'), 'At%(%d+%)', 'At(n)'))
end
local function count(where, name, seconds)
    local row = where[name]
    if not row then row = {calls = 0, seconds = 0}; where[name] = row end
    row.calls = row.calls + 1
    row.seconds = row.seconds + seconds
end

-- one read of Malakai's context: the value, or nil when the expression does not answer
local function read(cqi, expr)
    if not cqi then return nil end
    local t0 = P and clock()
    local ok, v = pcall(common.get_context_value, 'CcoCampaignCharacter', cqi, expr)
    if P then
        local s = clock() - t0
        count(P.expr, pattern(expr), s)
        P.reads, P.read_seconds = P.reads + 1, P.read_seconds + s
    end
    if ok then return v end
    return nil
end
local function record(key) return 'DatabaseRecordContext("CcoBuildingLevelRecord", "' .. key .. '")' end
local function slot(n) return SLOTS .. '.At(' .. n .. ')' end

-- ---------------- ASSUMED: each a single place ----------------
local ASSUMED = {}
-- The slot's construction: its level and the turns left. The key is BuildingLevelRecordContext.Key (probe 14.11, items 1, 2, 12: the other
-- expression never answered). At the moment of its completion the construction is still there with 0 turns while the level already stands
-- (8.2): 0 turns is no construction. TurnsToCompletion read (session 15.11: 1 and 2 as ordered).
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
-- A command is applied by the game a moment later (session 15.11: an order read at once was not there, read 1.5 s later it was, gold taken):
-- the slot is read again this often, and the command given up (refused) after this long (ms)
ASSUMED.command_poll_ms, ASSUMED.command_wait_ms = 100, 1000
-- The cancel of an earlier turn's construction: the game's window «Отменить строительство» (probe 14.11 item 12; session 15.11 ss_cancel_dialog)
-- has come when the construction is still there this long after the command (ms) and the order was not given in this turn by this panel
ASSUMED.ask_after_ms = 300
-- How often the slot is read again while the game's window is open, and for how long at most (ms)
ASSUMED.cancel_poll_ms, ASSUMED.cancel_poll_max_ms = 250, 600000
-- The game's window: a handle the game itself gave (PanelOpenedCampaign's component, or the parent of a clicked button_tick / button_cancel),
-- else the parent of the first ok_group, else a dialogue_box found by name; each only when it is on the screen. The dialogue_box's name alone
-- is not enough: session 15.11 found the HUD's hidden hud_campaign > rush_confirmation_holder > dialogue_box (ui/campaign ui/hud_campaign.twui.xml;
-- Visible true, VisibleFromRoot false, no dy_text) both with and without the cancel window on the screen: a search by name finds it first.
-- ok_group is a child of the game's popup only (ui/common ui/dialogue_box.twui.xml and dialogue_box_qr; the HUD's copy has none; else only a
-- developer's test layout). -> the component or nil
function ASSUMED.dialog(handle)
    local ok, found = pcall(function()
        if handle and handle:VisibleFromRoot() then return handle end
        local root = core:get_ui_root()
        local og = find_uicomponent(root, 'ok_group')
        if og then
            local db = UIComponent(og:Parent())
            if db and db:VisibleFromRoot() then return db end
        end
        local db = find_uicomponent(root, 'dialogue_box')
        if db and db:VisibleFromRoot() then return db end
        return nil
    end)
    if ok then return found end
    return nil
end
-- The window's buttons, by the layout ui/common ui/dialogue_box.twui.xml: dialogue_box/both_group/button_tick and button_cancel (a
-- purchase_options/button_cancel is there too, hidden: a name alone may find it)
ASSUMED.TICK, ASSUMED.CROSS = 'button_tick', 'button_cancel'
-- A Dismantle that the game executes at once after all (not seen: the runs of 03.11, 14.11 and 15.11 show the building until the turn ends): the
-- slot is read again this long after the command and the building told gone then
ASSUMED.dismantle_check_ms = 300
-- What a dismantle gives back (session 15.11, run 20261115-065150: +600 at the turn «Манекен для учебной стрельбы» of 1000 went; the game's data:
-- campaign_variables building_dismantle_recoup_multiplier_when_full_health 0.6, _when_damaged 0.3, _when_ruined 0.1; the game's settlement panel
-- reads BuildingContext.DismantleRefundAmount, ui/campaign ui/building_construction_popup.twui.xml). Read on the horde's slot by these expressions
-- (the first that answers a number); else the data's share of the level's own price, in per cent, rounded down. Not proven: the horde slot's
-- expression; the level's price or the line's; the rounding.
ASSUMED.refund_exprs = {'.BuildingContext.DismantleRefundAmount', '.DismantleRefundAmount'}
ASSUMED.refund_pct = 60
-- The game's own moments the panel gives way to, as the game's full-screen panels do. Found as the game's scripts find them (data_script.pack):
-- another faction's turn: cm:is_local_players_turn (lib_campaign_manager.lua; the HUD's buttons go inactive on IsLocalPlayersTurn false,
-- hud_campaign.twui.xml); a battle: cm:is_processing_battle (PendingBattle .. BattleCompleted), cm:model():pending_battle():is_active(); a dilemma
-- waiting for its answer: CampaignUI.DoesEventTypeRequireResponse (lib_campaign_intervention.lua); an event: the ui manager's is_event_panel_open
-- (lib_campaign_ui.lua: its flag and the events panel visible); a modal panel of the game (diplomacy, before and after a battle, a captured
-- settlement, waiting for the players), each only when it is on the screen (the manager's flags can be stale); the game's window: ASSUMED.dialog.
-- The game's other full-screen panels are not here: opening one closes ours (PanelOpenedCampaign), and a HUD button opens its panel over them
-- (the horde's own building browser comes back with every selection of Malakai: it must not shut this panel)
ASSUMED.DILEMMA = 'faction_event_dilemmaevent_feed_target_dilemma_faction'
ASSUMED.MODAL_PANELS = {'diplomacy_dropdown', 'popup_pre_battle', 'popup_battle_results', 'settlement_captured', 'waiting_for_players'}
-- The reads are kept until something changes (a command, the game's events of buildings, points and the turn) and at most this long by
-- os.clock (s): a change the adapter does not hear (a script's treasury_mod) shows at the latest by then
ASSUMED.cache_seconds = 0.25

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
    local levels, levelList = {}, {}
    for _, r in ipairs(config.levels) do
        if not levels[r.key] then levelList[#levelList + 1] = r end
        levels[r.key] = r
    end
    local listeners = {}
    local function emit(event, ctx) for _, fn in ipairs(listeners[event] or {}) do local ok, e = pcall(fn, ctx); if not ok then log(event .. ': ' .. tostring(e)) end end end
    G.emit = emit

    -- the cache of reads: everything the game says now, read once per change (the panel's refresh asks for every building many times)
    -- (one game tick at most: dropped by the game's next real callback, so what a script changed between two ticks is read again)
    local cache, cachedAt, dropping = {}, nil, false
    local function invalidate() cache = {}; cachedAt = nil end
    G.invalidate = invalidate
    local function cached(name, fn)
        local now = clock()
        if cachedAt == nil or now - cachedAt > ASSUMED.cache_seconds then
            cache = {}; cachedAt = now
            if not dropping then
                dropping = true
                pcall(function() core:get_tm():real_callback(function() dropping = false; invalidate() end, 1, 'mtb_ship_cache_drop') end)
            end
        end
        local v = cache[name]
        if v == nil then
            v = {fn()}
            cache[name] = v
        end
        return v[1]
    end

    local function cqi() return cached('cqi', function() local m = malakai(); return m and tostring(m:command_queue_index()) or nil end) end
    -- the horde's slots: {i (0 = the hull's), key or ''}; none without Malakai's force (wounded: docs/design/port-to-game.md 1.3, the panel reads only)
    local function slots()
        return cached('slots', function()
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
        end)
    end
    -- the construction of a slot ({key, turns} or false), read once per change
    local function construction(id, n)
        local c = cached('c' .. n, function() return ASSUMED.construction(id, n) or false end)
        return c or nil
    end
    -- the constructions of the force: key -> {slot, turns}
    local function constructions()
        return cached('constructions', function()
            local id, out = cqi(), {}
            if not id then return out end
            for _, s in ipairs(slots()) do
                local c = construction(id, s.i)
                if c then out[c.key] = {slot = s.i, turns = c.turns} end
            end
            return out
        end)
    end
    G.slots = function() return slots() end
    function G.treasury() return cached('gold', function() local f = cm:get_faction(FACTION); return f and f:treasury() or 0 end) end
    function G.treasury_mod(d) cm:treasury_mod(FACTION, d); invalidate() end
    function G.turn() return cm:model():turn_number() end
    -- The crew's upkeep is due only while the crew can stand on the barge (the old mod's rule, src/tww3_mtb_crew.lua paying: a human Malakai on the
    -- barge, the seats writable). SEAM: src/tww3_mtb_ship.lua's turn start asks this once patch P1 of docs/design/port-to-game.md 8.6 is in; the
    -- page's fake game has none (it always pays). true without the crew module.
    function G.crew_pays()
        local c = _G.tww3_mtb_crew
        if c and c.paying then
            local ok, v = pcall(c.paying)
            if ok then return v and true or false end
        end
        return true
    end
    -- [игра: 222543 п. 3] CreateCost(this) from his context = the pack's price, no selection needed; the data's when it does not answer
    function G.cost(key)
        return cached('cost ' .. key, function()
            local v = tonumber(read(cqi(), record(key) .. '.CreateCost(this)'))
            if v and v > 0 then return v end
            return levels[key] and levels[key].cost or 0
        end)
    end
    -- [игра: 222543 п. 3; 230723] DevelopmentPointCost(this) = the row's development_point_cost
    function G.dev_cost(key)
        return cached('dev ' .. key, function()
            local v = tonumber(read(cqi(), record(key) .. '.DevelopmentPointCost(this)'))
            if v and v >= 0 then return v end
            return levels[key] and levels[key].dev or 0
        end)
    end
    -- [игра: 222543 setup, 230723 requirement step] the horde's points (0 at the start of a campaign; the probe's script gave 50)
    function G.development_points() return cached('points', function() return tonumber(read(cqi(), HORDE .. 'DevelopmentPoints')) end) end
    -- The horde's growth, read as the game's own horde building browser reads it (ui/campaign ui/building_browser.twui.xml: GrowthPerTurn,
    -- TurnsUntilNextGrowthPoint shown as «-» when 0 or less, DevelopmentPoints, HasMaxDevelopmentPoints; ui/campaign ui/province_growth_tooltip:
    -- AccumulatedGrowth + "/" + GrowthThresholdForPoint, GrowthFactorList). The game's data: 20 growth a point, at most 50 points
    -- (campaign_variables military_force_development_point_growth_threshold, military_force_development_max_development_points).
    function G.growth()
        return cached('growth', function()
            local id = cqi()
            if not id then return nil end
            local now, per = tonumber(read(id, HORDE .. 'AccumulatedGrowth')), tonumber(read(id, HORDE .. 'GrowthPerTurn'))
            local need, turns = tonumber(read(id, HORDE .. 'GrowthThresholdForPoint')), tonumber(read(id, HORDE .. 'TurnsUntilNextGrowthPoint'))
            local max = read(id, HORDE .. 'HasMaxDevelopmentPoints')
            if now == nil and per == nil and need == nil and turns == nil then return nil end
            if turns ~= nil and turns <= 0 then turns = nil end
            return {now = now or 0, per_turn = per or 0, need = need or 0, turns = turns, max = max == true}
        end)
    end
    -- what stands, indexed once a tick: the keys standing, and the highest level standing of each chain (the panel asks has_building ~10 000
    -- times a refresh: session 15.11's profile of the fake)
    local function standingIndex()
        return cached('index', function()
            local keys, top = {}, {}
            for _, s in ipairs(slots()) do
                if s.key ~= '' then
                    keys[s.key] = true
                    local l = levels[s.key]
                    if l and (top[l.chain] == nil or l.level > top[l.chain]) then top[l.chain] = l.level end
                end
            end
            return {keys = keys, top = top}
        end)
    end
    function G.standing(key) return standingIndex().keys[key] == true end
    function G.has_building(key)
        local ix = standingIndex()
        if ix.keys[key] then return true end
        local row = levels[key]
        local t = row and ix.top[row.chain]
        return t ~= nil and t > row.level
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
            local c = construction(id, s.i)
            if c and levels[c.key] and levels[c.key].chain == row.chain then return s.i end
            if s.key == '' and s.i > 0 and not c and not empty then empty = s.i end
        end
        if row.level == 0 and row.chain == (levels[config.levels[1].key] or {}).chain then return 0 end      -- the hull's line: the main slot
        return empty
    end
    G.slot_for = slotFor
    function G.under_construction(key)
        local c = constructions()[key]
        return c and c.turns or nil
    end

    -- What can refuse an order, as the game reads it before the command (230723: HasEnoughDevelopmentPoints was the only false gate)
    local function gates(id, key, n)
        local R = record(key)
        return {active = read(id, R .. '.IsActiveForBuildingBrowser(' .. slot(n) .. ')'), enough = read(id, R .. '.HasEnoughDevelopmentPoints(this)'),
                afford = read(id, R .. '.CanAfford(this)'), locked = read(id, R .. '.IsLockedByLevel(this)'),
                points = tonumber(read(id, HORDE .. 'DevelopmentPoints')), dev = tonumber(read(id, R .. '.DevelopmentPointCost(this)'))}
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
        invalidate()
        return ok
    end
    -- the slot read again on the game's next ticks until done(elapsed ms) says so: the timer of a key, one at a time
    local waits = {}
    local function stopWait(name) waits[name] = nil; pcall(function() core:get_tm():remove_real_callback(name) end) end
    local function wait(name, every, step)
        stopWait(name)
        waits[name] = true
        local elapsed = 0
        core:get_tm():repeat_real_callback(function()
            elapsed = elapsed + every
            invalidate()
            local ok, e = pcall(step, elapsed)
            if not ok then log(name .. ': ' .. tostring(e)); stopWait(name) end
        end, every, name)
    end
    -- the orders this panel gave and the turn of each (a cancel in the same turn needs no window)
    local orderedIn = {}
    -- The order. The module orders only what it shows open: a gate of the game that says no is a disagreement, logged with the game's reasons.
    -- The command is given anyway (the game is the judge); the game applies it a moment later: the slot is read again on its next ticks.
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
        local c = construction(id, n)
        if c and c.key == key then orderedIn[key] = G.turn(); return true end
        local name = 'mtb_ship_order_' .. key
        wait(name, ASSUMED.command_poll_ms, function(elapsed)
            local now = construction(cqi(), n)
            if now and now.key == key then
                orderedIn[key] = G.turn()
                log('order ' .. key .. ' in slot ' .. n .. ': taken after ' .. elapsed .. ' ms')
            elseif elapsed < ASSUMED.command_wait_ms then
                return
            else
                refusals[key] = reasonOf(g)
                log('order ' .. key .. ' in slot ' .. n .. ' not taken (the slot read again for ' .. elapsed .. ' ms): ' .. said(refusals[key]))
            end
            stopWait(name)
            emit('CommandResult', {key = key, kind = 'order'})
        end)
        return 'pending'
    end

    -- [игра: 191708, stage 2b] the same command again cancels with the whole cost back (ConstructionItemContext.Cancel does not give it back). A
    -- construction of an earlier turn: the game asks in its window (222543 п. 12; 012811 ss_cancel_dialog) and nothing changes until it is
    -- answered. The window is the player's (as in the stock game); the answer is heard by the game's own click events on its buttons (as the
    -- game's scripts hear theirs: wh3_dlc23_labour_move.lua, wh2_dlc17_bloodgrounds.lua) and the slot read again.
    local asked, dialog, clicked = {}, nil, nil
    function G.cancel_asked(key) return asked[key] == true end
    G.dialog = function() return ASSUMED.dialog(dialog) end
    local function listenDialog(on)
        core:remove_listener('tww3_mtb_ship_game_dialog_click')
        core:remove_listener('tww3_mtb_ship_game_dialog_open')
        if not on then return end
        core:add_listener('tww3_mtb_ship_game_dialog_click', 'ComponentLClickUp', function(context)
            return context.string == ASSUMED.TICK or context.string == ASSUMED.CROSS
        end, function(context)
            -- the button's window: dialogue_box/both_group/<button> (the layout), kept as the window's handle
            local ok, db = pcall(function() return UIComponent(UIComponent(UIComponent(context.component):Parent()):Parent()) end)
            if ok and db then
                local okid, id = pcall(function() return db:Id() end)
                if okid and id == 'dialogue_box' then dialog = db end
            end
            clicked = context.string
            log('the game\'s window answered: ' .. tostring(context.string))
        end, true)
        core:add_listener('tww3_mtb_ship_game_dialog_open', 'PanelOpenedCampaign', true, function(context)
            local ok, c = pcall(function() return UIComponent(context.component) end)
            if ok and c and (context.string == 'dialogue_box' or select(2, pcall(function() return c:Id() end)) == 'dialogue_box') then dialog = c end
            log('a panel of the game opened while a cancel waits: ' .. tostring(context.string))
        end, true)
    end
    local function finishAsk(key, cancelled)
        asked[key] = nil
        stopWait('mtb_ship_cancel_ask')
        listenDialog(false)
        dialog, clicked = nil, nil
        emit('CancelAnswered', {key = key, cancelled = cancelled})
    end
    local function ask(key, n)
        asked[key] = true
        clicked = nil
        listenDialog(true)
        local answeredAt = nil
        wait('mtb_ship_cancel_ask', ASSUMED.cancel_poll_ms, function(elapsed)
            local now = construction(cqi(), n)
            if not (now and now.key == key) then finishAsk(key, true); return end
            -- answered with the cross, or the tick that changed nothing: a moment for the game to apply it, then the slot decides
            if clicked and not answeredAt then answeredAt = elapsed; return end
            if answeredAt and elapsed - answeredAt >= ASSUMED.cancel_poll_ms * 2 then finishAsk(key, false); return end
            -- the window known and gone without a click heard (Esc)
            if dialog and not ASSUMED.dialog(dialog) and not answeredAt then answeredAt = elapsed; return end
            if elapsed > ASSUMED.cancel_poll_max_ms then log('cancel ' .. key .. ': no answer of the game\'s window in ' .. elapsed .. ' ms'); finishAsk(key, false) end
        end)
    end
    function G.cancel_construction(key)
        local id = cqi()
        if not id or asked[key] then return false end
        local c = constructions()[key]
        if not c then return false end
        local n = c.slot
        command(key, n)
        local still = construction(id, n)
        if not (still and still.key == key) then return true end
        local name = 'mtb_ship_cancel_' .. key
        wait(name, ASSUMED.command_poll_ms, function(elapsed)
            local now = construction(cqi(), n)
            if now and now.key == key then
                if elapsed < ASSUMED.ask_after_ms then return end
                if orderedIn[key] ~= G.turn() then
                    -- a construction of an earlier turn (or of before a load): the game asks in its window
                    stopWait(name)
                    log('cancel ' .. key .. ': the game asks in its window (the window ' .. (ASSUMED.dialog(dialog) and 'found' or 'not found by name') .. ')')
                    ask(key, n)
                    emit('CommandResult', {key = key, kind = 'cancel'})
                    return
                end
                if elapsed < ASSUMED.command_wait_ms then return end
                log('cancel ' .. key .. ': the construction of this turn is still there after ' .. elapsed .. ' ms')
            end
            stopWait(name)
            emit('CommandResult', {key = key, kind = 'cancel'})
        end)
        return 'pending'
    end

    -- [игра: 20261103-162910; 222543 п. 12; 012811] Dismantle on the slot after its CanDismantle; the slot's whole building goes at the end of the
    -- turn (session 15.11: beer hall II dismantled, the slot empty after the turn, level I did not come back). The mark is kept in the save and
    -- checked at Malakai's next turn start (BuildingDemolished then). The hull never (CanDismantle false).
    function G.dismantle_takes(key)
        local row = levels[key]
        if not row then return {key} end
        local out = {}
        for lv = row.level, 0, -1 do
            for _, l in ipairs(levelList) do
                if l.chain == row.chain and l.level == lv then out[#out + 1] = l.key; break end
            end
        end
        return out
    end
    -- the refund the game gave for a dismantle when it was ordered (the building is gone when the turn's start tells it)
    local refunds = {}
    local function slotOf(key)
        for _, s in ipairs(slots()) do if s.key == key then return s.i end end
        return nil
    end
    local function refundRule(key)
        local row = levels[key]
        if not row then return 0 end
        local v = (tonumber(row.cost) or 0) * ASSUMED.refund_pct
        return (v - v % 100) / 100
    end
    function G.dismantle_refund(key)
        return cached('refund ' .. key, function()
            local n = slotOf(key)
            if n and n > 0 then
                local id = cqi()
                for _, e in ipairs(ASSUMED.refund_exprs) do
                    local v = tonumber(read(id, slot(n) .. e))
                    if v and v >= 0 then return v end
                end
            end
            return refunds[key] or refundRule(key)
        end)
    end
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
                invalidate()
                if not ok then log('dismantle ' .. key .. ': ' .. tostring(err)); return false end
                refunds[key] = G.dismantle_refund(key)
                marks[#marks + 1] = key
                saveMarks()
                pcall(function()
                    core:get_tm():real_callback(function()
                        invalidate()
                        if not G.standing(key) and not G.has_building(key) then
                            log('dismantle ' .. key .. ': gone at once (not at the turn end)')
                            dropMark(key)
                            emit('BuildingDemolished', {key = key, refund = refunds[key] or refundRule(key)})
                        end
                    end, ASSUMED.dismantle_check_ms, 'mtb_ship_dismantle_check')
                end)
                return true
            end
        end
        return false
    end

    -- the game's own moment the panel gives way to (ASSUMED above), or nil. Each test guarded: one the game does not answer is skipped
    local function visible(name)
        local ok, v = pcall(function() local u = find_uicomponent(core:get_ui_root(), name); return u and u:VisibleFromRoot() end)
        return ok and v and true or false
    end
    function G.blocker()
        local function try(fn) local ok, v = pcall(fn); return ok and v end
        if try(function() return cm:is_local_players_turn(true) == false end) then return 'turn' end
        if try(function() return cm:is_processing_battle() end) or try(function() return cm:model():pending_battle():is_active() end) then return 'battle' end
        if try(function() return CampaignUI.DoesEventTypeRequireResponse(ASSUMED.DILEMMA) end) then return 'dilemma' end
        local uim = try(function() return cm:get_campaign_ui_manager() end)
        if uim then
            if try(function() return uim:is_event_panel_open() end) then return 'event' end
            for _, name in ipairs(ASSUMED.MODAL_PANELS) do
                if try(function() return uim:is_panel_open(name) end) and visible(name) then return 'panel' end
            end
        end
        if ASSUMED.dialog(nil) then return 'dialog' end
        return nil
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
    local NAMES = {'tww3_mtb_ship_game_end', 'tww3_mtb_ship_game_turn', 'tww3_mtb_ship_game_built', 'tww3_mtb_ship_game_points', 'tww3_mtb_ship_game_razed'}
    for _, n in ipairs(NAMES) do core:remove_listener(n) end
    core:add_listener('tww3_mtb_ship_game_end', 'FactionTurnEnd', ours, function()
        invalidate()
        inTurn = false
        emit('FactionTurnEnd', {turn = G.turn()})
    end, true)
    core:add_listener('tww3_mtb_ship_game_turn', 'FactionTurnStart', ours, function()
        invalidate()
        inTurn = true
        -- the dismantles of the turn that ended: gone now (or not: logged, the mark dropped all the same)
        local was = marks
        marks = {}
        saveMarks()
        for _, k in ipairs(was) do
            if not G.standing(k) and not G.has_building(k) then
                local back = refunds[k] or refundRule(k)
                refunds[k] = nil
                emit('BuildingDemolished', {key = k, refund = back})
            else log('dismantle ' .. k .. ': still standing at the turn start') end
        end
        emit('FactionTurnStart', {turn = G.turn()})
        local q = waiting
        waiting = {}
        for _, key in ipairs(q) do emit('MilitaryForceBuildingCompleteEvent', {building = key}) end
    end, true)
    core:add_listener('tww3_mtb_ship_game_built', 'MilitaryForceBuildingCompleteEvent', true, function(context)
        invalidate()
        local key = context:building()
        if levels[key] == nil then return end
        if ASSUMED.queue_completions and not inTurn then waiting[#waiting + 1] = key; return end
        emit('MilitaryForceBuildingCompleteEvent', {building = key})
    end, true)
    -- what else changes what the cache holds (session 15.11 turn_events: these come for every horde of the world; the cache is only dropped)
    core:add_listener('tww3_mtb_ship_game_points', 'MilitaryForceDevelopmentPointChange', true, function() invalidate() end, true)
    core:add_listener('tww3_mtb_ship_game_razed', 'CharacterHordeBuildingDemolished', true, function() invalidate() end, true)

    function G.stop()
        for _, n in ipairs(NAMES) do core:remove_listener(n) end
        listenDialog(false)
        for name in pairs(waits) do pcall(function() core:get_tm():remove_real_callback(name) end) end
        waits = {}
        pcall(function() core:get_tm():remove_real_callback('mtb_ship_dismantle_check') end)
    end

    -- the profile: every function of G above timed (inclusive: a function's seconds hold the reads it made), the context reads by expression
    function G.profile_on(on)
        if on then P = {fn = {}, expr = {}, reads = 0, read_seconds = 0, since = clock()} else P = nil end
    end
    function G.profile_read()
        if not P then return nil end
        return {fn = P.fn, expr = P.expr, reads = P.reads, read_seconds = P.read_seconds, seconds = clock() - P.since}
    end
    local TIMED = {'treasury', 'cost', 'dev_cost', 'development_points', 'growth', 'standing', 'has_building', 'under_construction', 'slot_for',
                   'issue_building_command', 'cancel_construction', 'cancel_asked', 'dismantle', 'dismantling', 'dismantle_takes', 'refusal', 'slots'}
    for _, name in ipairs(TIMED) do
        local fn = G[name]
        G[name] = function(...)
            if not P then return fn(...) end
            local t0 = clock()
            local a, b = fn(...)
            count(P.fn, name, clock() - t0)
            return a, b
        end
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
