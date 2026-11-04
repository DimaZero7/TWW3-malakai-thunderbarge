-- Real orders through the game's own command, the one the building browser's cards issue. Malakai must be selected (P.select_malakai).
-- mtb_build: building levels without the prefix, comma separated, each in the first free side slot, or on top of the chain's slot
-- when a lower level stands there. mtb_dev: development points added first by script.
-- mtb_dismantle: one building without the prefix: its slot is dismantled.
local build, dev, dismantle = mtb_build, mtb_dev, mtb_dismantle
mtb_build, mtb_dev, mtb_dismantle = nil, nil, nil      -- the environment outlives this command
local PREFIX = 'wh3_dlc25_dwarf_spirit_of_grungni_'
local SLOTS = 'SelectedCharacter.MilitaryForceContext.HordeContext.BuildingSlotList'
local out = {}
local function ctx(expr) return common.get_context_value('CcoCampaignCharacter', P.cqi(), expr) end
P.select_malakai()
local mf = P.malakai():military_force()
if dev then cm:add_development_points_to_horde(mf, tonumber(dev)) end
local list = mf:horde_details():military_force_slot_list()
local function index_of(key)
  for i = 0, list:num_items() - 1 do
    if list:item_at(i):has_building() and list:item_at(i):building() == key then return i end
  end
end
local function first_empty()
  for i = 1, list:num_items() - 1 do
    if not list:item_at(i):has_building() and not out['used' .. i] then return i end
  end
end
if build then
  for short in string.gmatch(build, '[^,]+') do
    local chain, level = string.match(short, '^(.*)_(%d+)$')
    local slot = index_of(PREFIX .. chain .. '_' .. (tonumber(level) - 1)) or (chain == 'airship_hull' and 0) or first_empty()
    out['used' .. slot] = true
    local ok, err = pcall(common.call_context_command, 'CcoBuildingLevelRecord', PREFIX .. short,
      'IssueCommandForBuildingBrowser(' .. SLOTS .. '.At(' .. slot .. '))')
    out[short] = 'slot ' .. slot .. ' ' .. tostring(ok) .. (ok and '' or tostring(err))
  end
end
if dismantle then
  local slot = index_of(PREFIX .. dismantle)
  if not slot then return 'no building ' .. dismantle end
  local ok, err = pcall(common.call_context_command, 'CcoCampaignCharacter', P.cqi(), 'MilitaryForceContext.HordeContext.BuildingSlotList.At(' .. slot .. ').Dismantle')
  out.dismantle = tostring(ok) .. (ok and '' or tostring(err))
  out.dismantling = tostring(ctx('MilitaryForceContext.HordeContext.BuildingSlotList.At(' .. slot .. ').IsDismantling'))
end
out.gold = cm:get_faction(P.malakai():faction():name()):treasury()
out.dev = ctx('MilitaryForceContext.HordeContext.DevelopmentPoints')
return out
