// The airship screen's rules without a browser, over the author's tree (web/data/tree_design.json, only read) and the exported data:
//   node tools/tests/panel_rules_test.mjs
// - the reason of a locked building: exactly its direct requirements that do not stand (the level below in its line, every building it requires, the
//   hull of its tier when the hull is short), each once, nearest first, in the game's words; for all 41 buildings at many points of a campaign;
// - what a turn's buildings brought to the ship (the new details, the crew places opened), the foot line that names them, the tab's mark;
// - the first step of a fresh campaign; a refused click says the window's reason;
// - the small cards over a slot (at most three, «+N» for the rest); crossings and junctions of the tree's lines; the ammunition a seat in whole
//   volleys; numbers written as the game's Russian texts write them.
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {GameSim} from '../../web/js/game_sim.js';
import {makeBuildings} from '../../web/js/barge_buildings.js';
import * as T from '../../web/js/tree_model.mjs';
import {gameText, infoTop} from '../../web/js/panel.js';
import * as C from '../../web/js/crew_model.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const json = p => JSON.parse(readFileSync(join(root, p), 'utf-8'));
const data = json('build/web/data.json'), sim = json('web/data/sim.json'), blueprint = json('web/data/blueprint.json');
const stage = blueprint.stages[blueprint.stage];
let failed = 0;
const check = (name, ok, extra = '') => { if (!ok) failed++; console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok || !extra ? '' : '  ' + (typeof extra === 'string' ? extra : JSON.stringify(extra).slice(0, 1500)))); return ok; };

// the author's tree as the page builds it (web/js/main.js: the details of blueprint.json the nodes bring are joined, a detail named by its name)
const design = T.normalize(json('web/data/tree_design.json')).design;
const byName = Object.fromEntries(Object.entries(blueprint.parts).map(([k, s]) => [s.name, k]));
for (const n of design.nodes) for (const p of n.parts || []) if (!p.part && p.name && byName[p.name]) p.part = byName[p.name];
const parts = JSON.parse(JSON.stringify(stage.parts === true ? blueprint.parts : stage.parts || {}));
for (const p of design.nodes.flatMap(n => n.parts || [])) if (p.part && blueprint.parts[p.part]) parts[p.part] = {...blueprint.parts[p.part], ...(parts[p.part] || {}), enabled: true};
const levels = T.gameData(design, data);
const K = id => levels.key_of[id];
const node = Object.fromEntries(design.nodes.map(n => [K(n.id), n]));
const fresh = (gold = 1e6) => {
    const game = new GameSim(levels, {...sim, gold, built: []});
    const M = makeBuildings(levels, game, parts);
    for (const a of stage.crew_areas || []) if (a.words) M.words[a.group] = a.words;
    return {game, M};
};

// ---- 1. the reason of a locked building ----
// the rule written again from the tree's file, not from the module: the requirements of a node are its links (requires), the level below it in its
// line (prev), and the hull of its tier (the nodes airship_hull_N are tier N) when no hull of that tier or higher stands
const hullTier = Object.fromEntries(design.nodes.filter(n => /^airship_hull_\d+$/.test(n.mod_key || '')).map(n => [K(n.id), Number(n.mod_key.slice(13))]));
function expected(game, key) {
    const n = node[key], want = new Set();
    for (const id of [...(n.prev ? [n.prev] : []), ...n.requires]) if (!game.has_building(K(id))) want.add(K(id));
    const tier = Math.max(0, ...Object.entries(hullTier).filter(([k]) => game.has_building(k)).map(([, t]) => t));
    if (!(key in hullTier) && (n.tier || 0) > tier) {
        const h = Object.entries(hullTier).filter(([, t]) => t >= n.tier).sort((a, b) => a[1] - b[1])[0];
        if (h && !game.has_building(h[0])) want.add(h[0]);
    }
    return want;
}
const unbuiltBelow = (M, game, k) => M.needs_all(k).filter(x => !game.has_building(x)).length;
let states = 0, lockedSeen = 0;
const bad = [];
function audit(M, game, label) {
    states++;
    for (const key of Object.keys(node)) {
        const st = M.status(key);
        if (st.state !== 'locked' || st.poor || /^Уже строится/.test(st.why)) continue;
        lockedSeen++;
        const want = expected(game, key), got = st.missing || [];
        const names = [...st.why.matchAll(/«([^»]+)»/g)].map(m => m[1]);
        const problems = [];
        if (got.length !== want.size || got.some(k => !want.has(k))) problems.push('listed ≠ unbuilt direct requirements');
        if (new Set(got).size !== got.length) problems.push('a building twice');
        // the game's line, its number as the list's: one building «Требуется постройка: «X»», several «Требуются постройки: «X», «Y»»
        if (!st.why.startsWith(got.length > 1 ? 'Требуются постройки: ' : 'Требуется постройка: ')) problems.push('not the game\'s words in the list\'s number');
        if (/Нужен корпус|Сначала|Нужн[аы] постройк/.test(st.why)) problems.push('old wording');
        if (names.join('|') !== got.map(k => M.level(k).name).join('|')) problems.push('the text does not name the list');
        const far = got.map(k => unbuiltBelow(M, game, k));
        if (far.some((d, i) => i && d < far[i - 1])) problems.push('not nearest first');
        if (M.reason(key) !== st.why + '.') problems.push('the window\'s sentence differs');
        if (problems.length) bad.push({label, building: node[key].name, why: st.why, want: [...want].map(k => M.level(k).name), problems});
    }
}
{
    // fresh, then every building ordered in the tree's order as soon as it may be, a turn at a time (the states of a whole campaign), and a few
    // campaigns that build only one line first
    const {game, M} = fresh();
    audit(M, game, 'fresh');
    for (let turn = 0; turn < 80 && Object.keys(node).some(k => !game.has_building(k)); turn++) {
        for (const k of Object.keys(node)) if (M.status(k).state === 'open') M.order(k);
        audit(M, game, 'turn ' + turn + ' ordered');
        game.end_turn();
        audit(M, game, 'turn ' + turn);
    }
    for (const target of ['mtb_guns_3', 'n5', 'cargo_hold_3', 'n4', 'mtb_hatches_2', 'crew_weapons_3']) {
        const g = fresh();
        g.M.debug_build_to(K(design.nodes.find(n => n.id === target).prev || design.nodes.find(n => n.id === target).requires[0]));
        audit(g.M, g.game, 'built up to below ' + target);
    }
}
check(`the reason of every locked building names exactly its direct requirements not built, each once, nearest first, in the game's words «Требуется постройка: …» / «Требуются постройки: …» (${lockedSeen} locked buildings in ${states} states of a campaign)`,
    !bad.length && lockedSeen > 200, bad.slice(0, 6));
{
    const {M} = fresh();
    const one = M.requires_text([K('airship_hull_1')]), two = M.requires_text([K('airship_hull_1'), K('beer_hall_1')]);
    check('one building: «Требуется постройка: «X»»; several: «Требуются постройки: «X», «Y»»', one === 'Требуется постройка: «Заготовка под корабль»' && two === 'Требуются постройки: «Заготовка под корабль», «Пивной чертог»', {one, two});
}
{
    const {game, M} = fresh();
    const why = id => M.status(K(id)).why;
    check('the beer hall on a fresh campaign: its own hull named once, not «Нужен корпус «Прочный корпус»»', why('beer_hall_1') === 'Требуется постройка: «Прочный корпус»', why('beer_hall_1'));
    check('the bomb hatches on a fresh campaign: both parents named, not only a hull that is too low', /«Верстак инженера»/.test(why('mtb_hatches_1')) && /«Маленькая кузница»/.test(why('mtb_hatches_1')), why('mtb_hatches_1'));
    check('the second hull: the first, its level below', why('airship_hull_2') === 'Требуется постройка: «Заготовка под корабль»', why('airship_hull_2'));
    M.debug_build_to(K('airship_hull_2'));
    check('the hull built: the dummies name the weapon store, the nearest step', why('crew_weapons_1') === 'Требуется постройка: «Склад оружия»', why('crew_weapons_1'));
    check('a level whose tier asks for a higher hull than its links: the hull named with them (the outer cargo hatch)', /«Корпус с рунами»/.test(why('cargo_hold_3')), why('cargo_hold_3'));
    game.gold = 10;
    const poor = M.status(K('beer_hall_1'));
    check('short of gold: the gold sentence, with what the treasury has', poor.poor && M.reason(K('beer_hall_1')) === `Не хватает золота: нужно ${M.level(K('beer_hall_1')).cost}, в казне 10.`, M.reason(K('beer_hall_1')));
}

// ---- 2. the first step; a refused click ----
{
    const {game, M} = fresh(6000);
    check('a fresh campaign: the foot line gives the one first step in the game\'s voice', M.first_step() === 'Закажите первую постройку — «Заготовка под корабль».', M.first_step());
    M.order(K('airship_hull_1'));
    check('after the first order the first step is no longer given', M.first_step() === null);
    const before = M.message();
    check('a refused click: the foot line says the window\'s reason, the line before it gone', M.refuse(K('beer_hall_1')) && M.message() === M.reason(K('beer_hall_1')) && M.message() !== before, M.message());
    check('a click on what can be ordered is not a refusal', !M.refuse(K('airship_hull_1')));
}

// ---- 3. what a turn brought to the ship ----
{
    const {game, M} = fresh();
    const build = id => { M.order(K(id)); const t = M.level(K(id)).turns; for (let i = 0; i < t; i++) game.end_turn(); };
    build('airship_hull_1');
    build('airship_hull_2');
    const n2 = M.ship_news();
    check('the hull built: the turn\'s news has the barge, the tab\'s mark is on', n2 && n2.built.includes(K('airship_hull_2')) && n2.parts.includes('barge') && M.ship_unseen(), n2);
    M.ship_seen();
    check('«Корабль» looked at: the mark is off', !M.ship_unseen());
    M.order(K('mtb_nest_1'));
    for (let i = 0; i < M.level(K('mtb_nest_1')).turns; i++) game.end_turn();
    const n3 = M.ship_news();
    check('the crows\' nests built: their rings on the drawing, the nests\' crew place opened, the mark on', n3 && n3.parts.includes('rings') && n3.places.includes('cupolas') && M.ship_unseen(), n3);
    check('the foot line names it in the player\'s words', M.message() === 'Построено: «Вороньи гнёзда». Открыто место экипажа «Гнёзда».', M.message());
    game.end_turn();
    check('the next turn: no news (the glow was for that turn), the mark stays until «Корабль» is looked at', M.ship_news() === null && M.ship_unseen());
    const saved = JSON.parse(JSON.stringify(M.news_snapshot()));
    const again = fresh();
    again.game.restore(game.snapshot());
    again.M.set_news_silently(saved);
    again.M.sync_ship();
    check('a reload keeps the mark', again.M.ship_unseen());
    // a building that adds nothing to the ship: no news of the ship, no mark
    M.ship_seen();
    M.order(K('engines_1'));
    for (let i = 0; i < M.level(K('engines_1')).turns; i++) game.end_turn();
    const n4 = M.ship_news();
    check('a building with nothing on the ship: built named, no detail, no place, no mark', n4 && n4.built.length === 1 && !n4.parts.length && !n4.places.length && !M.ship_unseen() && M.message().startsWith('Построено: «Машинное отделение».'), {n4, m: M.message()});
    check('every crew place has a building that opens it', ['rifles', 'cannons', 'bombs', 'cupolas', 'harpoon'].every(g => M.place_opener(g)), ['rifles', 'cannons', 'bombs', 'cupolas', 'harpoon'].map(g => M.place_opener(g) && M.place_opener(g).name));
    // a new kind in a place already open is news too: «Гнёзда с боеукладкой» gives the nests «Топоры»
    M.ship_seen();
    const n2key = levels.tree_rows.find(r => r.name === 'Гнёзда с боеукладкой').key;
    for (const k of M.missing(n2key)) if (!k.startsWith('tier:')) M.debug_build_to(k);
    game.end_turn();
    game.gold = 1e6;
    M.ship_seen();
    if (M.status(n2key).state === 'open') { M.order(n2key); for (let i = 0; i < M.level(n2key).turns; i++) game.end_turn(); }
    const n5 = M.ship_news();
    check('a new kind in an open place: «!» on the tab, the place among the turn\'s news, the foot line says it in the player\'s words',
        M.status(n2key).state === 'built' && n5 && n5.kinds.includes('cupolas:axes') && !n5.places.includes('cupolas') && M.news_places().includes('cupolas') && M.ship_unseen()
        && M.message().startsWith('Построено: «Гнёзда с боеукладкой».') && M.message().includes('В гнёздах теперь доступны «Топоры».'), {n5, m: M.message(), unseen: M.ship_unseen()});
    // every place has its own words for a new kind
    const said = ['rifles', 'cannons', 'bombs', 'cupolas', 'harpoon'].map(g => M.new_kinds_text(g, ['X']));
    check('each place says a new kind in its own words, one sentence', new Set(said).size === 5 && said.every(s => /^[А-Я].*«X»\.$/.test(s)), said);
    // the foot line through a reload
    const msg = M.message(), snap = JSON.parse(JSON.stringify(M.message_snapshot()));
    const re = fresh();
    re.game.restore(game.snapshot());
    re.M.set_message_silently(snap);
    check('the foot line survives a reload (saved with the state)', re.M.message() === msg, {was: msg, now: re.M.message()});
}

// ---- 4. the small cards over a slot ----
{
    const it = (crew, tier = 0, k = '') => ({crew, tier, k});
    const nine = [it(false, 3, 'a'), it(true, 0, 'c1'), it(false, 1, 'b'), it(true, 0, 'c2'), ...Array.from({length: 5}, (_, i) => it(false, 2, 'x' + i))];
    const r = T.slotCards(nine);
    check('nine units: two cards and «+7»; the crew aboard first', r.shown.length === 2 && r.folded.length === 7 && r.shown.every(x => x.crew), r.shown.map(x => x.k));
    const three = T.slotCards([it(false, 2, 'b'), it(false, 1, 'a'), it(true, 0, 'c')]);
    check('three units: all three, the crew first, then by tier', three.shown.map(x => x.k).join() === 'c,a,b' && !three.folded.length);
    // every slot of the author's tree: the cards of what the level brings new in its line (newOnLevel), at most three in its row
    const cardOf = u => { const g = data.groups[u.group], o = g && g.options[u.option]; return o && o.unit_card && u.option !== g.mount; };
    const rows = levels.tree_rows.map(row => {
        const crew = row.unlocks_new.filter(cardOf);
        const r2 = T.slotCards([...crew.map(() => it(true)), ...row.units_new.map(() => it(false, 1))]);
        return {name: row.name, items: r2.shown.length + (r2.folded.length ? 1 : 0), all: r2.shown.length + r2.folded.length};
    });
    check('every slot of the author\'s tree has at most three cards in its row (the rest in «+N»)', rows.every(r => r.items <= 3), rows.filter(r => r.items > 3));
    const folding = rows.filter(r => r.all > 3);
    console.log('     slots that still fold into «+N» after the line rule: ' + (folding.map(r => `${r.name} (${r.all} new)`).join(', ') || 'none'));
    // no unit card on two levels of one line: what a level shows is never shown by a level below it in the same line
    const byKey = Object.fromEntries(levels.tree_rows.map(r => [r.key, r]));
    const twice = [];
    for (const n of design.nodes) {
        const line = T.lineOf(design, n.id).ids;
        if (line.length < 2) continue;
        const seen = new Map();
        for (const id of line) {
            const r = byKey[K(id)];
            for (const k of [...r.unlocks_new.filter(cardOf).map(u => 'crew ' + u.group + ':' + u.option), ...r.units_new.map(u => 'unit ' + u)]) {
                if (seen.has(k) && seen.get(k) !== id) twice.push(`${r.name}: ${k} (also on ${byKey[K(seen.get(k))].name})`);
                seen.set(k, seen.get(k) || id);
            }
        }
    }
    check('no unit card appears on two levels of the same line of the author\'s tree (a level shows only what it brings new)', !twice.length, [...new Set(twice)].slice(0, 8));
    // one unit, one card: a level that opens a kind aboard and the same unit for the army shows the crew's card once
    const ocu = T.oneCardPerUnit([{group: 'rifles', option: 'thunderers'}, {group: 'rifles', option: 'rakers'}], ['wh_main_dwf_inf_thunderers_0', 'wh_main_dwf_inf_rangers_0', 'wh_main_dwf_inf_thunderers_0'],
        c => ({thunderers: 'wh_main_dwf_inf_thunderers_0', rakers: 'wh3_dlc25_dwf_inf_thunderers_grudge_rakers'})[c.option]);
    check('oneCardPerUnit: a unit both aboard and for the army is one crew card (marked army), the army list keeps only the others, once each',
        ocu.crew[0].army === 'wh_main_dwf_inf_thunderers_0' && ocu.crew[1].army === null && ocu.units.join() === 'wh_main_dwf_inf_rangers_0', ocu);
    const unitOf = T.crewUnitOf(data.groups);
    check('every crew kind with a card knows the game\'s unit it is taken from (build/web/data.json, option.unit)', Object.values(data.groups).every(g => Object.values(g.options).every(o => !o.unit_card || o.unit)));
    const doubled = [], merged = [];
    for (const r of levels.tree_rows) {
        const crewUnits = r.unlocks_new.filter(cardOf).map(unitOf).filter(Boolean);
        for (const u of r.units_new) if (crewUnits.includes(u)) doubled.push(`${r.name}: ${u}`);
        if (new Set(r.units_new).size !== r.units_new.length) doubled.push(`${r.name}: an army unit twice`);
        for (const c of r.unlocks_new) if (c.army) merged.push(`${r.name}: ${data.groups[c.group].options[c.option].name}`);
    }
    check(`no slot shows one unit twice (a crew card and an army card of the same unit): one card, the crew's (${merged.join('; ')})`, !doubled.length && merged.length >= 2, doubled);
    const tirRow = levels.tree_rows.find(r => r.name === 'Тир'), hall = levels.tree_rows.find(r => r.name === 'Пивной чертог');
    const plateOf = r => T.slotCards([...r.unlocks_new.filter(cardOf).map(() => it(true)), ...r.units_new.map(() => it(false, 1))]);
    check('«Тир»: «Громобои» once; «Пивной чертог»: «Мстители-пираты» once; «+N» counts unique units',
        tirRow.unlocks_new.some(c => c.option === 'thunderers' && c.army) && !tirRow.units_new.includes('wh_main_dwf_inf_thunderers_0') && hall.unlocks_new.some(c => c.option === 'pirates' && c.army) && !hall.units_new.includes('wh3_dlc25_dwf_inf_slayer_pirates')
        && plateOf(tirRow).shown.length + plateOf(tirRow).folded.length === new Set([...tirRow.unlocks_new.filter(cardOf).map(unitOf), ...tirRow.units_new]).size, {tir: tirRow.unlocks_new, tu: tirRow.units_new});
    // «Вид на корабле»: a detail told once in its line, on the level that first brings it
    const partsTwice = [];
    for (const n of design.nodes) {
        const line = T.lineOf(design, n.id).ids;
        const seen = new Set();
        for (const id of line) for (const p of byKey[K(id)].parts_new) { const k = p.part || p.name; if (seen.has(k)) partsTwice.push(`${byKey[K(id)].name}: ${k}`); seen.add(k); }
    }
    const hulls = levels.tree_rows.filter(r => /корпус|каркас|Заготовка/i.test(r.name));
    check('«Вид на корабле» only on the level that first brings the detail in its line (no «Базовая барка» on four hull levels)', !partsTwice.length && hulls.filter(r => r.parts_new.some(p => p.part === 'barge')).length === 1, [...new Set(partsTwice)].slice(0, 6));
    const tir = levels.tree_rows.find(r => r.name === 'Тир'), dummies = levels.tree_rows.find(r => r.name === 'Манекен для учебной стрельбы');
    check('«Тир» shows only what «Манекен» below it did not: the thunderers and rakers, the Thunderers\' army units; its window still lists all it allows',
        !tir.unlocks_new.some(u => dummies.unlocks.some(x => x.group === u.group && x.option === u.option)) && !tir.units_new.some(u => dummies.units.includes(u))
        && tir.unlocks.length > tir.unlocks_new.length && tir.units.length > tir.units_new.length, {crew: tir.unlocks_new, units: tir.units_new});
}

// ---- 5. the tree's lines: a join is a dot, a crossing a gap ----
{
    // two links into one building from either side join under it; a third link from elsewhere climbs through their line
    const links = [{from: 'a', to: 'c', segs: [[0, 200, 0, 100], [0, 100, 100, 100], [100, 100, 100, 74]]},
                   {from: 'b', to: 'c', segs: [[200, 200, 200, 100], [200, 100, 100, 100]]},
                   {from: 'd', to: 'e', segs: [[50, 300, 50, 0]]}];
    const m = T.lineMarks(links);
    check('two links into one building: a junction where they meet', m.junctions.some(([x, y]) => x === 100 && y === 100), m.junctions);
    check('a line of another building through them: a crossing, not a junction', m.crossings.length === 1 && m.crossings[0].x === 50 && m.crossings[0].y === 100 && !m.junctions.some(([x]) => x === 50), m);
    // the author's tree: every crossing is between links that share no building
    const pos = {};
    const c0 = Math.min(...levels.tree_rows.map(r => r.col)), r1 = Math.max(...levels.tree_rows.map(r => r.row));
    for (const r of levels.tree_rows) pos[r.key] = {x: 16 + (r.col - c0) * T.GRID, y: 30 + (r1 - r.row) * T.GRID};
    const blocked = T.slotsBlock(Object.values(pos));
    const all = [];
    for (const r of levels.tree_rows) for (const p of r.requires) if (pos[p]) all.push({from: p, to: r.key, segs: T.linkSegments(pos[p], pos[r.key], blocked)});
    const mm = T.lineMarks(all);
    const owner = s => all.find(l => l.segs.includes(s));
    check(`the author's tree: ${mm.crossings.length} crossings and ${mm.junctions.length} junctions; no crossing between links that share a building`,
        mm.crossings.every(c => { const a = owner(c.h), b = owner(c.v); return a.from !== b.from && a.to !== b.to; }) && mm.junctions.length > 0);
}

// ---- 6. numbers as the player reads them ----
{
    // the ammunition: the group's whole is the number (the mod rounds the whole); a place's share «по N» only when whole, else «около N»
    const bombs = data.groups.bombs.options.stock;
    const a = C.crewAmmo(bombs.numbers, 130, bombs.unit_card.men), a0 = C.crewAmmo(bombs.numbers, 0, bombs.unit_card.men);
    check('the bombs with +130%: 258 for the group (112 × 2,3 = 257,6 → 258), «4 люка, около 65 на люк»; without the bonus «4 люка по 28»',
        a.total === 258 && C.ammoShare(a, 'bombs', 'на люк') === '4 люка, около 65 на люк' && C.ammoShare(a0, 'bombs', 'на люк') === '4 люка по 28', {a, a0});
    // the riflemen: 11 men (Malakai takes the twelfth seat): 11 places, the whole for 11
    const pir = data.groups.rifles.options.pirates, ap = C.crewAmmo(pir.numbers, 0, pir.unit_card.men);
    check('the riflemen count 11 places, as the men on their card (the data still has 12 seats): 11 × 6 = 66, «11 стрелков по 6»', ap.places === 11 && ap.total === 66 && C.ammoShare(ap, 'rifles', 'на стрелка') === '11 стрелков по 6', ap);
    // every pair of numbers a panel shows is consistent, for every kind and bonus: places × share = whole when «по», |whole / places − share| < 0.5 when
    // «около»; the bonus line «(base → total)» is base × (1 + pct) rounded as the mod rounds
    const wrong = [];
    for (const [g, grp] of Object.entries(data.groups)) for (const [k, o] of Object.entries(grp.options)) {
        if (!o.numbers || !o.numbers.seats) continue;
        for (const p of [0, 5, 15, 30, 50, 100, 130, 300]) {
            const x = C.crewAmmo(o.numbers, p, o.unit_card ? o.unit_card.men : 0), line = C.ammoShare(x, g, 'на место');
            const m = /^(\d+) \S+ (?:по (\d+)|, около (\d+) на место)$/.exec(line.replace(/^(\d+) (\S+), около/, '$1 $2 , около'));
            const places = m && Number(m[1]), each = m && Number(m[2] || m[3]);
            if (!m || places !== x.places) { wrong.push(`${g}:${k} +${p}%: «${line}»`); continue; }
            if (m[2] && places * each !== x.total) wrong.push(`${g}:${k} +${p}%: ${places} × ${each} ≠ ${x.total}`);
            if (m[3] && (Number.isInteger(x.total / places) || Math.abs(x.total / places - each) > 0.5)) wrong.push(`${g}:${k} +${p}%: «около ${each}» for ${x.total} / ${places}`);
            if (x.total !== Math.floor(x.base * (1 + p / 100) + 0.5)) wrong.push(`${g}:${k} +${p}%: ${x.base} → ${x.total}`);
            if (x.places !== (o.unit_card && o.unit_card.men < o.numbers.seats ? o.unit_card.men : o.numbers.seats)) wrong.push(`${g}:${k}: ${x.places} places for ${o.unit_card && o.unit_card.men} men`);
        }
    }
    check('every crew\'s ammunition: the places × the share is the whole («по»), or the share is the nearest whole and marked «около»; the bonus line base → total as the mod rounds', !wrong.length, wrong.slice(0, 6));
    // the building window's placement: under the title row when it fits, else over it, always inside the screen
    const top = (want, h) => infoTop(want, h, 900, 15, 66);
    check('a building window: under the title row when it fits; a taller one over the title row, inside the screen; never cut',
        top(500, 300) === 500 && top(10, 300) === 66 && top(700, 300) === 900 - 4 - 15 - 300 && top(100, 850) === 900 - 4 - 15 - 850 && top(100, 850) < 66 && top(100, 850) + 15 >= 4, [top(500, 300), top(10, 300), top(700, 300), top(100, 850)]);
    check('percent close to the number and a decimal comma, as the game\'s Russian texts', gameText('Меткость стрелков барки: +5 %') === 'Меткость стрелков барки: +5%' && gameText('16.6') === '16,6' && gameText('Боезапас +100 % (13 → 26 залпов)') === 'Боезапас +100% (13 → 26 залпов)');
}

console.log(failed ? `failed: ${failed}` : 'failed: 0');
process.exit(failed ? 1 : 0);
