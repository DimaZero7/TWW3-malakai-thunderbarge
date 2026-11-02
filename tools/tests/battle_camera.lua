-- Camera for the wheel. mtb_cam = "front" (default), "rear", "wide". Selects the lord's card first.
local UNIT = "mtb_dwf_cha_malakai_thunderbarge"
local lord
local alliances = bm:alliances()
for a = 1, alliances:count() do
  local armies = alliances:item(a):armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      if us:item(j):type() == UNIT then lord = us:item(j) end
    end
  end
end
if not lord then return "no lord unit" end
local p = lord:position()
local b = lord:bearing() * 3.14159265 / 180
local function world(f, r, u)
  return p:get_x() + math.sin(b) * f + math.cos(b) * r, p:get_y() + u, p:get_z() + math.cos(b) * f - math.sin(b) * r
end
local function vec(x, y, z)
  local v = battle_vector:new(); v:set_x(x); v:set_y(y); v:set_z(z); return v
end
local mode = mtb_cam or "front"
local cam = {front={-1.0, 0, 5.7, -4.5, 0, 5, 35}, rear={-7.0, 2.5, 5.7, -4.5, 0, 5, 35}, wide={-60, -60, 60, 0, 0, 15, 45}}
local c = cam[mode]
local cx, cy, cz = world(c[1], c[2], c[3])
local tx, ty, tz = world(c[4], c[5], c[6])
bm:camera():move_to(vec(cx, cy, cz), vec(tx, ty, tz), 0, false, c[7])
local parent = find_uicomponent(core:get_ui_root(), "battle_orders", "cards_panel", "review_DY")
if parent then
  local id = tostring(lord:unique_ui_id())
  for i = 0, parent:ChildCount() - 1 do
    local uic = UIComponent(parent:Find(i))
    if uic:Id() == id then uic:SimulateLClick() end
  end
end
return mode .. " phase " .. bm:get_current_phase_name()
