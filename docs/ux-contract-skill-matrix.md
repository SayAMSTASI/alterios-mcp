# Матрица skills и UX-контракта

Версия: `2026-07-17.2`.

Документ фиксирует, какие правила из skills являются блокирующими, какие требуют
live-evidence, а какие остаются рекомендациями. Единственный машинный источник
списка блокировок - `alterios_ux_contract` и `docs/ux-contract.json`.

## Классы правил

| Класс | Поведение |
|---|---|
| Hard | Нарушение блокирует strict validation и сценарный apply. |
| Evidence gate | Apply разрешен только после readback/UI/render/runtime evidence. |
| Advisory | Правило влияет на проектирование, но не может быть надежно определено по одному JSON. |
| Explicit exception | Отступление разрешено только по явному решению пользователя и фиксируется в work item. |

## Матрица по skills

| Skill | Hard UX-контракт | Evidence gate / advisory |
|---|---|---|
| `alterios-business-requirements-analyst` | Постановка и критерии приемки обязательны для live-сценария. | Mermaid-схема, роли и бизнес-термины проверяются аналитиком; это не form-JSON validation. |
| `alterios-field-types` | Новый тип материала и low-level upsert имеют осмысленное описание; поля получают пользовательскую подсказку; постоянная сноска допустима только для `date`; relation entity содержит join. | Тип, расширенные relation settings и фактический `mname` подтверждаются API readback и populated-data smoke. |
| `alterios-form-view-surface` | Нет пустых tabs/rows/cells; view работает в experimental/v2; встроенные views имеют field/current-record filter; отдельные list/add/edit/view формы; element actions edit/view совпадают кроме перехода в edit; заголовки человекочитаемы; таблица имеет centered+bold+10px header, нетабличная ячейка без header; технические колонки скрыты; view read-only. | F-pattern, плотность, необычный интерфейс и master-detail композиция требуют UI-проверки. |
| `alterios-ui-icons-and-actions` | Действия имеют project-local UUID `iconId`; registry-семантика соответствует действию; Google source size 16, SVG canvas 20px, цвет `#4B77D1`; element actions icon-only с tooltip; Close перед Save; row menu содержит Edit/View/Delete и View default; более трех element actions уходят в menu; print menu использует dropdown и открывает target в новой вкладке. | Неизвестный файл требует однократного deep file readback. Необычный существующий интерфейс меняется только с одобрением пользователя. |
| `alterios-script-bpmn-flow` | Manual script использует UUID, непустые argument bindings и однозначный `viewEntityId` для `__entity_id`. | Side effects, listener order, BPMN refs и аргументы подтверждаются sandbox/process smoke. |
| `alterios-stimulsoft-project-db` | Печатная форма открывается в новой вкладке и имеет Close; printable по умолчанию является report, не dashboard. | Источник Project Database, openId, непустой render и PDF/image layout подтверждаются render evidence. |
| `alterios-write-tools` | Dry-run plan_id, write gates, UX version, runtime fingerprint и project-local icon IDs обязательны для apply. | Readback, write journal и rollback notes обязательны после записи. |
| `alterios-safety-verifier` | Все коды из `alterios_ux_contract` являются stage gate. | Проверяет target profile/project, secrets scan, tests, git diff и live evidence. |
| `alterios-project-base-inventory` | Перед write известны профиль, project_id и существующие объекты, чтобы не создать дубликаты. | Inventory/cache/diff используются как evidence, а не как UI-правило. |
| `alterios-pm-control-loop` | Live apply требует private work item и handoff ролей analyst/implementer/verifier. | PM ведет stage/status и не блокирует мелкие read-only операции. |

## Явные исключения

- Legacy/classic view допускается только для типа представления, который реально
  не работает в experimental/v2, после UI/API evidence и решения пользователя.
- Глобальный embedded list без current-record фильтра допускается только по
  явному бизнес-требованию.
- Короткий видимый текст разрешен у утвержденного master-detail action hub с
  `position=top_center`; обычные действия элемента остаются icon-only.
- Намеренно своеобразный существующий интерфейс не перепроектируется без
  отдельного согласования.

## Контроль рассинхронизации

Тесты обязаны сравнивать версию и blocking codes между
`src/alterios_mcp/ux_contract.py`, `docs/ux-contract.json` и
`docs/ux-contract.md`. Добавление нового hard-правила без обновления всех трех
источников считается ошибкой сборки.
