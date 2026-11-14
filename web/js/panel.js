// The airship screen «Дух Грунгни»: one panel of the game's size (1560 x 870 units on every root of 1600 x 900 and larger) with two tabs, as the
// game's full screen panels have them:
//   «Корабль»    the drawing at the full height of the panel (about one unit a pixel of the drawing): the details the buildings bring, the five crew
//                places with their tags and choices, Malakai's side;
//   «Постройки»  the tree of buildings of the constructor's file (web/data/tree_design.json) at the game's size, its whole width in a window scrolled
//                up and down by the wheel, a drag or the game's scroll bar; in the width the tree leaves free (1482 - 1167 units on the author's tree) a
//                column with the ship as it stands now, small (the same drawing, live: its layers and stages as on «Корабль»), and its five crew places.
// Why the ship is small there and whole only on its tab (measured on the author's tree, 1167 x 2138 units): the drawing is held by the panel's
// height, 1021 x 746 at the full height; the tree and the full drawing side by side need 2188 of the 1528 there are. The small ship (300 wide) shows
// what each building did to the ship the turn it was built (the new detail glows, «Корабль» gets the game's mark of something new), a click on it
// opens «Корабль».
// A slot acts as the game's horde slot (building_frame.twui.xml: ContextCommandLeftClick = IssueCommandForBuildingBrowser): a click orders a
// building that can be built and cancels one under construction; a built one shows the game's round demolish button over it (building_browser.twui.xml,
// options_list > button_raze). Every state is on the slot itself; what a building is and why it cannot be built yet is in the game's building
// information window beside it, on hover. The foot row: the last thing that happened, and on the tree's tab «Всё дерево» / «Вблизи».
// Built as build() of src/tww3_mtb_crew_ui.lua would be: the same root, sizes and offsets, so the numbers carry over to the game.
// Reads only the module (web/js/barge_buildings.js); a click calls it, refresh() reads it back.

import {turnsText} from './barge_buildings.js';
import {linkSegments, slotsBlock, lineMarks, slotCards, GRID} from './tree_model.mjs';
import * as FX from './effects_model.mjs';
import {crewSources, crewAmmo, ammoShare} from './crew_model.mjs';
import {clearTooltip} from './gameui.js';

const LAYOUTS = 'ui/tww3_mtb/';
const WEB_ART = LAYOUTS + 'web/';       // the stage layers; in the game they would be ui/tww3_mtb/<name>.png like the others
const DEMOLISH = 'mtb_ship_demolish', TAB = 'mtb_tab_', FIT = 'mtb_tree_fit';
const SIDE = 'mtb_side_';
const EDGE_IN = 4, TAG_GAP = 3;     // the drawing's brass edge reaches 4 units into the sheet; a tag keeps 3 more from it (makeCrewArea)
const CREW_AREA = 'mtb_crew_area_', CREW_PICK = 'mtb_crew_card_pick_', CREW_CLOSE = 'mtb_crew_close_';

// helpers as in the Lua
function make(parent, id, layout) { return parent.CreateComponent(id, layout); }
function size(c, w, h) { c.Resize(Math.floor(w + 0.5), Math.floor(h + 0.5)); }
function at(c, x, y) { c.SetDockOffset(Math.floor(x + 0.5), Math.floor(y + 0.5)); }
function image(parent, id, path, x, y, w, h) { const c = make(parent, id, 'image'); c.SetImagePath(path, 0); size(c, w, h); at(c, x, y); return c; }
function text(parent, id, layout, x, y, w, h, value) { const c = make(parent, id, layout); size(c, w, h); at(c, x, y); c.SetStateText(value || ''); return c; }
// a line of text that may be longer than its box: cut at a word with "…", the whole of it in the tooltip (uic:TextDimensions)
function fitLine(c, value) {
    c.SetStateText(value);
    c.SetTooltipText('', true);
    if (!value || c.TextDimensions()[0] <= c.Width()) return;
    let lo = 0, hi = value.length;
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        c.SetStateText(value.slice(0, mid).replace(/[\s,.:;]+\S*$/, '') + '…');
        if (c.TextDimensions()[0] <= c.Width()) lo = mid; else hi = mid - 1;
    }
    c.SetStateText(value.slice(0, lo).replace(/[\s,.:;]+\S*$/, '') + '…');
    c.SetTooltipText(value, true);
}

// The title plate: the game's panel_title_large.png at its own proportions, 769 x 69 (squashed to 62 its dark field was 30 units tall, less than the
// ink of a 32 unit word with descenders: «Д» and «у» ran over its lower brass, and the text, centred by its line box, sat 8 units low). Its parts in the
// picture's pixels: the plate as seen 84..685 across and 10..56 down, the dark field 211..558 across and 15..49 down.
// The plate and its text are one component: the plate as large as the room allows (at most the picture's size), the text in its dark field MARGIN
// units clear of every edge, the ink centred there (not the line box: CSS centres the line, and a font's ascent is not its descent), in the layout's
// size or smaller when the field is too small for it, so the text can never outgrow the plate. cx, cy: the centre of the plate as seen; half: the
// room on each side of cx. GAME: the same offsets, measured once on the game's header font (src/tww3_mtb_crew_ui.lua has no ink measure).
export const TITLE_PLATE = {path: 'ui/skins/wh_main_dwf_dwarfs/panel_title_large.png', w: 769, h: 69, seen: [84, 10, 685, 56], field: [211, 15, 558, 49], margin: 2};
export function titlePlate(parent, cx, cy, half, value) {
    const P = TITLE_PLATE, k = Math.max(0.05, Math.min(1, 2 * half / (P.seen[2] - P.seen[0])));
    const plate = image(parent, 'title_back', P.path, cx - (P.seen[0] + P.seen[2]) / 2 * k, cy - (P.seen[1] + P.seen[3]) / 2 * k, P.w * k, P.h * k);
    const kx = plate.Width() / P.w, ky = plate.Height() / P.h;
    const f = {l: plate.x + P.field[0] * kx, r: plate.x + P.field[2] * kx, t: plate.y + P.field[1] * ky, b: plate.y + P.field[3] * ky};
    const title = make(parent, 'title', 'text_title');
    title.SetStateText(value);
    const roomW = f.r - f.l - 2 * P.margin, roomH = f.b - f.t - 2 * P.margin;
    let s = title.TextSize();
    for (let i = 0; i < 8; i++) {
        title.SetTextSize(s);
        const ink = title.InkDimensions();
        const iw = ink.right - ink.left, ih = ink.ascent + ink.descent;
        if (iw <= roomW + 0.01 && ih <= roomH + 0.01) break;
        s = Math.max(1, Math.floor(s * Math.min(roomW / iw, roomH / ih) * 10) / 10 - 0.1 * i);      // the ink grows with the size; a step more if rounding left it over
    }
    const ink = title.InkDimensions();
    // the box: across the field, the plate's height; moved so the ink's centre is the field's. Centred, the line starts at the box's centre less
    // half its advance and its ink's centre is (left + right) / 2 after that; the baseline lies (font ascent - font descent) / 2 under the box's
    // centre and the ink's centre (descent - ascent) / 2 under the baseline.
    const bw = f.r - f.l, bh = plate.Height();
    size(title, bw, bh);
    at(title, (f.l + f.r) / 2 - bw / 2 - ((ink.left + ink.right) / 2 - ink.w / 2), (f.t + f.b) / 2 - bh / 2 - (ink.fontAscent - ink.fontDescent) / 2 - (ink.descent - ink.ascent) / 2);
    return {plate, text: title, field: f};
}

// Numbers as the game's Russian texts write them: the percent sign close to the number («+15%», local_ru has no «+15 %»), a decimal comma («16,6»)
export const gameText = s => String(s ?? '').replace(/(\d) %/g, '$1%').replace(/(\d)\.(\d)/g, '$1,$2');
const num = v => gameText(String(v));

// keep: what a screen built again takes over from the one before (the tab, the tree's place and zoom)
export function makePanel(root, M, data, art, blueprint, flags, cards = {}, keep = {}) {
    const view = {layers: {}, selected: null, options: null, crew: [], data, cards, tab: keep.tab === 'ship' ? 'ship' : 'tree'};
    const W = root.Width(), H = root.Height();
    const panel_w = Math.min(W - 40, 1560), panel_h = Math.min(H - 30, 870);
    const pad = 16, top = 66, foot_h = 46;
    // the working area of both tabs: under the title row, over the foot row
    const area = {x: pad, y: top, w: panel_w - 2 * pad, h: panel_h - top - foot_h - 12};
    // the drawing: the area's height (its width when the area is the narrower), in the middle across
    let scheme_h = area.h, scheme_w = scheme_h * data.art.size[0] / data.art.size[1];
    if (scheme_w > area.w) { scheme_w = area.w; scheme_h = scheme_w * data.art.size[1] / data.art.size[0]; }
    const scale = scheme_w / data.art.size[0];

    const backdrop = make(root, 'mtb_ship_panel', 'backdrop');
    size(backdrop, W, H);
    backdrop.MoveTo(0, 0);
    backdrop.SetInteractive(true);      // a click beside the panel only closes what is open (click())
    const frame = make(root, 'frame', 'frame');     // in the game a child of the backdrop, docked at its centre (SetDockingPoint(5)); here placed at the same spot
    size(frame, panel_w, panel_h);
    at(frame, (W - panel_w) / 2, (H - panel_h) / 2);
    frame.SetInteractive(true);         // a click on the panel's bare ground: the same
    view.frame = frame;
    view.area = area;
    // The panel's ground inside its brass border: the game's panel_back_tile.png as one piece (its rounded edge is the picture's own, 9-slice), not
    // repeated (repeated it made a row of black plates under the title row and the foot row)
    const ground = make(frame, 'panel_back', 'panel_ground');
    size(ground, panel_w - 16, panel_h - 16);
    at(ground, 8, 8);
    ground.SetPassive();

    // the title row: the treasury on the left, the name in the middle, the two tabs and the cross on the right, none over another
    const close_w = 34, tab_w = 160, tab_gap = 6, tabs_w = 2 * tab_w + tab_gap;
    const tabs_x = panel_w - 14 - close_w - 14 - tabs_w;
    // the name on its plate, centred on the panel between the treasury (its box ends at 54 + 160) and the tabs, 8 units clear of each
    view.title = titlePlate(frame, panel_w / 2, 33, Math.min(panel_w / 2 - (54 + 160 + 8), tabs_x - 8 - panel_w / 2), '«Дух Грунгни»');
    const close = image(frame, 'mtb_ship_close', 'ui/skins/default/icon_cross.png', panel_w - 14 - close_w, 14, close_w, close_w);
    close.SetTooltipText('Закрыть', true);
    // the treasury, in the corner: in the game the same number is in the HUD's top bar too
    image(frame, 'gold_icon', 'ui/skins/default/icon_treasury.png', 22, 18, 26, 26);
    view.gold = text(frame, 'gold', 'text_head', 54, 14, 160, 34, '');
    view.gold.SetTooltipText('Казна фракции', true);
    view.tabs = {};
    [['ship', 'Корабль'], ['tree', 'Постройки']].forEach(([k, label], i) => { view.tabs[k] = makeButton(frame, TAB + k, tabs_x + i * (tab_w + tab_gap), 11, tab_w, 44, label); });
    // «Корабль» after a building changed the ship, until the player looks at it: a soft warm glow round the tab's own plate (the same glow as a new
    // detail's: GAME the tab's glow state) and the game's mark of something new on the tab's corner (icon_alert_message.png); M.ship_unseen.
    // The glow hugs the plate (6 units at most round it), so the title row's edge under the tabs never cuts it.
    const shipTab = view.tabs.ship.button;
    view.tabGlow = {on: false, SetVisible(on) { this.on = !!on; shipTab.SetGlow(this.on, 'soft'); }, Visible() { return this.on; }, el: shipTab.el};
    view.tabMark = image(view.tabs.ship.button, 'new_mark', 'ui/skins/default/icon_alert_message.png', tab_w - 26, 2, 24, 24);
    view.tabMark.SetPassive();

    // the working area's stone, one for both tabs (the panel's own tile is a pattern of dark blocks, not a ground for a drawing or a tree)
    view.pane = make(frame, 'work_pane', 'tree_pane');
    size(view.pane, area.w, area.h);
    at(view.pane, area.x, area.y);
    // «Корабль»: the drawing and its layers: pencil, hatching, ink per part, all created, one visible (SetVisible), as the panel's mount_ and occ_ layers
    const sx = area.x + (area.w - scheme_w) / 2, sy = area.y + (area.h - scheme_h) / 2;
    const sheet = image(frame, 'scheme', LAYOUTS + blueprint.sheet + '.png', sx, sy, scheme_w, scheme_h);
    sheet.SetInteractive(true);         // a click on the bare drawing closes an open choice (click())
    view.sheet = sheet;
    view.sheets = blueprint.sheets || null;     // rules: the first whose part is at its stage gives the whole drawing
    const place = (name) => art.places[name] || data.art.layers[name];
    view.layers = drawingLayers(sheet, data, art, blueprint, flags, scale);
    // the turns left, live text on the drawing while it is built (TurnsToCompletion in the game), on a small parchment plate so it reads over the
    // hatching; over every layer
    for (const [part, layers] of Object.entries(view.layers)) {
        const spec = blueprint.parts[part];
        layers.turns = text(sheet, `${part}_turns`, 'text_ink', spec.turns_at[0] * scale, spec.turns_at[1] * scale, 110, 28, '');
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
            const size_ = ms.mark * glow.size, off = (size_ - ms.mark) / 2;
            const holder = image(sheet, 'side_glow_' + s, WEB_ART + 'glow_0.png', (ms.marks[s][0] - off) * scale, (ms.marks[s][1] - off) * scale, size_ * scale, size_ * scale);
            holder.SetPassive();
            holder.phases = [];
            for (let i = 1; i < glow.phases; i++) {
                const ph = image(holder, 'phase_' + i, WEB_ART + `glow_${i}.png`, 0, 0, size_ * scale, size_ * scale);
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
        view.side.demo = demoTip(sheet, 'side_demo_tip', (ms.plan[0] + ms.plan[2] + 12) * scale, (ms.plan[1] + ms.plan[3]) * scale, {movie: 'side_demo', head: 'Борт Малакая',
            text: 'С какого борта Малакай ведёт огонь. Борт можно сменить и позже, между боями.'});
        view.side.tip = view.side.demo.tip;
        view.side.video = view.side.demo.video;
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
    view.sheetFrame = make(frame, 'scheme_frame', 'frame_edge');
    size(view.sheetFrame, scheme_w + 8, scheme_h + 8);
    at(view.sheetFrame, sx - 4, sy - 4);

    // «Постройки»: the tree in its window over the whole working area
    view.demolishShown = !!(flags.full || blueprint.demolish);
    view.blueprint = blueprint;
    view.flags = flags;
    view.art = art;
    makeFileTree(frame, view, M, area, keep.pan);
    view.paneEdge = make(frame, 'work_pane_edge', 'frame_edge');     // the same brass edge as round the drawing
    size(view.paneEdge, area.w + 8, area.h + 8);
    at(view.paneEdge, area.x - 4, area.y - 4);

    // the foot row: the last thing that happened (one line, the whole of it in the tooltip when it is longer), and the tree's zoom on the right
    const foot_y = area.y + area.h + 6, fit_w = 210, foot_hh = 40;
    const strip = make(frame, 'foot_strip', 'foot_strip');
    size(strip, area.w, foot_hh);
    at(strip, area.x, foot_y);
    view.fitBtn = makeButton(frame, FIT, area.x + area.w - fit_w - 2, foot_y + 2, fit_w, foot_hh - 4, 'Всё дерево');
    view.message = text(frame, 'message', 'text_copper', area.x + 14, foot_y, area.w - fit_w - 40, foot_hh, '');

    view.root = backdrop;
    view.frame = frame;
    view.scale = scale;
    view.area = area;
    return {view, refresh: () => refresh(view, M), click: (c) => click(view, M, c), escape: () => { const done = escape(view); if (done) refresh(view, M); return done; }};
}

// ---------------- the drawing's layers, one rule for the big drawing and the small one ----------------
// Every part's pencil, hatching and ink, each a layer over the sheet (one shown at a time, SetVisible). The stages are three holders, one over the
// other: every pencil under every hatching under every ink, so a detail not built yet is never drawn over one that stands. -> {part: {pencil, build, ink}}
function drawingLayers(sheet, data, art, blueprint, flags, scale, idp = '') {
    const place = name => art.places[name] || data.art.layers[name];
    // a layer of the panel's own art (data/crew_ui_art.json: mount_cannons, mount_bombs) or of tools/web_art.py
    const layerPath = name => (data.art.layers[name] ? LAYOUTS : WEB_ART) + name + '.png';
    const holders = {};
    for (const stage of ['pencil', 'build', 'ink']) {
        holders[stage] = make(sheet, idp + stage + '_layers', 'layer_holder');
        size(holders[stage], sheet.Width(), sheet.Height());
        holders[stage].SetPassive();
    }
    const out = {};
    for (const [part, spec] of Object.entries(blueprint.parts)) {
        if (!spec.enabled && !flags.all_parts) continue;      // only the data is ready: the base drawing has nothing of it
        const layers = {};
        for (const stage of ['pencil', 'build', 'ink']) {
            const name = spec[stage];
            if (!name) continue;                               // not drawn yet
            const p = place(name);
            layers[stage] = image(holders[stage], `${idp}${part}_${stage}`, layerPath(name), p[0] * scale, p[1] * scale, p[2] * scale, p[3] * scale);
            layers[stage].SetPassive();
        }
        out[part] = layers;
    }
    return out;
}
// the sheet of the whole drawing (blueprint.json, sheets: the first rule whose part is at its stage) and each part's layer at its stage
function paintDrawing(sheet, sheets, layers, M) {
    if (sheets) {
        const rule = sheets.find(r => !r.part || M.stage(r.part) === r.stage);
        sheet.SetImagePath(LAYOUTS + rule.sheet + '.png', 0);
    }
    for (const [part, l] of Object.entries(layers)) {
        const stage = M.stage(part);
        for (const s of ['pencil', 'build', 'ink']) if (l[s]) l[s].SetVisible(s === stage);
    }
}
// What the turn built glows on the drawing that turn (M.ship_news): the new detail's ink; a new sheet (the barge itself) the whole drawing.
// GAME: the layer's glow state (the picture again under it, additive, a little larger).
function paintNews(sheet, layers, M) {
    const news = M.ship_news(), parts = news ? news.parts : [];
    for (const [part, l] of Object.entries(layers)) if (l.ink) l.ink.SetGlow(parts.includes(part));
    sheet.SetGlow(parts.some(p => !layers[p] || !layers[p].ink));
}
// What a crew place shows on the drawing (the same for the big drawing and the small one): nobody there, a kind that stands, a kind on its way as
// a sketch; the detail the crew takes the place of (the nests' lookouts) hidden while someone is there or coming. set: {empty, layers, sketches}
function paintCrewLayers(set, M, g, hides) {
    const {place, now, nobody, coming} = crewState(M, g);
    if (set.empty) set.empty.SetVisible(place && nobody && !coming);
    for (const [key, layer] of Object.entries(set.layers)) layer.SetVisible(place && !nobody && key === now);
    for (const [key, layer] of Object.entries(set.sketches)) layer.SetVisible(place && key === coming);
    if (hides && hides.ink && place && (!nobody || coming)) hides.ink.SetVisible(false);
}

// ---------------- the ship beside the tree ----------------
// The column the tree leaves free on «Постройки»: the ship as it stands now, the whole drawing small (the same layers and stages as «Корабль»,
// live, not a picture of it), in the panel's brass edge; under it the five crew places, a row each (the army panel's small card of what stands
// there, the place's name as its tag writes it, its state in a line). A click on the ship opens «Корабль»; a click on an open place opens its
// choice there. x, y, w: the column's box on the tree's page.
function makeShipColumn(view, M, data, art, blueprint, flags, parent, x, y, w, h) {
    const k = w / data.art.size[0], sh = Math.round(data.art.size[1] * k);
    const col = {x, y, w, h, k};
    const sheet = image(parent, 'mtb_mini_ship', LAYOUTS + blueprint.sheet + '.png', x, y, w, sh);
    sheet.SetInteractive(true);
    sheet.SetHoverBrighten(0.12);
    sheet.SetTooltipText('Открыть вкладку «Корабль»', true);
    col.sheet = sheet;
    col.layers = drawingLayers(sheet, data, art, blueprint, flags, k, 'mini_');      // ids of their own: the big drawing's are unique
    const place = name => art.places[name] || data.art.layers[name];
    const lay = (holder, name) => { const q = place(name); if (!q) return null; const c = image(holder, 'mini_' + name, WEB_ART + name + '.png', q[0] * k, q[1] * k, q[2] * k, q[3] * k); c.SetPassive(); return c; };
    // the crews in ink and the hires on their way, over the details (as on the big drawing); no tags: at this size they would not read
    const crewHolder = make(sheet, 'mini_crew', 'layer_holder');
    size(crewHolder, w, sh);
    crewHolder.SetPassive();
    col.crew = {};
    for (const spec of blueprint.crew_areas || []) {
        const g = spec.group, group = data.groups[g];
        if (!group || !(art.crew_areas || {})[g]) continue;
        const set = {spec, empty: art.places[`crew_${g}_empty`] ? lay(crewHolder, `crew_${g}_empty`) : null, layers: {}, sketches: {}};
        const emptyKey = group.mount || group.start;
        for (const key of Object.keys(group.options)) {
            if (key !== emptyKey && art.places[`crew_${g}_${key}`]) set.layers[key] = lay(crewHolder, `crew_${g}_${key}`);
            if (art.places[`crew_${g}_${key}_sketch`]) set.sketches[key] = lay(crewHolder, `crew_${g}_${key}_sketch`);
        }
        col.crew[g] = set;
    }
    // Malakai on his side (the near side in ink, the far side in pencil), as on the big drawing
    col.malakai = {near: art.places.malakai_near ? lay(crewHolder, 'malakai_near') : null, far: art.places.malakai_far ? lay(crewHolder, 'malakai_far') : null};
    col.edge = make(parent, 'mtb_mini_ship_edge', 'frame_edge');
    size(col.edge, w + 8, sh + 8);
    at(col.edge, x - 4, y - 4);
    // the five places: a row each, under the ship
    const rowsY = y + sh + 18, rowH = 64;
    col.head = text(parent, 'mini_crew_head', 'text_head', x, rowsY, w, 32, 'Экипаж');
    const rule = make(parent, 'mini_crew_rule', 'separator_skull');
    size(rule, w, 14);
    at(rule, x, rowsY + 32);
    col.rows = {};
    (blueprint.crew_areas || []).filter(s => data.groups[s.group]).forEach((spec, i) => {
        const g = spec.group, ry = rowsY + 52 + i * rowH;
        const hit = make(parent, 'mtb_mini_crew_' + g, 'hit_area');
        size(hit, w, rowH - 4);
        at(hit, x, ry);
        hit.SetInteractive(true);
        hit.SetHoverBrighten(0.15);
        const row = {g, hit};
        row.card = image(hit, 'card', LAYOUTS + 'card_empty.png', 4, 4, CARD_W, CARD_H);
        row.frame = image(row.card, 'frame', 'ui/skins/default/unit_card_build_frame.png', 0, 0, CARD_W, CARD_H);
        row.padlock = image(hit, 'padlock', 'ui/skins/default/padlock.png', 4 + (CARD_W - 16) / 2, 4 + 15, 16, 20);
        row.waiting = image(row.card, 'waiting', 'ui/skins/default/icon_hourglass.png', CARD_W - 15, CARD_H - 17, 16, 16);
        row.name = text(hit, 'name', 'text_name', 38, 2, w - 42, 28, M.place_name(g));
        row.state = text(hit, 'state', 'text_caption_left', 38, 30, w - 42, 24, '');
        for (const c of [row.card, row.frame, row.padlock, row.waiting, row.name, row.state]) c.SetPassive();
        col.rows[g] = row;
    });
    return col;
}
function paintShipColumn(view, M, col) {
    paintDrawing(col.sheet, view.sheets, col.layers, M);
    for (const [g, set] of Object.entries(col.crew)) paintCrewLayers(set, M, g, set.spec.hides_part && col.layers[set.spec.hides_part]);
    const side = M.malakai_side(), bp = view.blueprint, ready = !bp.malakai_side || !bp.malakai_side.show_when || M.stage(bp.malakai_side.show_when) === 'ink';
    if (col.malakai.near) col.malakai.near.SetVisible(ready && side === 'left');
    if (col.malakai.far) col.malakai.far.SetVisible(ready && side === 'right');
    paintNews(col.sheet, col.layers, M);
    const newsPlaces = M.news_places();         // opened by the turn, or a new kind in a place already open
    for (const [g, row] of Object.entries(col.rows)) {
        const st = crewState(M, g), w = M.crew_words(g);
        const opener = M.place_opener(g);
        const shown = st.stand ? st.standing : st.coming ? st.ordered : null;
        row.card.SetImagePath(shown && shown.unit_card ? shown.unit_card.picture : LAYOUTS + 'card_empty.png', 0);
        row.card.ShaderTechniqueSet(st.place ? 'normal_t0' : 'set_greyscale_t0');
        row.card.SetImageColour(255, 255, 255, !st.place ? 0x80 : st.coming ? 0x8C : 255);
        row.padlock.SetVisible(!st.place);
        row.waiting.SetVisible(!!st.ordered);
        // the place the turn's building opened, or gave a new kind, glows that turn, its name in the game's gold (M.news_places)
        const fresh = newsPlaces.includes(g);
        row.card.SetGlow(fresh);
        row.name.SetStateText(!st.place ? `[[col:grey]]${M.place_name(g)}[[/col]]` : fresh ? `[[col:yellow]]${M.place_name(g)}[[/col]]` : M.place_name(g));
        const line = !st.place ? `[[col:grey]]${opener ? `Откроет «${opener.name}»` : 'Закрыто'}[[/col]]`
            : st.ordered ? (st.ordered.empty ? `${w.who} ${w.leave} в начале хода` : `${st.ordered.name}: ${w.come} в начале хода`)
            : st.nobody ? `[[col:grey]]${w.nobody}[[/col]]` : st.standing.name;
        fitLine(row.state, line);
        row.hit.SetTooltipText(row.state.GetStateText() !== line ? line : '', true);
    }
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
    // The tag (with its leaders and its pulse) clear of the drawing's brass edge: the edge (frame_edge round the sheet, 4 units out) draws its line and
    // shadow 4 units into the sheet, and the nests' tag is drawn at the sheet's very top (web/art/layers.json: y 1.25), where the line cut its top
    // border. Moved in by what it lacks of EDGE_IN + TAG_GAP on any side; its leaders' dots still end on the lookouts.
    const tq = place(`crew_${g}_tag_plus`);
    const clear = EDGE_IN + TAG_GAP, tx0 = tq[0] * scale, ty0 = tq[1] * scale, tx1 = tx0 + tq[2] * scale, ty1 = ty0 + tq[3] * scale;
    const tdx = Math.max(0, clear - tx0) - Math.max(0, tx1 - (scheme_w - clear)), tdy = Math.max(0, clear - ty0) - Math.max(0, ty1 - (scheme_h - clear));
    const shift = name => (/_tag_/.test(name) ? [tdx, tdy] : [0, 0]);
    const lay = name => { const q = place(name), [dx, dy] = shift(name); const c = image(area, name, WEB_ART + name + '.png', q[0] * scale - ax + dx, q[1] * scale - ay + dy, q[2] * scale, q[3] * scale); c.SetPassive(); return c; };
    const crew = {spec, area, group: g, layers: {}, open: false};
    // the pulse first, under the tag: one picture a phase, switched by a timer (GAME: SetState by core:get_tm():repeat_real_callback, as the side's)
    const gl = a.glow, prefix = gl.prefix || 'crew_glow';
    crew.glow = image(area, 'crew_glow', WEB_ART + `${prefix}_0.png`, gl.box[0] * scale - ax + tdx, gl.box[1] * scale - ay + tdy, gl.box[2] * scale, gl.box[3] * scale);
    crew.glow.SetPassive();
    crew.glow.el.style.zIndex = 1;      // over the drawing's brass edge: a tag at the sheet's top (the nests') keeps its whole halo
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
    const inHover = name => { const q = place(name), [dx, dy] = shift(name); return image(crew.hover, name, WEB_ART + name + '.png', q[0] * scale - ax + dx, q[1] * scale - ay + dy, q[2] * scale, q[3] * scale); };
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
    const pad = 26, slot_w = 106, ph = pad + 32 + 4 + UNIT_H + 4 + 42 + 24 + 26;
    let pw = Math.max(pad * 2 + slot_w * options.length, 440);
    const below = ay + cbox[3] * scale + 14, above = ay - 14 - ph;
    const py = below + ph <= scheme_h - 6 ? below : above >= 6 ? above : Math.max(6, scheme_h - ph - 6);
    const pick = image(sheet, 'mtb_crew_pick_' + g, LAYOUTS + 'backdrop.png', 0, py, pw, ph);
    pick.SetInteractive(true);      // a click on the window itself does nothing and does not reach the drawing
    pick.SetLayer('click');
    crew.pick = pick;
    crew.head = text(pick, 'pick_head', 'text_head', pad, pad - 4, pw - 2 * pad - 34, 32, spec.head || group.name);
    // the window as wide as its head too (the head in the game's header size, the cross clear of it)
    pw = Math.max(pw, crew.head.TextDimensions()[0] + 2 * pad + 34 + 8);
    size(pick, pw, ph);
    size(crew.head, pw - 2 * pad - 34, 32);
    at(pick, Math.max(6, Math.min(ax, scheme_w - pw - 12)), py);
    const cross = image(pick, CREW_CLOSE + g, 'ui/skins/default/icon_cross.png', pw - pad - 24, pad - 2, 22, 22);
    cross.SetInteractive(true);
    // A slot is the whole column of a kind (the card and its caption), one beside the other with no gap: the mouse goes from kind to kind without
    // leaving them, so the unit's panel beside the choice does not blink. Everything a card has to say is on the card, in the game's own marks
    // (ui/common ui/land_unit_card.twui.xml), and only its name under it:
    //   a kind one can hire   the recruitment card: the cost on the plate at the top, red when the treasury cannot pay it
    //   the kind in hire      the card's queued state: the picture and the frame at 100 of 255, the banner with the hourglass and the turns
    //   the kind that stands  the army panel's card of a unit one has: the men over the green bar, the frame of the selected card
    //   a kind not opened     the locked state: grey, the padlock
    const slot_y = pad + 32 + 4, slot_h = UNIT_H + 4 + 42;
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
//   building_information_holder   tooltip_frame.png, margins 15: nothing is written in that edge
//   dy_title                      at 0, 1; 400 x 38; header_14 centred, text offsets 10 / 10 across, 12 above, 8 below
//   hbar                          separator_skull2.png 380 x 14 at 10, 33
//   dy_secondary_title            the chain's name: at 39, 30 tall; body_12 centred, 12 above, 2 below
//   description_window            body_12_italic centred, 24 from either side (clear of the frame's edge), 12 above and below, at least 52 tall
//   effects_list                  building_info_generic_entry.twui.xml per effect: the icon 24 x 24 at 18, the text from 48 to 18 before the edge;
//                                 every entry of the window (an effect, a block's title, a unit) one rhythm: 5 above its text and 5 below, at least 32,
//                                 the icon's middle on the middle of the text's first line
//   building_info_recruitment_effects.twui.xml ("Unlocks recruitment of:"; here what the building opens in the crew): the title an entry like an
//                                 effect; a unit an entry indented: unit_cat_holder_round.png 26 x 26 at 34, the category icon 22 x 22 in it, the
//                                 name from 64
//   bottom_padding                14
//   instruction                   the reason why the building cannot be built (red), or what a click does (the game's light text), at the window's
//                                 foot under a thin rule: one window, so no seam and no gap between the two
// The game's window has no cost and no time: they stand by the slot (the cost banner; the turns in the panel's line of the selected building).
// The rows of effects and of the crew are made as many as a building has (none is ever dropped) and the description is always whole: a window too
// tall for the room under the title row goes over it (placeInfo); the constructor warns of a window taller than the whole screen (tree_model.mjs, INFO).
const INFO_W = 400, INFO_X = 18, INFO_TX = 48, INFO_UX = 34, INFO_UTX = 64, INFO_ROW = 32, INFO_PAD = 5;
function makeInfoTip(parent, id) {
    const tip = make(parent, id, 'tooltip_frame');
    size(tip, INFO_W, 100);
    const t = {tip, w: INFO_W, effects: [], units: [], id};
    t.title = text(tip, 'dy_title', 'text_info_title', 10, 1 + 2, INFO_W - 20, 38, '');      // 12 above and 8 below the text: its middle 2 under the box's
    t.hbar = make(tip, 'hbar', 'separator_skull');
    size(t.hbar, 380, 14);
    at(t.hbar, 10, 33);
    t.chain = text(tip, 'dy_secondary_title', 'text_info_centre', 18, 39 + 12 - 4, INFO_W - 36, 22, '');   // 30 tall with 12 above and 2 below: 16 left for a line of 22, it sits 4 higher
    t.description = text(tip, 'description_window', 'text_info_italic', 24, 0, INFO_W - 48, 16, '');
    t.opensIcon = image(tip, 'effect_icon', 'ui/skins/default/replenishement_positive.png', INFO_X, 0, 24, 24);
    t.opensTitle = text(tip, 'tx_enables', 'text_info', INFO_TX, 0, INFO_W - INFO_TX - INFO_X, 16, 'Открывает в экипаже:');
    // the game's own block of a building that unlocks units (building_info_recruitment_effects.twui.xml): «Открывает найм:» and the units
    t.armyIcon = image(tip, 'army_effect_icon', 'ui/skins/default/replenishement_positive.png', INFO_X, 0, 24, 24);
    t.armyTitle = text(tip, 'tx_enables_army', 'text_info', INFO_TX, 0, INFO_W - INFO_TX - INFO_X, 16, 'Открывает найм:');
    t.army = [];
    // the foot: the reason or what a click does, under a thin rule of the frame's colour
    t.rule = make(tip, 'instruction_rule', 'info_rule');
    size(t.rule, INFO_W - 2 * INFO_X, 1);
    t.reason = text(tip, 'reason', 'text_info', INFO_X + 2, 0, INFO_W - 2 * INFO_X - 4, 16, '');
    tip.SetLayer('hover');
    tip.SetVisible(false);
    return t;
}
function infoRows(t, effects, units, army = 0) {
    const D = 'ui/skins/default/';
    const unitRow = (key, i) => {
        const holder = image(t.tip, key + '_cat_frame_' + i, D + 'unit_cat_holder_round.png', INFO_UX, 0, 26, 26);
        return {holder, icon: image(holder, 'unit_category_icon', D + 'replenishement_positive.png', 2, 2, 22, 22), name: text(t.tip, key + '_name_' + i, 'text_info', INFO_UTX, 0, INFO_W - INFO_UTX - INFO_X, 16, '')};
    };
    while (t.army.length < army) t.army.push(unitRow('army', t.army.length));
    while (t.effects.length < effects) {
        const i = t.effects.length;
        t.effects.push({icon: image(t.tip, 'effect_icon_' + i, D + 'replenishement_positive.png', INFO_X, 0, 24, 24), text: text(t.tip, 'effect_' + i, 'text_info', INFO_TX, 0, INFO_W - INFO_TX - INFO_X, 16, '')});
    }
    while (t.units.length < units) t.units.push(unitRow('unit', t.units.length));
}

// Fills the window and stacks its blocks as the template's lists do. content: {title, chain, description, effects: [{icon, text, good}],
// opens: [{category, text}], army: [{category, text}], reason, note, maxH}. Returns the height of the whole.
function fillInfoTip(t, content) {
    const tall = c => c.TextDimensions()[1];
    const put = (c, x, y) => { at(c, x, y); size(c, c.Width(), Math.max(22, tall(c))); };
    const effects = content.effects || [], opens = content.opens || [], army = content.army || [];
    infoRows(t, effects.length, opens.length, army.length);
    // the window's width (400, the game's; wider only for a window that would otherwise be taller than the screen, fillInfo): every block across it
    const W = t.w = content.width || INFO_W;
    size(t.title, W - 20, 38); size(t.hbar, W - 20, 14); size(t.chain, W - 36, 22); size(t.description, W - 48, 16);
    for (const c of [t.opensTitle, t.armyTitle, ...t.effects.map(r => r.text)]) size(c, W - INFO_TX - INFO_X, 16);
    for (const r of [...t.units, ...t.army]) size(r.name, W - INFO_UTX - INFO_X, 16);
    size(t.rule, W - 2 * INFO_X, 1); size(t.reason, W - 2 * INFO_X - 4, 16);
    t.title.SetStateText(content.title || '');
    t.chain.SetStateText(content.chain || '');
    // the foot: why the building cannot be built (red), else what a click does with it (the game's light text)
    const said = content.reason || content.note || '';
    t.reason.SetStateText(content.reason ? `[[col:game_red]]${gameText(content.reason)}[[/col]]` : gameText(said));
    t.rule.SetVisible(!!said); t.reason.SetVisible(!!said);
    const reasonH = said ? 10 + Math.max(22, tall(t.reason)) + 12 : 0;
    // one entry: its icon (or a unit's round holder) with its middle on the middle of the text's first line, the text 5 under the entry's top
    const entry = (icon, iconX, iconH, label, textX, y) => {
        at(icon, iconX, y + INFO_PAD + 11 - iconH / 2);
        put(label, textX, y + INFO_PAD);
        return Math.max(INFO_ROW, INFO_PAD + label.Height() + INFO_PAD);
    };
    const layout = desc => {
        let y = content.chain ? 39 + 30 : 39 - 6;       // the chain's row only when there is a chain's name
        t.chain.SetVisible(!!content.chain);
        t.description.SetStateText(desc);
        t.description.SetVisible(!!desc);
        if (desc) {
            put(t.description, 24, y + 12);
            y += Math.max(52, 12 + tall(t.description) + 12);
        }
        y += 2;
        t.effects.forEach((row, i) => {
            const e = effects[i];
            row.icon.SetVisible(!!e); row.text.SetVisible(!!e);
            if (!e) return;
            row.icon.SetImagePath(e.icon || 'ui/skins/default/replenishement_positive.png', 0);
            row.text.SetStateText(`[[col:${e.good === false ? 'game_red' : 'game_green'}]]${gameText(e.text)}[[/col]]`);
            y += entry(row.icon, INFO_X, 24, row.text, INFO_TX, y);
        });
        const block = (icon, title, list, rows) => {
            icon.SetVisible(!!list.length); title.SetVisible(!!list.length);
            if (list.length) y += entry(icon, INFO_X, 24, title, INFO_TX, y);
            rows.forEach((row, i) => {
                const o = list[i];
                row.holder.SetVisible(!!o); row.name.SetVisible(!!o);
                if (!o) return;
                if (o.category) row.icon.SetImagePath(o.category, 0);
                row.name.SetStateText(gameText(o.text));
                y += entry(row.holder, INFO_UX, 26, row.name, INFO_UTX, y);
            });
        };
        block(t.opensIcon, t.opensTitle, opens, t.units);
        block(t.armyIcon, t.armyTitle, army, t.army);
        return y + 14;
    };
    // always the whole of it: nothing is shortened, no block is dropped (placeInfo finds it room, over the title row when it must)
    let y = layout(content.description || '');
    if (said) {
        at(t.rule, INFO_X, y - 4);
        put(t.reason, INFO_X + 2, y + 6);
        y += reasonH - 4;
    }
    size(t.tip, t.w, y);
    t.h = y;
    t.has_reason = !!said;
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
        row('range', D + 'icon_stat_range.png', 'Дальность', num(ab.range), null);
        if (ab.blast) row('blast', D + 'icon_stat_damage.png', 'Взрыв', `${ab.blast + ab.blast_ap} · ${ab.radius} м`, null);
        row('wind_up', D + 'icon_stat_reload_time.png', 'Замах, с', num(ab.wind_up), null);
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
        else row('range', D + 'icon_stat_range.png', 'Дальность', num(n.range), n.range / best(x => x.range));
        row('reload', D + 'icon_stat_reload_time.png', 'Перезарядка, с', num(n.reload), best(x => x.reload, true) / n.reload);
        // the ammunition: the group's whole, the true number (the mod rounds the whole, crew_model.mjs crewAmmo); under it in small letters its places
        // and a place's share («4 люка по 28», «4 люка, около 65 на люк»); with no seats in the data, the group's whole alone
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
        // the ammunition: the mod's Lua rounds the group's whole (floor(x + 0.5)) and the places share it, so a bonus smaller than a volley a place is
        // not lost (6 a pirate, +15%: 76 for the eleven, about 7 each); the group's whole is the number, the share beside it
        const ammoPct = bonus.ammo ? bonus.ammo.pct : 0, ammo = crewAmmo(n, ammoPct, o.unit_card ? o.unit_card.men : 0);
        info.ammo = ammo;
        if (info.ammoNote) {
            info.rows.ammo.value.SetStateText(colour('ammo', ammoPct, String(ammo.total)));
            info.ammoNote.SetStateText(ammoShare(ammo, spec.area && spec.area.group, spec.area && spec.area.per));
        } else if (info.rows.ammo && !ab) info.rows.ammo.value.SetStateText(colour('ammo', ammoPct, String(ammo.total)));
        for (const kind of ['range', 'reload']) {
            const b = bonus[kind], r = info.rows[kind];
            if (!r || (kind === 'range' && (o.range_text || ab))) continue;
            r.value.SetStateText(colour(kind, b ? b.pct : 0, num(b && b.pct ? FX.applyPct(base[kind], b.pct, kind) : base[kind])));
        }
        if (info.rows.damage && !ab) {
            const b = bonus.damage, d0 = (n.damage + n.ap) * n.shots * n.volley;
            info.rows.damage.value.SetStateText(colour('damage', b ? b.pct : 0, num(b && b.pct ? FX.applyPct(d0, b.pct, 'damage') : d0)));
        }
        const lines = FX.CREW_KINDS.filter(k => bonus[k] && bonus[k].pct && (k !== 'ammo' || n.ammo)).map(k => colour(k, bonus[k].pct,
            gameText(`${FX.KINDS[k].name} ${FX.signedPct(bonus[k].pct, false)}`) + (k === 'ammo' ? ` (${ammo.base} → ${ammo.total})` : '')
            + `: ${bonus[k].from.map(f => f.name).join(', ')}`));
        info.accuracy.SetStateText(lines.join('\n'));
        info.bonusLines = lines;
        const linesH = lines.length ? Math.max(20, info.accuracy.TextDimensions()[1] + 4) : 0;
        size(info.accuracy, W - 28, Math.max(20, linesH));
        info.h = info.base_h + linesH;
        size(panel, W, info.h);
        // a card that stands for the same unit opened for the army too (oneCardPerUnit): the second fact in the same window, in the army panel's words
        const armyLine = spec.army_building ? `«${spec.army_building}» открывает этот отряд и для найма в армию` : '';
        const crewLine = dyn.reason ? `[[col:game_red]]${dyn.reason}[[/col]]` : dyn.state || '';
        info.stateText.SetStateText([crewLine, armyLine].filter(Boolean).join('\n'));
        info.has_state = !!(dyn.reason || dyn.state || armyLine);
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
    const stat = (key, icon, name) => { if (st[key] !== null && st[key] !== undefined) row(key, D + icon, name, num(st[key]), st[key] / best(key)); };
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
        if (st.reload) row('reload', D + 'icon_stat_reload_time.png', 'Перезарядка, с', num(st.reload), Math.min(1, 4 / st.reload));
    }
    y += 10;
    info.h = y;
    size(panel, W, y);
    info.state = make(parent, id + '_state', 'tooltip_instruction');
    const stateText = text(info.state, 'text', 'text_info', 13, 10, W - 23, 22, `Найм в армию открывает постройка «${building}»`);
    info.state_h = 10 + Math.max(22, stateText.TextDimensions()[1]) + 10;
    size(stateText, W - 23, info.state_h - 20);
    size(info.state, W, info.state_h);
    info.total = info.h + info.state_h - 8;
    for (const c of [panel, info.state]) { c.SetLayer('hover'); c.SetPassive(); c.SetVisible(false); }
    info.place = (x, top) => { at(panel, x, top); at(info.state, x, top + info.h - 8); };
    info.hook = owner => { owner.SetHoverChild(panel); owner.AddHoverChild(info.state); };
    return info;
}


// The demo window of a place that shows a clip of the game (Malakai's side): a dark backing (the panel's backdrop picture), the video, a brass head
// and the text in the game's sizes, as tall as its text (uic:TextDimensions; measured again by fit() when it was made while hidden), the panel's frame
// edge over it all. x: its left, bottom: its lower edge. The clip is web/art/<movie>.webm or .mp4, taken when the file is there; until then a placeholder.
// In the game: a frame layout with a movie component (the spell browser's MoviePlayer callback, its loop property).
function demoTip(parent, id, x, bottom, spec) {
    const tw = 300, pad = 14, vw = tw - 2 * pad, vh = Math.round(vw * 9 / 16);
    const tip = image(parent, id, LAYOUTS + 'backdrop.png', x, 0, tw, 100);
    const video = make(tip, 'video', 'movie');
    size(video, vw, vh);
    at(video, pad, pad);
    video.SetMovie(['.webm', '.mp4'].map(ext => '/art/' + spec.movie + ext), 'Здесь будет видео из игры');
    text(tip, 'tip_head', 'text_head', pad, pad + vh + 8, vw, 32, spec.head);
    const body = text(tip, 'tip_text', 'text_body', pad, pad + vh + 8 + 34, vw, 20, spec.text);
    const edge = make(tip, 'tip_edge', 'frame_edge');
    const demo = {tip, video};
    demo.fit = () => {
        const bh = Math.max(20, body.TextDimensions()[1]);
        if (demo.bh === bh) return;
        demo.bh = bh;
        size(body, vw, bh);
        const th = pad + vh + 8 + 34 + bh + pad;
        size(tip, tw, th);
        at(tip, x, bottom - th);
        size(edge, tw, th);
        at(edge, 0, 0);
        demo.home = [x, bottom - th];
    };
    demo.fit();
    tip.SetPassive();
    tip.SetLayer('hover');
    tip.SetVisible(false);
    return demo;
}

// ---------------- the tree of buildings ----------------
// The game's numbers (ui/campaign ui/building_browser.twui.xml): a slot of the tree is 74 x 74 and the arrow between two slots 32 (TreeCallback,
// padding_x / padding_y), so one place of the grid is 106 (tree_model.mjs, GRID). Nothing of the slot is scaled at 1:1.
const NODE = 74, LINE = 3;
const TREE = 'mtb_tree_node_';
// the scroll bars of the game (parchment_slider_vertical / _horizontal: the track slider_*_mid, 6 thick; the arrows 15 x 22; the handle 18 thick,
// 39 at least, its ends kept) and the step of an arrow: one row of the tree
const BAR = 22, ARROW = 22, HANDLE_MIN = 39, STEP = 106;

// The tree of the constructor's file in its window: every node at its own place (col, row of the game's grid of 106, the tree growing up), the lines of
// tree_model.mjs linkSegments (the same as the constructor draws), the small crew cards of what each node opens. The window is the whole working area
// of the tab: the author's tree is narrower than it, so it only scrolls up and down (a drag, the wheel, the bar on the right); a wider tree scrolls
// across too (a drag, shift + the wheel, the bar at the foot). «Всё дерево» shows the whole of it smaller (a click on a slot then comes back to the
// game's size at that slot, it orders nothing), «Вблизи» back. It opens at what can be done now: the slots under construction and those that can be
// ordered.
function makeFileTree(frame, view, M, area, keep) {
    const rows = view.data.tree_rows || [];
    const D = 'ui/skins/default/';
    // the tab's page on the working area's stone: the window and its bars, hidden together on the other tab
    const pane = make(view.pane, 'tree_page', 'tree_page');
    size(pane, area.w, area.h);
    at(pane, 0, 0);
    const c0 = rows.length ? Math.min(...rows.map(r => r.col)) : 0, r1 = rows.length ? Math.max(...rows.map(r => r.row)) : 0;
    const pos = {};
    // 30 above the highest row for the crew cards (22 over the slot); 16 on the left (a line that goes round a slot of the first column takes the
    // lane half a step left of it); right of the last column its cards (17 over the slot's edge) and 4. The holder's (0, 0) is the content's corner.
    for (const r of rows) pos[r.key] = {x: 16 + (r.col - c0) * GRID, y: 30 + (r1 - r.row) * GRID};
    const cw = rows.length ? Math.max(...Object.values(pos).map(p => p.x)) + NODE + 17 + 4 : 0;
    const ch = rows.length ? Math.max(...Object.values(pos).map(p => p.y)) + NODE + 22 + 12 : 0;
    // The window inside the pane's edge with its bars (each only when the tree is larger than the window that way), and right of it the ship's column
    // (makeShipColumn) in the width the tree leaves: 260 to 320 wide; the author's tree (1171 wide) leaves 297.
    const edge = 10, gap = 4, colGap = 14;
    const colW = Math.max(260, Math.min(320, area.w - 2 * edge - BAR - gap - colGap - cw));
    const avail = area.w - 2 * edge - colGap - colW;
    let needV = ch > area.h - 2 * edge, needH = cw > avail - (needV ? BAR + gap : 0);
    needV = ch > area.h - 2 * edge - (needH ? BAR + gap : 0);
    const ww = avail - (needV ? BAR + gap : 0), wh = area.h - 2 * edge - (needH ? BAR + gap : 0);
    const win = make(pane, 'tree_window', 'tree_window');
    size(win, ww, wh);
    at(win, edge, edge);
    win.SetInteractive(true);       // a click on the bare tree closes a slot's options
    const holder = make(win, 'tree_holder', 'tree_holder');
    size(holder, Math.max(1, cw), Math.max(1, ch));
    const pan = view.pan = {x: 0, y: 0, z: 1, win, pane, holder, w: ww, h: wh, cw, ch, needH, needV};
    view.column = makeShipColumn(view, M, view.data, view.art, view.blueprint, view.flags, pane, area.w - edge - colW, edge + 4, colW, wh);
    // The lines: each link its segments (tree_model.mjs linkSegments, the same as the constructor's column), in a holder of their own under the
    // slots, so the whole web can be dimmed while one slot's links are lit (lightLinks). Where two links that belong together meet, a dot; where a
    // vertical crosses a line it has nothing to do with, the horizontal is broken round it (tree_model.mjs lineMarks).
    const lines = make(holder, 'tree_lines', 'layer_holder');
    size(lines, Math.max(1, cw), Math.max(1, ch));
    lines.SetPassive();
    const blocked = slotsBlock(Object.values(pos));
    const links = [];
    for (const r of rows) for (const p of r.requires) if (pos[p]) links.push({from: p, to: r.key, colour: r.branch, segs: linkSegments(pos[p], pos[r.key], blocked)});
    const marks = lineMarks(links);
    const cuts = new Map();       // a horizontal -> the x's where a vertical crosses it
    for (const c of marks.crossings) (cuts.get(c.h) || cuts.set(c.h, []).get(c.h)).push(c.x);
    const BRIDGE = 5;             // the gap each side of the crossing vertical
    let seg = 0;
    const line = (parent, x0, y0, x1, y1, colour) => image(parent, `tree_line_${seg++}`, WEB_ART + (colour ? `tree_line_${colour}.png` : 'tree_line.png'),
        Math.min(x0, x1) - LINE / 2, Math.min(y0, y1) - LINE / 2, Math.abs(x1 - x0) + LINE, Math.abs(y1 - y0) + LINE);
    for (const l of links) {
        l.imgs = [];
        for (const s of l.segs) {
            const [x0, y0, x1, y1] = s, xs = (cuts.get(s) || []).sort((a, b) => a - b);
            if (!xs.length) { l.imgs.push(line(lines, x0, y0, x1, y1, l.colour)); continue; }
            // the horizontal in pieces, a gap round every vertical that crosses it
            let from = Math.min(x0, x1);
            for (const x of xs) { if (x - BRIDGE > from) l.imgs.push(line(lines, from, y0, x - BRIDGE, y1, l.colour)); from = x + BRIDGE; }
            if (Math.max(x0, x1) > from) l.imgs.push(line(lines, from, y0, Math.max(x0, x1), y1, l.colour));
        }
    }
    view.links = links;
    view.junctions = marks.junctions.map(([x, y], i) => image(lines, 'tree_junction_' + i, WEB_ART + 'tree_line.png', x - 3.5, y - 3.5, 7, 7));
    view.crossings = marks.crossings;
    // the lit links of one slot: over the dimmed web, the links into it (what it needs) in the game's gold, the links out of it (what it opens) in
    // the game's green; made when lit (lightLinks)
    view.litLines = make(holder, 'tree_lines_lit', 'layer_holder');
    size(view.litLines, Math.max(1, cw), Math.max(1, ch));
    view.litLines.SetPassive();
    const nodes = rows.map(r => ({key: r.key, name: r.name, icon: r.icon_path, needs: r.requires, branch: r.branch ? {colour: r.branch} : null, row: r}));
    // A node is the game's own building slot (ui/templates/building_frame.twui.xml, square_building_button): the parchment tile building_frame.png,
    // the icon over it, a frame for built / selected / hover, the clock-wipe of construction, the turns banner, and under it the cost banner
    // (building_cost: icon_banner_bg, icon_treasury, and red_text_banner_shadow behind when the gold is short).
    view.tree = nodes.map((n, i) => {
        const {x: nx, y: ny} = pos[n.key];
        const b = image(holder, TREE + i, D + 'building_frame.png', nx, ny, NODE, NODE);
        b.SetInteractive(true);
        const v = {node: n, button: b};
        v.icon = image(b, 'icon', n.icon || D + 'icon_check.png', 0, 0, NODE, NODE);
        // a branch's node: its colour's frame, always shown (the slot's states still grey or dim the whole node); the trunk: the game's built frame
        v.plain = image(b, 'plain', n.branch ? WEB_ART + `branch_frame_${n.branch.colour}.png` : D + 'building_frame_plain.png', 0, 0, NODE, NODE);
        v.branch = n.branch;
        // selection (a built slot whose demolish button is shown): the game's orange frame; on a branch its own colour, lighter, with a bright rim
        v.frameSelected = image(b, 'selected', n.branch ? WEB_ART + `branch_frame_${n.branch.colour}_selected.png` : D + 'building_frame_selected.png', 0, 0, NODE, NODE);
        v.constructing = image(b, 'constructing', D + 'constructing_1.png', 6, 6, NODE - 12, NODE - 12);
        v.constructing.SetImageColour(255, 255, 255, 0x64);
        v.check = image(b, 'check', D + 'icon_check_green.png', 44, 48, 31, 28);      // the template's built state: 31 x 28 at 44, 48, the lower right corner
        // the padlock in the upper left corner: the upper right one is under the small unit cards of a slot that opens units (and a locked slot
        // has no demolish button over its left corner)
        v.padlock = image(b, 'padlock', D + 'padlock.png', 3, 2, 20, 25);
        // the level in its line, as the game's slot shows it (building_frame.twui.xml, building_level: 20 x 20 docked at the lower left, 0, 54;
        // the game has pictures of I to V)
        if (n.row.in_line && n.row.line_level <= 5) v.level = image(b, 'building_level', D + `settlement_silver_numeral_${n.row.line_level}.png`, 0, 54, 20, 20);
        // hover as the template: an unselected slot gets building_frame_hover (90 against the slot's 74) and brighten 0.40; the selected one
        // building_frame_selected_hover instead (refreshTree swaps them)
        v.hover = image(b, 'hover', D + 'building_frame_hover.png', -NODE * 8 / 74, -NODE * 8 / 74, NODE * 90 / 74, NODE * 90 / 74);
        v.hoverSelected = image(b, 'hover_selected', D + 'building_frame_selected_hover.png', 0, 0, NODE, NODE);
        v.hoverSelected.SetVisible(false);
        b.SetHoverChild(v.hover);
        b.SetHoverBrighten(0.4);
        // the slot's place in the lit links of another slot (lightLinks): a building it needs in the game's gold, one it opens in the game's green
        // (the hover frame's shape in the colour); and a click it refuses: the same frame in the game's red for a moment (denySlot)
        // (in the tree, not in the slot: the slot's own grey of a locked building must not grey them)
        const ring = (id, r, g, bl) => { const c = image(holder, 'mtb_slot_' + id + '_' + i, D + 'building_frame_hover.png', nx - NODE * 8 / 74, ny - NODE * 8 / 74, NODE * 90 / 74, NODE * 90 / 74); c.SetImageColour(r, g, bl, 255); c.SetPassive(); c.SetVisible(false); return c; };
        v.markIn = ring('lit_needed', 255, 211, 106);
        v.markOut = ring('lit_opened', 145, 231, 50);
        v.deny = ring('refused', 226, 40, 40);
        b.el.addEventListener('mouseenter', () => { view.hoverSlot = v; fillInfo(view, v); placeInfo(view, v); lightLinks(view); });
        b.el.addEventListener('mouseleave', () => { if (view.hoverSlot === v) view.hoverSlot = null; lightLinks(view); });
        // the turns of a construction: the game's banner across the slot's foot (turns_banner_queued.png with the hourglass at its left), the number
        // right of the hourglass, in the game's body size
        v.turnsBanner = image(b, 'turns_banner', D + 'turns_banner_queued.png', -6, NODE - 20, NODE + 12, 24);
        v.turns = text(b, 'turns', 'text_line', 22, NODE - 20, NODE - 22, 24, '');
        // the cost under the slot, always (the game shows it on hover; here every state is read at a glance): 62 wide, so that the unit card of the
        // slot below, which starts 68 from the slot's left, stays clear of it
        v.cost = image(holder, TREE + 'cost_' + i, D + 'icon_banner_bg.png', nx + 3, ny + NODE + 2, 62, 20);
        v.costRed = image(v.cost, 'red', D + 'red_text_banner_shadow.png', 0, 0, 62, 20);
        image(v.cost, 'coins', D + 'icon_treasury.png', 4, 2, 16, 16);
        v.costText = text(v.cost, 'value', 'text_line', 22, 0, 40, 20, '');
        v.info = makeInfoTip(frame, 'building_information_' + i);
        b.AddHoverChild(v.info.tip);
        return v;
    });
    view.wipe = 1;
    setInterval(() => {
        view.wipe = view.wipe % 12 + 1;
        for (const v of view.tree || []) if (v.constructing.Visible()) v.constructing.SetImagePath(D + `constructing_${view.wipe}.png`, 0);
    }, 120);
    // The crew a building opens: small unit cards beside its slot, exactly as the game's building browser places the units a building unlocks
    // (building_frame.twui.xml, units_list: docked to the slot's top right corner, dock_offset 17, -22, anchored by its own top right corner): the row
    // of cards ends 17 right of the slot and starts 22 above it; a second card pushes the row left by 13 (the entries overlap by 10). The row is a
    // later sibling of the slot's button: over its frames and marks, and not greyed with it. What has a unit card and is not the group's mount.
    view.crew = [];
    const blueprint = view.blueprint;
    const clips = Object.fromEntries((blueprint.crew_cards || []).map(c => [c.group + ':' + c.option, c]));
    const armyAll = view.data.army_units || {};
    // At most three in the row (tree_model.mjs slotCards): with more, two cards and the plate «+N» in the card's place; its tooltip lists the rest
    // (the building's window lists them all too).
    view.plates = [];
    for (const v of view.tree) {
        // only what this level brings new in its line, as the game's tree (tree_model.mjs newOnLevel); a tree without lines: all it opens
        const list = (v.node.row.unlocks_new || v.node.row.unlocks).map(u => ({...u, group_data: view.data.groups[u.group]})).map(u => ({...u, option_data: u.group_data && u.group_data.options[u.option]}))
            .filter(u => u.option_data && u.option_data.unit_card && u.option !== u.group_data.mount);
        const army = (v.node.row.units_new || v.node.row.units || []).map(k => armyAll[k]).filter(Boolean);
        const {shown, folded} = slotCards([...list.map(u => ({crew: true, u})), ...army.map(u => ({crew: false, tier: u.tier, u}))]);
        const total = shown.length + (folded.length ? 1 : 0), row_w = CARD_W + (total - 1) * (CARD_W - CARD_OVERLAP);
        const cardAt = i => [v.button.x + NODE + 17 - row_w + i * (CARD_W - CARD_OVERLAP), v.button.y - 22];
        shown.forEach((item, i) => {
            const [cx, cy] = cardAt(i), u = item.u;
            if (item.crew) {
                const card = slotUnitCard(holder, `mtb_crew_card_${v.node.row.short}_${u.option}`, cx, cy, u.option_data.unit_card, u.group_data.card_frame || 'gold', view.flags.aboard === 'outline');
                const waiting = image(card, 'waiting', D + 'icon_hourglass.png', CARD_W - 15, CARD_H - 17, 16, 16);
                const standing = image(card, 'standing', D + 'icon_check_green.png', CARD_W - 16, CARD_H - 15, 17, 15);
                const clip = clips[u.group + ':' + u.option] || {};
                // the same unit opened for the army too (tree_model.mjs oneCardPerUnit): this one card, its panel tells both
                const info = unitInfo(frame, `crew_info_${v.node.row.short}_${u.option}`, {option: u.option_data, group_data: u.group_data, movie: clip.movie || u.option + '_demo', text: clip.text || u.option_data.about || '',
                                      area: (blueprint.crew_areas || []).find(a => a.group === u.group), army_building: u.army ? v.node.row.name : null}, view.flags);
                info.hook(card);
                view.crew.push({card, info, tip: info.panel, building: v.node.key, group: u.group, option: u.option, alsoArmy: u.army || null, waiting, standing, v, cardY: cy});
            } else {
                // an army unit: the game's own frame (the crew's frame is the crew group's colour)
                const card = slotUnitCard(holder, `mtb_army_card_${v.node.row.short}_${u.key}`, cx, cy, u.card, null, false);
                const info = armyInfo(frame, `army_info_${v.node.row.short}_${u.key}`, u, armyAll, v.node.row.name);
                info.hook(card);
                view.crew.push({card, info, tip: info.panel, building: v.node.key, army: u.key, v, cardY: cy});
            }
        });
        if (folded.length) {
            // the plate: the card's size and frame, the game's dark card back, «+N» in the card's numbers
            const [px, py] = cardAt(shown.length);
            const plate = image(holder, `mtb_cards_more_${v.node.row.short}`, D + 'unit_card_back.png', px, py, CARD_W, CARD_H);
            image(plate, 'frame', D + 'unit_card_build_frame.png', 0, 0, CARD_W, CARD_H).SetPassive();
            text(plate, 'count', 'text_card_more', 0, 0, CARD_W, CARD_H, `+${folded.length}`).SetPassive();
            plate.SetHoverBrighten(0.25);
            plate.SetTooltipText(folded.map(item => item.crew ? item.u.option_data.name : item.u.name).join('\n'), true);
            view.plates.push({plate, v, folded: folded.length});
        }
    }
    // The game's demolish button over the selected built slot (building_browser.twui.xml, options_list > button_raze: round_small_button 38 x 38,
    // icon_raze, tooltip "Demolish"; its visibility CanDismantle). Here over the slot's upper left corner, where the slot has no mark; inactive with the
    // reason in its tooltip when the building cannot go yet.
    const raze = image(holder, DEMOLISH, D + 'button_round_small_active.png', 0, 0, 38, 38);
    raze.hoverImg = image(raze, 'hover', D + 'button_round_small_hover.png', 0, 0, 38, 38);
    raze.icon = image(raze, 'icon_raze', D + 'icon_raze.png', 0, 0, 38, 38);
    raze.hoverImg.SetPassive(); raze.icon.SetPassive();
    raze.SetHoverChild(raze.hoverImg);
    raze.SetInteractive(true);
    raze.SetVisible(false);
    view.raze = raze;

    // ---- the scroll bars ----
    const bars = [];
    const makeBar = (vertical, x, y, len) => {
        const k = vertical ? 'vertical' : 'horizontal';
        const bar = {vertical, len, range: len - 2 * ARROW};
        bar.track = image(pane, 'tree_bar_track_' + k, D + `slider_${k}_mid.png`, vertical ? x + (BAR - 6) / 2 : x + ARROW, vertical ? y + ARROW : y + (BAR - 6) / 2, vertical ? 6 : len - 2 * ARROW, vertical ? len - 2 * ARROW : 6);
        const arrow = (end, ax, ay) => {
            const w = vertical ? 15 : 22, h = vertical ? 22 : 15;
            const a = image(pane, `tree_bar_${end}`, D + `slider_${k}_${end}_active.png`, ax + (vertical ? (BAR - w) / 2 : 0), ay + (vertical ? 0 : (BAR - h) / 2), w, h);
            a.SetHoverChild(image(a, 'hover', D + `slider_${k}_${end}_hover.png`, 0, 0, w, h));
            return a;
        };
        bar.less = arrow(vertical ? 'top' : 'left', x, y);
        bar.more = arrow(vertical ? 'bottom' : 'right', vertical ? x : x + len - ARROW, vertical ? y + len - ARROW : y);
        bar.handle = make(pane, 'tree_bar_handle_' + k, 'slider_handle_' + (vertical ? 'v' : 'h'));
        bar.x = x; bar.y = y;
        bar.paint = () => {
            const total = (vertical ? ch : cw) * pan.z, seen = vertical ? pan.h : pan.w, off = -(vertical ? pan.y : pan.x);
            const on = total > seen + 0.5;
            for (const c of [bar.track, bar.less, bar.more, bar.handle]) c.SetVisible(on);
            if (!on) return;
            bar.hl = Math.max(HANDLE_MIN, bar.range * seen / total);
            const p = (bar.range - bar.hl) * Math.max(0, Math.min(1, off / (total - seen)));
            if (vertical) { size(bar.handle, 18, bar.hl); at(bar.handle, x + (BAR - 18) / 2, y + ARROW + p); } else { size(bar.handle, bar.hl, 18); at(bar.handle, x + ARROW + p, y + (BAR - 18) / 2); }
        };
        const scaleOf = () => pane.el.getBoundingClientRect().width / pane.Width() || 1;
        const by = d => { if (vertical) pan.y -= d; else pan.x -= d; pan.clamp(); };
        bar.less.el.addEventListener('mousedown', e => { if (e.button === 0) { e.preventDefault(); by(-STEP); } });
        bar.more.el.addEventListener('mousedown', e => { if (e.button === 0) { e.preventDefault(); by(STEP); } });
        // the track: a page toward the click
        bar.track.el.addEventListener('mousedown', e => {
            if (e.button !== 0) return;
            e.preventDefault();
            const r = bar.handle.el.getBoundingClientRect(), before = vertical ? e.clientY < r.top : e.clientX < r.left;
            by((before ? -1 : 1) * (vertical ? pan.h : pan.w) * 0.9);
        });
        // the handle dragged
        bar.handle.el.addEventListener('mousedown', e => {
            if (e.button !== 0) return;
            e.preventDefault();
            const start = vertical ? e.clientY : e.clientX, from = -(vertical ? pan.y : pan.x);
            const move = ev => {
                if (!(ev.buttons & 1)) { up(); return; }      // released where the page did not see it
                const total = (vertical ? ch : cw) * pan.z, seen = vertical ? pan.h : pan.w;
                const d = ((vertical ? ev.clientY : ev.clientX) - start) / scaleOf();
                const off = from + d * (total - seen) / Math.max(1, bar.range - bar.hl);
                if (vertical) pan.y = -off; else pan.x = -off;
                pan.clamp();
            };
            // the release seen on its way down (capture): a control under the mouse that keeps its click to itself does not keep the drag going
            const up = () => { window.removeEventListener('mousemove', move); window.removeEventListener('mouseup', up, true); };
            window.addEventListener('mousemove', move);
            window.addEventListener('mouseup', up, true);
        });
        bars.push(bar);
        return bar;
    };
    if (needV) pan.vbar = makeBar(true, edge + ww + gap, edge, wh);
    if (needH) pan.hbar = makeBar(false, edge, area.h - edge - BAR, ww);

    // ---- moving the tree ----
    pan.big = () => cw * pan.z > pan.w + 0.5 || ch * pan.z > pan.h + 0.5;
    pan.clamp = () => {
        const sw = cw * pan.z, sh = ch * pan.z, W = pan.w, H = pan.h;
        pan.x = sw <= W ? (W - sw) / 2 : Math.min(0, Math.max(W - sw, pan.x));
        pan.y = sh <= H ? (H - sh) / 2 : Math.min(0, Math.max(H - sh, pan.y));
        holder.el.style.transformOrigin = '0 0';
        holder.el.style.transform = `translate(${pan.x}px, ${pan.y}px) scale(${pan.z})`;
        for (const bar of bars) bar.paint();
        placeTips(view);
        if (view.onPan) view.onPan();
    };
    // a node's box with what belongs to it: its unit cards above and right, its cost banner under it
    const box = v => ({l: v.button.x - 14, t: v.button.y - 24, r: v.button.x + NODE + 20, b: v.button.y + NODE + 24});
    const centre = (x, y) => { pan.x = pan.w / 2 - x * pan.z; pan.y = pan.h / 2 - y * pan.z; pan.clamp(); };
    // the game's size, at what can be done now: the slots under construction and those that can be ordered (short of gold too), else what stands
    // highest, else the root of the tree; when they are taller than the window, the lowest of them (the next step up from the built part) at its foot
    pan.home = () => {
        pan.z = 1;
        const st = v => M.status(v.node.key);
        let now = view.tree.filter(v => ['building', 'open'].includes(st(v).state) || st(v).poor);
        if (!now.length) now = view.tree.filter(v => st(v).state === 'built');
        if (!now.length) now = view.tree.slice(-1);
        if (!now.length) { pan.clamp(); return; }
        const bs = now.map(box), l = Math.min(...bs.map(b => b.l)), r = Math.max(...bs.map(b => b.r)), t = Math.min(...bs.map(b => b.t)), b = Math.max(...bs.map(b => b.b));
        centre((l + r) / 2, b - t <= pan.h - 20 ? (t + b) / 2 : b + 10 - pan.h / 2);
    };
    // a node whole in the window at the game's size, moving the tree no more than needed
    pan.show = v => {
        const b = box(v);
        if (pan.z !== 1) { pan.z = 1; centre((b.l + b.r) / 2, (b.t + b.b) / 2); return; }
        if (pan.x + b.l < 0) pan.x = -b.l; else if (pan.x + b.r > pan.w) pan.x = pan.w - b.r;
        if (pan.y + b.t < 0) pan.y = -b.t; else if (pan.y + b.b > pan.h) pan.y = pan.h - b.b;
        pan.clamp();
    };
    // a click on a slot of the whole tree: the game's size at that slot (where the player was before is no longer wanted)
    pan.zoomTo = v => { pan.back = null; pan.z = 1; centre(v.button.x + NODE / 2, v.button.y + NODE / 2); };
    pan.fitZ = () => Math.min(1, pan.w / cw, pan.h / ch);
    // «Всё дерево» remembers where the player was; «Вблизи» goes back there (or, with no such place, to the middle of what is seen)
    pan.back = null;
    pan.toggle = () => {
        if (pan.z < 1) {
            const mx = (pan.w / 2 - pan.x) / pan.z, my = (pan.h / 2 - pan.y) / pan.z;
            pan.z = 1;
            if (pan.back) { pan.x = pan.back.x; pan.y = pan.back.y; pan.back = null; pan.clamp(); } else centre(mx, my);
            return;
        }
        pan.back = {x: pan.x, y: pan.y};
        pan.z = pan.fitZ();
        pan.clamp();
    };
    // what a reload or a screen built again takes back: the place, the zoom, where «Вблизи» goes back to
    pan.state = () => ({x: pan.x, y: pan.y, z: pan.z, back: pan.back});
    // drag to pan; a drag is not a click on what it started on
    let drag = null, dragged = false;
    win.el.addEventListener('mousedown', e => { if (e.button === 0 && pan.big()) { drag = {x: e.clientX, y: e.clientY, px: pan.x, py: pan.y}; dragged = false; } });
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
    window.addEventListener('mouseup', () => { drag = null; win.el.style.cursor = ''; }, true);
    // the end of a drag: not a click on the node it began on (the capture stops it before the node's own handler, and the window's listener too)
    win.el.addEventListener('mouseup', e => { if (dragged) e.stopPropagation(); drag = null; dragged = false; win.el.style.cursor = ''; }, true);
    // the wheel: up and down, as the game's lists; across with shift, or when the tree only goes across
    pane.el.addEventListener('wheel', e => {
        if (!pan.big()) return;
        e.preventDefault();
        const k = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? pan.h : 1;
        const across = e.shiftKey || ch * pan.z <= pan.h + 0.5;
        const d = (across ? e.deltaY || e.deltaX : e.deltaY) * k;
        if (across) pan.x -= d; else { pan.y -= d; pan.x -= e.deltaX * k; }
        pan.clamp();
    }, {passive: false});
    if (keep && typeof keep.y === 'number' && Number.isFinite(keep.x)) {
        pan.z = keep.z < 1 ? pan.fitZ() : 1;
        pan.x = keep.x; pan.y = keep.y;
        pan.back = keep.back && Number.isFinite(keep.back.x) && Number.isFinite(keep.back.y) ? {x: keep.back.x, y: keep.back.y} : null;
        pan.clamp();
    } else pan.home();
    view.selected = nodes.length ? nodes[0].key : null;
    view.linesHolder = lines;
}

// One slot's links lit over the dimmed web of lines: the slot under the mouse, else the selected one (a built slot with its demolish button). The links
// into it (the buildings it needs) in the game's gold and those slots ringed in gold; the links out of it (what it opens) in the game's green and those
// slots ringed in green; every other line dimmed. Back as it was when the mouse leaves.
// GAME: the lines' SetOpacity and a second set of line components shown for the lit links.
const LIT_IN = [255, 211, 106], LIT_OUT = [145, 231, 50], LIT = 5;
function lightLinks(view) {
    if (!view.tree || !view.linesHolder) return;
    const v = view.hoverSlot || (view.options && view.tree.find(t => t.node.key === view.options)) || null;
    const key = v ? v.node.key : null;
    if (view.litKey === key) return;
    view.litKey = key;
    view.litPool ||= [];
    for (const t of view.tree) { t.markIn.SetVisible(false); t.markOut.SetVisible(false); }
    let n = 0;
    if (key) {
        for (const l of view.links) {
            const into = l.to === key, out = l.from === key;
            if (!into && !out) continue;
            const c = into ? LIT_IN : LIT_OUT;
            for (const [x0, y0, x1, y1] of l.segs) {
                if (!view.litPool[n]) view.litPool[n] = image(view.litLines, 'lit_' + n, 'ui/skins/default/bar_white.png', 0, 0, 1, 1);
                const s = view.litPool[n++];
                at(s, Math.min(x0, x1) - LIT / 2, Math.min(y0, y1) - LIT / 2);
                size(s, Math.abs(x1 - x0) + LIT, Math.abs(y1 - y0) + LIT);
                s.SetImageColour(c[0], c[1], c[2], 255);
                s.SetVisible(true);
            }
            const other = view.tree.find(t => t.node.key === (into ? l.from : l.to));
            if (other) (into ? other.markIn : other.markOut).SetVisible(true);
        }
    }
    for (let i = n; i < view.litPool.length; i++) view.litPool[i].SetVisible(false);
    view.linesHolder.SetOpacity(key ? 70 : 255);
}

// A click the slot refuses (locked, or short of gold): its frame red for a moment; the foot line says why (M.refuse)
function denySlot(view, v) {
    v.deny.SetVisible(true);
    clearTimeout(v.denyTimer); cancelAnimationFrame(v.denyTimer);
    // the moment counts from when the slot is drawn red, not from the click (the panel is redrawn in between)
    v.denyTimer = requestAnimationFrame(() => { v.denyTimer = setTimeout(() => v.deny.SetVisible(false), 650); });
}

// Where a node's slot is on the panel's frame, through the tree's window (its pan and zoom): for the windows shown beside it.
function slotOnFrame(view, v) {
    const p = view.pan;
    return {x: view.pane.x + p.win.x + p.x + v.button.x * p.z, y: view.pane.y + p.win.y + p.y + v.button.y * p.z, k: p.z};
}

// a unit's panel by its small card: right of the card when it fits in the screen, else left of the card's slot; level with the card, inside the screen
function placeTips(view) {
    const root = view.frame && view.frame.parent;
    for (const c of view.crew || []) {
        if (!c.v || !c.info.total) continue;
        const s = slotOnFrame(view, c.v), frame = c.info.panel.parent, F = frame;
        const cardL = s.x + (c.card.x - c.v.button.x) * s.k, cardR = cardL + CARD_W * s.k;
        const cy = s.y + (c.cardY - c.v.button.y + CARD_H / 2) * s.k;
        const minX = 4 - F.x, maxX = (root ? root.Width() : F.Width()) - 4 - F.x - UNIT_INFO_W;
        let px = cardR + 10;
        if (px > maxX) px = Math.min(s.x - 18, cardL) - 10 - UNIT_INFO_W;
        px = Math.max(minX, Math.min(maxX, px));
        const maxY = (root ? root.Height() : F.Height()) - 4 - F.y - c.info.total, minY = view.area && maxY >= view.area.y ? view.area.y : 4 - F.y;
        c.info.place(px, Math.max(minY, Math.min(maxY, cy - c.info.total / 2)));
    }
}

// The building window of a node of the file: its own name, text, lines and crew; the chain's name of the mod for a node of the mod.
function fileInfo(view, row, card, reason) {
    const D = 'ui/skins/default/';
    return {
        // no second line under the title: the game's dy_secondary_title is the chain's own name, and a line of the tree has none (it only repeated the
        // name of the line's first level under the higher ones, which read as a misprint)
        title: row.name, chain: '', description: row.text,
        // the game's effects in full for the level; what appears on the ship with it a line each, only on the level that first brings it in its line
        // (tree_model.mjs newOnLevel: «Вид на корабле» is the page's own note, not an effect of the game)
        effects: [...(row.effects || []).filter(e => e.text).map(e => ({icon: e.icon || D + 'replenishement_positive.png', text: e.text, good: e.good})),
                  ...(row.parts_new || row.parts || []).map(p => {
                      const spec = p.part && (view.data.parts_all || {})[p.part];
                      return {icon: 'ui/campaign ui/effect_bundles/general_ability.png', good: true,
                              text: `Вид на корабле: ${p.part ? (spec ? spec.name : p.part) : p.name || 'новая деталь'}`};
                  })],
        opens: row.unlocks.map(u => ({g: view.data.groups[u.group], u})).filter(({g, u}) => g && g.options[u.option] && g.options[u.option].unit_card && u.option !== g.mount).map(({g, u}) => {
            const o = g.options[u.option], money = [o.hire ? `найм ${o.hire}` : '', o.upkeep ? `содержание ${o.upkeep} за ход` : ''].filter(Boolean).join(', ');
            return {category: o.unit_card.category, text: o.name + (money ? ` (${money})` : '')};
        }),
        army: (row.units || []).map(k => (view.data.army_units || {})[k]).filter(Boolean).map(u => ({category: u.card.category, text: u.name})),
        reason,
    };
}

// A building's window beside its slot as the game puts it (BuildingInfoPanelMouseOver: offset 10, flip_when_offscreen;
// docs/feedback/01-building-tooltip.png): right of the slot and of its unit cards (17 beyond the slot), the lower edge 28 under the slot's; on the
// left of the slot (clear of the demolish button over its corner) when the screen ends. Never over the title row and its tabs while the screen has
// room under it; always inside the screen. Offsets from the panel's frame; again whenever the mouse comes onto the slot (the tree may have moved).
// The window is always whole (fillInfoTip): it stays under the title row while it fits there; a taller one goes over the title row (the game's
// tooltips lie over anything), always inside the screen.
// A window taller than the whole screen (a building the constructor warns of: more lines than the game's window holds) is laid out wider, a hundred
// units at a time up to 800, until it fits: still whole, never cut, the font never smaller.
function fillInfo(view, v) {
    if (!v.info.dirty) return;
    v.info.dirty = false;
    const room = v.info.tip.parent.parent.Height() - 8;
    for (let w = INFO_W; w <= 800; w += 100) if (fillInfoTip(v.info, {...v.info.content, width: w}) <= room) break;
}
export function infoTop(want, h, screenH, frameY, headY) {
    const maxY = screenH - 4 - frameY - h;          // the window's foot 4 above the screen's foot
    const minY = maxY >= headY ? headY : 4 - frameY; // under the title row when it fits there, else as high as the screen's top
    return Math.max(minY, Math.min(maxY, want));
}
function placeInfo(view, v) {
    const frame = v.info.tip.parent, root = frame.parent;
    const on = slotOnFrame(view, v);
    let x = on.x + (NODE + 17) * on.k + 10;
    const w = v.info.w;
    if (frame.x + x + w > root.Width() - 4) x = on.x - 18 - 10 - w;
    x = Math.min(x, root.Width() - 4 - frame.x - w);
    x = Math.max(4 - frame.x, x);
    at(v.info.tip, x, infoTop(on.y + (NODE + 28) * on.k - v.info.h, v.info.h, root.Height(), frame.y, view.area.y));
}

// The states of the game's slot (square_building_button), each read on the slot itself:
//   built        full colour, building_frame_plain, the green check;
//   under construction  the clock-wipe and the turns banner with the turns left (a click cancels it, the gold comes back);
//   can be ordered      colour #FFFFFFB4 (a little see-through), the cost banner under it (a click orders it);
//   short of gold       the same, the cost banner red with the game's dark shadow;
//   locked       greyscale and #FFFFFF80, the padlock; why, in red in the building window on hover.
function refreshTree(view, M) {
    // the small unit cards: their marks and their panels
    for (const c of view.crew || []) {
        if (c.army) continue;           // an army unit's panel does not change with the game
        const o = M.crew_options(c.group).find(x => x.key === c.option);
        if (!o) continue;
        c.waiting.SetVisible(M.crew_order(c.group) === c.option);
        c.standing.SetVisible(M.crew(c.group) === c.option && M.crew_order(c.group) !== c.option);
        c.info.set(unitDyn(M, view.data, c.group, c.option, o));
    }
    if (view.options && (M.status(view.options).state !== 'built' || !view.demolishShown)) view.options = null;
    placeTips(view);
    for (const v of view.tree) {
        const st = M.status(v.node.key);
        const poor = st.state === 'locked' && st.poor;
        const greyed = (st.state === 'locked' && !poor) || st.state === 'unknown';
        const built = st.state === 'built', building = st.state === 'building';
        if (built) v.button.SetImageColour(255, 255, 255, 255);
        else if (greyed) v.button.SetImageColour(255, 255, 255, 0x80);
        else v.button.SetImageColour(255, 255, 255, 0xB4);
        v.button.ShaderTechniqueSet(greyed ? 'set_greyscale_t0' : 'normal_t0');
        const selected = view.options === v.node.key;
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
        const row = M.level(v.node.key);
        v.cost.SetVisible(!!row && !built && !building);
        v.costRed.SetVisible(poor);
        v.costText.SetStateText(row ? (poor ? `[[col:red]]${row.cost}[[/col]]` : String(row.cost)) : '');
        // The building information window: what the game writes about a building, and at its foot, red, why it cannot be built now (M.reason:
        // the same sentence the foot row gives after a refused click)
        const card = view.cards[v.node.key];
        const reason = M.reason(v.node.key);
        // what a click does, in the game's short words, with the time the slot itself does not show
        const note = st.state === 'open' ? `Щелчок — заказать: ${row.cost} золота, ${turnsText(row.turns)}.`
            : building ? `Строится, осталось ${turnsText(st.turns)}. Щелчок — отменить заказ, ${row.cost} золота вернутся.` : '';
        // filled when it is shown (under the mouse now, or when the mouse comes onto the slot): 41 windows measured at every change cost the page
        v.info.content = {...fileInfo(view, v.node.row, card, reason), note};
        v.info.dirty = true;
        if (v.info.tip.Visible()) { fillInfo(view, v); placeInfo(view, v); }
    }
    lightLinks(view);
    // the demolish button over the selected built slot
    const sel = view.options && view.tree.find(v => v.node.key === view.options);
    view.raze.SetVisible(!!sel);
    if (sel) {
        at(view.raze, sel.button.x - 14, sel.button.y - 14);
        const dem = M.can_demolish(sel.node.key);
        view.raze.SetImagePath('ui/skins/default/' + (dem.ok ? 'button_round_small_active.png' : 'button_round_small_inactive.png'), 0);
        view.raze.icon.ShaderTechniqueSet(dem.ok ? 'normal_t0' : 'set_greyscale_t0');
        view.raze.icon.SetImageColour(255, 255, 255, dem.ok ? 255 : 0x80);
        view.raze.hoverImg.el.style.visibility = dem.ok ? '' : 'hidden';
        view.raze.SetTooltipText(dem.ok ? `Снести «${sel.node.name}»` : dem.why, true);
        view.razeOk = dem.ok;
    }
}

// A group's place: there from the moment a building that makes it stands; with that building gone the place and its choice go too. What stands is in
// ink; an order waits for the turn: the ordered kind as a sketch at the places when nobody stands there (a crew that stands stays in ink until the
// turn replaces it, then only the tag tells of the order), the tag with an hourglass and the turns left. A detail the crew takes the place of (the
// lookouts of the nests, spec.hides_part) is hidden while someone of the crew is there or sketched there.
// What a group's place shows, for the drawing and the 3D model alike (one rule for both): the place there or not, the kind that stands (null:
// nobody), the kind sketched as a hire on its way (only where nobody stands; a crew that stands stays until the turn replaces it).
export function crewState(M, g) {
    const now = M.crew(g), order = M.crew_order(g), options = M.crew_options(g);
    const standing = options.find(o => o.key === now), ordered = options.find(o => o.key === order);
    const nobody = !standing || standing.empty;
    return {place: M.crew_place(g), now, order, options, standing, ordered, nobody, stand: nobody ? null : now, coming: ordered && !ordered.empty && nobody ? order : null};
}

function refreshCrewArea(view, M, c) {
    const g = c.group, w = M.crew_words(g);
    const {place: shown, now, order, options, standing, ordered, nobody, coming} = crewState(M, g);
    c.area.SetVisible(shown);
    if (!shown) c.open = false;
    c.pick.SetVisible(shown && c.open);
    paintCrewLayers({empty: c.empty, layers: c.layers, sketches: c.sketches}, M, g, c.spec.hides_part && view.layers[c.spec.hides_part]);
    const tag = ordered ? 'wait' : nobody ? 'plus' : 'swap';
    // the tag glows the turn its place opened or got a new kind (M.news_places), as the place's row beside the tree
    const fresh = shown && M.news_places().includes(g);
    for (const k of Object.keys(c.tags)) { c.tags[k].SetVisible(k === tag); c.hoverTags[k].SetVisible(k === tag); c.tags[k].SetGlow(fresh && k === tag); c.hoverTags[k].SetGlow(fresh && k === tag); }
    c.fresh = fresh;
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
    // over the choice, clear of the title row and its tabs when there is room for that, else as high as the screen lets it
    const head = view.area ? view.area.y : 8;
    if (py - 6 - h >= head) { slot.info.place(across, py - 6 - h); return; }
    if (py + ph + 6 + h <= F.h - 6) { slot.info.place(across, py + ph + 6); return; }
    const top = Math.max(F.h - 6 - h >= head ? head : 8, Math.min(py + ph / 2 - h / 2, F.h - 6 - h));
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

// The tab shown: the other's windows that pop up under the mouse go with it (its components are hidden under a still mouse, which gets no leave)
function setTab(view, tab) {
    if (view.tab === tab) return;
    view.tab = tab;
    for (const c of Object.values(view.crewAreas || {})) c.open = false;
    for (const v of view.tree || []) v.info.tip.SetVisible(false);
    for (const c of view.crew || []) { c.info.panel.SetVisible(false); c.info.state.SetVisible(false); }
    if (view.side) view.side.tip.SetVisible(false);
    view.options = null;
    view.hoverSlot = null;
    clearTooltip();
    if (view.onTab) view.onTab(tab);
}

// Escape, as the game's panels take it: the open crew's choice first, then the demolish button; true when it closed something
function escape(view) {
    const open = openArea(view);
    if (open) { open.open = false; return true; }
    if (view.options) { view.options = null; return true; }
    return false;
}

function refresh(view, M) {
    view.gold.SetStateText(M.game.treasury() < 0 ? `[[col:red]]${M.game.treasury()}[[/col]]` : String(M.game.treasury()));      // the game's treasury may be in debt
    const ship = view.tab === 'ship';
    for (const [k, t] of Object.entries(view.tabs)) {
        const on = k === view.tab, hovered = t.button.hovered;
        t.button.SetState(on ? (hovered ? 'selected_hover' : 'selected') : hovered ? 'hover' : 'active');
    }
    for (const c of [view.sheet, view.sheetFrame]) c.SetVisible(ship);
    view.pan.pane.SetVisible(!ship);
    // looking at «Корабль» is seeing what is new on it: the tab's mark goes
    if (ship && M.ship_unseen()) { M.ship_seen(); if (view.onSeen) view.onSeen(); }
    const unseen = M.ship_unseen() && !ship;
    view.tabMark.SetVisible(unseen);
    view.tabGlow.SetVisible(unseen);
    paintDrawing(view.sheet, view.sheets, view.layers, M);
    paintNews(view.sheet, view.layers, M);
    for (const [part, layers] of Object.entries(view.layers)) {
        const stage = M.stage(part);
        const st = stage === 'build' ? [...(M.parts[part].building ? [M.prefix + M.parts[part].building] : []), ...M.part_openers(part)].map(k => M.status(k)).find(x => x.state === 'building') || {} : {};
        const words = st.state === 'building' ? turnsText(st.turns) : '';
        layers.turns.SetVisible(stage === 'build' && !!words);
        layers.turns.SetStateText(words);
        if (words) size(layers.turns, layers.turns.TextDimensions()[0] + 16, 28);       // the plate as wide as its words
    }
    if (view.column && !ship) paintShipColumn(view, M, view.column);
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
                : s === side ? `Малакай на ${name} борту` : `Поставить Малакая на ${s === 'left' ? 'левый' : 'правый'} борт`, true);
        }
        for (const s of ['left', 'right']) view.side.portraits[s].SetVisible(shown && s === side);
        const hint = ready && M.side_hint();
        // the demo window opens on hover of the plan or a mark while the hint is on; the marks' own tooltips stay quiet then
        if (ship) view.side.demo.fit();
        const demo = hint ? view.side.tip : null;
        view.side.plan.SetHoverChild(demo);
        for (const b of Object.values(view.side.marks)) {
            b.SetHoverChild(demo);
            if (demo) b.SetTooltipText('', true);
        }
        if (!demo) view.side.tip.SetVisible(false);
        // beside the plan; with the crew's choice open, over the plan at the drawing's edge, where the choice is not
        const op = openArea(view), tip = view.side.tip, home = view.side.demo.home;
        const pickOpen = !!op && home[0] < op.pick.x + op.pick.Width() && home[0] + tip.Width() > op.pick.x && home[1] < op.pick.y + op.pick.Height() && home[1] + tip.Height() > op.pick.y;
        if (pickOpen) at(tip, 6, view.side.plan.y - 6 - tip.Height()); else at(tip, home[0], home[1]);
        // only the empty side glows: the place Malakai can be moved to
        for (const [s, g] of Object.entries(view.side.glows)) g.SetVisible(hint && s !== side);
        view.side.near.SetVisible(ready && side === 'left');
        view.side.far.SetVisible(ready && side === 'right');
        view.side.near_build.SetVisible(false);
        view.side.far_build.SetVisible(false);
    }
    for (const c of Object.values(view.crewAreas || {})) refreshCrewArea(view, M, c);
    // the foot row
    const zoom = !ship && (view.pan.needH || view.pan.needV);
    view.fitBtn.button.SetVisible(zoom);
    view.fitBtn.label.SetStateText(view.pan.z < 1 ? 'Вблизи' : 'Всё дерево');
    view.fitBtn.button.SetTooltipText(view.pan.z < 1 ? 'Вернуть дерево в обычный размер' : 'Показать всё дерево целиком', true);
    size(view.message, (zoom ? view.fitBtn.button.x - 24 : view.area.x + view.area.w - 14) - view.message.x, view.message.Height());
    fitLine(view.message, M.message() || M.first_step() || '');
}

// A click on a slot, as the game's horde slot: order what can be ordered, cancel what is under construction, a built one shows its demolish button.
// On the whole tree made smaller a click only comes back to the game's size at that slot.
function clickSlot(view, M, v) {
    const key = v.node.key;
    view.selected = key;
    const was = view.options;
    view.options = null;
    if (view.pan.z < 1) view.pan.zoomTo(v);
    else {
        const st = M.status(key);
        if (st.state === 'open') M.order(key);
        else if (st.state === 'building') M.cancel(key);
        else if (st.state === 'built' && view.demolishShown && was !== key) view.options = key;
        else if (st.state === 'locked' || st.state === 'unknown') { M.refuse(key); denySlot(view, v); }      // why, in the foot row
        view.pan.show(v);
    }
    if (view.onSelect) view.onSelect();
}

// what a click may do while a crew's choice is open: act in the choice, or go to another place's choice (its tag: the open one closes, the other
// opens, as before); any other click only closes the choice and does nothing under it (no order, no side, no tab)
const inPick = (id, g) => id.startsWith(CREW_AREA) || id === CREW_CLOSE + g || id.startsWith(CREW_PICK + g + ':') || id === 'mtb_crew_pick_' + g;

function click(view, M, c) {
    const id = c.Id();
    const open = openArea(view);
    if (open && !inPick(id, open.group)) {
        open.open = false;
        refresh(view, M);
        return;
    }
    if (id === 'mtb_ship_panel' || id === 'frame') {
        view.options = null;          // the bare panel or beside it: what is open closes
    } else if (id === 'mtb_mini_ship') {
        setTab(view, 'ship');
    } else if (id.startsWith('mtb_mini_crew_')) {
        // a place of the crew beside the tree: «Корабль» with that place's choice open (a place not open yet: only the tab)
        const g = id.slice('mtb_mini_crew_'.length);
        setTab(view, 'ship');
        const area = view.crewAreas[g];
        if (area && M.crew_place(g)) { area.open = true; if (view.onCrewArea) view.onCrewArea(g); }
    } else if (id.startsWith(TAB)) {
        setTab(view, id.slice(TAB.length));
    } else if (id.startsWith(SIDE)) {
        if (view.side && view.side.ready) M.set_malakai_side(id.slice(SIDE.length));      // no sides while the barge is only ordered
    } else if (id.startsWith(CREW_AREA)) {
        // one choice open at a time: the tag of another group closes the one that was open
        const c = view.crewAreas[id.slice(CREW_AREA.length)];
        if (c && !c.open && view.onCrewArea) view.onCrewArea(c.group);       // the page may turn its 3D view to the place (main.js)
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
    } else if (id === FIT) {
        view.options = null;
        view.pan.toggle();
    } else if (id === 'tree_window') {
        view.options = null;
    } else if (id === DEMOLISH) {
        if (view.options && view.razeOk) { const key = view.options; view.options = null; M.demolish(key); }
    } else if (id.startsWith(TREE)) {
        const v = view.tree[Number(id.slice(TREE.length))];
        if (v) clickSlot(view, M, v);
    }
    refresh(view, M);
}
