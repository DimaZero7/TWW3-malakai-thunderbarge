// The page opens and works with any tree of buildings, not only the author's: node --experimental-websocket tools/tests/any_tree_walk.mjs
// Its own server (tools/web_serve.py --port 8767 --tree <a file in the temp folder>), the file rewritten before each case; the author's
// web/data/tree_design.json is only read. Cases: an empty tree; one node; the constructor's starting tree (tools/tests/tree_design_start.json); the
// author's tree without each detail of the ship in turn (the lookouts linked by name too); with the lookouts renamed; without each building that makes
// a crew's place (the mounts, the beer hall and the dummies of the riflemen, the harpoon's winch) and without the hull's levels; a node without its
// mod key. For each: no error in the console, «Игра» and «Конструктор» both open, «Построить всё» and the turn go, a crew is ordered where a place
// is. A missing detail or group is simply not there. Prints a line a check; exit 1 on any failure.
import {readFileSync, writeFileSync, mkdirSync, rmSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {tmpdir} from 'node:os';
import {launch, startServer, sleep, debugRect} from './cdp.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DATA = join(tmpdir(), 'mtb_any_tree');
rmSync(DATA, {recursive: true, force: true});
mkdirSync(DATA, {recursive: true});
const FILE = join(DATA, 'tree_design.json');
const user = JSON.parse(readFileSync(join(ROOT, 'web/data/tree_design.json'), 'utf-8'));
const start = JSON.parse(readFileSync(join(ROOT, 'tools/tests/tree_design_start.json'), 'utf-8'));
writeFileSync(FILE, JSON.stringify(user));
// the page's own server: the port checked free first, stopped with its process tree in the finally below (cdp.mjs startServer)
const server = await startServer({root: ROOT, port: 8767, tree: FILE});
const URL0 = server.url, PORT = server.port;
let failed = 0;
const check = (name, ok, extra = '') => { if (!ok) failed++; console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok || !extra ? '' : '  ' + (typeof extra === 'string' ? extra : JSON.stringify(extra)))); return ok; };

const clone = x => JSON.parse(JSON.stringify(x));
// a tree without some nodes: their links and lines dropped with them
const without = (d, ids) => {
    const t = clone(d), gone = new Set(ids);
    t.nodes = t.nodes.filter(n => !gone.has(n.id));
    for (const n of t.nodes) { n.requires = n.requires.filter(r => !gone.has(r)); if (gone.has(n.prev)) n.prev = null; }
    return t;
};
const withoutPart = (d, test) => { const t = clone(d); for (const n of t.nodes) n.parts = (n.parts || []).filter(p => !test(p)); return t; };
const cases = [['empty tree', {...clone(user), nodes: []}], ['one node', {...clone(user), nodes: [{...clone(user.nodes[0]), requires: [], prev: null}]}], ['the starting tree', clone(start)]];
for (const part of ['barge', 'pub', 'rings', 'port', 'bomb_hatches', 'side_shields', 'balloon_shields', 'forsage_tank', 'stern_armour', 'porthole'])
    cases.push([`without the detail «${part}»`, withoutPart(user, p => p.part === part)]);
cases.push(['without the lookouts (linked by name)', withoutPart(user, p => !p.part && /Дозорные/.test(p.name || ''))]);
const renamed = clone(user);
for (const n of renamed.nodes) for (const p of n.parts || []) if (!p.part && /Дозорные/.test(p.name || '')) p.name = 'Дозорные (переименованы)';
cases.push(['the lookouts renamed', renamed]);
const mounts = user.nodes.filter(n => (n.crew || []).some(c => c.option === 'empty' || c.group === 'harpoon') || ['beer_hall_1', 'crew_weapons_1'].includes(n.mod_key));
for (const n of mounts) cases.push([`without «${n.name}»`, without(user, [n.id])]);
cases.push(['without the hull', without(user, user.nodes.filter(n => /^airship_hull_/.test(n.mod_key || '')).map(n => n.id))]);
const noKey = clone(user);
for (const n of noKey.nodes) if (n.mod_key === 'mtb_guns_1' || n.mod_key === 'mtb_nest_1') n.mod_key = null;
cases.push(['nodes without their mod key (ports, nests)', noKey]);

const b = await launch({width: 1600, height: 950, port: 9391, profile: join(tmpdir(), 'mtb_any_tree_profile')}).catch(async e => { await server.stop(); throw e; });
await b.size(1600, 950);
try {
    for (const [label, tree] of cases) {
        writeFileSync(FILE, JSON.stringify(tree));
        b.errors.length = 0;
        try {
            await b.open(URL0 + '?mode=game');
            await b.until('!!(window.mtb && mtb.M && mtb.panel)', 15000);
            await b.eval('localStorage.clear()');
            await b.reload();
            await b.until('!!(window.mtb && mtb.M && mtb.panel)', 15000);
            await sleep(600);
            const r = await debugRect(b, '#build_all'); await b.click(r.x, r.y); await sleep(500);
            await b.eval('mtb.game.gold = 100000; 1');
            const placed = await b.eval(`['rifles','cannons','bombs','cupolas','harpoon'].filter(g => mtb.M.crew_place(g)).map(g => { const o = mtb.M.crew_options(g).find(o => !o.empty && o.unlocked); return o ? [g, mtb.M.set_crew(g, o.key).kind] : [g, 'none']; })`);
            const e = await b.rect('#end_turn'); await b.click(e.x, e.y); await sleep(600);
            await b.eval(`mtb.setMode('constructor'); 1`); await sleep(800);
            const cx = await b.eval(`!!document.querySelector('.cx-canvas') && document.body.dataset.mode === 'constructor'`);
            await b.eval(`mtb.setMode('game'); 1`); await sleep(600);
            const turn = await b.eval('mtb.game.turn');
            check(`${label}: opens, builds all, the turn, both modes, no error`, !b.errors.length && cx && turn === 2 && placed.every(([, k]) => k === 'ordered' || k === 'none'), {errors: b.errors.slice(0, 3), cx, turn, placed});
        } catch (err) {
            check(`${label}: the page works`, false, {err: err.message, errors: b.errors.slice(0, 3)});
        }
    }
} finally {
    try { await b.close(); } finally { await server.stop(); }
}
console.log(`failed: ${failed}`);
process.exit(failed ? 1 : 0);
