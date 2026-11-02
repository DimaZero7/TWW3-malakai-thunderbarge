-- Has he got the kept and removed skills, how many points are left.
local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local cq = tostring(c:command_queue_index())
local keep = {bomb="wh3_dlc25_skill_dwf_malakai_makaisson_ability_1", innate="wh2_dlc25_skill_innate_dwf_malakai", inventor="wh3_dlc25_skill_dwf_malakai_makaisson_unique_1", artillery="wh3_dlc25_skill_dwf_malakai_makaisson_unique_4", engineer="wh3_dlc25_skill_dwf_malakai_makaisson_unique_6", brass="wh_main_skill_all_lord_battle_brass-lunged", inspiring="wh_main_skill_all_lord_battle_inspiring_presence", rally="wh_main_skill_all_lord_battle_rally", stand="wh_main_skill_all_lord_battle_stand_your_ground"}
local gone = {deathblow="wh_dlc08_skill_ability_dummy_deathblow", deathblow2="wh3_dlc25_skill_dwf_garagrim_determined_deathblow", deathblow3="wh3_dlc25_skill_dwf_slayer_extremely_daring_deathblow", survivalist="wh2_dlc11_skill_all_lord_self_survivalist", onslaught="wh3_dlc25_skill_dwf_malakai_makaisson_ability_2", rune="wh_main_skill_dwf_all_unique_rune_of_grimnir"}
local out = {rank=c:rank(), points=common.get_context_value("CcoCampaignCharacter", cq, "SkillPointsAvailable"), keep={}, gone={}}
for k, v in pairs(keep) do out.keep[k] = c:has_skill(v) end
for k, v in pairs(gone) do out.gone[k] = c:has_skill(v) end
local text = mtb.dump(out)
mtb.log("skill_state", text)
return text
