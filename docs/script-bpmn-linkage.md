# Связи scripts, forms и BPMN

Дата: 2026-07-10T08:41:15.142038+00:00
Профиль: `artx`
Проект: `<sandbox-project-id>`

## Сводка

| Метрика | Значение |
|---|---:|
| Scripts | 12 |
| Diagrams | 4 |
| BPMN nodes | 15 |
| UserTask form links | 8 |
| Form script links | 7 |
| Diagram script refs | 1 |
| Listener refs | 2 |

## Типы scripts

| Type | Количество |
|---|---:|
| `manual` | 9 |
| `diagram` | 1 |
| `event` | 2 |

## Service calls в script body

| Service | Количество |
|---|---:|
| `createContent` | 2 |
| `deleteManyContents` | 1 |
| `getContents` | 8 |
| `getTasks` | 3 |
| `notify` | 2 |
| `reassignTask` | 2 |
| `startProcess` | 3 |
| `updateContent` | 8 |
| `writeLog` | 11 |

## Forms -> scripts

| Форма | Action | Script ref | Match | Args |
|---|---|---|---|---|
| `Агрегаты. Отчет. Список` | `с` | `56e885ed-5342-4d3b-a3b7-1be43263ac45` | `Выбор исполнителя` | args, type |
| `Акт приёмки. Редактировать. Массовое удаление` | `Удалить отмеченные` | `747721c7-cee7-42c5-b166-32d9c9a0e1a2` | `Акт приёмки. Удалить отмеченные образцы` | args, type |
| `Демо HR-маршрутизация. Карточка заявки` | `Старт БП` | `fcdbb5bb-eeba-4eba-a9cc-68573513ca4c` | `Демо HR-маршрутизация. Старт процесса` | args, type |
| `Демо HR-маршрутизация. Карточка заявки` | `Передать внутри БП` | `714fee75-05c0-4dfd-832c-4474e1f6346e` | `Демо HR-маршрутизация. Передать внутри БП` | args, type |
| `Образец. Большое добавление. Мета` | `Сохранить` | `05bb1fbb-7a56-49c5-9841-05ee47cf8f29` | `Образец. Мета. Ручное создание образцов из текста` | args, type |
| `Сотрудник` | `Hello` | `19dc414a-25f5-45dc-a3bd-fe17b56e2066` | `Hello World` | args, type |
| `Сотрудник` | `TG` | `c9c12c07-35a6-4352-ab9c-004cd0093b1e` | `Телеграм` | args, type |

## BPMN userTask -> forms

| Diagram | Node | formKey | Form match |
|---|---|---|---|
| `MCP Practice. BPMN Sandbox` | `StartEvent_mcp_practice` | `15f5fb26-5db4-4153-8131-23a54411cd63` | `MCP Practice. Карточка записи` |
| `MCP Practice. BPMN Sandbox` | `MCP Practice task` | `15f5fb26-5db4-4153-8131-23a54411cd63` | `MCP Practice. Карточка записи` |
| `Выбор оборудования` | `StartEvent_1` | `e1a49c14-72ef-4111-9cca-c38eb4873392` | `Укажите доступное оборудование` |
| `Демо HR-маршрутизация. Процесс` | `StartEvent_demo` | `a4ceb740-b6bc-462d-9420-a0c374f356a1` | `Демо HR-маршрутизация. Форма задачи` |
| `Демо HR-маршрутизация. Процесс` | `1. Первичная задача` | `a4ceb740-b6bc-462d-9420-a0c374f356a1` | `Демо HR-маршрутизация. Форма задачи` |
| `Демо HR-маршрутизация. Процесс` | `2. Уточнить подразделение` | `a4ceb740-b6bc-462d-9420-a0c374f356a1` | `Демо HR-маршрутизация. Форма задачи` |
| `Демо HR-маршрутизация. Процесс` | `3. Выполнение МОЛ` | `a4ceb740-b6bc-462d-9420-a0c374f356a1` | `Демо HR-маршрутизация. Форма задачи` |
| `Статус согласования отчета` | `Согласование` | `24e1a9c8-552b-4f83-9f56-32e3145db0a6` | `Редактировать отчет` |

## Диаграммы

| Diagram | Nodes | Processes | Tasks | Parse |
|---|---:|---:|---:|---|
| `MCP Practice. BPMN Sandbox` | 3 | 3 | 0 | ok |
| `Выбор оборудования` | 3 | 4 | 0 | ok |
| `Демо HR-маршрутизация. Процесс` | 6 | 12 | 1 | ok |
| `Статус согласования отчета` | 3 | 0 | 0 | ok |

## JSON-матрица

- `docs/script-bpmn-linkage.json` - scripts, form actions, BPMN nodes/listeners/formKey/script refs, process/task readback counts.

## Границы проверки

- Scanner не запускает scripts и processes; side effects выводятся по статическим service-call маркерам и live process/task readback.
- Script body в JSON не сохраняется: только `body_length`, `body_sha256`, UUID refs и найденные service calls.
