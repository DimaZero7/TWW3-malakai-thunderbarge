// The page's mode «Как в игре» walked as its author uses it: node --experimental-websocket tools/tests/ingame_walk.mjs
// Its own server (tools/web_serve.py --port 8767, a copy of web/data/tree_design.json in the temp folder: the author's file is only read).
// Checks: the mode opens from its button with only the game's screen (no 3D, no overview, the bar a plate outside the frame); at windows of
// 1280 x 800, 1920 x 1080 and 2560 x 1440 and device pixel ratios 1, 1.25 and 1.5, for each screen of the game (1920 x 1080, 2560 x 1440,
// 3840 x 2160, this monitor) at «1:1» and «Вписать», a slot of the tree measures 74 x s x shown pixels of the device (getBoundingClientRect x DPR,
// within 1 px), s the interface's scale (web/js/ingame.js, uiScale), and the frame is the screen's size; the windows that pop up (the building's
// information, a unit's panel, the crew's choice, Malakai's side) at the four edges of the screen stay whole inside the frame; the full screen
// hides the plate at 1:1; the game's state is the one of «Игра»; no error in the console. Pictures in build/web/shots/ingame/. Exit 1 on a failure.
import {readFileSync, writeFileSync, mkdirSync, rmSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {tmpdir} from 'node:os';
import {launch, sleep} from './cdp.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const OUT = join(ROOT, 'build/web/shots/ingame');
mkdirSync(OUT, {recursive: true});
const DATA = join(tmpdir(), 'mtb_ingame_walk');
rmSync(DATA, {recursive: true, force: true});
mkdirSync(DATA, {recursive: true});
const FILE = join(DATA, 'tree_design.json');
writeFileSync(FILE, readFileSync(join(ROOT, 'web/data/tree_design.json')));
const PORT = 8767, URL0 = `http://127.0.0.1:${PORT}/`;
const server = spawn('py', ['-3.14', join(ROOT, 'tools/web_serve.py'), '--port', String(PORT), '--tree', FILE], {stdio: 'ignore'});
for (let i = 0; i < 50; i++) { if (await fetch(URL0 + 'data/tree_design.json').then(r => r.ok).catch(() => false)) break; await sleep(200); }
let failed = 0;
const check = (name, ok, extra = '') => { if (!ok) failed++; console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok || !extra ? '' : '  ' + (typeof extra === 'string' ? extra : JSON.stringify(extra)))); return ok; };
// the rule of web/js/ingame.js written again: the test does not take the page's own numbers for the expected ones
const uiScale = (w, h, u) => Math.min(h < 1440 ? Math.min(u, 1) : u, w / 1600, h / 900);

const b = await launch({width: 1920, height: 1080, port: 9396, profile: join(tmpdir(), 'mtb_ingame_profile')});
// a window of W x H pixels of the device at the ratio d: the CSS size is W / d, the monitor (screen) the same size
const win = async (W, H, d) => {
    await b.send('Emulation.setDeviceMetricsOverride', {width: Math.round(W / d), height: Math.round(H / d), deviceScaleFactor: d, mobile: false, screenWidth: Math.round(W / d), screenHeight: Math.round(H / d)});
    await sleep(350);
};
const grab = async () => (await b.send('Page.captureScreenshot', {format: 'png'})).data;
const shot = name => b.shot(join(OUT, name));
const ready = () => b.until('!!(window.mtb && mtb.M && mtb.panel && mtb.root)', 15000);
const set = async o => { await b.eval(`mtb.ig.set(${JSON.stringify(o)}); 1`); await sleep(250); };
const frameRect = () => b.rect('#ig_screen');
// every window that pops up and is shown now, and whether each lies whole in the frame of the game's screen
const popups = () => b.eval(`(() => {
    const f = document.querySelector('#ig_screen').getBoundingClientRect();
    const shown = e => { for (let x = e; x && x !== document.body; x = x.parentElement) { const s = getComputedStyle(x); if (s.display === 'none' || s.visibility === 'hidden') return false; } return true; };
    return [...document.querySelectorAll('#ig_screen .root .tooltip_frame, #ig_screen .root .unit_parchment, #ig_screen .root .layer_click, #ig_screen .root .layer_hover, #ig_screen .root > .tooltip')]
        .filter(e => shown(e) && e.getBoundingClientRect().width > 2)
        .map(e => { const r = e.getBoundingClientRect(); return {id: e.dataset.id || e.className, inside: r.left >= f.left - 1 && r.top >= f.top - 1 && r.right <= f.right + 1 && r.bottom <= f.bottom + 1,
                    r: [Math.round(r.left - f.left), Math.round(r.top - f.top), Math.round(r.right - f.left), Math.round(r.bottom - f.top)]}; });
})()`);
// a node of the tree's window by where it is: the slots whole in the window, the one most to the side asked
const nodeAt = side => b.eval(`(() => {
    const v = mtb.panel.view, w = v.pan.win.el.getBoundingClientRect();
    const all = v.tree.map(t => ({t, r: t.button.el.getBoundingClientRect()})).filter(({r}) => r.left >= w.left && r.right <= w.right && r.top >= w.top && r.bottom <= w.bottom);
    const key = {left: a => a.r.left, right: a => -a.r.right, top: a => a.r.top, bottom: a => -a.r.bottom}[${JSON.stringify(side)}];
    all.sort((a, b) => key(a) - key(b));
    const a = all[0];
    return a ? {x: a.r.left + a.r.width / 2, y: a.r.top + a.r.height / 2, name: a.t.node.name} : null;
})()`);

try {
    // ---- the mode opens from its button; the page as it is left in «Игра» ----
    await win(1920, 1080, 1);
    await b.open(URL0 + '?mode=game');
    await ready();
    await b.eval('localStorage.clear()');
    await b.reload();
    await ready();
    await sleep(500);
    await b.eval(`document.getElementById('build_all').click(); 1`);
    await sleep(400);
    const btn = await b.rect('#mode button[data-mode="ingame"]');
    await b.click(btn.x, btn.y);
    await sleep(600);
    const look = await b.eval(`({mode: document.body.dataset.mode, right: !!document.getElementById('right').offsetParent, overview: !!document.getElementById('overview').offsetParent,
        frame: !!document.querySelector('#ig_screen .root'), bar: document.getElementById('bar').getBoundingClientRect().bottom, top: document.getElementById('ig_screen').getBoundingClientRect().top,
        log: !!document.getElementById('log').offsetParent, saved: localStorage.getItem('mtb_mode')})`);
    check('«Как в игре» opens from its button: the frame of the screen, no 3D, no overview, the plate above the frame', look.mode === 'ingame' && !look.right && !look.overview && look.frame && look.top >= look.bar && !look.log && look.saved === 'ingame', look);

    // ---- the slot's size in the device's pixels: every window, ratio, screen, at 1:1 and fitted ----
    const sizes = [];
    for (const [W, H] of [[1280, 800], [1920, 1080], [2560, 1440]]) for (const d of [1, 1.25, 1.5]) {
        await win(W, H, d);
        for (const res of ['1920x1080', '2560x1440', '3840x2160', 'mine']) for (const show of ['one', 'fit']) {
            await set({res, ui: 1.6, show, layout: 'A'});
            const m = await b.eval(`(() => { const v = mtb.panel.view, t = v.tree.find(x => x.node.key === v.selected) || v.tree[0], d = devicePixelRatio, f = document.getElementById('ig_screen').getBoundingClientRect();
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
    for (const x of sizes.filter(x => x.show === 'one' && x.W === 1920 && x.d === 1.25)) console.log(`     1920x1080 window, DPR 1.25, ${x.res} 1:1: slot ${x.slot} px (expected ${x.want})`);

    // ---- the pictures: fitted at each screen, 1:1 at 1080 ----
    await win(1920, 1080, 1);
    for (const [res, name] of [['1920x1080', 'fit_1080.png'], ['2560x1440', 'fit_1440.png'], ['3840x2160', 'fit_2160.png']]) {
        await set({res, ui: 1.6, show: 'fit', layout: 'A', ruler: false});
        await sleep(300);
        await shot(name);
    }
    await set({res: '1920x1080', show: 'one'});
    const one = await b.rect('#ig_one');
    await b.click(one.x, one.y);
    await sleep(300);
    const oneFrame = await frameRect();
    check('1:1 at 1920x1080 in a 1920x1080 window: the frame is 1920x1080, the window scrolls for the rest', Math.round(oneFrame.w) === 1920 && Math.round(oneFrame.h) === 1080, oneFrame);
    await shot('one_to_one_1080.png');

    // ---- the ruler ----
    await set({res: '2560x1440', show: 'fit', layout: 'A'});
    await b.key('l');
    await sleep(500);
    const marks = await b.eval(`[...document.querySelectorAll('#ig_overlay .m b')].map(e => e.textContent)`);
    check('the ruler (L) writes the panel, the tree\'s window, a slot, a card, the column\'s text and the drawing in the game\'s pixels', marks.length >= 5 && marks.some(t => /слот 74 ед\. = 118×118 px/.test(t)) && marks.some(t => /текст колонки/.test(t)) && /карточка 23×50 ед. = 36,8×80 px/.test(await b.eval(`document.querySelector('#ig_overlay .legend').textContent`)), marks);
    await shot('ruler.png');
    await b.key('l');

    // ---- the windows that pop up, at the four edges of the screen ----
    const cases = [];
    const hover = async (label, layout, side) => {
        await set({res: '2560x1440', show: 'fit', layout});
        await b.move(5, 5);
        const p = await nodeAt(side);
        if (!p) { cases.push({label, ok: false, why: 'no node'}); return; }
        await b.move(p.x, p.y, 4);
        await sleep(350);
        const list = await popups();
        cases.push({label: `${label} (${p.name})`, ok: list.length > 0 && list.every(x => x.inside), list});
        return grab();
    };
    const pics = [];
    pics.push(await hover('the building window of the rightmost node', 'A', 'right'));
    pics.push(await hover('the building window of the leftmost node', 'B', 'left'));
    pics.push(await hover('the building window of the topmost node', 'C', 'top'));
    await hover('the building window of the lowest node', 'A', 'bottom');
    // a unit's panel: the card of the topmost node with crew in the wide window
    await set({res: '2560x1440', show: 'fit', layout: 'B'});
    await b.move(5, 5);
    const card = await b.eval(`(() => { const w = mtb.panel.view.pan.win.el.getBoundingClientRect(); const c = mtb.panel.view.crew.map(c => c.card.el.getBoundingClientRect()).filter(r => r.top >= w.top && r.bottom <= w.bottom && r.left >= w.left && r.right <= w.right).sort((a, b) => a.top - b.top)[0]; return c ? {x: c.left + c.width / 2, y: c.top + c.height / 2} : null; })()`);
    if (card) { await b.move(card.x, card.y, 4); await sleep(350); const l = await popups(); cases.push({label: 'a unit\'s panel of the topmost card', ok: l.length > 0 && l.every(x => x.inside), list: l}); }
    // the crew's choice of the bombs (the drawing's foot) and the harpoon's (its left edge), Malakai's side (its lower left corner)
    await set({res: '2560x1440', show: 'fit', layout: 'A'});
    for (const g of ['bombs', 'harpoon']) {
        await b.move(5, 5);
        const tag = await b.rect(`#ig_screen [data-id="mtb_crew_area_${g}"]`);
        if (!tag) { cases.push({label: `the crew's choice of ${g}`, ok: false, why: 'no tag'}); continue; }
        await b.click(tag.x, tag.y);
        await sleep(350);
        await b.move(5, 5);
        const l = await popups();
        cases.push({label: `the crew's choice of ${g}`, ok: l.length > 0 && l.every(x => x.inside), list: l});
        if (g === 'bombs') pics.push(await grab());
        await b.click(tag.x, tag.y);
        await sleep(200);
    }
    const plan = await b.rect('#ig_screen [data-id="plan_ship"]');
    if (plan) { await b.move(plan.x, plan.y, 4); await sleep(350); const l = await popups(); cases.push({label: 'Malakai\'s side (lower left)', ok: l.every(x => x.inside), list: l}); }
    for (const c of cases) check(`at the edge: ${c.label} stays inside the frame`, c.ok, c);
    // the four in one picture: a page of their pictures
    await b.move(5, 5);
    await b.eval(`(() => { document.body.innerHTML = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;background:#000">' + ${JSON.stringify(pics)}.map(p => '<img style="width:100%;display:block" src="data:image/png;base64,' + p + '">').join('') + '</div>'; document.body.style.overflow = 'hidden'; return 1; })()`);
    await sleep(500);
    await shot('popups_at_edges.png');
    await b.open(URL0 + '?mode=ingame');
    await ready();
    await sleep(600);

    // ---- the layouts and the summary of the tree ----
    for (const l of ['A', 'B', 'C']) {
        await set({res: '2560x1440', show: 'fit', layout: l, ruler: false});
        await b.move(5, 5);
        await sleep(300);
        await shot(`layout_variant_${l}.png`);
    }
    await set({layout: 'A'});
    const rb = await b.rect('#ig_report_btn');
    await b.click(rb.x, rb.y);
    await sleep(600);
    const fit = await b.eval('JSON.parse(JSON.stringify(mtb.ig.fitCache))');
    check('the summary (its button) counts the tree seen in each layout', ['A', 'B', 'C'].every(l => fit[l] && fit[l].total > 0 && fit[l].seen > 0), fit);
    console.log(`     nodes seen whole without scrolling, of ${fit.A.total}: A ${fit.A.seen} (opened: ${fit.A.open ? fit.A.open.seen : '-'}), B ${fit.B.seen}, C ${fit.C.seen}`);
    await shot('tree_fit_report.png');
    await b.key('r');
    check('R folds the summary', await b.eval(`document.getElementById('ig_report').style.display === 'none'`));

    // ---- the full screen: the plate hidden at 1:1, P calls it, Esc back ----
    await set({res: 'mine', show: 'one'});
    await b.key('f');
    await sleep(700);
    const fs = await b.eval(`({full: !!document.fullscreenElement, bar: getComputedStyle(document.getElementById('bar')).display})`);
    if (fs.full) {
        const f = await frameRect();
        check('the full screen at 1:1: no plate, the frame from the corner at the screen\'s size', fs.bar === 'none' && Math.round(f.l) === 0 && Math.round(f.t) === 0, {fs, f});
        await b.key('p'); await sleep(300);
        const p = await b.eval(`getComputedStyle(document.getElementById('bar')).display`);
        check('P shows the plate in the full screen', p !== 'none', p);
        await b.key('Escape'); await sleep(500);
        if (await b.eval('!!document.fullscreenElement')) { console.log('     (Esc of the headless browser does not leave the full screen: left by the page)'); await b.eval('document.exitFullscreen().then(() => 1)'); await sleep(400); }
        check('out of the full screen the plate is back', await b.eval(`!document.fullscreenElement && getComputedStyle(document.getElementById('bar')).display !== 'none'`));
    } else {
        // the headless browser gives no full screen: the page is told it is in one (the state the browser would give), the window being the screen
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

    // ---- one game with «Игра» ----
    await set({res: '2560x1440', show: 'fit', layout: 'A'});
    const t0 = await b.eval('mtb.game.turn');
    const end = await b.rect('#end_turn');
    await b.click(end.x, end.y);
    await sleep(400);
    const sel = await b.eval('mtb.panel.view.selected');
    const game = await b.rect('#mode button[data-mode="game"]');
    await b.click(game.x, game.y);
    await sleep(700);
    const inGame = await b.eval(`({turn: mtb.game.turn, text: document.getElementById('turn').textContent, sel: mtb.panel.view.selected, right: !!document.getElementById('right').offsetParent, w: mtb.root.Width()})`);
    check('the turn ended in «Как в игре» is the turn of «Игра», the same building selected, the 3D back, the root 1600x900', inGame.turn === t0 + 1 && inGame.text === `Ход ${t0 + 1}` && inGame.sel === sel && inGame.right && inGame.w === 1600, inGame);
    await b.open(URL0);
    await ready();
    check('a reload keeps «Игра» and its turn', await b.eval(`document.body.dataset.mode === 'game' && mtb.game.turn === ${t0 + 1}`));
    check('no error in the console', !b.errors.length, b.errors.slice(0, 5));
} catch (err) {
    check('the walk', false, {err: err.message, errors: b.errors.slice(0, 5)});
} finally {
    await b.close();
    server.kill();
}
console.log(failed ? `failed: ${failed}` : 'failed: 0');
process.exit(failed ? 1 : 0);
