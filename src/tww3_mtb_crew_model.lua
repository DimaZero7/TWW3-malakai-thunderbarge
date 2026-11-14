-- The order of a crew group and the crew's numbers as the player reads them: the Lua of web/js/crew_model.mjs, function for function
-- (docs/design/port-to-game.md, 4.1). Pure: no game, no UI, no saved values. Proven against the page by tools/lua_vectors.py.
--
--   state   {standing = option, order = nil | {option, paid}}
--   ctx     {start = the empty option, unlocked = function(option) -> bool, hire = function(option) -> gold, gold = the treasury now}
--
--   click(state, option, ctx) -> {state, gold, result}     result.kind: 'ordered' | 'cancelled' | 'kept' | 'locked' | 'poor'
--   turn(state) -> state                                    the faction's turn start: the order goes in
--   lose(state, ctx) -> {state, gold, lost}                 a building is gone
--   held(state) -> gold                                     what the waiting order holds
--   crew_sources(config, has, standing) -> [{effect, from, mod}]   what acts on the crew's shooting (web/js/crew_model.mjs crewSources)
--   crew_bonuses(sources, group) -> {kind = {pct, from}}           the percents of one group (web/js/effects_model.mjs crewBonuses)
--   apply_pct(base, pct, kind)                                     a number with a bonus (effects_model.mjs applyPct)
--   crew_places(n, men), crew_ammo(n, pct, men), plural(v, forms), ammo_share(a, group, per)
--
-- The same in the game's Lua and in plain Lua 5.1 (tools/game_lua_env.py; the replay runs under it): no string cutting, no math.huge, numbers
-- written by M.num; every number of the crew is whole and far below 2^24 except the fractional multipliers of the config (float32 in the game),
-- whose products are rounded to whole by round() before anyone reads them.
-- Loaded as a module (it returns its table and sets nothing global). Not read by the running mod yet: src/tww3_mtb_crew.lua keeps its own rule
-- until stage 3 calls this one.

local M = {}

local floor = math.floor
local function round(x) return floor(x + 0.5) end      -- JS Math.round: half up
M.round = round

local function copy_order(o)
    if not o then return nil end
    return {option = o.option, paid = o.paid}
end

function M.click(state, option, ctx)
    local function same(result) return {state = state, gold = ctx.gold, result = result} end
    if option ~= ctx.start and not ctx.unlocked(option) then return same({kind = 'locked', option = option}) end
    local paid = state.order and state.order.paid or 0
    if option == state.standing then
        if not state.order then return same({kind = 'kept', option = option, why = 'standing'}) end
        return {state = {standing = state.standing, order = nil}, gold = ctx.gold + paid,
                result = {kind = 'cancelled', option = state.order.option, back = paid, taken = 0}}
    end
    if state.order and state.order.option == option then return same({kind = 'kept', option = option, why = 'ordered'}) end
    local hire = 0
    if option ~= ctx.start then hire = ctx.hire(option) end
    if hire > 0 and ctx.gold + paid < hire then return same({kind = 'poor', option = option, hire = hire, have = ctx.gold + paid}) end
    return {state = {standing = state.standing, order = {option = option, paid = hire}}, gold = ctx.gold + paid - hire,
            result = {kind = 'ordered', option = option, back = paid, taken = hire, instead = state.order and state.order.option or nil}}
end

function M.turn(state)
    if state.order then return {standing = state.order.option, order = nil} end
    return state
end

function M.lose(state, ctx)
    local standing, order, gold = state.standing, copy_order(state.order), ctx.gold
    local lost = {}
    if order and order.option ~= ctx.start and not ctx.unlocked(order.option) then
        lost[#lost + 1] = {option = order.option, kind = 'order', back = order.paid}
        gold = gold + order.paid
        order = nil
    end
    if standing ~= ctx.start and not ctx.unlocked(standing) then
        lost[#lost + 1] = {option = standing, kind = 'standing', back = 0}
        standing = ctx.start
        if order and order.option == ctx.start then order = nil end      -- an order to take off a crew that has already left
    end
    return {state = {standing = standing, order = order}, gold = gold, lost = lost}
end

function M.held(state)
    return state.order and state.order.paid or 0
end

-- ---- what acts on the crew's shooting ----
M.CREW_KINDS = {'ammo', 'accuracy', 'range', 'reload', 'damage'}
local IS_CREW = {ammo = true, accuracy = true, range = true, reload = true, damage = true}
local function targets(e, g) return e.target == 'all' or e.target == nil or e.target == '' or e.target == g end

-- config: the ship's config (tools/ship_config.mjs): sources (the tree's rows in the tree's order, their crew effects), ammo_mod, groups with boost.
-- has(key): the building stands (a lower level counts under a higher one); standing(key): it is the level in its slot.
function M.crew_sources(config, has, standing)
    standing = standing or has
    local mods = {}
    for _, a in ipairs(config.ammo_mod or {}) do mods[a.key] = a.mult end
    local out = {}
    for _, r in ipairs(config.sources) do
        local own = r.effects
        local acts = config.tree and standing or has
        if acts(r.key) then for _, e in ipairs(own) do out[#out + 1] = {effect = e, from = r.name} end end
        if standing(r.key) then
            local function says(kind, g)
                for _, e in ipairs(own) do if e.kind == kind and targets(e, g) then return true end end
                return false
            end
            local mult = mods[r.key]
            local own_ammo = false
            for _, e in ipairs(own) do if e.kind == 'ammo' then own_ammo = true end end
            if mult and mult ~= 0 and not own_ammo then out[#out + 1] = {effect = {kind = 'ammo', target = 'all', value = round((mult - 1) * 100)}, from = r.name, mod = true} end
            for _, group in ipairs(config.groups) do
                local g = group.key
                for _, b in ipairs(group.boost or {}) do
                    if b.building == r.key then
                        if b.spread and b.spread ~= 0 and b.spread < 1 and not says('accuracy', g) then
                            out[#out + 1] = {effect = {kind = 'accuracy', target = g, value = round((1 - b.spread) * 100)}, from = r.name, mod = true}
                        end
                        if b.range and b.range ~= 0 and b.range > 1 and not says('range', g) then
                            out[#out + 1] = {effect = {kind = 'range', target = g, value = round((b.range - 1) * 100)}, from = r.name, mod = true}
                        end
                    end
                end
            end
        end
    end
    return out
end

function M.crew_bonuses(sources, group)
    local out = {}
    for _, k in ipairs(M.CREW_KINDS) do out[k] = {pct = 0, from = {}} end
    for _, s in ipairs(sources) do
        local e = s.effect
        if IS_CREW[e.kind] and targets(e, group) then
            out[e.kind].pct = out[e.kind].pct + e.value
            local f = out[e.kind].from
            f[#f + 1] = {name = s.from, value = e.value, mod = not not s.mod}
        end
    end
    return out
end

function M.apply_pct(base, pct, kind)
    local v = base * (1 + pct / 100)
    if kind == 'reload' then return round(v * 10) / 10 end
    return round(v)
end

-- ---- the ammunition of a crew as the player reads it ----
-- n: an option's numbers {ammo, seats}; men: the men of its card
function M.crew_places(n, men)
    if not n or not n.seats or n.seats == 0 then return 0 end
    if men and men ~= 0 and men < n.seats then return men end
    return n.seats
end

function M.crew_ammo(n, pct, men)
    local places = M.crew_places(n, men)
    local base = n.ammo
    if places ~= 0 and places ~= n.seats then base = round(n.ammo * places / n.seats) end
    local total = round(base * (1 + (pct or 0) / 100))      -- the page's Math.floor(x + 0.5): round() is the same, and the float32 check sees x
    local each = total
    if places ~= 0 then each = total / places end
    return {places = places, base = base, total = total, each = each, whole = each == floor(each), per = round(each)}
end

M.PLACE_NOUNS = {rifles = {'стрелок', 'стрелка', 'стрелков'}, cannons = {'ствол', 'ствола', 'стволов'}, bombs = {'люк', 'люка', 'люков'},
                 cupolas = {'гнездо', 'гнезда', 'гнёзд'}, harpoon = {'гарпун', 'гарпуна', 'гарпунов'}}

-- JS v % 10 for v >= 0 (the numbers of places and turns are never negative)
local function mod(a, b) return a - floor(a / b) * b end
M.mod = mod

function M.plural(v, forms)
    local m10, m100 = mod(v, 10), mod(v, 100)
    if m10 == 1 and m100 ~= 11 then return forms[1] end
    if m10 >= 2 and m10 <= 4 and (m100 < 12 or m100 > 14) then return forms[2] end
    return forms[3]
end

-- a number as JS writes it in a template (`${n}`), the same in the game's Lua (32-bit floats, %d wraps above 2^31, no %g in vanilla
-- scripts) and in plain Lua: a whole number in full (%d below 2^31, %.0f beyond), a fraction to 6 significant digits with the trailing zeros
-- cut (the text JS writes for a number of at most 6 digits; tostring would write 16.60000038147 for the game's 16.6). As Ship.num.
local sformat, sgsub, sfind = string.format, string.gsub, string.find_lua or string.find
local TWO31 = 2147483648
local function whole(n)
    if n > -TWO31 and n < TWO31 then return sformat('%d', n) end
    return sformat('%.0f', n)
end
function M.num(n)
    if n ~= n or n == 1 / 0 or n == -1 / 0 then return tostring(n) end
    if n == floor(n) then return whole(n) end
    local a = n < 0 and -n or n
    local p
    if a >= 1 then
        p = 6 - #whole(floor(a))
        if p < 0 then p = 0 end
    else      -- the place of the first digit read off the printed number (a * 10 rounds differently in a float and in a double)
        local zeros = string.match(sformat('%.50f', a), '^0%.(0*)[1-9]')
        if not zeros then return '0' end
        p = 6 + #zeros
    end
    local s = sformat('%.' .. whole(p) .. 'f', n)
    if sfind(s, '.', 1, true) then s = sgsub(sgsub(s, '0+$', ''), '%.$', '') end
    if s == '-0' then s = '0' end
    return s
end

function M.ammo_share(a, group, per)
    if not a.places or a.places == 0 then return '' end
    local noun = M.plural(a.places, M.PLACE_NOUNS[group] or {'место', 'места', 'мест'})
    if a.whole then return M.num(a.places) .. ' ' .. noun .. ' по ' .. M.num(a.each) end
    return M.num(a.places) .. ' ' .. noun .. ', около ' .. M.num(a.per) .. ' ' .. (per or 'на место')
end

return M
