# Alterios MCP Project Status

Last updated: 2026-07-09

## Current Summary

The project has completed the foundation, multi-instance profile inventory,
read-only inventory expansion, script runtime catalog, controlled write gates,
and the first browser/UI discovery tooling slice. Live browser captures are
still pending before the first typed write candidate.
First controlled live write practice has been completed on the `artx` test
project `4e247a6b-55ef-4665-b88c-3c156fee19ba`.
The ARTX project entity surface has been cataloged across metadata, UI,
runtime data, workflow, files, comments, users, and reports.

## Completed

| Stage | Result | Commit | Verification |
|---|---|---|---|
| 1. Foundation and safety | MCP package scaffold, profile model, project override, secret redaction, guarded writes, static scanner, base docs. | `f4d1b5d` | `pytest`: 18 passed; live project list: 18 projects; live readonly discovery: 11/11 OK; static scan: 143 API paths and 33 services; secret scan clean. |
| 2. Read-only inventory expansion | Added typed read-only tools for report, view, form, fields, groups, file metadata, comments, and generic view data context. Discovery matrix expanded to 15 routes. | `3821ef7` | `pytest`: 25 passed; live `vniimt` discovery: 15/15 OK; live typed checks OK for view/form/report/fields/groups/comments/file metadata; secret scan clean. |
| 3. Script runtime catalog | Expanded the 14 confirmed runtime services with risk levels, argument contracts, examples, result shapes, probe safety, docs, and false-positive scan coverage. | `7d01813` | `pytest`: 32 passed; static scan: 175 files, 143 API paths, 33 service-like names, 14 known services; `vniimt` runtime probe prepare blocked by `/api/scripts/execute-manual` endpoint config as expected; secret scan clean. |
| 4. Controlled writes | Added dry-run-first write gates, explicit `profile`/`project_id` validation, redacted audit output, destructive-operation extra flag, manual-script UUID validation, and no-network unit coverage. | `2bc7dd2` | `pytest`: 43 passed; no-network dry-run/execution smoke covered by tests; `git diff --check` OK; secret scan clean; no live write executed. |
| 5a. Browser/UI flow analyzer | Added HAR/JSON network-flow analyzer, route classification, stable ID placeholders, secret/content redaction, CLI entrypoint, docs, and unit coverage. | `649f2af` | `pytest`: 48 passed; `git diff --check` OK; secret scan clean; no live write executed; live UI capture artifacts still pending. |
| Config. Multi-instance profile inventory | Added `ALTERIOS_PROFILES` support, profile auto-discovery, `alterios_list_profiles`, `alterios-discover --profiles`, profile-scoped missing keys, default-profile inventory, and safer URL redaction. | `2f8a87c` | `pytest`: 55 passed; `git diff --check` OK; secret scan clean; CLI `--profiles --profile artx --json` smoke OK; no network/write executed. |
| Practice. ARTX help sandbox write | Created `MCP Practice Sandbox` help entry in `artx` project `4e247a6b-55ef-4665-b88c-3c156fee19ba` through controlled generic REST write. | `bb89755` | Redacted profile check OK; readonly discovery 15/15 OK; dry-run audit OK; `POST /api/helps` executed with `ALTERIOS_MCP_ALLOW_WRITE=1`; API readback found id `2794b152-e1ca-4de2-9d3d-23b81a747d09`; browser UI showed title and body text. |
| Analysis. ARTX entity surface catalog | Documented the full project entity surface: counts, read/write routes, observed settings, risks, and write-practice order. | `f2cd8e5` | Live read-only inventory: 13 content types, 2522 fields, 21 views, 37 forms, 11 scripts, 3 diagrams, 144 contents, 1 task, 16 processes, 10 groups, 2 helps; `/api/features` and `/api/files` generic list routes returned 404; no write executed for this analysis. |

## Active Stage

| Stage | Status | Owner | Acceptance Criteria |
|---|---|---|---|
| 5. Browser/UI discovery | In Progress | Lead Engineer + PM/Explorer/Verifier agents | Capture UI/network flows for write-relevant actions, map them to REST/script calls, and verify API behavior against operator-visible UI behavior before production typed writes. |

## Backlog

| Priority | Task | Status | Notes |
|---:|---|---|---|
| 1 | Capture browser/UI network-flow workflow for write-relevant actions. | In Progress | Analyzer/tooling delivered in `649f2af`; real Alterios UI captures and sanitized artifacts are still needed. |
| 1 | Prepare first typed write candidate: `alterios_update_content_fields`. | Next | Use one existing scratch/test content record; require preflight read, field allowlist, dry-run diff, execution gate, and readback verification. |
| 1 | Build sandbox data chain: content type -> fields -> form -> view -> content record. | Next | Use ARTX test project and the sequence in `docs/alterios-entity-surface-catalog.md`. |
| 2 | Add profile-level live smoke matrix across multiple Alterios instances. | Next | Run `alterios_list_profiles`, then read-only project list per profile with explicit `project_id` only where needed. |
| 2 | Add plan binding or expected target IDs for execution after dry-run review. | Deferred | Useful before production typed write execution. |
| 2 | Improve static scanner context classification (`matched_by`, confidence, callee kind). | Deferred | Stage 3 keeps false positives unknown; deeper classification is separate scanner work. |
| 3 | Release packaging and changelog process. | Deferred | Start after controlled writes are stable. |

## Current Risks

| Risk | Mitigation |
|---|---|
| Runtime service endpoint compatibility is blocked in the current `vniimt` config because the endpoint template is `/api/scripts/execute-manual`. | Keep runtime service names cataloged only; do not treat them as executable through manual-script UUID endpoint. |
| Generic write tools can mutate production Alterios projects if deliberately executed. | Keep dry-run as default, require explicit `profile`, explicit `project_id`, `ALTERIOS_MCP_ALLOW_WRITE=1`, and `dry_run=false`; use typed tools with readback for production workflows. |
| Many Alterios endpoints are project-scoped even when they look generic. | Continue treating profile as instance and `project_id` as explicit call context. |
| Browser/UI flow tooling has not yet captured a live Alterios scenario in this session. | Keep Stage 5 open; capture only in scratch/test context and commit sanitized artifacts after redaction checks. |
| Generic REST write can create live UI objects but does not yet provide typed preflight semantics. | Use the ARTX help sandbox result to design narrow typed write tools with explicit allowed fields, dry-run diffs, and readback checks. |

## Next Concrete Actions

1. Capture representative UI/network flows for content open, content save, form
   actions, file fields, process/task actions, and comments in a scratch/test
   project.
2. Run `alterios-ui-flow` on each capture and save sanitized JSON artifacts.
3. Map captured UI flows to REST routes or script-service calls.
4. Follow the cataloged entity order: content type, fields, forms, views,
   contents, comments, files, scripts, diagrams/processes, reports.
5. Add a typed `alterios_upsert_help` or practice-write helper based on the
   verified `/api/helps` flow.
6. Design `alterios_update_content_fields` around one scratch/test content
   record with preflight, dry-run diff, execution gate, and readback.
7. Keep destructive, workflow, notification, and file upload writes out of the
   first typed write candidate.

## PM Update Checklist

- Update this file after every pushed stage.
- Record commit hashes, not only task names.
- Separate verified facts from assumptions.
- Keep blocked or deferred work visible instead of silently dropping it.
- Close completed subagents after their output is integrated.
