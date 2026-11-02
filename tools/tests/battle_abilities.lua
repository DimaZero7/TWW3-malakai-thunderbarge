-- Army abilities in the battle: the ability bar's components.
local out = {}
local lines = {}
local function walk(uic, d)
  if not uic:Visible() then return end
  local id = uic:Id()
  if string.find(id, "abilit") or string.find(id, "spell") or string.find(id, "reinforc") then
    lines[#lines+1] = id .. " [" .. tostring(uic:CurrentState()) .. "]"
  end
  if d > 0 then for i = 0, uic:ChildCount()-1 do walk(UIComponent(uic:Find(i)), d-1) end end
end
walk(core:get_ui_root(), 10)
out.bar = table.concat(lines, " ")
local army = bm:alliances():item(1):armies():item(1)
local m = mtb.keys(army)
out.methods = string.sub(m, string.find(m, "use_special") or 1, -1)
local k = "wh3_dlc25_army_abilities_spirit_of_grungni"
local ok, v = pcall(function() return common.get_context_value("CcoBattleRoot", "", "PlayerArmyContext.AbilityList.Size") end)
out.cco_size = ok and tostring(v) or "err"
local ok2, v2 = pcall(function() return common.get_context_value("CcoBattleRoot", "", "PlayerArmyContext.AbilityList.Any(RecordContext.Key == \"" .. k .. "\")") end)
out.cco_has = ok2 and tostring(v2) or "err"
local ok3, v3 = pcall(function() return common.get_context_value("CcoBattleRoot", "", "AbilityList.Size") end)
out.cco2 = ok3 and tostring(v3) or "err"
return out
