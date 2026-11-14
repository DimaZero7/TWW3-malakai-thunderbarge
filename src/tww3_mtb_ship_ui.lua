-- The airship screen «Дух Грунгни» in the game: the drawing of web/js/panel.js, ported function for function and line for line
-- (docs/design/port-to-game.md, 3). The same panel (1560 x 870 units on every root of 1600 x 900 and larger), the same two tabs, the same ids,
-- offsets and sizes, drawn from the same state: src/tww3_mtb_ship.lua (buildings, crews, news, the foot line) over the game adapter
-- src/tww3_mtb_game.lua, and src/tww3_mtb_crew_model.lua (the crew's numbers).
--
-- It draws through the vocabulary of web/js/gameui.js: make, size, at, image, text, and on each component the methods of the page's Component
-- (CreateComponent, Resize, SetDockOffset, SetImagePath, SetStateText, TextDimensions, SetTooltipText, SetState, SetVisible, SetOpacity,
-- ShaderTechniqueSet, SetImageColour, SetInteractive, SetPassive, SetHoverChild, AddHoverChild, SetLayer, SetGlow, ...). Two implementations of
-- those components exist: src/tww3_mtb_ship_uic.lua over the game's UIComponent (every engine unknown in one function there), and
-- tools/tests/fake_uic.lua for tools/ui_layout_check.py, which builds the reference states of build/ui_dump and compares them with the page's.
--
--   local UI = <this file>
--   local panel = UI.make_panel{root = root, M = M, cfg = ui_config, CM = crew_model, Ship = ship, flags = {}, keep = {tab, pan}, host = host}
--   panel.refresh(); panel.click(component); panel.hover(component); panel.escape()
--   host: {every(ms, fn, name), after(ms, fn, name), clear_tooltip()}: the game's real timers (core:get_tm()), none offline
--
-- What the page does with its browser that the game does differently, each said where it is: the clock-wipe of a construction (none: the turns
-- banner and the pale slot, question V5), the video of a crew (a still), the drag of the tree (none: the wheel, the arrows, the bar's track), the
-- mouse leaving a component (the game tells only the mouse coming onto one: src/tww3_mtb_ship_uic.lua hides what the last one showed).
-- Loaded as a module: it returns its table and sets nothing global.

local UI = {}

local floor, max, min, abs = math.floor, math.max, math.min, math.abs
-- The game replaces string.find / sub / len with UTF-8 versions (find: 3 arguments, no patterns; a 4th argument broke the game's bindings,
-- build/port_probe/lua_env_census.txt): this module takes the byte-exact originals once, so the same code runs alike in the game and offline.
local sfind, ssub = string.find_lua or string.find, string.sub_lua or string.sub
local function round(x) return floor(x + 0.5) end       -- JS Math.round
local function push(t, v) t[#t + 1] = v end
local function includes(t, v) for _, x in ipairs(t or {}) do if x == v then return true end end return false end
local function find(t, fn) for _, x in ipairs(t or {}) do if fn(x) then return x end end return nil end
local function filter(t, fn) local o = {} for _, x in ipairs(t or {}) do if fn(x) then o[#o + 1] = x end end return o end
local function map(t, fn) local o = {} for i, x in ipairs(t or {}) do o[i] = fn(x, i) end return o end
local function starts(s, p) return ssub(s, 1, #p) == p end
local function maxOf(list, f) local m = nil for _, x in ipairs(list) do local v = f(x); if m == nil or v > m then m = v end end return m end
local function minOf(list, f) local m = nil for _, x in ipairs(list) do local v = f(x); if m == nil or v < m then m = v end end return m end

-- a number as JS writes it (String(n)): a whole one without a point. The game's numbers are 32-bit floats (whole ones exact to 2^24) and its
-- string.format has no proven %g: a whole number by %d inside that range, any other by tostring
local function str(n)
    if type(n) ~= 'number' then return tostring(n == nil and '' or n) end
    if n == floor(n) and n > -16777216 and n < 16777216 then return string.format('%d', n) end
    return tostring(n)
end
UI.str = str

-- ---- texts as JS strings: by characters (UTF-8 here, UTF-16 units on the page; every text of the screen is in the BMP) ----
local function chars(s)
    local out = {}
    for ch in string.gmatch(s, '[%z\1-\127\194-\244][\128-\191]*') do out[#out + 1] = ch end
    return out
end
local SEPS = {[' '] = true, ['\t'] = true, ['\n'] = true, ['\r'] = true, [','] = true, ['.'] = true, [':'] = true, [';'] = true,
              ['\194\160'] = true}         -- \s of JS takes the no-break space too
local SPACE = {[' '] = true, ['\t'] = true, ['\n'] = true, ['\r'] = true, ['\194\160'] = true}
-- s.slice(0, n).replace(/[\s,.:;]+\S*$/, ''): the first n characters without the cut word at their end
local function cutWord(cs, n)
    local len = min(n, #cs)
    -- the leftmost i where a run of separators begins after which no space follows to the end
    local spaceAfter = {}           -- spaceAfter[j]: a space at j or later (j <= len)
    local seen = false
    for j = len, 1, -1 do if SPACE[cs[j]] then seen = true end spaceAfter[j] = seen end
    for i = 1, len do
        if SEPS[cs[i]] then
            local k = i
            while k <= len and SEPS[cs[k]] do
                if not (k + 1 <= len and spaceAfter[k + 1]) then
                    return table.concat(cs, '', 1, i - 1)
                end
                k = k + 1
            end
        end
    end
    return table.concat(cs, '', 1, len)
end

-- Numbers as the game's Russian texts write them (panel.js gameText): «+15%», a decimal comma
local function gameText(s)
    s = tostring(s == nil and '' or s)
    s = string.gsub(s, '(%d) %%', '%1%%')
    s = string.gsub(s, '(%d)%.(%d)', '%1,%2')
    return s
end
UI.gameText = gameText
local function num(v) return gameText(str(v)) end

-- the page's constants in one table (a Lua 5.1 function has at most 60 upvalues)
local K = {
    LAYOUTS = 'ui/tww3_mtb/',
    D = 'ui/skins/default/',
    DEMOLISH = 'mtb_ship_demolish',
    TAB = 'mtb_tab_',
    FIT = 'mtb_tree_fit',
    SIDE = 'mtb_side_',
    EDGE_IN = 4,
    TAG_GAP = 3,
    CREW_AREA = 'mtb_crew_area_',
    CREW_PICK = 'mtb_crew_card_pick_',
    CREW_CLOSE = 'mtb_crew_close_',
    UNIT_W = 60,
    UNIT_H = 130,
    CARD_W = 23,
    CARD_H = 50,
    CARD_OVERLAP = 10,
    INFO_W = 400,
    INFO_X = 18,
    INFO_TX = 48,
    INFO_UX = 34,
    INFO_UTX = 64,
    INFO_ROW = 32,
    INFO_PAD = 5,
    UNIT_INFO_W = 290,
    NODE = 74,
    LINE = 3,
    TREE = 'mtb_tree_node_',
    BAR = 22,
    ARROW = 22,
    HANDLE_MIN = 39,
    STEP = 106,
    LIT_IN = {255, 211, 106},
    LIT_OUT = {145, 231, 50},
    LIT = 5,
}
K.WEB_ART = K.LAYOUTS .. 'web/'       -- the stage layers (tools/web_art.py), packed at this path by tools/ship_ui.py

-- helpers as in the page
local function make(parent, id, layout) return parent:CreateComponent(id, layout) end
local function size(c, w, h) c:Resize(floor(w + 0.5), floor(h + 0.5)) end
local function at(c, x, y) c:SetDockOffset(floor(x + 0.5), floor(y + 0.5)) end
local function image(parent, id, path, x, y, w, h) local c = make(parent, id, 'image'); c:SetImagePath(path, 0); size(c, w, h); at(c, x, y); return c end
local function text(parent, id, layout, x, y, w, h, value) local c = make(parent, id, layout); size(c, w, h); at(c, x, y); c:SetStateText(value or ''); return c end
local function width(c) local w = c:TextDimensions(); return w end
local function tall(c) local _, h = c:TextDimensions(); return h end
UI.make, UI.size, UI.at, UI.image, UI.text = make, size, at, image, text

-- a line of text that may be longer than its box: cut at a word with "…", the whole of it in the tooltip
local function fitLine(c, value)
    c:SetStateText(value)
    c:SetTooltipText('', true)
    if not value or value == '' or width(c) <= c:Width() then return end
    local cs = chars(value)
    local lo, hi = 0, #cs
    while lo < hi do
        local mid = math.ceil((lo + hi) / 2)
        c:SetStateText(cutWord(cs, mid) .. '…')
        if width(c) <= c:Width() then lo = mid else hi = mid - 1 end
    end
    c:SetStateText(cutWord(cs, lo) .. '…')
    c:SetTooltipText(value, true)
end

-- The title plate (panel.js titlePlate): the game's panel_title_large.png and its text as one component, the text in the plate's dark field,
-- its ink centred there, smaller when the field is too small for it. The ink's measure is an engine unknown (src/tww3_mtb_ship_uic.lua InkDimensions).
local TITLE_PLATE = {path = 'ui/skins/wh_main_dwf_dwarfs/panel_title_large.png', w = 769, h = 69, seen = {84, 10, 685, 56}, field = {211, 15, 558, 49}, margin = 2}
local function titlePlate(parent, cx, cy, half, value)
    local P = TITLE_PLATE
    local k = max(0.05, min(1, 2 * half / (P.seen[3] - P.seen[1])))
    local plate = image(parent, 'title_back', P.path, cx - (P.seen[1] + P.seen[3]) / 2 * k, cy - (P.seen[2] + P.seen[4]) / 2 * k, P.w * k, P.h * k)
    local kx, ky = plate:Width() / P.w, plate:Height() / P.h
    local f = {l = plate.x + P.field[1] * kx, r = plate.x + P.field[3] * kx, t = plate.y + P.field[2] * ky, b = plate.y + P.field[4] * ky}
    local title = make(parent, 'title', 'text_title')
    title:SetStateText(value)
    local roomW, roomH = f.r - f.l - 2 * P.margin, f.b - f.t - 2 * P.margin
    local s = title:TextSize()
    for i = 0, 7 do
        title:SetTextSize(s)
        local ink = title:InkDimensions()
        local iw, ih = ink.right - ink.left, ink.ascent + ink.descent
        if iw <= roomW + 0.01 and ih <= roomH + 0.01 then break end
        s = max(1, floor(s * min(roomW / iw, roomH / ih) * 10) / 10 - 0.1 * i)
    end
    local ink = title:InkDimensions()
    local bw, bh = f.r - f.l, plate:Height()
    size(title, bw, bh)
    at(title, (f.l + f.r) / 2 - bw / 2 - ((ink.left + ink.right) / 2 - ink.w / 2), (f.t + f.b) / 2 - bh / 2 - (ink.fontAscent - ink.fontDescent) / 2 - (ink.descent - ink.ascent) / 2)
    return {plate = plate, text = title, field = f}
end

function UI.make_panel(env)
    local root, M, cfg, CM, Ship = env.root, env.M, env.cfg, env.CM, env.Ship
    local flags, keep, host = env.flags or {}, env.keep or {}, env.host or {}
    local data, art, blueprint = cfg.data, cfg.art, cfg.blueprint
    local KINDS, CREW_KINDS = cfg.kinds, cfg.crew_kinds
    local turnsText = Ship.turns_text
    local every = host.every or function() end
    local after = host.after or function() end
    local clearTooltip = host.clear_tooltip or function() end

    -- ---- the state in the page's shapes ----
    -- M.crew_options with what the page's data has besides (the card, the numbers, the notes): web/js/barge_buildings.js spreads the whole option
    local function crewOptions(g)
        local disp = data.groups[g].options
        return map(M.crew_options(g), function(o)
            local d = disp[o.key] or {}
            local out = {}
            for k, v in pairs(d) do out[k] = v end
            for k, v in pairs(o) do out[k] = v end
            return out
        end)
    end
    -- panel.js crewState
    local function crewState(g)
        local now, order, options = M.crew(g), M.crew_order(g), crewOptions(g)
        local standing = find(options, function(o) return o.key == now end)
        local ordered = find(options, function(o) return o.key == order end)
        local nobody = not standing or standing.empty
        return {place = M.crew_place(g), now = now, order = order, options = options, standing = standing, ordered = ordered, nobody = nobody,
                stand = (not nobody) and now or nil, coming = (ordered and not ordered.empty and nobody) and order or nil}
    end
    UI.crewState = crewState
    local function place(name) return art.places[name] or data.art.layers[name] end
    local rowsByKey = {}
    for i, r in ipairs(data.rows) do r.index = i; rowsByKey[r.key] = r end

    local view = {layers = {}, selected = nil, options = nil, crew = {}, data = data, tab = keep.tab == 'ship' and 'ship' or 'tree'}
    local W, H = root:Width(), root:Height()
    local panel_w, panel_h = min(W - 40, 1560), min(H - 30, 870)
    local pad, top, foot_h = 16, 66, 46
    local area = {x = pad, y = top, w = panel_w - 2 * pad, h = panel_h - top - foot_h - 12}
    local scheme_h = area.h
    local scheme_w = scheme_h * data.art.size[1] / data.art.size[2]
    if scheme_w > area.w then scheme_w = area.w; scheme_h = scheme_w * data.art.size[2] / data.art.size[1] end
    local scale = scheme_w / data.art.size[1]

    local function makeButton(parent, id, x, y, w, h, label)
        local b = make(parent, id, 'button_plate')
        size(b, w, h)
        at(b, x, y)
        local t = text(b, 'label', 'text_button', 0, 0, w, h, label)
        return {button = b, label = t}
    end

    -- ---------------- the drawing's layers, one rule for the big drawing and the small one ----------------
    local function layerPath(name) return (data.art.layers[name] and K.LAYOUTS or K.WEB_ART) .. name .. '.png' end
    local function drawingLayers(sheet, k, idp)
        idp = idp or ''
        local holders = {}
        for _, stage in ipairs({'pencil', 'build', 'ink'}) do
            holders[stage] = make(sheet, idp .. stage .. '_layers', 'layer_holder')
            size(holders[stage], sheet:Width(), sheet:Height())
            holders[stage]:SetPassive()
        end
        local out, order = {}, {}
        for _, part in ipairs(blueprint.part_order) do
            local spec = blueprint.parts[part]
            if spec.enabled or flags.all_parts then
                local layers = {}
                for _, stage in ipairs({'pencil', 'build', 'ink'}) do
                    local name = spec[stage]
                    if name then
                        local p = place(name)
                        layers[stage] = image(holders[stage], idp .. part .. '_' .. stage, layerPath(name), p[1] * k, p[2] * k, p[3] * k, p[4] * k)
                        layers[stage]:SetPassive()
                    end
                end
                out[part] = layers
                push(order, part)
            end
        end
        return out, order
    end
    local function paintDrawing(sheet, sheets, layers, order)
        if sheets and #sheets > 0 then
            local rule = find(sheets, function(r) return not r.part or M.stage(r.part) == r.stage end)
            sheet:SetImagePath(K.LAYOUTS .. rule.sheet .. '.png', 0)
        end
        for _, part in ipairs(order) do
            local l, stage = layers[part], M.stage(part)
            for _, s in ipairs({'pencil', 'build', 'ink'}) do if l[s] then l[s]:SetVisible(s == stage) end end
        end
    end
    local function paintNews(sheet, layers, order)
        local news = M.ship_news()
        local parts = news and news.parts or {}
        for _, part in ipairs(order) do local l = layers[part]; if l.ink then l.ink:SetGlow(includes(parts, part)) end end
        local whole = false
        for _, p in ipairs(parts) do if not layers[p] or not layers[p].ink then whole = true end end
        sheet:SetGlow(whole)
    end
    local function paintCrewLayers(set, g, hides)
        local st = crewState(g)
        if set.empty then set.empty:SetVisible(st.place and st.nobody and not st.coming) end
        for key, layer in pairs(set.layers) do layer:SetVisible(st.place and not st.nobody and key == st.now) end
        for key, layer in pairs(set.sketches) do layer:SetVisible(st.place and key == st.coming) end
        if hides and hides.ink and st.place and (not st.nobody or st.coming) then hides.ink:SetVisible(false) end
    end

    -- ---------------- the ship beside the tree ----------------
    local function makeShipColumn(parent, x, y, w, h)
        local k = w / data.art.size[1]
        local sh = round(data.art.size[2] * k)
        local col = {x = x, y = y, w = w, h = h, k = k}
        local sheet = image(parent, 'mtb_mini_ship', K.LAYOUTS .. blueprint.sheet .. '.png', x, y, w, sh)
        sheet:SetInteractive(true)
        sheet:SetHoverBrighten(0.12)
        sheet:SetTooltipText('Открыть вкладку «Корабль»', true)
        col.sheet = sheet
        col.layers, col.order = drawingLayers(sheet, k, 'mini_')
        local function lay(holder, name)
            local q = place(name)
            if not q then return nil end
            local c = image(holder, 'mini_' .. name, K.WEB_ART .. name .. '.png', q[1] * k, q[2] * k, q[3] * k, q[4] * k)
            c:SetPassive()
            return c
        end
        local crewHolder = make(sheet, 'mini_crew', 'layer_holder')
        size(crewHolder, w, sh)
        crewHolder:SetPassive()
        col.crew, col.crew_order = {}, {}
        for _, spec in ipairs(blueprint.crew_areas) do
            local g = spec.group
            local group = data.groups[g]
            if group and art.crew_areas[g] then
                local set = {spec = spec, empty = art.places['crew_' .. g .. '_empty'] and lay(crewHolder, 'crew_' .. g .. '_empty') or nil, layers = {}, sketches = {}}
                local emptyKey = group.mount or group.start
                for _, key in ipairs(group.option_order) do
                    if key ~= emptyKey and art.places['crew_' .. g .. '_' .. key] then set.layers[key] = lay(crewHolder, 'crew_' .. g .. '_' .. key) end
                    if art.places['crew_' .. g .. '_' .. key .. '_sketch'] then set.sketches[key] = lay(crewHolder, 'crew_' .. g .. '_' .. key .. '_sketch') end
                end
                col.crew[g] = set
                push(col.crew_order, g)
            end
        end
        col.malakai = {near = art.places.malakai_near and lay(crewHolder, 'malakai_near') or nil, far = art.places.malakai_far and lay(crewHolder, 'malakai_far') or nil}
        col.edge = make(parent, 'mtb_mini_ship_edge', 'frame_edge')
        size(col.edge, w + 8, sh + 8)
        at(col.edge, x - 4, y - 4)
        local rowsY, rowH = y + sh + 18, 64
        col.head = text(parent, 'mini_crew_head', 'text_head', x, rowsY, w, 32, 'Экипаж')
        local rule = make(parent, 'mini_crew_rule', 'separator_skull')
        size(rule, w, 14)
        at(rule, x, rowsY + 32)
        col.rows, col.row_order = {}, {}
        local i = 0
        for _, spec in ipairs(blueprint.crew_areas) do
            if data.groups[spec.group] then
                local g = spec.group
                local ry = rowsY + 52 + i * rowH
                i = i + 1
                local hit = make(parent, 'mtb_mini_crew_' .. g, 'hit_area')
                size(hit, w, rowH - 4)
                at(hit, x, ry)
                hit:SetInteractive(true)
                hit:SetHoverBrighten(0.15)
                local row = {g = g, hit = hit}
                row.card = image(hit, 'card', K.LAYOUTS .. 'card_empty.png', 4, 4, K.CARD_W, K.CARD_H)
                row.frame = image(row.card, 'frame', K.D .. 'unit_card_build_frame.png', 0, 0, K.CARD_W, K.CARD_H)
                row.padlock = image(hit, 'padlock', K.D .. 'padlock.png', 4 + (K.CARD_W - 16) / 2, 4 + 15, 16, 20)
                row.waiting = image(row.card, 'waiting', K.D .. 'icon_hourglass.png', K.CARD_W - 15, K.CARD_H - 17, 16, 16)
                row.name = text(hit, 'name', 'text_name', 38, 2, w - 42, 28, M.place_name(g))
                row.state = text(hit, 'state', 'text_caption_left', 38, 30, w - 42, 24, '')
                for _, c in ipairs({row.card, row.frame, row.padlock, row.waiting, row.name, row.state}) do c:SetPassive() end
                col.rows[g] = row
                push(col.row_order, g)
            end
        end
        return col
    end
    local function paintShipColumn(col)
        paintDrawing(col.sheet, view.sheets, col.layers, col.order)
        for _, g in ipairs(col.crew_order) do
            local set = col.crew[g]
            paintCrewLayers(set, g, set.spec.hides_part and col.layers[set.spec.hides_part])
        end
        local side, bp = M.malakai_side(), blueprint
        local ready = not bp.malakai_side or not bp.malakai_side.show_when or M.stage(bp.malakai_side.show_when) == 'ink'
        if col.malakai.near then col.malakai.near:SetVisible(ready and side == 'left') end
        if col.malakai.far then col.malakai.far:SetVisible(ready and side == 'right') end
        paintNews(col.sheet, col.layers, col.order)
        local newsPlaces = M.news_places()
        for _, g in ipairs(col.row_order) do
            local row = col.rows[g]
            local st, w = crewState(g), M.crew_words(g)
            local opener = M.place_opener(g)
            local shown = st.stand and st.standing or (st.coming and st.ordered or nil)
            row.card:SetImagePath(shown and shown.unit_card and shown.unit_card.picture or K.LAYOUTS .. 'card_empty.png', 0)
            row.card:ShaderTechniqueSet(st.place and 'normal_t0' or 'set_greyscale_t0')
            row.card:SetImageColour(255, 255, 255, (not st.place) and 0x80 or (st.coming and 0x8C or 255))
            row.padlock:SetVisible(not st.place)
            row.waiting:SetVisible(st.ordered ~= nil)
            local fresh = includes(newsPlaces, g)
            row.card:SetGlow(fresh)
            row.name:SetStateText((not st.place) and ('[[col:grey]]' .. M.place_name(g) .. '[[/col]]') or (fresh and ('[[col:yellow]]' .. M.place_name(g) .. '[[/col]]') or M.place_name(g)))
            local line
            if not st.place then line = '[[col:grey]]' .. (opener and ('Откроет «' .. opener.name .. '»') or 'Закрыто') .. '[[/col]]'
            elseif st.ordered then line = st.ordered.empty and (w.who .. ' ' .. w.leave .. ' в начале хода') or (st.ordered.name .. ': ' .. w.come .. ' в начале хода')
            elseif st.nobody then line = '[[col:grey]]' .. w.nobody .. '[[/col]]'
            else line = st.standing.name end
            fitLine(row.state, line)
            row.hit:SetTooltipText(row.state:GetStateText() ~= line and line or '', true)
        end
    end

    -- ---------------- the small unit card beside a slot, the unit card of a choice ----------------
    local function unitCard(parent, id, x, y, uc, colour)
        local card = image(parent, id, uc.picture, x, y, K.UNIT_W, K.UNIT_H)
        card.frame = image(card, 'frame', 'ui/skins/tww3_mtb/unit_card_frame_plain_' .. colour .. '.png', 0, 0, K.UNIT_W, K.UNIT_H)
        card.army = {image(card, 'health_back', K.D .. 'unit_card_back.png', 4, 3, 52, 12), image(card, 'health_fill', K.D .. 'bar_white.png', 4, 4, 52, 6),
                     text(card, 'unit_strength_number', 'text_card_number', 13, 2, 33, 14, str(uc.men))}
        card.army[2]:SetImageColour(44, 140, 30, 255)
        card.costPlate = make(card, 'recruitment_cost_background', 'cost_plate')
        size(card.costPlate, 52, 16)
        at(card.costPlate, 4, 3)
        image(card.costPlate, 'icon_treasury', K.D .. 'icon_treasury.png', 3, 0, 16, 16)
        card.cost = text(card.costPlate, 'RecruitmentCost', 'text_card_cost', 21, 1, 30, 16, '')
        local rest = {image(card, 'unit_cat_frame', K.D .. 'unit_card_semicircle.png', 3, 95, 55, 35), image(card, 'unit_category_icon', uc.category, 19, 106, 22, 22)}
        for _, c in ipairs({card.frame, card.army[1], card.army[2], card.army[3], card.costPlate, rest[1], rest[2]}) do c:SetPassive() end
        return card
    end
    local function slotUnitCard(parent, id, x, y, uc, colour, outline)
        local card = image(parent, id, uc.picture, x, y, K.CARD_W, K.CARD_H)
        if colour == nil then image(card, 'frame', K.D .. 'unit_card_build_frame.png', 0, 0, K.CARD_W, K.CARD_H)
        elseif outline then
            image(card, 'frame', K.D .. 'unit_card_build_frame.png', 0, 0, K.CARD_W, K.CARD_H)
            image(card, 'aboard', K.WEB_ART .. 'aboard_outline_' .. colour .. '.png', 0, 0, K.CARD_W, K.CARD_H)
        else image(card, 'frame', 'ui/skins/tww3_mtb/unit_card_build_frame_' .. colour .. '.png', 0, 0, K.CARD_W, K.CARD_H) end
        card:SetHoverBrighten(0.25)
        return card
    end

    -- ---------------- the game's building information window ----------------
    local function makeInfoTip(parent, id)
        local tip = make(parent, id, 'tooltip_frame')
        size(tip, K.INFO_W, 100)
        local t = {tip = tip, w = K.INFO_W, effects = {}, units = {}, id = id}
        t.title = text(tip, 'dy_title', 'text_info_title', 10, 1 + 2, K.INFO_W - 20, 38, '')
        t.hbar = make(tip, 'hbar', 'separator_skull')
        size(t.hbar, 380, 14)
        at(t.hbar, 10, 33)
        t.chain = text(tip, 'dy_secondary_title', 'text_info_centre', 18, 39 + 12 - 4, K.INFO_W - 36, 22, '')
        t.description = text(tip, 'description_window', 'text_info_italic', 24, 0, K.INFO_W - 48, 16, '')
        t.opensIcon = image(tip, 'effect_icon', K.D .. 'replenishement_positive.png', K.INFO_X, 0, 24, 24)
        t.opensTitle = text(tip, 'tx_enables', 'text_info', K.INFO_TX, 0, K.INFO_W - K.INFO_TX - K.INFO_X, 16, 'Открывает в экипаже:')
        t.armyIcon = image(tip, 'army_effect_icon', K.D .. 'replenishement_positive.png', K.INFO_X, 0, 24, 24)
        t.armyTitle = text(tip, 'tx_enables_army', 'text_info', K.INFO_TX, 0, K.INFO_W - K.INFO_TX - K.INFO_X, 16, 'Открывает найм:')
        t.army = {}
        t.rule = make(tip, 'instruction_rule', 'info_rule')
        size(t.rule, K.INFO_W - 2 * K.INFO_X, 1)
        t.reason = text(tip, 'reason', 'text_info', K.INFO_X + 2, 0, K.INFO_W - 2 * K.INFO_X - 4, 16, '')
        tip:SetLayer('hover')
        tip:SetVisible(false)
        return t
    end
    local function infoRows(t, effects, units, army)
        local function unitRow(key, i)
            local holder = image(t.tip, key .. '_cat_frame_' .. i, K.D .. 'unit_cat_holder_round.png', K.INFO_UX, 0, 26, 26)
            return {holder = holder, icon = image(holder, 'unit_category_icon', K.D .. 'replenishement_positive.png', 2, 2, 22, 22),
                    name = text(t.tip, key .. '_name_' .. i, 'text_info', K.INFO_UTX, 0, K.INFO_W - K.INFO_UTX - K.INFO_X, 16, '')}
        end
        while #t.army < army do push(t.army, unitRow('army', #t.army)) end
        while #t.effects < effects do
            local i = #t.effects
            push(t.effects, {icon = image(t.tip, 'effect_icon_' .. i, K.D .. 'replenishement_positive.png', K.INFO_X, 0, 24, 24),
                             text = text(t.tip, 'effect_' .. i, 'text_info', K.INFO_TX, 0, K.INFO_W - K.INFO_TX - K.INFO_X, 16, '')})
        end
        while #t.units < units do push(t.units, unitRow('unit', #t.units)) end
    end
    local function fillInfoTip(t, content)
        local function put(c, x, y) at(c, x, y); size(c, c:Width(), max(22, tall(c))) end
        local effects, opens, army = content.effects or {}, content.opens or {}, content.army or {}
        infoRows(t, #effects, #opens, #army)
        local Wd = content.width or K.INFO_W
        t.w = Wd
        size(t.title, Wd - 20, 38); size(t.hbar, Wd - 20, 14); size(t.chain, Wd - 36, 22); size(t.description, Wd - 48, 16)
        size(t.opensTitle, Wd - K.INFO_TX - K.INFO_X, 16); size(t.armyTitle, Wd - K.INFO_TX - K.INFO_X, 16)
        for _, r in ipairs(t.effects) do size(r.text, Wd - K.INFO_TX - K.INFO_X, 16) end
        for _, r in ipairs(t.units) do size(r.name, Wd - K.INFO_UTX - K.INFO_X, 16) end
        for _, r in ipairs(t.army) do size(r.name, Wd - K.INFO_UTX - K.INFO_X, 16) end
        size(t.rule, Wd - 2 * K.INFO_X, 1); size(t.reason, Wd - 2 * K.INFO_X - 4, 16)
        t.title:SetStateText(content.title or '')
        t.chain:SetStateText(content.chain or '')
        local hasReason = content.reason ~= nil and content.reason ~= ''
        local said = hasReason and content.reason or (content.note or '')
        t.reason:SetStateText(hasReason and ('[[col:game_red]]' .. gameText(content.reason) .. '[[/col]]') or gameText(said))
        t.rule:SetVisible(said ~= ''); t.reason:SetVisible(said ~= '')
        local reasonH = said ~= '' and (10 + max(22, tall(t.reason)) + 12) or 0
        local function entry(icon, iconX, iconH, label, textX, y)
            at(icon, iconX, y + K.INFO_PAD + 11 - iconH / 2)
            put(label, textX, y + K.INFO_PAD)
            return max(K.INFO_ROW, K.INFO_PAD + label:Height() + K.INFO_PAD)
        end
        local function layout(desc)
            local chain = content.chain ~= nil and content.chain ~= ''
            local y = chain and (39 + 30) or (39 - 6)
            t.chain:SetVisible(chain)
            t.description:SetStateText(desc)
            t.description:SetVisible(desc ~= '')
            if desc ~= '' then
                put(t.description, 24, y + 12)
                y = y + max(52, 12 + tall(t.description) + 12)
            end
            y = y + 2
            for i, row in ipairs(t.effects) do
                local e = effects[i]
                row.icon:SetVisible(e ~= nil); row.text:SetVisible(e ~= nil)
                if e then
                    row.icon:SetImagePath(e.icon or (K.D .. 'replenishement_positive.png'), 0)
                    row.text:SetStateText('[[col:' .. (e.good == false and 'game_red' or 'game_green') .. ']]' .. gameText(e.text) .. '[[/col]]')
                    y = y + entry(row.icon, K.INFO_X, 24, row.text, K.INFO_TX, y)
                end
            end
            local function block(icon, title, list, rows)
                icon:SetVisible(#list > 0); title:SetVisible(#list > 0)
                if #list > 0 then y = y + entry(icon, K.INFO_X, 24, title, K.INFO_TX, y) end
                for i, row in ipairs(rows) do
                    local o = list[i]
                    row.holder:SetVisible(o ~= nil); row.name:SetVisible(o ~= nil)
                    if o then
                        if o.category then row.icon:SetImagePath(o.category, 0) end
                        row.name:SetStateText(gameText(o.text))
                        y = y + entry(row.holder, K.INFO_UX, 26, row.name, K.INFO_UTX, y)
                    end
                end
            end
            block(t.opensIcon, t.opensTitle, opens, t.units)
            block(t.armyIcon, t.armyTitle, army, t.army)
            return y + 14
        end
        local y = layout(content.description or '')
        if said ~= '' then
            at(t.rule, K.INFO_X, y - 4)
            put(t.reason, K.INFO_X + 2, y + 6)
            y = y + reasonH - 4
        end
        size(t.tip, t.w, y)
        t.h = y
        t.has_reason = said ~= ''
        return t.h
    end

    -- ---------------- the game's unit information panel of a crew ----------------
    local function fxnum(v)        -- effects_model.mjs num
        if v == floor(v) then return str(v) end
        return (string.gsub(str(round(v * 100) / 100), '%.', ',', 1))
    end
    local function unitInfo(parent, id, spec)
        local Wd, o = K.UNIT_INFO_W, spec.option
        local n, group = o.numbers or {}, spec.group_data
        local panel = make(parent, id, 'unit_parchment')
        local info = {panel = panel, spec = spec}
        text(panel, 'tx_unit-type', 'text_unit_title', 12, 1 + 4, Wd - 24, 30, o.name)
        local hbar = make(panel, 'hbar', 'separator_skull')
        size(hbar, Wd - 20, 8)
        at(hbar, 10, 31)
        local vw = Wd - 28
        local vh = round(vw * 9 / 16)
        local y = 39
        local function clip()
            -- the clip of the crew at work: a still in the game (question V5), in the component the page plays its video in
            local video = make(panel, 'video', 'movie')
            size(video, vw, vh)
            at(video, 14, y + 2)
            info.video = video
            y = y + vh + 8
        end
        if flags.unitvideo == 'top' then clip() end
        if o.unit_card then image(panel, 'category', o.unit_card.category, 12, y + 4, 26, 26) end
        text(panel, 'custom_name_display', 'text_unit', 48, y, Wd - 60, 34, (spec.area and spec.area.kind_name) or (group.name .. ' экипажа'))
        y = y + 34
        if flags.unitvideo ~= 'top' then clip() end
        local note = text(panel, 'short_description', 'text_unit_note', 14, y, Wd - 28, 54, spec.text or o.about or '')
        y = y + max(20, tall(note)) + 8
        image(panel, 'icon_men', K.D .. 'icon_entity_small.png', 12, y + 2, 26, 26)
        text(panel, 'dy_men', 'text_unit', 40, y, 40, 30, o.unit_card and str(o.unit_card.men) or '')
        image(panel, 'icon_upkeep', K.D .. 'icon_income.png', 104, y + 2, 26, 26):SetTooltipText('Содержание за ход', true)
        text(panel, 'upkeep', 'text_unit', 132, y, 50, 30, str(o.upkeep))
        image(panel, 'icon_cost', K.D .. 'icon_treasury.png', 196, y + 2, 26, 26)
        text(panel, 'cost', 'text_unit', 224, y, 56, 30, str(o.hire))
        y = y + 32
        local head = make(panel, 'row_header_stats', 'unit_header')
        size(head, Wd - 16, 34)
        at(head, 8, y)
        text(head, 'dy_title', 'text_unit_centre', 0, 0, Wd - 16, 34, (spec.area and spec.area.stats_head) or 'Стрельба экипажа')
        y = y + 38
        local all = {}
        for _, k in ipairs(group.option_order) do local x = group.options[k].numbers or {}; if x.range and x.range ~= 0 then push(all, x) end end
        local function best(f, low) if low then return minOf(all, f) end return maxOf(all, f) end
        info.rows = {}
        local function row(key, icon, name, value, share)
            image(panel, 'icon_' .. key, icon, 10, y, 22, 22)
            text(panel, 'name_' .. key, 'text_unit', 36, y - 1, 130, 24, name)
            local back, fill = nil, nil
            if share ~= nil then
                back = image(panel, 'bar_back_' .. key, K.D .. 'bar_back.png', 166, y + 5, 60, 12)
                fill = image(panel, 'bar_' .. key, K.D .. 'bar_white.png', 168, y + 7, max(2, round(56 * min(1, share))), 8)
                fill:SetImageColour(235, 189, 124, 255)
            end
            local vx = share == nil and 166 or 228
            info.rows[key] = {value = text(panel, 'value_' .. key, 'text_unit_right', vx, y - 1, Wd - vx - 12, 24, value), fill = fill, back = back}
            y = y + 24
        end
        local ab = o.ability
        if ab then
            row('uses', K.D .. 'icon_stat_ammo.png', 'Выстрелов за бой', str(ab.uses), nil)
            if ab.damage ~= nil then
                row('damage', K.D .. 'icon_stat_ranged_damage.png', 'Урон выстрела', str(ab.damage + ab.ap), nil)
                row('ap', K.D .. 'modifier_icon_armour_piercing.png', 'Бронебойный', str(ab.ap), nil)
                if ab.vs_large and ab.vs_large ~= 0 then row('vs_large', K.D .. 'icon_stat_damage.png', 'Против крупных', '+' .. str(ab.vs_large), nil) end
            end
            row('range', K.D .. 'icon_stat_range.png', 'Дальность', num(ab.range), nil)
            if ab.blast and ab.blast ~= 0 then row('blast', K.D .. 'icon_stat_damage.png', 'Взрыв', str(ab.blast + ab.blast_ap) .. ' · ' .. str(ab.radius) .. ' м', nil) end
            row('wind_up', K.D .. 'icon_stat_reload_time.png', 'Замах, с', num(ab.wind_up), nil)
        end
        if n.range and n.range ~= 0 then
            local function dmg(x) return (x.damage + x.ap) * x.shots * x.volley end
            if dmg(n) > 1 then
                row('damage', K.D .. 'icon_stat_ranged_damage.png', 'Урон выстрела', str(dmg(n)), dmg(n) / best(dmg))
                row('ap', K.D .. 'modifier_icon_armour_piercing.png', 'Бронебойный', str(n.ap * n.shots * n.volley), n.ap / (n.damage + n.ap))
            end
            if o.range_text then row('range', K.D .. 'icon_stat_range.png', 'Дальность', o.range_text, nil)
            else row('range', K.D .. 'icon_stat_range.png', 'Дальность', num(n.range), n.range / best(function(x) return x.range end)) end
            row('reload', K.D .. 'icon_stat_reload_time.png', 'Перезарядка, с', num(n.reload), best(function(x) return x.reload end, true) / n.reload)
            if n.seats and n.seats ~= 0 then
                row('ammo', K.D .. 'icon_stat_ammo.png', 'Боезапас', '', n.volleys / best(function(x) return x.volleys or 0 end))
                info.ammoNote = text(panel, 'ammo_note', 'text_unit_note', 36, y - 4, Wd - 48, 18, '')
                y = y + 16
            else row('ammo', K.D .. 'icon_stat_ammo.png', 'Боезапас', str(n.ammo), n.ammo / best(function(x) return x.ammo end)) end
            if n.blast and n.blast ~= 0 then row('blast', K.D .. 'icon_stat_damage.png', 'Взрыв', str(n.blast + n.blast_ap) .. ' · ' .. str(n.radius) .. ' м', nil) end
            if o.fragments then row('fragments', K.D .. 'icon_stat_damage.png', 'Взрыв осколка', str(o.fragments.blast + o.fragments.blast_ap) .. ' · ' .. str(o.fragments.radius) .. ' м', nil) end
        end
        info.accuracy = text(panel, 'accuracy', 'text_unit_note', 14, y + 2, Wd - 28, 20, '')
        info.accuracy_y = y + 2
        info.base_h = y + 12
        local base = {ammo = n.ammo, range = n.range, reload = n.reload}
        info.state = make(parent, id .. '_state', 'tooltip_instruction')
        info.stateText = text(info.state, 'text', 'text_info', 13, 10, Wd - 23, 22, '')
        for _, c in ipairs({panel, info.state}) do c:SetLayer('hover'); c:SetPassive(); c:SetVisible(false) end
        function info.set(dyn)
            local bonus = dyn.bonus or {}
            local function better(kind, pct) if KINDS[kind].positive_good then return pct > 0 end return pct < 0 end
            local function colour(kind, pct, t)
                if pct and pct ~= 0 then return '[[col:' .. (better(kind, pct) and 'game_green' or 'game_red') .. ']]' .. t .. '[[/col]]' end
                return t
            end
            local ammoPct = bonus.ammo and bonus.ammo.pct or 0
            local ammo = n.ammo and CM.crew_ammo(n, ammoPct, o.unit_card and o.unit_card.men or 0) or {}
            info.ammo = ammo
            if info.ammoNote then
                info.rows.ammo.value:SetStateText(colour('ammo', ammoPct, str(ammo.total)))
                info.ammoNote:SetStateText(CM.ammo_share(ammo, spec.area and spec.area.group, spec.area and spec.area.per))
            elseif info.rows.ammo and not ab then info.rows.ammo.value:SetStateText(colour('ammo', ammoPct, str(ammo.total))) end
            for _, kind in ipairs({'range', 'reload'}) do
                local b, r = bonus[kind], info.rows[kind]
                if r and not (kind == 'range' and (o.range_text or ab)) then
                    local pct = b and b.pct or 0
                    r.value:SetStateText(colour(kind, pct, num((pct ~= 0) and CM.apply_pct(base[kind], pct, kind) or base[kind])))
                end
            end
            if info.rows.damage and not ab then
                local b = bonus.damage
                local d0 = (n.damage + n.ap) * n.shots * n.volley
                local pct = b and b.pct or 0
                info.rows.damage.value:SetStateText(colour('damage', pct, num((pct ~= 0) and CM.apply_pct(d0, pct, 'damage') or d0)))
            end
            local lines = {}
            for _, k in ipairs(CREW_KINDS) do
                if bonus[k] and bonus[k].pct and bonus[k].pct ~= 0 and (k ~= 'ammo' or (n.ammo and n.ammo ~= 0)) then
                    local pct = bonus[k].pct
                    local signed = (pct > 0 and '+' or (pct < 0 and '-' or '')) .. fxnum(abs(pct)) .. '%'
                    local from = table.concat(map(bonus[k].from, function(f) return f.name end), ', ')
                    push(lines, colour(k, pct, gameText(KINDS[k].name .. ' ' .. signed) .. (k == 'ammo' and (' (' .. str(ammo.base) .. ' → ' .. str(ammo.total) .. ')') or '') .. ': ' .. from))
                end
            end
            info.accuracy:SetStateText(table.concat(lines, '\n'))
            info.bonusLines = lines
            local linesH = #lines > 0 and max(20, tall(info.accuracy) + 4) or 0
            size(info.accuracy, Wd - 28, max(20, linesH))
            info.h = info.base_h + linesH
            size(panel, Wd, info.h)
            local armyLine = spec.army_building and ('«' .. spec.army_building .. '» открывает этот отряд и для найма в армию') or ''
            local crewLine = (dyn.reason and dyn.reason ~= '') and ('[[col:game_red]]' .. dyn.reason .. '[[/col]]') or (dyn.state or '')
            info.stateText:SetStateText(table.concat(filter({crewLine, armyLine}, function(x) return x ~= '' end), '\n'))
            info.has_state = ((dyn.reason and dyn.reason ~= '') or (dyn.state and dyn.state ~= '') or armyLine ~= '') and true or false
            info.state_h = info.has_state and (10 + max(22, tall(info.stateText)) + 10) or 0
            size(info.stateText, Wd - 23, max(22, info.state_h - 20))
            size(info.state, Wd, info.state_h ~= 0 and info.state_h or 10)
            info.state:SetBlank(not info.has_state)
            info.total = info.h + (info.has_state and info.state_h - 8 or 0)
        end
        function info.place(x, topY) at(panel, x, topY); at(info.state, x, topY + info.h - 8) end
        function info.hook(owner) owner:SetHoverChild(panel); owner:AddHoverChild(info.state) end
        info.set({})
        return info
    end
    -- What the game changes in a crew's panel (panel.js unitDyn)
    local function unitDyn(group, option, opt)
        local now, order = M.crew(group), M.crew_order(group)
        local sources = CM.crew_sources(M.config, function(k) return M.game.has_building(k) end, function(k) return M.game.standing(k) end)
        return {bonus = CM.crew_bonuses(sources, group),
                reason = opt.unlocked and '' or ('Откроет постройка «' .. opt.building.name .. '»'),
                state = option == order and ('В найме: ' .. M.crew_words(group).come .. ' в начале хода') or (option == now and M.crew_words(group).stand or '')}
    end

    -- The game's unit information panel of an army unit (panel.js armyInfo)
    local CASTE = {melee_infantry = 'Пехота ближнего боя', missile_infantry = 'Стрелковая пехота', warmachine = 'Боевая машина'}
    local armyList = {}
    for _, x in pairs(data.army_units) do push(armyList, x) end
    local function armyInfo(parent, id, u, building)
        local Wd, st = K.UNIT_INFO_W, u.stats
        local panel = make(parent, id, 'unit_parchment')
        local info = {panel = panel}
        text(panel, 'tx_unit-type', 'text_unit_title', 12, 1 + 4, Wd - 24, 30, u.name)
        local hbar = make(panel, 'hbar', 'separator_skull')
        size(hbar, Wd - 20, 8)
        at(hbar, 10, 31)
        local y = 39
        image(panel, 'category', u.card.category, 12, y + 4, 26, 26)
        text(panel, 'custom_name_display', 'text_unit', 48, y, Wd - 60, 34, CASTE[u.caste] or u.caste)
        y = y + 36
        image(panel, 'icon_men', K.D .. 'icon_entity_small.png', 12, y + 2, 26, 26)
        text(panel, 'dy_men', 'text_unit', 40, y, 60, 30, str(st.men) .. ((st.engines and st.engines ~= 0) and (' · ' .. str(st.engines)) or ''))
        image(panel, 'icon_upkeep', K.D .. 'icon_income.png', 104, y + 2, 26, 26):SetTooltipText('Содержание за ход', true)
        text(panel, 'upkeep', 'text_unit', 132, y, 50, 30, str(u.upkeep))
        image(panel, 'icon_cost', K.D .. 'icon_treasury.png', 196, y + 2, 26, 26)
        text(panel, 'cost', 'text_unit', 224, y, 56, 30, str(u.hire))
        y = y + 32
        local head = make(panel, 'row_header_stats', 'unit_header')
        size(head, Wd - 16, 34)
        at(head, 8, y)
        text(head, 'dy_title', 'text_unit_centre', 0, 0, Wd - 16, 34, 'Характеристики')
        y = y + 38
        local function best(f) local m = 1; for _, x in ipairs(armyList) do m = max(m, x.stats[f] or 0) end return m end
        local function row(key, icon, name, value, share)
            image(panel, 'icon_' .. key, icon, 10, y, 22, 22)
            text(panel, 'name_' .. key, 'text_unit', 36, y - 1, 130, 24, name)
            image(panel, 'bar_back_' .. key, K.D .. 'bar_back.png', 166, y + 5, 60, 12)
            image(panel, 'bar_' .. key, K.D .. 'bar_white.png', 168, y + 7, max(2, round(56 * min(1, share))), 8):SetImageColour(235, 189, 124, 255)
            text(panel, 'value_' .. key, 'text_unit_right', 228, y - 1, Wd - 228 - 12, 24, value)
            y = y + 24
        end
        local function stat(key, icon, name) if st[key] ~= nil then row(key, K.D .. icon, name, num(st[key]), st[key] / best(key)) end end
        stat('health', 'icon_stat_health.png', 'Здоровье')
        stat('armour', 'icon_stat_armour.png', 'Броня')
        stat('leadership', 'icon_stat_morale.png', 'Боевой дух')
        stat('speed', 'icon_stat_speed.png', 'Скорость')
        stat('melee_attack', 'icon_stat_attack.png', 'Атака')
        stat('melee_defence', 'icon_stat_defence.png', 'Защита')
        stat('charge', 'icon_stat_charge_bonus.png', 'Бонус натиска')
        if st.range and st.range ~= 0 then
            local shots = (st.shots and st.shots ~= 0) and st.shots or 1
            local bestM = 1
            for _, x in ipairs(armyList) do bestM = max(bestM, (x.stats.missile_damage or 0) + (x.stats.missile_ap or 0)) end
            row('missile', K.D .. 'icon_stat_ranged_damage.png', 'Урон выстрела', str((st.missile_damage + st.missile_ap) * shots), (st.missile_damage + st.missile_ap) / bestM)
            row('missile_ap', K.D .. 'modifier_icon_armour_piercing.png', 'Бронебойный', str(st.missile_ap * shots), st.missile_ap / max(1, st.missile_damage + st.missile_ap))
            stat('range', 'icon_stat_range.png', 'Дальность')
            stat('ammo', 'icon_stat_ammo.png', 'Боезапас')
            if st.reload and st.reload ~= 0 then row('reload', K.D .. 'icon_stat_reload_time.png', 'Перезарядка, с', num(st.reload), min(1, 4 / st.reload)) end
        end
        y = y + 10
        info.h = y
        size(panel, Wd, y)
        info.state = make(parent, id .. '_state', 'tooltip_instruction')
        local stateText = text(info.state, 'text', 'text_info', 13, 10, Wd - 23, 22, 'Найм в армию открывает постройка «' .. building .. '»')
        info.state_h = 10 + max(22, tall(stateText)) + 10
        size(stateText, Wd - 23, info.state_h - 20)
        size(info.state, Wd, info.state_h)
        info.total = info.h + info.state_h - 8
        for _, c in ipairs({panel, info.state}) do c:SetLayer('hover'); c:SetPassive(); c:SetVisible(false) end
        function info.place(x, topY) at(panel, x, topY); at(info.state, x, topY + info.h - 8) end
        function info.hook(owner) owner:SetHoverChild(panel); owner:AddHoverChild(info.state) end
        return info
    end

    -- The demo window of a place that shows a clip of the game (panel.js demoTip): a still in the game (question V5)
    local function demoTip(parent, id, x, bottom, spec)
        local tw, dpad = 300, 14
        local vw = tw - 2 * dpad
        local vh = round(vw * 9 / 16)
        local tip = image(parent, id, K.LAYOUTS .. 'backdrop.png', x, 0, tw, 100)
        local video = make(tip, 'video', 'movie')
        size(video, vw, vh)
        at(video, dpad, dpad)
        text(tip, 'tip_head', 'text_head', dpad, dpad + vh + 8, vw, 32, spec.head)
        local body = text(tip, 'tip_text', 'text_body', dpad, dpad + vh + 8 + 34, vw, 20, spec.text)
        local edge = make(tip, 'tip_edge', 'frame_edge')
        local demo = {tip = tip, video = video}
        function demo.fit()
            local bh = max(20, tall(body))
            if demo.bh == bh then return end
            demo.bh = bh
            size(body, vw, bh)
            local th = dpad + vh + 8 + 34 + bh + dpad
            size(tip, tw, th)
            at(tip, x, bottom - th)
            size(edge, tw, th)
            at(edge, 0, 0)
            demo.home = {x, bottom - th}
        end
        demo.fit()
        tip:SetPassive()
        tip:SetLayer('hover')
        tip:SetVisible(false)
        return demo
    end

    -- ---------------- a crew group's place on the drawing (panel.js makeCrewArea) ----------------
    local frame          -- the panel's frame: the windows of the crew's cards are its children
    local function makeCrewArea(sheet, spec, a)
        local g = spec.group
        local group, cbox = data.groups[g], a.area
        local ax, ay = cbox[1] * scale, cbox[2] * scale
        local areaC = make(sheet, K.CREW_AREA .. g, 'hit_area')
        size(areaC, cbox[3] * scale, cbox[4] * scale)
        at(areaC, ax, ay)
        areaC:SetInteractive(true)
        local function has(name) return art.places[name] ~= nil end
        local tq = place('crew_' .. g .. '_tag_plus')
        local clear = K.EDGE_IN + K.TAG_GAP
        local tx0, ty0 = tq[1] * scale, tq[2] * scale
        local tx1, ty1 = tx0 + tq[3] * scale, ty0 + tq[4] * scale
        local tdx = max(0, clear - tx0) - max(0, tx1 - (scheme_w - clear))
        local tdy = max(0, clear - ty0) - max(0, ty1 - (scheme_h - clear))
        local function shift(name) if sfind(name, '_tag_', 1, true) then return tdx, tdy end return 0, 0 end
        local function lay(name)
            local q = place(name)
            local dx, dy = shift(name)
            local c = image(areaC, name, K.WEB_ART .. name .. '.png', q[1] * scale - ax + dx, q[2] * scale - ay + dy, q[3] * scale, q[4] * scale)
            c:SetPassive()
            return c
        end
        local crew = {spec = spec, area = areaC, group = g, layers = {}, open = false}
        local gl = a.glow
        local prefix = gl.prefix or 'crew_glow'
        crew.glow = image(areaC, 'crew_glow', K.WEB_ART .. prefix .. '_0.png', gl.box[1] * scale - ax + tdx, gl.box[2] * scale - ay + tdy, gl.box[3] * scale, gl.box[4] * scale)
        crew.glow:SetPassive()
        crew.glow:SetTopmost()          -- over the drawing's brass edge (the page's z-index 1)
        crew.glow.phases = {}
        for i = 1, gl.phases - 1 do
            local ph = image(crew.glow, 'phase_' .. i, K.WEB_ART .. prefix .. '_' .. i .. '.png', 0, 0, gl.box[3] * scale, gl.box[4] * scale)
            ph:SetVisible(false)
            push(crew.glow.phases, ph)
        end
        crew.phase = 0
        every(a.step_ms or 110, function()
            crew.phase = (crew.phase + 1) % gl.phases
            crew.glow:SetImageShown(crew.phase == 0)
            for i, ph in ipairs(crew.glow.phases) do ph:SetVisible(crew.phase == i) end
        end, 'mtb_crew_glow_' .. g)
        crew.empty = has('crew_' .. g .. '_empty') and lay('crew_' .. g .. '_empty') or nil
        crew.sketches = {}
        for _, key in ipairs(group.option_order) do if has('crew_' .. g .. '_' .. key .. '_sketch') then crew.sketches[key] = lay('crew_' .. g .. '_' .. key .. '_sketch') end end
        crew.tags = {plus = lay('crew_' .. g .. '_tag_plus'), swap = lay('crew_' .. g .. '_tag_swap'), wait = lay('crew_' .. g .. '_tag_wait')}
        crew.hover = make(areaC, 'hover', 'hover_holder')
        size(crew.hover, cbox[3] * scale, cbox[4] * scale)
        crew.hover:SetPassive()
        local function inHover(name)
            local q = place(name)
            local dx, dy = shift(name)
            return image(crew.hover, name, K.WEB_ART .. name .. '.png', q[1] * scale - ax + dx, q[2] * scale - ay + dy, q[3] * scale, q[4] * scale)
        end
        inHover('crew_' .. g .. '_hover')
        crew.hoverTags = {plus = inHover('crew_' .. g .. '_tag_plus_hover'), swap = inHover('crew_' .. g .. '_tag_swap_hover'), wait = inHover('crew_' .. g .. '_tag_wait_hover')}
        areaC:SetHoverChild(crew.hover)
        local emptyKey = group.mount or group.start
        for _, key in ipairs(group.option_order) do if key ~= emptyKey and has('crew_' .. g .. '_' .. key) then crew.layers[key] = lay('crew_' .. g .. '_' .. key) end end
        -- the choice
        local options = crewOptions(g)
        local ppad, slot_w = 26, 106
        local ph = ppad + 32 + 4 + K.UNIT_H + 4 + 42 + 24 + 26
        local pw = max(ppad * 2 + slot_w * #options, 440)
        local below, above = ay + cbox[4] * scale + 14, ay - 14 - ph
        local py = (below + ph <= scheme_h - 6) and below or (above >= 6 and above or max(6, scheme_h - ph - 6))
        local pick = image(sheet, 'mtb_crew_pick_' .. g, K.LAYOUTS .. 'backdrop.png', 0, py, pw, ph)
        pick:SetInteractive(true)
        pick:SetLayer('click')
        crew.pick = pick
        crew.head = text(pick, 'pick_head', 'text_head', ppad, ppad - 4, pw - 2 * ppad - 34, 32, spec.head or group.name)
        pw = max(pw, width(crew.head) + 2 * ppad + 34 + 8)
        size(pick, pw, ph)
        size(crew.head, pw - 2 * ppad - 34, 32)
        at(pick, max(6, min(ax, scheme_w - pw - 12)), py)
        local cross = image(pick, K.CREW_CLOSE .. g, K.D .. 'icon_cross.png', pw - ppad - 24, ppad - 2, 22, 22)
        cross:SetInteractive(true)
        local slot_y, slot_h = ppad + 32 + 4, K.UNIT_H + 4 + 42
        local clips = {}
        for _, c in ipairs(blueprint.crew_cards) do if c.group == g then clips[c.option] = c end end
        crew.slots = map(options, function(o, i)
            local hit = make(pick, K.CREW_PICK .. g .. ':' .. o.key, 'hit_area')
            size(hit, slot_w, slot_h)
            at(hit, ppad + (i - 1) * slot_w, slot_y)
            hit:SetInteractive(true)
            hit:SetHoverBrighten(0.15)
            local cx = (slot_w - K.UNIT_W) / 2
            local card = o.unit_card and unitCard(hit, 'card', cx, 0, o.unit_card, group.card_frame or 'gold') or image(hit, 'card', K.LAYOUTS .. 'card_empty.png', cx, 0, K.UNIT_W, K.UNIT_H)
            local slot = {key = o.key, hit = hit, card = card}
            slot.selected = image(card, 'selected', K.D .. 'unit_card_selected.png', 0, 0, K.UNIT_W, K.UNIT_H)
            slot.padlock = image(card, 'padlock', K.D .. 'padlock.png', (K.UNIT_W - 26) / 2, 46, 26, 33)
            slot.turnsBanner = make(card, 'Turns', 'turns_banner')
            size(slot.turnsBanner, 70, 34)
            at(slot.turnsBanner, -5, 48)
            slot.turns = text(slot.turnsBanner, 'turns', 'text_card_turns', 25, 1, 30, 34, '1')
            slot.name = text(hit, 'name', 'text_caption', 2, K.UNIT_H + 4, slot_w - 4, 40, '')
            for _, c in ipairs({card, slot.name}) do c:SetPassive() end
            if not o.empty then
                local clip = clips[o.key] or {}
                slot.info = unitInfo(frame, 'crew_pick_info_' .. g .. '_' .. o.key, {option = o, group_data = group, text = clip.text or o.about or '', area = spec})
                slot.info.hook(hit)
            end
            return slot
        end)
        crew.foot = text(pick, 'pick_foot', 'text_caption_left', ppad, slot_y + slot_h + 2, pw - 2 * ppad, 22, '')
        local edge = make(pick, 'pick_edge', 'frame_edge')
        size(edge, pw, ph)
        at(edge, 0, 0)
        pick:SetVisible(false)
        return crew
    end
    local function openArea()
        for _, g in ipairs(view.area_order or {}) do if view.crewAreas[g].open then return view.crewAreas[g] end end
        return nil
    end

    -- ---------------- the tree of buildings (panel.js makeFileTree) ----------------
    local lightLinks, placeTips, fillInfo, placeInfo
    local function makeFileTree(areaBox, keepPan)
        local rows = data.rows
        local pane = make(view.pane, 'tree_page', 'tree_page')
        size(pane, areaBox.w, areaBox.h)
        at(pane, 0, 0)
        local cw, ch = data.content[1], data.content[2]
        local edge, gap, colGap = 10, 4, 14
        local colW = max(260, min(320, areaBox.w - 2 * edge - K.BAR - gap - colGap - cw))
        local avail = areaBox.w - 2 * edge - colGap - colW
        local needV = ch > areaBox.h - 2 * edge
        local needH = cw > avail - (needV and K.BAR + gap or 0)
        needV = ch > areaBox.h - 2 * edge - (needH and K.BAR + gap or 0)
        local ww = avail - (needV and K.BAR + gap or 0)
        local wh = areaBox.h - 2 * edge - (needH and K.BAR + gap or 0)
        local win = make(pane, 'tree_window', 'tree_window')
        size(win, ww, wh)
        at(win, edge, edge)
        win:SetInteractive(true)
        win:SetClipChildren(true)
        local holder = make(win, 'tree_holder', 'tree_holder')
        size(holder, max(1, cw), max(1, ch))
        local pan = {x = 0, y = 0, z = 1, win = win, pane = pane, holder = holder, w = ww, h = wh, cw = cw, ch = ch, needH = needH, needV = needV}
        view.pan = pan
        view.column = makeShipColumn(pane, areaBox.w - edge - colW, edge + 4, colW, wh)
        local lines = make(holder, 'tree_lines', 'layer_holder')
        size(lines, max(1, cw), max(1, ch))
        lines:SetPassive()
        -- the links and their pieces (tools/ship_ui_config.mjs: tree_model.mjs linkSegments and lineMarks, as the page computes them)
        local links = {}
        for _, l in ipairs(data.links) do push(links, {from = rows[l.from].key, to = rows[l.to].key, colour = l.colour, segs = l.segs, imgs = {}}) end
        for n, p in ipairs(data.lines) do
            local x0, y0, x1, y1, li = p[1], p[2], p[3], p[4], p[5]
            local colour = links[li].colour
            push(links[li].imgs, image(lines, 'tree_line_' .. (n - 1), K.WEB_ART .. ((colour ~= '') and ('tree_line_' .. colour .. '.png') or 'tree_line.png'),
                min(x0, x1) - K.LINE / 2, min(y0, y1) - K.LINE / 2, abs(x1 - x0) + K.LINE, abs(y1 - y0) + K.LINE))
        end
        view.links = links
        view.junctions = map(data.junctions, function(j, i) return image(lines, 'tree_junction_' .. (i - 1), K.WEB_ART .. 'tree_line.png', j[1] - 3.5, j[2] - 3.5, 7, 7) end)
        view.litLines = make(holder, 'tree_lines_lit', 'layer_holder')
        size(view.litLines, max(1, cw), max(1, ch))
        view.litLines:SetPassive()
        view.tree = map(rows, function(r, i1)
            local i = i1 - 1
            local nx, ny = r.x, r.y
            local node = {key = r.key, name = r.name, row = r, branch = (r.branch ~= '') and {colour = r.branch} or nil}
            local b = image(holder, K.TREE .. i, K.D .. 'building_frame.png', nx, ny, K.NODE, K.NODE)
            b:SetInteractive(true)
            local v = {node = node, button = b}
            v.icon = image(b, 'icon', (r.icon ~= '' and r.icon) or (K.D .. 'icon_check.png'), 0, 0, K.NODE, K.NODE)
            v.plain = image(b, 'plain', node.branch and (K.WEB_ART .. 'branch_frame_' .. r.branch .. '.png') or (K.D .. 'building_frame_plain.png'), 0, 0, K.NODE, K.NODE)
            v.branch = node.branch
            v.frameSelected = image(b, 'selected', node.branch and (K.WEB_ART .. 'branch_frame_' .. r.branch .. '_selected.png') or (K.D .. 'building_frame_selected.png'), 0, 0, K.NODE, K.NODE)
            -- the clock-wipe of a construction: not in the game (question V5: the turns banner and the pale slot say it); the component stays, hidden
            v.constructing = image(b, 'constructing', K.D .. 'constructing_1.png', 6, 6, K.NODE - 12, K.NODE - 12)
            v.constructing:SetImageColour(255, 255, 255, 0x64)
            v.check = image(b, 'check', K.D .. 'icon_check_green.png', 44, 48, 31, 28)
            v.padlock = image(b, 'padlock', K.D .. 'padlock.png', 3, 2, 20, 25)
            if r.in_line and r.line_level <= 5 then v.level = image(b, 'building_level', K.D .. 'settlement_silver_numeral_' .. r.line_level .. '.png', 0, 54, 20, 20) end
            v.hover = image(b, 'hover', K.D .. 'building_frame_hover.png', -K.NODE * 8 / 74, -K.NODE * 8 / 74, K.NODE * 90 / 74, K.NODE * 90 / 74)
            v.hoverSelected = image(b, 'hover_selected', K.D .. 'building_frame_selected_hover.png', 0, 0, K.NODE, K.NODE)
            v.hoverSelected:SetVisible(false)
            b:SetHoverChild(v.hover)
            b:SetHoverBrighten(0.4)
            local function ring(id, cr, cg, cb)
                local c = image(holder, 'mtb_slot_' .. id .. '_' .. i, K.D .. 'building_frame_hover.png', nx - K.NODE * 8 / 74, ny - K.NODE * 8 / 74, K.NODE * 90 / 74, K.NODE * 90 / 74)
                c:SetImageColour(cr, cg, cb, 255)
                c:SetPassive()
                c:SetVisible(false)
                return c
            end
            v.markIn = ring('lit_needed', 255, 211, 106)
            v.markOut = ring('lit_opened', 145, 231, 50)
            v.deny = ring('refused', 226, 40, 40)
            b.on_enter = function() view.hoverSlot = v; fillInfo(v); placeInfo(v); lightLinks() end
            b.on_leave = function() if view.hoverSlot == v then view.hoverSlot = nil end; lightLinks() end
            v.turnsBanner = image(b, 'turns_banner', K.D .. 'turns_banner_queued.png', -6, K.NODE - 20, K.NODE + 12, 24)
            v.turns = text(b, 'turns', 'text_line', 22, K.NODE - 20, K.NODE - 22, 24, '')
            v.cost = image(holder, K.TREE .. 'cost_' .. i, K.D .. 'icon_banner_bg.png', nx + 3, ny + K.NODE + 2, 62, 20)
            v.costRed = image(v.cost, 'red', K.D .. 'red_text_banner_shadow.png', 0, 0, 62, 20)
            image(v.cost, 'coins', K.D .. 'icon_treasury.png', 4, 2, 16, 16)
            v.costText = text(v.cost, 'value', 'text_line', 22, 0, 40, 20, '')
            v.info = makeInfoTip(frame, 'building_information_' .. i)
            b:AddHoverChild(v.info.tip)
            return v
        end)
        -- the crew a building opens: small unit cards beside its slot, as the game's building browser places them
        local clips = {}
        for _, c in ipairs(blueprint.crew_cards) do clips[c.group .. ':' .. c.option] = c end
        view.plates = {}
        for _, v in ipairs(view.tree) do
            local r = v.node.row
            local total = #r.cards + (#r.folded > 0 and 1 or 0)
            local row_w = K.CARD_W + (total - 1) * (K.CARD_W - K.CARD_OVERLAP)
            local function cardAt(i) return v.button.x + K.NODE + 17 - row_w + i * (K.CARD_W - K.CARD_OVERLAP), v.button.y - 22 end
            for i1, item in ipairs(r.cards) do
                local cx, cy = cardAt(i1 - 1)
                if item.crew then
                    local gd = data.groups[item.group]
                    local od = gd.options[item.option]
                    local card = slotUnitCard(holder, 'mtb_crew_card_' .. r.id .. '_' .. item.option, cx, cy, od.unit_card, gd.card_frame or 'gold', flags.aboard == 'outline')
                    local waiting = image(card, 'waiting', K.D .. 'icon_hourglass.png', K.CARD_W - 15, K.CARD_H - 17, 16, 16)
                    local standing = image(card, 'standing', K.D .. 'icon_check_green.png', K.CARD_W - 16, K.CARD_H - 15, 17, 15)
                    local clip = clips[item.group .. ':' .. item.option] or {}
                    local info = unitInfo(frame, 'crew_info_' .. r.id .. '_' .. item.option, {option = od, group_data = gd, text = clip.text or od.about or '',
                        area = find(blueprint.crew_areas, function(a) return a.group == item.group end), army_building = item.army and r.name or nil})
                    info.hook(card)
                    push(view.crew, {card = card, info = info, tip = info.panel, building = r.key, group = item.group, option = item.option, alsoArmy = item.army or nil,
                                     waiting = waiting, standing = standing, v = v, cardY = cy})
                else
                    local u = data.army_units[item.unit]
                    local card = slotUnitCard(holder, 'mtb_army_card_' .. r.id .. '_' .. u.key, cx, cy, u.card, nil, false)
                    local info = armyInfo(frame, 'army_info_' .. r.id .. '_' .. u.key, u, r.name)
                    info.hook(card)
                    push(view.crew, {card = card, info = info, tip = info.panel, building = r.key, army = u.key, v = v, cardY = cy})
                end
            end
            if #r.folded > 0 then
                local px, py = cardAt(#r.cards)
                local plate = image(holder, 'mtb_cards_more_' .. r.id, K.D .. 'unit_card_back.png', px, py, K.CARD_W, K.CARD_H)
                image(plate, 'frame', K.D .. 'unit_card_build_frame.png', 0, 0, K.CARD_W, K.CARD_H):SetPassive()
                text(plate, 'count', 'text_card_more', 0, 0, K.CARD_W, K.CARD_H, '+' .. #r.folded):SetPassive()
                plate:SetHoverBrighten(0.25)
                plate:SetTooltipText(table.concat(map(r.folded, function(item)
                    if item.crew then return data.groups[item.group].options[item.option].name end
                    return data.army_units[item.unit].name
                end), '\n'), true)
                push(view.plates, {plate = plate, v = v, folded = #r.folded})
            end
        end
        -- the game's demolish button over the selected built slot
        local raze = image(holder, K.DEMOLISH, K.D .. 'button_round_small_active.png', 0, 0, 38, 38)
        raze.hoverImg = image(raze, 'hover', K.D .. 'button_round_small_hover.png', 0, 0, 38, 38)
        raze.icon = image(raze, 'icon_raze', K.D .. 'icon_raze.png', 0, 0, 38, 38)
        raze.hoverImg:SetPassive(); raze.icon:SetPassive()
        raze:SetHoverChild(raze.hoverImg)
        raze:SetInteractive(true)
        raze:SetVisible(false)
        view.raze = raze

        -- ---- the scroll bars: the arrows and the track take a click in the game (the page's own mouse listeners) ----
        local bars = {}
        local function makeBar(vertical, x, y, len)
            local k = vertical and 'vertical' or 'horizontal'
            local bar = {vertical = vertical, len = len, range = len - 2 * K.ARROW}
            bar.track = image(pane, 'tree_bar_track_' .. k, K.D .. 'slider_' .. k .. '_mid.png', vertical and (x + (K.BAR - 6) / 2) or (x + K.ARROW), vertical and (y + K.ARROW) or (y + (K.BAR - 6) / 2),
                vertical and 6 or (len - 2 * K.ARROW), vertical and (len - 2 * K.ARROW) or 6)
            bar.track:SetInteractive(true)
            local function arrow(endName, ax, ay)
                local w, h = vertical and 15 or 22, vertical and 22 or 15
                local a = image(pane, 'tree_bar_' .. endName, K.D .. 'slider_' .. k .. '_' .. endName .. '_active.png', ax + (vertical and (K.BAR - w) / 2 or 0), ay + (vertical and 0 or (K.BAR - h) / 2), w, h)
                a:SetHoverChild(image(a, 'hover', K.D .. 'slider_' .. k .. '_' .. endName .. '_hover.png', 0, 0, w, h))
                a:SetInteractive(true)
                return a
            end
            bar.less = arrow(vertical and 'top' or 'left', x, y)
            bar.more = arrow(vertical and 'bottom' or 'right', vertical and x or (x + len - K.ARROW), vertical and (y + len - K.ARROW) or y)
            bar.handle = make(pane, 'tree_bar_handle_' .. k, 'slider_handle_' .. (vertical and 'v' or 'h'))
            bar.handle:SetInteractive(true)
            bar.x, bar.y = x, y
            function bar.paint()
                local totalL = (vertical and ch or cw) * pan.z
                local seen = vertical and pan.h or pan.w
                local off = -(vertical and pan.y or pan.x)
                local on = totalL > seen + 0.5
                for _, c in ipairs({bar.track, bar.less, bar.more, bar.handle}) do c:SetVisible(on) end
                if not on then return end
                bar.hl = max(K.HANDLE_MIN, bar.range * seen / totalL)
                local p = (bar.range - bar.hl) * max(0, min(1, off / (totalL - seen)))
                if vertical then size(bar.handle, 18, bar.hl); at(bar.handle, x + (K.BAR - 18) / 2, y + K.ARROW + p)
                else size(bar.handle, bar.hl, 18); at(bar.handle, x + K.ARROW + p, y + (K.BAR - 18) / 2) end
            end
            -- a click on an arrow: a row; on the track: most of a window toward the handle's side the game says the mouse is on (one function: the uic module)
            function bar.by(d) if vertical then pan.y = pan.y - d else pan.x = pan.x - d end; pan.clamp() end
            bar.ids = {[bar.less:Id()] = function() bar.by(-K.STEP) end, [bar.more:Id()] = function() bar.by(K.STEP) end,
                       [bar.track:Id()] = function(where)
                           local before = where and where < (vertical and bar.handle.y or bar.handle.x)
                           bar.by((before and -1 or 1) * (vertical and pan.h or pan.w) * 0.9)
                       end}
            push(bars, bar)
            return bar
        end
        if needV then pan.vbar = makeBar(true, edge + ww + gap, edge, wh) end
        if needH then pan.hbar = makeBar(false, edge, areaBox.h - edge - K.BAR, ww) end
        view.bars = bars

        -- ---- moving the tree ----
        function pan.big() return cw * pan.z > pan.w + 0.5 or ch * pan.z > pan.h + 0.5 end
        function pan.clamp()
            local sw, shh, Ww, Hh = cw * pan.z, ch * pan.z, pan.w, pan.h
            pan.x = sw <= Ww and (Ww - sw) / 2 or min(0, max(Ww - sw, pan.x))
            pan.y = shh <= Hh and (Hh - shh) / 2 or min(0, max(Hh - shh, pan.y))
            -- the content moved under the window that cuts it (one function in the uic module: the clip and the move are engine unknowns)
            holder:SetContentOffset(pan.x, pan.y, pan.z)
            for _, bar in ipairs(bars) do bar.paint() end
            placeTips()
            if view.onPan then view.onPan() end
        end
        local function box(v) return {l = v.button.x - 14, t = v.button.y - 24, r = v.button.x + K.NODE + 20, b = v.button.y + K.NODE + 24} end
        local function centre(x, y) pan.x = pan.w / 2 - x * pan.z; pan.y = pan.h / 2 - y * pan.z; pan.clamp() end
        function pan.home()
            pan.z = 1
            local function st(v) return M.status(v.node.key) end
            local now = filter(view.tree, function(v) local s = st(v); return s.state == 'building' or s.state == 'open' or s.poor end)
            if #now == 0 then now = filter(view.tree, function(v) return st(v).state == 'built' end) end
            if #now == 0 and #view.tree > 0 then now = {view.tree[#view.tree]} end
            if #now == 0 then pan.clamp(); return end
            local bs = map(now, box)
            local l, r = minOf(bs, function(q) return q.l end), maxOf(bs, function(q) return q.r end)
            local t, b = minOf(bs, function(q) return q.t end), maxOf(bs, function(q) return q.b end)
            centre((l + r) / 2, (b - t <= pan.h - 20) and (t + b) / 2 or (b + 10 - pan.h / 2))
        end
        function pan.show(v)
            local b = box(v)
            if pan.z ~= 1 then pan.z = 1; centre((b.l + b.r) / 2, (b.t + b.b) / 2); return end
            if pan.x + b.l < 0 then pan.x = -b.l elseif pan.x + b.r > pan.w then pan.x = pan.w - b.r end
            if pan.y + b.t < 0 then pan.y = -b.t elseif pan.y + b.b > pan.h then pan.y = pan.h - b.b end
            pan.clamp()
        end
        function pan.zoomTo(v) pan.back = nil; pan.z = 1; centre(v.button.x + K.NODE / 2, v.button.y + K.NODE / 2) end
        function pan.fitZ() return min(1, pan.w / cw, pan.h / ch) end
        pan.back = nil
        function pan.toggle()
            if pan.z < 1 then
                local mx, my = (pan.w / 2 - pan.x) / pan.z, (pan.h / 2 - pan.y) / pan.z
                pan.z = 1
                if pan.back then pan.x = pan.back.x; pan.y = pan.back.y; pan.back = nil; pan.clamp() else centre(mx, my) end
                return
            end
            pan.back = {x = pan.x, y = pan.y}
            pan.z = pan.fitZ()
            pan.clamp()
        end
        function pan.state() return {x = pan.x, y = pan.y, z = pan.z, back = pan.back} end
        -- the wheel (src/tww3_mtb_ship_uic.lua tells it when the game gives it): up and down, across when the tree only goes across
        function pan.wheel(d, across)
            if not pan.big() then return end
            across = across or ch * pan.z <= pan.h + 0.5
            if across then pan.x = pan.x - d else pan.y = pan.y - d end
            pan.clamp()
        end
        if keepPan and type(keepPan.y) == 'number' and type(keepPan.x) == 'number' then
            pan.z = (keepPan.z and keepPan.z < 1) and pan.fitZ() or 1
            pan.x, pan.y = keepPan.x, keepPan.y
            pan.back = (keepPan.back and type(keepPan.back.x) == 'number' and type(keepPan.back.y) == 'number') and {x = keepPan.back.x, y = keepPan.back.y} or nil
            pan.clamp()
        else pan.home() end
        view.selected = rows[1] and rows[1].key or nil
        view.linesHolder = lines
    end

    -- One slot's links lit over the dimmed web of lines (panel.js lightLinks)
    view.litKey = false
    function lightLinks()
        if not view.tree or not view.linesHolder then return end
        local v = view.hoverSlot or (view.options and find(view.tree, function(t) return t.node.key == view.options end)) or nil
        local key = v and v.node.key or nil
        if view.litKey == key then return end
        view.litKey = key
        view.litPool = view.litPool or {}
        for _, t in ipairs(view.tree) do t.markIn:SetVisible(false); t.markOut:SetVisible(false) end
        local n = 0
        if key then
            for _, l in ipairs(view.links) do
                local into, out = l.to == key, l.from == key
                if into or out then
                    local c = into and K.LIT_IN or K.LIT_OUT
                    for _, s in ipairs(l.segs) do
                        local x0, y0, x1, y1 = s[1], s[2], s[3], s[4]
                        if not view.litPool[n + 1] then view.litPool[n + 1] = image(view.litLines, 'lit_' .. n, K.D .. 'bar_white.png', 0, 0, 1, 1) end
                        n = n + 1
                        local sc = view.litPool[n]
                        at(sc, min(x0, x1) - K.LIT / 2, min(y0, y1) - K.LIT / 2)
                        size(sc, abs(x1 - x0) + K.LIT, abs(y1 - y0) + K.LIT)
                        sc:SetImageColour(c[1], c[2], c[3], 255)
                        sc:SetVisible(true)
                    end
                    local otherKey = into and l.from or l.to
                    local other = find(view.tree, function(t) return t.node.key == otherKey end)
                    if other then (into and other.markIn or other.markOut):SetVisible(true) end
                end
            end
        end
        for i = n + 1, #view.litPool do view.litPool[i]:SetVisible(false) end
        view.linesHolder:SetOpacity(key and 70 or 255)
    end

    -- A click the slot refuses: its frame red for a moment
    local function denySlot(v)
        v.deny:SetVisible(true)
        after(650, function() v.deny:SetVisible(false) end, 'mtb_slot_refused')
    end

    local function slotOnFrame(v)
        local p = view.pan
        return {x = view.pane.x + p.win.x + p.x + v.button.x * p.z, y = view.pane.y + p.win.y + p.y + v.button.y * p.z, k = p.z}
    end

    function placeTips()
        local rootC = view.frame and view.frame.parent
        for _, c in ipairs(view.crew or {}) do
            if c.v and c.info.total and c.info.total ~= 0 then
                local s = slotOnFrame(c.v)
                local F = c.info.panel.parent
                local cardL = s.x + (c.card.x - c.v.button.x) * s.k
                local cardR = cardL + K.CARD_W * s.k
                local cy = s.y + (c.cardY - c.v.button.y + K.CARD_H / 2) * s.k
                local minX = 4 - F.x
                local maxX = (rootC and rootC:Width() or F:Width()) - 4 - F.x - K.UNIT_INFO_W
                local px = cardR + 10
                if px > maxX then px = min(s.x - 18, cardL) - 10 - K.UNIT_INFO_W end
                px = max(minX, min(maxX, px))
                local maxY = (rootC and rootC:Height() or F:Height()) - 4 - F.y - c.info.total
                local minY = (view.area and maxY >= view.area.y) and view.area.y or (4 - F.y)
                c.info.place(px, max(minY, min(maxY, cy - c.info.total / 2)))
            end
        end
    end

    function fillInfo(v)
        if not v.info.dirty then return end
        v.info.dirty = false
        local room = v.info.tip.parent.parent:Height() - 8
        for w = K.INFO_W, 800, 100 do
            local content = {}
            for k, x in pairs(v.info.content) do content[k] = x end
            content.width = w
            if fillInfoTip(v.info, content) <= room then break end
        end
    end
    local function infoTop(want, h, screenH, frameY, headY)
        local maxY = screenH - 4 - frameY - h
        local minY = maxY >= headY and headY or (4 - frameY)
        return max(minY, min(maxY, want))
    end
    UI.infoTop = infoTop
    function placeInfo(v)
        local frm = v.info.tip.parent
        local rootC = frm.parent
        local on = slotOnFrame(v)
        local x = on.x + (K.NODE + 17) * on.k + 10
        local w = v.info.w
        if frm.x + x + w > rootC:Width() - 4 then x = on.x - 18 - 10 - w end
        x = min(x, rootC:Width() - 4 - frm.x - w)
        x = max(4 - frm.x, x)
        at(v.info.tip, x, infoTop(on.y + (K.NODE + 28) * on.k - v.info.h, v.info.h, rootC:Height(), frm.y, view.area.y))
    end

    -- ---------------- the slots' states (panel.js refreshTree) ----------------
    local function refreshTree()
        for _, c in ipairs(view.crew or {}) do
            if not c.army then
                local o = find(crewOptions(c.group), function(x) return x.key == c.option end)
                if o then
                    c.waiting:SetVisible(M.crew_order(c.group) == c.option)
                    c.standing:SetVisible(M.crew(c.group) == c.option and M.crew_order(c.group) ~= c.option)
                    c.info.set(unitDyn(c.group, c.option, o))
                end
            end
        end
        if view.options and (M.status(view.options).state ~= 'built' or not view.demolishShown) then view.options = nil end
        placeTips()
        for _, v in ipairs(view.tree) do
            local st = M.status(v.node.key)
            local poor = st.state == 'locked' and st.poor
            local greyed = (st.state == 'locked' and not poor) or st.state == 'unknown'
            local built, building = st.state == 'built', st.state == 'building'
            if built then v.button:SetImageColour(255, 255, 255, 255)
            elseif greyed then v.button:SetImageColour(255, 255, 255, 0x80)
            else v.button:SetImageColour(255, 255, 255, 0xB4) end
            v.button:ShaderTechniqueSet(greyed and 'set_greyscale_t0' or 'normal_t0')
            local selected = view.options == v.node.key
            v.frameSelected:SetVisible(selected)
            v.plain:SetVisible((built or v.branch ~= nil) and not (selected and not v.branch))
            v.hover:SetVisible(false); v.hoverSelected:SetVisible(false)
            v.button:SetHoverChild(selected and v.hoverSelected or v.hover)
            v.check:SetVisible(built)
            v.padlock:SetVisible(greyed)
            v.constructing:SetVisible(false)        -- question V5: no clock-wipe in the game
            v.turnsBanner:SetVisible(building)
            v.turns:SetVisible(building)
            v.turns:SetStateText(building and str(st.turns) or '')
            if v.level then v.level:SetVisible(not building) end
            local row = M.level(v.node.key)
            v.cost:SetVisible(row ~= nil and not built and not building)
            v.costRed:SetVisible(poor and true or false)
            v.costText:SetStateText(row and (poor and ('[[col:red]]' .. str(row.cost) .. '[[/col]]') or str(row.cost)) or '')
            local reason = M.reason(v.node.key)
            local note = ''
            if st.state == 'open' then note = 'Щелчок — заказать: ' .. str(row.cost) .. ' золота, ' .. turnsText(row.turns) .. '.'
            elseif building then note = 'Строится, осталось ' .. turnsText(st.turns) .. '. Щелчок — отменить заказ, ' .. str(row.cost) .. ' золота вернутся.' end
            local i = v.node.row.info
            v.info.content = {title = i.title, chain = '', description = i.description, effects = i.effects, opens = i.opens, army = i.army, reason = reason, note = note}
            v.info.dirty = true
            if v.info.tip:Visible() then fillInfo(v); placeInfo(v) end
        end
        lightLinks()
        local sel = view.options and find(view.tree, function(v) return v.node.key == view.options end)
        view.raze:SetVisible(sel ~= nil)
        if sel then
            at(view.raze, sel.button.x - 14, sel.button.y - 14)
            local dem = M.can_demolish(sel.node.key)
            view.raze:SetImagePath(K.D .. (dem.ok and 'button_round_small_active.png' or 'button_round_small_inactive.png'), 0)
            view.raze.icon:ShaderTechniqueSet(dem.ok and 'normal_t0' or 'set_greyscale_t0')
            view.raze.icon:SetImageColour(255, 255, 255, dem.ok and 255 or 0x80)
            view.raze.hoverImg:SetBlank(not dem.ok)
            view.raze:SetTooltipText(dem.ok and ('Снести «' .. sel.node.name .. '»') or dem.why, true)
            view.razeOk = dem.ok
        end
    end

    -- the unit's panel beside the choice (panel.js placeUnitInfo)
    local function placeUnitInfo(c, slot)
        local frm = slot.info.panel.parent
        local F = {w = frm:Width(), h = frm:Height()}
        local px, py = view.sheet.x + c.pick.x, view.sheet.y + c.pick.y
        local pw, ph, h, Wd = c.pick:Width(), c.pick:Height(), slot.info.total, K.UNIT_INFO_W
        local cx = px + slot.hit.x + slot.hit:Width() / 2
        local across = max(6, min(cx - Wd / 2, F.w - 6 - Wd))
        local head = view.area and view.area.y or 8
        if py - 6 - h >= head then slot.info.place(across, py - 6 - h); return end
        if py + ph + 6 + h <= F.h - 6 then slot.info.place(across, py + ph + 6); return end
        local topY = max((F.h - 6 - h >= head) and head or 8, min(py + ph / 2 - h / 2, F.h - 6 - h))
        if px + pw + 8 + Wd <= F.w - 6 then slot.info.place(px + pw + 8, topY); return end
        slot.info.place(max(6, px - 8 - Wd), topY)
    end

    local function refreshCrewArea(c)
        local g = c.group
        local w = M.crew_words(g)
        local st = crewState(g)
        local shown, now, order, options, standing, ordered, nobody = st.place, st.now, st.order, st.options, st.standing, st.ordered, st.nobody
        c.area:SetVisible(shown)
        if not shown then c.open = false end
        c.pick:SetVisible(shown and c.open)
        paintCrewLayers({empty = c.empty, layers = c.layers, sketches = c.sketches}, g, c.spec.hides_part and view.layers[c.spec.hides_part])
        local tag = ordered and 'wait' or (nobody and 'plus' or 'swap')
        local fresh = shown and includes(M.news_places(), g)
        for _, k in ipairs({'plus', 'swap', 'wait'}) do
            c.tags[k]:SetVisible(k == tag); c.hoverTags[k]:SetVisible(k == tag)
            c.tags[k]:SetGlow(fresh and k == tag); c.hoverTags[k]:SetGlow(fresh and k == tag)
        end
        c.fresh = fresh
        c.glow:SetVisible(shown and M.crew_hint(g))
        local tip = ''
        if not c.open then
            if ordered then tip = ordered.empty and (w.who .. ' ' .. w.leave .. ' в начале хода') or (ordered.name .. ': в найме, ' .. w.come .. ' в начале хода')
            elseif not nobody then tip = standing.name .. ': ' .. (standing.unit_card and (str(standing.unit_card.men) .. ' ' .. w.at .. ', ') or '') .. 'содержание ' .. str(standing.upkeep) .. ' за ход' end
        end
        c.area:SetTooltipText(tip, true)
        for _, slot in ipairs(c.slots) do
            local o = find(options, function(x) return x.key == slot.key end)
            local will = M.crew_preview(g, o.key)
            slot.selected:SetVisible(o.key == now)
            slot.padlock:SetVisible(not o.unlocked)
            slot.turnsBanner:SetVisible(o.key == order)
            slot.card:ShaderTechniqueSet(o.unlocked and 'normal_t0' or 'set_greyscale_t0')
            slot.card:SetImageColour(255, 255, 255, o.unlocked and 255 or 0x80)
            slot.name:SetStateText(o.unlocked and o.name or ('[[col:grey]]' .. o.name .. '[[/col]]'))
            local hire = o.unlocked and not o.empty and o.key ~= now and o.key ~= order
            local queued = o.key == order
            if slot.card.costPlate then
                slot.card.costPlate:SetVisible(hire)
                slot.card.cost:SetStateText(will.kind == 'poor' and ('[[col:red]]' .. str(o.hire) .. '[[/col]]') or str(o.hire))
                for _, part in ipairs(slot.card.army) do part:SetVisible(o.key == now) end
                slot.card.frame:SetImageColour(255, 255, 255, queued and 0x64 or 255)
            end
            slot.card:SetImageOpacity(queued and 0x64 or nil)
            slot.hit:SetTooltipText(o.empty and will.text or '', true)
            if slot.info then
                local dyn = unitDyn(g, o.key, o)
                if will.bad then dyn.reason = will.text elseif will.kind == 'cancelled' then dyn.state = will.text end
                slot.info.set(dyn)
                placeUnitInfo(c, slot)
            end
        end
        local upkeep, nextU = M.crew_upkeep(), M.crew_upkeep_next()
        c.foot:SetStateText('Содержание экипажа: ' .. str(upkeep) .. ' за ход' .. (nextU ~= upkeep and (' → ' .. str(nextU)) or ''))
    end

    -- The tab shown: the other's windows that pop up under the mouse go with it
    local function setTab(tab)
        if view.tab == tab then return end
        view.tab = tab
        for _, g in ipairs(view.area_order) do view.crewAreas[g].open = false end
        for _, v in ipairs(view.tree or {}) do v.info.tip:SetVisible(false) end
        for _, c in ipairs(view.crew or {}) do c.info.panel:SetVisible(false); c.info.state:SetVisible(false) end
        if view.side then view.side.tip:SetVisible(false) end
        view.options = nil
        view.hoverSlot = nil
        clearTooltip()
        if view.onTab then view.onTab(tab) end
    end
    local function escape()
        local open = openArea()
        if open then open.open = false; return true end
        if view.options then view.options = nil; return true end
        return false
    end

    local function refresh()
        local gold = M.game.treasury()
        view.gold:SetStateText(gold < 0 and ('[[col:red]]' .. str(gold) .. '[[/col]]') or str(gold))
        local ship = view.tab == 'ship'
        for _, k in ipairs({'ship', 'tree'}) do
            local t = view.tabs[k]
            local on, hovered = k == view.tab, t.button.hovered
            t.button:SetState(on and (hovered and 'selected_hover' or 'selected') or (hovered and 'hover' or 'active'))
        end
        for _, c in ipairs({view.sheet, view.sheetFrame}) do c:SetVisible(ship) end
        view.pan.pane:SetVisible(not ship)
        if ship and M.ship_unseen() then M.ship_seen(); if view.onSeen then view.onSeen() end end
        local unseen = M.ship_unseen() and not ship
        view.tabMark:SetVisible(unseen)
        view.tabGlow:SetVisible(unseen)
        paintDrawing(view.sheet, view.sheets, view.layers, view.layer_order)
        paintNews(view.sheet, view.layers, view.layer_order)
        for _, part in ipairs(view.layer_order) do
            local layers = view.layers[part]
            local stage = M.stage(part)
            local st = {}
            if stage == 'build' then
                local keys = {}
                local b = blueprint.parts[part].building
                if b then push(keys, M.prefix .. b) end
                for _, k in ipairs(M.part_openers(part)) do push(keys, k) end
                st = find(map(keys, function(k) return M.status(k) end), function(x) return x.state == 'building' end) or {}
            end
            local words = st.state == 'building' and turnsText(st.turns) or ''
            layers.turns:SetVisible(stage == 'build' and words ~= '')
            layers.turns:SetStateText(words)
            if words ~= '' then size(layers.turns, width(layers.turns) + 16, 28) end
        end
        if view.column and not ship then paintShipColumn(view.column) end
        if view.tree then refreshTree() end
        if view.side then
            local bargeStage = view.side.show_when and M.stage(view.side.show_when) or 'ink'
            local shownP = bargeStage == 'ink' or bargeStage == 'build'
            local ready = bargeStage == 'ink'
            view.side.ready = ready
            local side = M.malakai_side()
            local function dim(c) c:SetImageColour(255, 255, 255, ready and 255 or 0x80); c:ShaderTechniqueSet(ready and 'normal_t0' or 'set_greyscale_t0') end
            view.side.plan:SetVisible(shownP)
            dim(view.side.plan)
            for _, s in ipairs({'left', 'right'}) do
                local b = view.side.marks[s]
                b:SetVisible(shownP)
                b:SetState((not ready) and 'inactive' or (s == side and 'selected' or 'active'))
                dim(b)
                local name = s == 'left' and 'левом' or 'правом'
                b:SetTooltipText((not ready) and 'Борт можно выбрать, когда корабль будет построен' or (M.side_hint() and 'Выберите борт для Малакая'
                    or (s == side and ('Малакай на ' .. name .. ' борту') or ('Поставить Малакая на ' .. (s == 'left' and 'левый' or 'правый') .. ' борт'))), true)
            end
            for _, s in ipairs({'left', 'right'}) do view.side.portraits[s]:SetVisible(shownP and s == side) end
            local hint = ready and M.side_hint()
            if ship then view.side.demo.fit() end
            local demo = hint and view.side.tip or nil
            view.side.plan:SetHoverChild(demo)
            for _, s in ipairs({'left', 'right'}) do
                local b = view.side.marks[s]
                b:SetHoverChild(demo)
                if demo then b:SetTooltipText('', true) end
            end
            if not demo then view.side.tip:SetVisible(false) end
            local op, tip, home = openArea(), view.side.tip, view.side.demo.home
            local pickOpen = op ~= nil and home[1] < op.pick.x + op.pick:Width() and home[1] + tip:Width() > op.pick.x and home[2] < op.pick.y + op.pick:Height() and home[2] + tip:Height() > op.pick.y
            if pickOpen then at(tip, 6, view.side.plan.y - 6 - tip:Height()) else at(tip, home[1], home[2]) end
            for _, s in ipairs({'left', 'right'}) do view.side.glows[s]:SetVisible(hint and s ~= side) end
            view.side.near:SetVisible(ready and side == 'left')
            view.side.far:SetVisible(ready and side == 'right')
            view.side.near_build:SetVisible(false)
            view.side.far_build:SetVisible(false)
        end
        for _, g in ipairs(view.area_order) do refreshCrewArea(view.crewAreas[g]) end
        local zoom = (not ship) and (view.pan.needH or view.pan.needV)
        view.fitBtn.button:SetVisible(zoom)
        view.fitBtn.label:SetStateText(view.pan.z < 1 and 'Вблизи' or 'Всё дерево')
        view.fitBtn.button:SetTooltipText(view.pan.z < 1 and 'Вернуть дерево в обычный размер' or 'Показать всё дерево целиком', true)
        size(view.message, (zoom and (view.fitBtn.button.x - 24) or (view.area.x + view.area.w - 14)) - view.message.x, view.message:Height())
        fitLine(view.message, M.message() or M.first_step() or '')
    end

    local function clickSlot(v)
        local key = v.node.key
        view.selected = key
        local was = view.options
        view.options = nil
        if view.pan.z < 1 then view.pan.zoomTo(v)
        else
            local st = M.status(key)
            if st.state == 'open' then M.order(key)
            elseif st.state == 'building' then M.cancel(key)
            elseif st.state == 'built' and view.demolishShown and was ~= key then view.options = key
            elseif st.state == 'locked' or st.state == 'unknown' then M.refuse(key); denySlot(v) end
            view.pan.show(v)
        end
        if view.onSelect then view.onSelect() end
    end

    local function inPick(id, g)
        return starts(id, K.CREW_AREA) or id == K.CREW_CLOSE .. g or starts(id, K.CREW_PICK .. g .. ':') or id == 'mtb_crew_pick_' .. g
    end

    -- where: the mouse's place along a scroll bar's track, when the game tells it (src/tww3_mtb_ship_uic.lua)
    local function click(c, where)
        local id = c:Id()
        local open = openArea()
        if open and not inPick(id, open.group) then
            open.open = false
            refresh()
            return
        end
        if id == 'mtb_ship_panel' or id == 'frame' then
            view.options = nil
        elseif id == 'mtb_mini_ship' then
            setTab('ship')
        elseif starts(id, 'mtb_mini_crew_') then
            local g = ssub(id, #'mtb_mini_crew_' + 1)
            setTab('ship')
            local a = view.crewAreas[g]
            if a and M.crew_place(g) then a.open = true; if view.onCrewArea then view.onCrewArea(g) end end
        elseif starts(id, K.TAB) then
            setTab(ssub(id, #K.TAB + 1))
        elseif starts(id, K.SIDE) then
            if view.side and view.side.ready then M.set_malakai_side(ssub(id, #K.SIDE + 1)) end
        elseif starts(id, K.CREW_AREA) then
            local a = view.crewAreas[ssub(id, #K.CREW_AREA + 1)]
            if a and not a.open and view.onCrewArea then view.onCrewArea(a.group) end
            local was = a and a.open
            for _, g in ipairs(view.area_order) do view.crewAreas[g].open = false end
            if a then a.open = not was end
        elseif starts(id, K.CREW_CLOSE) then
            local a = view.crewAreas[ssub(id, #K.CREW_CLOSE + 1)]
            if a then a.open = false end
        elseif starts(id, K.CREW_PICK) then
            local rest = ssub(id, #K.CREW_PICK + 1)
            local group, option = string.match(rest, '^([^:]+):(.+)$')
            if group and view.crewAreas[group] and option then M.set_crew(group, option) end
        elseif starts(id, 'mtb_crew_pick_') then
            -- a window's own backing
        elseif id == 'scheme' then
            for _, g in ipairs(view.area_order) do view.crewAreas[g].open = false end
        elseif id == K.FIT then
            view.options = nil
            view.pan.toggle()
        elseif id == 'tree_window' then
            view.options = nil
        elseif id == K.DEMOLISH then
            if view.options and view.razeOk then local key = view.options; view.options = nil; M.demolish(key) end
        elseif starts(id, K.TREE) then
            local v = view.tree[(tonumber(ssub(id, #K.TREE + 1)) or -1) + 1]
            if v then clickSlot(v) end
        else
            for _, bar in ipairs(view.bars or {}) do if bar.ids[id] then bar.ids[id](where) end end
        end
        refresh()
    end

    -- ---------------- the panel (panel.js makePanel) ----------------
    local backdrop = make(root, 'mtb_ship_panel', 'backdrop')
    size(backdrop, W, H)
    backdrop:MoveTo(0, 0)
    backdrop:SetInteractive(true)
    frame = make(root, 'frame', 'frame')
    size(frame, panel_w, panel_h)
    at(frame, (W - panel_w) / 2, (H - panel_h) / 2)
    frame:SetInteractive(true)
    view.frame = frame
    view.area = area
    local ground = make(frame, 'panel_back', 'panel_ground')
    size(ground, panel_w - 16, panel_h - 16)
    at(ground, 8, 8)
    ground:SetPassive()

    local close_w, tab_w, tab_gap = 34, 160, 6
    local tabs_w = 2 * tab_w + tab_gap
    local tabs_x = panel_w - 14 - close_w - 14 - tabs_w
    view.title = titlePlate(frame, panel_w / 2, 33, min(panel_w / 2 - (54 + 160 + 8), tabs_x - 8 - panel_w / 2), '«Дух Грунгни»')
    local close = image(frame, 'mtb_ship_close', K.D .. 'icon_cross.png', panel_w - 14 - close_w, 14, close_w, close_w)
    close:SetTooltipText('Закрыть', true)
    view.close = close
    image(frame, 'gold_icon', K.D .. 'icon_treasury.png', 22, 18, 26, 26)
    view.gold = text(frame, 'gold', 'text_head', 54, 14, 160, 34, '')
    view.gold:SetTooltipText('Казна фракции', true)
    view.tabs = {}
    for i, pair in ipairs({{'ship', 'Корабль'}, {'tree', 'Постройки'}}) do
        view.tabs[pair[1]] = makeButton(frame, K.TAB .. pair[1], tabs_x + (i - 1) * (tab_w + tab_gap), 11, tab_w, 44, pair[2])
    end
    local shipTab = view.tabs.ship.button
    view.tabGlow = {on = false}
    function view.tabGlow:SetVisible(on) self.on = on and true or false; shipTab:SetGlow(self.on, 'soft') end
    function view.tabGlow:Visible() return self.on end
    view.tabMark = image(view.tabs.ship.button, 'new_mark', K.D .. 'icon_alert_message.png', tab_w - 26, 2, 24, 24)
    view.tabMark:SetPassive()

    view.pane = make(frame, 'work_pane', 'tree_pane')
    size(view.pane, area.w, area.h)
    at(view.pane, area.x, area.y)
    -- «Корабль»: the drawing and its layers
    local sx, sy = area.x + (area.w - scheme_w) / 2, area.y + (area.h - scheme_h) / 2
    local sheet = image(frame, 'scheme', K.LAYOUTS .. blueprint.sheet .. '.png', sx, sy, scheme_w, scheme_h)
    sheet:SetInteractive(true)
    view.sheet = sheet
    view.sheets = (#blueprint.sheets > 0) and blueprint.sheets or nil
    view.layers, view.layer_order = drawingLayers(sheet, scale)
    for _, part in ipairs(view.layer_order) do
        local spec = blueprint.parts[part]
        view.layers[part].turns = text(sheet, part .. '_turns', 'text_ink', spec.turns_at[1] * scale, spec.turns_at[2] * scale, 110, 28, '')
    end
    -- Malakai's side
    local ms = art.malakai_side
    if blueprint.malakai_side and ms then
        local p = place('plan_ship')
        view.side = {show_when = blueprint.malakai_side.show_when, plan = image(sheet, 'plan_ship', K.WEB_ART .. 'plan_ship.png', p[1] * scale, p[2] * scale, p[3] * scale, p[4] * scale), marks = {}}
        view.side.portraits = {}
        view.side.glows = {}
        local glow = ms.glow
        for _, s in ipairs({'left', 'right'}) do
            local size_ = ms.mark * glow.size
            local off = (size_ - ms.mark) / 2
            local holderG = image(sheet, 'side_glow_' .. s, K.WEB_ART .. 'glow_0.png', (ms.marks[s][1] - off) * scale, (ms.marks[s][2] - off) * scale, size_ * scale, size_ * scale)
            holderG:SetPassive()
            holderG.phases = {}
            for i = 1, glow.phases - 1 do
                local ph = image(holderG, 'phase_' .. i, K.WEB_ART .. 'glow_' .. i .. '.png', 0, 0, size_ * scale, size_ * scale)
                ph:SetVisible(false)
                push(holderG.phases, ph)
            end
            view.side.glows[s] = holderG
        end
        view.side.phase = 0
        every(glow.step_ms, function()
            view.side.phase = (view.side.phase + 1) % glow.phases
            for _, s in ipairs({'left', 'right'}) do
                local g = view.side.glows[s]
                g:SetImageShown(view.side.phase == 0)
                for i, ph in ipairs(g.phases) do ph:SetVisible(view.side.phase == i) end
            end
        end, 'mtb_side_hint')
        for _, s in ipairs({'left', 'right'}) do
            local b = make(sheet, K.SIDE .. s, 'button_mark')
            size(b, ms.mark * scale, ms.mark * scale)
            at(b, ms.marks[s][1] * scale, ms.marks[s][2] * scale)
            view.side.marks[s] = b
            local inset = ms.portrait_inset * scale
            view.side.portraits[s] = image(b, 'portrait', ms.portrait, inset, inset, ms.mark * scale - 2 * inset, ms.mark * scale - 2 * inset)
        end
        view.side.demo = demoTip(sheet, 'side_demo_tip', (ms.plan[1] + ms.plan[3] + 12) * scale, (ms.plan[2] + ms.plan[4]) * scale,
            {head = 'Борт Малакая', text = 'С какого борта Малакай ведёт огонь. Борт можно сменить и позже, между боями.'})
        view.side.tip = view.side.demo.tip
        view.side.video = view.side.demo.video
        for _, n in ipairs({'near', 'far', 'near_build', 'far_build'}) do
            local q = place('malakai_' .. n)
            view.side[n] = image(sheet, 'malakai_' .. n, K.WEB_ART .. 'malakai_' .. n .. '.png', q[1] * scale, q[2] * scale, q[3] * scale, q[4] * scale)
        end
    end
    -- the crew's places on the drawing
    view.crewAreas, view.area_order = {}, {}
    for _, spec in ipairs(blueprint.crew_areas) do
        local a = art.crew_areas[spec.group]
        if a and data.groups[spec.group] then
            view.crewAreas[spec.group] = makeCrewArea(sheet, spec, a)
            push(view.area_order, spec.group)
        end
    end
    view.crewArea = view.crewAreas.rifles
    view.sheetFrame = make(frame, 'scheme_frame', 'frame_edge')
    size(view.sheetFrame, scheme_w + 8, scheme_h + 8)
    at(view.sheetFrame, sx - 4, sy - 4)

    -- «Постройки»
    view.demolishShown = (flags.full or blueprint.demolish) and true or false
    view.blueprint = blueprint
    view.flags = flags
    makeFileTree(area, keep.pan)
    view.paneEdge = make(frame, 'work_pane_edge', 'frame_edge')
    size(view.paneEdge, area.w + 8, area.h + 8)
    at(view.paneEdge, area.x - 4, area.y - 4)

    -- the foot row
    local foot_y, fit_w, foot_hh = area.y + area.h + 6, 210, 40
    local strip = make(frame, 'foot_strip', 'foot_strip')
    size(strip, area.w, foot_hh)
    at(strip, area.x, foot_y)
    view.fitBtn = makeButton(frame, K.FIT, area.x + area.w - fit_w - 2, foot_y + 2, fit_w, foot_hh - 4, 'Всё дерево')
    view.message = text(frame, 'message', 'text_copper', area.x + 14, foot_y, area.w - fit_w - 40, foot_hh, '')

    view.root = backdrop
    view.scale = scale
    return {view = view, refresh = refresh, click = click, escape = function() local done = escape(); if done then refresh() end return done end}
end

return UI
