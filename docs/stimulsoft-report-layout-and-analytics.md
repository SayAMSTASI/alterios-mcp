# Stimulsoft report layout and analytics playbook

Date: 2026-07-10
Scope: Alterios/LIMS reports stored through `/api/reports` with Stimulsoft
templates.

This document is the working checklist for building printable forms, embedded
reports, and analytics dashboards without layout drift.

## Source references

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

## Alterios source rules

Use the same data-source discipline for printable forms and dashboards:

1. Build the data in Alterios first: content types, fields, views, joins, and
   filters.
2. Verify source rows through:

```http
POST /api/views/v2/get-data-simplified
{"viewId":"<view-id>","limit":50,"offset":0}
```

3. For current-record context in embedded report/list scenarios, verify
   `POST /api/views/v2/get-data` with top-level `dataId: ["<openId>"]`.
   In the current ART X sandbox, `contentId` alone does not scope the view.
4. In the Stimulsoft template, bind Alterios views through the Project Database
   custom source. The saved template must contain:
   - `Dictionary.Databases[*].ServiceName = "Project Database"`;
   - a connection string with `{"type":"view-data-v2","filter":{"viewId":"..."}}`;
   - data-source columns matching the current view fields.
5. If view fields or joins change, refresh or rebuild the Stimulsoft
   dictionary data source. Do not trust old cached columns.

## Choosing report type

Use a printable report when the output must become a stable document: акт,
protocol, certificate, invoice, registry, route sheet, or PDF. Use bands and
fixed page geometry.

Use a dashboard when the output is interactive analytics: filters, charts,
indicators, tables, gauges, drill-like inspection, or embedded operational
summary.

Use an embedded report tab when the form needs the current record context.
The form cell shape is:

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

## Layout rules for printable forms

1. Set page size and margins first. Every component must fit inside the page
   printable area before dynamic behavior is enabled.
2. Use bands for vertical flow:
   - `ReportTitleBand` for one-time title;
   - `PageHeaderBand` for repeated column headers;
   - `GroupHeaderBand` for grouping keys;
   - `DataBand` for repeated rows;
   - `GroupFooterBand` for group totals;
   - `ReportSummaryBand` for final totals;
   - `PageFooterBand` for page numbers and signatures that must stay at the
     bottom of each page.
3. Do not stack unrelated components at absolute coordinates below a dynamic
   text field. Put them in the next band or set explicit `ShiftMode`.
4. For table rows, all visible cells in one logical row must share the same
   `Top` and `Height`. If one cell can grow, the row design must treat the
   whole row as dynamic: text cells use compatible `CanGrow`/`CanShrink`, and
   borders/backgrounds use `GrowToHeight`.
5. Avoid overlapping visible components in the same parent container. If a
   background rectangle is needed, make it a background/shape element behind
   text, not another text component.
6. Use `CanGrow` only for text that can really wrap. Pair it with `WordWrap`
   and enough width.
7. Use `CanShrink` for optional blocks and empty detail areas, but verify that
   lower components shift and the containing band also shrinks.
8. Use `CanBreak` only for long text/detail blocks that may split between
   pages. For signatures, stamps, short totals, and table headers, keep the
   block together.
9. Use `KeepHeaderTogether`, `KeepDetailsTogether`, `KeepFooterTogether`, and
   `KeepGroupTogether` for groups where a header/footer separated from its
   rows would make the printed form invalid.
10. Use `DockStyle`/`Anchor` for components that must follow the owner
    container or page edge. Do not emulate right/bottom anchoring with magic
    absolute coordinates.
11. Do not place totals in the middle of the detail row just because the
    expression works there. Put group totals into group footers and final
    totals into report summary/footer bands unless there is a deliberate
    visual reason.
12. For signatures, stamps, QR/barcodes, and images, reserve a fixed frame and
    use predictable scaling. Do not let an image grow into adjacent text.

## Layout rules for dashboards

1. Treat each dashboard component as a fixed card in page coordinates. Define a
   grid before placing elements.
2. Keep filters in one top row or side column and give charts/tables their own
   non-overlapping rectangles.
3. When a filter should affect only some elements, set matching `Group`
   properties. By default dashboard filters can affect all components.
4. Do not use DatePicker for exact snapshot equality until the source date is a
   real DateTime column and UI behavior is visually verified.
5. For current-state snapshots, prefer precomputed source rows or technical
   snapshot fields over complex dashboard-only expressions.

## Analytics capabilities to use

Stimulsoft can cover several analytics layers before custom code is needed:

| Need | Stimulsoft capability | Alterios rule |
|---|---|---|
| Simple totals | `Sum`, `Count`, `Avg`, `Max`, `Min`, `First`, `Last` expressions | Use for display totals after source rows are verified. |
| Group totals | Group headers/footers and aggregate expressions | Group in report when grouping is presentation-specific. |
| Running totals | Running total in dashboard data transformation or report expressions | Use only when sort order is explicit. |
| Percent of total | Data transformation "Show percentage" or expressions | Verify denominator against source view. |
| Top N / pagination-like analysis | Data transformation skip/limit | Good for dashboard cards, not for regulatory print totals. |
| Value normalization | Data transformation replace values | Use for labels; permanent business mapping should live in Alterios data. |
| Interactive filters | Combo Box, Date Picker, List Box, Tree View filters | Keep filter `Group` explicit when multiple independent charts exist. |
| Parameterized output | Report variables/dialog forms | Good for date ranges, organization, signatory, and current-record variants. |
| Master-detail print | Relations plus master/detail DataBands | Verify relation; without it, all details can print for every master row. |
| Charts/indicators | Dashboard charts, indicators, gauges, tables | Use for management analytics, not for strict print layout. |

## Static validation

Use the built-in checker before saving or after reading a template:

```powershell
alterios-stimulsoft-layout-check .\report-template.json --strict
```

Or through MCP:

```text
alterios_validate_stimulsoft_layout(report_id="<report-id>", profile="artx", project_id="<project-id>")
```

The checker currently flags:

- visible component overlap in the same parent container;
- component overflow beyond page width/height;
- zero or negative component sizes;
- growing/shrinking components with lower siblings that lack explicit
  `ShiftMode`;
- rows that mix dynamic and fixed-height behavior.

It is intentionally a preflight check. Final acceptance still requires render
verification: Stimulsoft preview/export or browser viewer plus source-data
comparison.

## Verification sequence

1. Read the current full report:

```http
GET /api/reports/full/{encode_filter({"_id":"<report-id>"})}
```

2. Save a local backup of the full report/template JSON.
3. Verify source rows with `get-data-simplified`.
4. Run `alterios-stimulsoft-layout-check`.
5. Save through `POST /api/reports` or `PUT /api/reports`.
6. Read the full report back and rerun the layout check on the saved template.
7. Open the UI/report viewer and verify the exact output scenario.
8. For printable forms, export/preview a representative page set:
   - short row;
   - long text row;
   - empty optional block;
   - page break;
   - group with one row;
   - group crossing a page boundary.

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Text overlaps the next block after long values | `CanGrow` without sibling shift or separate band | Move lower block to another band or set explicit `ShiftMode`. |
| Table row borders no longer match row text height | One cell grows while borders/siblings stay fixed | Make all row cells compatible and use `GrowToHeight` for visual frames. |
| Header is printed at page bottom without rows | Missing keep-together settings | Set header/detail/footer keep-together rules on the band/group. |
| Report shows stale/missing fields | Stimulsoft datasource was not refreshed after view change | Rebuild dictionary columns from the Alterios view. |
| Dashboard DatePicker gives unexpected totals | Source date type/filter semantics are not exact | Verify source DateTime and compare UI to API counts. |
| Embedded report ignores current record | Form cell lacks `openId=true` or verification used `contentId` | Add `openId=true` and verify with top-level `dataId: [openId]`. |
