# Alterios MCP Project Status

Last updated: 2026-07-10

## Current Summary

The project has completed the foundation, multi-instance profile inventory,
read-only inventory expansion, script runtime catalog, controlled write gates,
and the first browser/UI discovery tooling slice. Live browser captures are
still pending before the first typed write candidate.
First controlled live write practice has been completed on the `artx` test
project `4e247a6b-55ef-4665-b88c-3c156fee19ba`.
The ARTX project entity surface has been cataloged across metadata, UI,
runtime data, workflow, files, comments, users, and reports.
The ARTX sandbox metadata chain now exists as a reproducible practice script:
content type plus representative fields with dry-run, write gate, and readback.
The same practice script now covers the sandbox UI/data chain: table view,
view entity, view fields, add/edit/main forms, menu group, and one content row.
The same practice script now covers comment write/readback and a visible
`comments_list` UI block for the sandbox content row.
The same practice script now covers file-field upload, saved manual script
creation/execution, sandbox BPMN process/task completion, and dashboard report
create/update/full-readback.
Method coverage is now tracked explicitly: 23 MCP tools, 14 runtime services,
15 live read-only route probes, 57 REST route/method patterns, and 13 operation
classes.
Reinventory on 2026-07-10 confirmed the main product gap: ART X project base
has live evidence for views, forms, scripts, BPMN/process/task side effects,
files, comments, and reports, but the MCP server currently exposes only 4
write-like tools out of 23 total tools. The next build stage is typed write
expansion rather than more generic REST access.

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
| Practice. ARTX metadata sandbox chain | Added reproducible `scripts/artx_practice_metadata.py`, created `MCP Practice. Песочница` content type and 6 fields through controlled REST writes. | `5d3e057` | Profile/project check OK; initial dry-run blocked fields until content type existed; `POST /api/content-types/save` created id `572aedf5-500f-4538-82be-ae2170ff174a`; `POST /api/fields/save` created 6 fields; readback confirmed actual mnames and `contentNameTemplate={{field_test__mcp_practice_mcp_practice_title}}`; final dry-run was idempotent with no planned writes. |
| Practice. ARTX UI/data sandbox chain | Extended `scripts/artx_practice_metadata.py` to create and verify view, view entity, view fields, add/edit/main forms, menu group, and one content row for the same sandbox. | `347841f` | Created view `cfd46277-d8da-4b7d-ba0e-7c96ea85046e`, forms `281442af-bb94-43a2-bc80-f5303c05d0fc`, `15f5fb26-5db4-4153-8131-23a54411cd63`, `3cfc70ab-3fb0-4567-8e25-7c863f0e87d0`, group `aa997c9a-d81e-4042-91c5-bafa90b32819`, content `bd51e83f-201e-4d53-bdc6-c4cd16754756`; `get-data-simplified` row_count=1; final dry-run was all `exists`; browser UI showed columns, add action, record, and date `10.07.2026`. |
| Analysis. Method coverage matrix | Added `docs/alterios-method-coverage.md` with counted MCP tools, runtime services, REST route/method patterns, operation classes, and live/cataloged/needs-HAR statuses. | `63cd9c3` | Counted from source: 22 MCP tools, 14 runtime services, 15 live readonly probes; registry now tracks 50 REST route/method patterns and 13 operation classes; explicitly marks comments/files/scripts/workflow/reports/security/destructive flows as not complete until sandbox/HAR/readback verification exists. |
| Practice. ARTX comments sandbox write | Added typed `alterios_add_comment`, extended `scripts/artx_practice_metadata.py`, and created one idempotent sandbox comment on the existing practice content row. | `65118a4` | Profile/project check OK; dry-run planned only `POST /api/v1/comments`; execution with `ALTERIOS_MCP_ALLOW_WRITE=1` created comment `7c8d6eb2-6a0b-4029-bbd9-63322bce1294` on content `bd51e83f-201e-4d53-bdc6-c4cd16754756`; final dry-run was all `exists` with `comment_found=true`, `comment_count=1`. |
| Practice. ARTX comments UI surface | Switched default comment scope to `entity=any`, added `comments_list` to the edit form, and verified native comments in the browser. | `167a558` | Dry-run planned edit-form update plus one `entity=any` comment; execution created comment `58988a37-8ddc-4839-83ea-c77e8f9876af`; browser card `MCP Practice. Карточка записи` showed block `Обсуждение`, author/date, and text `MCP Practice comment: comments write/readback coverage.`. |
| Practice. ARTX file/script/BPMN/report sandbox | Extended `scripts/artx_practice_metadata.py` to cover file-field upload, manual script creation/execution, BPMN diagram/process/task side effects, and dashboard report create/update/readback. | `12b8eb0` | Created file field `ea8d3e8c-b0cb-4eb8-9bb7-ad85acd8d7f2`; uploaded `mcp-practice-upload.txt` as file `c3cae956-296c-4f36-a966-cf5c0f3fc433`; created manual script `804e613a-19dd-4ea6-a0fc-a8fc118f6140` and executed it; created BPMN diagram `8ecdd2a7-23d4-40b2-b883-eb7c2ca19011`, started process `56051aa8-07a7-473d-a8ec-7c3a6beb26c0`, completed task `c989aa11-52bc-4f56-bb56-24f4a82afbf1`; created report `86ad4189-deaf-4744-96d5-6b1d22e73468` with Stimulsoft dashboard full readback; final dry-run was idempotent and browser main form showed `ФАЙЛ`, the sandbox row, and `MCP Practice sandbox report`. |
| Analysis. ARTX reinventory and MCP startup correction | Rechecked project base totals, MCP tool surface, startup shape, typed-write gaps, and agents/skills plan. Added `docs/reinventory-2026-07-10.md` and `docs/agents-and-skills.md`; updated README startup guidance to prefer `alterios-mcp.exe`. | `TBD-REINVENTORY-COMMIT` | Live profile smoke OK for `artx` and `vniimt`; live read-only discovery 15/15 OK for ART X project; project totals: 14 content types, 2529 fields, 22 views, 40 forms, 12 scripts, 4 diagrams, 145 contents, 17 processes, 1 report; MCP surface: 23 tools, 4 write-like tools. |

## Active Stage

| Stage | Status | Owner | Acceptance Criteria |
|---|---|---|---|
| 6. Typed write expansion | In Progress | Lead Engineer + PM/Explorer/Worker/Verifier agents | Add entity-specific write tools with preflight, dry-run diff, managed-marker guard, write gate, live sandbox execution, and readback. |

## Backlog

| Priority | Task | Status | Notes |
|---:|---|---|---|
| 1 | Add typed content/file tools: `alterios_update_content_fields` and `alterios_file_upload_to_field`. | Next | Use existing `MCP Practice` sandbox; require preflight read, field allowlist, dry-run diff, execution gate, file metadata readback, and content readback. |
| 1 | Add typed view/form tools. | Next | Cover `alterios_upsert_view`, `alterios_upsert_view_entity`, `alterios_upsert_view_field`, `alterios_upsert_form`, and narrow form action patches. |
| 1 | Add typed script/BPMN/report tools. | Next | Cover script upsert, manual script execution preflight, BPMN diagram upsert, process start/task complete, report upsert, and Project Database validation. |
| 1 | Capture browser/UI network-flow workflow for uncovered operation classes. | In Progress | File/script/BPMN/report paths now have API sandbox coverage; remaining capture priority is destructive/security flows and UI proof for production-grade typed writes. |
| 1 | Build sandbox data chain: content type -> fields -> form -> view -> content record. | Done | Completed in ARTX sandbox; comments, files, manual scripts, BPMN/process/task side effects, and reports are now covered. |
| 2 | Add repo-owned agents and skills scaffolding after typed tools land. | Next | Follow `docs/agents-and-skills.md`; do not create skills that document unverified APIs as facts. |
| 2 | Add profile-level live smoke matrix across multiple Alterios instances. | Next | Run `alterios_list_profiles`, then read-only project list per profile with explicit `project_id` only where needed. |
| 2 | Add plan binding or expected target IDs for execution after dry-run review. | Deferred | Useful before production typed write execution. |
| 2 | Improve static scanner context classification (`matched_by`, confidence, callee kind). | Deferred | Stage 3 keeps false positives unknown; deeper classification is separate scanner work. |
| 3 | Release packaging and changelog process. | Deferred | Start after controlled writes are stable. |

## Current Risks

| Risk | Mitigation |
|---|---|
| Runtime service endpoint compatibility is blocked in the current `vniimt` config because the endpoint template is `/api/scripts/execute-manual`. | Keep runtime service names cataloged only; do not treat them as executable through manual-script UUID endpoint. |
| Generic write tools can mutate production Alterios projects if deliberately executed. | Keep dry-run as default, require explicit `profile`, explicit `project_id`, `ALTERIOS_MCP_ALLOW_WRITE=1`, and `dry_run=false`; use typed tools with readback for production workflows. |
| Current write MCP surface is too small for full operational use. | Expand from 4 write-like tools to typed entity tools for content/files, views/forms, scripts, BPMN/process/tasks, and reports. |
| Many Alterios endpoints are project-scoped even when they look generic. | Continue treating profile as instance and `project_id` as explicit call context. |
| Browser/UI flow tooling has not yet captured a live Alterios scenario in this session. | Keep Stage 5 open; capture only in scratch/test context and commit sanitized artifacts after redaction checks. |
| Generic REST write can create live UI objects but does not yet provide typed preflight semantics. | Use the ARTX help sandbox result to design narrow typed write tools with explicit allowed fields, dry-run diffs, and readback checks. |

## Next Concrete Actions

1. Implement shared typed-write helper semantics: preflight, dry-run diff,
   managed-marker guard, `ALTERIOS_MCP_ALLOW_WRITE=1`, execution, readback.
2. Add `alterios_update_content_fields` and `alterios_file_upload_to_field`
   against the existing `MCP Practice` sandbox.
3. Add typed view/form tools, then verify with `MCP Practice. Список` and the
   three MCP Practice forms.
4. Add script/BPMN/report typed tools and verify against the already-created
   manual script, BPMN process/task chain, and Project Database dashboard.
5. Add repo-owned skill folders only after each workflow has verified code and
   readback evidence.
6. Keep destructive/security flows out of normal write tools until a separate
   sandbox scenario and destructive gate are implemented.

## PM Update Checklist

- Update this file after every pushed stage.
- Record commit hashes, not only task names.
- Separate verified facts from assumptions.
- Keep blocked or deferred work visible instead of silently dropping it.
- Close completed subagents after their output is integrated.
