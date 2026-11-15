// The page's screen as data, for the port of its drawing to the game (docs/design/port-to-game.md, 4.2 «Экран без игры»):
//   node tools/tests/ui_dump_export.mjs [--only NAME]        (a Node with a global WebSocket: C:/Users/dima/AppData/Local/nvm/v25.2.1/node.exe)
// Its own server (tools/web_serve.py, port 8775 or MTB_PORT, a copy of web/data/tree_design.json in the temp folder) and a headless Chrome (port 9490 or
// MTB_CDP_PORT). The page in «Игра» at the reference size (root 1600 x 900, panel 1560 x 870), the page's timers stopped (the glows' phases and the
// construction's clock-wipe stay at their first frame), each reference state made by the page's own model as clicks would make it, then written and
// read back by a reload (the game's save and load), then the view acted on (a tab, a crew's choice, the mouse over a slot or a card), then
// web/js/gameui.js dump(): build/ui_dump/<state>.json = {name, about, snapshot (the saved state, the page's keys), actions, components, measures}.
// tools/ui_layout_check.py builds the same states with the mod's Lua (src/tww3_mtb_ship_ui.lua) and compares.
import {readFileSync, writeFileSync, mkdirSync, rmSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import {tmpdir} from 'node:os';
import {launch, startServer, sleep} from './cdp.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const OUT = join(ROOT, 'build/ui_dump');
const only = process.argv.includes('--only') ? process.argv[process.argv.indexOf('--only') + 1] : null;

// The campaigns, made by the page's model (web/js/barge_buildings.js, game_sim.js) as the player's clicks would make them. Short keys: the tree's nodes.
const CAMPAIGNS = {
    fresh: {about: 'a new campaign: nothing built, 6000 gold, no development points', steps: []},
    early: {about: 'the first hull ordered and built by the turn: no development point yet (its growth starts with the next turn), the next hull short of points',
            steps: [['order', 'airship_hull_1'], ['end_turn']]},
    mid: {about: 'the barge and the first buildings stand; the riflemen in hire came aboard with the turn; one building ordered, a crew order waiting, gold short for most',
          steps: [['points', 6], ['build', 'airship_hull_3'], ['build', 'beer_hall_1'], ['build', 'infantry_workshop_1'], ['build', 'crew_weapons_1'], ['build', 'mtb_nest_1'],
                  ['build', 'engineering_workshop_1'], ['gold', 3000], ['crew', 'rifles', 'quarrellers'], ['order', 'support_radius_1'], ['end_turn'],
                  ['order', 'cargo_hold_1'], ['gold', 1200], ['crew', 'rifles', 'pirates']]},
    dismantling: {about: 'mid, then the nests demolished: it stands, being dismantled, until the turn ends',
                  steps: 'mid', more: [['demolish', 'mtb_nest_1']]},
    asked: {about: 'a two-turn building ordered a turn ago; the game asks before such a cancel (sim ask_cancel)', sim: {ask_cancel: true},
            steps: [['points', 6], ['build', 'airship_hull_3'], ['build', 'beer_hall_1'], ['build', 'engineering_workshop_1'], ['gold', 6000],
                    ['order', 'engines_1'], ['end_turn']]},
    pending: {about: 'a new campaign; the game applies a command a moment later (sim async): a click orders, the order waits for the game', sim: {async: true}, steps: []},
    pending_cancel: {about: 'the first hull ordered and taken; the game applies a command a moment later (sim async): a click cancels, the cancel waits for the game',
                     sim: {async: true}, steps: [['order', 'airship_hull_1']]},
    // the session of 15.11 (run 20261115-030121): the nests ordered, the beer hall's line dismantled, the turn ended: a turn report of several
    // sentences that ends with what the player waits for (the foot row's two lines, M.foot_tail)
    report: {about: 'the hull II and the beer hall II stand; the pirates hired, the nests ordered with the last point; the turn ended',
             steps: [['points', 1], ['build', 'airship_hull_2'], ['build', 'beer_hall_2'], ['gold', 16000], ['crew', 'rifles', 'pirates'], ['order', 'mtb_nest_1'], ['end_turn']]},
    // the crew's bonuses the battle does not apply yet (stage 5): the riflemen with the dummies (accuracy applied; range and reload not yet) and the
    // cargo hatch (ammunition: all crews' x2 applied); the bombs with the torpedo gallery (their own +30 not yet: the total and the battle's)
    bonus: {about: 'the pirates and the bombs aboard; the dummies, the cargo hatch and the torpedo gallery stand: bonuses the battle applies, does not yet, and both',
            steps: [['points', 6], ['build', 'airship_hull_3'], ['build', 'beer_hall_1'], ['build', 'crew_weapons_1'], ['build', 'cargo_hold_3'],
                    ['build', 'mtb_hatches_1'], ['build', 'mtb_torpedoes_1'], ['gold', 6000], ['crew', 'rifles', 'pirates'], ['crew', 'bombs', 'stock'], ['end_turn']]},
    full: {about: 'every building of the tree stands, a crew at every place, Malakai on the right side',
           steps: [['build_all'], ['gold', 20000], ['crew', 'rifles', 'thunderers'], ['crew', 'cannons', 'organ'], ['crew', 'bombs', 'fire'], ['crew', 'cupolas', 'axes'],
                   ['crew', 'harpoon', 'on'], ['end_turn'], ['side', 'right']]},
};
// The states: a campaign and what is done to the view after the load. click / hover name a component by its id (slot: a node's slot by its short key).
const STATES = [
    ['fresh_tree', 'fresh', []],
    ['fresh_ship', 'fresh', [['click', 'mtb_tab_ship']]],
    ['fresh_tree_info', 'fresh', [['hover', {slot: 'airship_hull_1'}]]],
    ['mid_tree', 'mid', []],
    ['mid_tree_info', 'mid', [['hover', {slot: 'beer_hall_2'}]]],
    ['mid_tree_unit', 'mid', [['hover', 'mtb_crew_card_beer_hall_1_pirates']]],
    ['mid_tree_army', 'mid', [['hover', 'mtb_army_card_beer_hall_2_wh_main_dwf_inf_slayers']]],
    ['mid_tree_raze', 'mid', [['click', {slot: 'engineering_workshop_1'}]]],
    ['mid_ship', 'mid', [['click', 'mtb_tab_ship']]],
    ['mid_ship_pick', 'mid', [['click', 'mtb_tab_ship'], ['click', 'mtb_crew_area_rifles']]],
    ['early_tree', 'early', []],
    ['early_tree_short', 'early', [['hover', {slot: 'airship_hull_2'}]]],
    ['dismantling_tree', 'dismantling', [['click', {slot: 'mtb_nest_1'}], ['hover', {slot: 'mtb_nest_1'}]]],
    ['asked_tree', 'asked', [['click', {slot: 'engines_1'}], ['hover', {slot: 'engines_1'}]]],
    // a command the game has not applied yet (st.pending): the window's instruction line is the model's words for the wait (M.pending_note)
    ['pending_order_tree', 'pending', [['click', {slot: 'airship_hull_1'}], ['hover', {slot: 'airship_hull_1'}]]],
    ['pending_cancel_tree', 'pending_cancel', [['click', {slot: 'airship_hull_1'}], ['hover', {slot: 'airship_hull_1'}]]],
    // the window of a slot of the rightmost column: left of the slot, inside the panel (run 20261115-030121, ss_info_corner)
    ['mid_tree_corner', 'mid', [['show', {slot: 'engines_1'}], ['hover', {slot: 'engines_1'}]]],
    // a place a dismantle closes at the turn's end: its tag on the drawing says so (M.place_closing)
    ['dismantling_ship', 'dismantling', [['click', 'mtb_tab_ship']]],
    // the turn's report in the foot row: two lines, what the player waits for whole on the second
    ['report_tree', 'report', []],
    // P4: a unit panel with bonus lines the battle applies, does not apply yet (grey) and both (the total and the battle's); a building window with them
    ['bonus_tree_unit', 'bonus', [['hover', 'mtb_crew_card_beer_hall_1_pirates']]],
    ['bonus_tree_info', 'bonus', [['hover', {slot: 'crew_weapons_1'}]]],
    ['bonus_ship_pick_unit', 'bonus', [['click', 'mtb_tab_ship'], ['click', 'mtb_crew_area_bombs'], ['hover', 'mtb_crew_card_pick_bombs:stock']]],
    ['full_tree', 'full', []],
    // a player scrolls a slot into the tree's window before the mouse is on it (show: the tree moved as a click on the slot moves it, pan.show)
    ['full_tree_info', 'full', [['show', {slot: 'mtb_guns_3'}], ['hover', {slot: 'mtb_guns_3'}]]],
    ['full_ship', 'full', [['click', 'mtb_tab_ship']]],
    ['full_ship_pick_unit', 'full', [['click', 'mtb_tab_ship'], ['click', 'mtb_crew_area_cannons'], ['hover', 'mtb_crew_card_pick_cannons:organ']]],
];

mkdirSync(OUT, {recursive: true});
const DATA = join(tmpdir(), 'mtb_ui_dump');
rmSync(DATA, {recursive: true, force: true});
mkdirSync(DATA, {recursive: true});
const FILE = join(DATA, 'tree_design.json');
writeFileSync(FILE, readFileSync(join(ROOT, 'web/data/tree_design.json')));
const server = await startServer({root: ROOT, port: 8775, tree: FILE});
const b = await launch({width: 1600, height: 900, port: Number(process.env.MTB_CDP_PORT || 9490), profile: join(tmpdir(), 'mtb_ui_dump_profile')}).catch(async e => { await server.stop(); throw e; });
let failed = 0;
try {
    // the page's timers stopped before any of its scripts runs: what the dump sees is the first frame of every timer
    await b.send('Page.addScriptToEvaluateOnNewDocument', {source: 'window.setInterval = () => 0; window.MTB_REPORT_READ_MS = 0;'});      // nor the turn's report read by time (main.js)
    await b.size(1600, 900);
    const URL0 = server.url + '?mode=game';
    const ready = () => b.until('!!(window.mtb && mtb.M && mtb.panel && mtb.root && mtb.root.pictures)', 20000).catch(e => { throw new Error(e.message + ' | the page: ' + b.errors.join(' | ').slice(0, 1500)); });
    const made = {};
    for (const [name, campaign, actions] of STATES) {
        if (only && !name.includes(only)) continue;
        // the campaign from a clean page: its steps, then the save and a load (the reload restores the save, the panel is built anew on it)
        await b.open(URL0);
        await b.eval('localStorage.clear(); 1');
        await b.reload();
        await ready();
        const C = CAMPAIGNS[campaign];
        const steps = typeof C.steps === 'string' ? [...CAMPAIGNS[C.steps].steps, ...(C.more || [])] : C.steps;
        await b.eval(`(() => {
            const M = mtb.M, game = mtb.game, key = s => M.prefix + s;
            for (const st of ${JSON.stringify(steps)}) {
                const [what, a, c] = st;
                if (what === 'build') M.debug_build_to(key(a));
                else if (what === 'build_all') { for (const v of mtb.panel.view.tree) M.debug_build_to(v.node.key); }
                else if (what === 'gold') game.gold = a;
                else if (what === 'crew') M.set_crew(a, c);
                else if (what === 'order') { const r = M.order(key(a)); if (!r.ok) throw new Error('not ordered: ' + a + ': ' + (r.why || '')); }
                else if (what === 'points') game.dev = a;
                else if (what === 'demolish') { const r = M.demolish(key(a)); if (!r.ok) throw new Error('not demolished: ' + a + ': ' + (r.why || '')); }
                else if (what === 'end_turn') game.end_turn();
                else if (what === 'side') M.set_malakai_side(a);
            }
            mtb.update(); mtb.save(); return 1;
        })()`);
        // the panel opens on «Постройки» at its home place: the tab and the tree's place of the last visit forgotten
        await b.eval(`localStorage.setItem('mtb_panel_tab', 'tree'); for (const k of Object.keys(localStorage)) if (k.startsWith('mtb_panel_pan_')) localStorage.removeItem(k); 1`);
        await b.reload();
        await ready();
        // what the page's save does not keep: the game's own window before a cancel (the Lua side reads the dump's sim)
        if (C.sim && C.sim.ask_cancel) await b.eval('mtb.game.askCancel = true; 1');
        if (C.sim && C.sim.async) await b.eval('mtb.game.async = true; 1');
        const snapshot = await b.eval(`JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k => k.startsWith('mtb_web_state_'))))`);
        // the view acted on: ids of the components as the Lua names them; a slot by its node
        const resolved = [];
        for (const [what, target] of actions) {
            const id = typeof target === 'string' ? target : await b.eval(`'mtb_tree_node_' + mtb.panel.view.tree.findIndex(v => v.node.key === mtb.M.prefix + ${JSON.stringify(target.slot)})`);
            if (/_-1$/.test(id)) throw new Error(`${name}: no slot ${target.slot}`);
            const ok = await b.eval(`(() => {
                const find = (c, id) => { if (c.id === id) return c; for (const k of c.children) { const f = find(k, id); if (f) return f; } return null; };
                const c = find(mtb.root, ${JSON.stringify(id)});
                if (!c) return false;
                if (${JSON.stringify(what)} === 'click') mtb.panel.click(c);
                else if (${JSON.stringify(what)} === 'show') mtb.panel.view.pan.show(mtb.panel.view.tree[Number(${JSON.stringify(id)}.slice('mtb_tree_node_'.length))]);
                else c.el.dispatchEvent(new MouseEvent('mouseenter'));
                return true;
            })()`);
            if (!ok) throw new Error(`${name}: no component ${id}`);
            resolved.push([what, id]);
            await sleep(80);
        }
        const out = await b.eval(`(async () => {
            const G = await import('/js/gameui.js');
            return {components: G.dump(mtb.root), measures: G.measures()};
        })()`);
        const errors = b.errors.splice(0);
        if (errors.length) { failed++; console.log(`FAIL ${name}: the page's console: ${errors.join(' | ').slice(0, 800)}`); }
        const file = {name, campaign, about: C.about, sim: C.sim || {}, root: [1600, 900], snapshot, actions: resolved, ...out};
        writeFileSync(join(OUT, name + '.json'), JSON.stringify(file));
        made[name] = out.components.length;
        console.log(`${name}: ${out.components.length} components, ${Object.keys(out.measures).length} measures`);
    }
    if (!only) writeFileSync(join(OUT, 'index.json'), JSON.stringify({about: 'Made by tools/tests/ui_dump_export.mjs. Read by tools/ui_layout_check.py. Do not edit.', states: STATES.map(s => s[0]), components: made}, null, 1));
} finally {
    await b.close();
    await server.stop();
}
process.exit(failed ? 1 : 0);
