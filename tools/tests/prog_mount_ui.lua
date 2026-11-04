-- The vanilla Mount block of the character panel (the panel must be open), by clicks. mtb_step: "open": opens the list;
-- "off": clicks "no mount" in the open list; "on": clicks the first mount in the open list. Returns what it did and the list's rows.
local block = mtb.find('mount_ancillary_category', true)
if not block then return 'no mount block' end
if mtb_step == 'open' then
  local b = mtb.find('dropdown_item', true, block)
  b:SimulateLClick()
  return 'opened, state ' .. tostring(b:CurrentState())
end
local list = mtb.find('ancillary_selector_mount', true)
if not list then return 'list not open' end
local box = mtb.find('list_box', true, list)
local rows = {}
local target
for i = 0, box:ChildCount() - 1 do
  local row = UIComponent(box:Find(i))
  if row:Visible() then
    rows[#rows + 1] = row:Id()
    if mtb_step == 'off' and row:Id() == 'entry_none' then target = row end
    if mtb_step == 'on' and row:Id() ~= 'entry_none' then target = target or row end
  end
end
if target then
  target:SimulateLClick()
  return 'clicked ' .. target:Id() .. ' of ' .. table.concat(rows, ',')
end
return 'nothing for ' .. tostring(mtb_step) .. ' in ' .. table.concat(rows, ',')
