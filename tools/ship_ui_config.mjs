// What the airship screen's drawing reads in the game (src/tww3_mtb_ship_ui.lua), made from the same inputs and by the same steps as the page's screen
// (web/js/main.js buildGame and makePanel's arguments): docs/design/port-to-game.md, 3.2 and 4.1. Nothing here draws or decides a rule of the screen:
// it copies what web/js/panel.js reads (the levels' texts and pictures, the crew's cards and numbers, the drawing's places, blueprint.json's stage) and
// computes, with web/js/tree_model.mjs itself, the geometry the page computes at its start (a slot's place, the lines' segments with their breaks and
// junctions, the cards a slot shows), so the Lua has no second copy of those rules.
//
//   node tools/ship_ui_config.mjs [--out build/tree/ship_ui_config.json]      (tools/build.py runs it; tools/ship_lua.py packs it as Lua)
//
// Keys: every level by its mod key (as src/tww3_mtb_ship.lua names it, tools/ship_config.mjs rekey), and id: the page's short key of its level, which
// the page puts into its components' ids (mtb_crew_card_<id>_<option>): the Lua names its components as the page does, so the two screens compare.
// Every map whose order the page walks (Object.keys, Object.entries) comes with a list of its keys (*_order); no null anywhere (dropped).

import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import * as T from '../web/js/tree_model.mjs';
import * as FX from '../web/js/effects_model.mjs';
import {TEXT} from '../web/js/ui_text.mjs';
import {REPO, readJson, inputs, pageLevels, rekey} from './ship_config.mjs';

const clone = v => JSON.parse(JSON.stringify(v));
const NODE = 74;

// null and undefined out: dropped from an object, false in a list
function clean(v) {
    if (Array.isArray(v)) return v.map(x => (x === null || x === undefined ? false : clean(x)));
    if (v && typeof v === 'object') {
        const out = {};
        for (const [k, x] of Object.entries(v)) if (x !== null && x !== undefined) out[k] = clean(x);
        return out;
    }
    return v;
}

export function uiConfig(inp = inputs()) {
    // web/js/main.js lines 35-53: the stage's blueprint, the crew's drawn or close cards in place of the game's unit card
    const data = clone(inp.data);
    const blueprint = clone(inp.blueprint);
    const blueprintAll = clone(inp.blueprint);
    for (const st of Object.values(blueprint.stages)) for (const a of st.crew_areas || []) {
        const g = data.groups[a.group];
        if (g && a.cards === 'drawn') for (const o of Object.values(g.options)) if (o.drawn_card && o.unit_card) o.unit_card = {...o.unit_card, picture: o.drawn_card};
        if (g && a.cards === 'closeup') for (const [k, o] of Object.entries(g.options)) if (o.unit_card) o.unit_card = {...o.unit_card, picture: `ui/tww3_mtb_cards/${a.group}_${k}.png`};
    }
    const stageName = blueprint.stage, stage = blueprint.stages[stageName];
    Object.assign(blueprint, stage, {parts: stage.parts === true ? blueprint.parts : stage.parts || {}});
    // the levels of the tree as the page builds them (tools/ship_config.mjs pageLevels: the same steps), the details joined, then in the mod's keys
    const built = pageLevels({...inp, data});
    const pageShort = Object.fromEntries((built.levels.tree_rows || []).map(r => [r.node, r.short]));      // the page's short keys, before rekey changes them
    const page = rekey(built, inp.treeRows);
    const levels = page.levels;
    const partsInfo = T.shipParts(blueprintAll, {...inp.art.places, ...data.art.layers});
    const catalog = readJson('build/web/catalog.json');
    const armyAll = Object.fromEntries((catalog.army_units || []).map(u => [u.key, u]));
    const art = inp.art;
    const parts = page.parts;          // blueprint.parts of the stage with the tree's drawn details joined (main.js joinParts), buildings in mod keys

    // ---- the tree's geometry: web/js/panel.js makeFileTree, the same calls ----
    const rows = levels.tree_rows || [];
    const c0 = rows.length ? Math.min(...rows.map(r => r.col)) : 0, r1 = rows.length ? Math.max(...rows.map(r => r.row)) : 0;
    const pos = {};
    for (const r of rows) pos[r.key] = {x: 16 + (r.col - c0) * T.GRID, y: 30 + (r1 - r.row) * T.GRID};
    const cw = rows.length ? Math.max(...Object.values(pos).map(p => p.x)) + NODE + 17 + 4 : 0;
    const ch = rows.length ? Math.max(...Object.values(pos).map(p => p.y)) + NODE + 22 + 12 : 0;
    const blocked = T.slotsBlock(Object.values(pos));
    const links = [];
    for (const r of rows) for (const p of r.requires) if (pos[p]) links.push({from: p, to: r.key, colour: r.branch, segs: T.linkSegments(pos[p], pos[r.key], blocked)});
    const marks = T.lineMarks(links);
    const cuts = new Map();
    for (const c of marks.crossings) (cuts.get(c.h) || cuts.set(c.h, []).get(c.h)).push(c.x);
    const BRIDGE = 5;
    // every piece of line in the order the page creates them (tree_line_<n>), with its link
    const pieces = [];
    links.forEach((l, li) => {
        for (const s of l.segs) {
            const [x0, y0, x1, y1] = s, xs = (cuts.get(s) || []).sort((a, b) => a - b);
            if (!xs.length) { pieces.push([x0, y0, x1, y1, li + 1]); continue; }
            let from = Math.min(x0, x1);
            for (const x of xs) { if (x - BRIDGE > from) pieces.push([from, y0, x - BRIDGE, y1, li + 1]); from = x + BRIDGE; }
            if (Math.max(x0, x1) > from) pieces.push([from, y0, Math.max(x0, x1), y1, li + 1]);
        }
    });

    // ---- the rows as the panel reads them ----
    const groups = levels.groups;
    const rowOut = rows.map(r => {
        // the cards over a slot (makeFileTree): what the level brings new in its line, crew first, at most three (tree_model.mjs slotCards)
        const list = (r.unlocks_new || r.unlocks).map(u => ({...u, g: groups[u.group]})).filter(u => u.g && u.g.options[u.option] && u.g.options[u.option].unit_card && u.option !== u.g.mount);
        const army = (r.units_new || r.units || []).map(k => armyAll[k]).filter(Boolean);
        const {shown, folded} = T.slotCards([...list.map(u => ({crew: true, u})), ...army.map(u => ({crew: false, tier: u.tier, u}))]);
        const card = item => (item.crew ? {crew: true, group: item.u.group, option: item.u.option, army: !!item.u.army} : {crew: false, unit: item.u.key});
        // the building's window (panel.js fileInfo): its texts are the tree's, made here once
        const D = 'ui/skins/default/';
        const effects = [...(r.effects || []).filter(e => e.text).map(e => ({icon: e.icon || D + 'replenishement_positive.png', text: e.text, good: e.good !== false})),
                         ...(r.parts_new || r.parts || []).map(p => {
                             const spec = p.part && partsInfo[p.part];
                             return {icon: 'ui/campaign ui/effect_bundles/general_ability.png', good: true, text: `Вид на корабле: ${p.part ? (spec ? spec.name : p.part) : p.name || 'новая деталь'}`};
                         })];
        const opens = r.unlocks.map(u => ({g: groups[u.group], u})).filter(({g, u}) => g && g.options[u.option] && g.options[u.option].unit_card && u.option !== g.mount).map(({g, u}) => {
            const o = g.options[u.option], money = [o.hire ? `найм ${o.hire}` : '', o.upkeep ? `содержание ${o.upkeep} за ход` : ''].filter(Boolean).join(', ');
            return {category: o.unit_card.category, text: o.name + (money ? ` (${money})` : '')};
        });
        const armyRows = (r.units || []).map(k => armyAll[k]).filter(Boolean).map(u => ({category: u.card.category, text: u.name}));
        return {key: r.key, id: pageShort[r.node], name: r.name, text: r.text || '', icon: r.icon_path || '', branch: r.branch || '', in_line: !!r.in_line, line_level: r.line_level || 0,
                x: pos[r.key].x, y: pos[r.key].y, cards: shown.map(card), folded: folded.map(card),
                info: {title: r.name, description: r.text || '', effects, opens, army: armyRows}};
    });
    const index = Object.fromEntries(rows.map((r, i) => [r.key, i + 1]));
    const linkOut = links.map(l => ({from: index[l.from], to: index[l.to], colour: l.colour || "", segs: l.segs}));

    // ---- the crew's groups as the panel reads them (levels.groups: the page's data.json groups) ----
    const groupsOut = {}, groupOrder = Object.keys(groups);
    for (const [k, g] of Object.entries(groups)) {
        const options = {};
        for (const [ok, o] of Object.entries(g.options)) options[ok] = {name: o.name, about: o.about || '', hidden: !!o.hidden, unit_card: o.unit_card, numbers: o.numbers || {},
            range_text: o.range_text, fragments: o.fragments, ability: o.ability, upkeep: o.upkeep || 0, hire: o.hire || 0};
        groupsOut[k] = {name: g.name, mount: g.mount, start: g.start, card_frame: g.card_frame, options, option_order: Object.keys(g.options)};
    }
    const armyOut = {};
    for (const u of Object.values(armyAll)) armyOut[u.key] = {key: u.key, name: u.name, card: u.card, caste: u.caste, stats: u.stats, upkeep: u.upkeep, hire: u.hire, tier: u.tier};

    // ---- the drawing ----
    const partOrder = Object.keys(parts);
    const partsOut = {};
    for (const [k, p] of Object.entries(parts)) partsOut[k] = {enabled: !!p.enabled, pencil: p.pencil, build: p.build, ink: p.ink, turns_at: p.turns_at, building: p.building};
    const kinds = {};
    for (const k of FX.CREW_KINDS) kinds[k] = {name: FX.KINDS[k].name, positive_good: !!FX.KINDS[k].positiveGood};

    return clean({
        _about: 'Made by tools/ship_ui_config.mjs from the page\'s inputs as web/js/main.js builds its screen. Read by src/tww3_mtb_ship_ui.lua. Do not edit.',
        text: TEXT,
        kinds, crew_kinds: FX.CREW_KINDS,
        data: {art: {size: data.art.size, layers: data.art.layers}, groups: groupsOut, group_order: groupOrder, army_units: armyOut, rows: rowOut, links: linkOut,
               lines: pieces, junctions: marks.junctions, content: [cw, ch]},
        art: {places: art.places, crew_areas: art.crew_areas || {}, malakai_side: art.malakai_side},
        blueprint: {stage: stageName, sheet: blueprint.sheet, sheets: blueprint.sheets || [], demolish: !!blueprint.demolish, part_order: partOrder, parts: partsOut,
                    crew_areas: blueprint.crew_areas || [], crew_cards: blueprint.crew_cards || [], malakai_side: blueprint.malakai_side},
    });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    const i = process.argv.indexOf('--out');
    const out = i > 0 ? path.resolve(process.argv[i + 1]) : path.join(REPO, 'build', 'tree', 'ship_ui_config.json');
    const cfg = uiConfig();
    fs.mkdirSync(path.dirname(out), {recursive: true});
    fs.writeFileSync(out, JSON.stringify(cfg, null, 1) + '\n');
    console.log(`ship ui config: ${cfg.data.rows.length} slots, ${cfg.data.lines.length} pieces of line, ${Object.keys(cfg.data.groups).length} crew groups -> ${path.relative(REPO, out)}`);
}
