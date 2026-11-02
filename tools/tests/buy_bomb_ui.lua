-- Buys the Cinderblast Bomb as the player does: a click on its node in the open skill tree.
local KEY = "wh3_dlc25_skill_dwf_malakai_makaisson_ability_1"
local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local panel = mtb.find("character_details_panel", true)
local out = {before=c:has_skill(KEY)}
local node = mtb.find(KEY, true, panel)
if not node then out.err = "no node"; return out end
local names = {}
local function walk(u, d)
  names[#names+1] = u:Id() .. "[" .. tostring(u:CurrentState()) .. "]"
  if d > 0 then for i = 0, u:ChildCount()-1 do walk(UIComponent(u:Find(i)), d-1) end end
end
walk(node, 2)
out.tree = table.concat(names, " ")
local target = mtb.find("module_" .. KEY, true, node) or mtb.find("skill", true, node) or node
out.clicked = target:Id()
out.state = target:CurrentState()
target:SimulateLClick()
return out
