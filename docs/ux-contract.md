# UX-контракт Alterios MCP

Версия контракта: `2026-07-17.1`.

Контракт связывает правила skills, генераторы форм и отчетов, runtime-проверку и
сценарные write-tools. При нарушении подтвержденного правила apply блокируется,
а не ограничивается предупреждением.

## Обязательные проверки форм

| Код | Требование |
|---|---|
| `add_edit_page_action_order` | У явно распознанной add/edit-формы действия страницы начинаются с «Закрыть», затем «Сохранить». |
| `add_page_title_must_start_with_add` | Заголовок формы добавления использует шаблон «Добавить {сущность}». |
| `close_action_missing_redirect_back` | Действие «Закрыть» использует routing `redirect_back`. |
| `data_cell_missing_full_width_style` | Основная data-ячейка имеет full-width/flex-стиль и не оставляет случайный зазор. |
| `element_actions_must_use_menu` | Более трех действий элемента группируются в меню. |
| `element_action_title_must_be_tooltip` | Действие элемента отображается иконкой, текст переносится в tooltip. |
| `empty_layout_slot`, `empty_row`, `empty_tab` | Форма не содержит пустых вкладок, строк и ячеек-заполнителей. |
| `embedded_view_missing_filter_or_context` | `view_data`/`view_data_list` имеет field-based filter либо контекст `dataId`/`openId`. |
| `field_footnote_requires_date` | Постоянная сноска разрешена только для поля даты. |
| `list_row_action_icon_missing` | Внешнее меню строки и каждое настроенное действие строки имеют иконку. |
| `list_row_actions_must_be_menu` | Настроенные действия строки списка находятся во внешнем контейнере `type=menu`. |
| `list_row_menu_actions_missing` | Меню строки содержит `edit`, `view` и `delete`. |
| `manual_script_id_must_be_uuid` | Действие ручного скрипта ссылается на сохраненный UUID скрипта. |
| `manual_script_empty_argument_binding` | Каждый аргумент ручного скрипта имеет явный `dataProviderKey`. |
| `manual_script_value_entity_ambiguous` | Строчное действие с `__entity_id` содержит правильный `viewEntityId`. |
| `missing_action_icon` | Видимое действие формы или списка имеет иконку. |
| `missing_cell_type` | Каждая ячейка формы имеет тип. |
| `missing_page_title` | Пользовательская форма имеет непустой `pageTitle`; техническое `name` его не заменяет. |
| `non_table_cell_header` | У нетабличной ячейки отсутствует отдельный заголовок. |
| `report_or_analytics_form_should_open_new_tab` | Переход к печатной/аналитической форме использует `openInNewTab=true` и не открывает dialog. |
| `report_or_analytics_target_missing_close` | Форма, достоверно распознанная по `report`-ячейке как печатная/аналитическая, имеет действие «Закрыть». |
| `row_action_order` | Вложенные действия строки идут в порядке edit, view, delete. |
| `row_menu_default_view_missing` | В меню строки действие `view` отмечено `default=true`. |
| `table_cell_header_style` | Заголовок таблицы выровнен по центру и имеет bold. |
| `table_cell_header_top_padding` | У заголовка таблицы задан верхний отступ 10 px. |
| `technical_list_field_must_be_hidden` | `_id`, `_id0` и известные сервисные ID скрыты в `displaying.fields`. |
| `view_detail_close_action_missing` | Явно распознанная view/detail-форма с `view_data` имеет действие «Закрыть». |
| `view_detail_field_input_config_present` | Поле формы просмотра не содержит input-конфигурацию. |
| `view_detail_field_output_config_missing` | Поле формы просмотра имеет output-конфигурацию для read-only вывода. |
| `view_detail_view_data_must_be_readonly` | Представление в форме просмотра не допускает редактирование. |

Контракт применяет консервативную классификацию: add/edit/view/detail определяется
по явному пользовательскому названию, печатная/аналитическая target form — по
наличию `report`-ячейки. Пустой `valueActionContainers` допустим для специально
read-only списка; требования к menu применяются, когда действия строки уже
настроены. `conditions` и один `contentId` не считаются доказательством
field-based/current-record фильтрации.

Заголовок ячейки читается как из `cell.header`, так и из фактического
`cell.displaying.header`. Для верхнеуровневого реестра заголовок ячейки не
создается. Заголовок нужен только у вложенной табличной секции; он должен быть
центрирован, выделен bold и иметь верхний отступ 10 px.

Сценарий модуля материалов по умолчанию создает отдельные list/add/edit/view
формы. Пользовательские заголовки: `Добавить {сущность}` для add, множественное
название для списка и название сущности в единственном числе для edit/view.
Apply принимает только локальные UUID иконок целевого проекта; сначала следует
выполнить `alterios_ensure_project_icon_library`.

## Сценарная запись

Перед apply `alterios_create_material_module`, `alterios_create_report_tab` и
`alterios_create_process_flow` должны получить:

- `plan_id` проверенного dry-run;
- существующую открытую private Gitea-задачу `work_item_ref`;
- ссылки `agent_handoff_refs` на структурированные handoff-комментарии той же задачи;
- подтвержденные роли `analyst`, `implementer` и `verifier` с заполненными
  `Agent`, `Scope`, `Inputs`, `Findings`, `Artifacts`, `Verification`, `Risks`, `Next`;
- текущую версию UX-контракта;
- свежий runtime fingerprint без признака `stale`.

Проверка выполняется read-only инструментом `alterios_verify_delivery_evidence`
и повторяется внутри live preflight и сценарного apply. Наличия произвольной
строки в `agent_handoff_refs` недостаточно.

Активную версию и блокирующие коды возвращает `alterios_ux_contract`, а
`alterios_validate_form_contract` применяет контракт в строгом режиме к форме
по `form_id` или переданному JSON. `alterios_analyze_form_surface` остается
неблокирующим диагностическим анализатором. Инструмент
`alterios_runtime_info` возвращает commit, путь к исходникам, PID, время старта,
версию схемы tools, hashes исходников и skills и признак устаревшего процесса.

## Печатные отчеты

`alterios_create_report_tab` по умолчанию создает `type=report` с `StiPage`,
`StiReportTitleBand`, `StiPageHeaderBand`, `StiDataBand` и
`StiPageFooterBand`. Dashboard создается только при явном
`report_type=dashboard`.

`alterios_validate_printable_render` выполняет статическую проверку layout,
рендерит шаблон через Stimulsoft Reports.JS в Chromium и сохраняет PDF-evidence
с количеством страниц, размером и SHA-256.
