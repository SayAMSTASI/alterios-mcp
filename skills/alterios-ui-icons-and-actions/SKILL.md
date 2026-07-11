---
name: alterios-ui-icons-and-actions
description: Review and configure Alterios/LIMS UI icons, iconId values, compact action buttons, row menus, action order, Google Fonts Icons usage, and semantic action placement. Use when forms, groups, row actions, list actions, process actions, save/back/edit/view/delete/menu/info/add/sync/files buttons, or icon standards must be checked.
---

# Alterios UI Icons And Actions

Use this skill before finalizing any Alterios UI action surface. It is a reviewer skill: it should usually inspect and propose or validate, while form or write skills perform the actual patch.

## Standards

- Use Google Fonts Icons only.
- Use base icon size `16`.
- Use base color `#4B77D1`.
- Prefer compact icon buttons for common actions instead of text-only buttons.
- Use a three-dot menu for secondary row actions.
- Keep the standard row action order: edit, visibility/view, delete.
- Before writing forms, groups, or actions, ensure required Google icons are uploaded into the target project through `alterios_ensure_project_icons`.
- For the approved project icon set, use `alterios_ensure_project_icon_library` first. It must inventory the target project registry and file manager, upload only missing SVG files from `assets/icons/project-public`, and return target-project-local UUID values.
- Use the returned project-local UUID values as `iconId`; never leave raw Google icon names such as `save`, `more_vert`, or `visibility` in saved Alterios JSON.
- Never copy `iconId` values between projects. File UUIDs are local to one Alterios project; copy or upload the SVG file into the target project and use the new target UUID.
- Do not replace an existing icon if it already matches the action meaning and local style.
- Treat a UUID-like `iconId` as a stored reference, not proof that the icon matches the action standard.
- When inventorying file-manager icons from an elFinder URL, respect the selected folder exactly: `icons_folder_name=null` and `recurse=false` means current folder only. Do not descend into `public/icons` unless the user explicitly asks for that subfolder.
- When choosing among project icons or action types, read `docs/alterios-icons-and-actions-catalog.md` and match the user action to the documented semantic before assigning `iconId`.
- The reusable git icon library must use Google Fonts Icons downloaded with UI Size `16` and fill color `#4B77D1`; preserve the SVG `width`/`height` exactly as downloaded.
- For add/edit page actions, place `Закрыть` first with `keyboard_return`, then `Сохранить` with `save`.
- For view/detail page actions, include only `Закрыть` with `keyboard_return` unless the form has a separate business action.
- On a view/detail form, use an icon-only `edit_document` action with tooltip `Редактировать` to open the edit form for the current record. Do not add this action to the edit form itself.
- For script or processing actions, use `forms_apps_script`.
- If an element has more than three actions, group them behind `menu`.
- In list value actions, use a `menu` action and include `Редактировать`, `Просмотр`, and `Удалить` with icons.
- For dictionary/reference lists, add a bulk edit action only after confirming that the fields offered for bulk output are not relation fields.
- If a surface is intentionally custom or unusual, confirm with the user before replacing its action model.

## Review Steps

1. Inventory every `iconId` on forms, groups, form actions, row actions, list actions, and process actions.
2. Check action semantics before checking appearance.
3. Confirm destructive actions are visually and behaviorally distinct from view/edit.
4. Check that labels, icons, and menu placement match the user workflow.
5. If a needed icon is missing from the project registry, call `alterios_ensure_project_icon_library` in dry-run first for project-standard icons, or `alterios_ensure_project_icons` for pure Google Fonts icons; apply only with the saved `plan_id` and write gate.
6. If `iconId` is UUID-like, resolve it through the icon usage matrix or verified registry/readback before claiming it matches the semantic icon; otherwise mark it unresolved.
7. For project file-manager catalogs, use `alterios_list_project_icons` or `alterios_export_project_icons` before guessing from raw filenames; record whether the source was current folder, named subfolder, or recursive tree.
8. Validate local library SVG size/color before adding or replacing icons in a project.
9. Return a correction list with target object id, current icon, proposed icon, reason, and verification method.

## References

Read `references/source-map.md`, then open the full icon/action catalog for icon selection or action behavior, and the usage matrix only when existing `iconId` values must be resolved.
