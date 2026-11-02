-- The lord is killed by script: a wound in the campaign, as with a lord that falls in battle.
local UNIT = "mtb_dwf_cha_malakai_thunderbarge"
local alliances = bm:alliances()
for a = 1, alliances:count() do
  local armies = alliances:item(a):armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      if us:item(j):type() == UNIT then
        local su = script_unit:new(us:item(j))
        su:kill(true)
        return "lord killed; commander alive=" .. tostring(armies:item(i):is_commander_alive())
      end
    end
  end
end
return "no lord"
