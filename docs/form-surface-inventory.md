# Инвентаризация поверхности форм

Дата: 2026-07-10T08:41:15.142038+00:00
Профиль: `artx`
Проект: `<sandbox-project-id>`

## Сводка

| Метрика | Значение |
|---|---:|
| Формы | 40 |
| Tabs | 42 |
| Rows | 44 |
| Cells | 47 |
| Actions | 74 |
| Icon usages | 121 |

## Типы ячеек

| Cell type | Количество |
|---|---:|
| `comments_list` | 1 |
| `content` | 8 |
| `dependent_content` | 4 |
| `form` | 1 |
| `help` | 1 |
| `report` | 2 |
| `view_data` | 12 |
| `view_data_list` | 18 |

## Типы действий

| Action category | Количество |
|---|---:|
| `delete` | 2 |
| `delete_contents` | 4 |
| `manual_script` | 7 |
| `open_form` | 28 |
| `routing` | 9 |
| `save_submit` | 22 |
| `start_process` | 1 |
| `task_edit` | 1 |

## Классификация форм

| Kind | Количество |
|---|---:|
| `add` | 11 |
| `detail` | 20 |
| `edit` | 12 |
| `list` | 17 |
| `main` | 15 |
| `other` | 1 |
| `task` | 4 |

## Формы

| Форма | Kind | Tabs | Rows | Cells | Cell types | Actions | Surface issues |
|---|---|---:|---:|---:|---|---:|---|
| `MCP Practice` | list, main | 1 | 2 | 2 | view_data_list:1, report:1 | 2 | action_title_should_be_tooltip=2, report_without_openid=1 |
| `MCP Practice. Добавить запись` | add, detail | 1 | 1 | 1 | content:1 | 1 | action_title_should_be_tooltip=1 |
| `MCP Practice. Карточка записи` | detail, edit, task | 2 | 3 | 3 | view_data:1, comments_list:1, report:1 | 1 | action_title_should_be_tooltip=1 |
| `Агрегаты` | list, main | 1 | 1 | 1 | view_data_list:1 | 3 | action_title_should_be_tooltip=1 |
| `Агрегаты. Отчет. Добавить` | add | 1 | 1 | 1 | dependent_content:1 | 0 | 0 |
| `Агрегаты. Отчет. Список` | list, main | 1 | 1 | 1 | view_data_list:1 | 2 | missing_action_icon=1 |
| `Акт приёмки. Добавить` | add, detail | 1 | 1 | 1 | content:1 | 0 | 0 |
| `Акт приёмки. Редактировать` | detail, edit, list | 1 | 1 | 2 | view_data:1, view_data_list:1 | 7 | action_title_should_be_tooltip=3, missing_action_icon=2, view_content_not_full_row=1 |
| `Акт приёмки. Редактировать. Массовое удаление` | detail, edit, list | 1 | 1 | 2 | view_data:1, view_data_list:1 | 9 | action_title_should_be_tooltip=3, missing_action_icon=5, view_content_not_full_row=1 |
| `Акт приёмки. Список` | list, main | 1 | 1 | 1 | view_data_list:1 | 2 | action_title_should_be_tooltip=1, missing_action_icon=1 |
| `Акт приёмки. Список. Массовое удаление` | list, main | 1 | 1 | 1 | view_data_list:1 | 2 | action_title_should_be_tooltip=1, missing_action_icon=1 |
| `Виды полей` | list, main | 1 | 1 | 1 | view_data_list:1 | 3 | action_title_should_be_tooltip=3 |
| `Виды полей. Добавить пример` | add, detail | 1 | 1 | 1 | content:1 | 1 | action_title_should_be_tooltip=1 |
| `Виды полей. Редактировать пример` | detail, edit | 1 | 1 | 1 | view_data:1 | 1 | action_title_should_be_tooltip=1 |
| `Виды полей. Справка` | other | 1 | 1 | 1 | help:1 | 0 | 0 |
| `Демо HR-маршрутизация` | list, main | 2 | 2 | 2 | view_data_list:2 | 3 | action_title_should_be_tooltip=3 |
| `Демо HR-маршрутизация. Добавить заявку` | add, detail | 1 | 1 | 1 | content:1 | 1 | action_title_should_be_tooltip=1 |
| `Демо HR-маршрутизация. Карточка заявки` | detail, edit | 1 | 1 | 1 | view_data:1 | 3 | action_title_should_be_tooltip=3 |
| `Демо HR-маршрутизация. Форма задачи` | detail, edit, task | 1 | 1 | 1 | view_data:1 | 1 | action_title_should_be_tooltip=1 |
| `Добавить агрегат` | add, detail | 1 | 1 | 1 | content:1 | 1 | action_title_should_be_tooltip=1 |
| `Добавить оборудование` | add, detail | 1 | 1 | 1 | content:1 | 1 | action_title_should_be_tooltip=1 |
| `Добавить ответ` | add, detail | 1 | 1 | 1 | content:1 | 1 | action_title_should_be_tooltip=1 |
| `Добавить сотрудника` | add, detail | 1 | 1 | 1 | content:1 | 1 | action_title_should_be_tooltip=1 |
| `Доступное оборудование` | list, main | 1 | 1 | 1 | view_data_list:1 | 3 | action_title_should_be_tooltip=2 |
| `Мои задачи` | list, main | 1 | 1 | 1 | view_data_list:1 | 0 | missing_displaying_fields=1 |
| `Оборудование` | list, main | 1 | 1 | 1 | view_data_list:1 | 3 | action_title_should_be_tooltip=1 |
| `Образец. Большое добавление. Мета` | add | 1 | 1 | 1 | dependent_content:1 | 4 | action_title_should_be_tooltip=2 |
| `Образец. Добавить` | add | 1 | 1 | 1 | dependent_content:1 | 0 | 0 |
| `Образец. Редактировать` | detail, edit | 1 | 1 | 1 | view_data:1 | 3 | action_title_should_be_tooltip=2 |
| `Образец. Список` | list, main | 1 | 1 | 1 | view_data_list:1 | 0 | 0 |
| `Образцы. Слушатели` | list, main | 1 | 1 | 1 | view_data_list:1 | 2 | action_title_should_be_tooltip=2 |
| `Ответы` | list, main | 1 | 1 | 1 | view_data_list:1 | 2 | action_title_should_be_tooltip=2 |
| `Редактировать агрегат` | detail, edit | 1 | 1 | 2 | view_data:1, form:1 | 1 | action_title_should_be_tooltip=1, view_content_not_full_row=1 |
| `Редактировать оборудование` | detail, edit | 1 | 1 | 1 | view_data:1 | 1 | action_title_should_be_tooltip=1 |
| `Редактировать ответ` | detail, edit | 1 | 1 | 1 | view_data:1 | 1 | action_title_should_be_tooltip=1 |
| `Редактировать отчет` | detail, edit, task | 1 | 1 | 1 | view_data:1 | 1 | action_title_should_be_tooltip=1 |
| `Редактировать сотрудника` | detail, edit | 1 | 1 | 1 | view_data:1 | 1 | action_title_should_be_tooltip=1 |
| `Сотрудник` | list, main | 1 | 1 | 1 | view_data_list:1 | 6 | action_title_should_be_tooltip=2, missing_action_icon=2 |
| `Список оборудования для выбора доступного` | list, main | 1 | 1 | 1 | view_data_list:1 | 0 | 0 |
| `Укажите доступное оборудование` | task | 1 | 1 | 1 | dependent_content:1 | 0 | 0 |

## JSON-матрицы

- `docs/form-surface-inventory.json` - tabs/rows/cells/actions/params/styles/displaying/conditions.
- `docs/icon-usage-matrix.json` - iconId/icon/materialIcon usage по формам, группам и actions.

## Правила чтения

- `surface_check` показывает статический preflight, а не визуальную UI-проверку.
- UUID в `iconId` означает наличие ссылки на иконку; соответствие Google Fonts Icons требует отдельной сверки с registry/readback.
- Form kind выводится эвристически по ячейкам, actions и BPMN `formKey`; неоднозначные формы могут иметь несколько kind.
