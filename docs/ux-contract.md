# UX-контракт Alterios MCP

Версия контракта: `2026-07-16.2`.

Контракт связывает правила skills, генераторы форм и отчетов, runtime-проверку и
сценарные write-tools. При нарушении подтвержденного правила apply блокируется,
а не ограничивается предупреждением.

## Обязательные проверки форм

| Код | Требование |
|---|---|
| `add_edit_page_action_order` | У явно распознанной add/edit-формы действия страницы начинаются с «Закрыть», затем «Сохранить». |
| `close_action_missing_redirect_back` | Действие «Закрыть» использует routing `redirect_back`. |
| `element_action_title_must_be_tooltip` | Действие элемента отображается иконкой, текст переносится в tooltip. |
| `embedded_view_missing_filter_or_context` | `view_data`/`view_data_list` имеет field-based filter либо контекст `dataId`/`openId`. |
| `field_footnote_requires_date` | Постоянная сноска разрешена только для поля даты. |
| `list_row_action_icon_missing` | Внешнее меню строки и каждое настроенное действие строки имеют иконку. |
| `list_row_actions_must_be_menu` | Настроенные действия строки списка находятся во внешнем контейнере `type=menu`. |
| `list_row_menu_actions_missing` | Меню строки содержит `edit`, `view` и `delete`. |
| `missing_page_title` | Пользовательская форма имеет непустой `pageTitle`; техническое `name` его не заменяет. |
| `non_table_cell_header` | У нетабличной ячейки отсутствует отдельный заголовок. |
| `report_or_analytics_form_should_open_new_tab` | Переход к печатной/аналитической форме использует `openInNewTab=true` и не открывает dialog. |
| `report_or_analytics_target_missing_close` | Форма, достоверно распознанная по `report`-ячейке как печатная/аналитическая, имеет действие «Закрыть». |
| `row_menu_default_view_missing` | В меню строки действие `view` отмечено `default=true`. |
| `table_cell_header_style` | Заголовок таблицы выровнен по центру и имеет bold. |
| `technical_list_field_must_be_hidden` | `_id`, `_id0` и известные сервисные ID скрыты в `displaying.fields`. |
| `view_detail_close_action_missing` | Явно распознанная view/detail-форма с `view_data` имеет действие «Закрыть». |
| `view_detail_view_data_must_be_readonly` | Представление в форме просмотра не допускает редактирование. |

Контракт применяет консервативную классификацию: add/edit/view/detail определяется
по явному пользовательскому названию, печатная/аналитическая target form — по
наличию `report`-ячейки. Пустой `valueActionContainers` допустим для специально
read-only списка; требования к menu применяются, когда действия строки уже
настроены. `conditions` и один `contentId` не считаются доказательством
field-based/current-record фильтрации.

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
