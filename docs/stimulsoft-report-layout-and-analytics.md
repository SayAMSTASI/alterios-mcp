# Stimulsoft: раскладка отчетов и аналитика

Дата: 2026-07-10
Scope: Alterios/LIMS reports, которые сохраняются через `/api/reports` со
Stimulsoft templates.

Это рабочий checklist для построения печатных форм, embedded reports и
analytics dashboards без съезда layout.

## Источники Stimulsoft

- Stimulsoft report component properties:
  https://www.stimulsoft.com/documentation/en/user-manual/report_internals_components_image.htm
- Stimulsoft DataBand properties:
  https://admin.stimulsoft.com/documentation/classreference-dbs/html/2e8f8b2f-de30-008e-47d8-db43368ed668.htm
- Stimulsoft report creation and totals:
  https://www.stimulsoft.com/en/documentation/report-creation
- Stimulsoft dashboard data transformation:
  https://www.stimulsoft.com/manuals/en/user-manual/dashboards_data_filtering_data_transformation.htm
- Stimulsoft dashboard filter groups:
  https://www.stimulsoft.com/en/blog/articles/elements-of-data-filtering-in-dashboards

## Правила источников Alterios

Для printable forms и dashboards используется одна discipline по источникам:

1. Сначала построить данные в Alterios: content types, fields, views, joins и
   filters.
2. Проверить source rows:

```http
POST /api/views/v2/get-data-simplified
{"viewId":"<view-id>","limit":50,"offset":0}
```

3. Для current-record context в embedded report/list scenarios проверить
   `POST /api/views/v2/get-data` с top-level `dataId: ["<openId>"]`. В текущем
   ART X sandbox один `contentId` не ограничивает view.
4. В Stimulsoft template привязывать Alterios views через Project Database
   custom source. Saved template должен содержать:
   - `Dictionary.Databases[*].ServiceName = "Project Database"`;
   - connection string с `{"type":"view-data-v2","filter":{"viewId":"..."}}`;
   - data-source columns, соответствующие текущим view fields.
5. Если view fields или joins изменились, refresh или rebuild Stimulsoft
   dictionary data source. Не доверять старым cached columns.

## Выбор типа отчета

Printable report используйте, когда output должен стать стабильным документом:
акт, протокол, сертификат, счет, реестр, маршрутный лист или PDF. Для этого
нужны bands и fixed page geometry.

Dashboard используйте для interactive analytics: filters, charts, indicators,
tables, gauges, drill-like inspection или embedded operational summary.

Embedded report tab используйте, когда форме нужен контекст текущей записи.
Форма cell:

```json
{
  "type": "report",
  "params": {
    "reportId": "<report-id>",
    "fullscreenMode": false,
    "openId": true
  }
}
```

## Правила layout для печатных форм

1. Сначала задать page size и margins. Каждый component должен помещаться в
   printable area до включения dynamic behavior.
2. Использовать bands для vertical flow:
   - `ReportTitleBand` - одноразовый title;
   - `PageHeaderBand` - повторяемые column headers;
   - `GroupHeaderBand` - grouping keys;
   - `DataBand` - repeated rows;
   - `GroupFooterBand` - group totals;
   - `ReportSummaryBand` - final totals;
   - `PageFooterBand` - page numbers/signatures внизу страницы.
3. Не ставить unrelated components абсолютными координатами под dynamic text
   field. Перенесите их в следующий band или задайте явный `ShiftMode`.
4. Для table rows все visible cells одной логической строки должны иметь один
   `Top` и `Height`. Если одна cell может расти, весь row должен быть dynamic:
   text cells используют compatible `CanGrow`/`CanShrink`, а borders/backgrounds
   используют `GrowToHeight`.
5. Не допускать пересечения visible components в одном parent container. Если
   нужен background rectangle, делайте его background/shape element за text.
6. `CanGrow` использовать только для текста, который реально может переноситься.
   Добавлять `WordWrap` и достаточную width.
7. `CanShrink` использовать для optional blocks и пустых detail areas, но
   проверять, что lower components сдвигаются и containing band тоже shrinking.
8. `CanBreak` использовать только для длинных text/detail blocks, которые могут
   делиться между pages. Signatures, stamps, short totals и table headers
   держать together.
9. `KeepHeaderTogether`, `KeepDetailsTogether`, `KeepFooterTogether` и
   `KeepGroupTogether` включать там, где separation header/footer от rows
   делает printed form некорректной.
10. `DockStyle`/`Anchor` использовать для components, которые должны следовать
    owner container или page edge. Не имитировать right/bottom anchoring
    магическими absolute coordinates.
11. Totals размещать в group footers или report summary/footer bands, а не в
    середине detail row только потому, что expression там работает.
12. Для signatures, stamps, QR/barcodes и images резервировать fixed frame и
    predictable scaling. Image не должен расти в соседний text.

## Правила layout для dashboards

1. Считать каждый dashboard component fixed card в page coordinates. Сначала
   задать grid.
2. Filters держать в одном top row или side column; charts/tables получают
   свои non-overlapping rectangles.
3. Если filter должен влиять только на часть elements, задавать matching
   `Group` properties. По умолчанию dashboard filters могут влиять на все
   components.
4. Не использовать DatePicker для exact snapshot equality, пока source date не
   является реальным DateTime column и UI behavior не проверен визуально.
5. Для current-state snapshots предпочитать precomputed source rows или
   technical snapshot fields, а не complex dashboard-only expressions.

## Возможности аналитики

| Потребность | Stimulsoft capability | Правило Alterios |
|---|---|---|
| Simple totals | `Sum`, `Count`, `Avg`, `Max`, `Min`, `First`, `Last` expressions | Использовать после проверки source rows. |
| Group totals | Group headers/footers и aggregate expressions | Группировать в report, если grouping презентационный. |
| Running totals | Running total в dashboard data transformation или report expressions | Использовать только при явном sort order. |
| Percent of total | Data transformation "Show percentage" или expressions | Проверять denominator against source view. |
| Top N / pagination-like analysis | Data transformation skip/limit | Хорошо для dashboard cards, не для regulatory print totals. |
| Value normalization | Data transformation replace values | Для labels; permanent business mapping держать в Alterios data. |
| Interactive filters | Combo Box, Date Picker, List Box, Tree View filters | Явно задавать filter `Group`, если charts независимы. |
| Parameterized output | Report variables/dialog forms | Для date ranges, organization, signatory и current-record variants. |
| Master-detail print | Relations плюс master/detail DataBands | Проверять relation; без нее все details могут печататься для каждого master row. |
| Charts/indicators | Dashboard charts, indicators, gauges, tables | Для management analytics, не для strict print layout. |

## Static validation

Перед сохранением или после чтения template используйте checker:

```powershell
alterios-stimulsoft-layout-check .\report-template.json --strict
```

Или через MCP:

```text
alterios_validate_stimulsoft_layout(report_id="<report-id>", profile="artx", project_id="<project-id>")
```

Checker сейчас находит:

- пересечения visible components в одном parent container;
- component overflow за page width/height;
- zero или negative component sizes;
- growing/shrinking components с lower siblings без explicit `ShiftMode`;
- rows, где смешаны dynamic и fixed-height behavior.

Это preflight check. Final acceptance все равно требует render verification:
Stimulsoft preview/export или browser viewer плюс comparison с source data.

## Последовательность проверки

1. Прочитать текущий full report:

```http
GET /api/reports/full/{encode_filter({"_id":"<report-id>"})}
```

2. Сохранить local backup full report/template JSON.
3. Проверить source rows через `get-data-simplified`.
4. Запустить `alterios-stimulsoft-layout-check`.
5. Сохранить через `POST /api/reports` или `PUT /api/reports`.
6. Прочитать full report обратно и повторить layout check на saved template.
7. Открыть UI/report viewer и проверить exact output scenario.
8. Для printable forms сделать export/preview representative page set:
   - short row;
   - long text row;
   - empty optional block;
   - page break;
   - group with one row;
   - group crossing a page boundary.

## Частые отказы

| Симптом | Вероятная причина | Исправление |
|---|---|---|
| Text overlaps next block after long values | `CanGrow` без sibling shift или separate band | Перенести lower block в другой band или задать explicit `ShiftMode`. |
| Table row borders no longer match row text height | One cell grows while borders/siblings stay fixed | Сделать все row cells compatible и использовать `GrowToHeight` для visual frames. |
| Header printed at page bottom without rows | Missing keep-together settings | Включить header/detail/footer keep-together rules на band/group. |
| Report shows stale/missing fields | Stimulsoft datasource was not refreshed after view change | Rebuild dictionary columns from Alterios view. |
| Dashboard DatePicker gives unexpected totals | Source date type/filter semantics are not exact | Verify source DateTime and compare UI to API counts. |
| Embedded report ignores current record | Form cell lacks `openId=true` или verification used `contentId` | Add `openId=true` and verify with top-level `dataId: [openId]`. |
