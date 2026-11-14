-- The airship screen in the campaign: the logic (src/tww3_mtb_ship.lua) over the game (src/tww3_mtb_game.lua) for the whole session, and the
-- panel (src/tww3_mtb_ship_ui.lua over src/tww3_mtb_ship_uic.lua) while it is open. docs/design/port-to-game.md, 3 and 5 (stages 2, 3).
--
-- INERT: packed in script/campaign/tww3_mtb/, which the game does not run by itself. src/tww3_mtb_crew_ui.lua loads it only when its switch
-- NEW_SHIP_PANEL is on (off by default): then the HUD's button opens this panel instead of the old crew panel.
--
--   local S = <this file>; S.start(load)    load(name) -> the module script/campaign/tww3_mtb/<name>.lua (src/tww3_mtb_crew_ui.lua ship_module)
--   S.open(), S.close(), S.is_open(), S.toggle()
--   S.describe()                            the panel as text for the tests: tab, components made, the foot line

local S = {}
local LAYOUTS = 'ui/tww3_mtb/'
local ROOT = 'mtb_ship_screen'
local ESCAPE = 'mtb_ship_escape'
local TIMERS = {}

local function log(text) pcall(function() _G.tww3_mtb_campaign.file_log('[ship screen] ' .. tostring(text)) end) end
local function guarded(fn) return function(...) local ok, e = pcall(fn, ...); if not ok then log('error: ' .. tostring(e)) end end end

local mods = nil
-- the logic for the whole session: the turn's news and the foot line are kept while the panel is closed
function S.start(load)
    if mods then return true end
    mods = {Ship = load('tww3_mtb_ship'), CM = load('tww3_mtb_crew_model'), config = load('tww3_mtb_ship_config'), cfg = load('tww3_mtb_ship_ui_config'),
            UI = load('tww3_mtb_ship_ui'), Uic = load('tww3_mtb_ship_uic'), Game = load('tww3_mtb_game')}
    for k, v in pairs(mods) do if v == nil then log('module missing: ' .. k); mods = nil; return false end end
    S.game = mods.Game.new(mods.config)
    S.M = mods.Ship.make(mods.config, S.game, mods.CM)
    S.keep = mods.Game.load(mods.Ship, S.M) or {}
    S.M.on_change(guarded(function()
        if S.panel then S.panel.refresh() end
        S.save()
    end))
    log('started')
    return true
end

function S.save()
    if not mods then return end
    local view = S.panel and S.panel.view
    if view then S.keep = {tab = view.tab, scroll = view.pan and view.pan.state() or nil} end
    mods.Game.save(mods.Ship, S.M, S.keep)
end

function S.is_open() return S.panel ~= nil end

local function host()
    local tm = core:get_tm()
    return {
        every = function(ms, fn, name) TIMERS[#TIMERS + 1] = name; tm:repeat_real_callback(guarded(fn), ms, name) end,
        after = function(ms, fn, name) tm:real_callback(guarded(fn), ms, name) end,
        clear_tooltip = function() end,
    }
end

function S.open()
    if S.panel then return true end
    if not mods then return false, 'not started' end
    local ok, err = pcall(function()
        S.ui = mods.Uic.new(LAYOUTS, mods.cfg.text)
        S.root = S.ui.root(ROOT)
        S.panel = mods.UI.make_panel{root = S.root, M = S.M, cfg = mods.cfg, CM = mods.CM, Ship = mods.Ship, flags = {}, keep = {tab = S.keep.tab, pan = S.keep.scroll}, host = host()}
        -- the cross closes (the page is the whole page and has none to close): it takes the click in the game
        S.panel.view.close:SetInteractive(true)
        -- the dim over the map (the page's CSS .backdrop: 150 of 255, as the old panel sets it [игра])
        S.panel.view.root:SetOpacity(150)
        S.panel.view.onTab = function() S.save() end
        S.panel.view.onSeen = function() S.save() end
        S.panel.refresh()
    end)
    if not ok then
        log('build failed: ' .. tostring(err))
        S.close()
        return false, err
    end
    log('opened: ' .. tostring(S.ui.count) .. ' components')
    core:add_listener('tww3_mtb_ship_click', 'ComponentLClickUp', function(context) return S.ui and S.ui.by_id(context.string) ~= nil end, guarded(function(context)
        local id = context.string
        if id == 'mtb_ship_close' then S.close(); return end
        local c = S.ui.by_id(id)
        if c then S.panel.click(c, S.ui.ENGINE.mouse_along()) end
    end), true)
    core:add_listener('tww3_mtb_ship_hover', 'ComponentMouseOn', function() return S.ui ~= nil end, guarded(function(context) S.ui.mouse_on(context.string) end), true)
    core:add_listener('tww3_mtb_ship_turn_end', 'FactionTurnEnd', function(context) return context:faction():name() == 'wh3_dlc25_dwf_malakai' end, guarded(S.close), true)
    core:add_listener('tww3_mtb_ship_panel', 'PanelOpenedCampaign', function() return S.panel ~= nil end, guarded(S.close), true)
    local function onEscape()
        if not S.panel then return end
        if S.panel.escape() then cm:steal_escape_key_with_callback(ESCAPE, onEscape) else S.close() end
    end
    cm:steal_escape_key_with_callback(ESCAPE, onEscape)
    return true
end

function S.close()
    local root = S.root
    S.save()
    S.panel, S.ui, S.root = nil, nil, nil
    for _, n in ipairs({'tww3_mtb_ship_click', 'tww3_mtb_ship_hover', 'tww3_mtb_ship_turn_end', 'tww3_mtb_ship_panel'}) do core:remove_listener(n) end
    pcall(function() cm:release_escape_key_with_callback(ESCAPE) end)
    for _, name in ipairs(TIMERS) do pcall(function() core:get_tm():remove_real_callback(name) end) end
    TIMERS = {}
    if root then
        pcall(function() root.uic:SetVisible(false) end)
        -- not in the click's own call: the clicked component belongs to it
        core:get_tm():real_callback(function() pcall(function() root.uic:Destroy() end) end, 1, 'mtb_ship_screen_destroy')
    end
    log('closed')
end

function S.toggle() if S.panel then S.close(); return true end return S.open() end

function S.describe()
    local v = S.panel and S.panel.view
    return {open = tostring(v ~= nil), tab = v and v.tab or '', components = S.ui and S.ui.count or 0, message = v and v.message:GetStateText() or ''}
end

return S
