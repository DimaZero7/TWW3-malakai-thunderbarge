# Малакай в кампании: барка как постройка, на карте пеший, в бою у штурвала

Состояние на 03.11.2026. Всё проверено в настоящей игре, если не сказано иное.

**Мод несовместим со старыми сейвами, нужна новая кампания.** Это решение пользователя. Код подключения к идущей кампании не удалён и в прошлых тестах работал (раздел «Доказательства»), но на него больше не рассчитываем и не проверяем.

**Легендарные битвы работают по стоку.** Это тоже решение пользователя: таблицы `battle_set_piece_*` и скрипты битв не меняем, запуском битв не занимаемся.

## Как это устроено

Игрок начинает новую кампанию пешком, со стоковым отрядом и стоковыми навыками, а барку строит: постройка `airship_hull_2` выдаёт скрытое «ездовое животное», как у Икита. Прогрессия и привязка построек к экипажу: [design/progression-proposal.md](design/progression-proposal.md).

| Что | Запись | Зачем |
|---|---|---|
| Предмет | `ancillaries`: `mtb_anc_mount_dwf_malakai_thunderbarge`, категория `mount`, `provided_bodyguard_unit` = наш отряд | Игра сама меняет отряд лорда |
| Только для него | `ancillaries_included_agent_subtypes` | Другим персонажам не выдаётся |
| Модель | `agent_uniforms`: `mtb_uniform_dwf_malakai_thunderbarge`. `filename` как у Малакая, `battle_filename` = наша модель у штурвала; `campaign_character_uniform_ancillary_junctions` | На карте прежняя модель, в бою наша |
| Отряд | Все записи версии 1. `main_units.mount` пустой | Модели на карте нет |
| Выдача | `src/tww3_mtb_campaign.lua`: игрок при `MilitaryForceBuildingCompleteEvent` постройки `airship_hull_2`, ИИ на первом тике новой кампании; `cm:force_add_ancillary` один раз, флаг `mtb_barge_given` в сейве | Дальше предмет снимает и надевает только ванильный блок «Транспорт»: скрипт его не возвращает |
| Пустой стапель | `src/tww3_mtb_campaign.lua`: только игрок, новая кампания, первый тик, двойной `cm:convert_force_to_type` | `barracks_1` исчезает, `airship_hull_1` возвращается сам |
| Боковые постройки | `building_levels`: `barracks_1`, `crew_weapons_1`, `beer_hall_1` требуют уровень корпуса 1 (`airship_hull_2`) | До барки строить нечего |

`campaign_mount_animation_set_overrides` не понадобилась: без записи на карте остаётся анимация Малакая.

### Вызов второй барки

Шесть строк `building_effects_junction` с эффектом `wh3_dlc25_effect_army_ability_enable_spirit_of_grungni_summon_1` (`airship_hull_1..5`, `engines_3`) перекрыты значением 0. Ключи те же, фрагмент `!tww3_mtb` читается раньше `data__`.

Контроль в бою с постройками `airship_hull_1` и `engines_1`:

- без мода на панели есть `button_ability_wh3_dlc25_army_abilities_spirit_of_grungni`;
- с модом этой кнопки нет.

Что важно знать:

- Легендарные битвы включают вызов своим набором эффектов (`battle_set_piece_armies_effect_bundles`), его я не менял.
- Эффект `engines_3` действовал и на другие армии в зоне влияния. Теперь они тоже без вызова.
- Цепочка `army_ability_1` (`spirit_summon_1..3`) в игре не строится: это заготовка без эффектов, скрытая из интерфейса (`docs/research/spirit-of-grungni-buildings.md`). Вызов включают только `airship_hull_1..5` и `engines_3`.
- Описание эффекта на постройках дополнено: «только в легендарных битвах». В игре его вид не проверял.

### Задания

Два задания требуют применить вызов. Без правки первое застряло бы уже на первом ходу.

| Задание | Что сделано |
|---|---|
| `wh3_dlc25_camp_narrative_dwarfs_spirit_of_grungni_army_ability` («Призыв Духа», выдаётся на первом ходу) | Считает `thunderburner`, текст цели заменён. **Проверено:** галочка после боя с этой способностью, `f2_missions_after.png` |
| `wh3_dlc25_mis_dwf_malakai_warpstone_bomb_6` (5 применений) | То же, текст заменён. Лог `missions=true/true`. До конца в игре **не проходил**. Счётчик тот же: `get_how_many_times_ability_has_been_used_in_battle`, он вернул 1 |

Таблицы правятся на первом тике (`dwf_narrative_missions`, `malakai_battles`), тексты меняет `.loc`, файл `data/campaign_text.json`. Тексты только на русском.

### Улучшения барки

Свой набор `mtb_dwf_malakai_thunderbarge`, в набор вызова отряд не входит. Повторены строки `unit_set_unit_ability_junctions`, `effect_bonus_value_unit_set_unit_ability_junctions`, `effect_bonus_value_ids_unit_sets`, `effect_bonus_value_missile_weapon_junctions`.

В бою с `engines_1` и наградой `dragon_hunters_final_reward` отряд получил `thunderburner_upgraded` и `awe_inspiring_sight`, таймера нет. Огненные выстрелы и бомбы в бою **не проверял**: строки есть, эффект не измерен.

### Thunderburner

Это не наша ошибка. Способность ванильная: `affect_self`, `damage_amount` 30 каждые 0,2 с, работает, пока её не выключат. Контроль без мода: стоковая барка с `thunderburner_upgraded` теряет здоровье так же (100 → 96,4 → 92,7 % за 40 с). Наш отряд с обычной версией терял 0,58 %/с. Ничего не менял.

### Характеристики

Отряд в бою имеет характеристики барки: на панели персонажа доспехи 80, скорость 30, ближний бой 25. Навыки и предметы Малакая к ним прибавляются. Баланс вне этой задачи.

## Экипаж барки

Один отряд, выбор варианта на группу отсеков: стрелки, пушки, купола, люки, палуба. Устройство и доказательства: [design/modular-crew.md](design/modular-crew.md).

- **Нужен memreader Plus.** Без него или после патча, сломавшего поиск таблиц, барка со стоковым экипажем и один раз сообщение игроку. Кампания работает.
- **Выбор хранится в сейве** (`mtb_crew_<группа>`), на первом тике пишется в память.
- **Экипаж игрока задают постройки:** `buildings` в `data/crew_options.json`, одна строка на привязку. Действует последняя построенная в группе. Команда для теста осталась: `tww3_mtb_crew.set("cannons", "organ")`.
- **Начальные значения:** `start` в `data/crew_options.json` для Малакая-игрока (всё пусто, пиратов даёт `airship_hull_2`), `start_ai` для ИИ (стоковый экипаж). Выбор профиля один раз на кампанию: `mtb_crew_profile`.

```text
py -3.14 tools/build.py
py -3.14 tools/crew_cycle.py all       полный цикл, около 80 минут, нужна свободная игра
py -3.14 tools/crew_cycle.py report    таблица из build/crew/cycle/results.jsonl
py -3.14 tools/crew_cycle.py session prog_main   прогрессия в новой кампании; затем prog_load, prog_no_memreader, prog_ai
```

Одна сессия: `py -3.14 tools/crew_cycle.py session b_load`. Сессии описаны в `data/crew_cycle.json`; сессии после `a_new` загружают сейв, созданный предыдущей.

## Как собрать

```text
py -3.14 tools/build.py
```

- `build/campaign/pack/tww3_mtb_campaign.pack` — сам мод (версия 1 плюс кампания, без тестового боя и пробы).
- `build/campaign/pack/tww3_mtb_harness.pack` — только для тестов.
- `build/v1/pack/` — версия 1, её SHA-256 не изменился.
- `py -3.14 tools/rpfm_check.py --campaign --update-schemas` — проверка в RPFM: 29 файлов и все таблицы прочитаны.

## Как тестировать

**Нужен работающий Steam:** без него игра висит без событий или сразу выходит. RTX снова в машине, `--igpu` не нужен.

Пульт (`src/tww3_mtb_remote.lua`, только в тестовом паке) выполняет Lua, присланный во время игры, в меню, кампании и бою.

```text
tools\session.ps1 -Label x -Packs harness,campaign -Save tww3_mtb_malakai_t1.save -GameArgs "game_startup_mode campaign_load tww3_mtb_malakai_t1.save"
py -3.14 tools/rc.py --file tools/tests/snapshot.lua      выполнить Lua
py -3.14 tools/rc_lua.py tools/tests/click_named.lua mtb_name=button_attack
py -3.14 tools/rc.py --shot имя                           снимок окна игры
py -3.14 tools/turns.py 2                                 конец хода с закрытием окон
py -3.14 tools/report_campaign.py                         сравнение снимков состояния
py -3.14 tools/rc.py --stop                               закончить сессию
```

Сценарии лежат в `tools/tests/`.

- **Запуск из сейва:** `game_startup_mode campaign_load имя` доходит до карты примерно за 55 с, без меню и видео.
- **Новая кампания:** `frontend.start_campaign("wh3_main_combi", "wh3_main_combi", фракция)`, порядок аргументов верный.
- **Бой:** `cm:force_attack_of_opportunity`, затем `button_attack` или `button_autoresolve`.
- **Снимки:** только `PrintWindow`, копирования экрана в коде нет. Окно запускается без активации, клавиши и мышь не используются.
- **Нельзя:** `button_start_campaign` в меню — это «Продолжить». Она грузит самый новый сейв, то есть сейв пользователя.

## Что защищает данные пользователя

`tools/run_game.py` перед запуском копирует `save_games`, `advice_history`, `army_setups`, `battle_preferences`, `event_feed`, `resume`, `replays`, `scripts`, после закрытия игры сравнивает их по SHA-256 и возвращает изменённое. Новые файлы из `save_games` уходят в `build/campaign/saves/`.

Игра закрывается всегда: после ошибки, падения и тайм-аута. Замок снимается только когда её нет в `tasklist`.

Автосохранения: на время сессии `incremental_autosave_enabled false`. С этой настройкой игра всё равно пишет один файл `Новаторы_Автосохранение650314588.save`, он не совпадает с файлами пользователя. `cm:save()` пишет в него же; своё имя файлу дает переименование после сессии.

## Доказательства

Папка `build/campaign/runs/`.

| Что | Где |
|---|---|
| Новая кампания, на карте пеший | `20261102-190401-final_new/f_map_clear.png` |
| Новая кампания, отряд и лорд в API | `final_new/tww3_mtb_events.jsonl`, `battle_read`: `is_commanding_unit`, `IsGeneral`, `IsCharacter` = true, «Лорд» |
| У штурвала, карточка, портрет | `20261102-180707-c1/b_wheel_front.png` (полное качество), `final_new/f_wheel_new_game.png` |
| Эффекты персонажа в бою | `c1/tww3_mtb_events.jsonl`: ранг 11, способность предмета `makaissons_persuader`, пассивка от навыка `daring_deathblow` |
| Сейв без мода плюс мод (больше не поддерживается) | `c1/tww3_mtb_events.jsonl`: `given to cqi 143`, отряд заменён; `c1/c1_load.png` |
| Сохранение и загрузка | `tools/report_campaign.py`: `before_save` и `after_load` совпали по 17 полям, предмет не выдан повторно |
| Два хода, бой, автобой | `c1`: ходы 1→3, `c1_after_battle.png`, `c1_autoresolve_result.png` |
| Ранение | `c2`: `wounded=true`, армия ушла новому лорду (окно «Смерть на службе», `c2_after_end.png`), на ходу 8 здоров, новая армия с нашим отрядом, предмет, навыки и ранг на месте |
| ИИ и конфедерация | `20261102-185220-c3`: игрок — гномы, Малакай у ИИ получил предмет; после `force_confederation` найден в чужой фракции; ход без ошибок |
| Отряд ИИ-Малакая в бою | Летит и атакует; стоит только в армии с пушкой, пока игрок не двигается, как и стоковая барка: [research/barge-behaviour-checks.md](research/barge-behaviour-checks.md) |
| Постройки и контроль | `20261102-183031-c2/c2_b_front.png`, контроль `ctrl_nomod` |
| Версия 1 | `build/v1/runs/*-regression`: 29 бойцов, 265 с, таймера нет |

## Падения

| Прогон | Причина |
|---|---|
| fe1, fe2 | `frontend.start_campaign` со старым порядком аргументов |
| fe3–fe7 | Клик «Продолжить»: сейв пользователя, сделанный с его модами, загружался без них |
| qb, qb_ctrl | `frontend.start_named_battle` падает и без мода, адрес тот же |

В fe8 сейв пользователя загрузился с его модами. Кроме `faster_loading_script_cache` они все были подключены. Файлы сейвов пользователя не изменились, это подтверждают дата и размер: 15:01:22 и 15:03:29. В ходе этого прогона моды пользователя обновили свои логи в папке игры (`!groove_log.txt`, `wh3_native_dlss.log`), а `scripts/mct_registry.lua` восстановлен из копии.

Реестр: `frontend.start_campaign` добавляет значение с именем кампании в `HKCU\Software\The Creative Assembly\Warhammer3\Preferences\Campaigns`. fe1 и fe2 создали там лишнее `wh3_dlc25_dwf_malakai` = 1. Значения до моих запусков я не записал: вывод сделан по коду игры и имени значения, которое кампанией не является. После тестов оно удалено. `wh_main_emp_empire` в этом разделе не моё, оставлено.

## Что не проверено

- **Точный опыт.** Счётчика в скрипте не нашёл, сравнивал ранг и очки навыков. Ранг растёт от боя (11→12 в `c1`).
- Вид постройки с нулевым эффектом в интерфейсе, огненные выстрелы и бомбы, задание `warpstone_bomb_6` до конца.
