-- The panels for the pictures of a new campaign. mtb_tree: open_tab, open_slot (the first empty side slot's list), close_slot, skills, close_panel.
if mtb_tree == 'open_tab' then
  P.select_malakai()
  return mtb.click('tab_horde_buildings')
end
if mtb_tree == 'open_slot' or mtb_tree == 'close_slot' then
  local list = mtb.find('horde_slot_list', true)
  if not list then return 'no slot list' end
  local seen = 0
  for i = 0, list:ChildCount() - 1 do
    local slot = UIComponent(list:Find(i))
    if string.find(slot:Id(), '^CcoCampaignBuildingSlot') then
      seen = seen + 1
      if seen == 2 then
        slot:SimulateLClick()
        return 'clicked ' .. slot:Id()
      end
    end
  end
  return 'no second slot'
end
if mtb_tree == 'open_panel' then
  P.select_malakai()
  return mtb.click('button_general')
end
if mtb_tree == 'skills' then
  local panel = mtb.find('character_details_panel', true)
  if not panel then return 'no panel' end
  local b = mtb.find('TabSkills', true, panel) or mtb.find('tab_skills', true, panel) or mtb.find('skills_tab', true, panel) or mtb.find('button_stats_tab_skills', true, panel)
  if not b then return 'no skills tab' end
  b:SimulateLClick()
  return 'clicked ' .. b:Id()
end
if mtb_tree == 'skill_nodes' then
  local found = {}
  local function walk(u)
    local id = u:Id()
    if string.find(id, 'deathblow') or string.find(id, 'blade_shield') or string.find(id, 'hard_to_hit') then found[#found + 1] = id end
    for i = 0, u:ChildCount() - 1 do walk(UIComponent(u:Find(i))) end
  end
  walk(mtb.find('character_details_panel', true))
  return table.concat(found, ' ')
end
if mtb_tree == 'close_panel' then
  return mtb.click('button_ok')
end
return 'unknown ' .. tostring(mtb_tree)
