# Правила report tab и openId в UI

Дата: 2026-07-10
Profile: `artx`
Project: `<sandbox-project-id>`

Документ фиксирует live experiments по встраиванию Alterios report во вкладку
формы с контекстом текущей записи.

## Live-изменения в sandbox

Обновлен воспроизводимый practice script:

- file: `scripts/artx_practice_metadata.py`;
- edit form id: `15f5fb26-5db4-4153-8131-23a54411cd63`;
- static report id: `86ad4189-deaf-4744-96d5-6b1d22e73468`;
- openId data-bound report id: `49236112-3335-4ca4-9a85-7f2236f6365a`;
- primary content id: `bd51e83f-201e-4d53-bdc6-c4cd16754756`;
- control content id: `b69e914d-9250-4672-ac81-047fdce887f8`;
- additional content id: `9a504330-5ce4-4a76-9043-bbc2fc293e3c`.

В edit form добавлена вторая вкладка с report cell:

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

| Проверка | Результат |
|---|---|
| `edit_form_openid_report_tab` | `true` |
| openId data-bound report full readback | `true` |
| openId report has dashboard page | `true` |
| openId report has Project Database source | `true` |
| openId report template references title column | `true` |
| source view row count without context | `3` |
| UI tab visible | yes |
| embedded Stimulsoft viewer render | не подтвержден: in-app browser показывает пустой `viewer_*` container и для static, и для data-bound report |

## Проверка контекста

Source view: `cfd46277-d8da-4b7d-ba0e-7c96ea85046e`.

Первый openId experiment использовал две строки. Позже добавлена третья
sandbox row, чтобы правило context scoping оставалось проверяемым при трех
строках source view.

| Request shape | Row count | Значение |
|---|---:|---|
| `POST /api/views/v2/get-data` без context | 3 | Полный source view. |
| `POST /api/views/v2/get-data` с `contentId=<additional>` | 3 | Один `contentId` не ограничил view. |
| `POST /api/views/v2/get-data` с `dataId=[<primary>]` | 1 | Current-record context работает. |
| `POST /api/views/v2/get-data` с `dataId=[<control>]` | 1 | Другой openId ограничивает свою строку. |
| `POST /api/views/v2/get-data` с `dataId=[<additional>]` | 1 | Третья строка следует тому же правилу. |
| `POST /api/views/v2/get-data-simplified` без context | 3 | Полный source view так, как его видит report source. |

## Выученные правила

1. Report внутри формы - обычная form cell с `type = "report"`.
2. Минимальные параметры report cell: `reportId` и обычно `fullscreenMode`.
3. Для привязки к открытой записи добавляется `params.openId = true`.
4. Такую cell нужно размещать в edit/detail form, открытой с реальным `openId`;
   main menu form не обязательно имеет current-record context.
5. Для embedded view/report context current-record scoping соответствует
   `dataId: [openId]`. Не полагайтесь только на `contentId`.
6. Data-bound dashboard report можно создавать с Project Database source и
   `StiTextElement`, привязанным к title field source view.
7. Embedded report viewer требует отдельной renderer-диагностики: report cell
   создает `viewer_*` container, но он остается пустым в последней browser
   check. Не считать это visual proof, пока static или data-bound template не
   отрендерится.

## Операционный паттерн

1. Проверить profile и project перед записью.
2. Patch form `tabs` через typed form tool или reproducible setup script.
3. Прочитать form JSON обратно и проверить `params.openId=true`.
4. Проверить source view минимум с двумя строками.
5. Сравнить no-context, `contentId` и `dataId: [openId]` requests.
6. Открыть edit form URL с `openId=<content-id>`, перейти на report tab и
   подтвердить Stimulsoft render.
7. Если вкладка активна, но `viewer_*` div пустой, диагностировать viewer
   отдельно от template: static report render, console/network behavior, потом
   уже заявлять UI-level data binding.
