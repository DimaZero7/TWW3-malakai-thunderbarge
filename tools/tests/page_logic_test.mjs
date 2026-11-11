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
    const game = new GameSim(data, {...sim, gold, built: stage.built || sim.built, demolish: stage.demolish_mode});
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
    check('dummies demolished', M.demolish(P + 'crew_weapons_1').ok);
    check('crossbows left, the order for pirates stays', M.crew('rifles') === 'empty' && M.crew_order('rifles') === 'pirates'); same('dummies demolished');
    check('beer hall demolished', M.demolish(P + 'beer_hall_1').ok); ledger += opt('pirates').hire;
    check('the order for pirates came back with its gold', M.crew_order('rifles') === null && M.crew('rifles') === 'empty'); same('beer hall demolished');
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
    const game = new GameSim(gd, {...sim, gold: 6000, built: [], demolish: stage.demolish_mode});
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
    const game2 = new GameSim(g2, {...sim, gold: 20000, built: [], demolish: stage.demolish_mode});
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
    check('the child demolished, then the parent', M2.demolish(K(b)).ok && M2.demolish(K(a)).ok);
    check('the order of the crew came back with the child gone', M2.crew_order('rifles') === null);
    check('treasury matches the ledger', game2.treasury() === ledger, `${game2.treasury()} vs ${ledger}`);
}
console.log(failed ? `failed: ${failed}` : 'failed: 0');
process.exit(failed ? 1 : 0);
