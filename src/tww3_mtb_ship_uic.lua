-- The components src/tww3_mtb_ship_ui.lua draws with, over the game's UIComponent: the methods of web/js/gameui.js's Component (the same as
-- tools/tests/fake_uic.lua offline), each made of the calls src/tww3_mtb_crew_ui.lua has proven in the game, or, where the game's way is not
-- proven yet, of ONE function in ENGINE below with the probe item that answers it (tools/tests/port_probe.lua, docs/design/port-to-game.md 5,
-- stage 1) and what is done meanwhile.
--
--   local Uic = <this file>; local ui = Uic.new(layouts)        layouts: 'ui/tww3_mtb/' (tools/ship_ui.py writes them there)
--   ui.root(id)            a holder of the whole screen under core:get_ui_root(), the panel's root (Destroy it to close)
--   ui.by_id(id)           our component of that id (the first made), for the game's click and mouse events
--   ui.mouse_on(id)        the game's ComponentMouseOn: the hover children of the last one go, those of this one come
--   ui.count             components made (probe item 8 times the making of about 1500; this panel makes about 3800)
--
-- Never walks the game's components (ChildCount / Find broke the game's bindings, runs/20261104-191037): it holds a reference to everything it
-- makes and finds the game's own only by find_uicomponent along a path.

local Uic = {}

local floor = math.floor
-- the byte-exact string.find of Lua (the game's own is a 3-argument UTF-8 one: build/port_probe/lua_env_census.txt)
local sfind = string.find_lua or string.find
local function round(x) return floor(x + 0.5) end
local function log(text) pcall(function() _G.tww3_mtb_campaign.file_log('[ship ui] ' .. tostring(text)) end) end

-- ================ ENGINE: every call not proven in the game, one function each ================
local ENGINE = {}
-- probe 7: uic:TextDimensions() on our text component -> width, height, lines. Meanwhile (or if it fails): a measure by the characters at the
-- layout's size, one line per box's width. The one place where the game's measure of a text enters the panel.
-- ENGINE.measured counts which way each measure went (for the tests: did the panel's layout use the game's measures)
ENGINE.measured = {game = 0, chars = 0, empty = 0}
function ENGINE.measure_text(uic, text, layoutSize, boxW)
    -- the game answers at once with the width, the height wrapped to the component's width and a BOOLEAN third value (probe 14.11, item 7):
    -- the lines are counted from the height then
    local ok, w, h, n = pcall(function() return uic:TextDimensions() end)
    if ok and type(w) == 'number' and w > 0 then
        ENGINE.measured.game = ENGINE.measured.game + 1
        if type(n) ~= 'number' then n = math.max(1, floor((h or 0) / ((layoutSize or 16) * 1.35) + 0.5)) end
        return w, h, n
    end
    local m = ENGINE.measured
    if (text or '') == '' then m.empty = m.empty + 1 else m.chars = m.chars + 1 end
    local chars = 0
    for _ in string.gmatch(text or '', '[%z\1-\127\194-\244][\128-\191]*') do chars = chars + 1 end
    local width = chars * (layoutSize or 16) * 0.52
    local lines = (boxW and boxW > 0) and math.max(1, math.ceil(width / boxW)) or 1
    return math.min(width, boxW or width), lines * (layoutSize or 16) * 1.35, lines
end
-- The ink of the title on its plate (panel.js titlePlate): the page measures it on its font. The game's header font is not measured yet (probe 7
-- with the title's text): meanwhile the page's own numbers for «Дух Грунгни» at 32 units, which fit the plate's field at the layout's size.
function ENGINE.ink(text, size)
    local k = (size or 32) / 32
    return {w = 239.4 * k, left = 1 * k, right = 238.2 * k, ascent = 22 * k, descent = 9 * k, fontAscent = 34 * k, fontDescent = 10 * k}
end
-- A text's size other than its layout's: the game's text layouts have one size each (tools/ship_ui.py). A smaller title needs a layout of its own;
-- none is made while the title fits at its layout's size (it does at every root of 1600 x 900 and larger).
function ENGINE.set_text_size(uic, size, layoutSize)
    if size ~= layoutSize then log('the title wants size ' .. tostring(size) .. ', its layout has ' .. tostring(layoutSize)) end
end
-- probe 10: SetOpacity on a nested component (the dimmed web of lines under a lit slot). Proven only on the panel's backdrop.
function ENGINE.opacity(uic, a) pcall(function() uic:SetOpacity(a) end) end
-- The colour of a component's picture (the page's SetImageColour: the slot's state #FFFFFFB4 / #FFFFFF80, the lit line's gold and green, the bars):
-- not proven. Tried as uic:SetCurrentStateImageColour (index 0), else the alpha alone as the image's opacity; which one answered is logged once.
local tintWay = nil
function ENGINE.tint(uic, r, g, b, a)
    if tintWay ~= 'opacity' then
        local ok = pcall(function() uic:SetCurrentStateImageColour(0, r, g, b, a) end)
        if ok then if not tintWay then tintWay = 'colour'; log('tint: SetCurrentStateImageColour') end return end
    end
    if not tintWay then tintWay = 'opacity'; log('tint: no image colour, the alpha only') end
    pcall(function() uic:SetCurrentStateImageOpacity(0, a) end)
end
-- the picture fainter than its component's children (a card being recruited: the page's image opacity)
function ENGINE.image_opacity(uic, a) pcall(function() uic:SetCurrentStateImageOpacity(0, a) end) end
-- A window over everything (a building's window, a unit's panel, the crew's choice): the game's RegisterTopMost [файлы: in the game's scripts].
function ENGINE.top_most(uic) pcall(function() uic:RegisterTopMost() end) end
-- probe 6: the tree's window cuts its children (clipchildren="true" in our layout tree_window, tools/ship_ui.py). Proven by the probe of 14.11
-- (item 6a: the holder cuts its children, also after SetDockOffset). false would make the binding hide what lies outside the window itself
-- (cull below), kept only should the open be measured faster with it.
ENGINE.clips = true
-- probe 6: the mouse wheel over the tree. The game gives a script no wheel event (none in the game's scripts): the arrows, the track and the
-- handle's place move the tree (question V5: no drag). If the probe finds the game's list template scrolling our content, the tree goes into it.
ENGINE.wheel = false
-- The mouse's place along the scroll bar's track (a click there pages toward it): the game's event has no place. Meanwhile nil: a click on the
-- track pages down the tree.
function ENGINE.mouse_along() return nil end
-- probe 9 (only an experiment, the plan does not rest on it): ui/templates/building_frame with SetContextObject for our level. The probe of
-- 14.11: the template does not fill itself. false for good.
ENGINE.building_frame = false
-- A glow (a new detail, the tab of something new): the page draws a halo. The game's way is a state of the component with the picture again
-- under it, additive: our image layout has one state yet. Meanwhile none (the tab's «!» mark says it).
function ENGINE.glow(uic, on) end
-- The tree smaller («Всё дерево»): the game has no scale of a component's children. The binding lays the content out again at the scale:
-- every offset and size of the holder's descendants times z (the texts keep their size).
ENGINE.scale_by_layout = true

-- The number of a component's state images, to resize each with it (src/tww3_mtb_crew_ui.lua does so in the game today; no vanilla script calls
-- NumImages): one image, every layout of tools/ship_ui.py has, when the call does not answer.
function ENGINE.num_images(u)
    local ok, n = pcall(function() return u:NumImages() end)
    if ok and type(n) == 'number' then return n end
    return 1
end

-- ================ the components ================
local SKIN = {button_row = true, button_plate = true, button_mark = true}
function Uic.new(layouts, textLayouts)
    local env = {count = 0, ids = {}}
    local C = {}
    C.__index = C
    local function new(parent, id, layout, uic)
        local c = setmetatable({id = id, layout = layout, parent = parent, children = {}, x = 0, y = 0, w = 64, h = 64, visible = true, uic = uic}, C)
        if textLayouts and textLayouts[layout] then c.text = '' end
        if SKIN[layout] then c.state = 'active' end
        if parent then parent.children[#parent.children + 1] = c end
        env.count = env.count + 1
        if not env.ids[id] then env.ids[id] = c end
        return c
    end
    function C:CreateComponent(id, layout)
        local path = sfind(layout, '/', 1, true) and layout or (layouts .. layout)
        env.last_made = {id = id, layout = layout, path = path, parent = self.id, count = env.count}     -- for the tests: what was being made when a build fails
        return new(self, id, layout, UIComponent(self.uic:CreateComponent(id, path)))
    end
    function C:Id() return self.id end
    local function shown(c) return c.visible and not c.blank and not c.culled end
    function C:SetVisible(on) self.visible = on and true or false; self.uic:SetVisible(shown(self)) end
    function C:Visible() return self.visible end
    -- the size also of the state's images: a resized component keeps them otherwise (src/tww3_mtb_crew_ui.lua size)
    local function resize(c, w, h)
        local u = c.uic
        u:SetCanResizeWidth(true); u:SetCanResizeHeight(true)
        u:Resize(w, h)
        for i = 0, ENGINE.num_images(u) - 1 do
            u:SetCanResizeCurrentStateImageWidth(i, true); u:SetCanResizeCurrentStateImageHeight(i, true)
            u:ResizeCurrentStateImage(i, w, h)
        end
    end
    function C:Resize(w, h) self.w, self.h = round(w), round(h); resize(self, self.w * (self.k or 1), self.h * (self.k or 1)) end
    function C:Width() return self.w end
    function C:Height() return self.h end
    function C:SetDockOffset(x, y)
        self.x, self.y = round(x), round(y)
        self.uic:SetDockingPoint(1)
        self.uic:SetDockOffset(round(self.x * (self.k or 1)), round(self.y * (self.k or 1)))
    end
    function C:MoveTo(x, y) self.x, self.y = round(x), round(y); self.uic:MoveTo(self.x, self.y) end
    function C:SetImagePath(path) self.image = path; self.uic:SetImagePath(path, 0) end
    function C:SetStateText(t) if self.text ~= nil then self.text = t end; self.uic:SetStateText(t) end
    function C:GetStateText() return self.text or '' end
    function C:TextDimensions()
        if self.text == nil then return 0, 0, 0 end
        local spec = textLayouts and textLayouts[self.layout] or {}
        return ENGINE.measure_text(self.uic, self.text, spec.size, self.w)
    end
    function C:TextSize() return self.text_size or (textLayouts[self.layout] or {}).size or 0 end
    function C:SetTextSize(px) self.text_size = px; ENGINE.set_text_size(self.uic, px, (textLayouts[self.layout] or {}).size) end
    function C:InkDimensions() return ENGINE.ink(self.text, self:TextSize()) end
    function C:SetTooltipText(t) self.tooltip = t; self.uic:SetTooltipText(t or '', true) end
    function C:SetOpacity(a) self.opacity = a; ENGINE.opacity(self.uic, a) end
    function C:SetState(s) self.state = s; pcall(function() self.uic:SetState(s) end) end
    function C:CurrentState() return self.state end
    function C:ShaderTechniqueSet(name)
        self.shader = name
        pcall(function() self.uic:ShaderTechniqueSet(name, true); self.uic:ShaderVarsSet(1, 1, 0, 0, true) end)
    end
    function C:SetGlow(on, kind) self.glow = on and (kind or 'glow') or ''; ENGINE.glow(self.uic, on) end
    function C:SetImageColour(r, g, b, a) self.colour = {r, g, b, a}; ENGINE.tint(self.uic, r, g, b, a) end
    function C:SetInteractive(on) self.interactive = on and true or false; self.uic:SetInteractive(self.interactive) end
    function C:SetPassive() self.passive = true; self.uic:SetInteractive(false) end
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
    function C:SetLayer(name) self.layer = name; ENGINE.top_most(self.uic); return self end
    function C:SetHoverBrighten(k) self.brighten = k end
    function C:SetBlank(on) self.blank = on and true or nil; self.uic:SetVisible(shown(self)) end
    function C:SetImageOpacity(a) self.image_opacity = a; ENGINE.image_opacity(self.uic, a or 255) end
    function C:SetImageShown(on) ENGINE.image_opacity(self.uic, on and 255 or 0) end
    function C:SetTopmost() ENGINE.top_most(self.uic) end
    function C:SetClipChildren(on) self.clip = on end
    -- the tree under its window (panel.js pan.clamp): moved by SetDockOffset; at a smaller scale laid out again; what lies outside the window hidden
    -- while the game's clip is not proven (ENGINE.clips)
    local function relayout(c, k)
        for _, ch in ipairs(c.children) do
            ch.k = k
            resize(ch, round(ch.w * k), round(ch.h * k))
            ch.uic:SetDockOffset(round(ch.x * k), round(ch.y * k))
            relayout(ch, k)
        end
    end
    function C:SetContentOffset(x, y, z)
        self.x, self.y = x, y
        self.uic:SetDockingPoint(1)
        self.uic:SetDockOffset(round(x), round(y))
        if (z or 1) ~= (self.scale or 1) and ENGINE.scale_by_layout then relayout(self, z or 1) end
        self.scale = z or 1
        if not ENGINE.clips and self.parent then
            local W, H, k = self.parent.w, self.parent.h, self.scale
            for _, ch in ipairs(self.children) do
                if ch.layout == 'image' then
                    local l, t = x + ch.x * k, y + ch.y * k
                    local out = l + ch.w * k < 0 or t + ch.h * k < 0 or l > W or t > H
                    if (ch.culled or false) ~= out then ch.culled = out or nil; ch.uic:SetVisible(shown(ch)) end
                end
            end
        end
    end
    function C:Destroy() pcall(function() self.uic:Destroy() end) end

    function env.root(id)
        local ui = core:get_ui_root()
        env.last_made = {id = id, layout = 'layer_holder', path = layouts .. 'layer_holder', parent = 'ui root', count = env.count}
        local holder = new(nil, id, 'layer_holder', UIComponent(ui:CreateComponent(id, layouts .. 'layer_holder')))
        local W, H = ui:Width(), ui:Height()
        holder:Resize(W, H)
        holder:SetDockOffset(0, 0)
        return holder
    end
    function env.by_id(id) return env.ids[id] end
    local function enter(c)
        if c.state and SKIN[c.layout] and c.state == 'active' then c.state = 'hover' elseif c.state == 'selected' then c.state = 'selected_hover' end
        c.hovered = true
        if c.hoverChild then c.hoverChild:SetVisible(true) end
        for _, k in ipairs(c.hoverChildren or {}) do k:SetVisible(true) end
        if c.on_enter then c.on_enter() end
    end
    local function leave(c)
        if c.state == 'hover' then c.state = 'active' elseif c.state == 'selected_hover' then c.state = 'selected' end
        c.hovered = false
        if c.hoverChild then c.hoverChild:SetVisible(false) end
        for _, k in ipairs(c.hoverChildren or {}) do k:SetVisible(false) end
        if c.on_leave then c.on_leave() end
    end
    -- probe 5: ComponentMouseOn comes for our components (known from the game's scripts), ComponentMouseOff is not proven: the design needs none.
    -- The mouse coming onto any other of ours (the frame, the backdrop, the window's ground: all take the mouse) ends the last one's hover.
    function env.mouse_on(id)
        local c = env.ids[id]
        if env.hovered == c then return end
        if env.hovered then leave(env.hovered) end
        env.hovered = c
        if c then enter(c) end
    end
    -- For the tests (tools/tests/ship_session.lua), changes nothing: the components made under `top`, from this wrapper's own references (no walk
    -- of the game's components), in the rows of tools/tests/fake_uic.lua dump() (the same fields, the same paths; `top` written as 'root', as
    -- the fake's root is). Besides: culled, k (the scale a child was laid out at). live = true adds what the game's UIComponent itself answers
    -- for the row: ax, ay (Position), lw, lh (Bounds), lvis (Visible), lstate (CurrentState), ltext (GetStateText), td (TextDimensions, texts
    -- only), each read under pcall ({err} when it raises). lw, lh are the component's own Width() / Height(); bw, bh its Bounds(), which
    -- include its children (probe 14.11, item 6a).
    function env.dump(top, live)
        local out = {}
        local function ask(u, name, ...)
            local args = {...}
            local r = {pcall(function() return u[name](u, unpack(args)) end)}
            if not r[1] then return {err = tostring(r[2])} end
            return r
        end
        local function walk(c, path)
            local row = {path = path, id = c.id, layout = c.layout, x = c.x, y = c.y, w = c.w, h = c.h, visible = c.visible}
            if c == top then row.id, row.layout = 'root', 'root' end
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
            if c.culled then row.culled = true end
            if c.k and c.k ~= 1 then row.k = c.k end
            if live and c.uic then
                local u = c.uic
                local p = ask(u, 'Position'); if p.err then row.ax = p else row.ax, row.ay = p[2], p[3] end
                local w = ask(u, 'Width'); row.lw = w.err and w or w[2]
                local h = ask(u, 'Height'); row.lh = h.err and h or h[2]
                local b = ask(u, 'Bounds'); if b.err then row.bw = b else row.bw, row.bh = b[2], b[3] end
                local v = ask(u, 'Visible'); row.lvis = v.err and v or v[2]
                local s = ask(u, 'CurrentState'); row.lstate = s.err and s or s[2]
                if c.text ~= nil then
                    local t = ask(u, 'GetStateText'); row.ltext = t.err and t or t[2]
                    local d = ask(u, 'TextDimensions'); row.td = d.err and d or {d[2], d[3], d[4]}
                end
            end
            out[#out + 1] = row
            local seen = {}
            for _, k in ipairs(c.children) do
                seen[k.id] = (seen[k.id] or 0) + 1
                walk(k, path .. '/' .. k.id .. (seen[k.id] > 1 and ('#' .. seen[k.id]) or ''))
            end
        end
        walk(top, 'root')
        return out
    end
    env.ENGINE = ENGINE
    return env
end

Uic.ENGINE = ENGINE
return Uic
