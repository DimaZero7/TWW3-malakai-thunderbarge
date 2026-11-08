// The airship screen, "Корабль" tab: the drawing on the left with the stage of each part, the levels of a chain on the right, order and cancel.
// Built as build() of src/tww3_mtb_crew_ui.lua: the same root, the same sizes and offsets, so the numbers carry over to the game.
// Reads only the module (web/js/barge_buildings.js); a click calls it, refresh() reads it back.

import {turnsText} from './barge_buildings.js';

const LAYOUTS = 'ui/tww3_mtb/';
const WEB_ART = LAYOUTS + 'web/';       // the stage layers; in the game they would be ui/tww3_mtb/<name>.png like the others
const ROW = 'mtb_ship_row_', ORDER = 'mtb_ship_order', CANCEL = 'mtb_ship_cancel', DEMOLISH = 'mtb_ship_demolish';
const MAX_ROWS = 6;
let view_flags = {};

// helpers as in the Lua
function make(parent, id, layout) { return parent.CreateComponent(id, layout); }
function size(c, w, h) { c.Resize(Math.floor(w + 0.5), Math.floor(h + 0.5)); }
function at(c, x, y) { c.SetDockOffset(Math.floor(x + 0.5), Math.floor(y + 0.5)); }
function image(parent, id, path, x, y, w, h) { const c = make(parent, id, 'image'); c.SetImagePath(path, 0); size(c, w, h); at(c, x, y); return c; }
function text(parent, id, layout, x, y, w, h, value) { const c = make(parent, id, layout); size(c, w, h); at(c, x, y); c.SetStateText(value || ''); return c; }
function grey(c, on) { c.ShaderTechniqueSet(on ? 'set_greyscale_t0' : 'normal_t0', true); }

export function makePanel(root, M, data, art, blueprint, flags, cards = {}) {
    view_flags = flags;
    const view = {rows: [], layers: {}, selected: null};
    const W = root.Width(), H = root.Height();
    const panel_w = Math.min(W - 40, 1560), panel_h = Math.min(H - 30, 870);
    const title_h = 66, pad = 16;
    let scheme_h = panel_h - title_h - pad - 6;
    let scheme_w = scheme_h * data.art.size[0] / data.art.size[1];
    let column_w = panel_w - scheme_w - pad * 3;
    if (column_w < 360) { column_w = 360; scheme_w = panel_w - column_w - pad * 3; scheme_h = scheme_w * data.art.size[1] / data.art.size[0]; }
    const scale = scheme_w / data.art.size[0];
    const top = title_h;

    const backdrop = make(root, 'mtb_ship_panel', 'backdrop');
    size(backdrop, W, H);
    backdrop.MoveTo(0, 0);
    const frame = make(root, 'frame', 'frame');     // in the game a child of the backdrop, docked at its centre (SetDockingPoint(5)); here placed at the same spot
    size(frame, panel_w, panel_h);
    at(frame, (W - panel_w) / 2, (H - panel_h) / 2);

    const title_w = Math.min(769, panel_w - 160);
    image(frame, 'title_back', 'ui/skins/wh_main_dwf_dwarfs/panel_title_large.png', (panel_w - title_w) / 2, 2, title_w, 62);
    text(frame, 'title', 'text_title', (panel_w - title_w) / 2, 8, title_w, 50, '«Дух Грунгни»');
    const close = image(frame, 'mtb_ship_close', 'ui/skins/default/icon_cross.png', panel_w - 14 - 34, 14, 34, 34);
    close.SetTooltipText('Закрыть (Esc). На этой странице панель не закрывается', true);
    // the treasury, in the corner: in the game the same number is in the HUD's top bar too
    image(frame, 'gold_icon', 'ui/skins/default/icon_treasury.png', 22, 18, 26, 26);
    view.gold = text(frame, 'gold', 'text_head', 54, 16, 160, 30, '');
    view.gold.SetTooltipText('Казна фракции', true);

    // the drawing and its layers: pencil, hatching, ink per part, all created, one visible (SetVisible), as the panel's mount_ and occ_ layers
    const sx = pad, sy = top;
    const sheet = image(frame, 'scheme', LAYOUTS + blueprint.sheet + '.png', sx, sy, scheme_w, scheme_h);
    view.sheet = sheet;
    view.sheets = blueprint.sheets ? {sheets: blueprint.sheets, part: blueprint.sheet_part} : null;     // the whole drawing changes with this part's stage
    view.cards = cards;
    const place = (name) => art.places[name] || data.art.layers[name];
    // a layer of the panel's own art (data/crew_ui_art.json: mount_cannons, mount_bombs) or of tools/web_art.py
    const layerPath = (name) => (data.art.layers[name] ? LAYOUTS : WEB_ART) + name + '.png';
    for (const [part, spec] of Object.entries(blueprint.parts)) {
        if (!spec.enabled && !flags.all_parts) continue;      // only the data is ready: the base drawing has nothing of it
        const layers = {};
        for (const stage of ['pencil', 'build', 'ink']) {
            const name = spec[stage];
            if (!name) continue;                               // not drawn yet
            const p = place(name);
            layers[stage] = image(sheet, `${part}_${stage}`, layerPath(name), p[0] * scale, p[1] * scale, p[2] * scale, p[3] * scale);
        }
        // the turns left, live text on the drawing while it is built (TurnsToCompletion in the game)
        layers.turns = text(sheet, `${part}_turns`, 'text_ink', spec.turns_at[0] * scale, spec.turns_at[1] * scale, 80, 22, '');
        view.layers[part] = layers;
    }
    const sheet_frame = make(frame, 'scheme_frame', 'frame_edge');
    size(sheet_frame, scheme_w + 8, scheme_h + 8);
    at(sheet_frame, sx - 4, sy - 4);

    // the column: the levels of the chain, then what the selected one gives, then the commands
    const cx = sx + scheme_w + pad;
    const column = make(frame, 'column', 'frame_dark');
    size(column, column_w, scheme_h);
    at(column, cx, sy);
    view.head = text(column, 'head', 'text_head', 14, 6, column_w - 28, 28, 'Корабль');
    view.about = text(column, 'about', 'text_body', 14, 32, column_w - 28, 40, '');
    const rows_top = 80, row_gap = 4, foot_h = 82;
    const row_h = Math.min(92, Math.floor((scheme_h - rows_top - foot_h - row_gap * (MAX_ROWS - 1) - 8) / MAX_ROWS));
    // a stage with a tree of buildings (blueprint.json, tree; ?tree=demo the example) shows it instead of rows
    const treeMode = !!(blueprint.tree || (flags.tree === 'demo' && blueprint.tree_demo));
    view.detail_top = rows_top;
    if (treeMode) {
        view.detail_top = rows_top + 6 + makeTree(column, view, M, blueprint, flags, 14, rows_top + 6, column_w - 28) + 16;
        view.selName = text(column, 'sel_name', 'text_head', 14, 0, column_w - 28, 26, '');
        view.selMeta = text(column, 'sel_meta', 'text_line', 14, 0, column_w - 28, 20, '');
    } else {
        for (let i = 0; i < MAX_ROWS; i++) view.rows.push(makeRow(column, i + 1, 8, rows_top + i * (row_h + row_gap), column_w - 16, row_h));
    }
    // details of the selected level: the game's short description and its green lines
    view.detail = text(column, 'detail', 'text_body', 14, 0, column_w - 28, 44, '');
    view.lines = text(column, 'lines', 'text_green', 14, 0, column_w - 28, 80, '');
    // commands
    const button_w = (column_w - 28 - 10) / 2, button_h = 46;
    const buttons_y = scheme_h - foot_h - button_h - 34;
    view.order = makeButton(column, ORDER, 14, buttons_y, button_w, button_h, 'Заказать');
    view.cancel = makeButton(column, CANCEL, 14 + button_w + 10, buttons_y, button_w, button_h, 'Отменить');
    view.demolish = makeButton(column, DEMOLISH, 14, buttons_y - button_h - 8, button_w, button_h, 'Снести');
    view.demolishShown = !!blueprint.demolish;
    view.demolish.button.SetVisible(!!(flags.full || blueprint.demolish));
    view.demolish.button.SetTooltipText('Снести постройку. Золото не возвращается: возврата при сносе в данных нет (допущение). В игре корпус снести нельзя, здесь можно для проверки', true);
    view.message = text(column, 'message', 'text_copper', 14, scheme_h - foot_h - 26, column_w - 28, 22, '');
    text(column, 'foot', 'text_note', 14, scheme_h - foot_h + 2, column_w - 28, foot_h - 6,
        'Постройка идёт через очередь игры: цена списывается при заказе, отмена в том же ходу возвращает всё. Готовая часть встаёт на модель и на чертёж в начале хода.');

    // which levels show: the first of the chain now, all of it behind ?full=1
    view.levels = [];
    for (const key of blueprint.chains) {
        const chain = M.chain(key);
        view.levels.push(...(blueprint.first_only && !flags.full ? chain.levels.slice(0, 1) : chain.levels));
    }
    if (!view.tree) view.selected = view.levels.length ? view.levels[0].key : null;
    if (view.tree && flags.tree === 'demo') view.about.SetStateText('Пример дерева (?tree=demo): узлы и связи придуманы, не из данных.');
    else if (blueprint.caption) view.about.SetStateText(blueprint.caption);
    else if (view.levels.length) view.about.SetStateText(blueprint.first_only && !flags.full ? `Первая постройка линейки пушек: «${view.levels[0].name}».` : 'Линейка пушек: порты, палуба, арсенал, органы.');

    view.root = backdrop;
    view.frame = frame;
    view.scale = scale;
    return {view, refresh: () => refresh(view, M), click: (c) => click(view, M, c)};
}

// ---------------- the tree of buildings: square nodes joined by brass lines, laid out from the requirements ----------------
// Tiers by depth (the longest way from a node with no requirement), the order inside a tier by the mean place of the nodes it needs (one pass, enough
// for a small tree), every tier spread evenly across the width. direction "down": the first buildings on top, what needs them below; "up": the other way.
// Lines run square: from a node to halfway, across, on to the other node; lines that meet share their halfway.
const NODE = 68, TIER_GAP = 104, LINE = 3;
const TREE = 'mtb_tree_node_';

export function treeLayout(nodes) {
    const byKey = Object.fromEntries(nodes.map(n => [n.key, n]));
    const tier = {};
    const depth = k => {
        if (tier[k] !== undefined) return tier[k];
        const needs = byKey[k].needs.filter(p => byKey[p]);
        tier[k] = needs.length ? 1 + Math.max(...needs.map(depth)) : 0;
        return tier[k];
    };
    nodes.forEach(n => depth(n.key));
    const tiers = [];
    for (const n of nodes) (tiers[tier[n.key]] ||= []).push(n.key);
    const place = {};
    tiers.forEach((keys, t) => {
        if (t > 0) {
            const mean = k => { const ps = byKey[k].needs.filter(p => place[p] !== undefined); return ps.length ? ps.reduce((a, p) => a + place[p], 0) / ps.length : 0.5; };
            keys.sort((a, b) => mean(a) - mean(b));
        }
        keys.forEach((k, i) => { place[k] = (i + 0.5) / keys.length; });
    });
    return {tier, tiers, place};
}

function treeNodes(blueprint, M, flags) {
    // ?tree=demo: the example of blueprint.json (tree_demo), its own nodes and links; otherwise the stage's buildings, links from the data:
    // the level below in the same chain and the buildings each level requires, when they are in the tree too
    if (flags.tree === 'demo' && blueprint.tree_demo) return blueprint.tree_demo.nodes.map(n => ({...n, demo: true}));
    const keys = (blueprint.tree ? blueprint.tree.nodes : []).map(k => M.prefix + k);
    return keys.map(key => {
        const row = M.level(key);
        const chain = M.chain(row.chain);
        const below = chain && chain.levels.find(l => l.level === row.level - 1);
        const needs = [...(below ? [below.key] : []), ...row.requires].filter(k => keys.includes(k));
        return {key, name: row.name, icon: row.icon ? 'ui/buildings/icons/tww3_mtb_' + row.icon : null, needs};
    });
}

function makeTree(parent, view, M, blueprint, flags, x, y, w) {
    const nodes = treeNodes(blueprint, M, flags);
    const direction = flags.dir || (blueprint.tree && blueprint.tree.direction) || 'down';
    const {tier, tiers, place} = treeLayout(nodes);
    const height = tiers.length ? (tiers.length - 1) * TIER_GAP + NODE : 0;
    const pos = {};
    for (const n of nodes) {
        const t = direction === 'up' ? tiers.length - 1 - tier[n.key] : tier[n.key];
        pos[n.key] = {x: x + place[n.key] * w - NODE / 2, y: y + t * TIER_GAP};
    }
    // the lines first, under the nodes
    let seg = 0;
    const line = (x0, y0, x1, y1) => {
        const c = image(parent, `tree_line_${seg++}`, WEB_ART + 'tree_line.png', Math.min(x0, x1) - LINE / 2, Math.min(y0, y1) - LINE / 2,
                        Math.abs(x1 - x0) + LINE, Math.abs(y1 - y0) + LINE);
        return c;
    };
    for (const n of nodes) {
        for (const p of n.needs) {
            if (!pos[p]) continue;
            const a = pos[p], b = pos[n.key];
            const ax = a.x + NODE / 2, bx = b.x + NODE / 2;
            const down = b.y > a.y;
            const ay = down ? a.y + NODE : a.y, by = down ? b.y : b.y + NODE;
            const mid = (ay + by) / 2;
            line(ax, ay, ax, mid); line(ax, mid, bx, mid); line(bx, mid, bx, by);
        }
    }
    view.tree = nodes.map((n, i) => {
        const b = make(parent, TREE + i, 'button_plate');
        size(b, NODE, NODE);
        at(b, pos[n.key].x, pos[n.key].y);
        const v = {node: n, button: b};
        // a piece of parchment under the icon: the mod's building icons are dark and do not read on the dark plate
        v.back = image(b, 'back', WEB_ART + 'node_back.png', 9, 9, NODE - 18, NODE - 18);
        v.icon = image(b, 'icon', n.icon || 'ui/skins/default/icon_check.png', 11, 11, NODE - 22, NODE - 22);
        v.check = image(b, 'check', 'ui/skins/default/icon_check.png', NODE - 24, 2, 22, 22);
        v.padlock = image(b, 'padlock', 'ui/skins/default/icon_padlock.png', NODE - 24, 2, 22, 22);
        v.hourglass = image(b, 'hourglass', 'ui/skins/default/icon_hourglass.png', 4, NODE - 22, 18, 18);
        v.turns = text(b, 'turns', 'text_line', 22, NODE - 23, NODE - 24, 20, '');
        return v;
    });
    view.selected = nodes.length ? nodes[0].key : null;
    return height;
}

function nodeStatus(M, n) {
    return n.demo ? {state: 'demo'} : M.status(n.key);
}

function refreshTree(view, M) {
    for (const v of view.tree) {
        const st = nodeStatus(M, v.node);
        const locked = st.state === 'locked' || st.state === 'unknown';
        // a locked node stays clickable (its details tell why): grey icon and a padlock, not the plate's disabled state
        v.button.SetState(view.selected === v.node.key ? 'selected' : 'active');
        grey(v.icon, locked);
        v.check.SetVisible(st.state === 'built');
        v.padlock.SetVisible(locked);
        v.hourglass.SetVisible(st.state === 'building');
        v.turns.SetVisible(st.state === 'building');
        v.turns.SetStateText(st.state === 'building' ? String(st.turns) : '');
        const state = {built: 'построено', building: `строится, ${turnsText(st.turns || 0)}`, open: 'можно заказать', locked: st.why || 'недоступно', demo: 'пример, не из данных'}[st.state] || '';
        v.button.SetTooltipText(`${v.node.name}\n${state}`, true);
    }
}

function makeButton(parent, id, x, y, w, h, label) {
    const b = make(parent, id, 'button_plate');
    size(b, w, h);
    at(b, x, y);
    const t = text(b, 'label', 'text_button', 0, 0, w, h, label);
    return {button: b, label: t};
}

function makeRow(parent, i, x, y, w, h) {
    const b = make(parent, ROW + i, 'button_row');
    size(b, w, h);
    at(b, x, y);
    const o = 0;
    const view = {button: b};
    const icon = h - 20;
    view.icon = image(b, 'icon', 'ui/skins/default/icon_check.png', 10 + o, 10 + o, icon, icon);
    const tx = 10 + icon + 10;
    view.name = text(b, 'name', 'text_name', tx + o, 7 + o, w - tx - 130, 22, '');
    view.name_grey = text(b, 'name_grey', 'text_name_grey', tx + o, 7 + o, w - tx - 130, 22, '');
    view.check = image(b, 'check', 'ui/skins/default/icon_check.png', w - 46 + o, 5 + o, 30, 30);
    view.padlock = image(b, 'padlock', 'ui/skins/default/icon_padlock.png', w - 46 + o, 5 + o, 30, 30);
    // price and time on the second line: the chest is a price, the hourglass the turns, as on the game's building cards
    view.cost_icon = image(b, 'cost_icon', 'ui/skins/default/icon_treasury.png', tx + o, 32 + o, 18, 18);
    view.cost = text(b, 'cost', 'text_line', tx + 22 + o, 31 + o, 70, 20, '');
    view.time_icon = image(b, 'time_icon', 'ui/skins/default/icon_hourglass.png', tx + 100 + o, 32 + o, 18, 18);
    view.time = text(b, 'time', 'text_line', tx + 122 + o, 31 + o, 80, 20, '');
    view.note = text(b, 'note', 'text_line', tx + o, h - 28 + o, w - tx - 16, 22, '');
    view.note_grey = text(b, 'note_grey', 'text_copper', tx + o, h - 28 + o, w - tx - 16, 22, '');
    return view;
}

// The green lines of a level: every effect with the game's text (the overview's card) when there is one, the mod's own lines otherwise.
function effectLines(row, card) {
    if (!card) return row.lines;
    return card.effects.filter(e => !e.hidden).map(e => (e.text || `${e.effect} = ${e.value}`) + (e.off ? ' (выключено модом)' : ''));
}

function tooltip(row, status, card) {
    const lines = [`[[col:yellow]]${row.name}[[/col]]`];
    if (card && card.game_name && card.game_name !== row.name) lines.push(`В игре: «${card.game_name}». Название — мода`);
    const text = row.text || (card && card.text);
    if (text) lines.push(text);
    lines.push(`Цена: ${row.cost} золота, срок: ${turnsText(row.turns)}`);
    for (const l of effectLines(row, card)) lines.push(`[[col:green]]${l}[[/col]]`);
    if (status.why) lines.push(status.why);
    return lines.join('\n');
}

function refresh(view, M) {
    view.gold.SetStateText(String(M.game.treasury()));
    if (view.sheets) view.sheet.SetImagePath(LAYOUTS + view.sheets.sheets[M.stage(view.sheets.part)] + '.png', 0);
    for (const [part, layers] of Object.entries(view.layers)) {
        const stage = M.stage(part);
        for (const s of ['pencil', 'build', 'ink']) if (layers[s]) layers[s].SetVisible(s === stage);
        const st = stage === 'build' ? M.status(M.prefix + M.parts[part].building) : {};
        if (stage === 'build' && !layers.build) layers.turns.SetVisible(false);
        layers.turns.SetVisible(stage === 'build');
        layers.turns.SetStateText(st.state === 'building' ? turnsText(st.turns) : '');
    }
    if (view.tree) refreshTree(view, M);
    let rowsShown = 0;
    view.rows.forEach((r, i) => {
        const row = view.levels[i];
        if (!row) { r.button.SetVisible(false); return; }
        rowsShown++;
        const st = M.status(row.key);
        const locked = st.state === 'locked';
        r.button.SetVisible(true);
        r.button.SetState(locked ? 'inactive' : view.selected === row.key ? 'selected' : 'active');
        r.icon.SetImagePath(row.icon ? 'ui/buildings/icons/tww3_mtb_' + row.icon : 'ui/skins/default/icon_check.png', 0);
        grey(r.icon, locked);
        r.name.SetVisible(!locked); r.name_grey.SetVisible(locked);
        r.name.SetStateText(row.name); r.name_grey.SetStateText(row.name);
        r.check.SetVisible(st.state === 'built');
        r.padlock.SetVisible(locked);
        r.cost.SetStateText(String(row.cost));
        r.time.SetStateText(turnsText(row.turns));
        const note = st.state === 'built' ? 'Построено' : st.state === 'building' ? `Строится: осталось ${turnsText(st.turns)}` : st.state === 'open' ? 'Можно заказать' : '';
        r.note.SetVisible(!locked); r.note_grey.SetVisible(locked);
        r.note.SetStateText(note); r.note_grey.SetStateText(st.why || '');
        r.button.SetTooltipText(tooltip(row, st, view.cards[row.key]), true);
        r.row = row;
    });
    // details under the rows or the tree; none while the stage has no buildings
    const demo = view.tree && view.tree.find(v => v.node.key === view.selected && v.node.demo);
    if (view.selName) {
        const node = view.tree && view.tree.find(v => v.node.key === view.selected);
        view.selName.SetVisible(!!node);
        view.selMeta.SetVisible(!!node);
        if (node) {
            at(view.selName, 14, view.detail_top);
            at(view.selMeta, 14, view.detail_top + 28);
            view.selName.SetStateText(node.node.name);
        }
    }
    if (demo) {
        for (const c of [view.lines, view.order.button, view.cancel.button, view.demolish.button]) c.SetVisible(false);
        view.selMeta.SetStateText('Пример: узел не из данных, заказать нельзя');
        view.detail.SetVisible(false);
        view.message.SetStateText(M.message() || '');
        return;
    }
    if (view.tree) view.demolish.button.SetVisible(!!(view_flags.full || view.demolishShown));
    const sel = view.selected && M.level(view.selected);
    for (const c of [view.detail, view.lines, view.order.button, view.cancel.button]) c.SetVisible(!!sel);
    if (!sel) {
        view.demolish.button.SetVisible(false);
        view.message.SetStateText(M.message() || '');
        return;
    }
    const y = view.tree ? view.detail_top + 52 : view.detail_top + rowsShown * 96 + 8;
    at(view.detail, 14, y);
    const card = view.cards[sel.key];
    if (view.selMeta) {
        const s0 = M.status(sel.key);
        const state = {built: 'Построено', building: `Строится: осталось ${turnsText(s0.turns || 0)}`, open: 'Можно заказать', locked: s0.why || 'Недоступно'}[s0.state] || '';
        view.selMeta.SetStateText(`Цена: ${sel.cost} золота · ${turnsText(sel.turns)} · ${state}`);
    }
    view.detail.SetStateText(sel.text || (card && card.text) || '');
    at(view.lines, 14, y + 46);
    view.lines.SetStateText(effectLines(sel, card).join('\n'));
    const st = M.status(sel.key);
    view.order.button.SetState(st.state === 'open' ? 'active' : 'inactive');
    view.order.button.SetTooltipText(st.state === 'open' ? `Заказать «${sel.name}»: ${sel.cost} золота, ${turnsText(sel.turns)}` : (st.why || (st.state === 'building' ? 'Уже строится' : 'Уже построено')), true);
    view.cancel.button.SetState(st.state === 'building' ? 'active' : 'inactive');
    view.cancel.button.SetTooltipText(st.state === 'building' ? `Отменить стройку, ${sel.cost} золота вернутся` : 'Нечего отменять', true);
    view.demolish.button.SetState(st.state === 'built' ? 'active' : 'inactive');
    view.message.SetStateText(M.message() || '');
}

function click(view, M, c) {
    const id = c.Id();
    if (id.startsWith(TREE)) {
        const v = view.tree[Number(id.slice(TREE.length))];
        if (v) view.selected = v.node.key;
    } else if (id.startsWith(ROW)) {
        const r = view.rows[Number(id.slice(ROW.length)) - 1];
        if (r && r.row) view.selected = r.row.key;
    } else if (!view.selected) {
        // nothing to order yet
    } else if (id === ORDER) {
        M.order(view.selected);
    } else if (id === CANCEL) {
        M.cancel(view.selected);
    } else if (id === DEMOLISH) {
        M.demolish(view.selected);
    }
    refresh(view, M);
}
