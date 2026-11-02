-- Closes what stops a turn from ending: notices and the "appoint a new general" panel.
local out = {}
local a = mtb.find("appoint_new_general", true)
if a then
  local b = mtb.find("button_hire", true, a)
  if b then b:SimulateLClick(); out.clicked = "hire" end
end
local d = mtb.find("diplomacy_dropdown", true)
if d then
  local b = mtb.find("button_reject", true, d) or mtb.find("button_decline", true, d) or mtb.find("button_accept", true, d)
  if b then out.diplomacy = b:Id(); b:SimulateLClick() end
end
for _ = 1, 6 do
  local events = mtb.find("events", true)
  local b = events and mtb.find("button_accept", true, events)
  if not b then break end
  b:SimulateLClick()
  out.events = (out.events or 0) + 1
end
return out
