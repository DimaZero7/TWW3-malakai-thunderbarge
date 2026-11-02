-- In a campaign battle: all units of the player's army, the lord in full.
local UNIT = "mtb_dwf_cha_malakai_thunderbarge"
local out = {phase = bm:get_current_phase_name(), units = {}}
local function cco(u, k)
  local ok, v = pcall(function() return common.get_context_value("CcoBattleUnit", tostring(u:unique_ui_id()), k) end)
  return ok and v or "err"
end
local function list(fn)
  local ok, l = pcall(fn)
  if ok and type(l) == "table" then
    local t = {}
    for _, k in ipairs(l) do t[#t+1] = tostring(k) end
    return table.concat(t, ",")
  end
  return "?"
end
local lord
local alliances = bm:alliances()
for a = 1, alliances:count() do
  local armies = alliances:item(a):armies()
  for i = 1, armies:count() do
    local army = armies:item(i)
    local us = army:units()
    for j = 1, us:count() do
      local u = us:item(j)
      out.units[#out.units+1] = a .. ":" .. u:type() .. (u:is_commanding_unit() and "*" or "")
      if u:type() == UNIT or u:type() == "wh3_dlc25_dwf_cha_malakai_makaisson" then lord, out.army = u, army end
    end
  end
end
if lord then
  local gen = bm:get_general(out.army)
  out.army = nil
  out.lord = {type=lord:type(), name=lord:name(), commanding=lord:is_commanding_unit(), general_is_lord=(gen and gen:type()==lord:type()),
    men=lord:number_of_men_alive(), men0=lord:initial_number_of_men(), class=lord:unit_class(),
    cco_is_general=cco(lord,"IsGeneral"), cco_is_character=cco(lord,"IsCharacter"), cco_rank=cco(lord,"CharacterRank"), cco_name=cco(lord,"Name"),
    category=cco(lord,"UnitRecordContext.CategoryName"), hp=cco(lord,"HealthValue"), hpmax=cco(lord,"HealthMax"),
    effects=cco(lord,"ActiveEffectList.Size"),
    active=list(function() return lord:owned_non_passive_special_abilities() end),
    passive=list(function() return lord:owned_passive_special_abilities() end)}
  local p = lord:position()
  out.lord.pos = {p:get_x(), p:get_y(), p:get_z()}
  out.lord.bearing = lord:bearing()
end
out.army = nil
local text = mtb.dump(out)
mtb.log("battle_read", text)
return text
