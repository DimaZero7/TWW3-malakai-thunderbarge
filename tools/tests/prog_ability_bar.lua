-- In a battle: selects the lord's card, then lists the visible ability buttons.
local cards = mtb.find('review_panel', true) or core:get_ui_root()
local t = {}
local function walk(u)
  if not u:Visible() then return end
  local id = u:Id()
  if string.find(id, 'button_ability') then t[#t + 1] = id end
  for k = 0, u:ChildCount() - 1 do walk(UIComponent(u:Find(k))) end
end
local alliances = bm:alliances()
for a = 1, alliances:count() do
  local armies = alliances:item(a):armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      local u = us:item(j)
      if u:is_commanding_unit() and a == 1 then
        local card = mtb.find('card_image_holder', true, mtb.find('cards_panel', true) or cards)
        if card then card:SimulateLClick() end
      end
    end
  end
end
walk(core:get_ui_root())
return table.concat(t, ' ')
