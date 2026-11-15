-- The components src/tww3_mtb_ship_ui.lua draws with, over the game's UIComponent: the methods of web/js/gameui.js's Component (the same as
-- tools/tests/fake_uic.lua offline), each made of the calls src/tww3_mtb_crew_ui.lua has proven in the game, or, where the game's way is not
-- proven yet, of ONE function in ENGINE below with the probe item that answers it (tools/tests/port_probe.lua, docs/design/port-to-game.md 5,
-- stage 1, and 8: the results of the probe of 14.11) and what is done meanwhile.
--
--   local Uic = <this file>; local ui = Uic.new(layouts)        layouts: 'ui/tww3_mtb/' (tools/ship_ui.py writes them there)
--   ui.root(id)            a holder of the whole screen under core:get_ui_root(), the panel's root (shown and hidden by the screen, Destroy at the end)
--   ui.by_id(id)           our component of that id (the first made), for the game's click and mouse events
--   ui.mouse_on(id)        the game's ComponentMouseOn: the hover children of the last one go, those of this one come; nil: none hovered
--   ui.count               components made
--   ui.profile             with ENGINE.profile on: the calls into the game's UIComponent by method, {calls = {name = n}, seconds = {name = s}}
--
-- What the game's UIComponent does that the page's Component does not, and how this binding makes the page's look of it (the first session in the
-- game, runs/20261114-230723-ship_panel):
--   * Resize scales the component's children with it unless its third argument is false (a unit's panel, made at the layout's 64 x 64 and sized to
--     290 x 499 after its children, blew them up 4.5 x 7.8): resized with false, and checked once on the first resize of a component that has
--     children; should the children still follow, they get their sizes back (ENGINE.children_keep).
--   * No colour of a picture at run time (no SetCurrentStateImageColour): a coloured picture is a picture coloured in advance (tools/ship_ui.py TINTS,
--     tint_path below); the alpha of the page's colour is an opacity.
--   * SetOpacity dims the component's own picture only, PropagateOpacity sets it on every descendant (the session's step opacity). The page's opacity
--     dims a component with all it holds: here each component's opacity is the product of its own and its ancestors', set on each picture.
--   * Every call into the game is made once for a value: a size, a place, a text, a visibility, a picture, a shader set again unchanged is not sent
--     again, and a text's measure is asked again only when its text or its width changed.
--
-- Never walks the game's components (ChildCount / Find broke the game's bindings, runs/20261104-191037): it holds a reference to everything it
-- makes and finds the game's own only by find_uicomponent along a path.

local Uic = {}

local floor = math.floor
-- the byte-exact string.find / sub of Lua (the game's own are 3-argument UTF-8 ones: build/port_probe/lua_env_census.txt)
local sfind = string.find_lua or string.find
local ssub = string.sub_lua or string.sub
local function round(x) return floor(x + 0.5) end
local function log(text) pcall(function() _G.tww3_mtb_campaign.file_log('[ship ui] ' .. tostring(text)) end) end

-- ================ ENGINE: every call not proven in the game, one function each ================
local ENGINE = {}
-- probe 7: uic:TextDimensions() on our text component -> width, height wrapped to the component's width, a BOOLEAN (probe 14.11, item 7). Should
-- it fail: a measure by the characters at the layout's size, one line per box's width. The one place where the game's measure of a text enters.
-- ENGINE.measured counts which way each measure went (for the tests: did the panel's layout use the game's measures)
ENGINE.measured = {game = 0, chars = 0, empty = 0, cached = 0}
function ENGINE.measure_text(uic, text, layoutSize, boxW)
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
-- SetOpacity: the component's own picture only (probe 14.11, item 10; the session's step opacity: set_80 leaves the child at 255).
function ENGINE.opacity(uic, a) uic:SetOpacity(a) end
-- PropagateOpacity on a component that HAS a picture sets the opacity on it and on all its descendants (the session's step opacity:
-- propagate_80, parent 80, child 80). On a holder without a picture: not proven, not used.
function ENGINE.propagate_opacity(uic, a) uic:PropagateOpacity(a) end
-- The picture's own opacity under its children (a card being recruited: the page's image opacity): proven in the probe's smoke
function ENGINE.image_opacity(uic, a) pcall(function() uic:SetCurrentStateImageOpacity(0, a) end) end
-- A picture coloured in advance (tools/ship_ui.py TINTS, tint_path): the game has no colour of a picture at run time (probe 14.11, item 0)
local HEX = '0123456789abcdef'
local function hex2(v) v = math.max(0, math.min(255, round(v))); local hi = floor(v / 16); local lo = v - hi * 16; return ssub(HEX, hi + 1, hi + 1) .. ssub(HEX, lo + 1, lo + 1) end
function ENGINE.tint_path(path, r, g, b)
    local stem = string.match(path or '', '([^/]+)%.png$')
    if not stem then return nil end
    return 'ui/tww3_mtb/tint/' .. stem .. '_' .. hex2(r) .. hex2(g) .. hex2(b) .. '.png'
end
-- A window over everything (a building's window, a unit's panel, the crew's choice): the game's RegisterTopMost [файлы: in the game's scripts].
function ENGINE.top_most(uic) pcall(function() uic:RegisterTopMost() end) end
-- probe 6: the tree's window cuts its children: clipchildren="true" on the component of our layout tree_window (tools/ship_ui.py with_attrs; the
-- first session had it on the layout's hierarchy node, where the game ignores it, and the tree spilled over the panel). Proven by the probe of 14.11
-- (item 6a: the holder cuts its children, also after SetDockOffset). false: the binding hides the pictures of the tree that lie wholly outside the
-- window (cull below): a fallback that leaves lines across the window's edge drawn.
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
-- The texts of the tree at a smaller scale: the game keeps a text's size in its smaller box and cuts it with «…» (the first session, ss_whole_tree.png:
-- the costs read «1.», «3.»), while the page draws them a third of their size, too small to read. Hidden while the tree is smaller.
ENGINE.zoom_hides_texts = true
-- The hover state's brighten of the game's building browser (building_browser.twui.xml: shader_name="brighten_t0" on the slot's hover state; the
-- page's SetHoverBrighten): the shader set while the mouse is over a component that asks for it, its own shader back after. Not proven in the game:
-- false draws no brighten.
ENGINE.hover_brighten = true
function ENGINE.brighten(uic, on, base) pcall(function() uic:ShaderTechniqueSet(on and 'brighten_t0' or (base or 'normal_t0'), true) end) end
-- Resize(w, h, false): the children keep their sizes (the game's scripts pass the third argument: lib_scripted_tours.lua). nil until the first
-- resize of a component with children has been checked against a child's Width() / Height(); false then: the children got scaled anyway, and the
-- binding gives them their sizes back after each such resize.
ENGINE.children_keep = nil
function ENGINE.resize(uic, w, h) uic:Resize(w, h, false) end
-- The game's advisor sits over our root (runs/20261114-230723-ship_panel: it covered the treasury; probe 11). The game's own full screen panels
-- have it out of the way; the game's scripts find it as find_uicomponent(root, 'advice_interface') (lib_core.lua cache_and_set_advisor_priority).
-- Hidden while our panel is open (and again on AdviceIssued, src/tww3_mtb_ship_screen.lua), shown again as it was on close (shown when advice came
-- meanwhile: restore(true)). Returns the restore.
function ENGINE.hide_advisor()
    local ok, adv = pcall(function() return find_uicomponent(core:get_ui_root(), 'advice_interface') end)
    if not ok or not adv then return function() end end
    local okv, was = pcall(function() return adv:Visible() end)
    pcall(function() adv:SetVisible(false) end)
    return function(force) if force or (okv and was) then pcall(function() adv:SetVisible(true) end) end end
end
-- The calls into the game's UIComponent counted and timed by method (os.clock), for the session: which call makes the opening slow. Off: no cost.
ENGINE.profile = false

-- The number of a component's state images, to resize each with it (src/tww3_mtb_crew_ui.lua does so in the game today): asked once per layout
-- (0 for a holder, 1 for a picture, 2 for a button: the probe's smoke).
function ENGINE.num_images(u)
    local ok, n = pcall(function() return u:NumImages() end)
    if ok and type(n) == 'number' then return n end
    return 1
end

-- The layouts of tools/ship_ui.py and tools/crew_ui.py without a picture (holders): the opacity goes past them to their children. Every other
-- layout that is not a text has a picture (layer_holder a transparent one, for PropagateOpacity).
local NO_PICTURE = {tree_page = true, tree_window = true, tree_holder = true, hover_holder = true, hit_area = true, zone = true}
Uic.NO_PICTURE = NO_PICTURE

-- ================ the components ================
local SKIN = {button_row = true, button_plate = true, button_mark = true}
function Uic.new(layouts, textLayouts)
    local env = {count = 0, ids = {}}
    local C = {}
    C.__index = C
    local nimages = {}          -- layout -> its number of state images (NumImages, once per layout)
    local P = nil
    if ENGINE.profile then P = {calls = {}, seconds = {}}; env.profile = P end
    local clock = os.clock
    local function profiled(u)
        return setmetatable({}, {__index = function(_, k)
            local f = u[k]
            if type(f) ~= 'function' then return f end
            return function(_, ...)
                local t0 = clock()
                local r = {f(u, ...)}
                P.seconds[k] = (P.seconds[k] or 0) + (clock() - t0)
                P.calls[k] = (P.calls[k] or 0) + 1
                return unpack(r)
            end
        end})
    end
    local function apply_opacity(c, peff) end         -- below
    local function new(parent, id, layout, uic)
        if P then uic = profiled(uic) end
        local c = setmetatable({id = id, layout = layout, parent = parent, children = {}, x = 0, y = 0, w = 64, h = 64, visible = true, uic = uic,
                                ev = true, alpha = 255, eff = 255, dimmed = 0}, C)
        c.text_layout = textLayouts and textLayouts[layout] and true or nil
        c.picture = not c.text_layout and not NO_PICTURE[layout]
        if c.text_layout then c.text = '' end
        if SKIN[layout] then c.state = 'active' end
        if parent then
            parent.children[#parent.children + 1] = c
            -- under a dimmed component: dimmed with it (the page's opacity is that of all a component holds)
            if parent.eff < 255 then apply_opacity(c, parent.eff) end
        end
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
    local function shown(c) return c.visible and not c.blank and not c.culled and not c.zoomed end
    local function show(c)
        local on = shown(c) and true or false
        if c.ev ~= on then c.ev = on; c.uic:SetVisible(on) end
    end
    function C:SetVisible(on) self.visible = on and true or false; show(self) end
    function C:Visible() return self.visible end

    -- ---- the size: the game's Resize with the children kept, the state's images with it (a resized component keeps them otherwise) ----
    local function images(c)
        local n = nimages[c.layout]
        if n == nil then n = c.text_layout and 0 or ENGINE.num_images(c.uic); nimages[c.layout] = n end
        return n
    end
    local function engine_size(c, w, h, force)
        if not force and c.ew == w and c.eh == h then return end
        local u = c.uic
        if not c.can_resize then u:SetCanResizeWidth(true); u:SetCanResizeHeight(true) end
        ENGINE.resize(u, w, h)
        for i = 0, images(c) - 1 do
            if not c.can_resize then u:SetCanResizeCurrentStateImageWidth(i, true); u:SetCanResizeCurrentStateImageHeight(i, true) end
            u:ResizeCurrentStateImage(i, w, h)
        end
        c.can_resize = true
        c.ew, c.eh = w, h
    end
    -- the children's sizes given back, when the game scaled them with their parent (ENGINE.children_keep false)
    local function resize_back(c)
        for _, ch in ipairs(c.children) do
            if ch.ew then engine_size(ch, ch.ew, ch.eh, true) end
            resize_back(ch)
        end
    end
    local function resize(c, w, h)
        local had = c.ew
        engine_size(c, w, h)
        if not had or #c.children == 0 or ENGINE.children_keep == true then return end
        if ENGINE.children_keep == nil then
            local ch = nil
            for _, k in ipairs(c.children) do if k.ew then ch = k; break end end
            if not ch then return end
            local okw, cw = pcall(function() return ch.uic:Width() end)
            local okh, chh = pcall(function() return ch.uic:Height() end)
            if not (okw and okh and type(cw) == 'number' and type(chh) == 'number') then return end
            ENGINE.children_keep = math.abs(cw - ch.ew) <= 1 and math.abs(chh - ch.eh) <= 1
            log('Resize(w, h, false): the children ' .. (ENGINE.children_keep and 'keep their sizes' or ('follow their parent (' .. ch.id .. ' ' .. tostring(cw) .. ' x ' .. tostring(chh) .. ' for ' .. ch.ew .. ' x ' .. ch.eh .. '): given back after each resize')))
        end
        if ENGINE.children_keep == false then resize_back(c) end
    end
    function C:Resize(w, h) self.w, self.h = round(w), round(h); resize(self, round(self.w * (self.k or 1)), round(self.h * (self.k or 1))) end
    function C:Width() return self.w end
    function C:Height() return self.h end
    local function dock(c, x, y)
        if not c.docked then c.uic:SetDockingPoint(1); c.docked = true elseif c.ex == x and c.ey == y then return end
        c.ex, c.ey = x, y
        c.uic:SetDockOffset(x, y)
    end
    function C:SetDockOffset(x, y)
        self.x, self.y = round(x), round(y)
        dock(self, round(self.x * (self.k or 1)), round(self.y * (self.k or 1)))
    end
    function C:MoveTo(x, y) self.x, self.y = round(x), round(y); self.uic:MoveTo(self.x, self.y) end

    -- ---- pictures, colours, opacity ----
    local function engine_image(c)
        local path = c.tinted or c.image
        if path and c.eimage ~= path then c.eimage = path; c.uic:SetImagePath(path, 0) end
    end
    function C:SetImagePath(path)
        self.image = path
        if self.rgb then self.tinted = ENGINE.tint_path(path, self.rgb[1], self.rgb[2], self.rgb[3]) end
        engine_image(self)
    end
    -- the opacity each component draws with: its own times its ancestors' (the page's), set on its picture; a whole subtree of undimmed
    -- components under one with a picture by one PropagateOpacity
    local function mark_below(c, eff)
        for _, ch in ipairs(c.children) do ch.eff = eff; mark_below(ch, eff) end
    end
    apply_opacity = function(c, peff)
        local eff = round(peff * c.alpha / 255)
        if eff == c.eff and not c.fresh_alpha then return end
        c.fresh_alpha = nil
        c.eff = eff
        if c.picture and c.dimmed == 0 then
            ENGINE.propagate_opacity(c.uic, eff)
            mark_below(c, eff)
            return
        end
        if not NO_PICTURE[c.layout] then ENGINE.opacity(c.uic, eff) end
        for _, ch in ipairs(c.children) do apply_opacity(ch, eff) end
    end
    local function set_alpha(c, a)
        a = round(a or 255)
        if c.alpha == a then return end
        local was = c.alpha < 255
        c.alpha = a
        if was ~= (a < 255) then
            local d = a < 255 and 1 or -1
            local p = c.parent
            while p do p.dimmed = p.dimmed + d; p = p.parent end
        end
        c.fresh_alpha = true
        apply_opacity(c, c.parent and c.parent.eff or 255)
    end
    function C:SetOpacity(a) self.opacity = a; set_alpha(self, a) end
    -- the page's colour of a picture: the alpha an opacity, a colour a picture coloured in advance, a grey (a multiply that darkens) not drawn
    local warnedGrey = false
    function C:SetImageColour(r, g, b, a)
        self.colour = {r, g, b, a}
        set_alpha(self, a)
        if r == 255 and g == 255 and b == 255 then self.rgb, self.tinted = nil, nil
        elseif r == g and g == b then
            self.rgb, self.tinted = nil, nil
            if not warnedGrey then warnedGrey = true; log('a grey colour of a picture is not drawn (no picture made for it): ' .. tostring(self.id)) end
        else
            self.rgb = {r, g, b}
            self.tinted = ENGINE.tint_path(self.image, r, g, b)
        end
        engine_image(self)
    end
    function C:SetImageOpacity(a) self.image_opacity = a; ENGINE.image_opacity(self.uic, a or 255) end
    function C:SetImageShown(on) ENGINE.image_opacity(self.uic, on and 255 or 0) end

    -- ---- texts ----
    function C:SetStateText(t)
        if self.text ~= nil then self.text = t end
        if self.etext ~= t then self.etext = t; self.uic:SetStateText(t) end
    end
    function C:GetStateText() return self.text or '' end
    function C:TextDimensions()
        if self.text == nil then return 0, 0, 0 end
        -- asked of the game again only when the text or the component's width changed
        local key = self.text .. '\0' .. tostring(self.ew or self.w)
        if self.mkey == key then ENGINE.measured.cached = ENGINE.measured.cached + 1; return self.mw, self.mh, self.mn end
        local spec = textLayouts and textLayouts[self.layout] or {}
        local w, h, n = ENGINE.measure_text(self.uic, self.text, spec.size, self.w)
        self.mkey, self.mw, self.mh, self.mn = key, w, h, n
        return w, h, n
    end
    function C:TextSize() return self.text_size or (textLayouts[self.layout] or {}).size or 0 end
    function C:SetTextSize(px) self.text_size = px; ENGINE.set_text_size(self.uic, px, (textLayouts[self.layout] or {}).size) end
    function C:InkDimensions() return ENGINE.ink(self.text, self:TextSize()) end
    function C:SetTooltipText(t)
        self.tooltip = t
        if self.etip ~= (t or '') then self.etip = t or ''; self.uic:SetTooltipText(t or '', true) end
    end
    function C:SetState(s) self.state = s; pcall(function() self.uic:SetState(s) end) end
    function C:CurrentState() return self.state end
    local function engine_shader(c)
        local name = c.shader or 'normal_t0'
        local want = (c.hovered and c.brighten and ENGINE.hover_brighten and name == 'normal_t0') and 'brighten_t0' or name
        if c.eshader == want then return end
        if want == 'brighten_t0' or c.eshader == 'brighten_t0' then ENGINE.brighten(c.uic, want == 'brighten_t0', name)
        else pcall(function() c.uic:ShaderTechniqueSet(want, true); c.uic:ShaderVarsSet(1, 1, 0, 0, true) end) end
        c.eshader = want
    end
    function C:ShaderTechniqueSet(name) self.shader = name; engine_shader(self) end
    function C:SetGlow(on, kind) self.glow = on and (kind or 'glow') or ''; ENGINE.glow(self.uic, on) end
    function C:SetInteractive(on)
        self.interactive = on and true or false
        if self.einteractive ~= self.interactive then self.einteractive = self.interactive; self.uic:SetInteractive(self.interactive) end
    end
    function C:SetPassive() self.passive = true; if self.einteractive ~= false then self.einteractive = false; self.uic:SetInteractive(false) end end
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
    function C:SetLayer(name)
        self.layer = name
        if not self.topmost then self.topmost = true; ENGINE.top_most(self.uic) end
        return self
    end
    function C:SetHoverBrighten(k) self.brighten = k end
    function C:SetBlank(on) self.blank = on and true or nil; show(self) end
    function C:SetTopmost() if not self.topmost then self.topmost = true; ENGINE.top_most(self.uic) end end
    function C:SetClipChildren(on) self.clip = on end
    -- the tree under its window (panel.js pan.clamp): moved by SetDockOffset; at a smaller scale laid out again (hidden meanwhile: one change for the
    -- game to draw); what lies outside the window hidden only when the game does not clip (ENGINE.clips)
    local function relayout(c, k)
        for _, ch in ipairs(c.children) do
            ch.k = k
            if ch.text_layout and ENGINE.zoom_hides_texts then ch.zoomed = k < 1 or nil; show(ch) end
            resize(ch, round(ch.w * k), round(ch.h * k))
            if ch.docked then dock(ch, round(ch.x * k), round(ch.y * k)) end
            relayout(ch, k)
        end
    end
    function C:SetContentOffset(x, y, z)
        self.x, self.y = x, y
        dock(self, round(x), round(y))
        if (z or 1) ~= (self.scale or 1) and ENGINE.scale_by_layout then
            local on = self.ev
            if on then self.uic:SetVisible(false) end
            relayout(self, z or 1)
            if on then self.uic:SetVisible(true) end
        end
        self.scale = z or 1
        if not ENGINE.clips and self.parent then
            local W, H, k = self.parent.w, self.parent.h, self.scale
            for _, ch in ipairs(self.children) do
                if ch.picture then
                    local l, t = x + ch.x * k, y + ch.y * k
                    local out = l + ch.w * k < 0 or t + ch.h * k < 0 or l > W or t > H
                    if (ch.culled or false) ~= out then ch.culled = out or nil; show(ch) end
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
        env.root_size = {W, H}
        return holder
    end
    function env.by_id(id) return env.ids[id] end
    local function enter(c)
        if c.state and SKIN[c.layout] and c.state == 'active' then c.state = 'hover' elseif c.state == 'selected' then c.state = 'selected_hover' end
        c.hovered = true
        if c.brighten then engine_shader(c) end
        if c.hoverChild then c.hoverChild:SetVisible(true) end
        for _, k in ipairs(c.hoverChildren or {}) do k:SetVisible(true) end
        if c.on_enter then c.on_enter() end
    end
    local function leave(c)
        if c.state == 'hover' then c.state = 'active' elseif c.state == 'selected_hover' then c.state = 'selected' end
        c.hovered = false
        if c.brighten then engine_shader(c) end
        if c.hoverChild then c.hoverChild:SetVisible(false) end
        for _, k in ipairs(c.hoverChildren or {}) do k:SetVisible(false) end
        if c.on_leave then c.on_leave() end
    end
    -- probe 5: ComponentMouseOn comes for our components (known from the game's scripts), ComponentMouseOff is not proven: the design needs none.
    -- The mouse coming onto any other of ours (the frame, the backdrop, the window's ground: all take the mouse) ends the last one's hover.
    function env.mouse_on(id)
        local c = id and env.ids[id] or nil
        if env.hovered == c then return end
        if env.hovered then leave(env.hovered) end
        env.hovered = c
        if c then enter(c) end
    end
    -- For the tests (tools/tests/ship_session.lua, tools/ui_layout_check.py), changes nothing: the components made under `top`, from this wrapper's
    -- own references (no walk of the game's components), in the rows of tools/tests/fake_uic.lua dump() (the same fields, the same paths; `top`
    -- written as 'root', as the fake's root is). Besides: culled, k (the scale a child was laid out at), drawn (the opacity its picture is drawn
    -- with, when not 255), tinted (the picture coloured in advance set in place of `image`). live = true adds what the game's UIComponent itself
    -- answers for the row: ax, ay (Position), lw, lh (its own Width() / Height()), bw, bh (Bounds(): with its children, probe 14.11 6a), lvis
    -- (Visible), lstate (CurrentState), ltext (GetStateText), td (TextDimensions, texts only), each read under pcall ({err} when it raises).
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
            if c.eff ~= 255 then row.drawn = c.eff end
            if c.tinted then row.tinted = c.tinted end
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
                if c.picture then local o = ask(u, 'Opacity'); row.lop = o.err and o or o[2] end
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
