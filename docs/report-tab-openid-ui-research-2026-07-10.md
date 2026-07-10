# Report tab and openId UI rules

Date: 2026-07-10
Profile: `artx`
Project: `4e247a6b-55ef-4665-b88c-3c156fee19ba`

This note records live experiments for embedding an Alterios report in a form
tab with current-record context.

## Live sandbox changes

Updated the reproducible practice script:

- file: `scripts/artx_practice_metadata.py`;
- edit form id: `15f5fb26-5db4-4153-8131-23a54411cd63`;
- static report id: `86ad4189-deaf-4744-96d5-6b1d22e73468`;
- openId data-bound report id: `49236112-3335-4ca4-9a85-7f2236f6365a`;
- primary content id: `bd51e83f-201e-4d53-bdc6-c4cd16754756`;
- control content id: `b69e914d-9250-4672-ac81-047fdce887f8`.

The edit form has a second tab with a report cell:

```json
{
  "name": "Otchet openId",
  "rows": [
    {
      "cells": [
        {
          "name": "Otchet openId",
          "type": "report",
          "params": {
            "openId": true,
            "reportId": "49236112-3335-4ca4-9a85-7f2236f6365a",
            "fullscreenMode": false
          }
        }
      ]
    }
  ]
}
```

## Readback

| Check | Result |
|---|---|
| `edit_form_openid_report_tab` | `true` |
| openId data-bound report full readback | `true` |
| openId report has dashboard page | `true` |
| openId report has Project Database source | `true` |
| openId report template references title column | `true` |
| source view row count without context | `2` |
| UI tab visible | yes |
| embedded Stimulsoft viewer render | not currently confirmed; the in-app browser shows an empty `viewer_*` container for both the static and data-bound reports |

## Context checks

Source view: `cfd46277-d8da-4b7d-ba0e-7c96ea85046e`.

With two rows in the sandbox source, context behavior is visible through the
view API:

| Request shape | Row count | Meaning |
|---|---:|---|
| `POST /api/views/v2/get-data` without context | 2 | Full source view. |
| `POST /api/views/v2/get-data` with `contentId=<primary>` | 2 | `contentId` alone did not scope this view. |
| `POST /api/views/v2/get-data` with `dataId=[<primary>]` | 1 | Current-record context works. |
| `POST /api/views/v2/get-data` with `dataId=[<control>]` | 1 | A different openId scopes to its own row. |
| `POST /api/views/v2/get-data-simplified` without context | 2 | Full source view as the report source sees it. |

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
6. A separate data-bound dashboard report can be generated with the Project
   Database source and a `StiTextElement` bound to the source view title field.
   API readback confirms the report template, source, and title-field binding.
7. The embedded report viewer still needs renderer-level diagnosis: the report
   cell creates a `viewer_*` container, but the container remains empty in the
   latest browser check even for the static report. Do not treat this as visual
   proof of data-bound output until the viewer renders either the static or
   data-bound template again.

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
7. If the tab is active but the `viewer_*` div is empty, debug the report viewer
   separately from the report template: confirm static report render, inspect
   console/network behavior, and only then claim UI-level data binding.
