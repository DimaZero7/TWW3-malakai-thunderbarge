-- mtb_name = component id; first line of the caller sets it. Used through tools/rc_click.py-like one-liners.
local b = mtb.find(mtb_name, true)
if not b then return "no " .. tostring(mtb_name) end
b:SimulateLClick()
return "clicked " .. tostring(mtb_name)
