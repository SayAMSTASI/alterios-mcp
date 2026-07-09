# Каталог сущностей и обращений Alterios

Контекст анализа:

- профиль MCP: `artx`;
- экземпляр: `https://lims.artx.ru`;
- проект: `4e247a6b-55ef-4665-b88c-3c156fee19ba`;
- workspace: `https://lims.artx.ru/workspace/4e247a6b-55ef-4665-b88c-3c156fee19ba`;
- режим анализа: live read-only API + одна уже выполненная безопасная write-практика на `/api/helps`.

Цель документа - не ограничиваться справками. Это рабочая карта всего состава
проекта: какие сущности есть, для чего они нужны, какими endpoint-ами читаются и
пишутся, какие настройки надо учитывать перед автоматизацией записи.

## Фактический Состав Проекта

| Сущность | Количество | Что означает |
|---|---:|---|
| Проекты экземпляра | 35 | Доступные workspace внутри `lims.artx.ru`. |
| Типы материалов / content types | 13 | Модель данных: какие записи существуют. |
| Поля | 2522 | Метаданные полей всех типов материалов. |
| Представления | 21 | Таблицы/списки/справочные выборки поверх данных. |
| Формы | 37 | UI для списков, карточек, задач и действий. |
| Скрипты | 11 | Manual/event/diagram scripts. |
| Диаграммы | 3 | BPMN/process definitions. |
| Контент | 144 | Записи данных по типам материалов. |
| Активные задачи | 1 | Текущие workflow tasks. |
| Процессы | 16 | Запущенные/завершенные process instances. |
| Отчеты | 0 | В этом проекте отчетов не найдено. |
| Группы меню | 10 | Навигационные разделы workspace. |
| Группы пользователей | 2 | Проектные группы доступа/назначений. |
| Пользователи | 2 | Пользователи проекта. |
| Справки | 2 | HTML/help entries; одна создана для MCP practice. |
| Роли | 0 | `/api/roles/listandcount` доступен, но пуст. |

Дополнительные проверки:

- `/api/features` и `/api/features/listandcount` вернули `404`.
- `/api/files` и `/api/files/listandcount` вернули `404`.
- Файлы в этой версии API работают через конкретные file IDs:
  `GET /api/file/list?id=...` и upload endpoint, а не через общий список файлов.

## Общая Модель Обращений

| Класс обращения | Назначение | Пример |
|---|---|---|
| `listandcount` | Списки объектов и пагинация. | `GET /api/forms/listandcount?limit=100&offset=0` |
| detail read | Чтение полного объекта по ID. | `GET /api/forms/{formId}` |
| populated/config read | Чтение связанных конфигураций. | `GET /api/view-fields/populated/{viewId}` |
| save/create/update | Создание или обновление конфигурации. | `POST /api/fields/save`, `PUT /api/forms` |
| runtime data read | Чтение пользовательских данных. | `POST /api/views/v2/get-data` |
| runtime data write | Создание/обновление записей. | `POST|PATCH /api/contents/save` |
| workflow action | Движение процесса/задачи. | `DELETE /api/tasks/complete` |
| script execution | Запуск сохраненного script UUID. | `POST /api/scripts/execute-manual` |
| side-effect APIs | Файлы, комментарии, уведомления. | `POST /api/file/upload/field`, `POST /api/v1/comments` |

Для write-практики сохраняем правило:

- сначала read/preflight;
- затем dry-run audit;
- затем один узкий write;
- затем API readback;
- для UI-facing сущностей еще browser/UI readback.

## Проекты

Проект - workspace внутри экземпляра Alterios. Профиль `artx` задает экземпляр,
а `project_id` задает конкретный проект.

Read:

- `GET /api/projects/listandcount`

Write:

- не используем как тренировочный объект;
- создание/изменение проектов относится к администрированию экземпляра и должно
  идти отдельным этапом после изучения прав и UI flow.

Основные настройки:

- `name`;
- `description`;
- `organizationId`;
- `fieldNamePrefix`;
- `public`;
- `participantsIds`;
- `telegramSupportGroupIds`;
- `iconId`;
- `zoom`, `center`.

Риск: высокий. Ошибка влияет на весь workspace.

## Типы Материалов / Content Types

Content type определяет модель записи: набор полей, шаблон имени, права
создания/редактирования/удаления и префиксы.

Read:

- `GET /api/content-types/listandcount`

Write:

- `POST /api/content-types/save` - создать или обновить shell/config;
- для delete endpoint в этой сессии не подтвержден, destructive-практику не
  планируем.

Подтвержденные настройки:

- `name`;
- `description`;
- `fieldNamePrefix`;
- `contentNameTemplate`;
- `settings.maxRefDepth`;
- `share`;
- `shareCreating`;
- `shareEditing`;
- `shareDeleting`.

В проекте:

- 13 content types;
- `settings.maxRefDepth` есть у всех;
- `share=true` найден у `Сотрудники и оборудование`;
- остальные share flags в текущей выборке в основном `false`.

Для чего:

- создать новый справочник/журнал;
- связать поля и формы;
- определить, как записи будут называться и доступны ли они для шаринга.

Write-практика:

1. Создать `MCP Practice. Content Type` с `fieldNamePrefix=mcp_practice`.
2. Добавить 2-3 поля.
3. Создать форму и представление.
4. Создать одну запись через `/api/contents/save`.

## Поля

Поле - метаданные отдельного атрибута content type.

Read:

- `GET /api/fields`;
- `GET /api/fields?contentTypeId=...`;
- `GET /api/fields?_id=...`.

Write:

- `POST /api/fields/save` - создать или обновить поле.

Общие настройки:

- `name`;
- `mname`;
- `type`;
- `contentTypeId`;
- `description`;
- `tooltip`;
- `order`;
- `required`;
- `defaultValue`;
- `formDisplay`;
- `settings`.

Подтвержденные типы полей и настройки:

| Тип | Кол-во | Настройки, найденные в проекте |
|---|---:|---|
| `text` | 1166 | `contentTypes`, `defaultValue`, `dropSpecialCharacters`, `fields`, `fullscreen`, `granularity`, `mask`, `maxLength`, `pattern`, `prefix`, `required`, `searchFields`, `suffix`, `valueCount`, `values`, `widget` |
| `ref` | 540 | `addActions`, `contentTypeId`, `contentTypes`, `defaultValue`, `deleteOnContentDelete`, `deleteOnReplace`, `editActions`, `entityContentType`, `entityType`, `formId`, `isTyped`, `limit`, `orderBy`, `readonly`, `related`, `searchFields`, `sortBy`, `source`, `valueCount`, `views`, `widget`, plus часть file/geo-like настроек |
| `number` | 201 | `contentTypes`, `defaultValue`, `formId`, `limit`, `max`, `maxLength`, `min`, `orderBy`, `precision`, `prefix`, `required`, `searchFields`, `sortBy`, `source`, `suffix`, `valueCount`, `views`, `widget` |
| `list` | 191 | `defaultValue`, `dropSpecialCharacters`, `expression`, `maxLength`, `multiple`, `required`, `start`, `step`, `type`, `unique`, `valueCount`, `values`, `widget` |
| `date` | 175 | `defaultValue`, `format`, `granularity`, `includeTime`, `max`, `min`, `precision`, `required`, `size`, `storage`, `titleRequired`, `valueCount`, `widget` |
| `file` | 109 | `deleteOnContentDelete`, `deleteOnReplace`, `enableAccessToStore`, `enableDelete`, `enableDescription`, `enableRename`, `extensions`, `folder`, `inputType`, `mode`, `size`, `storage`, `titleRequired`, `valueCount`, `widget` |
| `inc` | 60 | `prefix`, `start`, `step`, `suffix`, `unique`, `valueCount`, `required`, `defaultValue` |
| `boolean` | 39 | `defaultValue`, `required`, `valueCount`, `widget`, plus reference-like настройки в отдельных полях |
| `address` | 24 | `defaultValue`, `dropSpecialCharacters`, `fromBound`, `maxLength`, `objects`, `required`, `toBound`, `valueCount`, `widget` |
| `legal_entity` | 4 | `defaultValue`, `objects`, `required`, `valueCount` |
| `person` | 4 | `defaultValue`, `dropSpecialCharacters`, `maxLength`, `objects`, `required`, `valueCount`, `widget` |
| `bank` | 3 | `defaultValue`, `objects`, `required`, `valueCount` |
| `calc` | 3 | `defaultValue`, `expression`, `valueCount` |
| `comb` | 1 | `contentTypes`, `defaultValue`, `fields`, `relatedFields`, `required`, `valueCount` |
| `geo` | 1 | `center`, `defaults`, `maxZoom`, `minZoom`, `mode`, `required`, `shapes`, `valueCount`, `zoom` |
| `spreadsheet` | 1 | `defaultValue`, `fullscreen`, `required`, `valueCount` |

Для чего:

- `text/number/date/boolean/list` - базовые данные;
- `ref` - связи между content types;
- `file` - вложения;
- `calc` - вычисляемые значения;
- `inc` - автоинкремент/номер;
- `geo/address/person/bank/legal_entity` - специализированные compound-поля;
- `spreadsheet` - табличное поле;
- `comb` - комбинированное поле.

Риск: средний-высокий. Ошибка в поле ломает формы, views, scripts и data entry.

## Контент / Contents

Контент - пользовательские записи по content type.

Read:

- `GET /api/contents/listandcount`;
- обычно с фильтрами `_id`, `contentTypeId`, `limit`, `offset`;
- через представление: `POST /api/views/v2/get-data`;
- через упрощенное представление: `POST /api/views/v2/get-data-simplified`.

Write:

- `POST /api/contents/save` - create;
- `PATCH /api/contents/save` - update;
- delete endpoint не берем в первый контур.

Настройки/ключи записи:

- `_id` для update;
- `contentTypeId`;
- поля по `mname` или field id в зависимости от UI/API shape;
- системные `createdAt`, `lastUpdate`, `version`, `authorId` не должны
  подставляться руками без необходимости.

В проекте 144 записи. В выборке:

- `Образец` - 94;
- `Образец. Мета` - 15;
- `Демо HR-маршрутизация` - 13;
- `Ответы` - 7;
- прочие типы - меньше.

Для чего:

- создавать/редактировать реальные данные;
- проверять формы и представления;
- запускать процессы, если content type связан с диаграммой.

Риск: средний для scratch-записей, высокий для бизнес-записей.

## Представления / Views

View определяет таблицу, справочник, reference-list или источник данных для форм
и отчетов.

Read:

- `GET /api/views/listandcount`;
- `GET /api/views/{viewId}`;
- `GET /api/view-entities/by-view/{viewId}`;
- `GET /api/view-fields/populated/{viewId}`;
- `POST /api/views/v2/get-data`;
- `POST /api/views/v2/get-data-simplified`.

Write:

- `POST /api/views` - создать;
- `PUT /api/views` - обновить;
- view entities / view fields обычно меняются через payload view или связанные
  save routes; точный UI flow нужно снять HAR перед typed write.

Подтвержденные настройки:

- `name`;
- `description`;
- `format`: в проекте `table` - 17, `reference` - 4;
- `strict`;
- `settings.engineVersion`;
- `settings.title`;
- entities count: от 1 до 5;
- populated fields count: от 2 до 17.

Для чего:

- отображать списки;
- строить embedded lists на формах;
- давать данные Stimulsoft/report/dashboard;
- задавать reference-выборки.

Риск: средний. Ошибка в view обычно ломает отображение, но не меняет данные.

## Формы / Forms

Форма - UI-конфигурация: список, карточка, задача, embedded view, actions.

Read:

- `GET /api/forms/listandcount`;
- `GET /api/forms/{formId}`.

Write:

- `POST /api/forms` - создать;
- `PUT /api/forms` - обновить.

Основные настройки:

- `name`;
- `pageTitle`;
- `description`;
- `tabs`;
- `tabs[].rows`;
- `formActionContainers`;
- вложенные action-ы и components.

Типы элементов, найденные в формах:

- `action` - 37;
- `forms` - 26;
- `view_data_list` - 17;
- `view_data` - 11;
- `content` - 7;
- `delete_contents` - 6;
- `dependent_content` - 4;
- `manual_script` - 3;
- `context` - 3;
- `help` - 1;
- `edit_task` - 1;
- `processes` - 1;
- `form` - 1.

Типы action-контейнеров:

- `action` - 28;
- `data_managing` - 20;
- `routing` - 9;
- `manual_script` - 4;
- `context` - 4.

Для чего:

- управлять тем, как оператор видит и меняет данные;
- запускать submit/delete/manual_script;
- показывать help, related forms, embedded lists;
- выполнять task actions.

Риск: высокий. Ошибка в action order может привести к неправильной записи или
workflow side effect.

## Группы Меню / Groups

Group - навигационный пункт workspace.

Read:

- `GET /api/groups`.

Write:

- `POST /api/groups`;
- `PUT /api/groups`.

Настройки:

- `name`;
- `description`;
- `root`;
- `parentGroupId`;
- `children`;
- `order`;
- `publish`;
- `formId`;
- `iconId`.

В проекте 10 групп, почти все опубликованы и привязаны к форме.

Для чего:

- вывести форму/раздел в левое меню;
- построить навигацию для пользователей;
- скрывать/публиковать рабочие разделы.

Риск: средний. Обычно не портит данные, но может сломать навигацию.

## Скрипты / Scripts

Script - серверный код Alterios. Может быть ручным, событийным или диаграммным.

Read:

- `GET /api/scripts/listandcount`.

Write:

- `POST /api/scripts` - создать;
- `PUT /api/scripts` - обновить;
- `POST /api/scripts/execute-manual` - выполнить сохраненный manual script по
  UUID.

Настройки:

- `name`;
- `description`;
- `type`: в проекте `manual` - 8, `event` - 2, `diagram` - 1;
- `active`;
- `share`;
- `librariesIds`;
- `config.arguments`;
- `config.cron`;
- `body`.

Для чего:

- автоматизация контента;
- обработка событий;
- шаги BPMN;
- массовые действия;
- интеграции и уведомления.

Риск: высокий. Даже read/update скрипта может изменить бизнес-логику, а execute
может менять данные, процессы, файлы и внешние системы.

## Диаграммы, Процессы И Задачи

Диаграмма - BPMN-шаблон. Процесс - экземпляр выполнения. Задача - текущий
операторский шаг.

Read:

- `GET /api/diagrams/listandcount`;
- `GET /api/processes/listandcount`;
- `GET /api/tasks/listandcount`.

Write/config:

- `POST /api/diagrams`;
- `PUT /api/diagrams`.

Runtime/write:

- `POST /api/scripts/execute-manual`, если запуск процесса завернут в script;
- script-service `startProcess`, `reassignTask`, `messageToAnotherProcess`;
- `DELETE /api/tasks/complete` - завершение task/transition.

Настройки диаграмм:

- `name`;
- `contentTypeId`;
- `contentType`;
- `createOnStart`;
- `delayedStart`;
- `value` - BPMN/process JSON;
- script tasks / user tasks внутри `value`.

В проекте:

- `Выбор оборудования`;
- `Демо HR-маршрутизация. Процесс`;
- `Статус согласования отчета`;
- 1 активная task: `1. Первичная задача`;
- 16 процессов: 15 completed, 1 executing.

Настройки task, найденные в проекте:

- `askConfirmation`;
- `confirmationMessage`;
- `confirmationTitle`;
- `savable`.

Риск: очень высокий. Здесь first-write должен быть только на scratch-процессе.

## Отчеты

В проекте сейчас 0 отчетов, но API и локальные скрипты подтверждают модель.

Read:

- `GET /api/reports/listandcount/{encoded_filter}`;
- `GET /api/reports/full/{encoded_filter({"_id": report_id})}`.

Write:

- `POST /api/reports`;
- `PUT /api/reports`.

Настройки:

- `name`;
- `description`;
- Stimulsoft JSON/template;
- data sources;
- variables;
- components;
- связи с forms через `reportId`.

Для чего:

- печатные формы;
- dashboards;
- аналитика.

Риск: средний-высокий. Ошибка обычно ломает отчет, но не данные.

## Справки / Helps

Help - HTML/text object для справок, инструкций, embedded пояснений.

Read:

- `GET /api/helps`.

Write:

- `POST /api/helps`;
- для update подтвержден fallback-паттерн из локальных helper-ов:
  `PUT /api/helps`, `PATCH /api/helps`, `POST /api/helps/update`.

Настройки:

- `name`;
- `value`;
- `_id` для update;
- системные `version`, `lastUpdate`, `authorId`.

В проекте:

- `MCP Practice Sandbox` - создано через MCP practice;
- `Виды полей. Справка`.

Риск: низкий. Хороший полигон для first write.

## Файлы

Файлы не имеют подтвержденного общего list endpoint в этом проекте:

- `/api/files` - `404`;
- `/api/files/listandcount` - `404`.

Read:

- `GET /api/file/list?id=...`.

Write:

- `POST /api/file/upload/field`.

Связанные настройки находятся у полей типа `file`:

- `extensions`;
- `folder`;
- `storage`;
- `size`;
- `inputType`;
- `deleteOnContentDelete`;
- `deleteOnReplace`;
- `enableAccessToStore`;
- `enableDelete`;
- `enableDescription`;
- `enableRename`;
- `titleRequired`;
- `valueCount`.

Риск: средний. Нужно сначала снять UI/HAR upload flow, потому что upload часто
multipart и зависит от поля.

## Комментарии

Comments - отдельный API v1 для обсуждений/заметок по сущности.

Read:

- `GET /api/v1/comments?entity=...&entityId=...&limit=...&depth=...&page=...`.

Write:

- `POST /api/v1/comments`;
- `DELETE /api/v1/comments/{commentId}`.

Настройки:

- `entity`;
- `entityId`;
- `body`;
- `parentId`;
- `limit`;
- `depth`;
- `page`.

Риск: низкий-средний. Можно практиковать на sandbox content/help entity, но
удаление все равно destructive и требует отдельного allow flag.

## Пользователи, Группы Пользователей, Роли

Read:

- `GET /api/users/listandcount`;
- `GET /api/user-groups/listandcount`;
- `GET /api/roles/listandcount`.

Write:

- не используем в ближайшей write-практике;
- права и пользователи требуют отдельной модели безопасности.

Настройки users:

- `email`;
- `firstName`, `lastName`;
- `isActive`;
- `roles`;
- `projectsIds`;
- `settings`;
- `notificationLevel`;
- `telegramId`;
- `superuser`.

Настройки user groups:

- `name`;
- `description`;
- `membersCount`;
- `projectId`.

В проекте:

- 2 users;
- 2 user groups;
- 0 roles.

Риск: высокий. Ошибка может повлиять на доступы.

## Рекомендуемый Порядок Write-Практики

1. **Справки** - уже выполнено: `MCP Practice Sandbox`.
2. **Typed `alterios_upsert_help`** - вынести подтвержденный `/api/helps` flow в
   отдельный tool с dry-run diff и readback.
3. **Группы меню** - создать неопубликованную или sandbox-группу, проверить
   UI-навигацию, затем удалить только после отдельного destructive approval.
4. **Content type + fields** - создать `MCP Practice` content type и несколько
   безопасных полей: text, number, list, date.
5. **Forms** - создать простую add/edit/list форму для sandbox content type.
6. **Views** - создать table view, проверить `get-data` и UI-list.
7. **Contents** - создать и обновить одну sandbox-запись через
   `/api/contents/save`.
8. **Comments** - добавить комментарий к sandbox-записи, проверить readback.
9. **Files** - загрузить маленький тестовый файл в file-field после HAR capture.
10. **Scripts** - создать безопасный manual script, который только пишет в
    sandbox-запись или возвращает диагностический результат.
11. **Diagrams/tasks/processes** - только после отдельного sandbox BPMN:
    start -> task -> complete -> readback.
12. **Reports** - создать отчет поверх sandbox view.
13. **Users/groups/roles** - отложить до отдельного security workflow.

## Что Нужно Добавить В MCP

Ближайшие typed tools:

- `alterios_upsert_help`;
- `alterios_list_content_types`;
- `alterios_list_fields_by_content_type`;
- `alterios_create_content_type`;
- `alterios_upsert_field`;
- `alterios_upsert_view`;
- `alterios_upsert_form`;
- `alterios_update_content_fields`;
- `alterios_add_comment`;
- `alterios_upload_file_to_field`;
- `alterios_execute_manual_script` уже есть, но нужен preflight по script UUID и
  аргументам.

Каждый write tool должен иметь:

- explicit `profile`;
- explicit `project_id`;
- dry-run by default;
- target IDs / object name in audit;
- validation of known settings;
- readback route;
- optional UI URL for operator verification.
