// The constructor's model of the tree (web/js/tree_model.mjs): node tools/tests/tree_model_test.mjs (from the repository's root)
// The operations, links and their checks, undo and redo, copy and paste, the file's text and the reading of a broken file, the warnings, the mod's
// buildings as nodes, the start file web/data/tree_design.json. Prints a line a check, exit 1 on any failure.
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import * as T from '../../web/js/tree_model.mjs';

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
// 5c. the constructor's grid: on the stand of 26 buildings every link has its own way, from the parent's slot top to the child's card bottom,
// and no two links share a stretch of line; the warnings of the game's building window
{
    const {standDesign} = await import('./constructor_stand.mjs');
    const d = standDesign(json('web/data/tree_design.json'));
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
    const start = T.normalize(json('web/data/tree_design.json'));
    check('the start file reads without problems', !start.problems.length, start.problems.join('; '));
    check('the start file is in its own text', T.serialize(start.design) === readFileSync(join(root, 'web/data/tree_design.json'), 'utf-8'));
    check('the start file: no warnings', !T.warnings(start.design, {modKeys: new Set(all.map(r => r.short))}).length, JSON.stringify(T.warnings(start.design)));
    const g = T.gameData(start.design, data);
    check('game levels keep the mod keys', g.chains.map(c => c.key).join() === start.design.nodes.map(n => data.prefix + n.mod_key).join());
    check('hull tiers from the nodes', g.hull_tiers[data.prefix + 'airship_hull_2'] === 2);
}
console.log(failed ? `failed: ${failed}` : 'failed: 0');
process.exit(failed ? 1 : 0);
