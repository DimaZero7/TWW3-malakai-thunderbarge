-- A generated enemy army attacked by Malakai's force; opens the pre-battle panel.
local leader = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local r = Forced_Battle_Manager:trigger_forced_battle_with_generated_army(
    leader:military_force():command_queue_index(),
    "wh_main_grn_greenskins", "wh_main_sc_grn_greenskins", 8, 1, false, true, false)
return "triggered " .. tostring(r)
