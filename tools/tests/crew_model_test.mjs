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
console.log(failed ? `failed: ${failed}` : 'failed: 0');
process.exit(failed ? 1 : 0);
