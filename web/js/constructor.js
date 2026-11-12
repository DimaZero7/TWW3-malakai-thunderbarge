// The constructor of the tree of buildings: the author lays out the barge's buildings with the mouse, and every change goes at once to
// web/data/tree_design.json (tools/web_serve.py, POST /api/tree_design), with a copy in the browser. The tree itself, its operations, undo, the
// checks, the constructor's grid and the ways of its lines are web/js/tree_model.mjs; this file only draws and listens.
//
//   the palette (left)     the mod's building levels (build/web/data.json, overview.json) and an empty building, dragged onto the canvas
//   the canvas             the constructor's own grid (tree_model.mjs, CX: a cell of 170 x 160, rows numbered from the bottom): every node a card
//                          with the game's slot, its price, its crew's small cards and its name in up to three lines; every link its own way
//                          through the corridors between the cards, an arrow at the building that needs it. Pan, zoom, select, move, link, menu.
//                          The status line under it: the zoom, a hint of what the mouse does where it is, the checks.
//   the properties (right) every field of the selected node, applied at once; a group, a link, or the tree as a whole when nothing is selected.
//                          The lines of effects come from a catalogue (web/js/effects_model.mjs: the crew's shooting by group, the ship, the game's own
//                          effects of build/web/catalog.json) or are free text; the army units a building opens for recruitment (catalog.json); what
//                          appears on the ship with it (web/data/blueprint.json parts, or a new detail described for the developer)
//   the bar                undo, redo, delete, copy, show all, the file's menu, the keys, and the state of saving
// Lines of levels (tree_model.mjs: prev, inherit, resolve): a node may continue a previous level of its line, as the game's chain; its level is on
// its slot in the game's numeral, the link to the level below is a double line, and with «Наследует» it gives all the level below gives, live, its
// own lines over it: the properties show the inherited block above the own one, a number of an inherited effect is changed in place, a line is
// changed or removed on this level and given back. «+ Следующий уровень» makes the next level at once.
// The file has a version (tools/web_serve.py): a write names the version it was made on, so it never goes over a change made from outside. The
// constructor asks for the version every two seconds; a change from outside is taken at once when nothing of the author's waits to be written, merged
// building by building when something does (tree_model.mjs, merge3), and only a building changed on both sides asks which to keep, the other kept
// as a copy beside the file.
// Both side panels fold away ([ and ], \ both) for a large tree on a small screen.

import * as T from './tree_model.mjs';
import * as FX from './effects_model.mjs';
import {url} from './gameui.js';

const D = 'ui/skins/default/';
const {CX} = T, N = T.NODE;
// the colours of web/art/tree_line*.png (tools/web_art.py: tree_line, branch_frames): the lines of the game's column
const LINE = {trunk: '#C58B4A', gold: '#FFB020', blue: '#4696FF', green: '#64D25A', red: '#EB4632'};
const BRANCHES = [[null, 'Ствол'], ['gold', 'Золотая'], ['blue', 'Синяя'], ['green', 'Зелёная'], ['red', 'Красная']];
const STORE = 'mtb_tree_design';
const NAME_FONT = '600 14px "Segoe UI", sans-serif', NAME_W = CX.CARD_W - 6;
const esc = s => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const turnsWord = n => { const a = n % 10, b = n % 100; return a === 1 && b !== 11 ? 'ход' : a >= 2 && a <= 4 && (b < 12 || b > 14) ? 'хода' : 'ходов'; };
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

function h(tag, attrs = {}, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
        if (v === undefined || v === null || v === false) continue;
        if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
        else if (k === 'class') el.className = v;
        else if (k === 'style') el.style.cssText = v;
        else if (k in el && k !== 'list') el[k] = v;
        else el.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : String(c));
    return el;
}

// The name of a node in lines of the card's width, as the card draws it (the same font): so the card's height, and the lines' ways round it, are
// known before anything is drawn. More than MAX_LINES: the last line ends in "…" (the whole name is in the tooltip and the panel).
const measure = document.createElement('canvas').getContext('2d');
function wrapName(text) {
    measure.font = NAME_FONT;
    const w = s => measure.measureText(s).width;
    const words = text.trim().split(/\s+/).filter(Boolean);
    const lines = [];
    let line = '';
    for (let word of words) {
        while (w(word) > NAME_W) {          // a word longer than the card: cut where it fits
            let k = word.length;
            while (k > 1 && w(word.slice(0, k) + '-') > NAME_W) k--;
            if (line) { lines.push(line); line = ''; }
            lines.push(word.slice(0, k) + '-');
            word = word.slice(k);
        }
        const next = line ? line + ' ' + word : word;
        if (w(next) <= NAME_W) line = next; else { lines.push(line); line = word; }
    }
    if (line) lines.push(line);
    if (lines.length > CX.MAX_LINES) {
        let last = lines.slice(CX.MAX_LINES - 1).join(' ');
        while (last && w(last + '…') > NAME_W) last = last.slice(0, -1);
        lines.length = CX.MAX_LINES - 1;
        lines.push(last.trimEnd() + '…');
    }
    return lines.length ? lines : [''];
}

export function makeConstructor(host, {data, cards, design, problems = [], onChange = () => {}, catalog = {}, blueprint = {}, art = {}, version = null, migrated = null}) {
    const hist = new T.History(design);
    const cur = () => hist.current;
    let sel = new Set(), selEdge = null, hotEdge = null;       // selected nodes (ids), one selected link {from, to}, the link under the mouse
    const view = {x: 0, y: 0, z: 1};
    let drag = null, clip = null, lastPointer = null, spaceDown = false, toastTimer = null, shown = false;

    // ---- the mod's levels: the palette, the keys, the hull's tiers, the names of the icons ----
    const modLevels = [...data.hull, ...data.chains.flatMap(c => c.levels)];
    const byShort = Object.fromEntries(modLevels.map(r => [r.short, r]));
    const modKeys = new Set(modLevels.map(r => r.short));
    const chainTitle = r => (cards[r.key] && cards[r.key].chain_title) || r.chain;
    const nodeOfMod = r => ({...T.fromModLevel(r, cards[r.key], data)});
    const hullNames = Object.fromEntries(data.hull.map(r => [r.level + 1, r.name]));
    const groupOrder = ['rifles', 'cannons', 'cupolas', 'bombs', 'harpoon', 'pub', 'deck'].filter(g => data.groups[g]).concat(Object.keys(data.groups).filter(g => !['rifles', 'cannons', 'cupolas', 'bombs', 'harpoon', 'pub', 'deck'].includes(g)));
    const crewCard = c => { const g = data.groups[c.group], o = g && g.options[c.option]; return o && o.unit_card && c.option !== g.mount ? {uc: o.unit_card, colour: g.card_frame || 'gold'} : null; };
    const unitsOf = n => n.crew.filter(crewCard).length;
    // the catalogue of effects (web/js/effects_model.mjs) over the export's game effects; the dwarfs' army units; the ship's details
    const fxCtx = {groups: data.groups, gameEffects: Object.fromEntries((catalog.game_effects || []).map(g => [g.key, g]))};
    const armyUnits = Object.fromEntries((catalog.army_units || []).map(u => [u.key, u]));
    const unitName = k => (armyUnits[k] ? armyUnits[k].name : k);
    fxCtx.unitName = unitName;          // the names of the units in an army effect's line
    // the army units the tree opens, by the line that opens them (its first level's id): the addressees an army effect picks from
    const unitLines = () => {
        const d = cur(), out = new Map();
        for (const n of d.nodes) for (const u of n.units || []) { const root = T.lineOf(d, n.id).ids[0]; if (!out.has(root)) out.set(root, []); if (!out.get(root).includes(u)) out.get(root).push(u); }
        return out;
    };
    const partsInfo = T.shipParts(blueprint, {...(art.places || {}), ...((data.art && data.art.layers) || {})});
    const partName = k => (partsInfo[k] ? partsInfo[k].name : k);
    // a new detail (part: null) named as a detail of the drawing is that detail (the game's mode links them so too, web/js/main.js)
    const partOfName = name => (Object.values(partsInfo).find(p => name && p.name === name) || {}).key || null;
    const checkCtx = {modKeys, units: unitsOf, unitName, partKnown: k => !!partsInfo[k], partDrawn: k => !!(partsInfo[k] && partsInfo[k].drawn), partName, partOfName};
    const CASTES = {melee_infantry: 'Пехота ближнего боя', missile_infantry: 'Стрелки', warmachine: 'Боевые машины', monster: 'Чудовища', cavalry: 'Кавалерия'};
    const VARIANT = {malakai: 'версия Малакая', grudge: 'награда за обиду'};
    let icons = null;
    const loadIcons = () => (icons ||= fetch('/api/tree_icons').then(r => r.json()).catch(() => ({buildings: [], effects: []})));
    // an icon's name for people: the buildings that use it (the mod's levels, the game's cards of the overview)
    const iconNames = {};
    for (const r of modLevels) { const p = nodeOfMod(r).icon; if (p && !(iconNames[p] || []).includes(r.name)) (iconNames[p] ||= []).push(r.name); }
    for (const c of Object.values(cards)) { const p = T.iconPath(c.icon); if (p && c.name && !(iconNames[p] || []).includes(c.name)) (iconNames[p] ||= []).push(c.name); }
    const EFFECT_NAMES = {agent: 'Герои', army: 'Армия', attrition: 'Потери', campaign_movement: 'Передвижение', dragon_slayer: 'Драконоборец', engineer: 'Инженер',
        experience: 'Опыт', general_ability: 'Способность', growth: 'Рост', magic_cooldown: 'Магия', military_spending: 'Содержание', replenishment: 'Пополнение',
        resource_dwarf_beer: 'Пиво', sphere_of_influence_size: 'Влияние', treasury: 'Казна'};
    const slotIcon = (path, cls = '') => h('span', {class: 'cx-slotpic ' + cls}, h('img', {src: url(path || D + 'icon_check.png'), alt: ''}));

    // ---- the layout ----
    host.innerHTML = '';
    const palette = h('aside', {class: 'cx-palette'});
    const cvWrap = h('div', {class: 'cx-middle'});
    const cv = h('div', {class: 'cx-canvas', tabIndex: 0});
    const status = h('div', {class: 'cx-status'});
    cvWrap.append(cv, status);
    const props = h('aside', {class: 'cx-props'});
    const propsFold = h('div', {class: 'cx-fold right', title: 'Показать свойства ( ] )', onclick: () => fold('props', false)}, h('span', {}, 'Свойства'));
    const palFold = h('div', {class: 'cx-fold left', title: 'Показать список построек ( [ )', onclick: () => fold('palette', false)}, h('span', {}, 'Постройки'));
    host.append(palFold, palette, cvWrap, props, propsFold);
    const rowsEl = h('div', {class: 'cx-rows'});
    const world = h('div', {class: 'cx-world'});
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('class', 'cx-edges');
    const nodesEl = h('div');
    world.append(svg, nodesEl);
    const toastEl = h('div', {class: 'cx-toast', style: 'display:none'});
    const tipEl = h('div', {class: 'cx-tip', style: 'display:none'});
    const dropEl = h('div', {class: 'cx-drop', style: 'display:none'});
    const bandEl = h('div', {class: 'cx-band', style: 'display:none'});
    world.append(dropEl);
    const warnList0 = h('div', {class: 'cx-warnlist', style: 'display:none'});
    cv.append(rowsEl, world, bandEl, warnList0, tipEl);
    const zoomText = h('span', {class: 'z'});
    const hintEl = h('span', {class: 'cx-hinttext'});
    const warnBtn = h('button', {class: 'cx-warnbtn', onclick: () => { warnList0.style.display = warnList0.style.display === 'none' ? '' : 'none'; renderWarnings(); }});
    status.append(h('span', {class: 'cx-zoom'},
        h('button', {title: 'Мельче (колесо мыши)', onclick: () => zoomAt(view.z / 1.2)}, '−'), zoomText,
        h('button', {title: 'Крупнее (колесо мыши)', onclick: () => zoomAt(view.z * 1.2)}, '+'),
        h('button', {title: 'Настоящий размер (1)', onclick: () => zoomAt(1)}, '100%'),
        h('button', {title: 'Показать всё дерево (F)', onclick: () => showAll()}, 'Показать всё')), hintEl, toastEl, warnBtn);
    const HINTS = {
        canvas: 'Двойной щелчок — новая постройка · фон — сдвиг · колесо — масштаб · Shift+рамка — несколько · ? — клавиши',
        node: 'Тяните — переставить · кружки сверху и снизу — связи · двойной щелчок — свойства',
        handle: 'Тяните к постройке, которую связать; на пустом месте — новая постройка со связью',
        edge: 'Щелчок — выделить связь · Delete — удалить · правая кнопка — развернуть',
    };
    const hint = k => { hintEl.textContent = HINTS[k] || k; };
    hint('canvas');

    // ---- the bar's tools ----
    const tools = document.getElementById('cx_tools');
    tools.innerHTML = '';
    const tb = {};
    const tbtn = (key, label, title, fn, cls = '') => (tb[key] = h('button', {title, onclick: fn, class: cls}, label));
    tools.append(
        tbtn('add', '+ Постройка', 'Новая пустая постройка в середине вида (N). Или двойной щелчок по пустому месту', () => addBlankAt(centerCell())),
        h('span', {class: 'sep'}),
        tbtn('undo', '↶ Отменить', '', () => undo()), tbtn('redo', '↷ Повторить', '', () => redo()),
        h('span', {class: 'sep'}),
        tbtn('dup', 'Копия', 'Сделать копию выделенного рядом (Ctrl+D)', () => duplicate()),
        tbtn('del', 'Удалить', 'Удалить выделенное (Delete)', () => deleteSelection()),
        h('span', {class: 'sep wide'}),
        tbtn('file', 'Файл ▾', 'Экспорт, импорт, вернуть сохранённое, очистить', e => fileMenu(e.currentTarget)),
        tbtn('keys', 'Клавиши', 'Все действия мыши и клавиш (?)', () => keysHelp()),
        h('span', {class: 'grow'}));
    const saveEl = h('span', {id: 'cx_save'});
    const retryBtn = h('button', {id: 'cx_retry', style: 'display:none', title: 'Сохранить в файл ещё раз', onclick: () => saveNow()}, 'Повторить');
    tools.append(saveEl, retryBtn);

    // ---- the side panels fold away ----
    const folded = {palette: false, props: false};
    try { Object.assign(folded, JSON.parse(localStorage.getItem('mtb_cx_folded') || '{}')); } catch (e) { /* no storage */ }
    function fold(which, on) {
        folded[which] = on;
        try { localStorage.setItem('mtb_cx_folded', JSON.stringify(folded)); } catch (e) { /* no storage */ }
        paintFolds();
    }
    function paintFolds() {
        const r0 = cv.getBoundingClientRect();
        palette.style.display = folded.palette ? 'none' : '';
        palFold.style.display = folded.palette ? 'flex' : 'none';
        props.style.display = folded.props ? 'none' : '';
        propsFold.style.display = folded.props ? 'flex' : 'none';
        // the world stays where it was on the screen
        const r1 = cv.getBoundingClientRect();
        view.x += r0.left - r1.left; view.y += r0.top - r1.top;
        if (shown) applyView();
    }

    // ---- coordinates ----
    const lineCache = new Map();
    const nameLines = n => { const k = n.name.trim() || 'без названия'; if (!lineCache.has(k)) lineCache.set(k, wrapName(k)); return lineCache.get(k); };
    const cardOf = (n, at = n) => T.cxCard({...n, col: at.col, row: at.row}, nameLines(n).length);
    const toWorld = (cx, cy) => { const r = cv.getBoundingClientRect(); return {x: (cx - r.left - view.x) / view.z, y: (cy - r.top - view.y) / view.z}; };
    const cellAt = (wx, wy) => T.cxCellAt(wx, wy);
    const inCanvas = (cx, cy) => { const r = cv.getBoundingClientRect(); return cx >= r.left && cx <= r.right && cy >= r.top && cy <= r.bottom; };
    const centerCell = () => { const r = cv.getBoundingClientRect(); const w = toWorld(r.left + r.width / 2, r.top + r.height / 2); const c = cellAt(w.x, w.y); return T.freeCell(cur(), c.col, c.row); };
    // the free cell nearest to (col, row), looked for upwards (dir 1) or downwards (-1) first
    const freeToward = (d, col, row, dir) => {
        for (let k = 0; k < 30; k++) if (!T.cellTaken(d, col, row + dir * k)) return {col, row: row + dir * k};
        return T.freeCell(d, col, row);
    };
    const applyView = () => {
        world.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.z})`;
        zoomText.textContent = Math.round(view.z * 100) + '%';
        cv.style.backgroundSize = `${CX.CW * view.z}px 100%`;
        cv.style.backgroundPosition = `${view.x}px 0`;
        renderRows();
    };
    function renderRows() {
        const r = cv.getBoundingClientRect();
        const top = -view.y / view.z, bottom = (r.height - view.y) / view.z;
        const from = Math.floor(-bottom / CX.CH), to = Math.ceil(-top / CX.CH) + 1;
        let html = '';
        for (let row = Math.max(from, -40); row <= Math.min(to, from + 120); row++) {
            const y = view.y + -row * CX.CH * view.z;
            html += `<div class="cx-row${row % 2 ? ' odd' : ''}" style="top:${y}px;height:${CX.CH * view.z}px">${row >= 0 ? `<span>Ряд ${row + 1}</span>` : ''}</div>`;
        }
        rowsEl.innerHTML = html;
    }
    function zoomAt(z, cx, cy) {
        const r = cv.getBoundingClientRect();
        if (cx === undefined) { cx = r.left + r.width / 2; cy = r.top + r.height / 2; }
        const w = toWorld(cx, cy);
        view.z = clamp(z, 0.3, 2.5);
        view.x = cx - r.left - w.x * view.z;
        view.y = cy - r.top - w.y * view.z;
        applyView();
    }
    function bounds(nodes = cur().nodes) {
        if (!nodes.length) return null;
        const cs = nodes.map(n => cardOf(n));
        return {x0: Math.min(...cs.map(c => c.x)) - 12, x1: Math.max(...cs.map(c => c.x + c.w)) + 12, y0: Math.min(...cs.map(c => c.y)) - 24, y1: Math.max(...cs.map(c => c.bottom)) + 16};
    }
    // «Показать всё» never makes the names smaller than READ_Z allows (11 px on the screen): a tree larger than that is shown from its root up,
    // centred across, and the status says how to see more (fold the panels, pan)
    const READ_Z = 11 / 14;
    function showAll(maxZ = 1.25) {
        const r = cv.getBoundingClientRect(), b = bounds();
        if (!b) { view.z = 1; const c = T.cxCard({col: 0, row: 0}); view.x = r.width / 2 - c.cx; view.y = r.height / 2 - c.y - 60; applyView(); return; }
        const fit = Math.min(maxZ, (r.width - 40) / (b.x1 - b.x0), (r.height - 30) / (b.y1 - b.y0));
        view.z = clamp(Math.max(fit, READ_Z), READ_Z, 2.5);
        const w = (b.x1 - b.x0) * view.z, hh = (b.y1 - b.y0) * view.z;
        view.x = w <= r.width ? (r.width - w) / 2 - b.x0 * view.z : 12 - b.x0 * view.z + (r.width - 24 - w) / 2;
        view.y = hh <= r.height ? (r.height - hh) / 2 - b.y0 * view.z : r.height - 12 - b.y1 * view.z;
        applyView();
        if (fit < READ_Z && shown) toast(folded.palette && folded.props ? 'Дерево целиком не помещается при читаемом размере — двигайте полотно мышью'
            : 'Дерево целиком не помещается при читаемом размере. Сверните боковые панели (клавиша \\) или двигайте полотно мышью');
    }
    function reveal(id) {
        const n = T.byId(cur(), id);
        if (!n) return;
        const r = cv.getBoundingClientRect(), c = cardOf(n);
        const sx = view.x + c.cx * view.z, sy = view.y + (c.y + N / 2) * view.z;
        if (sx < 40 || sx > r.width - 40 || sy < 40 || sy > r.height - 40) { view.x = r.width / 2 - c.cx * view.z; view.y = r.height / 2 - (c.y + N / 2) * view.z; applyView(); }
        const el = nodesEl.querySelector(`[data-id="${CSS.escape(id)}"]`);
        if (el) { el.classList.remove('flash'); void el.offsetWidth; el.classList.add('flash'); }
    }

    // ---- drawing the tree ----
    let warnList = [];
    function renderCanvas(over = null) {         // over: {id: {col, row}} while nodes are dragged
        const d = cur();
        const place = n => (over && over[n.id] ? over[n.id] : n);
        const warned = new Set(warnList.flatMap(w => w.nodes));
        nodesEl.innerHTML = '';
        for (const n of d.nodes) {
            const c = cardOf(n, place(n)), lines = nameLines(n);
            const frame = n.branch ? `/art/branch_frame_${n.branch}.png` : url(D + 'building_frame_plain.png');
            const full = T.resolve(d, n.id).full, lvl = T.inLine(d, n.id) ? T.levelOf(d, n.id) : 0;
            const crew = full.crew.map(x => crewCard(x.c)).filter(Boolean);
            const el = h('div', {class: 'cx-node' + (sel.has(n.id) ? ' sel' : '') + (over && over[n.id] ? ' moving' : '') + (lvl ? ' leveled' : ''), 'data-id': n.id,
                                 style: `left:${c.x}px;top:${c.y}px;height:${c.bottom - c.y + 4}px`, title: nodeTitle(n)},
                h('div', {class: 'slot'},
                    h('img', {src: url(D + 'building_frame.png'), alt: ''}),
                    h('img', {src: url(n.icon || D + 'icon_check.png'), alt: ''}),
                    h('img', {src: frame, alt: ''}),
                    // the level in its line: the game's numeral at the slot's lower left (building_frame.twui.xml, building_level, 20 x 20 at 0, 54)
                    lvl ? (lvl <= 5 ? h('img', {class: 'lvl', src: url(D + `settlement_silver_numeral_${lvl}.png`), alt: T.roman(lvl), title: `Уровень ${T.roman(lvl)} линейки`})
                        : h('span', {class: 'lvl txt', title: `Уровень ${T.roman(lvl)} линейки`}, T.roman(lvl))) : null,
                    h('div', {class: 'price' + (n.cost ? '' : ' none')}, h('img', {src: url(D + 'icon_treasury.png'), alt: ''}), h('span', {class: 'co'}, n.cost ? String(n.cost) : 'нет цены'),
                        h('img', {src: url(D + 'icon_hourglass.png'), alt: '', class: 'hg'}), h('span', {class: 'tu'}, String(n.turns)))),
                crew.length ? h('div', {class: 'thumbs'}, crew.map((k, i) => h('div', {class: 'card', style: `top:${i * Math.min(16, 46 / Math.max(1, crew.length - 1))}px`},
                    h('img', {src: url(k.uc.picture), alt: ''}), h('img', {src: url(`ui/skins/tww3_mtb/unit_card_build_frame_${k.colour}.png`), alt: ''})))) : null,
                army({units: full.units.map(x => x.u)}),
                h('div', {class: 'name' + (n.name.trim() ? '' : ' empty')}, ...lines.flatMap((l, i) => (i ? [h('br'), l] : [l]))),
                warned.has(n.id) ? h('div', {class: 'warn'}, '!') : null,
                h('div', {class: 'hd up', title: 'Тяните к постройке, которая строится ПОСЛЕ этой'}),
                h('div', {class: 'hd down', style: `top:${c.bottom - c.y + 1}px`, title: 'Тяните к постройке, которая нужна ДО этой'}));
            nodesEl.append(el);
        }
        renderEdges(over);
    }
    // the army units a node opens: the game's small cards in the game's own frame, left of the slot (the crew's, in the crew's colour, are right of it)
    function army(n) {
        const list = (n.units || []).map(k => armyUnits[k]).filter(Boolean);
        return list.length ? h('div', {class: 'army'}, list.map((u, i) => h('div', {class: 'card', style: `top:${i * Math.min(16, 46 / Math.max(1, list.length - 1))}px`},
            h('img', {src: url(u.card.picture), alt: ''}), h('img', {src: url(D + 'unit_card_build_frame.png'), alt: ''})))) : null;
    }
    function nodeTitle(n) {
        const d = cur();
        const req = n.requires.map(p => T.byId(d, p)).filter(Boolean).map(T.label);
        const lvl = T.inLine(d, n.id) ? T.levelOf(d, n.id) : 0, first = lvl ? T.byId(d, T.lineOf(d, n.id).ids[0]) : null;
        return [n.name || 'без названия', `${n.cost} золота, ${n.turns} ${turnsWord(n.turns)}${n.tier ? `, тир корпуса ${n.tier}` : ''}`,
            lvl ? `Уровень ${T.roman(lvl)} линейки «${T.label(first)}»${n.prev && n.inherit ? ', наследует прошлый уровень' : ''}` : '',
            req.length ? 'Требует: ' + req.join(', ') : 'Ничего не требует', n.mod_key ? 'Мод: ' + n.mod_key : 'Новая постройка (нет в моде)',
            (n.units || []).length ? 'Открывает найм: ' + n.units.map(unitName).join(', ') : '',
            (n.parts || []).length ? 'На корабле: ' + n.parts.map(p => (p.part ? partName(p.part) : p.name || 'новая деталь')).join(', ') : '',
            n.note ? 'Заметка: ' + n.note : ''].filter(Boolean).join('\n');
    }
    let tempLink = null;        // {a: {x, y}, b: {x, y}, bad}
    function renderEdges(over = null) {
        const d = cur();
        const placed = over ? {...d, nodes: d.nodes.map(n => (over[n.id] ? {...n, ...over[n.id]} : n))} : d;
        const b = bounds(placed.nodes) || {x0: 0, x1: 100, y0: 0, y1: 100};
        const x0 = b.x0 - 400, y0 = b.y0 - 400, w = b.x1 - b.x0 + 800, hh = b.y1 - b.y0 + 800;
        svg.setAttribute('style', `left:${x0}px;top:${y0}px;width:${w}px;height:${hh}px`);
        svg.setAttribute('viewBox', `${x0} ${y0} ${w} ${hh}`);
        const routes = T.cxRoutes(placed, n => nameLines(n).length);
        const focus = sel.size ? sel : null;
        let s = '';
        for (const [key, pts] of Object.entries(routes)) {
            const [from, to] = key.split('|');
            const n = T.byId(d, to);
            const colour = LINE[n.branch || 'trunk'];
            const path = T.roundedPath(pts);
            const [ex, ey] = pts[pts.length - 1];
            const isSel = selEdge && selEdge.from === from && selEdge.to === to;
            // the next level of the same line: a double line (a wide one in the branch's colour with a dark core), as a rail of the line
            const line = n.prev === from;
            const hot = isSel || hotEdge === key || (focus && (focus.has(from) || focus.has(to)));
            const dim = !hot && (focus || hotEdge || selEdge);
            s += `<g data-edge="${esc(key)}" data-pts="${esc(JSON.stringify(pts))}" class="${hot ? 'hot' : ''}${dim ? ' dim' : ''}${line ? ' lineedge' : ''}">`
                + (isSel ? `<path class="halo" d="${path}"/>` : '')
                + (line ? `<path class="ln line" d="${path}" stroke="${colour}"/><path class="ln core" d="${path}"/>` : `<path class="ln" d="${path}" stroke="${colour}"/>`)
                + `<path class="ar" d="M${ex - (line ? 7 : 5)} ${ey + (line ? 9 : 7)} L${ex} ${ey} L${ex + (line ? 7 : 5)} ${ey + (line ? 9 : 7)} Z" fill="${colour}"/>`
                + `<path class="hit" d="${path}"/></g>`;
        }
        if (tempLink) s += `<path class="temp${tempLink.bad ? ' bad' : ''}" d="M${tempLink.a.x} ${tempLink.a.y} L${tempLink.b.x} ${tempLink.b.y}"/>`;
        svg.innerHTML = s;
        // the nodes of the link under the mouse
        for (const el of nodesEl.querySelectorAll('.linkhot')) el.classList.remove('linkhot');
        const hk = hotEdge || (selEdge && selEdge.from + '|' + selEdge.to);
        if (hk) for (const id of hk.split('|')) { const el = nodesEl.querySelector(`[data-id="${CSS.escape(id)}"]`); if (el) el.classList.add('linkhot'); }
    }

    // ---- changes: one step of the history each, saved at once ----
    function commit(label, fn, merge = null, {props: p = true} = {}) {
        const r = hist.commit(label, fn, merge);
        if (r.changed) changed({props: p});
        return r;
    }
    function changed({props: p = true} = {}) {
        const d = cur();
        sel = new Set([...sel].filter(id => T.byId(d, id)));
        if (selEdge && !(T.byId(d, selEdge.to) && T.byId(d, selEdge.to).requires.includes(selEdge.from))) selEdge = null;
        warnList = T.warnings(d, checkCtx);
        renderCanvas();
        renderWarnings();
        renderPalette();
        updateTools();
        if (p) renderProps(); else refreshPropsLive();
        if (modalRedraw) modalRedraw();
        scheduleSave();
        onChange(d);
    }
    // the selection is painted on the elements there are (no new elements: a double click must find the same node it began on)
    function select(ids, {edge = null, keepProps = false} = {}) {
        sel = new Set(ids);
        selEdge = edge;
        for (const el of nodesEl.querySelectorAll('.cx-node')) el.classList.toggle('sel', sel.has(el.dataset.id));
        renderEdges();
        updateTools();
        if (!keepProps) renderProps();
    }
    function undo() {
        const focus = rememberFocus();
        const label = hist.undo();
        if (label === null) { toast('Отменять нечего'); return; }
        changed();
        restoreFocus(focus);
        toast('Отменено: ' + label);
    }
    function redo() {
        const focus = rememberFocus();
        const label = hist.redo();
        if (label === null) { toast('Повторять нечего'); return; }
        changed();
        restoreFocus(focus);
        toast('Повторено: ' + label);
    }
    const rememberFocus = () => { const a = document.activeElement; return a && a.dataset && a.dataset.field ? {field: a.dataset.field, start: a.selectionStart, end: a.selectionEnd} : null; };
    const restoreFocus = f => {
        if (!f) return;
        const el = props.querySelector(`[data-field="${f.field}"]`);
        if (!el) return;
        el.focus();
        try { el.setSelectionRange(Math.min(f.start, el.value.length), Math.min(f.end, el.value.length)); } catch (e) { /* not a text field */ }
    };

    // ---- operations ----
    function addBlankAt(cell, fields = {}) {
        let id;
        commit('Новая постройка', d => { const c = T.freeCell(d, cell.col, cell.row); id = T.addNode(d, {name: 'Новая постройка', cost: 1000, turns: 1, ...fields, col: c.col, row: c.row}); });
        select([id]);
        reveal(id);
        focusName(true);
        return id;
    }
    function focusName(selectAll) {
        if (folded.props) fold('props', false);
        const el = props.querySelector('[data-field="name"]');
        if (el) { el.focus(); if (selectAll) el.select(); }
    }
    function addFromMod(short, cell) {
        const r = byShort[short];
        if (!r) return;
        let id;
        const links = [];
        const already = cur().nodes.find(n => n.mod_key === short);
        commit(`Постройка «${r.name}»`, d => {
            const c = T.freeCell(d, cell.col, cell.row);
            id = T.addNode(d, {...nodeOfMod(r), col: c.col, row: c.row});
            // what the mod itself says: the level below and the requirements on the canvas are linked at once; and the levels above that wait for it
            for (const need of T.modNeeds(r, data)) for (const p of d.nodes.filter(n => n.mod_key === need && n.id !== id)) if (T.addEdge(d, p.id, id).ok) links.push(T.label(p) + ' → ' + T.label(T.byId(d, id)));
            for (const q of d.nodes) if (q.id !== id && q.mod_key && byShort[q.mod_key] && T.modNeeds(byShort[q.mod_key], data).includes(short)) if (T.addEdge(d, id, q.id).ok) links.push(T.label(T.byId(d, id)) + ' → ' + T.label(q));
            const parent = d.nodes.find(n => T.byId(d, id).requires.includes(n.id) && n.branch);
            if (parent && !T.byId(d, id).branch) T.byId(d, id).branch = parent.branch;
            // the line of the mod's chain: the level below on the canvas is its previous level, the level above continues it (inheritance off:
            // a level of the mod comes with its whole set)
            if (T.linkModChains(d, data)) links.push('линейка уровней мода');
        });
        select([id]);
        reveal(id);
        if (already) toast(`«${r.name}» уже есть на полотне — это вторая копия с тем же ключом мода (см. проверки)`, true);
        else if (links.length) toast('Связи по данным мода: ' + links.join('; ') + '. Ctrl+Z — убрать');
    }
    function deleteSelection() {
        if (selEdge) {
            const {from, to} = selEdge;
            commit('Удаление связи', d => T.deleteEdge(d, from, to));
            selEdge = null; renderEdges(); renderProps();
            toast('Связь удалена. Ctrl+Z — вернуть');
            return;
        }
        if (!sel.size) { toast('Ничего не выделено'); return; }
        const ids = [...sel];
        let r;
        commit(ids.length === 1 ? `Удаление «${T.label(T.byId(cur(), ids[0]))}»` : `Удаление ${ids.length} построек`, d => { r = T.deleteNodes(d, ids); });
        select([]);
        toast(`Удалено построек: ${r.nodes}, связей: ${r.links}. Ctrl+Z — вернуть`);
    }
    function duplicate() {
        if (!sel.size) { toast('Выделите постройки для копии'); return; }
        let ids;
        commit('Копия', d => { ids = T.duplicateNodes(d, [...sel]); });
        select(ids);
    }
    function copy(cut = false) {
        if (!sel.size) { toast('Выделите постройки'); return; }
        clip = T.copyNodes(cur(), [...sel]);
        if (cut) { const n = sel.size; deleteSelection(); toast(`Вырезано: ${n}. Ctrl+V — вставить`); } else toast(`Скопировано: ${clip.nodes.length}. Ctrl+V — вставить`);
    }
    function paste(cell) {
        if (!clip) { toast('Буфер пуст: сначала Ctrl+C'); return; }
        let ids;
        const at = cell || (lastPointer && inCanvas(lastPointer.x, lastPointer.y) ? cellAt(toWorld(lastPointer.x, lastPointer.y).x, toWorld(lastPointer.x, lastPointer.y).y) : centerCell());
        commit('Вставка', d => { ids = T.pasteNodes(d, clip, at.col, at.row); });
        select(ids);
    }
    function link(from, to) {
        const c = T.canLink(cur(), from, to);
        if (!c.ok) { toast(c.why, true); return false; }
        commit('Связь', d => T.addEdge(d, from, to));
        select([], {edge: {from, to}});
        return true;
    }
    function linkSelected() {
        if (sel.size !== 2) { toast('Для связи выделите две постройки (Shift+щелчок)', true); return; }
        const [a, b] = [...sel].map(id => T.byId(cur(), id));
        const [lo, hi] = a.row <= b.row ? [a, b] : [b, a];       // the lower is built first
        link(lo.id, hi.id);
    }
    function nudge(dc, dr) {
        if (!sel.size) return;
        const ids = [...sel], d = cur(), set = new Set(ids);
        if (d.nodes.some(n => set.has(n.id) && T.cellTaken(d, n.col + dc, n.row + dr, set))) { toast('Клетка занята', true); return; }
        commit('Сдвиг', x => T.moveNodes(x, ids, dc, dr), 'nudge:' + ids.join());
    }
    // The next level of a line: over the node, requires it, continues it and inherits all it gives; the same icon, branch, tier, price and turns;
    // the name empty, in focus to be typed
    function addNextLevel(id) {
        const n = T.byId(cur(), id);
        const fork = T.nextLevels(cur(), id).length;
        let nid;
        commit('Следующий уровень', d => {
            const c = freeToward(d, n.col, n.row + 1, 1);
            nid = T.addNode(d, {name: '', cost: n.cost, turns: n.turns, tier: n.tier, icon: n.icon, branch: n.branch, prev: id, inherit: true, col: c.col, row: c.row});
            T.addEdge(d, id, nid);
        });
        select([nid]);
        reveal(nid);
        focusName(true);
        toast(fork ? `У «${T.label(n)}» уже есть следующий уровень: линейка ветвится (см. проверки). Ctrl+Z — убрать` : `Уровень ${T.roman(T.levelOf(cur(), nid))} линейки: наследует всё от «${T.label(n)}». Введите название`, !!fork);
    }
    function addLinked(id, dir) {
        const n = T.byId(cur(), id);
        let nid;
        commit('Новая постройка со связью', d => {
            const c = freeToward(d, n.col, n.row + (dir === 'up' ? 1 : -1), dir === 'up' ? 1 : -1);
            nid = T.addNode(d, {name: 'Новая постройка', cost: 1000, turns: 1, branch: n.branch, col: c.col, row: c.row});
            if (dir === 'up') T.addEdge(d, id, nid); else T.addEdge(d, nid, id);
        });
        select([nid]);
        reveal(nid);
        focusName(true);
    }

    // ---- the mouse on the canvas ----
    // an old message goes at the next action
    host.addEventListener('pointerdown', () => hideToast(), true);
    cv.addEventListener('pointerdown', e => {
        hideMenu();
        lastPointer = {x: e.clientX, y: e.clientY};
        if (e.target.closest('.cx-warnlist, .cx-banner')) return;
        if (e.button === 1 || (e.button === 0 && spaceDown)) { e.preventDefault(); startPan(e, false); return; }
        if (e.button !== 0) return;
        if (document.activeElement && document.activeElement !== cv && props.contains(document.activeElement)) document.activeElement.blur();
        cv.focus({preventScroll: true});
        const nodeEl = e.target.closest('.cx-node'), hd = e.target.closest('.hd'), edgeEl = e.target.closest('[data-edge]');
        if (hd && nodeEl) { startLink(nodeEl.dataset.id, hd.classList.contains('up') ? 'up' : 'down', e); return; }
        if (nodeEl) {
            const id = nodeEl.dataset.id;
            if (e.shiftKey || e.ctrlKey || e.metaKey) {
                const s = new Set(sel);
                if (s.has(id)) s.delete(id); else s.add(id);
                select([...s]);
                return;
            }
            const was = sel.has(id) && sel.size > 1;
            if (!sel.has(id)) select([id]);
            startMove(id, e, was);
            return;
        }
        if (edgeEl) {
            const [from, to] = edgeEl.getAttribute('data-edge').split('|');
            select([], {edge: {from, to}});
            return;
        }
        if (e.shiftKey || e.ctrlKey) { startBand(e); return; }
        startPan(e, true);
    });
    window.addEventListener('pointermove', e => { lastPointer = {x: e.clientX, y: e.clientY}; if (drag) drag.move(e); });
    window.addEventListener('pointerup', e => { if (drag) { const d = drag; drag = null; d.up(e); } });
    // what is under the mouse: the hint of the status line, the link lit with its two buildings
    cv.addEventListener('pointerover', e => {
        if (drag) return;
        const edgeEl = e.target.closest('[data-edge]');
        const key = edgeEl ? edgeEl.getAttribute('data-edge') : null;
        hint(e.target.closest('.hd') ? 'handle' : e.target.closest('.cx-node') ? 'node' : edgeEl ? 'edge' : 'canvas');
        if (key !== hotEdge) { hotEdge = key; renderEdges(); }
    });
    cv.addEventListener('pointerleave', () => { if (hotEdge) { hotEdge = null; renderEdges(); } });
    cv.addEventListener('dblclick', e => {
        const nodeEl = e.target.closest('.cx-node');
        if (nodeEl) { select([nodeEl.dataset.id]); focusName(true); return; }
        if (e.target.closest('.cx-warnlist, [data-edge], .cx-banner')) return;
        const w = toWorld(e.clientX, e.clientY);
        addBlankAt(cellAt(w.x, w.y));
    });
    cv.addEventListener('wheel', e => {
        e.preventDefault();
        zoomAt(view.z * Math.exp(-e.deltaY * 0.0015), e.clientX, e.clientY);
    }, {passive: false});
    cv.addEventListener('contextmenu', e => {
        e.preventDefault();
        const nodeEl = e.target.closest('.cx-node'), edgeEl = e.target.closest('[data-edge]');
        const w = toWorld(e.clientX, e.clientY), cell = cellAt(w.x, w.y);
        if (nodeEl) {
            const id = nodeEl.dataset.id;
            if (!sel.has(id)) select([id]);
            const n = T.byId(cur(), id), many = sel.size > 1;
            showMenu(e.clientX, e.clientY, [
                !many && ['Переименовать', 'F2', () => focusName(true)],
                !many && ['Следующий уровень (та же линейка, наследует её)', '', () => addNextLevel(id)],
                !many && ['Новая постройка над ней (требует её)', '', () => addLinked(id, 'up')],
                !many && ['Новая постройка под ней (нужна ей)', '', () => addLinked(id, 'down')],
                many && sel.size === 2 && ['Связать две выделенные', 'L', linkSelected],
                '-',
                ['Копия рядом', 'Ctrl+D', duplicate], ['Копировать', 'Ctrl+C', () => copy()], ['Вырезать', 'Ctrl+X', () => copy(true)],
                ['Вставить', 'Ctrl+V', () => paste(cell), !clip],
                '-',
                !many && ['Убрать все связи постройки', '', () => commit('Связи убраны', d => { T.byId(d, id).requires = []; for (const c of d.nodes) c.requires = c.requires.filter(p => p !== id); }), !n.requires.length && !T.children(cur(), id).length],
                [many ? `Удалить ${sel.size} построек` : 'Удалить', 'Delete', deleteSelection],
            ]);
        } else if (edgeEl) {
            const [from, to] = edgeEl.getAttribute('data-edge').split('|');
            select([], {edge: {from, to}});
            showMenu(e.clientX, e.clientY, [['Развернуть связь', '', () => reverse(from, to)], ['Удалить связь', 'Delete', deleteSelection]]);
        } else {
            showMenu(e.clientX, e.clientY, [
                ['Новая постройка здесь', 'двойной щелчок', () => addBlankAt(cell)],
                ['Вставить сюда', 'Ctrl+V', () => paste(cell), !clip],
                '-', ['Выделить всё', 'Ctrl+A', () => select(cur().nodes.map(n => n.id))], ['Показать всё', 'F', () => showAll()]]);
        }
    });
    function reverse(from, to) {
        let r;
        commit('Связь развёрнута', d => { r = T.reverseEdge(d, from, to); return r.ok; });
        if (!r.ok) toast(r.why, true); else select([], {edge: {from: to, to: from}});
    }

    function startPan(e, clearOnClick) {
        const v0 = {...view}, x0 = e.clientX, y0 = e.clientY;
        let moved = false;
        drag = {
            move: ev => {
                if (!moved && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 3) return;
                moved = true;
                cv.classList.add('panning');
                view.x = v0.x + ev.clientX - x0; view.y = v0.y + ev.clientY - y0;
                applyView();
            },
            up: () => { cv.classList.remove('panning'); if (!moved && clearOnClick && (sel.size || selEdge)) select([]); },
        };
    }
    function startMove(id, e, wasMany) {
        const d = cur(), ids = [...sel], set = new Set(ids), w0 = toWorld(e.clientX, e.clientY);
        let dc = 0, dr = 0, moved = false, bad = false, outside = false;
        drag = {
            move: ev => {
                const w = toWorld(ev.clientX, ev.clientY);
                if (!moved && Math.hypot(w.x - w0.x, w.y - w0.y) * view.z < 4) return;
                moved = true;
                cv.classList.add('moving');
                outside = !inCanvas(ev.clientX, ev.clientY);
                dc = Math.round((w.x - w0.x) / CX.CW); dr = -Math.round((w.y - w0.y) / CX.CH);
                const over = {};
                for (const n of d.nodes) if (set.has(n.id)) over[n.id] = {col: n.col + dc, row: n.row + dr};
                bad = Object.values(over).some(p => T.cellTaken(d, p.col, p.row, set));
                renderCanvas(over);
                for (const el of nodesEl.querySelectorAll('.cx-node.moving')) el.classList.toggle('bad', bad || outside);
                showTip(ev, outside ? 'Отпустите над полотном — здесь постройка вернётся на место' : bad ? 'Клетка занята' : `${dc >= 0 ? '→' : '←'} ${Math.abs(dc)}  ${dr >= 0 ? '↑' : '↓'} ${Math.abs(dr)}`, bad || outside);
            },
            up: ev => {
                hideTip();
                cv.classList.remove('moving');
                if (!moved) { if (wasMany) select([id]); return; }
                if (!inCanvas(ev.clientX, ev.clientY)) { renderCanvas(); toast('Отпущено за полотном: постройки остались на месте', true); return; }
                if (bad || (!dc && !dr)) { renderCanvas(); if (bad) toast('Клетка занята: постройки остались на месте', true); return; }
                commit(ids.length > 1 ? `Перемещение ${ids.length} построек` : 'Перемещение', x => T.moveNodes(x, ids, dc, dr));
            },
        };
    }
    function startLink(id, dir, e) {
        const n = T.byId(cur(), id), c = cardOf(n);
        const a = {x: c.cx, y: dir === 'up' ? c.y : c.bottom};
        cv.classList.add('linking');
        const srcEl = nodesEl.querySelector(`[data-id="${CSS.escape(id)}"]`);
        if (srcEl) srcEl.classList.add('source');
        let target = null, check = null, onSelf = false;
        const mark = () => { for (const el of nodesEl.querySelectorAll('.target-ok, .target-bad')) el.classList.remove('target-ok', 'target-bad'); };
        drag = {
            move: ev => {
                const w = toWorld(ev.clientX, ev.clientY);
                const under = document.elementFromPoint(ev.clientX, ev.clientY);
                const tEl = under && under.closest && under.closest('.cx-node');
                onSelf = !!(tEl && tEl.dataset.id === id);
                target = tEl && !onSelf ? tEl.dataset.id : null;
                mark();
                check = target ? (dir === 'up' ? T.canLink(cur(), id, target) : T.canLink(cur(), target, id)) : null;
                if (tEl && target) tEl.classList.add(check.ok ? 'target-ok' : 'target-bad');
                tempLink = {a, b: w, bad: !!(check && !check.ok)};
                renderEdges();
                const tn = target && T.byId(cur(), target);
                showTip(ev, onSelf ? 'Отпустите на другой постройке' : !target ? (dir === 'up' ? 'Отпустите на постройке, которая строится после, — или на пустом месте: новая' : 'Отпустите на постройке, которая нужна до, — или на пустом месте: новая')
                    : check.ok ? (dir === 'up' ? `«${T.label(tn)}» будет требовать «${T.label(n)}»` : `«${T.label(n)}» будет требовать «${T.label(tn)}»`) : check.why, check && !check.ok);
            },
            up: ev => {
                cv.classList.remove('linking');
                if (srcEl) srcEl.classList.remove('source');
                tempLink = null; mark(); hideTip(); renderEdges();
                if (onSelf) return;                                   // let go on itself: nothing
                if (target) { if (dir === 'up') link(id, target); else link(target, id); return; }
                if (!inCanvas(ev.clientX, ev.clientY)) return;
                const w = toWorld(ev.clientX, ev.clientY);
                const cell = cellAt(w.x, w.y);
                let nid;
                // the new building in the cell let go on; when it is taken, the nearest free one above (a next building) or below (a needed one)
                commit('Новая постройка со связью', d => {
                    const p = T.cellTaken(d, cell.col, cell.row) ? freeToward(d, cell.col, cell.row, dir === 'up' ? 1 : -1) : cell;
                    nid = T.addNode(d, {name: 'Новая постройка', cost: 1000, turns: 1, branch: n.branch, col: p.col, row: p.row});
                    if (dir === 'up') T.addEdge(d, id, nid); else T.addEdge(d, nid, id);
                });
                select([nid]);
                focusName(true);
            },
        };
        drag.move(e);
    }
    function startBand(e) {
        const r = cv.getBoundingClientRect(), x0 = e.clientX - r.left, y0 = e.clientY - r.top, base = new Set(sel);
        drag = {
            move: ev => {
                const x1 = ev.clientX - r.left, y1 = ev.clientY - r.top;
                Object.assign(bandEl.style, {display: '', left: Math.min(x0, x1) + 'px', top: Math.min(y0, y1) + 'px', width: Math.abs(x1 - x0) + 'px', height: Math.abs(y1 - y0) + 'px'});
                const a = toWorld(Math.min(x0, x1) + r.left, Math.min(y0, y1) + r.top), b = toWorld(Math.max(x0, x1) + r.left, Math.max(y0, y1) + r.top);
                const inside = cur().nodes.filter(n => { const c = cardOf(n); return c.slotX + N > a.x && c.slotX < b.x && c.y + N > a.y && c.y < b.y; }).map(n => n.id);
                sel = new Set([...base, ...inside]);
                for (const el of nodesEl.querySelectorAll('.cx-node')) el.classList.toggle('sel', sel.has(el.dataset.id));
            },
            up: () => { bandEl.style.display = 'none'; select([...sel]); },
        };
    }
    function showTip(ev, text, bad) {
        const r = cv.getBoundingClientRect();
        tipEl.textContent = text;
        tipEl.className = 'cx-tip' + (bad ? ' bad' : '');
        tipEl.style.display = '';
        tipEl.style.left = clamp(ev.clientX - r.left + 16, 4, r.width - tipEl.offsetWidth - 6) + 'px';
        tipEl.style.top = clamp(ev.clientY - r.top + 18, 4, r.height - tipEl.offsetHeight - 4) + 'px';
    }
    const hideTip = () => { tipEl.style.display = 'none'; };
    function toast(text, bad = false) {
        toastEl.textContent = text;
        toastEl.className = 'cx-toast' + (bad ? ' bad' : '');
        toastEl.style.display = '';
        hintEl.style.display = 'none';
        clearTimeout(toastTimer);
        toastTimer = setTimeout(hideToast, bad ? 4500 : 2600);
    }
    function hideToast() { clearTimeout(toastTimer); toastEl.style.display = 'none'; hintEl.style.display = ''; }

    // ---- the context menu ----
    let menuEl = null;
    function showMenu(x, y, items) {
        hideMenu();
        menuEl = h('div', {class: 'cx-menu'});
        for (const it of items.filter(Boolean)) {
            if (it === '-') { menuEl.append(h('hr')); continue; }
            const [label, key, fn, off] = it;
            menuEl.append(h('div', {class: off ? 'off' : '', onclick: () => { if (off) return; hideMenu(); fn(); }}, h('span', {}, label), key ? h('kbd', {}, key) : ''));
        }
        document.body.append(menuEl);
        const r = menuEl.getBoundingClientRect();
        menuEl.style.left = Math.min(x, innerWidth - r.width - 6) + 'px';
        menuEl.style.top = Math.min(y, innerHeight - r.height - 6) + 'px';
    }
    function hideMenu() { if (menuEl) { menuEl.remove(); menuEl = null; } }
    document.addEventListener('pointerdown', e => { if (menuEl && !menuEl.contains(e.target)) hideMenu(); }, true);

    // ---- the keys ----
    window.addEventListener('keydown', e => {
        if (!shown) return;
        const k = e.key, ctrl = e.ctrlKey || e.metaKey, inField = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || '');
        if (document.querySelector('.cx-shade')) {
            if (document.querySelector('.cx-shade.sticky')) return;
            if (k === 'Escape') { e.preventDefault(); closeModal(); return; }
            // undo and redo inside a picker: the picker shows the state after it
            if (ctrl && (k === 'z' || k === 'Z' || k === 'я' || k === 'Я') && !e.shiftKey && !inField) { e.preventDefault(); undo(); return; }
            if (ctrl && (k === 'y' || k === 'Y' || k === 'н' || k === 'Н') && !inField) { e.preventDefault(); redo(); return; }
            return;
        }
        if (!['Shift', 'Control', 'Alt', 'Meta'].includes(k)) hideToast();
        if (ctrl && (k === 'z' || k === 'Z' || k === 'я' || k === 'Я') && !e.shiftKey) { e.preventDefault(); flushField(); undo(); return; }
        if (ctrl && ((k === 'y' || k === 'Y' || k === 'н' || k === 'Н') || ((k === 'z' || k === 'Z' || k === 'я' || k === 'Я') && e.shiftKey))) { e.preventDefault(); redo(); return; }
        if (inField) { if (k === 'Escape') e.target.blur(); return; }
        const code = e.code;
        const onCanvas = document.activeElement === cv;
        if (k === ' ') { if (onCanvas) { spaceDown = true; e.preventDefault(); } return; }
        // deleting: only with the canvas in focus (a click on it); after a click on a button of a panel the keys do not delete
        if (k === 'Delete' || k === 'Backspace') { if (onCanvas) { e.preventDefault(); deleteSelection(); } return; }
        if (code === 'BracketLeft' && !ctrl) { fold('palette', !folded.palette); return; }
        if (code === 'BracketRight' && !ctrl) { fold('props', !folded.props); return; }
        if (code === 'Backslash' && !ctrl) { const on = !(folded.palette && folded.props); fold('palette', on); fold('props', on); return; }
        if (ctrl && code === 'KeyD') { e.preventDefault(); duplicate(); }
        else if (ctrl && code === 'KeyC') { if (onCanvas) { e.preventDefault(); copy(); } }
        else if (ctrl && code === 'KeyX') { if (onCanvas) { e.preventDefault(); copy(true); } }
        else if (ctrl && code === 'KeyV') { if (onCanvas) { e.preventDefault(); paste(); } }
        else if (ctrl && code === 'KeyA') { e.preventDefault(); select(cur().nodes.map(n => n.id)); }
        else if (k === 'Escape') { hideMenu(); select([]); }
        else if (ctrl) return;
        else if (code === 'KeyF') showAll();
        else if (k === '1' || k === '0') zoomAt(1);
        else if (code === 'KeyN') addBlankAt(centerCell());
        else if (code === 'KeyL') linkSelected();
        else if (k === 'F2' || k === 'Enter') { if (sel.size === 1) { e.preventDefault(); focusName(true); } }
        else if (k === '?' || (code === 'Slash' && e.shiftKey)) keysHelp();
        else if (k.startsWith('Arrow') && sel.size && onCanvas) { e.preventDefault(); nudge(k === 'ArrowLeft' ? -1 : k === 'ArrowRight' ? 1 : 0, k === 'ArrowUp' ? 1 : k === 'ArrowDown' ? -1 : 0); }
    });
    window.addEventListener('keyup', e => { if (e.key === ' ') spaceDown = false; });

    // ---- the palette ----
    let palQuery = '';
    const palHead = h('div', {class: 'cx-pal-head'}, h('h3', {}, 'Постройки'),
        h('button', {title: 'Свернуть список ( [ )', onclick: () => fold('palette', true)}, '⇤'));
    const palSearch = h('input', {type: 'search', placeholder: 'Поиск: название, ключ…', oninput: e => { palQuery = e.target.value.trim().toLowerCase(); renderPalette(); }});
    const palList = h('div', {class: 'cx-pal-list'});
    palette.append(palHead, h('div', {class: 'cx-pal-search'}, palSearch), palList);
    function renderPalette() {
        const placed = new Set(cur().nodes.map(n => n.mod_key).filter(Boolean));
        const scroll = palList.scrollTop;
        palList.innerHTML = '';
        palList.append(palItem({blank: true}));
        const groups = new Map();
        for (const r of modLevels) {
            const hay = `${r.name} ${r.short} ${chainTitle(r)}`.toLowerCase();
            if (palQuery && !hay.includes(palQuery)) continue;
            const t = data.hull.includes(r) ? 'Корпус' : chainTitle(r);
            if (!groups.has(t)) groups.set(t, []);
            groups.get(t).push(r);
        }
        for (const [title, rows] of groups) {
            palList.append(h('h4', {}, title));
            for (const r of rows) palList.append(palItem({r, placed: placed.has(r.short)}));
        }
        if (!groups.size) palList.append(h('div', {class: 'sub', style: 'padding:8px;color:var(--cx-dim)'}, 'Ничего не нашлось'));
        palList.scrollTop = scroll;
    }
    function palItem({r, blank, placed}) {
        const meta = blank ? 'новая, нет в моде' : `${data.hull.includes(r) ? 'корпус ' + (r.level + 1) : 'тир корпуса ' + r.tier} · ${r.cost} · ${r.turns} ${turnsWord(r.turns)}`;
        const el = h('div', {class: 'cx-pal-item' + (blank ? ' blank' : '') + (placed ? ' placed' : ''),
                title: blank ? 'Пустая постройка: перетащите на полотно или щёлкните дважды' : `${r.name}\n${r.short}\n${meta}\n${placed ? 'Уже на полотне: щелчок покажет её' : 'Перетащите на полотно или щёлкните дважды'}`},
            slotIcon(blank ? null : nodeOfMod(r).icon),
            h('div', {class: 'tx'}, h('div', {class: 'n'}, blank ? '+ Пустая постройка' : r.name), h('div', {class: 'm'}, meta)),
            placed ? h('span', {class: 'badge', title: 'Уже на полотне'}, '✓') : null);
        el.addEventListener('pointerdown', e => {
            if (e.button !== 0) return;
            e.preventDefault();
            const x0 = e.clientX, y0 = e.clientY;
            let ghost = null;
            drag = {
                move: ev => {
                    if (!ghost && Math.hypot(ev.clientX - x0, ev.clientY - y0) < 5) return;
                    if (!ghost) { ghost = h('div', {class: 'cx-ghost'}, slotIcon(blank ? null : nodeOfMod(r).icon)); document.body.append(ghost); }
                    ghost.style.left = ev.clientX - 37 + 'px'; ghost.style.top = ev.clientY - 37 + 'px';
                    if (inCanvas(ev.clientX, ev.clientY)) {
                        const w = toWorld(ev.clientX, ev.clientY), c = cellAt(w.x, w.y), f = T.freeCell(cur(), c.col, c.row), k = T.cxCard({col: f.col, row: f.row});
                        Object.assign(dropEl.style, {display: '', left: k.slotX + 'px', top: k.y + 'px'});
                    } else dropEl.style.display = 'none';
                },
                up: ev => {
                    if (ghost) ghost.remove();
                    dropEl.style.display = 'none';
                    if (!ghost) {             // a click
                        if (!blank && placed) { const n = cur().nodes.find(x => x.mod_key === r.short); select([n.id]); reveal(n.id); }
                        return;
                    }
                    if (!inCanvas(ev.clientX, ev.clientY)) return;
                    const w = toWorld(ev.clientX, ev.clientY), c = cellAt(w.x, w.y);
                    if (blank) addBlankAt(c); else addFromMod(r.short, c);
                },
            };
        });
        el.addEventListener('dblclick', () => (blank ? addBlankAt(centerCell()) : addFromMod(r.short, centerCell())));
        return el;
    }

    // ---- the warnings ----
    function renderWarnings() {
        warnBtn.textContent = warnList.length ? `⚠ Проверки: ${warnList.length}` : '✓ Проверки: всё в порядке';
        warnBtn.classList.toggle('has', warnList.length > 0);
        warnList0.innerHTML = '';
        if (!warnList.length) { warnList0.append(h('div', {class: 'ok'}, 'Замечаний нет')); return; }
        warnList0.append(h('ul', {}, warnList.map(w => h('li', {title: 'Показать', onclick: () => { if (w.nodes.length) { select(w.nodes); reveal(w.nodes[0]); } }}, w.text))));
    }

    // ---- the properties ----
    function field(label, input, help) {
        return h('div', {class: 'cx-field'}, h('label', {}, label), input, help ? h('div', {class: 'help'}, help) : null);
    }
    // a field of the node: every keystroke is a change of the tree (joined into one step while typing), the canvas follows at once; on leaving the
    // field it shows what was written down (a number field: the number kept), and the file is written at once
    function bind(n, key, el, parse = v => v) {
        el.dataset.field = key;
        const show = () => { const v = (T.byId(cur(), n.id) || n)[key]; el.value = v === null || v === undefined ? '' : v; };
        show();
        el.addEventListener('input', () => {
            const v = parse(el.value);
            commit(fieldLabel[key] || 'Правка', d => T.updateNode(d, n.id, {[key]: v}), `f:${key}:${n.id}`, {props: false});
        });
        el.addEventListener('change', show);
        el.addEventListener('blur', () => { show(); flushField(); });
        return el;
    }
    const flushField = () => { if (saveTimer) saveNow(); };
    const fieldLabel = {name: 'Название', description: 'Описание', cost: 'Цена', turns: 'Ходы', tier: 'Тир корпуса', note: 'Заметка', mod_key: 'Ключ мода'};
    let live = null;            // the parts of the properties that follow the typing (the mod key's line)
    const put = (...kids) => props.append(...kids.flat().filter(k => k !== null && k !== undefined && k !== false));
    function refreshPropsLive() { if (live) live(); }
    const propsHead = title => h('div', {class: 'cx-props-head'}, h('h3', {}, title), h('button', {title: 'Свернуть свойства ( ] )', onclick: () => fold('props', true)}, '⇥'));
    function renderProps() {
        live = null;
        const scroll = props.scrollTop;
        props.innerHTML = '';
        const d = cur();
        if (selEdge) {
            const a = T.byId(d, selEdge.from), b = T.byId(d, selEdge.to);
            put(propsHead('Связь'), h('p', {}, `«${T.label(b)}» требует «${T.label(a)}»: сначала строится «${T.label(a)}».`),
                b.prev === a.id ? h('p', {class: 'cx-lineinfo'}, `Это следующий уровень той же линейки (двойная линия): «${T.label(b)}» — уровень ${T.roman(T.levelOf(d, b.id))}, ${b.inherit ? 'наследует всё, что даёт' : 'не наследует'} «${T.label(a)}».`) : null,
                h('div', {class: 'cx-actions'},
                    h('button', {onclick: () => reverse(selEdge.from, selEdge.to)}, 'Развернуть'),
                    h('button', {class: 'danger', onclick: deleteSelection}, 'Удалить связь')),
                h('div', {class: 'sub'}, 'Delete — удалить, Esc — снять выделение'));
            return;
        }
        if (sel.size > 1) {
            const ns = [...sel].map(id => T.byId(d, id));
            put(propsHead(`Выделено построек: ${ns.length}`), h('div', {class: 'sub'}, ns.map(T.label).join(', ')),
                field('Цвет ветки у всех', swatches(ns.every(n => n.branch === ns[0].branch) ? ns[0].branch : undefined, b => commit('Цвет ветки', x => { for (const n of ns) T.updateNode(x, n.id, {branch: b}); }))),
                h('div', {class: 'cx-actions'},
                    ns.length === 2 ? h('button', {onclick: linkSelected, title: 'L'}, 'Связать две') : null,
                    h('button', {onclick: duplicate}, 'Копия'), h('button', {onclick: () => copy()}, 'Копировать'),
                    h('button', {class: 'danger', onclick: deleteSelection}, 'Удалить')),
                h('div', {class: 'sub'}, 'Тащите любую из них — двигается вся группа. Стрелки — сдвиг на клетку.'));
            return;
        }
        if (!sel.size) { renderTreeInfo(); props.scrollTop = scroll; return; }
        const n = T.byId(d, [...sel][0]);
        const tierSel = h('select', {}, h('option', {value: ''}, 'не нужен'), ...Object.entries(hullNames).map(([t, name]) => h('option', {value: t}, `${t} · ${name}`)));
        bind(n, 'tier', tierSel, v => (v ? Number(v) : null));
        const keyInput = h('input', {list: 'cx_mod_keys', placeholder: 'пусто: новая постройка', spellcheck: false});
        bind(n, 'mod_key', keyInput, v => v.trim() || null);
        const keyHelp = h('div', {class: 'help'});
        const fill = h('button', {title: 'Взять название, описание, цену, ходы, тир корпуса, значок, строки и экипаж из мода', onclick: () => {
            const r = byShort[T.byId(cur(), n.id).mod_key];
            if (!r) return;
            const f = nodeOfMod(r);
            commit('Поля из мода', x => T.updateNode(x, n.id, {name: f.name, description: f.description, cost: f.cost, turns: f.turns, tier: f.tier, icon: f.icon, effects: f.effects, crew: f.crew}));
            toast('Поля взяты из мода. Ctrl+Z — вернуть');
        }}, 'Взять из мода');
        const descHelp = h('div', {class: 'help'});
        live = () => {
            const x = T.byId(cur(), n.id) || n;
            const r = x.mod_key && byShort[x.mod_key];
            keyHelp.className = 'help' + (x.mod_key ? (r ? ' ok' : ' bad') : '');
            keyHelp.textContent = !x.mod_key ? 'Новая постройка: в моде её пока нет' : r ? `В моде: «${r.name}» (${chainTitle(r)})` : 'В моде нет такой постройки';
            fill.disabled = !r;
            const max = T.infoDescMax(x, unitsOf(x));
            descHelp.className = 'help' + (x.description.length > max ? ' bad' : '');
            descHelp.textContent = `${x.description.length} знаков; в окне сведений игры поместится ${max}`;
        };
        live();
        const cost = h('input', {type: 'number', min: 0, step: 50}), turns = h('input', {type: 'number', min: 1, max: T.TURNS_MAX, step: 1});
        bind(n, 'cost', cost, v => Math.max(0, Math.round(Number(v) || 0)));
        bind(n, 'turns', turns, v => clamp(Math.round(Number(v) || 1), 1, T.TURNS_MAX));
        put(
            propsHead('Постройка'), h('div', {class: 'sub'}, `id ${n.id} · столбец ${n.col}, ряд ${n.row + 1}`),
            field('Название', bind(n, 'name', h('input', {spellcheck: true}))),
            h('div', {class: 'cx-field'}, h('label', {}, 'Описание (атмосферный текст, курсивом в окне сведений)'), bind(n, 'description', h('textarea', {rows: 3, class: 'cx-desc'})), descHelp),
            h('div', {class: 'cx-row2'}, field('Цена, золото', cost), field(`Ходы (1–${T.TURNS_MAX})`, turns)),
            field('Тир корпуса (какой корпус нужен)', tierSel),
            lineEditor(n),
            field('Значок', h('div', {class: 'cx-iconpick'}, h('span', {title: 'Выбрать значок', onclick: () => iconGallery(n.id)}, slotIcon(n.icon, 'big')),
                h('div', {}, h('button', {onclick: () => iconGallery(n.id)}, 'Выбрать…'), ' ',
                    n.icon ? h('button', {onclick: () => commit('Значок', x => T.updateNode(x, n.id, {icon: null}))}, 'Убрать') : null,
                    h('div', {class: 'help'}, n.icon ? iconLabel(n.icon) : 'нет значка')))),
            field('Эффекты (строки в окне сведений)', effectsEditor(n)),
            field('Открывает в экипаже', crewEditor(n)),
            field('Открывает найм отрядов (армия)', unitsEditor(n)),
            field('Что появляется на корабле', partsEditor(n)),
            field('Цвет ветки (рамка и линии к ней)', swatches(n.branch, b => commit('Цвет ветки', x => T.updateNode(x, n.id, {branch: b})))),
            field('Заметка для разработчика', bind(n, 'note', h('textarea', {rows: 3, placeholder: 'Что эта постройка должна делать, идеи, сомнения. Её читает агент'}))),
            h('div', {class: 'cx-field'}, h('label', {}, 'Ключ постройки мода'), h('div', {class: 'cx-row2', style: 'align-items:center'}, keyInput, fill), keyHelp),
            h('hr'),
            linksInfo(n),
            h('div', {class: 'cx-actions'},
                h('button', {onclick: () => addNextLevel(n.id), title: 'Новый уровень этой линейки над ней: требует её, наследует её эффекты, экипаж, отряды и вид на корабле; тот же значок, ветка и тир. Как уровни одной постройки в игре'}, '+ Следующий уровень'),
                h('button', {onclick: () => addLinked(n.id, 'up'), title: 'Отдельная новая постройка, которая требует эту. Ничего не наследует, своя линейка'}, '+ Постройка над ней'),
                h('button', {onclick: duplicate}, 'Копия'),
                h('button', {class: 'danger', onclick: deleteSelection}, 'Удалить')));
        props.scrollTop = scroll;
    }
    // an icon no level uses: named by the level or the chain its file is drawn for (mtb_guns_3: the guns' third level)
    const iconLabel = p => {
        if (iconNames[p]) return iconNames[p].slice(0, 2).join(', ') + (iconNames[p].length > 2 ? '…' : '');
        const stem = p.split('/').pop().replace(/\.png$/, '').replace(/^tww3_mtb_/, '');
        if (byShort[stem]) return byShort[stem].name;
        const m = /^(.*)_(\d+)$/.exec(stem), r = m && modLevels.find(x => x.short.startsWith(m[1] + '_'));
        return r ? `${data.hull.includes(r) ? 'Корпус' : chainTitle(r)}, уровень ${m[2]}` : 'значок без постройки';
    };
    function linksInfo(n) {
        const d = cur();
        const req = n.requires.map(id => T.byId(d, id)).filter(Boolean), kids = T.children(d, n.id).map(id => T.byId(d, id));
        const item = (x, from, to) => h('li', {}, h('a', {href: '#', onclick: e => { e.preventDefault(); select([x.id]); reveal(x.id); }}, T.label(x)), ' ',
            h('button', {class: 'mini', title: 'Убрать связь', onclick: () => commit('Удаление связи', y => T.deleteEdge(y, from, to))}, '×'));
        return h('div', {class: 'cx-field'}, h('label', {}, 'Требует (строится раньше)'),
            req.length ? h('ul', {class: 'list'}, req.map(x => item(x, x.id, n.id))) : h('div', {class: 'help'}, 'ничего — это начало ветки'),
            h('label', {style: 'margin-top:6px'}, 'Её требуют (строятся позже)'),
            kids.length ? h('ul', {class: 'list'}, kids.map(x => item(x, n.id, x.id))) : h('div', {class: 'help'}, 'ничего'),
            h('div', {class: 'help'}, 'Связь: тяните от кружка сверху постройки к следующей, от кружка снизу — к нужной до неё.'));
    }
    function swatches(current, fn) {
        return h('div', {class: 'cx-swatches'}, BRANCHES.map(([b, name]) => h('button', {class: current === b ? 'on' : '', onclick: () => fn(b)},
            h('i', {style: `background:${LINE[b || 'trunk']}`}), name)));
    }
    // An effect: its icon and its line on one row (the line as the game's window shows it, green or red), under it what it is. An effect of the
    // catalogue: its kind and target, the value, what the mod has for it; the line follows the value until the author writes his own (↺ gives the
    // pattern back). A free line: when it reads as an effect of the catalogue, a button proposes it; nothing changes without the click.
    const STATUS_SHORT = {have: 'есть в моде', dev: 'нужна разработка', unknown: 'не проверено'};
    // the proposals the author waved away: a convenience of this browser, not of the file
    const DISMISS = 'mtb_cx_no_propose';
    const dismissedSet = () => { try { return new Set(JSON.parse(localStorage.getItem(DISMISS) || '[]')); } catch (e) { return new Set(); } };
    const dismissed = (id, text) => dismissedSet().has(id + '|' + text);
    const dismiss = (id, text) => { try { const s = dismissedSet(); s.add(id + '|' + text); localStorage.setItem(DISMISS, JSON.stringify([...s].slice(-500))); } catch (e) { /* no storage */ } };
    const statusBadge = st => h('span', {class: 'cx-status-badge ' + st[0], title: `${FX.STATUS[st[0]]}: ${st[1]}`}, STATUS_SHORT[st[0]]);
    function effectsEditor(n) {
        const box = h('div', {class: 'cx-effects'});
        const setFx = (i, label, fn, merge = null, opt) => commit(label, d => { const fx = T.byId(d, n.id).effects; fn(fx[i]); fx[i] = FX.complete(fx[i], fxCtx); }, merge, opt);
        const res = T.resolve(cur(), n.id);
        const standing = new Set(res.inherited.effects.filter(x => x.status === 'replaced' && x.by).map(x => x.by.split('/').pop()));
        if (res.from) box.append(inheritedEffects(n, res));
        if (res.from) box.append(h('div', {class: 'cx-inh-head own'}, 'Свои строки этого уровня'));
        n.effects.forEach((e, i) => {
            if (standing.has(e.id)) return;       // shown in the inherited block, in the place of the line it stands for
            const structured = FX.isStructured(e);
            const row = h('div', {class: 'e' + (e.good ? '' : ' badfx') + (structured ? ' fx' : '')});
            const input = h('input', {value: e.text, placeholder: 'Текст строки', 'data-field': `effect_${i}`, title: structured ? 'Текст строки: можно переписать своими словами, эффект останется' : 'Свободная строка'});
            input.addEventListener('input', () => {
                if (structured) setFx(i, 'Текст эффекта', x => { x.text = input.value; x.own_text = true; }, `fx:${n.id}:${i}`, {props: false});
                else commit('Строка эффекта', d => { T.byId(d, n.id).effects[i].text = input.value; }, `fx:${n.id}:${i}`, {props: false});
                if (proposalEl) proposalEl.remove();
            });
            input.addEventListener('blur', () => { flushField(); if (structured && !input.value.trim()) setFx(i, 'Текст по образцу', x => { x.own_text = false; }); });
            row.append(h('img', {src: url(e.icon || D + 'replenishement_positive.png'), alt: '', title: 'Значок строки', onclick: () => effectIconGallery(n.id, i)}), input);
            let proposalEl = null;
            if (structured) {
                const value = h('input', {type: 'number', step: 'any', value: e.value, 'data-field': `fxv_${i}`, class: 'v', title: 'Значение'});
                value.addEventListener('input', () => {
                    if (value.value === '' || !Number.isFinite(Number(value.value))) return;
                    setFx(i, 'Значение эффекта', x => { x.value = Number(value.value); }, `fxv:${n.id}:${i}`, {props: false});
                    const x = T.byId(cur(), n.id).effects[i];
                    if (!x.own_text) input.value = x.text;
                    row.classList.toggle('badfx', !x.good);
                    goodBtn.textContent = x.good ? 'зелёная' : 'красная';
                });
                value.addEventListener('blur', () => { value.value = T.byId(cur(), n.id).effects[i].value; flushField(); });
                const isCrew = FX.CREW_KINDS.includes(e.kind), isArmy = FX.ARMY_KINDS.includes(e.kind), valueless = FX.KINDS[e.kind].valueless;
                const target = isCrew ? h('select', {'data-field': `fxt_${i}`, title: 'На кого действует', onchange: ev => setFx(i, 'Эффект: на кого', x => { x.target = ev.target.value; })},
                    ['all', ...FX.SHOOTING(data.groups)].map(t => h('option', {value: t, selected: e.target === t}, t === 'all' ? 'все команды' : data.groups[t].name)))
                    : e.kind === 'ability' ? h('select', {'data-field': `fxt_${i}`, title: 'Какая способность', onchange: ev => setFx(i, 'Эффект: способность', x => { x.target = ev.target.value; })},
                        Object.entries(FX.ABILITIES).map(([k, a]) => h('option', {value: k, selected: e.target === k}, a.name))) : null;
                row.append(h('div', {class: 'fxmeta'},
                    h('span', {class: 'kind', title: FX.labelOf(e, fxCtx)}, isCrew || isArmy || e.kind === 'ability' ? FX.KINDS[e.kind].name : FX.labelOf(e, fxCtx)), target, valueless ? null : value,
                    h('span', {class: 'unit'}, valueless ? '' : FX.KINDS[e.kind].percent || /%\+?n%/.test(((fxCtx.gameEffects[e.effect || (FX.KINDS[e.kind] || {}).game] || {}).text) || '') ? '%' : ''),
                    statusBadge(FX.statusOf(e, fxCtx))));
                if (isArmy) row.append(armyUnitsEditor(n, i, e, setFx));
            } else {
                const prop = FX.proposal(e, fxCtx);
                if (prop && !dismissed(n.id, e.text)) {
                    // one line under the field across the row: what it would become, «Сделать» and «×» (not to propose this line again, in this browser)
                    proposalEl = h('div', {class: 'propose', title: `${prop.say}\nСтрока читается как эффект каталога. Текст останется вашим, страница будет знать, что он делает`},
                        h('span', {class: 'ptxt'}, `→ ${prop.say}${prop.colour ? (prop.effects[0].good ? ' · зелёная' : ' · красная') : ''}`),
                        h('button', {class: 'mini', 'data-propose': i, onclick: () => commit('Строка → эффект', d => { const fx = T.byId(d, n.id).effects; fx.splice(i, 1, ...prop.effects); })}, 'Сделать'),
                        h('button', {class: 'mini', title: 'Не предлагать для этой строки', onclick: () => { dismiss(n.id, e.text); proposalEl.remove(); }}, '×'));
                    row.append(proposalEl);
                }
            }
            const goodBtn = h('button', {class: 'mini', title: e.good ? 'Полезная (зелёная). Щёлкните — вредная (красная)' : 'Вредная (красная). Щёлкните — полезная',
                onclick: () => (structured ? setFx(i, 'Цвет строки', x => { x.good = !e.good; x.own_good = x.good !== FX.goodOf(x, fxCtx); })
                    : commit('Строка эффекта', d => { T.byId(d, n.id).effects[i].good = !e.good; }))}, e.good ? 'зелёная' : 'красная');
            row.append(h('div', {class: 'ebtns'},
                structured && e.own_text ? h('button', {class: 'mini', title: 'Вернуть текст по образцу игры', onclick: () => setFx(i, 'Текст по образцу', x => { x.own_text = false; })}, '↺ текст') : null,
                goodBtn,
                h('button', {class: 'mini', title: 'Выше', disabled: i === 0, onclick: () => commit('Порядок строк', d => { const fx = T.byId(d, n.id).effects; [fx[i - 1], fx[i]] = [fx[i], fx[i - 1]]; })}, '↑'),
                h('button', {class: 'mini', title: 'Ниже', disabled: i === n.effects.length - 1, onclick: () => commit('Порядок строк', d => { const fx = T.byId(d, n.id).effects; [fx[i + 1], fx[i]] = [fx[i], fx[i + 1]]; })}, '↓'),
                h('button', {class: 'mini', title: 'Удалить строку', onclick: () => commit('Удаление строки', d => { T.byId(d, n.id).effects.splice(i, 1); })}, '×')));
            box.append(row);
        });
        box.append(h('div', {class: 'cx-actions', style: 'margin:0'},
            h('button', {onclick: () => effectPicker(n.id), title: 'Эффект из каталога: экипаж, корабль, эффекты игры — с поиском'}, '+ Эффект…'),
            h('button', {onclick: () => { commit('Новая строка', d => { T.byId(d, n.id).effects.push({text: '', icon: null, good: true}); }); const el = props.querySelector(`[data-field="effect_${n.effects.length}"]`); if (el) el.focus(); }, title: 'Свободная строка текста'}, '+ Строка')));
        return box;
    }
    // An army effect's addressees: a ready set (the units a line of the tree opens) or units one by one, of those the tree opens; none: the whole army
    function armyUnitsEditor(n, i, e, setFx) {
        const lines = unitLines(), all = [...new Set([...lines.values()].flat())];
        const preset = h('select', {'data-field': `fxu_${i}`, title: 'Готовый набор: отряды, которые открывает линейка дерева', onchange: ev => {
            const v = ev.target.value;
            if (v === '') return;
            setFx(i, 'Эффект: отряды', x => { if (v === '*') { x.units = []; delete x.units_from; } else { x.units = [...lines.get(v)]; x.units_from = v; } });
        }}, h('option', {value: ''}, e.units_from && lines.has(e.units_from) ? `отряды линейки «${T.label(T.byId(cur(), e.units_from))}»` : 'набор отрядов…'),
            [...lines.entries()].map(([root, us]) => h('option', {value: root}, `отряды линейки «${T.label(T.byId(cur(), root))}» (${us.length})`)),
            h('option', {value: '*'}, 'вся армия (без выбора)'));
        const chips = (e.units || []).map(k => h('span', {class: 'cx-chip army', title: k}, armyUnits[k] ? h('img', {src: url(armyUnits[k].card.picture), alt: ''}) : null, unitName(k),
            h('button', {class: 'mini', title: 'Убрать отряд', onclick: () => setFx(i, 'Эффект: отряды', x => { x.units = x.units.filter(y => y !== k); delete x.units_from; })}, '×')));
        const add = h('select', {title: 'Добавить отряд из тех, что открывает дерево', onchange: ev => { const k = ev.target.value; if (k) setFx(i, 'Эффект: отряды', x => { x.units = [...(x.units || []), k]; delete x.units_from; }); }},
            h('option', {value: ''}, '+ отряд…'), all.filter(k => !(e.units || []).includes(k)).map(k => h('option', {value: k}, unitName(k))));
        return h('div', {class: 'fxunits'}, h('span', {class: 'kind'}, 'Для отрядов:'), preset, h('div', {class: 'cx-chips'}, chips.length ? chips : h('span', {class: 'help'}, 'вся армия')), add);
    }
    // The inherited lines of the level below (its full set), each in its place: kept (muted; a number of the catalogue typed in place makes it this
    // level's own, of the same kind and target), changed here (the own line, editable; «вернуть» gives the inherited back), removed on this level
    // (struck; «вернуть»).
    // an effect with a number (a game effect without %n in its text, «Возможность найма героя», has none)
    const valued = e => (e.kind !== 'game' ? !(FX.KINDS[e.kind] || {}).valueless : /%\+?n/.test(((fxCtx.gameEffects[e.effect] || {}).text) || '%n'));
    function inheritedEffects(n, res) {
        const prev = T.byId(cur(), n.prev);
        const box = h('div', {class: 'cx-inherited'}, h('div', {class: 'cx-inh-head'}, `от «${T.label(prev)}» (${T.roman(T.levelOf(cur(), prev.id))})`,
            h('span', {class: 'sub'}, ' — унаследовано, живая связь')));
        const fromName = id => { const x = T.byId(cur(), id); return x ? `«${T.label(x)}» (${T.roman(T.levelOf(cur(), id))})` : id; };
        const unit = e => (FX.KINDS[e.kind] && (FX.KINDS[e.kind].percent || /%\+?n%/.test(((fxCtx.gameEffects[e.effect || (FX.KINDS[e.kind] || {}).game] || {}).text) || '')) ? '%' : '');
        res.inherited.effects.forEach(x => {
            if (x.status === 'replaced' && !x.by) return;
            const e = x.e, structured = FX.isStructured(e);
            const row = h('div', {class: 'e inh ' + x.status + (e.good ? '' : ' badfx'), 'data-key': x.key, title: `Унаследовано от ${fromName(x.from)}`});
            row.append(h('img', {src: url(e.icon || D + 'replenishement_positive.png'), alt: ''}));
            if (x.status === 'hidden') {
                row.append(h('span', {class: 'txt'}, e.text), h('div', {class: 'ebtns'}, h('span', {class: 'note'}, 'убрано на этом уровне'),
                    h('button', {class: 'mini', title: 'Вернуть унаследованную строку', onclick: () => commit('Вернуть строку', d => { const m = T.byId(d, n.id); m.hide = m.hide.filter(k => k !== x.key); })}, 'вернуть')));
                box.append(row); return;
            }
            if (x.status === 'replaced') {
                // the own line that stands for it, editable here
                const j = T.byId(cur(), n.id).effects.findIndex(o => `${n.id}/${o.id}` === x.by), own = T.byId(cur(), n.id).effects[j];
                const input = h('input', {value: own.text, 'data-field': `effect_${j}`, title: 'Своя строка взамен унаследованной'});
                input.addEventListener('input', () => commit('Текст строки', d => { const o = T.byId(d, n.id).effects[j]; o.text = input.value; if (FX.isStructured(o)) o.own_text = true; }, `fx:${n.id}:${j}`, {props: false}));
                input.addEventListener('blur', flushField);
                row.append(input);
                const meta = h('div', {class: 'fxmeta'}, h('span', {class: 'was', title: 'Унаследованная строка'}, `было: ${e.text}`));
                if (FX.isStructured(own) && valued(own)) {
                    const v = h('input', {type: 'number', step: 'any', value: own.value, class: 'v', 'data-field': `fxv_${j}`, title: 'Число на этом уровне'});
                    v.addEventListener('input', () => {
                        if (v.value === '' || !Number.isFinite(Number(v.value))) return;
                        commit('Число на этом уровне', d => { const fx = T.byId(d, n.id).effects; fx[j] = FX.complete({...fx[j], value: Number(v.value)}, fxCtx); }, `fxv:${n.id}:${j}`, {props: false});
                        const o = T.byId(cur(), n.id).effects[j];
                        if (!o.own_text) input.value = o.text;
                        row.classList.toggle('badfx', !o.good);
                    });
                    v.addEventListener('blur', () => { flushField(); renderProps(); });
                    meta.append(v, h('span', {class: 'unit'}, unit(own)));
                }
                row.classList.add('mine');
                row.append(meta, h('div', {class: 'ebtns'}, h('span', {class: 'note'}, 'изменено здесь'),
                    h('button', {class: 'mini', title: 'Убрать свою строку: снова действует унаследованная', onclick: () => commit('Вернуть унаследованную', d => { T.byId(d, n.id).effects.splice(j, 1); })}, 'вернуть')));
                box.append(row); return;
            }
            // kept: muted; the number of the catalogue typed here makes this level's own line of the same kind and target
            row.append(h('span', {class: 'txt'}, e.text));
            const meta = h('div', {class: 'fxmeta'});
            if (structured && valued(e)) {
                const sig = T.effectSig(e);
                const v = h('input', {type: 'number', step: 'any', value: e.value, class: 'v quick', 'data-quick': x.key, title: 'Другое число на этом уровне: строка станет своей, тот же эффект'});
                v.addEventListener('input', () => {
                    if (v.value === '' || !Number.isFinite(Number(v.value))) return;
                    commit('Число на этом уровне', d => {
                        const fx = T.byId(d, n.id).effects;
                        let k = fx.findIndex(o => T.effectSig(o) === sig);
                        if (k < 0) { fx.push({kind: e.kind, target: e.target, effect: e.effect, value: e.value, icon: e.icon}); k = fx.length - 1; }
                        fx[k] = FX.complete({...fx[k], value: Number(v.value)}, fxCtx);
                    }, `quick:${n.id}:${sig}`, {props: false});
                    const o = T.byId(cur(), n.id).effects.find(q => T.effectSig(q) === sig);
                    if (o) { row.querySelector('.txt').textContent = o.text; row.classList.toggle('badfx', !o.good); row.classList.add('editing'); }
                });
                v.addEventListener('blur', () => { flushField(); renderProps(); });
                meta.append(h('span', {class: 'kind'}, FX.labelOf(e, fxCtx)), v, h('span', {class: 'unit'}, unit(e)));
            }
            row.append(meta, h('div', {class: 'ebtns'},
                h('button', {class: 'mini', title: structured ? 'Своя строка того же эффекта на этом уровне' : 'Свой текст взамен унаследованной строки', onclick: () => {
                    let j;
                    commit('Изменить здесь', d => { const fx = T.byId(d, n.id).effects; fx.push(structured ? {kind: e.kind, target: e.target, effect: e.effect, value: e.value, icon: e.icon, text: e.text}
                        : {text: e.text, icon: e.icon, good: e.good, replaces: x.key}); j = fx.length - 1; fx[j] = FX.complete(fx[j], fxCtx); });
                    const el = props.querySelector(`[data-field="${structured ? 'fxv' : 'effect'}_${j}"]`);
                    if (el) { el.focus(); if (el.select) el.select(); }
                }}, 'изменить здесь'),
                h('button', {class: 'mini', title: 'Убрать эту строку на этом уровне (и выше по линейке)', onclick: () => commit('Убрать на этом уровне', d => { const m = T.byId(d, n.id); m.hide = [...(m.hide || []), x.key]; })}, 'убрать')));
            box.append(row);
        });
        if (!res.inherited.effects.length) box.append(h('div', {class: 'help'}, 'прошлый уровень строк не даёт'));
        return box;
    }
    // inherited crew, units, details: muted chips, «убрать» on this level, the removed struck with «вернуть»
    function inheritedThings(n, list, nameOf, cardOf) {
        const res = T.resolve(cur(), n.id);
        if (!res.below || !res.inherited[list].length) return null;
        const prev = T.byId(cur(), n.prev);
        return h('div', {class: 'cx-inherited things'}, h('div', {class: 'cx-inh-head'}, `от «${T.label(prev)}» (${T.roman(T.levelOf(cur(), prev.id))})`,
                h('span', {class: 'sub'}, ' — открытое прошлыми уровнями сохраняется')),
            h('div', {class: 'cx-chips'}, res.inherited[list].map(x => {
                const hidden = x.status === 'hidden', pic = cardOf ? cardOf(x) : null;
                return h('span', {class: 'cx-chip inh' + (hidden ? ' hidden' : ''), title: hidden ? 'Убрано на этом уровне' : 'Унаследовано'}, pic ? h('img', {src: url(pic), alt: ''}) : null, nameOf(x),
                    h('button', {class: 'mini', title: hidden ? 'Вернуть' : 'Убрать на этом уровне', onclick: () => commit(hidden ? 'Вернуть унаследованное' : 'Убрать на этом уровне', d => {
                        const m = T.byId(d, n.id); m.hide = hidden ? m.hide.filter(k => k !== x.key) : [...(m.hide || []), x.key];
                    })}, hidden ? 'вернуть' : '×'));
            })));
    }
    // The line of levels: what this node continues, its level, inheritance, the next levels; the line broken; the link «требует» added when missing
    function lineEditor(n) {
        const d = cur(), line = T.lineOf(d, n.id), lvl = T.inLine(d, n.id) ? line.ids.length : 0, prev = n.prev && T.byId(d, n.prev), nexts = T.nextLevels(d, n.id).map(id => T.byId(d, id));
        const options = d.nodes.filter(x => x.id !== n.id && T.canContinue(d, n.id, x.id).ok).sort((a, b) => T.label(a).localeCompare(T.label(b), 'ru'));
        const pick = h('select', {'data-field': 'prev', onchange: ev => setPrev(n.id, ev.target.value || null)}, h('option', {value: ''}, '— не продолжает (начало линейки или отдельная)'),
            options.map(x => h('option', {value: x.id, selected: x.id === n.prev}, `${T.label(x)}${T.inLine(d, x.id) ? ` (${T.roman(T.levelOf(d, x.id))})` : ''}`)));
        const inherit = h('input', {type: 'checkbox', checked: !!n.inherit, disabled: !prev, 'data-field': 'inherit', onchange: ev => { if (ev.target.checked) enableInherit(n.id); else commit('Наследование выключено', x => { T.byId(x, n.id).inherit = false; }); }});
        const go = x => h('a', {href: '#', onclick: e => { e.preventDefault(); select([x.id]); reveal(x.id); }}, T.label(x));
        return h('div', {class: 'cx-field cx-line'}, h('label', {}, 'Продолжает линейку (прошлый уровень)'), pick,
            lvl ? h('div', {class: 'help ok'}, `Уровень ${T.roman(lvl)} линейки «${T.label(T.byId(d, line.ids[0]))}»`) : h('div', {class: 'help'}, 'Не в линейке: отдельная постройка'),
            prev && !n.requires.includes(prev.id) && !T.leadsTo(d, prev.id, n.id) ? h('div', {class: 'help bad'}, `Не требует «${T.label(prev)}» — в игре следующий уровень строится на прошлом. `,
                h('button', {class: 'mini', onclick: () => commit('Связь', x => T.addEdge(x, prev.id, n.id))}, 'Добавить связь «требует»')) : null,
            prev ? h('label', {class: 'cx-check', title: 'Получает строки эффектов прошлого уровня (и тот — своего), живая связь. Экипаж, найм и вид на корабле, открытые прошлыми уровнями, сохраняются всегда'}, inherit, ' Наследует строки эффектов прошлого уровня') : null,
            nexts.length ? h('div', {class: 'help'}, 'Следующий уровень: ', ...nexts.flatMap((x, i) => [i ? ', ' : '', go(x)])) : null,
            h('div', {class: 'cx-actions', style: 'margin:4px 0 0'},
                h('button', {onclick: () => addNextLevel(n.id), title: 'Новый уровень этой линейки над ней: требует её и наследует всё, что она даёт'}, '+ Следующий уровень'),
                prev ? h('button', {class: 'danger', onclick: () => setPrev(n.id, null), title: 'Постройка перестаёт быть уровнем этой линейки; связь «требует» остаётся'}, 'Разорвать линейку') : null));
    }
    function setPrev(id, prev) {
        if (!prev) { commit('Линейка разорвана', d => { T.byId(d, id).prev = null; }); toast('Линейка разорвана: постройка больше не наследует. Ctrl+Z — вернуть'); return; }
        const c = T.canContinue(cur(), id, prev);
        if (!c.ok) { toast(c.why, true); renderProps(); return; }
        commit('Продолжает линейку', d => { const n = T.byId(d, id); n.prev = prev; n.inherit = false; if (!n.requires.includes(prev) && T.canLink(d, prev, id).ok) T.addEdge(d, prev, id); });
        enableInherit(id, true);
    }
    // Inheritance on: when the node has lines of its own (a building of the mod comes with its whole set), what would stand for the inherited, what
    // would be doubled; one action takes the doubles away
    function enableInherit(id, quiet = false) {
        const read = t => FX.recognize(t, fxCtx).map(T.effectSig);
        const o = T.inheritOverlap(cur(), id, read);
        const n = T.byId(cur(), id);
        if (!o.doubles.length && !o.sameKind.length && !o.things.length) {
            commit('Наследование включено', d => { T.byId(d, id).inherit = true; });
            if (!quiet || o.replace.length) toast(o.replace.length ? `Наследует «${T.label(T.byId(cur(), n.prev))}»; ${o.replace.length} своих эффектов заменяют унаследованные того же вида` : `Наследует всё от «${T.label(T.byId(cur(), n.prev))}»`);
            return;
        }
        const li = x => h('li', {}, x.e.text, h('span', {class: 'help'}, ` — у «${T.label(T.byId(cur(), x.of.from))}»: ${x.of.e.text}`));
        const fix = () => commit('Наследование включено, дубли убраны', d => {
            const m = T.byId(d, id);
            m.inherit = true;
            const drop = new Set(o.doubles.map(x => x.i));
            for (const x of o.sameKind) m.effects[x.i].replaces = x.of.key;
            m.effects = m.effects.filter((e, i) => !drop.has(i));
            for (const t of o.things) m[t.list] = m[t.list].filter(y => T.thingKey[t.list](y) !== t.key);
        });
        const box = modal([h('h3', {}, `Наследовать от «${T.label(T.byId(cur(), n.prev))}»`),
            h('p', {}, `У «${T.label(n)}» есть свои строки; с наследованием часть из них совпадёт с унаследованными.`),
            o.replace.length ? h('div', {}, h('b', {}, 'Заменят унаследованные (тот же эффект и адресат) — это не дубли:'), h('ul', {}, o.replace.map(li))) : null,
            o.doubles.length ? h('div', {}, h('b', {}, 'Совпадают дословно — задвоятся:'), h('ul', {}, o.doubles.map(li))) : null,
            o.sameKind.length ? h('div', {}, h('b', {}, 'Тот же вид с другим числом — задвоятся (станут заменой):'), h('ul', {}, o.sameKind.map(li))) : null,
            o.things.length ? h('div', {}, h('b', {}, 'Уже даёт прошлый уровень:'), h('ul', {}, o.things.map(t => h('li', {}, t.list === 'crew' ? `экипаж: ${(data.groups[t.x.group] || {}).options?.[t.x.option]?.name || t.x.option}` : t.list === 'units' ? `найм: ${unitName(t.x)}` : `вид: ${t.x.part ? partName(t.x.part) : t.x.name}`)))) : null,
            h('div', {class: 'btns'}, h('button', {onclick: () => { closeModal(); renderProps(); }}, 'Отмена'),
                h('button', {onclick: () => { closeModal(); commit('Наследование включено', d => { T.byId(d, id).inherit = true; }); }}, 'Включить как есть'),
                h('button', {class: 'danger', 'data-act': 'dedupe', onclick: () => { closeModal(); fix(); toast('Наследование включено, дубли убраны. Ctrl+Z — вернуть'); }}, 'Включить и убрать дубли'))], 'cx-dialog');
        box.querySelector('[data-act="dedupe"]').focus();
    }
    // The catalogue: a list in sections with a search; the crew's kinds a row each with its targets as buttons. The arrows move between the choices,
    // Enter takes one, Escape closes; the search's Enter takes the first shown.
    function effectPicker(id) {
        const all = FX.catalogue(fxCtx);
        const body = h('div', {class: 'body cx-fxlist', role: 'listbox'});
        const search = h('input', {type: 'search', placeholder: 'Поиск: боезапас, стрелки, найм, опыт…'});
        const take = (entry, target) => {
            closeModal();
            const n0 = T.byId(cur(), id);
            // an army effect starts with the units this building's line opens (or the whole army when it opens none)
            const root = T.lineOf(cur(), id).ids[0], own = unitLines().get(root);
            const e = entry.kind === 'text' ? {text: '', icon: null, good: true}
                : FX.newEffect(entry.kind, {target: target || entry.target, effect: entry.effect, ...(FX.ARMY_KINDS.includes(entry.kind) && own ? {units: own, units_from: root} : {})}, fxCtx);
            commit(entry.kind === 'text' ? 'Новая строка' : `Эффект: ${FX.labelOf(e, fxCtx)}`, d => { T.byId(d, id).effects.push(e); });
            const el = props.querySelector(`[data-field="${entry.kind === 'text' ? 'effect' : 'fxv'}_${n0.effects.length}"]`);
            if (el) { el.focus(); if (el.select) el.select(); }
            toast(entry.kind === 'text' ? 'Новая строка. Ctrl+Z — убрать' : `Добавлен эффект «${FX.labelOf(e, fxCtx)}». Ctrl+Z — убрать`);
        };
        const draw = () => {
            const q = search.value.trim().toLowerCase().replace(/ё/g, 'е');
            const words = q.split(/\s+/).filter(Boolean);
            const hit = x => words.every(w => x.search.includes(w));
            body.innerHTML = '';
            for (const sec of ['crew', 'ship', 'horde', 'game', 'army', 'text']) {
                let list = all.filter(x => x.section === sec && hit(x));
                if (!list.length) continue;
                body.append(h('h4', {}, FX.SECTIONS[sec] + (sec === 'game' ? ` (${list.length})` : '')));
                if (sec === 'crew') {
                    for (const kind of FX.CREW_KINDS) {
                        const rows = list.filter(x => x.kind === kind);
                        if (!rows.length) continue;
                        body.append(h('div', {class: 'fxrow'}, h('img', {src: url(rows[0].icon), alt: ''}),
                            h('div', {class: 'tx'}, h('b', {}, FX.KINDS[kind].name), h('div', {class: 'm'}, rows[0].sample)),
                            h('div', {class: 'targets'}, rows.map(x => h('button', {class: 'pick', title: `${x.title}: ${x.sub}. ${FX.STATUS[x.status[0]]}: ${x.status[1]}`, onclick: () => take(x, x.target)},
                                x.sub, ' ', h('span', {class: 'dot ' + x.status[0]}))))));
                    }
                    continue;
                }
                if (sec === 'game') list = list.sort((a, b) => (b.uses || 0) - (a.uses || 0)).slice(0, q ? 200 : 60);
                for (const x of list) {
                    body.append(h('div', {class: 'fxrow pick', tabIndex: 0, role: 'option', onclick: () => take(x), onkeydown: ev => { if (ev.key === 'Enter') { ev.preventDefault(); take(x); } }},
                        h('img', {src: url(x.icon), alt: ''}), h('div', {class: 'tx'}, h('b', {}, x.title), h('div', {class: 'm'}, x.sample || x.sub)),
                        statusBadge(x.status)));
                }
                if (sec === 'game' && !q) body.append(h('div', {class: 'help'}, 'Показаны частые эффекты игры; поиск найдёт любой из ' + all.filter(x => x.section === 'game').length + '.'));
            }
            if (!body.children.length) body.append(h('div', {class: 'help', style: 'padding:8px'}, 'Ничего не нашлось'));
        };
        search.addEventListener('input', draw);
        search.addEventListener('keydown', ev => {
            if (ev.key === 'Enter') { ev.preventDefault(); const f = body.querySelector('.pick'); if (f) f.click(); }
            if (ev.key === 'ArrowDown') { ev.preventDefault(); const f = body.querySelector('.pick'); if (f) f.focus(); }
        });
        body.addEventListener('keydown', ev => {
            if (ev.key !== 'ArrowDown' && ev.key !== 'ArrowUp') return;
            ev.preventDefault();
            const picks = [...body.querySelectorAll('.pick')], k = picks.indexOf(document.activeElement);
            const next = ev.key === 'ArrowDown' ? picks[k + 1] : k <= 0 ? search : picks[k - 1];
            if (next) next.focus();
        });
        modal([h('div', {class: 'top'}, h('h3', {}, 'Эффект из каталога'), search, h('button', {onclick: () => closeModal()}, 'Закрыть')),
            h('div', {class: 'cx-legend'}, h('span', {class: 'dot have'}), ' есть в моде  ', h('span', {class: 'dot dev'}), ' нужна разработка  ', h('span', {class: 'dot unknown'}), ' не проверено'), body]);
        draw();
        search.focus();
    }
    // The army units a building opens for recruitment: the game's small cards, a picker with a search by name and kind
    function unitsEditor(n) {
        const box = h('div');
        const chips = h('div', {class: 'cx-chips'});
        for (const k of n.units || []) {
            const u = armyUnits[k], others = cur().nodes.filter(x => x.id !== n.id && (x.units || []).includes(k));
            chips.append(h('span', {class: 'cx-chip army' + (others.length ? ' dup' : ''), title: `${u ? u.name : k}\n${k}${others.length ? '\nЕго же открывают: ' + others.map(T.label).join(', ') : ''}`},
                u ? h('img', {src: url(u.card.picture), alt: ''}) : null, u ? u.name : k, others.length ? h('span', {class: 'dupmark'}, '×2') : null,
                h('button', {class: 'mini', title: 'Убрать', onclick: () => commit('Найм отряда', d => { const x = T.byId(d, n.id); x.units = x.units.filter(y => y !== k); })}, '×')));
        }
        const inh = inheritedThings(n, 'units', x => unitName(x.u), x => armyUnits[x.u] && armyUnits[x.u].card.picture);
        box.append(inh || '', inh ? h('div', {class: 'cx-inh-head own'}, 'Свои') : '', (n.units || []).length ? chips : h('div', {class: 'help'}, 'ничего'), h('button', {onclick: () => unitsPicker(n.id)}, 'Выбрать…'),
            h('div', {class: 'help'}, 'Обычные отряды армии гномов: в игре — блок «Открывает найм» и карточки в обычной рамке. Найм армии страница не моделирует.'));
        return box;
    }
    function unitsPicker(id) {
        const body = h('div', {class: 'body cx-crewlist'});
        const search = h('input', {type: 'search', placeholder: 'Поиск: пушки, громобои, wh_main_dwf…'});
        const draw = () => {
            const q = search.value.trim().toLowerCase().replace(/ё/g, 'е'), n = T.byId(cur(), id);
            if (!n) { closeModal(); return; }
            body.innerHTML = '';
            const units = Object.values(armyUnits);
            for (const caste of [...new Set(units.map(u => u.caste))]) {
                const list = units.filter(u => u.caste === caste && (!q || `${u.name} ${u.key} ${CASTES[u.caste] || ''} ${VARIANT[u.variant] || ''}`.toLowerCase().replace(/ё/g, 'е').includes(q)));
                if (!list.length) continue;
                body.append(h('h4', {}, CASTES[caste] || caste));
                for (const u of list) {
                    const on = (n.units || []).includes(u.key), others = cur().nodes.filter(x => x.id !== id && (x.units || []).includes(u.key));
                    const box = h('input', {type: 'checkbox', checked: on, onchange: () => {
                        commit('Найм отряда', d => { const x = T.byId(d, id); x.units = box.checked ? [...(x.units || []), u.key] : (x.units || []).filter(k => k !== u.key); });
                    }});
                    body.append(h('label', {title: u.key}, box, h('img', {src: url(u.card.picture), alt: ''}), h('img', {class: 'cat', src: url(u.card.category), alt: ''}),
                        h('span', {}, h('b', {}, u.name), h('div', {class: 'm'}, `найм ${u.hire}, содержание ${u.upkeep} · ${u.stats.men} ${u.stats.engines ? '+ ' + u.stats.engines + ' машины' : 'бойцов'}`
                            + (u.variant ? ' · ' + VARIANT[u.variant] : '') + (others.length ? ` · уже открывает «${others.map(T.label).join('», «')}»` : '')))));
                }
            }
            if (!body.children.length) body.append(h('div', {class: 'help', style: 'padding:8px'}, Object.keys(armyUnits).length ? 'Ничего не нашлось' : 'Нет списка отрядов: py -3.14 tools/web_export.py --catalog'));
        };
        search.addEventListener('input', draw);
        modal([h('div', {class: 'top'}, h('h3', {}, 'Открывает найм отрядов'), search, h('button', {onclick: () => closeModal()}, 'Готово')), body]);
        modalRedraw = draw;
        draw();
        search.focus();
    }
    // What appears on the ship with the building: a detail of web/data/blueprint.json (drawn or not, in 3D or not), or a new one described for the
    // developer. No price, no hire, no choice of the player: it is there while the building stands.
    const partBadges = k => {
        const p = partsInfo[k];
        if (!p) return [h('span', {class: 'cx-status-badge unknown'}, 'нет в чертеже')];
        return [h('span', {class: 'cx-status-badge ' + (p.drawn ? 'have' : 'dev'), title: p.drawn ? 'Слой на чертеже есть' : 'Рисунка на чертеже нет'}, p.drawn ? 'на чертеже' : 'рисунок не готов'),
                h('span', {class: 'cx-status-badge ' + (p.model ? 'have' : 'dev'), title: p.model ? 'Модель есть (build/web/models)' : 'Модели нет'}, p.model ? 'в 3D' : 'нет 3D')];
    };
    function partsEditor(n) {
        const box = h('div', {class: 'cx-parts'});
        const inh = inheritedThings(n, 'parts', x => (x.p.part ? partName(x.p.part) : x.p.name || 'новая деталь'));
        if (inh) box.append(inh, h('div', {class: 'cx-inh-head own'}, 'Свои'));
        (n.parts || []).forEach((p, i) => {
            const del = h('button', {class: 'mini', title: 'Убрать', onclick: () => commit('Вид на корабле', d => { T.byId(d, n.id).parts.splice(i, 1); })}, '×');
            if (p.part) { box.append(h('div', {class: 'part'}, h('b', {}, partName(p.part)), ...partBadges(p.part), del)); return; }
            const named = partOfName(p.name);
            const set = (key, label, parse = v => v) => el => {
                el.dataset.field = `part_${key}_${i}`;
                el.addEventListener(el.tagName === 'SELECT' ? 'change' : 'input', () => commit(label, d => { T.byId(d, n.id).parts[i][key] = parse(el.value); }, `part:${n.id}:${i}:${key}`, {props: false}));
                el.addEventListener('blur', flushField);
                return el;
            };
            box.append(h('div', {class: 'part new'},
                h('div', {class: 'cx-row2', style: 'align-items:center'}, set('name', 'Название детали')(h('input', {value: p.name, placeholder: 'Название: Дозорные в гнёздах'})),
                    // named as a detail of the drawing: on the page it is that detail (web/js/main.js links them by name)
                    named && partsInfo[named].drawn ? h('span', {class: 'cx-status-badge have', title: `Деталь чертежа с тем же названием (${named}): на странице рисуется она. Выберите её через «Добавить…», чтобы связь была явной`}, 'на чертеже')
                        : h('span', {class: 'cx-status-badge dev'}, 'рисунок не готов'), del),
                field('Где на корабле', set('zone', 'Где на корабле')(h('select', {}, Object.entries(T.ZONES).map(([k, v]) => h('option', {value: k, selected: p.zone === k}, v))))),
                field('Что это', set('what', 'Что это')(h('select', {}, Object.entries(T.WHAT).map(([k, v]) => h('option', {value: k, selected: p.what === k}, v))))),
                p.what === 'figures' ? field('Сколько фигур', set('figures', 'Сколько фигур', v => Math.max(0, Math.round(Number(v) || 0)))(h('input', {type: 'number', min: 0, step: 1, value: p.figures}))) : null,
                field('Описание для разработчика', set('note', 'Описание детали')(h('textarea', {rows: 2, placeholder: 'Какие фигуры или модель нужны, где стоят, что делают', value: p.note})))));
        });
        box.append(h('button', {onclick: () => partsPicker(n.id)}, 'Добавить…'),
            h('div', {class: 'help'}, 'Вид на корабле вместе с постройкой: без цены, найма и выбора. Готовые детали встают на чертёж и в 3D; новые ждут рисунка.'));
        return box;
    }
    function partsPicker(id) {
        const body = h('div', {class: 'body cx-crewlist'});
        const draw = () => {
            const n = T.byId(cur(), id);
            if (!n) { closeModal(); return; }
            body.innerHTML = '';
            body.append(h('h4', {}, 'Детали чертежа'));
            for (const p of Object.values(partsInfo)) {
                const on = (n.parts || []).some(x => x.part === p.key);
                const box = h('input', {type: 'checkbox', checked: on, onchange: () => commit('Вид на корабле', d => {
                    const x = T.byId(d, id);
                    x.parts = box.checked ? [...(x.parts || []), {part: p.key}] : (x.parts || []).filter(y => y.part !== p.key);
                })});
                const others = cur().nodes.filter(x => x.id !== id && (x.parts || []).some(y => y.part === p.key)).map(T.label);
                body.append(h('label', {title: p.key}, box, h('span', {}, h('b', {}, p.name), ' ', ...partBadges(p.key),
                    h('div', {class: 'm'}, [p.building ? `в моде её даёт ${byShort[p.building] ? '«' + byShort[p.building].name + '»' : p.building}` : 'в моде её пока не даёт ни одна постройка',
                        p.planned ? `задумано: ${p.planned}` : '', others.length ? `уже у «${others.join('», «')}»` : ''].filter(Boolean).join(' · ')))));
            }
            body.append(h('h4', {}, 'Новая деталь'), h('button', {onclick: () => {
                closeModal();
                const k = (T.byId(cur(), id).parts || []).length;
                commit('Новая деталь вида', d => { const x = T.byId(d, id); (x.parts ||= []).push({part: null, name: '', zone: 'deck', what: 'figures', figures: 0, note: ''}); });
                const el = props.querySelector(`[data-field="part_name_${k}"]`);
                if (el) el.focus();
            }}, '+ Новая деталь: название, где, что это, сколько фигур'));
        };
        modal([h('div', {class: 'top'}, h('h3', {}, 'Что появляется на корабле'), h('span', {style: 'flex:1'}), h('button', {onclick: () => closeModal()}, 'Готово')), body]);
        modalRedraw = draw;
        draw();
    }
    function crewEditor(n) {
        const box = h('div');
        const chips = h('div', {class: 'cx-chips'});
        for (const c of n.crew) {
            const g = data.groups[c.group], o = g && g.options[c.option], card = crewCard(c);
            chips.append(h('span', {class: 'cx-chip' + (card ? '' : ' nocard'), title: `${g ? g.name : c.group}: ${o ? o.name : c.option}${card ? '' : ' — без карточки (крепление или не выбирается в панели)'}`},
                card ? h('img', {src: url(card.uc.picture), alt: ''}) : null, `${o ? o.name : c.option}`, h('span', {style: 'color:var(--cx-dim);font-size:12px'}, g ? g.name.toLowerCase() : ''),
                h('button', {class: 'mini', title: 'Убрать', onclick: () => commit('Экипаж', d => { const x = T.byId(d, n.id); x.crew = x.crew.filter(y => !(y.group === c.group && y.option === c.option)); })}, '×')));
        }
        const inh = inheritedThings(n, 'crew', x => { const g = data.groups[x.c.group], o = g && g.options[x.c.option]; return o ? o.name : x.c.option; }, x => { const k = crewCard(x.c); return k && k.uc.picture; });
        box.append(inh || '', inh ? h('div', {class: 'cx-inh-head own'}, 'Свои') : '', n.crew.length ? chips : h('div', {class: 'help'}, 'ничего'), h('button', {onclick: () => crewPicker(n.id)}, 'Выбрать…'));
        return box;
    }
    function renderTreeInfo() {
        const d = cur();
        const links = T.edges(d).length;
        put(propsHead('Дерево построек'),
            h('div', {class: 'sub'}, `Построек: ${d.nodes.length}, связей: ${links}. Файл web/data/tree_design.json — каждое изменение сохраняется сразу.`),
            h('p', {style: 'margin:6px 0 10px'}, 'Выделите постройку, чтобы править её поля.'),
            h('ul', {class: 'list'},
                h('li', {}, 'Перетащите постройку из списка слева на полотно — она придёт с названием, ценой, строками и экипажем из мода.'),
                h('li', {}, 'Двойной щелчок по пустому месту — новая пустая постройка.'),
                h('li', {}, 'Связь: тяните от кружка сверху постройки к той, что строится после. Отпустите на пустом месте — появится новая со связью.'),
                h('li', {}, 'Фон тянется мышью, колесо — масштаб, Shift+рамка — выделить несколько.'),
                h('li', {}, 'Боковые панели сворачиваются: [ и ], обе — \\.'),
                h('li', {}, 'Ошибка? Ctrl+Z. Правая кнопка — меню. Все клавиши — кнопка «Клавиши».')),
            h('hr'),
            h('label', {style: 'font-weight:600;color:var(--cx-dim);font-size:12.5px'}, warnList.length ? `Проверки (${warnList.length})` : 'Проверки: всё в порядке'),
            warnList.length ? h('ul', {class: 'list wl'}, warnList.map(w => h('li', {onclick: () => { if (w.nodes.length) { select(w.nodes); reveal(w.nodes[0]); } }}, w.text))) : null);
    }
    // the mod's keys for the key field
    host.append(h('datalist', {id: 'cx_mod_keys'}, modLevels.map(r => h('option', {value: r.short}, r.name))));

    // ---- pop-ups ----
    function modal(content, cls = 'cx-pop', {sticky = false} = {}) {
        closeModal(true);
        const box = h('div', {class: cls}, content);
        const shade = h('div', {class: 'cx-shade' + (sticky ? ' sticky' : ''), onpointerdown: e => { if (e.target === shade && !sticky) closeModal(); }}, box);
        document.body.append(shade);
        return box;
    }
    let modalRedraw = null;
    function closeModal(force = false) {
        for (const s of document.querySelectorAll('.cx-shade')) if (force || !s.classList.contains('sticky')) s.remove();
        if (!document.querySelector('.cx-shade')) modalRedraw = null;
    }
    async function iconGallery(id) {
        const list = (await loadIcons()).buildings;
        const n = T.byId(cur(), id);
        const grid = h('div', {class: 'cx-gallery'});
        const search = h('input', {type: 'search', placeholder: 'Поиск по названию постройки'});
        const draw = () => {
            const q = search.value.trim().toLowerCase();
            grid.innerHTML = '';
            for (const p of list) {
                const names = iconNames[p] || [];
                if (q && !names.join(' ').toLowerCase().includes(q)) continue;
                grid.append(h('div', {class: 'g' + (n.icon === p ? ' on' : ''), title: names.join(', ') || 'значок без постройки', onclick: () => { closeModal(); commit('Значок', d => T.updateNode(d, id, {icon: p})); }},
                    slotIcon(p), h('div', {class: 'gl'}, iconLabel(p)), p.includes('tww3_mtb_') ? h('div', {class: 'gs'}, 'мод') : h('div', {class: 'gs'}, 'игра')));
            }
            if (!grid.children.length) grid.append(h('div', {}, 'Ничего не нашлось'));
        };
        search.addEventListener('input', draw);
        modal([h('div', {class: 'top'}, h('h3', {}, 'Значок постройки'), search, h('button', {onclick: closeModal}, 'Закрыть')), h('div', {class: 'body'}, grid)]);
        draw();
        search.focus();
    }
    async function effectIconGallery(id, i) {
        const list = (await loadIcons()).effects;
        const cur0 = T.byId(cur(), id).effects[i].icon;
        // a name for people: the page's own for the common ones, else the first words of a game effect that has this icon (build/web/catalog.json)
        const byIcon = {};
        for (const g of Object.values(fxCtx.gameEffects)) if (g.icon && !byIcon[g.icon]) byIcon[g.icon] = g.text.replace(/[:(].*$/, '').replace(/%\+?n%?/g, '').trim().split(/\s+/).slice(0, 2).join(' ');
        const name = p => EFFECT_NAMES[p.split('/').pop().replace(/\.png$/, '')] || (/^[А-ЯЁ]/.test(byIcon[p] || '') ? byIcon[p] : 'Значок');
        const grid = h('div', {class: 'cx-gallery small'},
            h('div', {class: 'g' + (!cur0 ? ' on' : ''), onclick: () => { closeModal(); commit('Значок строки', d => { T.byId(d, id).effects[i].icon = null; }); }}, h('img', {src: url(D + 'replenishement_positive.png'), alt: ''}), 'Обычный'),
            list.map(p => h('div', {class: 'g' + (cur0 === p ? ' on' : ''), title: name(p), onclick: () => { closeModal(); commit('Значок строки', d => { T.byId(d, id).effects[i].icon = p; }); }},
                h('img', {src: url(p), alt: ''}), name(p))));
        modal([h('div', {class: 'top'}, h('h3', {}, 'Значок строки'), h('span', {style: 'flex:1'}), h('button', {onclick: closeModal}, 'Закрыть')), h('div', {class: 'body'}, grid)]);
    }
    function crewPicker(id) {
        const body = h('div', {class: 'body cx-crewlist'});
        const search = h('input', {type: 'search', placeholder: 'Поиск'});
        const draw = () => {
            const q = search.value.trim().toLowerCase(), n = T.byId(cur(), id);
            body.innerHTML = '';
            for (const gk of groupOrder) {
                const g = data.groups[gk];
                const opts = Object.entries(g.options).filter(([k, o]) => k !== g.start && (!q || `${o.name} ${g.name} ${k}`.toLowerCase().includes(q)));
                if (!opts.length) continue;
                body.append(h('h4', {}, g.name));
                for (const [k, o] of opts) {
                    const on = n.crew.some(c => c.group === gk && c.option === k), card = crewCard({group: gk, option: k});
                    const box = h('input', {type: 'checkbox', checked: on, onchange: () => {
                        commit('Экипаж', d => { const x = T.byId(d, id); if (box.checked) x.crew.push({group: gk, option: k}); else x.crew = x.crew.filter(c => !(c.group === gk && c.option === k)); });
                    }});
                    body.append(h('label', {}, box, card ? h('img', {src: url(card.uc.picture), alt: ''}) : h('span', {class: 'nocard'}),
                        h('span', {}, h('b', {}, o.name === 'stock' ? k : o.name), h('div', {class: 'm'},
                            k === g.mount ? `крепление: ${g.mount_name || ''}` : o.unit_card ? `найм ${o.hire || 0}, содержание ${o.upkeep || 0} за ход` : 'без карточки', o.hidden ? ' · скрыт в панели' : ''))));
                }
            }
        };
        search.addEventListener('input', draw);
        modal([h('div', {class: 'top'}, h('h3', {}, 'Что открывает в экипаже'), search, h('button', {onclick: closeModal}, 'Готово')), body]);
        draw();
        search.focus();
    }
    function confirmBox(title, text, ok, okLabel = 'Да') {
        const box = modal([h('h3', {}, title), typeof text === 'string' ? h('p', {}, text) : text,
            h('div', {class: 'btns'}, h('button', {onclick: closeModal}, 'Отмена'), ok ? h('button', {class: 'danger', onclick: () => { closeModal(); ok(); }}, okLabel) : null)], 'cx-dialog');
        box.querySelector('.btns button:last-child').focus();
    }
    function keysHelp() {
        const rows = [['Двойной щелчок по пустому', 'новая постройка'], ['Перетащить из списка слева', 'постройка мода с её полями'], ['Тянуть от кружка сверху постройки', 'связь: та постройка строится после'],
            ['Тянуть от кружка снизу постройки', 'связь: та постройка нужна до'], ['Отпустить связь на пустом месте', 'новая постройка уже со связью'], ['Тянуть постройку', 'переставить (вся выделенная группа)'],
            ['Тянуть фон / средней кнопкой / с пробелом', 'сдвинуть полотно'], ['Колесо', 'масштаб'], ['Shift + рамка, Shift + щелчок', 'выделить несколько'], ['Щелчок по линии', 'выделить связь'],
            ['Правая кнопка', 'меню'], ['Delete, Backspace', 'удалить выделенное (когда в фокусе полотно)'], ['Ctrl+Z', 'отменить'], ['Ctrl+Y, Ctrl+Shift+Z', 'повторить'], ['Ctrl+D', 'копия рядом'],
            ['Ctrl+C / Ctrl+X / Ctrl+V', 'копировать / вырезать / вставить у мыши'], ['Ctrl+A', 'выделить всё'], ['Стрелки', 'сдвинуть выделенное на клетку'], ['L', 'связать две выделенные (нижняя строится раньше)'],
            ['N', 'новая постройка в середине'], ['F2, Enter, двойной щелчок по постройке', 'переименовать'], ['F', 'показать всё'], ['1', 'масштаб 100%'],
            ['[ / ] / \\', 'свернуть список построек / свойства / обе панели'], ['Esc', 'снять выделение']];
        modal([h('h3', {}, 'Мышь и клавиши'), h('div', {class: 'cx-keys'}, rows.flatMap(([k, v]) => [h('kbd', {}, k), h('span', {}, v)])),
            h('div', {class: 'btns'}, h('button', {onclick: closeModal}, 'Понятно'))], 'cx-dialog');
    }
    function fileMenu(btn) {
        const r = btn.getBoundingClientRect();
        showMenu(r.left, r.bottom + 2, [
            ['Экспорт в файл…', '', exportFile], ['Импорт из файла…', '', importFile],
            '-', ['Вернуть сохранённое (из файла на диске)', '', revertToFile], ['Очистить полотно…', '', clearAll]]);
    }
    function exportFile() {
        const a = h('a', {href: URL.createObjectURL(new Blob([T.serialize(cur())], {type: 'application/json'})), download: 'tree_design.json'});
        document.body.append(a); a.click(); a.remove();
        toast('Дерево выгружено в tree_design.json');
    }
    // a copy beside the file: of the file on disk, or (text) of a state of the canvas that is not written
    async function backup(text = null) {
        const r = await fetch('/api/tree_design/backup', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: text || '{}'});
        if (!r.ok) throw new Error('копия не сделана: ' + r.status);
        return (await r.json()).name;
    }
    function importFile() {
        const input = h('input', {type: 'file', accept: '.json,application/json', style: 'display:none'});
        input.addEventListener('change', async () => {
            const f = input.files[0];
            input.remove();
            if (!f) return;
            let raw;
            try { raw = JSON.parse(await f.text()); } catch (e) { confirmBox('Импорт не сделан', `«${f.name}» не читается: это не JSON.`); return; }
            // a file of another kind is refused, not read as an empty tree
            if (!raw || typeof raw !== 'object' || !Array.isArray(raw.nodes)) { confirmBox('Импорт не сделан', `«${f.name}» — не файл дерева построек: в нём нет списка построек (nodes). Полотно не тронуто.`); return; }
            if (raw.format !== undefined && raw.format > T.FORMAT) { confirmBox('Импорт не сделан', `«${f.name}» сделан более новым конструктором (формат ${raw.format}).`); return; }
            const read = T.normalize(raw);
            if (!read.design.nodes.length) { confirmBox('Импорт не сделан', `В «${f.name}» нет ни одной постройки. Чтобы очистить полотно, есть «Файл → Очистить».`); return; }
            const body = h('div', {}, h('p', {}, `В файле «${f.name}» построек: ${read.design.nodes.length}. Дерево на полотне заменится им; прежний файл сохранится копией рядом, а Ctrl+Z вернёт полотно.`),
                read.problems.length ? h('div', {}, h('b', {}, 'Что поправлено при чтении:'), h('ul', {}, read.problems.map(p => h('li', {}, p)))) : null);
            confirmBox('Импорт дерева', body, async () => {
                try {
                    const name = await backup();
                    commit('Импорт', d => { d.nodes = read.design.nodes; });
                    select([]); showAll(1);
                    toast(`Импортировано построек: ${read.design.nodes.length}. Копия прежнего файла: ${name || '—'}`);
                } catch (e) { toast('Импорт не сделан: ' + e.message, true); }
            }, 'Заменить');
        });
        document.body.append(input);
        input.click();
    }
    async function revertToFile() {
        try {
            const {text, version: v} = await readFile();
            const read = T.normalize(JSON.parse(text));
            version = v; lastSaved = T.serialize(read.design); base = read.design;
            if (T.serialize(read.design) === T.serialize(cur())) { setSave('ok'); toast('Полотно уже совпадает с файлом на диске'); return; }
            commit('Возврат к файлу', d => { d.nodes = read.design.nodes; });
            select([]);
            toast('Взято дерево из файла на диске. Ctrl+Z — вернуть как было');
        } catch (e) { toast('Файл не прочитан: ' + e.message, true); }
    }
    function clearAll() {
        confirmBox('Очистить полотно', `Все постройки (${cur().nodes.length}) и связи уйдут с полотна. Прежний файл сохранится копией рядом, Ctrl+Z вернёт полотно.`, async () => {
            try {
                const name = await backup();
                commit('Очистка', d => { d.nodes = []; });
                select([]);
                toast(`Полотно очищено. Копия прежнего файла: ${name || '—'}`);
            } catch (e) { toast('Не очищено: ' + e.message, true); }
        }, 'Очистить');
    }

    // ---- saving: the file at once, a copy in the browser; a failure is retried by itself every few seconds ----
    // lastSaved: the text of the file as this page last wrote or read it; base: that state as a tree (merge3's base); version: its version on the server
    let lastSaved = T.serialize(design), saving = false, again = false, saveTimer = null, saveState = 'ok', retryTimer = null;
    let base = JSON.parse(JSON.stringify(design)), conflictOpen = false, extTimer = null;
    const readFile = async () => {
        const r = await fetch('/data/tree_design.json', {cache: 'no-store'});
        if (!r.ok) throw new Error('ответ ' + r.status);
        return {text: await r.text(), version: r.headers.get('X-Tree-Version')};
    };
    const pending = () => T.serialize(cur()) !== lastSaved || !!saveTimer || saving;
    // the draft kept in the browser with the state of the file it began from (base): taken back later building by building (T.mergeDraft)
    const keepLocal = fileOk => { try { localStorage.setItem(STORE, JSON.stringify({text: T.serialize(cur()), file_ok: fileOk, at: Date.now(), base: fileOk ? null : lastSaved, version})); } catch (e) { /* no storage */ } };
    function setSave(state, err = '') {
        saveState = state;
        const t = new Date().toLocaleTimeString('ru-RU');
        saveEl.className = state;
        saveEl.textContent = state === 'ok' ? `✓ Сохранено · ${t}` : state === 'busy' ? 'Сохраняю…' : state === 'conflict' ? '⚠ Файл изменён извне' : '✗ Не сохранено';
        saveEl.title = state === 'bad' ? `Файл не записан: ${err}. Изменения хранятся в браузере; страница пробует снова каждые 5 секунд.` : 'web/data/tree_design.json';
        retryBtn.style.display = state === 'bad' ? '' : 'none';
        clearTimeout(retryTimer);
        if (state === 'bad') retryTimer = setTimeout(saveNow, 5000);
    }
    function scheduleSave() {
        keepLocal(false);
        if (saveState !== 'bad') setSave('busy');
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveNow, 200);
    }
    async function saveNow() {
        clearTimeout(saveTimer); saveTimer = null;
        if (saving) { again = true; return; }
        const text = T.serialize(cur());
        if (text === lastSaved) { keepLocal(true); setSave('ok'); return; }
        if (conflictOpen) return;
        saving = true;
        try {
            const r = await fetch('/api/tree_design' + (version ? '?base=' + encodeURIComponent(version) : ''), {method: 'POST', headers: {'Content-Type': 'application/json'}, body: text, keepalive: text.length < 60000});
            const j = await r.json().catch(() => ({}));
            if (r.status === 409 && j.error === 'conflict') {
                // the file was changed from outside since this page read it: nothing was written; its state now comes back with the answer
                saving = false;
                await fromOutside(j.text, j.version);
                return;
            }
            if (!r.ok) throw new Error(j.error || 'ответ ' + r.status);
            lastSaved = text;
            base = JSON.parse(JSON.stringify(T.normalize(JSON.parse(text)).design));
            if (j.version) version = j.version;
            if (T.serialize(cur()) === text) { keepLocal(true); setSave('ok'); }
        } catch (e) {
            setSave('bad', e.message === 'Failed to fetch' ? 'сервер не отвечает' : e.message);
        } finally {
            saving = false;
            if (!conflictOpen && (again || (T.serialize(cur()) !== lastSaved && saveState !== 'bad'))) { again = false; saveNow(); }
        }
    }
    // ---- the file changed from outside (another program, an agent, another page): asked for every two seconds while the constructor is shown ----
    async function checkOutside() {
        if (!shown || saving || conflictOpen || document.hidden) return;
        const v = await fetch('/api/tree_design/version', {cache: 'no-store'}).then(r => r.json()).catch(() => null);
        if (!v || !v.version || v.version === version || saving || conflictOpen) return;
        try {
            const f = await readFile();
            if (f.version === version) return;
            await fromOutside(f.text, f.version);
        } catch (e) { /* the server is down: the next ask */ }
    }
    // A state of the file this page did not make: nothing of the author's waits to be written, the canvas takes it at once (the view and the
    // selection stay, a step of the history, Ctrl+Z gives the canvas back as it was); something waits, merged building by building; a building
    // changed on both sides, the author chooses, and the side not chosen is kept as a copy beside the file.
    async function fromOutside(text, v) {
        let read;
        try { read = T.normalize(JSON.parse(text)); } catch (e) { toast('Файл изменён извне, но не читается как JSON: изменения здесь не тронуты', true); return; }
        const theirs = read.design, mine = cur();
        const same = T.serialize(theirs) === T.serialize(mine);
        if (same) { version = v; lastSaved = T.serialize(theirs); base = theirs; keepLocal(true); setSave('ok'); return; }
        const changedIds = T.changedNodes(base, theirs);
        const say = ids => ids.map(id => '«' + T.label(T.byId(theirs, id) || T.byId(base, id) || {id, name: ''}) + '»').slice(0, 6).join(', ') + (ids.length > 6 ? ` и ещё ${ids.length - 6}` : '');
        if (!pending()) {
            version = v; lastSaved = T.serialize(theirs); base = theirs;
            commit('Изменение файла извне', d => { d.nodes = JSON.parse(JSON.stringify(theirs.nodes)); });
            toast(`Файл изменён извне — изменения взяты: ${say(changedIds) || 'порядок построек'}. Ctrl+Z — вернуть как было`);
            return;
        }
        const m = T.merge3(base, theirs, mine);
        if (!m.clashes.length) {
            version = v; lastSaved = T.serialize(theirs); base = theirs;
            commit('Соединено с изменениями извне', d => { d.nodes = m.design.nodes; });
            toast(`Файл изменён извне (${say(changedIds)}) — соединено с вашими правками`);
            return;
        }
        // a building changed on both sides: the choice
        conflictOpen = true;
        clearTimeout(saveTimer); saveTimer = null;
        setSave('conflict');
        const mineText = T.serialize(mine);
        const resolve = async keepMine => {
            closeModal(true);
            try {
                // the side not chosen, whole, as a copy beside the file
                const name = await backup(keepMine ? text : mineText);
                const nodes = m.design.nodes.map(n => (m.clashes.includes(n.id) && keepMine && T.byId(mine, n.id) ? JSON.parse(JSON.stringify(T.byId(mine, n.id))) : n));
                // a building deleted here and changed there: kept as the file has it unless the author keeps his side
                const finalNodes = keepMine ? nodes.filter(n => !(m.clashes.includes(n.id) && !T.byId(mine, n.id))) : nodes;
                version = v; lastSaved = T.serialize(theirs); base = theirs;
                conflictOpen = false;
                commit(keepMine ? 'Конфликт: оставлены мои правки' : 'Конфликт: взято из файла', d => { d.nodes = finalNodes; });
                if (T.serialize(cur()) === lastSaved) setSave('ok'); else scheduleSave();
                toast(`${keepMine ? 'Оставлены ваши правки' : 'Взято из файла'}; другая сторона целиком — в копии ${name || ''}`);
            } catch (e) { conflictOpen = false; toast('Не решено: ' + e.message, true); setSave('bad', e.message); }
        };
        const list = m.clashes.map(id => h('li', {}, T.label(T.byId(mine, id) || T.byId(theirs, id) || {id, name: ''}),
            !T.byId(mine, id) ? ' — здесь удалена, в файле изменена' : !T.byId(theirs, id) ? ' — в файле удалена, здесь изменена' : ''));
        const box = modal([h('h3', {}, 'Файл изменён извне'),
            h('p', {}, 'Пока здесь были несохранённые правки, файл web/data/tree_design.json изменили извне. Всё, что менялось только с одной стороны, уже соединено. С обеих сторон изменены постройки:'),
            h('ul', {}, list),
            h('p', {class: 'help'}, 'Что не выберете — не пропадёт: оно сохранится целиком копией рядом с файлом (tree_design.backup-…json).'),
            h('div', {class: 'btns'}, h('button', {onclick: () => resolve(false)}, 'Взять из файла'), h('button', {class: 'danger', onclick: () => resolve(true)}, 'Оставить мои правки'))],
        'cx-dialog', {sticky: true});
        box.querySelector('.btns button').focus();
    }
    const startWatch = () => { if (!extTimer) extTimer = setInterval(checkOutside, 2000); };
    // Leaving the page (F5, closing): what is not in the file yet goes with the page's last request (sendBeacon); the question «Покинуть сайт?»
    // only when that cannot go (the server did not answer before)
    window.addEventListener('beforeunload', e => {
        const text = T.serialize(cur());
        if (text === lastSaved) return;
        keepLocal(false);
        const sent = saveState !== 'bad' && !conflictOpen && navigator.sendBeacon && navigator.sendBeacon('/api/tree_design' + (version ? '?base=' + encodeURIComponent(version) : ''), new Blob([text], {type: 'application/json'}));
        if (!sent) { e.preventDefault(); e.returnValue = ''; }
    });

    function updateTools() {
        tb.undo.disabled = !hist.canUndo; tb.redo.disabled = !hist.canRedo;
        tb.undo.title = hist.canUndo ? `Отменить: ${hist.undoLabel} (Ctrl+Z)` : 'Отменять нечего';
        tb.redo.title = hist.canRedo ? `Повторить: ${hist.redoLabel} (Ctrl+Y)` : 'Повторять нечего';
        tb.del.disabled = !sel.size && !selEdge; tb.dup.disabled = !sel.size;
    }

    // ---- start ----
    warnList = T.warnings(cur(), checkCtx);
    renderCanvas(); renderPalette(); renderWarnings(); renderProps(); updateTools(); setSave('ok');
    new ResizeObserver(() => { if (shown) renderRows(); }).observe(cv);
    // a narrow status line keeps the zoom and the checks; the hint goes when it would wrap into more than two lines
    new ResizeObserver(() => status.classList.toggle('narrow', status.clientWidth < 720)).observe(status);
    // what the browser kept that never reached the file (the server was down): offered back
    try {
        const kept = JSON.parse(localStorage.getItem(STORE) || 'null');
        if (kept && !kept.file_ok && kept.text && T.serialize(T.normalize(JSON.parse(kept.text)).design) !== T.serialize(design)) {
            const keptRaw = JSON.parse(kept.text), baseRaw = kept.base ? JSON.parse(kept.base) : null;
            // building by building over the file as it is now: what the file got since (the lines, new fields) is not lost
            const m = T.mergeDraft(design, keptRaw, baseRaw);
            const changes = T.changedNodes(design, m.design).length;
            const banner = h('div', {class: 'cx-banner'}, h('span', {}, `В браузере остались изменения от ${new Date(kept.at).toLocaleString('ru-RU')}, которые не дошли до файла (построек с правками: ${changes}). `
                + `Они соединятся с файлом по постройкам${m.clashes.length ? `; ${m.clashes.length} изменены и в файле — там останется файл, ваш черновик целиком сохранится копией` : ''}.`),
                h('button', {onclick: async () => {
                    banner.remove();
                    if (m.clashes.length) { try { await backup(kept.text); } catch (e) { /* the draft stays in the browser */ } }
                    commit('Изменения из браузера', d => { d.nodes = m.design.nodes; });
                    showAll(1);
                }}, 'Взять их'),
                h('button', {onclick: () => { banner.remove(); keepLocal(true); }}, 'Оставить файл'));
            cv.append(banner);
        } else if (kept && !kept.file_ok) keepLocal(true);       // they did reach it (the last request of the page before)
    } catch (e) { /* nothing kept */ }
    if (problems.length) toast('Файл дерева прочитан с поправками: ' + problems.join('; '), true);
    else if (migrated) { lastSaved = ''; scheduleSave(); toast(`Файл переведён в новый формат${migrated.lines ? `: линейки уровней мода проставлены (${migrated.lines}), наследование у них выключено` : ''}`); }
    let first = true;
    return {
        show() { shown = true; paintFolds(); startWatch(); checkOutside(); if (first) { first = false; requestAnimationFrame(() => showAll(1)); } else applyView(); },
        hide() { shown = false; hideMenu(); closeModal(); },
        design: () => cur(),
        // for checks from the console and the test scripts
        api: {hist, select, view, showAll, toast, fold, get folded() { return {...folded}; }, get sel() { return [...sel]; }, get selEdge() { return selEdge; },
              saveState: () => saveState, saveNow, lastSaved: () => lastSaved, cardOf: id => cardOf(T.byId(cur(), id)), applyView, checkOutside,
              version: () => version, conflictOpen: () => conflictOpen},
    };
}
