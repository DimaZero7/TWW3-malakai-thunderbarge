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

return Fake
