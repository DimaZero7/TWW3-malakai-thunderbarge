# Уровни постройки в игре: отряды и эффекты на уровне

Справка для страницы (`web/js/panel.js`, `web/js/tree_model.mjs`) и для переноса в Lua. Что проверено по файлам игры и что выведено.

## 1. Данные: что игра хранит на каждом уровне

Таблица `building_units_allowed` (db.pack, `db\building_units_allowed_tables\data__`): строка = постройка-уровень + отряд.
**Каждый следующий уровень повторяет все отряды предыдущих** — список уровня полный, не прирост.

Пример: казармы гномов `wh_main_dwf_barracks_*` (прочитано из таблицы игры):

| уровень | отряды в таблице | новые на этом уровне |
|---|---|---|
| barracks_1 | dwarf_warrior_0, dwarf_warrior_1, miners_1 | все три |
| barracks_2 | dwarf_warrior_0, dwarf_warrior_1, miners_1, quarrellers_0, quarrellers_1 | quarrellers_0, quarrellers_1 |
| barracks_3 | всё из barracks_2 + longbeards, longbeards_1 | longbeards, longbeards_1 |

Так же устроены мастерские (`wh_main_dwf_workshop_1..4`: на 3-м уровне 6 отрядов, из них новых 2), инженерные (`engineer_1..3`), и цепочки самой барки в игре (`wh3_dlc25_dwarf_spirit_of_grungni_airship_hull_1..5`, `..._artillery_workshop_1..3`, `..._barracks_1..3`), и цепочки хаос-гномов (`wh3_dlc23_chd_military_*`).

Таблица `building_effects_junction`: строка = уровень + эффект + значение + область.
**У каждого уровня свой полный набор эффектов с полными значениями**, а не разница с прошлым уровнем:

| уровень | эффекты |
|---|---|
| engineer_1 | enable_recruitment_engineer 1; technology_research_points 2 |
| engineer_2 | enable_recruitment_engineer 1; agent_cap_increase_engineer 1; technology_research_points 3 |
| engineer_3 | enable_recruitment_engineer 1; agent_cap_increase_engineer 2; agent_recruitment_xp_engineer 1; technology_research_points 4 |

В слоте стоит один уровень цепочки (выше заменяет ниже), поэтому действует только набор стоящего уровня — отсюда полные списки.

## 2. Карточки на слоте дерева

`ui/templates/building_frame.twui.xml`, `units_list > unit_list` (GUID `72C5B48F-…`):

```
callback_id="ContextList" context_object_id="CcoBuildingLevelRecord"
context_function_id="UnitList(Buildings.StoredSettlementOrCharacter, PlayersFaction)"
```

Список строит движок (функция `UnitList` объекта уровня), фильтр в файле макета не виден. Доказано только: карточки берутся из записи **этого уровня**.

Вывод (лучшее, что подтверждается): слот показывает **только отряды, впервые доступные на этом уровне**. Основания:
- в таблицах на 3-м уровне мастерской 6 отрядов, а на снимке дерева барки в игре (`docs/feedback/18-tree-cards.jpg`) ни на одном слоте нет больше 2 карточек — полный список на слот не выводится;
- наблюдение автора в игре: «постройки не дублируют войска».

Не доказано файлами: делает ли это `UnitList` сравнением с уровнем ниже или другим правилом. Если в игре увидим иное — правило одно, в `tree_model.mjs newOnLevel`.

## 3. Окно постройки (наведение на слот)

`ui/campaign ui/building_information.twui.xml` — рамка, заголовок, описание, список эффектов; строки эффектов (`building_info_generic_entry.twui.xml`) заполняет движок, контекстных функций для отбора в макете нет.
`ui/campaign ui/building_info_recruitment_effects.twui.xml` — блок «Unlocks recruitment of:» (`Открывает найм:`), строка отряда `unit_entry` заполняется обратным вызовом `BuildingInfoUnitEntry` (движок), без отметки «новый».

Вывод (лучшее, что подтверждается): окно показывает **запись уровня целиком** — все его эффекты с их значениями и все отряды, которые уровень разрешает. Данные полные (раздел 1), а в макете нет ни фильтра, ни пометки «новое». Не доказано файлами, что движок не отсеивает отряды прошлых уровней в этом окне.

## 4. Как это сделано на странице

- Карточки на слоте (игровая колонка и конструктор): `tree_model.mjs newOnLevel(design, id)` — то, что уровень даёт сверх уровня ниже в своей линейке. Поля строки уровня: `unlocks_new`, `units_new` (`gameData`). Если новых больше трёх, лишние сворачиваются в табличку «+N» (`slotCards`).
- Окно постройки: полный набор уровня (`resolve(...).full`) — все эффекты и все отряды, как запись уровня в игре.
- Проверка: `tools/tests/panel_rules_test.mjs` — ни одна карточка не стоит на двух уровнях одной линейки дерева автора.
