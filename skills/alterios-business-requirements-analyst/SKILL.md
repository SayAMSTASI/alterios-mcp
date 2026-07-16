---
name: alterios-business-requirements-analyst
description: Formalize Alterios/LIMS business requests into developer-ready BRD, TRZ, technical task, or постановка artifacts. Use when Codex must turn user goals into requirements, scenarios, entities, fields, views, forms, scripts, BPMN, reports, roles, acceptance criteria, implementation handoffs, or documentation-ready specifications before Alterios MCP writes.
---

# Alterios Business Requirements Analyst

## Overview

Use this skill before building or changing Alterios modules when the request is still a business goal, an informal idea, or a partially specified workflow. The output must be a structured постановка/ТРЗ that another agent or developer can implement and verify.

## Workflow

1. Identify the object of work: project, module, material type, view, form, process, report, integration, instruction, or cross-project transfer.
2. Separate verified facts from assumptions. Use project inventory, screenshots, existing docs, and user text as sources; mark unknown values as `Требует уточнения`.
3. Define the business outcome, users, roles, permissions, data ownership, and operational constraints.
4. Convert the request into scenarios with preconditions, steps, expected result, errors, and acceptance criteria.
5. Build the Alterios implementation map:
   - content/material types, fields, field types, required/default values, relation targets;
   - views, view entities, joins, view fields, filters, sorts, display names, and source fields;
   - forms, tabs, rows, cells, actions, listeners, no-gap layout, F-pattern placement;
   - scripts, BPMN user tasks, script tasks, listeners, services, args, and side effects;
   - reports, Project Database source views, openId/current-record context, layout/render risks;
   - users, groups, roles, menu groups, icons, and action placement.
6. For any planned live write, require `alterios_live_task_preflight` first. Continue only when it returns `summary.status=ready`; use `alterios_project_health` as the detailed forms/views/scripts/BPMN/reports diagnostic inside or after the preflight.
7. Hand off scoped work to PM, Data Model, View Builder, Form Surface, Script/BPMN, Report, Write Tool, Documentation Scribe, and Safety Verifier agents.

## View Requirements

When a requirement touches представления, specify more than the visible table name:

- source content type and each `viewEntity`;
- relation field for parent-child lists, not only a verbal "linked records" label;
- field list with user label, source `mname`, alias, order, visibility, and whether the field is used in form/report/script;
- filters and sorts, including current-record filters through `openId` and `dataId: [openId]`;
- joins/entity chain and how it will be validated through `view_fields_populated` and `get-data`/`get-data-simplified`;
- expected row examples and empty-state behavior.

## Output Structure

Produce one of these artifacts depending on the request:

### Постановка Для Разработчика

- Goal and business context.
- Scope and out of scope.
- Actors, roles, permissions.
- Data model and object map.
- Scenario list with acceptance criteria.
- Implementation map by Alterios entities and MCP tools.
- Test data, readback checks, UI/render checks.
- Risks, rollback notes, open questions.

### ТРЗ/ТЗ Draft

Use ГОСТ 34 for automated-system level requirements and ГОСТ 19 for program/software-level artifacts when a formal baseline is needed. Do not invent contractual fields, document codes, customer names, dates, or acceptance boards.

Recommended sections:

- basis and sources;
- purpose and goals;
- object/process characteristics;
- functional requirements;
- data and information requirements;
- UI/form/report requirements;
- script/BPMN/process requirements;
- security and access requirements;
- documentation requirements;
- acceptance and verification procedure;
- appendices and unresolved questions.

## Boundaries

- Do not execute writes. This skill prepares requirements and handoffs.
- Do not mark a requirement as verified without source evidence.
- Do not replace the Documentation Scribe. For final ГОСТ/ЕСПД formatting, use `gost-documentation-builder` and the document-rendering skill when DOCX is needed.
- Do not hide ambiguity. Put unknowns into open questions or acceptance risks.

## References

Read `references/source-map.md` before drafting a project-specific постановка or TRZ.
