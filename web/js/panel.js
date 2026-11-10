// The airship screen, "Корабль" tab: the drawing on the left with the stage of each part, the levels of a chain on the right, order and cancel.
// Built as build() of src/tww3_mtb_crew_ui.lua: the same root, the same sizes and offsets, so the numbers carry over to the game.
// Reads only the module (web/js/barge_buildings.js); a click calls it, refresh() reads it back.

import {turnsText} from './barge_buildings.js';

const LAYOUTS = 'ui/tww3_mtb/';
const WEB_ART = LAYOUTS + 'web/';       // the stage layers; in the game they would be ui/tww3_mtb/<name>.png like the others
const ROW = 'mtb_ship_row_', ORDER = 'mtb_ship_order', CANCEL = 'mtb_ship_cancel', DEMOLISH = 'mtb_ship_demolish';
const MAX_ROWS = 6;
const SIDE = 'mtb_side_';
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
    const view = {rows: [], layers: {}, selected: null, crew: [], data};
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
    view.sheets = blueprint.sheets || null;     // rules: the first whose part is at its stage gives the whole drawing
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
    // Malakai's side: the ship's plan in the drawing's lower left corner, a mark on each side, his figure on the drawing (near side ink, far side pencil)
    const ms = art.malakai_side;
    if (blueprint.malakai_side && ms) {
        const p = place('plan_ship');
        view.side = {show_when: blueprint.malakai_side.show_when, plan: image(sheet, 'plan_ship', WEB_ART + 'plan_ship.png', p[0] * scale, p[1] * scale, p[2] * scale, p[3] * scale), marks: {}};
        view.side.portraits = {};
        // the halo under each mark while the side was never chosen: two pictures switched by a timer, as the game blinks a tutorial's button
        view.side.glows = {};
        const glow = ms.glow;
        // one image per phase, all loaded once, one shown at a time: as a component with a state per phase (SetState by a timer in the game)
        for (const s of ['left', 'right']) {
            const size = ms.mark * glow.size, off = (size - ms.mark) / 2;
            const holder = image(sheet, 'side_glow_' + s, WEB_ART + 'glow_0.png', (ms.marks[s][0] - off) * scale, (ms.marks[s][1] - off) * scale, size * scale, size * scale);
            holder.SetPassive();
            holder.phases = [];
            for (let i = 1; i < glow.phases; i++) {
                const ph = image(holder, 'phase_' + i, WEB_ART + `glow_${i}.png`, 0, 0, size * scale, size * scale);
                ph.SetVisible(false);
                holder.phases.push(ph);
            }
            holder.img.style.visibility = 'visible';
            view.side.glows[s] = holder;
        }
        view.side.phase = 0;
        setInterval(() => {         // GAME: core:get_tm():repeat_real_callback(..., step, 'mtb_side_hint') and SetState per phase
            view.side.phase = (view.side.phase + 1) % glow.phases;
            for (const g of Object.values(view.side.glows)) {
                g.img.style.visibility = view.side.phase === 0 ? 'visible' : 'hidden';
                g.phases.forEach((ph, i) => ph.SetVisible(view.side.phase === i + 1));
            }
        }, glow.step_ms);
        for (const s of ['left', 'right']) {
            const b = make(sheet, SIDE + s, 'button_mark');
            size(b, ms.mark * scale, ms.mark * scale);
            at(b, ms.marks[s][0] * scale, ms.marks[s][1] * scale);
            view.side.marks[s] = b;
            // Malakai's portrait of the game, round, inside the selected ring
            const inset = ms.portrait_inset * scale;
            view.side.portraits[s] = image(b, 'portrait', ms.portrait, inset, inset, ms.mark * scale - 2 * inset, ms.mark * scale - 2 * inset);
        }
        // the demo window: shown on hover of the plan or a mark until the side is first changed (as the hint's glow), then the plain short tooltips
        const demo = demoTip(sheet, 'side_demo_tip', (ms.plan[0] + ms.plan[2] + 12) * scale, (ms.plan[1] + ms.plan[3]) * scale, {movie: 'side_demo', head: 'Борт Малакая',
            text: 'Выберите, с какого борта Малакай ведёт огонь. Сменить борт можно позже, между боями.'});
        view.side.tip = demo.tip;
        view.side.video = demo.video;
        for (const n of ['near', 'far', 'near_build', 'far_build']) {
            const q = place('malakai_' + n);
            view.side[n] = image(sheet, 'malakai_' + n, WEB_ART + 'malakai_' + n + '.png', q[0] * scale, q[1] * scale, q[2] * scale, q[3] * scale);
        }
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
    // a stage with a tree of buildings (blueprint.json, tree; ?tree=demo the example) shows it instead of rows
    const treeMode = !!(blueprint.tree || (flags.tree === 'demo' && blueprint.tree_demo));
    // with the tree at the game's size (slots of 74, 106 from one to the next) the column is tight: the tree starts right under the caption and the note
    // at the foot takes only its three lines
    const rows_top = 80, row_gap = 4, foot_h = treeMode ? 56 : 82;
    const row_h = Math.min(92, Math.floor((scheme_h - rows_top - foot_h - row_gap * (MAX_ROWS - 1) - 8) / MAX_ROWS));
    view.detail_top = rows_top;
    if (treeMode) {
        view.detail_top = rows_top - 8 + makeTree(column, view, M, blueprint, flags, 14, rows_top - 8, column_w - 28) + 6;
        view.selName = text(column, 'sel_name', 'text_head', 14, 0, column_w - 28, 26, '');
        view.selMeta = text(column, 'sel_meta', 'text_line', 14, 0, column_w - 28, 20, '');
    } else {
        for (let i = 0; i < MAX_ROWS; i++) view.rows.push(makeRow(column, i + 1, 8, rows_top + i * (row_h + row_gap), column_w - 16, row_h));
    }
    // details of the selected level: the game's short description and its green lines
    view.detail = text(column, 'detail', 'text_body', 14, 0, column_w - 28, 44, '');
    view.lines = text(column, 'lines', 'text_green', 14, 0, column_w - 28, 80, '');
    // commands
    // the three commands in one row at the foot, so the tree and the details above have the room
    const button_w = (column_w - 28 - 16) / 3, button_h = 42;
    const buttons_y = scheme_h - foot_h - button_h - 30;
    view.order = makeButton(column, ORDER, 14, buttons_y, button_w, button_h, 'Заказать');
    view.cancel = makeButton(column, CANCEL, 14 + button_w + 8, buttons_y, button_w, button_h, 'Отменить');
    view.demolish = makeButton(column, DEMOLISH, 14 + 2 * (button_w + 8), buttons_y, button_w, button_h, 'Снести');
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

// The demo window, one component for every place that shows a clip of the game (Malakai's side, a crew aboard): a dark backing (the panel's backdrop
// picture), the video, a brass head and light text with even margins, the panel's frame edge over it all. x: its left, bottom: its lower edge.
// The clip is web/art/<movie>.webm or .mp4, taken when the file is there; until then a placeholder.
// In the game: a frame layout with a movie component (the spell browser's MoviePlayer callback, its loop property).
// The small unit card beside a building's slot in the game's building browser (ui/templates/building_frame.twui.xml, units_list > unit_list >
// template_unit_entry_parent > unit_context): 23 x 50, the unit's picture (unit_card_ph in the template) squeezed into it and unit_card_build_frame.png
// over it at the same size. Nothing is added round it. The crew aboard has the game's frame in the crew group's colour instead of the game's red
// (build/web/game/ui/tww3_mtb/unit_card_build_frame_<colour>.png, tools/web_export.py), as the game itself recolours this frame (state active_red).
// ?aboard=outline: the other variant, the game's red frame with a thin line of the colour over it (web/art/aboard_outline_<colour>.png).
// The game's hover state enlarges the card to 30 x 65; the page only brightens it.
const CARD_W = 23, CARD_H = 50, CARD_OVERLAP = 10;
function slotUnitCard(parent, id, x, y, uc, colour, outline) {
    const card = image(parent, id, uc.picture, x, y, CARD_W, CARD_H);
    if (outline) {
        image(card, 'frame', 'ui/skins/default/unit_card_build_frame.png', 0, 0, CARD_W, CARD_H);
        image(card, 'aboard', WEB_ART + `aboard_outline_${colour}.png`, 0, 0, CARD_W, CARD_H);
    } else image(card, 'frame', `ui/skins/tww3_mtb/unit_card_build_frame_${colour}.png`, 0, 0, CARD_W, CARD_H);
    card.SetHoverBrighten(0.25);
    return card;
}

function demoTip(parent, id, x, bottom, spec) {
    const tw = 300, pad = 14, vw = tw - 2 * pad, vh = Math.round(vw * 9 / 16), th = pad + vh + 12 + 24 + 44 + pad;
    const tip = image(parent, id, LAYOUTS + 'backdrop.png', x, bottom - th, tw, th);
    const video = make(tip, 'video', 'movie');
    size(video, vw, vh);
    at(video, pad, pad);
    video.SetMovie(['.webm', '.mp4'].map(ext => '/art/' + spec.movie + ext), 'Здесь будет видео из игры');
    text(tip, 'tip_head', 'text_head', pad, pad + vh + 10, vw, 24, spec.head);
    text(tip, 'tip_text', 'text_body', pad, pad + vh + 36, vw, 44, spec.text);
    const edge = make(tip, 'tip_edge', 'frame_edge');
    size(edge, tw, th);
    at(edge, 0, 0);
    tip.SetVisible(false);
    return {tip, video, w: tw, h: th};
}

// ---------------- the tree of buildings: square nodes joined by brass lines, laid out from the requirements ----------------
// Tiers by depth (the longest way from a node with no requirement), the order inside a tier by the mean place of the nodes it needs (one pass, enough
// for a small tree), every tier spread evenly across the width. direction "down": the first buildings on top, what needs them below; "up": the other way.
// Lines run square: from a node to halfway, across, on to the other node; lines that meet share their halfway.
// The game's numbers (ui/campaign ui/building_browser.twui.xml): a slot of the tree is 74 x 74 and the arrow between two slots 32 (TreeCallback, padding_y;
// the template's own comment: "106 is the sum of the height of a tree slot (74), plus the height of an arrow (32)"). Nothing here is scaled.
const NODE = 74, TIER_GAP = 106, LINE = 3;
// columns of the tree when it has side branches: the trunk right of the middle, a left branch, a right branch
const COLUMN = {trunk: 0.62, left: 0.2, right: 0.86};
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
    if (nodes.some(n => n.branch)) {        // a trunk and side branches: each node in its column (several in one row of a column are spread around it)
        const cols = {};
        for (const n of nodes) {
            const col = n.branch ? n.branch.side : 'trunk';
            const key = col + ':' + tier[n.key];
            (cols[key] ||= []).push(n.key);
        }
        for (const [key, keys] of Object.entries(cols)) {
            const c = COLUMN[key.split(':')[0]];
            keys.forEach((k, i) => { place[k] = c + (i - (keys.length - 1) / 2) * 0.18; });
        }
        return {tier, tiers, place};
    }
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
    const branchOf = {};
    for (const [name, br] of Object.entries((blueprint.tree && blueprint.tree.branches) || {})) for (const k of br.nodes) branchOf[M.prefix + k] = {name, ...br};
    return keys.map(key => {
        const row = M.level(key);
        const chain = M.chain(row.chain);
        const below = chain && chain.levels.find(l => l.level === row.level - 1);
        const needs = [...(below ? [below.key] : []), ...row.requires, ...(M.extra_requires[key] || [])].filter(k => keys.includes(k));
        return {key, name: row.name, icon: row.icon ? 'ui/buildings/icons/tww3_mtb_' + row.icon : null, needs, branch: branchOf[key] || null};
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
    const line = (x0, y0, x1, y1, colour) => {
        const c = image(parent, `tree_line_${seg++}`, WEB_ART + (colour ? `tree_line_${colour}.png` : 'tree_line.png'), Math.min(x0, x1) - LINE / 2, Math.min(y0, y1) - LINE / 2,
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
            const colour = n.branch && n.branch.colour;       // a line into a branch's node has the branch's colour
            line(ax, ay, ax, mid, colour); line(ax, mid, bx, mid, colour); line(bx, mid, bx, by, colour);
        }
    }
    // A node is the game's own building slot (ui/templates/building_frame.twui.xml, square_building_button): the parchment tile building_frame.png,
    // the icon over it, a frame for built / selected / hover, the clock-wipe of construction, the turns banner, and under it the cost banner
    // (building_cost: icon_banner_bg, icon_treasury, and red_text_banner_shadow behind when the gold is short).
    const D = 'ui/skins/default/';
    view.tree = nodes.map((n, i) => {
        const x = pos[n.key].x, y = pos[n.key].y;
        const b = image(parent, TREE + i, D + 'building_frame.png', x, y, NODE, NODE);
        b.SetInteractive(true);
        const v = {node: n, button: b};
        v.icon = image(b, 'icon', n.icon || D + 'icon_check.png', 0, 0, NODE, NODE);
        // a branch's node: its colour's frame, always shown (the slot's states still grey or dim the whole node); the trunk: the game's built frame
        v.plain = image(b, 'plain', n.branch ? WEB_ART + `branch_frame_${n.branch.colour}.png` : D + 'building_frame_plain.png', 0, 0, NODE, NODE);
        v.branch = n.branch;
        // selection: the game's orange frame on the trunk; on a branch the branch's own colour, lighter, with a bright rim (the colour stays)
        v.frameSelected = image(b, 'selected', n.branch ? WEB_ART + `branch_frame_${n.branch.colour}_selected.png` : D + 'building_frame_selected.png', 0, 0, NODE, NODE);
        v.constructing = image(b, 'constructing', D + 'constructing_1.png', 6, 6, NODE - 12, NODE - 12);
        v.constructing.SetImageColour(255, 255, 255, 0x64);
        v.check = image(b, 'check', D + 'icon_check_green.png', 44, 48, 31, 28);      // the template's built state: 31 x 28 at 44, 48, the lower right corner
        v.padlock = image(b, 'padlock', D + 'padlock.png', NODE - 24, 2, 20, 25);
        // hover as the template: an unselected slot gets building_frame_hover (the default skin's, red; the dwarfs have no skin of their own for it)
        // over it, 90 px against the slot's 74, and brighten 0.40; the selected slot gets building_frame_selected_hover instead (refreshTree swaps them)
        v.hover = image(b, 'hover', D + 'building_frame_hover.png', -NODE * 8 / 74, -NODE * 8 / 74, NODE * 90 / 74, NODE * 90 / 74);
        v.hoverSelected = image(b, 'hover_selected', D + 'building_frame_selected_hover.png', 0, 0, NODE, NODE);
        v.hoverSelected.SetVisible(false);
        b.SetHoverChild(v.hover);
        b.SetHoverBrighten(0.4);
        v.turnsBanner = image(b, 'turns_banner', D + 'turns_banner_queued.png', -6, NODE - 16, NODE + 12, 20);
        v.turns = text(b, 'turns', 'text_line', 20, NODE - 16, NODE - 14, 20, '');
        // the cost under the slot
        // (the game shows the cost on hover, right of the slot: cost_list at 21, 26; under the slot it is the page's own place, kept; 62 wide so that
        // the unit card of the slot below, which starts 68 from the slot's left, stays clear of it)
        v.cost = image(parent, TREE + 'cost_' + i, D + 'icon_banner_bg.png', x + 3, y + NODE + 2, 62, 18);
        v.costRed = image(v.cost, 'red', D + 'red_text_banner_shadow.png', 0, 0, 62, 18);
        image(v.cost, 'coins', D + 'icon_treasury.png', 4, 1, 16, 16);
        v.costText = text(v.cost, 'value', 'text_line', 22, -1, 40, 20, '');
        return v;
    });
    // the construction's clock-wipe, frame by frame (constructing_1 .. 12), as the game animates it
    view.wipe = 1;
    setInterval(() => {
        view.wipe = view.wipe % 12 + 1;
        for (const v of view.tree || []) if (v.constructing.Visible()) v.constructing.SetImagePath(D + `constructing_${view.wipe}.png`, 0);
    }, 120);
    // The crew a building opens (blueprint.json, crew_cards): small unit cards beside its slot, exactly as the game's building browser places the units a
    // building unlocks (building_frame.twui.xml, units_list: docked to the slot's top right corner, dock_offset 17, -22, anchored by its own top right
    // corner): the row of cards ends 17 right of the slot and starts 22 above it; one card stands 68 from the slot's left, a second pushes the row left
    // by 13 (the entries overlap by 10). The row is a later sibling of the slot's button: over its frames and marks, and not greyed with it.
    // On hover the demo window, the same as Malakai's side: left of the slot, level with the card, clear of the slot, the cards and the other nodes.
    view.crew = [];
    const specs = ((!flags.tree && blueprint.crew_cards) || []).map(spec => {
        const group = view.data.groups[spec.group], option = group && group.options[spec.option];
        return {spec, group, option, uc: option && option.unit_card, v: view.tree.find(t => t.node.key === M.prefix + spec.building)};
    }).filter(c => c.uc && c.v);
    const frame = parent.parent;
    const placed = {};
    for (const {spec, group, option, uc, v} of specs) {
        const total = specs.filter(c => c.v === v).length, i = placed[v.node.key] = (placed[v.node.key] || 0) + 1;
        const row_w = CARD_W + (total - 1) * (CARD_W - CARD_OVERLAP);
        const cx = v.button.x + NODE + 17 - row_w + (i - 1) * (CARD_W - CARD_OVERLAP), cy = v.button.y - 22;
        const card = slotUnitCard(parent, 'mtb_crew_card_' + spec.option, cx, cy, uc, group.card_frame || 'gold', flags.aboard === 'outline');
        const centre = parent.y + cy + CARD_H / 2, tip_h = 261;
        const bottom = Math.min(frame.Height() - 12, Math.max(70 + tip_h, centre + tip_h / 2));
        const demo = demoTip(frame, 'crew_demo_tip_' + spec.option, parent.x + v.button.x - 8 - 300, bottom, {movie: spec.movie, head: spec.head || option.name, text: spec.text || ''});
        card.SetHoverChild(demo.tip);
        view.crew.push({card, tip: demo.tip, building: v.node.key});
    }
    view.selected = nodes.length ? nodes[0].key : null;
    return height + 20;      // the cost banner under the lowest row
}

function nodeStatus(M, n) {
    return n.demo ? {state: 'demo'} : M.status(n.key);
}

// The states of the game's slot (square_building_button) as the page uses them:
//   built     full colour, building_frame_plain, the green check;
//   normal    can be ordered, or ordered: colour #FFFFFFB4 (a little see-through); the game also pulses it (glow_pulse_t0), not done here;
//   greyed    needs an earlier building: greyscale and #FFFFFF80 (half see-through);
//   short of gold: the slot as normal, the cost banner red (building_cost, state red). Which slot state the horde's tree takes then is to check in the game.
function refreshTree(view, M) {
    for (const v of view.tree) {
        const st = nodeStatus(M, v.node);
        const poor = st.state === 'locked' && st.poor;
        const greyed = (st.state === 'locked' && !poor) || st.state === 'unknown';
        const built = st.state === 'built', building = st.state === 'building';
        if (built) v.button.SetImageColour(255, 255, 255, 255);
        else if (greyed) v.button.SetImageColour(255, 255, 255, 0x80);
        else v.button.SetImageColour(255, 255, 255, 0xB4);
        v.button.ShaderTechniqueSet(greyed ? 'set_greyscale_t0' : 'normal_t0');
        // selected: building_frame_selected (orange) in place of the built frame, as the template's selected state; the green check is kept here
        // (the template's selected state has none: in the game's horde tree nothing stays selected, a click orders)
        const selected = view.selected === v.node.key;
        v.frameSelected.SetVisible(selected);
        v.plain.SetVisible((built || !!v.branch) && !(selected && !v.branch));
        v.hover.SetVisible(false); v.hoverSelected.SetVisible(false);
        v.button.SetHoverChild(selected ? v.hoverSelected : v.hover);
        v.check.SetVisible(built);
        v.padlock.SetVisible(greyed);
        v.constructing.SetVisible(building);
        v.turnsBanner.SetVisible(building);
        v.turns.SetVisible(building);
        v.turns.SetStateText(building ? String(st.turns) : '');
        const row = !v.node.demo && M.level(v.node.key);
        v.cost.SetVisible(!!row && !built && !building);
        v.costRed.SetVisible(poor);
        // the game's red state adds a dark shadow behind the number (red_text_banner_shadow.png); the red of the number itself is the page's guess, to check in the game
        v.costText.SetStateText(row ? (poor ? `[[col:red]]${row.cost}[[/col]]` : String(row.cost)) : '');
        const state = poor ? `не хватает золота: нужно ${row.cost}` : {built: 'построено', building: `строится, ${turnsText(st.turns || 0)}`, open: 'можно заказать', locked: st.why || 'недоступно', demo: 'пример, не из данных'}[st.state] || '';
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
// The mod's descriptions hold Russian, an empty line, then English: the panel shows the first part.
function firstPart(text) { return (text || '').split('\n\n')[0]; }

function effectLines(row, card) {
    if (!card) return row.lines;
    // an effect the mod switches off (its row set to 0) is not shown: the mod cannot take a row of the game out of its table
    return card.effects.filter(e => !e.hidden && !e.off).map(e => e.text || `${e.effect} = ${e.value}`);
}

// The green lines with what the level opens in the crew panel (the overview's card, opens): hire and upkeep from the mod's data, as the overview writes them.
// The money goes on the green line that names the option (the mod's line "Открывает в экипаже: ..."), else on a line of its own.
// Not the groups the panel does not list (the pub: buildings set it) and not the bare mounts, whose green line says it already.
function detailLines(row, card) {
    const lines = [...effectLines(row, card)];
    for (const o of (card && card.opens) || []) {
        if (o.panel === false || o.mount) continue;
        const money = [o.hire ? `найм ${o.hire}` : '', o.upkeep ? `содержание ${o.upkeep}/ход` : ''].filter(Boolean).join(', ');
        const i = lines.findIndex(l => l.includes(o.name));
        if (i >= 0) { if (money) lines[i] += ` [[col:yellow]](${money})[[/col]]`; }
        else lines.push(`[[col:yellow]]${o.group_name}: ${o.name}[[/col]]${money ? ` (${money})` : ''}`);
    }
    return lines;
}

function tooltip(row, status, card) {
    const lines = [`[[col:yellow]]${row.name}[[/col]]`];
    if (card && card.game_name && card.game_name !== row.name) lines.push(`В игре: «${card.game_name}». Название — мода`);
    const text = firstPart(row.text || (card && card.text));
    if (text) lines.push(text);
    lines.push(`Цена: ${row.cost} золота, срок: ${turnsText(row.turns)}`);
    for (const l of detailLines(row, card)) lines.push(`[[col:green]]${l}[[/col]]`);
    if (status.why) lines.push(status.why);
    return lines.join('\n');
}

function refresh(view, M) {
    view.gold.SetStateText(String(M.game.treasury()));
    if (view.sheets) {
        const rule = view.sheets.find(r => !r.part || M.stage(r.part) === r.stage);
        view.sheet.SetImagePath(LAYOUTS + rule.sheet + '.png', 0);
    }
    for (const [part, layers] of Object.entries(view.layers)) {
        const stage = M.stage(part);
        for (const s of ['pencil', 'build', 'ink']) if (layers[s]) layers[s].SetVisible(s === stage);
        const st = stage === 'build' ? M.status(M.prefix + M.parts[part].building) : {};
        if (stage === 'build' && !layers.build) layers.turns.SetVisible(false);
        layers.turns.SetVisible(stage === 'build');
        layers.turns.SetStateText(st.state === 'building' ? turnsText(st.turns) : '');
    }
    if (view.tree) refreshTree(view, M);
    if (view.side) {
        // the plan shows from the order of the barge on; while the barge is only ordered it has no sides yet: the whole plan dim as the game's greyed slot
        // (greyscale, #FFFFFF80), the marks take no click, no glow, no figure on the hatched barge. Once it stands: the plan as usual.
        const bargeStage = view.side.show_when ? M.stage(view.side.show_when) : 'ink';
        const shown = bargeStage === 'ink' || bargeStage === 'build';
        const ready = bargeStage === 'ink';
        view.side.ready = ready;
        const side = M.malakai_side();
        const dim = c => { c.SetImageColour(255, 255, 255, ready ? 255 : 0x80); c.ShaderTechniqueSet(ready ? 'normal_t0' : 'set_greyscale_t0'); };
        view.side.plan.SetVisible(shown);
        dim(view.side.plan);
        for (const [s, b] of Object.entries(view.side.marks)) {
            b.SetVisible(shown);
            b.SetState(!ready ? 'inactive' : s === side ? 'selected' : 'active');
            dim(b);
            const name = s === 'left' ? 'левом' : 'правом';
            b.SetTooltipText(!ready ? 'Борт можно выбрать, когда корабль будет построен' : M.side_hint() ? 'Выберите борт для Малакая'
                : s === side ? `Малакай на ${name} борту: стреляет стрелком` : `Пустой борт. Щёлкните, чтобы поставить Малакая на ${s === 'left' ? 'левый' : 'правый'} борт`, true);
        }
        // the drawing shows the left side (bow to the left): there he is in ink; on the right side he stands behind it, in pencil
        for (const s of ['left', 'right']) view.side.portraits[s].SetVisible(shown && s === side);
        const hint = ready && M.side_hint();
        // the demo window opens on hover of the plan or a mark while the hint is on; the marks' own tooltips stay quiet then
        const demo = hint ? view.side.tip : null;
        view.side.plan.SetHoverChild(demo);
        for (const b of Object.values(view.side.marks)) {
            b.SetHoverChild(demo);
            if (demo) b.SetTooltipText('', true);
        }
        if (!demo) view.side.tip.SetVisible(false);
        // only the empty side glows: the place Malakai can be moved to
        for (const [s, g] of Object.entries(view.side.glows)) g.SetVisible(hint && s !== side);
        view.side.near.SetVisible(ready && side === 'left');
        view.side.far.SetVisible(ready && side === 'right');
        view.side.near_build.SetVisible(false);
        view.side.far_build.SetVisible(false);
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
        const price = s0.poor ? `[[col:red]]Цена: ${sel.cost} золота[[/col]]` : `Цена: ${sel.cost} золота`;
        view.selMeta.SetStateText(`${price} · ${turnsText(sel.turns)} · ${state}`);
    }
    view.detail.SetStateText(firstPart(sel.text || (card && card.text)));
    // the green lines and what the level opens in the crew panel: under the description as tall as its text (uic:TextDimensions), down to the commands
    const lines_y = view.tree ? y + Math.max(1, view.detail.TextDimensions()[2]) * 15 + 4 : y + 46;
    at(view.lines, 14, lines_y);
    size(view.lines, view.lines.Width(), Math.max(80, view.order.button.y - lines_y - 4));
    view.lines.SetStateText(detailLines(sel, card).join('\n'));
    const st = M.status(sel.key);
    view.order.button.SetState(st.state === 'open' ? 'active' : 'inactive');
    view.order.button.SetTooltipText(st.state === 'open' ? `Заказать «${sel.name}»: ${sel.cost} золота, ${turnsText(sel.turns)}` : (st.why || (st.state === 'building' ? 'Уже строится' : 'Уже построено')), true);
    view.cancel.button.SetState(st.state === 'building' ? 'active' : 'inactive');
    view.cancel.button.SetTooltipText(st.state === 'building' ? `Отменить стройку, ${sel.cost} золота вернутся` : 'Нечего отменять', true);
    const dem = M.can_demolish(sel.key);
    view.demolish.button.SetState(dem.ok ? 'active' : 'inactive');
    view.demolish.button.SetTooltipText(dem.ok ? 'Снести постройку. Золото не возвращается: возврата при сносе в данных нет (допущение). В игре корпус снести нельзя, здесь можно для проверки; '
        + 'снос уровня оставляет уровень ниже (в игре уходит вся постройка)' : dem.why, true);
    view.message.SetStateText(M.message() || '');
}

function click(view, M, c) {
    const id = c.Id();
    if (id.startsWith(SIDE)) {
        if (view.side && view.side.ready) M.set_malakai_side(id.slice(SIDE.length));      // no sides while the barge is only ordered
    } else if (id.startsWith(TREE)) {
        const v = view.tree[Number(id.slice(TREE.length))];
        if (v) view.selected = v.node.key;
        if (view.onSelect) view.onSelect();
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
