-- Strength of Malakai's force relative to another force, the game's own number for the balance preview.
-- The target: the force spawned by barge tests, or else the nearest other faction's force.
local me = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader():military_force()
local other = _G.mtb_target_cqi
if not other then
  local best
  local fl = cm:model():world():faction_list()
  for i = 0, fl:num_items() - 1 do
    local f = fl:item_at(i)
    if f:name() ~= "wh3_dlc25_dwf_malakai" and not f:is_dead() then
      local mfl = f:military_force_list()
      for j = 0, mfl:num_items() - 1 do
        local mf = mfl:item_at(j)
        if mf:has_general() and mf:unit_list():num_items() > 2 then best = mf:command_queue_index(); break end
      end
    end
    if best then break end
  end
  other = best
end
local expr = 'MilitaryForceList.FirstContext(CQI == ' .. me:command_queue_index() .. ').CombatComparisonStrengthRelativeToForce(CampaignRoot.MilitaryForceList.FirstContext(CQI == ' .. other .. '))'
local r = {me = me:command_queue_index(), other = other, value = tostring(common.get_context_value("CcoCampaignRoot", "", expr))}
r.inacc = tostring(common.get_context_value("CcoCampaignRoot", "", 'MilitaryForceList.FirstContext(CQI == ' .. me:command_queue_index() .. ').AutoresolvePredictionInaccuracyPercent(CampaignRoot.MilitaryForceList.FirstContext(CQI == ' .. other .. '))'))
r.crew = mtb.dump(tww3_mtb_crew.get())
return r
