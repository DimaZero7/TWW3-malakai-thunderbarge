-- The crew panel: a flat engineer's sketch of the barge with a callout for every group of seats, and on the right the options of the selected
-- group. Opened by a button in the HUD's ring by the end turn button, for a human Malakai who has the hull. The art is in data/ui (tools/crew_ui_art.py),
-- the layouts and the numbers come from tools/crew_ui.py. Nothing here touches the seats: a click goes to tww3_mtb_crew.choose().
--
--   tww3_mtb_crew_ui.open(), .close(), .is_open(), .select(group)     the tests click the same components as the player: see tools/tests/crew_panel.lua
--   tww3_mtb_crew_ui.describe()                                       the panel as text, for the tests
local DATA = {} --@CONFIG@

local HOME_FACTION = 'wh3_dlc25_dwf_malakai'
local LAYOUTS = 'ui/tww3_mtb/'
local BUTTON, PANEL = 'button_mtb_crew', 'mtb_crew_panel'
local CLOSE, PLATE, ROW, ZONE = 'mtb_crew_close', 'mtb_crew_plate_', 'mtb_crew_row_', 'mtb_crew_zone_'
local NEW = 'mtb_crew_ui_new'       -- saved: a building has unlocked something the player has not seen yet
local ESCAPE = 'mtb_crew_panel_escape'
local TOOLTIP_TITLE = 'Экипаж барки'
local HULL = 'wh3_dlc25_dwarf_spirit_of_grungni_airship_hull_2'
local MAX_ROWS = 6
local M = {selected = 'rifles'}
_G.tww3_mtb_crew_ui = M

local ui = nil      -- the panel's components while it is open

local function log(text)
    pcall(function() _G.tww3_mtb_campaign.file_log('[panel] ' .. tostring(text)) end)
    pcall(ModLog, '[tww3_mtb_crew_ui] ' .. tostring(text))
    if _G.mtb and _G.mtb.log then pcall(_G.mtb.log, 'crew_ui', text) end
end

local function crew() return _G.tww3_mtb_crew end

local function ours()
    local c = crew()
    return c and c.profile() == 'player' and cm:get_local_faction_name(true) == HOME_FACTION
end

-- The game's own name of a building, on the player's language.
local function building_name(key)
    local ok, name = pcall(common.get_localised_string, 'building_culture_variants_name_' .. key)
    if ok and type(name) == 'string' and name ~= '' then return name end
    return key
end

-- Why the panel cannot be opened; nil when it can.
function M.blocked()
    local c = crew()
    if not c then return 'Модуль экипажа не загружен.' end
    if string.sub(tostring(c.status), 1, 5) == 'stock' then
        return 'Нужен мод memreader Plus: без него экипаж не меняется, на барке стоковый экипаж. Он не подключён или не подошёл к этой версии игры.'
    end
    if not c.has_barge() then
        return 'Барки ещё нет. Постройте «' .. building_name(HULL) .. '» на вкладке барки: постройка соберёт барку и откроет панель экипажа.'
    end
end

local function make(parent, id, layout)
    return UIComponent(parent:CreateComponent(id, LAYOUTS .. layout))
end

-- The size also of the state's images: a resized component keeps them otherwise.
local function size(c, w, h)
    w, h = math.floor(w + 0.5), math.floor(h + 0.5)
    c:SetCanResizeWidth(true)
    c:SetCanResizeHeight(true)
    c:Resize(w, h)
    for i = 0, c:NumImages() - 1 do
        c:SetCanResizeCurrentStateImageWidth(i, true)
        c:SetCanResizeCurrentStateImageHeight(i, true)
        c:ResizeCurrentStateImage(i, w, h)
    end
end

local function at(c, x, y)
    c:SetDockingPoint(1)
    c:SetDockOffset(math.floor(x + 0.5), math.floor(y + 0.5))
end

local function image(parent, id, path, x, y, w, h)
    local c = make(parent, id, 'image')
    c:SetImagePath(path, 0)
    size(c, w, h)
    at(c, x, y)
    return c
end

local function text(parent, id, layout, x, y, w, h, value)
    local c = make(parent, id, layout)
    size(c, w, h)
    at(c, x, y)
    c:SetStateText(value or '')
    return c
end

local function card_path(row)
    if row.own_card then return LAYOUTS .. row.own_card .. '.png' end
    if row.card then return 'ui/units/icons/' .. row.card .. '.png' end
    return LAYOUTS .. 'card_empty.png'
end

local function row_of(group, option)
    for _, row in ipairs(DATA.groups[group].rows) do
        if row.key == option then return row end
    end
end

local function number_text(value)
    return string.format('%g', value)
end

local function damage_text(row)
    if row.damage_text then return row.damage_text end
    local n, parts = row.numbers or {}, {}
    -- a grenade's own 1 point is not worth a place
    if (n.damage or 0) + (n.ap or 0) > 1 then parts[#parts + 1] = n.damage .. '+' .. n.ap end
    if (n.blast or 0) + (n.blast_ap or 0) > 0 then parts[#parts + 1] = 'взрыв ' .. n.blast .. '+' .. n.blast_ap end
    return table.concat(parts, ', ')
end

-- The numbers as they are now: the guns' range with the signal chain, every crew's ammunition with the cargo chain.
local function range_now(group, row)
    local c, n = crew(), row.numbers or {}
    local steps = DATA.groups[group].range_steps
    local level = steps and c.boost_level(group) or 0
    return math.floor((n.range or 0) * (steps and steps[level] or 1) + 0.5)
end

local function ammo_now(row)
    return math.floor((row.numbers or {}).ammo * crew().ammo_mod() + 0.5)
end

local function tooltip(row, locked_by, spent, need_text)
    local lines = {'[[col:yellow]]' .. row.name .. '[[/col]]'}
    if row.about then lines[#lines + 1] = row.about end
    local n = row.numbers or {}
    if n.reload then
        lines[#lines + 1] = 'Урон (обычный + бронебойный): ' .. damage_text(row)
        if row.radius or n.radius then lines[#lines + 1] = 'Радиус взрыва: ' .. number_text(row.radius or n.radius) .. ' м' end
        if n.shots > 1 or n.volley > 1 then lines[#lines + 1] = 'Снарядов за выстрел: ' .. n.shots .. ', выстрелов за залп: ' .. n.volley end
        lines[#lines + 1] = 'Перезарядка: ' .. number_text(n.reload) .. ' с'
        lines[#lines + 1] = 'Дальность: ' .. (row.range_text or (range_now(M.selected, row) .. ' м'))
        lines[#lines + 1] = 'Запас группы на бой: ' .. tostring(ammo_now(row))
    end
    if (row.upkeep or 0) > 0 then lines[#lines + 1] = 'Содержание: ' .. row.upkeep .. ' золота за ход' end
    if locked_by then lines[#lines + 1] = 'Откроет постройка: ' .. locked_by end
    if need_text then lines[#lines + 1] = need_text end
    if spent then lines[#lines + 1] = 'Уже менялся в этот ход: следующий заказ в новом ходу' end
    return table.concat(lines, '\n')
end

-- ---------------- filling the panel ----------------
local function grey(c, on)
    c:ShaderTechniqueSet(on and 'set_greyscale_t0' or 'normal_t0', true)
    c:ShaderVarsSet(1, 1, 0, 0, true)
end

local function fill_row(view, row, active, open, order, changed, needs)
    view.button:SetVisible(true)
    local closed = not open[row.key]
    local ordered = order == row.key
    -- changed: this group's change of the turn is used; only what stands now can still be picked, to take an order back
    local spent = changed and not active and not ordered and not closed
    -- needs: the variant is open but its group has no bay yet
    local no_mount = needs ~= nil and not closed
    local locked = closed or spent or no_mount
    local state = 'active'
    if locked then state = 'inactive' elseif active then state = 'selected' elseif ordered then state = 'invalid' end
    view.button:SetState(state)
    view.card:SetImagePath(card_path(row), 0)
    grey(view.card, locked)
    view.name:SetVisible(not locked)
    view.name_grey:SetVisible(locked)
    view.name:SetStateText(row.name)
    view.name_grey:SetStateText(row.name)
    view.check:SetVisible(active)
    view.padlock:SetVisible(locked)
    local n = row.numbers or {}
    local has_numbers = n.reload ~= nil
    local values = {damage_text(row), has_numbers and (number_text(n.reload or 0) .. ' с') or '', has_numbers and (row.range_text or (range_now(M.selected, row) .. ' м')) or '', has_numbers and tostring(n.ammo or '') or ''}
    for i, stat in ipairs(view.stats) do
        stat.icon:SetVisible(has_numbers)
        grey(stat.icon, locked)
        stat.value:SetVisible(has_numbers and not locked)
        stat.value_grey:SetVisible(has_numbers and locked)
        stat.value:SetStateText(values[i])
        stat.value_grey:SetStateText(values[i])
    end
    local upkeep = row.upkeep or 0
    view.upkeep.icon:SetVisible(upkeep > 0)
    grey(view.upkeep.icon, locked)
    view.upkeep.value:SetVisible(upkeep > 0 and not locked)
    view.upkeep.value_grey:SetVisible(upkeep > 0 and locked)
    view.upkeep.value:SetStateText(tostring(upkeep))
    view.upkeep.value_grey:SetStateText(tostring(upkeep))
    local locked_by = closed and building_name(row.building) or nil
    local note = row.about or ''
    if ordered then note = 'Заказан: встанет со следующего хода' end
    if active and order then note = 'Стоит сейчас. Щелчок отменит заказ' end
    view.note:SetVisible(not locked)
    view.note_grey:SetVisible(locked)
    view.note:SetStateText(note)
    local need_text = no_mount and ('Нужны: ' .. needs) or nil
    view.note_grey:SetStateText(locked_by and ('Откроет: ' .. locked_by) or need_text or (spent and 'Уже менялся в этот ход' or ''))
    view.button:SetTooltipText(tooltip(row, locked_by, spent, need_text), true)
    view.row = row
    view.locked = locked
end

local function refresh()
    if not ui then return end
    local c = crew()
    local choice, open, orders = c.get(), c.unlocked(), c.orders()
    for group, plate in pairs(ui.plates) do
        local row = row_of(group, choice[group]) or {name = DATA.groups[group].none_name or tostring(choice[group])}
        plate.button:SetState(group == M.selected and 'selected' or 'active')
        plate.card:SetImagePath(card_path(row), 0)
        local next_row = orders[group] and row_of(group, orders[group])
        plate.variant:SetStateText(next_row and ('→ ' .. next_row.name) or row.name)
        ui.sel[group]:SetVisible(group == M.selected)
    end
    for group, layer in pairs(ui.occ) do
        layer:SetVisible(choice[group] ~= 'empty' and choice[group] ~= 'none')
    end
    for group, layer in pairs(ui.mount) do
        layer:SetVisible(choice[group] == 'empty')
    end
    local spec = DATA.groups[M.selected]
    ui.head:SetStateText(spec.name)
    ui.about:SetStateText(spec.about)
    local now_row = row_of(M.selected, choice[M.selected]) or {name = spec.none_name or tostring(choice[M.selected])}
    local needs = spec.mount_name and not c.mount_ready(M.selected) and (spec.mount_name .. ' (постройка «' .. building_name(spec.mount_building) .. '»)') or nil
    local order = orders[M.selected]
    local changed = c.changed(M.selected)
    ui.now:SetStateText('Сейчас: ' .. now_row.name)
    ui.next:SetStateText(order and ('Со следующего хода: ' .. row_of(M.selected, order).name) or (changed and 'Уже менялся в этот ход' or ''))
    for i, view in ipairs(ui.rows) do
        local row = spec.rows[i]
        if row then
            local row_needs = needs
            if not row_needs and spec.requires_name and row.key ~= 'empty' and not c.requires_ok(M.selected) then
                row_needs = spec.requires_name .. ' (постройка «' .. building_name(spec.requires_building) .. '»)'
            end
            fill_row(view, row, choice[M.selected] == row.key, open[M.selected], order, changed, row_needs)
        else
            view.button:SetVisible(false)
        end
    end
    local now, later = c.upkeep()
    ui.total:SetStateText('Содержание: ' .. now .. ' золота за ход' .. (later ~= now and ('. Со следующего хода: ' .. later) or ''))
end
M.refresh = refresh

function M.select(group)
    if not DATA.groups[group] then return false end
    M.selected = group
    refresh()
    return true
end

-- ---------------- building it ----------------
local function make_row(parent, i, x, y, w, h)
    local b = make(parent, ROW .. i, 'button_row')
    size(b, w, h)
    at(b, x, y)
    local card_h = h - 16
    local card_w = card_h * 60 / 130
    local view = {button = b}
    view.card = image(b, 'card', LAYOUTS .. 'card_empty.png', 9, 8, card_w, card_h)
    local tx = 9 + card_w + 10
    local tw = w - tx - 12
    view.name = text(b, 'name', 'text_name', tx, 7, tw - 44, 22, '')
    view.name_grey = text(b, 'name_grey', 'text_name_grey', tx, 7, tw - 44, 22, '')
    view.check = image(b, 'check', 'ui/skins/default/icon_check.png', w - 50, 5, 30, 30)
    view.padlock = image(b, 'padlock', 'ui/skins/default/icon_padlock.png', w - 50, 5, 30, 30)
    view.stats = {}
    local stat_y = 30
    -- the damage takes what is left after the other three, which have short values
    local short = math.floor(tw * 0.165)
    local widths = {tw - short * 4, short, short, short}
    local icons = {'icon_stat_ranged_damage.png', 'icon_stat_reload_time.png', 'icon_stat_range.png', 'icon_stat_ammo.png'}
    local sx = tx
    for s = 1, 4 do
        local stat = {}
        stat.icon = image(b, 'stat_icon' .. s, 'ui/skins/default/' .. icons[s], sx, stat_y, 18, 18)
        stat.value = text(b, 'stat' .. s, 'text_line', sx + 20, stat_y - 1, widths[s] - 22, 20, '')
        stat.value_grey = text(b, 'stat_grey' .. s, 'text_line_grey', sx + 20, stat_y - 1, widths[s] - 22, 20, '')
        view.stats[s] = stat
        sx = sx + widths[s]
    end
    view.upkeep = {icon = image(b, 'upkeep_icon', 'ui/skins/default/icon_treasury.png', sx, stat_y, 18, 18),
                   value = text(b, 'upkeep', 'text_line', sx + 20, stat_y - 1, short - 22, 20, ''),
                   value_grey = text(b, 'upkeep_grey', 'text_line_grey', sx + 20, stat_y - 1, short - 22, 20, '')}
    view.note = text(b, 'note', 'text_line', tx, h - 28, tw - 12, 22, '')
    view.note_grey = text(b, 'note_grey', 'text_copper', tx, h - 28, tw - 12, 22, '')
    return view
end

-- Clicking the bay itself in the drawing selects its group too.
local function make_zones(parent, group, scale)
    for i, zone in ipairs(DATA.art.zones[group]) do
        local c = make(parent, ZONE .. group .. '_' .. i, 'zone')
        size(c, zone[3] * 2 * scale, zone[4] * 2 * scale)
        at(c, (zone[1] - zone[3]) * scale, (zone[2] - zone[4]) * scale)
        c:SetTooltipText(DATA.groups[group].name .. '\n' .. DATA.groups[group].about, true)
    end
end

local function make_plate(parent, group, scale)
    local spec = DATA.art.plates[group]
    local w, h = DATA.art.plate[1] * scale, DATA.art.plate[2] * scale
    local b = make(parent, PLATE .. group, 'button_plate')
    size(b, w, h)
    at(b, spec.at[1] * scale, spec.at[2] * scale)
    b:SetTooltipText(DATA.groups[group].name .. '\n' .. DATA.groups[group].about, true)
    local card_h = h - 12
    local card_w = card_h * 60 / 130
    local plate = {button = b}
    plate.card = image(b, 'card', LAYOUTS .. 'card_empty.png', 6, 6, card_w, card_h)
    local tx = 6 + card_w + 8
    plate.name = text(b, 'name', 'text_copper', tx, h * 0.14, w - tx - 8, h * 0.36, DATA.groups[group].name)
    plate.variant = text(b, 'variant', 'text_line', tx, h * 0.5, w - tx - 8, h * 0.36, '')
    return plate
end

local function build()
    local root = core:get_ui_root()
    local W, H = root:Width(), root:Height()
    local panel_w, panel_h = math.min(W - 40, 1560), math.min(H - 30, 870)
    local title_h, pad = 66, 16
    local scheme_h = panel_h - title_h - pad - 6
    local scheme_w = scheme_h * DATA.art.size[1] / DATA.art.size[2]
    local column_w = panel_w - scheme_w - pad * 3
    if column_w < 360 then
        column_w = 360
        scheme_w = panel_w - column_w - pad * 3
        scheme_h = scheme_w * DATA.art.size[2] / DATA.art.size[1]
    end
    local scale = scheme_w / DATA.art.size[1]
    local top = title_h

    local backdrop = make(root, PANEL, 'backdrop')
    size(backdrop, W, H)
    backdrop:MoveTo(0, 0)
    backdrop:SetOpacity(150)
    local frame = make(backdrop, 'frame', 'frame')
    size(frame, panel_w, panel_h)
    frame:SetDockingPoint(5)
    frame:SetDockOffset(0, 0)
    frame:SetOpacity(255)

    local title_w = math.min(769, panel_w - 160)
    image(frame, 'title_back', 'ui/skins/wh_main_dwf_dwarfs/panel_title_large.png', (panel_w - title_w) / 2, 2, title_w, 62)
    text(frame, 'title', 'text_title', (panel_w - title_w) / 2, 8, title_w, 50, 'Экипаж «Духа Грунгни»')
    local close = UIComponent(frame:CreateComponent(CLOSE, 'ui/templates/round_small_button'))
    close:SetImagePath('ui/skins/default/icon_cross.png', 0)
    close:SetDockingPoint(3)
    close:SetDockOffset(-14, 14)
    close:SetTooltipText('Закрыть (Esc)', true)

    -- the scheme and its layers
    local sx, sy = pad, top
    local sheet = image(frame, 'scheme', LAYOUTS .. 'blueprint.png', sx, sy, scheme_w, scheme_h)
    local view = {plates = {}, occ = {}, sel = {}, rows = {}, mount = {}}
    local function layer(name)
        local place = DATA.art.layers[name]
        return image(sheet, name, LAYOUTS .. name .. '.png', place[1] * scale, place[2] * scale, place[3] * scale, place[4] * scale)
    end
    for _, group in ipairs(DATA.drawn) do
        if DATA.art.layers['mount_' .. group] then view.mount[group] = layer('mount_' .. group) end
        view.occ[group] = layer('occ_' .. group)
    end
    for _, group in ipairs(DATA.order) do
        view.sel[group] = layer('sel_' .. group)
    end
    local sheet_frame = make(frame, 'scheme_frame', 'frame_edge')
    size(sheet_frame, scheme_w + 8, scheme_h + 8)
    at(sheet_frame, sx - 4, sy - 4)
    for _, group in ipairs(DATA.order) do
        make_zones(sheet, group, scale)
    end
    for _, group in ipairs(DATA.order) do
        view.plates[group] = make_plate(sheet, group, scale)
    end

    -- the options of the selected group
    local cx = sx + scheme_w + pad
    local column = make(frame, 'column', 'frame_dark')
    size(column, column_w, scheme_h)
    at(column, cx, sy)
    view.head = text(column, 'head', 'text_head', 14, 6, column_w - 28, 28, '')
    view.about = text(column, 'about', 'text_body', 14, 32, column_w - 28, 22, '')
    view.now = text(column, 'now', 'text_line', 14, 54, (column_w - 28) * 0.42, 20, '')
    view.next = text(column, 'next', 'text_copper', 14 + (column_w - 28) * 0.42, 54, (column_w - 28) * 0.58, 20, '')
    local rows_top, foot_h = 80, 82
    local row_gap = 4
    local row_h = math.min(92, math.floor((scheme_h - rows_top - foot_h - row_gap * (MAX_ROWS - 1) - 8) / MAX_ROWS))
    for i = 1, MAX_ROWS do
        view.rows[i] = make_row(column, i, 8, rows_top + (i - 1) * (row_h + row_gap), column_w - 16, row_h)
    end
    view.total = text(column, 'total', 'text_copper', 14, scheme_h - foot_h - 2, column_w - 28, 22, '')
    text(column, 'foot', 'text_note', 14, scheme_h - foot_h + 20, column_w - 28, foot_h - 22,
        'Выбор действует со следующего хода, каждый отсек меняется раз за ход. Новые варианты открывают постройки на вкладке барки. Малакай у штурвала, команда на палубе и «Испепеляющий гром» на борту всегда.')
    view.root = backdrop
    return view
end

function M.is_open()
    return ui ~= nil
end

function M.close()
    if not ui then return end
    local root = ui.root
    ui = nil
    pcall(function() cm:release_escape_key_with_callback(ESCAPE) end)
    root:SetVisible(false)
    -- not in the click's own call: the clicked component belongs to it
    core:get_tm():real_callback(function()
        pcall(function() root:Destroy() end)
    end, 1, 'mtb_crew_panel_destroy')
    local b = find_uicomponent(core:get_ui_root(), 'hud_campaign', 'faction_buttons_docker', 'button_group_management', BUTTON)
    if b then b:SetState('active') end
    log('closed')
end

function M.open()
    if ui then return true end
    local why = M.blocked()
    if why or not ours() then return false, why or 'not the player\'s Malakai' end
    local ok, result = pcall(build)
    if not ok then
        log('build failed: ' .. tostring(result))
        local leftover = find_uicomponent(core:get_ui_root(), PANEL)
        if leftover then pcall(function() leftover:Destroy() end) end
        return false, result
    end
    ui = result
    refresh()
    cm:steal_escape_key_with_callback(ESCAPE, M.close)
    cm:set_saved_value(NEW, false)
    M.refresh_button()
    log('opened')
    return true
end

local function on_click(id)
    if id == BUTTON then
        if ui then M.close() else
            local ok, why = M.open()
            if not ok then
                log('open: ' .. tostring(why))
                M.refresh_button()
            end
        end
    elseif id == CLOSE or id == PANEL then
        M.close()
    elseif ui and string.sub(id, 1, #PLATE) == PLATE then
        M.select(string.sub(id, #PLATE + 1))
    elseif ui and string.sub(id, 1, #ZONE) == ZONE then
        M.select(string.match(id, '^' .. ZONE .. '(%a+)_'))
    elseif ui and string.sub(id, 1, #ROW) == ROW then
        local view = ui.rows[tonumber(string.sub(id, #ROW + 1))]
        if view and view.row and not view.locked then
            local ok, why = crew().choose(M.selected, view.row.key)
            if not ok then log('choose: ' .. tostring(why)) end
            refresh()
        end
    end
end

-- ---------------- the HUD's button ----------------
function M.refresh_button()
    if not ours() then return end
    local ring = find_uicomponent(core:get_ui_root(), 'hud_campaign', 'faction_buttons_docker', 'button_group_management')
    if not ring then
        log('no button group in the HUD yet')
        return
    end
    local b = find_uicomponent(ring, BUTTON)
    if not b then
        b = UIComponent(ring:CreateComponent(BUTTON, 'ui/templates/round_hud_button_toggle'))
        b:SetImagePath(LAYOUTS .. 'icon_button.png', 0)
        -- the same mark as the game's buttons have when something waits there
        local mark = UIComponent(b:CreateComponent('alert', LAYOUTS .. 'image'))
        mark:SetImagePath('ui/skins/default/icon_alert_message.png', 0)
        size(mark, 24, 24)
        at(mark, -2, -2)
        ring:Layout()
    end
    local why = M.blocked()
    b:SetVisible(true)
    if not ui then b:SetState(why and 'inactive' or 'active') end
    local mark = find_uicomponent(b, 'alert')
    if mark then mark:SetVisible(not why and not ui and cm:get_saved_value(NEW) == true) end
    b:SetTooltipText(TOOLTIP_TITLE .. '\n' .. (why or 'Кто стоит на барке: стрелки, пушки, купола, люки, палуба. Открытые постройками варианты выбираются здесь.'), true)
end

function M.describe()
    local out = {open = tostring(ui ~= nil), selected = M.selected, blocked = M.blocked() or 'no'}
    local b = find_uicomponent(core:get_ui_root(), 'hud_campaign', 'faction_buttons_docker', 'button_group_management', BUTTON)
    out.button = b and (b:CurrentState() .. ' visible=' .. tostring(b:Visible())) or 'none'
    if ui then
        local rows = {}
        for i, view in ipairs(ui.rows) do
            if view.button:Visible() then
                rows[#rows + 1] = i .. ':' .. view.row.key .. '[' .. view.button:CurrentState() .. ']'
            end
        end
        out.rows = table.concat(rows, ' ')
        local plates = {}
        for group, plate in pairs(ui.plates) do
            plates[#plates + 1] = group .. '=' .. plate.variant:GetStateText() .. '[' .. plate.button:CurrentState() .. ']'
        end
        table.sort(plates)
        out.plates = table.concat(plates, ' ')
    end
    return out
end

local function guarded(fn)
    return function(...)
        local ok, err = pcall(fn, ...)
        if not ok then log('error: ' .. tostring(err)) end
    end
end

M.on_click = guarded(on_click)

-- ---------------- the crew's cards on the game's tree of buildings ----------------
-- The tree (ui/campaign ui/building_construction_popup) has no place for this: its card list only shows units a building recruits. So a card of ours is laid on each tile whose
-- building opens a crew option: the option's own unit card in a bright frame coloured by its group (data/crew_options.json, card_frames), at the tile's top right, where the game has its own cards of units. The tree is made anew by every click, so it is looked
-- at by a timer while the slots are on the screen: the popups open on the mouse, with no event for a script. It lives inside the tile and goes away with it.
local CARD_W, CARD_H, CARD_STEP = 30, 54, 28

local function decorate_tile(tile, key)
    local cards = DATA.building_cards[key]
    if not cards then return 0 end
    local n = 0
    for i, card in ipairs(cards) do
        local id = 'mtb_crew_card_' .. i
        if not find_uicomponent(tile, id) then
            local x, y = 50 + (i - 1) * CARD_STEP, -24
            local picture = image(tile, id, card.card, x, y, CARD_W, CARD_H)
            local edge = image(tile, id .. '_frame', card.frame, x - 3, y - 3, CARD_W + 6, CARD_H + 6)
            picture:SetInteractive(false)
            edge:SetInteractive(false)
            n = n + 1
        end
    end
    return n
end

-- Tiles are found by name, by the game's own search. A walk over the open tree with ChildCount and Find breaks the game's script bindings for good: after it every Id() and ChildCount()
-- of every component returns a function (runs 20261104-163806, -164729, -165425).
function M.decorate_tree(slot)
    local popup = find_uicomponent(slot, 'building_construction_popup')
    if not popup then return 0 end
    local count = 0
    for key in pairs(DATA.building_cards) do
        local tile = find_uicomponent(popup, key) or find_uicomponent(popup, 'CcoBuildingLevelRecord' .. key)
        if tile then count = count + decorate_tile(tile, key) end
    end
    return count
end

function M.watch_tree()
    local list = find_uicomponent(core:get_ui_root(), 'horde_slot_list')
    if not list or not list:VisibleFromRoot() then return 0 end
    local count = 0
    for i = 1, list:ChildCount() - 1 do
        local slot = UIComponent(list:Find(i))
        local cat = find_uicomponent(slot, 'building_categories_popup')
        local pop = find_uicomponent(slot, 'building_construction_popup')
        if (cat and cat:Visible()) or (pop and pop:Visible()) then count = count + M.decorate_tree(slot) end
    end
    return count
end

M.start = guarded(function()
    local c = crew()
    log('start: crew=' .. tostring(c ~= nil) .. ' profile=' .. tostring(c and c.profile()) .. ' local=' .. tostring(cm:get_local_faction_name(true)) .. ' status=' .. tostring(c and c.status))
    if not c or not ours() then return end
    c.on_changed = guarded(function()
        refresh()
        M.refresh_button()
    end)
    c.on_unlocked = guarded(function()
        cm:set_saved_value(NEW, true)
        refresh()
        M.refresh_button()
    end)
    M.refresh_button()
    -- The HUD's button group sets its children's states itself while it starts up (a new campaign: as late as after the intro), so a button
    -- that must stay shut is looked at again. Only while it is shut: then nothing else changes the button.
    core:get_tm():repeat_real_callback(guarded(function()
        if not M.blocked() then return end
        local ring = find_uicomponent(core:get_ui_root(), 'hud_campaign', 'faction_buttons_docker', 'button_group_management')
        local b = ring and find_uicomponent(ring, BUTTON)
        if b and b:CurrentState() ~= 'inactive' then b:SetState('inactive') end
    end), 2000, 'mtb_crew_button_watch')
    for _, name in ipairs({'click', 'turn', 'panel', 'turn_start'}) do core:remove_listener('tww3_mtb_crew_ui_' .. name) end
    -- The tree opens on the mouse, without any event of its own: looked at twice a second while the horde's slots are on the screen, by name only.
    core:get_tm():repeat_real_callback(guarded(M.watch_tree), 500, 'mtb_crew_tree_watch')
    core:add_listener('tww3_mtb_crew_ui_click', 'ComponentLClickUp', function(context)
        local id = context.string
        return id == BUTTON or id == CLOSE or id == PANEL or string.sub(id, 1, #PLATE) == PLATE or string.sub(id, 1, #ROW) == ROW or string.sub(id, 1, #ZONE) == ZONE
    end, function(context) M.on_click(context.string) end, true)
    -- Anything else that takes the screen closes it: the end of the turn, another panel of the game.
    core:add_listener('tww3_mtb_crew_ui_turn', 'FactionTurnEnd', function(context) return context:faction():name() == HOME_FACTION end, guarded(M.close), true)
    core:add_listener('tww3_mtb_crew_ui_panel', 'PanelOpenedCampaign', function() return ui ~= nil end, guarded(M.close), true)
    core:add_listener('tww3_mtb_crew_ui_turn_start', 'FactionTurnStart', function(context) return context:faction():name() == HOME_FACTION end, guarded(M.refresh_button), true)
end)

_G.tww3_mtb_campaign.when_ready(M.start)
