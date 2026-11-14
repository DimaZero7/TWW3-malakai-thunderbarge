// The page's logic as test vectors for its Lua port (docs/design/port-to-game.md, 4.2): node tools/tests/vectors_export.mjs
//
// Runs scenarios over the page's models (web/js/barge_buildings.js, crew_model.mjs, game_sim.js) and writes build/vectors/*.json: each step an
// action and the full observable answers after it (every building's status, reason and demolish answer; the foot line and the first step; the ship's
// news and the tab's mark; every crew group's standing, order, place, hint, last note, options, the preview of every option, the bonuses of its
// shooting and the ammunition of every kind with its line; the treasury, the upkeep; the stage of every part of the drawing; Malakai's side; the
// panel's tab and scroll through a reload). tools/lua_vectors.py replays them on the Lua of the pack and compares every answer.
//
// Scenarios: the paths of tools/tests/page_logic_test.mjs, panel_rules_test.mjs, crew_model_test.mjs, crew_groups_test.mjs, then 200 seeded random
// walks of 60 steps. The author's tree in the mod's keys (tools/ship_config.mjs: the same data tools/build.py packs for the Lua); the tests' own small
// trees carry their config in the vector. A step stores only the answers that changed (the replay keeps the whole state and compares all of it).
// Deterministic: the same files on every run. Needs build/web/data.json (tools/web_export.py --data) and build/tree (py -3.14 tools/build.py).

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {GameSim} from '../../web/js/game_sim.js';
import {makeBuildings, turnsText} from '../../web/js/barge_buildings.js';
import * as C from '../../web/js/crew_model.mjs';
import * as FX from '../../web/js/effects_model.mjs';
import * as T from '../../web/js/tree_model.mjs';
import {REPO, readJson, inputs, pageLevels, rekey, luaConfig} from '../ship_config.mjs';

const OUT = path.join(REPO, 'build', 'vectors');
const WALKS = 200, WALK_STEPS = 60, WALKS_PER_FILE = 25;
const inp = inputs();
const sim0 = readJson('web/data/sim.json');
const author = rekey(pageLevels(inp), inp.treeRows);
const authorConfig = luaConfig(author);
const stage = author.stage;
const prefix = authorConfig.prefix;

// ---- a world: the page's game and model over one config ----
// spec: {page: {levels, parts, words, per}, config, sim, keyName?: page key -> the name the answers use, keyOf?: the answers' key -> the page's}
function makeWorld(spec) {
    const w = {spec, view: {tab: null, scroll: null}};
    w.game = new GameSim(spec.page.levels, spec.sim);
    w.M = makeBuildings(spec.page.levels, w.game, spec.page.parts);
    for (const [g, words] of Object.entries(spec.page.words || {})) w.M.words[g] = words;
    return w;
}
const nameOfKey = (w, k) => { const n = w.spec.keyName ? w.spec.keyName(k) : k; return n.startsWith(prefix) ? n.slice(prefix.length) : n; };
const keyIn = (w, k) => (w.spec.keyOf ? w.spec.keyOf(k) : k);
const num = v => String(v);

// the answers after a step: a flat map field -> string | number | boolean | null
function observe(w) {
    const {M, game} = w, {levels, per} = w.spec.page, config = w.spec.config, o = {};
    const sk = k => nameOfKey(w, k);
    o.turn = game.turn;
    o.treasury = game.treasury();
    o.message = M.message();
    o.first_step = M.first_step();
    o.upkeep = M.crew_upkeep();
    o.upkeep_next = M.crew_upkeep_next();
    o.side = M.malakai_side();
    o.side_hint = M.side_hint();
    o.unseen = M.ship_unseen();
    const n = M.ship_news();
    o.news = n ? [n.built.map(sk).join(','), n.parts.join(','), n.places.join(','), (n.kinds || []).join(',')].join(' | ') : null;
    o.news_places = M.news_places().join(',');
    o.carried = M.carried();
    o['view.tab'] = w.view.tab;
    o['view.scroll'] = w.view.scroll ? [w.view.scroll.x, w.view.scroll.y, w.view.scroll.zoom].map(num).join(',') : null;
    for (const r of config.levels) {
        const k = keyIn(w, r.key), s = sk(k), st = M.status(k);
        o[`b.${s}`] = st.state + (st.turns !== undefined ? ':' + st.turns : '');
        o[`b.${s}.why`] = st.why || '';
        o[`b.${s}.poor`] = !!st.poor;
        o[`b.${s}.missing`] = (st.missing || []).map(x => (x.startsWith('tier:') ? x : sk(x))).join(',');
        o[`b.${s}.reason`] = M.reason(k);
        const d = M.can_demolish(k);
        o[`b.${s}.demolish`] = d.ok ? 'ok' : d.why;
        o[`b.${s}.stands`] = M.stands(k);
        o[`b.${s}.has`] = game.has_building(k);
    }
    for (const p of config.parts) o[`part.${p.key}`] = M.stage(p.key);
    const sources = C.crewSources(levels, k => game.has_building(k), k => game.standing(k));
    for (const [G, group] of Object.entries(levels.groups)) {
        o[`crew.${G}`] = M.crew(G);
        o[`crew.${G}.order`] = M.crew_order(G);
        o[`crew.${G}.place`] = M.crew_place(G);
        const po = M.place_opener(G);
        o[`crew.${G}.opener`] = po ? sk(po.key) : null;
        o[`crew.${G}.hint`] = M.crew_hint(G);
        const note = M.crew_note(G);
        o[`crew.${G}.note`] = note ? (note.bad ? '!' : '') + note.text : null;
        const opts = M.crew_options(G);
        o[`crew.${G}.options`] = opts.map(x => x.key + (x.unlocked ? '+' : '-') + (x.building ? '@' + sk(x.building.key) : '')).join(',');
        for (const x of opts) { const p = M.crew_preview(G, x.key); o[`crew.${G}.${x.key}.preview`] = p.kind + ':' + (p.bad ? '!' : '') + p.text; }
        const bonus = FX.crewBonuses(sources, G);
        for (const kind of FX.CREW_KINDS) o[`crew.${G}.bonus.${kind}`] = num(bonus[kind].pct) + ' ' + bonus[kind].from.map(f => (f.mod ? '*' : '') + f.name + ':' + num(f.value)).join(', ');
        for (const [k, op] of Object.entries(group.options)) {
            if (!op.numbers || op.numbers.ammo === undefined || op.numbers.ammo === null) continue;
            const a = C.crewAmmo(op.numbers, bonus.ammo.pct, op.unit_card ? op.unit_card.men : 0);
            o[`crew.${G}.${k}.ammo`] = [a.places, a.base, a.total, a.per, a.whole].map(num).join('/');
            o[`crew.${G}.${k}.ammo_line`] = C.ammoShare(a, G, per[G]);
        }
    }
    return o;
}

// one action on the page's world -> what it answered (a string)
function apply(w, a) {
    const {M} = w, game = w.game;
    const k = a.key ? keyIn(w, a.key) : null;
    const said = r => (r.ok ? 'ok' : 'no') + (r.why ? ':' + r.why : '') + (r.kind ? ':' + r.kind : '');
    switch (a.do) {
    case 'click': {         // a click on a slot (web/js/panel.js): order, cancel, or the reason in the foot row
        const st = M.status(k);
        if (st.state === 'open') return 'order ' + said(M.order(k));
        if (st.state === 'building') return 'cancel ' + said(M.cancel(k));
        if (st.state === 'locked' || st.state === 'unknown') return 'refuse ' + M.refuse(k);
        return 'none';
    }
    case 'order': return said(M.order(k));
    case 'cancel': return said(M.cancel(k));
    case 'demolish': return said(M.demolish(k));
    case 'refuse': return String(M.refuse(k));
    case 'set_crew': return said(M.set_crew(a.group, a.option));
    case 'end_turn': game.end_turn(); return '';
    case 'ship_seen': M.ship_seen(); return '';
    case 'side': M.set_malakai_side(a.side); return '';
    case 'gold': game.gold = a.gold; return '';
    case 'debug_build': M.debug_build_to(k); return '';
    case 'game_dismantle': return String(game.dismantle(k));
    case 'chosen_old': M.set_crew_chosen_silently(true); return '';
    case 'game_refuses': {      // the game takes the next order silently without doing it (right after a battle: port-to-game.md 3.4)
        game.issue_building_command = () => { delete game.issue_building_command; return true; };
        return '';
    }
    case 'view': w.view = {tab: a.tab ?? null, scroll: a.scroll ?? null}; return '';
    case 'reload': {        // web/js/main.js: the page's save and load, a new game and a new model on the saved data
        const saved = JSON.parse(JSON.stringify({...game.snapshot(), side: M.malakai_side(), side_chosen: !M.side_hint(), crew: M.crew_snapshot(),
            crew_chosen: M.crew_chosen(), ship: M.news_snapshot(), message: M.message_snapshot(), view: w.view}));
        const next = makeWorld(w.spec);
        next.game.restore(saved);
        if (saved.side) next.M.set_side_silently(saved.side);
        next.M.set_side_chosen_silently(saved.side_chosen);
        next.M.set_crew_silently(saved.crew);
        next.M.set_crew_chosen_silently(saved.crew_chosen);
        next.M.set_news_silently(saved.ship);
        next.M.set_message_silently(saved.message);
        next.M.sync_ship();
        w.game = next.game; w.M = next.M; w.view = saved.view;
        return '';
    }
    default: throw new Error('unknown action ' + a.do);
    }
}

// ---- a scenario: its steps with the answers that changed ----
let stepsAll = 0, fieldsAll = 0;
const texts = new Set();        // every string answer, for the coverage of the page's sentences (below)
const seen = o => { for (const v of Object.values(o)) if (typeof v === 'string' && v) texts.add(v); };
function scenario(name, spec) {
    const w = makeWorld(spec);
    let last = observe(w);
    seen(last);
    const rec = {name, config: spec.configName || 'author', sim: spec.sim, obs0: last, steps: []};
    if (spec.configName === 'inline') rec.config = spec.config;
    fieldsAll += Object.keys(last).length;
    const S = {
        w, rec,
        get M() { return w.M; }, get game() { return w.game; },
        run(action) {
            const ret = apply(w, action);
            const now = observe(w);
            const set = {}, del = [];
            for (const [f, v] of Object.entries(now)) if (!(f in last) || last[f] !== v) set[f] = v;
            for (const f of Object.keys(last)) if (!(f in now)) del.push(f);
            rec.steps.push({...action, ret, set, ...(del.length ? {del} : {})});
            seen(set);
            if (ret) texts.add(ret);
            last = now;
            stepsAll++;
            fieldsAll += Object.keys(now).length;
            return ret;
        },
        build(key) {         // order, then the turns it takes
            const r = S.run({do: 'order', key});
            if (r === 'ok') for (let i = 0; i < (w.M.level(keyIn(w, key)) || {turns: 1}).turns; i++) S.run({do: 'end_turn'});
            return r === 'ok';
        },
    };
    return S;
}
const files = {};
const add = (file, S) => { (files[file] ||= []).push(S.rec); };

// the author's tree, in the mod's keys
const authorSpec = (sim = {}) => ({page: author, config: authorConfig, configName: 'author',
    sim: {turn: sim0.turn, gold: 6000, income: sim0.income, built: [], ...sim}});
const node = id => inp.treeRows.levels.find(r => r.id === id);
const K = id => node(id).key;
const byMod = mk => inp.treeRows.levels.find(r => r.mod_key === mk).key;
const levelsOf = () => authorConfig.levels.map(r => r.key);

// ---- page_logic_test.mjs: its paths on the author's tree ----
{
    const S = scenario('page_logic 1: the long way (hull, beer hall, pirates, dummies, crossbows, a change of mind, a reload, demolitions)', authorSpec({demolish: stage.demolish_mode}));
    S.run({do: 'set_crew', group: 'rifles', option: 'pirates'});
    for (const mk of ['airship_hull_1', 'airship_hull_2', 'beer_hall_1']) S.build(byMod(mk));
    S.run({do: 'set_crew', group: 'rifles', option: 'pirates'});
    S.run({do: 'set_crew', group: 'rifles', option: 'quarrellers'});
    S.run({do: 'end_turn'});
    for (const mk of ['infantry_workshop_1', 'crew_weapons_1']) S.build(byMod(mk));
    S.run({do: 'set_crew', group: 'rifles', option: 'quarrellers'});
    S.run({do: 'set_crew', group: 'rifles', option: 'pirates'});
    S.run({do: 'set_crew', group: 'rifles', option: 'quarrellers'});
    S.run({do: 'reload'});
    S.run({do: 'end_turn'});
    S.run({do: 'demolish', key: byMod('beer_hall_1')});
    S.run({do: 'set_crew', group: 'rifles', option: 'pirates'});
    S.run({do: 'demolish', key: byMod('crew_weapons_1')});
    S.run({do: 'demolish', key: byMod('infantry_workshop_1')});
    S.run({do: 'demolish', key: byMod('beer_hall_1')});
    S.run({do: 'end_turn'});
    add('tests', S);
}
{
    const S = scenario('page_logic 2: a debug build, a treasury in debt, an order cancelled', authorSpec({demolish: stage.demolish_mode}));
    S.run({do: 'debug_build', key: byMod('crew_weapons_1')});
    S.run({do: 'set_crew', group: 'rifles', option: 'pirates'});
    S.run({do: 'end_turn'});
    S.run({do: 'gold', gold: 10});
    S.run({do: 'end_turn'});
    S.run({do: 'set_crew', group: 'rifles', option: 'quarrellers'});
    S.run({do: 'set_crew', group: 'rifles', option: 'empty'});
    S.run({do: 'end_turn'});
    S.run({do: 'gold', gold: 5000});
    S.run({do: 'order', key: byMod('crew_weapons_2')});
    S.run({do: 'cancel', key: byMod('crew_weapons_2')});
    add('tests', S);
}
// the tests' own small trees: the four start nodes of tools/tests/tree_design_start.json and nodes added to them; the stage's parts as the test has them
const data = inp.data;
const inline = (levels, parts, sim, words = {}, per = {}) => {
    const page = {levels, parts, words, per};
    return {page, config: luaConfig(page), configName: 'inline', sim: {turn: sim0.turn, gold: 6000, income: sim0.income, built: [], ...sim}};
};
const startDesign = () => T.normalize(readJson('tools/tests/tree_design_start.json')).design;
{
    const start = startDesign();
    const gd = T.gameData(start, data);
    const S = scenario('page_logic 4a: the start file: the beer hall waits for the hull, built up to the dummies, the dummies open the crossbows', inline(gd, stage.parts, {demolish: stage.demolish_mode}));
    S.run({do: 'debug_build', key: prefix + 'crew_weapons_1'});
    S.run({do: 'set_crew', group: 'rifles', option: 'quarrellers'});
    add('tests', S);

    const d = T.normalize(start).design;
    const hall = d.nodes.find(n => n.mod_key === 'beer_hall_1').id, hull2 = d.nodes.find(n => n.mod_key === 'airship_hull_2').id;
    const a = T.addNode(d, {name: 'Кузня', cost: 1000, turns: 2, col: 3, row: 2, crew: []});
    const b = T.addNode(d, {name: 'Пороховой склад', cost: 800, turns: 1, col: 1, row: 4, crew: [{group: 'rifles', option: 'thunderers'}]});
    T.addEdge(d, hull2, a); T.addEdge(d, hall, b); T.addEdge(d, a, b);
    const g2 = T.gameData(d, data);
    const S2 = scenario('page_logic 4b: a node of two parents, a new building, a crew opened by a node of the file', inline(g2, stage.parts, {gold: 20000, demolish: stage.demolish_mode}));
    const KK = id => g2.key_of[id];
    for (const id of [d.nodes[0].id, hull2]) S2.build(KK(id));
    S2.run({do: 'set_crew', group: 'rifles', option: 'thunderers'});
    S2.build(KK(a));
    S2.build(KK(hall));
    S2.run({do: 'order', key: KK(b)});
    S2.run({do: 'cancel', key: KK(b)});
    const ledger = S2.game.treasury();
    S2.run({do: 'gold', gold: 100});
    S2.run({do: 'gold', gold: ledger});
    S2.build(KK(b));
    S2.run({do: 'set_crew', group: 'rifles', option: 'thunderers'});
    S2.run({do: 'demolish', key: KK(a)});
    S2.run({do: 'demolish', key: KK(b)});
    S2.run({do: 'demolish', key: KK(a)});
    add('tests', S2);
}
{
    const d = JSON.parse(JSON.stringify(startDesign()));
    const hull2 = d.nodes.find(n => n.mod_key === 'airship_hull_2');
    const nid = T.addNode(d, {name: 'Гнёзда с дозорными', cost: 300, turns: 1, col: 5, row: 2, requires: [hull2.id],
        effects: [{kind: 'ammo', target: 'rifles', value: 25, text: 'Боезапас стрелков: +25 %', icon: null, good: true}],
        units: ['wh_main_dwf_art_cannon'], parts: [{part: 'pub'}, {part: null, name: 'Дозорные', zone: 'balloon', what: 'figures', figures: 2, note: ''}]});
    const levels = T.gameData(d, data);
    const parts = {...stage.parts, pub: {...stage.parts.pub, building: null}};
    const S = scenario('page_logic 5: a detail with the node that brings it; the node\'s ammo of the riflemen acts once it stands', inline(levels, parts, {gold: 50000}));
    for (const n of ['airship_hull_1', 'airship_hull_2']) { S.run({do: 'order', key: prefix + n}); S.run({do: 'end_turn'}); }
    S.run({do: 'order', key: levels.key_of[nid]});
    S.run({do: 'end_turn'});
    S.run({do: 'demolish', key: levels.key_of[nid]});
    add('tests', S);
}
for (const [inherit, hide, label] of [[true, [], 'II inherits'], [false, [], 'II does not inherit'], [false, ['crew:rifles:pirates'], 'II takes the pirates away']]) {
    const d = JSON.parse(JSON.stringify(startDesign()));
    const hull2 = d.nodes.find(n => n.mod_key === 'airship_hull_2');
    const one = T.addNode(d, {name: 'Чертог I', cost: 100, col: 6, row: 2, requires: [hull2.id], crew: [{group: 'rifles', option: 'pirates'}],
        effects: [{kind: 'ammo', target: 'rifles', value: 10, text: 'Боезапас стрелков: +10 %', icon: null, good: true}]});
    const two = T.addNode(d, {name: 'Чертог II', cost: 100, col: 6, row: 3, requires: [one], prev: one, inherit, hide,
        effects: [{kind: 'ammo', target: 'rifles', value: 25, text: 'Боезапас стрелков: +25 %', icon: null, good: true}]});
    const levels = T.gameData(d, data);
    const S = scenario(`page_logic 6: the lines of levels in the game: ${label}`, inline(levels, stage.parts, {gold: 50000, demolish: 'step_down'}));
    for (const k of ['airship_hull_1', 'airship_hull_2']) { S.run({do: 'order', key: prefix + k}); S.run({do: 'end_turn'}); }
    S.run({do: 'order', key: levels.key_of[one]}); S.run({do: 'end_turn'});
    S.run({do: 'set_crew', group: 'rifles', option: 'pirates'}); S.run({do: 'end_turn'});
    S.run({do: 'order', key: levels.key_of[two]}); S.run({do: 'end_turn'});
    S.run({do: 'demolish', key: levels.key_of[two]});
    S.run({do: 'reload'});
    add('tests', S);
}

// ---- panel_rules_test.mjs ----
{
    const S = scenario('panel_rules 1: a whole campaign: every building ordered as soon as it may be, a turn at a time', authorSpec({gold: 1e6}));
    for (let turn = 0; turn < 80 && levelsOf().some(k => !S.game.has_building(k)); turn++) {
        for (const k of levelsOf()) if (S.M.status(k).state === 'open') S.run({do: 'order', key: k});
        S.run({do: 'end_turn'});
    }
    add('tests', S);
    for (const target of ['mtb_guns_3', 'n5', 'cargo_hold_3', 'n4', 'mtb_hatches_2', 'crew_weapons_3']) {
        const t = node(target);
        const S2 = scenario(`panel_rules 1: built up to below ${target}`, authorSpec({gold: 1e6}));
        S2.run({do: 'debug_build', key: K(t.prev || t.requires[0])});
        add('tests', S2);
    }
}
{
    const S = scenario('panel_rules 1b: the reasons of a fresh campaign, the hull built, short of gold', authorSpec({gold: 1e6}));
    S.run({do: 'debug_build', key: byMod('airship_hull_2')});
    S.run({do: 'gold', gold: 10});
    add('tests', S);
}
{
    const S = scenario('panel_rules 2: the first step; a refused click', authorSpec({gold: 6000}));
    S.run({do: 'order', key: byMod('airship_hull_1')});
    S.run({do: 'refuse', key: byMod('beer_hall_1')});
    S.run({do: 'refuse', key: byMod('airship_hull_1')});
    S.run({do: 'click', key: byMod('beer_hall_1')});
    S.run({do: 'click', key: byMod('airship_hull_1')});
    S.run({do: 'click', key: byMod('airship_hull_1')});
    // the order the game did not take (after a battle): said so, the slot stays open; the next one goes in
    S.run({do: 'cancel', key: byMod('airship_hull_1')});
    S.run({do: 'game_refuses'});
    S.run({do: 'click', key: byMod('airship_hull_1')});
    S.run({do: 'click', key: byMod('airship_hull_1')});
    add('tests', S);
}
{
    const S = scenario('panel_rules 3: what a turn brought to the ship, the mark, the foot line through a reload', authorSpec({gold: 1e6}));
    for (const id of ['airship_hull_1', 'airship_hull_2']) S.build(K(id));
    S.run({do: 'ship_seen'});
    S.build(K('mtb_nest_1'));
    S.run({do: 'end_turn'});
    S.run({do: 'reload'});
    S.run({do: 'ship_seen'});
    S.build(K('engines_1'));
    S.run({do: 'ship_seen'});
    const n2key = K('mtb_nest_2');
    for (const k of S.M.missing(n2key)) if (!k.startsWith('tier:')) S.run({do: 'debug_build', key: k});
    S.run({do: 'end_turn'});
    S.run({do: 'gold', gold: 1e6});
    S.run({do: 'ship_seen'});
    if (S.M.status(n2key).state === 'open') S.build(n2key);
    S.run({do: 'reload'});
    add('tests', S);
}
// ---- crew_groups_test.mjs: its paths on the author's tree ----
const openersOf = (g, o) => authorConfig.levels.filter(r => r.unlocks.some(u => u.group === g && u.option === o)).map(r => r.key);
const groupOf = g => author.levels.groups[g];
const mountNode = g => openersOf(g, groupOf(g).mount)[0];
const kinds = g => Object.entries(groupOf(g).options).filter(([k, o]) => !o.hidden && k !== groupOf(g).mount).map(([k]) => k);
const CG = ['cannons', 'bombs', 'cupolas'];
const crewSpec = () => authorSpec({gold: 100000, demolish: stage.demolish_mode});
{
    const S = scenario('crew_groups 1: a place with the building of its mount; kinds locked until their buildings', crewSpec());
    for (const g of CG) { S.run({do: 'set_crew', group: g, option: kinds(g)[0]}); S.run({do: 'debug_build', key: mountNode(g)}); }
    add('tests', S);
}
const buildAll = S => { for (const k of levelsOf()) S.run({do: 'debug_build', key: k}); };
{
    const S = scenario('crew_groups 2: every group at once: orders, a change of mind, a reload, the turn, a change of kind, taking off', crewSpec());
    buildAll(S);
    const first = {}, second = {};
    for (const g of CG) {
        const ks = S.M.crew_options(g).filter(o => !o.empty).map(o => o.key);
        first[g] = ks[0]; second[g] = ks[ks.length - 1];
        S.run({do: 'set_crew', group: g, option: first[g]});
    }
    S.run({do: 'set_crew', group: 'cannons', option: first.cannons});
    S.run({do: 'set_crew', group: 'cannons', option: second.cannons});
    S.run({do: 'view', tab: 'ship', scroll: {x: -320, y: 48, zoom: 1}});
    S.run({do: 'reload'});
    S.run({do: 'end_turn'});
    S.run({do: 'set_crew', group: 'bombs', option: second.bombs});
    S.run({do: 'set_crew', group: 'cannons', option: groupOf('cannons').mount});
    S.run({do: 'end_turn'});
    add('tests', S);
}
{
    const S = scenario('crew_groups 3: short of gold: no hire; the preview says why', crewSpec());
    buildAll(S);
    S.run({do: 'gold', gold: 0});
    S.run({do: 'set_crew', group: 'bombs', option: S.M.crew_options('bombs').find(o => !o.empty).key});
    add('tests', S);
}
{
    const S = scenario('crew_groups 4: a building goes: its standing crew leaves, an order comes back; the mount gone, the place goes', crewSpec());
    buildAll(S);
    const line = authorConfig.levels.filter(r => openersOf('cannons', groupOf('cannons').mount).includes(r.key));
    const top = line[line.length - 1];
    const only = S.M.crew_options('cannons').find(o => !o.empty && openersOf('cannons', o.key).length === 1 && openersOf('cannons', o.key)[0] === top.key);
    if (!only) throw new Error('the guns\' top level opens no kind of its own');
    S.run({do: 'set_crew', group: 'cannons', option: only.key});
    S.run({do: 'end_turn'});
    S.run({do: 'demolish', key: top.key});
    const k = S.M.crew_options('bombs').find(o => !o.empty).key;
    S.run({do: 'set_crew', group: 'bombs', option: k});
    const hatches = authorConfig.levels.filter(r => openersOf('bombs', groupOf('bombs').mount).includes(r.key)).reverse();
    for (const r of hatches) S.run({do: 'demolish', key: r.key});
    add('tests', S);
}
{
    const S = scenario('crew_groups 5: the riflemen\'s place comes with the first building that opens a kind; an old save\'s single hint flag', crewSpec());
    S.run({do: 'debug_build', key: openersOf('rifles', 'pirates')[0]});
    S.run({do: 'chosen_old'});
    add('tests', S);
}
{
    const S = scenario('crew_groups 7: the harpoon: a place without a mount, hired as the rest', crewSpec());
    S.run({do: 'set_crew', group: 'harpoon', option: 'on'});
    S.run({do: 'debug_build', key: openersOf('harpoon', 'on')[0]});
    S.run({do: 'set_crew', group: 'harpoon', option: 'on'});
    S.run({do: 'end_turn'});
    add('tests', S);
}
{
    const S = scenario('crew_groups 7b: no barge, nothing on it; the hull taken from under a crew', crewSpec());
    buildAll(S);
    S.run({do: 'set_crew', group: 'cannons', option: S.M.crew_options('cannons').find(o => !o.empty).key});
    S.run({do: 'end_turn'});
    for (let n = 5; n >= 2; n--) S.run({do: 'game_dismantle', key: byMod('airship_hull_' + n)});
    add('tests', S);
}
{
    // crew_model_test «enough only with the waiting hire back», on the page: a change of mind paid by the hire that comes back
    const S = scenario('crew: enough gold only with the waiting hire back; a treasury in debt takes the crew off for free', crewSpec());
    S.run({do: 'debug_build', key: byMod('crew_weapons_1')});
    S.run({do: 'debug_build', key: byMod('beer_hall_1')});
    S.run({do: 'gold', gold: 110});
    S.run({do: 'set_crew', group: 'rifles', option: 'quarrellers'});
    S.run({do: 'set_crew', group: 'rifles', option: 'pirates'});
    S.run({do: 'set_crew', group: 'rifles', option: 'quarrellers'});
    S.run({do: 'end_turn'});
    S.run({do: 'gold', gold: -20});
    S.run({do: 'set_crew', group: 'rifles', option: 'pirates'});
    S.run({do: 'set_crew', group: 'rifles', option: 'empty'});
    S.run({do: 'set_crew', group: 'rifles', option: 'quarrellers'});
    S.run({do: 'set_crew', group: 'rifles', option: 'empty'});
    S.run({do: 'end_turn'});
    add('tests', S);
}
{
    const S = scenario('the side of Malakai and its hint, through a reload', authorSpec({gold: 6000}));
    S.run({do: 'side', side: 'left'});
    S.run({do: 'side', side: 'right'});
    S.run({do: 'reload'});
    S.run({do: 'side', side: 'left'});
    add('tests', S);
}

// ---- the random walks ----
function rng(seed) {            // mulberry32
    let a = seed >>> 0;
    return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const pick = (r, list) => list[Math.floor(r() * list.length)];
function walkAction(r, w) {
    const {M, game} = w;
    const keys = levelsOf().map(k => keyIn(w, k));
    const x = r();
    const back = k => authorConfig.levels.find(l => keyIn(w, l.key) === k).key;
    if (x < 0.34) {             // a click on a slot, mostly one that can be ordered or is being built
        const open = keys.filter(k => ['open', 'building'].includes(M.status(k).state));
        return {do: 'click', key: back(open.length && r() < 0.8 ? pick(r, open) : pick(r, keys))};
    }
    if (x < 0.62) {
        const g = pick(r, Object.keys(w.spec.page.levels.groups));
        const opts = M.crew_options(g);
        return {do: 'set_crew', group: g, option: pick(r, opts).key};
    }
    if (x < 0.78) return {do: 'end_turn'};
    if (x < 0.84) {
        const built = keys.filter(k => game.has_building(k));
        return built.length ? {do: 'demolish', key: back(pick(r, built))} : {do: 'end_turn'};
    }
    if (x < 0.88) return {do: 'reload'};
    if (x < 0.91) return {do: 'ship_seen'};
    if (x < 0.93) return {do: 'side', side: pick(r, ['left', 'right'])};
    if (x < 0.955) return {do: 'gold', gold: pick(r, [0, 90, 450, 1200, 5000, 40000])};
    if (x < 0.97) return {do: 'view', tab: pick(r, ['buildings', 'ship']), scroll: {x: -Math.floor(r() * 900), y: Math.floor(r() * 400), zoom: pick(r, [1, 0.5])}};
    if (x < 0.985) return {do: 'debug_build', key: back(pick(r, keys))};
    if (x < 0.993) return {do: 'refuse', key: back(pick(r, keys))};
    return {do: 'game_refuses'};
}
const walkSpec = i => {
    const r = rng(1000 + i);
    return authorSpec({gold: pick(r, [6000, 20000, 60000, 1e6]), income: pick(r, [0, 800, 3000]), demolish: pick(r, ['chain', 'chain', 'step_down'])});
};
for (let i = 0; i < WALKS; i++) {
    const spec = walkSpec(i);
    const S = scenario(`walk ${i} (seed ${2000 + i}, gold ${spec.sim.gold}, income ${spec.sim.income}, ${spec.sim.demolish})`, spec);
    const r = rng(2000 + i);
    for (let s = 0; s < WALK_STEPS; s++) S.run(walkAction(r, S.w));
    add(`walks_${String(Math.floor(i / WALKS_PER_FILE)).padStart(2, '0')}`, S);
}

// ---- the mod's keys change nothing: a few walks on the page's own keys answer the same (the re-keying of tools/ship_config.mjs is faithful) ----
{
    const page = pageLevels(inp);
    const toPage = {};
    const modOf = {};
    for (const r of page.levels.tree_rows) { const t = inp.treeRows.levels.find(x => x.id === r.node); toPage[t.key] = r.key; modOf[r.key] = t.key; }
    for (let i = 0; i < 12; i++) {
        const spec = walkSpec(i);
        const a = makeWorld(spec);
        const b = makeWorld({page, config: authorConfig, sim: spec.sim, keyName: k => modOf[k] || k, keyOf: k => toPage[k] || k});
        const ra = rng(2000 + i), rb = rng(2000 + i);
        for (let s = 0; s < WALK_STEPS; s++) {
            const act = walkAction(ra, a), act2 = walkAction(rb, b);
            if (JSON.stringify(act) !== JSON.stringify(act2)) throw new Error(`walk ${i} step ${s}: the two keyings chose different actions`);
            const x = apply(a, act), y = apply(b, act2);
            const oa = observe(a), ob = observe(b);
            for (const f of Object.keys(oa)) if (oa[f] !== ob[f] || x !== y) throw new Error(`re-keying changed the answer: walk ${i} step ${s} ${f}: ${oa[f]} vs ${ob[f]}`);
        }
    }
}

// ---- the pure functions of crew_model.mjs (crew_model_test.mjs, panel_rules_test.mjs 6, crew_groups_test.mjs 8) ----
const units = [];
{
    const HIRE = {pirates: 110, quarrellers: 80, thunderers: 110};
    const OPEN = ['pirates', 'quarrellers'];
    const ctxOf = (gold, open = OPEN) => ({start: 'empty', open, hire: HIRE, gold});
    const live = c => ({start: c.start, unlocked: o => c.open.includes(o), hire: o => c.hire[o], gold: c.gold});
    const scen = (standing, gold, clicks) => {
        let state = {standing, order: null}, g = gold;
        for (const option of clicks) {
            const ctx = ctxOf(g);
            const r = C.click(state, option, live(ctx));
            units.push({fn: 'click', state, option, ctx, want: r});
            state = r.state; g = r.gold;
        }
        units.push({fn: 'turn', state, want: C.turn(state)});
        units.push({fn: 'held', state, want: C.held(state)});
    };
    scen('empty', 6000, ['pirates', 'quarrellers']);
    scen('empty', 6000, ['pirates', 'pirates']);
    scen('empty', 6000, ['pirates', 'empty', 'quarrellers']);
    scen('quarrellers', 6000, ['pirates', 'quarrellers', 'pirates']);
    scen('quarrellers', 6000, ['pirates', 'empty']);
    scen('quarrellers', 6000, ['empty', 'empty', 'quarrellers']);
    scen('empty', 6000, [...Array(5)].flatMap(() => ['pirates', 'quarrellers']));
    scen('empty', 6000, ['thunderers', 'pirates', 'thunderers']);
    scen('pirates', 6000, ['pirates']);
    scen('empty', 6000, ['empty']);
    scen('empty', 100, ['pirates', 'quarrellers', 'pirates']);
    scen('empty', 110, ['quarrellers', 'pirates', 'quarrellers']);
    scen('pirates', -20, ['quarrellers', 'empty', 'pirates']);
    scen('pirates', 500, ['empty']);
    const lose = (state, gold, open) => { const ctx = ctxOf(gold, open); units.push({fn: 'lose', state, ctx, want: C.lose(state, live(ctx))}); };
    lose({standing: 'pirates', order: {option: 'quarrellers', paid: 80}}, 1000, ['pirates']);
    lose({standing: 'quarrellers', order: {option: 'pirates', paid: 110}}, 1000, ['pirates']);
    lose({standing: 'quarrellers', order: {option: 'empty', paid: 0}}, 1000, ['pirates']);
    lose({standing: 'pirates', order: {option: 'pirates', paid: 0}}, 1000, []);
    lose({standing: 'pirates', order: null}, 1000, ['pirates']);
    // the bonuses: a synthetic tree (crew_model_test) and the lines' rule (the tree of h1..h3, tg)
    const sourcesCase = (dataLike, built, groups) => {
        const has = k => built.includes(k);
        const src = C.crewSources(dataLike, has, has);
        const cfg = {tree: !!dataLike.tree_rows, sources: dataLike.tree_rows.map(r => ({key: r.key, name: r.name, effects: (r.effects || []).filter(e => e && FX.CREW_KINDS.includes(e.kind)).map(e => ({kind: e.kind, target: e.target || '', value: e.value}))})),
            ammo_mod: Object.entries(dataLike.ammo_mod || {}).map(([key, mult]) => ({key, mult})),
            groups: Object.entries(dataLike.groups || {}).map(([key, g]) => ({key, boost: (g.boost || []).map(b => ({building: b.building, ...(typeof b.spread === 'number' ? {spread: b.spread} : {}), ...(typeof b.range === 'number' ? {range: b.range} : {})}))}))};
        for (const g of groups) units.push({fn: 'bonuses', config: cfg, built, group: g, want: FX.crewBonuses(src, g)});
    };
    sourcesCase({ammo_mod: {K_cargo: 1.15}, groups: {rifles: {boost: [{building: 'K_dummy', spread: 0.95, range: null}]}, cannons: {boost: [{building: 'K_sig', spread: 0.9, range: 1.1}]}},
        tree_rows: [{key: 'K_cargo', name: 'Трюм', effects: [{kind: 'ammo', target: 'cannons', value: 25}]}, {key: 'K_dummy', name: 'Манекен', effects: [{text: 'Меткость стрелков: +5 %'}]},
                    {key: 'K_sig', name: 'Сигналы', effects: [{kind: 'range', target: 'all', value: 20}]}, {key: 'K_far', name: 'Не стоит', effects: [{kind: 'ammo', target: 'all', value: 50}]}]},
        ['K_cargo', 'K_dummy', 'K_sig'], ['rifles', 'cannons', 'bombs']);
    const d = T.emptyDesign();
    const h1 = T.addNode(d, {id: 'h1', name: 'Трюм', cost: 1, effects: [{kind: 'ammo', target: 'rifles', value: 15, text: '', icon: null, good: true}]});
    const h2 = T.addNode(d, {id: 'h2', name: 'Хранилище', cost: 1, requires: [h1], prev: h1, inherit: true, effects: [{kind: 'ammo', target: 'rifles', value: 30, text: '', icon: null, good: true}]});
    const h3 = T.addNode(d, {id: 'h3', name: 'Люк', cost: 1, requires: [h2], prev: h2, inherit: true, effects: [{kind: 'ammo', target: 'all', value: 100, text: '', icon: null, good: true}]});
    const tg = T.addNode(d, {id: 'tg', name: 'Торпедная галерея', cost: 1, effects: [{kind: 'ammo', target: 'bombs', value: 30, text: '', icon: null, good: true}]});
    const g = T.gameData(d, {prefix: 'p_', groups: {}, ammo_mod: {}, hull: [], chains: []});
    for (const ids of [[h2], [h3], [h3, tg], [tg], [h1, tg]]) sourcesCase(g, ids.map(id => g.key_of[id]), ['rifles', 'bombs', 'cannons']);
    // the author's tree: every set of standing levels a campaign walks through is in the walks; here the whole tree built, and the hold alone
    for (const pct of [-10, 0, 5, 25]) for (const [base, kind] of [[96, 'ammo'], [13, 'reload'], [16.6, 'reload'], [72, 'ammo'], [18, 'ammo'], [600, 'range']]) units.push({fn: 'apply_pct', base, pct, kind, want: FX.applyPct(base, pct, kind)});
    // the ammunition of every kind of the data, at every bonus the tests try
    for (const grp of authorConfig.groups) for (const o of grp.options) {
        if (o.ammo === undefined) continue;
        const n = author.levels.groups[grp.key].options[o.key].numbers;
        for (const p of [0, 5, 15, 30, 50, 100, 130, 300]) for (const per of [grp.per, 'на место', undefined]) {
            const a = C.crewAmmo(n, p, o.men || 0);
            units.push({fn: 'ammo', n: {ammo: o.ammo, ...(o.seats !== undefined ? {seats: o.seats} : {})}, pct: p, men: o.men || 0, group: grp.key, ...(per ? {per} : {}), want: {a, line: C.ammoShare(a, grp.key, per)}});
        }
    }
    for (const g2 of ['rifles', 'cannons', 'bombs', 'cupolas', 'harpoon', 'other']) for (let v = 0; v <= 125; v++) units.push({fn: 'plural', v, group: g2, want: C.plural(v, C.PLACE_NOUNS[g2] || ['место', 'места', 'мест'])});
    for (let v = 0; v <= 125; v++) units.push({fn: 'turns_text', v, want: turnsText(v)});
    // the sentences no state of the author's tree reaches: a new kind for every place, a tier with no hull, a key the data does not have
    const w = makeWorld(authorSpec());
    for (const g2 of ['rifles', 'cannons', 'bombs', 'cupolas', 'harpoon', 'deck']) for (const names of [['X'], ['X', 'Y']]) units.push({fn: 'new_kinds_text', group: g2, names, want: w.M.new_kinds_text(g2, names)});
    for (const keys of [['tier:3'], [byMod('beer_hall_1'), 'tier:6'], [prefix + 'nope']]) units.push({fn: 'requires_text', keys, want: w.M.requires_text(keys)});
    units.push({fn: 'status', key: 'nope', want: {status: w.M.status('nope'), reason: w.M.reason('nope'), order: w.M.order('nope')}});
    // the first letter up (the turn's line starts with a crew's words): every small letter the texts may start with
    for (const ch of 'абвгдеёжзийклмнопрстуфхцчшщъыьэюяabcz«1') { const s = ch + 'тест'; units.push({fn: 'upper_first', s, want: s[0].toUpperCase() + s.slice(1)}); }
}

// ---- the coverage: every sentence of barge_buildings.js said at least once by some step (the ones that cannot happen on this tree named) ----
const SENTENCES = {
    'Требуется постройка: ': 'one requirement', 'Требуются постройки: ': 'several requirements', 'Уже строится «': 'a line busy',
    'Не хватает золота: нужно ': 'short of gold', ', в казне ': 'short of gold, the window\'s sentence', 'Заказано: «': 'ordered',
    'не прошёл: игра его не приняла': 'an order the game did not take', 'Отменено: «': 'cancelled', 'Снесено: «': 'demolished',
    'Сначала снесите «': 'demolish refused', ': он стоит на этой постройке': 'demolish refused: a level above', ': ей нужна эта постройка': 'demolish refused: needed',
    'Не построено': 'demolish: not built', 'Постройки больше нет: ': 'a building gone, the crew', 'снят, ': 'a building gone: an order back',
    'сошли с корабля, найм не возвращается': 'a building gone: the standing crew', 'Построено: «': 'built', 'Открыто место экипажа «': 'a place opened',
    'Открыты места экипажа «': 'places opened', 'Для стрелков теперь': 'a new kind: rifles', 'В порты теперь можно поставить': 'a new kind: cannons',
    'На стеллажи над люками': 'a new kind: bombs', 'В гнёздах теперь доступны': 'a new kind: cupolas', 'На нос шара теперь': 'a new kind: harpoon',
    'Новый уровень этого не даёт: ': 'a level that does not carry on', 'Закажите первую постройку — «': 'the first step', 'Малакай встанет на левый': 'side left',
    'Малакай встанет на правый': 'side right', 'Заперто: ': 'crew locked', 'Не хватает золота на ': 'crew poor', 'Экипаж уже сходит в начале хода': 'kept: taking off ordered',
    ' уже в найме': 'kept: ordered', 'kept:У бортов никого': 'kept: nobody (rifles)', 'Заказ на ': 'cancelled (done)', 'Снять заказ на ': 'cancelled (preview)',
    'Экипаж сойдёт в начале хода': 'taking off (done)', 'Снять экипаж в начале хода': 'taking off (preview)', 'В найме «': 'ordered (done)',
    ' вместо «': 'ordered instead', 'Нанять «': 'ordered (preview)', ', вернулось ': 'gold back (done)', ', вернётся ': 'gold back (preview)',
    'встали к бортам': 'came (rifles)', 'встали в порты': 'came (cannons)', 'стрелки сошли с бортов': 'left (rifles)', 'орудия ушли из портов': 'left (cannons)',
    'Содержание экипажа: ': 'upkeep alone (capitalised)', 'содержание экипажа: ': 'upkeep with arrivals', ' по ': 'ammo: whole share', ', около ': 'ammo: about',
};
const said = [...texts];
const lower = said.map(t => t.toLowerCase());
const unseen = Object.entries(SENTENCES).filter(([s]) => !said.some(t => t.includes(s)) && !(s === s.toLowerCase() && lower.some(t => t.includes(s)))).map(([s, what]) => `${what} («${s.trim()}»)`);
if (unseen.length) console.log('sentences no step says: ' + unseen.join('; '));

// ---- the files ----
fs.rmSync(OUT, {recursive: true, force: true});
fs.mkdirSync(OUT, {recursive: true});
const counts = {scenarios: 0, steps: stepsAll, fields_compared: fieldsAll, units: units.length, sentences: Object.keys(SENTENCES).length, sentences_unseen: unseen};
for (const [file, scenarios] of Object.entries(files)) {
    counts.scenarios += scenarios.length;
    fs.writeFileSync(path.join(OUT, file + '.json'), JSON.stringify({scenarios}) + '\n');
}
fs.writeFileSync(path.join(OUT, 'units.json'), JSON.stringify({units}) + '\n');
const configText = JSON.stringify(authorConfig);
fs.writeFileSync(path.join(OUT, 'meta.json'), JSON.stringify({
    _about: 'Made by tools/tests/vectors_export.mjs. The author\'s config the scenarios with config "author" ran on: tools/lua_vectors.py checks the pack carries the same.',
    config_sha256: crypto.createHash('sha256').update(configText).digest('hex'), config: authorConfig, counts,
    files: [...Object.keys(files), 'units'].map(f => f + '.json'),
}, null, 1) + '\n');
console.log(`vectors: ${counts.scenarios} scenarios, ${counts.steps} steps, ${counts.fields_compared} answers, ${counts.units} unit calls -> ${path.relative(REPO, OUT)}`);
