# Навыки Малакая: что нужно переделать под барку

Состояние игры на 02.11.2026. Набор узлов `wh3_dlc25_skill_node_set_dwf_malakai_makaisson`, 56 навыков. Источник: таблицы `db.pack` (включая перечитанную `character_skills`), `local_ru.pack`, `local_en.pack`, собранный `tww3_mtb_campaign.pack`. Игру для этого списка не запускал. «Проверено» значит, что это уже видели бои в `docs/campaign.md`, `docs/v1.md` или журналах `build/`. «Вывод» значит, что по данным так получается, но в бою это не измерено.

| Группа | Навыков |
|---|---:|
| 1. Личные характеристики | 12 |
| 2. Способности | 10 |
| 3. Армия и кампания | 34 |

## Что важно для переделки

**Наш отряд.** `mtb_dwf_cha_malakai_thunderbarge` это копия барки с классом `com` и кастой `lord`. Эффекты `character_to_character_own` с набором `all_units` на него попадают: набор включает класс `com`. Сравнение с пешим Малакаем:

| Что | Пеший Малакай | Наш отряд |
|---|---|---|
| Атака и защита | 55 и 45 | 20 и 4 |
| Здоровье (в бою) | 4620 | 12 580 |
| Ближний бой | Топор: 280 + 120 пробивающего | Барка: 150 + 350 пробивающего |
| Выстрелы | Винтовка: 50 + 100, 3 выстрела в залпе, 7 с, дальность 180, запас 90 | Места экипажа, см. ниже, запас 40 и 50 |
| Скорость | Бег 4,2, полёта нет | Полёт и бег 3 (на панели 30, `docs/campaign.md`) |
| Анимация | `hu3_dlc25_malakai_axe_and_rifle` | Капитан `hu3_dlc25_zeppelin01_crew_captain`, корпус `zeppelin01_dlc25_thunderbarge_grungni` |

Места, из которых стреляет отряд: 12 стрелков (8 + 24, 3 снаряда, 2 выстрела в залпе, 4 с, дальность 100), 2 пушки (64 + 286, 11 с, дальность 100), 2 метателя бомб-головешек (взрыв 60 + 15, радиус 4, 4 с, дальность 100), 4 бомбовых люка (взрыв 75 + 35, радиус 6, 10 с). **Сам Малакай не стреляет:** место капитана без оружия. Личной винтовки в отряде нет, навыки, рассчитанные на неё, усиливают оружие экипажа, если вообще на него действуют.

**Главные выводы:**

1. **К набору `dwf_malakai_only` не привязан ни один навык.** Этот набор использует только награда `wh3_dlc25_dwf_upgrade_missile_damage_malakai` (+50 пробивающего и магические выстрелы, задание `exalted_bloodthirster_4`). Наш отряд в наборе состоит, награда на него ляжет.
2. **Армейские бонусы для барок на наш отряд не действуют.** Наборы `dwf_thunderbarge`, `dwf_flying_war_machines`, `dwf_artillery`, `dwf_gyros` содержат обычные громобаржи, но не барку Духа Грунгни и не наш отряд. Навыки «Мелкий ремонт», «Традиции новаторства» и +20 % от врождённого навыка её не усиливают. То же было и в оригинале.
3. **Способности через эффект работают.** В бою у отряда появились пассивка навыка и способность предмета. Значит, включение способностей навыками действует, хотя часть из них не записана за отрядом в `land_units_to_unit_abilites_junctions`.
4. **Навыки ближнего боя теряют смысл:** защита, сила оружия, смертельный удар и «Смертельная резня». Постоянный полёт и защита 4 делают их слабыми (вывод).
5. **Бомба на барке, скорее всего, сыграет анимацию гарпуна (вывод).** В таблице корпуса `zeppelin01_dlc25_thunderbarge_grungni` есть фрагмент `zeppelin01_dlc25_thunderbarge`, а в нём слоты `CAST_SPELL_FORWARD_SHORT` и `CAST_SPELL_FORWARD_SHORT_FLYING` с анимацией `zeppelin01_harpoon_fire_01.anim`. Стойка `cast_forward_short` та же, что у стокового `spear_of_grungni`. Что стойка попадает именно в эти слоты, я вывожу из названий. У капитана в собственном фрагменте слотов каста нет, базовый `hu3_dwarf_base` в дампе не разобран, поэтому что делает Малакай у штурвала, неизвестно. Откуда вылетит снаряд, тоже. `thunderburner` со стойкой `cast_up_long` у отряда в бою работал, хотя такого слота в этих фрагментах нет: падения от самой записи стойки не жду.

## Группа 1. Личные характеристики

| Навык | Ключ | Положение | Уровни и числа | Область | Как поведёт себя на барке |
|---|---|---|---|---|---|
| Луженая глотка (Brass-Lunged) | `wh_main_skill_all_lord_battle_brass-lunged`<br>узел `character_04` | Персонаж, колонка 0, ярус 3<br>без родителя<br>ур. 1: ранг 3<br>уровней: 1 | Аура дисциплины: +25% | сам Малакай | Цель: `character_to_character_own`; набор `all_units`.<br>**Вывод:** работает, размер ауры не зависит от тела. У отряда есть атрибут `encourages`. Измерений нет. |
| Руна Гримнира (Rune of Grimnir) | `wh_main_skill_dwf_all_unique_rune_of_grimnir`<br>узел `character_05` | Персонаж, колонка 0, ярус 7<br>без родителя<br>ур. 1: ранг 7<br>уровней: 1 | Сопротивление выстрелам: 10% | сам Малакай | Цель: `character_to_character_own`; набор `all_units`.<br>**Вывод:** работает. У барки своё `damage_mod_missile` = 15, такое же, как у Малакая. Как значения складываются в бою, не измерял. |
| Искусство выживания (Survivalist) | `wh2_dlc11_skill_all_lord_self_survivalist`<br>узел `combat_01` | Персонаж, колонка 2, боевые, ярус 0<br>без родителя<br>ранг не ограничен<br>уровней: 2 | Ур. 1: Здоровье: +7%<br>Ур. 2: Здоровье: +15% | сам Малакай | Цель: `character_to_character_own`; `general_bodyguard_size_mod`.<br>**Не проверено.** Бонус называется `general_bodyguard_size_mod`, он не привязан к набору. У пешего Малакая 4620 здоровья, у отряда 12 580. Если бонус считается от всего отряда, при +15 % это +1887 (мой расчёт). В прогоне `c1` на ранге 11 здоровье 12 580, но этого навыка там нет (список `skills` в журнале), так что замера с ним нет. |
| Всегда готов (Always Ready) | `wh3_dlc23_skill_chd_lord_self_always_ready`<br>узел `combat_02` | Персонаж, колонка 2, боевые, ярус 1<br>нужен `combat_01`<br>ранг не ограничен<br>уровней: 2 | Ур. 1: Ускорение перезарядки: +7%<br>Ур. 2: Ускорение перезарядки: +15% | сам Малакай | Цель: `character_to_character_own`; набор `all_units`.<br>**Вывод:** ускоряет оружие мест экипажа: 2 пушки (11 с), 12 стрелков (4 с), 2 метателя бомб-головешек (4 с), 4 бомбовых люка (10 с). Личной винтовки у отряда нет. |
| Патронташ (Bandolier) | `wh3_dlc23_skill_chd_lord_self_bandolier`<br>узел `combat_03` | Персонаж, колонка 2, боевые, ярус 2<br>нужен `combat_01`<br>ранг не ограничен<br>уровней: 2 | Ур. 1: Боеприпасы: +15%<br>Ур. 2: Боеприпасы: +30% | сам Малакай | Цель: `character_to_character_own`; набор `all_units`.<br>**Вывод:** действует на запас отряда: `primary_ammo` 40, `secondary_ammo` 50 вместо 90 у Малакая. На какой из двух запасов, не проверял. |
| Мастерство защиты (Hard to Hit) | `wh2_dlc11_skill_all_lord_self_hard_to_hit`<br>узел `combat_04` | Персонаж, колонка 2, боевые, ярус 3<br>нужен `combat_01`<br>ранг не ограничен<br>уровней: 2 | Ур. 1: Защита в бл. бою: +6<br>Ур. 2: Защита в бл. бою: +12 | сам Малакай | Цель: `character_to_character_own`; набор `all_units`.<br>**Вывод:** почти без смысла. Защита отряда 4 вместо 45, отряд `always_flying`. Как часто по нему вообще бьют в ближнем бою, по данным не определить. |
| Древние обиды (Ancestral Grudge) | `wh_main_skill_dwf_lord_self_ancestral_grudge`<br>узел `combat_05` | Персонаж, колонка 2, боевые, ярус 4<br>нужен `combat_01`<br>ранг не ограничен<br>уровней: 2 | Ур. 1: Сила оружия: +5%<br>Ур. 1: Сила оружия: +7% в битвах против зеленокожих<br>Ур. 2: Сила оружия: +8%<br>Ур. 2: Сила оружия: +15% в битвах против зеленокожих | сам Малакай | Цель: `character_to_character_own`; набор `all_units`, условие боя `fighting_culture_greenskins`.<br>**Вывод:** почти без смысла. Усиливает оружие барки (150 + 350 пробивающего), а не топор Малакая (280 + 120). Пригодится только если барка вступает в ближний бой. |
| Клинковая защита (Blade Shield) | `wh2_dlc11_skill_all_lord_self_blade_shield`<br>узел `combat_07` | Персонаж, колонка 2, боевые, ярус 6<br>нужен `combat_06`<br>ранг не ограничен<br>уровней: 2 | Ур. 1: Защита в бл. бою: +6<br>Ур. 2: Защита в бл. бою: +12 | сам Малакай | Цель: `character_to_character_own`; набор `all_units`.<br>**Вывод:** почти без смысла, как «Мастерство защиты»: защита 4, `always_flying`. |
| Проникающие выстрелы (Piercing Shots) | `wh3_dlc23_skill_chd_lord_self_piercing_shots`<br>узел `combat_08` | Персонаж, колонка 2, боевые, ярус 7<br>нужен `combat_06`<br>ранг не ограничен<br>уровней: 2 | Ур. 1: Урон от взрывных выстрелов: +7%<br>Ур. 1: Урон от выстрелов: +7%<br>Ур. 2: Урон от взрывных выстрелов: +15%<br>Ур. 2: Урон от выстрелов: +15% | сам Малакай | Цель: `character_to_character_own`; набор `all_units`.<br>**Вывод:** полезен. Обычный урон действует на пушки и стрелков, урон от взрывов на бомбы и бомбы-головешки. На то, что на эти места распространяются эффекты персонажа, прямых измерений нет. |
| Прицел (Gunsight) | `wh3_dlc23_skill_chd_hero_self_gunsight`<br>узел `combat_09` | Персонаж, колонка 2, боевые, ярус 8<br>нужен `combat_06`<br>ранг не ограничен<br>уровней: 1 | Дальность: +10% | сам Малакай | Цель: `character_to_character_own`; набор `all_units`.<br>**Вывод:** у пушек и стрелков дальность 100, станет 110. У бомб `effective_range` = 1, им навык не нужен. Дальность личной винтовки (180) теряется. |
| Неумолимость (Relentless) | `wh_main_skill_dwf_lord_self_relentless`<br>узел `combat_10` | Персонаж, колонка 2, боевые, ярус 9<br>нужен `combat_06`<br>ранг не ограничен<br>уровней: 2 | Ур. 1: Скорость: +7%<br>Ур. 2: Скорость: +15% | сам Малакай | Цель: `character_to_character_own`; набор `all_units`.<br>**Может не работать.** Бонус называется `mod_land_movement_battle`, а отряд летает всегда: `always_flying`, `fly_speed` 3, `run_speed` 3. Действует ли бонус на полёт, данные не говорят. Проверить в бою по панели. |
| Вдохновляющее присутствие (Inspiring Presence) | `wh_main_skill_all_lord_battle_inspiring_presence`<br>узел `army_01` | Бой, колонка 4, армия, ярус 0<br>без родителя<br>ранг не ограничен<br>уровней: 1 | Опыт за ход: +75<br>Влияние на дисциплину: +5 | армия лорда; сам Малакай | Цель: `general_to_force_own`, `character_to_character_own`; `unit_xp_mod_training`, набор `all_units`.<br>**Вывод:** аура работает, опыт идёт через `general_to_force_own`. В прогоне `c1` навык у Малакая был (`skills` в журнале), но размер прибавки в бою не измерен. |

## Группа 2. Способности и заклинания

Заклинаний у Малакая нет: `magic_lore` пусто, хотя `is_caster` = true. У всех десяти способностей ниже `mana_cost` = 0.

### Навыки

| Навык | Ключ | Положение | Уровни и числа | Область | Как поведёт себя на барке |
|---|---|---|---|---|---|
| Смертельный удар (Deathblow) | `wh_dlc08_skill_ability_dummy_deathblow`<br>узел `deathblow_01` | Персонаж, колонка 0, ярус 0<br>без родителя<br>дан при создании персонажа<br>уровней: 1 | Постоянная способность: «Смертельный удар» | сам Малакай | Цель: `character_to_character_own`; enable `wh_main_lord_passive_deathblow`.<br>**Проверено:** пассивка есть у отряда на ранге 1 (`battle_read`). **Вывод:** усиливает оружие барки, а не топор. |
| Решительный смертельный удар (Determined Deathblow) | `wh3_dlc25_skill_dwf_garagrim_determined_deathblow`<br>узел `deathblow_02` | Персонаж, колонка 0, ярус 1<br>нужен `deathblow_01`<br>ур. 1: ранг 4<br>уровней: 1 | Заменяет «Смертельный удар»<br>Постоянная способность: «Решительный смертельный удар» | сам Малакай | Цель: `character_to_character_own`; disable `wh_main_lord_passive_deathblow`, enable `wh_dlc08_lord_passive_determined_deathblow`.<br>**Вывод:** замена Смертельного удара. Прибавка атаки и урона нужна только в ближнем бою, см. выше. |
| Отчаянный смертельный удар (Extremely Daring Deathblow) | `wh3_dlc25_skill_dwf_slayer_extremely_daring_deathblow`<br>узел `deathblow_03` | Персонаж, колонка 0, ярус 2<br>нужен `deathblow_02`<br>ур. 1: ранг 9<br>уровней: 1 | Заменяет «Решительный смертельный удар»<br>Постоянная способность: «Отчаянный смертельный удар» | сам Малакай | Цель: `character_to_character_own`; disable `wh_dlc08_lord_passive_determined_deathblow`, disable `wh_main_lord_passive_deathblow`, enable `wh_dlc08_lord_passive_daring_deathblow`.<br>**Проверено:** пассивка `wh_dlc08_lord_passive_daring_deathblow` есть у отряда в `c1`. **Вывод:** из неё полезно только сопротивление физическому урону +15, остальное касается ближнего боя. |
| Повелитель артиллерии (Artillery Master) | `wh3_dlc25_skill_dwf_malakai_makaisson_unique_4`<br>узел `unique_4` | Персонаж, колонка 1, уникальные, ярус 3<br>нужен `unique_1`<br>ранг не ограничен<br>уровней: 1 | Постоянная способность: «Повелитель артиллерии»<br>Боеприпасы: +20%<br>Ускорение перезарядки: +10% | сам Малакай | Цель: `character_to_character_own`; enable `wh3_dlc25_character_passive_artillery_master`, набор `all_units`.<br>Аура действует вокруг отряда (`effect_range` = 55), но не на него самого: `target_self` = false. **Вывод:** работает для своей артиллерии и боевых машин, радиус считается от летящей барки. Боеприпасы и перезарядка, как у «Патронташа» и «Всегда готов». Проверить, что пассивка видна в бою. |
| Опытный инженер (Master Engineer) | `wh3_dlc25_skill_dwf_malakai_makaisson_unique_6`<br>узел `unique_6` | Персонаж, колонка 1, уникальные, ярус 5<br>из `unique_2`, `unique_3`, `unique_4`, `unique_5` нужно `required_num_parents` = 2<br>ранг не ограничен<br>уровней: 1 | Заменяет: «Безумные снаряды»<br>Способность: «Улучшенные безумные снаряды»<br>Урон от бронебойных выстрелов: +20<br>Дальность: +15% | сам Малакай | Цель: `character_to_character_own`; disable `wh3_dlc25_lord_abilities_deranged_munitions`, enable `wh3_dlc25_lord_abilities_deranged_munitions_upgraded`, `missile_damage_ap_mod_add`, набор `all_units`.<br>**Вывод, требует проверки:** плоская прибавка `missile_damage_ap_mod_add` +20 на снаряд. У стрелков пробивание 24, у пушки 286, на бомбы (урон 0) неясно. На стрелках прибавка очень сильная, если она вообще применяется к местам экипажа. Замена способности даёт ауру радиусом 35 м на свои стреляющие отряды. Дальность оружия: 100 → 115 (мой расчёт). |
| Бомбы-головешки (Cinderblast Cluster Bombs) | `wh3_dlc25_skill_dwf_malakai_makaisson_ability_1`<br>узел `combat_06` | Персонаж, колонка 2, боевые, ярус 5<br>из `combat_02`, `combat_03`, `combat_04`, `combat_05` нужно `required_num_parents` = 4<br>ранг не ограничен<br>уровней: 1 | Способность: «Бомба-головешка» | сам Малакай | Цель: `character_to_character_own`; enable `wh3_dlc25_lord_abilities_cinderblast_cluster_bomb`.<br>**Не проверено:** в бою способность не применялась (`docs/v1.md`). Стойка `cast_forward_short` та же, что у стокового `spear_of_grungni`, слот у корпуса есть. Вместо броска рукой будет, скорее всего, анимация гарпуна на корпусе (вывод). Подробно в таблице способностей. |
| Смертельная резня (Deadly Onslaught) | `wh3_dlc25_skill_dwf_malakai_makaisson_ability_2`<br>узел `combat_11` | Персонаж, колонка 2, боевые, ярус 10<br>из `combat_07`, `combat_08`, `combat_09`, `combat_10` нужно `required_num_parents` = 4<br>ранг не ограничен<br>уровней: 1 | Способность: «Смертельная резня» | сам Малакай | Цель: `character_to_character_own`; enable `wh_dlc03_character_abilities_deadly_onslaught`.<br>**Вывод:** почти без смысла. Усиливает натиск и ближний бой, а у барки `charge_bonus` 15 и постоянный полёт. |
| Сплочение (Rally!) | `wh_main_skill_all_lord_battle_rally`<br>узел `army_08` | Бой, колонка 4, армия, ярус 7<br>из `army_02`, `army_03`, `army_04`, `army_05`, `army_06`, `army_07` нужно `required_num_parents` = 6<br>ранг не ограничен<br>уровней: 1 | Способность: «Сплочение» | сам Малакай | Цель: `character_to_character_own`; enable `wh_main_character_abilities_rally`.<br>**Вывод:** работает как аура вокруг барки, радиус 35 м. На сам отряд почти не влияет: у него `unbreakable` и `immune_to_psychology`. |
| Держать позицию! (Stand Your Ground!) | `wh_main_skill_all_lord_battle_stand_your_ground`<br>узел `army_13` | Бой, колонка 4, армия, ярус 12<br>из `army_09`, `army_10`, `army_11`, `army_12` нужно `required_num_parents` = 1<br>ранг не ограничен<br>уровней: 1 | Заменяет «Сплочение»<br>Способность: «Держать позицию!» | сам Малакай | Цель: `character_to_character_own`; disable `wh_main_character_abilities_rally`, enable `wh_main_character_abilities_stand_your_ground`.<br>**Вывод:** работает как аура вокруг барки. Защита +24 нужна пехоте рядом, отряду почти нет. |
| Дух Грунгни (Spirit of Grungni) | `wh2_dlc25_skill_innate_dwf_malakai`<br>узел `innate` | Скрытый, скрытый врождённый, ярус 15<br>без родителя<br>дан при создании персонажа<br>уровней: 1 | Способность: «Безумные снаряды»<br>Урон от выстрелов: +20% для артиллерии и летающих боевых машин<br>У армии Малакая есть доступ к постройкам воздушного корабля «Дух Грунгни» | сам Малакай; своя армия, подсказки области нет | Цель: `character_to_character_own`, `character_to_force_own_unseen`; enable `wh3_dlc25_lord_abilities_deranged_munitions`, набор `dwf_artillery`, набор `dwf_gyros`, набор `dwf_thunderbarge`.<br>**Проверено:** «Безумные снаряды» есть у отряда на ранге 1 и применялись (`docs/v1.md`), действие не измерено. **Ни наш отряд, ни стоковая «Дух Грунгни» не входят** в `dwf_artillery`, `dwf_gyros`, `dwf_thunderbarge`: +20 % получает армия, а не барка Малакая. Заглушка `wh3_dlc25_main_effect_malakai_sog_dummy` без строк бонусов. |

### Сами способности

Дальность и радиус в метрах, время в секундах. `-1` или прочерк значит, что ограничения нет. Значения из `unit_special_abilities` и `special_ability_phase_stat_effects`.

| Способность | Ключ | Откуда | Что делает | На кого | Радиус | Дальность применения | Перезарядка | Действует | Применений | Подготовка | `wind_up_stance` | Прочие ограничения |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| Безумные снаряды (Deranged Munitions), активная | `wh3_dlc25_lord_abilities_deranged_munitions` | `innate` | пробивающий урон выстрелов ×1,5, обычный урон выстрелов ×1,5, выстрелы магические | сам, свои | — | 100 | 90 | 30 | — | — | — | `cannot_perform_missile_attack` |
| Улучшено: Безумные снаряды (Deranged Munitions Upgraded), активная | `wh3_dlc25_lord_abilities_deranged_munitions_upgraded` | `unique_6`, заменяет предыдущую | пробивающий урон выстрелов ×1,5, обычный урон выстрелов ×1,5, выстрелы магические | сам, свои | 35 | — | 90 | 30 | — | — | — | `cannot_perform_missile_attack` |
| Бомба-головешка (Cinderblast Cluster Bomb), активная | `wh3_dlc25_lord_abilities_cinderblast_cluster_bomb` | `combat_06` | Бомба: 10 + 25, взрыв 50 + 125 пробивающего, радиус 3. Огненная, по `unit_abilities_to_additional_ui_effects_juncs` | выстрел | — | 75 | 120 | — | 3 | 3 | `cast_forward_short` | — |
| Повелитель артиллерии (Artillery Master), пассивная | `wh3_dlc25_character_passive_artillery_master` | `unique_4` | точность +30, перезарядка +10 | свои | 55 | — | — | — | — | — | — | `unit_is_not_artillery_or_war_machine` |
| Смертельный удар (Deathblow), пассивная | `wh_main_lord_passive_deathblow` | `deathblow_01`, дан при создании | пробивающий урон ближнего боя ×1,2, обычный урон ближнего боя ×1,2 | сам | — | — | — | — | — | — | — | — |
| Решительный смертельный удар (Determined Deathblow), пассивная | `wh_dlc08_lord_passive_determined_deathblow` | `deathblow_02` | атака +10, пробивающий урон ближнего боя ×1,3, обычный урон ближнего боя ×1,3 | сам | — | — | — | — | — | — | — | — |
| Отчаянный смертельный удар (Extremely Daring Deathblow), пассивная | `wh_dlc08_lord_passive_daring_deathblow` | `deathblow_03` | атака +10, пробивающий урон ближнего боя ×1,5, обычный урон ближнего боя ×1,5, сопротивление физическому урону +15 | сам | — | — | — | — | — | — | — | — |
| Смертельная резня (Deadly Onslaught), активная | `wh_dlc03_character_abilities_deadly_onslaught` | `combat_11` | натиск ×1,6, пробивающий урон ближнего боя ×1,25, обычный урон ближнего боя ×1,25 | сам | — | — | 90 | 31 | — | — | — | — |
| Сплочение (Rally!), активная | `wh_main_character_abilities_rally` | `army_08` | дисциплина +16 | сам, свои | 35 | — | 60 | 14 | — | — | — | — |
| Держать позицию! (Stand Your Ground!), активная | `wh_main_character_abilities_stand_your_ground` | `army_13`, заменяет `army_08` | защита +24, дисциплина +16 | сам, свои | 35 | — | 90 | 18 | — | — | — | — |

Что ещё известно о базовых способностях:

- У пешего Малакая за отрядом записаны 5 способностей: `artillery_master`, `cinderblast_cluster_bomb`, `deranged_munitions`, `wh_main_lord_passive_deathblow`, `wh3_main_unit_passive_single_entity`. Наш отряд получил их все плюс `spear_of_grungni` и `thunderburner` барки (7 строк в паке). У первых четырёх `requires_effect_enabling` = true: без навыка не активны, это видно по бою на ранге 1, где нет бомбы.
- Для `deranged_munitions` и его улучшенной версии есть запрет `cannot_perform_missile_attack`. Способность в бою применялась, и отряд стреляет, но влияет ли множитель на места экипажа, не измерено.
- Способность `wh3_dlc25_character_passive_artillery_master` действует только на свои отряды артиллерии и боевых машин: запрет `unit_is_not_artillery_or_war_machine`.
- Анимационных полей `activation_effect`, `composite_scene_group_on_wind_up`, `wind_down_stance` у перечисленных способностей нет (`use_loop_stance` = false).

Не из дерева, но связано:

- **Предмет «Убеждатель Макайссона» (Makaisson’s Persuader)** (`wh3_dlc25_anc_weapon_makaissons_persuader`): способность `wh3_dlc25_weapon_abilities_makaissons_persuader`, атака +5, сила оружия +20 %, восполнение артиллерии и машин +8 %. В `c1` способность у отряда есть. Сами эффекты бонусов на барку не измерены.
- **Способности барки** `spear_of_grungni` и `thunderburner` навыками не меняются. Улучшение `thunderburner` даёт постройка, см. `docs/research/spirit-of-grungni-buildings.md`.

## Группа 3. Армия и кампания

Отряд в этих навыках напрямую не усиливается. Эффекты `general_to_force_own` без набора отрядов действуют на всю армию, значит и на него. Наборы отрядов проверены скриптом: кроме общего `all_units`, наш отряд входит только в набор `lords` навыка «Железная воля».

| Навык | Ключ | Коротко |
|---|---|---|
| Клятва кузницы (Oath of Forging) | `wh2_dlc10_skill_dwf_generic_oath_of_forging` | Доход клятвенного золота от построек +10 % |
| Повелитель глубин (Lord of the Deeps) | `wh_main_skill_dwf_lord_battle_lord_of_the_deeps` | Дисциплина армии +6: под землёй, при штурме под землёй, против скавенов |
| Упорство (Obstinacy) | `wh_main_skill_dwf_lord_battle_obstinacy` | Расход сил армии -15 % |
| Знаменитая армия (Army of Renown) | `wh3_main_skill_all_army_of_renown_legendary_lord` | Лимит знаменитых полков армии: +2 / +4 / +6 |
| Наставник (Mentor) | `wh3_main_skill_all_mentor_lord` | Опыт героев армии и обмен опытом с лордами |
| Изобретатель (Inventor) | `wh3_dlc25_skill_dwf_malakai_makaisson_unique_1` | Инженеры: найм, численность +2; исследования +10 |
| Мститель (Slayer) | `wh3_dlc25_skill_dwf_malakai_makaisson_unique_2` | Мстители всей фракции: сила оружия и выстрелов +10 %, содержание -10 % |
| Мелкий ремонт (Tinkerer) | `wh3_dlc25_skill_dwf_malakai_makaisson_unique_3` | Артиллерия и летающие машины: восполнение +10 %, перезарядка +10 % |
| Архитектор (Architect) | `wh3_dlc25_skill_dwf_malakai_makaisson_unique_5` | Постройки военной поддержки: стоимость -20 %, срок -1; постройки орды: стоимость -20 % |
| Гобелен клятв (Tapestry of Oaths) | `wh3_dlc25_dwf_daemon_slayer_units_1` | Мстители армии: сила оружия +10 %; пираты и рассекатели: выстрелы +10 % |
| Ритуальные шрамы (Ritualistic Scarring) | `wh3_dlc25_dwf_daemon_slayer_units_2_1` | Мстители армии: сопротивление выстрелам +15 % |
| Мстители, ко мне! (Slayers... to Me!) | `wh3_dlc25_dwf_daemon_slayer_units_2_2` | Мстители армии: восполнение +10 %, содержание -10 % |
| Командир топорников (Axe Lord) | `wh2_dlc11_skill_dwf_army_buff_axe_lord` | Горняки, воины, долгобороды: атака и защита |
| Громобой (Thunderer) | `wh2_dlc11_skill_dwf_army_buff_tactician` | Стрелки (`quarrellers`, `thunderers`, `rangers`): боеприпасы и выстрелы |
| Традиции новаторства (Tradition & Innovation) | `wh2_dlc11_skill_dwf_army_buff_tradition_and_innovation` | Автожиры, бомбовозы, громобаржа: боеприпасы и дальность |
| Огонь и ярость (Fire & Fury) | `wh2_dlc11_skill_dwf_army_buff_fire_and_fury` | Железные ящеры, огненные пушки: выстрелы и перезарядка |
| Наследники Гримнира (Grimnir's Heirs) | `wh2_dlc11_skill_dwf_army_buff_grimnirs_heirs` | Мстители, `hammerers`, `ironbreakers`: атака и сила оружия |
| Тактик (Tactician) | `wh2_dlc11_skill_dwf_army_buff_thunderer` | Местеметы, пушки, органные орудия: выстрелы и боеприпасы |
| Благословение Грунгни (Blessed by Grungni) | `wh2_dlc11_skill_dwf_army_buff_blessed_by_grungni` | Ветераны: горняки, воины, долгобороды от ранга 7: броня, магическое сопротивление, защита |
| Огневая мощь дави (Dawi Firepower) | `wh2_dlc11_skill_dwf_army_buff_dawi_firepower` | Ветераны: стрелки и автожиры от ранга 7: выстрелы, сопротивление выстрелам, перезарядка |
| Уважение Гримнира (Honoured by Grimnir) | `wh2_dlc11_skill_dwf_army_buff_honoured_by_grimnir` | Ветераны: мстители, `hammerers`, `ironbreakers` от ранга 7: атака, физическое сопротивление, сила оружия |
| Милость Моргрима (Morgrim’s Favoured) | `wh2_dlc11_skill_dwf_army_buff_morgrims_favoured` | Ветераны: артиллерия от ранга 7: выстрелы, боеприпасы, перезарядка |
| Опыт походов (Route Marcher) | `wh_main_skill_all_lord_campaign_route_marcher` | Дальность хода персонажа +5 % |
| Инстинкт горняка (Miner's Instinct) | `wh_main_skill_dwf_lord_campaign_miners_instinct` | Шанс перехвата на подземных путях |
| Разрушение стен (Wall Breaker) | `wh_main_skill_dwf_lord_campaign_wall_breaker` | Осада: потери врага |
| Чистобород (Pure-Beard) | `wh_main_skill_dwf_lord_campaign_pure-beard` | Снижение порчи в провинции |
| Каменщик (Mason) | `wh_main_skill_dwf_lord_campaign_mason` | Стоимость строительства в регионе |
| Железная воля (Iron-Willed) | `wh_main_skill_dwf_lord_campaign_iron-willed` | Лечение: срок ран -1 ход; восполнение лордов в армии +30 % (единственный из этой группы, у которого набор включает наш отряд: `lords`) |
| Стремительный удар (Lightning Strike) | `wh_main_skill_all_lord_campaign_lightning_strike` | Подкрепления, стремительный удар |
| Воодушевление (Reassuring Presence) | `wh_main_skill_lord_all_campaign_reassuring_presence` | Небоевые потери армии |
| Вдохновляющее руководство (Inspirational Leader) | `wh_main_skill_dwf_lord_campaign_inspirational_leader` | Восполнение потерь армии |
| Бдительность (Alert) | `wh_main_skill_all_lord_campaign_alert` | Защита от засад, перехват |
| Пытливый ум (Enquiring Mind) | `wh_main_skill_dwf_lord_campaign_enquiring_mind` | Исследования, содержание, ранг новых, защита от героев |
| Agent action success modifer (Agent action success modifer) | `wh3_main_skill_agent_action_success_scaling` | Служебный скрытый навык: шанс действий героев, растёт по уровням |

## Что не удалось установить

- **Действуют ли эффекты персонажа на оружие мест экипажа:** перезарядка, дальность, боеприпасы, урон. Данные этого не показывают, нужен замер в бою.
- **`mod_land_movement_battle` у летающего отряда.**
- **`general_bodyguard_size_mod` у барки:** от чего считается прибавка.
- **Слоты каста в `hu3_dwarf_base`** и вид броска бомбы: откуда летит снаряд и как двигается Малакай.
- **Какой ранг действует, если значения разные:** `character_skill_level_details` и `character_skills.unlocked_at_rank`. Например, у `deathblow_02` это 4 и 8. В таблицах указан первый вариант, если строка есть.
- **Смысл `required_num_parents`:** считает родителей или очки в них. Значения приведены как есть. Значимо для узлов с родителями на два уровня, например для «Бомб-головешек».
- **Названия колонок дерева** на экране: подписаны по ключам узлов, категории `character`, `battle`, `campaign` взяты из `character_skill_categories`.
