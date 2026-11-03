-- Separate ammo experiment (docs/design/separate-ammo.md). crew_lib is already loaded, C is the crew library.
-- Counts the shots of each crew group from the game's projectile list and changes the two ammo pools and the pool byte of a
-- group's weapon row. Everything here lives in memory until the game closes: nothing is saved, stock rows are put back by A.restore().
local mr = C.mr
local A = {}
_G.mtb_ammo = A

-- Battle unit: pool = {current, max, start, infinite flag}, primary then secondary. Weapon row: +0x30 use_secondary_ammo_pool.
local PRI, SEC, POOL_BYTE = 0x3d90, 0x3da0, 0x30
-- string.find in the game searches for plain text only: patterns do not work.
local function starts(text, prefix) return text:sub(1, #prefix) == prefix end
local function GROUP_OF(ap)
  if not ap then return nil end
  if starts(ap, "ap_cannon_") then return "cannons" end
  if starts(ap, "ap_cupola_") then return "cupolas" end
  if starts(ap, "ap_bomb_bay_") then return "bombs" end
  if starts(ap, "ap_crew_left") or starts(ap, "ap_crew_right") then return "rifles" end
end
local GROUPS = {"rifles", "cannons", "cupolas", "bombs"}

local function now() return bm:time_elapsed_ms() / 1000 end

local function pool(off)
  local b = A.bu
  return mr.read_int32(b, off), mr.read_int32(b, off + 4), mr.read_int32(b, off + 8), mr.read_int32(b, off + 12)
end
local function set_pool(off, cur, inf, max)
  mr.write(A.bu, off, mr.uint32(cur))
  if max then
    mr.write(A.bu, off + 4, mr.uint32(max))
    mr.write(A.bu, off + 8, mr.uint32(max))
  end
  if inf ~= nil then mr.write(A.bu, off + 12, mr.uint32(inf)) end
end
A.set_pool = set_pool

local function set_dry(group, value)
  local rows = A.weapons[group]
  if not rows then error("no weapon for " .. group) end
  for _, w in ipairs(rows) do mr.write(w.ptr, POOL_BYTE, value) end
end

-- Finds the men, their groups, weapon rows and first projectile rows. Stops before any write if something looks wrong.
function A.attach()
  A.unit = C.lord_unit()
  if not A.unit then error("no lord") end
  A.bu = C.battle_unit(A.unit)
  if not A.bu then error("no battle unit") end
  local lines = {}
  local battle = mr.read_pointer(A.bu, 0x30)
  local world = mr.read_pointer(battle, 0x440)
  if mr.tostring(mr.read_pointer(world, 8)) ~= mr.tostring(battle) then error("world does not point back at the battle") end
  A.mgr = mr.read_pointer(world, 0x1c8)
  A.by_shooter, A.by_record, A.weapons, A.men = {}, {}, {}, {}
  local size = mr.read_uint32(A.bu, 0x110 + 4)
  local data = mr.read_pointer(A.bu, 0x110 + 8)
  if size ~= 29 then error("riders " .. tostring(size)) end
  for i = 0, size - 1 do
    local m = mr.read_pointer(data, i * 8)
    local e = mr.read_pointer(m, 0xb70)
    if mr.is_null(e) then error("rider " .. i .. " has no seat") end
    local ap = mr.read_pointer(e, 8)
    local name = not mr.is_null(ap) and mr.read_string(ap, 0) or nil
    local g = GROUP_OF(name)
    local st = mr.read_pointer(mr.read_pointer(e, 0), 0x38)
    if g and not mr.is_null(st) then
      local w = mr.read_pointer(st, 0x20)
      if not mr.is_null(w) then
        local key = mr.read_string(w, 8)
        A.by_shooter[mr.tostring(m)] = g
        A.weapons[g] = A.weapons[g] or {}
        local known = false
        for _, w0 in ipairs(A.weapons[g]) do known = known or w0.key == key end
        if not known then
          local stock = mr.read_uint8(w, POOL_BYTE) ~= 0
          table.insert(A.weapons[g], {ptr = w, key = key, stock = stock})
          local proj = mr.read_pointer(mr.read_pointer(w, 0x28), 0)
          A.by_record[mr.tostring(proj)] = g
          local ok, pname = pcall(mr.read_string, proj, 8)
          lines[#lines + 1] = string.format("%s weapon %s pool byte %s projectile %s flag_bf0 %d", g, key, tostring(stock), tostring(ok and pname or "?"), mr.read_uint8(m, 0xbf0))
        end
      end
    end
    A.men[#A.men + 1] = m
  end
  for _, g in ipairs(GROUPS) do
    if not A.weapons[g] then error("group without a weapon: " .. g) end
  end
  if A.weapons.rifles[1].stock ~= true or A.weapons.cannons[1].stock ~= false then error("pool bytes are not what the table says: wrong offset") end
  local cur, max, start, inf = pool(PRI)
  if cur ~= A.unit:ammo_left() then error("primary pool " .. cur .. " is not ammo_left " .. A.unit:ammo_left()) end
  lines[#lines + 1] = string.format("pools primary %d/%d/%d inf %d secondary %d/%d/%d inf %d", cur, max, start, inf, pool(SEC))
  local mainmen = mr.read_uint32(A.bu, 0x180 + 4)
  local hull = mr.read_pointer(mr.read_pointer(A.bu, 0x180 + 8), 0)
  lines[#lines + 1] = string.format("hull men %d flag_bf0 %d unit bits %d", mainmen, mr.read_uint8(hull, 0xbf0), mr.read_uint8(A.bu, 0x3d1c))
  A.live, A.phases, A.polls, A.clock_sum, A.clock_max, A.listed_max, A.errors, A.others = {}, {}, 0, 0, 0, 0, {}, {}
  A.by_how = {shooter = 0, record = 0}
  return table.concat(lines, "\n")
end

local function count(group, how)
  local p = A.phases[#A.phases]
  if not p then return end
  A.by_how[how] = A.by_how[how] + 1
  p.shots[group] = p.shots[group] + 1
  if now() - p.t0 >= A.grace then p.late[group] = p.late[group] + 1 end
end

local LYING = {[5] = true, [6] = true}
local DONE = 7
function A.poll()
  local started = os.clock()
  A.polls = A.polls + 1
  local list = mr.read_vector(A.mgr, 0x10, {0, "pointer"}, 8) or {}
  if #list > A.listed_max then A.listed_max = #list end
  local c = A.polls
  for i = 1, #list do
    local p = list[i]
    if p then
      local key = mr.tostring(p)
      local st, t = mr.read_int32(p, 0xc0), mr.read_float(p, 0x11c)
      local rec = A.live[key]
      if rec and ((rec.st == DONE and st ~= DONE) or (st ~= DONE and not LYING[st] and t + 1e-3 < rec.t)) then
        rec = nil          -- the slot was reused for a new projectile
      end
      if not rec then
        rec = {st = st, t = t, c = c}
        A.live[key] = rec
        if st == 0 then
          local sp, rp = mr.read_pointer(p, 0x20), mr.read_pointer(p, 0x90)
          local g = not mr.is_null(sp) and A.by_shooter[mr.tostring(sp)]
          if g then
            count(g, "shooter")
          else
            g = not mr.is_null(rp) and A.by_record[mr.tostring(rp)]
            if g then count(g, "record") end
          end
        end
      else
        rec.st, rec.t, rec.c = st, t, c
      end
    end
  end
  for key, rec in pairs(A.live) do
    if c - rec.c >= 3 then A.live[key] = nil end
  end
  local spent = os.clock() - started
  A.clock_sum = A.clock_sum + spent
  if spent > A.clock_max then A.clock_max = spent end
end

function A.start(poll_ms, grace)
  A.grace = grace or 6
  core.tm:repeat_real_callback(function()
    local ok, err = pcall(A.poll)
    if not ok and #A.errors < 20 then A.errors[#A.errors + 1] = tostring(err) end
  end, poll_ms or 100, "tww3_mtb_ammo")
  return "polling"
end

local function close_phase()
  local p = A.phases[#A.phases]
  if p and not p.t1 then
    p.t1 = now()
    p.pri1, p.pri_max, p.pri_start, p.pri_inf = pool(PRI)
    p.sec1, p.sec_max, p.sec_start, p.sec_inf = pool(SEC)
    p.bits1 = mr.read_uint8(A.bu, 0x3d1c)
  end
end

-- What each step of the experiment changes in the unit and in the weapon rows.
local STEPS = {
  base = function() set_pool(PRI, 5000, nil, 5000) end,
  rifles_low = function() set_pool(SEC, 6, 0) end,
  guns_dry = function() set_pool(SEC, 0, 0); set_dry("cannons", true) end,
  resume = function() set_dry("cannons", false); set_dry("rifles", false) end,
  bombs_dry = function() set_dry("bombs", true) end,
  cupolas_dry = function() set_dry("bombs", false); set_dry("cupolas", true) end,
  primary_low = function()
    set_dry("cupolas", false); set_dry("rifles", true)
    set_pool(SEC, 50, 1); set_pool(PRI, 5)
  end,
  refilled = function() set_pool(PRI, 5000) end,
}

function A.phase(name)
  close_phase()
  local step = STEPS[name]
  if not step then error("no step " .. name) end
  step()
  local p = {name = name, t0 = now(), shots = {}, late = {}, pri0 = (pool(PRI)), sec0 = (pool(SEC)), bits0 = mr.read_uint8(A.bu, 0x3d1c)}
  for _, g in ipairs(GROUPS) do p.shots[g], p.late[g] = 0, 0 end
  A.phases[#A.phases + 1] = p
  return name
end

function A.ui()
  local u = A.unit
  local function cco(k)
    local ok, v = pcall(function() return common.get_context_value("CcoBattleUnit", tostring(u:unique_ui_id()), k) end)
    return ok and tostring(v) or "err"
  end
  return string.format("ammo_left %s starting %s pct %s sec_pct %s inf_pri %s inf_sec %s", tostring(u:ammo_left()), tostring(u:starting_ammo()),
    cco("PrimaryAmmoPercent"), cco("SecondaryAmmoPercent"), cco("HasInfinitePrimaryAmmo"), cco("HasInfiniteSecondaryAmmo"))
end

function A.report()
  close_phase()
  local out = {}
  for _, p in ipairs(A.phases) do
    local s = {}
    for _, g in ipairs(GROUPS) do s[#s + 1] = string.format("%s %d (%d)", g, p.shots[g], p.late[g]) end
    out[#out + 1] = string.format("%-12s %5.1f s | %s | primary %d -> %d inf %d | secondary %d -> %d inf %d | bits %d -> %d",
      p.name, (p.t1 or now()) - p.t0, table.concat(s, ", "), p.pri0, p.pri1 or -1, p.pri_inf or -1, p.sec0, p.sec1 or -1, p.sec_inf or -1, p.bits0, p.bits1 or -1)
  end
  out[#out + 1] = string.format("polls %d, average %.2f ms, max %.1f ms, list up to %d; by shooter %d, by record %d; errors %d", A.polls,
    A.polls > 0 and A.clock_sum / A.polls * 1000 or 0, A.clock_max * 1000, A.listed_max, A.by_how.shooter, A.by_how.record, #A.errors)
  for _, e in ipairs(A.errors) do out[#out + 1] = "error: " .. e end
  return table.concat(out, "\n")
end

-- Stock rows go back; the session closes the game right after this anyway.
function A.restore()
  core.tm:remove_real_callback("tww3_mtb_ammo")
  for _, rows in pairs(A.weapons or {}) do
    for _, w in ipairs(rows) do mr.write(w.ptr, POOL_BYTE, w.stock) end
  end
  return "restored"
end

-- Enemy that cannot be finished: the fight must last through all the steps. The lord is already invincible (crew_fight.lua).
function A.keep_enemy()
  local done, failed = 0, 0
  local armies = _G.mtb_crew_enemy:armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      local su = script_unit:new(us:item(j))
      local ok = pcall(function() su:set_invincible(true); su.uc:morale_behavior_fearless() end)
      if ok then done = done + 1 else failed = failed + 1 end
    end
  end
  return "enemy units kept " .. done .. ", failed " .. failed
end

return "ammo probe loaded"
