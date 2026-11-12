// The order of a crew group (web/js/crew_model.mjs) against the scenarios of one turn: node tools/tests/crew_model_test.mjs
// Each scenario: who stands, the gold, the clicks; after every click the state, the gold and the kind of result are compared, and the rule that
// the gold is a function of the state (start gold - hire of the waiting order) is checked. Prints one line a scenario, exit 1 on any mismatch.
import {click, turn, lose, held} from '../../web/js/crew_model.mjs';

const HIRE = {pirates: 110, quarrellers: 80, thunderers: 110};
const OPEN = new Set(['pirates', 'quarrellers']);
const ctxOf = (gold, open = OPEN) => ({start: 'empty', unlocked: o => open.has(o), hire: o => HIRE[o], gold});
let failed = 0;

// steps: [option, kind expected, order expected (option or null), gold expected]
function scenario(name, standing, gold, steps) {
    let state = {standing, order: null}, g = gold;
    const bad = [];
    steps.forEach(([option, kind, order, expect], i) => {
        const r = click(state, option, ctxOf(g));
        state = r.state; g = r.gold;
        const got = [r.result.kind, state.order ? state.order.option : null, g];
        if (got[0] !== kind || got[1] !== order || got[2] !== expect) bad.push(`step ${i + 1} ${option}: got ${JSON.stringify(got)}, want ${JSON.stringify([kind, order, expect])}`);
        if (g !== gold - held(state)) bad.push(`step ${i + 1} ${option}: gold ${g} is not start ${gold} - held ${held(state)}`);
        if (state.standing !== standing) bad.push(`step ${i + 1} ${option}: the standing crew changed within the turn`);
    });
    if (bad.length) failed++;
    console.log((bad.length ? 'FAIL ' : 'ok   ') + name + (bad.length ? '\n     ' + bad.join('\n     ') : ''));
    return {state, gold: g};
}

function check(name, ok) {
    if (!ok) failed++;
    console.log((ok ? 'ok   ' : 'FAIL ') + name);
}

scenario('empty: pirates, crossbows', 'empty', 6000, [['pirates', 'ordered', 'pirates', 5890], ['quarrellers', 'ordered', 'quarrellers', 5920]]);
scenario('empty: pirates, pirates', 'empty', 6000, [['pirates', 'ordered', 'pirates', 5890], ['pirates', 'kept', 'pirates', 5890]]);
scenario('empty: pirates, empty, crossbows', 'empty', 6000, [['pirates', 'ordered', 'pirates', 5890], ['empty', 'cancelled', null, 6000], ['quarrellers', 'ordered', 'quarrellers', 5920]]);
scenario('crossbows stand: pirates, crossbows, pirates', 'quarrellers', 6000,
    [['pirates', 'ordered', 'pirates', 5890], ['quarrellers', 'cancelled', null, 6000], ['pirates', 'ordered', 'pirates', 5890]]);
scenario('crossbows stand: pirates, empty (take the crew off)', 'quarrellers', 6000, [['pirates', 'ordered', 'pirates', 5890], ['empty', 'ordered', 'empty', 6000]]);
scenario('crossbows stand: empty, empty, crossbows', 'quarrellers', 6000, [['empty', 'ordered', 'empty', 6000], ['empty', 'kept', 'empty', 6000], ['quarrellers', 'cancelled', null, 6000]]);
scenario('double click: pirates twice at once', 'empty', 6000, [['pirates', 'ordered', 'pirates', 5890], ['pirates', 'kept', 'pirates', 5890]]);
scenario('ten fast clicks to and fro end as one slow click', 'empty', 6000,
    [...Array(5)].flatMap(() => [['pirates', 'ordered', 'pirates', 5890], ['quarrellers', 'ordered', 'quarrellers', 5920]]));
scenario('a locked kind', 'empty', 6000, [['thunderers', 'locked', null, 6000], ['pirates', 'ordered', 'pirates', 5890], ['thunderers', 'locked', 'pirates', 5890]]);
scenario('what stands, nothing ordered', 'pirates', 6000, [['pirates', 'kept', null, 6000]]);
scenario('empty stands, empty clicked', 'empty', 6000, [['empty', 'kept', null, 6000]]);
scenario('not enough gold', 'empty', 100, [['pirates', 'poor', null, 100], ['quarrellers', 'ordered', 'quarrellers', 20], ['pirates', 'poor', 'quarrellers', 20]]);
scenario('enough only with the waiting hire back', 'empty', 110, [['quarrellers', 'ordered', 'quarrellers', 30], ['pirates', 'ordered', 'pirates', 0], ['quarrellers', 'ordered', 'quarrellers', 30]]);

scenario('a treasury in debt: no hire, but the crew may be taken off', 'pirates', -20, [['quarrellers', 'poor', null, -20], ['empty', 'ordered', 'empty', -20], ['pirates', 'cancelled', null, -20]]);
// the window closed and opened, the page reloaded: the state is plain data, a copy of it behaves the same
{
    const a = scenario('before a reload', 'empty', 6000, [['pirates', 'ordered', 'pirates', 5890]]);
    const copy = JSON.parse(JSON.stringify(a.state));
    const r = click(copy, 'quarrellers', ctxOf(a.gold));
    check('after a reload (a copy of the saved state): crossbows instead, gold 5920', r.gold === 5920 && r.state.order.option === 'quarrellers' && r.state.order.paid === 80);
}
// the turn: the order goes in, nothing more is taken; no order: nothing changes
{
    const a = scenario('before the turn', 'quarrellers', 6000, [['pirates', 'ordered', 'pirates', 5890]]);
    const t = turn(a.state);
    check('the turn start: pirates stand, no order', t.standing === 'pirates' && t.order === null);
    check('the turn start with no order keeps the state', turn({standing: 'pirates', order: null}).standing === 'pirates');
    const off = turn(click({standing: 'pirates', order: null}, 'empty', ctxOf(500)).state);
    check('the order to take the crew off: nobody stands after the turn', off.standing === 'empty' && off.order === null);
}
// a building gone
{
    const onlyPirates = new Set(['pirates']);
    const a = lose({standing: 'pirates', order: {option: 'quarrellers', paid: 80}}, ctxOf(1000, onlyPirates));
    check('the dummies gone: the order for crossbows back with 80, pirates stay', a.gold === 1080 && a.state.order === null && a.state.standing === 'pirates' && a.lost.length === 1);
    const b = lose({standing: 'quarrellers', order: {option: 'pirates', paid: 110}}, ctxOf(1000, onlyPirates));
    check('the dummies gone: standing crossbows leave for nothing, the order for pirates stays', b.gold === 1000 && b.state.standing === 'empty' && b.state.order.option === 'pirates');
    const c = lose({standing: 'quarrellers', order: {option: 'empty', paid: 0}}, ctxOf(1000, onlyPirates));
    check('the dummies gone: an order to take off the crew that left is dropped', c.state.standing === 'empty' && c.state.order === null);
    const d = lose({standing: 'pirates', order: {option: 'pirates', paid: 0}}, ctxOf(1000, new Set()));
    check('everything gone: nobody stands, no order', d.state.standing === 'empty' && d.state.order === null);
}
// the crew's bonuses: the tree's effects by group, the mod's own numbers where the node says nothing, a building that does not stand adds nothing
{
    const {crewSources} = await import('../../web/js/crew_model.mjs');
    const FX = await import('../../web/js/effects_model.mjs');
    const data = {ammo_mod: {K_cargo: 1.15}, groups: {rifles: {boost: [{building: 'K_dummy', spread: 0.95, range: null}]}, cannons: {boost: [{building: 'K_sig', spread: 0.9, range: 1.1}]}},
        tree_rows: [{key: 'K_cargo', name: 'Трюм', effects: [{kind: 'ammo', target: 'cannons', value: 25}]},
                    {key: 'K_dummy', name: 'Манекен', effects: [{text: 'Меткость стрелков: +5 %'}]},
                    {key: 'K_sig', name: 'Сигналы', effects: [{kind: 'range', target: 'all', value: 20}]},
                    {key: 'K_far', name: 'Не стоит', effects: [{kind: 'ammo', target: 'all', value: 50}]}]};
    const built = new Set(['K_cargo', 'K_dummy', 'K_sig']), has = k => built.has(k);
    const src = crewSources(data, has, has);
    const rifles = FX.crewBonuses(src, 'rifles'), cannons = FX.crewBonuses(src, 'cannons');
    check('ammo of the cannons only: +25 % from the hold (its own effect, not the mod\'s 15 %)', cannons.ammo.pct === 25 && rifles.ammo.pct === 0, JSON.stringify(src));
    check('the dummy says nothing of the catalogue: the mod\'s +5 % accuracy, marked as the mod\'s', rifles.accuracy.pct === 5 && rifles.accuracy.from[0].mod);
    check('the signals\' own range +20 % to every crew, the mod\'s +10 % of the cannons not added', rifles.range.pct === 20 && cannons.range.pct === 20);
    check('the mod\'s accuracy of the signals stays (the node says nothing of accuracy)', cannons.accuracy.pct === 10);
    check('a building that does not stand adds nothing', !src.some(s => s.from === 'Не стоит'));
    check('the numbers with the bonus', FX.applyPct(96, 25, 'ammo') === 120 && FX.applyPct(13, -10, 'reload') === 11.7);
}
// the rules of the author's tree (docs/design/tree-audit.md): a line of levels acts by its highest level (the game replaces the lower one in its slot,
// so its numbers are not added up); different buildings add; «каждой команды» and one group's own number add (the cargo hold's +100 % for every crew
// and the torpedo gallery's +30 % for the bombs: the bombs +130 %)
{
    const T = await import('../../web/js/tree_model.mjs');
    const {crewSources} = await import('../../web/js/crew_model.mjs');
    const FX = await import('../../web/js/effects_model.mjs');
    const d = T.emptyDesign();
    const h1 = T.addNode(d, {id: 'h1', name: 'Трюм', cost: 1, effects: [{kind: 'ammo', target: 'rifles', value: 15, text: '', icon: null, good: true}]});
    const h2 = T.addNode(d, {id: 'h2', name: 'Хранилище', cost: 1, requires: [h1], prev: h1, inherit: true, effects: [{kind: 'ammo', target: 'rifles', value: 30, text: '', icon: null, good: true}]});
    const h3 = T.addNode(d, {id: 'h3', name: 'Люк', cost: 1, requires: [h2], prev: h2, inherit: true, effects: [{kind: 'ammo', target: 'all', value: 100, text: '', icon: null, good: true}]});
    const tg = T.addNode(d, {id: 'tg', name: 'Торпедная галерея', cost: 1, effects: [{kind: 'ammo', target: 'bombs', value: 30, text: '', icon: null, good: true}]});
    const n1 = T.addNode(d, {id: 'n1', name: 'Гнёзда', cost: 1, effects: [{kind: 'sight', value: 10, text: '', icon: null, good: true}]});
    const n2 = T.addNode(d, {id: 'n2', name: 'Гнёзда с боеукладкой', cost: 1, requires: [n1], prev: n1, inherit: false, effects: [{kind: 'sight', value: 15, text: '', icon: null, good: true}]});
    const data = {prefix: 'p_', groups: {}, ammo_mod: {}, hull: [], chains: []};
    const g = T.gameData(d, data), key = id => g.key_of[id];
    // the game: a line is one chain, the level built replaces the one under it in its slot (web/js/game_sim.js); standing = the level in the slot
    const bonus = (ids, group) => { const s = new Set(ids.map(key)); return FX.crewBonuses(crewSources(g, k => s.has(k), k => s.has(k)), group).ammo.pct; };
    check('a line acts by its highest level: Хранилище +30, not Трюм 15 + 30', bonus([h2], 'rifles') === 30, bonus([h2], 'rifles'));
    check('«каждой команды» and the group\'s own add: Люк gives the rifles 30 (inherited) + 100', bonus([h3], 'rifles') === 130, bonus([h3], 'rifles'));
    check('different buildings add: Люк +100 for every crew and the gallery +30 for the bombs: bombs +130, cannons +100', bonus([h3, tg], 'bombs') === 130 && bonus([h3, tg], 'cannons') === 100);
    check('the gallery alone: the bombs +30, nobody else', bonus([tg], 'bombs') === 30 && bonus([tg], 'rifles') === 0);
    // a level without inheritance gives only its own: the nests' sight 15, not 10 + 15
    const sight = id => T.resolve(d, id).full.effects.filter(x => x.e.kind === 'sight').map(x => x.e.value);
    check('a level that does not inherit: «Гнёзда с боеукладкой» give sight 15 only (the line\'s rule: the upgrade, not a sum)', sight(n2).join() === '15' && g.tree_rows.find(r => r.node === n2).chain === g.tree_rows.find(r => r.node === n1).chain);
}
// the ammunition's rule (the author, 12.11.2026; docs/design/ammo-balance.md): a crew option's volleys a seat = the stock volleys of its analog unit
// (land_units.primary_ammo) x 0.7, rounded up; the group's ammunition = that x its seats. The bonuses of the tree then on the group's whole.
{
    const {readFileSync} = await import('node:fs');
    const FX = await import('../../web/js/effects_model.mjs');
    const cfg = JSON.parse(readFileSync(new URL('../../data/crew_options.json', import.meta.url), 'utf-8'));
    const bad = [], seen = [];
    for (const [g, G] of Object.entries(cfg.groups)) for (const [k, o] of Object.entries(G.options)) {
        if (!o.ammo) continue;
        if (o.stock && g === 'rifles') continue;        // the AI's stock rifles: the barge's own secondary pool, as the game has it
        const r = o.ammo_rule;
        seen.push(`${g}:${k}`);
        if (!r || r.per_seat !== Math.ceil(r.stock * 0.7 - 1e-9) || r.seats !== G.seats.length || o.ammo !== r.per_seat * r.seats) bad.push([g, k, o.ammo, r]);
    }
    check('every weapon of the crew (but the AI\'s stock rifles) follows the rule: stock x 0.7 up a seat, x the seats', !bad.length && seen.length >= 14, bad);
    const q = cfg.groups.rifles.options.quarrellers.ammo_rule;
    check('the rounding up: crossbows 22 -> 16 (15.4 up), pirates 8 -> 6 (5.6 up), axes 12 -> 9 (8.4 up)', q.per_seat === 16 && cfg.groups.rifles.options.pirates.ammo_rule.per_seat === 6 && cfg.groups.cupolas.options.axes.ammo_rule.per_seat === 9);
    check('a small base keeps its percent: +15 % of the pirates\' 72 is 83 shots (the group\'s whole is rounded, not a man\'s 6)', FX.applyPct(72, 15, 'ammo') === 83 && FX.applyPct(18, 15, 'ammo') === 21);
}
console.log(failed ? `failed: ${failed}` : 'failed: 0');
process.exit(failed ? 1 : 0);
