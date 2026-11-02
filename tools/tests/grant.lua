-- Rank, a skill and an item, to compare with the state after a save and with their effects in battle.
local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local look = "character_cqi:" .. c:command_queue_index()
cm:add_agent_experience(look, 10, true)
cm:add_skill(c, "wh_main_skill_all_lord_battle_inspiring_presence", true, true)
cm:force_add_ancillary(c, "wh3_dlc25_anc_weapon_makaissons_persuader", true, true)
return "granted"
