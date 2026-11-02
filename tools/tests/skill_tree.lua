-- Malakai's skills as the game offers them. Rank up (mtb_rank), then opens the panel with the end-turn warning about points.
local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local look = "character_cqi:" .. c:command_queue_index()
if mtb_rank then cm:add_agent_experience(look, tonumber(mtb_rank), true); mtb_rank = nil end
local cq = tostring(c:command_queue_index())
local out = {rank=c:rank()}
local ok, pts = pcall(function() return common.get_context_value("CcoCampaignCharacter", cq, "SkillPointsAvailable") end)
out.points = ok and pts or "?"
return out
