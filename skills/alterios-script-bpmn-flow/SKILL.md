---
name: alterios-script-bpmn-flow
description: Map and verify Alterios/LIMS scripts, form actions, BPMN diagrams, process starts, user tasks, script tasks, listeners, service tasks, camunda:formKey links, task completion, web/cron/manual/event/library/diagram script types, passed args, and data side effects. Use when scripts and diagrams affect content, tasks, notifications, logs, or process routing.
---

# Alterios Script BPMN Flow

Use this skill when behavior crosses forms, scripts, BPMN, tasks, and data changes. Treat it as a flow-mapping and side-effect skill before write implementation.

## Workflow

1. Separate UI script types: `web`, `cron`, `manual`, `event`, `library`, and `diagram`.
2. Map form actions to scripts and record the args each action passes.
3. Parse BPMN for `userTask`, `scriptTask`, listeners, service tasks, sequence flows, and `camunda:formKey`.
4. Link user tasks to forms and script/service tasks to script references or runtime services.
5. Classify side effects: create/update/delete content, start process, complete/reassign task, notify, write log, files, comments, report output.
6. Keep UI `start_process` actions separate from script runtime `startProcess` service calls; they have different evidence and args.
7. For sandbox writes, verify process start, active tasks, task completion, and resulting content/task state.
8. For `cron`, verify `config.cron` as a six-part string: `second minute hour day month week`. Keep experimental cron scripts inactive until the schedule and side effects are approved.
9. For `library`, verify the consumer script has `librariesIds` and that runtime-visible helpers are written as global functions/constants unless UI/API evidence proves another module format.
10. For `web`, verify endpoint exposure separately before treating the script as callable from outside the project.
11. For form manual-script actions, distinguish `formActionContainers` (page),
    `cellActionContainers` (element), and `valueActionContainers` (row value).
    Do not copy the same identifier binding between these scopes without view
    and UI readback.
12. Resolve joined-record identifiers from populated view fields. `_id`, `_id0`,
    `_id5`, and similar keys are real view-field `mname` values for specific
    `entityId` values, not stable ordinal conventions.
13. Prefer `alterios_upsert_form_manual_script_action` over raw form JSON. Pass
    `argument_entity_ids` when the script needs an entity from a joined view;
    let the tool resolve the corresponding `_idN` provider key.

## Safety

- Do not execute manual scripts until profile, project, script id, args, and expected side effects are understood.
- Keep saved script UUIDs separate from runtime service names.
- Mark destructive or security-sensitive side effects before any write tool is used.
- Do not activate new cron or web scripts during research unless the user explicitly asks for live schedule or external endpoint behavior.

## Args Checklist

- `manual_script` action: saved script UUID, action args, current record context, save order if fresh data is required.
- Manual form action contract: `argumentsConfig.type=context` and
  `argumentsConfig.args.<argument>.dataProviderKey=<provider>`.
- `__entity_id`: current action entity; for a row value action it requires an
  explicit `action_view_entity_id` so the target row entity is unambiguous.
- `openId`: route/open-form record context. It is not interchangeable with a
  related row identifier.
- `_id`/`_idN`: a populated view-field mname. Resolve it by `entityId` before
  writing the action and keep the technical column hidden from users.
- If the script needs a newly saved record, keep the action sequence
  `submit_all -> manual_script -> routing/redirect`.
- Verify that the script is `type=manual`, active, and that the binding keys are
  compatible with `script.config.arguments`. Extra or omitted declared keys are
  review warnings; an empty binding or missing view provider is blocking.
- Saved script metadata: `type`, `active`, `config.cron`, `config.arguments`, `librariesIds`, `share`, body marker, and expected side effects.
- UI `start_process` action: diagram/process target, content/current record context, form params, expected userTask/formKey.
- Runtime `startProcess` service: service-call payload inside script code, cataloged risk, and service readback.

## References

Read `references/source-map.md`, then load the linkage matrix and runtime catalog relevant to the requested flow.
