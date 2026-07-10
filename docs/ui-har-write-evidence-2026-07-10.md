# UI/HAR evidence по write-сценариям, 2026-07-10

Этот документ фиксирует две запрошенные проверки:

1. UI/HAR по user create/delete.
2. UI/HAR по cross-project native content-type transfer.

Raw HAR в текущем in-app browser connector недоступен: connector позволяет
читать UI/DOM/logs/assets, но не отдает raw network stream. Поэтому evidence
собрано как UI-visible flow + frontend bundle route snippets + API readback.
Если нужен именно `.har`, его надо экспортировать из DevTools или отдельного
network capture и прогнать через `alterios-ui-flow`.

## User create/delete

Scope:

- Base URL: `<alterios-base-url>`;
- UI route: `/control/users`;
- Created disposable user id: `47ac9730-2fa6-4cd2-8078-780f66bd009b`;
- Created disposable email: `codex-ui-user-1783683550097@example.invalid`;
- Created display name: `Codex UI Disposable`.

Frontend bundle routes:

| UI operation | Route |
|---|---|
| List users | `GET /api/users/listandcount` |
| Get user | `GET /api/users/one/{id}` |
| Create user | `POST /api/users` |
| Update user | update on `/api/users` |
| Delete user | remove on `/api/users` with `_id` |
| Invite project user | `POST /api/users/invite` |
| Remove project user | remove `/api/users/project` with `users: ids[]` |

UI flow:

| Step | Evidence |
|---|---|
| Open users list | `/control/users`, title `Пользователи`; list columns include `Эл. почта`, `Имя`, `Статус`, `Роль`, `Владелец`, `Последний вход`, `Дата регистрации` |
| Open add form | `/control/users/new?destination=%2Fcontrol%2Fusers`, title `Добавить пользователя` |
| Form fields | `Владелец`, `Имя`, `Фамилия`, `Эл. почта`, `Роль`, `Пароль`, `Повторите пароль`, `Ключ API`, `Активен`, `Супер пользователь` |
| Save without owner | UI/backend error: `ownerId must be a UUID` |
| Owner options | `ArtX`, `ВНИИМТ`, `СВК` |
| Save with owner `ArtX` | redirect to `/control/users/47ac9730-2fa6-4cd2-8078-780f66bd009b?...`, page title `Codex UI Disposable` |
| List readback | row shows test email, `Codex UI Disposable`, status `Заблокирован`, owner `ArtX`, date `10.07.2026` |
| Row actions | menu contains `edit / Редактировать` and `Удалить` |
| Delete confirmation | dialog: `Вы действительно хотите удалить «Codex UI Disposable»?`, buttons `Отмена`, `Принять` |
| Delete result | toast: `«Codex UI Disposable» удален`; row no longer appears |
| API cleanup | `remaining_matches=0` from `GET /api/users/listandcount` by id/email |

Вывод для MCP:

- `alterios_upsert_user` должен требовать или вычислять валидный `ownerId`.
- Disposable user create/delete можно считать live UI-verified в sandbox.
- Delete path остается dangerous/security и должен требовать dangerous gates,
  expected email/name и readback.

## Cross-project native content-type transfer

Scope:

- Source project: `<sandbox-project-id>`;
- Source content type: `572aedf5-500f-4538-82be-ae2170ff174a`;
- Name: `MCP Practice. Песочница`.

Frontend bundle routes:

| Operation | Route/payload |
|---|---|
| List local content types | `GET /api/content-types/listandcount` |
| List shared content types | `GET /api/content-types` with query `share=true` |
| Create content type | `POST /api/content-types/save` |
| Update content type | `PATCH /api/content-types/save` |
| Remove content type | remove `/api/content-types` with `_id` |
| Clone content type | `POST /api/content-types/clone` with body `{id: <content-type-id>}` |
| Find usages | `GET api/content-types/{id}/usage` |

API readback:

| Check | Result |
|---|---|
| Source flags | `share=true`, `shareCreating=true`, `shareEditing=true`, `shareDeleting=false` |
| Shared list | `GET /api/content-types?share=true` returned `282` shared content types |
| Source visible in shared list | `MCP Practice. Песочница`, same id, same source project id |
| Safe target project | не найден отдельный `sandbox/test/MCP` target project в `artx` |

Вывод для MCP:

- Native publication is flag-based: source type becomes visible to other
  projects through `share=true` and operation flags.
- Native transfer/copy is clone-based: target project context calls
  `POST /api/content-types/clone` with source content type id.
- Live clone must remain gated until there is an explicit target sandbox
  project and cleanup/readback plan. Выполнять clone в рабочий project без
  согласования нельзя, потому что это создает реальный content type.

## Применимость к другим Alterios

MCP можно применять к любым Alterios/LIMS instances, если они совместимы по
REST API, auth scheme и правам токена. Практический порядок:

1. Добавить отдельный profile в private dotenv.
2. Выполнить `alterios-discover --profiles --json`.
3. Выполнить `alterios-profile-smoke --json`.
4. Для нужного project снять read-only inventory.
5. Перед writes выполнить dry-run и readback в sandbox project.
6. Включать write gates только для проверенного profile/project.

Это не blind guarantee для любой версии Alterios. Route variants, auth headers,
project scoping и permissions могут отличаться, поэтому каждый instance должен
проходить profile smoke и route discovery перед production write.
