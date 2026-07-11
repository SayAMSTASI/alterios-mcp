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
9. For views, distinguish source content fields from view fields: adding a content field is not enough until the view field, alias, order, filters, sorts, joins, and current-record behavior are verified.
10. For views, use the Alterios experimental mode as the default required mode. Treat a non-experimental view configuration as a blocker unless the user explicitly asks for legacy behavior.
11. After writes, verify API readback and UI-visible behavior when the result is user-facing.

## Layout Rules

- Keep list/add/edit/detail/task/main forms distinct.
- For every material module, create or verify a separate read-only view/detail form in addition to list/add/edit/task forms.
- Avoid empty tabs, rows, cells, and spacer-like content.
- Keep field labels, `pageTitle`, and page names user-readable.
- Write user-facing form titles and tab/page names so the user understands which interface and record context they are in.
- For add forms, set `pageTitle` to `Добавить {что добавляем}`.
- For list forms, set `pageTitle` to `{наименование сущности во множественном роде}`.
- For view/detail and edit forms, set `pageTitle` to `{наименование сущности в единственном роде}`.
- Check field order, labels, `displaying`, required status, and source field meaning before treating a field cell as finished.
- Use persistent bottom helper/footnote text under a form field only for fields whose persisted content type field is `date`. For other field types, prefer a clear label, tooltip/help, placeholder, or separate help block instead of always-visible bottom text.
- Use `view_data_list` for related rows and validate the real relation field.
- Validate view filters explicitly: static filters, user filters, role-dependent filters, and `openId`/`dataId` current-record filters have different acceptance checks.
- Always add a field-based filter for form-embedded views/lists. A `view_data` or `view_data_list` cell must be constrained by the relevant source field, relation field, or `dataId: [openId]`; unfiltered embedded lists are allowed only when the user explicitly needs a global list.
- Hide non-informative list columns by default: technical IDs, helper relation fields, system metadata, empty service fields, and columns that do not help the user's decision.
- For save plus script flows, preserve `submit_all -> manual_script -> routing/redirect` when the script needs fresh saved data.
- For add/edit page actions, place `Закрыть` first and `Сохранить` second, both with project-local icons.
- For view/detail page actions, include `Закрыть` with an icon and do not add save unless there is a real write scenario.
- Make save behavior context-aware: terminal hierarchy forms use save-and-back; non-terminal forms save in place.
- On view/detail forms, add an icon-only `Редактировать` action using the edit-document semantic when editing the current record is allowed. Do not add that self-edit action to edit forms.
- Keep element actions on view/detail and edit forms semantically consistent; the edit form only omits the transition to edit itself.
- For list value actions, the default row action is `Просмотр`. Use an outer `type: "menu"` value action container with nested `containers[]`, and set `default: true` on the nested `Просмотр` action container.
- If an existing interface is intentionally unusual, ask before changing its interaction model.

## References

Read `references/source-map.md` to choose the right inventory or UX reference.
