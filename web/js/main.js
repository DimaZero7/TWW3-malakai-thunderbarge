// The page: the game's screen on the left (root 1600 x 900, scaled as a whole), the 3D barge on the right, a test bar on top that stands for the game
// itself (the end turn button, the turn, the event feed). Flags in the address: ?full=1 shows the whole guns chain and the demolish button; ?k=1 draws the
// game's screen at a fixed scale instead of fitting it; ?steps=order,end_turn and ?view=port act at load (see the end of main); ?parts=all shows every detail as built,
// ?hull=stock the stock hull (export with --stock); ?stage=barge the base barge with the guns' first building (default: the bare timber).

import {makeRoot, onClick, setTooltipRoot} from './gameui.js';
import {GameSim} from './game_sim.js';
import {makeBuildings, turnsText} from './barge_buildings.js';
import {makePanel} from './panel.js';
import {Viewer} from './viewer3d.js';
import {makeOverview} from './overview.js';

const flags = Object.fromEntries(new URLSearchParams(location.search));

async function json(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
}

async function main() {
    const [data, sim, art, blueprint] = await Promise.all([json('/build/data.json'), json('/data/sim.json'), json('/art/layers.json'), json('/data/blueprint.json')]);
    const game = new GameSim(data, sim);
    // ?stage=barge (or another name of blueprint.json, stages): what is shown; the stage's own fields over the common ones. A stage without parts has none of them.
    const stageName = flags.stage || blueprint.stage;
    const stage = blueprint.stages[stageName];
    Object.assign(blueprint, stage, {parts: stage.parts ? blueprint.parts : {}});
    const M = makeBuildings(data, game, blueprint.parts);
    flags.all_parts = flags.parts === 'all';
    M.all_parts = flags.all_parts;

    const host = document.getElementById('screen');
    const root = makeRoot(host);
    setTooltipRoot(root);
    const panel = makePanel(root, M, data, art, blueprint, flags);
    onClick(c => panel.click(c));

    const viewer = new Viewer(document.getElementById('view3d'));
    // the base barge (build/solid_hull_hatches without the shields) and each detail as a model of its own; ?hull=stock shows the stock hull instead
    const hull = !stage.model ? null : flags.hull === 'stock' ? 'hull_stock' : 'hull_base';
    if (hull) viewer.show(hull);
    const parts = Object.entries(blueprint.parts);
    const setParts = () => {
        for (const [key, spec] of parts) viewer.setPart(spec.model.part, hull === 'hull_base' && M.stage(key) === 'ink', spec.model.hides);
    };
    const loading = document.getElementById('loading');
    const noShip = document.getElementById('no_ship');
    noShip.textContent = stage.no_ship || '';
    noShip.style.display = hull ? 'none' : '';
    for (const b of document.querySelectorAll('#tools3d button')) b.style.display = hull ? '' : 'none';      // no ship, no views of it
    Promise.all([hull ? viewer.load(hull, `/build/models/${hull}.gltf`) : null, ...parts.map(([, spec]) => viewer.load(spec.model.part, `/build/models/${spec.model.part}.gltf`))])
        .then(() => { setParts(); loading.style.display = 'none'; document.body.dataset.ready = '1'; })
        .catch(e => { loading.textContent = 'Модель не загрузилась: ' + e.message; console.error(e); });

    // the test bar: what the game does around the panel
    const turnEl = document.getElementById('turn'), logEl = document.getElementById('log'), hullEl = document.getElementById('hull');
    const log = text => { const li = document.createElement('li'); li.textContent = `Ход ${game.turn}: ${text}`; logEl.prepend(li); };
    game.on('MilitaryForceBuildingCompleteEvent', ctx => log(`постройка завершена: «${M.level(ctx.building).name}»`));
    const update = () => {
        panel.refresh();
        turnEl.textContent = `Ход ${game.turn}`;
        setParts();
        const built = parts.filter(([key]) => M.stage(key) === 'ink').map(([, spec]) => spec.name);
        hullEl.textContent = !hull ? '' : hull === 'hull_stock' ? 'Стоковый корпус' : 'Базовая барка' + (built.length ? ': ' + built.join(', ') : '');
    };
    M.on_change(update);
    document.getElementById('end_turn').addEventListener('click', () => { log('конец хода'); game.end_turn(); update(); });
    for (const which of ['port', 'all', 'left', 'right', 'below']) document.getElementById('view_' + which).addEventListener('click', () => viewer.view(which));

    const fit = () => {
        const area = document.getElementById('left');
        // ?k=1: the game's own pixels, scrolled (for close looks); otherwise the whole root fits the left side
        const k = flags.k ? Number(flags.k) : Math.min(area.clientWidth / root.Width(), area.clientHeight / root.Height());
        area.style.overflowX = flags.k ? 'auto' : 'hidden';
        area.style.overflowY = 'auto';      // the overview of the chains goes on under the screen
        root.el.style.transform = `scale(${k})`;
        host.style.width = root.Width() * k + 'px';
        host.style.height = root.Height() * k + 'px';
    };
    makeOverview(document.getElementById('overview')).catch(e => console.error(e));
    new ResizeObserver(fit).observe(document.getElementById('left'));
    fit();
    update();
    // for checks from the browser's console: the state as text
    window.mtb = {game, M, panel, viewer, describe: () => ({turn: game.turn, gold: game.treasury(), hull: viewer.current,
        levels: panel.view.levels.map(l => ({name: l.name, ...M.status(l.key)})), stage: stageName, port: blueprint.parts.port ? M.stage('port') : null, message: M.message(),
        shown: Object.entries(viewer.models).filter(([, m]) => m.visible).map(([k]) => k), hidden_nodes: viewer.hiddenNodes()})};
    window.turnsText = turnsText;
    // ?steps=order,end_turn&view=port: clicks done for the page at load, for pictures and checks without a mouse
    const steps = {order: () => M.order(panel.view.selected), cancel: () => M.cancel(panel.view.selected), demolish: () => M.demolish(panel.view.selected),
                   end_turn: () => { log('конец хода'); game.end_turn(); }};
    for (const step of (flags.steps || '').split(',').filter(Boolean)) { steps[step](); update(); }
    if (flags.view) viewer.view(flags.view);
}

main().catch(e => { document.getElementById('loading').textContent = 'Ошибка: ' + e.message; console.error(e); });
