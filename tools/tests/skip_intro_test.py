"""tools/tests/skip_intro.lua against a stub of the game's intro (py -3.10, lupa, Lua 5.1). No game.

  py -3.10 tools/tests/skip_intro_test.py

The stub keeps the game's Esc stack as _lib/lib_campaign_manager.lua does (steal_key_with_callback 13429, on_key_press_up 13391:
the top entry's callback runs and is removed) and plays Malakai's intro in the game's order: the loading screen dismissed ->
the movie's entry (movie_overlay "intro_movie", 100 ms after its start) -> its skip starts the flyover cutscene
(Campaign_Cutscene_<faction>_intro, Esc + Space) -> its skip/release starts the post-intro scene -> its end callback fires
ScriptEventCampaignIntroComplete. The real-time callbacks run on a fake 100 ms clock. Prints a line a case; exit 1 on a failure.
"""
import sys
from pathlib import Path

from lupa import lua51

LUA = Path(__file__).resolve().parent / "skip_intro.lua"

STUB = r"""
log_lines = {}
mtb = {log = function(event, text) log_lines[#log_lines + 1] = event .. ': ' .. tostring(text) end}
local listeners = {}
core = {}
function core:add_listener(name, event, cond, cb, persistent) listeners[#listeners + 1] = {name = name, event = event, cond = cond, cb = cb} end
function core:trigger_event(event, s)
  local ctx = {string = s, faction = function() return {name = function() return 'wh3_dlc25_dwf_malakai' end} end}
  for _, l in ipairs(listeners) do
    if l.event == event and (l.cond == true or (type(l.cond) == 'function' and l.cond(ctx))) then l.cb(ctx) end
  end
end
function core:is_loading_screen_visible() return 'campaign', {} end
real = {}
local tm = {}
function tm:repeat_real_callback(cb, ms, name) real[name] = {cb = cb, ms = ms} end
function tm:real_callback(cb, ms, name) real[name or tostring(cb)] = {cb = cb, ms = ms, once = true} end
function tm:remove_real_callback(name) real[name] = nil end
function core:get_tm() return tm end
cm = {stolen_keys = {}, new_game = true}
function cm:is_new_game() return self.new_game end
function cm:get_local_faction_name() return 'wh3_dlc25_dwf_malakai' end
function cm:turn_number() return 1 end
function cm:steal_key_with_callback(name, key, cb)
  self.stolen_keys[key] = self.stolen_keys[key] or {}
  table.insert(self.stolen_keys[key], {name = name, callback = cb, is_persistent = false})
end
function cm:release_key_with_callback(name, key)
  local t = self.stolen_keys[key] or {}
  for i = 1, #t do if t[i].name == name then table.remove(t, i); break end end
end
function cm:on_key_press_up(key)
  pressed = (pressed or 0) + 1
  local t = self.stolen_keys[key]
  if type(t) == 'table' and #t > 0 then
    local e = t[#t]
    if not e.is_persistent then table.remove(t, #t) end
    e.callback()
  end
end
-- the intro, in the game's order
flow = {}
local function post_intro()
  flow[#flow + 1] = 'post_intro_scene started'
  cm:steal_key_with_callback('Campaign_Cutscene_post_intro_scene', 'SPACE', function() end)
  cm:steal_key_with_callback('Campaign_Cutscene_post_intro_scene', 'ESCAPE', function()
    cm:release_key_with_callback('Campaign_Cutscene_post_intro_scene', 'SPACE')
    flow[#flow + 1] = 'post_intro_scene skipped'
    core:trigger_event('ScriptEventIntroCutsceneFinished')
    core:trigger_event('ScriptEventCampaignIntroComplete')
  end)
end
local function flyover()
  flow[#flow + 1] = 'flyover started'
  local n = 'Campaign_Cutscene_wh3_dlc25_dwf_malakai_intro'
  cm:steal_key_with_callback(n, 'SPACE', function() end)
  cm:steal_key_with_callback(n, 'ESCAPE', function()
    cm:release_key_with_callback(n, 'SPACE')
    flow[#flow + 1] = 'flyover skipped'
    core:trigger_event('ScriptEventCampaignIntroCutsceneCompleted', n)
    tm:real_callback(post_intro, 100, 'release')           -- release() 0.1 s later, then the end callback
  end)
end
function play_intro()
  core:trigger_event('LoadingScreenDismissed')
  flow[#flow + 1] = 'movie started'
  tm:real_callback(function()
    cm:steal_key_with_callback('movie_overlay_skip_monitor_intro_movie', 'ESCAPE', function()
      flow[#flow + 1] = 'movie skipped'
      flyover()
    end)
  end, 100, 'movie_steal')
end
function tick(ms)          -- the fake real-time clock: ms in steps of 100
  for t = 100, ms, 100 do
    for name, r in pairs(real) do
      r.left = (r.left or r.ms) - 100
      if r.left <= 0 then
        if r.once then real[name] = nil else r.left = r.ms end
        r.cb()
      end
    end
  end
end
"""


def runtime():
    rt = lua51.LuaRuntime(unpack_returned_tuples=True)
    assert rt.eval("_VERSION") == "Lua 5.1"
    rt.execute(STUB)
    return rt


def send(rt, skip):
    """As tools/crew_cycle.py Session.script sends it: the value line, then the file; the result as the remote's dump would."""
    code = f'mtb_skip = "{skip}"\n' + LUA.read_text(encoding="utf-8")
    fn = rt.eval("function(s) local f, err = loadstring(s, 'skip_intro.lua'); if not f then error(err) end; return f() end")
    return str(fn(code))


def lua_list(rt, name):
    t = rt.globals()[name]
    return [t[i] for i in range(1, len(t) + 1)] if t else []


def main():
    failures = []

    def check(name, ok, detail):
        print(f"  [{'ok' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            failures.append(name)

    rt = lua51.LuaRuntime(unpack_returned_tuples=True)
    ok = rt.eval("function(s) return loadstring(s) ~= nil end")(LUA.read_text(encoding="utf-8"))
    check("Lua 5.1 syntax", ok, str(LUA.name))

    # 1. skip on, a new game: the three parts skipped in order, the intro complete, the watcher gone
    rt = runtime()
    first = send(rt, "1")
    rt.execute("play_intro()")
    rt.execute("tick(10000)")
    flow = lua_list(rt, "flow")
    report = send(rt, "1")
    want = ["movie started", "movie skipped", "flyover started", "flyover skipped", "post_intro_scene started", "post_intro_scene skipped"]
    check("skip on: movie, flyover, post-intro scene skipped in the game's order", flow == want, " -> ".join(flow))
    check("skip on: the report says done, the three kinds", "done=true" in report and "skipped=movie,flyover,post_intro_scene" in report and "state=complete" in report,
          f"first: {first} | after: {report}")
    check("skip on: the watcher removed after the intro's end", rt.eval("real.tww3_mtb_skip_intro == nil"), "real-time callback tww3_mtb_skip_intro")
    lines = lua_list(rt, "log_lines")
    check("skip on: timeline lines", any("loading screen dismissed" in l for l in lines) and any("intro complete" in l for l in lines)
          and sum("skip " in l for l in lines) == 3, f"{len(lines)} lines, e.g. {lines[:2]}")
    check("skip on: only intro entries pressed (3 presses)", rt.eval("pressed") == 3, f"presses {rt.eval('pressed')}")

    # 2. skip off: nothing pressed, the intro still waiting, the timeline only
    rt = runtime()
    report = send(rt, "0")
    rt.execute("play_intro()")
    rt.execute("tick(10000)")
    check("skip off: nothing pressed, the movie still on the Esc stack", rt.eval("pressed") is None and lua_list(rt, "flow") == ["movie started"]
          and rt.eval("cm.stolen_keys.ESCAPE[1].name") == "movie_overlay_skip_monitor_intro_movie", report)

    # 3. another holder of Esc on top (the panel's own stolen key): never pressed
    rt = runtime()
    send(rt, "1")
    rt.execute("play_intro(); tick(300); cm:steal_key_with_callback('tww3_mtb_ship_screen', 'ESCAPE', function() panel_closed = true end); tick(3000)")
    check("a non-intro entry on top is never pressed", rt.eval("panel_closed") is None and rt.eval("pressed") is None, f"flow {lua_list(rt, 'flow')}")

    # 4. not a new game (a save, the campaign after a battle): no watcher, done at once
    rt = runtime()
    rt.execute("cm.new_game = false")
    report = send(rt, "1")
    check("not a new game: nothing to skip, done", "done=true" in report and "skip=off" in report and rt.eval("real.tww3_mtb_skip_intro == nil"), report)

    # 5. sent twice (timeline from wait_mode, then the skip): one install, the skip enabled by the second
    rt = runtime()
    send(rt, "0")
    report = send(rt, "1")
    rt.execute("play_intro(); tick(10000)")
    check("installed by the timeline first, enabled by the second send", "skip=on" in report and len(lua_list(rt, "flow")) == 6, report)

    print("skip_intro.lua:", "ok" if not failures else f"FAILED {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
