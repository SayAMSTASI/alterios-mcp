# Расширенные пользовательские сценарии alterios-mcp

Дата: 2026-07-10

Назначение документа: расширить набор пользовательских и конфигураторских
сценариев для `alterios-mcp` и явно отделить реализованные возможности от
сценариев, которым еще нужны UI/HAR/API evidence или новые typed tools.

Контекст текущего покрытия:

- MCP tools: 107;
- write-like MCP tools: 44;
- project-base сценарии уже покрывают content types, fields, content, files,
  views, forms, scripts, BPMN/process/tasks, reports, groups, comments;
- users, roles, user groups writes и destructive delete имеют typed security
  wrappers, но live execution остается sandbox/UI-evidence задачей.

## 1. Статусы сценариев

В документе используются статусы:

| Статус | Значение |
|---|---|
| `Поддержано typed tool` | Есть специализированный MCP tool с dry-run, write gate и readback. |
| `Поддержано read-only` | Есть чтение/инвентаризация, но запись не должна выполняться без отдельного сценария. |
| `Через form JSON` | Можно сделать через `alterios_upsert_form` или `alterios_patch_form_tabs`, но нет отдельного узкого tool для этой функции. |
| `Через generic/preflight` | Возможен исследовательский route через `alterios_rest_write`, но только после `alterios_write_safety_preflight`; для постоянной эксплуатации нужен typed tool. |
| `Требует evidence` | Нужен UI/HAR/API capture, payload shape, readback и sandbox-проверка. |

## 2. Создание диаграмм BPMN

Статус: `Поддержано typed tool`.

Цель сценария: создать или обновить BPMN-диаграмму, связать ее с типом материала,
запустить процесс, проверить задачи и side effects.

Используемые инструменты:

- `alterios_upsert_bpmn_diagram`;
- `alterios_start_process`;
- `alterios_list_process_tasks`;
- `alterios_complete_task`;
- `alterios_validate_process_result`;
- `alterios_deep_inventory` для карты связей.

Минимальный сценарий:

1. Проверить профиль и проект.
2. Подготовить BPMN XML.
3. Убедиться, что `userTask` содержит корректный `camunda:formKey`, если задача
   должна открывать форму.
4. Если есть `scriptTask`, service task или listeners, сверить ссылки на scripts.
5. Выполнить dry-run создания диаграммы.
6. Выполнить запись через `ALTERIOS_MCP_ALLOW_WRITE=1` и `dry_run=false`.
7. Прочитать диаграмму обратно.
8. Запустить процесс на sandbox-записи.
9. Проверить активные tasks.
10. Завершить задачу тестовым `nextFlowId`, если сценарий это требует.
11. Проверить process/task readback и изменения данных.

Что важно проверять:

- `contentTypeId`;
- `createOnStart`;
- `delayedStart`;
- `camunda:formKey`;
- task names;
- listeners;
- script refs;
- process count до/после;
- active task count;
- content side effects.

Ограничения:

- BPMN listeners распознаются scanner-ом и попадают в linkage matrix, но запуск
  listener side effects требует отдельного controlled workflow;
- destructive script/service calls внутри BPMN не должны выполняться без
  dangerous preflight.

## 3. Создание представлений

Статус: `Поддержано typed tool`.

Цель сценария: создать представление нужного формата поверх content type,
подключить view entity, добавить поля, проверить данные и использовать
представление в форме.

Инструменты:

- `alterios_upsert_view`;
- `alterios_upsert_view_entity`;
- `alterios_upsert_view_field`;
- `alterios_view_entities`;
- `alterios_view_fields_populated`;
- `alterios_view_data_simplified`;
- `alterios_view_data`.

Минимальный сценарий:

1. Выбрать content type.
2. Создать view.
3. Создать view entity с привязкой к content type.
4. Добавить view fields через `alterios_upsert_view_field`.
5. Проверить populated field metadata.
6. Проверить `get-data-simplified`.
7. Если view используется в текущей карточке, проверить `get-data` с
   `dataId: [openId]`.
8. Встроить view в форму через `view_data` или `view_data_list`.

Для experimental table/reference/list перед UI-preview нужно заполнить
`settings.title` одним `viewField.mname`. Это не mustache-шаблон, а ссылка на
поле представления, которое frontend использует как заголовок строки.

Правила качества:

- не добавлять поля без пользовательского смысла;
- сначала основные поля, потом технические;
- явно проверять joins/entity chain;
- для связанных списков проверять relation field;
- не считать view готовым только по факту сохранения JSON, нужен data readback.

Типовые виды представлений:

- основной список материала;
- список для выбора связанной записи;
- детализация текущей записи;
- связанный список дочерних объектов;
- source view для отчета;
- source view для dashboard/analytics.

Подтвержденные форматы:

- `table` - основной табличный список и joined views;
- `reference` - источник для `ref source=view`;
- `grid` - плиточный вывод с описанием/иконкой;
- `list` - компактный раскрываемый список;
- `gantt` - диаграмма Ганта по датам и ресурсам;
- `leaflet` - карта по `geo`-полям;
- `calendar` - календарный вывод по `title`, `startDate`, опциональным
  `endDate` и `bgColor`.

UI-проверка 2026-07-11 подтвердила настройку и preview для всех этих форматов.
Для `leaflet` значения `geo` должны быть GeoJSON `Feature`, иначе маркеры не
появятся. Для `reference` standalone preview не выводит строки; формат нужно
проверять как источник выбора для `ref source=view`.

### 3.0.1. Сценарий: сотрудник через reference-view

Цель: пользователь выбирает сотрудника в поле связи, а в списке видит ФИО, а не
технический id.

1. Создать или выбрать source content type "Сотрудники" с читаемым полем ФИО.
2. Создать `reference` view в experimental/v2 и добавить `_id` плюс ФИО.
3. В основном типе материала создать `ref` поле:
   `source=view`, `views=[reference view]`, `entityContentType=Сотрудники`,
   `widget=autocomplete`.
4. Добавить это поле в основной table view как view field и проверить, что
   обычный вывод возвращает id связанной записи.
5. Для пользовательского списка создать joined `table` view: основная сущность
   слева, "Сотрудники" справа.
6. Join строить по фактическим `viewField.mname`: слева `ref`-поле, справа `_id`
   связанной сущности.
7. Добавить в вывод читаемое поле ФИО связанной сущности, а технические id и
   helper ref-колонку скрыть на пользовательской форме.
8. Acceptance: `view_fields_populated`, `get-data-simplified` и UI-preview
   показывают код/наименование основной записи и ФИО сотрудника.

Не использовать `cards` как подтвержденный формат без отдельного evidence:
в актуальном frontend enum он не найден.

### 3.1. Связи, поля и фильтры

Представление считается настроенным только после проверки связей и данных:

- `viewEntity` задает источник и, при необходимости, цепочку `joins`;
- связь родитель/дочерний объект должна иметь конкретный relation field;
- добавление поля в content type не добавляет его автоматически в view:
  нужен отдельный `view field` с alias/order/display rules;
- фильтры фиксируются как часть требований: статические, пользовательские,
  роль-зависимые, current-record через `openId`/`dataId`;
- сортировка задается явно, если порядок строк важен для пользователя;
- source view для отчета не должен содержать лишние поля, которые не
  используются в шаблоне или аналитике;
- `contentId` без `dataId: [openId]` не считается проверкой current-record
  фильтрации.

Минимальный readback:

1. `alterios_view_entities` показывает ожидаемый entity chain.
2. `alterios_view_fields_populated` показывает все нужные поля и alias.
3. `alterios_view_data_simplified` возвращает ожидаемые строки.
4. Для карточки текущей записи `alterios_view_data` с `dataId: [openId]`
   возвращает только строки текущего контекста.

## 4. Группы меню

Статус: `Поддержано typed tool`.

Группа меню - навигационный пункт workspace, который обычно открывает форму.

Инструменты:

- `alterios_list_groups`;
- `alterios_upsert_group`.

Поддерживаемые настройки:

- `name`;
- `description`;
- `root`;
- `parentGroupId`;
- `children`;
- `order`;
- `publish`;
- `formId`;
- `iconId`.

Сценарии:

1. Создать новый пункт меню для main/list формы.
2. Привязать группу к форме через `formId`.
3. Разместить группу под root или другой parent group.
4. Установить `publish=true`, если пункт должен быть видим в меню.
5. Назначить `iconId` по стандарту Google Fonts Icons.
6. Проверить группу через `GET /api/groups` и UI.

Правила:

- root-группу не менять без необходимости;
- если пункт меню пользовательский, у него должна быть понятная форма и понятная
  иконка;
- `publish=false` использовать для скрытых/черновых пунктов;
- `publish` у группы не равен публикации content type в другие проекты.

## 5. Пользователи

Статус: `Поддержано typed security tools`; disposable user create/delete
проверен через UI и API cleanup-readback. Production security writes остаются
dangerous-gated и требуют отдельного sandbox/rollback-плана.

Известный read route:

- `GET /api/users/listandcount`.

Наблюдаемые настройки пользователей:

- `email`;
- `firstName`;
- `lastName`;
- `isActive`;
- `roles`;
- `projectsIds`;
- `settings`;
- `notificationLevel`;
- `telegramId`;
- `superuser`.

Пользовательские сценарии, которые нужны MCP:

1. Просмотреть пользователей проекта.
2. Найти пользователя по email/name/id.
3. Проверить активность пользователя.
4. Проверить проекты пользователя.
5. Проверить роли и группы пользователя.
6. Отключить пользователя без удаления.
7. Назначить роль или группу.
8. Снять роль или группу.

Почему live-запись остается dangerous:

- изменение пользователя влияет на доступы;
- нужен readback: пользователь, роли, проекты, группы;
- нужен rollback/restore план;
- нужны проверки, что оператор не отключает последнего администратора.

Инструменты:

- `alterios_list_users`;
- `alterios_get_user`;
- `alterios_upsert_user`;
- `alterios_delete_user`.

Для назначения ролей/групп текущий typed path - `alterios_upsert_user` с
явным payload, expected email, dry-run и dangerous gate.

## 6. Группы пользователей

Статус: `Поддержано typed security tools`; create/update/delete live-проверены
в приватном sandbox. Membership semantics still require separate UI/HAR evidence.

Известный read route:

- `GET /api/user-groups/listandcount`.

Наблюдаемые настройки:

- `name`;
- `description`;
- `membersCount`;
- `projectId`.

Сценарии:

1. Просмотреть группы пользователей проекта.
2. Проверить состав группы.
3. Добавить пользователя в группу.
4. Удалить пользователя из группы.
5. Использовать группу как candidate group в task/BPMN.
6. Проверить, какие формы или процессы завязаны на группу.

Инструменты:

- `alterios_list_user_groups`;
- `alterios_get_user_group`;
- `alterios_upsert_user_group`;
- `alterios_delete_user_group`.

Что еще нужно после live execution:

- UI/HAR для подтверждения состава и membership semantics;
- readback состава группы, если API возвращает только summary;
- проверка влияния на задачи и доступ к формам;
- безопасный сценарий для изменения membership, если группа содержит реальных
  пользователей.

## 7. Роли и права

Статус: `Поддержано typed security tools`; create/update/delete live-проверены
в приватном sandbox. Assignment semantics still require separate UI/HAR evidence.

Известный read route:

- `GET /api/roles/listandcount`.

В приватном sandbox role create/update/delete подтверждены live-записью и cleanup
readback. Семантика назначения роли пользователю пока не считается
подтвержденной без отдельного UI/HAR evidence.

Сценарии, которые нужны MCP:

1. Просмотреть роли.
2. Посмотреть разрешения роли.
3. Создать роль.
4. Изменить разрешения роли.
5. Назначить роль пользователю.
6. Снять роль.
7. Проверить доступ после изменения.

Риски:

- неверная роль может открыть или закрыть доступ к проекту;
- изменение permissions может иметь эффект шире текущего проекта;
- нужен отдельный dangerous/security gate;
- нужен UI-visible readback.

Инструменты:

- `alterios_list_roles`;
- `alterios_get_role`;
- `alterios_upsert_role`;
- `alterios_delete_role`.

Назначение роли пользователю выполняется через `alterios_upsert_user`, пока
отдельный membership/permission tool не будет подтвержден UI/HAR evidence.

## 8. Включения и связывание объектов

Статус: смешанный.

Под “включениями” в текущей модели MCP стоит разделять несколько разных
механизмов.

### 8.1. Включение формы в форму

Статус: `Через form JSON`.

Форма может содержать ячейку типа `form`. Это используется для вложенного
отображения другой формы. Перед записью нужно проверить:

- source form id;
- контекст `openId`;
- отсутствие пустых рядов вокруг вложенной формы;
- не конфликтуют ли actions вложенной формы с actions родителя.

### 8.2. Включение представлений в форму

Статус: `Поддержано typed form/view tools`.

Типы ячеек:

- `view_data`;
- `view_data_list`.

Проверять:

- `params.viewId`;
- `viewEntityId`;
- `openId`;
- relation field;
- `dataId: [openId]` для current-record context.

### 8.3. Включение справок, комментариев и отчетов

Статус: `Через form JSON`, источник поддержан typed/read tools.

Типы ячеек:

- `help`;
- `comments_list`;
- `report`;
- rich/html/content cells.

Проверять:

- `helpId` или содержимое help cell;
- `params.openId=true` для комментариев текущей записи;
- `reportId`, `fullscreenMode`, `openId` для отчета;
- UI render, если блок пользовательский.

### 8.4. Включение пользователя в группу/роль

Статус: `Поддержано typed security payload`; live semantics требуют evidence.

Это security-сценарий, его нельзя считать обычной связью project base.
Текущий typed path - `alterios_upsert_user` или `alterios_upsert_user_group`
с явным payload, expected target check и dangerous/security gate. Нужны UI/HAR,
membership readback и rollback до live execution.

### 8.5. Включение материала в меню/группу

Статус: частично поддержано.

Для контента используется `groupsIds` при create/update content. Для меню
используется `formId` на группе. Нужно не путать:

- группа меню открывает форму;
- `groupsIds` у content row может влиять на принадлежность/видимость записи;
- user group влияет на доступы и назначения.

## 9. Файлы

Статус: `Поддержано typed tool`.

Файлы в текущем API не имеют подтвержденного общего list endpoint:

- `/api/files` возвращал `404`;
- `/api/files/listandcount` возвращал `404`.

Поддержанные маршруты:

- `POST /api/file/upload/field`;
- `GET /api/file/list?id=...`;
- сохранение file value в content через `/api/contents/save`.

Инструменты:

- `alterios_file_upload_to_field`;
- `alterios_file_metadata`;
- `alterios_update_content_fields`.

Сценарии:

1. Создать или проверить field type `file`.
2. Проверить настройки file field:
   - `extensions`;
   - `folder`;
   - `storage`;
   - `size`;
   - `mode`;
   - `inputType`;
   - `enableDelete`;
   - `enableRename`;
   - `enableDescription`;
   - `enableAccessToStore`;
   - `deleteOnContentDelete`;
   - `deleteOnReplace`;
   - `valueCount`.
3. Загрузить файл через multipart.
4. Сохранить полученное file value в content row.
5. Прочитать metadata через `GET /api/file/list?id=...`.
6. Проверить карточку/форму, если файл должен быть видим пользователю.

Ограничения:

- массовый список всех файлов не подтвержден;
- удаление файлов не оформлено typed tool;
- file delete относится к destructive flow и требует отдельного сценария.

## 10. Действия элемента и формы

Статус: частично `Поддержано typed tool`, частично `Через form JSON`.

Текущая матрица действий форм содержит:

- `save_submit`;
- `open_form`;
- `manual_script`;
- `start_process`;
- `routing`;
- `task_edit`;
- `delete`;
- `delete_contents`;

Базового “открыть элемент” недостаточно. Для полноценной формы нужно
проектировать action surface.

### 10.1. Навигационные действия

- открыть форму добавления;
- открыть карточку просмотра;
- открыть форму редактирования;
- вернуться назад;
- перейти на main/list форму;
- открыть связанную форму;
- открыть task form.

### 10.2. Действия сохранения

- сохранить текущую форму;
- `submit_all` перед запуском скрипта, если скрипт должен видеть свежие данные;
- сохранить и закрыть;
- сохранить и перейти;
- сохранить и запустить процесс.

### 10.3. Скриптовые действия

- запуск manual script;
- передача args;
- запуск после сохранения;
- проверка active script;
- проверка expected script name;
- readback side effects.

Для настройки ручного скрипта в действии формы используется
`alterios_upsert_form_manual_script_action`. Инструмент:

- поддерживает области `page`, `element`, `value`;
- принимает сохраненный UUID ручного скрипта, а не имя или runtime service;
- связывает аргументы с `openId`, `__entity_id`, обычными полями или ID-полями
  представления;
- разрешает ID-поле по `entityId`, поэтому `_id`, `_id0`, `_id5` не выбираются
  по порядковому номеру;
- добавляет `submit_all` перед скриптом, когда требуются свежие значения формы;
- размещает действие значения во вложенном меню и проверяет его readback;
- блокирует пустые bindings и неоднозначный `__entity_id` без `viewEntityId`.

### 10.4. Процессные действия

- `start_process`;
- открыть task edit;
- завершить task;
- выбрать next flow;
- проверить process/task readback.

### 10.5. Действия со строками списка

Рекомендуемый порядок:

1. Редактировать.
2. Просмотр.
3. Удалить.

Видимые кнопки должны быть icon-first. Вторичные действия лучше убирать в меню
`more_vert`, если они перегружают строку.

### 10.6. Destructive actions

`delete` и `delete_contents` выполняются только typed destructive workflow
`alterios_fast_live_bulk_delete` и только при наличии evidence:

- exact UI route;
- payload shape;
- target ids;
- dependency check;
- restore/rollback model;
- readback/UI proof.

## 11. Слушатели в формах

Статус: `Поддержано typed tool` для patch одной ячейки; новые listener shapes
требуют инвентаризации перед live-записью.

В observed form JSON встречается структура:

```json
{
  "emitting": {
    "listeners": []
  }
}
```

Сценарии:

1. Найти форму и ячейку, где нужен listener.
2. Прочитать текущий form JSON.
3. Найти существующий `emitting` и не затирать соседние настройки.
4. Добавить listener в нужную ячейку или action surface.
5. Сохранить форму через `alterios_patch_form_cell_listeners`,
   `alterios_upsert_form` или `alterios_patch_form_tabs`.
6. Прочитать форму обратно.
7. Проверить UI-событие или side effect.

Что нужно до расширения listener coverage:

- inventory реальных listener shapes;
- список событий;
- payload listener-а;
- правила привязки к field/view/action;
- readback и UI behavior;
- связь с scripts, если listener запускает скрипт.

Safe path: редактировать listeners через `alterios_patch_form_cell_listeners`,
если известен точный путь `tabs[row][cell]`; для неизвестных shapes сначала
делать dry-run и readback формы.

## 12. Множественный выбор

Статус: `Поддержано typed tools` для поля list/multiple, массового обновления,
manual script, process и отдельно gated destructive delete.

Множественный выбор встречается в двух разных местах.

### 12.1. Поле типа list с multiple

В инвентаризации field settings есть `multiple` для type `list`.

Сценарий:

1. Создать или проверить field type `list`.
2. Настроить `values`.
3. Установить `multiple=true`, если поле допускает несколько значений.
4. Проверить `valueCount`, `required`, `defaultValue`.
5. Проверить форму добавления/редактирования.
6. Проверить сохранение content row.

Для content values MCP нормализует значения полей в массивы, поэтому важно
заранее понимать, где поле допускает одно значение, а где несколько.

### 12.2. Множественный выбор строк в списке

В формах наблюдаются actions `delete_contents` и сценарии массового удаления.
Для безопасного non-destructive сценария добавлен
`alterios_bulk_update_selected_content_fields`: он принимает `selected_content_ids`,
проверяет дубли, `expected_count`, `max_count`, content type и строит per-row
diff/readback. Destructive массовые действия исполняются только через
`alterios_fast_live_bulk_delete` с matching `plan_id`, dangerous gates и
absence-readback каждой записи.

Для безопасных массовых действий нужен отдельный сценарий:

- как UI передает selected ids;
- где хранится selection state;
- какой action получает args;
- какой script или REST route исполняется;
- как проверяется результат.

Поддержанные сценарии: одинаковые field values через
`alterios_bulk_update_selected_content_fields`, manual script через
`alterios_fast_live_bulk_manual_script`, BPMN process через
`alterios_fast_live_bulk_process` и destructive delete через отдельный
admin/full workflow `alterios_fast_live_bulk_delete`.

## 13. Отчеты

Статус: `Поддержано typed tools`; printable render/PDF proof автоматизирован,
embedded viewer требует отдельного UI spot-check.

Инструменты:

- `alterios_upsert_report`;
- `alterios_patch_report_template`;
- `alterios_validate_report_project_base`;
- `alterios_validate_stimulsoft_layout`;
- `alterios_validate_printable_render`;
- `alterios_report_full`.

Сценарии:

1. Создать dashboard report на Project Database source.
2. Создать печатную форму с band layout.
3. Встроить отчет во вкладку формы.
4. Настроить current-record report через `openId`.
5. Проверить source view.
6. Проверить Stimulsoft template geometry.
7. Прочитать full report после сохранения.
8. Проверить printable render/PDF автоматически и embedded viewer отдельно.

Правила:

- source rows строятся в Alterios view;
- Project Database source должен ссылаться на `view-data-v2`;
- current-record context проверяется через `dataId: [openId]`;
- `contentId` сам по себе не доказывает фильтрацию;
- динамические блоки Stimulsoft требуют band/ShiftMode дисциплины;
- финальная печатная форма требует render/export proof.

Открытый риск:

- embedded viewer в in-app browser может показывать пустой `viewer_*` container
  независимо от успешного printable render. Для viewer нужен UI spot-check.

## 14. Скрипты

Статус: `Поддержано typed tool` для saved scripts и manual execution.

Наблюдаемые типы scripts:

- `manual`;
- `event`;
- `diagram`.

Инструменты:

- `alterios_upsert_script`;
- `alterios_validate_script`;
- `alterios_execute_manual_script`;
- `alterios_service_catalog`;
- `alterios_call_readonly_service`;
- `alterios_call_write_service`.

### 14.1. Как писать скрипт

Перед написанием скрипта нужно зафиксировать:

1. Тип скрипта: `manual`, `event` или `diagram`.
2. Где он запускается:
   - action формы;
   - BPMN node/listener;
   - event;
   - ручной вызов.
3. Какие args получает.
4. Нужен ли `submit_all` перед запуском.
5. Какие сервисы вызывает.
6. Какие данные меняет.
7. Какой readback доказывает результат.
8. Что делать при ошибке.

### 14.2. Как собирать скрипты в рамках проекта

Рекомендуемый порядок:

1. Сначала построить content type, fields и views.
2. Создать forms без сложной логики.
3. Добавить manual script как отдельный объект.
4. Проверить script через `alterios_validate_script`.
5. Подключить script к form action.
6. Если нужен BPMN, добавить diagram script или listener refs.
7. Запустить sandbox process/content scenario.
8. Проверить data/process/task side effects.
9. Задокументировать args и expected readback.

### 14.3. Runtime services

Каталог известных runtime services:

- read: `getContents`, `getDependentContents`, `getTasks`, `getViewData`;
- write: `createContent`, `updateContent`, `createDependentContent`,
  `uploadFile`;
- destructive: `deleteManyContents`;
- workflow: `startProcess`, `reassignTask`, `messageToAnotherProcess`;
- external: `notify`;
- audit: `writeLog`.

Правила:

- runtime service name не является script UUID;
- `/api/scripts/execute-manual` принимает saved script UUID;
- destructive service calls запрещены без dangerous preflight;
- `notify` имеет внешний side effect;
- `writeLog` меняет audit-like state;
- script body в canonical JSON не сохраняется полностью, для inventory хранится
  `body_length`, `body_sha256` и найденные service calls.

## 15. Типы материалов и публикация в другие проекты

Статус: создание/обновление type fields `Поддержано typed tool`;
native флаги публикации type `Поддержано live через /api/content-types/save`;
cross-project публикация/transfer `Поддержано route evidence + typed clone tool`,
execution `Требует отдельный target sandbox`.

Поддержанные инструменты:

- `alterios_list_content_types`;
- `alterios_upsert_content_type`;
- `alterios_upsert_field`;
- `alterios_create_content`;
- `alterios_update_content_fields`;
- `alterios_plan_content_type_publish`.
- `alterios_clone_shared_content_type`.

Сценарии:

1. Создать content type.
2. Настроить `mname`, `name`, `description`.
3. Настроить `fieldNamePrefix`.
4. Настроить `contentNameTemplate`.
5. Добавить fields.
6. Создать view/form/group.
7. Создать тестовую запись.
8. Проверить view data и UI.

### 15.1. Перенос типа материала в другой проект

Текущий безопасный путь MCP - не “одна кнопка publish”, а управляемое
воспроизведение конфигурации в другом `project_id`:

1. Инвентаризировать source project.
2. Составить source map: content type, fields, views, forms, groups, scripts,
   reports, icons.
3. Проверить target project.
4. Создать/обновить content type в target project.
5. Создать fields.
6. Пересобрать views/view entities/view fields.
7. Пересобрать forms/actions.
8. Пересобрать scripts/BPMN/reports только после проверки ссылок.
9. Проверить runtime: forms, view data, script/BPMN links, reports.

### 15.2. Native publish в другие проекты

Флаги публикации типа (`share`, `shareCreating`, `shareEditing`) уже
live-проверены через `/api/content-types/save`; `shareDeleting` не включается
без отдельного destructive-сценария. Native endpoint для копирования
опубликованного типа в target project подтвержден как
`POST /api/content-types/clone`, а список опубликованных типов доступен через
`GET /api/content-types?share=true`.

`alterios_plan_content_type_publish` фиксирует source content type, target
projects и список evidence. `alterios_clone_shared_content_type` выполняет
dry-run и, при включенных write gates, может вызвать native clone route из
контекста явного target `project_id`. Live execution пока не выполнялся,
потому что нужен отдельный target sandbox project и cleanup/readback-план.
Для production-ready сценария нужно:

- понять, копируются ли fields/views/forms/scripts/reports или только metadata;
- проверить конфликт имен и `mname`;
- определить rollback;
- выполнить live clone только в target sandbox;
- проверить target readback, поля, представления, формы и меню;
- снять sanitized HAR, если требуется raw network artifact.

До target sandbox проверки нельзя обещать cross-project native clone как
production-готовую возможность, но route и typed MCP tool уже есть.

## 16. Следующие этапы

Приоритетные сценарии расширения:

1. Private live/UI evidence stored outside the public repository:
   - content type publish flags;
   - role create/update/delete;
   - user group create/update/delete;
   - disposable user create/delete;
   - cross-project content type clone route.
2. Remaining security evidence:
   - permissions;
   - delete/delete_contents;
   - assign/unassign role/group semantics.
3. Expanded form listener coverage:
   - inventory more listener shapes;
   - add/update/remove listener variants;
   - script/action linkage validation.
4. Поддерживать и расширять реализованные bulk action tools:
   - `alterios_fast_live_bulk_manual_script` для manual script по выбранным ID;
   - `alterios_fast_live_bulk_process` для BPMN process по выбранным ID;
   - `alterios_fast_live_bulk_delete` только в `full/admin`, после dry-run,
     matching `plan_id`, dangerous gates и проверки отсутствия каждой записи.
5. Native content type publish/transfer live execution:
   - designate target sandbox project;
   - source/target project map;
   - conflict detection;
   - dry-run diff;
   - apply;
   - readback/runtime check.
6. Embedded report viewer validation:
   - UI spot-check viewer container;
   - current-record report visual proof;
   - browser-specific diagnostics при пустом viewer.

## 17. Acceptance checklist для нового сценария

Сценарий можно считать готовым для MCP, если есть:

- profile и explicit `project_id`;
- read-only route или source object;
- payload contract;
- dry-run diff;
- write gate;
- dangerous gate, если есть security/destructive risk;
- readback;
- UI proof, если результат виден пользователю;
- unit tests;
- запись в приватной Gitea-задаче или локальном статусе проекта;
- ссылка из README или профильного документа.
