---
name: alterios-form-view-surface
description: Analyze, design, and verify Alterios/LIMS views and form surfaces. Use when working with tabs, rows, cells, fields, view_data, view_data_list, reports, comments_list, help/html/content cells, form actions, list/add/edit/detail/task/main forms, openId/dataId context, roles, styles, display conditions, source fields, no-gap layouts, or F-pattern placement.
---

# Alterios Form View Surface

Use this skill when a user-facing Alterios screen must be built, repaired, or audited. Pair it with `alterios-project-base-inventory` for source discovery and with `alterios-ui-icons-and-actions` before finalizing actions.

## Workflow

1. Read the relevant current form and source view before changing anything.
2. Map tabs, rows, cells, action containers, roles, conditions, styles, params, `openId`, and `viewEntityId`.
3. Confirm source data through `get-data` or `get-data-simplified`.
4. Place content with no empty visual gaps: primary fields first, related lists below context, reports/comments/help only where they support the user flow.
5. Preserve local module style unless the user explicitly asks for a redesign.
6. For embedded current-record surfaces, verify `dataId: [openId]`; do not rely on `contentId` alone.
7. Treat missing view/content type/report sources as quality blockers until resolved or explicitly documented.
8. For `view_data` and `view_data_list`, inspect `cell.params.viewId`, `cell.params.openId`, `viewEntityId`, the view entity chain, and the real relation field through view/entity/field readback.
9. After writes, verify API readback and UI-visible behavior when the result is user-facing.

## Layout Rules

- Keep list/add/edit/detail/task/main forms distinct.
- Avoid empty tabs, rows, cells, and spacer-like content.
- Keep field labels, `pageTitle`, and page names user-readable.
- Check field order, labels, `displaying`, required status, and source field meaning before treating a field cell as finished.
- Use `view_data_list` for related rows and validate the real relation field.
- For save plus script flows, preserve `submit_all -> manual_script -> routing/redirect` when the script needs fresh saved data.

## References

Read `references/source-map.md` to choose the right inventory or UX reference.
