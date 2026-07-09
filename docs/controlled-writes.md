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

## Required Context

Controlled writes require explicit target context:

- `profile` must be passed to the tool call.
- `project_id` must be passed to the tool call.
- Do not rely on `ALTERIOS_PROFILE` or `ALTERIOS_<PROFILE>_PROJECT_ID` for
  write execution.

This is stricter than read-only tools. Read-only tools may use the configured
default project for repetitive inspection, but writes must name the target.

## Destructive Writes

Destructive operations, currently inferred from destructive service risk or
REST `DELETE`, require an additional flag:

- `allow_destructive=true`

Dry-run output remains available without this flag, so target IDs can be
reviewed before execution.

## Audit Shape

Every controlled write returns:

- `dry_run` - whether the request was only planned;
- `audit.status` - `dry_run` or `ready_to_execute`;
- `audit.write_enabled` - whether `ALTERIOS_MCP_ALLOW_WRITE=1` is active;
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
4. Keep destructive operations out of the first typed write candidate.
5. Add unit tests that prove dry-run is default and execution is gated.

The first typed write candidate should be low-risk and idempotent, with a clear
readback route and no workflow, notification, or delete side effects.

## Next Candidate

The current preferred first typed write candidate is
`alterios_update_content_fields` for one existing scratch/test content record.

Candidate contract:

- inputs: explicit `profile`, explicit `project_id`, `content_type_id`,
  `content_id`, `fields`, and optional `expected_current_fields`;
- preflight: read exactly one record by `_id` and verify its `contentTypeId`;
- field validation: reject unknown fields, protected fields, empty patches, and
  create/delete/workflow intent;
- execution route: a narrow content-save route with only `_id`,
  `contentTypeId`, and changed fields;
- verification: read the same content record again and compare the changed
  field values.

This candidate is not implemented in Stage 4. It is the starting point for the
next typed-write implementation stage.
