-- Control without the mod: does the stock barge burn itself with Thunderburner? mtb_use=key uses it once.
local army = bm:alliances():item(1):armies():item(1)
local us = army:units()
local barge
for j = 1, us:count() do
  local u = us:item(j)
  if string.find(u:type(), "thunderbarge") then barge = u end
end
if not barge then return "no barge in the army" end
local list = {}
for _, k in ipairs(barge:owned_non_passive_special_abilities()) do list[#list+1] = tostring(k) end
local passive = {}
for _, k in ipairs(barge:owned_passive_special_abilities()) do passive[#passive+1] = tostring(k) end
local out = {type=barge:type(), hp=barge:unary_hitpoints(), active=table.concat(list, ","), passive=table.concat(passive, ",")}
if mtb_use and mtb_use ~= "" then
  out.can = barge:can_perform_special_ability(mtb_use)
  local uc = army:create_unit_controller()
  uc:add_units(barge)
  uc:perform_special_ability(mtb_use, barge)
  mtb_use = nil
end
return out
