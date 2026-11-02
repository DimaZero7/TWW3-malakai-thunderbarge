local panel = mtb.find("character_details_panel", true)
local names = {}
local function walk(uic, d)
  if not uic:Visible() then return end
  local id = string.lower(uic:Id())
  if string.find(id, "tab") or string.find(id, "skill") then names[#names+1] = uic:Id() .. "[" .. tostring(uic:CurrentState()) .. "]" end
  if d > 0 then for i = 0, uic:ChildCount()-1 do walk(UIComponent(uic:Find(i)), d-1) end end
end
walk(panel, 5)
local b = mtb.find("TabSkills", true, panel) or mtb.find("tab_skills", true, panel) or mtb.find("skills_tab", true, panel) or mtb.find("button_stats_tab_skills", true, panel)
if b then b:SimulateLClick(); names[#names+1] = "CLICKED " .. b:Id() end
return table.concat(names, " ")
