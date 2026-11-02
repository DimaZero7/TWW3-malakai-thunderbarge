-- Turn, whose turn, what is open.
local out = {turn=cm:turn_number()}
local w = cm:whose_turn_is_it()
out.whose = w:num_items() > 0 and w:item_at(0):name() or "?"
local root = core:get_ui_root()
local names = {}
for i = 0, root:ChildCount()-1 do
  local c = UIComponent(root:Find(i))
  if c:Visible() and c:Id() ~= "3d_ui_parent" and c:Id() ~= "ai_attack_targets_parent" and c:Id() ~= "watermark_square" and c:Id() ~= "under_advisor_docker" then names[#names+1] = c:Id() end
end
out.root = table.concat(names, " ")
local b = find_uicomponent(core:get_ui_root(), "hud_campaign", "faction_buttons_docker", "button_end_turn")
out.end_turn = b and b:CurrentState() or "-"
return out
