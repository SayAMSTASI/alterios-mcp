# Forward-test skills, 2026-07-10

Проверка использовала трех read-only subagents с реалистичными задачами
Alterios. Live-запись в Alterios не выполнялась.

## Сценарии

| Сценарий | Skills | Результат |
|---|---|---|
| Read-only инвентаризация нового проекта и PM handoff | `alterios-project-base-inventory`, `alterios-pm-control-loop` | Пройдено с улучшениями: добавлены project-scoped inventory output и PM handoff template. |
| Task form с `view_data_list`, `manual_script`, `start_process` и row icons | `alterios-form-view-surface`, `alterios-ui-icons-and-actions`, `alterios-script-bpmn-flow` | Пройдено с улучшениями: добавлены проверки relation/view source, field label/displaying, разрешение UUID `iconId` и разделение UI `start_process` от runtime service `startProcess`. |
| Запись и проверка Stimulsoft report на Project Database | `alterios-write-tools`, `alterios-stimulsoft-project-db`, `alterios-safety-verifier` | Пройдено с улучшениями: существующие report tools, targeted tests и риск renderer теперь явно описаны в skills. |

## Изменения после forward-test

- Добавлен `skills/alterios-project-base-inventory/references/inventory-pm-template.md`.
- Inventory workflow использует `artifacts/inventories/<profile>/<project_id>` для exploratory project inventories.
- Installer переписывает установленные `source-map.md` на абсолютные пути репозитория.
- Уточнены проверки источников `view_data` / `view_data_list`, labels и `displaying` у полей.
- Уточнена обработка UUID-like `iconId`.
- UI-действия `start_process` отделены от script runtime service calls `startProcess`.
- Stimulsoft typed report tools и риск embedded viewer сделаны явными.
- В safety guidance названы targeted write/report tests.

## Оставшиеся разрывы

- Endpoint registry для UUID-иконок пока не документирован как стабильный API.
  До каталогизации использовать usage matrices или verified readback.
- Rendered PDF/image comparison для Stimulsoft остается в backlog; текущая
  layout validation является static preflight.
- Security/destructive flows требуют отдельного sandbox-сценария и dangerous gate.
