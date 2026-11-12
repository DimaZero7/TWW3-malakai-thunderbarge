// The crew groups walked as the player does, with the mouse, in a headless Chrome (tools/tests/cdp.mjs), at the page's scale on the user's screen
// (0.6) and at 1:  node --experimental-websocket tools/tests/crew_groups_walk.mjs
// It starts a server of its own (tools/web_serve.py --port 8767 --tree <a copy in the temp folder>): the author's web/data/tree_design.json is
// never read by the page nor written. For each scale: «Построить всё»; for the guns, the bombs and the nests each: the empty place, the choice opened
// by its tag, a kind ordered, a double click, another kind instead, the sketch; the riflemen ordered too, so all four groups wait at once; F5 in the
// middle of the orders; the turn; a change of kind; taking a crew off; a building with a crew demolished; short of gold. The console and the pictures
// are checked. Pictures to build/web/shots/groups/. Prints a line a check; exit 1 on any failure.
import {readFileSync, writeFileSync, mkdirSync, rmSync} from 'node:fs';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {tmpdir} from 'node:os';
import {launch, sleep} from './cdp.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const DATA = join(tmpdir(), 'mtb_groups_tree');
rmSync(DATA, {recursive: true, force: true});
mkdirSync(DATA, {recursive: true});
const FILE = join(DATA, 'tree_design.json');
writeFileSync(FILE, readFileSync(join(ROOT, 'web/data/tree_design.json')));
const PORT = 8767, URL0 = `http://127.0.0.1:${PORT}/`;
const server = spawn('py', ['-3.14', join(ROOT, 'tools/web_serve.py'), '--port', String(PORT), '--tree', FILE], {stdio: 'ignore'});
for (let i = 0; i < 50; i++) { if (await fetch(URL0 + 'data/tree_design.json').then(r => r.ok).catch(() => false)) break; await sleep(200); }
const SHOTS = join(ROOT, 'build/web/shots/groups');
mkdirSync(SHOTS, {recursive: true});
let failed = 0;
const check = (name, ok, extra = '') => { if (!ok) failed++; console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok || !extra ? '' : '  ' + (typeof extra === 'string' ? extra : JSON.stringify(extra)))); return ok; };
const GROUPS = ['cannons', 'bombs', 'cupolas', 'harpoon'];
const EMPTY = g => `(mtb.panel.view.data.groups['${g}'].mount || mtb.panel.view.data.groups['${g}'].start)`;

async function walk(scale) {
    // the left side is 62 % of the window, the root 1600 x 900 fits it: this window gives the scale
    const W = Math.round(1600 * scale / 0.62) + 2, H = Math.max(950, Math.round(900 * scale) + 60);
    const b = await launch({width: W, height: H, port: 9360 + Math.round(scale * 10), profile: join(tmpdir(), 'mtb_groups_profile_' + String(scale).replace('.', '_'))});
    await b.size(W, H);
    const tag = `[${scale}]`;
    try {
        await b.open(URL0 + '?mode=game');
        await b.until('!!(window.mtb && mtb.M && mtb.panel)', 15000);
        await b.eval('localStorage.clear()');
        await b.reload();
        await b.until('!!(window.mtb && mtb.M && mtb.panel)', 15000);
        const k = await b.eval(`document.querySelector('#screen .root').getBoundingClientRect().width / 1600`);
        check(`${tag} the page's scale is ${scale}`, Math.abs(k - scale) < 0.02, k);
        const comp = id => b.eval(`(() => { const e = [...document.querySelectorAll('#screen [data-id="${id}"]')].find(x => x.offsetParent !== null && getComputedStyle(x).visibility !== 'hidden'); if (!e) return null; const r = e.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2, l: r.left, t: r.top, w: r.width, h: r.height}; })()`);
        const shown = id => comp(id).then(r => !!r);
        const clickId = async id => { const r = await comp(id); if (!r) throw new Error('not on the screen: ' + id); await b.click(r.x, r.y); await sleep(150); return r; };
        const button = async sel => { const r = await b.rect(sel); await b.click(r.x, r.y); await sleep(250); };
        const gold = () => b.eval('mtb.game.treasury()');
        const hire = (g, o) => b.eval(`mtb.M.crew_options('${g}').find(x => x.key === '${o}').hire`);
        const upkeep = (g, o) => b.eval(`mtb.M.crew_options('${g}').find(x => x.key === '${o}').upkeep`);
        const layerShown = name => b.eval(`(() => { const e = [...document.querySelectorAll('#screen [data-id="${name}"]')][0]; return !!e && e.offsetParent !== null; })()`);
        const pickOpen = () => b.eval(`[...document.querySelectorAll('#screen [data-id^="mtb_crew_pick_"]')].filter(e => e.offsetParent !== null).map(e => e.dataset.id)`);
        const images = () => b.eval(`(() => { const bad = [...document.querySelectorAll('#screen img')].filter(i => i.offsetParent !== null && (!i.complete || !i.naturalWidth)).map(i => i.src.split('/').pop()); return bad; })()`);
        const screen = async () => { const r = await b.rect('#screen .root'); return {x: r.l, y: r.t, width: r.w, height: r.h}; };
        const drawing = async () => { const r = await comp('scheme'); return {x: r.l, y: r.t, width: r.w, height: r.h}; };
        const settle = async () => { await sleep(300); await b.until(`[...document.querySelectorAll('#screen img')].filter(i => i.offsetParent !== null).every(i => i.complete)`, 15000).catch(() => {}); await sleep(250); };

        await button('#build_all');
        await settle();
        let ledger = await gold();
        for (const g of GROUPS) {
            check(`${tag} ${g}: the place is on the drawing after «Построить всё»`, await shown('mtb_crew_area_' + g));
            check(`${tag} ${g}: empty, the tag's plus`, await layerShown(`crew_${g}_tag_plus`) && await b.eval(`mtb.M.crew('${g}')`) === await b.eval(EMPTY(g)));
        }
        check(`${tag} the lookouts stand in the empty nests`, await layerShown('lookouts_ink'));
        await b.shot(join(SHOTS, `blueprint_all_empty_${scale}.png`), await drawing());
        if (scale === 0.6) await b.shot(join(SHOTS, 'blueprint_all_empty.png'), await drawing());

        // each group: open by the tag, order the first kind, a double click, another kind instead
        const chosen = {};
        for (const g of GROUPS) {
            await clickId('mtb_crew_area_' + g);
            check(`${tag} ${g}: its choice opens, one window only`, JSON.stringify(await pickOpen()) === JSON.stringify(['mtb_crew_pick_' + g]), await pickOpen());
            // the window's head and its line of the upkeep: apart, neither cut
            const hf = await b.eval(`(() => { const w = [...document.querySelectorAll('#screen [data-id="mtb_crew_pick_${g}"]')][0]; const h = w.querySelector('[data-id="pick_head"]'), f = w.querySelector('[data-id="pick_foot"]');
                const r = e => e.getBoundingClientRect(), a = r(h.querySelector('.t')), c = r(f.querySelector('.t')), rng = e => { const x = document.createRange(); x.selectNodeContents(e.querySelector('.t')); return x.getBoundingClientRect(); };
                const ta = rng(h), tc = rng(f);
                return {apart: ta.bottom <= tc.top || tc.bottom <= ta.top || ta.right <= tc.left || tc.right <= ta.left, headCut: ta.right > a.right + 0.5 || ta.left < a.left - 0.5, footCut: tc.right > c.right + 0.5 || tc.left < c.left - 0.5, foot: f.textContent}; })()`);
            check(`${tag} ${g}: the head and the upkeep line apart, neither cut`, hf.apart && !hf.headCut && !hf.footCut, hf);
            const kinds = await b.eval(`mtb.M.crew_options('${g}').filter(o => !o.empty && o.unlocked).map(o => o.key)`);
            check(`${tag} ${g}: every kind open after «Построить всё»`, kinds.length === await b.eval(`mtb.M.crew_options('${g}').filter(o => !o.empty).length`), kinds);
            const first = kinds[0], last = kinds[kinds.length - 1];
            // the unit's panel under the mouse
            const card = await comp(`mtb_crew_card_pick_${g}:${last}`);
            await b.move(card.x, card.y, 4); await sleep(400);
            const info = await comp(`crew_pick_info_${g}_${last}`);
            check(`${tag} ${g}: the unit's panel shows beside the choice, not over the card`, !!info && (info.l > card.x + 30 || info.l + info.w < card.x - 30 || info.t + info.h < card.t || info.t > card.t + card.h), info);
            const infoText = await b.eval(`document.querySelector('#screen [data-id="crew_pick_info_${g}_${last}"]').textContent`);
            check(`${tag} ${g}: the unit's panel has no broken number`, !/NaN|undefined|null/.test(infoText), infoText.slice(0, 200));
            check(`${tag} ${g}: the ammunition in volleys a seat (or the harpoon's shots)`, g === 'harpoon' ? /Выстрелов за бой/.test(infoText) : /залп/.test(infoText), infoText.slice(0, 300));
            const pk = await comp('mtb_crew_pick_' + g);
            const z = await b.eval(`[getComputedStyle(document.querySelector('#screen [data-id="crew_pick_info_${g}_${last}"]')).zIndex, getComputedStyle(document.querySelector('#screen [data-id="mtb_crew_pick_${g}"]')).zIndex]`);
            check(`${tag} ${g}: the panel under the mouse is over the window of the click`, Number(z[0]) > Number(z[1]), z);
            if (scale === 0.6) {
                await b.shot(join(SHOTS, `pick_${g}.png`), await screen());
                await b.shot(join(SHOTS, `unit_panel_${g}.png`), {x: Math.min(pk.l, info.l) - 6, y: Math.min(pk.t, info.t) - 6, width: Math.max(pk.l + pk.w, info.l + info.w) - Math.min(pk.l, info.l) + 12, height: Math.max(pk.t + pk.h, info.t + info.h) - Math.min(pk.t, info.t) + 12});
            }
            await clickId(`mtb_crew_card_pick_${g}:${first}`);
            ledger -= await hire(g, first);
            check(`${tag} ${g}: «${first}» ordered, its hire taken`, await b.eval(`mtb.M.crew_order('${g}')`) === first && await gold() === ledger, {gold: await gold(), ledger});
            const c1 = await comp(`mtb_crew_card_pick_${g}:${first}`);
            await b.dblclick(c1.x, c1.y); await sleep(200);
            check(`${tag} ${g}: a double click changes nothing`, await b.eval(`mtb.M.crew_order('${g}')`) === first && await gold() === ledger);
            if (last !== first) {
                await clickId(`mtb_crew_card_pick_${g}:${last}`);
                ledger += await hire(g, first) - await hire(g, last);
                check(`${tag} ${g}: «${last}» instead, the gold follows the order`, await b.eval(`mtb.M.crew_order('${g}')`) === last && await gold() === ledger);
            }
            chosen[g] = last;
            check(`${tag} ${g}: the sketch of the hire on the drawing, the tag's hourglass`, await layerShown(`crew_${g}_${last}_sketch`) && await layerShown(`crew_${g}_tag_wait`));
            await clickId('mtb_crew_close_' + g);
            check(`${tag} ${g}: the cross closes the window`, !(await pickOpen()).length);
        }
        check(`${tag} the lookouts step aside for the throwers' sketch`, !(await layerShown('lookouts_ink')));
        // a second tag while a window is open: that window closes, the other opens
        await clickId('mtb_crew_area_bombs');
        await clickId('mtb_crew_area_cannons');
        check(`${tag} another group's tag: one window open, the new one`, JSON.stringify(await pickOpen()) === JSON.stringify(['mtb_crew_pick_cannons']), await pickOpen());
        await clickId('mtb_crew_area_cannons');
        // the riflemen too: four groups wait at once
        await clickId('mtb_crew_area_rifles');
        await clickId('mtb_crew_card_pick_rifles:pirates');
        ledger -= await hire('rifles', 'pirates');
        await clickId('mtb_crew_area_rifles');
        check(`${tag} four groups ordered at once`, (await b.eval(`['rifles','cannons','bombs','cupolas'].map(g => mtb.M.crew_order(g))`)).every(Boolean) && await gold() === ledger);
        await settle();
        await b.shot(join(SHOTS, `hiring_${scale}.png`), await drawing());
        // F5 in the middle of the orders
        await b.reload();
        await b.until('!!(window.mtb && mtb.M && mtb.panel)', 15000);
        await settle();
        check(`${tag} F5: the orders, the treasury and the sketches are back`, (await b.eval(`${JSON.stringify(GROUPS)}.map(g => mtb.M.crew_order(g))`)).join() === GROUPS.map(g => chosen[g]).join() && await gold() === ledger
            && await layerShown(`crew_bombs_${chosen.bombs}_sketch`));
        check(`${tag} F5: the hints stay off for the groups chosen`, !(await layerShown('crew_glow')) || await b.eval(`['cannons','bombs','cupolas','rifles'].every(g => !mtb.M.crew_hint(g))`));
        // the turn
        await button('#end_turn');
        await settle();
        ledger -= (await Promise.all(GROUPS.map(g => upkeep(g, chosen[g])))).reduce((a, x) => a + x, 0) + await upkeep('rifles', 'pirates');
        for (const g of GROUPS) check(`${tag} ${g}: after the turn «${chosen[g]}» stands in ink, the tag's arrows`, await b.eval(`mtb.M.crew('${g}')`) === chosen[g] && await layerShown(`crew_${g}_${chosen[g]}`) && await layerShown(`crew_${g}_tag_swap`));
        check(`${tag} the upkeep taken at the turn`, await gold() === ledger, {gold: await gold(), ledger});
        await b.shot(join(SHOTS, `blueprint_all_filled_${scale}.png`), await drawing());
        if (scale === 0.6) await b.shot(join(SHOTS, 'blueprint_all_filled.png'), await drawing());
        // a change of kind: the guns' first kind; the bombs taken off
        const gunFirst = await b.eval(`mtb.M.crew_options('cannons').filter(o => !o.empty)[0].key`);
        await clickId('mtb_crew_area_cannons');
        await clickId(`mtb_crew_card_pick_cannons:${gunFirst}`);
        ledger -= await hire('cannons', gunFirst);
        check(`${tag} a change of kind: the gun that stands stays in ink until the turn`, await layerShown(`crew_cannons_${chosen.cannons}`) && await layerShown('crew_cannons_tag_wait'));
        await clickId('mtb_crew_area_bombs');
        await clickId(`mtb_crew_card_pick_bombs:${await b.eval(`mtb.panel.view.data.groups.bombs.mount`)}`);
        await clickId('mtb_crew_area_bombs');
        await button('#end_turn');
        await settle();
        ledger -= await upkeep('cannons', gunFirst) + await upkeep('cupolas', chosen.cupolas) + await upkeep('rifles', 'pirates') + await upkeep('harpoon', chosen.harpoon);
        check(`${tag} after the turn: the new gun, empty bombs' racks`, await b.eval(`mtb.M.crew('cannons')`) === gunFirst && await layerShown(`crew_cannons_${gunFirst}`)
            && await layerShown('crew_bombs_empty') && await gold() === ledger, {gold: await gold(), ledger});
        // a building with a crew demolished: the nests' line from the top (the throwers stand) down to nothing
        const nests = await b.eval(`mtb.panel.view.tree.filter(v => v.node.row.unlocks.some(u => u.group === 'cupolas' && u.option === 'empty')).sort((a, b) => b.node.row.line_level - a.node.row.line_level).map(v => mtb.panel.view.tree.indexOf(v))`);
        for (const i of nests) {
            // the node into the tree's window (a pan of the view, as a drag would), then a click on it and on «Снести»
            await b.eval(`(() => { const p = mtb.panel.view.pan, v = mtb.panel.view.tree[${i}]; p.x = p.w / 2 - v.button.x - 37; p.y = p.h / 2 - v.button.y - 37; p.clamp(); })()`);
            await clickId('mtb_tree_node_' + i);
            await clickId('mtb_ship_demolish');
        }
        check(`${tag} the nests demolished: their place, its crew and the lookouts are gone, nothing paid back`, !(await shown('mtb_crew_area_cupolas')) && !(await layerShown('lookouts_ink'))
            && await b.eval(`mtb.M.crew('cupolas')`) === 'empty' && await gold() === ledger, {msg: await b.eval('mtb.M.message()'), gold: await gold(), ledger});
        // short of gold
        await button('.gold_quick[data-gold="0"]');
        ledger = 0;
        await clickId('mtb_crew_area_bombs');
        const want = await b.eval(`mtb.M.crew_options('bombs').filter(o => !o.empty)[0].key`);
        const red = await b.eval(`[...document.querySelectorAll('#screen [data-id="mtb_crew_card_pick_bombs:${want}"] [data-id="RecruitmentCost"]')][0].innerHTML`);
        await clickId(`mtb_crew_card_pick_bombs:${want}`);
        check(`${tag} short of gold: the cost red, no hire`, /col_red/.test(red) && await b.eval(`mtb.M.crew_order('bombs')`) === null && await gold() === 0, red);
        if (scale === 0.6) {
            const card = await comp(`mtb_crew_card_pick_bombs:${want}`);
            await b.move(card.x + 3, card.y, 2); await sleep(400);
            await b.shot(join(SHOTS, 'poor_bombs.png'), await screen());
        }
        await clickId('mtb_crew_close_bombs');
        const bad = await images();
        check(`${tag} every picture on the screen loaded`, !bad.length, bad);
        check(`${tag} the console is clean`, !b.errors.length && !b.dialogs.length, [...b.errors, ...b.dialogs]);
    } catch (e) {
        check(`${tag} the walk ran through`, false, e.message);
        await b.shot(join(SHOTS, `walk_error_${scale}.png`)).catch(() => {});
    } finally {
        await b.close();
        await sleep(1500);
    }
}

try {
    for (const s of [0.6, 1]) await walk(s);
} finally {
    server.kill();
}
console.log(`failed: ${failed}`);
process.exit(failed ? 1 : 0);
