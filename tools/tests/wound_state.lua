-- Malakai's wound and where he is.
local out = {}
local fl = cm:model():world():faction_list()
for i = 0, fl:num_items()-1 do
  local cl = fl:item_at(i):character_list()
  for j = 0, cl:num_items()-1 do
    local c = cl:item_at(j)
    if c:character_subtype_key() == "wh3_dlc25_dwf_malakai_makaisson" then
      out.faction = c:faction():name(); out.cqi = c:command_queue_index(); out.wounded = c:is_wounded()
      out.limbo = c:is_in_limbo(); out.force = c:has_military_force(); out.anc = c:has_ancillary("mtb_anc_mount_dwf_malakai_thunderbarge")
      local ok, t = pcall(function() return c:compute_convalesence_time() end)
      out.time = ok and tostring(t) or "?"
      if c:has_military_force() then out.unit = c:military_force():unit_list():item_at(0):unit_key() end
    end
  end
end
out.turn = cm:turn_number()
return out
