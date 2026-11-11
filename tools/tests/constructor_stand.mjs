// The test stand of the constructor: the tree of 26 buildings and 35 links the independent check built with the mouse
// (tools/tests/verify_constructor_build.mjs: the four start nodes, 22 new ones, long names, a node of three parents, branch colours), made here
// straight from its plan so the walk can measure it (tools/tests/constructor_walk.mjs). standDesign(startDesign) -> a design.
import * as T from '../../web/js/tree_model.mjs';

export const PLAN = [
    [0, 1, 'Склад пороха и прочих взрывчатых припасов'], [3, 1, 'Каркас с рунами'], [4, 1, 'Тир'],
    [1, 2, 'Мастерская инженеров гильдии'], [2, 2, 'Палуба'], [3, 2, 'Кузня'], [4, 2, 'Очень длинное название постройки для проверки переноса'], [5, 2, 'Арсенал'],
    [0, 3, 'Казармы'], [2, 3, 'Пушечная палуба с тремя родителями'], [3, 3, 'Купол'], [4, 3, 'Гарпун'], [5, 3, 'Склад'],
    [0, 4, 'Таверна'], [2, 4, 'Капитанский мостик Малакая Макаиссона'], [3, 4, 'Рубка'], [4, 4, 'Машинное отделение'], [5, 4, 'Мост'],
    [2, 5, 'Флагман'], [4, 5, 'Небесный якорь'], [0, 5, 'Вороньё гнездо'], [5, 5, 'Палата органных орудий'],
];
export const LINKS = [
    ['Заготовка под корабль', 'Склад пороха и прочих взрывчатых припасов'], ['Заготовка под корабль', 'Каркас с рунами'], ['Заготовка под корабль', 'Тир'],
    ['Прочный корпус', 'Мастерская инженеров гильдии'], ['Прочный корпус', 'Палуба'], ['Каркас с рунами', 'Палуба'], ['Каркас с рунами', 'Кузня'], ['Тир', 'Кузня'],
    ['Тир', 'Очень длинное название постройки для проверки переноса'], ['Тир', 'Арсенал'], ['Пивной чертог', 'Казармы'],
    ['Мастерская инженеров гильдии', 'Пушечная палуба с тремя родителями'], ['Палуба', 'Пушечная палуба с тремя родителями'], ['Кузня', 'Пушечная палуба с тремя родителями'],
    ['Кузня', 'Купол'], ['Очень длинное название постройки для проверки переноса', 'Гарпун'], ['Палуба', 'Гарпун'], ['Арсенал', 'Склад'],
    ['Казармы', 'Таверна'], ['Пушечная палуба с тремя родителями', 'Таверна'], ['Пушечная палуба с тремя родителями', 'Капитанский мостик Малакая Макаиссона'],
    ['Купол', 'Рубка'], ['Гарпун', 'Машинное отделение'], ['Купол', 'Машинное отделение'], ['Склад', 'Машинное отделение'], ['Склад', 'Мост'],
    ['Капитанский мостик Малакая Макаиссона', 'Флагман'], ['Машинное отделение', 'Флагман'], ['Таверна', 'Флагман'], ['Машинное отделение', 'Небесный якорь'],
    ['Таверна', 'Вороньё гнездо'], ['Мост', 'Палата органных орудий'],
];
export const COLOURS = [['Тир', 'blue'], ['Кузня', 'blue'], ['Купол', 'green'], ['Арсенал', 'red']];

export function standDesign(start) {
    const d = T.normalize(JSON.parse(JSON.stringify(start))).design;
    for (const [col, row, name] of PLAN) T.addNode(d, {name, col, row, cost: 1000, turns: 1});
    const id = name => d.nodes.find(n => n.name === name).id;
    for (const [a, b] of LINKS) T.addEdge(d, id(a), id(b));
    for (const [name, c] of COLOURS) T.byId(d, id(name)).branch = c;
    // the crew: two kinds on the forge, so a node carries more than one small card
    T.byId(d, id('Кузня')).crew = [{group: 'cannons', option: 'stock'}, {group: 'cannons', option: 'clatter'}];
    // a building with more than the game's window can hold: 10 lines, 4 crews, a long description (the window must keep every line and crew,
    // shorten the description with "…", and the constructor must warn of it)
    const flag = T.byId(d, id('Флагман'));
    flag.effects = Array.from({length: 10}, (_, i) => ({text: `Строка эффекта номер ${i + 1}: +${i + 1}%`, icon: null, good: i !== 3}));
    flag.crew = ['rakers', 'thunderers', 'pirates', 'quarrellers'].map(option => ({group: 'rifles', option}));
    flag.description = 'Флагман воздушного флота: на его палубе собраны лучшие мастера, а в трюмах хранится всё, что нужно для долгого похода. '.repeat(6).trim();
    return d;
}
