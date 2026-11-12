// The airship screen, "Корабль" tab: the drawing on the left with the stage of each part, the levels of a chain on the right, order and cancel.
// Built as build() of src/tww3_mtb_crew_ui.lua: the same root, the same sizes and offsets, so the numbers carry over to the game.
// Reads only the module (web/js/barge_buildings.js); a click calls it, refresh() reads it back.

import {turnsText} from './barge_buildings.js';
import {linkSegments, slotsBlock, GRID} from './tree_model.mjs';
import * as FX from './effects_model.mjs';
import {crewSources} from './crew_model.mjs';

const LAYOUTS = 'ui/tww3_mtb/';
const WEB_ART = LAYOUTS + 'web/';       // the stage layers; in the game they would be ui/tww3_mtb/<name>.png like the others
const ROW = 'mtb_ship_row_', ORDER = 'mtb_ship_order', CANCEL = 'mtb_ship_cancel', DEMOLISH = 'mtb_ship_demolish';
const MAX_ROWS = 6;
const SIDE = 'mtb_side_';
const CREW_AREA = 'mtb_crew_area_', CREW_PICK = 'mtb_crew_card_pick_', CREW_CLOSE = 'mtb_crew_close_';
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
    sheet.SetInteractive(true);         // a click on the bare drawing closes an open choice (click())
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
    // The places of the crew groups on the drawing (blueprint.json, crew_areas: the riflemen, the guns, the bombs, the nests), one component each,
    // made by makeCrewArea below. Created after the details' layers, so a crew stands over the detail it uses (the port, the rings, the hatches).
    view.crewAreas = {};
    for (const spec of blueprint.crew_areas || []) {
        const a = art.crew_areas && art.crew_areas[spec.group];
        if (a && data.groups[spec.group]) view.crewAreas[spec.group] = makeCrewArea(view, M, data, art, blueprint, flags, sheet, frame, scale, scheme_w, scheme_h, place, spec, a);
    }
    view.crewArea = view.crewAreas.rifles || null;
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
    const treeMode = !!(blueprint.tree || data.tree_rows || (flags.tree === 'demo' && blueprint.tree_demo));
    // with the tree at the game's size (slots of 74, 106 from one to the next) the column is tight: the tree starts right under the caption and the note
    // at the foot takes only its three lines
    const rows_top = 80, row_gap = 4, foot_h = treeMode ? 56 : 82;
    const row_h = Math.min(92, Math.floor((scheme_h - rows_top - foot_h - row_gap * (MAX_ROWS - 1) - 8) / MAX_ROWS));
    view.detail_top = rows_top;
    if (treeMode && data.tree_rows) {
        // the tree of the constructor's file (web/data/tree_design.json): its own places, in a window of the column that pans when the tree is larger
        const tree_bottom = scheme_h - foot_h - 42 - 30 - 56 - 6;
        // opened, the tree's window spans the panel from the drawing's left edge to the column's, between the column's head and its commands
        const wide = {x: sx - cx, y: 40, w: cx - sx + column_w - 14, h: tree_bottom - 40};
        view.detail_top = rows_top - 8 + makeFileTree(column, view, M, blueprint, flags, 14, rows_top - 8, column_w - 28, tree_bottom - (rows_top - 8), wide) + 6;
        view.selName = text(column, 'sel_name', 'text_head', 14, 0, column_w - 28, 26, '');
        view.selMeta = text(column, 'sel_meta', 'text_line', 14, 0, column_w - 28, 20, '');
    } else if (treeMode) {
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
    else if (data.tree_rows) { /* the file's tree wrote its own line (makeFileTree) */ }
    else if (blueprint.caption) view.about.SetStateText(blueprint.caption);
    else if (view.levels.length) view.about.SetStateText(blueprint.first_only && !flags.full ? `Первая постройка линейки пушек: «${view.levels[0].name}».` : 'Линейка пушек: порты, палуба, арсенал, органы.');

    view.root = backdrop;
    view.column = column;
    view.frame = frame;
    view.scale = scale;
    return {view, refresh: () => refresh(view, M), click: (c) => click(view, M, c)};
}

// A crew group's place on the drawing: part of the drawing, not a button, and seen as a place to click at the scale the page really has on a screen
// (about 0.6; tools/web_art.py sizes its lines and the tag's text for 0.5). Nobody: light cut-outs of what would stand there in a dashed ink line (the
// riflemen's figures, the gun in the port, the bombs over the hatches; the nests have their lookouts instead); a crew: its kind in ink, a layer per
// kind; a hire on its way: the kind sketched in sepia where nobody stands. A tag on leaders names the group with a sign in a ring: a plus while the
// place is empty, two arrows when a crew stands, an hourglass and the turns while one is hired. Until the group's first choice the tag has a warm
// pulse, the same as Malakai's empty side. Under the mouse: dashed frames round the places in soft ink and the tag's slip lighter; the whole box takes
// the click, the gaps too. The place is there while a building that makes it stands (crew_model: M.crew_place).
// spec: blueprint.json crew_areas (group, head, kind_name, stats_head, words, hides_part); a: web/art/layers.json crew_areas (area, glow, step_ms).
function makeCrewArea(view, M, data, art, blueprint, flags, sheet, frame, scale, scheme_w, scheme_h, place, spec, a) {
    const g = spec.group, group = data.groups[g], cbox = a.area, ax = cbox[0] * scale, ay = cbox[1] * scale;
    const area = make(sheet, CREW_AREA + g, 'hit_area');
    size(area, cbox[2] * scale, cbox[3] * scale);
    at(area, ax, ay);
    area.SetInteractive(true);
    const has = name => !!art.places[name];
    const lay = name => { const q = place(name); const c = image(area, name, WEB_ART + name + '.png', q[0] * scale - ax, q[1] * scale - ay, q[2] * scale, q[3] * scale); c.SetPassive(); return c; };
    const crew = {spec, area, group: g, layers: {}, open: false};
    // the pulse first, under the tag: one picture a phase, switched by a timer (GAME: SetState by core:get_tm():repeat_real_callback, as the side's)
    const gl = a.glow, prefix = gl.prefix || 'crew_glow';
    crew.glow = image(area, 'crew_glow', WEB_ART + `${prefix}_0.png`, gl.box[0] * scale - ax, gl.box[1] * scale - ay, gl.box[2] * scale, gl.box[3] * scale);
    crew.glow.SetPassive();
    crew.glow.phases = [];
    for (let i = 1; i < gl.phases; i++) {
        const ph = image(crew.glow, 'phase_' + i, WEB_ART + `${prefix}_${i}.png`, 0, 0, gl.box[2] * scale, gl.box[3] * scale);
        ph.SetVisible(false);
        crew.glow.phases.push(ph);
    }
    crew.glow.img.style.visibility = 'visible';
    crew.phase = 0;
    setInterval(() => {
        crew.phase = (crew.phase + 1) % gl.phases;
        crew.glow.img.style.visibility = crew.phase === 0 ? 'visible' : 'hidden';
        crew.glow.phases.forEach((ph, i) => ph.SetVisible(crew.phase === i + 1));
    }, a.step_ms || 110);
    crew.empty = has(`crew_${g}_empty`) ? lay(`crew_${g}_empty`) : null;
    crew.sketches = {};
    for (const key of Object.keys(group.options)) if (has(`crew_${g}_${key}_sketch`)) crew.sketches[key] = lay(`crew_${g}_${key}_sketch`);
    crew.tags = {plus: lay(`crew_${g}_tag_plus`), swap: lay(`crew_${g}_tag_swap`), wait: lay(`crew_${g}_tag_wait`)};
    crew.hover = make(area, 'hover', 'hover_holder');
    size(crew.hover, cbox[2] * scale, cbox[3] * scale);
    crew.hover.SetPassive();
    const inHover = name => { const q = place(name); return image(crew.hover, name, WEB_ART + name + '.png', q[0] * scale - ax, q[1] * scale - ay, q[2] * scale, q[3] * scale); };
    inHover(`crew_${g}_hover`);
    crew.hoverTags = {plus: inHover(`crew_${g}_tag_plus_hover`), swap: inHover(`crew_${g}_tag_swap_hover`), wait: inHover(`crew_${g}_tag_wait_hover`)};
    area.SetHoverChild(crew.hover);
    const emptyKey = group.mount || group.start;
    for (const key of Object.keys(group.options)) if (key !== emptyKey && has(`crew_${g}_${key}`)) crew.layers[key] = lay(`crew_${g}_${key}`);
    // The choice: a window of the same family as the demo window of Malakai's side (the panel's dark backing, a brass head, the frame's edge),
    // under the place when there is room, over it otherwise. Every kind the buildings can open, as the army panel's unit card in the crew's colour;
    // a kind not opened yet is grey under a padlock, as the game shows a unit that cannot be recruited yet, and its panel names the building.
    const options = M.crew_options(g);
    // at least as wide as the head and the line of the upkeep: a group of two kinds has the same window, its cards from the left
    const pad = 26, slot_w = 106, pw = Math.max(pad * 2 + slot_w * options.length, 440), ph = pad + 28 + 4 + UNIT_H + 4 + 42 + 24 + 26;
    const below = ay + cbox[3] * scale + 14, above = ay - 14 - ph;
    const py = below + ph <= scheme_h - 6 ? below : above >= 6 ? above : Math.max(6, scheme_h - ph - 6);
    const pick = image(sheet, 'mtb_crew_pick_' + g, LAYOUTS + 'backdrop.png', Math.max(6, Math.min(ax, scheme_w - pw - 12)), py, pw, ph);
    pick.SetInteractive(true);      // a click on the window itself does nothing and does not reach the drawing
    pick.SetLayer('click');
    crew.pick = pick;
    crew.head = text(pick, 'pick_head', 'text_head', pad, pad - 4, pw - 2 * pad - 34, 28, spec.head || group.name);
    const cross = image(pick, CREW_CLOSE + g, 'ui/skins/default/icon_cross.png', pw - pad - 24, pad - 2, 22, 22);
    cross.SetInteractive(true);
    // A slot is the whole column of a kind (the card and its caption), one beside the other with no gap: the mouse goes from kind to kind without
    // leaving them, so the unit's panel beside the choice does not blink. Everything a card has to say is on the card, in the game's own marks
    // (ui/common ui/land_unit_card.twui.xml), and only its name under it:
    //   a kind one can hire   the recruitment card: the cost on the plate at the top, red when the treasury cannot pay it
    //   the kind in hire      the card's queued state: the picture and the frame at 100 of 255, the banner with the hourglass and the turns
    //   the kind that stands  the army panel's card of a unit one has: the men over the green bar, the frame of the selected card
    //   a kind not opened     the locked state: grey, the padlock
    const slot_y = pad + 28 + 4, slot_h = UNIT_H + 4 + 42;
    const clips = Object.fromEntries((blueprint.crew_cards || []).filter(c => c.group === g).map(c => [c.option, c]));
    crew.slots = options.map((o, i) => {
        const hit = make(pick, CREW_PICK + g + ':' + o.key, 'hit_area');
        size(hit, slot_w, slot_h);
        at(hit, pad + i * slot_w, slot_y);
        hit.SetInteractive(true);
        hit.SetHoverBrighten(0.15);
        const cx = (slot_w - UNIT_W) / 2;
        const card = o.unit_card ? unitCard(hit, 'card', cx, 0, o.unit_card, group.card_frame || 'gold') : image(hit, 'card', LAYOUTS + 'card_empty.png', cx, 0, UNIT_W, UNIT_H);
        const slot = {key: o.key, hit, card};
        slot.selected = image(card, 'selected', 'ui/skins/default/unit_card_selected.png', 0, 0, UNIT_W, UNIT_H);
        slot.padlock = image(card, 'padlock', 'ui/skins/default/padlock.png', (UNIT_W - 26) / 2, 46, 26, 33);
        // the game's mark of a unit being recruited (land_unit_card.twui.xml, campaign > Turns: 70 x 34 at -5, 48, the banner with the hourglass)
        slot.turnsBanner = make(card, 'Turns', 'turns_banner');
        size(slot.turnsBanner, 70, 34);
        at(slot.turnsBanner, -5, 48);
        slot.turns = text(slot.turnsBanner, 'turns', 'text_card_turns', 25, 1, 30, 34, '1');
        slot.name = text(hit, 'name', 'text_caption', 2, UNIT_H + 4, slot_w - 4, 40, '');
        for (const c of [card, slot.name]) c.SetPassive();
        if (!o.empty) {
            const clip = clips[o.key] || {};
            slot.info = unitInfo(frame, `crew_pick_info_${g}_${o.key}`, {option: o, group_data: group, movie: clip.movie || `${g}_${o.key}_demo`, text: clip.text || o.about || '', area: spec}, flags);
            slot.info.hook(hit);
        }
        return slot;
    });
    // the upkeep of the whole crew: its own line under the cards' captions, left, so it never meets the head however long either is
    crew.foot = text(pick, 'pick_foot', 'text_caption_left', pad, slot_y + slot_h + 2, pw - 2 * pad, 22, '');
    const edge = make(pick, 'pick_edge', 'frame_edge');
    size(edge, pw, ph);
    at(edge, 0, 0);
    pick.SetVisible(false);
    return crew;
}

// the crew's choice that is open now (one at a time), or null
function openArea(view) {
    return Object.values(view.crewAreas || {}).find(c => c.open) || null;
}

// The demo window, one component for every place that shows a clip of the game (Malakai's side, a crew aboard): a dark backing (the panel's backdrop
// picture), the video, a brass head and light text with even margins, the panel's frame edge over it all. x: its left, bottom: its lower edge.
// The clip is web/art/<movie>.webm or .mp4, taken when the file is there; until then a placeholder.
// In the game: a frame layout with a movie component (the spell browser's MoviePlayer callback, its loop property).
// A unit as the army panel shows it (ui/common ui/land_unit_card.twui.xml): 60 x 130, the unit's picture, the frame, the plate with the number of men
// over the bar (health_frame at 4, 3: 52 x 11), the half round with the unit's category (unit_cat_frame, the icon 22 x 22). The crew aboard has the
// game's frame in the crew group's colour, as the small card of the tree. uc: unit_card of build/web/data.json.
const UNIT_W = 60, UNIT_H = 130;
function unitCard(parent, id, x, y, uc, colour) {
    const D = 'ui/skins/default/';
    const card = image(parent, id, uc.picture, x, y, UNIT_W, UNIT_H);
    card.frame = image(card, 'frame', `ui/skins/tww3_mtb/unit_card_frame_plain_${colour}.png`, 0, 0, UNIT_W, UNIT_H);
    // the army panel's marks of a unit one has: the plate with the number of men over the green bar (health_frame at 4, 3)
    // health_frame 52 x 14 at 4, 3: health_back (unit_card_back.png 52 x 12), in it the bar 52 x 6 one down (bar_clip), and over the bar the number
    // of men (unit_strength_number 33 x 14 at 9, -1 of the frame; body_10)
    card.army = [image(card, 'health_back', D + 'unit_card_back.png', 4, 3, 52, 12), image(card, 'health_fill', D + 'bar_white.png', 4, 4, 52, 6),
                 text(card, 'unit_strength_number', 'text_card_number', 13, 2, 33, 14, String(uc.men))];
    card.army[1].SetImageColour(44, 140, 30, 255);
    // The recruitment's mark of a unit one can hire: the cost on its plate, in the place of the health frame. The game: recruitment_cost_background,
    // frame_text.png 38 x 16 at 11, 3 with margins 4, the number alone (RecruitmentCost, body_10, 2 down). Here, by the user's wish, the treasury's
    // coins stand before the number (icon_treasury.png, the icon the game puts before every price), so the plate is as wide as the health frame, 52.
    card.costPlate = make(card, 'recruitment_cost_background', 'cost_plate');
    size(card.costPlate, 52, 16);
    at(card.costPlate, 4, 3);
    image(card.costPlate, 'icon_treasury', D + 'icon_treasury.png', 3, 0, 16, 16);
    card.cost = text(card.costPlate, 'RecruitmentCost', 'text_card_cost', 21, 1, 30, 16, '');
    const rest = [image(card, 'unit_cat_frame', D + 'unit_card_semicircle.png', 3, 95, 55, 35), image(card, 'unit_category_icon', uc.category, 19, 106, 22, 22)];
    for (const c of [card.frame, ...card.army, card.costPlate, ...rest]) c.SetPassive();
    return card;
}

// The small unit card beside a building's slot in the game's building browser (ui/templates/building_frame.twui.xml, units_list > unit_list >
// template_unit_entry_parent > unit_context): 23 x 50, the unit's picture (unit_card_ph in the template) squeezed into it and unit_card_build_frame.png
// over it at the same size. Nothing is added round it. The crew aboard has the game's frame in the crew group's colour instead of the game's red
// (build/web/game/ui/tww3_mtb/unit_card_build_frame_<colour>.png, tools/web_export.py), as the game itself recolours this frame (state active_red).
// ?aboard=outline: the other variant, the game's red frame with a thin line of the colour over it (web/art/aboard_outline_<colour>.png).
// The game's hover state enlarges the card to 30 x 65; the page only brightens it.
const CARD_W = 23, CARD_H = 50, CARD_OVERLAP = 10;
function slotUnitCard(parent, id, x, y, uc, colour, outline) {
    const card = image(parent, id, uc.picture, x, y, CARD_W, CARD_H);
    if (colour === null) image(card, 'frame', 'ui/skins/default/unit_card_build_frame.png', 0, 0, CARD_W, CARD_H);      // an army unit: the game's own frame
    else if (outline) {
        image(card, 'frame', 'ui/skins/default/unit_card_build_frame.png', 0, 0, CARD_W, CARD_H);
        image(card, 'aboard', WEB_ART + `aboard_outline_${colour}.png`, 0, 0, CARD_W, CARD_H);
    } else image(card, 'frame', `ui/skins/tww3_mtb/unit_card_build_frame_${colour}.png`, 0, 0, CARD_W, CARD_H);
    card.SetHoverBrighten(0.25);
    return card;
}

// The game's building information window, shown while the mouse is over a node of the tree, as over any building of the game.
// Laid out after ui/campaign ui/building_information.twui.xml, 400 wide, every block as tall as its text (the template's lists size to content):
//   building_information_holder   tooltip_frame.png, margins 15
//   dy_title                      at 0, 1; 400 x 38; header_14 centred, text offsets 10 / 10 across, 12 above, 8 below
//   hbar                          separator_skull2.png 380 x 14 at 10, 33
//   dy_secondary_title            the chain's name: at 39, 30 tall; body_12 centred, 12 above, 2 below
//   description_window            body_12_italic centred, 14 / 14 across, 20 above, 16 below, at least 52 tall
//   effects_list                  building_info_generic_entry.twui.xml per effect: icon 24 x 24 at 10, 0 (effects.icon); text from 36 to 8 before the edge,
//                                 6 above, 8 below, at least 30 tall
//   building_info_recruitment_effects.twui.xml ("Unlocks recruitment of:"; here what the building opens in the crew): title row 24: icon 24 x 24 at 10, 0,
//                                 text at 38, 6 above; unit_entry 50 tall: unit_cat_holder_round.png 26 x 26 at 24, 4, the category icon 22 x 22 in it,
//                                 the name at 52, 11 above
//   bottom_padding                17
//   instruction_window            a window of its own under the first, overlapping it by 8 (the list's spacing 0, -8): tooltip_frame.png, margins 16
//                                 and 20; body_12, 13 / 10 across, 13 above, 10 below; the reason why the building cannot be built, red
// The game's window has no cost and no time: they stand by the slot (the cost banner; the turns in the panel's line of the selected building).
// The rows of effects and of the crew are made as many as a building has (none is ever dropped); a window that would be taller than the screen
// keeps every row and shortens its description, with "…" (the constructor warns of it before: tree_model.mjs, INFO).
const INFO_W = 400;
function makeInfoTip(parent, id) {
    const tip = make(parent, id, 'tooltip_frame');
    size(tip, INFO_W, 100);
    const t = {tip, w: INFO_W, effects: [], units: [], id};
    t.title = text(tip, 'dy_title', 'text_info_title', 10, 1 + 2, INFO_W - 20, 38, '');      // 12 above and 8 below the text: its middle 2 under the box's
    t.hbar = make(tip, 'hbar', 'separator_skull');
    size(t.hbar, 380, 14);
    at(t.hbar, 10, 33);
    t.chain = text(tip, 'dy_secondary_title', 'text_info_centre', 8, 39 + 12 - 4, INFO_W - 16, 22, '');   // 30 tall with 12 above and 2 below: 16 left for a line of 22, it sits 4 higher
    t.description = text(tip, 'description_window', 'text_info_italic', 14, 0, INFO_W - 28, 16, '');
    t.opensIcon = image(tip, 'effect_icon', 'ui/skins/default/replenishement_positive.png', 10, 0, 24, 24);
    t.opensTitle = text(tip, 'tx_enables', 'text_info', 38, 0, INFO_W - 38 - 10, 16, 'Открывает в экипаже:');
    // the game's own block of a building that unlocks units (building_info_recruitment_effects.twui.xml): «Открывает найм:» and the units
    t.armyIcon = image(tip, 'army_effect_icon', 'ui/skins/default/replenishement_positive.png', 10, 0, 24, 24);
    t.armyTitle = text(tip, 'tx_enables_army', 'text_info', 38, 0, INFO_W - 38 - 10, 16, 'Открывает найм:');
    t.army = [];
    t.instruction = make(parent, id + '_instruction', 'tooltip_instruction');
    t.reason = text(t.instruction, 'reason', 'text_info', 13, 13, INFO_W - 23, 16, '');
    tip.SetLayer('hover');
    t.instruction.SetLayer('hover');
    tip.SetVisible(false);
    t.instruction.SetVisible(false);
    return t;
}
function infoRows(t, effects, units, army = 0) {
    const D = 'ui/skins/default/';
    while (t.army.length < army) {
        const i = t.army.length;
        const holder = image(t.tip, 'army_cat_frame_' + i, D + 'unit_cat_holder_round.png', 24, 0, 26, 26);
        t.army.push({holder, icon: image(holder, 'unit_category_icon', D + 'replenishement_positive.png', 2, 2, 22, 22), name: text(t.tip, 'army_name_' + i, 'text_info', 52, 0, INFO_W - 52 - 10, 16, '')});
    }
    while (t.effects.length < effects) {
        const i = t.effects.length;
        t.effects.push({icon: image(t.tip, 'effect_icon_' + i, D + 'replenishement_positive.png', 10, 0, 24, 24), text: text(t.tip, 'effect_' + i, 'text_info', 36, 0, INFO_W - 36 - 8, 16, '')});
    }
    while (t.units.length < units) {
        const i = t.units.length;
        const holder = image(t.tip, 'unit_cat_frame_' + i, D + 'unit_cat_holder_round.png', 24, 0, 26, 26);
        t.units.push({holder, icon: image(holder, 'unit_category_icon', D + 'replenishement_positive.png', 2, 2, 22, 22), name: text(t.tip, 'unit_name_' + i, 'text_info', 52, 0, INFO_W - 52 - 10, 16, '')});
    }
}

// Fills the window and stacks its blocks as the template's lists do. content: {title, chain, description, effects: [{icon, text, good}],
// opens: [{category, text}], reason, maxH}. Returns the height of the whole (with the instruction window).
function fillInfoTip(t, content) {
    const tall = c => c.TextDimensions()[1];
    const put = (c, x, y) => { at(c, x, y); size(c, c.Width(), Math.max(22, tall(c))); };
    const effects = content.effects || [], opens = content.opens || [], army = content.army || [];
    infoRows(t, effects.length, opens.length, army.length);
    t.title.SetStateText(content.title || '');
    t.chain.SetStateText(content.chain || '');
    t.reason.SetStateText(content.reason ? `[[col:game_red]]${content.reason}[[/col]]` : '');
    const reasonH = content.reason ? 13 + Math.max(22, tall(t.reason)) + 10 - 8 : 0;
    const layout = desc => {
        let y = 39 + 30;
        t.description.SetStateText(desc);
        t.description.SetVisible(!!desc);
        if (desc) {
            put(t.description, 14, y + 20);
            y += Math.max(52, 20 + tall(t.description) + 16);
        }
        t.effects.forEach((row, i) => {
            const e = effects[i];
            row.icon.SetVisible(!!e); row.text.SetVisible(!!e);
            if (!e) return;
            row.icon.SetImagePath(e.icon || 'ui/skins/default/replenishement_positive.png', 0);
            row.text.SetStateText(`[[col:${e.good === false ? 'game_red' : 'game_green'}]]${e.text}[[/col]]`);
            at(row.icon, 10, y);
            put(row.text, 36, y + 6);
            y += Math.max(30, 6 + tall(row.text) + 8);
        });
        t.opensIcon.SetVisible(!!opens.length); t.opensTitle.SetVisible(!!opens.length);
        if (opens.length) {
            at(t.opensIcon, 10, y);
            put(t.opensTitle, 38, y + 6);
            y += 24;
        }
        t.units.forEach((row, i) => {
            const o = opens[i];
            row.holder.SetVisible(!!o); row.name.SetVisible(!!o);
            if (!o) return;
            if (o.category) row.icon.SetImagePath(o.category, 0);
            row.name.SetStateText(o.text);
            at(row.holder, 24, y + 4);
            put(row.name, 52, y + 11);
            y += Math.max(50, 11 + tall(row.name) + 4);
        });
        t.armyIcon.SetVisible(!!army.length); t.armyTitle.SetVisible(!!army.length);
        if (army.length) {
            at(t.armyIcon, 10, y);
            put(t.armyTitle, 38, y + 6);
            y += 24;
        }
        t.army.forEach((row, i) => {
            const o = army[i];
            row.holder.SetVisible(!!o); row.name.SetVisible(!!o);
            if (!o) return;
            if (o.category) row.icon.SetImagePath(o.category, 0);
            row.name.SetStateText(o.text);
            at(row.holder, 24, y + 4);
            put(row.name, 52, y + 11);
            y += Math.max(50, 11 + tall(row.name) + 4);
        });
        return y + 17;
    };
    const full = content.description || '';
    let y = layout(full);
    t.cut = false;
    if (content.maxH && y + reasonH > content.maxH && full) {
        // the longest start of the description, cut at a word, that lets the window fit
        let lo = 0, hi = full.length;
        while (lo < hi) {
            const mid = Math.ceil((lo + hi) / 2);
            if (layout(full.slice(0, mid).replace(/\s+\S*$/, '') + '…') + reasonH <= content.maxH) lo = mid; else hi = mid - 1;
        }
        y = layout(lo ? full.slice(0, lo).replace(/\s+\S*$/, '') + '…' : '');
        t.cut = true;
    }
    size(t.tip, t.w, y);
    t.h = y;
    t.has_reason = !!content.reason;
    t.reason_h = 0;
    if (content.reason) {
        size(t.reason, t.reason.Width(), Math.max(22, tall(t.reason)));
        t.reason_h = 13 + t.reason.Height() + 10;
        size(t.instruction, t.w, t.reason_h);
        t.h = y - 8 + t.reason_h;
    }
    return t.h;
}

// The game's unit information panel for a crew of the barge, shown while the mouse is over its card: the small card beside a building's node and the
// card in the crew's choice. One component for both. Laid out after ui/common ui/unit_information.twui.xml (290 wide, the blocks stacked as its list):
//   info_panel            the panel's dark tile (panel_back_tile.png) in a thin brass line; the game lays parchment_texture_v_rolls.png over it,
//                         which the page leaves out (as a stretched border picture it left the middle see-through)
//   tx_unit-type          the name: 290 x 30 at 0, 1; header_14 centred
//   hbar                  separator_skull2.png at 31
//   subheader             34 tall at 39: the category's icon 26 x 26 at 12, the troop type from 48
//   descr_holder          84 tall in the game (bullet points); here the clip of the crew at work (16:9, web/art/<movie>.webm) and under it the short
//                         text in the notes' size: the game's description is the place of ours. ?unitvideo=top puts the clip above the subheader.
//   top_bar               30 tall: the men (icon_entity_small.png and the number), the upkeep (icon_income.png), and the hire (icon_treasury.png) in
//                         the place of the game's experience
//   row_header_stats      275 x 34, parchment_button_square_active.png, the title centred
//   dynamic_stats         a row a stat: the icon, the name from 22 on, the bar, the value
//   additional_explanation  a tooltip_frame window under the panel: here the state of the crew, red when a building has to open it first
// Left out on purpose, with their rows of the game: the unit's health, armour, leadership, speed, melee attack and defence, weapon strength, charge:
// a crew is 11 dwarfs on the barge's seats, those numbers belong to the barge, and the source unit's would be untrue. The stats are the crew's own
// weapon as the mod builds it (build/web/data.json, numbers: tools/crew_ui.py group_numbers), the ammunition with the cargo hold's bonus that stands,
// the accuracy with the bonus of the shooters' buildings that stand.
const UNIT_INFO_W = 290;
function unitInfo(parent, id, spec, flags = {}) {
    const D = 'ui/skins/default/', W = UNIT_INFO_W, o = spec.option, n = o.numbers || {}, group = spec.group_data;
    const panel = make(parent, id, 'unit_parchment');
    const info = {panel, spec};
    text(panel, 'tx_unit-type', 'text_unit_title', 12, 1 + 4, W - 24, 30, o.name);
    const hbar = make(panel, 'hbar', 'separator_skull');
    size(hbar, W - 20, 8);
    at(hbar, 10, 31);
    const vw = W - 28, vh = Math.round(vw * 9 / 16);
    let y = 39;
    const clip = () => {
        const video = make(panel, 'video', 'movie');
        size(video, vw, vh);
        at(video, 14, y + 2);
        video.SetMovie(['.webm', '.mp4'].map(ext => '/art/' + spec.movie + ext), 'Здесь будет видео из игры');
        info.video = video;
        y += vh + 8;
    };
    if (flags.unitvideo === 'top') clip();
    if (o.unit_card) image(panel, 'category', o.unit_card.category, 12, y + 4, 26, 26);
    text(panel, 'custom_name_display', 'text_unit', 48, y, W - 60, 34, (spec.area && spec.area.kind_name) || `${group.name} экипажа`);
    y += 34;
    if (flags.unitvideo !== 'top') clip();
    const note = text(panel, 'short_description', 'text_unit_note', 14, y, W - 28, 54, spec.text || o.about || '');
    y += Math.max(20, note.TextDimensions()[1]) + 8;
    // top_bar
    image(panel, 'icon_men', D + 'icon_entity_small.png', 12, y + 2, 26, 26);
    text(panel, 'dy_men', 'text_unit', 40, y, 40, 30, String(o.unit_card ? o.unit_card.men : ''));
    image(panel, 'icon_upkeep', D + 'icon_income.png', 104, y + 2, 26, 26).SetTooltipText('Содержание за ход', true);
    text(panel, 'upkeep', 'text_unit', 132, y, 50, 30, String(o.upkeep));
    image(panel, 'icon_cost', D + 'icon_treasury.png', 196, y + 2, 26, 26);
    text(panel, 'cost', 'text_unit', 224, y, 56, 30, String(o.hire));
    y += 32;
    const head = make(panel, 'row_header_stats', 'unit_header');
    size(head, W - 16, 34);
    at(head, 8, y);
    text(head, 'dy_title', 'text_unit_centre', 0, 0, W - 16, 34, (spec.area && spec.area.stats_head) || 'Стрельба экипажа');
    y += 38;
    // the rows of the crew's weapon; the bar is the value against the best of the group's kinds (for the reload: the fastest)
    const all = Object.values(group.options).map(x => x.numbers || {}).filter(x => x.range);
    const best = (f, low) => (low ? Math.min : Math.max)(...all.map(f));
    info.rows = {};
    // share null: a value in words or a pair (the blast and its radius), written across the bar's place, no bar
    const row = (key, icon, name, value, share) => {
        image(panel, 'icon_' + key, icon, 10, y, 22, 22);
        text(panel, 'name_' + key, 'text_unit', 36, y - 1, 130, 24, name);
        let back = null, fill = null;
        if (share !== null) {
            back = image(panel, 'bar_back_' + key, D + 'bar_back.png', 166, y + 5, 60, 12);
            fill = image(panel, 'bar_' + key, D + 'bar_white.png', 168, y + 7, Math.max(2, Math.round(56 * Math.min(1, share))), 8);
            fill.SetImageColour(235, 189, 124, 255);
        }
        const vx = share === null ? 166 : 228;
        info.rows[key] = {value: text(panel, 'value_' + key, 'text_unit_right', vx, y - 1, W - vx - 12, 24, value), fill, back};
        y += 24;
    };
    const ab = o.ability;
    if (ab) {
        // a crew that is an ability (the harpoon): its shot as the game's tables have it (build/web/data.json, ability)
        row('uses', D + 'icon_stat_ammo.png', 'Выстрелов за бой', String(ab.uses), null);
        if (ab.damage !== undefined) {
            row('damage', D + 'icon_stat_ranged_damage.png', 'Урон выстрела', String(ab.damage + ab.ap), null);
            row('ap', D + 'modifier_icon_armour_piercing.png', 'Бронебойный', String(ab.ap), null);
            if (ab.vs_large) row('vs_large', D + 'icon_stat_damage.png', 'Против крупных', '+' + ab.vs_large, null);
        }
        row('range', D + 'icon_stat_range.png', 'Дальность', String(ab.range), null);
        if (ab.blast) row('blast', D + 'icon_stat_damage.png', 'Взрыв', `${ab.blast + ab.blast_ap} · ${ab.radius} м`, null);
        row('wind_up', D + 'icon_stat_reload_time.png', 'Замах, с', String(ab.wind_up), null);
    }
    if (n.range) {
        // Each kind's own true numbers (build/web/data.json: the mod's weapon rows): the shot's damage where the shot itself hurts (a bomb or a
        // grenade does its harm by the blast: no damage row of 1), the range or the mod's words for it (a bomb falls under the barge), the reload,
        // the ammunition, the blast and its radius, the burning pieces of a bomb that bursts in the air.
        const dmg = x => (x.damage + x.ap) * x.shots * x.volley;
        if (dmg(n) > 1) {
            row('damage', D + 'icon_stat_ranged_damage.png', 'Урон выстрела', String(dmg(n)), dmg(n) / best(dmg));
            row('ap', D + 'modifier_icon_armour_piercing.png', 'Бронебойный', String(n.ap * n.shots * n.volley), n.ap / (n.damage + n.ap));
        }
        if (o.range_text) row('range', D + 'icon_stat_range.png', 'Дальность', o.range_text, null);
        else row('range', D + 'icon_stat_range.png', 'Дальность', String(n.range), n.range / best(x => x.range));
        row('reload', D + 'icon_stat_reload_time.png', 'Перезарядка, с', String(n.reload), best(x => x.reload, true) / n.reload);
        // the ammunition as the game shows a unit's: volleys a man or gun (the author's rule, docs/design/ammo-balance.md; numbers.volleys, seats), the
        // group's whole under it in small letters; with no seats in the data, the group's whole alone
        if (n.seats) {
            row('ammo', D + 'icon_stat_ammo.png', 'Боезапас', '', n.volleys / best(x => x.volleys || 0));
            info.ammoNote = text(panel, 'ammo_note', 'text_unit_note', 36, y - 4, W - 48, 18, '');
            y += 16;
        } else row('ammo', D + 'icon_stat_ammo.png', 'Боезапас', String(n.ammo), n.ammo / best(x => x.ammo));
        if (n.blast) row('blast', D + 'icon_stat_damage.png', 'Взрыв', `${n.blast + n.blast_ap} · ${n.radius} м`, null);
        if (o.fragments) row('fragments', D + 'icon_stat_damage.png', 'Взрыв осколка', `${o.fragments.blast + o.fragments.blast_ap} · ${o.fragments.radius} м`, null);
    }
    // what the buildings that stand add, a line a kind with the buildings it comes from (green; red when it makes the crew worse)
    info.accuracy = text(panel, 'accuracy', 'text_unit_note', 14, y + 2, W - 28, 20, '');
    info.accuracy_y = y + 2;
    info.base_h = y + 12;
    const base = {ammo: n.ammo, range: n.range, reload: n.reload};
    // additional_explanation: the crew's state, a window of its own under the panel
    info.state = make(parent, id + '_state', 'tooltip_instruction');
    info.stateText = text(info.state, 'text', 'text_info', 13, 10, W - 23, 22, '');
    for (const c of [panel, info.state]) { c.SetLayer('hover'); c.SetPassive(); c.SetVisible(false); }
    // what changes with the game: the ammunition with the cargo hold, the accuracy with the shooters' buildings, the state
    info.set = dyn => {
        const bonus = dyn.bonus || {};
        const better = (kind, pct) => (FX.KINDS[kind].positiveGood ? pct > 0 : pct < 0);
        const colour = (kind, pct, t) => (pct ? `[[col:${better(kind, pct) ? 'game_green' : 'game_red'}]]${t}[[/col]]` : t);
        // the ammunition in volleys a seat: the mod's Lua rounds the group's whole (floor(x + 0.5)) and the seats share it, so a bonus smaller than a
        // volley a seat is not lost (6 a pirate, +15 %: 83 for the twelve, 6,9 each)
        const ammo = ammoOf(n, bonus.ammo ? bonus.ammo.pct : 0);
        if (info.ammoNote) {
            const pct = bonus.ammo ? bonus.ammo.pct : 0;
            info.rows.ammo.value.SetStateText(colour('ammo', pct, ammo.each));
            info.ammoNote.SetStateText(`${volleysWord(ammo.per)} ${(spec.area && spec.area.per) || 'на место'} · на всех ${ammo.total} (${n.seats} ${seatsWord(n.seats)})`);
        }
        for (const kind of ['ammo', 'range', 'reload']) {
            const b = bonus[kind], r = info.rows[kind];
            if (!r || (kind === 'range' && (o.range_text || ab)) || (kind === 'ammo' && info.ammoNote)) continue;
            r.value.SetStateText(colour(kind, b ? b.pct : 0, String(b && b.pct ? FX.applyPct(base[kind], b.pct, kind) : base[kind])));
        }
        if (info.rows.damage && !ab) {
            const b = bonus.damage, d0 = (n.damage + n.ap) * n.shots * n.volley;
            info.rows.damage.value.SetStateText(colour('damage', b ? b.pct : 0, String(b && b.pct ? FX.applyPct(d0, b.pct, 'damage') : d0)));
        }
        const lines = FX.CREW_KINDS.filter(k => bonus[k] && bonus[k].pct && (k !== 'ammo' || n.ammo)).map(k => colour(k, bonus[k].pct,
            `${FX.KINDS[k].name} ${FX.signedPct(bonus[k].pct)}` + (k === 'ammo' && n.seats ? ` (${ammoOf(n, 0).each} → ${ammo.each} ${volleysWord(ammo.per)} ${(spec.area && spec.area.per) || 'на место'})` : '')
            + `: ${bonus[k].from.map(f => f.name + (f.mod ? ' (как в моде)' : '')).join(', ')}`));
        info.accuracy.SetStateText(lines.join('\n'));
        const linesH = lines.length ? Math.max(20, info.accuracy.TextDimensions()[1] + 4) : 0;
        size(info.accuracy, W - 28, Math.max(20, linesH));
        info.h = info.base_h + linesH;
        size(panel, W, info.h);
        info.stateText.SetStateText(dyn.reason ? `[[col:game_red]]${dyn.reason}[[/col]]` : dyn.state || '');
        info.has_state = !!(dyn.reason || dyn.state);
        info.state_h = info.has_state ? 10 + Math.max(22, info.stateText.TextDimensions()[1]) + 10 : 0;
        size(info.stateText, W - 23, Math.max(22, info.state_h - 20));
        size(info.state, W, info.state_h || 10);
        info.state.el.style.visibility = info.has_state ? '' : 'hidden';
        info.total = info.h + (info.has_state ? info.state_h - 8 : 0);
    };
    info.place = (x, top) => { at(panel, x, top); at(info.state, x, top + info.h - 8); };
    info.hook = owner => { owner.SetHoverChild(panel); owner.AddHoverChild(info.state); };
    info.set({});
    return info;
}

// The ammunition of a crew with a bonus, as the mod's Lua counts it: the group's whole times the bonus, rounded (floor(x + 0.5)), shared by its seats.
// -> {total, per: volleys a seat, each: the same as written (one decimal when it is not whole, a comma)}
function ammoOf(n, pct) {
    const total = Math.floor(n.ammo * (1 + (pct || 0) / 100) + 0.5), per = n.seats ? total / n.seats : total;
    const r = Math.round(per * 10) / 10;
    return {total, per: r, each: Number.isInteger(r) ? String(r) : r.toFixed(1).replace('.', ',')};
}
function volleysWord(v) {
    if (!Number.isInteger(v)) return 'залпа';
    const m10 = v % 10, m100 = v % 100;
    return m10 === 1 && m100 !== 11 ? 'залп' : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? 'залпа' : 'залпов';
}
function seatsWord(v) {
    const m10 = v % 10, m100 = v % 100;
    return m10 === 1 && m100 !== 11 ? 'место' : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? 'места' : 'мест';
}

// What the game changes in a crew's panel: every effect of the crew of the buildings that stand (the tree's effects of the catalogue, and the mod's
// own numbers of its buildings where the tree says nothing of that kind: web/js/crew_model.mjs, crewSources), where the crew is now.
function unitDyn(M, data, group, option, opt) {
    const now = M.crew(group), order = M.crew_order(group);
    return {bonus: FX.crewBonuses(crewSources(data, key => M.game.has_building(key), key => M.game.standing(key)), group),
            reason: opt.unlocked ? '' : `Откроет постройка «${opt.building.name}»`,
            state: option === order ? `В найме: ${M.crew_words(group).come} в начале хода` : option === now ? M.crew_words(group).stand : ''};
}

// The game's unit information panel of an army unit (ui/common ui/unit_information.twui.xml): here its numbers are true, it is an ordinary unit of the
// game. The stats of the game's tables (build/web/catalog.json, tools/web_export.py export_catalog): the men's health, armour, leadership, speed, melee
// attack and defence, charge; the missile weapon's damage, armour piercing, range, ammunition, reload. The weapon strength is not shown: the table of
// melee weapons has no layout the export can read. The bar is the value against the best of the dwarfs' units.
function armyInfo(parent, id, u, all, building) {
    const D = 'ui/skins/default/', W = UNIT_INFO_W, st = u.stats;
    const panel = make(parent, id, 'unit_parchment');
    const info = {panel};
    text(panel, 'tx_unit-type', 'text_unit_title', 12, 1 + 4, W - 24, 30, u.name);
    const hbar = make(panel, 'hbar', 'separator_skull');
    size(hbar, W - 20, 8);
    at(hbar, 10, 31);
    let y = 39;
    image(panel, 'category', u.card.category, 12, y + 4, 26, 26);
    text(panel, 'custom_name_display', 'text_unit', 48, y, W - 60, 34, {melee_infantry: 'Пехота ближнего боя', missile_infantry: 'Стрелковая пехота', warmachine: 'Боевая машина'}[u.caste] || u.caste);
    y += 36;
    image(panel, 'icon_men', D + 'icon_entity_small.png', 12, y + 2, 26, 26);
    text(panel, 'dy_men', 'text_unit', 40, y, 60, 30, String(st.men) + (st.engines ? ` · ${st.engines}` : ''));
    image(panel, 'icon_upkeep', D + 'icon_income.png', 104, y + 2, 26, 26).SetTooltipText('Содержание за ход', true);
    text(panel, 'upkeep', 'text_unit', 132, y, 50, 30, String(u.upkeep));
    image(panel, 'icon_cost', D + 'icon_treasury.png', 196, y + 2, 26, 26);
    text(panel, 'cost', 'text_unit', 224, y, 56, 30, String(u.hire));
    y += 32;
    const head = make(panel, 'row_header_stats', 'unit_header');
    size(head, W - 16, 34);
    at(head, 8, y);
    text(head, 'dy_title', 'text_unit_centre', 0, 0, W - 16, 34, 'Характеристики');
    y += 38;
    const units = Object.values(all);
    const best = f => Math.max(1, ...units.map(x => x.stats[f] || 0));
    const row = (key, icon, name, value, share) => {
        image(panel, 'icon_' + key, icon, 10, y, 22, 22);
        text(panel, 'name_' + key, 'text_unit', 36, y - 1, 130, 24, name);
        image(panel, 'bar_back_' + key, D + 'bar_back.png', 166, y + 5, 60, 12);
        image(panel, 'bar_' + key, D + 'bar_white.png', 168, y + 7, Math.max(2, Math.round(56 * Math.min(1, share))), 8).SetImageColour(235, 189, 124, 255);
        text(panel, 'value_' + key, 'text_unit_right', 228, y - 1, W - 228 - 12, 24, value);
        y += 24;
    };
    const stat = (key, icon, name) => { if (st[key] !== null && st[key] !== undefined) row(key, D + icon, name, String(st[key]), st[key] / best(key)); };
    stat('health', 'icon_stat_health.png', 'Здоровье');
    stat('armour', 'icon_stat_armour.png', 'Броня');
    stat('leadership', 'icon_stat_morale.png', 'Боевой дух');
    stat('speed', 'icon_stat_speed.png', 'Скорость');
    stat('melee_attack', 'icon_stat_attack.png', 'Атака');
    stat('melee_defence', 'icon_stat_defence.png', 'Защита');
    stat('charge', 'icon_stat_charge_bonus.png', 'Бонус натиска');
    if (st.range) {
        row('missile', D + 'icon_stat_ranged_damage.png', 'Урон выстрела', String((st.missile_damage + st.missile_ap) * (st.shots || 1)), (st.missile_damage + st.missile_ap) / Math.max(1, ...units.map(x => (x.stats.missile_damage || 0) + (x.stats.missile_ap || 0))));
        row('missile_ap', D + 'modifier_icon_armour_piercing.png', 'Бронебойный', String(st.missile_ap * (st.shots || 1)), st.missile_ap / Math.max(1, st.missile_damage + st.missile_ap));
        stat('range', 'icon_stat_range.png', 'Дальность');
        stat('ammo', 'icon_stat_ammo.png', 'Боезапас');
        if (st.reload) row('reload', D + 'icon_stat_reload_time.png', 'Перезарядка, с', String(st.reload), Math.min(1, 4 / st.reload));
    }
    const note = text(panel, 'note', 'text_unit_note', 14, y + 2, W - 28, 20, st.health === null ? 'Сила оружия ближнего боя и здоровье машины не прочитаны: их таблиц страница не читает' : 'Сила оружия ближнего боя не прочитана: таблицы оружия страница не читает');
    y += Math.max(20, note.TextDimensions()[1]) + 10;
    info.h = y;
    size(panel, W, y);
    info.state = make(parent, id + '_state', 'tooltip_instruction');
    const stateText = text(info.state, 'text', 'text_info', 13, 10, W - 23, 22, `Обычный отряд армии: открывает «${building}». Найм армии на этой странице не моделируется`);
    info.state_h = 10 + Math.max(22, stateText.TextDimensions()[1]) + 10;
    size(stateText, W - 23, info.state_h - 20);
    size(info.state, W, info.state_h);
    info.total = info.h + info.state_h - 8;
    for (const c of [panel, info.state]) { c.SetLayer('hover'); c.SetPassive(); c.SetVisible(false); }
    info.place = (x, top) => { at(panel, x, top); at(info.state, x, top + info.h - 8); };
    info.hook = owner => { owner.SetHoverChild(panel); owner.AddHoverChild(info.state); };
    return info;
}

function demoTip(parent, id, x, bottom, spec) {
    const noted = spec.note !== undefined;         // one more line under the text, set later (red: what opens a locked kind)
    const tw = 300, pad = 14, vw = tw - 2 * pad, vh = Math.round(vw * 9 / 16), th = pad + vh + 12 + 24 + 44 + (noted ? 22 : 0) + pad;
    const tip = image(parent, id, LAYOUTS + 'backdrop.png', x, bottom - th, tw, th);
    const video = make(tip, 'video', 'movie');
    size(video, vw, vh);
    at(video, pad, pad);
    video.SetMovie(['.webm', '.mp4'].map(ext => '/art/' + spec.movie + ext), 'Здесь будет видео из игры');
    text(tip, 'tip_head', 'text_head', pad, pad + vh + 10, vw, 24, spec.head);
    text(tip, 'tip_text', 'text_body', pad, pad + vh + 36, vw, 44, spec.text);
    const note = noted ? text(tip, 'tip_note', 'text_line', pad, pad + vh + 36 + 44, vw, 20, spec.note) : null;
    const edge = make(tip, 'tip_edge', 'frame_edge');
    size(edge, tw, th);
    at(edge, 0, 0);
    tip.SetPassive();
    tip.SetLayer('hover');
    tip.SetVisible(false);
    return {tip, video, note, w: tw, h: th};
}

// ---------------- the tree of buildings: square nodes joined by brass lines, laid out from the requirements ----------------
// Tiers by depth (the longest way from a node with no requirement), the order inside a tier by the mean place of the nodes it needs (one pass, enough
// for a small tree), every tier spread evenly across the width. direction "down": the first buildings on top, what needs them below; "up": the other way.
// Lines run square: from a node to halfway, across, on to the other node; lines that meet share their halfway.
// The game's numbers (ui/campaign ui/building_browser.twui.xml): a slot of the tree is 74 x 74 and the arrow between two slots 32 (TreeCallback, padding_y;
// the template's own comment: "106 is the sum of the height of a tree slot (74), plus the height of an arrow (32)"). Nothing here is scaled.
const NODE = 74, TIER_GAP = 106, LINE = 3;
// columns of the tree when it has side branches: the trunk right of the middle, a left branch, a right branch. A branch may stand some columns to the
// right of its side's column (blueprint.json, branches, shift): a side branch of a side chain, the column over the chain's first building stays free
// for the chain's own levels. One such column is the game's 106 (a slot of 74 and 32 between, TreeCallback padding_x of building_browser.twui.xml).
// left: the left chain's slot starts 20 from the tree's edge, so its side branch one column right (with its unit card, 17 beyond the slot) ends
// before the trunk's slot begins.
const COLUMN = {trunk: 0.62, left: 0.138, right: 0.86}, COLUMN_STEP = 106;
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
            const key = col + ':' + tier[n.key] + ':' + ((n.branch && n.branch.shift) || 0);
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
        pos[n.key] = {x: x + place[n.key] * w - NODE / 2 + ((n.branch && n.branch.shift) || 0) * COLUMN_STEP, y: y + t * TIER_GAP, shift: (n.branch && n.branch.shift) || 0};
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
            if (b.shift > a.shift && !down) {
                // a side branch: the line leaves the building by its side, at the middle (under its unit cards, which end 28 below the slot's top),
                // and turns up into the branch's node
                const side = a.y + NODE / 2;
                line(a.x + NODE, side, bx, side, colour); line(bx, side, bx, by, colour);
                continue;
            }
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
    // the game's building information window of every node, shown while the mouse is over its slot (not over its unit cards: they are siblings)
    if (flags.tree !== 'demo') for (const [i, v] of view.tree.entries()) {
        v.info = makeInfoTip(parent.parent, 'building_information_' + i);
        v.button.AddHoverChild(v.info.tip);
    }
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
    // On hover the demo window, the same as Malakai's side: left of the tree's leftmost slot, level with the card, clear of the slot, the cards and the other nodes.
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
        // its marks: an hourglass while this kind is hired, the green check while it stands at the rails (the same states the choice shows)
        const waiting = image(card, 'waiting', 'ui/skins/default/icon_hourglass.png', CARD_W - 15, CARD_H - 17, 16, 16);
        const standing = image(card, 'standing', 'ui/skins/default/icon_check_green.png', CARD_W - 16, CARD_H - 15, 17, 15);
        const info = unitInfo(frame, 'crew_info_' + spec.option, {option, group_data: group, movie: spec.movie, text: spec.text || option.about || ''}, flags);
        info.hook(card);
        view.crew.push({card, info, tip: info.panel, building: v.node.key, group: spec.group, option: spec.option, waiting, standing, cy: parent.y + cy + CARD_H / 2,
                        x: parent.x + v.button.x - 10 - UNIT_INFO_W});      // beside the card: left of its slot, the card stays clear
    }
    view.selected = nodes.length ? nodes[0].key : null;
    return height + 20;      // the cost banner under the lowest row
}

// The tree of the constructor's file: every node at its own place (col, row of the game's grid of 106, the tree growing up), the lines of
// tree_model.mjs linkSegments (the same as the constructor draws), the small crew cards of what each node opens. The column is narrow: the tree
// lies in a window that pans by dragging (and by the wheel) when it is larger; "Всё" shows the whole of it smaller, "1:1" back to the game's
// size. Nothing of the slot changes its size at 1:1.
function makeFileTree(parent, view, M, blueprint, flags, x, y, w, h, wide) {
    const rows = view.data.tree_rows;
    const D = 'ui/skins/default/';
    const win = make(parent, 'tree_window', 'tree_window');
    size(win, w, h);
    at(win, x, y);
    const holder = make(win, 'tree_holder', 'tree_holder');
    const pan = view.pan = {x: 0, y: 0, z: 1, win, holder};
    const c0 = rows.length ? Math.min(...rows.map(r => r.col)) : 0, r1 = rows.length ? Math.max(...rows.map(r => r.row)) : 0;
    const pos = {};
    // 24 above the highest row for the crew cards (22 over the slot), 8 on the left; the holder's (0, 0) is the content's corner
    for (const r of rows) pos[r.key] = {x: 8 + (r.col - c0) * GRID, y: 24 + (r1 - r.row) * GRID};
    const cw = rows.length ? Math.max(...Object.values(pos).map(p => p.x)) + NODE + 17 + 8 : 0;
    const ch = rows.length ? Math.max(...Object.values(pos).map(p => p.y)) + NODE + 22 + 4 : 0;
    size(holder, Math.max(1, cw), Math.max(1, ch));
    pan.cw = cw; pan.ch = ch; pan.w = w; pan.h = h;
    let seg = 0;
    const line = (x0, y0, x1, y1, colour) => image(holder, `tree_line_${seg++}`, WEB_ART + (colour ? `tree_line_${colour}.png` : 'tree_line.png'),
        Math.min(x0, x1) - LINE / 2, Math.min(y0, y1) - LINE / 2, Math.abs(x1 - x0) + LINE, Math.abs(y1 - y0) + LINE);
    const blocked = slotsBlock(Object.values(pos));
    for (const r of rows) for (const p of r.requires) {
        if (!pos[p]) continue;
        for (const [x0, y0, x1, y1] of linkSegments(pos[p], pos[r.key], blocked)) line(x0, y0, x1, y1, r.branch);
    }
    const nodes = rows.map(r => ({key: r.key, name: r.name, icon: r.icon_path, needs: r.requires, branch: r.branch ? {colour: r.branch} : null, row: r}));
    view.tree = nodes.map((n, i) => {
        const {x: nx, y: ny} = pos[n.key];
        const b = image(holder, TREE + i, D + 'building_frame.png', nx, ny, NODE, NODE);
        b.SetInteractive(true);
        const v = {node: n, button: b};
        v.icon = image(b, 'icon', n.icon || D + 'icon_check.png', 0, 0, NODE, NODE);
        v.plain = image(b, 'plain', n.branch ? WEB_ART + `branch_frame_${n.branch.colour}.png` : D + 'building_frame_plain.png', 0, 0, NODE, NODE);
        v.branch = n.branch;
        v.frameSelected = image(b, 'selected', n.branch ? WEB_ART + `branch_frame_${n.branch.colour}_selected.png` : D + 'building_frame_selected.png', 0, 0, NODE, NODE);
        v.constructing = image(b, 'constructing', D + 'constructing_1.png', 6, 6, NODE - 12, NODE - 12);
        v.constructing.SetImageColour(255, 255, 255, 0x64);
        v.check = image(b, 'check', D + 'icon_check_green.png', 44, 48, 31, 28);
        v.padlock = image(b, 'padlock', D + 'padlock.png', NODE - 24, 2, 20, 25);
        // the level in its line, as the game's slot shows it (building_frame.twui.xml, building_level: 20 x 20 docked at the lower left, 0, 54;
        // the game has pictures of I to V)
        if (n.row.in_line && n.row.line_level <= 5) v.level = image(b, 'building_level', D + `settlement_silver_numeral_${n.row.line_level}.png`, 0, 54, 20, 20);
        v.hover = image(b, 'hover', D + 'building_frame_hover.png', -NODE * 8 / 74, -NODE * 8 / 74, NODE * 90 / 74, NODE * 90 / 74);
        v.hoverSelected = image(b, 'hover_selected', D + 'building_frame_selected_hover.png', 0, 0, NODE, NODE);
        v.hoverSelected.SetVisible(false);
        b.SetHoverChild(v.hover);
        b.SetHoverBrighten(0.4);
        v.turnsBanner = image(b, 'turns_banner', D + 'turns_banner_queued.png', -6, NODE - 16, NODE + 12, 20);
        v.turns = text(b, 'turns', 'text_line', 20, NODE - 16, NODE - 14, 20, '');
        v.cost = image(holder, TREE + 'cost_' + i, D + 'icon_banner_bg.png', nx + 3, ny + NODE + 2, 62, 18);
        v.costRed = image(v.cost, 'red', D + 'red_text_banner_shadow.png', 0, 0, 62, 18);
        image(v.cost, 'coins', D + 'icon_treasury.png', 4, 1, 16, 16);
        v.costText = text(v.cost, 'value', 'text_line', 22, -1, 40, 20, '');
        v.info = makeInfoTip(parent.parent, 'building_information_' + i);
        b.AddHoverChild(v.info.tip);
        return v;
    });
    view.wipe = 1;
    setInterval(() => {
        view.wipe = view.wipe % 12 + 1;
        for (const v of view.tree || []) if (v.constructing.Visible()) v.constructing.SetImagePath(D + `constructing_${view.wipe}.png`, 0);
    }, 120);
    // the crew each node opens, as the game's small unit cards by its slot (see makeTree): what has a unit card and is not the group's mount
    view.crew = [];
    const frame = parent.parent;
    const clips = Object.fromEntries((blueprint.crew_cards || []).map(c => [c.group + ':' + c.option, c]));
    const armyAll = view.data.army_units || {};
    for (const v of view.tree) {
        const list = v.node.row.unlocks.map(u => ({...u, group_data: view.data.groups[u.group]})).map(u => ({...u, option_data: u.group_data && u.group_data.options[u.option]}))
            .filter(u => u.option_data && u.option_data.unit_card && u.option !== u.group_data.mount);
        const army = (v.node.row.units || []).map(k => armyAll[k]).filter(Boolean);
        const total = list.length + army.length;
        // the army units after the crew in the same row, the game's own frame (the crew's frame is the crew group's colour)
        army.forEach((u, j) => {
            const i = list.length + j, row_w = CARD_W + (total - 1) * (CARD_W - CARD_OVERLAP);
            const cx = v.button.x + NODE + 17 - row_w + i * (CARD_W - CARD_OVERLAP), cy = v.button.y - 22;
            const card = slotUnitCard(holder, `mtb_army_card_${v.node.row.short}_${u.key}`, cx, cy, u.card, null, false);
            const info = armyInfo(frame, `army_info_${v.node.row.short}_${u.key}`, u, armyAll, v.node.row.name);
            info.hook(card);
            view.crew.push({card, info, tip: info.panel, building: v.node.key, army: u.key, v, cardY: cy});
        });
        list.forEach((u, i) => {
            const row_w = CARD_W + (total - 1) * (CARD_W - CARD_OVERLAP);
            const cx = v.button.x + NODE + 17 - row_w + i * (CARD_W - CARD_OVERLAP), cy = v.button.y - 22;
            const card = slotUnitCard(holder, `mtb_crew_card_${v.node.row.short}_${u.option}`, cx, cy, u.option_data.unit_card, u.group_data.card_frame || 'gold', flags.aboard === 'outline');
            const waiting = image(card, 'waiting', D + 'icon_hourglass.png', CARD_W - 15, CARD_H - 17, 16, 16);
            const standing = image(card, 'standing', D + 'icon_check_green.png', CARD_W - 16, CARD_H - 15, 17, 15);
            const clip = clips[u.group + ':' + u.option] || {};
            const info = unitInfo(frame, `crew_info_${v.node.row.short}_${u.option}`, {option: u.option_data, group_data: u.group_data, movie: clip.movie || u.option + '_demo', text: clip.text || u.option_data.about || ''}, flags);
            info.hook(card);
            view.crew.push({card, info, tip: info.panel, building: v.node.key, group: u.group, option: u.option, waiting, standing, v, cardY: cy});
        });
    }
    // "Всё" / "1:1": the whole tree smaller, or the game's size; shown only when the tree is larger than its window
    // in the column's head row, right of its title: never over the tree
    const fitBtn = makeButton(parent, 'mtb_tree_fit', x + w - 64, 4, 64, 26, 'Всё');
    pan.fitBtn = fitBtn;
    pan.fits = cw <= w && ch <= h;
    fitBtn.button.SetVisible(!pan.fits);
    // «Развернуть дерево»: the window opens over the drawing, across the whole panel, at the game's size; «Свернуть» back into the column
    const openBtn = makeButton(parent, 'mtb_tree_expand', x + w - 64 - 8 - 150, 4, 150, 26, 'Развернуть дерево');
    openBtn.button.SetVisible(!pan.fits);
    openBtn.button.SetTooltipText('Дерево поверх чертежа на всю панель, в игровом размере', true);
    pan.open = false;
    pan.expand = () => {
        pan.open = !pan.open;
        const r = pan.open ? wide : {x, y, w, h};
        size(win, r.w, r.h); at(win, r.x, r.y);
        pan.w = r.w; pan.h = r.h;
        win.el.classList.toggle('open', pan.open);
        openBtn.label.SetStateText(pan.open ? 'Свернуть дерево' : 'Развернуть дерево');
        pan.fits = cw <= pan.w && ch <= pan.h;
        fitBtn.button.SetVisible(!pan.fits || pan.z < 1);
        pan.home();
    };
    fitBtn.button.SetTooltipText('Показать всё дерево или вернуть игровой размер. Дерево двигается перетаскиванием и колесом мыши', true);
    pan.clamp = () => {
        const sw = cw * pan.z, sh = ch * pan.z, W = pan.w, H = pan.h;
        pan.x = sw <= W ? (W - sw) / 2 : Math.min(0, Math.max(W - sw, pan.x));
        pan.y = sh <= H ? 0 : Math.min(0, Math.max(H - sh, pan.y));
        holder.el.style.transformOrigin = '0 0';
        holder.el.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${pan.z})`;
        placeTips(view);
    };
    pan.home = () => {
        // the root's end in sight: the lowest row at the window's foot, the lowest node (the root) in the middle across
        pan.z = 1;
        const low = rows.length ? rows.reduce((m, r) => (r.row < m.row ? r : m), rows[0]) : null;
        pan.x = low ? pan.w / 2 - (pos[low.key].x + NODE / 2) : (pan.w - cw) / 2;
        pan.y = pan.h - ch;
        pan.clamp();
        fitBtn.label.SetStateText('Всё');
    };
    pan.toggle = () => {
        if (pan.z < 1) { pan.home(); return; }
        pan.z = Math.min(1, pan.w / cw, pan.h / ch);
        pan.x = 0; pan.y = 0;
        pan.clamp();
        fitBtn.label.SetStateText('1:1');
    };
    // drag to pan; a drag is not a click on what it started on
    let drag = null, dragged = false;
    win.el.addEventListener('mousedown', e => { if (e.button === 0 && !pan.fits) { drag = {x: e.clientX, y: e.clientY, px: pan.x, py: pan.y}; dragged = false; } });
    window.addEventListener('mousemove', e => {
        if (!drag) return;
        if (!(e.buttons & 1)) { drag = null; win.el.style.cursor = ''; return; }
        const k = win.el.getBoundingClientRect().width / pan.w || 1;
        const dx = (e.clientX - drag.x) / k, dy = (e.clientY - drag.y) / k;
        if (!dragged && Math.hypot(dx, dy) < 4) return;
        dragged = true;
        win.el.style.cursor = 'grabbing';
        pan.x = drag.px + dx; pan.y = drag.py + dy;
        pan.clamp();
    });
    window.addEventListener('mouseup', () => { drag = null; win.el.style.cursor = ''; });
    // the end of a drag: not a click on the node it began on (the capture stops it before the node's own handler, and the window's listener too)
    win.el.addEventListener('mouseup', e => { if (dragged) e.stopPropagation(); drag = null; dragged = false; win.el.style.cursor = ''; }, true);
    win.el.addEventListener('wheel', e => {
        if (pan.fits) return;
        e.preventDefault();
        pan.y -= e.deltaY; pan.x -= e.deltaX;
        pan.clamp();
    }, {passive: false});
    pan.home();
    view.selected = nodes.length ? nodes[0].key : null;
    view.about.SetStateText(`Построек: ${rows.length}.`);
    return h;
}

// Where a node's slot is on the panel's frame, through the tree's window (its pan and zoom): for the windows shown beside it.
function slotOnFrame(view, v) {
    const p = view.pan, col = p.win.parent;
    return {x: col.x + p.win.x + p.x + v.button.x * p.z, y: col.y + p.win.y + p.y + v.button.y * p.z, k: p.z};
}

// the crew cards' panels of the file's tree: left of the tree's window, level with the card, inside the screen
function placeTips(view) {
    for (const c of view.crew || []) {
        if (!c.v || !c.info.total) continue;
        const s = slotOnFrame(view, c.v), frame = c.info.panel.parent;
        const cy = s.y + (c.cardY - c.v.button.y + CARD_H / 2) * s.k;
        // left of the tree's window; with the window opened over the drawing, right of the card
        let px = view.pan.win.parent.x + view.pan.win.x - 10 - UNIT_INFO_W;
        if (px < 4) px = Math.min(frame.Width() - 8 - UNIT_INFO_W, s.x + (c.card.x - c.v.button.x + CARD_W + 10) * s.k);
        c.info.place(px, Math.max(70, Math.min(cy - c.info.total / 2, frame.Height() - 8 - c.info.total)));
    }
}

function nodeStatus(M, n) {
    return n.demo ? {state: 'demo'} : M.status(n.key);
}

// The states of the game's slot (square_building_button) as the page uses them:
//   built     full colour, building_frame_plain, the green check;
//   normal    can be ordered, or ordered: colour #FFFFFFB4 (a little see-through); the game also pulses it (glow_pulse_t0), not done here;
//   greyed    needs an earlier building: greyscale and #FFFFFF80 (half see-through);
//   short of gold: the slot as normal, the cost banner red (building_cost, state red). Which slot state the horde's tree takes then is to check in the game.
// The building window of a node of the file: its own name, text, lines and crew; the chain's name of the mod for a node of the mod.
function fileInfo(view, row, card, reason) {
    const D = 'ui/skins/default/';
    return {
        title: row.name, chain: (card && card.chain_title) || '', description: row.text,
        // what appears on the ship with it: a line each, «(рисунок не готов)» where the drawing has nothing for it yet
        effects: [...(row.effects || []).filter(e => e.text).map(e => ({icon: e.icon || D + 'replenishement_positive.png', text: e.text, good: e.good})),
                  ...(row.parts || []).map(p => {
                      const spec = p.part && (view.data.parts_all || {})[p.part];
                      const drawn = spec && spec.drawn;
                      return {icon: 'ui/campaign ui/effect_bundles/general_ability.png', good: true,
                              text: `Вид на корабле: ${p.part ? (spec ? spec.name : p.part) : p.name || 'новая деталь'}${drawn ? '' : ' (рисунок не готов)'}`};
                  })],
        opens: row.unlocks.map(u => ({g: view.data.groups[u.group], u})).filter(({g, u}) => g && g.options[u.option] && g.options[u.option].unit_card && u.option !== g.mount).map(({g, u}) => {
            const o = g.options[u.option], money = [o.hire ? `найм ${o.hire}` : '', o.upkeep ? `содержание ${o.upkeep} за ход` : ''].filter(Boolean).join(', ');
            return {category: o.unit_card.category, text: o.name + (money ? ` (${money})` : '')};
        }),
        army: (row.units || []).map(k => (view.data.army_units || {})[k]).filter(Boolean).map(u => ({category: u.card.category, text: u.name})),
        reason,
    };
}

function refreshTree(view, M) {
    // the small unit cards: their marks and their panels (left of the tree's leftmost slot, level with the card, inside the screen)
    for (const c of view.crew || []) {
        if (c.army) continue;           // an army unit's panel does not change with the game
        const o = M.crew_options(c.group).find(x => x.key === c.option);
        if (!o) continue;
        c.waiting.SetVisible(M.crew_order(c.group) === c.option);
        c.standing.SetVisible(M.crew(c.group) === c.option && M.crew_order(c.group) !== c.option);
        c.info.set(unitDyn(M, view.data, c.group, c.option, o));
        if (c.v) continue;          // the file's tree: placeTips, through the window's pan
        const frame = c.info.panel.parent;
        c.info.place(c.x, Math.max(70, Math.min(c.cy - c.info.total / 2, frame.Height() - 8 - c.info.total)));      // under the screen's title
    }
    if (view.pan) placeTips(view);
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
        if (v.level) v.level.SetVisible(!building);        // the turns banner takes the slot's foot while it is built
        const row = !v.node.demo && M.level(v.node.key);
        v.cost.SetVisible(!!row && !built && !building);
        v.costRed.SetVisible(poor);
        // the game's red state adds a dark shadow behind the number (red_text_banner_shadow.png); the red of the number itself is the page's guess, to check in the game
        v.costText.SetStateText(row ? (poor ? `[[col:red]]${row.cost}[[/col]]` : String(row.cost)) : '');
        const state = poor ? `не хватает золота: нужно ${row.cost}` : {built: 'построено', building: `строится, ${turnsText(st.turns || 0)}`, open: 'можно заказать', locked: st.why || 'недоступно', demo: 'пример, не из данных'}[st.state] || '';
        if (!v.info) { v.button.SetTooltipText(`${v.node.name}\n${state}`, true); continue; }
        // The building information window: what the game writes about a building, and under it, red, why it cannot be built now.
        const card = view.cards[v.node.key];
        const opens = ((card && card.opens) || []).filter(o => o.panel !== false && !o.mount);
        const reason = st.state === 'locked' ? (poor ? `Не хватает золота: нужно ${row.cost}.` : (st.why || 'Недоступно') + '.') : '';
        if (v.node.row) fillInfoTip(v.info, {...fileInfo(view, v.node.row, card, reason), maxH: v.info.tip.parent.parent.Height() - 8});
        else fillInfoTip(v.info, {
            title: v.node.name, chain: (card && card.chain_title) || '', description: firstPart(row.text || (card && card.text)),
            // a line of the mod that only names what the crew block below shows is not repeated
            effects: (card ? card.effects.filter(e => !e.hidden && !e.off && !opens.some(o => (e.text || '').includes(o.name))) : row.lines.map(l => ({text: l})))
                .map(e => ({icon: e.icon, text: e.text || `${e.effect} = ${e.value}`, good: e.good})),
            opens: opens.map(o => {
                const option = view.data.groups[o.group].options[o.option], money = [o.hire ? `найм ${o.hire}` : '', o.upkeep ? `содержание ${o.upkeep} за ход` : ''].filter(Boolean).join(', ');
                return {category: option.unit_card && option.unit_card.category, text: o.name + (money ? ` (${money})` : '')};
            }),
            reason,
        });
        // Beside the slot as the game puts it (docs/feedback/01-building-tooltip.png): right of the slot and of its unit cards (17 beyond the slot), the
        // lower edge 28 under the slot's; on the left of the slot when the screen ends, and kept inside the screen. Offsets from the panel's frame.
        const frame = v.info.tip.parent, col = v.button.parent, root = frame.parent;
        const on = view.pan ? slotOnFrame(view, v) : {x: col.x + v.button.x, y: col.y + v.button.y, k: 1};
        const sx = on.x, sy = on.y;
        let x = sx + (NODE + 17) * on.k;
        if (frame.x + x + INFO_W > root.Width() - 4) x = sx - 8 - INFO_W;
        let y = Math.max(4 - frame.y, Math.min(root.Height() - 4 - frame.y, sy + (NODE + 28) * on.k) - v.info.h);
        // an open choice of the crew: the window goes above it when there is room (it is over the choice in any case, by its layer)
        const pk = openArea(view) ? openArea(view).pick : null;
        if (pk) {
            const px0 = view.sheet.x + pk.x, py0 = view.sheet.y + pk.y;
            if (x < px0 + pk.Width() && x + INFO_W > px0 && y + v.info.h > py0 && py0 - 6 - v.info.h >= 4 - frame.y) y = py0 - 6 - v.info.h;
        }
        at(v.info.tip, x, y);
        at(v.info.instruction, x, y + v.info.h - v.info.reason_h);
        if (!v.info.hooked) { v.info.hooked = true; v.button.AddHoverChild(v.info.instruction); }
        if (!v.info.has_reason) v.info.instruction.SetVisible(false);
        v.info.instruction.el.style.visibility = v.info.has_reason ? '' : 'hidden';
        v.button.SetTooltipText('', true);
    }
}

// A group's place: there from the moment a building that makes it stands; with that building gone the place and its choice go too. What stands is in
// ink; an order waits for the turn: the ordered kind as a sketch at the places when nobody stands there (a crew that stands stays in ink until the
// turn replaces it, then only the tag tells of the order), the tag with an hourglass and the turns left. A detail the crew takes the place of (the
// lookouts of the nests, spec.hides_part) is hidden while someone of the crew is there or sketched there.
function refreshCrewArea(view, M, c) {
    const g = c.group, w = M.crew_words(g), shown = M.crew_place(g), now = M.crew(g), order = M.crew_order(g);
    const options = M.crew_options(g), standing = options.find(o => o.key === now), ordered = options.find(o => o.key === order);
    const nobody = !standing || standing.empty, coming = ordered && !ordered.empty && nobody ? order : null;
    c.area.SetVisible(shown);
    if (!shown) c.open = false;
    c.pick.SetVisible(shown && c.open);
    if (c.empty) c.empty.SetVisible(nobody && !coming);
    for (const [key, layer] of Object.entries(c.layers)) layer.SetVisible(!nobody && key === now);
    for (const [key, layer] of Object.entries(c.sketches)) layer.SetVisible(key === coming);
    const hides = c.spec.hides_part && view.layers[c.spec.hides_part];
    if (hides && hides.ink && (!nobody || coming)) hides.ink.SetVisible(false);
    const tag = ordered ? 'wait' : nobody ? 'plus' : 'swap';
    for (const k of Object.keys(c.tags)) { c.tags[k].SetVisible(k === tag); c.hoverTags[k].SetVisible(k === tag); }
    c.glow.SetVisible(shown && M.crew_hint(g));
    c.area.SetTooltipText(c.open ? '' : ordered ? (ordered.empty ? `${w.who} ${w.leave} в начале хода` : `${ordered.name}: в найме, ${w.come} в начале хода`)
        : nobody ? '' : `${standing.name}: ${standing.unit_card ? standing.unit_card.men + ' ' + w.at + ', ' : ''}содержание ${standing.upkeep} за ход`, true);
    // Both states show at once: who stands (the game's frame of the selected card) and who is ordered (the game's banner of a unit being recruited
    // with the turns); every other kind its hire, red when the treasury cannot pay it.
    for (const slot of c.slots) {
        const o = options.find(x => x.key === slot.key), will = M.crew_preview(g, o.key);
        slot.selected.SetVisible(o.key === now);
        slot.padlock.SetVisible(!o.unlocked);
        slot.turnsBanner.SetVisible(o.key === order);
        slot.card.ShaderTechniqueSet(o.unlocked ? 'normal_t0' : 'set_greyscale_t0');
        slot.card.SetImageColour(255, 255, 255, o.unlocked ? 255 : 0x80);
        slot.name.SetStateText(o.unlocked ? o.name : `[[col:grey]]${o.name}[[/col]]`);
        const hire = o.unlocked && !o.empty && o.key !== now && o.key !== order, queued = o.key === order;
        if (slot.card.costPlate) {
            slot.card.costPlate.SetVisible(hire);
            slot.card.cost.SetStateText(will.kind === 'poor' ? `[[col:red]]${o.hire}[[/col]]` : String(o.hire));
            for (const part of slot.card.army) part.SetVisible(o.key === now);
            slot.card.frame.SetImageColour(255, 255, 255, queued ? 0x64 : 255);
        }
        slot.card.img.style.opacity = queued ? String(0x64 / 255) : '';      // the card's queued state: the picture and the frame at 100 of 255
        slot.hit.SetTooltipText(o.empty ? will.text : '', true);       // the empty card has no panel: the small tooltip says what a click does
        if (slot.info) {
            slot.info.set({...unitDyn(M, view.data, g, o.key, o), ...(will.bad ? {reason: will.text} : will.kind === 'cancelled' ? {state: will.text} : {})});
            placeUnitInfo(view, c, slot);
        }
    }
    const upkeep = M.crew_upkeep(), next = M.crew_upkeep_next();
    c.foot.SetStateText(`Содержание экипажа: ${upkeep} за ход` + (next !== upkeep ? ` → ${next}` : ''));
}

// The unit's panel beside the choice, as the game's tooltip of a unit card stands by it: over the choice, centred on the card under the mouse, when
// it fits; under it otherwise; beside the window, right or left, when neither does (a choice opened over a place low on the drawing). Kept inside
// the panel's frame; it covers neither the card under the mouse nor its neighbours.
function placeUnitInfo(view, c, slot) {
    const frame = slot.info.panel.parent, F = {w: frame.Width(), h: frame.Height()};
    const px = view.sheet.x + c.pick.x, py = view.sheet.y + c.pick.y, pw = c.pick.Width(), ph = c.pick.Height(), h = slot.info.total, W = UNIT_INFO_W;
    const cx = px + slot.hit.x + slot.hit.Width() / 2;
    const across = Math.max(6, Math.min(cx - W / 2, F.w - 6 - W));
    if (py - 6 - h >= 8) { slot.info.place(across, py - 6 - h); return; }
    if (py + ph + 6 + h <= F.h - 6) { slot.info.place(across, py + ph + 6); return; }
    const top = Math.max(8, Math.min(py + ph / 2 - h / 2, F.h - 6 - h));
    if (px + pw + 8 + W <= F.w - 6) { slot.info.place(px + pw + 8, top); return; }
    slot.info.place(Math.max(6, px - 8 - W), top);
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
    view.gold.SetStateText(M.game.treasury() < 0 ? `[[col:red]]${M.game.treasury()}[[/col]]` : String(M.game.treasury()));      // the game's treasury may be in debt
    if (view.sheets) {
        const rule = view.sheets.find(r => !r.part || M.stage(r.part) === r.stage);
        view.sheet.SetImagePath(LAYOUTS + rule.sheet + '.png', 0);
    }
    for (const [part, layers] of Object.entries(view.layers)) {
        const stage = M.stage(part);
        for (const s of ['pencil', 'build', 'ink']) if (layers[s]) layers[s].SetVisible(s === stage);
        const st = stage === 'build' ? [...(M.parts[part].building ? [M.prefix + M.parts[part].building] : []), ...M.part_openers(part)].map(k => M.status(k)).find(x => x.state === 'building') || {} : {};
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
        // beside the plan; with the crew's choice open, over the plan at the drawing's edge, where the choice is not
        if (!view.side.tip_home) view.side.tip_home = [view.side.tip.x, view.side.tip.y];
        const op = openArea(view), tip = view.side.tip, home = view.side.tip_home;
        const pickOpen = !!op && home[0] < op.pick.x + op.pick.Width() && home[0] + tip.Width() > op.pick.x && home[1] < op.pick.y + op.pick.Height() && home[1] + tip.Height() > op.pick.y;
        if (pickOpen) at(view.side.tip, 6, view.side.plan.y - 6 - view.side.tip.Height()); else at(view.side.tip, view.side.tip_home[0], view.side.tip_home[1]);
        // only the empty side glows: the place Malakai can be moved to
        for (const [s, g] of Object.entries(view.side.glows)) g.SetVisible(hint && s !== side);
        view.side.near.SetVisible(ready && side === 'left');
        view.side.far.SetVisible(ready && side === 'right');
        view.side.near_build.SetVisible(false);
        view.side.far_build.SetVisible(false);
    }
    for (const c of Object.values(view.crewAreas || {})) refreshCrewArea(view, M, c);
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
            // the name and one line of state right over the commands; what the building gives is in its information window, on hover
            at(view.selName, 14, view.order.button.y - 56);
            at(view.selMeta, 14, view.order.button.y - 28);
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
    if (view.tree) { view.detail.SetVisible(false); view.lines.SetVisible(false); }
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
    } else if (id.startsWith(CREW_AREA)) {
        // one choice open at a time: the tag of another group closes the one that was open
        const c = view.crewAreas[id.slice(CREW_AREA.length)];
        const was = c && c.open;
        for (const x of Object.values(view.crewAreas)) x.open = false;
        if (c) c.open = !was;
    } else if (id.startsWith(CREW_CLOSE)) {
        const c = view.crewAreas[id.slice(CREW_CLOSE.length)];
        if (c) c.open = false;
    } else if (id.startsWith(CREW_PICK)) {
        // the window stays: the card, the captions, the foot line and the treasury answer every click at once; it closes by its cross or the tag
        const [group, option] = id.slice(CREW_PICK.length).split(':');
        if (view.crewAreas[group] && option) M.set_crew(group, option);
    } else if (id.startsWith('mtb_crew_pick_')) {
        // a window's own backing
    } else if (id === 'scheme') {
        for (const x of Object.values(view.crewAreas || {})) x.open = false;
    } else if (id === 'mtb_tree_expand') {
        if (view.pan) view.pan.expand();
    } else if (id === 'mtb_tree_fit') {
        if (view.pan) view.pan.toggle();
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
