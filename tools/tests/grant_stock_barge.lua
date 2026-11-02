local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
cm:grant_unit_to_character("character_cqi:" .. c:command_queue_index(), "wh3_dlc25_dwf_veh_thunderbarge_grungni")
local ul = c:military_force():unit_list()
return "units " .. ul:num_items()
