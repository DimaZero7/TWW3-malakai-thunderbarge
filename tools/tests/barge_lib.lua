-- Checks of docs/research/barge-behaviour-checks.md. Loaded after crew_lib.lua by tools/barge.py.
local C = _G.mtb_crew
local B = {}

local function cco(u, k)
  local ok, v = pcall(function() return common.get_context_value("CcoBattleUnit", tostring(u:unique_ui_id()), k) end)
  if ok then return v end
  return "err"
end
B.cco = cco

-- The barge of the army: the lord's unit, or a stock barge by key.
function B.unit(key)
  local alliances = bm:alliances()
  for a = 1, alliances:count() do
    local armies = alliances:item(a):armies()
    for i = 1, armies:count() do
      local us = armies:item(i):units()
      for j = 1, us:count() do
        if us:item(j):type() == (key or C.LAND_UNIT) then return us:item(j), armies:item(i), a end
      end
    end
  end
end

-- Live state of an ability from the game's own object (CcoBattleAbility).
function B.ability(u, key)
  local f = 'BattleAbilityList.FirstContext(SetupAbilityContext.RecordKey == "' .. key .. '").'
  local out = {}
  for _, k in ipairs({"RemainingUses", "CurrentState", "CanCurrentlyPerform", "WindUpPercent", "RechargeTimeRemainingSecs", "IsActive"}) do
    out[#out + 1] = k .. "=" .. tostring(cco(u, f .. k))
  end
  return table.concat(out, " ")
end

function B.abilities(u)
  local n = cco(u, "BattleAbilityList.Size")
  local lines = {"abilities " .. tostring(n)}
  local ok, list = pcall(function() return u:owned_non_passive_special_abilities() end)
  if ok and type(list) == "table" then
    for _, key in ipairs(list) do lines[#lines + 1] = tostring(key) .. " " .. B.ability(u, tostring(key)) end
  end
  return table.concat(lines, "\n")
end

-- Every unit of the battle on one line: alliance, key, position, men, health, AI control, flying, melee.
function B.units()
  local lines = {}
  local alliances = bm:alliances()
  for a = 1, alliances:count() do
    local armies = alliances:item(a):armies()
    for i = 1, armies:count() do
      local us = armies:item(i):units()
      for j = 1, us:count() do
        local u = us:item(j)
        local p = u:position()
        lines[#lines + 1] = string.format("%d %s%s x=%d y=%d z=%d men=%d/%d hp=%s/%s ai=%s fly=%s melee=%s kills=%s ammo=%s", a, u:type(), u:is_commanding_unit() and "*" or "",
          p:get_x(), p:get_y(), p:get_z(), u:number_of_men_alive(), u:initial_number_of_men(), tostring(cco(u, "HealthValue")), tostring(cco(u, "HealthMax")),
          tostring(cco(u, "IsUnderAIControl")), tostring(cco(u, "IsFlying")), tostring(cco(u, "IsInMelee")), tostring(cco(u, "NumKills")), tostring(cco(u, "PrimaryAmmoPercent")))
      end
    end
  end
  return table.concat(lines, "\n")
end

-- Men alive per alliance; the enemy of alliance a.
function B.men(a)
  local n, armies = 0, bm:alliances():item(a):armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do n = n + us:item(j):number_of_men_alive() end
  end
  return n
end

-- The living enemy unit nearest to u.
function B.nearest(u, alliance)
  local best, best_d
  local up = u:position()
  local armies = bm:alliances():item(3 - alliance):armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      local e = us:item(j)
      if e:number_of_men_alive() > 0 then
        local p = e:position()
        local dx, dz = p:get_x() - up:get_x(), p:get_z() - up:get_z()
        local d = math.sqrt(dx * dx + dz * dz)
        if not best_d or d < best_d then best, best_d = e, d end
      end
    end
  end
  return best, best_d
end

_G.mtb_barge = B
