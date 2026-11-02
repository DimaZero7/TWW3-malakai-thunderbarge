-- Everything of the character that must survive: writes one "snapshot" event. Run with tools/rc.py --file.
-- mtb_label is set by the caller's first line, or the label is "snapshot".
local SKILLS = {"wh2_dlc10_skill_dwf_generic_oath_of_forging","wh2_dlc11_skill_all_lord_self_blade_shield","wh2_dlc11_skill_all_lord_self_hard_to_hit","wh2_dlc11_skill_all_lord_self_survivalist","wh2_dlc11_skill_dwf_army_buff_axe_lord","wh2_dlc11_skill_dwf_army_buff_blessed_by_grungni","wh2_dlc11_skill_dwf_army_buff_dawi_firepower","wh2_dlc11_skill_dwf_army_buff_fire_and_fury","wh2_dlc11_skill_dwf_army_buff_grimnirs_heirs","wh2_dlc11_skill_dwf_army_buff_honoured_by_grimnir","wh2_dlc11_skill_dwf_army_buff_morgrims_favoured","wh2_dlc11_skill_dwf_army_buff_tactician","wh2_dlc11_skill_dwf_army_buff_thunderer","wh2_dlc11_skill_dwf_army_buff_tradition_and_innovation","wh2_dlc25_skill_innate_dwf_malakai","wh3_dlc23_skill_chd_hero_self_gunsight","wh3_dlc23_skill_chd_lord_self_always_ready","wh3_dlc23_skill_chd_lord_self_bandolier","wh3_dlc23_skill_chd_lord_self_piercing_shots","wh3_dlc25_dwf_daemon_slayer_units_1","wh3_dlc25_dwf_daemon_slayer_units_2_1","wh3_dlc25_dwf_daemon_slayer_units_2_2","wh3_dlc25_skill_dwf_garagrim_determined_deathblow","wh3_dlc25_skill_dwf_malakai_makaisson_ability_1","wh3_dlc25_skill_dwf_malakai_makaisson_ability_2","wh3_dlc25_skill_dwf_malakai_makaisson_unique_1","wh3_dlc25_skill_dwf_malakai_makaisson_unique_2","wh3_dlc25_skill_dwf_malakai_makaisson_unique_3","wh3_dlc25_skill_dwf_malakai_makaisson_unique_4","wh3_dlc25_skill_dwf_malakai_makaisson_unique_5","wh3_dlc25_skill_dwf_malakai_makaisson_unique_6","wh3_dlc25_skill_dwf_slayer_extremely_daring_deathblow","wh_dlc08_skill_ability_dummy_deathblow","wh_main_skill_all_lord_battle_brass-lunged","wh_main_skill_all_lord_battle_inspiring_presence","wh_main_skill_all_lord_battle_rally","wh_main_skill_all_lord_battle_stand_your_ground","wh_main_skill_all_lord_campaign_alert","wh_main_skill_all_lord_campaign_lightning_strike","wh_main_skill_all_lord_campaign_route_marcher","wh_main_skill_dwf_all_unique_rune_of_grimnir","wh_main_skill_dwf_lord_battle_lord_of_the_deeps","wh_main_skill_dwf_lord_battle_obstinacy","wh_main_skill_dwf_lord_campaign_enquiring_mind","wh_main_skill_dwf_lord_campaign_inspirational_leader","wh_main_skill_dwf_lord_campaign_iron-willed","wh_main_skill_dwf_lord_campaign_mason","wh_main_skill_dwf_lord_campaign_miners_instinct","wh_main_skill_dwf_lord_campaign_pure-beard","wh_main_skill_dwf_lord_campaign_wall_breaker","wh_main_skill_dwf_lord_self_ancestral_grudge","wh_main_skill_dwf_lord_self_relentless","wh_main_skill_lord_all_campaign_reassuring_presence"}
local ANC = {"mtb_anc_mount_dwf_malakai_thunderbarge","wh3_dlc25_anc_enchanted_item_the_eyes_of_grungni","wh3_dlc25_anc_weapon_glaive_gun","wh3_dlc25_anc_weapon_makaissons_persuader"}
local function find()
  local fl = cm:model():world():faction_list()
  for i = 0, fl:num_items()-1 do
    local cl = fl:item_at(i):character_list()
    for j = 0, cl:num_items()-1 do
      local c = cl:item_at(j)
      if c:character_subtype_key() == "wh3_dlc25_dwf_malakai_makaisson" then return c end
    end
  end
end
local c = find()
local cqs = tostring(c:command_queue_index())
local s = {turn=cm:turn_number(), faction=c:faction():name(), cqi=c:command_queue_index(), rank=c:rank(), wounded=c:is_wounded(),
  fought=c:battles_fought(), won=c:battles_won(), traits=c:number_of_traits(), hp_force=c:has_military_force(), loyal=c:loyalty(),
  x=c:logical_position_x(), y=c:logical_position_y(), skills={}, anc={}, unit=nil, units=nil, xp={}}
for _, k in ipairs(SKILLS) do if c:has_skill(k) then s.skills[#s.skills+1]=k end end
table.sort(s.skills)
for _, k in ipairs(ANC) do if c:has_ancillary(k) then s.anc[#s.anc+1]=k end end
if c:has_military_force() then
  local ul = c:military_force():unit_list()
  local keys = {}
  for i=0, ul:num_items()-1 do keys[#keys+1]=ul:item_at(i):unit_key() end
  s.units = table.concat(keys, ",")
  s.general_unit = keys[1]
end
for _, k in ipairs({"Rank","Name","SkillPointsAvailable","SkillPointsSpent","Experience","ExperienceCurrent","CurrentExperience","XP","RankProgress","AncillaryList.Size","NumAvailableSkillPoints","UnspentSkillPoints","RankExperience","ExperienceToNextRank"}) do
  local ok, v = pcall(function() return common.get_context_value("CcoCampaignCharacter", cqs, k) end)
  if ok and v ~= nil then s.xp[k] = v end
end
s.label = mtb_label or "snapshot"
local text = mtb.dump(s)
mtb.log("snapshot", text)
return text
