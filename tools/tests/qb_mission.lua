-- Gives Malakai's legendary battle mission for the warpstone set, then reports what the mission offers.
local key = "wh3_dlc25_mis_dwf_malakai_warpstone_bomb_narrative_battle_ie"
cm:trigger_mission("wh3_dlc25_dwf_malakai", key, true)
return "triggered " .. key
