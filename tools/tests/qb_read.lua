-- In a quest battle: the units, whether its script found Malakai, whether the summon is there.
local out = {}
local t = {}
local ok = pcall(function()
  local army = bm:alliances():item(1):armies():item(1)
  local us = army:units()
  for j = 1, us:count() do t[#t+1] = us:item(j):type() .. (us:item(j):is_commanding_unit() and "*" or "") end
end)
out.units = table.concat(t, ",")
out.malakai_sunit = tostring(malakai_sunit)
out.malakai_type = malakai_sunit and malakai_sunit.unit and malakai_sunit.unit:type() or "none"
out.phase = bm:get_current_phase_name()
local lines = {}
local function walk(uic, d)
  if not uic:Visible() then return end
  if string.find(uic:Id(), "army_abilities") then lines[#lines+1] = uic:Id() end
  if d > 0 then for i = 0, uic:ChildCount()-1 do walk(UIComponent(uic:Find(i)), d-1) end end
end
walk(core:get_ui_root(), 10)
out.bar = table.concat(lines, " ")
return out
