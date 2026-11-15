// The page's logic as a whole, without a browser: buildings + crew + treasury + turn (web/js/game_sim.js, barge_buildings.js, crew_model.mjs) over the
// exported data (build/web/data.json: run tools/web_export.py --data first).
//   node tools/tests/page_logic_test.mjs      (from the repository's root; web/js/package.json marks the page's scripts as ES modules for node)
// A ledger is kept beside the game: after every step the treasury must be the ledger's sum. Prints a line a check, exit 1 on any failure.
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {GameSim} from '../../web/js/game_sim.js';
import {makeBuildings} from '../../web/js/barge_buildings.js';
import * as T from '../../web/js/tree_model.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const json = p => JSON.parse(readFileSync(join(root, p), 'utf-8'));
const data = json('build/web/data.json'), sim = json('web/data/sim.json'), blueprint = json('web/data/blueprint.json');
const stage = blueprint.stages[blueprint.stage];
let failed = 0;
const check = (name, ok, extra = '') => { if (!ok) failed++; console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok ? '' : '  ' + extra)); };

function fresh(gold = 6000) {
    const game = new GameSim(data, {...sim, dev_points: 1000, gold, built: stage.built || sim.built, demolish: stage.demolish_mode});
    const M = makeBuildings(data, game, stage.parts);
    for (const [k, needs] of Object.entries(stage.tree.requires || {})) M.extra_requires[data.prefix + k] = needs.map(n => data.prefix + n);
    return {game, M, P: data.prefix};
}
const opt = k => data.groups.rifles.options[k];
const cost = (M, k) => M.level(k).cost;

// 1. the long way: the hull, the beer hall, pirates, the dummies, crossbows, with a change of mind and a reload in the middle
{
    const {game, M, P} = fresh();
    let ledger = 6000;
    const same = step => check(`${step}: treasury ${game.treasury()} = ledger ${ledger}`, game.treasury() === ledger);
    const build = short => { const r = M.order(P + short); if (r.ok) ledger -= cost(M, short); game.end_turn(); ledger -= M.crew_upkeep(); return r.ok; };
    check('beer hall locked before the hull', M.status(P + 'beer_hall_1').state === 'locked');
    check('crew: pirates locked before the beer hall', M.set_crew('rifles', 'pirates').kind === 'locked');
    same('nothing done');
    check('hull 1 built', build('airship_hull_1') && M.status(P + 'airship_hull_1').state === 'built');
    check('hull 2 built', build('airship_hull_2'));
    check('dummies locked before the beer hall', M.status(P + 'crew_weapons_1').state === 'locked');
    check('beer hall built', build('beer_hall_1'));
    same('after three buildings');
    check('order pirates', M.set_crew('rifles', 'pirates').kind === 'ordered'); ledger -= opt('pirates').hire; same('pirates ordered');
    check('crossbows still locked', M.set_crew('rifles', 'quarrellers').kind === 'locked'); same('a locked click');
    check('nobody stands before the turn', M.crew('rifles') === 'empty' && M.crew_order('rifles') === 'pirates' && M.crew_upkeep() === 0 && M.crew_upkeep_next() === opt('pirates').upkeep);
    game.end_turn(); ledger -= opt('pirates').upkeep;
    check('pirates stand after the turn, upkeep taken', M.crew('rifles') === 'pirates' && M.crew_order('rifles') === null); same('turn with pirates');
    check('dummies built', build('crew_weapons_1')); same('dummies');
    check('order crossbows', M.set_crew('rifles', 'quarrellers').kind === 'ordered'); ledger -= opt('quarrellers').hire; same('crossbows ordered');
    check('change of mind: back to pirates takes the order back', M.set_crew('rifles', 'pirates').kind === 'cancelled'); ledger += opt('quarrellers').hire; same('order taken back');
    check('and crossbows again, the same turn', M.set_crew('rifles', 'quarrellers').kind === 'ordered'); ledger -= opt('quarrellers').hire; same('crossbows again');
    // a reload in the middle: the same game from the saved data
    const saved = JSON.parse(JSON.stringify({...game.snapshot(), crew: M.crew_snapshot()}));
    const again = fresh();
    again.game.restore(saved); again.M.set_crew_silently(saved.crew);
    check('reload mid-order: the same state and treasury', again.M.crew('rifles') === 'pirates' && again.M.crew_order('rifles') === 'quarrellers' && again.game.treasury() === ledger);
    again.game.end_turn();
    check('reload, then the turn: crossbows stand', again.M.crew('rifles') === 'quarrellers' && again.game.treasury() === ledger - opt('quarrellers').upkeep);
    game.end_turn(); ledger -= opt('quarrellers').upkeep;
    check('crossbows stand after the turn', M.crew('rifles') === 'quarrellers'); same('turn with crossbows');
    // demolish: the beer hall is held by the dummies; the dummies take the crossbows with them, for nothing
    check('the beer hall cannot go while the dummies need it', !M.can_demolish(P + 'beer_hall_1').ok);
    check('order pirates before the demolition', M.set_crew('rifles', 'pirates').kind === 'ordered'); ledger -= opt('pirates').hire;
    check('dummies: the demolish is ordered, they stand until the turn ends', M.demolish(P + 'crew_weapons_1').ok && M.status(P + 'crew_weapons_1').state === 'dismantling' && M.crew('rifles') === 'quarrellers');
    check('dummies: a second click says why nothing more happens', M.reason(P + 'crew_weapons_1') === `Сносится: «${M.level(P + 'crew_weapons_1').name}» уйдёт в конце хода.` && !M.can_demolish(P + 'crew_weapons_1').ok, M.reason(P + 'crew_weapons_1'));
    check('the beer hall still cannot go: the dummies stand on it until the turn ends', !M.can_demolish(P + 'beer_hall_1').ok);
    game.end_turn(); ledger -= opt('pirates').upkeep;
    check('the turn ended: the dummies gone, the crossbows left for nothing, the pirates came', M.status(P + 'crew_weapons_1').state !== 'built' && M.crew('rifles') === 'pirates' && /^Снесено: «/.test(M.message()), M.message()); same('dummies demolished');
    check('beer hall: the demolish is ordered', M.demolish(P + 'beer_hall_1').ok);
    game.end_turn();
    check('beer hall demolished: the pirates leave for nothing', M.crew('rifles') === 'empty' && !game.has_building(P + 'beer_hall_1')); same('beer hall demolished');
    game.end_turn();
    check('nothing more is taken with nobody aboard', game.treasury() === ledger);
}
// 2. a building cancelled, a treasury in debt
{
    const {game, M, P} = fresh(6000);
    M.debug_build_to(P + 'crew_weapons_1');
    check('debug build costs nothing', game.treasury() === 6000 && M.status(P + 'crew_weapons_1').state === 'built');
    M.set_crew('rifles', 'pirates'); game.end_turn();
    check('pirates stand', M.crew('rifles') === 'pirates' && game.treasury() === 6000 - opt('pirates').hire - opt('pirates').upkeep);
    game.gold = 10;
    game.end_turn();
    check('the upkeep takes the treasury below zero, as the game allows', game.treasury() === 10 - opt('pirates').upkeep);
    check('in debt: no hire', M.set_crew('rifles', 'quarrellers').kind === 'poor' && M.crew_order('rifles') === null);
    check('in debt: taking the crew off is free and allowed', M.set_crew('rifles', 'empty').kind === 'ordered');
    game.end_turn();
    check('the crew left, nothing more taken', M.crew('rifles') === 'empty' && game.treasury() === 10 - opt('pirates').upkeep);
    game.gold = 5000;
    const before = game.treasury();
    check('order and cancel a building returns its price', M.order(P + 'crew_weapons_2').ok === (M.status(P + 'crew_weapons_2').state === 'building') && (M.cancel(P + 'crew_weapons_2'), game.treasury() === before));
}
// 3. every count of riflemen is 11, every hire and upkeep a multiple of ten
{
    const kinds = Object.entries(data.groups.rifles.options).filter(([, o]) => o.unit_card && !o.hidden);
    check('all the rifle crews count 11', kinds.every(([, o]) => o.unit_card.men === 11), kinds.map(([k, o]) => k + ':' + o.unit_card.men).join(' '));
    check('hire and upkeep are multiples of ten', kinds.every(([, o]) => o.hire % 10 === 0 && o.upkeep % 10 === 0));
    check('every kind has its weapon numbers', kinds.every(([, o]) => o.numbers && o.numbers.range > 0 && o.numbers.ammo > 0));
}
// 4. the tree of the constructor's file (tree_model.mjs gameData) on the four start nodes (tools/tests/tree_design_start.json), then a tree with a node of two parents,
// new buildings that the mod does not have, and a crew opened by a node of the file
{
    const start = T.normalize(json('tools/tests/tree_design_start.json')).design;      // the four start nodes, not the author's working file
    const gd = T.gameData(start, data);
    const game = new GameSim(gd, {...sim, dev_points: 1000, gold: 6000, built: [], demolish: stage.demolish_mode});
    const M = makeBuildings(gd, game, stage.parts);
    const P = data.prefix;
    check('file: the beer hall needs the hull 2 (tier and link)', M.status(P + 'beer_hall_1').state === 'locked');
    M.debug_build_to(P + 'crew_weapons_1');
    check('file: built up to the dummies, the parts of the drawing found by key', M.stage('pub') === 'ink' && M.stage('barge') === 'ink' && M.stage('frame') === 'ink');
    check('file: the dummies open the crossbows', M.set_crew('rifles', 'quarrellers').kind === 'ordered');

    const d = T.normalize(start).design;
    const hall = d.nodes.find(n => n.mod_key === 'beer_hall_1').id, hull2 = d.nodes.find(n => n.mod_key === 'airship_hull_2').id;
    const a = T.addNode(d, {name: 'Кузня', cost: 1000, turns: 2, col: 3, row: 2, crew: []});
    const b = T.addNode(d, {name: 'Пороховой склад', cost: 800, turns: 1, col: 1, row: 4, crew: [{group: 'rifles', option: 'thunderers'}]});
    T.addEdge(d, hull2, a); T.addEdge(d, hall, b); T.addEdge(d, a, b);
    const g2 = T.gameData(d, data);
    const game2 = new GameSim(g2, {...sim, dev_points: 1000, gold: 20000, built: [], demolish: stage.demolish_mode});
    const M2 = makeBuildings(g2, game2, stage.parts);
    const K = id => g2.key_of[id];
    let ledger = 20000;
    const build = id => { const r = M2.order(K(id)); if (r.ok) ledger -= M2.level(K(id)).cost; for (let i = 0; i < M2.level(K(id)).turns; i++) game2.end_turn(); return r.ok; };
    for (const id of [d.nodes[0].id, hull2]) build(id);
    const s0 = M2.status(K(b));
    check('two parents: locked while both are missing, both named', s0.state === 'locked' && /Кузня/.test(s0.why) && /Пивной/.test(s0.why), s0.why);
    check('a new building (not in the mod) can be ordered', M2.status(K(a)).state === 'open' && build(a) && M2.status(K(a)).state === 'built');
    const s1 = M2.status(K(b));
    check('two parents: one stands, the other is named', s1.state === 'locked' && /Пивной/.test(s1.why) && !/Кузня/.test(s1.why), s1.why);
    check('thunderers locked before the node that opens them', M2.set_crew('rifles', 'thunderers').kind === 'locked');
    check('beer hall built', build(hall));
    check('two parents: open once both stand', M2.status(K(b)).state === 'open');
    check('order, cancel gives the price back', M2.order(K(b)).ok && M2.cancel(K(b)).ok && game2.treasury() === ledger);
    game2.gold = 100;
    check('short of gold: locked with the price', M2.status(K(b)).state === 'locked' && M2.status(K(b)).poor);
    game2.gold = ledger;
    check('the two-parent node built', build(b) && M2.status(K(b)).state === 'built');
    check('a crew opened by a node of the file', M2.set_crew('rifles', 'thunderers').kind === 'ordered');
    check('a parent cannot go while the child stands', !M2.can_demolish(K(a)).ok && !M2.can_demolish(K(hall)).ok);
    check('the child demolished; the parent waits for the turn\'s end', M2.demolish(K(b)).ok && !M2.can_demolish(K(a)).ok);
    game2.end_turn();
    check('then the parent', M2.demolish(K(a)).ok);
    game2.end_turn();
    check('the order of the crew came back with the child gone', M2.crew_order('rifles') === null);
    check('treasury matches the ledger', game2.treasury() === ledger, `${game2.treasury()} vs ${ledger}`);
}
// the constructor's tree in the game: a detail of the ship shows with the node that brings it; the crew's bonus of a node acts once it stands
{
    const {crewSources} = await import('../../web/js/crew_model.mjs');
    const FX = await import('../../web/js/effects_model.mjs');
    const start = T.normalize(json('tools/tests/tree_design_start.json')).design;
    const d = JSON.parse(JSON.stringify(start));
    const hull2 = d.nodes.find(n => n.mod_key === 'airship_hull_2');
    const nid = T.addNode(d, {name: 'Гнёзда с дозорными', cost: 300, turns: 1, col: 5, row: 2, requires: [hull2.id],
        effects: [{kind: 'ammo', target: 'rifles', value: 25, text: 'Боезапас стрелков: +25 %', icon: null, good: true}],
        units: ['wh_main_dwf_art_cannon'], parts: [{part: 'pub'}, {part: null, name: 'Дозорные', zone: 'balloon', what: 'figures', figures: 2, note: ''}]});
    const levels = T.gameData(d, data);
    const parts = {...stage.parts, pub: {...stage.parts.pub, building: null}};
    const game = new GameSim(levels, {...sim, dev_points: 1000, gold: 50000, built: []});
    const M = makeBuildings(levels, game, parts);
    const key = levels.key_of[nid];
    check('no barge yet: the detail is not on the drawing at all, not even in pencil', M.stage('pub') === 'none');
    for (const n of ['airship_hull_1', 'airship_hull_2']) { M.order(data.prefix + n); game.end_turn(); }
    check('the barge stands: the detail waits in pencil while its node does not stand', M.stage('pub') === 'pencil');
    M.order(key);
    check('the detail is being built with its node', M.stage('pub') === 'build');
    const before = FX.crewBonuses(crewSources(levels, k => game.has_building(k), k => game.standing(k)), 'rifles').ammo.pct;
    game.end_turn();
    check('the detail stands with its node', M.stage('pub') === 'ink');
    const after = FX.crewBonuses(crewSources(levels, k => game.has_building(k), k => game.standing(k)), 'rifles');
    check('the node\'s ammo of the riflemen acts once it stands: 0 -> +25 %', before === 0 && after.ammo.pct === 25 && after.ammo.from[0].name === 'Гнёзда с дозорными');
    check('the level carries the army unit it opens', levels.tree_rows.find(r => r.key === key).units[0] === 'wh_main_dwf_art_cannon');
    M.demolish(key);
    game.end_turn();
    check('demolished: the detail goes, the bonus goes', M.stage('pub') === 'pencil' && FX.crewBonuses(crewSources(levels, k => game.has_building(k), k => game.standing(k)), 'rifles').ammo.pct === 0);
}
// the lines of levels in the game: the level that stands acts with its whole set, the levels are not added up; demolished, the one below acts again;
// a next level that does not inherit closes what the level below opened
{
    const {crewSources} = await import('../../web/js/crew_model.mjs');
    const FX = await import('../../web/js/effects_model.mjs');
    const make = (inherit, hide = []) => {
        const d = JSON.parse(JSON.stringify(T.normalize(json('tools/tests/tree_design_start.json')).design));
        const hull2 = d.nodes.find(n => n.mod_key === 'airship_hull_2');
        const one = T.addNode(d, {name: 'Чертог I', cost: 100, col: 6, row: 2, requires: [hull2.id], crew: [{group: 'rifles', option: 'pirates'}],
            effects: [{kind: 'ammo', target: 'rifles', value: 10, text: 'Боезапас стрелков: +10 %', icon: null, good: true}]});
        const two = T.addNode(d, {name: 'Чертог II', cost: 100, col: 6, row: 3, requires: [one], prev: one, inherit, hide,
            effects: [{kind: 'ammo', target: 'rifles', value: 25, text: 'Боезапас стрелков: +25 %', icon: null, good: true}]});
        const levels = T.gameData(d, data);
        const game = new GameSim(levels, {...sim, dev_points: 1000, gold: 50000, built: [], demolish: 'step_down'});
        const M = makeBuildings(levels, game, stage.parts);
        for (const k of ['airship_hull_1', 'airship_hull_2']) { M.order(data.prefix + k); game.end_turn(); }
        return {game, M, levels, k1: levels.key_of[one], k2: levels.key_of[two]};
    };
    const ammo = ({levels, game}) => FX.crewBonuses(crewSources(levels, k => game.has_building(k), k => game.standing(k)), 'rifles').ammo.pct;
    const pirates = M => M.crew_options('rifles').find(o => o.key === 'pirates');
    let w = make(true);
    w.M.order(w.k1); w.game.end_turn();
    check('lines in the game: I built: +10 %, the pirates open', ammo(w) === 10 && pirates(w.M).unlocked);
    w.M.set_crew('rifles', 'pirates'); w.game.end_turn();
    check('lines in the game: II waits for I: ordered only after I', w.M.status(w.k2).state === 'open');
    w.M.order(w.k2); w.game.end_turn();
    check('lines in the game: I and II built: II\'s set acts, +25 % (not 35); the pirates of I open with II', ammo(w) === 25 && pirates(w.M).unlocked && w.M.crew('rifles') === 'pirates' && w.game.standing(w.k2) && !w.game.standing(w.k1));
    w.M.demolish(w.k2); w.game.end_turn();
    check('lines in the game: II demolished: I stands and acts again, +10 %', ammo(w) === 10 && w.game.standing(w.k1));
    w = make(false);
    w.M.order(w.k1); w.game.end_turn(); w.M.set_crew('rifles', 'pirates'); w.game.end_turn();
    w.M.order(w.k2); w.game.end_turn();
    check('lines in the game: a II that does not inherit the lines: +25 % only, and the pirates of I stay open and at the rails (what is opened is never taken back)', ammo(w) === 25 && pirates(w.M).unlocked && w.M.crew('rifles') === 'pirates', w.M.message());
    w = make(false, ['crew:rifles:pirates']);
    w.M.order(w.k1); w.game.end_turn(); w.M.set_crew('rifles', 'pirates'); w.game.end_turn();
    w.M.order(w.k2); w.game.end_turn();
    check('lines in the game: «убрать на этом уровне» the pirates on II: closed with II, gone from the rails', !pirates(w.M).unlocked && w.M.crew('rifles') !== 'pirates', w.M.message());
    w.M.demolish(w.k2); w.game.end_turn();
    check('lines in the game: II with them taken away demolished: I opens the pirates again', pirates(w.M).unlocked);
}
// the game's own rules the panel must follow (run 20261114-230723): the development points a level costs, the dismantle that stands until the turn
// ends, the hull that is never dismantled, the game's window before a cancel of an earlier turn's construction, the news against the ship of the
// turn's end
{
    const P = data.prefix;
    const make = (extra = {}) => {
        const game = new GameSim(data, {...sim, gold: 50000, built: ['airship_hull_1', 'airship_hull_2'], demolish: 'chain', ...extra});
        return {game, M: makeBuildings(data, game, stage.parts)};
    };
    const hall = P + 'beer_hall_1';
    // the horde's growth as the game counts it: 20 a point (campaign_variables); this data (no tree) has no «Рост орды» of its buildings: 20 of
    // the horde's own a turn
    let {game, M} = make({dev_points: 0, growth_base: 20, growth_threshold: 20});
    const need = M.dev(hall);
    check('points: a first level costs its points (data)', need > 0, need);
    const st = M.status(hall);
    check('points: none at the start of a campaign: locked, short, the game\'s words', st.state === 'locked' && st.short && st.why === `Не хватает избытка населения: нужно ${need}` && M.reason(hall) === `Не хватает избытка населения: нужно ${need}, есть 0.`, M.reason(hall));
    check('points: the game refuses the order itself (the command answers, nothing happens)', (game.issue_building_command(hall), game.under_construction(hall) === null && game.treasury() === 50000));
    check('points: nothing to order, the foot says what the player waits for', M.waiting() === 'Нечего заказать: не хватает избытка населения, следующая единица через 1 ход.' && M.first_step() === M.waiting(), M.waiting());
    check('points: the growth as the game shows it', JSON.stringify(M.growth()) === JSON.stringify({now: 0, per_turn: 20, need: 20, turns: 1, max: false}), M.growth());
    for (let i = 0; i < need; i++) game.end_turn();
    check('points: the growth of the turns brings them, then the order goes in', M.status(hall).state === 'open' && M.order(hall).ok && game.development_points() === 0, M.status(hall));
    check('points: the order says the points', / и \d+ ед\. избытка населения, готово через /.test(M.message()), M.message());
    check('points: a cancel of this turn gives the points back with the gold', M.cancel(hall).ok && game.development_points() === need && game.treasury() === 50000 && /золото и избыток населения вернулись/.test(M.message()), M.message());
    check('points: a level above the first costs none', M.dev(P + 'beer_hall_2') === 0);
    // the hull
    check('the hull is never dismantled: the panel says so, the game refuses', !M.can_demolish(P + 'airship_hull_2').ok && M.can_demolish(P + 'airship_hull_2').why === 'Корпус не сносится: на нём держится весь корабль' && !game.dismantle(P + 'airship_hull_2'));
    // the dismantle
    ({game, M} = make({dev_points: 100}));
    M.debug_build_to(P + 'crew_weapons_1');
    const before = game.treasury();
    check('dismantle: before it, the preview names what goes and the crew place it closes', M.demolish_preview(P + 'crew_weapons_1') === `Снос: «${M.level(P + 'crew_weapons_1').name}» уйдёт в конце хода. Закроется место экипажа «Стрелки».`, M.demolish_preview(P + 'crew_weapons_1'));
    check('dismantle: ordered, said so', M.demolish(P + 'crew_weapons_1').ok && M.message() === `Снос заказан: «${M.level(P + 'crew_weapons_1').name}» уйдёт в конце хода. Закроется место экипажа «Стрелки».`, M.message());
    check('dismantle: it stands until the turn ends, being dismantled', game.standing(P + 'crew_weapons_1') && M.status(P + 'crew_weapons_1').state === 'dismantling' && M.can_demolish(P + 'crew_weapons_1').why === 'Уже сносится: постройка уйдёт в конце хода');
    check('dismantle: the level above it cannot be ordered meanwhile', M.status(P + 'crew_weapons_2').state === 'locked', M.status(P + 'crew_weapons_2').why);
    const dependant = Object.values(M.level ? data.chains.flatMap(c => c.levels) : []).find(l => (l.requires || []).includes(P + 'crew_weapons_1') && !M.missing(l.key).length);
    if (dependant) check('dismantle: what needs it waits, named', M.status(dependant.key).why === `«${M.level(P + 'crew_weapons_1').name}» сносится: уйдёт в конце хода`, M.status(dependant.key).why);
    game.end_turn();
    check('dismantle: gone at the turn\'s start, said in the turn\'s line, no gold back', !game.has_building(P + 'crew_weapons_1') && game.treasury() === before && M.message().startsWith(`Снесено: «${M.level(P + 'crew_weapons_1').name}».`), M.message());
    // a construction under way in the slot: cancel it first
    ({game, M} = make({dev_points: 100}));
    M.debug_build_to(P + 'airship_hull_5');
    for (const k of M.needs_all(P + 'beer_hall_2')) if (k !== P + 'beer_hall_2') game.debug_complete(k);
    M.order(P + 'beer_hall_2');
    check('dismantle: not while a level of its line is being built there', !M.can_demolish(P + 'beer_hall_1').ok && /^Сначала отмените стройку «/.test(M.can_demolish(P + 'beer_hall_1').why), M.can_demolish(P + 'beer_hall_1').why);
    // the game's window before the cancel of an earlier turn's construction
    ({game, M} = make({dev_points: 100, ask_cancel: true}));
    M.debug_build_to(P + 'airship_hull_5');
    const long = data.chains.flatMap(c => c.levels).find(l => l.turns >= 2 && l.level === 0);
    if (long) for (const k of M.needs_all(long.key)) if (k !== long.key) game.debug_complete(k);
    check('cancel window: a building of two turns is open', !!long);
    if (long) {
        M.order(long.key); game.end_turn();
        const gold = game.treasury();
        const r = M.cancel(long.key);
        check('cancel window: the game asks; the panel waits and says where to answer', !r.ok && M.status(long.key).state === 'building' && M.status(long.key).asked && M.message() === `Отмена «${long.name}»: ответьте в окне игры.` && game.treasury() === gold, M.message());
        check('cancel window: a second click while it waits changes nothing', !M.cancel(long.key).ok && game.cancel_asked(long.key));
        game.answer_cancel(false);
        check('cancel window: answered no: the construction goes on, said so', M.status(long.key).state === 'building' && !M.status(long.key).asked && /продолжается: отмену не подтвердили/.test(M.message()), M.message());
        M.cancel(long.key); game.answer_cancel(true);
        check('cancel window: answered yes: cancelled, the gold back', M.status(long.key).state === 'open' && game.treasury() === gold + long.cost && /^Отменено: «/.test(M.message()), M.message());
    }
    // the news against the ship of the turn's end: a building stood by a script during the turn is no news of the next turn
    ({game, M} = make({dev_points: 100}));
    M.debug_build_to(P + 'beer_hall_1');
    game.built.add(P + 'crew_weapons_1');            // a script's add: no event
    game.end_turn();
    check('news: the script-stood building is not the next turn\'s news', !M.ship_news() && !M.ship_unseen() || !(M.ship_news() || {places: []}).places.includes('rifles'), JSON.stringify(M.ship_news()));
}
// a command the game applies a moment later: from the click until its verdict the foot line says the command waits, never the last verdict
// (run 20261115-030121: «Отменено: …» stood under a fresh order twice)
{
    const game = new GameSim(data, {...sim, dev_points: 1000, gold: 100000, built: stage.built || sim.built, demolish: stage.demolish_mode, async: true});
    const M = makeBuildings(data, game, stage.parts);
    const P = data.prefix, k = P + 'airship_hull_1', name = M.level(k).name;
    const said = [];
    M.order(k); said.push(M.message()); game.tick(); said.push(M.message());
    M.cancel(k); said.push(M.message()); game.tick(); said.push(M.message());
    M.order(k); said.push(M.message());
    check('a waiting order or cancel: the foot line says it waits from the click on, then the verdict replaces it',
        said[0] === `Заказ «${name}» отправлен, ждём ответа игры.` && /^Заказано: /.test(said[1]) && said[2] === `Отмена «${name}» отправлена, ждём ответа игры.`
        && /^Отменено: /.test(said[3]) && said[4] === `Заказ «${name}» отправлен, ждём ответа игры.`, JSON.stringify(said));
}

console.log(failed ? `failed: ${failed}` : 'failed: 0');
process.exit(failed ? 1 : 0);
