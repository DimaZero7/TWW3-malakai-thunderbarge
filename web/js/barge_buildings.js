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

    // the game's own words for a building whose requirement is not met (local_ru: campaign_localised_strings_string_building_required, and the
    // building tooltip's label of a list of them, wh3_dlc26_building_info_tooltip_required_buildings_label_tx: «Требуется постройка:»)
    M.REQUIRES = 'Требуется постройка: ';
    M.REQUIRES_MANY = 'Требуются постройки: ';      // several: the plural of the same line
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

    // The hull a tier asks for: the hull level of that tier, else the lowest hull above it (a tree may skip a tier); null when the tree has none
    const hullFor = tier => hullByTier[tier] || Object.entries(hullTier).filter(([, t]) => t >= tier).sort((a, b) => a[1] - b[1]).map(([k]) => levels[k])[0] || null;
    // The direct requirements of a level that do not stand yet, nearest first. Direct: the level below it in its line, every building it requires
    // (a node of the tree may have several parents, and the page's extra ones), and the hull of its tier when the hull's tier is short and that hull
    // is not named already. Nearest: the fewest buildings still to build to get it (itself counted), then the order above. One rule for every case,
    // so the reason never hides a missing parent behind the hull and never names the hull twice. -> [key]
    M.missing = key => {
        const row = M.level(key);
        if (!row) return [];
        const out = [];
        const add = k => { if (k && k !== row.key && !out.includes(k) && !game.has_building(k)) out.push(k); };
        const chain = M.chain(row.chain);
        const below = chain && chain.levels.find(l => l.level === row.level - 1);
        if (below) add(below.key);
        for (const k of needsOf(row)) add(k);
        if (!(row.key in hullTier) && row.tier > M.hull_tier()) { const h = hullFor(row.tier); if (h) add(h.key); else out.push('tier:' + row.tier); }
        const left = k => (k.startsWith('tier:') ? 1e6 : M.needs_all(k).filter(x => !game.has_building(x)).length);
        return out.map((k, i) => ({k, i, d: left(k)})).sort((a, b) => a.d - b.d || a.i - b.i).map(x => x.k);
    };
    // the reason of a locked level in the game's words (the game's own line for a building whose requirements are not met, local_ru: see
    // M.REQUIRES): the buildings in quotes, nearest first
    M.requires_text = keys => (keys.length > 1 ? M.REQUIRES_MANY : M.REQUIRES) + keys.map(k => (k.startsWith('tier:') ? `корпус яруса ${k.slice(5)}` : `«${M.level(k) ? M.level(k).name : k.slice(prefix.length)}»`)).join(', ');

    // The price of a level as the game takes it: its gold (GAME: CreateCost(this) from Malakai's context, the data's price when it does not answer)
    // and its development points (DevelopmentPointCost(this); the data's: tools/tree_export.mjs, data/tree_port.json В2). The force's points now:
    // GAME: MilitaryForceContext.HordeContext.DevelopmentPoints; null when the game does not say (then the game alone judges them).
    M.cost = key => { const row = M.level(key); return game.cost ? game.cost(row.key) : row.cost; };
    M.dev = key => { const row = M.level(key); return game.dev_cost ? game.dev_cost(row.key) : row.dev || 0; };
    M.points = () => (game.development_points ? game.development_points() : null);
    // the game's words for the points of a horde's building (local_ru: random_localisation_strings_string_building_insufficent_development_points
    // «Недостаточно избытка населения», pop_surplus_cost_tooltip «Требуемый избыток населения»): the name in the genitive, as the reasons use it,
    // and in the nominative
    M.POINTS = 'избытка населения';
    M.POINTS_NOM = 'избыток населения';
    // The horde's growth as the game counts it (GAME: HordeContext.AccumulatedGrowth, GrowthPerTurn, GrowthThresholdForPoint,
    // TurnsUntilNextGrowthPoint, HasMaxDevelopmentPoints: the game's own horde building browser reads these): {now, per_turn, need, turns, max};
    // null when the game does not say
    M.growth = () => (game.growth ? game.growth() : null);
    // A building being dismantled: the game takes it at the end of the turn (probe 14.11, 8.2), it stands till then
    const going = row => !!(game.dismantling && game.dismantling(row.key));
    const belowOf = row => { const chain = M.chain(row.chain); return (chain && chain.levels.find(l => l.level === row.level - 1)) || null; };
    // What a dismantle of a level takes (GAME: the slot's whole building, its lower levels with it: run 20261115-012811, «Пивной чертог» II
    // dismantled, the slot empty after the turn); the top first
    const takesOf = row => (game.dismantle_takes ? game.dismantle_takes(row.key) : [row.key]).map(k => M.level(k)).filter(Boolean);
    // the standing level of a line being dismantled (its mark), and the names of what goes with it
    const goingTop = row => { const chain = M.chain(row.chain); return (chain && [...chain.levels].reverse().find(l => game.standing(l.key))) || row; };
    const namesOf = rows => rows.map(r => `«${r.name}»`).join(', ');
    const goesText = rows => `${namesOf(rows)} ${rows.length > 1 ? 'уйдут' : 'уйдёт'} в конце хода`;
    // the direct requirements of a level that stand but are being dismantled (they will not stand next turn): the level below, the buildings it needs
    const goingNeeds = row => {
        const below = belowOf(row);
        return [...(below ? [below] : []), ...needsOf(row).map(k => M.level(k)).filter(Boolean)].filter(r => game.has_building(r.key) && going(r));
    };

    // A command the game applies a moment later (GAME: the slot read right after IssueCommandForBuildingBrowser still shows the old state, run
    // 20261115-012811; the adapter reads it again on the game's next ticks and tells CommandResult {key, kind}). Till then the panel says nothing
    // and the slot shows the command waiting (pending: 'order' | 'cancel'). key -> {kind, cost, dev}
    const pending = {};
    M.pending = key => { const row = M.level(key); return row && pending[row.key] ? pending[row.key].kind : null; };
    // the building window's instruction line while a command waits for the game (instead of «Щелчок — …»); '' when nothing waits
    M.pending_note = key => {
        const st = M.status(key);
        if (st.pending === 'order') return 'Заказ отправлен, ждём ответа игры.';
        if (st.pending === 'cancel') return `Строится, осталось ${turnsText(st.turns)}. Отмена отправлена, ждём ответа игры.`;
        return '';
    };

    // {state: built | dismantling | building | open | locked, turns, asked, pending, why, missing, poor, short}. why: the reason as the panel prints
    // it (without the full stop). poor: short of gold; short: short of development points; asked: a cancel waits for the game's window; pending:
    // an order or a cancel the game has not applied yet.
    M.status = key => {
        const row = M.level(key);
        if (!row) return {state: 'unknown', why: `Нет в выгрузке: ${key}`};     // a building of a chain the page does not export yet
        if (game.has_building(row.key)) return going(row) ? {state: 'dismantling', why: `Сносится: ${goesText(takesOf(goingTop(row)))}`} : {state: 'built'};
        const turns = game.under_construction(row.key);
        const p = pending[row.key];
        if (turns !== null) {
            const st = {state: 'building', turns};
            if (game.cancel_asked && game.cancel_asked(row.key)) st.asked = true;
            if (p) st.pending = p.kind;
            return st;
        }
        if (p && p.kind === 'order') return {state: 'building', turns: row.turns, pending: 'order'};
        const missing = M.missing(row.key);
        if (missing.length) return {state: 'locked', why: M.requires_text(missing), missing};
        const gone = goingNeeds(row);
        if (gone.length) return {state: 'locked', why: `«${gone[0].name}» сносится: уйдёт в конце хода`};
        // a line of levels builds one level at a time (the game's slot holds one construction)
        const chain = M.chain(row.chain);
        const busy = chain && chain.levels.find(l => game.under_construction(l.key) !== null);
        if (busy) return {state: 'locked', why: `Уже строится «${busy.name}»`};
        if (M.not_connected.has(row.key)) return {state: 'locked', why: 'Пока не подключено на странице'};
        const dev = M.dev(row.key), have = M.points();
        if (dev > 0 && have !== null && have < dev) return {state: 'locked', why: `Не хватает ${M.POINTS}: нужно ${dev}`, short: true};
        if (game.treasury() < M.cost(row.key)) return {state: 'locked', why: `Не хватает золота: нужно ${M.cost(row.key)}`, poor: true};
        return {state: 'open'};
    };

    M.order = key => {
        const row = M.level(key);
        const before = M.status(key);
        if (before.state !== 'open') return {ok: false, why: before.why || 'Нельзя заказать'};
        // GAME: DatabaseRecordContext("CcoBuildingLevelRecord", row.key):IssueCommandForBuildingBrowser(slot) through common.call_context_command;
        // the slot is the chain's own one or the first empty (tools/tests/prog_build.lua). The game takes the gold.
        const cost = M.cost(row.key), dev = M.dev(row.key);
        // 'pending': the game applies it a moment later (CommandResult below); otherwise it is applied now
        if (game.issue_building_command(row.key) === 'pending') {
            pending[row.key] = {kind: 'order', cost, dev};
            // the foot line from the click on: the wait, never the last verdict (run 20261115-030121: «Отменено…» stood under a fresh order)
            message = `Заказ «${row.name}» отправлен, ждём ответа игры.`;
            fire();
            return {ok: true, kind: 'pending'};
        }
        const out = ordered(row, cost, dev);
        fire();
        return out;
    };
    // Check after the order: the game may refuse it while answering ok (port-to-game.md 3.4). Read the slot again; the game's reason when it
    // gives one (GAME: the adapter reads IsActiveForBuildingBrowser and its gates before the command)
    const ordered = (row, cost, dev) => {
        if (game.under_construction(row.key) === null) {
            const why = game.refusal ? game.refusal(row.key) : null;
            message = `Заказ «${row.name}» не прошёл: ${why || 'игра его не приняла'}.`;
            return {ok: false, why: message};
        }
        message = `Заказано: «${row.name}», ${cost} золота${dev > 0 ? ` и ${dev} ед. ${M.POINTS}` : ''}, готово через ${turnsText(row.turns)}.`;
        return {ok: true};
    };

    // Why a level cannot be ordered now, as a sentence: the building window's red line and the foot row after a refused click say the same.
    // '' when it can be ordered (or stands, or is being built).
    M.reason = key => {
        const st = M.status(key);
        if (st.state === 'dismantling') return `${st.why}.`;
        if (st.state !== 'locked' && st.state !== 'unknown') return '';
        if (st.short) return `Не хватает ${M.POINTS}: нужно ${M.dev(key)}, есть ${M.points()}.`;
        return st.poor ? `Не хватает золота: нужно ${M.cost(key)}, в казне ${game.treasury()}.` : `${st.why || 'Недоступно'}.`;
    };
    // a click on a slot that cannot be ordered: the foot row says why (the message before it goes)
    M.refuse = key => {
        const why = M.reason(key);
        if (!why) return false;
        message = why;
        fire();
        return true;
    };

    // GAME: the same IssueCommandForBuildingBrowser once more cancels (check run 04.11); the game gives the gold back. A construction of an earlier
    // turn: the game asks first in its own window «Отменить строительство» (probe 14.11, item 12) and nothing changes until it is answered; the
    // panel says so and waits (status building, asked), the answer comes as CancelAnswered. guess: the points come back with the gold.
    const cancelled = row => `Отменено: «${row.name}», ${M.dev(row.key) > 0 ? `золото и ${M.POINTS_NOM} вернулись` : 'золото вернулось'}.`;
    M.cancel = key => {
        const row = M.level(key);
        if (game.under_construction(row.key) === null || pending[row.key]) return {ok: false};
        if (game.cancel_asked && game.cancel_asked(row.key)) return {ok: false, why: `Отмена «${row.name}»: ответьте в окне игры.`};
        if (game.cancel_construction(row.key) === 'pending') {
            pending[row.key] = {kind: 'cancel'};
            message = `Отмена «${row.name}» отправлена, ждём ответа игры.`;
            fire();
            return {ok: true, kind: 'pending'};
        }
        const out = uncancelled(row);
        fire();
        return out;
    };
    const uncancelled = row => {
        if (game.under_construction(row.key) !== null) {
            message = game.cancel_asked && game.cancel_asked(row.key) ? `Отмена «${row.name}»: ответьте в окне игры.` : `Отмена «${row.name}» не прошла: игра её не приняла.`;
            return {ok: false, why: message};
        }
        message = cancelled(row);
        return {ok: true};
    };
    // the game applied a waiting command (or the adapter gave up waiting): what it did is read now, and said
    game.on('CommandResult', ctx => {
        const row = M.level(ctx.key);
        const p = row && pending[row.key];
        if (!p) return;
        delete pending[row.key];
        if (p.kind === 'order') ordered(row, p.cost, p.dev);
        else uncancelled(row);
        fire();
    });
    game.on('CancelAnswered', ctx => {
        const row = M.level(ctx.key);
        if (!row) return;
        message = ctx.cancelled ? cancelled(row) : `Стройка «${row.name}» продолжается: отмену не подтвердили.`;
        fire();
    });

    // Behind the flag ?full=1 until the chain is shown: the mod's rule is that a demolished building closes its options at once (docs/summary.md, «Правило»).
    // A building may be demolished when it is what stands in its slot (not a level an upgrade has replaced) and no other standing building needs it.
    M.can_demolish = key => {
        const row = M.level(key);
        if (!row || !game.has_building(row.key)) return {ok: false, why: 'Не построено'};
        // the hull carries everything: the game has no dismantle for it (CanDismantle = false)
        if (row.key in hullTier) return {ok: false, why: 'Корпус не сносится: на нём держится весь корабль'};
        if (going(row)) return {ok: false, why: 'Уже сносится: постройка уйдёт в конце хода'};
        if (!game.standing(row.key)) {
            const chain = M.chain(row.chain);
            const top = chain && [...chain.levels].reverse().find(l => game.standing(l.key));
            return {ok: false, why: `Сначала снесите «${top ? top.name : 'верхний уровень'}»: он стоит на этой постройке`};
        }
        // what stands on any level the dismantle takes (the game takes the lower levels of the line with it)
        const takes = takesOf(row).map(r => r.key);
        const needing = Object.values(levels).filter(l => !takes.includes(l.key) && needsOf(l).some(k => takes.includes(k)) && game.has_building(l.key));
        if (needing.length) return {ok: false, why: `Сначала снесите «${needing[0].name}»: ей нужна эта постройка`};
        // a level of its line under construction in the same slot: that first
        const chain = M.chain(row.chain);
        const busy = chain && chain.levels.find(l => game.under_construction(l.key) !== null);
        if (busy) return {ok: false, why: `Сначала отмените стройку «${busy.name}»`};
        return {ok: true};
    };

    M.demolish = key => {
        const row = M.level(key);
        if (!M.can_demolish(key).ok) return {ok: false, why: M.can_demolish(key).why};
        // GAME: HordeContext.BuildingSlotList.At(n).Dismantle, after its CanDismantle. The building stands until the turn ends (probe 14.11, 8.2): it
        // is «being dismantled» till then (the game's adapter keeps the mark in the save), its crew and what it opens stay; at the turn's start it is
        // gone (BuildingDemolished). The game pays back part of its price then (M.refund).
        const said = demolishSaid(row);
        if (!game.dismantle(row.key)) {
            message = `Снос «${row.name}» не прошёл: игра его не приняла.`;
            fire();
            return {ok: false, why: message};
        }
        message = `Снос заказан: ${said}`;
        fire();
        return {ok: true};
    };
    // What a demolish will take, said before it is confirmed (the round button's tooltip) and when it is ordered: every level that goes, the crew
    // places it closes, the crew and the orders that go with them. '' when it cannot be demolished
    M.demolish_preview = key => (M.can_demolish(key).ok ? `Снос: ${demolishSaid(M.level(key))}` : '');
    const demolishSaid = row => {
        const fx = afterDemolish(row), back = M.refund(row.key);
        let s = goesText(fx.takes) + '.';
        if (back > 0) s += ` За снос вернётся ${back} золота.`;
        if (fx.places.length) s += ` ${fx.places.length > 1 ? 'Закроются места экипажа' : 'Закроется место экипажа'} ${quoted(fx.places.map(M.place_name))}.`;
        if (fx.said.length) s += ' ' + upper(fx.said.join('; ')) + '.';
        return s;
    };
    const upper = s => (s ? s[0].toUpperCase() + s.slice(1) : s);

    // The stage of a part of the drawing and the model: pencil (not built), build (under construction), ink (built); none for a part not connected yet
    // (web/data/blueprint.json, enabled). M.all_parts (?parts=all): every part as built, to look at the whole ship.
    // A node of the constructor's tree may bring a detail too (web/data/tree_design.json, parts: {part}): it shows with any building that brings it,
    // the detail's own building of blueprint.json or a node's. The stage of the most advanced of them.
    M.all_parts = false;
    const partOpeners = {};
    for (const row of Object.values(levels)) for (const p of row.parts || []) if (p.part) (partOpeners[p.part] ||= []).push(row.key);
    M.part_openers = part => partOpeners[part] || [];
    // The part everything else stands on (web/data/blueprint.json, carrier: the base barge): while it is not built (bare timber, the frame on its
    // slip, the hull being built) no detail and no crew place is on the drawing or the model, in no stage, not even as a pencil of what is to come.
    M.carrier = Object.keys(parts || {}).find(k => parts[k] && parts[k].carrier) || null;
    M.carried = () => !M.carrier || M.stage(M.carrier) === 'ink';
    M.stage = part => {
        const p = parts[part];
        if (!p) return 'none';         // a detail the stage or the tree does not have: simply not there
        if (M.all_parts) return 'ink';
        if (M.carrier && part !== M.carrier && !p.base && !M.carried()) return 'none';
        const keys = [...(p.building ? [prefix + p.building] : []), ...(partOpeners[part] || [])];
        if (!p.enabled || !keys.length) return 'none';
        // a node's own detail goes when a higher level of its line replaces it without carrying the detail on
        const states = keys.map(k => (partOpeners[part] || []).includes(k) && M.status(k).state === 'built' && !M.stands(k) ? 'pencil' : M.status(k).state);
        return states.includes('built') ? 'ink' : states.includes('building') ? 'build' : 'pencil';
    };

    // The turn's report: what the game's events of the turn's start told (the buildings gone and the gold they gave back, the crew that came or
    // left, the upkeep, the completions, a crew gone with its building) stays the player's news until the panel has been on the screen with it,
    // also when the panel was closed when it happened (GAME: the screen marks it read a moment after the panel shows it,
    // src/tww3_mtb_ship_screen.lua; the page the same, web/js/main.js; the vectors' report_read). Till then a click's line comes after it in the
    // foot row, not instead of it, and the HUD's button carries the game's mark of something waiting. {turn, text, read}
    let report = null;
    M.report = () => (report && !report.read && report.turn === game.turn ? report.text : null);
    M.report_read = () => { if (report) report.read = true; };
    // what an event of the game has just said (message) is the report; more: added to a report not read yet (a crew gone after the turn's start)
    const told = more => {
        if (!message) return;
        const r = M.report();
        if (more && r) message = r + ' ' + message;
        report = {turn: game.turn, text: message, read: false};
    };
    // the foot row: the unread report first, then what the player did since
    M.message = () => { const r = M.report(); return r && message && message !== r ? r + ' ' + message : r || message; };
    // the foot line through a reload, as the rest of the state (main.js saves it with the game): what happened stays said until something else happens
    M.message_snapshot = () => ({text: message, turn_line: turnLine, report: report ? {...report} : null});
    M.set_message_silently = s => {
        message = s && typeof s.text === 'string' && s.text ? s.text : null;
        turnLine = s && s.turn_line && typeof s.turn_line.text === 'string' ? {turn: Number(s.turn_line.turn), text: s.turn_line.text} : null;
        report = s && s.report && typeof s.report.text === 'string' ? {turn: Number(s.report.turn), text: s.report.text, read: !!s.report.read} : null;
    };

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
        message = null;         // a debug action of the page, not the game's: told in the page's bar (main.js), never in the panel
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
    // the earlier of two buildings: a tree of the constructor by how many buildings stand before it (its tier is often unset), the mod's by tier; then the price
    const cheap = r => (data.tree_rows ? M.needs_all(r.key).length : r.tier) * 100000 + r.cost;
    // the one to name: a standing one, else the cheapest
    // A tree of the constructor: what a building opens is its full set with its line (tree_model.mjs resolve), and of a line of levels only the level
    // that stands acts (the game's chain: II replaces I, what I opened stays only when II carries it on). The mod's data: a higher level counts the
    // lower ones as standing (src/tww3_mtb_crew.lua).
    const stands = r => (data.tree_rows ? game.standing(r.key) : game.has_building(r.key));
    M.stands = key => { const r = M.level(key); return !!r && stands(r); };
    const opener = (g, o) => { const list = (openers[g] || {})[o]; return list ? list.find(r => stands(r)) || [...list].sort((a, b) => cheap(a) - cheap(b))[0] : null; };
    // A group with a mount (the guns' ports, the bombs' hatches, the nests' rings: data/crew_options.json, mount) exists from its mount's building on:
    // its empty place is the mount, not the group's start (none: no ports at all), and nothing of it can stand or be ordered without the place. A
    // group without a mount (the riflemen at the rails) has its place from the first building that opens a kind of it.
    const emptyOf = g => data.groups[g].mount || data.groups[g].start;
    const opens = (g, o) => ((openers[g] || {})[o] || []).some(r => stands(r));
    M.crew_place = g => {
        const group = data.groups[g];
        if (!group || !M.carried()) return false;          // no barge, no place for a crew on it
        if (group.mount) return opens(g, group.mount);
        return Object.keys(group.options).some(o => o !== group.start && opens(g, o));
    };
    // the building that opens a group's place: its mount's (the ports, the hatches, the rings), or the earliest of those that open a kind of it
    M.place_opener = g => {
        const group = data.groups[g];
        if (!group) return null;
        if (group.mount) return opener(g, group.mount);
        const list = Object.keys(group.options).filter(o => o !== group.start).map(o => opener(g, o)).filter(Boolean);
        return list.find(r => stands(r)) || list.sort((a, b) => cheap(a) - cheap(b))[0] || null;
    };
    const stateOf = g => crew[g] || {standing: emptyOf(g), order: null};
    const ctxOf = g => ({start: emptyOf(g), gold: game.treasury(), hire: o => (data.groups[g].options[o] || {}).hire || 0,
                         unlocked: o => o === emptyOf(g) || (M.crew_place(g) && opens(g, o))});
    M.crew = group => stateOf(group).standing;
    M.crew_order = group => (stateOf(group).order ? stateOf(group).order.option : null);
    M.crew_options = group => {
        const g = data.groups[group], ctx = ctxOf(group);
        const rank = k => { const b = opener(group, k); return b ? cheap(b) : 0; };
        const empty = emptyOf(group);
        return Object.entries(g.options).filter(([k, o]) => !o.hidden && (k === empty || opener(group, k)))
            .map(([key, o], i) => ({key, i, ...o, empty: key === empty, building: opener(group, key), unlocked: ctx.unlocked(key)}))
            .sort((a, b) => (a.empty ? -1 : b.empty ? 1 : rank(a.key) - rank(b.key) || a.i - b.i));
    };
    const upkeepOf = (g, o) => (data.groups[g].options[o] || {}).upkeep || 0;
    // gold per turn now, and with the orders of this turn (M.upkeep of the mod)
    M.crew_upkeep = () => Object.keys(data.groups).reduce((sum, g) => sum + upkeepOf(g, M.crew(g)), 0);
    M.crew_upkeep_next = () => Object.keys(data.groups).reduce((sum, g) => sum + upkeepOf(g, M.crew_order(g) || M.crew(g)), 0);
    // What a click on an option would do, without doing it (the window's line under the mouse), and what the last click did (its line after).
    // The words of a group's place (blueprint.json, crew_areas, words): where its crew stands, how it comes and goes. The riflemen's by default.
    const RIFLES = {at: 'у бортов', stand: 'Стоят у бортов', come: 'встанут к бортам', came: 'встали к бортам', leave: 'сойдут с бортов', left: 'стрелки сошли с бортов',
                    nobody: 'У бортов никого', empty_name: 'пустые борта', who: 'Стрелки'};
    M.words = {};
    M.crew_words = g => ({...RIFLES, ...(M.words[g] || {})});
    const nameOf = (g, o) => (o === emptyOf(g) ? M.crew_words(g).empty_name : `«${data.groups[g].options[o].name}»`);
    const sayResult = (g, r, done) => {
        const n = nameOf(g, r.option), start = emptyOf(g), w = M.crew_words(g);
        if (r.kind === 'locked') return {bad: true, text: `Заперто: ${n} откроет постройка «${opener(g, r.option).name}»`};
        if (r.kind === 'poor') return {bad: true, text: `Не хватает золота на ${n}: найм ${r.hire}, есть ${r.have}`};
        if (r.kind === 'kept') return {text: r.why === 'ordered' ? (r.option === start ? 'Экипаж уже сходит в начале хода' : `${n} уже в найме`) : r.option === start ? w.nobody : `${n} уже ${w.at}`};
        const back = r.back ? `, вернулось ${r.back}` : '', willBack = r.back ? `, вернётся ${r.back}` : '';
        if (r.kind === 'cancelled') return {text: done ? `Заказ на ${nameOf(g, r.option)} снят${back}` : `Снять заказ на ${nameOf(g, r.option)}${willBack}: ${w.at} остаются, кто стоит`};
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
        if (r.result.kind === 'ordered') crewChosen[group] = true;
        message = notes[group].text + '.';
        fire();
        return {ok: r.result.kind === 'ordered' || r.result.kind === 'cancelled', kind: r.result.kind};
    };
    // The hint: a place's tag glows until the player chooses a crew of that group once (as the side's hint; GAME: cm:set_saved_value('mtb_crew_chosen_<group>', true)).
    // An older save has one flag for the riflemen.
    let crewChosen = {};
    M.crew_hint = (g = 'rifles') => !crewChosen[g];
    M.crew_chosen = () => ({...crewChosen});
    M.set_crew_chosen_silently = v => { crewChosen = v === true ? {rifles: true} : v && typeof v === 'object' ? {...v} : {}; };
    M.crew_snapshot = () => JSON.parse(JSON.stringify(crew));
    M.set_crew_silently = saved => {
        for (const [g, st] of Object.entries(saved || {})) {
            if (!data.groups[g] || !st || !data.groups[g].options[st.standing]) continue;
            const order = st.order && data.groups[g].options[st.order.option] ? {option: st.order.option, paid: Number(st.order.paid) || 0} : null;
            crew[g] = {standing: st.standing, order};
        }
    };
    // a building that no longer stands takes its option away: the order with its gold, the standing crew without
    const dropLocked = () => {
        const said = [];
        for (const g of Object.keys(crew)) {
            const r = crewModel.lose(stateOf(g), ctxOf(g));
            crew[g] = r.state;
            game.gold = r.gold;
            for (const l of r.lost) said.push(l.kind === 'order' ? `заказ на ${nameOf(g, l.option)} снят, ${l.back} золота вернулось` : `${nameOf(g, l.option)} сошли с корабля, найм не возвращается`);
            if (r.lost.length) delete notes[g];
        }
        return said;
    };
    // the same for a building gone without an event the model hears (GAME: the bridge, src/tww3_mtb_crew.lua: after a load, a battle, a turn
    // start), told on the panel's line as the events tell it; true when some crew went
    M.drop_locked = () => {
        if (!data.tree_rows) return false;
        const said = dropLocked();
        if (said.length) {
            message = 'Постройки больше нет: ' + said.join('; ') + '.';
            told(true);
            fire();
        }
        return said.length > 0;
    };
    // What the ship has after a demolish of row, before it is done: the levels it takes, the crew places it closes, and what of the crew goes (the
    // same rule as dropLocked: an order whose option closes comes back with its gold, a standing crew leaves without)
    const afterDemolish = row => afterDismantles([row]);
    // the same for every dismantle of the turn at once (M.place_closing)
    const afterDismantles = rows => {
        const takes = rows.flatMap(takesOf), gone_ = takes.map(r => r.key);
        // a dismantle of one level (the page's step_down): the one below stands again
        const back = rows.map(row => { const below = belowOf(row); return takesOf(row).length === 1 && below ? below.key : null; }).filter(Boolean);
        const standsAfter = r => back.includes(r.key) || (stands(r) && !gone_.includes(r.key));
        const opensAfter = (g, o) => ((openers[g] || {})[o] || []).some(standsAfter);
        const placeAfter = g => {
            const group = data.groups[g];
            if (!group || !M.carried()) return false;
            if (group.mount) return opensAfter(g, group.mount);
            return Object.keys(group.options).some(o => o !== group.start && opensAfter(g, o));
        };
        const places = [], said = [], next = {};
        let orderBack = 0;
        for (const g of Object.keys(data.groups)) {
            const after = placeAfter(g);
            if (M.crew_place(g) && !after) places.push(g);
            const open = o => o === emptyOf(g) || (after && opensAfter(g, o));
            const st = stateOf(g);
            if (st.order && st.order.option !== emptyOf(g) && !open(st.order.option)) {
                said.push(`заказ на ${nameOf(g, st.order.option)} снимут, ${st.order.paid} золота вернётся`);
                orderBack += st.order.paid;
            }
            if (st.standing !== emptyOf(g) && !open(st.standing)) said.push(`${nameOf(g, st.standing)} сойдут с корабля, найм не вернётся`);
            // who stands there after the turn's start: the order if it stays open, else the standing crew if it does, else nobody
            next[g] = st.order && open(st.order.option) ? st.order.option : open(st.standing) ? st.standing : emptyOf(g);
        }
        return {takes, places, said, next, back: orderBack};
    };
    // A building gone at the end of the turn (GAME: the adapter tells it at Malakai's turn start, from its saved mark, before FactionTurnStart): its
    // crew goes with it, and the turn's line says so: every level that went, the crew places that closed, the crew that left
    let gone = [];          // [{names, places, said, refund}] told by the turn's line
    const goneText = () => {
        if (!gone.length) return null;
        const said = gone.flatMap(g => g.said), places = gone.flatMap(g => g.places), back = gone.reduce((s, g) => s + g.refund, 0);
        return `Снесено: ${gone.map(g => g.names).join(', ')}.` + (back > 0 ? ` За снос вернулось ${back} золота.` : '') +
            (places.length ? ` ${places.length > 1 ? 'Закрыты места экипажа' : 'Закрыто место экипажа'} ${quoted(places.map(M.place_name))}.` : '') +
            (said.length ? ' Постройки больше нет: ' + said.join('; ') + '.' : '');
    };
    game.on('BuildingDemolished', ctx => {
        const said = dropLocked();
        const row = M.level(ctx.key);
        // the places it closed: open in the ship of the turn's end, closed now
        const now = shipNow(), was = shipWas || now;
        const places = was.places.filter(g => !now.places.includes(g));
        gone.push({names: row ? namesOf(takesOf(row)) : `«${ctx.key}»`, places, said, refund: ctx.refund || 0});
        // the baseline of the turn's news loses what went, and gains nothing: the game has already put this turn's completions in their slots
        // (they are told after FactionTurnStart, run 20261115-012811), so a place they open is still news then
        shipWas = {parts: was.parts.filter(p => now.parts.includes(p)), places: was.places.filter(g => now.places.includes(g)),
                   kinds: (was.kinds || []).filter(k => now.kinds.includes(k))};
        message = goneText();
        told(false);
        fire();
    });

    // ---- What the buildings of a turn brought to the ship: the details now on the drawing, the crew places now open ----
    // news: the turn's completions {turn, built: [key], parts: [part], places: [group]}, read by the panel (the new detail glows on the small drawing
    // that turn); unseen: something new on the ship since the player last looked at «Корабль» (the tab's mark). Both kept through a reload.
    // GAME: cm:set_saved_value('mtb_ship_news', ...) at MilitaryForceBuildingCompleteEvent; the tab's mark cleared by the panel's tab click.
    // kinds: 'group:option' of every kind a place that is open can take now (a new kind in a place already open is news too: «Топоры» in the nests)
    const kindsNow = places => places.flatMap(g => M.crew_options(g).filter(o => !o.empty && o.unlocked).map(o => g + ':' + o.key));
    const shipNow = () => { const places = Object.keys(data.groups).filter(g => M.crew_place(g)); return {parts: Object.keys(parts || {}).filter(p => M.stage(p) === 'ink'), places, kinds: kindsNow(places)}; };
    let shipWas = null, news = null, unseen = false, turnLine = null;
    M.sync_ship = () => { shipWas = shipNow(); };
    M.ship_news = () => (news && news.turn === game.turn ? news : null);
    M.ship_unseen = () => unseen;
    M.ship_seen = () => { unseen = false; };
    M.news_snapshot = () => ({news, unseen});
    M.set_news_silently = s => { news = s && s.news && Array.isArray(s.news.built) ? {kinds: [], ...s.news} : null; unseen = !!(s && s.unseen); };
    // the places whose crew the turn's buildings changed: opened, or a new kind in a place that was open (the glow of the row and of the tag)
    M.news_places = () => { const n = M.ship_news(); return n ? [...new Set([...n.places, ...(n.kinds || []).map(k => k.split(':')[0])])] : []; };
    // The name of a crew place as its tag on the drawing writes it (tools/web_art.py, the tags' text)
    const TAG = {rifles: 'Стрелки', cannons: 'Орудия', bombs: 'Бомбы', cupolas: 'Гнёзда', harpoon: 'Гарпун'};
    M.place_name = g => TAG[g] || (data.groups[g] && data.groups[g].name) || g;
    const quoted = list => list.map(s => `«${s}»`).join(', ');
    // a new kind in a place already open, said as the place is spoken of (one kind or several: the same words fit both)
    const NEW_KINDS = {rifles: (l, one) => `Для стрелков теперь ${one ? 'открыт отряд' : 'открыты отряды'} ${l}.`, cannons: l => `В порты теперь можно поставить ${l}.`,
                       bombs: l => `На стеллажи над люками теперь можно положить ${l}.`, cupolas: l => `В гнёздах теперь доступны ${l}.`, harpoon: l => `На нос шара теперь можно поставить ${l}.`};
    M.new_kinds_text = (g, names) => (NEW_KINDS[g] ? NEW_KINDS[g](quoted(names), names.length === 1) : `Новое для места «${M.place_name(g)}»: ${quoted(names)}.`);
    // the foot line of the turn's news: what was built, the crew places it opened, then what the turn did to the crew (arrivals, upkeep)
    const newsText = (lost = []) => {
        const n = M.ship_news(), out = [];
        if (n && n.built.length) out.push(`Построено: ${quoted(n.built.map(k => M.level(k).name))}.`);
        if (n && n.places.length) out.push(n.places.length === 1 ? `Открыто место экипажа ${quoted(n.places.map(M.place_name))}.` : `Открыты места экипажа ${quoted(n.places.map(M.place_name))}.`);
        if (n && (n.kinds || []).length) {
            const by = {};
            for (const k of n.kinds) { const [g, o] = k.split(':'); (by[g] ||= []).push(data.groups[g].options[o].name); }
            for (const [g, names] of Object.entries(by)) out.push(M.new_kinds_text(g, names));
        }
        if (lost.length) out.push('Новый уровень этого не даёт: ' + lost.join('; ') + '.');
        if (turnLine && turnLine.turn === game.turn) out.push(turnLine.text);
        return out.join(' ') || null;
    };

    // The game's events, as the mod listens to them (core:add_listener)
    game.on('MilitaryForceBuildingCompleteEvent', ctx => {
        // GAME: here the mod's own on_building also runs (src/tww3_mtb_crew.lua): the bay appears, the hull's mount row changes
        if (!news || news.turn !== game.turn) news = {turn: game.turn, built: [], parts: [], places: [], kinds: []};
        news.kinds ||= [];
        news.built.push(ctx.building);
        // a tree's next level that does not carry on what the level below opened: that crew is no longer open
        const lost = data.tree_rows ? dropLocked() : [];
        const now = shipNow(), was = shipWas || now;
        const parts_ = now.parts.filter(p => !was.parts.includes(p)), places = now.places.filter(g => !was.places.includes(g));
        // a new kind only in a place that was open before (a place opened now is told as opened, its kinds with it)
        const kinds = now.kinds.filter(k => !(was.kinds || []).includes(k) && (was.places || []).includes(k.split(':')[0]));
        news.parts.push(...parts_.filter(p => !news.parts.includes(p)));
        news.places.push(...places.filter(g => !news.places.includes(g)));
        news.kinds.push(...kinds.filter(k => !news.kinds.includes(k) && !news.places.includes(k.split(':')[0])));
        if (parts_.length || places.length || kinds.length) unseen = true;
        shipWas = now;
        message = newsText(lost);
        told(false);
        fire();
    });
    // the ship as it was when the player ended the turn: the turn's news are told against it (a building stood by a script during the turn, which no
    // event told, is not news of the next turn)
    game.on('FactionTurnEnd', () => { shipWas = shipNow(); });
    // The one obvious first step of a fresh campaign, in the game's voice: nothing built, nothing ordered, nothing said yet
    // Nothing can be ordered and points are what is missing: what the player waits for, in the game's words (local_ru: «Численность этой орды
    // растет со временем», the horde's growth makes the surplus: GrowthThresholdForPoint, TurnsUntilNextGrowthPoint). null otherwise
    M.waiting = () => {
        const all = Object.values(levels);
        let short = false;
        for (const r of all) {
            const st = M.status(r.key);
            if (st.state === 'open') return null;
            if (st.short) short = true;
        }
        if (!short) return null;
        const g = M.growth();
        if (g && g.turns) return `Нечего заказать: не хватает ${M.POINTS}, следующая единица через ${turnsText(g.turns)}.`;
        return `Нечего заказать: не хватает ${M.POINTS}.`;
    };
    // The part of the foot line that tells the player what to wait for (M.waiting, at the line's end): the panel never cuts it, it gets a line of its
    // own when the whole does not fit (run 20261115-030121, ss_after_turn: «…Нечего заказать: не хватает…» cut). '' when the line has none
    M.foot_tail = () => {
        const msg = M.message() || M.first_step() || '', w = M.waiting();
        return w && msg.endsWith(w) ? w : '';
    };
    // A crew place that a dismantle ordered this turn closes at the turn's end (it stays open till then): the «Экипаж» row's grey note (M.CLOSING)
    // and the place's tag say so for the whole turn, not only the foot line until the next message. '' when the place stays
    M.CLOSING = 'Закроется в конце хода';
    const goingTops = () => {
        const tops = [];
        for (const r of Object.values(levels)) if (game.has_building(r.key) && going(r)) { const t = goingTop(r); if (!tops.includes(t)) tops.push(t); }
        return tops;
    };
    M.place_closing = g => {
        const tops = goingTops();
        if (!tops.length || !afterDismantles(tops).places.includes(g)) return '';
        return `${M.CLOSING}: снос ${namesOf(tops.flatMap(takesOf))}.`;
    };
    // What the game gives back for a dismantle of a level when the building goes at the turn's end (GAME: the adapter reads the slot's
    // DismantleRefundAmount; the data's rule: campaign_variables building_dismantle_recoup_multiplier_when_full_health 0.6 of the level's
    // create_cost; run 20261115-065150: +600 for «Манекен для учебной стрельбы» of 1000). 0 when the game says nothing of it
    M.refund = key => { const row = M.level(key); return row && game.dismantle_refund ? game.dismantle_refund(row.key) || 0 : 0; };
    // What the turn's end does to the treasury besides the faction's own income, as the game and this model will do it: the gold the dismantles
    // give back, the orders a dismantle cancels (their hire back), the crew's upkeep at the turn's start (the crew after the dismantles). The
    // treasury's tooltip. {refund, back, upkeep, net}
    M.turn_gold = () => {
        const tops = goingTops();
        const fx = afterDismantles(tops);
        const refund = tops.reduce((s, r) => s + M.refund(r.key), 0);
        const pays = game.crew_pays === undefined || game.crew_pays();
        const upkeep = !pays ? 0 : tops.length ? Object.keys(data.groups).reduce((s, g) => s + upkeepOf(g, fx.next[g]), 0) : M.crew_upkeep_next();
        return {refund, back: fx.back, upkeep, net: refund + fx.back - upkeep};
    };
    // The game's own moments the panel gives way to, as the game's full-screen panels do (GAME: the adapter's blocker(): another faction's turn,
    // a battle pending or being fought, a dilemma waiting for its answer, an event message, a panel or a window of the game on the screen; the
    // page's game: its modal, set by the vectors): the panel cannot be opened then and closes itself when one comes. The reasons in the game's
    // words where it has them (local_ru: campaign_localised_strings_string_MPC_cannot_construct_not_your_turn, rituals_ritual_status_blocked_pending_battle)
    M.BLOCKED = {turn: 'Недоступно во время хода другой фракции.', battle: 'Недоступно, пока ведется битва.', dilemma: 'Сначала примите решение по дилемме.',
                 event: 'Сначала закройте сообщение о событии.', panel: 'Сначала закройте окно игры.', dialog: 'Сначала ответьте в окне игры.'};
    M.can_open = () => {
        const kind = game.blocker ? game.blocker() : null;
        return kind ? {ok: false, kind, why: M.BLOCKED[kind] || M.BLOCKED.panel} : {ok: true};
    };
    M.first_step = () => {
        if (message) return null;
        const all = Object.values(levels);
        if (all.some(r => game.has_building(r.key) || game.under_construction(r.key) !== null)) return M.waiting();
        const first = all.find(r => !M.missing(r.key).length);
        if (!first) return null;
        return M.status(first.key).state === 'open' ? `Закажите первую постройку — «${first.name}».` : `Первая постройка — «${first.name}». ${M.reason(first.key)}`;
    };
    game.on('FactionTurnStart', () => {
        // the orders go in (M.carry_out), then the upkeep of what stands now is taken (M.pay_upkeep)
        const came = [];
        for (const g of Object.keys(crew)) {
            if (!crew[g].order) continue;
            crew[g] = crewModel.turn(crew[g]);
            delete notes[g];
            came.push(crew[g].standing === emptyOf(g) ? M.crew_words(g).left : `${nameOf(g, crew[g].standing)} ${M.crew_words(g).came}`);
        }
        // no upkeep while the crew cannot serve (GAME: the adapter's crew_pays, Malakai on foot, the places not written; the page's game has none)
        const upkeep = (game.crew_pays === undefined || game.crew_pays()) ? M.crew_upkeep() : 0;
        game.gold -= upkeep;        // GAME: cm:treasury_mod; the page lets the treasury go below zero
        let crewLine = [came.length ? came.join('; ') : '', upkeep ? `содержание экипажа: ${upkeep} золота` : ''].filter(Boolean).join(', ');
        crewLine = crewLine ? crewLine[0].toUpperCase() + crewLine.slice(1) + '.' : null;
        message = [goneText(), crewLine, M.waiting()].filter(Boolean).join(' ') || null;
        gone = [];
        turnLine = message ? {turn: game.turn, text: message} : null;
        told(false);
        fire();
    });
    M.sync_ship();
    return M;
}

export function turnsText(n) {
    const m10 = n % 10, m100 = n % 100;
    const word = m10 === 1 && m100 !== 11 ? 'ход' : (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) ? 'хода' : 'ходов';
    return `${n} ${word}`;
}
