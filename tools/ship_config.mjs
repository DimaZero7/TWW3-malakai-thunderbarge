// The data the airship screen's logic runs on, made once for the page's model (web/js/barge_buildings.js, crew_model.mjs) and for its Lua port
// (src/tww3_mtb_ship.lua, src/tww3_mtb_crew_model.lua): docs/design/port-to-game.md, 4.1.
//
//   pageLevels()       the author's tree as the page builds it (web/js/main.js buildGame: tree_model.gameData over the tree with blueprint.json's
//                      details linked by name, the stage's details joined with the tree's drawn ones, the crew areas' words), in the page's keys
//   rekey(...)         the same in the mod's keys (build/tree/tree_rows.json: a node's level key and chain in the game), so the vectors and the game
//                      name a building alike
//   luaConfig(...)     the plain table the Lua modules read (no rule in it, only what the page's levels carry): tools/build.py packs it as
//                      script/campaign/tww3_mtb/tww3_mtb_ship_config.lua
//
//   node tools/ship_config.mjs [--out build/tree/ship_config.json]      (tools/build.py runs it after tools/tree_export.mjs)
//
// Inputs: web/data/tree_design.json, build/web/data.json (tools/web_export.py --data: the crew groups, their hire and upkeep), web/data/blueprint.json,
// web/art/layers.json, build/tree/tree_rows.json. Nothing here decides a rule: the levels are tree_model.gameData's, the rest is copied.

import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import * as T from '../web/js/tree_model.mjs';

export const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
export const readJson = p => JSON.parse(fs.readFileSync(path.isAbsolute(p) ? p : path.join(REPO, p), 'utf8'));
const clone = v => JSON.parse(JSON.stringify(v));
const CREW_KINDS = ['ammo', 'accuracy', 'range', 'reload', 'damage'];

// The page's inputs, read once
export function inputs() {
    return {data: readJson('build/web/data.json'), blueprint: readJson('web/data/blueprint.json'), art: readJson('web/art/layers.json'),
            designText: fs.readFileSync(path.join(REPO, 'web/data/tree_design.json'), 'utf8'), treeRows: readJson('build/tree/tree_rows.json')};
}

// web/js/main.js, buildGame over the tree's file, step by step (lines 35-76, 189-203): the levels, the details (parts) and the words of the places
export function pageLevels({data, blueprint: bp0, art, designText}, designOverride = null) {
    const blueprint = clone(bp0);
    const blueprintAll = clone(bp0);
    const stage = blueprint.stages[blueprint.stage];
    Object.assign(blueprint, stage, {parts: stage.parts === true ? blueprint.parts : stage.parts || {}});
    const partsInfo = T.shipParts(blueprintAll, {...art.places, ...data.art.layers});
    const byName = Object.fromEntries(Object.entries(blueprintAll.parts).map(([k, spec]) => [spec.name, k]));
    const linkParts = d => { for (const n of d ? d.nodes : []) for (const p of n.parts || []) if (!p.part && p.name && byName[p.name]) p.part = byName[p.name]; return d; };
    const joinParts = d0 => {
        const d = d0 ? linkParts(clone(d0)) : null;
        for (const p of (d ? d.nodes : []).flatMap(n => n.parts || [])) {
            const info = p.part && partsInfo[p.part];
            if (!info || (!info.drawn && !info.model)) continue;
            if (!blueprint.parts[p.part]) blueprint.parts[p.part] = {...blueprintAll.parts[p.part], enabled: true};
            else if (!blueprint.parts[p.part].enabled) blueprint.parts[p.part] = {...blueprint.parts[p.part], enabled: true};
        }
    };
    const design = designOverride || T.normalize(JSON.parse(designText)).design;
    if (!designOverride) joinParts(JSON.parse(designText));
    joinParts(design);
    const levels = T.gameData(linkParts(clone(design)), data);
    const words = {}, per = {};
    for (const a of blueprint.crew_areas || []) { if (a.words) words[a.group] = a.words; if (a.per) per[a.group] = a.per; }
    return {levels, parts: blueprint.parts, words, per, design, stage};
}

// The page's keys -> the mod's (tree_rows.json, by node): the level keys and the chain keys, everywhere the model reads a key
export function rekey(page, treeRows) {
    const {levels} = page;
    const prefix = levels.prefix;
    const byNode = Object.fromEntries(treeRows.levels.map(r => [r.id, r]));
    const key = {}, chain = {};
    for (const r of levels.tree_rows) {
        const t = byNode[r.node];
        if (!t) throw new Error(`node ${r.node} of the page is not in tree_rows.json: build again (py -3.14 tools/build.py)`);
        key[r.key] = t.key;
        chain[r.chain] = t.chain;
    }
    const k = x => (x in key ? key[x] : x);
    for (const r of levels.tree_rows) {
        r.key = k(r.key); r.short = r.key.slice(prefix.length); r.chain = chain[r.chain] || r.chain; r.requires = r.requires.map(k);
    }
    for (const c of levels.chains) c.key = chain[c.key] || c.key;
    levels.hull_tiers = Object.fromEntries(Object.entries(levels.hull_tiers).map(([x, t]) => [k(x), t]));
    levels.key_of = Object.fromEntries(Object.entries(levels.key_of).map(([id, x]) => [id, k(x)]));
    levels.ammo_mod = Object.fromEntries(Object.entries(levels.ammo_mod || {}).map(([x, v]) => [k(x), v]));
    levels.groups = clone(levels.groups);
    for (const g of Object.values(levels.groups)) {
        g.boost = (g.boost || []).map(b => ({...b, building: k(b.building)}));
        if (g.requires) g.requires = k(g.requires);
    }
    const parts = clone(page.parts);
    for (const p of Object.values(parts)) if (p.building && (prefix + p.building) in key) p.building = key[prefix + p.building].slice(prefix.length);
    return {...page, levels, parts, keyMap: key};
}

// What the Lua reads: every list in the order the page's model walks it (Object.values, Object.keys), no null inside a list
export function luaConfig({levels, parts, words, per}) {
    const all = [...levels.hull, ...levels.chains.flatMap(c => c.levels)];
    const num = v => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);
    const out = {
        _about: 'Made by tools/ship_config.mjs from the author\'s tree as the page builds it (web/js/main.js) in the mod\'s keys. Read by src/tww3_mtb_ship.lua and src/tww3_mtb_crew_model.lua. Do not edit.',
        prefix: levels.prefix,
        tree: !!levels.tree_rows,
        levels: all.map(r => ({key: r.key, name: r.name, chain: r.chain, level: r.level, tier: r.tier || 0, cost: r.cost, turns: r.turns,
                               requires: [...r.requires], unlocks: (r.unlocks || []).map(u => ({group: u.group, option: u.option})),
                               parts: (r.parts || []).filter(p => p && p.part).map(p => p.part)})),
        chains: levels.chains.map(c => ({key: c.key, levels: c.levels.map(r => r.key)})),
        hull_tiers: Object.entries(levels.hull_tiers || {}).map(([key, tier]) => ({key, tier})),
        // crewSources walks the tree's rows in the tree's order (not the chains'); only the crew's kinds of effects matter to it
        sources: (levels.tree_rows || all).map(r => ({key: r.key, name: r.name,
            effects: (r.effects || []).filter(e => e && CREW_KINDS.includes(e.kind)).map(e => ({kind: e.kind, target: e.target || '', value: e.value}))})),
        ammo_mod: Object.entries(levels.ammo_mod || {}).map(([key, mult]) => ({key, mult})),
        groups: Object.entries(levels.groups).map(([key, g]) => ({
            key, name: g.name, start: g.start, mount: g.mount || undefined, per: per[key] || undefined, words: words[key] || undefined,
            boost: (g.boost || []).map(b => ({building: b.building, spread: num(b.spread), range: num(b.range)})),
            options: Object.entries(g.options).map(([ok, o]) => ({key: ok, name: o.name, hire: o.hire || 0, upkeep: o.upkeep || 0, hidden: !!o.hidden,
                ammo: o.numbers ? num(o.numbers.ammo) : undefined, seats: o.numbers ? num(o.numbers.seats) : undefined,
                men: o.unit_card ? num(o.unit_card.men) : undefined})),
        })),
        parts: Object.entries(parts || {}).map(([key, p]) => ({key, enabled: !!p.enabled, building: p.building || undefined, carrier: !!p.carrier, base: !!p.base})),
    };
    for (const r of out.levels) if (r.unlocks.some(u => !levels.groups[u.group])) throw new Error(`${r.key}: unlocks a group not in the data`);
    return JSON.parse(JSON.stringify(out));       // undefined fields go
}

// The author's tree in the mod's keys: {page (for the JS model), config (for the Lua)}
export function authorConfig(inp = inputs()) {
    const page = rekey(pageLevels(inp), inp.treeRows);
    return {page, config: luaConfig(page)};
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
    const i = process.argv.indexOf('--out');
    const out = i > 0 ? path.resolve(process.argv[i + 1]) : path.join(REPO, 'build', 'tree', 'ship_config.json');
    const {config} = authorConfig();
    fs.mkdirSync(path.dirname(out), {recursive: true});
    fs.writeFileSync(out, JSON.stringify(config, null, 1) + '\n');
    console.log(`ship config: ${config.levels.length} levels, ${config.groups.length} crew groups, ${config.parts.length} details -> ${path.relative(REPO, out)}`);
}
