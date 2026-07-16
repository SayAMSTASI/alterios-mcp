# UX-контракт Alterios MCP

Версия контракта: `2026-07-16.1`.

Контракт связывает правила skills, генераторы форм и отчетов, runtime-проверку и
сценарные write-tools. При нарушении подтвержденного правила apply блокируется,
а не ограничивается предупреждением.

## Обязательные проверки форм

| Код | Требование |
|---|---|
| `close_action_missing_redirect_back` | Действие «Закрыть» использует routing `redirect_back`. |
| `element_action_title_must_be_tooltip` | Действие элемента отображается иконкой, текст переносится в tooltip. |
| `field_footnote_requires_date` | Постоянная сноска разрешена только для поля даты. |
| `non_table_cell_header` | У нетабличной ячейки отсутствует отдельный заголовок. |
| `table_cell_header_style` | Заголовок таблицы выровнен по центру и имеет bold. |
| `view_detail_view_data_must_be_readonly` | Представление в форме просмотра не допускает редактирование. |

## Сценарная запись

Перед apply `alterios_create_material_module`, `alterios_create_report_tab` и
`alterios_create_process_flow` должны получить:

- `plan_id` проверенного dry-run;
- ссылку на рабочую задачу `work_item_ref`;
- хотя бы одну ссылку на передачу результата агента `agent_handoff_refs`;
- текущую версию UX-контракта;
- свежий runtime fingerprint без признака `stale`.

Активную версию и блокирующие коды возвращает `alterios_ux_contract`, а
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
