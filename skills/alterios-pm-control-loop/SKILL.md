---
name: alterios-pm-control-loop
description: Manage Alterios MCP multi-agent delivery stages, project status, backlog, risks, acceptance criteria, verification evidence, next actions, and agent handoffs. Use when planning or updating work across PM, explorer, data model, view, form, icon, script/BPMN, report, write-tool, verifier, and skill-curator roles.
---

# Alterios PM Control Loop

Use this skill to keep multi-agent Alterios MCP work visible, scoped, and tied to verified outcomes.

## Workflow

1. Define the active stage and one concrete outcome.
2. Assign owner roles and narrow scopes.
3. State acceptance criteria before implementation.
4. Track status as Done, In Progress, Next, Blocked, Deferred, or Risk.
5. Require artifacts and verification commands from every agent.
6. Update the private Gitea work item or local project status after a meaningful mergeable slice.
7. Keep roadmap changes separate from current status updates.
8. For read-only planning or discovery that has not run yet, return a PM handoff instead of marking repo status `Done`.
9. Before a scenario apply, require a private work item reference and published
   agent handoff references in `delivery_evidence`; local narrative is not a
   substitute for traceable evidence.
10. Move a task to Done only after runtime freshness, UX-contract, automated
    tests, report PDF evidence where applicable, git push, and readback evidence
    are recorded.

## Handoff Format

Use this format when collecting agent results:

```text
Agent:
Scope:
Inputs:
Findings:
Artifacts:
Verification:
Risks:
Next:
```

## References

Read `references/source-map.md`, then update the relevant status or roadmap document.
