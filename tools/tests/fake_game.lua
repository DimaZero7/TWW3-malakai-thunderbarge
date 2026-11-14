-- The game's side for the offline replay: the Lua of web/js/game_sim.js (the page's fake game), method for method, as the interface
-- src/tww3_mtb_ship.lua reads (docs/design/port-to-game.md, 4.1). Only for tools/lua_vectors.py: never packed into the mod.
--
--   local Fake = <this file>; local game = Fake.new(config, sim)
--     config   the ship's config (tools/ship_config.mjs): prefix, levels {key, chain, level, cost, turns}
--     sim      {turn, gold, income, demolish = 'chain' | 'step_down', built = {short keys}}
-- The interface: treasury(), treasury_mod(delta), turn(), has_building, standing, under_construction, issue_building_command,
-- cancel_construction, dismantle, on(event, fn); the page's debug and saving: debug_complete, set_gold, snapshot, restore; end_turn.

local Fake = {}

function Fake.new(config, sim)
    local G = {}
    local prefix = config.prefix
    local turn, gold, income = sim.turn, sim.gold, sim.income or 0
    local demolishMode = sim.demolish or 'chain'
    local levels, levelList = {}, {}
    for _, r in ipairs(config.levels) do
        if not levels[r.key] then levelList[#levelList + 1] = r end
        levels[r.key] = r
    end
    local built = {}
    for _, s in ipairs(sim.built or {}) do built[prefix .. s] = true end
    local queue = {}            -- the page's Map in its order: {key, turns_left, paid}
    local listeners = {}

    local function qindex(key)
        for i, q in ipairs(queue) do if q.key == key then return i end end
        return nil
    end
    function G.on(event, fn)
        listeners[event] = listeners[event] or {}
        listeners[event][#listeners[event] + 1] = fn
    end
    function G.emit(event, ctx)
        for _, fn in ipairs(listeners[event] or {}) do fn(ctx) end
    end
    function G.treasury() return gold end
    function G.treasury_mod(d) gold = gold + d end
    function G.set_gold(n) gold = n end
    function G.turn() return turn end

    function G.has_building(key)
        local row = levels[key]
        if built[key] then return true end
        for k in pairs(built) do
            local l = levels[k]
            if l and row and l.chain == row.chain and l.level > row.level then return true end
        end
        return false
    end
    function G.under_construction(key)
        local i = qindex(key)
        return i and queue[i].turns_left or nil
    end
    function G.issue_building_command(key)
        local row = levels[key]
        if not row then return false end
        if qindex(key) then G.cancel_construction(key); return true end
        if gold < row.cost then return false end
        gold = gold - row.cost
        queue[#queue + 1] = {key = key, turns_left = row.turns, paid = row.cost}
        return true
    end
    function G.cancel_construction(key)
        local i = qindex(key)
        if not i then return false end
        gold = gold + queue[i].paid
        table.remove(queue, i)
        return true
    end
    function G.standing(key) return built[key] == true end

    local function dropChain(row, cond)
        local gone = {}
        for k in pairs(built) do
            local l = levels[k]
            if l and l.chain == row.chain and cond(l) then gone[#gone + 1] = k end
        end
        for _, k in ipairs(gone) do built[k] = nil end
    end
    function G.dismantle(key)
        if not built[key] then return false end
        built[key] = nil
        local row = levels[key]
        if demolishMode == 'step_down' then
            for _, l in ipairs(levelList) do
                if l.chain == row.chain and l.level == row.level - 1 then built[l.key] = true; break end
            end
            G.emit('BuildingDemolished', {key = key})
            return true
        end
        dropChain(row, function() return true end)
        G.emit('BuildingDemolished', {key = key})
        return true
    end
    function G.debug_complete(key)
        local row = levels[key]
        if not row or G.has_building(key) then return false end
        local i = qindex(key)
        if i then table.remove(queue, i) end
        dropChain(row, function(l) return l.level < row.level end)
        built[key] = true
        G.emit('MilitaryForceBuildingCompleteEvent', {building = key})
        return true
    end

    function G.snapshot()
        local b, q = {}, {}
        for k in pairs(built) do b[#b + 1] = k end
        table.sort(b)
        for i, x in ipairs(queue) do q[i] = {key = x.key, turns_left = x.turns_left, paid = x.paid} end
        return {turn = turn, gold = gold, built = b, queue = q}
    end
    function G.restore(s)
        turn, gold = s.turn, s.gold
        built, queue = {}, {}
        for _, k in ipairs(s.built) do if levels[k] then built[k] = true end end
        for _, x in ipairs(s.queue) do if levels[x.key] then queue[#queue + 1] = {key = x.key, turns_left = x.turns_left, paid = x.paid} end end
    end

    function G.end_turn()
        turn = turn + 1
        gold = gold + income
        local done = {}
        for _, q in ipairs(queue) do
            q.turns_left = q.turns_left - 1
            if q.turns_left <= 0 then done[#done + 1] = q.key end
        end
        G.emit('FactionTurnStart', {turn = turn})
        for _, key in ipairs(done) do
            local i = qindex(key)
            if i then table.remove(queue, i) end
            local row = levels[key]
            dropChain(row, function(l) return l.level < row.level end)
            built[key] = true
            G.emit('MilitaryForceBuildingCompleteEvent', {building = key})
        end
    end
    return G
end

return Fake
