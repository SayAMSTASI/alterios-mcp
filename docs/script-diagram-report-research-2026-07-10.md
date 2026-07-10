# Scripts, BPMN diagrams, and report source rules

Date: 2026-07-10
Profile: `artx`
Project: `4e247a6b-55ef-4665-b88c-3c156fee19ba`
Base URL: `https://lims.artx.ru`

This is a live research note for the ART X sandbox project. Secrets were not
printed or stored. The created report is a Codex-managed sandbox object.

## Script types

Live inventory route: `GET /api/scripts/listandcount`.

Observed in this project: 12 scripts.

| Type | Count | Purpose | Main calls |
|---|---:|---|---|
| `manual` | 9 | Saved scripts that can be executed explicitly by UUID. | `POST /api/scripts`, `PUT /api/scripts`, `POST /api/scripts/execute-manual` |
| `event` | 2 | Saved event handlers. They are stored as scripts, but execution is driven by Alterios event bindings, not by runtime service names. | `POST /api/scripts`, `PUT /api/scripts` |
| `diagram` | 1 | Script used from BPMN/diagram runtime, for example a script task. | `POST /api/scripts`, `PUT /api/scripts` |

Common saved script fields observed for all three types:

- `_id`, `name`, `description`, `type`, `active`, `body`, `share`,
  `config`, `librariesIds`, `projectId`, `version`;
- `body` is stored as a string;
- `config` can contain `cron` and, for event/diagram examples, `arguments`;
- all observed scripts were active.

Important split:

- `manual` script execution uses a saved script UUID:
  `POST /api/scripts/execute-manual` with body
  `{"_id": "<script-id>", "args": {...}}`;
- runtime service names such as `getTasks`, `getContents`, `startProcess` are
  not saved script UUIDs and must not be sent to `/api/scripts/execute-manual`;
- `event` and `diagram` scripts should be written and validated as metadata,
  then checked through the event/BPMN flow that invokes them.

## BPMN diagram task inventory

Live inventory route: `GET /api/diagrams/listandcount`.

Observed in this project: 4 diagrams. Parsed BPMN node totals:

| BPMN node | Count |
|---|---:|
| `startEvent` | 4 |
| `endEvent` | 5 |
| `userTask` | 5 |
| `scriptTask` | 1 |
| `sequenceFlow` | 12 |

Task-like nodes observed across all diagrams:

| Diagram | Task type | Task id | Name | Form key | Outgoing flows |
|---|---|---|---|---|---|
| `MCP Practice. BPMN Sandbox` | `userTask` | `Activity_mcp_practice_task` | `MCP Practice task` | `15f5fb26-5db4-4153-8131-23a54411cd63` | `Flow_to_end` / `Complete sandbox task` |
| `Выбор оборудования` | - | - | No task nodes; start event routes directly to end events. | - | `Flow_1q6pfjy`, `Flow_09534ll` |
| `Демо HR-маршрутизация. Процесс` | `userTask` | `Activity_stage_1` | `1. Первичная задача` | `a4ceb740-b6bc-462d-9420-a0c374f356a1` | `Flow_to_stage_2` / `Уточнить подразделение` |
| `Демо HR-маршрутизация. Процесс` | `userTask` | `Activity_stage_2` | `2. Уточнить подразделение` | `a4ceb740-b6bc-462d-9420-a0c374f356a1` | `Flow_to_stage_3` / `Создать задачу МОЛ` |
| `Демо HR-маршрутизация. Процесс` | `userTask` | `Activity_stage_3` | `3. Выполнение МОЛ` | `a4ceb740-b6bc-462d-9420-a0c374f356a1` | `Flow_stage_3_done` / `Завершить` |
| `Демо HR-маршрутизация. Процесс` | `scriptTask` | `Activity_complete` | `Отметить завершение` | - | `Flow_to_end` |
| `Статус согласования отчета` | `userTask` | `Activity_0houqkq` | `Согласование` | `24e1a9c8-552b-4f83-9f56-32e3145db0a6` | `Flow_1brkl7b` / `Согласовано`; `Flow_1acuodu` / `Не согласовано` |

User-task settings observed in XML:

- `camunda:formKey` links a task to the form opened for work;
- `camunda:savable="true"` is present on user tasks;
- `camunda:candidateUsers` and `camunda:candidateGroups` can be empty strings;
- task completion needs a task id and usually the selected outgoing
  `nextFlowId`;
- after `POST /api/processes`, check active tasks through `GET /api/tasks/`
  and process state through `GET /api/processes/listandcount`.

Current typed MCP coverage:

- create/update diagram: `alterios_upsert_bpmn_diagram`;
- start process: `alterios_start_process`;
- read process/tasks: `alterios_list_process_tasks`;
- complete task: `alterios_complete_task`;
- validate side effects: `alterios_validate_process_result`.

## Report creation test

Created a separate sandbox report:

| Field | Value |
|---|---|
| Name | `MCP Practice. Source Rules Report` |
| Report id | `35b6bdbe-f4ae-4ec1-99e9-c23db4df4543` |
| Type | `dashboard` |
| Marker | `Codex-managed: alterios-mcp report source rules research.` |
| Source view id | `cfd46277-d8da-4b7d-ba0e-7c96ea85046e` |
| Source view name | `MCP Practice. Список` |

Validated after save:

| Check | Result |
|---|---|
| `/api/reports/full/{filter}` readback | OK |
| Stimulsoft dashboard page exists | OK |
| `Project Database` source exists | OK |
| Codex marker matches | OK |
| Source view name exists in template | OK |
| `POST /api/views/v2/get-data-simplified` source readback | OK, `row_count=1` |

The source template was copied from the existing managed sandbox report and
then narrowed to a new marker/report name. The original source report was not
modified.

## Report source binding rules

Use these rules when connecting an Alterios view as a report source.

1. Treat the Alterios project as the data boundary. Always pass explicit
   `profile` and `project_id`; do not rely on a stale default project from
   `.env`.
2. Verify the source view first:
   `POST /api/views/v2/get-data-simplified` with
   `{"viewId": "<view-id>", "limit": 5, "offset": 0}`.
3. Save reports through `/api/reports`:
   create with `POST /api/reports`, update with `PUT /api/reports`.
4. Read full reports through:
   `GET /api/reports/full/{encode_filter({"_id": report_id})}`.
5. Store Stimulsoft dashboard template as JSON in `template`; dashboard page
   should contain `Pages/0/Ident = StiDashboard`.
6. The Stimulsoft dictionary must contain a Project Database connection:
   `Dictionary.Databases[*].ServiceName = "Project Database"`.
7. The data source must also reference Project Database and the source view:
   `Dictionary.DataSources[*].ServiceName = "Project Database"`,
   `Alias` or `NameInSource` equal to the Alterios view name.
8. Keep data source columns synchronized with the view fields. If the view
   fields or joins change, rebuild or refresh the Stimulsoft data source; do
   not assume old columns are still valid.
9. Add a stable `CodexMarker` to the template and a `Codex-managed` marker to
   the report description before allowing automated updates.
10. After save, validate both layers: report template structure and live source
    data via `get-data-simplified`.

PowerShell note: do not pass Cyrillic expected strings through a plain here
string in this environment. Use Unicode escapes, for example
`MCP Practice. \u0421\u043f\u0438\u0441\u043e\u043a`, or read the expected
name from API data. Plain Cyrillic literals were converted to `??????` and
caused a false negative in `view_name_matches`.
