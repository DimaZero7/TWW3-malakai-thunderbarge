-- A new small enemy army beside Malakai, attacked at once: opens the pre-battle panel. mtb_units: comma list.
local leader = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local look = "character_cqi:" .. leader:command_queue_index()
local enemy = "wh_main_grn_greenskins"
local x, y = cm:find_valid_spawn_location_for_character_from_character("wh3_dlc25_dwf_malakai", look, true, 6)
local units = mtb_units or "wh_main_grn_inf_goblin_spearmen,wh_main_grn_inf_goblin_spearmen,wh_main_grn_inf_goblin_archers"
local out = {x=x, y=y, region=leader:region():name()}
cm:force_declare_war(enemy, "wh3_dlc25_dwf_malakai", false, false)
cm:create_force(enemy, units, leader:region():name(), x, y, true, function(char_cqi, force_cqi)
  mtb.log("spawned", tostring(char_cqi) .. " force " .. tostring(force_cqi))
  cm:callback(function()
    local a = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader():military_force():command_queue_index()
    cm:force_attack_of_opportunity(a, force_cqi, false, true)
    mtb.log("attack", tostring(a) .. " on " .. tostring(force_cqi))
  end, 1)
end)
return out
