-- Helpers of the progression test (tools/crew_cycle.py, prog_* steps). Sets _G.mtb_prog; each call of a step loads it again.
local P = {}
_G.mtb_prog = P
local PREFIX = 'wh3_dlc25_dwarf_spirit_of_grungni_'
local ANC = 'mtb_anc_mount_dwf_malakai_thunderbarge'

function P.malakai()
  local fl = cm:model():world():faction_list()
  for i = 0, fl:num_items() - 1 do
    local cl = fl:item_at(i):character_list()
    for j = 0, cl:num_items() - 1 do
      if cl:item_at(j):character_subtype_key() == 'wh3_dlc25_dwf_malakai_makaisson' then return cl:item_at(j) end
    end
  end
end

function P.cqi() return tostring(P.malakai():command_queue_index()) end

function P.ctx(expr)
  local ok, v = pcall(common.get_context_value, 'CcoCampaignCharacter', P.cqi(), expr)
  if ok then return v end
  return 'ERR ' .. tostring(v)
end

function P.slots()
  local keys = tww3_mtb_campaign.slots(P.malakai()) or {}
  for i, k in ipairs(keys) do keys[i] = string.gsub(k, PREFIX, '') end
  return table.concat(keys, ',')
end

-- One line that says where the campaign stands.
function P.state()
  local c = P.malakai()
  local f = c:faction()
  local first = c:has_military_force() and c:military_force():unit_list():item_at(0):unit_key() or '-'
  return mtb.dump({
    turn = cm:turn_number(), faction = f:name(), human = f:is_human(), unit = first,
    item_on = c:has_ancillary(ANC), given = cm:get_saved_value('mtb_barge_given'), slots = P.slots(),
    dev = P.ctx('MilitaryForceContext.HordeContext.DevelopmentPoints'),
    growth = P.ctx('MilitaryForceContext.HordeContext.GrowthPoints'),
    gold = f:treasury(), profile = tww3_mtb_crew.profile(), crew = tww3_mtb_crew.get(), built = string.gsub(tww3_mtb_crew.built(), PREFIX, ''),
    crew_status = tww3_mtb_crew.status,
    ammo_status = tostring(_G.tww3_mtb_ammo and tww3_mtb_ammo.status),
  })
end

function P.select_malakai()
  CampaignUI.ClearSelection()
  common.call_context_command('CcoCampaignCharacter', P.cqi(), 'SelectAndZoom(false)')
  return 'selected'
end

-- Peace with everyone at war: the test decides when a battle happens.
function P.peace()
  local me = P.malakai():faction()
  local at_war, n = me:factions_at_war_with(), 0
  for i = 0, at_war:num_items() - 1 do
    cm:force_make_peace(me:name(), at_war:item_at(i):name())
    n = n + 1
  end
  -- No offers either: an offer's panel stops the turn.
  pcall(function() cm:force_diplomacy('all', 'faction:' .. me:name(), 'all', false, false, true) end)
  return 'peace with ' .. n
end

-- The narrative mission "Призыв Духа": its block flag and what it counts. Completions go to the log from src/tww3_mtb_remote.lua.
function P.missions()
  local me = P.malakai():faction():name()
  return {block = tostring(narrative and narrative.get and narrative.get(me, 'dwarf_event_use_army_ability_block')),
    key = tostring(dwf_narrative_missions and dwf_narrative_missions.army_ability and dwf_narrative_missions.army_ability.army_ability_key)}
end

-- The texts of the two hull levels, as the game has them now.
function P.texts()
  local base = 'building_short_description_texts_short_description_wh3_dlc25_dwarf_spirit_of_grungni_airship_hull_'
  return common.get_localised_string(base .. '1') .. ' || ' .. common.get_localised_string(base .. '2')
end

function P.visible_tree(name, depth, filter)
  local root = mtb.find(name, true)
  if not root then return 'no ' .. name end
  return mtb.tree(depth or 8, filter, root)
end

