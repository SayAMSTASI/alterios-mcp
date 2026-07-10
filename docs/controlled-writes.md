# Controlled Writes

Stage 4 defines the safety contract for every Alterios operation that can
change state. It does not add a new production write workflow by itself; it
adds the policy and audit layer that future typed write tools must use.

## Default Behavior

Write-capable MCP tools are dry-run first.

By default, these tools return a write audit and do not send a request:

- `alterios_call_write_service`
- `alterios_execute_manual_script`
- `alterios_rest_write`

To execute a write, a caller must pass `dry_run=false` and the process must have
`ALTERIOS_MCP_ALLOW_WRITE=1`.

Use `alterios_write_safety_preflight` before broad REST writes when the route is
not already covered by a typed tool. It classifies the route and returns the
execution gates without sending a network request.

## Required Context

Controlled writes require explicit target context:

- `profile` must be passed to the tool call.
- `project_id` must be passed to the tool call.
- Do not rely on `ALTERIOS_PROFILE` or `ALTERIOS_<PROFILE>_PROJECT_ID` for
  write execution.

This is stricter than read-only tools. Read-only tools may use the configured
default project for repetitive inspection, but writes must name the target.

## Dangerous Writes

Dangerous operations are destructive or permission-changing writes. The current
classifier marks these as dangerous:

- destructive service risk, for example `deleteManyContents`;
- REST `DELETE`;
- REST writes under `/api/users`, `/api/user-groups`, `/api/usergroups`,
  `/api/roles`, `/api/security`, or `/api/permissions`.

Dangerous execution requires all normal write gates plus:

- `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`
- `allow_destructive=true`

Dry-run and `alterios_write_safety_preflight` output remain available without
these gates, so target IDs and route classification can be reviewed before
execution.

## Audit Shape

Every controlled write returns:

- `dry_run` - whether the request was only planned;
- `audit.status` - `dry_run` or `ready_to_execute`;
- `audit.write_enabled` - whether `ALTERIOS_MCP_ALLOW_WRITE=1` is active;
- `audit.dangerous_write_enabled` - whether
  `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1` is active;
- `audit.target.profile`;
- `audit.target.project_id`;
- `audit.operation` - name, kind, risk level, method/path, target IDs, redacted
  request summary, and readback requirement;
- `audit.required_checks` - checks expected before and after execution;
- `response` - `null` for dry-run or the redacted Alterios response after real
  execution.

Request fields named like tokens, passwords, API keys, or auth headers are
redacted from audit output.

## Future Typed Write Tools

Before adding a typed write tool:

1. Define the target object and required IDs.
2. Define validation rules and dry-run summary.
3. Define the readback route that proves the write happened.
4. Keep dangerous operations behind the separate dangerous gate and preflight.
5. Add unit tests that prove dry-run is default and execution is gated.

Typed tools should be low-risk or explicitly classified, with a clear readback
route and no hidden workflow, notification, permission, or delete side effects.

## Security/Destructive Candidate

The dangerous-flow candidate must start read-only:

- run `alterios_write_safety_preflight` for the exact route;
- verify the target profile and project with `alterios_config`;
- collect target IDs through safe reads or UI/HAR capture;
- execute only in a dedicated sandbox with both write env gates enabled;
- record API readback and UI-visible evidence when permissions or deletes are
  user-facing.

Do not use generic REST writes for production security or delete work until the
same route has a typed tool with target checks and readback.
