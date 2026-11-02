-- Dismisses open notices (one per call of the button, they queue), then ends the turn through the engine.
local out = {turn=cm:turn_number(), dismissed=0}
for _ = 1, 6 do
  local events = mtb.find("events", true)
  local b = events and mtb.find("button_accept", true, events)
  if not b then break end
  b:SimulateLClick()
  out.dismissed = out.dismissed + 1
end
cm.game_interface:end_turn()
return out
