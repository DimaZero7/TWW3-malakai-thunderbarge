-- The lord's unit gets a controller and fires at will; C.order() then moves it at the enemy (crew_lib is already loaded).
local lord = C.lord_unit()
if not lord then return "no lord" end
local lord_army, enemy_alliance
local alliances = bm:alliances()
for a = 1, alliances:count() do
  local armies = alliances:item(a):armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      if us:item(j):type() == C.LAND_UNIT then lord_army, enemy_alliance = armies:item(i), alliances:item(3 - a) end
    end
  end
end
local uc = lord_army:create_unit_controller()
uc:add_units(lord)
uc:take_control()
uc:fire_at_will(true)
-- These tests are about weapons: the barge keeps its damage between battles and would die after a few of them.
local su = script_unit:new(lord)
local invincible = pcall(function() su:set_invincible(true) end)
_G.mtb_crew_uc = uc
_G.mtb_crew_enemy = enemy_alliance
bm:modify_battle_speed(3)
C.order()
return "controller ready, invincible " .. tostring(invincible)
