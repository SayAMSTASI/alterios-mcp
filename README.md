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

Текущая поверхность MCP: **74 инструмента**, из них **35 write-like инструментов**.
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
- `alterios-form-surface-check` - проверка формы на layout/F-pattern,
  источники данных, роли, стили и действия;
- `alterios-stimulsoft-layout-check` - статическая проверка Stimulsoft layout
  на пересечения, выход за страницу и риски динамической высоты;
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
- создание и обновление manual/event/diagram scripts;
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
`dry_run=false` требуют совпадающий `plan_id`.

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

Связующая карта лежит в [docs/script-bpmn-linkage.md](docs/script-bpmn-linkage.md).

### Отчеты и Stimulsoft

Поддержаны отчеты на Project Database:

- создание/обновление отчета;
- patch JSON-шаблона;
- чтение full report;
- проверка связи отчета с представлением;
- проверка current-record контекста через `dataId: [openId]`;
- статическая проверка геометрии Stimulsoft-компонентов;
- правила размещения элементов, чтобы они не съезжались в печатной форме.

Подробный playbook: [docs/stimulsoft-report-layout-and-analytics.md](docs/stimulsoft-report-layout-and-analytics.md).

### Агенты и skills

В репозитории есть рабочий набор Alterios skills:

- `alterios-project-base-inventory`;
- `alterios-form-view-surface`;
- `alterios-ui-icons-and-actions`;
- `alterios-script-bpmn-flow`;
- `alterios-write-tools`;
- `alterios-stimulsoft-project-db`;
- `alterios-safety-verifier`;
- `alterios-pm-control-loop`.

Отдельно добавлен агент **Documentation Scribe / Писарь** для подготовки
пользовательских и администраторских инструкций по ГОСТ/ЕСПД и ГОСТ 34. Он
использует установленный skill `gost-documentation-builder` и локальный Alterios
playbook: [docs/gost-documentation-scribe-agent.md](docs/gost-documentation-scribe-agent.md).

Матрица агентов и ролей: [docs/agents-and-skills.md](docs/agents-and-skills.md).

## Безопасность записи

Запись выключена по умолчанию.

Чтобы изменение реально ушло в Alterios, должны совпасть условия:

1. Передан явный `profile`.
2. Для project-level инструментов передан явный `project_id`.
3. Инструмент вызван с `dry_run=false`.
4. В окружении включен `ALTERIOS_MCP_ALLOW_WRITE=1`.
5. Для destructive/security маршрутов дополнительно включен
   `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`.
6. Для destructive/security вызова дополнительно передан `allow_destructive=true`.

Если условия не выполнены, write-инструменты возвращают dry-run audit и не
выполняют сетевую запись.

Перед неизвестными, destructive или permission-changing маршрутами используйте
`alterios_write_safety_preflight`: он классифицирует proposed REST route без
network request и показывает, какие gate-флаги понадобятся.

## Быстрый старт

### 1. Установка

```powershell
git clone https://github.com/<owner>/alterios-mcp.git
cd alterios-mcp
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

### 2. Приватный конфиг

Секреты не должны попадать в репозиторий. Предпочтительный вариант - хранить
приватный dotenv вне папки проекта и передавать путь через `ALTERIOS_DOTENV_PATH`.

Пример приватного файла:

```dotenv
ALTERIOS_PROFILE=primary
ALTERIOS_PROFILES=primary,secondary

ALTERIOS_PRIMARY_BASE_URL=https://alterios-primary.example.local
ALTERIOS_PRIMARY_API_TOKEN=put-token-here
ALTERIOS_PRIMARY_PROJECT_ID=put-optional-default-project-id-here
ALTERIOS_PRIMARY_ENDPOINT_TEMPLATE={base_url}/api/scripts/execute-manual
ALTERIOS_PRIMARY_BODY_STYLE=manual_script
ALTERIOS_PRIMARY_AUTH_HEADER=x-api-key
ALTERIOS_PRIMARY_AUTH_SCHEME=
ALTERIOS_PRIMARY_TIMEOUT_SECONDS=20

ALTERIOS_SECONDARY_BASE_URL=https://alterios-secondary.example.local
ALTERIOS_SECONDARY_API_TOKEN=put-token-here
ALTERIOS_SECONDARY_PROJECT_ID=put-optional-default-project-id-here
ALTERIOS_SECONDARY_ENDPOINT_TEMPLATE={base_url}/api/scripts/execute-manual
ALTERIOS_SECONDARY_BODY_STYLE=manual_script
ALTERIOS_SECONDARY_AUTH_HEADER=Authorization
ALTERIOS_SECONDARY_AUTH_SCHEME=Bearer
ALTERIOS_SECONDARY_TIMEOUT_SECONDS=20

ALTERIOS_MCP_ALLOW_WRITE=0
```

Подключить файл в текущей PowerShell-сессии:

```powershell
$env:ALTERIOS_DOTENV_PATH = "C:\path\to\private\alterios.env"
```

### 3. Проверка профилей

```powershell
.\.venv\Scripts\alterios-profile-smoke.exe --json
```

Проверка MCP после обновления без записи:

```powershell
.\.venv\Scripts\python.exe -m alterios_mcp.replay_smoke --json --profile artx --project-id 4e247a6b-55ef-4665-b88c-3c156fee19ba
```

Минимальная локальная проверка конфигурации без записи:

```powershell
.\.venv\Scripts\alterios-discover.exe --profiles --json
```

### 4. Запуск MCP-сервера

Локально:

```powershell
.\.venv\Scripts\alterios-mcp.exe
```

Пример подключения в Codex MCP config:

```toml
[mcp_servers.alterios]
command = "C:\\path\\to\\alterios-mcp\\.venv\\Scripts\\alterios-mcp.exe"
args = []
startup_timeout_sec = 60
tool_timeout_sec = 120

[mcp_servers.alterios.env]
ALTERIOS_DOTENV_PATH = "C:\\path\\to\\private\\alterios.env"
```

Fallback через Python:

```toml
[mcp_servers.alterios]
command = "C:\\path\\to\\alterios-mcp\\.venv\\Scripts\\python.exe"
args = ["-m", "alterios_mcp.server"]
startup_timeout_sec = 60
tool_timeout_sec = 120

[mcp_servers.alterios.env]
ALTERIOS_DOTENV_PATH = "C:\\path\\to\\private\\alterios.env"
```

## Как выполнять запись

Рабочий порядок такой:

1. Проверить профиль и проект через `alterios_config` или `alterios-profile-smoke`.
2. Вызвать нужный write-инструмент в dry-run режиме.
3. Проверить audit: целевой объект, route, diff, gate status, ожидаемый readback.
4. Включить `ALTERIOS_MCP_ALLOW_WRITE=1` только для безопасной целевой среды.
5. Повторить вызов с `dry_run=false`.
6. Проверить readback через тот же инструмент или отдельный read-only tool.
7. Зафиксировать результат в `docs/project-status.md`, если это часть этапа работ.

Для destructive/security операций нужен отдельный read-only анализ target,
dry-run typed tool или `alterios_write_safety_preflight`, затем явные gates:
`ALTERIOS_MCP_ALLOW_WRITE=1`, `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`,
`allow_destructive=true`. Cross-project native content-type clone не выполняется
без явного target sandbox project, dry-run review, cleanup/readback-плана и
подтвержденного route evidence.

## Основные пользовательские сценарии

### Инвентаризировать проект

Используйте read-only tools и `alterios-deep-inventory`, чтобы получить список
форм, представлений, скриптов, диаграмм, отчетов, связей и иконок. Результаты
можно использовать как source map для последующих изменений.

### Построить тип материалов

MCP может создать content type, поля, форму добавления/редактирования, list/main
view, группу меню и тестовую запись. Запись выполняется через dry-run -> write
gate -> readback.

### Доработать форму

MCP анализирует расположение элементов, пустые места, источники данных, роли,
стили, условия, действия и иконки. После анализа можно точечно заменить tabs или
action containers без полной ручной пересборки формы.

### Связать форму, скрипт и BPMN

MCP может показать, какие действия формы запускают скрипты, какие userTask
открывают формы, какие scriptTask/listeners ссылаются на scripts и какие side
effects надо проверить после запуска процесса или завершения задачи.

### Сделать отчет или печатную форму

MCP помогает подключить Project Database source, проверить source view, openId
контекст, Stimulsoft layout и риски съезда элементов. Для визуального финального
приемочного контроля пока нужен отдельный render/UI proof.

### Подготовить инструкцию пользователя или администратора

Documentation Scribe собирает проверенные факты из проекта, отделяет подтвержденное
от предположений и оформляет инструкции в понятной структуре. Для ГОСТ-ориентированных
документов используется `gost-documentation-builder`.

## Проверка проекта

Перед коммитом запускайте:

```powershell
.\.venv\Scripts\python.exe -m alterios_mcp.replay_smoke --json
.\.venv\Scripts\python -m pytest
git diff --check
```

Для проверки README и документов на случайные секреты:

```powershell
rg -n "(Bearer\s+[A-Za-z0-9._-]{20,}|\bsk-[A-Za-z0-9]{20,}|ALTERIOS_[A-Z0-9_]*=.*[A-Za-z0-9]{30,}|password\s*=\s*[^<\s].{8,})" README.md docs
```

Выход `rg` с кодом `1` означает, что совпадений не найдено.

## Документы

- [docs/project-status.md](docs/project-status.md) - текущий статус, этапы,
  проверки, риски и ближайшие действия.
- [docs/controlled-writes.md](docs/controlled-writes.md) - правила безопасной
  записи.
- [docs/administrator-guide.md](docs/administrator-guide.md) - инструкция
  администратора по установке, настройке, безопасной записи, проверкам и
  сопровождению MCP.
- [docs/expanded-user-scenarios.md](docs/expanded-user-scenarios.md) -
  расширенные сценарии: диаграммы, представления, группы, пользователи, роли,
  включения, файлы, действия, listeners, множественный выбор, отчеты, скрипты и
  публикация типов материалов.
- [docs/optimization-plan.md](docs/optimization-plan.md) - план оптимизации:
  сценарные tools, UI/report validation, write workflow и inventory cache/diff
  health.
- [docs/alterios-method-coverage.md](docs/alterios-method-coverage.md) - матрица
  инструментов, route patterns и operation classes.
- [docs/live-write-evidence-2026-07-10.md](docs/live-write-evidence-2026-07-10.md) -
  live evidence по publish flags, role/user-group security delete,
  disposable user create/delete и cross-project clone route.
- [docs/ui-har-write-evidence-2026-07-10.md](docs/ui-har-write-evidence-2026-07-10.md) -
  UI-visible evidence, route snippets и API readback по user create/delete и
  content-type transfer boundaries.
- [docs/form-surface-inventory.md](docs/form-surface-inventory.md) - инвентаризация
  форм.
- [docs/script-bpmn-linkage.md](docs/script-bpmn-linkage.md) - связи scripts,
  forms и BPMN.
- [docs/stimulsoft-report-layout-and-analytics.md](docs/stimulsoft-report-layout-and-analytics.md) -
  правила отчетов и Stimulsoft layout.
- [docs/agents-and-skills.md](docs/agents-and-skills.md) - роли агентов и skills.
- [docs/skill-installation.md](docs/skill-installation.md) - установка repo-owned
  skills в локальный Codex.

## Следующие направления

Новые работы фиксируются в `docs/project-status.md` и проходят через replay smoke,
targeted tests, `git diff --check` и secret scan.

1. Создать отдельный target sandbox project для live-проверки
   `POST /api/content-types/clone` и cleanup/readback после clone.
2. При необходимости экспортировать true HAR из DevTools для уже снятых
   UI-сценариев; текущий in-app browser connector дал UI/route/API evidence,
   но не raw HAR stream.
3. Расширить Stimulsoft-проверку до render/PDF/image comparison, когда будет
   доступен надежный экспорт или renderer.
4. Довести release packaging и changelog process, если репозиторий готовится к
   tagged release.
