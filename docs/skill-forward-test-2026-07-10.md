# Skill Forward Test 2026-07-10

This forward test used three read-only subagents with realistic Alterios tasks.
No live Alterios writes were executed.

## Scenarios

| Scenario | Skills | Result |
|---|---|---|
| New project read-only inventory and PM handoff | `alterios-project-base-inventory`, `alterios-pm-control-loop` | Passed with improvements: project-scoped inventory output and PM handoff template added. |
| Task form with `view_data_list`, `manual_script`, `start_process`, and row icons | `alterios-form-view-surface`, `alterios-ui-icons-and-actions`, `alterios-script-bpmn-flow` | Passed with improvements: relation/view source checks, field label/displaying checks, UUID `iconId` resolution, and UI `start_process` versus runtime `startProcess` split added. |
| Stimulsoft Project Database report write and verification | `alterios-write-tools`, `alterios-stimulsoft-project-db`, `alterios-safety-verifier` | Passed with improvements: existing report tools, targeted tests, and renderer risk are now explicit in skills. |

## Changes From Forward Test

- Added `skills/alterios-project-base-inventory/references/inventory-pm-template.md`.
- Updated inventory workflow to use `artifacts/inventories/<profile>/<project_id>` for exploratory project inventories.
- Updated installer to rewrite installed `source-map.md` files to absolute repo paths.
- Clarified `view_data` / `view_data_list` source checks and field labels/displaying.
- Clarified UUID-like `iconId` handling.
- Separated UI `start_process` actions from script runtime `startProcess` service calls.
- Made Stimulsoft typed report tools and embedded viewer risk explicit.
- Named targeted write/report tests in safety guidance.

## Remaining Gaps

- Icon UUID registry endpoint is still not documented as a stable API. Use usage matrices or verified readback until it is cataloged.
- Rendered PDF/image comparison for Stimulsoft remains backlog; current layout validation is static preflight.
- Security/destructive flows still need a separate sandbox scenario and destructive gate.
