// The constructor and the game's tree walked as the user would, with the mouse and the keys, in a headless Chrome (tools/tests/cdp.mjs):
//   node --experimental-websocket tools/tests/constructor_walk.mjs
// It starts a server of its own (tools/web_serve.py --port 8766 --tree <a copy in the temp folder>): the author's working file
// web/data/tree_design.json is never read nor written, and checked unchanged at the end.
// Part 1 builds a tree from nothing at 1280 x 800 (the palette, empty buildings, links by the handles, a node with two parents, a group moved, every
// field edited, a node with links deleted, a long undo and redo, F5) and checks after each kind of action that web/data/tree_design.json on disk is
// what the canvas shows (the walk's own copy), and each of the faults the independent check found (items 6-14 of its list). Part 2 imports the test stand of 26
// buildings (tools/tests/constructor_stand.mjs) and measures it at 1600, 1280 and 1024: no line across a name, a price, a crew card or another
// building; no name cut or smaller than 11 px; every icon on the slot's parchment. Part 3 plays the stand's tree in «Игра». Pictures to
// build/web/shots/constructor_*.png, the walked tree to build/web/tree_design_walk.json. Prints a line a check; exit 1 on any failure.
import {readFileSync, writeFileSync, existsSync, readdirSync, mkdirSync, rmSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {tmpdir} from 'node:os';
import {launch, sleep} from './cdp.mjs';
import {standDesign} from './constructor_stand.mjs';
import * as T from '../../web/js/tree_model.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const WORK = join(ROOT, 'web/data/tree_design.json');
const hash = p => (existsSync(p) ? createHash('sha256').update(readFileSync(p)).digest('hex') : 'none');
const workBefore = hash(WORK);
// the walk's own tree file and its own server
const DATA = join(tmpdir(), 'mtb_walk_tree');
rmSync(DATA, {recursive: true, force: true});
mkdirSync(DATA, {recursive: true});
const FILE = join(DATA, 'tree_design.json');
const START = readFileSync(join(ROOT, 'tools/tests/tree_design_start.json'), 'utf-8');
writeFileSync(FILE, START);
const PORT = 8766, URL0 = `http://127.0.0.1:${PORT}/`;
const server = spawn('py', ['-3.14', join(ROOT, 'tools/web_serve.py'), '--port', String(PORT), '--tree', FILE], {stdio: 'ignore'});
for (let i = 0; i < 50; i++) { if (await fetch(URL0 + 'data/tree_design.json').then(r => r.ok).catch(() => false)) break; await sleep(200); }
const SHOTS = join(ROOT, 'build/web/shots');
mkdirSync(SHOTS, {recursive: true});
let failed = 0;
const results = [];
const check = (name, ok, extra = '') => { if (!ok) failed++; results.push([name, ok]); console.log((ok ? 'ok   ' : 'FAIL ') + name + (extra ? '  ' + (typeof extra === 'string' ? extra : JSON.stringify(extra)) : '')); return ok; };
const tmp = join(tmpdir(), 'mtb_walk_files');
mkdirSync(tmp, {recursive: true});

const b = await launch({width: 1280, height: 800});
await b.size(1280, 800);
const E = 'mtb.editor.api';
const design = () => b.eval('JSON.stringify(mtb.editor.design())').then(s => JSON.parse(s));
const text = async () => T.serialize(T.normalize(await design()).design);
const idOf = async name => (await design()).nodes.find(n => n.name === name)?.id;
// the slot's middle of a cell on the screen
const cell = async (col, row) => b.eval(`(() => { const r = document.querySelector('.cx-canvas').getBoundingClientRect(), v = ${E}.view; const c = {x: ${col} * ${T.CX.CW} + ${T.CX.CARD_X} + ${T.CX.CARD_W / 2}, y: ${-row} * ${T.CX.CH} + ${T.CX.SLOT_Y} + 37}; return {x: r.left + v.x + c.x * v.z, y: r.top + v.y + c.y * v.z}; })()`);
const slot = async id => b.rect(`.cx-node[data-id="${id}"] .slot`);
const nodeBox = async id => b.rect(`.cx-node[data-id="${id}"]`);
const handle = async (id, which) => { const s = await slot(id), n = await nodeBox(id), z = await b.eval(`${E}.view.z`); return which === 'up' ? {x: s.x, y: s.t} : {x: s.x, y: n.t + n.h + 5 * z}; };
const at = sel => b.eval(`(() => { const e = ${sel}; if (!e) return null; e.scrollIntoView({block: 'nearest'}); const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height}; })()`);
const byText = (sel, t, starts = true) => `[...document.querySelectorAll(${JSON.stringify(sel)})].find(x => x.offsetParent !== null && (${starts} ? x.textContent.trim().startsWith(${JSON.stringify(t)}) : x.textContent.trim() === ${JSON.stringify(t)}))`;
const clickText = async (sel, t, starts = true) => { const r = await at(byText(sel, t, starts)); if (!r) throw new Error('no ' + sel + ' ' + t); await b.click(r.x, r.y); return r; };
const palItem = name => at(`[...document.querySelectorAll('.cx-pal-item')].find(x => x.querySelector('.n').textContent === ${JSON.stringify(name)})`);
const saved = async () => { await b.until(`${E}.saveState() === 'ok'`, 8000).catch(() => {}); await sleep(150); };
const sameAsFile = async label => { await saved(); const s = await text(), d = readFileSync(FILE, 'utf-8'); return check(`file = canvas after ${label}`, s === d, s === d ? '' : `${s.length} vs ${d.length}`); };
const toast = () => b.eval(`(() => { const t = document.querySelector('.cx-toast'); return t.style.display === 'none' ? '' : t.textContent; })()`);
const dialogText = () => b.eval(`(() => { const d = document.querySelector('.cx-dialog'); return d ? d.textContent : ''; })()`);
const linkDrag = async (fromId, which, to, opts = {}) => {
    const a = await handle(fromId, which), s = await slot(fromId);
    await b.move(s.x, s.y, 2);                // over the node first: the handles show under the mouse
    await b.move(a.x, a.y, 2);
    const t = typeof to === 'string' ? await slot(to) : (to || opts.to);
    await b.drag(a.x, a.y, t.x, t.y, {steps: 16, hold: opts.hold});
    await sleep(100);
};
const drop = async (name, col, row) => { const p = await palItem(name), c = await cell(col, row); await b.drag(p.x, p.y, c.x, c.y, {steps: 18}); await sleep(150); };
const fieldXY = f => at(`document.querySelector('.cx-props [data-field="${f}"]')`);
const typeInto = async (f, t) => { const q = await fieldXY(f); await b.click(q.x, q.y); await b.key('a', 'ctrl'); await b.type(t); };
const fieldValue = f => b.eval(`document.querySelector('.cx-props [data-field="${f}"]').value`);
const clickCanvasEmpty = async () => { const r = await b.rect('.cx-canvas'); await b.click(r.l + r.w - 20, r.t + 20); };
const backups = () => readdirSync(DATA).filter(f => f.startsWith('tree_design.backup-')).sort();
const menu = async (label, item) => { await clickText('#cx_tools button', label); await clickText('.cx-menu div', item); };
const importFile = async path => {
    await menu('Файл', 'Импорт');
    await sleep(200);
    const doc = await b.send('DOM.getDocument', {});
    const inp = await b.send('DOM.querySelector', {nodeId: doc.root.nodeId, selector: 'input[type=file]'});
    await b.send('DOM.setFileInputFiles', {nodeId: inp.nodeId, files: [path]});
    await b.until('!!document.querySelector(".cx-dialog")');
};
// what a user sees on the canvas, measured: every piece of every line against the names (their text), the prices, the crew cards and the slots
// of the buildings the line does not belong to; the names cut or too small; returns the lists
const measure = () => b.eval(`(() => {
    const hit = (a, c) => a.left < c.right - 0.5 && c.left < a.right - 0.5 && a.top < c.bottom - 0.5 && c.top < a.bottom - 0.5;
    const names = [...document.querySelectorAll('.cx-node .name')].map(e => { const rg = document.createRange(); rg.selectNodeContents(e); const rs = [...rg.getClientRects()];
        return {id: e.parentElement.dataset.id, t: e.textContent, box: {left: Math.min(...rs.map(r => r.left)), right: Math.max(...rs.map(r => r.right)), top: Math.min(...rs.map(r => r.top)), bottom: Math.max(...rs.map(r => r.bottom))}, el: e}; });
    const prices = [...document.querySelectorAll('.cx-node .price')].map(e => ({id: e.closest('.cx-node').dataset.id, box: e.getBoundingClientRect()}));
    const cards = [...document.querySelectorAll('.cx-node .thumbs .card')].map(e => ({id: e.closest('.cx-node').dataset.id, box: e.getBoundingClientRect()}));
    const slots = [...document.querySelectorAll('.cx-node .slot')].map(e => ({id: e.closest('.cx-node').dataset.id, box: e.getBoundingClientRect()}));
    const svg = document.querySelector('.cx-edges'), m = svg.getScreenCTM();
    const out = {links: 0, lineName: [], linePrice: [], lineCard: [], lineSlot: [], nameCut: [], nameSmall: [], namesOnNames: []};
    for (const g of svg.querySelectorAll('g[data-edge]')) {
        out.links++;
        const pts = JSON.parse(g.dataset.pts).map(([x, y]) => new DOMPoint(x, y).matrixTransform(m));
        const [from, to] = g.dataset.edge.split('|');
        for (let i = 1; i < pts.length; i++) {
            const a = pts[i - 1], c = pts[i];
            const seg = {left: Math.min(a.x, c.x) - 1.2, right: Math.max(a.x, c.x) + 1.2, top: Math.min(a.y, c.y) - 1.2, bottom: Math.max(a.y, c.y) + 1.2};
            for (const n of names) if (hit(seg, n.box)) out.lineName.push(g.dataset.edge + ' x «' + n.t + '»');
            for (const p of prices) if (hit(seg, p.box)) out.linePrice.push(g.dataset.edge + ' x price ' + p.id);
            for (const k of cards) if (hit(seg, k.box)) out.lineCard.push(g.dataset.edge + ' x card ' + k.id);
            // its own slots: the line starts on the parent's top edge; inside them it must not go
            for (const s of slots) { const own = s.id === from || s.id === to; const box = own ? {left: s.box.left, right: s.box.right, top: s.box.top + 2, bottom: s.box.bottom} : s.box; if (hit(seg, box)) out.lineSlot.push(g.dataset.edge + ' x slot ' + s.id); }
        }
    }
    const z = ${E}.view.z;
    for (const n of names) {
        const card = n.el.parentElement.getBoundingClientRect();
        if (n.box.right > card.right + 1 || n.box.left < card.left - 1) out.nameCut.push(n.t);
        const full = mtb.editor.design().nodes.find(x => x.id === n.id).name;
        if (full.length <= 40 && n.t.includes('…')) out.nameCut.push(n.t + ' (…)');
        const px = parseFloat(getComputedStyle(n.el).fontSize) * z;
        const r = n.el.getBoundingClientRect(), cv = document.querySelector('.cx-canvas').getBoundingClientRect();
        if (r.bottom > cv.top && r.top < cv.bottom && r.right > cv.left && r.left < cv.right && px < 11) out.nameSmall.push(n.t + ' ' + px.toFixed(1));
    }
    for (let i = 0; i < names.length; i++) for (let j = i + 1; j < names.length; j++) if (hit(names[i].box, names[j].box)) out.namesOnNames.push(names[i].t + ' / ' + names[j].t);
    for (const k of Object.keys(out)) if (Array.isArray(out[k])) out[k] = [...new Set(out[k])];
    return out;
})()`);
const crossings = m => m.lineName.length + m.linePrice.length + m.lineCard.length + m.lineSlot.length;
// the icons as drawn: the mean brightness of each icon's square on the screen (on the dark panel an icon without its parchment is dark)
const iconLuma = async sel => {
    const boxes = await b.eval(`[...document.querySelectorAll(${JSON.stringify(sel)})].filter(e => e.offsetParent !== null).slice(0, 12).map(e => { const r = e.getBoundingClientRect(); return {x: r.left, y: r.top, width: r.width, height: r.height}; }).filter(r => r.y >= 0 && r.y + r.height <= innerHeight)`);
    const out = [];
    for (const c of boxes) out.push(Math.round(await b.luma(c)));
    return out;
};
const images = () => b.eval(`(async () => {
    const bad = [...document.querySelectorAll('img')].filter(i => i.offsetParent !== null).filter(i => i.getAttribute('src') && (!i.complete || !i.naturalWidth)).map(i => i.src);
    const urls = new Set();
    for (const e of document.querySelectorAll('*')) { const s = getComputedStyle(e); for (const v of [s.backgroundImage, s.borderImageSource, s.maskImage]) for (const m of (v || '').matchAll(/url\\("?([^")]+)"?\\)/g)) urls.add(m[1]); }
    const missing = [];
    for (const u of urls) if (!u.startsWith('data:')) { const r = await fetch(u); if (!r.ok) missing.push(u); }
    return {bad, missing};
})()`);

// CAPS_ONLY=1: only part 4 (the new capabilities), for a quick walk
if (process.env.CAPS_ONLY) {
    try { await walkCaps(); const errs = b.errors.filter(e => !/status of 409 \(Conflict\).*api\/tree_design\?base=/.test(e)); check("caps: the console is clean (the 409 of the conflict walked on purpose aside), no dialog", !errs.length && !b.dialogs.length, [...errs, ...b.dialogs]); } catch (e) { failed++; console.log("FAIL walk stopped: " + e.stack); try { await b.shot(join(SHOTS, "caps_walk_error.png")); } catch (x) { /* no picture */ } }
    await b.close(); server.kill();
    check("the author's working file web/data/tree_design.json untouched, byte for byte", hash(WORK) === workBefore);
    console.log(`checks: ${results.length}, failed: ${failed}`); process.exit(failed ? 1 : 0);
}
try {
    await b.open(URL0 + '?mode=constructor');
    await b.until('!!(window.mtb && window.mtb.editor && document.querySelector(".cx-node"))', 15000);
    await sleep(500);
    await b.eval(`${E}.fold('palette', false); ${E}.fold('props', false)`);

    // ======== part 1: a tree from nothing ========
    let before = backups();
    await menu('Файл', 'Очистить');
    await clickText('.cx-dialog .btns button', 'Очистить');
    await b.until('mtb.editor.design().nodes.length === 0');
    await sameAsFile('clearing');
    const made = backups().filter(f => !before.includes(f));
    check('clearing kept a copy of the old file beside it', made.length === 1 && readFileSync(join(DATA, made[0]), 'utf-8') === START);

    // the working view at 1280 x 800: one step smaller than 100 % (the names stay 11.6 px), four columns and five rows in sight
    await clickText('.cx-zoom button', '100%', false);
    await clickText('.cx-zoom button', '−', false);
    let r = await b.rect('.cx-canvas');
    let c00 = await cell(0, 0);
    const want = {x: r.l + 100, y: r.t + r.h - 90};
    await b.drag(r.x, r.y, r.x + want.x - c00.x, r.y + want.y - c00.y, {steps: 10});
    c00 = await cell(0, 0);
    check('the canvas pans by dragging the background', Math.abs(c00.x - want.x) < 2 && Math.abs(c00.y - want.y) < 2);
    // the camera of the walk: back to this view before an action whose places it computes (a new building may move the view to show itself)
    const homeView = await b.eval(`({...${E}.view})`);
    const home = () => b.eval(`Object.assign(${E}.view, ${JSON.stringify(homeView)}); ${E}.applyView()`);
    check('cursors: a hand on the background, a hand on a node, a cross on a handle', await b.eval(`getComputedStyle(document.querySelector('.cx-canvas')).cursor === 'grab'`));

    // the palette: its icons on the slot's parchment, the placed ones marked
    const lumaPal = await iconLuma('.cx-pal-item .cx-slotpic');
    check('palette: every icon on the parchment (mean brightness > 110)', lumaPal.length > 5 && lumaPal.every(l => l > 110), lumaPal);
    check('palette: rows end in … when long, nothing sticks out', await b.eval(`[...document.querySelectorAll('.cx-pal-item .n, .cx-pal-item .m')].every(e => getComputedStyle(e).textOverflow === 'ellipsis' && e.getBoundingClientRect().right <= document.querySelector('.cx-pal-list').getBoundingClientRect().right + 0.5)`));
    await drop('Заготовка под корабль', 1, 0);
    await drop('Прочный корпус', 1, 1);
    let d = await design();
    const H1 = d.nodes[0].id, H2 = d.nodes[1].id;
    check('palette: nodes with the mod\'s fields, the second hull linked by the mod', d.nodes.length === 2 && d.nodes[1].cost === 1500 && d.nodes[1].requires.includes(H1));
    check('palette: a placed item marked with a badge, not faded', await b.eval(`(() => { const e = [...document.querySelectorAll('.cx-pal-item')].find(x => x.querySelector('.n').textContent === 'Прочный корпус'); return !!e.querySelector('.badge') && getComputedStyle(e).opacity === '1'; })()`));
    await drop('Каркас с рунами', 1, 2);
    await drop('Пивной чертог', 0, 2);
    await drop('Манекен для учебной стрельбы', 0, 3);
    await drop('Орудийные порты', 3, 2);
    await drop('Сигнальная система', 2, 3);
    const BEER = await idOf('Пивной чертог'), DUM = await idOf('Манекен для учебной стрельбы'), GUNS = await idOf('Орудийные порты'), SIG = await idOf('Сигнальная система');
    await sameAsFile('palette drops');
    await linkDrag(H2, 'up', BEER);
    await linkDrag(H2, 'up', GUNS);
    await linkDrag(SIG, 'down', H2);
    await linkDrag(BEER, 'up', DUM);
    d = await design();
    check('links drawn by the handles', T.byId(d, BEER).requires.join() === H2 && T.byId(d, GUNS).requires.join() === H2 && T.byId(d, SIG).requires.join() === H2 && T.byId(d, DUM).requires.join() === BEER);
    await sameAsFile('links');
    await drop('Тир', 0, 4);
    check('the next level of the dummies linked by the mod', T.byId(await design(), await idOf('Тир')).requires.join() === DUM);

    // item 6: a link let go on its own node makes nothing; let go on an empty cell, a building in that very cell
    let n0 = (await design()).nodes.length;
    const g0 = await handle(GUNS, 'up'), gs = await slot(GUNS);
    await b.move(gs.x, gs.y, 2); await b.move(g0.x, g0.y, 2);
    await b.drag(g0.x, g0.y, gs.x + 10, gs.y + 20, {steps: 12});
    check('6: a link let go on its own building makes nothing', (await design()).nodes.length === n0);
    const target = await cell(3, 3);
    await linkDrag(GUNS, 'up', null, {to: target});
    await b.key('a', 'ctrl'); await b.type('Орудийная палуба');
    const DECK = await idOf('Орудийная палуба');
    d = await design();
    check('6: a link let go on an empty cell: the building in that very cell, with the link', !!DECK && T.byId(d, DECK).col === 3 && T.byId(d, DECK).row === 3 && T.byId(d, DECK).requires.join() === GUNS, [T.byId(d, DECK).col, T.byId(d, DECK).row]);
    // and on a taken cell from below: the nearest free one under it
    const taken = await cell(1, 2);
    await linkDrag(SIG, 'down', null, {to: {x: taken.x + 60, y: taken.y - 52}});      // in the cell, beside its card
    await b.key('Escape');
    d = await design();
    const under = d.nodes.find(n => n.requires.length === 0 && T.children(d, n.id).includes(SIG) && n.id !== H2);
    check('6: let go on a taken cell from the lower handle: placed below it', !!under && under.col === 1 && under.row < 2, under && [under.col, under.row]);
    await b.key('z', 'ctrl');       // the building made there: taken back
    check('6: and that building deleted again', !T.byId(await design(), under ? under.id : 'none'));

    // empty buildings: a double click (in that cell), the context menu; a node with two parents; a cycle refused
    let c = await cell(1, 3);
    await b.dblclick(c.x, c.y);
    await sleep(150);
    await b.key('a', 'ctrl'); await b.type('Оружейная мастерская');
    const A1 = await idOf('Оружейная мастерская');
    check('a double click makes an empty building in that cell, its name typed at once', !!A1 && T.byId(await design(), A1).col === 1 && T.byId(await design(), A1).row === 3);
    await linkDrag(A1, 'down', H2);
    c = await cell(1, 4);
    await b.click(c.x, c.y, {button: 'right'});
    await clickText('.cx-menu div', 'Новая постройка здесь');
    await b.key('a', 'ctrl'); await b.type('Пороховой погреб');
    const POW = await idOf('Пороховой погреб');
    await linkDrag(await idOf('Тир'), 'up', POW);
    await linkDrag(A1, 'up', POW);
    check('a node with two parents', T.byId(await design(), POW).requires.length === 2);
    await home();
    await linkDrag(POW, 'up', H2);
    check('a cycle is refused with a message', /круг/.test(await toast()) && !T.byId(await design(), H2).requires.includes(POW), {toast: await toast(), a1: T.byId(await design(), A1).requires, h2: T.byId(await design(), H2).requires});
    await linkDrag(DECK, 'up', null, {to: await cell(3, 4), hold: async () => {
        const t = await slot(POW);
        await b.move(t.x, t.y, 6); await sleep(150);
        await b.shot(join(SHOTS, 'constructor_edge_drag.png'));
    }});
    check('the dragged link joined the deck to the powder store', T.byId(await design(), POW).requires.includes(DECK));
    await sameAsFile('empty buildings and links');

    // item 13: Delete after a click on a button of a panel deletes nothing; with the canvas in focus it deletes
    await home();
    let p = await slot(DECK);
    await b.click(p.x, p.y);
    await clickText('.cx-zoom button', '+', false);
    await b.key('Delete'); await b.key('Backspace');
    check('13: Delete and Backspace after a click on a button delete nothing', !!T.byId(await design(), DECK));
    await home();
    // a node with links deleted (the bar's button makes it, Backspace on the canvas deletes it)
    await clickText('#cx_tools button', '+ Постройка');
    await b.key('a', 'ctrl'); await b.type('Временная');
    const TMP = await idOf('Временная');
    await linkDrag(SIG, 'up', TMP);
    p = await slot(TMP);
    await b.click(p.x, p.y);
    await b.key('Backspace');
    d = await design();
    check('a node with links deleted (Backspace on the canvas), its links gone', !T.byId(d, TMP) && !d.nodes.some(n => n.requires.includes(TMP)));
    await sameAsFile('deleting a node with links');

    // every field of the powder store
    p = await slot(POW);
    await b.click(p.x, p.y);
    await typeInto('description', 'Бочки с порохом под палубой: стрелки берут заряды прямо отсюда.');
    await typeInto('cost', '2200');
    await typeInto('turns', '2');
    await b.eval(`document.querySelector('.cx-props [data-field="tier"]').focus()`); await b.key('ArrowDown'); await b.key('ArrowDown'); await b.key('ArrowDown');
    await typeInto('note', 'Хочу, чтобы погреб давал +15% боезапаса стрелкам и открывал громобоев. Риск: взрыв при попадании?');
    const addLine = async t => { await clickText('.cx-props .cx-effects .cx-actions button', '+ Строка'); await b.type(t); };
    await addLine('Боезапас стрелков: +15%');
    await addLine('Риск взрыва при попадании');
    let q = await at(`document.querySelectorAll('.cx-props .cx-effects .e')[1].querySelector('.ebtns button')`); await b.click(q.x, q.y);
    q = await at(`document.querySelectorAll('.cx-props .cx-effects .e')[1].querySelectorAll('.ebtns button')[1]`); await b.click(q.x, q.y);
    q = await at(`document.querySelectorAll('.cx-props .cx-effects .e')[1].querySelector('img')`); await b.click(q.x, q.y);
    await b.until('!!document.querySelector(".cx-gallery.small .g")');
    const effNames = await b.eval(`[...document.querySelectorAll('.cx-gallery.small .g')].map(g => g.textContent)`);
    check('the gallery of line icons names them for people', effNames.every(t => /^[А-ЯЁ]/.test(t.trim())), effNames.slice(0, 5));
    await clickText('.cx-gallery.small .g', 'Опыт', false);
    await clickText('.cx-props .cx-field button', 'Выбрать…');      // the icon's
    await b.until('document.querySelectorAll(".cx-gallery .g .cx-slotpic").length > 10');
    const galNames = await b.eval(`[...document.querySelectorAll('.cx-gallery .g .gl')].map(g => g.textContent)`);
    check('C: the icon gallery names each icon by its building, not its file', galNames.every(t => !/\\.png|_/.test(t)), galNames.slice(0, 6));
    await sleep(300);
    const lumaGal = await iconLuma('.cx-gallery .g .cx-slotpic');
    check('C: the gallery\'s icons on the parchment', lumaGal.every(l => l > 110), lumaGal);
    await b.shot(join(SHOTS, 'constructor_props_gallery.png'));
    await b.type('трюм');
    await sleep(200);
    await clickText('.cx-gallery .g', 'Трюм');
    const crewBtn = await at(`[...document.querySelectorAll('.cx-props button')].find(x => x.textContent === 'Выбрать…' && x.closest('.cx-field').querySelector('label').textContent.startsWith('Открывает'))`);
    await b.click(crewBtn.x, crewBtn.y);
    await b.until('!!document.querySelector(".cx-crewlist label")');
    await clickText('.cx-crewlist label', 'Громобои', false).catch(async () => { const x = await at(byText('.cx-crewlist label', 'Громобои').replace('.startsWith', '.includes')); await b.click(x.x, x.y); });
    await b.key('Escape');
    await clickText('.cx-props .cx-swatches button', 'Золотая', false);
    await typeInto('mod_key', 'powder_store_1');
    check('a key the mod lacks is told', /нет такой/.test(await b.eval(`document.querySelector('.cx-props .help.bad') ? document.querySelector('.cx-props .help.bad').textContent : ''`)));
    await typeInto('mod_key', '');
    d = await design();
    let P = T.byId(d, POW);
    check('every field edited', P.description.startsWith('Бочки') && P.cost === 2200 && P.turns === 2 && P.tier === 3 && P.note.startsWith('Хочу') && P.effects.length === 2
        && P.effects[0].text.startsWith('Риск') && P.effects[0].good === false && P.effects[1].icon && P.effects[1].icon.endsWith('experience.png') && P.crew.some(x => x.option === 'thunderers')
        && P.branch === 'gold' && P.mod_key === null && P.icon && P.icon.includes('cargo_hold'), P);
    await sameAsFile('editing the fields');
    // item 10: a number field shows what was written down once left
    await typeInto('cost', '-5'); await b.key('Tab');
    await typeInto('turns', '45'); await b.key('Tab');
    const v1 = [await fieldValue('cost'), await fieldValue('turns')];
    await typeInto('cost', '013'); await b.key('Tab');
    await typeInto('turns', '0'); await b.key('Tab');
    const v2 = [await fieldValue('cost'), await fieldValue('turns')];
    P = T.byId(await design(), POW);
    check('10: the numbers shown are those kept (−5 → 0, 45 → 30, 013 → 13, 0 → 1)', v1.join() === '0,30' && v2.join() === '13,1' && P.cost === 13 && P.turns === 1, [v1, v2]);
    await typeInto('cost', '2200'); await typeInto('turns', '2'); await b.key('Tab');
    // item 14: a field typed and F5 at once: nothing lost, no question
    await typeInto('name', 'Пороховой погреб');
    await typeInto('note', 'Хочу, чтобы погреб давал +15% боезапаса стрелкам. Записано перед F5');
    await b.key('F5');
    await b.reload();
    await b.until('!!(window.mtb && window.mtb.editor && document.querySelector(".cx-node"))', 15000);
    await sleep(500);
    check('14: typed then F5 at once: kept, no «Покинуть сайт?»', T.byId(await design(), POW).note.endsWith('перед F5') && !b.dialogs.length && readFileSync(FILE, 'utf-8').includes('перед F5'), b.dialogs);
    check('14: no banner of unsaved changes after the reload', !(await b.eval(`!!document.querySelector('.cx-banner')`)));
    await home();
    p = await slot(POW);
    await b.click(p.x, p.y);
    await b.eval(`document.querySelector('.cx-props').scrollTop = 0`);
    await sleep(200);
    await b.shot(join(SHOTS, 'constructor_props.png'));

    // a group moved: Shift + a frame round column 0, dragged one column right; item 7: a node let go over a panel goes back
    await clickCanvasEmpty();
    await home();
    const col0 = (await design()).nodes.filter(n => n.col === 0).map(n => n.id);
    const top0 = await cell(0, 4), low0 = await cell(0, 2);
    b.mods = 8;
    await b.drag(top0.x - 100, top0.y - 60, low0.x + 70, low0.y + 50, {steps: 8});
    b.mods = 0;
    const selNow = await b.eval(`${E}.sel`);
    check('Shift + frame selects the column', col0.every(id => selNow.includes(id)) && selNow.length === col0.length, {selNow, col0, top0, low0});
    if (process.env.DEBUG) await b.shot(join(SHOTS, 'constructor_walk_debug.png'));
    let g = await slot(col0[0]);
    const z = await b.eval(`${E}.view.z`);
    const rowsBefore = Object.fromEntries((await design()).nodes.filter(n => col0.includes(n.id)).map(n => [n.id, n.row]));
    await b.drag(g.x, g.y, g.x, g.y - T.CX.CH * z, {steps: 10});
    d = await design();
    check('the group moved one row up', col0.every(id => T.byId(d, id).row === rowsBefore[id] + 1), col0.map(id => T.byId(d, id).row));
    await sameAsFile('moving a group');
    await b.key('ArrowDown');
    check('arrows move the group', (await design()).nodes.filter(n => col0.includes(n.id)).every(n => n.row === rowsBefore[n.id]));
    g = await slot(col0[0]);
    const pal = await b.rect('.cx-palette');
    await b.drag(g.x, g.y, pal.x, pal.y, {steps: 12});
    d = await design();
    check('7: nodes let go over a panel go back to their place', (await design()).nodes.filter(n => col0.includes(n.id)).every(n => n.col === 0));

    // copy, paste, duplicate, and the long undo / redo
    await home();
    const beforeCopies = await text();
    p = await slot(DECK);
    await b.click(p.x, p.y);
    await b.key('d', 'ctrl');
    await b.key('c', 'ctrl');
    const pc = await cell(3, 4);
    await b.move(pc.x, pc.y, 4);
    await b.key('v', 'ctrl');
    check('Ctrl+D and Ctrl+C / Ctrl+V add copies', (await design()).nodes.filter(n => n.name === 'Орудийная палуба').length === 3);
    for (let i = 0; i < 12; i++) await b.key('z', 'ctrl');
    const mid = await text();
    await sameAsFile('12 undos');
    for (let i = 0; i < 12; i++) await b.key('y', 'ctrl');
    await b.key('z', 'ctrl'); await b.key('z', 'ctrl');
    await b.key('z', 'ctrl+shift'); await b.key('z', 'ctrl+shift');
    check('12 undos changed the tree, 12 redos gave it back', mid !== (await text()) && (await design()).nodes.filter(n => n.name === 'Орудийная палуба').length === 3);
    await sameAsFile('redos');
    await b.key('z', 'ctrl'); await b.key('z', 'ctrl');
    check('two undos take the copies away', (await text()) === beforeCopies);
    await sameAsFile('undoing the copies');

    // the warnings: an orphan without a cost; the list from the status line
    await home();
    c = await cell(3, 1);
    await b.dblclick(c.x, c.y);
    await b.key('a', 'ctrl'); await b.type('Сирота');
    await typeInto('cost', '0'); await b.key('Escape');
    await clickText('.cx-status .cx-warnbtn', '⚠');
    const warns = await b.eval(`[...document.querySelectorAll('.cx-warnlist li')].map(x => x.textContent)`);
    check('warnings: the orphan and its missing cost', warns.some(w => /Сирота.*нет пути/.test(w)) && warns.some(w => /Сирота.*нет цены/.test(w)), warns);
    await b.shot(join(SHOTS, 'constructor_warnings.png'));
    await clickText('.cx-status .cx-warnbtn', '⚠');
    p = await slot(await idOf('Сирота'));
    await b.click(p.x, p.y, {button: 'right'});
    await clickText('.cx-menu div', 'Удалить');
    check('deleted from the context menu', !(await idOf('Сирота')));
    // item 18: an old message gone at the next action
    await b.key('z', 'ctrl');
    const t1 = await toast();
    p = await slot(H2); await b.click(p.x, p.y);
    check('18: an old message goes at the next action', !!t1 && !(await toast()));
    await b.key('y', 'ctrl');

    // the palette picture: searching, an item dragged over the canvas; let go outside it adds nothing
    await home();
    r = await b.rect('.cx-pal-search input');
    await b.click(r.x, r.y);
    await b.type('пив');
    await sleep(200);
    const p1 = await palItem('Столовая');
    const pd = await cell(2, 4);
    const nBefore = (await design()).nodes.length;
    await b.move(p1.x, p1.y, 2); await b.down(); await b.move(pd.x, pd.y, 14); await sleep(200);
    await b.shot(join(SHOTS, 'constructor_palette.png'));
    await b.move(10, 400, 6); await b.up();
    await b.click(r.x, r.y); await b.key('a', 'ctrl'); await b.key('Delete'); await b.key('Escape');
    check('a palette drag let go outside the canvas adds nothing', (await design()).nodes.length === nBefore);

    // item 11: the server does not answer: a short state and a button; the page retries by itself, then all is in the file
    await b.send('Fetch.enable', {patterns: [{urlPattern: '*api/tree_design*'}]});
    const failing = m => { if (m.method === 'Fetch.requestPaused') b.send('Fetch.failRequest', {requestId: m.params.requestId, errorReason: 'ConnectionRefused'}).catch(() => {}); };
    b.listen(failing);
    p = await slot(H2); await b.click(p.x, p.y);
    await typeInto('note', 'Правка без сервера');
    await b.key('Tab');
    await b.until(`${E}.saveState() === 'bad'`, 5000);
    const st = await b.eval(`({text: document.getElementById('cx_save').textContent, retry: getComputedStyle(document.getElementById('cx_retry')).display !== 'none', fits: document.getElementById('cx_tools').scrollWidth <= document.getElementById('cx_tools').clientWidth + 1})`);
    await b.shot(join(SHOTS, 'constructor_save_failed.png'), {x: 640, y: 0, width: 640, height: 42});
    check('11: a failed save: a short state, a visible «Повторить», nothing cut', st.text.length <= 16 && st.retry && st.fits, st);
    b.unlisten(failing);
    await b.send('Fetch.disable');
    // the refused requests of this check are its own: not errors of the page
    for (let i = b.errors.length - 1; i >= 0; i--) if (/ERR_CONNECTION_REFUSED.*api\/tree_design/.test(b.errors[i])) b.errors.splice(i, 1);
    await b.until(`${E}.saveState() === 'ok'`, 9000).catch(() => {});
    check('11: retried by itself once the server answers: the file has the change', readFileSync(FILE, 'utf-8').includes('Правка без сервера'));

    // the tree's picture, then F5: everything in its place
    await clickCanvasEmpty();
    await b.key('f');
    await sleep(300);
    await b.shot(join(SHOTS, 'constructor_overview.png'));
    const m1 = await measure();
    check('B: the walked tree, no line across a name, price, card or building', crossings(m1) === 0, m1);
    const beforeF5 = await text();
    writeFileSync(join(ROOT, 'build/web/tree_design_walk.json'), beforeF5);
    await b.key('F5');
    await b.reload();
    await b.until('!!(window.mtb && window.mtb.editor && document.querySelector(".cx-node"))', 15000);
    await sleep(400);
    check('F5: the same tree, the file is the tree', (await text()) === beforeF5 && readFileSync(FILE, 'utf-8') === beforeF5);

    // item 12: a JSON that is not a tree is refused; export and import of a real one
    writeFileSync(join(tmp, 'foreign.json'), JSON.stringify({name: 'не дерево', items: [1, 2, 3]}));
    await importFile(join(tmp, 'foreign.json'));
    const refusal = await dialogText();
    check('12: a foreign JSON is refused with a reason, the canvas untouched', /не файл дерева/.test(refusal) && !(await b.eval(`!!${byText('.cx-dialog button', 'Заменить')}`)) && (await text()) === beforeF5, refusal);
    await b.key('Escape');
    await b.send('Browser.setDownloadBehavior', {behavior: 'allow', downloadPath: tmp});
    await menu('Файл', 'Экспорт');
    await sleep(800);
    check('export: the file downloaded is the tree', existsSync(join(tmp, 'tree_design.json')) && readFileSync(join(tmp, 'tree_design.json'), 'utf-8') === beforeF5);

    // ======== the author's case: the hull, three empty rows, the runed frame straight over it; side links beside ========
    const strt = T.normalize(JSON.parse(START)).design;
    const h2 = strt.nodes.find(n => n.mod_key === 'airship_hull_2');
    const frame = T.addNode(strt, {name: 'Каркас с рунами', col: h2.col, row: h2.row + 4, cost: 3000, turns: 2});
    const forge = T.addNode(strt, {name: 'Кузня', col: h2.col + 1, row: h2.row + 1, cost: 1000});
    const arsenal = T.addNode(strt, {name: 'Арсенал', col: h2.col + 2, row: h2.row + 2, cost: 1000});
    for (const x of [frame, forge, arsenal]) T.addEdge(strt, h2.id, x);
    writeFileSync(join(tmp, 'straight.json'), T.serialize(strt));
    await importFile(join(tmp, 'straight.json'));
    await clickText('.cx-dialog .btns button', 'Заменить');
    await b.until(`mtb.editor.design().nodes.length === ${strt.nodes.length}`);
    await clickCanvasEmpty();
    await b.key('f');
    await sleep(300);
    const wayOf = (f, x) => b.eval(`JSON.parse(document.querySelector('.cx-edges g[data-edge="${f}|${x}"]').dataset.pts)`);
    const way = await wayOf(h2.id, frame);
    const hc = await b.eval(`${E}.cardOf(${JSON.stringify(h2.id)}).cx`);
    check('the author\'s case: the hull to the frame over 3 empty rows, one straight line out of the middle', way.length === 2 && way[0][0] === hc && way[1][0] === hc, way);
    const sides = [await wayOf(h2.id, forge), await wayOf(h2.id, arsenal)];
    check('the author\'s case: the side links leave right of the middle, one step each', sides.every(p => p[0][0] > hc && p.length === 4), sides);
    await b.shot(join(SHOTS, 'constructor_straight_edges.png'));
    // a building put on the way: round it; taken away: straight again
    const midc = await cell(h2.col, h2.row + 2);
    await b.dblclick(midc.x + 55, midc.y);         // beside the straight line, in the same cell
    await b.key('a', 'ctrl'); await b.type('На пути'); await b.key('Escape');
    let w2 = await wayOf(h2.id, frame);
    const m2 = await measure();
    check('a building put on the way: the line goes round it, crossing nothing', w2.length > 2 && crossings(m2) === 0, {pts: w2.length, n: crossings(m2)});
    await b.shot(join(SHOTS, 'constructor_straight_edges_blocked.png'));
    const inWay = await idOf('На пути');
    const iw = await slot(inWay);
    await b.click(iw.x, iw.y);
    await b.key('Delete');
    w2 = await wayOf(h2.id, frame);
    check('taken away (Delete): straight again', w2.length === 2, w2);

    // ======== part 2: the stand of 26 buildings, imported, measured ========
    writeFileSync(join(tmp, 'stand.json'), T.serialize(standDesign(JSON.parse(START))));
    before = backups();
    await importFile(join(tmp, 'stand.json'));
    await clickText('.cx-dialog .btns button', 'Заменить');
    await b.until('mtb.editor.design().nodes.length === 26');
    await sameAsFile('importing the stand');
    check('import kept a copy of the replaced file', backups().filter(f => !before.includes(f)).length === 1);
    const sw = await b.eval(`document.querySelector('.cx-warnbtn').textContent`);
    await clickText('.cx-status .cx-warnbtn', '⚠');
    const standWarns = await b.eval(`[...document.querySelectorAll('.cx-warnlist li')].map(x => x.textContent)`);
    check('8-9: the constructor warns of a description the game\'s window would shorten', standWarns.some(w => /Флагман.*описание длиннее \d+ знаков/.test(w)), standWarns.length ? standWarns : sw);
    await clickText('.cx-status .cx-warnbtn', '⚠');
    const sizes = [[1600, 900, false], [1280, 800, false], [1280, 800, true], [1024, 768, true]];
    for (const [w, hh, foldIt] of sizes) {
        await b.size(w, hh);
        await b.eval(`${E}.fold('palette', ${foldIt}); ${E}.fold('props', ${foldIt})`);
        await clickCanvasEmpty();
        await b.key('f');
        await sleep(350);
        const m = await measure();
        const tag = `${w}${foldIt ? ', panels folded' : ''}`;
        check(`B: stand at ${tag} («Показать всё»): no line across a name, price, card or building`, crossings(m) === 0 && m.links === 35, {links: m.links, n: crossings(m), ex: [...m.lineName, ...m.linePrice, ...m.lineCard, ...m.lineSlot].slice(0, 5)});
        check(`A: stand at ${tag}: no name cut, none under 11 px, none on another`, !m.nameCut.length && !m.nameSmall.length && !m.namesOnNames.length, {cut: m.nameCut, small: m.nameSmall.slice(0, 4), on: m.namesOnNames});
        if (!(w === 1280 && !foldIt)) await b.shot(join(SHOTS, `constructor_big_tree_${w}.png`));
    }
    await b.eval(`${E}.fold('palette', false); ${E}.fold('props', false)`);
    await b.size(1600, 900);
    await clickCanvasEmpty();
    await clickText('.cx-zoom button', '100%', false);
    const m100 = await measure();
    // the links up a free column are straight: no bend; no two links share a stretch
    const bentStraight = await b.eval(`(() => { const d = mtb.editor.design(), at = {}; for (const n of d.nodes) at[n.col + ':' + n.row] = n.id; const out = [];
        for (const g of document.querySelectorAll('.cx-edges g[data-edge]')) { const [f, t] = g.dataset.edge.split('|'), a = d.nodes.find(n => n.id === f), c = d.nodes.find(n => n.id === t);
            if (a.col !== c.col || c.row <= a.row) continue; let freeWay = true; for (let r = a.row + 1; r < c.row; r++) if (at[a.col + ':' + r]) freeWay = false;
            const pts = JSON.parse(g.dataset.pts); if (freeWay) out.push({k: g.dataset.edge, bends: pts.length - 2}); } return out; })()`);
    check('stand: links up a free column have no bend', bentStraight.length > 0 && bentStraight.every(x => x.bends === 0), bentStraight);
    const shared = await b.eval(`(() => { const segs = []; for (const g of document.querySelectorAll('.cx-edges g[data-edge]')) { const p = JSON.parse(g.dataset.pts); for (let i = 1; i < p.length; i++) segs.push({k: g.dataset.edge, a: p[i - 1], b: p[i]}); }
        let n = 0; for (let i = 0; i < segs.length; i++) for (let j = i + 1; j < segs.length; j++) { const s = segs[i], t = segs[j]; if (s.k === t.k) continue;
            for (const ax of [0, 1]) { const o = 1 - ax; if (s.a[o] === s.b[o] && t.a[o] === t.b[o] && s.a[o] === t.a[o]) { const lo = Math.max(Math.min(s.a[ax], s.b[ax]), Math.min(t.a[ax], t.b[ax])), hi = Math.min(Math.max(s.a[ax], s.b[ax]), Math.max(t.a[ax], t.b[ax])); if (hi - lo > 2) n++; } } }
        return n; })()`);
    check('stand: no two links share a stretch of line', shared === 0, String(shared));
    check('B: stand at 100 %: no line across a name, price, card or building', crossings(m100) === 0, crossings(m100));
    check('A: stand at 100 %: names 14 px, none cut', !m100.nameCut.length && !m100.nameSmall.length);
    // the link under the mouse lit with its two buildings; a selected building lights its links and dims the rest
    const eg = await b.eval(`(() => { const m = document.querySelector('.cx-edges').getScreenCTM(), cv = document.querySelector('.cx-canvas').getBoundingClientRect();
        const mid = x => { const p = JSON.parse(x.dataset.pts); if (p.length < 4) return null; const a = new DOMPoint(p[1][0], p[1][1]).matrixTransform(m), c = new DOMPoint(p[2][0], p[2][1]).matrixTransform(m); return {x: (a.x + c.x) / 2, y: (a.y + c.y) / 2}; };
        for (const g of document.querySelectorAll('.cx-edges g[data-edge]')) { const q = mid(g); if (q && q.x > cv.left + 40 && q.x < cv.right - 40 && q.y > cv.top + 40 && q.y < cv.bottom - 40 && document.elementFromPoint(q.x, q.y + 5).closest('[data-edge]')) return {...q, key: g.dataset.edge}; } return null; })()`);
    await b.move(eg.x, eg.y + 5, 6);       // 5 px off the line: its wide zone
    await sleep(200);
    const hov = await b.eval(`({hot: !!document.querySelector('.cx-edges g.hot[data-edge="${eg.key}"]'), nodes: [...document.querySelectorAll('.cx-node.linkhot')].map(e => e.dataset.id).sort().join()})`);
    check('B: a link under the mouse (5 px off it) lit with its two buildings', hov.hot && hov.nodes === eg.key.split('|').sort().join(), {...hov, eg, under: await b.eval(`(() => { const e = document.elementFromPoint(${eg.x}, ${eg.y + 5}); return e ? e.outerHTML.slice(0, 120) : null; })()`)});
    await b.shot(join(SHOTS, 'constructor_edge_hover.png'));
    const kuz = await idOf('Кузня');
    p = await slot(kuz); await b.click(p.x, p.y);
    const lit = await b.eval(`({hot: document.querySelectorAll('.cx-edges g.hot').length, dim: document.querySelectorAll('.cx-edges g.dim').length})`);
    const kd = await design();
    check('B: a selected building lights its own links and dims the others', lit.hot === T.byId(kd, kuz).requires.length + T.children(kd, kuz).length && lit.dim === 35 - lit.hot, lit);
    await b.shot(join(SHOTS, 'constructor_node_selected.png'));
    // the handles on a selected building cover neither its price nor a name
    const cover = await b.eval(`(() => { const n = document.querySelector('.cx-node.sel'); const hit = (a, c) => a.left < c.right && c.left < a.right && a.top < c.bottom && c.top < a.bottom; const hs = [...n.querySelectorAll('.hd')].map(x => x.getBoundingClientRect()); const others = [...document.querySelectorAll('.cx-node .price, .cx-node .name')].map(x => { const rg = document.createRange(); rg.selectNodeContents(x); const rs = [...rg.getClientRects()]; return x.classList.contains('price') ? x.querySelector('.co').getBoundingClientRect() : {left: Math.min(...rs.map(r => r.left)), right: Math.max(...rs.map(r => r.right)), top: Math.min(...rs.map(r => r.top)), bottom: Math.max(...rs.map(r => r.bottom))}; }); return hs.some(h => others.some(o => hit(h, o))); })()`);
    check('B: the handles cover no price and no name', !cover);
    check('cursors: a hand on a node, a cross on a handle', await b.eval(`getComputedStyle(document.querySelector('.cx-node')).cursor === 'grab' && getComputedStyle(document.querySelector('.cx-node.sel .hd')).cursor === 'crosshair'`));
    check('D: the canvas says «Ряд», the panel «тир корпуса», nothing says «ярус»', await b.eval(`!/ярус/i.test(document.getElementById('constructor').textContent) && /Ряд 1/.test(document.querySelector('.cx-rows').textContent)`));
    let im = await images();
    check('constructor: every picture loaded', !im.bad.length && !im.missing.length, im);
    const lumaProps = await iconLuma('.cx-props .cx-slotpic');
    check('C: the icon in the properties on the parchment', lumaProps.length === 1 && lumaProps[0] > 110, lumaProps);
    // the small window
    await b.size(1000, 700);
    await sleep(300);
    await clickCanvasEmpty();
    await b.key('f');
    await sleep(300);
    await b.shot(join(SHOTS, 'constructor_small_window.png'));
    const small = await b.eval(`(() => { const t = document.getElementById('cx_tools'); return {tools: t.scrollWidth <= t.clientWidth + 1, bar: document.getElementById('bar').scrollWidth <= innerWidth + 1, canvas: document.querySelector('.cx-canvas').clientWidth}; })()`);
    check('1000 px: the bar fits, the canvas has room', small.tools && small.bar && small.canvas > 380, small);
    // 1024: a line of effects readable in the properties
    await b.size(1024, 768);
    await b.eval(`${E}.select([mtb.editor.design().nodes.find(n => n.name === 'Флагман').id])`);
    await sleep(200);
    const fx = await b.eval(`(() => { const i = document.querySelector('.cx-props .cx-effects .e input'); return i ? i.getBoundingClientRect().width : 0; })()`);
    await b.shot(join(SHOTS, 'constructor_props_1024.png'));
    check('17: at 1024 a line of effects is a readable field (> 200 px)', fx > 200, String(fx));

    // ======== part 3: «Игра» with the stand ========
    await b.size(1600, 900);
    await clickText('#mode button', 'Игра', false);
    await b.until('document.body.dataset.mode === "game" && !!mtb.panel.view.tree && mtb.panel.view.tree.length === 26');
    await sleep(500);
    const comp = id => b.eval(`(() => { const e = [...document.querySelectorAll('#screen [data-id="${id}"]')].find(x => x.offsetParent !== null); if (!e) return null; const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, t: r.top, b: r.bottom}; })()`);
    const gm = 'mtb.panel.view';
    const nodeOnScreen = async name => comp('mtb_tree_node_' + await b.eval(`${gm}.tree.findIndex(v => v.node.name === ${JSON.stringify(name)})`));
    const inSight = async name => {
        let n = await nodeOnScreen(name);
        const win = await comp('tree_window');
        for (let i = 0; i < 8 && (n.y < win.t + 30 || n.y > win.b - 30 || n.x < win.x - win.w / 2 + 30 || n.x > win.x + win.w / 2 - 30); i++) {
            await b.drag(win.x, win.y, win.x + Math.max(-150, Math.min(150, win.x - n.x)), win.y + Math.max(-150, Math.min(150, win.y - n.y)), {steps: 6});
            n = await nodeOnScreen(name);
        }
        return n;
    };
    im = await images();
    check('game: every picture loaded', !im.bad.length && !im.missing.length, im);
    check('game: the overview under the screen no longer counts the game\'s hidden effects', !(await b.eval(`/не по-русски/.test(document.getElementById('overview').textContent)`)));
    // the building window of a building with more than it can hold: every line and crew, the description shortened with …, inside the screen
    const flag = await inSight('Флагман');
    await b.move(flag.x, flag.y, 4); await sleep(300);
    const tip = await b.eval(`(() => { const t = [...document.querySelectorAll('#screen .tooltip_frame')].find(x => x.offsetParent !== null); if (!t) return null; const r = t.getBoundingClientRect(), root = document.querySelector('#screen .root').getBoundingClientRect();
        const effects = [...t.querySelectorAll('[data-id^="effect_"]')].filter(x => x.offsetParent !== null && /^effect_[0-9]+$/.test(x.dataset.id)).length;
        const units = [...t.querySelectorAll('[data-id^="unit_name_"]')].filter(x => x.offsetParent !== null).length;
        const desc = t.querySelector('[data-id="description_window"]').textContent;
        const ins = [...document.querySelectorAll('#screen .tooltip_instruction')].find(x => x.offsetParent !== null && x.style.visibility !== 'hidden');
        const bottom = ins ? ins.getBoundingClientRect().bottom : r.bottom;
        return {effects, units, cut: desc.endsWith('…'), inside: r.top >= root.top - 0.5 && bottom <= root.bottom + 0.5}; })()`);
    check('8-9: the game\'s window keeps all 10 lines and 4 crews, shortens the description with …, stays inside the screen', tip && tip.effects === 10 && tip.units === 4 && tip.cut && tip.inside, tip);
    await b.shot(join(SHOTS, 'constructor_game_mode_info.png'));
    // order, turn, short of gold, the crew on the drawing, at the user's scale (~0.6)
    const order = async name => { const n = await inSight(name); await b.click(n.x, n.y); const o = await comp('mtb_ship_order'); await b.click(o.x, o.y); };
    const endTurn = async () => { const e = await b.rect('#end_turn'); await b.click(e.x, e.y); await sleep(120); };
    const gold = async v => { const q2 = await b.rect(`.gold_quick[data-gold="${v}"]`); await b.click(q2.x, q2.y); };
    const status = name => b.eval(`(() => { const v = ${gm}.tree.find(v => v.node.name === ${JSON.stringify(name)}); return mtb.M.status(v.node.key); })()`);
    await gold(6000);
    await order('Заготовка под корабль'); await endTurn();
    check('game: the first hull built', (await status('Заготовка под корабль')).state === 'built');
    await order('Прочный корпус'); await endTurn();
    await gold(0);
    const beer = await inSight('Пивной чертог');
    await b.move(beer.x, beer.y, 4); await sleep(250);
    const reason = await b.eval(`[...document.querySelectorAll('#screen [data-id="reason"]')].filter(x => x.offsetParent !== null && x.parentElement.style.visibility !== 'hidden').map(x => x.textContent).join(' | ')`);
    check('game: short of gold, the reason in red', /Не хватает золота/.test(reason), reason);
    await gold(6000);
    await order('Пивной чертог'); await endTurn();
    const area = await comp('mtb_crew_area_rifles');
    await b.click(area.x, area.y);
    const pick = await comp('mtb_crew_pick_pirates');
    await b.click(pick.x, pick.y);
    await b.click(area.x, area.y);
    check('game: pirates ordered from the drawing', await b.eval('mtb.M.crew_order("rifles")') === 'pirates');
    await order('Каркас с рунами'); await endTurn();
    const three = await status('Пушечная палуба с тремя родителями');
    check('game: three parents missing, all named', three.state === 'locked' && /Мастерская.*Палуба.*Кузня|Нужны постройки/.test(three.why), three.why);
    await sleep(300);
    await b.shot(join(SHOTS, 'constructor_game_mode.png'));
    // «Развернуть дерево»: over the drawing, the game's size; and back
    const ex = await comp('mtb_tree_expand');
    await b.click(ex.x, ex.y);
    await sleep(300);
    const open = await b.eval(`(() => { const w = [...document.querySelectorAll('#screen [data-id="tree_window"]')][0]; const r = w.getBoundingClientRect(), s = [...document.querySelectorAll('#screen [data-id="scheme"]')][0].getBoundingClientRect(); return {open: w.classList.contains('open'), overDrawing: r.left <= s.left + 2, z: mtb.panel.view.pan.z}; })()`);
    check('21: «Развернуть дерево» opens the tree over the drawing at the game\'s size', open.open && open.overDrawing && open.z === 1, open);
    await b.shot(join(SHOTS, 'constructor_game_expanded.png'));
    await b.open(URL0 + '?mode=game&k=1');
    await b.until('!!(window.mtb && mtb.panel && mtb.panel.view.tree)', 15000);
    await sleep(800);
    await b.eval(`document.getElementById('left').scrollLeft = 10000`);
    await sleep(200);
    let ex1 = await comp('mtb_tree_expand');
    await b.click(ex1.x, ex1.y);
    await sleep(300);
    await b.shot(join(SHOTS, 'constructor_game_expanded_k1.png'));
    ex1 = await comp('mtb_tree_expand');
    await b.click(ex1.x, ex1.y);
    check('21: and back into the column', await b.eval(`!document.querySelector('#screen [data-id="tree_window"]').classList.contains('open')`));
    im = await images();
    check('game at 1:1: every picture loaded', !im.bad.length && !im.missing.length, im);
    if (!process.env.SKIP_CAPS) await walkCaps();
    const errs = b.errors.filter(e => !/status of 409 \(Conflict\).*api\/tree_design\?base=/.test(e));
    check('the console is clean (the 409 of the conflict walked on purpose aside), no dialog', !errs.length && !b.dialogs.length, [...errs, ...b.dialogs]);
} catch (e) {
    failed++;
    console.log('FAIL walk stopped: ' + e.stack);
    try { await b.shot(join(SHOTS, 'constructor_walk_error.png')); } catch (x) { /* no picture */ }
} finally {
    await b.close();
    server.kill();
    check('the author\'s working file web/data/tree_design.json untouched, byte for byte', hash(WORK) === workBefore);
    check('no copy of the tree file left in web/data', !readdirSync(join(ROOT, 'web/data')).some(f => f.startsWith('tree_design.backup-')));
}
// Part 4: the new capabilities, on the author's own tree (build/web/tree_design.user_before_caps.json, the copy of his file taken before the work):
// an effect of the catalogue for one crew group and its number in the unit's panel of the game; the free lines read as effects (the proposal's
// row measured at 1024, 1280, 1600); a detail of the ship, drawn and new, built and seen; an army unit opened for recruitment: its card, the
// game's block and its panel; a change of the file from outside while the constructor is open; a conflict of versions. Pictures caps_*.png.
async function walkCaps() {
    let im;
    const gameComp = id => b.eval(`(() => { const e = [...document.querySelectorAll('#screen [data-id="${id}"]')].find(x => x.offsetParent !== null); if (!e) return null; const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, t: r.top, b: r.bottom, l: r.left, r: r.right}; })()`);
    const design = () => b.eval('JSON.stringify(mtb.editor.design())').then(s => JSON.parse(s));
    const nodeByName = async name => (await design()).nodes.find(n => n.name === name);
    const pick = async key => {
        const r = await at(`[...document.querySelectorAll('.cx-pal-item')].find(x => (x.title.split('\\n')[1] || '') === ${JSON.stringify(key)})`);
        if (!r) throw new Error('no palette item ' + key);
        await b.click(r.x, r.y); await sleep(250);
    };
    const savedOk = async () => { await b.until(`${E}.saveState() === 'ok'`, 8000).catch(() => {}); await sleep(200); };
    const fileNode = name => JSON.parse(readFileSync(FILE, 'utf-8')).nodes.find(n => n.name === name);
    const smallText = sel => b.eval(`[...document.querySelectorAll(${JSON.stringify(sel)})].filter(e => e.offsetParent !== null && [...e.childNodes].some(c => c.nodeType === 3 && c.textContent.trim())).map(e => [e.textContent.trim().slice(0, 30), parseFloat(getComputedStyle(e).fontSize)]).filter(([, px]) => px < 11)`);
    const toConstructor = async () => { await clickText('#mode button', 'Конструктор'); await b.until('document.body.dataset.mode === "constructor"'); await sleep(300); };
    const toGame = async () => { await clickText('#mode button', 'Игра'); await b.until('document.body.dataset.mode === "game" && !!mtb.panel.view.tree'); await sleep(500); };
    const gm = 'mtb.panel.view';
    const nodeOnScreen = async name => gameComp('mtb_tree_node_' + await b.eval(`${gm}.tree.findIndex(v => v.node.name === ${JSON.stringify(name)})`));
    const inSight = async name => {
        let n = await nodeOnScreen(name);
        const win = await gameComp('tree_window');
        for (let i = 0; i < 10 && (n.y < win.t + 40 || n.y > win.b - 40 || n.x < win.l + 40 || n.x > win.r - 40); i++) {
            await b.drag(win.x, win.y, win.x + Math.max(-150, Math.min(150, win.x - n.x)), win.y + Math.max(-150, Math.min(150, win.y - n.y)), {steps: 6});
            n = await nodeOnScreen(name);
        }
        return n;
    };
    const selectInGame = async name => { const n = await inSight(name); await b.click(n.x, n.y); await sleep(150); return n; };
    const buildTo = async name => { await selectInGame(name); const r = await b.rect('#build_to'); await b.click(r.x, r.y); await sleep(200); };
    // «Сбросить» reloads the page: the address still says ?mode=constructor, so the game is chosen again
    const resetGame = async () => { const r = await b.rect('#reset_all'); await b.click(r.x, r.y); await sleep(500); await b.until('!!(window.mtb && mtb.panel && mtb.panel.view.tree && mtb.editor)', 15000).catch(() => {}); await sleep(800); if (await b.eval('document.body.dataset.mode') !== 'game') await toGame(); };
    const visibleText = id => b.eval(`(() => { const t = [...document.querySelectorAll('#screen [data-id="${id}"]')].find(x => x.offsetParent !== null); return t ? t.textContent : ''; })()`);
    const infoText = () => b.eval(`(() => { const t = [...document.querySelectorAll('#screen .tooltip_frame')].find(x => x.offsetParent !== null); return t ? [...t.querySelectorAll('[data-id]')].filter(x => x.offsetParent !== null && x.querySelector('.t')).map(x => x.textContent).join(' | ') : ''; })()`);

    writeFileSync(FILE, readFileSync(join(ROOT, 'build/web/tree_design.user_before_caps.json'), 'utf-8'));
    await b.size(1280, 800);
    await b.open(URL0 + '?mode=constructor');
    await b.until('!!(window.mtb && mtb.editor && mtb.editor.design().nodes.length === 22)', 15000);
    await sleep(1000);
    check('caps: the author\'s tree (format 1) opens in the constructor, 22 buildings', (await design()).nodes.length === 22);

    // ---- the proposals of the free lines: one row under the field, measured at three widths, on the two nodes of five lines with proposals ----
    for (const w of [1024, 1280, 1600]) {
        await b.size(w, 800); await sleep(400);
        for (const [key, least] of [['cargo_hold_1', 5], ['engines_1', 2]]) {
            await pick(key);
            const m = await b.eval(`(() => { const pw = document.querySelector('.cx-props').clientWidth; return [...document.querySelectorAll('.cx-props .cx-effects .e')].filter(e => e.querySelector('.propose')).map(e => ({h: Math.round(e.getBoundingClientRect().height), w: Math.round(e.querySelector('.propose').getBoundingClientRect().width), panel: pw, lines: Math.round(e.querySelector('.propose .ptxt').getBoundingClientRect().height / 16)})); })()`);
            check(`caps ${w}: ${key}: every free line read as an effect has its proposal in one row under the field (row ≤ 125 px, proposal ≥ half the panel, ≤ 3 lines of text)`,
                m.length >= least && m.every(x => x.h <= 125 && x.w >= x.panel / 2 && x.lines <= 3), m);
        }
        const small = await smallText('.cx-props *');
        check(`caps ${w}: no text in the properties smaller than 11 px`, !small.length, small.slice(0, 5));
        // the new pickers fit the window: nothing out of it, nothing scrolled sideways, no text under 11 px
        for (const [label, sel] of [['+ Эффект', '.cx-props .cx-effects .cx-actions button']]) {
            await clickText(sel, label);
            await b.until('!!document.querySelector(".cx-pop")');
            await sleep(200);
            const fit = await b.eval(`(() => { const p = document.querySelector('.cx-pop').getBoundingClientRect(), body = document.querySelector('.cx-pop .body');
                const over = [...document.querySelectorAll('.cx-pop .fxrow')].filter(r => r.scrollWidth > r.clientWidth + 1).length;
                return {inside: p.left >= 0 && p.top >= 0 && p.right <= innerWidth && p.bottom <= innerHeight, sideways: body.scrollWidth > body.clientWidth + 1, over}; })()`);
            const tiny = await smallText('.cx-pop *');
            check(`caps ${w}: the catalogue fits the window, no row cut, no text under 11 px`, fit.inside && !fit.sideways && !fit.over && !tiny.length, {fit, tiny: tiny.slice(0, 3)});
            await b.key('Escape'); await sleep(150);
        }
        await pick('artillery_workshop_1');
        await clickText('.cx-props .cx-parts > button', 'Добавить');
        await b.until('!!document.querySelector(".cx-crewlist")');
        const pf = await b.eval(`(() => { const p = document.querySelector('.cx-pop').getBoundingClientRect(), body = document.querySelector('.cx-pop .body'); return p.right <= innerWidth && p.bottom <= innerHeight && body.scrollWidth <= body.clientWidth + 1; })()`);
        check(`caps ${w}: the picker of the ship's details fits the window`, pf);
        await b.key('Escape'); await sleep(150);
    }
    await b.size(1280, 800); await sleep(400);

    // ---- an effect of the catalogue for one group ----
    await pick('cargo_hold_1');
    await clickText('.cx-props .cx-effects .cx-actions button', '+ Эффект');
    await b.until('!!document.querySelector(".cx-fxlist")');
    await b.type('боезапас');
    await sleep(500);
    const small = await smallText('.cx-pop *');
    check('caps: the catalogue: no text smaller than 11 px', !small.length, small.slice(0, 5));
    im = await images();
    check('caps: the catalogue: every icon loaded', !im.bad.length && !im.missing.length, im);
    await b.shot(join(SHOTS, 'caps_effect_catalog.png'));
    const tgt = await at(`[...document.querySelectorAll('.cx-fxlist .targets button')].find(x => x.textContent.trim().startsWith('Стрелки'))`);
    await b.click(tgt.x, tgt.y);
    await sleep(200);
    let hold = await nodeByName('Трюм');
    let fx = hold.effects[hold.effects.length - 1];
    check('caps: the ammunition of the riflemen added from the catalogue', fx.kind === 'ammo' && fx.target === 'rifles' && fx.text === 'Боезапас стрелков: +5 %', fx);
    await b.key('a', 'ctrl'); await b.type('30');
    await sleep(300);
    hold = await nodeByName('Трюм'); fx = hold.effects[hold.effects.length - 1];
    check('caps: the value typed, the line follows it', fx.value === 30 && fx.text === 'Боезапас стрелков: +30 %', fx);
    await savedOk();
    check('caps: the file keeps the effect whole', JSON.stringify(fileNode('Трюм').effects.slice(-1)[0]) === JSON.stringify({kind: 'ammo', target: 'rifles', value: 30, text: 'Боезапас стрелков: +30 %', icon: fx.icon, good: true}), fileNode('Трюм').effects.slice(-1)[0]);
    await b.key('z', 'ctrl'); await sleep(200);
    hold = await nodeByName('Трюм');
    check('caps: Ctrl+Z takes the value back', hold.effects.slice(-1)[0].value === 5, hold.effects.slice(-1)[0]);
    await b.key('y', 'ctrl'); await sleep(200);
    check('caps: Ctrl+Y gives it again', (await nodeByName('Трюм')).effects.slice(-1)[0].value === 30);
    // the catalogue by the keys: the search's Enter takes the first shown, Escape closes, Ctrl+Z takes the effect away
    await clickText('.cx-props .cx-effects .cx-actions button', '+ Эффект');
    await b.until('!!document.querySelector(".cx-fxlist")');
    await b.type('стоимость найма');
    await sleep(200);
    await b.key('Enter'); await sleep(250);
    hold = await nodeByName('Трюм');
    check('caps: Enter in the search takes the first: a game effect with the game\'s text', hold.effects.slice(-1)[0].kind === 'game' && /Стоимость найма/.test(hold.effects.slice(-1)[0].text) && !(await b.eval('!!document.querySelector(".cx-shade")')), hold.effects.slice(-1)[0]);
    await clickText('.cx-props .cx-effects .cx-actions button', '+ Эффект');
    await b.until('!!document.querySelector(".cx-fxlist")');
    await b.key('ArrowDown'); await b.key('ArrowDown');
    const focused = await b.eval('document.activeElement && document.activeElement.classList.contains("pick")');
    await b.key('Escape'); await sleep(150);
    check('caps: the arrows move over the choices, Escape closes', focused && !(await b.eval('!!document.querySelector(".cx-shade")')));
    await clickCanvasEmpty(); await sleep(100); await pick('cargo_hold_1');
    await b.eval(`document.querySelector('.cx-canvas').focus()`);
    await b.key('z', 'ctrl'); await sleep(200);
    check('caps: Ctrl+Z takes the game effect away', (await nodeByName('Трюм')).effects.slice(-1)[0].kind === 'ammo');
    // a free line made an effect by its proposal, its text kept, red by its sense; Ctrl+Z gives the free line back
    const prop = await at(`[...document.querySelectorAll('.cx-props .cx-effects .e')].find(e => e.querySelector('input').value === 'Скорость бараки на поле боя -5%').querySelector('.propose button')`);
    await b.click(prop.x, prop.y); await sleep(200);
    let sp = (await nodeByName('Трюм')).effects.find(e => e.text === 'Скорость бараки на поле боя -5%');
    check('caps: «Сделать» turns the free line into an effect: battle speed -5, red, the author\'s text', sp && sp.kind === 'battle_speed' && sp.value === -5 && !sp.good && sp.own_text, sp);
    await b.eval(`document.querySelector('.cx-canvas').focus()`);
    await b.key('z', 'ctrl'); await sleep(200);
    sp = (await nodeByName('Трюм')).effects.find(e => e.text === 'Скорость бараки на поле боя -5%');
    check('caps: Ctrl+Z gives the free line back as it was', sp && !sp.kind && sp.good);
    await savedOk();

    // ---- in the game: the riflemen's panel counts the hold's ammunition, says where it comes from ----
    await toGame();
    await resetGame();
    await buildTo('Трюм');
    const card = await (async () => { await inSight('Пивной чертог'); return gameComp('mtb_crew_card_beer_hall_1_pirates'); })();
    await b.move(card.x, card.y, 4); await sleep(350);
    const ammo = await visibleText('value_ammo');
    const lines = await visibleText('accuracy');
    check('caps: game: the pirates\' ammunition 96 + 30 % = 125, green, from «Трюм»', ammo === '125' && /Боезапас \+30 %: Трюм/.test(lines), {ammo, lines});
    await b.shot(join(SHOTS, 'caps_effect_group.png'));
    const panelIn = await b.eval(`(() => { const p = [...document.querySelectorAll('#screen .unit_parchment')].find(x => x.offsetParent !== null); const r = p.getBoundingClientRect(), root = document.querySelector('#screen .root').getBoundingClientRect(); return r.top >= root.top - 1 && r.bottom <= root.bottom + 1 && r.left >= root.left - 1 && r.right <= root.right + 1; })()`);
    check('caps: game: the unit\'s panel inside the screen', panelIn);

    // ---- a detail of the ship: one drawn and in 3D, one new; built and seen; the new one named «рисунок не готов» ----
    await toConstructor();
    await pick('mtb_nest_1');
    await clickText('.cx-props .cx-parts > button', 'Добавить');
    await b.until('!!document.querySelector(".cx-crewlist")');
    const rings = await at(`document.querySelector('.cx-crewlist label[title="rings"] input')`);
    await b.click(rings.x, rings.y); await sleep(200);
    await clickText('.cx-crewlist button', '+ Новая деталь');
    await sleep(200);
    await b.type('Дозорные в гнёздах');
    const zone = await at(`document.querySelector('.cx-props [data-field="part_zone_1"]')`);
    await b.eval(`document.querySelector('.cx-props [data-field="part_zone_1"]').focus()`); await b.key('ArrowUp');
    const figs = await at(`document.querySelector('.cx-props [data-field="part_figures_1"]')`);
    await b.click(figs.x, figs.y); await b.key('a', 'ctrl'); await b.type('2');
    const note = await at(`document.querySelector('.cx-props [data-field="part_note_1"]')`);
    await b.click(note.x, note.y); await b.type('Два гнома без оружия смотрят вдаль, по одному в гнезде');
    await sleep(300);
    let nest = await nodeByName('Вороньи гнёзда');
    check('caps: parts: the drawn rings and a new detail, with where, what, how many', nest.parts.length === 2 && nest.parts[0].part === 'rings' && nest.parts[1].name === 'Дозорные в гнёздах'
        && nest.parts[1].zone === 'balloon' && nest.parts[1].figures === 2 && /гнома/.test(nest.parts[1].note), {nest: nest.parts, zone: !!zone});
    const warnText = await b.eval(`mtb.editor.api.select && [...document.querySelectorAll('.cx-warnlist li')].map(l => l.textContent).join(' | ')`);
    await b.eval(`document.querySelector('.cx-canvas').focus()`);
    await b.key('z', 'ctrl'); await sleep(200);
    check('caps: Ctrl+Z takes the note back', !(await nodeByName('Вороньи гнёзда')).parts[1].note);
    await b.key('y', 'ctrl'); await sleep(200);
    await b.eval(`document.querySelector('.cx-props [data-field="part_name_1"]').scrollIntoView({block: 'center'})`); await sleep(150);
    await b.shot(join(SHOTS, 'caps_ship_parts.png'));
    const checks = await b.eval(`(() => { document.querySelector('.cx-warnbtn').click(); return [...document.querySelectorAll('.cx-warnlist li')].map(l => l.textContent); })()`);
    check('caps: the checks name the new detail «(рисунок не готов)»', checks.some(t => /Дозорные в гнёздах» \(рисунок не готов\)/.test(t)), checks.slice(0, 6));
    await b.eval(`document.querySelector('.cx-warnbtn').click()`);
    await savedOk();
    await toGame();
    await resetGame();
    await buildTo('Прочный корпус');
    await selectInGame('Вороньи гнёзда');
    const ord = await gameComp('mtb_ship_order'); await b.click(ord.x, ord.y); await sleep(150);
    check('caps: game: the rings are being built with the nests', await b.eval(`mtb.M.stage('rings')`) === 'build');
    const et = await b.rect('#end_turn'); await b.click(et.x, et.y); await sleep(300);
    await b.until(`!!mtb.viewer.models.part_rings`, 15000).catch(() => {});
    check('caps: game: a turn later the rings stand: on the drawing and in 3D', await b.eval(`mtb.M.stage('rings') === 'ink' && !!mtb.viewer.models.part_rings && mtb.viewer.models.part_rings.visible`));
    const nestOn = await inSight('Вороньи гнёзда');
    await b.move(nestOn.x, nestOn.y, 4); await sleep(350);
    const info = await infoText();
    check('caps: game: the window names both details, the new one «(рисунок не готов)»', /Вид на корабле: Кольца вороньих гнёзд на шаре(?! \()/.test(info) && /Вид на корабле: Дозорные в гнёздах \(рисунок не готов\)/.test(info), info);
    await b.shot(join(SHOTS, 'caps_ship_parts_game.png'));

    // ---- an army unit opened for recruitment ----
    await toConstructor();
    await pick('artillery_workshop_1');
    const unitsBtn = await at(`[...document.querySelectorAll('.cx-props .cx-field')].find(f => f.querySelector('label') && f.querySelector('label').textContent.startsWith('Открывает найм')).querySelector('button')`);
    await b.click(unitsBtn.x, unitsBtn.y);
    await b.until('!!document.querySelector(".cx-crewlist")');
    await b.type('пушки');
    await sleep(400);
    await b.shot(join(SHOTS, 'caps_units_unlock.png'));
    const cannon = await at(`document.querySelector('.cx-crewlist label[title="wh_main_dwf_art_cannon"] input')`);
    await b.click(cannon.x, cannon.y); await sleep(200);
    await b.key('Escape'); await sleep(150);
    check('caps: the forge opens the dwarfs\' cannons for recruitment', (await nodeByName('Маленькая кузница')).units.join() === 'wh_main_dwf_art_cannon');
    // the same unit on the beer hall too: the check names it; its node shows the crew's card and the army's side by side
    await pick('beer_hall_1');
    const ub2 = await at(`[...document.querySelectorAll('.cx-props .cx-field')].find(f => f.querySelector('label') && f.querySelector('label').textContent.startsWith('Открывает найм')).querySelector('button')`);
    await b.click(ub2.x, ub2.y);
    await b.until('!!document.querySelector(".cx-crewlist")');
    const c2 = await at(`document.querySelector('.cx-crewlist label[title="wh_main_dwf_art_cannon"] input')`);
    await b.click(c2.x, c2.y); await sleep(200);
    await clickText('.cx-pop button', 'Готово');
    const dupW = await b.eval(`[...document.querySelectorAll('.cx-warnlist li')].map(l => l.textContent).find(t => /Найм «Пушки» открывают 2/.test(t)) || ''`);
    check('caps: one unit opened by two buildings is in the checks', !!dupW, dupW);
    const beer = (await design()).nodes.find(n => n.mod_key === 'beer_hall_1');
    const box = await b.rect(`.cx-node[data-id="${beer.id}"]`);
    const both = await b.eval(`(() => { const n = document.querySelector('.cx-node[data-id="${beer.id}"]'); return {crew: n.querySelectorAll('.thumbs .card').length, army: n.querySelectorAll('.army .card').length}; })()`);
    check('caps: the node shows the crew\'s cards and the army\'s, on two sides of the slot', both.crew >= 1 && both.army === 1, both);
    await b.shot(join(SHOTS, 'caps_node_cards.png'), {x: Math.max(0, box.l - 40), y: Math.max(0, box.t - 30), width: box.w + 80, height: box.h + 50});
    await savedOk();
    await toGame();
    await resetGame();
    const forge = await inSight('Маленькая кузница');
    await b.move(forge.x, forge.y, 4); await sleep(350);
    const finfo = await infoText();
    check('caps: game: the forge\'s window has the game\'s block «Открывает найм:» with the cannons', /Открывает найм:/.test(finfo) && /Пушки/.test(finfo), finfo);
    const acard = await gameComp('mtb_army_card_artillery_workshop_1_wh_main_dwf_art_cannon');
    await b.move(acard.x, acard.y, 4); await sleep(350);
    const ap = await b.eval(`(() => { const p = [...document.querySelectorAll('#screen .unit_parchment')].find(x => x.offsetParent !== null); if (!p) return null; const r = p.getBoundingClientRect(), root = document.querySelector('#screen .root').getBoundingClientRect();
        return {text: p.textContent, inside: r.top >= root.top - 1 && r.bottom <= root.bottom + 1 && r.left >= root.left - 1 && r.right <= root.right + 1}; })()`);
    check('caps: game: the army card\'s panel: the unit\'s name and its true stats (range 440, ammo, armour), inside the screen', ap && /Пушки/.test(ap.text) && /Дальность/.test(ap.text) && /440/.test(ap.text) && /Броня/.test(ap.text) && ap.inside, ap && ap.text.slice(0, 200));
    im = await images();
    check('caps: game: every picture loaded', !im.bad.length && !im.missing.length, im);
    await b.shot(join(SHOTS, 'caps_unit_panel_army.png'));

    // ---- the file changed from outside while the constructor is open, nothing waiting: taken, the view and the selection kept ----
    await toConstructor();
    await pick('cargo_hold_1');
    await savedOk();
    const view0 = await b.eval(`JSON.stringify([${E}.view.x, ${E}.view.y, ${E}.view.z, ${E}.sel])`);
    const outside = JSON.parse(readFileSync(FILE, 'utf-8'));
    outside.nodes.find(n => n.name === 'Верстак инженера').note = 'Изменено извне';
    writeFileSync(FILE, JSON.stringify(outside, null, 2) + '\n');
    await b.until(`mtb.editor.design().nodes.find(n => n.name === 'Верстак инженера').note === 'Изменено извне'`, 6000).catch(() => {});
    const view1 = await b.eval(`JSON.stringify([${E}.view.x, ${E}.view.y, ${E}.view.z, ${E}.sel])`);
    const said = await toast();
    check('caps: a change from outside is taken by the open constructor, the view and the selection kept, a line in the status', (await nodeByName('Верстак инженера')).note === 'Изменено извне' && view0 === view1 && /изменён извне/.test(said), {said, view0, view1});
    // a stale version is refused by the server and writes nothing
    const before = readFileSync(FILE, 'utf-8');
    const stale = await fetch(URL0 + 'api/tree_design?base=0000000000000000', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: before.replace('Изменено извне', 'старое')});
    const sj = await stale.json();
    check('caps: a write on an old version: 409 with the file as it is, nothing written', stale.status === 409 && sj.error === 'conflict' && sj.text === before && readFileSync(FILE, 'utf-8') === before);
    // the conflict: the same building changed outside and here before it was written
    let dialog = false;
    for (let attempt = 0; attempt < 4 && !dialog; attempt++) {
        await pick('cargo_hold_1');
        await savedOk();
        const o2 = JSON.parse(readFileSync(FILE, 'utf-8'));
        o2.nodes.find(n => n.name === 'Трюм').description += ' ИЗВНЕ' + attempt;
        writeFileSync(FILE, JSON.stringify(o2, null, 2) + '\n');
        const d0 = await at(`document.querySelector('.cx-props [data-field="description"]')`);
        await b.click(d0.x, d0.y); await b.key('End', 'ctrl'); await b.type(' мои' + attempt);
        dialog = await b.until(`${E}.conflictOpen()`, 5000).then(() => true).catch(() => false);
    }
    check('caps: the same building changed outside and here: the choice is asked', dialog);
    if (dialog) {
        await sleep(200);
        await b.shot(join(SHOTS, 'caps_conflict.png'));
        const copies0 = readdirSync(DATA).filter(f => f.startsWith('tree_design.backup-')).length;
        await clickText('.cx-dialog button', 'Оставить мои');
        await savedOk();
        const desc = fileNode('Трюм').description;
        const copies = readdirSync(DATA).filter(f => f.startsWith('tree_design.backup-')).sort();
        const kept = copies.length > copies0 && /ИЗВНЕ/.test(readFileSync(join(DATA, copies[copies.length - 1]), 'utf-8'));
        check('caps: «Оставить мои»: the file has the author\'s text, the outside one is kept whole in a copy', / мои\d$/.test(desc) && !/ИЗВНЕ/.test(desc) && kept, {desc: desc.slice(-30), kept});
    }
}
console.log(`checks: ${results.length}, failed: ${failed}`);
console.log(failed ? `failed: ${failed}` : 'failed: 0');
process.exit(failed ? 1 : 0);
