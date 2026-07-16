---
name: alterios-stimulsoft-project-db
description: Build, repair, and verify Alterios/LIMS Stimulsoft reports and dashboards backed by Project Database view sources. Use for printable forms, dashboard widgets, report tabs, openId/current-record reports, datasource binding, view fields, filters, Stimulsoft JSON templates, layout overlap/overflow checks, dynamic-height risks, report/full readback, and report rendering diagnostics.
---

# Alterios Stimulsoft Project DB

Use this skill when report output depends on Alterios project-base data or when a report must render correctly for users.

## Workflow

1. Confirm the source view and fields with `get-data` or `get-data-simplified`.
2. Bind Stimulsoft data through Project Database sources when the report is based on Alterios project data.
3. Keep printable forms, dashboards, and embedded report tabs as separate design modes.
4. For current-record reports, verify `dataId: [openId]` behavior.
5. Validate `report/full` readback after template changes.
6. Run static layout checks for overlap, page overflow, and dynamic-height risk.
7. If the user needs UI/render proof, verify in browser or exported/rendered output; do not stop at JSON readback.
8. For Project Database dashboard tables, prefer templates saved through the Stimulsoft runtime/native builder so the saved JSON contains `ConnectionStringEncrypted`, `StiCustomDatabase`, `StiCustomSource`, and explicit table columns. Manually assembled JSON can render headers while returning blank rows in the Alterios viewer.
9. For printable output, require `type=report`, `StiPage`, title/header/data/footer
   bands, `{data.field}` expressions, and technical-column suppression.
10. Run `alterios_validate_printable_render` with sample rows. Acceptance needs
    a real PDF signature, positive page count, artifact size, and SHA-256; JSON
    structure alone is not render evidence.

Prefer existing typed tools before adding anything new: `alterios_upsert_report`, `alterios_patch_report_template`, `alterios_validate_report_project_base`, and `alterios_validate_stimulsoft_layout`.
The local PDF smoke proves Stimulsoft rendering and export. Embedded Alterios
viewer behavior still needs UI smoke when the report is installed into a live
form because browser integration and Project Database loading are separate
acceptance surfaces.

## Layout Rules

- Keep bands and components within page boundaries.
- Avoid overlapping visible components unless the template intentionally layers them.
- Reserve dynamic-height components enough room or place them in bands that can grow.
- Refresh Stimulsoft datasources after view field changes; stale datasources can hide fields.
- For table reports, validate both headers and row values in the UI. Source-view rows plus JSON readback are not enough when the embedded viewer is the acceptance target.

## References

Read `references/source-map.md`, then open the layout playbook and report-openId research for the current task.
For report write safety, also inspect `tests/test_write_control.py`; for layout behavior inspect `tests/test_stimulsoft_layout.py`.
