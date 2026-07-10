# alterios-form-view-surface

Use this skill when creating, auditing, or changing Alterios/LIMS forms that
contain views, content cells, embedded reports, comments, row actions, or
task/edit surfaces.

## Workflow

1. Identify the target profile, `project_id`, form id/name, and related
   `viewId`/`contentTypeId`/`reportId`.
2. Read the current form before planning changes.
3. Run `alterios_analyze_form_surface` or `alterios-form-surface-check` before
   write actions.
4. Fix blocking source errors first: missing `viewId`, `contentTypeId`, or
   `reportId`.
5. Fix UX warnings next: empty layout slots, data cells without full-width/flex
   style, missing action icons, row action order, and missing `openId` where
   current-record context is required.
6. For write changes, use the narrowest typed tool:
   `alterios_patch_form_tabs`, `alterios_patch_form_actions`, or
   `alterios_upsert_form`.
7. Verify with readback, analyzer result, and UI/HAR/screenshot when the
   change is user-visible.

## Rules

- Primary `view_data_list`/`view_data` content should occupy the full row.
- Do not leave empty visual slots, spacer cells, or empty tabs in production
  forms.
- Follow F-pattern layout: user-facing title first, primary content next,
  secondary report/comments/help below or in named tabs.
- Inventory role/access keys before changing forms used by BPMN tasks.
- Actions are icon-first. Visible toolbar/list buttons should be icons; text is
  tooltip/menu/title only.
- Row action order is edit, view, delete. Delete is last and destructive.
- Use Google Fonts Icons, size `16`, color `#4B77D1`.

## References

- `docs/form-surface-ux-and-icons.md`
- `docs/alterios-icon-standards.md` in the working AlteriosCodex workspace when
  available.
