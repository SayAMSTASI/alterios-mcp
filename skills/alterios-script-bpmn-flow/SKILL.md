---
name: alterios-script-bpmn-flow
description: Map and verify Alterios/LIMS scripts, form actions, BPMN diagrams, process starts, user tasks, script tasks, listeners, service tasks, camunda:formKey links, task completion, manual/event/diagram script types, passed args, and data side effects. Use when scripts and diagrams affect content, tasks, notifications, logs, or process routing.
---

# Alterios Script BPMN Flow

Use this skill when behavior crosses forms, scripts, BPMN, tasks, and data changes. Treat it as a flow-mapping and side-effect skill before write implementation.

## Workflow

1. Separate manual scripts, event scripts, and diagram scripts.
2. Map form actions to scripts and record the args each action passes.
3. Parse BPMN for `userTask`, `scriptTask`, listeners, service tasks, sequence flows, and `camunda:formKey`.
4. Link user tasks to forms and script/service tasks to script references or runtime services.
5. Classify side effects: create/update/delete content, start process, complete/reassign task, notify, write log, files, comments, report output.
6. Keep UI `start_process` actions separate from script runtime `startProcess` service calls; they have different evidence and args.
7. For sandbox writes, verify process start, active tasks, task completion, and resulting content/task state.

## Safety

- Do not execute manual scripts until profile, project, script id, args, and expected side effects are understood.
- Keep saved script UUIDs separate from runtime service names.
- Mark destructive or security-sensitive side effects before any write tool is used.

## Args Checklist

- `manual_script` action: saved script UUID, action args, current record context, save order if fresh data is required.
- UI `start_process` action: diagram/process target, content/current record context, form params, expected userTask/formKey.
- Runtime `startProcess` service: service-call payload inside script code, cataloged risk, and service readback.

## References

Read `references/source-map.md`, then load the linkage matrix and runtime catalog relevant to the requested flow.
