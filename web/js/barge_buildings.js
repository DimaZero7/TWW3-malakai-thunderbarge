// The airship screen's buildings: what may be ordered and why not, the order, cancel, demolish, the stage of each part of the drawing.
// Written as the mod's scripts are (one module M, events, no UI in it), so it can become src/tww3_mtb_buildings.lua line for line.
// It talks to the game only through `game` (web/js/game_sim.js here, the game itself there); places marked GAME are the game's commands.
// Data: build/web/data.json (tools/web_export.py), made by the same functions as the mod's pack; nothing here repeats a price or a tier.

export function makeBuildings(data, game, parts) {
    const M = {game, prefix: data.prefix, parts};
    // The page's own requirements over the mod's data (blueprint.json, tree.requires: full keys) and the nodes shown but not orderable yet
    M.extra_requires = {};
    M.not_connected = new Set();
    const needsOf = row => [...row.requires, ...(M.extra_requires[row.key] || [])];
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
        for (const need of M.extra_requires[row.key] || []) {
            if (!game.has_building(need)) return {state: 'locked', why: `Нужен: ${M.level(need) ? M.level(need).name : need.slice(prefix.length)}`};
        }
        if (M.not_connected.has(row.key)) return {state: 'locked', why: 'Пока не подключено на странице'};
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
        const needing = Object.values(levels).filter(l => needsOf(l).includes(row.key) && game.has_building(l.key));
        if (needing.length) return {ok: false, why: `Сначала снесите «${needing[0].name}»: ей нужна эта постройка`};
        return {ok: true};
    };

    M.demolish = key => {
        const row = M.level(key);
        if (!M.can_demolish(key).ok) return {ok: false, why: M.can_demolish(key).why};
        // guess: no gold back (the data has no refund for demolishing). In the game the hull cannot be demolished at all (CanDismantle = false): here it can, to test.
        // GAME: HordeContext.BuildingSlotList.At(n).Dismantle
        const crewBefore = message;
        if (!game.dismantle(row.key)) return {ok: false};
        message = `Снесено: «${row.name}».` + (message !== crewBefore && message ? ' ' + message : '');
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

    // Every level a building needs, all the way down (the level below in its chain, the buildings it requires), the deepest first. For the debug button.
    M.needs_all = key => {
        const out = [], seen = new Set();
        const walk = k => {
            const row = M.level(k);
            if (!row || seen.has(row.key)) return;
            seen.add(row.key);
            const chain = M.chain(row.chain);
            const below = chain && chain.levels.find(l => l.level === row.level - 1);
            if (below) walk(below.key);
            for (const r of needsOf(row)) walk(r);
            out.push(row.key);
        };
        walk(key);
        return out;
    };
    M.debug_build_to = key => {
        for (const k of M.needs_all(key)) if (!M.not_connected.has(k)) game.debug_complete(k);
        message = `Отладка: построено до «${M.level(key).name}» без ходов и золота.`;
        fire();
    };
    M.set_side_silently = s => { side = s; };

    let side = 'left';
    // Malakai's side: he stands as a shooter on the left or the right side (docs/design/barge-upgrades-ideas.md, «Место Малакая»).
    // GAME: cm:set_saved_value('mtb_malakai_side', side); src/tww3_mtb_crew.lua would put him on a rifle seat of that side before a battle.
    M.malakai_side = () => side;
    // The hint: the marks glow until the player changes the side once (a tutorial's flag; GAME: cm:set_saved_value('mtb_malakai_side_chosen', true)).
    let sideChosen = false;
    M.side_hint = () => !sideChosen;
    M.set_side_chosen_silently = v => { sideChosen = !!v; };
    M.set_malakai_side = s => {
        if (s === side) return;
        side = s;
        sideChosen = true;
        message = `Малакай встанет на ${s === 'left' ? 'левый' : 'правый'} борт.`;
        fire();
    };

    // ---- The crew: what stands in a group of seats (the riflemen), chosen by the player among what the buildings have opened. ----
    // The rules are the mod's (src/tww3_mtb_crew.lua): a building only opens an option; the hire is taken once, at the choice; what stood is not paid
    // back when it is replaced, and going back to it is paid again; empty is free; the upkeep is taken at the faction's turn start for what stands; a
    // building that goes takes its option with it, the group falls back to its start (empty), nothing is returned.
    // One difference, the page's: the choice stands at once. In the mod the panel orders and the turn carries out, one change of a group a turn.
    // GAME: tww3_mtb_crew.order(group, option) / .get() / .unlocked(); the treasury through cm:treasury_mod.
    const crew = {};
    const openedBy = {};        // group -> option -> the building level that opens it
    for (const row of Object.values(levels)) for (const u of row.unlocks || []) (openedBy[u.group] ||= {})[u.option] = row;
    M.crew = group => crew[group] || data.groups[group].start;
    M.crew_options = group => {
        const g = data.groups[group];
        const rank = k => { const b = (openedBy[group] || {})[k]; return b ? b.tier * 100000 + b.cost : 0; };
        return Object.entries(g.options).filter(([k, o]) => !o.hidden && (k === g.start || (openedBy[group] || {})[k]))
            .map(([key, o], i) => ({key, i, ...o, empty: key === g.start, building: (openedBy[group] || {})[key] || null,
                                    unlocked: key === g.start || game.has_building((openedBy[group] || {})[key].key)}))
            .sort((a, b) => (a.empty ? -1 : b.empty ? 1 : rank(a.key) - rank(b.key) || a.i - b.i));
    };
    M.crew_upkeep = () => Object.keys(data.groups).reduce((sum, g) => sum + ((data.groups[g].options[M.crew(g)] || {}).upkeep || 0), 0);
    M.set_crew = (group, option) => {
        const o = M.crew_options(group).find(x => x.key === option);
        if (!o) return {ok: false};
        if (option === M.crew(group)) return {ok: true, same: true};
        if (!o.unlocked) { message = `«${o.name}» откроет постройка «${o.building.name}».`; fire(); return {ok: false, why: message}; }
        if (game.treasury() < o.hire) { message = `Не хватает золота на «${o.name}»: найм ${o.hire}.`; fire(); return {ok: false, why: message}; }
        game.gold -= o.hire;        // GAME: cm:treasury_mod(faction, -hire)
        crew[group] = option;
        message = o.empty ? 'Стрелки сошли с бортов.' : `«${o.name}» встают к бортам: найм ${o.hire}, содержание ${o.upkeep} за ход.`;
        fire();
        return {ok: true};
    };
    M.crew_snapshot = () => ({...crew});
    M.set_crew_silently = saved => { for (const [g, o] of Object.entries(saved || {})) if (data.groups[g] && data.groups[g].options[o]) crew[g] = o; };
    // a building that no longer stands takes its crew away
    const dropLostCrew = () => {
        const lost = [];
        for (const g of Object.keys(crew)) {
            const o = M.crew_options(g).find(x => x.key === crew[g]);
            if (o && !o.unlocked) { lost.push(o.name); delete crew[g]; }
        }
        return lost;
    };
    game.on('BuildingDemolished', () => {
        const lost = dropLostCrew();
        if (lost.length) { message = `«${lost.join('», «')}» сошли с корабля: их постройки больше нет. Найм не возвращается.`; fire(); }
    });

    // The game's events, as the mod listens to them (core:add_listener)
    game.on('MilitaryForceBuildingCompleteEvent', ctx => {
        // GAME: here the mod's own on_building also runs (src/tww3_mtb_crew.lua): the bay appears, the hull's mount row changes
        message = `Постройка завершена: «${M.level(ctx.building).name}».`;
        fire();
    });
    game.on('FactionTurnStart', () => {
        const upkeep = M.crew_upkeep();
        game.gold -= upkeep;        // GAME: the mod takes the crew's upkeep at the faction's turn start (cm:treasury_mod); the page lets the treasury go below zero
        message = upkeep ? `Содержание экипажа: ${upkeep} золота.` : null;
        fire();
    });
    return M;
}

export function turnsText(n) {
    const m10 = n % 10, m100 = n % 100;
    const word = m10 === 1 && m100 !== 11 ? 'ход' : (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) ? 'хода' : 'ходов';
    return `${n} ${word}`;
}
