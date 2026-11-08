// The airship screen's buildings: what may be ordered and why not, the order, cancel, demolish, the stage of each part of the drawing.
// Written as the mod's scripts are (one module M, events, no UI in it), so it can become src/tww3_mtb_buildings.lua line for line.
// It talks to the game only through `game` (web/js/game_sim.js here, the game itself there); places marked GAME are the game's commands.
// Data: build/web/data.json (tools/web_export.py), made by the same functions as the mod's pack; nothing here repeats a price or a tier.

export function makeBuildings(data, game, parts) {
    const M = {game, prefix: data.prefix, parts};
    const prefix = data.prefix;
    const levels = {};
    for (const row of data.hull) levels[row.key] = row;
    for (const chain of data.chains) for (const row of chain.levels) levels[row.key] = row;
    const hullByTier = {};
    for (const row of data.hull) hullByTier[row.level + 1] = row;     // the hull chain's level n is the tree's row n + 1

    let message = null;     // the last thing that happened, for the panel's line of news
    const changed = [];
    M.on_change = fn => changed.push(fn);
    const fire = () => changed.forEach(fn => fn());

    M.level = key => levels[key] || levels[prefix + key];
    // 'hull' or the hull's chain key: the levels of the hull (data.hull); otherwise one of the chains of data.chains
    const hullChain = {key: 'hull', levels: data.hull};
    M.chain = key => (key === 'hull' || (data.hull[0] && key === data.hull[0].chain) ? hullChain : data.chains.find(c => c.key === key));
    M.hull_tier = () => {
        let tier = 0;
        for (const row of data.hull) if (game.has_building(row.key)) tier = Math.max(tier, row.level + 1);
        return tier;
    };

    // {state: built | building | open | locked, turns, why}. why: the reason as the panel prints it.
    M.status = key => {
        const row = M.level(key);
        if (!row) return {state: 'unknown', why: `Нет в выгрузке: ${key}`};     // a building of a chain the page does not export yet
        if (game.has_building(row.key)) return {state: 'built'};
        const turns = game.under_construction(row.key);
        if (turns !== null) return {state: 'building', turns};
        // the hull's own levels need only the level below them (checked next); a side chain needs the hull's tier
        if (row.chain !== hullChain.levels[0].chain && row.tier > M.hull_tier()) return {state: 'locked', why: `Нужен корпус «${hullByTier[row.tier].name}»`};
        const chain = M.chain(row.chain);
        if (chain) {
            const below = chain.levels.find(l => l.level === row.level - 1);
            if (below && !game.has_building(below.key)) return {state: 'locked', why: `Сначала «${below.name}»`};
            const busy = chain.levels.find(l => game.under_construction(l.key) !== null);
            if (busy) return {state: 'locked', why: `Уже строится «${busy.name}»`};
        }
        for (const need of row.requires) {
            if (!game.has_building(need)) return {state: 'locked', why: `Нужна постройка «${M.level(need) ? M.level(need).name : need.slice(prefix.length)}»`};
        }
        if (game.treasury() < row.cost) return {state: 'locked', why: `Не хватает золота: нужно ${row.cost}`, poor: true};
        return {state: 'open'};
    };

    M.order = key => {
        const row = M.level(key);
        const before = M.status(key);
        if (before.state !== 'open') return {ok: false, why: before.why || 'Нельзя заказать'};
        // GAME: DatabaseRecordContext("CcoBuildingLevelRecord", row.key):IssueCommandForBuildingBrowser(slot) through common.call_context_command;
        // the slot is the chain's own one or the first empty (tools/tests/prog_build.lua). The game takes the gold.
        game.issue_building_command(row.key);
        // Check after the order: right after a battle an order sometimes did nothing until the character was selected (progression-proposal.md). Read the slot again.
        if (game.under_construction(row.key) === null) {
            message = `Заказ «${row.name}» не прошёл: игра его не приняла. Выберите Малакая и повторите.`;
            fire();
            return {ok: false, why: message};
        }
        message = `Заказано: «${row.name}», ${row.cost} золота, готово через ${turnsText(row.turns)}.`;
        fire();
        return {ok: true};
    };

    M.cancel = key => {
        const row = M.level(key);
        if (game.under_construction(row.key) === null) return {ok: false};
        // GAME: the same IssueCommandForBuildingBrowser once more cancels (check run 04.11); the game gives the gold back.
        game.cancel_construction(row.key);
        message = `Отменено: «${row.name}», золото вернулось.`;
        fire();
        return {ok: true};
    };

    // Behind the flag ?full=1 until the chain is shown: the mod's rule is that a demolished building closes its options at once (docs/summary.md, «Правило»).
    // A building may be demolished when it is what stands in its slot (not a level an upgrade has replaced) and no other standing building needs it.
    M.can_demolish = key => {
        const row = M.level(key);
        if (!row || !game.has_building(row.key)) return {ok: false, why: 'Не построено'};
        if (!game.standing(row.key)) {
            const chain = M.chain(row.chain);
            const top = chain && [...chain.levels].reverse().find(l => game.standing(l.key));
            return {ok: false, why: `Сначала снесите «${top ? top.name : 'верхний уровень'}»: он стоит на этой постройке`};
        }
        const needing = Object.values(levels).filter(l => l.requires.includes(row.key) && game.has_building(l.key));
        if (needing.length) return {ok: false, why: `Сначала снесите «${needing[0].name}»: ей нужна эта постройка`};
        return {ok: true};
    };

    M.demolish = key => {
        const row = M.level(key);
        if (!M.can_demolish(key).ok) return {ok: false, why: M.can_demolish(key).why};
        // guess: no gold back (the data has no refund for demolishing). In the game the hull cannot be demolished at all (CanDismantle = false): here it can, to test.
        // GAME: HordeContext.BuildingSlotList.At(n).Dismantle
        if (!game.dismantle(row.key)) return {ok: false};
        message = `Снесено: «${row.name}».`;
        fire();
        return {ok: true};
    };

    // The stage of a part of the drawing and the model: pencil (not built), build (under construction), ink (built); none for a part not connected yet
    // (web/data/blueprint.json, enabled). M.all_parts (?parts=all): every part as built, to look at the whole ship.
    M.all_parts = false;
    M.stage = part => {
        const p = parts[part];
        if (M.all_parts) return 'ink';
        if (!p.enabled || !p.building) return 'none';
        const s = M.status(prefix + p.building);
        return s.state === 'built' ? 'ink' : s.state === 'building' ? 'build' : 'pencil';
    };

    M.message = () => message;

    // The game's events, as the mod listens to them (core:add_listener)
    game.on('MilitaryForceBuildingCompleteEvent', ctx => {
        // GAME: here the mod's own on_building also runs (src/tww3_mtb_crew.lua): the bay appears, the hull's mount row changes
        message = `Постройка завершена: «${M.level(ctx.building).name}».`;
        fire();
    });
    game.on('FactionTurnStart', () => { message = null; fire(); });
    return M;
}

export function turnsText(n) {
    const m10 = n % 10, m100 = n % 100;
    const word = m10 === 1 && m100 !== 11 ? 'ход' : (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) ? 'хода' : 'ходов';
    return `${n} ${word}`;
}
