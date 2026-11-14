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
    fresh: {about: 'a new campaign: nothing built, 6000 gold', steps: []},
    mid: {about: 'the barge and the first buildings stand; the riflemen in hire came aboard with the turn; one building ordered, a crew order waiting, gold short for most',
          steps: [['build', 'airship_hull_3'], ['build', 'beer_hall_1'], ['build', 'infantry_workshop_1'], ['build', 'crew_weapons_1'], ['build', 'mtb_nest_1'],
                  ['build', 'engineering_workshop_1'], ['gold', 3000], ['crew', 'rifles', 'quarrellers'], ['order', 'support_radius_1'], ['end_turn'],
                  ['order', 'cargo_hold_1'], ['gold', 1200], ['crew', 'rifles', 'pirates']]},
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
    ['full_tree', 'full', []],
    ['full_tree_info', 'full', [['hover', {slot: 'mtb_guns_3'}]]],
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
    await b.send('Page.addScriptToEvaluateOnNewDocument', {source: 'window.setInterval = () => 0;'});
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
        const steps = CAMPAIGNS[campaign].steps;
        await b.eval(`(() => {
            const M = mtb.M, game = mtb.game, key = s => M.prefix + s;
            for (const st of ${JSON.stringify(steps)}) {
                const [what, a, c] = st;
                if (what === 'build') M.debug_build_to(key(a));
                else if (what === 'build_all') { for (const v of mtb.panel.view.tree) M.debug_build_to(v.node.key); }
                else if (what === 'gold') game.gold = a;
                else if (what === 'crew') M.set_crew(a, c);
                else if (what === 'order') { if (!M.order(key(a))) throw new Error('not ordered: ' + a); }
                else if (what === 'end_turn') game.end_turn();
                else if (what === 'side') M.set_malakai_side(a);
            }
            mtb.update(); mtb.save(); return 1;
        })()`);
        // the panel opens on «Постройки» at its home place: the tab and the tree's place of the last visit forgotten
        await b.eval(`localStorage.setItem('mtb_panel_tab', 'tree'); for (const k of Object.keys(localStorage)) if (k.startsWith('mtb_panel_pan_')) localStorage.removeItem(k); 1`);
        await b.reload();
        await ready();
        // the page builds its screen before it reads the save back (web/js/main.js buildGame): what it lays out by the state at its build (the tree's
        // home place, the order of a crew's kinds) is then the fresh campaign's. The game builds the panel on the loaded state: so the screen is built
        // again on it, at its home place, and only then written
        await b.eval('mtb.rebuild(); mtb.panel.view.pan.home(); mtb.panel.refresh(); 1');
        await b.until('!!(mtb.root && mtb.root.pictures)', 20000);
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
        const file = {name, campaign, about: CAMPAIGNS[campaign].about, root: [1600, 900], snapshot, actions: resolved, ...out};
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
