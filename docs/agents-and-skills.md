# План агентов и skills

Этот документ задает рабочий контракт для мультиагентного режима в
`alterios-mcp`. Агенты не заменяют MCP tools: они разделяют исследование,
проектирование, реализацию и проверку так, чтобы работа по Alterios оставалась
воспроизводимой и проверяемой.

## Принцип

- Lead Engineer отвечает за итоговую интеграцию, проверки, commit/push и за то,
  что считается verified.
- PM Agent держит этапы, критерии приемки, риски и следующий шаг.
- Остальные агенты получают узкую область ответственности и возвращают
  проверяемый артефакт: матрицу, патч, отчет проверки, список рисков или
  готовый skill.
- Live write разрешается только через Lead Engineer gate: явный `profile`,
  явный `project_id`, dry-run, `ALTERIOS_MCP_ALLOW_WRITE=1`, readback.

## Матрица задач агентов

| Agent | Когда подключать | Основные задачи | Входы | Выходы | Пишет код/данные |
|---|---|---|---|---|---:|
| Lead Engineer | Всегда, как владелец сессии | Интегрирует вывод агентов, выбирает конечное решение, запускает проверки, коммитит и пушит | Все артефакты агентов, код, live evidence | Проверенный repo state, commit/push, краткий итог | Да |
| PM Control Loop | В начале этапа и после каждого проверенного среза | Разбить цель на этапы, зафиксировать acceptance criteria, вести статус, риски, блокеры, следующий шаг | Приватная Gitea, backlog, текущая цель пользователя | Обновленный статус, stage gate, список следующих задач | Только private workboard |
| Business/System Analyst / Аналитик требований | Когда запрос нужно превратить в постановку, ТРЗ, сценарии или developer handoff | Формализовать бизнес-цель, роли, сценарии, модель данных, views/forms/scripts/BPMN/reports, acceptance criteria, open questions и Stage 19 preflight | Запрос пользователя, inventory, `alterios_project_health`, UI/HAR evidence, договор/ТЗ/протокол при наличии | Постановка/ТРЗ, карта объектов, view/form/process/report requirements, acceptance checklist | Только docs |
| Project Base Explorer | Перед любыми изменениями project base или расширением покрытия | Read-only инвентаризация проектов, content types, fields, views, forms, scripts, diagrams, reports, files, comments, users/groups, tasks/processes; поиск route/response shape | `profile`, `project_id`, discovery JSON, live API read-only | JSON/MD матрицы, id/name map, route map, gaps | Нет |
| Data Model Engineer | При типах материалов, полях, связях, источниках данных | Проектировать content types/material types, persisted field types, refs, file fields, calc/spreadsheet/combined/person fields, `contentNameTemplate`, role/source constraints | Inventory, `alterios-field-types`, существующие content types/fields | Спецификация модели, field matrix, safe migration plan | Да, scoped |
| View Builder | При списках, представлениях, источниках для форм/отчетов | Проектировать views, view entities, joins, view fields, filters, sorts, display names, source fields, current-record context, `dataId/openId` behavior | Content model, view inventory, expected UI rows | View spec, view field matrix, get-data readback plan | Да, scoped |
| Form Surface Engineer | При карточках, списках, add/edit/detail/task/main формах | Проектировать tabs/rows/cells, `field`, `view_data`, `view_data_list`, `report`, `comments_list`, `help/html/content`; убирать пустые места; соблюдать F-pattern; проверять roles, source, styles, conditions, params, `openId`, `viewEntityId` | Form inventory, view spec, UX rules | Form layout matrix, action matrix, patch plan | Да, scoped |
| UI Icons & Actions Reviewer | Перед сохранением форм, строковых действий, меню, process actions | Проверить Google Fonts Icons, `size=16`, `color=#4B77D1`, `iconId`, порядок действий `edit/view/delete`, меню с троеточием, смысл действия, когда не менять существующую иконку | Form/action matrix, icon standard, icon usage matrix | Icon/action review, список исправлений, validation notes | Нет |
| Script/BPMN Flow Integrator | При web/cron/manual/event/library/diagram scripts, form actions, BPMN/process/task side effects | Картировать scripts -> forms -> BPMN: args actions, `scriptTask`, listeners, service tasks, `camunda:formKey`, userTask forms, process start/task complete, data side effects | Script/BPMN linkage JSON, scripts, diagrams | Flow map, side-effect table, test scenario | Да, scoped |
| Report/Stimulsoft Specialist | При отчетах, печатных формах, dashboards, report tabs | Настроить Project Database datasource, view binding, openId report tabs, filters, dashboard widgets, printable layout, geometry/dynamic-height checks | View spec, report JSON, layout playbook | Report spec/template patch, layout validation, readback | Да, scoped |
| Documentation Scribe / Писарь | При инструкциях пользователя, администратора, эксплуатационных разделах и ГОСТ/ЕСПД оформлении | Выбрать ГОСТ 19 / ГОСТ 34 / ГОСТ Р 5979x базис, собрать карту разделов, оформить пользовательские и администраторские процедуры, зафиксировать недостающие источники и скриншоты | Verified docs, inventory matrices, UI/HAR evidence, screenshots, `gost-documentation-builder`, `docs/gost-documentation-scribe-agent.md` | Draft/fill map инструкции, список gaps, screenshot plan, compliance notes | Только docs |
| Write Tool Engineer | Когда повторяемое действие должно стать MCP tool | Реализовать typed write tool, schema, dry-run diff, write gate, target-id checks, readback, unit tests, CLI/MCP exposure | Verified workflow, route contract, safety rules | Код tool, tests, docs, examples | Да |
| Safety Verifier | Перед признанием результата verified | Проверить profile/project, secret redaction, no leaked tokens, dry-run/write gate, unit tests, diff check, live readback, UI/HAR evidence где нужно | Патчи, команды, live target, expected result | Verification report, residual risks, fail/pass | Нет |
| Skill Curator | После того как workflow доказан кодом или live sandbox | Создать/обновить repo-owned skill: triggers, workflow, safety rules, references, examples; убрать дублирование с другими skills | Проверенные docs/tools/matrices | `skills/<name>/SKILL.md`, refs, agent config | Да, scoped |

## Детализация агентов

### PM Control Loop

Задачи:

- держать один текущий этап и не смешивать несколько stage одновременно;
- формулировать критерии приемки до реализации;
- отделять verified, inferred, blocked и deferred;
- требовать от каждого агента конкретный output, а не общий пересказ;
- после интеграции обновлять статус и backlog.

Done:

- есть понятный следующий шаг;
- acceptance criteria измеримы;
- статус не скрывает открытые риски;
- завершенный этап связан с commit hash в следующем статусном срезе.

### Business/System Analyst / Аналитик Требований

Задачи:

- переводить бизнес-запрос в постановку или ТРЗ до проектирования и записи;
- отделять подтвержденные факты от предположений и неизвестных значений;
- описывать пользователей, роли, права, сценарии, ошибки и acceptance criteria;
- раскладывать будущую реализацию на Alterios-объекты: content types, fields,
  views, forms, scripts, BPMN, reports, groups, icons, users/roles;
- для представлений фиксировать source content type, `viewEntity`, joins,
  relation field, view fields, filters, sorts, `openId/dataId` и readback;
- перед live-write через сценарные tools требовать `alterios_project_health`
  без blocking errors;
- отдавать профильным агентам scoped handoff, а не общий пересказ задачи.

Done:

- есть структура постановки/ТРЗ с источниками, рисками и вопросами;
- требования проверяемы и имеют acceptance criteria;
- связи представлений описаны конкретными полями/joins, а не словами "связано";
- понятно, какие MCP tools будут использоваться и какие проверки нужны;
- live-write не запланирован без `profile`, `project_id`, health preflight,
  dry-run `plan_id` и readback.

### Project Base Explorer

Задачи:

- собирать список проектов на instance и не путать `profile` с `project_id`;
- строить id/name map по content types, fields, views, forms, groups, scripts,
  diagrams, reports;
- фиксировать route/method/scope/required params/response shape/common errors;
- находить реальные UI/API поверхности, а не только очевидные endpoints;
- сохранять reproducible JSON без секретов.

Done:

- read-only команды воспроизводимы;
- матрица содержит counts, ids, names, route evidence и read errors;
- проектная область не подменена дефолтным project id.

### Data Model Engineer

Задачи:

- проектировать типы материалов как устойчивую модель: content type, fields,
  field groups, display names, `contentNameTemplate`;
- выбирать persisted field type отдельно от виджета формы;
- учитывать `file`, `ref`, `calc`, `spreadsheet`, `comb`, `address`, `geo`,
  `bank`, `legal_entity`, `person`;
- проверять связи родитель/дочерние записи и источники данных для view/report;
- задавать правила миграции: создать новое, обновить существующее, не трогать
  чужое.

Done:

- есть field matrix с типами, `mname`, title, required, defaults, relation target;
- понятны поля для view/form/report;
- есть readback после создания или dry-run diff до записи.

### View Builder

Задачи:

- строить представления от project base, а не от догадок по UI;
- подбирать view entity и view fields под будущие формы/отчеты;
- проверять `get-data` и `get-data-simplified`;
- учитывать `dataId: [openId]` для контекстных списков и report tabs;
- не перегружать view полями, которые не используются в UX или отчетах.

Done:

- `get-data-simplified` возвращает ожидаемые строки и поля;
- view fields имеют понятные названия для пользователя;
- контекст текущей записи проверен отдельно от общего списка.

### Form Surface Engineer

Задачи:

- инвентаризировать все `tabs`, `rows`, `cells`, `formActionContainers`;
- размещать элементы без пустых зон и разрывов логики чтения;
- соблюдать F-pattern: важное слева/сверху, вложенные списки ниже контекста;
- проверять типы ячеек: `field`, `view_data`, `view_data_list`, `report`,
  `comments_list`, `help`, `content`, HTML/rich blocks;
- проверять action types: save/submit, open form, manual script, start process,
  delete, routing, report, task edit;
- учитывать `conditions`, `styles`, `displaying`, `params`, `openId`,
  `viewEntityId`, roles и source.

Done:

- нет пустых рядов/ячеек и случайных больших промежутков;
- list/add/edit/detail/task/main формы описаны отдельно;
- действия доступны в ожидаемом месте и не ломают порядок работы пользователя.

### UI Icons & Actions Reviewer

Задачи:

- использовать только Google Fonts Icons;
- держать базу `size=16`, `color=#4B77D1`;
- проверять `iconId` на форме, группе, действии и строковом меню;
- соблюдать стандартные смыслы: save, back, edit, view, delete, menu, info, add,
  sync, files;
- для строковых действий держать порядок: редактировать, просмотр, удалить;
- использовать меню с троеточием для вторичных действий;
- не заменять существующую иконку, если она уже корректно передает смысл.

Done:

- все action-like элементы имеют понятную иконку или осознанное исключение;
- нет текстовых кнопок там, где ожидается компактная иконка;
- delete не спутан с archive/close, view не спутан с edit.

### Интегратор Script/BPMN Flow

Задачи:

- разделять manual scripts, event scripts и diagram scripts;
- фиксировать, какие формы запускают какие scripts;
- описывать `args`, которые реально передаются action-ами;
- находить BPMN `scriptTask`, listeners, service tasks и refs на scripts;
- связывать `userTask` с формами через `camunda:formKey`;
- проверять side effects: create/update/delete content, task reassignment,
  process start, notification, log writes.

Done:

- есть карта script -> trigger -> args -> side effects -> readback;
- task flow можно повторить в sandbox;
- опасные side effects явно помечены до write.

### Специалист по отчетам и Stimulsoft

Задачи:

- подключать источники через Alterios Project Database, когда отчет строится от
  project base;
- проверять view binding и наличие нужных полей в datasource;
- различать dashboard, printable report и embedded report tab;
- проверять layout: overlap, overflow, dynamic-height risk, bands, page margins;
- проверять openId/current-record behavior через `dataId: [openId]`;
- не считать сохраненный JSON доказательством, если пользователю нужен UI/render.

Done:

- `report/full` подтверждает шаблон и datasource;
- source view возвращает строки;
- layout validator не находит критичных пересечений;
- для UI-critical отчета есть браузерная или render-проверка, либо риск открыт.

### Documentation Scribe / Писарь

Задачи:

- оформлять инструкции пользователя, администратора, эксплуатационные разделы и
  help/reference материалы на базе проверенных источников;
- выбирать стандартный базис: ГОСТ 19 для программных документов, ГОСТ 34 /
  ГОСТ Р 5979x для автоматизированной системы и эксплуатационного контура;
- использовать `gost-documentation-builder` как основной ГОСТ/ЕСПД skill и
  `docs/gost-documentation-scribe-agent.md` как локальный Alterios playbook;
- не начинать финальную редакцию без source map: README, controlled writes,
  private status records, inventory matrices, UI/HAR evidence, screenshots, договор/ТЗ
  или шаблон заказчика, если он есть;
- для инструкции пользователя описывать реальные рабочие сценарии: цель,
  предусловия, шаги, ожидаемый результат, сообщения и ошибки;
- для инструкции администратора описывать установку, запуск MCP, профили,
  `ALTERIOS_DOTENV_PATH`, write gates, диагностику, backup/recovery и
  эксплуатационные ограничения;
- делать fill map: раздел, источник, статус, вопрос, риск;
- помечать неизвестные факты как `Требует уточнения`, а не заменять их общими
  формулировками.

Done:

- выбран ГОСТ/ЕСПД или ГОСТ 34 базис и объяснено, почему он применим;
- есть структура документа и карта источников по разделам;
- пользовательская и администраторская инструкции разделены по аудитории;
- screenshots нужны только там, где они подтверждают действие, и список
  недостающих скриншотов явно указан;
- документ не содержит выдуманных ролей, URL, прав, сообщений, сроков,
  требований безопасности или приемочных критериев.

### Write Tool Engineer

Задачи:

- превращать повторяемые операции в typed tools, а не в одноразовые REST writes;
- добавлять schemas и ограничения по allowed fields;
- делать dry-run diff до live write;
- требовать `profile`, `project_id`, target checks и write gate;
- добавлять readback и unit tests;
- не смешивать destructive flows с обычными write tools.

Done:

- tool имеет dry-run по умолчанию;
- write требует `ALTERIOS_MCP_ALLOW_WRITE=1` и `dry_run=false`;
- тесты покрывают happy path, blocked write, validation errors и redaction;
- docs показывают safe usage.

### Safety Verifier

Задачи:

- проверять `config --profile <name>` перед write;
- запускать unit tests, targeted smoke, `git diff --check`;
- искать секреты в измененных файлах и generated artifacts;
- проверять readback после write;
- для UI-facing изменений требовать browser/UI evidence;
- удерживать destructive/security flows за отдельным gate.

Done:

- результат помечен verified только после конкретной команды/проверки;
- все остаточные риски названы;
- секреты не попали в commit/log/docs.

### Skill Curator

Задачи:

- создавать skill только после проверенного workflow;
- держать `SKILL.md` коротким: triggers, порядок работы, safety rules;
- подробные схемы, route examples и матрицы хранить в `references/`;
- не дублировать соседние skills;
- валидировать skill package и привязку к agents.

Done:

- skill не закрепляет гипотезу как факт;
- есть references на verified docs/tools;
- понятно, когда skill должен сработать и когда он не подходит.

## Рабочие Пайплайны

### Материалы, Представления И Формы

1. PM Control Loop задает stage и acceptance criteria.
2. Business/System Analyst формализует постановку, роли, сценарии и acceptance.
3. Project Base Explorer собирает текущие content types, fields, views, forms.
4. Data Model Engineer проектирует тип материала и поля.
5. View Builder собирает view и проверяет связи, поля, фильтры и `get-data`.
6. Form Surface Engineer размещает поля, списки, отчеты, комментарии и действия.
7. UI Icons & Actions Reviewer проверяет иконки и порядок действий.
8. Safety Verifier запускает проверки и readback.
9. Lead Engineer интегрирует, коммитит, пушит и обновляет статус.

### Scripts/BPMN/Tasks

1. Project Base Explorer собирает scripts, diagrams, forms, tasks/processes.
2. Script/BPMN Flow Integrator строит карту trigger -> args -> side effects.
3. Write Tool Engineer добавляет typed wrapper только для проверенного действия.
4. Safety Verifier проверяет dry-run, sandbox write/readback и task state.
5. Skill Curator обновляет `alterios-script-bpmn-flow`, когда workflow стабилен.

### Reports/Stimulsoft

1. View Builder подтверждает source view и поля.
2. Report/Stimulsoft Specialist собирает datasource/template/layout.
3. Safety Verifier проверяет `report/full`, source rows, layout validator и UI/render evidence.
4. Skill Curator обновляет `alterios-stimulsoft-project-db` после проверки.

### Инструкции Администратора И Пользователя

1. PM Control Loop фиксирует аудиторию, тип документа и acceptance criteria.
2. Business/System Analyst готовит постановку, структуру требований и open questions.
3. Project Base Explorer и профильные агенты передают проверенные источники:
   tools, routes, forms, scripts, BPMN, reports, screenshots и ограничения.
4. Documentation Scribe / Писарь выбирает ГОСТ 19 / ГОСТ 34 базис, составляет
   fill map и draft инструкции.
5. Safety Verifier проверяет, что документ не содержит секретов, неподтвержденных
   фактов, нечитабельных screenshots и смешения пользовательских/админских
   процедур.
6. Lead Engineer интегрирует документ в репозиторий, запускает проверки и
   обновляет статус.

### Новый MCP Tool

1. PM Control Loop фиксирует, зачем tool нужен и какую ручную рутину снимает.
2. Project Base Explorer подтверждает endpoint contract.
3. Write Tool Engineer реализует tool, tests и docs.
4. Safety Verifier проверяет dry-run/write-gate/readback/redaction.
5. Lead Engineer мержит, коммитит, пушит.

## Skills из репозитория

Skills добавляются только после того, как соответствующий workflow уже проверен
кодом или live sandbox. Иначе skill начнет закреплять догадки.

Рабочий набор repo-owned skills создан в `skills/`. Эти skills являются
тонкими диспетчерами: `SKILL.md` содержит триггеры, workflow, safety rules и
границы ответственности, а `references/source-map.md` указывает на проверенные
docs, JSON-матрицы, тесты и кодовые области.

| Skill | Когда создавать | Основной владелец | Что должен знать |
|---|---|---|---|
| `alterios-project-base-inventory` | После deep inventory project-base matrix | Project Base Explorer | Профиль, project_id, listandcount, object totals, route/readback evidence |
| `alterios-business-requirements-analyst` | После появления Stage 19 и документационного workflow | Business/System Analyst | Постановка/ТРЗ, сценарии, view/form/process/report requirements, acceptance criteria |
| `alterios-field-types` | После live-проверки типов полей и relation joins | Data Model Engineer | Persisted field types, relation settings, short mnames, material descriptions, field/view/form separation |
| `alterios-form-view-surface` | После локальной form inventory и JSON-матрицы | Form Surface Engineer | View links, form tabs/actions, no-gap layout, F-pattern, roles/source/styles |
| `alterios-ui-icons-and-actions` | После локальной icon matrix и UTF-8 icon standard | UI Icons & Actions Reviewer | Google Fonts Icons, size 16, `#4B77D1`, action meaning, iconId validation |
| `alterios-script-bpmn-flow` | После локальной linkage matrix и parser refs | Script/BPMN Flow Integrator | Script types, form actions, BPMN formKey/listeners/script refs, side effects |
| `alterios-write-tools` | После typed content/file/view/form/script/BPMN/report tools | Write Tool Engineer | Write-gate, dry-run diff, managed marker, readback |
| `alterios-stimulsoft-project-db` | После report/source validation tools | Report/Stimulsoft Specialist | Stimulsoft JSON, Project Database datasource, report_full readback, layout checks |
| `alterios-safety-verifier` | После scanner/test/readback workflow стабилизации | Safety Verifier | Tests, secret redaction, dry-run/write-gate, UI/HAR evidence |
| `alterios-pm-control-loop` | После стабилизации private workboard и stage format | PM Control Loop | Stage control, acceptance criteria, risks, next steps |

Business/System Analyst имеет отдельный repo-owned skill
`alterios-business-requirements-analyst`, потому что он формирует вход для всех
write-сценариев. Documentation Scribe / Писарь пока не дублирует
`gost-documentation-builder`: он использует установленный документный skill,
локальный playbook `docs/gost-documentation-scribe-agent.md` и, при DOCX,
document-render workflow. Отдельный repo-owned skill для Писаря стоит создавать
только после серии проверенных инструкций администратора/пользователя.

Формат каждого skill folder:

```text
skills/<skill-name>/
  SKILL.md
  agents/openai.yaml
  references/
```

## Формат передачи результата

Каждый агент должен возвращать результат в одном формате:

```text
Agent:
Scope:
Inputs:
Findings:
Artifacts:
Проверка:
Риски:
Дальше:
```

Минимальные требования:

- `Scope` должен быть узким: конкретный project, entity family, files или tool.
- `Artifacts` должны быть ссылками на файлы, JSON, commands или live ids.
- `Verification` должен содержать команду или readback, а не фразу "проверено".
- `Risks` не удаляются молча: PM переносит их в статус или backlog.

## Что Не Делаем

- Не добавляем skill, который описывает непроверенный API как факт.
- Не даем агентам право на live write без Lead Engineer gate.
- Не смешиваем runtime service names и manual script UUID.
- Не считаем JSON-save достаточной проверкой для форм и отчетов, если результат
  должен быть виден оператору в UI.
- Не расширяем число skills сверх проверенного repo-owned набора, пока не станет понятно,
  где реально есть дублирование или новая область ответственности.
