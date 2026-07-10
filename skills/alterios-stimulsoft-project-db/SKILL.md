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

## Layout Rules

- Keep bands and components within page boundaries.
- Avoid overlapping visible components unless the template intentionally layers them.
- Reserve dynamic-height components enough room or place them in bands that can grow.
- Refresh Stimulsoft datasources after view field changes; stale datasources can hide fields.

## References

Read `references/source-map.md`, then open the layout playbook and report-openId research for the current task.
