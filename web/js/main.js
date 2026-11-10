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
    const [data, sim, art, blueprint, overview] = await Promise.all([json('/build/data.json'), json('/data/sim.json'), json('/art/layers.json'), json('/data/blueprint.json'),
                                                                     json('/build/overview.json').catch(() => ({chains: []}))]);
    // ?stage=barge (or another name of blueprint.json, stages): what is shown; the stage's own fields over the common ones. parts: true the common ones,
    // false none, an object its own. built: what stands at the start of the stage, over web/data/sim.json.
    const stageName = flags.stage || blueprint.stage;
    const stage = blueprint.stages[stageName];
    Object.assign(blueprint, stage, {parts: stage.parts === true ? blueprint.parts : stage.parts || {}});
    const game = new GameSim(data, {...sim, ...(stage.built ? {built: stage.built} : {}), ...(stage.demolish_mode ? {demolish: stage.demolish_mode} : {})});
    // the cards of the overview (tools/web_export.py, export_overview) by key: every effect of a level with the game's text, the description, the game's name
    const cards = {};
    for (const chain of overview.chains) for (const c of chain.cards) cards[c.key] = {...c, chain_title: chain.title};
    const M = makeBuildings(data, game, blueprint.parts);
    const treeSpec = blueprint.tree || {};
    for (const [k, needs] of Object.entries(treeSpec.requires || {})) M.extra_requires[data.prefix + k] = needs.map(n => data.prefix + n);
    for (const k of treeSpec.not_connected || []) M.not_connected.add(data.prefix + k);
    flags.all_parts = flags.parts === 'all';
    M.all_parts = flags.all_parts;

    const host = document.getElementById('screen');
    const root = makeRoot(host);
    setTooltipRoot(root);
    const panel = makePanel(root, M, data, art, blueprint, flags, cards);
    onClick(c => panel.click(c));

    const viewer = new Viewer(document.getElementById('view3d'));
    // the base barge (build/solid_hull_hatches without the shields) and each detail as a model of its own; ?hull=stock shows the stock hull instead
    // model_when: the base barge is loaded at once but shown only when that part's building stands
    const hull = !(stage.model || stage.model_when) ? null : flags.hull === 'stock' ? 'hull_stock' : 'hull_base';
    const hullShown = () => !!hull && (!stage.model_when || M.stage(stage.model_when) === 'ink');
    if (hull) viewer.show(hull);
    const parts = Object.entries(blueprint.parts).filter(([, spec]) => spec.model);     // the frame has a drawing only
    const setParts = () => {
        for (const [key, spec] of parts) viewer.setPart(spec.model.part, hull === 'hull_base' && M.stage(key) === 'ink', spec.model.hides);
    };
    const loading = document.getElementById('loading');
    const noShip = document.getElementById('no_ship');
    noShip.textContent = stage.no_ship || '';
    const showNoShip = () => {
        noShip.style.display = hullShown() ? 'none' : '';
        for (const b of document.querySelectorAll('#tools3d button')) b.style.display = hullShown() ? '' : 'none';      // no ship, no views of it
    };
    showNoShip();
    Promise.all([hull ? viewer.load(hull, `/build/models/${hull}.gltf`) : null, ...parts.map(([, spec]) => viewer.load(spec.model.part, `/build/models/${spec.model.part}.gltf`))])
        .then(() => { setParts(); if (hull) viewer.setVisible(hull, hullShown()); loading.style.display = 'none'; document.body.dataset.ready = '1'; })
        .catch(e => { loading.textContent = 'Модель не загрузилась: ' + e.message; console.error(e); });

    // the test bar: what the game does around the panel
    const turnEl = document.getElementById('turn'), logEl = document.getElementById('log'), hullEl = document.getElementById('hull');
    const log = text => { const li = document.createElement('li'); li.textContent = `Ход ${game.turn}: ${text}`; logEl.prepend(li); };
    game.on('MilitaryForceBuildingCompleteEvent', ctx => log(`постройка завершена: «${M.level(ctx.building).name}»`));
    const update = () => {
        panel.refresh();
        turnEl.textContent = `Ход ${game.turn}`;
        setParts();
        if (hull) viewer.setVisible(hull, hullShown());
        showNoShip();
        if (hullShown()) {
            viewer.showFrameScheme(false);
            if (!viewer.bargeViewSet && stage.model_when) { viewer.bargeViewSet = true; viewer.view('all'); }
        } else {        // no ship yet: the timber, or the frame as a scheme (no model of it exists); the frame also while the barge is built
            const frame = stage.frame_scheme && M.stage('frame') === 'ink';
            viewer.showFrameScheme(frame);
            noShip.textContent = frame ? 'Каркас: 3D-модели пока нет, это схема из киля и рёбер' : stage.no_ship || '';
            noShip.classList.toggle('top', frame);
        }
        const built = parts.filter(([key]) => M.stage(key) === 'ink').map(([, spec]) => spec.name);
        hullEl.textContent = !hullShown() ? '' : hull === 'hull_stock' ? 'Стоковый корпус' : 'Базовая барка' + (built.length ? ': ' + built.join(', ') : '');
    };
    M.on_change(update);
    // The page's state lives through a reload: localStorage, one key per stage; the buttons of the bar: build up to the selected building, forget all.
    const saveKey = 'mtb_web_state_' + stageName;
    const save = () => { try { localStorage.setItem(saveKey, JSON.stringify({...game.snapshot(), side: M.malakai_side(), side_chosen: !M.side_hint(), selected: panel.view.selected, crew: M.crew_snapshot(), crew_chosen: !M.crew_hint()})); } catch (e) { /* no storage: the page still works */ } };
    M.on_change(save);
    panel.view.onSelect = save;
    try {
        const saved = JSON.parse(localStorage.getItem(saveKey) || 'null');
        if (saved && !flags.steps) {
            game.restore(saved);
            if (saved.side) M.set_side_silently(saved.side);
            M.set_side_chosen_silently(saved.side_chosen);
            M.set_crew_silently(saved.crew);
            M.set_crew_chosen_silently(saved.crew_chosen);
            if (saved.selected && M.level(saved.selected)) panel.view.selected = saved.selected;
        }
    } catch (e) { /* a broken or missing save: start fresh */ }
    if (flags.gold !== undefined) game.gold = Number(flags.gold);      // ?gold=500: start with this much, to see the short of gold state
    // Debug: the faction's gold set by hand; saved with the state, the tree and its prices redrawn at once
    const goldInput = document.getElementById('gold_value');
    const setGold = v => {
        if (!Number.isFinite(v) || v < 0) return;
        game.gold = Math.round(v);
        log(`отладка: золото ${game.gold}`);
        update(); save();
        goldInput.value = game.treasury();
    };
    document.getElementById('gold_set').addEventListener('click', () => setGold(Number(goldInput.value)));
    goldInput.addEventListener('keydown', e => { if (e.key === 'Enter') setGold(Number(goldInput.value)); });
    for (const b of document.querySelectorAll('.gold_quick')) b.addEventListener('click', () => setGold(Number(b.dataset.gold)));
    const showGold = () => { if (document.activeElement !== goldInput) goldInput.value = game.treasury(); };
    M.on_change(showGold);
    document.getElementById('build_to').addEventListener('click', () => {
        if (panel.view.selected && M.level(panel.view.selected)) { M.debug_build_to(panel.view.selected); log('отладка: построено до выбранной'); }
    });
    document.getElementById('reset_all').addEventListener('click', () => {
        try { localStorage.removeItem(saveKey); } catch (e) { /* nothing saved */ }
        location.reload();
    });
    document.getElementById('end_turn').addEventListener('click', () => { log('конец хода'); game.end_turn(); update(); save(); });
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
    // the overview leaves out what the panel's tree already holds
    makeOverview(document.getElementById('overview'), (blueprint.tree ? blueprint.tree.nodes : []).map(k => data.prefix + k)).catch(e => console.error(e));
    new ResizeObserver(fit).observe(document.getElementById('left'));
    fit();
    update();
    goldInput.value = game.treasury();
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
