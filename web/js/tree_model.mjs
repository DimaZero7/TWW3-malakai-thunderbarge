// The tree of the barge's buildings as the author designs it (web/data/tree_design.json), apart from any drawing: the nodes, the links between them
// ("требует": a node needs every node of its `requires` standing first), the operations of the editor, undo and redo, the checks, the file's text,
// and the levels the page's game (web/js/game_sim.js, barge_buildings.js) builds from it. Pure functions over plain data, so the same code runs on
// the page (web/js/constructor.js, web/js/main.js) and in the test (node tools/tests/tree_model_test.mjs).
//
// The file:
//   {_about, format: 2, nodes: [node]}
//   node {id, col, row, name, description, cost, turns, tier, icon, effects: [effect], crew: [{group, option}], units: [unit key], parts: [part],
//         branch, mod_key, note, requires: [id]}
//     effects    the green and red lines: {text, icon, good} a free line, or an effect of the catalogue {kind, target, effect, value, text, icon, good,
//                own_text, own_good} (web/js/effects_model.mjs)
//     units      the army units of the game the building opens for recruitment (main_units keys, build/web/catalog.json army_units): shown only
//     parts      what appears on the ship with the building, no hire, no choice: {part: a key of web/data/blueprint.json parts} or a new detail
//                {part: null, name, zone, what, figures, note} (ZONES, WHAT)
//   Format 1 (no units, no parts, free lines only) is read as it is and written as format 2.
//     col, row   the place on the game's grid: a column and a row of 106 (a slot of 74 and 32 between, ui/campaign ui/building_browser.twui.xml);
//                row 0 is the lowest, the tree grows up
//     tier       the hull's tier the building needs (the mod's rule: tier N needs airship_hull_N), null: none
//     icon       a pack path (ui/buildings/icons/...), as the game's and the mod's pictures are named; null: none
//     branch     the colour of the frame and of the lines into the node: gold, blue, green, red (data/crew_options.json, card_frames); null: the trunk
//     mod_key    the level of the mod this node stands for, without the prefix (airship_hull_2), null for a new building
//     requires   the nodes that must stand before this one (several: all of them)

export const FORMAT = 2;
export const TURNS_MAX = 30;
export const GRID = 106, NODE = 74;
export const BRANCHES = [null, 'gold', 'blue', 'green', 'red'];
export const ABOUT = 'The tree of the barge\'s buildings, made in the page\'s constructor (web/js/constructor.js, model web/js/tree_model.mjs). '
    + 'nodes: id; col, row: the place on the game\'s grid (106 px a step, row 0 the lowest, the tree grows up); name, description, cost, turns; '
    + 'tier: the hull tier needed (null none); icon: pack path; effects: the lines, a free one {text, icon, good} or an effect of the catalogue {kind, target, effect, value, '
    + 'text, icon, good, own_text, own_good} (web/js/effects_model.mjs); crew: what the building opens in the crew (data/crew_options.json); '
    + 'units: the army units it opens for recruitment (main_units keys); parts: what appears on the ship with it, {part: a key of web/data/blueprint.json parts} or a new one '
    + '{part: null, name, zone, what, figures, note}; '
    + 'branch: colour of the frame and lines (null the trunk); mod_key: the mod\'s building level without the prefix (null for a new one); '
    + 'note: what the author wants from this building; requires: ids of the nodes that must stand first (all of them).';

const NODE_KEYS = ['id', 'col', 'row', 'name', 'description', 'cost', 'turns', 'tier', 'icon', 'effects', 'crew', 'units', 'parts', 'branch', 'mod_key', 'note', 'requires'];
// a new detail of the ship: where it is and what it is (the constructor's choices)
export const ZONES = {balloon: 'шар и вороньи гнёзда', deck: 'палуба', side: 'борт', bow: 'нос', stern: 'корма', hold: 'трюм', bottom: 'днище'};
export const WHAT = {figures: 'фигуры гномов без оружия', item: 'предмет', hull: 'часть корпуса'};
const EFFECT_KEYS = ['kind', 'target', 'effect', 'value', 'text', 'icon', 'good', 'own_text', 'own_good'];
const EFFECT_KINDS = new Set(['ammo', 'accuracy', 'range', 'reload', 'damage', 'battle_speed', 'campaign_movement', 'sight', 'influence', 'game']);
// an effect as read: a free line keeps only its three fields; an effect of the catalogue all of its own, each of its kind
export function normalizeEffect(e) {
    if (!e || typeof e !== 'object') return null;
    const base = {text: str(e.text), icon: e.icon ? str(e.icon) : null, good: e.good !== false};
    if (!EFFECT_KINDS.has(e.kind)) return base;
    const out = {kind: e.kind};
    if (['ammo', 'accuracy', 'range', 'reload', 'damage'].includes(e.kind)) out.target = e.target ? str(e.target) : 'all';
    if (e.kind === 'game') { if (!e.effect) return base; out.effect = str(e.effect); }
    out.value = Number.isFinite(Number(e.value)) && e.value !== null && e.value !== '' ? Number(e.value) : 0;
    Object.assign(out, base);
    if (e.own_text) out.own_text = true;
    if (e.own_good) out.own_good = true;
    return out;
}
export function normalizePart(p) {
    if (!p || typeof p !== 'object') return null;
    if (p.part) return {part: str(p.part)};
    return {part: null, name: str(p.name), zone: ZONES[p.zone] ? p.zone : 'deck', what: WHAT[p.what] ? p.what : 'figures',
            figures: Math.max(0, int(p.figures, 0)), note: str(p.note)};
}
const clone = x => JSON.parse(JSON.stringify(x));
const int = (v, dflt) => (Number.isFinite(Number(v)) && v !== null && v !== '' ? Math.round(Number(v)) : dflt);
const str = v => (v === null || v === undefined ? '' : String(v));

export function emptyDesign() { return {_about: ABOUT, format: FORMAT, nodes: []}; }

export function blankNode(fields = {}) {
    return {id: '', col: 0, row: 0, name: '', description: '', cost: 0, turns: 1, tier: null, icon: null, effects: [], crew: [], units: [], parts: [],
            branch: null, mod_key: null, note: '', requires: [], ...fields};
}

// A design from anything read (the file, an import, the browser's copy): every field present and of its kind, ids unique, links only to nodes that
// exist, no link twice, no link to itself. -> {design, problems: [text]}
export function normalize(raw) {
    const problems = [];
    const src = raw && typeof raw === 'object' ? raw : {};
    if (!Array.isArray(src.nodes)) { if (raw !== undefined) problems.push('В файле нет списка узлов'); }
    const nodes = [], seen = new Set();
    for (const [i, r] of (Array.isArray(src.nodes) ? src.nodes : []).entries()) {
        if (!r || typeof r !== 'object') { problems.push(`Узел ${i + 1}: не объект, пропущен`); continue; }
        let id = str(r.id).trim() || `n${i + 1}`;
        if (seen.has(id)) { problems.push(`Узел «${id}» повторяется: второму дан новый id`); let k = 2; while (seen.has(`${id}_${k}`)) k++; id = `${id}_${k}`; }
        seen.add(id);
        const branch = BRANCHES.includes(r.branch) ? r.branch : null;
        nodes.push({
            id, col: int(r.col, 0), row: int(r.row, 0), name: str(r.name), description: str(r.description),
            cost: Math.max(0, int(r.cost, 0)), turns: Math.min(TURNS_MAX, Math.max(1, int(r.turns, 1))), tier: r.tier === null || r.tier === undefined || r.tier === '' ? null : Math.max(0, int(r.tier, 0)) || null,
            icon: r.icon ? str(r.icon) : null,
            effects: (Array.isArray(r.effects) ? r.effects : []).map(normalizeEffect).filter(Boolean),
            crew: (Array.isArray(r.crew) ? r.crew : []).filter(c => c && c.group && c.option).map(c => ({group: str(c.group), option: str(c.option)})),
            units: [...new Set((Array.isArray(r.units) ? r.units : []).filter(u => typeof u === 'string' && u.trim()).map(u => u.trim()))],
            parts: (Array.isArray(r.parts) ? r.parts : []).map(normalizePart).filter(Boolean).filter((p, k, all) => !p.part || all.findIndex(q => q.part === p.part) === k),
            branch, mod_key: r.mod_key ? str(r.mod_key).trim() || null : null, note: str(r.note),
            requires: Array.isArray(r.requires) ? r.requires.map(str) : [],
        });
    }
    const ids = new Set(nodes.map(n => n.id));
    for (const n of nodes) {
        const out = [];
        for (const p of n.requires) {
            if (!ids.has(p)) { problems.push(`«${n.name || n.id}» требует узел «${p}», которого нет: связь убрана`); continue; }
            if (p === n.id) { problems.push(`«${n.name || n.id}» требует сам себя: связь убрана`); continue; }
            if (!out.includes(p)) out.push(p);
        }
        n.requires = out;
        // crew without repeats
        const c = [];
        for (const x of n.crew) if (!c.some(y => y.group === x.group && y.option === x.option)) c.push(x);
        n.crew = c;
    }
    return {design: {_about: ABOUT, format: FORMAT, nodes}, problems, from: Number(src.format) || 1};
}

// The file's text: the keys always in one order, two spaces, a newline at the end, so a change shows in git as the lines it changed.
// A line of an effect or of the crew and the list of requirements stay on one line each: the file reads as a list of buildings.
export function serialize(design) {
    const J = v => JSON.stringify(v);
    const list = (items, pad) => (items.length ? '[\n' + items.map(x => pad + '  ' + J(x)).join(',\n') + '\n' + pad + ']' : '[]');
    const node = n => {
        const lines = NODE_KEYS.map(k => {
            const v = k === 'effects' ? list(n.effects.map(e => Object.fromEntries(EFFECT_KEYS.filter(f => e[f] !== undefined && ((f !== 'own_text' && f !== 'own_good') || e[f])).map(f => [f, e[f]]))), '      ')
                : k === 'crew' ? list(n.crew.map(c => ({group: c.group, option: c.option})), '      ')
                : k === 'units' ? J(n.units || [])
                : k === 'parts' ? list((n.parts || []).map(p => (p.part ? {part: p.part} : {part: null, name: p.name, zone: p.zone, what: p.what, figures: p.figures, note: p.note})), '      ')
                : J(n[k] === undefined ? null : n[k]);
            return `      ${J(k)}: ${v}`;
        });
        return '    {\n' + lines.join(',\n') + '\n    }';
    };
    return '{\n' + `  "_about": ${J(ABOUT)},\n  "format": ${FORMAT},\n  "nodes": ` + (design.nodes.length ? '[\n' + design.nodes.map(node).join(',\n') + '\n  ]' : '[]') + '\n}\n';
}

export const byId = (d, id) => d.nodes.find(n => n.id === id);
export const children = (d, id) => d.nodes.filter(n => n.requires.includes(id)).map(n => n.id);

export function newId(d, base) {
    const ids = new Set(d.nodes.map(n => n.id));
    if (base) {
        const b = String(base).replace(/[^\w-]+/g, '_');
        if (!ids.has(b)) return b;
        for (let k = 2; ; k++) if (!ids.has(`${b}_${k}`)) return `${b}_${k}`;
    }
    let max = 0;
    for (const id of ids) { const m = /^n(\d+)$/.exec(id); if (m) max = Math.max(max, Number(m[1])); }
    return `n${max + 1}`;
}

export const cellTaken = (d, col, row, except = new Set()) => d.nodes.some(n => n.col === col && n.row === row && !except.has(n.id));

// The free cell nearest to (col, row), the row kept when it can be.
export function freeCell(d, col, row, except = new Set()) {
    for (let r = 0; r < 60; r++) for (let dr = 0; dr <= r; dr++) for (const [c, w] of [[col + (r - dr), row + dr], [col - (r - dr), row + dr], [col + (r - dr), row - dr], [col - (r - dr), row - dr]]) {
        if (!cellTaken(d, c, w, except)) return {col: c, row: w};
    }
    return {col, row};
}

export function addNode(d, fields = {}) {
    const n = blankNode({...clone(fields)});
    n.id = fields.id && !byId(d, fields.id) ? fields.id : newId(d, fields.mod_key || null);
    n.requires = (n.requires || []).filter(p => byId(d, p));
    d.nodes.push(n);
    return n.id;
}

export function updateNode(d, id, patch) {
    const n = byId(d, id);
    if (!n) return false;
    for (const [k, v] of Object.entries(patch)) if (k !== 'id' && k !== 'requires' && NODE_KEYS.includes(k)) n[k] = clone(v);
    return true;
}

export function moveNodes(d, ids, dc, dr) {
    for (const n of d.nodes) if (ids.includes(n.id)) { n.col += dc; n.row += dr; }
}

export function placeNodes(d, places) {         // {id: {col, row}}
    for (const n of d.nodes) if (places[n.id]) { n.col = places[n.id].col; n.row = places[n.id].row; }
}

export function deleteNodes(d, ids) {
    const gone = new Set(ids);
    const links = d.nodes.filter(n => !gone.has(n.id)).reduce((s, n) => s + n.requires.filter(p => gone.has(p)).length, 0)
        + d.nodes.filter(n => gone.has(n.id)).reduce((s, n) => s + n.requires.filter(p => !gone.has(p)).length, 0);
    d.nodes = d.nodes.filter(n => !gone.has(n.id));
    for (const n of d.nodes) n.requires = n.requires.filter(p => !gone.has(p));
    return {nodes: ids.length, links};
}

// Is `to` reachable from `from` along the links (from a node to what needs it)?
export function leadsTo(d, from, to) {
    const seen = new Set(), stack = [from];
    while (stack.length) {
        const k = stack.pop();
        if (k === to) return true;
        if (seen.has(k)) continue;
        seen.add(k);
        stack.push(...children(d, k));
    }
    return false;
}

// A link from `from` (built first) to `to` (needs it). -> {ok, why}
export function canLink(d, from, to) {
    const a = byId(d, from), b = byId(d, to);
    if (!a || !b) return {ok: false, why: 'Нет такого узла'};
    if (from === to) return {ok: false, why: 'Узел не может требовать сам себя'};
    if (b.requires.includes(from)) return {ok: false, why: 'Такая связь уже есть'};
    if (leadsTo(d, to, from)) return {ok: false, why: `Получится круг: «${label(a)}» уже требует «${label(b)}» через другие постройки`};
    return {ok: true};
}

export function addEdge(d, from, to) {
    const c = canLink(d, from, to);
    if (!c.ok) return c;
    byId(d, to).requires.push(from);
    return {ok: true};
}

export function deleteEdge(d, from, to) {
    const b = byId(d, to);
    if (!b || !b.requires.includes(from)) return false;
    b.requires = b.requires.filter(p => p !== from);
    return true;
}

export function reverseEdge(d, from, to) {
    if (!deleteEdge(d, from, to)) return {ok: false, why: 'Нет такой связи'};
    const r = addEdge(d, to, from);
    if (!r.ok) { byId(d, to).requires.push(from); return r; }
    return {ok: true};
}

export const edges = d => d.nodes.flatMap(n => n.requires.map(p => ({from: p, to: n.id})));
export const label = n => (n.name || '').trim() || n.id;

// Copy: the nodes and the links among them; a paste puts the group with its lowest-left corner at (col, row), each in a free cell.
export function copyNodes(d, ids) {
    const set = new Set(ids);
    const nodes = d.nodes.filter(n => set.has(n.id)).map(n => ({...clone(n), requires: n.requires.filter(p => set.has(p))}));
    return {nodes};
}

export function pasteNodes(d, clip, col, row) {
    if (!clip || !clip.nodes || !clip.nodes.length) return [];
    const c0 = Math.min(...clip.nodes.map(n => n.col)), r0 = Math.min(...clip.nodes.map(n => n.row));
    // the whole group moves on by a column until none of its cells is taken
    let dc = col - c0, dr = row - r0;
    for (let k = 0; k < 200 && clip.nodes.some(n => cellTaken(d, n.col + dc, n.row + dr)); k++) dc++;
    const map = {};
    for (const n of clip.nodes) map[n.id] = newId({nodes: [...d.nodes, ...Object.values(map).map(id => ({id}))]}, null);
    for (const n of clip.nodes) {
        d.nodes.push({...blankNode(), ...clone(n), id: map[n.id], col: n.col + dc, row: n.row + dr, requires: n.requires.map(p => map[p]).filter(Boolean)});
    }
    return clip.nodes.map(n => map[n.id]);
}

export function duplicateNodes(d, ids) {
    const clip = copyNodes(d, ids);
    if (!clip.nodes.length) return [];
    const c0 = Math.min(...clip.nodes.map(n => n.col)), c1 = Math.max(...clip.nodes.map(n => n.col)), r0 = Math.min(...clip.nodes.map(n => n.row));
    return pasteNodes(d, clip, clip.nodes.length === 1 ? c0 + 1 : c1 + 1, r0);
}

// ---- checks ----
// The root: the node of the mod's first hull without requirements, or else the node without requirements that most others come from.
export function rootOf(d) {
    const free = d.nodes.filter(n => !n.requires.length);
    if (!free.length) return null;
    const hull = free.find(n => n.mod_key === 'airship_hull_1');
    if (hull) return hull.id;
    const count = id => d.nodes.filter(n => n.id !== id && leadsTo(d, id, n.id)).length;
    return free.map(n => ({id: n.id, c: count(n.id)})).sort((a, b) => b.c - a.c)[0].id;
}

export function hasCycle(d) {
    const state = {};
    const visit = id => {
        if (state[id] === 1) return true;
        if (state[id] === 2) return false;
        state[id] = 1;
        for (const c of children(d, id)) if (visit(c)) return true;
        state[id] = 2;
        return false;
    };
    return d.nodes.some(n => visit(n.id));
}

// ctx: {modKeys: Set of the mod's level keys (short)}. -> [{kind, text, nodes: [id]}]
export function warnings(d, ctx = {}) {
    const out = [];
    const root = rootOf(d);
    if (hasCycle(d)) out.push({kind: 'cycle', text: 'В дереве есть круг связей: постройки требуют друг друга', nodes: []});
    if (d.nodes.length && root) {
        for (const n of d.nodes) {
            if (n.id === root || leadsTo(d, root, n.id)) continue;
            out.push({kind: 'orphan', text: `«${label(n)}»: нет пути от корня «${label(byId(d, root))}»`, nodes: [n.id]});
        }
    }
    for (const n of d.nodes) {
        if (!n.name.trim()) out.push({kind: 'name', text: `Узел ${n.id}: нет названия`, nodes: [n.id]});
        if (!n.cost) out.push({kind: 'cost', text: `«${label(n)}»: нет цены`, nodes: [n.id]});
        if (n.mod_key && ctx.modKeys && !ctx.modKeys.has(n.mod_key)) out.push({kind: 'mod_key', text: `«${label(n)}»: в моде нет постройки ${n.mod_key}`, nodes: [n.id]});
    }
    const byKey = {};
    for (const n of d.nodes) if (n.mod_key) (byKey[n.mod_key] ||= []).push(n.id);
    for (const [k, ids] of Object.entries(byKey)) if (ids.length > 1) out.push({kind: 'dup_key', text: `Ключ ${k} у ${ids.length} узлов: ${ids.map(id => '«' + label(byId(d, id)) + '»').join(', ')}`, nodes: ids});
    const cells = {};
    for (const n of d.nodes) (cells[n.col + ':' + n.row] ||= []).push(n.id);
    for (const ids of Object.values(cells)) if (ids.length > 1) out.push({kind: 'overlap', text: `Узлы в одной клетке: ${ids.map(id => '«' + label(byId(d, id)) + '»').join(', ')}`, nodes: ids});
    // an army unit opened by two buildings: the second adds nothing in the game
    const byUnit = {};
    for (const n of d.nodes) for (const u of n.units || []) (byUnit[u] ||= []).push(n.id);
    for (const [u, ids] of Object.entries(byUnit)) if (ids.length > 1) out.push({kind: 'dup_unit', text: `Найм «${ctx.unitName ? ctx.unitName(u) : u}» открывают ${ids.length} постройки: ${ids.map(id => '«' + label(byId(d, id)) + '»').join(', ')}`, nodes: ids});
    // what appears on the ship and has no picture yet: the author sees it is counted, the drawing does not invent it
    for (const n of d.nodes) for (const p of n.parts || []) {
        if (p.part && ctx.partKnown && !ctx.partKnown(p.part)) out.push({kind: 'ship_part', text: `«${label(n)}»: вид на корабле «${p.part}» — такой детали нет в web/data/blueprint.json`, nodes: [n.id]});
        else if (!p.part || (ctx.partDrawn && !ctx.partDrawn(p.part))) out.push({kind: 'ship_part', text: `«${label(n)}»: вид на корабле: «${p.part ? (ctx.partName ? ctx.partName(p.part) : p.part) : p.name || 'новая деталь'}» (рисунок не готов)`, nodes: [n.id]});
    }
    // what the game's building window would have to shorten (INFO, measured on the real window)
    for (const n of d.nodes) {
        const units = (ctx.units ? ctx.units(n) : n.crew.length) + (n.units || []).length;
        const bare = infoHeight({...n, description: ''}, units), max = infoDescMax(n, units);
        if (bare > INFO.SCREEN_H) {
            const fit = Math.floor((INFO.SCREEN_H - INFO.HEAD - INFO.FOOT - INFO.REASON - (units ? INFO.OPENS_HEAD + units * INFO.UNIT : 0)) / INFO.EFFECT) - (n.parts || []).length;
            out.push({kind: 'info_lines', text: `«${label(n)}»: строк ${n.effects.length}${units ? ` и отрядов ${units}` : ''} — в окне игры поместится строк не больше ${Math.max(0, fit)}`, nodes: [n.id]});
        } else if (n.description && max < INFO.DESC_CHARS_LINE) {
            out.push({kind: 'info_desc', text: `«${label(n)}»: при стольких строках и отрядах описанию нет места в окне игры`, nodes: [n.id]});
        } else if (n.description.length > max) {
            out.push({kind: 'info_desc', text: `«${label(n)}»: описание длиннее ${max} знаков — в окне игры обрежется`, nodes: [n.id]});
        }
    }
    const hulls = hullTiers(d);
    const tiers = new Set(Object.values(hulls));
    for (const n of d.nodes) {
        if (n.tier && n.tier > 1 && !(n.id in hulls) && !tiers.has(n.tier) && ![...tiers].some(t => t > n.tier)) out.push({kind: 'tier', text: `«${label(n)}»: нужен корпус яруса ${n.tier}, его нет в дереве`, nodes: [n.id]});
    }
    return out;
}

// The nodes that stand for the mod's hull levels and their tier (airship_hull_N is tier N).
export function hullTiers(d) {
    const out = {};
    for (const n of d.nodes) { const m = /^airship_hull_(\d+)$/.exec(n.mod_key || ''); if (m) out[n.id] = Number(m[1]); }
    return out;
}

// ---- the lines, the same in the constructor and in the game's column ----
// a, b: the top left corners of the slots (74 x 74) of the node built first and of the node that needs it. Square lines as the game's tree: out of
// the parent's top, up to a junction 25 under the child (in the 32 between two rows, under the child's name or cost), across, up into the child.
// Every line into one child meets at the same junction, so two parents read as one join. A child below its parent: the same, downwards; on the same
// row: straight across between their sides. blocked(x, y0, y1): is another slot on that vertical? Then the line leaves the parent to the lane
// between two columns (half a step aside, towards the child) and climbs there, so it never runs behind a building it has nothing to do with.
// -> [[x0, y0, x1, y1], ...]
export const JUNCTION = 25;
export function linkSegments(a, b, blocked = null) {
    const ax = a.x + NODE / 2, bx = b.x + NODE / 2;
    const up = b.y < a.y - NODE / 2, down = b.y > a.y + NODE / 2;
    if (up || down) {
        const gap = GRID - NODE;
        const jy = up ? b.y + NODE + JUNCTION : b.y - gap + JUNCTION;
        const ay = up ? a.y : a.y + NODE, by = up ? b.y + NODE : b.y;
        if (blocked && blocked(ax, Math.min(ay, jy), Math.max(ay, jy))) {
            const turn = up ? a.y - gap + JUNCTION : a.y + NODE + JUNCTION;
            const lane = ax + (bx >= ax ? 1 : -1) * GRID / 2;
            return [[ax, ay, ax, turn], [ax, turn, lane, turn], [lane, turn, lane, jy], [lane, jy, bx, jy], [bx, jy, bx, by]];
        }
        return ax === bx ? [[ax, ay, bx, by]] : [[ax, ay, ax, jy], [ax, jy, bx, jy], [bx, jy, bx, by]];
    }
    const y = a.y + NODE / 2;
    return b.x > a.x ? [[a.x + NODE, y, b.x, y]] : [[a.x, y, b.x + NODE, y]];
}

// blocked() for linkSegments over the slots at these corners: a vertical at x between y0 and y1 crosses one of them
export function slotsBlock(corners) {
    return (x, y0, y1) => corners.some(c => x > c.x && x < c.x + NODE && c.y < y1 - 1 && c.y + NODE > y0 + 1);
}

// ---- the constructor's own grid and its lines ----
// The game's step of 106 (a slot of 74 and 32 between) leaves no room for what the constructor shows under a slot. Its cell is larger; the file
// keeps the same col and row, the game draws them at 106. A cell of CW x CH:
//   the card       CARD_W wide, CARD_X from the cell's left: the slot (74, centred, its top SLOT_Y under the cell's top) with the price and turns
//                  in its lower strip, the crew's small cards right of the slot, the name under the slot in up to MAX_LINES lines of LINE_H
//   the corridors  between two rows (over a slot, under the names of the row above) the lines run across; between two columns (the 20 between
//                  two cards) they climb past rows they do not belong to
export const CX = {CW: 170, CH: 160, CARD_W: 150, CARD_X: 10, SLOT_Y: 30, NAME_GAP: 4, LINE_H: 15, MAX_LINES: 3};
export const cxCell = (col, row) => ({x: col * CX.CW, y: -row * CX.CH});
// the card of a node: its box, the slot's box, the bottom of its name (lines: the name's number of lines)
export function cxCard(n, lines = 1) {
    const c = cxCell(n.col, n.row);
    const x = c.x + CX.CARD_X, y = c.y + CX.SLOT_Y, slotX = x + (CX.CARD_W - NODE) / 2;
    return {x, y, w: CX.CARD_W, slotX, slotY: y, cx: x + CX.CARD_W / 2, bottom: y + NODE + CX.NAME_GAP + Math.max(1, lines) * CX.LINE_H + 2};
}
// the cell under a point of the constructor's world
export const cxCellAt = (x, y) => ({col: Math.floor(x / CX.CW), row: -Math.floor(y / CX.CH)});

// Every link its own way, with as few bends as it can have:
//   straight   the child in the parent's column, higher, every cell between empty: straight up the column's axis, out of the middle of the
//              parent's slot top into the middle of the child's card bottom, over any number of rows
//   step       the child one row higher in another column, or its own column empty over the parent's row: up into the corridor over the
//              parent, across, up into the child (the column of the child carries the climb)
//   climb      the parent's column empty up to under the child: up the parent's column, across the corridor under the child, up into it
//   round      a building on the way (or the child lower than the parent, or on its row): up into the corridor over the parent, across to the gap
//              between two columns, along the gap, across the corridor under the child, up into it; the side of the gap with fewer lines
// The ends: the straight link of a building takes the middle; the links that go left leave left of it, those to the right right of it, the
// nearest first (so they do not cross by the building); the ends of a child the same by where its links come from. Each piece across a corridor
// or along a gap takes a lane no other piece uses where they overlap, so no two links share a stretch; the corridors and gaps hold nothing but
// lines, so a line never crosses a name, a price, a card or another building. lines(n): the number of lines of the node's name.
// -> {"from|to": [[x, y], ...]}
export function cxRoutes(design, lines = () => 1) {
    const d = design, out = {};
    const card = {}, node = {}, taken = new Set();
    for (const n of d.nodes) { card[n.id] = cxCard(n, lines(n)); node[n.id] = n; taken.add(n.col + ':' + n.row); }
    const free = (col, r0, r1) => { for (let r = r0; r <= r1; r++) if (taken.has(col + ':' + r)) return false; return true; };
    const L = edges(d).filter(e => card[e.from] && card[e.to]).map(e => ({...e}));
    for (const l of L) {
        const a = node[l.from], b = node[l.to];
        l.dc = Math.sign(b.col - a.col);
        if (b.row > a.row && b.col === a.col && free(a.col, a.row + 1, b.row - 1)) l.kind = 'straight';
        else if (b.row > a.row && b.col !== a.col && free(b.col, a.row + 1, b.row - 1)) l.kind = 'step';
        else if (b.row > a.row && b.col !== a.col && free(a.col, a.row + 1, b.row - 1)) l.kind = 'climb';
        else l.kind = 'round';
    }
    // the ends
    const spread = (key, other, shift) => {
        const by = {};
        for (const l of L) (by[l[key]] ||= []).push(l);
        for (const [id, group] of Object.entries(by)) {
            const mid = group.find(l => l.kind === 'straight') || null;
            const side = s => group.filter(l => l !== mid && (s < 0 ? card[l[other]].cx < card[id].cx : card[l[other]].cx >= card[id].cx))
                .sort((x, y) => Math.abs(card[x[other]].cx - card[id].cx) - Math.abs(card[y[other]].cx - card[id].cx) || card[x[other]].y - card[y[other]].y);
            if (mid) mid[key === 'from' ? 'sx' : 'ex'] = card[id].cx;
            for (const s of [-1, 1]) {
                const list = side(s), step = Math.min(10, 30 / Math.max(1, list.length));
                list.forEach((l, i) => { l[key === 'from' ? 'sx' : 'ex'] = card[id].cx + s * (i + 1) * step + shift; });
            }
        }
    };
    // starts 2 right of the grid of 10 and ends 2 left: a line leaving a building never runs on the line entering the building over it
    spread('from', 'to', 2); spread('to', 'from', -2);
    // the corridor k lies between row k and row k + 1: from under the names of row k + 1 to over the slots of row k
    const rowsBottom = {};
    for (const n of d.nodes) rowsBottom[n.row] = Math.max(rowsBottom[n.row] ?? -Infinity, card[n.id].bottom);
    const corridor = k => {
        const bottom = cxCell(0, k).y + CX.SLOT_Y - 8;
        const top = (rowsBottom[k + 1] ?? cxCell(0, k + 1).y + CX.SLOT_Y + NODE + CX.NAME_GAP + CX.LINE_H + 2) + 5;
        return {top, bottom};
    };
    const pieces = [], gapUse = {};
    const across = (k, x0, x1, l, f) => pieces.push({ch: 'h' + k, lo: Math.min(x0, x1), hi: Math.max(x0, x1), l, f});
    for (const l of L) {
        const a = node[l.from], b = node[l.to];
        l.k1 = a.row; l.k2 = b.row - 1;
        if (l.kind === 'straight') continue;
        if (l.kind === 'step') across(l.k1, l.sx, l.ex, l, 'y1');
        else if (l.kind === 'climb') across(l.k2, l.sx, l.ex, l, 'y2');
    }
    // the round ones last: each takes the gap on its side with fewer lines along it
    for (const l of L.filter(x => x.kind === 'round')) {
        const a = node[l.from], b = node[l.to];
        const sides = b.col !== a.col ? [b.col > a.col ? b.col : b.col + 1] : [b.col, b.col + 1];
        const ya = corridor(l.k1), yb = corridor(l.k2), lo = Math.min(ya.top, yb.top), hi = Math.max(ya.bottom, yb.bottom);
        const use = g => (gapUse[g] || []).filter(([p, q]) => p < hi && lo < q).length;
        l.g = sides.sort((x, y) => use(x) - use(y) || y - x)[0];
        (gapUse[l.g] ||= []).push([lo, hi]);
        l.gx = l.g * CX.CW;
        across(l.k1, l.sx, l.gx, l, 'y1');
        across(l.k2, l.gx, l.ex, l, 'y2');
        pieces.push({ch: 'v' + l.g, lo, hi, l, f: 'x'});
    }
    // lanes: in each channel the pieces that overlap take different lanes
    const byCh = {};
    for (const p of pieces) (byCh[p.ch] ||= []).push(p);
    for (const [ch, list] of Object.entries(byCh)) {
        list.sort((a, b) => a.lo - b.lo || b.hi - a.hi);
        const ends = [];
        for (const p of list) {
            let i = ends.findIndex(e => e < p.lo - 6);
            if (i < 0) { i = ends.length; ends.push(0); }
            ends[i] = p.hi;
            p.lane = i;
        }
        const n = ends.length;
        if (ch[0] === 'h') {
            const c = corridor(Number(ch.slice(1)));
            const step = Math.max(3, Math.min(7, (c.bottom - c.top) / Math.max(1, n)));
            for (const p of list) p.l[p.f] = c.bottom - step / 2 - p.lane * step;
        } else {
            const step = n > 1 ? Math.min(4, 16 / (n - 1)) : 0;
            for (const p of list) p.l.x = Number(ch.slice(1)) * CX.CW + (p.lane - (n - 1) / 2) * step;
        }
    }
    for (const l of L) {
        const a = card[l.from], b = card[l.to];
        const start = [l.sx, a.slotY], end = [l.ex, b.bottom + 3];
        out[l.from + '|' + l.to] = l.kind === 'straight' ? [start, end]
            : l.kind === 'step' ? (l.sx === l.ex ? [start, end] : [start, [l.sx, l.y1], [l.ex, l.y1], end])
            : l.kind === 'climb' ? [start, [l.sx, l.y2], [l.ex, l.y2], end]
            : [start, [l.sx, l.y1], [l.x, l.y1], [l.x, l.y2], [l.ex, l.y2], end];
    }
    return out;
}

// the bends of a route (its points less the two ends)
export const bends = pts => Math.max(0, pts.length - 2);

// the points of a route as an SVG path with rounded corners
export function roundedPath(pts, r = 6) {
    const q = pts.filter((p, i) => i === 0 || p[0] !== pts[i - 1][0] || p[1] !== pts[i - 1][1]);
    let s = `M${q[0][0]} ${q[0][1]}`;
    for (let i = 1; i < q.length - 1; i++) {
        const [px, py] = q[i - 1], [x, y] = q[i], [nx, ny] = q[i + 1];
        const d1 = Math.hypot(x - px, y - py), d2 = Math.hypot(nx - x, ny - y), k = Math.min(r, d1 / 2, d2 / 2);
        const ax = x - (x - px) / (d1 || 1) * k, ay = y - (y - py) / (d1 || 1) * k, bx = x + (nx - x) / (d2 || 1) * k, by = y + (ny - y) / (d2 || 1) * k;
        s += ` L${ax.toFixed(1)} ${ay.toFixed(1)} Q${x} ${y} ${bx.toFixed(1)} ${by.toFixed(1)}`;
    }
    const e = q[q.length - 1];
    return s + ` L${e[0]} ${e[1]}`;
}

// ---- what the game's building window can hold (web/js/panel.js, fillInfoTip), measured on the real window on the page's root of 1600 x 900:
// the title and the chain's name 69, an effect line 36, the title of the crew block 24, a crew line 59 (its name and money take two lines), the
// foot 17, the red reason up to three lines 81; the description 372 wide, italic 16 px, about 44 letters a line, 22 a line, 36 round it. The
// window must fit in 892. The constructor warns before the game has to shorten a description or has no room left for it.
export const INFO = {SCREEN_H: 892, DESC_CHARS_LINE: 44, DESC_LINE: 22, DESC_PAD: 36, EFFECT: 36, UNIT: 59, HEAD: 69, FOOT: 17, REASON: 81, OPENS_HEAD: 24};
export function infoHeight(n, units = n.crew.length) {
    const desc = n.description ? Math.max(52, INFO.DESC_PAD + Math.ceil(n.description.length / INFO.DESC_CHARS_LINE) * INFO.DESC_LINE) : 0;
    // the lines: the effects, and one a detail of the ship (web/js/panel.js, fileInfo); a block of army units has its own title
    const lines = n.effects.length + (n.parts || []).length;
    const army = (n.units || []).length;
    return INFO.HEAD + desc + lines * INFO.EFFECT + (units ? INFO.OPENS_HEAD + units * INFO.UNIT : 0) + (army ? INFO.OPENS_HEAD : 0) + INFO.FOOT + INFO.REASON;
}
// the longest description that still fits with the node's lines and crew (0: no room for one line)
export function infoDescMax(n, units = n.crew.length) {
    const rest = infoHeight({...n, description: ''}, units);
    const lines = Math.floor((INFO.SCREEN_H - rest - INFO.DESC_PAD) / INFO.DESC_LINE);
    return Math.max(0, lines * INFO.DESC_CHARS_LINE);
}

// ---- the mod's buildings as nodes ----
// A level of build/web/data.json and its card of build/web/overview.json -> the fields of a node: what the page's building window shows of it.
export function fromModLevel(row, card, data) {
    const opens = ((card && card.opens) || []).filter(o => o.panel !== false && !o.mount);
    const effects = card ? card.effects.filter(e => !e.hidden && !e.off && !opens.some(o => (e.text || '').includes(o.name)))
        .map(e => ({text: e.text || `${e.effect} = ${e.value}`, icon: e.icon || null, good: e.good !== false}))
        : (row.lines || []).map(t => ({text: t, icon: null, good: true}));
    return {name: row.name || (card && card.name) || row.short, description: ((row.text || (card && card.text) || '').split('\n\n')[0]).trim(),
            cost: row.cost || 0, turns: row.turns || 1, tier: isHull(row, data) ? null : row.tier || null,
            icon: row.icon ? 'ui/buildings/icons/tww3_mtb_' + row.icon : card && card.icon ? iconPath(card.icon) : null,
            effects, crew: (row.unlocks || []).map(u => ({group: u.group, option: u.option})), mod_key: row.short};
}

const isHull = (row, data) => !!(data && data.hull && data.hull.some(h => h.key === row.key));

// a picture's address on the page back to its pack path (tools/web_serve.py, web/js/gameui.js url())
export function iconPath(u) {
    if (!u) return null;
    if (u.startsWith('/mod/ui/buildings/')) return 'ui/buildings/icons/tww3_mtb_' + u.slice('/mod/ui/buildings/'.length);
    if (u.startsWith('/build/game/')) return u.slice('/build/game/'.length);
    return u;
}

// What the mod itself says a level needs: the level below in its chain and its requirements (short keys).
export function modNeeds(row, data) {
    const chain = data.chains.find(c => c.key === row.chain) || (data.hull[0] && row.chain === data.hull[0].chain ? {levels: data.hull} : null);
    const below = chain && chain.levels.find(l => l.level === row.level - 1);
    return [...(below ? [below.short] : []), ...(row.requires || []).map(k => k.slice(data.prefix.length))];
}

// ---- the game's levels from the design ----
// Every node is a building of its own (a chain of one level), its requirements the nodes it requires; the hull's tier rule through hull_tiers.
// A node of the mod keeps the mod's key (prefix + mod_key), so what the drawing and the crew know by key still finds it (the beer hall, the
// dummies, the hull); a new node gets prefix + 'tree_' + id. Two nodes with one mod key: the first keeps it.
export function gameData(design, data) {
    const prefix = data.prefix, keyOf = {}, used = new Set();
    for (const n of design.nodes) {
        if (n.mod_key && !used.has(n.mod_key)) { used.add(n.mod_key); keyOf[n.id] = prefix + n.mod_key; } else keyOf[n.id] = prefix + 'tree_' + n.id;
    }
    const rows = design.nodes.map(n => ({
        key: keyOf[n.id], short: keyOf[n.id].slice(prefix.length), chain: keyOf[n.id], level: 0, name: label(n), game_name: null, text: n.description,
        cost: n.cost, turns: n.turns, dev: 0, tier: n.tier || 0, requires: n.requires.map(p => keyOf[p]).filter(Boolean),
        icon: null, icon_path: n.icon, lines: n.effects.map(e => e.text), effects: n.effects, unlocks: n.crew.filter(c => data.groups[c.group] && data.groups[c.group].options[c.option]),
        units: n.units || [], parts: n.parts || [],
        branch: n.branch, node: n.id, col: n.col, row: n.row,
    }));
    const hull_tiers = {};
    for (const [id, t] of Object.entries(hullTiers(design))) hull_tiers[keyOf[id]] = t;
    return {...data, hull: [], chains: rows.map(r => ({key: r.key, levels: [r]})), hull_tiers, tree_rows: rows, key_of: keyOf};
}

// ---- two states of the file that went apart: the author's in the open constructor and one written from outside ----
// Building by building against the state both began from (the same rule as merge3 of tools/web_serve.py): a building changed on one side only takes
// that side; changed on both, differently, is a clash. Added on one side: it comes in; deleted on one side and not changed on the other: it goes.
// -> {design, clashes: [id]}: in design a clash keeps the file's (theirs) state.
export function merge3(base, theirs, mine) {
    const key = d => new Map(d.nodes.map(n => [n.id, n]));
    const b = key(base), t = key(theirs), m = key(mine), same = (x, y) => JSON.stringify(x) === JSON.stringify(y);
    const nodes = [], clashes = [];
    for (const id of [...t.keys(), ...[...m.keys()].filter(i => !t.has(i))]) {
        const tn = t.get(id), mn = m.get(id), bn = b.get(id);
        if (tn && mn) {
            if (same(tn, mn) || (bn && same(mn, bn))) nodes.push(tn);
            else if (bn && same(tn, bn)) nodes.push(mn);
            else { nodes.push(tn); clashes.push(id); }
        } else if (tn) {
            if (bn && same(tn, bn)) continue;
            if (bn) clashes.push(id);
            nodes.push(tn);
        } else {
            if (bn && same(mn, bn)) continue;
            if (bn) clashes.push(id);
            nodes.push(mn);
        }
    }
    // a link to a building that went is dropped
    const ids = new Set(nodes.map(n => n.id));
    return {design: {...theirs, nodes: nodes.map(n => ({...clone(n), requires: n.requires.filter(p => ids.has(p))}))}, clashes};
}
// the nodes whose fields differ between two states (for the status line: what came from outside)
export function changedNodes(a, b) {
    const m = new Map(a.nodes.map(n => [n.id, JSON.stringify(n)]));
    const out = b.nodes.filter(n => m.get(n.id) !== JSON.stringify(n)).map(n => n.id);
    for (const id of m.keys()) if (!b.nodes.some(n => n.id === id)) out.push(id);
    return out;
}

// ---- the details of the ship a building can bring (web/data/blueprint.json, parts; the stage's own parts over them) ----
// -> {key: {key, name, building, drawn: a layer of it is drawn (web/art/layers.json places or data/crew_ui_art.json layers), model: a 3D model of
//    it exists, shown: the page's stage shows it now}}
export function shipParts(blueprint, places = {}) {
    const stage = (blueprint.stages || {})[blueprint.stage] || {};
    const own = stage.parts && typeof stage.parts === 'object' ? stage.parts : {};
    const out = {};
    for (const [key, spec] of [...Object.entries(blueprint.parts || {}), ...Object.entries(own)]) {
        const layers = ['pencil', 'build', 'ink'].map(s => spec[s]).filter(Boolean);
        out[key] = {key, name: spec.name, building: spec.building || null, drawn: layers.some(l => !!places[l]), model: !!(spec.model && spec.model.part),
                    shown: !!(key in own ? own[key].enabled : stage.parts === true && spec.enabled), planned: spec.planned || null};
    }
    return out;
}

// ---- undo and redo: the whole design kept at every step (a tree of dozens of nodes is small) ----
export class History {
    constructor(design, limit = 300) { this.past = []; this.future = []; this.current = clone(design); this.limit = limit; this.mergeKey = null; this.mergeAt = 0; }
    // fn(draft) changes a copy; nothing changed: no step. merge: a key; the same key again within 1.2 s (typing in one field) joins the last step.
    commit(label, fn, merge = null, now = Date.now()) {
        const draft = clone(this.current);
        const result = fn(draft);
        if (result === false) return {changed: false, result};
        if (JSON.stringify(draft) === JSON.stringify(this.current)) return {changed: false, result};
        const join = merge && this.mergeKey === merge && now - this.mergeAt < 1200 && this.past.length;
        if (!join) { this.past.push({design: this.current, label}); if (this.past.length > this.limit) this.past.shift(); }
        this.current = draft;
        this.future = [];
        this.mergeKey = merge; this.mergeAt = now;
        return {changed: true, result};
    }
    replace(design, label) { return this.commit(label, d => { d.nodes = clone(design.nodes); }); }
    undo() {
        if (!this.past.length) return null;
        const step = this.past.pop();
        this.future.push({design: this.current, label: step.label});
        this.current = step.design;
        this.mergeKey = null;
        return step.label;
    }
    redo() {
        if (!this.future.length) return null;
        const step = this.future.pop();
        this.past.push({design: this.current, label: step.label});
        this.current = step.design;
        this.mergeKey = null;
        return step.label;
    }
    get canUndo() { return this.past.length > 0; }
    get canRedo() { return this.future.length > 0; }
    get undoLabel() { return this.past.length ? this.past[this.past.length - 1].label : ''; }
    get redoLabel() { return this.future.length ? this.future[this.future.length - 1].label : ''; }
}
