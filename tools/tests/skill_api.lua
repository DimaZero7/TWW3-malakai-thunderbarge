-- Which engine functions deal with skills.
local k = mtb.keys(cm.game_interface)
local hits = {}
for w in string.gmatch(k, "[%w_]+:function") do
  if string.find(w, "skill") or string.find(w, "respec") or string.find(w, "reset") then hits[#hits+1] = w end
end
local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local cq = tostring(c:command_queue_index())
local t = {}
for _, key in ipairs({"SkillPointsAvailable","SkillPointsTotal","SkillPointsSpent","NumSkillPointsSpent","CanResetSkills","SkillsResetCost","CanReset","CanRespec","RespecCost","SkillNodeSetContext.Key"}) do
  local ok, v = pcall(function() return common.get_context_value("CcoCampaignCharacter", cq, key) end)
  if ok and v ~= nil then t[#t+1] = key .. "=" .. tostring(v) end
end
return table.concat(hits, " ") .. "\n" .. table.concat(t, " ")
