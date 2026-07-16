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
   В тестовом sandbox один `contentId` не ограничивает view.
4. В Stimulsoft template привязывать Alterios views через Project Database
   custom source. Saved template должен содержать:
   - `Dictionary.Databases[*].ServiceName = "Project Database"`;
   - connection string с `{"type":"view-data-v2","filter":{"viewId":"..."}}`;
   - data-source columns, соответствующие текущим view fields.
5. Для dashboard/table reports Project Database template лучше создавать через
   Stimulsoft runtime/native builder. Сохраненный JSON должен содержать
   `ConnectionStringEncrypted`, `StiCustomDatabase`, `StiCustomSource` и явные
   table columns. Ручной JSON с обычным connection string может показать
   заголовки таблицы, но не вывести строки в embedded viewer.
6. Если view fields или joins изменились, refresh или rebuild Stimulsoft
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
| Simple totals | `Sum`, `Count`, `Avg`, `Max`, `Min`, `First`, `Last` expressions …18413 tokens truncated…n            "- `script-bpmn-linkage.json` - scripts, form actions, BPMN nodes/listeners/formKey/script refs, process/task readback counts.",
            "",
            "## Границы проверки",
            "",
            "- Scanner не запускает scripts и processes; side effects выводятся по статическим service-call маркерам и live process/task readback.",
            "- Script body в JSON не сохраняется: только `body_length`, `body_sha256`, UUID refs и найденные service calls.",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deep Alterios form/script/BPMN/icon inventory.")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--project-id", default=None)
    parser.add_argument("--dotenv", default=".env")
    parser.add_argument("--out-dir", default=None, help="Write docs and JSON matrices to this directory.")
    parser.add_argument("--no-processes", action="store_true", help="Skip live process/task readback.")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)

    inventory = collect_live_project_inventory(
        profile=args.profile,
        project_id=args.project_id,
        dotenv_path=args.dotenv,
        include_processes=not args.no_processes,
    )
    if args.out_dir:
        paths = write_inventory_outputs(inventory, Path(args.out_dir))
        print(json.dumps({"written": paths, "context": inventory["context"], "read_errors": inventory["read_errors"]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(inventory, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
