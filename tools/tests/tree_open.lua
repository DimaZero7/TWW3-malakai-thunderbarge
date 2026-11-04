-- The game's tree of an empty slot of the horde, as the mouse opens it. mtb_step: slot (the categories), set (the tree of mtb_set), read (what is on it), off.
local step, set_name = mtb_step, mtb_set or 'compartments'
mtb_step, mtb_set = nil, nil
local list = mtb.find('horde_slot_list', true)
if not list then return 'no slot list' end
local slot
for i = 1, list:ChildCount() - 1 do
  local s = UIComponent(list:Find(i))
  if s:CurrentState() == 'empty' then slot = s; break end
end
if not slot then return 'no empty slot' end
local cat = find_uicomponent(slot, 'building_categories_popup')
if step == 'slot' then
  slot:SimulateMouseOn()
  return 'hover ' .. slot:Id()
end
if step == 'set' then
  local icon = find_uicomponent(cat, 'category_list', 'CcoBuildingSetRecordwh3_dlc25_set_dwarf_spirit_of_grungni_' .. set_name)
  if not icon then return 'no set ' .. set_name end
  icon:SimulateMouseOn()
  return 'set ' .. tostring(cat:Visible())
end
if step == 'click' then
  local icon = find_uicomponent(cat, 'category_list', 'CcoBuildingSetRecordwh3_dlc25_set_dwarf_spirit_of_grungni_' .. set_name)
  icon:SimulateLClick()
  return 'clicked'
end
if step == 'off' then
  slot:SimulateMouseOff()
  return 'off'
end
local cards = tww3_mtb_crew_ui.decorate_tree(slot)
local pop = find_uicomponent(slot, 'building_construction_popup')
local out = {new_cards = cards, popup = tostring(pop ~= nil)}
local tiles, on = 0, 0
local missing = {}
for _, short in ipairs({'crew_weapons_1', 'crew_weapons_2', 'crew_weapons_3', 'mtb_guns_2', 'mtb_guns_3', 'mtb_guns_4', 'mtb_nest_2', 'mtb_nest_3', 'mtb_hatches_2', 'mtb_hatches_3', 'mtb_harpoon_1', 'mtb_torpedoes_1'}) do
  local tile = pop and find_uicomponent(pop, 'wh3_dlc25_dwarf_spirit_of_grungni_' .. short)
  if tile then
    tiles = tiles + 1
    if find_uicomponent(tile, 'mtb_crew_card_1') then on = on + 1 else missing[#missing + 1] = short end
  else
    missing[#missing + 1] = 'no tile ' .. short
  end
end
out.tiles = tiles
out.with_card = on
out.missing = table.concat(missing, ',')
return mtb.dump(out)
