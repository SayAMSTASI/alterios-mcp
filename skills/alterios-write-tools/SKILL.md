---
name: alterios-write-tools
description: Build, review, and operate guarded Alterios MCP write tools. Use when implementing or using typed write tools for content, file-field upload, views, view entities, view fields, forms, form actions/tabs, scripts, BPMN diagrams, process/task operations, reports, template patches, dry-run diffs, write gates, target checks, managed markers, and readback validation.
---

# Alterios Write Tools

Use this skill when a repeated Alterios operation should become a typed MCP tool or when an existing write tool must be operated safely.

## Workflow

1. Confirm the workflow has read-only evidence and a known route contract.
2. Prefer a typed tool over generic REST write.
3. Require explicit `profile`, explicit `project_id`, target identifiers, dry-run diff, and narrow allowed fields.
4. Keep `dry_run=true` as the default.
5. Execute live writes only with `ALTERIOS_MCP_ALLOW_WRITE=1` and `dry_run=false`.
6. Return redacted audit details and perform readback.
7. Add tests for happy path, blocked write, validation errors, target mismatch, and redaction.

For material-module write scenarios, enforce the configured UX contract:

- content type/material type must include a meaningful description and user hint/tooltip;
- views must use Alterios experimental mode unless the user explicitly asks for legacy behavior;
- forms must include list, add, edit, and read-only view/detail surfaces;
- form-embedded views/lists must have a relevant field-based filter or `dataId: [openId]`;
- list views must hide non-informative technical/service columns;
- forms must use human-readable user-facing titles, tab names, and page names.

Existing report write coverage includes `alterios_upsert_report`, `alterios_patch_report_template`, `alterios_validate_report_project_base`, and `alterios_validate_stimulsoft_layout`; use these before adding another report write tool.

## Boundaries

- Do not mix destructive/security flows into normal write tools.
- Do not mutate objects not marked as managed or explicitly targeted.
- Do not treat a successful save as verified without readback; use UI evidence when the change is user-facing.

## References

Read `references/source-map.md` before adding or changing a write tool.
