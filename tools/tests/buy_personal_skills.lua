-- For the old-save test: rank up and spend points on the personal skills, as a player would have. Army skills too.
local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local look = "character_cqi:" .. c:command_queue_index()
cm:add_agent_experience(look, 25, true)
local skills = {"wh2_dlc11_skill_all_lord_self_survivalist","wh3_dlc23_skill_chd_lord_self_always_ready","wh3_dlc23_skill_chd_lord_self_bandolier",
  "wh2_dlc11_skill_all_lord_self_hard_to_hit","wh_main_skill_dwf_lord_self_ancestral_grudge","wh3_dlc25_skill_dwf_malakai_makaisson_ability_1",
  "wh2_dlc11_skill_all_lord_self_blade_shield","wh_main_skill_dwf_all_unique_rune_of_grimnir",
  "wh3_dlc25_skill_dwf_garagrim_determined_deathblow","wh3_dlc25_skill_dwf_slayer_extremely_daring_deathblow",
  "wh_main_skill_all_lord_battle_inspiring_presence","wh_main_skill_all_lord_battle_brass-lunged"}
for _, s in ipairs(skills) do cm:add_skill(c, s, true, false) end
return "bought " .. #skills
