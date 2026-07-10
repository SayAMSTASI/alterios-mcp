# Alterios MCP Roadmap

The roadmap targets a production-oriented Alterios MCP that can safely inspect,
operate, and validate real Alterios instances with many projects. The current
code already has read-only discovery and guarded generic writes; the remaining
work is to make coverage complete, safety explicit, and releases repeatable.

## 1. Foundation And Safety

- Keep the profile model instance-scoped: one profile equals one Alterios
  instance, not one project.
- Keep profile registry extensible through `ALTERIOS_PROFILES` and
  `ALTERIOS_<PROFILE>_*` auto-discovery.
- Require project-scoped tools to accept explicit `project_id`.
- Use `ALTERIOS_<PROFILE>_PROJECT_ID` only as an optional default for local
  convenience.
- Keep `ALTERIOS_DOTENV_PATH` as the supported way to reuse private dotenv files
  without copying secrets into this repository.
- Redact tokens, auth headers, passwords, cookies, and API keys from all tool
  responses and errors.
- Maintain read-only defaults; keep writes behind `ALTERIOS_MCP_ALLOW_WRITE=1`.
- Add smoke checks for config loading, profile isolation, project override, and
  secret redaction.

## 2. Complete Read-Only Inventory

- Inventory instance-level projects first.
- Inventory project-level objects across content types, fields, views, forms,
  scripts, diagrams, contents, tasks, processes, reports, files, users/groups if
  available, and view data.
- Normalize route metadata: scope, method, path, required params, pagination,
  filters, response shape, and common errors.
- Add stable MCP tools for common inventory tasks instead of relying only on
  generic REST calls.
- Save reproducible JSON artifacts that identify profile and project context but
  exclude secrets.

## 3. Script Runtime Catalog

- Expand the known script-service catalog with categories, arguments,
  permissions, read/write labels, and examples.
- Probe read-only services by profile and project to capture body style,
  endpoint template behavior, and response shape.
- Keep runtime service names separate from `/api/scripts/execute-manual`, which
  executes saved scripts by UUID.
- Classify mutating services by risk and required safeguards.
- Add typed wrappers for safe high-value services after their payload contracts
  are verified.

## 4. Controlled Writes

- Keep generic writes disabled by default and gated by
  `ALTERIOS_MCP_ALLOW_WRITE=1`.
- Require explicit `project_id`, verified profile output, and narrow target
  arguments for write tools.
- Prefer typed write tools with validation over broad generic write endpoints.
- Treat generic `alterios_rest_write` as a research/emergency layer, not the
  normal operator interface.
- Expand typed writes by entity family: content/files, views/forms,
  scripts, BPMN/process/tasks, reports, then security/destructive flows.
- Add dry-run validation where Alterios supports it, plus request summaries and
  redacted audit records.
- Validate writes through API readback and, when relevant, UI-visible behavior.

## 5. Browser/UI Discovery

- Capture real UI network flows for list pages, forms, task screens, process
  actions, reports, dashboards, file fields, and permissions-sensitive flows.
- Map UI actions to REST endpoints and script-service calls.
- Use UI discovery to find missing request headers, route variants, encoded
  filters, and project-context behavior.
- Verify that API changes match what operators see in the Alterios UI.

## 6. Release Packaging

- Provide packaged console entry points and MCP server configuration examples.
- Prefer the installed `alterios-mcp` console script in MCP client configs;
  keep `python -m alterios_mcp.server` as a fallback.
- Document private configuration via environment variables and
  `ALTERIOS_DOTENV_PATH`; do not ship or copy secrets into the repo.
- Add release smoke tests for config, readonly inventory, project override, and
  write-gate behavior.
- Publish versioned artifacts, changelog notes, compatibility notes, and example
  discovery outputs.
- Keep docs aligned with implemented tools so production operators can tell what
  is shipped, experimental, or planned.

## 7. Agents And Skills

- Keep agent roles as a project control layer: PM, Project Base Explorer,
  Data Model Engineer, View Builder, Form Surface Engineer, UI Icons & Actions
  Reviewer, Script/BPMN Flow Integrator, Report/Stimulsoft Specialist, Write
  Tool Engineer, Safety Verifier, and Skill Curator.
- Store the operating contract in `docs/agents-and-skills.md`.
- Add repo-owned skills only after the relevant workflow is implemented and
  verified through tests or live sandbox readback.
- Start with skills for project base inventory, typed write tools,
  form/view surfaces, BPMN task flow, and Stimulsoft Project Database reports.
- Do not let skills encode unverified API behavior as fact.
