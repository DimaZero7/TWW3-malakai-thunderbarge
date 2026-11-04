-- The mod's campaign part: Malakai walks and stays stock until the barge is built, then the mount item puts him at its wheel.
-- A human Malakai starts on foot with an empty slipway and gets the item once, when airship_hull_2 is complete; from then on the
-- game's own Mount block moves the item on and off and nothing here touches it. Under the AI he has the item from the first tick.
local SUBTYPE = 'wh3_dlc25_dwf_malakai_makaisson'
local HOME_FACTION = 'wh3_dlc25_dwf_malakai'
local ANCILLARY = 'mtb_anc_mount_dwf_malakai_thunderbarge'
local MOUNT_BUILDING = 'wh3_dlc25_dwarf_spirit_of_grungni_airship_hull_2'
local HORDE_TYPE = 'MALAKAI_BOUND_HORDE'
local GIVEN = 'mtb_barge_given'         -- saved: the item has been handed out in this campaign, never again
local PENDING = 'mtb_barge_pending'     -- saved: the building is complete, but he could not be found (wounded)
local MISSION = 'wh3_dlc25_mis_dwf_malakai_warpstone_bomb_6'
local MISSION_ABILITY = 'wh3_dlc25_unit_abilities_thunderburner'

local M = {}
_G.tww3_mtb_campaign = M

local function log(text)
    if _G.mtb and _G.mtb.log then pcall(_G.mtb.log, 'mod', text) end
end

local function is_malakai(character)
    return not character:is_null_interface() and character:character_subtype_key() == SUBTYPE
end

local function find_in_faction(faction)
    local characters = faction:character_list()
    for i = 0, characters:num_items() - 1 do
        if is_malakai(characters:item_at(i)) then return characters:item_at(i) end
    end
end

-- His home faction first, then the whole world (a confederation).
local function find_malakai()
    local home = cm:get_faction(HOME_FACTION)
    local found = home and not home:is_dead() and find_in_faction(home)
    if found then return found end
    local factions = cm:model():world():faction_list()
    for i = 0, factions:num_items() - 1 do
        local faction = factions:item_at(i)
        if not faction:is_dead() then
            found = find_in_faction(faction)
            if found then return found end
        end
    end
end

M.find_malakai = find_malakai

-- Once in a campaign: a second copy would lie in the faction's reserve. force_add_ancillary also equips, so he rides at once.
local function give(character)
    if cm:get_saved_value(GIVEN) then return end
    cm:set_saved_value(GIVEN, true)
    cm:set_saved_value(PENDING, false)
    if character:has_ancillary(ANCILLARY) then return end
    cm:force_add_ancillary(character, ANCILLARY, true, true)
    log('given to cqi ' .. tostring(character:command_queue_index()) .. ' of ' .. character:faction():name())
end

-- For the tests too: cm:add_building_to_force fires no event, so a script that adds a building calls this itself.
function M.on_building(key)
    if key ~= MOUNT_BUILDING or cm:get_saved_value(GIVEN) then return end
    local malakai = find_malakai()
    if malakai then give(malakai) else cm:set_saved_value(PENDING, true) end
end

-- Keys of the buildings in his horde's slots. nil when he has no horde.
function M.slots(character)
    if not character:has_military_force() then return nil end
    local details = character:military_force():horde_details()
    if details:is_null_interface() then return nil end
    local out, slots = {}, details:military_force_slot_list()
    for i = 0, slots:num_items() - 1 do
        if slots:item_at(i):has_building() then out[#out + 1] = slots:item_at(i):building() end
    end
    return out
end

-- startpos.esf gives his horde the hull and barracks_1. Converted away and back, the side buildings are gone and the hull comes back
-- by itself (docs/design/progression-mount.md). Everything else of the force stays. Asked again shortly if the first tick was too early.
local function empty_slipway(character, attempt)
    local slots = M.slots(character)
    if not slots or #slots <= 1 then
        log('slipway: ' .. table.concat(slots or {'no horde'}, ',') .. ' after attempt ' .. attempt)
        return
    end
    if attempt >= 3 then
        log('slipway: not emptied: ' .. table.concat(slots, ','))
        return
    end
    cm:convert_force_to_type(character:military_force(), 'ARMY')
    cm:convert_force_to_type(character:military_force(), HORDE_TYPE)
    cm:callback(function()
        local malakai = find_malakai()
        if malakai then pcall(empty_slipway, malakai, attempt + 1) end
    end, 0.2)
end

local function new_campaign()
    local malakai = find_malakai()
    if not malakai then
        log('new campaign: Malakai not found')
        return
    end
    if malakai:faction():is_human() then
        empty_slipway(malakai, 0)
    else
        give(malakai)
    end
end

-- Two missions count a use of the summon, which ordinary battles no longer have: they count the barge's Thunderburner.
-- Both tables are read when a battle ends, so changing them on the first tick is enough. A plain name: the game's
-- campaign scripts are globals of this environment, not of _G.
local function patch_missions()
    local narrative = false
    if dwf_narrative_missions and dwf_narrative_missions.army_ability then
        dwf_narrative_missions.army_ability.army_ability_key = MISSION_ABILITY
        narrative = true
    end
    local adventure = false
    if malakai_battles and malakai_battles.mission_data then
        local function walk(t, depth)
            if depth > 6 then return false end
            for key, value in pairs(t) do
                if type(value) == 'table' then
                    if key == MISSION and value.ability_key then
                        value.ability_key = MISSION_ABILITY
                        return true
                    end
                    if walk(value, depth + 1) then return true end
                end
            end
            return false
        end
        adventure = walk(malakai_battles.mission_data, 0)
    end
    return tostring(narrative) .. '/' .. tostring(adventure)
end

local function guarded(fn)
    return function(...)
        local ok, err = pcall(fn, ...)
        if not ok then
            pcall(ModLog, '[tww3_mtb] ' .. tostring(err))
            log('error: ' .. tostring(err))
        end
    end
end

cm:add_first_tick_callback(guarded(function()
    log('first tick: new=' .. tostring(cm:is_new_game()) .. ' missions=' .. patch_missions())
    if cm:is_new_game() then new_campaign() end
    core:add_listener('tww3_mtb_barge_built', 'MilitaryForceBuildingCompleteEvent',
        function(context) return context:building() == MOUNT_BUILDING end,
        guarded(function(context) M.on_building(context:building()) end), true)
    core:add_listener('tww3_mtb_barge_pending', 'CharacterTurnStart',
        function(context) return cm:get_saved_value(PENDING) and is_malakai(context:character()) end,
        guarded(function(context) give(context:character()) end), true)
end))
