// The airship screen's buildings: what may be ordered and why not, the order, cancel, demolish, the stage of each part of the drawing.
// Written as the mod's scripts are (one module M, events, no UI in it), so it can become src/tww3_mtb_buildings.lua line for line.
// It talks to the game only through `game` (web/js/game_sim.js here, the game itself there); places marked GAME are the game's commands.
// Data: build/web/data.json (tools/web_export.py), made by the same functions as the mod's pack; nothing here repeats a price or a tier.

import * as crewModel from './crew_model.mjs';

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
    // the hull's levels and their tier: the hull chain's level n is tier n + 1; a tree of the constructor (web/js/tree_model.mjs, gameData) names
    // its hull nodes itself (hull_tiers: key -> tier)
    const hullTier = data.hull_tiers || Object.fromEntries(data.hull.map(row => [row.key, row.level + 1]));
    const hullByTier = {};
    for (const [key, tier] of Object.entries(hullTier)) hullByTier[tier] ||= levels[key];

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
        for (const [key, t] of Object.entries(hullTier)) if (game.has_building(key)) tier = Math.max(tier, t);
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
        if (!(row.key in hullTier) && row.tier > M.hull_tier()) return {state: 'locked', why: hullByTier[row.tier] ? `Нужен корпус «${hullByTier[row.tier].name}»` : `Нужен корпус яруса ${row.tier}`};
        const chain = M.chain(row.chain);
        if (chain) {
            const below = chain.levels.find(l => l.level === row.level - 1);
            if (below && !game.has_building(below.key)) return {state: 'locked', why: `Сначала «${below.name}»`};
            const busy = chain.levels.find(l => game.under_construction(l.key) !== null);
            if (busy) return {state: 'locked', why: `Уже строится «${busy.name}»`};
        }
        // every building it requires (a node of the tree may have several parents): all that are missing are named
        const missing = row.requires.filter(need => !game.has_building(need)).map(need => `«${M.level(need) ? M.level(need).name : need.slice(prefix.length)}»`);
        if (missing.length) return {state: 'locked', why: missing.length === 1 ? `Нужна постройка ${missing[0]}` : `Нужны постройки ${missing.join(', ')}`, missing: row.requires.filter(need => !game.has_building(need))};
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

    // ---- The crew: what stands in a group of seats (the riflemen) and what is ordered for the next turn. ----
    // The rules live apart from the page, in web/js/crew_model.mjs (pure functions, tested by tools/tests/crew_model_test.mjs); here they only meet
    // the game: the treasury, the buildings, the turn. From the mod (src/tww3_mtb_crew.lua): an order goes in at the faction's turn start and what
    // stands stays till then; the hire is taken when it is ordered and comes back when the order is taken back; what stood is not paid back; the
    // upkeep is taken at the turn start, after the orders went in; a building that goes takes its option (an order with its gold back, a standing
    // crew for nothing). Not the mod's, the page's (the mod is to follow): the order may be changed any number of times in a turn, and the gold
    // taken always is the hire of the order that waits.
    // GAME: tww3_mtb_crew.choose(group, option) / .get() / .orders() / .unlocked(); the treasury through cm:treasury_mod.
    const crew = {};            // group -> {standing, order: null | {option, paid}} (crew_model.mjs)
    // group -> option -> the building levels that open it (a tree of the constructor may give one kind to several buildings: any of them opens it)
    const openers = {};
    for (const row of Object.values(levels)) for (const u of row.unlocks || []) ((openers[u.group] ||= {})[u.option] ||= []).push(row);
    const cheap = r => r.tier * 100000 + r.cost;
    // the one to name: a standing one, else the cheapest
    const opener = (g, o) => { const list = (openers[g] || {})[o]; return list ? list.find(r => game.has_building(r.key)) || [...list].sort((a, b) => cheap(a) - cheap(b))[0] : null; };
    const stateOf = g => crew[g] || {standing: data.groups[g].start, order: null};
    const ctxOf = g => ({start: data.groups[g].start, gold: game.treasury(), hire: o => (data.groups[g].options[o] || {}).hire || 0,
                         unlocked: o => o === data.groups[g].start || ((openers[g] || {})[o] || []).some(r => game.has_building(r.key))});
    M.crew = group => stateOf(group).standing;
    M.crew_order = group => (stateOf(group).order ? stateOf(group).order.option : null);
    M.crew_options = group => {
        const g = data.groups[group], ctx = ctxOf(group);
        const rank = k => { const b = opener(group, k); return b ? cheap(b) : 0; };
        return Object.entries(g.options).filter(([k, o]) => !o.hidden && (k === g.start || opener(group, k)))
            .map(([key, o], i) => ({key, i, ...o, empty: key === g.start, building: opener(group, key), unlocked: ctx.unlocked(key)}))
            .sort((a, b) => (a.empty ? -1 : b.empty ? 1 : rank(a.key) - rank(b.key) || a.i - b.i));
    };
    const upkeepOf = (g, o) => (data.groups[g].options[o] || {}).upkeep || 0;
    // gold per turn now, and with the orders of this turn (M.upkeep of the mod)
    M.crew_upkeep = () => Object.keys(data.groups).reduce((sum, g) => sum + upkeepOf(g, M.crew(g)), 0);
    M.crew_upkeep_next = () => Object.keys(data.groups).reduce((sum, g) => sum + upkeepOf(g, M.crew_order(g) || M.crew(g)), 0);
    // What a click on an option would do, without doing it (the window's line under the mouse), and what the last click did (its line after).
    const nameOf = (g, o) => (o === data.groups[g].start ? 'пустые борта' : `«${data.groups[g].options[o].name}»`);
    const sayResult = (g, r, done) => {
        const n = nameOf(g, r.option), start = data.groups[g].start;
        if (r.kind === 'locked') return {bad: true, text: `Заперто: ${n} откроет постройка «${opener(g, r.option).name}»`};
        if (r.kind === 'poor') return {bad: true, text: `Не хватает золота на ${n}: найм ${r.hire}, есть ${r.have}`};
        if (r.kind === 'kept') return {text: r.why === 'ordered' ? (r.option === start ? 'Экипаж уже сходит в начале хода' : `${n} уже в найме`) : r.option === start ? 'У бортов никого' : `${n} уже у бортов`};
        const back = r.back ? `, вернулось ${r.back}` : '', willBack = r.back ? `, вернётся ${r.back}` : '';
        if (r.kind === 'cancelled') return {text: done ? `Заказ на ${nameOf(g, r.option)} снят${back}` : `Снять заказ на ${nameOf(g, r.option)}${willBack}: у бортов остаются, кто стоит`};
        if (r.option === start) return {text: done ? `Экипаж сойдёт в начале хода${back}` : `Снять экипаж в начале хода${willBack}`};
        const instead = r.instead && r.instead !== start ? ` вместо ${nameOf(g, r.instead)}` : '';
        return {text: done ? `В найме ${n}${instead}: списано ${r.taken}${back}, встанут в начале хода` : `Нанять ${n}${instead}: найм ${r.taken}${willBack}, встанут в начале хода`};
    };
    const notes = {};           // group -> what the last click did
    M.crew_note = group => notes[group] || null;
    M.crew_preview = (group, option) => { const r = crewModel.click(stateOf(group), option, ctxOf(group)).result; return {kind: r.kind, ...sayResult(group, r, false)}; };
    M.set_crew = (group, option) => {
        if (!data.groups[group].options[option]) return {ok: false};
        const r = crewModel.click(stateOf(group), option, ctxOf(group));
        crew[group] = r.state;
        game.gold = r.gold;         // GAME: cm:treasury_mod(faction, back - taken)
        notes[group] = sayResult(group, r.result, true);
        if (r.result.kind === 'ordered') crewChosen = true;
        message = notes[group].text + '.';
        fire();
        return {ok: r.result.kind === 'ordered' || r.result.kind === 'cancelled', kind: r.result.kind};
    };
    // The hint: the place's tag glows until the player chooses a crew once (as the side's hint; GAME: cm:set_saved_value('mtb_crew_chosen', true)).
    let crewChosen = false;
    M.crew_hint = () => !crewChosen;
    M.set_crew_chosen_silently = v => { crewChosen = !!v; };
    M.crew_snapshot = () => JSON.parse(JSON.stringify(crew));
    M.set_crew_silently = saved => {
        for (const [g, st] of Object.entries(saved || {})) {
            if (!data.groups[g] || !st || !data.groups[g].options[st.standing]) continue;
            const order = st.order && data.groups[g].options[st.order.option] ? {option: st.order.option, paid: Number(st.order.paid) || 0} : null;
            crew[g] = {standing: st.standing, order};
        }
    };
    // a building that no longer stands takes its option away: the order with its gold, the standing crew without
    game.on('BuildingDemolished', () => {
        const said = [];
        for (const g of Object.keys(crew)) {
            const r = crewModel.lose(stateOf(g), ctxOf(g));
            crew[g] = r.state;
            game.gold = r.gold;
            for (const l of r.lost) said.push(l.kind === 'order' ? `заказ на ${nameOf(g, l.option)} снят, ${l.back} золота вернулось` : `${nameOf(g, l.option)} сошли с корабля, найм не возвращается`);
            if (r.lost.length) delete notes[g];
        }
        if (said.length) { message = 'Постройки больше нет: ' + said.join('; ') + '.'; fire(); }
    });

    // The game's events, as the mod listens to them (core:add_listener)
    game.on('MilitaryForceBuildingCompleteEvent', ctx => {
        // GAME: here the mod's own on_building also runs (src/tww3_mtb_crew.lua): the bay appears, the hull's mount row changes
        message = `Постройка завершена: «${M.level(ctx.building).name}».`;
        fire();
    });
    game.on('FactionTurnStart', () => {
        // the orders go in (M.carry_out), then the upkeep of what stands now is taken (M.pay_upkeep)
        const came = [];
        for (const g of Object.keys(crew)) {
            if (!crew[g].order) continue;
            crew[g] = crewModel.turn(crew[g]);
            delete notes[g];
            came.push(crew[g].standing === data.groups[g].start ? 'стрелки сошли с бортов' : `${nameOf(g, crew[g].standing)} встали к бортам`);
        }
        const upkeep = M.crew_upkeep();
        game.gold -= upkeep;        // GAME: cm:treasury_mod; the page lets the treasury go below zero
        message = [came.length ? came.join('; ') : '', upkeep ? `содержание экипажа: ${upkeep} золота` : ''].filter(Boolean).join(', ');
        message = message ? message[0].toUpperCase() + message.slice(1) + '.' : null;
        fire();
    });
    return M;
}

export function turnsText(n) {
    const m10 = n % 10, m100 = n % 100;
    const word = m10 === 1 && m100 !== 11 ? 'ход' : (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) ? 'хода' : 'ходов';
    return `${n} ${word}`;
}
