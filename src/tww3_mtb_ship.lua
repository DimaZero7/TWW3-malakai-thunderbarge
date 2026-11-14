-- The airship screen's buildings and crew, without the screen: the Lua of web/js/barge_buildings.js, the same module M function for function
-- (docs/design/port-to-game.md, 4.1). What may be ordered and why not, the order, cancel, demolish, the stage of each part of the drawing, the
-- news of a turn, the first step, the crew's orders; the saved state as strings (4.3).
--
--   local Ship = <this module>; local M = Ship.make(config, game, crew_model)
--     config       the generated table (tools/ship_config.mjs -> script/campaign/tww3_mtb/tww3_mtb_ship_config.lua): the levels of the author's
--                  tree, the crew groups, the parts of the drawing, the words of the places. Nothing in it is a rule: lines, inheritance, what is new
--                  on a level are already resolved by the build (tree_model.mjs)
--     game         the game's side, the interface of web/js/game_sim.js (tools/tests/fake_game.lua offline, src/tww3_mtb_game.lua in the game):
--                  treasury(), treasury_mod(delta), turn(), has_building(key), standing(key), under_construction(key) -> turns | nil,
--                  issue_building_command(key), cancel_construction(key), dismantle(key) -> bool, on(event, fn); debug_complete(key) (debug only)
--     crew_model   src/tww3_mtb_crew_model.lua
--   Ship.save_state(M, view) -> {saved key = string}      Ship.load_state(M, get) -> view      (get(key) -> the saved string or nil)
--
-- Pure: no UI, no cm, no core, no os/io. It returns its table and sets nothing global; the running mod does not load it yet (it is packed outside
-- script/campaign/mod, which is the only folder the game runs by itself). The Russian lines are the page's, byte for byte (tools/lua_vectors.py).
-- Only the tree's way of the page is ported (data.tree_rows: a level acts while it stands in its slot); the page's older data of the mod's own
-- chains is not the game's any more.

local Ship = {}

-- ---- small helpers: the page's JS idioms ----
local function push(list, v) list[#list + 1] = v end
local function includes(list, v)
    for _, x in ipairs(list) do if x == v then return true end end
    return false
end
local function find(list, fn)
    for _, x in ipairs(list) do if fn(x) then return x end end
    return nil
end
local function filter(list, fn)
    local out = {}
    for _, x in ipairs(list) do if fn(x) then push(out, x) end end
    return out
end
local function map(list, fn)
    local out = {}
    for i, x in ipairs(list) do out[i] = fn(x) end
    return out
end
local function join(list, sep) return table.concat(list, sep) end
local function copy(list)
    local out = {}
    for i, x in ipairs(list) do out[i] = x end
    return out
end
-- a stable sort (Array.prototype.sort is stable; table.sort is not): insertion, the lists are short
local function ssort(list, less)
    for i = 2, #list do
        local v, j = list[i], i - 1
        while j >= 1 and less(v, list[j]) do list[j + 1] = list[j]; j = j - 1 end
        list[j + 1] = v
    end
    return list
end
local function starts(s, p) return string.sub(s, 1, #p) == p end
local function truthy(s) return s ~= nil and s ~= false and s ~= '' and s ~= 0 end
local floor = math.floor
-- a number as a JS template writes it (`${n}`): the page's numbers here are whole
local function num(n)
    if type(n) ~= 'number' then return tostring(n) end
    if n == floor(n) and n > -1e15 and n < 1e15 then return string.format('%d', n) end
    return tostring(n)
end
Ship.num = num
-- the first letter up, as JS toUpperCase: ASCII and the Cyrillic of the texts (а-я, ё)
local function upper_first(s)
    local b1, b2 = string.byte(s, 1, 2)
    if not b1 then return s end
    if b1 >= 97 and b1 <= 122 then return string.char(b1 - 32) .. string.sub(s, 2) end
    if b1 == 0xD0 and b2 and b2 >= 0xB0 and b2 <= 0xBF then return string.char(0xD0, b2 - 0x20) .. string.sub(s, 3) end      -- а-п
    if b1 == 0xD1 and b2 and b2 >= 0x80 and b2 <= 0x8F then return string.char(0xD0, b2 + 0x20) .. string.sub(s, 3) end      -- р-я
    if b1 == 0xD1 and b2 == 0x91 then return string.char(0xD0, 0x81) .. string.sub(s, 3) end                                -- ё
    return s
end
Ship.upper_first = upper_first

function Ship.turns_text(n)
    local m10, m100 = n - floor(n / 10) * 10, n - floor(n / 100) * 100
    local word = 'ходов'
    if m10 == 1 and m100 ~= 11 then word = 'ход'
    elseif m10 >= 2 and m10 <= 4 and (m100 < 12 or m100 > 14) then word = 'хода' end
    return num(n) .. ' ' .. word
end
local turnsText = Ship.turns_text

function Ship.make(config, game, crewModel)
    local M = {game = game, prefix = config.prefix, config = config}
    -- the page's own requirements over the mod's data and the nodes shown but not orderable yet: empty in the game (kept for the line-for-line port)
    M.extra_requires = {}
    M.not_connected = {}
    local prefix = config.prefix
    local TREE = config.tree ~= false
    local levels, levelList = {}, {}
    for _, row in ipairs(config.levels) do
        if not levels[row.key] then push(levelList, row) end
        levels[row.key] = row
    end
    local function needsOf(row)
        local out = copy(row.requires)
        for _, k in ipairs(M.extra_requires[row.key] or {}) do push(out, k) end
        return out
    end
    local chains = {}
    for _, c in ipairs(config.chains) do
        local ls = {}
        for _, k in ipairs(c.levels) do push(ls, levels[k]) end
        chains[c.key] = {key = c.key, levels = ls}
    end
    -- the hull's levels and their tier (hull_tiers: key -> tier, in the page's order)
    local hullTier, hullOrder, hullByTier = {}, {}, {}
    for _, h in ipairs(config.hull_tiers) do
        if hullTier[h.key] == nil then push(hullOrder, h.key) end
        hullTier[h.key] = h.tier
    end
    for _, k in ipairs(hullOrder) do
        local t = hullTier[k]
        if not hullByTier[t] then hullByTier[t] = levels[k] end
    end
    local groups, groupOrder = {}, {}
    for _, g in ipairs(config.groups) do
        local options, optionOrder = {}, {}
        for _, o in ipairs(g.options) do options[o.key] = o; push(optionOrder, o.key) end
        groups[g.key] = {key = g.key, name = g.name, start = g.start, mount = g.mount, options = options, option_order = optionOrder}
        push(groupOrder, g.key)
    end
    M.groups, M.group_order = groups, groupOrder
    local parts, partOrder = {}, {}
    for _, p in ipairs(config.parts or {}) do parts[p.key] = p; push(partOrder, p.key) end
    M.part_order = partOrder

    -- the game's own words for a building whose requirement is not met (local_ru: campaign_localised_strings_string_building_required)
    M.REQUIRES = 'Требуется постройка: '
    M.REQUIRES_MANY = 'Требуются постройки: '
    local message = nil
    local changed = {}
    function M.on_change(fn) push(changed, fn) end
    local function fire() for _, fn in ipairs(changed) do fn() end end

    function M.level(key) return levels[key] or levels[prefix .. key] end
    local hullChain = {key = 'hull', levels = {}}
    function M.chain(key)
        if key == 'hull' then return hullChain end
        return chains[key]
    end
    function M.hull_tier()
        local tier = 0
        for _, k in ipairs(hullOrder) do
            if game.has_building(k) then tier = math.max(tier, hullTier[k]) end
        end
        return tier
    end

    -- the hull a tier asks for: the hull level of that tier, else the lowest hull above it; nil when the tree has none
    local function hullFor(tier)
        if hullByTier[tier] then return hullByTier[tier] end
        local list = {}
        for _, k in ipairs(hullOrder) do if hullTier[k] >= tier then push(list, k) end end
        ssort(list, function(a, b) return hullTier[a] < hullTier[b] end)
        return list[1] and levels[list[1]] or nil
    end
    local function belowOf(row)
        local chain = M.chain(row.chain)
        return chain and find(chain.levels, function(l) return l.level == row.level - 1 end) or nil
    end
    -- The direct requirements of a level that do not stand yet, nearest first (barge_buildings.js M.missing)
    function M.missing(key)
        local row = M.level(key)
        if not row then return {} end
        local out = {}
        local function add(k)
            if k and k ~= row.key and not includes(out, k) and not game.has_building(k) then push(out, k) end
        end
        local below = belowOf(row)
        if below then add(below.key) end
        for _, k in ipairs(needsOf(row)) do add(k) end
        if hullTier[row.key] == nil and row.tier > M.hull_tier() then
            local h = hullFor(row.tier)
            if h then add(h.key) else push(out, 'tier:' .. num(row.tier)) end
        end
        local function left(k)
            if starts(k, 'tier:') then return 1e6 end
            return #filter(M.needs_all(k), function(x) return not game.has_building(x) end)
        end
        local items = {}
        for i, k in ipairs(out) do push(items, {k = k, i = i, d = left(k)}) end
        ssort(items, function(a, b) return a.d < b.d or (a.d == b.d and a.i < b.i) end)
        return map(items, function(x) return x.k end)
    end
    function M.requires_text(keys)
        local names = map(keys, function(k)
            if starts(k, 'tier:') then return 'корпус яруса ' .. string.sub(k, 6) end
            local l = M.level(k)
            return '«' .. (l and l.name or string.sub(k, #prefix + 1)) .. '»'
        end)
        return (#keys > 1 and M.REQUIRES_MANY or M.REQUIRES) .. join(names, ', ')
    end

    -- {state = built | building | open | locked | unknown, turns, why, missing, poor}
    function M.status(key)
        local row = M.level(key)
        if not row then return {state = 'unknown', why = 'Нет в выгрузке: ' .. key} end
        if game.has_building(row.key) then return {state = 'built'} end
        local turns = game.under_construction(row.key)
        if turns ~= nil then return {state = 'building', turns = turns} end
        local missing = M.missing(row.key)
        if #missing > 0 then return {state = 'locked', why = M.requires_text(missing), missing = missing} end
        local chain = M.chain(row.chain)
        local busy = chain and find(chain.levels, function(l) return game.under_construction(l.key) ~= nil end)
        if busy then return {state = 'locked', why = 'Уже строится «' .. busy.name .. '»'} end
        if M.not_connected[row.key] then return {state = 'locked', why = 'Пока не подключено на странице'} end
        if game.treasury() < row.cost then return {state = 'locked', why = 'Не хватает золота: нужно ' .. num(row.cost), poor = true} end
        return {state = 'open'}
    end

    function M.order(key)
        local row = M.level(key)
        local before = M.status(key)
        if before.state ~= 'open' then return {ok = false, why = before.why or 'Нельзя заказать'} end
        -- GAME: the order is the game's command (src/tww3_mtb_game.lua); the game takes the gold
        game.issue_building_command(row.key)
        -- check after the order: right after a battle an order sometimes did nothing. Read the slot again.
        if game.under_construction(row.key) == nil then
            message = 'Заказ «' .. row.name .. '» не прошёл: игра его не приняла. Выберите Малакая и повторите.'
            fire()
            return {ok = false, why = message}
        end
        message = 'Заказано: «' .. row.name .. '», ' .. num(row.cost) .. ' золота, готово через ' .. turnsText(row.turns) .. '.'
        fire()
        return {ok = true}
    end

    -- why a level cannot be ordered now, as a sentence; '' when it can be ordered (or stands, or is being built)
    function M.reason(key)
        local st, row = M.status(key), M.level(key)
        if st.state ~= 'locked' and st.state ~= 'unknown' then return '' end
        if st.poor then return 'Не хватает золота: нужно ' .. num(row.cost) .. ', в казне ' .. num(game.treasury()) .. '.' end
        return (st.why or 'Недоступно') .. '.'
    end
    function M.refuse(key)
        local why = M.reason(key)
        if why == '' then return false end
        message = why
        fire()
        return true
    end

    function M.cancel(key)
        local row = M.level(key)
        if game.under_construction(row.key) == nil then return {ok = false} end
        game.cancel_construction(row.key)
        message = 'Отменено: «' .. row.name .. '», золото вернулось.'
        fire()
        return {ok = true}
    end

    function M.can_demolish(key)
        local row = M.level(key)
        if not row or not game.has_building(row.key) then return {ok = false, why = 'Не построено'} end
        if not game.standing(row.key) then
            local chain = M.chain(row.chain)
            local top = nil
            if chain then
                for i = #chain.levels, 1, -1 do
                    if game.standing(chain.levels[i].key) then top = chain.levels[i]; break end
                end
            end
            return {ok = false, why = 'Сначала снесите «' .. (top and top.name or 'верхний уровень') .. '»: он стоит на этой постройке'}
        end
        local needing = filter(levelList, function(l) return includes(needsOf(l), row.key) and game.has_building(l.key) end)
        if #needing > 0 then return {ok = false, why = 'Сначала снесите «' .. needing[1].name .. '»: ей нужна эта постройка'} end
        return {ok = true}
    end

    function M.demolish(key)
        local row = M.level(key)
        if not M.can_demolish(key).ok then return {ok = false, why = M.can_demolish(key).why} end
        local crewBefore = message
        if not game.dismantle(row.key) then return {ok = false} end
        local said = ''
        if message ~= crewBefore and truthy(message) then said = ' ' .. message end
        message = 'Снесено: «' .. row.name .. '».' .. said
        fire()
        return {ok = true}
    end

    -- ---- the stage of a part of the drawing: pencil, build, ink; none for a part not connected ----
    M.all_parts = false
    local partOpeners = {}
    for _, row in ipairs(levelList) do
        for _, p in ipairs(row.parts or {}) do
            partOpeners[p] = partOpeners[p] or {}
            push(partOpeners[p], row.key)
        end
    end
    function M.part_openers(part) return partOpeners[part] or {} end
    M.carrier = nil
    for _, k in ipairs(partOrder) do if parts[k].carrier then M.carrier = k; break end end
    function M.carried() return not M.carrier or M.stage(M.carrier) == 'ink' end
    function M.stage(part)
        local p = parts[part]
        if not p then return 'none' end
        if M.all_parts then return 'ink' end
        if M.carrier and part ~= M.carrier and not p.base and not M.carried() then return 'none' end
        local keys = {}
        if p.building then push(keys, prefix .. p.building) end
        for _, k in ipairs(partOpeners[part] or {}) do push(keys, k) end
        if not p.enabled or #keys == 0 then return 'none' end
        local states = map(keys, function(k)
            if includes(partOpeners[part] or {}, k) and M.status(k).state == 'built' and not M.stands(k) then return 'pencil' end
            return M.status(k).state
        end)
        if includes(states, 'built') then return 'ink' end
        if includes(states, 'building') then return 'build' end
        return 'pencil'
    end

    local turnLine = nil
    function M.message() return message end
    function M.message_snapshot() return {text = message, turn_line = turnLine and {turn = turnLine.turn, text = turnLine.text} or nil} end
    function M.set_message_silently(s)
        message = (s and type(s.text) == 'string' and s.text ~= '') and s.text or nil
        turnLine = (s and s.turn_line and type(s.turn_line.text) == 'string') and {turn = tonumber(s.turn_line.turn), text = s.turn_line.text} or nil
    end

    -- every level a building needs, all the way down, the deepest first
    function M.needs_all(key)
        local out, seen = {}, {}
        local function walk(k)
            local row = M.level(k)
            if not row or seen[row.key] then return end
            seen[row.key] = true
            local below = belowOf(row)
            if below then walk(below.key) end
            for _, r in ipairs(needsOf(row)) do walk(r) end
            push(out, row.key)
        end
        walk(key)
        return out
    end
    -- debug of the page only (the fake game's debug_complete): never in the game
    function M.debug_build_to(key)
        for _, k in ipairs(M.needs_all(key)) do if not M.not_connected[k] then game.debug_complete(k) end end
        message = nil
        fire()
    end

    local side = 'left'
    local sideChosen = false
    function M.set_side_silently(s) side = s end
    function M.malakai_side() return side end
    function M.side_hint() return not sideChosen end
    function M.set_side_chosen_silently(v) sideChosen = truthy(v) end
    function M.set_malakai_side(s)
        if s == side then return end
        side = s
        sideChosen = true
        message = 'Малакай встанет на ' .. (s == 'left' and 'левый' or 'правый') .. ' борт.'
        fire()
    end

    -- ---- the crew: what stands in a group of seats and what is ordered for the next turn (crew_model.lua) ----
    local crew, crewKeys = {}, {}       -- group -> {standing, order}; the groups in the order they first got a state (the page's object keys)
    local function setCrew(g, st)
        if crew[g] == nil then push(crewKeys, g) end
        crew[g] = st
    end
    local function setGold(gold)        -- the page writes game.gold; the game moves the treasury by the difference
        local d = gold - game.treasury()
        if d ~= 0 then game.treasury_mod(d) end
    end
    -- group -> option -> the building levels that open it
    local openers = {}
    for _, row in ipairs(levelList) do
        for _, u in ipairs(row.unlocks or {}) do
            openers[u.group] = openers[u.group] or {}
            openers[u.group][u.option] = openers[u.group][u.option] or {}
            push(openers[u.group][u.option], row)
        end
    end
    local function cheap(r)
        if TREE then return #M.needs_all(r.key) * 100000 + r.cost end
        return r.tier * 100000 + r.cost
    end
    local function stands(r)
        if TREE then return game.standing(r.key) end
        return game.has_building(r.key)
    end
    function M.stands(key) local r = M.level(key); return (r and stands(r)) and true or false end
    local function opener(g, o)
        local list = (openers[g] or {})[o]
        if not list then return nil end
        local s = find(list, stands)
        if s then return s end
        return ssort(copy(list), function(a, b) return cheap(a) < cheap(b) end)[1]
    end
    M.opener = opener
    local function emptyOf(g) return groups[g].mount or groups[g].start end
    local function opens(g, o)
        local list = (openers[g] or {})[o] or {}
        return find(list, stands) ~= nil
    end
    function M.crew_place(g)
        local group = groups[g]
        if not group or not M.carried() then return false end
        if group.mount then return opens(g, group.mount) end
        for _, o in ipairs(group.option_order) do
            if o ~= group.start and opens(g, o) then return true end
        end
        return false
    end
    function M.place_opener(g)
        local group = groups[g]
        if not group then return nil end
        if group.mount then return opener(g, group.mount) end
        local list = {}
        for _, o in ipairs(group.option_order) do
            if o ~= group.start then local r = opener(g, o); if r then push(list, r) end end
        end
        local s = find(list, stands)
        if s then return s end
        return ssort(list, function(a, b) return cheap(a) < cheap(b) end)[1]
    end
    local function stateOf(g) return crew[g] or {standing = emptyOf(g), order = nil} end
    local function ctxOf(g)
        return {start = emptyOf(g), gold = game.treasury(),
                hire = function(o) return (groups[g].options[o] or {}).hire or 0 end,
                unlocked = function(o) return o == emptyOf(g) or (M.crew_place(g) and opens(g, o)) end}
    end
    function M.crew(group) return stateOf(group).standing end
    function M.crew_order(group) local o = stateOf(group).order; return o and o.option or nil end
    function M.crew_options(group)
        local g, ctx = groups[group], ctxOf(group)
        local function rank(k) local b = opener(group, k); return b and cheap(b) or 0 end
        local empty = emptyOf(group)
        local list = {}
        for _, k in ipairs(g.option_order) do
            local o = g.options[k]
            if not o.hidden and (k == empty or opener(group, k)) then
                push(list, {key = k, i = #list, name = o.name, hire = o.hire, upkeep = o.upkeep, empty = k == empty, building = opener(group, k), unlocked = ctx.unlocked(k)})
            end
        end
        local ranks = {}
        for _, x in ipairs(list) do ranks[x.key] = rank(x.key) end
        return ssort(list, function(a, b)
            if a.empty then return not b.empty end
            if b.empty then return false end
            local ra, rb = ranks[a.key], ranks[b.key]
            return ra < rb or (ra == rb and a.i < b.i)
        end)
    end
    local function upkeepOf(g, o) return (groups[g].options[o] or {}).upkeep or 0 end
    function M.crew_upkeep()
        local sum = 0
        for _, g in ipairs(groupOrder) do sum = sum + upkeepOf(g, M.crew(g)) end
        return sum
    end
    function M.crew_upkeep_next()
        local sum = 0
        for _, g in ipairs(groupOrder) do sum = sum + upkeepOf(g, M.crew_order(g) or M.crew(g)) end
        return sum
    end
    -- the words of a group's place (blueprint.json crew_areas, words): the riflemen's by default
    local RIFLES = {at = 'у бортов', stand = 'Стоят у бортов', come = 'встанут к бортам', came = 'встали к бортам', leave = 'сойдут с бортов', left = 'стрелки сошли с бортов',
                    nobody = 'У бортов никого', empty_name = 'пустые борта', who = 'Стрелки'}
    M.words = {}
    for _, g in ipairs(config.groups) do if g.words then M.words[g.key] = g.words end end
    function M.crew_words(g)
        local out = {}
        for k, v in pairs(RIFLES) do out[k] = v end
        for k, v in pairs(M.words[g] or {}) do out[k] = v end
        return out
    end
    local function nameOf(g, o)
        if o == emptyOf(g) then return M.crew_words(g).empty_name end
        return '«' .. groups[g].options[o].name .. '»'
    end
    local function sayResult(g, r, done)
        local n, start, w = nameOf(g, r.option), emptyOf(g), M.crew_words(g)
        if r.kind == 'locked' then return {bad = true, text = 'Заперто: ' .. n .. ' откроет постройка «' .. opener(g, r.option).name .. '»'} end
        if r.kind == 'poor' then return {bad = true, text = 'Не хватает золота на ' .. n .. ': найм ' .. num(r.hire) .. ', есть ' .. num(r.have)} end
        if r.kind == 'kept' then
            if r.why == 'ordered' then
                return {text = r.option == start and 'Экипаж уже сходит в начале хода' or (n .. ' уже в найме')}
            end
            return {text = r.option == start and w.nobody or (n .. ' уже ' .. w.at)}
        end
        local back, willBack = '', ''
        if truthy(r.back) then back = ', вернулось ' .. num(r.back); willBack = ', вернётся ' .. num(r.back) end
        if r.kind == 'cancelled' then
            if done then return {text = 'Заказ на ' .. nameOf(g, r.option) .. ' снят' .. back} end
            return {text = 'Снять заказ на ' .. nameOf(g, r.option) .. willBack .. ': ' .. w.at .. ' остаются, кто стоит'}
        end
        if r.option == start then
            if done then return {text = 'Экипаж сойдёт в начале хода' .. back} end
            return {text = 'Снять экипаж в начале хода' .. willBack}
        end
        local instead = ''
        if r.instead and r.instead ~= start then instead = ' вместо ' .. nameOf(g, r.instead) end
        if done then return {text = 'В найме ' .. n .. instead .. ': списано ' .. num(r.taken) .. back .. ', встанут в начале хода'} end
        return {text = 'Нанять ' .. n .. instead .. ': найм ' .. num(r.taken) .. willBack .. ', встанут в начале хода'}
    end
    local notes = {}
    function M.crew_note(group) return notes[group] end
    function M.crew_preview(group, option)
        local r = crewModel.click(stateOf(group), option, ctxOf(group)).result
        local said = sayResult(group, r, false)
        return {kind = r.kind, text = said.text, bad = said.bad}
    end
    local crewChosen = {}
    function M.set_crew(group, option)
        if not groups[group].options[option] then return {ok = false} end
        local r = crewModel.click(stateOf(group), option, ctxOf(group))
        setCrew(group, r.state)
        setGold(r.gold)
        notes[group] = sayResult(group, r.result, true)
        if r.result.kind == 'ordered' then crewChosen[group] = true end
        message = notes[group].text .. '.'
        fire()
        return {ok = r.result.kind == 'ordered' or r.result.kind == 'cancelled', kind = r.result.kind}
    end
    function M.crew_hint(g) return not crewChosen[g or 'rifles'] end
    function M.crew_chosen()
        local out = {}
        for k, v in pairs(crewChosen) do out[k] = v end
        return out
    end
    function M.set_crew_chosen_silently(v)
        crewChosen = {}
        if v == true then crewChosen = {rifles = true}
        elseif type(v) == 'table' then for k, x in pairs(v) do crewChosen[k] = x end end
    end
    -- the crew as plain data, in the order the groups got their state: {{group, standing, order = {option, paid} | nil}}
    function M.crew_snapshot()
        local out = {}
        for _, g in ipairs(crewKeys) do
            local st = crew[g]
            push(out, {group = g, standing = st.standing, order = st.order and {option = st.order.option, paid = st.order.paid} or nil})
        end
        return out
    end
    function M.set_crew_silently(saved)
        for _, st in ipairs(saved or {}) do
            local g = st.group
            if groups[g] and groups[g].options[st.standing] then
                local order = nil
                if st.order and groups[g].options[st.order.option] then order = {option = st.order.option, paid = tonumber(st.order.paid) or 0} end
                setCrew(g, {standing = st.standing, order = order})
            end
        end
    end
    -- a building that no longer stands takes its option away: the order with its gold, the standing crew without
    local function dropLocked()
        local said = {}
        for _, g in ipairs(copy(crewKeys)) do
            local r = crewModel.lose(stateOf(g), ctxOf(g))
            crew[g] = r.state
            setGold(r.gold)
            for _, l in ipairs(r.lost) do
                if l.kind == 'order' then push(said, 'заказ на ' .. nameOf(g, l.option) .. ' снят, ' .. num(l.back) .. ' золота вернулось')
                else push(said, nameOf(g, l.option) .. ' сошли с корабля, найм не возвращается') end
            end
            if #r.lost > 0 then notes[g] = nil end
        end
        return said
    end
    game.on('BuildingDemolished', function()
        local said = dropLocked()
        if #said > 0 then message = 'Постройки больше нет: ' .. join(said, '; ') .. '.'; fire() end
    end)

    -- ---- what the buildings of a turn brought to the ship ----
    local function kindsNow(places)
        local out = {}
        for _, g in ipairs(places) do
            for _, o in ipairs(M.crew_options(g)) do if not o.empty and o.unlocked then push(out, g .. ':' .. o.key) end end
        end
        return out
    end
    local function shipNow()
        local places = filter(groupOrder, function(g) return M.crew_place(g) end)
        return {parts = filter(partOrder, function(p) return M.stage(p) == 'ink' end), places = places, kinds = kindsNow(places)}
    end
    local function groupOf(kind) return string.match(kind, '^([^:]*)') end
    local shipWas, news, unseen = nil, nil, false
    function M.sync_ship() shipWas = shipNow() end
    function M.ship_news() if news and news.turn == game.turn() then return news end return nil end
    function M.ship_unseen() return unseen end
    function M.ship_seen() unseen = false end
    function M.news_snapshot()
        local n = nil
        if news then n = {turn = news.turn, built = copy(news.built), parts = copy(news.parts), places = copy(news.places), kinds = copy(news.kinds or {})} end
        return {news = n, unseen = unseen}
    end
    function M.set_news_silently(s)
        news = nil
        if s and s.news and type(s.news.built) == 'table' then
            news = {turn = s.news.turn, built = copy(s.news.built), parts = copy(s.news.parts or {}), places = copy(s.news.places or {}), kinds = copy(s.news.kinds or {})}
        end
        unseen = (s and truthy(s.unseen)) and true or false
    end
    function M.news_places()
        local n = M.ship_news()
        if not n then return {} end
        local out = {}
        for _, g in ipairs(n.places) do if not includes(out, g) then push(out, g) end end
        for _, k in ipairs(n.kinds or {}) do local g = groupOf(k); if not includes(out, g) then push(out, g) end end
        return out
    end
    local TAG = {rifles = 'Стрелки', cannons = 'Орудия', bombs = 'Бомбы', cupolas = 'Гнёзда', harpoon = 'Гарпун'}
    function M.place_name(g) return TAG[g] or (groups[g] and groups[g].name) or g end
    local function quoted(list) return join(map(list, function(s) return '«' .. s .. '»' end), ', ') end
    local NEW_KINDS = {
        rifles = function(l, one) return 'Для стрелков теперь ' .. (one and 'открыт отряд' or 'открыты отряды') .. ' ' .. l .. '.' end,
        cannons = function(l) return 'В порты теперь можно поставить ' .. l .. '.' end,
        bombs = function(l) return 'На стеллажи над люками теперь можно положить ' .. l .. '.' end,
        cupolas = function(l) return 'В гнёздах теперь доступны ' .. l .. '.' end,
        harpoon = function(l) return 'На нос шара теперь можно поставить ' .. l .. '.' end,
    }
    function M.new_kinds_text(g, names)
        if NEW_KINDS[g] then return NEW_KINDS[g](quoted(names), #names == 1) end
        return 'Новое для места «' .. M.place_name(g) .. '»: ' .. quoted(names) .. '.'
    end
    local function newsText(lost)
        lost = lost or {}
        local n, out = M.ship_news(), {}
        if n and #n.built > 0 then push(out, 'Построено: ' .. quoted(map(n.built, function(k) return M.level(k).name end)) .. '.') end
        if n and #n.places > 0 then
            local names = quoted(map(n.places, M.place_name))
            push(out, #n.places == 1 and ('Открыто место экипажа ' .. names .. '.') or ('Открыты места экипажа ' .. names .. '.'))
        end
        if n and #(n.kinds or {}) > 0 then
            local by, byOrder = {}, {}
            for _, k in ipairs(n.kinds) do
                local g, o = string.match(k, '^([^:]*):(.*)$')
                if not by[g] then by[g] = {}; push(byOrder, g) end
                push(by[g], groups[g].options[o].name)
            end
            for _, g in ipairs(byOrder) do push(out, M.new_kinds_text(g, by[g])) end
        end
        if #lost > 0 then push(out, 'Новый уровень этого не даёт: ' .. join(lost, '; ') .. '.') end
        if turnLine and turnLine.turn == game.turn() then push(out, turnLine.text) end
        local s = join(out, ' ')
        if s == '' then return nil end
        return s
    end

    game.on('MilitaryForceBuildingCompleteEvent', function(ctx)
        if not news or news.turn ~= game.turn() then news = {turn = game.turn(), built = {}, parts = {}, places = {}, kinds = {}} end
        news.kinds = news.kinds or {}
        push(news.built, ctx.building)
        -- a tree's next level that does not carry on what the level below opened: that crew is no longer open
        local lost = TREE and dropLocked() or {}
        local now = shipNow()
        local was = shipWas or now
        local parts_ = filter(now.parts, function(p) return not includes(was.parts, p) end)
        local places = filter(now.places, function(g) return not includes(was.places, g) end)
        local kinds = filter(now.kinds, function(k) return not includes(was.kinds or {}, k) and includes(was.places or {}, groupOf(k)) end)
        for _, p in ipairs(filter(parts_, function(p) return not includes(news.parts, p) end)) do push(news.parts, p) end
        for _, g in ipairs(filter(places, function(g) return not includes(news.places, g) end)) do push(news.places, g) end
        for _, k in ipairs(filter(kinds, function(k) return not includes(news.kinds, k) and not includes(news.places, groupOf(k)) end)) do push(news.kinds, k) end
        if #parts_ > 0 or #places > 0 or #kinds > 0 then unseen = true end
        shipWas = now
        message = newsText(lost)
        fire()
    end)
    game.on('BuildingDemolished', function() shipWas = shipNow() end)
    -- the one obvious first step of a fresh campaign: nothing built, nothing ordered, nothing said yet
    function M.first_step()
        if truthy(message) then return nil end
        for _, r in ipairs(levelList) do
            if game.has_building(r.key) or game.under_construction(r.key) ~= nil then return nil end
        end
        local first = find(levelList, function(r) return #M.missing(r.key) == 0 end)
        return first and ('Закажите первую постройку — «' .. first.name .. '».') or nil
    end
    game.on('FactionTurnStart', function()
        -- the orders go in, then the upkeep of what stands now is taken
        local came = {}
        for _, g in ipairs(copy(crewKeys)) do
            if crew[g].order then
                crew[g] = crewModel.turn(crew[g])
                notes[g] = nil
                if crew[g].standing == emptyOf(g) then push(came, M.crew_words(g).left)
                else push(came, nameOf(g, crew[g].standing) .. ' ' .. M.crew_words(g).came) end
            end
        end
        local upkeep = M.crew_upkeep()
        setGold(game.treasury() - upkeep)
        local said = {}
        if #came > 0 then push(said, join(came, '; ')) end
        if upkeep ~= 0 then push(said, 'содержание экипажа: ' .. num(upkeep) .. ' золота') end
        local s = join(said, ', ')
        message = s ~= '' and (upper_first(s) .. '.') or nil
        turnLine = message and {turn = game.turn(), text = message} or nil
        fire()
    end)
    M.sync_ship()
    return M
end

-- ---- the saved state (docs/design/port-to-game.md, 4.3): every value a string, for cm:set_saved_value ----
-- A small JSON for the values that are tables (the game keeps strings and numbers; tables are not proven).
local function esc(s)
    return (string.gsub(s, '[%c"\\]', function(c)
        if c == '"' then return '\\"' elseif c == '\\' then return '\\\\' elseif c == '\n' then return '\\n' elseif c == '\t' then return '\\t' end
        return string.format('\\u%04x', string.byte(c))
    end))
end
local function encode(v)
    local t = type(v)
    if v == nil then return 'null' end
    if t == 'boolean' then return v and 'true' or 'false' end
    if t == 'number' then
        if v == floor(v) and v > -1e15 and v < 1e15 then return string.format('%d', v) end
        return string.format('%.17g', v)
    end
    if t == 'string' then return '"' .. esc(v) .. '"' end
    if t == 'table' then
        if v[1] ~= nil or next(v) == nil then
            local out = {}
            for i = 1, #v do out[i] = encode(v[i]) end
            return '[' .. table.concat(out, ',') .. ']'
        end
        local keys = {}
        for k in pairs(v) do keys[#keys + 1] = tostring(k) end
        table.sort(keys)
        local out = {}
        for _, k in ipairs(keys) do out[#out + 1] = '"' .. esc(k) .. '":' .. encode(v[k]) end
        return '{' .. table.concat(out, ',') .. '}'
    end
    error('cannot save a ' .. t)
end
Ship.encode = encode

local function decode(s)
    local pos = 1
    local value
    local function ws() pos = string.find(s, '[^ \t\r\n]', pos) or (#s + 1) end
    local function fail(what) error('saved value: ' .. what .. ' at ' .. pos .. ' of ' .. string.sub(s, 1, 60)) end
    local function str()
        local out = {}
        pos = pos + 1
        while true do
            local c = string.sub(s, pos, pos)
            if c == '' then fail('unterminated string') end
            if c == '"' then pos = pos + 1; return table.concat(out) end
            if c == '\\' then
                local e = string.sub(s, pos + 1, pos + 1)
                if e == 'n' then out[#out + 1] = '\n'; pos = pos + 2
                elseif e == 't' then out[#out + 1] = '\t'; pos = pos + 2
                elseif e == 'r' then out[#out + 1] = '\r'; pos = pos + 2
                elseif e == 'b' then out[#out + 1] = '\b'; pos = pos + 2
                elseif e == 'f' then out[#out + 1] = '\f'; pos = pos + 2
                elseif e == 'u' then
                    local n = tonumber(string.sub(s, pos + 2, pos + 5), 16)
                    if not n then fail('bad \\u') end
                    if n < 0x80 then out[#out + 1] = string.char(n)
                    elseif n < 0x800 then out[#out + 1] = string.char(0xC0 + floor(n / 64), 0x80 + n % 64)
                    else out[#out + 1] = string.char(0xE0 + floor(n / 4096), 0x80 + floor(n / 64) % 64, 0x80 + n % 64) end
                    pos = pos + 6
                else out[#out + 1] = e; pos = pos + 2 end
            else
                local j = string.find(s, '["\\]', pos) or (#s + 1)
                out[#out + 1] = string.sub(s, pos, j - 1)
                pos = j
            end
        end
    end
    value = function()
        ws()
        local c = string.sub(s, pos, pos)
        if c == '{' then
            local out = {}
            pos = pos + 1; ws()
            if string.sub(s, pos, pos) == '}' then pos = pos + 1; return out end
            while true do
                ws()
                if string.sub(s, pos, pos) ~= '"' then fail('a key') end
                local k = str()
                ws()
                if string.sub(s, pos, pos) ~= ':' then fail('a colon') end
                pos = pos + 1
                out[k] = value()
                ws()
                local d = string.sub(s, pos, pos)
                pos = pos + 1
                if d == '}' then return out end
                if d ~= ',' then fail('a comma') end
            end
        elseif c == '[' then
            local out = {}
            pos = pos + 1; ws()
            if string.sub(s, pos, pos) == ']' then pos = pos + 1; return out end
            while true do
                out[#out + 1] = value()
                ws()
                local d = string.sub(s, pos, pos)
                pos = pos + 1
                if d == ']' then return out end
                if d ~= ',' then fail('a comma') end
            end
        elseif c == '"' then return str()
        elseif string.sub(s, pos, pos + 3) == 'true' then pos = pos + 4; return true
        elseif string.sub(s, pos, pos + 4) == 'false' then pos = pos + 5; return false
        elseif string.sub(s, pos, pos + 3) == 'null' then pos = pos + 4; return nil
        else
            local j = string.find(s, '[^%d%.eE+-]', pos) or (#s + 1)
            local n = tonumber(string.sub(s, pos, j - 1))
            if not n then fail('a value') end
            pos = j
            return n
        end
    end
    local v = value()
    ws()
    if pos <= #s then fail('trailing text') end
    return v
end
Ship.decode = decode

-- The keys of the save (4.3). mtb_crew_<group>: {standing, order = {option, paid}} (an older save of the mod holds the standing option alone: read so);
-- mtb_crew_groups: the groups in the order they got a state (the order the turn's news names them in).
Ship.SAVE_KEYS = {'mtb_crew_groups', 'mtb_crew_chosen', 'mtb_ship_news', 'mtb_ship_unseen', 'mtb_ship_message', 'mtb_ship_turn_line',
                  'mtb_malakai_side', 'mtb_malakai_side_chosen', 'mtb_ship_tab', 'mtb_ship_scroll'}

-- view: the panel's own {tab = string | nil, scroll = table | nil}
function Ship.save_state(M, view)
    view = view or {}
    local out = {}
    local names = {}
    for _, st in ipairs(M.crew_snapshot()) do
        names[#names + 1] = st.group
        out['mtb_crew_' .. st.group] = encode({standing = st.standing, order = st.order})
    end
    out.mtb_crew_groups = table.concat(names, ',')
    out.mtb_crew_chosen = encode(M.crew_chosen())
    local ship = M.news_snapshot()
    out.mtb_ship_news = ship.news and encode(ship.news) or ''
    out.mtb_ship_unseen = ship.unseen and '1' or '0'
    local msg = M.message_snapshot()
    out.mtb_ship_message = msg.text or ''
    out.mtb_ship_turn_line = msg.turn_line and encode(msg.turn_line) or ''
    out.mtb_malakai_side = M.malakai_side()
    out.mtb_malakai_side_chosen = M.side_hint() and '0' or '1'
    out.mtb_ship_tab = view.tab or ''
    out.mtb_ship_scroll = view.scroll and encode(view.scroll) or ''
    return out
end

-- get(key) -> the saved string or nil (a fresh campaign). Restores M as the page's load does (web/js/main.js), then the ship is synced.
function Ship.load_state(M, get)
    local function s(k) local v = get(k); if v == nil then return nil end return tostring(v) end
    local function obj(k) local v = s(k); if v == nil or v == '' then return nil end return decode(v) end
    local side = s('mtb_malakai_side')
    if side and side ~= '' then M.set_side_silently(side) end
    M.set_side_chosen_silently(s('mtb_malakai_side_chosen') == '1')
    local order = {}
    local listed = s('mtb_crew_groups')
    if listed then
        for g in string.gmatch(listed, '[^,]+') do order[#order + 1] = g end
    else
        for _, g in ipairs(M.group_order) do order[#order + 1] = g end
    end
    local crew = {}
    for _, g in ipairs(order) do
        local v = s('mtb_crew_' .. g)
        if v and v ~= '' then
            local st
            if string.sub(v, 1, 1) == '{' then st = decode(v) else st = {standing = v} end
            crew[#crew + 1] = {group = g, standing = st.standing, order = st.order}
        end
    end
    M.set_crew_silently(crew)
    M.set_crew_chosen_silently(obj('mtb_crew_chosen') or {})
    M.set_news_silently({news = obj('mtb_ship_news'), unseen = s('mtb_ship_unseen') == '1'})
    M.set_message_silently({text = s('mtb_ship_message'), turn_line = obj('mtb_ship_turn_line')})
    M.sync_ship()
    local tab = s('mtb_ship_tab')
    return {tab = (tab ~= '' and tab) or nil, scroll = obj('mtb_ship_scroll')}
end

return Ship
