-- Uses the Cinderblast Bomb on the nearest enemy; the game's counter after the battle tells whether it was cast.
local KEY = "wh3_dlc25_lord_abilities_cinderblast_cluster_bomb"
local UNIT = "mtb_dwf_cha_malakai_thunderbarge"
local a = bm:alliances():item(1):armies():item(1)
local us, lord = a:units()
for j = 1, us:count() do if us:item(j):type() == UNIT then lord = us:item(j) end end
local enemy = bm:alliances():item(2):armies():item(1):units():item(1)
local out = {can=lord:can_perform_special_ability(KEY), enemy=enemy:type()}
local uc = a:create_unit_controller()
uc:add_units(lord)
local ok, err = pcall(function() uc:perform_special_ability(KEY, enemy) end)
out.unit_target = ok and "called" or tostring(err)
if not ok then
  local ok2, err2 = pcall(function() uc:perform_special_ability_ground(KEY, enemy:position()) end)
  out.ground = ok2 and "called" or tostring(err2)
end
return out
