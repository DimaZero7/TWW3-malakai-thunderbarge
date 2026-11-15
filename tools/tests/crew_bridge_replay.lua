-- The new panel's crew bridge replayed without the game (tools/crew_bridge_offline.py loads this; docs/design/port-to-game.md 8.6): the page's
-- scenarios (build/vectors) run on the screen's model (src/tww3_mtb_ship.lua over the page's fake game, tools/tests/fake_game.lua) AND on the old
-- mod's crew module as packed (script/campaign/mod/tww3_mtb_crew.lua) with NEW_SHIP_PANEL on, in one fake campaign: the same saved values, the
-- game's events in the game's order to the old module (the completions before FactionTurnStart), the model's in the adapter's order. The old
-- module's write into memory (apply) is replaced by a recorder of what it would write: the seat plan, the choice, the cargo, Malakai's seat.
-- After every step R.check says where the seats, the harpoon's bundle, the cargo or the gold differ from what the model has standing, and
-- where the numbers the panel shows for a crew differ from those the battle applies beyond the known gaps (X.unapplied).
--
--   local R = <this>(Ship, CM, Fake, VR, crew_source, load_crew, X)
--     VR           tools/tests/vectors_replay.lua made over the same modules (its actions are reused as they are)
--     load_crew    function(source) running the crew module's chunk in its own environment (tools/game_lua_env.py load_mod)
--     X            the expectations of the tree (tools/crew_bridge_offline.py): boost {group = {keys, steps}}, ammo_mod {key = mult},
--                  malakai {seats, rows, helm_seat, helm_crew}, unapplied {"name|kind|target" = true}, battle_mod {"name|kind|group" = true}
--   R.world(config, sim) -> w;  R.apply(w, action) -> answer;  R.check(w, expected) -> {problem lines};  R.gaps() -> {line = count}

return function(Ship, CM, Fake, VR, CREW, load_crew, X)
    local R = {}
    local HOME = 'wh3_dlc25_dwf_malakai'
    local floor = math.floor
    local function round(x) return floor(x + 0.5) end
    local function push(list, v) list[#list + 1] = v end
    local gaps, gapOrder = {}, {}

    -- ---------------- the fake campaign the old module runs in (one per world; the globals point at the current world) ----------------
    local W = nil
    local function fire(event, ctx)
        for _, l in ipairs(W.listeners) do
            if l.event == event and (l.cond == true or l.cond(ctx)) then l.cb(ctx) end
        end
    end
    local function ours() return {name = function() return HOME end} end
    local function slotList()
        local keys = W.game.snapshot().built
        return {num_items = function() return #keys end,
                item_at = function(_, i) local k = keys[i + 1]; return {has_building = function() return true end, building = function() return k end} end}
    end
    local force = {
        command_queue_index = function() return 7 end,
        has_effect_bundle = function(_, b) return W.bundles[b] == true end,
        horde_details = function() return {is_null_interface = function() return false end, military_force_slot_list = function() return slotList() end} end,
    }
    local malakai = {has_military_force = function() return true end, military_force = function() return force end,
                     has_ancillary = function() return W.on_barge end}
    local faction = {is_human = function() return true end, treasury = function() return W.game.treasury() end,
                     military_force_list = function() return {num_items = function() return 1 end, item_at = function() return force end} end}
    _G.cm = {
        get_saved_value = function(_, k) return W.saved[k] end,
        set_saved_value = function(_, k, v) W.saved[k] = v end,
        turn_number = function() return W.game.turn() end,
        get_faction = function() return faction end,
        get_local_faction_name = function() return HOME end,
        -- every move of the treasury through cm is the OLD mechanics' (the model moves it through its game): none is expected
        treasury_mod = function(_, f, n) W.game.treasury_mod(n); push(W.moves, n) end,
        show_message_event = function(_, f, title) push(W.messages, title) end,
        apply_effect_bundle_to_force = function(_, b) W.bundles[b] = true end,
        remove_effect_bundle_from_force = function(_, b) W.bundles[b] = nil end,
    }
    _G.core = {
        svr_save_string = function(_, k, v) W.svr[k] = v end,
        add_listener = function(_, name, event, cond, cb)
            for i, l in ipairs(W.listeners) do if l.name == name then table.remove(W.listeners, i); break end end
            push(W.listeners, {name = name, event = event, cond = cond, cb = cb})
        end,
        remove_listener = function(_, name)
            for i, l in ipairs(W.listeners) do if l.name == name then table.remove(W.listeners, i); break end end
        end,
        get_tm = function()
            return {real_callback = function(_, fn, ms, name) push(W.timers, fn) end, repeat_real_callback = function() end, remove_real_callback = function() end}
        end,
    }
    _G.ModLog = function() end
    _G.tww3_mtb_campaign = {when_ready = function(cb) push(W.ready, cb) end, file_log = function(t) push(W.log, t) end,
                            find_malakai = function() return malakai end}
    _G.tww3_mtb_crew_ui = {NEW_SHIP_PANEL = true, ship_screen = function() return W.S end}

    -- the next ticks of the game: the real callbacks waiting (the bridge's turn pass)
    function R.tick(w)
        for _ = 1, 20 do
            local list = w.timers
            if #list == 0 then return end
            w.timers = {}
            for _, fn in ipairs(list) do fn() end
        end
    end

    -- the model over its game, the game's events forwarded to the old module in the game's order (8.2: every completion before Malakai's
    -- FactionTurnStart, with the slot already holding the level), then the old module started as the campaign's Lua starts
    local function boot(w, game, snap, saved)
        W = w
        w.game, w.told, w.listeners, w.ready, w.timers = game, {}, {}, {}, {}
        game.on('FactionTurnEnd', function()
            w.completing = {}
            for _, q in ipairs(game.snapshot().queue) do if q.turns_left <= 1 then push(w.completing, q.key) end end
        end)
        game.on('FactionTurnStart', function()
            for _, key in ipairs(w.completing or {}) do
                if game.standing(key) then
                    w.told[key] = true
                    fire('MilitaryForceBuildingCompleteEvent', {building = function() return key end})
                end
            end
            w.completing = nil
            fire('FactionTurnStart', {faction = ours})
        end)
        game.on('MilitaryForceBuildingCompleteEvent', function(ctx)
            if w.told[ctx.building] then w.told[ctx.building] = nil; return end
            fire('MilitaryForceBuildingCompleteEvent', {building = function() return ctx.building end})       -- a completion outside the turn (debug)
        end)
        local M = Ship.make(w.config, game, CM)
        if snap then game.restore(snap) end
        if saved then w.view = Ship.load_state(M, function(k) return w.saved[k] end) end
        w.M = M
        w.S = {M = M, game = game, save = function() for k, v in pairs(Ship.save_state(M, w.view)) do w.saved[k] = v end end,
               modules = function() return {CM = CM, Ship = Ship} end}
        M.on_change(function() w.S.save() end)          -- the screen's own listener comes first (src/tww3_mtb_ship_screen.lua S.start)
        _G.tww3_mtb_crew = nil
        load_crew(CREW)
        local C = _G.tww3_mtb_crew
        w.C = C
        -- the recording stub of the old application: what write_seats would point the seats at, and the cargo it hands to the battle
        C.apply = function()
            local rec = {choice = C.get(), plan = C.seat_plan(), cargo = C.ammo_mod(), malakai = C.malakai_seat(), step = w.step}
            push(w.applies, rec)
            w.last = rec
            W.svr.mtb_crew_ammo_mod = tostring(rec.cargo)
            C.status = 'applied'
            return true
        end
        for _, cb in ipairs(w.ready) do cb() end
        R.tick(w)
    end

    function R.world(config, sim)
        local w = {config = config, sim = sim, saved = {}, svr = {}, moves = {}, messages = {}, bundles = {}, applies = {}, log = {}, view = {},
                   on_barge = true, step = 0}
        boot(w, Fake.new(config, sim), nil, false)
        return w
    end

    -- a save and a load: the model's strings and the old module's values in the same saved values, the game's own state kept by the game; the
    -- campaign's Lua starts again (the old module and the bridge anew)
    local function reload(w)
        W = w
        w.game.tick()
        w.S.save()
        local snap = w.game.snapshot()
        boot(w, Fake.new(w.config, w.sim), snap, true)
    end

    function R.apply(w, a)
        W = w
        w.step = w.step + 1
        local ret
        if a['do'] == 'reload' then reload(w); ret = '' else ret = VR.apply(w, a) end
        -- a level stood by a script: the game tells nobody (no event), the seats follow at the next change, the turn start or the battle's start
        w.script_stood = a['do'] == 'script_stand'
        R.tick(w)
        return ret
    end
    R.info = {}

    -- ---------------- the checks ----------------
    local function groupsOf(config)
        local out = {}
        for _, g in ipairs(config.groups) do out[g.key] = g end
        return out
    end
    -- the option the seats must carry for a group, from the model alone: its standing; its empty place of a bay is the bay where the model has the
    -- place, the plain ship (the group's start: none) where it has not
    local function expectedOption(M, g)
        local st = M.crew(g.key)
        if g.mount and st == g.mount and not M.crew_place(g.key) then return g.start end
        return st
    end
    local function levelOf(game, g)
        local b, level = X.boost[g], 0
        if not b then return 0, nil end
        for i, k in ipairs(b.keys) do if game.has_building(k) then level = i end end
        return level, level > 0 and b.steps[level] or nil
    end
    local function cargoOf(game)
        local m = 1
        for k, v in pairs(X.ammo_mod) do if v > m and game.has_building(k) then m = v end end
        return m
    end

    -- the numbers the panel shows for every option of a place (src/tww3_mtb_crew_model.lua crew_sources, crew_bonuses, crew_ammo: the page's own) against
    -- those the battle applies (the option's ammo x the cargo, src/tww3_mtb_ammo.lua; accuracy and range of the boost's step at its level; reload
    -- and damage: nothing yet). A difference made only of the known gaps (X.unapplied: the tree's effects the port skips, the mod's own sources the
    -- battle has not) is counted as a gap; any other is a problem.
    local KINDS = {'ammo', 'accuracy', 'range', 'reload', 'damage'}
    local function gap(line)
        if not gaps[line] then gaps[line] = 0; push(gapOrder, line) end
        gaps[line] = gaps[line] + 1
    end
    local function numbers(w, out)
        local config, game = w.config, w.game
        local sources = CM.crew_sources(config, function(k) return game.has_building(k) end, function(k) return game.standing(k) end)
        local cargo = cargoOf(game)
        for _, g in ipairs(config.groups) do
            if X.owned[g.key] then
                local bonus = CM.crew_bonuses(sources, g.key)
                local level, step = levelOf(game, g.key)
                local applied = {ammo = round((cargo - 1) * 100), reload = 0, damage = 0,
                                 accuracy = step and step.calibration_area and round((1 - step.calibration_area) * 100) or 0,
                                 range = step and step.effective_range and round((step.effective_range - 1) * 100) or 0}
                for _, kind in ipairs(KINDS) do
                    local b = bonus[kind]
                    local unapplied, names = 0, {}
                    for _, f in ipairs(b.from) do
                        local known
                        if f.mod then known = not X.battle_mod[f.name .. '|' .. kind .. '|' .. g.key]
                        else known = X.unapplied[f.name .. '|' .. kind .. '|' .. g.key] or X.unapplied[f.name .. '|' .. kind .. '|all'] end
                        if known then unapplied = unapplied + f.value; push(names, (f.mod and '*' or '') .. f.name .. ' ' .. f.value) end
                    end
                    if b.pct ~= applied[kind] then
                        if b.pct - unapplied == applied[kind] then
                            gap(kind .. ' ' .. g.key .. ': the panel ' .. b.pct .. ', the battle ' .. applied[kind] .. ' (not applied: ' .. table.concat(names, ', ') .. ')')
                        else
                            push(out, 'numbers ' .. kind .. ' ' .. g.key .. ': the panel ' .. b.pct .. ' (' .. #b.from .. ' sources), the battle ' .. applied[kind] ..
                                 ', the known gaps ' .. unapplied .. ': not explained')
                        end
                    end
                end
                -- the ammunition as a number (the group's whole): the panel's total against the battle's, both rounded as their code rounds
                for _, o in ipairs(g.options) do
                    if o.ammo ~= nil and o.seats ~= nil then
                        local shown = CM.crew_ammo({ammo = o.ammo, seats = o.seats}, bonus.ammo.pct, o.men or 0).total
                        local battle = floor(o.ammo * cargo + 0.5)
                        if battle < 1 then battle = 1 end
                        if shown ~= battle and bonus.ammo.pct == applied.ammo then
                            push(out, 'ammo ' .. g.key .. ' ' .. o.key .. ': the panel ' .. shown .. ', the battle ' .. battle .. ' with the same percent')
                        end
                    end
                end
            end
        end
    end

    -- expected: {treasury, crew = {group = option}, order = {group = option | false}} of the page's vectors after this step
    local check
    function R.check(w, expected)
        W = w
        local out = check(w, expected)
        if #out > 0 and w.script_stood then
            -- the battle's start writes them (PendingBattle): then they must agree
            fire('PendingBattle', {})
            R.tick(w)
            out = check(w, expected)
            if #out == 0 then R.info['a level stood by a script: the seats written at the next battle start (PendingBattle)'] = (R.info['a level stood by a script: the seats written at the next battle start (PendingBattle)'] or 0) + 1 end
        end
        w.script_stood = false
        return out
    end
    check = function(w, expected)
        local out = {}
        local M, game, C = w.M, w.game, w.C
        local config = w.config
        -- the gold: the model's alone (the vectors' treasury), nothing taken or given by the old mechanics
        if expected.treasury ~= nil and game.treasury() ~= expected.treasury then
            push(out, 'treasury ' .. game.treasury() .. ', the page ' .. expected.treasury)
        end
        if #w.moves > 0 then push(out, 'the old mechanics moved the treasury: ' .. table.concat(w.moves, ', ')); w.moves = {} end
        for g, v in pairs(expected.crew or {}) do
            if M.crew(g) ~= v then push(out, 'crew ' .. g .. ' ' .. tostring(M.crew(g)) .. ', the page ' .. tostring(v)) end
        end
        for g, v in pairs(expected.order or {}) do
            local got = M.crew_order(g)
            if (got or false) ~= v then push(out, 'order ' .. g .. ' ' .. tostring(got) .. ', the page ' .. tostring(v)) end
        end
        -- what the seats were last written for, against the model now
        local last = w.last
        if not last then push(out, 'the seats were never written'); return out end
        local CONF = C.config()
        X.malakai = X.malakai or CONF.malakai
        for _, g in ipairs(config.groups) do
            if X.owned[g.key] then
                local want = expectedOption(M, g)
                if last.choice[g.key] ~= want then
                    push(out, 'seats ' .. g.key .. ': the model ' .. tostring(M.crew(g.key)) .. ' (place ' .. tostring(M.crew_place(g.key)) .. ') -> ' ..
                         tostring(want) .. ', written ' .. tostring(last.choice[g.key]))
                else
                    local level = levelOf(game, g.key)
                    local spec = CONF.groups[g.key]
                    for _, seat in ipairs(spec.seats or {}) do
                        local row = (level > 0 and CONF.seats[seat][want .. '@' .. level]) or CONF.seats[seat][want]
                        local mk = last.malakai
                        if mk and seat == mk.seat then row = X.malakai.rows[mk.side] end
                        if last.plan[seat] ~= row then
                            push(out, 'seat ' .. seat .. ': ' .. tostring(last.plan[seat]) .. ', expected ' .. tostring(row) .. ' (' .. want .. ' level ' .. level .. ')')
                            break
                        end
                    end
                end
            end
        end
        -- Malakai at the rail of the model's side, a crew dwarf at the helm
        local side = M.malakai_side()
        local seat = X.malakai.seats[side]
        if last.plan[seat] ~= X.malakai.rows[side] or last.plan[X.malakai.helm_seat] ~= X.malakai.helm_crew then
            push(out, 'Malakai: side ' .. side .. ', ' .. seat .. ' ' .. tostring(last.plan[seat]) .. ', helm ' .. tostring(last.plan[X.malakai.helm_seat]))
        end
        X.harpoon_bundle = X.harpoon_bundle or (CONF.groups.harpoon or {}).off_bundle
        -- the cargo the battle reads
        local cargo = cargoOf(game)
        if last.cargo ~= cargo or w.svr.mtb_crew_ammo_mod ~= tostring(cargo) then
            push(out, 'cargo: written ' .. tostring(last.cargo) .. ' / ' .. tostring(w.svr.mtb_crew_ammo_mod) .. ', standing ' .. cargo)
        end
        -- the harpoon's bundle: on the force while the harpoon's place is empty
        local h = groupsOf(config).harpoon
        if h then
            local off = expectedOption(M, h) == h.start
            if (w.bundles[X.harpoon_bundle] == true) ~= off then
                push(out, 'harpoon: model ' .. tostring(M.crew('harpoon')) .. ', the bundle that takes it away ' .. tostring(w.bundles[X.harpoon_bundle]))
            end
        end
        numbers(w, out)
        return out
    end

    function R.gaps()
        local out = {}
        for _, line in ipairs(gapOrder) do push(out, {line = line, count = gaps[line]}) end
        return out
    end
    function R.writes(w) return #w.applies end
    function R.logs(w) return w.log end
    return R
end
