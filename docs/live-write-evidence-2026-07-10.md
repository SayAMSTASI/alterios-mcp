# Live write evidence, 2026-07-10

Цель: проверить, что write-first часть MCP реально умеет выполнять запись в
Alterios, а не только строить dry-run. Проверка выполнялась в тестовом проекте
ART X.

## Target

- Profile: `artx`.
- Project: `4e247a6b-55ef-4665-b88c-3c156fee19ba`.
- Sandbox content type: `572aedf5-500f-4538-82be-ae2170ff174a`,
  `MCP Practice. Песочница`.
- Write gates for normal writes: `ALTERIOS_MCP_ALLOW_WRITE=1`.
- Write gates for security/destructive writes:
  `ALTERIOS_MCP_ALLOW_WRITE=1`, `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`,
  `allow_destructive=true`.

Секреты, токены, cookies, пароли и raw authorization headers в evidence не
сохраняются.

## Content type publish flags

Native save route is verified through the typed tool
`alterios_upsert_content_type` and API route `/api/content-types/save`.

Observed frontend bundle evidence:

- content type create: `POST /api/content-types/save`;
- content type update: `PATCH /api/content-types/save`;
- model fields include `share`, `shareCreating`, `shareEditing`,
  `shareDeleting`;
- UI toggles directly bind to `shareCreating`, `shareEditing`,
  `shareDeleting`.

Live execution:

| Step | Result |
|---|---|
| Before readback | `share=false`, `shareCreating=false`, `shareEditing=false`, `shareDeleting=false` |
| Dry-run | Planned only `share`, `shareCreating`, `shareEditing` changes |
| Live write | `POST /api/content-types/save`, status `201` |
| Final readback | `share=true`, `shareCreating=true`, `shareEditing=true`, `shareDeleting=false` |

`shareDeleting` is intentionally left `false`: this confirms publication for
visibility/create/edit without expanding destructive cross-project behavior.

Windows/PowerShell note: one live attempt passed Cyrillic through a lossy
console pipe and temporarily changed the name suffix to question marks. The
same typed tool immediately restored the name using Unicode-safe input, and
final readback confirms `MCP Practice. Песочница`.

This is native content type flag publishing. It is not yet proof of a separate
cross-project "publish/copy to project" command. The cross-project native flow
still requires UI/HAR evidence for route, method, payload shape, and target
readback.

## Role create/update/delete

Typed tools:

- `alterios_upsert_role`;
- `alterios_delete_role`.

Live cycle:

| Step | Route | Status | Evidence |
|---|---|---:|---|
| Create dry-run | `POST /api/roles` | n/a | `risk=security`, `kind=role` |
| Create live | `POST /api/roles` | `201` | Created/read back `9619ddfd-3f39-48d7-bc3f-791f4149e900` |
| Update dry-run | `PATCH /api/roles/9619ddfd-3f39-48d7-bc3f-791f4149e900` | n/a | Expected name matched |
| Update live | `PATCH /api/roles/9619ddfd-3f39-48d7-bc3f-791f4149e900` | `200` | Readback id/name matched |
| Delete dry-run | `DELETE /api/roles/9619ddfd-3f39-48d7-bc3f-791f4149e900` | n/a | Expected name matched |
| Delete live | `DELETE /api/roles/9619ddfd-3f39-48d7-bc3f-791f4149e900` | `200` | Delete readback: `deleted=true`, `body=null` |
| Cleanup scan | `GET /api/roles/listandcount` | `200` | Remaining matching roles: `0` |

## User group create/update/delete

Typed tools:

- `alterios_upsert_user_group`;
- `alterios_delete_user_group`.

Live cycle:

| Step | Route | Status | Evidence |
|---|---|---:|---|
| Create dry-run | `POST /api/user-groups` | n/a | `risk=security`, `kind=user_group` |
| Create live | `POST /api/user-groups` | `201` | Created/read back `a4307928-fbe3-4447-89b2-889b884f7623` |
| Update dry-run | `PATCH /api/user-groups/a4307928-fbe3-4447-89b2-889b884f7623` | n/a | Expected name matched |
| Update live | `PATCH /api/user-groups/a4307928-fbe3-4447-89b2-889b884f7623` | `200` | Readback id/name matched |
| Delete dry-run | `DELETE /api/user-groups/a4307928-fbe3-4447-89b2-889b884f7623` | n/a | Expected name matched |
| Delete live | `DELETE /api/user-groups/a4307928-fbe3-4447-89b2-889b884f7623` | `200` | Delete readback: `deleted=true`, `body=null` |
| Cleanup scan | `GET /api/user-groups/listandcount` | `200` | Remaining matching groups: `0` |

## User create/delete status

Typed tools exist:

- `alterios_upsert_user`;
- `alterios_delete_user`.

Observed frontend bundle evidence:

- `createUser(a)` calls `POST /api/users`;
- `updateUser(a)` calls update on `/api/users`;
- `removeUser(a)` calls remove on `/api/users` with `_id`;
- project invite uses a separate `POST /api/users/invite` route.

Live attempts:

| Payload class | Result |
|---|---|
| Basic disabled sandbox user without password | `HTTP 500`: key argument received `undefined` |
| Disabled sandbox user with `password` and `repassword` | Same `HTTP 500` |
| Cleanup scan by sandbox email prefix | Remaining matching users: `0` |

Interpretation: the typed tool route is correct, but user creation requires an
additional backend/UI contract not visible from the current static bundle
snippet. Until a real UI/HAR create-user capture is available, user create/delete
must stay guarded and treated as not live-verified. User delete itself cannot be
live-verified without a successfully created disposable user.

## Safety fixes from this run

Two safety issues were corrected after live practice:

- `repassword`, `passwordRecoverCode`, `clientSecret`, and similar key names are
  now redacted by the common MCP redactor.
- security upsert audit now strips readback metadata before calculating
  `target_ids`, so `authorId`, `updatedBy`, `version`, and similar fields do not
  pollute dangerous-write review.

Targeted tests:

- `tests/test_write_control.py::test_dry_run_audit_redacts_sensitive_request_values`
- `tests/test_write_control.py::test_security_upsert_audit_strips_readback_metadata_target_ids_without_real_network`

Full verification after documentation/code updates:

- `pytest`: 122 passed;
- `git diff --check`: OK;
- `py_compile` for `src/alterios_mcp/client.py` and
  `src/alterios_mcp/server.py`: OK;
- changed-file secret scan: no matches for real token/password patterns;
- final live readback: sandbox type name and publish flags are correct,
  remaining Codex test roles/user groups/users are all `0`.
