-- The game's UIComponent for the offline check of the airship screen's drawing (tools/ui_layout_check.py, docs/design/port-to-game.md 4.2): a
-- component with the methods src/tww3_mtb_ship_ui.lua calls, behaving as web/js/gameui.js's Component does where the dump can see it (offsets,
-- sizes, visibility, texts, states, pictures, colours, the hover children shown while the mouse is over a component), and dump() writing the same
-- rows as gameui.js dump(). Never packed into the mod.
--
--   local Fake = <this file>; local ui = Fake.new{measures = {...}, text = cfg.text, w = 1600, h = 900}
--   ui.root          the root component (the game's core:get_ui_root(), here 1600 x 900)
--   ui.mouse_on(c)   the mouse comes onto c (the game's ComponentMouseOn): the last one's hover children go, c's come, c.on_enter / on_leave run
--   ui.find(id)      the first component of that id, parents before children
--   ui.dump()        {rows}: path, id, layout, x, y, w, h, visible, text, state, image, colour, shader, opacity, tooltip, glow, layer, interactive,
--                    text_size, blank, image_opacity, scale
--   ui.unmeasured    the texts the page never measured (their key: layout|width|text): a layout the page and the Lua do differently
--   ui.count         components made
--
-- Text measures: the page's own (build/ui_dump/<state>.json, measures), by the layout, the box's width and the text: the one place where the game's
-- uic:TextDimensions() answers in the game (src/tww3_mtb_ship_uic.lua measure_text).

local Fake = {}

local SKIN = {button_row = true, button_plate = true, button_mark = true}
local ON_ENTER = {active = 'hover', selected = 'selected_hover'}
local ON_LEAVE = {hover = 'active', selected_hover = 'selected', down = 'active', down_off = 'active'}
local function round(x) return math.floor(x + 0.5) end

-- a number as CSS writes a font size back (Chrome: at most 6 significant digits)
local function css(v)
    local s = string.format('%.6g', v)
    return s
end

function Fake.new(opts)
    local env = {unmeasured = {}, count = 0, all = {}}
    local measures, textLayouts = opts.measures or {}, opts.text or {}
    local C = {}
    C.__index = C
    local function new(parent, id, layout)
        local c = setmetatable({id = id, layout = layout, parent = parent, children = {}, x = 0, y = 0, w = 64, h = 64, visible = true}, C)
        if textLayouts[layout] then c.text = '' end
        if SKIN[layout] then c.state = 'active' end
        if parent then parent.children[#parent.children + 1] = c end
        env.count = env.count + 1
        env.all[#env.all + 1] = c
        return c
    end
    function C:CreateComponent(id, layout) return new(self, id, layout) end
    function C:Id() return self.id end
    function C:SetVisible(on) self.visible = on and true or false end
    function C:Visible() return self.visible end
    function C:Resize(w, h) self.w = round(w); self.h = round(h) end
    function C:Width() return self.w end
    function C:Height() return self.h end
    function C:SetDockOffset(x, y) self.x = round(x); self.y = round(y) end
    function C:MoveTo(x, y) self:SetDockOffset(x, y) end
    function C:SetImagePath(path) self.image = path end
    function C:SetStateText(t) if self.text ~= nil then self.text = t end end
    function C:GetStateText() return self.text or '' end
    function C:TextDimensions()
        if self.text == nil then return 0, 0, 0 end
        local key = self.layout .. '|' .. self.w .. '|' .. self.text
        local m = measures[key]
        if not m then
            env.unmeasured[#env.unmeasured + 1] = key
            local n = 0
            for _ in string.gmatch(self.text, '[%z\1-\127\194-\244][\128-\191]*') do n = n + 1 end
            return n * 8, 22, 1
        end
        return m[1], m[2], m[3]
    end
    function C:TextSize() return self.text_size or (textLayouts[self.layout] and textLayouts[self.layout].size) or 0 end
    function C:SetTextSize(px) self.text_size = px end
    function C:InkDimensions()
        local key = 'ink|' .. self.layout .. '|' .. css(self:TextSize()) .. '|' .. (self.text or '')
        local m = measures[key]
        if not m then
            env.unmeasured[#env.unmeasured + 1] = key
            return {w = 0, left = 0, right = 0, ascent = 0, descent = 0, fontAscent = 0, fontDescent = 0}
        end
        return m
    end
    function C:SetTooltipText(t) self.tooltip = t end
    function C:SetOpacity(a) self.opacity = a end
    function C:SetState(s) self.state = s end
    function C:CurrentState() return self.state end
    function C:ShaderTechniqueSet(name) self.shader = name end
    function C:SetGlow(on, kind) self.glow = on and (kind or 'glow') or '' end
    function C:SetImageColour(r, g, b, a) self.colour = {r, g, b, a} end
    function C:SetInteractive(on) self.interactive = on and true or false end
    function C:SetPassive() self.passive = true end
    function C:SetHoverChild(child)
        if self.hoverChild and self.hoverChild ~= child then self.hoverChild:SetVisible(false) end
        self.hoverChild = child
        if child then child:SetVisible(self.hovered == true) end
    end
    function C:AddHoverChild(child)
        self.hoverChildren = self.hoverChildren or {}
        self.hoverChildren[#self.hoverChildren + 1] = child
        child:SetVisible(self.hovered == true)
    end
    function C:SetLayer(name) self.layer = name; return self end
    function C:SetHoverBrighten(k) self.brighten = k end
    function C:SetBlank(on) self.blank = on and true or nil end
    function C:SetImageOpacity(a) self.image_opacity = a end
    function C:SetImageShown(on) self.image_shown = on end
    function C:SetTopmost() self.topmost = true end
    function C:SetClipChildren(on) self.clip = on end
    function C:SetContentOffset(x, y, z) self.x = x; self.y = y; self.scale = z end

    env.root = new(nil, 'root', 'root')
    env.root:Resize(opts.w or 1600, opts.h or 900)

    local function enter(c)
        if c.state and SKIN[c.layout] and ON_ENTER[c.state] then c.state = ON_ENTER[c.state] end
        c.hovered = true
        if c.hoverChild then c.hoverChild:SetVisible(true) end
        for _, k in ipairs(c.hoverChildren or {}) do k:SetVisible(true) end
        if c.on_enter then c.on_enter() end
    end
    local function leave(c)
        if c.state and SKIN[c.layout] and ON_LEAVE[c.state] then c.state = ON_LEAVE[c.state] end
        c.hovered = false
        if c.hoverChild then c.hoverChild:SetVisible(false) end
        for _, k in ipairs(c.hoverChildren or {}) do k:SetVisible(false) end
        if c.on_leave then c.on_leave() end
    end
    function env.mouse_on(c)
        if env.hovered == c then return end
        if env.hovered then leave(env.hovered) end
        env.hovered = c
        if c then enter(c) end
    end
    function env.find(id)
        for _, c in ipairs(env.all) do if c.id == id then return c end end
        return nil
    end

    function env.dump()
        local out = {}
        local function walk(c, path)
            local row = {path = path, id = c.id, layout = c.layout, x = c.x, y = c.y, w = c.w, h = c.h, visible = c.visible}
            if c.text ~= nil then row.text = c.text end
            if c.state ~= nil then row.state = c.state end
            if c.image then row.image = c.image end
            if c.colour then row.colour = c.colour end
            if c.shader then row.shader = c.shader end
            if c.opacity ~= nil then row.opacity = c.opacity end
            if c.tooltip and c.tooltip ~= '' then row.tooltip = c.tooltip end
            if c.glow and c.glow ~= '' then row.glow = c.glow end
            if c.layer then row.layer = c.layer end
            if c.interactive or SKIN[c.layout] then row.interactive = true end
            if c.text_size ~= nil then row.text_size = c.text_size end
            if c.blank then row.blank = true end
            if c.image_opacity then row.image_opacity = c.image_opacity end
            if c.scale and c.scale ~= 1 then row.scale = c.scale end
            out[#out + 1] = row
            local seen = {}
            for _, k in ipairs(c.children) do
                seen[k.id] = (seen[k.id] or 0) + 1
                walk(k, path .. '/' .. k.id .. (seen[k.id] > 1 and ('#' .. seen[k.id]) or ''))
            end
        end
        walk(env.root, 'root')
        return out
    end
    return env
end

-- ================ the game's own UIComponent, as the first session in the game showed it ================
-- Fake.engine{layouts = {...}, measures = {...}, w = 1600, h = 900, prefix = 'ui/tww3_mtb/'}: a stand-in of the game's UIComponent for
-- src/tww3_mtb_ship_uic.lua (installed as the globals UIComponent and core by the caller), which behaves as the game did where it mattered in
-- runs/20261114-230723-ship_panel and the probe of 14.11:
--   * a component is made from its layout (layouts: tools/ui_layout_check.py reads them from the pack): the size of its default state, its picture,
--     clipchildren read from the component's own element (where the game reads it), the states it has;
--   * Resize(w, h) scales the children with their parent unless the third argument is false (a unit's panel 290 x 499 made after its children:
--     266 x 30 -> 1205 x 234);
--   * no SetCurrentStateImageColour (probe 14.11, item 0): a call of a method the game lacks raises, as in the game;
--   * SetOpacity dims the component's own picture only (a holder or a text: nothing); PropagateOpacity on a component with a picture sets it on
--     every descendant (the session's step opacity); on one without a picture: nothing, counted (not proven);
--   * TextDimensions -> width, height, true (a boolean: probe 14.11, item 7), from `measures` by the layout, the component's own width and the text;
--     a text measured at a width the measures do not have is counted in unmeasured.
-- E.calls counts the calls by method; E.root is the game's root; E.rows(c) the game's own answers for a component.
function Fake.engine(opts)
    local E = {calls = {}, count = 0, unmeasured = {}, images = {}, propagate_without_picture = 0}
    local layouts, measures, prefix = opts.layouts or {}, opts.measures or {}, opts.prefix or 'ui/tww3_mtb/'
    local M = {}
    local meta = {__index = function(_, k)
        local f = M[k]
        if f ~= nil then E.calls[k] = (E.calls[k] or 0) + 1 end
        return f
    end}
    local function new(parent, id, name, L)
        local c = setmetatable({id = id, name = name, L = L, parent = parent, children = {}, x = 0, y = 0, w = L.w or 64, h = L.h or 64, dp = 0,
                                visible = true, opacity = 255, image_opacity = 255, state = L.default, interactive = L.interactive, text = L.text and '' or nil}, meta)
        if parent then parent.children[#parent.children + 1] = c end
        E.count = E.count + 1
        return c
    end
    function M.CreateComponent(self, id, path)
        local name = string.sub(path, 1, #prefix) == prefix and string.sub(path, #prefix + 1) or path
        local L = layouts[name]
        if not L then error('the game has no layout ' .. tostring(path)) end
        return new(self, id, name, L)
    end
    function M.Id(self) return self.id end
    function M.Address(self) return self end
    local function scale(c, w, h)
        local kx, ky = (c.w ~= 0) and w / c.w or 1, (c.h ~= 0) and h / c.h or 1
        for _, ch in ipairs(c.children) do
            local cw, chh = math.floor(ch.w * kx + 0.5), math.floor(ch.h * ky + 0.5)
            scale(ch, cw, chh)
            ch.w, ch.h = cw, chh
        end
    end
    function M.Resize(self, w, h, children)
        if children ~= false then scale(self, w, h) end
        self.w, self.h = w, h
    end
    function M.Width(self) return self.w end
    function M.Height(self) return self.h end
    function M.SetCanResizeWidth(self, on) self.can_w = on end
    function M.SetCanResizeHeight(self, on) self.can_h = on end
    function M.SetCanResizeCurrentStateImageWidth() end
    function M.SetCanResizeCurrentStateImageHeight() end
    function M.ResizeCurrentStateImage(self, i, w, h) self.image_w, self.image_h = w, h end
    function M.NumImages(self) return self.L.images or 0 end
    function M.SetDockingPoint(self, p) self.dp = p end
    function M.SetDockOffset(self, x, y) self.x, self.y = x, y end
    local function position(c)
        if not c.parent then return 0, 0 end
        local px, py = position(c.parent)
        return px + c.x, py + c.y
    end
    function M.Position(self) return position(self) end
    function M.MoveTo(self, x, y) local px, py = 0, 0; if self.parent then px, py = position(self.parent) end; self.x, self.y = x - px, y - py end
    function M.Bounds(self) return self.w, self.h end
    function M.SetVisible(self, on) self.visible = on and true or false end
    function M.Visible(self) return self.visible end
    function M.SetImagePath(self, path) self.image = path; E.images[path] = true end
    function M.SetStateText(self, t) self.text = t end
    function M.GetStateText(self) return self.text or '' end
    function M.TextDimensions(self)
        if not self.L.text then return 0, 0, false end
        if (self.text or '') == '' then return 0, 0, true end
        local key = self.name .. '|' .. tostring(self.w) .. '|' .. self.text
        local m = measures[key]
        if not m then
            E.unmeasured[#E.unmeasured + 1] = key
            local n = 0
            for _ in string.gmatch(self.text, '[%z\1-\127\194-\244][\128-\191]*') do n = n + 1 end
            return n * 8, 22, true
        end
        return m[1], m[2], true
    end
    function M.SetTooltipText(self, t) self.tooltip = t end
    function M.SetOpacity(self, a) if self.L.picture then self.opacity = a end end
    function M.Opacity(self) return self.opacity end
    local function propagate(c, a) c.opacity = a; for _, ch in ipairs(c.children) do propagate(ch, a) end end
    function M.PropagateOpacity(self, a)
        if self.L.picture then propagate(self, a) else E.propagate_without_picture = E.propagate_without_picture + 1 end
    end
    function M.SetCurrentStateImageOpacity(self, i, a) self.image_opacity = a end
    function M.ShaderTechniqueSet(self, name) self.shader = name end
    function M.ShaderVarsSet() end
    function M.SetState(self, s) self.state = s end
    function M.CurrentState(self) return self.state end
    function M.SetInteractive(self, on) self.interactive = on and true or false end
    function M.RegisterTopMost(self) self.topmost = true end
    function M.RemoveTopMost(self) self.topmost = nil end
    function M.PropagatePriority(self, p) self.priority = p end
    function M.Priority(self) return self.priority or 42 end
    function M.Destroy(self)
        local p = self.parent
        if p then for i, ch in ipairs(p.children) do if ch == self then table.remove(p.children, i); break end end end
        self.parent = nil
    end
    E.root = new(nil, 'root', 'root', {w = opts.w or 1600, h = opts.h or 900, picture = false})
    -- the clip the game draws a component with: the nearest ancestor with clipchildren (nil: none)
    function E.clipper(c)
        local p = c.parent
        while p do if p.L.clip then return p end; p = p.parent end
        return nil
    end
    E.position = position
    return E
end

-- ================ what the game draws, against what the page draws (tools/ui_layout_check.py) ================
local function each_child(c, path, fn)
    local seen = {}
    for _, k in ipairs(c.children) do
        seen[k.id] = (seen[k.id] or 0) + 1
        fn(k, path .. '/' .. k.id .. (seen[k.id] > 1 and ('#' .. seen[k.id]) or ''))
    end
end

-- Fake.check_engine(top, E, pack): the components of src/tww3_mtb_ship_uic.lua under `top` (its root holder) against the game's components under
-- them (E: Fake.engine). Problems {kind, path, text}:
--   size     the game's Width() / Height() not the size the binding gave (times the scale of «Всё дерево»)
--   opacity  the opacity the game draws a shown picture with not the page's (the product of the component's and its ancestors' opacity or colour
--            alpha: the page's CSS opacity holds a component's children)
--   image    the picture's own opacity (the page's image opacity) not the game's
--   tint     a coloured picture (the page's SetImageColour with a colour) drawn uncoloured: no picture coloured in advance set in its place
--   picture  a picture of ours (ui/tww3_mtb/...) set on the game's component and not in the pack (pack: {path = true})
--   clip     a shown component of the tree's content with no ancestor that clips (clipchildren on its layout's component)
function Fake.check_engine(top, E, pack)
    local out = {}
    local function add(kind, path, text) out[#out + 1] = {kind = kind, path = path, text = text} end
    local unclipped = 0
    local function walk(c, path, shown, alpha, inTree)
        local u = c.uic
        local k = c.k or 1
        local w, h = math.floor(c.w * k + 0.5), math.floor(c.h * k + 0.5)
        if c ~= top and (math.abs(u.w - w) > 1 or math.abs(u.h - h) > 1) then
            add('size', path, 'the binding ' .. w .. ' x ' .. h .. ', the game ' .. tostring(u.w) .. ' x ' .. tostring(u.h))
        end
        local own = (c.colour and c.colour[4]) or c.opacity or 255
        local a = alpha * own / 255
        local vis = shown and c.visible and not c.blank and not c.culled
        if vis and u.L.picture and c.layout ~= 'layer_holder' and math.abs(u.opacity - a) > 2 then
            add('opacity', path, 'the page ' .. math.floor(a + 0.5) .. ', the game ' .. tostring(u.opacity))
        end
        if c.image_opacity and u.image_opacity ~= c.image_opacity then add('image', path, 'the page ' .. c.image_opacity .. ', the game ' .. tostring(u.image_opacity)) end
        local col = c.colour
        if col and not (col[1] == col[2] and col[2] == col[3]) and (u.image == c.image or not pack[u.image or '']) then
            add('tint', path, 'the page colours ' .. tostring(c.image) .. ' (' .. col[1] .. ', ' .. col[2] .. ', ' .. col[3] .. '), the game draws ' .. tostring(u.image))
        end
        if u.image and string.sub(u.image, 1, 12) == 'ui/tww3_mtb/' and not pack[u.image] then add('picture', path, u.image .. ' is not in the pack') end
        if inTree and vis and not E.clipper(u) then unclipped = unclipped + 1; if unclipped <= 3 then add('clip', path, 'drawn beyond the tree\'s window: no ancestor clips') end end
        each_child(c, path, function(ch, p) walk(ch, p, vis, a, inTree or c.layout == 'tree_holder') end)
    end
    walk(top, 'root', true, 255, false)
    if unclipped > 3 then add('clip', '...', unclipped .. ' shown components of the tree with no clipping ancestor') end
    return out
end

-- Fake.check_windows(top, E): the windows under the mouse as the game draws them (a building's window, a unit's panel and the line under it): in
-- each shown window, the ink of its texts (TextDimensions placed by the layout's alignment), and its small pictures (icons, at most 32 x 32), in
-- the game's own places and sizes. Problems {kind, path, text}:
--   overlap  two texts' ink over each other (a title over the description)
--   icons    two icons over each other (icons piled at an edge)
--   row      an icon beside no text (an icon off its line)
--   outside  a text's ink or an icon out of its window
local WINDOWS = {tooltip_frame = true, unit_parchment = true, tooltip_instruction = true}
function Fake.check_windows(top, E)
    local out = {}
    local function add(kind, path, text) out[#out + 1] = {kind = kind, path = path, text = text} end
    local function over(a, b) return math.min(a.r, b.r) - math.max(a.l, b.l) > 2 and math.min(a.b, b.b) - math.max(a.t, b.t) > 2 end
    local function window(c, path)
        local wx, wy = E.position(c.uic)
        local box = {l = wx, t = wy, r = wx + c.uic.w, b = wy + c.uic.h}
        local texts, icons = {}, {}
        each_child(c, path, function(ch, p)
            if not (ch.visible and not ch.blank) or ch.stand_in then return end
            local u = ch.uic
            local x, y = E.position(u)
            if ch.text ~= nil then
                if (ch.text or '') == '' then return end
                local tw, th = u:TextDimensions()
                tw = math.min(tw, u.w)
                local L = u.L
                local ix = (L.align == 'Center') and (x + (u.w - tw) / 2) or ((L.align == 'Right') and (x + u.w - tw) or x)
                local iy = (L.valign == 'Top') and y or (y + (u.h - th) / 2)
                texts[#texts + 1] = {l = ix, t = iy, r = ix + tw, b = iy + th, path = p}
            elseif u.L.picture and u.w <= 32 and u.h <= 32 and ch.layout == 'image' then
                icons[#icons + 1] = {l = x, t = y, r = x + u.w, b = y + u.h, path = p}
            end
        end)
        for i = 1, #texts do
            for j = i + 1, #texts do if over(texts[i], texts[j]) then add('overlap', texts[i].path, 'its ink over that of ' .. texts[j].path) end end
        end
        for i = 1, #icons do
            for j = i + 1, #icons do if over(icons[i], icons[j]) then add('icons', icons[i].path, 'over ' .. icons[j].path) end end
            local beside = false
            for _, t in ipairs(texts) do if math.min(icons[i].b, t.b) - math.max(icons[i].t, t.t) > 2 then beside = true end end
            if not beside then add('row', icons[i].path, 'beside no line of text') end
        end
        for _, q in ipairs(texts) do
            if q.l < box.l - 2 or q.r > box.r + 2 or q.t < box.t - 2 or q.b > box.b + 2 then add('outside', q.path, 'the ink out of its window') end
        end
        for _, q in ipairs(icons) do
            if q.l < box.l - 2 or q.r > box.r + 2 or q.t < box.t - 2 or q.b > box.b + 2 then add('outside', q.path, 'the icon out of its window') end
        end
    end
    local function walk(c, path, shown)
        local vis = shown and c.visible and not c.blank
        if vis and WINDOWS[c.layout] then window(c, path) end
        if vis then each_child(c, path, function(ch, p) walk(ch, p, vis) end) end
    end
    walk(top, 'root', true)
    return out
end

return Fake
