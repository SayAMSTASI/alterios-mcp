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

## Ручной скрипт как действие формы

Ручной скрипт в форме хранится как действие `manual_script`, где `_id` - UUID
сохраненного скрипта, а `argumentsConfig` связывает аргументы скрипта с
провайдерами данных формы:

```json
{
  "_id": "<script UUID>",
  "name": "Обработка записи",
  "type": "manual_script",
  "argumentsConfig": {
    "type": "context",
    "args": {
      "contentId": {"dataProviderKey": "__entity_id"}
    }
  }
}
```

Поверхности действий различаются:

- `formActionContainers` - действие страницы;
- `cellActionContainers` - действие элемента формы;
- `valueActionContainers` - действие значения/строки списка, обычно вложенное
  в `type=menu`;
- `__entity_id` - текущая сущность действия;
- `openId` - идентификатор из маршрута открытой формы;
- `_id`, `_id0`, `_id5` - реальные `mname` ID-полей сущностей представления;
- обычный `field_*`/mname - значение поля формы или представления.

Нельзя выбирать `_idN` по номеру или переносить его между представлениями.
Нужно прочитать populated view fields, найти поле `type=attribute` требуемого
`entityId` и использовать его `mname`. Для этого предназначен
`alterios_upsert_form_manual_script_action`: `argument_entity_ids` задает
смысловую сущность, а MCP разрешает ее ID-поле автоматически.

Перед применением tool проверяет UUID, `type=manual`, active state, пустые
привязки, наличие provider key в ячейке/представлении и совместимость с
`script.config.arguments`. После записи действие повторно читается из формы.
Если скрипт зависит от только что сохраненных полей или ID новой записи,
используется порядок `submit_all -> manual_script -> routing`.

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
