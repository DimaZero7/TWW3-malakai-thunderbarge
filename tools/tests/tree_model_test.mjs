// The constructor's model of the tree (web/js/tree_model.mjs): node tools/tests/tree_model_test.mjs (from the repository's root)
// The operations, links and their checks, undo and redo, copy and paste, the file's text and the reading of a broken file, the warnings, the mod's
// buildings as nodes, the working file web/data/tree_design.json and the start fixture tools/tests/tree_design_start.json. Prints a line a check, exit 1 on any failure.
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import * as T from '../../web/js/tree_model.mjs';
import * as FX from '../../web/js/effects_model.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const json = p => JSON.parse(readFileSync(join(root, p), 'utf-8'));
let failed = 0;
const check = (name, ok, extra = '') => { if (!ok) failed++; console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok ? '' : '  ' + extra)); };

// 1. nodes and links
{
    const d = T.emptyDesign();
    const a = T.addNode(d, {name: 'A', cost: 100, col: 0, row: 0});
    const b = T.addNode(d, {name: 'B', cost: 100, col: 0, row: 1});
    const c = T.addNode(d, {name: 'C', cost: 100, col: 1, row: 1});
    const e = T.addNode(d, {name: 'E', cost: 100, col: 0, row: 2});
    check('ids are n1..n4', [a, b, c, e].join() === 'n1,n2,n3,n4', [a, b, c, e].join());
    check('link A -> B', T.addEdge(d, a, b).ok && T.byId(d, b).requires.includes(a));
    check('link A -> C', T.addEdge(d, a, c).ok);
    check('two parents: B -> E and C -> E', T.addEdge(d, b, e).ok && T.addEdge(d, c, e).ok && T.byId(d, e).requires.join() === `${b},${c}`);
    check('the same link twice is refused', !T.addEdge(d, a, b).ok);
    check('a link to itself is refused', !T.addEdge(d, a, a).ok);
    const cyc = T.addEdge(d, e, a);
    check('a cycle is refused with a reason', !cyc.ok && /круг/.test(cyc.why), cyc.why);
    check('no cycle in the tree', !T.hasCycle(d));
    check('children of A', T.children(d, a).join() === `${b},${c}`);
    const d2 = T.emptyDesign();
    const x = T.addNode(d2, {name: 'X'}), y = T.addNode(d2, {name: 'Y'}), z = T.addNode(d2, {name: 'Z'});
    T.addEdge(d2, x, y);
    check('reverse X -> Y gives Y -> X', T.reverseEdge(d2, x, y).ok && T.byId(d2, x).requires.join() === y && !T.byId(d2, y).requires.length);
    T.deleteEdge(d2, y, x);
    T.addEdge(d2, x, y); T.addEdge(d2, x, z); T.addEdge(d2, z, y);      // X -> Y, X -> Z, Z -> Y
    const rv = T.reverseEdge(d2, x, y);               // Y -> X would make X -> Z -> Y -> X
    check('a reverse that makes a cycle is refused and the link stays', !rv.ok && T.byId(d2, y).requires.includes(x) && !T.hasCycle(d2), rv.why);
    const r = T.deleteNodes(d, [c]);
    check('delete a node with two links: its links go too', r.nodes === 1 && r.links === 2 && T.byId(d, e).requires.join() === b && !T.byId(d, c), JSON.stringify(r));
    check('delete an edge', T.deleteEdge(d, a, b) && !T.byId(d, b).requires.length);
    T.moveNodes(d, [a, b], 2, 3);
    check('move a group', T.byId(d, a).col === 2 && T.byId(d, a).row === 3 && T.byId(d, b).col === 2 && T.byId(d, b).row === 4);
    check('a free cell beside a taken one', JSON.stringify(T.freeCell(d, 2, 3)) !== JSON.stringify({col: 2, row: 3}) && !T.cellTaken(d, T.freeCell(d, 2, 3).col, T.freeCell(d, 2, 3).row));
}
// 2. undo and redo, typing joined into one step
{
    const h = new T.History(T.emptyDesign());
    let id;
    h.commit('новый узел', d => { id = T.addNode(d, {name: ''}); });
    h.commit('название', d => T.updateNode(d, id, {name: 'П'}), 'name:' + id, 1000);
    h.commit('название', d => T.updateNode(d, id, {name: 'Пи'}), 'name:' + id, 1500);
    h.commit('название', d => T.updateNode(d, id, {name: 'Пив'}), 'name:' + id, 2000);
    check('typing is one step', h.past.length === 2 && T.byId(h.current, id).name === 'Пив', h.past.length);
    h.commit('название', d => T.updateNode(d, id, {name: 'Пиво'}), 'name:' + id, 9000);
    check('after a pause a new step', h.past.length === 3);
    check('no change, no step', !h.commit('ничего', () => {}).changed && h.past.length === 3);
    const id2 = (h.commit('второй', d => T.addNode(d, {name: 'B'})), h.current.nodes[1].id);
    h.commit('связь', d => T.addEdge(d, id, id2));
    for (let i = 0; i < 20; i++) h.commit('сдвиг', d => T.moveNodes(d, [id2], 1, 0));
    check('a long chain: 20 moves', T.byId(h.current, id2).col === 20);
    let n = 0; while (h.undo()) n++;
    check('undo all the way: empty', h.current.nodes.length === 0 && n === 25, n);
    let m = 0; while (h.redo()) m++;
    check('redo all the way: the same tree', m === 25 && T.byId(h.current, id2).col === 20 && T.byId(h.current, id2).requires.join() === id && T.byId(h.current, id).name === 'Пиво');
    h.undo(); h.undo();
    h.commit('другое', d => T.updateNode(d, id, {cost: 5}));
    check('a new step after undo drops the redo', !h.canRedo);
}
// 3. copy, paste, duplicate
{
    const d = T.emptyDesign();
    const a = T.addNode(d, {name: 'A', col: 0, row: 0}), b = T.addNode(d, {name: 'B', col: 0, row: 1}), c = T.addNode(d, {name: 'C', col: 3, row: 0});
    T.addEdge(d, a, b); T.addEdge(d, c, b);
    const clip = T.copyNodes(d, [a, b]);
    check('copy keeps only the inner links', clip.nodes.length === 2 && clip.nodes[1].requires.join() === a);
    const ids = T.pasteNodes(d, clip, 0, 0);
    const na = T.byId(d, ids[0]), nb = T.byId(d, ids[1]);
    check('paste: new ids, a free place, the inner link', ids.length === 2 && !ids.includes(a) && nb.requires.join() === na.id && !T.cellTaken({nodes: d.nodes.filter(n => !ids.includes(n.id))}, na.col, na.row), JSON.stringify([na, nb].map(n => [n.col, n.row])));
    const dup = T.duplicateNodes(d, [c]);
    check('duplicate one node: beside it, the same name, no links', dup.length === 1 && T.byId(d, dup[0]).name === 'C' && T.byId(d, dup[0]).col === 4 && !T.byId(d, dup[0]).requires.length);
}
// 4. the file: stable text, read back the same; a broken file read with its problems told
{
    const d = T.emptyDesign();
    const a = T.addNode(d, {name: 'Корпус', cost: 700, mod_key: 'airship_hull_1', effects: [{text: 'Рост: +10', icon: null, good: true}], crew: [{group: 'rifles', option: 'pirates'}]});
    T.addEdge(d, a, T.addNode(d, {name: 'Б', cost: 1}));
    const text = T.serialize(d);
    const back = T.normalize(JSON.parse(text));
    check('text -> design -> text is the same', T.serialize(back.design) === text && !back.problems.length);
    check('keys in a fixed order', text.indexOf('"id"') < text.indexOf('"col"') && text.indexOf('"note"') < text.indexOf('"requires"'));
    const broken = T.normalize({nodes: [{id: 'a', requires: ['zz', 'a']}, {id: 'a', cost: '12', tier: '3', branch: 'pink'}, 5]});
    check('a broken file: links to nothing and to itself gone, ids made unique, numbers read', broken.design.nodes.length === 2 && !broken.design.nodes[0].requires.length
        && broken.design.nodes[1].id === 'a_2' && broken.design.nodes[1].cost === 12 && broken.design.nodes[1].tier === 3 && broken.design.nodes[1].branch === null && broken.problems.length === 4, JSON.stringify(broken.problems));
    check('not a tree at all', T.normalize('x').problems.length === 1 && T.normalize('x').design.nodes.length === 0);
}
// 5. the warnings
{
    const d = T.emptyDesign();
    const a = T.addNode(d, {name: 'Корень', cost: 1, mod_key: 'airship_hull_1', col: 0, row: 0});
    const b = T.addNode(d, {name: '', cost: 0, col: 0, row: 1});
    const c = T.addNode(d, {name: 'Сам по себе', cost: 5, col: 0, row: 1, mod_key: 'beer_hall_1'});
    T.addNode(d, {name: 'Второй', cost: 5, col: 2, row: 1, mod_key: 'beer_hall_1', tier: 4});
    T.addEdge(d, a, b);
    const w = T.warnings(d, {modKeys: new Set(['airship_hull_1', 'beer_hall_1'])});
    const kinds = w.map(x => x.kind).sort().join();
    check('warnings: no name, no cost, two orphans, a key twice, a cell twice, no hull for tier 4', kinds === 'cost,dup_key,name,orphan,orphan,overlap,tier', kinds);
    check('the orphan named', w.some(x => x.kind === 'orphan' && x.nodes[0] === c));
    const cyc = T.normalize({nodes: [{id: 'p', requires: ['q']}, {id: 'q', requires: ['p']}]}).design;
    check('a cycle read from a file is found', T.hasCycle(cyc) && T.warnings(cyc).some(x => x.kind === 'cycle'));
}
// 5b. the lines: straight up between neighbours, round a building that stands on the way
{
    const a = {x: 0, y: 212}, b = {x: 0, y: 0}, mid = {x: 0, y: 106};
    check('a line straight up when nothing is between', JSON.stringify(T.linkSegments(a, b, T.slotsBlock([a, b]))) === JSON.stringify([[37, 212, 37, 74]]));
    const seg = T.linkSegments(a, b, T.slotsBlock([a, b, mid]));
    check('a line goes round a building on its way, in the lane between columns', seg.length === 5 && seg[2][0] === 37 + 53 && seg.every(([x0, y0, x1, y1]) => !(x0 === 37 && x1 === 37 && Math.min(y0, y1) < 180 && Math.max(y0, y1) > 106)), JSON.stringify(seg));
}
// 5d. the constructor's lines take the shortest way: straight up a free column, round only what stands on it, one step to the next column
{
    const route = (d, a, b) => T.cxRoutes(d)[a + '|' + b];
    for (const gap of [1, 2, 4]) {
        const d = T.emptyDesign();
        const a = T.addNode(d, {name: 'A', col: 0, row: 0}), b = T.addNode(d, {name: 'B', col: 0, row: gap + 1});
        T.addNode(d, {name: 'Сосед', col: 1, row: 1});         // a building in the next column changes nothing
        T.addEdge(d, a, b);
        const r = route(d, a, b), ca = T.cxCard(T.byId(d, a)), cb = T.cxCard(T.byId(d, b));
        check(`the same column over ${gap} empty row(s): a straight line of two points, middle to middle`, r.length === 2 && r[0][0] === ca.cx && r[1][0] === cb.cx, r);
    }
    const d = T.emptyDesign();
    const a = T.addNode(d, {name: 'A', col: 0, row: 0}), b = T.addNode(d, {name: 'B', col: 0, row: 3}), mid = T.addNode(d, {name: 'Посередине', col: 0, row: 2});
    T.addEdge(d, a, b);
    let r = route(d, a, b);
    const cm = T.cxCard(T.byId(d, mid), 1);
    const crosses = r.slice(1).some((q, i) => { const p = r[i]; const x0 = Math.min(p[0], q[0]), x1 = Math.max(p[0], q[0]), y0 = Math.min(p[1], q[1]), y1 = Math.max(p[1], q[1]); return x0 < cm.x + cm.w && x1 > cm.x && y0 < cm.bottom && y1 > cm.y; });
    check('a building on the way: the line goes round it', r.length > 2 && !crosses, r);
    T.deleteNodes(d, [mid]);
    r = route(d, a, b);
    check('the building taken away: straight again', r.length === 2);
    const e = T.emptyDesign();
    const p = T.addNode(e, {name: 'P', col: 1, row: 0});
    const l = T.addNode(e, {name: 'L', col: 0, row: 1}), s = T.addNode(e, {name: 'S', col: 1, row: 1}), rr = T.addNode(e, {name: 'R', col: 2, row: 1});
    for (const c of [rr, s, l]) T.addEdge(e, p, c);
    const R = T.cxRoutes(e), cp = T.cxCard(T.byId(e, p));
    const sx = k => R[p + '|' + k][0][0];
    check('three children left, straight, right: exits left, middle, right', sx(l) < sx(s) && sx(s) === cp.cx && sx(rr) > sx(s) && R[p + '|' + s].length === 2, [sx(l), sx(s), sx(rr)]);
    check('a child one row up in the next column: one step (two bends)', T.bends(R[p + '|' + l]) === 2 && T.bends(R[p + '|' + rr]) === 2);
    // the game's column: straight up a free column, round a building in the way
    const g0 = {x: 0, y: 318}, g1 = {x: 0, y: 0}, gm = {x: 0, y: 106};
    check('the game: the same column over empty rows, one straight piece', T.linkSegments(g0, g1, T.slotsBlock([g0, g1])).length === 1);
    check('the game: a building in the way, round it', T.linkSegments(g0, g1, T.slotsBlock([g0, g1, gm])).length === 5);
}
// 5c. the constructor's grid: on the stand of 26 buildings every link has its own way, from the parent's slot top to the child's card bottom,
// and no two links share a stretch of line; the warnings of the game's building window
{
    const {standDesign} = await import('./constructor_stand.mjs');
    const d = standDesign(json('tools/tests/tree_design_start.json'));
    const routes = T.cxRoutes(d, n => (n.name.length > 40 ? 3 : n.name.length > 18 ? 2 : 1));
    const keys = Object.keys(routes);
    check('stand: a way for each of the 35 links', keys.length === 35 && T.edges(d).length === 35);
    const ends = keys.every(k => { const [f, t] = k.split('|'), p = routes[k], a = T.cxCard(T.byId(d, f)), c = T.cxCard(T.byId(d, t), T.byId(d, t).name.length > 40 ? 3 : T.byId(d, t).name.length > 18 ? 2 : 1);
        return p[0][1] === a.slotY && Math.abs(p[0][0] - a.cx) <= 28 && p[p.length - 1][1] === c.bottom + 3 && Math.abs(p[p.length - 1][0] - c.cx) <= 28; });
    check('stand: out of the parent\'s slot top, into the child\'s card bottom', ends);
    const segs = keys.flatMap(k => routes[k].slice(1).map((q, i) => ({k, a: routes[k][i], b: q})));
    let shared = 0;
    for (let i = 0; i < segs.length; i++) for (let j = i + 1; j < segs.length; j++) {
        const s = segs[i], t = segs[j];
        if (s.k === t.k) continue;
        const hor = s.a[1] === s.b[1] && t.a[1] === t.b[1] && s.a[1] === t.a[1], ver = s.a[0] === s.b[0] && t.a[0] === t.b[0] && s.a[0] === t.a[0];
        const lo = (x, y) => Math.max(Math.min(x[0], x[1]), Math.min(y[0], y[1])), hi = (x, y) => Math.min(Math.max(x[0], x[1]), Math.max(y[0], y[1]));
        if (hor && hi([s.a[0], s.b[0]], [t.a[0], t.b[0]]) - lo([s.a[0], s.b[0]], [t.a[0], t.b[0]]) > 2) shared++;
        if (ver && hi([s.a[1], s.b[1]], [t.a[1], t.b[1]]) - lo([s.a[1], s.b[1]], [t.a[1], t.b[1]]) > 2) shared++;
    }
    check('stand: no two links share a stretch of line', shared === 0, String(shared));
    const flag = d.nodes.find(n => n.name === 'Флагман');
    check('the game\'s window: a description too long for it is warned of', T.warnings(d).some(w => w.kind === 'info_desc' && w.nodes[0] === flag.id));
    check('the game\'s window: a short description is not', !T.warnings(d).some(w => w.kind === 'info_desc' && w.nodes[0] !== flag.id));
}
// 6. the mod's buildings as nodes, the start file, the game's levels
{
    const data = json('build/web/data.json'), ov = json('build/web/overview.json');
    const cards = {};
    for (const ch of ov.chains) for (const k of ch.cards) cards[k.key] = k;
    const all = [...data.hull, ...data.chains.flatMap(c => c.levels)];
    const beer = all.find(r => r.short === 'beer_hall_1');
    const f = T.fromModLevel(beer, cards[beer.key], data);
    check('a mod level as a node: name, cost, icon, effects, crew', f.name === beer.name && f.cost === beer.cost && f.icon.endsWith('beer_hall_1.png') && f.effects.length > 0 && f.crew.some(c => c.option === 'pirates'));
    check('the mod says beer hall 2 needs beer hall 1', T.modNeeds(all.find(r => r.short === 'beer_hall_2'), data).includes('beer_hall_1'));
    // the working file (the author's tree, whatever it holds now) reads cleanly and is in the file's own text; the four start nodes (a fixture,
    // tools/tests/tree_design_start.json) also have no warning and keep the mod's keys in the game
    const work = T.normalize(json('web/data/tree_design.json'));
    check('the working file reads without problems', !work.problems.length, work.problems.join('; '));
    // format 2 is written in its own text; a format 1 file (the author's before this version) reads with every field it had, and its text written
    // again as format 2 reads back the same
    const workText = readFileSync(join(root, 'web/data/tree_design.json'), 'utf-8');
    if (json('web/data/tree_design.json').format >= T.FORMAT) check('the working file is in its own text', T.serialize(work.design) === workText);
    else check('the working file (an older format) reads into the new one and back the same', work.from < T.FORMAT && T.serialize(T.normalize(JSON.parse(T.serialize(work.design))).design) === T.serialize(work.design)
        && work.design.nodes.every((n, i) => JSON.stringify(n.effects.map(e => ({...e, id: undefined}))) === JSON.stringify(json('web/data/tree_design.json').nodes[i].effects.map(e => ({...e, id: undefined})))));
    const start = T.normalize(json('tools/tests/tree_design_start.json'));
    check('the start file: no warnings', !T.warnings(start.design, {modKeys: new Set(all.map(r => r.short))}).length, JSON.stringify(T.warnings(start.design)));
    const g = T.gameData(start.design, data);
    check('game levels keep the mod keys', g.chains.map(c => c.key).join() === start.design.nodes.map(n => data.prefix + n.mod_key).join());
    check('hull tiers from the nodes', g.hull_tiers[data.prefix + 'airship_hull_2'] === 2);
}
// 9. format 2: effects of the catalogue, army units, the ship's details; format 1 read as it was
{
    const data = json('build/web/data.json');
    let catalog = {game_effects: [], army_units: []};
    try { catalog = json('build/web/catalog.json'); } catch (e) { /* run tools/web_export.py --catalog */ }
    const ctx = {groups: data.groups, gameEffects: Object.fromEntries(catalog.game_effects.map(g => [g.key, g]))};
    check('the catalogue of the export: game effects and army units', catalog.game_effects.length > 50 && catalog.army_units.length > 10, `${catalog.game_effects.length} / ${catalog.army_units.length}`);
    const old = {format: 1, nodes: [{id: 'a', name: 'Old', cost: 5, effects: [{text: 'Строка', icon: null, good: true}]}]};
    const r = T.normalize(old);
    check('format 1 reads: units and parts empty, the line as it was', r.from === 1 && r.design.format === T.FORMAT && !r.design.nodes[0].units.length && !r.design.nodes[0].parts.length && r.design.nodes[0].effects[0].text === 'Строка');
    // the crew's effects by group
    const ammo = FX.complete({kind: 'ammo', target: 'rifles', value: 25}, ctx);
    check('ammo of the riflemen: the line after the mod\'s pattern, green', ammo.text === 'Боезапас стрелков: +25 %' && ammo.good, ammo.text);
    const all = FX.complete({kind: 'ammo', target: 'all', value: 25}, ctx);
    check('ammo of every crew', all.text === 'Боезапас каждой команды: +25 %');
    const reload = FX.complete({kind: 'reload', target: 'cannons', value: -10}, ctx);
    check('a shorter reload is green, a longer one red', reload.good && !FX.complete({kind: 'reload', target: 'cannons', value: 10}, ctx).good);
    const slow = FX.complete({kind: 'battle_speed', value: -5}, ctx);
    check('-5 % speed in battle is red', !slow.good && slow.text === 'Скорость барки на поле боя: -5 %', slow.text);
    const cheap = FX.complete({kind: 'game', effect: 'wh_main_effect_force_all_campaign_recruitment_cost', value: -10}, ctx);
    check('-10 % recruitment cost is green, the game\'s text and icon', cheap.good && cheap.text === 'Стоимость найма: -10%' && /treasury/.test(cheap.icon), JSON.stringify(cheap));
    const own = FX.complete({kind: 'ammo', target: 'rifles', value: 30, own_text: true, text: 'Мой текст'}, ctx);
    check('the author\'s own text stays, the structure with it', own.text === 'Мой текст' && own.kind === 'ammo' && own.value === 30);
    // the author's lines read as effects (the typos of his tree too), never changed without the click
    const rec = t => FX.recognize(t, ctx).map(e => `${e.kind}${e.target ? ':' + e.target : ''}${e.effect && e.kind === 'game' ? ':' + e.effect : ''}=${e.value}`).join(' ');
    check('"Боезапас каждой команды: +25 %"', rec('Боезапас каждой команды: +25 %') === 'ammo:all=25', rec('Боезапас каждой команды: +25 %'));
    check('"Меткость стрелков: +5 %"', rec('Меткость стрелков: +5 %') === 'accuracy:rifles=5');
    check('"Дальность и меткость орудий: +10 %": two', rec('Дальность и меткость орудий: +10 %') === 'range:cannons=10 accuracy:cannons=10');
    check('"Скорость бараки на поле боя -5%"', rec('Скорость бараки на поле боя -5%') === 'battle_speed=-5', rec('Скорость бараки на поле боя -5%'));
    check('"Даотность пермешения пок арте компании +20%"', rec('Даотность пермешения пок арте компании +20%') === 'campaign_movement=20', rec('Даотность пермешения пок арте компании +20%'));
    check('"Скорость на карте кмопании -5% скорость"', rec('Скорость на карте кмопании -5% скорость') === 'campaign_movement=-5');
    check('"Обзор на карте кампании: +5%"', rec('Обзор на карте кампании: +5%') === 'sight=5');
    check('"Стоимость найма: -10%" by the game\'s template', rec('Стоимость найма: -10%') === 'game:wh_main_effect_force_all_campaign_recruitment_cost=-10', rec('Стоимость найма: -10%'));
    check('"Опыт за ход: +250"', /^game:.*=250$/.test(rec('Опыт за ход: +250')), rec('Опыт за ход: +250'));
    check('"+10" alone does not read', rec('+10') === '');
    const prop = FX.proposal({text: 'Скорость бараки на поле боя -5%', icon: null, good: true}, ctx);
    check('the proposal keeps the author\'s text and turns it red', prop && prop.effects[0].text === 'Скорость бараки на поле боя -5%' && !prop.effects[0].good && prop.colour === 'станет красной', JSON.stringify(prop));
    // the file keeps the structure
    const d = T.emptyDesign();
    const id = T.addNode(d, {name: 'Трюм', cost: 100, effects: [ammo, {text: 'Своя', icon: null, good: false}], units: ['wh_main_dwf_art_cannon'],
        parts: [{part: 'pub'}, {part: null, name: 'Дозорные', zone: 'balloon', what: 'figures', figures: 2, note: 'фигуры'}]});
    const back = T.normalize(JSON.parse(T.serialize(d))).design;
    const n = T.byId(back, id);
    check('the file keeps an effect of the catalogue whole', JSON.stringify({...n.effects[0], id: undefined}) === JSON.stringify({...T.normalizeEffect(ammo), id: undefined}) && n.effects[0].id === 'e1' && n.effects[0].kind === 'ammo' && n.effects[0].target === 'rifles');
    check('the file keeps a free line as three fields', JSON.stringify(n.effects[1]) === JSON.stringify({text: 'Своя', icon: null, good: false, id: 'e2'}));
    check('the file keeps units and parts', n.units.join() === 'wh_main_dwf_art_cannon' && n.parts.length === 2 && n.parts[1].figures === 2 && n.parts[1].zone === 'balloon');
    // the checks: one army unit by two buildings, a detail without a picture
    T.addNode(d, {name: 'Кузня', cost: 100, units: ['wh_main_dwf_art_cannon']});
    const w = T.warnings(d, {unitName: k => k, partKnown: k => k === 'pub', partDrawn: () => true, partName: k => k});
    check('a unit opened by two buildings is warned of', w.some(x => x.kind === 'dup_unit'));
    check('a new detail is warned of as not drawn', w.some(x => x.kind === 'ship_part' && /рисунок не готов/.test(x.text) && /Дозорные/.test(x.text)));
    // the game's levels carry them
    const g = T.gameData(d, data);
    check('the game\'s level carries units, parts and the effects', g.tree_rows[0].units[0] === 'wh_main_dwf_art_cannon' && g.tree_rows[0].parts.length === 2 && g.tree_rows[0].effects[0].kind === 'ammo');
}
// 10. merge3: the author's state and the file's changed apart
{
    const base = T.emptyDesign();
    for (const [nm, c] of [['A', 0], ['B', 1], ['C', 2]]) T.addNode(base, {name: nm, cost: 1, col: c, row: 0});
    const theirs = JSON.parse(JSON.stringify(base)), mine = JSON.parse(JSON.stringify(base));
    T.byId(theirs, 'n1').note = 'из файла';
    T.byId(mine, 'n2').cost = 7;
    let m = T.merge3(base, theirs, mine);
    check('merge3: changes on different buildings join', !m.clashes.length && T.byId(m.design, 'n1').note === 'из файла' && T.byId(m.design, 'n2').cost === 7);
    T.byId(mine, 'n1').note = 'моё';
    m = T.merge3(base, theirs, mine);
    check('merge3: one building changed on both sides is a clash, the file\'s kept', m.clashes.join() === 'n1' && T.byId(m.design, 'n1').note === 'из файла');
    const added = JSON.parse(JSON.stringify(mine));
    T.addNode(added, {name: 'D', cost: 1, col: 3, row: 0});
    m = T.merge3(base, theirs, added);
    check('merge3: a building added here comes in', !!T.byId(m.design, 'n4'));
    const gone = JSON.parse(JSON.stringify(base));
    T.deleteNodes(gone, ['n3']);
    m = T.merge3(base, gone, mine);
    check('merge3: a building deleted in the file and untouched here goes', !T.byId(m.design, 'n3'));
}
// 11. lines of levels: three levels with inheritance, numbers changed on II and on I, a line hidden and given back, a fork, a broken line,
// inheritance turned on over a node's whole set, the game's chains
{
    const data = json('build/web/data.json');
    const d = T.emptyDesign();
    const i1 = T.addNode(d, {name: 'Пивной чертог', cost: 1, col: 0, row: 0, crew: [{group: 'rifles', option: 'pirates'}], units: ['u1'], parts: [{part: 'pub'}],
        effects: [{kind: 'ammo', target: 'rifles', value: 10, text: 'Боезапас стрелков: +10 %', icon: null, good: true}, {text: 'Строка A', icon: null, good: true}, {text: 'Строка B', icon: null, good: true}]});
    const i2 = T.addNode(d, {name: 'Таверна', cost: 1, col: 0, row: 1, requires: [i1], prev: i1, inherit: true,
        effects: [{kind: 'ammo', target: 'rifles', value: 25, text: 'Боезапас стрелков: +25 %', icon: null, good: true}, {text: 'Своя C', icon: null, good: true}]});
    const i3 = T.addNode(d, {name: 'Винокурня', cost: 1, col: 0, row: 2, requires: [i2], prev: i2, inherit: true});
    const texts = id => T.resolve(d, id).full.effects.map(x => x.e.text);
    check('lines: levels I, II, III', [i1, i2, i3].map(id => T.levelOf(d, id)).join() === '1,2,3' && T.roman(3) === 'III');
    check('lines: II gives I\'s lines with its own number in the place of I\'s, and its own line', texts(i2).join('|') === 'Боезапас стрелков: +25 %|Строка A|Строка B|Своя C', texts(i2));
    check('lines: III gives II\'s whole set; crew, units, details along the line', texts(i3).join('|') === texts(i2).join('|') && T.resolve(d, i3).full.crew.length === 1 && T.resolve(d, i3).full.units[0].u === 'u1' && T.resolve(d, i3).full.parts.length === 1);
    T.byId(d, i1).effects[0].value = 12; T.byId(d, i1).effects[1].text = 'Строка A2';
    check('lines: I changed: III keeps II\'s number, sees I\'s new line (a live link)', texts(i3)[0] === 'Боезапас стрелков: +25 %' && texts(i3)[1] === 'Строка A2', texts(i3));
    const keyB = `${i1}/${T.byId(d, i1).effects[2].id}`;
    T.byId(d, i3).hide = [keyB];
    check('lines: a line hidden on III', !texts(i3).includes('Строка B') && T.resolve(d, i3).inherited.effects.find(x => x.key === keyB).status === 'hidden');
    T.byId(d, i3).hide = [];
    check('lines: given back', texts(i3).includes('Строка B'));
    T.byId(d, i3).effects.push({text: 'Строка A на III', icon: null, good: true, replaces: `${i1}/${T.byId(d, i1).effects[1].id}`});
    T.ensureIds(d);
    check('lines: a free line replaced on III in its place', texts(i3)[1] === 'Строка A на III' && texts(i3).length === 4, texts(i3));
    check('lines: no warning for a whole line', !T.warnings(d).some(w => /^line/.test(w.kind)), T.warnings(d).filter(w => /^line/.test(w.kind)));
    const fork = T.addNode(d, {name: 'Развилка', cost: 1, col: 1, row: 1, prev: i1, inherit: true});
    const w = T.warnings(d);
    check('lines: a fork is warned of, a next level that does not require the one before is warned of', w.some(x => x.kind === 'line_fork') && w.some(x => x.kind === 'line_require' && x.nodes.includes(fork)), w.map(x => x.kind));
    check('lines: a circle is refused', !T.canContinue(d, i1, i3).ok && !T.canContinue(d, i1, i1).ok && T.canContinue(d, fork, i3).ok);
    T.byId(d, fork).prev = null;
    check('lines: broken: nothing inherited', T.resolve(d, fork).full.effects.length === 0 && T.resolve(d, fork).from === null);
    // the file keeps only what is own
    const back = T.normalize(JSON.parse(T.serialize(d))).design;
    check('lines: the file keeps prev, inherit, hide, the ids and the replacements; nothing inherited is written', T.byId(back, i3).prev === i2 && T.byId(back, i3).inherit && T.byId(back, i3).effects.length === 1 && !!T.byId(back, i3).effects[0].replaces
        && JSON.stringify(T.resolve(back, i3).full.effects.map(x => [x.key, x.e.text])) === JSON.stringify(T.resolve(d, i3).full.effects.map(x => [x.key, x.e.text])), [T.byId(back, i3), T.resolve(back, i3).full.effects.map(x => x.e.text)]);
    // inheritance on over a node's whole set (a building of the mod): the doubles found
    const m = T.emptyDesign();
    const a = T.addNode(m, {name: 'Трюм', cost: 1, effects: [{text: 'Рост орды: +5', icon: null, good: true}, {text: 'Ровно так же', icon: null, good: true}, {kind: 'ammo', target: 'all', value: 15, text: 'Боезапас каждой команды: +15 %', icon: null, good: true}], crew: [{group: 'bombs', option: 'stock'}]});
    const bb = T.addNode(m, {name: 'Хранилище', cost: 1, requires: [a], prev: a, effects: [{text: 'Рост орды: +10', icon: null, good: true}, {text: 'Ровно так же', icon: null, good: true}, {kind: 'ammo', target: 'all', value: 40, text: 'Боезапас каждой команды: +40 %', icon: null, good: true}], crew: [{group: 'bombs', option: 'stock'}]});
    const read = t => (/Рост орды/.test(t) ? ['game|' + '|wh_main_effect_hordebuilding_growth_core'] : []);
    const o = T.inheritOverlap(m, bb, read);
    check('lines: inheritance over a whole set: the catalogue\'s replaces, the word for word doubles, the same kind, the crew', o.replace.length === 1 && o.doubles.length === 1 && o.sameKind.length === 1 && o.things.length === 1, o);
    // the game's levels: a line is one chain of levels, each level the whole set
    const g = T.gameData(d, data);
    const r3 = g.tree_rows.find(r => r.node === i3), r1 = g.tree_rows.find(r => r.node === i1);
    check('lines: the game: one chain, levels 0, 1, 2; III\'s row carries the whole set', r3.chain === r1.chain && r3.level === 2 && r3.line_level === 3 && r3.effects.length === 4 && r3.unlocks.length === 1 && r3.units[0] === 'u1');
    // the mod's chains on the canvas become lines (inheritance off)
    const start = T.normalize(json('tools/tests/tree_design_start.json')).design;
    const n = T.linkModChains(start, data);
    check('lines: the mod\'s chains made lines: the hull\'s II continues I, inheritance off', n >= 1 && start.nodes.find(x => x.mod_key === 'airship_hull_2').prev === start.nodes.find(x => x.mod_key === 'airship_hull_1').id && !start.nodes.some(x => x.inherit));
}
// 12. what is opened is kept along a line without inheritance; a draft of the browser taken back building by building
{
    const d = T.emptyDesign();
    const a = T.addNode(d, {name: 'I', cost: 1, crew: [{group: 'rifles', option: 'pirates'}], units: ['u1'], parts: [{part: 'pub'}], effects: [{text: 'Строка I', icon: null, good: true}]});
    const b2 = T.addNode(d, {name: 'II', cost: 1, requires: [a], prev: a, inherit: false, effects: [{text: 'Строка II', icon: null, good: true}]});
    const r = T.resolve(d, b2);
    check('opened kept: II without inheritance keeps I\'s crew, units, details; not its lines', r.full.crew.length === 1 && r.full.units[0].u === 'u1' && r.full.parts.length === 1 && r.full.effects.map(x => x.e.text).join() === 'Строка II' && r.below === a && r.from === null);
    T.byId(d, b2).hide = ['crew:rifles:pirates'];
    check('opened kept: an explicit «убрать» on II takes the crew away', T.resolve(d, b2).full.crew.length === 0);
    T.byId(d, b2).hide = [];
    // a draft of an older page (format 2, no base): its edits over the file, the file's line and new fields kept
    const file = JSON.parse(JSON.stringify(d));
    T.byId(file, b2).hide = ['unit:u1'];
    const old = {format: 2, nodes: file.nodes.map(n => { const {prev, inherit, hide, ...rest} = n; return {...rest, effects: n.effects.map(({id, replaces, ...e}) => e)}; })};
    old.nodes[0].cost = 777;
    old.nodes.push({id: 'z', name: 'Новая из черновика', cost: 5});
    const m = T.mergeDraft(file, old);
    const n2 = T.byId(m.design, b2);
    check('draft: an older draft joins by buildings: its cost in, a new building in, the line, inheritance, hide and the ids of the file kept',
        T.byId(m.design, a).cost === 777 && !!T.byId(m.design, 'z') && n2.prev === a && n2.hide.join() === 'unit:u1' && T.byId(m.design, a).effects[0].id === file.nodes[0].effects[0].id, m.design.nodes.map(x => [x.id, x.prev, x.cost]));
    // a draft of this format with its base: merge3, the file's change elsewhere kept
    const base = JSON.parse(T.serialize(file));
    const mine = JSON.parse(T.serialize(file)); mine.nodes[0].note = 'черновик';
    const now = JSON.parse(JSON.stringify(file)); T.byId(now, b2).note = 'из файла';
    const m2 = T.mergeDraft(now, mine, base);
    check('draft: with its base: building by building, the draft\'s note and the file\'s both kept', T.byId(m2.design, a).note === 'черновик' && T.byId(m2.design, b2).note === 'из файла' && !m2.clashes.length);
}
console.log(failed ? `failed: ${failed}` : 'failed: 0');
process.exit(failed ? 1 : 0);
