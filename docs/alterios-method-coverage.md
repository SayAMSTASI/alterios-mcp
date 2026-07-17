# Покрытие методов и видов обращений Alterios

Документ отвечает на два вопроса:

1. сколько методов и маршрутов сейчас явно учитывает `alterios-mcp`;
2. какие виды обращений покрыты, а какие еще требуют live/HAR-подтверждения.

Матрица описывает переиспользуемую поверхность MCP. Project-specific counts,
profiles, identifiers and live evidence are intentionally excluded.

## Сводка По Количеству

| Уровень | Количество | Что считается |
|---|---:|---|
| MCP tools | 109 | Полный callable registry собран доменными модулями `src/alterios_mcp/tools/`; профиль `live` публикует 82 tools. |
| Write-like MCP tools | 44 | Сценарные, typed, security, dangerous и raw-write инструменты по классификации `tool_profiles.py`; в число сценарных входят `alterios_fast_live_write`, `alterios_fast_live_bulk_manual_script`, `alterios_fast_live_bulk_process` и admin-only `alterios_fast_live_bulk_delete`. |
| Runtime service methods | 14 | Известные script-service имена в `src/alterios_mcp/services.py`. |
| Live read-only REST probes | 15 | Маршруты в `READONLY_ROUTES`, проверяемые discovery matrix. |
| REST route/method patterns in coverage registry | 78 | Read/detail/runtime/write/workflow/file/comment/report/security/content-transfer patterns ниже. |
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
| Users/groups/security | Частично | users, user groups, groups, roles | Sandbox create/update/delete and cleanup are verified; production security writes remain dangerous-gated. |
| Reports/dashboards | Да | report full/read/save | Dashboard report created/updated in sandbox with Stimulsoft template and full readback. |

## MCP Tools: 107

| Tool | Вид |
|---|---|
| `alterios_config` | Config/profile |
| `alterios_list_profiles` | Config/profile |
| `alterios_list_write_plans` | Stored dry-run write plan read |
| `alterios_get_write_plan` | Stored dry-run write plan detail read |
| `alterios_write_journal` | Write plan/execution journal read |
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
| `alterios_list_content_types` | Content type metadata read |
| `alterios_list_users` | Security user read |
| `alterios_get_user` | Security user detail read |
| `alterios_list_user_groups` | Security user-group read |
| `alterios_get_user_group` | Security user-group detail read |
| `alterios_list_roles` | Security role read |
| `alterios_get_role` | Security role detail read |
| `alterios_file_metadata` | File metadata read |
| `alterios_upsert_user` | Controlled typed security user create/update |
| `alterios_upsert_user_group` | Controlled typed security user-group create/update |
| `alterios_upsert_role` | Controlled typed security role create/update |
| `alterios_delete_user` | Controlled typed security user delete |
| `alterios_delete_user_group` | Controlled typed security user-group delete |
| `alterios_delete_role` | Controlled typed security role delete |
| `alterios_list_comments` | Comment read |
| `alterios_add_comment` | Controlled comment write |
| `alterios_upsert_content_type` | Controlled typed content type create/update |
| `alterios_plan_content_type_publish` | Content type publish/transfer planner and safety review with route evidence fields |
| `alterios_clone_shared_content_type` | Controlled native clone of a shared content type into an explicit target project |
| `alterios_upsert_field` | Controlled typed field create/update |
| `alterios_create_content` | Controlled typed content create |
| `alterios_upsert_group` | Controlled typed menu group create/update |
| `alterios_upsert_help` | Controlled typed help create/update |
| `alterios_update_content_fields` | Controlled typed content field update |
| `alterios_bulk_update_selected_content_fields` | Controlled typed bulk update for selected content rows |
| `alterios_file_upload_to_field` | Controlled typed file-field upload and content save |
| `alterios_upsert_view` | Controlled typed view create/update |
| `alterios_upsert_view_entity` | Controlled typed view entity create/update |
| `alterios_upsert_view_field` | Controlled typed view field attach/update |
| `alterios_upsert_form` | Controlled typed form create/update |
| `alterios_create_material_module` | Controlled scenario tool for content type, fields, view, add/edit/list forms, and menu group |
| `alterios_patch_form_actions` | Controlled typed form actions patch |
| `alterios_patch_form_tabs` | Controlled typed form tabs patch |
| `alterios_patch_form_cell_listeners` | Controlled typed form cell listener patch |
| `alterios_upsert_form_manual_script_action` | Controlled typed manual script action upsert for page, element, or row value with verified identifier bindings |
| `alterios_analyze_form_surface` | Form UX/layout/action validation read |
| `alterios_upsert_script` | Controlled typed script create/update |
| `alterios_validate_script` | Script validation read |
| `alterios_upsert_bpmn_diagram` | Controlled typed BPMN diagram create/update |
| `alterios_list_process_tasks` | Process/task read |
| `alterios_start_process` | Controlled workflow process start |
| `alterios_complete_task` | Controlled workflow task completion |
| `alterios_validate_process_result` | Process result validation read |
| `alterios_create_process_flow` | Controlled scenario tool for task form, script refs, BPMN formKey, and optional process smoke |
| `alterios_upsert_report` | Controlled typed report create/update |
| `alterios_patch_report_template` | Controlled report template patch |
| `alterios_validate_report_project_base` | Report Project Database validation read |
| `alterios_validate_stimulsoft_layout` | Stimulsoft report layout validation read |
| `alterios_create_report_tab` | Controlled scenario tool for Project Database report plus openId form tab and dataId context check |
| `alterios_validate_form_contract` | Strict blocking validation alias for the active form UX contract |
| `alterios_validate_module_contract` | Bounded validation of content type, fields, v2 view/joins, four form roles, icons, bulk and reports |
| `alterios_fast_live_write` | Two-phase fast workflow: live preflight plus scenario plan/apply |
| `alterios_fast_live_bulk_manual_script` | Fast cached-health plan/apply workflow for one manual script over selected content IDs |
| `alterios_fast_live_bulk_process` | Fast cached-health plan/apply workflow for one BPMN process over selected content IDs |
| `alterios_fast_live_bulk_delete` | Admin-only destructive bulk delete with exact target plan, dangerous gates and absence readback |
| `alterios_view_data` | Runtime data read |
| `alterios_discover_readonly` | Live route matrix |
| `alterios_profile_smoke_matrix` | Profile/project read-only smoke matrix |
| `alterios_replay_smoke` | Local/read-only MCP replay smoke after updates |
| `alterios_project_health` | Read-only TTL-cached project health with persisted diff before writes |
| `alterios_live_task_preflight` | Fast read-only go/no-go preflight before live write tasks |
| `alterios_tool_profile` | Active `full/live/discovery/admin` registry profile and removed-tool summary |
| `alterios_verify_delivery_evidence` | Read-only private Gitea issue and structured agent handoff verification |
| `alterios_write_safety_preflight` | Write safety classification read |
| `alterios_call_write_service` | Controlled runtime write/service call |
| `alterios_execute_manual_script` | Controlled manual script execution |
| `alterios_rest_write` | Controlled generic REST write |
| `alterios_runtime_info` | Runtime fingerprint, package version, schema version, process and launch diagnostics |
| `alterios_ux_contract` | Active UX contract metadata and blocking validation rules |
| `gitea_workboard_config` | Private Gitea workboard configuration summary without secrets |
| `gitea_workboard_probe` | Gitea repository, issue and project-board connectivity probe |
| `local_workboard_config` | Local fallback workboard configuration summary |
| `local_workboard_init` | Local fallback workboard initialization |
| `local_workboard_create_item` | Local fallback work item creation |
| `local_workboard_list_items` | Local fallback work item list |
| `local_workboard_add_agent_report` | Structured agent report in the local fallback workboard |
| `gitea_list_work_items` | Private Gitea issue list used as the durable work status source |
| `gitea_sync_standard_labels` | Synchronize standard role, stage and priority labels |
| `gitea_create_work_item` | Create a private Gitea work item with acceptance criteria and stage |
| `gitea_create_sprint` | Create a milestone-backed Gitea sprint |
| `gitea_list_sprint_tasks` | List work items assigned to a Gitea sprint |
| `gitea_add_agent_report` | Add a structured agent handoff report to a Gitea issue |
| `gitea_sync_board_by_labels` | Synchronize Gitea project-board columns from durable `stage:*` labels |
| `gitea_transition_issue_stage` | Move an issue to another stage and synchronize its board card |
| `alterios_list_project_icons` | Inventory project-local icons before form action configuration |
| `alterios_resolve_project_icon` | Resolve a semantic icon name to a project-local file UUID |
| `alterios_export_project_icons` | Export reusable project icons with a manifest |
| `alterios_ensure_project_icons` | Upload missing reusable icons into the target project |
| `alterios_ensure_project_icon_library` | Ensure the standard reusable icon set is present in a project |
| `alterios_validate_printable_render` | Validate printable report render output as PDF or image evidence |

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

## REST Route/Method Registry: 78

Statuses:

- `live_read` - live read verified through API.
- `live_write` - write executed in an approved private sandbox and read back.
- `live_ui` - browser-visible behavior verified.
- `cataloged` - known from code/docs/static scan, not yet exercised in the
  approved private sandbox.
- `needs_har` - needs browser/HAR capture before typed write.
- `typed_guarded` - has a typed tool, dry-run audit, gates, and no-network tests;
  live execution remains sandbox-only until evidence is collected.
- `needs_sandbox_execution` - execution is intentionally not marked live until a
  controlled sandbox run and readback/UI proof exist.
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
| 58 | GET | `/api/roles/listandcount` | Role read | `live_read` |
| 59 | POST | `/api/users` | User create | `typed_guarded`, `blocked_backend_key_error`, `needs_ui_har` |
| 60 | PATCH | `/api/users/{userId}` | User update variant | `typed_guarded`, `needs_disposable_user` |
| 61 | PUT | `/api/users/{userId}` | User update fallback variant | `typed_guarded`, `needs_disposable_user` |
| 62 | PUT | `/api/users` | User update fallback variant | `typed_guarded`, `needs_disposable_user` |
| 63 | DELETE | `/api/users/{userId}` | User delete | `typed_guarded`, `needs_disposable_user` |
| 64 | DELETE | `/api/users` | User delete fallback variant | `typed_guarded`, `needs_disposable_user` |
| 65 | POST | `/api/user-groups` | User group create | `typed_guarded`, `live_write` |
| 66 | PATCH | `/api/user-groups/{userGroupId}` | User group update variant | `typed_guarded`, `live_write` |
| 67 | PUT | `/api/user-groups/{userGroupId}` | User group update fallback variant | `typed_guarded`, `fallback_not_executed` |
| 68 | PUT | `/api/user-groups` | User group update fallback variant | `typed_guarded`, `fallback_not_executed` |
| 69 | DELETE | `/api/user-groups/{userGroupId}` | User group delete | `typed_guarded`, `live_write` |
| 70 | DELETE | `/api/user-groups` | User group delete fallback variant | `typed_guarded`, `fallback_not_executed` |
| 71 | POST | `/api/roles` | Role create | `typed_guarded`, `live_write` |
| 72 | PATCH | `/api/roles/{roleId}` | Role update variant | `typed_guarded`, `live_write` |
| 73 | PUT | `/api/roles/{roleId}` | Role update fallback variant | `typed_guarded`, `fallback_not_executed` |
| 74 | PUT | `/api/roles` | Role update fallback variant | `typed_guarded`, `fallback_not_executed` |
| 75 | DELETE | `/api/roles/{roleId}` | Role delete | `typed_guarded`, `live_write` |
| 76 | DELETE | `/api/roles` | Role delete fallback variant | `typed_guarded`, `fallback_not_executed` |
| 77 | GET | `/api/content-types?share=true` | Shared content type visibility from target project | `live_read`, `route_evidence` |
| 78 | POST | `/api/content-types/clone` | Native shared content type clone into target project | `typed_guarded`, `needs_sandbox_execution` |

## Что считается всеми видами обращений

Покрытие считается закрытым по **классу операции**, а не по предположению, что
заранее известен каждый внутренний route. Класс считается покрытым только если
есть:

- at least one known route or service name;
- risk classification;
- request target context: profile + explicit `project_id` when project-scoped;
- dry-run/write-gate rule for mutating calls;
- readback route;
- UI verification rule when the result is user-facing.

По этому определению все основные классы операций представлены. Еще не закрыты:

- raw HAR export for disposable user creation/deletion if raw network artifacts
  are required beyond UI/API evidence;
- live native cross-project content-type clone in a dedicated target sandbox
  with cleanup/readback;
- rendered Stimulsoft proof for report layouts where visual acceptance matters.

Эти пункты намеренно не считаются завершенными, пока для каждого нет
sandbox-сценария, HAR/API evidence, execution gate и readback/UI verification.
