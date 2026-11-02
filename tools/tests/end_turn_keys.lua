local gi = cm.game_interface
local k = mtb.keys(gi)
local hits = {}
for w in string.gmatch(k, "[%w_]+:function") do
  if string.find(w, "turn") or string.find(w, "save") or string.find(w, "load") or string.find(w, "autoresolve") or string.find(w, "win_next") then hits[#hits+1] = w end
end
local cuim = cm:get_campaign_ui_manager()
local warn = {}
for a, b in pairs(cuim.end_turn_warnings) do warn[#warn+1] = tostring(a) .. "=" .. tostring(b) end
return table.concat(hits, " ") .. "\n" .. table.concat(warn, " ")
