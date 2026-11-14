-- The session «ship_panel»: the mod's new airship panel opened in the real game for the first time (docs/design/port-to-game.md, 5, stages 2
-- and 3). Helpers only: tools/tests/ship_session.py sends tools/tests/port_probe.lua (its encoder PP.J, its protected call PP.protect with the
-- stack, its campaign reads) and then this file before every call, and calls _G.mtb_ss.run(item, args): one JSON line back.
--
-- The panel is the mod's own: src/tww3_mtb_ship_screen.lua as tww3_mtb_crew_ui.ship_screen() gives it (the session's pack has the switch on).
-- A click here is S.click(id), the very function the panel's ComponentLClickUp listener runs; a hover is S.hover(id); Esc is S.on_escape, the
-- callback the panel gave cm:steal_escape_key_with_callback. No global mouse or key. Only our own components are read: the wrapper's
-- references (src/tww3_mtb_ship_uic.lua env.dump), never a walk of the game's UI. The game's own string.find is never called (string.find_lua).
-- Nothing here is risky for the game's bindings except the items named so in ship_session.py (RISKY), which run last.

local PP = _G.mtb_pp
if not PP then error('tools/tests/port_probe.lua must be sent before this file') end
local SS = {}
_G.mtb_ss = SS
local T = _G.mtb_ss_state or {}      -- survives the next send (not a battle: there is none in this session)
_G.mtb_ss_state = T
local J, protect = PP.J, PP.protect
local sfind = string.find_lua or string.find
local ssub = string.sub_lua or string.sub
local FOLDER = 'script/campaign/tww3_mtb/'
local MODULES = {'tww3_mtb_ship', 'tww3_mtb_crew_model', 'tww3_mtb_ship_config', 'tww3_mtb_ship_ui_config', 'tww3_mtb_ship_ui', 'tww3_mtb_ship_uic',
  'tww3_mtb_game', 'tww3_mtb_ship_screen'}
local FACTION = 'wh3_dlc25_dwf_malakai'
local ROOT_ID = 'mtb_ship_screen'
local DIAG_ID = 'tww3_mtb_ss_diag'
local ENV = getfenv(1)       -- the mod environment the remote runs us in (core, cm, common: census, getfenv(0) ~= _G)

local function crew_ui() return _G.tww3_mtb_crew_ui or ENV.tww3_mtb_crew_ui end
local function crew() return _G.tww3_mtb_crew or ENV.tww3_mtb_crew end
local function flat(s) s = tostring(s); s = string.gsub(s, '[\r\n]+', ' | '); s = string.gsub(s, '\t', ' '); return ssub(s, 1, 1500) end
local function clock() local ok, c = pcall(os.clock); return ok and c or 0 end

-- ---------------------------------------------------------------- loading ----------------------------------------------------------------
-- A module as the switch's own loader would get it (src/tww3_mtb_crew_ui.lua ship_module: require, then loadfile) and whether the functions it
-- defines see the game's API (a chunk run with _G as its environment does not: the census shows core, common, UIComponent nil in _G).
local function env_sees(mod)
  if type(mod) ~= 'table' then return nil end
  for _, v in pairs(mod) do
    if type(v) == 'function' then
      local ok, e = pcall(getfenv, v)
      if ok and type(e) == 'table' then
        return {same_as_ours = e == ENV, core = e.core ~= nil, common = e.common ~= nil, UIComponent = e.UIComponent ~= nil, cm = e.cm ~= nil}
      end
    end
  end
  return {no_function = true}
end

-- our own loader: the source handed in by the driver (inline, the last way), else loadfile with our environment
local function load_fresh(name)
  local src = T.inline and T.inline[name]
  local f, err
  if src then f, err = loadstring(src, '@' .. name .. '.lua') else f, err = loadfile(FOLDER .. name .. '.lua') end
  if not f then error('cannot load ' .. name .. ': ' .. tostring(err), 0) end
  setfenv(f, ENV)
  local m = f()
  if type(m) ~= 'table' then error(name .. ' returned a ' .. type(m), 0) end
  return m
end

-- the pure modules the session uses itself (Ship's save and load, the config): what the game already loaded, else our loader
local function mod(name)
  T.mods = T.mods or {}
  if T.mods[name] then return T.mods[name] end
  local m
  local ok, loaded = pcall(function() return package.loaded[FOLDER .. name] end)
  if ok and type(loaded) == 'table' then m = loaded else m = load_fresh(name) end
  T.mods[name] = m
  return m
end
SS.mod = mod

local function screen() return T.scr end
local function view() return T.scr and T.scr.panel and T.scr.panel.view end

-- ---------------------------------------------------------------- reading the panel ----------------------------------------------------------------
local function game_slots()
  local ok, s = pcall(PP.slots)
  return ok and s or {err = flat(s)}
end

local function treasuries()
  local out = {}
  local ok, g = pcall(function() return cm:get_faction(FACTION):treasury() end)
  out.game = ok and g or flat(g)
  local s = screen()
  if s and s.game then local ok2, a = pcall(s.game.treasury); out.adapter = ok2 and a or flat(a) end
  return out
end

-- one level as the module, the adapter and the game's own model see it
local function level_state(key)
  local s = screen()
  local out = {key = key}
  if not (s and s.M) then return out end
  local M = s.M
  local ok, st = pcall(M.status, key)
  out.status = ok and st or {err = flat(st)}
  out.under_construction = s.game.under_construction(key)
  out.standing = s.game.standing(key)
  out.has_building = s.game.has_building(key)
  out.reason = M.reason(key)
  -- the game's model: the horde's slots by the model interface, and the slot's construction by the context (port_probe.lua slot_read)
  local slots = game_slots()
  out.model_slot = nil
  if type(slots) == 'table' then for i, k in ipairs(slots) do if k == key then out.model_slot = i - 1 end end end
  out.construction = {}
  for _, sl in ipairs(s.game.slots and s.game.slots() or {}) do
    local okr, r = pcall(PP.slot_read, sl.i)
    if okr and r and (r.item == true) then out.construction[#out.construction + 1] = {slot = sl.i, level = r.item_level or r.item_level2, turns = r.turns} end
  end
  return out
end

local function node_of(key)
  local v = view()
  for i, t in ipairs(v and v.tree or {}) do if t.node.key == key then return i - 1, t end end
end

local function panel_state(keys)
  local s, v = screen(), view()
  local out = {open = s and s.is_open() or false}
  if s and s.M then
    local M = s.M
    out.message = M.message()
    out.first_step = M.first_step()
    out.unseen = M.ship_unseen()
    local Ship = mod('tww3_mtb_ship')
    local news = M.ship_news()
    out.news = news and Ship.encode(news) or nil
    out.crew_upkeep = M.crew_upkeep()
    out.turn = s.game.turn()
  end
  if v then
    out.tab = v.tab
    out.options = v.options
    out.pan = v.pan and v.pan.state() or nil
    out.foot = v.message and v.message:GetStateText() or nil
    out.foot_tooltip = v.message and v.message.tooltip or nil
    out.gold_text = v.gold and v.gold:GetStateText() or nil
    out.mark = v.tabMark and v.tabMark.visible or nil
    out.raze = v.raze and v.raze.visible or nil
    out.fit_label = v.fitBtn and v.fitBtn.label:GetStateText() or nil
    out.count = s.ui and s.ui.count or nil
    out.hovered = s.ui and s.ui.hovered and s.ui.hovered.id or nil
  end
  out.treasury = treasuries()
  out.slots = game_slots()
  out.levels = {}
  for _, k in ipairs(keys or {}) do
    local n, t = node_of(k)
    local l = level_state(k)
    if t then l.node = n; l.check = t.check.visible; l.turns_banner = t.turnsBanner.visible; l.turns_text = t.turns:GetStateText(); l.cost_visible = t.cost.visible
      l.info_visible = t.info.tip.visible
    end
    out.levels[k] = l
  end
  return out
end
SS.panel_state = panel_state

-- ---------------------------------------------------------------- the items ----------------------------------------------------------------
local I = {}
SS.items = I

local function canary()
  local bad = ''
  local function check(label, fn)
    local ok, v = pcall(fn)
    if not ok or not v then bad = bad .. (bad == '' and '' or ', ') .. label .. (ok and '' or (': ' .. flat(v))) end
  end
  check('sub_lua', function() return ssub('abcdef', 2, 3) == 'bc' end)
  check('game string.sub', function() return string.sub('abcdef', 2, 3) == 'bc' end)
  check('root Id string', function() return type(core:get_ui_root():Id()) == 'string' end)
  check('root Width number', function() return type(core:get_ui_root():Width()) == 'number' end)
  check('turn_number number', function() return type(cm:turn_number()) == 'number' end)
  return bad
end
SS.canary = canary

function I.health()
  local c = canary()
  return {ui_root = c == '' or not sfind(c, 'root', 1, true), canary = c, open = screen() and screen().is_open() or false}
end
function I.clear()
  -- our diagnostic holder only; the panel is closed by its own path (item close)
  local old = find_uicomponent(core:get_ui_root(), DIAG_ID)
  if old then pcall(function() old:Destroy() end) end
  return {cleared = old and true or false}
end

-- The root as the game reports it
local function root_info()
  local ui = core:get_ui_root()
  local out = {w = ui:Width(), h = ui:Height()}
  local ok, sw, sh = pcall(function() return core:get_screen_resolution() end)
  if ok then out.screen = {sw, sh} end
  return out
end
function I.root() return root_info() end

-- smoke: each of this file's helpers once, each protected, the canary after each. Read only (no order, no panel). Text lines as the probe's.
function SS.smoke(a)
  a = a or {}
  local out, n, first_broken = '', 0, nil
  local function step(name, fn)
    n = n + 1
    local r = {protect(fn)}
    local c = canary()
    if c ~= '' and not first_broken then first_broken = n .. ' ' .. name end
    local shown = ''
    for i = 2, 6 do if r[i] ~= nil then shown = shown .. (shown == '' and '' or ', ') .. type(r[i]) .. ' ' .. ssub(tostring(r[i]), 1, 120) end end
    out = out .. 'S\t' .. n .. ' ' .. name .. '\t' .. (r[1] and ('ok ' .. (shown == '' and '(nothing)' or shown)) or ('ERR ' .. flat(r[2]))) .. '\t' ..
      (c == '' and 'canary ok' or ('canary BROKEN: ' .. c)) .. '\n'
    if r[1] then return r[2], r[3] end
  end
  step('canary before anything', function() local c = canary(); if c ~= '' then error(c) end; return true end)
  step('PP.J', function() return J({1, 'Дух', x = 2.5}) end)
  step('PP.protect traceback', function() local ok, e = protect(function() error('x') end); return ok, sfind(tostring(e), 'traceback', 1, true) ~= nil end)
  step('root_info()', function() local r = root_info(); return r.w, r.h, r.screen and r.screen[1], r.screen and r.screen[2] end)
  step('getfenv(1) is not _G', function() return ENV ~= _G, ENV.core ~= nil, ENV.common ~= nil end)
  local cu = step('tww3_mtb_crew_ui', function() return crew_ui() end)
  step('NEW_SHIP_PANEL (the session pack has it on)', function() return cu and cu.NEW_SHIP_PANEL end)
  step('ship_screen type', function() return cu and type(cu.ship_screen) end)
  step('tww3_mtb_campaign.file_log type', function() return type(_G.tww3_mtb_campaign and _G.tww3_mtb_campaign.file_log) end)
  step('tww3_mtb_crew, its pay_upkeep, its get', function() local c = crew(); return type(c), c and type(c.pay_upkeep), c and type(c.get) end)
  step('core:get_tm() and its callbacks', function() local tm = core:get_tm(); return type(tm), type(tm.real_callback), type(tm.repeat_real_callback), type(tm.remove_real_callback) end)
  step('cm.steal_escape_key_with_callback, release', function() return type(cm.steal_escape_key_with_callback), type(cm.release_escape_key_with_callback) end)
  step('cm.treasury_mod (rawget: an own field?)', function() return type(cm.treasury_mod), rawget(cm, 'treasury_mod') ~= nil end)
  step('cm:get_saved_value(mtb_ship_tab)', function() return cm:get_saved_value('mtb_ship_tab') end)
  step('cm:get_saved_value(mtb_crew_rifles) (the old mod and the new model share it)', function() return cm:get_saved_value('mtb_crew_rifles') end)
  step('require, loadfile, package.path', function() return type(require), type(loadfile), type(package) == 'table' and ssub(tostring(package.path), 1, 200) end)
  for _, name in ipairs(MODULES) do
    step('package.loaded ' .. name, function()
      local m = package.loaded[FOLDER .. name]
      local e = env_sees(m)
      return type(m), e and ((e.same_as_ours and 'env ours' or 'env other') .. ', core ' .. tostring(e.core) .. ', UIComponent ' .. tostring(e.UIComponent)) or nil
    end)
  end
  step('loadfile ship_screen (compiled, not run)', function()
    local f, err = loadfile(FOLDER .. 'tww3_mtb_ship_screen.lua')
    if not f then return 'nil', tostring(err) end
    local e = getfenv(f)
    return 'function', e == ENV and 'env ours' or (e == _G and 'env _G' or 'env other'), e.core ~= nil
  end)
  step('PP.malakai(), subtype', function() local m = PP.malakai(); return m and m:character_subtype_key() end)
  step('cm:get_faction(malakai) character_list has him with a force', function()
    local cl, found = cm:get_faction(FACTION):character_list(), nil
    for i = 0, cl:num_items() - 1 do local c = cl:item_at(i); if c:character_subtype_key() == 'wh3_dlc25_dwf_malakai_makaisson' and c:has_military_force() then found = true end end
    return found
  end)
  step('PP.slots() first, count', function() local s = PP.slots(); return s[1], #s end)
  step('PP.slot_read(1)', function() local r = PP.slot_read(1); return r.empty, r.item, r.turns end)
  step('treasuries()', function() local t = treasuries(); return t.game end)
  step('find_uicomponent(root, our absent id)', function() return find_uicomponent(core:get_ui_root(), DIAG_ID .. '_absent') end)
  local holder = step('our holder ui/tww3_mtb/layer_holder', function() return UIComponent(core:get_ui_root():CreateComponent(DIAG_ID, 'ui/tww3_mtb/layer_holder')) end)
  if holder then
    for _, l in ipairs({'image', 'text_head', 'backdrop'}) do
      local c = step('make ' .. l, function() return UIComponent(holder:CreateComponent('ss_smoke_' .. l, 'ui/tww3_mtb/' .. l)) end)
      if c and l == 'text_head' then
        step('text_head SetStateText, TextDimensions', function() c:SetStateText('Дух Грунгни'); return c:TextDimensions() end)
      end
    end
    step('holder:Destroy', function() holder:Destroy(); return true end)
  end
  out = out .. 'C\tfirst_broken\t' .. (first_broken or 'none') .. '\nC\tsteps\t' .. n .. '\n'
  return out
end

-- a. the modules and the panel. Step 1: the mod's own way (the switch). If that gives no started screen whose functions see the game's API:
-- our loader (loadfile + our environment); inline sources are the driver's last way (item load_inline).
function I.load(a)
  local out = {modules = {}}
  local cu = crew_ui()
  out.switch = cu and cu.NEW_SHIP_PANEL
  local t0 = clock()
  local ok, scr = protect(function() return cu.ship_screen() end)
  out.switch_seconds = clock() - t0
  out.switch_call = ok and type(scr) or ('ERR ' .. flat(scr))
  for _, name in ipairs(MODULES) do
    local m = package.loaded[FOLDER .. name]
    out.modules[name] = {required = type(m), env = env_sees(m)}
  end
  local good = ok and type(scr) == 'table' and scr.M ~= nil
  if good then
    local e = env_sees(scr)
    good = e and e.core and e.common and e.UIComponent
    out.screen_env = e
  end
  if good then
    T.scr, T.how = scr, 'switch'
  else
    for _, name in ipairs(MODULES) do
      local okf, f = pcall(loadfile, FOLDER .. name .. '.lua')
      out.modules[name].loadfile = okf and type(f) or ('ERR ' .. flat(f))
    end
    local t1 = clock()
    local ok2, fresh = protect(function() local s = load_fresh('tww3_mtb_ship_screen'); if not s.start(load_fresh) then error('start() said false (a module missing: the log says which)') end; return s end)
    out.fallback_seconds = clock() - t1
    out.fallback = ok2 and 'started' or ('ERR ' .. flat(fresh))
    if ok2 then T.scr, T.how = fresh, (T.inline and 'inline' or 'loadfile') end
  end
  out.how = T.how
  out.started = T.scr ~= nil and T.scr.M ~= nil
  return out
end

-- the driver's last way: every module's source (from the session's own pack) given here, then the same as item load's fallback
function I.load_inline(a)
  T.inline = a.sources
  T.mods = nil
  local ok, fresh = protect(function() local s = load_fresh('tww3_mtb_ship_screen'); if not s.start(load_fresh) then error('start() said false') end; return s end)
  if ok then T.scr, T.how = fresh, 'inline' end
  return {ok = ok, err = (not ok) and flat(fresh) or nil, how = T.how}
end

-- The probe's answers as configuration (tools/tests/ship_session.py OPTIONS): set on the screen's own modules before the first open. Each
-- option is one engine unknown of src/tww3_mtb_ship_uic.lua ENGINE or src/tww3_mtb_game.lua ASSUMED; an option not given keeps the module's own.
--   engine.clips, .wheel, .building_frame, .scale_by_layout    booleans, as the modules have them
--   engine.measure_text  'game' (the module's: TextDimensions, the characters when it gives 0) | 'chars' (never the game's measure)
--   engine.tint          'auto' (the module's: SetCurrentStateImageColour, else the alpha) | 'opacity' (the alpha only)
--   assumed.queue_completions   boolean
--   assumed.construction        'record_first' (the module's: BuildingLevelRecordContext.Key first) | 'level_first' (BuildingLevelContext.Key first)
--   assumed.after_dismantle_ms  the delay before the adapter reads the slot again after its Dismantle (the module's: 200)
function I.configure(a)
  local s = screen()
  local mods = s and s.modules and s.modules()
  if not mods then error('the screen gives no modules (src/tww3_mtb_ship_screen.lua S.modules)') end
  local E, A = mods.Uic.ENGINE, mods.Game.ASSUMED
  local set = {}
  local e, as = a.engine or {}, a.assumed or {}
  for _, k in ipairs({'clips', 'wheel', 'building_frame', 'scale_by_layout'}) do
    if e[k] ~= nil then E[k] = e[k] and true or false; set['engine.' .. k] = E[k] end
  end
  if e.measure_text == 'chars' then
    local own = T.own_measure or E.measure_text
    T.own_measure = own
    E.measure_text = function(_, text, size, w) return own({TextDimensions = function() return 0 end}, text, size, w) end
    set['engine.measure_text'] = 'chars'
  elseif e.measure_text == 'game' and T.own_measure then E.measure_text = T.own_measure; set['engine.measure_text'] = 'game' end
  if e.tint == 'opacity' then E.tint = function(uic, r, g, b, al) pcall(function() uic:SetCurrentStateImageOpacity(0, al) end) end; set['engine.tint'] = 'opacity' end
  if as.queue_completions ~= nil then A.queue_completions = as.queue_completions and true or false; set['assumed.queue_completions'] = A.queue_completions end
  if as.construction == 'level_first' then
    A.construction = function(cqi, n)
      local base = 'MilitaryForceContext.HordeContext.BuildingSlotList.At(' .. n .. ').ConstructionItemContext'
      local okv, valid = pcall(common.get_context_value, 'CcoCampaignCharacter', cqi, 'IsContextValid(' .. base .. ')')
      if not okv or not valid then return nil end
      local key
      for _, x in ipairs({'.BuildingLevelContext.Key', '.BuildingLevelRecordContext.Key'}) do
        local ok, v = pcall(common.get_context_value, 'CcoCampaignCharacter', cqi, base .. x)
        if ok and type(v) == 'string' and v ~= '' then key = v; break end
      end
      local okt, turns = pcall(common.get_context_value, 'CcoCampaignCharacter', cqi, base .. '.TurnsToCompletion')
      if not key then return nil end
      return {key = key, turns = (okt and tonumber(turns)) or 1}
    end
    set['assumed.construction'] = 'level_first'
  end
  if as.after_dismantle_ms then
    local ms = as.after_dismantle_ms
    A.after_dismantle = function(fn) core:get_tm():real_callback(fn, ms, 'mtb_ship_dismantled') end
    set['assumed.after_dismantle_ms'] = ms
  end
  return {set = set, engine_now = {clips = E.clips, wheel = E.wheel, building_frame = E.building_frame, scale_by_layout = E.scale_by_layout},
    assumed_now = {queue_completions = A.queue_completions}}
end

function I.open()
  local s = screen()
  if not s then error('no screen loaded') end
  local t0 = clock()
  local ok, err = s.open()
  local out = {ok = ok, err = err and flat(err) or nil, seconds = clock() - t0, build_seconds = s.build_seconds, root = root_info(), how = T.how}
  if ok then
    out.count = s.ui.count
    out.measured = s.ui.ENGINE.measured       -- the texts the layout measured by the game's TextDimensions / by the characters / empty
    out.state = panel_state()
  else
    local f = s.failed_ui
    out.failed_count = f and f.count
    out.last_made = f and f.last_made
  end
  return out
end

-- the cheap diagnostics of a failed open: every layout the pack has, made once under a holder of ours; each text layout with a Russian text and
-- its TextDimensions; an image with some paths the panel uses
function I.diag(a)
  local out = {layouts = {}, images = {}}
  local ui = core:get_ui_root()
  local old = find_uicomponent(ui, DIAG_ID)
  if old then pcall(function() old:Destroy() end) end
  local okh, holder = pcall(function() return UIComponent(ui:CreateComponent(DIAG_ID, 'ui/tww3_mtb/layer_holder')) end)
  if not okh then return {holder = flat(holder)} end
  for i, l in ipairs(a.layouts or {}) do
    local ok, c = pcall(function() return UIComponent(holder:CreateComponent('ss_diag_' .. i, 'ui/tww3_mtb/' .. l)) end)
    local row = {ok = ok, err = (not ok) and flat(c) or nil}
    if ok and ssub(l, 1, 5) == 'text_' then
      local okt, w, h, n = pcall(function() c:SetStateText('Дух Грунгни: 2 500'); return c:TextDimensions() end)
      row.text = okt and {w, h, n} or flat(w)
    end
    out.layouts[l] = row
  end
  local okc, img = pcall(function() return UIComponent(holder:CreateComponent('ss_diag_img', 'ui/tww3_mtb/image')) end)
  if okc then
    for _, p in ipairs(a.images or {}) do
      local ok, e = pcall(function() img:SetImagePath(p, 0); return img:GetImagePath() end)
      out.images[p] = ok and tostring(e) or ('ERR ' .. flat(e))
    end
  end
  pcall(function() holder:Destroy() end)
  return out
end

-- b. the live panel in the offline check's rows, kept here and fetched in pages
function I.dump_begin(a)
  local s = screen()
  if not (s and s.ui and s.root) then error('the panel is not open') end
  local t0 = clock()
  T.rows = s.ui.dump(s.root, a.live ~= false)
  return {rows = #T.rows, seconds = clock() - t0, root = root_info(), state = panel_state(a.keys)}
end
function I.dump_page(a)
  local out = {}
  for i = a.from, math.min(#(T.rows or {}), a.from + a.n - 1) do out[#out + 1] = T.rows[i] end
  return {rows = out, total = #(T.rows or {})}
end

-- the ids of our components by a prefix (the wrapper's own table: no walk), for the driver to pick a crew card, a scroll arrow
function I.ids(a)
  local out = {}
  local s = screen()
  for id in pairs(s and s.ui and s.ui.ids or {}) do
    if ssub(id, 1, #a.prefix) == a.prefix then out[#out + 1] = id end
  end
  table.sort(out)
  return {ids = out}
end

-- the tree's nodes: index (the component mtb_tree_node_<index>), key, name, cost, turns, state
function I.nodes()
  local s, v = screen(), view()
  local out = {}
  if not v then      -- the panel closed: the levels of the config, without their components
    for _, row in ipairs(mod('tww3_mtb_ship_config').levels) do
      local st = s.M.status(row.key)
      out[#out + 1] = {index = -1, key = row.key, name = row.name, cost = row.cost, turns = row.turns, state = st.state, poor = st.poor, chain = row.chain,
        hull = sfind(row.key, 'airship_hull_', 1, true) ~= nil, requires = row.requires}
    end
    return {nodes = out, closed = true}
  end
  for i, t in ipairs(v and v.tree or {}) do
    local row = s.M.level(t.node.key) or {}
    local st = s.M.status(t.node.key)
    out[#out + 1] = {index = i - 1, key = t.node.key, name = row.name, cost = row.cost, turns = row.turns, state = st.state, poor = st.poor, chain = row.chain,
      hull = sfind(t.node.key, 'airship_hull_', 1, true) ~= nil, requires = row.requires}
  end
  return {nodes = out}
end

-- the start of the game state for the driver's offline replay: what stands, the gold, the turn, the module's saved strings
function I.snapshot(a)
  local s = screen()
  local Ship = mod('tww3_mtb_ship')
  local v = view()
  local keep = {tab = v and v.tab, scroll = v and v.pan and v.pan.state() or nil}
  local built = {}
  for _, k in ipairs(game_slots()) do if k ~= '' then built[#built + 1] = k end end
  local queue = {}
  for _, sl in ipairs(s.game.slots()) do
    local okr, r = pcall(PP.slot_read, sl.i)
    if okr and r.item == true then queue[#queue + 1] = {key = r.item_level or r.item_level2, turns_left = r.turns, slot = sl.i} end
  end
  return {turn = s.game.turn(), gold = s.game.treasury(), built = built, queue = queue, saved = Ship.save_state(s.M, keep), keep = keep, root = root_info(),
    hovered = s.ui and s.ui.hovered and s.ui.hovered.id or nil}
end

-- d. a click / a hover, as the panel's listeners take them: way 'direct' = S.click(id) / S.hover(id) (the listener's own function);
-- way 'simulate' = the game's SimulateLClick / SimulateMouseOn on our component (the event then comes through the game: RISKY item)
function I.click(a)
  local s = screen()
  if not (s and s.ui) then error('the panel is not open') end
  local c = s.ui.by_id(a.id)
  if not c then return {missing = a.id, state = panel_state(a.keys)} end
  local t0 = clock()
  if a.way == 'simulate' then c.uic:SimulateLClick() else s.click(a.id) end
  return {id = a.id, way = a.way or 'direct', seconds = clock() - t0, state = panel_state(a.keys)}
end
function I.hover(a)
  local s = screen()
  if not (s and s.ui) then error('the panel is not open') end
  if not s.ui.by_id(a.id) then return {missing = a.id} end
  if a.way == 'simulate' then s.ui.by_id(a.id).uic:SimulateMouseOn() else s.hover(a.id) end
  local c = s.ui.by_id(a.id)
  local out = {id = a.id, hovered = s.ui.hovered and s.ui.hovered.id or nil, state = panel_state(a.keys)}
  -- the window that came with the hover: a slot's building window, a card's unit panel (their own components, by reference)
  local v = view()
  for _, t in ipairs(v and v.tree or {}) do
    if t.info.tip.visible then out.info = {node = t.node.key, x = t.info.tip.x, y = t.info.tip.y, w = t.info.tip.w, h = t.info.tip.h} end
  end
  for _, cr in ipairs(v and v.crew or {}) do
    if cr.info.panel.visible then out.unit = {group = cr.group, option = cr.option, x = cr.info.panel.x, y = cr.info.panel.y, w = cr.info.panel.w, h = cr.info.panel.h} end
  end
  -- a crew picker's card: its unit panel
  for g, area in pairs(v and v.crewAreas or {}) do
    for _, sl in ipairs(area.slots or {}) do
      local p = sl.info and sl.info.panel
      if p and p.visible then out.unit = {group = g, option = sl.key, x = p.x, y = p.y, w = p.w, h = p.h, picker = true} end
    end
  end
  return out
end

-- the module's baseline of the ship (what the next turn's news is told against) taken now: the session's setup stood buildings by script,
-- which no event told the module
function I.resync() local s = screen(); s.M.sync_ship(); return {synced = true} end

function I.state(a) return panel_state(a.keys) end

-- the crew's places as the module sees them now (a place exists from its mount; none without the barge), and their components
function I.places()
  local s, v = screen(), view()
  local out = {}
  for _, g in ipairs(s.M.group_order) do
    local a = v and v.crewAreas and v.crewAreas[g]
    out[#out + 1] = {group = g, place = s.M.crew_place(g), area = a and a.area and a.area.id or nil, area_visible = a and a.area and a.area.visible or nil,
      open = a and a.open or nil, options = #(s.M.crew_options(g) or {})}
  end
  return {places = out, carried = s.M.carried()}
end

-- close by the cross (S.click('mtb_ship_close'), as the listener) and the screen's state after the destroy's callback
function I.closed()
  local s = screen()
  local found = find_uicomponent(core:get_ui_root(), ROOT_ID)
  return {is_open = s and s.is_open() or false, root_left = found and true or false, keep = s and s.keep}
end
function I.reopen()
  local s = screen()
  local ok, err = s.open()
  return {ok = ok, err = err and flat(err) or nil, build_seconds = s.build_seconds, state = panel_state()}
end

-- Esc: the callback the panel stole the key with
function I.escape(a)
  local s = screen()
  if not (s and s.on_escape) then return {err = 'no on_escape (the panel is closed or the screen file is older)'} end
  local before = panel_state(a.keys)
  s.on_escape()
  return {before = {options = before.options, open = before.open}, state = panel_state(a.keys)}
end

-- e. who changes the treasury during the turn: cm.treasury_mod and the old mod's pay_upkeep wrapped (each call logged with its stack), the
-- original called through; off restores both exactly (an own field of cm is put back, an inherited one removed again)
function I.money_on()
  T.money = {}
  T.money_saved = T.money_saved or {cm_own = rawget(cm, 'treasury_mod'), crew = crew() and crew().pay_upkeep}
  local original = cm.treasury_mod
  cm.treasury_mod = function(self, faction, amount)
    local okt, tb = pcall(debug.traceback, '', 2)
    T.money[#T.money + 1] = {what = 'cm:treasury_mod', faction = tostring(faction), amount = amount, turn = cm:turn_number(), stack = okt and flat(tb) or nil}
    return original(self, faction, amount)
  end
  local c = crew()
  if c and type(c.pay_upkeep) == 'function' then
    local pay = c.pay_upkeep
    c.pay_upkeep = function(...)
      local before = cm:get_faction(FACTION):treasury()
      local r = {pay(...)}
      T.money[#T.money + 1] = {what = 'tww3_mtb_crew.pay_upkeep', turn = cm:turn_number(), delta = cm:get_faction(FACTION):treasury() - before, upkeep = c.upkeep and c.upkeep() or nil}
      return unpack(r)
    end
  end
  return {on = true, crew = c ~= nil}
end
function I.money_read() return {calls = T.money or {}, treasury = treasuries()} end
function I.money_off()
  local saved = T.money_saved
  if not saved then return {off = 'nothing to restore'} end
  cm.treasury_mod = saved.cm_own        -- nil: the class's own method is seen again
  local c = crew()
  if c and saved.crew then c.pay_upkeep = saved.crew end
  T.money_saved = nil
  return {off = true, restored_own = saved.cm_own ~= nil}
end

-- f. the panel's state through the adapter (cm:set_saved_value) and back (Ship.load_state) in this session; a second module over a game that
-- only reads (no listener of its own) takes the saved strings; the strings it would save again must equal the first module's, byte for byte
function I.save_check()
  local s = screen()
  local Ship, CM, config = mod('tww3_mtb_ship'), mod('tww3_mtb_crew_model'), mod('tww3_mtb_ship_config')
  local v = view()
  local keys = {}
  for _, k in ipairs(Ship.SAVE_KEYS) do keys[#keys + 1] = k end
  for _, g in ipairs(s.M.group_order) do keys[#keys + 1] = 'mtb_crew_' .. g end
  local before = {}
  for _, k in ipairs(keys) do before[k] = cm:get_saved_value(k) end
  local old = crew()
  local old_get = old and old.get and select(2, pcall(old.get)) or nil
  s.save()
  local want = Ship.save_state(s.M, s.keep)
  local after, differ = {}, {}
  for k, w in pairs(want) do
    after[k] = cm:get_saved_value(k)
    if after[k] ~= w then differ[#differ + 1] = {key = k, want = w, saved = after[k], saved_type = type(after[k])} end
  end
  local g = s.game
  local reads = {treasury = g.treasury, treasury_mod = function() error('the second module must not pay') end, turn = g.turn, has_building = g.has_building,
    standing = g.standing, under_construction = g.under_construction, issue_building_command = function() return false end,
    cancel_construction = function() return false end, dismantle = function() return false end, on = function() end}
  local M2 = Ship.make(config, reads, CM)
  local view2 = Ship.load_state(M2, function(k) return cm:get_saved_value(k) end)
  local again = Ship.save_state(M2, view2)
  local round = {}
  for k, w in pairs(want) do if again[k] ~= w then round[#round + 1] = {key = k, first = w, again = again[k]} end end
  local old_get_after = old and old.get and select(2, pcall(old.get)) or nil
  return {before = before, want = want, differ = differ, round_trip_differ = round, view2 = view2, keep = s.keep,
    old_mod_get_before = old_get, old_mod_get_after = old_get_after}
end

-- the probe's own items (tools/tests/port_probe.lua: add, avail, order, check, cancel, slots, first_empty, slot_read), their reads unchanged
function I.pp(a)
  local fn = PP.items[a.item]
  if not fn then error('no probe item ' .. tostring(a.item)) end
  return fn(a.args or {})
end

-- the game's own confirmation window (the cancel of a construction of an earlier turn opens «Отменить строительство»). Names from the game's
-- scripts: dialogue_box at the root (wh3_battle_prologue_values.lua), button_tick / button_cancel (wh2_dlc17_bloodgrounds.lua). Found by name.
local function dialog()
  local db = find_uicomponent(core:get_ui_root(), 'dialogue_box')
  if not db then return nil end
  return db, find_uicomponent(db, 'button_tick'), find_uicomponent(db, 'button_cancel')
end
function I.dialog()
  local db, tick, cancel = dialog()
  if not db then return {present = false} end
  local okv, vis = pcall(function() return db:VisibleFromRoot() end)
  return {present = true, visible = okv and vis or nil, tick = tick and true or false, cancel = cancel and true or false}
end
function I.dialog_answer(a)
  local db, tick, cancel = dialog()
  local b = (a.button == 'cancel') and cancel or tick
  if not b then return {clicked = false, present = db ~= nil} end
  b:SimulateLClick()
  return {clicked = a.button or 'tick'}
end

-- What the panel shows at each of the game's events of the turn (the adapter's order of completion and turn start is being fixed: this logs
-- the module's view right after each event, our listeners being added after the adapter's). Ours only for the worldwide events.
local WATCH = {'FactionTurnEnd', 'FactionTurnStart', 'CharacterTurnStart', 'MilitaryForceBuildingCompleteEvent', 'MilitaryForceBuildingCancelled',
  'BuildingCancelled', 'CharacterHordeBuildingDemolished', 'BuildingDemolished', 'BuildingConstructionIssuedByPlayer', 'MilitaryForceDevelopmentPointChange'}
local WORLD = {FactionTurnEnd = true, FactionTurnStart = true, CharacterTurnStart = true, BuildingDemolished = true, BuildingCancelled = true}
function I.watch_on(a)
  T.watch, T.watch_keys = {}, a.keys or {}
  for _, ev in ipairs(WATCH) do
    core:remove_listener('tww3_mtb_ss_w_' .. ev)
    core:add_listener('tww3_mtb_ss_w_' .. ev, ev, true, function(context)
      local okf, f = pcall(function() return context:faction():name() end)
      if WORLD[ev] and not (okf and f == FACTION) then
        local okc, ch = pcall(function() return context:character():faction():name() end)
        if not (okc and ch == FACTION) then return end
      end
      local okb, b = pcall(function() return context:building() end)
      local rec = {event = ev, clock = clock(), turn = cm:turn_number(), building = okb and type(b) == 'string' and b or nil}
      local ok, st = pcall(panel_state, T.watch_keys)
      if ok then
        rec.message, rec.unseen, rec.news, rec.treasury, rec.slots = st.message, st.unseen, st.news, st.treasury, st.slots
        rec.levels = {}
        for k, l in pairs(st.levels) do rec.levels[k] = {state = l.status and l.status.state, turns = l.under_construction, model_slot = l.model_slot, construction = l.construction} end
      else rec.err = flat(st) end
      T.watch[#T.watch + 1] = rec
    end, true)
  end
  return {on = #WATCH}
end
function I.watch_read() return {events = T.watch or {}} end
function I.watch_off() for _, ev in ipairs(WATCH) do core:remove_listener('tww3_mtb_ss_w_' .. ev) end; return {off = true} end

-- frames: the game's real timer every 1 ms counts its calls (one per frame at most) while the driver waits a known time
function I.frames_on() T.frames = 0; T.frames_clock = clock(); core:get_tm():repeat_real_callback(function() T.frames = T.frames + 1 end, 1, 'tww3_mtb_ss_frames'); return {on = true} end
function I.frames_off()
  pcall(function() core:get_tm():remove_real_callback('tww3_mtb_ss_frames') end)
  return {frames = T.frames, cpu = clock() - (T.frames_clock or clock())}
end

-- SetOpacity and PropagateOpacity on a parent that HAS an image (the probe tried holders without one): what Opacity() answers for the parent and
-- its child; the driver takes a picture. Left on screen until item clear.
function I.opacity_test()
  local ui = core:get_ui_root()
  local old = find_uicomponent(ui, DIAG_ID)
  if old then pcall(function() old:Destroy() end) end
  local holder = UIComponent(ui:CreateComponent(DIAG_ID, 'ui/tww3_mtb/layer_holder'))
  local out = {}
  local function pair(n, x, call)
    local p = UIComponent(holder:CreateComponent('ss_op_parent_' .. n, 'ui/tww3_mtb/image'))
    p:SetImagePath('ui/skins/default/icon_cross.png', 0); p:SetDockingPoint(1); p:SetDockOffset(x, 200); p:Resize(120, 120)
    local c = UIComponent(p:CreateComponent('ss_op_child_' .. n, 'ui/tww3_mtb/image'))
    c:SetImagePath('ui/skins/default/icon_treasury.png', 0); c:SetDockingPoint(1); c:SetDockOffset(30, 30); c:Resize(60, 60)
    local ok, e = pcall(call, p)
    local okp, op = pcall(function() return p:Opacity() end)
    local okc, oc = pcall(function() return c:Opacity() end)
    out[n] = {call_ok = ok, err = (not ok) and flat(e) or nil, parent = okp and op or flat(op), child = okc and oc or flat(oc), x = x}
  end
  pair('control', 100, function() end)
  pair('set_80', 260, function(p) p:SetOpacity(80) end)
  pair('set_80_true', 420, function(p) p:SetOpacity(80, true) end)
  pair('propagate_80', 580, function(p) p:PropagateOpacity(80) end)
  return out
end

-- the cost and the turns the game reads for a level (probe 14.11, item 3: from his character's context, no selection needed)
function I.cost(a)
  local n = a.slot or PP.first_empty()
  local rec = 'DatabaseRecordContext("CcoBuildingLevelRecord", "' .. a.key .. '")'
  return {key = a.key, slot = n, cost = PP.char(rec .. '.CreateCost(this)'), dev = PP.char(rec .. '.DevelopmentPointCost(this)'),
    time = n and PP.char(rec .. '.CreateTime(MilitaryForceContext.HordeContext.BuildingSlotList.At(' .. n .. '))') or nil,
    active = n and PP.char(rec .. '.IsActiveForBuildingBrowser(MilitaryForceContext.HordeContext.BuildingSlotList.At(' .. n .. '))') or nil}
end

-- a side building stood by script for the demolish path (the probe's add: cm:add_building_to_force, proven by its item 2), the panel refreshed
function I.stand(a)
  local r = PP.items.add({keys = {a.key}})
  local s = screen()
  if s and s.panel then s.panel.refresh() end
  return {add = r.adds, state = panel_state({a.key})}
end

-- whether the panel would let a level be demolished, against the game's own CanDismantle on its slot (no command is given)
function I.can_demolish(a)
  local s = screen()
  local d = s.M.can_demolish(a.key)
  local n
  for i, k in ipairs(game_slots()) do if k == a.key then n = i - 1 end end
  local can = n and PP.char('MilitaryForceContext.HordeContext.BuildingSlotList.At(' .. n .. ').CanDismantle') or nil
  return {panel_ok = d.ok, why = d.why, slot = n, game_can = can}
end

-- the demolish path: the built slot clicked (its round button comes), then the button; the game's slot a moment later is read by the driver
function I.dismantle_read(a)
  local n
  local slots = game_slots()
  for i, k in ipairs(type(slots) == 'table' and slots or {}) do if k == a.key then n = i - 1 end end
  local out = {key = a.key, model_slot = n, slots = slots}
  if a.slot then
    local base = 'MilitaryForceContext.HordeContext.BuildingSlotList.At(' .. a.slot .. ')'
    out.dismantling = PP.char(base .. '.IsDismantling')
    out.can = PP.char(base .. '.CanDismantle')
    out.building = PP.char(base .. '.BuildingContext.BuildingLevelRecordContext.Key')
  end
  out.state = panel_state({a.key})
  return out
end

-- the whole state at the end, then the panel closed by its own path
function I.finish()
  local s = screen()
  if not s then return {state = 'no screen in this Lua (a battle restarts the campaign Lua)', how = T.how} end
  local st = panel_state()
  if s.is_open() then s.close() end
  return {state = st, how = T.how}
end

-- ---------------------------------------------------------------- the call ----------------------------------------------------------------
function SS.run(name, args)
  local fn = I[name]
  local t0 = clock()
  local out
  if not fn then
    out = {ok = false, err = 'no item ' .. tostring(name)}
  else
    local ok, res = protect(fn, args or {})
    out = {ok = ok, data = ok and res or nil, err = (not ok) and tostring(res) or nil}
  end
  out.item = name
  out.cpu_ms = math.floor((clock() - t0) * 1000 + 0.5)
  local okj, text = pcall(J, out)
  if not okj or type(text) ~= 'string' then
    text = '{"ok":false,"item":"' .. tostring(name) .. '","err":"encoder failed: ' .. string.gsub(flat(text), '["\\]', ' ') .. '"}'
  end
  if mtb and mtb.log then pcall(mtb.log, 'ship_session', ssub(text, 1, 4000)) end
  return text
end

return 'ready'
