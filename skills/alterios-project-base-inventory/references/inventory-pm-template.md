# Inventory PM Handoff Template

Use this after a read-only inventory run or when planning a new project inventory.

```text
Stage:
Owner:
Profile:
Project ID:
Config source:
Commands:
Artifacts:
Verified counts:
Read errors:
Route gaps:
Assumptions:
Risks:
Next:
Status update needed:
```

Rules:

- Do not include tokens, cookies, private dotenv values, or raw auth headers.
- Keep read errors separate from successful counts.
- Mark the stage `Done` only after commands actually ran and artifacts/readback were checked.
- Use a project-scoped artifact directory for exploratory inventories.
