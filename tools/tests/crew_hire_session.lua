-- The session «crew_hire» (tools/tests/crew_hire_session.py; docs/design/port-to-game.md 8.6): the new panel's hire drives the old mod's crew
-- mechanics. Helpers only, sent after tools/tests/port_probe.lua and tools/tests/ship_session.lua (their encoder PP.J, protect, the screen as
-- _G.mtb_ss_state.scr after ship_session's item load): _G.mtb_ch.run(item, args) -> one JSON line.
--
-- The panel's own handlers only: a click here is S.click(id), the function the panel's ComponentLClickUp listener runs. The crew is read through
-- both books: the screen's model (S.M) and the old crew module (tww3_mtb_crew: get(), seat_plan(), malakai_seat(), its bridge). No global mouse
-- or key; only our own components; the game's own string.find is never called.

local PP = _G.mtb_pp
local SSX = _G.mtb_ss
if not (PP and SSX) then error('tools/tests/port_probe.lua and tools/tests/ship_session.lua must be sent before this file') end
local CH = {}
_G.mtb_ch = CH
local J, protect = PP.J, PP.protect
local ssub = string.sub_lua or string.sub
local FACTION = 'wh3_dlc25_dwf_malakai'
local ENV = getfenv(1)
local OWNED = {'rifles', 'cannons', 'bombs', 'cupolas', 'harpoon'}

local function crew() return _G.tww3_mtb_crew or ENV.tww3_mtb_crew end
local function screen() local T = _G.mtb_ss_state; return T and T.scr end
local function flat(s) s = tostring(s); s = string.gsub(s, '[\r\n]+', ' | '); return ssub(s, 1, 1500) end
local function gold() local ok, g = pcall(function() return cm:get_faction(FACTION):treasury() end); return ok and g or nil end
local I = {}

-- the crew as both books have it: the model's standing, order, place and open kinds; the old module's choice, the seats it would write, Malakai's
-- seat, the bridge, the cargo and the boosts; the gold and both upkeeps
function I.crew(a)
  local s, c = screen(), crew()
  local out = {gold = gold(), groups = {}}
  if c then
    out.status = tostring(c.status)
    out.new_panel = c.new_panel and c.new_panel() or nil
    local okg, get = pcall(c.get)
    out.old = okg and get or flat(get)
    local okp, plan = pcall(c.seat_plan)
    out.plan = okp and plan or flat(plan)
    local okm, mk = pcall(c.malakai_seat)
    out.malakai = okm and mk or flat(mk)
    out.bridge = {attached = c.bridge and c.bridge.S ~= nil or false, writes = c.bridge and c.bridge.writes or 0, applied = c.bridge and c.bridge.applied or nil}
    out.writes = c.writes
    out.cargo = c.ammo_mod and c.ammo_mod() or nil
    local oks, svr = pcall(function() return core:svr_load_string('mtb_crew_ammo_mod') end)
    out.cargo_battle = oks and svr or nil
    local oku, now, nxt = pcall(c.upkeep)
    out.old_upkeep = oku and {now = now, next = nxt} or flat(now)
    out.paying = c.paying and c.paying() or nil
    out.boost = {}
    for _, g in ipairs(OWNED) do out.boost[g] = c.boost_level and c.boost_level(g) or nil end
  end
  if s and s.M then
    local M = s.M
    out.adapter_gold = s.game.treasury()
    out.model_upkeep = {now = M.crew_upkeep(), next = M.crew_upkeep_next()}
    out.message = M.message()
    out.side = M.malakai_side()
    out.crew_pays = s.game.crew_pays and s.game.crew_pays() or nil
    for _, g in ipairs(OWNED) do
      local opts = {}
      for _, o in ipairs(M.crew_options(g) or {}) do opts[#opts + 1] = o.key .. (o.unlocked and '+' or '-') .. ':' .. tostring(o.hire) .. '/' .. tostring(o.upkeep) end
      local note = M.crew_note(g)
      out.groups[g] = {standing = M.crew(g), order = M.crew_order(g), place = M.crew_place(g), options = opts, note = note and note.text or nil}
    end
  end
  return out
end

-- a building ordered by the model (the panel's own order: the adapter's command from his context) or stood by script (the probe's add, no event:
-- the bridge is told then, as the battle's start would tell it)
function I.order(a)
  local s = screen()
  local r = s.M.order(a.key)
  return {result = r, crew = I.crew({})}
end
function I.stand(a)
  local r = PP.items.add({keys = a.keys})
  local s = screen()
  if s and s.M then s.M.sync_ship() end
  local c = crew()
  local wrote = c and c.bridge and c.bridge.sync and c.bridge.sync('script') or false
  if s and s.panel and s.shown then s.panel.refresh() end
  return {add = r.adds, wrote = wrote, crew = I.crew({})}
end
function I.sync(a)
  local c = crew()
  return {wrote = c.bridge.sync(a.reason or 'session'), crew = I.crew({})}
end
function I.demolish(a)
  local s = screen()
  return {result = s.M.demolish(a.key), status = s.M.status(a.key), crew = I.crew({})}
end

-- the panel open on «Корабль» (by its own open; the tab by its own click)
local function open_ship()
  local s = screen()
  if not s.is_open() then local ok, e = s.open(); if not ok then error('the panel did not open: ' .. flat(e)) end end
  s.click('mtb_tab_ship')
end
-- a hire through the panel's own handlers: the place's area clicked (the picker opens), then the kind's card in it
function I.pick(a)
  local s = screen()
  open_ship()
  local before = I.crew({})
  local area = 'mtb_crew_area_' .. a.group
  if not s.ui.by_id(area) then return {missing = area, crew = before} end
  s.click(area)
  local card = 'mtb_crew_card_pick_' .. a.group .. ':' .. a.option
  if not s.ui.by_id(card) then return {missing = card, crew = before} end
  s.click(card)
  local after = I.crew({})
  return {area = area, card = card, before = before, after = after}
end
-- Malakai's side by its mark on the plan (the panel's own handler)
function I.side(a)
  local s = screen()
  open_ship()
  local id = 'mtb_side_' .. a.side
  if not s.ui.by_id(id) then return {missing = id, crew = I.crew({})} end
  s.click(id)
  return {id = id, crew = I.crew({})}
end
function I.close()
  local s = screen()
  if s.is_open() then s.close() end
  return {open = s.is_open()}
end

-- the barge unit in the campaign after a battle: its strength (what the battle took) and the force's effect bundles
function I.barge()
  local out = {}
  local ok, err = pcall(function()
    local m = PP.malakai()
    local units = m:military_force():unit_list()
    for i = 0, units:num_items() - 1 do
      local u = units:item_at(i)
      if u:unit_key() == 'mtb_dwf_cha_malakai_thunderbarge' then
        out.unit = u:unit_key()
        out.strength = u:percentage_proportion_of_full_strength()
      end
    end
    local c = crew()
    out.harpoon_off = m:military_force():has_effect_bundle('mtb_bundle_harpoon_off')
    out.on_barge = c and c.paying and c.paying() or nil
  end)
  if not ok then out.err = flat(err) end
  return out
end

-- ---------------------------------------------------------------- what the player sees (15.11 afternoon) ----------------------------------------------------------------
-- Every answer below is read from the game's own components (UIComponent GetStateText / GetTooltipText / Visible / VisibleFromRoot) or from the
-- game's own state (cm, the context), never from the mod's account of itself; the mod's own words are logged next to them, marked so.
local ST = _G.mtb_ch_state or {}          -- survives the next send (not a battle: the campaign Lua restarts after it)
_G.mtb_ch_state = ST
local sfind = string.find_lua or string.find
local function view() local s = screen(); return s and s.panel and s.panel.view end
local function uic_of(c) if type(c) == 'table' and c.uic then return c.uic end return c end
-- the text the game's component holds (the wrapper's own copy only when the game does not answer: marked)
local function drawn(c)
  if not c then return nil end
  local ok, t = pcall(function() return uic_of(c):GetStateText() end)
  if ok and type(t) == 'string' then return t end
  return nil
end
local function tip(c)
  if not c then return {} end
  local ok, t = pcall(function() return uic_of(c):GetTooltipText() end)
  if ok and type(t) == 'string' then return {text = t, from = 'game'} end
  return {text = type(c) == 'table' and c.tooltip or nil, from = 'wrapper (GetTooltipText: ' .. flat(t) .. ')'}
end
-- a wrapper component's box on the game's root (src/tww3_mtb_ship_uic.lua: x, y relative to the parent; the panel's holder at 0, 0)
local function box(c, pad)
  pad = pad or 0
  local x, y, p = 0, 0, c
  while p do x = x + (p.x or 0); y = y + (p.y or 0); p = p.parent end
  local out = {x = x - pad, y = y - pad, w = (c.w or 0) + 2 * pad, h = (c.h or 0) + 2 * pad}
  local ok, ax, ay = pcall(function() return uic_of(c):Position() end)
  if ok then out.game_x, out.game_y = ax, ay end
  return out
end
local function vis(u)
  if not u then return nil end
  local out = {}
  local ok1, a = pcall(function() return u:Visible() end)
  if ok1 then out.own = a and true or false end
  local ok2, b = pcall(function() return u:VisibleFromRoot() end)
  if ok2 then out.from_root = b and true or false end
  return out
end
-- the foot row as the game draws it: both its lines (src/tww3_mtb_ship_ui.lua UI.foot_lines: message, message2 when the text needs two), each
-- only when shown; their tooltip (the whole text when a line was cut); the box of both
local function foot_drawn(v)
  if not (v and v.message) then return nil, nil, nil end
  local parts, tipt = {}, nil
  for _, c in ipairs({v.message, v.message2}) do
    local on = vis(c.uic)
    local t = drawn(c)
    if on and on.own ~= false and t and t ~= '' then parts[#parts + 1] = t end
    local tt = tip(c).text
    if tt and tt ~= '' then tipt = tt end
  end
  local b = box(v.message, 6)
  if v.message2 then local b2 = box(v.message2, 6); b.h = math.max(b.y + b.h, b2.y + b2.h) - b.y end
  return table.concat(parts, ' '), tipt, b
end
local function root_ui() return core:get_ui_root() end

-- the mod's log file (src/tww3_mtb_campaign.lua file_log: tww3_mtb_log.txt in the game's folder; the fake keeps it in fake_log)
local function log_lines()
  if type(_G.fake_log) == 'table' then return _G.fake_log end
  local ok, f = pcall(function() return io.open('tww3_mtb_log.txt', 'r') end)
  if not ok or not f then return {} end
  local t = {}
  for line in f:lines() do t[#t + 1] = line end
  f:close()
  return t
end
function I.log_mark() local l = log_lines(); ST.log_n = #l; return {n = ST.log_n} end
function I.log_since(a)
  local l, out = log_lines(), {}
  local from = (ST.log_n or 0) + 1
  if from > #l + 1 then from = 1 end       -- the file started anew (the campaign Lua restarted)
  for i = from, #l do
    local line = tostring(l[i])
    if not a.has or sfind(line, a.has, 1, true) then out[#out + 1] = line end
  end
  return {lines = out, total = #l}
end

-- the panel as the game draws it: its holder's visibility, every window of ours still shown by its own flag, the top-most layer, the pickers,
-- the foot row's text as the game's component holds it; the game's moment (blocker) and the turn
-- the windows (a component on the hover or the click layer: a building's window, a unit's panel, the crew's choice) still shown by their own flag;
-- other top-most components (a place's glow) only listed: they draw with the panel's holder, and the layer is off while it is closed
local function windows_shown(s)
  local out, tops = {}, {}
  local function walk(c)
    if c.topmost and c.visible then
      if c.layer then out[#out + 1] = c.id else tops[#tops + 1] = c.id end
    end
    for _, k in ipairs(c.children or {}) do walk(k) end
  end
  if s and s.root then walk(s.root) end
  return out, tops
end
local function look()
  local s, v = screen(), view()
  local out = {is_open = s and s.is_open() or false}
  local r = find_uicomponent(root_ui(), 'mtb_ship_screen')
  out.root = r and vis(r) or 'none'
  out.topmost_on = (s and s.ui and s.ui.topmost_on) and s.ui.topmost_on() or false
  out.windows, out.topmost_shown = windows_shown(s)
  local pickers = {}
  for g, ar in pairs(v and v.crewAreas or {}) do
    local pv = ar.pick and vis(ar.pick.uic)
    if ar.open or (pv and pv.own) then pickers[#pickers + 1] = g end
  end
  out.pickers = pickers
  out.foot = v and (foot_drawn(v)) or nil
  if s and s.game and s.game.blocker then local ok, b = pcall(s.game.blocker); out.blocker = ok and (b or 'none') or ('ERR ' .. flat(b)) end
  out.turn = cm:turn_number()
  local okl, lt = pcall(function() return cm:is_local_players_turn(true) end)
  out.local_turn = okl and lt or nil
  return out
end
I.look = look

-- the turn end with the panel open: what the screen looks like a moment after Malakai's FactionTurnEnd (the AI's turn is running then)
function I.turn_watch_on()
  ST.turn_snaps = {}
  core:remove_listener('tww3_mtb_ch_turn_watch')
  core:add_listener('tww3_mtb_ch_turn_watch', 'FactionTurnEnd', function(c) return c:faction():name() == FACTION end, function()
    ST.turn_snaps[#ST.turn_snaps + 1] = {at = 'the event', look = look()}
    core:get_tm():real_callback(function()
      local ok, l = pcall(look)
      ST.turn_snaps[#ST.turn_snaps + 1] = {at = '0.6 s after the event', look = ok and l or {err = flat(l)}}
    end, 600, 'tww3_mtb_ch_turn_watch_late')
  end, true)
  return {on = true}
end
function I.turn_watch_read()
  core:remove_listener('tww3_mtb_ch_turn_watch')
  return {snaps = ST.turn_snaps or {}, now = look()}
end

-- the crew's picker of a place opened by its own area's click (no card clicked): the window a player has open
function I.open_picker(a)
  local s = screen()
  if not s.is_open() then local ok, e = s.open(); if not ok then return {opened = false, why = flat(e), look = look()} end end
  s.click('mtb_tab_ship')
  local v = view()
  local ar = v.crewAreas[a.group]
  if not (ar and ar.open) then s.click('mtb_crew_area_' .. a.group) end
  return {opened = true, look = look()}
end

-- the HUD's button of the mod (src/tww3_mtb_crew_ui.lua refresh_button) as the game draws it: state, the «!» mark, the tooltip; its box
local HUD_PATH = {'hud_campaign', 'faction_buttons_docker', 'button_group_management', 'button_mtb_crew'}
local function hud_button() return find_uicomponent(root_ui(), HUD_PATH[1], HUD_PATH[2], HUD_PATH[3], HUD_PATH[4]) end
function I.hud(a)
  local cu = _G.tww3_mtb_crew_ui or ENV.tww3_mtb_crew_ui
  if a.refresh and cu and cu.refresh_button then pcall(cu.refresh_button) end
  local b = hud_button()
  if not b then return {button = 'none'} end
  local out = {button = 'found'}
  local ok, st = pcall(function() return b:CurrentState() end)
  out.state = ok and st or nil
  out.visible = vis(b)
  local mark = find_uicomponent(b, 'alert')
  out.mark = mark and vis(mark) or 'none'
  out.tooltip = tip(b)
  local okp, x, y = pcall(function() return b:Position() end)
  local okb, w, h = pcall(function() return b:Bounds() end)
  out.box = {x = okp and x or nil, y = okp and y or nil, w = okb and w or nil, h = okb and h or nil}
  local s = screen()
  out.mod_says = s and s.button_state and s.button_state() or nil       -- the mod's own account: next to the game's, never instead
  if a.hover then pcall(function() b:SimulateMouseOn() end); out.hovered = true end
  return out
end
-- a click on the HUD's button: the game's SimulateLClick (what a click of the player sends, when the game sends it for an inactive button), then,
-- when the screen did not move, the button's own handler (src/tww3_mtb_crew_ui.lua on_click); the log says what the mod answered
function I.hud_click(a)
  local s = screen()
  local before = s.is_open()
  I.log_mark()
  local b = hud_button()
  local out = {before = before}
  if b then local ok, e = pcall(function() b:SimulateLClick() end); out.simulated = ok and 'sent' or flat(e) end
  out.after_simulated = s.is_open()
  out.log_simulated = I.log_since({}).lines
  if a.direct and out.after_simulated == before then
    local cu = _G.tww3_mtb_crew_ui or ENV.tww3_mtb_crew_ui
    I.log_mark()
    local ok, e = pcall(function() cu.on_click('button_mtb_crew') end)
    out.direct = ok and 'called' or flat(e)
    out.after_direct = s.is_open()
    out.log_direct = I.log_since({}).lines
  end
  out.look = look()
  return out
end
-- the screen's own open (S.open) while the game's moment is up: its answer
function I.try_open()
  local s = screen()
  local ok, why = s.open()
  local out = {ok = ok, why = why and flat(why) or nil, look = look()}
  return out
end

-- the game's moment: what the adapter says (src/tww3_mtb_game.lua blocker), what the model makes of it (M.can_open), and the game's own reads
-- under it: the events panel on the screen, the ui manager's flag, the dilemma's response, the turn
function I.blocker()
  local s = screen()
  local out = {}
  local ok, b = pcall(s.game.blocker)
  out.adapter = ok and (b or 'none') or ('ERR ' .. flat(b))
  local okc, c = pcall(s.M.can_open)
  out.can_open = okc and c or flat(c)
  local e = find_uicomponent(root_ui(), 'events')
  out.events = e and vis(e) or 'none'
  local uim = (function() local okm, m = pcall(function() return cm:get_campaign_ui_manager() end); return okm and m or nil end)()
  local oke, ev = pcall(function() return uim:is_event_panel_open() end)
  out.ui_manager_event_panel = oke and ev or ('ERR ' .. flat(ev))
  local CUI = ENV.CampaignUI or _G.CampaignUI
  out.campaign_ui = CUI and 'present' or 'nil in this environment'
  local okd, d = pcall(function() return CUI.DoesEventTypeRequireResponse('faction_event_dilemmaevent_feed_target_dilemma_faction') end)
  out.dilemma_waits = okd and d or ('ERR ' .. flat(d))
  local okl, lt = pcall(function() return cm:is_local_players_turn(true) end)
  out.local_turn = okl and lt or nil
  out.turn = cm:turn_number()
  return out
end
-- a stock incident by script (no payload, no option rows in the game's data: db cdir_events_incident_payloads / _option_junctions): the first of
-- the keys that the game reports issued (IncidentOccuredEvent) within the call or by the next read
function I.incident(a)
  ST.incidents = {}
  core:remove_listener('tww3_mtb_ch_incident')
  core:add_listener('tww3_mtb_ch_incident', 'IncidentOccuredEvent', true, function(c)
    local okk, k = pcall(function() return c:dilemma() end)
    ST.incidents[#ST.incidents + 1] = okk and tostring(k) or 'issued'
  end, true)
  local tried = {}
  for _, key in ipairs(a.keys or {}) do
    local ok, e = pcall(function() return cm:trigger_incident(FACTION, key, true) end)
    tried[#tried + 1] = {key = key, call = ok and tostring(e) or ('ERR ' .. flat(e)), heard = #ST.incidents}
    if #ST.incidents > 0 then break end
  end
  return {tried = tried, heard = ST.incidents}
end
function I.incident_read()
  core:remove_listener('tww3_mtb_ch_incident')
  return {heard = ST.incidents or {}, blocker = I.blocker(), look = look()}
end
-- the game's events panel answered as the session's turn end answers it (a dilemma: its first choice; an event: accept)
function I.dismiss()
  local n = 0
  for _ = 1, 6 do
    local e = find_uicomponent(root_ui(), 'events')
    local ok, on = pcall(function() return e and e:VisibleFromRoot() end)
    if not (ok and on) then break end
    local b = find_uicomponent(e, 'choice_button') or find_uicomponent(e, 'button_accept')
    if not b then break end
    b:SimulateLClick()
    n = n + 1
  end
  return {answered = n}
end

-- E, F: the hired kind's unit window in the picker (the card under the mouse) and the picker's upkeep line, read back from the game's components
function I.unit_window(a)
  local s = screen()
  local r = I.open_picker({group = a.group})
  if not r.opened then return r end
  local v = view()
  local ar = v.crewAreas[a.group]
  if ar.buildPick then pcall(ar.buildPick) end
  local card = 'mtb_crew_card_pick_' .. a.group .. ':' .. a.option
  s.hover(card)
  local out = {card = card, hovered = s.ui.hovered and s.ui.hovered.id or nil}
  local slot
  for _, sl in ipairs(ar.slots or {}) do if sl.key == a.option then slot = sl end end
  local info = slot and slot.info
  if info and info.panel then
    out.window = vis(info.panel.uic)
    out.window_box = box(info.panel, 12)
    local rows = {}
    for k, row in pairs(info.rows or {}) do rows[k] = row.value and drawn(row.value) or nil end
    out.rows = rows
    out.ammo_text = info.rows and info.rows.ammo and drawn(info.rows.ammo.value) or nil
    out.ammo_note = info.ammoNote and drawn(info.ammoNote) or nil
    out.ammo_model = info.ammo        -- the panel's own numbers: logged beside, not used for the verdict
    -- every text of the window that says «с N до M» (the bonus line), as the game's components hold it
    local lines = {}
    local function walk(c)
      local t = c.text_layout and drawn(c) or nil
      if t and sfind(t, ' до ', 1, true) then lines[#lines + 1] = {id = c.id, text = t, box = box(c, 6)} end
      for _, k in ipairs(c.children or {}) do walk(k) end
    end
    walk(info.panel)
    out.bonus_lines = lines
  else
    out.window = 'none (no unit window made for ' .. card .. ')'
  end
  if ar.foot then out.upkeep_text = drawn(ar.foot); out.upkeep_box = box(ar.foot, 8) end
  out.look = look()
  return out
end

-- D: what a dismantle gives back, as the game's own slot says it (both expressions), as the adapter has it, and the faction's money now: the
-- treasury, the context's Income, the HUD's income label (the game's own number under the treasury); the panel's forecast (M.turn_gold) and its
-- treasury tooltip as the game's component holds it
function I.refund_read(a)
  local s = screen()
  local out = {key = a.key, treasury = gold()}
  local n
  local okg, slots = pcall(PP.slots)
  for i, k in ipairs(okg and slots or {}) do if k == a.key then n = i - 1 end end
  out.slot = n
  if n then
    local base = 'MilitaryForceContext.HordeContext.BuildingSlotList.At(' .. n .. ')'
    out.game_building_refund = PP.char(base .. '.BuildingContext.DismantleRefundAmount')
    out.game_slot_refund = PP.char(base .. '.DismantleRefundAmount')
    out.dismantling = PP.char(base .. '.IsDismantling')
  end
  local okr, r = pcall(s.game.dismantle_refund, a.key)
  out.adapter_refund = okr and r or flat(r)
  out.turn_gold = s.M.turn_gold()
  local okf, f = pcall(function()
    local fac = cm:get_faction(FACTION)
    local id = tostring(fac:command_queue_index())
    local function c(expr) local ok, x = pcall(common.get_context_value, 'CcoCampaignFaction', id, expr); return ok and x or nil end
    return {income = c('Income'), treasury_amount = c('TreasuryAmount')}
  end)
  out.faction = okf and f or flat(f)
  local di = find_uicomponent(root_ui(), 'dy_income')
  out.hud_income = di and drawn(di) or 'none'
  local v = view()
  if v and v.gold then out.gold_tooltip = tip(v.gold) end
  return out
end

-- C: the panel opened as the player opens it (the HUD's button: its handler), the foot row read at once from the game's component
function I.open_read(a)
  local s = screen()
  I.log_mark()
  local cu = _G.tww3_mtb_crew_ui or ENV.tww3_mtb_crew_ui
  local way
  if cu and cu.on_click then pcall(function() cu.on_click('button_mtb_crew') end); way = 'the HUD button handler' end
  if not s.is_open() then s.open(); way = 'S.open (the handler did not open it)' end
  local v = view()
  local foot, ftip, fbox = foot_drawn(v)
  return {way = way, open = s.is_open(), foot = foot, foot_tip = ftip, foot_box = fbox, model_report = s.M.report(), model_message = s.M.message(), look = look()}
end
-- C: a click on a kind of the place's picker (the area, then the card, the panel's own handlers) and the foot row read right after
function I.pick_read(a)
  local s = screen()
  local v = view()
  if v and v.tab ~= 'ship' then s.click('mtb_tab_ship') end      -- a tab's click changes no line of the foot
  local ar = v and v.crewAreas[a.group]
  if not (ar and ar.open) then s.click('mtb_crew_area_' .. a.group) end
  s.click('mtb_crew_card_pick_' .. a.group .. ':' .. a.option)
  v = view()
  local foot, ftip = foot_drawn(v)
  return {foot = foot, foot_tip = ftip, model_report = s.M.report(), model_message = s.M.message(), log = I.log_since({has = 'report'}).lines}
end

-- D: the demolish's round button over the selected slot as the game holds it: shown, its tooltip, its box; hover: the game's SimulateMouseOn (the
-- game's own tooltip comes on a real mouse; whether a simulated one brings it is what the picture shows)
function I.raze_read(a)
  local s, v = screen(), view()
  local r = v and v.raze
  if not r then return {raze = 'none'} end
  local out = {shown = vis(r.uic), tooltip = tip(r), box = box(r, 60), ok = v.razeOk, selected = v.options}
  if v.options then out.model_preview = s.M.demolish_preview(v.options) end
  if a.hover then pcall(function() r.uic:SimulateMouseOn() end); out.hovered = true end
  return out
end

-- this file's own smoke: every read once, protected
function CH.smoke()
  local lines = {}
  for _, name in ipairs({'crew', 'barge', 'look', 'hud', 'log_mark'}) do
    local ok, r = protect(I[name], {})
    lines[#lines + 1] = 'S\t' .. name .. '\t' .. (ok and 'ok' or ('ERR ' .. flat(r)))
  end
  return table.concat(lines, '\n')
end

function CH.run(name, args)
  local scr = screen()
  if scr and scr.game and scr.game.invalidate then pcall(scr.game.invalidate) end
  local fn = I[name]
  local out
  if not fn then out = {ok = false, err = 'no item ' .. tostring(name)}
  else
    local ok, res = protect(fn, args or {})
    out = {ok = ok, data = ok and res or nil, err = (not ok) and tostring(res) or nil}
  end
  out.item = name
  local okj, text = pcall(J, out)
  if not okj or type(text) ~= 'string' then text = '{"ok":false,"item":"' .. tostring(name) .. '","err":"encoder failed"}' end
  return text
end

return 'ready'
