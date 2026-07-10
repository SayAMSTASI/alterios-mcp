# Report tab and openId UI rules

Date: 2026-07-10
Profile: `artx`
Project: `4e247a6b-55ef-4665-b88c-3c156fee19ba`

This note records a live UI experiment for embedding an Alterios report in a
form tab with current-record context.

## Live sandbox changes

Updated the reproducible practice script:

- file: `scripts/artx_practice_metadata.py`;
- form: `MCP Practice. Карточка записи`;
- form id: `15f5fb26-5db4-4153-8131-23a54411cd63`;
- report id: `86ad4189-deaf-4744-96d5-6b1d22e73468`;
- primary content id: `bd51e83f-201e-4d53-bdc6-c4cd16754756`;
- control content id: `b69e914d-9250-4672-ac81-047fdce887f8`.

The edit form now has a second tab:

```json
{
  "name": "Отчет openId",
  "rows": [
    {
      "cells": [
        {
          "name": "Отчет openId",
          "type": "report",
          "params": {
            "openId": true,
            "reportId": "86ad4189-deaf-4744-96d5-6b1d22e73468",
            "fullscreenMode": false
          }
        }
      ]
    }
  ]
}
```

Readback after live update:

| Check | Result |
|---|---|
| `edit_form_openid_report_tab` | `true` |
| source view row count without context | `2` |
| UI tab `Отчет openId` visible | yes |
| clicking tab renders Stimulsoft report | yes, `MCP Practice sandbox report` visible |

## Context checks

Source view: `cfd46277-d8da-4b7d-ba0e-7c96ea85046e`.

With two rows in the sandbox source, the context behavior is now visible:

| Request shape | Row count | Meaning |
|---|---:|---|
| `POST /api/views/v2/get-data` without context | 2 | Full source view. |
| `POST /api/views/v2/get-data` with `contentId=<primary>` | 2 | `contentId` alone did not scope this view. |
| `POST /api/views/v2/get-data` with `dataId=[<primary>]` | 1 | Current-record context works. |
| `POST /api/views/v2/get-data` with `dataId=[<control>]` | 1 | A different openId scopes to its own row. |
| `POST /api/views/v2/get-data-simplified` without context | 2 | Full source view as report source sees it. |

## Rules learned

1. A report inside a form is a normal form cell with `type = "report"`.
2. The minimal required report parameters are `reportId` and usually
   `fullscreenMode`.
3. To bind the report cell to the currently opened record, add
   `params.openId = true`.
4. Put this cell in an edit/detail form opened with an actual `openId`; a main
   menu form does not necessarily have a current-record context.
5. For embedded view/report context, current-record scoping maps to
   `dataId: [openId]`. Do not rely on `contentId` alone.
6. The UI can render the report in a named tab. The tested route was:
   `/workspace/<project>/group-viewer/<group>/form-viewer/<edit-form>?openId=<content-id>&menuAnchor=<group>`.
7. The current sandbox report template is mostly static. It proves that the
   report cell renders in the tab with `openId`, while data-level scoping was
   proven through the view-data API. To visually prove row-sensitive report
   output, the next step is a data-bound report template that displays the row
   title or id from the Project Database source.

## Operational pattern

Use this write/verify sequence:

1. Verify profile and project before writes.
2. Patch form `tabs` through the typed form tool or the reproducible setup
   script.
3. Read form JSON back and check the report cell has `params.openId=true`.
4. Verify the source view with at least two rows.
5. Compare no-context, `contentId`, and `dataId: [openId]` requests.
6. Open the edit form URL with `openId=<content-id>`, click the report tab, and
   confirm Stimulsoft renders.
