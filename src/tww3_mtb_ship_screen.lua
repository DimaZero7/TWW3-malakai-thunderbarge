-- The airship screen in the campaign: the logic (src/tww3_mtb_ship.lua) over the game (src/tww3_mtb_game.lua) for the whole session, and the
-- panel (src/tww3_mtb_ship_ui.lua over src/tww3_mtb_ship_uic.lua) while it is open. docs/design/port-to-game.md, 3 and 5 (stages 2, 3).
--
-- INERT: packed in script/campaign/tww3_mtb/, which the game does not run by itself. src/tww3_mtb_crew_ui.lua loads it only when its switch
-- NEW_SHIP_PANEL is on (off by default): then the HUD's button opens this panel instead of the old crew panel.
--
--   local S = <this file>; S.start(load)    load(name) -> the module script/campaign/tww3_mtb/<name>.lua (src/tww3_mtb_crew_ui.lua ship_module)
--   S.open(), S.close(), S.is_open(), S.toggle()      S.open() -> false, why while the game's own moment is up (S.blocked)
--   S.blocked()                             why the panel cannot be opened now (the model's words for the game's blocker), nil when it can
--   S.button_state()                        {inactive, mark, why} for the HUD's button (src/tww3_mtb_crew_ui.lua)
--   S.destroy()                             the panel's components gone (the next open builds them again)
--   S.describe()                            the panel as text for the tests: tab, components made, the foot line
--
-- The panel is built once and kept: closing hides it, opening shows it again and refreshes it (the first session: building it took 3 s each time,
-- runs/20261114-230723-ship_panel). It is built anew only when the game's root changed its size (another resolution or UI scale).

local S = {}
local LAYOUTS = 'ui/tww3_mtb/'
local ROOT = 'mtb_ship_screen'
local ESCAPE = 'mtb_ship_escape'
local LISTENERS = {'tww3_mtb_ship_click', 'tww3_mtb_ship_hover', 'tww3_mtb_ship_turn_end', 'tww3_mtb_ship_panel', 'tww3_mtb_ship_advice',
                   'tww3_mtb_ship_battle', 'tww3_mtb_ship_dilemma', 'tww3_mtb_ship_incident'}
local WATCH = 'mtb_ship_screen_watch'           -- the timer that looks for the game's own moments while the panel is open
local WATCH_MS = 250
local READ = 'mtb_ship_screen_report_read'      -- the timer after which the turn's report counts as seen
local READ_MS = 1000
local function button()
    local ok, b = pcall(function() return _G.tww3_mtb_crew_ui end)
    if ok and b and b.refresh_button then pcall(b.refresh_button) end
end

local function log(text) pcall(function() _G.tww3_mtb_campaign.file_log('[ship screen] ' .. tostring(text)) end) end
local function guarded(fn) return function(...) local ok, e = pcall(fn, ...); if not ok then log('error: ' .. tostring(e)) end end end

local mods = nil
local NAMES = {Ship = 'tww3_mtb_ship', CM = 'tww3_mtb_crew_model', config = 'tww3_mtb_ship_config', cfg = 'tww3_mtb_ship_ui_config',
               UI = 'tww3_mtb_ship_ui', Uic = 'tww3_mtb_ship_uic', Game = 'tww3_mtb_game'}
-- the logic for the whole session: the turn's news and the foot line are kept while the panel is closed. The modules are this screen's only after
-- everything started: a failed start leaves nothing behind, and the next call tries again.
function S.start(load)
    if mods then return true end
    local m = {}
    for k, name in pairs(NAMES) do
        m[k] = load(name)
        if m[k] == nil then log('module missing: ' .. name); return false end
    end
    local ok, err = pcall(function()
        local game = m.Game.new(m.config)
        local M = m.Ship.make(m.config, game, m.CM)
        local keep = m.Game.load(m.Ship, M) or {}
        S.game, S.M, S.keep = game, M, keep
    end)
    if not ok then
        S.game, S.M, S.keep = nil, nil, nil
        log('start failed: ' .. tostring(err))
        return false
    end
    mods = m
    S.M.on_change(guarded(function()
        if S.panel and S.shown then S.panel.refresh(); S.read_later() end
        S.save()
        button()        -- the HUD's mark of the turn's report
    end))
    log('started')
    return true
end

-- the modules this screen runs on (for the tests: tools/tests/ship_session.lua sets ENGINE / ASSUMED options on them before the first open)
function S.modules() return mods end

function S.save()
    if not mods then return end
    local view = S.panel and S.panel.view
    if view then S.keep = {tab = view.tab, scroll = view.pan and view.pan.state() or nil} end
    mods.Game.save(mods.Ship, S.M, S.keep)
end

function S.is_open() return S.shown == true end

-- why the panel cannot be opened now: the game's own moment (src/tww3_mtb_game.lua blocker) in the model's words; nil when it can
function S.blocked()
    if not mods then return nil end
    local ok, r = pcall(function() return S.M.can_open() end)
    if ok and r and not r.ok then return r.why end
    return nil
end
-- the HUD's button: inactive (the game's look of a stock button that cannot be used now) with the reason, or the game's mark when the turn's
-- report waits unread or the ship has something new the player has not looked at
function S.button_state()
    local why = S.blocked()
    local mark = false
    if mods and not S.shown then pcall(function() mark = S.M.report() ~= nil or S.M.ship_unseen() end) end
    return {inactive = why ~= nil, why = why, mark = mark and not why}
end
-- the turn's report counts as seen a moment after the panel shows it (src/tww3_mtb_ship.lua M.report): a click in the same moment does not
-- take its place; a click after it does
function S.read_later()
    if not (S.shown and S.M.report()) then return end
    pcall(function() core:get_tm():remove_real_callback(READ) end)
    core:get_tm():real_callback(guarded(function()
        if S.shown and S.M.report() then S.M.report_read(); S.save(); log('the turn\'s report seen') end
    end), READ_MS, READ)
end

-- the panel's real-time timers (the glows): kept with the panel, running only while it is shown
local timers = {}
local function host()
    return {
        every = function(ms, fn, name)
            local t = {ms = ms, fn = guarded(fn), name = name}
            timers[#timers + 1] = t
            core:get_tm():repeat_real_callback(t.fn, ms, name)
        end,
        after = function(ms, fn, name) core:get_tm():real_callback(guarded(fn), ms, name) end,
        clear_tooltip = function() end,
    }
end
local function timers_on(on)
    local tm = core:get_tm()
    for _, t in ipairs(timers) do
        if on then tm:repeat_real_callback(t.fn, t.ms, t.name) else pcall(function() tm:remove_real_callback(t.name) end) end
    end
end

-- The game's events on our components, as the listeners of S.open run them (exported for the tests, tools/tests/ship_session.lua: a click
-- there is this same function)
function S.click(id)
    if not (S.ui and S.shown) then return end
    if id == 'mtb_ship_close' then S.close(); return end
    local c = S.ui.by_id(id)
    if c then S.panel.click(c, S.ui.ENGINE.mouse_along()) end
end
function S.hover(id) if S.ui and S.shown then S.ui.mouse_on(id) end end

-- the error of a failed build with its stack, when the game's Lua has debug.traceback (the census: it has)
local function traced(e)
    local ok, t = pcall(function() return debug.traceback(tostring(e), 2) end)
    return ok and t or tostring(e)
end

local function root_size()
    local ok, w, h = pcall(function() local r = core:get_ui_root(); return r:Width(), r:Height() end)
    if ok then return w, h end
    return nil, nil
end

local function build()
    S.failed_ui = nil
    timers = {}
    local ok, err = xpcall(function()
        S.ui = mods.Uic.new(LAYOUTS, mods.cfg.text)
        S.root = S.ui.root(ROOT)
        S.panel = mods.UI.make_panel{root = S.root, M = S.M, cfg = mods.cfg, CM = mods.CM, Ship = mods.Ship, flags = {}, keep = {tab = S.keep.tab, pan = S.keep.scroll}, host = host(), ui = S.ui,
                                       profile = mods.Uic.ENGINE.profile}
        -- the cross closes (the page is the whole page and has none to close): it takes the click in the game
        S.panel.view.close:SetInteractive(true)
        -- the dim over the map (the page's CSS .backdrop: 150 of 255, as the old panel sets it [игра])
        S.panel.view.root:SetOpacity(150)
        S.panel.view.onTab = function() S.save() end
        S.panel.view.onSeen = function() S.save() end
    end, traced)
    if not ok then
        log('build failed: ' .. tostring(err))
        S.failed_ui = S.ui      -- the components made before the failure, for the tests' diagnosis
        S.destroy()
        return false, err
    end
    log('built: ' .. tostring(S.ui.count) .. ' components')
    return true
end

function S.open()
    if S.shown then return true end
    if not mods then return false, 'not started' end
    -- as the game's own full-screen panels: not over a dilemma, an event, a battle, another faction's turn, the game's modal panel or window
    local why = S.blocked()
    if why then log('not opened: ' .. why); button(); return false, why end
    local t0 = os.clock()
    if S.panel then
        local w, h = root_size()
        local size = S.ui.root_size
        if w and size and (w ~= size[1] or h ~= size[2]) then log('the game root is now ' .. w .. ' x ' .. h .. ': the panel built anew'); S.destroy() end
    end
    S.reused = S.panel ~= nil
    if not S.panel then
        local ok, err = build()
        if not ok then S.build_seconds = os.clock() - t0; return false, err end
    end
    local ok, err = xpcall(function()
        S.root:SetVisible(true)
        S.panel.refresh()
    end, traced)
    if not ok then
        log('show failed: ' .. tostring(err))
        S.destroy()
        S.build_seconds = os.clock() - t0
        return false, err
    end
    S.shown = true
    if S.reused then timers_on(true) end
    S.ui.topmost(true)          -- the windows over the panel (src/tww3_mtb_ship_uic.lua): taken off when it closed
    S.build_seconds = os.clock() - t0
    log((S.reused and 'shown again' or 'opened') .. ': ' .. tostring(S.ui.count) .. ' components, ' .. tostring(math.floor(S.build_seconds * 1000 + 0.5) / 1000) .. ' s')
    core:add_listener('tww3_mtb_ship_click', 'ComponentLClickUp', function(context) return S.ui and S.ui.by_id(context.string) ~= nil end, guarded(function(context)
        S.click(context.string)
    end), true)
    core:add_listener('tww3_mtb_ship_hover', 'ComponentMouseOn', function() return S.ui ~= nil end, guarded(function(context) S.hover(context.string) end), true)
    core:add_listener('tww3_mtb_ship_turn_end', 'FactionTurnEnd', function(context) return context:faction():name() == 'wh3_dlc25_dwf_malakai' end, guarded(S.close), true)
    core:add_listener('tww3_mtb_ship_panel', 'PanelOpenedCampaign', function() return S.shown == true end, guarded(S.close), true)
    -- the game's own moments close it as they close the game's full-screen panels: a battle, a dilemma, an incident (their panels may come a
    -- moment later or not at all); the rest, and any of them that came without an event, the watch below finds
    core:add_listener('tww3_mtb_ship_battle', 'PendingBattle', function() return S.shown == true end, guarded(S.close), true)
    core:add_listener('tww3_mtb_ship_dilemma', 'DilemmaIssuedEvent', function() return S.shown == true end, guarded(S.close), true)
    core:add_listener('tww3_mtb_ship_incident', 'IncidentOccuredEvent', function() return S.shown == true end, guarded(S.close), true)
    -- the watch: the game's moment up -> closed; the game's window (the cancel's «Отменить строительство», which the panel waits for) leaves it
    -- open, but nothing of ours over it: the windows over the panel hidden and taken off the top while the window is up
    core:get_tm():repeat_real_callback(guarded(function()
        if not S.shown then return end
        local kind = S.game.blocker()
        if kind and kind ~= 'dialog' then log('closed by the game: ' .. kind); S.close(); return end
        local dialog = kind == 'dialog'
        if dialog and S.ui.topmost_on() then S.ui.mouse_on(nil) end
        S.ui.topmost(not dialog)
    end), WATCH_MS, WATCH)
    S.read_later()
    button()
    -- the game's advisor out of the way while the panel is open (src/tww3_mtb_ship_uic.lua ENGINE.hide_advisor), again when it gives new advice
    local E = S.ui.ENGINE
    S.advisor = {restore = E.hide_advisor(), came = false}
    S.hud = E.hide_hud and E.hide_hud() or nil
    core:add_listener('tww3_mtb_ship_advice', 'AdviceIssued', function() return S.shown == true end, guarded(function()
        S.advisor.came = true
        E.hide_advisor()
    end), true)
    local function onEscape()
        if not S.shown then return end
        if S.panel.escape() then cm:steal_escape_key_with_callback(ESCAPE, onEscape) else S.close() end
    end
    S.on_escape = onEscape      -- the key's callback, for the tests (no key can be pressed for them)
    cm:steal_escape_key_with_callback(ESCAPE, onEscape)
    return true
end

local function quiet()
    for _, n in ipairs(LISTENERS) do core:remove_listener(n) end
    pcall(function() core:get_tm():remove_real_callback(WATCH) end)
    pcall(function() core:get_tm():remove_real_callback(READ) end)
    pcall(function() cm:release_escape_key_with_callback(ESCAPE) end)
    timers_on(false)
    if S.advisor then local a = S.advisor; S.advisor = nil; a.restore(a.came) end
    if S.hud then local h = S.hud; S.hud = nil; h() end
end

-- closed: hidden and kept, its hover windows and choices gone
function S.close()
    if not S.shown then return end
    S.save()
    S.shown = false
    quiet()
    pcall(function()
        S.ui.mouse_on(nil)
        S.panel.reset()
        S.ui.topmost(false)         -- nothing of ours stays over the game (top-most draws over a hidden root's siblings: not proven otherwise)
        S.root:SetVisible(false)
    end)
    log('closed')
    button()
end

-- the components gone: not in the click's own call (the clicked component belongs to them), in the game's next callback
function S.destroy()
    if S.shown then S.save(); S.shown = false; quiet() end
    local root = S.root
    S.panel, S.ui, S.root = nil, nil, nil
    timers = {}
    if root then
        pcall(function() root.uic:SetVisible(false) end)
        core:get_tm():real_callback(function() pcall(function() root.uic:Destroy() end) end, 1, 'mtb_ship_screen_destroy')
    end
end

function S.toggle() if S.shown then S.close(); return true end return S.open() end

function S.describe()
    local v = S.shown and S.panel and S.panel.view
    return {open = tostring(v and true or false), tab = v and v.tab or '', components = S.ui and S.ui.count or 0, message = v and v.message:GetStateText() or ''}
end

return S
