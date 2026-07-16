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

For scenario apply, do not let code, skills, and the running MCP drift apart:

- read `alterios_runtime_info` and block writes when `stale=true`;
- preserve the reviewed runtime fingerprint between dry-run and apply;
- verify `delivery_evidence.work_item_ref` and every `agent_handoff_refs` entry
  against private Gitea; require structured analyst, implementer, and verifier
  comments plus the current `ux_contract_version`;
- reject closed/missing work items, mismatched issue references, incomplete
  handoff sections, and missing required roles;
- use `alterios_ux_contract` as the machine-readable source of blocking form
  issue codes;
- require the same evidence in the saved dry-run plan and apply request.
- use `ALTERIOS_MCP_TOOL_PROFILE=live` for normal scenario work; restricted
  profiles must not expose generic REST/script write escape hatches.

For material-module write scenarios, enforce the configured UX contract:

- content type/material type must include a meaningful description and user hint/tooltip;
- views must use Alterios experimental mode unless the user explicitly asks for legacy behavior;
- forms must include list, add, edit, and read-only view/detail surfaces;
- form-embedded views/lists must have a relevant field-based filter or `dataId: [openId]`;
- list views must hide non-informative technical/service columns;
- forms must use human-readable user-facing titles, tab names, and page names.
- material-module apply must use target-project-local UUID values for every
  action/group `iconId`; resolve them with `alterios_ensure_project_icon_library`
  before the scenario dry-run/apply pair.

Existing report coverage includes `alterios_upsert_report`,
`alterios_patch_report_template`, `alterios_validate_report_project_base`,
`alterios_validate_stimulsoft_layout`, and
`alterios_validate_printable_render`. A report-tab scenario defaults to a
printable `type=report`; use `report_type=dashboard` only for an explicitly
requested analytical dashboard.

For script write scenarios:

- `alterios_upsert_script` must accept the UI-observed script types: `web`, `cron`, `manual`, `event`, `library`, and `diagram`;
- `cron` scripts require `config.cron` as a six-part string: `second minute hour day month week`;
- keep new `web` and `cron` research scripts inactive until endpoint/schedule behavior is explicitly approved and verified;
- `library` scripts are linked from consumer scripts through `librariesIds`; use global functions/constants for shared helpers unless live runtime evidence proves a different module format;
- manual execution uses `/api/scripts/execute-manual` with a saved script UUID, not runtime service names.
- configure a manual script in a form through
  `alterios_upsert_form_manual_script_action`, not an unvalidated raw form patch;
- select `page`, `element`, or `value` scope explicitly. For row values, keep
  the action in the existing menu or provide the project-local menu icon;
- pass semantic `argument_entity_ids` for joined records and let the tool
  resolve the actual populated `_idN` field. Never infer `_idN` from join order;
- require `action_view_entity_id` when a row action binds `__entity_id` and use
  `save_before_execute=true` when the script must see freshly saved form data.
- For selected-row side effects, use `alterios_fast_live_bulk_manual_script` or
  `alterios_fast_live_bulk_process`; require exact IDs, expected count, cached
  project health, a reviewed plan, and per-row readback.
- Never route destructive selected-row work through a generic service tool.
  Use `alterios_fast_live_bulk_delete` in `full/admin`; require expected content
  type, matching plan, dangerous environment gate, `allow_destructive=true`,
  and absence readback for every target. Pass a saved active `manual` delete
  script UUID that declares one `contentIds` argument; the reviewed plan freezes
  the script fingerprint and executes it through `/api/scripts/execute-manual`.

For view write scenarios:

- `alterios_upsert_view` must default to experimental/v2 by writing `settings.engineVersion = "v2"`.
- For user-facing experimental `table`, `reference`, and `list` previews, write
  `settings.title` as one populated view-field mname. Do not write a Mustache
  template there.
- For user-facing table/list/joined form surfaces, write human-readable
  `viewField.alias` values and verify form-viewer headers. Do not rely only on
  `displaying.fields.title`.
- Do not use `reference` as a standalone embedded list in a generated user
  form; it is a `ref source=view` selector source. A technical sample may use a
  help cell to explain this limitation.
- For `grid`, keep `desc` only after form-viewer UI evidence proves it renders
  field values, not raw mnames.
- Legacy/classic views require an explicit `allow_legacy_mode=true` argument and documented evidence that the target scenario needs that mode.
- Known frontend formats are `table`, `grid`, `list`, `leaflet`, `gantt`, `reference`, and `calendar`; do not invent other formats without UI/API evidence.
- `gantt` write scenarios must validate `defaultView` (`day`, `week`, `month`, `quarter`, `year`) and `date1.field`/`date2.field` before live write.
- `leaflet` write scenarios must validate `geoFields` after populated view fields are available; each geo field needs `name` and `markerIcons` (`default`, `img`, or `field`). Content values must be GeoJSON `Feature` objects for marker rendering.
- `calendar` write scenarios must set `title` and `startDate` before declaring the view complete; `endDate` and `bgColor` are optional but UI-verified.
- For system attributes such as `_id`, add the view field with the legacy add payload but save it with normalized `contentTypeId` and `contentAttribute`; remove null selector keys before save.
- For ordinary content source fields, call `alterios_upsert_view_field` with
  `content_type_field_id`; for `_id`, call it with `attribute="_id"`. After the
  add/save step, rely on populated readback for the real mname.
- For relation joins, do not declare success until populated fields and
  `get-data`/`get-data-simplified` prove the joined readable value is present.
- For relation joins embedded into forms, explicitly hide `_id`, helper ref
  fields, and generated related id fields such as `_id0`; include UI smoke for
  UUID leakage before accepting the write.
- After code or schema changes to MCP tools, restart the running MCP process before relying on live tool output or available arguments.
- Redaction must cover nested author/user/project metadata, emails, verification codes, tokens, passwords, cookies, api keys, participant ids, and support chat ids in audit/readback data.

## Boundaries

- Do not mix destructive/security flows into normal write tools.
- Do not mutate objects not marked as managed or explicitly targeted.
- Do not treat a successful save as verified without readback; use UI evidence when the change is user-facing.

## References

Read `references/source-map.md` before adding or changing a write tool.
