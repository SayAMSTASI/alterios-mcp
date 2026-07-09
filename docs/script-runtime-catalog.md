# Script Runtime Catalog

Stage 3 turns script-service names into an explicit runtime catalog. The goal is
to make every service visible by purpose, arguments, risk, and probe safety
before any write-capable wrapper is added.

## Runtime Services Vs Manual Scripts

Runtime service names such as `getTasks` and `createContent` are not script
UUIDs. They must not be sent to `/api/scripts/execute-manual`.

`/api/scripts/execute-manual` executes saved Alterios scripts by UUID. The MCP
client rejects non-UUID runtime service names when the configured endpoint is
`/api/scripts/execute-manual`.

## Risk Levels

| Risk Level | Meaning |
|---|---|
| `read` | Read-only when called through a compatible runtime endpoint. |
| `write` | Creates or updates Alterios data. Requires write gate and readback verification. |
| `destructive` | Deletes data. Requires a separate dry-run and explicit target review before any typed tool is added. |
| `workflow_side_effect` | Starts, advances, or reassigns workflow activity. Requires UI/API verification. |
| `external_side_effect` | Sends user-visible notifications or other external effects. |
| `audit_side_effect` | Writes operational logs or other audit-like state. |

## Confirmed Catalog

| Service | Category | Mutates | Risk | Safe To Probe | Key Args |
|---|---|---:|---|---:|---|
| `getContents` | contents | No | `read` | Yes | `query` |
| `getDependentContents` | contents | No | `read` | Yes | `query` |
| `getTasks` | tasks | No | `read` | Yes | `query` |
| `getViewData` | views | No | `read` | Yes | `query` |
| `createContent` | contents | Yes | `write` | No | `content` |
| `updateContent` | contents | Yes | `write` | No | `content` |
| `deleteManyContents` | contents | Yes | `destructive` | No | `args` |
| `createDependentContent` | contents | Yes | `write` | No | `content`, `relatedContentId`, `relatedFieldId` |
| `startProcess` | processes | Yes | `workflow_side_effect` | No | `diagramId`, `name`, `content`, `startMessageId`, `responseMessageId`, `params`, `contents` |
| `reassignTask` | tasks | Yes | `workflow_side_effect` | No | `query` |
| `messageToAnotherProcess` | processes | Yes | `workflow_side_effect` | No | `messageEventsIds`, `processesIds`, `diagramsIds`, `safeMode` |
| `uploadFile` | files | Yes | `write` | No | `data`, `filename`, `fieldId`, `signal` |
| `notify` | notifications | Yes | `external_side_effect` | No | `notification` |
| `writeLog` | logs | Yes | `audit_side_effect` | No | `data`, `severity` |

## Probe Policy

Read-only runtime services may be probed only when:

- `alterios_config` shows a compatible runtime endpoint template;
- the selected profile and explicit `project_id` are verified;
- the request body uses the documented body style for that endpoint;
- probe arguments are bounded by low limits and do not include writes.

When the endpoint template is `/api/scripts/execute-manual`, runtime service
probing is considered blocked by configuration, not failed API behavior.

## Static Scan Notes

`alterios-static-scan` detects known services and likely service-like strings.
Likely strings can include variable names such as `startPayload` or
`uploadResponse`; do not promote them into the catalog until they are confirmed
as real runtime services.

The catalog in `src/alterios_mcp/services.py` is the source of truth for known
runtime services exposed by `alterios_service_catalog`.
