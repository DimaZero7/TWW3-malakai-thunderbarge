-- Helpers of the crew panel's test (tools/crew_cycle.py, panel steps). Clicks the same components as the player, with SimulateLClick inside the game.
local Q = {}
_G.mtb_panel = Q
local RING = {'hud_campaign', 'faction_buttons_docker', 'button_group_management'}

function Q.ring()
  return find_uicomponent(core:get_ui_root(), unpack(RING))
end

function Q.button()
  return find_uicomponent(Q.ring(), 'button_mtb_crew')
end

-- One line with all there is to know; the steps of data/crew_cycle.json look for parts of it.
function Q.state()
  local ui = tww3_mtb_crew_ui
  local d = ui.describe()
  local open = {}
  for group, options in pairs(tww3_mtb_crew.unlocked()) do
    local keys = {}
    for key in pairs(options) do keys[#keys + 1] = key end
    table.sort(keys)
    open[#open + 1] = group .. ':' .. table.concat(keys, '+')
  end
  table.sort(open)
  local b = Q.button()
  local mark = b and find_uicomponent(b, 'alert')
  return mtb.dump({
    panel_open = tostring(ui.is_open()), panel_exists = tostring(mtb.find('mtb_crew_panel') ~= nil), roots = core:get_ui_root():ChildCount(),
    button = d.button, blocked = d.blocked, selected = d.selected, rows = d.rows, plates = d.plates, alert = tostring(mark and mark:Visible()),
    crew = tww3_mtb_crew.get(), unlocked = table.concat(open, ' '), status = tww3_mtb_crew.status, writes = tww3_mtb_crew.writes,
    orders = tww3_mtb_crew.orders(), upkeep = table.concat({tww3_mtb_crew.upkeep()}, '/'), gold = cm:get_faction('wh3_dlc25_dwf_malakai'):treasury(), turn = cm:turn_number(),
    income = tostring((select(2, pcall(common.get_context_value, 'CcoCampaignFaction', tostring(cm:get_faction('wh3_dlc25_dwf_malakai'):command_queue_index()), 'Income')))),
    net = tostring((select(2, pcall(common.get_context_value, 'CcoCampaignFaction', tostring(cm:get_faction('wh3_dlc25_dwf_malakai'):command_queue_index()), 'NetIncome')))),
  })
end

function Q.click_button()
  Q.button():SimulateLClick()
  return 'button clicked'
end

function Q.hover_button()
  Q.button():SimulateMouseOn()
  return Q.button():GetTooltipText()
end

function Q.unhover_button()
  Q.button():SimulateMouseOff()
  return 1
end

-- A panel of the game opening closes ours: the player opens it again.
local function reopen()
  if not tww3_mtb_crew_ui.is_open() then Q.click_button() end
end

function Q.plate(group)
  reopen()
  local b = mtb.find('mtb_crew_plate_' .. group, true)
  if not b then return 'no plate ' .. group end
  b:SimulateLClick()
  return 'plate ' .. group
end

function Q.zone(name)
  local b = mtb.find('mtb_crew_zone_' .. name, true)
  if not b then return 'no zone ' .. name end
  b:SimulateLClick()
  return 'zone ' .. name
end

-- The row of an option of the selected group: by what it shows.
function Q.row(option)
  reopen()
  for part in string.gmatch(tww3_mtb_crew_ui.describe().rows or '', '%S+') do
    local i, key = string.match(part, '^(%d+):(%w+)%[')
    if key == option then
      mtb.find('mtb_crew_row_' .. i, true):SimulateLClick()
      return 'row ' .. i .. ' ' .. key
    end
  end
  return 'no row ' .. option
end

function Q.hover_row(option)
  reopen()
  for part in string.gmatch(tww3_mtb_crew_ui.describe().rows or '', '%S+') do
    local i, key = string.match(part, '^(%d+):(%w+)%[')
    if key == option then
      local b = mtb.find('mtb_crew_row_' .. i, true)
      b:SimulateMouseOn()
      return b:GetTooltipText()
    end
  end
  return 'no row ' .. option
end

function Q.close()
  local b = mtb.find('mtb_crew_close', true)      -- a panel of the game may have closed ours already
  if b then b:SimulateLClick() end
  return 'close clicked'
end

-- Esc: the path the game uses for a stolen key, from the model to the callback. A real key press needs the focus and is not done by the test.
function Q.esc()
  cm:on_key_press_up('ESCAPE')
  return 'esc'
end

function Q.message()
  cm:show_message_event('wh3_dlc25_dwf_malakai', 'ui_text_replacements_localised_text_mtb_crew_lost_title', 'ui_text_replacements_localised_text_mtb_crew_lost_primary',
    'ui_text_replacements_localised_text_mtb_crew_lost_secondary', true, 1701)
  return 'message'
end
