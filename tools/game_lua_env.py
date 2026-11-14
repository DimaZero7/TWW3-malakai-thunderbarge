"""The game's Lua, as far as it is known, for every offline runner (py -3.10, lupa.lua51): ONE description, used by tools/lua_vectors.py,
tools/tests/port_probe.py (its fake game) and tools/ui_layout_check.py.

What it is built on: the census of the game's Lua (build/port_probe/lua_env_census.txt, item "census" of a real probe run) and the game's
own script library (_lib/lib_lua_extensions.lua documents find/sub/len as the game's UTF-8 versions, the originals as *_lua).

    rt, info = new_runtime()            # desktop Lua 5.1 altered like the game (below); info: what was removed and why
    load_mod(rt, src, name)             # a chunk in its own environment (the game runs mod chunks in the mod environment, not _G); returns what
                                        # the chunk returns; a global the chunk sets is an error (the modules are pure)
    F = Float32(rt, sources)            # the float32 checker (below); F.report() -> text, F.failures() -> [lines]
    lint(source) -> [(line, what)]      # the constructs the modules must not use (no runtime can show them all)
    f32(x) -> float | None              # x rounded to float32 (None: out of range); is_f32(x) -> bool

What the runtime emulates:
  * string.find / string.sub / string.len replaced by UTF-8 versions: sub and len count characters, find takes 3 arguments, matches plainly (no
    patterns) and RAISES on a 4th argument (in run 20261114-210531 a 4-argument call preceded broken game bindings for the session); the
    originals stay as string.find_lua / string.sub_lua / string.len_lua. string.gsub / match / gmatch / byte / format are the originals, as in
    the game. A method call s:sub(...) goes to the same replaced function (the string metatable indexes the string table).
  * the standard library trimmed: math.huge (nil in the game: run 20261114-204941) and every standard global or library member the census
    reports nil (rawlen, bit32, utf8, math.maxinteger, table.pack, table.unpack...).
  * mod chunks in their own environment (getfenv(0) ~= _G in the game).
What it cannot emulate:
  * 32-bit float numbers: desktop Lua computes in doubles. The Float32 checker makes the difference visible instead (see its docstring); a
    value it does not see (a temporary inside an expression, a comparison of two temporaries) is not checked.
  * the game's printf (string.format) quirks beyond the census lines (%d of 3e9 gives -2147483648 in both), its locale (strcoll in string
    comparison and table.sort without a comparator), its garbage collector, and the binding damage the 4th find argument caused (the fake
    stops at the call itself).
"""
import re
import struct
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CENSUS = REPO / "build" / "port_probe" / "lua_env_census.txt"

# What the game's Lua is KNOWN to lack (run 20261114-204941: `-math.huge` raised "arithmetic on field 'huge' (a nil value)").
# The runtime removes these, and also every global / standard member that the newest real census (build/port_probe/lua_env_census.txt,
# written by item "census" of a real run) reported as nil. Never add here what was not seen missing in the game.
GAME_LACKS = ["math.huge"]

# Standard Lua names the census may report missing. Game API names (core, cm, UIComponent...) are never removed on a census:
# the census of run 20261114-210531 read them through _G, where the game does not keep them (the chunk's environment does).
STANDARD_GLOBALS = {"assert", "collectgarbage", "dofile", "error", "gcinfo", "getfenv", "getmetatable", "ipairs", "load", "loadfile", "loadstring",
                    "module", "newproxy", "next", "pairs", "pcall", "print", "rawequal", "rawget", "rawset", "require", "select", "setfenv",
                    "setmetatable", "tonumber", "tostring", "type", "unpack", "xpcall", "io", "os", "debug", "coroutine", "package"}


def parse_census(text):
    """{"G": {name: type}, "M": {...}, "K": {...}, "B": {name: value}} from the census lines (kind TAB name TAB value)."""
    out = {"G": {}, "M": {}, "K": {}, "B": {}}
    for line in str(text).splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[0] in out:
            out[parts[0]][parts[1]] = parts[2]
    return out


def game_lacks(census_path=CENSUS):
    """[(name, why)]: the names the runtime removes from desktop Lua 5.1."""
    out = [(n, "known: run 20261114-204941") for n in GAME_LACKS]
    path = Path(census_path)
    if path.exists():
        c = parse_census(path.read_text(encoding="utf-8"))
        for name, t in c["G"].items():
            if t == "nil" and name in STANDARD_GLOBALS and name not in GAME_LACKS:
                out.append((name, f"census {path.name}"))
        for name, t in c["M"].items():
            if t == "nil" and name not in GAME_LACKS and name.split(".", 1)[1] not in ("find_lua", "sub_lua", "len_lua"):
                out.append((name, f"census {path.name}"))
    return out


# The game's own string functions (data_script.pack _lib/lib_lua_extensions.lua; census K lines of run 20261114-210531): find, sub and len
# are UTF-8 versions, find without patterns and without the 4th argument; the originals are kept as find_lua, sub_lua, len_lua.
# The fake refuses a 4th argument to string.find: the game cannot be made to show the binding damage that followed such a call in
# run 20261114-210531, so the fake stops at the call itself.
GAME_STRINGS = r"""
local find, sub, len, byte = string.find, string.sub, string.len, string.byte
string.find_lua, string.sub_lua, string.len_lua = find, sub, len
local function starts(s)       -- byte index of every UTF-8 character
  local out, i, n = {}, 1, len(s)
  while i <= n do
    out[#out + 1] = i
    local b = byte(s, i)
    i = i + ((b >= 240 and 4) or (b >= 224 and 3) or (b >= 192 and 2) or 1)
  end
  return out, n
end
local function char_index(k, count)
  if k < 0 then k = count + k + 1 end
  return k
end
string.len = function(s) local st = starts(s); return #st end
string.sub = function(s, i, j)
  local st, n = starts(s)
  local count = #st
  i = char_index(i or 1, count); j = char_index(j or count, count)
  if i < 1 then i = 1 end
  if j > count then j = count end
  if i > j then return '' end
  local last = (st[j + 1] or (n + 1)) - 1
  return sub(s, st[i], last)
end
string.find = function(s, needle, init, extra)
  if extra ~= nil then
    error("the game's string.find (UTF-8) takes 3 arguments and no patterns; a 4th argument preceded broken game bindings in run 20261114-210531: use string.find_lua", 2)
  end
  local st = starts(s)
  local from = st[char_index(init or 1, #st)] or (len(s) + 1)
  local a, b = find(s, needle, from, true)
  if not a then return nil end
  local ca, cb
  for k, pos in ipairs(st) do
    if pos == a then ca = k end
    if pos <= b then cb = k end
  end
  return ca, cb
end
"""


REDUCE = r"""
return function(names)
  local ipairs, match, type, concat, G = ipairs, string.match, type, table.concat, _G
  local done = {}
  for _, name in ipairs(names) do
    local lib, member = match(name, '^([%w_]+)%.([%w_]+)$')
    if lib then
      if type(G[lib]) == 'table' then G[lib][member] = nil; done[#done + 1] = name end
    elseif name ~= '_G' then
      G[name] = nil; done[#done + 1] = name
    end
  end
  return concat(done, ' ')
end
"""

# A chunk in its own environment: reads fall through to _G, writes are refused (the game would keep them in the mod environment; the
# modules here set nothing global, so a write is a bug).
LOAD_MOD = r"""
return function(src, name)
  local f, e = loadstring(src, '@' .. name)
  if not f then error(e, 0) end
  local env = setmetatable({}, {__index = _G, __newindex = function(_, k) error(name .. ' sets a global: ' .. tostring(k), 2) end})
  setfenv(f, env)
  return f()
end
"""


def apply(rt, census_path=CENSUS):
    """Alter a lupa.lua51 runtime like the game: the game's string functions, then the library reduced. Returns (removed, lacks)."""
    rt.execute(GAME_STRINGS)
    lacks = game_lacks(census_path)
    removed = rt.execute(REDUCE)(rt.table_from([n for n, _ in lacks]))
    return removed, lacks


def new_runtime(census_path=CENSUS):
    """(rt, info): a fresh lupa.lua51 runtime altered like the game. info: {"removed": str, "lacks": [(name, why)]}."""
    from lupa import lua51
    rt = lua51.LuaRuntime(unpack_returned_tuples=True)
    if rt.eval("_VERSION") != "Lua 5.1":
        raise RuntimeError("not Lua 5.1: " + str(rt.eval("_VERSION")))
    removed, lacks = apply(rt, census_path)
    return rt, {"removed": removed, "lacks": lacks}


def load_mod(rt, src, name):
    return rt.execute(LOAD_MOD)(src, name)


# ---------------------------------------------------------------- numbers ----------------------------------------------------------------

F32_WHOLE = 16777216        # 2^24: the last whole number a float32 holds with every whole number below it


def f32(x):
    """x rounded to the nearest float32, or None when it does not fit."""
    try:
        return struct.unpack("<f", struct.pack("<f", float(x)))[0]
    except OverflowError:
        return None


def is_f32(x):
    """x is exactly a float32 and, when whole, not above 2^24 (a counter there no longer steps by 1)."""
    x = float(x)
    if x != x or x in (float("inf"), float("-inf")):
        return False
    if x == int(x) and abs(x) > F32_WHOLE:
        return False
    return f32(x) == x


F32_LUA = r"""
return function(sources, edges)
  local frexp, ldexp, floor, getinfo, getlocal, sethook, type = math.frexp, math.ldexp, math.floor, debug.getinfo, debug.getlocal, debug.sethook, type
  local LIMIT, inf = 16777216, 1 / 0
  local watch = {}
  for _, s in ipairs(sources) do watch['@' .. s] = true end
  -- edges['chunk.lua|line the function starts on|local']: a local rounded half up there (floor(x + 0.5)); float32 must not be able to move it across the .5 edge
  local edge = {}
  for _, k in ipairs(edges or {}) do edge[k] = true end
  local sites, order = {}, {}
  local function exact(v)
    if v == 0 then return true end
    local m, e = frexp(v)
    if e > 128 then return false end
    local bits = 24
    if e < -125 then bits = 24 + e + 125; if bits < 1 then return false end end
    local s = ldexp(m, bits)
    return s == floor(s)
  end
  local function note(kind, where, name, v)
    local key = kind .. '\t' .. where .. '\t' .. name
    local s = sites[key]
    if not s then s = {kind = kind, where = where, name = name, n = 0, first = v}; sites[key] = s; order[#order + 1] = key end
    s.n = s.n + 1
  end
  local function check(v, where, name)
    if v ~= v or v == inf or v == -inf then note('inf/nan', where, name, v)
    elseif v == floor(v) then
      if v > LIMIT or v < -LIMIT then note('big', where, name, v) end
    elseif not exact(v) then note('inexact', where, name, v) end
  end
  -- a value rounded half up whose distance to the .5 edge is within 16 float32 steps (2^-19 of it): the game's float may round it the other way
  local function near_edge(v)
    if exact(v) then return false end
    local y = v + 0.5
    local f = y - floor(y)
    local d = f < 0.5 and f or 1 - f
    return d <= (v < 0 and -v or v) * 2 ^ -19
  end
  local function hook()
    local info = getinfo(2, 'S')
    if not info or not watch[info.source] then return end
    info = getinfo(2, 'Sln')
    local where = info.short_src .. ':' .. info.currentline .. ' ' .. tostring(info.name)
    local fname = info.short_src .. '|' .. info.linedefined .. '|'      -- by the line the function starts on: a tail call has no name
    local caller = nil
    local i = 1
    while true do
      local name, v = getlocal(2, i)
      if not name then break end
      if type(v) == 'number' then
        check(v, where, name)
        if edge[fname .. name] and v == v and near_edge(v) then
          caller = caller or getinfo(3, 'Sln')
          note('edge', where .. ' from ' .. (caller and (caller.short_src .. ':' .. caller.currentline .. ' ' .. tostring(caller.name)) or '?'), name, v)
        end
      end
      i = i + 1
    end
  end
  local C = {}
  function C.start() sethook(hook, 'r') end
  function C.stop() sethook() end
  function C.check(v, where, name) check(v, where, name or '') end
  function C.sites()
    local out = {}
    for i, k in ipairs(order) do local s = sites[k]; out[i] = s.kind .. '\t' .. s.where .. '\t' .. s.name .. '\t' .. s.n .. '\t' .. string.format('%.17g', s.first) end
    return table.concat(out, '\n')
  end
  return C
end
"""


class Float32:
    """The 32-bit float check. The game's Lua numbers are floats: whole numbers are exact only up to 2^24 and a fraction keeps 24 bits; desktop
    Lua has doubles. If every number a computation produces is exactly a float32 (and whole ones stay within 2^24), the float and the double
    computation give the same results step for step. So the check looks at the numbers:
      * every local of every function of the watched chunks when that function returns (a debug return hook: parameters, locals, loop
        variables, at the line of the return); Python adds the numbers the runner observes (check()).
      * kinds: 'big' (a whole number beyond 2^24), 'inexact' (a fraction that needs more than 24 bits: float32 rounds it), 'inf/nan',
        'edge' (edges: 'chunk.lua|first line of the function|local' of a value rounded half up, floor(x + 0.5): x is inexact and within 16 float32 steps of the
        .5 edge, so the game's float can round it the other way than the double did; e.g. 50 * 1.15 = 57.4999... rounds to 57, a float to 58).
    It cannot see a temporary that is never stored in a local (a * b / c inside one expression, the operands of a comparison), nor a local that
    is overwritten before its function returns; and an 'inexact' site only says that float32 rounds there, not whether the result differs: that
    is decided by the allowance the runner gives each such site (why the rounding cannot change what the player sees) and by the
    nudged-input passes of tools/lua_vectors.py (--nudge)."""

    def __init__(self, rt, sources, edges=()):
        self.c = rt.execute(F32_LUA)(rt.table_from(list(sources)), rt.table_from(list(edges)))

    def start(self):
        self.c.start()

    def stop(self):
        self.c.stop()

    def check(self, v, where, name=""):
        self.c.check(float(v), where, name)

    def sites(self):
        """[(kind, where, name, count, first value)]"""
        out = []
        for line in (self.c.sites() or "").split("\n"):
            if line:
                k, w, n, c, v = line.split("\t")
                out.append((k, w, n, int(c), float(v)))
        return out


# ---------------------------------------------------------------- lint ----------------------------------------------------------------

LINT_RULES = [
    (re.compile(r"\bstring\.(find|sub|len)\s*\("), "string.{0}: the game's is the UTF-8 one (take string.{0}_lua or string.{0} once at the top)"),
    (re.compile(r":(find|sub|len)\s*\("), "s:{0}(): the game's UTF-8 string.{0}"),
    (re.compile(r"\bmath\.huge\b"), "math.huge: nil in the game"),
    (re.compile(r"\bstring\.char\b"), "string.char: no vanilla script uses it"),
    (re.compile(r"\bstring\.dump\b|\bcollectgarbage\b|\bgcinfo\b"), "not used by vanilla scripts"),
    (re.compile(r"%[-+ #0]*\d*(?:\.\d+)?[gGeE]"), "a %g/%e format: no vanilla script uses it"),
    (re.compile(r"\b(?:bit32|utf8|rawlen|table\.pack|table\.unpack|math\.maxinteger|math\.mininteger)\b"), "nil in the game (census)"),
]


def _code_only(source):
    """The source with comments blanked (strings kept), line for line."""
    out, i, n = [], 0, len(source)
    quote = None
    while i < n:
        c = source[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(source[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'":
            quote = c
        elif source.startswith("--", i):
            m = re.match(r"--\[(=*)\[", source[i:i + 64])
            if m:
                close = "]" + m.group(1) + "]"
                end = source.find(close, i)
                end = n if end < 0 else end + len(close)
            else:
                end = source.find("\n", i)
                end = n if end < 0 else end
            out.append("".join(ch if ch == "\n" else " " for ch in source[i:end]))
            i = end
            continue
        out.append(c)
        i += 1
    return "".join(out)


def lint(source):
    """[(line number, what)] for the constructs the logic modules must not use in the game."""
    found = []
    for no, line in enumerate(_code_only(source).split("\n"), 1):
        for rx, what in LINT_RULES:
            for m in rx.finditer(line):
                found.append((no, what.format(*m.groups()) if m.groups() else what))
    return found
