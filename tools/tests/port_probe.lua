-- The engine questions of docs/design/port-to-game.md, stage 1 (section 5, items 1-11). Helpers only: tools/tests/port_probe.py sends this
-- file before every call (tools/rc.py) and calls _G.mtb_pp.run(item, args). Every call returns one JSON line, written also to the events file.
-- Nothing of the mod is changed. The game's own UI is only reached by find_uicomponent with a path or a name; there is no ChildCount / Find(i)
-- walk anywhere here (run 20261104-191037: such a walk broke the game's bindings). Our own components are kept in _G.mtb_pp_state.
local PP = {}
_G.mtb_pp = PP
local S = _G.mtb_pp_state or {}       -- survives the next send of this file, not a battle (Lua restarts with the mode)
_G.mtb_pp_state = S
S.keep = S.keep or {}
S.events = S.events or {}
PP.S = S

local PREFIX = 'wh3_dlc25_dwarf_spirit_of_grungni_'
local SUBTYPE = 'wh3_dlc25_dwf_malakai_makaisson'
local SLOTS = 'MilitaryForceContext.HordeContext.BuildingSlotList'
local LAYOUT = 'ui/tww3_mtb_pp/'
local ROOT_ID = 'tww3_mtb_pp_root'
local LISTENER = 'tww3_mtb_pp_'

-- ---------------------------------------------------------------- JSON ----------------------------------------------------------------
local function esc(s)
  return (string.gsub(s, '[%z\1-\31\\"]', function(c)
    local map = {['"'] = '\\"', ['\\'] = '\\\\', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t'}
    return map[c] or string.format('\\u%04x', string.byte(c))
  end))
end

local function J(v, depth)
  depth = depth or 0
  local t = type(v)
  if v == nil then return 'null' end
  if t == 'boolean' then return tostring(v) end
  if t == 'number' then
    if v ~= v or v == math.huge or v == -math.huge then return '"' .. tostring(v) .. '"' end
    if v == math.floor(v) and math.abs(v) < 1e15 then return string.format('%d', v) end
    return string.format('%.6g', v)
  end
  if t == 'string' then return '"' .. esc(v) .. '"' end
  if t ~= 'table' or depth > 12 then return '"' .. esc(tostring(v)) .. '"' end
  local n = #v
  local is_array = n > 0
  if is_array then
    for k in pairs(v) do
      if type(k) ~= 'number' or k < 1 or k > n or k ~= math.floor(k) then is_array = false; break end
    end
  end
  local out = {}
  if is_array then
    for i = 1, n do out[i] = J(v[i], depth + 1) end
    return '[' .. table.concat(out, ',') .. ']'
  end
  local keys = {}
  for k in pairs(v) do keys[#keys + 1] = tostring(k) end
  table.sort(keys)
  for _, k in ipairs(keys) do
    local x = v[k]
    if x == nil then x = v[tonumber(k)] end
    out[#out + 1] = '"' .. esc(k) .. '":' .. J(x, depth + 1)
  end
  return '{' .. table.concat(out, ',') .. '}'
end
PP.J = J

-- ---------------------------------------------------------------- the campaign ----------------------------------------------------------------
local function malakai()
  local fl = cm:model():world():faction_list()
  for i = 0, fl:num_items() - 1 do
    local cl = fl:item_at(i):character_list()
    for j = 0, cl:num_items() - 1 do
      if cl:item_at(j):character_subtype_key() == SUBTYPE then return cl:item_at(j) end
    end
  end
end
PP.malakai = malakai

local function cqi() return tostring(malakai():command_queue_index()) end
local function faction() return malakai():faction():name() end
local function gold() return cm:get_faction(faction()):treasury() end

-- One read of a context expression: {t = type, v = value} or {err = text}.
local function read(object, id, expr)
  local ok, v = pcall(common.get_context_value, object, id, expr)
  if not ok then return {err = string.sub(tostring(v), 1, 160)} end
  if v == nil then return {t = 'nil'} end
  local tv = type(v)
  if tv == 'number' or tv == 'string' or tv == 'boolean' then return {t = tv, v = v} end
  return {t = tv, v = tostring(v)}
end
local function char(expr) return read('CcoCampaignCharacter', cqi(), expr) end
local function rec(key, expr) return read('CcoBuildingLevelRecord', key, expr) end
local function value(r) return r and r.v end
PP.read, PP.char = read, char

local function slot_list() return malakai():military_force():horde_details():military_force_slot_list() end

-- Keys in the slots, index 1 = slot 0 (the hull). '' for no building.
local function slots()
  local list, out = slot_list(), {}
  for i = 0, list:num_items() - 1 do
    local s = list:item_at(i)
    out[#out + 1] = s:has_building() and s:building() or ''
  end
  return out
end
PP.slots = slots

local function index_of(key)
  local list = slot_list()
  for i = 0, list:num_items() - 1 do
    if list:item_at(i):has_building() and list:item_at(i):building() == key then return i end
  end
end

local function slot_read(n)
  local base = SLOTS .. '.At(' .. n .. ')'
  return {
    empty = value(char(base .. '.IsEmpty')),
    building = value(char(base .. '.BuildingContext.BuildingLevelRecordContext.Key')),
    item = value(char('IsContextValid(' .. base .. '.ConstructionItemContext)')),
    turns = value(char(base .. '.ConstructionItemContext.TurnsToCompletion')),
    item_level = value(char(base .. '.ConstructionItemContext.BuildingLevelRecordContext.Key')),
    item_level2 = value(char(base .. '.ConstructionItemContext.BuildingLevelContext.Key')),
  }
end
PP.slot_read = slot_read

-- A side slot with nothing in it and nothing being built; skip: {[index] = true}.
local function first_empty(skip)
  local list = slot_list()
  for i = 1, list:num_items() - 1 do
    if not list:item_at(i):has_building() and not (skip and skip[i]) then
      local r = slot_read(i)
      if r.item ~= true then return i end
    end
  end
end
PP.first_empty = first_empty

local function select_malakai()
  CampaignUI.ClearSelection()
  common.call_context_command('CcoCampaignCharacter', cqi(), 'SelectAndZoom(false)')
end

-- way: own = the record reached from the character's context, no selection needed ([игра: 191708]); selected = the stock expression.
local function order(key, n, way)
  local ok, err
  if way == 'selected' then
    ok, err = pcall(common.call_context_command, 'CcoBuildingLevelRecord', key, 'IssueCommandForBuildingBrowser(SelectedCharacter.' .. SLOTS .. '.At(' .. n .. '))')
  else
    ok, err = pcall(common.call_context_command, 'CcoCampaignCharacter', cqi(),
      'DatabaseRecordContext("CcoBuildingLevelRecord", "' .. key .. '").IssueCommandForBuildingBrowser(' .. SLOTS .. '.At(' .. n .. '))')
  end
  return {ok = ok, err = (not ok) and tostring(err) or nil, way = way, slot = n, key = key}
end

local function add(key)
  local mf = malakai():military_force()
  local ok, err = pcall(function() cm:add_building_to_force(mf:command_queue_index(), key) end)
  return {ok = ok, err = (not ok) and tostring(err) or nil, at = index_of(key)}
end

-- Was the order taken: the slot has a construction of the key, or the gold went down.
local function accepted(key, n, gold_before)
  local r = slot_read(n)
  local g = gold()
  r.gold_before, r.gold = gold_before, g
  r.accepted = (r.item == true and (r.item_level == key or r.item_level2 == key or (r.item_level == nil and r.item_level2 == nil))) or (gold_before ~= nil and g < gold_before)
  return r
end

local function slots_info()
  local list = slot_list()
  local occupied, empty = 0, {}
  for i = 1, list:num_items() - 1 do
    if list:item_at(i):has_building() then occupied = occupied + 1 else empty[#empty + 1] = i end
  end
  return {num_items = list:num_items(), cco_size = value(char(SLOTS .. '.Size')), side_occupied = occupied, empty = empty, slots = slots(),
    dev = value(char('MilitaryForceContext.HordeContext.DevelopmentPoints')), gold = gold()}
end
PP.slots_info = slots_info

-- ---------------------------------------------------------------- our own UI ----------------------------------------------------------------
local function make(parent, id, layout)
  local path = string.find(layout, '/', 1, true) and layout or LAYOUT .. layout
  return UIComponent(parent:CreateComponent(id, path))
end

local function size(c, w, h)
  w, h = math.floor(w + 0.5), math.floor(h + 0.5)
  c:SetCanResizeWidth(true)
  c:SetCanResizeHeight(true)
  c:Resize(w, h)
  for i = 0, c:NumImages() - 1 do
    c:SetCanResizeCurrentStateImageWidth(i, true)
    c:SetCanResizeCurrentStateImageHeight(i, true)
    c:ResizeCurrentStateImage(i, w, h)
  end
end

local function at(c, x, y)
  c:SetDockingPoint(1)
  c:SetDockOffset(math.floor(x + 0.5), math.floor(y + 0.5))
end

local function box(parent, id, layout, x, y, w, h)
  local c = make(parent, id, layout)
  size(c, w, h)
  at(c, x, y)
  return c
end

local function rect(c)
  local x, y = c:Position()
  local w, h = c:Bounds()
  return {x = x, y = y, w = w, h = h, width = c:Width(), height = c:Height()}
end

local function ui_root() return core:get_ui_root() end

-- Destroys our root (and with it every component of ours) and makes a new one: a full-screen container that takes no mouse.
local function new_root()
  local ui = ui_root()
  if S.root then pcall(function() S.root:Destroy() end) end
  local old = find_uicomponent(ui, ROOT_ID)
  if old then pcall(function() old:Destroy() end) end
  local r = make(ui, ROOT_ID, 'pp_zone')
  size(r, ui:Width(), ui:Height())
  r:MoveTo(0, 0)
  S.root = r
  S.keep = {}
  return r
end

local function clear()
  local n = 0
  if S.root then
    local ok = pcall(function() S.root:Destroy() end)
    n = ok and 1 or 0
  end
  local old = find_uicomponent(ui_root(), ROOT_ID)
  if old then pcall(function() old:Destroy() end); n = n + 1 end
  S.root, S.keep = nil, {}
  return n
end

local function members(uic)
  local out, mt = {}, getmetatable(uic)
  local function scan(x) if type(x) == 'table' then for k in pairs(x) do out[#out + 1] = tostring(k) end end end
  if type(uic) == 'table' then scan(uic) end
  if type(mt) == 'table' then scan(type(mt.__index) == 'table' and mt.__index or mt) end
  table.sort(out)
  return out
end

-- A place on the screen for a test: centre of the root, left part (the HUD is at the edges).
local function test_origin(w, h)
  local ui = ui_root()
  return math.floor((ui:Width() - w) / 2), math.floor((ui:Height() - h) / 2) - 60
end

local function healthy()
  local ok, id = pcall(function() return ui_root():Id() end)
  local hud = pcall(function() return find_uicomponent(ui_root(), 'hud_campaign', 'faction_buttons_docker') end)
  return {ui_root = ok and type(id) == 'string', hud_path = hud}
end

-- ---------------------------------------------------------------- the items ----------------------------------------------------------------
local I = {}
PP.items = I

function I.health() return healthy() end
function I.clear() return {destroyed = clear()} end
function I.select() select_malakai(); return {selected = true} end
function I.deselect() CampaignUI.ClearSelection(); return {cleared = true} end
function I.slots() return slots_info() end
function I.slot_read(a) return slot_read(a.slot) end
function I.first_empty() return {slot = first_empty(), info = slots_info()} end
-- Where our kept components are now, a frame after they were placed.
function I.rects()
  local out = {}
  for name, c in pairs(S.keep or {}) do
    local ok, r = pcall(rect, c)
    out[name] = ok and r or {err = tostring(r)}
  end
  return out
end
function I.add(a)
  local out = {}
  for _, k in ipairs(a.keys) do out[#out + 1] = {key = k, r = add(k)} end
  return {adds = out, info = slots_info()}
end
function I.order(a)
  local g = gold()
  local r = order(a.key, a.slot, a.way or 'own')
  r.gold_before = g
  return r
end
function I.check(a) return accepted(a.key, a.slot, a.gold_before) end

-- Gold and points for the whole run; the hull raised to its top so that no tier blocks an order.
function I.setup(a)
  local c = malakai()
  local mf = c:military_force()
  local before = slots()
  cm:treasury_mod(faction(), a.gold or 300000)
  pcall(function() cm:add_development_points_to_horde(mf, a.dev or 500) end)
  local hull
  if a.hull and before[1] ~= a.hull then hull = add(a.hull) end
  return {before = before, hull = a.hull, hull_add = hull, hull_now = slots()[1], info = slots_info(),
    hull_level = value(char('MilitaryForceContext.HordeContext.PrimarySlotContext.BuildingContext.BuildingLevelRecordContext.Level'))}
end

-- 0. The API surface: methods of a UIComponent, globals, sizes. Nothing is walked.
function I.api()
  local r = new_root()
  local m = members(r)
  local has = {}
  for _, k in ipairs(m) do has[k] = true end
  local want = {'TextDimensions', 'TextDimensionsForText', 'SetContextObject', 'GetContextObject', 'SimulateMouseOn', 'SimulateMouseOff', 'SimulateLClick',
    'SetOpacity', 'Opacity', 'RegisterTopMost', 'RemoveTopMost', 'SetProperty', 'GetProperty', 'Layout', 'Bounds', 'Position', 'SetDockOffset', 'CopyComponent',
    'Adopt', 'Divorce', 'SetImagePath', 'GetImagePath', 'SetTooltipText', 'SetStateText', 'GetStateText', 'ResizeTextResizingComponentToInitialSize'}
  -- by indexing too: a protected metatable lists nothing
  local function present(k)
    local ok, f = pcall(function() return r[k] end)
    return ok and f ~= nil
  end
  local flags = {}
  for _, k in ipairs(want) do flags[k] = has[k] == true or present(k) end
  local scroll = {}
  for _, k in ipairs(m) do if string.find(string.lower(k), 'scroll', 1, true) or string.find(string.lower(k), 'clip', 1, true) or string.find(string.lower(k), 'slider', 1, true) then scroll[#scroll + 1] = k end end
  for _, k in ipairs({'SetScrollPosition', 'ScrollTo', 'Scroll', 'SetScroll', 'ScrollPosition', 'SetSliderPosition', 'SetSliderValue', 'SetValue',
    'SetCurrentValue', 'SetClipChildren', 'ClipChildren', 'SetClip'}) do
    if not has[k] and present(k) then scroll[#scroll + 1] = k end
  end
  local sx, sy = core:get_screen_resolution()
  local ui = ui_root()
  clear()
  return {members = m, count = #m, flags = flags, scroll_or_clip = scroll, cco = type(cco), screen = {sx, sy}, root = {ui:Width(), ui:Height()},
    find_uicomponent = type(find_uicomponent), campaign_ui = type(CampaignUI)}
end

-- 7. TextDimensions on our own text components. a.styles: {layout, wrap}; a.strings: list. Kept for a second read after a frame.
function I.text(a)
  local r = new_root()
  local x0, y0 = 40, 60
  local rows = {}
  S.texts = {}
  local n = 0
  for si, st in ipairs(a.styles) do
    for ti, s in ipairs(a.strings) do
      if not st.only or st.only[ti] then
        n = n + 1
        local w = st.wrap or 1400
        local c = make(r, 'pp_text_' .. n, st.layout)
        size(c, w, st.height or 40)
        at(c, x0, y0 + (n % 30) * 22)
        c:SetStateText(s)
        local row = {style = st.layout, wrap = st.wrap, text = s}
        local ok, w1, h1, l1 = pcall(function() return c:TextDimensions() end)
        row.now = ok and {w1, h1, l1} or {err = tostring(w1)}
        local ok2, w2, h2, l2 = pcall(function() return c:TextDimensionsForText(s) end)
        row.for_text = ok2 and {w2, h2, l2} or {err = string.sub(tostring(w2), 1, 80)}
        local ok3, back = pcall(function() return c:GetStateText() end)
        row.same_text = ok3 and back == s
        rows[#rows + 1] = row
        S.texts[#S.texts + 1] = {c = c, row = row}
      end
    end
  end
  return {count = n, rows = rows}
end

function I.text_again()
  local rows = {}
  for _, t in ipairs(S.texts or {}) do
    local ok, w, h, l = pcall(function() return t.c:TextDimensions() end)
    rows[#rows + 1] = {style = t.row.style, text = t.row.text, later = ok and {w, h, l} or {err = tostring(w)}, bounds = {t.c:Bounds()}}
  end
  clear()
  S.texts = nil
  return {rows = rows}
end

-- 8. Time to create n components (images, the panel's commonest kind, each resized and placed, as the panel does) and to destroy them.
function I.many(a)
  local n = a.n or 1500
  local r = new_root()
  local holder = box(r, 'pp_many', 'pp_zone', 0, 0, 10, 10)
  collectgarbage('collect')
  local kb = collectgarbage('count')
  local t0, w0 = os.clock(), os.time()
  local made = 0
  for i = 1, n do
    local kind = (a.texts and i % 5 == 0) and 'pp_text_line' or 'pp_red'
    local c = make(holder, 'm' .. i, kind)
    size(c, 8, 8)
    at(c, (i % 60) * 9, math.floor(i / 60) * 9)
    if kind == 'pp_text_line' then c:SetStateText('IV') end
    made = i
  end
  local t1, w1 = os.clock(), os.time()
  local kb1 = collectgarbage('count')
  local ok = pcall(function() holder:Destroy() end)
  local t2, w2 = os.clock(), os.time()
  clear()
  return {n = n, made = made, create_cpu_s = t1 - t0, create_wall_s = w1 - w0, destroy_cpu_s = t2 - t1, destroy_wall_s = w2 - w1, destroyed = ok,
    lua_kb_before = kb, lua_kb_after = kb1, texts = a.texts and true or false}
end

-- 10. SetOpacity on nested layers, over an opaque black ground. The picture decides (tools/tests/port_probe.py samples the pixels).
function I.opacity()
  local r = new_root()
  local W, H = 560, 140
  local x0, y0 = test_origin(W, H)
  local ground = box(r, 'pp_op_ground', 'pp_black', x0, y0, W, H)
  local cases = {}
  local function case(name, x, fn)
    local holder = box(ground, 'pp_op_' .. name, 'pp_zone', x, 20, 100, 100)
    local mid = box(holder, 'pp_op_' .. name .. '_mid', 'pp_zone', 0, 0, 100, 100)
    local red = box(mid, 'pp_op_' .. name .. '_red', 'pp_red', 0, 0, 100, 100)
    local ok, err = pcall(fn, holder, mid, red)
    S.keep['op_' .. name] = red
    cases[#cases + 1] = {name = name, ok = ok, err = (not ok) and tostring(err) or nil, rect = rect(red),
      opacity = {holder = (pcall(holder.Opacity, holder) and holder:Opacity()) or 'n/a', mid = (pcall(mid.Opacity, mid) and mid:Opacity()) or 'n/a', red = (pcall(red.Opacity, red) and red:Opacity()) or 'n/a'}}
  end
  case('control', 10, function() end)
  case('self_128', 120, function(_, _, red) red:SetOpacity(128) end)
  case('parent_128', 230, function(_, mid) mid:SetOpacity(128) end)
  case('parent_128_children', 340, function(_, mid) mid:SetOpacity(128, true) end)
  case('grand_0', 450, function(holder) holder:SetOpacity(0, true) end)
  return {cases = cases, ground = rect(ground), root = {ui_root():Width(), ui_root():Height()}}
end

-- 6a. Clipping by our own container (layout pp_clip has clipchildren="true"; pp_zone is the same without it). A red child overflows by 40 on each side.
function I.clip()
  local r = new_root()
  local W, H = 600, 260
  local x0, y0 = test_origin(W, H)
  local ground = box(r, 'pp_clip_ground', 'pp_black', x0, y0, W, H)
  local out = {}
  for i, kind in ipairs({'pp_clip', 'pp_zone'}) do
    local holder = box(ground, 'pp_holder_' .. i, kind, 60 + (i - 1) * 300, 60, 180, 140)
    local red = box(holder, 'pp_child_' .. i, 'pp_red', -40, -40, 260, 220)
    out[#out + 1] = {layout = kind, holder = rect(holder), child = rect(red)}
    S.keep['child' .. i] = red
    S.keep['holder' .. i] = holder
  end
  return {cases = out, ground = rect(ground), root = {ui_root():Width(), ui_root():Height()}}
end

-- 6a, second picture: the child moved up by 120 inside the clipping holder, as a scroll by SetDockOffset would move the tree.
function I.clip_move()
  local out = {}
  for i = 1, 2 do
    local c = S.keep and S.keep['child' .. i]
    if c then
      c:SetDockOffset(-40, -160)
      out[#out + 1] = rect(c)
    end
  end
  return {moved = out}
end

-- 5. Do mouse events reach Lua for our own component. Without the real mouse: the game's SimulateMouseOn / SimulateMouseOff / SimulateLClick
-- (used by the game's own tours, data_script.pack), listeners on ComponentMouseOn, ComponentMouseOff, ComponentLClickUp.
function I.mouse_setup()
  local r = new_root()
  local x0, y0 = test_origin(300, 120)
  local b = box(r, 'pp_button', 'pp_button', x0, y0, 120, 80)
  local img = box(r, 'pp_plain', 'pp_red', x0 + 160, y0, 120, 80)
  S.keep.button, S.keep.plain = b, img
  S.events = {}
  local reg = {}
  for _, ev in ipairs({'ComponentMouseOn', 'ComponentMouseOff', 'ComponentLClickUp', 'ComponentLClickDown'}) do
    core:remove_listener(LISTENER .. ev)
    local ok, err = pcall(function()
      core:add_listener(LISTENER .. ev, ev, function(context) return string.sub(tostring(context.string), 1, 3) == 'pp_' end, function(context)
        local list = _G.mtb_pp_state.events
        list[#list + 1] = {event = ev, id = tostring(context.string), clock = os.clock()}
      end, true)
    end)
    reg[ev] = ok and true or tostring(err)
  end
  S.listening = true
  return {registered = reg, button = rect(b), state = b:CurrentState(), plain = rect(img)}
end

function I.mouse_do(a)
  local c = S.keep[a.target or 'button']
  if not c then return {err = 'no component'} end
  local before = #S.events
  local ok, err = pcall(function() c[a.call](c) end)
  return {call = a.call, target = a.target, ok = ok, err = (not ok) and tostring(err) or nil, state = c:CurrentState(), events_at_once = #S.events - before}
end

function I.mouse_read()
  local events = S.events or {}
  for _, ev in ipairs({'ComponentMouseOn', 'ComponentMouseOff', 'ComponentLClickUp', 'ComponentLClickDown'}) do core:remove_listener(LISTENER .. ev) end
  S.listening = false
  local state = S.keep.button and S.keep.button:CurrentState()
  clear()
  return {events = events, count = #events, last_state = state}
end

-- 11. A panel of the port's size on the root as it is now: min(W - 40, 1560) x min(H - 30, 870), the game's frame of the old panel,
-- the author's tiles at col / row, slot 74 and step 106, under a clipping holder. a.nodes: {id, col, row, name}.
function I.panel(a)
  local r = new_root()
  local ui = ui_root()
  local W, H = ui:Width(), ui:Height()
  local pw, ph = math.min(W - 40, 1560), math.min(H - 30, 870)
  local frame_ok, frame = pcall(make, r, 'pp_panel', 'ui/tww3_mtb/frame')
  if not frame_ok then frame = make(r, 'pp_panel', 'pp_black') end
  size(frame, pw, ph)
  frame:SetDockingPoint(5)
  frame:SetDockOffset(0, 0)
  local title_ok, title = pcall(make, frame, 'pp_title', 'pp_text_title')
  if title_ok then
    size(title, 600, 40); at(title, (pw - 600) / 2, 14); title:SetStateText(a.title or 'Дух Грунгни')
  end
  local view = box(frame, 'pp_tree', 'pp_clip', 16, 66, pw - 32 - 300, ph - 66 - 60)
  local slot, step = 74, 106
  local made = 0
  for i, node in ipairs(a.nodes or {}) do
    local tile = box(view, 'pp_tile_' .. i, (i % 3 == 0) and 'pp_green' or 'pp_red', 20 + node.col * step, 20 + node.row * step, slot, slot)
    local label = make(tile, 'pp_label', 'pp_text_line')
    size(label, 120, 20); at(label, -23, slot + 2); label:SetStateText(node.name or node.id)
    made = made + 1
  end
  local bottom = make(frame, 'pp_bottom', 'pp_text_line')
  size(bottom, pw - 40, 24); at(bottom, 20, ph - 40); bottom:SetStateText(a.bottom or 'Закажите первую постройку')
  return {root = {W, H}, screen = {core:get_screen_resolution()}, panel = {pw, ph}, frame_layout = frame_ok and 'ui/tww3_mtb/frame' or 'pp_black',
    frame = rect(frame), view = rect(view), tiles = made}
end

function I.crew_panel(a)
  if not _G.tww3_mtb_crew_ui then return {err = 'no tww3_mtb_crew_ui'} end
  if a.open then
    local blocked = tww3_mtb_crew_ui.blocked and tww3_mtb_crew_ui.blocked()
    local ok, err = pcall(tww3_mtb_crew_ui.open)
    return {blocked = blocked, opened = ok and tww3_mtb_crew_ui.is_open and tww3_mtb_crew_ui.is_open(), err = (not ok) and tostring(err) or nil}
  end
  pcall(tww3_mtb_crew_ui.close)
  return {closed = true}
end

-- 3. The cost of a building: candidate expressions on the record, through the character, on a slot being built.
function I.cost(a)
  local key, n, m = a.key, a.slot, a.built_slot
  local out = {}
  local function r(label, x) out[#out + 1] = {expr = label, r = x} end
  local at_n = n and (SLOTS .. '.At(' .. n .. ')') or nil
  local rec_exprs = {'Key', 'Level', 'CreateCost', 'BaseCreateCost', 'Cost', 'TreasuryCost', 'CreateTime', 'PrimarySlotBuildingLevelRequirement',
    'CreateCost(SelectedCharacter)', 'CreateCost(SelectedCharacter.MilitaryForceContext)', 'CreateCost(Buildings.StoredSettlementOrCharacter)',
    'CreateCost(SelectedCharacter, PlayersFaction)', 'CanAfford(SelectedCharacter)', 'CanAfford(Buildings.StoredSettlementOrCharacter)',
    'DevelopmentPointCost(SelectedCharacter)', 'HasEnoughDevelopmentPoints(SelectedCharacter)', 'IsLockedByLevel(SelectedCharacter)'}
  if at_n then
    for _, e in ipairs({'CreateTime(SelectedCharacter.' .. at_n .. ')', 'IsActiveForBuildingBrowser(SelectedCharacter.' .. at_n .. ')',
      'ResourceCostContext(SelectedCharacter.' .. at_n .. ').PooledResourceTransactionList.FirstContext.AbsoluteValue',
      'CanAffordResourceCostForSlot(SelectedCharacter.' .. at_n .. ')'}) do rec_exprs[#rec_exprs + 1] = e end
  end
  for _, e in ipairs(rec_exprs) do r('record ' .. e, rec(key, e)) end
  local D = 'DatabaseRecordContext("CcoBuildingLevelRecord", "' .. key .. '").'
  local char_exprs = {D .. 'CreateCost(this)', D .. 'CreateCost(MilitaryForceContext)', D .. 'CreateCost(MilitaryForceContext.HordeContext)',
    D .. 'CreateCost(this, FactionContext)', D .. 'CanAfford(this)', D .. 'DevelopmentPointCost(this)', D .. 'HasEnoughDevelopmentPoints(this)', D .. 'CreateCost'}
  if at_n then
    for _, e in ipairs({D .. 'CreateTime(' .. at_n .. ')', D .. 'IsActiveForBuildingBrowser(' .. at_n .. ')',
      D .. 'ResourceCostContext(' .. at_n .. ').PooledResourceTransactionList.FirstContext.AbsoluteValue', D .. 'CanAffordResourceCostForSlot(' .. at_n .. ')'}) do
      char_exprs[#char_exprs + 1] = e
    end
  end
  if m then
    local B = SLOTS .. '.At(' .. m .. ').ConstructionItemContext.'
    for _, e in ipairs({'Cost', 'TreasuryCost', 'TotalCost', 'CostValue', 'RefundAmount', 'CancelRefundAmount', 'TurnsToCompletion', 'TotalTurns',
      'BuildingLevelRecordContext.Key', 'BuildingLevelRecordContext.CreateCost(this)', 'IsPaused'}) do char_exprs[#char_exprs + 1] = B .. e end
  end
  for _, e in ipairs(char_exprs) do r('char ' .. e, char(e)) end
  -- the same through a cco object, as the game's own scripts read (episode_nagash_endgame.lua)
  local okc, obj = pcall(cco, 'CcoBuildingLevelRecord', key)
  if okc and obj then
    for _, e in ipairs({'CreateCost(SelectedCharacter)', 'CreateTime'}) do
      local ok, v = pcall(function() return obj:Call(e) end)
      r('cco ' .. e, ok and {t = type(v), v = (type(v) == 'number' or type(v) == 'string' or type(v) == 'boolean') and v or tostring(v)} or {err = tostring(v)})
    end
  else
    r('cco', {err = tostring(obj)})
  end
  return {key = key, slot = n, built_slot = m, reads = out, selected = value(read('CcoCampaignRoot', '', 'IsContextValid(SelectedCharacter)'))}
end

-- 1. Several rows of building_level_required_buildings on one level. Availability as the game's browser reads it, then one order.
local function availability(key, n)
  local out = {}
  local D = 'DatabaseRecordContext("CcoBuildingLevelRecord", "' .. key .. '").'
  local at_n = SLOTS .. '.At(' .. n .. ')'
  for _, e in ipairs({'IsActiveForBuildingBrowser(' .. at_n .. ')', 'IsContextValid(AdditionalBuildingRequirementContext)', 'AdditionalBuildingRequirementContext.Key',
    'IsLockedByLevel(this)', 'HasEnoughDevelopmentPoints(this)', 'CanAfford(this)', 'PrimarySlotBuildingLevelRequirement'}) do
    out[#out + 1] = {expr = 'char ' .. D .. e, r = char(D .. e)}
  end
  for _, e in ipairs({'IsActiveForBuildingBrowser(SelectedCharacter.' .. at_n .. ')', 'IsContextValid(AdditionalBuildingRequirementContext)',
    'AdditionalBuildingRequirementContext.Key', 'IsLockedByLevel(SelectedCharacter)'}) do
    out[#out + 1] = {expr = 'record ' .. e, r = rec(key, e)}
  end
  out[#out + 1] = {expr = 'char ' .. at_n .. '.CanUpgrade', r = char(at_n .. '.CanUpgrade')}
  out[#out + 1] = {expr = 'char ' .. at_n .. '.IsEmpty', r = char(at_n .. '.IsEmpty')}
  return out
end

-- a: key, prev (a level of the same chain that must stand in the slot) or nil, place: parents to add first, order: true to issue the order.
function I.requires(a)
  local added = {}
  for _, p in ipairs(a.place or {}) do
    if not index_of(p) then added[#added + 1] = {key = p, r = add(p)} end
  end
  if a.prev and not index_of(a.prev) then added[#added + 1] = {key = a.prev, r = add(a.prev)} end
  local n = a.prev and index_of(a.prev) or a.slot or first_empty()
  if not n then return {err = 'no slot for the order', added = added, info = slots_info()} end
  local out = {slot = n, added = added, reads = availability(a.key, n), gold_before = gold()}
  local present = {}
  for _, k in ipairs(a.parents or {}) do present[k] = index_of(k) ~= nil end
  out.parents_present = present
  if a.order then out.ordered = order(a.key, n, 'own') end
  return out
end

-- 6b (risky: a template of the game in our layout). The game's list template: our boxes in its list_box, what its slider does.
function I.listview(a)
  local r = new_root()
  local x0, y0 = test_origin(360, 300)
  local ok, lv = pcall(make, r, 'pp_listview', 'ui/templates/listview')
  if not ok then return {err = 'create: ' .. tostring(lv)} end
  size(lv, 360, 300)
  at(lv, x0, y0)
  local clip = find_uicomponent(lv, 'list_clip')
  local list = find_uicomponent(lv, 'list_clip', 'list_box') or find_uicomponent(lv, 'list_box')
  local slider = find_uicomponent(lv, 'vslider')
  if not list then return {err = 'no list_box in the template', lv = rect(lv)} end
  local before = rect(list)
  for i = 1, a.n or 30 do
    box(list, 'pp_row_' .. i, (i % 2 == 0) and 'pp_red' or 'pp_green', 0, 0, 320, 40)
  end
  local layout_ok, layout_err = pcall(function() list:Layout() end)
  S.keep.list, S.keep.slider, S.keep.lv = list, slider, lv
  return {lv = rect(lv), clip = clip and rect(clip), list_before = before, list_after = rect(list), layout = layout_ok or tostring(layout_err),
    slider = slider and {rect = rect(slider), visible = slider:Visible(), from_root = slider:VisibleFromRoot()} or false}
end

function I.listview_scroll(a)
  local list, slider = S.keep.list, S.keep.slider
  if not list then return {err = 'no list'} end
  local tried = {}
  for _, name in ipairs(a.methods or {}) do
    for _, target in ipairs({{'list', list}, {'slider', slider}}) do
      if target[2] then
        local ok, res = pcall(function() return target[2][name](target[2], a.amount or 200) end)
        tried[#tried + 1] = {method = name, on = target[1], ok = ok, res = tostring(res)}
      end
    end
  end
  local ok = pcall(function() list:SetDockOffset(0, -200) end)
  return {tried = tried, dock_offset = ok, list = rect(list), slider = slider and slider:Visible()}
end

-- 9 (risky: a template with the game's bindings). ui/templates/building_frame with SetContextObject(cco('CcoBuildingLevelRecord', key)).
function I.frame(a)
  local r = new_root()
  local x0, y0 = test_origin(300, 200)
  local out = {}
  local ok, bf = pcall(make, r, 'pp_building_frame', 'ui/templates/building_frame')
  if not ok then return {err = 'create: ' .. tostring(bf)} end
  at(bf, x0, y0)
  local okc, obj = pcall(cco, 'CcoBuildingLevelRecord', a.key)
  out.cco = okc and tostring(obj) or ('ERR ' .. tostring(obj))
  local oks, err = pcall(function() bf:SetContextObject(obj) end)
  out.set = oks and true or tostring(err)
  S.keep.frame = bf
  out.rect = rect(bf)
  -- a second one under a holder that carries the slot's context, as the browser nests them
  if a.slot then
    local okh, holder = pcall(box, r, 'pp_slot_holder', 'pp_zone', x0 + 160, y0, 120, 120)
    if okh then
      local okq, slot_obj = pcall(function() return cco('CcoCampaignCharacter', cqi()):Call(SLOTS .. '.At(' .. a.slot .. ')') end)
      out.slot_cco = okq and tostring(slot_obj) or ('ERR ' .. tostring(slot_obj))
      local okh2, e2 = pcall(function() holder:SetContextObject(slot_obj) end)
      out.slot_set = okh2 and true or tostring(e2)
      local okb, bf2 = pcall(make, holder, 'pp_building_frame_2', 'ui/templates/building_frame')
      if okb then
        local okt, e3 = pcall(function() bf2:SetContextObject(obj) end)
        out.second_set = okt and true or tostring(e3)
        S.keep.frame2 = bf2
      else
        out.second_set = 'create: ' .. tostring(bf2)
      end
    end
  end
  return out
end

function I.frame_read()
  local out = {}
  for _, name in ipairs({'frame', 'frame2'}) do
    local bf = S.keep and S.keep[name]
    if bf then
      local o = {state = bf:CurrentState(), visible = bf:Visible(), rect = rect(bf)}
      for _, path in ipairs({{'known_parent', 'building_level'}, {'known_parent', 'turns_center'}, {'known_parent', 'mouseover_parent', 'upgrade_box', 'cost_list', 'building_cost'},
        {'known_parent', 'dev_points', 'dy_num_points_required'}, {'square_building_button'}, {'circular_building_button'}}) do
        local c = find_uicomponent(bf, unpack(path))
        local label = table.concat(path, '/')
        if c then
          local okt, text = pcall(function() return c:GetStateText() end)
          local oki, img = pcall(function() return c:GetImagePath() end)
          o[label] = {text = okt and text or nil, image = oki and img or nil, visible = c:Visible(), state = c:CurrentState()}
        else
          o[label] = 'absent'
        end
      end
      local okg, ctxo = pcall(function() return bf:GetContextObject('CcoBuildingLevelRecord') end)
      o.context_back = okg and tostring(ctxo) or ('ERR ' .. tostring(ctxo))
      out[name] = o
    end
  end
  return out
end

-- 12. The order of campaign events around a turn end, a cancel, a dismantle. Every candidate event of events.lua is listened to; each firing
-- gets a sequence number, os.clock(), what its context says and the state of the watched slots at that moment. Turn events of other
-- factions and characters are only counted (they fire for the whole world).
local EVENTS = {'FactionTurnEnd', 'FactionTurnStart', 'FactionBeginTurnPhaseNormal', 'CharacterTurnEnd', 'CharacterTurnStart', 'SlotTurnStart',
  'MilitaryForceBuildingCompleteEvent', 'MilitaryForceBuildingCancelled', 'MilitaryForceDevelopmentPointChange', 'CharacterHordeBuildingDemolished',
  'BuildingCompleted', 'BuildingCancelled', 'BuildingDemolished', 'BuildingConstructionIssued', 'BuildingConstructionIssuedByPlayer',
  'ForeignSlotBuildingCompleteEvent', 'FactionHordeStatusChange', 'SlotOpens', 'WorldStartRound'}
local WORLDWIDE = {FactionTurnEnd = true, FactionTurnStart = true, FactionBeginTurnPhaseNormal = true, CharacterTurnEnd = true, CharacterTurnStart = true,
  SlotTurnStart = true, WorldStartRound = true}

local function short(v)
  if v == nil then return nil end
  local t = type(v)
  if t == 'string' or t == 'number' or t == 'boolean' then return v end
  for _, m in ipairs({'name', 'key', 'command_queue_index', 'building'}) do
    local ok, x = pcall(function() return v[m](v) end)
    if ok and x ~= nil and type(x) ~= 'userdata' and type(x) ~= 'table' then return m .. ':' .. tostring(x) end
  end
  return tostring(v)
end

local function describe(context)
  local out = {}
  local ok, s = pcall(function() return context.string end)
  if ok and s ~= nil then out.string = tostring(s) end
  for _, m in ipairs({'faction', 'character', 'building', 'military_force', 'garrison_residence', 'slot', 'region'}) do
    local okm, v = pcall(function() return context[m](context) end)
    if okm and v ~= nil then out[m] = short(v) end
  end
  return out
end

local function watched()
  local out = {}
  local list = slot_list()
  for _, n in ipairs(S.watch or {}) do
    local w = {slot = n}
    if n < list:num_items() then
      local it = list:item_at(n)
      w.model = it:has_building() and it:building() or ''
    end
    local ok, r = pcall(slot_read, n)
    w.cco = ok and r or {err = tostring(r)}
    out[#out + 1] = w
  end
  return out
end

function I.events_on(a)
  S.seq, S.log, S.noise, S.watch = 0, {}, {}, a.watch or {}
  local me_faction, me_cqi = faction(), cqi()
  local reg = {}
  for _, ev in ipairs(EVENTS) do
    core:remove_listener(LISTENER .. 'ev_' .. ev)
    local ok, err = pcall(function()
      core:add_listener(LISTENER .. 'ev_' .. ev, ev, true, function(context)
        local st = _G.mtb_pp_state
        local d = describe(context)
        local ours = string.find(tostring(d.faction), me_faction, 1, true) or string.find(tostring(d.character), me_cqi, 1, true)
          or string.find(tostring(d.military_force), me_cqi, 1, true)
        if WORLDWIDE[ev] and not ours then
          st.noise[ev] = (st.noise[ev] or 0) + 1
          return
        end
        st.seq = st.seq + 1
        local rec = {seq = st.seq, clock = os.clock(), event = ev, context = d}
        local okt, turn = pcall(function() return cm:turn_number() end)
        rec.turn = okt and turn or nil
        local okw, w = pcall(watched)
        rec.slots = okw and w or {err = tostring(w)}
        st.log[#st.log + 1] = rec
      end, true)
    end)
    reg[ev] = ok and true or tostring(err)
  end
  return {registered = reg, watch = S.watch, turn = cm:turn_number(), slots = watched()}
end

function I.events_watch(a) S.watch = a.watch or S.watch; return {watch = S.watch, slots = watched()} end
function I.events_mark(a)
  S.seq = (S.seq or 0) + 1
  S.log = S.log or {}
  S.log[#S.log + 1] = {seq = S.seq, clock = os.clock(), event = 'MARK ' .. tostring(a.text), turn = cm:turn_number(), slots = watched()}
  return {seq = S.seq}
end
function I.events_read(a)
  local out, from = {}, a.from or 0
  for _, r in ipairs(S.log or {}) do if r.seq > from then out[#out + 1] = r end end
  return {log = out, noise = S.noise, seq = S.seq or 0, turn = cm:turn_number(), slots = watched()}
end
function I.events_off()
  for _, ev in ipairs(EVENTS) do core:remove_listener(LISTENER .. 'ev_' .. ev) end
  return {off = #EVENTS}
end

-- The cancel the mod uses: the same order command once more on a slot being built ([игра: 191708], full refund).
function I.cancel(a)
  local g = gold()
  local before = slot_read(a.slot)
  local r = order(a.key, a.slot, 'own')
  r.gold_before, r.before = g, before
  return r
end

function I.dismantle(a)
  local base = SLOTS .. '.At(' .. a.slot .. ')'
  local before = {can = value(char(base .. '.CanDismantle')), model = slots()[a.slot + 1]}
  local ok, err = pcall(common.call_context_command, 'CcoCampaignCharacter', cqi(), base .. '.Dismantle')
  return {ok = ok, err = (not ok) and tostring(err) or nil, before = before, dismantling = value(char(base .. '.IsDismantling')), model_after = slots()[a.slot + 1]}
end

function I.avail(a)
  local n = a.slot or first_empty()
  if not n then return {err = 'no slot to read against', info = slots_info()} end
  return {slot = n, reads = availability(a.key, n), present = {r1 = a.r1 and index_of(a.r1), r2 = a.r2 and index_of(a.r2)}, slots = slots()}
end

-- 14. The effect list of a level as the context reads it (the info panel's own list is filled by C++: CampaignEffectsListTooltip).
function I.effects(a)
  local out = {}
  for _, key in ipairs(a.keys or {}) do
    local o = {key = key, size = value(rec(key, 'EffectList.Size')), nonzero = value(rec(key, 'EffectList.Filter((x) => x.Value != 0).Size')), rows = {}}
    local n = tonumber(o.size) or 0
    for i = 0, math.min(n, 24) - 1 do
      local row = {}
      for _, f in ipairs({'Key', 'Value', 'LocalisedText', 'Description', 'IconPath', 'IsPositive', 'Scope', 'EffectScopeContext.Key'}) do
        row[f] = value(rec(key, 'EffectList.At(' .. i .. ').' .. f))
      end
      o.rows[#o.rows + 1] = row
    end
    out[#out + 1] = o
  end
  local texts = {}
  for _, e in ipairs(a.effects or {}) do
    local ok, t = pcall(common.get_localised_string, 'effects_description_' .. e)
    texts[e] = ok and t or ('ERR ' .. tostring(t))
  end
  return {levels = out, texts = texts}
end

-- ---------------------------------------------------------------- the call ----------------------------------------------------------------
function PP.run(name, args)
  local fn = I[name]
  local t0 = os.clock()
  local out
  if not fn then
    out = {ok = false, err = 'no item ' .. tostring(name)}
  else
    local ok, res = pcall(fn, args or {})
    out = {ok = ok, data = ok and res or nil, err = (not ok) and tostring(res) or nil}
  end
  out.item = name
  out.cpu_ms = math.floor((os.clock() - t0) * 1000 + 0.5)
  local text = J(out)
  if mtb and mtb.log then pcall(mtb.log, 'port_probe', string.sub(text, 1, 6000)) end
  return text
end

return 'ready'
