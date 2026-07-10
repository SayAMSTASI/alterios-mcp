# Live evidence записи, 2026-07-10

Цель: проверить, что write-first часть MCP реально умеет выполнять запись в
Alterios, а не только строить dry-run. Проверка выполнялась в тестовом проекте
ART X.

## Цель проверки

- Profile: `artx`.
- Project: `4e247a6b-55ef-4665-b88c-3c156fee19ba`.
- Sandbox content type: `572aedf5-500f-4538-82be-ae2170ff174a`,
  `MCP Practice. Песочница`.
- Write gate для обычных writes: `ALTERIOS_MCP_ALLOW_WRITE=1`.
- Write gates для security/destructive writes:
  `ALTERIOS_MCP_ALLOW_WRITE=1`, `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`,
  `allow_destructive=true`.

Secrets, tokens, cookies, passwords и raw authorization headers в evidence не
сохраняются.

## Publication flags типа материалов

Native save route проверен через typed tool `alterios_upsert_content_type` и
API route `/api/content-types/save`.

Frontend bundle evidence:

- create content type: `POST /api/content-types/save`;
- update content type: `PATCH /api/content-types/save`;
- model fields: `share`, `shareCreating`, `shareEditing`, `shareDeleting`;
- UI toggles напрямую bind к `shareCreating`, `shareEditing`,
  `shareDeleting`.

Live execution:

| Шаг | Результат |
|---|---|
| Readback до записи | `share=false`, `shareCreating=false`, `shareEditing=false`, `shareDeleting=false` |
| Dry-run | Запланированы только изменения `share`, `shareCreating`, `shareEditing` |
| Live write | `POST /api/content-types/save`, status `201` |
| Финальный readback | `share=true`, `shareCreating=true`, `shareEditing=true`, `shareDeleting=false` |

`shareDeleting` намеренно оставлен `false`: это подтверждает публикацию для
видимости/create/edit без расширения destructive cross-project behavior.

Это native content type flag publishing. Это не является отдельной командой
копирования типа в другой проект.

## Cross-project native transfer evidence

Frontend bundle и API readback подтверждают следующую native-механику:

| Слой | Evidence |
|---|---|
| Source publish | `share=true`, `shareCreating=true`, `shareEditing=true`, `shareDeleting=false` на sandbox type |
| Shared list | `GET /api/content-types?share=true` возвращает опубликованный `MCP Practice. Песочница` |
| UI/source route | project UI route для типов материалов: `/workspace/:id/content-types` |
| Clone route | frontend service вызывает `POST /api/content-types/clone` с body `{id: <content-type-id>}` |
| Display rule | `allContentTypes()` добавляет `projectName` к имени shared type, если source project отличается |

Live clone в другой проект не выполнялся: в `artx` не найден отдельный проект с
safe sandbox/test/MCP названием, отличный от исходного project. Клонирование
создает реальный content type в target project, поэтому без согласованного
target sandbox это остается gated operation.

## Role create/update/delete

Typed tools:

- `alterios_upsert_role`;
- `alterios_delete_role`.

Live cycle:

| Шаг | Route | Status | Evidence |
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

| Шаг | Route | Status | Evidence |
|---|---|---:|---|
| Create dry-run | `POST /api/user-groups` | n/a | `risk=security`, `kind=user_group` |
| Create live | `POST /api/user-groups` | `201` | Created/read back `a4307928-fbe3-4447-89b2-889b884f7623` |
| Update dry-run | `PATCH /api/user-groups/a4307928-fbe3-4447-89b2-889b884f7623` | n/a | Expected name matched |
| Update live | `PATCH /api/user-groups/a4307928-fbe3-4447-89b2-889b884f7623` | `200` | Readback id/name matched |
| Delete dry-run | `DELETE /api/user-groups/a4307928-fbe3-4447-89b2-889b884f7623` | n/a | Expected name matched |
| Delete live | `DELETE /api/user-groups/a4307928-fbe3-4447-89b2-889b884f7623` | `200` | Delete readback: `deleted=true`, `body=null` |
| Cleanup scan | `GET /api/user-groups/listandcount` | `200` | Remaining matching groups: `0` |

## User create/delete через UI

Typed tools существуют:

- `alterios_upsert_user`;
- `alterios_delete_user`.

Frontend bundle evidence:

- `createUser(a)` вызывает `POST /api/users`;
- `updateUser(a)` вызывает update на `/api/users`;
- `removeUser(a)` вызывает remove на `/api/users` с `_id`;
- project invite использует отдельный `POST /api/users/invite`.

UI evidence:

| Шаг | Результат |
|---|---|
| Открыт список | `/control/users`, title `Пользователи` |
| Открыта форма | `/control/users/new?destination=%2Fcontrol%2Fusers`, поля: `owner`, `firstName`, `lastName`, `email`, `role`, `password`, `repassword`, `apiKey`, `isActive`, `superuser` |
| Первая попытка без owner | UI/backend error: `ownerId must be a UUID` |
| Выбор owner | dropdown options: `ArtX`, `ВНИИМТ`, `СВК`; выбран `ArtX` |
| Create | создан disabled disposable user, redirect на `/control/users/47ac9730-2fa6-4cd2-8078-780f66bd009b?...`, title `Codex UI Disposable` |
| Список | строка содержит email `codex-ui-user-1783683550097@example.invalid`, status `Заблокирован`, owner `ArtX` |
| Row menu | actions: `edit / Редактировать`, `Удалить` |
| Delete confirm | dialog: `Вы действительно хотите удалить «Codex UI Disposable»?`, buttons `Отмена`, `Принять` |
| Delete result | toast: `«Codex UI Disposable» удален`, строка исчезла из UI |
| API cleanup readback | `GET /api/users/listandcount`, `remaining_matches=0` по email и id |

Вывод: UI-контракт для user create/delete снят. Для корректного create обязателен
`ownerId`; password/repassword сами по себе недостаточны. Delete выполняется из
row menu списка, а не с edit page.

## Safety fixes из этого этапа

- `repassword`, `passwordRecoverCode`, `clientSecret` и похожие key names
  скрываются common MCP redactor.
- security upsert audit удаляет readback metadata перед расчетом `target_ids`,
  поэтому `authorId`, `updatedBy`, `version` и похожие fields не попадают в
  dangerous-write review.

Targeted tests:

- `tests/test_write_control.py::test_dry_run_audit_redacts_sensitive_request_values`;
- `tests/test_write_control.py::test_security_upsert_audit_strips_readback_metadata_target_ids_without_real_network`.

Full verification после documentation/code updates:

- `pytest`: 122 passed;
- `git diff --check`: OK;
- `py_compile` для `src/alterios_mcp/client.py` и
  `src/alterios_mcp/server.py`: OK;
- changed-file secret scan: no matches for real token/password patterns;
- final live readback: sandbox type name и publish flags корректны,
  remaining Codex test roles/user groups/users равны `0`.
