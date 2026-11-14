// The page's mode «Как в игре» walked as its author uses it: node --experimental-websocket tools/tests/ingame_walk.mjs
// Its own server (tools/web_serve.py --port 8767, a copy of web/data/tree_design.json in the temp folder: the author's file is only read).
// Checks:
//   - the mode opens from its button with only the game's screen (no 3D, no overview, the bar a plate outside the frame);
//   - at windows of 1280 x 800, 1920 x 1080 and 2560 x 1440 and device pixel ratios 1, 1.25 and 1.5, for each screen of the game (1920 x 1080,
//     2560 x 1440, 3840 x 2160, this monitor) at «1:1» and «Вписать», a slot measures 74 x s x shown pixels of the device, s the interface's scale
//     (web/js/ingame.js, uiScale), and the frame is the screen's size;
//   - at each of the three screens, on both tabs of the panel: every text shown is whole (nothing cut, its box inside its parent and inside the
//     screen), in the game's size or larger (body_10, 13 units, the smallest the game uses), and the panel's controls do not overlap;
//   - the tree: every slot is reached by the wheel alone, the wheel goes up and down, a drag and the scroll bar's handle move it, «Всё дерево» shows
//     all of it and a click on a slot there only comes back to the game's size; every slot's building window lies inside the screen, clear of its slot;
//   - the whole tree built from a reset by clicks on the slots (a click orders, a click on one under construction cancels it with the gold back),
//     with the turns ended; a built slot shows the game's demolish button, which takes it down; one others stand on has it inactive;
//   - the five crew places: each choice opens inside the screen, a unit's panel by a card inside it, a hire; the state, the tab and the crews
//     survive F5; the full screen hides the plate at 1:1; the game's state is the one of «Игра»; no error in the console.
// Pictures in build/web/shots/ingame/ and build/web/shots/redesign/. Exit 1 on a failure.
import {readFileSync, writeFileSync, mkdirSync, rmSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {tmpdir} from 'node:os';
import {launch, startServer, sleep, debugRect} from './cdp.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const OUT = join(ROOT, 'build/web/shots/ingame'), RED = join(ROOT, 'build/web/shots/redesign'), FIX = join(ROOT, 'build/web/shots/fix');
mkdirSync(OUT, {recursive: true});
mkdirSync(FIX, {recursive: true});
mkdirSync(RED, {recursive: true});
const DATA = join(tmpdir(), 'mtb_ingame_walk');
rmSync(DATA, {recursive: true, force: true});
mkdirSync(DATA, {recursive: true});
const FILE = join(DATA, 'tree_design.json');
writeFileSync(FILE, readFileSync(join(ROOT, 'web/data/tree_design.json')));
// the page's own server: the port checked free first, stopped with its process tree in the finally below (cdp.mjs startServer)
const server = await startServer({root: ROOT, port: 8767, tree: FILE});
const URL0 = server.url, PORT = server.port;
let failed = 0;
const check = (name, ok, extra = '') => { if (!ok) failed++; console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok || !extra ? '' : '  ' + (typeof extra === 'string' ? extra : JSON.stringify(extra).slice(0, 1500)))); return ok; };
// the rule of web/js/ingame.js written again: the test does not take the page's own numbers for the expected ones
const uiScale = (w, h, u) => Math.min(h < 1440 ? Math.min(u, 1) : u, w / 1600, h / 900);

const b = await launch({width: 1920, height: 1080, port: 9396, profile: join(tmpdir(), 'mtb_ingame_profile')}).catch(async e => { await server.stop(); throw e; });
// a window of W x H pixels of the device at the ratio d: the CSS size is W / d, the monitor (screen) the same size
const win = async (W, H, d) => {
    await b.send('Emulation.setDeviceMetricsOverride', {width: Math.round(W / d), height: Math.round(H / d), deviceScaleFactor: d, mobile: false, screenWidth: Math.round(W / d), screenHeight: Math.round(H / d)});
    await sleep(350);
};
const grab = async () => (await b.send('Page.captureScreenshot', {format: 'png'})).data;
const shot = (name, dir = OUT, clip) => b.shot(join(dir, name), clip);
// the page up and its screen shown whole (gameui.js whenPictures: the screen is shown once its pictures are in)
const ready = () => b.until('!!(window.mtb && mtb.M && mtb.panel && mtb.root && mtb.root.pictures)', 15000);
const set = async o => { await b.eval(`mtb.ig.set(${JSON.stringify(o)}); 1`); await sleep(250); await ready(); };
const frameRect = () => b.rect('#ig_screen');
// a component of the game's screen shown now, by its id
const comp = id => b.eval(`(() => { const e = [...document.querySelectorAll('#ig_screen [data-id="${id}"]')].find(x => x.offsetParent !== null && getComputedStyle(x).visibility !== 'hidden'); if (!e) return null; const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, l: r.left, t: r.top, w: r.width, h: r.height}; })()`);
const clickId = async id => { const r = await comp(id); if (!r) throw new Error('not on the screen: ' + id); await b.click(r.x, r.y); await sleep(200); return r; };
const tab = async t => { if (await b.eval('mtb.panel.view.tab') !== t) await clickId('mtb_tab_' + t); };
// every window that pops up and is shown now, and whether each lies whole in the frame of the game's screen
const popups = () => b.eval(`(() => {
    const f = document.querySelector('#ig_screen').getBoundingClientRect();
    const shown = e => { for (let x = e; x && x !== document.body; x = x.parentElement) { const s = getComputedStyle(x); if (s.display === 'none' || s.visibility === 'hidden') return false; } return true; };
    return [...document.querySelectorAll('#ig_screen .root .tooltip_frame, #ig_screen .root .unit_parchment, #ig_screen .root .layer_click, #ig_screen .root .layer_hover, #ig_screen .root > .tooltip')]
        .filter(e => shown(e) && e.getBoundingClientRect().width > 2)
        .map(e => { const r = e.getBoundingClientRect(); return {id: e.dataset.id || e.className, inside: r.left >= f.left - 1 && r.top >= f.top - 1 && r.right <= f.right + 1 && r.bottom <= f.bottom + 1,
                    r: [Math.round(r.left - f.left), Math.round(r.top - f.top), Math.round(r.right - f.left), Math.round(r.bottom - f.top)]}; });
})()`);
// a slot by index brought whole into the tree's window (the page's own «show», as a scroll would), its centre on the screen
const slotAt = i => b.eval(`(() => { const v = mtb.panel.view.tree[${i}]; mtb.panel.view.pan.show(v); const r = v.button.el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, l: r.left, t: r.top, r: r.right, b: r.bottom, name: v.node.name, key: v.node.key}; })()`);
const status = key => b.eval(`mtb.M.status('${key}').state`);

// Every text of the game's screen that is shown: cut or not, inside its parent and the screen, its size in the interface's units; and the panel's
// controls (the title row, the foot row) that overlap. In the units of the interface: the root's scale taken out.
const audit = () => b.eval(`(() => {
    const root = document.querySelector('#ig_screen .root'), R = root.getBoundingClientRect(), k = R.width / mtb.root.Width();
    const shown = e => { for (let x = e; x && x !== root.parentElement; x = x.parentElement) { const s = getComputedStyle(x); if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return false; } return true; };
    const range = e => { const r = document.createRange(); r.selectNodeContents(e); return r.getBoundingClientRect(); };
    const texts = [...root.querySelectorAll('.t')].filter(t => t.textContent.trim() && shown(t) && t.getBoundingClientRect().width > 0);
    const bad = [];
    for (const t of texts) {
        const c = t.parentElement, id = c.dataset.id, size = parseFloat(getComputedStyle(t).fontSize);
        const tr = range(t), box = t.getBoundingClientRect();
        const cut = t.scrollWidth > t.clientWidth + 1 || t.scrollHeight > t.clientHeight + 1 || tr.left < box.left - 1 || tr.right > box.right + 1 || tr.top < box.top - 2 || tr.bottom > box.bottom + 2;
        const outside = tr.left < R.left - 1 || tr.right > R.right + 1 || tr.top < R.top - 1 || tr.bottom > R.bottom + 1;
        // a text inside a scrolled window may be cut by its edge (a slot half in sight): that is the window, not the text
        const scrolled = !!c.closest('[data-id="tree_window"]');
        if ((cut || outside) && !scrolled || size < 13 - 0.01) bad.push({id, text: t.textContent.slice(0, 40), cut, outside, size});
    }
    const ctl = ['gold_icon', 'gold', 'title', 'mtb_tab_ship', 'mtb_tab_tree', 'mtb_ship_close', 'message', 'mtb_tree_fit']
        .map(id => [...root.querySelectorAll('[data-id="' + id + '"]')].find(shown)).filter(Boolean)
        .map(e => { const t = e.querySelector(':scope > .t'); const r = t && e.dataset.id !== 'mtb_tab_ship' && e.dataset.id !== 'mtb_tab_tree' && e.dataset.id !== 'mtb_tree_fit' ? range(t) : e.getBoundingClientRect(); return {id: e.dataset.id, r, empty: t && !t.textContent.trim()}; })
        .filter(x => !x.empty && x.r.width > 0);
    const overlap = [];
    for (let i = 0; i < ctl.length; i++) for (let j = i + 1; j < ctl.length; j++) {
        const a = ctl[i].r, c = ctl[j].r;
        if (a.left < c.right - 1 && c.left < a.right - 1 && a.top < c.bottom - 1 && c.top < a.bottom - 1) overlap.push([ctl[i].id, ctl[j].id]);
    }
    return {texts: texts.length, bad, overlap, min: Math.min(...texts.map(t => parseFloat(getComputedStyle(t).fontSize)))};
})()`);

// The title row measured as drawn (the rule of web/js/panel.js, titlePlate, written again here): the plate panel_title_large.png is 769 x 69, seen
// 84..685 across and 10..56 down, its dark field 211..558 across and 15..49 down. The title's ink (canvas measureText of the text in its computed
// font, placed on the line the browser laid out: the range's top is the font's ascent above the baseline) inside the field with at least 1 unit
// clear and centred on it within 1 unit, both ways; the treasury, the tabs, the «!» mark and the cross clear of the plate as seen. In the units of
// the interface. sel: the component holding the plate (the panel's frame, or a test holder).
const titleAudit = (sel = null) => b.eval(`(() => {
    const host = ${sel ? `document.querySelector(${JSON.stringify(sel)})` : 'mtb.root.el'}, k = mtb.root.el.getBoundingClientRect().width / mtb.root.Width();
    const q = id => [...host.querySelectorAll('[data-id="' + id + '"]')].find(e => e.offsetParent !== null);
    const pe = q('title_back'), te = q('title') && q('title').querySelector('.t');
    if (!pe || !te) return {missing: true};
    const P = pe.getBoundingClientRect(), kx = P.width / 769, ky = P.height / 69;
    const field = {l: P.left + 211 * kx, r: P.left + 558 * kx, t: P.top + 15 * ky, b: P.top + 49 * ky};
    const seen = {l: P.left + 84 * kx, r: P.left + 685 * kx, t: P.top + 10 * ky, b: P.top + 56 * ky};
    const cs = getComputedStyle(te), c = document.createElement('canvas').getContext('2d');
    c.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
    c.letterSpacing = cs.letterSpacing === 'normal' ? '0px' : cs.letterSpacing;
    const m = c.measureText(te.textContent), rg = document.createRange();
    rg.selectNodeContents(te);
    const R = rg.getBoundingClientRect(), base = R.top + m.fontBoundingBoxAscent * k;
    const ink = {l: R.left - m.actualBoundingBoxLeft * k, r: R.left + m.actualBoundingBoxRight * k, t: base - m.actualBoundingBoxAscent * k, b: base + m.actualBoundingBoxDescent * k};
    const u = x => +(x / k).toFixed(2);
    const out = {size: parseFloat(cs.fontSize), line: u(R.height) - (m.fontBoundingBoxAscent + m.fontBoundingBoxDescent),
        clear: [u(ink.l - field.l), u(field.r - ink.r), u(ink.t - field.t), u(field.b - ink.b)],
        off: [u((ink.l + ink.r) / 2 - (field.l + field.r) / 2), u((ink.t + ink.b) / 2 - (field.t + field.b) / 2)], hits: []};
    if (!${!!sel}) for (const id of ['gold_icon', 'gold', 'mtb_tab_ship', 'mtb_tab_tree', 'new_mark', 'mtb_ship_close']) {
        const e = q(id); if (!e) continue;
        const t = e.querySelector(':scope > .t'), r = id === 'gold' && t ? (() => { const x = document.createRange(); x.selectNodeContents(t); return x.getBoundingClientRect(); })() : e.getBoundingClientRect();
        if (r.width && r.left < seen.r && seen.l < r.right && r.top < seen.b && seen.t < r.bottom) out.hits.push(id);
    }
    out.ok = Math.abs(out.line) < 1 && out.clear.every(x => x >= 1) && out.off.every(x => Math.abs(x) <= 1) && !out.hits.length;
    return out;
})()`);
// every window, ratio, screen and fit, both modes and both tabs; a 7-digit treasury and the tab's «!» shown
async function titleRow() {
    if (!(await b.eval('location.protocol').catch(() => '')).startsWith('http')) { await b.open(URL0 + '?mode=ingame'); await ready(); }
    const kept = await b.eval('JSON.stringify(Object.entries(localStorage))');      // the game as the walk left it, back after these checks
    const bad = [];
    let cases = 0;
    const both = async label => {
        for (const t of ['ship', 'tree']) {
            // the tab by a real click where it is on the window; at 1:1 on a screen larger than the window, by the click's handler (the same path)
            const r = await b.eval(`(() => { const r = mtb.panel.view.tabs['${t}'].button.el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, on: r.right <= innerWidth && r.bottom <= innerHeight && r.left >= 0 && r.top >= 0}; })()`);
            if (await b.eval('mtb.panel.view.tab') !== t) { if (r.on) await b.click(r.x, r.y); else await b.eval(`mtb.panel.click(mtb.panel.view.tabs['${t}'].button); 1`); await sleep(150); }
            if (await b.eval('mtb.panel.view.tab') !== t) bad.push({label, t, tab: 'not switched'});
            await b.eval(`mtb.game.gold = 1234567; mtb.panel.refresh(); mtb.panel.view.tabMark.SetVisible(true); 1`);
            await sleep(120);
            const a = await titleAudit();
            cases++;
            if (!a.ok) bad.push({label, t, ...a});
        }
    };
    for (const [W, H] of [[1280, 800], [1920, 1080], [2560, 1440]]) for (const d of [1, 0.67, 1.5]) {
        await win(W, H, d);
        await b.open(URL0 + '?mode=ingame'); await ready(); await sleep(300);
        for (const res of ['1920x1080', '2560x1440', '3840x2160', 'mine']) for (const ui of [1, 1.6, 2]) for (const show of ['one', 'fit']) {
            await set({res, ui, show});
            await both(`«Как в игре» ${W}x${H} DPR ${d} ${res} UI ${ui} ${show}`);
        }
        await b.open(URL0 + '?mode=game'); await ready(); await sleep(400);
        await both(`«Игра» ${W}x${H} DPR ${d}`);
    }
    check(`the title row: «Дух Грунгни» inside the plate's dark field (1 unit clear at least) and centred on it within 1 unit both ways; the treasury, the tabs, the «!» and the cross clear of the plate (${cases} cases: «Игра» and «Как в игре», both tabs, windows 1280x800..2560x1440, DPR 1, 0.67, 1.5, every screen, UI 1 / 1.6 / 2, 1:1 and fitted)`, !bad.length, bad.slice(0, 4));
    // less room than the plate's size: the plate and its text shrink together, the rule still holds
    const narrow = [];
    for (const half of [300, 200, 120, 60]) {
        await b.eval(`(async () => { const {titlePlate} = await import('/js/panel.js'); document.querySelector('[data-id="mtb_title_test"]')?.remove();
            const box = mtb.panel.view.frame.CreateComponent('mtb_title_test', 'holder'); box.Resize(800, 80); box.SetDockOffset(0, 120); titlePlate(box, 400, 33, ${half}, '«Дух Грунгни»'); return 1; })()`);
        const a = await titleAudit('[data-id="mtb_title_test"]');
        if (!a.ok) narrow.push({half, ...a});
    }
    await b.eval(`document.querySelector('[data-id="mtb_title_test"]')?.remove(); 1`);
    check('the title plate in less room (300, 200, 120, 60 units each side): plate and text shrink as one, the text inside the dark field and centred', !narrow.length, narrow);
    // the crew tags clear of the drawing's brass edge (4 units into the sheet) by 3 units more: the nests' tag is drawn at the sheet's very top
    const tags = await b.eval(`Object.entries(mtb.panel.view.crewAreas).map(([g, c]) => { const t = c.tags.plus, a = c.area, s = mtb.panel.view.sheet;
        return {g, l: a.x + t.x, t: a.y + t.y, r: s.Width() - (a.x + t.x + t.Width()), b: s.Height() - (a.y + t.y + t.Height())}; })`);
    check('every crew tag 7 units or more inside the drawing (clear of its brass edge, the nests\' tag no longer on the line)', tags.length && tags.every(x => Math.min(x.l, x.t, x.r, x.b) >= 7 - 0.5), tags);
    await win(1920, 1080, 1);
    await b.open(URL0 + '?mode=ingame'); await ready();
    await b.eval(`localStorage.clear(); for (const [k, v] of ${kept}) localStorage.setItem(k, v); 1`);
    await b.reload(); await ready(); await sleep(500);
}

// TITLE_ONLY=1: only the title row's checks (titleRow below)
if (process.env.TITLE_ONLY) {
    try { await titleRow(); } catch (err) { check('the walk (title)', false, {err: err.message, stack: err.stack && err.stack.split('\n').slice(0, 3).join(' | ')}); } finally { try { await b.close(); } finally { await server.stop(); } }
    console.log(failed ? `failed: ${failed}` : 'failed: 0');
    process.exit(failed ? 1 : 0);
}
// FIX2_ONLY=1: only the checks of the second QA pass (fix2 below), for a quick walk
if (process.env.FIX2_ONLY) {
    try { await fix2(); } catch (err) { check('the walk (fix2)', false, {err: err.message, stack: err.stack && err.stack.split('\n').slice(0, 3).join(' | ')}); } finally { try { await b.close(); } finally { await server.stop(); } }
    console.log(failed ? `failed: ${failed}` : 'failed: 0');
    process.exit(failed ? 1 : 0);
}
try {
    // ---- the mode opens from its button; the page as it is left in «Игра» ----
    await win(1920, 1080, 1);
    await b.open(URL0 + '?mode=game');
    await ready();
    await b.eval('localStorage.clear()');
    await b.reload();
    await ready();
    await sleep(500);
    const btn = await b.rect('#mode button[data-mode="ingame"]');
    await b.click(btn.x, btn.y);
    await sleep(600);
    const look = await b.eval(`({mode: document.body.dataset.mode, right: !!document.getElementById('right').offsetParent, overview: !!document.getElementById('overview').offsetParent,
        frame: !!document.querySelector('#ig_screen .root'), bar: document.getElementById('bar').getBoundingClientRect().bottom, top: document.getElementById('ig_screen').getBoundingClientRect().top,
        log: !!document.getElementById('log').offsetParent, saved: localStorage.getItem('mtb_mode'), tools: [...document.querySelectorAll('#ig_tools button, #ig_tools select')].map(e => e.id)})`);
    check('«Как в игре» opens from its button: the frame of the screen, no 3D, no overview, the plate above the frame', look.mode === 'ingame' && !look.right && !look.overview && look.frame && look.top >= look.bar && !look.log && look.saved === 'ingame', look);
    check('the plate has no switch of the old sketches or of a smaller font', !look.tools.includes('ig_font') && !look.tools.includes('ig_layout') && look.tools.includes('ig_ruler') && look.tools.includes('ig_report_btn'), look.tools);
    check('the panel opens on «Постройки» at what can be done now: the first building whole in sight', await b.eval(`(() => { const v = mtb.panel.view, w = v.pan.win.el.getBoundingClientRect(); const t = v.tree.find(x => mtb.M.status(x.node.key).state === 'open'); const r = t.button.el.getBoundingClientRect(); return v.tab === 'tree' && r.left >= w.left && r.right <= w.right && r.top >= w.top && r.bottom <= w.bottom; })()`));

    {   // ======== the fixes after the QA pass: each defect a check, played with real input at 2560 x 1440, UI 1.6, 1:1; a picture each in shots/fix ========
    await win(2560, 1480, 1);
    await b.open(URL0 + '?mode=ingame'); await ready(); await sleep(500);      // a reload stays in this mode
    await set({res: '2560x1440', ui: 1.6, show: 'one'});
    await b.move(2, 2); await sleep(300);
    const screenClip = () => b.eval(`(() => { const r = document.querySelector('#ig_screen').getBoundingClientRect(); return {x: r.left, y: r.top, width: r.width, height: r.height}; })()`);
    const fixShot = async name => shot(name, FIX, await screenClip());
    const footer = () => b.eval('mtb.panel.view.message.GetStateText()');
    const slotByName = name => b.eval(`(() => { const v = mtb.panel.view.tree.find(t => t.node.name === ${JSON.stringify(name)}); mtb.panel.view.pan.show(v); const r = v.button.el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, l: r.left, t: r.top, w: r.width, h: r.height, key: v.node.key}; })()`);
    const endTurn = async () => { const e = await b.rect('#end_turn'); await b.click(e.x, e.y); await sleep(250); };
    // the treasury set by the page's debug field (saved with the game, as a player's would be)
    const goldTo = async v => { await b.eval(`document.getElementById('gold_value').value = ${v}; document.getElementById('gold_set').click(); 1`); await sleep(120); };
    const shown = id => b.eval(`(() => { const e = [...document.querySelectorAll('#ig_screen [data-id="${id}"]')].find(x => x.offsetParent !== null && getComputedStyle(x).visibility !== 'hidden'); return !!e; })()`);
    // A3: the first step of a fresh campaign
    check('A3: a fresh campaign: the foot line gives the one first step in the game\'s voice', await footer() === 'Закажите первую постройку — «Заготовка под корабль».', await footer());
    await fixShot('A3_first_step.png');
    // A1: the ship beside the tree
    const col = await b.eval(`(() => { const v = mtb.panel.view, m = v.column.sheet.el.getBoundingClientRect(), w = v.pan.win.el.getBoundingClientRect(), bar = v.pan.vbar ? v.pan.vbar.handle.el.parentElement && document.querySelector('#ig_screen [data-id="tree_bar_track_vertical"]').getBoundingClientRect() : null;
        return {mini: v.column.sheet.Width(), shown: v.column.sheet.el.offsetParent !== null, across: v.pan.cw <= v.pan.w && !v.pan.hbar, clear: m.left >= w.right && (!bar || m.left >= bar.right), inPanel: m.right <= document.querySelector('#ig_screen [data-id="frame"]').getBoundingClientRect().right}; })()`);
    check('A1: «Постройки» shows the ship beside the tree (about 300 units wide), the tree\'s whole width without scrolling across, nothing over another', col.shown && col.mini >= 260 && col.mini <= 320 && col.across && col.clear && col.inPanel, col);
    // the small drawing is the big one's layers at the same stages, at every point of a campaign (here: fresh; later: with parts under construction and built)
    const sameStages = () => b.eval(`(() => { const v = mtb.panel.view, out = [];
        for (const [part, l] of Object.entries(v.layers)) for (const s of ['pencil', 'build', 'ink']) if (l[s] && v.column.layers[part] && v.column.layers[part][s] && (l[s].Visible() !== v.column.layers[part][s].Visible())) out.push(part + ':' + s);
        if (v.sheet.path !== v.column.sheet.path) out.push('sheet ' + v.sheet.path + ' vs ' + v.column.sheet.path);
        for (const [g, set] of Object.entries(v.column.crew)) { const c = v.crewAreas[g]; if (!c) continue; for (const [k, layer] of Object.entries(set.layers)) if (c.layers[k] && layer.Visible() !== (c.layers[k].Visible() && c.area.Visible())) out.push(g + ':' + k); }
        return out; })()`);
    check('A1: the small ship is live: every layer at the same stage as on «Корабль» (fresh campaign)', !(await sameStages()).length, await sameStages());
    // order the first hull: on the small ship its timber in hatching with the turns, as on the big one
    let s0 = await slotByName('Заготовка под корабль');
    await b.click(s0.x, s0.y); await sleep(150);
    await endTurn();
    s0 = await slotByName('Прочный корпус');
    await b.click(s0.x, s0.y); await sleep(150);
    check('A1: a hull under construction: the small ship\'s layers at the big one\'s stages', !(await sameStages()).length, await sameStages());
    await b.move(2, 2);
    await fixShot('A1_ship_on_tree_building.png');
    for (let i = 0; i < 3 && (await status(s0.key)) !== 'built'; i++) await endTurn();
    await b.move(2, 2); await sleep(200);
    check('A1: the barge built: the small ship shows it at once', !(await sameStages()).length && await b.eval(`mtb.panel.view.column.sheet.path.endsWith('blueprint_base.png')`), await sameStages());
    // A2: a building that opens a crew place, built by a turn
    const nest = await slotByName('Вороньи гнёзда');
    await b.click(nest.x, nest.y); await sleep(150);
    await endTurn();
    await b.move(2, 2); await sleep(250);
    const a2 = await b.eval(`(() => { const v = mtb.panel.view, rings = v.column.layers.rings && v.column.layers.rings.ink;
        return {msg: v.message.GetStateText(), mark: v.tabMark.Visible() && v.tabMark.el.offsetParent !== null, glow: v.tabGlow.Visible(), ringsGlow: !!(rings && /drop-shadow/.test(rings.el.style.filter)),
                row: /drop-shadow/.test(v.column.rows.cupolas.card.el.style.filter), rowText: v.column.rows.cupolas.state.GetStateText(), others: Object.entries(v.column.rows).filter(([g]) => g !== 'cupolas').some(([, r]) => /drop-shadow/.test(r.card.el.style.filter))}; })()`);
    check('A2: the nests built by the turn: the foot line names what opened, «Корабль» has the game\'s mark, the new rings glow on the small ship, the nests\' place glows in the crew list',
        a2.msg === 'Построено: «Вороньи гнёзда». Открыто место экипажа «Гнёзда».' && a2.mark && a2.glow && a2.ringsGlow && a2.row && !a2.others, a2);
    await fixShot('A2_new_on_ship.png');
    await shot('A1_ship_on_tree.png', FIX, await screenClip());
    await shot('tree_tab_full.png', FIX, await screenClip());
    await b.reload(); await ready(); await sleep(600);
    check('A2: F5 keeps the mark of «Корабль» and the glow of the turn', await b.eval('mtb.panel.view.tabMark.Visible() && mtb.M.ship_news() !== null'));
    // a click on the small ship opens «Корабль»; the mark goes; the new part glows there too
    const mini = await comp('mtb_mini_ship');
    await b.click(mini.x, mini.y); await sleep(300);
    check('A1/A2: a click on the small ship opens «Корабль»; looked at, the mark is gone', await b.eval(`mtb.panel.view.tab === 'ship' && !mtb.M.ship_unseen()`));
    await b.move(2, 2); await sleep(200);
    await fixShot('ship_tab_full.png');
    await tab('tree'); await b.move(2, 2); await sleep(200);
    check('A2: back on «Постройки» the tab has no mark', !(await b.eval('mtb.panel.view.tabMark.Visible()')));
    // a crew place in the list opens its choice on «Корабль»
    const row = await comp('mtb_mini_crew_cupolas');
    await b.click(row.x, row.y); await sleep(300);
    check('A1: a click on an open crew place beside the tree: «Корабль» with that place\'s choice open', await b.eval(`mtb.panel.view.tab === 'ship' && mtb.panel.view.crewAreas.cupolas.open`));
    // B14: Escape closes the choice; a click outside a choice only closes it
    await b.key('Escape'); await sleep(200);
    check('B14: Escape closes the open crew choice', !(await b.eval('Object.values(mtb.panel.view.crewAreas).some(c => c.open)')));
    await clickId('mtb_crew_area_cupolas');
    const tabT = await comp('mtb_tab_tree');
    await b.click(tabT.x, tabT.y); await sleep(250);
    check('B14: with a choice open, a click on another control only closes the choice (the tab stays)', await b.eval(`mtb.panel.view.tab === 'ship' && !Object.values(mtb.panel.view.crewAreas).some(c => c.open)`));
    await clickId('mtb_crew_area_cupolas');
    await fixShot('B14_choice_open.png');
    const side = await comp('mtb_side_right');
    if (side) { await b.click(side.x, side.y); await sleep(200); }
    check('B14: a click on Malakai\'s other side while a choice is open: the choice closes, the side stays', await b.eval(`mtb.M.malakai_side() === 'left' && !Object.values(mtb.panel.view.crewAreas).some(c => c.open)`));
    await tab('tree');
    // B12: a click on a locked slot
    await goldTo(100000);
    const locked = await slotByName('Склад оружия');
    await b.click(locked.x, locked.y); await sleep(120);
    const b12 = await b.eval(`(() => { const v = mtb.panel.view.tree.find(t => t.node.name === 'Склад оружия'); return {msg: mtb.panel.view.message.GetStateText(), reason: mtb.M.reason(v.node.key), deny: v.deny.Visible(), denied: mtb.panel.view.tree.filter(t => t.deny.Visible()).map(t => t.node.name), window: v.info.reason.GetStateText()}; })()`);
    check('B12: a click on a locked slot: the foot line says the window\'s reason, the slot flashes red', b12.msg === b12.reason && /^Требуется постройка/.test(b12.msg) && b12.deny && b12.window.includes(b12.reason), b12);
    await fixShot('B12_locked_click.png');
    await sleep(800);
    check('B12: the red flash is short', !(await b.eval(`mtb.panel.view.tree.find(t => t.node.name === 'Склад оружия').deny.Visible()`)));
    await goldTo(10);
    const poorSlot = await slotByName('Пивной чертог');
    await b.click(poorSlot.x, poorSlot.y); await sleep(120);
    check('B12: a click on a slot short of gold: the foot line says so', /^Не хватает золота: нужно \d+, в казне 10\.$/.test(await footer()), await footer());
    await goldTo(100000);
    // B1: the reason in the window: every unbuilt direct requirement, the game's words
    await b.move(locked.x, locked.y, 3); await sleep(300);
    const b1 = await b.eval(`(() => { const v = mtb.panel.view.tree.find(t => t.node.name === 'Склад оружия'); return {text: v.info.reason.el.textContent, missing: mtb.M.status(v.node.key).missing.map(k => mtb.M.level(k).name)}; })()`);
    check('B1: the window\'s reason lists the missing buildings in the game\'s words', /^Требуется постройка: /.test(b1.text) && b1.missing.every(n => b1.text.includes(n)), b1);
    await fixShot('B1_lock_reason.png');
    // B3: the cards over every slot: at most three, «+N» for the rest; the padlock and the line out of the slot clear of them
    const b3 = await b.eval(`(() => { const v = mtb.panel.view, bad = [];
        for (const t of v.tree) {
            const cards = [...v.crew.filter(c => c.v === t).map(c => c.card), ...v.plates.filter(p => p.v === t).map(p => p.plate)];
            if (cards.length > 3) bad.push(t.node.name + ': ' + cards.length + ' cards');
            const lock = {l: t.button.x + t.padlock.x, r: t.button.x + t.padlock.x + 20, t: t.button.y + 2, b: t.button.y + 27};
            const mid = t.button.x + 37;
            for (const c of cards) {
                if (c.x < lock.r && c.x + 23 > lock.l && c.y < lock.b && c.y + 50 > lock.t) bad.push(t.node.name + ': a card over the padlock');
                if (c.x <= mid + 2 && c.x + 23 >= mid - 2) bad.push(t.node.name + ': a card over the line out of the slot');
            }
        }
        const tir = v.plates.find(p => p.v.node.name === 'Тир'), pol = v.plates.find(p => p.v.node.name === 'Манекен для учебной стрельбы');
        return {bad, tir: tir && tir.folded, pol: pol && pol.folded}; })()`);
    check('B3: no slot has more than three in its row; the padlock and the line out of a slot are never under a card; «Манекен» (more than three new units) folds the rest into «+N»; «Тир» (three units once each, one card a unit) needs no plate', !b3.bad.length && !b3.tir && b3.pol > 0, b3);
    const dupes = await b.eval(`(() => { const seen = {}, out = []; for (const c of mtb.panel.view.crew) { const k = c.v.node.row.chain + '|' + (c.army || c.group + ':' + c.option); if (seen[k] && seen[k] !== c.v.node.name) out.push(c.v.node.name + ' / ' + seen[k] + ': ' + k); seen[k] ||= c.v.node.name; } return out; })()`);
    check('B3: no unit card on two levels of the same line (a level shows only what it brings new, as the game\x27s tree)', !dupes.length, dupes);
    const tirS = await slotByName('Тир');
    await shot('B3_cards_tir.png', FIX, {x: tirS.l - 200, y: tirS.t - 160, width: 560, height: 360});
    const polS = await slotByName('Манекен для учебной стрельбы');
    await shot('B3_cards_dummies.png', FIX, {x: polS.l - 200, y: polS.t - 160, width: 560, height: 360});
    const more = await comp('mtb_cards_more_crew_weapons_1');
    await b.move(more.x, more.y, 3); await sleep(300);
    const moreTip = await b.eval(`document.querySelector('#ig_screen .root > .tooltip').textContent`);
    check('B3: the «+N» plate names the folded units on hover', moreTip.split(/\s*\n\s*|(?<=[а-я)])(?=[А-Я])/).length >= 2 && /Громобои|Егеря|Забияки/.test(moreTip), moreTip);
    // B4: the links of the slot under the mouse lit, the rest dimmed; back on leave; crossings broken, junctions dotted
    const hall = await slotByName('Столовая');
    await b.move(2, 2); await sleep(150);
    await b.move(hall.x, hall.y, 3); await sleep(300);
    const b4 = await b.eval(`(() => { const v = mtb.panel.view, key = v.hoverSlot && v.hoverSlot.node.key, segs = v.links.filter(l => l.to === key || l.from === key).reduce((n, l) => n + l.segs.length, 0);
        const lit = v.litPool.filter(s => s.Visible()).length, ins = v.tree.filter(t => t.markIn.Visible()).map(t => t.node.name), outs = v.tree.filter(t => t.markOut.Visible()).map(t => t.node.name);
        return {key, segs, lit, dim: parseFloat(v.linesHolder.el.style.opacity), ins, outs, crossings: v.crossings.length, junctions: v.junctions.length}; })()`);
    check('B4: hover on a slot: its links lit (into it gold, out of it green), its prerequisite and unlocked slots ringed, the other lines dimmed', b4.key && b4.lit === b4.segs && b4.dim < 0.5 && b4.ins.includes('Пивной чертог') && b4.ins.includes('Трюм') && b4.outs.length > 0, b4);
    check('B4: the tree\'s lines: crossings broken round the crossing line, joins dotted', b4.crossings > 0 && b4.junctions > 0, b4);
    await fixShot('B4_links_hover.png');
    await b.move(2, 2); await sleep(200);
    check('B4: the mouse away: every line as it was', await b.eval(`(mtb.panel.view.linesHolder.el.style.opacity === '1' || mtb.panel.view.linesHolder.el.style.opacity === '') && !mtb.panel.view.litPool.some(s => s.Visible())`));
    // B7-9, B10: every building window: one format, a clean layout, under the title row; in both zoom states
    const infoAudit = () => b.eval(`(() => { const v = mtb.panel.view, f = v.frame, out = [];
        const tip = v.tree.find(t => t.info.tip.el.style.display !== 'none' && t.info.tip.el.offsetParent !== null);
        if (!tip) return {none: true};
        const t = tip.info, top = f.y + t.tip.y, head = f.y + v.area.y;
        if (top < head - 0.5 && t.h <= mtb.root.Height() - 4 - head) out.push('over the title row though it fits under it: ' + top + ' < ' + head);      // a taller one goes over it, whole
        const d = t.description;
        if (d.Visible() && (d.x < 22 || d.x + d.Width() > t.w - 22)) out.push('description by the edge');
        const rows = [...t.effects.map(r => [r.icon, r.text, 24]), [t.opensIcon, t.opensTitle, 24], [t.armyIcon, t.armyTitle, 24], ...t.units.map(r => [r.holder, r.name, 26]), ...t.army.map(r => [r.holder, r.name, 26])].filter(([i, x]) => i.Visible() && x.Visible());
        for (const [i, x, h] of rows) if (Math.abs((i.y + h / 2) - (x.y + 11)) > 1.5) out.push('icon off its line: ' + x.GetStateText().slice(0, 20));
        const steps = rows.map(([, x]) => x.y).sort((a, b) => a - b).map((y, k, a) => k ? y - a[k - 1] : null).filter(Boolean);
        const singles = rows.filter(([, x]) => x.Height() <= 22).map(([, x]) => x.y);
        const rhythm = [...new Set(steps.filter((s, k) => singles.includes(rows.map(([, x]) => x.y).sort((a, b) => a - b)[k])))];
        if (rhythm.some(s => s !== 32)) out.push('uneven rhythm ' + rhythm.join(','));
        const text = t.tip.el.textContent;
        if (/\\d %|\\d\\.\\d/.test(text)) out.push('number format: ' + (text.match(/.{12}(\\d %|\\d\\.\\d).{4}/) || [''])[0]);
        if (document.querySelector('#ig_screen .tooltip_instruction[data-id^="building_information"]')) out.push('a second window for the reason');
        return {name: tip.node.name, out}; })()`);
    const infoBad = [];
    const total = await b.eval('mtb.panel.view.tree.length');
    for (const z of ['near', 'all']) {
        if (z === 'all') { await clickId('mtb_tree_fit'); await sleep(250); }
        for (let i = 0; i < total; i++) {
            await b.move(2, 2);
            const p = z === 'near' ? await slotAt(i) : await b.eval(`(() => { const r = mtb.panel.view.tree[${i}].button.el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()`);
            await b.move(p.x, p.y, 2); await sleep(90);
            const a = await infoAudit();
            if (a.none || a.out.length) infoBad.push({z, i, ...a});
            if (z === 'near' && i === 14) await fixShot('B7_info_window.png');
            if (z === 'all' && i === 14) await fixShot('B10_popup_overview.png');
        }
    }
    check(`B7-9, B10: every building window (${total} x 2 zoom states): under the title row, the description clear of the frame, icons on their text line, an even rhythm, the game's number format, one window with its reason`, !infoBad.length, infoBad.slice(0, 5));
    await clickId('mtb_tree_fit'); await sleep(200);
    // B13: the tree's place and zoom through F5; «Вблизи» goes back to where the player was
    const wc = await b.eval(`(() => { const r = mtb.panel.view.pan.win.el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()`);
    await b.move(wc.x + 300, wc.y);
    await b.mouse('mouseWheel', wc.x + 300, wc.y, {deltaX: 0, deltaY: -420}); await sleep(400);
    const placeA = await b.eval('JSON.stringify(mtb.panel.view.pan.state())');
    await b.reload(); await ready(); await sleep(600);
    check('B13: F5 keeps the tree where it was scrolled', await b.eval('JSON.stringify(mtb.panel.view.pan.state())') === placeA, {placeA, after: await b.eval('JSON.stringify(mtb.panel.view.pan.state())')});
    await clickId('mtb_tree_fit'); await sleep(250);
    await b.reload(); await ready(); await sleep(600);
    check('B13: F5 keeps «Всё дерево»', await b.eval('mtb.panel.view.pan.z < 1'));
    await clickId('mtb_tree_fit'); await sleep(250);
    check('B13: «Вблизи» goes back to where the player was before «Всё дерево»', await b.eval(`(() => { const s = mtb.panel.view.pan.state(), a = ${placeA}; return s.z === 1 && Math.abs(s.x - a.x) < 1 && Math.abs(s.y - a.y) < 1; })()`));
    await clickId('mtb_tree_fit'); await sleep(250);
    const anyOpen = await b.eval(`(() => { const v = mtb.panel.view.tree.find(t => mtb.M.status(t.node.key).state === 'open' || mtb.M.status(t.node.key).poor); const r = v.button.el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, key: v.node.key}; })()`);
    await b.click(anyOpen.x, anyOpen.y); await sleep(250);
    check('B13: a click on a slot of the whole tree goes to that slot (not back)', await b.eval(`(() => { const p = mtb.panel.view.pan, v = mtb.panel.view.tree.find(t => t.node.key === '${anyOpen.key}'), w = p.win.el.getBoundingClientRect(), r = v.button.el.getBoundingClientRect(); return p.z === 1 && r.left >= w.left && r.right <= w.right && r.top >= w.top && r.bottom <= w.bottom && !p.back; })()`));
    // B14: Escape takes the demolish button away
    await b.eval(`document.getElementById('build_to') && 1`);
    const built = await b.eval(`mtb.panel.view.tree.findIndex(v => mtb.M.status(v.node.key).state === 'built')`);
    const bs = await slotAt(built);
    await b.click(bs.x, bs.y); await sleep(200);
    const razeOn = await shown('mtb_ship_demolish');
    await b.key('Escape'); await sleep(200);
    check('B14: Escape takes the demolish button away', razeOn && !(await shown('mtb_ship_demolish')));
    // B15: the title row and the foot row: no black plates of a repeated tile; the stone without the tile's seams
    const b15 = await b.eval(`(() => { const f = document.querySelector('#ig_screen [data-id="frame"]'), g = document.querySelector('#ig_screen [data-id="panel_back"]'), p = document.querySelector('#ig_screen [data-id="work_pane"]');
        return {frameBg: getComputedStyle(f).backgroundImage, ground: getComputedStyle(g).borderImageSource, groundRepeat: getComputedStyle(g).borderImageRepeat, pane: getComputedStyle(p).backgroundImage, paneBorder: getComputedStyle(p).borderImageSource}; })()`);
    check('B15: the panel\'s ground is the game\'s tile as one piece (no row of black plates), the working area\'s stone repeated without its seams', b15.frameBg === 'none' && /panel_back_tile\.png/.test(b15.ground) && /stretch/.test(b15.groundRepeat) && b15.pane === 'none' && /panel_back_tile_stone/.test(b15.paneBorder), b15);
    await shot('B15_header.png', FIX, {...(await screenClip()), height: 200});
    // B17: the drawing: the turns on a plate, every pencil under every ink, the nests' halo whole (the beer hall ordered: the pub's turns on the drawing)
    const pubS = await slotByName('Пивной чертог');
    if (await status(pubS.key) === 'open') { await b.click(pubS.x, pubS.y); await sleep(150); }
    await tab('ship');
    const b17 = await b.eval(`(() => { const v = mtb.panel.view, holders = [...v.sheet.el.children].map(e => e.dataset.id).filter(id => /_layers$/.test(id || ''));
        const glow = v.crewAreas.cupolas && v.crewAreas.cupolas.glow.el.style.zIndex;
        const turns = Object.values(v.layers).map(l => l.turns).find(t => t && t.Visible() && t.GetStateText());
        return {holders, glow, plate: turns ? getComputedStyle(turns.el).backgroundColor : null, turns: turns && turns.GetStateText()}; })()`);
    check('B17: the drawing\'s pencils under its hatching under its ink; the turns on a plate; the nests\' halo over the sheet\'s edge', b17.holders.join() === 'pencil_layers,build_layers,ink_layers' && b17.glow === '1' && (!b17.turns || /rgba?\(246/.test(b17.plate)), b17);
    await fixShot('B17_drawing.png');
    // B11: the numbers of the crews' panels: whole volleys a place, a decimal comma
    await clickId('mtb_crew_area_cupolas');
    const nums = await b.eval(`[...document.querySelectorAll('#ig_screen [data-id^="crew_pick_info_"], #ig_screen [data-id^="crew_info_"]')].map(e => e.textContent).join(' | ')`);
    check('B11: no fraction of a volley and no decimal point in any crew\'s panel', !/\d,\d+ залп|\d\.\d/.test(nums), (nums.match(/.{30}(\d,\d+ залп|\d\.\d).{10}/) || [''])[0]);
    const thun = await comp('mtb_crew_card_pick_cupolas:axes');
    if (thun) { await b.move(thun.x, thun.y, 3); await sleep(300); await fixShot('B11_unit_numbers.png'); }
    await clickId('mtb_crew_close_cupolas');
    await tab('tree');
    // B18: the page's label never over the game's screen
    const b18 = [];
    for (const [W, H] of [[1280, 800], [1920, 1080], [2560, 1480]]) for (const show of ['fit', 'one']) {
        await win(W, H, 1);
        await set({res: '2560x1440', show});
        const r = await b.eval(`(() => { const l = document.getElementById('ig_label').getBoundingClientRect(), f = document.getElementById('ig_screen').getBoundingClientRect(); return {over: l.width > 0 && l.left < f.right && f.left < l.right && l.top < f.bottom && f.top < l.bottom, w: l.width}; })()`);
        if (r.over || !r.w) b18.push({W, H, show, ...r});
    }
    check('B18: the label of what is shown («экран игры…») is in the plate, never over the game\'s screen, at every window size', !b18.length, b18);
    await win(2560, 1480, 1);
    await set({res: '2560x1440', show: 'one'});
    await shot('B18_label.png', FIX, {x: 0, y: 0, width: 2560, height: 60});
    // B5: gold in «Как в игре» from the debug menu
    const g0 = await b.eval('mtb.game.treasury()');
    const add = await debugRect(b, '.gold_add[data-add="5000"]');
    await b.click(add.x, add.y); await sleep(200);
    check('B5: «Отладка» in «Как в игре» adds gold (+5000)', await b.eval('mtb.game.treasury()') === g0 + 5000, {g0, now: await b.eval('mtb.game.treasury()')});
    await b.move(2, 2);
    await b.eval('localStorage.clear()'); await b.reload(); await ready(); await sleep(500);
    }

    // ======== the second QA pass: each defect a check, played at 2560 x 1440, UI 1.6, 1:1 (1920 x 1080, UI 1.0 where said); pictures in shots/fix2 ========
    await fix2();

    // ---- the title row: the name on its plate in every mode, size and tab ----
    await titleRow();

    // ---- the slot's size in the device's pixels: every window, ratio, screen, at 1:1 and fitted ----
    const sizes = [];
    for (const [W, H] of [[1280, 800], [1920, 1080], [2560, 1440]]) for (const d of [1, 1.25, 1.5]) {
        await win(W, H, d);
        for (const res of ['1920x1080', '2560x1440', '3840x2160', 'mine']) for (const show of ['one', 'fit']) {
            await set({res, ui: 1.6, show});
            const m = await b.eval(`(() => { const v = mtb.panel.view, t = v.tree[0], d = devicePixelRatio, f = document.getElementById('ig_screen').getBoundingClientRect();
                return {dpr: d, slot: t.button.el.getBoundingClientRect().width * d, fw: f.width * d, fh: f.height * d, shown: mtb.ig.shown().f, sw: screen.width, sh: screen.height, fl: f.left * d, ft: f.top * d}; })()`);
            const [rw, rh] = res === 'mine' ? [Math.round(m.sw * d), Math.round(m.sh * d)] : res.split('x').map(Number);
            const s = uiScale(rw, rh, 1.6), f = show === 'one' ? 1 : Math.min(1, m.shown);
            const want = 74 * s * f;
            const ok = Math.abs(m.slot - want) <= 1 && Math.abs(m.fw - rw * f) <= 1 && Math.abs(m.fh - rh * f) <= 1 && (show !== 'one' || Math.abs(m.fl - Math.round(m.fl)) < 0.01);
            sizes.push({W, H, d, res, show, ok, slot: +m.slot.toFixed(2), want: +want.toFixed(2), f: +f.toFixed(4), frame: [Math.round(m.fw), Math.round(m.fh)]});
            if (!ok) check(`slot at ${W}x${H} DPR ${d}, ${res} ${show}`, false, sizes.at(-1));
        }
    }
    check(`a slot of 74 units is 74 x s x shown device pixels, the frame the screen's size, in all ${sizes.length} cases (windows 1280x800, 1920x1080, 2560x1440; DPR 1, 1.25, 1.5)`, sizes.every(x => x.ok));

    // ---- every text whole and in the game's size, no control over another: three screens, both tabs, an empty and a full ship ----
    await win(1920, 1080, 1);
    for (const state of ['start', 'all built']) {
        if (state === 'all built') { await b.eval(`document.getElementById('build_all').click(); 1`); await sleep(400); await b.eval(`mtb.M.order; mtb.game.gold = 123456; mtb.panel.refresh(); 1`); }
        for (const res of ['1920x1080', '2560x1440', '3840x2160']) for (const t of ['tree', 'ship']) {
            await set({res, ui: 1.6, show: 'fit'});
            await tab(t);
            await b.move(2, 2);
            await sleep(200);
            const a = await audit();
            check(`${state}, ${res}, «${t === 'tree' ? 'Постройки' : 'Корабль'}»: ${a.texts} texts whole, in the game's size (smallest ${a.min} units), no control over another`, !a.bad.length && !a.overlap.length && a.min >= 13, a);
        }
    }
    // the windows of the ship's tab, opened one by one: their texts whole too (the five choices, Malakai's side)
    await set({res: '2560x1440', ui: 1.6, show: 'fit'});
    await tab('ship');
    for (const g of ['rifles', 'cannons', 'bombs', 'cupolas', 'harpoon']) {
        await clickId('mtb_crew_area_' + g);
        await b.move(2, 2); await sleep(200);
        const a = await audit(), p = await popups();
        check(`the choice of ${g}: its texts whole and in the game's size, the window inside the screen`, !a.bad.length && p.length > 0 && p.every(x => x.inside), {a, p});
        // a unit's panel by the first card that has one
        const opt = await b.eval(`mtb.M.crew_options('${g}').filter(o => !o.empty)[0].key`);
        const card = await comp(`mtb_crew_card_pick_${g}:${opt}`);
        await b.move(card.x, card.y, 3); await sleep(300);
        const a2 = await audit(), p2 = await popups();
        check(`the choice of ${g}: the unit's panel by its card, inside the screen, its texts whole`, !a2.bad.length && p2.some(x => /unit_parchment/.test(x.id) || /crew_pick_info/.test(x.id)) && p2.every(x => x.inside), {bad: a2.bad, p2});
        if (g === 'bombs') { await shot('crew_picker.png', RED); }
        await clickId('mtb_crew_close_' + g);
    }
    const plan = await comp('plan_ship');
    await b.move(plan.x, plan.y, 4); await sleep(350);
    const pa = await audit(), pp = await popups();
    check('Malakai\'s side: the demo window whole inside the screen', !pa.bad.length && pp.every(x => x.inside), {pa, pp});

    // ---- the pictures: fitted at each screen; the ruler ----
    await b.open(URL0 + '?mode=ingame'); await ready(); await b.eval('localStorage.clear()'); await b.reload(); await ready(); await sleep(500);
    for (const [res, name, W, H] of [['1920x1080', 'full_1080.png', 1920, 1080], ['2560x1440', 'full_1440.png', 2560, 1440], ['3840x2160', 'full_2160.png', 3840, 2160]]) {
        await win(W, H + 40, 1);
        await set({res, ui: 1.6, show: 'one', ruler: false});
        await b.move(2, 2); await sleep(300);
        const f = await frameRect();
        await shot(name, RED, {x: f.l, y: f.t, width: f.w, height: f.h});
    }
    await win(1920, 1080, 1);
    await set({res: '2560x1440', show: 'fit'});
    await b.key('l');
    await sleep(500);
    const marks = await b.eval(`[...document.querySelectorAll('#ig_overlay .m b')].map(e => e.textContent)`);
    check('the ruler (L) writes the panel, the tree\'s window, a slot, a card in the game\'s pixels', marks.length >= 3 && marks.some(t => /слот 74 ед\. = 118×118 px/.test(t)) && /карточка 23×50 ед. = 36,8×80 px/.test(await b.eval(`document.querySelector('#ig_overlay .legend').textContent`)), marks);
    await shot('ruler.png');
    await b.key('l');

    // ---- the tree: the wheel reaches every slot, a drag, the bar, «Всё дерево» ----
    await win(2560, 1480, 1);
    await set({res: '2560x1440', show: 'one'});
    await tab('tree');
    const W0 = await b.eval(`(() => { const r = mtb.panel.view.pan.win.el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()`);
    const seenNow = () => b.eval(`(() => { const v = mtb.panel.view, w = v.pan.win.el.getBoundingClientRect(); return v.tree.filter(t => { const r = t.button.el.getBoundingClientRect(); return r.left >= w.left - 0.5 && r.right <= w.right + 0.5 && r.top >= w.top - 0.5 && r.bottom <= w.bottom + 0.5; }).map(t => t.node.key); })()`);
    const reached = new Set(await seenNow());
    const y0 = await b.eval('mtb.panel.view.pan.y');
    await b.mouse('mouseWheel', W0.x, W0.y, {deltaX: 0, deltaY: -100}); await sleep(120);
    const y1 = await b.eval('mtb.panel.view.pan.y');
    check('the wheel scrolls the tree up and down (100 of the wheel up: the tree moves down 100 units)', Math.abs(y1 - y0 - 100) < 1, {y0, y1});
    for (let i = 0; i < 40; i++) { await b.mouse('mouseWheel', W0.x, W0.y, {deltaX: 0, deltaY: -150}); await sleep(40); for (const k of await seenNow()) reached.add(k); }
    const top = await b.eval('mtb.panel.view.pan.y');
    for (let i = 0; i < 40; i++) { await b.mouse('mouseWheel', W0.x, W0.y, {deltaX: 0, deltaY: 150}); await sleep(40); for (const k of await seenNow()) reached.add(k); }
    const total = await b.eval('mtb.panel.view.tree.length');
    check(`the wheel alone reaches every slot of the tree whole in its window (${reached.size} of ${total})`, reached.size === total, {reached: reached.size, total});
    check('the tree goes across without scrolling: its whole width is in the window', await b.eval('mtb.panel.view.pan.cw <= mtb.panel.view.pan.w && !mtb.panel.view.pan.hbar'));
    // shift + the wheel does nothing when the tree is in its window across
    const x0 = await b.eval('mtb.panel.view.pan.x');
    b.mods = 8; await b.mouse('mouseWheel', W0.x, W0.y, {deltaX: 0, deltaY: 100}); b.mods = 0; await sleep(100);
    check('shift + the wheel: no sideways jump for a tree the window holds across', Math.abs(await b.eval('mtb.panel.view.pan.x') - x0) < 0.5);
    // the bar's handle dragged to the top shows the top of the tree
    const hd = await comp('tree_bar_handle_vertical');
    const tr = await comp('tree_bar_track_vertical');
    await b.drag(hd.x, hd.y, hd.x, tr.t - 30, {steps: 10});
    check('the scroll bar\'s handle dragged up to the end: the top of the tree', Math.abs(await b.eval('mtb.panel.view.pan.y')) < 1, await b.eval('mtb.panel.view.pan.y'));
    await shot('tree_scrolled.png', RED, await b.eval(`(() => { const r = document.querySelector('#ig_screen').getBoundingClientRect(); return {x: r.left, y: r.top, width: r.width, height: r.height}; })()`));
    // a drag on the bare tree moves it, and is not a click
    const yA = await b.eval('mtb.panel.view.pan.y');
    await b.drag(W0.x + 400, W0.y, W0.x + 400, W0.y - 300, {steps: 12});
    const yB = await b.eval('mtb.panel.view.pan.y');
    check('a drag on the tree moves it (300 px up: the tree 300 / 1.6 units up)', Math.abs(yB - yA + 300 / 1.6) < 2, {yA, yB, W0, win: await b.eval(`(() => { const r = mtb.panel.view.pan.win.el.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom].map(Math.round); })()`), under: await b.eval(`(() => { const e = document.elementFromPoint(${W0.x + 400}, ${W0.y}); return e.className + ' ' + (e.closest('[data-id]') || {dataset: {}}).dataset.id; })()`)});
    // the bottom back: the arrow of the bar steps a row
    const yC = await b.eval('mtb.panel.view.pan.y');
    await clickId('tree_bar_bottom');
    check('the bar\'s lower arrow steps one row of the grid (106 units)', Math.abs(await b.eval('mtb.panel.view.pan.y') - (yC - 106)) < 1);
    // «Всё дерево»: the whole of it; a click on a slot there orders nothing, comes back to 1:1 at it
    await clickId('mtb_tree_fit');
    await b.move(2, 2); await sleep(250);
    const all = await b.eval(`(() => { const p = mtb.panel.view.pan, w = p.win.el.getBoundingClientRect(); return {z: p.z, every: mtb.panel.view.tree.every(t => { const r = t.button.el.getBoundingClientRect(); return r.left >= w.left - 0.5 && r.right <= w.right + 0.5 && r.top >= w.top - 0.5 && r.bottom <= w.bottom + 0.5; }), label: document.querySelector('#ig_screen [data-id="mtb_tree_fit"]').textContent}; })()`);
    check('«Всё дерево»: every slot in the window, smaller; the button now says «Вблизи»', all.z < 1 && all.every && /Вблизи/.test(all.label), all);
    await shot('tree_show_all.png', RED, await b.eval(`(() => { const r = document.querySelector('#ig_screen').getBoundingClientRect(); return {x: r.left, y: r.top, width: r.width, height: r.height}; })()`));
    const firstOpen = await b.eval(`mtb.panel.view.tree.findIndex(v => mtb.M.status(v.node.key).state === 'open')`);
    const fo = await b.eval(`(() => { const r = mtb.panel.view.tree[${firstOpen}].button.el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()`);
    const g0 = await b.eval('mtb.game.treasury()');
    await b.click(fo.x, fo.y); await sleep(250);
    check('a click on a slot of the whole tree: back to the game\'s size at that slot, nothing ordered', await b.eval(`mtb.panel.view.pan.z === 1 && mtb.game.treasury() === ${g0}`) && await status(await b.eval(`mtb.panel.view.tree[${firstOpen}].node.key`)) === 'open');

    // ---- every slot's building window: inside the screen, clear of its slot ----
    const tips = [];
    for (let i = 0; i < total; i++) {
        await b.move(2, 2);
        const s = await slotAt(i);
        await b.move(s.x, s.y, 2); await sleep(120);
        const t = await b.eval(`(() => { const v = mtb.panel.view.tree[${i}], f = document.querySelector('#ig_screen').getBoundingClientRect(), r = v.info.tip.el.getBoundingClientRect(), s = v.button.el.getBoundingClientRect();
            const on = getComputedStyle(v.info.tip.el).display !== 'none';
            const under = document.elementFromPoint(${s.x}, ${s.y});
            return {under: under && under.className + ' ' + (under.closest('[data-id]') || {dataset: {}}).dataset.id, on, inside: r.left >= f.left - 1 && r.top >= f.top - 1 && r.right <= f.right + 1 && r.bottom <= f.bottom + 1, clear: r.right <= s.left + 0.5 || r.left >= s.right - 0.5 || r.bottom <= s.top || r.top >= s.bottom}; })()`);
        tips.push({i, name: s.name, ...t});
        if (i === 0) await shot('info_popup.png', RED, await b.eval(`(() => { const r = document.querySelector('#ig_screen').getBoundingClientRect(); return {x: r.left, y: r.top, width: r.width, height: r.height}; })()`));
    }
    check(`every slot's building window (${tips.length}) shows on hover, inside the screen, clear of its slot`, tips.every(t => t.on && t.inside && t.clear), tips.filter(t => !(t.on && t.inside && t.clear)));

    // ---- the whole tree built from a reset, by clicks on the slots; cancel; demolish ----
    await b.move(2, 2);
    await b.eval(`mtb.game.gold = 1000000; mtb.panel.refresh(); 1`);
    // cancel: the root ordered and taken back
    const root0 = await b.eval(`mtb.panel.view.tree.findIndex(v => mtb.M.status(v.node.key).state === 'open')`);
    let s = await slotAt(root0);
    const gA = await b.eval('mtb.game.treasury()');
    await b.click(s.x, s.y); await sleep(200);
    const ordered = await status(s.key), gB = await b.eval('mtb.game.treasury()');
    await b.move(s.x, s.y + 1); await sleep(200);
    const banner = await b.eval(`(() => { const v = mtb.panel.view.tree[${root0}]; return {turns: v.turns.GetStateText(), banner: v.turnsBanner.Visible(), note: v.info.reason.GetStateText()}; })()`);
    await shot('order_flow_1_ordered.png', RED, {x: s.l - 160, y: s.t - 260, width: 1100, height: 520});
    await b.click(s.x, s.y); await sleep(200);
    const cancelled = await status(s.key), gC = await b.eval('mtb.game.treasury()');
    check('a click on a slot that can be built orders it: the gold taken, the turns banner on the slot, the window says how to cancel', ordered === 'building' && gB < gA && banner.banner && /^\d+$/.test(banner.turns) && /отменить/.test(banner.note), {ordered, gA, gB, banner});
    check('a click on the slot under construction cancels it: the gold back', cancelled === 'open' && gC === gA, {cancelled, gA, gC});
    await shot('order_flow_2_cancelled.png', RED, {x: s.l - 160, y: s.t - 260, width: 1100, height: 520});
    // everything, turn by turn: each slot that can be built clicked, then the turn ended
    let turns = 0, clicks = 0;
    for (; turns < 60; turns++) {
        const open = await b.eval(`mtb.panel.view.tree.map((v, i) => [i, mtb.M.status(v.node.key).state]).filter(([, s]) => s === 'open').map(([i]) => i)`);
        for (const i of open) {
            if (await b.eval(`mtb.M.status(mtb.panel.view.tree[${i}].node.key).state`) !== 'open') continue;      // a level of the same line taken by the click before
            const p = await slotAt(i);
            await b.click(p.x, p.y); await sleep(60);
            clicks++;
        }
        if (await b.eval(`mtb.panel.view.tree.every(v => mtb.M.status(v.node.key).state === 'built' || !mtb.M.stands(v.node.key) && mtb.game.has_building(v.node.key))`)) break;
        const e = await b.rect('#end_turn'); await b.click(e.x, e.y); await sleep(150);
    }
    const left = await b.eval(`mtb.panel.view.tree.filter(v => !mtb.game.has_building(v.node.key)).map(v => v.node.name + ': ' + mtb.M.status(v.node.key).state + ' ' + (mtb.M.status(v.node.key).why || ''))`);
    check(`the whole tree built from a reset by ${clicks} clicks on its slots and ${turns} turns`, !left.length, left);
    await shot('order_flow_3_built.png', RED, {x: s.l - 160, y: s.t - 260, width: 1100, height: 520});
    // demolish: the root has others on it (its button inactive, why in its tooltip); a top slot goes
    s = await slotAt(root0);
    await b.click(s.x, s.y); await sleep(200);
    const rz = await comp('mtb_ship_demolish');
    await b.move(rz.x, rz.y, 2); await sleep(250);
    const tip0 = await b.eval(`document.querySelector('#ig_screen .root > .tooltip').textContent`);
    await b.click(rz.x, rz.y); await sleep(200);
    check('a built slot with others on it: the demolish button over it, inactive, why in its tooltip; a click does nothing', await status(s.key) === 'built' && /Сначала снесите/.test(tip0), tip0);
    const leaf = await b.eval(`mtb.panel.view.tree.findIndex(v => mtb.M.can_demolish(v.node.key).ok)`);
    s = await slotAt(leaf);
    await b.click(s.x, s.y); await sleep(200);
    const rz2 = await comp('mtb_ship_demolish');
    check('a click on a built slot shows the game\'s demolish button over its corner, the slot selected', !!rz2 && rz2.l < s.l && rz2.t < s.t && await b.eval('mtb.panel.view.options') === s.key, {rz2, s});
    await b.move(rz2.x, rz2.y, 2); await sleep(250);
    await shot('order_flow_4_demolish.png', RED, {x: s.l - 300, y: s.t - 260, width: 1100, height: 520});
    await b.click(rz2.x, rz2.y); await sleep(250);
    check('the demolish button takes the building down', await b.eval(`!mtb.game.has_building('${s.key}')`) && !(await comp('mtb_ship_demolish')));
    await shot('order_flow_5_demolished.png', RED, {x: s.l - 300, y: s.t - 260, width: 1100, height: 520});
    // a click on the bare tree folds a shown demolish button
    s = await slotAt(root0);
    await b.click(s.x, s.y); await sleep(150);
    await b.click(s.x + 300, s.y - 53); await sleep(150);
    check('a click beside the slots folds the demolish button', !(await comp('mtb_ship_demolish')));

    // ---- the crews hired on «Корабль»; F5 keeps them, the tab and the treasury ----
    await tab('ship');
    for (const g of ['rifles', 'cannons', 'bombs', 'cupolas', 'harpoon']) {
        await clickId('mtb_crew_area_' + g);
        const opt = await b.eval(`mtb.M.crew_options('${g}').filter(o => !o.empty && o.unlocked)[0].key`);
        await clickId(`mtb_crew_card_pick_${g}:${opt}`);
        await clickId('mtb_crew_close_' + g);
    }
    const hired = await b.eval(`['rifles', 'cannons', 'bombs', 'cupolas', 'harpoon'].every(g => mtb.M.crew_order(g))`);
    const e2 = await b.rect('#end_turn'); await b.click(e2.x, e2.y); await sleep(300);
    check('the five crews hired on the drawing, standing after the turn', hired && await b.eval(`['rifles', 'cannons', 'bombs', 'cupolas', 'harpoon'].every(g => mtb.M.crew(g) && !mtb.M.crew_order(g))`));
    const before = await b.eval(`JSON.stringify({c: mtb.M.crew_snapshot(), g: mtb.game.treasury(), t: mtb.game.turn, tab: mtb.panel.view.tab, b: mtb.panel.view.tree.map(v => mtb.M.status(v.node.key).state)})`);
    await b.reload(); await ready(); await sleep(600);
    const after = await b.eval(`JSON.stringify({c: mtb.M.crew_snapshot(), g: mtb.game.treasury(), t: mtb.game.turn, tab: mtb.panel.view.tab, b: mtb.panel.view.tree.map(v => mtb.M.status(v.node.key).state)})`);
    check('F5: the buildings, the crews, the treasury, the turn and the tab as they were', before === after, {before: before.slice(0, 300), after: after.slice(0, 300)});
    await set({res: '2560x1440', show: 'one'});
    await b.move(2, 2); await sleep(300);
    const sh = await comp('scheme');
    await shot('drawing_readability.png', RED, {x: sh.l, y: sh.t, width: sh.w, height: sh.h});

    // ---- an old save of the page (before the tabs) still loads ----
    await b.eval(`(() => { const k = Object.keys(localStorage).find(k => k.startsWith('mtb_web_state_')); const s = JSON.parse(localStorage.getItem(k)); delete s.tab; localStorage.setItem(k, JSON.stringify(s)); localStorage.removeItem('mtb_panel_tab'); localStorage.setItem('mtb_ig', JSON.stringify({res: '2560x1440', ui: 1.6, show: 'fit', layout: 'B', font: false})); return 1; })()`);
    await b.reload(); await ready(); await sleep(500);
    check('a save made before the tabs (and the plate\'s old sketch and font) loads: the same game, the tree\'s tab', await b.eval(`mtb.panel.view.tab === 'tree' && mtb.game.turn > 1 && !mtb.ig.state.layout`) && !b.errors.length, b.errors.slice(0, 3));

    // ---- the full screen: the plate hidden at 1:1, P calls it, Esc back ----
    await win(1920, 1080, 1);
    await set({res: 'mine', show: 'one'});
    await b.key('f');
    await sleep(700);
    const fs = await b.eval(`({full: !!document.fullscreenElement, bar: getComputedStyle(document.getElementById('bar')).display})`);
    if (fs.full) {
        const f = await frameRect();
        check('the full screen at 1:1: no plate, the frame from the corner at the screen\'s size', fs.bar === 'none' && Math.round(f.l) === 0 && Math.round(f.t) === 0, {fs, f});
        await b.key('p'); await sleep(300);
        check('P shows the plate in the full screen', await b.eval(`getComputedStyle(document.getElementById('bar')).display`) !== 'none');
        await b.key('Escape'); await sleep(500);
        if (await b.eval('!!document.fullscreenElement')) { await b.eval('document.exitFullscreen().then(() => 1)'); await sleep(400); }
        check('out of the full screen the plate is back', await b.eval(`!document.fullscreenElement && getComputedStyle(document.getElementById('bar')).display !== 'none'`));
    } else {
        console.log('     (the headless browser gives no full screen: its state stood in for)');
        await b.eval(`Object.defineProperty(document, 'fullscreenElement', {get: () => document.documentElement, configurable: true}); document.dispatchEvent(new Event('fullscreenchange')); 1`);
        await sleep(500);
        const f = await frameRect(), bar = await b.eval(`getComputedStyle(document.getElementById('bar')).display`);
        check('the full screen at 1:1 (stood in for): no plate, the frame from the corner at the screen size', bar === 'none' && Math.round(f.l) === 0 && Math.round(f.t) === 0 && Math.round(f.w) === 1920 && Math.round(f.h) === 1080, {bar, f});
        await b.key('p'); await sleep(300);
        check('P shows the plate in the full screen', await b.eval(`getComputedStyle(document.getElementById('bar')).display !== 'none'`));
        await b.eval(`delete document.fullscreenElement; document.dispatchEvent(new Event('fullscreenchange')); 1`);
        await sleep(400);
        check('out of the full screen the plate is back', await b.eval(`getComputedStyle(document.getElementById('bar')).display !== 'none'`));
    }

    // ---- the summary ----
    await set({res: '2560x1440', show: 'fit'});
    await b.key('r'); await sleep(500);
    const fit = await b.eval('JSON.parse(JSON.stringify(mtb.ig.fitCache))');
    check('the summary (R) counts the tree seen in its window', fit && fit.total > 0 && fit.seen > 0 && fit.across, fit);
    console.log(`     slots whole in sight where the tab opens: ${fit.seen} of ${fit.total}; the window ${fit.w}x${fit.h} units, ${fit.rows} rows of the grid`);
    await shot('tree_fit_report.png');
    await b.key('r');

    // ---- one game with «Игра» ----
    const t0 = await b.eval('mtb.game.turn');
    const end = await b.rect('#end_turn');
    await b.click(end.x, end.y);
    await sleep(400);
    const tabNow = await b.eval('mtb.panel.view.tab');
    const game = await b.rect('#mode button[data-mode="game"]');
    await b.click(game.x, game.y);
    await sleep(700);
    const inGame = await b.eval(`({turn: mtb.game.turn, text: document.getElementById('turn').textContent, tab: mtb.panel.view.tab, right: !!document.getElementById('right').offsetParent, w: mtb.root.Width()})`);
    check('the turn ended in «Как в игре» is the turn of «Игра», the same tab, the 3D back, the root 1600x900, the same panel', inGame.turn === t0 + 1 && inGame.text === `Ход ${t0 + 1}` && inGame.tab === tabNow && inGame.right && inGame.w === 1600, inGame);
    await b.open(URL0);
    await ready();
    check('a reload keeps «Игра» and its turn', await b.eval(`document.body.dataset.mode === 'game' && mtb.game.turn === ${t0 + 1}`));
    check('no error in the console', !b.errors.length, b.errors.slice(0, 5));
} catch (err) {
    check('the walk', false, {err: err.message, stack: err.stack && err.stack.split('\n').slice(0, 3).join(' | '), errors: b.errors.slice(0, 5)});
} finally {
    try { await b.close(); } finally { await server.stop(); }
}
console.log(failed ? `failed: ${failed}` : 'failed: 0');
process.exit(failed ? 1 : 0);

// The second QA pass (build/web/shots/verify2): each item a check with real input, a picture each in build/web/shots/fix2.
async function fix2() {
    const FIX2 = join(ROOT, 'build/web/shots/fix2');
    mkdirSync(FIX2, {recursive: true});
    // 13: a walk does not start over a server it did not start
    const refused = await startServer({root: ROOT, port: server.port, tree: FILE}).then(async s => { await s.stop(); return false; }, e => /already taken/.test(e.message));
    check('13: a server on the walk\'s port already: the walk refuses to start another, with a clear message', refused);

    await win(2560, 1480, 1);
    await b.open(URL0 + '?mode=ingame'); await ready();
    await b.eval('localStorage.clear()'); await b.reload(); await ready(); await sleep(600);
    await set({res: '2560x1440', ui: 1.6, show: 'one'});
    await b.move(2, 2); await sleep(300);
    const clip = () => b.eval(`(() => { const r = document.querySelector('#ig_screen').getBoundingClientRect(); return {x: r.left, y: r.top, width: r.width, height: r.height}; })()`);
    const pic = async (name, c) => b.shot(join(FIX2, name), c || await clip());
    const footer = () => b.eval('mtb.panel.view.message.GetStateText()');
    const slotByName = name => b.eval(`(() => { const v = mtb.panel.view.tree.find(t => t.node.name === ${JSON.stringify(name)}); if (mtb.panel.view.pan.z === 1) mtb.panel.view.pan.show(v); const r = v.button.el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, l: r.left, t: r.top, key: v.node.key}; })()`);
    const endTurn = async () => { const e = await b.rect('#end_turn'); await b.click(e.x, e.y); await sleep(250); };
    // the game set as a campaign would have it: these buildings stand (with what they need), this much gold, the turn's news gone
    const setGame = (names, gold = 1000000) => b.eval(`(() => { const M = mtb.M, keys = new Set();
        for (const n of ${JSON.stringify(names)}) for (const k of M.needs_all(mtb.panel.view.tree.find(t => t.node.name === n).node.key)) keys.add(k);
        mtb.game.restore({turn: mtb.game.turn + 1, gold: ${gold}, built: [...keys], queue: []}); M.sync_ship(); M.ship_seen(); mtb.panel.refresh(); return 1; })()`);

    // ---- 1, 2, 5, 7, 8: every building window, three states, both zooms, two screens ----
    const windowAudit = async (res, ui) => {
        await set({res, ui, show: 'one'});
        const total = await b.eval('mtb.panel.view.tree.length');
        const bad = [];
        let n = 0, maxH = 0, over = 0, barge = new Set();
        for (const z of ['near', 'all']) {
            if ((z === 'all') !== await b.eval('mtb.panel.view.pan.z < 1')) await clickId('mtb_tree_fit');
            for (const state of ['locked', 'open', 'built']) for (let i = 0; i < total; i++) {
                await b.move(2, 2);
                const p = await b.eval(`(() => { const v = mtb.panel.view.tree[${i}], M = mtb.M, key = v.node.key, deps = M.needs_all(key).filter(k => k !== key);
                    const built = '${state}' === 'locked' ? [] : '${state}' === 'open' ? deps : [...deps, key];
                    mtb.game.restore({turn: mtb.game.turn, gold: '${state}' === 'locked' && !deps.length ? 0 : 1000000, built, queue: []});
                    mtb.panel.refresh();
                    if (mtb.panel.view.pan.z === 1) mtb.panel.view.pan.show(v);
                    const r = v.button.el.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, st: M.status(key).state}; })()`);
                await b.move(p.x, p.y, 2); await sleep(30);
                const a = await b.eval(`(() => { const v = mtb.panel.view.tree[${i}], t = v.info, f = document.querySelector('#ig_screen').getBoundingClientRect(), r = t.tip.el.getBoundingClientRect();
                    const want = v.node.row.text || '', d = t.description, text = t.tip.el.textContent, cs = getComputedStyle(t.tip.el);
                    const inner = [...t.tip.el.querySelectorAll('.t')].filter(e => e.offsetParent !== null).every(e => { const q = e.getBoundingClientRect(); return q.bottom <= r.bottom + 0.5 && q.top >= r.top - 0.5 && q.right <= r.right + 0.5 && q.left >= r.left - 0.5; });
                    const reason = t.reason.Visible() ? t.reason.el.textContent : '', names = (reason.match(/«[^»]+»/g) || []).length;
                    const grammar = !/^Требу/.test(reason) || (names > 1 ? reason.startsWith('Требуются постройки: ') : reason.startsWith('Требуется постройка: '));
                    const parts = (text.match(/Вид на корабле: /g) || []).length;
                    return {name: v.node.name, shown: cs.display !== 'none', inside: r.left >= f.left - 0.5 && r.top >= f.top - 0.5 && r.right <= f.right + 0.5 && r.bottom <= f.bottom + 0.5,
                        full: d.textEl.textContent === want && (!want || d.Visible()), ell: /…/.test(text) && !/…/.test(want), inner, grammar,
                        chain: t.chain.Visible(), gap: want ? d.y > 33 + 12 + 1 : false, parts, partsWant: (v.node.row.parts_new || []).length, barge: /Вид на корабле: Базовая барка/.test(text),
                        opaque: /gradient/.test(cs.backgroundImage) && cs.backgroundClip === 'border-box', h: t.h, over: t.tip.y < mtb.panel.view.area.y}; })()`);
                n++; maxH = Math.max(maxH, a.h); if (a.over) over++;
                if (a.barge) barge.add(a.name);
                const why = ['shown', 'inside', 'full', 'inner', 'grammar', 'opaque'].filter(k => !a[k]).concat(a.ell ? ['«…»'] : [], a.chain ? ['the chain\'s line'] : [], a.gap ? ['a gap under the title'] : [], a.parts !== a.partsWant ? ['«Вид на корабле» lines'] : []);
                if (why.length) bad.push({res, z, state, st: p.st, name: a.name, why});
                if (res === '2560x1440' && z === 'near' && state === 'locked' && a.name === 'Тир') { await pic('01_tir_window_full.png'); await pic('05_lock_reason_plural.png'); }
                if (res === '2560x1440' && z === 'near' && state === 'locked' && a.name === 'Полигон') await pic('01_poligon_locked.png');
                if (res === '2560x1440' && z === 'near' && state === 'built' && a.name === 'Корпус с рунами') await pic('07_parts_once_hull.png');
                if (res === '2560x1440' && z === 'all' && state === 'open' && a.name === 'Полигон') await pic('01_poligon_all_tree.png');
                if (res === '1920x1080' && z === 'near' && state === 'locked' && a.name === 'Полигон') await pic('01_poligon_locked_1080.png');
            }
        }
        if ((await b.eval('mtb.panel.view.pan.z < 1'))) await clickId('mtb_tree_fit');
        check(`1, 2, 5, 7, 8: ${res} UI ${ui}: all ${n} building windows (41 × locked, orderable, built × both zooms) whole: the full description, nothing «…», every text inside, inside the screen (${over} over the title row, the tallest ${maxH}); opaque; the reason\'s grammar; no chain\'s line and no gap; «Вид на корабле» only where new`,
            !bad.length && n === total * 6, bad.slice(0, 6));
        check(`7: ${res}: «Вид на корабле: Базовая барка» in one window only (the level that brings the barge)`, barge.size === 1, [...barge]);
    };
    await windowAudit('2560x1440', 1.6);
    await windowAudit('1920x1080', 1.0);
    await set({res: '2560x1440', ui: 1.6, show: 'one'});

    // ---- 6: one unit, one card; its panel tells both ----
    await setGame(['Тир', 'Пивной чертог', 'Торпедная галерея']);
    const six = await b.eval(`(() => { const v = mtb.panel.view, groups = v.data.groups, bad = [];
        for (const t of v.tree) { const units = v.crew.filter(c => c.v === t).map(c => c.army || groups[c.group].options[c.option].unit); if (new Set(units).size !== units.length) bad.push(t.node.name + ': ' + units.join(', ')); }
        const merged = v.crew.filter(c => c.alsoArmy).map(c => c.v.node.name + ': ' + groups[c.group].options[c.option].name);
        return {bad, merged}; })()`);
    check('6: no slot shows one unit twice; «Громобои» on «Тир», «Мстители-пираты» on «Пивной чертог», the torpedoes once, each the crew\'s card', !six.bad.length && ['Тир: Громобои', 'Пивной чертог: Мстители-пираты', 'Торпедная галерея: Ящеры с торпедами'].every(m => six.merged.includes(m)), six);
    let s = await slotByName('Тир');
    await b.move(2, 2);
    const card = await comp('mtb_crew_card_crew_weapons_2_thunderers');
    await b.move(card.x, card.y, 3); await sleep(300);
    const both = await b.eval(`mtb.panel.view.crew.find(c => c.option === 'thunderers' && c.v.node.name === 'Тир').info.stateText.el.textContent`);
    check('6: the merged card\'s panel says both: the crew and the army', /для найма в армию/.test(both), both);
    await pic('06_one_card_per_unit.png');

    // ---- 9: a new kind in a place already open: «!», the row's and the tag's glow, the foot line ----
    // everything «Гнёзда с боеукладкой» needs stands (the nests open with their grenades), the level itself not
    await setGame(await b.eval(`(() => { const M = mtb.M, key = mtb.panel.view.tree.find(t => t.node.name === 'Гнёзда с боеукладкой').node.key, names = new Set(M.needs_all(key).filter(k => k !== key));
        mtb.game.restore({turn: mtb.game.turn, gold: 1e6, built: [...names], queue: []});
        for (let i = 0; i < 5 && M.missing(key).length; i++) for (const k of M.missing(key)) if (!k.startsWith('tier:')) { for (const x of M.needs_all(k)) names.add(x); mtb.game.restore({turn: mtb.game.turn, gold: 1e6, built: [...names], queue: []}); }
        return [...names].map(k => M.level(k).name); })()`));
    s = await slotByName('Гнёзда с боеукладкой');
    await b.click(s.x, s.y); await sleep(150);
    check('3: an order: the foot line says it', /^Заказано: «Гнёзда с боеукладкой»/.test(await footer()), await footer());
    const ordered = await footer();
    await b.reload(); await ready(); await sleep(700);
    check('3: the foot line «Заказано: …» survives F5', await footer() === ordered, {was: ordered, now: await footer()});
    for (let i = 0; i < 4 && await b.eval(`mtb.M.status('${s.key}').state`) !== 'built'; i++) await endTurn();
    await b.move(2, 2); await sleep(300);
    const nine = await b.eval(`(() => { const v = mtb.panel.view; return {msg: v.message.GetStateText(), mark: v.tabMark.Visible(), glow: v.tabGlow.Visible() && /drop-shadow/.test(v.tabs.ship.button.el.style.filter),
        row: /drop-shadow/.test(v.column.rows.cupolas.card.el.style.filter), others: Object.entries(v.column.rows).filter(([g]) => g !== 'cupolas').some(([, r]) => /drop-shadow/.test(r.card.el.style.filter))}; })()`);
    check('9: «Гнёзда с боеукладкой» built: «!» on «Корабль», the nests\' row glows, the foot line «… В гнёздах теперь доступны «Топоры».»',
        nine.msg === 'Построено: «Гнёзда с боеукладкой». В гнёздах теперь доступны «Топоры».' && nine.mark && nine.glow && nine.row && !nine.others, nine);
    await pic('09_new_kind_tree.png');
    // 4: the tab's glow hugs the tab, whole, inside the title row
    const four = await b.eval(`(() => { const v = mtb.panel.view, t = v.tabs.ship.button.el.getBoundingClientRect(), f = v.frame.el.getBoundingClientRect(), k = f.width / v.frame.Width();
        return {old: !!document.querySelector('#ig_screen [data-id="mtb_tab_ship_glow"]'), top: (t.top - f.top) / k - 6, bottom: (t.bottom - f.top) / k + 6, head: v.area.y - 4}; })()`);
    check('4: the «Корабль» tab\'s glow: a soft halo round the tab itself (no separate rectangle), whole inside the title row', !four.old && four.top >= 0 && four.bottom <= four.head, four);
    const tb = await comp('mtb_tab_ship');
    await pic('04_tab_glow.png', {x: tb.l - 40, y: tb.t - 20, width: tb.w + 420, height: tb.h + 40});
    const built9 = await footer();
    await b.reload(); await ready(); await sleep(700);
    check('3: the foot line «Построено: …» survives F5 with the «!» mark', await footer() === built9 && await b.eval('mtb.panel.view.tabMark.Visible()'), {was: built9, now: await footer()});
    await pic('03_footer_after_f5.png');
    await tab('ship'); await b.move(2, 2); await sleep(300);
    const tag9 = await b.eval(`(() => { const c = mtb.panel.view.crewAreas.cupolas; return Object.values(c.tags).some(t => t.Visible() && /drop-shadow/.test(t.el.style.filter)) && !Object.values(mtb.panel.view.crewAreas).filter(x => x !== c).some(x => Object.values(x.tags).some(t => /drop-shadow/.test(t.el.style.filter))); })()`);
    check('9: on «Корабль» the nests\' tag glows that turn (and no other)', tag9);
    await pic('09_new_kind_ship.png');
    await tab('tree');

    // ---- 10, 11: the crews' numbers that add up; the riflemen are 11 ----
    const all = await debugRect(b, '#build_all'); await b.click(all.x, all.y); await sleep(500);
    await b.eval('mtb.game.gold = 1000000; mtb.panel.refresh(); 1');
    await tab('ship');
    const sums = [];
    for (const g of ['rifles', 'cannons', 'bombs', 'cupolas', 'harpoon']) {
        await clickId('mtb_crew_area_' + g);
        for (const o of await b.eval(`mtb.M.crew_options('${g}').filter(o => !o.empty).map(o => o.key)`)) {
            const c = await comp(`mtb_crew_card_pick_${g}:${o}`);
            if (!c) continue;
            await b.move(c.x, c.y, 2); await sleep(120);
            const r = await b.eval(`(() => { const s = mtb.panel.view.crewAreas['${g}'].slots.find(x => x.key === '${o}'); const i = s.info; if (!i || !i.rows.ammo) return null;
                return {value: i.rows.ammo.value.el.textContent, note: i.ammoNote ? i.ammoNote.el.textContent : '', bonus: (i.bonusLines || []).join(' ').replace(/\\[\\[[^\\]]*\\]\\]/g, ''), men: i.panel.el.querySelector('[data-id="dy_men"]').textContent}; })()`);
            if (!r) continue;
            const total = Number(r.value), m = /^(\d+) \S+(?: по (\d+)|, около (\d+) )/.exec(r.note), bm = /Боезапас [^(]*\((\d+) → (\d+)\)/.exec(r.bonus);
            const ok = Number.isInteger(total) && (!r.note || (m && (m[2] ? Number(m[1]) * Number(m[2]) === total : !Number.isInteger(total / Number(m[1])) && Math.abs(total / Number(m[1]) - Number(m[3])) <= 0.5)))
                && (!bm || Number(bm[2]) === total) && (!m || Number(m[1]) === Number(r.men));
            sums.push({g, o, ...r, ok});
            if (g === 'bombs' && o === 'stock') await pic('10_ammo_bombs.png');
            if (g === 'rifles' && o === 'pirates') await pic('11_rifles_11.png');
            if (g === 'cannons' && o === 'stock') await pic('10_ammo_cannons.png');
        }
        await clickId('mtb_crew_close_' + g);
    }
    check(`10: every crew's ammunition adds up (${sums.length} panels): the group's whole as the number, «N мест по M» = whole or «около M» when not whole, the bonus «(base → whole)», the places = the men`, sums.length >= 10 && sums.every(x => x.ok), sums.filter(x => !x.ok).slice(0, 4));
    const pir = sums.find(x => x.g === 'rifles' && x.o === 'pirates');
    check('11: the pirates: 11 men, 11 places, their ammunition for 11', pir && pir.men === '11' && /^11 стрелков/.test(pir.note), pir);
    await b.move(2, 2); await sleep(200);
    await pic('ship_tab_full.png');

    // ---- 12: F5 and the tab clicked at once: never a frame with the parchment or the barge missing ----
    await b.eval(`window.__frames = []; 1`);
    await b.reload();
    const t0 = Date.now(), frames = [];
    let clicked = false;
    while (Date.now() - t0 < 2500) {
        const f = await b.eval(`(() => { const r = window.mtb && mtb.root; if (!r) return {none: true}; const hidden = getComputedStyle(r.el).visibility === 'hidden';
            const imgs = [...r.el.querySelectorAll('img')].filter(i => i.offsetParent !== null && i.getAttribute('src') && getComputedStyle(i).visibility !== 'hidden');
            return {hidden, missing: imgs.filter(i => !i.complete || !i.naturalWidth).map(i => i.getAttribute('src').split('/').pop()).slice(0, 4)}; })()`).catch(() => ({none: true}));
        frames.push(f);
        if (!clicked && Date.now() - t0 > 300 && !f.none && !f.hidden) { const t = await comp('mtb_tab_tree').catch(() => null); if (t) { await b.click(t.x, t.y); clicked = true; } }
        if (!clicked && Date.now() - t0 > 300 && !f.none && f.hidden) await sleep(10);
    }
    const halfDrawn = frames.filter(f => !f.none && !f.hidden && f.missing.length);
    check(`12: F5 then a tab click at once (${frames.length} looks in 2.5 s): the screen is never shown with a picture still loading; shown whole as soon as loaded`, !halfDrawn.length && frames.some(f => !f.none && !f.hidden), halfDrawn.slice(0, 3));
    await sleep(300); await b.move(2, 2); await sleep(200);
    await pic('12_after_f5.png');
    await tab('tree'); await b.move(2, 2); await sleep(300);
    await pic('tree_tab_full.png');
    check('fix2: no error in the console', !b.errors.length, b.errors.slice(0, 4));
    await b.eval('localStorage.clear()'); await b.reload(); await ready(); await sleep(500);
}
