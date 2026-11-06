// The page: the game's screen on the left (root 1600 x 900, scaled as a whole), the 3D barge on the right, a test bar on top that stands for the game
// itself (the end turn button, the turn, the event feed). Flags in the address: ?full=1 shows the whole guns chain and the demolish button; ?k=1 draws the
// game's screen at a fixed scale instead of fitting it; ?steps=order,end_turn and ?view=port act at load (see the end of main).

import {makeRoot, onClick, setTooltipRoot} from './gameui.js';
import {GameSim} from './game_sim.js';
import {makeBuildings, turnsText} from './barge_buildings.js';
import {makePanel} from './panel.js';
import {Viewer} from './viewer3d.js';

const flags = Object.fromEntries(new URLSearchParams(location.search));

async function json(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
}

async function main() {
    const [data, sim, art, blueprint] = await Promise.all([json('/build/data.json'), json('/data/sim.json'), json('/art/layers.json'), json('/data/blueprint.json')]);
    const game = new GameSim(data, sim);
    const M = makeBuildings(data, game, blueprint.parts);

    const host = document.getElementById('screen');
    const root = makeRoot(host);
    setTooltipRoot(root);
    const panel = makePanel(root, M, data, art, blueprint, flags);
    onClick(c => panel.click(c));

    const viewer = new Viewer(document.getElementById('view3d'));
    const hullFor = () => (M.status(data.prefix + blueprint.parts.port.building).state === 'built' ? 'hull_port' : 'hull_closed');
    viewer.show(hullFor());
    const loading = document.getElementById('loading');
    Promise.all([viewer.load('hull_closed', '/build/models/hull_closed.gltf'), viewer.load('hull_port', '/build/models/hull_port.gltf')])
        .then(() => { loading.style.display = 'none'; document.body.dataset.ready = '1'; })
        .catch(e => { loading.textContent = 'Модель не загрузилась: ' + e.message; console.error(e); });

    // the test bar: what the game does around the panel
    const turnEl = document.getElementById('turn'), logEl = document.getElementById('log'), hullEl = document.getElementById('hull');
    const log = text => { const li = document.createElement('li'); li.textContent = `Ход ${game.turn}: ${text}`; logEl.prepend(li); };
    game.on('MilitaryForceBuildingCompleteEvent', ctx => log(`постройка завершена: «${M.level(ctx.building).name}»`));
    const update = () => {
        panel.refresh();
        turnEl.textContent = `Ход ${game.turn}`;
        const hull = hullFor();
        viewer.show(hull);
        hullEl.textContent = hull === 'hull_port' ? 'Корпус: с портом (стоковый)' : 'Корпус: без порта (hull_port_closed_v1)';
    };
    M.on_change(update);
    document.getElementById('end_turn').addEventListener('click', () => { log('конец хода'); game.end_turn(); update(); });
    document.getElementById('view_port').addEventListener('click', () => viewer.view('port'));
    document.getElementById('view_all').addEventListener('click', () => viewer.view('all'));

    const fit = () => {
        const area = document.getElementById('left');
        // ?k=1: the game's own pixels, scrolled (for close looks); otherwise the whole root fits the left side
        const k = flags.k ? Number(flags.k) : Math.min(area.clientWidth / root.Width(), area.clientHeight / root.Height());
        area.style.overflow = flags.k ? 'auto' : 'hidden';
        root.el.style.transform = `scale(${k})`;
        host.style.width = root.Width() * k + 'px';
        host.style.height = root.Height() * k + 'px';
    };
    new ResizeObserver(fit).observe(document.getElementById('left'));
    fit();
    update();
    // for checks from the browser's console: the state as text
    window.mtb = {game, M, panel, viewer, describe: () => ({turn: game.turn, gold: game.treasury(), hull: viewer.current,
        levels: panel.view.levels.map(l => ({name: l.name, ...M.status(l.key)})), stage: M.stage('port'), message: M.message()})};
    window.turnsText = turnsText;
    // ?steps=order,end_turn&view=port: clicks done for the page at load, for pictures and checks without a mouse
    const steps = {order: () => M.order(panel.view.selected), cancel: () => M.cancel(panel.view.selected), demolish: () => M.demolish(panel.view.selected),
                   end_turn: () => { log('конец хода'); game.end_turn(); }};
    for (const step of (flags.steps || '').split(',').filter(Boolean)) { steps[step](); update(); }
    if (flags.view) viewer.view(flags.view);
}

main().catch(e => { document.getElementById('loading').textContent = 'Ошибка: ' + e.message; console.error(e); });
