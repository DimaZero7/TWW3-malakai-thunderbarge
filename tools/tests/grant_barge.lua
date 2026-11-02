-- The barge's upgrades as in a real campaign: a hull and an engine building on Malakai's force, the reward bundle on the faction.
local out = {}
local f = cm:get_faction("wh3_dlc25_dwf_malakai")
local mf = f:faction_leader():military_force()
local cqi = mf:command_queue_index()
for _, b in ipairs({"wh3_dlc25_dwarf_spirit_of_grungni_airship_hull_1", "wh3_dlc25_dwarf_spirit_of_grungni_engines_1"}) do
  local ok, err = pcall(function() cm:add_building_to_force(cqi, b) end)
  out[b] = ok and "ok" or tostring(err)
end
cm:apply_effect_bundle("wh3_dlc25_reward_dwf_malakai_dragon_hunters_final_reward", "wh3_dlc25_dwf_malakai", 0)
cm:apply_effect_bundle("wh3_dlc25_reward_dwf_malakai_warpstone_bomb_final_reward", "wh3_dlc25_dwf_malakai", 0)
out.buildings = {}
local bl = mf:buildings()
if bl then for i = 0, bl:num_items()-1 do out.buildings[#out.buildings+1] = bl:item_at(i):name() end end
return out
