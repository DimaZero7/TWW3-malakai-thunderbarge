-- Where do the seat vectors really live? Prints the land unit's row as seen through the table and through main_units.
local mr = C.mr
local out = {}
local function hex(p) return mr.tostring(p) end
local function dump_ints(p, from, to)
  local t = {}
  for off = from, to, 8 do
    t[#t + 1] = string.format("%x:%s/%s", off, mr.tostring(mr.read_uint32(p, off, true)), mr.tostring(mr.read_uint32(p, off + 4, true)))
  end
  return table.concat(t, " ")
end
local function row_info(tname, key)
  local t = C.table(tname)
  local node = mr.map_find_key(mr.add(t, 0x28), key)
  if not node then return tname .. " " .. key .. ": no key" end
  local idx = mr.read_uint32(node, 0x20)
  local size, data = mr.read_array(t, 0x08)
  local p = mr.read_pointer(data, idx * 8)
  return tname .. " " .. key .. " table " .. hex(t) .. " size " .. tostring(size) .. " idx " .. tostring(idx) .. " row " .. hex(p), p
end
for _, key in ipairs({"mtb_dwf_cha_malakai_thunderbarge", "wh3_dlc25_dwf_veh_thunderbarge_grungni", "wh2_main_skv_veh_doomwheel"}) do
  local text, p = row_info("land_units", key)
  out[#out + 1] = text
  if p then
    out[#out + 1] = "  " .. dump_ints(p, 0x0, 0xb0)
    for _, off in ipairs({0x8, 0x18, 0xf8, 0x128}) do
      local ok, s = pcall(mr.read_string, p, off)
      out[#out + 1] = string.format("  str %x: %s", off, tostring(ok and s or "?"))
    end
  end
  local text2, m = row_info("main_units", key)
  out[#out + 1] = text2
  if m then
    local lu = mr.read_pointer(m, 0x500)
    out[#out + 1] = "  main_unit+0x500 -> " .. hex(lu) .. " key3e0 " .. tostring(mr.read_string(m, 0x3e0))
    if not mr.is_null(lu) then out[#out + 1] = "  " .. dump_ints(lu, 0x0, 0xb0) end
  end
end
-- How the junction table looks: the first row of ours.
local t = C.table("land_units_to_battle_personalities_junctions")
local size, data = mr.read_array(t, 0x08)
out[#out + 1] = "junctions " .. tostring(size)
local lu0 = C.row("land_units", C.LAND_UNIT)
local found = 0
for i = 0, size - 1 do
  local r = mr.read_pointer(data, i * 8)
  if mr.read_pointer(r, 0x18) == lu0 then
    found = found + 1
    if found <= 3 then out[#out + 1] = "  row " .. i .. " " .. dump_ints(r, 0, 0x30) .. " pers " .. mr.read_string(mr.read_pointer(r, 0x10), 8) end
  end
end
out[#out + 1] = "junction rows pointing at our row: " .. found
return table.concat(out, "\n")
