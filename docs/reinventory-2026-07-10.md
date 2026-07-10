# Реинвентаризация Alterios MCP от 2026-07-10

Документ фиксирует текущее состояние MCP после live-проверки проекта ART X и
разрыв между уже доказанными API-возможностями Alterios и тем, что сейчас
доступно как удобные typed MCP tools.

## Контекст Проверки

| Параметр | Значение |
|---|---|
| Профиль | `artx` |
| Project base / workspace | `4e247a6b-55ef-4665-b88c-3c156fee19ba` |
| Приватный конфиг | Через `ALTERIOS_DOTENV_PATH`, секреты не выводились |
| Smoke запуска | `alterios-discover.exe --profiles --profile artx --json` |
| Read-only discovery | 15/15 маршрутов OK |

Проверенный профиль видит 2 экземпляра конфигурации: `artx` и `vniimt`.
Для `artx` заданы `base_url`, token, `project_id`, endpoint
`{base_url}/api/scripts/execute-manual`, `auth_header=x-api-key`.

## Live-Состояние Project Base

| Сущность | Количество |
|---|---:|
| Типы контента | 14 |
| Поля | 2529 |
| Представления | 22 |
| Формы | 40 |
| Скрипты | 12 |
| BPMN-диаграммы | 4 |
| Контент-записи | 145 |
| Задачи | 1 |
| Процессы | 17 |
| Отчеты | 1 |
| Группы меню | 11 |

В project base уже есть управляемая sandbox-цепочка `MCP Practice`:

- тип контента `MCP Practice. Песочница`;
- представление `MCP Practice. Список`: 1 entity, 8 полей (`ID`,
  `Название`, `Статус`, `Оценка`, `Дата проверки`, `Проверено`,
  `Комментарий`, `Файл`);
- формы `MCP Practice`, `MCP Practice. Добавить запись`,
  `MCP Practice. Карточка записи`;
- запись `MCP Practice. Тестовая запись`;
- manual script `MCP Practice. Manual Script Sandbox`;
- BPMN `MCP Practice. BPMN Sandbox`;
- dashboard report `MCP Practice. Report Sandbox`.

Отдельно обнаружены Codex-managed демо-сущности HR-маршрутизации и массового
удаления, которые полезны как дополнительные образцы форм, скриптов и BPMN.

## Фактический MCP Surface

На момент реинвентаризации в `src/alterios_mcp/server.py` было опубликовано
23 MCP tools, из них write-like tools только 4. Первый кодовый этап после этой
реинвентаризации добавил 2 typed content/file tools; текущий surface: 25 tools,
6 write-like tools.

| Tool | Что делает | Ограничение |
|---|---|---|
| `alterios_add_comment` | Typed comment write | Покрывает только комментарии |
| `alterios_update_content_fields` | Typed content write | Добавлено после реинвентаризации; PATCH `/api/contents/save` с preflight/diff/readback |
| `alterios_file_upload_to_field` | Typed file-field write | Добавлено после реинвентаризации; multipart upload + сохранение file value |
| `alterios_call_write_service` | Generic runtime service write | Нет typed контракта по сущностям |
| `alterios_execute_manual_script` | Запуск сохраненного manual script UUID | Не создает и не обновляет скрипты |
| `alterios_rest_write` | Generic REST write | Слишком широкий интерфейс для стабильной работы |

Вывод: live API-практика уже доказала больше, чем текущий MCP surface удобно
экспортирует. Нужно расширять именно typed write tools, а generic REST оставить
как аварийный/исследовательский слой.

## Представления

Уже доказано в sandbox:

- `POST /api/views`;
- `POST /api/view-entities`;
- `POST /api/view-entities/add-one-field`;
- `POST /api/view-fields/save`;
- `GET /api/views/{viewId}`;
- `GET /api/view-entities/by-view/{viewId}`;
- `GET /api/view-fields/populated/{viewId}`;
- `POST /api/views/v2/get-data-simplified`.

Нужные typed tools:

| Tool | Назначение |
|---|---|
| `alterios_upsert_view` | Создать/обновить представление по имени, формату, strict/settings |
| `alterios_upsert_view_entity` | Привязать content type или системную entity к view |
| `alterios_upsert_view_field` | Добавить/обновить поле view, alias/order/visibility/settings |
| `alterios_validate_view_data` | Проверить, что view реально читает project base |

Обязательные правила: `profile`, явный `project_id`, preflight по имени/ID,
dry-run diff, отказ от обновления чужих объектов без managed marker, readback.

## Формы

В 40 формах project base обнаружены основные UI-типы:

| Тип компонента | Количество в формах |
|---|---:|
| `action` | 69 |
| `forms` | 28 |
| `data_managing` | 22 |
| `view_data_list` | 18 |
| `view_data` | 12 |
| `routing` | 9 |
| `content` | 8 |
| `manual_script` | 7 |
| `context` | 7 |
| `delete_contents` | 6 |
| `dependent_content` | 4 |
| `report` | 1 |
| `comments_list` | 1 |
| `help` | 1 |
| `edit_task` | 1 |
| `processes` | 1 |

Уже доказано: создание форм, формы add/edit/main, action-контейнеры,
`data_managing`, `view_data_list`, `view_data`, `comments_list`, `report`.

Нужные typed tools:

| Tool | Назначение |
|---|---|
| `alterios_upsert_form` | Создать/обновить форму целиком с tabs и action containers |
| `alterios_patch_form_actions` | Узко менять кнопки/действия без перезаписи всей формы |
| `alterios_patch_form_tabs` | Узко менять вкладки/компоненты |
| `alterios_validate_form_surface` | Проверить ссылки на view/form/script/report/process |

Особый риск: форма - это UI-контракт, поэтому readback по JSON недостаточен.
Для пользовательских изменений нужна UI-проверка или сохраненный HAR/screenshot.

## Скрипты

Live-состояние:

| Тип | Количество |
|---|---:|
| `manual` | 9 |
| `event` | 2 |
| `diagram` | 1 |

Уже доказано: `POST /api/scripts`, `POST /api/scripts/execute-manual`.
В каталоге также есть update-route `PUT /api/scripts`, но typed update еще не
экспортирован как MCP tool.

Нужные typed tools:

| Tool | Назначение |
|---|---|
| `alterios_upsert_script` | Создать/обновить manual/event/diagram script |
| `alterios_validate_script` | Проверить type, active, librariesIds, config, managed marker |
| `alterios_execute_manual_script` | Оставить, но усилить preflight и readback |
| `alterios_bind_script_to_form_action` | Связать manual script с кнопкой формы |

Важно: runtime service names (`getTasks`, `createContent`, `startProcess`) и
manual script UUID - разные уровни. Endpoint `/api/scripts/execute-manual`
выполняет сохраненный скрипт по UUID.

## BPMN, Процессы И Задачи

Уже доказано:

- `POST /api/diagrams`;
- `POST /api/processes`;
- `GET /api/tasks/`;
- `DELETE /api/tasks/complete`;
- readback процессов через `/api/processes/listandcount`.

Sandbox BPMN `MCP Practice. BPMN Sandbox` содержит start/user/end events,
имеет 1 процесс, процесс завершен, активных задач нет.

Дополнительный HR demo BPMN имеет 12 процессов, 11 завершенных, 1 активную
задачу. Это полезный источник для анализа реальных side effects.

Нужные typed tools:

| Tool | Назначение |
|---|---|
| `alterios_upsert_bpmn_diagram` | Создать/обновить диаграмму и settings |
| `alterios_start_process` | Запустить процесс по diagram/content |
| `alterios_list_process_tasks` | Прочитать активные задачи процесса |
| `alterios_complete_task` | Завершить задачу с контролем process/task/content |
| `alterios_validate_process_result` | Проверить completed/error/status/stages |

Task completion должен оставаться side-effect operation с отдельным audit и
readback. Для destructive/stopping flows нужен отдельный этап.

## Отчеты И Project Base

В project base сейчас 1 отчет: `MCP Practice. Report Sandbox`.
Full readback подтвержден. Сохраненный Stimulsoft template содержит:

- dashboard page (`StiDashboard`);
- `CodexMarker: Codex-managed: alterios-mcp report sandbox.`;
- `Dictionary.DataSources`;
- `Dictionary.Databases`;
- `ServiceName: Project Database`;
- alias/name source `MCP Practice. Список`.

Буквальный `view-data-v2` в сохраненном template не найден; текущая проверенная
связь с project base идет через Stimulsoft `Project Database`. Следующий tool
должен проверять оба уровня: report template и контрольное чтение исходного view
через `/api/views/v2/get-data-simplified`.

Нужные typed tools:

| Tool | Назначение |
|---|---|
| `alterios_upsert_report` | Создать/обновить report metadata и template |
| `alterios_validate_report_project_base` | Проверить Project Database datasource + view readback |
| `alterios_report_full` | Уже есть; оставить как readback tool |
| `alterios_patch_report_template` | Узко менять dashboard/report JSON без потери datasource |

## Главный Gap

Проблема не в том, что нет write API. Проблема в том, что write API пока
экспортирован в MCP как generic operations. Для полноценного MCP нужны typed
commands по сущностям:

1. content/content fields/file-field;
2. views/view entities/view fields;
3. forms/form actions/form components;
4. scripts/manual/event/diagram scripts;
5. BPMN/process/task side effects;
6. reports/Stimulsoft Project Database;
7. groups/help/comments;
8. security/destructive flows отдельным gated этапом.

## План Дальше

| Этап | Что сделать | Acceptance criteria |
|---|---|---|
| 1 | Исправить и зафиксировать запуск MCP через `alterios-mcp.exe` | README содержит рабочий Codex config и smoke через `alterios-discover.exe` |
| 2 | Вынести общие typed write helpers | Единые preflight, dry-run diff, managed-marker guard, write-gate, readback |
| 3 | Добавить content/file typed tools | Выполнено: `alterios_update_content_fields`, `alterios_file_upload_to_field`, тесты, live sandbox readback |
| 4 | Добавить views/forms typed tools | Upsert view/entity/field/form/action, sandbox idempotency, UI/HAR validation |
| 5 | Добавить scripts typed tools | Upsert manual/event/diagram script, execute preflight, form binding |
| 6 | Добавить BPMN/process/task tools | Diagram upsert, process start, task list/complete, process result validation |
| 7 | Добавить report tools | Upsert report, Project Database validation, full readback |
| 8 | Добавить repo agents/skills | Агентные роли и skill-пакеты привязаны к проверенным tools и docs |
| 9 | Закрыть security/destructive flows | Только после отдельного sandbox сценария и явного destructive gate |

Первый кодовый шаг после этой реинвентаризации выполнен: typed content/file
tools добавлены и проверены на `MCP Practice` sandbox. Следующий шаг - typed
views/forms tools, потому что они закрывают основной UI-конструкторский слой.
