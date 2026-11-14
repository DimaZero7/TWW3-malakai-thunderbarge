// The order of a crew group, apart from any drawing: pure functions over a small state, so the same rules run on the page, in the test
// (tools/tests/crew_model_test.mjs, node) and can be carried to the mod line for line (src/tww3_mtb_crew.lua, M.choose).
//
// A group of seats has what stands now (standing) and what is ordered for the next turn (order, or none). Within a turn the player may change the
// order as often as he likes. The gold is a function of the state, never of the clicks that led to it: what is taken is the hire of the order that
// waits now (nothing for no order and for the order to take the crew off).
//
//   state   {standing: option, order: null | {option, paid}}
//   ctx     {start: the empty option, unlocked: option => bool, hire: option => gold, gold: the treasury now}
//
//   click(state, option, ctx) -> {state, gold, result}
//     result.kind   'ordered'    the order is this option now (a first order, or another in place of the one before: its hire back, this one's taken)
//                   'cancelled'  the option that stands was clicked while an order waited: the order is gone, its hire is back
//                   'kept'       nothing to change: the order already is this option, or it stands and nothing is ordered
//                   'locked'     no building opens it yet: nothing changes
//                   'poor'       not enough gold even with the hire of the waiting order back: nothing changes (what costs nothing is never
//                                refused, with the treasury in debt too)
//     result.back, result.taken   gold returned and gold taken by this click
//
//   turn(state)                the faction's turn start: the order goes in; -> state
//   lose(state, ctx)           a building is gone: an order of a locked option comes back with its hire, a standing locked crew leaves for nothing;
//                              -> {state, gold, lost: [{option, kind: 'order' | 'standing', back}]}
//
// Differences from the mod today (to be carried there): the mod allows one order of a group a turn and counts taking it back as that order;
// here any number, and the gold always matches the order that waits.

export function click(state, option, ctx) {
    const same = {state, gold: ctx.gold};
    if (option !== ctx.start && !ctx.unlocked(option)) return {...same, result: {kind: 'locked', option}};
    const paid = state.order ? state.order.paid : 0;
    if (option === state.standing) {
        if (!state.order) return {...same, result: {kind: 'kept', option, why: 'standing'}};
        return {state: {standing: state.standing, order: null}, gold: ctx.gold + paid, result: {kind: 'cancelled', option: state.order.option, back: paid, taken: 0}};
    }
    if (state.order && state.order.option === option) return {...same, result: {kind: 'kept', option, why: 'ordered'}};
    const hire = option === ctx.start ? 0 : ctx.hire(option);
    if (hire > 0 && ctx.gold + paid < hire) return {...same, result: {kind: 'poor', option, hire, have: ctx.gold + paid}};
    return {state: {standing: state.standing, order: {option, paid: hire}}, gold: ctx.gold + paid - hire,
            result: {kind: 'ordered', option, back: paid, taken: hire, instead: state.order ? state.order.option : null}};
}

export function turn(state) {
    return state.order ? {standing: state.order.option, order: null} : state;
}

export function lose(state, ctx) {
    let {standing, order} = state, gold = ctx.gold;
    const lost = [];
    if (order && order.option !== ctx.start && !ctx.unlocked(order.option)) {
        lost.push({option: order.option, kind: 'order', back: order.paid});
        gold += order.paid;
        order = null;
    }
    if (standing !== ctx.start && !ctx.unlocked(standing)) {
        lost.push({option: standing, kind: 'standing', back: 0});
        standing = ctx.start;
        if (order && order.option === ctx.start) order = null;      // an order to take off a crew that has already left
    }
    return {state: {standing, order}, gold, lost};
}

// What acts on the crew's shooting now: the sources for effects_model.mjs crewBonuses. data: the game's levels (build/web/data.json, or the tree's of
// tree_model.mjs gameData: tree_rows); has(key): the building stands (a lower level counts under a higher one); standing(key): it is the level in its slot.
//   a node's effects of the catalogue for the crew (ammo, accuracy, range, reload, damage), from every building that stands
//   the mod's own numbers of a mod building (data/crew_options.json: ammo_mod of the cargo hold, boost of a group: accuracy and range), as the mod
//   has them today, from the level in its slot only (the levels of one chain are not added up, the mod takes the highest), and only where the
//   building's node says nothing of that kind itself: the tree's own effect is what the author wants instead
// -> [{effect: {kind, target, value}, from: the building's name, mod: true for the mod's own}]
export function crewSources(data, has, standing = has) {
    const rows = data.tree_rows || [...(data.hull || []), ...(data.chains || []).flatMap(c => c.levels)];
    const crewKinds = ['ammo', 'accuracy', 'range', 'reload', 'damage'];
    const out = [];
    for (const r of rows) {
        const own = (r.effects || []).filter(e => e && crewKinds.includes(e.kind));
        // a tree of the constructor: a line of levels acts by the level that stands (its full set), the levels are not added up
        if ((data.tree_rows ? standing : has)(r.key)) for (const e of own) out.push({effect: e, from: r.name});
        if (!standing(r.key)) continue;
        const says = (kind, g) => own.some(e => e.kind === kind && (e.target === 'all' || !e.target || e.target === g));
        const mult = (data.ammo_mod || {})[r.key];
        if (mult && !own.some(e => e.kind === 'ammo')) out.push({effect: {kind: 'ammo', target: 'all', value: Math.round((mult - 1) * 100)}, from: r.name, mod: true});
        for (const [g, group] of Object.entries(data.groups || {})) for (const b of group.boost || []) {
            if (b.building !== r.key) continue;
            if (b.spread && b.spread < 1 && !says('accuracy', g)) out.push({effect: {kind: 'accuracy', target: g, value: Math.round((1 - b.spread) * 100)}, from: r.name, mod: true});
            if (b.range && b.range > 1 && !says('range', g)) out.push({effect: {kind: 'range', target: g, value: Math.round((b.range - 1) * 100)}, from: r.name, mod: true});
        }
    }
    return out;
}

// ---- The ammunition of a crew as the player reads it ----
// The mod gives a group one whole for a battle (src/tww3_mtb_ammo.lua: the group's ammo times the cargo hold's bonus, rounded floor(x + 0.5)); its
// places share it. So the group's whole is the true number and the main one; a place's share is told beside it, as «по N» only when it is whole,
// else «около N». The places are the men who shoot: the riflemen are 11 (Malakai takes the twelfth seat of the deck,
// docs/design/barge-upgrades-ideas.md, «Место Малакая»), so their whole is 11 places' worth (data/crew_options.json still counts 12 seats: the
// page follows the men). n: an option's numbers (build/web/data.json: ammo, seats), men: the number of men of its card.
// -> {places, base: the whole without a bonus, total: with it, each: total / places, whole: each is a whole number, per: each rounded}
export function crewPlaces(n, men) {
    if (!n || !n.seats) return 0;
    return men && men < n.seats ? men : n.seats;
}
export function crewAmmo(n, pct = 0, men = 0) {
    const places = crewPlaces(n, men);
    const base = places && places !== n.seats ? Math.round(n.ammo * places / n.seats) : n.ammo;
    const total = Math.floor(base * (1 + (pct || 0) / 100) + 0.5);
    const each = places ? total / places : total;
    return {places, base, total, each, whole: Number.isInteger(each), per: Math.round(each)};
}
// the places of a group in words (the number's form: 1 люк, 2 люка, 5 люков)
export const PLACE_NOUNS = {rifles: ['стрелок', 'стрелка', 'стрелков'], cannons: ['ствол', 'ствола', 'стволов'], bombs: ['люк', 'люка', 'люков'],
                            cupolas: ['гнездо', 'гнезда', 'гнёзд'], harpoon: ['гарпун', 'гарпуна', 'гарпунов']};
export function plural(v, forms) {
    const m10 = v % 10, m100 = v % 100;
    return m10 === 1 && m100 !== 11 ? forms[0] : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? forms[1] : forms[2];
}
// The line under the number: «4 люка по 28», or «4 люка, около 65 на люк» when the share is not whole. per: the place's words («на люк»).
export function ammoShare(a, group, per) {
    if (!a.places) return '';
    const noun = plural(a.places, PLACE_NOUNS[group] || ['место', 'места', 'мест']);
    return a.whole ? `${a.places} ${noun} по ${a.each}` : `${a.places} ${noun}, около ${a.per} ${per || 'на место'}`;
}

// What is taken from the treasury for this state: the hire of the order that waits.
export function held(state) {
    return state.order ? state.order.paid : 0;
}
