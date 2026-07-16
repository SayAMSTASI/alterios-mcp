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

Полная поверхность MCP: **101 инструмент**, из них **35 write-like инструментов**.
Рекомендуемый профиль `live` публикует клиенту 75 инструментов.
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
- `alterios-live-task-preflight` - быстрый read-only go/no-go перед live-задачей:
  явный профиль/проект, runtime freshness, delivery evidence, project health
  и replay smoke в одном отчете `ready/blocked`;
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

Если Gitea недоступна, используется локальный private workboard в файлах
пользователя:

- `local_workboard_config` показывает путь локальной доски;
- `local_workboard_init` создает структуру каталогов;
- `local_workboard_create_item` создает локальную задачу с dry-run по умолчанию;
- `local_workboard_list_items` читает локальный backlog/sprint;
- `local_workboard_add_agent_report` дописывает отчет агента.

Локальный workboard хранится вне public Git. Если каталог случайно создан внутри
repo, путь `workboard/` игнорируется Git.

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
ALTERIOS_MCP_TOOL_PROFILE=live
ALTERIOS_MCP_REQUIRED_AGENT_ROLES=analyst,implementer,verifier
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
.\.venv\Scripts\python.exe -m alterios_mcp.replay_smoke --json --profile secondary --project-id <sandbox-project-id>
```

Быстрая проверка проекта перед записью с локальным cache:

```powershell
.\.venv\Scripts\alterios-project-health.exe --profile secondary --project-id <sandbox-project-id> --refresh --json --pretty
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
ALTERIOS_MCP_TOOL_PROFILE = "live"
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
ALTERIOS_MCP_TOOL_PROFILE = "live"
```

## Как выполнять запись

Рабочий порядок такой:

1. Проверить профиль и проект через `alterios_config` или `alterios-profile-smoke`.
2. Перед сценарной live-записью запустить `alterios_live_task_preflight` по
   явному `profile`, `project_id`, сценарию и delivery evidence; при статусе
   `blocked` сначала исправить blocker или явно зафиксировать риск.
3. Вызвать нужный write-инструмент в dry-run режиме и сохранить `plan_id`.
4. Проверить audit: целевой объект, route, diff, gate status, ожидаемый readback.
5. Включить `ALTERIOS_MCP_ALLOW_WRITE=1` только для безопасной целевой среды.
6. Повторить вызов с `dry_run=false` и тем же `plan_id`, если tool его требует.
7. Проверить readback через тот же инструмент или отдельный read-only tool.
8. Зафиксировать результат в приватной Gitea-задаче или локальном каталоге
   проекта, не добавляя project evidence в публичный MCP-репозиторий.

Для destructive/security операций нужен отдельный read-only анализ target,
dry-run typed tool или `alterios_write_safety_preflight`, затем явные gates:
`ALTERIOS_MCP_ALLOW_WRITE=1`, `ALTERIOS_MCP_ALLOW_DANGEROUS_WRITE=1`,
`allow_destructive=true`. Cross-project native content-type clone не выполняется
без явного target sandbox project, dry-run review, cleanup/readback-плана и
подтвержденного route evidence.

Быстрая CLI-проверка без live-записи:

```powershell
.\.venv\Scripts\python.exe -m alterios_mcp.live_task_preflight `
  --profile <profile> `
  --project-id <project-id> `
  --scenario-tool alterios_create_material_module `
  --work-item-ref <private-task-ref> `
  --agent-handoff-ref <private-handoff-ref> `
  --pretty
```

## Основные пользовательские сценарии

### Инвентаризировать проект

Используйте read-only tools и `alterios-deep-inventory`, чтобы получить список
форм, представлений, скриптов, диаграмм, отчетов, связей и иконок. Результаты
можно использовать как source map для последующих изменений.

### Построить тип материалов

MCP может создать content type, поля, форму добавления/редактирования, list/main
view, группу меню и тестовую запись. Запись выполняется через dry-run -> write
gate -> readback.

### Построить представление

MCP работает с представлением как с источником данных: `view`, `viewEntity`,
`joins`, `view fields`, фильтры, сортировки и контекст текущей записи. Поле,
добавленное в content type, отдельно добавляется в `view field`; связь
доказывается relation field или entity chain, а фильтрация current-record
проверяется через `dataId: [openId]`, а не только через `contentId`.
Готовность view подтверждается `view_fields_populated` и
`get-data`/`get-data-simplified`.

### Доработать форму

MCP анализирует расположение элементов, пустые места, источники данных, роли,
стили, условия, действия и иконки. После анализа можно точечно заменить tabs или
action containers без полной ручной пересборки формы.

### Подготовить иконки проекта

Перед записью форм, групп или действий с иконками сначала загрузите Google Fonts
Icons в файловый менеджер нужного проекта:

```powershell
# 1. Dry-run: получить plan_id и проверить, какие иконки будут загружены.
alterios_ensure_project_icons(
  profile="secondary",
  project_id="<project-id>",
  icon_specs=[{"semantic": "save", "google_name": "save"}],
  include_defaults=false
)

# 2. Apply: выполнить тот же вызов с dry_run=false и plan_id при ALTERIOS_MCP_ALLOW_WRITE=1.
```

Правило: в JSON форм/групп/действий использовать только UUID из результата
`alterios_ensure_project_icons`, а не строковые `save`, `more_vert`,
`visibility` и другие Google icon names. Registry хранится отдельно для каждого
`profile + project_id` в `artifacts/project-icons/...`.

Для проверки уже загруженных проектных иконок используйте read-only tools:

```powershell
# Снять иконки только из выбранной папки elFinder, без подпапок.
alterios_list_project_icons(
  profile="<profile>",
  project_id="<project-id>",
  folder_hash="elf_public_L3B1YmxpYw",
  icons_folder_name=null,
  recurse=false
)

# Скачать файлы и сформировать локальный справочник "когда какую использовать".
alterios_export_project_icons(
  profile="<profile>",
  project_id="<project-id>",
  folder_hash="elf_public_L3B1YmxpYw",
  icons_folder_name=null,
  recurse=false
)
```

Git-библиотека проектных иконок хранится в `assets/icons/project-public`.
В ней лежат SVG из прямой папки `public`, но без исходных fileId проекта.
Перед добавлением иконок в формы или группы используйте сценарный tool:

```powershell
# 1. Dry-run: проверить registry и файловый менеджер целевого проекта.
alterios_ensure_project_icon_library(
  profile="secondary",
  project_id="<project-id>",
  semantics=["save", "edit", "delete", "menu"]
)

# 2. Apply: тот же вызов с dry_run=false и plan_id при ALTERIOS_MCP_ALLOW_WRITE=1.
```

Правило: `iconId` нельзя переносить между проектами. Если нужной иконки нет
в целевом проекте, MCP загружает SVG из `assets/icons/project-public` в этот
проект и использует только новый UUID, возвращенный Alterios.

Если нужны иконки из подпапки, ее нужно указать явно:
`icons_folder_name="icons"`. По умолчанию export уважает выбранный
`folder_hash` и не спускается в подпапки. Для выбора одной иконки используйте
`alterios_resolve_project_icon`: он сначала проверяет registry, затем
файловый менеджер, и только после этого строит upload-plan через
`alterios_ensure_project_icons`.

### Связать форму, скрипт и BPMN

MCP может показать, какие действия формы запускают скрипты, какие userTask
открывают формы, какие scriptTask/listeners ссылаются на scripts и какие side
effects надо проверить после запуска процесса или завершения задачи.

### Сделать отчет или печатную форму

MCP помогает подключить Project Database source, проверить source view, openId
контекст, Stimulsoft layout и риски съезда элементов. Для визуального финального
приемочного контроля пока нужен отдельный render/UI proof.

### Подготовить постановку или ТРЗ

Business/System Analyst собирает бизнес-цель, роли, сценарии, модель данных,
представления, формы, процессы, отчеты, ограничения и acceptance criteria в
developer-ready постановку. Для формального ГОСТ/ЕСПД оформления результат
передается Documentation Scribe и `gost-documentation-builder`.

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

Перед публикацией также запускайте:

```powershell
.\.venv\Scripts\python scripts\check_public_tree.py
```

Политика разделения публичного MCP и приватных проектных материалов описана в
[docs/public-repository-data-policy.md](docs/public-repository-data-policy.md).

## Документы

- [docs/git-team-workflow.md](docs/git-team-workflow.md) - правила командной
  работы, push и разграничения business task artifacts от reusable MCP/skills.
- [docs/development-cycle-and-agent-workflow.md](docs/development-cycle-and-agent-workflow.md) -
  положение о цикле разработки, stage gates, Definition of Done и работе агентов.
- [docs/gitea-private-workboard.md](docs/gitea-private-workboard.md) -
  использование приватного Gitea как Jira-подобного рабочего поля для реальных задач.
- [docs/runtime-hygiene.md](docs/runtime-hygiene.md) -
  проверка и очистка локальных `alterios-mcp` процессов перед live-записью.
- [docs/mcp-tool-profiles.md](docs/mcp-tool-profiles.md) - профили `live`,
  `discovery`, `admin`, `full` и проверка private Gitea agent evidence.
- [docs/controlled-writes.md](docs/controlled-writes.md) - правила безопасной
  записи.
- [docs/administrator-guide.md](docs/administrator-guide.md) - инструкция
  администратора по установке, настройке, безопасной записи, проверкам и
  сопровождению MCP.
- [docs/expanded-user-scenarios.md](docs/expanded-user-scenarios.md) -
  расширенные сценарии: диаграммы, представления, группы, пользователи, роли,
  включения, файлы, действия, listeners, множественный выбор, отчеты, скрипты и
  публикация типов материалов.
- [docs/business-requirements-analyst-agent.md](docs/business-requirements-analyst-agent.md) -
  агент аналитика требований, постановка/ТРЗ, правила для представлений, связей,
  полей и фильтров.
- [docs/material-types-and-view-types-research.md](docs/material-types-and-view-types-research.md) -
  исследование типов материалов, полей, форматов `table`, `reference`, `grid`,
  `list`, `gantt`, `leaflet`, `calendar`, relation joins и
  legacy/classic исключений.
- [docs/view-format-inventory.json](docs/view-format-inventory.json) -
  машинно-читаемая матрица форматов представлений и обязательных настроек.
- [docs/optimization-plan.md](docs/optimization-plan.md) - план оптимизации:
  сценарные tools, UI/report validation, write workflow и inventory cache/diff
  health.
- [docs/alterios-method-coverage.md](docs/alterios-method-coverage.md) - матрица
  инструментов, route patterns и operation classes.
- [docs/stimulsoft-report-layout-and-analytics.md](docs/stimulsoft-report-layout-and-analytics.md) -
  правила отчетов и Stimulsoft layout.
- [docs/agents-and-skills.md](docs/agents-and-skills.md) - роли агентов и skills.
- [docs/skill-installation.md](docs/skill-installation.md) - установка repo-owned
  skills в локальный Codex.

## Следующие направления

Новые работы фиксируются в приватной Gitea или локальном project workspace и
проходят через replay smoke, targeted tests, `git diff --check` и public-tree
scan. Публичный репозиторий содержит только переиспользуемый MCP.

1. Создать отдельный target sandbox project для live-проверки
   `POST /api/content-types/clone` и cleanup/readback после clone.
2. При необходимости экспортировать true HAR из DevTools для уже снятых
   UI-сценариев; текущий in-app browser connector дал UI/route/API evidence,
   но не raw HAR stream.
3. Расширить подтвержденный render/PDF smoke до эталонного image comparison.
4. Довести release packaging и changelog process, если репозиторий готовится к
   tagged release.
