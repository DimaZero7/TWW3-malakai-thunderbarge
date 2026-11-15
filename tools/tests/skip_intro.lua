-- Harness only, sent through the remote (tools/crew_cycle.py Session.timeline_lua), never in the mod. Two jobs:
-- 1. The timeline: "timeline" lines in tww3_mtb_events.jsonl with the wall clock (os.date, 1 s): installed, the loading screen
--    dismissed, each skip, the intro's end events, the player's turn end and turn start. tools/session_timeline.py reads them.
-- 2. With mtb_skip = "1" on a new game: the faction intro skipped the way the player skips it. The game calls
--    cm:on_key_press_up("ESCAPE") when Esc is pressed while a script holds the key (_lib/lib_campaign_manager.lua 13381-13401);
--    this script calls the same function, only while the top of the Esc stack is one of the intro's own entries:
--      movie_overlay_skip_monitor_intro_movie    the fullscreen movie (_lib/lib_movie_overlay.lua 851, skip 973)
--      Campaign_Cutscene_<faction>_intro         the flyover cindyscene (lib_campaign_manager.lua 2548, 2587)
--      Campaign_Cutscene_post_intro_scene        the post-intro scene (main_warhammer_faction_intro.lua 359), whose end
--                                                callback fires ScriptEventCampaignIntroComplete (290-291)
--    Every end callback of the game runs as after a player's Esc (lib_campaign_cutscene.lua 1477). No key, no mouse, no focus.
--    Stops at ScriptEventCampaignIntroComplete or after 300 s. Anything else on top of the stack is never pressed.
-- Returns a report: "skip=on new=true done=false skipped=movie,flyover state=watching".
local want_skip = (mtb_skip == "1")
local S = _G.mtb_skip_intro
if S then
  if want_skip then S.enable() end
  return S.report()
end

S = {skip = false, skipped = {}, complete = false, state = 'timeline only', errors = 0}
_G.mtb_skip_intro = S
local new_game = cm:is_new_game() and true or false
S.new_game = new_game

local function stamp(what)
  mtb.log('timeline', os.date('%H:%M:%S') .. ' ' .. what)
end
S.stamp = stamp

local function starts(s, prefix)
  return string.sub(s, 1, string.len(prefix)) == prefix
end
local function ends(s, suffix)
  return string.len(s) >= string.len(suffix) and string.sub(s, string.len(s) - string.len(suffix) + 1) == suffix
end

-- The kind of an Esc entry of the intro, or nil.
function S.kind(name)
  name = tostring(name)
  if name == 'movie_overlay_skip_monitor_intro_movie' then return 'movie' end
  if name == 'Campaign_Cutscene_post_intro_scene' then return 'post_intro_scene' end
  if starts(name, 'Campaign_Cutscene_') and ends(name, '_intro') then return 'flyover' end
  return nil
end

local function top_entry()
  local stack = cm.stolen_keys and cm.stolen_keys['ESCAPE']
  if type(stack) ~= 'table' or #stack == 0 then return nil end
  return stack[#stack]
end

function S.report()
  local top = top_entry()
  return 'skip=' .. (S.skip and 'on' or 'off') .. ' new=' .. tostring(S.new_game) .. ' done=' .. tostring(S.complete or not S.new_game)
    .. ' skipped=' .. (#S.skipped > 0 and table.concat(S.skipped, ',') or 'none') .. ' state=' .. S.state
    .. ' esc_top=' .. (top and tostring(top.name) or 'none')
end

local function listen(event, condition, text)
  core:add_listener('tww3_mtb_timeline_' .. event, event, condition, function(context)
    local ok, line = pcall(text, context)
    stamp(ok and line or (event .. ' (' .. tostring(line) .. ')'))
  end, true)
end

local me = cm:get_local_faction_name(true)
listen('LoadingScreenDismissed', true, function() return 'loading screen dismissed' end)
listen('ScriptEventCampaignIntroCutsceneCompleted', true, function(c) return 'intro cutscene completed ' .. tostring(c.string) end)
listen('ScriptEventIntroCutsceneFinished', true, function() return 'ScriptEventIntroCutsceneFinished' end)
listen('FactionTurnEnd', function(c) return c:faction():name() == me end, function() return 'turn end ' .. cm:turn_number() end)
listen('FactionTurnStart', function(c) return c:faction():name() == me end, function() return 'turn start ' .. cm:turn_number() end)
core:add_listener('tww3_mtb_timeline_intro_complete', 'ScriptEventCampaignIntroComplete', true, function()
  S.complete = true
  if S.skip then S.state = 'complete' end
  stamp('intro complete (ScriptEventCampaignIntroComplete)')
end, true)

local NAME = 'tww3_mtb_skip_intro'
local seen = {}
local deadline

local function stop(state)
  S.state = state
  core:get_tm():remove_real_callback(NAME)
end

local function watch()
  if S.complete then return stop('complete') end
  if os.time() > deadline then
    stamp('skip_intro: stopped after 300 s, the intro did not report complete')
    return stop('timed out')
  end
  local top = top_entry()
  local kind = top and S.kind(top.name)
  if not kind then return end
  seen[top.name] = (seen[top.name] or 0) + 1
  if seen[top.name] < 2 then return end      -- on the stack for one poll first: the entry and its first actions are in place
  seen[top.name] = nil
  S.skipped[#S.skipped + 1] = kind
  stamp('skip ' .. kind .. ' (' .. tostring(top.name) .. ')')
  cm:on_key_press_up('ESCAPE')
end

function S.enable()
  if S.skip then return end
  if not S.new_game then
    S.state = 'not a new game: nothing to skip'
    return
  end
  S.skip = true
  S.state = 'watching'
  deadline = os.time() + 300
  stamp('skip_intro on')
  core:get_tm():repeat_real_callback(function()
    local ok, err = pcall(watch)
    if not ok then
      S.errors = S.errors + 1
      stamp('skip_intro error: ' .. tostring(err))
      if S.errors >= 3 then stop('error') end
    end
  end, 200, NAME)
end

local loading = core.is_loading_screen_visible and core:is_loading_screen_visible()
stamp('timeline installed: new game ' .. tostring(new_game) .. ', loading screen ' .. (loading and ('visible ' .. tostring(loading)) or 'not visible')
  .. ', turn ' .. tostring(cm:turn_number()))
if want_skip then S.enable() end
return S.report()
