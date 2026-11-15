-- The game's side for the offline replay: the Lua of web/js/game_sim.js (the page's fake game), method for method, as the interface
-- src/tww3_mtb_ship.lua reads (docs/design/port-to-game.md, 4.1). Only for tools/lua_vectors.py: never packed into the mod.
--
--   local Fake = <this file>; local game = Fake.new(config, sim)
--     config   the ship's config (tools/ship_config.mjs): prefix, levels {key, chain, level, cost, turns, dev}, hull_tiers
--     sim      {turn, gold, income, dev_points, growth, growth_base, growth_threshold, dev_max, ask_cancel, async, demolish = 'chain' | 'step_down',
--              built = {short keys}}
-- The interface: treasury(), treasury_mod(delta), turn(), cost, dev_cost, development_points, growth, has_building, standing, under_construction,
-- issue_building_command, refusal, cancel_construction, cancel_asked, answer_cancel, dismantle, dismantling, dismantle_takes, tick, on(event, fn);
-- the page's debug and saving: debug_complete, set_gold, snapshot, restore; end_turn (the events in the order the game's adapter hands them on:
-- FactionTurnEnd; the dismantles and completions of the game; BuildingDemolished; FactionTurnStart; each completion).

local Fake = {}

function Fake.new(config, sim)
    local G = {}
    local prefix = config.prefix
    local turn, gold, income = sim.turn, sim.gold, sim.income or 0
    local dev = sim.dev_points          -- nil: not modelled
    -- the horde's growth makes the points (game_sim.js: growth accumulated, per turn the horde's own and the standing levels' «Рост орды», a point
    -- each full threshold, at most dev_max points)
    local growthAcc, growthBase = sim.growth or 0, sim.growth_base or 0
    local growthNeed = sim.growth_threshold or 20
    local devMax = sim.dev_max or 50
    -- the game applies a command a moment later: async, the commands wait for tick(), then CommandResult {key, kind}
    local async = sim.async and true or false
    local commands = {}
    local askCancel = sim.ask_cancel and true or false
    local demolishMode = sim.demolish or 'chain'
    local levels, levelList = {}, {}
    for _, r in ipairs(config.levels) do
        if not levels[r.key] then levelList[#levelList + 1] = r end
        levels[r.key] = r
    end
    local hull = {}
    for _, h in ipairs(config.hull_tiers or {}) do hull[h.key] = true end
    local built = {}
    for _, s in ipairs(sim.built or {}) do built[prefix .. s] = true end
    local queue = {}            -- the page's Map in its order: {key, turns_left, paid, dev, turn}
    local dismantles = {}       -- the page's Set in its order: keys
    local asked = nil
    local listeners = {}

    local function qindex(key)
        for i, q in ipairs(queue) do if q.key == key then return i end end
        return nil
    end
    local function dindex(key)
        for i, k in ipairs(dismantles) do if k == key then return i end end
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
    function G.set_dev(n) dev = n end
    function G.set_growth(n) growthAcc = n end
    function G.turn() return turn end
    function G.cost(key) return levels[key].cost end
    function G.dev_cost(key) return levels[key].dev or 0 end
    function G.development_points() return dev end
    local function growthPerTurn()
        local sum = growthBase
        for _, r in ipairs(levelList) do if built[r.key] then sum = sum + (r.growth or 0) end end
        return sum
    end
    function G.growth()
        if dev == nil then return nil end
        local per, max = growthPerTurn(), dev >= devMax
        local turns = nil
        if per > 0 and not max then turns = math.ceil((growthNeed - growthAcc) / per) end
        return {now = growthAcc, per_turn = per, need = growthNeed, turns = turns, max = max}
    end

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
    local function refund(key)
        local i = qindex(key)
        local q = queue[i]
        gold = gold + q.paid
        if dev ~= nil then dev = dev + (q.dev or 0) end
        table.remove(queue, i)
    end
    local applyCancel
    local function applyCommand(key)
        local row = levels[key]
        if qindex(key) then applyCancel(key); return true end
        local d = G.dev_cost(key)
        if gold < row.cost or (dev ~= nil and dev < d) then return true end
        gold = gold - row.cost
        if dev ~= nil then dev = dev - d end
        queue[#queue + 1] = {key = key, turns_left = row.turns, paid = row.cost, dev = d, turn = turn}
        return true
    end
    function G.issue_building_command(key)
        local row = levels[key]
        if not row then return false end
        if async then
            commands[#commands + 1] = {key = key, kind = qindex(key) and 'cancel' or 'order'}
            return 'pending'
        end
        return applyCommand(key)
    end
    function G.refusal() return nil end
    applyCancel = function(key)
        local i = qindex(key)
        if not i then return false end
        if askCancel and queue[i].turn < turn then asked = key; return true end
        refund(key)
        return true
    end
    function G.cancel_construction(key)
        if not qindex(key) then return false end
        if async then commands[#commands + 1] = {key = key, kind = 'cancel'}; return 'pending' end
        return applyCancel(key)
    end
    -- the game's next tick: the waiting commands applied, each told
    function G.tick()
        local list = commands
        commands = {}
        for _, c in ipairs(list) do
            if c.kind == 'order' then applyCommand(c.key) else applyCancel(c.key) end
            G.emit('CommandResult', {key = c.key, kind = c.kind})
        end
        return #list
    end
    -- what a Dismantle takes: the slot's whole building, its lower levels with it (the game); step_down: the level alone. The top first
    function G.dismantle_takes(key)
        local row = levels[key]
        if not row or demolishMode == 'step_down' then return {key} end
        local out = {}
        for lv = row.level, 0, -1 do
            for _, l in ipairs(levelList) do
                if l.chain == row.chain and l.level == lv then out[#out + 1] = l.key; break end
            end
        end
        return out
    end
    function G.cancel_asked(key) return asked == key end
    function G.answer_cancel(yes)
        local key = asked
        if not key then return false end
        asked = nil
        if yes and qindex(key) then refund(key) end
        G.emit('CancelAnswered', {key = key, cancelled = yes and true or false})
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
    function G.dismantling(key)
        local row = levels[key]
        if not row then return false end
        for _, k in ipairs(dismantles) do
            if levels[k].chain == row.chain and built[k] then return true end
        end
        return false
    end
    function G.dismantle(key)
        if not built[key] or hull[key] or G.dismantling(key) then return false end
        local row = levels[key]
        for _, q in ipairs(queue) do
            if levels[q.key] and levels[q.key].chain == row.chain then return false end
        end
        dismantles[#dismantles + 1] = key
        return true
    end
    local function takeDown(key)
        built[key] = nil
        local row = levels[key]
        if demolishMode == 'step_down' then
            for _, l in ipairs(levelList) do
                if l.chain == row.chain and l.level == row.level - 1 then built[l.key] = true; break end
            end
            return
        end
        dropChain(row, function() return true end)
    end
    function G.debug_complete(key)
        G.tick()
        local row = levels[key]
        if not row or G.has_building(key) then return false end
        local i = qindex(key)
        if i then table.remove(queue, i) end
        if asked == key then asked = nil end
        local keep = {}
        for _, k in ipairs(dismantles) do if levels[k].chain ~= row.chain then keep[#keep + 1] = k end end
        dismantles = keep
        dropChain(row, function(l) return l.level < row.level end)
        built[key] = true
        G.emit('MilitaryForceBuildingCompleteEvent', {building = key})
        return true
    end

    -- a script's cm:add_building_to_force: the level stands at once in its line's slot, no event, nothing paid
    function G.script_stand(key)
        G.tick()
        local row = levels[key]
        if not row then return false end
        dropChain(row, function() return true end)
        built[key] = true
        return true
    end

    function G.snapshot()
        local b, q, d = {}, {}, {}
        for k in pairs(built) do b[#b + 1] = k end
        table.sort(b)
        for i, x in ipairs(queue) do q[i] = {key = x.key, turns_left = x.turns_left, paid = x.paid, dev = x.dev, turn = x.turn} end
        for i, k in ipairs(dismantles) do d[i] = k end
        return {turn = turn, gold = gold, dev = dev, growth = growthAcc, built = b, queue = q, dismantles = d}
    end
    function G.restore(s)
        turn, gold = s.turn, s.gold
        dev = s.dev
        if s.growth ~= nil then growthAcc = s.growth end
        built, queue, dismantles, asked = {}, {}, {}, nil
        for _, k in ipairs(s.built) do if levels[k] then built[k] = true end end
        for _, x in ipairs(s.queue) do
            if levels[x.key] then queue[#queue + 1] = {key = x.key, turns_left = x.turns_left, paid = x.paid, dev = x.dev, turn = x.turn} end
        end
        for _, k in ipairs(s.dismantles or {}) do if levels[k] then dismantles[#dismantles + 1] = k end end
    end

    function G.end_turn()
        G.tick()
        G.emit('FactionTurnEnd', {turn = turn})
        if dev ~= nil then
            growthAcc = growthAcc + growthPerTurn()
            if growthAcc < 0 then growthAcc = 0 end
            while growthNeed > 0 and growthAcc >= growthNeed do
                growthAcc = growthAcc - growthNeed
                if dev < devMax then dev = dev + 1 end
            end
        end
        asked = nil
        local gone = {}
        for _, k in ipairs(dismantles) do if built[k] then gone[#gone + 1] = k end end
        for _, k in ipairs(gone) do takeDown(k) end
        dismantles = {}
        local done = {}
        for _, q in ipairs(queue) do
            q.turns_left = q.turns_left - 1
            if q.turns_left <= 0 then done[#done + 1] = q.key end
        end
        for _, key in ipairs(done) do
            local i = qindex(key)
            if i then table.remove(queue, i) end
            local row = levels[key]
            dropChain(row, function(l) return l.level < row.level end)
            built[key] = true
        end
        turn = turn + 1
        gold = gold + income
        for _, key in ipairs(gone) do G.emit('BuildingDemolished', {key = key}) end
        G.emit('FactionTurnStart', {turn = turn})
        for _, key in ipairs(done) do G.emit('MilitaryForceBuildingCompleteEvent', {building = key}) end
    end
    return G
end

return Fake
