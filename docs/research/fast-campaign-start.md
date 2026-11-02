# Быстрый вход в кампанию за Малакая и в бой кампании

Исследование для автоматических тестов мода, 02.11.2026. Сборка игры: Patch 9.0, `v9.0.4 Build 50791`, `Warhammer3.exe` от 15.10.2026.

Сам я игру не запускал. Метки в таблицах и разделах:

- **в игре**: видно в прогонах соседнего агента, `build/campaign/runs/*-feN` (только чтение);
- **в файлах**: прочитано в exe, скриптах или логах, в игре не пробовалось;
- **догадка**: вывод из косвенных данных.

Адреса указаны как виртуальные (база `0x140000000`). Декомпиляция сделана на копии проекта Ghidra в scratchpad.

## Итог

| № | Способ | Скорость | Надёжность | Статус |
|---|---|---|---|---|
| 1 | `game_startup_mode campaign_load tww3_mtb_malakai_t1.save` | Лучшая: нет меню, логотипов и вступления | Высокая, если тот же набор паков, что у сейва | в файлах |
| 2 | Из меню: `frontend.load_campaign("tww3_mtb_malakai_t1.save", false)` | Плюс загрузка меню, логотипы 33,4 с (без `-autotest`) | Запасной вариант 1 | функция есть (в игре), вызов не пробовался |
| 3 | Новая кампания: `frontend.start_campaign("wh3_main_combi", "wh3_main_combi", "wh3_dlc25_dwf_malakai")` | Плюс видео Малакая 61,5 с и облёт, если их не снять | Порядок аргументов выведен из кода; старый порядок падает | падение (в игре), новый порядок (в файлах) |
| 4 | Клики по меню | Самый медленный | Зависит от UI | кнопка «Продолжить» (в игре) |
| — | `game_startup_mode campaign wh3_main_combi` | Быстро | Не подходит: не тот лорд | в файлах |
| — | `game_startup_mode last_campaign`, `frontend.continue_campaign()`, кнопка `button_start_campaign` | Быстро | Опасно: берут самый новый сейв, то есть сейв пользователя | в игре, в файлах |

Рекомендация: один раз создать свой сейв способом 3 и затем всегда запускать способом 1. Способ 2 оставить на случай, если 1 не заработает.

## Что уже показали прогоны в игре

Это важнее всего остального, потому что объясняет падения.

**`button_start_campaign` в главном меню не начинает новую кампанию.** На `fe_menu.png` (прогон fe3) верхний пункт меню: «Продолжить кампанию». В дереве UI того же прогона первым идёт `button_start_campaign`, затем `button_campaign`, `button_battle`, `button_multiplayer`, `button_options`. Значит, это «Продолжить», а «Кампания» это `button_campaign`.

**Падение после этого клика вызвано отсутствием модов пользователя.**

- fe3–fe7: клик, только паки теста, падение `0xc0000005` по адресу `0x142435415` (чтение `+0x3a8` от нуля) в прогонах, где я разбирал дамп (fe3, fe4, fe5).
- Цепочка: `FUN_14266c618` (чтение фракции, рядом строки `FACTION_ARRAY`) → `FUN_142437c6c` → `FUN_1424378dc` → `FUN_14243534c`.
- `FUN_1424378dc` читает ключ из файла и ищет его через `FUN_1426be2b0`. Результат без проверки уходит вторым параметром в `FUN_14243534c`, где и происходит чтение от нуля.
- fe8: тот же клик, полный список модов (`build/campaign/mods_all.txt`). Кампания загрузилась: `faction=wh3_dlc25_dwf_malakai, turn=2, new=false`, картинка `c_load.png`.
- В дампах есть имя автосохранения `.23419554618.save`. В `save_games` лежит `Новаторы_Автосохранение.23419554618.save`.
- Вывод (догадка, но хорошо подкреплён): сейв с ключами из модов падает, если модов нет.

**Правило:** сейв запускается только с тем же набором паков, с которым создан, или с большим.

**`frontend.start_campaign` с порядком из документации падает.** fe2: `("wh3_main_combi","wh3_dlc25_dwf_malakai","wh3_dlc25_political_party_dwf_malakai")`, падение примерно через 2 с, чтение `+0xe0` от нуля по адресу `0x14140cdc7`. Причина разобрана ниже. В fe1 тот же вызов без кавычек передал `nil` и ничего не сделал.

**Содержимое таблицы `frontend` подтверждено** (fe1, id 1): `campaign_saves_exist, campaign_saves_exist_mp, continue_campaign, game_intro_video_enabled, load_campaign, override_defender_budget_ratio, register_scripted_startup_movie, start_campaign, start_named_battle`.

**Ошибка в тестовом пульте.** В fe8 команда с id 15 выполнилась дважды: в меню и снова в кампании. В `src/tww3_mtb_remote.lua` `last_id` хранится в локальной переменной и сбрасывается при смене среды, поэтому последняя команда запускается снова в новом режиме. Клик по кнопке или запуск кампании могут так сработать второй раз. Исправить: удалять `tww3_mtb_cmd.lua` после чтения или хранить последний id в файле.

## Как запускают сейчас

- Наш `tools/run_battle.py:191` и сосед `tools/launcher/launch.ps1:179` запускают `Warhammer3.exe game_startup_mode battle <xml>; <mods>.txt;`. Меню нет. Настройки правятся в `preferences.script.txt` с копией и возвратом.
- `tools/run_game.py` собирает `"exe" {args}; tww3_mtb_mods.txt;`, умеет `--save NAME` и после сессии переносит новые сейвы в `build/campaign/saves/`. Для способа 1 менять его не нужно.
- Замер соседа: около 83 с до `ready` в бою из XML, повторная загрузка боя в том же процессе около 11 с (`TWW3-batle-ai/docs/ru/research/launch/loading-times.md`). Отключение `fe_game_intro_video_enabled` на прямой запуск боя не влияет.

## Разбор исполняемого файла

### Режимы `game_startup_mode`

Строка помощи (`0x373d0f0` в файле) называет только `battle|campaign|campaign_edit|frontend|naval`. Код знает больше. Обработчик аргументов: `FUN_1405716a8`. Выбор режима: `FUN_14133a2c0`.

| Режим | Что делает | Применимость |
|---|---|---|
| `campaign_load <путь>` | Загрузка сейва без показа меню | **Способ 1** |
| `last_campaign` | Самый новый сейв (`FUN_1425ea584`) | Нельзя: сейв пользователя |
| `campaign_demo` | `testdata/campaign_reveal/demo.save` | Нет |
| `campaign [ключ]` | Новая кампания, по умолчанию ключ `main` (`FUN_141338838`) | Не тот лорд, см. ниже |
| `campaign_edit`, `campaign_benchmark` | Та же функция с флагами | Бенчмарк кампании рассчитан на `wh_main_dwf_dwarfs` (`wh_start.lua:33-60`) |
| `battle_autotest`, `battle_logger`, `battle_building_memory`, `battle_tile_test`, `battle_benchmark`, `benchmark`, `benchmark_loop`, `benchmark_auto_quit`, `replay`, `campaign_replay`, `last_battle` | Отладочные режимы CA | Не для нашей задачи |

**Почему `campaign_load` быстрее всего.** Ветка в `FUN_14133a2c0` (`0x14133a2c0`):

1. Создаёт объект меню: `FUN_14328cea0(..., 0, state+0x111)`. Четвёртый аргумент здесь равен нулю, а при обычном запуске это `state+0x62`, по умолчанию 1.
2. Этот аргумент попадает в поле `+0xbb0` меню, а `FUN_1432a9db4` с нуля в этом поле сразу выходит. Там и запускаются `movies/startup_movie_0N` и предупреждение об эпилепсии. То есть логотипов не будет.
3. Читает сейв `FUN_1423c981c`, проверяет фракцию (ошибка `Invalid faction record %s`), сразу создаёт состояние загрузки `FUN_14242ffd4`.

**Имя файла.** В `FUN_1423c981c`: без `/` и `\` файл ищется в папке сейвов пользователя, расширение `.save` добавляется, если его нет (`FUN_14058bdc8`, таблица по `0x1436de5b0`). С разделителем путь берётся как есть. Имя лучше ASCII и без пробелов: аргумент читается отдельным токеном до `;`.

**Почему не `campaign wh3_main_combi`.** Игрок берётся из `state+0x28` или списка `state+0x20`. Записей в них в exe я не нашёл, только обнуление в конструкторе `FUN_140572eac`. При пустом значении `FUN_141338838` берёт первую играбельную фракцию. Выбрать Малакая так нельзя. Вероятно, это поле заполнялось библиотекой автотестов, которой в игре нет.

### Функции `frontend.*`

Регистрация: `0x1402a35a0…0x1402a4690`, вызовы `0x14072596c`. Работают только в меню: обработчики берут объект меню из `0x144483240`.

**`frontend.start_campaign` (`FUN_141f6f64c`).** Требует ровно 3 аргумента, но читает 2, начиная с вершины стека (`FUN_1413570c8` читает индекс -1 и снимает значение):

- первое чтение, третий аргумент: уходит в `param_4`, это **фракция** (в `FUN_1432ab740` ищется в списке игроков);
- второе чтение, второй аргумент: уходит в `param_3`, это **кампания**, подставляется в `campaigns/%S/startpos.esf` (`0x1438aac28`, `FUN_142431944`);
- первый аргумент не читается.

Описание в exe («campaign name, the faction, the political party») устарело. Вызов в `frontend_start.lua:65` идёт за настройкой `SCRIPTED_TWEAKER_02`, строки которой в exe нет, так что это мёртвый код. Падение fe2 с этим совпадает: кампанией стал `wh3_dlc25_dwf_malakai`, а такой папки нет.

Верный вызов:

```lua
frontend.start_campaign("wh3_main_combi", "wh3_main_combi", "wh3_dlc25_dwf_malakai")
```

Папки кампаний в `data/campaigns`: `wh3_main_chaos`, `wh3_main_combi`, `wh3_main_prologue`. Если фракция не играбельна, код берёт первую играбельную: проверяйте результат через `cm:get_local_faction_name(true)`.

Побочный эффект: `FUN_1432aa918` создаёт значение с именем кампании в `HKCU\Software\The Creative Assembly\Warhammer…`, если его ещё нет. Пользователь уже играл в эту кампанию, так что значение, скорее всего, есть (догадка).

**`frontend.load_campaign(путь [, облако])` (`FUN_141f6f500`).** Второй аргумент необязателен и означает сохранение в облаке, передавайте `false`. Внутри `FUN_1432a2894`: имя без `\` ищется в папке сейвов, путь с `:` берётся как есть, остальное считается от текущей папки.

**`frontend.continue_campaign()` (`FUN_141f6f434`).** Самый новый сейв. **`frontend.campaign_saves_exist()`:** проверка наличия. **`frontend.start_named_battle(имя)`:** именованный бой.

В `lib_campaign_manager.lua` загрузки сейва нет. Из кампании вернуться можно только через меню: `core:get_ui_root():InterfaceFunction("QuitForScript")`.

### Ключи командной строки

Найдены: `-autotest`, `-swallow_asserts`, `-no_exception_handler`, `-multirun`, `-timeout`, `-sptest`, `-epiclocale=`. Ключей `-nomovie` и `-skip*` в exe нет.

**`-autotest`** (`FUN_1408ba0a4`, `FUN_1405af868`):

- Пытается загрузить `AutoTestInitialiser.retail.x64.dll`. Файла в папке игры нет, ошибка игнорируется.
- Ставит `state+0x62 = 0`, то есть логотипов и предупреждения не будет. Это единственный найденный ключ, который их убирает.
- Ставит `state+0x63 = 1` (то же, что `skip_directx_version_check`) и ещё два флага, назначение которых не разобрано (`0x143de7a08`, `0x143ddf360`; второй читают многие функции).
- **Не ставит обработчик исключений** `SetUnhandledExceptionFilter(FUN_141334404)`. Вероятно, при падении не появится `crash_report`, и `run_game.py` увидит только выход процесса.

Нужен только для способов 2 и 3. Для способа 1 не нужен. Ключ ищется как подстрока всей командной строки, а разбор команд идёт отдельно: токен `-autotest;` даст сообщение `cannot find command, variable or file`, после чего разбор продолжится (`FUN_14054f920`). Ставить его только отдельной командой: `-autotest; game_startup_mode ...`. Не пробовалось.

**`auto_run_script <путь>`** (`FrontEnd.cpp`, `FUN_14329238c`, потребитель `FUN_143292e7c`). Настоящий путь автотестов CA: создаёт объект по адресу `0x144480c28`, после чего `common.is_autotest()` становится истиной. Нам не нужен, потому что `script/frontend/mod` уже работает, а флаг автотеста меняет поведение скриптов (`lib_campaign_manager.lua:2399`, `frontend_start.lua:27`).

**Другие команды** (всего по шаблону регистрации нашлась 191 запись, список неполный):

- `all_players_ai`, `campaign_autorun` (`FUN_1423b831c`), `play_ai_land_battles_percentage`: прогоны ИИ;
- `fast_campaign_toggle`, `fast_campaign_target <до 10000>` (`EmpireCampaignEnv.cpp:3997,4003`): значение читают `FUN_1422bd7e8`, `FUN_1423b7bc0`, `FUN_1423d0434`, назначение не разобрано, стоит попробовать на конце хода;
- `campaign_tick_pause <bool>`, `set_model_tick_time_ms`, `constant_random_seed`, `skip_episodic_battles`, `show_advice`;
- `docudemon`: пишет документ со всеми командами и настройками. Стоит вызвать один раз при свободной игре;
- `find_tweaker_or_command <слово>`: поиск команд.

**Настройки CA в скриптах.** `SCRIPTED_TWEAKER_02`, `DISABLE_PRELUDE_CAMPAIGN_SCRIPTS`, `UNLOCK_FRONTEND_MOVIES` в exe строками не встречаются, поэтому в этой сборке через команду не включаются (в файлах). Строка в exe подтверждает, что в retail настройки так не меняют.

### Команды важнее файла настроек

Порядок в `FUN_14060def0`: сначала `preferences.script.txt` (`FUN_14060e28c`), затем `user.script.txt` (`FUN_14060e1fc`), затем разбор команд `FUN_14060e1a4`. Разбор `FUN_14054f920` ищет токен как команду, затем как переменную (настройку), затем как файл в папке игры, затем в `scripts/`. Отсюда два вывода:

1. **Настройки можно задавать на запуск, не трогая файл пользователя** (в файлах). Например, в `tww3_mtb_mods.txt`:

   ```text
   mod "tww3_mtb_harness.pack";
   write_preferences_at_exit false;
   fe_game_intro_video_enabled false;
   incremental_autosave_enabled false;
   advice_level 0;
   campaign_difficulty 1;
   battle_difficulty 1;
   ```

   Сначала проверить на одной заметной настройке (например, `x_res`). Пока это не подтверждено, копию и возврат файла настроек убирать нельзя. Настройки окна могут читаться раньше, это тоже проверить.
2. `user.script.txt` использовать не надо: он читается при каждом запуске, в том числе у пользователя и соседа.

## Видео и их длительность

Заголовки `CAMV` в `movies.pack` и `movies_dwf.pack` (кадры × 33,33 мс):

| Файл | Секунд | Когда |
|---|---|---|
| `startup_movie_01…05` | 5,0 + 3,0 + 6,4 + 2,0 + 2,0 = 18,4 | Каждый запуск меню |
| `epilepsy_warning_ru` | 15,0 | Каждый запуск меню |
| `gam_int` | 96,0 | Если `fe_game_intro_video_enabled true`; у пользователя `false` |
| `warhammer3/dwf/malakai_intro` | 61,5 | Новая кампания Малакая |

Итого 33,4 с перед меню. Пропускаются ли они раньше сами, неизвестно.

**Обойти логотипы без `-autotest`:** положить в тестовый пак однокадровые `movies/startup_movie_0N.ca_vp8` и `movies/epilepsy_warning/epilepsy_warning_ru.ca_vp8`. `FUN_1432a9db4` перебирает номера, пока файл есть, поэтому файлы нужно подменить, а не убрать. Так же работают моды сообщества. `exclude_pack_file movies.pack` я бы не использовал: исчезнут и остальные видео этого пака.

`_G.suppress_intro_movie = true` (`frontend_start.lua:55`) отключает только `gam_int`.

## Настройки пользователя

`preferences.script.txt`, только чтение:

| Ключ | Значение | Смысл |
|---|---|---|
| `fe_game_intro_video_enabled` | `false` | `gam_int` уже выключен |
| `advice_level` | `0` | Советник на минимуме |
| `advisor_mode` | `2` | Текст и голос |
| `fast_forward_end_turns` | `true` | Быстрый конец хода уже включён |
| `incremental_autosave_enabled` | `true`, лимит 6 | `run_game.py` выключает на сессию |
| `save_to_cloud`, `autosave_to_disk_and_cloud` | `false` | Облако не участвует |
| `incompatible_save_games_enabled` | `false` | Несовместимые сейвы не грузятся из меню |
| `write_preferences_at_exit` | `true` | При обычном выходе файл перезаписывается |
| `enable_context_viewer` | `false` | Отладочная консоль выключена |

**`steam -applaunch 1142710 <аргументы>`** не нужен. Прямой запуск exe работает (`steam_appid.txt` есть, подтверждено всеми прогонами), и при нём известен PID, который нужно закрыть.

## Скрипты кампании

Вступление новой кампании (все пути в `script/`):

1. `campaign/main_warhammer/wh_start.lua:29-82`: на первом тике `faction_intro:perform_intro("main_warhammer", фракция)`.
2. `campaign/faction_intro.lua:341` → `cm:setup_campaign_intro_cutscene` (`_lib/lib_campaign_manager.lua:2666`). При сохранённой игре функция сразу выходит: `if not self:is_new_game() ... return` (`:2667`). **В своём сейве вступления нет.**
3. Для Малакая (`main_warhammer_faction_intro.lua:791`): `fullscreen_movie = "warhammer3/dwf/malakai_intro"`, облёт `wh3_camp_flyover_norska_kislev_01`, затем советник `wh3_dlc25_ie_camp_dwf_malakai_makaisson_intro_01`.

Снятие вступления для новой кампании (только тестовый пак; не пробовалось; задания из вступления при этом не выдаются):

```lua
-- script/campaign/mod/tww3_mtb_no_intro.lua
cm:add_pre_first_tick_callback(function()
    if not cm:is_new_game() then return end
    faction_intro.perform_intro = function()
        core:progress_on_loading_screen_dismissed(function()
            core:trigger_event("ScriptEventIntroCutsceneFinished")
            core:trigger_event("ScriptEventCampaignIntroComplete")
        end)
    end
end)
```

Этих событий ждут `wh_campaign_interventions.lua:10631` и `wh_campaign_scripted_tours.lua:1737,2358,6119`. Порядок `add_pre_first_tick_callback` и первого тика по чтению кода не проверен до конца.

Другие полезные вызовы:

- `cm:set_advice_enabled(false)` (`:13674`), `cm:suppress_all_event_feed_messages(true)` (`:16651`), `cm:disable_event_feed_events(...)` (`:16700`); в exe есть `disable_event_panel_auto_open`;
- сохранение: `cm:save(callback)` (`:1975`) = `disable_saving_game(false)` + `autosave_at_next_opportunity()`. Команды сохранить под именем у скриптов нет, поэтому файл надо переименовать после сессии;
- конец хода: `find_uicomponent(core:get_ui_root(), "hud_campaign", "faction_buttons_docker", "button_end_turn"):SimulateLClick()` (путь из `lib_campaign_ui.lua:4457`). В exe есть ещё `end_turn_for_faction`, `set_ai_uses_human_display_speed`, в скриптах CA примеров вызова нет;
- `core:progress_on_loading_screen_dismissed`: в fe8 между загрузкой и снимком кликов по экрану загрузки не было, значит сейв его проходит сам (догадка по журналу команд).

**Автотесты CA.** `script/autorun.lua` устарел: требует `data.script.all_scripted`, старые имена кнопок, кампания без выбора лорда. `script/benchmarks/` и `cm:is_benchmark_mode()` работают только в режиме бенчмарка. В `all_scripted.lua` есть `__lib_type_autotest`. Строки `session_autotest_benchmark_*`, `load_test`, `%Sbattle_load_test.bat` относятся к внутренней сборке с отсутствующей у нас DLL.

## Бой кампании

Команды через `tools/rc.py` или свой файл. Сигнатуры взяты из кода; цепочка целиком не пробовалась.

```lua
-- Малакай атакует созданную армию
local leader = cm:get_faction("wh3_dlc25_dwf_malakai"):faction_leader()
assert(leader:has_military_force())
Forced_Battle_Manager:trigger_forced_battle_with_generated_army(
    leader:military_force():command_queue_index(),
    "wh_main_grn_greenskins", "wh_main_sc_grn_greenskins", -- фракция, шаблон по субкультуре
    8, 1,   -- размер, сила
    false,  -- атакует игрок
    true,   -- убрать армию после боя
    false)  -- не засада
```

`wh2_campaign_forced_battle_manager.lua`: сам создаёт армию, объявляет войну и вызывает `cm:force_attack_of_opportunity(атакующий_cqi, цель_cqi, засада, обычный_бой)` (`:452,463`). Шаблон взят по образцу `episode_glottkin.lua:750`; проверьте значение через `cm:get_faction(...):subculture()`.

Ручной вариант: `cm:create_force(фракция, "юнит1,юнит2", регион, x, y, true, function(char_cqi, force_cqi) ... end)` (`:6501`), `cm:force_declare_war`, `cm:force_attack_of_opportunity`. Место: `cm:find_valid_spawn_location_for_character_from_character`.

Дальше кнопки. Все строки есть в exe, но id надо уточнить через `mtb.tree` на открытой панели:

1. панель `popup_pre_battle`, кнопка `button_attack` (`button_autoresolve` для автобоя);
2. в бою `bm:end_deployment()` (`lib_battle_manager.lua:1215`) или `button_battle_start`;
3. выход: `bm:end_battle()` (`:1735`), затем `button_dismiss_results` или `button_end_battle`.

Ускорение: второй сейв с уже стоящей рядом вражеской армией, тогда остаётся один вызов `force_attack_of_opportunity`.

Если тест проверяет только модель на поле, уже есть быстрый запуск `tools/run_battle.py` (XML, около 83 с по замеру соседа). Бой кампании нужен, чтобы проверить данные кампании, например Дух Грунгни.

**Повторы без перезапуска.** `InterfaceFunction("QuitForScript")` возвращает в меню, затем `frontend.load_campaign(...)`. У соседа повтор боя в процессе занимал 11 с вместо 83 с; для кампании замера нет. Новый пак так не подхватить, только Lua из файлов.

## memreader Plus и мод быстрой загрузки

**memreader Plus** (`scratchpad/ext/mr/README.md`) здесь не нужен:

- `call`: `frontend.load_campaign` и `start_campaign` уже доступны из Lua;
- `hook`: можно перехватить `FUN_1432a9db4` или поставить `state+0x62`, но скрипт загрузится только после этих шагов, а адреса зависят от сборки;
- `file_edit`: работает с текстом (XML, `.twui.xml`), видео не меняет. Может убрать панели, но пока это не нужно;
- полезен отчёт о падениях: он записывает стек Lua. Для падения из-за отсутствующего мода можно было бы прочитать ключ в `FUN_1426be2b0` через `hook`. Если причина подтвердится правилом о паках, это не нужно.

**Мод 3816496233 (`faster_loading_script_cache`, файл `!!!!!!!!!!!!!!!!!!!!!_loadfast.lua`).** Кэширует скомпилированные скрипты модов (`string.dump`) в `loadfast_cache_<среда>.bin`, проверяя отпечаток списка модов. Автор пишет про 30 мс на файл из пака и 890 скриптов под Proton. На этой машине, по `loadfast_log.txt`, скрипты занимают 209–297 мс на всю кампанию без кэша при 39–42 модах. Для теста с одним-двумя паками выигрыша нет. Он пишет файлы в папку игры, в свой список модов его включать незачем.

## Сообщество

- **Workshop 2789854789, «Disable startup splash screens / intros»:** существует, виден в выдаче поиска, правка в журнале от мая 2023. [Журнал изменений](https://steamcommunity.com/sharedfiles/filedetails/changelog/2789854789?p=2), [обсуждение](https://steamcommunity.com/sharedfiles/filedetails/comments/2789854789). Сама страница вернула HTTP 429, как он устроен и работает ли на 9.0, я не прочитал.
- **Аналог для WH2:** заменяет три стартовых видео пустыми ([описание](https://catalogue.smods.ru/archives/155508)). То же, что предложено выше.
- **tw-modding wiki:** [страница Lua](https://www.tw-modding.com/wiki/Lua), [Calling Scripts](https://tw-modding.com/wiki/Lua:Calling_Scripts). По фрагменту из поиска, `UICreated` меню приходит после вступительных роликов. Прямой запрос к [Commands, Interfaces & Listeners](https://www.tw-modding.com/wiki/Lua:Commands,_Interfaces_%26_Listeners) не прошёл (соединение отклонено), прочитаны только фрагменты.
- **Da Modding Den:** это Discord, доступа нет.
- По `game_startup_mode campaign_load`, `frontend.load_campaign`, автозагрузке при старте поиск ничего не дал. Всё в этом документе по этим темам взято из самой игры.

## Сколько это экономит

| Что убирается | Секунд | Основание |
|---|---|---|
| Логотипы и предупреждение | 33,4 | Заголовки видео |
| Видео Малакая (только новая кампания) | 61,5 | Заголовок видео |
| Облёт и советник вступления | неизвестно | Не замерялось |
| Меню и переходы | неизвестно | В fe3 меню было на снимке через 75 с после старта, это верхняя граница с задержками агента |

Загрузка самой кампании останется: от старта скрипта кампании до первого тика 34–50 с при 40 модах (`script_log_281026_1314.txt`, `_1155.txt`). С меньшим числом модов, вероятно, быстрее. Общего замера нет. Для сравнения, fe8 дошёл до карты не позже чем через 161 с с 42 модами, включая задержки агента.

## План

**Один раз (и при смене ключей в паках):**

```powershell
py -3.14 tools/build.py --target harness
py -3.14 tools/run_game.py --label mksave --packs harness
py -3.14 tools/rc.py 'frontend.start_campaign("wh3_main_combi","wh3_main_combi","wh3_dlc25_dwf_malakai"); return "called"'
# дождаться remote_ready в mode campaign и конца вступления
py -3.14 tools/rc.py --events 5
py -3.14 tools/rc.py 'return {cm:get_local_faction_name(true), cm:turn_number(), cm:is_new_game()}'
py -3.14 tools/rc.py 'cm:save(function() mtb.log("saved", "ok") end); return "asked"'
py -3.14 tools/rc.py --stop
```

`run_game.py` перенесёт новый файл в `build/campaign/saves/`. Его надо переименовать в `tww3_mtb_malakai_t1.save`. Перед этим исправить повтор команды в пульте, иначе `start_campaign` выполнится ещё раз уже в кампании (там `frontend` нет, будет ошибка, но без вреда; с кликами опаснее).

**Каждый тест:**

```powershell
py -3.14 tools/run_game.py --label t --packs harness --save tww3_mtb_malakai_t1.save --args "game_startup_mode campaign_load tww3_mtb_malakai_t1.save"
```

Готовность: событие `remote_ready` с `mode=campaign` в `tww3_mtb_events.jsonl`. Затем проверка фракции и команды теста.

**Что проверить в игре, по порядку:**

1. `campaign_load`: загрузка, отсутствие логотипов, время от запуска до `remote_ready`.
2. `start_campaign` с новым порядком: Малакай ли получился.
3. Появляется ли автосохранение при `incremental_autosave_enabled false` и как называется файл.
4. Сейв, созданный с пультом, плюс пак мода: загружается ли.
5. Вариант с путём вне `save_games`, например `tww3_mtb_saves/x.save` в папке игры: тогда папка сейвов пользователя вообще не затрагивается. Внутренняя функция загрузки получает путь как есть, поэтому результат не очевиден.
6. Настройки из командной строки вместо правки файла.
7. Цепочка боя и id кнопок.
8. `-autotest`, если останется способ через меню: не помешает ли отсутствие `crash_report`.

**Что затрагивает данные пользователя:**

- `--save` временно кладёт наш файл в `save_games`; `run_game.py` убирает его и сверяет остальные. В fe8 так был восстановлен `scripts/mct_registry.lua`, который переписал один из модов.
- Файл настроек правится на сессию, копия возвращается (пока не проверен п. 6).
- `start_campaign` может записать значение в реестр, если его нет.
- `used_mods.txt`, сейвы пользователя и файлы соседа не меняются. Загружать сейв пользователя («Продолжить», `last_campaign`, `continue_campaign`) в тестах не надо: результат зависит от его списка модов, и его сейв не должен быть условием теста.
