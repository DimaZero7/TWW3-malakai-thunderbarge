-- Dismisses open event panels and sends Malakai's force at the nearest enemy army.
local out = {}
local events = mtb.find("events", true)
if events then
  local b = mtb.find("button_accept", true, events)
  if b then b:SimulateLClick(); out.dismissed = true end
end
local leader = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local lx, ly = leader:logical_position_x(), leader:logical_position_y()
local best, best_d
local fl = cm:model():world():faction_list()
for i = 0, fl:num_items()-1 do
  local f = fl:item_at(i)
  if f:name() ~= "wh3_dlc25_dwf_malakai" then
    local mfl = f:military_force_list()
    for j = 0, mfl:num_items()-1 do
      local mf = mfl:item_at(j)
      if mf:has_general() and not mf:is_armed_citizenry() then
        local g = mf:general_character()
        local d = (g:logical_position_x()-lx)^2 + (g:logical_position_y()-ly)^2
        if not best_d or d < best_d then best, best_d = mf, d; out.enemy = f:name(); out.subtype = g:character_subtype_key(); out.units = mf:unit_list():num_items() end
      end
    end
  end
end
out.dist2 = best_d
local a = leader:military_force():command_queue_index()
cm:force_attack_of_opportunity(a, best:command_queue_index(), false, true)
out.ordered = true
return out
