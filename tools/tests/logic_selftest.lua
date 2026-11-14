-- The self-test of the screen logic's string and number primitives, for the game's own Lua (one cheap probe item) and for the offline Lua.
-- No UI, no cm, no core, no saved values of the game: a tiny inline game (a table) stands under the module, so nothing of the campaign moves.
--
--   local T = <this chunk>; local results = T(Ship, CrewModel)      -- {name = string}; results._text = 'name<TAB>value' lines, by name
-- Every input is a number a float32 holds exactly (so the answers are the same in doubles and in floats), except the f32.* items: their
-- literals are rounded by the game's Lua when it reads this chunk; offline the expected answers are made by passing the float32 values as the
-- third argument (T(Ship, CM, f32_inputs)), so in the game they show that its numbers are the floats the offline check assumes.
-- Ship and CrewModel are src/tww3_mtb_ship.lua and src/tww3_mtb_crew_model.lua as loaded in that Lua. The expected strings are in
-- tools/tests/logic_selftest.json (py -3.10 tools/tests/logic_selftest.py writes them from plain Lua and the game's emulated Lua, which must
-- agree); a value that differs in the game is a difference between the game's Lua and both offline ones.

return function(Ship, CM, f32_inputs)
    local R = {}
    local ssub = string.sub_lua or string.sub
    local function put(name, v)
        if type(v) == 'number' then v = CM.num(v) elseif type(v) ~= 'string' then v = tostring(v) end
        R[name] = v
    end
    local function try(name, fn)
        local ok, v = pcall(fn)
        if ok then put(name, v) else R[name] = 'ERROR ' .. tostring(v) end
    end

    -- ---- the saved-state encoder / decoder (strings through cm:set_saved_value) ----
    local TEXT = 'Стрелки встали к бортам; «Гнёзда»: ёЁ, "кавычки", обратная \\ черта, перевод\nстроки, таб\tи байт \1.'
    try('save.text', function() return Ship.encode(TEXT) end)
    try('save.text_back', function() return Ship.decode(Ship.encode(TEXT)) == TEXT end)
    try('save.table', function()
        return Ship.encode({standing = 'pirates', order = {option = 'quarrellers', paid = 80}, turn_line = {turn = 12, text = 'Ход 12: всё на местах.'},
                            scroll = {x = -885, y = 194, zoom = 0.5}, chosen = {rifles = true, cannons = false}, list = {1, 'два', -3}})
    end)
    try('save.table_again', function()
        local s = Ship.encode({a = {x = 0.5, y = -3}, b = 'Ж', c = {}})
        return Ship.encode(Ship.decode(s)) == s
    end)
    try('save.numbers', function()
        return Ship.encode({0, -1, 0.25, -0.5, 16777216, 2147483648, -2147483648, 3000000000, 1.5})
    end)
    try('save.numbers_back', function()
        local s = Ship.encode({16.6, 0.1, 1 / 3})
        local t = Ship.decode(s)
        return Ship.encode(t) == s
    end)
    -- standard JSON with \u escapes (the decoder builds the UTF-8 bytes itself)
    try('save.json_u', function() return Ship.decode('{"k":"\\u0430\\u0451\\u00e9\\u20ac\\u0001 \\"q\\" \\\\ end","n":[1.5,-2e-3,12]}').k end)
    try('save.json_u_bytes', function() return #Ship.decode('"\\u0430\\u20ac"') end)
    try('save.json_n', function() return Ship.encode(Ship.decode('[1.5,-25e-2,12,1e2]')) end)

    -- ---- a tiny ship: one hull, one building that needs it, one crew group; the game is a table ----
    local P = 'tst_'
    local config = {
        prefix = P, tree = true,
        levels = {{key = P .. 'hull_1', name = 'Корпус I', chain = 'hull', level = 1, tier = 1, cost = 1500, turns = 2, requires = {}},
                  {key = P .. 'hall_1', name = 'Пивной чертог', chain = 'hall', level = 1, tier = 1, cost = 900, turns = 3, requires = {P .. 'hull_1'},
                   unlocks = {{group = 'rifles', option = 'pirates'}}}},
        chains = {{key = 'hull', levels = {P .. 'hull_1'}}, {key = 'hall', levels = {P .. 'hall_1'}}},
        hull_tiers = {{key = P .. 'hull_1', tier = 1}},
        groups = {{key = 'rifles', name = 'Стрелки', start = 'empty',
                   options = {{key = 'empty', name = 'Пусто', hire = 0, upkeep = 0}, {key = 'pirates', name = 'Небесные пираты', hire = 110, upkeep = 30}}}},
        parts = {},
    }
    local function newGame(gold, built)
        local G, ev, has = {}, {}, {}
        for _, k in ipairs(built or {}) do has[k] = true end
        function G.treasury() return gold end
        function G.treasury_mod(d) gold = gold + d end
        function G.turn() return 7 end
        function G.has_building(k) return has[k] == true end
        function G.standing(k) return has[k] == true end
        function G.under_construction() return nil end
        function G.issue_building_command() return false end
        function G.cancel_construction() return false end
        function G.dismantle() return false end
        function G.on(name, fn) ev[name] = fn end
        return G
    end

    -- the reasons a building cannot be ordered: short of gold; a requirement missing
    try('reason.poor', function() return Ship.make(config, newGame(1200), CM).reason(P .. 'hull_1') end)
    try('reason.missing', function() return Ship.make(config, newGame(1200), CM).reason(P .. 'hall_1') end)
    try('reason.requires_two', function() return Ship.make(config, newGame(1200), CM).requires_text({P .. 'hull_1', 'tier:2', P .. 'nothing_9'}) end)
    try('reason.order_open', function()
        local M = Ship.make(config, newGame(5000, {P .. 'hull_1'}), CM)
        return M.reason(P .. 'hall_1') .. '|' .. M.status(P .. 'hall_1').state
    end)

    -- the crew: an order and its words, the saved state through a second ship and back to the same strings
    try('crew.order', function()
        local game = newGame(5000, {P .. 'hull_1', P .. 'hall_1'})
        local M = Ship.make(config, game, CM)
        local r = M.set_crew('rifles', 'pirates')
        return tostring(r.ok) .. '|' .. M.message() .. '|' .. CM.num(game.treasury())
    end)
    try('crew.save_round_trip', function()
        local game = newGame(5000, {P .. 'hull_1', P .. 'hall_1'})
        local M = Ship.make(config, game, CM)
        M.set_crew('rifles', 'pirates')
        M.set_malakai_side('right')
        local saved = Ship.save_state(M, {tab = 'crew', scroll = {x = -885, y = 194, zoom = 0.5}})
        local M2 = Ship.make(config, newGame(4890, {P .. 'hull_1', P .. 'hall_1'}), CM)
        local view = Ship.load_state(M2, function(k) return saved[k] end)
        local again = Ship.save_state(M2, view)
        local keys = {}
        for k in pairs(saved) do keys[#keys + 1] = k end
        table.sort(keys)
        local lines, same = {}, true
        for _, k in ipairs(keys) do
            if again[k] ~= saved[k] then same = false end
            lines[#lines + 1] = k .. '=' .. saved[k]
        end
        return tostring(same) .. '|' .. table.concat(lines, ';')
    end)

    -- ---- the words: the first letter up, turns, numbers ----
    try('words.upper', function()
        local out = {}
        for _, s in ipairs({'стрелки встали', 'ёж', 'яма', 'abc', 'Уже', '«кавычка»', ''}) do out[#out + 1] = Ship.upper_first(s) end
        return table.concat(out, '|')
    end)
    try('words.turns', function() return Ship.turns_text(1) .. '|' .. Ship.turns_text(3) .. '|' .. Ship.turns_text(12) .. '|' .. Ship.turns_text(21) .. '|' .. Ship.turns_text(111) end)
    try('words.num', function()
        return table.concat({Ship.num(0), Ship.num(-0.5), Ship.num(16.6), Ship.num(1 / 3), Ship.num(2147483648), Ship.num(3000000000), CM.num(12.25), CM.num(-7)}, '|')
    end)
    try('words.plural', function() return CM.plural(1, CM.PLACE_NOUNS.rifles) .. '|' .. CM.plural(4, CM.PLACE_NOUNS.cannons) .. '|' .. CM.plural(11, CM.PLACE_NOUNS.cupolas) end)

    -- ---- the ammunition and the bonuses (fractional multipliers: float32 in the game) ----
    try('ammo.mod_pct', function() return CM.round((1.15 - 1) * 100) .. '|' .. CM.round((1.4 - 1) * 100) .. '|' .. CM.round((1 - 0.85) * 100) .. '|' .. CM.round((1.1 - 1) * 100) end)
    try('ammo.apply_pct', function()
        return table.concat({CM.num(CM.apply_pct(15, 10, 'reload')), CM.num(CM.apply_pct(13.8, 20, 'reload')), CM.num(CM.apply_pct(200, 15, 'ammo')), CM.num(CM.apply_pct(37, -30, 'range'))}, '|')
    end)
    try('ammo.share_whole', function()
        local a = CM.crew_ammo({ammo = 200, seats = 10}, 15, 0)
        return CM.num(a.places) .. '/' .. CM.num(a.base) .. '/' .. CM.num(a.total) .. '/' .. CM.num(a.per) .. '/' .. tostring(a.whole) .. '|' .. CM.ammo_share(a, 'rifles')
    end)
    try('ammo.share_part', function()
        local a = CM.crew_ammo({ammo = 392, seats = 11}, 15, 0)
        return CM.num(a.places) .. '/' .. CM.num(a.base) .. '/' .. CM.num(a.total) .. '/' .. CM.num(a.per) .. '/' .. tostring(a.whole) .. '|' .. CM.ammo_share(a, 'cannons', 'на ствол')
    end)
    try('ammo.share_men', function()
        local a = CM.crew_ammo({ammo = 392, seats = 11}, 40, 7)
        return CM.num(a.places) .. '/' .. CM.num(a.base) .. '/' .. CM.num(a.total) .. '/' .. CM.num(a.per) .. '/' .. tostring(a.whole) .. '|' .. CM.ammo_share(a, 'bombs')
    end)
    try('ammo.bonuses', function()
        local cfg = {tree = true, ammo_mod = {{key = 'w', mult = 1.15}},
                     sources = {{key = 'w', name = 'Мастерская', effects = {{kind = 'reload', target = 'all', value = -10}}}},
                     groups = {{key = 'rifles', boost = {{building = 'w', spread = 0.85, range = 1.1}}}}}
        local has = function(k) return k == 'w' end
        local b = CM.crew_bonuses(CM.crew_sources(cfg, has, has), 'rifles')
        local out = {}
        for _, k in ipairs(CM.CREW_KINDS) do out[#out + 1] = k .. '=' .. CM.num(b[k].pct) end
        return table.concat(out, ',')
    end)

    -- ---- numbers a float32 does not hold: the game rounds these literals as it reads the chunk ----
    local F = f32_inputs or {16.6, 0.1, 2147483647, 16777217, 0.001, 1 / 3, 0.01, 0.0999999}
    try('f32.save', function() return Ship.encode(F) end)
    try('f32.save_back', function() local s = Ship.encode(F); return Ship.encode(Ship.decode(s)) == s end)
    try('f32.num', function()
        local out = {}
        for i, v in ipairs(F) do out[i] = Ship.num(v) end
        return table.concat(out, '|')
    end)
    try('f32.step', function() local big = F[4]; return Ship.num(big + 1) .. '|' .. Ship.num(F[3] - 1) end)

    -- ---- the strings of the game's Lua the module relies on ----
    try('lua.bytes', function() return #'Дух' .. '|' .. ssub('Дух', 1, 2) .. '|' .. #ssub('Дух', 3) end)

    local names = {}
    for k in pairs(R) do names[#names + 1] = k end
    table.sort(names)
    local lines = {}
    for _, k in ipairs(names) do lines[#lines + 1] = k .. '\t' .. R[k] end
    R._text = table.concat(lines, '\n')
    return R
end
