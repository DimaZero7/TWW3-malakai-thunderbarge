-- Ends the battle in the player's favour: every enemy unit is killed by script.
local n = 0
local alliances = bm:alliances()
local a2 = alliances:item(2)
local armies = a2:armies()
for i = 1, armies:count() do
  local us = armies:item(i):units()
  for j = 1, us:count() do
    local su = script_unit:new(us:item(j))
    su:kill(true)
    n = n + 1
  end
end
return n .. " enemy units killed"
