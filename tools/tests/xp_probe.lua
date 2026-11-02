-- Looks for the character's exact experience among context values.
local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local cq = tostring(c:command_queue_index())
local out = {}
for _, k in ipairs({"Experience","ExperienceInt","ExperienceTotal","TotalExperience","CurrentRankExperience","ExperienceForCurrentRank","ExperienceForNextRank","ExperienceToNextLevel","XpToNextRank","RankXP","ProgressToNextRank","ExperiencePercent","ExperienceProgress","ExperienceProgressPercent","XPProgress","NextRankExperience","Xp","XP","XpValue","Level","Rank","TotalSkillPoints","SkillPointsSpent","SkillPointsAvailable","SkillPointsTotal","NumSkillPoints"}) do
  local ok, v = pcall(function() return common.get_context_value("CcoCampaignCharacter", cq, k) end)
  if ok and v ~= nil then out[k] = v end
end
return out
