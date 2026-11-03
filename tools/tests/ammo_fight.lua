-- Helpers of the ammunition battles (tools/crew_cycle.py, ammo steps). crew_lib is already loaded, crew_fight.lua has run for the player's battles.
local T = {}
_G.mtb_ammo_t = T

local function enemy_units()
  local out = {}
  local armies = _G.mtb_crew_enemy:armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do out[#out + 1] = us:item(j) end
  end
  return out
end

-- The enemy cannot be finished and stands still, so the fight lasts as long as the shots do and the distance is ours to choose.
function T.keep_enemy()
  T.kept = {}
  local done = 0
  for _, unit in ipairs(enemy_units()) do
    local su = script_unit:new(unit)
    if pcall(function()
      su:set_invincible(true)
      su.uc:morale_behavior_fearless()
      su.uc:take_control()
      su.uc:halt()
    end) then
      done = done + 1
      T.kept[#T.kept + 1] = su
    end
  end
  return "enemy units held " .. done
end

function T.release_enemy()
  for _, su in ipairs(T.kept or {}) do pcall(function() su:set_invincible(false) end) end
  return "released"
end

local function nearest()
  local up = C.lord_unit():position()
  local best, best_d
  for _, unit in ipairs(enemy_units()) do
    if unit:number_of_men_alive() > 0 then
      local p = unit:position()
      local dx, dz = p:get_x() - up:get_x(), p:get_z() - up:get_z()
      local d = math.sqrt(dx * dx + dz * dz)
      if not best_d or d < best_d then best, best_d = unit, d end
    end
  end
  return best, best_d, up
end

-- Bombs fall straight down, the others need some distance: over the enemy while the bombs have ammunition, at 70 m after that.
function T.order()
  local target, d, up = nearest()
  if not target then return "no enemy" end
  local uc = _G.mtb_crew_uc
  local state = tww3_mtb_ammo.read()
  if d > 120 then
    uc:goto_location(target:position(), true)
    return "moving " .. math.floor(d)
  end
  if state.bombs and state.bombs.ammo > 0 then
    uc:attack_unit(target, true, true)
    return "over " .. math.floor(d)
  end
  -- Cannons that have not fired for a while: the angle may be wrong, go over the target for a moment.
  local now = bm:time_elapsed_ms() / 1000
  local guns = state.cannons
  if guns and guns.ammo > 0 and now - (guns.last_shot or T.started or now) > 40 then
    if not T.started then T.started = now end
    if now - (T.moved or 0) > 25 then
      T.moved = now
      uc:attack_unit(target, true, true)
      return "over for the cannons " .. math.floor(d)
    end
    return "waiting for the cannons " .. math.floor(d)
  end
  T.started = T.started or now
  if d < 45 or d > 95 then
    local p = target:position()
    local dx, dz = up:get_x() - p:get_x(), up:get_z() - p:get_z()
    local len = math.max(d, 1)
    local goal = battle_vector:new()
    goal:set_x(p:get_x() + dx / len * 70)
    goal:set_y(up:get_y())
    goal:set_z(p:get_z() + dz / len * 70)
    uc:goto_location(goal, true)
    return "to 70 m from " .. math.floor(d)
  end
  return "holding " .. math.floor(d)
end

-- string.find in the game searches for plain text, and a fourth argument breaks it for everybody: two arguments only.
-- Battle seconds since these groups (comma list, or all) are all dry; -1 while one still has ammunition.
function T.dry_for(names)
  local state = tww3_mtb_ammo.read()
  local latest = 0
  local any = false
  for group, row in pairs(state) do
    if names == "all" or string.find("," .. names .. ",", "," .. group .. ",") then
      any = true
      if not row.dry_at then return -1 end
      if row.dry_at > latest then latest = row.dry_at end
    end
  end
  if not any then return -1 end
  return bm:time_elapsed_ms() / 1000 - latest
end

-- In a battle under the AI: the player's army walks at the barge, or the AI's army stands and waits (docs/research/barge-behaviour-checks.md).
function T.push_player()
  local lord = C.lord_unit()
  local alliances = bm:alliances()
  local n = 0
  for a = 1, alliances:count() do
    local armies = alliances:item(a):armies()
    local ours = false
    for i = 1, armies:count() do
      local us = armies:item(i):units()
      for j = 1, us:count() do
        if us:item(j):type() == C.LAND_UNIT then ours = true end
      end
    end
    if not ours then
      for i = 1, armies:count() do
        local uc = armies:item(i):create_unit_controller()
        local us = armies:item(i):units()
        for j = 1, us:count() do uc:add_units(us:item(j)); n = n + 1 end
        uc:take_control()
        uc:goto_location(lord:position(), true)
        T.player_uc = uc
      end
    end
  end
  return "player's units sent " .. n
end

function T.line()
  return tostring(tww3_mtb_ammo.status) .. " | " .. tostring(tww3_mtb_ammo.report()) .. " | " .. C.stats()
end

return "ammo helpers loaded"
