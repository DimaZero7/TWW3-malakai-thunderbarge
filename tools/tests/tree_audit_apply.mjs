// The audit of the author's tree (docs/design/tree-audit.md), as one script: reads a tree file, writes the tree with the audit's edits.
//   node tools/tests/tree_audit_apply.mjs IN OUT
// What it changes and why is in docs/design/tree-audit.md, «Правки по постройкам». It never moves a node (col, row) and never changes a link (requires);
// the numbers stay the author's (where the line's text and its number disagreed, the text he typed is taken and the question is in the audit).
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';
import * as T from '../../web/js/tree_model.mjs';
import * as FX from '../../web/js/effects_model.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', '..');
const json = p => JSON.parse(readFileSync(p.match(/^[A-Za-z]:|^\//) ? p : join(root, p), 'utf-8'));
const [IN = 'web/data/tree_design.json', OUT] = process.argv.slice(2);
const data = json('build/web/data.json'), catalog = json('build/web/catalog.json');
const units = Object.fromEntries(catalog.army_units.map(u => [u.key, u]));
const ctx = {groups: data.groups, gameEffects: Object.fromEntries(catalog.game_effects.map(g => [g.key, g])), unitName: k => (units[k] || {}).name || k};
const d = T.normalize(json(IN)).design;
const N = id => { const n = T.byId(d, id); if (!n) throw new Error('no node ' + id); return n; };
const ICON = k => `ui/buildings/icons/tww3_mtb_${k}.png`;

// ---- the kinds of lines ----
const G = (effect, value, more = {}) => ({kind: 'game', effect, value, ...more});
const GAME = {
    reserve: 'wh_main_effect_force_all_recruitment_points', growth: 'wh_main_effect_hordebuilding_growth_core', cost: 'wh_main_effect_force_all_campaign_recruitment_cost',
    upkeep: 'wh_main_effect_force_all_campaign_upkeep', beer: 'wh_main_effect_region_resource_beer_production', replenish: 'wh_main_effect_force_all_campaign_replenishment_rate',
    attrition: 'wh_main_effect_force_army_campaign_attrition_all_resistance', xp: 'wh_dlc05_effect_building_army_xp_gain', slayerCap: 'wh3_dlc25_effect_agent_cap_increase_dignitary_dwarfs',
    slayerOn: 'wh3_dlc25_effect_agent_enable_recruitment_dignitary_dragon_slayer', engCap: 'wh_main_effect_agent_cap_increase_engineer', engOn: 'wh_main_effect_agent_enable_recruitment_engineer',
    thunder: 'wh3_dlc25_effect_ability_enable_thunderburner_upgraded', iron: 'wh_main_effect_region_resource_iron_production',
};
const crew = (kind, target, value, more = {}) => ({kind, target, value, ...more});
// a node's line by its id: replaced by what it becomes (one effect), its id and the inherited line it stands for kept
function line(nodeId, effId, to) {
    const n = N(nodeId), i = n.effects.findIndex(e => e.id === effId);
    if (i < 0) throw new Error(`${nodeId}/${effId}: no such line`);
    const old = n.effects[i];
    n.effects[i] = {...to, id: old.id, ...(old.replaces ? {replaces: old.replaces} : {})};
}
const drop = (nodeId, effId) => { const n = N(nodeId); n.effects = n.effects.filter(e => e.id !== effId); };
const add = (nodeId, e) => { N(nodeId).effects.push(e); T.ensureIds(d); };
const note = (nodeId, text) => { const n = N(nodeId); n.note = (n.note ? n.note.replace(/\s+$/, '') + '\n' : '') + text; };

// ---- the hull ----
line('airship_hull_1', 'e1', G(GAME.reserve, 1));
line('airship_hull_1', 'e2', G(GAME.growth, 10));
// II and III inherit: the reserve +1 and the growth +10 of I went away with II (the game replaces the level in its slot) and came back on IV only
N('airship_hull_2').inherit = true;
N('airship_hull_3').inherit = true;
N('airship_hull_3').hide = ['airship_hull_2/e1'];     // «Открывает доступ к кораблю» is said once, on II
line('airship_hull_3', 'e1', G(GAME.slayerCap, 1));
line('airship_hull_3', 'e2', G(GAME.growth, 10));
line('airship_hull_3', 'e3', {kind: 'hp', value: 1000});
line('airship_hull_4', 'e1', G(GAME.slayerCap, 2));
line('airship_hull_4', 'e3', G(GAME.reserve, 2));
line('airship_hull_4', 'e2', G(GAME.growth, 20));
line('airship_hull_4', 'e4', {kind: 'missile_resist', value: 10});
line('airship_hull_4', 'e5', {kind: 'battle_speed', value: -5});
line('airship_hull_5', 'e4', G(GAME.growth, 30));
line('airship_hull_5', 'e1', {kind: 'hp', value: 2000});
line('airship_hull_5', 'e3', {kind: 'missile_resist', value: 15});
note('airship_hull_3', '→ сделано: значок перерисован — металлический каркас с открытыми рёбрами и рунными пластинами (tools/draw_building_icons.py, airship_hull_3). Каркас теперь наследует строки «Прочного корпуса»: резерв найма +1 не пропадает между I и IV.');

// ---- the beer hall ----
line('beer_hall_1', 'e1', G(GAME.cost, -10));
line('beer_hall_1', 'e2', G(GAME.upkeep, -5));
line('beer_hall_1', 'e3', G(GAME.beer, 5));
drop('beer_hall_1', 'e4');                            // «Открывает цепочку экипажа»: a line of the mod's old tree, the crew block says it now
line('beer_hall_1', 'e5', {kind: 'morale', value: 10});
add('beer_hall_1', G(GAME.slayerCap, 1));
note('beer_hall_1', '→ сделано: «Возможность найма» в игре только открывает найм, а нанять можно столько, сколько даёт «Численность героев» (эффект agent_cap, на фракцию). '
    + 'В стоке первая численность драконоборцев — у «Каркаса с рунами» (+1), а возможность — у «Прочного корпуса»: между ними нанять некого. Добавлена строка «Численность героев: +1 для драконоборцев». '
    + '«Столовая» теперь наследует строки чертога — возможность и численность не пропадают на II и III. Итог при всём дереве: 1 (чертог) + 2 (корпус IV–V) = 3 драконоборца, в стоке 2.\n'
    + '→ вопрос: «Дисциплина барки максимальная» записана как «Боевой дух барки» (в игре величины «дисциплина» нет). Если имелось в виду другое — скажи.');
N('beer_hall_2').inherit = true;
line('beer_hall_2', 'e1', G(GAME.cost, -15));
line('beer_hall_2', 'e2', G(GAME.upkeep, -7));
line('beer_hall_2', 'e3', G(GAME.beer, 10));
line('beer_hall_2', 'e4', {kind: 'morale', value: 15});
line('beer_hall_3', 'e1', G(GAME.cost, -30));
line('beer_hall_3', 'e2', G(GAME.upkeep, -25));
line('beer_hall_3', 'e4', {kind: 'morale', value: 30});
note('beer_hall_3', '«Содержание: -25% (для армии героя)» → эффект игры wh_main_effect_force_all_campaign_upkeep, область force_to_force_own: это и есть армия Малакая.');

// ---- the shooters' training ----
line('crew_weapons_1', 'e1', G(GAME.xp, 250));
line('crew_weapons_1', 'e2', crew('accuracy', 'rifles', 5));
line('crew_weapons_1', 'e3', crew('range', 'rifles', 5));
line('crew_weapons_1', 'e4', crew('reload', 'rifles', -5));
line('crew_weapons_2', 'e1', G(GAME.xp, 550));
line('crew_weapons_2', 'e2', crew('accuracy', 'rifles', 10));
line('crew_weapons_2', 'e3', crew('range', 'rifles', 10));
line('crew_weapons_2', 'e4', crew('reload', 'rifles', -7));
note('crew_weapons_2', 'Пометки в строках «(барки)», «(бараки)» учтены: дальность и перезарядка — у стрелков барки (экипажа), не у отрядов армии.');
line('crew_weapons_3', 'e1', G(GAME.xp, 880));
line('crew_weapons_3', 'e3', crew('accuracy', 'rifles', 15));
line('crew_weapons_3', 'e2', crew('accuracy', 'cannons', 45));
line('crew_weapons_3', 'e4', crew('reload', 'cannons', -3));
note('crew_weapons_3', '«Точность орудий +30% (нивелируем те 30 процентов что забрали) + 15% (накидываем сверху)» → одна строка «Меткость орудий барки: +45 %». '
    + 'Проценты одного вида в игре складываются: −30 % «Орудийной палубы» + 45 % = +15 % к стоку, как и задумано.');

// ---- the weapon stores: replenishment of the shooters of the dummies' line only (the author's note) ----
const dummyUnits = N('crew_weapons_1').units;               // crossbows: Забияки, Егеря (no gunpowder in this store)
line('infantry_workshop_1', 'e1', G(GAME.cost, -10));
line('infantry_workshop_1', 'e2', {kind: 'army_replenish', units: [...dummyUnits], value: 1, own_text: true, text: 'Скорость восполнения потерь: +1% для забияк и егерей'});
note('infantry_workshop_1', '→ сделано: строка — эффект «Скорость восполнения потерь» с адресатом «выбранные отряды»: Забияки и Егеря (обе версии), их открывает «Манекен для учебной стрельбы». '
    + 'Пираты и громобои не входят. В игре так делается эффектом на набор отрядов (bonus_value replenishment_percentage_bonus, образец wh3_dlc25_effect_force_replenishment_rate_dwf_arty_warmachines); в моде нужна разработка: свой набор отрядов и эффект на него.');
const lineUnits = [...new Set([...N('crew_weapons_1').units, ...N('crew_weapons_2').units, ...N('crew_weapons_3').units])];
line('infantry_workshop_2', 'e1', G(GAME.cost, -15));
line('infantry_workshop_2', 'e2', {kind: 'army_replenish', units: lineUnits, units_from: 'crew_weapons_1', value: 2, own_text: true, text: 'Скорость восполнения потерь: +2% для забияк, егерей, громобоев и злопыхателей'});
note('infantry_workshop_2', '«Скорость восполнения потерь: +2% (по аналогии с прошлой, только адаптировано под будущих стрелков этой ветки)» → эффект на отряды линейки «Манекен для учебной стрельбы»: '
    + 'арбалетчики первого склада и громобои со злопыхателями «Тира».\n→ вопрос: на втором складе огнестрел уже есть? Если нет — оставить только Забияк и Егерей (тогда +2% заменит +1% тем же отрядам).');

// ---- the nests ----
line('mtb_nest_1', 'e1', {kind: 'sight', value: 10});
N('mtb_nest_1').parts.push({part: null, name: 'Дозорные в гнёздах', zone: 'balloon', what: 'figures', figures: 2,
    note: 'В каждом из двух гнёзд на макушке шара — гном-дозорный без оружия (подзорная труба). Не стреляют, мест в бою не занимают, просто видны на модели; с метателями топоров («Гнёзда с боеукладкой») их место занимают метатели.'});
note('mtb_nest_1', '→ сделано: деталь «Дозорные в гнёздах» (2 фигуры без оружия, шар) в «Что появляется на корабле»; описание переписано под дозорных.');
line('mtb_nest_2', 'e1', {kind: 'sight', value: 15});
note('mtb_nest_2', '→ так и работает: «Гнёзда с боеукладкой» — следующий уровень линейки «Вороньих гнёзд» без наследования. В игре уровень заменяет прошлый в своём слоте, на странице постройка линейки действует старшим уровнем: обзор +15 %, не 10 + 15.');

// ---- the hold ----
line('cargo_hold_1', 'e1', G(GAME.replenish, 2));
line('cargo_hold_1', 'e2', G(GAME.growth, 5));
line('cargo_hold_1', 'e3', crew('ammo', 'rifles', 15));
line('cargo_hold_1', 'e4', crew('ammo', 'cupolas', 15));
line('cargo_hold_1', 'e5', {kind: 'battle_speed', value: -5});
line('cargo_hold_2', 'e1', G(GAME.replenish, 5));
line('cargo_hold_2', 'e2', G(GAME.attrition, -20));
line('cargo_hold_2', 'e3', G(GAME.growth, 10));
line('cargo_hold_2', 'e4', crew('ammo', 'rifles', 30));
line('cargo_hold_2', 'e5', crew('ammo', 'cupolas', 30));
line('cargo_hold_2', 'e6', {kind: 'battle_speed', value: -12});
line('cargo_hold_3', 'e1', G(GAME.replenish, 10));
line('cargo_hold_3', 'e2', G(GAME.attrition, -40));
line('cargo_hold_3', 'e4', crew('ammo', 'all', 100));
line('cargo_hold_3', 'e3', G(GAME.growth, 20));
line('cargo_hold_3', 'e5', {kind: 'battle_speed', value: -25});
note('cargo_hold_3', '→ сделано: на странице «каждой команды» и строка одной команды складываются (web/js/crew_model.mjs, тест tools/tests/crew_model_test.mjs): Люк +100 % всем и Торпедная галерея +30 % люкам дают люкам +130 %.\n'
    + '→ вопрос: на этом уровне убраны унаследованные «Боезапас стрелков +30 %» и «Боезапас куполов +30 %» Хранилища — у стрелков и куполов будет +100 %, а не +130 %. Так задумано? Если нет — «вернуть» их в унаследованных строках.');

// ---- the engines ----
line('engines_1', 'e1', G(GAME.thunder, 1));
line('engines_1', 'e2', {kind: 'campaign_movement', value: 5});
line('engines_1', 'e3', {kind: 'battle_speed', value: 7});
line('engines_2', 'e3', {kind: 'campaign_movement', value: 20});
line('engines_2', 'e4', {kind: 'battle_speed', value: 20});
line('engines_3', 'e3', {kind: 'campaign_movement', value: 40});
line('engines_3', 'e4', {kind: 'battle_speed', value: 60});

// ---- the engineer ----
line('engineering_workshop_1', 'e1', G(GAME.engOn, 1));
line('engineering_workshop_1', 'e2', crew('damage', 'rifles', 5));
line('engineering_workshop_1', 'e4', crew('reload', 'rifles', -5));
add('engineering_workshop_1', G(GAME.engCap, 1));
N('engineering_workshop_2').hide = [];               // the hire of the engineer was hidden on II: the cap alone hires nobody
line('engineering_workshop_2', 'e2', crew('reload', 'rifles', -6));
line('engineering_workshop_2', 'e3', crew('damage', 'rifles', 8));
line('engineering_workshop_2', 'e4', G(GAME.engCap, 1));
N('engineering_workshop_3').hide = [];               // «Число инженеров +1» of II: replaced by III's own cap of the same effect now
line('engineering_workshop_3', 'e1', G(GAME.engCap, 2));
line('engineering_workshop_3', 'e3', crew('reload', 'rifles', -10));
line('engineering_workshop_3', 'e4', crew('damage', 'rifles', 10));
line('engineering_workshop_3', 'e5', crew('reload', 'cannons', -10));
line('engineering_workshop_3', 'e6', crew('damage', 'cannons', 5));
line('engineering_workshop_3', 'e7', crew('range', 'cannons', 10));
note('engineering_workshop_1', '→ сделано: правило проверено по всему дереву (раздел «Правило 6» в docs/design/tree-audit.md). Скорость, перезарядка, боезапас, меткость, урон, дальность — только у команд барки, '
    + 'строки так и звучат: «… стрелков барки», «… орудий барки». Армии дерево даёт найм, стоимость, содержание, опыт, пополнение, рост. Нарушений по смыслу нет, были только формулировки.\n'
    + '→ сделано: на «Отсеке инженера» была убрана «Возможность найма героя: опытный инженер» — без неё численность никого не нанимает; возвращена. '
    + 'На «Верстаке» добавлена «Численность героев: +1 для опытных инженеров», как у драконоборцев.\n'
    + '→ вопрос: числа численности 1 / 1 / 2 по уровням: «Отсек» ничего не прибавляет к «Верстаку». Предлагаю 1 / 2 / 3.');

// ---- the signals ----
line('support_radius_1', 'e1', {kind: 'influence', value: 25});
line('support_radius_2', 'e1', {kind: 'influence', value: 50});
for (const [n, e] of [['support_radius_1', 'e2']]) { const x = N(n).effects.find(y => y.id === e); delete x.own_text; x.text = ''; }
for (const [n, e] of [['support_radius_1', 'e3']]) { const x = N(n).effects.find(y => y.id === e); delete x.own_text; }

// ---- the forge ----
line('artillery_workshop_1', 'e1', G(GAME.iron, 50));
line('artillery_workshop_2', 'e1', G(GAME.iron, 120));
note('artillery_workshop_1', '→ вопрос: в строке было число 30, а текст ты написал «50» (на «Облегчённых плавильнях» 60 и «120»). Взял текст: 50 и 120. Если правильные 30 и 60 — скажи.');

// ---- the guns ----
drop('mtb_guns_1', 'e1');      // the mod's line of the old tree («Крепление… ставится в панели экипажа»): an instruction; the crew block says what it opens
N('mtb_guns_1').parts.push({part: 'port'});
line('mtb_guns_2', 'e1', crew('accuracy', 'cannons', -30));
N('mtb_hatches_1').parts.push({part: 'bomb_hatches'});
N('support_radius_1').parts.push({part: 'porthole'});
line('mtb_torpedoes_1', 'e1', crew('ammo', 'bombs', 30));

// ---- the author's new buildings ----
const n1 = N('n1'), n2 = N('n2'), n3 = N('n3'), n4 = N('n4'), n5 = N('n5');
n1.name = 'Бортовые щиты';
n1.description = 'Вдоль бортов, как на старых драккарах, висят круглые щиты с железными умбонами. Стрелы и пули теперь чаще стучат по дереву и железу, чем по гномам.';
n1.icon = ICON('tree_side_shields');
line('n1', 'e1', {kind: 'missile_resist', value: 5});
line('n1', 'e2', {kind: 'battle_speed', value: -1});
n2.name = 'Щиты на шаре';
n2.description = 'Самое уязвимое место барки — шар над головой. Его бока закрыли клёпаными щитами: тяжело, зато оболочку не продырявит ни стрела, ни пуля.';
n2.icon = ICON('tree_balloon_shields');
line('n2', 'e1', {kind: 'missile_resist', value: 12});
line('n2', 'e2', {kind: 'battle_speed', value: -3});
n4.name = 'Броня двигателя';
n4.description = 'К корме вернулись доски-закрылки с железными накладками. Они прикрывают привод винта от выстрелов и служат рулём, хотя барка от них заметно тяжелеет.';
n4.icon = ICON('tree_engine_armour');
line('n4', 'e1', {kind: 'battle_speed', value: -10});
line('n4', 'e2', {kind: 'missile_resist', value: 20});
n4.parts.push({part: 'stern_armour'});
// one line of the ship's armour: II needs I and nothing else opens it, III the same; the numbers grow as a level's whole; the details stay along it
n2.prev = 'n1'; n2.inherit = true;
n4.prev = 'n2'; n4.inherit = true;
note('n1', '→ сделано: название «Бортовые щиты», описание, значок. Щиты → щиты на шаре → броня двигателя теперь одна линейка «обшивки» (уровни I–III с наследованием): '
    + 'каждая следующая требует прошлую и ничего больше её не открывает, числа растут как итог уровня (защита 5 → 12 → 20 %, скорость −1 → −3 → −10 %), детали на корабле при этом остаются все три. '
    + 'Так же экономятся два слота орды из 15. Если задумано, что три постройки складываются (итог защиты 37 %, скорости −14 %), — «Разорвать линейку» у «Щитов на шаре» и «Брони двигателя».');
note('n2', '→ сделано: название «Щиты на шаре» вместо «Новая постройка», описание, значок; уровень II линейки обшивки.');
note('n4', '→ сделано: это снятые с корпуса кормовые доски-руль (деталь чертежа stern_armour, в списке она называлась «Кормовые доски-руль», переименована в «Кормовая броня-руль (закрылки у винта)») — привязана. '
    + 'Название «Броня двигателя», описание, значок; уровень III линейки обшивки.\n→ вопрос: по решению 06.11 эта постройка даёт и манёвренность. Строки манёвренности нет: в игре эффекта на скорость поворота отряда нет, только через свою способность. Добавлять?');
n3.name = 'Баки форсажа';
n3.description = 'У привода винта встал бак высокого давления с красным вентилем. Котёл копит в нём пар впрок, а когда вентиль открывают, барка рвётся вперёд, будто её подтолкнул сам Грунгни.';
n3.icon = ICON('tree_forsage_tanks');
line('n3', 'e1', {kind: 'ability', target: 'mtb_forsage'});
note('n3', '→ сделано: название «Баки форсажа», описание, значок; строка — эффект «Способность в бою: Форсаж» (способность mtb_forsage уже есть в моде, сейчас её дают «Повышенная мощность двигателя» и «Большие пропеллеры» — при переносе enabled_by сменить на эту постройку). Деталь — «Бак «Форсажа» с красным вентилем».');
n5.description = 'Пороховой погреб обшит медью, чтобы ни одна искра не высеклась о гвоздь. Свет сюда идёт только через толстое стекло фонаря: без такой камеры огненную смесь под шаром не возят.';
n5.icon = ICON('tree_powder_room');
note('n5', '→ сделано: описание и значок (пороховой погреб в медной обшивке, фонарь за стеклом). Название твоё.\n→ вопрос: гранаты куполов открывают и она, и «Автоматизированная плавильня» — оставить одной из них?');

// ---- the icons of their own ----
for (const [id, k] of [['infantry_workshop_1', 'tree_infantry_workshop_1'], ['infantry_workshop_2', 'tree_infantry_workshop_2'],
    ['engineering_workshop_1', 'tree_engineering_workshop_1'], ['engineering_workshop_2', 'tree_engineering_workshop_2'], ['engineering_workshop_3', 'tree_engineering_workshop_3'],
    ['artillery_workshop_1', 'tree_artillery_workshop_1'], ['artillery_workshop_2', 'tree_artillery_workshop_2'], ['artillery_workshop_3', 'tree_artillery_workshop_3']]) N(id).icon = ICON(k);

// ---- the descriptions that no longer say what the building gives ----
N('infantry_workshop_1').description = 'Вдоль переборки тянутся стойки с арбалетами и топорами, у каждого крюка — бирка с руной. Пороха здесь не держат: этот склад для тетивы и стали.';
N('infantry_workshop_2').description = 'Склад разросся на полтрюма: к арбалетам добавились ружья в смазке, ящики с болтами и пулями уложены до самой палубы. Новобранцу тут найдётся оружие по руке.';
N('mtb_nest_1').description = 'Два гнезда на самой макушке шара. В каждом дежурит дозорный с подзорной трубой: оттуда видно дальше всех, и ни одна туча не подкрадётся незамеченной.';
N('mtb_nest_2').description = 'В гнёздах закрепили стойки с метательными топорами. Дозорный больше не только смотрит: топор, пущенный с высоты шара, летит вниз охотнее, чем вверх.';
N('mtb_guns_3').description = 'Четыре ствола на одном лафете бьют залпом, а заряжает их целая команда. Когда органное орудие заговорит, внизу замолкает всё остальное.';

// every effect of the catalogue made whole (its text by the pattern unless the author's own, its colour by its sense, its icon)
for (const n of d.nodes) n.effects = n.effects.map(e => (FX.isStructured(e) ? FX.complete(e, ctx) : e));
// the notes: no trailing empty line
for (const n of d.nodes) n.note = n.note.replace(/\n+$/, '');
T.ensureIds(d);
const text = T.serialize(d);
if (OUT) writeFileSync(OUT, text, 'utf-8'); else process.stdout.write(text);
