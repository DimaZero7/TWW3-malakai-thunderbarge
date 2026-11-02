local b = mtb.find("button_attack", true)
if not b then return "no button_attack" end
b:SimulateLClick()
return "clicked"
