-- Visible buttons under a panel: mtb_panel (default: whole tree without 3D labels).
local lines = {}
local function walk(uic, d)
  if not uic:Visible() then return end
  local id = uic:Id()
  if string.find(id, "button") or string.find(id, "btn") or string.find(id, "option") then lines[#lines+1] = id .. " [" .. tostring(uic:CurrentState()) .. "]" end
  if d > 0 then for i = 0, uic:ChildCount()-1 do walk(UIComponent(uic:Find(i)), d-1) end end
end
if mtb_panel then
  walk(mtb.find(mtb_panel, true), 12)
else
  local root = core:get_ui_root()
  for i = 0, root:ChildCount()-1 do
    local c = UIComponent(root:Find(i))
    if c:Visible() and c:Id() ~= "3d_ui_parent" and c:Id() ~= "ai_attack_targets_parent" then walk(c, 12) end
  end
end
return table.concat(lines, "\n")
