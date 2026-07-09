# Alterios MCP Discovery Plan

Discovery must produce a reusable production inventory of an Alterios instance,
not a one-off MVP probe. Each run separates confirmed runtime behavior from
assumptions, preserves secret hygiene, and records the exact profile and
project context used.

## Scope Model

- `profile` means one Alterios instance: base URL, auth, script endpoint, body
  style, and timeout settings.
- An instance can contain many projects.
- `project_id` is call context. Project-scoped tools accept explicit
  `project_id` and use `ALTERIOS_<PROFILE>_PROJECT_ID` only as an optional
  default.
- Instance-scoped discovery, especially project listing, must work without a
  project id.
- Secrets are loaded from environment variables or `ALTERIOS_DOTENV_PATH`; they
  are not copied into this repository or discovery artifacts.

## Discovery Stages

1. Foundation and safety:
   - Confirm selected profile with `alterios_config`.
   - Verify redaction of auth headers, tokens, passwords, and API keys.
   - Verify missing-value diagnostics for instance, project, and script calls.
   - Confirm explicit `project_id` overrides the optional env default.
2. Complete read-only inventory:
   - List projects at the instance level.
   - For each target project, inventory content types, fields, views, forms,
     scripts, diagrams, contents, tasks, processes, reports, and view data
     smoke checks.
   - Capture pagination, filter shape, response shape, status code, and error
     shape for every route.
   - Save JSON artifacts without secrets.
3. Static source inventory:
   - Run `python -m alterios_mcp.static_scan <repo> --json`.
   - By default, skip generated/bulky directories such as `artifacts`, `data`,
     `outputs`, `site`, and `work`.
   - Use `--include-generated` only for an intentional full scan.
4. Script runtime catalog:
   - Catalog script-service functions by category, arguments, permissions, and
     mutation risk.
   - Probe read-only services first.
   - Record required body style, endpoint template behavior, and response
     shapes per instance.
   - Keep `/api/scripts/execute-manual` separate from runtime service names:
     execute-manual requires a saved script UUID.
   - Keep mutating functions disabled until controlled-write gates exist.
5. Controlled writes:
   - Require `ALTERIOS_MCP_ALLOW_WRITE=1`.
   - Require verified profile and explicit `project_id`.
   - Add narrow, typed write tools before broad generic writes.
   - Record request/response audit data with secrets redacted.
   - Prefer idempotent helpers, dry-run validation, and test projects.
6. Browser/UI discovery:
   - Capture real UI network flows for lists, forms, tasks, reports,
     dashboards, files, and process actions.
   - Map UI actions to REST routes or script-service calls.
   - Compare UI-visible behavior with API readbacks.
7. Release packaging:
   - Publish MCP configuration examples, private dotenv guidance, smoke-check
     commands, compatibility notes, and versioned release artifacts.

## Current Read-Only REST Route Catalog

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

## Typed Read-Only Inventory Tools

These tools use confirmed Alterios REST patterns but require caller-provided
IDs, so they are not part of the route matrix probe:

- `alterios_report_full` - `GET /api/reports/full/{encode_filter({"_id": id})}`.
- `alterios_get_view` - `GET /api/views/{view_id}`.
- `alterios_get_form` - `GET /api/forms/{form_id}`.
- `alterios_view_entities` - `GET /api/view-entities/by-view/{view_id}`.
- `alterios_view_fields_populated` - `GET /api/view-fields/populated/{view_id}`.
- `alterios_file_metadata` - `GET /api/file/list?id=...`.
- `alterios_list_comments` - `GET /api/v1/comments` with `entity`,
  `entityId`, `limit`, `depth`, and `page`.
- `alterios_view_data` - `POST /api/views/v2/get-data` with optional
  `contentId`, array `dataId`, and `userFilters`.

## Current Script-Service Catalog

Read-only:

- `getContents`
- `getDependentContents`
- `getTasks`
- `getViewData`

Mutating, disabled unless `ALTERIOS_MCP_ALLOW_WRITE=1`:

- `createContent`
- `updateContent`
- `deleteManyContents`
- `createDependentContent`
- `startProcess`
- `reassignTask`
- `messageToAnotherProcess`
- `uploadFile`
- `notify`
- `writeLog`

Manual script execution:

- `/api/scripts/execute-manual` requires a script UUID and is exposed only as a
  write-gated operation.

## Safety Rules

- Always call `alterios_config` before any write-capable tool.
- Pass explicit `project_id` for project-scoped operations whenever it is known
  from the UI, URL, ticket, or operator request.
- Treat `ALTERIOS_<PROFILE>_PROJECT_ID` as an optional default only.
- Write mode is process-wide and must be explicitly enabled with
  `ALTERIOS_MCP_ALLOW_WRITE=1`.
- Tool responses redact known secret-bearing keys.
- Hidden or undocumented endpoints are not brute-forced.
- Discovery artifacts must not include tokens, cookies, passwords, or full auth
  headers.
