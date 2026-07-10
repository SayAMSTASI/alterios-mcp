# Скрипты, BPMN-диаграммы и правила источников отчетов

Дата: 2026-07-10
Profile: `artx`
Project: `<sandbox-project-id>`
Base URL: `<alterios-base-url>`

Это live research note по ART X sandbox project. Secrets не печатались и не
сохранялись. Созданный report - Codex-managed sandbox object.

## Типы скриптов

Live inventory route: `GET /api/scripts/listandcount`.

В проекте найдено 12 scripts.

| Type | Count | Назначение | Основные calls |
|---|---:|---|---|
| `manual` | 9 | Saved scripts, которые можно запускать явно по UUID. | `POST /api/scripts`, `PUT /api/scripts`, `POST /api/scripts/execute-manual` |
| `event` | 2 | Saved event handlers. Хранятся как scripts, но execution идет через Alterios event bindings. | `POST /api/scripts`, `PUT /api/scripts` |
| `diagram` | 1 | Script для BPMN/diagram runtime, например script task. | `POST /api/scripts`, `PUT /api/scripts` |

Общие поля saved script для всех трех типов:

- `_id`, `name`, `description`, `type`, `active`, `body`, `share`,
  `config`, `librariesIds`, `projectId`, `version`;
- `body` хранится строкой;
- `config` может содержать `cron`, а для event/diagram примеров - `arguments`;
- все наблюдаемые scripts были active.

Важное разделение:

- `manual` script execution использует saved script UUID:
  `POST /api/scripts/execute-manual` с body
  `{"_id": "<script-id>", "args": {...}}`;
- runtime service names вроде `getTasks`, `getContents`, `startProcess` не
  являются saved script UUID и не отправляются в `/api/scripts/execute-manual`;
- `event` и `diagram` scripts нужно писать и валидировать как metadata, а
  затем проверять через event/BPMN flow, который их вызывает.

## Inventory BPMN task nodes

Live inventory route: `GET /api/diagrams/listandcount`.

В проекте найдено 4 diagrams. Parsed BPMN node totals:

| BPMN node | Count |
|---|---:|
| `startEvent` | 4 |
| `endEvent` | 5 |
| `userTask` | 5 |
| `scriptTask` | 1 |
| `sequenceFlow` | 12 |

Task-like nodes по всем diagrams:

| Diagram | Task type | Task id | Name | Form key | Outgoing flows |
|---|---|---|---|---|---|
| `MCP Practice. BPMN Sandbox` | `userTask` | `Activity_mcp_practice_task` | `MCP Practice task` | `15f5fb26-5db4-4153-8131-23a54411cd63` | `Flow_to_end` / `Complete sandbox task` |
| `Выбор оборудования` | - | - | Нет task nodes; start event идет напрямую к end events. | - | `Flow_1q6pfjy`, `Flow_09534ll` |
| `Демо HR-маршрутизация. Процесс` | `userTask` | `Activity_stage_1` | `1. Первичная задача` | `a4ceb740-b6bc-462d-9420-a0c374f356a1` | `Flow_to_stage_2` / `Уточнить подразделение` |
| `Демо HR-маршрутизация. Процесс` | `userTask` | `Activity_stage_2` | `2. Уточнить подразделение` | `a4ceb740-b6bc-462d-9420-a0c374f356a1` | `Flow_to_stage_3` / `Создать задачу МОЛ` |
| `Демо HR-маршрутизация. Процесс` | `userTask` | `Activity_stage_3` | `3. Выполнение МОЛ` | `a4ceb740-b6bc-462d-9420-a0c374f356a1` | `Flow_stage_3_done` / `Завершить` |
| `Демо HR-маршрутизация. Процесс` | `scriptTask` | `Activity_complete` | `Отметить завершение` | - | `Flow_to_end` |
| `Статус согласования отчета` | `userTask` | `Activity_0houqkq` | `Согласование` | `24e1a9c8-552b-4f83-9f56-32e3145db0a6` | `Flow_1brkl7b` / `Согласовано`; `Flow_1acuodu` / `Не согласовано` |

Observed user-task XML settings:

- `camunda:formKey` связывает task с form, которая открывается для работы;
- `camunda:savable="true"` есть на user tasks;
- `camunda:candidateUsers` и `camunda:candidateGroups` могут быть пустыми;
- task completion требует task id и обычно selected outgoing `nextFlowId`;
- после `POST /api/processes` проверять active tasks через `GET /api/tasks/`
  и process state через `GET /api/processes/listandcount`.

Текущее typed MCP coverage:

- create/update diagram: `alterios_upsert_bpmn_diagram`;
- start process: `alterios_start_process`;
- read process/tasks: `alterios_list_process_tasks`;
- complete task: `alterios_complete_task`;
- validate side effects: `alterios_validate_process_result`.

## Тест создания отчета

Создан отдельный sandbox report:

| Field | Value |
|---|---|
| Name | `MCP Practice. Source Rules Report` |
| Report id | `35b6bdbe-f4ae-4ec1-99e9-c23db4df4543` |
| Type | `dashboard` |
| Marker | `Codex-managed: alterios-mcp report source rules research.` |
| Source view id | `cfd46277-d8da-4b7d-ba0e-7c96ea85046e` |
| Source view name | `MCP Practice. Список` |

Проверено после save:

| Проверка | Результат |
|---|---|
| `/api/reports/full/{filter}` readback | OK |
| Stimulsoft dashboard page exists | OK |
| `Project Database` source exists | OK |
| Codex marker matches | OK |
| Source view name exists in template | OK |
| `POST /api/views/v2/get-data-simplified` source readback | OK, `row_count=1` |

Source template скопирован из существующего managed sandbox report и сужен до
нового marker/report name. Исходный source report не менялся.

## Правила подключения report source

1. Считать Alterios project границей данных. Всегда передавать явные `profile`
   и `project_id`; не полагаться на stale default project из `.env`.
2. Сначала проверять source view:
   `POST /api/views/v2/get-data-simplified` с
   `{"viewId": "<view-id>", "limit": 5, "offset": 0}`.
3. Сохранять reports через `/api/reports`: create через `POST /api/reports`,
   update через `PUT /api/reports`.
4. Читать full reports через:
   `GET /api/reports/full/{encode_filter({"_id": report_id})}`.
5. Stimulsoft dashboard template хранить JSON в `template`; dashboard page
   должна содержать `Pages/0/Ident = StiDashboard`.
6. Stimulsoft dictionary должен содержать Project Database connection:
   `Dictionary.Databases[*].ServiceName = "Project Database"`.
7. Data source тоже должен ссылаться на Project Database и source view:
   `Dictionary.DataSources[*].ServiceName = "Project Database"`,
   `Alias` или `NameInSource` равен Alterios view name.
8. Data source columns должны совпадать с view fields. Если fields или joins
   изменились, перестройте или refresh Stimulsoft data source.
9. Добавляйте stable `CodexMarker` в template и `Codex-managed` marker в
   report description перед automated updates.
10. После save проверяйте оба слоя: структуру report template и live source
    data через `get-data-simplified`.

PowerShell note: не передавайте Cyrillic expected strings через обычный here
string в этой среде. Используйте Unicode escapes или читайте expected name из
API data; plain Cyrillic literals могут превратиться в `??????` и дать false
negative.
