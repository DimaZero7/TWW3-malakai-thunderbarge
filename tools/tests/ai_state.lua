-- Malakai under the AI or in a confederation: who owns him, his item, his unit.
local out = {player=cm:get_local_faction_name(true), turn=cm:turn_number(), found=0}
local fl = cm:model():world():faction_list()
for i = 0, fl:num_items()-1 do
  local f = fl:item_at(i)
  local cl = f:character_list()
  for j = 0, cl:num_items()-1 do
    local c = cl:item_at(j)
    if c:character_subtype_key() == "wh3_dlc25_dwf_malakai_makaisson" then
      out.found = out.found + 1
      out.faction = f:name(); out.human = f:is_human(); out.anc = c:has_ancillary("mtb_anc_mount_dwf_malakai_thunderbarge")
      out.force = c:has_military_force()
      if c:has_military_force() then out.unit = c:military_force():unit_list():item_at(0):unit_key() end
    end
  end
end
local home = cm:get_faction("wh3_dlc25_dwf_malakai")
out.home_dead = home and home:is_dead()
return out
