-- Test harness: runs Lua sent by tools/rc.py while the game runs (frontend, campaign, battle). Only in the test pack
-- tww3_mtb_harness.pack (tools/build.py --target campaign), never in the mod itself. Files in the game's folder:
--   tww3_mtb_cmd.lua    first line "--id N", then the code; run once per id
--   tww3_mtb_rc.jsonl   one line per result: {"id":N,"ok":true,"result":"...","mode":"..."}
local CMD, RC, EVENTS = 'tww3_mtb_cmd.lua', 'tww3_mtb_rc.jsonl', 'tww3_mtb_events.jsonl'

if _G.mtb then return end

local function quote(s)
    local escaped = string.gsub(tostring(s), '[%z\1-\31\\"]', function(c)
        return string.format('\\u%04x', string.byte(c))
    end)
    return '"' .. escaped .. '"'
end

local function dump(v, depth)
    depth = depth or 4
    if type(v) ~= 'table' or depth <= 0 then return tostring(v) end
    local out = {}
    for k, x in pairs(v) do out[#out + 1] = tostring(k) .. '=' .. dump(x, depth - 1) end
    table.sort(out)
    return '{' .. table.concat(out, ', ') .. '}'
end

local function append(path, line)
    local f = io.open(path, 'a')
    if f then
        f:write(line .. '\n')
        f:close()
    end
end

local mode = (bm and 'battle') or (cm and 'campaign') or 'frontend'
local M = {mode = mode, dump = dump}
_G.mtb = M

function M.log(event, text)
    append(EVENTS, '{"event":' .. quote(event) .. ',"mode":' .. quote(mode) .. ',"text":' .. quote(text) .. '}')
end

-- UI ----------------------------------------------------------------------------------------------
local function ui_root()
    return core:get_ui_root()
end

-- Depth-first search by component id, optionally only visible ones. Returns the component.
function M.find(name, visible_only, root)
    local function walk(uic)
        if uic:Id() == name and (not visible_only or uic:VisibleFromRoot()) then return uic end
        for i = 0, uic:ChildCount() - 1 do
            local found = walk(UIComponent(uic:Find(i)))
            if found then return found end
        end
    end
    return walk(root or ui_root())
end

function M.click(name, root)
    local uic = M.find(name, true, root)
    if not uic then return 'not found: ' .. name end
    uic:SimulateLClick()
    return 'clicked ' .. name .. ' state ' .. tostring(uic:CurrentState())
end

-- The visible tree as text. depth: how deep; filter: Lua pattern on the id (only matching lines are kept).
function M.tree(depth, filter, root)
    local lines = {}
    local function walk(uic, d, indent)
        if not uic:Visible() then return end
        local id = uic:Id()
        if not filter or string.find(id, filter) then
            lines[#lines + 1] = indent .. id .. ' [' .. tostring(uic:CurrentState()) .. ']'
        end
        if d > 0 then
            for i = 0, uic:ChildCount() - 1 do
                walk(UIComponent(uic:Find(i)), d - 1, indent .. ' ')
            end
        end
    end
    walk(root or ui_root(), depth or 3, '')
    return table.concat(lines, '\n')
end

-- Names of the members of a table or a game object.
function M.keys(t)
    local out = {}
    local function scan(x)
        for k, v in pairs(x) do out[#out + 1] = tostring(k) .. ':' .. type(v) end
    end
    if type(t) == 'table' then scan(t) end
    local mt = getmetatable(t)
    if mt and type(mt) == 'table' then
        if type(mt.__index) == 'table' then scan(mt.__index) else scan(mt) end
    end
    table.sort(out)
    return table.concat(out, ' ')
end

-- Remote loop ---------------------------------------------------------------------------------------
local last_id = -1

local function poll()
    local f = io.open(CMD, 'r')
    if not f then return end
    local text = f:read('*a')
    f:close()
    local id = tonumber(string.match(text or '', '^%-%-id (%d+)'))
    if not id or id == last_id then return end
    last_id = id
    local fn, err = loadstring(text)
    local ok, result
    if not fn then
        ok, result = false, err
    else
        setfenv(fn, getfenv(1))
        ok, result = pcall(fn)
    end
    append(RC, '{"id":' .. id .. ',"ok":' .. tostring(ok) .. ',"mode":' .. quote(mode) .. ',"result":' .. quote(dump(result)) .. '}')
end

local function guarded_poll()
    local ok, err = pcall(poll)
    if not ok then M.log('remote_error', err) end
end

local function start(tm)
    -- Lua restarts with each mode, so the id of the last command is taken from the file: it has run already.
    local f = io.open(CMD, 'r')
    if f then
        last_id = tonumber(string.match(f:read('*a') or '', '^%-%-id (%d+)')) or -1
        f:close()
    end
    M.log('remote_ready', tostring(tm ~= nil))
    tm:repeat_real_callback(guarded_poll, 300, 'tww3_mtb_remote')
end

-- Each mode has its own timer manager and its own moment when it is ready.
if mode == 'battle' then
    start(bm.tm)
elseif mode == 'campaign' then
    cm:add_first_tick_callback(function()
        start(cm.tm)
        for _, event in ipairs({'MissionSucceeded', 'MissionFailed', 'MissionCancelled'}) do
            core:add_listener('tww3_mtb_remote_' .. event, event, true, function(context)
                M.log('mission', event .. ' ' .. context:mission():mission_record_key())
            end, true)
        end
    end)
else
    core:add_ui_created_callback(function() start(core.tm) end)
end
M.log('remote_loaded', mode)
