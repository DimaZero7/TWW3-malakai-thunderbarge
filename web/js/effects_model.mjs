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

// The crew groups' names in the lines, as the mod writes them («Меткость стрелков», «Дальность и меткость орудий»): the genitive plural. The lines say
// «барки» after them (the author's rule: the bonuses of the shooting are the barge's crew's, never the army's units; docs/design/tree-audit.md).
export const GROUP_GENITIVE = {rifles: 'стрелков', cannons: 'орудий', cupolas: 'куполов', bombs: 'бомбовых люков', harpoon: 'гарпуна', pub: 'паба', deck: 'палубы'};
// the groups whose shooting the crew kinds can change: the ones with a weapon of numbers (the harpoon is an ability, the deck and the pub do not shoot)
export const SHOOTING = groups => Object.keys(groups).filter(g => Object.values(groups[g].options).some(o => o.numbers && o.numbers.range));

// The kinds. pattern(target, ctx): the line's words before the value; percent: the value is a percent; positiveGood: a plus is good;
// status: what the mod has (docs/design/progression-proposal.md, data/crew_options.json, src/tww3_mtb_ammo.lua).
export const KINDS = {
    ammo: {section: 'crew', name: 'Боезапас', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
           words: t => (t === 'all' ? 'Боезапас каждой команды барки' : `Боезапас ${GROUP_GENITIVE[t] || 'группы «' + t + '»'} барки`),
           status: t => (t === 'all' ? ['have', 'один множитель на всех: уровень трюма уходит в бой через core:svr_save_string, src/tww3_mtb_ammo.lua умножает запас каждой группы (ammo_mod)']
                                     : ['dev', 'сейчас множитель один на все группы (ammo_mod, src/tww3_mtb_ammo.lua): нужен свой множитель на группу в той же строке реестра'])},
    accuracy: {section: 'crew', name: 'Меткость', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
               words: t => (t === 'all' ? 'Меткость каждой команды барки' : `Меткость ${GROUP_GENITIVE[t] || 'группы «' + t + '»'} барки`),
               status: () => ['have', 'boost группы в data/crew_options.json: копия снаряда на уровень, calibration_area × 0,95 / 0,90 / 0,85; «все команды» — boost в каждой группе']},
    range: {section: 'crew', name: 'Дальность стрельбы', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
            words: t => (t === 'all' ? 'Дальность стрельбы каждой команды барки' : `Дальность стрельбы ${GROUP_GENITIVE[t] || 'группы «' + t + '»'} барки`),
            status: () => ['have', 'boost группы: effective_range × 1,1 / 1,2 в копии снаряда (так сделано у орудий от сигнальной системы)']},
    reload: {section: 'crew', name: 'Время перезарядки', percent: true, positiveGood: false, icon: GI + 'general_ability.png',
             words: t => (t === 'all' ? 'Время перезарядки каждой команды барки' : `Время перезарядки ${GROUP_GENITIVE[t] || 'группы «' + t + '»'} барки`),
             status: () => ['dev', 'в boost группы нет base_reload_time: нужно добавить поле в копию снаряда, как calibration_area']},
    damage: {section: 'crew', name: 'Урон выстрела', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
             words: t => (t === 'all' ? 'Урон выстрела каждой команды барки' : `Урон выстрела ${GROUP_GENITIVE[t] || 'группы «' + t + '»'} барки`),
             status: () => ['dev', 'в boost группы нет damage и ap_damage: нужно добавить поля в копию снаряда']},
    battle_speed: {section: 'ship', name: 'Скорость барки в бою', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
                   words: () => 'Скорость барки на поле боя',
                   status: () => ['have', 'пассивные способности mtb_engine_speed_1..3 (scalar_speed 1,05 / 1,10 / 1,15) включаются эффектом постройки; новое число (и минус: трюм, броня) — новая строка способности того же образца']},
    // the barge itself in battle (the unit of Malakai on the barge, the mod's unit set mtb_dwf_malakai_thunderbarge)
    missile_resist: {section: 'ship', name: 'Защита барки от выстрелов', percent: true, positiveGood: true, icon: GI + 'general_ability.png',
                     words: () => 'Защита барки от выстрелов',
                     status: () => ['dev', 'в игре есть образец: wh3_dlc25_effect_force_stat_missile_resistance_dwf_thunderbarge (сопротивление обстрелу, bonus_value unit_damage_resistance_missile_mod) на набор dwf_thunderbarge, барка мода в него не входит. Нужен свой эффект на набор mtb_dwf_malakai_thunderbarge и строка постройки, как у способностей мода. Сопротивления в игре складываются и ограничены 90 %']},
    hp: {section: 'ship', name: 'Здоровье барки', percent: false, positiveGood: true, icon: GI + 'general_ability.png',
         words: () => 'Здоровье барки',
         status: () => ['dev', 'эффекта игры на очки здоровья отряда нет (среди bonus_value есть только барьер battle_barrier_health). Здоровье барки — bonus_hit_points отряда в land_units (у «Духа Грунгни» 12 340): нужна копия отряда на уровень корпуса и его подмена, или барьер вместо здоровья']},
    morale: {section: 'ship', name: 'Боевой дух барки', percent: false, positiveGood: true, icon: GI + 'general_ability.png',
             words: () => 'Боевой дух барки',
             status: () => ['dev', 'в игре есть: bonus_value morale на набор отрядов (эффекты effect_bonus_value_ids_unit_sets). Нужен свой эффект на набор mtb_dwf_malakai_thunderbarge']},
    ability: {section: 'ship', name: 'Способность в бою', percent: false, positiveGood: true, valueless: true, icon: GI + 'general_ability.png',
              words: (t, ctx = {}) => `Способность «${abilityOf(t, ctx).name}»`,
              status: (t, ctx = {}) => (abilityOf(t, ctx).mod ? ['have', `способность ${t} уже есть в моде (data/crew_options.json, abilities): включается эффектом постройки на набор барки, enabled_by — ключ уровня`]
                                                            : ['dev', 'своей способности в моде нет: строки unit_abilities и фаз по образцу abilities в data/crew_options.json'])},
    campaign_movement: {section: 'ship', name: 'Дальность перемещения по карте', game: 'wh_main_effect_force_all_campaign_movement_range'},
    sight: {section: 'ship', name: 'Обзор на карте кампании', game: 'wh_main_effect_agent_field_line_of_sight_mod'},
    influence: {section: 'ship', name: 'Размер зоны влияния', game: 'wh3_dlc25_effect_force_stat_support_radius'},
    // the army's units chosen by the author (the units the tree opens, or the units a line of it opens): a number of the game for those units only
    army_replenish: {section: 'army', name: 'Скорость восполнения потерь', percent: true, positiveGood: true, icon: GI + 'replenishment.png', bonus: 'replenishment_percentage_bonus',
                     sample: 'wh3_dlc25_effect_force_replenishment_rate_dwf_arty_warmachines (на наборы dwf_artillery, dwf_flying_war_machines)'},
    army_cost: {section: 'army', name: 'Стоимость найма', percent: true, positiveGood: false, icon: GI + 'treasury.png', bonus: 'cost_mod',
                sample: 'wh2_main_effect_resource_recruitment_cost_reduction_dwf_quarreler_ranger_grudge_boltthrower'},
    army_upkeep: {section: 'army', name: 'Содержание', percent: true, positiveGood: false, icon: GI + 'military_spending.png', bonus: 'upkeep_mod',
                  sample: 'wh2_main_effect_resource_upkeep_cost_reduction_dwf_quarreler_ranger_grudge_boltthrower'},
    // the recruitment into the barge's own army: the horde's slots of recruitment («Резерв найма орды», for the dwarfs «Резерв найма команд воздушного
    // корабля»), the units its buildings allow (building_units_allowed). The game's own effect of the Spirit of Grungni's beer hall, scope force_to_force_own
    horde_cost: {section: 'horde', name: 'Стоимость найма в барке', game: 'wh_main_effect_force_all_campaign_recruitment_cost', scope: 'force_to_force_own',
                 status: () => ['have', 'эффект игры wh_main_effect_force_all_campaign_recruitment_cost с областью force_to_force_own, как у ванильного «Пивного чертога» I–II: скидка на найм в эту армию — '
                     + 'в слоты найма орды, из отрядов, которые разрешают её постройки (building_units_allowed). Не фракция и не провинция. Текст строки — игры: «Стоимость найма: %+n%»']},
    game: {section: 'game', name: 'Эффект игры'},
};
export const CREW_KINDS = ['ammo', 'accuracy', 'range', 'reload', 'damage'];
export const SHIP_KINDS = ['battle_speed', 'missile_resist', 'hp', 'morale', 'ability', 'campaign_movement', 'sight', 'influence'];
export const ARMY_KINDS = ['army_replenish', 'army_cost', 'army_upkeep'];
export const HORDE_KINDS = ['horde_cost'];
for (const k of ARMY_KINDS) KINDS[k].status = () => ['dev', `в игре есть: bonus_value ${KINDS[k].bonus} на набор отрядов (образец ${KINDS[k].sample}). Нужен свой набор из выбранных отрядов (unit_sets, unit_set_to_unit_junctions), эффект на него (effect_bonus_value_ids_unit_sets) и строка постройки`];
export const SECTIONS = {crew: 'Экипаж', ship: 'Корабль', horde: 'Найм в барке', army: 'Армия: выбранные отряды', game: 'Игра', text: 'Своя строка'};
// the abilities a building can open: the mod's own (data/crew_options.json, abilities; ctx.abilities over them)
export const ABILITIES = {mtb_forsage: {name: 'Форсаж', mod: true}};
const abilityOf = (t, ctx = {}) => ({...(ABILITIES[t] || {name: t || '…', mod: false}), ...((ctx.abilities || {})[t] || {})});
// the units of an army effect in its line: their names without the variant in brackets, each once («Забияки», «Егеря»)
export function unitsWords(units, ctx = {}) {
    const name = k => String((ctx.unitName ? ctx.unitName(k) : k) || k).replace(/\s*\(.*\)\s*$/, '');
    return [...new Set((units || []).map(name))];
}
const GAME_STATUS = ['have', 'строка building_effects_junction у постройки, как у стоковых построек (tools/build.py пишет такие строки в таблицу мода)'];

const num = v => (Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100).replace('.', ','));
const signed = v => (v > 0 ? '+' : v < 0 ? '-' : '') + num(Math.abs(v));       // the hyphen, as the game's lines write a minus

// the game's row of a kind that is a game effect
const gameRow = (e, ctx) => (ctx.gameEffects || {})[e.kind === 'game' ? e.effect : (KINDS[e.kind] || {}).game];

export function isStructured(e) { return !!(e && e.kind && e.kind !== 'text' && KINDS[e.kind]); }
export const isCrew = e => isStructured(e) && CREW_KINDS.includes(e.kind);
export const isArmy = e => isStructured(e) && ARMY_KINDS.includes(e.kind);

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
    if (k.valueless) return k.words(e.target, ctx);
    if (ARMY_KINDS.includes(e.kind)) {
        const w = unitsWords(e.units, ctx);
        return `${k.name}: ${signed(e.value)}% ${w.length ? 'для отрядов: ' + w.join(', ') : 'для всех отрядов армии'}`;
    }
    return `${k.words(e.target || 'all', ctx)}: ${signed(e.value)}${k.percent ? ' %' : ''}`;
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
    if (k.status) return k.status(e.target || 'all', ctx);
    return GAME_STATUS;
}
// the effect's name for people, with its target: «Боезапас, стрелки», «Опыт за ход», «Скорость восполнения потерь, 4 отряда»
export function labelOf(e, ctx = {}) {
    const k = KINDS[e.kind];
    if (!k) return 'Своя строка';
    if (e.kind === 'game') { const g = gameRow(e, ctx); return g ? g.text.replace(/:?\s*%\+?n%?/, '').replace(/\s+/g, ' ').trim() : e.effect; }
    if (CREW_KINDS.includes(e.kind)) return `${k.name}, ${e.target === 'all' || !e.target ? 'все команды' : ((ctx.groups || {})[e.target] || {}).name?.toLowerCase() || e.target}`;
    if (ARMY_KINDS.includes(e.kind)) { const w = unitsWords(e.units, ctx); return `${k.name}, ${w.length ? w.join(', ') : 'вся армия'}`; }
    if (e.kind === 'ability') return k.words(e.target, ctx);
    return k.name;
}

// An effect made whole: the text and the colour follow the pattern unless the author set his own; the icon the kind's when none is set.
export function complete(e, ctx = {}) {
    // the effect's id and the inherited line it stands for go with it (web/js/tree_model.mjs, the lines of levels)
    const tail = o => { if (e.id) o.id = e.id; if (e.replaces) o.replaces = e.replaces; return o; };
    if (!isStructured(e)) return tail({text: String(e.text ?? ''), icon: e.icon || null, good: e.good !== false});
    const out = {kind: e.kind};
    if (CREW_KINDS.includes(e.kind)) out.target = e.target || 'all';
    if (e.kind === 'ability') out.target = e.target || Object.keys(ABILITIES)[0];
    if (ARMY_KINDS.includes(e.kind)) { out.units = [...new Set((e.units || []).map(String))]; if (e.units_from) out.units_from = String(e.units_from); }
    if (e.kind === 'game') out.effect = e.effect;
    out.value = KINDS[e.kind].valueless ? 1 : Number.isFinite(Number(e.value)) ? Number(e.value) : 0;
    out.own_text = !!e.own_text;
    out.text = out.own_text ? String(e.text ?? '') : makeText(out, ctx);
    out.own_good = !!e.own_good;
    out.good = out.own_good ? e.good !== false : goodOf(out, ctx);
    out.icon = e.icon || iconOf(out, ctx);
    return tail(out);
}

// A new effect of a kind (the catalogue's choice): the value the game uses most for a game effect, 5 otherwise
export function newEffect(kind, opts = {}, ctx = {}) {
    const e = {kind, ...(CREW_KINDS.includes(kind) ? {target: opts.target || 'all'} : {}), ...(kind === 'game' ? {effect: opts.effect} : {}),
               ...(kind === 'ability' ? {target: opts.target || Object.keys(ABILITIES)[0]} : {}),
               ...(ARMY_KINDS.includes(kind) ? {units: opts.units || [], ...(opts.units_from ? {units_from: opts.units_from} : {})} : {})};
    const g = gameRow(e, ctx);
    e.value = opts.value ?? (g && g.values && g.values.length ? g.values[Math.floor(g.values.length / 2)] : kind === 'reload' || kind === 'army_cost' || kind === 'army_upkeep' ? -10 : kind === 'hp' ? 500 : 5);
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
        if (kind === 'ability') {
            for (const t of Object.keys({...ABILITIES, ...(ctx.abilities || {})})) {
                const e = {kind, target: t, value: 1};
                out.push({section: 'ship', kind, target: t, title: KINDS[kind].name, sub: abilityOf(t, ctx).name, icon: iconOf(e, ctx), status: statusOf(e, ctx), sample: makeText(e, ctx)});
            }
            continue;
        }
        const e = {kind, value: kind === 'hp' ? 500 : 5};
        out.push({section: 'ship', kind, title: KINDS[kind].name, sub: KINDS[kind].game ? 'эффект игры' : 'барка в бою', icon: iconOf(e, ctx), status: statusOf(e, ctx), sample: makeText(e, ctx)});
    }
    for (const kind of HORDE_KINDS) {
        const e = {kind, value: -10};
        out.push({section: 'horde', kind, title: KINDS[kind].name, sub: 'эффект игры, своя армия-орда', icon: iconOf(e, ctx), status: statusOf(e, ctx), sample: makeText(e, ctx)});
    }
    for (const kind of ARMY_KINDS) {
        const e = {kind, units: [], value: KINDS[kind].positiveGood ? 5 : -10};
        out.push({section: 'army', kind, title: KINDS[kind].name, sub: 'для выбранных отрядов', icon: iconOf(e, ctx), status: statusOf(e, ctx), sample: makeText(e, ctx).replace('для всех отрядов армии', 'для выбранных отрядов')});
    }
    const shipKeys = new Set([...SHIP_KINDS, ...HORDE_KINDS].map(k => KINDS[k].game).filter(Boolean));
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
    if (/меткост|точност/.test(s)) return crew('accuracy');
    if (/перезаряд|перезряд|перзаряд|перезардя/.test(s)) return crew('reload');
    if (/урон/.test(s) && targetIn(s, groups) && !/%для|для/.test(s)) return crew('damage');
    // the barge itself: protection from shots, health, the «discipline» (its morale), an ability
    const barge = /барк|барж|барак|корабл/.test(s);
    if (/форсаж/.test(s)) return [complete({kind: 'ability', target: 'mtb_forsage'}, ctx)];
    if (/защит/.test(s) && /выстрел|вытсрел|выстерл|обстрел/.test(s) && v !== null) return [complete({kind: 'missile_resist', value: v}, ctx)];
    if (/здоров|здоро[яй]/.test(s) && barge && v !== null) return [complete({kind: 'hp', value: v}, ctx)];
    if (/дисциплин|боевойдух/.test(s) && v !== null) return [complete({kind: 'morale', value: v}, ctx)];
    if (/скорост/.test(s) && barge && !/карт/.test(s) && v !== null) return [complete({kind: 'battle_speed', value: v}, ctx)];
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
        const own = [...SHIP_KINDS, ...HORDE_KINDS].find(k => KINDS[k].game === g.key);
        return [complete({kind: own || 'game', effect: g.key, value}, ctx)];
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
