-- Modular crew experiments (docs/design/modular-crew.md). Prepended to the crew_*.lua scenarios by tools/crew_lua.py.
-- Reads the game's tables through memreader Plus and writes only the seat list of our own land unit, nothing else.
local mr = _G.memreader_plus
local LAND_UNIT = "mtb_dwf_cha_malakai_thunderbarge"
local DB_ROOT = '48 8B 0D ?? ?? ?? ?? 4C 8B C0 48 8B 91 ?? ?? ?? ?? 48 8B CB E8 ?? ?? ?? ?? 48 85 C0 74 ?? 48 8B 0D ?? ?? ?? ?? 48 89 81'
local TABLE_VT = '48 8D 41 28 48 89 02 48 8B 41 58 49 89 00 C3'
local SLOTS, SLOT_SIZE = 1812, 0x38
local C = {mr = mr, LAND_UNIT = LAND_UNIT}

local function db()
  local root, count = mr.find_pattern(DB_ROOT)
  if count ~= 1 then error("database pattern matched " .. tostring(count)) end
  local app = mr.add(mr.add(root, 7), mr.read_int32(root, 3, true))
  return mr.read_pointer(mr.read_pointer(app, 0), mr.read_int32(root, 13, true))
end

local cached = {}
function C.table(name)
  if cached[name] then return cached[name] end
  local d, vt = db(), mr.find_pattern(TABLE_VT)
  for i = 0, SLOTS - 1 do
    local t = mr.read_pointer(d, i * SLOT_SIZE)
    if not mr.is_null(t) and mr.read_chain(t, 0, 0) == vt then
      cached[mr.read_string(mr.read_pointer(t, 0x58), 0)] = t
    end
  end
  return cached[name] or error("no table " .. name)
end

function C.row(table_name, key)
  local t = C.table(table_name)
  local node = mr.map_find_key(mr.add(t, 0x28), key)
  if not node then error("no key " .. key .. " in " .. table_name) end
  local index = mr.read_uint32(node, 0x20)
  local size, data = mr.read_array(t, 0x08, true)
  return mr.read_pointer(data, index * 8), index
end

-- The seat list of the land unit: capacity, size, data pointer.
function C.seats(unit_key)
  local lu = C.row("land_units", unit_key or LAND_UNIT)
  local cap, size = mr.read_uint32(lu, 0x48), mr.read_uint32(lu, 0x4c)
  local data = mr.read_pointer(lu, 0x50)
  local out = {cap = cap, size = size, data = data, lu = lu, seats = {}}
  for i = 0, size - 1 do
    local p = mr.read_pointer(data, i * 0x18)
    out.seats[i + 1] = {i = i, key = mr.read_string(p, 8), ptr = p, ap = C.ap(data, i)}
  end
  return out
end

-- The attachment point of element i. The element holds a pointer to the name.
function C.ap(data, i)
  local a = mr.read_pointer(data, i * 0x18 + 8)
  if mr.is_null(a) then return nil end
  local ok, s = pcall(mr.read_string, a, 0)
  return ok and s or nil
end

-- seats_map: {ap_name = personality_key}. Fails before any write if the list does not look right.
function C.apply(seats_map)
  local s = C.seats()
  if s.size ~= 29 or s.cap ~= 29 then error("seat list is " .. s.size .. "/" .. s.cap .. ", not 29") end
  local done, wanted = {}, 0
  for _ in pairs(seats_map) do wanted = wanted + 1 end
  local known = 0
  for _, seat in ipairs(s.seats) do
    if seat.ap and seats_map[seat.ap] then known = known + 1 end
  end
  if known ~= wanted then error("only " .. known .. " of " .. wanted .. " seats found") end
  for _, seat in ipairs(s.seats) do
    if seat.ap and seats_map[seat.ap] then
      local p = C.row("battle_personalities", seats_map[seat.ap])
      if mr.read_string(p, 8) ~= seats_map[seat.ap] then error("row check failed for " .. seats_map[seat.ap]) end
      mr.write(s.data, seat.i * 0x18, p)
      done[#done + 1] = seat.ap .. "=" .. seats_map[seat.ap]
    end
  end
  return done
end

function C.list()
  local s = C.seats()
  local lines = {"size " .. s.size .. " cap " .. s.cap}
  for _, seat in ipairs(s.seats) do lines[#lines + 1] = seat.i .. " " .. tostring(seat.ap) .. " " .. seat.key end
  return table.concat(lines, "\n")
end

-- In a battle: script unit of the land unit and the game's unit behind it.
function C.lord_unit()
  local alliances = bm:alliances()
  for a = 1, alliances:count() do
    local armies = alliances:item(a):armies()
    for i = 1, armies:count() do
      local us = armies:item(i):units()
      for j = 1, us:count() do
        if us:item(j):type() == LAND_UNIT then return us:item(j) end
      end
    end
  end
end

function C.battle_unit(u)
  local lu = C.row("land_units", LAND_UNIT)
  local base = mr.ud_topointer(u)
  local function try(p, off)
    local ok, v = pcall(mr.read_pointer, p, off)
    if ok and not mr.is_null(v) then return v end
  end
  local function is_unit(p)
    return p and try(p, 0x50) == lu
  end
  if is_unit(base) then return base, "self" end
  for _, off in ipairs({8, 0x10, 0x18, 0x20, 0x28}) do
    local p = try(base, off)
    if is_unit(p) then return p, off end
    if p then
      for _, off2 in ipairs({0, 8, 0x10, 0x18}) do
        local q = try(p, off2)
        if is_unit(q) then return q, off * 256 + off2 end
      end
    end
  end
end

-- What each living man of the lord's unit really has: the live pointers man -> seat -> row -> stats -> weapon.
function C.men()
  local u = C.lord_unit()
  if not u then return "no lord" end
  local bu, how = C.battle_unit(u)
  if not bu then return "no battle unit, script object at " .. mr.tostring(mr.ud_topointer(u)) end
  local lines = {"script " .. u:number_of_men_alive() .. "/" .. u:initial_number_of_men() .. " via " .. tostring(how)}
  local pos = u:position()
  lines[#lines + 1] = string.format("unit at %.1f %.1f %.1f bearing %.0f", pos:get_x(), pos:get_y(), pos:get_z(), u:bearing())
  local function where(m)
    local ok, x, y, z = pcall(function() return mr.read_float(m, 0x88), mr.read_float(m, 0x8c), mr.read_float(m, 0x90) end)
    return ok and string.format("at %.1f %.1f %.1f", x, y, z) or "at ?"
  end
  for _, vec_off in ipairs({0x110, 0x180}) do
    local size = mr.read_uint32(bu, vec_off + 4)
    local data = mr.read_pointer(bu, vec_off + 8)
    lines[#lines + 1] = string.format("vector %x: %d", vec_off, size)
    for i = 0, size - 1 do
      local m = mr.read_pointer(data, i * 8)
      local ok, text = pcall(function()
        local e = mr.read_pointer(m, 0xb70)
        if mr.is_null(e) then return "no seat" end
        local p = mr.read_pointer(e, 0)
        local ap = mr.read_pointer(e, 8)
        local w, st = "-", mr.read_pointer(p, 0x38)
        if not mr.is_null(st) then
          local mw = mr.read_pointer(st, 0x20)
          w = mr.is_null(mw) and "no_missile" or tostring(select(2, pcall(mr.read_string, mw, 8)))
        end
        local va = mr.read_pointer(p, 0x28)
        return tostring(mr.is_null(ap) and "?" or mr.read_string(ap, 0)) .. " " .. mr.read_string(p, 8) .. " var=" .. (mr.is_null(va) and "-" or mr.read_string(va, 0x18)) .. " anim=" .. mr.read_string(p, 0x18) .. " w=" .. w
      end)
      lines[#lines + 1] = i .. " " .. (ok and text or "not a seated man") .. " " .. where(m)
    end
  end
  return table.concat(lines, "\n")
end

-- Vectors of the battle unit with about 29 entries whose entries have a seat pointer: where the riders are kept.
function C.vectors()
  local u = C.lord_unit()
  local bu = C.battle_unit(u)
  local out = {}
  for off = 0x60, 0x400, 8 do
    local ok, cap, size, data = pcall(function()
      return mr.read_uint32(bu, off), mr.read_uint32(bu, off + 4), mr.read_pointer(bu, off + 8)
    end)
    if ok and size >= 1 and size <= cap and cap <= 4096 and not mr.is_null(data) then
      local ok2, key = pcall(function()
        local m = mr.read_pointer(data, 0)
        local e = mr.read_pointer(m, 0xb70)
        return mr.read_string(mr.read_pointer(e, 0), 8)
      end)
      out[#out + 1] = string.format("%x size %d %s", off, size, ok2 and tostring(key) or "-")
    end
  end
  return table.concat(out, "\n")
end

local function vec(x, y, z)
  local v = battle_vector:new(); v:set_x(x); v:set_y(y); v:set_z(z); return v
end

-- Camera relative to the lord: f forward, r right, u up; t* the point looked at.
function C.camera(f, r, up, tf, tr, tu, fov)
  local u = C.lord_unit()
  local p = u:position()
  local b = u:bearing() * 3.14159265 / 180
  local function world(a, c, d)
    return p:get_x() + math.sin(b) * a + math.cos(b) * c, p:get_y() + d, p:get_z() + math.cos(b) * a - math.sin(b) * c
  end
  local cx, cy, cz = world(f, r, up)
  local tx, ty, tz = world(tf, tr, tu)
  bm:camera():move_to(vec(cx, cy, cz), vec(tx, ty, tz), 0, false, fov or 40)
  return bm:get_current_phase_name()
end

-- Seats' places relative to the unit (forward, right, up), read from men_*.txt of a battle with the barge still.
local SEAT_AT = {ap_captain = {-4.5, 0, 4.4}, ap_cannon_left = {6.9, -1.8, 1.4}, ap_cannon_right = {6.9, 1.8, 1.4}, ap_cupola_front = {4.2, 0, 24.9}, ap_cupola_rear = {-6.2, 0, 24.7}, bow = {8, 0, 4}, cup_mid = {-1, 0, 24.9}, centre = {0, 0, 4}}

-- Camera at dist metres from a seat. az: degrees from the barge's bow, negative = its left side; el: degrees above the seat.
function C.camera_seat(name, dist, az, el, fov)
  local s = SEAT_AT[name] or error("no seat " .. name)
  local u = C.lord_unit()
  local p = u:position()
  local bearing = u:bearing() * 3.14159265 / 180
  local x = p:get_x() + math.sin(bearing) * s[1] + math.cos(bearing) * s[2]
  local y = p:get_y() + s[3]
  local z = p:get_z() + math.cos(bearing) * s[1] - math.sin(bearing) * s[2]
  local b, e = bearing + az * 3.14159265 / 180, el * 3.14159265 / 180
  local cx, cy, cz = x + math.sin(b) * math.cos(e) * dist, y + math.sin(e) * dist, z + math.cos(b) * math.cos(e) * dist
  bm:camera():move_to(vec(cx, cy, cz), vec(x, y, z), 0, false, fov)
  return string.format("seat %.1f %.1f %.1f camera %.1f %.1f %.1f", x, y, z, cx, cy, cz)
end

-- The nearest living enemy unit. A far target ignores attack_unit (the stock AI does not answer either), so: move there, then attack.
function C.order()
  local uc, enemy_alliance = _G.mtb_crew_uc, _G.mtb_crew_enemy
  if not uc then return "no controller" end
  local u = C.lord_unit()
  local up = u:position()
  local best, best_d
  local armies = enemy_alliance:armies()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      local e = us:item(j)
      if e:number_of_men_alive() > 0 then
        local ep = e:position()
        local dx, dz = ep:get_x() - up:get_x(), ep:get_z() - up:get_z()
        local d = math.sqrt(dx * dx + dz * dz)
        if not best_d or d < best_d then best, best_d = e, d end
      end
    end
  end
  if not best then return "no enemy" end
  if best_d > 120 then
    uc:goto_location(best:position(), true)
    return "moving " .. math.floor(best_d)
  end
  uc:attack_unit(best, true, true)
  return "attacking " .. math.floor(best_d)
end

-- Ammo, kills, health of the lord's unit, from the script API and the unit panel's context.
function C.stats()
  local u = C.lord_unit()
  local function cco(k)
    local ok, v = pcall(function() return common.get_context_value("CcoBattleUnit", tostring(u:unique_ui_id()), k) end)
    return ok and tostring(v) or "err"
  end
  local near
  local alliances = bm:alliances()
  local ours
  for a = 1, alliances:count() do
    local armies = alliances:item(a):armies()
    for i = 1, armies:count() do
      local us = armies:item(i):units()
      for j = 1, us:count() do
        if us:item(j):type() == LAND_UNIT then ours = a end
      end
    end
  end
  local armies = alliances:item(3 - ours):armies()
  local up = u:position()
  for i = 1, armies:count() do
    local us = armies:item(i):units()
    for j = 1, us:count() do
      local ep = us:item(j):position()
      local dx, dz = ep:get_x() - up:get_x(), ep:get_z() - up:get_z()
      local d = math.sqrt(dx * dx + dz * dz)
      if not near or d < near then near = d end
    end
  end
  return "near=" .. tostring(near and math.floor(near)) .. " men=" .. u:number_of_men_alive() .. " pct=" .. cco("PrimaryAmmoPercent") .. " kills=" .. cco("NumKills") .. " hp=" .. cco("HealthValue") .. "/" .. cco("HealthMax") .. " ents=" .. cco("NumEntities")
end
_G.mtb_crew = C
