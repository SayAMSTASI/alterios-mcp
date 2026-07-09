# alterios-mcp

Production-oriented MCP server and discovery toolkit for Alterios/LIMS
instances.

This repository is being shaped as a durable operational MCP, not a narrow MVP.
The core contract is:

- One MCP profile represents one Alterios instance: base URL, auth method,
  token, script endpoint template, and timeouts.
- An Alterios instance can contain many projects.
- Project-scoped tools accept an explicit `project_id`. The project id from
  environment configuration is only a convenience default, not the identity of
  the profile.
- Instance-scoped tools, such as project inventory, must not require a project
  id.
- Secrets are read from environment variables or a private dotenv file and are
  never copied into the repository or returned by tools.

## Current Tools

- `alterios_config` - redacted profile/config check with missing-value lists.
- `alterios_list_projects` - instance-scoped project inventory.
- `alterios_service_catalog` - known script-service catalog with read/write
  labels.
- `alterios_call_readonly_service` - guarded calls to known read-only script
  services such as `getTasks`, `getContents`, and `getViewData` when an
  external service endpoint is configured.
- `alterios_rest_get` - safe REST reads against `/api/...` routes.
- `alterios_list_objects` - common Alterios object inventory via validated
  `listandcount` routes.
- `alterios_view_data_simplified` - smoke reads for
  `/api/views/v2/get-data-simplified`.
- `alterios_report_full` - full report read through the encoded
  `/api/reports/full/{filter}` route.
- `alterios_get_view`, `alterios_view_entities`, and
  `alterios_view_fields_populated` - view object, join/entity, and populated
  field inventory.
- `alterios_get_form` - full form read by ID.
- `alterios_list_fields` - content type field inventory with optional
  `content_type_id` or `field_id` filters.
- `alterios_list_groups` - project group inventory via `/api/groups`.
- `alterios_file_metadata` - file metadata lookup via `/api/file/list`.
- `alterios_list_comments` - comment inventory via `/api/v1/comments`.
- `alterios_view_data` - `/api/views/v2/get-data` reads with optional
  `content_id`, array `data_id`, and `user_filters` context.
- `alterios_discover_readonly` - live read-only route matrix.
- `alterios_call_write_service` and `alterios_rest_write` - disabled unless
  `ALTERIOS_MCP_ALLOW_WRITE=1`.
- `alterios_execute_manual_script` - execute `/api/scripts/execute-manual` by
  script UUID; disabled unless `ALTERIOS_MCP_ALLOW_WRITE=1`.

Project-scoped tools should be called with `project_id` whenever the target
project is known from a URL, UI session, or task context. The configured
`ALTERIOS_<PROFILE>_PROJECT_ID` is only a fallback for repetitive work against a
known default project.

## Install

```powershell
git clone https://github.com/SayAMSTASI/alterios-mcp.git
cd alterios-mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

## Configure Alterios

Use a private `.env` locally; do not commit it.

```powershell
Copy-Item .env.example .env
```

Example profile for one Alterios instance:

```dotenv
ALTERIOS_PROFILE=vniimt

ALTERIOS_VNIIMT_BASE_URL=http://lims.vniimt.local
ALTERIOS_VNIIMT_API_TOKEN=put-token-here

# Optional default only. Prefer explicit project_id in project-scoped tools.
ALTERIOS_VNIIMT_PROJECT_ID=40466687-b093-4d80-b4f2-ba0ed0245bfa

ALTERIOS_VNIIMT_ENDPOINT_TEMPLATE={base_url}/api/scripts/execute-manual
ALTERIOS_VNIIMT_BODY_STYLE=manual_script
ALTERIOS_VNIIMT_AUTH_HEADER=x-api-key
ALTERIOS_VNIIMT_AUTH_SCHEME=
ALTERIOS_VNIIMT_TIMEOUT_SECONDS=20
```

`BASE_URL`, `API_TOKEN`, and transport settings are profile-isolated on purpose.
If a profile is selected, the server does not silently fall back to another
target instance.

To reuse an existing private config without copying secrets into this
repository, set `ALTERIOS_DOTENV_PATH` outside the repo:

```powershell
$env:ALTERIOS_DOTENV_PATH = "C:\Users\admin\Documents\AlteriosCodex\.env"
python -m alterios_mcp.discovery --profile vniimt --projects --json
```

Codex MCP config can pass the same private dotenv path:

```toml
[mcp_servers.alterios]
command = "C:\\path\\to\\alterios-mcp\\.venv\\Scripts\\python.exe"
args = ["-m", "alterios_mcp.server"]
startup_timeout_sec = 60
tool_timeout_sec = 120

[mcp_servers.alterios.env]
ALTERIOS_DOTENV_PATH = "C:\\Users\\admin\\Documents\\AlteriosCodex\\.env"
```

## Run Discovery

List projects on the selected Alterios instance:

```powershell
python -m alterios_mcp.discovery --profile vniimt --projects --json
```

Probe a specific project with an explicit project id:

```powershell
python -m alterios_mcp.discovery --profile vniimt `
  --project-id 40466687-b093-4d80-b4f2-ba0ed0245bfa `
  --json
```

Save a reproducible inventory artifact:

```powershell
New-Item -ItemType Directory -Force artifacts\alterios-mcp | Out-Null
python -m alterios_mcp.discovery --profile vniimt `
  --project-id 40466687-b093-4d80-b4f2-ba0ed0245bfa `
  --json > artifacts\alterios-mcp\live-readonly-matrix.json
```

Scan an existing Alterios automation repository for known API paths and script
service candidates:

```powershell
python -m alterios_mcp.static_scan C:\Users\admin\Documents\AlteriosCodex `
  --json > artifacts\alterios-mcp\static-calls.json
```

The static scanner skips generated and bulky working directories by default:
`artifacts`, `data`, `outputs`, `site`, and `work`. Use
`--include-generated` only when you intentionally need a full slow scan.

## Run MCP Server

```powershell
python -m alterios_mcp.server
```

Enable write mode only for a verified safe target profile and project:

```powershell
$env:ALTERIOS_MCP_ALLOW_WRITE = "1"
```

Before write-capable calls, run `alterios_config`, verify the selected profile,
and pass `project_id` explicitly. See [docs/roadmap.md](docs/roadmap.md) for
the staged production plan and [docs/discovery-plan.md](docs/discovery-plan.md)
for the inventory strategy.

Important: `/api/scripts/execute-manual` executes saved Alterios scripts by
UUID. It does not call runtime service names such as `getTasks` directly. Keep
runtime service names in the catalog until a compatible external service
endpoint is configured and verified.

## Validate

```powershell
python -m pytest
```
