-- The replay of build/vectors on the Lua of the pack (tools/lua_vectors.py loads this): a world of the mod's modules over the fake game, the actions
-- of a step, the answers after it in the fields and the forms tools/tests/vectors_export.mjs writes them. Only for the offline replay.
--
--   local R = <this>(Ship, CrewModel, Fake)
--   R.world(config, sim) -> w;  R.apply(w, action) -> what it answered;  R.observe(w) -> 'field\tvalue' lines;  R.unit(call) -> the result

return function(Ship, CM, Fake)
    local R = {}
    local NULL = {}
    local num = Ship.num
    -- the game's string.sub counts UTF-8 characters (tools/game_lua_env.py); the driver cuts bytes, as plain Lua does
    local ssub = string.sub_lua or string.sub

    function R.world(config, sim)
        local w = {config = config, sim = sim, view = {}}
        w.game = Fake.new(config, sim)
        w.M = Ship.make(config, w.game, CM)
        return w
    end

    local function short(w, k)
        local p = w.config.prefix
        if ssub(k, 1, #p) == p then return ssub(k, #p + 1) end
        return k
    end
    local function join(list, sep, fn)
        local out = {}
        for i, x in ipairs(list) do out[i] = fn and fn(x) or x end
        return table.concat(out, sep)
    end
    local function opt(v) if v == nil then return NULL end return v end

    function R.observe(w)
        local M, game, config = w.M, w.game, w.config
        local o, order = {}, {}
        local function put(f, v) o[f] = opt(v); order[#order + 1] = f end
        local sk = function(k) return short(w, k) end
        put('turn', game.turn())
        put('treasury', game.treasury())
        put('message', M.message())
        put('first_step', M.first_step())
        put('upkeep', M.crew_upkeep())
        put('upkeep_next', M.crew_upkeep_next())
        put('side', M.malakai_side())
        put('side_hint', M.side_hint())
        put('unseen', M.ship_unseen())
        local n = M.ship_news()
        put('news', n and table.concat({join(n.built, ',', sk), join(n.parts, ','), join(n.places, ','), join(n.kinds or {}, ',')}, ' | ') or nil)
        put('news_places', join(M.news_places(), ','))
        put('carried', M.carried() and true or false)
        put('view.tab', w.view.tab)
        local s = w.view.scroll
        put('view.scroll', s and (num(s.x) .. ',' .. num(s.y) .. ',' .. num(s.zoom)) or nil)
        for _, r in ipairs(config.levels) do
            local k = r.key
            local b = 'b.' .. sk(k)
            local st = M.status(k)
            put(b, st.state .. (st.turns ~= nil and (':' .. num(st.turns)) or ''))
            put(b .. '.why', st.why or '')
            put(b .. '.poor', st.poor and true or false)
            put(b .. '.missing', join(st.missing or {}, ',', function(x) if ssub(x, 1, 5) == 'tier:' then return x end return sk(x) end))
            put(b .. '.reason', M.reason(k))
            local d = M.can_demolish(k)
            put(b .. '.demolish', d.ok and 'ok' or d.why)
            put(b .. '.stands', M.stands(k))
            put(b .. '.has', game.has_building(k))
        end
        for _, p in ipairs(config.parts) do put('part.' .. p.key, M.stage(p.key)) end
        local sources = CM.crew_sources(config, function(k) return game.has_building(k) end, function(k) return game.standing(k) end)
        for _, group in ipairs(config.groups) do
            local G = group.key
            local c = 'crew.' .. G
            put(c, M.crew(G))
            put(c .. '.order', M.crew_order(G))
            put(c .. '.place', M.crew_place(G) and true or false)
            local po = M.place_opener(G)
            put(c .. '.opener', po and sk(po.key) or nil)
            put(c .. '.hint', M.crew_hint(G))
            local note = M.crew_note(G)
            put(c .. '.note', note and ((note.bad and '!' or '') .. note.text) or nil)
            local opts = M.crew_options(G)
            put(c .. '.options', join(opts, ',', function(x) return x.key .. (x.unlocked and '+' or '-') .. (x.building and ('@' .. sk(x.building.key)) or '') end))
            for _, x in ipairs(opts) do
                local p = M.crew_preview(G, x.key)
                put(c .. '.' .. x.key .. '.preview', p.kind .. ':' .. (p.bad and '!' or '') .. p.text)
            end
            local bonus = CM.crew_bonuses(sources, G)
            for _, kind in ipairs(CM.CREW_KINDS) do
                put(c .. '.bonus.' .. kind, num(bonus[kind].pct) .. ' ' .. join(bonus[kind].from, ', ', function(f) return (f.mod and '*' or '') .. f.name .. ':' .. num(f.value) end))
            end
            for _, op in ipairs(group.options) do
                if op.ammo ~= nil then
                    local a = CM.crew_ammo({ammo = op.ammo, seats = op.seats}, bonus.ammo.pct, op.men or 0)
                    put(c .. '.' .. op.key .. '.ammo', num(a.places) .. '/' .. num(a.base) .. '/' .. num(a.total) .. '/' .. num(a.per) .. '/' .. tostring(a.whole))
                    put(c .. '.' .. op.key .. '.ammo_line', CM.ammo_share(a, G, group.per))
                end
            end
        end
        -- one string: field TAB typed value, a line a field
        local lines = {}
        local function esc(v) return (string.gsub(v, '[\\\n\t]', {['\\'] = '\\\\', ['\n'] = '\\n', ['\t'] = '\\t'})) end
        for _, f in ipairs(order) do
            local v = o[f]
            local t
            if v == NULL then t = 'z'
            elseif type(v) == 'boolean' then t = v and 'b:true' or 'b:false'
            elseif type(v) == 'number' then t = 'n:' .. string.format('%.17g', v)
            else t = 's:' .. esc(tostring(v)) end
            lines[#lines + 1] = f .. '\t' .. t
        end
        return table.concat(lines, '\n')
    end

    local function truthy(v) return v ~= nil and v ~= false and v ~= '' end
    local function said(r)
        return (r.ok and 'ok' or 'no') .. (truthy(r.why) and (':' .. r.why) or '') .. (truthy(r.kind) and (':' .. r.kind) or '')
    end

    function R.apply(w, a)
        local M, game = w.M, w.game
        local k = a.key
        local act = a['do']
        if act == 'click' then
            local st = M.status(k).state
            if st == 'open' then return 'order ' .. said(M.order(k)) end
            if st == 'building' then return 'cancel ' .. said(M.cancel(k)) end
            if st == 'locked' or st == 'unknown' then return 'refuse ' .. tostring(M.refuse(k)) end
            return 'none'
        elseif act == 'order' then return said(M.order(k))
        elseif act == 'cancel' then return said(M.cancel(k))
        elseif act == 'demolish' then return said(M.demolish(k))
        elseif act == 'refuse' then return tostring(M.refuse(k))
        elseif act == 'set_crew' then return said(M.set_crew(a.group, a.option))
        elseif act == 'end_turn' then game.end_turn(); return ''
        elseif act == 'ship_seen' then M.ship_seen(); return ''
        elseif act == 'side' then M.set_malakai_side(a.side); return ''
        elseif act == 'gold' then game.set_gold(a.gold); return ''
        elseif act == 'debug_build' then M.debug_build_to(k); return ''
        elseif act == 'game_dismantle' then return tostring(game.dismantle(k))
        elseif act == 'chosen_old' then M.set_crew_chosen_silently(true); return ''
        elseif act == 'game_refuses' then
            -- the game takes the next order silently without doing it (right after a battle)
            -- one refusal however many times it is asked for before an order (as the page's driver: the override is one)
            game.real_issue = game.real_issue or game.issue_building_command
            game.issue_building_command = function() game.issue_building_command = game.real_issue; return true end
            return ''
        elseif act == 'view' then w.view = {tab = a.tab, scroll = a.scroll}; return ''
        elseif act == 'reload' then
            -- the mod's save: every value a string (cm:set_saved_value), the game's own state (buildings, queue, gold) kept by the game
            local saved = Ship.save_state(M, w.view)
            for key, v in pairs(saved) do
                if type(v) ~= 'string' then error('saved value ' .. key .. ' is a ' .. type(v) .. ', not a string') end
            end
            local snap = game.snapshot()
            local game2 = Fake.new(w.config, w.sim)
            local M2 = Ship.make(w.config, game2, CM)
            game2.restore(snap)
            w.view = Ship.load_state(M2, function(key) return saved[key] end)
            w.game, w.M = game2, M2
            w.saved = saved
            return ''
        end
        error('unknown action ' .. tostring(act))
    end

    -- the strings the last reload saved ({key = string}), for the runner's checks
    function R.saved_of(w) return w.saved end

    -- the pure functions of crew_model.lua
    local function ctxOf(c)
        local open = {}
        for _, o in ipairs(c.open or {}) do open[o] = true end
        return {start = c.start, gold = c.gold, unlocked = function(o) return open[o] == true end, hire = function(o) return (c.hire or {})[o] end}
    end
    local function stateOf(s) return {standing = s.standing, order = s.order and {option = s.order.option, paid = s.order.paid} or nil} end
    function R.unit(u)
        local fn = u.fn
        if fn == 'click' then return CM.click(stateOf(u.state), u.option, ctxOf(u.ctx)) end
        if fn == 'turn' then return CM.turn(stateOf(u.state)) end
        if fn == 'held' then return CM.held(stateOf(u.state)) end
        if fn == 'lose' then return CM.lose(stateOf(u.state), ctxOf(u.ctx)) end
        if fn == 'bonuses' then
            local built = {}
            for _, k in ipairs(u.built) do built[k] = true end
            local has = function(k) return built[k] == true end
            return CM.crew_bonuses(CM.crew_sources(u.config, has, has), u.group)
        end
        if fn == 'apply_pct' then return CM.apply_pct(u.base, u.pct, u.kind) end
        if fn == 'ammo' then
            local a = CM.crew_ammo(u.n, u.pct, u.men)
            return {a = a, line = CM.ammo_share(a, u.group, u.per)}
        end
        if fn == 'plural' then return CM.plural(u.v, CM.PLACE_NOUNS[u.group] or {'место', 'места', 'мест'}) end
        if fn == 'turns_text' then return Ship.turns_text(u.v) end
        if fn == 'upper_first' then return Ship.upper_first(u.s) end
        if fn == 'new_kinds_text' or fn == 'requires_text' or fn == 'status' then
            -- on the author's tree (R.author: the packed config), a fresh campaign
            local w = R.world(R.author, {turn = 1, gold = 6000, income = 0, built = {}})
            if fn == 'new_kinds_text' then return w.M.new_kinds_text(u.group, u.names) end
            if fn == 'requires_text' then return w.M.requires_text(u.keys) end
            return {status = w.M.status(u.key), reason = w.M.reason(u.key), order = w.M.order(u.key)}
        end
        error('unknown unit ' .. tostring(fn))
    end
    return R
end
