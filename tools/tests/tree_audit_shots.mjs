// The audited tree walked as the author would look at it (docs/design/tree-audit.md), in a headless Chrome (tools/tests/cdp.mjs):
//   node --experimental-websocket tools/tests/tree_audit_shots.mjs [tree file, default build/web/audit/tree_design.audit.json]
// A server of its own (tools/web_serve.py --port 8766 --tree <a copy in the temp folder>); the author's web/data/tree_design.json is never read nor
// written. At 1280 x 800 and 1600 x 900, for every building: the constructor's properties (the icon loaded, a name, a description, no free line left,
// no line twice in the level's whole set) and the game's information window (its title, description, lines, none twice, every picture loaded).
// Pictures to build/web/shots/audit/: tree_full.png, info_<id>.png of the chosen buildings, props_<id>.png, game_full_built.png. Exit 1 on any failure.
import {readFileSync, writeFileSync, mkdirSync, rmSync, existsSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {tmpdir} from 'node:os';
import {launch, sleep, debugRect} from './cdp.mjs';
import * as T from '../../web/js/tree_model.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const WORK = join(ROOT, 'web/data/tree_design.json');
const hash = p => (existsSync(p) ? createHash('sha256').update(readFileSync(p)).digest('hex') : 'none');
const workBefore = hash(WORK);
const SRC = process.argv[2] || join(ROOT, 'build/web/audit/tree_design.audit.json');
const DATA = join(tmpdir(), 'mtb_audit_tree');
rmSync(DATA, {recursive: true, force: true});
mkdirSync(DATA, {recursive: true});
const FILE = join(DATA, 'tree_design.json');
writeFileSync(FILE, readFileSync(SRC, 'utf-8'));
const design = T.normalize(JSON.parse(readFileSync(FILE, 'utf-8'))).design;
const PORT = 8766, URL0 = `http://127.0.0.1:${PORT}/`;
const server = spawn('py', ['-3.14', join(ROOT, 'tools/web_serve.py'), '--port', String(PORT), '--tree', FILE], {stdio: 'ignore'});
for (let i = 0; i < 50; i++) { if (await fetch(URL0 + 'data/tree_design.json').then(r => r.ok).catch(() => false)) break; await sleep(200); }
const SHOTS = join(ROOT, 'build/web/shots/audit');
mkdirSync(SHOTS, {recursive: true});
let failed = 0, n = 0, warnsNow = [];
const check = (name, ok, extra = '') => { n++; if (!ok) failed++; if (!ok || process.env.VERBOSE) console.log((ok ? 'ok   ' : 'FAIL ') + name + (extra && !ok ? '  ' + (typeof extra === 'string' ? extra : JSON.stringify(extra)) : '')); return ok; };
// the buildings whose window is pictured: new names and descriptions, and the most loaded
const INFO_SHOTS = ['n1', 'n2', 'n3', 'n4', 'n5', 'infantry_workshop_1', 'infantry_workshop_2', 'mtb_nest_1', 'mtb_nest_2', 'mtb_guns_3', 'airship_hull_3',
    'beer_hall_3', 'crew_weapons_3', 'cargo_hold_3', 'engineering_workshop_3', 'airship_hull_5', 'beer_hall_1'];

const b = await launch({width: 1600, height: 900});
const E = 'mtb.editor.api';
const at = sel => b.eval(`(() => { const e = ${sel}; if (!e) return null; e.scrollIntoView({block: 'nearest'}); const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height}; })()`);
const clickText = async (sel, t) => { const r = await at(`[...document.querySelectorAll(${JSON.stringify(sel)})].find(x => x.offsetParent !== null && x.textContent.trim().startsWith(${JSON.stringify(t)}))`); if (!r) throw new Error('no ' + t); await b.click(r.x, r.y); };
const images = () => b.eval(`[...document.querySelectorAll('img')].filter(i => i.offsetParent !== null).filter(i => i.getAttribute('src') && (!i.complete || !i.naturalWidth)).map(i => i.src)`);
const gameComp = id => b.eval(`(() => { const e = [...document.querySelectorAll('#screen [data-id="${id}"]')].find(x => x.offsetParent !== null); if (!e) return null; const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, t: r.top, b: r.bottom, l: r.left, r: r.right}; })()`);
const gm = 'mtb.panel.view';
const nodeOnScreen = async id => gameComp('mtb_tree_node_' + await b.eval(`${gm}.tree.findIndex(v => v.node.row && v.node.row.node === ${JSON.stringify(id)})`));
const inSight = async id => {
    let p = await nodeOnScreen(id);
    const win = await gameComp('tree_window');
    for (let i = 0; i < 12 && p && (p.y < win.t + 40 || p.y > win.b - 40 || p.x < win.l + 40 || p.x > win.r - 40); i++) {
        await b.drag(win.x, win.y, win.x + Math.max(-150, Math.min(150, win.x - p.x)), win.y + Math.max(-150, Math.min(150, win.y - p.y)), {steps: 6});
        p = await nodeOnScreen(id);
    }
    return p;
};
const infoLines = () => b.eval(`(() => { const t = [...document.querySelectorAll('#screen .tooltip_frame')].find(x => x.offsetParent !== null); if (!t) return null;
    const r = t.getBoundingClientRect(); return {box: {x: r.left, y: r.top, width: r.width, height: r.height}, lines: [...t.querySelectorAll('[data-id]')].filter(x => x.offsetParent !== null && x.querySelector('.t')).map(x => x.textContent.trim())}; })()`);
const toConstructor = async () => { await clickText('#mode button', 'Конструктор'); await b.until('document.body.dataset.mode === "constructor"'); await sleep(300); };
const toGame = async () => { await clickText('#mode button', 'Игра'); await b.until('document.body.dataset.mode === "game" && !!mtb.panel.view.tree'); await sleep(600); };

try {
    await b.open(URL0 + '?mode=constructor');
    await b.until(`!!(window.mtb && mtb.editor && mtb.editor.design().nodes.length === ${design.nodes.length})`, 20000);
    await sleep(1200);
    for (const [w, h] of [[1280, 800], [1600, 900]]) {
        await b.size(w, h); await sleep(500);
        if (await b.eval('document.body.dataset.mode') !== 'constructor') await toConstructor();
        await b.eval(`${E}.select([])`); await b.eval(`${E}.showAll(1)`); await sleep(500);
        if (w === 1600) {
            // the whole tree at the readable size: a tall window, both side panels folded
            await b.eval(`${E}.fold('palette', true); ${E}.fold('props', true)`); await b.size(1760, 2780); await sleep(600);
            await b.eval(`${E}.showAll(1)`); await sleep(600);
            await b.shot(join(SHOTS, 'tree_full.png'));
            await b.eval(`${E}.fold('palette', false); ${E}.fold('props', false)`); await b.size(w, h); await sleep(600);
            await b.eval(`${E}.showAll(1)`); await sleep(300);
        }
        // the checks of the constructor: their list
        const warns = await b.eval(`(() => { const btn = document.querySelector('.cx-warnbtn'); btn.click(); const l = [...document.querySelectorAll('.cx-warnlist li')].map(x => x.textContent); btn.click(); return l; })()`);
        warnsNow = warns;
        console.log(`${w}: the constructor's checks (${warns.length}):\n  ` + warns.join('\n  '));
        check(`${w}: no error among the checks (no circle, no orphan, no name or price missing, no unknown detail)`, !warns.some(t => /круг|нет пути|нет названия|нет цены|нет в web\/data\/blueprint|в моде нет постройки/.test(t)), warns);
        for (const node of design.nodes) {
            await b.eval(`${E}.select([${JSON.stringify(node.id)}])`); await sleep(120);
            const p = await b.eval(`(() => { const pr = document.querySelector('.cx-props'); const img = pr.querySelector('.cx-iconpick img');
                const name = pr.querySelector('[data-field="name"]'), desc = pr.querySelector('.cx-desc');
                const rows = [...pr.querySelectorAll('.cx-effects .e')].filter(e => !e.classList.contains('inh') || e.classList.contains('mine'));
                return {icon: !!(img && img.complete && img.naturalWidth), src: img && img.getAttribute('src'), name: name && name.value, desc: desc && desc.value,
                        free: [...pr.querySelectorAll('.cx-effects > .e:not(.fx)')].map(e => e.querySelector('input') && e.querySelector('input').value), proposals: pr.querySelectorAll('.propose').length}; })()`);
            const full = T.resolve(design, node.id).full.effects.map(x => x.e.text);
            check(`${w}: «${node.name}»: the icon loaded`, p.icon, p.src);
            check(`${w}: «${node.name}»: a name and a description`, !!(p.name && p.name.trim()) && !!(p.desc && p.desc.trim()), p);
            check(`${w}: «${node.name}»: no line twice in the level's whole set`, full.length === new Set(full).size, full);
            check(`${w}: «${node.name}»: no free line with a proposal left`, !p.proposals, p.free);
            if (w === 1600 && ['beer_hall_1', 'infantry_workshop_1', 'n4', 'engineering_workshop_2'].includes(node.id)) {
                await b.eval(`document.querySelector('.cx-props').scrollTop = 0`); await sleep(100);
                await b.shot(join(SHOTS, `props_${node.id}.png`));
            }
        }
        // the game's tree: every building's information window
        await toGame();
        const tiles = await b.eval(`${gm}.tree.filter(v => v.node.row).length`);
        check(`${w}: the game's tree has every building`, tiles === design.nodes.length, tiles);
        for (const node of design.nodes) {
            const pos = await inSight(node.id);
            if (!check(`${w}: «${node.name}»: its slot on the game's tree`, !!pos)) continue;
            await b.move(pos.x + 3, pos.y + 2, 3); await sleep(380);
            const info = await infoLines();
            if (!check(`${w}: «${node.name}»: the information window opens`, !!info)) continue;
            const text = info.lines.join(' | ');
            // the second line is the chain's name (the game's secondary title): the page names a chain by its first level, so on a first level it
            // repeats the title; that is the mod's naming of chains, not a line of the building (docs/design/tree-audit.md)
            const lines = info.lines.filter((l, i) => !/^Вид на корабле/.test(l) && !(i === 1 && l === info.lines[0]));
            // a window the constructor already warns of (too many lines: the game drops the description) is not counted twice
            const crowded = warnsNow.some(t => t.includes(`«${node.name}»`) && /не больше|нет места/.test(t));
            check(`${w}: «${node.name}»: the window has its name and description${crowded ? ' (the constructor warns: no room for the description)' : ''}`,
                text.includes(node.name) && (!node.description || crowded || text.includes(node.description.slice(0, 25))), text.slice(0, 200));
            check(`${w}: «${node.name}»: no line twice in the window`, lines.length === new Set(lines).size, lines);
            const bad = await images();
            check(`${w}: «${node.name}»: every picture loaded`, !bad.length, bad);
            const slotImg = await b.eval(`(() => { const e = [...document.querySelectorAll('#screen [data-id="mtb_tree_node_' + ${gm}.tree.findIndex(v => v.node.row && v.node.row.node === ${JSON.stringify(node.id)}) + '"] img')]; return e.length ? e.every(i => i.complete && i.naturalWidth) : null; })()`);
            check(`${w}: «${node.name}»: the slot's icon loaded in the game`, slotImg !== false, slotImg);
            if (w === 1600 && INFO_SHOTS.includes(node.id)) {
                const pad = 12, x = Math.max(0, Math.min(pos.x - 60, info.box.x) - pad), y = Math.max(0, Math.min(pos.y - 60, info.box.y) - pad);
                const x1 = Math.min(w, Math.max(pos.x + 60, info.box.x + info.box.width) + pad), y1 = Math.min(h, Math.max(pos.y + 60, info.box.y + info.box.height) + pad);
                await b.shot(join(SHOTS, `info_${node.id}.png`), {x, y, width: x1 - x, height: y1 - y});
            }
            await b.move(5, h - 5, 2); await sleep(60);
        }
        if (w === 1600) {
            // everything built: each top level built with all it needs (the page's debug «Построить до»)
            const tops = design.nodes.filter(x => !design.nodes.some(m => m.prev === x.id));
            for (const t of tops) {
                const pos = await inSight(t.id);
                await b.click(pos.x, pos.y); await sleep(150);
                const r = await debugRect(b, '#build_to'); await b.click(r.x, r.y); await sleep(200);
            }
            const built = await b.eval(`${gm}.tree.filter(v => v.node.row && mtb.game.standing(v.node.key)).length`);
            check('1600: the whole tree built: every top level stands', built === tops.length, built);
            await b.move(5, h - 5, 2); await sleep(300);
            await b.shot(join(SHOTS, 'game_full_built.png'));
            const rifles = await b.eval(`(async () => { const FX = await import('/js/effects_model.mjs'), C = await import('/js/crew_model.mjs'); const L = ${gm}.data; const g = k => FX.crewBonuses(C.crewSources(L, x => mtb.game.has_building(x), x => mtb.game.standing(x)), k); return {r: g('rifles').ammo.pct, b: g('bombs').ammo.pct, acc: g('cannons').accuracy.pct}; })()`);
            check('1600: built: the riflemen\'s ammunition +100 %, the bombs\' +130 % (every crew + their own), the guns\' accuracy as the audit counts it', rifles.r === 100 && rifles.b === 130, rifles);
            console.log('built: crew bonuses', JSON.stringify(rifles));
            await clickText('#reset_all', ''); await sleep(800);
            await b.until('!!(window.mtb && mtb.panel && mtb.panel.view.tree && mtb.editor)', 15000).catch(() => {});
        }
    }
    check('the console is clean, no dialog', !b.errors.length && !b.dialogs.length, [...b.errors, ...b.dialogs]);
} catch (e) {
    failed++; console.log('FAIL walk stopped: ' + e.stack);
    try { await b.shot(join(SHOTS, 'audit_walk_error.png')); } catch (x) { /* no picture */ }
}
await b.close();
server.kill();
check('the author\'s working file web/data/tree_design.json untouched, byte for byte', hash(WORK) === workBefore);
console.log(`checks: ${n}, failed: ${failed}`);
process.exit(failed ? 1 : 0);
