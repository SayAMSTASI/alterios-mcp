# Browser/UI Network Flow Discovery

Stage 5 records how the Alterios web UI actually talks to the backend before
typed write tools are built. The first delivered slice is a local analyzer for
HAR or JSON network dumps. It is read-only tooling: it does not open a browser,
does not call Alterios, and does not execute any write.

## Command

```powershell
python -m alterios_mcp.ui_flow .\capture.har `
  --profile vniimt `
  --project-id 40466687-b093-4d80-b4f2-ba0ed0245bfa `
  --scenario content-form-open `
  --json > artifacts\alterios-mcp\ui-flow-content-form-open.json
```

The installed console entrypoint is equivalent:

```powershell
alterios-ui-flow .\capture.har --scenario content-form-open --json
```

## Supported Inputs

- Browser HAR exports with `log.entries`.
- Plain JSON event lists with `method`, `url`, optional `headers`, `body`,
  `status`, and `response_body`.
- Single JSON event objects for small smoke checks.

Only `/api/...` routes are included in the output. Static assets and other
browser noise are counted as dropped non-API events.

## Output Contract

The analyzer writes one JSON object:

- `context` - profile, project id, scenario, and source path supplied by the
  operator.
- `flows` - ordered route evidence: method, path, query keys, sanitized URL,
  status, content type, classification, target id placeholders, request body
  shape, and response shape.
- `summary` - read route count, write-gated route count, unknown write-like
  routes, and successful write-like route count.
- `redaction_report` - counts of redacted headers, redacted fields, redacted
  query values, omitted bodies, dropped non-API events, and stable placeholder
  IDs.

Target identifiers are replaced with stable placeholders such as `<id:1>` so a
scenario can still be traced without preserving raw production IDs.

## Classification Rules

The classifier is fail-closed for mutating HTTP methods.

Confirmed read-only routes:

- `GET|POST /api/*/listandcount`
- `GET /api/contents...`
- `POST /api/views/v2/get-data`
- `POST /api/views/v2/get-data-simplified`
- `GET /api/file/list`
- `GET /api/v1/comments`
- generic `GET`, `HEAD`, and `OPTIONS` calls

Write-gated routes:

- `POST|PATCH|PUT /api/contents/save`
- `POST /api/file/upload/field`
- `POST /api/v1/comments`
- `POST /api/scripts/execute-manual`
- mutating `/api/tasks`, `/api/processes`, and `/api/diagrams` routes
- mutating admin/config routes under `/api/forms`, `/api/views`,
  `/api/scripts`, `/api/reports`, `/api/helps`, `/api/view-fields`, and
  `/api/view-entities`
- any unknown `POST`, `PUT`, `PATCH`, or `DELETE`

`DELETE /api/tasks/complete` is classified as a workflow side effect, not as a
generic delete, because it advances an operator task/process.

## Redaction Rules

The analyzer removes or replaces:

- `Authorization`, `Cookie`, `Set-Cookie`, `x-api-key`, and proxy auth headers;
- query/body keys such as token, password, secret, api key, and authorization;
- UI content values such as `fields`, comments, rich text, names, titles,
  filenames, and free text;
- multipart upload bodies.

It preserves route order, method/path, query key names, body structure, response
shape, status code, content type, classification, and stable placeholder IDs.

## Required Stage 5 Scenarios

Capture each scenario in a scratch/test project first:

1. Open a list and a content form without saving.
2. Save one scratch content record and read it back.
3. Upload a small test file through a file field and read metadata back.
4. Add and delete a scratch comment.
5. Execute a form action that calls a manual script in dry/test context.
6. Complete or route a scratch workflow task, with before/after task/process
   readbacks.

For each scenario, keep the raw HAR private, commit only sanitized JSON if it is
needed as evidence, and ensure `successful_write_like_route_count` matches the
approved scenario. For read-only scenarios it must be `0`.

## Next Typed Write Input

The first production-oriented typed write should be based on sanitized evidence
for `PATCH /api/contents/save` and should include:

- preflight read of the target content record;
- explicit `profile` and `project_id`;
- content type and field allowlist;
- dry-run diff;
- existing controlled write gate;
- readback verification after execution.
