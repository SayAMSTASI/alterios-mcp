# Покрытие методов и видов обращений Alterios

Документ отвечает на два вопроса:

1. сколько методов и маршрутов сейчас явно учитывает `alterios-mcp`;
2. какие виды обращений покрыты, а какие еще требуют live/HAR-подтверждения.

Контекст текущего покрытия:

- профиль: `artx`;
- проект: `4e247a6b-55ef-4665-b88c-3c156fee19ba`;
- основной sandbox: `MCP Practice`;
- дата ревизии: 2026-07-10.

## Сводка По Количеству

| Уровень | Количество | Что считается |
|---|---:|---|
| MCP tools | 25 | Публичные callable tools в `src/alterios_mcp/server.py`. |
| Write-like MCP tools | 6 | `alterios_add_comment`, `alterios_update_content_fields`, `alterios_file_upload_to_field`, `alterios_call_write_service`, `alterios_execute_manual_script`, `alterios_rest_write`. |
| Runtime service methods | 14 | Известные script-service имена в `src/alterios_mcp/services.py`. |
| Live read-only REST probes | 15 | Маршруты в `READONLY_ROUTES`, проверяемые discovery matrix. |
| REST route/method patterns in coverage registry | 57 | Read/detail/runtime/write/workflow/file/comment/report/security patterns ниже. |
| Виды обращений | 13 | Классы операций: от config/read до workflow, files, comments, security. |

Это не означает, что в Alterios больше нет скрытых внутренних endpoint-ов.
Текущая цель MCP - покрывать все **операционные виды обращений**, которые нужны
для работы с проектами, и расширять список конкретных маршрутов через live API,
browser/HAR capture и sandbox write-практику.

## Виды Обращений

| Вид | Покрыт | Пример | Текущий статус |
|---|---|---|---|
| Config/profile | Да | `alterios_config`, `alterios_list_profiles` | Реализовано, без network write. |
| Instance/project inventory | Да | `GET /api/projects/listandcount` | Live read-only. |
| Project object inventory | Да | `listandcount` для content types, forms, views и т.д. | Live read-only, 15 probes. |
| Detail reads | Да | `GET /api/forms/{formId}` | Реализовано typed tools. |
| Populated/config reads | Да | `GET /api/view-fields/populated/{viewId}` | Live verified in sandbox chain. |
| Runtime data reads | Да | `POST /api/views/v2/get-data`, `get-data-simplified` | Live verified for sandbox view. |
| Metadata create/update | Да | content types, fields, forms, views, groups | Live sandbox write. |
| Content create/update | Да | `POST /api/contents/save`, `PATCH /api/contents/save` | Create and update live verified in sandbox; update used for file-field value. |
| Script execution/services | Да | `POST /api/scripts`, `POST /api/scripts/execute-manual`, 14 service names | Saved manual script UUID created and executed in sandbox; runtime service names remain cataloged separately. |
| Workflow/process/task | Да | `POST /api/diagrams`, `POST /api/processes`, `GET /api/tasks/`, `DELETE /api/tasks/complete` | Dedicated sandbox BPMN created; process started; user task completed; process readback completed. |
| Files | Да | `POST /api/file/upload/field`, `GET /api/file/list` | File-field created; multipart upload executed; content value patched; file metadata readback verified. |
| Comments/logs/audit | Частично | `GET/POST /api/v1/comments`, `writeLog` | Comment read/write and `comments_list` UI live verified; `writeLog` remains cataloged as runtime service. |
| Users/groups/security | Частично | users, user groups, groups, roles | Groups live write; users/roles deferred as security workflow. |
| Reports/dashboards | Да | report full/read/save | Dashboard report created/updated in sandbox with Stimulsoft template and full readback. |

## MCP Tools: 25

| Tool | Вид |
|---|---|
| `alterios_config` | Config/profile |
| `alterios_list_profiles` | Config/profile |
| `alterios_list_projects` | Instance inventory |
| `alterios_service_catalog` | Runtime service catalog |
| `alterios_call_readonly_service` | Runtime read service |
| `alterios_rest_get` | Generic REST read |
| `alterios_list_objects` | Object inventory |
| `alterios_view_data_simplified` | Runtime data read |
| `alterios_report_full` | Report read |
| `alterios_get_view` | View detail read |
| `alterios_get_form` | Form detail read |
| `alterios_view_entities` | View config read |
| `alterios_view_fields_populated` | View field config read |
| `alterios_list_fields` | Field metadata read |
| `alterios_list_groups` | Group metadata read |
| `alterios_file_metadata` | File metadata read |
| `alterios_list_comments` | Comment read |
| `alterios_add_comment` | Controlled comment write |
| `alterios_update_content_fields` | Controlled typed content field update |
| `alterios_file_upload_to_field` | Controlled typed file-field upload and content save |
| `alterios_view_data` | Runtime data read |
| `alterios_discover_readonly` | Live route matrix |
| `alterios_call_write_service` | Controlled runtime write/service call |
| `alterios_execute_manual_script` | Controlled manual script execution |
| `alterios_rest_write` | Controlled generic REST write |

## 2026-07-10 Reinventory Note

The 2026-07-10 reinventory initially found 23 MCP tools and only 4 write-like
tools. The first typed-write expansion added `alterios_update_content_fields`
and `alterios_file_upload_to_field`, bringing the surface to 25 tools and 6
write-like tools.

Live ART X practice proves that Alterios accepts write routes for content,
files, views, forms, scripts, BPMN/process/tasks, comments, and reports. That
does **not** mean the MCP operator surface is complete. Today 6 tools are
write-like, and 3 of them are still either generic or narrow:

- `alterios_add_comment` is typed but only covers comments;
- `alterios_update_content_fields` and `alterios_file_upload_to_field` now cover
  the first typed content/file slice;
- `alterios_execute_manual_script` executes an existing script UUID but does not
  create or update scripts;
- `alterios_call_write_service` and `alterios_rest_write` are broad escape
  hatches, not production-grade entity tools.

Next coverage work must therefore add typed write tools for the verified
project-base surfaces:

1. content fields and file-field upload;
2. views, view entities, and view fields;
3. forms, tabs, components, and actions;
4. manual/event/diagram scripts;
5. BPMN diagrams, process start, task reads, task completion;
6. reports with Stimulsoft Project Database datasource validation.

## Runtime Services: 14

| Risk | Count | Services |
|---|---:|---|
| `read` | 4 | `getContents`, `getDependentContents`, `getTasks`, `getViewData` |
| `write` | 4 | `createContent`, `updateContent`, `createDependentContent`, `uploadFile` |
| `destructive` | 1 | `deleteManyContents` |
| `workflow_side_effect` | 3 | `startProcess`, `reassignTask`, `messageToAnotherProcess` |
| `external_side_effect` | 1 | `notify` |
| `audit_side_effect` | 1 | `writeLog` |

Runtime service names are not manual script UUIDs. If the configured endpoint is
`/api/scripts/execute-manual`, only saved script UUIDs can be executed there.

## REST Route/Method Registry: 57

Statuses:

- `live_read` - live read verified through API.
- `live_write` - write executed in ART X sandbox and read back.
- `live_ui` - browser-visible behavior verified.
- `cataloged` - known from code/docs/static scan, not yet exercised in the
  current sandbox.
- `needs_har` - needs browser/HAR capture before typed write.
- `deferred` - intentionally postponed because of destructive/security risk.

| # | Method | Route pattern | Вид | Status |
|---:|---|---|---|---|
| 1 | GET | `/api/projects/listandcount` | Project inventory | `live_read` |
| 2 | GET | `/api/content-types/listandcount` | Content type inventory | `live_read` |
| 3 | GET | `/api/fields` | Field metadata read | `live_read` |
| 4 | GET | `/api/views/listandcount` | View inventory | `live_read` |
| 5 | GET | `/api/forms/listandcount` | Form inventory | `live_read` |
| 6 | GET | `/api/scripts/listandcount` | Script inventory | `live_read` |
| 7 | GET | `/api/diagrams/listandcount` | Diagram inventory | `live_read` |
| 8 | GET | `/api/contents/listandcount` | Content inventory/read | `live_read` |
| 9 | GET | `/api/tasks/listandcount` | Task read | `live_read` |
| 10 | GET | `/api/processes/listandcount` | Process read | `live_read` |
| 11 | GET | `/api/reports/listandcount/{filter}` | Report inventory | `live_read` |
| 12 | GET | `/api/user-groups/listandcount` | User-group read | `live_read` |
| 13 | GET | `/api/users/listandcount` | User read | `live_read` |
| 14 | GET | `/api/groups` | Group read | `live_read` |
| 15 | GET | `/api/helps` | Help read | `live_read` |
| 16 | GET | `/api/reports/full/{filter}` | Report detail read | `live_read` |
| 17 | GET | `/api/views/{viewId}` | View detail read | `cataloged` |
| 18 | GET | `/api/forms/{formId}` | Form detail read | `cataloged` |
| 19 | GET | `/api/view-entities/by-view/{viewId}` | View entity read | `live_read` |
| 20 | GET | `/api/view-fields/populated/{viewId}` | View field read | `live_read` |
| 21 | GET | `/api/file/list?id=...` | File metadata read | `live_read` |
| 22 | GET | `/api/v1/comments` | Comment read | `live_read` |
| 23 | POST | `/api/v1/comments` | Comment write | `live_write`, `live_ui` |
| 24 | POST | `/api/views/v2/get-data-simplified` | Runtime data read | `live_read`, `live_ui` |
| 25 | POST | `/api/views/v2/get-data` | Runtime data read | `cataloged` |
| 26 | POST | `/api/helps` | Help create/write | `live_write`, `live_ui` |
| 27 | PATCH | `/api/helps/{helpId}` | Help update variant | `cataloged` |
| 28 | PUT | `/api/helps/{helpId}` | Help update variant | `cataloged` |
| 29 | POST | `/api/content-types/save` | Content type save | `live_write` |
| 30 | POST | `/api/fields/save` | Field save | `live_write`, `live_ui` |
| 31 | POST | `/api/views` | View create | `live_write`, `live_ui` |
| 32 | PATCH | `/api/views/{viewId}` | View update variant | `cataloged` |
| 33 | PUT | `/api/views` | View update variant | `cataloged` |
| 34 | POST | `/api/view-entities` | View entity create | `live_write`, `live_ui` |
| 35 | PATCH | `/api/view-entities/{entityId}` | View entity update variant | `cataloged` |
| 36 | PUT | `/api/view-entities` | View entity update variant | `cataloged` |
| 37 | POST | `/api/view-entities/add-one-field` | View field attach | `live_write`, `live_ui` |
| 38 | POST | `/api/view-fields/save` | View field save | `live_write`, `live_ui` |
| 39 | POST | `/api/forms` | Form create | `live_write`, `live_ui` |
| 40 | PATCH | `/api/forms/{formId}` | Form update variant | `cataloged` |
| 41 | PUT | `/api/forms` | Form update variant | `cataloged` |
| 42 | POST | `/api/groups` | Menu group create | `live_write`, `live_ui` |
| 43 | PATCH | `/api/groups/{groupId}` | Menu group update variant | `cataloged` |
| 44 | PUT | `/api/groups` | Menu group update variant | `cataloged` |
| 45 | POST | `/api/contents/save` | Content create | `live_write`, `live_ui` |
| 46 | PATCH | `/api/contents/save` | Content update | `live_write` |
| 47 | POST | `/api/scripts` | Script create | `live_write` |
| 48 | PUT | `/api/scripts` | Script update | `cataloged` |
| 49 | POST | `/api/scripts/execute-manual` | Manual script execution | `live_write` |
| 50 | PUT | `/api/reports` | Report save | `live_write` |
| 51 | POST | `/api/file/upload/field` | File upload | `live_write` |
| 52 | POST | `/api/reports` | Report create | `live_write` |
| 53 | POST | `/api/diagrams` | BPMN diagram create | `live_write` |
| 54 | PUT | `/api/diagrams` | BPMN diagram update variant | `cataloged` |
| 55 | POST | `/api/processes` | Process start | `live_write` |
| 56 | GET | `/api/tasks/` | Active task read | `live_read` |
| 57 | DELETE | `/api/tasks/complete` | Task transition/complete | `live_write` |

## What Counts As "All Types"

We treat coverage as complete by **operation class**, not by pretending to know
every internal route in advance. A class is considered covered only when it has:

- at least one known route or service name;
- risk classification;
- request target context: profile + explicit `project_id` when project-scoped;
- dry-run/write-gate rule for mutating calls;
- readback route;
- UI verification rule when the result is user-facing.

By that definition, all main operation classes are represented. The not-yet
closed areas are:

- users/roles/security writes;
- destructive delete flows.

These are deliberately not marked complete until each has a sandbox scenario,
HAR/API evidence, execution gate, and readback/UI verification.
