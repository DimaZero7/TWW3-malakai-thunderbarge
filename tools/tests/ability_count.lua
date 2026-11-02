-- After a battle: how many times the game counted the abilities of the last battle.
local pb = cm:model():pending_battle()
local q = cm:get_faction("wh3_dlc25_dwf_malakai"):command_queue_index()
local out = {fought=tostring(pb:has_been_fought())}
for _, k in ipairs({"wh3_dlc25_unit_abilities_thunderburner","wh3_dlc25_army_abilities_spirit_of_grungni","wh3_dlc25_lord_abilities_deranged_munitions"}) do
  out[k] = pb:get_how_many_times_ability_has_been_used_in_battle(q, k)
end
return out
