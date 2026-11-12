// The crew groups beside the riflemen (the guns in the ports, the bombs over the hatches, the throwers in the nests) as the page plays them, without a
// browser: web/js/barge_buildings.js over the author's tree (web/data/tree_design.json, read only) and the export (build/web/data.json: run
// tools/web_export.py --data first). Nothing of the data is written here: the kinds, prices and buildings are read from the files.
//   node tools/tests/crew_groups_test.mjs
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
const design = T.normalize(json('web/data/tree_design.json')).design;
const levels = T.gameData(design, data);
let failed = 0;
const check = (name, ok, extra = '') => { if (!ok) failed++; console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok ? '' : '  ' + (typeof extra === 'string' ? extra : JSON.stringify(extra)))); };

function fresh(gold = 100000) {
    const game = new GameSim(levels, {...sim, gold, built: stage.built || sim.built, demolish: stage.demolish_mode});
    const M = makeBuildings(levels, game, stage.parts);
    for (const a of stage.crew_areas || []) if (a.words) M.words[a.group] = a.words;
    return {game, M};
}
// the tree's own answers: which node makes a group's place (the one that opens its mount), which nodes open a kind
const nodeKey = id => levels.key_of[id];
const openersOf = (g, o) => levels.tree_rows.filter(r => r.unlocks.some(u => u.group === g && u.option === o)).map(r => r.key);
const mountNode = g => openersOf(g, data.groups[g].mount)[0];
const groups = ['cannons', 'bombs', 'cupolas'];
const kinds = g => Object.entries(data.groups[g].options).filter(([k, o]) => !o.hidden && k !== data.groups[g].mount).map(([k]) => k);
const opt = (g, k) => data.groups[g].options[k];

// 1. a place appears with the building of its mount, empty; kinds stay locked until their buildings stand
{
    const {game, M} = fresh();
    for (const g of groups) {
        check(`${g}: the tree has a node that makes the place`, !!mountNode(g), g);
        check(`${g}: no place before it`, !M.crew_place(g));
        const k = kinds(g)[0];
        check(`${g}: a kind cannot be ordered without the place`, M.set_crew(g, k).kind === 'locked');
        M.debug_build_to(mountNode(g));
        check(`${g}: the place stands with «${M.level(mountNode(g)).name}», empty`, M.crew_place(g) && M.crew(g) === data.groups[g].mount && M.crew_order(g) === null);
        const options = M.crew_options(g);
        check(`${g}: the choice lists «Пусто» first and every kind of the tree`, options[0].empty && options[0].key === data.groups[g].mount
            && kinds(g).filter(k => openersOf(g, k).length).every(k => options.some(o => o.key === k)), options.map(o => o.key));
        for (const o of options.filter(o => !o.empty)) {
            const open = openersOf(g, o.key).some(key => game.standing(key) || M.stands(key));
            check(`${g}/${o.key}: unlocked only when a building that opens it stands (${open})`, o.unlocked === open);
        }
    }
}

// 2. the long way of every group at once: build all, order a kind of each in the same turn, change one's mind, the turn, a change of kind, taking off
{
    const {game, M} = fresh();
    let ledger = game.treasury();
    const same = step => check(`${step}: treasury ${game.treasury()} = ledger ${ledger}`, game.treasury() === ledger);
    for (const v of levels.tree_rows) M.debug_build_to(v.key);
    same('built everything (debug: no gold)');
    for (const g of groups) check(`${g}: the place stands and every kind is open`, M.crew_place(g) && M.crew_options(g).every(o => o.unlocked));
    const first = {}, second = {};
    for (const g of groups) {
        const ks = M.crew_options(g).filter(o => !o.empty).map(o => o.key);
        first[g] = ks[0]; second[g] = ks[ks.length - 1];
        check(`${g}: the hint glows before the first choice`, M.crew_hint(g));
        check(`${g}: order «${opt(g, first[g]).name}»`, M.set_crew(g, first[g]).kind === 'ordered'); ledger -= opt(g, first[g]).hire; same(`${g} ordered`);
        check(`${g}: the hint is off once chosen`, !M.crew_hint(g));
    }
    check('the riflemen\'s hint is its own', M.crew_hint('rifles'));
    check('the same click again changes nothing', M.set_crew('cannons', first.cannons).kind === 'kept'); same('a double click');
    check('the cannons change their mind the same turn', M.set_crew('cannons', second.cannons).kind === 'ordered'); ledger += opt('cannons', first.cannons).hire - opt('cannons', second.cannons).hire; same('cannons changed');
    check('the other groups keep their orders', M.crew_order('bombs') === first.bombs && M.crew_order('cupolas') === first.cupolas);
    check('the upkeep of next turn counts every order', M.crew_upkeep() === 0 && M.crew_upkeep_next() === opt('cannons', second.cannons).upkeep + opt('bombs', first.bombs).upkeep + opt('cupolas', first.cupolas).upkeep);
    // a reload in the middle (F5): the same orders, the same treasury
    const saved = JSON.parse(JSON.stringify({...game.snapshot(), crew: M.crew_snapshot(), chosen: M.crew_chosen()}));
    const again = fresh();
    again.game.restore(saved); again.M.set_crew_silently(saved.crew); again.M.set_crew_chosen_silently(saved.chosen);
    check('reload mid-order: the same orders and treasury', groups.every(g => again.M.crew_order(g) === M.crew_order(g)) && again.game.treasury() === ledger);
    check('reload: the hints as they were', groups.every(g => !again.M.crew_hint(g)) && again.M.crew_hint('rifles'));
    game.end_turn();
    ledger -= opt('cannons', second.cannons).upkeep + opt('bombs', first.bombs).upkeep + opt('cupolas', first.cupolas).upkeep;
    check('after the turn every group stands', M.crew('cannons') === second.cannons && M.crew('bombs') === first.bombs && M.crew('cupolas') === first.cupolas); same('turn');
    check('the turn\'s news speaks of the ports', /встали в порты/.test(M.message() || ''), M.message());
    check('a change of kind: the old stands until the turn', M.set_crew('bombs', second.bombs).kind === 'ordered' && M.crew('bombs') === first.bombs); ledger -= opt('bombs', second.bombs).hire; same('bombs changed');
    check('taking the cannons off is free', M.set_crew('cannons', data.groups.cannons.mount).kind === 'ordered'); same('cannons off');
    game.end_turn(); ledger -= opt('bombs', second.bombs).upkeep + opt('cupolas', first.cupolas).upkeep;
    check('after the turn: new bombs, empty ports', M.crew('bombs') === second.bombs && M.crew('cannons') === data.groups.cannons.mount); same('second turn');
    check('the turn\'s news: the guns left their ports', /ушли из портов/.test(M.message() || ''), M.message());
}

// 3. short of gold: no hire, the order waits; taking off is free
{
    const {game, M} = fresh();
    for (const v of levels.tree_rows) M.debug_build_to(v.key);
    game.gold = 0;
    const k = M.crew_options('bombs').find(o => !o.empty).key;
    const r = M.set_crew('bombs', k);
    check('no gold: the bombs are not hired', r.kind === 'poor' && M.crew_order('bombs') === null && game.treasury() === 0);
    check('no gold: the preview says why', /Не хватает золота/.test(M.crew_preview('bombs', k).text));
}

// 4. a building goes: a standing crew of a kind it opened leaves, an order of it comes back with its gold; without the mount nothing of the group stays
{
    const {game, M} = fresh();
    for (const v of levels.tree_rows) M.debug_build_to(v.key);
    let ledger = game.treasury();
    // the guns' line: its top level opens a kind the others do not; taken down, that kind is gone
    const line = levels.tree_rows.filter(r => openersOf('cannons', data.groups.cannons.mount).includes(r.key)).sort((a, b) => a.line_level - b.line_level);
    const top = line[line.length - 1];
    const only = M.crew_options('cannons').find(o => !o.empty && openersOf('cannons', o.key).length === 1 && openersOf('cannons', o.key)[0] === top.key);
    if (only) {
        M.set_crew('cannons', only.key); ledger -= only.hire; game.end_turn(); ledger -= only.upkeep;
        check(`«${only.name}» stands`, M.crew('cannons') === only.key && game.treasury() === ledger);
        const r = M.demolish(top.key);
        check(`demolish «${top.name}»: «${only.name}» leave for nothing`, r.ok && M.crew('cannons') === data.groups.cannons.mount && game.treasury() === ledger, M.message());
    } else check('the guns\' top level opens a kind of its own', false, line.map(r => r.key));
    // the bombs' place: an order waits, its mount goes (the whole line down) -> the order back, the place gone
    const k = M.crew_options('bombs').find(o => !o.empty).key;
    M.set_crew('bombs', k); ledger -= opt('bombs', k).hire;
    const hatches = levels.tree_rows.filter(r => openersOf('bombs', data.groups.bombs.mount).includes(r.key)).sort((a, b) => b.line_level - a.line_level);
    let ok = true;
    for (const r of hatches) { const d = M.demolish(r.key); ok = ok && d.ok; }
    ledger += opt('bombs', k).hire;
    check('the hatches demolished level by level', ok, M.message());
    check('without the hatches: no place, the order back with its gold', !M.crew_place('bombs') && M.crew_order('bombs') === null && game.treasury() === ledger, {place: M.crew_place('bombs'), order: M.crew_order('bombs'), gold: game.treasury(), ledger});
    check('the other groups untouched', M.crew_place('cannons') && M.crew_place('cupolas'));
}

// 5. the riflemen as before: their place comes with the first building that opens a kind of them (no mount)
{
    const {M} = fresh();
    check('rifles: no place on the bare barge', !M.crew_place('rifles'));
    const k = openersOf('rifles', 'pirates')[0];
    M.debug_build_to(k);
    check(`rifles: the place with «${M.level(k).name}»`, M.crew_place('rifles') && M.crew('rifles') === 'empty');
    check('rifles: an old save\'s single hint flag still reads', (M.set_crew_chosen_silently(true), !M.crew_hint('rifles') && M.crew_hint('cannons')));
}

// 6. the page's data for the three groups: a card for every kind, a drawing for every kind, the words of every place
{
    const art = json('web/art/layers.json');
    for (const g of groups) {
        const area = (stage.crew_areas || []).find(a => a.group === g);
        check(`${g}: a place in blueprint.json with its words`, !!area && !!area.words && ['at', 'stand', 'come', 'came', 'leave', 'left', 'nobody', 'empty_name', 'who'].every(w => area.words[w]));
        check(`${g}: its box and glow in layers.json`, !!(art.crew_areas[g] && art.crew_areas[g].area && art.crew_areas[g].glow));
        for (const k of kinds(g)) {
            const o = opt(g, k);
            check(`${g}/${k}: a card (game's or drawn)`, !!(o.unit_card || o.drawn_card), o);
            check(`${g}/${k}: ink, sketch on the drawing`, !!art.places[`crew_${g}_${k}`] && !!art.places[`crew_${g}_${k}_sketch`]);
            check(`${g}/${k}: its own numbers`, !!(o.numbers && o.numbers.reload && o.numbers.ammo));
        }
    }
    // every detail a node of the tree brings has a drawing
    const parts = blueprint.parts, places = art.places;
    for (const n of design.nodes) for (const p of n.parts || []) {
        const key = p.part || Object.keys(parts).find(k => parts[k].name === p.name) || Object.keys(stage.parts || {}).find(k => stage.parts[k].name === p.name);
        const spec = key && (parts[key] || (stage.parts || {})[key]);
        const drawn = spec && ['pencil', 'build', 'ink'].some(s => spec[s] && (places[spec[s]] || (data.art.layers || {})[spec[s]]));
        check(`«${n.name}» brings «${spec ? spec.name : p.name}»: drawn`, !!drawn, p);
    }
}

// 7. the harpoon: a place without a mount, opened by the building of the tree that opens its «on»; a choice of empty or the harpoon, hired as the rest
{
    const {game, M} = fresh();
    const k = openersOf('harpoon', 'on')[0];
    check('harpoon: the tree has a building that opens it', !!k);
    check('harpoon: no place before it', !M.crew_place('harpoon') && M.set_crew('harpoon', 'on').kind === 'locked');
    M.debug_build_to(k);
    let ledger = game.treasury();
    check(`harpoon: the place with «${M.level(k).name}», empty`, M.crew_place('harpoon') && M.crew('harpoon') === 'empty');
    check('harpoon: ordered for its hire', M.set_crew('harpoon', 'on').kind === 'ordered' && game.treasury() === ledger - opt('harpoon', 'on').hire);
    ledger -= opt('harpoon', 'on').hire;
    game.end_turn(); ledger -= opt('harpoon', 'on').upkeep;
    check('harpoon: stands after the turn, its upkeep taken', M.crew('harpoon') === 'on' && game.treasury() === ledger);
    check('harpoon: the turn\'s news speaks of the nose', /на нос/.test(M.message() || ''), M.message());
    const ab = opt('harpoon', 'on').ability;
    check('harpoon: its numbers from the game\'s tables (uses, range, damage)', !!ab && ab.uses >= 1 && ab.range > 0 && ab.damage > 0, ab);
    const art = json('web/art/layers.json');
    check('harpoon: ink, sketch, empty, tags on the drawing', ['crew_harpoon_on', 'crew_harpoon_on_sketch', 'crew_harpoon_empty', 'crew_harpoon_tag_plus'].every(n => art.places[n]));
}

// 7b. no barge, nothing on it: before the base barge no detail (not even in pencil) and no crew place; the hull taken from under a crew takes it
{
    const {game, M} = fresh();
    check('carrier: the base barge is the part everything stands on', M.carrier === 'barge');
    check('carrier: on the bare timber no detail is drawn, not even in pencil', Object.keys(stage.parts).filter(p => p !== 'barge' && !stage.parts[p].base).every(p => M.stage(p) === 'none'));
    for (const v of levels.tree_rows) M.debug_build_to(v.key);
    M.set_crew('cannons', M.crew_options('cannons').find(o => !o.empty).key);
    game.end_turn();
    check('carrier: with the barge the places and the details are there', M.crew_place('cannons') && M.stage('pub') === 'ink' && M.crew('cannons') !== 'empty');
    for (let n = 5; n >= 2; n--) game.dismantle(data.prefix + 'airship_hull_' + n);
    check('carrier: the hull gone, every place and detail goes, the crew leaves', ['rifles', ...groups, 'harpoon'].every(g => !M.crew_place(g)) && M.stage('pub') === 'none' && M.crew('cannons') === 'empty');
}

// 8. the ammunition in volleys a seat, as the mod's Lua counts it: the group's whole times the bonus, rounded, shared by the seats
{
    const ammoOf = (n, pct) => { const total = Math.floor(n.ammo * (1 + pct / 100) + 0.5); return {total, per: Math.round(total / n.seats * 10) / 10}; };
    for (const g of ['rifles', ...groups]) for (const k of kinds(g)) {
        const n = opt(g, k).numbers;
        if (!n || !n.seats) continue;
        check(`${g}/${k}: the volleys a seat times the seats are the group's ammunition`, n.volleys * n.seats === n.ammo, n);
        const plus = ammoOf(n, 15);
        check(`${g}/${k}: +15 % is not lost in the rounding (${n.ammo} -> ${plus.total}, ${plus.per} a seat)`, plus.total > n.ammo || n.ammo * 0.15 < 0.5);
    }
    for (const a of stage.crew_areas) check(`${a.group}: the place says whom the volleys are counted for`, a.group === 'harpoon' || !!a.per, a);
}

console.log(`failed: ${failed}`);
process.exit(failed ? 1 : 0);
