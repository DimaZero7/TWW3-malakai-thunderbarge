// The catalogue of a building's effects in the constructor, apart from any drawing: what kinds of effect a node can have, the line of text each
// makes (after the game's own wording), whether it is green or red, how a line the author typed by hand can be read as one of them, and what the
// mod has for each kind already. Pure functions over plain data: the constructor (web/js/constructor.js), the game's window (web/js/panel.js) and the
// test (node tools/tests/tree_model_test.mjs) use the same code.
//
// An effect of a node (web/data/tree_design.json, format 2):
//   {text, icon, good}                                  a free line, as before (format 1 had only these): no kind, the page does not know what it does
//   {kind, target?, effect?, value, text, icon, good, own_text?}
//     kind      'ammo' | 'accuracy' | 'range' | 'reload' | 'damage'        the crew's shooting (target: 'all' or a crew group of build/web/data.json)
//               'battle_speed' | 'campaign_movement' | 'sight' | 'influence'   the ship
//               'game'                                                       an effect of the game's table (effect: its key, build/web/catalog.json)
//     value     the number as the line shows it (percent for the percents)
//     text      the line; made from the kind's pattern while own_text is not set; the author's own words when it is (the structure stays)
//     good      green (true) or red (false): from the value's sign and the kind's sense, unless the author turned it (own_good)
//
// ctx for the functions: {groups: build/web/data.json groups, gameEffects: {key: catalog row}}.

const GI = 'ui/campaign ui/effect_bundles/';
export const DEFAULT_ICON = GI + 'general_ability.png';

// what the mod has for a kind: 'есть' (a mechanism of the mod already does it), 'нужна разработка', 'не проверено'; why: where it is
export const STATUS = {have: 'в моде уже есть механизм', dev: 'в моде потребуется разработка', unknown: 'не проверено'};

// The crew groups' names in the lines, as the mod writes them («Меткость стрелков», «Дальность и меткость орудий»): the genitive plural.
export const GROUP_GENITIVE = {rifles: 'стрелков', cannons: 'орудий', cupolas: 'куполов', bombs: 'бомбовых люков', harpoon: 'гарпуна', pub: 'паба', deck: 'палубы'};
// the groups whose shooting the crew kinds can change: the ones with a weapon of numbers (the harpoon is an ability, the deck and the pub do not shoot)
export const SHOOTING = groups => Object.keys(groups).filter(g => Object.values(groups[g].options).some(o => o.numbers && o.numbers.range));

// The kinds. pattern(target, ctx): the line's words before the value; percent: the value is a percent; positiveGood: a plus is good;
// status: what the mod has (docs/design/progression-proposal.md, data/crew_options.json, src/tww3_mtb_ammo.lua).
export const KINDS = {
    ammo: {section: 'crew', name: 'Боезапас', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
           words: t => (t === 'all' ? 'Боезапас каждой команды' : `Боезапас ${GROUP_GENITIVE[t] || 'группы «' + t + '»'}`),
           status: t => (t === 'all' ? ['have', 'один множитель на всех: уровень трюма уходит в бой через core:svr_save_string, src/tww3_mtb_ammo.lua умножает запас каждой группы (ammo_mod)']
                                     : ['dev', 'сейчас множитель один на все группы (ammo_mod, src/tww3_mtb_ammo.lua): нужен свой множитель на группу в той же строке реестра'])},
    accuracy: {section: 'crew', name: 'Меткость', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
               words: t => (t === 'all' ? 'Меткость каждой команды' : `Меткость ${GROUP_GENITIVE[t] || 'группы «' + t + '»'}`),
               status: () => ['have', 'boost группы в data/crew_options.json: копия снаряда на уровень, calibration_area × 0,95 / 0,90 / 0,85; «все команды» — boost в каждой группе']},
    range: {section: 'crew', name: 'Дальность стрельбы', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
            words: t => (t === 'all' ? 'Дальность стрельбы каждой команды' : `Дальность стрельбы ${GROUP_GENITIVE[t] || 'группы «' + t + '»'}`),
            status: () => ['have', 'boost группы: effective_range × 1,1 / 1,2 в копии снаряда (так сделано у орудий от сигнальной системы)']},
    reload: {section: 'crew', name: 'Время перезарядки', percent: true, positiveGood: false, icon: GI + 'general_ability.png',
             words: t => (t === 'all' ? 'Время перезарядки каждой команды' : `Время перезарядки ${GROUP_GENITIVE[t] || 'группы «' + t + '»'}`),
             status: () => ['dev', 'в boost группы нет base_reload_time: нужно добавить поле в копию снаряда, как calibration_area']},
    damage: {section: 'crew', name: 'Урон выстрела', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
             words: t => (t === 'all' ? 'Урон выстрела каждой команды' : `Урон выстрела ${GROUP_GENITIVE[t] || 'группы «' + t + '»'}`),
             status: () => ['dev', 'в boost группы нет damage и ap_damage: нужно добавить поля в копию снаряда']},
    battle_speed: {section: 'ship', name: 'Скорость барки в бою', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
                   words: () => 'Скорость барки на поле боя',
                   status: () => ['have', 'пассивные способности mtb_engine_speed_1..3 (scalar_speed 1,05 / 1,10 / 1,15) включаются эффектом постройки; новое число — новая строка способности']},
    campaign_movement: {section: 'ship', name: 'Дальность перемещения по карте', game: 'wh_main_effect_force_all_campaign_movement_range'},
    sight: {section: 'ship', name: 'Обзор на карте кампании', game: 'wh_main_effect_agent_field_line_of_sight_mod'},
    influence: {section: 'ship', name: 'Размер зоны влияния', game: 'wh3_dlc25_effect_force_stat_support_radius'},
    game: {section: 'game', name: 'Эффект игры'},
};
export const CREW_KINDS = ['ammo', 'accuracy', 'range', 'reload', 'damage'];
export const SHIP_KINDS = ['battle_speed', 'campaign_movement', 'sight', 'influence'];
export const SECTIONS = {crew: 'Экипаж', ship: 'Корабль', game: 'Игра', text: 'Своя строка'};
const GAME_STATUS = ['have', 'строка building_effects_junction у постройки, как у стоковых построек (tools/build.py пишет такие строки в таблицу мода)'];

const num = v => (Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100).replace('.', ','));
const signed = v => (v > 0 ? '+' : v < 0 ? '-' : '') + num(Math.abs(v));       // the hyphen, as the game's lines write a minus

// the game's row of a kind that is a game effect
const gameRow = (e, ctx) => (ctx.gameEffects || {})[e.kind === 'game' ? e.effect : (KINDS[e.kind] || {}).game];

export function isStructured(e) { return !!(e && e.kind && e.kind !== 'text' && KINDS[e.kind]); }
export const isCrew = e => isStructured(e) && CREW_KINDS.includes(e.kind);

// The line of an effect after the game's own pattern: the mod's lines «Меткость стрелков: +5 %», the game's template with its %+n / %n.
export function makeText(e, ctx = {}) {
    const k = KINDS[e.kind];
    if (!k) return e.text || '';
    const g = gameRow(e, ctx);
    if (g) {
        const t = g.text;
        if (t.includes('%+n')) return t.replace('%+n', signed(e.value));
        if (t.includes('%n')) return t.replace('%n', num(e.value));
        return t;
    }
    if (k.game) return `${k.name}: ${signed(e.value)}%`;     // the catalogue not exported yet: the kind's own name
    return `${k.words(e.target || 'all')}: ${signed(e.value)}${k.percent ? ' %' : ''}`;
}

// green or red: the sign of the value and whether the kind's plus is good (the game's is_positive_value_good); 0 counts as good
export function goodOf(e, ctx = {}) {
    const k = KINDS[e.kind];
    if (!k) return e.good !== false;
    const g = gameRow(e, ctx);
    const plusGood = g ? g.positive_good !== false : k.positiveGood !== false;
    return e.value === 0 || (e.value > 0) === plusGood;
}
export function iconOf(e, ctx = {}) {
    const g = gameRow(e, ctx);
    return (g && g.icon) || (KINDS[e.kind] && KINDS[e.kind].icon) || DEFAULT_ICON;
}
export function statusOf(e, ctx = {}) {
    const k = KINDS[e.kind];
    if (!k) return ['unknown', 'свободная строка: что она делает, страница не знает'];
    if (k.status) return k.status(e.target || 'all');
    return GAME_STATUS;
}
// the effect's name for people, with its target: «Боезапас, стрелки», «Опыт за ход»
export function labelOf(e, ctx = {}) {
    const k = KINDS[e.kind];
    if (!k) return 'Своя строка';
    if (e.kind === 'game') { const g = gameRow(e, ctx); return g ? g.text.replace(/:?\s*%\+?n%?/, '').replace(/\s+/g, ' ').trim() : e.effect; }
    if (CREW_KINDS.includes(e.kind)) return `${k.name}, ${e.target === 'all' || !e.target ? 'все команды' : ((ctx.groups || {})[e.target] || {}).name?.toLowerCase() || e.target}`;
    return k.name;
}

// An effect made whole: the text and the colour follow the pattern unless the author set his own; the icon the kind's when none is set.
export function complete(e, ctx = {}) {
    // the effect's id and the inherited line it stands for go with it (web/js/tree_model.mjs, the lines of levels)
    const tail = o => { if (e.id) o.id = e.id; if (e.replaces) o.replaces = e.replaces; return o; };
    if (!isStructured(e)) return tail({text: String(e.text ?? ''), icon: e.icon || null, good: e.good !== false});
    const out = {kind: e.kind};
    if (CREW_KINDS.includes(e.kind)) out.target = e.target || 'all';
    if (e.kind === 'game') out.effect = e.effect;
    out.value = Number.isFinite(Number(e.value)) ? Number(e.value) : 0;
    out.own_text = !!e.own_text;
    out.text = out.own_text ? String(e.text ?? '') : makeText(out, ctx);
    out.own_good = !!e.own_good;
    out.good = out.own_good ? e.good !== false : goodOf(out, ctx);
    out.icon = e.icon || iconOf(out, ctx);
    return tail(out);
}

// A new effect of a kind (the catalogue's choice): the value the game uses most for a game effect, 5 otherwise
export function newEffect(kind, opts = {}, ctx = {}) {
    const e = {kind, ...(CREW_KINDS.includes(kind) ? {target: opts.target || 'all'} : {}), ...(kind === 'game' ? {effect: opts.effect} : {})};
    const g = gameRow(e, ctx);
    e.value = opts.value ?? (g && g.values && g.values.length ? g.values[Math.floor(g.values.length / 2)] : kind === 'reload' ? -10 : 5);
    if (g && !/%\+?n/.test(g.text)) e.value = opts.value ?? (g.values && g.values[0]) ?? 1;
    return complete(e, ctx);
}

// The catalogue's entries for the picker: [{section, kind, target?, effect?, title, sub, icon, status, search}]
export function catalogue(ctx = {}) {
    const out = [];
    const groups = ctx.groups || {};
    for (const kind of CREW_KINDS) {
        for (const t of ['all', ...SHOOTING(groups)]) {
            const e = {kind, target: t, value: kind === 'reload' ? -10 : 5};
            out.push({section: 'crew', kind, target: t, title: KINDS[kind].name, sub: t === 'all' ? 'все команды' : (groups[t] || {}).name || t, icon: KINDS[kind].icon,
                      status: statusOf(e, ctx), sample: makeText(e, ctx)});
        }
    }
    for (const kind of SHIP_KINDS) {
        const e = {kind, value: 5};
        out.push({section: 'ship', kind, title: KINDS[kind].name, sub: KINDS[kind].game ? 'эффект игры' : 'способность мода', icon: iconOf(e, ctx), status: statusOf(e, ctx), sample: makeText(e, ctx)});
    }
    const shipKeys = new Set(SHIP_KINDS.map(k => KINDS[k].game).filter(Boolean));
    for (const g of Object.values(ctx.gameEffects || {})) {
        if (shipKeys.has(g.key)) continue;
        const e = {kind: 'game', effect: g.key, value: g.values && g.values.length ? g.values[Math.floor(g.values.length / 2)] : 1};
        out.push({section: 'game', kind: 'game', effect: g.key, title: labelOf(e, ctx), sub: g.category === 'battle' ? 'в бою' : 'на карте', icon: g.icon || DEFAULT_ICON,
                  status: GAME_STATUS, sample: makeText(e, ctx), uses: g.uses || 0});
    }
    for (const x of out) x.search = `${x.title} ${x.sub} ${x.sample} ${x.effect || ''}`.toLowerCase().replace(/ё/g, 'е');
    out.push({section: 'text', kind: 'text', title: 'Своя строка', sub: 'свободный текст: страница не знает, что он делает', icon: GI + 'general_ability.png', status: ['unknown', 'свободная строка'], sample: '', search: 'своя строка текст'});
    return out;
}

// ---- reading a line the author typed as an effect of the catalogue ----
// Tolerant of the typos of a quick hand («пермешения», «кмопании», «пок арте»): the words are looked for in the line with its spaces taken out, by
// their stems. -> [effect] (one line may say two: «Дальность и меткость орудий: +10 %»), or [] when it does not read.
const squash = s => String(s).toLowerCase().replace(/ё/g, 'е').replace(/[\s ]+/g, '');
function valueIn(text) {
    const m = [...String(text).replace(/−/g, '-').matchAll(/([+-]?)\s*(\d+(?:[.,]\d+)?)/g)];
    if (!m.length) return null;
    const last = m[m.length - 1];
    return (last[1] === '-' ? -1 : 1) * Number(last[2].replace(',', '.'));
}
const GROUP_STEMS = [['rifles', ['стрелк', 'стрелок']], ['cannons', ['оруди', 'пушк', 'пушек']], ['cupolas', ['купол', 'гнезд']], ['bombs', ['бомб', 'люк']]];
function targetIn(s, groups) {
    if (/кажд|всех|всем|команд/.test(s) && !GROUP_STEMS.some(([, st]) => st.some(x => s.includes(x)))) return 'all';
    for (const [g, stems] of GROUP_STEMS) if (groups[g] && stems.some(x => s.includes(x))) return g;
    return /кажд|всех|всем/.test(s) ? 'all' : null;
}
export function recognize(text, ctx = {}) {
    const s = squash(text), v = valueIn(text), groups = ctx.groups || {};
    if (!s) return [];
    const crew = kind => { const t = targetIn(s, groups); return t && v !== null ? [complete({kind, target: t, value: v}, ctx)] : []; };
    if (/боезапас|боеприпас|запаскажд/.test(s)) return crew('ammo');
    if (/дальност.*иметкост|меткост.*идальност/.test(s)) { const t = targetIn(s, groups); return t && v !== null ? ['range', 'accuracy'].map(kind => complete({kind, target: t, value: v}, ctx)) : []; }
    if (/меткост/.test(s)) return crew('accuracy');
    if (/перезаряд/.test(s)) return crew('reload');
    if (/урон/.test(s) && targetIn(s, groups) && !/%для|для/.test(s)) return crew('damage');
    if (/обзор/.test(s) && v !== null) return [complete({kind: 'sight', value: v}, ctx)];
    if (/зон\S*влиян/.test(s) && v !== null) return [complete({kind: 'influence', value: v}, ctx)];
    if (/(скорост|ход)/.test(s) && /(бо[йяе]|пол[ея]боя|сражен)/.test(s) && v !== null) return [complete({kind: 'battle_speed', value: v}, ctx)];
    if (/карт/.test(s) && /(дальн|даотн|перемещ|пермещ|пермеш|скорост|передвиж)/.test(s) && v !== null) return [complete({kind: 'campaign_movement', value: v}, ctx)];
    // the game's own lines, by their templates: the words as they are, the value where %+n or %n stands
    for (const g of Object.values(ctx.gameEffects || {})) {
        const parts = g.text.split(/(%\+n|%n)/);
        const re = new RegExp('^' + parts.map(p => (p === '%+n' ? '([+\\-−]?\\d+(?:[.,]\\d+)?)' : p === '%n' ? '([+\\-−]?\\d+(?:[.,]\\d+)?)' : squash(p).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))).join('') + '$');
        const m = re.exec(s.replace(/−/g, '-'));
        if (!m) continue;
        const value = m[1] !== undefined ? Number(m[1].replace(',', '.').replace('−', '-')) : (g.values && g.values[0]) ?? 1;
        return [complete({kind: g.key === KINDS.campaign_movement.game ? 'campaign_movement' : g.key === KINDS.sight.game ? 'sight' : g.key === KINDS.influence.game ? 'influence' : 'game',
                          effect: g.key, value}, ctx)];
    }
    return [];
}
// The proposal for a free line: what it would become, said in a few words («Боезапас, все команды, +25 %»), and the effects themselves. The line's
// text stays the author's (own_text), the colour follows the sense. null: nothing to propose.
export function proposal(e, ctx = {}) {
    if (isStructured(e) || !String(e.text || '').trim()) return null;
    const found = recognize(e.text, ctx);
    if (!found.length) return null;
    const effects = found.map((x, i) => complete({...x, own_text: found.length === 1, text: found.length === 1 ? e.text : undefined, icon: e.icon && found.length === 1 ? e.icon : null}, ctx));
    const say = effects.map(x => `${labelOf(x, ctx)}, ${signed(x.value)}${KINDS[x.kind].percent || (gameRow(x, ctx) || {}).text?.includes('%+n%') ? '\u00a0%' : ''}`).join('; ');
    return {effects, say, colour: effects.some(x => x.good !== (e.good !== false)) ? (effects[0].good ? 'станет зелёной' : 'станет красной') : null};
}

// ---- what the crew's shooting gets from the buildings that stand ----
// sources: [{effect, from: the building's name, mod?: true for the mod's own number of a mod building (ammo_mod, boost)}]. -> {kind: {pct, from:
// [{name, value}]}} for the crew kinds, the percents of every source that acts on this group added up (the game adds effects of one kind).
export function crewBonuses(sources, group) {
    const out = Object.fromEntries(CREW_KINDS.map(k => [k, {pct: 0, from: []}]));
    for (const {effect: e, from, mod} of sources) {
        if (!isCrew(e) || !(e.target === 'all' || !e.target || e.target === group)) continue;
        out[e.kind].pct += e.value;
        out[e.kind].from.push({name: from, value: e.value, mod: !!mod});
    }
    return out;
}
// A number of the crew's weapon with a bonus: ammunition, range and damage round to whole, the reload to a tenth
export function applyPct(base, pct, kind) {
    const v = base * (1 + pct / 100);
    return kind === 'reload' ? Math.round(v * 10) / 10 : Math.round(v);
}
export const signedPct = (v, space = true) => signed(v) + (space ? ' %' : '%');
