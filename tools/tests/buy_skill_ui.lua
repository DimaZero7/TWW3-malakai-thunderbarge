-- Buys a skill as the player does: a click on the card of its node in the open tree. mtb_skill = skill key.
local panel = mtb.find("character_details_panel", true)
local node = mtb.find(mtb_skill, true, panel)
if not node then return "no node " .. tostring(mtb_skill) end
local card = mtb.find("card", true, node)
local state = card:CurrentState()
card:SimulateLClick()
return mtb_skill .. " card was " .. tostring(state)
