// The crew on the 3D barge walked as the player does (tools/tests/cdp.mjs, a headless Chrome whose WebGL really draws): node --experimental-websocket
// tools/tests/crew_3d_walk.mjs. Its own server (tools/web_serve.py --port 8767 --tree <a copy>). At the page's scales 0.6 and 1: «Построить всё»;
// every kind of every group put by clicks on the drawing and the turn; each seen on the model from the view that shows its place, beside the
// drawing; a hire on its way (the ghost); F5; Malakai's side; a building with a crew demolished; the button «К месту экипажа». The 3D pictures are
// checked not to be empty (the canvas's pixels where the crew stands change when it is shown). The weight: the bytes the page loads at the start and
// for each crew model. Pictures to build/web/shots/groups3d/. Prints a line a check; exit 1 on any failure.
import {readFileSync, writeFileSync, mkdirSync, rmSync} from 'node:fs';
import {spawn, spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {tmpdir} from 'node:os';
import {launch, sleep, decodePng, debugRect} from './cdp.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DATA = join(tmpdir(), 'mtb_groups3d_tree');
rmSync(DATA, {recursive: true, force: true});
mkdirSync(DATA, {recursive: true});
const FILE = join(DATA, 'tree_design.json');
writeFileSync(FILE, readFileSync(join(ROOT, 'web/data/tree_design.json')));
const PORT = 8767, URL0 = `http://127.0.0.1:${PORT}/`;
const server = spawn('py', ['-3.14', join(ROOT, 'tools/web_serve.py'), '--port', String(PORT), '--tree', FILE], {stdio: 'ignore'});
for (let i = 0; i < 50; i++) { if (await fetch(URL0 + 'data/tree_design.json').then(r => r.ok).catch(() => false)) break; await sleep(200); }
const SHOTS = join(ROOT, 'build/web/shots/groups3d'), PARTS = join(SHOTS, 'parts');
mkdirSync(PARTS, {recursive: true});
let failed = 0;
const check = (name, ok, extra = '') => { if (!ok) failed++; console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok || !extra ? '' : '  ' + (typeof extra === 'string' ? extra : JSON.stringify(extra)))); return ok; };
const weight = {};

async function walk(scale) {
    const W = Math.round(1600 * scale / 0.62) + 2, H = Math.max(950, Math.round(900 * scale) + 60);
    const b = await launch({width: W, height: H, port: 9380 + Math.round(scale * 10), profile: join(tmpdir(), 'mtb_3d_profile_' + String(scale).replace('.', '_'))});
    await b.size(W, H);
    const tag = `[${scale}]`, big = scale === 0.6;
    try {
        await b.open(URL0 + '?mode=game');
        await b.until('!!(window.mtb && mtb.M && mtb.panel)', 15000);
        await b.eval('localStorage.clear()');
        await b.reload();
        await b.until('document.body.dataset.ready === "1"', 30000);
        // the start of the page: what it loaded, and that no crew model is among it (each comes when it is wanted)
        const start = await b.eval(`(() => { const r = performance.getEntriesByType('resource'); return {files: r.length, bytes: r.reduce((s, e) => s + (e.decodedBodySize || 0), 0), crew: r.filter(e => e.name.includes('/build/models/crew_')).length, ms: Math.round(performance.now())}; })()`);
        if (big) weight.start = start;
        check(`${tag} the page's start loads no crew model`, start.crew === 0, start);
        const comp = id => b.eval(`(() => { const e = [...document.querySelectorAll('#screen [data-id="${id}"]')].find(x => x.offsetParent !== null && getComputedStyle(x).visibility !== 'hidden'); if (!e) return null; const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, l: r.left, t: r.top, w: r.width, h: r.height}; })()`);
        const clickId = async id => { const r = await comp(id); if (!r) throw new Error('not on the screen: ' + id); await b.click(r.x, r.y); await sleep(150); };
        const button = async sel => { const r = /gold_quick|build_|reset_all/.test(sel) ? await debugRect(b, sel) : await b.rect(sel); await b.click(r.x, r.y); await sleep(250); };
        const crew3d = () => b.eval('mtb.viewer.crewState()');
        const view3d = async () => { const r = await b.rect('#view3d canvas'); return {x: r.l, y: r.t, width: r.w, height: r.h}; };
        const drawing = async () => { const r = await comp('scheme'); return {x: r.l, y: r.t, width: r.w, height: r.h}; };
        const loaded = name => b.until(`mtb.viewer.crewModels && mtb.viewer.crewModels['${name}'] !== undefined`, 20000).then(() => sleep(400));
        // the 3D picture is not empty: its pixels differ when the model is hidden (the crew's own pixels)
        const pixels = async () => { const r = await b.send('Page.captureScreenshot', {format: 'png', clip: {...await view3d(), scale: 1}}); return decodePng(Buffer.from(r.data, 'base64')); };
        const diff = async name => {
            const a = await pixels();
            await b.eval(`mtb.viewer.crewModels['${name}'].visible = false; 1`); await sleep(120);
            const c = await pixels();
            await b.eval(`mtb.viewer.applyCrew(); 1`); await sleep(120);
            let n = 0;
            for (let i = 0; i < a.data.length; i += 4) if (Math.abs(a.data[i] - c.data[i]) + Math.abs(a.data[i + 1] - c.data[i + 1]) + Math.abs(a.data[i + 2] - c.data[i + 2]) > 30) n++;
            return n;
        };
        const pick = async (g, k) => { await clickId('mtb_crew_area_' + g); await clickId(`mtb_crew_card_pick_${g}:${k}`); await clickId('mtb_crew_close_' + g); };
        await button('#build_all');
        await b.eval('mtb.game.gold = 100000; 1');         // the debug field's gold: a dozen hires in a row
        await sleep(600);
        check(`${tag} nothing of the crew on the model before a choice (the lookouts stand in the nests)`, JSON.stringify(Object.entries(await crew3d()).filter(([k, v]) => v !== 'hidden' && k !== 'lookouts_on' && !k.startsWith('malakai'))) === '[]', await crew3d());
        // every gun, each by the clicks of the choice and the turn, seen from the port's view beside the drawing
        const guns = await b.eval(`mtb.M.crew_options('cannons').filter(o => !o.empty).map(o => o.key)`);
        for (const k of guns) {
            await pick('cannons', k);
            await button('#end_turn');
            const model = k === 'flaming' ? 'cannons_stock' : 'cannons_' + k;
            const t0 = Date.now();
            await loaded(model);
            if (big && !weight[model]) weight[model] = {ms_to_shown: Date.now() - t0};
            await b.eval(`mtb.viewer.view('port'); 1`); await sleep(500);
            const n = await diff(model);
            check(`${tag} cannons/${k}: «${model}» stands on the model, its pixels drawn (${n})`, (await crew3d())[model] === 'stand' && n > 300, {state: await crew3d(), n});
            check(`${tag} cannons/${k}: only this gun on the model`, Object.entries(await crew3d()).filter(([kk, v]) => kk.startsWith('cannons_') && v !== 'hidden').length === 1);
            if (big) { await b.shot(join(PARTS, `cannons_${k}_3d.png`), await view3d()); await b.shot(join(PARTS, `cannons_${k}_draw.png`), await drawing()); }
        }
        // the other groups: every kind, each from its view
        const VIEW = {rifles: 'rail', cupolas: 'top', harpoon: 'nose'};
        for (const g of ['rifles', 'cupolas', 'harpoon']) {
            const kinds = await b.eval(`mtb.M.crew_options('${g}').filter(o => !o.empty).map(o => o.key)`);
            for (const k of kinds) {
                await pick(g, k);
                await button('#end_turn');
                await loaded(`${g}_${k}`);
                if (big && !weight[`${g}_${k}`]) weight[`${g}_${k}`] = {loaded: true};
                await b.eval(`mtb.viewer.view('${VIEW[g]}'); 1`); await sleep(500);
                const n = await diff(`${g}_${k}`);
                check(`${tag} ${g}/${k}: on the model, drawn (${n})`, (await crew3d())[`${g}_${k}`] === 'stand' && n > 100, {state: await crew3d(), n});
                if (big) await b.shot(join(PARTS, `${g}_${k}_3d.png`), await view3d());
            }
        }
        check(`${tag} the lookouts gone where the throwers stand`, (await crew3d()).lookouts_on !== 'stand');
        const sideNow = await b.eval('mtb.M.malakai_side()');
        check(`${tag} Malakai on his side, the riflemen's copy on his seat hidden`, (await crew3d())['malakai_' + sideNow] === 'stand'
            && await b.eval(`mtb.viewer.crewModels['rifles_' + mtb.M.crew('rifles')].getObjectByName('ap_crew_${sideNow}_1').visible === false`));
        // all filled: five views
        for (const v of ['all', 'port', 'top', 'below', 'nose']) { await b.eval(`mtb.viewer.view('${v}'); 1`); await sleep(500); if (big) await b.shot(join(PARTS, `all_${v}.png`), await view3d()); }
        await b.eval(`mtb.viewer.view('left'); 1`); await sleep(500);
        if (big) { await b.shot(join(PARTS, 'compare_3d.png'), await view3d()); await b.shot(join(PARTS, 'compare_draw.png'), await drawing()); }
        // F5: the same on the model
        const shownOf = s => JSON.stringify(Object.entries(s).filter(([, v]) => v !== 'hidden').sort());
        const before = shownOf(await crew3d());
        await b.reload();
        await b.until('document.body.dataset.ready === "1"', 30000);
        await sleep(4000);
        check(`${tag} F5: the same crew on the model`, shownOf(await crew3d()) === before, {before, after: shownOf(await crew3d())});
        // Malakai to the other side by his mark
        const other = sideNow === 'left' ? 'right' : 'left';
        await clickId('mtb_side_' + other);
        await loaded('malakai_' + other);
        check(`${tag} Malakai moves to the ${other} side on the model`, (await crew3d())['malakai_' + other] === 'stand' && (await crew3d())['malakai_' + sideNow] !== 'stand');
        // a hire on its way: the guns taken off, then a new gun ordered: the ghost of it on the empty port; the cupolas' place emptied to the lookouts
        await pick('cannons', await b.eval(`mtb.panel.view.data.groups.cannons.mount`));
        await button('#end_turn');
        await pick('cannons', 'organ');
        await loaded('cannons_organ');
        check(`${tag} a hire on its way: the gun's ghost in the port`, (await crew3d()).cannons_organ === 'ghost');
        await b.eval(`mtb.viewer.view('port'); 1`); await sleep(500);
        if (big) { await b.shot(join(PARTS, 'hiring_3d.png'), await view3d()); await b.shot(join(PARTS, 'hiring_draw.png'), await drawing()); }
        // the nests demolished: the throwers and the lookouts leave the model
        const nests = await b.eval(`mtb.panel.view.tree.filter(v => v.node.row.unlocks.some(u => u.group === 'cupolas' && u.option === 'empty')).sort((a, b) => b.node.row.line_level - a.node.row.line_level).map(v => mtb.panel.view.tree.indexOf(v))`);
        for (const i of nests) {
            await b.eval(`(() => { const p = mtb.panel.view.pan, v = mtb.panel.view.tree[${i}]; p.x = p.w / 2 - v.button.x - 37; p.y = p.h / 2 - v.button.y - 37; p.clamp(); })()`);
            await clickId('mtb_tree_node_' + i);
            await clickId('mtb_ship_demolish');
        }
        check(`${tag} the nests demolished: nobody in them on the model`, Object.entries(await crew3d()).every(([k, v]) => !(k.startsWith('cupolas_') || k === 'lookouts_on') || v === 'hidden'), await crew3d());
        // «К месту экипажа»: off by default; on, a click on a tag turns the view to its place
        const target = () => b.eval(`mtb.viewer.controls.target.toArray().map(v => Math.round(v * 10) / 10)`);
        await b.eval(`mtb.viewer.view('all'); 1`);
        const t0 = await target();
        await clickId('mtb_crew_area_harpoon'); await sleep(900);
        check(`${tag} off by default: a tag does not move the 3D`, JSON.stringify(await target()) === JSON.stringify(t0));
        await clickId('mtb_crew_area_harpoon');
        await button('#follow_crew');
        await clickId('mtb_crew_area_harpoon'); await sleep(1100);
        check(`${tag} on: a tag turns the 3D to its place (the harpoon's nose)`, JSON.stringify(await target()) === JSON.stringify([0, 15.4, 15.5]), await target());
        await clickId('mtb_crew_area_harpoon');
        check(`${tag} the console is clean`, !b.errors.length && !b.dialogs.length, [...b.errors, ...b.dialogs]);
    } catch (e) {
        check(`${tag} the walk ran through`, false, e.message);
        await b.shot(join(SHOTS, `walk_error_${scale}.png`)).catch(() => {});
    } finally {
        await b.close();
        await sleep(1500);
    }
}

// The 3D side's bar at the window's usual widths: the buttons of the views and the ship's line do not lie on one another nor on the model, nothing cut,
// no text under 11 px. Pictures groups3d/panel_<width>.png.
async function panelBar() {
    const b = await launch({width: 1280, height: 900, port: 9399, profile: join(tmpdir(), 'mtb_3d_profile_bar')});
    try {
        await b.open(URL0 + '?mode=game');
        await b.until('!!(window.mtb && mtb.M && mtb.panel)', 15000);
        await b.eval('localStorage.clear()');
        await b.reload();
        await b.until('document.body.dataset.ready === "1"', 30000);
        const r = await debugRect(b, '#build_all'); await b.click(r.x, r.y); await sleep(800);
        for (const w of [1024, 1280, 1600, 1920]) {
            await b.size(w, 900); await sleep(500);
            const m = await b.eval(`(() => {
                const box = e => e.getBoundingClientRect(), els = [...document.querySelectorAll('#tools3d button'), document.getElementById('hull')].filter(e => e.offsetParent !== null);
                const rs = els.map(e => ({id: e.id, r: box(e), cut: e.scrollWidth > e.clientWidth + 1 && e.id !== 'hull', px: parseFloat(getComputedStyle(e).fontSize)}));
                const meet = [];
                for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) { const a = rs[i].r, c = rs[j].r; if (a.left < c.right - 0.5 && c.left < a.right - 0.5 && a.top < c.bottom - 0.5 && c.top < a.bottom - 0.5) meet.push(rs[i].id + '/' + rs[j].id); }
                const bar = box(document.getElementById('tools3d')), model = box(document.querySelector('#view3d canvas')), right = box(document.getElementById('right'));
                const hull = document.getElementById('hull');
                return {meet, cut: rs.filter(x => x.cut).map(x => x.id), small: rs.filter(x => x.px < 11).map(x => x.id), barBottom: bar.bottom, modelTop: model.top,
                        inside: rs.every(x => x.r.left >= right.left - 0.5 && x.r.right <= right.right + 0.5), hull: hull.textContent, title: hull.title.length, rows: new Set(rs.map(x => Math.round(x.r.top))).size};
            })()`);
            check(`bar at ${w}: nothing meets, nothing cut, text 11 px or more, all inside, the model under the bar`, !m.meet.length && !m.cut.length && !m.small.length && m.inside && m.modelTop >= m.barBottom - 0.5, m);
            check(`bar at ${w}: the ship's line short, the list in its tooltip`, m.hull.length <= 40 && m.title > 40, m);
            const rr = await b.rect('#right');
            await b.shot(join(SHOTS, `panel_${w}.png`), {x: rr.l, y: rr.t - 41, width: rr.w, height: Math.min(rr.h + 41, 900)});
        }
        check('bar: the console is clean', !b.errors.length, b.errors);
    } catch (e) {
        check('bar: the check ran through', false, e.message);
    } finally {
        await b.close();
        await sleep(1500);
    }
}

// The page's own bar in both modes at the same widths: its groups wrap whole, nothing lies on anything, nothing cut, the page starts under it, the
// feed shortened with "…"; narrow, the debug buttons fold into «Отладка ▾» (its dropdown checked open too). Pictures groups3d/topbar_<width>_<mode>.png.
async function topBar() {
    const b = await launch({width: 1280, height: 900, port: 9398, profile: join(tmpdir(), 'mtb_3d_profile_top')});
    try {
        await b.open(URL0 + '?mode=game');
        await b.until('!!(window.mtb && mtb.M && mtb.panel)', 15000);
        await b.eval('localStorage.clear()');
        await b.reload();
        await b.until('document.body.dataset.ready === "1"', 30000);
        // a long line in the feed, as after a few turns
        for (let i = 0; i < 3; i++) { const r = await b.rect('#end_turn'); await b.click(r.x, r.y); await sleep(200); }
        const measure = () => b.eval(`(() => {
            const vis = e => e.offsetParent !== null && getComputedStyle(e).visibility !== 'hidden' && e.getBoundingClientRect().width > 0;
            const bar = document.getElementById('bar'), br = bar.getBoundingClientRect();
            const leaves = [...bar.querySelectorAll('button, input, .tag, #turn, #cx_save, #log li:first-child, .debug-gold')].filter(vis).filter(e => !e.closest('#debug_tools') || getComputedStyle(document.getElementById('debug_tools')).position !== 'absolute');
            const flat = leaves.filter(e => !leaves.some(o => o !== e && e.contains(o)));
            const rs = flat.map(e => ({id: e.id || e.className || e.tagName, r: e.getBoundingClientRect(), cut: e.tagName !== 'LI' && e.tagName !== 'INPUT' && e.scrollWidth > e.clientWidth + 1}));
            const meet = [];
            for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) { const a = rs[i].r, c = rs[j].r; if (a.left < c.right - 0.5 && c.left < a.right - 0.5 && a.top < c.bottom - 0.5 && c.top < a.bottom - 0.5) meet.push(rs[i].id + '/' + rs[j].id); }
            const page = document.body.dataset.mode === 'constructor' ? document.getElementById('constructor') : document.querySelector('main');
            const log = document.getElementById('log'), li = log.querySelector('li');
            return {meet, cut: rs.filter(x => x.cut).map(x => x.id), outside: rs.filter(x => x.r.right > window.innerWidth + 0.5 || x.r.left < -0.5).map(x => x.id),
                    pageTop: page.getBoundingClientRect().top, barBottom: br.bottom, rows: new Set(rs.map(x => Math.round(x.r.top / 4))).size,
                    feedFits: !li || !vis(log) || li.getBoundingClientRect().right <= log.getBoundingClientRect().right + 0.5, small: rs.filter(x => parseFloat(getComputedStyle(document.getElementById(x.id) || bar).fontSize) < 11).length};
        })()`);
        for (const mode of ['game', 'constructor']) {
            await b.eval(`mtb.setMode('${mode}'); 1`); await sleep(400);
            for (const w of [1024, 1280, 1600, 1920]) {
                await b.size(w, 900); await sleep(400);
                const m = await measure();
                check(`top bar, ${mode}, ${w}: nothing meets, nothing cut or outside, the page under the bar`, !m.meet.length && !m.cut.length && !m.outside.length && m.pageTop >= m.barBottom - 0.5 && m.feedFits, m);
                await b.shot(join(SHOTS, `topbar_${w}_${mode}.png`), {x: 0, y: 0, width: w, height: Math.min(900, Math.round(m.barBottom) + 120)});
                if (mode === 'game' && w <= 1280) {
                    const t = await b.rect('#debug_toggle');
                    check(`top bar, ${w}: the debug folded into «Отладка ▾»`, !!t && t.w > 0);
                    await b.click(t.x, t.y); await sleep(200);
                    const d = await b.eval(`(() => { const items = [...document.querySelectorAll('#debug_tools button, #debug_tools input')].map(e => e.getBoundingClientRect()); const meet = items.some((a, i) => items.some((c, j) => j > i && a.left < c.right - 0.5 && c.left < a.right - 0.5 && a.top < c.bottom - 0.5 && c.top < a.bottom - 0.5)); return {n: items.length, meet, inside: items.every(r => r.right <= window.innerWidth + 0.5 && r.width > 0)}; })()`);
                    check(`top bar, ${w}: the debug dropdown opens, its buttons apart and inside`, d.n >= 8 && !d.meet && d.inside, d);
                    await b.shot(join(SHOTS, `topbar_${w}_game_debug.png`), {x: 0, y: 0, width: w, height: 260});
                    await b.click(Math.round(w * 0.3), 600); await sleep(200);
                }
            }
        }
        check('top bar: the console is clean', !b.errors.length, b.errors);
    } catch (e) {
        check('top bar: the check ran through', false, e.message);
    } finally {
        await b.close();
        await sleep(1500);
    }
}

try {
    await topBar();
    await panelBar();
    if (!process.env.BAR_ONLY) for (const s of [0.6, 1]) await walk(s);
} finally {
    server.kill();
}
if (!process.env.BAR_ONLY) writeFileSync(join(SHOTS, 'weight.json'), JSON.stringify(weight, null, 1));
// the sheets: the 3D beside the drawing
const py = String.raw`
import sys, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
S = Path(sys.argv[1]); P = S / 'parts'
font = ImageFont.truetype('arial.ttf', 16)
def row(pairs, out, h=520):
    ims = []
    for title, files in pairs:
        cells = [Image.open(P / f).convert('RGB') for f in files if (P / f).exists()]
        cells = [c.resize((round(c.width * h / c.height), h)) for c in cells]
        w = sum(c.width for c in cells) + 6 * max(0, len(cells) - 1)
        im = Image.new('RGB', (max(w, 10), h + 26), (24, 21, 17)); d = ImageDraw.Draw(im); d.text((6, 4), title, fill=(235, 189, 124), font=font)
        x = 0
        for c in cells: im.paste(c, (x, 26)); x += c.width + 6
        ims.append(im)
    W = sum(i.width for i in ims) + 10 * len(ims); out_im = Image.new('RGB', (W, h + 26), (24, 21, 17)); x = 0
    for i in ims: out_im.paste(i, (x, 0)); x += i.width + 10
    out_im.save(S / out)
for k in ['stock', 'flaming', 'organ', 'clatter', 'flame']:
    row([(f'cannons {k}: чертёж | 3D, вид на порт', [f'cannons_{k}_draw.png', f'cannons_{k}_3d.png'])], f'cannons_{k}.png', 420)
row([(v, [f'all_{v}.png']) for v in ['all', 'port', 'top', 'below', 'nose']], 'all_filled_views.png', 520)
row([('в найме: чертёж | 3D (призрак)', ['hiring_draw.png', 'hiring_3d.png'])], 'hiring_state.png', 420)
row([('чертёж | 3D, левый борт', ['compare_draw.png', 'compare_3d.png'])], 'compare_blueprint_3d.png', 520)
`;
const r = spawnSync('py', ['-3.10', '-c', py, SHOTS], {encoding: 'utf-8'});
check('the sheets made', r.status === 0, r.stderr);
console.log('weight', JSON.stringify(weight));
console.log(`failed: ${failed}`);
process.exit(failed ? 1 : 0);
