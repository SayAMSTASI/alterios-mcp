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
- Use the returned project-local UUID values as `iconId`; never leave raw Google icon names such as `save`, `more_vert`, or `visibility` in saved Alterios JSON.
- Do not replace an existing icon if it already matches the action meaning and local style.
- Treat a UUID-like `iconId` as a stored reference, not proof that the icon matches the action standard.

## Review Steps

1. Inventory every `iconId` on forms, groups, form actions, row actions, list actions, and process actions.
2. Check action semantics before checking appearance.
3. Confirm destructive actions are visually and behaviorally distinct from view/edit.
4. Check that labels, icons, and menu placement match the user workflow.
5. If a needed icon is missing from the project registry, call `alterios_ensure_project_icons` in dry-run first; apply only with the saved `plan_id` and write gate.
6. If `iconId` is UUID-like, resolve it through the icon usage matrix or verified registry/readback before claiming it matches the semantic icon; otherwise mark it unresolved.
7. Return a correction list with target object id, current icon, proposed icon, reason, and verification method.

## References

Read `references/source-map.md`, then open the icon standard and icon usage matrix only when icon validation is needed.
