# План discovery для Alterios MCP

Discovery должен давать переиспользуемую production inventory экземпляра
Alterios, а не одноразовый MVP-probe. Каждый запуск отделяет подтвержденное
runtime behavior от предположений, соблюдает secret hygiene и записывает точный
profile/project context.

## Модель scope

- `profile` - один экземпляр Alterios: base URL, auth, script endpoint, body
  style и timeout settings.
- Один экземпляр может содержать много проектов.
- `project_id` - контекст вызова. Project-scoped tools принимают явный
  `project_id` и используют `ALTERIOS_<PROFILE>_PROJECT_ID` только как
  optional default.
- Несколько экземпляров настраиваются как несколько profiles в одном приватном
  dotenv. Используйте `ALTERIOS_PROFILES` или auto-discovery переменных
  `ALTERIOS_<PROFILE>_*`.
- Profile inventory читается локально через `alterios_list_profiles` или
  `python -m alterios_mcp.discovery --profiles --json`; это не должно делать
  network calls и не должно показывать API tokens.
- `--profiles --profile <name>` и `alterios_list_profiles(profile=...)`
  только помечают выбранный profile в output, но не переписывают dotenv.
- Instance-scoped discovery, особенно project listing, должно работать без
  project id.
- Secrets загружаются из environment variables или `ALTERIOS_DOTENV_PATH`; они
  не копируются в репозиторий и discovery artifacts.

## Этапы discovery

1. Foundation and safety:
   - проверить выбранный profile через `alterios_config`;
   - проверить доступные instance profiles через `alterios_list_profiles`;
   - проверить redaction auth headers, tokens, passwords и API keys;
   - проверить diagnostics для отсутствующих instance/project/script values;
   - подтвердить, что явный `project_id` перекрывает optional env default.
2. Complete read-only inventory:
   - сначала получить список projects на уровне instance;
   - для каждого target project собрать content types, fields, views, forms,
     scripts, diagrams, contents, tasks, processes, reports и view data smoke;
   - записать pagination, filter shape, response shape, status code и error
     shape для каждого route;
   - сохранить JSON artifacts без secrets.
3. Static source inventory:
   - запустить `python -m alterios_mcp.static_scan <repo> --json`;
   - по умолчанию пропускать generated/bulky directories: `artifacts`, `data`,
     `outputs`, `site`, `work`;
   - `--include-generated` использовать только для намеренного full scan.
4. Script runtime catalog:
   - каталогизировать script-service functions по category, arguments,
     permissions и mutation risk;
   - сначала probe read-only services;
   - записать body style, endpoint template behavior и response shapes по
     instance;
   - держать `/api/scripts/execute-manual` отдельно от runtime service names:
     execute-manual требует saved script UUID;
   - mutating functions держать disabled до controlled-write gates.
5. Controlled writes:
   - требовать `ALTERIOS_MCP_ALLOW_WRITE=1`;
   - требовать verified profile и явный `project_id`;
   - добавлять narrow typed write tools до broad generic writes;
   - писать request/response audit с redaction;
   - предпочитать idempotent helpers, dry-run validation и test projects.
6. Browser/UI discovery:
   - снимать реальные UI network flows для lists, forms, tasks, reports,
     dashboards, files и process actions;
   - маппить UI actions на REST routes или script-service calls;
   - сравнивать UI-visible behavior с API readbacks.
7. Release packaging:
   - публиковать MCP config examples, private dotenv guidance, smoke-check
     commands, compatibility notes и versioned release artifacts.

## Текущий read-only REST route catalog

| Name | Scope | Method | Path | Tool |
|---|---|---|---|---|
| projects | instance | GET | `/api/projects/listandcount` | `alterios_list_projects`, `alterios_discover_readonly` |
| content_types | project | GET | `/api/content-types/listandcount` | `alterios_list_objects` |
| fields | project | GET | `/api/fields` | `alterios_list_fields`, `alterios_discover_readonly` |
| views | project | GET | `/api/views/listandcount` | `alterios_list_objects` |
| forms | project | GET | `/api/forms/listandcount` | `alterios_list_objects` |
| scripts | project | GET | `/api/scripts/listandcount` | `alterios_list_objects` |
| diagrams | project | GET | `/api/diagrams/listandcount` | `alterios_list_objects` |
| contents | project | GET | `/api/contents/listandcount` | `alterios_list_objects` |
| tasks | project | GET | `/api/tasks/listandcount` | `alterios_list_objects` |
| processes | project | GET | `/api/processes/listandcount` | `alterios_discover_readonly` |
| reports | project | GET | `/api/reports/listandcount/{encoded_filter}` | `alterios_list_objects` |
| user_groups | project | GET | `/api/user-groups/listandcount` | `alterios_list_objects` |
| users | project | GET | `/api/users/listandcount` | `alterios_list_objects` |
| groups | project | GET | `/api/groups` | `alterios_list_groups`, `alterios_list_objects` |
| helps | project | GET | `/api/helps` | `alterios_list_objects` |
| view_data_simplified | project | POST | `/api/views/v2/get-data-simplified` | `alterios_view_data_simplified` |

## Typed read-only inventory tools

Эти tools используют подтвержденные Alterios REST patterns, но требуют
caller-provided IDs, поэтому не входят в route matrix probe:

- `alterios_report_full` - `GET /api/reports/full/{encode_filter({"_id": id})}`;
- `alterios_get_view` - `GET /api/views/{view_id}`;
- `alterios_get_form` - `GET /api/forms/{form_id}`;
- `alterios_view_entities` - `GET /api/view-entities/by-view/{view_id}`;
- `alterios_view_fields_populated` - `GET /api/view-fields/populated/{view_id}`;
- `alterios_file_metadata` - `GET /api/file/list?id=...`;
- `alterios_list_comments` - `GET /api/v1/comments` с `entity`,
  `entityId`, `limit`, `depth` и `page`;
- `alterios_view_data` - `POST /api/views/v2/get-data` с optional
  `contentId`, array `dataId` и `userFilters`.

## Текущий script-service catalog

Source of truth - `src/alterios_mcp/services.py`; operator-facing catalog
описан в [script-runtime-catalog.md](script-runtime-catalog.md).

Read-only и safe-to-probe через compatible runtime endpoint:

- `getContents`;
- `getDependentContents`;
- `getTasks`;
- `getViewData`.

Mutating и disabled без `ALTERIOS_MCP_ALLOW_WRITE=1`:

- `createContent` - `write`;
- `updateContent` - `write`;
- `deleteManyContents` - `destructive`;
- `createDependentContent` - `write`;
- `startProcess` - `workflow_side_effect`;
- `reassignTask` - `workflow_side_effect`;
- `messageToAnotherProcess` - `workflow_side_effect`;
- `uploadFile` - `write`;
- `notify` - `external_side_effect`;
- `writeLog` - `audit_side_effect`.

Manual script execution:

- `/api/scripts/execute-manual` требует script UUID и доступен только как
  write-gated operation.
- Runtime service names вроде `getTasks` не являются script UUID и
  отклоняются, если endpoint template указывает на `/api/scripts/execute-manual`.

## Правила безопасности

- Перед каждым write-capable tool вызывать `alterios_config`.
- Передавать явный `project_id` для project-scoped operations, когда он известен
  из UI, URL, ticket или operator request.
- Считать `ALTERIOS_<PROFILE>_PROJECT_ID` только optional default.
- Write mode включается process-wide и требует `ALTERIOS_MCP_ALLOW_WRITE=1`.
- Tool responses скрывают known secret-bearing keys.
- Hidden или undocumented endpoints не brute-force.
- Discovery artifacts не должны содержать tokens, cookies, passwords или full
  auth headers.
