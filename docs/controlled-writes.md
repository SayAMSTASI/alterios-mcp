# Управляемая запись в Alterios

Этап 4 задает safety contract для каждой операции Alterios, которая может
изменить состояние. Сам по себе он не добавляет новый production workflow
записи; он добавляет policy и audit layer, который обязаны использовать typed
write tools.

## Поведение по умолчанию

Все write-capable MCP tools сначала работают как dry-run.

По умолчанию эти инструменты возвращают write audit и не отправляют запрос:

- `alterios_call_write_service`;
- `alterios_execute_manual_script`;
- `alterios_rest_write`;
- typed metadata/data/form/report tools, например `alterios_upsert_form`;
- typed security tools, например `alterios_upsert_user` и
  `alterios_delete_role`.

Чтобы реально выполнить запись, caller должен передать `dry_run=false`, а
процесс должен быть запущен с `ALTERIOS_MCP_ALLOW_WRITE=1`.

Перед broad REST writes используйте `alterios_write_safety_preflight`, если
route еще не покрыт typed tool. Он классифицирует route и возвращает нужные
execution gates без сетевого запроса.

## Обязательный контекст

Controlled writes требуют явный target context:

- `profile` передается в tool call;
- `project_id` передается в tool call;
- write execution не должен полагаться на `ALTERIOS_PROFILE` или
  `ALTERIOS_<PROFILE>_PROJECT_ID`.

Это строже, чем read-only tools. Read-only tools могут использовать default
project для повторной инвентаризации, но writes всегда должны явно называть
цель.

## Dangerous writes

Dangerous operations - это destructive или permission-changing writes.
Текущий классификатор считает dangerous:

- destructive service risk, например `deleteManyContents`;
- REST `DELETE`;
- REST writes под `/api/users`, `/api/user-groups`, `/api/usergroups`,
  `/api/roles`, `/api/security` или `/api/permissions`.

Dangerous execution требует все обычные write gates плюс:

- `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`;
- `allow_destructive=true`.

Dry-run и `alterios_write_safety_preflight` доступны без этих gates, поэтому
target IDs и route classification можно проверить до выполнения.

Для массового удаления content rows generic `alterios_call_write_service` не
используется. Применяется `alterios_fast_live_bulk_delete`: точные IDs,
`expected_count` и `expected_content_type_id` сохраняются в dry-run плане,
apply сверяет `plan_id`, а readback подтверждает отсутствие каждой записи.

## Форма audit

Каждая controlled write возвращает:

- `dry_run` - была ли операция только запланирована;
- `audit.status` - `dry_run` или `ready_to_execute`;
- `audit.write_enabled` - включен ли `ALTERIOS_MCP_ALLOW_WRITE=1`;
- `audit.dangerous_write_enabled` - включен ли
  `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`;
- `audit.target.profile`;
- `audit.target.project_id`;
- `audit.operation` - name, kind, risk level, method/path, target IDs,
  redacted request summary и readback requirement;
- `audit.required_checks` - ожидаемые проверки до и после выполнения;
- `response` - `null` для dry-run или redacted Alterios response после
  реального выполнения.

Поля запроса с tokens, passwords, repeated passwords, recovery codes,
secrets, API keys и auth headers скрываются из audit output.

## Правила добавления typed write tool

Перед добавлением typed write tool:

1. Определить target object и обязательные IDs.
2. Определить validation rules и dry-run summary.
3. Определить readback route, который доказывает выполнение записи.
4. Оставить dangerous operations за отдельным dangerous gate и preflight.
5. Добавить unit tests, которые доказывают dry-run по умолчанию и gated
   execution.

Typed tools должны быть narrow, с понятным readback route и без скрытых
workflow, notification, permission или delete side effects.

## Security/destructive typed tools

Security/destructive flows имеют typed wrappers для первого admin slice:

- `alterios_list_users`, `alterios_get_user`, `alterios_upsert_user`,
  `alterios_delete_user`;
- `alterios_list_user_groups`, `alterios_get_user_group`,
  `alterios_upsert_user_group`, `alterios_delete_user_group`;
- `alterios_list_roles`, `alterios_get_role`, `alterios_upsert_role`,
  `alterios_delete_role`.

Эти tools остаются dangerous. Typed wrapper нужен для target checks,
route-specific audit, expected-name/email checks и readback. Он не отменяет
dangerous gate.

Dangerous-flow run начинается read-only:

- выполнить `alterios_write_safety_preflight` для точного route;
- проверить target profile и project через `alterios_config`;
- получить target IDs через safe reads или UI/HAR capture;
- выполнять только в dedicated sandbox с обоими write env gates;
- записать API readback и UI-visible evidence, если permissions/delete видимы
  пользователю.

Для users, user groups, roles и delete flows используйте typed security tools,
а не generic REST writes. В production их нельзя выполнять без dry-run target,
rollback/readback plan и отдельной проверки.

## Доказательства от 2026-07-10

- role create/update/delete live-verified с dry-run, dangerous gates, live
  execution, delete readback и cleanup scan;
- user-group create/update/delete live-verified с dry-run, dangerous gates,
  live execution, delete readback и cleanup scan;
- disposable user create/delete live-verified через UI: форма требует `ownerId`,
  после выбора целевого владельца создается disabled user, delete выполняется из
  row menu, cleanup API readback возвращает `remaining_matches=0`;
- content type publication flags live-verified через `/api/content-types/save`;
- cross-project content type transfer имеет route evidence:
  `GET /api/content-types?share=true` и `POST /api/content-types/clone`, но
  live clone не выполнялся без отдельного target sandbox project.
