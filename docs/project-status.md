# Alterios MCP Project Status

Last updated: 2026-07-09

## Current Summary

The project is past the foundation and first read-only inventory expansion.
The next delivery stage is the script runtime catalog.

## Completed

| Stage | Result | Commit | Verification |
|---|---|---|---|
| 1. Foundation and safety | MCP package scaffold, profile model, project override, secret redaction, guarded writes, static scanner, base docs. | `f4d1b5d` | `pytest`: 18 passed; live project list: 18 projects; live readonly discovery: 11/11 OK; static scan: 143 API paths and 33 services; secret scan clean. |
| 2. Read-only inventory expansion | Added typed read-only tools for report, view, form, fields, groups, file metadata, comments, and generic view data context. Discovery matrix expanded to 15 routes. | `3821ef7` | `pytest`: 25 passed; live `vniimt` discovery: 15/15 OK; live typed checks OK for view/form/report/fields/groups/comments/file metadata; secret scan clean. |

## Active Stage

| Stage | Status | Owner | Acceptance Criteria |
|---|---|---|---|
| 3. Script runtime catalog | Next | Lead Engineer + Explorer/Verifier agents | Catalog known runtime script services, classify read/write risk, document argument contracts, validate read-only calls where a compatible endpoint exists, and keep `/api/scripts/execute-manual` separate from runtime service names. |

## Backlog

| Priority | Task | Status | Notes |
|---:|---|---|---|
| 1 | Expand `services.py` with service categories, arguments, examples, and risk levels. | Next | Keep mutating services gated. |
| 1 | Add script-service catalog docs and tests for service metadata. | Next | Should be testable without live API. |
| 1 | Probe compatible read-only runtime service endpoint if available. | Next | Do not confuse runtime service names with manual script UUID execution. |
| 2 | Add controlled write design with typed validators and dry-run strategy. | Deferred | No broad write enablement without stage gate. |
| 2 | Add browser/UI discovery workflow for network-flow capture. | Deferred | Needed before user-facing write automation. |
| 3 | Release packaging and changelog process. | Deferred | Start after controlled writes are stable. |

## Current Risks

| Risk | Mitigation |
|---|---|
| Runtime service endpoint compatibility is not fully confirmed. | Keep script runtime services cataloged but do not expose unsafe execution paths as verified tools until probed. |
| Write APIs can mutate production Alterios projects. | Keep write tools disabled by default and require explicit `ALTERIOS_MCP_ALLOW_WRITE=1`, verified profile, and explicit `project_id`. |
| Many Alterios endpoints are project-scoped even when they look generic. | Continue treating profile as instance and `project_id` as explicit call context. |

## Next Concrete Actions

1. Convert `services.py` into a richer runtime catalog with service category,
   argument schema hints, examples, and mutation risk.
2. Add unit tests proving read/write classification and metadata export.
3. Add docs for the runtime catalog and the manual-script distinction.
4. Run `pytest`, secret scan, and a live read-only probe only if a compatible
   runtime endpoint is configured.

## PM Update Checklist

- Update this file after every pushed stage.
- Record commit hashes, not only task names.
- Separate verified facts from assumptions.
- Keep blocked or deferred work visible instead of silently dropping it.
- Close completed subagents after their output is integrated.
