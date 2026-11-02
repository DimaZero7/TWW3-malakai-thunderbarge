-- The mod's campaign part: Malakai rides the Spirit of Grungni in battles, stays on foot on the map.
-- One mount item on him, given once, wherever he is (his faction, a confederation, under the AI). Safe on old saves.
local SUBTYPE = 'wh3_dlc25_dwf_malakai_makaisson'
local HOME_FACTION = 'wh3_dlc25_dwf_malakai'
local ANCILLARY = 'mtb_anc_mount_dwf_malakai_thunderbarge'
local MISSION = 'wh3_dlc25_mis_dwf_malakai_warpstone_bomb_6'
local MISSION_ABILITY = 'wh3_dlc25_unit_abilities_thunderburner'

local function log(text)
    if _G.mtb and _G.mtb.log then pcall(_G.mtb.log, 'mod', text) end
end

-- Gives the item if he does not have it yet. Returns true when he has it afterwards.
local function equip(character)
    if character:has_ancillary(ANCILLARY) then return true end
    cm:force_add_ancillary(character, ANCILLARY, true, true)
    log('given to cqi ' .. tostring(character:command_queue_index()) .. ' of ' .. character:faction():name())
    return true
end

local function is_malakai(character)
    return not character:is_null_interface() and character:character_subtype_key() == SUBTYPE
end

local function scan_faction(faction)
    local characters = faction:character_list()
    for i = 0, characters:num_items() - 1 do
        local character = characters:item_at(i)
        if is_malakai(character) then
            equip(character)
            return true
        end
    end
    return false
end

-- Malakai's home faction first, then the whole world (a confederation, or his faction under another name).
local function scan_world()
    local home = cm:get_faction(HOME_FACTION)
    if home and not home:is_dead() and scan_faction(home) then return true end
    local factions = cm:model():world():faction_list()
    for i = 0, factions:num_items() - 1 do
        local faction = factions:item_at(i)
        if not faction:is_dead() and scan_faction(faction) then return true end
    end
    return false
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
    log('first tick: found=' .. tostring(scan_world()) .. ' missions=' .. patch_missions())
    -- He comes back from a wound or is created later: the check is cheap and does nothing when he has the item.
    core:add_listener('tww3_mtb_turn', 'CharacterTurnStart',
        function(context) return is_malakai(context:character()) end,
        guarded(function(context) equip(context:character()) end), true)
    core:add_listener('tww3_mtb_confederation', 'FactionJoinsConfederation', true,
        guarded(function() scan_world() end), true)
end))
