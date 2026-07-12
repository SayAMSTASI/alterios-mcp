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
12. When the user asks for a sample form or a user-facing view format, open the
    form-viewer UI and click every tab; `get-data` and standalone view preview
    are not enough.

## View Types And Modes

- Confirmed frontend `view.format` values are `table`, `grid`, `list`, `leaflet`, `gantt`, `reference`, and `calendar`.
- Confirmed live UI experimental/v2 formats are `table`, `reference`, `grid`, `list`, `gantt`, `leaflet`, and `calendar`. A joined `table` view is also confirmed when the join uses real view-field mnames.
- For experimental `table`, `reference`, and `list` UI-preview, set
  `settings.title` to one populated `viewField.mname`; do not use a Mustache
  template in this field.
- `calendar` requires `settings.title` for UI save/preview and `settings.startDate` for event rendering; `endDate` and `bgColor` are optional but verified.
- `settings.engineVersion = "v2"` is the default for new views. Empty settings or missing `engineVersion` are legacy/classic and require explicit evidence plus an explicit legacy flag in the write tool.
- Treat `cards` as unconfirmed: it is not present in the confirmed frontend enum.
- `grid` settings can include `desc`, `iconField`, `iconWidth`, and `iconHeight`.
- `list` has no separate config UI in the confirmed frontend build; use `engineVersion=v2` and verify through `get-data`.
- `gantt` requires `defaultView` (`day`, `week`, `month`, `quarter`, or `year`) plus `date1.field` and `date2.field`; optional settings include `plannedDate1`, `plannedDate2`, `title`, `resource`, `completion`, and show flags.
- `leaflet` requires a `geo` content field attached to the view, then `settings.geoFields[]` saved by populated view-field `mname`; `markerIcons` is required and must be `default`, `img`, or `field`. For visible markers, persisted `geo` values must be GeoJSON `Feature` objects, not bare `Point` geometry.
- `reference` is verified as a selector/ref source. Its standalone preview can save without error but does not render rows like a table/list.
- Do not embed `reference` as a standalone user list. Demonstrate it through a
  `ref source=view` field scenario or add a help note in a technical sample.
- For user-facing v2 table/list/joined views, set human-readable
  `viewField.alias` values. Form display titles alone do not reliably replace
  the table headers.
- For `grid`, treat `desc` as UI-sensitive: verify form-viewer output before
  keeping it. If the UI prints the mname literally, remove `desc` or use a
  proven syntax.
- `get-data-simplified` returns rows only for these formats; use full `get-data` when headers/settings evidence matters.
- For relation views, use short content field suffixes and `fieldNamePrefix` before fields are created. Long generated mnames can break joins through backend SQL alias truncation.
- Attach source fields to the view explicitly before using them in display,
  joins, filters, or reports. Adding a field to a content type does not make it
  available in the view.
- Read populated view fields before writing join conditions; do not infer `_id` aliases. Backends can expose the related id as `_id0` or another generated mname.
- Validate a view through both populated fields and `get-data` or `get-data-simplified`; a successful save is not enough.
- For `ref source=view`, the base table may show only the related row id. Use a
  joined table view to expose readable related attributes such as employee FIO.

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
- Use persistent bottom helper/footnote text under a form field only for fields whose persisted content type field is `date`. For other field types, prefer a clear label, tooltip, placeholder, or separate help block instead of always-visible bottom text. Treat analyzer issue `field_footnote_requires_date` as a tester failure before accepting a form.
- For table display cells, keep the visible cell header centered and bold. For non-table display cells, do not add a visible cell header; use `pageTitle`, tab titles, field labels, or tooltips instead.
- Use `view_data_list` for related rows and validate the real relation field.
- Treat the user-approved master-detail reference pattern as: top context row, compact action hub, grouped menus, second-row detail blocks, related list with centered bold table header, and nested downstream form section.
- In master-detail action hubs that follow this reference, short visible group labels on `top_center` action containers are allowed. Do not rewrite them to icon-only without a user request.
- Validate view filters explicitly: static filters, user filters, role-dependent filters, and `openId`/`dataId` current-record filters have different acceptance checks.
- Always add a field-based filter for form-embedded views/lists. A `view_data` or `view_data_list` cell must be constrained by the relevant source field, relation field, or `dataId: [openId]`; unfiltered embedded lists are allowed only when the user explicitly needs a global list.
- Hide non-informative list columns by default: technical IDs, helper relation fields, system metadata, empty service fields, and columns that do not help the user's decision.
- In joined views embedded in forms, hide generated related-id columns such as
  `_id0` in addition to the main `_id`; the join may need them internally but
  users must not see UUID values.
- For save plus script flows, preserve `submit_all -> manual_script -> routing/redirect` when the script needs fresh saved data.
- For add/edit page actions, place `Закрыть` first and `Сохранить` second, both with project-local icons.
- For view/detail page actions, include `Закрыть` with an icon and do not add save unless there is a real write scenario.
- Make save behavior context-aware: terminal hierarchy forms use save-and-back; non-terminal forms save in place.
- On view/detail forms, add an icon-only `Редактировать` action using the edit-document semantic when editing the current record is allowed. Do not add that self-edit action to edit forms.
- Keep element actions on view/detail and edit forms semantically consistent; the edit form only omits the transition to edit itself.
- Element actions must be icon-only: in `cellActionContainers`, set `title` to an empty string, put the visible meaning in `tooltip`, and use a project-local `iconId`. Text is allowed inside nested menu items, not on the outer element action.
- Exception: approved master-detail action hubs may use short visible labels on `position: "top_center"` action containers, such as `Отбор`, `Журналы`, `Отчеты`, `Вложения`.
- For menus with multiple print variants, use `arrow_drop_down` on the outer menu and `print` on each nested print item.
- Analytical and printable forms are opened as separate forms in a new browser tab: `type: "forms"`, `openInNewTab: true`, `openInDialog: false`. The target analytical/print form must include a page action `Закрыть`.
- For list value actions, the default row action is `Просмотр`. Use an outer `type: "menu"` value action container with nested `containers[]`, and set `default: true` on the nested `Просмотр` action container.
- If an existing interface is intentionally unusual, ask before changing its interaction model.

## References

Read `references/source-map.md` to choose the right inventory or UX reference.
