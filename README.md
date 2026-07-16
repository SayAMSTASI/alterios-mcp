# alterios-mcp

`alterios-mcp` - MCP-сервер для работы с Alterios/LIMS из Codex и других MCP-клиентов.
Он нужен, чтобы инвентаризировать проекты Alterios, читать настройки, строить формы,
представления, скрипты, BPMN-процессы и отчеты, а также выполнять управляемую запись
с dry-run, явными gate-флагами и readback-проверкой.

Проект развивается как полноценный рабочий MCP для Alterios, а не как MVP. Основной
фокус - безопасная запись в проектную базу, при этом чтение и инвентаризация нужны
как обязательная подготовка перед изменениями.

## Для кого

- Для администратора Alterios, который хочет быстро проверить состав проекта,
  настройки форм, представлений, скриптов, диаграмм, отчетов и меню.
- Для разработчика или аналитика, который через Codex проектирует и изменяет
  структуру Alterios без ручной рутины в интерфейсе.
- Для проектной команды, которой нужны воспроизводимые изменения: dry-run, запись,
  readback, отчет о проверке и понятный журнал статуса.
- Для автора пользовательских и администраторских инструкций, которому нужно
  получать проверенные факты из проекта, а не описывать систему вручную.

## Что умеет сейчас

Текущая поверхность MCP: **75 инструментов**, из них **35 write-like инструментов**.
Полная матрица методов ведется в [docs/alterios-method-coverage.md](docs/alterios-method-coverage.md).

### Профили и проекты

- Поддержка нескольких экземпляров Alterios через профили.
- Один профиль = один экземпляр Alterios: base URL, авторизация, токен,
  endpoint-шаблоны и таймауты.
- Один экземпляр Alterios может содержать много проектов.
- Инструменты уровня проекта принимают явный `project_id`; профиль не подменяет
  проект и не должен использоваться как скрытый выбор рабочей области.
- Есть smoke-проверка всех профилей и default-проектов.

MCP можно подключать к разным экземплярам Alterios/LIMS, если они совместимы
по REST API, auth scheme и правам токена. Для нового экземпляра добавляется
отдельный profile, затем выполняются `alterios-discover --profiles --json`,
`alterios-profile-smoke --json` и read-only inventory нужного проекта. Запись
разрешается только после dry-run и sandbox readback на этом конкретном
экземпляре; route variants и project scoping у разных установок могут
отличаться.

### Инвентаризация project base

MCP умеет собирать состав проекта:

- проекты экземпляра;
- типы материалов и поля;
- представления, view entities и view fields;
- формы, tabs, rows, cells и action containers;
- группы меню и справки;
- контент, файлы и комментарии;
- скрипты, BPMN-диаграммы, процессы и задачи;
- отчеты и Stimulsoft-шаблоны;
- iconId и правила UI-действий.

Для глубоких срезов есть отдельные CLI:

- `alterios-deep-inventory` - формы, скрипты, BPMN-связи и иконки;
- `alterios-project-health` - быстрый read-only preflight перед записью:
  cache inventory, diff с прошлым snapshot и health по forms/views/scripts/BPMN/reports;
- `alterios-form-surface-check` - проверка формы на layout/F-pattern,
  источники данных, роли, стили и действия;
- `alterios-stimulsoft-layout-check` - статическая проверка Stimulsoft layout
  на пересечения, выход за страницу и риски динамической высоты;
- `alterios-runtime-info` - fingerprint запущенного MCP: commit, путь к
  исходникам, PID, время старта, версии схемы tools/UX-контракта и hashes skills;
- `alterios-profile-smoke` - матрица профилей и project-route smoke.
- `alterios-replay-smoke` - локальная/read-only проверка MCP после обновления:
  tool registry, write gates, dry-run `plan_id`, form-surface, Stimulsoft layout
  и классификация risky routes.

### Запись в Alterios

Основные write-сценарии уже закрыты типизированными инструментами:

- сценарное создание модуля материала: тип материала, поля, представление,
  add/edit/list формы и группа меню через `alterios_create_material_module`;
- сценарное создание вкладки отчета: source view, Project Database report,
  form tab, `openId` и `dataId`-проверка через `alterios_create_report_tab`;
- сценарное создание процесса: task-form, script refs, BPMN XML, `camunda:formKey`,
  start-process smoke и optional task complete через `alterios_create_process_flow`;
- создание и обновление типов материалов;
- создание и обновление полей;
- создание контента;
- обновление значений существующего контента;
- загрузка файла в file-field;
- создание и обновление групп меню;
- создание и обновление справок;
- создание и обновление представлений, view entities и view fields;
- создание и обновление форм;
- точечная замена `tabs` и `formActionContainers`;
- точечная настройка `emitting.listeners` у ячейки формы;
- массовое обновление выбранных content rows по `selected_content_ids`;
- создание и обновление web/cron/manual/event/library/diagram scripts;
- запуск manual script;
- создание и обновление BPMN-диаграмм;
- запуск процесса, чтение задач, завершение задачи, проверка side effects;
- создание и обновление отчетов;
- patch Stimulsoft template;
- создание комментариев;
- security-операции users/user-groups/roles и delete через отдельные typed tools
  с dangerous-gate, expected-проверками и readback; role/user-group
  create/update/delete live-проверены в sandbox, disposable user create/delete
  live-проверен через UI и API cleanup-readback;
- native content-type publish flags через `/api/content-types/save`;
  cross-project transfer имеет route evidence (`GET /api/content-types?share=true`,
  `POST /api/content-types/clone`), но live clone остается gated до отдельного
  target sandbox project.

Есть generic-инструменты `alterios_rest_write` и `alterios_call_write_service`,
но для штатной работы предпочтительны типизированные инструменты: они знают контекст,
проверяют цель, формируют dry-run audit и делают readback там, где API это позволяет.
Dry-run write tools сохраняют проверяемый `plan_id` в `artifacts/write-plans`,
а execution events пишутся в `artifacts/write-journal`; generic
`alterios_rest_write`, `alterios_create_material_module` и
`alterios_create_report_tab`, `alterios_create_process_flow` при
`dry_run=false` требуют совпадающий `plan_id`. Сценарные apply также требуют
`delivery_evidence` со ссылкой на Gitea-задачу, ссылками на handoff агентов и
активной версией UX-контракта. Устаревший runtime блокирует запись до перезапуска.

### Формы и пользовательский UI

MCP учитывает не только JSON формы, но и пользовательский смысл поверхности:

- тип формы: `main`, `list`, `add`, `edit`, `detail`, `task`;
- вкладки, строки, ячейки и пустые места;
- `field`, `view_data`, `view_data_list`, `report`, `comments_list`,
  help/rich/html-контент;
- источники данных: `openId`, `dataId`, `viewEntityId`, view/report binding;
- условия отображения, роли, стили, параметры;
- порядок действий: редактировать, просмотр, удалить;
- compact icon-first кнопки и меню строки через троеточие;
- стандарт иконок Google Fonts Icons.

Правила иконок описаны в [docs/alterios-icon-standards.md](docs/alterios-icon-standards.md).

### Скрипты, BPMN и задачи

MCP умеет связывать:

- manual scripts;
- event scripts;
- diagram scripts;
- form actions, которые запускают скрипты;
- BPMN `scriptTask`, service/listener refs и `userTask`;
- `camunda:formKey` и task forms;
- процессы, задачи и side effects по данным.

Для сборки процесса как одного сценария используйте `alterios_create_process_flow`: dry-run валидирует
task-form, script refs, BPMN/formKey и сохраняет `plan_id`; apply по этому плану сохраняет форму и
диаграмму, а при переданном `content_id` выполняет process smoke с чтением активной задачи.

Правила связей scripts/forms/BPMN входят в skill
`alterios-script-bpmn-flow`. Снимки конкретных проектов хранятся только локально
или в приватном рабочем контуре.

### Отчеты и Stimulsoft

Поддержаны отчеты на Project Database:

- создание/обновление отчета;
- patch JSON-шаблона;
- чтение full report;
- проверка связи отчета с представлением;
- проверка current-record контекста через `dataId: [openId]`;
- статическая проверка геометрии Stimulsoft-компонентов;
- рендер печатного шаблона в Chromium и PDF-evidence через
  `alterios_validate_printable_render`;
- печатный `type=report` с `StiPage` и bands по умолчанию; dashboard создается
  только при явном `report_type=dashboard`;
- правила размещения элементов, чтобы они не съезжались в печатной форме.

Подробный playbook: [docs/stimulsoft-report-layout-and-analytics.md](docs/stimulsoft-report-layout-and-analytics.md).
Машиночитаемые правила: [docs/ux-contract.json](docs/ux-contract.json),
описание контракта: [docs/ux-contract.md](docs/ux-contract.md).

### Агенты и skills

В репозитории есть рабочий набор Alterios skills:

- `alterios-project-base-inventory`;
- `alterios-business-requirements-analyst`;
- `alterios-field-types`;
- `alterios-form-view-surface`;
- `alterios-ui-icons-and-actions`;
- `alterios-script-bpmn-flow`;
- `alterios-write-tools`;
- `alterios-stimulsoft-project-db`;
- `alterios-safety-verifier`;
- `alterios-pm-control-loop`.

Агент **Business/System Analyst / Аналитик требований** формализует бизнес-запрос
в постановку или ТРЗ: роли, сценарии, типы материалов, поля, представления,
формы, скрипты, BPMN, отчеты, acceptance criteria и open questions. Его
repo-owned skill: `alterios-business-requirements-analyst`.

Отдельно добавлен агент **Documentation Scribe / Писарь** для подготовки
пользовательских и администраторских инструкций по ГОСТ/ЕСПД и ГОСТ 34. Он
использует установленный skill `gost-documentation-builder` и локальный Alterios
playbook: [docs/gost-documentation-scribe-agent.md](docs/gost-documentation-scribe-agent.md).

Матрица агентов и ролей: [docs/agents-and-skills.md](docs/agents-and-skills.md).

### Приватное рабочее поле Gitea

Для реальных бизнес-задач, которые нельзя светить в публичном `alterios-mcp`,
поддержан private Gitea workboard:

- `gitea_workboard_config` и `gitea_workboard_probe` проверяют конфиг и доступ;
- `gitea_list_work_items` читает задачи;
- `gitea_sync_standard_labels` синхронизирует стандартные labels;
- `gitea_create_sprint` создает milestone как sprint;
- `gitea_list_sprint_tasks` читает задачи sprint/milestone;
- `gitea_create_work_item` создает private issue;
- `gitea_add_agent_report` добавляет отчет агента в issue;
- `gitea_transition_issue_stage` меняет статус issue через замену одного `stage:*`
  label с API-readback и сохранением остальных labels;
- `gitea_sync_board_by_labels` строит dry-run план и, при включенном gate,
  переносит карточки Projects board по labels `stage:*`.

Для ручного запуска и запуска по расписанию есть CLI:

```powershell
gitea_transition_issue_stage 1 verify --dotenv C:\path\to\private\.env --pretty
gitea_transition_issue_stage 1 verify --dotenv C:\path\to\private\.env --apply --pretty
gitea_sync_board_by_labels --dotenv C:\path\to\private\.env --project-id 3 --pretty
gitea_sync_board_by_labels --dotenv C:\path\to\private\.env --project-id 3 --apply --pretty
```

По умолчанию это dry-run. При `--apply` нужен `GITEA_MCP_ALLOW_WRITE=1`.
Надежный статус задачи - это label `stage:*`; Projects board синхронизируется
из labels, когда доступен board API или web-session bridge.
Если Gitea не публикует board API, для web-переноса нужны
`GITEA_BOARD_COOKIE_FILE` или `GITEA_BOARD_COOKIE_HEADER`; эти значения хранятся
только в private `.env`.

Запись в Gitea имеет отдельный gate `GITEA_MCP_ALLOW_WRITE=1`; он не связан с
`ALTERIOS_MCP_ALLOW_WRITE`, чтобы не смешивать Alterios live-write и публикацию
задач в private workboard.

Если Git…19071 tokens truncated…апускать unit tests, targeted smoke, `git diff --check`;
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
