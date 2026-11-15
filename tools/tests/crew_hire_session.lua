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

-- this file's own smoke: every read once, protected
function CH.smoke()
  local lines = {}
  for _, name in ipairs({'crew', 'barge'}) do
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
