# Multi-Agent Project Management

This project uses a lightweight PM control loop so multi-agent work stays
visible, reviewable, and tied to verified outcomes.

## Roles

| Role | Responsibility | Writes Code |
|---|---|---:|
| Lead Engineer | Owns final integration, verification, commits, and pushes. | Yes |
| PM Agent | Maintains task status, stage boundaries, risks, decisions, and next actions. | No |
| Explorer Agent | Answers bounded codebase/API questions with evidence and file references. | No |
| Worker Agent | Implements a bounded task with an explicit file ownership scope. | Yes |
| Verifier Agent | Runs independent checks, reviews risk areas, and reports gaps. | No |

The Lead Engineer is accountable for the final repository state. Subagents can
recommend or patch, but their work is integrated only after review and checks.

## Control Artifacts

- `docs/project-status.md` is the single current status board.
- `docs/roadmap.md` is the durable delivery roadmap.
- `docs/discovery-plan.md` is the endpoint and inventory strategy.
- Commit messages mark completed slices.
- Verification evidence is summarized in status updates and final answers.

## Stage Gate

Every stage must have:

- scope and intended outcome;
- owner role;
- acceptance criteria;
- verification commands or live smoke checks;
- risks or blocked items;
- a commit hash after completion.

A task is not `Done` until its code/docs are committed and the relevant checks
pass, or the status explicitly says what could not be verified.

## Status Vocabulary

| Status | Meaning |
|---|---|
| Done | Implemented, verified, committed, and pushed. |
| In Progress | Currently being implemented or verified. |
| Next | Ready to start after the active task. |
| Blocked | Cannot move without user input or external state change. |
| Deferred | Valid work, intentionally postponed. |
| Risk | Known uncertainty that needs mitigation before release. |

## Multi-Agent Operating Rules

- Spawn agents only for bounded work that can run in parallel.
- Give each Worker Agent an explicit file or module ownership scope.
- Tell every Worker Agent that other changes may exist and must not be
  reverted.
- Keep PM Agent read-only unless explicitly asked to edit project documents.
- Close completed agents so no stale work remains open.
- Do not use subagent output as proof until the Lead Engineer verifies it.

## Reporting Cadence

At the end of every implementation stage, update `docs/project-status.md` with:

- completed work;
- commit hash;
- checks run and result;
- live-smoke result when applicable;
- new risks;
- next stage and first concrete tasks.

For long stages, update the status board after each meaningful mergeable slice.
