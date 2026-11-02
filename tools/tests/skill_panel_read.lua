-- The open character panel: the nodes the skills tab shows, by column, with their state.
local panel = mtb.find("character_details_panel", true)
if not panel then return "panel is not open" end
local lines = {}
local function walk(uic, depth)
  if not uic:Visible() then return end
  local id = uic:Id()
  if string.find(id, "skill_node") or string.find(id, "CcoCharacterSkillNode") or string.find(id, "malakai_makaisson") then
    lines[#lines+1] = id .. " [" .. tostring(uic:CurrentState()) .. "]"
  end
  if depth > 0 then for i = 0, uic:ChildCount()-1 do walk(UIComponent(uic:Find(i)), depth-1) end end
end
walk(panel, 14)
return #lines .. "\n" .. table.concat(lines, "\n")
