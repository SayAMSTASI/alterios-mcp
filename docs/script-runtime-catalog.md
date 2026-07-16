# Каталог runtime-сервисов скриптов

Этап 3 превращает имена script-service в явный runtime catalog. Цель - сделать
каждый service видимым по назначению, аргументам, риску и безопасности probe
до добавления write-capable wrapper.

## Runtime services и manual scripts

Runtime service names, например `getTasks` и `createContent`, не являются
script UUID. Их нельзя отправлять в `/api/scripts/execute-manual`.

`/api/scripts/execute-manual` выполняет сохраненные Alterios scripts по UUID.
MCP client отклоняет non-UUID runtime service names, если configured endpoint
указывает на `/api/scripts/execute-manual`.

## Уровни риска

| Risk level | Значение |
|---|---|
| `read` | Read-only при вызове через совместимый runtime endpoint. |
| `write` | Создает или обновляет данные Alterios. Требует write gate и readback verification. |
| `destructive` | Удаляет данные. Требует отдельный dry-run и явный target review до добавления typed tool. |
| `workflow_side_effect` | Запускает, продвигает или переназначает workflow activity. Требует UI/API verification. |
| `external_side_effect` | Отправляет видимые пользователю notifications или другие внешние effects. |
| `audit_side_effect` | Пишет operational logs или похожее audit state. |

## Подтвержденный каталог

| Service | Категория | Меняет данные | Risk | Safe to probe | Key args |
|---|---|---:|---|---:|---|
| `getContents` | contents | Нет | `read` | Да | `query` |
| `getDependentContents` | contents | Нет | `read` | Да | `query` |
| `getTasks` | tasks | Нет | `read` | Да | `query` |
| `getViewData` | views | Нет | `read` | Да | `query` |
| `createContent` | contents | Да | `write` | Нет | `content` |
| `updateContent` | contents | Да | `write` | Нет | `content` |
| `deleteManyContents` | contents | Да | `destructive` | Нет | `args` |
| `createDependentContent` | contents | Да | `write` | Нет | `content`, `relatedContentId`, `relatedFieldId` |
| `startProcess` | processes | Да | `workflow_side_effect` | Нет | `diagramId`, `name`, `content`, `startMessageId`, `responseMessageId`, `params`, `contents` |
| `reassignTask` | tasks | Да | `workflow_side_effect` | Нет | `query` |
| `messageToAnotherProcess` | processes | Да | `workflow_side_effect` | Нет | `messageEventsIds`, `processesIds`, `diagramsIds`, `safeMode` |
| `uploadFile` | files | Да | `write` | Нет | `data`, `filename`, `fieldId`, `signal` |
| `notify` | notifications | Да | `external_side_effect` | Нет | `notification` |
| `writeLog` | logs | Да | `audit_side_effect` | Нет | `data`, `severity` |

## Probe policy

Read-only runtime services можно probe только если:

- `alterios_config` показывает compatible runtime endpoint template;
- выбранный profile и явный `project_id` проверены;
- request body использует documented body style для этого endpoint;
- probe arguments ограничены малыми limits и не содержат writes.

Если endpoint template равен `/api/scripts/execute-manual`, runtime service
probing считается blocked by configuration, а не failed API behavior.

## Заметки static scan

`alterios-static-scan` находит known services и likely service-like strings.
Likely strings могут быть переменными вроде `startPayload` или
`uploadResponse`; не переносите их в catalog, пока они не подтверждены как
реальные runtime services.

Каталог в `src/alterios_mcp/services.py` - source of truth для known runtime
services, которые показывает `alterios_service_catalog`.
