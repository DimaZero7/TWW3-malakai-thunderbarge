-- Recovered Malakai gets a new army: which unit does the game give him?
local F = "wh3_dlc25_dwf_malakai"
local cl = cm:get_faction(F):character_list()
local m
for i = 0, cl:num_items()-1 do
  if cl:item_at(i):character_subtype_key() == "wh3_dlc25_dwf_malakai_makaisson" then m = cl:item_at(i) end
end
local region = "wh3_main_combi_region_kraka_drak"
local x, y = cm:find_valid_spawn_location_for_character_from_settlement(F, region, false, true, 6)
cm:create_force_with_existing_general("character_cqi:" .. m:command_queue_index(), F, "wh_main_dwf_inf_miners_1", region, x, y,
  function(cqi, force_cqi) mtb.log("reappointed", tostring(cqi) .. " force " .. tostring(force_cqi)) end)
return {x=x, y=y, cqi=m:command_queue_index()}
