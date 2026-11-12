-- Probes for docs/design/panel-upgrades-proposal.md, section 8. Helpers only: tools/tests/panel_probe.py calls them. Sets _G.mtb_z. Nothing of the mod is changed.
local Z = {}
_G.mtb_z = Z
local PREFIX = 'wh3_dlc25_dwarf_spirit_of_grungni_'
local FACTION = 'wh3_dlc25_dwf_malakai'
local SLOTS = 'MilitaryForceContext.HordeContext.BuildingSlotList'

local function P() return _G.mtb_prog end
-- The game's own search by name. A walk in Lua over the UI after the horde's tab was open and hidden breaks every binding for good (run 20261104-191037).
local function F(name) local c = find_uicomponent(core:get_ui_root(), name); return c or nil end
Z.F = F
function Z.healthy() return type(core:get_ui_root():Id()) == 'string' end
function Z.cqi() return P().cqi() end
function Z.gold() return cm:get_faction(FACTION):treasury() end

function Z.try(fn, ...)
  local ok, v = pcall(fn, ...)
  if ok then return v end
  return 'ERR ' .. tostring(v)
end

function Z.ctx(object, id, expr)
  local ok, v = pcall(common.get_context_value, object, id, expr)
  if ok then return tostring(v) end
  return 'ERR ' .. tostring(v):sub(1, 60)
end

function Z.char(expr) return Z.ctx('CcoCampaignCharacter', Z.cqi(), expr) end

-- ---- the tab
function Z.tab()
  return find_uicomponent(core:get_ui_root(), 'units_panel', 'main_units_panel') and F('tab_horde_buildings') or F('tab_horde_buildings')
end

function Z.tab_state()
  local t = F('tab_horde_buildings')
  if not t then return 'no tab' end
  local list = F('horde_slot_list')
  list = list and list:VisibleFromRoot() and list or nil
  return 'visible=' .. tostring(t:Visible()) .. ' fromroot=' .. tostring(t:VisibleFromRoot()) .. ' state=' .. tostring(t:CurrentState()) .. ' slots_on_screen=' .. tostring(list ~= nil)
end

function Z.hide_tab()
  local t = F('tab_horde_buildings')
  if not t then return 'no tab' end
  t:SetVisible(false)
  return Z.tab_state()
end

-- Hides again whenever it comes back, counts how often that was needed.
function Z.watch_tab()
  _G.mtb_tab_shown = 0
  core:get_tm():remove_real_callback('mtb_probe_tab')
  core:get_tm():repeat_real_callback(function()
    local t = F('tab_horde_buildings')
    if t and t:Visible() then
      _G.mtb_tab_shown = _G.mtb_tab_shown + 1
      t:SetVisible(false)
    end
  end, 100, 'mtb_probe_tab')
  return 'watching'
end

function Z.unwatch_tab()
  core:get_tm():remove_real_callback('mtb_probe_tab')
  return 'came back ' .. tostring(_G.mtb_tab_shown) .. ' times'
end

function Z.select() return P().select_malakai() end
function Z.deselect() CampaignUI.ClearSelection(); return 'cleared' end

function Z.siblings()
  local t = F('tab_horde_buildings')
  if not t then return 'no tab' end
  local p = UIComponent(t:Parent())
  local o = {p:Id()}
  for i = 0, p:ChildCount() - 1 do
    local c = UIComponent(p:Find(i))
    o[#o + 1] = c:Id() .. ':' .. tostring(c:Visible()) .. ':' .. tostring(c:CurrentState())
  end
  return table.concat(o, ' ')
end

function Z.click_bar()
  local bar = F('city_info_bar_horde')
  if not bar then return 'no bar found' end
  local vis = tostring(bar:VisibleFromRoot())
  bar:SimulateLClick()
  local info = find_uicomponent(bar, 'info_bar')
  if info then info:SimulateLClick() end
  local name = find_uicomponent(bar, 'dy_name')
  if name then name:SimulateLClick() end
  return 'clicked ' .. bar:Id() .. ' visible ' .. vis .. ' info ' .. tostring(info ~= false and info ~= nil)
end

-- ---- orders
function Z.slot_index(short)
  local list = P().malakai():military_force():horde_details():military_force_slot_list()
  for i = 0, list:num_items() - 1 do
    if list:item_at(i):has_building() and list:item_at(i):building() == PREFIX .. short then return i end
  end
end

function Z.first_empty()
  local list = P().malakai():military_force():horde_details():military_force_slot_list()
  for i = 1, list:num_items() - 1 do
    if not list:item_at(i):has_building() then return i end
  end
end

function Z.slot_read(n)
  local base = SLOTS .. '.At(' .. n .. ')'
  return 'empty=' .. Z.char(base .. '.IsEmpty') .. ' building=' .. Z.char(base .. '.BuildingContext.BuildingLevelRecordContext.Key') ..
    ' item=' .. Z.char('IsContextValid(' .. base .. '.ConstructionItemContext)') .. ' turns=' .. Z.char(base .. '.ConstructionItemContext.TurnsToCompletion') ..
    ' item_level=' .. Z.char(base .. '.ConstructionItemContext.BuildingLevelContext.Key')
end

-- way: selected: the stock expression; own: no selection needed, the record found from the character's own context
function Z.order(short, n, way)
  local key = PREFIX .. short
  if way == 'selected' then
    return tostring(pcall(common.call_context_command, 'CcoBuildingLevelRecord', key, 'IssueCommandForBuildingBrowser(SelectedCharacter.' .. SLOTS .. '.At(' .. n .. '))'))
  end
  return tostring(pcall(common.call_context_command, 'CcoCampaignCharacter', Z.cqi(),
    'DatabaseRecordContext("CcoBuildingLevelRecord", "' .. key .. '").IssueCommandForBuildingBrowser(' .. SLOTS .. '.At(' .. n .. '))'))
end

function Z.cancel(n)
  local base = SLOTS .. '.At(' .. n .. ')'
  local a = tostring(pcall(common.call_context_command, 'CcoCampaignCharacter', Z.cqi(), base .. '.ConstructionItemContext.Cancel'))
  return a
end

function Z.give(gold, dev)
  cm:treasury_mod(FACTION, gold)
  cm:add_development_points_to_horde(P().malakai():military_force(), dev)
  return Z.gold()
end

function Z.reads(short, n)
  local key = PREFIX .. short
  local out = {}
  local function rec(expr) out[#out + 1] = expr .. ' = ' .. Z.ctx('CcoBuildingLevelRecord', key, expr) end
  local c = 'CharacterContext'
  rec('Key'); rec('Level'); rec('CreateTime'); rec('ConstructionTime'); rec('TurnsToConstruct'); rec('BaseCreateCost')
  for _, who in ipairs({'SelectedCharacter', 'Buildings.StoredSettlementOrCharacter'}) do
    rec('DevelopmentPointCost(' .. who .. ')')
    rec('HasEnoughDevelopmentPoints(' .. who .. ')')
    rec('CreateCost(' .. who .. ').PooledResourceTransactionList.FirstContext.AbsoluteValue')
    rec('CreateCost(' .. who .. ').TreasuryCost')
    rec('CreateCost(' .. who .. ').Cost')
    rec('CreateCost(' .. who .. ').TotalValue')
    rec('CreateTurns(' .. who .. ')')
    rec('ConstructionTime(' .. who .. ')')
  end
  rec('IsActiveForBuildingBrowser(SelectedCharacter.' .. SLOTS .. '.At(' .. n .. '))')
  local char = {SLOTS .. '.At(' .. n .. ').CanUpgrade', SLOTS .. '.At(' .. n .. ').CanDismantle', SLOTS .. '.At(' .. n .. ').IsEmpty', 'MilitaryForceContext.HordeContext.DevelopmentPoints',
    SLOTS .. '.At(' .. n .. ').BuildingContext.DismantleRefundAmount', 'MilitaryForceContext.HordeContext.GrowthPoints'}
  for _, e in ipairs(char) do out[#out + 1] = 'char ' .. e .. ' = ' .. Z.char(e) end
  return table.concat(out, '\n')
end

-- ---- units
function Z.units()
  local list = P().malakai():military_force():unit_list()
  local o = {}
  for i = 0, list:num_items() - 1 do o[#o + 1] = list:item_at(i):unit_key() end
  return list:num_items() .. ': ' .. table.concat(o, ',')
end

function Z.listen_units()
  _G.mtb_created = _G.mtb_created or {}
  core:remove_listener('mtb_probe_unit')
  core:add_listener('mtb_probe_unit', 'UnitCreated', true, function(context)
    local ok, k = pcall(function() return context:unit():unit_key() end)
    _G.mtb_created[#_G.mtb_created + 1] = tostring(k)
  end, true)
  return 'listening'
end

function Z.grant(unit)
  local c = P().malakai()
  local g0 = Z.gold()
  local ok, ret = pcall(function() return cm:grant_unit_to_character(cm:char_lookup_str(c), unit) end)
  return 'ok=' .. tostring(ok) .. ' ret=' .. tostring(ret) .. ' gold ' .. g0 .. ' -> ' .. Z.gold() .. ' units ' .. Z.units()
end

function Z.fleet()
  return 'stance=' .. tostring(P().malakai():military_force():active_stance()) .. ' force_type=' .. tostring(P().malakai():military_force():force_type():key()) ..
    ' upkeep=' .. Z.try(function() return P().malakai():military_force():upkeep() end) .. ' created=' .. table.concat(_G.mtb_created or {}, ',')
end

function Z.first_unit_strength(key)
  local list = P().malakai():military_force():unit_list()
  for i = list:num_items() - 1, 0, -1 do
    local u = list:item_at(i)
    if u:unit_key() == key then return key .. ' men ' .. tostring(u:percentage_proportion_of_full_strength()) .. '% upkeep ' .. Z.try(function() return u:get_unit_custom_battle_cost() end) end
  end
  return 'none'
end

function Z.can(unit)
  return Z.try(function() return tostring(P().malakai():military_force():can_recruit_unit(unit)) end)
end

function Z.recruit_button()
  local b = F('button_recruitment')
  if not b then return 'no button' end
  return b:CurrentState() .. ' visible=' .. tostring(b:Visible()) .. ' root=' .. tostring(b:VisibleFromRoot())
end

function Z.lock_recruit()
  local b = F('button_recruitment')
  if not b then return 'no button' end
  b:SetState('inactive')
  return b:CurrentState()
end

function Z.open_recruit()
  local b = F('button_recruitment')
  if not b then return 'no button' end
  b:SimulateLClick()
  return b:CurrentState()
end

-- what the recruitment panel lists now: {section = ids}
function Z.recruit_list()
  local out = {}
  local panel = F('recruitment_listbox') or F('recruitment_options') or F('recruitment_docker')
  if panel and not panel:VisibleFromRoot() then panel = nil end
  if not panel then return 'no recruitment panel on screen' end
  local function walk(u, depth)
    local id = u:Id()
    if string.find(id, '_recruitable', 1, true) or string.find(id, 'CcoMainUnitRecord', 1, true) or string.find(id, 'QueuedLandUnit', 1, true) or string.find(id, 'wh_', 1, true) == 1 then
      out[#out + 1] = id .. ':' .. tostring(u:CurrentState())
    end
    if depth < 9 then
      for i = 0, u:ChildCount() - 1 do walk(UIComponent(u:Find(i)), depth + 1) end
    end
  end
  walk(panel, 0)
  return panel:Id() .. ' [' .. #out .. '] ' .. table.concat(out, ' ')
end

function Z.click_recruit(fragment)
  local panel = F('recruitment_listbox') or F('recruitment_options') or F('recruitment_docker')
  if panel and not panel:VisibleFromRoot() then panel = nil end
  if not panel then return 'no panel' end
  local hit
  local function walk(u, depth)
    if hit then return end
    local id = u:Id()
    if string.find(id, fragment, 1, true) and (string.find(id, 'recruitable', 1, true) or string.find(id, 'CcoMainUnitRecord', 1, true)) then hit = u; return end
    if depth < 9 then
      for i = 0, u:ChildCount() - 1 do walk(UIComponent(u:Find(i)), depth + 1) end
    end
  end
  walk(panel, 0)
  if not hit then return 'no card ' .. fragment end
  local g0 = Z.gold()
  hit:SimulateLClick()
  return 'clicked ' .. hit:Id() .. ' state ' .. hit:CurrentState() .. ' gold ' .. g0 .. ' -> ' .. Z.gold()
end

function Z.recruit_by_cco(unit)
  local a = tostring(pcall(common.call_context_command, 'CcoMainUnitRecord', unit, 'Recruit'))
  local b = tostring(pcall(common.call_context_command, 'CcoCampaignCharacter', Z.cqi(), 'MilitaryForceContext.Recruit("' .. unit .. '")'))
  return 'record.Recruit ' .. a .. ' | force.Recruit ' .. b .. ' gold ' .. Z.gold()
end

function Z.queue()
  return Z.char('MilitaryForceContext.UnitQueueList.Size') .. ' / ' .. Z.char('MilitaryForceContext.QueuedUnitList.Size') .. ' / ' .. Z.char('MilitaryForceContext.RecruitmentQueueList.Size')
end

function Z.home_settlement()
  local f = cm:get_faction(FACTION)
  local rl = f:region_list()
  local o = {}
  for i = 0, rl:num_items() - 1 do o[#o + 1] = rl:item_at(i):name() .. '@' .. rl:item_at(i):settlement():logical_position_x() .. ',' .. rl:item_at(i):settlement():logical_position_y() end
  return rl:num_items() .. ' ' .. table.concat(o, ' ')
end

function Z.go_home()
  local rl = cm:get_faction(FACTION):region_list()
  if rl:num_items() == 0 then return 'no region' end
  local s = rl:item_at(0):settlement()
  local c = P().malakai()
  local x, y = cm:find_valid_spawn_location_for_character_from_settlement(FACTION, s:region():name(), false, true, 3)
  cm:teleport_to(cm:char_lookup_str(c), x, y)
  return 'to ' .. s:region():name() .. ' ' .. x .. ',' .. y
end

function Z.where()
  local c = P().malakai()
  return 'region=' .. Z.try(function() return c:region():name() end) .. ' owner=' .. Z.try(function() return c:region():owning_faction():name() end) ..
    ' garrison=' .. Z.try(function() return tostring(c:in_settlement()) end) .. ' at ' .. c:logical_position_x() .. ',' .. c:logical_position_y()
end

-- a second general of the faction, for what the lock does to others
function Z.other_lord()
  local rl = cm:get_faction(FACTION):region_list()
  local region = rl:num_items() > 0 and rl:item_at(0):name() or P().malakai():region():name()
  local c = P().malakai()
  local x, y = cm:find_valid_spawn_location_for_character_from_character(FACTION, 'character_cqi:' .. c:command_queue_index(), true, 8)
  cm:create_force(FACTION, 'wh_main_dwf_inf_dwarf_warrior_0', region, x, y, true, function(cqi) _G.mtb_other = cqi end)
  return 'asked at ' .. x .. ',' .. y
end

function Z.select_other()
  if not _G.mtb_other then return 'no other lord yet' end
  CampaignUI.ClearSelection()
  common.call_context_command('CcoCampaignCharacter', tostring(_G.mtb_other), 'SelectAndZoom(false)')
  return 'selected ' .. tostring(_G.mtb_other)
end

function Z.ui_lock(on)
  return Z.try(function() cm:override_ui('disable_recruit_units', on); return 'override ' .. tostring(on) end)
end

-- ---- opacity on a nested layer of the crew panel
function Z.opacity(value)
  local layer = F('occ_rifles') or F('occ_deck')
  if not layer then return 'no layer on screen' end
  local before = Z.try(function() return layer:Opacity() end)
  local a = Z.try(function() layer:SetOpacity(value); return 'SetOpacity(v)' end)
  local b = Z.try(function() layer:SetOpacity(value, true); return 'SetOpacity(v, true)' end)
  return layer:Id() .. ' parent ' .. UIComponent(layer:Parent()):Id() .. ' before ' .. tostring(before) .. ' | ' .. tostring(a) .. ' | ' .. tostring(b) .. ' | now ' .. tostring(Z.try(function() return layer:Opacity() end))
end

-- ---- plan B
function Z.to_army()
  local c = P().malakai()
  local before = Z.fleet()
  local r = Z.try(function() cm:convert_force_to_type(c:military_force(), 'ARMY'); return 'converted' end)
  return before .. ' => ' .. tostring(r)
end

function Z.wound(turns)
  local c = P().malakai()
  return Z.try(function() cm:wound_character(cm:char_lookup_str(c), turns); return 'wounded ' .. turns end)
end

function Z.state()
  local c = P().malakai()
  local has = c:has_military_force()
  return 'wounded=' .. Z.try(function() return tostring(c:is_wounded()) end) .. ' force=' .. tostring(has) .. (has and (' ' .. Z.fleet() .. ' units ' .. Z.units()) or '') .. ' slots=' .. P().slots()
end

return 'ready'
