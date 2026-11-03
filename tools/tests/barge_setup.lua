-- Malakai's army under the AI before a meeting. mtb_remove: pattern of unit keys to take out; mtb_add: comma list to grant.
local c = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
local look = "character_cqi:" .. c:command_queue_index()
local out = {removed = {}, added = {}}
local keys = {}
local gi = mtb.keys(cm.game_interface)
for w in string.gmatch(gi, "[%w_]+:function") do
  if string.find(w, "remove_unit") or string.find(w, "remove_all_units") or string.find(w, "disband") or string.find(w, "destroy_unit") then keys[#keys + 1] = w end
end
out.api = table.concat(keys, " ")
local ul = c:military_force():unit_list()
local todo = {}
for i = 0, ul:num_items() - 1 do
  local k = ul:item_at(i):unit_key()
  if mtb_remove and string.find(k, mtb_remove) then todo[#todo + 1] = k end
end
for _, k in ipairs(todo) do
  local ok, err = pcall(function() cm:remove_unit_from_character(look, k) end)
  out.removed[#out.removed + 1] = k .. "=" .. tostring(ok and "ok" or err)
end
if mtb_add then
  for k in string.gmatch(mtb_add, "[^,]+") do
    cm:grant_unit_to_character(look, k)
    out.added[#out.added + 1] = k
  end
end
cm:callback(function() end, 1)
local now = {}
ul = c:military_force():unit_list()
for i = 0, ul:num_items() - 1 do now[#now + 1] = ul:item_at(i):unit_key() end
out.units = table.concat(now, ",")
return out
