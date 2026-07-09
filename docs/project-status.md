# Alterios MCP Project Status

Last updated: 2026-07-09

## Current Summary

The project has completed the foundation, read-only inventory expansion, and
script runtime catalog stages. The next delivery stage is controlled writes
design.

## Completed

| Stage | Result | Commit | Verification |
|---|---|---|---|
| 1. Foundation and safety | MCP package scaffold, profile model, project override, secret redaction, guarded writes, static scanner, base docs. | `f4d1b5d` | `pytest`: 18 passed; live project list: 18 projects; live readonly discovery: 11/11 OK; static scan: 143 API paths and 33 services; secret scan clean. |
| 2. Read-only inventory expansion | Added typed read-only tools for report, view, form, fields, groups, file metadata, comments, and generic view data context. Discovery matrix expanded to 15 routes. | `3821ef7` | `pytest`: 25 passed; live `vniimt` discovery: 15/15 OK; live typed checks OK for view/form/report/fields/groups/comments/file metadata; secret scan clean. |
| 3. Script runtime catalog | Expanded the 14 confirmed runtime services with risk levels, argument contracts, examples, result shapes, probe safety, docs, and false-positive scan coverage. | `7d01813` | `pytest`: 32 passed; static scan: 175 files, 143 API paths, 33 service-like names, 14 known services; `vniimt` runtime probe prepare blocked by `/api/scripts/execute-manual` endpoint config as expected; secret scan clean. |

## Active Stage

| Stage | Status | Owner | Acceptance Criteria |
|---|---|---|---|
| 4. Controlled writes | Next | Lead Engineer + PM/Explorer/Verifier agents | Define typed write safeguards, dry-run summaries, explicit target validation, audit output, and readback verification before adding or using any production write wrapper. |

## Backlog

| Priority | Task | Status | Notes |
|---:|---|---|---|
| 1 | Design controlled write policy and typed validator contract. | Next | No broad write enablement without stage gate. |
| 1 | Add dry-run/audit response model for future write tools. | Next | Must include target profile, explicit `project_id`, operation summary, and redacted request data. |
| 1 | Select first low-risk typed write candidate only after validation design is complete. | Next | Prefer idempotent update with API readback; do not start with destructive operations. |
| 2 | Add browser/UI discovery workflow for network-flow capture. | Deferred | Needed before user-facing write automation. |
| 2 | Improve static scanner context classification (`matched_by`, confidence, callee kind). | Deferred | Stage 3 keeps false positives unknown; deeper classification is separate scanner work. |
| 3 | Release packaging and changelog process. | Deferred | Start after controlled writes are stable. |

## Current Risks

| Risk | Mitigation |
|---|---|
| Runtime service endpoint compatibility is blocked in the current `vniimt` config because the endpoint template is `/api/scripts/execute-manual`. | Keep runtime service names cataloged only; do not treat them as executable through manual-script UUID endpoint. |
| Write APIs can mutate production Alterios projects. | Keep write tools disabled by default and require explicit `ALTERIOS_MCP_ALLOW_WRITE=1`, verified profile, and explicit `project_id`. |
| Many Alterios endpoints are project-scoped even when they look generic. | Continue treating profile as instance and `project_id` as explicit call context. |

## Next Concrete Actions

1. Write the controlled-write policy and acceptance gate.
2. Define a reusable dry-run/audit response shape for write-capable tools.
3. Add tests proving write mode remains disabled by default and target context
   is explicit.
4. Pick one low-risk typed write candidate only after the validator and dry-run
   contract are in place.

## PM Update Checklist

- Update this file after every pushed stage.
- Record commit hashes, not only task names.
- Separate verified facts from assumptions.
- Keep blocked or deferred work visible instead of silently dropping it.
- Close completed subagents after their output is integrated.
