---
name: alterios-project-base-inventory
description: Inventory Alterios/LIMS project base objects and route coverage. Use when Codex must inspect projects, content types, fields, views, forms, scripts, BPMN diagrams, reports, files, comments, users/groups, tasks, processes, object counts, route shapes, or read-only discovery for one or more Alterios profiles/projects before making changes.
---

# Alterios Project Base Inventory

Use this skill before designing or changing an Alterios project surface. Keep it read-only unless another skill or explicit user request moves the work into a guarded write stage.

## Workflow

1. Identify the Alterios `profile` and explicit `project_id`; do not treat a profile as a project.
2. Verify configuration without printing secrets.
3. Inventory instance-level projects first, then project-level objects.
4. Capture counts, ids, names, route/method scope, required params, pagination, filters, response shape, and common errors.
5. Save or update reproducible evidence only after checking that generated artifacts contain no secrets.

## Commands

Prefer existing tools and CLIs from this repo:

```powershell
.\.venv\Scripts\alterios-discover.exe --profile secondary --project-id <project_id> --json
.\.venv\Scripts\alterios-deep-inventory.exe --profile secondary --project-id <project_id> --out-dir artifacts\inventories\secondary\<project_id>
```

Use MCP tools for targeted reads when available; use generic REST reads only to fill a documented route gap.
Use `--out-dir docs` only when intentionally refreshing canonical repo matrices for the current reference project.

## Evidence Rules

- Record live read errors separately from successful counts.
- Keep `profile`, `project_id`, object ids, object names, and non-secret route facts.
- Redact tokens, cookies, auth headers, passwords, and API keys.
- If UI behavior matters, inventory API first, then verify through browser/UI evidence.

## References

Read `references/source-map.md` first, then open only the listed project docs relevant to the current entity family.
Use `references/inventory-pm-template.md` when the inventory result must be handed off to PM status.
