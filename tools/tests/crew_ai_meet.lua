-- The player's leader beside Malakai under the AI; Malakai's force attacks. Opens the pre-battle panel for the player.
local world = cm:model():world()
local malakai
local factions = world:faction_list()
for i = 0, factions:num_items() - 1 do
  local chars = factions:item_at(i):character_list()
  for j = 0, chars:num_items() - 1 do
    if chars:item_at(j):character_subtype_key() == "wh3_dlc25_dwf_malakai_makaisson" then malakai = chars:item_at(j) end
  end
end
if not malakai or not malakai:has_military_force() then return "no Malakai with a force" end
local player = cm:get_faction(cm:get_local_faction_name(true))
local leader = player:faction_leader()
if not leader:has_military_force() then return "no player force" end
local look = "character_cqi:" .. malakai:command_queue_index()
local x, y = cm:find_valid_spawn_location_for_character_from_character(player:name(), look, true, 4)
cm:force_declare_war(player:name(), malakai:faction():name(), false, false)
cm:teleport_to("character_cqi:" .. leader:command_queue_index(), x, y)
local a, b = malakai:military_force():command_queue_index(), leader:military_force():command_queue_index()
cm:callback(function() cm:force_attack_of_opportunity(a, b, false, true) end, 1)
return {malakai = malakai:faction():name(), player = player:name(), x = x, y = y, unit = malakai:military_force():unit_list():item_at(0):unit_key()}
