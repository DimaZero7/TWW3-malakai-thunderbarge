local UNIT = "mtb_dwf_cha_malakai_thunderbarge"
local lord, army
local alliances = bm:alliances()
for a = 1, alliances:count() do
  local armies = alliances:item(a):armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      if us:item(j):type() == UNIT then lord, army = us:item(j), armies:item(i) end
    end
  end
end
local key = mtb_ability or "wh3_dlc25_unit_abilities_thunderburner"
local can = lord:can_perform_special_ability(key)
local uc = army:create_unit_controller()
uc:add_units(lord)
uc:perform_special_ability(key, lord)
return {can=can, key=key, phase=bm:get_current_phase_name(), hp=lord:unary_hitpoints()}
