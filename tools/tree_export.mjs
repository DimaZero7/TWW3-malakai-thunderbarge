// The author's tree (web/data/tree_design.json) as the mod's rows: one file, build/tree/tree_rows.json, the single source of the tables, of the Lua's
// config and later of the page (docs/design/port-to-game.md, 2.1). The rules of lines, inheritance and what is new on a level are the page's own
// (web/js/tree_model.mjs resolve, newOnLevel, gameData; web/js/effects_model.mjs complete, statusOf): imported, not repeated. The rules of the port
// (keys, engine tiers, development points, scopes, what an effect becomes in the game) are here, with their switches in data/tree_port.json.
// The game's side comes from build/tree/game_facts.json (tools/tree_port.py). tools/build.py runs this and only writes the rows it gives.
//
//   node tools/tree_export.mjs [--design web/data/tree_design.json] [--port data/tree_port.json] [--facts build/tree/game_facts.json] [--out build/tree/tree_rows.json]
//
// An effect of a level becomes (effects[].port.as):
//   game      a row of building_effects_junction: the game's effect, the value, a scope the game itself uses for it (below)
//   text      a line of text only: an effect of ours whose description is the line (a free line of the author)
//   boost     the crew group's own projectile rows per level (data/crew_options.json boost, tools/crew_options.py), with its line of text
//   ammo_mod  the crew's ammunition multiplier of src/tww3_mtb_ammo.lua (one for all groups), with its line of text
//   ability   the mod's ability (data/crew_options.json abilities), enabled by the level
//   skip      not in this stage: «нужна разработка» (stage 5) or nothing in the game to carry it; listed per level in skipped, nothing in the game
// The scope of a game effect: the stock row of the same level (a stock key overrides it), else the scope the catalogue gives the kind, else the one the
// game uses most on Malakai's buildings, else the one it uses most on any horde's buildings from a force; none of these: skipped (iron, wine,
// province growth: nothing proves they act from a horde).
// Exit 1 with the reasons when the tree cannot be written as rows (a cycle, an unknown effect or unit, a tier over V, a key taken by the game).

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import * as T from '../web/js/tree_model.mjs';
import * as E from '../web/js/effects_model.mjs';

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const arg = (name, dflt) => { const i = process.argv.indexOf('--' + name); return i > 0 ? process.argv[i + 1] : dflt; };
const at = p => (path.isAbsolute(p) ? p : path.join(REPO, p));
const read = p => JSON.parse(fs.readFileSync(at(p), 'utf8'));

const designPath = arg('design', 'web/data/tree_design.json');
const designText = fs.readFileSync(at(designPath), 'utf8');
const facts = read(arg('facts', 'build/tree/game_facts.json'));
const port = read(arg('port', 'data/tree_port.json'));
const crewOptions = read('data/crew_options.json');
const outPath = at(arg('out', 'build/tree/tree_rows.json'));
const catalogPath = at('build/web/catalog.json');
const catalog = fs.existsSync(catalogPath) ? JSON.parse(fs.readFileSync(catalogPath, 'utf8')) : {game_effects: []};

const errors = [], warnings = [];
const P = facts.prefix;
const strip = id => String(id).replace(/^mtb_/, '');

// ---- the tree, read as the page reads it ----
const {design, problems} = T.normalize(JSON.parse(designText));
for (const p of problems) warnings.push('tree: ' + p);
if (T.hasCycle(design)) errors.push('the tree has a cycle of links');
for (const w of T.warnings(design)) if (['cycle', 'line_cycle', 'line_fork', 'dup_key', 'line_require'].includes(w.kind)) warnings.push(`tree (${w.kind}): ${w.text}`);
const node = Object.fromEntries(design.nodes.map(n => [n.id, n]));

// the crew groups and their options as the mod has them (disabled options are not in the game); an option's unit for the cards
const groups = {};
for (const [g, spec] of Object.entries(crewOptions.groups)) {
    groups[g] = {options: Object.fromEntries(Object.entries(spec.options).filter(([, o]) => !o.disabled).map(([k, o]) => [k, {unit: (o.upkeep_from || {}).unit || null}])),
                 mount: spec.mount || null, no_panel: !!spec.no_panel};
}
const gameEffects = Object.fromEntries((catalog.game_effects || []).map(g => [g.key, g]));
const ctx = {groups, gameEffects};
const page = T.gameData(design, {prefix: P, groups, hull: [], chains: [], tree_tiers: port.tiers});
const pageRow = Object.fromEntries(page.tree_rows.map(r => [r.node, r]));
const hullTier = T.hullTiers(design);      // node id -> N for airship_hull_N

// ---- lines: the page's chains (gameData: a line of levels is one chain, a fork's second branch a chain of its own) ----
const lines = [];
for (const c of page.chains) {
    const ids = c.levels.map(r => r.node);
    lines.push({ids, first: ids[0]});
}
const lineOf = {};
for (const l of lines) l.ids.forEach((id, i) => { lineOf[id] = {line: l, level: i}; });

// В1: which lines keep the stock keys and chain. A line can when its nodes are exactly the visible levels of one stock chain, in order.
const stockChainOf = l => {
    const keys = l.ids.map(id => node[id].mod_key && P + node[id].mod_key);
    const first = keys[0] && facts.levels[keys[0]];
    if (!first || !facts.chains[first.chain]) return null;
    const stock = facts.chains[first.chain].levels;
    return stock.length === keys.length && stock.every((k, i) => k === keys[i]) ? first.chain : null;
};
for (const l of lines) {
    l.stock_chain = stockChainOf(l);
    const always = (port.keys.always_vanilla || []).some(p => (node[l.first].mod_key || '').startsWith(p));
    l.vanilla = !!l.stock_chain && (always || port.keys.mode === 'vanilla');
    if (always && !l.stock_chain) errors.push(`line of «${T.label(node[l.first])}»: must keep the stock keys (${(port.keys.always_vanilla || []).join(', ')}) but its levels are not the stock chain's`);
    l.key = l.vanilla ? l.stock_chain : `mtb_${strip(l.first)}`;
    l.hull = l.ids.some(id => id in hullTier);
}
const keyOf = {};
for (const l of lines) for (const id of l.ids) keyOf[id] = l.vanilla ? P + node[id].mod_key : `${P}mtb_${strip(id)}`;
const seenKeys = {};
for (const [id, k] of Object.entries(keyOf)) {
    if (seenKeys[k]) errors.push(`two nodes get the key ${k}: ${seenKeys[k]}, ${id}`);
    seenKeys[k] = id;
    if (!lineOf[id].line.vanilla && facts.levels[k]) errors.push(`${id}: the new key ${k} is a stock level of the game`);
}
const short = id => keyOf[id].slice(P.length);

// ---- В4: engine tiers: the page's own rule (tree_model.mjs engineTiers), the same the page locks a level by ----
const maxHull = Math.max(...Object.values(hullTier), 1);
const {tier: tierOf, why: tierWhy, shares_row: sharesRow} = T.engineTiers(design, port.tiers);
const engineTier = id => tierOf[id];
// the page's game data was made with the same rule: the tier it locks by is the tier the game checks
for (const r of page.tree_rows) if (r.tier !== tierOf[r.node]) errors.push(`${r.node}: the page locks by tier ${r.tier}, the game by ${tierOf[r.node]}`);

// ---- В2: development points ----
function devPoints(id) {
    const n = node[id], mode = port.development_points.mode;
    if (mode === 'zero') return 0;
    if (mode === 'tree') return Number.isInteger(n.dev) ? n.dev : 0;
    const stock = n.mod_key && facts.levels[P + n.mod_key];
    if (id in hullTier) return stock ? stock.dev : 0;
    if (lineOf[id].level !== 0) return 0;
    if (stock && stock.level === 0) return stock.dev;
    return port.development_points.first_level_by_tier[String(engineTier(id))] ?? 1;
}

// ---- crew: what a level opens (own and new on it), the parts the current Lua knows as a group ----
const partGroups = port.rules.part_groups || {};
const bindingsOf = id => {
    const fresh = T.newOnLevel(design, id);
    const out = fresh.crew.map(x => [x.c.group, x.c.option]).filter(([g, o]) => groups[g] && groups[g].options[o]);
    for (const x of fresh.parts) if (x.p.part && partGroups[x.p.part]) out.push(partGroups[x.p.part]);
    return out;
};

// ---- scopes ----
const effectsKnown = new Set(facts.effects);
const best = list => {
    if (!list || !list.length) return null;
    const top = list[0][1];
    const tied = list.filter(([, c]) => c === top).map(([s]) => s);
    return tied.includes('force_to_force_own') ? 'force_to_force_own' : tied.sort()[0];
};
function scopeFor(effect, building, vanilla, fixed) {
    const own = vanilla && (facts.vanilla_effects[building] || []).find(r => r.effect === effect && !r.context_requirement);
    if (own) return {scope: own.effect_scope, from: 'the stock row of this level'};
    if (fixed) return {scope: fixed, from: 'the catalogue'};
    const s = facts.scope_samples[effect] || {grungni: [], horde: []};
    const g = best(s.grungni);
    if (g) return {scope: g, from: "Malakai's buildings"};
    const h = best((s.horde || []).filter(([scope]) => facts.scope_source[scope] === 'force'));
    if (h) return {scope: h, from: "horde buildings, from a force"};
    return null;
}

// what the port does with an effect's kind besides the game's own effects
const SKIP_WHY = {
    reload: 'stage 5: the reload of one group (base_reload_time in the group\'s projectile copies, combinations of several lines)',
    damage: 'stage 5: the damage of one group (damage and ap_damage in the group\'s projectile copies, combinations of several lines)',
    battle_speed: 'stage 5: the tree adds the speeds of several lines (engines, hold, hull, armour); the mod\'s passive abilities multiply and have other numbers',
    missile_resist: 'stage 5: an effect of ours with unit_damage_resistance_missile_mod on mtb_dwf_malakai_thunderbarge',
    hp: 'stage 5 and question В8: no effect of the game changes a unit\'s hit points',
    morale: 'stage 5: an effect of ours with morale on mtb_dwf_malakai_thunderbarge',
    army_replenish: 'stage 5: a unit set of the chosen units and an effect with replenishment_percentage_bonus on it',
    army_cost: 'stage 5: a unit set of the chosen units and an effect with cost_mod on it',
    army_upkeep: 'stage 5: a unit set of the chosen units and an effect with upkeep_mod on it',
    influence: 'the game\'s script sets the radius by the keys support_radius_1/2 (question В8: the game\'s radius); the stock row of those levels stays',
    ammo_group: 'stage 5: the ammunition of one group (the mod has one multiplier for all groups)',
    crew_lines: 'stage 5: the bonuses of several lines add up for this group (one projectile copy per combination)',
    ability_unknown: 'no such ability in the mod (data/crew_options.json abilities)',
};
// game effects the tree names whose stock row of a stock-key level stays as it is (not overridden, not zeroed)
const keepStock = new Set([E.KINDS.influence.game]);

// ---- the boosts: an accuracy or range of one group that comes from one line only, levels in order, never taken back on a higher level ----
const fullOf = Object.fromEntries(design.nodes.map(n => [n.id, T.resolve(design, n.id).full]));
const boostOf = {}, boostSkip = new Set();
for (const g of Object.keys(groups)) {
    const kinds = {};
    for (const kind of ['accuracy', 'range']) {
        const carriers = design.nodes.filter(n => fullOf[n.id].effects.some(x => x.e.kind === kind && x.e.target === g));
        if (!carriers.length) continue;
        const ls = new Set(carriers.map(n => lineOf[n.id].line.first));
        const line = ls.size === 1 ? lineOf[carriers[0].id].line : null;
        // from its first carrier up, every level of the line carries it (a level that takes it back cannot: the built list keeps the lower level)
        const ok = line && (() => { const i0 = line.ids.findIndex(id => carriers.some(c => c.id === id)); return line.ids.slice(i0).every(id => carriers.some(c => c.id === id)); })();
        if (ok) kinds[kind] = line; else carriers.forEach(n => boostSkip.add(`${n.id}|${kind}|${g}`));
    }
    const ks = Object.keys(kinds);
    if (!ks.length) continue;
    const line = kinds[ks[0]];
    for (const k of ks.slice(1)) if (kinds[k] !== line) { design.nodes.forEach(n => boostSkip.add(`${n.id}|${k}|${g}`)); delete kinds[k]; }
    const ids = line.ids.filter(id => Object.keys(kinds).some(k => fullOf[id].effects.some(x => x.e.kind === k && x.e.target === g)));
    boostOf[g] = {line: line.first, levels: ids, steps: ids.map(id => {
        const step = {};
        for (const x of fullOf[id].effects) {
            if (x.e.target !== g || !kinds[x.e.kind]) continue;
            if (x.e.kind === 'accuracy') step.calibration_area = Math.round((1 - x.e.value / 100) * 1e6) / 1e6;
            if (x.e.kind === 'range') step.effective_range = Math.round((1 + x.e.value / 100) * 1e6) / 1e6;
        }
        return step;
    })};
}
const abilities = Object.keys(crewOptions.abilities).filter(k => !k.startsWith('_'));

// ---- the levels ----
const unitsKeysTaken = new Set(facts.units_allowed_keys);
let unitKey = port.rules.units_key_base;
const nextUnitKey = () => { while (unitsKeysTaken.has(unitKey)) unitKey++; unitsKeysTaken.add(unitKey); return unitKey++; };
const iconsDir = path.join(REPO, 'data', 'ui', 'buildings');
const out = [];
for (const l of lines) for (const [li, id] of l.ids.entries()) {
    const n = node[id], key = keyOf[id], vanilla = l.vanilla, full = fullOf[id], fresh = T.newOnLevel(design, id);
    const tier = engineTier(id);
    if (!(id in hullTier) && tier > maxHull) errors.push(`${id}: engine tier ${tier} is over the highest hull ${maxHull}`);
    if (!(id in hullTier) && tier > 5) errors.push(`${id}: engine tier ${tier}: the game's hull has 5 levels`);
    const effects = [], rows = [], text = [], skipped = [];
    const gameRow = (effect, value, fixed, e) => {
        if (!effectsKnown.has(effect)) { errors.push(`${id}: the effect ${effect} is not in the game`); return {as: 'skip', why: 'not in the game'}; }
        const s = scopeFor(effect, key, vanilla, fixed);
        if (!s) return {as: 'skip', why: `no scope: the game uses ${effect} on no building of a horde from a force (stage 5)`};
        if (rows.some(r => r.effect === effect)) { errors.push(`${id}: the effect ${effect} twice on one level`); return {as: 'skip', why: 'twice'}; }
        rows.push({building: key, effect, effect_scope: s.scope, value, value_damaged: value, value_ruined: 0, context_requirement: ''});
        return {as: 'game', effect, scope: s.scope, scope_from: s.from};
    };
    const textLine = (x, done) => {
        const effect = `mtb_effect_line_${strip(x.from)}_${x.e.id}`;
        text.push({effect, text: done.text, good: done.good !== false, value: 1});
        return effect;
    };
    for (const x of full.effects) {
        const e = x.e;
        const done = e.kind === 'game' && !gameEffects[e.effect] ? {...e} : E.complete(e, ctx);
        const status = E.statusOf(done, ctx);
        let p;
        if (!E.isStructured(done)) p = {as: 'text', effect: textLine(x, done)};
        else if (done.kind === 'game') p = gameRow(done.effect, done.value, null, done);
        else if (['horde_cost', 'campaign_movement', 'sight'].includes(done.kind)) p = gameRow(E.KINDS[done.kind].game, done.value, E.KINDS[done.kind].scope || null, done);
        else if (done.kind === 'influence') p = {as: 'skip', why: SKIP_WHY.influence};
        else if (done.kind === 'ability') p = abilities.includes(done.target) ? {as: 'ability', ability: done.target} : {as: 'skip', why: SKIP_WHY.ability_unknown};
        else if (done.kind === 'ammo') p = done.target === 'all' ? {as: 'ammo_mod', mult: Math.round((1 + done.value / 100) * 1e6) / 1e6} : {as: 'skip', why: SKIP_WHY.ammo_group};
        else if (done.kind === 'accuracy' || done.kind === 'range') {
            const b = boostOf[done.target];
            p = b && b.levels.includes(id) && !boostSkip.has(`${id}|${done.kind}|${done.target}`) && b.steps[b.levels.indexOf(id)][done.kind === 'accuracy' ? 'calibration_area' : 'effective_range'] !== undefined
                ? {as: 'boost', group: done.target, step: b.levels.indexOf(id) + 1} : {as: 'skip', why: SKIP_WHY.crew_lines};
        } else p = {as: 'skip', why: SKIP_WHY[done.kind] || 'not ported'};
        if (p.as === 'boost' || p.as === 'ammo_mod') p.text_effect = textLine(x, done);
        if (p.as === 'skip') skipped.push({from: x.from, id: e.id, kind: done.kind || 'text', target: done.target || null, value: done.value ?? null, text: done.text, why: p.why});
        effects.push({from: x.from, id: e.id, key: x.key, kind: done.kind || null, target: done.target || null, effect: done.effect || null, value: done.value ?? null,
                      text: done.text, good: done.good !== false, icon: done.icon || null, status, port: p});
    }
    // a stock key: the stock effects the tree does not have are written as 0, except those the tree names but leaves (the radius) and those the build sets
    const zero = [];
    if (vanilla) {
        const ours = new Set(rows.map(r => r.effect));
        const keep = new Set([...keepStock, ...(port.rules.vanilla_effects_left || [])]);
        for (const r of facts.vanilla_effects[key] || []) {
            if (ours.has(r.effect) || keep.has(r.effect)) continue;
            zero.push({building: key, effect: r.effect, effect_scope: r.effect_scope, value: 0, value_damaged: 0, value_ruined: 0, context_requirement: r.context_requirement});
        }
    }
    // the units it allows: the level's whole list, as the game's tables have it
    const units = [];
    for (const x of full.units) {
        if (!facts.units[x.u]) { errors.push(`${id}: the unit ${x.u} is not in main_units`); continue; }
        if (vanilla && (facts.vanilla_units[key] || []).includes(x.u)) continue;
        units.push({building: key, unit: x.u, XP: 0, key: nextUnitKey(), conditions: 0, faction: null, enabled: false});
    }
    const stockExtra = vanilla ? (facts.vanilla_units[key] || []).filter(u => !full.units.some(x => x.u === u)) : [];
    // the requirements: the direct parents other than the level below in the line and the hull the tier carries (a required hull over the engine tier,
    // В4 mode own: a row of its own)
    const direct = n.requires.filter(p => p !== n.prev && (!(p in hullTier) || (!(id in hullTier) && hullTier[p] > tier)));
    const hullNeed = Math.max(0, ...n.requires.filter(p => p in hullTier).map(p => hullTier[p]));
    // the icon: a pack path of ours (ui/buildings/icons/tww3_mtb_<name>.png) drawn in data/ui/buildings/<name>.png
    const m = /^ui\/buildings\/icons\/(tww3_mtb_(.+))\.png$/.exec(n.icon || '');
    if (!m) errors.push(`${id}: the icon ${n.icon} is not one of ours (ui/buildings/icons/tww3_mtb_*.png)`);
    else if (!fs.existsSync(path.join(iconsDir, m[2] + '.png'))) errors.push(`${id}: no drawing data/ui/buildings/${m[2]}.png for its icon`);
    const cards = T.oneCardPerUnit(fresh.crew.map(x => x.c).filter(c => groups[c.group] && groups[c.group].options[c.option]), fresh.units.map(x => x.u), T.crewUnitOf(groups));
    const slot = T.slotCards([...cards.crew.map(c => ({crew: true, ...c})), ...cards.units.map(u => ({crew: false, unit: u, tier: (facts.units[u] || {}).tier || 0}))]);
    out.push({
        id, key, short: short(id), chain: l.key, line: l.first, level: li, line_ids: l.ids, prev: n.prev, inherit: n.inherit, vanilla, hull: id in hullTier,
        name: T.label(n), description: n.description, cost: n.cost, turns: n.turns, dev: devPoints(id),
        tier_own: n.tier, tier_engine: tier, tier_why: tierWhy[id], requirement: id in hullTier ? (facts.levels[key] || {}).requirement ?? 0 : tier - 1,
        shares_row_with: sharesRow[id] && engineTier(sharesRow[id]) === tier ? keyOf[sharesRow[id]] : null,
        requires: n.requires, requires_rows: direct.map(p => keyOf[p]), hull_need: hullNeed,
        icon: m ? {path: n.icon, name: m[1], file: `data/ui/buildings/${m[2]}.png`} : null,
        branch: n.branch, col: n.col, row: n.row, mod_key: n.mod_key,
        effects, skipped,
        rows: {effects: rows, zero, text, units},
        stock_units_kept: stockExtra,
        crew_full: full.crew.map(x => x.c), crew_new: fresh.crew.map(x => x.c), bindings: bindingsOf(id),
        units_full: full.units.map(x => x.u), units_new: fresh.units.map(x => x.u),
        parts_full: full.parts.map(x => x.p), parts_new: fresh.parts.map(x => x.p),
        hides: n.hide, cards: {crew: cards.crew, units: cards.units, shown: slot.shown, folded: slot.folded},
    });
}
for (const r of out) if (r.shares_row_with) warnings.push(`«${r.name}» (${r.id}) stands on tier ${r.tier_engine} with the level below it in its line: no hull tier above for its own row; the stock tab shows one of the two`);

// ---- the chains of the lines, the upgrades, the requirements ----
const setOf = l => {
    const stock = node[l.first].mod_key && facts.levels[P + node[l.first].mod_key];
    const sets = stock && facts.chains[stock.chain] ? facts.chains[stock.chain].building_sets : [];
    return sets[0] || port.rules.set_default;
};
const chains = lines.map((l, order) => ({
    key: l.key, first: l.first, nodes: l.ids, vanilla: l.vanilla, stock_chain: l.stock_chain, hull: l.hull,
    superchain: l.vanilla ? null : `mtb_sch_${strip(l.first)}`, instance: l.vanilla ? null : `${P}mtb_inst_${strip(l.first)}`,
    set: l.vanilla ? null : setOf(l), sort_order: order,
}));
const upgrades = [];
for (const l of lines) if (!l.vanilla) for (let i = 1; i < l.ids.length; i++) upgrades.push({from: keyOf[l.ids[i - 1]], to: keyOf[l.ids[i]]});
const requirements = out.flatMap(r => r.requires_rows.map(k => ({building_level: r.key, required: k})));

// ---- В3: the stock side chains of Malakai the tree does not use ----
const usedStock = new Set(chains.filter(c => c.vanilla).map(c => c.key));
const aiChains = Object.entries(facts.chains).filter(([c, spec]) => !usedStock.has(c) && spec.set_items.includes(port.rules.chain_set)).map(([c]) => c);
const vanillaAi = {mode: port.vanilla_chains.mode, chains: aiChains, levels: aiChains.flatMap(c => facts.chains[c].levels)};

// ---- what the current crew Lua reads by building (tools/tree_port.py crew_config) ----
const barge = out.find(r => r.parts_new.some(p => p.part === 'barge')) || out.find(r => r.mod_key === 'airship_hull_2');
const buildings = {}, autoActive = [barge.short], ammoMod = {}, abilityBy = {}, names = {};
for (const r of out) {
    names[r.short] = r.name;
    if (r.bindings.length) buildings[r.short] = r.bindings;
    const sets = r.bindings.some(([g, o]) => groups[g].no_panel || groups[g].mount === o);
    if (sets && r.short !== barge.short) autoActive.push(r.short);
    for (const e of r.effects) {
        if (e.port.as === 'ammo_mod') ammoMod[r.short] = e.port.mult;
        if (e.port.as === 'ability') (abilityBy[e.port.ability] ||= []).push(r.short);
    }
}
const boost = Object.fromEntries(Object.entries(boostOf).map(([g, b]) => [g, {buildings: b.levels.map(short), steps: b.steps}]));
const crewConfig = {buildings, auto_active: autoActive, ammo_mod: ammoMod, boost, abilities: abilityBy, names};

// ---- counts and the file ----
const counts = {
    buildings: out.length, lines: lines.length, side_lines: lines.filter(l => !l.hull).length, new_levels: out.filter(r => !r.vanilla).length, stock_key_levels: out.filter(r => r.vanilla).length,
    effects_in_tree: out.reduce((s, r) => s + r.effects.length, 0),
    effect_rows_game: out.reduce((s, r) => s + r.rows.effects.length, 0), effect_rows_zero: out.reduce((s, r) => s + r.rows.zero.length, 0),
    effect_rows_text: out.reduce((s, r) => s + r.rows.text.length, 0),
    effects_by_mod_mechanism: out.reduce((s, r) => s + r.effects.filter(e => ['boost', 'ammo_mod', 'ability'].includes(e.port.as)).length, 0),
    effects_skipped: out.reduce((s, r) => s + r.skipped.length, 0),
    units_rows: out.reduce((s, r) => s + r.rows.units.length, 0), requirement_rows: requirements.length, upgrade_rows: upgrades.length,
    levels_with_several_requirements: out.filter(r => r.requires.length >= 2).length, levels_with_several_rows: out.filter(r => r.requires_rows.length >= 2).length,
    texts: out.length * 2 + out.reduce((s, r) => s + r.rows.text.length, 0), icons: new Set(out.map(r => r.icon && r.icon.name)).size,
    tier_raised: out.filter(r => !r.hull && r.tier_engine !== (r.tier_own || 0)).length,
};
const result = {
    _about: 'Made by tools/tree_export.mjs from the author\'s tree, the page\'s models and data/tree_port.json over build/tree/game_facts.json. The single source of the tree\'s rows: '
        + 'tools/build.py writes them, tools/check_mod.py compares the pack with them. Do not edit.',
    source: {design: designPath, sha256: crypto.createHash('sha256').update(designText).digest('hex'), port: port},
    prefix: P, slot_cap: port.slot_cap.value,
    levels: out, chains, upgrades, requirements, vanilla_ai: vanillaAi, crew_config: crewConfig,
    links: T.edges(design), counts, warnings, errors,
};
fs.mkdirSync(path.dirname(outPath), {recursive: true});
fs.writeFileSync(outPath, JSON.stringify(result, null, 1) + '\n');
for (const w of warnings) console.log('warning:', w);
if (errors.length) { for (const e of errors) console.error('ERROR', e); process.exit(1); }
console.log(`tree: ${counts.buildings} levels in ${counts.lines} lines -> ${path.relative(REPO, outPath)}`);
