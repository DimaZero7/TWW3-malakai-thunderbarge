-- The real button. Warning panels that appear can be dismissed with button_tick by the caller.
local b = find_uicomponent(core:get_ui_root(), "hud_campaign", "faction_buttons_docker", "button_end_turn")
if not b then return "no button" end
local state = b:CurrentState()
b:SimulateLClick()
return "clicked in state " .. tostring(state)
