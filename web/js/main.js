// The page: the game's screen on the left (root 1600 x 900, scaled as a whole), the 3D barge on the right, a test bar on top that stands for the game
// itself (the end turn button, the turn, the event feed). Flags in the address: ?full=1 shows the whole guns chain and the demolish button; ?k=1 draws the
// game's screen at a fixed scale instead of fitting it; ?steps=order,end_turn and ?view=port act at load (see the end of main); ?parts=all shows every detail as built,
// ?hull=stock the stock hull (export with --stock); ?stage=barge the base barge with the guns' first building (default: the bare timber).
// Two modes, switched in the bar: «Игра», the game's screen with the tree of buildings of web/data/tree_design.json, and «Конструктор», the editor of
// that file (web/js/constructor.js). ?mode=constructor or ?mode=game at load; otherwise the last mode used. ?tree=blueprint: the old tree of
// blueprint.json in place of the file's.

import {makeRoot, onClick, setTooltipRoot} from './gameui.js';
import {GameSim} from './game_sim.js';
import {makeBuildings, turnsText} from './barge_buildings.js';
import {makePanel, crewState} from './panel.js';
import {Viewer} from './viewer3d.js';
import {makeOverview} from './overview.js';
import * as T from './tree_model.mjs';
import {makeConstructor} from './constructor.js';

const flags = Object.fromEntries(new URLSearchParams(location.search));

async function json(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
}

async function main() {
    // the tree's file with its version (tools/web_serve.py: a write names the version it was made on)
    let fileVersion = null;
    const [data, sim, art, blueprint, overview, designFile, catalog] = await Promise.all([json('/build/data.json'), json('/data/sim.json'), json('/art/layers.json'), json('/data/blueprint.json'),
        json('/build/overview.json').catch(() => ({chains: []})),
        flags.tree === 'blueprint' ? null : fetch('/data/tree_design.json', {cache: 'no-store'}).then(r => { fileVersion = r.headers.get('X-Tree-Version'); return r.ok ? r.text() : null; }).catch(() => null),
        // the constructor's catalogue: the game's effects of the dwarfs' buildings, the dwarfs' army units (tools/web_export.py --catalog)
        json('/build/catalog.json').catch(() => ({game_effects: [], army_units: []}))]);
    const blueprintAll = JSON.parse(JSON.stringify(blueprint));      // before the stage's fields go over it: every part, for the constructor
    // The crew's cards: a group whose place says so (blueprint.json, crew_areas, cards: drawn) shows the mod's own drawn cards (data/ui/crew_cards: the
    // game's models on the barge, as the mod's panel shows them) in place of the game's unit card of a unit that stands for it; the riflemen keep the
    // game's cards (the user rejected their drawn set).
    for (const st of Object.values(blueprint.stages)) for (const a of st.crew_areas || []) {
        const g = data.groups[a.group];
        if (g && a.cards === 'drawn') for (const o of Object.values(g.options)) if (o.drawn_card && o.unit_card) o.unit_card = {...o.unit_card, picture: o.drawn_card};
        // closeup: the close views of what stands at the place (tools/web_art.py --cards: the game's models, build/web/game/ui/tww3_mtb_cards)
        if (g && a.cards === 'closeup') for (const [k, o] of Object.entries(g.options)) if (o.unit_card) o.unit_card = {...o.unit_card, picture: `ui/tww3_mtb_cards/${a.group}_${k}.png`};
    }
    // ?stage=barge (or another name of blueprint.json, stages): what is shown; the stage's own fields over the common ones. parts: true the common ones,
    // false none, an object its own. built: what stands at the start of the stage, over web/data/sim.json.
    const stageName = flags.stage || blueprint.stage;
    const stage = blueprint.stages[stageName];
    Object.assign(blueprint, stage, {parts: stage.parts === true ? blueprint.parts : stage.parts || {}});
    // the cards of the overview (tools/web_export.py, export_overview) by key: every effect of a level with the game's text, the description, the game's name
    const cards = {};
    for (const chain of overview.chains) for (const c of chain.cards) cards[c.key] = {...c, chain_title: chain.title};
    flags.all_parts = flags.parts === 'all';

    const host = document.getElementById('screen');
    const viewer = new Viewer(document.getElementById('view3d'));
    // the base barge (build/solid_hull_hatches without the shields) and each detail as a model of its own; ?hull=stock shows the stock hull instead
    // model_when: the base barge is loaded at once but shown only when that part's building stands
    const hull = !(stage.model || stage.model_when) ? null : flags.hull === 'stock' ? 'hull_stock' : 'hull_base';
    // the details the tree's nodes bring (web/data/tree_design.json, parts): one of blueprint.json the stage does not show joins it, shown with its
    // node's building (barge_buildings.js, M.stage); one without a layer or a model is only named in the building's window ("рисунок не готов")
    const partsInfo = T.shipParts(blueprintAll, {...art.places, ...data.art.layers});
    // A new detail of a node (part: null) named as a detail of blueprint.json is that detail: the tree's «Дозорные в гнёздах» is the drawn lookouts
    // (the constructor would write part: "lookouts"; until the author does, the name links them)
    const byName = Object.fromEntries(Object.entries(blueprintAll.parts).map(([k, spec]) => [spec.name, k]));
    const linkParts = d => { for (const n of d ? d.nodes : []) for (const p of n.parts || []) if (!p.part && p.name && byName[p.name]) p.part = byName[p.name]; return d; };
    const joinParts = d0 => {
        const d = d0 ? linkParts(JSON.parse(JSON.stringify(d0))) : null;      // a copy: the constructor's tree is never written by the game's side
        for (const p of (d ? d.nodes : []).flatMap(n => n.parts || [])) {
            const info = p.part && partsInfo[p.part];
            if (!info || (!info.drawn && !info.model)) continue;
            if (!blueprint.parts[p.part]) blueprint.parts[p.part] = {...blueprintAll.parts[p.part], enabled: true};
            else if (!blueprint.parts[p.part].enabled) blueprint.parts[p.part] = {...blueprint.parts[p.part], enabled: true};
        }
    };
    try { joinParts(designFile ? JSON.parse(designFile) : null); } catch (e) { /* read again below */ }
    let parts = Object.entries(blueprint.parts).filter(([, spec]) => spec.model);     // the frame has a drawing only

    // ---- the game's part: built from the tree, again whenever the tree changed in the constructor ----
    let G = null;           // {game, M, panel, root, designText}
    const hullShown = () => !!hull && (!stage.model_when || G.M.stage(stage.model_when) === 'ink');
    const setParts = () => {
        // a detail only on the barge it belongs to: none hangs in the air while the hull is not shown
        for (const [key, spec] of parts) viewer.setPart(spec.model.part, hull === 'hull_base' && hullShown() && G.M.stage(key) === 'ink', spec.model.hides);
    };
    const loading = document.getElementById('loading');
    const noShip = document.getElementById('no_ship');
    const showNoShip = () => {
        noShip.style.display = hullShown() ? 'none' : '';
        for (const b of document.querySelectorAll('#tools3d button')) b.style.display = hullShown() ? '' : 'none';      // no ship, no views of it
    };
    const turnEl = document.getElementById('turn'), logEl = document.getElementById('log'), hullEl = document.getElementById('hull');
    const log = text => {
        const li = document.createElement('li');
        li.textContent = `Ход ${G.game.turn}: ${text}`;
        logEl.prepend(li);
        while (logEl.children.length > 12) logEl.lastChild.remove();
        logEl.title = [...logEl.children].map(x => x.textContent).join(String.fromCharCode(10));      // the last lines, the newest first
    };
    const update = () => {
        const {M, panel, game} = G;
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
        setCrew3d();
        const built = parts.filter(([key]) => M.stage(key) === 'ink').map(([, spec]) => spec.name);
        // one short line over the model; the whole list of the details in its tooltip
        hullEl.textContent = !hullShown() ? '' : hull === 'hull_stock' ? 'Стоковый корпус' : 'Базовая барка' + (built.length ? ` · деталей: ${built.length}` : '');
        hullEl.title = hullShown() && built.length ? 'На корабле: ' + built.join(', ') : '';
    };
    // The crew on the 3D model (tools/web_crew3d.py), from the same state as the drawing (panel.js, crewState): what stands at a place stands on the
    // model, a hire on its way is a warm see-through ghost of its kind, nobody is nothing. The flaming shells are the stock gun (the mod changes only
    // the shell); the bombs have no model (a stowed bomb is not on the barge's model). The lookouts stand in the nests while nobody of the crew is
    // there or coming; Malakai on his side takes a rifle seat (his own model, the riflemen's copy on that seat hidden).
    const MODEL_OF = {cannons: k => (k === 'flaming' ? 'cannons_stock' : 'cannons_' + k), rifles: k => 'rifles_' + k, cupolas: k => 'cupolas_' + k, harpoon: k => 'harpoon_' + k};
    const setCrew3d = () => {
        const {M} = G;
        viewer.showCrew(hullShown());
        const side = M.malakai_side(), sideReady = !stage.malakai_side || !stage.malakai_side.show_when || M.stage(stage.malakai_side.show_when) === 'ink';
        for (const a of blueprint.crew_areas || []) {
            const of = MODEL_OF[a.group];
            if (!of) continue;
            const st = crewState(M, a.group);
            const kind = st.place ? st.stand || st.coming : null;
            viewer.setCrew(a.group, kind ? of(kind) : null, kind ? (st.stand ? 'stand' : 'ghost') : null, a.group === 'rifles' && sideReady ? [`ap_crew_${side}_1`] : []);
            // the detail the crew takes the place of (the nests' lookouts), in 3D its own model (blueprint.json, hides_part_3d); none in the tree: nothing
            if (a.hides_part && a.hides_part_3d) viewer.setCrew(a.hides_part, M.stage(a.hides_part) === 'ink' && st.nobody && !st.coming ? a.hides_part_3d : null, 'stand');
        }
        viewer.setCrew('malakai', sideReady && hullShown() ? 'malakai_' + side : null, 'stand');
    };
    // The page's state lives through a reload: localStorage, one key per stage.
    const saveKey = 'mtb_web_state_' + stageName;
    const save = () => { const {game, M, panel} = G; try { localStorage.setItem(saveKey, JSON.stringify({...game.snapshot(), side: M.malakai_side(), side_chosen: !M.side_hint(), selected: panel.view.selected, crew: M.crew_snapshot(), crew_chosen: M.crew_chosen()})); } catch (e) { /* no storage: the page still works */ } };
    const goldInput = document.getElementById('gold_value');
    const showGold = () => { if (document.activeElement !== goldInput) goldInput.value = G.game.treasury(); };

    const buildGame = design => {
        // the levels: the file's nodes (web/js/tree_model.mjs, gameData), or the mod's data and blueprint.json's tree without a file
        joinParts(design);
        parts = Object.entries(blueprint.parts).filter(([, spec]) => spec.model);
        for (const [, spec] of parts) if (!viewer.models[spec.model.part] && !(viewer.pending ||= new Set()).has(spec.model.part) && viewer.pending.add(spec.model.part)) viewer.load(spec.model.part, `/build/models/${spec.model.part}.gltf`).then(() => { if (G) setParts(); }).catch(e => console.error(e));
        const levels = design ? {...T.gameData(linkParts(JSON.parse(JSON.stringify(design))), data), army_units: Object.fromEntries((catalog.army_units || []).map(u => [u.key, u])), parts_all: partsInfo} : data;
        const game = new GameSim(levels, {...sim, ...(stage.built ? {built: stage.built} : {}), ...(stage.demolish_mode ? {demolish: stage.demolish_mode} : {})});
        const M = makeBuildings(levels, game, blueprint.parts);
        for (const a of blueprint.crew_areas || []) if (a.words) M.words[a.group] = a.words;
        if (!design) {
            const treeSpec = blueprint.tree || {};
            for (const [k, needs] of Object.entries(treeSpec.requires || {})) M.extra_requires[data.prefix + k] = needs.map(n => data.prefix + n);
            for (const k of treeSpec.not_connected || []) M.not_connected.add(data.prefix + k);
        }
        M.all_parts = flags.all_parts;
        host.innerHTML = '';
        const root = makeRoot(host);
        setTooltipRoot(root);
        const panel = makePanel(root, M, levels, art, design ? {...blueprint, tree: null} : blueprint, flags, cards);
        onClick(c => panel.click(c));
        G = {game, M, panel, root, designText: design ? T.serialize(design) : null};
        game.on('MilitaryForceBuildingCompleteEvent', ctx => log(`постройка завершена: «${M.level(ctx.building).name}»`));
        M.on_change(update);
        M.on_change(save);
        M.on_change(showGold);
        panel.view.onSelect = save;
        panel.view.onCrewArea = g => onCrewArea(g);
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
        fit();
        update();
        goldInput.value = game.treasury();
        // the overview under the screen leaves out what the panel's tree already holds
        makeOverview(document.getElementById('overview'), design ? design.nodes.filter(n => n.mod_key).map(n => data.prefix + n.mod_key) : (blueprint.tree ? blueprint.tree.nodes : []).map(k => data.prefix + k)).catch(e => console.error(e));
    };

    noShip.textContent = stage.no_ship || '';
    viewer.pending = new Set(parts.map(([, spec]) => spec.model.part));
    Promise.all([hull ? viewer.load(hull, `/build/models/${hull}.gltf`) : null, ...parts.map(([, spec]) => viewer.load(spec.model.part, `/build/models/${spec.model.part}.gltf`))])
        .then(() => { setParts(); if (hull) viewer.setVisible(hull, hullShown()); loading.style.display = 'none'; document.body.dataset.ready = '1'; })
        .catch(e => { loading.textContent = 'Модель не загрузилась: ' + e.message; console.error(e); });

    // Debug: the faction's gold set by hand; saved with the state, the tree and its prices redrawn at once
    const setGold = v => {
        if (!Number.isFinite(v) || v < 0) return;
        G.game.gold = Math.round(v);
        log(`отладка: золото ${G.game.gold}`);
        update(); save();
        goldInput.value = G.game.treasury();
    };
    document.getElementById('gold_set').addEventListener('click', () => setGold(Number(goldInput.value)));
    goldInput.addEventListener('keydown', e => { if (e.key === 'Enter') setGold(Number(goldInput.value)); });
    for (const b of document.querySelectorAll('.gold_quick')) b.addEventListener('click', () => setGold(Number(b.dataset.gold)));
    // Debug: every building of the tree built at once, as if the campaign were over (the guns, the bombs, the nests and every detail on the drawing)
    document.getElementById('build_all').addEventListener('click', () => {
        const {M, panel} = G;
        for (const v of panel.view.tree || []) M.debug_build_to(v.node.key);
        log('отладка: построено всё');
    });
    document.getElementById('build_to').addEventListener('click', () => {
        const {M, panel} = G;
        if (panel.view.selected && M.level(panel.view.selected)) { M.debug_build_to(panel.view.selected); log('отладка: построено до выбранной'); }
    });
    document.getElementById('reset_all').addEventListener('click', () => {
        try { localStorage.removeItem(saveKey); } catch (e) { /* nothing saved */ }
        location.reload();
    });
    document.getElementById('end_turn').addEventListener('click', () => { log('конец хода'); G.game.end_turn(); update(); save(); });
    for (const which of ['port', 'all', 'left', 'right', 'below', 'top', 'nose', 'rail']) document.getElementById('view_' + which).addEventListener('click', () => viewer.flyTo(which, 450));
    // A click on a group's tag on the drawing may turn the 3D view to that place: the user's choice, off until asked (the button «К месту экипажа»),
    // remembered; the flight is smooth and the mouse stops it.
    const FOLLOW = {cannons: 'port', rifles: 'rail', bombs: 'below', cupolas: 'top', harpoon: 'nose'};
    const followBtn = document.getElementById('follow_crew');
    let follow = false;
    try { follow = localStorage.getItem('mtb_follow_crew') === '1'; } catch (e) { /* no storage */ }
    const showFollow = () => { followBtn.classList.toggle('on', follow); followBtn.title = follow ? 'Клик по бирке на чертеже поворачивает 3D к месту экипажа. Щёлкните, чтобы выключить' : 'Включить: клик по бирке на чертеже повернёт 3D к месту экипажа'; };
    followBtn.addEventListener('click', () => { follow = !follow; try { localStorage.setItem('mtb_follow_crew', follow ? '1' : '0'); } catch (e) { /* no storage */ } showFollow(); });
    showFollow();
    const onCrewArea = g => { if (follow && FOLLOW[g] && hullShown()) viewer.flyTo(FOLLOW[g]); };

    // the bar's honest height: the page and the constructor start under it however many rows its groups take
    const bar = document.getElementById('bar');
    new ResizeObserver(() => document.documentElement.style.setProperty('--bar-h', bar.offsetHeight + 'px')).observe(bar);
    // «Отладка ▾»: the debug buttons in a dropdown when the window is narrow (web/css/page.css); a click elsewhere folds it
    const debugBox = document.getElementById('debug');
    document.getElementById('debug_toggle').addEventListener('click', e => { e.stopPropagation(); debugBox.classList.toggle('open'); e.currentTarget.setAttribute('aria-expanded', String(debugBox.classList.contains('open'))); });
    document.addEventListener('click', e => { if (!debugBox.contains(e.target)) debugBox.classList.remove('open'); });
    // an action done folds it again (the gold's field stays open while it is typed in)
    document.getElementById('debug_tools').addEventListener('click', e => { if (e.target.closest('button')) debugBox.classList.remove('open'); });
    const fit = () => {
        if (!G) return;
        const area = document.getElementById('left'), root = G.root;
        if (!area.clientWidth) return;          // hidden while the constructor is shown
        // ?k=1: the game's own pixels, scrolled (for close looks); otherwise the whole root fits the left side
        const k = flags.k ? Number(flags.k) : Math.min(area.clientWidth / root.Width(), area.clientHeight / root.Height());
        area.style.overflowX = flags.k ? 'auto' : 'hidden';
        area.style.overflowY = 'auto';      // the overview of the chains goes on under the screen
        root.el.style.transform = `scale(${k})`;
        host.style.width = root.Width() * k + 'px';
        host.style.height = root.Height() * k + 'px';
    };
    new ResizeObserver(fit).observe(document.getElementById('left'));

    // ---- the tree's file and the two modes ----
    let design = null, problems = [], migrated = null;
    if (designFile !== null) {
        try {
            let from;
            ({design, problems, from} = T.normalize(JSON.parse(designFile)));
            // a file older than the lines of levels: the mod's chains on the canvas become lines (inheritance off), written by the constructor
            if (from < T.FORMAT) migrated = {from, lines: T.linkModChains(design, data)};
        } catch (e) {
            // a broken file is kept as a copy before the constructor writes anything over it
            console.error('web/data/tree_design.json:', e);
            design = T.emptyDesign();
            const kept = await fetch('/api/tree_design/backup', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}'}).then(r => r.json()).catch(() => ({}));
            problems = [`файл не читается как JSON (${e.message}), его копия: web/data/${kept.name || '—'}`];
        }
    }
    let editor = null;
    const modeButtons = document.querySelectorAll('#mode button');
    const setMode = mode => {
        if (mode === 'constructor' && design === null) mode = 'game';
        document.body.dataset.mode = mode;
        for (const b of modeButtons) b.classList.toggle('on', b.dataset.mode === mode);
        try { localStorage.setItem('mtb_mode', mode); } catch (e) { /* no storage */ }
        if (mode === 'constructor') {
            if (!editor) editor = makeConstructor(document.getElementById('constructor'), {data, cards, design, problems, onChange: d => { design = d; }, catalog, blueprint: blueprintAll, art, version: fileVersion, migrated});
            editor.show();
        } else {
            if (editor) { editor.hide(); design = editor.design(); }
            if (!G || (design && G.designText !== T.serialize(design))) buildGame(design);
            requestAnimationFrame(fit);
        }
    };
    for (const b of modeButtons) b.addEventListener('click', () => setMode(b.dataset.mode));
    let mode = flags.mode;
    if (!mode) { try { mode = localStorage.getItem('mtb_mode'); } catch (e) { /* no storage */ } }
    buildGame(design);
    setMode(mode === 'constructor' ? 'constructor' : 'game');

    // for checks from the browser's console: the state as text
    window.mtb = {get game() { return G.game; }, get M() { return G.M; }, get panel() { return G.panel; }, viewer, get editor() { return editor; }, setMode,
        describe: () => ({turn: G.game.turn, gold: G.game.treasury(), hull: viewer.current, mode: document.body.dataset.mode,
            levels: (G.panel.view.tree ? G.panel.view.tree.map(v => ({key: v.node.key, name: v.node.name, ...G.M.status(v.node.key)})) : G.panel.view.levels.map(l => ({name: l.name, ...G.M.status(l.key)}))),
            stage: stageName, port: blueprint.parts.port ? G.M.stage('port') : null, message: G.M.message(),
            shown: Object.entries(viewer.models).filter(([, m]) => m.visible).map(([k]) => k), hidden_nodes: viewer.hiddenNodes()})};
    window.turnsText = turnsText;
    // ?steps=order,end_turn&view=port: clicks done for the page at load, for pictures and checks without a mouse
    const steps = {order: () => G.M.order(G.panel.view.selected), cancel: () => G.M.cancel(G.panel.view.selected), demolish: () => G.M.demolish(G.panel.view.selected),
                   end_turn: () => { log('конец хода'); G.game.end_turn(); }};
    for (const step of (flags.steps || '').split(',').filter(Boolean)) { steps[step](); update(); }
    if (flags.view) viewer.view(flags.view);
}

main().catch(e => { document.getElementById('loading').textContent = 'Ошибка: ' + e.message; console.error(e); });
