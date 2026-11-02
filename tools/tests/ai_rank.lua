-- AI Malakai gains ranks, so the AI spends points in the shortened tree. Reports the skills he owns.
local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local look = "character_cqi:" .. c:command_queue_index()
if mtb_add then cm:add_agent_experience(look, tonumber(mtb_add), true); mtb_add = nil end
local nodes = {"wh_dlc08_skill_ability_dummy_deathblow","wh3_dlc25_skill_dwf_garagrim_determined_deathblow","wh3_dlc25_skill_dwf_slayer_extremely_daring_deathblow","wh2_dlc11_skill_all_lord_self_survivalist","wh_main_skill_dwf_all_unique_rune_of_grimnir",
 "wh3_dlc25_skill_dwf_malakai_makaisson_ability_1","wh3_dlc25_skill_dwf_malakai_makaisson_unique_1","wh3_dlc25_skill_dwf_malakai_makaisson_unique_2","wh3_dlc25_skill_dwf_malakai_makaisson_unique_3","wh3_dlc25_skill_dwf_malakai_makaisson_unique_4","wh3_dlc25_skill_dwf_malakai_makaisson_unique_5","wh3_dlc25_skill_dwf_malakai_makaisson_unique_6",
 "wh_main_skill_all_lord_battle_brass-lunged","wh2_dlc10_skill_dwf_generic_oath_of_forging","wh_main_skill_dwf_lord_battle_lord_of_the_deeps","wh_main_skill_dwf_lord_battle_obstinacy","wh_main_skill_all_lord_battle_inspiring_presence","wh_main_skill_all_lord_campaign_route_marcher","wh3_dlc25_dwf_daemon_slayer_units_1"}
local have = {}
for _, k in ipairs(nodes) do if c:has_skill(k) then have[#have+1] = k end end
local cq = tostring(c:command_queue_index())
local text = "turn " .. cm:turn_number() .. " rank " .. c:rank() .. " points " .. tostring(common.get_context_value("CcoCampaignCharacter", cq, "SkillPointsAvailable")) .. " skills " .. table.concat(have, ",")
mtb.log("ai_skills", text)
return text
