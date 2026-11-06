// The airship screen, "Корабль" tab: the drawing on the left with the stage of each part, the levels of a chain on the right, order and cancel.
// Built as build() of src/tww3_mtb_crew_ui.lua: the same root, the same sizes and offsets, so the numbers carry over to the game.
// Reads only the module (web/js/barge_buildings.js); a click calls it, refresh() reads it back.

import {turnsText} from './barge_buildings.js';

const LAYOUTS = 'ui/tww3_mtb/';
const WEB_ART = LAYOUTS + 'web/';       // the stage layers; in the game they would be ui/tww3_mtb/<name>.png like the others
const ROW = 'mtb_ship_row_', ORDER = 'mtb_ship_order', CANCEL = 'mtb_ship_cancel', DEMOLISH = 'mtb_ship_demolish';
const MAX_ROWS = 6;

// helpers as in the Lua
function make(parent, id, layout) { return parent.CreateComponent(id, layout); }
function size(c, w, h) { c.Resize(Math.floor(w + 0.5), Math.floor(h + 0.5)); }
function at(c, x, y) { c.SetDockOffset(Math.floor(x + 0.5), Math.floor(y + 0.5)); }
function image(parent, id, path, x, y, w, h) { const c = make(parent, id, 'image'); c.SetImagePath(path, 0); size(c, w, h); at(c, x, y); return c; }
function text(parent, id, layout, x, y, w, h, value) { const c = make(parent, id, layout); size(c, w, h); at(c, x, y); c.SetStateText(value || ''); return c; }
function grey(c, on) { c.ShaderTechniqueSet(on ? 'set_greyscale_t0' : 'normal_t0', true); }

export function makePanel(root, M, data, art, blueprint, flags) {
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
    for (let i = 0; i < MAX_ROWS; i++) view.rows.push(makeRow(column, i + 1, 8, rows_top + i * (row_h + row_gap), column_w - 16, row_h));
    // details of the selected level: the game's short description and its green lines
    view.detail_top = rows_top;
    view.detail = text(column, 'detail', 'text_body', 14, 0, column_w - 28, 44, '');
    view.lines = text(column, 'lines', 'text_green', 14, 0, column_w - 28, 80, '');
    // commands
    const button_w = (column_w - 28 - 10) / 2, button_h = 46;
    const buttons_y = scheme_h - foot_h - button_h - 34;
    view.order = makeButton(column, ORDER, 14, buttons_y, button_w, button_h, 'Заказать');
    view.cancel = makeButton(column, CANCEL, 14 + button_w + 10, buttons_y, button_w, button_h, 'Отменить');
    view.demolish = makeButton(column, DEMOLISH, 14, buttons_y - button_h - 8, button_w, button_h, 'Снести');
    view.demolish.button.SetVisible(!!flags.full);
    view.message = text(column, 'message', 'text_copper', 14, scheme_h - foot_h - 26, column_w - 28, 22, '');
    text(column, 'foot', 'text_note', 14, scheme_h - foot_h + 2, column_w - 28, foot_h - 6,
        'Постройка идёт через очередь игры: цена списывается при заказе, отмена в том же ходу возвращает всё. Готовая часть встаёт на модель и на чертёж в начале хода.');

    // which levels show: the first of the chain now, all of it behind ?full=1
    view.levels = [];
    for (const key of blueprint.chains) {
        const chain = M.chain(key);
        view.levels.push(...(blueprint.first_only && !flags.full ? chain.levels.slice(0, 1) : chain.levels));
    }
    view.selected = view.levels[0].key;
    const chainName = view.levels[0].name;
    view.about.SetStateText(blueprint.first_only && !flags.full ? `Первая постройка линейки пушек: «${chainName}».` : 'Линейка пушек: порты, палуба, арсенал, органы.');

    view.root = backdrop;
    view.frame = frame;
    view.scale = scale;
    return {view, refresh: () => refresh(view, M), click: (c) => click(view, M, c)};
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

function tooltip(row, status) {
    const lines = [`[[col:yellow]]${row.name}[[/col]]`];
    if (row.text) lines.push(row.text);
    lines.push(`Цена: ${row.cost} золота, срок: ${turnsText(row.turns)}`);
    for (const l of row.lines) lines.push(`[[col:green]]${l}[[/col]]`);
    if (status.why) lines.push(status.why);
    return lines.join('\n');
}

function refresh(view, M) {
    view.gold.SetStateText(String(M.game.treasury()));
    for (const [part, layers] of Object.entries(view.layers)) {
        const stage = M.stage(part);
        for (const s of ['pencil', 'build', 'ink']) if (layers[s]) layers[s].SetVisible(s === stage);
        const st = stage === 'build' ? M.status(M.prefix + M.parts[part].building) : {};
        layers.turns.SetVisible(stage === 'build');
        layers.turns.SetStateText(st.state === 'building' ? turnsText(st.turns) : '');
    }
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
        r.button.SetTooltipText(tooltip(row, st), true);
        r.row = row;
    });
    // details under the rows
    const sel = M.level(view.selected);
    const y = view.detail_top + rowsShown * 96 + 8;
    at(view.detail, 14, y);
    view.detail.SetStateText(sel.text);
    at(view.lines, 14, y + 46);
    view.lines.SetStateText(sel.lines.join('\n'));
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
    if (id.startsWith(ROW)) {
        const r = view.rows[Number(id.slice(ROW.length)) - 1];
        if (r && r.row) view.selected = r.row.key;
    } else if (id === ORDER) {
        M.order(view.selected);
    } else if (id === CANCEL) {
        M.cancel(view.selected);
    } else if (id === DEMOLISH) {
        M.demolish(view.selected);
    }
    refresh(view, M);
}
