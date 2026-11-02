-- What panels and main buttons are open now.
local out = {}
for _, n in ipairs({"popup_pre_battle","button_attack","button_autoresolve","button_set_attack","button_retreat","button_continue","button_dismiss_results","button_end_turn","post_battle","popup_battle_results","button_battle_results"}) do
  local u = mtb.find(n, true)
  out[n] = u and tostring(u:CurrentState()) or "-"
end
local root = core:get_ui_root()
local names = {}
for i = 0, root:ChildCount()-1 do
  local c = UIComponent(root:Find(i))
  if c:Visible() then names[#names+1] = c:Id() end
end
out.root = table.concat(names, " ")
return out
